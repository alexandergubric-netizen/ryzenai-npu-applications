"""Runs every engine operation on many PDFs and reports any exception (no document content is printed).

    python tests\\stress.py                 # synthetic edge cases only
    python tests\\stress.py file.pdf ...    # plus your own files (opened read-only, outputs go to a temp folder)
    python tests\\stress.py --list x.csv    # plus every path in a CSV/text file
"""
import csv
import io
import os
import shutil
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="washi-stress-")
os.environ["WASHI_HOME"] = os.path.join(TMP, "home")

import fitz  # noqa: E402

from core import assistant, docs  # noqa: E402

problems = []
slow = []
SLOW = 1.0   # seconds; anything slower is listed so it can be looked at
stats = {"docs": 0, "ops": 0}


def synthetic():
    out = {}
    # 1. crop box offset from the media box, on every rotation
    d = fitz.open()
    for rot in (0, 90, 180, 270):
        p = d.new_page(width=612, height=792)
        p.insert_text((150, 200), f"Offset crop box rotation {rot}", fontsize=14)
        p.insert_text((150, 230), "Second line for editing tests", fontsize=11)
        p.set_cropbox(fitz.Rect(100, 100, 560, 700))
        p.set_rotation(rot)
    out["cropbox+rotation"] = d.tobytes()
    # 2. media box not starting at 0,0
    d = fitz.open()
    p = d.new_page(width=600, height=800)
    p.insert_text((100, 120), "Shifted media box", fontsize=14)
    d.xref_set_key(p.xref, "MediaBox", "[50 50 650 850]")
    out["shifted mediabox"] = d.tobytes()
    # 3. scanned page: an image, no text
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 600, 800), False)
    pix.clear_with(235)
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_image(p.rect, pixmap=pix)
    out["scan (image only)"] = d.tobytes()
    # 4. empty page document
    d = fitz.open()
    d.new_page()
    out["blank"] = d.tobytes()
    # 5. owner-password only (opens without a password, restricted)
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 72), "Owner protected document", fontsize=12)
    out["owner password only"] = d.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="",
                                             permissions=fitz.PDF_PERM_PRINT)
    # 6. long document with outline and forms
    d = fitz.open()
    for i in range(240):
        p = d.new_page(width=595, height=842)
        p.insert_text((72, 72), f"Chapter {i // 10 + 1} page {i + 1} lorem ipsum dolor sit amet", fontsize=11)
    d.set_toc([[1, f"Chapter {k + 1}", k * 10 + 1] for k in range(24)])
    for kind, rect in ((fitz.PDF_WIDGET_TYPE_TEXT, (72, 100, 300, 120)), (fitz.PDF_WIDGET_TYPE_CHECKBOX, (72, 130, 86, 144)),
                       (fitz.PDF_WIDGET_TYPE_COMBOBOX, (72, 150, 200, 170)), (fitz.PDF_WIDGET_TYPE_LISTBOX, (72, 180, 200, 230))):
        w = fitz.Widget()
        w.field_type = kind
        w.rect = fitz.Rect(rect)
        w.field_name = f"f{kind}"
        if kind in (fitz.PDF_WIDGET_TYPE_COMBOBOX, fitz.PDF_WIDGET_TYPE_LISTBOX):
            w.choice_values = ["One", "Two", "Three"]
            w.field_value = "One"
        d[0].add_widget(w)
    out["240 pages + forms"] = d.tobytes()
    # 7. vertical / rotated text and right-to-left mixed content
    d = fitz.open()
    p = d.new_page()
    p.insert_text((100, 400), "Vertical text up", fontsize=12, rotate=90)
    p.insert_text((300, 200), "Upside down", fontsize=12, rotate=180)
    p.insert_font(fontname="ar", fontfile=os.path.join(docs.WINFONTS, "arial.ttf"))
    p.insert_text((72, 600), "Ελληνικά Русский Čeština", fontsize=12, fontname="ar")
    out["rotated text + scripts"] = d.tobytes()
    # 8. existing annotations of many kinds, links and an attachment
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 72), "Annotated document with links", fontsize=12)
    p.add_highlight_annot(fitz.Rect(72, 60, 300, 76))
    p.add_text_annot((400, 100), "Old note")
    p.add_freetext_annot(fitz.Rect(72, 200, 300, 260), "Old free text")
    p.add_ink_annot([[(100, 300), (150, 350), (200, 300)]])
    p.add_polygon_annot([(300, 300), (400, 300), (350, 380)])
    p.add_polyline_annot([(300, 400), (400, 420), (450, 380)])
    p.add_caret_annot((200, 500))
    p.add_file_annot((500, 500), b"attached", "a.txt")
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(72, 60, 300, 76), "uri": "https://example.com"})
    p.insert_link({"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 80, 300, 96), "page": 0})
    d.embfile_add("data.csv", b"a,b\n1,2", filename="data.csv")
    out["annotations + links"] = d.tobytes()
    # 9. damaged file (truncated)
    good = out["annotations + links"]
    out["truncated (damaged)"] = good[: int(len(good) * 0.8)]
    # 10. e-books (shown as PDFs) and an XPS-like non-PDF: an image
    sys.path.insert(0, os.path.join(HERE, "tests"))
    import make_ebooks
    for p in make_ebooks.main(os.path.join(TMP, "books")):
        with open(p, "rb") as f:
            out["ebook " + os.path.basename(p)] = f.read()
    out["image.png"] = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300), False).tobytes("png")
    return out


def run(label, data, name):
    stats["docs"] += 1
    m = docs.manager

    def op(what, fn):
        stats["ops"] += 1
        if os.environ.get("WASHI_STRESS_TRACE"):
            print(f"[{label}] {what}", file=sys.stderr, flush=True)
        t = time.time()
        try:
            return fn()
        except (ValueError, docs.PasswordRequired) as e:   # expected, user-facing messages
            return e
        except Exception as e:  # noqa: BLE001
            problems.append(f"[{label}] {what}: {type(e).__name__}: {e}\n" + traceback.format_exc(limit=4))
            return None
        finally:
            dt = time.time() - t
            if dt > SLOW:
                slow.append(f"{dt:5.1f}s [{label}] {what}")

    try:
        d = m.open_bytes(data, name)
    except docs.PasswordRequired:
        return
    except Exception as e:  # noqa: BLE001
        if "damaged" in label or "broken" in str(e).lower() or "cannot open" in str(e).lower():
            return   # refusing a broken file with an error message is fine
        problems.append(f"[{label}] open: {type(e).__name__}: {e}")
        return
    n = d.doc.page_count
    sample = list(range(min(n, 6))) + ([n - 1] if n > 6 else [])
    op("info", d.info)
    for p in sample:
        op(f"render p{p}", lambda p=p: d.render(p, 0.6))
        op(f"thumb p{p}", lambda p=p: d.render(p, 0.2, "jpg"))
        tl = op(f"text layer p{p}", lambda p=p: d.text_layer(p))
        op(f"links p{p}", lambda p=p: d.links(p))
        op(f"widgets p{p}", lambda p=p: d.widgets(p))
        op(f"annots p{p}", lambda p=p: d.annots(p))
        if tl:
            r = tl[0]["r"]
            pt = [(r[0] + r[2]) / 2, (r[1] + r[3]) / 2]
            line = op(f"line_at p{p}", lambda: d.line_at(p, pt))
            if line:
                op(f"edit line p{p}", lambda: d.edit_line(p, {"point": pt, "text": line["text"].strip()[:60] + " ✓ č"}))
            op(f"selection text p{p}", lambda: d.selection_text(p, [r]))
            op(f"highlight p{p}", lambda: d.add_annot(p, "highlight", {"rects": [r]}))
        pg = d.doc[p].rect
        a = op(f"rect annot p{p}", lambda: d.add_annot(p, "rect", {"rect": [10, 10, 60, 50], "color": "#e2452f"}))
        if isinstance(a, dict):
            op(f"move annot p{p}", lambda: d.update_annot(p, a["id"], {"rect": [20, 20, 90, 70], "opacity": 0.5}))
            op(f"annot at p{p}", lambda: d.annot_at(p, [30, 30]))
        op(f"note p{p}", lambda: d.add_annot(p, "note", {"point": [pg.width - 40, 20], "content": "n"}))
        op(f"freetext p{p}", lambda: d.add_annot(p, "freetext", {"rect": [20, 80, 200, 120], "text": "Box č"}))
        op(f"stamp p{p}", lambda: d.add_annot(p, "stamp", {"rect": [20, 130, 200, 180], "label": "Approved"}))
        op(f"ink p{p}", lambda: d.add_annot(p, "ink", {"paths": [[[30, 200], [60, 230], [90, 200]]]}))
        op(f"arrow p{p}", lambda: d.add_annot(p, "arrow", {"points": [[30, 250], [120, 280]]}))
        op(f"add text p{p}", lambda: d.add_text(p, {"point": [30, 300], "text": "Typed čšž"}))
        op(f"whiteout p{p}", lambda: d.whiteout(p, [pg.width - 60, pg.height - 60, pg.width - 10, pg.height - 10]))
        png = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 20, 10), False).tobytes("png")
        op(f"image p{p}", lambda: d.add_image(p, [30, 330, 90, 360], data=png))
        op(f"signature p{p}", lambda: d.add_signature(p, [100, 330, 160, 360], png))
        op(f"link p{p}", lambda: d.add_link(p, [30, 370, 90, 390], uri="example.com"))
        op(f"redact mark p{p}", lambda: d.add_annot(p, "redact", {"rect": [30, 400, 90, 420]}))
    for w in (op("widgets 0", lambda: d.widgets(0)) or []):
        if not isinstance(w, dict):
            continue
        val = True if w["type"] in ("CheckBox", "RadioButton") else ((w["options"] or ["x"])[-1] if w["options"] else "Filled")
        if isinstance(val, list):
            val = val[0]
        op(f"set field {w['type']}", lambda w=w, val=val: d.set_field(0, w["xref"], val))
    op("search", lambda: d.search("the"))
    op("search case/whole", lambda: d.search("The", case=True, whole=True))
    ol = op("outline", d.outline)
    if isinstance(ol, list):
        op("set outline", lambda: d.set_outline(ol + [{"lvl": 1, "title": "Added", "p": 0}]))
    op("all text", d.all_text)
    op("apply redactions", d.apply_redactions)
    op("rotate", lambda: d.rotate_pages([0], 90))
    op("duplicate", lambda: d.duplicate_pages([0]))
    op("move", lambda: d.move_pages([0], d.doc.page_count))
    op("blank", lambda: d.insert_blank(1))
    op("extract", lambda: d.extract_pages([0]))
    op("crop", lambda: d.crop([0], [5, 5, 200, 200], 0))
    op("uncrop", lambda: d.uncrop([0]))
    op("watermark", lambda: d.watermark({"text": "DRAFT", "pages": "1-2"}))
    op("numbers", lambda: d.header_footer({"text": "{page}/{pages}", "pages": "all"}))
    op("meta", lambda: d.set_meta({"title": "Stress"}))
    op("attachments", d.attachments)
    for k in range(4):
        op(f"undo {k}", d.do_undo)
    for k in range(2):
        op(f"redo {k}", d.do_redo)
    for kind in ("txt", "md", "html", "png", "docx"):
        op(f"export {kind}", lambda kind=kind: d.export(kind, os.path.join(TMP, f"{stats['docs']}.{kind}"), {"pages": "1-2", "dpi": 40}))
    data2 = op("save bytes", d.save_bytes)
    if isinstance(data2, bytes):
        op("reopen saved", lambda: fitz.open("pdf", data2).page_count)
    op("summary chunks", lambda: assistant.retrieve(d.all_text(), "what is this about"))
    op("optimize", lambda: d.optimize("strong"))
    op("flatten", d.flatten)
    op("protect+save", lambda: (d.protect({"user": "x"}), d.save(os.path.join(TMP, f"{stats['docs']}-enc.pdf"))))
    op("thumbnail fn", lambda: docs.thumbnail_png(os.path.join(TMP, f"{stats['docs']}-enc.pdf")))
    m.close(d.id)


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith("--") and a.lower().endswith(".pdf")]
    if "--list" in sys.argv:
        lst = sys.argv[sys.argv.index("--list") + 1]
        with open(lst, encoding="utf-8-sig") as f:
            for row in csv.reader(f):
                if row and row[-1].lower().endswith(".pdf") and os.path.exists(row[-1]):
                    paths.append(row[-1])
    t0 = time.time()
    for label, data in synthetic().items():
        name = label.split()[-1] if "." in label.split()[-1] else f"{label}.pdf"   # e-books keep their extension
        run(label, data, name)
    for i, p in enumerate(paths):
        with open(p, "rb") as f:
            data = f.read()
        run(f"file {i + 1} ({os.path.getsize(p) // 1024} KB)", data, f"file{i + 1}.pdf")
    print(f"{stats['docs']} documents, {stats['ops']} operations, {len(problems)} problems, {time.time() - t0:.0f}s")
    if slow:
        print(f"slow operations (> {SLOW}s):")
        for s in sorted(slow, reverse=True)[:40]:
            print("  " + s)
    for pr in problems:
        print("-" * 60)
        print(pr)
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
