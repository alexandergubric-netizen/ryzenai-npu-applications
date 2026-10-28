"""Settings and the data folder (%LOCALAPPDATA%\\Morph)."""
import json
import os
import threading

DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Morph")
INBOX = os.path.join(DATA_DIR, "inbox")      # files dropped into the window are copied here
WORK = os.path.join(DATA_DIR, "work")        # scratch space for multi-step conversions
for _d in (DATA_DIR, INBOX, WORK):
    os.makedirs(_d, exist_ok=True)
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

DEFAULTS = {
    "output_dir": os.path.join(os.path.expanduser("~"), "Downloads", "Morph"),
    "beside": True,            # files picked with Browse are saved next to the original
    "quality": "balanced",     # original | high | balanced | small
    "gpu": True,               # Radeon AMF video encoders when they work
    "ai": True,                # format advice from the NPU model
    "auto_advise": True,       # ask the model as soon as a file arrives
    "model": "qwen3.5:4b",        # FastFlowLM model tag (qwen3.5:2b is the faster alternative)
    "flm_port": 52625,         # FastFlowLM's default port; an already running server is reused
    "pmode": "performance",
    "parallel": 2,             # conversions running at the same time
}
_lock = threading.Lock()


def get():
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
