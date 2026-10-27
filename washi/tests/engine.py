"""Exercises core/docs.py on generated PDFs (no UI, no AI). Run: python tests\\engine.py  [--keep]"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="washi-test-")
os.environ["WASHI_HOME"] = os.path.join(TMP, "home")

import fitz  # noqa: E402

from core import docs  # noqa: E402

passed, failed = 0, []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
    else:
        failed.append(f"{name} {detail}")
        print("FAIL", name, detail)


def sample(path, rotated=False, form=False):
    d = fitz.open()
    for i in range(4):
        p = d.new_page(width=595, height=842)
        p.insert_text((72, 90), f"Chapter {i + 1}: Quarterly report", fontsize=20, fontname="hebo")
        p.insert_text((72, 130), "Revenue grew by 12 percent in the third quarter.", fontsize=11)
        p.insert_text((72, 150), "Costs were stable and the team hired two engineers.", fontsize=11)
        p.insert_font(fontname="ar", fontfile=os.path.join(docs.WINFONTS, "arial.ttf"))
        p.insert_text((72, 170), "Slovenčina: žltý kôň úpel ďábelské ódy.", fontsize=11, fontname="ar")
    if rotated:
        d[1].set_rotation(90)
    if form:
        w = fitz.Widget()
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.rect = fitz.Rect(72, 200, 300, 222)
        w.field_name = "name"
        w.field_value = ""
        d[0].add_widget(w)
        c = fitz.Widget()
        c.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        c.rect = fitz.Rect(72, 230, 86, 244)
        c.field_name = "agree"
        d[0].add_widget(c)
    d.set_toc([[1, "Chapter 1", 1], [1, "Chapter 2", 2], [2, "Details", 2]])
    d.save(path)


def main():
    src = os.path.join(TMP, "sample.pdf")
    sample(src, rotated=True, form=True)
    m = docs.manager
    d = m.open_path(src)
    info = d.info()
    check("open", len(info["pages"]) == 4)
    check("rotated page dims", info["pages"][1]["w"] == 842 and info["pages"][1]["rot"] == 90, str(info["pages"][1]))
    check("render", d.render(0, 1.0)[:4] == b"\x89PNG")
    check("render rotated", d.render(1, 0.5)[:4] == b"\x89PNG")

    tl = d.text_layer(0)
    check("text layer", any("Quarterly" in l["t"] for l in tl))
    tl1 = d.text_layer(1)
    r = next(l["r"] for l in tl1 if "Quarterly" in l["t"])
    check("rotated text box in display space", r[0] > 600 and r[3] - r[1] > r[2] - r[0], str(r))

    hits = d.search("revenue")
    check("search", len(hits) == 4, str(len(hits)))
    check("search whole word", len(d.search("Revenue", case=True, whole=True)) == 4)
    check("search rotated hit in display space", hits[1]["r"][0] > 600, str(hits[1]))

    # markup from a selection rectangle in display space
    a = d.add_annot(0, "highlight", {"rects": [hits[0]["r"]]}, author="Tester")
    check("highlight", a["kind"] == "Highlight" and a["author"] == "Tester")
    a1 = d.add_annot(1, "underline", {"rects": [hits[1]["r"]]})
    check("underline on rotated page", abs(a1["r"][0] - hits[1]["r"][0]) < 8, f"{a1['r']} vs {hits[1]['r']}")
    n = d.add_annot(0, "note", {"point": [400, 300], "content": "Check this"})
    check("note", n["content"] == "Check this")
    ft = d.add_annot(1, "freetext", {"rect": [100, 100, 300, 160], "text": "Box on rotated page", "size": 14})
    check("freetext rotated", abs(ft["r"][0] - 100) < 2 and abs(ft["r"][1] - 100) < 2, str(ft["r"]))
    sq = d.add_annot(0, "rect", {"rect": [100, 400, 200, 480], "color": "#27407a", "fill": "#ffeeaa", "width": 2})
    check("rect", sq["stroke"] == "#27407a")
    d.add_annot(0, "ellipse", {"rect": [220, 400, 320, 480]})
    ar = d.add_annot(0, "arrow", {"points": [[100, 500], [300, 560]], "width": 3})
    ink = d.add_annot(0, "ink", {"paths": [[[100, 600], [120, 620], [160, 610], [200, 650]]]})
    st = d.add_annot(0, "stamp", {"rect": [350, 600, 550, 660], "label": "Approved"})
    check("stamp", st["content"] == "Approved")
    check("annot list", len(d.annots()) >= 8, str(len(d.annots())))
    moved = d.update_annot(0, ink["id"], {"rect": [300, 700, 400, 750]})
    check("move ink", abs(moved["r"][0] - 300) < 4, str(moved["r"]))
    moved = d.update_annot(0, ar["id"], {"rect": [50, 50, 250, 110]})
    check("move arrow", abs(moved["r"][0] - 50) < 8, str(moved["r"]))
    up = d.update_annot(0, sq["id"], {"color": "#e2452f", "opacity": 0.5, "content": "Look"})
    check("update rect", up["stroke"] == "#e2452f" and up["opacity"] == 0.5 and up["content"] == "Look")
    up = d.update_annot(1, ft["id"], {"text": "Changed", "size": 18})
    check("update freetext", up["content"] == "Changed" and abs(up.get("size", 0) - 18) < 0.1, str(up))
    hit = d.annot_at(0, [150, 440])
    check("annot at point", hit and hit["kind"] in ("Rectangle", "Ellipse"), str(hit))
    d.delete_annot(0, n["id"])
    check("delete annot", all(x["id"] != n["id"] for x in d.annots(0)))

    # undo / redo
    count = len(d.annots())
    d.do_undo()
    check("undo", len(d.annots()) == count + 1)
    d.do_redo()
    check("redo", len(d.annots()) == count)

    # text editing
    line = d.line_at(0, [100, 125])
    check("line at", line and "Revenue" in line["text"], str(line))
    d.edit_line(0, {"point": [100, 125], "text": "Revenue grew by 15 percent — Slovenčina ťažká."})
    t0 = d.page_text(0)
    check("edit line", "15 percent" in t0 and "12 percent" not in t0 and "ťažká" in t0, t0[:300])
    check("edited text has normal spaces", "\xa0" not in t0)
    d.edit_line(1, {"point": hits[1]["r"][:2], "text": "Profit rose on a rotated page"})
    check("edit line rotated", "Profit rose" in d.page_text(1))
    d.add_text(2, {"point": [72, 300], "text": "Typed line one\nline two čšž", "size": 12})
    check("add text", "line two čšž" in d.page_text(2))
    d.whiteout(2, [60, 140, 500, 158])
    check("whiteout removes text", "Costs were stable" not in d.page_text(2))

    # image
    png = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 20), False)
    png.set_rect(png.irect, (226, 69, 47))
    d.add_image(1, [100, 300, 300, 400], data=png.tobytes("png"))
    imgs = d.doc[1].get_image_info()
    if imgs:
        bb = d.rect_out(d.doc[1], imgs[0]["bbox"])
        check("image on rotated page lands where asked", abs(bb[0] - 100) < 3 and abs(bb[1] - 300) < 52, str(bb))
    else:
        check("image inserted", False)

    # links
    d.add_link(3, [72, 70, 300, 95], uri="example.com")
    check("link", d.links(3)[0]["uri"] == "https://example.com")

    # forms
    ws = d.widgets(0)
    check("widgets", {w["name"] for w in ws} == {"name", "agree"}, str(ws))
    tx = next(w for w in ws if w["name"] == "name")
    d.set_field(0, tx["xref"], "Alexander")
    cb = next(w for w in ws if w["name"] == "agree")
    d.set_field(0, cb["xref"], True)
    ws = {w["name"]: w["value"] for w in d.widgets(0)}
    check("fill form", ws["name"] == "Alexander" and ws["agree"] not in ("Off", "", False), str(ws))
    d.add_field(3, "text", [72, 400, 300, 420], "new_field")
    check("add field", any(w["name"] == "new_field" for w in d.widgets(3)))

    # outline
    ol = d.outline()
    check("outline", len(ol) == 3 and ol[2]["lvl"] == 2)
    d.set_outline(ol + [{"lvl": 1, "title": "Appendix", "p": 3}])
    check("set outline", d.outline()[-1]["title"] == "Appendix")

    # pages
    d.rotate_pages([0], 90)
    check("rotate page", d.doc[0].rotation == 90)
    d.rotate_pages([0], -90)
    d.insert_blank(4)
    check("insert blank", d.doc.page_count == 5)
    d.duplicate_pages([0])
    check("duplicate", d.doc.page_count == 6 and "15 percent" in d.page_text(1))
    n0 = d.doc.page_count
    d.duplicate_pages([n0 - 1, 0])
    check("duplicate last + first", d.doc.page_count == n0 + 2)
    d.do_undo()
    d.move_pages([5], 0)
    check("move page to front", d.page_text(0).strip() == "", repr(d.page_text(0)[:40]))
    d.delete_pages([0])
    check("delete", d.doc.page_count == 5)
    other = os.path.join(TMP, "other.pdf")
    sample(other)
    added = d.insert_file(other, 5)
    check("insert file", added == 4 and d.doc.page_count == 9)
    data = d.extract_pages([0, 1])
    check("extract", fitz.open("pdf", data).page_count == 2)
    d.crop([0], [50, 50, 400, 300], 0)
    check("crop", round(d.doc[0].rect.width) == 350 and round(d.doc[0].rect.height) == 250, str(d.doc[0].rect))
    d.uncrop([0])
    check("uncrop", round(d.doc[0].rect.width) == 595)
    d.watermark({"text": "CONFIDENTIAL", "pages": "1-3"})
    check("watermark", "CONFIDENTIAL" in d.page_text(0))
    d.header_footer({"text": "Page {page} of {pages}", "position": "bottom-right"})
    check("page numbers", "Page 9 of 9" in d.page_text(8))
    check("parse ranges", docs.parse_ranges("1-3, 5, 8-", 9) == [0, 1, 2, 4, 7, 8])

    # redaction
    hits = d.search("engineers")
    for h in hits[:2]:
        d.add_annot(h["p"], "redact", {"rect": h["r"]})
    n = d.apply_redactions()
    check("redact", n >= 1 and "engineers" not in d.page_text(hits[0]["p"]))

    # attachments + metadata
    att = os.path.join(TMP, "notes.txt")
    with open(att, "w") as f:
        f.write("hello")
    d.add_attachment(att)
    check("attachment", d.attachments()[0]["name"] == "notes.txt" and d.get_attachment("notes.txt") == b"hello")
    d.set_meta({"title": "Test report", "author": "Washi"})
    check("metadata", d.meta()["title"] == "Test report")

    # save, security
    out = os.path.join(TMP, "saved.pdf")
    d.save(out)
    check("save", os.path.getsize(out) > 1000 and not d.dirty)
    d.add_annot(0, "note", {"point": [30, 30]})
    check("edit after save is unsaved", d.dirty)
    d.do_undo()
    check("undo back to the saved state is clean", not d.dirty)
    d.do_redo()
    check("redo is unsaved again", d.dirty)
    d.do_undo()
    d.protect({"remove": True})
    check("removing a password the file doesn't have changes nothing", not d.dirty)
    d2 = m.open_path(out)
    check("reopen", d2.doc.page_count == 9 and len(d2.annots()) >= 6)
    d2.protect({"user": "secret", "print": True, "copy": False})
    enc = os.path.join(TMP, "enc.pdf")
    d2.save(enc)
    try:
        m.docs.pop(d2.id)
        m.open_path(enc)
        check("password required", False)
    except docs.PasswordRequired:
        check("password required", True)
    d3 = m.open_path(enc, password="secret")
    check("open with password", d3.doc.page_count == 9)
    # protect -> save -> edit -> save again must stay protected (the in-memory copy follows the saved file)
    d4 = m.open_bytes(fitz.open(src).tobytes(), "keep.pdf")
    d4.protect({"user": "pw2"})
    keep = os.path.join(TMP, "keep.pdf")
    d4.save(keep)
    d4.add_annot(0, "note", {"point": [50, 50], "content": "after save"})
    d4.save(keep)
    with fitz.open(keep) as kd:
        check("protection kept on second save", kd.needs_pass)
        check("edits after protecting saved", kd.authenticate("pw2") and len(list(kd[0].annots())) >= 1)
    check("no temp file left", not os.path.exists(keep + ".washi-tmp"))
    d4.add_annot(0, "note", {"point": [60, 60]})
    d4.do_undo()
    check("undo after protected save", len(d4.annots(0)) >= 1)
    d4.save(keep)
    with fitz.open(keep) as kd:
        check("protection kept after undo", kd.needs_pass)
    # a file that arrived protected stays protected when edited and saved (permissions too)
    d5 = m.open_path(enc, password="secret")
    d5.add_annot(0, "note", {"point": [70, 70]})
    again = os.path.join(TMP, "again.pdf")
    d5.save(again)
    ad = fitz.open(again)
    check("opened-protected file stays protected", ad.needs_pass and ad.authenticate("secret"))
    check("permissions kept", int(ad.xref_get_key(-1, "Encrypt/P")[1]) == int(fitz.open(enc).xref_get_key(-1, "Encrypt/P")[1]))
    own = fitz.open()
    own.new_page().insert_text((50, 50), "owner only")
    ownb = own.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="boss", user_pw="", permissions=fitz.PDF_PERM_PRINT)
    d6 = m.open_bytes(ownb, "owner.pdf")
    d6.add_annot(0, "note", {"point": [70, 70]})
    ob = fitz.open("pdf", d6.save_bytes())
    check("owner-only restrictions kept", not ob.needs_pass and ob.metadata.get("encryption"))
    d6.protect({"remove": True})
    check("unlock removes restrictions", not fitz.open("pdf", d6.save_bytes()).metadata.get("encryption"))
    d3.protect({"remove": True})
    plain = os.path.join(TMP, "plain.pdf")
    d3.save(plain)
    check("remove password", not fitz.open(plain).needs_pass)
    before, after = d3.optimize("strong")
    check("optimize", after > 0, f"{before}->{after}")
    d3.flatten()
    check("flatten", len(d3.annots()) == 0)

    # export
    for kind in ("txt", "md", "html", "png"):
        files = d.export(kind, os.path.join(TMP, f"export.{kind}"), {"pages": "1-2", "dpi": 50})
        check(f"export {kind}", files and all(os.path.getsize(f) > 0 for f in files), str(files))
    try:
        files = d.export("docx", os.path.join(TMP, "export.docx"), {"pages": "1-2"})
        check("export docx", os.path.getsize(files[0]) > 1000)
    except ValueError as e:
        print("skip docx:", e)

    # e-books: shown as PDF, never written back, saved as a real PDF elsewhere
    sys.path.insert(0, os.path.join(HERE, "tests"))
    import make_ebooks
    book = make_ebooks.main(os.path.join(TMP, "books"))[0]
    raw = open(book, "rb").read()
    eb = m.open_path(book)
    check("e-book opens unchanged", not eb.dirty and eb.path is None and eb.source_format == "EPUB" and eb.doc.is_pdf)
    eb.add_annot(0, "note", {"point": [20, 20], "content": "on a book"})
    pdf_out = os.path.join(TMP, "book.pdf")
    eb.save(pdf_out)
    with fitz.open(pdf_out) as bp:
        check("e-book saved as PDF", bp.is_pdf and len(bp.get_toc()) == 5 and len(list(bp[0].annots())) == 1)
    check("original e-book untouched", open(book, "rb").read() == raw)
    check("after Save as it is a normal PDF", eb.path == pdf_out and not eb.dirty)
    dropped = m.open_bytes(raw, "dropped.epub")
    check("dropped e-book not 'unsaved'", not dropped.dirty and dropped.source_format == "EPUB")

    # new docs
    b = m.new_blank("a4", 2)
    check("blank", b.doc.page_count == 2)
    img = os.path.join(TMP, "pic.png")
    png.save(img)
    im = m.from_images([img, img])
    check("from images", im.doc.page_count == 2)
    mg = m.merge([src, other])
    check("merge", mg.doc.page_count == 8)
    check("thumbnail", docs.thumbnail_png(src)[:4] == b"\x89PNG")

    print(f"\n{passed} passed, {len(failed)} failed")
    if "--keep" in sys.argv:
        print("files in", TMP)
    else:
        shutil.rmtree(TMP, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
