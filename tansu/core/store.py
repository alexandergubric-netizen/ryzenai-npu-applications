"""The archive library in Documents\\Archives: what is where, what is inside, and keeping it tidy.

Tansu's notes live next to the archives in a hidden Archives\\.tansu folder (index.json + cached content lists), so
they travel with the library. Archives moved or renamed in Explorer are re-linked by size + timestamp.
"""
import hashlib
import json
import os
import re
import threading
import time
import uuid

from . import config, engine
from .rules import clean_folder, clean_part

ARCH_EXT = (".zip", ".7z", ".tar.xz", ".txz", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar", ".tar.zst", ".rar")
_lock = threading.RLock()


def meta_dir():
    d = os.path.join(config.root(), ".tansu")
    if not os.path.isdir(d):
        os.makedirs(os.path.join(d, "lists"), exist_ok=True)
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(d, 0x2)  # hidden
        except OSError:
            pass
    os.makedirs(os.path.join(d, "lists"), exist_ok=True)
    return d


def _index_file():
    return os.path.join(meta_dir(), "index.json")


def load():
    try:
        with open(_index_file(), encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data.get("archives"), dict):
                return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "archives": {}}


def save(data):
    with _lock:
        tmp = _index_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, _index_file())


def rel_of(path):
    return os.path.relpath(path, config.root()).replace("\\", "/")


def abs_of(rel):
    root = config.root()
    p = os.path.normpath(os.path.join(root, rel))
    if not p.startswith(root.rstrip("\\") + "\\"):
        raise ValueError("outside the library")
    return p


def is_archive(name):
    n = name.lower()
    return n.endswith(ARCH_EXT) and not n.endswith(".part")


# ---------------------------------------------------------------- scanning the library
def scan_disk():
    """(folders, archives on disk, loose files) - folders and archives as library-relative paths."""
    root = config.root()
    folders, archives, loose = [], [], []
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x.lower() != ".tansu" and not x.startswith("$"))
        rel = os.path.relpath(d, root).replace("\\", "/")
        if rel != ".":
            folders.append(rel)
        for f in files:
            p = os.path.join(d, f)
            r = f if rel == "." else f"{rel}/{f}"
            if is_archive(f):
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                archives.append((r, st.st_size, st.st_mtime))
            elif f.lower() not in ("desktop.ini", "thumbs.db") and not f.endswith(".part"):
                loose.append(r)
    return folders, archives, loose


def reconcile():
    """Bring the index in line with the disk: re-link moved archives, add unknown ones, drop vanished ones."""
    with _lock:
        data = load()
        idx = data["archives"]
        folders, on_disk, loose = scan_disk()
        disk = {r: (s, m) for r, s, m in on_disk}
        orphans = {r: e for r, e in idx.items() if r not in disk}
        changed = False
        for r, (s, m) in disk.items():
            if r in idx:
                e = idx[r]
                if e.get("size") != s or abs(e.get("mtime", 0) - m) > 2:
                    e.update(size=s, mtime=m, listed=None)  # changed outside Tansu: list again
                    changed = True
                continue
            # moved/renamed in Explorer? same size and timestamp, or same file name elsewhere
            hit = next((o for o, e in orphans.items() if e.get("size") == s and abs(e.get("mtime", 0) - m) < 2), None)
            if hit:
                idx[r] = orphans.pop(hit)
                idx.pop(hit, None)
            else:
                idx[r] = {"id": uuid.uuid4().hex[:12], "fmt": engine.fmt_of(r), "created": m, "size": s,
                          "mtime": m, "by": "found", "files": None, "original": None, "encrypted": None}
            idx[r].update(size=s, mtime=m)
            changed = True
        for o in orphans:
            idx.pop(o, None)
            changed = True
        if changed:
            save(data)
        return data, folders, loose


def _list_path(aid):
    return os.path.join(meta_dir(), "lists", aid + ".json")


def contents(rel, password=None, refresh=False):
    """The archive's file list (cached; encrypted 7z lists are saved when Tansu creates them)."""
    data = load()
    e = data["archives"].get(rel)
    if not e:
        data, _, _ = reconcile()
        e = data["archives"].get(rel)
        if not e:
            raise ValueError("archive not found")
    lp = _list_path(e["id"])
    if not refresh and e.get("listed") and os.path.exists(lp):
        with open(lp, encoding="utf-8") as f:
            return e, json.load(f)
    path = abs_of(rel)
    try:
        items = engine.listing(path, password)
    except Exception as ex:
        if "password" in str(ex).lower() or type(ex).__name__ in ("PasswordRequired", "UnsupportedCompressionMethodError"):
            raise PermissionError("password needed")
        raise
    remember_listing(rel, items)
    return load()["archives"][rel], items


def remember_listing(rel, items, extra=None):
    with _lock:
        data = load()
        e = data["archives"].get(rel)
        if not e:
            return
        with open(_list_path(e["id"]), "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
        files = [i for i in items if not i["dir"]]
        e["files"] = len(files)
        e["original"] = sum(i["size"] for i in files) or e.get("original")
        e["listed"] = time.time()
        if extra:
            e.update(extra)
        save(data)


def record(path, meta, items):
    """A new archive made by Tansu."""
    rel = rel_of(path)
    st = os.stat(path)
    with _lock:
        data = load()
        old = data["archives"].get(rel, {})
        e = {"id": old.get("id") or uuid.uuid4().hex[:12], "created": old.get("created") or time.time(),
             "size": st.st_size, "mtime": st.st_mtime, "by": "tansu", **meta}
        if old.get("history"):
            e["history"] = old["history"]
        data["archives"][rel] = e
        save(data)
    remember_listing(rel, items)
    return rel


def overview():
    data, folders, loose = reconcile()
    arcs = []
    for rel, e in sorted(data["archives"].items(), key=lambda kv: -kv[1].get("created", 0)):
        folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
        arcs.append({"rel": rel, "name": rel.rsplit("/", 1)[-1], "folder": folder, "fmt": e.get("fmt"),
                     "size": e.get("size"), "original": e.get("original"), "files": e.get("files"),
                     "created": e.get("created"), "encrypted": e.get("encrypted"), "by": e.get("by"),
                     "why": e.get("why"), "cats": e.get("cats"), "sources": e.get("sources"),
                     "layout": e.get("layout"), "verified": e.get("verified"), "level": e.get("level"),
                     "note": e.get("note")})
    tree = {}
    for f in folders:
        tree.setdefault(f, {"path": f, "archives": 0, "size": 0})
    for a in arcs:
        parts = a["folder"].split("/") if a["folder"] else []
        for i in range(len(parts) + 1):
            p = "/".join(parts[:i])
            n = tree.setdefault(p, {"path": p, "archives": 0, "size": 0})
            n["archives"] += 1
            n["size"] += a["size"] or 0
    tree.setdefault("", {"path": "", "archives": 0, "size": 0})
    known = [a for a in arcs if a["original"]]
    fmts = {}
    for a in arcs:
        fmts[a["fmt"] or "?"] = fmts.get(a["fmt"] or "?", 0) + 1
    return {"root": config.root(), "archives": arcs, "folders": sorted(tree.values(), key=lambda n: n["path"].lower()),
            "loose": loose, "stats": {"count": len(arcs), "size": sum(a["size"] or 0 for a in arcs),
                                      "original": sum(a["original"] for a in known),
                                      "packed_known": sum(a["size"] or 0 for a in known),
                                      "files": sum(a["files"] or 0 for a in arcs), "formats": fmts,
                                      "unlisted": sum(1 for a in arcs if a["files"] is None)}}


def folder_list():
    return [f for f in scan_disk()[0]]


def library_summary(limit=70):
    """A compact text picture of the library for the AI: folders with what is in them."""
    ov = overview()
    by_folder = {}
    for a in ov["archives"]:
        by_folder.setdefault(a["folder"], []).append(a["name"])
    lines = []
    for n in ov["folders"]:
        if not n["path"]:
            continue
        names = by_folder.get(n["path"], [])
        ex = "; ".join(names[:3]) + (" ..." if len(names) > 3 else "")
        lines.append(f"- {n['path']}/  ({len(names)} archives{': ' + ex if ex else ''})")
        if len(lines) >= limit:
            break
    loose_root = by_folder.get("", [])
    if loose_root:
        lines.append(f"- (top level)  {len(loose_root)} archives: " + "; ".join(loose_root[:4]))
    return "\n".join(lines) or "(the library is empty - no folders yet)"


def append_candidates(folder, fmt="zip"):
    """Existing archives in a folder that Tansu could add the files to."""
    ov = overview()
    return [a for a in ov["archives"] if a["folder"].lower() == folder.lower() and a["fmt"] == fmt
            and not a["encrypted"]]


# ---------------------------------------------------------------- search inside everything
def search(q, limit=300):
    q = q.strip().lower()
    if not q:
        return []
    data = load()
    words = q.split()
    out = []
    for rel, e in data["archives"].items():
        hit_name = all(w in rel.lower() for w in words)
        lp = _list_path(e["id"])
        items = []
        if os.path.exists(lp):
            try:
                with open(lp, encoding="utf-8") as f:
                    items = json.load(f)
            except (OSError, ValueError):
                items = []
        hits = [i for i in items if not i["dir"] and all(w in i["name"].lower() for w in words)]
        if hit_name or hits:
            out.append({"rel": rel, "fmt": e.get("fmt"), "name_hit": hit_name, "count": len(hits),
                        "hits": hits[:25]})
        if len(out) >= limit:
            break
    out.sort(key=lambda r: (-r["name_hit"], -r["count"]))
    return out


def index_all(stop=None):
    """List every archive that has no cached list yet (background)."""
    data, _, _ = reconcile()
    done = 0
    for rel, e in list(data["archives"].items()):
        if stop is not None and stop.is_set():
            break
        if e.get("listed") and os.path.exists(_list_path(e["id"])):
            continue
        try:
            path = abs_of(rel)
            enc = engine.is_encrypted(path)
            items = engine.listing(path)
            remember_listing(rel, items, {"encrypted": enc})
            done += 1
        except Exception:
            with _lock:
                d = load()
                if rel in d["archives"]:
                    d["archives"][rel]["encrypted"] = True if engine.is_encrypted(abs_of(rel)) else d["archives"][rel].get("encrypted")
                    d["archives"][rel]["listed"] = None
                    save(d)
    return done


# ---------------------------------------------------------------- moving things around
def unique_path(folder_abs, filename):
    p = os.path.join(folder_abs, filename)
    if not os.path.exists(p):
        return p
    stem, ext = filename, ""
    for e in ARCH_EXT:
        if filename.lower().endswith(e):
            stem, ext = filename[: -len(e)], filename[-len(e):]
            break
    i = 2
    while os.path.exists(os.path.join(folder_abs, f"{stem} ({i}){ext}")):
        i += 1
    return os.path.join(folder_abs, f"{stem} ({i}){ext}")


def move(rel, folder=None, new_name=None):
    src = abs_of(rel)
    if not os.path.exists(src):
        raise ValueError("archive not found")
    folder = clean_folder(folder) if folder is not None else (rel.rsplit("/", 1)[0] if "/" in rel else "")
    name = rel.rsplit("/", 1)[-1]
    if new_name:
        ext = next((e for e in ARCH_EXT if name.lower().endswith(e)), "")
        stem = clean_part(new_name.removesuffix(ext) if ext and new_name.lower().endswith(ext) else new_name, 120)
        if not stem:
            raise ValueError("invalid name")
        name = stem + ext
    dst_dir = os.path.join(config.root(), *folder.split("/")) if folder else config.root()
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, name)
    if os.path.normcase(dst) == os.path.normcase(src):
        return rel
    dst = unique_path(dst_dir, name)
    os.replace(src, dst)
    new_rel = rel_of(dst)
    with _lock:
        data = load()
        if rel in data["archives"]:
            data["archives"][new_rel] = data["archives"].pop(rel)
            st = os.stat(dst)
            data["archives"][new_rel].update(size=st.st_size, mtime=st.st_mtime)
            save(data)
    remove_empty_dirs(os.path.dirname(src))
    return new_rel


def remove_empty_dirs(start):
    root = os.path.normcase(config.root())
    d = start
    while os.path.normcase(d).startswith(root) and os.path.normcase(d) != root:
        try:
            left = [x for x in os.listdir(d) if x.lower() not in ("desktop.ini", "thumbs.db")]
            if left:
                break
            for x in os.listdir(d):
                os.remove(os.path.join(d, x))
            os.rmdir(d)
        except OSError:
            break
        d = os.path.dirname(d)


def recycle(rel):
    from send2trash import send2trash
    p = abs_of(rel)
    send2trash(p)
    with _lock:
        data = load()
        e = data["archives"].pop(rel, None)
        save(data)
    if e:
        try:
            os.remove(_list_path(e["id"]))
        except OSError:
            pass
    remove_empty_dirs(os.path.dirname(p))


def set_meta(rel, **kw):
    with _lock:
        data = load()
        if rel in data["archives"]:
            data["archives"][rel].update(kw)
            save(data)


def sha256(path, stop=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(4 << 20)
            if not b:
                break
            h.update(b)
            if stop is not None and stop.is_set():
                raise engine.Cancelled()
    return h.hexdigest()


# ---------------------------------------------------------------- checkup
def checkup(deep=False, stop=None, cb=None):
    """Problems worth fixing in the library, each with a suggested fix."""
    cb = cb or (lambda f, t="": None)
    data, folders, loose = reconcile()
    root = config.root()
    issues = []
    arcs = data["archives"]
    # 1) archives lying at the top level
    top = [r for r in arcs if "/" not in r]
    for r in top:
        issues.append({"kind": "loose_archive", "rel": r, "title": f"“{r}” is not in a folder",
                       "fix": "move", "detail": "Tansu can file it into the right folder."})
    # 2) files that are not archives
    for r in loose:
        issues.append({"kind": "loose_file", "rel": r, "title": f"“{r.rsplit('/', 1)[-1]}” is not an archive",
                       "fix": "archive", "detail": f"Found in {r.rsplit('/', 1)[0] if '/' in r else 'the top level'}. "
                                                     "Archive it (then the original goes to the Recycle Bin)."})
    # 3) empty folders
    for f in folders:
        p = os.path.join(root, *f.split("/"))
        try:
            if not any(True for _ in os.scandir(p)):
                issues.append({"kind": "empty_folder", "rel": f, "title": f"Empty folder “{f}”", "fix": "remove",
                               "detail": "Nothing inside - it can go."})
        except OSError:
            pass
    # 4) folders with a single archive one level deeper than needed, near-duplicate folder names
    tops = {}
    for f in folders:
        key = re.sub(r"[^a-z0-9]", "", f.lower())
        tops.setdefault(key, []).append(f)
    for key, group in tops.items():
        if len(group) > 1:
            issues.append({"kind": "similar_folders", "rel": group[0], "others": group[1:],
                           "title": "Folders with almost the same name: " + ", ".join(f"“{g}”" for g in group),
                           "fix": "merge", "detail": f"Move everything into “{group[0]}”."})
    # 5) duplicates (same size, then same SHA-256)
    by_size = {}
    for r, e in arcs.items():
        by_size.setdefault(e.get("size"), []).append(r)
    groups = [g for s, g in by_size.items() if len(g) > 1 and s]
    for gi, g in enumerate(groups):
        cb(gi / max(len(groups), 1) * (.3 if deep else 1), "comparing duplicates")
        hashes = {}
        for r in g:
            try:
                hashes.setdefault(sha256(abs_of(r), stop), []).append(r)
            except OSError:
                continue
        copy_name = re.compile(r"copy|kópia|kopia|kopie|\(\d+\)|- copy|duplicate", re.I)
        for same in hashes.values():
            if len(same) > 1:
                # keep the one Tansu filed, not looking like a copy, inside a folder, made first
                keep = sorted(same, key=lambda r: (arcs[r].get("by") != "tansu", bool(copy_name.search(r.rsplit("/", 1)[-1])),
                                                   "/" not in r, arcs[r].get("created") or 0, len(r)))[0]
                for r in same:
                    if r != keep:
                        issues.append({"kind": "duplicate", "rel": r, "keep": keep,
                                       "title": f"“{r}” is an exact copy of “{keep}”", "fix": "recycle",
                                       "detail": "Byte-for-byte identical. The copy can go to the Recycle Bin."})
    # 6) never listed (Tansu does not know what is inside)
    for r, e in arcs.items():
        if not e.get("listed") and not e.get("encrypted"):
            issues.append({"kind": "unlisted", "rel": r, "title": f"Contents of “{r}” not indexed yet", "fix": "index",
                           "detail": "Index it so it shows up in search."})
    # 7) integrity (deep only: reads every archive)
    if deep:
        rels = [r for r, e in arcs.items() if not e.get("encrypted")]
        for i, r in enumerate(rels):
            if stop is not None and stop.is_set():
                break
            cb(.3 + .7 * i / max(len(rels), 1), f"testing {r}")
            ok, msg = engine.verify(abs_of(r), cancel=stop)
            set_meta(r, verified=time.time() if ok else None, broken=None if ok else msg)
            if not ok:
                issues.append({"kind": "broken", "rel": r, "title": f"“{r}” is damaged", "fix": None,
                               "detail": msg + ". Keep it until you have the originals again."})
    cb(1.0, "")
    order = ["broken", "duplicate", "loose_archive", "loose_file", "similar_folders", "empty_folder", "unlisted"]
    issues.sort(key=lambda i: order.index(i["kind"]))
    return issues
