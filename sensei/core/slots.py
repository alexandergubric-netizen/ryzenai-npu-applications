"""Finds the concrete values in a request (folders, apps, file types, sizes, times, numbers...)
so a library template can be filled in without asking the AI.

extract("delete pdf files older than 30 days in downloads") ->
    residual "delete @ext file older than @days in @folder", values {ext: ..., days: 30, folder: ...}
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "knowledge", "entities.json"), encoding="utf-8") as _f:
    _E = json.load(_f)
APPS = _E["apps"]                      # alias -> {process, winget, launch, name}
SERVICES = _E["services"]              # phrase -> service name
TIMEZONES = _E["timezones"]            # phrase -> Windows time zone id
EXT_GROUPS = _E["ext_groups"]          # word -> [extensions]
FOLDERS = _E["folders"]                # word -> PowerShell path expression
SETTINGS_PAGES = _E["settings"]        # word -> ms-settings uri

NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
             "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
             "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90, "hundred": 100, "half an": 0.5, "half a": 0.5}
NUM = r"(\d+(?:[.,]\d+)?|" + "|".join(sorted((re.escape(k) for k in NUM_WORDS), key=len, reverse=True)) + r")"
EXTS = ("pdf|docx?|xlsx?|pptx?|odt|ods|txt|csv|json|xml|html?|md|log|ini|jpe?g|png|gif|bmp|webp|heic|tiff?|svg|ico|"
        "mp4|mkv|avi|mov|wmv|webm|m4v|mp3|wav|flac|m4a|aac|ogg|wma|zip|rar|7z|tar|gz|iso|exe|msi|ps1|py|js|ts|"
        "bat|cmd|dll|sys|tmp|bak|psd|epub|srt")
CLEAR_EXTS = ("pdf|docx|xlsx|pptx|jpe?g|png|gif|bmp|webp|heic|tiff|svg|mp4|mkv|avi|mov|wmv|webm|mp3|wav|flac|"
              "m4a|aac|ogg|msi|ps1|csv|json|txt|epub|psd|srt")
TLDS = "com|net|org|io|ai|dev|app|co|eu|info|gov|edu|sk|cz|de|uk|fr|it|es|pl|at|ch|nl|us|ca|me|tv|gg|ly"
PREP = r"(?:in|from|on|inside|under|of|within|at|to|into|onto)"


def _num(s):
    s = s.strip().lower().replace(",", ".")
    if s in NUM_WORDS:
        return NUM_WORDS[s]
    v = float(s)
    return int(v) if v.is_integer() else v


def _dq(s):
    """Escape a literal for use inside a double-quoted PowerShell string."""
    # PowerShell also treats the typographic quotes “ ” „ as double quotes
    return re.sub('([`"$“”„])', r"`\1", s)


class Found:
    def __init__(self, text):
        self.text = text
        self.low = text.lower()
        self.taken = [False] * len(text)
        self.items = []     # (start, type, value)

    def free(self, a, b):
        return not any(self.taken[a:b])

    def add(self, a, b, typ, value):
        for i in range(a, b):
            self.taken[i] = True
        self.items.append((a, typ, value))

    def scan(self, pattern, typ, conv, flags=re.I, group=0):
        for m in re.finditer(pattern, self.text, flags):
            a, b = m.span(group)
            if a < b and self.free(a, b):
                v = conv(m)
                if v is not None:
                    self.add(a, b, typ, v)


def _holiday(name):
    """The next date of a named day, as yyyy-mm-dd."""
    import datetime
    today = datetime.date.today()
    md = {"new year": (1, 1), "christmas": (12, 25), "xmas": (12, 25), "valentine": (2, 14), "halloween": (10, 31)}
    key = next((k for k in md if name.startswith(k)), None)
    if not key:
        return None
    m, d = md[key]
    if name.endswith("eve"):
        dt = datetime.date(today.year, m, d) - datetime.timedelta(days=1)
        if key == "new year":
            dt = datetime.date(today.year, 12, 31)
    else:
        dt = datetime.date(today.year, m, d)
    if dt < today:
        dt = dt.replace(year=dt.year + 1)
    return dt.isoformat()


def _folder_value(word):
    return {"expr": FOLDERS[word], "label": word if word in (".", "here") else word.title()}


def extract(text):
    """Returns (residual_text, values) where values maps slot type -> list of values in order."""
    f = Found(text)
    # --- unambiguous literals first
    f.scan(r"https?://[^\s\"']+", "url", lambda m: m.group(0))
    f.scan(r"(?<![\w])'([^']+)'(?![\w])|\"([^\"]+)\"|[“„]([^”“]+)[”“]", "text", lambda m: m.group(1) or m.group(2) or m.group(3))
    for m in re.finditer(r"(?<![\w])(?:[A-Za-z]:\\|\\\\)[^\s\"'<>|]*", text):     # full paths: a file if it has an extension
        p = m.group(0).rstrip(".,;")
        if f.free(m.start(), m.start() + len(p)):
            if re.search(r"\\[^\\]+\.\w{1,5}$", p):
                f.add(m.start(), m.start() + len(p), "file", p)
            else:
                f.add(m.start(), m.start() + len(p), "folder", {"expr": _dq(p.rstrip("\\") if len(p) > 3 else p), "label": p})
    f.scan(r"^\s*(?:please\s+)?(?:say|speak|read aloud|read out loud|read out|pronounce)\s+(.+?)\s*$", "text",
           lambda m: m.group(1), group=1)
    f.scan(r"\bremind me\b.*?\bto\s+(.+?)(?=\s+(?:in|at|after)\s+(?:\d|an?\b|half)|\s*$)", "text", lambda m: m.group(1), group=1)
    f.scan(r"\b([a-z][a-z0-9.\-]*:\d+(?:\.\d+)?[bm])\b", "model", lambda m: m.group(1))
    # times: 11 pm, 11:30, 23:00
    def time_conv(m):
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower().replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None
    f.scan(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", "time", time_conv)
    f.scan(r"\b(?:at\s+)?(\d{1,2}):(\d{2})()\b", "time", time_conv)
    f.scan(r"\b(\d{4}-\d{2}-\d{2})\b", "date", lambda m: m.group(1))
    f.scan(r"\b(new year(?:'s)?(?: day| eve)?|christmas(?: eve)?|xmas|valentine'?s(?: day)?|halloween|my birthday)\b", "date",
           lambda m: _holiday(m.group(1).lower()))
    f.scan(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b", "date", lambda m: f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}")
    # sizes, percentages, durations, ages
    units = {"k": "KB", "m": "MB", "g": "GB", "t": "TB"}
    f.scan(r"(?<![\w.])" + NUM + r"\s*(kb|mb|gb|tb|kilobytes?|megabytes?|megs?|gigabytes?|gigs?|terabytes?|teras?)\b", "size",
           lambda m: f"{_num(m.group(1))}{units[m.group(2)[0].lower()]}")
    f.scan(r"(?<![\w.])" + NUM + r"\s*(?:%|percent\b)", "percent", lambda m: int(_num(m.group(1))))

    def dur(m):
        n, u = _num(m.group(1)), m.group(2).lower()
        secs = n * (3600 if u.startswith("h") else 60 if u.startswith("m") else 1)
        return {"seconds": int(secs), "minutes": max(1, round(secs / 60)) if secs >= 60 else round(secs / 60, 2)}
    f.scan(r"(?<![\w.])" + NUM + r"\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", "duration", dur)

    def age(m):
        n, u = _num(m.group(1)), m.group(2).lower()
        return int(n * (365 if u.startswith("y") else 30 if u.startswith("mo") else 7 if u.startswith("w") else 1))
    f.scan(r"(?<![\w.])" + NUM + r"\s*(days?|weeks?|months?|years?)\b", "days", age)
    rel = {"today": 1, "yesterday": 2, "this week": 7, "last week": 14, "past week": 7, "this month": 31, "last month": 62,
           "past month": 31, "this year": 366, "last year": 731}
    f.scan(r"\b(today|yesterday|(?:this|last|past) (?:week|month|year))\b", "days", lambda m: rel[m.group(1).lower()])
    f.scan(r"\bport\s+(?:number\s+)?(\d{1,5})\b", "port", lambda m: int(m.group(1)), group=0)
    # file names (report.docx), host names (google.com)
    f.scan(r"(?<![\w\\/.])([\w\-()]+\.(?:" + EXTS + r"))\b", "file", lambda m: m.group(1))
    f.scan(r"\b((?:[a-z0-9\-]+\.)+(?:" + TLDS + r"))\b", "host", lambda m: m.group(1))
    # drive letters: drive E, E drive, E:
    f.scan(r"\b(?:drive|disk|usb|stick)\s+([a-z])\b(?!\.)|\b([a-z]):(?![\\/\w])|\b([a-z])\s+drive\b",
           "drive", lambda m: (m.group(1) or m.group(2) or m.group(3)).upper())
    f.scan(r"\b(?:on|in|from|of)\s+([a-z])(?=\s*$|\s*[?.!])", "drive", lambda m: m.group(1).upper(), group=1)
    # names: called X / named X
    f.scan(r"\b(?:called|named|name it|rename (?:it )?to)\s+([\w\-. ]+?)(?=\s+(?:on|in|to|at|from|inside|with)\b|[,.!?]?$)",
           "name", lambda m: m.group(1).strip(), group=0)
    # file types: "pdf files", ".mp4", "png"
    def ext_conv(m):
        e = m.group(1).lower().lstrip(".")
        twin = {"jpg": "jpeg", "jpeg": "jpg", "tif": "tiff", "tiff": "tif", "htm": "html", "html": "htm"}.get(e)
        return {"exts": [e] + ([twin] if twin else []), "raw": e}
    kinds = r"(?:files?|documents?|images?|pictures?|photos?|videos?|archives?|songs?|logs?)"
    f.scan(r"(?<![\w\\/])\.(" + EXTS + r")\b(?:\s+" + kinds + r")?", "ext", ext_conv)          # .pdf
    f.scan(r"(?<![\w\\/.])\b(" + EXTS + r")\s+" + kinds + r"\b", "ext", ext_conv)              # pdf files
    f.scan(r"(?<![\w\\/.])\b(" + CLEAR_EXTS + r")\b", "ext", ext_conv)                       # png, mp4 ...
    # folders: "in downloads", "documents folder", "desktop"
    folder_words = sorted(FOLDERS, key=len, reverse=True)
    fw = "|".join(re.escape(w) for w in folder_words)
    f.scan(r"\b" + PREP + r"\s+(?:my\s+|the\s+|this\s+|a\s+)?(" + fw + r")(?:\s+(?:folder|directory|dir))?\b", "folder",
           lambda m: _folder_value(m.group(1).lower()), group=0)
    f.scan(r"\b(?:my\s+|the\s+)?(" + fw + r")\s+(?:folder|directory|dir)\b", "folder",
           lambda m: _folder_value(m.group(1).lower()))
    # groups of file types: photos, videos, music, documents (when not a folder)
    gw = "|".join(sorted((re.escape(w) for w in EXT_GROUPS), key=len, reverse=True))
    f.scan(r"\b(" + gw + r")\b", "ext", lambda m: {"exts": EXT_GROUPS[m.group(1).lower()], "raw": m.group(1).lower()})
    # "files I downloaded" means the Downloads folder
    if not any(t == "folder" for _, t, _ in f.items):
        f.scan(r"\b(?:i\s+|i've\s+|have\s+)?downloaded\b", "folder", lambda m: {"expr": FOLDERS["downloads"], "label": "Downloads"})
    # remaining bare folder words (desktop, downloads...); "screenshots" alone means the files, not the folder
    bare = "|".join(re.escape(w) for w in folder_words if w not in ("screenshots", "onedrive"))
    f.scan(r"\b(" + bare + r")\b", "folder", lambda m: _folder_value(m.group(1).lower()))
    # settings pages: "sound settings", "settings for bluetooth"
    pw = "|".join(sorted((re.escape(w) for w in SETTINGS_PAGES), key=len, reverse=True))
    f.scan(r"\b(" + pw + r")\s+(?:settings|options|page)\b", "page", lambda m: SETTINGS_PAGES[m.group(1).lower()])
    f.scan(r"\bsettings\s+(?:for|of)\s+(?:the\s+)?(" + pw + r")\b", "page", lambda m: SETTINGS_PAGES[m.group(1).lower()])
    # apps, services, time zones
    for table, typ in ((SERVICES, "service"), (TIMEZONES, "tz"), (APPS, "app")):
        for alias in sorted(table, key=len, reverse=True):
            f.scan(r"(?<![\w\-])" + re.escape(alias) + r"(?![\w\-])", typ,
                   lambda m, a=alias, t=table, ty=typ: (dict(t[a], alias=a) if ty == "app" else t[a]))
    # an app the vocabulary does not know: "install obsidian"
    f.scan(r"^\s*(?:please\s+)?(?:open|launch|start|run|close|quit)\s+(?:the\s+)?(?:app\s+)?([a-z][\w.+\-]*(?:\s+[a-z][\w.+\-]*)?)\s*$",
           "pkg", lambda m: None if m.group(1).lower() in ("it", "this", "that", "everything", "all", "up", "a", "the") else m.group(1), group=1)
    f.scan(r"\b(?:install|uninstall|reinstall|update|upgrade)\s+([a-z][\w.+\-]*(?:\s+[a-z][\w.+\-]*)?)\s*$", "pkg",
           lambda m: None if m.group(1).lower() in ("all", "everything", "windows", "apps", "programs", "drivers", "all apps",
                                                     "all programs", "my apps", "my programs") else m.group(1), group=1)
    # bare numbers last
    f.scan(r"(?<![\w.])(\d+(?:[.,]\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|"
           r"thirty|forty|fifty|hundred)(?![\w.])", "n", lambda m: _num(m.group(1)))

    values = {}
    out, last = [], 0
    for a, typ, v in sorted(f.items, key=lambda x: x[0]):
        values.setdefault(typ, []).append(v)
    # residual: replace each found span with " @type "
    spans = sorted(((a, typ) for a, typ, _ in f.items), key=lambda x: x[0])
    i = 0
    while i < len(text):
        hit = next((s for s in spans if s[0] == i), None)
        if hit:
            j = i
            while j < len(text) and f.taken[j]:
                j += 1
            out.append(f" @{hit[1]} ")
            i = j
            continue
        out.append(text[i] if not f.taken[i] else " ")
        i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip(), values


# ------------------------------------------------------------------ filling a template
SLOT_TYPES = {
    "folder": "folder", "src": "folder", "dest": "folder", "file": "file", "ext": "ext", "ext2": "ext",
    "n": "n", "percent": "percent", "port": "port", "size": "size", "days": "days", "seconds": "duration",
    "minutes": "duration", "time": "time", "date": "date", "text": "text", "name": "name", "url": "url",
    "host": "host", "app": "app", "page": "page", "file2": "file", "pkg": "pkg", "path": "folder", "service": "service", "tz": "tz", "drive": "drive", "path": "path",
    "model": "model",
}
SLOT_RE = re.compile(r"\{\{(\w+)(?:\|(\w+))?\}\}")


def slot_values(slots_in_template, values, query):
    """Assign extracted values to the template's slots. Returns {slot: value or None}."""
    pools = {k: list(v) for k, v in values.items()}
    # an explicit path counts as a folder (or a file if it has an extension)
    for p in pools.pop("path", []):
        if re.search(r"\.\w{1,5}$", p):
            pools.setdefault("file", []).insert(0, p)
        else:
            pools.setdefault("folder", []).insert(0, {"expr": _dq(p), "label": p})
    # a full path given as the file: split it into folder + file name when the template has both
    if "folder" in slots_in_template and "file" in slots_in_template:
        for k, fv in enumerate(pools.get("file", [])):
            if re.match(r"^(?:[A-Za-z]:\\|\\\\)", fv):
                pools["file"][k] = fv.rsplit("\\", 1)[1]
                pools.setdefault("folder", []).insert(0, {"expr": _dq(fv.rsplit("\\", 1)[0] or fv[:3]), "label": fv.rsplit("\\", 1)[0]})
    # a drive used as folder
    wants_folder = any(SLOT_TYPES.get(s) == "folder" for s in slots_in_template)
    for d in pools.get("drive", []) if wants_folder and "drive" not in slots_in_template else []:
        pools.setdefault("folder", []).append({"expr": f"{d}:\\", "label": f"{d}:"})
    # "copy my music to D:" - with no source folder named, photos/music/videos come from their own folder
    natural = {"music": "music", "songs": "music", "audio": "music", "photos": "pictures", "pictures": "pictures",
               "images": "pictures", "videos": "videos", "movies": "videos"}
    if "src" in slots_in_template and pools.get("ext") and len(pools.get("folder", [])) <= 1:
        nat = natural.get(pools["ext"][0].get("raw", ""))
        named = [f["label"].lower() for f in pools.get("folder", [])]
        if nat and nat not in named:
            pools.setdefault("folder", []).insert(0, {"expr": FOLDERS[nat], "label": nat.title()})
    # source and destination: "from X to Y"
    low = query.lower()
    out = {}
    if "src" in slots_in_template or "dest" in slots_in_template:
        folders = pools.get("folder", [])
        dest = next((x for x in folders if re.search(r"\b(?:to|into|onto)\s+(?:my\s+|the\s+|a\s+)?" +
                                                     re.escape(x["label"].lower()), low)), None)
        src = next((x for x in folders if x is not dest), None)
        if dest is None and len(folders) >= 2:
            dest = folders[1]
        out["src"], out["dest"] = src, dest
    order = {}
    for s in slots_in_template:
        if s in out:
            continue
        typ = SLOT_TYPES.get(s, s)
        pool = pools.get(typ, [])
        idx = order.get(typ, 0)
        if s in ("ext2", "file2"):
            idx = max(idx, 1)
        if typ == "percent" and not pool:
            pool = pools.get("n", [])          # "volume 30" means 30 %
        if typ == "duration" and not pool and pools.get("n"):
            n = pools["n"][0]                   # "timer 5" means 5 minutes
            pool = [{"seconds": int(n * (1 if s == "seconds" else 60)), "minutes": n}]
        out[s] = pool[idx] if idx < len(pool) else None
        order[typ] = idx + 1
    return out


def _in_quote(template, pos):
    """Which quote the position is inside: None, "'" or '"'."""
    q = None
    i = 0
    while i < pos:
        c = template[i]
        if q is None and c in "'\"":
            q = c
        elif q == "'" and c == "'":
            q = None
        elif q == '"' and c == '"' and template[i - 1] != "`":
            q = None
        i += 1
    return q


def render(value, slot, mod, quote):
    """A slot value as PowerShell text for its place in the template."""
    typ = SLOT_TYPES.get(slot, slot)
    if typ == "folder":
        s = value["expr"]
    elif typ == "ext":
        if mod == "raw":
            s = value["raw"] if value["raw"] in EXT_GROUPS else value["exts"][0]
        else:
            s = ", ".join(f"*.{e}" for e in value["exts"]) if quote is None else f"*.{value['exts'][0]}"
    elif typ == "duration":
        s = str(value["seconds"] if slot == "seconds" else value["minutes"])
    elif typ == "app":
        s = value.get({"process": "process", "winget": "winget", "launch": "launch", "name": "name"}.get(mod or "", "process")) \
            or value.get("process")
    else:
        s = str(value)
    if quote == "'":
        # PowerShell also ends single-quoted strings at the typographic quotes ‘ ’ ‚ ‛ (pasted "Bob’s"): double them all
        return re.sub("(['‘’‚‛])", r"\1\1", s)
    if quote == '"' and typ not in ("folder",):
        return _dq(s)
    return s


def fill(template, values, query, defaults):
    """Fill {{slot}} / {{slot|mod}} in the command. Missing slots use defaults or become <slot> placeholders."""
    slots = list(dict.fromkeys(m.group(1) for m in SLOT_RE.finditer(template)))
    assigned = slot_values(slots, values, query)
    missing = []

    def sub(m):
        slot, mod = m.group(1), m.group(2)
        v = assigned.get(slot)
        if v is None:
            if slot in defaults:
                return defaults[slot]
            missing.append(slot)
            return f"<{slot}>"
        return render(v, slot, mod, _in_quote(template, m.start()))
    return SLOT_RE.sub(sub, template), missing, assigned


DEFAULT_LABELS = {"$HOME": "your user folder", ".": "the current folder", "": "the same folder",
                  "$HOME\\Downloads": "Downloads", "$env:TEMP": "your temp folder"}


def fill_text(note, assigned, defaults):
    """Fill {slot} in an explanation with readable values."""
    def sub(m):
        slot = m.group(1)
        v = assigned.get(slot)
        if v is None:
            d = defaults.get(slot, slot)
            return DEFAULT_LABELS.get(d) or next((w for w, e in FOLDERS.items() if e == d), None) or d.replace('"', "")
        typ = SLOT_TYPES.get(slot, slot)
        if typ == "folder":
            return v["label"]
        if typ == "ext":
            return v["raw"]
        if typ == "duration":
            return str(v["minutes"] if slot == "minutes" else v["seconds"])
        if typ == "app":
            return v.get("name") or v.get("alias")
        return str(v)
    return re.sub(r"\{(\w+)\}", sub, note)
