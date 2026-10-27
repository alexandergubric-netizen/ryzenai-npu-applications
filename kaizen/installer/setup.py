r"""Kaizen 5S installer.

Copyright (c) 2026 Alexander Gubric. Free and open source software under the MIT License.

Runs from the folder the self-extracting Kaizen5S-Setup.exe unpacks to:
    <temp>\runtime\   bundled Python (pythonw.exe runs this file)
    <temp>\app\       Kaizen itself
    <temp>\setup\     this installer
It checks the PC, lets the person pick an AI engine that fits it, and installs everything per user (no admin
rights needed for Kaizen; FastFlowLM's own installer asks Windows for permission).

KAIZEN_SETUP_TEST=<folder> runs a dry run: installs into that folder, writes shortcuts there, skips the registry
and simulates downloads/third-party installers.
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
sys.path.insert(0, HERE)
import safety  # noqa: E402


def _edition():
    try:
        with open(os.path.join(ROOT, "app", "edition.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"id": "public", "name": "", "grant": "", "allow_uninstall": True}


EDITION = _edition()
APP = "Kaizen 5S"
DISPLAY_NAME = EDITION.get("display_name") or APP
VERSION = "1.0.1"
PUBLISHER = "Alexander Gubric"
COPYRIGHT = "© 2026 Alexander Gubric"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Kaizen5S"
TEST = os.environ.get("KAIZEN_SETUP_TEST")
TOKEN = secrets.token_urlsafe(24)
CREATE_NO_WINDOW = 0x08000000

# FastFlowLM itself is pinned and verified in safety.py; LM Studio must carry its publisher's signature
LMS_SIGNER = "O=Element Labs Inc."
FLM_MODEL = "qwen3:4b"
FLM_MIN_DRIVER = (32, 0, 203, 311)
LMS_MODELS = ["qwen/qwen3-4b-2507", "qwen/qwen3-4b"]
NPU_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{f01a9d53-3ff6-48d2-9f97-c8a7004be10c}"
GPU_CLASS = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"

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


def _devices(class_path):
    out = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, class_path)
    except OSError:
        return out
    with root:
        for i in range(winreg.QueryInfoKey(root)[0]):
            name = winreg.EnumKey(root, i)
            if not name.isdigit():
                continue
            sub = class_path + "\\" + name
            desc = _reg(winreg.HKEY_LOCAL_MACHINE, sub, "DriverDesc")
            if desc:
                out.append({"name": desc, "driver": _reg(winreg.HKEY_LOCAL_MACHINE, sub, "DriverVersion", ""),
                            "vendor": _reg(winreg.HKEY_LOCAL_MACHINE, sub, "ProviderName", "")})
    return out


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


def flm_exe():
    for p in (shutil.which("flm"), os.path.expandvars(r"%ProgramFiles%\flm\flm.exe")):
        if p and os.path.exists(p):
            return p
    return None


def flm_models():
    exe = flm_exe()
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "list", "--filter", "installed", "--quiet"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30, creationflags=CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return re.findall(r"^\s*-\s+(\S+)", out, re.M)


def flm_version():
    exe = flm_exe()
    if not exe:
        return ""
    try:
        out = subprocess.run([exe, "version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=20, creationflags=CREATE_NO_WINDOW).stdout
        m = re.search(r"v?(\d+\.\d+\.\d+)", out)
        return m.group(1) if m else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def lmstudio_app():
    for p in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\LM Studio\LM Studio.exe"),
              os.path.expandvars(r"%ProgramFiles%\LM Studio\LM Studio.exe")):
        if os.path.exists(p):
            return p
    return None


def lms_exe():
    for p in (os.path.expanduser(r"~\.lmstudio\bin\lms.exe"), shutil.which("lms")):
        if p and os.path.exists(p):
            return p
    return None


def edge():
    for p in (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
              os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")):
        if os.path.exists(p):
            return p
    return None


def _ver(text):
    return tuple(int(x) for x in re.findall(r"\d+", text or "")[:4])


def system_check():
    nt = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    build = int(_reg(winreg.HKEY_LOCAL_MACHINE, nt, "CurrentBuild", "0") or 0)
    arch = _reg(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                "PROCESSOR_ARCHITECTURE", "AMD64")
    cpu = (_reg(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
                "ProcessorNameString", "") or "").strip()
    gpus = [d for d in _devices(GPU_CLASS) if not re.search(r"basic|remote|virtual|mirror", d["name"], re.I)]
    npus = [d for d in _devices(NPU_CLASS) if re.search(r"npu|ipu|neural|ai boost", d["name"], re.I)]
    amd_npu = next((d for d in npus if "amd" in (d["vendor"] or "").lower() or "amd" in cpu.lower()), None)
    intel_npu = next((d for d in npus if "intel" in (d["vendor"] or "").lower() or "ai boost" in d["name"].lower()), None)
    ram = ram_gb()
    install_drive = os.path.splitdrive(os.path.expandvars("%LOCALAPPDATA%"))[0] + "\\"
    docs = documents()
    free_install = shutil.disk_usage(install_drive).free / 2 ** 30
    free_docs = shutil.disk_usage(os.path.splitdrive(docs)[0] + "\\").free / 2 ** 30
    win11 = build >= 22000
    xdna2 = bool(re.search(r"Ryzen\s+AI\s+(Max\+?\s+)?(PRO\s+)?(\d\s+)?(HX\s+)?(PRO\s+)?[34]\d\d", cpu, re.I)) or \
        bool(re.search(r"Ryzen\s+AI\s+Max", cpu, re.I))
    driver = amd_npu["driver"] if amd_npu else ""
    driver_ok = bool(driver) and _ver(driver) >= FLM_MIN_DRIVER
    existing = _reg(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY, "InstallLocation")
    flm = flm_exe()
    models = flm_models() if flm else []
    lms_app, lms = lmstudio_app(), lms_exe()

    checks = []

    def add(key, label, value, status, note=""):
        checks.append({"key": key, "label": label, "value": value, "status": status, "note": note})

    add("os", "Windows", f"Windows {'11' if win11 else '10'} · build {build}",
        "ok" if build >= 17763 else "bad", "" if build >= 17763 else "Kaizen needs Windows 10 (1809) or newer")
    add("arch", "Processor type", {"AMD64": "64-bit (x64)", "ARM64": "ARM64"}.get(arch, arch),
        "ok" if arch == "AMD64" else "warn" if arch == "ARM64" else "bad",
        "Kaizen runs through Windows' x64 emulation" if arch == "ARM64" else
        "" if arch == "AMD64" else "Kaizen needs a 64-bit PC")
    add("cpu", "CPU", cpu or "unknown", "ok")
    add("ram", "Memory", f"{ram} GB", "ok" if ram >= 16 else "warn" if ram >= 8 else "bad",
        "" if ram >= 16 else "Local AI will be slow" if ram >= 8 else "Too little memory for local AI")
    if amd_npu:
        add("npu", "NPU (AI chip)", f"{amd_npu['name']} · driver {driver}",
            "ok" if (xdna2 and driver_ok) else "warn" if xdna2 else "info",
            "" if (xdna2 and driver_ok) else
            "Update the AMD NPU driver to 32.0.203.311 or newer for FastFlowLM" if xdna2 else
            "This first-generation NPU isn't supported by FastFlowLM. LM Studio will run the AI instead.")
    elif intel_npu:
        add("npu", "NPU (AI chip)", f"{intel_npu['name']} · driver {intel_npu['driver']}", "info",
            "Not needed: on Intel Core Ultra, LM Studio runs Kaizen's AI faster on the processor and Intel graphics")
    else:
        add("npu", "NPU (AI chip)", npus[0]["name"] if npus else "None found", "info",
            "LM Studio will run the AI on the processor and graphics instead")
    add("gpu", "Graphics", ", ".join(g["name"] for g in gpus) or "unknown", "ok")
    add("disk", "Free space", f"{free_install:.0f} GB", "ok" if free_install >= 6 else "warn" if free_install >= 1 else "bad",
        "" if free_install >= 6 else "AI models need about 3–5 GB")
    add("edge", "Microsoft Edge", "found" if edge() else "missing", "ok" if edge() else "warn",
        "" if edge() else "Kaizen will open in your default browser instead")

    flm_ready = bool(win11 and amd_npu and xdna2 and arch == "AMD64")
    engines = {
        "flm": {
            "available": flm_ready,
            "installed": bool(flm),
            "version": flm_version() if flm else "",
            "model_ready": FLM_MODEL in models,
            "driver_ok": driver_ok,
            "reason": "" if flm_ready else (
                "Needs Windows 11" if not win11 else
                "Needs an AMD Ryzen AI 300/400 or Ryzen AI Max processor with an XDNA 2 NPU"),
            "download_gb": (0 if flm else 0.033) + (0 if FLM_MODEL in models else 3.1),
            "pinned": safety.FLM_VERSION,
        },
        "lmstudio": {  # a leftover lms.exe without the app doesn't count: the CLI needs the app installed
            "available": arch in ("AMD64", "ARM64") and ram >= 8,
            "installed": bool(lms_app),
            "cli": bool(lms),
            "reason": "" if ram >= 8 else "Needs at least 8 GB of memory",
            "download_gb": (0 if lms_app else (0.49 if arch == "ARM64" else 0.62)) + 2.5,
        },
    }
    recommend = "flm" if flm_ready else "lmstudio" if engines["lmstudio"]["available"] else "none"
    can_install = build >= 17763 and arch in ("AMD64", "ARM64") and free_install >= 0.3
    return {
        "checks": checks, "engines": engines, "recommend": recommend, "can_install": can_install,
        "arch": arch, "cpu": cpu, "ram": ram, "existing": existing, "free_docs_gb": round(free_docs, 1),
        "app_folder": APP,
        "default_dir": existing or (os.path.join(TEST, "Kaizen 5S") if TEST else
                                    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Kaizen 5S")),
    }


# ======================================================================= install

class Job:
    def __init__(self):
        self.running = False
        self.done = False
        self.error = ""
        self.steps = []
        self.wait = None          # {"kind": ..., "text": ...} when the person has to do something
        self.answer = threading.Event()
        self.answer_value = None
        self.cancelled = False
        self.result = {}

    def step(self, key, label):
        s = {"key": key, "label": label, "state": "active", "detail": "", "pct": None}
        self.steps.append(s)
        log(label)
        return s

    def ask(self, kind, text, actions):
        self.answer.clear()
        self.wait = {"kind": kind, "text": text, "actions": actions}
        self.answer.wait()
        self.wait = None
        return self.answer_value


job = Job()


def download(url, dest, step):
    """Stream a download to disk with live progress. Simulated in test mode."""
    if TEST:
        for i in range(21):
            step["pct"], step["detail"] = i * 5, f"Test mode: simulated download {i * 5}%"
            time.sleep(0.08)
        return False
    req = urllib.request.Request(url, headers={"User-Agent": f"Kaizen5S-Setup/{VERSION}"})
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
            speed = got / max(time.time() - t0, 0.1)
            step["pct"] = round(got * 100 / total) if total else None
            step["detail"] = (f"{got / 2**20:.0f} of {total / 2**20:.0f} MB · {speed / 2**20:.1f} MB/s" if total
                              else f"{got / 2**20:.0f} MB")
    os.replace(dest + ".part", dest)
    return True


def powershell(script):
    return subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                          capture_output=True, text=True, timeout=120, creationflags=CREATE_NO_WINDOW)


def make_shortcut(lnk, target, args, workdir, icon, description):
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:K_LNK);$s.TargetPath=$env:K_TARGET;"
          "$s.Arguments=$env:K_ARGS;$s.WorkingDirectory=$env:K_DIR;$s.IconLocation=$env:K_ICON;"
          "$s.Description=$env:K_DESC;$s.Save()")
    env = dict(os.environ, K_LNK=lnk, K_TARGET=target, K_ARGS=args, K_DIR=workdir, K_ICON=icon + ",0",
               K_DESC=description)
    subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], env=env,
                   capture_output=True, timeout=60, creationflags=CREATE_NO_WINDOW)


def kaizen_running():
    return safety.app_running(os.path.expandvars(r"%LOCALAPPDATA%\Kaizen5S"))


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
        engine = opts.get("engine", "none")

        # 1. Kaizen itself
        s = job.step("copy", "Installing Kaizen 5S")
        while kaizen_running() and not TEST:
            if job.ask("close_kaizen", "Kaizen is open. Close its window so the installer can update it.",
                       ["I closed it", "Cancel"]) == "Cancel":
                raise RuntimeError("Cancelled")
        os.makedirs(target, exist_ok=True)
        for part in ("runtime", "app"):
            dst = os.path.join(target, part)
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(os.path.join(ROOT, part), dst)
            s["detail"] = f"Copied {part}"
        shutil.copy2(os.path.join(HERE, "uninstall.py"), os.path.join(target, "uninstall.py"))
        pyw = os.path.join(target, "runtime", "pythonw.exe")
        app_py = os.path.join(target, "app", "app.py")
        icon = os.path.join(target, "app", "kaizen-sei.ico")
        safety.write_manifest(target, VERSION)   # the uninstaller removes exactly these files
        s["state"], s["detail"] = "done", target

        # 2. Shortcuts + Apps & features entry
        s = job.step("shortcuts", "Creating shortcuts")
        made = []
        lnk_dir = os.path.join(target, "test-shortcuts") if TEST else None
        if lnk_dir:
            os.makedirs(lnk_dir, exist_ok=True)
        if opts.get("desktop", True):
            lnk = os.path.join(lnk_dir or desktop(), f"{APP}.lnk")
            make_shortcut(lnk, pyw, f'"{app_py}"', os.path.dirname(app_py), icon, "Tidy your PC with 5S and local AI")
            made.append("Desktop")
        if opts.get("startmenu", True):
            menu = lnk_dir or os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")
            make_shortcut(os.path.join(menu, f"{APP}.lnk"), pyw, f'"{app_py}"', os.path.dirname(app_py), icon,
                          "Tidy your PC with 5S and local AI")
            made.append("Start menu")
        if not TEST:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
                for name, value in (("DisplayName", DISPLAY_NAME), ("DisplayVersion", VERSION), ("Publisher", PUBLISHER),
                                    ("DisplayIcon", icon), ("InstallLocation", target),
                                    ("UninstallString", f'"{pyw}" "{os.path.join(target, "uninstall.py")}"'),
                                    ("Comments", "Free and open source (MIT License)"),
                                    ("URLInfoAbout", "https://opensource.org/license/mit")):
                    winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
                winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, dir_size(target) // 1024)
            made.append("Apps & features")
        s["state"], s["detail"] = "done", ", ".join(made) or "None"

        # 3. AI engine
        if engine == "flm":
            install_flm()
        elif engine == "lmstudio":
            install_lmstudio()
        job.result = {"pythonw": pyw, "app": app_py}
        job.done = True
    except Exception as e:  # noqa: BLE001
        job.error = str(e)
        log("ERROR " + traceback.format_exc())
        for st in job.steps:
            if st["state"] == "active":
                st["state"] = "failed"
    finally:
        job.running = False


def install_flm():
    if not flm_exe() or TEST:
        s = job.step("flm", f"Installing FastFlowLM {safety.FLM_VERSION} (NPU engine)")
        with safety.PrivateDownload() as dl:
            msi = dl.path("flm-setup.msi")
            if download(safety.FLM_MSI_URL, msi, s):
                s["pct"], s["detail"] = None, "Checking the download…"
                safety.verify(msi, sha=safety.FLM_MSI_SHA256)   # pinned: the MSI is not code-signed
                s["detail"] = "Windows will ask for permission. Please click Yes."
                rc = subprocess.run(["msiexec.exe", "/i", msi, "/passive", "/norestart"]).returncode
                if rc not in (0, 3010):
                    raise RuntimeError(f"FastFlowLM's installer stopped (code {rc}). You can install it later from "
                                       "github.com/FastFlowLM/FastFlowLM.")
        s["state"], s["detail"] = "done", "Installed" if not TEST else "Test mode"
    s = job.step("model", f"Downloading the AI model {FLM_MODEL} (about 3.1 GB)")
    if FLM_MODEL in flm_models() and not TEST:
        s["state"], s["detail"] = "done", "Already downloaded"
        return
    if TEST:
        download("", "", s)
        s["state"], s["detail"] = "done", "Test mode"
        return
    exe = flm_exe()
    if not exe:
        raise RuntimeError("FastFlowLM was not found after installing it. Restart Windows and run setup again.")
    folder = os.path.join(documents(), "flm", "models")
    before = dir_size(folder) if os.path.isdir(folder) else 0
    proc = subprocess.Popen([exe, "pull", FLM_MODEL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW)
    expected = 3.1 * 2 ** 30
    while proc.poll() is None:
        if job.cancelled:
            proc.terminate()
            raise RuntimeError("Cancelled")
        got = (dir_size(folder) if os.path.isdir(folder) else 0) - before
        s["pct"] = min(99, round(got * 100 / expected))
        s["detail"] = f"{got / 2**30:.2f} of about 3.1 GB"
        time.sleep(1)
    if FLM_MODEL not in flm_models():
        raise RuntimeError(f"The model did not finish downloading. Kaizen will retry, or run: flm pull {FLM_MODEL}")
    s["state"], s["pct"], s["detail"] = "done", 100, "Ready on the NPU"


def install_lmstudio():
    arch = "arm64" if system_check()["arch"] == "ARM64" else "x64"
    if not lmstudio_app() or TEST:
        s = job.step("lms", "Installing LM Studio")
        with safety.PrivateDownload() as dl:
            exe = dl.path(f"LM-Studio-Setup-{arch}.exe")
            if download(f"https://lmstudio.ai/download/latest/win32/{arch}", exe, s):
                s["pct"], s["detail"] = None, "Checking the download's signature…"
                safety.verify(exe, signer=LMS_SIGNER)   # LM Studio has no pinned build; its publisher signs it
                s["detail"] = "Follow LM Studio's installer window"
                subprocess.run([exe])
        s["state"], s["detail"] = "done", "Installed" if not TEST else "Test mode"
    s = job.step("lms_first", "Preparing LM Studio")
    if not TEST:
        while not lms_exe():
            app = lmstudio_app()
            if app:
                subprocess.Popen([app])
            answer = job.ask("open_lmstudio", "LM Studio has to be opened once to finish its setup. It should open "
                             "now. When you see its main window, come back and press Continue.",
                             ["Continue", "Skip the AI model"])
            if answer != "Continue":
                s["state"], s["detail"] = "skipped", "Download “Qwen3 4B” in LM Studio later"
                return
    s["state"], s["detail"] = "done", "Ready"
    s = job.step("model", "Downloading the AI model Qwen3 4B (about 2.5 GB)")
    if TEST:
        download("", "", s)
        s["state"], s["detail"] = "done", "Test mode"
        return
    for model in LMS_MODELS:
        s["detail"] = f"lms get {model}"
        proc = subprocess.Popen([lms_exe(), "get", model, "--yes"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                creationflags=CREATE_NO_WINDOW)
        try:
            proc.stdin.write("y\n")
            proc.stdin.close()
        except OSError:
            pass
        for line in proc.stdout:
            m = re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", line)
            if m:
                s["pct"] = min(99, round(float(m.group(1))))
            s["detail"] = line.strip()[-90:] or s["detail"]
            if job.cancelled:
                proc.terminate()
                raise RuntimeError("Cancelled")
        if proc.wait() == 0:
            s["state"], s["pct"], s["detail"] = "done", 100, "Ready in LM Studio"
            return
    s["state"] = "skipped"
    s["detail"] = "Couldn't download automatically. In LM Studio, search “Qwen3 4B” and download it."


# ======================================================================= web UI

info_cache = {}


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
            with open(os.path.join(ROOT, "app", "kaizen-icon.png"), "rb") as f:
                return self._send(200, f.read(), "image/png")
        if self.headers.get("X-Setup") != TOKEN:
            return self._send(403, {"error": "forbidden"})
        if path == "/api/info":
            if "system" not in info_cache:
                info_cache["system"] = system_check()
            with open(os.path.join(ROOT, "app", "LICENSE"), encoding="utf-8") as f:
                lic = f.read()
            return self._send(200, {"app": APP, "version": VERSION, "copyright": COPYRIGHT, "license": lic,
                                    "test": bool(TEST), "edition": EDITION, **info_cache["system"]})
        if path == "/api/progress":
            return self._send(200, {"running": job.running, "done": job.done, "error": job.error,
                                    "steps": job.steps, "wait": job.wait, "log": log_lines[-8:]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._ok() or self.headers.get("X-Setup") != TOKEN:
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        path = urlparse(self.path).path
        if path == "/api/ping":
            last_ping["t"] = time.time()
            return self._send(200, {"ok": True})
        if path == "/api/install":
            if not job.running:
                threading.Thread(target=install, args=(body,), daemon=True).start()
            return self._send(200, {"ok": True})
        if path == "/api/answer":
            job.answer_value = body.get("value")
            job.answer.set()
            return self._send(200, {"ok": True})
        if path == "/api/cancel":
            job.cancelled = True
            job.answer_value = "Cancel"
            job.answer.set()
            return self._send(200, {"ok": True})
        if path == "/api/launch" and job.result:
            subprocess.Popen([job.result["pythonw"], job.result["app"]], cwd=os.path.dirname(job.result["app"]))
            return self._send(200, {"ok": True})
        if path == "/api/open":
            url = body.get("url", "")
            if url in (safety.FLM_LICENSE_URL, "https://www.amd.com/en/support/download/drivers.html", "https://lmstudio.ai",
                       "https://github.com/FastFlowLM/FastFlowLM", "https://opensource.org/license/mit"):
                os.startfile(url)  # noqa: S606 - fixed allow-list
            return self._send(200, {"ok": True})
        if path == "/api/browse":
            return self._send(200, {"dir": pick_folder(body.get("dir", ""))})
        return self._send(404, {"error": "not found"})


def pick_folder(start):
    """Native folder picker (Shell.Application BrowseForFolder via PowerShell)."""
    ps = ("$f=(New-Object -ComObject Shell.Application).BrowseForFolder(0,'Choose where to install Kaizen 5S',"
          "0x51,0);if($f){$f.Self.Path}")
    try:
        out = powershell(ps).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    return os.path.join(out, "Kaizen 5S") if out and not out.lower().endswith("kaizen 5s") else (out or start)


last_ping = {"t": 0.0}


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
    browser = edge()
    window = None
    if TEST:
        os.makedirs(TEST, exist_ok=True)
        with open(os.path.join(TEST, "setup-port.txt"), "w") as f:
            f.write(str(PORT))
    if os.environ.get("KAIZEN_SETUP_HEADLESS"):
        pass  # test harness drives the UI itself
    elif browser:
        profile = os.path.join(os.environ.get("TEMP", HERE), f"kaizen-setup-window-{PORT}")
        window = subprocess.Popen([browser, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1020,720",
                                   "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"])
    else:
        os.startfile(url)  # noqa: S606
    started = time.time()
    while True:
        time.sleep(1)
        idle = time.time() - (last_ping["t"] or started)
        if job.running:
            continue  # never quit in the middle of an install
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
        with open(os.path.join(os.environ.get("TEMP", "."), "kaizen-setup-error.log"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
