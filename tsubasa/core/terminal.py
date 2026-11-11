"""Restricted terminal broker. User code never reaches a host interpreter as executable code."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time

from core.file_catalog import filename
from core.file_hub import ROOT,safe
from core.terminal_paths import exact_handle,read_file
from core import job_runner
from tools.expression_worker import parse_expression

PS=Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
COMMANDS=("Get-ChildItem -File","Get-Content -LiteralPath 'notes.txt'","Get-FileHash -LiteralPath 'notes.txt' -Algorithm SHA256")
SCHEMAS={
 "ps_run":("run","Run one of the reviewed project-only PowerShell commands.",{"code":{"type":"string"}}),
 "py_run":("run","Evaluate a restricted Python expression. No imports, attributes or file/network/process access.",{"code":{"type":"string"}}),
 "fs_read":("read","Read a UTF-8 file in this terminal project.",{"path":{"type":"string"}}),
 "fs_write":("write","Write a project text file after reviewing its exact diff.",{"path":{"type":"string"},"content":{"type":"string"}})}

def validate(name,args):
    if name not in SCHEMAS or not isinstance(args,dict) or set(args)!=set(SCHEMAS[name][2]):
        raise ValueError("Invalid terminal operation.")
    if not all(isinstance(v,str) for v in args.values()):raise ValueError("Use text arguments.")
    if "path" in args:filename(args["path"])
    if "content" in args and len(args["content"].encode())>16000:raise ValueError("Use up to 16,000 UTF-8 bytes.")
    if "code" in args and not 1<=len(args["code"])<=4000:raise ValueError("Use code up to 4,000 characters.")
    if name=="py_run":
        try:parse_expression(args["code"])
        except (SyntaxError,TypeError,ZeroDivisionError,OverflowError) as exc:
            raise ValueError("Invalid restricted expression.") from exc
    if name=="ps_run":parse_ps(args["code"])

def parse_ps(code):
    if code=="Get-ChildItem -File":return "list",None
    match=re.fullmatch(r"Get-(Content|FileHash) -LiteralPath '([^']+)'( -Algorithm SHA256)?",code)
    if not match or bool(match[3])!=(match[1]=="FileHash"):
        raise ValueError("Choose a reviewed PowerShell command from the template list.")
    return ("read" if match[1]=="Content" else "hash"),filename(match[2])

class Terminal:
    def __init__(self,app):
        self.app=app;self.lock=threading.RLock();self.pending={}
    def root(self,w):
        with self.app.store.connect() as db:
            if not isinstance(w,str) or not db.execute("SELECT id FROM workspaces WHERE id=?",(w,)).fetchone():raise ValueError("Unknown workspace.")
        if not re.fullmatch("default|[a-f0-9]{32}",w):raise ValueError("Invalid project.")
        root=self.app.home/"tsubasa-work"/w
        for p in (*reversed(root.parents),root):safe(p)
        with exact_handle(self.app.home,directory=True):
            root.parent.mkdir(exist_ok=True)
            with exact_handle(root.parent,directory=True):root.mkdir(exist_ok=True)
        return root
    def file(self,root,name):
        path=safe(root/filename(name))
        if path.exists() and (not path.is_file() or path.stat().st_size>16000):raise ValueError("Choose a text file up to 16,000 bytes.")
        return path
    def plan(self,w,name,args):
        validate(name,args);root=self.root(w);old=None;target=args.get("path")
        if name=="ps_run":
            _,target=parse_ps(args["code"])
            if target is None:
                for p in root.iterdir():
                    if p.is_symlink() or p.is_junction():raise ValueError("Remove linked entries before listing this project.")
        if target:
            path=self.file(root,target)
            if path.exists():old=read_file(path)
            elif name!="fs_write":raise ValueError("Project file does not exist.")
        diff=""
        if name=="fs_write":
            before=old.decode("utf-8") if old is not None else ""
            changes=difflib.unified_diff(before.splitlines(keepends=True),args["content"].splitlines(keepends=True),
                fromfile=target+" (current)",tofile=target+" (proposed)")
            diff="".join(line if line.endswith("\n") else line+"\n[no final newline]\n" for line in changes)
            if not diff:diff="Create empty file." if old is None else "Contents already match."
        return {"workspace":w,"name":name,"arguments":json.loads(json.dumps(args)),"target":target,
                "revision":hashlib.sha256(old).hexdigest() if old is not None else None,"diff":diff}
    def prepare(self,w,name,args):
        plan=self.plan(w,name,args)
        with self.lock:
            now=time.monotonic();self.pending={k:v for k,v in self.pending.items() if v[0]>now}
            if len(self.pending)>=32:raise ValueError("Too many pending approvals.")
            ticket=secrets.token_urlsafe(24);self.pending[ticket]=(now+120,plan)
        return {"ticket":ticket,**plan}
    def take(self,w,ticket,allow):
        with self.lock:item=self.pending.pop(ticket,None)
        if not item or item[0]<time.monotonic() or item[1]["workspace"]!=w:raise ValueError("Approval expired or already used.")
        return item[1] if allow is True else None
    def environment(self,root):
        base=Path("C:/Windows")
        return {"SystemRoot":str(base),"WINDIR":str(base),"PATH":str(base/"System32"),
                "TEMP":str(root),"TMP":str(root),"PSModulePath":str(base/"System32/WindowsPowerShell/v1.0/Modules")}
    def check_ps(self,codes,folder,event):
        source=folder/"verify.json"
        source.write_text(json.dumps(codes),encoding="utf8")
        command=[str(PS),"-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(ROOT/"tools/sensei_check.ps1"),str(source)]
        result=job_runner.run(command,folder,self.environment(folder),event)
        if result["exit_code"] or result["limited"]:
            raise ValueError(result["limited"] or "The copied Sensei checker could not verify this command.")
        return json.loads(result["output"])
    def runtime(self,w):
        base=safe(self.app.home/"terminal-runtime")
        with exact_handle(self.app.home,directory=True):
            base.mkdir(exist_ok=True)
            with exact_handle(base,directory=True):
                root=safe(base/w);root.mkdir(exist_ok=True)
        return root
    def python(self,root):
        env=safe(root/"environment")
        if not env.exists():
            with tempfile.TemporaryDirectory(dir=root) as staging:
                candidate=Path(staging)/"environment"
                try:
                    subprocess.run([sys.executable,"-I","-B","-m","venv","--without-pip",str(candidate)],check=True,timeout=30,
                        capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
                except (subprocess.CalledProcessError,subprocess.TimeoutExpired,OSError):
                    # The bundled runtime of an installed copy has no venv module: the restricted evaluator
                    # (-I -S, no imports) then runs on the app's own interpreter.
                    return Path(sys.executable)
                os.rename(candidate,env)
        for p in (env,env/"pyvenv.cfg",env/"Scripts",env/"Scripts/python.exe"):
            safe(p)
            if not p.exists():raise ValueError("The project runtime is incomplete.")
        return env/"Scripts/python.exe"
    def execute(self,plan,event):
        w,name,args=plan["workspace"],plan["name"],plan["arguments"]
        with self.lock,exact_handle(self.root(w),directory=True):
            if self.plan(w,name,args)!=plan:raise ValueError("The project file changed. Review the action again.")
            if event.is_set():raise ValueError("Cancelled.")
            root=self.root(w)
            if name=="fs_read":return {"output":read_file(self.file(root,args["path"])).decode("utf-8")}
            if name=="fs_write":
                with tempfile.TemporaryDirectory(dir=root) as temp:
                    stage=Path(temp)/"write.txt";stage.write_text(args["content"],encoding="utf-8",newline="")
                    if self.plan(w,name,args)!=plan:raise ValueError("The file changed. Review again.")
                    target=self.file(root,args["path"])
                    if plan["revision"] is None:os.rename(stage,target)
                    else:os.replace(stage,target)
                return {"output":"Saved "+args["path"]}
            if __import__("core.platform").platform.is_admin():raise ValueError("Run Tsubasa without administrator privileges.")
            runtime=self.runtime(w)
            with exact_handle(runtime,directory=True),tempfile.TemporaryDirectory(dir=runtime) as temp:
                folder=Path(temp)
                if name=="py_run":
                    exe=self.python(runtime);source=folder/"expression.txt";source.write_text(args["code"],encoding="utf-8")
                    command=[str(exe),"-I","-S","-B",str(ROOT/"tools/expression_worker.py"),str(source)]
                    return job_runner.run(command,folder,self.environment(folder),event,active=2)
                checks=self.check_ps([args["code"]],folder,event)
                if len(checks)!=1 or checks[0]["risk"]!="safe" or checks[0]["problems"] or checks[0]["syntax"]:
                    raise ValueError("The copied Sensei checker rejected this command.")
                action,target=parse_ps(args["code"])
                work=folder/"snapshot";work.mkdir()
                if target:
                    snapshot = read_file(self.file(root, target))
                    if hashlib.sha256(snapshot).hexdigest() != plan["revision"]:
                        raise ValueError("The project file changed. Review again.")
                    (work / "input.txt").write_bytes(snapshot)
                if action=="list":
                    # Pass bounded metadata to the trusted command without traversing any child directory.
                    entries=[]
                    for entry in root.iterdir():
                        safe(entry)
                        if entry.is_file():
                            entries.append({"Name":entry.name,"Length":entry.stat().st_size})
                        if len(entries)>256:raise ValueError("Project listing exceeds 256 files.")
                    (work/"listing.json").write_text(json.dumps(entries),encoding="utf-8-sig")
                    script="Microsoft.PowerShell.Management\\Get-Content -Raw -Encoding UTF8 -LiteralPath listing.json"
                elif action=="read":
                    script="Microsoft.PowerShell.Management\\Get-Content -Raw -Encoding UTF8 -LiteralPath 'input.txt'"
                else:
                    script="Microsoft.PowerShell.Utility\\Get-FileHash -Algorithm SHA256 -LiteralPath 'input.txt' | Microsoft.PowerShell.Utility\\Select-Object Hash | Microsoft.PowerShell.Utility\\ConvertTo-Json -Compress"
                script="[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"+script
                return job_runner.run([str(PS),"-NoProfile","-NonInteractive","-Command",script],
                    work,self.environment(folder),event)

