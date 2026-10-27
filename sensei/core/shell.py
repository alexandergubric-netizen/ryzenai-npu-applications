"""PowerShell sessions driven over a local socket (see host.ps1)."""
import atexit
import base64
import json
import os
import queue
import secrets
import shutil
import socket
import subprocess
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOST_PS1 = os.path.join(HERE, "host.ps1")
TOOLS_PSM1 = os.path.join(HERE, "SenseiTools.psm1")
CATALOG_PS1 = os.path.join(HERE, "build_catalog.ps1")
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Sensei")
CATALOG = os.path.join(DATA_DIR, "catalog.json")
# the most used modules of the library, loaded into the session ahead of time (each saves 0.2-1.3 s on first use).
# Measured Oct 2026: these five cost ~43 MB; warming all 14 cost ~146 MB, so Storage, ScheduledTasks, Defender,
# NetSecurity, SmbShare, PrintManagement… now load on first use (1-2 s once) instead of always taking RAM.
WARM_MODULES = ["Microsoft.PowerShell.Archive", "NetTCPIP", "NetAdapter", "PnpDevice", "DnsClient"]
CREATE_NO_WINDOW = 0x08000000


def pwsh_exe():
    return shutil.which("pwsh") or shutil.which("powershell")


class Host:
    """One long-lived PowerShell process. mode='run' keeps state between commands; mode='verify' checks code."""

    def __init__(self, mode, cwd=None):
        self.mode = mode
        self.cwd = cwd or os.path.expanduser("~")
        self.proc = None
        self.events = queue.Queue()
        self.lock = threading.Lock()
        self.env = {}
        self.alive = False
        self._start_lock = threading.Lock()
        self.gen = 0
        self.stopping = False

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        with self._start_lock:
            if self.alive and self.proc and self.proc.poll() is None:
                return
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            srv.settimeout(40)
            token = secrets.token_hex(16)
            port = srv.getsockname()[1]
            self.events = queue.Queue()
            self.proc = subprocess.Popen(
                [pwsh_exe(), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned",
                 "-File", HOST_PS1, "-Port", str(port), "-Token", token, "-Mode", self.mode, "-Catalog", CATALOG],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=self.cwd if os.path.isdir(self.cwd) else None, creationflags=CREATE_NO_WINDOW)
            try:
                conn, _ = srv.accept()
            finally:
                srv.close()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.rf = conn.makefile("r", encoding="utf-8", newline="\n")
            self.wf = conn.makefile("w", encoding="utf-8", newline="\n")
            self.conn = conn
            if self.rf.readline().strip() != token:
                conn.close()
                raise RuntimeError("PowerShell host failed the handshake")
            ready = json.loads(self.rf.readline())
            self.env = ready["d"]
            self.cwd = self.env.get("cwd", self.cwd)
            self.alive = True
            self.gen += 1
            threading.Thread(target=self._read_socket, args=(self.rf, self.events, self.gen), daemon=True).start()
            threading.Thread(target=self._read_stdout, args=(self.proc, self.events), daemon=True).start()

    def _read_socket(self, rf, q, gen):
        try:
            for line in rf:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                q.put((msg["t"], msg["d"]))
        except (OSError, ValueError):
            pass
        if self.gen == gen:
            self.alive = False
        q.put(("exit", None))

    def _read_stdout(self, proc, q):
        # anything a command writes straight to the console (bypassing the pipeline) lands here
        for raw in iter(proc.stdout.readline, b""):
            text = raw.decode("utf-8", "replace").rstrip("\r\n")
            q.put(("out", text))

    def kill(self):
        self.alive = False
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)], capture_output=True,
                           creationflags=CREATE_NO_WINDOW)
        try:
            self.conn.close()
        except (OSError, AttributeError):
            pass

    def restart(self):
        self.kill()
        self.start()

    def _send(self, obj):
        self.wf.write(json.dumps(obj) + "\n")
        self.wf.flush()

    def _drain(self):
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                return

    # ---------------------------------------------------------------- requests
    def request(self, op, timeout=20, **kw):
        """Send one request and wait for its single reply (verify/env)."""
        with self.lock:
            if not self.alive:
                self.start()
            self._drain()
            self._send({"op": op, **kw})
            deadline = time.time() + timeout
            while True:
                try:
                    t, d = self.events.get(timeout=max(0.05, deadline - time.time()))
                except queue.Empty:
                    self.restart()
                    raise TimeoutError(op)
                if t == op:
                    return d
                if t == "exit":
                    raise RuntimeError("PowerShell host exited")

    def run(self, code):
        """Run code in the persistent session, yielding (type, data) events until ('done', info)."""
        with self.lock:
            if not self.alive:
                self.start()
            self._drain()
            self._send({"op": "run", "code": code})
            while True:
                t, d = self.events.get()
                if t == "exit":
                    yield "info", ("Stopped. PowerShell restarted in the same folder; variables were cleared." if self.stopping
                                   else "The PowerShell session ended (the command called exit). A fresh one was started.")
                    self.stopping = False
                    try:
                        self.start()
                    except (OSError, RuntimeError):
                        pass
                    yield "done", {"ok": False, "errors": 1, "exit": None, "ms": 0, "cwd": self.cwd, "dropped": 0,
                                   "restarted": True}
                    return
                if t == "done":
                    self.cwd = d.get("cwd") or self.cwd
                    yield t, d
                    return
                yield t, d


class Shell:
    """The user's session plus a separate checker, so checking never waits for a running command."""

    def __init__(self):
        self.session = Host("run")
        self.checker = Host("verify")
        self.running = False
        self.warm = False
        atexit.register(self.shutdown)

    def shutdown(self):
        for h in (self.session, self.checker):
            h.kill()

    def start(self):
        threads = [threading.Thread(target=h.start, daemon=True) for h in (self.session, self.checker)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(45)
        threading.Thread(target=self.ensure_catalog, daemon=True).start()
        threading.Thread(target=self.warm_up, daemon=True).start()

    def catalog_stale(self):
        try:
            age = time.time() - os.path.getmtime(CATALOG)
        except OSError:
            return True
        exe = pwsh_exe()
        newer_ps = exe and os.path.exists(exe) and os.path.getmtime(exe) > os.path.getmtime(CATALOG)
        return age > 14 * 86400 or newer_ps

    def ensure_catalog(self):
        """Build the command catalog in the background when it is missing or old, then hand it to the checker."""
        if not self.catalog_stale():
            return
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            subprocess.run([pwsh_exe(), "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned",
                            "-File", CATALOG_PS1, "-Out", CATALOG], capture_output=True, timeout=900,
                           creationflags=CREATE_NO_WINDOW | 0x00004000)   # BELOW_NORMAL_PRIORITY_CLASS
            self.checker.request("reload", timeout=60)
        except (OSError, subprocess.SubprocessError, TimeoutError, RuntimeError):
            pass

    def warm_up(self):
        """Load the common modules into the session while it is idle (a user command waits at most one module)."""
        for m in WARM_MODULES:
            if self.running:
                time.sleep(0.5)
            try:
                self.session.request("warm", timeout=60, module=m)
            except (TimeoutError, RuntimeError, OSError):
                return
        self.warm = True

    @property
    def env(self):
        env = dict(self.checker.env or self.session.env)
        env["cwd"] = self.session.cwd
        return env

    def verify(self, code):
        try:
            return self.checker.request("verify", timeout=25, code=code, cwd=self.session.cwd)
        except (TimeoutError, RuntimeError, OSError) as e:
            return {"syntax": [], "commands": [], "problems": [], "risk": "caution",
                    "reasons": [f"could not be checked ({e})"], "placeholders": [], "interactive": False}

    def run(self, code):
        self.running = True
        try:
            yield from self.session.run(code)
        finally:
            self.running = False

    def stop(self):
        """Stop a running command. The session is restarted in the same folder (variables are lost)."""
        cwd = self.session.cwd
        self.session.stopping = True
        self.session.kill()
        self.session.cwd = cwd

    def open_terminal(self, code, admin=False):
        """Open a real PowerShell window running the command and staying open."""
        cwd = self.session.cwd
        q = lambda s: "'" + s.replace("'", "''") + "'"  # noqa: E731
        script = f"Import-Module {q(TOOLS_PSM1)} -DisableNameChecking\nSet-Location -LiteralPath {q(cwd)}"
        if code:
            script += "\n" + code
        enc = base64.b64encode(script.encode("utf-16-le")).decode()
        exe = pwsh_exe()
        if admin:
            ps = (f"Start-Process -FilePath '{exe}' -Verb RunAs -ArgumentList "
                  f"'-NoExit','-NoLogo','-EncodedCommand','{enc}'")
            subprocess.Popen([exe, "-NoProfile", "-NonInteractive", "-Command", ps], creationflags=CREATE_NO_WINDOW)
            return
        wt = shutil.which("wt")
        if wt:
            subprocess.Popen([wt, "-w", "new", "-d", cwd, exe, "-NoExit", "-NoLogo", "-EncodedCommand", enc])
        else:
            subprocess.Popen([exe, "-NoExit", "-NoLogo", "-EncodedCommand", enc], cwd=cwd,
                             creationflags=subprocess.CREATE_NEW_CONSOLE)


shell = Shell()
