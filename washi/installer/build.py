"""Builds Washi-Setup.exe - one self-contained file to share - into Documents\\Apps by Alex.

    python installer\\build.py

Steps:
  1. a portable Python runtime made from this PC's Python 3.12 (stdlib precompiled into python312.zip, plus PyMuPDF),
     so the people you share it with need nothing pre-installed
  2. Washi's app files and the installer UI
  3. everything zipped into payload.zip and wrapped by Windows' built-in IExpress into a single .exe

Copyright (c) 2026 Alexander Gubric. MIT License.
"""
import ctypes
import importlib.util
import marshal
import os
import shutil
import subprocess
import sys
import time
import zipfile

WASHI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER = os.path.join(WASHI, "installer")
BUILD = os.path.join(INSTALLER, "build")
STAGE = os.path.join(BUILD, "stage")
PY = os.path.dirname(sys.executable)
PY_TAG = f"python{sys.version_info.major}{sys.version_info.minor}"
SETUP_FILE = "Washi-Setup.exe"
OUTPUT_SUBFOLDER = os.environ.get("APPS_OUTPUT_SUBFOLDER") or "Apps by Alex"   # under Documents

STDLIB_SKIP = {"site-packages", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3",
               "pydoc_data", "__pycache__", "venv"}
DLL_SKIP = ("_tkinter", "tcl", "tk", "_test", "xxlimited", "_ctypes_test")
APP_FILES = ["app.py", "LICENSE", "README.md", "washi.ico"]
PACKAGES = ["pymupdf", "fitz"]
LICENSE_DIRS = ("pymupdf-",)


def documents():
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"), ctypes.byref(g))
    p = ctypes.c_wchar_p()
    ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p))
    return p.value


def pyc_bytes(src_path, rel):
    with open(src_path, "rb") as f:
        source = f.read()
    code = compile(source, rel, "exec", dont_inherit=True, optimize=0)
    st = os.stat(src_path)
    data = bytearray(importlib.util.MAGIC_NUMBER)
    data += (0).to_bytes(4, "little")
    data += int(st.st_mtime).to_bytes(4, "little")
    data += (st.st_size & 0xFFFFFFFF).to_bytes(4, "little")
    data += marshal.dumps(code)
    return bytes(data)


def build_runtime():
    rt = os.path.join(STAGE, "runtime")
    os.makedirs(rt)
    for name in ("python.exe", "pythonw.exe", f"{PY_TAG}.dll", "python3.dll", "vcruntime140.dll",
                 "vcruntime140_1.dll", "LICENSE.txt"):
        shutil.copy2(os.path.join(PY, name), rt)
    for name in os.listdir(os.path.join(PY, "DLLs")):
        if name.lower().endswith((".pyd", ".dll")) and not name.lower().startswith(DLL_SKIP):
            shutil.copy2(os.path.join(PY, "DLLs", name), rt)
    lib = os.path.join(PY, "Lib")
    n = 0
    with zipfile.ZipFile(os.path.join(rt, f"{PY_TAG}.zip"), "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, dirnames, filenames in os.walk(lib):
            dirnames[:] = [d for d in dirnames if d not in STDLIB_SKIP]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, lib).replace("\\", "/")
                try:
                    z.writestr(rel[:-3] + ".pyc", pyc_bytes(full, rel))
                    n += 1
                except SyntaxError:
                    pass
    sp = os.path.join(rt, "site-packages")
    for pkg in PACKAGES:
        shutil.copytree(os.path.join(lib, "site-packages", pkg), os.path.join(sp, pkg),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyi", "*.h", "*.lib"))
    for info in os.listdir(os.path.join(lib, "site-packages")):   # keep the licence files
        if info.lower().startswith(LICENSE_DIRS) and info.endswith(".dist-info"):
            src = os.path.join(lib, "site-packages", info)
            dst = os.path.join(rt, "licenses", info)
            os.makedirs(dst, exist_ok=True)
            for f in os.listdir(src):
                full = os.path.join(src, f)
                if os.path.isfile(full) and ("licen" in f.lower() or f in ("METADATA",)):
                    shutil.copy2(full, dst)
                elif os.path.isdir(full):
                    shutil.copytree(full, os.path.join(dst, f), dirs_exist_ok=True)
    with open(os.path.join(rt, f"{PY_TAG}._pth"), "w", encoding="ascii") as f:
        f.write(f"{PY_TAG}.zip\n.\nsite-packages\n")
    print(f"runtime: {n} stdlib modules precompiled")


def build_app():
    app = os.path.join(STAGE, "app")
    os.makedirs(app)
    for name in APP_FILES:
        shutil.copy2(os.path.join(WASHI, name), app)
    for sub in ("core", "web", "licenses"):
        shutil.copytree(os.path.join(WASHI, sub), os.path.join(app, sub), ignore=shutil.ignore_patterns("__pycache__"))
    setup = os.path.join(STAGE, "setup")
    os.makedirs(setup)
    for name in ("setup.py", "setup.html", "uninstall.py", "safety.py"):
        shutil.copy2(os.path.join(INSTALLER, name), setup)
    # the native launcher, so Windows can offer Washi in "Open with" / Default apps
    sys.path.insert(0, WASHI)
    import make_launcher
    make_launcher.build(os.path.join(STAGE, "Washi.exe"))


BOOTSTRAP = r"""@echo off
setlocal
set "L=%TEMP%\washi-setup-boot.log"
set "D=%TEMP%\Washi-Setup-%RANDOM%%RANDOM%"
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
HideExtractAnimation=1
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
FriendlyName=Washi Setup
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
    out_dir = os.path.join(documents(), OUTPUT_SUBFOLDER)
    t0 = time.time()
    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(STAGE)
    build_runtime()
    build_app()
    # IExpress/makecab can't handle spaces in source paths, so the last step happens in %TEMP%
    pack = os.path.join(os.environ["TEMP"], "washi-pack")
    shutil.rmtree(pack, ignore_errors=True)
    os.makedirs(pack)
    payload = os.path.join(pack, "payload.zip")
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, filenames in os.walk(STAGE):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.relpath(full, STAGE))
    with open(os.path.join(pack, "setup.cmd"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(BOOTSTRAP)
    built = os.path.join(pack, SETUP_FILE)
    sed = os.path.join(pack, "washi.sed")
    with open(sed, "w", encoding="mbcs") as f:
        f.write(SED.format(target=built, src=pack))
    subprocess.run([os.path.expandvars(r"%SystemRoot%\System32\iexpress.exe"), "/N", "/Q", sed], check=True)
    for _ in range(90):   # iexpress returns before the file is fully written on some systems
        if os.path.exists(built):
            break
        time.sleep(1)
    time.sleep(1)
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, SETUP_FILE)
    shutil.move(built, target)
    shutil.rmtree(pack, ignore_errors=True)
    if "--keep" not in sys.argv:
        shutil.rmtree(BUILD, ignore_errors=True)
    print(f"{target} ({os.path.getsize(target) / 2**20:.1f} MB) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
