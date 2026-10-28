r"""Tansu installer.

Copyright (c) 2026 Alexander Gubric. MIT License.

Runs from the folder the self-extracting Tansu-Setup.exe unpacks to:
    <temp>\runtime\   bundled Python with py7zr and send2trash (pythonw.exe runs this file)
    <temp>\app\       Tansu itself
    <temp>\setup\     this installer
It checks the PC, installs Tansu per user (no admin rights) and creates shortcuts. On PCs with an AMD Ryzen AI NPU it
explains that the archiving advisor needs FastFlowLM and can install FastFlowLM and the model. On every other PC (Intel,
older AMD) Tansu archives with its built-in rules: every format, verification and the library work, only the AI is off.

TANSU_SETUP_TEST=<folder> runs a dry run: installs into that folder, writes shortcuts there, skips the registry and
simulates downloads. TANSU_SETUP_HEADLESS=1 opens no window (a test drives the API; port in <folder>\setup-port.txt).
TANSU_NO_AI=1 shows the setup as it looks on a PC without a supported NPU.
"""
import ctypes
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import winreg
from ctypes import wintypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "app"))
sys.path.insert(0, HERE)
import safety  # noqa: E402

APP = "Tansu"
VERSION = "0.9.0"
PUBLISHER = "Alexander Gubric"
COPYRIGHT = "© 2026 Alexander Gubric"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Tansu"
TEST = os.environ.get("TANSU_SETUP_TEST")
TOKEN = secrets.token_urlsafe(24)
CREATE_NO_WINDOW = 0x08000000
FLM_MODELS = [("qwen3.5:4b", 3.2), ("qwen3.5:2b", 1.9)]   # the default, and a faster one to switch to
FLM_MODEL, FLM_MODEL_GB = FLM_MODELS[0][0], 5.1
SENDTO_NAME = "Tansu (archive).lnk"                       # the same name the app's Settings switch uses

log_lines = []


def log(msg):
    log_lines.append(time.strftime("%H:%M:%S ") + msg)


# ======================================================================= system check
def _reg(hive, path, name, default=None):
    try:
        with winreg.OpenKey(hive, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return default


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def ram_gb():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return round(m.ullTotalPhys / 2 ** 30)


def known_folder(guid):
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid), ctypes.byref(g))
    p = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) != 0:
        return None
    try:
        return p.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(p)


def documents():
    return known_folder("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}") or os.path.expanduser(r"~\Documents")


def desktop():
    return known_folder("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}") or os.path.expanduser(r"~\Desktop")


def edge():
    for p in (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
              os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")):
        if os.path.exists(p):
            return p
    return None


def flm_models():
    from core import hw
    exe = hw.flm_exe()
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "list", "--filter", "installed", "--quiet"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30, creationflags=CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return re.findall(r"^\s*-\s+(\S+)", out, re.M)


def system_check():
    from core import hw
    h = hw.check(refresh=True)
    build = int(_reg(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuild", "0") or 0)
    arch = _reg(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                "PROCESSOR_ARCHITECTURE", "AMD64")
    ram = ram_gb()
    drive = os.path.splitdrive(os.path.expandvars("%LOCALAPPDATA%"))[0] + "\\"
    free = shutil.disk_usage(drive).free / 2 ** 30
    existing = _reg(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, "InstallLocation")
    models = flm_models() if h["flm"] else []
    library = os.path.join(documents(), "Archives")
    checks = []

    def add(label, value, status, note=""):
        checks.append({"label": label, "value": value, "status": status, "note": note})

    add("Windows", f"Windows {'11' if build >= 22000 else '10'} · build {build}", "ok" if build >= 17763 else "bad",
        "" if build >= 17763 else "Tansu needs Windows 10 (1809) or newer")
    add("Processor", h["cpu"] or "unknown", "ok" if arch in ("AMD64", "ARM64") else "bad",
        "Runs through Windows' x64 emulation" if arch == "ARM64" else "")
    add("Memory", f"{ram} GB", "ok" if ram >= 8 else "warn", "" if ram >= 8 else "Big archives are packed more slowly")
    add("Free space", f"{free:.0f} GB", "ok" if free >= 5 else "warn" if free >= 0.2 else "bad",
        "" if free >= 5 else "Tansu needs about 40 MB, the AI models about 5 GB more, and your archives their own space")
    add("Microsoft Edge", "found" if edge() else "missing", "ok" if edge() else "warn",
        "" if edge() else "Tansu opens in your default browser instead of its own window")
    add("Archive library", library, "ok" if os.path.isdir(library) else "info",
        "Your existing archives are found and indexed" if os.path.isdir(library)
        else "Created when you file your first archive (you can choose another folder in Settings)")
    if h["supported"]:
        add("AI chip (NPU)", h["npu"] or "Ryzen AI NPU", "ok", "The archiving advisor can run here")
        add("FastFlowLM", "installed" if h["flm"] else "not installed", "ok" if h["flm"] else "warn",
            "Prerequisite for the AI advisor" + ("" if h["flm"] else " — setup can install it in the next step"))
    else:
        add("AI chip (NPU)", h["npu"] or "none supported", "info",
            h["reason"] + " — Tansu plans archives with its built-in rules")
    return {"checks": checks,
            "ai": {"supported": h["supported"], "reason": h["reason"], "flm": h["flm"], "model": all(x in models for x, _ in FLM_MODELS),
                   "npu": h["npu"], "vendor": h["vendor"], "model_name": " and ".join(x for x, _ in FLM_MODELS), "model_gb": FLM_MODEL_GB},
            "can_install": build >= 17763 and arch in ("AMD64", "ARM64") and free >= 0.2, "existing": existing,
            "default_dir": existing or (os.path.join(TEST, APP) if TEST else os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tansu"))}


# ======================================================================= install
class Job:
    def __init__(self):
        self.running = self.done = self.cancelled = False
        self.error = ""
        self.steps = []
        self.result = {}

    def step(self, key, label):
        s = {"key": key, "label": label, "state": "active", "detail": "", "pct": None}
        self.steps.append(s)
        log(label)
        return s


job = Job()


def download(url, dest, step):
    if TEST:
        for i in range(21):
            step["pct"], step["detail"] = i * 5, f"Test mode: simulated download {i * 5}%"
            time.sleep(0.05)
        return False
    req = urllib.request.Request(url, headers={"User-Agent": f"Tansu-Setup/{VERSION}"})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, t0 = 0, time.time()
        while True:
            if job.cancelled:
                raise RuntimeError("Cancelled")
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            step["pct"] = round(got * 100 / total) if total else None
            step["detail"] = f"{got / 2**20:.0f} of {total / 2**20:.0f} MB · {got / max(time.time() - t0, .1) / 2**20:.1f} MB/s"
    os.replace(dest + ".part", dest)
    return True


def make_shortcuts(lnks, target, args, workdir, icon, description):
    """All shortcuts in one Windows PowerShell run (each start costs seconds). Paths travel as JSON in the
    environment, never inside the command."""
    ps = ("$w=New-Object -ComObject WScript.Shell;foreach($l in (ConvertFrom-Json $env:K_LNKS)){"
          "$s=$w.CreateShortcut($l);$s.TargetPath=$env:K_TARGET;$s.Arguments=$env:K_ARGS;$s.WorkingDirectory=$env:K_DIR;"
          "$s.IconLocation=$env:K_ICON;$s.Description=$env:K_DESC;$s.Save()}")
    # Windows PowerShell can't load its own modules with PowerShell 7's PSModulePath, so don't pass that on
    env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    env.update(K_LNKS=json.dumps(lnks), K_TARGET=target, K_ARGS=args, K_DIR=workdir, K_ICON=icon + ",0", K_DESC=description)
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), r"System32\WindowsPowerShell\v1.0\powershell.exe")
    subprocess.run([exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps], env=env,
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=120, creationflags=CREATE_NO_WINDOW)
    return [lnk for lnk in lnks if os.path.exists(lnk)]


def tansu_running():
    return safety.app_running(os.path.expandvars(r"%LOCALAPPDATA%\Tansu"))


def dir_size(path):
    total = 0
    for dp, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return total


def install(opts):
    job.running, job.done, job.error, job.steps = True, False, "", []
    try:
        target = safety.dedicated_dir(opts["dir"], APP)
        safety.check_target(target, APP, _reg(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, "InstallLocation"))
        s = job.step("copy", "Installing Tansu")
        for _ in range(30):
            if TEST or not tansu_running():
                break
            s["detail"] = "Waiting for Tansu to close…"
            time.sleep(2)
        else:
            raise RuntimeError("Tansu is still open (or still packing an archive). Close its window and run setup again.")
        os.makedirs(target, exist_ok=True)
        for part in ("runtime", "app"):
            dst = os.path.join(target, part)
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            s["detail"] = f"Copying {part}…"
            shutil.copytree(os.path.join(ROOT, part), dst)
        shutil.copy2(os.path.join(HERE, "uninstall.py"), os.path.join(target, "uninstall.py"))
        pyw = os.path.join(target, "runtime", "pythonw.exe")
        app_py = os.path.join(target, "app", "app.py")
        icon = os.path.join(target, "app", "tansu.ico")
        safety.write_manifest(target, VERSION)   # the uninstaller removes exactly these files
        s["state"], s["detail"] = "done", target

        s = job.step("shortcuts", "Creating shortcuts")
        lnk_dir = os.path.join(target, "test-shortcuts") if TEST else None
        if lnk_dir:
            os.makedirs(lnk_dir, exist_ok=True)
        wanted = {}
        if opts.get("desktop", True):
            wanted["Desktop"] = os.path.join(lnk_dir or desktop(), f"{APP}.lnk")
        if opts.get("startmenu", True):
            wanted["Start menu"] = os.path.join(lnk_dir or os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
                                                f"{APP}.lnk" if not TEST else f"{APP} (start menu).lnk")
        if opts.get("sendto"):
            wanted["Send to"] = os.path.join(lnk_dir or os.path.expandvars(r"%APPDATA%\Microsoft\Windows\SendTo"), SENDTO_NAME)
        done = make_shortcuts(list(wanted.values()), pyw, f'"{app_py}"', target, icon,
                              "Tansu - smart archiver (local AI on the Ryzen NPU)") if wanted else []
        made = [k for k, v in wanted.items() if v in done]
        if len(made) < len(wanted):
            log("shortcuts missing: " + ", ".join(k for k in wanted if k not in made))
        if not TEST:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
                for name, value in (("DisplayName", APP), ("DisplayVersion", VERSION), ("Publisher", PUBLISHER),
                                    ("DisplayIcon", icon), ("InstallLocation", target),
                                    ("UninstallString", f'"{pyw}" "{os.path.join(target, "uninstall.py")}"'),
                                    ("Comments", "Smart archiver with an optional AI advisor for Ryzen AI NPUs. "
                                                 "MIT License; bundled components see THIRD-PARTY-NOTICES.txt")):
                    winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
                winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, dir_size(target) // 1024)
            made.append("Apps & features")
        s["state"], s["detail"] = "done", ", ".join(made) or "None"

        if opts.get("ai"):
            install_ai()
        job.result = {"pyw": pyw, "app": app_py, "dir": target}
        job.done = True
    except Exception as e:  # noqa: BLE001
        job.error = str(e)
        log("ERROR " + traceback.format_exc())
        for st in job.steps:
            if st["state"] == "active":
                st["state"] = "failed"
    finally:
        job.running = False


def install_ai():
    from core import hw
    if not hw.flm_exe() or TEST:
        s = job.step("flm", f"Installing FastFlowLM {safety.FLM_VERSION} (the NPU engine for the AI advisor)")
        with safety.PrivateDownload() as dl:
            msi = dl.path("flm-setup.msi")
            if download(safety.FLM_MSI_URL, msi, s):
                s["pct"], s["detail"] = None, "Checking the download…"
                safety.verify(msi, sha=safety.FLM_MSI_SHA256)   # pinned: the MSI is not code-signed
                s["detail"] = "Windows will ask for permission. Please click Yes."
                rc = subprocess.run(["msiexec.exe", "/i", msi, "/passive", "/norestart"]).returncode
                if rc not in (0, 3010):
                    s["state"], s["detail"] = "skipped", (f"FastFlowLM's installer stopped (code {rc}). Tansu is installed and "
                                                          "archives with its rules; set up the AI later from github.com/FastFlowLM.")
                    return
        s["state"], s["detail"] = "done", "Installed" if not TEST else "Test mode"
    for model, gb in FLM_MODELS:
        s = job.step("model" if model == FLM_MODEL else "model2", f"Downloading the AI model {model} (about {gb} GB)")
        if TEST:
            download("", "", s)
            s["state"], s["detail"] = "done", "Test mode"
            continue
        if model in flm_models():
            s["state"], s["detail"] = "done", "Already downloaded"
            continue
        exe = hw.flm_exe()
        if not exe:
            s["state"], s["detail"] = "skipped", "FastFlowLM needs a Windows restart first - then open Tansu again."
            return
        folder = os.path.join(documents(), "flm", "models")
        before = dir_size(folder) if os.path.isdir(folder) else 0
        proc = subprocess.Popen([exe, "pull", model], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=CREATE_NO_WINDOW)
        while proc.poll() is None:
            if job.cancelled:
                proc.terminate()
                raise RuntimeError("Cancelled")
            got = (dir_size(folder) if os.path.isdir(folder) else 0) - before
            s["pct"] = min(99, round(got * 100 / (gb * 2 ** 30)))
            s["detail"] = f"{got / 2**30:.2f} of about {gb} GB"
            time.sleep(1)
        if model not in flm_models():
            s["state"], s["detail"] = "skipped", "Not finished — run `flm pull " + model + "` later"
            continue
        s["state"], s["pct"], s["detail"] = "done", 100, "Ready on the NPU"


# ======================================================================= web UI
info_cache = {}
last_ping = {"t": 0.0}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _ok(self):
        return self.headers.get("Host", "") == f"127.0.0.1:{PORT}"

    def do_GET(self):
        if not self._ok():
            return self._send(403, {"error": "forbidden"})
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "setup.html"), "rb") as f:
                return self._send(200, f.read().replace(b"{{TOKEN}}", TOKEN.encode()), "text/html; charset=utf-8")
        if path == "/logo.png":
            with open(os.path.join(ROOT, "app", "web", "icon512.png"), "rb") as f:
                return self._send(200, f.read(), "image/png")
        if self.headers.get("X-Setup") != TOKEN:
            return self._send(403, {"error": "forbidden"})
        if path == "/api/info":
            if "system" not in info_cache:
                info_cache["system"] = system_check()
            with open(os.path.join(ROOT, "app", "LICENSE"), encoding="utf-8") as f:
                lic = f.read()
            with open(os.path.join(ROOT, "app", "THIRD-PARTY-NOTICES.txt"), encoding="utf-8") as f:
                lic += "\n\n" + f.read()
            return self._send(200, {"app": APP, "version": VERSION, "copyright": COPYRIGHT, "license": lic,
                                    "test": bool(TEST), **info_cache["system"]})
        if path == "/api/progress":
            return self._send(200, {"running": job.running, "done": job.done, "error": job.error,
                                    "steps": job.steps, "log": log_lines[-8:]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._ok() or self.headers.get("X-Setup") != TOKEN:
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        if n > 64 * 1024:
            return self._send(413, {"error": "too large"})
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        path = urlparse(self.path).path
        if path == "/api/ping":
            last_ping["t"] = time.time()
            return self._send(200, {"ok": True})
        if path == "/api/install":
            if not job.running:
                threading.Thread(target=install, args=(body,), daemon=True).start()
            return self._send(200, {"ok": True})
        if path == "/api/cancel":
            job.cancelled = True
            return self._send(200, {"ok": True})
        if path == "/api/launch" and job.result:
            subprocess.Popen([job.result["pyw"], job.result["app"]], cwd=job.result["dir"])
            return self._send(200, {"ok": True})
        if path == "/api/open":
            url = body.get("url", "")
            if url in (safety.FLM_LICENSE_URL, "https://github.com/FastFlowLM/FastFlowLM", "https://opensource.org/license/mit"):
                os.startfile(url)  # noqa: S606 - fixed allow-list
            return self._send(200, {"ok": True})
        if path == "/api/browse":
            return self._send(200, {"dir": pick_folder(body.get("dir", ""))})
        return self._send(404, {"error": "not found"})


def pick_folder(start):
    ps = ("$f=(New-Object -ComObject Shell.Application).BrowseForFolder(0,'Choose where to install Tansu',0x51,0);"
          "if($f){$f.Self.Path}")
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=300, creationflags=CREATE_NO_WINDOW).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    return os.path.join(out, APP) if out and not out.lower().endswith("tansu") else (out or start)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = free_port()


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=lambda: info_cache.setdefault("system", system_check()), daemon=True).start()
    url = f"http://127.0.0.1:{PORT}/"
    window = None
    if TEST:
        os.makedirs(TEST, exist_ok=True)
        with open(os.path.join(TEST, "setup-port.txt"), "w") as f:
            f.write(f"{PORT} {TOKEN}")
    if os.environ.get("TANSU_SETUP_HEADLESS"):
        pass
    elif edge():
        profile = os.path.join(os.environ.get("TEMP", HERE), f"tansu-setup-window-{PORT}")
        window = subprocess.Popen([edge(), f"--app={url}", f"--user-data-dir={profile}", "--window-size=1000,700",
                                   "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"])
    else:
        os.startfile(url)  # noqa: S606
    started = time.time()
    while True:
        time.sleep(1)
        idle = time.time() - (last_ping["t"] or started)
        if job.running:
            continue
        if window is not None and window.poll() is not None and idle > 6:
            break
        if idle > (60 if last_ping["t"] else 240):
            break
    server.shutdown()
    if window is not None:   # don't leave the setup window's browser profile behind in %TEMP%
        for _ in range(10):
            shutil.rmtree(profile, ignore_errors=True)
            if not os.path.exists(profile):
                break
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        with open(os.path.join(os.environ.get("TEMP", "."), "tansu-setup-error.log"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
