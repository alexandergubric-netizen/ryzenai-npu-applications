"""Tansu - a smart archiver for Documents\\Archives, with an archiving advisor on the Ryzen AI NPU (FastFlowLM).

Starts a small local web server, opens the window (Edge app mode) and shuts everything down when it closes.
Run with file/folder paths (Explorer's "Send to") to hand them to the running window.
"""
import json
import logging
import os
import shutil
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
from core import advisor, config, engine, hw, rules, store, winutil  # noqa: E402
from core.jobs import batches, jobs  # noqa: E402
from core.llm import npu  # noqa: E402
from core.scan import CAT_LABEL, category, _ext  # noqa: E402
from core.websec import Gate  # noqa: E402

VERSION = "0.9.0"   # beta
PORT = int(os.environ.get("TANSU_PORT") or 52693)
WEB = os.path.join(HERE, "web")


class TansuGate(Gate):
    def on_launch(self, body):   # a second Tansu started by "Send to": its paths go into this window
        paths = [p for p in body.get("args") or [] if isinstance(p, str) and os.path.exists(p)]
        if paths:
            try:
                batches.add(paths)
                bump()
            except ValueError as e:
                log.warning("handed-over paths: %s", e)


# the window gets a session cookie through a one-time launch key; the page itself holds no secret
gate = TansuGate("Tansu", config.DATA_DIR, "X-Tansu", PORT)
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".png": "image/png", ".ico": "image/x-icon", ".svg": "image/svg+xml"}

logging.basicConfig(filename=os.path.join(config.DATA_DIR, "tansu.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tansu")
state = {"models": [], "last_seen": time.time(), "version": 0, "checkup": None}


def bump():
    state["version"] += 1


def suggest_folders(rels):
    """Where loose archives should go: the AI when it is online, the rules otherwise."""
    entries, fallback = [], {}
    idx = store.load()["archives"]
    folders = store.folder_list()
    for rel in rels:
        try:
            _, items = store.contents(rel)
        except Exception:
            items = []
        files = [i for i in items if not i["dir"]]
        sample = [i["name"].rsplit("/", 1)[-1] for i in sorted(files, key=lambda i: -i["size"])[:10]]
        entries.append({"name": rel.rsplit("/", 1)[-1], "rel": rel, "sample": sample})
        cats = {}
        for i in files:
            c = category(_ext(i["name"]))
            cats[c] = cats.get(c, 0) + i["size"] + 1
        top = max(cats, key=cats.get) if cats else "other"
        base = rules.FOLDER_FOR.get(top, "Misc")
        for f in folders:
            if f.split("/")[0].lower() == base.lower():
                base = f.split("/")[0]
                break
        year = time.localtime(idx.get(rel, {}).get("mtime") or time.time()).tm_year
        fallback[rel] = f"{base}/{year}" if top in ("photo", "video", "document") else base
    out = dict(fallback)
    if config.get()["ai"] and npu.state == "online" and entries:
        try:
            ai = advisor.file_archives(entries, store.library_summary())
            for e in entries:
                if e["name"] in ai:
                    out[e["rel"]] = ai[e["name"]]
        except Exception:
            log.error(traceback.format_exc())
    return out


def fix(issue, body):
    kind, rel = issue.get("kind"), issue.get("rel", "")
    root = config.root()
    if kind == "empty_folder":
        p = store.abs_of(rel)
        if os.path.isdir(p) and not os.listdir(p):
            os.rmdir(p)
        return {"ok": True}
    if kind == "duplicate":
        store.recycle(rel)
        return {"ok": True}
    if kind == "loose_archive":
        folder = rules.clean_folder(body.get("folder", ""))
        if not folder:
            raise ValueError("choose a folder")
        return {"ok": True, "rel": store.move(rel, folder)}
    if kind == "similar_folders":
        target = rel
        for other in issue.get("others", []):
            for a in store.overview()["archives"]:
                if a["folder"] == other or a["folder"].startswith(other + "/"):
                    store.move(a["rel"], target + a["folder"][len(other):])
            p = os.path.join(root, *other.split("/"))
            if os.path.isdir(p):
                store.remove_empty_dirs(p)
                for d, dirs, files in os.walk(p, topdown=False):
                    if not os.listdir(d):
                        os.rmdir(d)
        return {"ok": True}
    if kind == "loose_file":
        b = batches.add([store.abs_of(rel)], recycle=True)
        return {"ok": True, "batch": batches.public(b)}
    if kind == "unlisted":
        store.contents(rel, refresh=True)
        return {"ok": True}
    raise ValueError("nothing to fix automatically")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def end_headers(self):
        gate.add_headers(self)
        super().end_headers()

    def _json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path):
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(path)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

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
            return
        except Exception as e:
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

    # ------------------------------------------------------------ routes
    def do_GET(self):
        if not gate.get_allowed(self):
            return
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            path = "/index.html"
        file = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not file.startswith(WEB) or not os.path.isfile(file):
            return self._json({"error": "not found"}, 404)
        self._file(file)

    def do_PUT(self):
        """A dropped file: raw body, X-Session groups one drop, X-Rel is its path inside the drop."""
        if not gate.post_allowed(self, max_body=1 << 40):   # checked before anything is read; files can be huge
            return
        n = int(self.headers.get("Content-Length") or 0)
        sess = "".join(c for c in (self.headers.get("X-Session") or "") if c.isalnum())[:20] or uuid.uuid4().hex[:10]
        rel = urllib.parse.unquote(self.headers.get("X-Rel") or "file")
        parts = [rules.clean_part(p, 200) for p in rel.replace("\\", "/").split("/")]
        parts = [p for p in parts if p]
        if not parts:
            parts = ["file"]
        base = os.path.join(config.DROP, sess)
        dst = os.path.join(base, *parts)
        if not os.path.normpath(dst).startswith(base):
            return self._json({"error": "bad name"}, 400)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        left = n
        with open(dst, "wb") as f:
            while left > 0:
                buf = self.rfile.read(min(left, 4 << 20))
                if not buf:
                    break
                f.write(buf)
                left -= len(buf)
        if left:
            self.close_connection = True
            return self._json({"error": "upload interrupted"}, 400)
        mt = self.headers.get("X-Mtime")
        if mt and mt.isdigit():
            t = int(mt) / 1000
            os.utime(dst, (t, t))
        state["last_seen"] = time.time()
        return self._json({"ok": True, "session": sess})

    def do_POST(self):
        if gate.handle_launch(self):
            return
        if not gate.post_allowed(self, max_body=16 * 2 ** 20):   # checked before the body is read
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "bad request"}, 400)
        path = self.path.split("?")[0]
        state["last_seen"] = time.time()
        try:
            return self._route(path, body)
        except PermissionError as e:
            return self._json({"error": str(e), "password": True}, 401)
        except (ValueError, KeyError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            log.error(traceback.format_exc())
            return self._json({"error": str(e)}, 500)

    def _route(self, path, body):
        s = config.get()
        if path == "/api/state":
            h = hw.check()   # no Ryzen AI NPU: "unsupported", and the plans come from the rules
            return self._json({"llm": npu.state if h["supported"] else "unsupported",
                               "detail": npu.detail if h["supported"] else h["reason"], "tps": npu.tps, "settings": s,
                               "models": state["models"], "version": state["version"], "jobs": jobs.public(),
                               "sendto": winutil.sendto_installed(), "batches": list(batches.items),
                               "app_version": VERSION})
        if path == "/api/batches":
            return self._json([batches.public(b) for b in batches.items.values()])
        if path == "/api/batch":
            return self._json(batches.public(batches.items[body["id"]]))
        if path == "/api/pick":
            kind = "folder" if body.get("kind") == "folder" else "files"
            paths = winutil.pick(kind, "Choose a folder to archive" if kind == "folder" else "Choose files to archive")
            if not paths:
                return self._json(None)
            return self._json(batches.public(batches.add(paths, batch_id=body.get("batch"))))
        if path == "/api/add_paths":
            return self._json(batches.public(batches.add(body.get("paths") or [], batch_id=body.get("batch"))))
        if path == "/api/drop_done":
            sess = "".join(c for c in body.get("session", "") if c.isalnum())
            base = os.path.join(config.DROP, sess)
            if not sess or not os.path.isdir(base):
                raise ValueError("nothing was dropped")
            paths = [os.path.join(base, x) for x in os.listdir(base)]
            b = batches.add(paths, temp=True, batch_id=body.get("batch"))
            b["drop"] = b.get("drop") or base
            if b["drop"] != base:   # a second drop into the same card: keep both folders for cleanup
                b.setdefault("extra_drops", []).append(base)
            return self._json(batches.public(b))
        if path == "/api/batch_remove":
            b = batches.remove_path(body["id"], body["path"])
            return self._json(batches.public(b) if b else None)
        if path == "/api/batch_drop":
            batches.drop(body["id"])
            return self._json({"ok": True})
        if path == "/api/preview":
            b = batches.items[body["id"]]
            layout = body.get("layout") if body.get("layout") in rules.LAYOUTS else "keep"
            return self._json(batches.preview(b, layout))
        if path == "/api/advise":
            b = batches.items.get(body.get("id"))
            if not b:
                raise ValueError("these files are no longer in the list")
            if not s["ai"]:
                raise ValueError("the AI advisor is off (Settings)")
            if not hw.check()["supported"]:
                raise ValueError(hw.check()["reason"])
            if npu.state == "missing":   # no FastFlowLM: waiting would never end
                raise ValueError("FastFlowLM is not installed - get it from github.com/FastFlowLM/FastFlowLM")
            if npu.state != "online":
                npu.ensure()
                return self._stream(iter([{"type": "wait", "text": npu.detail or "Loading the AI model on the NPU…"}]))
            note = (body.get("note") or "").strip() or None
            previous = b["ai"] if note else None

            def events():
                for kind, data in advisor.advise(b["facts"], b["opts"], store.library_summary(), store.folder_list(),
                                                 note, previous):
                    if kind == "plan":
                        if note:
                            data["note"] = note
                        b["ai"] = data
                        yield {"type": "plan", "data": data, "preview": batches.preview(b, data["layout"]),
                               "tps": npu.tps}
                    else:
                        yield {"type": kind, "data": data}
            return self._stream(events())
        if path == "/api/append_candidates":
            folder = rules.clean_folder(body.get("folder", ""))
            return self._json([a["rel"] for a in store.append_candidates(folder, "zip")][:12])
        if path == "/api/archive":
            j = jobs.archive(body["id"], body.get("plan") or {}, body.get("password") or None)
            return self._json(j)
        if path == "/api/jobs":
            return self._json(jobs.public())
        if path == "/api/cancel":
            jobs.cancel(body.get("id", ""))
            return self._json({"ok": True})
        if path == "/api/dismiss":
            jobs.items.pop(body.get("id", ""), None)
            return self._json({"ok": True})
        # ---------------------------------------------------------- library
        if path == "/api/library":
            return self._json(store.overview())
        if path == "/api/folders":
            return self._json(store.folder_list())
        if path == "/api/contents":
            e, items = store.contents(body["rel"], body.get("password") or None, bool(body.get("refresh")))
            return self._json({"meta": e, "items": items})
        if path == "/api/search":
            return self._json(store.search(body.get("q", "")))
        if path == "/api/extract":
            dest = None
            if body.get("choose"):
                p = winutil.pick("folder", "Extract to…", s["extract_dir"])
                if not p:
                    return self._json(None)
                dest = p[0]
            return self._json(jobs.extract(body["rel"], dest, body.get("members") or None, body.get("password") or None))
        if path == "/api/move":
            return self._json({"rel": store.move(body["rel"], body.get("folder"), body.get("name") or None)})
        if path == "/api/recycle":
            store.recycle(body["rel"])
            return self._json({"ok": True})
        if path == "/api/note":
            store.set_meta(body["rel"], note=str(body.get("note", ""))[:500])
            return self._json({"ok": True})
        if path == "/api/reveal":
            if body.get("rel") is not None:
                p = store.abs_of(body["rel"]) if body["rel"] else config.root()
            else:
                p = body.get("path") or config.root()
            if not os.path.exists(p):
                raise ValueError("it is gone")
            winutil.reveal(p)
            return self._json({"ok": True})
        if path == "/api/open":
            os.startfile(store.abs_of(body["rel"]))
            return self._json({"ok": True})
        if path == "/api/verify":
            rel = body["rel"]
            ok, msg = engine.verify(store.abs_of(rel), body.get("password") or None)
            store.set_meta(rel, verified=time.time() if ok else None, broken=None if ok else msg)
            return self._json({"ok": ok, "msg": msg})
        # ---------------------------------------------------------- care
        if path == "/api/checkup":
            return self._json(jobs.checkup(bool(body.get("deep"))))
        if path == "/api/suggest_folders":
            return self._json(suggest_folders(body.get("rels") or []))
        if path == "/api/fix":
            return self._json(fix(body.get("issue") or {}, body))
        if path == "/api/index":
            return self._json(jobs.index())
        # ---------------------------------------------------------- settings
        if path == "/api/settings":
            before = s
            after = config.update(body)
            if after["ai"] and not before["ai"]:
                if hw.check()["supported"]:
                    npu.ensure()
            elif after["ai"] and after["model"] != before["model"]:
                npu.request_switch()          # live: FastFlowLM swaps the model in place
            if after["ai"] and after["pmode"] != before["pmode"]:
                npu.apply_pmode()             # restarts the server unless another app is using it
            if after["root"] != before["root"] or after["skip_junk"] != before["skip_junk"]:
                for b in list(batches.items.values()):
                    batches.rescan(b)
            return self._json(after)
        if path == "/api/pick_root":
            p = winutil.pick("folder", "Where should the Archives library live?", s["root"])
            if p:
                config.update({"root": p[0]})
            return self._json(config.get())
        if path == "/api/pick_extract":
            p = winutil.pick("folder", "Default folder for extracted files", s["extract_dir"])
            if p:
                config.update({"extract_dir": p[0]})
            return self._json(config.get())
        if path == "/api/sendto":
            return self._json({"on": winutil.set_sendto(bool(body.get("on")))})
        if path == "/api/ping":
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)


def open_window(url):
    edge = winutil.edge_exe()
    if edge:
        return subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={os.path.join(config.DATA_DIR, 'window')}",
                                 "--window-size=1180,880", "--no-first-run", "--no-default-browser-check",
                                 "--disable-features=Translate", "--disable-extensions"])
    import webbrowser
    webbrowser.open(url)
    return None


def main():
    paths = [os.path.abspath(a) for a in sys.argv[1:] if not a.startswith("--") and os.path.exists(a)]
    running = gate.find_running(args=paths)
    if running:   # already running: it takes the paths; bring its window forward (or open one)
        if "--no-window" not in sys.argv and not winutil.bring_to_front():
            open_window(f"http://127.0.0.1:{running[0]}/?k={running[1]}")
        return
    shutil.rmtree(config.DROP, ignore_errors=True)
    os.makedirs(config.DROP, exist_ok=True)
    server = gate.bind(ThreadingHTTPServer, Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    gate.publish()
    url = f"http://127.0.0.1:{gate.port}/"
    if paths:
        try:
            batches.add(paths)
        except ValueError as e:
            log.warning("start paths: %s", e)
    if config.get()["ai"] and hw.check()["supported"]:
        npu.ensure()
        threading.Thread(target=lambda: state.__setitem__("models", npu.downloaded_models()), daemon=True).start()
    threading.Thread(target=store.index_all, daemon=True).start()   # so search covers archives made elsewhere
    log.info("Tansu %s started on %s", VERSION, url)

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
        # Edge may hand the window to an already running instance; then wait until the page stops pinging,
        # and never quit in the middle of archiving
        while time.time() - state["last_seen"] < 20 or jobs.busy():
            time.sleep(2)
    log.info("Tansu closing")
    jobs.cancel_all()
    npu.stop()
    server.shutdown()
    gate.withdraw()
    shutil.rmtree(config.DROP, ignore_errors=True)


if __name__ == "__main__":
    main()
