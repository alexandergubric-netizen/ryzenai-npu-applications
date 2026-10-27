"""Sets up this source folder like an installed Washi: builds Washi.exe, puts a Washi shortcut on the desktop and
registers Washi with Windows for PDF files ("Open with", Settings > Default apps). Run: python make_shortcut.py
(The installer does the same for installed copies.)"""
import ctypes
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_launcher  # noqa: E402
from core import assoc, winutil  # noqa: E402


def desktop():
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"), ctypes.byref(g))
    p = ctypes.c_wchar_p()
    ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p))
    return p.value or os.path.expanduser(r"~\Desktop")


if __name__ == "__main__":
    exe = os.path.join(HERE, "Washi.exe")
    make_launcher.build(exe)
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if os.path.exists(pyw):
        with open(os.path.join(HERE, "pythonw.txt"), "w", encoding="utf-8") as f:
            f.write(pyw)
    lnk = os.path.join(desktop(), "Washi.lnk")
    winutil.shortcut(lnk, exe, "", HERE, exe + ",0", "Washi - PDF editor with a local AI assistant")
    assoc.register(exe, os.path.join(HERE, "washi.ico"))
    print(lnk, "created" if os.path.exists(lnk) else "NOT created")
    print("registered:", assoc.registered_exe(), "| default for .pdf:", assoc.is_default())
    if "--default" in sys.argv:
        assoc.open_default_settings()
