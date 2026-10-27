"""Fresh, casually worded requests the library was NOT tuned on: shows how each is answered, how fast, with what.
Usage: python tests/holdout.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import assistant  # noqa: E402
from core.llm import npu  # noqa: E402
from core.shell import shell  # noqa: E402

REQUESTS = [
    "my laptop fan is loud, what's eating the cpu", "how much storage do i have left", "make it quieter",
    "what's my laptop's serial number", "show me everything I downloaded this week", "kill teams",
    "check if my internet is working", "can you mute the sound", "what wifi am i connected to",
    "list all the apps on this computer", "show my desktop files", "how hot is the cpu",
    "remove all .log files from my temp folder", "rename the folder Old to Archive", "how much ram does this laptop have",
    "show pdf files I downloaded", "what is taking up space on my C drive", "set brightness to max",
    "put my pc to sleep in 30 minutes", "find a file called invoice", "open the calculator", "turn off the screen",
    "show the 3 biggest videos in my videos folder", "who is connected to my wifi", "show me my network speed",
    "how many photos do I have", "zip the documents folder and put it on the desktop", "what's my windows build",
    "pause windows updates for a week", "show me processes that use more than 1 GB of RAM",
    "open the hosts file in notepad", "make a new folder named Taxes in documents", "list my bluetooth devices",
    "when did I last restart", "close all chrome windows", "empty my downloads folder", "show the startup programs",
    "check disk health", "how many days until new year", "what's the weather like",
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
        c = ans["check"] or {}
        probs = assistant.problems_of(c) if c else []
        print(f"[{how:7}] {dt:4.1f}s {c.get('risk', '-'):7} {q}\n          {(ans['code'] or ans['text']).splitlines()[0][:150] if (ans['code'] or ans['text']) else '(nothing)'}"
              + (f"\n          ! {probs[0][:120]}" if probs else ""))
    print(f"\n{len(REQUESTS)} requests: {counts}, average {total / len(REQUESTS):.1f}s")
