"""Suggestions for the "For you" tab, from what is going on with this PC right now.
Everything here is read in a few milliseconds without PowerShell (Windows APIs, the registry, one folder listing)."""
import ctypes
import os
import shutil
import time
import winreg


class _PowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte),
                ("SystemStatusFlag", ctypes.c_ubyte), ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]


def _key_exists(path):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path))
        return True
    except OSError:
        return False


def hints():
    """[{q, why, tone}] - q is a request Sensei answers from its library; tone: warn | info."""
    out = []
    # disk space on the system drive
    try:
        sysdrive = os.environ.get("SystemDrive", "C:") + "\\"
        du = shutil.disk_usage(sysdrive)
        free = du.free / du.total * 100
        if free < 15:
            out.append({"q": f"What is taking up space on {sysdrive[0]} drive", "why": f"{sysdrive[0]}: only {free:.0f}% free", "tone": "warn"})
            out.append({"q": "Clean temp files", "why": "frees space safely", "tone": "warn"})
    except OSError:
        pass
    # battery
    ps = _PowerStatus()
    if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(ps)) and ps.BatteryFlag != 128 and ps.BatteryLifePercent <= 100:
        if ps.ACLineStatus == 0 and ps.BatteryLifePercent < 30:
            out.append({"q": "Power saver mode", "why": f"battery {ps.BatteryLifePercent}%", "tone": "warn"})
            out.append({"q": "Lower the screen brightness", "why": "saves battery", "tone": "info"})
    # restart waiting after updates, or a very long uptime
    if _key_exists(r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending") or \
            _key_exists(r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"):
        out.append({"q": "Is a restart pending?", "why": "Windows is waiting for a restart", "tone": "warn"})
    days = ctypes.windll.kernel32.GetTickCount64() / 86_400_000
    if days >= 7:
        out.append({"q": "How long has my PC been on?", "why": f"on for {days:.0f} days", "tone": "info"})
    # a crowded Downloads folder (top level only, so it stays fast)
    try:
        dl = os.path.join(os.path.expanduser("~"), "Downloads")
        with os.scandir(dl) as it:
            files = [e for e in it if e.is_file()]
        if len(files) >= 40:
            out.append({"q": "Sort my downloads into folders by type", "why": f"{len(files)} loose files in Downloads", "tone": "info"})
        old = sum(1 for e in files if time.time() - e.stat().st_mtime > 90 * 86400)
        if old >= 20:
            out.append({"q": "Delete files in Downloads older than 90 days", "why": f"{old} files older than 3 months", "tone": "info"})
    except OSError:
        pass
    return out
