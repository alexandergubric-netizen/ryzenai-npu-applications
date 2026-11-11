"""Authenticated project terminal endpoints. Every mutation consumes an immutable proposal."""
import re
import subprocess
import threading
import time

from core.terminal import COMMANDS

def catalog():
    from vendor.sensei.recipes import library  # ~0.6 s to load, so only when the catalog is asked for
    phrases=("list files in {folder}","hash of {file}")
    sources=[next((item["source"] for item in library.items if phrase in item["q"]),None) for phrase in phrases]
    return [{"code":COMMANDS[0],"label":"List project files","source":sources[0]},
            {"code":COMMANDS[1],"label":"Read a project file","source":"Tsubasa"},
            {"code":COMMANDS[2],"label":"SHA-256 of a project file","source":sources[1]}]

def handle(handler,body):
    app=handler.app;term=app.terminal
    action=body.get("action");workspace=body.get("workspace")
    start=time.monotonic();acquired=False;ident=None;name="terminal";args={};decision="rejected"
    try:
        term.root(workspace)
        if action=="catalog":
            result=catalog();decision="read"
        elif action=="prepare":
            name=body["name"];args=body["arguments"]
            if name=="fs_read":
                result=term.execute(term.plan(workspace,name,args),threading.Event());decision="read"
            else:
                result=term.prepare(workspace,name,args);decision="proposed"
        elif action=="decide":
            plan=term.take(workspace,body.get("ticket"),body.get("allow"))
            if plan is None:
                decision="denied";return handler.reply(200,{"cancelled":True})
            name,args=plan["name"],plan["arguments"]
            ident=body.get("request_id")
            if not isinstance(ident,str) or not re.fullmatch("[a-f0-9]{32}",ident):raise ValueError("Invalid request ID.")
            if not app.operation.acquire(False):raise ValueError("Another operation is active. Review again when it finishes.")
            acquired=True;event=threading.Event()
            with app.active_lock:app.active[ident]=event
            result=term.execute(plan,event);decision="cancelled" if event.is_set() else "allowed_once"
        else:raise ValueError("Unknown terminal action.")
        return handler.reply(200,{"result":result})
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,subprocess.SubprocessError) as exc:
        return handler.reply(400,{"error":str(exc) if isinstance(exc,(ValueError,RuntimeError)) else "Terminal operation failed. Check the input and project file."})
    finally:
        if acquired:
            with app.active_lock:app.active.pop(ident,None)
            app.operation.release()
        app.tools.audit(name,args,decision,start)

