"""Kaizen 5S - local AI file & program organizer.

Copyright (c) 2026 Alexander Gubric. Open source under the MIT License (see LICENSE).

Runs a private server on 127.0.0.1 and opens it as a native-looking Edge app window.
The AI runs on the Ryzen AI NPU through FastFlowLM, or through LM Studio on other PCs. Nothing leaves this PC.
"""
import hashlib
import json
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import ai, chat, db, edition, folders, programs, scanner, winshell  # noqa: E402
from core.websec import Gate  # noqa: E402

PORT = int(os.environ.get("KAIZEN_PORT", "47555"))
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
VERSION = "1.0.2"
# the window gets a session cookie through a one-time launch key; the page itself holds no secret
gate = Gate("Kaizen", db.DATA_DIR, "X-Kaizen", PORT)
# the log stays small: 1 MB, plus two older files
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
    logging.handlers.RotatingFileHandler(os.path.join(db.DATA_DIR, "kaizen.log"), maxBytes=2 ** 20, backupCount=2,
                                         encoding="utf-8")])
log = logging.getLogger("kaizen")

progress = scanner.Progress(running=False, phase="", files=0, bytes=0, current="", error="", finished=0)
last_ping = {"t": 0.0}
thumb_gate = threading.Semaphore(4)
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}


# ------------------------------------------------------------------ scanning

def run_scan():
    if progress["running"]:
        return
    progress.set(running=True, phase="Starting", files=0, bytes=0, error="", current="", skipped=[], cancel=False,
                 stopped=False)

    def work():
        try:
            settings = db.get_settings()
            t = time.time()
            res = scanner.scan_files(settings, progress)
            res.update(programs.scan_programs(settings, progress))
            scanner.record_scan()
            log.info("scan done in %.1fs: %s", time.time() - t, {k: v for k, v in res.items() if k != "roots"})
        except scanner.ScanCancelled:
            progress.set(stopped=True)
            log.info("scan stopped by the user after %s files", progress.get("files"))
        except Exception as e:  # noqa: BLE001
            log.error("scan failed: %s", traceback.format_exc())
            progress.set(error=str(e))
        finally:
            progress.set(running=False, phase="", finished=time.time())

    threading.Thread(target=work, daemon=True).start()


# ------------------------------------------------------------------ queries

def _with_descriptions(items, prefix):
    if not items:
        return items
    keys = {}
    for it in items:
        ed = edition.get()["id"]
        k = f"f:{it['path']}:{it['mtime']}" if prefix == "f" else (
            f"p:{it['key']}" if ed == "public" else f"p:{ed}:{it['key']}")
        keys[k] = it
    marks = ",".join("?" * len(keys))
    for r in db.rows(f"SELECT key, text FROM descriptions WHERE key IN ({marks})", list(keys)):
        keys[r["key"]]["ai"] = r["text"]
    for it in items:
        it["reasons"] = json.loads(it.get("reasons") or "[]")
    return items


def overview():
    sc = scanner.scores()
    history = db.rows("SELECT ts, overall, s_sort, s_order, s_shine, s_std, s_sustain, reclaim FROM scans "
                      "ORDER BY ts DESC LIMIT 24")[::-1]
    folders = db.rows("SELECT * FROM folders WHERE need NOT IN ('sustain','app') AND files >= 1 "
                      "ORDER BY severity * (sort_n + order_n + shine_n + std_n) DESC LIMIT 6")
    progs = db.rows("SELECT * FROM programs WHERE i_sort=1 AND kind='app' ORDER BY size DESC LIMIT 5")
    pc = db.one("SELECT COUNT(*) n, SUM(i_sort) unused, SUM(i_std) dup, SUM(kind='leftover') lo, SUM(protected) prot, "
                "SUM(sustained) active, SUM(CASE WHEN i_sort THEN size END) unused_bytes FROM programs")
    managed = db.one("SELECT COUNT(*) n, COALESCE(SUM(size),0) b FROM files WHERE managed IS NOT NULL")
    return {"scores": sc, "history": history, "folders": folders, "programs": _with_descriptions(progs, "p"),
            "program_counts": pc, "managed": managed}


def folder_list():
    """The folder manager's list: Windows libraries (on/off) and the extra folders with their kind."""
    s = db.get_settings()
    libs = scanner.library_paths(s)
    out = {"libraries": [], "extra": []}
    for name, _, _ in scanner.KNOWN_FOLDERS:
        path = libs.get(name, "")
        out["libraries"].append({"name": name, "path": path, "enabled": name not in s["skip_roots"],
                                 "exists": os.path.isdir(path), "kind": folders.volume(path)[0] if path else "local"})
    for p in s["extra_roots"]:
        kind, fs, label = folders.volume(p) if (p.startswith("\\\\") or p[1:3] == ":\\") else ("local", "", "")
        out["extra"].append({"path": p, "kind": kind, "fs": fs, "label": label})
    return out


def tree(path):
    if not path:
        children = db.rows("SELECT * FROM folders WHERE parent='' ORDER BY bytes DESC")
        return {"path": "", "name": "This PC", "children": children}
    me = db.one("SELECT * FROM folders WHERE path=?", (path,))
    children = db.rows("SELECT * FROM folders WHERE parent=? ORDER BY bytes DESC", (path,))
    if me:
        here = db.one("SELECT COUNT(*) n, COALESCE(SUM(size),0) b, SUM(i_sort) s, SUM(i_order) o, SUM(i_shine) sh, "
                      "SUM(i_std) st, SUM(managed IS NOT NULL) m, "
                      "COALESCE(SUM(CASE WHEN managed IS NOT NULL THEN size END),0) mb FROM files WHERE dir=?", (path,))
        if here["n"]:
            n = max(here["n"] - (here["m"] or 0), 1)
            shares = {"sort": (here["s"] or 0) / n, "order": (here["o"] or 0) / n, "shine": (here["sh"] or 0) / n,
                      "std": (here["st"] or 0) / n}
            need = max(shares, key=shares.get)
            children.append({"path": path, "name": "Files in this folder", "files_here": True, "bytes": here["b"],
                             "files": here["n"], "need": "app" if (here["m"] or 0) >= 0.9 * here["n"] and me["parent"]
                             else (need if shares[need] >= 0.08 else "sustain"), "severity": shares[need],
                             "subdirs": 0, "sort_n": here["s"] or 0, "order_n": here["o"] or 0,
                             "shine_n": here["sh"] or 0, "std_n": here["st"] or 0, "last_used": me["last_used"],
                             "managed_n": here["m"] or 0, "managed_bytes": here["mb"]})
    crumbs = []
    p = me
    while p:
        crumbs.insert(0, {"path": p["path"], "name": p["name"]})
        p = db.one("SELECT * FROM folders WHERE path=?", (p["parent"],)) if p["parent"] else None
    return {"path": path, "name": me["name"] if me else path, "children": children, "crumbs": crumbs,
            "me": me}


def list_files(qs):
    s = qs.get("s", "all")
    where, args = [], []
    cond = {"all": "(i_sort=1 OR i_order=1 OR i_shine=1 OR i_std=1)", "sort": "i_sort=1", "order": "i_order=1",
            "shine": "i_shine=1", "std": "i_std=1", "sustain": "sustained=1", "everything": "1=1",
            "app": "managed IS NOT NULL"}.get(s, "1=1")
    where.append(cond)
    if s != "app" and not qs.get("ids"):
        where.append("managed IS NULL")
    if qs.get("path"):
        p = qs["path"]
        if qs.get("here"):
            where.append("dir = ?")
            args.append(p)
        else:
            where.append("(dir = ? OR substr(dir, 1, ?) = ?)")
            args += [p, len(p) + 1, p + "\\"]
    if qs.get("q"):
        where.append("name LIKE ?")
        args.append(f"%{qs['q']}%")
    if qs.get("ids"):
        ids = [int(x) for x in qs["ids"].split(",") if x.isdigit()]
        where = [f"id IN ({','.join('?' * len(ids))})"]
        args = ids
    order = {"size": "size DESC", "old": "last_used ASC", "new": "last_used DESC", "name": "name COLLATE NOCASE"}.get(
        qs.get("sort", "size"), "size DESC")
    w = " AND ".join(where)
    total = db.one(f"SELECT COUNT(*) n, COALESCE(SUM(size),0) b FROM files WHERE {w}", args)
    limit = min(int(qs.get("limit", 60)), 300)
    offset = int(qs.get("offset", 0))
    items = db.rows(f"SELECT * FROM files WHERE {w} ORDER BY {order} LIMIT ? OFFSET ?", args + [limit, offset])
    return {"items": _with_descriptions(items, "f"), "total": total["n"], "total_bytes": total["b"]}


def list_programs(qs):
    tab = qs.get("tab", "unused")
    conds = {
        "unused": ("kind='app' AND i_sort=1", "COALESCE(NULLIF(last_run,0), installed) ASC"),
        "dupes": ("dup_group IS NOT NULL", "dup_group, last_run DESC"),
        "leftovers": ("kind='leftover'", "size DESC"),
        "active": ("kind='app' AND sustained=1", "last_run DESC"),
        "protected": ("protected=1", "name COLLATE NOCASE"),
        "all": ("kind='app'", "name COLLATE NOCASE"),
    }
    where, order = conds.get(tab, conds["unused"])
    args = []
    if qs.get("q"):
        where += " AND (name LIKE ? OR publisher LIKE ?)"
        args += [f"%{qs['q']}%"] * 2
    items = db.rows(f"SELECT * FROM programs WHERE {where} ORDER BY {order}", args)
    for it in items:
        it["evidence"] = json.loads(it["evidence"] or "[]")
    counts = {k: db.one(f"SELECT COUNT(*) n FROM programs WHERE {c[0]}")["n"] for k, c in conds.items()}
    return {"items": _with_descriptions(items, "p"), "counts": counts}


# ------------------------------------------------------------------ actions

def _unique(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{stem} ({i}){ext}"):
        i += 1
    return f"{stem} ({i}){ext}"


def _log(batch, op, src, dst, row):
    with db.conn() as c:
        c.execute("INSERT INTO actions(batch, ts, op, src, dst, row) VALUES(?,?,?,?,?,?)",
                  (batch, time.time(), op, src, dst, json.dumps(row, ensure_ascii=False)))


def _changed_since_scan(r):
    try:
        st = os.stat(r["path"])
    except OSError:
        return True
    return st.st_size != r["size"] or abs(st.st_mtime - (r["mtime"] or 0)) > 2


def do_action(body):
    op, kind = body.get("op"), body.get("kind", "file")
    ids = [int(i) for i in body.get("ids", [])]
    batch = uuid.uuid4().hex[:12]
    table = "files" if kind == "file" else "programs"
    marks = ",".join("?" * len(ids))
    rows = db.rows(f"SELECT * FROM {table} WHERE id IN ({marks})", ids) if ids else []
    c = db.conn()

    if op == "recycle" and kind == "file":
        # the same rules the UI shows, enforced here: network shares and USB drives have no Recycle Bin, app data
        # is never touched, and a file that changed since the scan is not acted on from stale scan data
        failed = []
        ok_rows = []
        for r in rows:
            if r.get("remote") or folders.no_recycle_bin(r["path"]):
                failed.append((r["path"], "Network or removable drive: no Recycle Bin, so Kaizen won't delete it"))
            elif r.get("managed"):
                failed.append((r["path"], f"{r['managed']}: Kaizen doesn't delete app data"))
            elif _changed_since_scan(r):
                failed.append((r["path"], "This file changed since the last scan. Scan again before cleaning it up."))
            else:
                ok_rows.append(r)
        done, refused, entries = winshell.recycle([r["path"] for r in ok_rows], {r["path"]: r["size"] for r in ok_rows})
        failed += refused
        done_set = set(done)
        freed = 0
        for r in ok_rows:
            if r["path"] in done_set:
                freed += r["size"] or 0
                _log(batch, "recycle", r["path"], entries.get(r["path"], ""), r)   # dst = its $I entry, for Undo
                with c:
                    c.execute("DELETE FROM files WHERE id=?", (r["id"],))
        return {"ok": True, "batch": batch, "done": len(done), "failed": failed, "freed": freed}

    if op == "keep":
        with c:
            for r in rows:
                key = r["path"] if kind == "file" else r["key"]
                c.execute("INSERT OR REPLACE INTO kept VALUES(?, ?)", (key, time.time()))
                if kind == "file":
                    c.execute("UPDATE files SET i_sort=0, i_order=0, i_shine=0, i_std=0, sustained=1, reasons='[]' "
                              "WHERE id=?", (r["id"],))
                else:
                    c.execute("UPDATE programs SET i_sort=0, i_std=0, i_shine=0, sustained=1, reasons='[]' WHERE id=?",
                              (r["id"],))
                _log(batch, "keep", key, "", r)
        return {"ok": True, "batch": batch, "done": len(rows)}

    if op == "move":
        moved, failed = 0, []
        for r in rows:
            target = body.get("target") or r["target"]
            if not target:
                continue
            try:
                os.makedirs(target, exist_ok=True)
                dest = _unique(os.path.join(target, r["name"]))
                shutil.move(r["path"], dest)
                _log(batch, "move", r["path"], dest, r)
                reasons = [x for x in json.loads(r["reasons"] or "[]") if x["s"] != "order"]
                with c:
                    c.execute("UPDATE files SET path=?, dir=?, name=?, i_order=0, target=NULL, reasons=? WHERE id=?",
                              (dest, os.path.dirname(dest), os.path.basename(dest),
                               json.dumps(reasons, ensure_ascii=False), r["id"]))
                moved += 1
            except OSError as e:
                failed.append((r["path"], str(e)))
        return {"ok": True, "batch": batch, "done": moved, "failed": failed}

    if op == "rename":
        names = body.get("names", {})
        done, failed = 0, []
        for r in rows:
            new = (names.get(str(r["id"])) or r["new_name"] or "").strip()
            if not new or any(ch in new for ch in '\\/:*?"<>|'):
                continue
            dest = _unique(os.path.join(r["dir"], new))
            try:
                os.rename(r["path"], dest)
                _log(batch, "rename", r["path"], dest, r)
                reasons = [x for x in json.loads(r["reasons"] or "[]") if x["s"] != "std"]
                with c:
                    c.execute("UPDATE files SET path=?, name=?, i_std=0, new_name=NULL, reasons=? WHERE id=?",
                              (dest, os.path.basename(dest), json.dumps(reasons, ensure_ascii=False), r["id"]))
                done += 1
            except OSError as e:
                failed.append((r["path"], str(e)))
        return {"ok": True, "batch": batch, "done": done, "failed": failed}

    if op == "undo":
        acts = db.rows("SELECT * FROM actions WHERE batch=? AND undone=0", (body.get("batch"),))
        restored = 0
        recycled = [a for a in acts if a["op"] == "recycle"]
        failed = []
        if recycled:
            back = set(winshell.restore_from_recycle_bin([(a["src"], a["dst"] or None) for a in recycled]))
            failed = [a["src"] for a in recycled if a["src"] not in back]
            for a in recycled:
                if a["src"] in back:
                    row = json.loads(a["row"])
                    cols = [k for k in row if k != "id"]
                    with c:
                        c.execute(f"INSERT OR REPLACE INTO files({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                                  [row[k] for k in cols])
                    restored += 1
        for a in acts:
            row = json.loads(a["row"])
            try:
                if a["op"] in ("move", "rename") and os.path.exists(a["dst"]) and not os.path.exists(a["src"]):
                    shutil.move(a["dst"], a["src"])
                    with c:
                        c.execute("UPDATE files SET path=?, dir=?, name=?, i_order=?, i_std=?, target=?, new_name=?, "
                                  "reasons=? WHERE id=?", (row["path"], row["dir"], row["name"], row["i_order"],
                                                           row["i_std"], row["target"], row["new_name"], row["reasons"],
                                                           row["id"]))
                    restored += 1
                elif a["op"] == "keep":
                    with c:
                        c.execute("DELETE FROM kept WHERE path=?", (a["src"],))
                        if "path" in row:
                            c.execute("UPDATE files SET i_sort=?, i_order=?, i_shine=?, i_std=?, sustained=?, "
                                      "reasons=? WHERE id=?", (row["i_sort"], row["i_order"], row["i_shine"],
                                                               row["i_std"], row["sustained"], row["reasons"], row["id"]))
                        else:
                            c.execute("UPDATE programs SET i_sort=?, i_std=?, i_shine=?, sustained=?, reasons=? "
                                      "WHERE id=?", (row["i_sort"], row["i_std"], row["i_shine"], row["sustained"],
                                                     row["reasons"], row["id"]))
                    restored += 1
            except OSError:
                continue
        with c:   # what couldn't be restored stays undoable (and is reported, not counted as success)
            if failed:
                c.execute("UPDATE actions SET undone=1 WHERE batch=? AND NOT (op='recycle' AND src IN (%s))"
                          % ",".join("?" * len(failed)), (body.get("batch"), *failed))
            else:
                c.execute("UPDATE actions SET undone=1 WHERE batch=?", (body.get("batch"),))
        return {"ok": not failed, "restored": restored, "failed": [(p, "Not found in the Recycle Bin any more")
                                                                    for p in failed]}

    if op in ("open", "reveal") and rows:
        r = rows[0]
        path = r.get("path") or r.get("exe") or r.get("location")
        if op == "reveal" and kind == "program" and r.get("location"):
            os.startfile(r["location"])  # noqa: S606
        elif path and os.path.exists(path):
            (winshell.open_path if op == "open" else winshell.reveal)(path)
        return {"ok": True}

    if op == "uninstall" and rows:
        if not edition.get()["allow_uninstall"]:  # enforced here too, not only by the greyed-out button
            return {"ok": False, "error": edition.get()["uninstall_note"] or "Uninstalling is disabled."}
        r = rows[0]
        if r["protected"]:
            return {"ok": False, "error": "This program is protected: " + r["protect_reason"]}
        ok = winshell.run_uninstaller(r["uninstall"])
        if not ok:
            winshell.open_apps_settings()
        _log(batch, "uninstall", r["name"], "", r)
        return {"ok": True, "launched": ok}

    return {"ok": False, "error": "Unknown action"}


# ------------------------------------------------------------------ thumbnails

def thumbnail(path, size, mode):
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = hashlib.sha1(f"{path}|{st.st_mtime}|{st.st_size}|{size}|{mode}".encode()).hexdigest()
    cache = os.path.join(db.THUMB_DIR, key + ".webp")
    if os.path.exists(cache):
        with open(cache, "rb") as f:
            return f.read()
    # cloud placeholders and network files: use Windows' cached thumbnail or the icon, never pull the whole file
    cloud = bool(getattr(st, "st_file_attributes", 0) & winshell.CLOUD_ATTRS) or folders.volume(path)[0] in (
        "network", "cloud")
    with thumb_gate:
        flags = winshell.THUMB_ICON_ONLY if mode == "icon" else (
            winshell.THUMB_IN_CACHE_ONLY if cloud else winshell.THUMB_ANY)
        with winshell.preserve_atime(path):
            img = winshell.shell_image(path, size, flags)
        if img is None and flags != winshell.THUMB_ICON_ONLY:
            img = winshell.shell_image(path, size, winshell.THUMB_ICON_ONLY)
    if img is None:
        return None
    img.thumbnail((size, size))
    img.save(cache, "WEBP", quality=82, method=4)
    with open(cache, "rb") as f:
        return f.read()


NO_AI = ("No local AI is installed, so chat and the one-line descriptions are off. Everything else in Kaizen works. "
         "To add AI, install LM Studio (any PC) or FastFlowLM (AMD Ryzen AI), then restart Kaizen.")


def ai_unavailable():
    """(status, body) for requests that need the AI while it isn't ready. 503 = try again soon, 409 = won't come."""
    ai.npu.ensure()  # picks up an engine installed since Kaizen started
    if ai.npu.state == "missing":
        return 409, {"error": NO_AI, "code": "no_ai"}
    if ai.npu.state == "starting":
        where = "on the NPU" if ai.npu.kind == "flm" else "in LM Studio"
        return 503, {"error": f"The AI model is still loading {where}. Try again in a few seconds.", "code": "starting"}
    return 503, {"error": ai.npu.detail or "The local AI isn't running. Press the AI button at the top to start it.",
                 "code": "offline"}


# ------------------------------------------------------------------ HTTP

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def end_headers(self):
        gate.add_headers(self)
        super().end_headers()

    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        if not gate.get_allowed(self):   # host, cross-site, session cookie
            return
        url = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path.startswith("/api/") and not self.headers.get("X-Kaizen") and url.path != "/api/thumb":
                return self._send(403, {"error": "forbidden"})
            if url.path == "/api/status":
                return self._send(200, {
                    "scan": dict(progress),
                    "ai": {"state": ai.npu.state, "detail": ai.npu.detail, "model": ai.npu.model, "tps": ai.npu.tps,
                           "ttft": ai.npu.ttft, "engine": ai.npu.label, "kind": ai.npu.kind},
                    "has_data": bool(db.one("SELECT 1 FROM scans LIMIT 1")),
                    "last_scan": (db.one("SELECT MAX(ts) t FROM scans") or {}).get("t"),
                    "settings": db.get_settings(), "version": VERSION, "edition": edition.get()})
            if url.path == "/api/overview":
                return self._send(200, overview())
            if url.path == "/api/tree":
                return self._send(200, tree(qs.get("path", "")))
            if url.path == "/api/files":
                return self._send(200, list_files(qs))
            if url.path == "/api/programs":
                return self._send(200, list_programs(qs))
            if url.path == "/api/folders":
                return self._send(200, folder_list())
            if url.path == "/api/models":
                return self._send(200, {"models": ai.npu.downloaded_models()})
            if url.path == "/api/thumb":   # <img> requests carry the session cookie
                data = thumbnail(qs.get("path", ""), min(int(qs.get("size", 256)), 512), qs.get("mode", ""))
                if data is None:
                    return self._send(404, {"error": "no thumbnail"})
                return self._send(200, data, "image/webp", {"Cache-Control": "private, max-age=604800"})
            return self._static(url.path)
        except Exception:  # noqa: BLE001
            log.error("GET %s failed: %s", self.path, traceback.format_exc())
            return self._send(500, {"error": "internal error"})

    def do_POST(self):
        if gate.handle_launch(self):
            return
        if not gate.post_allowed(self):   # checked before the body is read; refused connections are closed
            return
        url = urlparse(self.path)
        try:
            body = self._body()
            if url.path == "/api/ping":
                last_ping["t"] = time.time()
                return self._send(200, {"ok": True})
            if url.path == "/api/scan":
                run_scan()
                return self._send(200, {"ok": True})
            if url.path == "/api/scan/stop":
                progress["cancel"] = True
                return self._send(200, {"ok": True})
            if url.path == "/api/settings":
                before = db.get_settings()
                after = db.save_settings(body)
                if any(before[k] != after[k] for k in ("pmode", "flm_port", "engine", "lms_port", "lms_model")):
                    threading.Thread(target=ai.npu.restart, daemon=True).start()   # needs a server (re)start
                elif before["model"] != after["model"]:
                    ai.npu.request_switch()   # FastFlowLM swaps the model in place, no restart
                return self._send(200, after)
            if url.path == "/api/folders/check":
                return self._send(200, folders.check(body.get("path", ""), edition.get().get("org", "")))
            if url.path == "/api/folders/pick":
                return self._send(200, {"path": folders.pick_folder()})
            if url.path == "/api/ai/start":
                ai.npu.ensure()
                return self._send(200, {"ok": True})
            if url.path == "/api/action":
                return self._send(200, do_action(body))
            if url.path == "/api/describe":
                if ai.npu.state != "online":
                    return self._send(*ai_unavailable())
                if body.get("kind") == "program":
                    row = db.one("SELECT * FROM programs WHERE id=?", (int(body["id"]),))
                    text = ai.describe_program(row) if row else ""
                else:
                    row = db.one("SELECT * FROM files WHERE id=?", (int(body["id"]),))
                    text = ai.describe_file(row) if row else ""
                return self._send(200, {"text": text})
            if url.path == "/api/chat":
                return self._chat(body)
            return self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            log.error("POST %s failed: %s", self.path, traceback.format_exc())
            return self._send(500, {"error": str(e)})

    def _chat(self, body):
        if ai.npu.state != "online":
            return self._send(*ai_unavailable())
        history = [m for m in body.get("messages", []) if m.get("role") in ("user", "assistant")][-6:]
        question = history[-1]["content"] if history else ""
        system, items = chat.build_context(question)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def emit(obj):
            self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False, default=str)}\n\n".encode())
            self.wfile.flush()

        try:
            emit({"items": items})
            for piece in ai.npu.stream([{"role": "system", "content": system}] + history, max_tokens=450,
                                       temperature=0.2):
                emit({"t": piece})
            emit({"done": True, "tps": ai.npu.tps, "ttft": ai.npu.ttft, "engine": ai.npu.label})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            log.error("chat failed: %s", traceback.format_exc())
            try:
                emit({"error": str(e)})
            except OSError:
                pass

    def _static(self, path):
        if path in ("/", "/index.html"):
            path = "/index.html"
        full = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not full.startswith(WEB) or not os.path.isfile(full):
            return self._send(404, {"error": "not found"})
        with open(full, "rb") as f:
            data = f.read()
        if path == "/index.html":
            data = data.replace(b"{{TOKEN}}", b"1")   # the session cookie authenticates; the header only marks app calls
        return self._send(200, data, CONTENT_TYPES.get(os.path.splitext(full)[1], "application/octet-stream"),
                          {"Cache-Control": "no-store"})


def find_edge():
    for p in (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
              os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")):
        if os.path.exists(p):
            return p
    return None


def open_window(url):
    edge = find_edge()
    if edge:
        return subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={os.path.join(db.DATA_DIR, 'window')}",
                                 "--window-size=1440,920", "--no-first-run", "--no-default-browser-check",
                                 "--disable-features=Translate"])
    import webbrowser
    webbrowser.open(url)
    return None


def prune_thumbnails(days=60):
    """Cached previews of files nobody looked at for a while (often of files already deleted) are removed."""
    cutoff = time.time() - days * 86400
    try:
        for e in os.scandir(db.THUMB_DIR):
            if e.is_file() and e.stat().st_atime < cutoff and e.stat().st_mtime < cutoff:
                os.remove(e.path)
    except OSError:
        pass


def main():
    threading.Thread(target=prune_thumbnails, daemon=True).start()
    running = gate.find_running()
    if running:   # this user already runs Kaizen - just show another window
        if "--no-window" not in sys.argv:
            open_window(f"http://127.0.0.1:{running[0]}/?k={running[1]}")
        return
    server = gate.bind(ThreadingHTTPServer, Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    gate.publish()
    if not os.environ.get("KAIZEN_NO_AI"):   # KAIZEN_NO_AI=1: tests without starting an AI engine
        ai.npu.ensure()
    log.info("Kaizen started on port %s", gate.port)
    headless = "--no-window" in sys.argv
    window = None if headless else open_window(gate.launch_url())
    started = time.time()
    try:
        while True:
            time.sleep(3)
            if headless:
                continue
            idle = time.time() - (last_ping["t"] or started)
            # Our Edge window has its own profile, so its process lives exactly as long as the window.
            if window is not None and window.poll() is not None and idle > 10:
                break
            if window is None and idle > (150 if last_ping["t"] else 300):
                break  # browser tab closed
    except KeyboardInterrupt:
        pass
    finally:
        gate.withdraw()
        ai.npu.stop()
        server.shutdown()
        log.info("Kaizen stopped")


if __name__ == "__main__":
    main()
