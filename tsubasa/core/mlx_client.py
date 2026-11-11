"""MLX engine for Apple silicon: Tsubasa talks to mlx-lm's OpenAI-compatible server on 127.0.0.1.

    python -m mlx_lm.server --host 127.0.0.1 --port 52631

Facts this relies on (mlx-lm SERVER.md and server.py, read 2026-11-11; not yet run on a Mac by the author):
- GET /health answers {"status": "ok"}; POST /v1/chat/completions streams OpenAI-style chunks and ends with [DONE].
- The request's "model" (a Hugging Face repo id from the local cache, or a path) is loaded on demand, one at a time.
- "chat_template_kwargs": {"enable_thinking": false} switches Qwen3 reasoning off per request; reasoning text arrives
  in delta["reasoning"] (core/client.py also accepts <think> tags and reasoning_content).
- "stream_options": {"include_usage": true} adds a final usage chunk.
Models are never downloaded silently: only models already in the Hugging Face cache are offered, and a download
starts only when the user presses the button for it.
"""
import http.client
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from .client import Client
from .config import DATA_HOME, DEFAULT_MODEL, MLX_PORT, TERMINAL_MODEL

REPO = re.compile(r"[A-Za-z0-9][\w.-]{0,95}/[A-Za-z0-9][\w.-]{0,95}")
# Shown as one-click downloads when nothing is installed yet (4-bit MLX builds by the mlx-community project).
SUGGESTED = [{"id": DEFAULT_MODEL, "note": "Chat · about 4.6 GB · needs 16 GB memory"},
             {"id": TERMINAL_MODEL, "note": "Fast, for Code mode · about 2.3 GB · fine on 8 GB"}]


def hf_cache():
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME") or Path.home() / ".cache/huggingface") / "hub"


def cached_models(cache=None):
    """Chat models in the Hugging Face cache: a snapshot with config.json, a tokenizer config and MLX weights."""
    found = []
    cache = cache or hf_cache()
    if not cache.is_dir():
        return found
    for repo in sorted(cache.glob("models--*--*")):
        snaps = sorted((repo / "snapshots").glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        snap = next((s for s in snaps if (s / "config.json").exists() and (s / "tokenizer_config.json").exists()
                     and any(s.glob("*.safetensors"))), None)
        if not snap:
            continue
        name = repo.name[len("models--"):].replace("--", "/", 1)
        try:
            config = json.loads((snap / "config.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            config = {}
        if "whisper" in name.lower() or config.get("model_type") in ("whisper", "bert", "clip"):
            continue
        found.append({"id": name, "supports_vision": False, "supports_tools": True,
                      "supports_reasoning": bool(re.search(r"qwen3|deepseek-r|think|reason", name, re.I)),
                      "context_length": 32768})
    return found


class MlxClient(Client):
    kind = "mlx"
    label = "MLX"

    def __init__(self, port=MLX_PORT):
        super().__init__(port, None)
        self.proc, self.log, self.pull = None, None, None

    # ---- inventory
    def models(self):
        with self.model_lock:
            if not self.cache or time.monotonic() - self.cache_at > 10:
                self.cache, self.cache_at = cached_models(), time.monotonic()
            return self.cache

    def suggested(self):
        have = {m["id"] for m in self.models()}
        return [dict(s, downloading=bool(self.pull and self.pull[0] == s["id"] and self.pull[1].poll() is None))
                for s in SUGGESTED if s["id"] not in have]

    def download(self, model):
        """Fetch one MLX model from Hugging Face into the usual cache. Only on the user's click."""
        if not isinstance(model, str) or not REPO.fullmatch(model):
            raise ValueError("Give a Hugging Face model id such as mlx-community/Qwen3-4B-4bit.")
        if self.pull and self.pull[1].poll() is None:
            raise ValueError(f"Still downloading {self.pull[0]}.")
        code = "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1])"
        log = open(DATA_HOME / "model-download.log", "ab")
        self.pull = (model, subprocess.Popen([sys.executable, "-c", code, model], stdout=log, stderr=log,
                                             stdin=subprocess.DEVNULL))
        return {"downloading": model}

    # ---- the server process
    def status(self):
        base = {"engine": self.kind, "busy": self.lock.locked(), "warming": self.warming,
                "downloading": self.pull[0] if self.pull and self.pull[1].poll() is None else None}
        try:
            online = self.get_json("/health").get("status") == "ok"
        except (OSError, ValueError, RuntimeError, http.client.HTTPException):
            online = False
        return {**base, "online": online, "last_observed_model": self.observed_model if online else None,
                "last_observed_at": self.observed_at}

    def start_engine(self, model=None):
        """Start mlx-lm's server on loopback. It loads a model with the first request, so starting is quick."""
        if self.status()["online"] or (self.proc and self.proc.poll() is None):
            return model
        try:
            import mlx_lm  # noqa: F401
        except ImportError:
            raise ValueError("The MLX engine (mlx-lm) is not installed in this copy of Tsubasa. See MAC.md.") from None
        self.log = open(DATA_HOME / "mlx-server.log", "ab")
        self.proc = subprocess.Popen([sys.executable, "-m", "mlx_lm.server", "--host", "127.0.0.1", "--port",
                                      str(self.port), "--max-tokens", "2048", "--log-level", "WARNING"],
                                     stdout=self.log, stderr=self.log, stdin=subprocess.DEVNULL, cwd=str(DATA_HOME))
        return model

    def stop_engine(self):
        if not self.proc or self.proc.poll() is not None:
            raise ValueError("The MLX server was not started by this Tsubasa window, so it is left running.")
        self._stop()
        self.observed_model = None

    def _stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self.log:
            self.log.close()
            self.log = None

    def join(self):
        pass

    def detach(self):
        self._stop()   # only the server this app started

    # ---- requests
    def connect(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=600)   # the first request loads the model

    def shape(self, payload, model, think):
        payload["chat_template_kwargs"] = {"enable_thinking": bool(think)}


def wait_online(client, seconds=40):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if client.status()["online"]:
            return True
        time.sleep(0.5)
    return False


def start_in_background(client):
    threading.Thread(target=lambda: (client.start_engine(), wait_online(client)), daemon=True).start()
