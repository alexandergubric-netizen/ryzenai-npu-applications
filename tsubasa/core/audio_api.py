"""Authenticated, one-at-a-time transcription with request-scoped cancellation."""
import re
import threading
import time

from core.audio import transcribe

def handle(handler,body):
    app=handler.app
    ident=body.get("request_id")
    if not isinstance(ident,str) or not re.fullmatch(r"[a-f0-9]{32}",ident):
        return handler.reply(400,{"error":"Invalid audio request ID."})
    if not app.operation.acquire(False):
        return handler.reply(409,{"error":"Another Tsubasa operation is running."})
    event=threading.Event()
    with app.active_lock:app.active[ident]=event
    start=time.monotonic()
    args=body.get("arguments");workspace=body.get("workspace")
    decision="failed"
    try:
        with app.store.connect() as db:
            if not db.execute("SELECT id FROM workspaces WHERE id=?",(workspace,)).fetchone():
                raise ValueError("Unknown workspace.")
        output=transcribe(app.tools.files,workspace,args,event,app.client.port)
        decision="read"
        return handler.reply(200,output)
    except (ValueError,TypeError,OSError,RuntimeError) as exc:
        decision="cancelled" if event.is_set() else "failed"
        return handler.reply(400,{"error":str(exc) if isinstance(exc,ValueError) else "Audio service unavailable."})
    finally:
        with app.active_lock:app.active.pop(ident,None)
        app.operation.release()
        app.tools.audit("transcribe",args,decision,start)

