"""The smart part: a small model on the NPU (FastFlowLM, Qwen3) plans each archive.

It is grounded on facts Tansu measured (sizes, real compression ratios, this PC's speed), the rule engine's scored
options and the current library tree. It answers in JSON; every field is validated and anything missing or invalid
falls back to the rule plan, so a confused answer can never produce a bad archive or a strange folder.
"""
import json
import logging
import re
import time

from . import rules
from .llm import npu
from .rules import FORMATS, LAYOUTS, clean_folder, clean_part, human, human_secs, strip_archive_ext
from .scan import CAT_LABEL

log = logging.getLogger("tansu")

SYSTEM = (
    "You are the archiving assistant inside Tansu, an offline archiver for Windows. You plan how to pack the "
    "user's files and where to file the archive in their Archives library. Use ONLY the facts given.\n"
    "Reply with ONE JSON object and nothing else:\n"
    '{"format": "zip|7z|tar.xz", "level": "fast|balanced|max", "encrypt": true|false, '
    '"folder": "Top/Sub", "name": "...", "layout": "keep|by_type|by_date|flat", '
    '"why": "...", "tip": "..."}\n'
    "Rules:\n"
    "- format/level: prefer the option marked RECOMMENDED unless the user's request or the facts clearly say "
    "otherwise. Mention the real numbers (size, time) in why.\n"
    "- encrypt: true only for 7z and only when file names look personal, financial, medical or identity related.\n"
    "- folder: 1-3 levels, relative to the library root (never start it with Documents or Archives, never end "
    "it with the archive's own name - the archive is a file inside it). Reuse an existing folder when the "
    "content fits it, and follow the "
    "language and naming style of the existing folders. Otherwise invent a clear one in English like "
    "Photos/2024, Documents/Finance, Work/Projects, Software, Backups. Put a year level for photos, videos and "
    "documents that clearly belong to one year.\n"
    "- name: a short human title for the content (event, project, document type, place), max 50 characters, "
    "no file extension, no date at the start (Tansu adds the date). Base it on the file and folder names and "
    "write it in the SAME language as those names - never translate them. If the user added one folder, its "
    "name is usually the best title.\n"
    "- layout: keep = keep the user's own folders (default when they added folders); by_type = loose files of "
    "many kinds; by_date = many loose photos/videos over months; flat = a few loose files.\n"
    "- why: 2 short sentences for the user. tip: one concrete sentence about the library - where similar "
    "future archives should go or how to name them consistently. Do not repeat the layout or the format. "
    "Empty string if nothing useful.\n"
    "Write why and tip in English."
)


def facts_text(f):
    lines = [f"Items added: {len(f['roots'])} ("
             + ", ".join(("folder " if r["dir"] else "") + f"'{r['name']}'" for r in f["roots"][:8])
             + (" ..." if len(f["roots"]) > 8 else "") + ")",
             f"Total: {f['count']} files in {f['dirs']} folders, {human(f['total'])}"]
    cats = ", ".join(f"{CAT_LABEL.get(c, c)} {v['files']} files/{human(v['bytes'])}" for c, v in list(f["by_cat"].items())[:6])
    lines.append(f"Types: {cats}")
    lines.append("Top extensions: " + ", ".join(f".{e['ext']} x{e['files']}" for e in f["top_ext"][:6]))
    lines.append(f"Already compressed (photos/videos/Office/zip): {f['precompressed']:.0%} of the bytes")
    d = f["dates"]
    span = time.strftime("%Y-%m-%d", time.localtime(d["min"])) + " to " + time.strftime("%Y-%m-%d", time.localtime(d["max"]))
    lines.append(f"Modified: {span}; files per year: " + ", ".join(f"{y}: {n}" for y, n in list(d["years"].items())[-5:]))
    if f["dir_names"]:
        lines.append("Folder names: " + ", ".join(f["dir_names"][:12]))
    lines.append("File names: " + ", ".join(f["names"][:16]))
    if f["sensitive"]:
        lines.append("Names that look personal/financial: " + ", ".join(f["sensitive"][:6]))
    if f["project"]:
        lines.append("Project markers: " + ", ".join(f["project"]))
    if f["junk"]["files"]:
        lines.append(f"Junk that will be left out: {f['junk']['files']} files ({human(f['junk']['bytes'])})")
    return "\n".join(lines)


def options_text(opts):
    out = []
    for i, o in enumerate(opts):
        tag = " RECOMMENDED" if i == 0 else ""
        out.append(f"- {o['fmt']} level={o['level']}: ~{human(o['size'])} ({o['ratio']:.0%} of original), "
                   f"~{human_secs(o['secs'])} to create.{tag} " + "; ".join(o["reasons"][:3]))
    return "\n".join(out)


def build_messages(facts, opts, library, note=None, previous=None, base=None):
    prompt = (f"FILES\n{facts_text(facts)}\n\nFORMAT OPTIONS (measured on this PC)\n{options_text(opts)}\n\n"
              f"EXISTING FOLDERS IN THE LIBRARY (paths relative to the library root)\n{library}\n")
    if base:
        name = ("(none yet - write a short descriptive title from the file names)" if base.get("generic_name")
                else f"\"{base['name']}\"")
        prompt += (f"\nTANSU'S DEFAULT PLAN: folder \"{base['folder']}\", name {name}, layout {base['layout']}. "
                   "Keep it unless the names, the existing folders or the user give a reason for something better.\n")
    if previous:
        prompt += ("\nYOUR PREVIOUS PLAN\n" + json.dumps({k: previous.get(k) for k in
                   ("format", "level", "encrypt", "folder", "name", "layout")}, ensure_ascii=False) + "\n")
    if note:
        prompt += f"\nTHE USER SAYS: \"{note.strip()[:400]}\" - follow it and change the plan accordingly.\n"
    prompt += "\nJSON:"
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]


# qwen3.5 on FastFlowLM sometimes drops the opening quote of a text value: "why": These are...",
MISSING_QUOTE = re.compile(r'("[A-Za-z_]+"\s*:\s*)(?!(?:true|false|null)\b)(?=[^\s"\[{\d-])')


def parse(text):
    """The first {...} object in the answer, tolerating code fences, trailing commas and a dropped opening quote."""
    t = re.sub(r"```(?:json)?", "", text)
    for cand in (t, MISSING_QUOTE.sub(r'\1"', t)):
        obj = _first_object(cand)
        if obj is not None:
            return obj
    return None


def _first_object(t):
    start = t.find("{")
    if start < 0:
        return None
    depth, end, ins, esc = 0, None, False, False
    for i, ch in enumerate(t[start:], start):
        if ins:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                ins = False
            continue
        if ch == '"':
            ins = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    raw = t[start:end] if end else t[start:] + "}"
    raw = re.sub(r",\s*}", "}", raw)
    for fixed in (raw, raw.replace("'", '"')):
        try:
            obj = json.loads(fixed)
            return obj if isinstance(obj, dict) else None
        except ValueError:
            pass
    return None


def validate(ai, fallback, facts):
    """Merge the model's answer into the rule plan, keeping only valid values."""
    p = dict(fallback)
    if not isinstance(ai, dict):
        return p
    fmt = str(ai.get("format", "")).lower().strip(". ")
    fmt = {"tar": "tar.xz", "txz": "tar.xz", "xz": "tar.xz", "7zip": "7z", "7-zip": "7z"}.get(fmt, fmt)
    if fmt in FORMATS:
        p["format"] = fmt
    lvl = str(ai.get("level", "")).lower()
    if lvl in rules.LEVELS:
        p["level"] = lvl
    lay = str(ai.get("layout", "")).lower().replace("-", "_").replace(" ", "_")
    if lay in LAYOUTS:
        # never flatten or re-sort folders the user added on purpose unless they asked for it
        if not (lay != "keep" and any(r["dir"] for r in facts["roots"]) and fallback["layout"] == "keep"
                and not ai.get("_asked")):
            p["layout"] = lay
    p["encrypt"] = bool(ai.get("encrypt")) and FORMATS[p["format"]]["encrypt"]
    name = clean_part(strip_archive_ext(str(ai.get("name", ""))), 70).lstrip("-–—•* ")   # "- Dokumenty"
    name = re.sub(r"^\d{4}[-_.]\d{2}([-_.]\d{2})?\s*[-_]?\s*", "", name).strip() or name  # Tansu adds the date
    if len(name) >= 3 and not (name.startswith("(") and name.endswith(")")):   # not a "(none)" placeholder
        p["name"] = name
    parts = clean_folder(ai.get("folder", "")).split("/")
    while parts and parts[0].lower() in ("documents", "dokumenty", "archives", "archive", "library", "my documents"):
        parts.pop(0)        # the model sometimes repeats the library's own location
    roots = {strip_archive_ext(r["name"]).lower() for r in facts["roots"]}
    if len(parts) > 1 and (parts[-1].lower() == p["name"].lower() or parts[-1].lower() in roots):
        parts.pop()         # a folder named like the archive itself: one folder per archive is clutter
    folder = "/".join(x for x in parts if x)
    if folder and folder.lower() not in roots:
        p["folder"] = folder
    for k in ("why", "tip"):
        v = ai.get(k)
        if isinstance(v, str) and v.strip():
            p[k] = v.strip()[:600]
    p["source"] = "ai"
    return p


def advise(facts, opts, library, folders, note=None, previous=None):
    """Yields ('think', n) / ('tokens', n) while the model works (('status', text) if the engine had to be
    restarted), then ('plan', plan)."""
    base = rules.plan(facts, folders)
    fallback = previous or base
    msgs = build_messages(facts, opts, library, note, previous, None if previous else base)
    text, n = "", 0
    t0 = time.time()
    for kind, piece in npu.stream(msgs, max_tokens=360, temperature=0.2):
        if kind in ("think", "status"):
            yield kind, piece
            continue
        text += piece
        n += 1
        if n % 4 == 0:
            yield "tokens", n
    ai = parse(text)
    log.info("plan in %.1fs (%d chunks): %r", time.time() - t0, n, text[:400])
    if isinstance(ai, dict) and note:
        ai["_asked"] = True
    plan = validate(ai, fallback, facts)
    if ai is None:
        plan["source"] = "rules"
        plan["why"] = fallback["why"]
    yield "plan", plan


# ---------------------------------------------------------------- filing archives already in the library
FILE_SYSTEM = (
    "You file archives into folders of an Archives library. For each archive you get its name and a sample of "
    "the file names inside. Choose a folder path (1-3 levels) for each. Reuse the existing folders when they fit; "
    "otherwise invent clear English ones like Photos/2024, Documents/Finance, Projects, Software, Backups. "
    'Reply with ONE JSON object mapping each archive name to its folder, e.g. {"x.zip": "Photos/2023"}. Nothing else.'
)


def file_archives(entries, library):
    """entries: [{'name', 'sample': [...]}] -> {name: folder}"""
    lines = [f"- {e['name']}: " + ", ".join(e["sample"][:10]) for e in entries]
    msgs = [{"role": "system", "content": FILE_SYSTEM},
            {"role": "user", "content": f"LIBRARY FOLDERS\n{library}\n\nARCHIVES\n" + "\n".join(lines) + "\n\nJSON:"}]
    text = npu.complete(msgs, max_tokens=60 + 30 * len(entries), temperature=0.1)
    ai = parse(text) or {}
    out = {}
    for e in entries:
        v = ai.get(e["name"])
        if isinstance(v, str) and clean_folder(v):
            out[e["name"]] = clean_folder(v)
    return out
