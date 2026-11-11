"""Builds Tsubasa-Setup.exe - one self-contained file to share - into Documents\\Apps by Alex.

    .venv\\file-worker\\python.exe installer\\build.py           # build + verify the bundle with the test suite
    .venv\\file-worker\\python.exe installer\\build.py --fast    # skip the verification run

Steps:
  1. the portable runtime (.venv\\file-worker: embedded Python 3.12 with PyMuPDF, python-docx, openpyxl, lxml), with
     the licence files of exactly the packages it contains. The app itself needs only the standard library, so the
     same runtime runs the app and its document worker.
  2. Tsubasa's app files and the installer UI
  3. verify: the whole test suite on the bundled runtime and staged app only
  4. everything zipped into payload.zip and wrapped by Windows' built-in IExpress into a single .exe

Copyright (c) 2026 Alexander Gubric. MIT License (see THIRD-PARTY-NOTICES.txt for the bundled components).
"""
import ctypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER = os.path.join(APP, "installer")
RUNTIME = os.path.join(APP, ".venv", "file-worker")
BUILD = os.path.join(INSTALLER, "build")
STAGE = os.path.join(BUILD, "stage")
SETUP_FILE = "Tsubasa-Setup.exe"
OUTPUT_SUBFOLDER = os.environ.get("APPS_OUTPUT_SUBFOLDER") or "Apps by Alex"   # under Documents
APP_FILES = ["app.py", "LICENSE", "README.md", "THIRD-PARTY-NOTICES.txt", "CHANGELOG.md"]
APP_DIRS = ["core", "web", "tools", "vendor", "library", "licenses"]
MIN_TESTS = 160
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def documents():
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"), ctypes.byref(g))
    p = ctypes.c_wchar_p()
    ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p))
    return p.value


def version_of(path, pattern=r'''^VERSION = ["']([^"']+)["']'''):
    with open(path, encoding="utf-8") as f:
        return re.search(pattern, f.read(), re.M).group(1)


def build_runtime():
    rt = os.path.join(STAGE, "runtime")
    shutil.copytree(RUNTIME, rt, ignore=IGNORE)
    lic, sp, n = os.path.join(rt, "licenses"), os.path.join(rt, "site-packages"), 0
    for name in sorted(os.listdir(sp)):           # the licence files of each bundled distribution
        info = os.path.join(sp, name)
        if not name.endswith(".dist-info"):
            continue
        for root, _, files in os.walk(info):
            for f in files:
                if "licen" in f.lower() or "copying" in f.lower() or "notice" in f.lower() or root != info:
                    rel = os.path.relpath(os.path.join(root, f), info)
                    os.makedirs(os.path.dirname(os.path.join(lic, name, rel)), exist_ok=True)
                    shutil.copy2(os.path.join(root, f), os.path.join(lic, name, rel))
                    n += 1
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(rt) for f in fs)
    print(f"runtime: {size / 2**20:.0f} MB, {n} licence files")


def build_app():
    app = os.path.join(STAGE, "app")
    os.makedirs(app)
    for name in APP_FILES:
        shutil.copy2(os.path.join(APP, name), app)
    for sub in APP_DIRS:
        shutil.copytree(os.path.join(APP, sub), os.path.join(app, sub), ignore=IGNORE)
    setup = os.path.join(STAGE, "setup")
    os.makedirs(setup)
    for name in ("setup.py", "setup.html", "uninstall.py", "safety.py", "hw.py"):
        shutil.copy2(os.path.join(INSTALLER, name), setup)


def verify():
    """The test suite on the bundled runtime and staged app only (no venv, no sibling folders)."""
    tests = os.path.join(STAGE, "app", "tests")
    shutil.copytree(os.path.join(APP, "tests"), tests, ignore=IGNORE)
    print("verifying the bundle (test suite on the bundled runtime only)…")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "TSUBASA_"))}
    code = ("import sys, unittest; sys.path.insert(0, '.'); "
            "r = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.discover('tests', top_level_dir='.')); "
            "print(f'{r.testsRun} run, {len(r.failures) + len(r.errors)} failed, {len(r.skipped)} skipped'); "
            "sys.exit(not r.wasSuccessful())")
    r = subprocess.run([os.path.join(STAGE, "runtime", "python.exe"), "-B", "-c", code], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=os.path.join(STAGE, "app"))
    out = r.stdout + r.stderr
    m = re.search(r"(\d+) run, (\d+) failed, (\d+) skipped", out)
    for extra in ("tests", ".test-runs"):
        shutil.rmtree(os.path.join(STAGE, "app", extra), ignore_errors=True)
    if r.returncode != 0 or not m or m.group(2) != "0" or int(m.group(1)) < MIN_TESTS:
        raise RuntimeError("The bundle failed its tests:\n" + out[-6000:])
    print(f"  {m.group(0)}")
    for dp, dn, _ in os.walk(STAGE):     # don't ship the bytecode the test run produced
        for d in list(dn):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dp, d), ignore_errors=True)


BOOTSTRAP = r"""@echo off
setlocal
set "L=%TEMP%\tsubasa-setup-boot.log"
set "D=%TEMP%\Tsubasa-Setup-%RANDOM%%RANDOM%"
echo [%DATE% %TIME%] start in "%~dp0" > "%L%"
mkdir "%D%" >nul 2>nul
"%SystemRoot%\System32\tar.exe" -xf "%~dp0payload.zip" -C "%D%" >> "%L%" 2>&1
echo tar exit %ERRORLEVEL% >> "%L%"
if not exist "%D%\runtime\pythonw.exe" "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy RemoteSigned -Command "Expand-Archive -LiteralPath '%~dp0payload.zip' -DestinationPath '%D%' -Force" >> "%L%" 2>&1
if not exist "%D%\runtime\pythonw.exe" echo extraction failed >> "%L%" & exit /b 1
echo running setup >> "%L%"
"%D%\runtime\pythonw.exe" "%D%\setup\setup.py" >> "%L%" 2>&1
echo setup exit %ERRORLEVEL% >> "%L%"
rmdir /s /q "%D%" >nul 2>nul
"""

SED = r"""[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles
[Strings]
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName={target}
FriendlyName=Tsubasa Setup
AppLaunched=cmd.exe /c setup.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
FILE0="payload.zip"
FILE1="setup.cmd"
[SourceFiles]
SourceFiles0={src}\
[SourceFiles0]
%FILE0%=
%FILE1%=
"""


def main():
    v_app = version_of(os.path.join(APP, "core", "config.py"))
    v_setup = version_of(os.path.join(INSTALLER, "setup.py"))
    if v_app != v_setup:
        sys.exit(f"core/config.py says {v_app}, setup.py says {v_setup} - make them the same first")
    out_dir = os.path.join(documents(), OUTPUT_SUBFOLDER)
    t0 = time.time()
    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(STAGE)
    build_runtime()
    build_app()
    if "--fast" not in sys.argv:
        verify()
    # IExpress/makecab can't handle spaces in source paths, so the last step happens in %TEMP%
    pack = os.path.join(os.environ["TEMP"], "tsubasa-pack")
    shutil.rmtree(pack, ignore_errors=True)
    os.makedirs(pack)
    payload = os.path.join(pack, "payload.zip")
    print("compressing…")
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, filenames in os.walk(STAGE):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.relpath(full, STAGE))
    print(f"payload: {os.path.getsize(payload) / 2**20:.1f} MB")
    with open(os.path.join(pack, "setup.cmd"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(BOOTSTRAP)
    built = os.path.join(pack, SETUP_FILE)
    sed = os.path.join(pack, "tsubasa.sed")
    with open(sed, "w", encoding="mbcs") as f:
        f.write(SED.format(target=built, src=pack))
    subprocess.run([os.path.expandvars(r"%SystemRoot%\System32\iexpress.exe"), "/N", "/Q", sed], check=True)
    for _ in range(300):   # iexpress returns before the file is fully written on some systems
        if os.path.exists(built):
            break
        time.sleep(1)
    last = -1
    while os.path.getsize(built) != last:   # wait until the file stops growing
        last = os.path.getsize(built)
        time.sleep(2)
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, SETUP_FILE)
    shutil.move(built, target)
    shutil.rmtree(pack, ignore_errors=True)
    if "--keep" not in sys.argv:
        shutil.rmtree(BUILD, ignore_errors=True)
    print(f"{target} ({os.path.getsize(target) / 2**20:.1f} MB, version {v_app}) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
