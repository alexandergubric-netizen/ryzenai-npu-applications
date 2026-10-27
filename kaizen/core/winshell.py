"""Thin ctypes wrappers around the Windows shell APIs Kaizen needs.

Everything here is native Win32 - no extra packages except Pillow for image encoding.
"""
import ctypes
import glob
import os
import re
import struct
import subprocess
import threading
from contextlib import contextmanager
from ctypes import wintypes

ole32 = ctypes.WinDLL("ole32")
shell32 = ctypes.WinDLL("shell32")
gdi32 = ctypes.WinDLL("gdi32")
user32 = ctypes.WinDLL("user32")
kernel32 = ctypes.WinDLL("kernel32")


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long), ("bmPlanes", ctypes.c_ushort),
                ("bmBitsPixel", ctypes.c_ushort), ("bmBits", ctypes.c_void_p)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32), ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16), ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32), ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32), ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32), ("biClrImportant", ctypes.c_uint32)]


ole32.CLSIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(GUID)]
ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
ole32.CoTaskMemFree.restype = None
shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                         ctypes.POINTER(ctypes.c_wchar_p)]
shell32.SHGetKnownFolderPath.restype = ctypes.c_long
shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(GUID),
                                                ctypes.POINTER(ctypes.c_void_p)]
shell32.SHCreateItemFromParsingName.restype = ctypes.c_long
shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                  wintypes.LPCWSTR, ctypes.c_int]
shell32.ShellExecuteW.restype = ctypes.c_void_p
gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                            ctypes.c_void_p, wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
kernel32.QueryDosDeviceW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]

IID_IShellItemImageFactory = "{bcc18b79-ba16-442f-80c4-8a59c30c463b}"

# SIIGBF flags
THUMB_ANY = 0x0
THUMB_ICON_ONLY = 0x4
THUMB_IN_CACHE_ONLY = 0x10

# File attributes
ATTR_HIDDEN = 0x2
ATTR_SYSTEM = 0x4
ATTR_OFFLINE = 0x1000
ATTR_RECALL_ON_OPEN = 0x40000
ATTR_RECALL_ON_DATA_ACCESS = 0x400000
CLOUD_ATTRS = ATTR_OFFLINE | ATTR_RECALL_ON_OPEN | ATTR_RECALL_ON_DATA_ACCESS


def guid(text):
    g = GUID()
    ole32.CLSIDFromString(text, ctypes.byref(g))
    return g


def known_folder(guid_text):
    """Resolve a Known Folder GUID (follows OneDrive / user redirection)."""
    out = ctypes.c_wchar_p()
    try:
        if shell32.SHGetKnownFolderPath(ctypes.byref(guid(guid_text)), 0, None, ctypes.byref(out)) != 0:
            return None
        return out.value
    except OSError:
        return None
    finally:
        if out:
            ole32.CoTaskMemFree(out)


def _method(obj, index, *argtypes):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])


def _hbitmap_to_image(hbmp):
    from PIL import Image
    bm = BITMAP()
    gdi32.GetObjectW(hbmp, ctypes.sizeof(bm), ctypes.byref(bm))
    w, h = bm.bmWidth, abs(bm.bmHeight)
    if w <= 0 or h <= 0:
        return None
    bih = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    hdc = user32.GetDC(None)
    try:
        gdi32.GetDIBits(hdc, hbmp, 0, h, buf, ctypes.byref(bih), 0)
    finally:
        user32.ReleaseDC(None, hdc)
    raw = buf.raw
    if not raw[3::4].strip(b"\x00"):
        # Photo thumbnails come back without an alpha channel.
        return Image.frombuffer("RGB", (w, h), raw, "raw", "BGRX", 0, 1)
    # Icons are premultiplied BGRA.
    img = Image.frombuffer("RGBa", (w, h), raw, "raw", "BGRa", 0, 1)
    return img.convert("RGBA")


def shell_image(path, size=256, flags=THUMB_ANY):
    """Return a PIL image with the same thumbnail/icon File Explorer shows."""
    ole32.CoInitializeEx(None, 0x2)
    try:
        factory = ctypes.c_void_p()
        hr = shell32.SHCreateItemFromParsingName(path, None, ctypes.byref(guid(IID_IShellItemImageFactory)),
                                                 ctypes.byref(factory))
        if hr != 0 or not factory:
            return None
        try:
            hbmp = wintypes.HBITMAP()
            get_image = _method(factory, 3, SIZE, ctypes.c_int, ctypes.POINTER(wintypes.HBITMAP))
            hr = get_image(factory, SIZE(size, size), flags, ctypes.byref(hbmp))
            if hr != 0 or not hbmp:
                return None
            try:
                return _hbitmap_to_image(hbmp)
            finally:
                gdi32.DeleteObject(hbmp)
        finally:
            _method(factory, 2)(factory)
    finally:
        ole32.CoUninitialize()


@contextmanager
def preserve_atime(path):
    """Reading a file for thumbnails/AI must not make it look 'recently used'."""
    try:
        st = os.stat(path)
    except OSError:
        st = None

    def restore():
        try:
            if os.stat(path).st_mtime_ns == st.st_mtime_ns:  # never touch a file that really changed meanwhile
                os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
        except OSError:
            pass

    try:
        yield
    finally:
        if st is not None:
            restore()
            # Antivirus scans triggered by icon extraction can touch the file a moment later.
            t = threading.Timer(4.0, restore)
            t.daemon = True
            t.start()


def _utf16z(data, pos):
    end = pos
    while end + 1 < len(data) and data[end:end + 2] != b"\x00\x00":
        end += 2
    return data[pos:end].decode("utf-16-le", "ignore")


def lnk_target(path):
    """Local target path of a .lnk shortcut, or None if it can't be determined."""
    try:
        with open(path, "rb") as f:
            data = f.read(65536)
        if data[:4] != b"\x4c\x00\x00\x00":
            return None
        flags = struct.unpack_from("<I", data, 0x14)[0]
        pos = 0x4C
        if flags & 0x01:  # HasLinkTargetIDList
            pos += 2 + struct.unpack_from("<H", data, pos)[0]
        if not flags & 0x02:  # HasLinkInfo
            return None
        li = pos
        header = struct.unpack_from("<I", data, li + 4)[0]
        li_flags = struct.unpack_from("<I", data, li + 8)[0]
        if not li_flags & 0x01:  # VolumeIDAndLocalBasePath
            return None
        if header >= 0x24:
            base = _utf16z(data, li + struct.unpack_from("<I", data, li + 0x1C)[0])
            suffix = _utf16z(data, li + struct.unpack_from("<I", data, li + 0x20)[0])
        else:
            off = li + struct.unpack_from("<I", data, li + 0x10)[0]
            base = data[off:data.index(b"\x00", off)].decode("mbcs", "ignore")
            soff = li + struct.unpack_from("<I", data, li + 0x18)[0]
            suffix = data[soff:data.index(b"\x00", soff)].decode("mbcs", "ignore")
        return base + suffix if base else None
    except (OSError, struct.error, ValueError):
        return None


def device_map():
    """Map \\Device\\HarddiskVolumeN -> C: (used to decode BAM paths)."""
    out = {}
    buf = ctypes.create_unicode_buffer(1024)
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        if kernel32.QueryDosDeviceW(f"{letter}:", buf, 1024):
            out[buf.value.lower()] = f"{letter}:"
    return out


class _ShFileOp(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]


# ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI | WANTNUKEWARNING: if Windows would still destroy an item
# instead of recycling it, it asks first rather than deleting silently
_RECYCLE_FLAGS = 0x0040 | 0x0010 | 0x0004 | 0x0400 | 0x4000


def recycle_problem(path, size):
    """Why the Recycle Bin can't take this item (so Windows would delete it for good), or None."""
    if len(path) >= 260:
        return "It is too deep in folders for the Recycle Bin."
    root = os.path.splitdrive(os.path.abspath(path))[0] + "\\"
    if ctypes.windll.kernel32.GetDriveTypeW(root) != 3:   # DRIVE_FIXED
        return "The Recycle Bin doesn't cover this drive."
    buf = ctypes.create_unicode_buffer(64)
    if not ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(root, buf, 64):
        return None
    m = re.search(r"\{[0-9a-fA-F-]+\}", buf.value)
    if not m:
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\BitBucket\Volume" + "\\" + m.group(0)) as k:
            def val(name):
                try:
                    return winreg.QueryValueEx(k, name)[0]
                except OSError:
                    return None
            if val("NukeOnDelete") == 1:
                return f"The Recycle Bin is turned off for drive {root[:2]}."
            cap = val("MaxCapacity")
            if isinstance(cap, int) and size and size > cap * 2 ** 20:
                return f"It is bigger than the Recycle Bin of drive {root[:2]} ({cap // 1024} GB)."
    except OSError:
        pass
    return None


def _bin_entries(drive):
    """(original path, deletion time, $I file) for every item this user has in the drive's Recycle Bin."""
    out = []
    for ifile in glob.glob(drive + "\\$Recycle.Bin\\*\\$I*"):
        try:
            with open(ifile, "rb") as f:
                data = f.read(4096)
            version = struct.unpack_from("<Q", data, 0)[0]
            deleted = struct.unpack_from("<Q", data, 16)[0]
            if version == 2:
                n = struct.unpack_from("<I", data, 24)[0]
                orig = data[28:28 + n * 2].decode("utf-16-le", "ignore").rstrip("\x00")
            else:
                orig = data[24:24 + 520].decode("utf-16-le", "ignore").split("\x00")[0]
        except (OSError, struct.error):
            continue
        out.append((orig, deleted, ifile))
    return out


def recycle(paths, sizes=None):
    """Send files to the Recycle Bin - and only there. Items the bin can't take are refused beforehand; each item is
    then found in the bin, and its $I entry returned so Undo restores exactly that item.
    Returns (done, failed, entries) with entries = {path: $I file}."""
    sizes = sizes or {}
    done, failed, entries = [], [], {}
    for p in paths:
        why = recycle_problem(p, sizes.get(p) or 0)
        if why:
            failed.append((p, why + " Kaizen left it where it is."))
            continue
        op = _ShFileOp(None, 3, p + "\0\0", None, _RECYCLE_FLAGS, 0, None, None)   # FO_DELETE
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if op.fAnyOperationsAborted:
            failed.append((p, "Not deleted (you chose to keep it)."))
            continue
        if rc or os.path.lexists(p):
            failed.append((p, f"Windows couldn't move it to the Recycle Bin (code {rc}). It may be open in another program."))
            continue
        drive = os.path.splitdrive(os.path.abspath(p))[0]
        mine = [e for e in _bin_entries(drive) if os.path.normcase(e[0]) == os.path.normcase(p)]
        if mine:
            entries[p] = max(mine, key=lambda e: e[1])[2]
        done.append(p)
    return done, failed, entries


def restore_from_recycle_bin(items):
    """Undo a recycle. items = [(original path, $I file or None)]: the recorded entry is restored exactly; for older
    log entries without one, the newest bin item with that original path. Returns the paths really back in place."""
    restored = []
    by_drive = {}
    for orig, ifile in items:
        if not ifile or not os.path.exists(ifile):
            d = os.path.splitdrive(orig)[0]
            if d not in by_drive:
                by_drive[d] = _bin_entries(d)
            cands = [e for e in by_drive[d] if os.path.normcase(e[0]) == os.path.normcase(orig)]
            ifile = max(cands, key=lambda e: e[1])[2] if cands else None
        if not ifile:
            continue
        rfile = os.path.join(os.path.dirname(ifile), "$R" + os.path.basename(ifile)[2:])
        if os.path.exists(orig) or not os.path.exists(rfile):
            continue
        try:
            os.makedirs(os.path.dirname(orig), exist_ok=True)
            os.rename(rfile, orig)
            os.remove(ifile)
        except OSError:
            continue
        if os.path.exists(orig):   # verify, don't assume
            restored.append(orig)
    return restored


def open_path(path):
    os.startfile(path)  # noqa: S606 - user clicked "Open"


def reveal(path):
    subprocess.Popen(f'explorer /select,"{path}"')


def run_uninstaller(command):
    """Launch a program's own uninstaller UI. Windows handles elevation (UAC)."""
    cmd = (command or "").strip()
    if not cmd:
        return False
    if cmd.startswith('"'):
        exe, _, args = cmd[1:].partition('"')
    else:
        m = re.match(r"(.+?\.exe)\s*(.*)$", cmd, re.I)
        exe, args = (m.group(1), m.group(2)) if m else (cmd, "")
    args = args.strip()
    if os.path.basename(exe).lower() == "msiexec.exe":
        args = re.sub(r"/I\s*\{", "/X{", args, flags=re.I)
    rc = shell32.ShellExecuteW(None, "open", exe, args or None, None, 1)
    return (rc or 0) > 32


def open_apps_settings():
    os.startfile("ms-settings:appsfeatures")  # noqa: S606
