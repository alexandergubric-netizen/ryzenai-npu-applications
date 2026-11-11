"""Settings > Engine (start/stop on the user's click) and model preload, without touching the real engine."""
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import app as tsubasa
from core.client import Client

RUNS = Path(__file__).resolve().parents[1] / ".test-runs"


class FakeEngine:
    observed_model = None
    warming = None
    def require_model(self, model):
        if model not in ("qwen3-it:4b", "qwen-liberty3.5:9b"):
            raise ValueError("Select an installed chat model.")
    def detach(self):
        pass
    def warm(self, model):
        self.require_model(model)
        return model != self.observed_model
    # the real start/stop logic (core/client.py) with a fake inventory
    start_engine, stop_engine = Client.start_engine, Client.stop_engine
    def default_model(self):
        return tsubasa.DEFAULT_MODEL


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.box = tempfile.TemporaryDirectory(dir=RUNS)
        self.app = tsubasa.App(self.box.name, 0, FakeEngine())
        self.app.bind()
        self.thread = threading.Thread(target=self.app.server.serve_forever, daemon=True)
        self.thread.start()
        self.headers = {"Cookie": self.app.gate.cookie + "=" + self.app.gate.session, "X-Tsubasa": "1",
                        "Content-Type": "application/json"}

    def tearDown(self):
        self.app.server.shutdown()
        self.app.close()
        self.box.cleanup()

    def post(self, path, body):
        c = http.client.HTTPConnection("127.0.0.1", self.app.gate.port, timeout=10)
        c.request("POST", path, json.dumps(body), self.headers)
        r = c.getresponse()
        data = json.loads(r.read())
        c.close()
        return r.status, data

    @unittest.skipUnless((Path(__file__).resolve().parents[2] / "flm-gateway" / "Start-LocalAI.ps1").is_file(),
                         "the author's flm-gateway launcher scripts are not next to this copy")
    def test_start_runs_the_launcher_engine_only_and_stop_runs_stop_script(self):
        with mock.patch.object(tsubasa.subprocess, "Popen") as popen, mock.patch.object(tsubasa.subprocess, "run") as run:
            status, data = self.post("/api/engine", {"action": "start", "model": "qwen3-it:4b"})
            self.assertEqual((status, data["model"]), (200, "qwen3-it:4b"))
            cmd = popen.call_args[0][0]
            self.assertTrue(cmd[-6].endswith("Start-LocalAI.ps1"))
            self.assertEqual(cmd[-5:], ["-App", "Tsubasa", "-EngineOnly", "-Model", "qwen3-it:4b"])
            status, data = self.post("/api/engine", {"action": "start", "model": "evil; rm -rf"})
            self.assertEqual(popen.call_args[0][0][-1], tsubasa.DEFAULT_MODEL)   # unknown models fall back
            status, _ = self.post("/api/engine", {"action": "stop"})
            self.assertEqual(status, 200)
            self.assertTrue(run.call_args[0][0][-1].endswith("Stop-LocalAI.ps1"))

    def test_engine_refuses_bad_actions_and_busy_times(self):
        self.assertEqual(self.post("/api/engine", {"action": "restart"})[0], 400)
        self.app.operation.acquire()
        try:
            self.assertEqual(self.post("/api/engine", {"action": "stop"})[0], 409)
            self.assertEqual(self.post("/api/warm", {"model": "qwen3-it:4b"})[1]["started"], False)
        finally:
            self.app.operation.release()

    def test_preload_endpoint(self):
        self.assertEqual(self.post("/api/warm", {"model": "qwen3-it:4b"}), (200, {"started": True, "model": "qwen3-it:4b"}))
        self.assertEqual(self.post("/api/warm", {"model": "not-installed"})[0], 400)


class PreloadWaitTests(unittest.TestCase):
    def test_a_message_waits_for_a_preload_instead_of_failing(self):
        c = Client()
        c.require_model = lambda m: None
        c.lock.acquire()
        c.warming = "qwen3-it:4b"
        threading.Timer(0.3, c.lock.release).start()
        started = time.monotonic()
        got = c.lock.acquire(timeout=5) if c.warming else False   # what stream() does while a preload runs
        self.assertTrue(got)
        self.assertGreater(time.monotonic() - started, 0.25)
        c.lock.release()


class FakeConnection:
    """Stands in for the verified FLM connection: records the request, answers with one reasoning and one text chunk."""
    sent = []
    def __init__(self, *a, **kw):
        pass
    def request(self, method, path, body, headers):
        FakeConnection.sent.append(json.loads(body))
    def getresponse(self):
        class R:
            status = 200
            def __iter__(self):
                yield b'data: {"choices":[{"delta":{"reasoning_content":"391 = 17 x 23."}}]}\n'
                yield b'data: {"choices":[{"delta":{"content":"No."}}]}\n'
                yield b"data: [DONE]\n"
        return R()
    def close(self):
        pass


class ThinkRequestTests(unittest.TestCase):
    """FastFlowLM 1.0.9 reasons only when the request says "think": true (no reasoning without it, even with no
    /no_think), so Think first must send it."""
    def run_stream(self, think):
        c = Client()
        c.require_model = lambda m: None
        c.join = lambda: None
        FakeConnection.sent.clear()
        with mock.patch("core.client.ServiceConnection", FakeConnection):
            out = list(c.stream("qwen-liberty3.5:9b", [{"role": "user", "content": "Is 391 prime?"}], think=think))
        return FakeConnection.sent[0], out

    def test_think_first_asks_the_engine_to_reason(self):
        sent, out = self.run_stream(True)
        self.assertIs(sent["think"], True)
        self.assertEqual(sent["messages"][-1]["content"], "Is 391 prime?")
        self.assertIn(("thinking", "391 = 17 x 23."), out)
        self.assertIn(("text", "No."), out)

    def test_without_think_first_the_answer_comes_at_once(self):
        # Without an explicit "think": false FLM let liberty reason anyway: "hello!" took 41 s (2026-11-05).
        sent, _ = self.run_stream(False)
        self.assertIs(sent["think"], False)
        self.assertTrue(sent["messages"][-1]["content"].startswith("/no_think "))

    def test_models_without_the_switch_get_no_think_field(self):
        c = Client()
        c.require_model = lambda m: None
        c.join = lambda: None
        FakeConnection.sent.clear()
        with mock.patch("core.client.ServiceConnection", FakeConnection):
            list(c.stream("qwen3-it:4b", [{"role": "user", "content": "hi"}], think=False))
        self.assertNotIn("think", FakeConnection.sent[0])


if __name__ == "__main__":
    unittest.main()


class PortableTests(unittest.TestCase):
    """What an installed copy on another PC relies on (2026-11-11 audit)."""
    def test_model_fallbacks_when_the_defaults_are_not_installed(self):
        c = Client()
        c.cache, c.cache_at = [{"id": "qwen3.5:4b"}], time.monotonic()
        self.assertEqual(c.default_model(), "qwen3.5:4b")
        self.assertEqual(c.terminal_model(), "qwen3.5:4b")
        c.cache = [{"id": "qwen3.5:4b"}, {"id": "qwen3-it:4b"}]
        self.assertEqual(c.terminal_model(), "qwen3-it:4b")
        c.cache, c.cache_at = [], 0
        with mock.patch.object(Client, "models", return_value=[]):
            self.assertIsNone(c.default_model())

    def test_no_personal_paths_in_the_source(self):
        root = Path(__file__).resolve().parents[1]
        for folder in ("core", "web", "tools", "installer", "mac"):
            for f in (root / folder).rglob("*"):
                if f.is_file() and f.suffix in (".py", ".js", ".html", ".css", ".ps1", ".sh", ".cmd"):
                    self.assertNotIn("Users\\alexa", f.read_text(encoding="utf-8", errors="replace").replace("/", "\\"), f)

    def test_mlx_engine_request_shape_and_inventory(self):
        from core.mlx_client import MlxClient, cached_models
        with tempfile.TemporaryDirectory(dir=RUNS) as d:
            snap = Path(d) / "models--mlx-community--Qwen3-4B-4bit" / "snapshots" / "abc"
            snap.mkdir(parents=True)
            for name in ("config.json", "tokenizer_config.json"):
                (snap / name).write_text("{}", encoding="utf-8")
            (snap / "model.safetensors").write_bytes(b"x")
            (Path(d) / "models--openai--whisper-tiny" / "snapshots" / "x").mkdir(parents=True)
            found = cached_models(Path(d))
        self.assertEqual([m["id"] for m in found], ["mlx-community/Qwen3-4B-4bit"])
        self.assertTrue(found[0]["supports_reasoning"])
        payload = {}
        MlxClient().shape(payload, "mlx-community/Qwen3-4B-4bit", False)
        self.assertEqual(payload, {"chat_template_kwargs": {"enable_thinking": False}})
        with self.assertRaises(ValueError):
            MlxClient().download("not a repo; rm -rf")

    def test_mlx_client_streams_reasoning_text_and_usage_from_an_openai_style_server(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from core.mlx_client import MlxClient
        seen = {}
        class Fake(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_GET(self):
                body = b'{"status": "ok"}'
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                seen.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                for chunk in ({"choices": [{"delta": {"reasoning": "hm"}}]}, {"choices": [{"delta": {"content": "Hi"}}]},
                              {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}):
                    self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
        server = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            c = MlxClient(server.server_address[1])
            c.cache, c.cache_at = [{"id": "m/x"}], time.monotonic()
            self.assertTrue(c.status()["online"])
            out = list(c.stream("m/x", [{"role": "user", "content": "hello"}], think=True))
        finally:
            server.shutdown(); server.server_close()
        self.assertEqual(out, [("thinking", "hm"), ("text", "Hi"), ("usage", {"prompt_tokens": 3, "completion_tokens": 1})])
        self.assertEqual(seen["chat_template_kwargs"], {"enable_thinking": True})
        self.assertNotIn("think", seen)
        self.assertEqual(seen["messages"][-1]["content"], "hello")   # no FastFlowLM /no_think prefix
