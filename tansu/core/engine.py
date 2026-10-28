"""Creating, verifying, listing and extracting archives.

ZIP and TAR.XZ use Python's own zipfile/tarfile, 7z uses py7zr (LZMA2 + AES-256): all in-process, so Slovak,
Cyrillic or emoji file names work (Windows' tar.exe mangles them). Archives are written to a .part file, checked,
and only then renamed - a crash never leaves a half archive behind under the real name.
"""
import os
import shutil
import stat
import subprocess
import tarfile
import threading
import time
import zipfile

import py7zr

from .rules import LEVELS
from .scan import CAT_LABEL, PRECOMPRESSED, _ext

CREATE_NO_WINDOW = 0x08000000
CHUNK = 1 << 20


class Cancelled(Exception):
    pass


def fmt_of(path):
    n = path.lower()
    for ext, fmt in ((".tar.xz", "tar.xz"), (".txz", "tar.xz"), (".tar.gz", "tar.gz"), (".tgz", "tar.gz"),
                     (".tar.bz2", "tar.bz2"), (".tbz2", "tar.bz2"), (".tar.zst", "tar.zst"), (".tar", "tar"),
                     (".zip", "zip"), (".7z", "7z"), (".rar", "rar")):
        if n.endswith(ext):
            return fmt
    return None


# ---------------------------------------------------------------- layout inside the archive
def mapping(files, empty_dirs, layout, skip_junk=True):
    """[(src or None for a directory, name inside the archive)] for the chosen layout."""
    out, taken = [], set()

    def add(src, arc):
        arc = arc.strip("/")
        base, ext = os.path.splitext(arc)
        i = 2
        while arc.lower() in taken:
            arc = f"{base} ({i}){ext}"
            i += 1
        taken.add(arc.lower())
        out.append((src, arc))

    for f in files:
        if skip_junk and f["junk"]:
            continue
        name = f["rel"].rsplit("/", 1)[-1]
        if layout == "by_type":
            add(f["src"], f"{CAT_LABEL.get(f['cat'], 'Other')}/{name}")
        elif layout == "by_date":
            t = time.localtime(f["mtime"])
            add(f["src"], f"{t.tm_year}/{t.tm_year}-{t.tm_mon:02d}/{name}")
        elif layout == "flat":
            add(f["src"], name)
        else:
            add(f["src"], f["rel"])
    if layout == "keep":
        for d in empty_dirs:
            if not (skip_junk and any(p.lower() in ("node_modules", "__pycache__") for p in d.split("/"))):
                out.append((None, d.strip("/") + "/"))
    return out


def preview(m, limit=16):
    """A compact tree of the first entries, for the UI."""
    lines, shown_dirs = [], set()
    for src, arc in sorted(m, key=lambda x: x[1].lower()):
        parts = arc.rstrip("/").split("/")
        for depth in range(len(parts) - 1):
            d = "/".join(parts[: depth + 1])
            if d not in shown_dirs:
                shown_dirs.add(d)
                lines.append({"depth": depth, "name": parts[depth], "dir": True})
        if not arc.endswith("/"):
            lines.append({"depth": len(parts) - 1, "name": parts[-1], "dir": False})
        if len(lines) >= limit:
            break
    return lines


# ---------------------------------------------------------------- creating
class Progress:
    def __init__(self, total, cb, cancel):
        self.total, self.done, self.cb, self.cancel = max(total, 1), 0, cb, cancel
        self._last = 0

    def add(self, n):
        self.done += n
        now = time.time()
        if now - self._last > .15:
            self._last = now
            self.cb(min(self.done / self.total, 1.0))
        if self.cancel.is_set():
            raise Cancelled()


class Reader:
    """A file object that reports how much was read (tarfile pulls data through it)."""
    def __init__(self, f, prog):
        self.f, self.prog = f, prog

    def read(self, n=-1):
        b = self.f.read(n if n and n > 0 else CHUNK)
        self.prog.add(len(b))
        return b


def _store(src, ext):
    return ext in PRECOMPRESSED


def write_zip(part, m, level, prog, append_from=None):
    if append_from:
        shutil.copy2(append_from, part)
    lvl = LEVELS[level]["zip"]
    with zipfile.ZipFile(part, "a" if append_from else "w", zipfile.ZIP_DEFLATED, allowZip64=True,
                         compresslevel=lvl, strict_timestamps=False) as z:
        existing = {n.lower() for n in z.namelist()} if append_from else set()
        for src, arc in m:
            if arc.lower() in existing:
                base, ext = os.path.splitext(arc)
                i = 2
                while f"{base} ({i}){ext}".lower() in existing:
                    i += 1
                arc = f"{base} ({i}){ext}"
            existing.add(arc.lower())
            if src is None:
                z.writestr(zipfile.ZipInfo(arc), b"")
                continue
            zi = zipfile.ZipInfo.from_file(src, arc, strict_timestamps=False)
            zi.compress_type = zipfile.ZIP_STORED if _store(src, _ext(arc)) else zipfile.ZIP_DEFLATED
            for attr in ("_compresslevel", "compress_level"):   # renamed in Python 3.13
                try:
                    setattr(zi, attr, lvl)
                except AttributeError:
                    pass
            size = os.path.getsize(src)
            with open(src, "rb") as f, z.open(zi, "w", force_zip64=size > 0x7FFF0000) as out:
                while True:
                    b = f.read(CHUNK)
                    if not b:
                        break
                    out.write(b)
                    prog.add(len(b))


def write_7z(part, m, level, prog, password=None):
    filters = [{"id": py7zr.FILTER_LZMA2, "preset": LEVELS[level]["lzma"]}]
    if password:
        filters.append({"id": py7zr.FILTER_CRYPTO_AES256_SHA256})
    stop = threading.Event()
    state = {"base": 0, "cur": 0, "start": 0}

    def watch():  # py7zr has no byte callback; follow the growing file for a smooth bar on big files
        while not stop.wait(.4):
            try:
                grown = os.path.getsize(part) - state["start"]
            except OSError:
                continue
            est = min(state["cur"], grown * 2.2)
            prog.cb(min((state["base"] + est) / prog.total, .99))

    threading.Thread(target=watch, daemon=True).start()
    try:
        with py7zr.SevenZipFile(part, "w", filters=filters, password=password or None,
                                header_encryption=bool(password)) as z:
            for src, arc in m:
                if src is None:
                    continue  # empty folders are not worth a special case in 7z
                size = os.path.getsize(src)
                state.update(cur=size, start=os.path.getsize(part) if os.path.exists(part) else 0)
                z.write(src, arc)
                state["base"] += size
                prog.add(size)
    finally:
        stop.set()


def write_tar(part, m, level, prog):
    with tarfile.open(part, "w:xz", preset=LEVELS[level]["lzma"], format=tarfile.PAX_FORMAT) as t:
        for src, arc in m:
            if src is None:
                ti = tarfile.TarInfo(arc.rstrip("/"))
                ti.type, ti.mode, ti.mtime = tarfile.DIRTYPE, 0o755, time.time()
                t.addfile(ti)
                continue
            ti = t.gettarinfo(src, arc)
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            with open(src, "rb") as f:
                t.addfile(ti, Reader(f, prog))


def create(out, fmt, level, m, cb, cancel, password=None, append_from=None):
    """Writes the archive to out (via out.part). cb(fraction) reports progress."""
    total = sum(os.path.getsize(s) for s, _ in m if s)
    prog = Progress(total, cb, cancel)
    part = out + ".part"
    if os.path.exists(part):
        os.remove(part)
    try:
        if fmt == "zip":
            write_zip(part, m, level, prog, append_from)
        elif fmt == "7z":
            write_7z(part, m, level, prog, password)
        elif fmt == "tar.xz":
            write_tar(part, m, level, prog)
        else:
            raise ValueError(f"Tansu cannot create {fmt}")
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise
    return part, total


# ---------------------------------------------------------------- reading
def _entry(name, size, mtime, is_dir=False, packed=None):
    return {"name": name.replace("\\", "/").rstrip("/"), "size": int(size or 0), "mtime": mtime, "dir": is_dir,
            "packed": packed}


def listing(path, password=None):
    fmt = fmt_of(path)
    if fmt == "zip":
        with zipfile.ZipFile(path) as z:
            return [_entry(i.filename, i.file_size, time.mktime(i.date_time + (0, 0, -1)) if i.date_time[0] > 1979 else None,
                           i.is_dir(), i.compress_size) for i in z.infolist()]
    if fmt == "7z":
        with py7zr.SevenZipFile(path, password=password or None) as z:
            return [_entry(i.filename, i.uncompressed, i.creationtime.timestamp() if i.creationtime else None,
                           i.is_directory) for i in z.list()]
    if fmt in ("tar.xz", "tar.gz", "tar.bz2", "tar"):
        with tarfile.open(path) as t:
            return [_entry(i.name, i.size, i.mtime, i.isdir()) for i in t.getmembers()]
    # anything else (rar, tar.zst...): Windows' own libarchive can at least list it
    r = subprocess.run(["tar", "-tf", path], capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=120)
    if r.returncode:
        raise ValueError(r.stderr.decode("utf-8", "replace").strip() or "cannot read this archive")
    return [_entry(n, 0, None, n.endswith("/")) for n in r.stdout.decode("utf-8", "replace").splitlines() if n]


def is_encrypted(path):
    fmt = fmt_of(path)
    try:
        if fmt == "7z":
            with py7zr.SevenZipFile(path) as z:
                return z.needs_password()
        if fmt == "zip":
            with zipfile.ZipFile(path) as z:
                return any(i.flag_bits & 1 for i in z.infolist())
    except py7zr.exceptions.PasswordRequired:
        return True
    except Exception:
        return False
    return False


def verify(path, password=None, expect=None, cb=None, cancel=None):
    """Re-read everything and check the checksums. Returns (ok, message)."""
    fmt = fmt_of(path) or ("7z" if path.endswith(".7z.part") else "zip" if path.endswith(".zip.part") else
                           "tar.xz" if path.endswith(".tar.xz.part") else None)
    cb = cb or (lambda f: None)
    try:
        if fmt == "zip":
            with zipfile.ZipFile(path) as z:
                infos = z.infolist()
                total = sum(i.file_size for i in infos) or 1
                done = 0
                for i in infos:
                    if i.is_dir():
                        continue
                    with z.open(i) as f:        # reading to the end checks the CRC
                        while True:
                            b = f.read(CHUNK)
                            if not b:
                                break
                            done += len(b)
                            if cancel is not None and cancel.is_set():
                                raise Cancelled()
                    cb(done / total)
                names = {i.filename.rstrip("/"): i.file_size for i in infos}
        elif fmt == "7z":
            with py7zr.SevenZipFile(path, password=password or None) as z:
                bad = z.testzip()
                if bad:
                    return False, f"checksum error in {bad}"
                names = {i.filename: i.uncompressed for i in z.list()}
        elif fmt in ("tar.xz", "tar.gz", "tar.bz2", "tar"):
            with tarfile.open(path, "r:*") as t:
                names = {}
                for i in t:
                    names[i.name] = i.size
                    if i.isfile():
                        f = t.extractfile(i)
                        while f.read(CHUNK):
                            if cancel is not None and cancel.is_set():
                                raise Cancelled()
        else:
            r = subprocess.run(["tar", "-tf", path], capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=600)
            return r.returncode == 0, "readable" if r.returncode == 0 else "unreadable"
    except Cancelled:
        raise
    except Exception as e:
        if password and (isinstance(e, TypeError) or "password" in str(e).lower() or type(e).__name__ == "Bad7zFile"):
            return False, "wrong password (or the archive is damaged)"
        return False, f"{type(e).__name__}: {e}"
    if expect:
        missing = [a for a, s in expect.items() if a not in names]
        wrong = [a for a, s in expect.items() if a in names and names[a] != s]
        if missing or wrong:
            return False, f"{len(missing)} missing, {len(wrong)} with the wrong size (e.g. {(missing + wrong)[0]})"
    return True, f"{len(names)} entries, all checksums OK"


def _safe(dest, name):
    p = os.path.normpath(os.path.join(dest, name))
    if not (p == dest or p.startswith(dest.rstrip("\\") + "\\")):
        raise ValueError(f"unsafe path in archive: {name}")
    return p


def extract(path, dest, members=None, password=None, cb=None, cancel=None):
    """Extract all (or only `members`, names or folder prefixes) into dest. Returns the number of files."""
    dest = os.path.abspath(dest)
    os.makedirs(dest, exist_ok=True)
    cb = cb or (lambda f: None)
    fmt = fmt_of(path)
    want = None
    if members:
        pref = [m.rstrip("/") for m in members]
        want = lambda n: any(n.rstrip("/") == p or n.startswith(p + "/") for p in pref)
    n = 0
    if fmt == "zip":
        with zipfile.ZipFile(path) as z:
            infos = [i for i in z.infolist() if not want or want(i.filename)]
            total = sum(i.file_size for i in infos) or 1
            done = 0
            for i in infos:
                _safe(dest, i.filename)
                z.extract(i, dest, pwd=password.encode() if password else None)
                done += i.file_size
                n += not i.is_dir()
                cb(done / total)
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                if i.date_time[0] > 1979 and not i.is_dir():
                    t = time.mktime(i.date_time + (0, 0, -1))
                    os.utime(os.path.join(dest, i.filename), (t, t))
    elif fmt == "7z":
        with py7zr.SevenZipFile(path, password=password or None) as z:
            names = [i.filename for i in z.list()]
            targets = [x for x in names if not want or want(x)]
            for x in targets:
                _safe(dest, x)
            if want:
                z.extract(path=dest, targets=targets)
            else:
                z.extractall(path=dest)
            n = len(targets)
    elif fmt in ("tar.xz", "tar.gz", "tar.bz2", "tar"):
        with tarfile.open(path, "r:*") as t:
            ms = [m for m in t.getmembers() if not want or want(m.name)]
            t.extractall(dest, members=ms, filter="data")
            n = sum(m.isfile() for m in ms)
    else:
        r = subprocess.run(["tar", "-xf", path], cwd=dest, capture_output=True, creationflags=CREATE_NO_WINDOW)
        if r.returncode:
            raise ValueError(r.stderr.decode("utf-8", "replace").strip())
        n = sum(len(f) for _, _, f in os.walk(dest))
    cb(1.0)
    return n


def make_writable(p):
    try:
        os.chmod(p, stat.S_IWRITE)
    except OSError:
        pass
