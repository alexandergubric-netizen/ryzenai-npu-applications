"""Files on this PC for Chat and Code mode: list, read and write anything outside system and app-data folders.

Every call is shown to the user first and runs only after Allow (the agent loop in core/agent.py asks). This module
only decides which paths are reachable and does the bounded I/O.
"""
import difflib
import os
import stat
from pathlib import Path

from core.platform import blocked_roots

HOME = Path.home()
TEXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".html",
        ".htm", ".css", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".py", ".ps1", ".psm1", ".bat", ".cmd", ".sh", ".c", ".h",
        ".cpp", ".hpp", ".cs", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".sql", ".lua", ".r", ".tex", ".log", ".srt",
        ".vtt", ".gitignore", ".env.example", ""}
MAX_READ, MAX_WRITE, MAX_LIST = 400_000, 400_000, 300


def _blocked_roots():
    return [os.path.normcase(os.path.realpath(r)) for r in blocked_roots(HOME) if r]


BLOCKED = _blocked_roots()
BLOCKED_NAMES = {".ds_store", "ntuser.dat", "ntuser.ini", "pagefile.sys", "hiberfil.sys", "swapfile.sys", "desktop.ini"}


def resolve(path):
    """An absolute, real path the assistant may touch, or ValueError saying why not."""
    if not isinstance(path, str) or not path.strip() or len(path) > 1024 or "\x00" in path:
        raise ValueError("Give a file or folder path.")
    raw = os.path.expandvars(os.path.expanduser(path.strip().strip('"')))
    p = Path(raw if os.path.isabs(raw) else HOME / raw)
    real = os.path.realpath(p)
    norm = os.path.normcase(real)
    if norm.startswith("\\\\") or norm.startswith("/Network/"):
        raise ValueError("Network paths are not available.")
    for b in BLOCKED:
        if norm == b or norm.startswith(b + os.sep):
            raise ValueError("That is a system or app-data folder; Tsubasa does not open it.")
    if Path(real).name.casefold() in BLOCKED_NAMES:
        raise ValueError("That is a system file.")
    try:
        attrs = os.stat(real, follow_symlinks=False).st_file_attributes
        if attrs & stat.FILE_ATTRIBUTE_SYSTEM:
            raise ValueError("That is a system file.")
    except (FileNotFoundError, AttributeError):
        pass
    return Path(real)


def list_folder(path):
    p = resolve(path)
    if not p.is_dir():
        raise ValueError("That folder does not exist.")
    rows = []
    for entry in sorted(os.scandir(p), key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.casefold())):
        try:
            st = entry.stat(follow_symlinks=False)
            if getattr(st, "st_file_attributes", 0) & (stat.FILE_ATTRIBUTE_SYSTEM | stat.FILE_ATTRIBUTE_HIDDEN):
                continue
        except OSError:
            continue
        rows.append(("📁 " if entry.is_dir(follow_symlinks=False) else "   ") + entry.name +
                    ("" if entry.is_dir(follow_symlinks=False) else f"  ({_size(st.st_size)})"))
        if len(rows) >= MAX_LIST:
            rows.append(f"… more entries not shown (limit {MAX_LIST})")
            break
    return {"path": str(p), "text": "\n".join(rows) or "(empty folder)"}


def read_file(path):
    p = resolve(path)
    if not p.is_file():
        raise ValueError("That file does not exist.")
    if p.stat().st_size > MAX_READ:
        raise ValueError(f"That file is larger than {_size(MAX_READ)}; Tsubasa reads text files up to that size.")
    if p.suffix.lower() not in TEXT:
        raise ValueError("Tsubasa can read text, code, Markdown, CSV and JSON files here. For PDFs and Word files, "
                         "attach them with 📎 instead.")
    raw = p.read_bytes()
    if b"\x00" in raw[:4096]:
        raise ValueError("That looks like a binary file.")
    return {"path": str(p), "text": raw.decode("utf-8-sig", "replace")}


def plan_write(path, content):
    """The diff the user approves. Nothing is written here."""
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_WRITE:
        raise ValueError(f"Write up to {_size(MAX_WRITE)} of text.")
    p = resolve(path)
    if p.suffix.lower() not in TEXT:
        raise ValueError("Tsubasa writes text, code, Markdown, CSV and JSON files.")
    if p.exists() and not p.is_file():
        raise ValueError("That path is a folder.")
    if not p.parent.is_dir():
        raise ValueError("The folder for that file does not exist.")
    old = p.read_text("utf-8-sig", "replace") if p.exists() else None
    diff = "".join(difflib.unified_diff((old or "").splitlines(True), content.splitlines(True),
                                        fromfile=p.name + (" (now)" if old is not None else " (new file)"),
                                        tofile=p.name + " (after)", n=2))
    return {"path": str(p), "exists": old is not None, "diff": diff[:20000] or "(no changes)",
            "mtime": p.stat().st_mtime_ns if old is not None else None}


def write_file(plan, content):
    p = resolve(plan["path"])
    now = p.stat().st_mtime_ns if p.exists() else None
    if now != plan["mtime"]:
        raise ValueError("The file changed after you approved the change. Ask again.")
    tmp = p.with_name(p.name + ".tsubasa-tmp")
    tmp.write_text(content, encoding="utf-8", newline="")
    os.replace(tmp, p)
    return {"path": str(p), "text": f"Saved {p} ({_size(len(content.encode('utf-8')))})."}


def _size(n):
    return f"{n} B" if n < 1024 else f"{n / 1024:.0f} KB" if n < 1024 ** 2 else f"{n / 1024 ** 2:.1f} MB"
