"""The tested command library: templates with slots, instant matching and BM25 search.

Library files (core/knowledge/*.txt), one block per task, blocks separated by a blank line:
    ? phrasings | separated by pipes | {slot} marks a value from the request
    the command, with {{slot}} or {{slot|mod}} where the value goes (may span lines)
    = explanation, may use {slot}
    & slot=default ; slot2=default      (optional; PowerShell text used when the request has no value)
    ! admin                              (optional; needs an elevated PowerShell)
"""
import difflib
import glob
import math
import os
import re
from collections import Counter

from . import slots

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.join(HERE, "knowledge")

# filler words. Question words like why/when/where/who, and not/no/only, are NOT filler: they change the meaning
STOP = set("""a an the i me my mine you your it its this that these those be am do does did
to of in at for from by with and or what which whom how can could should would will
please show tell give get list find all any some there here want need like just using use command powershell
pc computer way something every each now currently right hey pls plz let lets really also
sure into onto inside within out about via called named don whats thats hows wats teh hte adn waht thw pleas plese
got bit little""".split())
NEGATIONS = {"never", "not", "no", "without", "stop", "cancel", "undo", "off", "on", "un", "except"}
SOFT = {"is"}   # may be left out of a match, but only for tasks that just read information
# verbs that change something: a phrasing may not add one the request does not contain
ACTIONS = {"copy", "move", "delete", "create", "rename", "zip", "unzip", "install", "uninstall", "stop", "close",
           "restart", "shut", "set", "change", "add", "write", "empty", "format", "eject", "convert", "resize",
           "download", "sync", "mirror", "block", "clear", "flush", "reset", "kill", "update", "disable", "enable",
           "lock", "sleep", "hibernate", "mute", "unmute", "start", "run", "open", "replace", "merge", "share", "map",
           "disconnect", "connect", "forget", "pull", "print", "scan", "repair", "optimize", "speak", "say"}

SYNONYMS = {
    "biggest": "largest", "big": "large", "huge": "large", "bigger": "larger", "greater": "larger", "over": "larger",
    "above": "larger", "tiny": "small", "less": "smaller", "under": "smaller", "below": "smaller",
    "directory": "folder", "directories": "folder", "dir": "folder", "folders": "folder", "subfolders": "subfolder",
    "erase": "delete", "remove": "delete", "rm": "delete", "del": "delete", "wipe": "delete", "trash": "delete",
    "kill": "stop", "end": "stop", "terminate": "stop", "quit": "close", "exit": "close",
    "app": "program", "apps": "program", "application": "program", "applications": "program", "software": "program",
    "programs": "program",
    "wifi": "wi-fi", "wireless": "wi-fi", "wlan": "wi-fi", "ssid": "wi-fi",
    "reboot": "restart", "boot": "start", "booted": "start", "startup": "start", "launch": "open", "run": "open",
    "ram": "memory", "mem": "memory", "cpu": "processor", "processes": "process", "task": "process", "tasks": "process",
    "hdd": "disk", "ssd": "disk", "drive": "disk", "drives": "disk", "storage": "disk", "disks": "disk",
    "ipv4": "ip", "internet": "network", "online": "network", "net": "network", "connection": "network",
    "antivirus": "defender", "virus": "defender", "viruses": "defender", "malware": "defender",
    "temp": "temporary", "tmp": "temporary", "junk": "temporary", "pwd": "password", "passwords": "password",
    "updates": "update", "upgrade": "update", "updated": "update", "upgrades": "update",
    "files": "file", "document": "file", "doc": "file",
    "extract": "unzip", "decompress": "unzip", "compress": "zip", "archive": "zip",
    "ports": "port", "listening": "listen",
    "admin": "administrator", "elevated": "administrator", "administrators": "administrator",
    "pid": "id", "renaming": "rename",
    "gpu": "graphics", "monitor": "display", "screen": "display", "monitors": "display",
    "charge": "battery", "logs": "log", "events": "event", "crashed": "crash", "crashes": "crash", "bsod": "crash",
    "enable": "on", "activate": "on", "disable": "off", "deactivate": "off",
    "using": "use", "used": "use", "uses": "use", "utilization": "use", "usage": "use",
    "latest": "newest", "recent": "newest", "recently": "newest",
    "modified": "changed", "edited": "changed",
    "sound": "volume", "audio": "volume", "loudness": "volume", "louder": "up", "quieter": "down", "increase": "up",
    "decrease": "down", "raise": "up", "lower": "down", "boost": "up", "crank": "up",
    "dim": "down", "dimmer": "down", "darker": "down", "brighter": "up", "make": "create", "are": "is", "was": "is", "were": "is",
    "screengrab": "screenshot", "capture": "screenshot", "printscreen": "screenshot",
    "shutdown": "shut", "poweroff": "shut",
    "duplicates": "duplicate", "identical": "duplicate",
    "backup": "copy",
    "picture": "image", "pictures": "image", "photo": "image", "photos": "image", "images": "image",
    "speak": "say", "aloud": "say", "loud": "say", "tts": "say",
    "alarm": "timer", "countdown": "timer", "reminder": "timer", "remind": "timer",
    "unplug": "eject", "safely": "eject",
    "opened": "opened", "accessed": "opened",
    "transfer": "move", "relocate": "move",
}


def _stem(w):
    """A small, consistent stemmer: files->file, processes->process, copies->copy, running->runn, changed->chang."""
    if w.startswith("@") or len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "shes", "ches", "xes", "zes")):
        return w[:-2]
    if w.endswith(("ss", "us", "is", "ys")):
        return w
    if w.endswith("ing") and len(w) > 5:
        return w[:-3]
    if w.endswith("ed") and len(w) > 4:
        return w[:-2]
    if w.endswith("s"):
        return w[:-1]
    return w


def _norm_word(w):
    """Synonyms, then the stem, then synonyms of the stem (shutdowns -> shutdown -> shut)."""
    w = _stem(SYNONYMS.get(w, w))
    return SYNONYMS.get(w, w)


def tokens(text):
    out = []
    text = re.sub(r"[’']\s?(s|re|ll|ve|d|m|t)\b", " ", text.lower())    # what's -> what, don't -> don
    for w in re.findall(r"@\w+|[a-z0-9][a-z0-9\-\.+]*", text):
        w = w.strip(".-")
        if not w or w in STOP:
            continue
        if w.startswith("@"):
            out.append(w)
            continue
        out.append(_norm_word(w))
    return out


def _phrase_tokens(phrase):
    """Tokens of a library phrasing: {slot} becomes @type; literal values (photos, chrome) also become @type."""
    marked = re.sub(r"\{(\w+)\}", lambda m: f" @{slots.SLOT_TYPES.get(m.group(1), m.group(1))} ", phrase)
    residual, values = slots.extract(marked)
    return tokens(residual), values


# commands that change something; a task without any of these only reads information
ACTION_RE = re.compile(
    r"\b(?:Set|New|Remove|Stop|Start|Restart|Rename|Move|Copy|Clear|Install|Uninstall|Disable|Enable|Add|Register|"
    r"Unregister|Save|Convert|Resize|Close|Out-Speech|Dismount|Format|Compress|Expand|Update|Optimize|Repair|Unblock|"
    r"Export|Checkpoint|Invoke|Suspend|Resume|Mount|Block|Grant|Revoke|Reset)-|"
    r"\b(?:winget (?:install|uninstall|upgrade --all|upgrade --id|upgrade \")|shutdown(?:\.exe)? /|powercfg /(?:change|setactive|hibernate)|"
    r"netsh (?:wlan (?:connect|disconnect|delete)|winsock|int)|ffmpeg|rundll32|flm (?:pull|remove|run)|wsl --shutdown|"
    r"sfc|DISM|control\.exe|notepad|explorer\.exe|ipconfig /(?:release|renew|flushdns)|tree)\b|\.(?:MinimizeAll|UndoMinimizeALL|"
    r"CreateShortcut|SetSuspendState)|\.Attributes|PriorityClass|IsReadOnly|SenseiWatch", re.I)


def _fits(it, values, query):
    """Type constraints ("% file=images"): the value given for a slot must be of an allowed kind."""
    assigned = slots.slot_values(it["slots"], values, query)
    for slot, allowed in it["only"].items():
        v = assigned.get(slot)
        if v is None:
            continue
        if isinstance(v, dict) and "exts" in v:
            exts = set(v["exts"])
        else:
            exts = {str(v).rsplit(".", 1)[-1].lower()}
        if not exts & allowed:
            return False
    return True


def _norm(v):
    if isinstance(v, dict):
        return (v.get("raw") or v.get("label") or v.get("process") or "").lower()
    return str(v).lower()


class Library:
    def __init__(self, folder=KNOWLEDGE):
        self.items = []
        for path in sorted(glob.glob(os.path.join(folder, "*.txt"))):
            self._load(path)
        self._index()

    # ---------------------------------------------------------------- loading
    def _load(self, path):
        section, block = os.path.splitext(os.path.basename(path))[0], []
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines() + [""]
        for n, line in enumerate(lines, 1):
            if line.startswith("## "):
                section = line[3:].strip()
                continue
            if line.startswith("#") and not block:
                continue
            if line.strip():
                block.append(line)
                continue
            if block:
                self._add(block, section, f"{os.path.basename(path)}:{n - len(block)}")
                block = []

    def _add(self, block, section, source):
        q, cmd, note, admin, defaults, only = [], [], "", False, {}, {}
        for line in block:
            if line.startswith("? "):
                q += [p.strip() for p in line[2:].split("|") if p.strip()]
            elif line.startswith("= "):
                note = line[2:].strip()
            elif line.startswith("! "):
                admin = "admin" in line
            elif line.startswith("% "):
                for part in line[2:].split(" ; "):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        allowed = set()
                        for g in v.split(","):
                            g = g.strip().lower()
                            allowed |= set(slots.EXT_GROUPS.get(g, [g]))
                        only[k.strip()] = allowed
            elif line.startswith("& "):
                for part in line[2:].split(" ; "):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        defaults[k.strip()] = v.strip()
            else:
                cmd.append(line)
        if q and cmd:
            text = "\n".join(cmd)
            self.items.append({"q": q, "cmd": text, "note": note, "admin": admin, "defaults": defaults, "only": only,
                               "section": section, "source": source,
                               "slots": list(dict.fromkeys(m.group(1) for m in slots.SLOT_RE.finditer(text)))})

    def _index(self):
        self.docs = []
        self.phrases = []          # (item index, token list, literal values)
        for i, it in enumerate(self.items):
            it["types"] = {f"@{slots.SLOT_TYPES.get(s, s)}" for s in it["slots"]}
            words = []
            for p in it["q"]:
                toks, lit = _phrase_tokens(p)
                self.phrases.append((i, toks, lit))
                words += toks
            note_words = tokens(re.sub(r"\{\w+\}", "", it["note"]))
            it["readonly"] = not ACTION_RE.search(it["cmd"])
            it["vocab"] = {w for w in words + note_words if not w.startswith("@")}
            words = words * 2 + note_words + tokens(it["section"])
            self.docs.append(Counter(words))
        self.vocab = {w for d in self.docs for w in d if not w.startswith("@")}
        self._fixes = {}
        self._known = sorted(self.vocab | set(SYNONYMS))
        self._known = sorted(self.vocab | set(SYNONYMS))
        self.avg = sum(sum(d.values()) for d in self.docs) / max(len(self.docs), 1)
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def fix_typos(self, toks):
        """Replaces words the library has never seen with the closest known word (scrennshot -> screenshot)."""
        out = []
        for t in toks:
            if t.startswith("@") or t in self.vocab or len(t) < 3 or t.isdigit():
                out.append(t)
                continue
            if t not in self._fixes:
                m = difflib.get_close_matches(t, self._known, n=1, cutoff=0.8)
                self._fixes[t] = (m[0] if m[0] in self.vocab else _norm_word(m[0])) if m else t
            out.append(self._fixes[t])
        return out

    # ---------------------------------------------------------------- instant match
    def exact(self, query):
        """The best template whose phrasing covers every meaningful word of the query, filled in; or None."""
        residual, values = slots.extract(query)
        qset = set(self.fix_typos(tokens(residual)))
        if not qset:
            return None
        best, best_key = None, None
        for i, toks, lit in self.phrases:
            it = self.items[i]
            q = set(qset)
            # a bare number fills a percent or duration slot ("volume 30", "timer 5")
            if "@drive" in q and "@drive" not in it["types"] and "@folder" in it["types"]:
                q = (q - {"@drive"}) | {"@folder"}             # "to the D drive" is a folder
            if "@n" in q and "@n" not in it["types"]:
                for alt in ("@percent", "@duration"):
                    if alt in it["types"] and alt not in q:
                        q = (q - {"@n"}) | {alt}
                        break
            pset = set(toks)
            if not pset:
                continue
            missing = q - pset
            soft = missing & SOFT
            hard = missing - SOFT
            # at most one query word may be absent from this phrasing, and only a word this task uses elsewhere;
            # "is" may be absent only when the task just reads information ("is wifi on" must never switch it on)
            if len(hard) > 1 or any(w.startswith("@") or w not in it["vocab"] for w in hard):
                continue
            if soft and not it["readonly"]:
                continue
            extra = len(pset - q)
            if extra > 2:
                continue
            # a short request must match closely ("list all the apps" must not land on "startup apps settings")
            if (len(q) == 1 and extra > 1) or (len(q) == 2 and missing and extra > 1):
                continue
            # a word that flips the meaning must not be added by the phrasing ("never turn off the screen"), nor an
            # action the user never asked for ("list everything in X" must not become "copy everything from X")
            if (pset - q) & (NEGATIONS | ACTIONS):
                continue
            ok, specific = True, 0
            for t, vals in values.items():
                if f"@{t}" not in q:
                    continue
                if t in lit and _norm(vals[0]) == _norm(lit[t][0]):
                    specific += 1                 # the phrasing names this very value (temp, chrome, photos)
                    continue
                if f"@{t}" in it["types"] or (t == "drive" and "@folder" in it["types"]):
                    continue                      # a slot takes it
                ok = False
                break
            if not ok:
                continue
            if it["only"]:
                if not _fits(it, values, query):
                    continue
                specific += 1                     # its type rule matched (a .mp4 for the video recipe)
            key = (len(missing), extra, -specific, i)
            if best_key is None or key < best_key:
                best, best_key = i, key
        if best is None:
            return None
        hit = self.instantiate(self.items[best], query, values)
        # a loose match that still needs a value the user never gave is a guess: let the AI router decide
        if best_key[0] and hit["missing"]:
            return None
        return hit

    def instantiate(self, it, query, values=None):
        if values is None:
            _, values = slots.extract(query)
        code, missing, assigned = slots.fill(it["cmd"], values, query, it["defaults"])
        extra = [m for m in re.findall(r"\{(\w+)\}", it["note"]) if m not in assigned]
        if extra:
            assigned = dict(slots.slot_values(extra, values, query), **assigned)
        note = slots.fill_text(it["note"], assigned, it["defaults"])
        return dict(it, code=code, missing=missing, note_filled=note)

    # ---------------------------------------------------------------- search (references for the AI)
    def search(self, query, k=4, min_score=2.0):
        residual, values = slots.extract(query)
        q = self.fix_typos(tokens(residual))
        if not q:
            return []
        scored = []
        for it, d in zip(self.items, self.docs):
            length = sum(d.values())
            s = 0.0
            for t in set(q):
                f = d.get(t, 0)
                if f:
                    s += self.idf[t] * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * length / self.avg))
            if s >= min_score:
                scored.append((s, it))
        scored.sort(key=lambda x: -x[0])
        return [dict(self.instantiate(it, query, values), score=round(s, 2)) for s, it in scored[:k]]


library = Library()
