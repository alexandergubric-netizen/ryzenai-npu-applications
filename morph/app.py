"""Morph - a local universal file converter with an NPU format advisor (FastFlowLM).

Starts a small local web server, opens the window (Edge app mode) and shuts everything down when it closes.
"""
import json
import logging
import logging.handlers
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
# NumPy's OpenBLAS reserves ~30 MB of memory per CPU thread at import (~480 MB on a 16-thread PC). Morph's table
# conversions don't need parallel linear algebra, so two threads keep that reservation at ~100 MB.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
from core import advisor, config, enabler, hw, router, winutil  # noqa: E402
from core.formats import CATEGORIES, FORMATS  # noqa: E402
from core.inbox import inbox  # noqa: E402
from core.jobs import jobs  # noqa: E402
from core.llm import npu  # noqa: E402
from core.websec import Gate  # noqa: E402

VERSION = "1.0.1"
PORT = int(os.environ.get("MORPH_PORT") or 52691)   # MORPH_PORT: tests run a second copy elsewhere
WEB = os.path.join(HERE, "web")
# the window gets a session cookie through a one-time launch key; the page itself holds no secret
gate = Gate("Morph", config.DATA_DIR, "X-Morph", PORT)
MAX_UPLOAD = 20 * 2 ** 30          # one dropped file
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".png": "image/png", ".ico": "image/x-icon", ".svg": "image/svg+xml", ".webp": "image/webp",
         ".jpg": "image/jpeg"}

# the log stays small: 1 MB, plus two older files
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
    logging.handlers.RotatingFileHandler(os.path.join(config.DATA_DIR, "morph.log"), maxBytes=2 ** 20, backupCount=2,
                                         encoding="utf-8")])
log = logging.getLogger("morph")
state = {"models": [], "last_seen": time.time(), "ai": {"ready": False, "supported": False, "checked": False}}


def refresh_ai(start=True):
    """Is the AI advisor usable here (Ryzen AI NPU + FastFlowLM + model)? Starts FastFlowLM when it is and wanted.
    On every other PC Morph runs as a converter only."""
    st = enabler.status()
    state["ai"] = {**st, "checked": True}
    state["models"] = st["models"]
    if start and st["ready"] and config.get()["ai"] and npu.state not in ("online", "starting"):
        npu.ensure()
    return state["ai"]


def catalog():
    """Every format with whether Morph can read and/or write it right now."""
    E = router.edges()
    reads = set().union(*(e.srcs for e in E))
    writes = set().union(*(e.dsts for e in E))
    out = {c: [] for c in CATEGORIES}
    for fid, f in FORMATS.items():
        out[f["cat"]].append({"id": fid, "name": f["name"], "ext": f["ext"], "read": fid in reads,
                              "write": fid in writes, "up": f["up"], "down": f["down"]})
    return [{"cat": c, "label": CATEGORIES[c], "formats": v} for c, v in out.items()]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def end_headers(self):
        gate.add_headers(self)
        super().end_headers()

    def _json(self, obj, status=200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path, cache=False):
        with open(path, "rb") as f:
            data = f.read()
        if path.endswith("index.html"):
            data = data.replace(b"__TOKEN__", b"1")   # the session cookie authenticates; the header only marks app calls
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(path)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
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
                chunk((json.dumps(ev) + "\n").encode())
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
        url = urllib.parse.urlparse(self.path)
        path = url.path
        if path.startswith("/api/thumb/"):   # <img> requests carry the session cookie
            th = inbox.thumbnail(path.rsplit("/", 1)[-1])
            if not th:
                return self._json({"error": "none"}, 404)
            return self._file(th, cache=True)
        if path == "/":
            path = "/index.html"
        file = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not file.startswith(WEB) or not os.path.isfile(file):
            return self._json({"error": "not found"}, 404)
        self._file(file)

    def do_PUT(self):
        """Upload of a dropped file: raw body, name in X-Name."""
        if not gate.post_allowed(self, max_body=MAX_UPLOAD):   # checked before anything is read
            return
        n = int(self.headers.get("Content-Length") or 0)
        if n > shutil.disk_usage(config.INBOX).free - 2 ** 30:
            self.close_connection = True
            return self._json({"error": "Not enough free disk space for this file"}, 507)
        name = os.path.basename(urllib.parse.unquote(self.headers.get("X-Name") or "file")) or "file"
        folder = os.path.join(config.INBOX, uuid.uuid4().hex[:10])
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, name)
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
        state["last_seen"] = time.time()
        try:
            return self._json(inbox.public(inbox.add(dst, name, temp=True)))
        except Exception as e:
            log.error(traceback.format_exc())
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        if gate.handle_launch(self):
            return
        if not gate.post_allowed(self):   # checked before the body is read; refused connections are closed
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        state["last_seen"] = time.time()
        path = self.path.split("?")[0]
        try:
            return self._route(path, body)
        except (ValueError, KeyError) as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:
            log.error(traceback.format_exc())
            return self._json({"error": str(e)}, 500)

    def _route(self, path, body):
        if path == "/api/state":
            ai = state["ai"]
            return self._json({"llm": npu.state, "detail": npu.detail, "tps": npu.tps, "settings": config.get(),
                               "models": state["models"], "engines": router.engines(), "version": VERSION,
                               "ai": {"ready": ai["ready"], "supported": ai["supported"], "checked": ai["checked"],
                                      "reason": ai.get("reason", ""), "flm": ai.get("flm", False),
                                      "busy": bool(enabler.state["task"])}})
        if path == "/api/ai/status":   # the NPU enabler card in Settings
            if enabler.state["task"]:
                return self._json({**state["ai"], "job": dict(enabler.state)})
            return self._json(refresh_ai())
        if path == "/api/ai/install_flm":
            if not hw.check()["supported"]:
                return self._json({"error": "This PC has no supported Ryzen AI NPU"}, 400)
            enabler.install_flm()
            threading.Thread(target=_after_enabler, daemon=True).start()
            return self._json({"ok": True})
        if path == "/api/ai/pull":
            enabler.pull_model()
            threading.Thread(target=_after_enabler, daemon=True).start()
            return self._json({"ok": True})
        if path == "/api/ai/open_flm_site":
            os.startfile(hw.FLM_URL)  # noqa: S606 - fixed URL
            return self._json({"ok": True})
        if path == "/api/files":  # after a window reload
            return self._json([inbox.public(e) for e in inbox.items.values()])
        if path == "/api/catalog":
            return self._json(catalog())
        if path == "/api/pick":
            paths = winutil.pick_files()
            out = []
            for p in paths:
                if os.path.isfile(p):
                    out.append(inbox.public(inbox.add(os.path.normpath(p))))
            return self._json(out)
        if path == "/api/add_paths":
            out = [inbox.public(inbox.add(os.path.normpath(p))) for p in body.get("paths", []) if os.path.isfile(p)]
            return self._json(out)
        if path == "/api/pickdir":
            p = winutil.pick_folder("Choose where converted files go")
            if p:
                config.update({"output_dir": os.path.normpath(p)})
            return self._json(config.get())
        if path == "/api/remove":
            if body.get("id") not in inbox.items:   # only files Morph knows, never a made-up name
                return self._json({"error": "unknown file"}, 404)
            inbox.remove(body["id"])
            return self._json({"ok": True})
        if path == "/api/convert":
            return self._json(jobs.submit(body["id"], body["target"], body.get("opts") or {}))
        if path == "/api/merge":
            return self._json(jobs.merge(body.get("ids") or [], body.get("opts") or {}))
        if path == "/api/jobs":
            return self._json(jobs.public())
        if path == "/api/cancel":
            jobs.cancel(body.get("id", ""))
            return self._json({"ok": True})
        if path in ("/api/reveal", "/api/open"):
            job = jobs.items.get(body.get("id", ""))
            target = job and job.get("out")
            if not target and path == "/api/reveal" and body.get("folder"):
                target = config.get()["output_dir"]
                os.makedirs(target, exist_ok=True)
                os.startfile(target)
                return self._json({"ok": True})
            if not target or not os.path.exists(target):
                return self._json({"error": "file is gone"}, 404)
            if path == "/api/open":
                os.startfile(target)
            else:
                subprocess.Popen(["explorer", "/select,", target])
            return self._json({"ok": True})
        if path == "/api/advise":
            e = inbox.get(body.get("id", ""))
            if not e or not e.get("targets"):
                return self._json({"error": "nothing to advise on"}, 400)
            if not state["ai"]["ready"]:
                return self._stream(iter([{"type": "error", "text": state["ai"].get("reason") or
                                           "The AI advisor isn't set up on this PC - see Settings"}]))
            if npu.state != "online":
                npu.ensure()
                return self._stream(iter([{"type": "wait", "text": npu.detail or "Loading the AI model on the NPU…"}]))
            return self._stream({"type": k, "data": d}
                                for k, d in advisor.advise(e, body.get("q"), body.get("history")))
        if path == "/api/settings":
            before = config.get()
            after = config.update(body)
            if after["model"] != before["model"] and after["ai"] and state["ai"]["ready"]:
                threading.Thread(target=npu.warmup, args=(after["model"],), daemon=True).start()
            if after["ai"] and not before["ai"] and state["ai"]["ready"]:
                npu.ensure()
            return self._json(after)
        if path == "/api/install":
            if body.get("what") == "libreoffice":
                subprocess.Popen('start "Installing LibreOffice" cmd /k winget install -e --id '
                                 'TheDocumentFoundation.LibreOffice --accept-package-agreements', shell=True)
            return self._json({"ok": True})
        if path == "/api/refresh":
            for e in list(inbox.items.values()):
                inbox.refresh_targets(e)
            return self._json([inbox.public(e) for e in inbox.items.values()])
        if path == "/api/ping":
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)


def _after_enabler():
    """When an enabler step finishes, re-check and start the AI if everything is in place now."""
    time.sleep(1)
    while enabler.state["task"]:
        time.sleep(1)
    refresh_ai()


def open_window(url):
    from core.docs import edge_exe
    edge = edge_exe()
    if edge:
        return subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={os.path.join(config.DATA_DIR, 'window')}",
                                 "--window-size=1040,860", "--no-first-run", "--no-default-browser-check",
                                 "--disable-features=Translate", "--disable-extensions"])
    import webbrowser
    webbrowser.open(url)
    return None


def main():
    running = gate.find_running()
    if running:   # this user already runs Morph - just show another window
        if "--no-window" not in sys.argv:
            open_window(f"http://127.0.0.1:{running[0]}/?k={running[1]}")
        return
    inbox.clear_temp()
    server = gate.bind(ThreadingHTTPServer, Handler)
    server.daemon_threads = True
    gate.publish()
    url = f"http://127.0.0.1:{gate.port}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=refresh_ai, daemon=True).start()   # NPU + FastFlowLM check; starts the AI if all is there
    log.info("Morph %s started on %s", VERSION, url)

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
        # and never quit in the middle of a conversion
        while time.time() - state["last_seen"] < 20 or any(j["status"] in ("running", "queued") for j in jobs.items.values()):
            time.sleep(2)
    log.info("Morph closing")
    gate.withdraw()
    jobs.cancel_all()
    npu.stop()
    server.shutdown()
    inbox.clear_temp()


if __name__ == "__main__":
    main()
