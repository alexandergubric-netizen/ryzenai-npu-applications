"""Builds Tansu-Setup.exe - one self-contained file to share - into Documents\\Apps by Alex.

    runtime\\python.exe installer\\build.py           # build + verify the bundle with the smoke test
    runtime\\python.exe installer\\build.py --fast    # skip the verification run

Steps:
  1. Tansu's own portable runtime (runtime\\: embedded Python 3.12 with py7zr and send2trash), with the licence
     files of exactly the packages it contains
  2. Tansu's app files and the installer UI
  3. verify: run tests/smoke.py on the bundled runtime and app only (no access to anything else)
  4. everything zipped into payload.zip and wrapped by Windows' built-in IExpress into a single .exe

Copyright (c) 2026 Alexander Gubric. MIT License.
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

TANSU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER = os.path.join(TANSU, "installer")
RUNTIME = os.path.join(TANSU, "runtime")
BUILD = os.path.join(INSTALLER, "build")
STAGE = os.path.join(BUILD, "stage")
SETUP_FILE = "Tansu-Setup.exe"
OUTPUT_SUBFOLDER = os.environ.get("APPS_OUTPUT_SUBFOLDER") or "Apps by Alex"   # under Documents
APP_FILES = ["app.py", "LICENSE", "README.md", "THIRD-PARTY-NOTICES.txt", "tansu.ico", "requirements.txt"]
MIN_CHECKS = 55            # tests/smoke.py without --ai
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")
SEND2TRASH_LICENSE = """Copyright (c) 2017, Virgil Dupras
All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
following conditions are met:

    * Redistributions of source code must retain the above copyright notice, this list of conditions and the
      following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
      following disclaimer in the documentation and/or other materials provided with the distribution.
    * Neither the name of Hardcoded Software Inc. nor the names of its contributors may be used to endorse or
      promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""


def documents():
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_ulong), ("b", ctypes.c_ushort), ("c", ctypes.c_ushort), ("d", ctypes.c_ubyte * 8)]
    g = GUID()
    ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"), ctypes.byref(g))
    p = ctypes.c_wchar_p()
    ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p))
    return p.value


def version_of(path):
    with open(path, encoding="utf-8") as f:
        return re.search(r'^VERSION = "([^"]+)"', f.read(), re.M).group(1)


def build_runtime():
    rt = os.path.join(STAGE, "runtime")

    def ignore(folder, names):   # runtime\licenses is rebuilt below (the dist-info licences stay where they are)
        skip = {n for n in names if n == "__pycache__" or n.endswith(".pyc")}
        return skip | ({"licenses"} if os.path.normcase(folder) == os.path.normcase(RUNTIME) else set())
    shutil.copytree(RUNTIME, rt, ignore=ignore)
    lic = os.path.join(rt, "licenses")
    sp = os.path.join(rt, "site-packages")
    n = 0
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
    os.makedirs(os.path.join(lic, "send2trash"))   # it came without its metadata folder
    with open(os.path.join(lic, "send2trash", "LICENSE"), "w", encoding="utf-8") as f:
        f.write(SEND2TRASH_LICENSE)
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(rt) for f in fs)
    print(f"runtime: {size / 2**20:.0f} MB, {n + 1} licence files")


def build_app():
    app = os.path.join(STAGE, "app")
    os.makedirs(app)
    for name in APP_FILES:
        shutil.copy2(os.path.join(TANSU, name), app)
    for sub in ("core", "web", "licenses"):
        shutil.copytree(os.path.join(TANSU, sub), os.path.join(app, sub), ignore=IGNORE)
    setup = os.path.join(STAGE, "setup")
    os.makedirs(setup)
    for name in ("setup.py", "setup.html", "uninstall.py", "safety.py"):
        shutil.copy2(os.path.join(INSTALLER, name), setup)


def verify():
    """The smoke test on the bundled runtime and app only: every format, the library and the web gate."""
    tests = os.path.join(STAGE, "app", "tests")
    shutil.copytree(os.path.join(TANSU, "tests"), tests, ignore=IGNORE)
    print("verifying the bundle (smoke test on the bundled runtime only)…")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("PYTHON", "TANSU_"))}
    r = subprocess.run([os.path.join(STAGE, "runtime", "python.exe"), os.path.join(tests, "smoke.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                       cwd=tempfile.gettempdir())
    shutil.rmtree(tests, ignore_errors=True)
    m = re.search(r"(\d+) passed, (\d+) failed", r.stdout)
    if r.returncode != 0 or not m or m.group(2) != "0" or int(m.group(1)) < MIN_CHECKS:
        raise RuntimeError("The bundle failed the smoke test:\n" + r.stdout[-4000:] + r.stderr[-3000:])
    print(f"  {m.group(0)}")
    for dp, dn, _ in os.walk(STAGE):     # don't ship the bytecode the test run produced
        for d in list(dn):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dp, d), ignore_errors=True)


BOOTSTRAP = r"""@echo off
setlocal
set "L=%TEMP%\tansu-setup-boot.log"
set "D=%TEMP%\Tansu-Setup-%RANDOM%%RANDOM%"
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
FriendlyName=Tansu Setup
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
    v_app, v_setup = version_of(os.path.join(TANSU, "app.py")), version_of(os.path.join(INSTALLER, "setup.py"))
    if v_app != v_setup:
        sys.exit(f"app.py says {v_app}, setup.py says {v_setup} - make them the same first")
    out_dir = os.path.join(documents(), OUTPUT_SUBFOLDER)
    t0 = time.time()
    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(STAGE)
    build_runtime()
    build_app()
    if "--fast" not in sys.argv:
        verify()
    # IExpress/makecab can't handle spaces in source paths, so the last step happens in %TEMP%
    pack = os.path.join(os.environ["TEMP"], "tansu-pack")
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
    sed = os.path.join(pack, "tansu.sed")
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
