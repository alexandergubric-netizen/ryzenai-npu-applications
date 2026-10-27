"""Starts a separate Washi server (port 52794, throwaway WASHI_HOME) and drives its HTTP API like the UI does.

    python tests\\smoke.py         # everything except the AI
    python tests\\smoke.py --ai    # also a summary, a question and a guide answer on the NPU (supported PCs only)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 52794
BASE = f"http://127.0.0.1:{PORT}"
passed, failed = 0, []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
    else:
        failed.append(name)
        print("FAIL", name, str(detail)[:300])


def hdr(token):
    """The window's credentials: its session cookie, plus the app header every API call sends."""
    return {"Cookie": token or "", "X-Washi": "1" if token else ""}


def get(url, token):
    return urllib.request.urlopen(urllib.request.Request(url, headers=hdr(token)))


def login(home):
    """What the window does: a one-time launch key (asked for with the secret in instance.json) becomes a cookie."""
    with open(os.path.join(home, "instance.json"), encoding="utf-8") as f:
        info = json.load(f)
    req = urllib.request.Request(BASE + "/api/launch", b"{}", {"X-Washi-Secret": info["secret"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        key = json.load(r)["key"]

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        urllib.request.build_opener(NoRedirect).open(f"{BASE}/?k={key}")
    except urllib.error.HTTPError as e:
        return e.headers["Set-Cookie"].split(";")[0], info["secret"]
    raise RuntimeError("no session cookie")


def call(path, body=None, token=None, raw=False):
    req = urllib.request.Request(BASE + path, json.dumps(body or {}).encode(),
                                 {"Content-Type": "application/json", **hdr(token)})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    if raw:
        return data
    return json.loads(data) if data else None


def call_status(path, body, token):
    """(HTTP status, JSON) without raising on errors."""
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json", **hdr(token)})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def stream(path, body, token):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json", **hdr(token)})
    events = []
    with urllib.request.urlopen(req, timeout=600) as r:
        for line in r:
            if line.strip():
                events.append(json.loads(line))
    return events


def main():
    tmp = tempfile.mkdtemp(prefix="washi-smoke-")
    home = os.path.join(tmp, "home")
    sample = os.path.join(tmp, "report.pdf")
    subprocess.run([sys.executable, os.path.join(HERE, "tests", "make_sample.py")], check=True, capture_output=True)
    shutil.copy2(os.path.join(HERE, "tests", "sample.pdf"), sample)
    env = dict(os.environ, WASHI_HOME=home, WASHI_PORT=str(PORT))
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "app.py"), "--no-window"], env=env, cwd=HERE)
    try:
        for _ in range(120):
            if os.path.exists(os.path.join(home, "instance.json")):
                break
            time.sleep(0.25)
        time.sleep(0.5)
        token, secret = login(home)

        # security: no session, and the page holds no secret
        try:
            call("/api/state", {}, token="washi_s=nope")
            check("rejects a missing session", False)
        except urllib.error.HTTPError as e:
            check("rejects a missing session", e.code == 403)
        try:
            urllib.request.urlopen(BASE + "/")
            check("page needs the session", False)
        except urllib.error.HTTPError as e:
            check("page needs the session", e.code == 403)
        html = get(BASE + "/", token).read().decode()
        check("index holds no secret", secret not in html and token.split("=", 1)[1] not in html and "__TOKEN__" not in html)

        st = call("/api/state", {"full": True}, token)
        check("state", "settings" in st and "ai" in st and st["version"])
        res = call("/api/open", {"path": sample}, token)
        d = res[0]["doc"]
        did = d["id"]
        check("open", len(d["pages"]) == 6 and d["meta"]["title"].startswith("Quarterly"))
        png = get(f"{BASE}/api/page?d={did}&p=0&s=1&v=0", token).read()
        check("page image", png[:4] == b"\x89PNG" and len(png) > 5000)
        jpg = get(f"{BASE}/api/page?d={did}&p=1&s=0.3&v=0&f=jpg", token).read()
        check("thumbnail jpg", jpg[:2] == b"\xff\xd8")
        pi = call("/api/pageinfo", {"d": did, "p": 5}, token)
        check("pageinfo text", any("Approval" in l["t"] for l in pi["text"]))
        check("pageinfo widgets", {w["name"] for w in pi["widgets"]} == {"name", "date", "approve"}, pi["widgets"])
        hits = call("/api/search", {"d": did, "q": "paper"}, token)
        check("search", len(hits) >= 8, len(hits))
        ol = call("/api/outline", {"d": did}, token)
        check("outline", len(ol) == 7, ol)

        rev = [h for h in call("/api/search", {"d": did, "q": "Revenue grew"}, token)][0]
        a = call("/api/annot_add", {"d": did, "p": 0, "kind": "highlight", "o": {"rects": [rev["r"]], "color": "#ffd84d"}}, token)
        check("highlight", a["annot"]["kind"] == "Highlight" and a["doc"]["dirty"] and a["doc"]["pages"][0]["pv"] == 1)
        u = call("/api/annot_update", {"d": did, "p": 0, "id": a["annot"]["id"], "o": {"content": "Check", "color": "#8bd17c"}}, token)
        check("update annot", u["annot"]["content"] == "Check" and u["annot"]["stroke"] == "#8bd17c")
        s = call("/api/annot_add", {"d": did, "p": 0, "kind": "stamp", "o": {"rect": [300, 600, 500, 660], "label": "Approved"}}, token)
        check("stamp", s["annot"]["kind"] == "Stamp")
        sp = call("/api/stamp_preview", {"label": "Draft"}, token)
        check("stamp preview", sp["img"].startswith("data:image/png;base64,"))
        at = call("/api/annot_at", {"d": did, "p": 0, "pt": [400, 630]}, token)
        check("annot at", at and at["id"] == s["annot"]["id"], at)
        call("/api/annot_delete", {"d": did, "p": 0, "id": s["annot"]["id"]}, token)
        check("delete annot", len(call("/api/annots", {"d": did, "p": 0}, token)) == 1)

        line = call("/api/line_at", {"d": did, "p": 0, "pt": [100, 212]}, token)
        check("line at", line and "board" in line["text"] and line["family"] == "sans", line)
        call("/api/edit_line", {"d": did, "p": 0, "point": [100, 212], "text": "The board approved a machine in Žilina."}, token)
        pi = call("/api/pageinfo", {"d": did, "p": 0}, token)
        check("edit line", any("Žilina" in l["t"] for l in pi["text"]))
        call("/api/add_text", {"d": did, "p": 0, "point": [72, 700], "text": "Typed by smoke test", "size": 12}, token)
        call("/api/field_set", {"d": did, "p": 5, "xref": next(w["xref"] for w in call("/api/pageinfo", {"d": did, "p": 5}, token)["widgets"] if w["name"] == "name"), "value": "Alexander"}, token)
        check("form value", any(w["value"] == "Alexander" for w in call("/api/pageinfo", {"d": did, "p": 5}, token)["widgets"]))

        info = call("/api/pages_rotate", {"d": did, "pages": [1], "angle": 90}, token)["doc"]
        check("rotate", info["pages"][1]["rot"] == 90)
        info = call("/api/pages_duplicate", {"d": did, "pages": [0]}, token)["doc"]
        check("duplicate", len(info["pages"]) == 7)
        info = call("/api/pages_move", {"d": did, "pages": [6], "to": 0}, token)["doc"]
        check("move", len(info["pages"]) == 7)
        info = call("/api/pages_delete", {"d": did, "pages": [0]}, token)["doc"]
        check("delete page", len(info["pages"]) == 6)
        info = call("/api/watermark", {"d": did, "text": "DRAFT", "pages": "1-2"}, token)["doc"]
        info = call("/api/header_footer", {"d": did, "text": "{page}/{pages}"}, token)["doc"]
        check("watermark + numbers", info["undo"] >= 10)
        before = info["undo"]
        info = call("/api/undo", {"d": did}, token)["doc"]
        check("undo", info["undo"] == before - 1 and info["redo"] == 1)
        info = call("/api/redo", {"d": did}, token)["doc"]
        check("redo", info["redo"] == 0)
        info = call("/api/meta_set", {"d": did, "meta": {"title": "Smoke"}}, token)["doc"]
        check("metadata", info["meta"]["title"] == "Smoke")
        info = call("/api/protect", {"d": did, "user": "pw"}, token)["doc"]
        check("protect pending", info["security"] == "set")
        saved = call("/api/save", {"d": did}, token)
        check("save", saved["saved"] == sample and not saved["doc"]["dirty"])
        call("/api/close", {"d": did}, token)
        res = call("/api/open", {"path": sample}, token)
        check("needs password", res[0].get("password"))
        res = call("/api/open", {"path": sample, "password": "pw"}, token)
        check("open with password", res[0]["doc"]["meta"]["title"] == "Smoke")
        did = res[0]["doc"]["id"]
        n = call("/api/new", {"pages": 2}, token)
        check("new blank", len(n["doc"]["pages"]) == 2)
        check("recent", any(r["path"] == sample for r in call("/api/recent", {}, token)))
        try:
            get(f"{BASE}/api/thumb?path={urllib.parse.quote(sample)}", token)
            check("no preview of a protected file", False)
        except urllib.error.HTTPError as e:
            check("no preview of a protected file", e.code == 404)
        hs = call("/api/help_search", {"q": "how do I sign"}, token)
        check("help search", hs and hs[0]["id"] == "sign", [h["id"] for h in hs])
        hs = call("/api/help_search", {"q": "merge two pdfs"}, token)
        check("help search merge", hs and hs[0]["id"] == "merge", [h["id"] for h in hs])
        ai = call("/api/ai/state", {}, token)
        check("ai state", "supported" in ai)
        check("settings", call("/api/settings", {"set": {"theme": "dark"}}, token)["settings"]["theme"] == "dark")

        # ---------------------------------------------------------------- saving where Washi can't write
        def edited(path):
            r = call("/api/open", {"path": path}, token)[0]["doc"]
            call("/api/annot_add", {"d": r["id"], "p": 0, "kind": "note", "o": {"point": [30, 30], "content": "x"}}, token)
            return r["id"]

        ro = os.path.join(tmp, "readonly.pdf")
        shutil.copy2(os.path.join(HERE, "tests", "sample.pdf"), ro)
        os.chmod(ro, 0o444)
        before = os.path.getmtime(ro)
        st, res = call_status("/api/save", {"d": edited(ro)}, token)
        check("read-only file: 409 + offer save as", st == 409 and res.get("save_as") and "read-only" in res["error"], (st, res))
        check("read-only file untouched", os.path.getmtime(ro) == before and not os.path.exists(ro + ".washi-tmp"))
        os.chmod(ro, 0o666)

        locked = os.path.join(tmp, "locked.pdf")
        shutil.copy2(os.path.join(HERE, "tests", "sample.pdf"), locked)
        did_l = edited(locked)
        with open(locked, "rb"):   # another program keeps the file open
            st, res = call_status("/api/save", {"d": did_l}, token)
        check("locked file: 409 + explains", st == 409 and res.get("save_as") and "another program" in res["error"], (st, res))
        check("locked file: no temp left", not os.path.exists(locked + ".washi-tmp"))
        st, res = call_status("/api/save", {"d": did_l}, token)
        check("saves once the other program lets go", st == 200 and not res["doc"]["dirty"], (st, res))

        gone_dir = os.path.join(tmp, "gone")
        os.makedirs(gone_dir)
        gone = os.path.join(gone_dir, "gone.pdf")
        shutil.copy2(os.path.join(HERE, "tests", "sample.pdf"), gone)
        did_g = edited(gone)
        shutil.rmtree(gone_dir)
        st, res = call_status("/api/save", {"d": did_g}, token)
        check("deleted folder: explains", st == 409 and "no longer exists" in res["error"], (st, res))

        protected = r"C:\Program Files\Oracle\VirtualBox\doc\UserManual.pdf"
        if os.path.exists(protected):
            folder = os.path.dirname(protected)
            stamp = os.path.getmtime(protected)
            st, res = call_status("/api/save", {"d": edited(protected)}, token)
            if st == 409:
                check("Program Files: explains protected folder", "protected" in res["error"] and res.get("save_as"), res)
            else:
                print("  (this test process may write to Program Files - protected-folder case not checkable here)")
            check("Program Files file never changed", os.path.getmtime(protected) == stamp)
            check("no temp file in Program Files", not os.path.exists(protected + ".washi-tmp"))
            config_recent = call("/api/forget", {"path": protected}, token)

        # ---------------------------------------------------------------- e-books
        sys.path.insert(0, os.path.join(HERE, "tests"))
        import make_ebooks
        books = make_ebooks.main(os.path.join(tmp, "books"))
        for b in books:
            r = call("/api/open", {"path": b}, token)[0]
            info = r.get("doc") or {}
            check(f"open {os.path.basename(b)}", info.get("converted") and not info.get("dirty") and info.get("reflowable")
                  and info.get("source") in ("EPUB", "FB2") and len(info.get("pages", [])) >= 3, r)
        epub = call("/api/open", {"path": books[0]}, token)[0]["doc"]
        check("same e-book opens once", epub["id"] == call("/api/open", {"path": books[0]}, token)[0]["doc"]["id"])
        check("e-book chapters as bookmarks", len(call("/api/outline", {"d": epub["id"]}, token)) == 5)
        check("e-book in recent files", any(r["path"] == books[0] for r in call("/api/recent", {}, token)))
        big = call("/api/reflow", {"d": epub["id"], "size": 16}, token)["doc"]
        check("e-book text size", len(big["pages"]) > len(epub["pages"]) and big["fontsize"] == 16)
        check("text size remembered", call("/api/state", {}, token)["settings"]["ebook_fontsize"] == 16)
        check("e-book has no save path (Save goes to Save as)", epub["path"] is None and epub["source_path"] == books[0])
        call("/api/annot_add", {"d": epub["id"], "p": 0, "kind": "highlight", "o": {"rects": [[40, 40, 300, 80]]}}, token)
        st, res = call_status("/api/reflow", {"d": epub["id"], "size": 11}, token)
        check("text size refused after edits", st == 400 and "changes" in res["error"], (st, res))
        call("/api/settings", {"set": {"ebook_fontsize": 11}}, token)

        if "--ai" in sys.argv and ai["supported"]:
            for _ in range(120):
                if call("/api/ai/state", {}, token)["state"] == "online":
                    break
                time.sleep(1)
            ev = stream("/api/ai/summary", {"d": did, "style": "brief"}, token)
            text = "".join(e.get("text", "") for e in ev if e["type"] == "text")
            check("ai summary", len(text) > 80 and ev[-1]["type"] == "done", ev[-3:])
            print("  summary:", text[:200].replace("\n", " "), "…")
            ev = stream("/api/ai/ask", {"d": did, "q": "How many sheets did the mill produce?"}, token)
            text = "".join(e.get("text", "") for e in ev if e["type"] == "text")
            check("ai question", "412" in text, text)
            print("  answer:", text[:200].replace("\n", " "))
            ev = stream("/api/ai/guide", {"q": "How do I rotate a page?"}, token)
            text = "".join(e.get("text", "") for e in ev if e["type"] == "text")
            acts = next((e["items"] for e in ev if e["type"] == "actions"), [])
            check("ai guide", ("rotat" in text.lower() or "pages tab" in text.lower()) and any(a["action"] == "page.rotatecw" for a in acts), (text, acts))
            print("  guide:", text[:200].replace("\n", " "))
    finally:
        proc.terminate()
        proc.wait(10)
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{passed} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    import urllib.error  # noqa: F401
    import urllib.parse  # noqa: F401
    sys.exit(main())
