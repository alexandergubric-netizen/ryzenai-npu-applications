"""FastFlowLM on the Ryzen AI NPU (OpenAI-compatible server started with `flm serve`)."""
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import config, hw

CREATE_NO_WINDOW = 0x08000000
DEFAULT_MODEL = "qwen3:4b"


class Cancelled(Exception):
    pass


class NPU:
    def __init__(self):
        self.proc = None            # the server process, if Washi started it
        self.state = "offline"      # offline | starting | online | missing | nomodel | pulling
        self.detail = ""
        self.tps = None
        self.ttft = None
        self.lock = threading.Lock()  # the NPU runs one generation at a time
        self.warm = set()             # models that already answered once (weights loaded)
        self.models = []
        self.cancel = threading.Event()
        self.pull_pct = None

    @property
    def base(self):
        return f"http://127.0.0.1:{config.get()['flm_port']}/v1"

    def flm_exe(self):
        return hw.flm_exe()

    def model(self):
        """The chosen model, or the best installed one when the chosen model is not downloaded."""
        m = config.get()["model"]
        if not self.models or m in self.models:
            return m
        for pref in (DEFAULT_MODEL, "qwen3:8b", "llama3.2:3b", "gemma3:4b"):
            if pref in self.models:
                return pref
        return self.models[0]

    def pull(self, model=DEFAULT_MODEL):
        """Download a model with `flm pull`, reporting progress from the growing model folder."""
        exe = self.flm_exe()
        if not exe or self.state == "pulling":
            return
        self.state, self.detail, self.pull_pct = "pulling", f"Downloading {model} (about 3 GB)…", 0

        def size(folder):
            total = 0
            for dp, _, files in os.walk(folder):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(dp, f))
                    except OSError:
                        pass
            return total

        def run():
            from .winutil import documents
            folder = os.path.join(documents(), "flm", "models")
            before = size(folder) if os.path.isdir(folder) else 0
            proc = subprocess.Popen([exe, "pull", model], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=CREATE_NO_WINDOW)
            while proc.poll() is None:
                got = (size(folder) if os.path.isdir(folder) else 0) - before
                self.pull_pct = min(99, round(got * 100 / (3.1 * 2 ** 30)))
                self.detail = f"Downloading {model}: {got / 2**30:.2f} of about 3.1 GB"
                time.sleep(1.5)
            self.models = self.downloaded_models()
            self.pull_pct = None
            if model in self.models:
                config.update({"model": model})
                self.state = "offline"
                self.ensure()
            else:
                self.state, self.detail = "nomodel", "The download did not finish. Try again."
        threading.Thread(target=run, daemon=True).start()

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

    def ensure(self, on_ready=None):
        """Start `flm serve` in the background unless a server is already listening, then warm the model up."""
        s = config.get()
        if self.state in ("starting", "pulling"):
            return
        exe = self.flm_exe()
        if not exe and not self.ping():
            self.state, self.detail = "missing", "FastFlowLM is not installed"
            return
        self.models = self.downloaded_models()
        if exe and not self.models:
            self.state, self.detail = "nomodel", "No AI model is downloaded yet"
            return
        model = self.model()

        def run():
            if not self.ping():
                self.state, self.detail = "starting", "Starting FastFlowLM…"
                try:
                    self.proc = subprocess.Popen(
                        [exe, "serve", model, "--port", str(s["flm_port"]), "--pmode", s["pmode"],
                         "--ctx-len", "16384"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                except OSError as e:
                    self.state, self.detail = "offline", str(e)
                    return
                for _ in range(240):
                    if self.ping():
                        break
                    if self.proc.poll() is not None:
                        self.state, self.detail = "offline", "FastFlowLM stopped while starting"
                        return
                    time.sleep(0.5)
                else:
                    self.state, self.detail = "offline", "FastFlowLM did not start"
                    return
            self.warmup(model)
            if on_ready:
                on_ready()

        self.state, self.detail = "starting", "Loading model onto the NPU…"
        threading.Thread(target=run, daemon=True).start()

    def warmup(self, model):
        """A one-token request so the model's weights are on the NPU before the first real question."""
        self.state, self.detail = "starting", f"Loading {model} onto the NPU…"
        try:
            self.complete([{"role": "user", "content": "hi"}], max_tokens=1, model=model)
            self.warm.add(model)
            self.state, self.detail = "online", ""
        except (urllib.error.URLError, OSError, ValueError) as e:
            self.state, self.detail = "offline", f"Model failed to load: {e}"

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None

    # ---------------------------------------------------------------- generation
    def stream(self, messages, max_tokens=400, model=None, temperature=0.15, think=False):
        """Yield ('think', n) while the model reasons and ('text', piece) for the answer."""
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
            with urllib.request.urlopen(req, timeout=600) as r:
                for raw in r:
                    if self.cancel.is_set():
                        raise Cancelled()
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

    def complete(self, messages, **kw):
        return "".join(p for kind, p in self.stream(messages, **kw) if kind == "text").strip()


npu = NPU()
