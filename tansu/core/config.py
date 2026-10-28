"""Settings and the data folder (%LOCALAPPDATA%\\Tansu). The archive library itself lives in Documents\\Archives."""
import ctypes
import json
import os
import threading

TEST_HOME = os.environ.get("TANSU_HOME")      # tests: a throwaway data folder + library instead of the real ones
DATA_DIR = TEST_HOME or os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Tansu")
DROP = os.path.join(DATA_DIR, "drop")        # files dropped into the window are copied here first
for _d in (DATA_DIR, DROP):
    os.makedirs(_d, exist_ok=True)
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")


def documents():
    """The real Documents folder, even when it is redirected (OneDrive, another drive)."""
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
        return buf.value
    return os.path.join(os.path.expanduser("~"), "Documents")


DEFAULTS = {
    "root": os.path.join(TEST_HOME or documents(), "Archives"),
    "ai": True,                 # recommendations from the NPU model
    "auto_advise": True,        # ask the model as soon as files are added
    "model": "qwen3.5:4b",      # FastFlowLM model tag (qwen3.5:2b is the faster alternative)
    "flm_port": 52625,          # the FastFlowLM server shared with the other apps (core\flmshare.py)
    "pmode": "performance",     # ~40 % faster than balanced on this NPU
    "date_prefix": True,        # "2026-10-17 Holiday photos.7z"
    "verify": True,             # re-read every new archive and check its checksums before calling it done
    "skip_junk": True,          # leave out Thumbs.db, desktop.ini, node_modules, __pycache__, ~$ lock files...
    "extract_dir": os.path.join(TEST_HOME or os.path.expanduser("~"), "Downloads"),
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


def root():
    r = get()["root"]
    os.makedirs(r, exist_ok=True)
    return r
