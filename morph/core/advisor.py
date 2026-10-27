"""The AI format advisor: a small NPU model, grounded in the file's real facts and Morph's format notes.

The model only sees formats Morph can actually produce, and its picks are checked against that list,
so it cannot recommend something that does not exist.
"""
import logging
import re

from .formats import FORMATS
from .inbox import human_size, human_time
from .llm import npu

log = logging.getLogger("morph")

SYSTEM = (
    "You are the format advisor inside Morph, an offline file converter. "
    "Recommend output formats for the user's file using ONLY the facts and the format list given. "
    "Be concrete and practical, no filler, no headings, no tables. "
    "Write exactly 3 bullet points, best first, each naming one format in bold and saying when to pick it, "
    "its upside for THIS file and its downside. Example of the style:\n"
    "- **WebP** - best for sharing online: roughly a third smaller than this 2.4 MB JPG with the same look. "
    "Downside: some older photo editors can't open it.\n"
    "Use the file's real properties (size, resolution, codec, pages...) where they matter. "
    "Recommend the 're-compressed (same format)' option only if the file is big (over 20 MB) or the user wants "
    "it smaller. "
    "Finish with exactly one line: BEST: id1, id2, id3  (the ids from the list, best first)."
)


def describe(e):
    f = FORMATS[e["fid"]]
    info = e["info"]
    lines = [f"File: {e['name']} - {f['name']} ({f['cat']}), {human_size(e['size'])}"]
    if e.get("facts"):
        lines.append("Facts: " + ", ".join(e["facts"]))
    if info.get("bitrate") and info.get("duration"):
        lines.append(f"Overall bitrate: {info['bitrate'] // 1000} kb/s over {human_time(info['duration'])}")
    if info.get("tags"):
        tags = {k: v for k, v in info["tags"].items() if k in ("make", "model", "com.apple.quicktime.model", "encoder")}
        if tags:
            lines.append("Recorded with: " + ", ".join(str(v) for v in tags.values())[:120])
    lines.append(f"About {f['name']}: + {f['up']}; - {f['down']}")
    return "\n".join(lines)


def candidates(e, limit=10):
    ts = {t["id"]: t for t in e["targets"]}
    order = list(e.get("picks") or [])
    for t in e["targets"]:
        if t["id"] not in order and not t["compress"]:
            order.append(t["id"])
    order = order[:limit - 1] + [t["id"] for t in e["targets"] if t["compress"]]  # re-compressing goes last
    out = []
    for tid in order:
        t = ts[tid]
        note = f" [{t['note']}]" if t.get("note") else ""
        label = f"{t['name']} re-compressed (same format, smaller)" if t["compress"] else t["name"]
        out.append(f"- {label} (id={tid}): + {t['up']}; - {t['down']}{note}")
    return out


def advise(e, question=None, history=None, model=None):
    """Yields ('text', piece) while streaming, then ('best', [ids])."""
    question = (question or "").strip()
    goal = (f"The user says: \"{question}\". Answer that first in one sentence, then give the 3 bullets."
            if question else "Which 3 formats should I convert this file to, for the most common goals "
                             "(sharing, saving space, editing/archiving)?")
    prompt = (describe(e) + "\n\nFormats Morph can create from it:\n" + "\n".join(candidates(e)) +
              "\n\n" + goal)
    msgs = [{"role": "system", "content": SYSTEM}]
    for h in (history or [])[-4:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": str(h["content"])[:1500]})
    msgs.append({"role": "user", "content": prompt})
    valid = {t["id"] for t in e["targets"]}
    names = {t["name"].lower(): t["id"] for t in e["targets"]}
    full, sent = "", 0

    def visible(final):
        """Everything before the BEST: line (held back a little while it may still be arriving)."""
        i = full.find("BEST")
        text = full[:i] if i >= 0 else (full if final else full[:-8])
        return text.rstrip(" *\n") if (i >= 0 or final) else text

    for kind, piece in npu.stream(msgs, max_tokens=420, temperature=0.3, model=model):
        if kind != "text":
            yield "think", piece
            continue
        full += piece
        v = visible(False)
        if len(v) > sent:
            yield "text", v[sent:]
            sent = len(v)
    v = visible(True)
    if len(v) > sent:
        yield "text", v[sent:]
    log.info("advice for %s (%d chars): %r", e["name"], len(full), full[:160])
    yield "best", parse_best(full, valid, names)


def parse_best(text, valid, names):
    m = re.search(r"BEST\**\s*:\s*(.+)", text)
    picks = []
    if m:
        for tok in re.split(r"[,\s/]+", m.group(1).lower()):
            tok = tok.strip(".*`'\"()[]")
            tok = tok.replace("id=", "")
            if tok in valid and tok not in picks:
                picks.append(tok)
    if not picks:  # fall back to the bold names in the bullets
        for bold in re.findall(r"\*\*(.+?)\*\*", text):
            b = bold.lower().strip()
            tid = names.get(b) or (b if b in valid else None)
            if tid and tid not in picks:
                picks.append(tid)
    return picks[:3]
