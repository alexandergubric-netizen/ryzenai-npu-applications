"""Settings and the data folder (%LOCALAPPDATA%\\Sensei)."""
import json
import os
import threading

DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Sensei")
os.makedirs(DATA_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

DEFAULTS = {
    "model": "",                # FastFlowLM model tag ("" = the recommended one)
    "flm_port": 52625,          # FastFlowLM's default port; an already running server is reused
    "pmode": "performance",     # NPU power mode
    "autorun": True,            # run commands the checker marks read-only straight away
    "router": True,             # let the AI pick a tested library task before writing new code
    "max_repairs": 2,           # how often the AI may fix a command the checker rejected
}
# the model the benchmark (tests/model_bench.py) found fastest while still accurate on this hardware
RECOMMENDED_MODEL = "qwen3-it:4b"
_lock = threading.Lock()


def get():
    data = _read()
    data["model"] = data.get("model") or RECOMMENDED_MODEL
    return data


def _read():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS}}


def update(changes):
    with _lock:
        data = get()
        for k, v in changes.items():
            if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                data[k] = v
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return data
