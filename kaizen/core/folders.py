"""Folders to scan: what kind of place a folder is, whether you may use it, and a native folder picker.

Access is checked with the same permission test Windows uses (CreateFile with the wanted access rights), so
nothing is ever created, changed or deleted while checking - safe on shared network drives.
"""
import ctypes
import os
import threading
import time
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32")
user32 = ctypes.WinDLL("user32")

kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                 wintypes.DWORD, wintypes.HANDLE]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
kernel32.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p, wintypes.LPWSTR, wintypes.DWORD]
user32.GetForegroundWindow.restype = wintypes.HWND
ole32.CoCreateInstance.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
ole32.CoTaskMemFree.restype = None

INVALID = wintypes.HANDLE(-1).value
FILE_LIST_DIRECTORY, FILE_ADD_FILE, FILE_DELETE_CHILD, DELETE = 0x1, 0x2, 0x40, 0x10000
SHARE_ALL = 0x1 | 0x2 | 0x4
OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS = 3, 0x02000000
DRIVE_KIND = {2: "removable", 3: "local", 4: "network", 5: "optical", 6: "ramdisk"}

_kind_cache = {}


def _can_open(path, access):
    h = kernel32.CreateFileW(path, access, SHARE_ALL, None, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None)
    if h in (None, INVALID):
        return False
    kernel32.CloseHandle(h)
    return True


def volume(path):
    """(kind, filesystem, label) of the drive or share holding `path`."""
    p = os.path.abspath(path)
    if p.startswith("\\\\"):
        parts = p.split("\\")
        root = "\\\\" + "\\".join(parts[2:4]) + "\\"
    else:
        root = os.path.splitdrive(p)[0] + "\\"
    if root in _kind_cache:
        return _kind_cache[root]
    kind = "network" if p.startswith("\\\\") else DRIVE_KIND.get(kernel32.GetDriveTypeW(root), "local")
    label, fs = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
    ok = kernel32.GetVolumeInformationW(root, label, 261, None, None, None, fs, 261)
    fs_name = fs.value if ok else ""
    if kind == "local" and ("fuse" in fs_name.lower() or "rclone" in fs_name.lower()):
        kind = "cloud"   # e.g. Google Drive / Uloz.to mounted with rclone: reading files downloads them
    home = os.path.expanduser("~").lower()
    if kind == "local" and any(p.lower().startswith(os.path.join(home, c).lower())
                               for c in ("OneDrive", "Dropbox", "Google Drive", "iCloudDrive", "Box")):
        kind = "cloud"
    result = (kind, fs_name, label.value if ok else "")
    _kind_cache[root] = result
    return result


def no_recycle_bin(path):
    """Network shares and removable drives have no Recycle Bin - deleting there would be permanent."""
    return volume(path)[0] in ("network", "removable", "optical")


def _check(path, out):
    t0 = time.time()
    out["exists"] = os.path.isdir(path)
    if not out["exists"]:
        out["error"] = "Folder not found, or the network location can't be reached."
        return
    out["read"] = _can_open(path, FILE_LIST_DIRECTORY)
    out["write"] = _can_open(path, FILE_ADD_FILE)
    out["delete"] = _can_open(path, FILE_DELETE_CHILD)
    files = dirs = 0
    try:
        with os.scandir(path) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False):
                    dirs += 1
                else:
                    files += 1
                if files + dirs >= 2000:
                    break
                if not out["delete"] and files == 1 and not e.is_dir(follow_symlinks=False):
                    out["delete"] = _can_open(e.path, DELETE)  # some shares grant delete per file, not per folder
    except PermissionError:
        out["read"] = False
    except OSError as e:
        out["error"] = f"Couldn't list the folder: {e.strerror or e}"
    out["files"], out["dirs"] = files, dirs
    out["ms"] = round((time.time() - t0) * 1000)


def check(path, edition_org=""):
    """Everything the folder dialog shows about a folder. Times out instead of hanging on a dead network share."""
    path = os.path.normpath(os.path.expandvars(path.strip().strip('"'))) if path.strip() else ""
    out = {"path": path, "exists": False, "read": False, "write": False, "delete": False, "files": 0, "dirs": 0,
           "ms": None, "error": "", "warnings": []}
    if not path:
        out["error"] = "Type or choose a folder first."
        return out
    if not (path.startswith("\\\\") or (len(path) >= 3 and path[1:3] == ":\\")):
        out["error"] = "Use a full path like D:\\Projects or \\\\server\\share\\folder."
        return out
    kind, fs, label = volume(path)
    out.update(kind=kind, fs=fs, label=label)
    worker = threading.Thread(target=_check, args=(path, out), daemon=True)
    worker.start()
    worker.join(12)
    if worker.is_alive():
        out["error"] = "No answer after 12 seconds. The network location may be offline or very slow."
        return out
    w = out["warnings"]
    if kind == "network":
        w.append("Network folder: scanning reads every file name over the network and can take a long time. "
                 "Files here may belong to other people, so only add folders you're allowed to tidy.")
        w.append("Network folders have no Recycle Bin, so Kaizen never deletes files here. It only shows them and can "
                 "move or rename them if you have permission.")
        if edition_org:
            w.append(f"Follow {edition_org}'s IT rules for shared drives.")
    elif kind == "cloud":
        w.append("Cloud-synced folder: Kaizen won't download files to read them, but thousands of files can still be "
                 "slow to scan.")
    elif kind in ("removable", "optical"):
        w.append("Removable drive: it has no Recycle Bin, so Kaizen never deletes files here.")
    if out["exists"] and not out["read"]:
        out["error"] = "You don't have permission to see what's in this folder."
    elif out["exists"] and not out["write"]:
        w.append("Read-only for you: Kaizen can show results here but can't move, rename or clean anything.")
    if out["ms"] and out["ms"] > 3000:
        w.append(f"This location answers slowly ({out['ms'] / 1000:.1f} s for the first files). A scan may take a while.")
    return out


# ------------------------------------------------------------------ native folder picker (modern Explorer dialog)

class GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]


def _guid(s):
    g = GUID()
    ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
    return g


def _vcall(obj, index, *argtypes):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])


def pick_folder(title="Choose a folder for Kaizen to check"):
    """Explorer's folder picker (supports typing \\\\server\\share). Returns a path or '' if cancelled."""
    owner = user32.GetForegroundWindow()  # the Kaizen window - keeps the dialog on top of it
    ole32.CoInitializeEx(None, 0x2)
    dlg = ctypes.c_void_p()
    try:
        hr = ole32.CoCreateInstance(ctypes.byref(_guid("{DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7}")), None, 1,
                                    ctypes.byref(_guid("{d57c7288-d4ad-4768-be02-9d969532d960}")), ctypes.byref(dlg))
        if hr != 0 or not dlg:
            return ""
        _vcall(dlg, 9, wintypes.DWORD)(dlg, 0x20 | 0x40 | 0x800)          # SetOptions: pick folders, file system
        _vcall(dlg, 17, wintypes.LPCWSTR)(dlg, title)                     # SetTitle
        _vcall(dlg, 18, wintypes.LPCWSTR)(dlg, "Choose this folder")       # SetOkButtonLabel
        if _vcall(dlg, 3, wintypes.HWND)(dlg, owner) != 0:                 # Show (cancelled -> non-zero)
            return ""
        item = ctypes.c_void_p()
        if _vcall(dlg, 20, ctypes.POINTER(ctypes.c_void_p))(dlg, ctypes.byref(item)) != 0:   # GetResult
            return ""
        try:
            name = ctypes.c_wchar_p()
            if _vcall(item, 5, ctypes.c_int, ctypes.POINTER(ctypes.c_wchar_p))(item, 0x80058000, ctypes.byref(name)):
                return ""
            try:
                return name.value or ""
            finally:
                ole32.CoTaskMemFree(ctypes.cast(name, ctypes.c_void_p))
        finally:
            _vcall(item, 2)(item)
    finally:
        if dlg:
            _vcall(dlg, 2)(dlg)
        ole32.CoUninitialize()
