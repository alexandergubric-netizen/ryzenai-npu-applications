"""The Bitmap (1-bit retro) theme: the setting is accepted and the bundled pixel font is a complete TrueType file."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "web" / "fonts" / "tsubasa-bitmap.ttf"
sys.path.insert(0, str(ROOT / "tools"))
import make_pixel_font  # noqa: E402
from core.storage import Store  # noqa: E402


def tables(data):
    n = struct.unpack(">H", data[4:6])[0]
    out = {}
    for i in range(n):
        tag, _, off, ln = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
        out[tag.decode()] = data[off:off + ln]
    return out


class BitmapThemeTests(unittest.TestCase):
    def test_theme_setting(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".test-runs") as h:
            s = Store(h)
            st = s.state()["settings"]
            s.mutate({"action": "settings", "settings": {**st, "theme": "bitmap"}})
            self.assertEqual(s.state()["settings"]["theme"], "bitmap")
            with self.assertRaises(ValueError):
                s.mutate({"action": "settings", "settings": {**st, "theme": "neon"}})

    def test_font_is_complete_and_matches_its_source(self):
        data = FONT.read_bytes()
        t = tables(data)
        self.assertEqual(set(t), {"OS/2", "cmap", "glyf", "head", "hhea", "hmtx", "loca", "maxp", "name", "post"})
        self.assertEqual(len(t["OS/2"]), 96)
        self.assertEqual(struct.unpack(">I", t["head"][12:16])[0], 0x5F0F3CF5)
        self.assertEqual(sum(struct.unpack(f">{len(data) // 4}I", data + b"\0" * (-len(data) % 4))) & 0xFFFFFFFF, 0xB1B0AFBA)
        glyphs = struct.unpack(">H", t["maxp"][4:6])[0]
        self.assertEqual(len(t["loca"]) // 4, glyphs + 1)
        self.assertEqual(len(t["hmtx"]) // 4, glyphs)
        # rebuilding gives the same glyphs (only the timestamps and checksums differ)
        rebuilt = tables(make_pixel_font.build()[0])
        self.assertEqual(rebuilt["glyf"], t["glyf"])
        self.assertEqual(rebuilt["cmap"], t["cmap"])

    def test_slovak_and_czech_letters_are_drawn(self):
        cmap = tables(FONT.read_bytes())["cmap"]
        for ch in "áäčďéíĺľňóôŕšťúýžÁÄČĎÉÍĹĽŇÓÔŔŠŤÚÝŽěřůĚŘŮöüß€→✓":
            self.assertIn(struct.pack(">H", ord(ch)), cmap, ch)


if __name__ == "__main__":
    unittest.main()
