"""Native Windows dialogs through ctypes (no tkinter, so the installed runtime stays small)."""
import ctypes
import os
import subprocess
import threading
from ctypes import wintypes

CREATE_NO_WINDOW = 0x08000000
_dialog = threading.Lock()
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


def _open_files(title):
    buf = ctypes.create_unicode_buffer(1 << 17)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = ctypes.windll.user32.GetForegroundWindow()   # opens on top of the Morph window
    ofn.lpstrFilter = "All files (*.*)\0*.*\0\0"
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = len(buf)
    ofn.lpstrTitle = title
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


def _in_thread(fn, *args):
    """Common dialogs need a COM apartment; each runs in its own short-lived thread."""
    out = {}

    def run():
        ctypes.windll.ole32.CoInitializeEx(None, 2)
        try:
            out["v"] = fn(*args)
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
    return out.get("v") or []


def pick_files(title="Choose files to convert"):
    return _in_thread(_open_files, title)


def pick_folder(title, start=""):
    ps = ("$f=(New-Object -ComObject Shell.Application).BrowseForFolder(0,$env:M_TITLE,0x51,0);if($f){$f.Self.Path}")
    with _dialog:
        try:
            out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                                 timeout=600, env=dict(os.environ, M_TITLE=title),
                                 creationflags=CREATE_NO_WINDOW).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            out = ""
    return out if out and os.path.isdir(out) else None
