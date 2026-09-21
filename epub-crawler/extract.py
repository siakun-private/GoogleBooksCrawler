"""Capture complete reader segments and their original assets, then build an EPUB.

The displayed pages contain sliced/reopened paragraphs. Detached source segments
in the reader retain complete paragraphs, code blocks, and original image URLs;
capturing those avoids guessing how to join text at screen-page boundaries.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from lxml import etree
from PIL import Image

from browser import Browser

XHTML = "http://www.w3.org/1999/xhtml"
XLINK = "http://www.w3.org/1999/xlink"
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)


def bootstrap(browser):
    source = browser.evaluate("[...document.scripts].find(s=>s.textContent.startsWith('reader.start(')).textContent", reader=False)
    match = re.match(r"^reader\.start\('(?:\\.|[^'\\])*'\s*,\s*", source)
    if not match:
        raise RuntimeError("The reader bootstrap format has changed")
    decoder = json.JSONDecoder()
    _, offset = decoder.raw_decode(source, match.end())
    while source[offset] in ", \t\r\n":
        offset += 1
    metadata, _ = decoder.raw_decode(source, offset)
    for key in ("metadata", "segment", "toc_entry", "page"):
        if key not in metadata:
            raise RuntimeError(f"Reader metadata is missing {key}")
    return metadata


def scan_segments(browser):
    proto = browser.call("Runtime.evaluate", {"expression": "HTMLDivElement.prototype", "objectGroup": "book-export"}, browser.reader_session)["result"]["objectId"]
    objects = browser.call("Runtime.queryObjects", {"prototypeObjectId": proto, "objectGroup": "book-export"}, browser.reader_session)["objects"]["objectId"]
    # Keep only the unpaginated source, never a displayed page with split text.
    function = """function(){
      window.__localBookSources ||= new Map();
      for (const e of this) {
        if (e.className !== 'gb-segment' || e.hasAttribute('ocean-sliced-element')) continue;
        const id=e.querySelector('[id^="GBS."]')?.id;
        if (!id) continue;
        const previous=window.__localBookSources.get(id);
        if (!previous || previous.textContent.length < e.textContent.length) window.__localBookSources.set(id,e);
      }
      return [...window.__localBookSources].map(([id,e])=>({id,chars:e.textContent.length,images:e.querySelectorAll('img,image').length}));
    }"""
    result = browser.call("Runtime.callFunctionOn", {"objectId": objects, "functionDeclaration": function, "returnByValue": True}, browser.reader_session)
    browser.call("Runtime.releaseObjectGroup", {"objectGroup": "book-export"}, browser.reader_session)
    if result.get("exceptionDetails"):
        raise RuntimeError("Cannot inspect complete reader segments")
    return result["result"]["value"]


def get_segment(browser, expected_id, reading_position):
    def lookup():
        return browser.evaluate("(()=>{const e=window.__localBookSources?.get(" + json.dumps(expected_id) + ");return e?{xml:new XMLSerializer().serializeToString(e),chars:e.textContent.length,head:e.querySelector('h1,h2,h3')?.textContent?.trim()||''}:null})()")
    found = lookup()
    if found:
        return found
    browser.navigate_position(reading_position)
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        scan_segments(browser)
        found = lookup()
        if found:
            return found
        time.sleep(0.3)
    raise RuntimeError(f"Complete source segment did not load: {expected_id}")


class Assets:
    def __init__(self, browser, root, records=None):
        self.browser = browser
        self.root = root
        self.paths = {}
        self.records = list(records or [])
        (root / "assets").mkdir(parents=True, exist_ok=True)

    def fetch(self, url):
        parsed = urlparse(url)
        reader = parsed.scheme in {"blob", "data"}
        if not reader and not (parsed.scheme == "https" and parsed.hostname == "play.google.com" and parsed.path.startswith("/books/") and parse_qs(parsed.query).get("id") == [self.browser.book_id]):
            raise RuntimeError("An embedded asset points outside the selected book")
        expression = """(async()=>{const r=await fetch(URL_VALUE,{signal:AbortSignal.timeout(20000)});
          if(!r.ok)throw Error('Asset HTTP '+r.status);
          const a=new Uint8Array(await r.arrayBuffer());let s='';
          for(let i=0;i<a.length;i+=32768)s+=String.fromCharCode(...a.subarray(i,i+32768));
          return {mime:r.headers.get('content-type')||'',base64:btoa(s)};})()""".replace("URL_VALUE", json.dumps(url))
        for attempt in range(3):
            try:
                result = self.browser.evaluate(expression, reader=reader)
                return base64.b64decode(result["base64"], validate=True), result["mime"]
            except (RuntimeError, OSError):
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)

    def save(self, url, label=None, font=False):
        if url in self.paths:
            return self.paths[url]
        parsed = urlparse(url)
        pg = parse_qs(parsed.query).get("pg", [None])[0]
        name = label or pg or "asset"
        stem = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(name).stem).strip(".") or "asset"
        data, mime = self.fetch(url)
        record = {"name": name, "bytes": len(data)}
        if font:
            signature = data[:4]
            extension = {b"OTTO": ".otf", b"wOFF": ".woff", b"wOF2": ".woff2", b"\x00\x01\x00\x00": ".ttf"}.get(signature)
            if extension is None:
                raise RuntimeError(f"Invalid font resource: {name}")
        else:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                record.update(width=image.width, height=image.height)
                extension = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "WEBP": ".webp"}.get(image.format)
            if extension is None:
                raise RuntimeError(f"Unsupported embedded image format: {name}")
        digest = hashlib.sha256(data).hexdigest()
        relative = f"assets/{stem}-{digest[:12]}{extension}"
        target = self.root / relative
        if not target.exists():
            target.write_bytes(data)
        record.update(file=relative, sha256=digest)
        if not any(r.get("file") == relative for r in self.records):
            self.records.append(record)
        self.paths[url] = relative
        return relative

    def inventory(self):
        # Re-read saved files so resumed captures report earlier assets too.
        known = {r["file"]: r for r in self.records}
        records = []
        for path in sorted((self.root / "assets").iterdir()):
            if not path.is_file():
                continue
            relative = path.relative_to(self.root).as_posix()
            data = path.read_bytes()
            record = {"name": known.get(relative, {}).get("name", re.sub(r"-[0-9a-f]{12}(?=\.)", "", path.name)), "file": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            if path.suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                with Image.open(io.BytesIO(data)) as image:
                    image.verify()
                with Image.open(io.BytesIO(data)) as image:
                    record.update(width=image.width, height=image.height)
            records.append(record)
        self.records = records
        return records

    def css(self, css, label_prefix="font"):
        families = {}
        for block in re.findall(r"@font-face\s*\{[^}]*\}", css, re.I):
            family = re.search(r"font-family\s*:\s*(['\"]?)(.*?)\1\s*;", block, re.I)
            for match in CSS_URL.finditer(block):
                families[match[2]] = family[2] if family else label_prefix
        def replace(match):
            url = match[2]
            if not url or url.startswith("#"):
                return match[0]
            path = self.save(url, families.get(url), font=url in families)
            return 'url("../' + path + '")'
        return CSS_URL.sub(replace, css)


def capture_styles(browser, assets):
    css = browser.evaluate("[...document.querySelectorAll('style')].find(s=>s.textContent.startsWith('._')&&s.textContent.includes('@font-face'))?.textContent")
    if not css:
        raise RuntimeError("The book's stylesheet is not available")
    scope = css.split("{", 1)[0].strip()
    css = css.replace(scope, ".book-content")
    css = assets.css(css)
    # Pagination dimensions belong to the web reader, not a reflowable EPUB.
    css += """
/* Keep original typography while letting the reading app choose its page size. */
body.book-content { margin: 0 auto; padding: 1.2em; max-width: 56em; }
.book-content .gb-segment { height: auto; }
.book-content img, .book-content svg { max-width: 100%; height: auto; }
.book-content svg { display: block; }
.book-content pre { overflow-wrap: anywhere; }
"""
    directory = assets.root / "styles"
    directory.mkdir(exist_ok=True)
    (directory / "book.css").write_text(css, encoding="utf-8")


def make_chapter(segment, title, language, assets):
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(segment["xml"].encode("utf-8"), parser)
    for element in root.iter():
        tag = etree.QName(element).localname
        if tag in {"script", "iframe", "object", "embed"}:
            raise RuntimeError(f"Unexpected active content in book source: {tag}")
        for attr in list(element.attrib):
            if attr.startswith("ocean-") or attr == "resource-id" or attr.lower().startswith("on"):
                del element.attrib[attr]
        for attr in ("src", "href", f"{{{XLINK}}}href"):
            url = element.get(attr)
            if not url or tag == "a":
                continue
            element.set(attr, "../" + assets.save(url))
        if element.get("style") and "url(" in element.get("style"):
            element.set("style", assets.css(element.get("style")))
    document = etree.Element(f"{{{XHTML}}}html", nsmap={None: XHTML})
    document.set("lang", language)
    document.set("{http://www.w3.org/XML/1998/namespace}lang", language)
    head = etree.SubElement(document, f"{{{XHTML}}}head")
    etree.SubElement(head, f"{{{XHTML}}}title").text = title
    etree.SubElement(head, f"{{{XHTML}}}meta", charset="utf-8")
    etree.SubElement(head, f"{{{XHTML}}}link", rel="stylesheet", type="text/css", href="../styles/book.css")
    body = etree.SubElement(document, f"{{{XHTML}}}body", {"class": "book-content"})
    body.append(root)
    return document


def write_xml(path, root):
    path.write_bytes(etree.tostring(root, encoding="utf-8", xml_declaration=True, doctype="<!DOCTYPE html>"))


def chapter_title(source, segment, toc, book_title):
    if source["head"] or segment.get("title"):
        title = source["head"] or segment["title"]
    else:
        root = etree.fromstring(source["xml"].encode("utf-8"))
        paragraphs = ["".join(p.itertext()).strip() for p in root.iter(f"{{{XHTML}}}p")]
        first = next((p for p in paragraphs if p), "")
        # Some publishers mark front-matter headings as ordinary paragraphs.
        title = first if first and len(first) <= 80 else toc[0]["label"] if toc else book_title
    return " ".join(title.split())


def capture(book_id, destination, resume=False, endpoint=None):
    destination.mkdir(parents=True, exist_ok=True)
    content = destination / "content"
    text_dir = content / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    state_file = destination / "capture-state.json"
    if state_file.exists() and not resume:
        raise RuntimeError("Capture output already exists; use --resume or choose another --output directory")
    previous = json.loads(state_file.read_text(encoding="utf-8")) if resume and state_file.exists() else {}
    if previous and previous.get("id") != book_id:
        raise RuntimeError("The capture directory belongs to another book")
    chapters = []
    with Browser(book_id, endpoint) as browser:
        original = browser.original_url
        meta = bootstrap(browser)
        if meta["metadata"]["volume_id"] != book_id:
            raise RuntimeError("Reader metadata does not match the requested book")
        if previous.get("volume_version") and previous["volume_version"] != meta["volume_version"]:
            raise RuntimeError("The book edition changed; capture it into a new output directory")
        assets = Assets(browser, content, previous.get("assets"))
        scan_segments(browser)
        capture_styles(browser, assets)
        try:
            for index, segment in enumerate(meta["segment"]):
                # A segment can begin at the previous page's trailing anchor.
                # The reader's explicit start position is authoritative.
                expected_id = segment["start_position"]
                filename = f"text/{index:03d}-{Path(segment['label']).stem}.xhtml"
                target = content / filename
                cached = next((c for c in previous.get("chapters", []) if c["file"] == filename), None)
                if resume and cached and target.exists():
                    etree.parse(str(target))
                    chapter = cached
                else:
                    source = get_segment(browser, expected_id, expected_id)
                    toc = [e for e in meta["toc_entry"] if e.get("segment_index") == index]
                    title = chapter_title(source, segment, toc, meta["metadata"]["title"])
                    document = make_chapter(source, title, meta.get("language", "ko"), assets)
                    write_xml(target, document)
                    chapter = {"file": filename, "title": title, "first_id": expected_id, "source_chars": source["chars"]}
                chapters.append(chapter)
                state_file.write_text(json.dumps({"id": book_id, "volume_version": meta["volume_version"], "chapters": chapters, "assets": assets.records}, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[{index+1}/{len(meta['segment'])}] {segment['label']} ({chapter['source_chars']} characters)", flush=True)
        finally:
            position = parse_qs(urlparse(original).query).get("pg", [None])[0]
            if position:
                browser.navigate_position(position)
            browser.evaluate("delete window.__localBookSources;true")
        anchor_map = {}
        documents = []
        for chapter in chapters:
            document = etree.parse(str(content / chapter["file"]))
            root = document.find(f".//{{{XHTML}}}body/{{{XHTML}}}div")
            if root is None or len("".join(root.itertext()).encode("utf-16-le")) // 2 != chapter["source_chars"]:
                raise RuntimeError(f"Saved chapter text differs from the captured source: {chapter['file']}")
            documents.append(document)
            for element in document.iter():
                if element.get("id"):
                    anchor_map.setdefault(element.get("id"), chapter["file"])
        def local_href(position):
            if position in anchor_map:
                return anchor_map[position] + "#" + position
            page = re.match(r"GBS\.[A-Z]+\d+", position)
            if page and page[0] in anchor_map:
                return anchor_map[page[0]] + "#" + page[0]
            raise RuntimeError(f"Missing reading-position anchor: {position}")
        for chapter, document in zip(chapters, documents):
            for element in document.iter(f"{{{XHTML}}}a"):
                href = element.get("href")
                if not href:
                    continue
                parsed = urlparse(href)
                position = parse_qs(parsed.query).get("pg", [None])[0]
                if href.startswith("#") and unquote(href[1:]) in anchor_map:
                    mapped = local_href(unquote(href[1:]))
                    element.set("href", Path(mapped.split("#")[0]).name + "#" + mapped.split("#", 1)[1])
                elif position and parse_qs(parsed.query).get("id") == [book_id]:
                    mapped = local_href(position)
                    element.set("href", Path(mapped.split("#")[0]).name + "#" + mapped.split("#", 1)[1])
            write_xml(content / chapter["file"], document.getroot())
        missing = [p["pid"] for p in meta["page"] if "GBS." + p["pid"] not in anchor_map]
        if missing:
            raise RuntimeError(f"Missing original page anchors: {', '.join(missing)}")
        authors = meta["metadata"].get("authors", [])
        if isinstance(authors, str):
            authors = [authors]
        book = {"id": book_id, "title": meta["metadata"]["title"], "authors": authors, "publisher": meta["metadata"].get("publisher", ""), "language": meta.get("language", "ko"), "chapters": chapters,
                "toc": [{"label": entry["label"], "depth": entry.get("depth", 0), "href": local_href(entry["reading_position"])} for entry in meta["toc_entry"]],
                "page_list": [{"label": p.get("title", str(index + 1)), "href": local_href("GBS." + p["pid"])} for index, p in enumerate(meta["page"])]}
        cover = next((e for e in documents[0].iter() if etree.QName(e).localname in {"img", "image"}), None)
        if cover is not None:
            cover_href = cover.get("src") or cover.get(f"{{{XLINK}}}href") or cover.get("href")
            if cover_href:
                book["cover_image"] = cover_href.removeprefix("../")
        book_path = content / "book.json"
        book_path.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
        assets.inventory()
        state_file.write_text(json.dumps({"id": book_id, "volume_version": meta["volume_version"], "chapters": chapters, "assets": assets.records}, ensure_ascii=False, indent=2), encoding="utf-8")
        report = {"book_id": book_id, "title": book["title"], "chapters": len(chapters), "expected_chapters": len(meta["segment"]), "original_page_anchors": len(meta["page"]), "toc_entries": len(book["toc"]), "source_characters": sum(c["source_chars"] for c in chapters), "assets": assets.records, "missing_page_anchors": missing}
        (destination / "capture-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Captured {len(chapters)} complete segments and {len(meta['page'])} original page anchors.", flush=True)
        return book_path


def main():
    parser = argparse.ArgumentParser(description="Save an open, signed-in Google Play Books reader as local XHTML and EPUB")
    parser.add_argument("--book-id", required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "output")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--cdp", help="Optional explicit Orca tab-scoped loopback CDP WebSocket URL")
    parser.add_argument("--capture-only", action="store_true")
    args = parser.parse_args()
    if args.cdp and not args.cdp.startswith("ws://127.0.0.1:"):
        parser.error("--cdp must point to a loopback Orca proxy")
    book_path = capture(args.book_id, args.output.resolve(), args.resume, args.cdp)
    if not args.capture_only:
        from build_epub import build_epub
        metadata = json.loads(book_path.read_text(encoding="utf-8"))
        title = re.sub(r'[<>:"/\\|?*]', "_", metadata["title"])
        output = args.output / f"{title}.epub"
        build_epub(book_path, output)
        print(f"Saved: {output.resolve()}")


if __name__ == "__main__":
    main()
