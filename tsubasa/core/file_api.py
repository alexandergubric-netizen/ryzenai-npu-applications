"""Authenticated file endpoints. The launch gate runs before dispatch."""
import os
from pathlib import Path
import subprocess
import time
from core.audio import FORMATS
from core.file_catalog import CAT, EXTS
from core.file_hub import LIMIT
from core.extract import SUPPORTED

def handle(handler, body, upload=None):
    tools=handler.app.tools
    hub=tools.files
    w=body.get("workspace","default")
    action=body.get("action")
    start=time.monotonic()
    label="file_"+str(action) if action in ("list","decide","run","draft","open","import","download") else "file_invalid"
    decision="read"
    audit_args=body
    try:
        with tools.store.connect() as db:
            if not db.execute("SELECT 1 FROM workspaces WHERE id=?",(w,)).fetchone():
                raise ValueError("Unknown workspace.")
        root=hub.root(w)
        if action=="list":
            result=sorted(p.name for p in root.iterdir() if p.is_file() and hub.path(root,p.name))
        elif action=="decide":
            with hub.lock:
                pending=hub.pending.get(body["ticket"])
                if pending:
                    label=pending[1]["name"]
                    audit_args=pending[1]["args"]
                result=hub.decide(body["ticket"],body["allow"],w)
            decision="allowed_once" if body["allow"] is True else "denied"
        elif action=="run":
            plan=hub.plan(w,body["name"],body["args"])
            label=plan["name"]
            audit_args=plan["args"]
            decision="proposed" if CAT[label][0]=="write" else "read"
            result=hub.propose(plan) if CAT[plan["name"]][0]=="write" else hub.execute(plan)
        else:
            path=hub.path(root,body["name"])
            if action=="import" and upload is not None:
                if path.suffix.lower() not in EXTS.union(FORMATS,SUPPORTED):
                    raise ValueError("Tsubasa cannot read "+(path.suffix or "files without an extension")+" files. It reads documents (PDF, Word, PowerPoint, Excel, OpenDocument, EPUB, RTF), text, code, data, e-mails, pictures, audio and video.")
                if len(upload)>LIMIT:
                    raise ValueError("Files can be up to 8 MB.")
                with hub.lock:
                    with path.open("xb") as stream:
                        try:
                            stream.write(upload)
                        except OSError:
                            stream.close()
                            path.unlink()
                            raise
                result={"saved":path.name}
                decision="user_import"
            elif action=="draft" and path.name.endswith((".tsdoc.json",".tstable.json")):
                import json
                result=json.loads(path.read_text(encoding="utf-8"))
            elif action=="download" and path.suffix.lower() in EXTS:
                from urllib.parse import quote
                data=path.read_bytes()
                tools.audit(label,body,"read",start)
                handler.send_response(200)
                handler.send_header("Content-Type","application/octet-stream")
                handler.send_header("Content-Disposition","attachment; filename*=UTF-8''"+quote(path.name))
                handler.send_header("Content-Length",str(len(data)))
                handler.end_headers()
                handler.wfile.write(data)
                return
            elif action=="open" and path.is_file() and path.suffix.lower()==".pdf" and body.get("confirmed") is True:
                exe=Path(os.environ.get("LOCALAPPDATA",""))/"Programs/Washi/Washi.exe"
                if not exe.is_file():
                    raise ValueError("Washi is unavailable.")
                subprocess.Popen([str(exe),str(path)])
                result={"opened":True}
                decision="user_open"
            else:
                raise ValueError("Unknown file action.")
        tools.audit(label,audit_args,decision,start)
        return handler.reply(200,{"result":result})
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as error:
        tools.audit(label,audit_args,"rejected",start)
        return handler.reply(400,{"error":str(error) if isinstance(error,ValueError) else "File action failed. Check the selection and output name."})

