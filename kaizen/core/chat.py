"""Chat with your files: retrieve the relevant rows from the scan, hand them to the local model as context.

Accuracy rules learned from tests\\chat_eval.py:
  * retrieval must never come back empty for a general question ("what should I clean up?") - an empty context
    makes a small model invent items
  * each data line states ONE clear action per issue (recycle / move to X / rename to Y) so the model can't mix them
  * facts (counts, sizes) live in a FACTS block the model is told to quote from
"""
import json
import re
import time

from . import db, edition, scanner
from .ai import _fmt_size, _date

S_NAMES = {"sort": "Seiri (Sort)", "order": "Seiton (Set in order)", "shine": "Seiso (Shine)",
           "std": "Seiketsu (Standardize)", "sustain": "Shitsuke (Sustain)"}
ACTION = {"sort": "can go to the Recycle Bin", "shine": "can be cleaned away (Recycle Bin)",
          "order": "move to {target}", "std": "rename to “{new_name}”"}

# word-boundary patterns: "old" must not match "folder", "app" must not match "happen"
INTENTS = [
    ("space", r"\b(space|free|freed|reclaim|disk|storage|gb|mb|big|biggest|large|largest|heavy)\b"),
    ("duplicates", r"\bduplicat\w*|\bcop(y|ies)\b|\bsame file"),
    ("sort", r"\b(seiri|sort|unused|old|oldest|stale|forgotten|ages|delete|remove)\b|haven.?t (used|opened|touched)"),
    ("order", r"\b(seiton|order|misplaced|move|organi[sz]e|place|downloads|desktop)\b"),
    ("shine", r"\b(seiso|shine|temp|temporary|junk|installers?|empty|broken|leftovers?)\b"),
    ("std", r"\b(seiketsu|standardi[sz]e|naming|names?|rename)\b"),
    ("sustain", r"\b(shitsuke|sustain|healthy|good shape|in order)\b"),
    ("folders", r"\bfolders?\b.*\b(attention|worst|messiest|most|needs?)\b|\bwhich folders?\b"),
]
CATS = [("image", r"\b(photos?|pictures?|images?|screenshots?)\b"), ("video", r"\b(videos?|movies?|clips?)\b"),
        ("audio", r"\b(music|songs?|audio)\b"), ("pdf", r"\bpdfs?\b"), ("document", r"\b(documents?|word|docx?)\b"),
        ("spreadsheet", r"\b(excel|spreadsheets?|sheets?|xlsx|csv)\b"), ("installer", r"\b(installers?|setup|exe|msi)\b"),
        ("archive", r"\b(zips?|rar|archives?|7z)\b")]

SYSTEM = """You are Kaizen, a calm, practical assistant that runs fully offline on the user's own PC.
You help the user keep their PC tidy with the Japanese 5S method:
Seiri (Sort), Seiton (Set in order), Seiso (Shine), Seiketsu (Standardize), Shitsuke (Sustain).

How to answer:
- Start with ONE short sentence that answers the question, using numbers from FACTS only.
- Then up to 5 bullets, each exactly like:  - [F12] short reason in your own words (max 12 words)
- Use only tags that appear in DATA, one tag per bullet. Never write a tag range and never invent a tag.
- Give each item the action written in its DATA line - don't swap "move" and "recycle".
- If DATA is empty, say so plainly and suggest running a 5S check or asking differently. Don't write any tag then.
- Never copy DATA lines. Never suggest removing drivers, runtimes, security software or app data.
- You can't change anything yourself: the user does it with Kaizen's buttons. Files go to the Recycle Bin.
- At most about 110 words.
Today is {today}.

FACTS
{facts}

DATA
{data}"""


def _days(q):
    m = re.search(r"(\d+)\s*(day|week|month|year)", q)
    if m:
        return int(m.group(1)) * {"day": 1, "week": 7, "month": 30, "year": 365}[m.group(2)]
    if re.search(r"half a year|six months", q):
        return 182
    if re.search(r"\b(a|one|last) year\b", q):
        return 365
    return None


def _where(path, root_name):
    parts = path.split("\\")
    return "\\".join(parts[-2:]) if len(parts) > 2 else root_name


def _file_line(r, focus=None):
    reasons = json.loads(r["reasons"] or "[]")
    if focus:  # a Seiton question only needs the Seiton action, not the duplicate/rename ones too
        reasons = [x for x in reasons if x["s"] in focus] or reasons
    actions = []
    for x in reasons:
        act = ACTION.get(x["s"], "").format(target=_where(r["target"] or "", ""), new_name=r["new_name"] or "")
        actions.append(f"{x['t']} → {act}" if act else x["t"])
    head = f"[F{r['id']}] “{r['name']}” ({r['category']}, {_fmt_size(r['size'])}, in {_where(r['dir'], r['root_name'])})"
    if r["managed"]:
        return f"{head}: app data, leave alone."
    return f"{head}: " + ("; ".join(actions) if actions else f"no issues, last used {_date(r['last_used'])}") + "."


def _prog_line(r):
    reasons = "; ".join(x["t"] for x in json.loads(r["reasons"] or "[]"))
    size = _fmt_size(r["size"]) if r["size"] else "size unknown"
    if r["kind"] == "leftover":
        return f"[P{r['id']}] leftover folder “{r['name']}” in Program Files ({size}): {reasons}."
    used = f"last used {_date(r['last_run'])}" if r["last_run"] else "never seen in use"
    if r["protected"]:
        return f"[P{r['id']}] “{r['name']}” ({size}, {used}): PROTECTED ({r['protect_reason']}), keep it."
    if not reasons:
        return f"[P{r['id']}] “{r['name']}” by {r['publisher'] or 'unknown publisher'} ({size}, {used}): in use, keep it."
    action = ("uninstall it in Kaizen's Programs tab if you don't need it" if edition.get()["allow_uninstall"]
              else "ask IT to remove it if you don't need it")
    return f"[P{r['id']}] program “{r['name']}” ({size}, {used}): {reasons} → {action} (programs never go to the Recycle Bin)."


def build_context(question):
    q = question.lower()
    sc = scanner.scores()
    facts = []
    if sc:
        c = sc["counts"]
        facts.append(f"5S score {sc['overall'] * 100:.0f}%: " + ", ".join(
            f"{S_NAMES[k]} {v * 100:.0f}%" for k, v in sc["scores"].items()) + ".")
        facts.append(f"Files to review: {c['sort']} to sort out, {c['order']} to move, {c['shine']} to clean, "
                     f"{c['std']} to rename. {c['sustain']} files are in good shape.")
        facts.append(f"Space that could be freed (Sort + Shine items): {_fmt_size(sc['reclaim'])}. "
                     f"Personal files scanned: {sc['files']}.")
    else:
        facts.append("No 5S check has been run yet. Tell the user to press 'Run 5S check'.")
    pc = db.one("SELECT COUNT(*) n, SUM(kind='app' AND i_sort) unused, SUM(i_std) dup, SUM(kind='leftover') lo, "
                "SUM(protected) prot FROM programs")
    if pc and pc["n"]:
        facts.append(f"Programs: {pc['n'] - (pc['lo'] or 0)} installed, {pc['unused'] or 0} unused for a long time, "
                     f"{pc['dup'] or 0} duplicating another program's job, {pc['lo'] or 0} leftover folders.")

    intents = {name for name, pat in INTENTS if re.search(pat, q)}
    wants_programs = bool(re.search(r"\b(programs?|apps?|software|applications?|install\w*|uninstall\w*|games?|tools?)\b", q))
    days = _days(q)
    cat = next((c for c, pat in CATS if re.search(pat, q)), None)
    folder = None
    for f in db.rows("SELECT path, name FROM folders WHERE length(name) >= 4 AND need != 'app' ORDER BY length(path)"):
        if re.search(r"(?<!\w)" + re.escape(f["name"].lower()) + r"(?!\w)", q):
            folder = f
            break
    data, items, rows_f, rows_p = [], [], [], []

    if "folders" in intents:
        top = db.rows("SELECT * FROM folders WHERE need NOT IN ('sustain','app') AND files >= 2 "
                      "ORDER BY (sort_n + order_n + shine_n + std_n) DESC LIMIT 5")
        for f in top:
            data.append(f"Folder “{f['name']}” ({_where(f['path'], f['root_name'])}): {f['files']} files, "
                        f"{f['sort_n']} to sort out, {f['order_n']} to move, {f['shine_n']} to clean, "
                        f"{f['std_n']} to rename. Needs {S_NAMES.get(f['need'], f['need'])} most.")
        if top:
            folder = folder or top[0]

    general = not (intents - {"folders"}) and not wants_programs and not cat and not days
    file_words = bool(re.search(r"\b(files?|folders?|photos?|pictures?|documents?|downloads|desktop|pdfs?|videos?|"
                                r"music|duplicat\w*|space|names?)\b", q)) or cat or folder
    hints = []
    focus = {k for k in ("sort", "order", "shine", "std") if k in intents}
    if "space" in intents:
        focus |= {"sort", "shine"}
    if "duplicates" in intents:
        focus |= {"sort"}
    if not wants_programs or file_words:
        where, args = ["managed IS NULL"], []
        if "duplicates" in intents:
            where.append("dup_group IS NOT NULL AND i_sort=1")
        elif "space" in intents:
            where.append("(i_sort=1 OR i_shine=1)")
        elif "sustain" in intents and len(intents) == 1:
            where.append("sustained=1")
        else:
            flags = [f"i_{k}=1" for k in ("sort", "order", "shine", "std") if k in intents]
            where.append("(" + " OR ".join(flags or ["i_sort=1", "i_order=1", "i_shine=1", "i_std=1"]) + ")")
        if days:
            where.append("last_used < ?")
            args.append(time.time() - days * 86400)
        if cat:
            where.append("category = ?")
            args.append(cat)
        if folder:
            where.append("(dir = ? OR substr(dir, 1, ?) = ?)")
            args += [folder["path"], len(folder["path"]) + 1, folder["path"] + "\\"]
        if "space" in intents or "duplicates" in intents:
            order = "size DESC"
        elif "sort" in intents and "space" not in intents:
            order = "last_used ASC"
        else:  # general: deletable things first, then the rest - biggest wins first
            order = "(i_sort + i_shine) DESC, size DESC"
        w = " AND ".join(where)
        total = db.one(f"SELECT COUNT(*) n, COALESCE(SUM(size),0) b FROM files WHERE {w}", args)
        rows_f = db.rows(f"SELECT * FROM files WHERE {w} ORDER BY {order} LIMIT {4 if general else 5}", args)
        if total["n"]:
            what = ("duplicate files" if "duplicates" in intents else
                    "files that could be removed to free space" if "space" in intents else
                    "files to move" if focus == {"order"} else "files to rename" if focus == {"std"} else
                    "files in good shape" if "sustain" in intents and len(intents) == 1 else "files to review")
            where_txt = f" in {folder['name']}" if folder else ""
            hints.append(f"There are {total['n']} {what}{where_txt} ({_fmt_size(total['b'])}). "
                         f"Start with these {len(rows_f)}:")
    if wants_programs or general:
        where = ["kind='app' AND protected=0"]
        if "shine" in intents or re.search(r"leftover", q):
            where = ["kind='leftover'"]
        elif "duplicates" in intents or re.search(r"\b(same job|several|multiple|too many)\b", q):
            where.append("dup_group IS NOT NULL")
        elif "sustain" in intents or re.search(r"\b(active|often|daily)\b", q):
            where.append("sustained=1")
        else:
            where.append("(i_sort=1 OR i_std=1)")
        order = "size DESC" if "space" in intents else "COALESCE(NULLIF(last_run,0), installed) ASC"
        w = " AND ".join(where)
        n = db.one(f"SELECT COUNT(*) n FROM programs WHERE {w}")["n"]
        rows_p = db.rows(f"SELECT * FROM programs WHERE {w} ORDER BY {order} LIMIT {2 if general else 5}")
        if n:
            hints.append(f"{n} programs match. Here are {len(rows_p)} of them:")

    data += [_file_line(r, focus) for r in rows_f] + [_prog_line(r) for r in rows_p]
    if hints:
        facts.insert(0, "ANSWER STARTS WITH THIS (rephrase if you like, keep the numbers): " + " ".join(hints))
    for r in rows_f:
        items.append({"ref": f"F{r['id']}", "kind": "file", "id": r["id"], "name": r["name"], "size": r["size"],
                      "path": r["path"], "category": r["category"], "mtime": r["mtime"], "cloud": r["cloud"],
                      "reasons": json.loads(r["reasons"] or "[]")})
    for r in rows_p:
        items.append({"ref": f"P{r['id']}", "kind": "program", "id": r["id"], "name": r["name"], "size": r["size"],
                      "exe": r["exe"], "location": r["location"], "reasons": json.loads(r["reasons"] or "[]")})
    system = SYSTEM.format(today=time.strftime("%Y-%m-%d"), facts="\n".join(facts),
                           data="\n".join(data) or "(empty - nothing in the scan matches this question)")
    ed = edition.get()
    if not ed["allow_uninstall"]:
        system += (f"\n\nThis is a company PC of {ed['org']}. The user is NOT allowed to uninstall programs. Never tell them "
                   "to uninstall; suggest asking company IT to remove programs they no longer need.")
    return system, items
