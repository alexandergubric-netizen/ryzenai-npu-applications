"""SQLite storage for scan results, settings, AI descriptions and the undo log."""
import json
import os
import sqlite3
import threading

DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Kaizen5S")
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")
DB_PATH = os.path.join(DATA_DIR, "kaizen.db")
os.makedirs(THUMB_DIR, exist_ok=True)

DEFAULTS = {
    "stale_days": 365,          # Seiri: file not used for this long -> candidate
    "program_stale_days": 180,  # Seiri for programs
    "downloads_days": 14,       # Seiton: how long a file may sit in Downloads
    "protect_media": True,      # photos/videos/music in their libraries are memories, not clutter
    "extra_roots": [],          # additional folders/drives to scan
    "skip_roots": [],           # default folders the user turned off
    "model": "qwen3:4b",
    "vision_model": "",         # e.g. qwen3vl-it:4b once downloaded
    "auto_describe": True,
    "engine": "auto",           # auto | flm (AMD Ryzen AI NPU) | lmstudio (any PC)
    "lms_port": 1234,
    "lms_model": "",            # empty = pick the best model LM Studio has
    "flm_port": 52625,
    "pmode": "performance",     # NPU power mode: powersaver | balanced | performance | turbo
    "theme": "auto",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files(
  id INTEGER PRIMARY KEY, path TEXT UNIQUE, name TEXT, ext TEXT, dir TEXT, root TEXT, root_name TEXT,
  category TEXT, size INTEGER, mtime REAL, atime REAL, ctime REAL, last_used REAL, cloud INTEGER DEFAULT 0,
  i_sort INTEGER DEFAULT 0, i_order INTEGER DEFAULT 0, i_shine INTEGER DEFAULT 0, i_std INTEGER DEFAULT 0,
  sustained INTEGER DEFAULT 0, reasons TEXT, target TEXT, new_name TEXT, dup_group TEXT, managed TEXT);
CREATE INDEX IF NOT EXISTS files_dir ON files(dir);
CREATE INDEX IF NOT EXISTS files_used ON files(last_used);
CREATE INDEX IF NOT EXISTS files_size ON files(size);
CREATE TABLE IF NOT EXISTS folders(
  path TEXT PRIMARY KEY, parent TEXT, name TEXT, root_name TEXT, bytes INTEGER, files INTEGER, subdirs INTEGER,
  last_used REAL, sort_bytes INTEGER, sort_n INTEGER, order_n INTEGER, shine_n INTEGER, std_n INTEGER,
  managed_n INTEGER, need TEXT, severity REAL);
CREATE INDEX IF NOT EXISTS folders_parent ON folders(parent);
CREATE TABLE IF NOT EXISTS programs(
  id INTEGER PRIMARY KEY, key TEXT UNIQUE, kind TEXT, name TEXT, publisher TEXT, version TEXT, installed REAL,
  size INTEGER, location TEXT, exe TEXT, uninstall TEXT, last_run REAL, run_count INTEGER, evidence TEXT,
  protected INTEGER DEFAULT 0, protect_reason TEXT, i_sort INTEGER DEFAULT 0, i_shine INTEGER DEFAULT 0,
  i_std INTEGER DEFAULT 0, sustained INTEGER DEFAULT 0, reasons TEXT, dup_group TEXT);
CREATE TABLE IF NOT EXISTS kept(path TEXT PRIMARY KEY, ts REAL);
CREATE TABLE IF NOT EXISTS descriptions(key TEXT PRIMARY KEY, text TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS scans(
  id INTEGER PRIMARY KEY, ts REAL, files INTEGER, bytes INTEGER, s_sort REAL, s_order REAL, s_shine REAL,
  s_std REAL, s_sustain REAL, overall REAL, reclaim INTEGER);
CREATE TABLE IF NOT EXISTS actions(
  id INTEGER PRIMARY KEY, batch TEXT, ts REAL, op TEXT, src TEXT, dst TEXT, row TEXT, undone INTEGER DEFAULT 0);
"""

MIGRATIONS = [("folders", "managed_bytes", "INTEGER DEFAULT 0"),
              ("files", "remote", "INTEGER DEFAULT 0")]   # 1 = network/removable: no Recycle Bin there

_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def conn():
    global _initialized
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        with _init_lock:
            if not _initialized:
                c.executescript(SCHEMA)
                for table, col, kind in MIGRATIONS:
                    try:
                        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
                    except sqlite3.OperationalError:
                        pass  # already there
                _initialized = True
        _local.c = c
    return c


def get_settings():
    s = dict(DEFAULTS)
    for row in conn().execute("SELECT key, value FROM settings"):
        try:
            s[row["key"]] = json.loads(row["value"])
        except ValueError:
            pass
    return s


def save_settings(values):
    c = conn()
    with c:
        for k, v in values.items():
            if k in DEFAULTS:
                c.execute("INSERT OR REPLACE INTO settings VALUES(?, ?)", (k, json.dumps(v)))
    return get_settings()


def rows(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args)]


def one(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None
