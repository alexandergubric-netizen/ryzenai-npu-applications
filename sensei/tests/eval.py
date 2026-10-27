"""Runs a set of questions through the whole pipeline. Usage: python tests/eval.py [model]"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import assistant, config  # noqa: E402
from core.llm import npu  # noqa: E402
from core.shell import shell  # noqa: E402

QUESTIONS = [
    "show my ip address",
    "find the 10 largest files in my Documents folder",
    "which process is using port 3000",
    "list wifi networks I saved",
    "how long has my pc been on",
    "what's the password of my home wifi called MyHome5G",
    "how much free space is on my drives",
    "kill notepad",
    "show me all pdf files on my desktop",
    "which apps start automatically when windows starts",
    "how much ram does edge use in total",
    "delete all .tmp files in my Downloads folder",
    "what is my windows version",
    "list services that are running",
    "check if google.com is reachable",
    "show the last 20 errors from the system log",
    "find files bigger than 500 MB in my user folder",
    "update all my apps",
    "rename all .jpeg files in this folder to .jpg",
    "how many cores does my cpu have",
    "is my firewall turned on",
    "show my battery percentage",
    "copy all photos from Downloads to Pictures",
    "what does Get-ChildItem -Recurse do",
    "make a zip of my Desktop folder",
    "show my public ip",
    "list installed programs sorted by name",
    "what is my mac address",
    "show files I changed in the last 3 days in Documents",
    "flush the dns cache",
]

model = sys.argv[1] if len(sys.argv) > 1 else config.get()["model"]
config.update({"model": model})
shell.start()
npu.ensure()
while npu.state == "starting":
    time.sleep(0.5)
print("NPU:", npu.state, npu.detail, "model", model)

total = 0
for q in QUESTIONS:
    ans = None
    for ev in assistant.ask(q):
        if ev["type"] == "answer":
            ans = ev
        elif ev["type"] == "status" and ev.get("problems"):
            print("   repair:", ev["problems"])
    c = ans["check"] or {}
    total += ans["seconds"]
    flags = f"risk={c.get('risk')} problems={len(assistant.problems_of(c)) if c else '-'} repairs={ans['repairs']}"
    print(f"\n### {q}   [{ans['seconds']}s, {ans['tps']} tok/s, {flags}]\n{ans['code']}\n-- {ans['text'][:200]}")
print(f"\naverage {total / len(QUESTIONS):.1f}s per answer")
