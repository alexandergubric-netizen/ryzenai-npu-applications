"""Text editing against the kinds of fonts real PDFs carry: subset-embedded fonts Washi does not know
(Candara, Corbel, Constantia - like PDFs from Word or InDesign), system fonts (Calibri), the 14 standard fonts,
and characters the subset does not contain. Run: python tests\\fonts.py"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
os.environ["WASHI_HOME"] = tempfile.mkdtemp(prefix="washi-fonts-home-")

import fitz  # noqa: E402

from core import docs  # noqa: E402

W = docs.WINFONTS
passed, failed = 0, []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
    else:
        failed.append(name)
        print("FAIL", name, str(detail)[:300])


def make(fontfile, alias, text="Budget review meeting on Monday", subset=True):
    d = fitz.open()
    p = d.new_page()
    if fontfile:
        p.insert_font(fontname=alias, fontfile=os.path.join(W, fontfile))
        p.insert_text((72, 100), text, fontname=alias, fontsize=14)
    else:
        p.insert_text((72, 100), text, fontname=alias, fontsize=14)
    p.insert_text((72, 140), "Second line stays untouched", fontname="helv", fontsize=11)
    if subset:
        d.subset_fonts()
    return d.tobytes(garbage=3, deflate=True)


def text_of(doc, pno=0):
    return docs.Doc._norm_text(doc.page_text(pno))


def main():
    m = docs.manager
    cases = [("Candara.ttf", "Candara", True), ("corbel.ttf", "Corbel", True), ("constan.ttf", "Constantia", True),
             ("bahnschrift.ttf", "Bahnschrift", True), ("calibri.ttf", "Calibri", True), ("Candara.ttf", "Candara", False),
             (None, "helv", False), (None, "tiro", False), (None, "cour", False)]
    for fontfile, alias, subset in cases:
        if fontfile and not os.path.exists(os.path.join(W, fontfile)):
            print("skip", fontfile)
            continue
        label = f"{alias}{' subset' if subset else ''}"
        d = m.open_bytes(make(fontfile, alias, subset=subset), f"{alias}.pdf")
        line = d.line_at(0, [80, 96])
        check(f"{label}: line found", line and "Budget" in line["text"], line)
        # 1. only letters the subset already has -> may reuse the embedded font
        try:
            d.edit_line(0, {"point": [80, 96], "text": "Budget meeting on Monday"})
            check(f"{label}: edit with known letters", "Budget meeting on Monday" in text_of(d), text_of(d))
        except Exception as e:  # noqa: BLE001
            check(f"{label}: edit with known letters", False, repr(e))
        # 2. new letters (Slovak, digits, symbols) the subset lacks -> must fall back, not crash or garble
        new = "Rozpočet – stretnutie v pondelok 18. 10. 2026 (€ 1 250,50) ŽŠČŤ"
        try:
            d.edit_line(0, {"point": [80, 96], "text": new})
            check(f"{label}: edit with new letters", docs.Doc._norm_text(new) in text_of(d), text_of(d))
        except Exception as e:  # noqa: BLE001
            check(f"{label}: edit with new letters", False, repr(e))
        check(f"{label}: other line kept", "Second line stays untouched" in text_of(d))
        check(f"{label}: no nbsp", "\xa0" not in d.page_text(0))
        # 3. bold / family override from the style bar
        d.edit_line(0, {"point": [80, 96], "text": "Bold serif", "bold": True, "family": "serif"})
        check(f"{label}: style override", "Bold serif" in text_of(d))
        # 4. second edit on the same page with the same embedded font (font registered once)
        d.add_text(0, {"point": [72, 200], "text": "Typed note č", "size": 12})
        check(f"{label}: add text", "Typed note č" in text_of(d))
        # 5. save + reopen keeps everything readable
        out = d.save_bytes()
        re = fitz.open("pdf", out)
        t = docs.Doc._norm_text(re[0].get_text())
        check(f"{label}: saved text", "Bold serif" in t and "Typed note č" in t and "Second line" in t, t)
        check(f"{label}: saved no nbsp", "\xa0" not in re[0].get_text())
        m.close(d.id)

    # the original bug: reuse of an embedded font must go through insert_font, never insert_text(fontbuffer=)
    d = m.open_bytes(make("Candara.ttf", "Candara", subset=False), "c.pdf")
    kw = d._font_for(d.doc[0], "Candara", 0, "Budget")
    check("embedded font chosen for unknown family", "fontbuffer" in kw, kw.keys())
    d.edit_line(0, {"point": [80, 96], "text": "Budget"})
    fonts = [f[3] for f in d.doc[0].get_fonts()]
    check("embedded Candara reused", any("Candara" in f for f in fonts), fonts)

    # edit -> save (fonts get subset) -> edit again with letters the subset lacks: must not turn into ����
    d = m.open_bytes(make(None, "helv"), "again.pdf")
    d.add_text(0, {"point": [72, 300], "text": "abc", "size": 12})
    saved = d.save_bytes()
    d.add_text(0, {"point": [72, 330], "text": "Nové písmená xyzŽ", "size": 12})
    check("edit after save keeps letters", "Nové písmená xyzŽ" in text_of(d), text_of(d))
    d.optimize("strong")
    d.add_text(0, {"point": [72, 360], "text": "Po zmenšení QWERTY", "size": 12})
    check("edit after reduce-size keeps letters", "Po zmenšení QWERTY" in text_of(d), text_of(d))
    # a file saved by Washi (with its subset fonts) opened again and edited
    d2 = m.open_bytes(saved, "reopened.pdf")
    d2.add_text(0, {"point": [72, 400], "text": "Reopened ľščťž 12345", "size": 12})
    d2.edit_line(0, {"point": [74, 306], "text": "abc plus new words"})
    t = text_of(d2)
    check("edit reopened Washi file", "Reopened ľščťž 12345" in t and "abc plus new words" in t and "�" not in t, t)
    re2 = fitz.open("pdf", d2.save_bytes())
    t2 = docs.Doc._norm_text(re2[0].get_text())
    check("reopened file saved readable", "Reopened ľščťž 12345" in t2 and "�" not in t2, t2)

    # a PDF whose page has a broken font resource still edits (falls back to Arial)
    d = m.open_bytes(make(None, "helv"), "h.pdf")
    bad = {"fontname": "WBroken", "fontbuffer": b"not a font"}
    d._write(d.doc[0], fitz.Point(72, 300), "Fallback works", bad, fontsize=12)
    check("broken font falls back", "Fallback works" in text_of(d))

    print(f"\n{passed} passed, {len(failed)} failed")
    shutil.rmtree(os.environ["WASHI_HOME"], ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
