"""Protection for the app's local web server (shared by Washi, Morph, Sensei and Kaizen; keep the copies identical).

How the window gets in, and nobody else does:
  * The server keeps a per-user discovery file (%LOCALAPPDATA%\\<App>\\instance.json) with its port and a random
    secret. Only this Windows user can read it (it lives in their profile).
  * The window is opened at  http://127.0.0.1:<port>/?k=<one-time launch key>. The server swaps the key for an
    HttpOnly, SameSite=Strict session cookie and redirects to "/", so the page never contains a secret and other
    users or programs fetching "/" get nothing useful.
  * A second launch of the app reads the discovery file and asks the running server for a new launch key with the
    secret, instead of trusting whatever answers on the port.
  * Every request must come from the window: right Host header, no cross-site Sec-Fetch-Site, the session cookie,
    and (for POST) the app's header. Bodies are size-checked before they are read.
  * Every response forbids framing (clickjacking) and MIME sniffing.
"""
import hmac
import json
import os
import secrets
import socket
import threading
import time
from http.cookies import SimpleCookie

LAUNCH_TTL = 120          # seconds a launch key stays valid
SAFE_SITES = {"same-origin", "none", ""}
SECURITY_HEADERS = [
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy", "frame-ancestors 'none'"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
]
BLOCKED_PAGE = (b"<!doctype html><meta charset=utf-8><title>Closed</title>"
                b"<body style='font:15px system-ui;margin:3em;color:#444'>"
                b"This window has expired. Please open the app again from its shortcut.</body>")


class Gate:
    def __init__(self, app, data_dir, header, preferred_port, max_body=2 * 1024 * 1024):
        self.app = app
        self.data_dir = data_dir
        self.header = header                  # e.g. "X-Sensei": the page sends it on every POST
        self.preferred_port = preferred_port
        self.max_body = max_body
        self.port = None
        self.secret = secrets.token_urlsafe(32)
        self.session = secrets.token_urlsafe(32)
        self.cookie = f"{app.lower()}_s"
        self._launch = {}                     # key -> expiry
        self._lock = threading.Lock()
        self.file = os.path.join(data_dir, "instance.json")

    # ---------------------------------------------------------------- server side
    def bind(self, server_cls, handler_cls):
        """Create the server on the preferred port, or on a free one if that is taken."""
        for port in (self.preferred_port, 0):
            try:
                srv = server_cls(("127.0.0.1", port), handler_cls)
                break
            except OSError:
                if port == 0:
                    raise
        self.port = srv.server_address[1]
        return srv

    def publish(self):
        """Write the discovery file (port + secret) for later launches by this user."""
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = self.file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"app": self.app, "port": self.port, "secret": self.secret, "pid": os.getpid()}, f)
        os.replace(tmp, self.file)

    def withdraw(self):
        try:
            with open(self.file, encoding="utf-8") as f:
                if json.load(f).get("pid") == os.getpid():
                    os.remove(self.file)
        except (OSError, ValueError):
            pass

    def new_launch_key(self):
        key = secrets.token_urlsafe(24)
        now = time.time()
        with self._lock:
            self._launch = {k: t for k, t in self._launch.items() if t > now}
            self._launch[key] = now + LAUNCH_TTL
        return key

    def launch_url(self, path="/", extra=""):
        return f"http://127.0.0.1:{self.port}{path}?k={self.new_launch_key()}{extra}"

    def _take_launch_key(self, key):
        with self._lock:
            t = self._launch.pop(key or "", 0)
        return t > time.time()

    def host_ok(self, h):
        host = h.headers.get("Host", "")
        return host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}")

    def site_ok(self, h):
        return (h.headers.get("Sec-Fetch-Site") or "").lower() in SAFE_SITES

    def has_session(self, h):
        try:
            c = SimpleCookie(h.headers.get("Cookie") or "")
        except Exception:  # noqa: BLE001 - a malformed cookie header is simply not a session
            return False
        m = c.get(self.cookie)
        return bool(m) and hmac.compare_digest(m.value, self.session)

    def secret_ok(self, h):
        return hmac.compare_digest(h.headers.get(f"{self.header}-Secret") or "", self.secret)

    def add_headers(self, h):
        """Call from the handler's end_headers(), so every response carries these."""
        for k, v in SECURITY_HEADERS:
            h.send_header(k, v)

    def get_allowed(self, h):
        """For GET. Handles the launch-key exchange itself; returns True when the request may be served."""
        if not self.host_ok(h) or not self.site_ok(h):
            self._deny(h)
            return False
        path, _, query = h.path.partition("?")
        key = next((p[2:] for p in query.split("&") if p.startswith("k=")), "")
        if key:
            if self._take_launch_key(key):
                rest = "&".join(p for p in query.split("&") if not p.startswith("k="))
                h.send_response(303)
                h.send_header("Set-Cookie", f"{self.cookie}={self.session}; HttpOnly; SameSite=Strict; Path=/")
                h.send_header("Location", path + ("?" + rest if rest else ""))
                h.send_header("Content-Length", "0")
                h.send_header("Cache-Control", "no-store")
                h.end_headers()
                return False
            if self.has_session(h):      # reload of a page whose URL still carries a used key
                return True
            self._deny(h)
            return False
        if not self.has_session(h):
            self._deny(h)
            return False
        return True

    def post_allowed(self, h, max_body=None):
        """For POST, before reading the body. On False the connection is closed and the body left unread."""
        limit = self.max_body if max_body is None else max_body
        try:
            n = int(h.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        ok = (self.host_ok(h) and self.site_ok(h) and h.headers.get(self.header) and self.has_session(h)
              and 0 <= n <= limit)
        if not ok:
            h.close_connection = True
            self._deny(h, json_body=True)
        return bool(ok)

    def _deny(self, h, json_body=False):
        body = b'{"error":"forbidden"}' if json_body else BLOCKED_PAGE
        h.close_connection = True
        h.send_response(403)
        h.send_header("Content-Type", "application/json" if json_body else "text/html; charset=utf-8")
        h.send_header("Content-Length", str(len(body)))
        h.send_header("Cache-Control", "no-store")
        h.send_header("Connection", "close")
        h.end_headers()
        try:
            h.wfile.write(body)
        except OSError:
            pass

    def handle_launch(self, h):
        """POST /api/launch from a second copy of the app: secret in, new launch key out. True if handled."""
        if h.path.split("?")[0] != "/api/launch":
            return False
        if not self.host_ok(h) or not self.secret_ok(h):
            h.close_connection = True
            self._deny(h, json_body=True)
            return True
        n = int(h.headers.get("Content-Length") or 0)
        body = {}
        if 0 < n <= 64 * 1024:
            try:
                body = json.loads(h.rfile.read(n))
            except ValueError:
                body = {}
        data = json.dumps({"app": self.app, "key": self.new_launch_key(), "port": self.port,
                           "args": body.get("args") or []}).encode()
        h.send_response(200)
        h.send_header("Content-Type", "application/json")
        h.send_header("Content-Length", str(len(data)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        h.wfile.write(data)
        self.on_launch(body)
        return True

    def on_launch(self, body):
        """Override to act on a second launch (e.g. open the files it was given)."""

    # ---------------------------------------------------------------- client side (a second launch)
    def find_running(self, args=None, timeout=1.5):
        """Ask the copy this user already runs for a launch key. Returns (port, key) or None."""
        try:
            with open(self.file, encoding="utf-8") as f:
                info = json.load(f)
            port, secret = int(info["port"]), info["secret"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        body = json.dumps({"args": args or []}).encode()
        req = (f"POST /api/launch HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n{self.header}-Secret: {secret}\r\n"
               f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
                s.sendall(req)
                chunks = []
                while True:
                    b = s.recv(65536)
                    if not b:
                        break
                    chunks.append(b)
            head, _, payload = b"".join(chunks).partition(b"\r\n\r\n")
            if not head.startswith(b"HTTP/1.1 200") and not head.startswith(b"HTTP/1.0 200"):
                return None
            data = json.loads(payload)
            if data.get("app") != self.app:
                return None
            return port, data["key"]
        except (OSError, ValueError, KeyError):
            return None
