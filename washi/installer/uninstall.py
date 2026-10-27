"""Washi uninstaller (run from Settings > Apps). Copyright (c) 2026 Alexander Gubric, MIT License.

Removes Washi, its shortcuts, its "Open with" entries and its Apps entry. FastFlowLM and its models are a separate
program and stay installed (it has its own uninstaller).

Only the files setup listed in install-manifest.json are removed, then the folders that are left empty, so files
that are not Washi's are never touched (even if someone put them into the install folder).
"""
import ctypes
import json
import os
import shutil
import subprocess
import tempfile
import winreg

APP = "Washi"
TARGET = os.path.dirname(os.path.abspath(__file__))
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Washi"
DATA = os.path.expandvars(r"%LOCALAPPDATA%\Washi")
MANIFEST = os.path.join(TARGET, "install-manifest.json")
MB_YESNO, MB_ICONQUESTION, MB_ICONINFO, IDYES = 0x4, 0x20, 0x40, 6
CREATE_NO_WINDOW = 0x08000000


def ask(text):
    return ctypes.windll.user32.MessageBoxW(None, text, f"Uninstall {APP}", MB_YESNO | MB_ICONQUESTION) == IDYES


def known_folder(guid):
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid), ctypes.byref(g))
    p = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) != 0:
        return None
    return p.value


def delete_tree(root, path):
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                delete_tree(root, path + "\\" + sub)
        winreg.DeleteKey(root, path)
    except OSError:
        pass


def removal_script():
    """A batch file that deletes the listed files and then the empty folders, after this process has exited
    (the running Python is one of the files). Without a manifest only the known top-level items are removed."""
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            m = json.load(f)
        files = [os.path.join(TARGET, p) for p in m.get("files", [])]
        dirs = sorted((os.path.join(TARGET, d) for d in m.get("dirs", [])), key=len, reverse=True)
    except (OSError, ValueError):
        files = [os.path.join(TARGET, f) for f in ("uninstall.py", f"{APP}.exe")]
        dirs = []
        for part in ("app", "runtime"):    # older versions: these two folders were always created by setup
            for dp, dns, fns in os.walk(os.path.join(TARGET, part)):
                files += [os.path.join(dp, f) for f in fns]
                dirs.append(dp)
        dirs.sort(key=len, reverse=True)
    q = lambda p: '"' + p.replace("%", "%%") + '"'  # noqa: E731
    lines = ["@echo off", "ping 127.0.0.1 -n 3 >nul"]
    lines += [f"del /f /q {q(p)} >nul 2>nul" for p in files + [MANIFEST]]
    lines += [f"rmdir {q(d)} >nul 2>nul" for d in dirs + [TARGET]]   # rmdir without /s: only if empty
    lines.append('(goto) 2>nul & del /f /q "%~f0"')   # delete this script without cmd complaining
    fd, path = tempfile.mkstemp(prefix=f"{APP.lower()}-uninstall-", suffix=".cmd")
    with os.fdopen(fd, "w", encoding="mbcs", errors="replace", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main():
    if not ask("Remove Washi from this PC?\n\nYour PDF files are not touched. FastFlowLM and its AI models stay "
               "installed; you can remove them separately in Settings → Apps."):
        return
    keep_data = not ask("Also delete Washi's settings, recent-files list and saved signature?")

    ps = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | "
          "Where-Object { $_.CommandLine -like ('*' + $env:K_TARGET + '*') -and $_.ProcessId -ne $env:K_SELF } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, timeout=60,
                   env=dict(os.environ, K_TARGET=TARGET, K_SELF=str(os.getpid())), creationflags=CREATE_NO_WINDOW)

    desk = known_folder("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}") or os.path.expanduser(r"~\Desktop")
    for lnk in (os.path.join(desk, "Washi.lnk"), os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Washi.lnk")):
        try:
            os.remove(lnk)
        except OSError:
            pass
    hk = winreg.HKEY_CURRENT_USER
    for path in (UNINSTALL_KEY, r"Software\Classes\Washi.PDF", r"Software\Washi", r"Software\Classes\Applications\Washi.exe",
                 r"Software\Microsoft\Windows\CurrentVersion\App Paths\Washi.exe"):
        delete_tree(hk, path)
    for ext in (".pdf", ".xps", ".oxps", ".epub", ".mobi", ".fb2"):
        try:
            with winreg.OpenKey(hk, rf"Software\Classes\{ext}\OpenWithProgids", 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "Washi.PDF")
        except OSError:
            pass
    try:
        with winreg.OpenKey(hk, r"Software\RegisteredApplications", 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, "Washi")
    except OSError:
        pass
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
    if not keep_data:
        shutil.rmtree(DATA, ignore_errors=True)
    # the Edge window profiles of older setups stayed in %TEMP%
    for name in os.listdir(tempfile.gettempdir()):
        if name.lower().startswith("washi-setup-window-"):
            shutil.rmtree(os.path.join(tempfile.gettempdir(), name), ignore_errors=True)

    ctypes.windll.user32.MessageBoxW(None, "Washi has been removed. Thank you for using it!\n\nThe AI models FastFlowLM "
                                     "downloaded (2–3 GB) stay in Documents\\flm\\models; remove them with "
                                     "FastFlowLM's own uninstaller or by deleting that folder.", "Uninstall Washi", MB_ICONINFO)
    subprocess.Popen(["cmd.exe", "/c", removal_script()], creationflags=CREATE_NO_WINDOW, cwd=os.path.dirname(TARGET))


if __name__ == "__main__":
    main()
