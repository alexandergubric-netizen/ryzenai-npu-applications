"""What differs between Windows and macOS, in one place.

Windows is the original platform (FastFlowLM on the Ryzen AI NPU, Edge window, PowerShell). macOS on Apple silicon
uses MLX (core/mlx_client.py), a Chromium-family or default browser window and zsh. Everything else is shared.
"""
import os
import shutil
import sys
from pathlib import Path

WINDOWS = os.name == "nt"
MAC = sys.platform == "darwin"
NO_WINDOW = 0x08000000 if WINDOWS else 0   # subprocess creationflags: no console window on Windows


def data_home(app):
    """Per-user data folder; TSUBASA_HOME overrides it (tests and scratch runs)."""
    if os.environ.get("TSUBASA_HOME"):
        return Path(os.environ["TSUBASA_HOME"])
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / app
    if MAC:
        return Path.home() / "Library/Application Support" / app
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / app


def is_admin():
    """Tsubasa refuses to run commands while it is itself elevated."""
    if WINDOWS:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    return os.geteuid() == 0


def worker_python(root):
    """The document worker's own Python (PDF, Word, Excel packages). Installed copies keep it in runtime/."""
    names = ("python.exe",) if WINDOWS else ("bin/python3", "bin/python")
    for base in (root / ".venv/file-worker", root.parent / "runtime", root.parent / "python"):
        for name in names:
            if (base / name).is_file():
                return base / name
    return root / ".venv/file-worker" / names[0]


def window_browsers():
    """Browsers that can show the page as an app window (--app=), best first."""
    if WINDOWS:
        roots = [os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")]
        tails = ["Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"]
        return [Path(r) / t for t in tails for r in roots if r]
    if MAC:
        apps = ["Google Chrome.app/Contents/MacOS/Google Chrome", "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "Brave Browser.app/Contents/MacOS/Brave Browser", "Chromium.app/Contents/MacOS/Chromium"]
        return [base / a for a in apps for base in (Path("/Applications"), Path.home() / "Applications")]
    return [Path(p) for p in filter(None, map(shutil.which, ("google-chrome", "chromium", "microsoft-edge")))]


def blocked_roots(home):
    """Folders the assistant never opens through "Files on this PC" or Code mode's file tools."""
    env = os.environ
    private = [home / ".ssh", home / ".gnupg", home / ".aws", home / ".azure", home / ".codex", home / ".claude"]
    if WINDOWS:
        return [env.get("SystemRoot", r"C:\Windows"), env.get("ProgramFiles", r"C:\Program Files"),
                env.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), env.get("ProgramData", r"C:\ProgramData"),
                r"C:\$Recycle.Bin", r"C:\System Volume Information", r"C:\Recovery", r"C:\Boot", r"C:\PerfLogs",
                str(home / "AppData"), *map(str, private)]
    return ["/System", "/Library", "/usr", "/bin", "/sbin", "/private", "/etc", "/var", "/dev", "/cores", "/opt",
            "/Applications", str(home / "Library"), str(home / ".Trash"), str(home / ".config"), *map(str, private)]
