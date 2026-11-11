"""Attached files: text extraction for many formats, the size budget and how files reach the model."""
import tempfile
import unittest
import zipfile
from pathlib import Path

from core import extract

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
O = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
     'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"')


def make_zip(path, parts):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in parts.items():
            z.writestr(name, data)


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def text(self, name):
        return extract.read(self.root / name)["text"]

    def test_office_formats(self):
        make_zip(self.root / "a.docx", {"word/document.xml":
                 f'<w:document {W}><w:body><w:p><w:r><w:t>Hello</w:t></w:r><w:r><w:t xml:space="preserve"> Word</w:t></w:r></w:p>'
                 f'<w:p><w:r><w:t>Second line</w:t></w:r></w:p></w:body></w:document>'})
        self.assertEqual(self.text("a.docx"), "Hello Word\nSecond line")
        make_zip(self.root / "b.pptx", {"ppt/slides/slide2.xml": f'<p:sld xmlns:p="x" {A}><a:p><a:r><a:t>Two</a:t></a:r></a:p></p:sld>',
                                       "ppt/slides/slide1.xml": f'<p:sld xmlns:p="x" {A}><a:p><a:r><a:t>One</a:t></a:r></a:p></p:sld>'})
        self.assertEqual(self.text("b.pptx"), "Slide 1:\nOne\n\nSlide 2:\nTwo")
        make_zip(self.root / "c.xlsx", {
            "xl/sharedStrings.xml": f'<sst {S}><si><t>Item</t></si><si><t>Milk</t></si></sst>',
            "xl/worksheets/sheet1.xml": f'<worksheet {S}><sheetData><row><c t="s"><v>0</v></c><c><v>Price</v></c></row>'
                                        f'<row><c t="s"><v>1</v></c><c><v>1.25</v></c></row></sheetData></worksheet>'})
        self.assertIn("Milk\t1.25", self.text("c.xlsx"))
        make_zip(self.root / "d.odt", {"content.xml": f'<office:document-content {O}><office:body><office:text>'
                                                      f'<text:h>Title</text:h><text:p>Body text</text:p></office:text></office:body></office:document-content>'})
        self.assertEqual(self.text("d.odt"), "Title\nBody text")
        make_zip(self.root / "e.epub", {"OEBPS/ch1.xhtml": "<html><body><h1>Chapter</h1><p>Once upon a time</p></body></html>"})
        self.assertIn("Once upon a time", self.text("e.epub"))

    def test_text_like_formats(self):
        (self.root / "f.html").write_text("<html><style>x{}</style><body><p>Hi &amp; bye</p><script>evil()</script></body></html>", encoding="utf-8")
        self.assertEqual(self.text("f.html"), "Hi & bye")
        (self.root / "g.rtf").write_text(r"{\rtf1\ansi{\fonttbl\f0 Arial;}\f0 Caf\'e9 time\par Next}", encoding="cp1252")
        self.assertIn("Café time", self.text("g.rtf"))
        (self.root / "h.eml").write_bytes(b"From: a@b.c\r\nSubject: Lunch\r\nContent-Type: text/plain\r\n\r\nNoon at the cafe.\r\n")
        self.assertIn("Subject: Lunch", self.text("h.eml"))
        self.assertIn("Noon at the cafe.", self.text("h.eml"))
        (self.root / "i.py").write_text("print('hi')\n", encoding="utf-8")
        self.assertEqual(self.text("i.py"), "print('hi')\n")

    def test_bad_files_are_refused_clearly(self):
        (self.root / "broken.docx").write_bytes(b"not a zip")
        with self.assertRaises(ValueError):
            extract.read(self.root / "broken.docx")
        (self.root / "bin.txt").write_bytes(b"\x00\x01\x02binary")
        with self.assertRaises(ValueError):
            extract.read(self.root / "bin.txt")

    def test_attach_budget_images_and_vision(self):
        (self.root / "big.txt").write_text("x" * 40000, encoding="utf-8")
        (self.root / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        msgs = [{"role": "system", "content": "s"},
                {"role": "user", "content": "Read this\n\n[Attached file: big.txt]\n[Attached image: pic.png]"}]
        out, notes = extract.attach(msgs, self.root, vision=True)
        parts = out[-1]["content"]
        self.assertIsInstance(parts, list)
        self.assertTrue(parts[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertLess(len(parts[0]["text"]), extract.BUDGET + 1000)
        self.assertTrue(any("first" in n for n in notes))
        out, notes = extract.attach(msgs, self.root, vision=False)
        self.assertIsInstance(out[-1]["content"], str)
        self.assertTrue(any("cannot see pictures" in n for n in notes))

    def test_files_from_earlier_messages_stay_in_the_chat(self):
        (self.root / "notes.md").write_text("The launch code word is heron.", encoding="utf-8")
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "Look\n\n[Attached file: notes.md]"},
                {"role": "assistant", "content": "Done."}, {"role": "user", "content": "What is the code word?"}]
        out, _ = extract.attach(msgs, self.root, vision=False)
        self.assertIn("heron", out[-1]["content"])
        self.assertTrue(out[-1]["content"].startswith("What is the code word?"))


if __name__ == "__main__":
    unittest.main()
