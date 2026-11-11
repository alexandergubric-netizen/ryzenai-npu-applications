"""Adapted from Washi core/llm.py, snapshot 2026-10-30 (vendor/provenance.json).
No downloads, server restarts, global cancel, or reasoning-to-answer fallback.
"""
import http.client
import json
import subprocess
import threading
import time
from .service_peer import ServiceConnection
from .config import FLM_EXE, FLM_PORT, GATEWAY_PORT, DEFAULT_MODEL, TERMINAL_MODEL, pick_model
from .platform import NO_WINDOW, WINDOWS
if WINDOWS:
    from vendor.washi import flmshare   # shared-engine bookkeeping of the Ryzen AI apps

# Models with the Think first switch: FLM gets an explicit "think" for them on every request (see stream()).
THINKERS = ('qwen3.5', 'qwen-liberty3.5')
POWERSHELL = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'

class BusyError(RuntimeError):
    pass

class ThinkSplit:
    def __init__(self):
        self.pending = ''
        self.thinking = False
    def feed(self, text, final=False):
        self.pending += text
        out = []
        while self.pending:
            tag = '</think>' if self.thinking else '<think>'
            at = self.pending.find(tag)
            if at >= 0:
                if at: out.append(('thinking' if self.thinking else 'text', self.pending[:at]))
                self.pending = self.pending[at+len(tag):]
                self.thinking = not self.thinking
                continue
            keep = 0
            if not final:
                for n in range(1, min(len(tag),len(self.pending)+1)):
                    if self.pending.endswith(tag[:n]): keep = n
            chunk = self.pending[:-keep] if keep else self.pending
            self.pending = self.pending[-keep:] if keep else ''
            if chunk: out.append(('thinking' if self.thinking else 'text',chunk))
            break
        return out

class Client:
    """FastFlowLM on the Ryzen AI NPU. core/mlx_client.py subclasses it for Apple silicon; app code uses only:
    models, require_model, default_model, terminal_model, status, stream, warm, detach, start_engine, stop_engine."""
    kind = 'flm'
    label = 'FastFlowLM'
    def __init__(self, port=FLM_PORT, gateway_port=GATEWAY_PORT):
        self.port, self.gateway_port = port, gateway_port
        self.lock = threading.Lock()
        self.model_lock = threading.Lock()
        self.cache, self.cache_at = [], 0
        self.observed_model = None
        self.observed_at = None
        self.warming = None
        self.joined = False
    def get_json(self, path, port=None, timeout=2):
        c = http.client.HTTPConnection('127.0.0.1',port or self.port,timeout=timeout)
        try:
            c.request('GET',path)
            r = c.getresponse()
            if r.status != 200: raise RuntimeError('Local service refused the request.')
            raw = r.read(2*1024*1024+1)
            if len(raw) > 2*1024*1024: raise RuntimeError('Service response too large.')
            return json.loads(raw)
        finally:
            c.close()
    def models(self):
        with self.model_lock:
            if self.cache and time.monotonic()-self.cache_at < 20: return self.cache
            try:
                entries = self.get_json('/v1/models', self.gateway_port)['data']
            except (OSError,ValueError,KeyError,RuntimeError,http.client.HTTPException):
                p = subprocess.run([str(FLM_EXE),'list','--filter','installed','--json','--quiet'],
                    capture_output=True,text=True,encoding='utf-8',timeout=20,
                    creationflags=NO_WINDOW)
                if p.returncode: raise RuntimeError('Could not read installed models.')
                raw = json.loads(p.stdout[p.stdout.index('{'):])['models']
                entries = []
                for m in raw:
                    labels = m.get('label') or []
                    entries.append({'id':m['name'],'supports_vision':bool(m.get('vlm')),
                        'supports_reasoning':'reasoning' in labels,'context_length':m.get('default_context_length',4096)})
            self.cache = [m for m in entries if isinstance(m,dict) and isinstance(m.get('id'),str)
                          and not m['id'].startswith(('embed','whisper'))]
            self.cache_at = time.monotonic()
            return self.cache
    def default_model(self):
        """The chat model for new chats: the app default when it is installed, else the first installed model."""
        return pick_model(self.models(), DEFAULT_MODEL)
    def terminal_model(self):
        """Code mode's command writer: the fast instruct model when installed, else the chat default."""
        return pick_model(self.models(), TERMINAL_MODEL, DEFAULT_MODEL)
    def require_model(self, model):
        if model not in {m['id'] for m in self.models()}:
            raise ValueError('Select an installed chat model. Downloads are disabled.')
    def status(self):
        try:
            npu = self.get_json('/api/npu/status')
            return {'online':True,'npu':npu,'engine':self.kind,'last_observed_model':self.observed_model,
                    'last_observed_at':self.observed_at,'busy':self.lock.locked(),'warming':self.warming}
        except (OSError,ValueError,RuntimeError,http.client.HTTPException):
            return {'online':False,'engine':self.kind,'last_observed_model':None,'busy':self.lock.locked()}
    # Starting and stopping the engine happens only on the user's click (Settings > Engine) or when the installed
    # app's launcher passes --start-engine. On the author's PC the flm-gateway scripts next to the app do it (they
    # also start the gateway); an installed copy starts FastFlowLM itself and stops only an engine the apps started.
    def start_engine(self, model):
        from .config import ROOT, DATA_HOME
        try: self.require_model(model)
        except Exception: model = self.default_model() or DEFAULT_MODEL
        script = ROOT.parent/'flm-gateway'/'Start-LocalAI.ps1'
        if script.is_file():
            subprocess.Popen([POWERSHELL,'-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',str(script),
                              '-App','Tsubasa','-EngineOnly','-Model',model],creationflags=NO_WINDOW)
            return model
        if not FLM_EXE.is_file():
            raise ValueError('FastFlowLM is not installed. Get it from fastflowlm.com, then press Start again.')
        if self.status()['online']: return model
        flmshare.start(str(FLM_EXE),model,self.port,'performance','Tsubasa')
        self.joined = True
        return model
    def stop_engine(self):
        from .config import ROOT
        script = ROOT.parent/'flm-gateway'/'Stop-LocalAI.ps1'
        if script.is_file():
            subprocess.run([POWERSHELL,'-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',str(script)],
                           timeout=30,capture_output=True,creationflags=NO_WINDOW)
        elif not flmshare.stop_server(self.port):
            raise ValueError('This engine was not started by Tsubasa or another Ryzen AI app, so it is left running.')
        self.observed_model = None
    def download(self, model):
        raise ValueError('On Windows, add models with FastFlowLM itself: flm pull <model>.')
    def suggested(self):
        return []
    def connect(self):
        return ServiceConnection(self.port,FLM_EXE,timeout=120)
    def shape(self, payload, model, think):
        # FastFlowLM 1.0.9 decides by itself whether the qwen3.5 models reason unless the request says so:
        # "hello!" with no flag reasoned for 25-32 s (2026-11-05), /no_think did not stop it, "think": false
        # answered in 1.6 s. So Think first is always sent explicitly, on or off.
        if think or model.startswith(THINKERS): payload['think'] = bool(think)
    def join(self):
        if not self.joined:
            flmshare.join('Tsubasa')
            self.joined = True
    def detach(self):
        # Never call vendor.leave(): its last-user path can terminate someone else's FLM.
        if self.joined and WINDOWS:
            with flmshare._lock:
                d = flmshare._read()
                if d.get('users',{}).get('Tsubasa') == __import__('os').getpid():
                    d['users'].pop('Tsubasa',None)
                    flmshare._write(d)
            self.joined = False
    def warm(self, model):
        """Load a model in the background (the page asks when you switch modes), so the next message does not wait
        for the swap. A message sent meanwhile waits for it below instead of failing as busy."""
        self.require_model(model)
        if model == self.observed_model or self.warming:
            return False
        def work():
            try:
                for _ in self.stream(model, [{'role':'user','content':'Reply with OK.'}], max_tokens=1, warm=True): pass
            except (OSError, RuntimeError, ValueError):
                pass
            finally:
                self.warming = None
        self.warming = model
        threading.Thread(target=work, daemon=True).start()
        return True
    def stream(self, model, messages, max_tokens=256, cancelled=None, think=False, tools=None, warm=False):
        self.require_model(model)
        # A background preload holds the engine for up to a model swap (about 9-30 s): wait for it.
        waited = self.warming and not warm and self.lock.acquire(timeout=120)
        if not waited and not self.lock.acquire(blocking=False): raise BusyError('Another Tsubasa request is running.')
        c = self.connect()
        try:
            msgs = [dict(m) for m in messages]
            if self.kind=='flm' and msgs[-1]["role"]=="user" and not think and (model.startswith('qwen3.5') or model.startswith('qwen-liberty3.5')):
                if isinstance(msgs[-1]["content"],str):
                    msgs[-1]['content'] = '/no_think '+msgs[-1]['content']
                elif msgs[-1]["content"] and msgs[-1]["content"][0].get("type")=="text":
                    msgs[-1]['content'] = [{**msgs[-1]["content"][0],'text':'/no_think '+msgs[-1]["content"][0]['text']},*msgs[-1]["content"][1:]]
            payload = {'model':model,'messages':msgs,'stream':True,'max_tokens':max_tokens,
                       'temperature':0.3,'top_p':0.9,'stream_options':{'include_usage':True}}
            # FastFlowLM 1.0.9 decides by itself whether the qwen3.5 models reason unless the request says so:
            # "hello!" with no flag reasoned for 25-32 s (2026-11-05), /no_think did not stop it, "think": false
            # answered in 1.6 s. So Think first is always sent explicitly, on or off.
            self.shape(payload, model, think)
            if tools:
                payload.update(tools=tools, tool_choice='auto', temperature=0.2)
            c.request('POST','/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'})
            r = c.getresponse()
            if r.status != 200: raise RuntimeError(f'The AI engine returned HTTP {r.status}.')
            self.join()
            splitter, done, size = ThinkSplit(), False, 0
            for raw in r:
                # Stop: hang up our own connection. FastFlowLM ends that generation at once (measured: the next
                # request starts normally), so the engine is free again instead of finishing a long answer unseen.
                if cancelled and cancelled.is_set():
                    try: c.sock.shutdown(2)
                    except (OSError, AttributeError): pass
                    self.observed_model, self.observed_at = model,time.time()   # the model is loaded either way
                    return
                size += len(raw)
                if size > 8*1024*1024: raise RuntimeError('Model response exceeded the limit.')
                # Only our own connection is ever closed; another app's requests are never cancelled.
                line = raw.decode('utf-8').strip()
                if not line.startswith('data:'): continue
                if line[5:].strip() == '[DONE]':
                    done = True
                    break
                data = json.loads(line[5:])
                if data.get('error'): raise RuntimeError('The AI engine reported a generation error.')
                if data.get('usage'): yield 'usage',data['usage']
                for choice in data.get('choices',[]):
                    delta = choice.get('delta',{})
                    if cancelled and cancelled.is_set(): continue
                    if choice.get('finish_reason')=='length' and tools:
                        raise RuntimeError('Truncated tool response. No pending calls executed.')
                    if delta.get('tool_calls'):
                        if not tools: raise RuntimeError('Unexpected tool call.')
                        yield 'tool_delta',delta['tool_calls']
                    if delta.get('reasoning_content') or delta.get('reasoning'): yield 'thinking',delta.get('reasoning_content') or delta['reasoning']
                    if delta.get('content'):
                        yield from splitter.feed(delta['content'])
            if not done: raise RuntimeError('The AI engine stopped before the answer was complete.')
            if not cancelled or not cancelled.is_set(): yield from splitter.feed('',final=True)
            self.observed_model, self.observed_at = model,time.time()
        finally:
            c.close()
            self.lock.release()
