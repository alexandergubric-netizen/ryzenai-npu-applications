"""Code mode: read-only steps run by themselves; administrator steps always ask in the app, run elevated and their
output comes back to the model. The real UAC prompt is not exercised here: the elevated host is started with the
'open' verb, which runs the same plumbing without elevation."""
import os
import threading
import unittest
from unittest import mock

from core import agent as agent_mod
from core.agent import Agent, read_only

SAFE = {"syntax": [], "problems": [], "risk": "safe", "reasons": [], "interactive": False}
CAUTION = {**SAFE, "risk": "caution"}


class FakeShell:
    def __init__(self, lines=(("out", "hello"),), ok=True):
        self.lines, self.ok, self.ran = list(lines), ok, []
        self.session = type("S", (), {"cwd": os.path.expanduser("~")})()
    def verify(self, code):
        return dict(SAFE)
    def run(self, code):
        self.ran.append(code)
        yield from self.lines
        yield "done", {"ok": self.ok, "errors": 0 if self.ok else 1, "exit": 0, "ms": 5}
    def stop(self):
        pass


class Harness:
    """Runs one step; answers approval requests with `reply` (or not at all when reply is None)."""
    def __init__(self, autorun=True, reply=None, shell=None):
        self.agent = Agent(app=None)
        self.agent.autorun = autorun
        self.reply, self.events, self.asked = reply, [], []
        self.sensei = type("Z", (), {"shell": shell or FakeShell()})()
        self.cancel = threading.Event()

    def emit(self, kind, data):
        self.events.append((kind, data))
        if kind == "step" and not data.get("auto"):
            self.asked.append(data)
            answer = self.reply(data) if callable(self.reply) else self.reply
            if answer is None:
                self.cancel.set()
            else:
                self.agent.approvals.decide(data["ticket"], "t", answer)

    def step(self, code, check, admin=False):
        return self.agent._step(1, "run_command", {"task": "do it"}, "t", self.emit, self.cancel, self.sensei,
                                preset=(code, check, "test", admin))


class ReadOnlyTests(unittest.TestCase):
    def test_only_clean_safe_commands_qualify(self):
        self.assertTrue(read_only(SAFE, "Get-Date"))
        self.assertFalse(read_only(CAUTION, "Set-AudioVolume -Percent 30"))
        self.assertFalse(read_only({**SAFE, "interactive": True}, "ping -t 1.1.1.1"))
        self.assertFalse(read_only({**SAFE, "syntax": ["Missing }"]}, "Get-ChildItem | % {"))
        self.assertFalse(read_only({**SAFE, "problems": ["Unknown parameter"]}, "Get-Date -Foo"))
        self.assertFalse(read_only(SAFE, "Get-Process -Name <name>"))
        self.assertFalse(read_only(None, "Get-Date"))


class AutoRunTests(unittest.TestCase):
    def test_safe_step_runs_without_a_click(self):
        h = Harness(autorun=True)
        result, line = h.step("Get-Date", dict(SAFE))
        self.assertEqual(h.asked, [])
        self.assertTrue(any(k == "step" and d.get("auto") for k, d in h.events))
        self.assertIn("succeeded", result)
        self.assertIn("hello", result)          # the model reads the output

    def test_changes_still_wait_for_run(self):
        h = Harness(autorun=True, reply=None)
        result, _ = h.step("Set-AudioVolume -Percent 30", dict(CAUTION))
        self.assertEqual(len(h.asked), 1)
        self.assertTrue(result.startswith("STOPPED"))
        self.assertEqual(h.sensei.shell.ran, [])

    def test_setting_off_means_every_step_waits(self):
        h = Harness(autorun=False, reply=None)
        h.step("Get-Date", dict(SAFE))
        self.assertEqual(len(h.asked), 1)
        self.assertEqual(h.sensei.shell.ran, [])

    def test_admin_steps_never_run_by_themselves(self):
        h = Harness(autorun=True, reply=None)
        h.step("Get-BitLockerVolume", dict(SAFE), admin=True)
        self.assertEqual(len(h.asked), 1)
        self.assertTrue(h.asked[0]["admin"])
        self.assertFalse(any(d.get("auto") for k, d in h.events if k == "step"))


def fake_elevated(lines=(("out", "elevated output"),), ok=True):
    calls = []
    def run(code, cwd, cancelled, verb="runas"):
        calls.append(code)
        yield from lines
        yield "done", {"ok": ok, "errors": 0, "exit": 0, "ms": 9, "admin": True}
    return run, calls


class AdminTests(unittest.TestCase):
    def test_run_as_administrator_reads_the_output(self):
        run, calls = fake_elevated()
        with mock.patch("core.elevated.run_elevated", run):
            h = Harness(reply={"action": "allow", "elevate": True})
            result, line = h.step("Get-BitLockerVolume", dict(SAFE), admin=True)
        self.assertEqual(calls, ["Get-BitLockerVolume"])
        self.assertEqual(h.sensei.shell.ran, [])       # not in the normal session
        self.assertIn("as administrator succeeded", result)
        self.assertIn("elevated output", result)
        self.assertIn("as administrator", line)
        done = [d for k, d in h.events if k == "step_done"][-1]
        self.assertTrue(done["admin"])

    def test_declined_windows_prompt_is_reported(self):
        def declined(*a, **k):
            raise PermissionError("You declined the Windows administrator prompt, so nothing was run.")
            yield  # pragma: no cover
        with mock.patch("core.elevated.run_elevated", declined):
            h = Harness(reply={"action": "allow", "elevate": True})
            result, _ = h.step("Get-BitLockerVolume", dict(SAFE), admin=True)
        self.assertIn("declined", result)
        self.assertEqual([d["kind"] for k, d in h.events if k == "step_done"], ["failed"])

    def test_dangerous_admin_command_still_needs_the_second_click(self):
        run, calls = fake_elevated()
        with mock.patch("core.elevated.run_elevated", run):
            h = Harness(reply={"action": "allow", "elevate": True})
            result, _ = h.step("Remove-Item C:\\x", {**SAFE, "risk": "danger"}, admin=True)
        self.assertEqual(calls, [])
        self.assertIn("not confirmed", result)

    def test_access_denied_offers_administrator_in_the_app(self):
        shell = FakeShell(lines=[("err", "Access is denied.")], ok=False)
        run, calls = fake_elevated()
        replies = iter([{"action": "allow"}, {"action": "allow"}])
        with mock.patch("core.elevated.run_elevated", run):
            h = Harness(autorun=False, reply=lambda d: next(replies), shell=shell)
            result, line = h.step("Restart-Service Spooler", dict(CAUTION))
        self.assertEqual([a["n"] for a in h.asked], [1, "1a"])
        self.assertTrue(h.asked[1]["admin"] and h.asked[1]["retry"])
        self.assertEqual(calls, ["Restart-Service Spooler"])
        self.assertIn("Ran again as administrator", result)
        self.assertIn("elevated output", result)

    def test_declining_the_offer_runs_nothing_more(self):
        shell = FakeShell(lines=[("err", "Access is denied.")], ok=False)
        run, calls = fake_elevated()
        replies = iter([{"action": "allow"}, {"action": "skip"}])
        with mock.patch("core.elevated.run_elevated", run):
            h = Harness(autorun=False, reply=lambda d: next(replies), shell=shell)
            result, _ = h.step("Restart-Service Spooler", dict(CAUTION))
        self.assertEqual(calls, [])
        self.assertIn("failed", result)

    def test_ordinary_failures_do_not_offer_administrator(self):
        shell = FakeShell(lines=[("err", "Cannot find path 'C:\\nope'.")], ok=False)
        h = Harness(autorun=False, reply={"action": "allow"}, shell=shell)
        h.step("Get-ChildItem C:\\nope", dict(SAFE))
        self.assertEqual(len(h.asked), 1)


class ElevatedHostPlumbingTests(unittest.TestCase):
    def test_host_streams_output_errors_and_folder(self):
        from core.elevated import run_elevated
        events = list(run_elevated("'one'; Write-Error 'two'; (Get-Location).Path", os.path.expanduser("~"),
                                   threading.Event(), verb="open"))
        kinds = [k for k, _ in events]
        self.assertIn("out", kinds)
        self.assertIn("err", kinds)
        text = "\n".join(str(d) for _, d in events)
        self.assertIn("one", text)
        self.assertIn(os.path.expanduser("~"), text)
        done = events[-1]
        self.assertEqual(done[0], "done")
        self.assertFalse(done[1]["ok"])
        self.assertFalse(done[1]["admin"])     # 'open' is not elevated

    def test_stop_closes_the_host(self):
        from core.elevated import run_elevated
        cancel = threading.Event()
        threading.Timer(1.5, cancel.set).start()
        events = list(run_elevated("Start-Sleep -Seconds 30; 'late'", os.path.expanduser("~"), cancel, verb="open"))
        self.assertNotIn("late", "\n".join(str(d) for _, d in events))


if __name__ == "__main__":
    unittest.main()
