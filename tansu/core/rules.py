"""Deterministic recommendations. They ground the AI (it chooses between these, with real numbers) and are the
fallback whenever the AI is off, busy or answers nonsense."""
import os
import re
import time

from .scan import CAT_LABEL

FORMATS = {
    "zip": {"name": "ZIP", "ext": ".zip", "encrypt": False, "append": True,
            "up": "Opens everywhere: Windows Explorer, macOS, phones, e-mail - no extra app needed. "
                  "Tansu stores photos/videos as-is and only compresses what shrinks, so it is also fast.",
            "down": "Bigger than 7z for documents, code and text; no strong encryption."},
    "7z": {"name": "7z", "ext": ".7z", "encrypt": True, "append": False,
           "up": "Smallest archives (LZMA2, solid). Optional AES-256 encryption that hides even the file names.",
           "down": "Slower to create; phones and older PCs need an app (Windows 11 opens it)."},
    "tar.xz": {"name": "TAR.XZ", "ext": ".tar.xz", "encrypt": False, "append": False,
               "up": "The Linux/macOS standard - keeps the whole tree in one stream, superb on code and logs.",
               "down": "No quick look inside: opening one file reads through the archive. Not for sharing with "
                       "Windows users who don't have Windows 11."},
}
LEVELS = {"fast": {"zip": 1, "lzma": 1, "speed": 2.2, "size": 1.06},
          "balanced": {"zip": 6, "lzma": 5, "speed": 1.0, "size": 1.0},
          "max": {"zip": 9, "lzma": 9, "speed": 0.55, "size": 0.96}}
LAYOUTS = {
    "keep": "Keep folders as they are",
    "by_type": "Sort into folders by type (Photos/, Documents/...)",
    "by_date": "Sort into year/month folders",
    "flat": "All files at the top level",
}
FOLDER_FOR = {"photo": "Photos", "video": "Videos", "audio": "Music", "document": "Documents",
              "spreadsheet": "Documents", "presentation": "Documents", "ebook": "Books", "code": "Projects",
              "design": "Design", "archive": "Archives", "software": "Software", "data": "Backups", "font": "Fonts",
              "mail": "Mail", "other": "Misc"}
BAD = re.compile(r'[<>:"|?*\x00-\x1f]')
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def clean_part(s, limit=60):
    s = BAD.sub("", str(s)).replace("/", "-").replace("\\", "-").strip().strip(".").strip()
    s = re.sub(r"\s+", " ", s)[:limit].strip().strip(".")
    if not s or s.lower() in RESERVED or s in (".", ".."):
        return ""
    return s


def clean_folder(path):
    parts = [clean_part(p, 40) for p in re.split(r"[\\/]+", str(path or ""))]
    parts = [p for p in parts if p and p.lower() != ".tansu"]
    return "/".join(parts[:4])


def strip_archive_ext(name):
    n = str(name)
    for e in (".tar.xz", ".tar.gz", ".tar.bz2", ".tar.zst", ".zip", ".7z", ".rar", ".tar", ".txz", ".tgz"):
        if n.lower().endswith(e):
            return n[: -len(e)]
    return n


def estimates(facts, fmt, level):
    """(bytes, seconds) for one choice, from the measured ratios and this PC's measured speed."""
    total, est, sp = facts["total"], facts["est"], facts["speeds"]
    L = LEVELS[level]
    pre = facts["precompressed"]
    if fmt == "zip":
        size = est["deflate"] * (L["size"] if level != "fast" else 1.04)
        # already-compressed files are stored, not deflated: ~disk speed
        secs = total * (1 - pre) / (sp["deflate"] * L["speed"]) + total * pre / 250e6
    else:
        size = est["lzma"] * L["size"]
        if fmt == "7z" and facts["count"] > 200:
            size *= 0.97        # solid block across many small files
        secs = total / (sp["lzma"] * L["speed"])
        if pre > .5:
            secs *= 0.8         # LZMA gives up faster on incompressible data
    size = min(size, total * 1.002 + 2048) + 200 + facts["count"] * (90 if fmt == "zip" else 30)
    return int(size), max(round(secs, 1), 0.2)


def options(facts, library=None):
    """Score every format; returns a list (best first) with estimates and plain reasons."""
    total = facts["total"]
    pre = facts["precompressed"]
    zip_size, zip_secs = estimates(facts, "zip", "balanced")
    out = []
    for fmt in FORMATS:
        reasons, score = [], {"zip": 50, "7z": 46, "tar.xz": 18}[fmt]
        level = "balanced"
        if fmt != "zip" and total < 400e6 and pre < .7:
            level = "max"
        size, secs = estimates(facts, fmt, level)
        saved_vs_zip = zip_size - size
        if fmt == "zip":
            if pre > .75:
                score += 30
                reasons.append(f"{pre:.0%} of the data is already compressed (photos/videos/Office files) - "
                               "no format can shrink it much, so the most compatible one wins")
            if total < 15e6:
                score += 15
                reasons.append("small enough that the format hardly changes the size")
            reasons.append("opens with a double-click on any computer or phone")
        else:
            gain = saved_vs_zip / max(zip_size, 1)
            if saved_vs_zip > 40e6 or (gain > .12 and total > 5e6):
                score += 26 if fmt == "7z" else 14
                reasons.append(f"about {gain:.0%} smaller than ZIP here ({human(saved_vs_zip)} saved)")
            elif gain < .04:
                score -= 12
                reasons.append("barely smaller than ZIP for these files")
            if secs > 900:
                score -= 18
                reasons.append(f"slow on this much data (~{human_secs(secs)})")
            if fmt == "7z":
                if facts["sensitive"]:
                    score += 70     # privacy outweighs compatibility
                    reasons.insert(0, "file names look personal/financial - 7z can encrypt the contents and the names")
                if facts["count"] > 2000:
                    score += 8
                    reasons.append("solid compression shines with thousands of small files")
            if fmt == "tar.xz" and facts["project"]:
                score += 22
                reasons.append("looks like a code project - tar keeps the tree exactly, the Unix standard")
        out.append({"fmt": fmt, "level": level, "score": score, "size": size, "secs": secs,
                    "ratio": size / total if total else 1, "reasons": reasons})
    out.sort(key=lambda o: -o["score"])
    return out


def dominant(facts):
    cats = facts["by_cat"]
    if not cats:
        return "other"
    first = next(iter(cats))
    # documents + spreadsheets + presentations count together
    office = sum(cats.get(c, {"files": 0})["files"] for c in ("document", "spreadsheet", "presentation"))
    if office > facts["count"] * .5 and first not in ("photo", "video"):
        return "document"
    by_files = max(cats, key=lambda c: cats[c]["files"])
    if cats[first]["bytes"] > facts["total"] * .55:
        return first
    return by_files


def main_year(facts):
    # a year in the name the user gave it ("Holiday 2024") beats the file dates (copies get new dates)
    for r in facts["roots"]:
        m = re.search(r"(?<!\d)(19[89]\d|20[0-4]\d)(?!\d)", r["name"])
        if m:
            return int(m.group(1))
    years = facts["dates"]["years"]
    return max(years, key=years.get) if years else time.localtime().tm_year


def layout(facts):
    roots = facts["roots"]
    loose = [r for r in roots if not r["dir"]]
    if any(r["dir"] for r in roots):
        return "keep"
    cats = [c for c, v in facts["by_cat"].items() if v["files"] >= max(2, facts["count"] * .1)]
    if len(loose) >= 8 and len(cats) >= 3:
        return "by_type"
    media = sum(facts["by_cat"].get(c, {"files": 0})["files"] for c in ("photo", "video"))
    span = facts["dates"]["max"] - facts["dates"]["min"]
    if len(loose) >= 12 and media > facts["count"] * .7 and span > 60 * 86400:
        return "by_date"
    return "keep"


def folder_and_name(facts, library_folders=()):
    cat = dominant(facts)
    year = main_year(facts)
    base = FOLDER_FOR.get(cat, "Misc")
    if facts["sensitive"] and cat in ("document", "other", "photo"):
        base = "Personal"
    # reuse an existing top-level folder with the same meaning, whatever its case
    for f in library_folders:
        if f.split("/")[0].lower() == base.lower():
            base = f.split("/")[0]
            break
    folder = f"{base}/{year}" if cat in ("photo", "video", "document", "spreadsheet", "presentation", "mail") else base
    roots = facts["roots"]
    if len(roots) == 1:
        name = os.path.splitext(roots[0]["name"])[0] if not roots[0]["dir"] else roots[0]["name"]
    else:
        common = os.path.commonprefix([r["name"] for r in roots]).strip(" -_.(")
        month = facts["dates"]["top_month"] or str(year)
        name = common if len(common) >= 4 else f"{CAT_LABEL.get(cat, 'Files')} {month}"
    return folder, clean_part(strip_archive_ext(name)) or "Archive"


def plan(facts, library_folders=()):
    """The full rule-based plan - same shape as the AI's."""
    opts = options(facts)
    best = opts[0]
    folder, name = folder_and_name(facts, library_folders)
    why = "; ".join(best["reasons"][:2]) or "a good all-round choice for these files"
    generic = len(facts["roots"]) > 1 and any(name.startswith(label + " ") for label in CAT_LABEL.values())
    return {"format": best["fmt"], "level": best["level"], "encrypt": bool(facts["sensitive"]) and best["fmt"] == "7z",
            "folder": folder, "name": name, "generic_name": generic, "layout": layout(facts), "append_to": None,
            "why": f"{FORMATS[best['fmt']]['name']}: {why}.", "tip": "", "source": "rules"}


def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024


def human_secs(s):
    if s < 60:
        return f"{s:.0f} s"
    if s < 3600:
        return f"{s / 60:.0f} min"
    return f"{s / 3600:.1f} h"
