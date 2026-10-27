"""Washi - a PDF editor with a local AI assistant on the Ryzen AI NPU (FastFlowLM).

Starts a small local web server, opens the window (Edge app mode) and shuts down when the window closes.
Run with PDF paths ("Open with", drag onto the shortcut) to open them, also in an already running Washi.

Copyright (c) 2026 Alexander Gubric. MIT License (PyMuPDF, bundled, is AGPL-3.0).
"""
import base64
import json
import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import assistant, assoc, config, docs, hw, winutil  # noqa: E402
from core.llm import npu  # noqa: E402
from core.dpapi import protect, unprotect  # noqa: E402
from core.websec import Gate  # noqa: E402

VERSION = "1.0.3"
PORT = int(os.environ.get("WASHI_PORT") or 52694)
WEB = os.path.join(HERE, "web")
SIGNATURE_FILE = os.path.join(config.DATA_DIR, "signature.bin")   # the remembered signature, DPAPI-encrypted


class WashiGate(Gate):
    def on_launch(self, body):   # a second Washi started with PDFs ("Open with"): open them here
        state["pending"].extend(p for p in body.get("args") or [] if isinstance(p, str) and os.path.isfile(p))


# the window gets a session cookie through a one-time launch key; the page itself holds no secret
gate = WashiGate("Washi", config.DATA_DIR, "X-Washi", PORT)
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".png": "image/png", ".ico": "image/x-icon", ".svg": "image/svg+xml", ".json": "application/json; charset=utf-8",
         ".woff2": "font/woff2"}

# the log stays small: 1 MB, plus two older files
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
    logging.handlers.RotatingFileHandler(os.path.join(config.DATA_DIR, "washi.log"), maxBytes=2 ** 20, backupCount=2,
                                         encoding="utf-8")])
try:   # a crash inside a native library (MuPDF) leaves a Python stack in crash.log instead of nothing
    import faulthandler
    _crash_log = open(os.path.join(config.DATA_DIR, "crash.log"), "a", encoding="utf-8")
    faulthandler.enable(_crash_log)
except OSError:
    pass
log = logging.getLogger("washi")
state = {"last_seen": time.time(), "pending": [], "images": {}}
M = docs.manager


def ai_public():
    h = hw.check()
    s = config.get()
    return {"supported": h["supported"], "reason": h["reason"], "flm": h["flm"], "enabled": s["ai"] and h["supported"],
            "state": npu.state, "detail": npu.detail, "tps": npu.tps, "models": npu.models, "model": npu.model(),
            "pull": npu.pull_pct, "cpu": h["cpu"], "npu": h["npu"], "flm_url": h["flm_url"]}


def folder_writable(folder):
    """Can Washi create files here? (os.access ignores Windows permissions, so really try.)"""
    probe = os.path.join(folder, f".washi-probe-{uuid.uuid4().hex[:8]}")
    try:
        with open(probe, "wb"):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


def save_problem(e, target):
    """Why a save failed, in words, with what to do about it."""
    folder = os.path.dirname(target) or "."
    name = os.path.basename(target)
    if isinstance(e, FileNotFoundError) or not os.path.isdir(folder):
        return f"The folder {folder} no longer exists. Save the PDF somewhere else."
    if getattr(e, "errno", None) == 28 or getattr(e, "winerror", None) == 112:
        return f"The disk is full, so {name} could not be saved. Free some space or save it on another drive."
    if not folder_writable(folder):
        return (f"Windows doesn't let apps change files in {folder} (it is a protected or read-only folder). "
                f"Save a copy somewhere else, for example in Documents.")
    try:
        if os.path.exists(target) and os.stat(target).st_file_attributes & 1:   # FILE_ATTRIBUTE_READONLY
            return f"{name} is marked read-only, so Washi can't replace it. Save a copy under another name."
    except (OSError, AttributeError):
        pass
    if isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32, 33):
        return f"{name} is open in another program, which keeps it locked. Close it there and save again, or save a copy."
    return f"{name} could not be saved: {e.strerror or e}. Try saving a copy somewhere else."


def friendly(e):
    """Error text for the person, not the programmer."""
    if isinstance(e, KeyError):
        return f"Something the app needed was missing ({e.args[0] if e.args else 'value'}). Please try again."
    if isinstance(e, FileNotFoundError):
        return f"The file {os.path.basename(getattr(e, 'filename', '') or '')} was moved or deleted."
    if isinstance(e, PermissionError):   # open() sets errno 13 without a winerror
        where = getattr(e, "filename", "") or ""
        return (f"Windows didn't let Washi write {os.path.basename(where) or 'the file'}. The folder may be protected "
                f"(like Program Files), the file read-only, or open in another program.")
    msg = str(e).strip() or type(e).__name__
    low = msg.lower()
    if any(s in low for s in ("open stream", "cannot open", "format error", "no objects found", "cannot recognize",
                              "broken", "syntax error", "repair")):
        return "the file is damaged or is not a document Washi can read"
    if "code=" in low or "fzerror" in type(e).__name__.lower():   # other MuPDF internals
        return "MuPDF could not process this part of the file. It may be damaged."
    return msg[:1].upper() + msg[1:]


def open_result(d):
    src = d.path or d.source_path
    if src:
        config.add_recent(src, d.doc.page_count, d.meta().get("title", ""))
    return {"doc": d.info()}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def end_headers(self):
        gate.add_headers(self)
        super().end_headers()

    def _send(self, data, ctype, status=200, cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, status=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

    def _stream(self, events):
        """Newline-delimited JSON, flushed per event (chunked transfer)."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def chunk(b):
            self.wfile.write(f"{len(b):x}\r\n".encode() + b + b"\r\n")
            self.wfile.flush()
        try:
            for ev in events:
                chunk((json.dumps(ev, ensure_ascii=False) + "\n").encode())
        except (ConnectionError, OSError):
            npu.cancel.set()   # the window stopped listening
            return
        except Exception as e:  # noqa: BLE001
            log.error(traceback.format_exc())
            try:
                chunk((json.dumps({"type": "error", "text": str(e)}) + "\n").encode())
            except OSError:
                return
        try:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except OSError:
            pass

    # ------------------------------------------------------------------ GET: UI files and page images
    def do_GET(self):
        if not gate.get_allowed(self):   # page images and thumbnails carry the session cookie
            return
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, dict(urllib.parse.parse_qsl(u.query))
        if path.startswith("/api/"):
            try:
                if path == "/api/page":
                    d = M.get(q["d"])
                    fmt = "jpg" if q.get("f") == "jpg" else "png"
                    data = d.render(int(q["p"]), float(q.get("s", 1)), fmt)
                    return self._send(data, "image/jpeg" if fmt == "jpg" else "image/png", cache="private, max-age=600")
                if path == "/api/thumb":
                    p = q.get("path", "")
                    if not any(os.path.normcase(r["path"]) == os.path.normcase(p) for r in config.recent()):
                        return self._json({"error": "forbidden"}, 403)
                    data = docs.thumbnail_png(p)
                    if not data:
                        return self._json({"error": "no preview"}, 404)
                    return self._send(data, "image/png", cache="private, max-age=120")
            except (ValueError, KeyError, IndexError) as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001 - a damaged page: the viewer shows a notice instead
                log.error("render %s: %r", self.path.split("&t=")[0], e)
                try:
                    return self._json({"error": friendly(e)}, 500)
                except OSError:
                    return None
            return self._json({"error": "not found"}, 404)
        if path == "/":
            path = "/index.html"
        file = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not file.startswith(WEB) or not os.path.isfile(file):
            return self._json({"error": "not found"}, 404)
        with open(file, "rb") as f:
            data = f.read()
        if file.endswith("index.html"):
            data = data.replace(b"__TOKEN__", b"1").replace(b"__VERSION__", VERSION.encode())
        self._send(data, TYPES.get(os.path.splitext(file)[1], "application/octet-stream"))

    # ------------------------------------------------------------------ PUT: a file dropped on the window
    def do_PUT(self):
        if not gate.post_allowed(self, max_body=1 << 30):   # checked before anything is read
            return
        n = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(n)
        name = os.path.basename(urllib.parse.unquote(self.headers.get("X-Name") or "Dropped.pdf"))
        purpose = self.headers.get("X-Purpose") or "open"
        try:
            if purpose == "image":
                return self._json(stash_image(data))
            d = M.open_bytes(data, name, password=urllib.parse.unquote(self.headers.get("X-Password") or "") or None)
            return self._json({"doc": d.info()})
        except docs.PasswordRequired:
            return self._json({"password": True, "name": name, "wrong": bool(self.headers.get("X-Password"))})
        except Exception as e:  # noqa: BLE001
            log.error(traceback.format_exc())
            return self._json({"error": f"Washi couldn't open {name}: {friendly(e)}"}, 400)

    # ------------------------------------------------------------------ POST: the API
    def do_POST(self):
        if gate.handle_launch(self):
            return
        if not gate.post_allowed(self, max_body=64 * 2 ** 20):   # checked before the body is read
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        path = self.path.split("?")[0]
        state["last_seen"] = time.time()
        if not isinstance(body, dict):
            return self._json({"error": "bad request"}, 400)
        target = M.docs.get(body.get("d")) if isinstance(body.get("d"), str) else None
        depth = len(target.undo) if target and path not in ("/api/undo", "/api/redo") else None

        def restore():   # an edit that failed half-way must not leave the document half-changed
            if depth is not None and len(target.undo) > depth:
                try:
                    target.rollback(depth)
                except Exception:  # noqa: BLE001
                    log.error(traceback.format_exc())
        try:
            return self._route(path, body)
        except docs.PasswordRequired as e:
            restore()
            return self._json({"error": str(e), "password": True}, 401)
        except (ValueError, KeyError, IndexError, TypeError, FileNotFoundError) as e:
            restore()
            log.warning("%s: %r", path, e)
            return self._json({"error": friendly(e)}, 400)
        except Exception as e:  # noqa: BLE001
            restore()
            log.error(traceback.format_exc())
            return self._json({"error": friendly(e)}, 500)

    def _route(self, path, b):  # noqa: C901 - a flat routing table reads best
        s = config.get()
        if path.startswith("/api/ai/"):
            return self._ai(path[8:], b)
        d = M.get(b["d"]) if b.get("d") else None
        ok = lambda **extra: self._json({"doc": d.info(), **extra})  # noqa: E731

        # ---------------------------------------------------------------- app
        if path == "/api/state":
            pending, state["pending"] = state["pending"], []
            return self._json({"settings": s, "ai": ai_public(), "pending": pending, "version": VERSION,
                               "open": [x.info() for x in M.docs.values()] if b.get("full") else None})
        if path == "/api/ping":
            pending, state["pending"] = state["pending"], []
            return self._json({"pending": pending, "ai": ai_public()})
        if path == "/api/settings":
            before = s
            after = config.update(b.get("set") or {})
            if after["ai"] and not before["ai"] and hw.check()["supported"]:
                npu.ensure()
            if after["model"] != before["model"] and after["ai"] and npu.state == "online":
                threading.Thread(target=npu.warmup, args=(after["model"],), daemon=True).start()
            return self._json({"settings": after, "ai": ai_public()})
        if path == "/api/recent":
            return self._json(config.recent())
        if path == "/api/forget":
            config.forget_recent(b["path"])
            return self._json(config.recent())
        if path == "/api/signature_saved":   # the remembered signature lives encrypted with Windows (DPAPI)
            try:
                with open(SIGNATURE_FILE, "rb") as f:
                    return self._json({"png": unprotect(f.read()).decode("ascii")})
            except (OSError, ValueError):
                return self._json({"png": None})
        if path == "/api/signature_remember":
            png = b.get("png")
            if png:
                if not (isinstance(png, str) and png.startswith("data:image/") and len(png) < 8 * 2 ** 20):
                    raise ValueError("that is not a signature image")
                with open(SIGNATURE_FILE, "wb") as f:
                    f.write(protect(png.encode("ascii")))
            else:
                try:
                    os.remove(SIGNATURE_FILE)
                except OSError:
                    pass
            return self._json({"ok": True})
        if path == "/api/reveal":
            winutil.reveal(b["path"])
            return self._json({"ok": True})
        if path == "/api/open_url":
            url = b.get("url", "")
            if url.startswith(("https://", "http://", "mailto:")):
                os.startfile(url)  # noqa: S606 - links the person clicked in the document / about box
            return self._json({"ok": True})
        if path == "/api/help_search":
            return self._json(assistant.search_guide(b.get("q", ""), 8))
        if path == "/api/default_app":
            return self._json(default_app(bool(b.get("make"))))

        # ---------------------------------------------------------------- open / new
        if path == "/api/open":
            paths = [b["path"]] if b.get("path") else winutil.pick_open("openable", "Open PDF", self._dir(), multi=True)
            out = []
            for p in paths:
                try:
                    out.append(open_result(M.open_path(p, b.get("password") or None)))
                except docs.PasswordRequired:
                    out.append({"password": True, "path": p, "name": os.path.basename(p), "wrong": bool(b.get("password"))})
                except FileNotFoundError:
                    config.forget_recent(p)
                    out.append({"error": f"{os.path.basename(p)} was moved or deleted"})
                except Exception as e:  # noqa: BLE001
                    log.error(traceback.format_exc())
                    out.append({"error": f"Washi couldn't open {os.path.basename(p)}: {friendly(e)}"})
            return self._json(out)
        if path == "/api/new":
            return self._json({"doc": M.new_blank(b.get("size", "a4"), int(b.get("pages") or 1)).info()})
        if path == "/api/from_images":
            paths = winutil.pick_open("image", "Choose images for the new PDF", self._dir())
            if not paths:
                return self._json(None)
            return self._json({"doc": M.from_images(paths).info()})
        if path == "/api/merge":
            paths = winutil.pick_open("openable", "Choose the files to combine (in order)", self._dir())
            if not paths:
                return self._json(None)
            return self._json({"doc": M.merge(paths).info()})
        if path == "/api/close":
            M.close(b["d"])
            return self._json({"ok": True})
        if path == "/api/info":
            return ok()

        # ---------------------------------------------------------------- reading
        if path == "/api/pageinfo":
            p = int(b["p"])
            return self._json({"text": d.text_layer(p), "links": d.links(p), "annots": d.annots(p),
                               "widgets": d.widgets(p) if d.doc.is_form_pdf else []})
        if path == "/api/search":
            return self._json(d.search(b.get("q", ""), bool(b.get("case")), bool(b.get("whole"))))
        if path == "/api/outline":
            return self._json(d.outline())
        if path == "/api/outline_set":
            d.set_outline(b.get("items") or [])
            return ok(outline=d.outline())
        if path == "/api/annots":
            return self._json(d.annots(b.get("p")))
        if path == "/api/annot_at":
            return self._json(d.annot_at(int(b["p"]), b["pt"]))
        if path == "/api/line_at":
            return self._json(d.line_at(int(b["p"]), b["pt"]))
        if path == "/api/selection_text":
            return self._json({"text": d.selection_text(int(b["p"]), b.get("rects") or [])})
        if path == "/api/attachments":
            return self._json(d.attachments())
        if path == "/api/text_all":
            return self._json({"pages": d.all_text()})

        # ---------------------------------------------------------------- comments & markup
        if path == "/api/annot_add":
            a = d.add_annot(int(b["p"]), b["kind"], b.get("o") or {}, s["author"])
            return ok(annot=a)
        if path == "/api/annot_update":
            return ok(annot=d.update_annot(int(b["p"]), int(b["id"]), b.get("o") or {}))
        if path == "/api/annot_delete":
            d.delete_annot(int(b["p"]), int(b["id"]))
            return ok()
        if path == "/api/stamp_preview":
            pix, ratio = docs.Doc.stamp_png(b.get("label") or "Approved", b.get("color"), s["author"] if b.get("sign", True) else "")
            return self._json({"img": docs.b64png(pix.tobytes("png")), "ratio": ratio})
        if path == "/api/signature_add":
            png = base64.b64decode(b["png"].split(",", 1)[1])
            return ok(annot=d.add_signature(int(b["p"]), b["rect"], png))
        if path == "/api/redact_apply":
            n = d.apply_redactions()
            return ok(pages=n)
        if path == "/api/flatten":
            d.flatten()
            return ok()

        # ---------------------------------------------------------------- content editing
        if path == "/api/edit_line":
            d.edit_line(int(b["p"]), b)
            return ok()
        if path == "/api/add_text":
            d.add_text(int(b["p"]), b)
            return ok()
        if path == "/api/whiteout":
            d.whiteout(int(b["p"]), b["rect"], b.get("color") or "#ffffff")
            return ok()
        if path == "/api/pick_image":
            paths = winutil.pick_open("image", "Choose an image", self._dir(), multi=False)
            if not paths:
                return self._json(None)
            with open(paths[0], "rb") as f:
                return self._json(stash_image(f.read()))
        if path == "/api/image_add":
            img = state["images"].get(b["img"])
            if not img:
                raise ValueError("choose the image again")
            d.add_image(int(b["p"]), b["rect"], data=img)
            return ok()
        if path == "/api/link_add":
            d.add_link(int(b["p"]), b["rect"], uri=b.get("uri"), page_to=b.get("page"))
            return ok()
        if path == "/api/field_set":
            d.set_field(int(b["p"]), int(b["xref"]), b.get("value"))
            return ok()
        if path == "/api/field_add":
            d.add_field(int(b["p"]), b.get("kind", "text"), b["rect"], b.get("name") or None)
            return ok()

        # ---------------------------------------------------------------- pages
        pnos = [int(x) for x in b["pages"]] if isinstance(b.get("pages"), list) else []
        if path == "/api/pages_rotate":
            d.rotate_pages(pnos, int(b.get("angle", 90)))
            return ok()
        if path == "/api/pages_delete":
            d.delete_pages(pnos)
            return ok()
        if path == "/api/pages_blank":
            d.insert_blank(int(b.get("at", d.doc.page_count)), count=int(b.get("count") or 1))
            return ok()
        if path == "/api/pages_duplicate":
            d.duplicate_pages(pnos)
            return ok()
        if path == "/api/pages_move":
            d.move_pages(pnos, int(b["to"]))
            return ok()
        if path == "/api/pages_insert_file":
            paths = winutil.pick_open("openable", "Insert pages from", self._dir())
            if not paths:
                return self._json(None)
            at = int(b.get("at", d.doc.page_count))
            added = 0
            for p in paths:
                added += d.insert_file(p, at + added)
            return ok(added=added)
        if path == "/api/pages_extract":
            target = winutil.pick_save("pdf", "Save the pages as", self._dir(d),
                                       f"{os.path.splitext(d.name)[0]} (pages).pdf")
            if not target:
                return self._json(None)
            with open(target, "wb") as f:
                f.write(d.extract_pages(pnos))
            if b.get("remove"):
                d.delete_pages(pnos)
            return ok(saved=target)
        if path == "/api/split":
            return self._json(split(d, b))
        if path == "/api/crop":
            d.crop(pnos or list(range(d.doc.page_count)), b["rect"], int(b["p"]))
            return ok()
        if path == "/api/uncrop":
            d.uncrop(pnos or list(range(d.doc.page_count)))
            return ok()
        if path == "/api/watermark":
            d.watermark(b)
            return ok()
        if path == "/api/header_footer":
            d.header_footer(b)
            return ok()

        # ---------------------------------------------------------------- document
        if path == "/api/undo":
            d.do_undo()
            return ok()
        if path == "/api/redo":
            d.do_redo()
            return ok()
        if path == "/api/reflow":
            d.reflow(float(b.get("size") or 11))
            config.update({"ebook_fontsize": float(d.ebook_fontsize or 11)})
            return ok()
        if path == "/api/meta_set":
            d.set_meta(b.get("meta") or {})
            return ok()
        if path == "/api/protect":
            d.protect(b)
            return ok()
        if path == "/api/optimize":
            before, after = d.optimize(b.get("level", "balanced"))
            return ok(before=before, after=after)
        if path == "/api/attachment_add":
            paths = winutil.pick_open("any", "Attach a file", self._dir(d), multi=False)
            if not paths:
                return self._json(None)
            d.add_attachment(paths[0])
            return ok(items=d.attachments())
        if path == "/api/attachment_save":
            target = winutil.pick_save("any", "Save the attachment as", self._dir(d), b["name"])
            if not target:
                return self._json(None)
            with open(target, "wb") as f:
                f.write(d.get_attachment(b["name"]))
            return self._json({"saved": target})
        if path == "/api/attachment_delete":
            d.del_attachment(b["name"])
            return ok(items=d.attachments())
        if path == "/api/save":
            if not d.path or b.get("as"):
                start = winutil.documents() if b.get("elsewhere") else self._dir(d)
                name = os.path.splitext(d.name)[0] + ".pdf"
                target = winutil.pick_save("pdf", "Save PDF as", start, name)
                if not target:
                    return self._json(None)
            else:
                target = d.path
            if target == d.path and not b.get("as") and d.signed():
                return self._json({"error": "This PDF is digitally signed. Saving changes into it would make the signature "
                                            "invalid, so Washi keeps the original as it is. Use Save a copy as.",
                                   "save_as": True}, 409)
            try:
                size = d.save(target)
            except OSError as e:
                log.warning("save %s: %r", target, e)
                return self._json({"error": save_problem(e, target), "save_as": True}, 409)
            config.add_recent(target, d.doc.page_count, d.meta().get("title", ""))
            return ok(saved=target, size=size)
        if path == "/api/export":
            kind = b.get("kind", "txt")
            ext = {"png": "png", "jpg": "jpg", "txt": "txt", "md": "md", "html": "html", "docx": "docx", "pdf": "pdf"}[kind]
            target = winutil.pick_save(ext, "Export as", self._dir(d), f"{os.path.splitext(d.name)[0]}.{ext}")
            if not target:
                return self._json(None)
            files = d.export(kind, target, b)
            return self._json({"files": files})
        if path == "/api/print_file":
            # a temporary copy for Windows' own PDF printing route
            tmp = os.path.join(config.DATA_DIR, "print", f"{uuid.uuid4().hex[:6]}-{d.name}")
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            with open(tmp, "wb") as f:
                f.write(d.save_bytes())
            return self._json({"path": tmp})
        return self._json({"error": "not found"}, 404)

    # ------------------------------------------------------------------ AI
    def _ai(self, name, b):
        if name == "state":
            return self._json(ai_public())
        if name == "cancel":
            npu.cancel.set()
            return self._json({"ok": True})
        if not hw.check()["supported"]:
            raise ValueError("Local AI isn't available on this PC: " + hw.check()["reason"])
        if name == "start":
            npu.ensure()
            return self._json(ai_public())
        if name == "pull":
            npu.pull(b.get("model") or "qwen3:4b")
            return self._json(ai_public())
        if not config.get()["ai"]:
            raise ValueError("Local AI is turned off in Settings")
        if npu.state != "online":
            npu.ensure()
            return self._stream(iter([{"type": "wait", "text": npu.detail or "Loading the AI model onto the NPU…"}]))
        if name == "summary":
            d = M.get(b["d"])
            return self._stream(assistant.summarize(d.all_text(), d.name, b.get("style", "bullets")))
        if name == "ask":
            d = M.get(b["d"])
            return self._stream(assistant.ask(d.all_text(), d.name, b["q"], b.get("history")))
        if name == "selection":
            return self._stream(assistant.on_selection(b.get("text", ""), b.get("mode", "explain"), b.get("lang")))
        if name == "guide":
            return self._stream(assistant.ask_guide(b["q"], b.get("history"), b.get("context")))
        return self._json({"error": "not found"}, 404)

    @staticmethod
    def _dir(d=None):
        if d and d.path:
            return os.path.dirname(d.path)
        r = config.recent()
        return os.path.dirname(r[0]["path"]) if r else winutil.documents()


def default_app(make=False):
    """Is Washi registered / the default for PDFs? With make=True: register this copy's Washi.exe (if needed)
    and open Windows' Default apps page, where the person confirms - Windows doesn't let apps set it silently."""
    exe = assoc.find_exe(HERE)
    out = {"exe": exe, "registered": bool(exe) and os.path.normcase(assoc.registered_exe() or "") == os.path.normcase(exe),
           "default": assoc.is_default()}
    if make:
        if not exe:
            raise ValueError("Washi.exe is missing. Reinstall Washi, or when running from source run: python make_launcher.py")
        if not out["registered"]:
            assoc.register(exe, os.path.join(HERE, "washi.ico"))
            out["registered"] = True
        out["opened"] = assoc.open_default_settings()
    return out


def stash_image(data):
    key = uuid.uuid4().hex[:10]
    try:
        w, h = docs.Doc.image_size(data)
    except Exception as e:  # noqa: BLE001
        raise ValueError("that file is not an image Washi can read") from e
    state["images"][key] = data
    while len(state["images"]) > 12:
        state["images"].pop(next(iter(state["images"])))
    mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg" if data[:2] == b"\xff\xd8" else "image/*"
    preview = f"data:{mime};base64," + base64.b64encode(data).decode() if len(data) < 6 * 2 ** 20 and mime != "image/*" else None
    return {"img": key, "w": w, "h": h, "preview": preview}


def split(d, b):
    """Split into several PDFs: every N pages, by bookmarks (top level) or by explicit ranges."""
    n = d.doc.page_count
    mode = b.get("mode", "every")
    groups = []
    if mode == "every":
        k = max(1, int(b.get("n") or 1))
        groups = [list(range(i, min(i + k, n))) for i in range(0, n, k)]
    elif mode == "bookmarks":
        starts = sorted({o["p"] for o in d.outline() if o["lvl"] == 1 and 0 <= o["p"] < n} | {0})
        groups = [list(range(a, (starts[i + 1] if i + 1 < len(starts) else n))) for i, a in enumerate(starts)]
    else:
        for part in (b.get("ranges") or "").split(";"):
            if part.strip():
                groups.append(docs.parse_ranges(part, n))
    groups = [g for g in groups if g]
    if len(groups) < 2 and mode != "ranges":
        raise ValueError("that would make just one file")
    base = winutil.pick_save("pdf", "Choose the folder and base name for the parts", Handler._dir(d),
                             f"{os.path.splitext(d.name)[0]}.pdf")
    if not base:
        return None
    stem = os.path.splitext(base)[0]
    files = []
    for i, g in enumerate(groups, 1):
        out = docs.free_name(f"{stem} - part {i}.pdf")   # never overwrite a file that is already there
        with open(out, "wb") as f:
            f.write(d.extract_pages(g))
        files.append(out)
    return {"files": files}


def open_window(url):
    edge = winutil.edge_exe()
    if edge:
        return subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={os.path.join(config.DATA_DIR, 'window')}",
                                 "--window-size=1360,900", "--no-first-run", "--no-default-browser-check",
                                 "--disable-features=Translate", "--disable-extensions"])
    import webbrowser
    webbrowser.open(url)
    return None


def main():
    paths = [os.path.abspath(a) for a in sys.argv[1:] if not a.startswith("--") and os.path.isfile(a)]
    running = gate.find_running(args=paths)
    if running:   # already running: it takes the files; bring its window forward (or open one)
        if "--no-window" not in sys.argv and not winutil.bring_to_front():
            open_window(f"http://127.0.0.1:{running[0]}/?k={running[1]}")
        return
    server = gate.bind(ThreadingHTTPServer, Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    gate.publish()
    url = f"http://127.0.0.1:{gate.port}/"
    state["pending"].extend(paths)
    if config.get()["ai"] and hw.check()["supported"]:
        npu.ensure()
    log.info("Washi %s started on %s", VERSION, url)

    if "--no-window" in sys.argv:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        win = open_window(gate.launch_url())
        if win:
            win.wait()
        # Edge may hand the window to an already running instance; wait until the page stops pinging
        while time.time() - state["last_seen"] < 20:
            time.sleep(2)
    log.info("Washi closing")
    npu.cancel.set()
    npu.stop()
    server.shutdown()
    gate.withdraw()
    import shutil
    shutil.rmtree(os.path.join(config.DATA_DIR, "print"), ignore_errors=True)


if __name__ == "__main__":
    main()
