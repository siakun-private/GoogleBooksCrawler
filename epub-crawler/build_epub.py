"""Build an offline EPUB from captured XHTML, independent of the live reader.

Validate references before packaging so a successful ZIP operation cannot hide
missing pictures, fonts, navigation targets, or a partial capture.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from html_reader import write_html_reader

XHTML = "http://www.w3.org/1999/xhtml"
SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
EPUB = "http://www.idpf.org/2007/ops"
OPF = "http://www.idpf.org/2007/opf"
DC = "http://purl.org/dc/elements/1.1/"
NCX = "http://www.daisy.org/z3986/2005/ncx/"
MIME = {".xhtml": "application/xhtml+xml", ".css": "text/css", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".svg": "image/svg+xml", ".woff": "font/woff", ".woff2": "font/woff2", ".otf": "font/otf", ".ttf": "font/ttf"}
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)


def xml_bytes(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def local_target(root, source, reference, allow_external=False):
    url = urlsplit(reference)
    if url.scheme or url.netloc:
        if allow_external and url.scheme in {"http", "https", "mailto", "tel"}:
            return None
        raise ValueError(f"External dependency in {source.relative_to(root)}")
    path = unquote(url.path)
    if "\\" in path or path.startswith("/"):
        raise ValueError(f"Non-relative path in {source.relative_to(root)}")
    target = (source.parent / path).resolve() if path else source.resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError(f"Missing or out-of-root dependency: {source.relative_to(root)} -> {reference}")
    return target, unquote(url.fragment)


def validate_content(book_json):
    root = book_json.resolve().parent
    book = json.loads(book_json.read_text(encoding="utf-8"))
    if not book.get("chapters"):
        raise ValueError("No chapters to package")
    files = {}
    documents = {}
    ids = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {"book.json", "index.html"}:
            continue
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or path.suffix not in MIME:
            raise ValueError(f"Unsupported package file: {relative}")
        files[relative] = path
        if path.suffix in {".xhtml", ".svg"}:
            document = ET.parse(path)
            documents[path.resolve()] = document
            found = [e.attrib["id"] for e in document.iter() if "id" in e.attrib]
            if len(set(found)) != len(found):
                raise ValueError(f"Duplicate element IDs in {relative}")
            ids[path.resolve()] = set(found)
    references = []
    for path, document in documents.items():
        for element in document.iter():
            name = element.tag.rsplit("}", 1)[-1]
            if name in {"script", "iframe", "object", "embed"}:
                raise ValueError(f"Active embedded content in {path.name}")
            for attribute in ("src", "href", f"{{{XLINK}}}href", "poster"):
                value = element.get(attribute)
                if value:
                    references.append((path, value, name == "a"))
            for value in [element.get("style", ""), element.text or "" if name == "style" else ""]:
                references.extend((path, match[2], False) for match in CSS_URL.finditer(value))
    for path in files.values():
        if path.suffix == ".css":
            css = path.read_text(encoding="utf-8")
            if re.search(r"@import\b", css, re.I):
                raise ValueError(f"CSS imports must be localized first: {path.name}")
            references.extend((path, match[2], False) for match in CSS_URL.finditer(css))
    for entry in book["chapters"]:
        references.append((book_json, entry["file"], False))
    for entry in book.get("toc", []) + book.get("page_list", []):
        references.append((book_json, entry["href"], False))
    if book.get("cover_image"):
        references.append((book_json, book["cover_image"], False))
    for source, href, allow_external in references:
        resolved = local_target(root, source.resolve(), href, allow_external)
        if resolved is None:
            continue
        target, fragment = resolved
        if target.relative_to(root).as_posix() not in files:
            raise ValueError(f"Dependency will not be packaged: {href}")
        if fragment and fragment not in ids.get(target, set()):
            raise ValueError(f"Missing fragment: {source.name} -> {href}")
    return book, files, documents


def toc_tree(entries):
    roots = []
    stack = []
    for entry in entries:
        node = {**entry, "children": []}
        depth = int(entry.get("depth", 0))
        while stack and stack[-1][0] >= depth:
            stack.pop()
        (stack[-1][1]["children"] if stack else roots).append(node)
        stack.append((depth, node))
    return roots


def navigation(book):
    ET.register_namespace("", XHTML)
    ET.register_namespace("epub", EPUB)
    root = ET.Element(f"{{{XHTML}}}html", {"lang": book["language"]})
    head = ET.SubElement(root, f"{{{XHTML}}}head")
    ET.SubElement(head, f"{{{XHTML}}}title").text = book["title"]
    body = ET.SubElement(root, f"{{{XHTML}}}body")
    nav = ET.SubElement(body, f"{{{XHTML}}}nav", {f"{{{EPUB}}}type": "toc", "id": "toc"})
    ET.SubElement(nav, f"{{{XHTML}}}h1").text = "목차"
    def append_nodes(parent, nodes):
        ordered = ET.SubElement(parent, f"{{{XHTML}}}ol")
        for node in nodes:
            li = ET.SubElement(ordered, f"{{{XHTML}}}li")
            ET.SubElement(li, f"{{{XHTML}}}a", {"href": node["href"]}).text = node["label"]
            if node["children"]:
                append_nodes(li, node["children"])
    entries = book.get("toc") or [{"label": c["title"], "href": c["file"], "depth": 0} for c in book["chapters"]]
    append_nodes(nav, toc_tree(entries))
    if book.get("page_list"):
        pages = ET.SubElement(body, f"{{{XHTML}}}nav", {f"{{{EPUB}}}type": "page-list", "hidden": "hidden"})
        ET.SubElement(pages, f"{{{XHTML}}}h2").text = "원본 페이지"
        ordered = ET.SubElement(pages, f"{{{XHTML}}}ol")
        for entry in book["page_list"]:
            li = ET.SubElement(ordered, f"{{{XHTML}}}li")
            ET.SubElement(li, f"{{{XHTML}}}a", href=entry["href"]).text = str(entry["label"])
    return xml_bytes(root)


def legacy_navigation(book):
    ET.register_namespace("", NCX)
    root = ET.Element(f"{{{NCX}}}ncx", {"version": "2005-1"})
    head = ET.SubElement(root, f"{{{NCX}}}head")
    ET.SubElement(head, f"{{{NCX}}}meta", name="dtb:uid", content="urn:google:books:" + book["id"])
    title = ET.SubElement(root, f"{{{NCX}}}docTitle")
    ET.SubElement(title, f"{{{NCX}}}text").text = book["title"]
    nav = ET.SubElement(root, f"{{{NCX}}}navMap")
    order = 0
    def add(parent, nodes):
        nonlocal order
        for node in nodes:
            order += 1
            point = ET.SubElement(parent, f"{{{NCX}}}navPoint", id=f"nav-{order}", playOrder=str(order))
            label = ET.SubElement(point, f"{{{NCX}}}navLabel")
            ET.SubElement(label, f"{{{NCX}}}text").text = node["label"]
            ET.SubElement(point, f"{{{NCX}}}content", src=node["href"])
            add(point, node["children"])
    entries = book.get("toc") or [{"label": c["title"], "href": c["file"], "depth": 0} for c in book["chapters"]]
    add(nav, toc_tree(entries))
    return xml_bytes(root)


def package_document(book, files, documents):
    ET.register_namespace("", OPF)
    ET.register_namespace("dc", DC)
    root = ET.Element(f"{{{OPF}}}package", {"version": "3.0", "unique-identifier": "book-id", "prefix": "rendition: http://www.idpf.org/vocab/rendition/#"})
    metadata = ET.SubElement(root, f"{{{OPF}}}metadata")
    ET.SubElement(metadata, f"{{{DC}}}identifier", id="book-id").text = "urn:google:books:" + book["id"]
    ET.SubElement(metadata, f"{{{DC}}}title").text = book["title"]
    ET.SubElement(metadata, f"{{{DC}}}language").text = book["language"]
    for author in book.get("authors", []):
        ET.SubElement(metadata, f"{{{DC}}}creator").text = author
    if book.get("publisher"):
        ET.SubElement(metadata, f"{{{DC}}}publisher").text = book["publisher"]
    ET.SubElement(metadata, f"{{{OPF}}}meta", property="dcterms:modified").text = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ET.SubElement(metadata, f"{{{OPF}}}meta", property="rendition:layout").text = "reflowable"
    manifest = ET.SubElement(root, f"{{{OPF}}}manifest")
    mapping = {}
    for index, (relative, path) in enumerate(files.items()):
        identifier = f"item-{index}"
        mapping[relative] = identifier
        attrs = {"id": identifier, "href": relative, "media-type": MIME[path.suffix]}
        properties = []
        if relative == book.get("cover_image"):
            properties.append("cover-image")
        if path.suffix == ".xhtml" and any(e.tag == f"{{{SVG}}}svg" for e in documents[path.resolve()].iter()):
            properties.append("svg")
        if properties:
            attrs["properties"] = " ".join(properties)
        ET.SubElement(manifest, f"{{{OPF}}}item", attrs)
    ET.SubElement(manifest, f"{{{OPF}}}item", {"id": "nav", "href": "nav.xhtml", "media-type": "application/xhtml+xml", "properties": "nav"})
    ET.SubElement(manifest, f"{{{OPF}}}item", {"id": "ncx", "href": "toc.ncx", "media-type": "application/x-dtbncx+xml"})
    if book.get("cover_image"):
        ET.SubElement(metadata, f"{{{OPF}}}meta", name="cover", content=mapping[book["cover_image"]])
    spine = ET.SubElement(root, f"{{{OPF}}}spine", toc="ncx")
    for chapter in book["chapters"]:
        ET.SubElement(spine, f"{{{OPF}}}itemref", idref=mapping[chapter["file"]])
    return xml_bytes(root)


def build_epub(book_json: Path, output: Path):
    book_json, output = Path(book_json).resolve(), Path(output).resolve()
    book, files, documents = validate_content(book_json)
    if output.is_relative_to(book_json.parent):
        raise ValueError("EPUB output must be outside the content directory")
    generated = {"OEBPS/nav.xhtml": navigation(book), "OEBPS/toc.ncx": legacy_navigation(book), "OEBPS/package.opf": package_document(book, files, documents)}
    container = b'<?xml version="1.0" encoding="UTF-8"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
    generated["META-INF/container.xml"] = container
    for data in generated.values():
        ET.fromstring(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".epub-", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            for relative, path in files.items():
                archive.write(path, "OEBPS/" + relative)
            for relative, data in generated.items():
                archive.writestr(relative, data)
        with zipfile.ZipFile(temporary) as archive:
            failure = archive.testzip()
            if failure:
                raise ValueError(f"ZIP checksum failed: {failure}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    write_html_reader(book_json)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package captured local XHTML and assets into EPUB3")
    parser.add_argument("book_json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(build_epub(arguments.book_json, arguments.output))
