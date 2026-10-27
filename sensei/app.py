"""Sensei - an offline PowerShell helper running on the Ryzen AI NPU through FastFlowLM.

Starts a small local web server, opens the window (Edge app mode) and shuts everything down when it closes.
"""
import hashlib
import json
import logging
import logging.handlers
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from core import assistant, config  # noqa: E402
from core.llm import npu  # noqa: E402
from core.recipes import library  # noqa: E402
from core.shell import CATALOG, shell  # noqa: E402
from core.websec import Gate  # noqa: E402

VERSION = "2.0.2"
PORT = int(os.environ.get("SENSEI_PORT") or 52690)   # SENSEI_PORT: tests run a second copy elsewhere
WEB = os.path.join(HERE, "web")
# the window gets a session cookie through a one-time launch key; the page itself holds no secret
gate = Gate("Sensei", config.DATA_DIR, "X-Sensei", PORT)
TICKET_TTL = 300
tickets = {}          # one-time run tickets from /api/verify: id -> (sha256 of the code, risk, expiry)
tickets_lock = threading.Lock()
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".png": "image/png", ".ico": "image/x-icon", ".svg": "image/svg+xml"}

# the log stays small: 1 MB, plus two older files
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
    logging.handlers.RotatingFileHandler(os.path.join(config.DATA_DIR, "sensei.log"), maxBytes=2 ** 20, backupCount=2,
                                         encoding="utf-8")])
log = logging.getLogger("sensei")
state = {"models": [], "last_seen": time.time()}


def fix_code(code):
    """Small fixes before running: a bare .msc/.cpl name cannot run inside a pipeline."""
    if re.fullmatch(r"\s*[\w\-]+\.(msc|cpl)\s*", code, re.I):
        return "Start-Process " + code.strip()
    return code


def _digest(code):
    return hashlib.sha256(code.encode("utf-8", "replace")).hexdigest()


def issue_ticket(code, risk):
    """A one-time permission to run exactly this code, handed out with its check result."""
    tid = secrets.token_urlsafe(18)
    now = time.time()
    with tickets_lock:
        for k in [k for k, v in tickets.items() if v[2] < now]:
            del tickets[k]
        tickets[tid] = (_digest(code), risk, now + TICKET_TTL)
    return tid


def gate_code(code, body):
    """The server's own check before anything runs (the page's warnings are only a convenience).

    Returns None when the code may run, else the reason it may not. Read-only code runs freely; anything else needs
    the ticket the page got with its check of this exact code, and destructive code also needs confirmed=true
    (the page sends it only after the second click)."""
    check = shell.verify(code)
    risk = check.get("risk") or "caution"
    if (check.get("syntax") or []) and risk == "safe":
        risk = "caution"
    if risk == "safe":
        return None
    with tickets_lock:
        t = tickets.pop(str(body.get("ticket") or ""), None)
    if not t or t[0] != _digest(code) or t[2] < time.time():
        return "This command was not checked before running. Check it and press Run again."
    if risk == "danger" and body.get("confirmed") is not True:
        return "This command deletes or changes things and needs your confirmation (click Run twice)."
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def end_headers(self):
        gate.add_headers(self)
        super().end_headers()

    # ------------------------------------------------------------ helpers
    def _json(self, obj, status=200):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

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
            batch, last = [], time.time()
            for ev in events:
                batch.append(json.dumps(ev))
                if ev.get("type") != "out" or len(batch) > 200 or time.time() - last > 0.05:
                    chunk(("\n".join(batch) + "\n").encode())
                    batch, last = [], time.time()
            if batch:
                chunk(("\n".join(batch) + "\n").encode())
        except (ConnectionError, OSError):
            return
        except Exception as e:  # report the failure in the UI instead of a broken stream
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
        path = self.path.split("?")[0]
        if path == "/":
            path = "/index.html"
        file = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not file.startswith(WEB) or not os.path.isfile(file):
            return self._json({"error": "not found"}, 404)
        with open(file, "rb") as f:
            data = f.read()
        if file.endswith("index.html"):
            data = data.replace(b"__TOKEN__", b"1")   # the session cookie authenticates; the header only marks app calls
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(file)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if gate.handle_launch(self):
            return
        if not gate.post_allowed(self):   # checked before the body is read; refused connections are closed
            return
        try:
            body = self._body()   # always consume the body, or the next request on this connection breaks
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        state["last_seen"] = time.time()
        path = self.path.split("?")[0]

        if path == "/api/state":
            s = config.get()
            return self._json({"llm": npu.state, "detail": npu.detail, "tps": npu.tps, "ttft": npu.ttft,
                               "settings": s, "models": state["models"], "env": shell.env, "version": VERSION,
                               "running": shell.running, "recipes": len(library.items),
                               "recommended": config.RECOMMENDED_MODEL, "catalog": os.path.exists(CATALOG)})
        if path == "/api/hints":
            from core import hints
            return self._json(hints.hints())
        if path == "/api/library":
            return self._json([{"title": it["q"][0], "also": " ".join(it["q"][1:]), "note": it["note"],
                                "section": it["section"], "file": it["source"].split(".")[0], "source": it["source"],
                                "admin": it["admin"]} for it in library.items])
        if path == "/api/ask":
            q = (body.get("q") or "").strip()[:2000]
            if body.get("task"):
                return self._stream(assistant.ask_task(body["task"], q))
            if npu.state != "online" and not library.exact(q):
                return self._stream(wait_for_ai(q, body))
            return self._stream(assistant.ask(q, body.get("history") or [], bool(body.get("deep")),
                                             body.get("instant", True) is not False,
                                             use_router=config.get()["router"]))
        if path == "/api/run":
            code = body.get("code") or ""
            refused = gate_code(code, body)
            if refused:
                return self._stream(iter([{"type": "error", "text": refused}]))
            return self._stream({"type": t, "data": d} for t, d in shell.run(fix_code(code)))
        if path == "/api/stop":
            shell.stop()
            return self._json({"ok": True})
        if path == "/api/verify":
            code = body.get("code") or ""
            check = shell.verify(code)
            check["ticket"] = issue_ticket(code, check.get("risk"))
            return self._json(check)
        if path == "/api/terminal":
            code = body.get("code") or ""
            refused = gate_code(code, body) if code.strip() else None
            if refused:
                return self._json({"ok": False, "error": refused}, 409)
            shell.open_terminal(code, bool(body.get("admin")))
            return self._json({"ok": True})
        if path == "/api/settings":
            before = config.get()
            after = config.update(body)
            if after["model"] != before["model"]:
                threading.Thread(target=npu.warmup, args=(after["model"],), daemon=True).start()
            return self._json(after)
        if path == "/api/ping":
            return self._json({"ok": True})
        return self._json({"error": "not found"}, 404)


def wait_for_ai(q, body):
    """The model is still loading: wait for it (up to 40 s) instead of turning the question away."""
    if npu.state not in ("starting", "online"):
        npu.ensure()
    t0 = time.time()
    while npu.state == "starting" and time.time() - t0 < 40:
        yield {"type": "status", "text": f"Waking up the AI on the NPU… {int(time.time() - t0)} s"}
        time.sleep(1)
    if npu.state != "online":
        yield {"type": "error", "text": "The AI is not available (" + (npu.detail or "FastFlowLM is not running") + "). "
               "Library answers still work: open the Library (Ctrl+L) or try other words."}
        return
    yield from assistant.ask(q, body.get("history") or [], bool(body.get("deep")), body.get("instant", True) is not False,
                             use_router=config.get()["router"])


def find_edge():
    for p in (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
              os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")):
        if os.path.exists(p):
            return p
    return None


def open_window(url):
    edge = find_edge()
    if edge:
        return subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={os.path.join(config.DATA_DIR, 'window')}",
                                 "--window-size=880,820", "--no-first-run", "--no-default-browser-check",
                                 "--disable-features=Translate", "--disable-extensions"])
    import webbrowser
    webbrowser.open(url)
    return None


def main():
    running = gate.find_running()
    if running:   # this user already runs Sensei - just show another window
        if "--no-window" not in sys.argv:
            open_window(f"http://127.0.0.1:{running[0]}/?k={running[1]}")
        return
    server = gate.bind(ThreadingHTTPServer, Handler)
    server.daemon_threads = True
    gate.publish()
    url = f"http://127.0.0.1:{gate.port}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=shell.start, daemon=True).start()
    # the chosen model must be downloaded; otherwise use the recommended one, or whatever chat model is there
    state["models"] = npu.downloaded_models()
    if state["models"] and config.get()["model"] not in state["models"]:
        rec = config.RECOMMENDED_MODEL
        config.update({"model": rec if rec in state["models"] else state["models"][0]})
    if not os.environ.get("SENSEI_NO_AI"):      # SENSEI_NO_AI=1: library only (UI tests while the NPU is busy)
        npu.ensure()
    log.info("Sensei started on %s", url)

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
        # Edge may hand the window to an already running instance; then wait until the page stops pinging
        while time.time() - state["last_seen"] < 20:
            time.sleep(2)
    log.info("Sensei closing")
    gate.withdraw()
    npu.stop()
    shell.shutdown()
    server.shutdown()


if __name__ == "__main__":
    main()
