"""Timing of the non-AI parts: library load, matching, search and the PowerShell checker."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
t = time.time()
from core.recipes import library  # noqa: E402
print(f"library load: {time.time() - t:.2f}s ({len(library.items)} tasks)")
from core.shell import shell  # noqa: E402
from tests.stress import REQUESTS  # noqa: E402  (importing runs nothing heavy: guarded below)

t = time.time()
shell.start()
print(f"PowerShell hosts start: {time.time() - t:.2f}s")
t = time.time()
for q in REQUESTS:
    library.exact(q)
print(f"exact(): {(time.time() - t) / len(REQUESTS) * 1000:.1f} ms per request")
t = time.time()
for q in REQUESTS:
    library.search(q, k=3)
print(f"search(): {(time.time() - t) / len(REQUESTS) * 1000:.1f} ms per request")
for label in ("first verify", "second verify", "third verify"):
    t = time.time()
    shell.verify("Get-ChildItem $HOME -File | Sort-Object Length | Select-Object -First 3")
    print(f"{label}: {(time.time() - t) * 1000:.0f} ms")
t = time.time()
shell.verify("Set-AudioVolume -Percent 50; Get-NetAdapter; Get-PnpDevice -Class USB")
print(f"verify with module autoload: {(time.time() - t) * 1000:.0f} ms")
