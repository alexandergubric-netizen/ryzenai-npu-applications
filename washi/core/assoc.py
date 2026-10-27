"""Registers Washi.exe with Windows as an app for PDF (and XPS / EPUB) files, per user, no admin rights.

Windows 10/11 only let the person choose the default app themselves (the choice is protected), so this makes Washi
appear in "Open with" and in Settings > Default apps; `open_default_settings()` jumps to Washi's page there.
Used by the installer, by Settings > Make default, and for running from source.
"""
import ctypes
import os
import winreg

APP = "Washi"
PROGID = "Washi.PDF"
EXTS = (".pdf", ".xps", ".oxps", ".epub", ".mobi", ".fb2")
CLASSES = r"Software\Classes"
APP_KEY = CLASSES + r"\Applications\Washi.exe"
CAPS = r"Software\Washi\Capabilities"
DESCRIPTION = "PDF editor with a local AI assistant"
HKCU = winreg.HKEY_CURRENT_USER


def _set(path, values):
    with winreg.CreateKey(HKCU, path) as k:
        for name, value in values.items():
            if isinstance(value, bytes):
                winreg.SetValueEx(k, name, 0, winreg.REG_NONE, value)
            else:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _get(path, name=""):
    try:
        with winreg.OpenKey(HKCU, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _delete_tree(path):
    try:
        with winreg.OpenKey(HKCU, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    sub = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(path + "\\" + sub)
        winreg.DeleteKey(HKCU, path)
    except OSError:
        pass


def _notify():
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED


def register(exe, icon=None):
    """Make `exe` (Washi.exe) known to Windows for PDF files. Safe to call again (e.g. after moving Washi)."""
    exe = os.path.abspath(exe)
    icon = os.path.abspath(icon) if icon else exe
    cmd = f'"{exe}" "%1"'
    _set(CLASSES + "\\" + PROGID, {"": "PDF document", "FriendlyTypeName": "PDF document (Washi)"})
    _set(CLASSES + "\\" + PROGID + r"\DefaultIcon", {"": f"{icon},0"})
    _set(CLASSES + "\\" + PROGID + r"\Application", {"ApplicationName": APP, "ApplicationIcon": f"{icon},0",
                                                       "ApplicationCompany": "Alexander Gubric",
                                                       "ApplicationDescription": DESCRIPTION})
    _set(CLASSES + "\\" + PROGID + r"\shell", {"": "open"})
    _set(CLASSES + "\\" + PROGID + r"\shell\open", {"FriendlyAppName": APP})
    _set(CLASSES + "\\" + PROGID + r"\shell\open\command", {"": cmd})
    # the exe itself, so "Open with > Choose another app > browse to Washi.exe" works as well
    _set(APP_KEY, {"FriendlyAppName": APP})
    _set(APP_KEY + r"\DefaultIcon", {"": f"{icon},0"})
    _set(APP_KEY + r"\shell\open\command", {"": cmd})
    _set(APP_KEY + r"\SupportedTypes", {ext: "" for ext in EXTS})
    for ext in EXTS:
        _set(CLASSES + "\\" + ext + r"\OpenWithProgids", {PROGID: b""})
    # Default apps (Settings) lists applications from RegisteredApplications + Capabilities
    _set(CAPS, {"ApplicationName": APP, "ApplicationDescription": DESCRIPTION, "ApplicationIcon": f"{icon},0"})
    _set(CAPS + r"\FileAssociations", {ext: PROGID for ext in EXTS})
    _set(r"Software\RegisteredApplications", {APP: CAPS})
    # Start > Run "washi" and other launchers
    _set(r"Software\Microsoft\Windows\CurrentVersion\App Paths\Washi.exe", {"": exe, "Path": os.path.dirname(exe)})
    _notify()


def unregister():
    for path in (CLASSES + "\\" + PROGID, APP_KEY, r"Software\Washi",
                 r"Software\Microsoft\Windows\CurrentVersion\App Paths\Washi.exe"):
        _delete_tree(path)
    for ext in EXTS:
        try:
            with winreg.OpenKey(HKCU, CLASSES + "\\" + ext + r"\OpenWithProgids", 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, PROGID)
        except OSError:
            pass
    try:
        with winreg.OpenKey(HKCU, r"Software\RegisteredApplications", 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP)
    except OSError:
        pass
    _notify()


def registered_exe():
    """The Washi.exe Windows currently knows about, or None."""
    cmd = _get(CLASSES + "\\" + PROGID + r"\shell\open\command") or ""
    if cmd.startswith('"'):
        exe = cmd[1:].split('"', 1)[0]
        return exe if os.path.exists(exe) else None
    return None


def is_default(ext=".pdf"):
    """True when the person has chosen Washi for `ext` (Windows stores that choice in UserChoice)."""
    choice = _get(r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts" + "\\" + ext + r"\UserChoice", "ProgId")
    if choice == PROGID:
        return True
    return bool(choice) and choice.lower().startswith("applications\\washi.exe")


def open_default_settings():
    """Settings > Default apps > Washi (Windows 11), or the Default apps page."""
    for uri in (f"ms-settings:defaultapps?registeredAppUser={APP}", "ms-settings:defaultapps"):
        try:
            os.startfile(uri)  # noqa: S606 - fixed Settings URIs
            return True
        except OSError:
            continue
    return False


def find_exe(app_dir):
    """Washi.exe for the copy in `app_dir` (the folder with app.py): installed = one level up, source = same folder."""
    for p in (os.path.join(os.path.dirname(app_dir), "Washi.exe"), os.path.join(app_dir, "Washi.exe")):
        if os.path.exists(p) and (os.path.exists(os.path.join(os.path.dirname(p), "app.py")) or
                                  os.path.exists(os.path.join(os.path.dirname(p), "app", "app.py"))):
            return p
    return None
