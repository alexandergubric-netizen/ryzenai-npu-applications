"""Phase 0 loopback server; run with the project venv. No automatic FLM startup."""
import argparse
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))   # the bundled (isolated) Python does not add the script folder
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from core.config import APP_NAME, ROOT, DATA_HOME, DEFAULT_MODEL, TERMINAL_MODEL, VERSION, ENGINE, pick_model
from core.platform import MAC, WINDOWS, NO_WINDOW, window_browsers
from core.client import Client, BusyError
from core.storage import Store
from core.tool_loop import ToolLoop
from core.knowledge_api import KnowledgeActions
from core import knowledge_chat
from core.terminal import Terminal
from core import terminal_api
from core.images import Images
from core import images_api
from core import audio_api
from core import file_api
from core import modes_api
from core import cad_api
from core.library import Library
from core import extract
from core.agent import Agent
from urllib.parse import parse_qs
import sqlite3
from vendor.washi.websec import Gate

CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"

def models_info(client):
    """Installed chat models plus what the page needs to label them on this platform."""
    models = client.models()
    return {'models':models,'default':pick_model(models,DEFAULT_MODEL) or DEFAULT_MODEL,
            'terminal':pick_model(models,TERMINAL_MODEL,DEFAULT_MODEL) or TERMINAL_MODEL,
            'engine':getattr(client,'kind','flm'),'engine_label':getattr(client,'label','FastFlowLM'),
            'platform':'mac' if MAC else 'windows' if WINDOWS else 'other','version':VERSION,
            'suggested':getattr(client,'suggested',lambda:[])()}

class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False
    def __init__(self, *args, **kwargs):
        self.request_slots = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self.request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.request_slots.release()

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()

def make_client():
    if ENGINE == 'mlx':
        from core.mlx_client import MlxClient
        return MlxClient()
    return Client()

class App:
    def __init__(self, home=DATA_HOME, port=52698, client=None):
        self.home = Path(home)
        self.client = client or make_client()
        self.store = None
        self.gate = Gate(APP_NAME,str(home),'X-Tsubasa',port,max_body=32768)
        self.active, self.active_lock = {}, threading.Lock()
        self.operation = threading.Lock()
        self.server = None
        self._sensei = None
        self.last_seen = time.monotonic()
    def bind(self):
        # Preserve vendor websec unchanged; implement the brief's next-free-port policy here.
        for port in range(self.gate.preferred_port,self.gate.preferred_port+100):
            try:
                self.server = LocalServer(('127.0.0.1',port),Handler)
                break
            except OSError as exc:
                if getattr(exc,'winerror',None) not in (10048,10013) and exc.errno not in (98,13): raise
        if not self.server: raise RuntimeError('No free application port in the allowed range.')
        self.store = Store(self.home)
        self.tools = ToolLoop(self.store,self.home)
        self.knowledge = KnowledgeActions(self)
        self.images = Images(self)
        self.tools.images = self.images
        self.terminal=Terminal(self)
        self.tools.terminal=self.terminal
        self.library=Library(self.home)
        self.agent=Agent(self)
        self.server.app = self
        self.gate.port = self.server.server_address[1]
        self.gate.publish()
        return self.server
    @property
    def sensei(self):
        # Terminal mode's Sensei pipeline; its 541-task library loads on first use (~0.6 s), not at app start.
        with self.active_lock:
            if self._sensei is None:
                if WINDOWS: from core.sensei_term import Sensei
                else: from core.posix_term import Sensei
                self._sensei = Sensei(self.client)
            return self._sensei
    def close(self):
        if self._sensei is not None: self._sensei.shell.shutdown()
        if hasattr(self,"images"): self.images.stop_owned()
        self.client.detach()
        self.gate.withdraw()
        if self.server: self.server.server_close()

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    server_version = APP_NAME
    def setup(self):
        super().setup()
        self.connection.settimeout(15)
    @property
    def app(self): return self.server.app
    def log_message(self,*args): pass  # launch keys and prompts must not enter logs
    def end_headers(self):
        self.app.gate.add_headers(self)
        self.send_header('Content-Security-Policy',CSP)
        self.send_header('Cache-Control','no-store')
        super().end_headers()
    def reply(self,code,data,kind='application/json; charset=utf-8'):
        body = json.dumps(data).encode() if not isinstance(data,bytes) else data
        self.send_response(code)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if not self.app.gate.get_allowed(self): return
        path = urlsplit(self.path).path
        files = {'/':('index.html','text/html; charset=utf-8'),
                 '/app.js':('app.js','text/javascript; charset=utf-8'),
                 '/markdown.js':('markdown.js','text/javascript; charset=utf-8'),
                 '/bird.svg':('bird.svg','image/svg+xml'),
                 '/mark.svg':('mark.svg','image/svg+xml'),
                 '/tsubasa.ico':('tsubasa.ico','image/x-icon'),
                 '/app.css':('app.css','text/css; charset=utf-8'),
                 '/theme.css':('theme.css','text/css; charset=utf-8'),
                 '/shell.js':('shell.js','text/javascript; charset=utf-8'),
                 '/modes.js':('modes.js','text/javascript; charset=utf-8'),
                 '/fonts/tsubasa-bitmap.ttf':('fonts/tsubasa-bitmap.ttf','font/ttf'),
                 '/cad.js':('cad.js','text/javascript; charset=utf-8')}
        files.update({'/terminal':('terminal.html','text/html; charset=utf-8'),'/terminal.js':('terminal.js','text/javascript; charset=utf-8'),'/images':('images.html','text/html; charset=utf-8'),'/images.js':('images.js','text/javascript; charset=utf-8'),'/audio':('audio.html','text/html; charset=utf-8'),'/audio.js':('audio.js','text/javascript; charset=utf-8'),'/knowledge':('knowledge.html','text/html; charset=utf-8'),'/knowledge.js':('knowledge.js','text/javascript; charset=utf-8'),'/files.css':('files.css','text/css; charset=utf-8'),'/docs':('files.html','text/html; charset=utf-8'),'/tables':('files.html','text/html; charset=utf-8'),'/files.js':('files.js','text/javascript; charset=utf-8')})
        if path in files:
            name,kind = files[path]
            raw = (ROOT/'web'/name).read_bytes().replace(b'__APP_NAME__',APP_NAME.encode())
            return self.reply(200,raw,kind)
        try:
            if path == '/api/image': return images_api.get(self)
            if path == '/api/cad-file': return cad_api.download(self,parse_qs(urlsplit(self.path).query))
            if path == '/api/state': return self.reply(200,self.app.store.state())
            if path.startswith('/api/chats/'):
                return self.reply(200,self.app.store.chat(path.rsplit('/',1)[1]))
            if path == '/api/models': return self.reply(200,models_info(self.app.client))
            if path == '/api/status': return self.reply(200,self.app.client.status())
        except Exception:
            return self.reply(503,{'error':'Could not read the local AI service. Try Refresh.'})
        self.reply(404,{'error':'Not found'})
    def do_POST(self):
        path = urlsplit(self.path).path
        gate = self.app.gate
        # Validate framing before the unchanged vendor launch handler reads a body.
        lengths = self.headers.get_all('Content-Length',[])
        try: n = int(lengths[0]) if len(lengths) == 1 else -1
        except ValueError: n = -1
        if self.headers.get('Transfer-Encoding') or not 0 <= n <= (8388608 if path=='/api/files/import' else 131072 if path=='/api/cad' else 32768):
            self.close_connection = True
            return self.reply(400,{'error':'Invalid request size or framing.'})
        if path == '/api/launch':
            if not gate.host_ok(self) or not gate.site_ok(self) or not gate.secret_ok(self):
                return gate._deny(self,True)
            try:
                launch = json.loads(self.rfile.read(n))
                if not isinstance(launch,dict) or set(launch)-{'args'} or launch.get('args',[]) != []: raise ValueError()
            except (ValueError,UnicodeError): return self.reply(400,{'error':'Invalid launch request.'})
            self.app.last_seen = time.monotonic()
            return self.reply(200,{'app':APP_NAME,'key':gate.new_launch_key(),'port':gate.port})
        if path=='/api/files/import':
            if not gate.post_allowed(self,max_body=8388608): return
            args={k:v[0] for k,v in parse_qs(urlsplit(self.path).query).items()}
            args['action']='import'
            return file_api.handle(self,args,self.rfile.read(n))
        if not gate.post_allowed(self,max_body=131072 if path=='/api/cad' else None): return
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            return self.reply(415,{'error':'Use application/json.'})
        try:
            body = json.loads(self.rfile.read(n))
            if not isinstance(body,dict): raise ValueError()
        except (ValueError,UnicodeError): return self.reply(400,{'error':'Invalid JSON object.'})
        if path == '/api/terminal': return terminal_api.handle(self,body)
        if path == '/api/terminal-ai': return modes_api.terminal(self,body)
        if path == '/api/agent': return modes_api.agent(self,body)
        if path == '/api/cad': return cad_api.handle(self,body)
        if path == '/api/agent-decision': return modes_api.agent_decision(self,body)
        if path == '/api/library': return modes_api.library(self,body)
        if path == '/api/pick': return modes_api.pick(self,body)
        if path == '/api/images-create': return modes_api.images(self,body)
        if path == '/api/images': return images_api.handle(self,body)
        if path == '/api/audio': return audio_api.handle(self,body)
        if path == '/api/knowledge': return self.app.knowledge.handle(self,body)
        if path == '/api/files': return file_api.handle(self,body)
        if path == '/api/store':
            if self.app.operation.locked(): return self.reply(409,{'error':'Wait for the current answer to finish.'})
            try:
                if body.get('action') in ('chat','options'): self.app.client.require_model(body.get('model'))
                return self.reply(200,self.app.store.mutate(body))
            except (ValueError,KeyError,TypeError,sqlite3.Error): return self.reply(400,{'error':'Could not save. Check the selected chat, workspace and settings.'})
        if path == '/api/tool-decision':
            ok=self.app.tools.tickets.decide(body.get('ticket'),body.get('request_id'),body.get('allow'))
            return self.reply(200 if ok else 409,{'ok':True} if ok else {'error':'Approval expired or already used.'})
        if path == '/api/engine':
            # Only on the user's click in Settings > Engine; Tsubasa never starts or stops the engine by itself.
            action=body.get('action')
            if action not in ('start','stop','download'): return self.reply(400,{'error':'Choose start or stop.'})
            if self.app.operation.locked(): return self.reply(409,{'error':'Wait for the current answer to finish.'})
            try:
                if action=='start': return self.reply(200,{'started':True,'model':self.app.client.start_engine(body.get('model'))})
                if action=='download': return self.reply(200,self.app.client.download(body.get('model')))
                self.app.client.stop_engine()
                return self.reply(200,{'stopped':True})
            except ValueError as exc: return self.reply(400,{'error':str(exc)})
            except Exception: return self.reply(503,{'error':'The engine did not respond to that. Try again in a moment.'})
        if path == '/api/warm':
            # Preload the model of the mode you switched to; a no-op when it is already loaded or Tsubasa is busy.
            try:
                if self.app.operation.locked(): return self.reply(200,{'started':False,'reason':'busy'})
                return self.reply(200,{'started':self.app.client.warm(body.get('model')),'model':body.get('model')})
            except ValueError as exc: return self.reply(400,{'error':str(exc)})
            except Exception: return self.reply(503,{'error':'Installed model list is unavailable.'})
        if path == '/api/ping':
            self.app.last_seen = time.monotonic()
            return self.reply(200,{'ok':True})
        if path == '/api/close':
            if self.app.operation.locked(): return self.reply(409,{'error':'Wait for the current generation to finish.'})
            self.reply(200,{'ok':True})
            threading.Thread(target=self.app.server.shutdown,daemon=True).start()
            return
        if path == '/api/cancel':
            request_id = body.get('request_id')
            if not isinstance(request_id,str): return self.reply(400,{'error':'Invalid request id.'})
            with self.app.active_lock:
                event = self.app.active.get(request_id)
                if event: event.set()
            return self.reply(200,{'cancelled':bool(event),'note':'Stopped; Tsubasa closed its own engine request.'})
        if path not in ('/api/chat','/api/switch'): return self.reply(404,{'error':'Not found'})
        try:
            model = body.get('model')
            if not isinstance(model,str): raise ValueError('Select a model.')
            self.app.client.require_model(model)
            if body.get('confirmed') is not True:
                return self.reply(409,{'error':'Confirm use of the shared model before sending.'})
            message = body.get('message','')
            if path == '/api/chat' and (not isinstance(message,str) or not message.strip() or len(message)>12000):
                raise ValueError('Enter a message of 1–12,000 characters.')
        except ValueError as exc: return self.reply(400,{'error':str(exc)})
        except Exception: return self.reply(503,{'error':'Installed model list is unavailable.'})
        if not self.app.operation.acquire(False): return self.reply(409,{'error':'Wait for the current request to finish.'})
        request_id, cancelled = secrets.token_hex(12),threading.Event()
        with self.app.active_lock: self.app.active[request_id] = cancelled
        started, first, usage = time.perf_counter(),None,{}
        disconnected = False
        saved_id=None; answer_parts=[]; thinking_parts=[]; final_state="interrupted"
        def emit(kind,data):
            nonlocal disconnected
            if disconnected: return
            try:
                self.wfile.write(('data: '+json.dumps({'type':kind,'data':data})+'\n\n').encode())
                self.wfile.flush()
            except OSError:
                disconnected = True
                cancelled.set()
        try:
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream; charset=utf-8')
            self.send_header('Connection','close')
            self.end_headers()
            emit('start',{'request_id':request_id})
            switching = path == '/api/switch'
            emit('status','Loading selected model…' if switching else 'Waiting for the first answer text…')
            messages = [{'role':'system','content':f'You are {APP_NAME}, a private offline assistant. Be brief and concrete.'},
                        {'role':'user','content':'Reply with OK.' if switching else message.strip()}]
            options={}
            if not switching and body.get('chat_id'):
                cid=body['chat_id']
                messages=self.app.store.context(cid,message.strip())
                if body.get('library') is True:
                    extra,used=self.app.library.context(message)
                    messages[0]['content']+=extra
                    if used: emit('library',used)
                # Files attached in this chat go into the message as data (pictures only to models that see them).
                if any(m['role']=='user' and extract.HINT.search(m['content']) for m in messages if isinstance(m.get('content'),str)):
                    with self.app.store.connect() as db:
                        chat_ws=db.execute('SELECT workspace FROM chats WHERE id=?',(cid,)).fetchone()[0]
                    vision=any(m.get('id')==model and m.get('supports_vision') for m in self.app.client.models())
                    messages,notes=extract.attach(messages,self.app.tools.files.root(chat_ws),vision)
                    if notes: emit('attach_notes',notes)
                with self.app.store.connect() as db:
                    options['think']=bool(db.execute('SELECT think FROM chats WHERE id=?',(cid,)).fetchone()[0])
                saved_id=self.app.store.begin(cid,message.strip())
            if not switching and saved_id and body.get('knowledge_tools') is True:
                with self.app.store.connect() as db:
                    workspace=db.execute('SELECT workspace FROM chats WHERE id=?',(cid,)).fetchone()[0]
                stream=knowledge_chat.stream(self.app,model,messages,workspace,body.get('knowledge_area','coding'),emit,cancelled,options)
            elif not switching and saved_id and (body.get('practice_tools') is True or body.get('file_tools') is True or body.get('terminal_tools') is True):
                with self.app.store.connect() as db:
                    workspace=db.execute('SELECT workspace FROM chats WHERE id=?',(cid,)).fetchone()[0]
                stream=self.app.tools.stream(self.app.client,model,messages,workspace=workspace,turn=request_id,
                                             emit=emit,cancelled=cancelled,file_tools=body.get('file_tools') is True,terminal_tools=body.get('terminal_tools') is True,max_tokens=2048,**options)
            else:
                stream=self.app.client.stream(model,messages,max_tokens=1 if switching else 2048,cancelled=cancelled,**options)
            for kind,value in stream:
                if kind == 'usage': usage = value
                elif not switching and not cancelled.is_set():
                    if kind == 'text' and value.strip() and first is None: first = time.perf_counter()-started
                    emit(kind,value)
                    if kind=='text': answer_parts.append(value)
                    if kind=='thinking': thinking_parts.append(value)
            final_state='stopped' if cancelled.is_set() else 'complete'
            if saved_id:
                self.app.store.finish(saved_id,''.join(answer_parts),''.join(thinking_parts),final_state)
                saved_id=None
            emit('done',{'cancelled':cancelled.is_set(),'first_text_seconds':first,
                         'total_seconds':time.perf_counter()-started,'usage':usage,'model':model})
        except Exception as exc:
            emit('error',str(exc) if isinstance(exc,(ValueError,RuntimeError)) else 'Local AI connection failed. Check that the engine is running (Settings → Engine), then retry.')
        finally:
            if saved_id:
                try: self.app.store.finish(saved_id,''.join(answer_parts),''.join(thinking_parts),final_state)
                except sqlite3.Error: pass
            with self.app.active_lock: self.app.active.pop(request_id,None)
            self.app.operation.release()
            self.close_connection = True

_instance = None
def first_instance(home):
    """One server per data home: a double-clicked shortcut must not start a second server on the next port.
    Windows: a named mutex. macOS: an exclusive lock on a file in the data home. Held until this process exits."""
    global _instance
    if os.name == 'nt':
        import ctypes, hashlib
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        name = 'Local\\Tsubasa-'+hashlib.sha256(str(Path(home).resolve()).lower().encode()).hexdigest()[:16]
        _instance = kernel.CreateMutexW(None,False,name)
        return bool(_instance) and ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
    import fcntl
    Path(home).mkdir(parents=True,exist_ok=True)
    _instance = open(Path(home)/'instance.lock','w')
    try: fcntl.flock(_instance,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError: return False
    return True

def open_window(url, profile, first):
    """The app window: a Chromium-family browser in --app mode with Tsubasa's own profile; else the default browser."""
    for exe in window_browsers():
        if exe.is_file():
            if first: tidy_window(profile)
            subprocess.Popen([str(exe),'--app='+url,'--user-data-dir='+str(profile),*EDGE_FLAGS],creationflags=NO_WINDOW)
            return True
    if MAC:
        subprocess.Popen(['/usr/bin/open',url])
        return True
    return False

# The window is a local page: no extensions, no syncing, and no background downloads. Edge's component updater
# had filled the window profile with ~450 MB (DRM, Wallet, "provenance" and entity-extraction models) that slowed
# every start.
EDGE_FLAGS = ['--no-first-run','--no-default-browser-check','--disable-extensions','--disable-component-update',
              '--disable-background-networking','--disable-sync','--disable-default-apps','--no-pings']
STALE_COMPONENTS = ('component_crx_cache','ProvenanceData','Edge Entity Extraction','Edge Wallet','WidevineCdm',
                    'BrowserMetrics','Subresource Filter','Edge Shopping','Trust Protection Lists')
def tidy_window(profile):
    """Remove downloaded browser components from Tsubasa's own window profile, only while no window uses it."""
    import shutil
    lock = profile/'lockfile'
    try:
        if lock.exists(): lock.unlink()   # Edge keeps this file open while a window runs, so this fails then
    except OSError:
        return
    for name in STALE_COMPONENTS:
        target = profile/name
        if target.is_dir() and not target.is_symlink() and not target.is_junction():
            shutil.rmtree(target, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description=f'{APP_NAME} {VERSION}')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--start-engine',action='store_true',help='start the AI engine if it is not running (installed copies)')
    args = parser.parse_args()
    app = App()
    # A second launch asks the authenticated server for a fresh one-time key.
    first = first_instance(app.home)
    existing = app.gate.find_running()
    if not existing and not first:
        # Another launch is still starting up: wait for it to publish instead of binding a second port.
        for _ in range(40):
            time.sleep(0.25)
            existing = app.gate.find_running()
            if existing: break
        if not existing: raise SystemExit(f'{APP_NAME} is already starting.')
    if existing:
        port,key = existing
        url = f'http://127.0.0.1:{port}/?k={key}'
    else:
        app.bind()
        url = app.gate.launch_url()
    if not args.no_browser and not open_window(url,app.home/'window',not existing):
        raise SystemExit('Microsoft Edge or Google Chrome was not found. Use --no-browser with a local browser.')
    if existing: return
    print(f'{APP_NAME} listening on 127.0.0.1:{app.gate.port}.',flush=True)
    if args.start_engine:
        def start_engine():
            try:
                if not app.client.status()['online']: app.client.start_engine(app.client.default_model())
            except Exception: pass   # the page shows the engine as offline and offers Start
        threading.Thread(target=start_engine,daemon=True).start()
    if not args.no_browser:
        def watch_window():
            while time.monotonic()-app.last_seen < 60 or app.operation.locked():
                time.sleep(2)
            app.server.shutdown()
        threading.Thread(target=watch_window,daemon=True).start()
    try: app.server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt: pass
    finally: app.close()

if __name__ == '__main__': main()
