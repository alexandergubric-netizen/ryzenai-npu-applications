"""Writes test e-books into a folder: an EPUB 3 (nav document, CSS, a cover image, internal links, a table,
Slovak text), an EPUB 2 (NCX table of contents) and an FB2 file.

    python tests\\make_ebooks.py [folder]      (default: tests\\ebooks)
"""
import base64
import os
import sys
import zipfile

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))

CHAPTERS = [
    ("Kapitola 1: Papier", "Washi je ručne vyrábaný japonský papier. Vyrába sa z vlákien kúry kozo, mitsumata a gampi. "
     "Je ľahký, pevný a vydrží stáročia."),
    ("Kapitola 2: Výroba", "Kôra sa varí, čistí a tĺče, kým sa vlákna neoddelia. Potom sa rozptýlia vo vode s nerivým "
     "slizom a papiernik ich naberá na sito su-keta."),
    ("Kapitola 3: Použitie", "Washi sa používa na posuvné dvere shoji, lampióny, kaligrafiu a reštaurovanie kníh v "
     "múzeách po celom svete."),
    ("Chapter 4: Numbers", "In 2026 the mill produced 412,000 sheets. Waste fell from 6.1 to 4.3 percent."),
    ("Chapter 5: Notes", "End of the test book. Return to the first chapter."),
]


def cover_png():
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 420), False)
    pix.clear_with(235)
    pix.set_rect(fitz.IRect(40, 60, 260, 120), (39, 64, 122))
    pix.set_rect(fitz.IRect(180, 300, 240, 360), (226, 69, 47))
    return pix.tobytes("png")


def body(i, title, text, filler=12):
    para = "".join(f"<p>{text} ({k + 1}.)</p>" for k in range(filler))
    extra = ""
    if i == 0:
        extra = '<p><img src="cover.png" alt="cover"/></p><p>Ďalej: <a href="ch4.xhtml#numbers">čísla v kapitole 4</a>.</p>'
    if i == 3:
        extra = ('<table id="numbers"><tr><th>Item</th><th>Q2</th><th>Q3</th></tr>'
                 '<tr><td>Sheets</td><td>378,000</td><td>412,000</td></tr><tr><td>Waste</td><td>6.1 %</td><td>4.3 %</td></tr></table>')
    if i == 4:
        extra = '<p><a href="ch1.xhtml">Back to chapter 1</a> · <a href="https://example.com/washi">example.com</a></p>'
    return (f'<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title>'
            f'<link rel="stylesheet" href="style.css"/></head><body><h1 id="top">{title}</h1>{extra}{para}</body></html>')


def epub3(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        items = "".join(f'<item id="ch{i + 1}" href="ch{i + 1}.xhtml" media-type="application/xhtml+xml"/>' for i in range(len(CHAPTERS)))
        spine = "".join(f'<itemref idref="ch{i + 1}"/>' for i in range(len(CHAPTERS)))
        z.writestr("OEBPS/content.opf", f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">'
                   f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">washi-test-3</dc:identifier>'
                   f'<dc:title>Kniha o papieri Washi</dc:title><dc:creator>Alexander Gubric</dc:creator><dc:language>sk</dc:language></metadata>'
                   f'<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
                   f'<item id="css" href="style.css" media-type="text/css"/><item id="cover" href="cover.png" media-type="image/png"/>{items}</manifest>'
                   f'<spine>{spine}</spine></package>')
        nav = "".join(f'<li><a href="ch{i + 1}.xhtml">{t}</a></li>' for i, (t, _) in enumerate(CHAPTERS))
        z.writestr("OEBPS/nav.xhtml", f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
                   f'<head><title>Obsah</title></head><body><nav epub:type="toc"><ol>{nav}</ol></nav></body></html>')
        z.writestr("OEBPS/style.css", "body{font-family:serif;line-height:1.4} h1{color:#27407a} table{border-collapse:collapse} td,th{border:1px solid #999;padding:3px}")
        z.writestr("OEBPS/cover.png", cover_png())
        for i, (t, text) in enumerate(CHAPTERS):
            z.writestr(f"OEBPS/ch{i + 1}.xhtml", body(i, t, text))


def epub2(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        items = "".join(f'<item id="ch{i + 1}" href="ch{i + 1}.xhtml" media-type="application/xhtml+xml"/>' for i in range(3))
        spine = "".join(f'<itemref idref="ch{i + 1}"/>' for i in range(3))
        z.writestr("content.opf", f'<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
                   f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">washi-test-2</dc:identifier><dc:title>Old style book</dc:title>'
                   f'<dc:creator>Test Author</dc:creator></metadata><manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
                   f'<item id="css" href="style.css" media-type="text/css"/><item id="cover" href="cover.png" media-type="image/png"/>{items}</manifest>'
                   f'<spine toc="ncx">{spine}</spine></package>')
        points = "".join(f'<navPoint id="p{i + 1}" playOrder="{i + 1}"><navLabel><text>{CHAPTERS[i][0]}</text></navLabel><content src="ch{i + 1}.xhtml"/></navPoint>' for i in range(3))
        z.writestr("toc.ncx", f'<?xml version="1.0" encoding="utf-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head/>'
                   f'<docTitle><text>Old style book</text></docTitle><navMap>{points}</navMap></ncx>')
        z.writestr("style.css", "body{font-family:sans-serif}")
        z.writestr("cover.png", cover_png())
        for i in range(3):
            z.writestr(f"ch{i + 1}.xhtml", body(i, *CHAPTERS[i], filler=30))


def fb2(path):
    secs = "".join(f"<section><title><p>{t}</p></title>" + "".join(f"<p>{x} {k}</p>" for k in range(10)) + "</section>"
                   for t, x in CHAPTERS)
    img = base64.b64encode(cover_png()).decode()
    xml = (f'<?xml version="1.0" encoding="utf-8"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" '
           f'xmlns:l="http://www.w3.org/1999/xlink"><description><title-info><book-title>FB2 test book</book-title>'
           f'<author><first-name>Test</first-name><last-name>Author</last-name></author></title-info></description>'
           f'<body><image l:href="#cover.png"/>{secs}</body><binary id="cover.png" content-type="image/png">{img}</binary></FictionBook>')
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)


def main(folder):
    os.makedirs(folder, exist_ok=True)
    out = [os.path.join(folder, n) for n in ("book3.epub", "book2.epub", "book.fb2")]
    epub3(out[0])
    epub2(out[1])
    fb2(out[2])
    return out


if __name__ == "__main__":
    for p in main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "ebooks")):
        print(p)
