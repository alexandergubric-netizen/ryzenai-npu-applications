"""Open documents and everything Washi does to them, on top of PyMuPDF.

Coordinates: the UI always works in *display* points (the page as it appears, rotation applied, origin top-left).
PyMuPDF's text and annotation APIs use the unrotated page, so every rect/point crosses `_to_ui` / `_from_ui`.
Documents are loaded from bytes (no file locks); every change first takes a byte snapshot (undo/redo).
"""
import base64
import hashlib
import html
import os
import secrets
import re
import threading
import time
import uuid
from collections import OrderedDict

import fitz

fitz.TOOLS.set_small_glyph_heights(True)
fitz.TOOLS.mupdf_display_errors(False)

WINFONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
# family keyword -> (regular, bold, italic, bold italic) font files in C:\Windows\Fonts
SYSTEM_FONTS = {
    "arial": ("arial", "arialbd", "ariali", "arialbi"), "helvetica": ("arial", "arialbd", "ariali", "arialbi"),
    "times": ("times", "timesbd", "timesi", "timesbi"), "calibri": ("calibri", "calibrib", "calibrii", "calibriz"),
    "cambria": ("cambria", "cambriab", "cambriai", "cambriaz"), "verdana": ("verdana", "verdanab", "verdanai", "verdanaz"),
    "georgia": ("georgia", "georgiab", "georgiai", "georgiaz"), "tahoma": ("tahoma", "tahomabd", "tahoma", "tahomabd"),
    "segoe": ("segoeui", "segoeuib", "segoeuii", "segoeuiz"), "courier": ("cour", "courbd", "couri", "courbi"),
    "consolas": ("consola", "consolab", "consolai", "consolaz"), "trebuchet": ("trebuc", "trebucbd", "trebucit", "trebucbi"),
    "garamond": ("GARA", "GARABD", "GARAIT", "GARABD"), "century": ("GOTHIC", "GOTHICB", "GOTHICI", "GOTHICBI"),
    "aptos": ("aptos", "aptos-bold", "aptos-italic", "aptos-bold-italic"),
}
UI_FONTS = {"sans": "arial", "serif": "times", "mono": "courier"}   # Washi's style picker -> SYSTEM_FONTS key
STAMPS = {"Approved": ("APPROVED", "#2f8f4e"), "Draft": ("DRAFT", "#27407a"), "Confidential": ("CONFIDENTIAL", "#c0392b"),
          "Final": ("FINAL", "#2f8f4e"), "Not approved": ("NOT APPROVED", "#c0392b"), "For comment": ("FOR COMMENT", "#b7791f"),
          "Reviewed": ("REVIEWED", "#27407a"), "Void": ("VOID", "#c0392b"), "Sign here": ("SIGN HERE", "#e2452f")}
ANNOT_NAMES = {
    fitz.PDF_ANNOT_TEXT: "Note", fitz.PDF_ANNOT_FREE_TEXT: "Text box", fitz.PDF_ANNOT_HIGHLIGHT: "Highlight",
    fitz.PDF_ANNOT_UNDERLINE: "Underline", fitz.PDF_ANNOT_STRIKE_OUT: "Strikeout", fitz.PDF_ANNOT_SQUIGGLY: "Squiggly",
    fitz.PDF_ANNOT_SQUARE: "Rectangle", fitz.PDF_ANNOT_CIRCLE: "Ellipse", fitz.PDF_ANNOT_LINE: "Line",
    fitz.PDF_ANNOT_INK: "Drawing", fitz.PDF_ANNOT_STAMP: "Stamp", fitz.PDF_ANNOT_POLYGON: "Polygon",
    fitz.PDF_ANNOT_POLY_LINE: "Polyline", fitz.PDF_ANNOT_REDACT: "Redaction mark", fitz.PDF_ANNOT_FILE_ATTACHMENT: "Attachment",
    fitz.PDF_ANNOT_CARET: "Caret", fitz.PDF_ANNOT_LINK: "Link",
}
EBOOK_PAGE = (432, 648)   # 6 x 9 inch, a common book size
EBOOK_FONTSIZE = 11
EBOOK_TYPES = ("epub", "mobi", "fb2", "cbz", "xps", "oxps")
MAX_UNDO = 60
MAX_UNDO_BYTES = 600 * 2 ** 20
BACKUPS = 20                    # previous versions kept in %LOCALAPPDATA%\Washi\backups
BACKUP_MAX_BYTES = 300 * 2 ** 20


def free_name(path):
    """`path`, or "name (2).ext", "name (3).ext"… when that file already exists - exports never overwrite."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem} ({n}){ext}"):
        n += 1
    return f"{stem} ({n}){ext}"


def backup(path):
    """Before a save replaces a file, keep its previous version in Washi's data folder (newest BACKUPS, last 30 days)."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > BACKUP_MAX_BYTES:
            return None
        from . import config
        folder = os.path.join(config.DATA_DIR, "backups")
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, time.strftime("%Y-%m-%d %H%M%S ") + os.path.basename(path))
        with open(path, "rb") as fin, open(dst, "wb") as fout:
            fout.write(fin.read())
        olds = sorted((os.path.join(folder, f) for f in os.listdir(folder)), key=os.path.getmtime, reverse=True)
        for i, f in enumerate(olds):
            if i >= BACKUPS or os.path.getmtime(f) < time.time() - 30 * 86400:
                os.remove(f)
        return dst
    except OSError:
        return None   # a backup is a safety net; it never blocks saving


def _ebook_fontsize():
    try:
        from . import config
        return max(6.0, min(float(config.get().get("ebook_fontsize") or EBOOK_FONTSIZE), 30.0))
    except Exception:  # noqa: BLE001
        return float(EBOOK_FONTSIZE)


class PasswordRequired(Exception):
    """The PDF needs a (different) password to open. Not an OSError, so file-permission problems stay apart."""


def rgb(hexcolor, default=(0, 0, 0)):
    if not hexcolor:
        return default
    if isinstance(hexcolor, (list, tuple)):
        return tuple(float(c) for c in hexcolor[:3])
    h = str(hexcolor).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return default


def hexc(color):
    if not color:
        return None
    if isinstance(color, int):
        return "#%06x" % color
    c = list(color)[:3]
    if len(c) == 1:
        c = c * 3
    return "#" + "".join("%02x" % max(0, min(255, round(v * 255))) for v in c)


def _r(rect):
    return [round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)]


def _label_number(n, style):
    """A page-label number in a PDF numbering style: D 1 2 3, r i ii iii, R I II III, a a..z aa, A A..Z AA."""
    if style == "D":
        return str(n)
    if style in ("r", "R"):
        vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
                (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
        out, k = "", max(n, 1)
        for v, s in vals:
            while k >= v:
                out += s
                k -= v
        return out.upper() if style == "R" else out
    if style in ("a", "A"):
        k = max(n, 1) - 1
        s = chr(ord("a") + k % 26) * (k // 26 + 1)
        return s.upper() if style == "A" else s
    return ""   # no style: the prefix alone


def parse_ranges(text, count):
    """'1-3, 5, 8-' -> zero-based page numbers (1-based input, in order, no duplicates)."""
    out = []
    for part in re.split(r"[,;\s]+", (text or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            a = int(m.group(1) or 1)
            b = int(m.group(2) or count)
            rng = range(a, b + 1) if a <= b else range(a, b - 1, -1)
        elif part.isdigit():
            rng = [int(part)]
        else:
            raise ValueError(f"'{part}' is not a page range")
        for n in rng:
            if 1 <= n <= count and n - 1 not in out:
                out.append(n - 1)
    if not out:
        raise ValueError("no pages in that range")
    return out


class Doc:
    def __init__(self, data, path=None, name=None, password=None, filetype=None):
        self.id = uuid.uuid4().hex[:12]
        self.path = path
        self.name = name or (os.path.basename(path) if path else "Untitled.pdf")
        self.password = password
        self.lock = threading.RLock()
        self.undo, self.redo = [], []
        self.dirty = False
        self.saved_mark = 0                     # undo depth that matches the file on disk (-1: none)
        self.security = None          # pending {"user","owner","permissions"} or {"remove": True}, applied on save
        self.converted = False
        self.source = None            # (bytes, filetype) of an e-book, kept so its text size can change
        self.source_format = None     # "EPUB", "MOBI", "XPS", "Image"… when the file isn't a PDF
        self.source_path = path       # the file that was opened (an e-book stays the source, saves go elsewhere)
        self.ebook_fontsize = None
        self.cache = OrderedDict()
        self._load(data, filetype)
        self.keep = self._protection(self._needed_password)   # protection re-applied on every save
        if not self.doc.is_pdf:       # XPS, EPUB, MOBI, FB2, comics, images…: shown as a PDF copy
            fmt = (self.doc.metadata or {}).get("format") or (filetype or "document").upper()
            low = fmt.lower()
            self.source_format = "Image" if low.startswith(("png", "jpeg", "jpg", "gif", "bmp", "tif", "webp", "image", "pnm", "jpx")) \
                else "FB2" if "fiction" in low or low.startswith("fb2") else fmt.split()[0].upper()
            if self.doc.is_reflowable:
                self.source = (data, filetype)
            self._convert(_ebook_fontsize())
            self.converted = True
            self.path = None          # Save asks where the PDF should go; the e-book is never overwritten
        self.pv = [0] * self.doc.page_count     # per-page revision, for render caching in the UI
        self._labels = None                     # page labels, rebuilt after page-structure changes
        self._fonts_added = False               # True after text editing embedded a font (subset on save)
        self._font_tag = secrets.token_hex(3)   # makes Washi's font resource names unique, see _fname
        self._text = None                       # (pv, [page text]) for the AI

    def _convert(self, fontsize):
        """Turn the opened non-PDF document into a PDF copy. E-books are first laid out on book-sized pages at
        `fontsize`; their table of contents becomes bookmarks and their links keep working."""
        src = self.doc
        meta = dict(src.metadata or {})
        if src.is_reflowable:
            src.layout(width=EBOOK_PAGE[0], height=EBOOK_PAGE[1], fontsize=fontsize)
            self.ebook_fontsize = fontsize
        try:
            toc = src.get_toc(simple=True)
        except Exception:  # noqa: BLE001
            toc = []
        pdf = fitz.open("pdf", src.convert_to_pdf())
        n = pdf.page_count
        for i in range(min(n, src.page_count)):
            try:
                links = src[i].get_links()
            except Exception:  # noqa: BLE001
                continue
            for link in links:
                try:
                    kind, target = link.get("kind"), None
                    if kind == fitz.LINK_URI and re.match(r"^(https?:|mailto:)", link.get("uri") or "", re.I):
                        pdf[i].insert_link({"kind": fitz.LINK_URI, "from": link["from"], "uri": link["uri"]})
                        continue
                    if kind == fitz.LINK_GOTO and link.get("page", -1) >= 0:
                        target = link["page"]
                    elif link.get("uri") or link.get("nameddest"):   # "chapter2.xhtml#sec" inside the book
                        loc = src.resolve_link(link.get("uri") or link.get("nameddest"))
                        if loc and loc[0] is not None:
                            target = src.page_number_from_location(loc[0])
                    if target is not None and 0 <= target < n:
                        pdf[i].insert_link({"kind": fitz.LINK_GOTO, "from": link["from"], "page": target,
                                            "to": fitz.Point(0, 0)})
                except Exception:  # noqa: BLE001 - a link MuPDF can't follow is simply left out
                    continue
        clean, last = [], 0
        for lvl, title, page in toc:
            if not (1 <= page <= n) or not str(title).strip():
                continue
            lvl = max(1, min(int(lvl), last + 1))
            clean.append([lvl, str(title).strip(), page])
            last = lvl
        try:
            if clean:
                pdf.set_toc(clean)
        except Exception:  # noqa: BLE001
            pass
        try:
            pdf.set_metadata({k: meta.get(k) or "" for k in ("title", "author", "subject", "keywords")} |
                             {"creator": meta.get("creator") or "", "producer": "Washi"})
        except Exception:  # noqa: BLE001
            pass
        src.close()
        self.doc = pdf

    def reflow(self, fontsize):
        """Lay an e-book out again at another text size (only before it has been edited)."""
        with self.lock:
            if not self.source:
                raise ValueError("only e-books (EPUB, MOBI, FB2…) can change their text size")
            if self.undo:
                raise ValueError("this e-book has changes. Save them as a PDF first, or close it and open the book "
                                 "again to change the text size")
            fontsize = max(6.0, min(float(fontsize), 30.0))
            data, ftype = self.source
            self.doc.close()
            self._load(data, ftype)
            self._convert(fontsize)
            self.cache.clear()
            self._labels = None
            self._text = None
            self.pv = [max(self.pv or [0]) + 1] * self.doc.page_count

    def _protection(self, needed_password):
        """How the file was protected when it was opened. MuPDF only keeps encryption on incremental saves and
        Washi writes whole files, so save_bytes() re-applies this every time."""
        enc = (self.doc.metadata or {}).get("encryption")
        if not enc:
            return None
        try:
            perms = int(self.doc.xref_get_key(-1, "Encrypt/P")[1])
        except (ValueError, TypeError, RuntimeError):
            perms = -1
        pw = self.password or ""
        auth = self._auth   # what the typed password unlocked: 2 = user (open) password, 4 = owner password, 6 = both
        if needed_password and not auth & 2:
            # opened with the owner password only: the open password is unknown, so a save would change who can
            # open the file. save_bytes() refuses until new passwords are set under Security.
            return {"user": None, "owner": pw, "permissions": perms}
        # the owner password is only kept when it was typed (as the owner password); otherwise one nobody knows
        # keeps the restrictions, so knowing the open password never lifts them
        return {"user": pw if needed_password else "", "owner": pw if (pw and auth & 4) else secrets.token_urlsafe(18),
                "permissions": perms}

    def _load(self, data, filetype=None):
        self.doc = fitz.open(filetype or "pdf", data) if filetype or data[:5] == b"%PDF-" else fitz.open(stream=data)
        self._needed_password = self.doc.needs_pass
        self._auth = 0
        if self.doc.needs_pass:
            self._auth = self.doc.authenticate(self.password) if self.password else 0
            if not self._auth:
                raise PasswordRequired("This document is protected by a password")
        elif self.password and (self.doc.metadata or {}).get("encryption"):
            self._auth = self.doc.authenticate(self.password)   # an owner password typed for a restricted file

    # ------------------------------------------------------------------ undo
    def _dirty(self):
        """Unsaved = not at the undo depth of the last save, or a password change waits for the next save."""
        self.dirty = self.saved_mark != len(self.undo) or bool(self.security)

    def snap(self):
        data = self.doc.tobytes(garbage=0)
        if len(self.undo) < self.saved_mark:   # a new edit after undoing past the save: that state is gone
            self.saved_mark = -1
        self.undo.append((data, list(self.pv)))
        self._before_edit = self.undo[-1]   # rollback() needs it even after the undo limit dropped old steps
        self.redo.clear()
        while len(self.undo) > MAX_UNDO or (len(self.undo) > 1 and sum(len(u[0]) for u in self.undo) > MAX_UNDO_BYTES):
            self.undo.pop(0)
            self.saved_mark = self.saved_mark - 1 if self.saved_mark > 0 else -1

    def rollback(self, depth):
        """An edit failed half-way: go back to the snapshot it took. That is the newest snapshot - also once the undo
        limit (MAX_UNDO) keeps the stack at the same length, so `depth` alone can't tell."""
        with self.lock:
            snap = getattr(self, "_before_edit", None)
            if snap is None or not self.undo or self.undo[-1] is not snap:
                return   # the failed request took no snapshot: nothing was changed
            data, _pv = snap
            self.undo.pop()
            self._before_edit = None
            try:
                self.doc.close()
            except Exception:  # noqa: BLE001
                pass
            self._load(data)
            self.changed(None)

    def changed(self, pages=None):
        """Mark pages (zero-based) as changed; None = page structure changed (everything)."""
        self._dirty()
        self._text = None
        if pages is None or len(self.pv) != self.doc.page_count:
            gen = max(self.pv or [0]) + 1
            self.pv = [gen] * self.doc.page_count
            self.cache.clear()
        else:
            for p in pages:
                self.pv[p] += 1
            for key in [k for k in self.cache if k[0] in pages]:
                del self.cache[key]

    def _swap(self, src, dst):
        if not src:
            raise ValueError("nothing to undo" if src is self.undo else "nothing to redo")
        data, pv = src.pop()
        dst.append((self.doc.tobytes(garbage=0), list(self.pv)))
        self.doc.close()
        self._load(data)
        gen = max(max(pv or [0]), max(self.pv or [0])) + 1
        self.pv = [gen] * self.doc.page_count
        self.cache.clear()
        self._labels = None
        self._text = None
        self._dirty()

    def do_undo(self):
        with self.lock:
            self._swap(self.undo, self.redo)

    def do_redo(self):
        with self.lock:
            self._swap(self.redo, self.undo)

    # ------------------------------------------------------------------ geometry
    def page(self, pno):
        if not 0 <= pno < self.doc.page_count:
            raise ValueError("no such page")
        return self.doc[pno]

    @staticmethod
    def _to_ui(page, obj):
        return obj * page.rotation_matrix if page.rotation else obj

    @staticmethod
    def _from_ui(page, obj):
        return obj * page.derotation_matrix if page.rotation else obj

    def rect_in(self, page, r):
        rect = fitz.Rect(r)
        rect.normalize()
        return self._from_ui(page, rect).normalize()

    def rect_out(self, page, rect):
        return _r(fitz.Rect(self._to_ui(page, fitz.Rect(rect))).normalize())

    def pt_in(self, page, p):
        return self._from_ui(page, fitz.Point(p[0], p[1]))

    def pt_out(self, page, p):
        q = self._to_ui(page, fitz.Point(p))
        return [round(q.x, 2), round(q.y, 2)]

    # ------------------------------------------------------------------ info
    def labels(self):
        """Page labels ("i", "ii", "1"…); computed once per page structure (get_label is slow on big files)."""
        if self._labels is None or len(self._labels) != self.doc.page_count:
            try:
                rules = self.doc.get_page_labels()
            except Exception:  # noqa: BLE001
                rules = []
            n = self.doc.page_count
            labels = [str(i + 1) for i in range(n)]
            try:   # from the label rules directly: page.get_label() costs ~1.5 ms per page
                rules = sorted(rules, key=lambda r: r.get("startpage", 0))
                for k, r in enumerate(rules):
                    start = int(r.get("startpage", 0))
                    end = int(rules[k + 1].get("startpage", n)) if k + 1 < len(rules) else n
                    first = int(r.get("firstpagenum", 1) or 1)
                    style, prefix = r.get("style", "") or "", r.get("prefix", "") or ""
                    for p in range(max(start, 0), min(end, n)):
                        labels[p] = prefix + _label_number(first + p - start, style)
            except (TypeError, ValueError):
                labels = [(p.get_label() or str(i + 1)) for i, p in enumerate(self.doc)]
            self._labels = labels
        return self._labels

    def info(self):
        with self.lock:
            d = self.doc
            pages = []
            labels = self.labels()
            for i, p in enumerate(d):
                r = p.rect
                pages.append({"w": round(r.width, 2), "h": round(r.height, 2), "rot": p.rotation, "pv": self.pv[i],
                              "label": labels[i]})
            return {"id": self.id, "name": self.name, "path": self.path, "pages": pages, "dirty": self.dirty,
                    "undo": len(self.undo), "redo": len(self.redo), "meta": self.meta(), "encrypted": bool(self.keep),
                    "protection": ("password" if self.keep.get("user") else "restrictions") if self.keep else None,
                    "forms": bool(d.is_form_pdf), "outline": len(d.get_toc(simple=True)), "converted": self.converted,
                    "security": "remove" if (self.security or {}).get("remove") else ("set" if self.security else None),
                    "attachments": d.embfile_count(), "source": self.source_format, "reflowable": bool(self.source),
                "fontsize": self.ebook_fontsize, "source_path": self.source_path}

    def meta(self):
        with self.lock:
            m = self.doc.metadata or {}
            out = {k: m.get(k) or "" for k in ("title", "author", "subject", "keywords", "creator", "producer",
                                               "creationDate", "modDate", "format", "encryption")}
            if self.keep and not out["encryption"]:   # an undo snapshot is in memory unencrypted
                out["encryption"] = "AES-256 (applied when saved)"
            return out

    # ------------------------------------------------------------------ rendering
    def render(self, pno, scale, fmt="png"):
        scale = max(0.05, min(float(scale), 8.0))
        key = (pno, self.pv[pno], round(scale, 3), fmt)
        with self.lock:
            hit = self.cache.get(key)
            if hit:
                self.cache.move_to_end(key)
                return hit
            page = self.page(pno)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), annots=True, alpha=False)
            data = pix.tobytes("jpeg", jpg_quality=82) if fmt == "jpg" else pix.tobytes("png")
            self.cache[key] = data
            while sum(len(v) for v in self.cache.values()) > 160 * 2 ** 20:
                self.cache.popitem(last=False)
            return data

    # ------------------------------------------------------------------ text
    def text_layer(self, pno):
        """Lines of text with their display boxes, for the selectable transparent layer and text editing."""
        with self.lock:
            page = self.page(pno)
            out = []
            d = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP)
            for bi, b in enumerate(d["blocks"]):
                if b.get("type") != 0:
                    continue
                for li, line in enumerate(b["lines"]):
                    spans = [s for s in line["spans"] if s["text"].strip() or s["text"] == " "]
                    if not spans:
                        continue
                    text = "".join(s["text"] for s in line["spans"])
                    if not text.strip():
                        continue
                    big = max(spans, key=lambda s: len(s["text"].strip()))
                    dx, dy = line["dir"]
                    out.append({"b": bi, "l": li, "r": self.rect_out(page, line["bbox"]), "t": text,
                                "s": round(big["size"], 2), "f": big["font"], "fl": big["flags"],
                                "c": hexc(big["color"]), "dir": [round(dx, 3), round(dy, 3)]})
            return out

    def page_text(self, pno):
        with self.lock:
            return self.page(pno).get_text("text", sort=True)

    def all_text(self):
        """Text of every page for the AI, cached until the document changes. Unsorted extraction keeps the
        PDF's own reading order and is ~15x faster than sort=True on big files."""
        with self.lock:
            key = tuple(self.pv)
            if self._text and self._text[0] == key:
                return self._text[1]
            pages = [p.get_text("text") for p in self.doc]
            self._text = (key, pages)
            return pages

    def selection_text(self, pno, rects):
        with self.lock:
            page = self.page(pno)
            parts = []
            for r in rects:
                parts.append(page.get_textbox(self.rect_in(page, r)).strip())
            return "\n".join(p for p in parts if p)

    def search(self, query, case=False, whole=False, limit=2000):
        """Find text line by line from one word extraction per page (fast on big files). Matches may span words
        of the same line; the highlight covers the matched characters."""
        q = re.sub(r"\s+", " ", (query or "").replace("\xa0", " ")).strip()
        if not q:
            return []
        pat = r"\s+".join(re.escape(part) for part in q.split(" "))
        if whole:
            pat = rf"(?<!\w){pat}(?!\w)"
        rx = re.compile(pat, 0 if case else re.IGNORECASE)
        out = []
        with self.lock:
            for pno, page in enumerate(self.doc):
                lines = OrderedDict()
                for w in page.get_text("words"):
                    lines.setdefault((w[5], w[6]), []).append(w)
                for words in lines.values():
                    text, spans = "", []
                    for w in words:
                        if text:
                            text += " "
                        spans.append((len(text), len(text) + len(w[4]), fitz.Rect(w[:4])))
                        text += w[4].replace("\xa0", " ")
                    for m in rx.finditer(text):
                        rect = fitz.Rect()
                        for a, b, wr in spans:
                            if b <= m.start() or a >= m.end():
                                continue
                            part = fitz.Rect(wr)
                            n = max(b - a, 1)
                            if wr.width >= wr.height:   # trim to the matched letters of a horizontal word
                                x0 = wr.x0 + wr.width * max(0, m.start() - a) / n
                                x1 = wr.x0 + wr.width * min(n, m.end() - a) / n
                                part = fitz.Rect(x0, wr.y0, x1, wr.y1)
                            rect = part if rect.is_empty else rect | part
                        if rect.is_empty:
                            continue
                        s = max(0, m.start() - 60)
                        snippet = ("…" if s else "") + text[s:m.end() + 90]
                        out.append({"p": pno, "r": self.rect_out(page, rect), "snippet": snippet})
                        if len(out) >= limit:
                            return out
        return out

    def snap_rects(self, page, rects):
        """Text selection rectangles -> one rectangle per text line, built from the words they cover."""
        words = page.get_text("words")
        lines = OrderedDict()
        for r in rects:
            rr = self.rect_in(page, r)
            for w in words:
                wr = fitz.Rect(w[:4])
                c = fitz.Point((wr.x0 + wr.x1) / 2, (wr.y0 + wr.y1) / 2)
                if rr.contains(c) or (rr & wr).get_area() > wr.get_area() * 0.5:
                    key = (w[5], w[6])
                    lines[key] = (lines[key] | wr) if key in lines else fitz.Rect(wr)
        if not lines:   # no words under the selection (e.g. a scanned page): use the raw rectangles
            return [self.rect_in(page, r) for r in rects]
        return list(lines.values())

    # ------------------------------------------------------------------ outline
    def outline(self):
        with self.lock:
            out = []
            for lvl, title, pno, *_ in self.doc.get_toc(simple=False):
                out.append({"lvl": lvl, "title": title, "p": pno - 1})
            return out

    def set_outline(self, items):
        toc, last = [], 0
        for it in items:
            lvl = max(1, min(int(it.get("lvl", 1)), last + 1))
            p = int(it.get("p", 0))
            toc.append([lvl, str(it.get("title", "")).strip() or "Untitled", max(1, min(p + 1, self.doc.page_count))])
            last = lvl
        with self.lock:
            self.snap()
            self.doc.set_toc(toc)
            self.changed([])

    # ------------------------------------------------------------------ annotations
    def annot_public(self, page, a, pno):
        t = a.type[0]
        info = a.info or {}
        colors = a.colors or {}
        kind = ANNOT_NAMES.get(t, a.type[1])
        if t == fitz.PDF_ANNOT_STAMP and info.get("subject") == "Signature":
            kind = "Signature"
        o = {"id": a.xref, "p": pno, "type": t, "kind": kind, "r": self.rect_out(page, a.rect),
             "stroke": hexc(colors.get("stroke")), "fill": hexc(colors.get("fill")),
             "opacity": round(a.opacity if a.opacity is not None and a.opacity >= 0 else 1, 2),
             "width": (a.border or {}).get("width") or 0, "content": info.get("content", ""),
             "author": info.get("title", ""), "subject": info.get("subject", ""),
             "date": info.get("modDate") or info.get("creationDate") or "", "flags": a.flags}
        if t == fitz.PDF_ANNOT_FREE_TEXT:
            try:
                m = re.search(r"(\d+(?:\.\d+)?)\s*Tf", self.doc.xref_get_key(a.xref, "DA")[1] or "")
                o["size"] = float(m.group(1)) if m else 12
            except Exception:  # noqa: BLE001
                o["size"] = 12
            o["textcolor"] = o["stroke"]
        return o

    def annots(self, pno=None):
        with self.lock:
            out = []
            pages = [pno] if pno is not None else range(self.doc.page_count)
            for i in pages:
                page = self.doc[i]
                for a in page.annots():
                    if a.type[0] in (fitz.PDF_ANNOT_LINK, fitz.PDF_ANNOT_POPUP, fitz.PDF_ANNOT_WIDGET):
                        continue
                    out.append(self.annot_public(page, a, i))
            return out

    def _find_annot(self, page, xref):
        for a in page.annots():
            if a.xref == xref:
                return a
        raise ValueError("that comment no longer exists")

    def _finish(self, a, opts, author):
        now = fitz.get_pdf_now()
        info = {"title": author or "", "subject": opts.get("subject") or ANNOT_NAMES.get(a.type[0], ""),
                "creationDate": now, "modDate": now}
        if opts.get("content") is not None:
            info["content"] = str(opts["content"])
        a.set_info(**info)
        if opts.get("opacity") is not None and a.type[0] != fitz.PDF_ANNOT_FREE_TEXT:
            a.set_opacity(max(0.05, min(float(opts["opacity"]), 1)))
        a.update()
        return a

    def add_annot(self, pno, kind, o, author=""):
        with self.lock:
            page = self.page(pno)
            self.snap()
            stroke = rgb(o.get("color"), (0.89, 0.27, 0.18))
            fill = rgb(o["fill"]) if o.get("fill") else None
            width = float(o.get("width") or 1.5)
            a = None
            if kind in ("highlight", "underline", "strikeout", "squiggly"):
                rects = self.snap_rects(page, o.get("rects") or [])
                if not rects:
                    raise ValueError("select some text first")
                fn = {"highlight": page.add_highlight_annot, "underline": page.add_underline_annot,
                      "strikeout": page.add_strikeout_annot, "squiggly": page.add_squiggly_annot}[kind]
                a = fn(quads=[r.quad for r in rects])
                a.set_colors(stroke=rgb(o.get("color"), (1, 0.85, 0.2)))
            elif kind == "area":
                r = self.rect_in(page, o["rect"])
                a = page.add_highlight_annot(r)
                a.set_colors(stroke=rgb(o.get("color"), (1, 0.85, 0.2)))
            elif kind == "note":
                p = self.pt_in(page, o["point"])
                a = page.add_text_annot(p, o.get("content") or "", icon=o.get("icon") or "Comment")
                a.set_colors(stroke=rgb(o.get("color"), (1, 0.78, 0.2)))
            elif kind == "freetext":
                r = self.rect_in(page, o["rect"])
                font = {"sans": "helv", "serif": "tiro", "mono": "cour"}.get(o.get("font"), "helv")
                a = page.add_freetext_annot(r, o.get("text") or "", fontsize=float(o.get("size") or 12), fontname=font,
                                            text_color=rgb(o.get("textcolor") or o.get("color"), (0.1, 0.1, 0.12)),
                                            fill_color=fill, border_width=float(o.get("width") or 0),
                                            rotate=page.rotation, align=int(o.get("align") or 0))
                if o.get("width"):
                    a.set_border(width=float(o["width"]))
                o = dict(o, content=o.get("text") or "")
            elif kind in ("rect", "ellipse"):
                r = self.rect_in(page, o["rect"])
                a = (page.add_rect_annot if kind == "rect" else page.add_circle_annot)(r)
                a.set_colors(stroke=stroke, fill=fill)
                a.set_border(width=width)
            elif kind in ("line", "arrow"):
                p1, p2 = self.pt_in(page, o["points"][0]), self.pt_in(page, o["points"][1])
                a = page.add_line_annot(p1, p2)
                a.set_colors(stroke=stroke)
                a.set_border(width=width)
                if kind == "arrow":
                    a.set_line_ends(fitz.PDF_ANNOT_LE_NONE, fitz.PDF_ANNOT_LE_CLOSED_ARROW)
                    a.set_colors(stroke=stroke, fill=stroke)
            elif kind == "polygon":
                pts = [self.pt_in(page, p) for p in o["points"]]
                a = page.add_polygon_annot(pts)
                a.set_colors(stroke=stroke, fill=fill)
                a.set_border(width=width)
            elif kind == "ink":
                paths = [[tuple(self.pt_in(page, p)) for p in path] for path in o["paths"] if len(path) > 1]
                if not paths:
                    raise ValueError("nothing was drawn")
                a = page.add_ink_annot(paths)
                a.set_colors(stroke=stroke)
                a.set_border(width=width)
            elif kind == "stamp":
                a = self._stamp(page, self.rect_in(page, o["rect"]), o.get("label") or "Approved", o.get("color"),
                                author if o.get("sign", True) else "")
                o = dict(o, content=o.get("label"))
            elif kind == "redact":
                r = self.rect_in(page, o["rect"])
                a = page.add_redact_annot(r, text=o.get("overlay") or None, fill=(0, 0, 0))
            else:
                raise ValueError(f"unknown tool {kind}")
            self._finish(a, o, author)
            self.changed([pno])
            return self.annot_public(page, self._find_annot(page, a.xref), pno)

    @staticmethod
    def _upright(pix, rot):
        """Stamp annotations are drawn in unrotated page space: turn their image so it looks upright on a page
        displayed with /Rotate `rot`."""
        if not rot:
            return pix
        src = fitz.open()
        pg = src.new_page(width=pix.width, height=pix.height)
        pg.insert_image(pg.rect, pixmap=pix)
        pg.set_rotation((360 - rot) % 360)
        return pg.get_pixmap(alpha=True)

    @staticmethod
    def stamp_png(label, color=None, author="", dated=True):
        """Draws a rubber stamp (rounded double frame, bold caps, name + date line) as a transparent PNG."""
        text, col = STAMPS.get(label, (label.upper(), "#c0392b"))
        c = rgb(color or col)
        tl = fitz.get_text_length(text, fontname="hebo", fontsize=30)
        w = max(160, tl + 44)
        sub = " · ".join(x for x in (author, time.strftime("%d.%m.%Y %H:%M") if dated else "") if x)
        h = 74 if sub else 56
        s = fitz.open()
        sp = s.new_page(width=w, height=h)
        sh = sp.new_shape()
        sh.draw_rect(fitz.Rect(2.5, 2.5, w - 2.5, h - 2.5), radius=0.12)
        sh.finish(color=c, width=3)
        sh.draw_rect(fitz.Rect(7, 7, w - 7, h - 7), radius=0.09)
        sh.finish(color=c, width=1)
        sh.commit()
        sp.insert_text(((w - tl) / 2, 40), text, fontsize=30, fontname="hebo", color=c)
        if sub:
            sl = fitz.get_text_length(sub, fontname="helv", fontsize=10)
            sp.insert_text(((w - sl) / 2, 59), sub, fontsize=10, fontname="helv", color=c)
        return sp.get_pixmap(dpi=220, alpha=True), w / h

    def _stamp(self, page, rect, label, color=None, author=""):
        pix, _ = self.stamp_png(label, color, author)
        pix = self._upright(pix, page.rotation)
        ratio = pix.width / pix.height
        # keep the stamp's proportions inside the box that was drawn
        if rect.width / max(rect.height, 1) > ratio:
            w = rect.height * ratio
            rect = fitz.Rect(rect.x0 + (rect.width - w) / 2, rect.y0, rect.x0 + (rect.width + w) / 2, rect.y1)
        else:
            h = rect.width / ratio
            rect = fitz.Rect(rect.x0, rect.y0 + (rect.height - h) / 2, rect.x1, rect.y0 + (rect.height + h) / 2)
        a = page.add_stamp_annot(rect, stamp=pix)
        a.set_info(subject="Stamp")
        return a

    def add_signature(self, pno, rect, png):
        """A drawn or imported signature, as a movable image stamp."""
        with self.lock:
            page = self.page(pno)
            self.snap()
            stamp = self._upright(fitz.Pixmap(png), page.rotation) if page.rotation else png
            a = page.add_stamp_annot(self.rect_in(page, rect), stamp=stamp)
            a.set_info(subject="Signature", content="Signature")
            a.update()
            self.changed([pno])
            return self.annot_public(page, self._find_annot(page, a.xref), pno)

    def update_annot(self, pno, xref, o):
        with self.lock:
            page = self.page(pno)
            a = self._find_annot(page, xref)
            self.snap()
            t = a.type[0]
            if "content" in o and t != fitz.PDF_ANNOT_FREE_TEXT:
                a.set_info(content=str(o["content"]))
            if t == fitz.PDF_ANNOT_FREE_TEXT and ("text" in o or "size" in o or "textcolor" in o or "content" in o):
                # FreeText appearance can't change font size/colour in place reliably: rebuild it
                cur = self.annot_public(page, a, pno)
                text = o.get("text", o.get("content", cur["content"]))
                r = a.rect
                fill = (a.colors or {}).get("fill")
                fill = rgb(o["fill"]) if o.get("fill") else (fill or None)
                info = a.info
                page.delete_annot(a)
                a = page.add_freetext_annot(r, text, fontsize=float(o.get("size") or cur.get("size") or 12),
                                            text_color=rgb(o.get("textcolor") or cur.get("textcolor"), (0.1, 0.1, 0.12)),
                                            fill_color=fill, rotate=page.rotation)
                a.set_info(title=info.get("title", ""), content=text, subject=info.get("subject", ""))
            if "color" in o:
                if t == fitz.PDF_ANNOT_FREE_TEXT:
                    pass
                elif t in (fitz.PDF_ANNOT_LINE,) and (a.line_ends or (0, 0))[1]:
                    a.set_colors(stroke=rgb(o["color"]), fill=rgb(o["color"]))
                else:
                    a.set_colors(stroke=rgb(o["color"]), fill=(a.colors or {}).get("fill") or None)
            if "fill" in o and t in (fitz.PDF_ANNOT_SQUARE, fitz.PDF_ANNOT_CIRCLE, fitz.PDF_ANNOT_POLYGON):
                a.set_colors(stroke=(a.colors or {}).get("stroke"), fill=rgb(o["fill"]) if o["fill"] else [])
            if o.get("width") is not None and t not in (fitz.PDF_ANNOT_FREE_TEXT, fitz.PDF_ANNOT_TEXT) and \
                    t not in (fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE, fitz.PDF_ANNOT_STRIKE_OUT, fitz.PDF_ANNOT_SQUIGGLY):
                a.set_border(width=float(o["width"]))
            if o.get("opacity") is not None:
                a.set_opacity(max(0.05, min(float(o["opacity"]), 1)))
            if o.get("rect"):
                a = self._move(page, a, self.rect_in(page, o["rect"]))
            a.update()
            self.changed([pno])
            return self.annot_public(page, self._find_annot(page, a.xref), pno)

    def _move(self, page, a, new):
        """Move/resize. Shapes with vertices are moved by rewriting their points."""
        t = a.type[0]
        old = a.rect
        if t in (fitz.PDF_ANNOT_INK, fitz.PDF_ANNOT_LINE, fitz.PDF_ANNOT_POLYGON, fitz.PDF_ANNOT_POLY_LINE):
            sx = new.width / old.width if old.width > 1 else 1
            sy = new.height / old.height if old.height > 1 else 1
            m = fitz.Matrix(1, 0, 0, 1, -old.x0, -old.y0) * fitz.Matrix(sx, sy) * fitz.Matrix(1, 0, 0, 1, new.x0, new.y0)
            colors, border, info, opacity = a.colors, a.border, a.info, a.opacity
            if t == fitz.PDF_ANNOT_INK:
                paths = [[tuple(fitz.Point(p) * m) for p in path] for path in a.vertices]
                ends = None
                page.delete_annot(a)
                a = page.add_ink_annot(paths)
            elif t == fitz.PDF_ANNOT_LINE:
                v = [fitz.Point(p) * m for p in a.vertices]
                ends = a.line_ends
                page.delete_annot(a)
                a = page.add_line_annot(v[0], v[1])
                if ends:
                    a.set_line_ends(*ends)
            else:
                v = [fitz.Point(p) * m for p in a.vertices]
                page.delete_annot(a)
                a = (page.add_polygon_annot if t == fitz.PDF_ANNOT_POLYGON else page.add_polyline_annot)(v)
            a.set_colors(stroke=colors.get("stroke"), fill=colors.get("fill") or None)
            a.set_border(width=(border or {}).get("width") or 1.5)
            a.set_info(**{k: v for k, v in info.items() if k in ("title", "content", "subject")})
            if opacity is not None and opacity >= 0:
                a.set_opacity(opacity)
            return a
        if t in (fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE, fitz.PDF_ANNOT_STRIKE_OUT, fitz.PDF_ANNOT_SQUIGGLY):
            return a   # text markup belongs to its text
        if t == fitz.PDF_ANNOT_TEXT:
            new = fitz.Rect(new.x0, new.y0, new.x0 + old.width, new.y0 + old.height)
        a.set_rect(new)
        return a

    def delete_annot(self, pno, xref):
        with self.lock:
            page = self.page(pno)
            a = self._find_annot(page, xref)
            self.snap()
            page.delete_annot(a)
            self.changed([pno])

    def annot_at(self, pno, point):
        with self.lock:
            page = self.page(pno)
            p = self.pt_in(page, point)
            best = None
            for a in page.annots():
                if a.type[0] in (fitz.PDF_ANNOT_LINK, fitz.PDF_ANNOT_POPUP, fitz.PDF_ANNOT_WIDGET):
                    continue
                r = a.rect + (-3, -3, 3, 3)
                if r.contains(p) and (best is None or a.rect.get_area() < best.rect.get_area()):
                    best = a
            return self.annot_public(page, best, pno) if best else None

    def apply_redactions(self):
        with self.lock:
            pages = [i for i, p in enumerate(self.doc) if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in p.annots())]
            if not pages:
                raise ValueError("mark something to redact first")
            self.snap()
            for i in pages:
                self.doc[i].apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
            self.changed(pages)
            return len(pages)

    def flatten(self):
        with self.lock:
            self.snap()
            self.doc.bake(annots=True, widgets=True)
            self.changed(None)

    # ------------------------------------------------------------------ content editing
    def line_at(self, pno, point):
        with self.lock:
            page = self.page(pno)
            p = self.pt_in(page, point)
            d = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
            best = None
            for b in d["blocks"]:
                if b.get("type") != 0:
                    continue
                for line in b["lines"]:
                    r = fitz.Rect(line["bbox"])
                    if (r + (-2, -2, 2, 2)).contains(p):
                        if best is None or r.get_area() < fitz.Rect(best["bbox"]).get_area():
                            best = line
            if not best:
                return None
            spans = [s for s in best["spans"] if s["text"].strip()]
            big = max(spans, key=lambda s: len(s["text"])) if spans else best["spans"][0]
            low = big["font"].lower()
            return {"r": self.rect_out(page, best["bbox"]), "text": "".join(s["text"] for s in best["spans"]),
                    "size": round(big["size"], 2), "font": big["font"], "flags": big["flags"], "color": hexc(big["color"]),
                    "bold": bool(big["flags"] & 16) or "bold" in low or "black" in low or "heavy" in low,
                    "italic": bool(big["flags"] & 2) or "italic" in low or "oblique" in low,
                    "family": self._family(big["font"], big["flags"]),
                    "origin": self.pt_out(page, spans[0]["origin"] if spans else big["origin"]),
                    "dir": list(best["dir"])}

    @staticmethod
    def _family(fontname, flags):
        """sans | serif | mono, from the font name first (MuPDF's serif flag is unreliable), then the flags."""
        low = re.sub(r"^[A-Z]{6}\+", "", fontname or "").lower()
        if re.search(r"mono|cour|consol|code", low):
            return "mono"
        if re.search(r"sans|arial|helv|calibri|segoe|verdana|tahoma|aptos|gothic|grotesk|roboto|inter|lato|open|frutiger|univers|futura", low):
            return "sans"
        if re.search(r"serif|roman|times|georgia|cambria|garamond|minion|palatino|book|baskerville|tiro", low):
            return "serif"
        return "mono" if flags & 8 else "serif" if flags & 4 else "sans"

    @staticmethod
    def _norm_text(s):
        return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()

    def _embedded_font(self, page, clean, text):
        """The PDF's own embedded font for `clean`, if it is a real TrueType/OpenType font that has every
        character of `text` AND writes it back as the same text (subset fonts often have broken cmaps).
        Returns the font bytes or None."""
        def key(name):   # "ABCDEF+Candara-Regular", "Candara Regular", "Candara,Regular" -> "candara"
            n = re.sub(r"^[A-Z]{6}\+", "", name or "").lower()
            n = re.sub(r"[\s,_-]*(regular|roman|book|normal|mt|ps|psmt)$", "", n)
            return re.sub(r"[\s,_-]", "", n)

        want = key(clean)
        for xref, ext, _typ, base, _ref, _enc in page.get_fonts():
            if key(base) != want or ext not in ("ttf", "otf"):
                continue
            try:
                _n, _e, _t, buf = self.doc.extract_font(xref)
                if not buf:
                    continue
                f = fitz.Font(fontbuffer=buf)
                if not all(c.isspace() or f.has_glyph(ord(c)) for c in text):
                    continue
                trial = fitz.open()
                tp = trial.new_page(width=2000, height=200)
                tp.insert_font(fontname="T", fontbuffer=buf)
                tp.insert_text((10, 100), text, fontname="T", fontsize=12)
                ok = self._norm_text(tp.get_text()) == self._norm_text(text)
                trial.close()
                if ok:
                    return buf
            except Exception:  # noqa: BLE001 - an unusable font: try the next one / fall back
                continue
        return None

    def _font_for(self, page, fontname, flags, text, family=None, bold=None, italic=None):
        """Pick a font that can show `text` and return insert_text kwargs ("fontbuffer" means: register it with
        `insert_font` first - see `_write`). Order: the same family from C:\\Windows\\Fonts (full character set,
        identical look), the document's own embedded font, then Arial / Times New Roman / Courier New by style."""
        bold = bool(flags & 16) if bold is None else bold
        italic = bool(flags & 2) if italic is None else italic
        clean = re.sub(r"^[A-Z]{6}\+", "", fontname or "")
        low = clean.lower().replace("-", "").replace(" ", "").replace(",", "")
        key = None
        if family is None:
            key = next((k for k in SYSTEM_FONTS if k in low), None)
            if key is None and clean:
                buf = self._embedded_font(page, clean, text)
                if buf:
                    return {"fontname": self._fname(hashlib.md5(buf).hexdigest()[:8]), "fontbuffer": buf}
            if key is None:
                key = UI_FONTS[self._family(fontname, flags)]
        else:
            key = UI_FONTS.get(family, family if family in SYSTEM_FONTS else "arial")
        if not bold and "bold" in low and family is None:
            bold = True
        if not italic and ("italic" in low or "oblique" in low) and family is None:
            italic = True
        files = SYSTEM_FONTS[key]
        name = files[(1 if bold else 0) + (2 if italic else 0)]
        path = os.path.join(WINFONTS, name + ".ttf")
        if not os.path.exists(path):
            path = os.path.join(WINFONTS, files[0] + ".ttf")
        if os.path.exists(path):
            return {"fontname": self._fname(re.sub(r"\W", "", name)), "fontfile": path}
        return self._base14(key, bold, italic)

    def _fname(self, base):
        """Resource name for a font Washi embeds. The tag changes whenever fonts are subset (save, reduce size)
        and differs per opened document, so a new edit never reuses a shrunken copy that lacks its letters."""
        return f"W{base}{self._font_tag}"

    @staticmethod
    def _base14(key, bold, italic):
        base = {"arial": "helv", "times": "tiro", "courier": "cour"}.get(key, "helv")
        b14 = {"helv": ["helv", "hebo", "heit", "hebi"], "tiro": ["tiro", "tibo", "tiit", "tibi"],
               "cour": ["cour", "cobo", "coit", "cobi"]}[base]
        return {"fontname": b14[(1 if bold else 0) + (2 if italic else 0)]}

    def _write(self, page, origin, text, font, **kw):
        """insert_text with a font from `_font_for`. Font bytes are registered on the page first (insert_text
        only accepts font files); if that font cannot be used, Arial is used instead."""
        font = dict(font)
        buf = font.pop("fontbuffer", None)
        if buf is not None or "fontfile" in font:
            self._fonts_added = True
        try:
            if buf is not None:
                page.insert_font(fontname=font["fontname"], fontbuffer=buf)
            page.insert_text(origin, text, **font, **kw)
        except Exception:  # noqa: BLE001
            if buf is None and "fontfile" not in font:
                raise
            fallback = os.path.join(WINFONTS, "arial.ttf")
            alt = {"fontname": self._fname("ArialFB"), "fontfile": fallback} if os.path.exists(fallback) else self._base14("arial", False, False)
            page.insert_text(origin, text, **alt, **kw)
        self._fix_spaces(page)

    def _fix_spaces(self, page, doc=None):
        """Fonts Washi embeds (resource names W…) map the space glyph to U+00A0 in their ToUnicode table, so
        copied text would carry non-breaking spaces. Point that glyph back at a normal space."""
        for xref, _ext, _typ, _base, name, _enc in page.get_fonts():
            if not name.startswith("W"):
                continue
            try:
                tu = (doc or self.doc).xref_get_key(xref, "ToUnicode")
                if tu[0] != "xref":
                    continue
                sx = int(tu[1].split()[0])
                cmap = (doc or self.doc).xref_stream(sx)
                fixed = re.sub(rb"(\n<[0-9a-fA-F]{4}>)\s*<00[aA]0>", rb"\1 <0020>", cmap)
                if fixed != cmap:
                    (doc or self.doc).update_stream(sx, fixed)
            except Exception:  # noqa: BLE001
                continue

    @staticmethod
    def _dir_rotate(d):
        """Text direction (unrotated page space) -> insert_text's counter-clockwise rotate."""
        dx, dy = d
        if abs(dx) >= abs(dy):
            return 0 if dx >= 0 else 180
        return 90 if dy < 0 else 270

    def edit_line(self, pno, o):
        """Replace a line of page text: remove the old glyphs (redaction, keeping images and drawings)
        and write the new text at the same baseline in the closest font available."""
        with self.lock:
            page = self.page(pno)
            line = self.line_at(pno, o["point"])
            if not line:
                raise ValueError("there is no text there")
            text = o.get("text", "")
            self.snap()
            r = self.rect_in(page, line["r"])
            page.add_redact_annot(r, fill=False)
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)
            if text.strip():
                size = float(o.get("size") or line["size"])
                kw = self._font_for(page, line["font"], line["flags"], text, family=o.get("family"),
                                    bold=o.get("bold"), italic=o.get("italic"))
                origin = self.pt_in(page, line["origin"])
                self._write(page, origin, text, kw, fontsize=size, color=rgb(o.get("color") or line["color"]),
                            rotate=self._dir_rotate(line["dir"]))
            self.changed([pno])

    def add_text(self, pno, o):
        """Typewriter: new page text (not a comment) at a point; several lines allowed."""
        with self.lock:
            page = self.page(pno)
            text = o.get("text", "")
            if not text.strip():
                raise ValueError("type some text first")
            self.snap()
            size = float(o.get("size") or 12)
            kw = self._font_for(page, "", 0, text, family=o.get("family") or "sans",
                                bold=bool(o.get("bold")), italic=bool(o.get("italic")))
            x, y = o["point"]
            origin = self.pt_in(page, (x, y + size * 0.88))   # point = top-left of the first line
            self._write(page, origin, text, kw, fontsize=size, color=rgb(o.get("color"), (0, 0, 0)),
                        rotate=page.rotation, lineheight=1.2)
            self.changed([pno])

    def whiteout(self, pno, rect, color="#ffffff"):
        with self.lock:
            page = self.page(pno)
            self.snap()
            r = self.rect_in(page, rect)
            page.add_redact_annot(r, fill=rgb(color, (1, 1, 1)))
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
            self.changed([pno])

    def add_image(self, pno, rect, data=None, path=None, keep_ratio=True):
        with self.lock:
            page = self.page(pno)
            if path:
                with open(path, "rb") as f:
                    data = f.read()
            if not data:
                raise ValueError("no image")
            try:
                fitz.Pixmap(data)
            except Exception as e:  # noqa: BLE001
                raise ValueError("that file is not an image Washi can read") from e
            self.snap()
            r = self.rect_in(page, rect)
            page.insert_image(r, stream=data, keep_proportion=keep_ratio, rotate=page.rotation)
            self.changed([pno])

    @staticmethod
    def image_size(data):
        pix = fitz.Pixmap(data)
        return pix.width, pix.height

    def add_link(self, pno, rect, uri=None, page_to=None):
        with self.lock:
            page = self.page(pno)
            self.snap()
            r = self.rect_in(page, rect)
            if uri:
                if not re.match(r"^(https?://|mailto:)", uri):
                    uri = "https://" + uri
                page.insert_link({"kind": fitz.LINK_URI, "from": r, "uri": uri})
            else:
                page.insert_link({"kind": fitz.LINK_GOTO, "from": r, "page": int(page_to), "to": fitz.Point(0, 0)})
            self.changed([pno])

    def links(self, pno):
        with self.lock:
            page = self.page(pno)
            out = []
            for l in page.get_links():
                if l.get("kind") in (fitz.LINK_URI, fitz.LINK_GOTO, fitz.LINK_NAMED):
                    out.append({"r": self.rect_out(page, l["from"]), "uri": l.get("uri"),
                                "page": l.get("page") if l.get("kind") == fitz.LINK_GOTO else None})
            return out

    # ------------------------------------------------------------------ forms
    def widgets(self, pno):
        with self.lock:
            page = self.page(pno)
            out = []
            for w in page.widgets():
                out.append({"xref": w.xref, "name": w.field_name, "label": w.field_label or w.field_name,
                            "type": w.field_type_string, "value": w.field_value, "r": self.rect_out(page, w.rect),
                            "options": w.choice_values or [], "readonly": bool(w.field_flags & 1),
                            "multiline": bool(w.field_flags & 4096), "on": w.on_state() if w.field_type in (
                                fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON) else None,
                            "size": w.text_fontsize or 0, "max": w.text_maxlen or 0})
            return out

    def set_field(self, pno, xref, value):
        with self.lock:
            page = self.page(pno)
            for w in page.widgets():
                if w.xref == xref:
                    self.snap()
                    if w.field_type in (fitz.PDF_WIDGET_TYPE_CHECKBOX, fitz.PDF_WIDGET_TYPE_RADIOBUTTON):
                        w.field_value = w.on_state() if value else "Off"
                    else:
                        w.field_value = str(value)
                    w.update()
                    self.changed(None if w.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON else [pno])
                    return
            raise ValueError("that field no longer exists")

    def add_field(self, pno, kind, rect, name=None):
        with self.lock:
            page = self.page(pno)
            self.snap()
            w = fitz.Widget()
            w.field_type = {"text": fitz.PDF_WIDGET_TYPE_TEXT, "check": fitz.PDF_WIDGET_TYPE_CHECKBOX,
                            "combo": fitz.PDF_WIDGET_TYPE_COMBOBOX, "sign": fitz.PDF_WIDGET_TYPE_SIGNATURE}.get(kind, fitz.PDF_WIDGET_TYPE_TEXT)
            w.rect = self.rect_in(page, rect)
            w.field_name = name or f"{kind}_{uuid.uuid4().hex[:6]}"
            w.text_fontsize = 0
            w.border_color = (0.6, 0.65, 0.75)
            w.fill_color = (0.94, 0.96, 1)
            if kind == "combo":
                w.choice_values = ["Option 1", "Option 2", "Option 3"]
                w.field_value = "Option 1"
            page.add_widget(w)
            self.changed([pno])

    # ------------------------------------------------------------------ pages
    def rotate_pages(self, pnos, angle):
        with self.lock:
            self.snap()
            for p in pnos:
                pg = self.page(p)
                pg.set_rotation((pg.rotation + int(angle)) % 360)
            self.changed(None)

    def delete_pages(self, pnos):
        with self.lock:
            if len(set(pnos)) >= self.doc.page_count:
                raise ValueError("a document needs at least one page")
            self.snap()
            self.doc.delete_pages(sorted(set(pnos)))
            self.changed(None)

    def insert_blank(self, at, w=None, h=None, count=1):
        with self.lock:
            ref = self.doc[min(max(at - 1, 0), self.doc.page_count - 1)].rect if self.doc.page_count else fitz.paper_rect("a4")
            self.snap()
            for i in range(int(count)):
                self.doc.new_page(at + i, width=w or ref.width, height=h or ref.height)
            self.changed(None)

    def duplicate_pages(self, pnos):
        with self.lock:
            pnos = sorted(set(pnos))
            if not pnos or pnos[0] < 0 or pnos[-1] >= self.doc.page_count:
                raise ValueError("no such page")
            self.snap()
            for i, p in enumerate(pnos):
                src = p + i   # earlier copies shifted this page down
                to = src + 1
                self.doc.fullcopy_page(src, to if to < self.doc.page_count else -1)   # -1 = append after the last
            self.changed(None)

    def move_pages(self, pnos, to):
        """Move pages (zero-based) so they start before page `to` (in the original numbering)."""
        with self.lock:
            pnos = sorted(set(pnos))
            n = self.doc.page_count
            order = [i for i in range(n) if i not in pnos]
            dest = len([i for i in range(min(to, n)) if i not in pnos])
            new = order[:dest] + pnos + order[dest:]
            if new == list(range(n)):
                return
            self.snap()
            self.doc.select(new)
            self._labels = None
            self.changed(None)

    def insert_file(self, path, at, password=None, data=None):
        with self.lock:
            if data is None:
                with open(path, "rb") as f:
                    data = f.read()
            src = fitz.open(stream=data, filetype=os.path.splitext(path or "")[1].lstrip(".") or None) if data[:5] != b"%PDF-" \
                else fitz.open("pdf", data)
            if src.needs_pass and not src.authenticate(password or ""):
                raise ValueError(f"{os.path.basename(path or 'file')} is protected by a password. Open it in Washi, remove the password (Protect > Unlock), save, then insert it.")
            if not src.is_pdf:
                src = fitz.open("pdf", src.convert_to_pdf())
            self.snap()
            self.doc.insert_pdf(src, start_at=at, links=True, annots=True)
            self.changed(None)
            return src.page_count

    def extract_pages(self, pnos):
        with self.lock:
            out = fitz.open()
            for p in pnos:
                out.insert_pdf(self.doc, from_page=p, to_page=p)
            return out.tobytes(garbage=3, deflate=True)

    def crop(self, pnos, rect_ui, ref_page):
        with self.lock:
            page = self.page(ref_page)
            r = self.rect_in(page, rect_ui)
            self.snap()
            for p in pnos:
                pg = self.page(p)
                cb = pg.cropbox
                rr = fitz.Rect(r.x0 + cb.x0, r.y0 + cb.y0, r.x1 + cb.x0, r.y1 + cb.y0) & pg.mediabox
                if rr.is_empty:
                    continue
                pg.set_cropbox(rr)
            self.changed(None)

    def uncrop(self, pnos):
        with self.lock:
            self.snap()
            for p in pnos:
                pg = self.page(p)
                pg.set_cropbox(pg.mediabox)
            self.changed(None)

    # ------------------------------------------------------------------ stamps over pages
    def _pages_for(self, spec):
        if not spec or spec == "all":
            return list(range(self.doc.page_count))
        if isinstance(spec, list):
            return [int(p) for p in spec]
        return parse_ranges(spec, self.doc.page_count)

    def watermark(self, o):
        with self.lock:
            text = (o.get("text") or "").strip()
            if not text:
                raise ValueError("type the watermark text")
            pages = self._pages_for(o.get("pages"))
            self.snap()
            size = float(o.get("size") or 60)
            angle = float(o.get("angle") if o.get("angle") is not None else 45)
            color = rgb(o.get("color"), (0.75, 0.2, 0.15))
            opacity = float(o.get("opacity") or 0.18)
            font = "hebo"
            for p in pages:
                page = self.doc[p]
                rect = page.rect
                tl = fitz.get_text_length(text, fontname=font, fontsize=size)
                c = self.pt_in(page, (rect.width / 2, rect.height / 2))     # page centre, unrotated space
                origin = fitz.Point(c.x - tl / 2, c.y + size * 0.35)       # text centred on it, then turned
                # rotate around the page centre, counter-clockwise as seen on screen
                m = fitz.Matrix(angle + page.rotation)
                page.insert_text(origin, text, fontsize=size, fontname=font, color=color, fill_opacity=opacity,
                                 stroke_opacity=opacity, morph=(c, m), overlay=bool(o.get("front", True)))
            self.changed(pages)

    def header_footer(self, o):
        """Page numbers / header / footer text. Tokens: {page} {pages} {date} {name}."""
        with self.lock:
            pages = self._pages_for(o.get("pages"))
            tpl = o.get("text") or "Page {page} of {pages}"
            pos = o.get("position") or "bottom-center"
            size = float(o.get("size") or 10)
            margin = float(o.get("margin") or 28)
            color = rgb(o.get("color"), (0.25, 0.25, 0.3))
            start = int(o.get("start") or 1)
            self.snap()
            total = len(pages)
            for i, p in enumerate(pages):
                page = self.doc[p]
                text = tpl.replace("{page}", str(start + i)).replace("{pages}", str(total + start - 1)) \
                    .replace("{date}", time.strftime("%d.%m.%Y")).replace("{name}", os.path.splitext(self.name)[0])
                tl = fitz.get_text_length(text, fontname="helv", fontsize=size)
                w, h = page.rect.width, page.rect.height
                vert, horiz = pos.split("-")
                x = {"left": margin, "center": (w - tl) / 2, "right": w - margin - tl}[horiz]
                y = margin if vert == "top" else h - margin + size * 0.3
                if vert == "top":
                    y = margin + size * 0.7
                kw = self._font_for(page, "", 0, text, family="sans")
                self._write(page, self.pt_in(page, (x, y)), text, kw, fontsize=size, color=color, rotate=page.rotation)
            self.changed(pages)

    # ------------------------------------------------------------------ document level
    def set_meta(self, m):
        with self.lock:
            self.snap()
            cur = self.doc.metadata or {}
            cur.update({k: str(v) for k, v in m.items() if k in ("title", "author", "subject", "keywords", "creator")})
            self.doc.set_metadata(cur)
            self._dirty()

    def protect(self, o):
        if o.get("remove"):
            self.security = {"remove": True} if self.keep else None   # nothing to remove from an open file
        else:
            user, owner = o.get("user") or "", o.get("owner") or ""
            if not user and not owner:
                raise ValueError("set at least one password")
            perms = fitz.PDF_PERM_ACCESSIBILITY
            for key, flag in (("print", fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ), ("copy", fitz.PDF_PERM_COPY),
                              ("edit", fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ASSEMBLE),
                              ("annotate", fitz.PDF_PERM_ANNOTATE | fitz.PDF_PERM_FORM)):
                if o.get(key, True):
                    perms |= flag
            self.security = {"user": user, "owner": owner or user, "permissions": perms}
        self._dirty()

    def attachments(self):
        with self.lock:
            out = []
            for name in self.doc.embfile_names():
                i = self.doc.embfile_info(name)
                out.append({"name": name, "file": i.get("filename") or name, "size": i.get("size") or i.get("length") or 0,
                            "desc": i.get("description") or ""})
            return out

    def add_attachment(self, path):
        with self.lock:
            with open(path, "rb") as f:
                data = f.read()
            self.snap()
            name = os.path.basename(path)
            base, n = name, 2
            while name in self.doc.embfile_names():
                name = f"{os.path.splitext(base)[0]} ({n}){os.path.splitext(base)[1]}"
                n += 1
            self.doc.embfile_add(name, data, filename=os.path.basename(path))
            self._dirty()

    def get_attachment(self, name):
        with self.lock:
            return self.doc.embfile_get(name)

    def del_attachment(self, name):
        with self.lock:
            self.snap()
            self.doc.embfile_del(name)
            self._dirty()

    def _shrink_images(self, threshold, target, quality):
        """Resample page images shown above `threshold` dpi down to about `target` dpi (halving steps) and store
        them as JPEG (PNG when they have transparency). 1-bit scans, tiny images and images whose new version
        would be bigger are left alone. Returns how many images were replaced."""
        import math
        done, replaced = set(), 0
        for page in self.doc:
            try:   # get_images reads the resources only; get_image_info parses every page (~60 ms each)
                items = page.get_images(full=True)
            except Exception:  # noqa: BLE001
                continue
            for item in items:
                xref, _smask, w, h, bpc = item[0], item[1], item[2], item[3], item[4]
                if xref <= 0 or xref in done:
                    continue
                done.add(xref)
                try:
                    if min(w, h) < 64 or bpc < 8:
                        continue
                    boxes = [r for r in page.get_image_rects(xref) if r.width >= 1 and r.height >= 1]
                    if not boxes:
                        continue
                    box = max(boxes, key=lambda r: r.width * r.height)   # its largest appearance decides
                    shown = max(w / (box.width / 72), h / (box.height / 72))
                    if shown <= threshold:
                        continue
                    steps = int(math.floor(math.log2(shown / target)))
                    if steps < 1:
                        continue
                    pix = fitz.Pixmap(self.doc, xref)
                    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    smask = self.doc.xref_get_key(xref, "SMask")
                    mask = None
                    if smask[0] == "xref":
                        mask = fitz.Pixmap(self.doc, int(smask[1].split()[0]))
                    if pix.alpha:
                        pix = fitz.Pixmap(pix, 0)
                    pix.shrink(steps)
                    if mask is not None:
                        mask.shrink(steps)
                        if (mask.width, mask.height) != (pix.width, pix.height) or mask.n != 1:
                            continue
                        pix = fitz.Pixmap(pix, mask)
                        data = pix.tobytes("png")
                    else:
                        data = pix.tobytes("jpeg", jpg_quality=quality)
                    old = len(self.doc.xref_stream_raw(xref) or b"")
                    if old and len(data) >= old:
                        continue
                    page.replace_image(xref, stream=data)
                    replaced += 1
                except Exception:  # noqa: BLE001 - an image MuPDF can't decode: keep it as it is
                    continue
        return replaced

    def optimize(self, level="balanced"):
        """Downsample big images and recompress; returns (before, after) sizes."""
        with self.lock:
            before = len(self.doc.tobytes(garbage=0))
            self.snap()
            dpi = {"light": (300, 200, 85), "balanced": (200, 150, 75), "strong": (150, 100, 60)}.get(level, (200, 150, 75))
            # Not Document.rewrite_images(): MuPDF 1.27's pdf_rewrite_images crashes the whole process now and
            # then (access violation, seen on a file with forms + image stamps). Same result, safe calls only.
            self._shrink_images(*dpi)
            try:
                self.doc.subset_fonts()
                self._font_tag = secrets.token_hex(3)
            except Exception:  # noqa: BLE001
                pass
            data = self.doc.tobytes(garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True)
            self.doc.close()
            self._load(data)
            self.changed(None)
            return before, len(data)

    def save_bytes(self):
        with self.lock:
            sec = self.security or {}
            kw = dict(garbage=3, deflate=True, clean=False)
            prot = None if sec.get("remove") else (sec if (sec.get("owner") or sec.get("user")) else self.keep)
            if prot and prot.get("user") is None:
                raise ValueError("This PDF was opened with its owner password, so Washi doesn't know the password that "
                                 "opens it. Saving would lock out everyone who only has that password. Set the "
                                 "passwords under Protect first, then save.")
            if prot:
                kw.update(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=prot.get("user") or "",
                          owner_pw=prot.get("owner") or "", permissions=prot.get("permissions", -1))
            else:
                kw["encryption"] = fitz.PDF_ENCRYPT_NONE
            if self._fonts_added:
                # Whole Windows fonts were embedded by text editing: the file gets only the glyphs used. This is
                # done on a copy - MuPDF caches inserted fonts by file fingerprint, so subsetting the live document
                # would make later edits reuse the shrunken font and print missing letters.
                try:
                    copy = fitz.open("pdf", self.doc.tobytes(garbage=3, deflate=True, encryption=fitz.PDF_ENCRYPT_NONE))
                    copy.subset_fonts()
                    for page in copy:
                        self._fix_spaces(page, copy)
                    data = copy.tobytes(**kw)
                    copy.close()
                    return data
                except Exception:  # noqa: BLE001 - subsetting is only an optimisation
                    pass
            return self.doc.tobytes(**kw)

    def signed(self):
        """True when the PDF carries digital signatures (rewriting the file would break them)."""
        try:
            return self.doc.is_pdf and self.doc.get_sigflags() >= 3
        except Exception:  # noqa: BLE001
            return False

    def save(self, path=None):
        path = path or self.path
        if not path:
            raise ValueError("choose where to save")
        with self.lock:
            data = self.save_bytes()
            backup(path)   # the version this save replaces stays restorable for a while
            tmp = path + ".washi-tmp"
            try:
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
            except OSError:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
            sec = self.security or {}
            if sec.get("remove"):
                self.keep, self.password = None, None
            elif sec:   # later saves keep the new protection
                self.keep = {"user": sec.get("user") or "", "owner": sec.get("owner") or sec.get("user"),
                             "permissions": sec.get("permissions", -1)}
                self.password = sec.get("user") or sec.get("owner")
            self.security = None
            self.path = path
            self.name = os.path.basename(path)
            self.saved_mark = len(self.undo)
            self.dirty = False
            self.converted = False
            return len(data)

    # ------------------------------------------------------------------ export
    def export(self, kind, path, o=None):
        o = o or {}
        with self.lock:
            pages = self._pages_for(o.get("pages"))
            if kind == "txt":
                with open(path, "w", encoding="utf-8") as f:
                    for p in pages:
                        f.write(self.doc[p].get_text("text", sort=True))
                        f.write("\n\f\n")
                return [path]
            if kind == "md":
                with open(path, "w", encoding="utf-8") as f:
                    for p in pages:
                        f.write(self._markdown(self.doc[p]))
                        f.write("\n\n---\n\n")
                return [path]
            if kind == "html":
                with open(path, "w", encoding="utf-8") as f:
                    f.write("<!doctype html><meta charset='utf-8'><title>%s</title><body style='background:#888'>" % html.escape(self.name))
                    for p in pages:
                        f.write("<div style='margin:16px auto;background:#fff;width:fit-content'>")
                        f.write(self.doc[p].get_text("html"))
                        f.write("</div>")
                return [path]
            if kind in ("png", "jpg"):
                dpi = int(o.get("dpi") or 150)
                base, _ = os.path.splitext(path)
                out = []
                for p in pages:
                    pix = self.doc[p].get_pixmap(dpi=dpi, annots=True, alpha=False)
                    name = free_name(f"{base}-{p + 1:03d}.{kind}") if len(pages) > 1 else f"{base}.{kind}"
                    if kind == "jpg":
                        pix.save(name, jpg_quality=int(o.get("quality") or 90))
                    else:
                        pix.save(name)
                    out.append(name)
                return out
            if kind == "docx":
                return [self._export_docx(pages, path)]
            if kind == "pdf":
                data = self.extract_pages(pages) if o.get("pages") else self.save_bytes()
                with open(path, "wb") as f:
                    f.write(data)
                return [path]
        raise ValueError("unknown export format")

    def _export_docx(self, pages, path):
        """pdf2docx when installed (best layout), on a plain copy of the chosen pages in %TEMP%; if it is missing
        or fails on this file, Washi's own exporter (core/docx_export.py)."""
        from .docx_export import export as builtin
        try:
            from pdf2docx import Converter
        except ImportError:   # the shared installer ships without it (OpenCV is too big)
            return builtin(self.doc, pages, path)
        import logging
        import tempfile
        root = logging.getLogger()
        level = root.level
        root.setLevel(logging.WARNING)   # pdf2docx logs every step to the root logger
        fd, tmp = tempfile.mkstemp(suffix=".pdf", prefix="washi-docx-")
        os.close(fd)
        cv = None
        try:
            with open(tmp, "wb") as f:
                f.write(self.extract_pages(pages))
            cv = Converter(tmp)
            cv.convert(path)
            return path
        except Exception:  # noqa: BLE001 - pdf2docx gives up on some files (scans, odd pages)
            if cv is not None:
                try:
                    cv.close()
                except Exception:  # noqa: BLE001
                    pass
                cv = None
            return builtin(self.doc, pages, path)
        finally:
            root.setLevel(level)
            if cv is not None:
                try:
                    cv.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                os.remove(tmp)
            except OSError:
                pass

    @staticmethod
    def _markdown(page):
        d = page.get_text("dict")
        sizes = sorted((s["size"] for b in d["blocks"] if b.get("type") == 0 for l in b["lines"] for s in l["spans"]
                        if s["text"].strip()), reverse=True)
        body = sizes[len(sizes) // 2] if sizes else 11
        out = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            text = " ".join("".join(s["text"] for s in l["spans"]).strip() for l in b["lines"]).strip()
            if not text:
                continue
            size = max((s["size"] for l in b["lines"] for s in l["spans"] if s["text"].strip()), default=body)
            bold = all(s["flags"] & 16 for l in b["lines"] for s in l["spans"] if s["text"].strip())
            if size >= body * 1.6:
                out.append("# " + text)
            elif size >= body * 1.25 or (bold and len(text) < 90):
                out.append("## " + text)
            else:
                out.append(text)
        return "\n\n".join(out)

    def close(self):
        with self.lock:
            self.cache.clear()
            self.undo.clear()
            self.redo.clear()
            try:
                self.doc.close()
            except Exception:  # noqa: BLE001
                pass


class Manager:
    def __init__(self):
        self.docs = {}

    def get(self, did):
        d = self.docs.get(did)
        if not d:
            raise ValueError("that document is no longer open")
        return d

    def find_path(self, path):
        want = os.path.normcase(os.path.abspath(path))
        for d in self.docs.values():
            for p in (d.path, d.source_path):
                if p and os.path.normcase(os.path.abspath(p)) == want:
                    return d
        return None

    def open_path(self, path, password=None):
        same = self.find_path(path)
        if same:
            return same
        with open(path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        ftype = None if ext == "pdf" or data[:5] == b"%PDF-" else ext
        d = Doc(data, path=path, password=password, filetype=ftype)
        self.docs[d.id] = d
        return d

    def open_bytes(self, data, name, password=None):
        ext = os.path.splitext(name)[1].lower().lstrip(".")
        d = Doc(data, name=name, password=password, filetype=None if data[:5] == b"%PDF-" else ext)
        self.docs[d.id] = d   # a dropped file is unchanged: no "save changes?" unless it gets edited
        return d

    def new_blank(self, size="a4", pages=1):
        doc = fitz.open()
        w, h = fitz.paper_size(size) if size in ("a4", "letter", "a3", "a5", "legal") else fitz.paper_size("a4")
        for _ in range(int(pages)):
            doc.new_page(width=w, height=h)
        d = Doc(doc.tobytes(), name="Untitled.pdf")
        d.saved_mark = -1
        d.dirty = True
        self.docs[d.id] = d
        return d

    def from_images(self, paths, name="Images.pdf"):
        out = fitz.open()
        for p in paths:
            img = fitz.open(p)
            pdf = fitz.open("pdf", img.convert_to_pdf())
            out.insert_pdf(pdf)
        if not out.page_count:
            raise ValueError("no images")
        d = Doc(out.tobytes(), name=name)
        d.saved_mark = -1
        d.dirty = True
        self.docs[d.id] = d
        return d

    def merge(self, paths, name="Combined.pdf"):
        out = fitz.open()
        for p in paths:
            src = fitz.open(p)
            if src.needs_pass:
                raise ValueError(f"{os.path.basename(p)} is protected by a password. Open it in Washi, remove the password (Protect > Unlock), save, then combine again.")
            if not src.is_pdf:
                src = fitz.open("pdf", src.convert_to_pdf())
            out.insert_pdf(src)
        d = Doc(out.tobytes(), name=name)
        d.saved_mark = -1
        d.dirty = True
        self.docs[d.id] = d
        return d

    def close(self, did):
        d = self.docs.pop(did, None)
        if d:
            d.close()


def thumbnail_png(path, width=220):
    """First-page preview for the start screen's recent files."""
    try:
        with fitz.open(path) as doc:
            if doc.needs_pass or not doc.page_count:
                return None
            page = doc[0]
            s = width / page.rect.width
            return page.get_pixmap(matrix=fitz.Matrix(s, s), alpha=False).tobytes("png")
    except Exception:  # noqa: BLE001
        return None


def b64png(data):
    return "data:image/png;base64," + base64.b64encode(data).decode()


manager = Manager()
