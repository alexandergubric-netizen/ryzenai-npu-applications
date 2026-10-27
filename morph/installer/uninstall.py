"""Morph uninstaller (run from Settings > Apps). Copyright (c) 2026 Alexander Gubric, MIT License.

Removes Morph, its shortcuts and its Apps entry. Converted files are never touched. FastFlowLM and its models are a
separate program and stay installed (it has its own uninstaller).

Only the files setup listed in install-manifest.json are removed, then the folders that are left empty, so files
that are not the app's are never touched (even if someone put them into the install folder).
"""
import ctypes
import json
import os
import shutil
import subprocess
import tempfile
import winreg

TARGET = os.path.dirname(os.path.abspath(__file__))
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Morph"
APP_EXE = "Morph"
MANIFEST = os.path.join(TARGET, "install-manifest.json")
DATA = os.path.expandvars(r"%LOCALAPPDATA%\Morph")
MB_YESNO, MB_ICONQUESTION, MB_ICONINFO, IDYES = 0x4, 0x20, 0x40, 6
CREATE_NO_WINDOW = 0x08000000


def ask(text):
    return ctypes.windll.user32.MessageBoxW(None, text, "Uninstall Morph", MB_YESNO | MB_ICONQUESTION) == IDYES


def known_folder(guid):
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid), ctypes.byref(g))
    p = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) != 0:
        return None
    return p.value


def removal_script():
    """A batch file that deletes the listed files and then the empty folders, after this process has exited
    (the running Python is one of the files). Without a manifest only the known top-level items are removed."""
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            m = json.load(f)
        files = [os.path.join(TARGET, p) for p in m.get("files", [])]
        dirs = sorted((os.path.join(TARGET, d) for d in m.get("dirs", [])), key=len, reverse=True)
    except (OSError, ValueError):
        files = [os.path.join(TARGET, f) for f in ("uninstall.py", f"{APP_EXE}.exe")]
        dirs = []
        for part in ("app", "runtime", "tools"):    # older versions: setup always created these folders
            for dp, dns, fns in os.walk(os.path.join(TARGET, part)):
                files += [os.path.join(dp, f) for f in fns]
                dirs.append(dp)
        dirs.sort(key=len, reverse=True)
    q = lambda p: '"' + p.replace("%", "%%") + '"'  # noqa: E731
    lines = ["@echo off", "ping 127.0.0.1 -n 3 >nul"]
    lines += [f"del /f /q {q(p)} >nul 2>nul" for p in files + [MANIFEST]]
    lines += [f"rmdir {q(d)} >nul 2>nul" for d in dirs + [TARGET]]   # rmdir without /s: only if empty
    lines.append('(goto) 2>nul & del /f /q "%~f0"')   # delete this script without cmd complaining
    fd, path = tempfile.mkstemp(prefix=f"{APP_EXE.lower()}-uninstall-", suffix=".cmd")
    with os.fdopen(fd, "w", encoding="mbcs", errors="replace", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return path


def clean_temp(prefix):
    """Edge window profiles that older setups left in %TEMP%."""
    for name in os.listdir(tempfile.gettempdir()):
        if name.lower().startswith(prefix):
            shutil.rmtree(os.path.join(tempfile.gettempdir(), name), ignore_errors=True)


def main():
    if not ask("Remove Morph from this PC?\n\nYour converted files are not touched. FastFlowLM and its AI models "
               "(if installed) stay; you can remove them separately in Settings → Apps."):
        return
    keep_data = not ask("Also delete Morph's settings and logs?")

    ps = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe' or Name='ffmpeg.exe'\" | "
          "Where-Object { $_.CommandLine -like ('*' + $env:K_TARGET + '*') -and $_.ProcessId -ne $env:K_SELF } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, timeout=60,
                   env=dict(os.environ, K_TARGET=TARGET, K_SELF=str(os.getpid())), creationflags=CREATE_NO_WINDOW)

    desk = known_folder("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}") or os.path.expanduser(r"~\Desktop")
    for lnk in (os.path.join(desk, "Morph.lnk"), os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Morph.lnk")):
        try:
            os.remove(lnk)
        except OSError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except OSError:
        pass
    if not keep_data:
        shutil.rmtree(DATA, ignore_errors=True)

    ctypes.windll.user32.MessageBoxW(None, "Morph has been removed. Thank you for using it!", "Uninstall Morph", MB_ICONINFO)
    clean_temp("morph-setup-window-")
    subprocess.Popen(["cmd.exe", "/c", removal_script()], creationflags=CREATE_NO_WINDOW, cwd=os.path.dirname(TARGET))


if __name__ == "__main__":
    main()
