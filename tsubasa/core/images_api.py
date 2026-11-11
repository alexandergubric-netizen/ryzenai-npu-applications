"""Image approvals and authenticated workspace gallery routes."""
import re
import threading
import time
from urllib.parse import parse_qs,urlsplit

def get(handler):
    q=parse_qs(urlsplit(handler.path).query)
    try:
        data=handler.app.images.content(q.get("workspace",[""])[0],q.get("id",[""])[0])
        handler.send_response(200)
        handler.send_header("Content-Type","image/png")
        handler.send_header("Content-Length",str(len(data)))
        if q.get("download")==["1"]:handler.send_header("Content-Disposition",'attachment; filename="tsubasa-image.png"')
        handler.end_headers();handler.wfile.write(data)
    except (ValueError,TypeError):
        handler.reply(404,{"error":"Image unavailable."})

def handle(handler,body):
    app=handler.app;images=app.images
    start=time.monotonic();decision="read";label="images";args=body
    acquired=False;ident=None
    try:
        w=body.get("workspace","default");images.workspace(w)
        action=body.get("action")
        if action=="status":result=images.status()
        elif action=="list":result=images.history(w)
        elif action in ("prepare_generate","prepare_start"):
            operation="generate" if action=="prepare_generate" else "start"
            result=images.prepare(w,operation,body.get("arguments",{}));decision="proposed"
        elif action=="decide":
            taken=images.take(w,body.get("ticket"),body.get("allow"))
            if taken is None:
                decision="denied";return handler.reply(200,{"cancelled":True})
            ident=body.get("request_id")
            if not isinstance(ident,str) or not re.fullmatch("[a-f0-9]{32}",ident):raise ValueError("Invalid request ID.")
            if not app.operation.acquire(False):raise ValueError("Another Tsubasa operation is running. Review the action again when it finishes.")
            acquired=True;event=threading.Event()
            with app.active_lock:app.active[ident]=event
            operation,args=taken;label="image_generate" if operation=="generate" else "image_start"
            decision="allowed_once"
            result=images.generate(w,args,event) if operation=="generate" else images.start_owned()
        else:raise ValueError("Unknown image action.")
        return handler.reply(200,{"result":result})
    except (ValueError,TypeError,KeyError,OSError) as exc:
        decision="failed"
        return handler.reply(400,{"error":str(exc) if isinstance(exc,ValueError) else "Image action failed."})
    finally:
        if acquired:
            with app.active_lock:app.active.pop(ident,None)
            app.operation.release()
        app.tools.audit(label,args,decision,start)

