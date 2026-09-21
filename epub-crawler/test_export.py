"""Check that packaging fails on broken offline content before replacing an EPUB."""

import base64
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from build_epub import build_epub, validate_content
from html_reader import reader_data, write_html_reader
from lxml import etree, html as lxml_html


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.root = self.directory / "content"
        for part in ("text", "assets", "styles"):
            (self.root / part).mkdir(parents=True)
        (self.root / "assets/dot.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="))
        (self.root / "styles/book.css").write_text("body {color: #222;}", encoding="utf-8")
        self.chapter = self.root / "text/one.xhtml"
        self.chapter.write_text('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>One</title><link rel="stylesheet" href="../styles/book.css"/></head><body><p id="one">본문</p><img src="../assets/dot.png" alt=""/><a href="two.xhtml#note">각주</a></body></html>', encoding="utf-8")
        (self.root / "text/two.xhtml").write_text('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Two</title></head><body><p id="note">각주 내용</p></body></html>', encoding="utf-8")
        book = {"id": "fixture", "title": "테스트", "authors": ["작성자"], "language": "ko", "chapters": [{"file": "text/one.xhtml", "title": "One"}, {"file": "text/two.xhtml", "title": "Two"}], "toc": [{"href": "text/one.xhtml#one", "label": "본문", "depth": 0}, {"href": "text/two.xhtml#note", "label": "각주", "depth": 1}]}
        self.book_json = self.root / "book.json"
        self.book_json.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8")
        self.output = self.directory / "book.epub"

    def tearDown(self):
        self.temporary.cleanup()

    def test_offline_package_preserves_chapters_and_footnote(self):
        build_epub(self.book_json, self.output)
        with zipfile.ZipFile(self.output) as archive:
            first = archive.infolist()[0]
            self.assertEqual(first.filename, "mimetype")
            self.assertEqual(first.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(archive.read("OEBPS/text/one.xhtml"), self.chapter.read_bytes())
            self.assertIn("OEBPS/text/two.xhtml", archive.namelist())
            self.assertNotIn("OEBPS/book.json", archive.namelist())
            self.assertIsNone(archive.testzip())
        self.assertTrue((self.root / "index.html").is_file())

    def test_missing_image_does_not_replace_previous_output(self):
        self.output.write_bytes(b"previous output")
        (self.root / "assets/dot.png").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            build_epub(self.book_json, self.output)
        self.assertEqual(self.output.read_bytes(), b"previous output")

    def test_missing_cross_chapter_footnote_is_rejected(self):
        self.chapter.write_text(self.chapter.read_text(encoding="utf-8").replace("two.xhtml#note", "two.xhtml#absent"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Missing fragment"):
            validate_content(self.book_json)

    def test_css_remote_dependency_is_rejected(self):
        (self.root / "styles/book.css").write_text('@font-face {src:url("https://example.com/font.woff")}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "External dependency"):
            validate_content(self.book_json)

    def test_path_outside_content_is_rejected(self):
        (self.directory / "outside.png").write_bytes(b"outside")
        self.chapter.write_text(self.chapter.read_text(encoding="utf-8").replace("../assets/dot.png", "../../outside.png"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "out-of-root"):
            validate_content(self.book_json)

    def test_html_reader_keeps_text_and_footnote_when_parsed_as_html(self):
        self.chapter.write_text(self.chapter.read_text(encoding="utf-8").replace('본문</p>', '앞<a id="position"/>뒤</p>'), encoding="utf-8")
        data = reader_data(self.book_json)
        document = lxml_html.fromstring(data["chapters"][0]["html"])
        self.assertEqual("".join(document.itertext()), "앞뒤각주")
        self.assertEqual(document.xpath('//a[@id="position"]')[0].text_content(), "")
        self.assertEqual(document.xpath('//a[@href]')[0].get("href"), "two.xhtml#note")

    def test_book_text_cannot_close_embedded_json_script(self):
        document = etree.parse(str(self.chapter))
        document.find('.//{http://www.w3.org/1999/xhtml}p').text = '</script><script>window.unwanted=true</script>'
        document.write(str(self.chapter), encoding="utf-8")
        output = write_html_reader(self.book_json)
        page = lxml_html.parse(str(output))
        data = json.loads(page.xpath('//script[@id="book-data"]')[0].text)
        self.assertIn("&lt;/script&gt;", data["chapters"][0]["html"])
        self.assertEqual(len(page.xpath('//script[not(@type)]')), 1)


if __name__ == "__main__":
    unittest.main()
