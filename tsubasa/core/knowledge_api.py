"""Authenticated, manual knowledge operations. Indexing shares the foreground lock."""
import hashlib
import secrets
import sqlite3
import threading
import time
from core.knowledge import AREAS,Knowledge,area_name

class KnowledgeActions:
    def __init__(self,app):
        self.app=app
        self.index=Knowledge(app.store,app.tools.files)
        self.pending={}
        self.lock=threading.Lock()

    def proposal(self,w,action,area,names):
        area=area_name(area)
        if not isinstance(names,list) or not 1<=len(names)<=8 or not all(isinstance(n,str) for n in names):
            raise ValueError("Select one to eight sources.")
        if action=="remove":
            records={r["name"]:r["sha"] for r in self.index.inventory(w) if r["area"]==area}
            hashes=[records[n] for n in names]
        else:
            hashes=[hashlib.sha256(self.index.source(w,n).read_bytes()).hexdigest() for n in names]
        return {"workspace":w,"action":action,"area":area,"paths":names,"sha256":hashes}

    def prepare(self,w,action,area,names):
        plan=self.proposal(w,action,area,names)
        with self.lock:
            now=time.monotonic()
            self.pending={k:v for k,v in self.pending.items() if v[0]>now}
            if len(self.pending)>=32:raise ValueError("Too many outstanding requests.")
            token=secrets.token_urlsafe(24)
            self.pending[token]=(now+60,plan)
        return {"ticket":token,"plan":plan}

    def idle(self):
        try:
            npu=self.app.client.get_json("/api/npu/status")
        except ConnectionRefusedError:
            return True  # FLM is offline; lexical indexing uses only the CPU.
        except (OSError,ValueError,RuntimeError):
            return False
        return isinstance(npu,dict) and (npu.get("idle") is True or npu.get("status")=="idle") and not npu.get("busy") and not npu.get("active_requests")

    def decide(self,w,token,allow):
        with self.lock:item=self.pending.pop(token,None)
        if not item or item[0]<time.monotonic() or item[1]["workspace"]!=w:
            raise ValueError("Approval expired or belongs to another workspace.")
        plan=item[1];start=time.monotonic();decision="denied"
        try:
            if allow is not True:return {"cancelled":True}
            if not self.app.operation.acquire(False):
                raise ValueError("Wait for the active chat to finish, then review again.")
            try:
                action,area,names=plan["action"],plan["area"],plan["paths"]
                if self.proposal(w,action,area,names)!=plan:
                    raise ValueError("The source changed. Review again.")
                if action=="kb_add":
                    if not self.idle():raise ValueError("Indexing waits for confirmed idle or offline FLM.")
                    result=self.index.add(w,area,names,expected=dict(zip(names,plan['sha256'])))
                else:
                    if len(names)!=1:raise ValueError("Remove one index entry at a time.")
                    self.index.remove(w,area,names[0]);result={"removed":names[0]}
                decision="allowed_once"
                return result
            finally:self.app.operation.release()
        finally:self.app.tools.audit(plan["action"],plan,decision,start)

    def handle(self,handler,b):
        try:
            w=b["workspace"];action=b["action"]
            with self.app.store.connect() as db:
                if not db.execute("SELECT 1 FROM workspaces WHERE id=?",(w,)).fetchone():raise ValueError("Unknown workspace.")
            if action=="list":
                result={"areas":AREAS,"sources":self.index.inventory(w),"mode":"BM25"}
            elif action=="kb_search":
                result=self.index.search(w,b["area"],b["query"],b.get("k",5))
            elif action in ("kb_add","remove"):
                result=self.prepare(w,action,b["area"],b["paths"])
            elif action=="decide":
                result=self.decide(w,b["ticket"],b["allow"])
            else:raise ValueError("Unknown knowledge operation.")
            return handler.reply(200,{"result":result})
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as e:
            return handler.reply(400,{"error":str(e) if isinstance(e,ValueError) else "Knowledge operation failed. Check the source and area."})

