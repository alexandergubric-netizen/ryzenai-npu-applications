"""Local image service adapter and transactional workspace gallery."""
import base64
import http.client
import json
from pathlib import Path
import re
import secrets
import struct
import subprocess
import threading
import time
import zlib

from core.service_peer import ServiceConnection
from core.file_hub import safe
from core.config import image_studio
from core.platform import NO_WINDOW, WINDOWS

PORT=52627
STUDIO=image_studio()
EXE=STUDIO/("bin/sd-server.exe" if WINDOWS else "bin/sd-server")
MODEL=STUDIO/"models/RealVisXL_V5.0_Lightning_fp16.safetensors"
MISSING=("The image engine is not set up on this computer. Images need stable-diffusion.cpp's sd-server in "
         f"{STUDIO/'bin'} and RealVisXL_V5.0_Lightning_fp16.safetensors in {STUDIO/'models'} (see the README).")
# SDXL works best near one megapixel at these shapes ("Standard"); "Draft" is about half the pixels and twice as fast.
SHAPES={"1:1":("1024x1024","768x768"),"4:3":("1152x896","768x576"),"3:4":("896x1152","576x768"),
        "3:2":("1216x832","768x512"),"2:3":("832x1216","512x768"),"16:9":("1344x768","896x512"),
        "9:16":("768x1344","512x896"),"21:9":("1536x640","1024x448")}
SIZES={s for pair in SHAPES.values() for s in pair}|{"512x512"}
WARNING="Image generation uses about 7–8 GB of memory. With Qwen Liberty loaded, memory pressure may be high. Close other heavy apps if needed."
SCHEMA={"name":"image_generate","risk":"write","description":"Generate and save one image in this workspace gallery.",
        "parameters":{"type":"object","properties":{"prompt":{"type":"string","maxLength":2000},
        "size":{"type":"string","enum":sorted(SIZES)}},"required":["prompt","size"],"additionalProperties":False}}

def validate(args):
    if not isinstance(args,dict) or set(args)!={"prompt","size"}:
        raise ValueError("Supply a prompt and image size.")
    if not isinstance(args["prompt"],str) or not 1<=len(args["prompt"].strip())<=2000:
        raise ValueError("Enter a prompt of 1 to 2,000 characters.")
    if not isinstance(args["size"],str) or args["size"] not in SIZES:
        raise ValueError("Choose one of the listed picture shapes and sizes.")

def valid_png(data,size):
    if len(data)>8*1024*1024 or data[:8]!=b"\x89PNG\r\n\x1a\n":
        raise ValueError("Image service returned an invalid PNG.")
    offset=8;has_data=False;first=True;compressed=[];expected=0
    while offset+12<=len(data):
        length=struct.unpack(">I",data[offset:offset+4])[0]
        kind=data[offset+4:offset+8];end=offset+8+length
        if end+4>len(data) or zlib.crc32(data[offset+4:end])&0xffffffff!=struct.unpack(">I",data[end:end+4])[0]:
            raise ValueError("Image service returned a damaged PNG.")
        if first:
            if kind!=b"IHDR" or length!=13 or struct.unpack(">II",data[offset+8:offset+16])!=tuple(map(int,size.split("x"))):
                raise ValueError("Image size did not match the approved request.")
            depth,color,compression,filtering,interlace=struct.unpack("BBBBB",data[offset+16:offset+21])
            if depth!=8 or color not in (2,6) or compression or filtering or interlace:
                raise ValueError("Image service returned an unsupported PNG encoding.")
            width,height=map(int,size.split("x"))
            expected=height*(1+width*(3 if color==2 else 4))
            first=False
        elif kind==b"IHDR":raise ValueError("Duplicate PNG header.")
        if kind==b"IDAT":
            has_data=True;compressed.append(data[offset+8:end])
        if kind==b"acTL":raise ValueError("Animated images are unavailable.")
        if kind==b"IEND":
            if length or end+4!=len(data) or not has_data:raise ValueError("Incomplete PNG.")
            decoder=zlib.decompressobj()
            pixels=decoder.decompress(b"".join(compressed),expected+1)
            if len(pixels)!=expected or not decoder.eof or decoder.unused_data:
                raise ValueError("Image service returned invalid pixel data.")
            return data
        offset=end+4
    raise ValueError("Incomplete PNG.")

class Images:
    def __init__(self,app,port=PORT):
        self.app=app;self.port=port;self.pending={};self.lock=threading.RLock()
        self.owned=None;self.log=None
        with app.store.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS image_jobs(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,
                prompt TEXT NOT NULL,size TEXT NOT NULL,status TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP,
                seconds REAL,error TEXT,content BLOB)""")
            db.execute("UPDATE image_jobs SET status='interrupted',error='The app closed before the result was saved.' WHERE status='generating'")

    def workspace(self,w):
        with self.app.store.connect() as db:
            if not isinstance(w,str) or not db.execute("SELECT id FROM workspaces WHERE id=?",(w,)).fetchone():
                raise ValueError("Unknown workspace.")

    def online(self):
        conn=ServiceConnection(self.port,EXE,timeout=2)
        try:
            conn.request("GET","/v1/models");r=conn.getresponse();raw=r.read(65537)
            return r.status==200 and len(raw)<=65536 and isinstance(json.loads(raw).get("data"),list)
        except (OSError,ValueError,http.client.HTTPException):return False
        finally:conn.close()

    def status(self):
        return {"online":self.online(),"installed":EXE.is_file() and MODEL.is_file(),"owned":bool(self.owned and self.owned.poll() is None),
                "warning":WARNING,"last_observed_model":getattr(self.app.client,"observed_model",None)}

    def prepare(self,w,action,args):
        self.workspace(w)
        if action=="generate":validate(args)
        elif action!="start" or args!={}:raise ValueError("Invalid image action.")
        with self.lock:
            now=time.monotonic();self.pending={k:v for k,v in self.pending.items() if v[0]>now}
            if len(self.pending)>=32:raise ValueError("Too many pending approvals.")
            token=secrets.token_urlsafe(24)
            self.pending[token]=(now+120,w,action,json.loads(json.dumps(args)))
        return {"ticket":token,"action":action,"arguments":args,"warning":WARNING}

    def take(self,w,token,allow):
        with self.lock:item=self.pending.pop(token,None)
        if not item or item[0]<time.monotonic() or item[1]!=w:
            raise ValueError("Approval expired or was already used.")
        return item[2:] if allow is True else None

    def history(self,w):
        self.workspace(w)
        with self.app.store.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,prompt,size,status,created,seconds,error FROM image_jobs WHERE workspace=? ORDER BY rowid DESC LIMIT 100",(w,))]

    def content(self,w,ident):
        self.workspace(w)
        if not isinstance(ident,str) or not re.fullmatch("[a-f0-9]{32}",ident):raise ValueError("Invalid image ID.")
        with self.app.store.connect() as db:
            row=db.execute("SELECT content FROM image_jobs WHERE id=? AND workspace=? AND status='complete'",(ident,w)).fetchone()
        if not row:raise ValueError("Image unavailable in this workspace.")
        return bytes(row[0])

    def start_owned(self):
        if self.online():return {"online":True,"reused":True}
        if self.owned and self.owned.poll() is None:raise ValueError("The owned image service is still starting.")
        # Do not launch a second engine while another user-owned engine is loading.
        if not EXE.is_file() or not MODEL.is_file():raise ValueError(MISSING)
        try:
            probe=(["powershell","-NoProfile","-Command","@(Get-Process -Name sd-server -ErrorAction SilentlyContinue).Count"]
                   if WINDOWS else ["sh","-c","pgrep -x sd-server | wc -l"])
            check=subprocess.run(probe,capture_output=True,text=True,timeout=10,creationflags=NO_WINDOW)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise ValueError("Could not verify image service ownership. Refresh and try again.") from exc
        if check.returncode or check.stdout.strip()!="0":raise ValueError("An image engine is already present. Wait for it to become ready.")
        from vendor.image_studio.launch import arguments
        path=safe(self.app.home/"image-service.log")
        self.log=path.open("ab")
        try:
            self.owned=subprocess.Popen([str(EXE),*arguments(STUDIO,self.port)],cwd=self.app.home,
                stdout=self.log,stderr=self.log,creationflags=NO_WINDOW)
            end=time.monotonic()+90
            while time.monotonic()<end:
                if self.owned.poll() is not None:raise ValueError("The image service could not start. Check its local log.")
                if self.online():return {"online":True,"reused":False}
                time.sleep(.5)
            raise ValueError("Image service startup timed out.")
        except Exception:
            self.stop_owned();raise

    def touch(self):
        """Stop the image engine Tsubasa started after 3 idle minutes, so its ~7 GB go back to the system.
        (It starts again in about a second: measured 1.0-1.1 s to ready, so keeping it loaded longer buys little.)"""
        self.used=time.monotonic()
        if getattr(self,"idle",None) and self.idle.is_alive():return
        def watch():
            while self.owned and self.owned.poll() is None:
                time.sleep(15)
                if time.monotonic()-self.used>180 and not self.app.operation.locked():
                    with self.lock:self.stop_owned()
        self.idle=threading.Thread(target=watch,daemon=True);self.idle.start()

    def stop_owned(self):
        if self.owned:
            if self.owned.poll() is None:self.owned.terminate()
            self.owned.wait(timeout=15);self.owned=None
        if self.log:self.log.close();self.log=None

    def generate(self,w,args,cancelled,emit=lambda *a:None):
        self.workspace(w);validate(args)
        if cancelled.is_set():raise ValueError("Image generation cancelled.")
        if not self.online():raise ValueError("Image service is unavailable. Open Images and start the local service.")
        ident=secrets.token_hex(16);start=time.monotonic()
        with self.app.store.connect() as db:
            db.execute("INSERT INTO image_jobs(id,workspace,prompt,size,status) VALUES(?,?,?,?,'generating')",(ident,w,args["prompt"],args["size"]))
        conn=ServiceConnection(self.port,EXE,timeout=240)
        try:
            emit("status","Generating image… The local service does not report a percentage.")
            conn.request("POST","/v1/images/generations",json.dumps({"model":"sd-cpp-local",**args,"n":1,"response_format":"b64_json"}).encode(),{"Content-Type":"application/json"})
            response=conn.getresponse();raw=response.read(12*1024*1024+1)
            if cancelled.is_set():raise ValueError("Image generation cancelled.")
            if response.status!=200:raise ValueError(f"Image service returned HTTP {response.status}. Try again after checking the service.")
            if len(raw)>12*1024*1024:raise ValueError("Image response exceeds the size limit.")
            payload=json.loads(raw)
            data=payload["data"]
            if not isinstance(data,list) or len(data)!=1 or not isinstance(data[0].get("b64_json"),str):
                raise ValueError("Image service returned no PNG.")
            png=valid_png(base64.b64decode(data[0]["b64_json"],validate=True),args["size"])
            if cancelled.is_set():raise ValueError("Image generation cancelled.")
            elapsed=round(time.monotonic()-start,3)
            with self.app.store.connect() as db:
                db.execute("UPDATE image_jobs SET status='complete',seconds=?,content=? WHERE id=?",(elapsed,png,ident))
            return {"id":ident,"workspace":w,"size":args["size"],"seconds":elapsed}
        except Exception as exc:
            message=str(exc) if isinstance(exc,ValueError) else "Image generation failed. Check the local service and retry."
            with self.app.store.connect() as db:
                db.execute("UPDATE image_jobs SET status=?,error=?,seconds=? WHERE id=?",("cancelled" if cancelled.is_set() else "failed",message,round(time.monotonic()-start,3),ident))
            raise ValueError(message) from exc
        finally:conn.close()

