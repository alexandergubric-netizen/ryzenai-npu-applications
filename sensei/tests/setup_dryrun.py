"""End-to-end dry run of the built installer:
extracts Documents\\Apps by Alex\\Sensei-Setup.exe, runs its wizard in test mode (no registry, simulated downloads),
installs into a throwaway folder, then starts the INSTALLED Sensei with its bundled Python and asks it a question.
Usage: python tests/setup_dryrun.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from installer.build import documents  # noqa: E402

EXE = os.path.join(documents(), "Apps by Alex", "Sensei-Setup.exe")
WORK = os.path.join(tempfile.gettempdir(), "sensei-dryrun")
TEST = os.path.join(WORK, "target")


def call(port, token, path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Setup": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    ext = os.path.join(WORK, "cab")
    os.makedirs(ext)
    subprocess.run([EXE, "/C", f"/T:{ext}", "/Q"], check=True, timeout=120)
    pay = os.path.join(WORK, "payload")
    shutil.unpack_archive(os.path.join(ext, "payload.zip"), pay)
    print("extracted:", sorted(os.listdir(pay)))
    env = dict(os.environ, SENSEI_SETUP_TEST=TEST, SENSEI_SETUP_HEADLESS="1")
    proc = subprocess.Popen([os.path.join(pay, "runtime", "python.exe"), os.path.join(pay, "setup", "setup.py")], env=env)
    for _ in range(60):
        if os.path.exists(os.path.join(TEST, "setup-port.txt")):
            break
        time.sleep(0.5)
    port, token = open(os.path.join(TEST, "setup-port.txt")).read().split()
    time.sleep(1)
    info = call(port, token, "/api/info")
    print("checks:", [(c["label"], c["status"]) for c in info["checks"]], "| can_install:", info["can_install"],
          "| ai:", info["ai"]["name"], info["ai"]["supported"])
    call(port, token, "/api/install", {"dir": os.path.join(TEST, "Sensei"), "desktop": True, "startmenu": True, "ai": True})
    while True:
        p = call(port, token, "/api/progress")
        if not p["running"] and (p["done"] or p["error"]):
            break
        time.sleep(0.5)
    for s in p["steps"]:
        print(f"  {s['state']:8} {s['label']}  {s['detail']}")
    if p["error"]:
        raise SystemExit("install failed: " + p["error"])
    call(port, token, "/api/ping", {})
    proc.terminate()
    inst = os.path.join(TEST, "Sensei")
    need = ["Sensei.exe", "uninstall.py", r"runtime\pythonw.exe", r"app\app.py", r"app\core\SenseiTools.psm1",
            r"app\core\knowledge\files.txt", r"app\web\logo.svg", r"test-shortcuts\Sensei.lnk"]
    missing = [n for n in need if not os.path.exists(os.path.join(inst, n))]
    print("installed files:", "all present" if not missing else f"MISSING {missing}")
    # the installed app, started with its own Python, must answer from its library
    app = subprocess.Popen([os.path.join(inst, "runtime", "python.exe"), os.path.join(inst, "app", "app.py"), "--no-window"],
                           env=dict(os.environ, SENSEI_NO_AI="1", SENSEI_PORT="52790"), cwd=os.path.join(inst, "app"))
    try:
        for _ in range(40):
            try:
                with urllib.request.urlopen("http://127.0.0.1:52790/", timeout=2) as r:
                    html = r.read().decode()
                break
            except OSError:
                time.sleep(0.5)
        with urllib.request.urlopen("http://127.0.0.1:52790/api/hello", timeout=5) as r:
            hello = json.load(r)
        if os.path.normcase(hello["path"]) != os.path.normcase(os.path.join(inst, "app")):
            raise SystemExit(f"the server answering is not the installed copy: {hello}")
        print("installed app is the one answering:", hello["path"], "version", hello["version"])
        tok = html.split('SENSEI_TOKEN = "')[1].split('"')[0]
        time.sleep(3)
        req = urllib.request.Request("http://127.0.0.1:52790/api/ask", data=json.dumps({"q": "set the volume to 40%"}).encode(),
                                     headers={"X-Sensei": tok, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            events = [json.loads(line) for line in r.read().decode().splitlines() if line.strip()]
        ans = next(e for e in events if e["type"] == "answer")
        print("installed app answers:", ans["code"], "|", ans["model"], "| checked:", not ans["check"]["problems"])
    finally:
        app.terminate()
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(app.pid)], capture_output=True)
    print("DRY RUN OK" if not missing else "DRY RUN FAILED")


if __name__ == "__main__":
    main()
