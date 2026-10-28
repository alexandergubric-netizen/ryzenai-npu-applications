"""Small Windows helpers: native pickers, Explorer, shortcuts (desktop + "Send to")."""
import ctypes
import os
import subprocess
import sys
import threading
from ctypes import wintypes

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREATE_NO_WINDOW = 0x08000000
_dialog = threading.Lock()
SENDTO = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "SendTo", "Tansu (archive).lnk")


def edge_exe():
    for p in (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
              os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")):
        if os.path.exists(p):
            return p
    return None


def bring_to_front():
    """Raise the open Tansu window (an Edge app window titled "Tansu" / "… — Tansu"). The process that calls this
    was just started by the person (shortcut, Send to), which is what Windows needs to allow it."""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value
                if title == "Tansu" or title.endswith(" — Tansu") or title.endswith(" - Tansu"):
                    found.append(hwnd)
        return True
    user32.EnumWindows(visit, 0)
    if not found:
        return False
    hwnd = found[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)   # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


OFN_HIDEREADONLY, OFN_NOCHANGEDIR, OFN_ALLOWMULTISELECT = 0x4, 0x8, 0x200
OFN_PATHMUSTEXIST, OFN_FILEMUSTEXIST, OFN_EXPLORER, OFN_ENABLESIZING = 0x800, 0x1000, 0x80000, 0x800000


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND), ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR), ("lpstrCustomFilter", wintypes.LPWSTR),
                ("nMaxCustFilter", wintypes.DWORD), ("nFilterIndex", wintypes.DWORD), ("lpstrFile", wintypes.LPWSTR),
                ("nMaxFile", wintypes.DWORD), ("lpstrFileTitle", wintypes.LPWSTR), ("nMaxFileTitle", wintypes.DWORD),
                ("lpstrInitialDir", wintypes.LPCWSTR), ("lpstrTitle", wintypes.LPCWSTR), ("Flags", wintypes.DWORD),
                ("nFileOffset", wintypes.WORD), ("nFileExtension", wintypes.WORD), ("lpstrDefExt", wintypes.LPCWSTR),
                ("lCustData", wintypes.LPARAM), ("lpfnHook", ctypes.c_void_p), ("lpTemplateName", wintypes.LPCWSTR),
                ("pvReserved", ctypes.c_void_p), ("dwReserved", wintypes.DWORD), ("FlagsEx", wintypes.DWORD)]


def _open_files(title, initial):
    buf = ctypes.create_unicode_buffer(1 << 17)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = ctypes.windll.user32.GetForegroundWindow()   # opens on top of the Tansu window
    ofn.lpstrFilter = "All files (*.*)\0*.*\0\0"
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = len(buf)
    ofn.lpstrTitle = title
    ofn.lpstrInitialDir = initial
    ofn.Flags = (OFN_EXPLORER | OFN_NOCHANGEDIR | OFN_HIDEREADONLY | OFN_ENABLESIZING | OFN_PATHMUSTEXIST
                 | OFN_FILEMUSTEXIST | OFN_ALLOWMULTISELECT)
    if not ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
        return []
    parts = ctypes.wstring_at(ctypes.addressof(buf), len(buf)).split("\0")
    names = []
    for p in parts[1:]:
        if not p:
            break
        names.append(p)
    return [os.path.join(parts[0], n) for n in names] if names else [parts[0]]


def _pick_folder(title):
    ps = "$f=(New-Object -ComObject Shell.Application).BrowseForFolder(0,$env:T_TITLE,0x51,0);if($f){$f.Self.Path}"
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             timeout=600, env=dict(os.environ, T_TITLE=title),
                             creationflags=CREATE_NO_WINDOW).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    return [os.path.normpath(out)] if out and os.path.isdir(out) else []


def pick(kind="files", title=None, initial=None):
    """Native Windows dialogs through ctypes/Shell (no tkinter: the bundled runtime has none). kind: files | folder."""
    if kind == "folder":
        with _dialog:
            return _pick_folder(title or "Choose a folder")
    out = {}

    def run():   # common dialogs need a COM apartment of their own
        ctypes.windll.ole32.CoInitializeEx(None, 2)
        try:
            out["v"] = _open_files(title or "Choose files", initial)
        except Exception as e:  # noqa: BLE001
            out["e"] = e
        finally:
            ctypes.windll.ole32.CoUninitialize()
    with _dialog:
        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join()
    if "e" in out:
        raise out["e"]
    return [os.path.normpath(p) for p in out.get("v") or []]


def reveal(path):
    if os.path.isdir(path):
        os.startfile(path)
    elif os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", path])


def pythonw():
    bundled = os.path.join(HERE, "runtime", "pythonw.exe")   # Tansu's own Python, independent of a system install
    if os.path.exists(bundled):
        return bundled
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return w if os.path.exists(w) else exe


def _shortcut(lnk, target, args, workdir, icon, desc):
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:K_LNK);"
          "$s.TargetPath=$env:K_TARGET;$s.Arguments=$env:K_ARGS;$s.WorkingDirectory=$env:K_DIR;"
          "$s.IconLocation=$env:K_ICON;$s.Description=$env:K_DESC;$s.Save()")
    env = {**os.environ, "K_LNK": lnk, "K_TARGET": target, "K_ARGS": args, "K_DIR": workdir,
           "K_ICON": icon, "K_DESC": desc}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env,
                   creationflags=CREATE_NO_WINDOW, timeout=30, check=True)


def app_shortcut(lnk):
    _shortcut(lnk, pythonw(), f'"{os.path.join(HERE, "app.py")}"', HERE, os.path.join(HERE, "tansu.ico") + ",0",
              "Tansu - smart archiver (local AI on the Ryzen NPU)")


def sendto_installed():
    return os.path.exists(SENDTO)


def set_sendto(on):
    if on:
        app_shortcut(SENDTO)
    elif os.path.exists(SENDTO):
        os.remove(SENDTO)
    return sendto_installed()
