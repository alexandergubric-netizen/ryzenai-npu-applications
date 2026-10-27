"""AI router: when a request does not match the library exactly, the model picks the right tested task
from the closest candidates (and fills in missing values) instead of writing a command from scratch.
The answer is a few tokens of JSON, so it is fast even on small models."""
import json
import re

from . import slots
from .llm import npu
from .recipes import library

ROUTER_SYSTEM = """You match a Windows request to one task from a numbered list.
Reply with JSON only, no other text: {"task": N, "values": {"slot": "value"}}
- N is the number of the task that does what the user wants. The user's words often differ from the task's words
  (casual, slang, typos): choose by meaning. Use 0 only if no task does what they want.
- The action must match: listing, opening, deleting, stopping or changing are different tasks.
- "values" holds only slots the task needs that the request names, written plainly (app name, folder, file name, number). Leave it {} otherwise."""


def _describe(i, r):
    slots_txt = ", ".join(f"{{{s}}}" for s in r["slots"] if s not in r["defaults"]) or "-"
    names = " / ".join(r["q"][:3])
    return f"{i}. {names} -- {r['note_filled'][:110]} (needs: {slots_txt})"


def candidates(question, k=8):
    return library.search(question, k=k, min_score=0.8)


def route(question, k=8, model=None, cands=None):
    """Returns (task dict filled in, raw model reply) or (None, reply)."""
    cands = cands if cands is not None else candidates(question, k)
    if not cands:
        return None, ""
    lines = "\n".join(_describe(i, r) for i, r in enumerate(cands, 1))
    msgs = [{"role": "system", "content": ROUTER_SYSTEM},
            {"role": "user", "content": f"Tasks:\n{lines}\n\nRequest: {question}"}]
    reply = npu.complete(msgs, max_tokens=60, temperature=0.1, model=model)
    m = re.search(r"\{.*\}", reply, re.S)
    if not m:
        n = re.search(r"\b(\d+)\b", reply)
        data = {"task": int(n.group(1))} if n else {}
    else:
        try:
            data = json.loads(m.group(0))
        except ValueError:
            n = re.search(r'"task"\s*:\s*(\d+)', m.group(0))
            data = {"task": int(n.group(1))} if n else {}
    try:
        n = int(data.get("task", 0))
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= len(cands):
        return None, reply
    chosen = cands[n - 1]
    # values: the request's own values first, then what the model named for slots still empty
    query = question
    extra = data.get("values") or {}
    if isinstance(extra, dict) and chosen["missing"]:
        added = " ".join(str(v) for s, v in extra.items() if s in chosen["missing"] and v)
        if added:
            query = f"{question} {added}"
    it = next(x for x in library.items if x["source"] == chosen["source"])
    return library.instantiate(it, query), reply
