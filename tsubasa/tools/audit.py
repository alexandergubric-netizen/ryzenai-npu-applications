"""Stability, security and speed audit of a running-but-isolated Tsubasa server (no model requests).

Starts app.py with a throwaway data home, then checks:
  1. the security gate (cookie, header, host, cross-site, launch secret, body limits)
  2. fuzzed and malformed requests on every POST endpoint: 4xx answers, never a crash or a hang
  3. one-operation-at-a-time and recovery after a cancelled command
  4. memory, handle and thread growth over hundreds of requests
  5. response times of the main read endpoints and the library/attachment helpers
Run:  .venv\\Scripts\\python.exe tools\\audit.py   (prints a JSON report; exit code 1 if a check failed)
"""
import concurrent.futures as cf
import ctypes
import http.client
import json
import os
import random
import statistics
import string
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
ENDPOINTS = ["/api/store", "/api/terminal-ai", "/api/agent", "/api/agent-decision", "/api/library", "/api/pick",
             "/api/images", "/api/images-create", "/api/files", "/api/knowledge", "/api/terminal", "/api/tool-decision",
             "/api/chat", "/api/switch", "/api/cancel", "/api/audio"]
SAFE_ACTIONS = {"/api/pick": None}   # opens a native dialog; never fuzzed with a valid kind
results, failures = {}, []


def check(name, ok, detail=""):
    results[name] = {"ok": bool(ok), "detail": detail}
    if not ok:
        failures.append(name)


class Server:
    def __init__(self):
        self.home = tempfile.mkdtemp(prefix="audit-", dir=ROOT / ".test-runs")
        env = {**os.environ, "TSUBASA_HOME": self.home}
        self.proc = subprocess.Popen([str(PY), str(ROOT / "app.py"), "--no-browser"], cwd=ROOT, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
        info = Path(self.home) / "instance.json"
        for _ in range(100):
            if info.exists():
                break
            time.sleep(0.1)
        meta = json.loads(info.read_text())
        self.port, self.secret = meta["port"], meta["secret"]
        self.pid = self._child_pid()
        key = self.raw("POST", "/api/launch", b"{}", {"X-Tsubasa-Secret": self.secret, "Content-Type": "application/json"})
        launch = json.loads(key[1])["key"]
        status, _, headers = self.raw("GET", f"/?k={launch}", headers_out=True)
        self.cookie = headers.get("Set-Cookie", "").split(";")[0]

    def _child_pid(self):
        # The venv python.exe is a redirector; the real server is the process that owns the listening port.
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              f"(Get-NetTCPConnection -State Listen -LocalPort {self.port}).OwningProcess"],
                             capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout.split()
        return int(out[0]) if out else self.proc.pid

    def raw(self, method, path, body=None, headers=None, headers_out=False, timeout=15):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        h = {"Host": f"127.0.0.1:{self.port}", **(headers or {})}
        c.request(method, path, body, h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return (r.status, data, dict(r.getheaders())) if headers_out else (r.status, data)

    def post(self, path, body, extra=None, timeout=15):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        return self.raw("POST", path, data, {"Cookie": self.cookie, "X-Tsubasa": "1", "Content-Type": "application/json",
                                             **(extra or {})}, timeout=timeout)

    def stop(self):
        try:
            self.post("/api/close", {})
        except OSError:
            pass
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def usage(pid):
    """(working set MB, handles, threads) of the server process."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"$p=Get-Process -Id {pid}; '{{0}} {{1}} {{2}}' -f [math]::Round($p.WorkingSet64/1MB,1),$p.HandleCount,$p.Threads.Count"],
                         capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout.split()
    return float(out[0]), int(out[1]), int(out[2])


def junk(depth=0):
    kinds = [lambda: None, lambda: random.randint(-10**12, 10**12), lambda: random.random() * 1e9,
             lambda: "".join(random.choices(string.printable + "ěščřžýáíé\u202e\x00", k=random.randint(0, 300))),
             lambda: "A" * random.choice([0, 1, 4000, 40000]), lambda: True, lambda: "../../../../Windows/win.ini",
             lambda: "C:\\Windows\\System32\\config\\SAM", lambda: "\\\\server\\share"]
    if depth < 2:
        kinds += [lambda: [junk(depth + 1) for _ in range(random.randint(0, 4))],
                  lambda: {random.choice(["action", "id", "path", "name", "code", "q", "workspace", "ticket", "model",
                                          "message", "chat_id", "arguments", "allow", "on", "kind", "source"]): junk(depth + 1)
                           for _ in range(random.randint(0, 5))}]
    return random.choice(kinds)()


def main():
    random.seed(7)
    s = Server()
    try:
        # 1. gate ------------------------------------------------------------------------------------------
        check("gate: page without cookie is refused", s.raw("GET", "/")[0] == 403)
        check("gate: API without cookie is refused", s.raw("POST", "/api/store", b"{}", {"X-Tsubasa": "1", "Content-Type": "application/json"})[0] == 403)
        check("gate: API without the app header is refused", s.raw("POST", "/api/store", b"{}", {"Cookie": s.cookie, "Content-Type": "application/json"})[0] == 403)
        check("gate: cross-site request is refused", s.post("/api/store", {"action": "list"}, {"Sec-Fetch-Site": "cross-site"})[0] == 403)
        check("gate: wrong Host is refused (DNS rebinding)", s.raw("GET", "/api/state", None, {"Cookie": s.cookie, "Host": "evil.example:80"})[0] == 403)
        check("gate: launch with a wrong secret is refused", s.raw("POST", "/api/launch", b"{}", {"X-Tsubasa-Secret": "nope", "Content-Type": "application/json"})[0] == 403)
        check("gate: oversized body is refused before reading", s.post("/api/store", b"{" + b" " * 40000 + b"}")[0] == 400)
        check("gate: invalid JSON is refused", s.post("/api/store", b"{not json")[0] == 400)
        status, _, h = s.raw("GET", "/", None, {"Cookie": s.cookie}, headers_out=True)
        csp = h.get("Content-Security-Policy", "")
        check("gate: strict CSP and no framing", status == 200 and "default-src 'self'" in csp and h.get("X-Frame-Options") == "DENY", csp[:80])
        check("files: import refuses path tricks", s.raw("POST", "/api/files/import?workspace=default&name=..%5Cevil.txt", b"x",
                                                         {"Cookie": s.cookie, "X-Tsubasa": "1"})[0] == 400)
        check("files: import refuses executables", s.raw("POST", "/api/files/import?workspace=default&name=run.exe", b"MZ",
                                                         {"Cookie": s.cookie, "X-Tsubasa": "1"})[0] == 400)
        check("terminal: destructive code without a ticket is refused",
              s.post("/api/terminal-ai", {"action": "run", "code": "Remove-Item -LiteralPath $HOME\\nonexistent-audit.txt"}, timeout=60)[0] == 409)
        check("library: system folders cannot be indexed", s.post("/api/library", {"action": "add_source", "id": "builtin-coding", "path": "C:\\Windows"})[0] == 400)
        check("agent: unknown decision is refused", s.post("/api/agent-decision", {"ticket": "x", "request_id": "y", "action": "allow"})[0] == 409)

        # 2. fuzz -------------------------------------------------------------------------------------------
        before = usage(s.pid)
        codes, slow, crashes = {}, [], []
        for i in range(400):
            path = random.choice(ENDPOINTS)
            body = junk()
            if not isinstance(body, dict):
                body = {"payload": body}
            if path == "/api/pick":
                body["kind"] = "nope"            # never open a real dialog
            if path in ("/api/terminal-ai",) and body.get("action") in ("run", "open", "cd"):
                body["action"] = "check"         # never execute fuzzed code
            if path in ("/api/library",) and body.get("action") == "add_source":
                body["path"] = "C:\\Windows"
            if path in ("/api/store",) and body.get("action") in ("delete", "delete_workspace"):
                body["action"] = "list"
            t0 = time.monotonic()
            try:
                code = s.post(path, body, timeout=30)[0]
            except (OSError, http.client.HTTPException) as exc:
                crashes.append(f"{path}: {type(exc).__name__}")
                continue
            dt = time.monotonic() - t0
            codes[code] = codes.get(code, 0) + 1
            if dt > 5:
                slow.append(f"{path} {dt:.1f}s")
            if code >= 500 and path not in ("/api/models", "/api/status"):
                crashes.append(f"{path} -> {code} {json.dumps(body)[:120]}")
        check("fuzz: 400 malformed requests, no 5xx or dropped connection", not crashes, "; ".join(crashes[:6]))
        check("fuzz: no request took over 5 s", not slow, "; ".join(slow[:6]))
        check("fuzz: server still healthy afterwards", s.raw("GET", "/api/state", None, {"Cookie": s.cookie})[0] == 200,
              json.dumps(codes))

        # 3. one operation at a time; stop and recover --------------------------------------------------------
        long_run = {}
        def slow_cmd():
            long_run["r"] = s.post("/api/terminal-ai", {"action": "run", "code": "Start-Sleep -Seconds 4; 'done'"}, timeout=60)
        t = threading.Thread(target=slow_cmd)
        t.start()
        time.sleep(1.5)
        second = s.post("/api/terminal-ai", {"action": "run", "code": "Get-Date"}, timeout=30)[0]
        check("busy: a second run while one is running gets 409", second == 409, str(second))
        s.post("/api/terminal-ai", {"action": "stop"})
        t.join(30)
        check("stop: the running command ended", not t.is_alive() and long_run.get("r", (0,))[0] == 200)
        status, body = s.post("/api/terminal-ai", {"action": "run", "code": "'after-stop'"}, timeout=60)
        check("stop: the terminal works again after Stop", status == 200 and b"after-stop" in body)

        # 4. leaks ---------------------------------------------------------------------------------------------
        def burst(n):
            with cf.ThreadPoolExecutor(16) as pool:
                list(pool.map(lambda _: s.raw("GET", "/api/state", None, {"Cookie": s.cookie}), range(n)))
        burst(300)
        mid = usage(s.pid)
        burst(600)
        after = usage(s.pid)
        check("leaks: memory stays flat over 900 parallel requests", after[0] - mid[0] < 15, f"MB {before[0]} → {mid[0]} → {after[0]}")
        check("leaks: handles stay flat", after[1] - mid[1] < 60, f"handles {before[1]} → {mid[1]} → {after[1]}")
        check("leaks: threads return to normal", after[2] <= mid[2] + 4, f"threads {before[2]} → {mid[2]} → {after[2]}")

        # 5. speed ---------------------------------------------------------------------------------------------
        def timed(fn, n=30):
            xs = []
            for _ in range(n):
                t0 = time.perf_counter()
                fn()
                xs.append((time.perf_counter() - t0) * 1000)
            return round(statistics.median(xs), 1), round(max(xs), 1)
        import socket
        def get(path):
            # Socket-level timing: http.client adds ~15 ms of its own on Windows, which is not the server's.
            sock = socket.create_connection(("127.0.0.1", s.port))
            sock.sendall(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{s.port}\r\nCookie: {s.cookie}\r\nConnection: close\r\n\r\n".encode())
            while sock.recv(65536):
                pass
            sock.close()
        speed = {
            "GET / (page)": timed(lambda: get("/")),
            "GET /app.js": timed(lambda: get("/app.js")),
            "GET /api/state": timed(lambda: get("/api/state")),
            "GET /api/models (cached)": timed(lambda: get("/api/models")),
            "POST library list": timed(lambda: s.post("/api/library", {"action": "list"})),
            "POST terminal check": timed(lambda: s.post("/api/terminal-ai", {"action": "check", "code": "Get-ChildItem $HOME"}), 10),
        }
        sys.path.insert(0, str(ROOT))
        from core.library import Library
        from core import extract
        lib = Library(s.home)
        speed["library context (3 packs)"] = timed(lambda: lib.context("What is the escape velocity of Earth in km/s?"))
        big = Path(s.home) / "big.md"
        big.write_text(("Lorem ipsum dolor sit amet, consectetur. " * 25 + "\n") * 1000, encoding="utf-8")
        speed["read 1 MB Markdown attachment"] = timed(lambda: (extract._cache.clear(), extract.read(big)), 5)
        sizes = {p: len(s.raw("GET", p, None, {"Cookie": s.cookie})[1]) for p in ("/", "/app.js", "/app.css", "/theme.css", "/modes.js", "/markdown.js")}
        results["speed (median ms, max ms)"] = speed
        results["page weight (bytes)"] = {**sizes, "total": sum(sizes.values())}
        results["server usage (MB, handles, threads)"] = {"start": before, "after 900 requests": after}
        check("speed: state and page under 50 ms median", speed["GET /api/state"][0] < 50 and speed["GET / (page)"][0] < 50)
    finally:
        s.stop()
    print(json.dumps({"failed": failures, "results": results}, indent=2, ensure_ascii=False))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
