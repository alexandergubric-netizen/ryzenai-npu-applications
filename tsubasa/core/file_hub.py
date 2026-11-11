"""Workspace-confined file operations and single-use write proposals."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
from tempfile import TemporaryDirectory, TemporaryFile

from core import job_runner
from core.platform import worker_python
import threading
import time

from core.file_catalog import CAT, EXTS, filename, target, validate

ROOT=Path(__file__).resolve().parents[1]
LIMIT=8*1024*1024


def safe(path):
    if path.is_symlink() or path.is_junction():
        raise ValueError("Linked paths are unavailable.")
    if path.exists():
        s=path.lstat()
        if getattr(s,"st_file_attributes",0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("Reparse points are unavailable.")
        if not path.is_dir() and (not path.is_file() or s.st_nlink!=1 or s.st_size>LIMIT):
            raise ValueError("Choose a regular file under 8 MiB.")
    return path


def run_file_worker(request, folder, *, output_limit, print_pdf=False):
    # Stdin is an owned temporary file so a worker cannot block its supervisor while reading a pipe.
    command = [str(worker_python(ROOT)), "-B", str(ROOT / "tools/file_worker.py")]
    with TemporaryFile(dir=folder) as source:
        source.write(json.dumps(request).encode("utf-8"))
        source.seek(0)
        result = job_runner.run(command, folder, None, threading.Event(), stdin=source,
            stderr=subprocess.DEVNULL, seconds=45, cpu_seconds=25, output_limit=output_limit,
            active=32 if print_pdf else 1, memory=(1024 if print_pdf else 384) * 1024 * 1024)
    if result["exit_code"] or result["limited"]:
        raise ValueError("File worker failed or exceeded its resource limits.")
    return json.loads(result["output"])


class FileHub:
    def __init__(self,home):
        self.home=Path(home)
        self.lock=threading.RLock()
        self.pending={}

    def root(self,workspace):
        if not isinstance(workspace,str) or not re.fullmatch(r"default|[a-f0-9]{32}",workspace):
            raise ValueError("Invalid workspace.")
        root=self.home/"files"/workspace
        for directory in (*reversed(root.parents),root):
            safe(directory)
        root.mkdir(parents=True,exist_ok=True)
        return root

    def path(self,root,name):
        return safe(root/filename(name))

    def plan(self,workspace,name,args):
        validate(name,args)
        root=self.root(workspace)
        names=args.get("paths") or ([args["path"]] if "path" in args else [args["id"]] if "id" in args and name!="table_create" else [])
        destination=target(name,args)
        for n in names:
            path=self.path(root,n)
            allowed=(n.lower().endswith(".tsdoc.json") if name.startswith("doc_") else
                     n.lower().endswith(".tstable.json") if name.startswith("table_") else
                     path.suffix.lower()==".pdf" if name.startswith("pdf_") else path.suffix.lower() in EXTS)
            if not allowed or not path.is_file():
                raise ValueError("Choose an existing file of the required type.")
        if destination:
            output=self.path(root,destination)
            if name not in ("doc_edit","table_update") and output.exists():
                raise ValueError("That output exists. Choose a new name.")
            fmt=args.get("format",args.get("target","pdf"))
            if "out" in args and (fmt not in ({"pdf","docx"} if name=="doc_export" else {"csv","xlsx"} if name=="table_export" else {"pdf"} if name.startswith("pdf_") else {"xlsx","pdf","docx"}) or output.suffix.lower()!="."+fmt):
                raise ValueError("Output extension must match the requested format.")
        return {"workspace":workspace,"name":name,"args":args,"target":destination,"inputs":names,
                "hashes":[hashlib.sha256(self.path(root,n).read_bytes()).hexdigest() for n in names]}

    def propose(self,plan):
        with self.lock:
            now=time.monotonic()
            self.pending={k:v for k,v in self.pending.items() if v[0]>now}
            if len(self.pending)>=32:
                raise ValueError("Too many pending approvals.")
            token=secrets.token_urlsafe(24)
            self.pending[token]=(now+60,plan)
            return {"ticket":token,"target":plan["target"],"name":plan["name"],"arguments":plan["args"]}

    def decide(self,token,allow,workspace):
        with self.lock:
            item=self.pending.pop(token,None)
            if not item or item[0]<time.monotonic() or item[1]["workspace"]!=workspace:
                raise ValueError("Approval expired or was already used.")
            return self.execute(item[1]) if allow is True else {"cancelled":True}

    def execute(self,plan):
        with self.lock:
            w,name,args=plan["workspace"],plan["name"],plan["args"]
            if self.plan(w,name,args)!=plan:
                raise ValueError("The input changed. Review the action again.")
            root=self.root(w)
            # A print helper (Edge) may still hold its profile for a moment after the worker's job ends.
            with TemporaryDirectory(dir=root, ignore_cleanup_errors=True) as folder:
                output=Path(folder)/"output" if plan["target"] else None
                ident=secrets.token_hex(8)
                payload={"jsonrpc":"2.0","id":ident,"method":"tools/call","params":{"name":name,"args":args,
                    "inputs":[str(self.path(root,n)) for n in plan["inputs"]],"output":str(output) if output else None}}
                print_pdf = (name in ("doc_export", "convert_file") and
                             args.get("format", args.get("target")) == "pdf")
                reply = run_file_worker(payload, folder, output_limit=5*1024*1024, print_pdf=print_pdf)
                if reply.get("id")!=ident or "error" in reply:
                    raise ValueError(reply.get("error","Invalid worker response."))
                if output:
                    safe(output)
                    if self.plan(w,name,args)!=plan:
                        raise ValueError("The input changed. Review the action again.")
                    dest=self.path(root,plan["target"])
                    if name in ("doc_edit","table_update"):
                        os.replace(output,dest)
                    else:
                        os.rename(output,dest)
                return reply["result"]

