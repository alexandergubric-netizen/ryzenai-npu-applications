"""The FastFlowLM server shared by Washi, Morph, Sensei and Kaizen 5S (keep the copies identical; Postura's Ai.cs
follows the same rules).

One `flm serve` on 127.0.0.1:52625 serves whichever of these apps is open. A request that names another model makes
FastFlowLM swap models in place (about 15 s, the old model is unloaded), so a model change never needs a restart.
Every app starts the server the same way - the model's full 32k context and the user's power mode - and the server
is stopped when the last app that uses it closes, so one app closing never pulls the AI away from another.

The bookkeeping lives in %TEMP%\\ryzenai-apps-flm.json:
    {"server": <pid of the flm.exe one of the apps started>, "port": 52625, "pmode": "performance",
     "users": {"Washi": <pid>, "Postura": <pid>, ...}}
"""
import ctypes
import ctypes.wintypes as wt
import http.client
import json
import os
import signal
import subprocess
import tempfile
import threading
import time
import urllib.error

CTX_LEN = 32768           # the full context of the 4B models: costs memory (about 8.4 GB), not speed
FILE = os.path.join(tempfile.gettempdir(), "ryzenai-apps-flm.json")
CREATE_NO_WINDOW = 0x08000000
APP_IMAGES = ("python.exe", "pythonw.exe", "postura.exe")
_lock = threading.Lock()
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wt.HANDLE


def _image(pid):
    """File name of a running process, or None when it is gone."""
    if not pid:
        return None
    h = _k32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        code = wt.DWORD()
        if not _k32.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:   # STILL_ACTIVE
            return None
        buf, n = ctypes.create_unicode_buffer(1024), wt.DWORD(1024)
        if not _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return None
        return os.path.basename(buf.value).lower()
    finally:
        _k32.CloseHandle(h)


def _read():
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d):
    tmp = f"{FILE}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, FILE)
    except OSError:
        pass


def _live_users(d, skip=None):
    return {a: p for a, p in (d.get("users") or {}).items() if a != skip and _image(p) in APP_IMAGES}


PMODES = ("powersaver", "balanced", "performance", "turbo")


def serve_args(exe, model, port, pmode):
    pmode = pmode if pmode in PMODES else "performance"
    return [exe, "serve", model, "--port", str(int(port)), "--pmode", pmode, "--ctx-len", str(CTX_LEN)]


def start(exe, model, port, pmode, app):
    """Start the shared server and record it. Returns the process."""
    proc = subprocess.Popen(serve_args(exe, model, port, pmode), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
    with _lock:
        d = _read()
        d.update(server=proc.pid, port=int(port), pmode=pmode)
        d["users"] = {**_live_users(d), app: os.getpid()}
        _write(d)
    return proc


def join(app):
    """This app uses the server (started by itself or by another app)."""
    with _lock:
        d = _read()
        d["users"] = {**_live_users(d), app: os.getpid()}
        _write(d)


def server_pmode():
    """The power mode the recorded server was started with (None if it was not started by one of the apps)."""
    d = _read()
    return d.get("pmode") if _image(d.get("server")) == "flm.exe" else None


def others_using(app):
    return bool(_live_users(_read(), skip=app))


def stop_server(port=None):
    """Stop the server one of the apps started (never a FastFlowLM someone started by hand). True if stopped."""
    with _lock:
        d = _read()
        pid = d.get("server")
        if _image(pid) != "flm.exe" or (port and d.get("port") not in (None, int(port))):
            return False
        try:
            os.kill(pid, signal.SIGTERM)          # TerminateProcess
        except OSError:
            return False
        d.pop("server", None)
        _write(d)
    for _ in range(40):                           # wait until the port is free again
        if _image(pid) is None:
            break
        time.sleep(0.25)
    return True


def leave(app, port=None):
    """This app no longer needs the server. The last app to leave stops it. True if the server was stopped."""
    with _lock:
        d = _read()
        users = _live_users(d, skip=app)
        d["users"] = users
        _write(d)
    return False if users else stop_server(port)


def lost(exc):
    """Did a request fail because the server is gone (refused or dropped), rather than because of the request?"""
    if isinstance(exc, urllib.error.HTTPError):
        return False
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, (ConnectionError, http.client.RemoteDisconnected, http.client.IncompleteRead)) or \
        isinstance(exc, (ConnectionError, http.client.RemoteDisconnected))


def ctx_from_usage(usage):
    """The server's context length, from the KV occupancy FastFlowLM reports with every answer."""
    try:
        pct = float(usage.get("kv_token_occupancy_rate_percentage") or 0)
        total = int(usage.get("total_tokens") or 0)
    except (TypeError, ValueError, AttributeError):
        return None
    if pct <= 0 or total <= 0:
        return None
    return int(round(total * 100 / pct / 1024)) * 1024 or None
