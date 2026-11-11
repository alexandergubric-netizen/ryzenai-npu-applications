"""Installer safety helpers shared by the Washi, Morph, Sensei and Kaizen installers (keep the copies identical).

* Install folders are always a dedicated <chosen>\\<App> folder, and a folder holding anything else is refused,
  so uninstalling can never take a user's own files with it.
* setup writes install-manifest.json listing every file it put there; the uninstaller removes only those.
* Third-party installers (FastFlowLM, LM Studio) are downloaded into a private temporary folder, checked against a
  pinned SHA-256 and/or the expected code-signing publisher, run, and deleted.

Copyright (c) 2026 Alexander Gubric. MIT License.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

MANIFEST = "install-manifest.json"
CREATE_NO_WINDOW = 0x08000000

# FastFlowLM's MSI is not code-signed, so the exact file is pinned. Update both together (gh api
# repos/ROCm/FastFlowLM/releases/tags/<tag> lists each asset's sha256 digest).
FLM_VERSION = "1.0.9"
FLM_MSI_URL = f"https://github.com/ROCm/FastFlowLM/releases/download/v{FLM_VERSION}/flm-setup.msi"
FLM_MSI_SHA256 = "a14fda91b55192391bd4422d6e3c2fa13fce09d3c8877a63df94997a306372e0"
FLM_LICENSE_URL = "https://github.com/ROCm/FastFlowLM/blob/main/LICENSE"


# ----------------------------------------------------------------------------- install folder
def dedicated_dir(chosen, app):
    """The folder the app really goes into: <chosen>\\<App>, unless the chosen folder already is that."""
    target = os.path.abspath(os.path.expandvars(chosen.strip().strip('"')))
    if os.path.basename(target.rstrip("\\/")).lower() != app.lower():
        target = os.path.join(target, app)
    return target


def ours(target, existing=None):
    """True when the folder holds an earlier installation of this app (manifest, or the registered location)."""
    if os.path.isfile(os.path.join(target, MANIFEST)):
        return True
    return bool(existing) and os.path.normcase(os.path.abspath(existing)) == os.path.normcase(target)


def check_target(target, app, existing=None):
    """Refuse folders that hold other things. Raises RuntimeError with a message for the user."""
    drive, rest = os.path.splitdrive(target)
    if not drive or rest.strip("\\/") == "":
        raise RuntimeError("Choose a folder, not a whole drive.")
    if os.path.exists(target) and not os.path.isdir(target):
        raise RuntimeError(f"{target} is a file. Choose a folder.")
    if os.path.isdir(target) and os.listdir(target) and not ours(target, existing):
        raise RuntimeError(f"{target} already contains other files. Choose an empty folder (or the suggested one), "
                           f"so uninstalling {app} can never remove anything else.")


def write_manifest(target, version):
    """List every file and folder now in the install folder (all of it was put there by setup)."""
    files, dirs = [], []
    for dp, dns, fns in os.walk(target):
        rel = os.path.relpath(dp, target)
        if rel != ".":
            dirs.append(rel)
        for fn in fns:
            if fn != MANIFEST:
                files.append(os.path.normpath(os.path.join(rel, fn)))
    with open(os.path.join(target, MANIFEST), "w", encoding="utf-8") as f:
        json.dump({"version": version, "files": sorted(files), "dirs": sorted(dirs)}, f, indent=0)


def app_running(data_dir):
    """True while this user's copy of the app runs (its server keeps <data>\\instance.json with its process id)."""
    import ctypes
    try:
        with open(os.path.join(data_dir, "instance.json"), encoding="utf-8") as f:
            pid = int(json.load(f)["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
    ctypes.windll.kernel32.CloseHandle(h)
    return code.value == 259   # STILL_ACTIVE


# ----------------------------------------------------------------------------- verified downloads
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def signature(path):
    """(status, signer subject) from Windows' Authenticode check, e.g. ('Valid', 'CN=Element Labs Inc., ...')."""
    ps = ("$s = Get-AuthenticodeSignature -LiteralPath $env:K_FILE; "
          "$s.Status.ToString() + '|' + $(if ($s.SignerCertificate) { $s.SignerCertificate.Subject } else { '' })")
    # Windows PowerShell can't load its own modules with PowerShell 7's PSModulePath, so don't pass that on
    env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    env["K_FILE"] = path
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), r"System32\WindowsPowerShell\v1.0\powershell.exe")
    try:
        out = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                             text=True, timeout=60, env=env, creationflags=CREATE_NO_WINDOW).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "Unknown", ""
    status, _, subject = out.partition("|")
    return status or "Unknown", subject


def verify(path, sha=None, signer=None):
    """Raise RuntimeError unless the file matches the pinned hash and/or carries a valid signature by signer."""
    if sha and sha256(path).lower() != sha.lower():
        raise RuntimeError("The downloaded installer does not match the expected file, so it was not run. "
                           "Please try again later.")
    if signer:
        status, subject = signature(path)
        if status != "Valid" or signer.lower() not in subject.lower():
            raise RuntimeError(f"The downloaded installer is not signed by {signer} (Windows says: {status}), "
                               "so it was not run.")


class PrivateDownload:
    """A private temporary folder for one download; removed afterwards, whatever happens."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="setup-dl-")
        return self

    def path(self, name):
        return os.path.join(self.dir, name)

    def __exit__(self, *exc):
        shutil.rmtree(self.dir, ignore_errors=True)
        return False
