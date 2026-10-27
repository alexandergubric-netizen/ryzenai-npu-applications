"""Compares FastFlowLM models on Sensei's two AI jobs:
  routing   - pick the right tested task for a paraphrased request (45 cases)
  writing   - write a new read-only command; it must pass the checker, run without errors and do the right thing (15 cases)
Usage: python tests/model_bench.py qwen3-it:4b lfm2.5-it:1.2b ...   (results -> tests/model_bench.json)"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import assistant, router  # noqa: E402
from core.llm import npu  # noqa: E402
from core.recipes import library  # noqa: E402
from core.shell import shell  # noqa: E402

ROUTE = [
    ("my computer is really slow, what's hogging the processor", r"PercentProcessorTime"),
    ("free up some disk space", r"Clear-TempFiles|cleanmgr"),
    ("I want to see how full my hard drive is", r"Get-PSDrive|Get-Volume"),
    ("get rid of everything in my downloads older than 30 days", r"AddDays\(-30\).*Remove-ToRecycleBin"),
    ("make my screen less bright", r"Set-ScreenBrightness"),
    ("crank the volume all the way up", r"Set-AudioVolume -(Percent 100|Up)"),
    ("silence my laptop", r"Set-AudioVolume -Mute"),
    ("what's the name of the wifi I'm on", r"netsh wlan show interfaces"),
    ("forget about the shutdown I scheduled", r"Stop-Shutdown"),
    ("power off the laptop in half an hour", r"Start-Shutdown -InMinutes 30\b"),
    ("snap a picture of my screen", r"Save-Screenshot"),
    ("which programs launch by themselves when I log in", r"Win32_StartupCommand"),
    ("chrome froze, close it", r'Name "chrome"'),
    ("is anything listening on port 5000", r"LocalPort 5000"),
    ("how many gigs of memory does this machine have", r"Win32_PhysicalMemory|TotalPhysicalMemory|TotalVisibleMemorySize"),
    ("gimme my ip", r"Get-NetIPAddress|Get-PublicIP"),
    ("get me the newest version of firefox", r"winget (upgrade|install) --id Mozilla\.Firefox"),
    ("tidy my desktop into folders by file type", r"Extension\.TrimStart.*|GetFolderPath\('Desktop'\)"),
    ("make the pc stay awake", r"standby-timeout-ac 0"),
    ("I need the password for the network I'm connected to", r"Get-WifiPassword"),
    ("print what's in readme.md", r'Get-Content -Path ".*readme\.md"'),
    ("dump the clipboard", r"Get-Clipboard"),
    ("grab the qwen3:1.7b model", r"flm pull qwen3:1\.7b"),
    ("which ai models do I have", r"flm list"),
    ("check if google.com responds", r"Test-Connection -TargetName google\.com|google\.com"),
    ("what version of windows is this", r"Win32_OperatingSystem"),
    ("are any devices not working properly", r"ERROR"),
    ("battery percentage please", r"EstimatedChargeRemaining"),
    ("take me to the windows update page", r"windowsupdate"),
    ("murder whatever is using port 3000", r"LocalPort 3000.*Stop-Process"),
    ("how much room is my downloads folder taking", r'Get-FolderSize -Path "\$HOME\\Downloads"'),
    ("pack the pictures folder into a zip", r"Compress-Archive"),
    ("look for files bigger than 2 gigs", r"Length -gt 2GB"),
    ("reboot my machine in 15 min", r"-InMinutes 15 -Restart"),
    ("turn the brightness right down", r"Set-ScreenBrightness"),
    ("wipe my temp junk", r"Clear-TempFiles"),
    ("which apps are talking to the internet", r"Established"),
    ("is my antivirus ok", r"Get-MpComputerStatus"),
    ("update everything that is installed", r"upgrade --all"),
    ("show the biggest folders in my user directory", r"Get-FolderSize -Path \"?\$HOME\"? -Subfolders"),
    ("lock the screen now", r"LockWorkStation"),
    ("switch the clock to tokyo time", r"Tokyo Standard Time"),
    ("put the computer to sleep", r"SetSuspendState"),
    ("safely remove my usb stick E", r"Dismount-Drive -Letter E"),
    ("how long has windows been running", r"Get-Uptime"),
]

WRITE = [
    ("list the 5 processes with the most handles", r"Handle"),
    ("show environment variables whose name contains PATH", r"(?i)env:"),
    ("count the .ps1 files in my Documents folder", r"(?i)\.ps1"),
    ("show the 10 newest entries of the Application event log", r"Get-WinEvent"),
    ("show services that start automatically and are running", r"StartType"),
    ("show my default web browser", r"(?i)UserChoice|http"),
    ("list the installed fonts", r"(?i)fonts"),
    ("what CPU architecture is this PC", r"(?i)architecture"),
    ("count how many processes are running", r"(?i)count|Measure-Object"),
    ("list files in Downloads that were modified on a weekend", r"DayOfWeek"),
    ("show which local user accounts are disabled", r"Enabled"),
    ("print today's date in ISO 8601 format", r"Get-Date"),
    ("list network adapters that are disconnected", r"Get-NetAdapter"),
    ("show the 5 processes that started most recently", r"StartTime"),
    ("show how many files of each extension are on my Desktop", r"Group-Object"),
]


def run_ok(code, timeout=90):
    """Runs a read-only command; True if it finished without errors."""
    errs, info = [], {}
    t = time.time()
    for kind, data in shell.run(code):
        if kind == "done":
            info = data
        elif kind == "err":
            errs.append(data)
        if time.time() - t > timeout:
            shell.stop()
            return False, ["timeout"]
    return (not errs and bool(info.get("ok"))), errs[:2]


def bench(model):
    res = {"model": model, "route": [], "write": []}
    npu.complete([{"role": "user", "content": "hi"}], max_tokens=1, model=model)   # load it onto the NPU
    t_route = []
    for q, want in ROUTE:
        exact = library.exact(q)
        t = time.time()
        task, reply = router.route(q, model=model)
        dt = time.time() - t
        t_route.append(dt)
        code = task["code"] if task else ""
        ok = bool(task) and re.search(want, code, re.S) is not None
        res["route"].append({"q": q, "ok": ok, "s": round(dt, 2), "exact": bool(exact),
                             "reply": reply[:120], "code": code[:160]})
        print(f"  route {'OK ' if ok else 'BAD'} {dt:4.1f}s {q[:55]:55} -> {reply[:60]!r}")
    tps, ttft = [], []
    for q, want in ([] if "--route-only" in sys.argv else WRITE):
        t = time.time()
        ans = None
        for ev in assistant.ask(q, instant=False, model=model, use_router=False):
            if ev["type"] == "answer":
                ans = ev
        dt = time.time() - t
        code = ans["code"] if ans else ""
        check = ans["check"] if ans else None
        clean = bool(code) and check is not None and not assistant.all_problems(q, check)
        ran, errs = (run_ok(code) if clean and check.get("risk") == "safe" else (False, ["not safe/clean"]))
        good = clean and ran and re.search(want, code) is not None
        if npu.tps:
            tps.append(npu.tps)
        if npu.ttft:
            ttft.append(npu.ttft)
        res["write"].append({"q": q, "ok": good, "clean": clean, "ran": ran, "s": round(dt, 1), "code": code[:200],
                             "errs": errs, "repairs": ans["repairs"] if ans else None})
        print(f"  write {'OK ' if good else 'BAD'} {dt:4.1f}s {q[:55]:55} {code[:70]!r} {errs if not good else ''}")
    res["route_acc"] = sum(r["ok"] for r in res["route"]) / len(ROUTE)
    res["route_s"] = sum(t_route) / len(t_route)
    res["write_acc"] = sum(r["ok"] for r in res["write"]) / max(1, len(res["write"]))
    res["write_s"] = sum(r["s"] for r in res["write"]) / max(1, len(res["write"]))
    res["tps"] = round(sum(tps) / len(tps), 1) if tps else None
    res["ttft"] = round(sum(ttft) / len(ttft), 2) if ttft else None
    return res


if __name__ == "__main__":
    shell.start()
    npu.ensure()
    while npu.state == "starting":
        time.sleep(0.5)
    out_path = os.path.join(os.path.dirname(__file__), "model_bench.json")
    try:
        results = json.load(open(out_path, encoding="utf-8"))
    except (OSError, ValueError):
        results = {}
    for m in [a for a in sys.argv[1:] if not a.startswith("--")]:
        print(f"\n=== {m}")
        r = bench(m)
        results[m] = r
        json.dump(results, open(out_path, "w", encoding="utf-8"), indent=1)
        print(f"=== {m}: route {r['route_acc']:.0%} in {r['route_s']:.1f}s | write {r['write_acc']:.0%} in "
              f"{r['write_s']:.1f}s | {r['tps']} tok/s, first token {r['ttft']}s")
    print("\nmodel              route   r-time  write   w-time  tok/s  ttft")
    for m, r in results.items():
        print(f"{m:18} {r['route_acc']:5.0%}  {r['route_s']:5.1f}s  {r['write_acc']:5.0%}  {r['write_s']:5.1f}s  "
              f"{r['tps']}  {r['ttft']}")
