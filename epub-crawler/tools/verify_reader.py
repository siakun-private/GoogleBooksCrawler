"""Verify saved content and the exact local reader tab without a fixed CDP port.

The live check navigates the reader, so preserve its storage and restore it even
when a check fails. Nothing in this tool navigates the signed-in Google book.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from urllib.parse import unquote, urlsplit

from lxml import etree, html
import websocket

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from browser import Browser
from build_epub import validate_content
from html_reader import reader_data


class LocalReader(Browser):
    """Reuse Orca discovery/transport, with a local URL and no Google OOPIF."""

    def __init__(self, path: Path):
        self.path = path.resolve()
        self.orca = os.environ.get("ORCA_CLI_COMMAND") or shutil.which("orca")
        if not self.orca:
            raise RuntimeError("Orca CLI was not found")
        matches = [t for t in self.cli("tab", "list")["tabs"] if self.is_book(t.get("url", ""))]
        if len(matches) != 1:
            raise RuntimeError(f"Open the generated index.html in exactly one Orca tab; found {len(matches)} matching tabs")
        self.page = matches[0]["browserPageId"]
        endpoint = self.discover_proxy()
        if not endpoint:
            self.cli("network", "--limit", "1", "--page", self.page)
            endpoint = self.discover_proxy()
        if not endpoint:
            raise RuntimeError("The selected local reader has no Orca debugger proxy")
        self.ws = websocket.create_connection(endpoint, timeout=60, suppress_origin=True)
        self.sequence, self.events, self.reader_session = 0, [], None
        if not self.is_book(self.evaluate("location.href", reader=False)):
            self.close()
            raise RuntimeError("The debugger proxy does not belong to the selected local file")

    def is_book(self, url):
        parsed = urlsplit(url)
        expected = urlsplit(self.path.as_uri())
        return parsed.scheme == "file" and parsed.netloc == expected.netloc and unquote(parsed.path).casefold() == unquote(expected.path).casefold()

    def evaluate(self, expression, reader=False):
        return super().evaluate(expression, reader=False)

    def reload(self):
        self.evaluate("if(document.body) document.body.dataset.ready='false'")
        self.call("Page.reload", {"ignoreCache": True})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if self.evaluate("document.body?.dataset.ready==='true'"):
                    return
            except RuntimeError:
                pass
            time.sleep(0.1)
        raise RuntimeError("Local reader did not become ready after reload")

    def close(self):
        if getattr(self, "ws", None):
            self.ws.close()
            self.ws = None


def verify_files(book_json):
    validate_content(book_json)
    data = reader_data(book_json)
    for chapter in data["chapters"]:
        source = etree.parse(str(book_json.parent / chapter["file"])).find("{http://www.w3.org/1999/xhtml}body")
        rendered = html.fragment_fromstring(chapter["html"], create_parent="div")
        if "".join(source.itertext()) != "".join(rendered.itertext()):
            raise ValueError(f"HTML serialization changed text: {chapter['file']}")
        if [e.get("id") for e in source.iter() if e.get("id")] != [e.get("id") for e in rendered.iter() if e.get("id")]:
            raise ValueError(f"HTML serialization changed anchors: {chapter['file']}")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("book_json", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    book_json = args.book_json.resolve()
    data = verify_files(book_json)
    index = book_json.parent / "index.html"
    report_path = args.report or book_json.parent.parent / "reader-verification.latest.json"
    report = {"book_id": data["id"], "html_sha256": hashlib.sha256(index.read_bytes()).hexdigest(), "file_validation": "passed", "chapters": len(data["chapters"])}
    script = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    with LocalReader(index) as browser:
        prefix = json.dumps(f"offline-reader:{data['id']}:")
        storage = browser.evaluate("(()=>{const result={};for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);if(k.startsWith(" + prefix + "))result[k]=localStorage.getItem(k)}return result})()")
        try:
            browser.reload()
            actual_id = browser.evaluate("JSON.parse(document.getElementById('book-data').textContent).id")
            if actual_id != data["id"]:
                raise ValueError("The local reader belongs to a different book; regenerate it first")
            report["browser"] = browser.evaluate(script)
        finally:
            browser.evaluate("(()=>{const saved=" + json.dumps(storage) + ";for(const key of Object.keys(localStorage)){if(key.startsWith(" + prefix + ")&&!(key in saved))localStorage.removeItem(key)}for(const [key,value]of Object.entries(saved))localStorage.setItem(key,value)})()")
            browser.reload()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["browser"]["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
