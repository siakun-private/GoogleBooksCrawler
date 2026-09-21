"""Build a file:// reader without requiring fetch, a server, or a browser session.

Chapter markup is embedded as inert JSON. Publisher styles stay inside an iframe
so reader controls and book typography cannot override each other.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from lxml import etree


def reader_data(book_json: Path):
    root = book_json.parent
    book = json.loads(book_json.read_text(encoding="utf-8"))
    chapters, positions = [], {}
    page_lookup = {p["href"]: i for i, p in enumerate(book.get("page_list", []))}
    current_page = 0
    for index, chapter in enumerate(book["chapters"]):
        path = (root / chapter["file"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Chapter is outside the content directory")
        document = etree.parse(str(path), etree.XMLParser(resolve_entities=False, no_network=True))
        body = document.find("{http://www.w3.org/1999/xhtml}body")
        if body is None:
            raise ValueError(f"Missing chapter body: {chapter['file']}")
        for node in body.iter():
            identifier = node.get("id")
            if identifier:
                href = chapter["file"] + "#" + identifier
                current_page = page_lookup.get(href, current_page)
                positions[href] = {"chapter": index, "anchor": identifier, "page": current_page}
        styles = [node.get("href") for node in document.findall(".//{http://www.w3.org/1999/xhtml}link") if node.get("rel") == "stylesheet"]
        # HTML serialization closes empty anchors; XML self-closing <a/> would
        # otherwise consume subsequent content when assigned to iframe.srcdoc.
        markup = (html.escape(body.text) if body.text else "") + "".join(etree.tostring(child, encoding="unicode", method="html") for child in body)
        chapters.append({**chapter, "html": markup, "styles": styles})
    def destination(href):
        if href in positions:
            return positions[href]
        parsed = urlsplit(href)
        index = next(i for i, c in enumerate(chapters) if c["file"] == unquote(parsed.path))
        return {"chapter": index, "anchor": unquote(parsed.fragment), "page": 0}
    pages = [{**p, **destination(p["href"])} for p in book.get("page_list", [])]
    if not pages:
        pages = [{"label": str(i + 1), "href": c["file"], "chapter": i, "anchor": "", "page": i} for i, c in enumerate(chapters)]
    toc = [{**entry, **destination(entry["href"])} for entry in book.get("toc", [])]
    return {"id": book["id"], "title": book["title"], "language": book.get("language", "ko"), "chapters": chapters, "pages": pages, "toc": toc}


def write_html_reader(book_json: Path):
    book_json = Path(book_json).resolve()
    data = reader_data(book_json)
    templates = Path(__file__).parent / "reader"
    template = (templates / "reader.html").read_text(encoding="utf-8")
    # Escaping '<' prevents book text from terminating the inert JSON script.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    replacements = {
        "@@TITLE@@": html.escape(data["title"]),
        "@@UI_CSS@@": (templates / "reader.css").read_text(encoding="utf-8"),
        "@@CONTENT_CSS@@": json.dumps((templates / "content.css").read_text(encoding="utf-8")).replace("<", "\\u003c"),
        "@@BOOK@@": payload,
        "@@SCRIPT@@": (templates / "reader.js").read_text(encoding="utf-8"),
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    output = book_json.parent / "index.html"
    temporary = output.with_suffix(".html.tmp")
    try:
        temporary.write_text(template, encoding="utf-8")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the offline HTML reader from a saved book")
    parser.add_argument("book_json", type=Path)
    args = parser.parse_args()
    print(write_html_reader(args.book_json))
