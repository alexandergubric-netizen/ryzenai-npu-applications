"""Terminal mode (Sensei pipeline) and Images mode checks that need no PowerShell host or engine."""
import threading
import unittest

from core import sensei_term
from core.sensei_term import Sensei, Tickets, overreach, extract_code


class FakeShell:
    def __init__(self, risk="safe"):
        self.risk, self.env = risk, {}
    def verify(self, code):
        return {"syntax": [], "problems": [], "risk": self.risk, "reasons": [], "placeholders": [], "interactive": False}


class OfflineClient:
    observed_model = None
    def stream(self, *a, **k):
        raise ConnectionRefusedError("engine down")
        yield  # pragma: no cover


class TicketTests(unittest.TestCase):
    def test_safe_code_runs_without_ticket(self):
        self.assertIsNone(Tickets().gate(FakeShell("safe"), "Get-Date", {}))

    def test_caution_needs_matching_single_use_ticket(self):
        t, shell = Tickets(), FakeShell("caution")
        self.assertIn("not checked", t.gate(shell, "Set-AudioVolume -Percent 30", {}))
        ticket = t.issue("Set-AudioVolume -Percent 30", "caution")
        self.assertIn("not checked", t.gate(shell, "Set-AudioVolume -Percent 90", {"ticket": ticket}))
        ticket = t.issue("Set-AudioVolume -Percent 30", "caution")
        self.assertIsNone(t.gate(shell, "Set-AudioVolume -Percent 30", {"ticket": ticket}))
        self.assertIn("not checked", t.gate(shell, "Set-AudioVolume -Percent 30", {"ticket": ticket}))

    def test_danger_needs_confirmation(self):
        t, shell, code = Tickets(), FakeShell("danger"), "Remove-ToRecycleBin -Path $HOME\\old.txt"
        self.assertIn("confirmation", t.gate(shell, code, {"ticket": t.issue(code, "danger")}))
        self.assertIsNone(t.gate(shell, code, {"ticket": t.issue(code, "danger"), "confirmed": True}))

    def test_syntax_errors_are_never_treated_as_safe(self):
        shell = FakeShell("safe")
        shell.verify = lambda code: {"syntax": ["Missing closing '}'"], "problems": [], "risk": "safe"}
        self.assertIn("not checked", Tickets().gate(shell, "Get-ChildItem | ForEach-Object {", {}))


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.s = Sensei(OfflineClient())
        self.s.shell = FakeShell()

    def test_library_answers_without_the_engine(self):
        events = list(self.s.ask("what is my ip address", [], threading.Event()))
        kind, ans = events[-1]
        self.assertEqual(kind, "answer")
        self.assertEqual(ans["how"], "library")
        self.assertIn("Get-NetIPAddress", ans["code"])
        self.assertTrue(ans["ticket"])

    def test_offline_engine_offers_tested_commands(self):
        kind, ans = list(self.s.ask("make my speakers quieter please", [], threading.Event()))[-1]
        self.assertEqual((kind, ans["how"], ans["code"]), ("answer", "offline", ""))
        self.assertTrue(ans["suggestions"])

    def test_picked_task_is_filled_from_the_request(self):
        source = next(x["source"] for x in sensei_term.library.items if x["q"][0] == "set the volume to {percent}")
        ans = self.s.task(source, "volume to 30 percent")
        self.assertIn("30", ans["code"])

    def test_overreach_and_code_extraction(self):
        self.assertTrue(overreach("show my files", {"risk": "danger", "reasons": ["deletes files"]}))
        self.assertIsNone(overreach("delete old.txt", {"risk": "danger", "reasons": []}))
        self.assertEqual(extract_code("```powershell\nPS C:\\> Get-Date\n```\nShows the date."), "Get-Date")


class ImageModeTests(unittest.TestCase):
    def test_saved_image_tag_round_trips(self):
        from core.modes_api import IMAGE_TAG
        import re
        tag = IMAGE_TAG.format(id="a" * 32, workspace="default")
        self.assertTrue(re.fullmatch(r"\[\[image:[a-f0-9]{32}:[\w-]+\]\]", tag))


if __name__ == "__main__":
    unittest.main()
