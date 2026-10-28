"""The Ryzen AI NPU enabler: installs FastFlowLM (the prerequisite for the AI advisor) and downloads the model.

Both steps run in the background and report progress to Settings. FastFlowLM's own installer asks Windows for
permission (UAC), so the user stays in control.
"""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request

from . import config, hw

CREATE_NO_WINDOW = 0x08000000
DEFAULT_MODELS = [("qwen3.5:4b", 3.2), ("qwen3.5:2b", 1.9)]   # the default, and a faster one to switch to
MODEL_GB = 5.1   # both together
state = {"task": None, "label": "", "pct": None, "detail": "", "error": ""}
_lock = threading.Lock()


def models():
    exe = hw.flm_exe()
    if not exe:
        return []
    try:
        out = subprocess.run([exe, "list", "--filter", "installed", "--quiet"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30, creationflags=CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [m for m in re.findall(r"^\s*-\s+(\S+)", out, re.M) if not re.match(r"(embed|whisper)", m)]


def status():
    """Everything Settings needs to show the enabler card."""
    h = hw.check(refresh=state["task"] is None)
    have = models() if h["flm"] else []
    model = config.get()["model"]
    if have and model not in have:   # the chosen model was removed: use the default, or any downloaded chat model
        model = next((x for x, _ in DEFAULT_MODELS if x in have), have[0])
        config.update({"model": model})
    ready = h["supported"] and h["flm"] and model in have
    return {**h, "models": have, "model": model, "has_model": model in have, "ready": ready,
            "job": dict(state), "model_gb": MODEL_GB}


def _set(**kw):
    state.update(kw)


def _documents():
    return os.path.join(os.path.expanduser("~"), "Documents")


def _dir_size(path):
    total = 0
    for dp, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return total


def install_flm():
    """Download FastFlowLM's installer and run it (Windows asks for permission)."""
    def run():
        folder = tempfile.mkdtemp(prefix="morph-flm-")   # private, and removed afterwards
        try:
            _set(task="flm", label=f"Downloading FastFlowLM {hw.FLM_VERSION}", pct=0, detail="", error="")
            msi = os.path.join(folder, "flm-setup.msi")
            req = urllib.request.Request(hw.FLM_MSI, headers={"User-Agent": "Morph"})
            digest = hashlib.sha256()
            with urllib.request.urlopen(req, timeout=60) as r, open(msi + ".part", "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got, t0 = 0, time.time()
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    digest.update(chunk)
                    got += len(chunk)
                    _set(pct=round(got * 100 / total) if total else None,
                         detail=f"{got / 2**20:.0f} of {total / 2**20:.0f} MB · {got / max(time.time() - t0, .1) / 2**20:.1f} MB/s")
            if digest.hexdigest() != hw.FLM_MSI_SHA256:
                raise RuntimeError("The downloaded FastFlowLM installer does not match the expected file, so it was not run")
            os.replace(msi + ".part", msi)
            _set(label="Installing FastFlowLM", pct=None, detail="Windows will ask for permission - please click Yes")
            rc = subprocess.run(["msiexec.exe", "/i", msi, "/passive", "/norestart"]).returncode
            if rc not in (0, 3010):
                raise RuntimeError(f"FastFlowLM's installer stopped (code {rc})")
            hw.check(refresh=True)
            if not hw.flm_exe():
                raise RuntimeError("FastFlowLM was installed but not found yet - restart Windows, then come back here")
            _set(task=None, label="FastFlowLM installed", pct=100, detail="")
        except Exception as e:  # noqa: BLE001
            _set(task=None, error=str(e) or e.__class__.__name__, pct=None)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    with _lock:
        if state["task"]:
            return False
        state["task"] = "flm"
    threading.Thread(target=run, daemon=True).start()
    return True


def pull_model():
    """flm pull <model>, with progress from the size of FastFlowLM's model folder."""
    def run():
        try:
            exe = hw.flm_exe()
            if not exe:
                raise RuntimeError("Install FastFlowLM first")
            chosen = config.get()["model"]
            todo = DEFAULT_MODELS if chosen in dict(DEFAULT_MODELS) else [(chosen, MODEL_GB)]
            folder = os.path.join(_documents(), "flm", "models")
            for model, gb in todo:
                if model in models():
                    continue
                _set(task="model", label=f"Downloading the AI model {model}", pct=0, detail="", error="")
                before = _dir_size(folder) if os.path.isdir(folder) else 0
                proc = subprocess.Popen([exe, "pull", model], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=CREATE_NO_WINDOW)
                while proc.poll() is None:
                    got = (_dir_size(folder) if os.path.isdir(folder) else 0) - before
                    _set(pct=min(99, round(got * 100 / (gb * 2 ** 30))), detail=f"{got / 2**30:.2f} of about {gb} GB")
                    time.sleep(1)
            if chosen not in models():
                raise RuntimeError("The download did not finish - check the internet connection and try again")
            _set(task=None, label="AI model ready", pct=100, detail="")
        except Exception as e:  # noqa: BLE001
            _set(task=None, error=str(e) or e.__class__.__name__, pct=None)

    with _lock:
        if state["task"]:
            return False
        state["task"] = "model"
    threading.Thread(target=run, daemon=True).start()
    return True
