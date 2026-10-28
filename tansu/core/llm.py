"""FastFlowLM on the Ryzen AI NPU (OpenAI-compatible server started with `flm serve`), shared with the other apps
through core\\flmshare.py."""
import http.client
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import config, flmshare

FLM_CANDIDATES = [r"C:\Program Files\flm\flm.exe"]
CREATE_NO_WINDOW = 0x08000000
APP = "Tansu"


class NPU:
    def __init__(self):
        self.state = "offline"      # offline | starting | online | missing
        self.detail = ""
        self.tps = None
        self.ttft = None
        self.lock = threading.Lock()  # the NPU runs one generation at a time
        self.warm = set()             # models that already answered once (weights loaded)
        self.loaded = None            # the model FastFlowLM has on the NPU right now (as far as we know)
        self.ctx = flmshare.CTX_LEN   # the server's context length (read from its answers)
        self._switching = False
        self._switch_lock = threading.Lock()

    @property
    def base(self):
        return f"http://127.0.0.1:{config.get()['flm_port']}/v1"

    def model(self):
        return config.get()["model"]

    def flm_exe(self):
        return shutil.which("flm") or next((p for p in FLM_CANDIDATES if os.path.exists(p)), None)

    def ping(self):
        try:
            with urllib.request.urlopen(self.base + "/models", timeout=2) as r:
                return r.status == 200
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def downloaded_models(self):
        exe = self.flm_exe()
        if not exe:
            return []
        try:
            out = subprocess.run([exe, "list", "--filter", "installed", "--quiet"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=30, creationflags=CREATE_NO_WINDOW).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        models = re.findall(r"^\s*-\s+(\S+)", out, re.M)
        # chat models only
        return [m for m in models if not re.match(r"(embed|whisper)", m)]

    def _start_server(self, model):
        """Start the shared FastFlowLM server (full context, the chosen power mode) and wait until it answers."""
        s, exe = config.get(), self.flm_exe()
        if not exe:
            self.state, self.detail = "missing", "FastFlowLM is not installed"
            return False
        self.state, self.detail = "starting", "Starting FastFlowLM…"
        try:
            proc = flmshare.start(exe, model, s["flm_port"], s["pmode"], APP)
        except OSError as e:
            self.state, self.detail = "offline", str(e)
            return False
        for _ in range(240):
            if self.ping():
                return True
            if proc.poll() is not None:
                if self.ping():           # another app started it at the same moment
                    return True
                self.state, self.detail = "offline", "FastFlowLM stopped while starting"
                return False
            time.sleep(0.5)
        self.state, self.detail = "offline", "FastFlowLM did not start"
        return False

    def ensure(self, on_ready=None):
        """Start `flm serve` in the background unless a server is already listening, then warm the model up."""
        if self.state == "starting":
            return

        def run():
            if self.ping():
                flmshare.join(APP)
            elif not self._start_server(self.model()):
                return
            self.loaded = None        # a fresh or someone else's server: we don't know what it has loaded
            self.warmup(self.model())
            self.request_switch()     # the choice may have changed while the server was starting
            if on_ready:
                on_ready()

        self.state, self.detail = "starting", "Loading model onto the NPU…"
        threading.Thread(target=run, daemon=True).start()

    def _probe(self, model):
        """One token from `model` (loads it if needed). Returns FastFlowLM's usage report."""
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1,
                           "temperature": 0.2, "stream": False}).encode()
        req = urllib.request.Request(self.base + "/chat/completions", body, {"Content-Type": "application/json"})
        with self.lock, urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r).get("usage") or {}

    def warmup(self, model):
        """Put `model` on the NPU before the first real question (a switch takes about 15-20 s)."""
        switching = self.loaded not in (None, model)
        self.state, self.detail = "starting", (f"Switching to {model}… (about 15–20 s)" if switching
                                               else f"Loading {model} onto the NPU…")
        try:
            usage = self._probe(model)
            self.ctx = flmshare.ctx_from_usage(usage) or self.ctx
            self.loaded = model
            self.warm.add(model)
            if self.model() != model:     # chosen again meanwhile: the switch loop goes on, stay "switching"
                self.detail = f"Switching to {self.model()}… (about 15–20 s)"
            else:
                self.state, self.detail = "online", ""
        except (urllib.error.URLError, OSError, ValueError) as e:
            self.loaded = None
            self.state, self.detail = "offline", f"Model failed to load: {e}"

    def request_switch(self):
        """Make the model on the NPU match the chosen one - live, no restart. Changes made while a switch is
        still loading are not lost: the loop keeps going until the loaded model is the latest choice."""
        with self._switch_lock:
            if self._switching or self.state not in ("online", "starting") or not self.ping():
                return
            self._switching = True

        def run():
            try:
                while self.model() != self.loaded:
                    self.warmup(self.model())
                    if self.state == "offline":   # the load failed
                        break
            finally:
                with self._switch_lock:
                    self._switching = False
            if self.state == "online" and self.model() != self.loaded:
                self.request_switch()
        threading.Thread(target=run, daemon=True).start()

    def apply_pmode(self):
        """A new power mode needs a server restart. Done now unless another app is using the server.
        Returns True when it will apply now."""
        want = config.get()["pmode"]
        if flmshare.server_pmode() == want or not self.ping():
            return True
        if flmshare.others_using(APP) or self.state == "starting":
            return False

        def run():
            with self.lock:           # never in the middle of an answer
                flmshare.stop_server(config.get()["flm_port"])
            self.state = "offline"
            self.ensure()
        self.state, self.detail = "starting", f"Restarting FastFlowLM in {want} mode…"
        threading.Thread(target=run, daemon=True).start()
        return True

    def stop(self):
        """The app is closing: the server stops too, unless another app still uses it."""
        flmshare.leave(APP, config.get()["flm_port"])

    def _heal(self):
        """The server went away (another app or a crash stopped it): start it again and wait (up to 3 minutes)."""
        self.state, self.loaded = "offline", None
        self.ensure()
        t0 = time.time()
        while self.state == "starting" and time.time() - t0 < 180:
            time.sleep(0.5)
        return self.state == "online"

    # ---------------------------------------------------------------- generation
    def stream(self, messages, max_tokens=400, model=None, temperature=0.15, think=False):
        """Yield ('think', n) while the model reasons and ('text', piece) for the answer.
        If FastFlowLM is gone, start it again and retry once (a ('status', text) event says so); if it dies
        mid-answer, raise RuntimeError with a clear message and restart it in the background."""
        sent = False
        for attempt in (1, 2):
            try:
                for ev in self._stream(messages, max_tokens, model, temperature, think):
                    sent = True
                    yield ev
                return
            except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
                if isinstance(e, urllib.error.HTTPError) or not flmshare.lost(e):
                    raise RuntimeError(f"The AI engine refused the request ({e})") from e
                if sent or attempt == 2:
                    self.state, self.loaded = "offline", None
                    threading.Thread(target=self.ensure, daemon=True).start()
                    raise RuntimeError("The AI engine stopped while answering. It is restarting - "
                                       "ask again in a moment.") from e
                yield "status", "The AI engine had stopped - starting it again…"
                if not self._heal():
                    raise RuntimeError("The AI engine could not be restarted"
                                       + (f" ({self.detail})" if self.detail else "") + ".") from e

    def _stream(self, messages, max_tokens=400, model=None, temperature=0.15, think=False):
        model = model or self.model()
        msgs = [dict(m) for m in messages]
        if "qwen3" in model and "-it" not in model and "vl" not in model:
            for m in reversed(msgs):  # Qwen3 hybrid models: thinking is on by default
                if m["role"] == "user":
                    m["content"] = ("/think " if think else "/no_think ") + m["content"]
                    break
        body = json.dumps({"model": model, "messages": msgs, "stream": True, "max_tokens": max_tokens,
                           "temperature": temperature, "top_p": 0.9}).encode()
        req = urllib.request.Request(self.base + "/chat/completions", body, {"Content-Type": "application/json"})
        with self.lock:
            t0 = time.time()
            first, n = None, 0
            in_think, started, thought = False, False, 0
            pending = ""
            hidden = ""   # text swallowed as "thinking" - used if the model never closes the block
            with urllib.request.urlopen(req, timeout=120) as r:   # per read; covers a model swap/load
                for raw in r:
                    line = raw.decode("utf-8", "ignore").strip()
                    if not line.startswith("data:") or line.endswith("[DONE]"):
                        continue
                    try:
                        delta = json.loads(line[5:])["choices"][0].get("delta", {})
                    except (ValueError, KeyError, IndexError):
                        continue
                    if delta.get("reasoning_content"):
                        if think:
                            thought += 1
                            yield "think", thought
                            continue
                        # thinking is off, yet FastFlowLM sometimes streams the answer in this field
                        delta = {"content": delta["reasoning_content"]}
                    piece = delta.get("content") or ""
                    if not piece:
                        continue
                    n += 1
                    first = first or time.time()
                    pending += piece
                    # strip <think>...</think> blocks
                    while True:
                        if in_think:
                            end = pending.find("</think>")
                            if end < 0:
                                thought += 1
                                yield "think", thought
                                hidden += pending[:-10]
                                pending = pending[-10:]
                                break
                            hidden = ""
                            pending, in_think = pending[end + 8:], False
                            continue
                        start = pending.find("<think>")
                        if start >= 0:
                            out, pending, in_think = pending[:start], pending[start + 7:], True
                        elif "<" in pending[-8:] and not pending.rstrip().endswith(">"):
                            cut = pending.rfind("<")
                            out, pending = pending[:cut], pending[cut:]
                        else:
                            out, pending = pending, ""
                        if not started:
                            out = out.lstrip()
                            started = bool(out)
                        if out:
                            yield "text", out
                        if not in_think:
                            break
            if pending and not in_think:
                yield "text", pending.lstrip() if not started else pending
            elif in_think and not started and not think and (hidden + pending).strip():
                yield "text", (hidden + pending).strip()   # an unclosed <think> held the whole answer
            if first and n > 4:
                self.tps = round(n / max(time.time() - first, 0.01), 1)
                self.ttft = round(first - t0, 2)
            self.warm.add(model)
            self.loaded = model

    def complete(self, messages, **kw):
        return "".join(p for kind, p in self.stream(messages, **kw) if kind == "text").strip()


npu = NPU()
