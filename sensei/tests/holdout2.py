"""A second set of fresh, casually worded requests (written after all tuning): an honest measure of coverage.
Usage: python tests/holdout2.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import assistant  # noqa: E402
from core.llm import npu  # noqa: E402
from core.shell import shell  # noqa: E402

REQUESTS = [
    "whats hogging my memory", "make the screen dimmer", "where did all my disk space go",
    "show me hidden stuff in documents", "nuke the old installers in my downloads", "is spotify open",
    "what version of powershell do i have", "boost the volume a bit", "my wifi password pls",
    "which drive has the most free space", "show the network adapters that are connected",
    "I want a screenshot in 10 seconds", "open control panel", "stop onedrive", "how much battery do i have",
    "copy all my music to the D drive", "turn the sound down to 20", "list everything in program files", "what's my mac",
    "kill whatever is on port 5173", "get the newest version of vlc", "show me the 5 biggest files on my desktop",
    "make a zip of the pictures folder", "what time is it in new york", "find word documents in my documents folder",
]

if __name__ == "__main__":
    shell.start()
    npu.ensure()
    while npu.state == "starting":
        time.sleep(0.5)
    counts, total = {}, 0.0
    for q in REQUESTS:
        t = time.time()
        ans = next(ev for ev in assistant.ask(q) if ev["type"] == "answer")
        dt = time.time() - t
        total += dt
        how = ans["model"] if ans["model"] in ("library", "router") else "ai"
        counts[how] = counts.get(how, 0) + 1
        first = (ans["code"] or ans["text"] or "(nothing)").splitlines()[0][:110]
        print(f"[{how:7}] {dt:4.1f}s {q:45} => {first}")
    print(f"\n{len(REQUESTS)} requests: {counts}, average {total / len(REQUESTS):.1f}s")
