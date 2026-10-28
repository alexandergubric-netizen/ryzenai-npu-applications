"""Looks at what the user wants to archive: every file, its type, dates, junk, and how well it really compresses.

The compression numbers are measured, not guessed: a sample of the files is compressed with deflate (ZIP)
and LZMA2 (7z / xz) right here, which also times this PC's speed for the size/time estimates.
"""
import lzma
import os
import re
import stat
import time
import zlib
from collections import Counter, defaultdict

CATS = {
    "photo": "jpg jpeg png heic heif webp avif gif bmp tif tiff raw cr2 cr3 nef arw dng orf rw2 raf srw jfif",
    "video": "mp4 mkv mov avi wmv webm m4v mts m2ts 3gp flv mpg mpeg ts vob",
    "audio": "mp3 m4a aac flac wav ogg opus wma aiff aif alac mid midi amr",
    "document": "pdf doc docx odt rtf txt md pages tex wpd xps oxps",
    "spreadsheet": "xls xlsx xlsm xlsb ods csv tsv numbers",
    "presentation": "ppt pptx pps ppsx odp key",
    "ebook": "epub mobi azw azw3 fb2 djvu cbz cbr",
    "code": "py pyw js mjs ts jsx tsx java c cc cpp h hpp cs go rs rb php html htm css scss less json yaml yml "
            "toml xml sh ps1 psm1 bat cmd sql ipynb kt swift vue svelte lua r m gradle sln csproj vcxproj ini cfg",
    "design": "psd psb ai svg sketch fig xd indd blend fbx obj stl 3mf dwg dxf kra xcf afdesign afphoto cdr eps",
    "archive": "zip 7z rar gz tgz xz txz bz2 zst tar cab iso img dmg",
    "software": "exe msi msix msixbundle appx apk dll sys jar appimage deb rpm",
    "data": "db sqlite sqlite3 mdb accdb parquet bak dat log sav bin dump",
    "font": "ttf otf woff woff2 fon",
    "mail": "eml msg pst ost mbox",
}
EXT_CAT = {e: c for c, exts in CATS.items() for e in exts.split()}
CAT_LABEL = {"photo": "Photos", "video": "Videos", "audio": "Audio", "document": "Documents",
             "spreadsheet": "Spreadsheets", "presentation": "Presentations", "ebook": "E-books", "code": "Code",
             "design": "Design & 3D", "archive": "Archives", "software": "Software", "data": "Data & backups",
             "font": "Fonts", "mail": "Mail", "other": "Other"}

# formats that are compressed inside already - deflating them again only burns time
PRECOMPRESSED = set(("jpg jpeg jfif heic heif webp avif gif png mp4 mkv mov m4v webm wmv 3gp flv mts m2ts "
                     "mp3 m4a aac ogg opus flac wma amr zip 7z rar gz tgz xz txz bz2 zst cab docx xlsx xlsm pptx "
                     "ppsx odt ods odp epub cbz cbr jar apk msix appx woff woff2 cr3 dng arw nef pdf").split())

JUNK_NAMES = {"thumbs.db", "desktop.ini", ".ds_store", "ehthumbs.db", "ehthumbs_vista.db", "$recycle.bin",
              "system volume information", ".localized"}
JUNK_DIRS = {"node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache", ".gradle", ".next",
             ".cache", ".parcel-cache", ".tox", ".idea", ".vs", "obj", ".terraform"}
JUNK_RE = re.compile(r"^(~\$.*|.*\.tmp|.*\.temp|.*\.crdownload|.*\.part|.*\.partial|~.*\.tmp)$", re.I)

SENSITIVE = re.compile(
    r"pas+port|passport|id[ _-]?card|identity|občian|obcian|rodn[ýy]|birth|tax|daň|dan[eě]|danov|invoice|faktur|"
    r"zmluv|contract|agreement|bank|výpis|vypis|statement|salary|payslip|mzd|výplat|vyplat|medical|lekár|lekar|"
    r"zdravot|insurance|poist|heslo|password|secret|private|súkrom|sukrom|osobn|personal|wallet|seed|recovery|"
    r"\.kdbx$|\.pem$|\.key$|\.pfx$|\.p12$|id_rsa|\.ovpn$|resume|cv[ _.-]|životopis|zivotopis|diplom|vysvedčen", re.I)
PROJECT_MARKERS = {".git", "package.json", "pyproject.toml", "setup.py", "requirements.txt", "cargo.toml",
                   "go.mod", "pom.xml", "build.gradle", "makefile", "cmakelists.txt", "composer.json", "gemfile"}

MAX_FILES = 400_000


def category(ext):
    return EXT_CAT.get(ext, "other")


def _ext(name):
    n = name.lower()
    for double in (".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst"):
        if n.endswith(double):
            return double[1:]
    return os.path.splitext(n)[1].lstrip(".")


def is_junk(name, is_dir=False):
    n = name.lower()
    if is_dir:
        return n in JUNK_DIRS or n in JUNK_NAMES
    return n in JUNK_NAMES or bool(JUNK_RE.match(n))


def _unique(name, taken):
    if name.lower() not in taken:
        taken.add(name.lower())
        return name
    stem, ext = os.path.splitext(name)
    i = 2
    while f"{stem} ({i}){ext}".lower() in taken:
        i += 1
    taken.add(f"{stem} ({i}){ext}".lower())
    return f"{stem} ({i}){ext}"


def walk(paths):
    """Every file under the given files/folders.

    Returns (files, empty_dirs, roots). Each file: src, rel (path inside the archive, starting with the
    top-level item's own name), size, mtime, ext, cat, junk. Links and junctions are not followed.
    """
    files, empty_dirs, roots, taken = [], [], [], set()
    for p in paths:
        p = os.path.normpath(p)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        name = _unique(os.path.basename(p.rstrip("\\/")) or p[0], taken)
        if stat.S_ISDIR(st.st_mode):
            root = {"path": p, "name": name, "dir": True, "size": 0, "files": 0}
            stack = [(p, name, False)]
            while stack and len(files) < MAX_FILES:
                d, rel, junk_parent = stack.pop()
                try:
                    entries = list(os.scandir(d))
                except OSError:
                    continue
                if not entries:
                    empty_dirs.append(rel)
                for e in entries:
                    try:
                        if e.is_symlink() or (e.is_dir(follow_symlinks=False) and e.stat(follow_symlinks=False).st_file_attributes & 0x400):
                            continue  # reparse points: never follow
                        r = rel + "/" + e.name
                        if e.is_dir(follow_symlinks=False):
                            stack.append((e.path, r, junk_parent or is_junk(e.name, True)))
                        elif e.is_file(follow_symlinks=False):
                            s = e.stat(follow_symlinks=False)
                            x = _ext(e.name)
                            files.append({"src": e.path, "rel": r, "size": s.st_size, "mtime": s.st_mtime, "ext": x,
                                          "cat": category(x), "junk": junk_parent or is_junk(e.name)})
                            root["size"] += s.st_size
                            root["files"] += 1
                    except OSError:
                        continue
            roots.append(root)
        elif stat.S_ISREG(st.st_mode):
            x = _ext(p)
            files.append({"src": p, "rel": name, "size": st.st_size, "mtime": st.st_mtime, "ext": x,
                          "cat": category(x), "junk": is_junk(name)})
            roots.append({"path": p, "name": name, "dir": False, "size": st.st_size, "files": 1})
    return files, empty_dirs, roots


def sample_compression(files, budget=1_400_000, per_file=96_000):
    """Compress a slice of up to ~40 files with deflate-6 and LZMA2-5; returns per-ext ratios and speeds."""
    real = [f for f in files if not f["junk"] and f["size"] > 0]
    if not real:
        return {}, {}, None
    # biggest files matter most for the total, but a few small ones keep the picture honest
    by_size = sorted(real, key=lambda f: -f["size"])
    picks, seen = by_size[:24], set()
    step = max(1, len(by_size) // 16)
    picks += by_size[24::step][:16]
    ratios_d, ratios_l = defaultdict(list), defaultdict(list)
    t_def = t_lz = raw = 0.0
    used = 0
    for f in picks:
        if f["src"] in seen or used >= budget:
            continue
        seen.add(f["src"])
        try:
            with open(f["src"], "rb") as fh:
                if f["size"] > per_file * 3:
                    fh.seek(f["size"] // 3)       # skip headers, sample the body
                data = fh.read(per_file)
        except OSError:
            continue
        if len(data) < 64:
            continue
        used += len(data)
        a = time.perf_counter()
        d = len(zlib.compress(data, 6))
        b = time.perf_counter()
        lz = len(lzma.compress(data, preset=5))
        c = time.perf_counter()
        t_def, t_lz, raw = t_def + b - a, t_lz + c - b, raw + len(data)
        ratios_d[f["ext"]].append(min(d / len(data), 1.0))
        ratios_l[f["ext"]].append(min(lz / len(data), 1.0))
    speeds = None
    if raw > 50_000:
        # measured on small blocks; real runs over large files are somewhat faster (warm dictionary, big buffers)
        speeds = {"deflate": raw / max(t_def, 1e-4) * 1.1, "lzma": raw / max(t_lz, 1e-4) * 1.15}
    avg = lambda d: {k: sum(v) / len(v) for k, v in d.items()}
    return avg(ratios_d), avg(ratios_l), speeds


PRIOR = {  # (deflate, lzma) ratios when a type was not sampled
    "photo": (.99, .98), "video": (.995, .99), "audio": (.98, .97), "archive": (1.0, .995),
    "document": (.55, .45), "spreadsheet": (.45, .3), "presentation": (.9, .87), "ebook": (.95, .93),
    "code": (.28, .2), "design": (.6, .5), "software": (.5, .38), "data": (.35, .22), "font": (.6, .5),
    "mail": (.45, .33), "other": (.6, .5),
}


def analyse(paths):
    """Facts about a set of files/folders, used by both the rules and the AI."""
    t0 = time.time()
    files, empty_dirs, roots = walk(paths)
    keep = [f for f in files if not f["junk"]]
    junk = [f for f in files if f["junk"]]
    rd, rl, speeds = sample_compression(keep)

    def ratio(f, which):
        table = rd if which == 0 else rl
        if f["ext"] in table:
            return table[f["ext"]]
        if f["ext"] in PRECOMPRESSED:
            return .995
        return PRIOR.get(f["cat"], PRIOR["other"])[which]

    total = sum(f["size"] for f in keep)
    est_deflate = sum(f["size"] * ratio(f, 0) for f in keep)
    est_lzma = sum(f["size"] * ratio(f, 1) for f in keep)
    by_cat = defaultdict(lambda: {"bytes": 0, "files": 0})
    for f in keep:
        by_cat[f["cat"]]["bytes"] += f["size"]
        by_cat[f["cat"]]["files"] += 1
    exts = Counter()
    ext_bytes = Counter()
    for f in keep:
        exts[f["ext"] or "(none)"] += 1
        ext_bytes[f["ext"] or "(none)"] += f["size"]
    pre = sum(f["size"] for f in keep if f["ext"] in PRECOMPRESSED or rd.get(f["ext"], 0) > .97)
    mt = sorted(f["mtime"] for f in keep) or [time.time()]
    years = Counter(time.localtime(f["mtime"]).tm_year for f in keep)
    months = Counter(time.strftime("%Y-%m", time.localtime(f["mtime"])) for f in keep)
    names_lower = {os.path.basename(f["rel"]).lower() for f in files}
    dir_names = sorted({part for f in keep for part in f["rel"].split("/")[:-1]}, key=lambda s: (len(s), s))
    sensitive = sorted({os.path.basename(f["rel"]) for f in keep if SENSITIVE.search(f["rel"])})
    markers = sorted(PROJECT_MARKERS & (names_lower | {d.lower() for d in dir_names}))
    sample_names = []
    for f in sorted(keep, key=lambda f: (-f["size"])):
        n = os.path.basename(f["rel"])
        if n not in sample_names:
            sample_names.append(n)
        if len(sample_names) >= 24:
            break
    return {
        "roots": roots,
        "files": files,
        "empty_dirs": empty_dirs,
        "total": total,
        "count": len(keep),
        "dirs": len(dir_names),
        "junk": {"files": len(junk), "bytes": sum(f["size"] for f in junk),
                 "examples": sorted({os.path.basename(f["rel"]) for f in junk})[:6]},
        "by_cat": dict(sorted(by_cat.items(), key=lambda kv: -kv[1]["bytes"])),
        "top_ext": [{"ext": e, "files": n, "bytes": ext_bytes[e]} for e, n in exts.most_common(8)],
        "precompressed": pre / total if total else 0,
        "est": {"deflate": est_deflate, "lzma": est_lzma},
        "speeds": speeds or {"deflate": 30e6, "lzma": 2.5e6},
        "dates": {"min": mt[0], "max": mt[-1], "years": dict(sorted(years.items())),
                  "top_month": months.most_common(1)[0][0] if months else None},
        "largest": [{"name": f["rel"], "size": f["size"]} for f in sorted(keep, key=lambda f: -f["size"])[:5]],
        "sensitive": sensitive[:12],
        "project": markers,
        "names": sample_names,
        "dir_names": dir_names[:20],
        "truncated": len(files) >= MAX_FILES,
        "scan_secs": round(time.time() - t0, 2),
    }


def public(a):
    """Everything except the per-file list (that stays on the server)."""
    return {k: v for k, v in a.items() if k != "files"}
