"""End-to-end check of the archive engine and library, in a throwaway library (never the real Documents\\Archives).

python tests/smoke.py          rules + every format + verify/list/extract + library/checkup + the web gate
python tests/smoke.py --ai     also asks the NPU model for a plan (FastFlowLM must be installed)
"""
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from core import config  # noqa: E402

TMP = tempfile.mkdtemp(prefix="tansu_smoke_")
LIB = os.path.join(TMP, "Archives")
_real_get = config.get
config.get = lambda: {**_real_get(), "root": LIB, "extract_dir": os.path.join(TMP, "out")}

from core import engine, rules, scan, store  # noqa: E402
from core.jobs import batches, jobs  # noqa: E402

ok = fail = 0


def check(cond, label):
    global ok, fail
    if cond:
        ok += 1
        print("  ok  ", label)
    else:
        fail += 1
        print("  FAIL", label)


def make_samples():
    src = os.path.join(TMP, "src")
    trip = os.path.join(src, "Dovolenka Chorvátsko 2024")
    os.makedirs(os.path.join(trip, "Deň 1 – Split"), exist_ok=True)
    os.makedirs(os.path.join(trip, "prázdny"), exist_ok=True)
    os.makedirs(os.path.join(trip, "node_modules", "x"), exist_ok=True)
    with open(os.path.join(trip, "Deň 1 – Split", "fotka 😀 ж.jpg"), "wb") as f:
        f.write(os.urandom(300_000))
    with open(os.path.join(trip, "poznámky.txt"), "w", encoding="utf-8") as f:
        f.write("Kúpať sa, jesť, spať. " * 4000)
    with open(os.path.join(trip, "Thumbs.db"), "wb") as f:
        f.write(b"junk" * 100)
    with open(os.path.join(trip, "node_modules", "x", "index.js"), "w") as f:
        f.write("module.exports = 1;\n" * 50)
    docs = os.path.join(src, "loose")
    os.makedirs(docs, exist_ok=True)
    names = ["Faktúra 2026-03.pdf", "Daňové priznanie 2025.docx", "rozpočet.xlsx", "zmluva nájom.pdf"]
    for n in names:
        with open(os.path.join(docs, n), "wb") as f:
            f.write((n * 500).encode())
    t = time.mktime((2025, 4, 2, 10, 0, 0, 0, 0, -1))
    for n in names:
        os.utime(os.path.join(docs, n), (t, t))
    return trip, [os.path.join(docs, n) for n in names]


def wait(j, limit=300):
    t0 = time.time()
    while j["status"] in ("queued", "running") and time.time() - t0 < limit:
        time.sleep(.1)
    return j


def fetch(port, method, path, headers=None, body=b""):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        c.request(method, path, body, headers or {})
        r = c.getresponse()
        return r.status, r.headers, r.read()
    finally:
        c.close()


def login(port, home):
    """What the window does: a one-time launch key (asked for with the secret in instance.json) becomes a cookie."""
    with open(os.path.join(home, "instance.json"), encoding="utf-8") as f:
        info = json.load(f)
    st, _, data = fetch(port, "POST", "/api/launch", {"X-Tansu-Secret": info["secret"], "Content-Type": "application/json"}, b"{}")
    key = json.loads(data)["key"]
    st, hd, _ = fetch(port, "GET", f"/?k={key}")
    return st, (hd.get("Set-Cookie") or "").split(";")[0], hd.get("Set-Cookie") or ""


def web_gate(trip):
    """The real server in a child process (throwaway TANSU_HOME, AI off, a free port): only the window gets in."""
    home = os.path.join(TMP, "home")
    os.makedirs(home)
    with open(os.path.join(home, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"ai": False}, f)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "TANSU_HOME": home, "TANSU_PORT": str(port)}
    app = os.path.join(HERE, "app.py")
    proc = subprocess.Popen([sys.executable, app, "--no-window"], env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=0x08000000)
    try:
        for _ in range(100):
            if os.path.exists(os.path.join(home, "instance.json")):
                break
            time.sleep(.1)
        check(os.path.exists(os.path.join(home, "instance.json")), "server published instance.json in its data folder")
        st, _, data = fetch(port, "GET", "/")
        check(st == 403 and b"TANSU" not in data, f"no cookie: the page is refused ({st})")
        st, _, _ = fetch(port, "POST", "/api/state", {"X-Tansu": "1", "Content-Type": "application/json"}, b"{}")
        check(st == 403, f"no cookie: the API is refused ({st})")
        st, _, _ = fetch(port, "POST", "/api/launch", {"X-Tansu-Secret": "wrong"}, b"{}")
        check(st == 403, f"wrong secret: no launch key ({st})")
        st, cookie, raw = login(port, home)
        check(st == 303 and cookie.startswith("tansu_s=") and "HttpOnly" in raw and "SameSite=Strict" in raw,
              "launch key -> HttpOnly SameSite=Strict session cookie")
        st, hd, data = fetch(port, "GET", "/", {"Cookie": cookie})
        with open(os.path.join(home, "instance.json"), encoding="utf-8") as f:
            secret = json.load(f)["secret"]
        check(st == 200 and b"__TOKEN__" not in data and b"TANSU_TOKEN" not in data and secret.encode() not in data,
              "the page loads with the cookie and holds no secret")
        check(hd.get("X-Frame-Options") == "DENY" and hd.get("X-Content-Type-Options") == "nosniff",
              "no framing, no MIME sniffing")
        api = {"Cookie": cookie, "X-Tansu": "1", "Content-Type": "application/json"}
        st, _, data = fetch(port, "POST", "/api/state", api, b"{}")
        check(st == 200 and json.loads(data)["batches"] == [], f"cookie + header: the API answers ({st})")
        st, _, _ = fetch(port, "POST", "/api/state", {"Cookie": cookie, "Content-Type": "application/json"}, b"{}")
        check(st == 403, f"without the X-Tansu header: refused ({st})")
        st, _, _ = fetch(port, "POST", "/api/state", {**api, "Host": f"evil.example:{port}"}, b"{}")
        check(st == 403, f"DNS rebinding (wrong Host): refused ({st})")
        st, _, _ = fetch(port, "POST", "/api/state", {**api, "Sec-Fetch-Site": "cross-site"}, b"{}")
        check(st == 403, f"cross-site request: refused ({st})")
        st, _, _ = fetch(port, "PUT", "/api/drop", {"X-Tansu": "1", "X-Rel": "a.txt"}, b"x")
        check(st == 403, f"drop without cookie: refused ({st})")
        # a second Tansu ("Send to") hands its paths to the running one through /api/launch
        r = subprocess.run([sys.executable, app, "--no-window", trip], env=env, timeout=60, capture_output=True,
                           creationflags=0x08000000)
        got = []
        for _ in range(100):
            got = json.loads(fetch(port, "POST", "/api/state", api, b"{}")[2])["batches"]
            if got:
                break
            time.sleep(.1)
        check(r.returncode == 0 and len(got) == 1, f"second launch handed its folder to the running Tansu ({len(got)})")
    finally:
        proc.terminate()   # only the server this test started
        proc.wait(10)


def main():
    print("library:", LIB)
    trip, loose = make_samples()

    print("\n[scan + rules]")
    f = scan.analyse([trip])
    check(f["count"] == 2, f"junk left out (count={f['count']}, junk={f['junk']['files']})")
    check(f["junk"]["files"] == 2, "Thumbs.db and node_modules counted as junk")
    check("Dovolenka Chorvátsko 2024/prázdny" in f["empty_dirs"], "empty folder found")
    check(0.3 < f["precompressed"] < 0.9, f"precompressed share measured ({f['precompressed']:.2f})")
    p = rules.plan(f)
    check(p["layout"] == "keep" and p["name"] == "Dovolenka Chorvátsko 2024", f"rule plan {p['format']} {p['folder']} / {p['name']}")
    f2 = scan.analyse(loose)
    p2 = rules.plan(f2)
    check(f2["sensitive"] and p2["format"] == "7z" and p2["encrypt"], f"sensitive docs -> encrypted 7z ({p2['format']})")
    check(p2["folder"].startswith("Personal"), f"sensitive docs folder {p2['folder']}")

    print("\n[mapping]")
    m = engine.mapping(f["files"], f["empty_dirs"], "keep")
    names = {a for _, a in m}
    check("Dovolenka Chorvátsko 2024/Deň 1 – Split/fotka 😀 ж.jpg" in names, "unicode path kept")
    check(not any("node_modules" in a or "Thumbs" in a for a in names), "junk excluded from mapping")
    m2 = engine.mapping(f2["files"], [], "by_date")
    check(all(a.startswith("2025/2025-04/") for _, a in m2), "by_date layout")
    m3 = engine.mapping(f2["files"], [], "by_type")
    check({a.split("/")[0] for _, a in m3} == {"Documents", "Spreadsheets"}, "by_type layout")

    print("\n[every format: create, verify, list, extract]")
    for fmt, pw in (("zip", None), ("7z", None), ("7z", "heslo-ščť"), ("tar.xz", None)):
        out = os.path.join(TMP, f"t_{fmt}{'_enc' if pw else ''}{rules.FORMATS[fmt]['ext']}")
        part, total = engine.create(out, fmt, "fast", m, lambda x: None, threading.Event(), pw)
        okv, msg = engine.verify(part, pw, {a: os.path.getsize(s) for s, a in m if s})
        os.replace(part, out)
        check(okv, f"{fmt}{' +AES' if pw else ''} verify: {msg}")
        ls = engine.listing(out, pw)
        check(any(i["name"].endswith("fotka 😀 ж.jpg") for i in ls), f"{fmt} listing has unicode name")
        dest = os.path.join(TMP, "x_" + os.path.basename(out))
        n = engine.extract(out, dest, None, pw)
        back = os.path.join(dest, "Dovolenka Chorvátsko 2024", "poznámky.txt")
        check(n >= 2 and os.path.exists(back) and os.path.getsize(back) == os.path.getsize(os.path.join(trip, "poznámky.txt")),
              f"{fmt} extract round-trip ({n} files)")
        if pw:
            check(engine.is_encrypted(out), "7z AES detected as encrypted")
            try:
                engine.listing(out)
                check(False, "encrypted 7z hides names without password")
            except Exception:
                check(True, "encrypted 7z hides names without password")
    # zip: photos stored, text deflated
    import zipfile
    with zipfile.ZipFile(os.path.join(TMP, "t_zip.zip")) as z:
        types = {i.filename.rsplit("/", 1)[-1]: i.compress_type for i in z.infolist()}
    check(types.get("fotka 😀 ж.jpg") == zipfile.ZIP_STORED and types.get("poznámky.txt") == zipfile.ZIP_DEFLATED,
          "zip stores jpg, deflates txt")
    # corrupted archive must fail verification
    bad = os.path.join(TMP, "bad.zip")
    shutil.copy(os.path.join(TMP, "t_zip.zip"), bad)
    with open(bad, "r+b") as fh:
        fh.seek(400)
        fh.write(b"\x00" * 64)
    check(not engine.verify(bad)[0], "damaged zip detected")

    print("\n[jobs + library]")
    b = batches.add([trip])
    plan = {**batches.plan(b), "format": "zip", "folder": "Photos/2024"}
    j = wait(jobs.archive(b["id"], plan))
    check(j["status"] == "done", f"archive job {j['status']} {j.get('error') or ''}")
    rel = j["result"]["rel"]
    check(rel.startswith("Photos/2024/") and rel.endswith("Dovolenka Chorvátsko 2024.zip"), f"filed as {rel}")
    b2 = batches.add(loose)
    j2 = wait(jobs.archive(b2["id"], {**batches.plan(b2)}, "tajne"))
    check(j2["status"] == "done", f"encrypted 7z job {j2['status']} {j2.get('error') or ''}")
    ov = store.overview()
    check(ov["stats"]["count"] == 2, f"library has {ov['stats']['count']} archives")
    e, items = store.contents(j2["result"]["rel"])
    check(len(items) == 4, "encrypted archive contents known from Tansu's own index")
    hits = store.search("faktúra")
    check(hits and hits[0]["count"] == 1, "search inside archives")
    # append to the zip
    extra = os.path.join(TMP, "src", "extra.txt")
    with open(extra, "w") as fh:
        fh.write("more")
    b3 = batches.add([extra])
    j3 = wait(jobs.archive(b3["id"], {**batches.plan(b3), "format": "zip", "append_to": rel}))
    check(j3["status"] == "done" and j3["result"]["appended"], f"append to existing zip {j3.get('error') or ''}")
    _, items = store.contents(rel)
    check(any(i["name"] == "extra.txt" for i in items), "appended file listed")
    # move by hand in Explorer -> re-linked
    moved_dir = os.path.join(LIB, "Elsewhere")
    os.makedirs(moved_dir)
    os.replace(store.abs_of(rel), os.path.join(moved_dir, "renamed.zip"))
    data, _, _ = store.reconcile()
    check("Elsewhere/renamed.zip" in data["archives"] and data["archives"]["Elsewhere/renamed.zip"].get("why") is not None
          or data["archives"]["Elsewhere/renamed.zip"].get("by") == "tansu", "moved archive re-linked to its notes")
    new = store.move("Elsewhere/renamed.zip", "Photos/2024", "Croatia trip")
    check(new == "Photos/2024/Croatia trip.zip" and not os.path.exists(moved_dir), "move + rename, empty folder removed")
    # checkup
    os.makedirs(os.path.join(LIB, "Empty one"))
    shutil.copy(store.abs_of(new), os.path.join(LIB, "copy.zip"))
    with open(os.path.join(LIB, "loose note.txt"), "w") as fh:
        fh.write("x")
    j4 = wait(jobs.checkup(deep=True))
    kinds = sorted({i["kind"] for i in j4["result"]["issues"]})
    check({"duplicate", "empty_folder", "loose_file"} <= set(kinds), f"checkup found {kinds}")
    dup = next(i for i in j4["result"]["issues"] if i["kind"] == "duplicate")
    check(dup["rel"] == "copy.zip" and dup["keep"] == new, f"duplicate: recycle the copy, keep Tansu's ({dup['rel']})")
    from core import advisor
    bad = advisor.validate({"folder": "Documents/Archives/Dovolenka Chorvátsko 2024", "name": "Dovolenka"},
                           {**p, "folder": "Photos/2024"}, f)
    check(bad["folder"] == "Photos/2024", f"AI folder 'Documents/Archives/<name>' rejected -> {bad['folder']}")
    got = advisor.parse('{"format": "zip", "folder": null, "why": These are docs. Time: 3 s.", "tip": "Note: x", "encrypt": false}')
    check(got and got["why"] == "These are docs. Time: 3 s." and got["tip"] == "Note: x" and got["encrypt"] is False,
          "AI answer with a dropped opening quote repaired")
    # extract job
    j5 = wait(jobs.extract(new))
    check(j5["status"] == "done" and j5["result"]["files"] >= 3, f"extract job -> {j5['result'] and j5['result']['dest']}")

    print("\n[web gate: launch key -> session cookie]")
    web_gate(trip)

    if "--ai" in sys.argv:
        print("\n[AI plan on the NPU]")
        from core import advisor, flmshare
        from core.llm import npu
        others = flmshare.others_using("Tansu")   # another app already has the shared server
        npu.ensure()
        for _ in range(240):
            if npu.state in ("online", "missing") or (npu.state == "offline" and npu.detail):
                break
            time.sleep(.5)
        check(npu.state == "online", f"FastFlowLM {npu.state} {npu.detail} ({npu.model()})")
        check((flmshare._read().get("users") or {}).get("Tansu") == os.getpid(),
              "Tansu is listed as a user of the shared FastFlowLM server")
        check(npu.ctx == flmshare.CTX_LEN, f"server context {npu.ctx} tokens")
        for label, fx in (("trip folder", f), ("tax documents", f2)):
            t0 = time.time()
            plan = None
            for kind, data in advisor.advise(fx, rules.options(fx), store.library_summary(), store.folder_list()):
                if kind == "plan":
                    plan = data
            print(f"   {label}: {time.time() - t0:.1f}s ->", {k: plan[k] for k in ("format", "level", "encrypt", "folder", "name", "layout", "source")})
            print("     why:", plan["why"])
            check(plan["source"] == "ai", f"{label}: model answered valid JSON")
        npu.stop()
        if not others and not flmshare.others_using("Tansu"):
            check(not npu.ping(), "last app to leave: the shared server stopped")
        else:
            print("   (another app uses the FastFlowLM server - it keeps running)")

    print(f"\n{ok} passed, {fail} failed")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
