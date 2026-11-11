"""Administrator commands: one elevated PowerShell per approved command, its output streamed back into Tsubasa.

The user approves the step in the app; Windows then shows its own UAC prompt. The elevated process is Sensei's host
(vendor/sensei/host.ps1) in run mode, hidden, connecting back over a loopback socket with a one-time token, so the
output arrives line by line exactly like the normal session's and goes back to the model as untrusted data. Each
command gets a fresh process that ends when the command finishes: nothing stays elevated in the background.
"""
import ctypes
import json
import secrets
import socket
import subprocess
import threading
from ctypes import wintypes

from core.sensei_term import CATALOG, HOST_PS1, Host, pwsh_exe

ERROR_CANCELLED = 1223
UAC_WAIT = 120          # seconds for the user to answer the Windows prompt
SEE_MASK_NOCLOSEPROCESS, SEE_MASK_NOASYNC, SEE_MASK_FLAG_NO_UI = 0x40, 0x100, 0x400


class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]


_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfo)]
_shell32.ShellExecuteExW.restype = wintypes.BOOL
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class ElevatedHost(Host):
    """Host started through ShellExecuteEx (verb 'runas' shows the UAC prompt; tests use 'open')."""

    def __init__(self, cwd, verb="runas"):
        super().__init__("run")
        self.cwd, self.verb, self.handle = cwd, verb, None

    def start(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(UAC_WAIT)
        token = secrets.token_hex(16)
        args = subprocess.list2cmdline(["-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                                        "-ExecutionPolicy", "RemoteSigned", "-File", HOST_PS1,
                                        "-Port", str(srv.getsockname()[1]), "-Token", token, "-Mode", "run",
                                        "-Catalog", CATALOG])
        info = _ShellExecuteInfo(cbSize=ctypes.sizeof(_ShellExecuteInfo),
                                 fMask=SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI,
                                 lpVerb=self.verb, lpFile=pwsh_exe(), lpParameters=args, lpDirectory=self.cwd, nShow=0)
        try:
            if not _shell32.ShellExecuteExW(ctypes.byref(info)):
                err = ctypes.get_last_error()
                if err == ERROR_CANCELLED:
                    raise PermissionError("You declined the Windows administrator prompt, so nothing was run.")
                raise OSError(f"Could not start PowerShell as administrator (Windows error {err}).")
            self.handle = info.hProcess
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                raise TimeoutError("The administrator PowerShell did not start within 2 minutes.") from None
        finally:
            srv.close()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.conn = conn
        self.rf = conn.makefile("r", encoding="utf-8", newline="\n")
        self.wf = conn.makefile("w", encoding="utf-8", newline="\n")
        if self.rf.readline().strip() != token:
            self.kill()
            raise RuntimeError("The administrator PowerShell failed the handshake.")
        self.env = json.loads(self.rf.readline())["d"]
        self.alive = True
        self.gen += 1
        threading.Thread(target=self._read_socket, args=(self.rf, self.events, self.gen), daemon=True).start()

    def kill(self):
        self.alive = False
        try:
            self.conn.close()      # the host exits when its socket closes
        except (OSError, AttributeError):
            pass
        if self.handle:
            _kernel32.TerminateProcess(self.handle, 1)   # may be refused for an elevated process; the socket still ends it
            _kernel32.CloseHandle(self.handle)
            self.handle = None


def run_elevated(code, cwd, cancelled, verb="runas"):
    """Like Shell.run: yields (kind, data) lines, then ('done', info). info['admin'] says whether it really was elevated."""
    host, finished = ElevatedHost(cwd, verb), threading.Event()
    host.start()

    def watch():
        while not finished.wait(0.2):
            if cancelled.is_set():
                host.kill()
                return
    threading.Thread(target=watch, daemon=True).start()
    try:
        q = "'" + cwd.replace("'", "''") + "'"
        for kind, data in host.run(f"Set-Location -LiteralPath {q}\n{code}"):
            if kind == "done":
                yield kind, {**data, "admin": bool(host.env.get("admin"))}
                return
            if kind == "info" and data.startswith(("Stopped.", "The PowerShell session ended")):
                data = "Stopped. The administrator PowerShell was closed." if cancelled.is_set() else \
                    "The administrator PowerShell ended before the command finished."
            yield kind, data
    finally:
        finished.set()
        host.kill()
