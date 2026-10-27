"""Checks every library template on this PC.

  python tests/check_library.py            fill every template with sample values and verify it
                                            (syntax, commands, parameters)
  python tests/check_library.py --run      also run the read-only ones
  python tests/check_library.py --sandbox  also run file/image/video templates inside a throwaway folder
"""
import os
import re
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import slots  # noqa: E402
from core.recipes import library  # noqa: E402
from core.shell import shell  # noqa: E402

RUN = "--run" in sys.argv
SANDBOX = "--sandbox" in sys.argv
BOX = os.path.join(tempfile.gettempdir(), "sensei-library-check")
SKIP_RUN = re.compile(r"Desktop|Register-ScheduledTask|Start-Process|Invoke-Item|notepad|explorer\.exe|Set-Wallpaper|"
                      r"Out-Speech|Start-MpScan|-Verb|Start-Timer|Start-Shutdown|Stop-Computer|Restart-Computer|"
                      r"Set-Clipboard|Save-Screenshot|-Wait\b|mspaint|Close-App|Stop-Process|shutdown|"
                      r"winget (install|uninstall|upgrade)|flm (pull|remove|run)|Set-Audio|Set-Screen|Set-DarkMode|"
                      r"Dismount|Format-Volume|Clear-TempFiles|Clear-RecycleBin|powercfg|wsl --shutdown|Set-ItemProperty|"
                      r"Install-Module|Test-InternetSpeed|Set-Service|Get-Help|SetSuspendState|Unblock|LockWorkStation", re.I)


def sample_values(it):
    words = " ".join(it["q"]).lower()
    file = "sample.txt"
    only = it["only"].get("file", set())
    if only & {"png", "jpg"}:
        file = "sample.png"
    elif only & {"mp4"}:
        file = "sample.mp4"
    elif "zip" in words and "unzip" in words or "inside" in words and "zip" in words:
        file = "sample.zip"
    elif "json" in words and "csv" not in words:
        file = "sample.json"
    elif "csv" in words or "table" in words:
        file = "sample.csv"
    ext = {"exts": ["txt"], "raw": "txt"}
    ext2 = {"exts": ["md"], "raw": "md"}
    if it["only"].get("ext", set()) & {"png"} or "image" in words or "resize" in words:
        ext, ext2 = {"exts": ["png"], "raw": "png"}, {"exts": ["jpg", "jpeg"], "raw": "jpg"}
    if it["only"].get("ext", set()) & {"mp4"}:
        ext = {"exts": ["mkv"], "raw": "mkv"}
    sub = lambda p: {"expr": os.path.join(BOX, p), "label": p}  # noqa: E731
    return {
        "folder": [sub("src"), sub("dest")], "file": [file, "renamed.txt"], "ext": [ext, ext2],
        "n": [5], "percent": [50], "port": [8080], "size": ["1KB"], "days": [7],
        "duration": [{"seconds": 3, "minutes": 1}], "time": ["23:30"], "date": ["2026-12-24"], "text": ["hello"],
        "name": ["demo"], "url": ["https://example.com/"], "host": ["example.com"],
        "app": [dict(slots.APPS["notepad"], alias="notepad")], "service": ["Spooler"], "tz": ["UTC"], "drive": ["C"],
        "model": ["qwen3:4b"], "page": ["ms-settings:sound"], "pkg": ["vlc"],
    }


def make_box():
    shutil.rmtree(BOX, ignore_errors=True)
    os.makedirs(os.path.join(BOX, "src", "sub"))
    os.makedirs(os.path.join(BOX, "dest"))
    code = f"""
$b = '{BOX}\\src'
Set-Content "$b\\sample.txt" "hello world`nsecond line`nhello again"
Set-Content "$b\\sub\\copy.txt" "hello world`nsecond line`nhello again"
Set-Content "$b\\sample.csv" "name,age`nAda,36`nAlan,41"
Set-Content "$b\\sample.json" '{{"a":1,"b":[1,2]}}'
Set-Content "$b\\Screenshot 1.txt" 'x'
New-Item -ItemType File "$b\\empty.txt" | Out-Null
New-Item -ItemType Directory "$b\\emptydir" | Out-Null
Add-Type -AssemblyName System.Drawing
$bmp = [System.Drawing.Bitmap]::new(64, 48); $g = [System.Drawing.Graphics]::FromImage($bmp); $g.Clear([System.Drawing.Color]::Orange); $g.Dispose()
$bmp.Save("$b\\sample.png", [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Save("$b\\photo2.png", [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
Compress-Archive -Path "$b\\sample.txt" -DestinationPath "$b\\sample.zip"
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {{ ffmpeg -hide_banner -loglevel error -y -f lavfi -i testsrc=duration=2:size=160x120:rate=10 -f lavfi -i sine=duration=2 -shortest "$b\\sample.mp4" }}
'ok'
"""
    out = list(shell.run(code))
    if out[-1][1].get("ok") is not True:
        print("sandbox setup failed:", out)


shell.start()
print("PowerShell ready:", shell.env.get("ps"))
bad = ran = run_fail = 0
fails = []
t0 = time.time()
ONLY = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")), "")
for it in library.items:
    if ONLY and not it["source"].startswith(ONLY):
        continue
    code, missing, _ = slots.fill(it["cmd"], sample_values(it), "", it["defaults"])
    v = shell.verify(code)
    probs = (v.get("syntax") or []) + (v.get("problems") or [])
    if probs:
        bad += 1
        fails.append((it["source"], it["q"][0], code, probs))
        print(f"PROBLEM {it['source']:22} {it['q'][0][:50]}\n    {code[:240]}\n    -> {'; '.join(probs)[:300]}")
        continue
    in_box = BOX in code
    runnable = not it["admin"] and not v.get("interactive") and not SKIP_RUN.search(code) and "<" not in code
    if runnable and ((RUN and v["risk"] == "safe" and not in_box) or (SANDBOX and in_box and v["risk"] != "danger")):
        if in_box:
            make_box()
        errs, info = [], {}
        t_run = time.time()
        watchdog = threading.Timer(60, shell.stop)   # one stuck command must not stall the whole check
        watchdog.start()
        for kind, data in shell.run(code):
            if kind == "done":
                info = data
            elif kind == "err":
                errs.append(data)
        watchdog.cancel()
        if time.time() - t_run > 59:
            errs.append("TIMEOUT after 60 s")
        ran += 1
        if errs or not info.get("ok"):
            run_fail += 1
            fails.append((it["source"], it["q"][0], code, errs))
            print(f"RUN FAIL {it['source']:22} {it['q'][0][:50]}\n    {code[:240]}\n    -> {' | '.join(errs)[:300]} {info}")
print(f"\n{len(library.items)} templates checked in {time.time() - t0:.0f}s: {bad} with problems; "
      f"ran {ran}, {run_fail} failed at run time")
shutil.rmtree(BOX, ignore_errors=True)
