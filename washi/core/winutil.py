"""Windows helpers: native Open/Save dialogs (comdlg32 through ctypes, no tkinter), Edge, Explorer, shortcuts."""
import ctypes
import os
import subprocess
import sys
import threading
from ctypes import wintypes

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREATE_NO_WINDOW = 0x08000000
_dialog = threading.Lock()

OFN_OVERWRITEPROMPT = 0x2
OFN_HIDEREADONLY = 0x4
OFN_NOCHANGEDIR = 0x8
OFN_ALLOWMULTISELECT = 0x200
OFN_PATHMUSTEXIST = 0x800
OFN_FILEMUSTEXIST = 0x1000
OFN_EXPLORER = 0x80000
OFN_ENABLESIZING = 0x800000

FILTERS = {
    "pdf": [("PDF documents", "*.pdf")],
    "openable": [("PDFs, e-books and images", "*.pdf;*.epub;*.mobi;*.fb2;*.cbz;*.xps;*.oxps;*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff;*.webp"),
                 ("PDF documents", "*.pdf"), ("E-books", "*.epub;*.mobi;*.fb2;*.cbz"), ("All files", "*.*")],
    "image": [("Images", "*.png;*.jpg;*.jpeg;*.bmp;*.gif;*.tif;*.tiff;*.webp"), ("All files", "*.*")],
    "txt": [("Text", "*.txt")],
    "md": [("Markdown", "*.md")],
    "html": [("Web page", "*.html")],
    "docx": [("Word document", "*.docx")],
    "png": [("PNG image", "*.png")],
    "jpg": [("JPEG image", "*.jpg")],
    "any": [("All files", "*.*")],
}


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [("lStructSize", wintypes.DWORD), ("hwndOwner", wintypes.HWND), ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR), ("lpstrCustomFilter", wintypes.LPWSTR),
                ("nMaxCustFilter", wintypes.DWORD), ("nFilterIndex", wintypes.DWORD), ("lpstrFile", wintypes.LPWSTR),
                ("nMaxFile", wintypes.DWORD), ("lpstrFileTitle", wintypes.LPWSTR), ("nMaxFileTitle", wintypes.DWORD),
                ("lpstrInitialDir", wintypes.LPCWSTR), ("lpstrTitle", wintypes.LPCWSTR), ("Flags", wintypes.DWORD),
                ("nFileOffset", wintypes.WORD), ("nFileExtension", wintypes.WORD), ("lpstrDefExt", wintypes.LPCWSTR),
                ("lCustData", wintypes.LPARAM), ("lpfnHook", ctypes.c_void_p), ("lpTemplateName", wintypes.LPCWSTR),
                ("pvReserved", ctypes.c_void_p), ("dwReserved", wintypes.DWORD), ("FlagsEx", wintypes.DWORD)]


def _filter_string(kind):
    parts = []
    for label, pattern in FILTERS.get(kind, FILTERS["any"]):
        parts += [f"{label} ({pattern.replace(';', ', ')})", pattern]
    return "\0".join(parts) + "\0\0"


def _dialog_call(save, kind, title, initial_dir, default_name, multi):
    buf = ctypes.create_unicode_buffer(default_name or "", 65536)
    flt = _filter_string(kind)
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    # owned by the foreground window (the Washi window) so the dialog opens on top of it
    ofn.hwndOwner = ctypes.windll.user32.GetForegroundWindow()
    ofn.lpstrFilter = flt
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = len(buf)
    ofn.lpstrTitle = title
    ofn.lpstrInitialDir = initial_dir if initial_dir and os.path.isdir(initial_dir) else None
    ext = FILTERS.get(kind, FILTERS["any"])[0][1].split(";")[0].replace("*.", "")
    ofn.lpstrDefExt = None if ext == "*" else ext
    ofn.Flags = OFN_EXPLORER | OFN_NOCHANGEDIR | OFN_HIDEREADONLY | OFN_ENABLESIZING | OFN_PATHMUSTEXIST
    if save:
        ofn.Flags |= OFN_OVERWRITEPROMPT
        ok = ctypes.windll.comdlg32.GetSaveFileNameW(ctypes.byref(ofn))
    else:
        ofn.Flags |= OFN_FILEMUSTEXIST | (OFN_ALLOWMULTISELECT if multi else 0)
        ok = ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn))
    if not ok:
        return []
    raw = ctypes.wstring_at(ctypes.addressof(buf), len(buf))
    parts = raw.split("\0")
    if save or not multi:
        return [parts[0]]
    names = []
    for p in parts[1:]:
        if not p:
            break
        names.append(p)
    if not names:
        return [parts[0]]
    return [os.path.join(parts[0], n) for n in names]


def _run_in_thread(fn, *args):
    """Common dialogs need a thread with COM initialised; run each in its own short-lived thread."""
    out = {}

    def run():
        ctypes.windll.ole32.CoInitializeEx(None, 2)   # apartment threaded
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


def pick_open(kind="openable", title="Open", initial_dir=None, multi=True):
    return _run_in_thread(_dialog_call, False, kind, title, initial_dir, "", multi)


def pick_save(kind="pdf", title="Save as", initial_dir=None, default_name=""):
    r = _run_in_thread(_dialog_call, True, kind, title, initial_dir, default_name, False)
    return r[0] if r else None


def edge_exe():
    for p in (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
              os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")):
        if os.path.exists(p):
            return p
    return None


def bring_to_front():
    """Raise the open Washi window (an Edge app window titled "Washi" / "… — Washi"). The process that calls this
    was just started by the person (double-click, Open with), which is what Windows needs to allow it."""
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
                if title == "Washi" or title.endswith(" — Washi") or title.endswith(" - Washi"):
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


def reveal(path):
    if os.path.isdir(path):
        os.startfile(path)
    elif os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", path])


def documents():
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"), ctypes.byref(g))
    p = ctypes.c_wchar_p()
    if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0 and p.value:
        return p.value
    return os.path.expanduser(r"~\Documents")


def pythonw():
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return w if os.path.exists(w) else exe


def shortcut(lnk, target, args, workdir, icon, desc):
    ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:K_LNK);"
          "$s.TargetPath=$env:K_TARGET;$s.Arguments=$env:K_ARGS;$s.WorkingDirectory=$env:K_DIR;"
          "$s.IconLocation=$env:K_ICON;$s.Description=$env:K_DESC;$s.Save()")
    env = {**os.environ, "K_LNK": lnk, "K_TARGET": target, "K_ARGS": args, "K_DIR": workdir,
           "K_ICON": icon, "K_DESC": desc}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env=env,
                   creationflags=CREATE_NO_WINDOW, timeout=30, check=True)
