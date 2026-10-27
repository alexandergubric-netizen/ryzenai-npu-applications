"""Local AI for Kaizen, nothing leaves the PC.

Two engines speak the same OpenAI-compatible API:
  * FastFlowLM - runs the model on the AMD Ryzen AI NPU (`flm serve`), the fast and frugal choice.
  * LM Studio  - runs on any PC (CPU/GPU), used when there is no Ryzen AI NPU.
"""
import base64
import io
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
import zlib

from . import db, edition, winshell

FLM_CANDIDATES = [os.path.expandvars(r"%ProgramFiles%\flm\flm.exe"), r"C:\Program Files\flm\flm.exe"]
LMS_CANDIDATES = [os.path.expanduser(r"~\.lmstudio\bin\lms.exe"),
                  os.path.expandvars(r"%LOCALAPPDATA%\Programs\LM Studio\resources\app\.webpack\lms.exe")]
LMS_APPS = [os.path.expandvars(r"%LOCALAPPDATA%\Programs\LM Studio\LM Studio.exe"),
            os.path.expandvars(r"%ProgramFiles%\LM Studio\LM Studio.exe")]
LMS_PREFERRED =("qwen3-4b", "qwen3", "qwen", "llama-3.2", "gemma", "phi", "llama")
CREATE_NO_WINDOW = 0x08000000


def _ping(base):
    try:
        with urllib.request.urlopen(base + "/models", timeout=2) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _server_models(base):
    try:
        with urllib.request.urlopen(base + "/models", timeout=4) as r:
            data = json.load(r).get("data", [])
    except (urllib.error.URLError, OSError, ValueError):
        return []
    return [m["id"] for m in data if not re.search(r"embed|whisper|rerank", m.get("id", ""), re.I)]


class Engine:
    def __init__(self):
        self.proc = None              # the server process, if Kaizen started it
        self.kind = None              # "flm" | "lmstudio" | None
        self.state = "offline"        # offline | starting | online | missing
        self.detail = ""
        self.tps = None
        self.ttft = None
        self.model = None
        self.lock = threading.Lock()  # one generation at a time

    # ---------------------------------------------------------------- discovery
    @staticmethod
    def flm_exe():
        return shutil.which("flm") or next((p for p in FLM_CANDIDATES if os.path.exists(p)), None)

    @staticmethod
    def lms_exe():
        return shutil.which("lms") or next((p for p in LMS_CANDIDATES if os.path.exists(p)), None)

    @property
    def label(self):
        return {"flm": "NPU", "lmstudio": "LM Studio"}.get(self.kind, "AI")

    def base_for(self, kind):
        s = db.get_settings()
        port = s["flm_port"] if kind == "flm" else s["lms_port"]
        return f"http://127.0.0.1:{port}/v1"

    @property
    def base(self):
        return self.base_for(self.kind or "flm")

    def choose(self):
        engine = db.get_settings().get("engine", "auto")
        has_flm = bool(self.flm_exe())
        # the lms CLI alone can be a leftover; LM Studio counts when its app is installed or its server answers
        has_lms = any(os.path.exists(p) for p in LMS_APPS) or _ping(self.base_for("lmstudio"))
        if engine == "flm":
            return "flm" if has_flm else None
        if engine == "lmstudio":
            return "lmstudio" if has_lms else None
        return "flm" if has_flm else "lmstudio" if has_lms else None

    def downloaded_models(self):
        if self.kind == "lmstudio":
            return _server_models(self.base)
        exe = self.flm_exe()
        if not exe:
            return []
        try:
            out = subprocess.run([exe, "list", "--filter", "installed", "--quiet"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=30, creationflags=CREATE_NO_WINDOW).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        return [m for m in re.findall(r"^\s*-\s+(\S+)", out, re.M) if not re.match(r"(embed|whisper)", m)]

    # ---------------------------------------------------------------- lifecycle
    def ensure(self):
        """Start the chosen engine in the background (if it isn't running yet) and warm the model up."""
        if self.state == "starting":
            return
        kind = self.choose()
        if not kind:
            self.kind, self.state = None, "missing"
            self.detail = "No local AI found. Install FastFlowLM (AMD Ryzen AI) or LM Studio."
            return
        self.kind = kind
        self.state, self.detail = "starting", "Waking the NPU…" if kind == "flm" else "Starting LM Studio…"
        threading.Thread(target=self._start_flm if kind == "flm" else self._start_lms, daemon=True).start()

    def _wait(self, base, proc=None, seconds=120):
        for _ in range(seconds * 2):
            if _ping(base):
                return True
            if proc is not None and proc.poll() is not None:
                return False
            time.sleep(0.5)
        return False

    def _start_flm(self):
        s = db.get_settings()
        self.model = s["model"]
        if not _ping(self.base):
            try:
                self.proc = subprocess.Popen(
                    [self.flm_exe(), "serve", self.model, "--port", str(s["flm_port"]), "--pmode", s["pmode"]],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
            except OSError as e:
                self.state, self.detail = "offline", str(e)
                return
            if not self._wait(self.base, self.proc, 180):
                self.state, self.detail = "offline", "FastFlowLM did not start (is the NPU driver up to date?)"
                return
        self._warmup()

    def _start_lms(self):
        s = db.get_settings()
        if not _ping(self.base):
            exe = self.lms_exe()
            if not exe:
                self.state, self.detail = "offline", "Start LM Studio once, then press the AI button again"
                return
            # starts LM Studio's headless service and its local server (older lms versions have no --port)
            for args in (["server", "start", "--port", str(s["lms_port"])], ["server", "start"]):
                try:
                    if subprocess.run([exe, *args], capture_output=True, timeout=90,
                                      creationflags=CREATE_NO_WINDOW).returncode == 0:
                        break
                except (OSError, subprocess.SubprocessError):
                    pass
            if not self._wait(self.base, None, 60):
                self.state, self.detail = "offline", "LM Studio's server did not start. Open LM Studio once."
                return
        models = _server_models(self.base)
        if not models:
            self.state, self.detail = "offline", "LM Studio has no model yet. Download “Qwen3 4B” in LM Studio."
            return
        wanted = s.get("lms_model")
        if wanted not in models:
            wanted = next((m for p in LMS_PREFERRED for m in models if p in m.lower()), models[0])
        self.model = wanted
        self._warmup()

    def _warmup(self):
        """A one-token request so the weights are loaded before the first real question."""
        self.detail = f"Loading {self.model}…"
        try:
            self.complete([{"role": "user", "content": "hi"}], max_tokens=1)
            self.state, self.detail = "online", ""
        except (urllib.error.URLError, OSError, ValueError) as e:
            self.state, self.detail = "offline", f"The model failed to load: {e}"

    def restart(self):
        self.stop()
        self.state = "offline"
        self.ensure()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()   # only FastFlowLM servers we started ourselves; LM Studio is left alone
        self.proc = None

    # ---------------------------------------------------------------- generation
    def stream(self, messages, max_tokens=400, model=None, temperature=0.3):
        """Yield the answer text piece by piece, with any <think> reasoning removed."""
        model = model or self.model or db.get_settings()["model"]
        msgs = [dict(m) for m in messages]
        if re.search(r"qwen3(?!.*(2507|instruct|-it|vl))", model, re.I):
            for m in reversed(msgs):  # Qwen3 hybrid models think by default - skip it, it's slow
                if m["role"] == "user" and isinstance(m["content"], str):
                    m["content"] = "/no_think " + m["content"]
                    break
        body = json.dumps({"model": model, "messages": msgs, "stream": True, "max_tokens": max_tokens,
                           "temperature": temperature, "top_p": 0.9}).encode()
        req = urllib.request.Request(self.base + "/chat/completions", body, {"Content-Type": "application/json"})
        with self.lock:
            t0 = time.time()
            first, n = None, 0
            in_think, started = False, False
            pending, hidden = "", ""   # hidden: text inside an unclosed <think>, used if it held the whole answer
            with urllib.request.urlopen(req, timeout=600) as r:
                for raw in r:
                    line = raw.decode("utf-8", "ignore").strip()
                    if not line.startswith("data:") or line.endswith("[DONE]"):
                        continue
                    try:
                        delta = json.loads(line[5:])["choices"][0].get("delta", {})
                    except (ValueError, KeyError, IndexError):
                        continue
                    piece = delta.get("content") or ""
                    if not piece and delta.get("reasoning_content") and self.kind == "flm":
                        piece = delta["reasoning_content"]  # FastFlowLM sometimes streams the answer here
                    if not piece:
                        continue
                    n += 1
                    first = first or time.time()
                    pending += piece
                    while True:
                        if in_think:
                            end = pending.find("</think>")
                            if end < 0:
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
                            yield out
                        if not in_think:
                            break
            if pending and not in_think:
                yield pending.lstrip() if not started else pending
            elif in_think and not started and (hidden + pending).strip():
                yield (hidden + pending).strip()
            if first and n > 4:
                self.tps = round(n / max(time.time() - first, 0.01), 1)
                self.ttft = round(first - t0, 2)

    def complete(self, messages, **kw):
        return "".join(self.stream(messages, **kw)).strip()


npu = Engine()

# ---------------------------------------------------------------- text extraction


def _xml_text(xml):
    xml = re.sub(r"</w:p>|</a:p>|</text:p>|<row", "\n", xml)
    text = re.sub(r"<[^>]+>", " ", xml)
    return re.sub(r"[ \t]+", " ", text)


def _pdf_text(path, limit=1500):
    with open(path, "rb") as f:
        data = f.read(3_000_000)
    out = []
    m = re.search(rb"/Title\s*\(([^)]{3,200})\)", data)
    if m:
        out.append("Title: " + m.group(1).decode("latin-1", "ignore"))
    for sm in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        chunk = sm.group(1)
        try:
            chunk = zlib.decompress(chunk)
        except zlib.error:
            pass
        for t in re.findall(rb"\(((?:[^()\\]|\\.){1,300})\)\s*(?:Tj|')|\[((?:[^\]]){1,2000})\]\s*TJ", chunk):
            s = t[0] or b"".join(re.findall(rb"\(((?:[^()\\]|\\.)*)\)", t[1]))
            s = s.decode("latin-1", "ignore")
            if re.search(r"[A-Za-z]{2}", s):
                out.append(s)
        if sum(map(len, out)) > limit:
            break
    return " ".join(out)


def extract_text(path, category, limit=1500):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".docx", ".pptx", ".xlsx", ".odt", ".ods", ".odp"):
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                parts = [n for n in names if n in ("word/document.xml", "xl/sharedStrings.xml", "content.xml")]
                parts += sorted(n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml"))[:6]
                text = " ".join(_xml_text(z.read(n).decode("utf-8", "ignore")) for n in parts)
        elif ext == ".pdf":
            text = _pdf_text(path, limit)
        elif category in ("text", "code") or ext in (".csv", ".md", ".txt"):
            with open(path, "rb") as f:
                raw = f.read(8000)
            text = raw.decode("utf-8", "ignore") if raw.count(b"\x00") < 10 else ""
        else:
            return ""
    except (OSError, zipfile.BadZipFile, KeyError, ValueError):
        return ""
    return re.sub(r"\s+", " ", text).strip()[:limit]


# ---------------------------------------------------------------- descriptions

DESCRIBE_SYSTEM = (
    "You are Kaizen, a calm 5S organizing assistant. You write ONE short sentence (max 20 words). "
    "Say what the item most likely is and whether it seems worth keeping. No preamble, no quotes.")


def _fmt_size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def _date(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else "unknown"


def describe_file(row):
    key = f"f:{row['path']}:{row['mtime']}"
    cached = db.one("SELECT text FROM descriptions WHERE key=?", (key,))
    if cached:
        return cached["text"]
    settings = db.get_settings()
    info = (f"File name: {row['name']}\nFolder: {row['dir']}\nType: {row['category']}\nSize: {_fmt_size(row['size'])}\n"
            f"Last used: {_date(row['last_used'])}\nModified: {_date(row['mtime'])}")
    content = None
    if not row["cloud"] and row["category"] != "folder":
        with winshell.preserve_atime(row["path"]):
            text = extract_text(row["path"], row["category"])
        if text:
            info += f"\nBeginning of the content: {text[:1200]}"
        elif row["category"] == "image" and settings.get("vision_model") and npu.kind == "flm":
            img = winshell.shell_image(row["path"], 384, winshell.THUMB_ANY)
            if img is not None:
                buf = io.BytesIO()
                img.convert("RGB").save(buf, "JPEG", quality=80)
                content = [{"type": "text", "text": info + "\nDescribe what the picture shows."},
                           {"type": "image_url", "image_url": {
                               "url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}]
    messages = [{"role": "system", "content": DESCRIBE_SYSTEM},
                {"role": "user", "content": content or info}]
    model = settings["vision_model"] if content else None
    text = npu.complete(messages, max_tokens=60, model=model, temperature=0.2)
    text = text.strip().strip('"').split("\n")[0][:220]
    if text:
        with db.conn() as c:
            c.execute("INSERT OR REPLACE INTO descriptions VALUES(?,?,?)", (key, text, time.time()))
    return text


def describe_program(row):
    ed = edition.get()["id"]
    key = f"p:{row['key']}" if ed == "public" else f"p:{ed}:{row['key']}"  # editions word advice differently
    cached = db.one("SELECT text FROM descriptions WHERE key=?", (key,))
    if cached:
        return cached["text"]
    if row["kind"] == "leftover":
        info = (f"A folder in Program Files named '{row['name']}' that no installed program uses. "
                f"Size {_fmt_size(row['size'] or 0)}, unchanged since {_date(row['last_run'])}. "
                "What did it probably belong to, and is it likely safe to remove?")
    else:
        question = ("What is this program for, and can a typical home user remove it safely?"
                    if edition.get()["allow_uninstall"] else
                    "What is this program for, and does a typical office worker still need it? "
                    "(On this company PC only IT can remove programs, so don't tell the user to uninstall it.)")
        info = (f"Program: {row['name']}\nPublisher: {row['publisher']}\nVersion: {row['version']}\n"
                f"Size: {_fmt_size(row['size'] or 0)}\nLast used: {_date(row['last_run'])}\n{question}")
    text = npu.complete([{"role": "system", "content": DESCRIBE_SYSTEM}, {"role": "user", "content": info}],
                        max_tokens=60, temperature=0.2)
    text = text.strip().strip('"').split("\n")[0][:220]
    if text:
        with db.conn() as c:
            c.execute("INSERT OR REPLACE INTO descriptions VALUES(?,?,?)", (key, text, time.time()))
    return text
