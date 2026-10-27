"""Lists phrasings of different library tasks that read the same to the matcher (they would steal each other's requests)."""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.recipes import library  # noqa: E402

seen = defaultdict(list)
for (i, toks, lit), phrase in zip(library.phrases, [p for it in library.items for p in it["q"]]):
    key = (frozenset(toks), tuple(sorted((k, str(v[0])) for k, v in lit.items())))
    seen[key].append((i, phrase))
n = 0
for key, entries in seen.items():
    items = {i for i, _ in entries}
    if len(items) > 1:
        n += 1
        print(" vs ".join(f"[{library.items[i]['source']}] {p}" for i, p in entries))
print(f"\n{n} collisions")
