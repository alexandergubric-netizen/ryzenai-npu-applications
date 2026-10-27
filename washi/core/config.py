"""Settings and the recent-files list, kept in %LOCALAPPDATA%\\Washi (WASHI_HOME overrides it for tests)."""
import json
import os
import threading
import time

DATA_DIR = os.environ.get("WASHI_HOME") or os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Washi")
os.makedirs(DATA_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
RECENT_FILE = os.path.join(DATA_DIR, "recent.json")
SESSION_FILE = os.path.join(DATA_DIR, "session.json")

DEFAULTS = {
    "theme": "auto",          # auto | light | dark
    "accent": "indigo",       # indigo | vermilion | matcha | gold
    "splash": True,
    "ai": True,               # the person's switch; only matters on PCs that can run the AI
    "model": "qwen3:4b",
    "flm_port": 52625,
    "pmode": "balanced",
    "author": os.environ.get("USERNAME", "") or "Me",
    "page_dark": False,       # invert page colours in dark theme (reading mode)
    "zoom": "fit-width",
    "layout": "continuous",   # continuous | single | two
    "sidebar": "thumbs",
    "ebook_fontsize": 11.0,   # text size for EPUB / MOBI / FB2 books
}
_lock = threading.Lock()
_cache = {}


def get():
    if not _cache:
        s = dict(DEFAULTS)
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
        _cache.update(s)
    return dict(_cache)


def update(changes):
    with _lock:
        s = get()
        for k, v in (changes or {}).items():
            if k not in DEFAULTS or isinstance(v, bool) != isinstance(DEFAULTS[k], bool):
                continue
            if isinstance(DEFAULTS[k], float) and isinstance(v, (int, float)):
                s[k] = float(v)
            elif type(v) is type(DEFAULTS[k]) or (isinstance(DEFAULTS[k], int) and isinstance(v, int)):
                s[k] = v
        _cache.clear()
        _cache.update(s)
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
        os.replace(tmp, SETTINGS_FILE)
        return dict(s)


def recent():
    try:
        with open(RECENT_FILE, encoding="utf-8") as f:
            items = json.load(f)
    except (OSError, ValueError):
        return []
    return [i for i in items if isinstance(i, dict) and os.path.exists(i.get("path", ""))]


def add_recent(path, pages=0, title=""):
    with _lock:
        items = [i for i in recent() if os.path.normcase(i["path"]) != os.path.normcase(path)]
        items.insert(0, {"path": path, "name": os.path.basename(path), "pages": pages, "title": title,
                         "opened": time.time()})
        with open(RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(items[:24], f, ensure_ascii=False, indent=1)


def forget_recent(path):
    with _lock:
        items = [i for i in recent() if os.path.normcase(i["path"]) != os.path.normcase(path)]
        with open(RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
