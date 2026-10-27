"""Installed programs + when you last really used them.

Usage evidence (strongest first, all read-only):
  * UserAssist  - Explorer's own record of programs you started (per user, no admin needed)
  * BAM         - Background Activity Moderator, last execution per exe (readable when Windows allows it)
  * Prefetch    - C:\\Windows\\Prefetch (only when Kaizen runs as administrator)
  * Last access - the exe's last-access time (approximate fallback)
"""
import codecs
import glob
import json
import os
import re
import threading
import time
import winreg

from . import db, winshell

DAY = 86400
UNINSTALL_KEYS = [
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
]

PROTECT = [
    (r"driver|chipset|firmware|bios|realtek|elan|synaptics|dolby|audio codec|bluetooth|wi-?fi|wlan|thunderbolt",
     "Hardware driver or firmware tool"),
    (r"\bamd\b|radeon|ryzen|adrenalin|nvidia|intel\b|qualcomm|mediatek", "Chip / graphics vendor software"),
    (r"redistributable|runtime|\.net|dotnet|visual c\+\+|vc_?redist|directx|vulkan|webview2|java\b|openal|physx",
     "Shared runtime other programs depend on"),
    (r"^microsoft (edge|windows|update|onedrive)|windows (sdk|driver|app|security|subsystem|terminal)|"
     r"microsoft 365|microsoft office|teams machine", "Part of Windows / Microsoft"),
    (r"defender|antivirus|security|bitdefender|eset|avast|avg\b|norton|kaspersky|malwarebytes|sophos|mcafee",
     "Security software"),
    (r"^python \d|python launcher|fastflowlm|\bflm\b", "Kaizen needs this to run"),
]

FAMILIES = {
    "PDF readers": r"acrobat|foxit|sumatra|pdf-xchange|pdfgear|nitro pdf|pdf24",
    "Web browsers": r"google chrome|firefox|opera|brave|vivaldi|tor browser|waterfox|librewolf|arc\b",
    "Media players": r"\bvlc\b|mpc-hc|mpc-be|potplayer|kmplayer|gom player|mpv|winamp|aimp",
    "Archivers": r"7-zip|winrar|peazip|bandizip|winzip|nanazip",
    "Office suites": r"libreoffice|openoffice|wps office|onlyoffice|softmaker|freeoffice",
    "Cloud storage": r"dropbox|google drive|mega(sync)?\b|box drive|pcloud|sync\.com|icloud",
    "Local AI apps": r"lm studio|ollama|gpt4all|\bjan\b|anythingllm|msty|koboldcpp|text-generation|amuse",
    "Image viewers": r"irfanview|xnview|faststone|imageglass|honeyview|nomacs",
    "Screenshot tools": r"sharex|greenshot|lightshot|snagit|flameshot|picpick",
    "Torrent clients": r"qbittorrent|utorrent|bittorrent|deluge|transmission|tixati",
    "Messengers": r"whatsapp|telegram|signal|viber|skype|messenger",
    "Code editors": r"visual studio code|vscodium|notepad\+\+|sublime|cursor|zed\b|windsurf|antigravity",
}

PF_IGNORE = {"common files", "windowsapps", "modifiablewindowsapps", "windows defender", "windows mail",
             "windows media player", "windows nt", "windows photo viewer", "windows portable devices",
             "windows security", "windows sidebar", "windowspowershell", "internet explorer", "microsoft.net",
             "reference assemblies", "msbuild", "dotnet", "packagemanagement", "uninstall information",
             "microsoft update health tools", "windows defender advanced threat protection", "amd", "ati technologies",
             "realtek", "intel", "nvidia corporation", "microsoft", "microsoft office", "microsoft onedrive",
             "windows kits", "microsoft sdks", "iis", "iis express", "dell", "hp", "lenovo", "asus", "acer", "msi"}


def _filetime(ft):
    return ft / 1e7 - 11644473600 if ft else 0


def _q(key, name, default=None):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def installed_programs():
    out = {}
    for hive, path in UNINSTALL_KEYS:
        for view in (winreg.KEY_WOW64_64KEY,) if hive == winreg.HKEY_LOCAL_MACHINE else (0,):
            try:
                root = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            with root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        sub = winreg.EnumKey(root, i)
                        k = winreg.OpenKey(root, sub)
                    except OSError:
                        continue
                    with k:
                        name = _q(k, "DisplayName")
                        if not name or _q(k, "SystemComponent") == 1 or _q(k, "ParentKeyName") or \
                                (_q(k, "ReleaseType") or "") in ("Update", "Hotfix", "Security Update"):
                            continue
                        last_write = _filetime(winreg.QueryInfoKey(k)[2])
                        date = _q(k, "InstallDate") or ""
                        installed = last_write
                        if re.fullmatch(r"\d{8}", str(date)):
                            try:
                                installed = time.mktime(time.strptime(str(date), "%Y%m%d"))
                            except ValueError:
                                pass
                        icon = (_q(k, "DisplayIcon") or "").split(",")[0].strip().strip('"')
                        location = (_q(k, "InstallLocation") or "").strip().strip('"').rstrip("\\")
                        if not location and icon.lower().endswith(".exe"):
                            location = os.path.dirname(icon)
                        size = _q(k, "EstimatedSize")
                        key = f"{name}|{_q(k, 'Publisher') or ''}".lower()
                        if key in out:
                            continue
                        out[key] = {
                            "key": key, "kind": "app", "name": name.strip(), "publisher": (_q(k, "Publisher") or "").strip(),
                            "version": str(_q(k, "DisplayVersion") or ""), "installed": installed,
                            "size": int(size) * 1024 if isinstance(size, int) else 0, "location": location,
                            "exe": icon if icon.lower().endswith(".exe") and os.path.exists(icon) else "",
                            "uninstall": _q(k, "UninstallString") or "", "last_run": 0, "run_count": 0,
                            "evidence": [],
                        }
    return list(out.values())


def userassist():
    """Programs started through Explorer/Start/taskbar: {exe_path_lower: (last_run, count)}."""
    out = {}
    base = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
    folder_cache = {}
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base)
    except OSError:
        return out
    with root:
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                count_key = winreg.OpenKey(root, winreg.EnumKey(root, i) + r"\Count")
            except OSError:
                continue
            with count_key:
                for j in range(winreg.QueryInfoKey(count_key)[1]):
                    try:
                        name, data, _ = winreg.EnumValue(count_key, j)
                    except OSError:
                        continue
                    if not isinstance(data, bytes) or len(data) < 68:
                        continue
                    path = codecs.decode(name, "rot_13")
                    m = re.match(r"^(\{[0-9A-Fa-f-]{36}\})(.*)$", path)
                    if m:
                        g = m.group(1).upper()
                        if g not in folder_cache:
                            folder_cache[g] = winshell.known_folder(g)
                        if not folder_cache[g]:
                            continue
                        path = folder_cache[g] + m.group(2)
                    if not re.match(r"^[A-Za-z]:\\", path):
                        continue
                    count = int.from_bytes(data[4:8], "little")
                    last = _filetime(int.from_bytes(data[60:68], "little"))
                    targets = [path]
                    if path.lower().endswith(".lnk"):
                        t = winshell.lnk_target(path)
                        if t:
                            targets.append(t)
                    for t in targets:
                        k = t.lower()
                        prev = out.get(k, (0, 0))
                        out[k] = (max(prev[0], last), prev[1] + count)
    return out


def bam():
    out = {}
    devices = winshell.device_map()
    base = r"SYSTEM\CurrentControlSet\Services\bam\State\UserSettings"
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base)
    except OSError:
        return out
    with root:
        for i in range(winreg.QueryInfoKey(root)[0]):
            try:
                k = winreg.OpenKey(root, winreg.EnumKey(root, i))
            except OSError:
                continue
            with k:
                for j in range(winreg.QueryInfoKey(k)[1]):
                    try:
                        name, data, _ = winreg.EnumValue(k, j)
                    except OSError:
                        continue
                    if not isinstance(data, bytes) or len(data) < 8 or not name.lower().startswith("\\device\\"):
                        continue
                    parts = name.split("\\")
                    dev = "\\".join(parts[:3]).lower()
                    if dev in devices:
                        out[(devices[dev] + "\\" + "\\".join(parts[3:])).lower()] = \
                            _filetime(int.from_bytes(data[:8], "little"))
    return out


def prefetch():
    out = {}
    for pf in glob.glob(r"C:\Windows\Prefetch\*.pf"):
        exe = os.path.basename(pf).rsplit("-", 1)[0].lower()
        try:
            out[exe] = max(out.get(exe, 0), os.path.getmtime(pf))
        except OSError:
            pass
    return out


def _exes(location, limit=300):
    found = []
    if not location or not os.path.isdir(location):
        return found
    for dirpath, dirnames, filenames in os.walk(location):
        depth = dirpath[len(location):].count(os.sep)
        if depth >= 2:
            dirnames[:] = []
        for fn in filenames:
            if fn.lower().endswith(".exe") and not re.search(r"unins|uninst|setup|update|crash|helper", fn, re.I):
                found.append(os.path.join(dirpath, fn))
                if len(found) >= limit:
                    return found
    return found


def _dir_size(path, cap=40000):
    total, n = 0, 0
    newest = 0
    for dirpath, _, filenames in os.walk(path):
        for fn in filenames:
            try:
                st = os.stat(os.path.join(dirpath, fn))
            except OSError:
                continue
            total += st.st_size
            newest = max(newest, st.st_mtime)
            n += 1
            if n >= cap:
                return total, newest
    return total, newest


def ago(seconds):
    days = seconds / DAY
    if days < 60:
        return f"{max(int(days), 1)} days"
    if days < 730:
        return f"{int(days / 30.4)} months"
    return f"{days / 365:.0f} years"


JUNK_EXE = re.compile(r"(?i)unins|setup|install|update|crash|helper|redist|quicksfv|vc_?redist|dxsetup|report|"
                      r"elevat|service|notif|bootstrap")


def _best_exe(p, exes, launched):
    """The exe that represents the program: the one you actually launch, named like the program."""
    tokens = set(re.findall(r"[a-z0-9]{3,}", p["name"].lower()))
    loc = os.path.normcase(p["location"]) if p["location"] else ""

    def score(e):
        base = os.path.splitext(os.path.basename(e))[0].lower()
        s = 4 if e.lower() in launched else 0
        s += 2 if any(t in base for t in tokens) else 0
        s -= 5 if JUNK_EXE.search(base) else 0
        s += 1 if loc and os.path.normcase(os.path.dirname(e)) == loc else 0
        try:
            size = os.path.getsize(e)
        except OSError:
            size = 0
        return s, size

    return max(exes, key=score) if exes else ""


def fill_sizes(keys_and_paths):
    """Program folders without a registry size are measured after the scan, so the scan itself stays quick."""
    for key, path in keys_and_paths:
        size, _ = _dir_size(path, cap=60000)
        with db.conn() as c:
            c.execute("UPDATE programs SET size=? WHERE key=? AND (size IS NULL OR size=0)", (size, key))


def scan_programs(settings, progress):
    progress.set(phase="Reading installed programs")
    now = time.time()
    programs = installed_programs()
    ua, bm, pf = userassist(), bam(), prefetch()
    launched = set(ua) | set(bm)
    stale = settings["program_stale_days"] * DAY
    kept = {r["path"] for r in db.rows("SELECT path FROM kept")}
    need_size = []

    for p in programs:
        loc = os.path.normcase(p["location"]) if p["location"] else ""
        exes = _exes(p["location"]) if loc else []
        if p["exe"] and p["exe"] not in exes:
            exes.insert(0, p["exe"])
        p["exe"] = _best_exe(p, exes, launched)
        if not p["size"] and loc and os.path.isdir(p["location"]) and len(loc) > 4:
            need_size.append((p["key"], p["location"]))
        names = {os.path.basename(e).lower() for e in exes}
        ev = set()

        def under(path):
            return loc and len(loc) > 3 and (path.startswith(loc.lower() + "\\") or path == loc.lower())

        for path, (last, count) in ua.items():
            if under(path) or path in (e.lower() for e in exes[:5]):
                p["run_count"] += count
                if last > p["last_run"]:
                    p["last_run"] = last
                    ev.add("Start menu & taskbar history")
        for path, last in bm.items():
            if under(path):
                p["last_run"] = max(p["last_run"], last)
                ev.add("Windows activity log")
        for n in names:
            if n in pf:
                p["last_run"] = max(p["last_run"], pf[n])
                ev.add("Prefetch")
        if not ev:
            for e in exes[:20]:
                try:
                    at = os.stat(e).st_atime
                except OSError:
                    continue
                if at > p["last_run"]:
                    p["last_run"] = at
                    ev.add("File access time (approximate)")
        p["evidence"] = sorted(ev)

        text = f"{p['name']} {p['publisher']}".lower()
        p["protected"], p["protect_reason"] = 0, ""
        for pattern, why in PROTECT:
            if re.search(pattern, text):
                p["protected"], p["protect_reason"] = 1, why
                break

        p["reasons"], p["i_sort"], p["i_std"], p["i_shine"], p["sustained"], p["dup_group"] = [], 0, 0, 0, 0, None
        if p["key"] in kept:
            p["sustained"] = 1
            continue
        if p["last_run"] and now - p["last_run"] <= 30 * DAY:
            p["sustained"] = 1
        if p["protected"]:
            continue
        if p["last_run"] and now - p["last_run"] > stale:
            p["i_sort"] = 1
            p["reasons"].append({"s": "sort", "t": f"Last used {ago(now - p['last_run'])} ago"})
        elif not p["last_run"] and now - p["installed"] > stale:
            p["i_sort"] = 1
            p["reasons"].append({"s": "sort", "t": f"No record of use since it was installed "
                                                   f"{ago(now - p['installed'])} ago"})
        for family, pattern in FAMILIES.items():
            if re.search(pattern, p["name"].lower()):
                p["dup_group"] = family
                break

    # Seiketsu: several programs doing the same job
    groups = {}
    for p in programs:
        if p["dup_group"]:
            groups.setdefault(p["dup_group"], []).append(p)
    for family, members in groups.items():
        if len(members) < 2:
            for m in members:
                m["dup_group"] = None
            continue
        members.sort(key=lambda m: m["last_run"], reverse=True)
        for m in members[1:]:
            m["i_std"] = 1
            m["reasons"].append({"s": "std", "t": f"You have {len(members)} {family.lower()} – "
                                                  f"“{members[0]['name']}” is the one you use most recently"})

    # Seiso: leftover folders in Program Files from programs that are gone
    progress.set(phase="Looking for leftovers")
    known = [os.path.normcase(p["location"]) for p in programs if p["location"]]
    known += [os.path.normcase(os.path.dirname(p["exe"])) for p in programs if p["exe"]]
    known += [os.path.normcase(re.sub(r'^"?([^"]+?\.exe).*$', r"\1", p["uninstall"])) for p in programs
              if p["uninstall"]]
    words = set()
    for p in programs:
        words |= set(re.findall(r"[a-z0-9]{3,}", f"{p['name']} {p['publisher']}".lower()))
    leftovers = []
    for pf_root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                    os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        try:
            entries = list(os.scandir(pf_root))
        except OSError:
            continue
        for e in entries:
            if not e.is_dir() or e.name.lower() in PF_IGNORE:
                continue
            key = os.path.normcase(e.path)
            if any(k == key or k.startswith(key + "\\") for k in known):
                continue
            tokens = set(re.findall(r"[a-z0-9]{3,}", e.name.lower()))
            if tokens and tokens <= words:
                continue
            size, newest = _dir_size(e.path, cap=4000)
            if newest and now - newest < 365 * DAY:
                continue
            leftovers.append({
                "key": "leftover|" + e.path.lower(), "kind": "leftover", "name": e.name, "publisher": "",
                "version": "", "installed": newest, "size": size, "location": e.path, "exe": "", "uninstall": "",
                "last_run": newest, "run_count": 0, "evidence": ["Folder contents unchanged"], "protected": 0,
                "protect_reason": "", "i_sort": 0, "i_std": 0, "i_shine": 1, "sustained": 0, "dup_group": None,
                "reasons": [{"s": "shine", "t": f"Possible leftover folder, no installed program uses it, "
                                                f"untouched for {ago(now - newest) if newest else 'a long time'}"}],
            })

    c = db.conn()
    with c:
        c.execute("DELETE FROM programs")
        c.executemany(
            "INSERT OR REPLACE INTO programs(key,kind,name,publisher,version,installed,size,location,exe,uninstall,"
            "last_run,run_count,evidence,protected,protect_reason,i_sort,i_shine,i_std,sustained,reasons,dup_group) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(p["key"], p["kind"], p["name"], p["publisher"], p["version"], p["installed"], p["size"],
              p["location"], p["exe"], p["uninstall"], p["last_run"], p["run_count"], json.dumps(p["evidence"]),
              p["protected"], p["protect_reason"], p["i_sort"], p["i_shine"], p["i_std"], p["sustained"],
              json.dumps(p["reasons"], ensure_ascii=False), p["dup_group"]) for p in programs + leftovers])
    threading.Thread(target=fill_sizes, args=(need_size,), daemon=True).start()
    return {"programs": len(programs), "leftovers": len(leftovers), "userassist": len(ua), "bam": len(bm),
            "prefetch": len(pf), "sizing_later": len(need_size)}
