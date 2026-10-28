"""Batches (what the user added) and background jobs (archiving, extracting, checkups)."""
import logging
import os
import queue
import shutil
import threading
import time
import traceback
import uuid

from . import config, engine, rules, scan, store

log = logging.getLogger("tansu")


# ---------------------------------------------------------------- batches
class Batches:
    def __init__(self):
        self.items = {}
        self.lock = threading.Lock()

    def add(self, paths, temp=False, batch_id=None, recycle=False):
        paths = [os.path.normpath(p) for p in paths if p and os.path.exists(p)]
        root = os.path.normcase(config.root())
        for p in paths:
            n = os.path.normcase(os.path.abspath(p))
            if n == root or root.startswith(n.rstrip("\\") + "\\"):
                raise ValueError("That folder contains the Archives library itself - pick something inside it.")
        if not paths:
            raise ValueError("nothing to add")
        with self.lock:
            b = self.items.get(batch_id) if batch_id else None
            if b is None:
                b = {"id": uuid.uuid4().hex[:10], "paths": [], "temp": temp, "created": time.time(), "ai": None,
                     "recycle": recycle, "drop": None}
                self.items[b["id"]] = b
            for p in paths:
                if p not in b["paths"]:
                    b["paths"].append(p)
            b["temp"] = b["temp"] or temp
        self.rescan(b)
        return b

    def rescan(self, b):
        b["facts"] = scan.analyse(b["paths"])
        folders = store.folder_list()
        b["opts"] = rules.options(b["facts"])
        b["rules"] = rules.plan(b["facts"], folders)
        b["ai"] = None
        return b

    def remove_path(self, bid, path):
        b = self.items[bid]
        b["paths"] = [p for p in b["paths"] if p != path]
        if not b["paths"]:
            self.drop(bid)
            return None
        return self.rescan(b)

    def drop(self, bid):
        b = self.items.pop(bid, None)
        for d in ([b.get("drop")] + b.get("extra_drops", [])) if b else []:
            if d:
                shutil.rmtree(d, ignore_errors=True)

    def plan(self, b):
        return b["ai"] or b["rules"]

    def public(self, b):
        f = b["facts"]
        p = self.plan(b)
        return {"id": b["id"], "temp": b["temp"], "recycle": b["recycle"], "facts": scan.public(f),
                "options": [{**o, **{k: rules.FORMATS[o["fmt"]][k] for k in ("name", "ext", "up", "down", "encrypt")}}
                            for o in b["opts"]],
                "levels": {fmt: {lv: rules.estimates(f, fmt, lv) for lv in rules.LEVELS} for fmt in rules.FORMATS},
                "plan": p, "rules": b["rules"], "has_ai": b["ai"] is not None,
                "preview": self.preview(b, p["layout"])}

    def preview(self, b, layout):
        m = engine.mapping(b["facts"]["files"], b["facts"]["empty_dirs"], layout, config.get()["skip_junk"])
        return {"layout": layout, "entries": len(m), "tree": engine.preview(m, 18)}


batches = Batches()


# ---------------------------------------------------------------- jobs
class Jobs:
    def __init__(self, workers=2):
        self.items = {}
        self.q = queue.Queue()
        self.cancels = {}
        for _ in range(workers):
            threading.Thread(target=self._worker, daemon=True).start()

    def _new(self, kind, title, fn, **extra):
        jid = uuid.uuid4().hex[:10]
        self.items[jid] = {"id": jid, "kind": kind, "title": title, "status": "queued", "progress": 0.0,
                           "phase": "Waiting…", "result": None, "error": None, "created": time.time(),
                           "started": None, "eta": None, **extra}
        self.cancels[jid] = threading.Event()
        self.q.put((jid, fn))
        return self.items[jid]

    def _worker(self):
        while True:
            jid, fn = self.q.get()
            j = self.items.get(jid)
            if not j or j["status"] == "cancelled":
                continue
            j["status"], j["started"] = "running", time.time()
            try:
                j["result"] = fn(j, self.cancels[jid])
                j["status"], j["progress"], j["eta"] = "done", 1.0, None
            except engine.Cancelled:
                j["status"], j["phase"] = "cancelled", "Cancelled"
            except Exception as e:
                log.error(traceback.format_exc())
                j["status"], j["error"] = "error", str(e) or type(e).__name__
            j["finished"] = time.time()

    def _progress(self, j, lo, hi, phase):
        def cb(frac, text=None):
            j["progress"] = lo + (hi - lo) * max(0.0, min(frac, 1.0))
            j["phase"] = text or phase
            el = time.time() - j["started"]
            if j["progress"] > .03 and el > 1.5:
                j["eta"] = round(el / j["progress"] * (1 - j["progress"]))
        return cb

    def cancel(self, jid):
        if jid in self.cancels:
            self.cancels[jid].set()
        j = self.items.get(jid)
        if j and j["status"] == "queued":
            j["status"] = "cancelled"

    def cancel_all(self):
        for jid in list(self.cancels):
            self.cancel(jid)

    def busy(self):
        return any(j["status"] in ("queued", "running") for j in self.items.values())

    def public(self):
        return sorted(self.items.values(), key=lambda j: -j["created"])[:40]

    # ------------------------------------------------------------ archive
    def archive(self, bid, plan, password=None):
        b = batches.items.get(bid)
        if not b:
            raise ValueError("these files are no longer in the list")
        s = config.get()
        fmt = plan["format"] if plan.get("format") in rules.FORMATS else "zip"
        level = plan["level"] if plan.get("level") in rules.LEVELS else "balanced"
        layout = plan["layout"] if plan.get("layout") in rules.LAYOUTS else "keep"
        folder = rules.clean_folder(plan.get("folder", ""))
        name = rules.clean_part(rules.strip_archive_ext(plan.get("name") or ""), 90) or "Archive"
        encrypt = bool(plan.get("encrypt")) and rules.FORMATS[fmt]["encrypt"]
        if encrypt and not password:
            raise ValueError("enter a password for the encrypted archive")
        append_to = plan.get("append_to") if fmt == "zip" else None
        if append_to:
            ap = store.abs_of(append_to)
            if not os.path.isfile(ap) or engine.fmt_of(ap) != "zip":
                raise ValueError("the archive to add to is gone")
        recycle = bool(plan.get("recycle")) and not b["temp"]
        skip_junk = plan.get("skip_junk", s["skip_junk"])
        title = (append_to.rsplit("/", 1)[-1] if append_to else name + rules.FORMATS[fmt]["ext"])
        facts = b["facts"]

        def run(j, cancel):
            t0 = time.time()
            m = engine.mapping(facts["files"], facts["empty_dirs"], layout, skip_junk)
            if not any(src for src, _ in m):
                raise ValueError("no files left to archive")
            if append_to:
                out = store.abs_of(append_to)
            else:
                dest = os.path.join(config.root(), *folder.split("/")) if folder else config.root()
                os.makedirs(dest, exist_ok=True)
                prefix = time.strftime("%Y-%m-%d ") if s["date_prefix"] else ""
                out = store.unique_path(dest, prefix + name + rules.FORMATS[fmt]["ext"])
            j["target"] = store.rel_of(out)
            verify = s["verify"]
            part, total = engine.create(out, fmt, level, m, self._progress(j, 0, .82 if verify else .98, "Packing"),
                                        cancel, password if encrypt else None, out if append_to else None)
            ok_msg = "not checked"
            if verify:
                expect = None if append_to else {arc: os.path.getsize(src) for src, arc in m if src}
                ok, ok_msg = engine.verify(part, password if encrypt else None, expect,
                                           self._progress(j, .82, .98, "Verifying checksums"), cancel)
                if not ok:
                    os.remove(part)
                    raise ValueError(f"verification failed - nothing was saved ({ok_msg})")
            os.replace(part, out)
            if append_to:
                items = engine.listing(out)
            else:
                items = [{"name": arc.rstrip("/"), "size": os.path.getsize(src) if src else 0,
                          "mtime": os.path.getmtime(src) if src else None, "dir": src is None, "packed": None}
                         for src, arc in m]
            cats = {c: v["files"] for c, v in facts["by_cat"].items()}
            meta = {"fmt": fmt, "level": level, "encrypted": encrypt, "layout": layout,
                    "why": plan.get("why"), "tip": plan.get("tip"), "note": plan.get("note"),
                    "sources": [r["path"] for r in facts["roots"]] if not b["temp"] else [r["name"] for r in facts["roots"]],
                    "cats": cats, "verified": time.time() if verify else None, "plan_by": plan.get("source")}
            if append_to:
                old = store.load()["archives"].get(append_to, {})
                meta = {**{k: v for k, v in old.items() if k not in ("size", "mtime", "files", "original", "listed")},
                        "history": (old.get("history") or []) + [{"at": time.time(), "added": len(m),
                                                                   "sources": meta["sources"]}],
                        "verified": meta["verified"]}
            rel = store.record(out, meta, items)
            recycled, failed = [], []
            if recycle:
                j["phase"] = "Moving originals to the Recycle Bin"
                from send2trash import send2trash
                for r in facts["roots"]:
                    try:
                        send2trash(r["path"])
                        recycled.append(r["path"])
                    except Exception as e:
                        failed.append(f"{r['name']}: {e}")
            batches.drop(bid)   # done: a reload must not offer the same files again
            size = os.path.getsize(out)
            return {"rel": rel, "path": out, "size": size, "original": total, "files": sum(1 for s_, _ in m if s_),
                    "secs": round(time.time() - t0, 1), "verified": ok_msg, "recycled": len(recycled),
                    "recycle_failed": failed, "appended": bool(append_to)}

        return self._new("archive", title, run, batch=bid, fmt=fmt)

    # ------------------------------------------------------------ extract
    def extract(self, rel, dest=None, members=None, password=None):
        path = store.abs_of(rel)
        if not os.path.isfile(path):
            raise ValueError("archive not found")
        stem = rules.strip_archive_ext(os.path.basename(path))
        if not dest:
            base = config.get()["extract_dir"]
            dest = os.path.join(base, stem)
            i = 2
            while os.path.exists(dest):
                dest = os.path.join(base, f"{stem} ({i})")
                i += 1

        def run(j, cancel):
            try:
                n = engine.extract(path, dest, members, password, self._progress(j, 0, 1, "Extracting"), cancel)
            except engine.Cancelled:
                raise
            except Exception as e:
                text = f"{type(e).__name__} {e}".lower()
                if os.path.isdir(dest) and not os.listdir(dest):
                    os.rmdir(dest)
                if any(w in text for w in ("password", "crc", "bad7z", "decrypt", "lzmaerror", "corrupt input", "unknown field")):
                    raise ValueError("wrong password (or the archive is damaged)") from e
                raise
            return {"dest": dest, "files": n}

        return self._new("extract", stem, run, rel=rel)

    # ------------------------------------------------------------ library checkup
    def checkup(self, deep=False):
        def run(j, cancel):
            cb = self._progress(j, 0, 1, "Looking through the library")
            issues = store.checkup(deep, cancel, cb)
            return {"issues": issues, "deep": deep, "at": time.time()}
        return self._new("checkup", "Library checkup" + (" + integrity test" if deep else ""), run)

    def index(self):
        def run(j, cancel):
            j["phase"] = "Indexing archive contents"
            return {"indexed": store.index_all(cancel)}
        return self._new("index", "Indexing contents", run)


jobs = Jobs()
