"""File scanner: walks your folders and classifies every file by the 5S principle.

Seiri    (Sort)          - not used for a long time, duplicates
Seiton   (Set in order)  - lives in the wrong place (Downloads, loose on Desktop, media in Documents)
Seiso    (Shine)         - temp files, old installers, empty files/folders, broken shortcuts
Seiketsu (Standardize)   - messy names: "(1)", "copy", "final v2", "untitled"
Shitsuke (Sustain)       - recently used and without issues; folders that stay clean
"""
import hashlib
import json
import os
import re
import threading
import time
import winreg
from collections import defaultdict

from . import db, winshell
from . import folders as places  # "folders" is also the name of the folder-map table and its dict below

KNOWN_FOLDERS = [
    ("Desktop", "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}", "Desktop"),
    ("Documents", "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}", "Documents"),
    ("Downloads", "{374DE290-123F-4565-9164-39C4925E467B}", "Downloads"),
    ("Pictures", "{33E28130-4E1E-4676-835A-98395C3BC3BB}", "Pictures"),
    ("Videos", "{18989B1D-99B5-455E-841C-AB7C74E4DDFC}", "Videos"),
    ("Music", "{4BD8D571-6D19-48D3-BE97-422220080E43}", "Music"),
]

CATEGORIES = {
    "image": "jpg jpeg png gif bmp webp heic heif tif tiff raw cr2 nef arw dng svg ico psd avif",
    "video": "mp4 mov avi mkv wmv m4v webm flv 3gp mts m2ts mpg mpeg",
    "audio": "mp3 wav flac aac ogg m4a wma opus aiff",
    "pdf": "pdf",
    "document": "doc docx odt rtf pages",
    "spreadsheet": "xls xlsx xlsm ods csv numbers",
    "presentation": "ppt pptx odp key",
    "text": "txt md log json xml yaml yml ini cfg",
    "archive": "zip rar 7z tar gz bz2 xz iso img cab",
    "installer": "exe msi msix msixbundle appx appxbundle",
    "code": "py js ts html css java c cpp h cs go rs php rb sh ps1 bat ipynb sql",
    "shortcut": "lnk url",
}
EXT_CATEGORY = {e: cat for cat, exts in CATEGORIES.items() for e in exts.split()}

TEMP_EXT = {".tmp", ".temp", ".crdownload", ".part", ".partial", ".download", ".bak", ".old", ".dmp", ".~tmp"}
SKIP_DIRS = {"node_modules", "__pycache__", "$recycle.bin", "appdata", ".git", ".venv", "venv", "site-packages",
             "system volume information", ".cache", ".idea", ".vs"}

NAME_RULES = [
    (re.compile(r"\s\(\d+\)$"), "Copy-style name like “(1)”"),
    (re.compile(r"(?i)(^|[\s_-])(copy|kopie|kópia|kopia|kopija|kopya)($|[\s_-])"), "“Copy” in the name"),
    (re.compile(r"(?i)(^|[\s_-])(final|finál|finalni|finální|finálna|finalna)($|[\s_-])"),
     "“final” versions tend to multiply"),
    (re.compile(r"(?i)(^|[\s_-])v\d{1,2}($|[\s_-])"), "Version number in the file name"),
    (re.compile(r"(?i)^(new|nový|nova|novy|nová|untitled|bez názvu|unnamed|document|dokument|image|obrázok|"
                r"obrázek|noname|file|soubor|súbor)([\s_\d-]|$)"), "Generic name"),
    (re.compile(r"(?i)^[0-9a-f-]{24,}$"), "Random-looking name"),
]
STRIP_RULES = [r"\s\(\d+\)$", r"(?i)\s*-?\s*(copy|kopie|kópia|kopia|kopija)\b", r"(?i)\b(final|finál\w*)\b",
               r"(?i)(^|[\s_-])v\d{1,2}(?=$|[\s_-])"]
STD_CATEGORIES = {"pdf", "document", "spreadsheet", "presentation", "text", "archive"}
# Photos only get the obvious copy-style rules - camera names like IMG_1234 are a standard of their own.
STD_IMAGE_RULES = 2

# Folders that programs own (game saves, AI models, caches...). Kaizen never suggests touching them.
APP_DIR_RE = re.compile(
    r"(?i)^(my games|saved games|paradox interactive|rockstar games|electronic arts|ea games|ubisoft|klei|"
    r"cd projekt red|bethesda.*|steam|epic games|battle\.net|riot games|flm|lm ?studio|\.lmstudio|huggingface|"
    r"ollama|zoom|obs-studio|discord|visual studio( \d+)?|github|outlook files|custom office templates|"
    r"onenote notebooks|fiddler2|wondershare.*|adobe|autodesk|unity|unreal projects|virtual machines|"
    r"virtualbox vms|powershell|windowspowershell|wsl|.*cache.*|crashdumps|shadercache)$")
APP_MARKER_DIRS = {"save", "saves", "savegames", "savegame", "saved", "savedata", "profiles", "mods", "logs",
                   "crashdumps", "shadercache", "cache", "replays", "config", "settings", "userdata"}
APP_EXT = {".sav", ".save", ".cfg", ".ini", ".dat", ".db", ".log", ".json", ".xml", ".bin", ".profile", ".pak",
           ".cache", ".ck3", ".hoi4", ".eu4", ".v3", ".vdf", ".lua", ".journal", ".ldb", ".sqlite", ""}
PROJECT_MARKERS = {".git", "package.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml", "build.gradle",
                   "cmakelists.txt", "requirements.txt"}

TARGETS = {
    "pdf": ("Documents", "PDF"), "document": ("Documents", "Docs"), "spreadsheet": ("Documents", "Sheets"),
    "presentation": ("Documents", "Slides"), "text": ("Documents", "Notes"), "archive": ("Documents", "Archives"),
    "code": ("Documents", "Code"), "image": ("Pictures", "{year}"), "video": ("Videos", "{year}"),
    "audio": ("Music", ""), "other": ("Documents", "Other"),
}

DAY = 86400


def ago(seconds):
    days = seconds / DAY
    if days < 1:
        return "today"
    if days < 14:
        return f"{int(days)} days"
    if days < 60:
        return f"{int(days / 7)} weeks"
    if days < 730:
        return f"{int(days / 30.4)} months"
    return f"{days / 365:.0f} years"


def atime_trusted():
    """Windows only records 'last opened' when NtfsDisableLastAccessUpdate allows it."""
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            value = winreg.QueryValueEx(k, "NtfsDisableLastAccessUpdate")[0]
        return not (value & 1)
    except OSError:
        return False


def resolve_roots(settings):
    roots, seen = [], set()
    home = os.path.expanduser("~")
    for name, gid, fallback in KNOWN_FOLDERS:
        if name in settings.get("skip_roots", []):
            continue
        path = winshell.known_folder(gid) or os.path.join(home, fallback)
        if os.path.isdir(path):
            roots.append((name, path))
    for p in settings.get("extra_roots", []):
        if reachable(p):   # a dead network share must not hang the whole scan
            roots.append((extra_name(p), p))
    # Drop roots nested inside another root (e.g. Desktop inside OneDrive Documents).
    out = []
    for name, path in sorted(roots, key=lambda r: len(r[1])):
        key = os.path.normcase(os.path.abspath(path))
        if any(key == s or key.startswith(s + os.sep) for s in seen):
            continue
        seen.add(key)
        out.append((name, path))
    return out


def extra_name(path):
    """'Documents (\\\\NAS\\homes)' or 'Projects (D:)' - never the bare name of a Windows library, because the 5S
    rules treat 'Documents', 'Downloads' and 'Desktop' specially."""
    p = path.rstrip("\\/")
    base = os.path.basename(p)
    if p.startswith("\\\\"):
        parts = p.split("\\")
        where = "\\\\" + "\\".join(parts[2:4])
        return f"{base} ({where})" if len(parts) > 4 else where
    drive = os.path.splitdrive(p)[0]
    return f"{base} ({drive})" if base else f"Drive {drive}"


def reachable(path, timeout=8):
    box = []
    t = threading.Thread(target=lambda: box.append(os.path.isdir(path)), daemon=True)
    t.start()
    t.join(timeout)
    return bool(box and box[0])


def library_paths(settings):
    home = os.path.expanduser("~")
    out = {}
    for name, gid, fallback in KNOWN_FOLDERS:
        out[name] = winshell.known_folder(gid) or os.path.join(home, fallback)
    return out


def app_owned(path):
    """Does a top-level Documents folder belong to a program (game saves, settings, models)?"""
    name = os.path.basename(path)
    if APP_DIR_RE.match(name):
        return "Managed by an app"
    app_files = user_files = 0
    for dirpath, dirnames, filenames in os.walk(path):
        depth = dirpath[len(path):].count(os.sep)
        if any(d.lower() in APP_MARKER_DIRS for d in dirnames):
            return "Game or app data"
        if depth >= 2:
            dirnames[:] = []
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in APP_EXT or EXT_CATEGORY.get(ext.lstrip(".")) in (None, "code"):
                app_files += 1
            else:
                user_files += 1
        if app_files + user_files > 400:
            break
    if app_files >= 5 and app_files >= 0.7 * (app_files + user_files):
        return "Game or app data"
    return None


def suggest_name(stem, ext, mtime):
    clean = stem
    for pattern in STRIP_RULES:
        clean = re.sub(pattern, " ", clean)
    clean = re.sub(r"[\s_]+", " ", clean).strip(" -_")
    generic = not clean or NAME_RULES[4][0].match(clean) or NAME_RULES[5][0].match(clean)
    date = time.strftime("%Y-%m-%d", time.localtime(mtime))
    if generic:
        clean = "Untitled"
    if not re.match(r"^\d{4}-\d{2}-\d{2}", clean):
        clean = f"{date} {clean}"
    return clean + ext


class Progress(dict):
    def set(self, **kw):
        self.update(kw)

    def check_cancel(self):
        if self.get("cancel"):
            raise ScanCancelled()


class ScanCancelled(Exception):
    """The person pressed Stop. Nothing has been written yet, so the previous results stay."""


def _hash(path, size, full):
    h = hashlib.blake2b(digest_size=16)
    with winshell.preserve_atime(path):
        with open(path, "rb") as f:
            if full:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            else:
                h.update(f.read(65536))
                if size > 131072:
                    f.seek(-65536, os.SEEK_END)
                    h.update(f.read(65536))
    return h.hexdigest()


def scan_files(settings, progress):
    now = time.time()
    trust_atime = atime_trusted()
    progress.set(phase="Checking folders")
    roots = resolve_roots(settings)
    found = {os.path.normcase(p) for _, p in roots}
    skipped = [p for p in settings.get("extra_roots", []) if os.path.normcase(p) not in found
               and not any(os.path.normcase(p).startswith(f + os.sep) for f in found)]
    libs = library_paths(settings)
    kept = {r["path"] for r in db.rows("SELECT path FROM kept")}
    stale_days = settings["stale_days"]
    files, empty_dirs = [], []
    progress.set(phase="Walking folders", files=0, bytes=0, roots=[p for _, p in roots], skipped=skipped)

    for root_name, root in roots:
        remote = 1 if places.no_recycle_bin(root) else 0
        progress.set(current=root)
        stack = [(root, None)]
        while stack:
            d, managed = stack.pop()
            progress.check_cancel()
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            if not entries and d != root and not managed:
                empty_dirs.append((d, root, root_name))
            if not managed and d != root and any(e.name.lower() in PROJECT_MARKERS or e.name.lower().endswith(".sln")
                                                 for e in entries):
                managed = "Code project"
            for e in entries:
                try:
                    st = e.stat(follow_symlinks=False)
                    is_dir = e.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                attrs = getattr(st, "st_file_attributes", 0)
                if is_dir:
                    if e.is_symlink() or e.is_junction():
                        continue
                    if e.name.lower() in SKIP_DIRS or e.name.startswith(".") or (attrs & winshell.ATTR_SYSTEM):
                        continue
                    child_managed = managed
                    if not child_managed and d == root:
                        if APP_DIR_RE.match(e.name):
                            child_managed = "Managed by an app"
                        elif root_name == "Documents":
                            progress.set(current=e.path)
                            child_managed = app_owned(e.path)
                    stack.append((e.path, child_managed))
                    continue
                low = e.name.lower()
                if low in ("desktop.ini",) or (attrs & winshell.ATTR_HIDDEN and attrs & winshell.ATTR_SYSTEM):
                    continue
                stem, ext = os.path.splitext(e.name)
                ext = ext.lower()
                atime = st.st_atime if trust_atime else 0
                files.append({
                    "path": e.path, "name": e.name, "stem": stem, "ext": ext, "dir": d, "root": root,
                    "root_name": root_name, "category": EXT_CATEGORY.get(ext.lstrip("."), "other"),
                    "size": st.st_size, "mtime": st.st_mtime, "atime": atime, "ctime": st.st_ctime,
                    "last_used": max(st.st_mtime, atime, st.st_ctime),
                    "cloud": 1 if attrs & winshell.CLOUD_ATTRS else 0, "remote": remote, "reasons": [],
                    "i_sort": 0, "i_order": 0, "i_shine": 0, "i_std": 0, "sustained": 0,
                    "target": None, "new_name": None, "dup_group": None, "managed": managed,
                })
                progress["files"] += 1
                progress["bytes"] += st.st_size
                if progress["files"] % 500 == 0:
                    progress.set(current=d)

    # ---- duplicates (Seiri) ----
    progress.set(phase="Looking for duplicates", current="")
    by_size = defaultdict(list)
    for f in files:
        # network files aren't hashed: reading every same-size file over the network would make scans crawl
        if f["size"] >= 131072 and not f["cloud"] and not f["remote"] and not f["managed"] and \
                f["category"] not in ("shortcut",):
            by_size[f["size"]].append(f)
    groups = []
    for size, same in by_size.items():
        if len(same) < 2:
            continue
        partial = defaultdict(list)
        progress.check_cancel()
        for f in same:
            try:
                partial[_hash(f["path"], size, False)].append(f)
            except OSError:
                pass
        for h, cand in partial.items():
            if len(cand) < 2:
                continue
            # always the whole file: disk images and recordings often share their first and last 64 KB, and a
            # wrong "duplicate" of a big file is exactly the one the Recycle Bin may not be able to take
            full = defaultdict(list)
            for f in cand:
                try:
                    progress.check_cancel()
                    if size > 512 * 1024 * 1024:
                        progress.set(current=f"Comparing {f['name']} ({size // 2 ** 20:,} MB)")
                    full[_hash(f["path"], size, True)].append(f)
                except OSError:
                    pass
            groups += [(k, g) for k, g in full.items() if len(g) > 1]
    for h, group in groups:
        # keep the copy that lives in a library folder and was used most recently
        group.sort(key=lambda f: (f["root_name"] in ("Pictures", "Videos", "Music", "Documents"), f["last_used"]),
                   reverse=True)
        keeper = group[0]
        for f in group:
            f["dup_group"] = h
        for f in group[1:]:
            f["i_sort"] = 1
            if os.path.normcase(f["dir"]) == os.path.normcase(keeper["dir"]):
                where = "the same folder"
            else:
                parts = keeper["dir"].split("\\")
                where = "\\".join(parts[-2:]) if len(parts) > 2 else keeper["dir"]
            f["reasons"].append({"s": "sort", "t": f"Duplicate of “{keeper['name']}” in {where}"})

    # ---- per-file rules ----
    progress.set(phase="Applying the 5S rules")
    for f in files:
        if f["managed"]:
            continue
        if f["path"] in kept:
            f["i_sort"] = 0
            f["reasons"] = []
            f["sustained"] = 1
            continue
        age = now - f["last_used"]
        arrived = now - max(f["ctime"], f["mtime"])
        cat, rn = f["category"], f["root_name"]
        media_lib = settings["protect_media"] and cat in ("image", "video", "audio") and \
            rn in ("Pictures", "Videos", "Music")

        # Seiri - Sort
        if age > stale_days * DAY and not media_lib:
            f["i_sort"] = 1
            f["reasons"].append({"s": "sort", "t": f"Not opened for {ago(age)}"})

        # Seiso - Shine
        low = f["name"].lower()
        if f["ext"] in TEMP_EXT or low.startswith("~$") or low in ("thumbs.db", ".ds_store"):
            f["i_shine"] = 1
            f["reasons"].append({"s": "shine", "t": "Temporary or leftover file"})
        elif cat == "installer" and rn in ("Downloads", "Desktop") and arrived > 30 * DAY:
            f["i_shine"] = 1
            f["reasons"].append({"s": "shine", "t": "Old installer, you can download it again if needed"})
        elif f["size"] == 0 and not f["cloud"]:
            f["i_shine"] = 1
            f["reasons"].append({"s": "shine", "t": "Empty file (0 bytes)"})
        elif f["ext"] == ".lnk":
            target = winshell.lnk_target(f["path"])
            if target and len(target) > 3 and target[1:3] == ":\\" and os.path.exists(target[:3]) \
                    and not os.path.exists(target):
                f["i_shine"] = 1
                f["reasons"].append({"s": "shine", "t": "Shortcut points to a file that no longer exists"})

        # Seiton - Set in order
        if not f["i_shine"] and cat not in ("shortcut",):
            where = None
            if rn == "Downloads" and arrived > settings["downloads_days"] * DAY:
                where = f"Sitting in Downloads for {ago(arrived)}"
            elif rn == "Desktop" and os.path.normcase(f["dir"]) == os.path.normcase(f["root"]):
                where = "Loose file on the Desktop"
            elif rn == "Documents" and cat in ("image", "video", "audio"):
                where = "Media file stored in Documents"
            if where:
                lib, sub = TARGETS.get(cat, TARGETS["other"])
                sub = sub.replace("{year}", time.strftime("%Y", time.localtime(f["mtime"])))
                target = os.path.join(libs.get(lib) or os.path.expanduser("~\\" + lib), sub) if sub \
                    else libs.get(lib)
                if target and os.path.normcase(target) != os.path.normcase(f["dir"]):
                    f["i_order"] = 1
                    f["target"] = target
                    f["reasons"].append({"s": "order", "t": f"{where} → {lib}{chr(92) + sub if sub else ''}"})

        # Seiketsu - Standardize
        if cat in STD_CATEGORIES or cat == "image":
            for rule, why in (NAME_RULES if cat != "image" else NAME_RULES[:STD_IMAGE_RULES]):
                if rule.search(f["stem"]):
                    f["i_std"] = 1
                    f["new_name"] = suggest_name(f["stem"], f["ext"], f["mtime"])
                    f["reasons"].append({"s": "std", "t": why})
                    break

        # Shitsuke - Sustain
        if not (f["i_sort"] or f["i_order"] or f["i_shine"] or f["i_std"]) and age <= 90 * DAY:
            f["sustained"] = 1

    for d, root, rn in empty_dirs:
        if d in kept:
            continue
        files.append({
            "path": d, "name": os.path.basename(d), "stem": os.path.basename(d), "ext": "", "dir": os.path.dirname(d),
            "root": root, "root_name": rn, "category": "folder", "size": 0, "mtime": 0, "atime": 0, "ctime": 0,
            "last_used": 0, "cloud": 0, "i_sort": 0, "i_order": 0, "i_shine": 1, "i_std": 0, "sustained": 0,
            "reasons": [{"s": "shine", "t": "Empty folder"}], "target": None, "new_name": None, "dup_group": None,
            "managed": None, "remote": 1 if places.no_recycle_bin(root) else 0,
        })
        try:
            f = files[-1]
            st = os.stat(d)
            f["mtime"], f["ctime"], f["last_used"] = st.st_mtime, st.st_ctime, max(st.st_mtime, st.st_ctime)
        except OSError:
            pass

    # ---- folder aggregation for the map ----
    progress.set(phase="Building the folder map")
    folders = {}
    for f in files:
        d = f["dir"]
        root = f["root"]
        child = None
        while True:
            agg = folders.get(d)
            if agg is None:
                parent = os.path.dirname(d) if os.path.normcase(d) != os.path.normcase(root) else ""
                agg = folders[d] = {"path": d, "parent": parent, "name": os.path.basename(d) or d,
                                    "root_name": f["root_name"], "bytes": 0, "files": 0, "subdirs": set(),
                                    "last_used": 0, "sort_bytes": 0, "sort_n": 0, "order_n": 0, "shine_n": 0,
                                    "std_n": 0, "managed_n": 0, "managed_bytes": 0}
            if child:
                agg["subdirs"].add(child)
            agg["bytes"] += f["size"]
            agg["files"] += 1
            agg["last_used"] = max(agg["last_used"], f["last_used"])
            if f["i_sort"]:
                agg["sort_bytes"] += f["size"]
                agg["sort_n"] += 1
            agg["order_n"] += f["i_order"]
            agg["shine_n"] += f["i_shine"]
            agg["std_n"] += f["i_std"]
            if f["managed"]:
                agg["managed_n"] += 1
                agg["managed_bytes"] += f["size"]
            if os.path.normcase(d) == os.path.normcase(root) or os.path.dirname(d) == d:
                break
            child, d = d, os.path.dirname(d)
    for agg in folders.values():
        agg["subdirs"] = len(agg["subdirs"])
        n = max(agg["files"] - agg["managed_n"], 1)
        shares = {
            "sort": 0.5 * (agg["sort_n"] / n + agg["sort_bytes"] / max(agg["bytes"], 1)),
            "order": agg["order_n"] / n, "shine": agg["shine_n"] / n, "std": agg["std_n"] / n,
        }
        need = max(shares, key=shares.get)
        agg["severity"] = round(shares[need], 3)
        agg["need"] = need if shares[need] >= 0.08 else "sustain"
        if agg["managed_n"] >= 0.9 * agg["files"] and agg["parent"]:
            agg["need"], agg["severity"] = "app", 0

    # ---- write ----
    progress.set(phase="Saving results")
    c = db.conn()
    with c:
        c.execute("DELETE FROM files")
        c.executemany(
            "INSERT OR REPLACE INTO files(path,name,ext,dir,root,root_name,category,size,mtime,atime,ctime,last_used,"
            "cloud,i_sort,i_order,i_shine,i_std,sustained,reasons,target,new_name,dup_group,managed,remote) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(f["path"], f["name"], f["ext"], f["dir"], f["root"], f["root_name"], f["category"], f["size"],
              f["mtime"], f["atime"], f["ctime"], f["last_used"], f["cloud"], f["i_sort"], f["i_order"],
              f["i_shine"], f["i_std"], f["sustained"], json.dumps(f["reasons"], ensure_ascii=False), f["target"],
              f["new_name"], f["dup_group"], f["managed"], f["remote"]) for f in files])
        c.execute("DELETE FROM folders")
        c.executemany(
            "INSERT INTO folders(path,parent,name,root_name,bytes,files,subdirs,last_used,sort_bytes,sort_n,order_n,"
            "shine_n,std_n,managed_n,need,severity,managed_bytes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(a["path"], a["parent"], a["name"], a["root_name"], a["bytes"], a["files"], a["subdirs"],
              a["last_used"], a["sort_bytes"], a["sort_n"], a["order_n"], a["shine_n"], a["std_n"],
              a["managed_n"], a["need"], a["severity"], a["managed_bytes"]) for a in folders.values()])
    return {"files": len(files), "roots": roots, "trust_atime": trust_atime, "duplicates": len(groups),
            "skipped": skipped}


def scores():
    """Live 5S scores (recomputed after every keep/recycle so the rings react immediately)."""
    t = db.one("SELECT COUNT(*) n, COALESCE(SUM(size),0) b, SUM(i_sort) s, SUM(CASE WHEN i_sort THEN size END) sb, "
               "SUM(i_order) o, SUM(i_shine) sh, SUM(CASE WHEN i_shine THEN size END) shb, SUM(i_std) st, "
               "SUM(sustained) su, SUM(CASE WHEN category IN ('image','pdf','document','spreadsheet','presentation',"
               "'text','archive','image') THEN 1 END) std_n FROM files WHERE managed IS NULL")
    n = t["n"] or 0
    if not n:
        return None
    b = max(t["b"], 1)
    s_sort = 1 - 0.5 * ((t["s"] or 0) / n + (t["sb"] or 0) / b)
    s_order = 1 - (t["o"] or 0) / n
    s_shine = 1 - min(1.0, 3 * (t["sh"] or 0) / n)  # clutter is usually a small share, so weigh it more
    s_std = 1 - (t["st"] or 0) / max(t["std_n"] or 1, 1)
    top = db.one("SELECT COUNT(*) n, SUM(CASE WHEN need='sustain' THEN 1 END) ok FROM folders "
                 "WHERE files >= 3 AND need != 'app' AND (parent = '' OR parent IN (SELECT path FROM folders WHERE parent = ''))")
    healthy = (top["ok"] or 0) / max(top["n"] or 1, 1)
    recent = db.one("SELECT COUNT(*) n FROM scans WHERE ts > ?", (time.time() - 30 * DAY,))["n"]
    s_sustain = 0.7 * healthy + 0.3 * min(recent, 4) / 4
    vals = {"sort": s_sort, "order": s_order, "shine": s_shine, "std": s_std, "sustain": s_sustain}
    vals = {k: max(0.0, min(1.0, v)) for k, v in vals.items()}
    return {
        "scores": vals,
        "overall": sum(vals.values()) / 5,
        "counts": {"sort": t["s"] or 0, "order": t["o"] or 0, "shine": t["sh"] or 0, "std": t["st"] or 0,
                   "sustain": t["su"] or 0},
        "bytes": {"sort": t["sb"] or 0, "shine": t["shb"] or 0},
        "reclaim": (t["sb"] or 0) + (t["shb"] or 0),
        "files": n, "total_bytes": t["b"], "healthy_folders": healthy, "scans_30d": recent,
    }


def record_scan():
    s = scores()
    if not s:
        return
    c = db.conn()
    with c:
        c.execute("INSERT INTO scans(ts,files,bytes,s_sort,s_order,s_shine,s_std,s_sustain,overall,reclaim) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (time.time(), s["files"], s["total_bytes"], s["scores"]["sort"], s["scores"]["order"],
                   s["scores"]["shine"], s["scores"]["std"], s["scores"]["sustain"], s["overall"], s["reclaim"]))
