"""Custom instructions: settings, workspace instructions, the system prompt and upgrading an older database."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.storage import Store, DEFAULTS

RUNS = Path(__file__).resolve().parents[1] / ".test-runs"


class InstructionTests(unittest.TestCase):
    def test_instructions_reach_the_system_prompt(self):
        with tempfile.TemporaryDirectory(dir=RUNS) as h:
            s = Store(h)
            st = s.state()["settings"]
            s.mutate({"action": "settings", "settings": {**st, "about_me": "  I teach physics.  ", "instructions": "Use SI units."}})
            self.assertEqual(s.state()["settings"]["about_me"], "I teach physics.")
            w = s.mutate({"action": "workspace", "name": "Lab"})["id"]
            s.mutate({"action": "workspace_instructions", "id": w, "instructions": "Name the experiment first."})
            c = s.mutate({"action": "chat", "workspace": w, "model": "qwen3-it:4b"})["id"]
            system = s.context(c, "hi")[0]["content"]
            for part in ("I teach physics.", "Use SI units.", 'workspace "Lab"', "Name the experiment first."):
                self.assertIn(part, system)
            self.assertIn("Use SI units.", s.instructions(c))
            other = s.mutate({"action": "chat", "workspace": "default", "model": "qwen3-it:4b"})["id"]
            self.assertNotIn("Name the experiment", s.context(other, "hi")[0]["content"])

    def test_limits_and_old_clients(self):
        with tempfile.TemporaryDirectory(dir=RUNS) as h:
            s = Store(h)
            base = {k: v for k, v in s.state()["settings"].items() if k not in ("about_me", "instructions")}
            s.mutate({"action": "settings", "settings": base})          # a page from before this change still saves
            with self.assertRaises(ValueError):
                s.mutate({"action": "settings", "settings": {**base, "instructions": "x" * 2001}})
            with self.assertRaises(ValueError):
                s.mutate({"action": "settings", "settings": {**base, "assistant_name": ""}})
            with self.assertRaises(ValueError):
                s.mutate({"action": "workspace_instructions", "id": "default", "instructions": "x" * 2001})

    def test_an_older_database_is_upgraded(self):
        with tempfile.TemporaryDirectory(dir=RUNS) as h:
            db = sqlite3.connect(Path(h) / "chats.sqlite3")
            db.executescript("""CREATE TABLE settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
                CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT NOT NULL);
                INSERT INTO workspaces VALUES('default','Personal'),('abc','Old');""")
            db.execute("INSERT INTO settings VALUES(1,?)", (json.dumps({k: v for k, v in DEFAULTS.items()
                                                                       if k not in ("about_me", "instructions")}),))
            db.commit()
            db.close()
            s = Store(h)
            st = s.state()
            self.assertEqual(st["settings"]["instructions"], "")
            self.assertEqual({w["id"]: w["instructions"] for w in st["workspaces"]}, {"default": "", "abc": ""})


if __name__ == "__main__":
    unittest.main()
