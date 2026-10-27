"""Builds Morph-Setup.exe - one self-contained file to share - into Documents\\Apps by Alex.

    python installer\\build.py            # build + verify the bundle with the full conversion test
    python installer\\build.py --fast     # skip the verification run

Steps:
  1. a portable Python runtime made from this PC's Python 3.12 (stdlib precompiled into python312.zip)
  2. the libraries Morph really uses - found by running tests/smoke.py (every conversion) and recording what loads
  3. ffmpeg/ffprobe in tools\\, Morph's app files and the installer UI
  4. verify: run the conversion test again on the bundled runtime only
  5. everything zipped into payload.zip and wrapped by Windows' built-in IExpress into a single .exe

OpenCV (pdf2docx) and pyarrow (Parquet) are left out on purpose: they add ~200 MB. PDF -> Word still works
(through HTML); Parquet is the only format that goes away.

Copyright (c) 2026 Alexander Gubric. MIT License.
"""
import ctypes
import importlib.util
import json
import marshal
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

MORPH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER = os.path.join(MORPH, "installer")
BUILD = os.path.join(INSTALLER, "build")
STAGE = os.path.join(BUILD, "stage")
PY = os.path.dirname(sys.executable)
SITE = os.path.join(PY, "Lib", "site-packages")
PY_TAG = f"python{sys.version_info.major}{sys.version_info.minor}"
SETUP_FILE = "Morph-Setup.exe"
OUTPUT_SUBFOLDER = os.environ.get("APPS_OUTPUT_SUBFOLDER") or "Apps by Alex"   # under Documents

STDLIB_SKIP = {"site-packages", "test", "tests", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3",
               "pydoc_data", "__pycache__", "venv"}
DLL_SKIP = ("_tkinter", "tcl", "tk", "_test", "xxlimited", "_ctypes_test")
APP_FILES = ["app.py", "LICENSE", "README.md", "THIRD-PARTY-NOTICES.txt", "morph.ico", "requirements.txt"]
LEFT_OUT = ["cv2", "pyarrow", "pdf2docx", "tkinter"]   # see the docstring
EXTRA_IMPORTS = ["xlrd", "rawpy", "pillow_heif", "py7zr", "tabulate", "yaml", "tomli_w", "xmltodict",
                 "fontTools.ttLib.woff2", "brotli", "odf.opendocument", "odf.table", "odf.text", "lxml.etree", "docx",
                 "pypandoc", "openpyxl", "fitz", "pandas", "PIL.AvifImagePlugin"]
SITE_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyi", "*.h", "*.hpp", "*.lib", "*.a", "tests", "include",
                                     "*.pyx", "*.pxd")

TRACE = r"""
import json, os, sys, importlib
class Absent:                                  # behave exactly as if these were not installed
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in %(left_out)r:
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
sys.meta_path.insert(0, Absent())
sys.path.insert(0, %(morph)r)
sys.argv = ["smoke", %(scratch)r]
for m in %(extra)r:
    importlib.import_module(m)
import runpy
runpy.run_path(os.path.join(%(morph)r, "tests", "smoke.py"), run_name="__main__")
site = os.path.normcase(%(site)r)
top = set()
for mod in list(sys.modules.values()):
    f = getattr(mod, "__file__", None)
    if f and os.path.normcase(f).startswith(site + os.sep):
        top.add(os.path.relpath(f, %(site)r).split(os.sep)[0])
print("TRACE" + json.dumps(sorted(top)))
"""


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
    with open(os.path.join(rt, f"{PY_TAG}._pth"), "w", encoding="ascii") as f:
        f.write(f"{PY_TAG}.zip\n.\nsite-packages\n")
    print(f"runtime: {n} stdlib modules precompiled")


def trace_packages():
    """Run every conversion once and record which site-packages entries got loaded."""
    scratch = tempfile.mkdtemp(prefix="morph-trace-")
    script = TRACE % {"left_out": LEFT_OUT, "morph": MORPH, "scratch": scratch, "extra": EXTRA_IMPORTS, "site": SITE}
    print("tracing libraries (runs every conversion once)…")
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=MORPH)
    shutil.rmtree(scratch, ignore_errors=True)
    line = next((l for l in r.stdout.splitlines() if l.startswith("TRACE")), None)
    summary = next((l for l in r.stdout.splitlines() if " ok, " in l), "")
    if not line or " 0 failed" not in summary:
        raise RuntimeError("Tracing failed:\n" + r.stdout[-3000:] + r.stderr[-3000:])
    print("  " + summary.strip())
    return json.loads(line[5:]), int(summary.split()[0])


def copy_packages(top):
    sp = os.path.join(STAGE, "runtime", "site-packages")
    os.makedirs(sp)
    entries = set(top)
    for name in list(entries):   # vendored DLL folders (numpy.libs, pandas.libs …)
        base = name.split(".")[0]
        if os.path.isdir(os.path.join(SITE, base + ".libs")):
            entries.add(base + ".libs")
    # delvewheel-style DLLs lying loose in site-packages (pillow-heif's libheif, libde265, libx265 …)
    entries.update(f for f in os.listdir(SITE) if f.lower().endswith(".dll") and os.path.isfile(os.path.join(SITE, f)))
    import importlib.metadata as md
    dists = md.packages_distributions()
    lic = os.path.join(STAGE, "runtime", "licenses")
    for name in sorted(entries):
        src = os.path.join(SITE, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(sp, name), ignore=SITE_IGNORE)
        elif os.path.isfile(src):
            shutil.copy2(src, sp)
        # the distribution's metadata (some packages read their own version) and its licence files
        mod = name.split(".")[0]
        for dist in set(dists.get(mod, [])):
            try:
                d = md.distribution(dist)
            except md.PackageNotFoundError:
                continue
            info = str(d._path)   # noqa: SLF001
            if os.path.isdir(info) and not os.path.exists(os.path.join(sp, os.path.basename(info))):
                shutil.copytree(info, os.path.join(sp, os.path.basename(info)))
                dst = os.path.join(lic, os.path.basename(info))
                for root, _, files in os.walk(info):
                    for f in files:
                        if "licen" in f.lower() or "copying" in f.lower() or "notice" in f.lower() or root != info:
                            rel = os.path.relpath(os.path.join(root, f), info)
                            os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
                            shutil.copy2(os.path.join(root, f), os.path.join(dst, rel))
    size = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(sp) for f in fs)
    print(f"site-packages: {len(entries)} entries, {size / 2**20:.0f} MB")


def build_app():
    app = os.path.join(STAGE, "app")
    os.makedirs(app)
    for name in APP_FILES:
        shutil.copy2(os.path.join(MORPH, name), app)
    for sub in ("core", "web", "licenses"):
        shutil.copytree(os.path.join(MORPH, sub), os.path.join(app, sub), ignore=shutil.ignore_patterns("__pycache__"))
    tools = os.path.join(STAGE, "tools")
    os.makedirs(tools)
    for exe in ("ffmpeg", "ffprobe"):
        src = shutil.which(exe)
        real = os.path.join(r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin", exe + ".exe")
        shutil.copy2(real if os.path.exists(real) else src, tools)   # choco's PATH entry is only a shim
    # GPL programs ship with their licence text and where to get their exact source
    with open(os.path.join(tools, "FFMPEG-LICENSE.txt"), "w", encoding="utf-8") as f:
        f.write("FFmpeg 8.0.1 static build by gyan.dev (essentials), licensed GPL-3.0 (includes libx264 and libx265).\n"
                "Source of this version: https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz\n"
                "Build scripts: https://www.gyan.dev/ffmpeg/builds/\n"
                "The written offer for the source is in app\\THIRD-PARTY-NOTICES.txt.\n\n")
        with open(os.path.join(MORPH, "licenses", "GPL-3.0.txt"), encoding="utf-8") as g:
            f.write(g.read())
    setup = os.path.join(STAGE, "setup")
    os.makedirs(setup)
    for name in ("setup.py", "setup.html", "uninstall.py", "safety.py"):
        shutil.copy2(os.path.join(INSTALLER, name), setup)


def verify(expected):
    """Run the full conversion test on the bundled runtime only (no access to this PC's Python packages).
    It must offer and pass exactly as many conversions as the traced run - fewer means a format went missing."""
    tests = os.path.join(STAGE, "app", "tests")
    shutil.copytree(os.path.join(MORPH, "tests"), tests)
    scratch = tempfile.mkdtemp(prefix="morph-verify-")
    print("verifying the bundle (every conversion, bundled runtime only)…")
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    r = subprocess.run([os.path.join(STAGE, "runtime", "python.exe"), os.path.join(tests, "smoke.py"), scratch],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    shutil.rmtree(tests, ignore_errors=True)
    shutil.rmtree(scratch, ignore_errors=True)
    summary = next((l for l in r.stdout.splitlines() if " ok, " in l), "")
    if r.returncode != 0 or " 0 failed" not in summary:
        raise RuntimeError("The bundled runtime failed the conversion test:\n" + r.stdout[-4000:] + r.stderr[-3000:])
    print("  " + summary.strip())
    if int(summary.split()[0]) != expected:
        raise RuntimeError(f"The bundle offers {summary.split()[0]} conversions, the traced run {expected} - "
                           "a library is missing:\n" + r.stdout[-4000:])
    for dp, dn, _ in os.walk(STAGE):     # don't ship the bytecode the test run produced
        for d in list(dn):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dp, d), ignore_errors=True)


BOOTSTRAP = r"""@echo off
setlocal
set "L=%TEMP%\morph-setup-boot.log"
set "D=%TEMP%\Morph-Setup-%RANDOM%%RANDOM%"
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
FriendlyName=Morph Setup
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
    top, expected = trace_packages()
    build_runtime()
    copy_packages(top)
    build_app()
    if "--fast" not in sys.argv:
        verify(expected)
    # IExpress/makecab can't handle spaces in source paths, so the last step happens in %TEMP%
    pack = os.path.join(os.environ["TEMP"], "morph-pack")
    shutil.rmtree(pack, ignore_errors=True)
    os.makedirs(pack)
    payload = os.path.join(pack, "payload.zip")
    print("compressing…")
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for dirpath, _, filenames in os.walk(STAGE):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                z.write(full, os.path.relpath(full, STAGE))
    print(f"payload: {os.path.getsize(payload) / 2**20:.0f} MB")
    with open(os.path.join(pack, "setup.cmd"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(BOOTSTRAP)
    built = os.path.join(pack, SETUP_FILE)
    sed = os.path.join(pack, "morph.sed")
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
    print(f"{target} ({os.path.getsize(target) / 2**20:.1f} MB) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
