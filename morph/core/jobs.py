"""Conversion jobs: run route steps in the background with progress, cancel and a tidy output folder."""
import os
import shutil
import threading
import time
import traceback
import uuid
import logging

from . import config, docs, media, router
from .formats import FORMATS, split_name
from .inbox import human_size, inbox

log = logging.getLogger("morph")


class Ctx:
    """Handed to every engine: options, progress reporting, cancellation."""

    def __init__(self, job, opts, info):
        self.job, self.opts, self._info = job, opts, info
        self.cancelled = False
        self.proc = None
        self.step, self.steps = 0, 1
        self.src0 = None

    def progress(self, frac, stage=None):
        if frac is None:
            self.job["progress"] = None if self.steps == 1 else (self.step / self.steps)
        else:
            self.job["progress"] = (self.step + max(0.0, min(frac, 1.0))) / self.steps
        if stage:
            self.job["stage"] = stage

    def attach(self, proc):
        self.proc = proc
        if self.cancelled:
            proc.kill()

    def info_for(self, path):
        return self._info if path == self.src0 else media.probe(path)


def unique(path):
    if not os.path.exists(path):
        return path
    stem, ext = split_name(os.path.basename(path))
    folder = os.path.dirname(path)
    for i in range(1, 1000):
        p = os.path.join(folder, f"{stem} ({i}).{ext}" if ext else f"{stem} ({i})")
        if not os.path.exists(p):
            return p
    return path


class Jobs:
    def __init__(self):
        self.items = {}
        self.ctx = {}
        self.slots = threading.BoundedSemaphore(max(1, config.get()["parallel"]))

    def public(self):
        return [{k: v for k, v in j.items() if not k.startswith("_")} for j in self.items.values()]

    def _new(self, file_id, name, target, label):
        job = {"id": uuid.uuid4().hex[:10], "file": file_id, "name": name, "target": target, "label": label,
               "status": "queued", "progress": 0.0, "stage": "Waiting", "out": None, "out_name": None,
               "out_size": None, "error": None, "t0": time.time(), "t1": None}
        self.items[job["id"]] = job
        return job

    def _dest_dir(self, entry):
        s = config.get()
        if entry and not entry["temp"] and s["beside"]:
            return os.path.dirname(entry["path"])
        os.makedirs(s["output_dir"], exist_ok=True)
        return s["output_dir"]

    def submit(self, file_id, target, opts):
        e = inbox.get(file_id)
        if not e:
            raise ValueError("File not found")
        if target not in {t["id"] for t in e["targets"]}:
            raise ValueError("That conversion is not available")
        job = self._new(file_id, e["name"], target, FORMATS[target]["name"])
        s = config.get()
        opts = {"quality": s["quality"], "gpu": s["gpu"], **(opts or {})}
        ctx = Ctx(job, opts, e["info"])
        self.ctx[job["id"]] = ctx
        threading.Thread(target=self._run, args=(job, ctx, e, target), daemon=True).start()
        return job

    def _run(self, job, ctx, e, target):
        work = os.path.join(config.WORK, job["id"])
        with self.slots:
            if ctx.cancelled:
                job.update(status="cancelled", stage="Cancelled", t1=time.time())
                return
            job.update(status="running", stage="Starting", t0=time.time())
            try:
                steps = router.plan(e["fid"], target, e["info"])
                ctx.steps = len(steps)
                stem, _ = split_name(e["name"])
                cur = e["path"]
                ctx.src0 = cur
                for i, (engine, fn, a, b) in enumerate(steps):
                    ctx.step = i
                    ctx.progress(0, f"{FORMATS[a]['name'].split(' (')[0]} → {FORMATS[b]['name'].split(' (')[0]}")
                    folder = os.path.join(work, str(i))
                    os.makedirs(folder, exist_ok=True)
                    dst = os.path.join(folder, f"{stem}.{FORMATS[b]['ext']}")
                    made = fn(ctx, cur, dst, a, b)
                    if ctx.cancelled:
                        raise InterruptedError
                    if made != dst and i < len(steps) - 1:
                        raise RuntimeError("This document has several pages - convert it in one step instead")
                    cur = made
                ctx.step = ctx.steps
                _, ext = split_name(os.path.basename(cur))
                name = f"{stem}{' (compressed)' if target == e['fid'] else ''}.{ext}"
                final = unique(os.path.join(self._dest_dir(e), name))
                shutil.move(cur, final)
                size = os.path.getsize(final)
                job.update(status="done", progress=1.0, stage="Done", out=final, out_name=os.path.basename(final),
                           out_size=size, out_size_h=human_size(size), in_size=e["size"], t1=time.time())
            except InterruptedError:
                job.update(status="cancelled", stage="Cancelled", t1=time.time())
            except Exception as ex:
                log.error(traceback.format_exc())
                msg = str(ex) or ex.__class__.__name__
                job.update(status="error", stage="Failed", error=msg[:400], t1=time.time())
            finally:
                shutil.rmtree(work, ignore_errors=True)
                self.ctx.pop(job["id"], None)

    def merge(self, file_ids, opts):
        """Several PDFs/pictures into one PDF, in the order given."""
        entries = [inbox.get(i) for i in file_ids]
        entries = [e for e in entries if e and e.get("fid")]
        if len(entries) < 2:
            raise ValueError("Pick at least two files")
        job = self._new(None, f"{len(entries)} files", "pdf", "Merged PDF")
        ctx = Ctx(job, opts or {}, {})

        def run():
            with self.slots:
                job.update(status="running", stage="Merging")
                try:
                    stem, _ = split_name(entries[0]["name"])
                    work = os.path.join(config.WORK, job["id"])
                    os.makedirs(work, exist_ok=True)
                    tmp = docs.merge_pdf(ctx, [(e["path"], e["fid"]) for e in entries], os.path.join(work, "m.pdf"))
                    final = unique(os.path.join(self._dest_dir(entries[0]), f"{stem} (merged).pdf"))
                    shutil.move(tmp, final)
                    size = os.path.getsize(final)
                    job.update(status="done", progress=1.0, stage="Done", out=final, out_name=os.path.basename(final),
                               out_size=size, out_size_h=human_size(size), in_size=sum(e["size"] for e in entries),
                               t1=time.time())
                except InterruptedError:
                    job.update(status="cancelled", stage="Cancelled", t1=time.time())
                except Exception as ex:
                    log.error(traceback.format_exc())
                    job.update(status="error", stage="Failed", error=str(ex)[:400], t1=time.time())
                finally:
                    shutil.rmtree(os.path.join(config.WORK, job["id"]), ignore_errors=True)
                    self.ctx.pop(job["id"], None)

        self.ctx[job["id"]] = ctx
        threading.Thread(target=run, daemon=True).start()
        return job

    def cancel(self, job_id):
        ctx = self.ctx.get(job_id)
        if ctx:
            ctx.cancelled = True
            if ctx.proc and ctx.proc.poll() is None:
                ctx.proc.kill()

    def cancel_all(self):
        for jid in list(self.ctx):
            self.cancel(jid)


jobs = Jobs()
