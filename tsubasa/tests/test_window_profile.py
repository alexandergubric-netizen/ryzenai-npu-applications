"""The window profile is cleaned of downloaded browser components, but never while a window is using it."""
import tempfile
import unittest
from pathlib import Path

import app

RUNS = Path(__file__).resolve().parents[1] / ".test-runs"


class WindowProfileTests(unittest.TestCase):
    def make(self, root):
        for name in ("component_crx_cache", "ProvenanceData", "Default"):
            (root / name).mkdir()
            (root / name / "x.bin").write_bytes(b"0" * 10)

    def test_stale_components_go_and_the_profile_stays(self):
        with tempfile.TemporaryDirectory(dir=RUNS) as d:
            root = Path(d)
            self.make(root)
            app.tidy_window(root)
            self.assertFalse((root / "component_crx_cache").exists())
            self.assertFalse((root / "ProvenanceData").exists())
            self.assertTrue((root / "Default" / "x.bin").exists())

    def test_nothing_is_touched_while_a_window_holds_the_profile(self):
        with tempfile.TemporaryDirectory(dir=RUNS) as d:
            root = Path(d)
            self.make(root)
            with open(root / "lockfile", "w"):   # a running Edge keeps this file open
                app.tidy_window(root)
            self.assertTrue((root / "component_crx_cache").exists())

    def test_window_flags_switch_off_background_downloads(self):
        self.assertIn("--disable-component-update", app.EDGE_FLAGS)
        self.assertIn("--disable-background-networking", app.EDGE_FLAGS)


if __name__ == "__main__":
    unittest.main()
