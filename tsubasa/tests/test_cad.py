"""3D Print: the OpenSCAD-subset interpreter, CSG geometry, STL output, materials, parameters and the /api/cad endpoints
(design with a repair round, render, download), without the real engine."""
import http.client
import json
import math
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path

import app as tsubasa
from core import cad_api
from core.cad import geometry, materials, scad
from core.cad.geometry import CadError

RUNS = Path(__file__).resolve().parents[1] / ".test-runs"


def build(src, overrides=None):
    polys, echo = scad.build(src, overrides)
    return polys, echo, geometry.stats(polys)


class InterpreterTests(unittest.TestCase):
    def vol(self, src, overrides=None):
        return build(src, overrides)[2]["volume_mm3"]

    def test_primitives_and_booleans_have_exact_volumes(self):
        self.assertAlmostEqual(self.vol("cube(10);"), 1000, places=3)
        self.assertAlmostEqual(self.vol("cube([10, 20, 2], center = true);"), 400, places=3)
        self.assertAlmostEqual(self.vol("intersection(){cube(10); translate([5,5,5]) cube(10);}"), 125, places=3)
        self.assertAlmostEqual(self.vol("union(){cube(10); translate([5,0,0]) cube(10);}"), 1500, places=3)
        # a 64-sided hole: the exact polygon area, not pi r^2
        hole = 0.5 * 64 * 9 * math.sin(2 * math.pi / 64) * 20
        self.assertAlmostEqual(self.vol("$fn=64; difference(){cube(20,center=true); cylinder(h=22,r=3,center=true);}"),
                               8000 - hole, delta=0.06)
        self.assertAlmostEqual(self.vol("hull(){cube(2); translate([10,0,0]) cube(2);}"), 48, places=3)
        self.assertAlmostEqual(self.vol("polyhedron(points=[[0,0,0],[10,0,0],[0,10,0],[0,0,10]], "
                                        "faces=[[0,1,2],[0,3,1],[0,2,3],[1,3,2]]);"), 1000 / 6, delta=0.06)
        sphere = self.vol("sphere(r = 10, $fn = 48);")
        self.assertTrue(0.95 * 4 / 3 * math.pi * 1000 < sphere < 4 / 3 * math.pi * 1000, sphere)

    def test_extrusions_and_2d(self):
        self.assertAlmostEqual(self.vol("linear_extrude(height = 5) square(10);"), 500, places=3)
        circle = 0.5 * 32 * 4 * math.sin(2 * math.pi / 32)
        self.assertAlmostEqual(self.vol("linear_extrude(height=5) difference(){square(10,center=true); circle(r=2,$fn=32);}"),
                               (100 - circle) * 5, delta=0.06)
        ring = self.vol("rotate_extrude($fn = 96) translate([10, 0]) square([2, 4]);")
        self.assertAlmostEqual(ring, math.pi * (144 - 100) * 4, delta=2)
        tri = self.vol("linear_extrude(height = 2) polygon([[0,0],[10,0],[0,10]]);")
        self.assertAlmostEqual(tri, 100, places=3)
        # facets of a twisted extrusion converge on the smooth solid (16 mm² × 10 mm) as the slices grow
        coarse, fine = (build(f"linear_extrude(height = 10, twist = 90, slices = {n}) square(4, center = true);")[2]["volume_mm3"]
                        for n in (8, 64))
        self.assertLess(abs(fine - 160), abs(coarse - 160))
        self.assertAlmostEqual(fine, 160, delta=2)

    def test_transforms(self):
        _, _, st = build("translate([5, 0, 0]) rotate([0, 0, 90]) cube([10, 2, 3]);")
        self.assertEqual([round(v, 3) for v in st["size"]], [2, 10, 3])
        self.assertEqual([round(v, 3) for v in st["min"]], [3, 0, 0])
        _, _, st = build("mirror([1, 0, 0]) translate([5, 0, 0]) cube(2);")
        self.assertAlmostEqual(st["min"][0], -7, places=3)
        self.assertAlmostEqual(st["volume_mm3"], 8, places=3)   # mirrored faces still point outwards
        self.assertAlmostEqual(self.vol("scale([2, 1, 1]) cube(5);"), 250, places=3)
        _, _, st = build("resize([30, 0, 0], auto = true) cube([10, 5, 2]);")
        self.assertEqual([round(v, 2) for v in st["size"]], [30, 15, 6])

    def test_language_features(self):
        self.assertAlmostEqual(self.vol("function sq(x) = x * x; cube(sq(3));"), 729, places=3)
        self.assertAlmostEqual(self.vol("pts = [for (i = [0:3]) [i * 10, 0, 0]]; for (p = pts) translate(p) cube(2);"), 32, places=3)
        self.assertAlmostEqual(self.vol("module plate(w = 4, t = 1) { cube([w, w, t]); } plate(t = 2); translate([10,0,0]) plate(6);"),
                               32 + 36, places=3)
        self.assertAlmostEqual(self.vol("module two() { children(0); translate([5,0,0]) children(0); } two() cube(1);"), 2, places=3)
        self.assertAlmostEqual(self.vol("n = 3; s = n > 2 ? 4 : 1; cube(s);"), 64, places=3)
        self.assertAlmostEqual(self.vol("v = [1, 2, 3]; cube([v.x, v[1], len(v)]);"), 6, places=3)
        self.assertAlmostEqual(self.vol("let (a = 2, b = a + 1) cube([a, b, 1]);"), 6, places=3)
        self.assertAlmostEqual(self.vol("if (false) cube(5); else cube(2);"), 8, places=3)
        self.assertAlmostEqual(self.vol("*cube(50); cube(1);"), 1, places=3)
        self.assertAlmostEqual(self.vol("x = cos(60) * 4 + max([1, 2]) + norm([3, 4]); cube(x);"), 9 ** 3, places=2)
        # assignments are hoisted per block, as in OpenSCAD
        self.assertAlmostEqual(self.vol("cube(w); w = 3;"), 27, places=3)
        _, echo, _ = build('echo("width", 5); cube(1);')
        self.assertTrue(any("width" in e and "5" in e for e in echo), echo)

    def test_errors_name_the_line_and_the_fix(self):
        cases = {
            "cube(10);\ntranslate([0,0,0] cube(5);": "Line 2: expected ')'",
            "cub(10);": "Line 1: unknown module cub()",
            "minkowski(){cube(5); sphere(1);}": "hull()",
            "offset(r = 1) square(5);": "not available",
            'import("a.stl");': "not available",
            "\n\ncube(size);": "Line 3: cube(): cube size must be a number (got undef",
            "w = 5;\ncube([w, depht, 2]);": "'depht' is not defined",
            "module m(n) { m(n + 1); } m(0);": "recurses too deeply",
            "function f(n) = f(n + 1); cube(f(1));": "recurses too deeply",
            'assert(false, "too small"); cube(1);': "assert failed: too small",
            "x = 1;": "no solid",
            "for (i = [0:1:1e9]) cube(1);": "too long",
            "linear_extrude(5) cube(2);": "needs a 2D shape",
            # habits from other languages get an explanation the model can act on (seen live 2026-11-04)
            "cube(1);\ntoRad(x) { return x * PI / 180; }": "Line 2: 'toRad(...) { ... }' with 'return' is not OpenSCAD",
            "function f(x) { return x; }": "Line 1:",
            "return 5;": "no 'return'",
            "var w = 5;": "OpenSCAD has no 'var'",
            "cube(1);\nmodule cone(h=10,r=5): cylinder(h=h,r=r);": "Line 2: a module body goes in braces",
        }
        for src, want in cases.items():
            with self.subTest(src=src), self.assertRaises(CadError) as ctx:
                scad.build(src)
            self.assertIn(want, str(ctx.exception))

    def test_runaway_models_stop_quickly(self):
        t = time.time()
        with self.assertRaises(CadError):
            scad.build("for (i = [0:99999]) translate([i * 2, 0, 0]) cube(1);")
        self.assertLess(time.time() - t, 60)
        with self.assertRaises(CadError):
            cad_api.build("function f(n) = n <= 0 ? 0 : 1 + f(n - 1); cube(f(100000));")

    def test_parameters_and_overrides(self):
        src = "width = 60;   // Width of the base [20:200]\nlid = true;  // Print a lid\nwall = 2.0;\nh = width / 2;\ncube([width, 10, h]);\n"
        params = scad.parameters(src)
        self.assertEqual([p["name"] for p in params], ["width", "lid", "wall"])
        self.assertEqual((params[0]["label"], params[0]["min"], params[0]["max"]), ("Width of the base", 20, 200))
        self.assertIs(params[1]["value"], True)
        _, _, st = build(src, {"width": 100})
        self.assertEqual([round(v, 3) for v in st["size"]], [100, 10, 50])
        edited = cad_api.apply_overrides(src, {"width": 100, "lid": False})
        self.assertIn("width = 100; // Width of the base [20:200]", edited)
        self.assertIn("lid = false; // Print a lid", edited)
        self.assertEqual(scad.parameters(edited)[0]["value"], 100)
        # units after the range are not part of the label (the form shows the unit itself)
        labels = [p["label"] for p in scad.parameters("a = 1; // Back plate width [30:60] mm\nb = 2; // Depth (mm)\n"
                                                      "c = 3; // Angle [0:90]\n")]
        self.assertEqual(labels, ["Back plate width", "Depth", "Angle"])


class HelperTests(unittest.TestCase):
    def test_every_helper_builds_and_is_appended_only_when_used(self):
        from core.cad import helpers
        uses = {"rounded_plate": "rounded_plate([40, 20, 5], 3);", "rounded_box": "rounded_box([20, 20, 10], 2);",
                "chamfer_cube": "chamfer_cube([20, 10, 5], 1);", "rod": "rod([0, 0, 2], [30, 0, 2], 4);",
                "path_rod": "path_rod([[0, 0, 3], [0, 0, 40], [10, 0, 50]], 6);", "tube": "tube(20, 16, 10);",
                "slot": "slot(20, 5, 3);", "screw_hole": "difference() { cube([20, 20, 5]); translate([10, 10, 0]) screw_hole(4, 5); }"}
        self.assertEqual(set(uses), set(helpers.HELPERS))
        for name, src in uses.items():
            with self.subTest(name=name):
                full = helpers.with_helpers(src)
                self.assertIn("module " + name, full)
                self.assertGreater(geometry.stats(scad.build(full)[0])["volume_mm3"], 0)
        self.assertEqual(helpers.with_helpers("cube(1);"), "cube(1);")
        # the model's own module of the same name wins, and line numbers stay the model's own
        own = "module rod(a, b, d) { cube(1); }\nrod(0, 0, 0);"
        self.assertNotIn("Tsubasa building blocks", helpers.with_helpers(own))
        # path_rod called with loose points instead of one list says how to call it
        with self.assertRaises(CadError) as ctx:
            scad.build(helpers.with_helpers("path_rod([0, 0, 0], [10, 0, 0], d = 6);"))
        self.assertIn("takes ONE list of points", str(ctx.exception))
        with self.assertRaises(CadError) as ctx:
            scad.build(helpers.with_helpers("rod([0,0,0], [9,0,0], 2);\n\ncub(1);"))
        self.assertIn("Line 3:", str(ctx.exception))

    def test_countersunk_hole_removes_the_right_volume(self):
        from core.cad import helpers
        plate = geometry.stats(scad.build("cube([20, 20, 5]);")[0])["volume_mm3"]
        holed = geometry.stats(scad.build(helpers.with_helpers(
            "$fn = 48; difference() { cube([20, 20, 5]); translate([10, 10, 0]) screw_hole(4, 5); }"))[0])
        removed = plate - holed["volume_mm3"]
        shaft = math.pi * 2.15 ** 2 * 5
        self.assertGreater(removed, shaft)               # the countersink takes more than the plain shaft
        self.assertLess(removed, math.pi * 4.65 ** 2 * 5)
        self.assertEqual([round(v, 3) for v in holed["size"]], [20, 20, 5])

    def test_code_is_found_even_when_the_block_is_not_closed(self):
        self.assertEqual(cad_api.code_of("Text\n```openscad\ncube(1);\n```\nMore"), "cube(1);")
        self.assertEqual(cad_api.code_of("Text\n```openscad\ncube(2);\n// the model stopped here"), "cube(2);\n// the model stopped here")
        self.assertIsNone(cad_api.code_of("No code at all."))
        # an unclosed block stops where the explanation starts
        self.assertEqual(cad_api.code_of("```openscad\ncube(3);\n\n**What I designed**: 40 × 60 mm"), "cube(3);")
        # plain prose after an unclosed block (seen live: "unexpected ':'" past the end of the model)
        self.assertEqual(cad_api.code_of("```openscad\nw = 5; // Width\ncube(w);\n\nMaterial: PLA is fine here.\n"
                                         "Print settings: 0.2 mm layers."), "w = 5; // Width\ncube(w);")
        self.assertEqual(cad_api.code_of("```openscad\ncube(4);\nThis pyramid prints without any supports at all.\n"),
                         "cube(4);")
        self.assertEqual(cad_api.code_of("```openscad\nfor (i = [0:2])\n  translate([i * 10, 0, 0])\n    cube(2);\n"),
                         "for (i = [0:2])\n  translate([i * 10, 0, 0])\n    cube(2);")
        self.assertEqual(geometry.stats(scad.build("cube([2 × 5, 4, 3 − 1]);")[0])["size"], [10, 4, 2])
        self.assertIsNone(cad_api.code_of("```python\nprint(1)"))


class PartsTests(unittest.TestCase):
    """Every ready-made part builds as one printable solid with the sizes it was given (sets are flagged)."""
    def part(self, src):
        from core.cad import helpers
        polys, echo = scad.build(helpers.with_helpers("$fn = 32; " + src))
        flat, note = geometry.lay_flat(polys)
        return geometry.stats(polys), geometry.pieces(polys), any("MULTIPART" in e for e in echo), geometry.stats(flat), note

    def test_every_part_builds_as_one_solid(self):
        from core.cad import parts
        calls = {"wall_hook": "wall_hook();", "l_bracket": "l_bracket();", "box": "box(lid = false);",
                 "phone_stand": "phone_stand();", "cable_clip": "cable_clip();", "knob": "knob();",
                 "hose_adapter": "hose_adapter();", "mount_plate": "mount_plate();",
                 "pyramid": "pyramid(base_w = 25, h = 37);"}
        self.assertEqual(set(calls), set(parts.PARTS))
        for name, src in calls.items():
            with self.subTest(name=name):
                st, loose, _, printed, _ = self.part(src)
                self.assertEqual(len(loose), 1)
                self.assertGreater(st["volume_mm3"], 100)
                self.assertLess(printed["overhang_pct"], 8)
            with self.subTest(name=name, doc=True):
                self.assertIn(name + "(", parts.DOC)

    def test_parts_follow_the_given_sizes(self):
        st, _, _, printed, note = self.part("wall_hook(plate_w = 40, plate_h = 60, plate_t = 5, arm_len = 45, tip_up = 15);")
        self.assertEqual(round(st["size"][0]), 40)
        self.assertEqual(round(st["size"][2]), 60)
        self.assertAlmostEqual(st["size"][1], 45, delta=0.2)     # reach from the wall
        self.assertGreaterEqual(st["min"][1], -1e-6)              # nothing behind the back plate
        self.assertIn("−Y side", note)                            # printed lying on its back
        st, *_ = self.part("l_bracket(wall_leg = 50, shelf_leg = 40, width = 25, thick = 5);")
        self.assertEqual([round(v) for v in st["size"]], [25, 40, 50])
        st, *_ = self.part("hose_adapter(d1 = 25, d2 = 16, len1 = 20, len2 = 20, cone = 10);")
        self.assertEqual([round(v) for v in st["size"]], [25, 25, 50])
        st, *_ = self.part("mount_plate(w = 80, d = 50, t = 4);")
        self.assertEqual([round(v) for v in st["size"]], [80, 50, 4])

    def test_requests_are_matched_to_parts(self):
        from core.cad import parts
        cases = {"A wall hook for a bath towel, 40 mm wide": "wall_hook", "Coat hanger hook for my door": "wall_hook",
                 "A shelf bracket 150 mm deep": "l_bracket", "A small box with a lid for SD cards": "box",
                 "A phone stand for my desk": "phone_stand", "Stand for my phone, 65 degrees": "phone_stand",
                 "A set of 4 cable clips for 6 mm cables": "cable_clip", "Replacement knob for a 6 mm D-shaft": "knob",
                 "Adapter from my vacuum hose (35 mm) to a 25 mm pipe": "hose_adapter",
                 "A mounting plate 80 x 50 with four holes": "mount_plate",
                 "A simple pyramid 2.5 cm x 2.5 cm": "pyramid", "A chess pawn 30 mm tall": None, "A gear with 20 teeth": None}
        for msg, want in cases.items():
            with self.subTest(msg=msg):
                self.assertEqual(parts.suggest(msg), want)
        note = parts.hint("wall_hook")
        self.assertIn("wall_hook(plate_w = 40", note)
        self.assertIn("Do not redraw it", note)

    def test_unasked_extras_around_a_part_are_trimmed(self):
        from core.cad import parts
        # what liberty sent live for "Design a simple pyramid, 2.5 cm x 2.5 cm" (2026-11-04)
        live = ("width = 25;      // Base width [10:60] mm\nheight = 30;     // Pyramid height [20:80] mm\n$fn = 48;\n\n"
                "difference() {\n    union() {\n        pyramid(base_w = width, base_d = 0, h = height);   // Square-based pyramid\n"
                "        translate([0, -height/2]) cube([18, 45, thickness]);    // Flat bed contact area\n    }\n"
                "    translate([5, height*0.6]) cylinder(h = thickness + 1, d = hole_d);   // Screw holes\n}\n\n"
                "thickness = 4;   // Wall thickness [2:8] mm\nhole_d = 4.2;     // Screw hole diameter [3:6] mm")
        msg = "Design a simple pyramid, 2.5 cm x 2.5 cm"
        self.assertEqual(parts.extras(live, "pyramid", msg), ["cube", "cylinder"])
        clean = parts.strip_to_part(live, "pyramid")
        self.assertIn("pyramid(base_w = width, base_d = 0, h = height);", clean)
        self.assertNotIn("cube", clean)
        st, loose, _, _, _ = self.part(clean)
        self.assertEqual(([round(v) for v in st["size"]], len(loose)), ([25, 25, 30], 1))
        self.assertEqual([p["name"] for p in scad.parameters(clean)], ["width", "height", "thickness", "hole_d"])
        # asked-for extras stay: holes in a hook the user wanted screwed on, a base under a pyramid
        hook = "wall_hook(plate_w = 40);\ntranslate([0, 0, 10]) rotate([-90, 0, 0]) cylinder(h = 6, d = 4);"
        self.assertEqual(parts.extras(hook, "wall_hook", "A hook with an extra hole for a 4 mm screw"), [])
        base = "pyramid(base_w = 25, h = 30);\ntranslate([-15, -15, -3]) cube([30, 30, 3]);"
        self.assertEqual(parts.extras(base, "pyramid", "A pyramid on a square base plate"), [])
        self.assertEqual(parts.extras("pyramid(base_w = 25, h = 30);", "pyramid", msg), [])

    def test_sets_are_flagged_so_they_are_not_joined(self):
        _, loose, multi, _, _ = self.part("box(w = 60, d = 40, h = 30);")
        self.assertEqual((len(loose), multi), (2, True))          # the box and its lid
        _, loose, multi, _, _ = self.part("cable_clip(count = 3);")
        self.assertEqual((len(loose), multi), (3, True))
        _, loose, multi, _, _ = self.part("cable_clip();")
        self.assertEqual((len(loose), multi), (1, False))


class ExperimentalToggleTests(unittest.TestCase):
    """3D Print is marked experimental, has a disclaimer and can be turned off in Settings → Experimental."""
    def test_settings_toggle_disclaimer_and_default(self):
        web = Path(__file__).resolve().parents[1] / "web"
        html = (web / "index.html").read_text(encoding="utf-8")
        js = (web / "app.js").read_text(encoding="utf-8")
        self.assertIn('<button type="button" data-pane="labs">Experimental</button>', html)
        self.assertIn('data-pref="print3d"', html)
        self.assertIn('id="print-warning"', html)
        self.assertIn("3D Print is experimental.", html)
        self.assertIn('class="nav-tag"', html)
        self.assertIn("print3d:true", js)                                    # on by default
        self.assertIn("if(m==='print3d'&&!prefs().print3d)m='chat';", js)    # off: the tab cannot be entered
        self.assertIn("$('print-tab').hidden=!p.print3d;", js)
        self.assertIn("$('print-warning').hidden=m!=='print3d';", js)


class GeometryTests(unittest.TestCase):
    def test_stl_is_a_valid_binary_file(self):
        polys, _, _ = build("difference(){cube(10); translate([2,2,-1]) cube([6,6,12]);}")
        data = geometry.stl(polys, "frame")
        n = struct.unpack("<I", data[80:84])[0]
        self.assertEqual(len(data), 84 + 50 * n)
        self.assertEqual(n, len(list(geometry.triangles(polys))))
        # closed and outward: the signed volume from the STL triangles matches
        vol = 0.0
        for i in range(n):
            vals = struct.unpack("<12f", data[84 + 50 * i:84 + 50 * i + 48])
            a, b, c = vals[3:6], vals[6:9], vals[9:12]
            vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
        self.assertAlmostEqual(vol, 1000 - 360, places=2)

    def test_overhangs_are_measured(self):
        flat = build("cube(10);")[2]
        self.assertEqual(flat["overhang_pct"], 0)              # the bottom face rests on the bed
        bridge = build("difference(){cube([30,10,10]); translate([5,-1,-1]) cube([20,12,6]);}")[2]
        self.assertGreater(bridge["overhang_mm2"], 150)        # the 20 × 10 ceiling of the arch

    def test_separate_pieces_are_found_but_seams_are_not_breaks(self):
        one = ["cube(10);", "$fn=48; union(){cube([40,60,5]); translate([20,30,0]) cylinder(h=30,r=5);}",
               "$fn=48; difference(){ union(){cube([40,60,5]); translate([10,10,0]) cube([5,40,20]); "
               "translate([20,30,4]) sphere(r=6);} translate([30,50,-1]) cylinder(h=10,r=2);}",
               "cube(10); translate([10,0,0]) cube(10);"]
        for src in one:
            with self.subTest(src=src):
                self.assertEqual(len(geometry.pieces(build(src)[0])), 1)
        parts = geometry.pieces(build("cube(10); translate([20,0,0]) cube(5); translate([0,30,0]) cube(2);")[0])
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], {"min": [0, 0, 0], "max": [10, 10, 10]})     # largest first
        self.assertEqual(parts[1], {"min": [20, 0, 0], "max": [25, 5, 5]})

    def test_parts_drawn_as_used_are_laid_flat_for_printing(self):
        from core.cad import helpers
        # a towel hook drawn on the wall: back plate in X/Z, arm out in +Y, tip up
        hook = helpers.with_helpers("$fn=32; cube([40, 5, 60]); path_rod([[20, 5, 24], [20, 50, 24], [20, 53, 39]], 8);")
        flat, note = geometry.lay_flat(build(hook)[0])
        st = geometry.stats(flat)
        self.assertIn("−Y side", note)                                         # lying on its back plate
        self.assertEqual([round(v, 2) for v in st["size"][:2]], [40, 60])
        self.assertAlmostEqual(st["min"][2], 0, places=6)
        self.assertLess(st["overhang_pct"], 5)
        flipped, note = geometry.lay_flat(build("$fn=48; cylinder(h=20, r1=0, r2=10);")[0])
        self.assertIn("top face", note)
        self.assertEqual(geometry.stats(flipped)["overhang_pct"], 0)
        # a good orientation stays as drawn (only centred on the bed), even a tall one
        for src in ("cube([30, 20, 10]);", "cube([10, 10, 50]);", "$fn=48; cylinder(h=20, r1=10, r2=0);",
                    "cube([4, 20, 30]); cube([30, 20, 4]);"):
            with self.subTest(src=src):
                out, note = geometry.lay_flat(build(src)[0])
                self.assertIsNone(note)
                self.assertEqual(geometry.stats(out)["size"], build(src)[2]["size"])

    def test_lettering_is_left_out_with_a_warning(self):
        polys, echo = scad.build('difference() { cube([30, 10, 3]); translate([2, 2, 2]) linear_extrude(2) text("HI"); }')
        self.assertAlmostEqual(geometry.volume(polys), 900, places=3)
        self.assertTrue(any(e.startswith("SKIPPED: line 1: text()") for e in echo), echo)

    def test_hull_of_fine_spheres_stays_fast(self):
        t = time.time()
        polys, _ = scad.build("$fn = 96; hull() { sphere(5); translate([30, 0, 0]) sphere(5); }")
        self.assertLess(time.time() - t, 10)
        self.assertAlmostEqual(geometry.stats(polys)["size"][0], 40, delta=0.1)

    def test_mesh_for_the_viewer(self):
        polys, _, _ = build("cube(1);")
        self.assertEqual(len(geometry.mesh_floats(polys)), 12 * 9)


class MaterialTests(unittest.TestCase):
    def test_estimates(self):
        e = materials.estimates(10000, "PLA", 0.2, area_mm2=3000)
        self.assertLess(e["printed_cm3"], 10)                  # 20 % infill uses less than solid
        self.assertGreater(e["printed_cm3"], 3)                # but walls are solid
        self.assertAlmostEqual(e["grams"], e["printed_cm3"] * materials.MATERIALS["PLA"]["density"], places=1)
        self.assertGreater(materials.estimates(10000, "PLA", 1.0, area_mm2=3000)["grams"], e["grams"])
        self.assertGreater(materials.estimates(10000, "PETG", 0.2, area_mm2=3000)["grams"], e["grams"])

    def test_table_covers_common_materials(self):
        for m in ("PLA", "PETG", "ABS", "ASA", "TPU 95A", "Nylon", "PC"):
            self.assertTrue(any(k.startswith(m) for k in materials.MATERIALS), m)
            self.assertIn(m, materials.prompt_table())
        self.assertIn("45", materials.DESIGN_RULES)


GOOD = """Here is the hook.

```openscad
width = 40;   // Width [20:80]
depth = 30;   // Depth [10:60]
$fn = 48;
difference() {
  union() { cube([width, 4, 50]); translate([0, 0, 0]) cube([width, depth, 4]); }
  for (x = [10, width - 10]) translate([x, -0.5, 35]) rotate([-90, 0, 0]) cylinder(h = 5, r = 2.1);
}
```

**What I designed**: a 40 mm wall hook.
**Material**: PETG."""
BROKEN = "```openscad\ncube([10, 10, 10]\n```\nA cube."


class FakeEngine:
    """Answers the first design request with broken code, the repair request with working code."""
    observed_model = None
    warming = None
    def __init__(self):
        self.calls = []
    def models(self):
        return [{"id": "qwen-liberty3.5:9b", "supports_vision": True}, {"id": "qwen3-it:4b"}]
    def require_model(self, model):
        if model not in ("qwen3-it:4b", "qwen-liberty3.5:9b"):
            raise ValueError("Select an installed chat model.")
    def detach(self):
        pass
    def stream(self, model, messages, max_tokens=0, cancelled=None, think=False, **kw):
        self.calls.append({"messages": messages, "think": think, "max_tokens": max_tokens})
        if think:
            yield "thinking", "The hook needs two screw holes. "
        yield "text", BROKEN if len(self.calls) == 1 else GOOD


class CadApiTests(unittest.TestCase):
    def setUp(self):
        self.box = tempfile.TemporaryDirectory(dir=RUNS)
        self.engine = FakeEngine()
        self.app = tsubasa.App(self.box.name, 0, self.engine)
        self.app.bind()
        self.thread = threading.Thread(target=self.app.server.serve_forever, daemon=True)
        self.thread.start()
        self.headers = {"Cookie": self.app.gate.cookie + "=" + self.app.gate.session, "X-Tsubasa": "1",
                        "Content-Type": "application/json"}

    def tearDown(self):
        self.app.server.shutdown()
        self.app.close()
        self.box.cleanup()

    def request(self, method, path, body=None, raw=False):
        c = http.client.HTTPConnection("127.0.0.1", self.app.gate.port, timeout=60)
        c.request(method, path, body if isinstance(body, (bytes, type(None))) else json.dumps(body), self.headers)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, (data if raw else json.loads(data or b"null"))

    check_reply = "OK"

    def events(self, body):
        # The shape check after each build is answered by self.check_reply (OK unless a test says otherwise).
        inner = self.engine.stream
        if not getattr(inner, "checks", False):
            self.checks = []
            def stream(model, messages, **kw):
                last = messages[-1].get("content", "")
                if isinstance(last, str) and last.startswith("I built your model and measured it:"):
                    self.checks.append(last)
                    return iter([("text", self.check_reply)])
                return inner(model, messages, **kw)
            stream.checks = True
            self.engine.stream = stream
        status, raw = self.request("POST", "/api/cad", body, raw=True)
        self.assertEqual(status, 200, raw[:300])
        return [json.loads(line[6:]) for line in raw.decode().split("\n") if line.startswith("data: ")]

    def test_materials(self):
        status, data = self.request("POST", "/api/cad", {"action": "materials"})
        self.assertEqual(status, 200)
        self.assertIn("PLA", data["materials"])
        self.assertIn("nozzle", data["materials"]["PETG"])

    def test_design_repairs_the_code_then_builds_and_saves(self):
        chat = self.app.store.mutate({"action": "chat", "workspace": "default", "model": "qwen-liberty3.5:9b"})["id"]
        evs = self.events({"action": "design", "chat_id": chat, "message": "A wall hook, 40 mm wide, 2 screws",
                           "model": "qwen-liberty3.5:9b", "think": True, "material": "PETG", "infill": 0.3, "bed": [180, 180, 180]})
        kinds = [e["type"] for e in evs]
        self.assertIn("thinking", kinds)
        self.assertIn("repair", kinds)
        self.assertLess(kinds.index("repair"), kinds.index("text_reset"))
        self.assertNotIn("error", kinds, evs)
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        self.assertEqual([round(v) for v in cad["stats"]["size"]], [40, 30, 50])
        self.assertEqual(cad["estimate"]["material"], "PETG")
        self.assertEqual([p["name"] for p in cad["params"]], ["width", "depth"])
        self.assertEqual(len(cad_api.base64.b64decode(cad["mesh"])) % 36, 0)
        # deep thinking first; the repair goes without it and carries the exact error
        self.assertEqual((self.engine.calls[0]["think"], self.engine.calls[0]["max_tokens"]), (True, 12288))
        self.assertFalse(self.engine.calls[1]["think"])
        self.assertIn("Line 1: expected ')' but the code ended", self.engine.calls[1]["messages"][-1]["content"])
        system = self.engine.calls[0]["messages"][0]["content"]
        for needle in ("OpenSCAD", "PETG", "180 × 180 × 180", "overhang"):
            self.assertIn(needle, system)
        # the files are in the workspace, and the answer is saved with the working code
        root = self.app.tools.files.root("default")
        self.assertTrue((root / cad["files"]["stl"]).is_file())
        self.assertIn("difference()", (root / cad["files"]["scad"]).read_text(encoding="utf-8"))
        saved = self.request("GET", f"/api/chats/{chat}")[1]["messages"]
        self.assertIn("width = 40;", saved[-1]["content"])
        # the next message sees the current design
        self.engine.calls.clear()
        self.engine.calls.append({})        # skip the broken first answer
        self.events({"action": "design", "chat_id": chat, "message": "Make it 60 mm wide", "model": "qwen-liberty3.5:9b",
                     "think": False})
        self.assertIn("The current design in this chat", self.engine.calls[1]["messages"][0]["content"])
        self.assertFalse(self.engine.calls[1]["think"])

    def design(self, message):
        chat = self.app.store.mutate({"action": "chat", "workspace": "default", "model": "qwen-liberty3.5:9b"})["id"]
        return self.events({"action": "design", "chat_id": chat, "message": message, "model": "qwen-liberty3.5:9b",
                            "think": True})

    def test_a_part_that_falls_apart_is_sent_back_once_with_its_pieces(self):
        apart = "```openscad\nw = 40; // Width [20:80]\ncube([w, 60, 5]);\ntranslate([60, 0, 0]) cube([10, 10, 30]);\n```\n**What I designed**: a plate with a post, sized as asked, ready to print in PLA."
        joined = "```openscad\nw = 40; // Width [20:80]\ncube([w, 60, 5]);\ntranslate([15, 25, 0]) cube([10, 10, 30]);\n```\n**What I designed**: a plate with a post, sized as asked, ready to print in PLA."
        answers = iter([apart, joined])
        self.engine.stream = lambda model, messages, **kw: (self.engine.calls.append({"messages": messages, **kw}) or
                                                            iter([("text", next(answers))]))
        evs = self.design("A plate with a post")
        review = next(e["data"] for e in evs if e["type"] == "repair")
        self.assertEqual(review["kind"], "review")
        note = self.engine.calls[1]["messages"][-1]["content"]
        self.assertIn("2 separate pieces", note)
        self.assertIn("piece 2: x 60 to 70", note)
        self.assertTrue(self.engine.calls[1]["think"])                         # the fix is thought through again
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        self.assertEqual(cad["stats"]["pieces"], 1)
        self.assertEqual(cad["warnings"], [])

    def test_a_set_of_parts_is_not_joined_and_a_broken_fix_keeps_the_working_version(self):
        apart = "```openscad\ncube(10);\ntranslate([20, 0, 0]) cube(10);\n```\n**What I designed**: a plate with a post, sized as asked, ready to print in PLA."
        self.engine.stream = lambda model, messages, **kw: (self.engine.calls.append(kw) or iter([("text", apart)]))
        evs = self.design("A set of 2 spacer cubes")
        self.assertEqual(len(self.engine.calls), 1)                             # no review for a set
        self.assertEqual(next(e["data"] for e in evs if e["type"] == "cad")["stats"]["pieces"], 2)
        answers = iter([apart, "```openscad\ncub(1);\n```", "```openscad\ncub(2);\n```", "```openscad\ncub(3);\n```"])
        self.engine.calls.clear()
        self.engine.stream = lambda model, messages, **kw: (self.engine.calls.append(kw) or iter([("text", next(answers))]))
        evs = self.design("A plate with a post")
        kinds = [e["data"].get("kind") for e in evs if e["type"] == "repair"]
        self.assertEqual(kinds, ["review", "build", "build"])
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        self.assertEqual(cad["stats"]["pieces"], 2)                             # the version that built, with its warning
        self.assertIn("separate pieces", cad["warnings"][0])

    def test_code_written_only_in_the_thinking_is_used_and_saved(self):
        def stream(model, messages, **kw):
            self.engine.calls.append(kw)
            yield "thinking", "Plan done.\n```openscad\ncube(4);\n```\nNow the final version:\n```openscad\ncube([20, 10, 5]);\n```\n"
            yield "text", "**What I designed**: a block."
        self.engine.stream = stream
        evs = self.design("A 20 x 10 x 5 block")
        self.assertNotIn("repair", [e["type"] for e in evs])
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        self.assertEqual([round(v) for v in cad["stats"]["size"]], [20, 10, 5])
        chat = self.app.store.state()["chats"][0]["id"]
        saved = self.request("GET", f"/api/chats/{chat}")[1]["messages"][-1]["content"]
        self.assertTrue(saved.startswith("```openscad\ncube([20, 10, 5]);\n```"), saved)

    def test_a_pyramid_drawn_as_a_cube_is_caught_and_corrected(self):
        # seen live 2026-11-04: "a simple pyramid" came back as a cube with an empty "four faces" comment
        cube = ("```openscad\nwidth = 25; // Base width [15:40]\nheight = 37; // Height [20:60]\n"
                "cube([width, width, height]); // four triangular faces meeting at the apex\n```\n"
                "**What I designed**: a pyramid with a 25 mm base, 37 mm tall, ready for PLA.")
        self.engine.stream = lambda model, messages, **kw: (self.engine.calls.append(kw) or iter([("text", cube)]))
        self.check_reply = ("It was a box, not a pyramid.\n```openscad\nwidth = 25; // Base width [15:40]\n"
                            "height = 37; // Height [20:60]\npyramid(base_w = width, h = height);\n```")
        evs = self.design("A simple pyramid, 25 x 25 mm base, 37 mm tall")
        note = self.checks[0]
        self.assertIn("fills 100 % of its bounding box", note)
        self.assertIn("WARNING", note)
        fix = next(e["data"] for e in evs if e["type"] == "repair")
        self.assertEqual((fix["kind"], fix["error"]), ("check", "It was a box, not a pyramid."))
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        self.assertEqual([round(v) for v in cad["stats"]["size"]], [25, 25, 37])
        self.assertAlmostEqual(cad["stats"]["volume_mm3"], 25 * 25 * 37 / 3, delta=30)
        self.assertIn("**What I designed**", cad["answer"])           # the explanation survives the correction
        self.assertEqual(len(self.checks), 1)                          # checked once, not in a loop

    def test_a_pyramid_with_invented_screw_holes_is_trimmed_and_advised_again(self):
        holes = ("```openscad\nw = 25; // Base width [10:60]\nh = 30; // Height [20:80]\n$fn = 32;\ndifference() {\n"
                 "  pyramid(base_w = w, h = h);\n  translate([5, 5, -1]) cylinder(h = 10, d = 3.5); // mounting hole\n}\n```\n"
                 "**What I designed**: a pyramid with four corner screw holes for mounting, in PLA.")
        answers = iter([[("text", holes)], [("text", "**What I designed**: a 25 mm square pyramid, 30 mm tall.\n"
                                                     "**Material**: PLA.")]])
        self.engine.stream = lambda model, messages, **kw: (self.engine.calls.append({"messages": messages, **kw})
                                                            or iter(next(answers)))
        evs = self.design("Design a simple pyramid, 2.5 cm x 2.5 cm")
        trim = next(e["data"] for e in evs if e["type"] == "repair")
        self.assertEqual((trim["kind"], trim["error"]), ("trim", "cylinder"))
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        self.assertEqual([round(v) for v in cad["stats"]["size"]], [25, 25, 30])
        self.assertNotIn("cylinder", cad["script"])
        self.assertNotIn("screw holes", cad["answer"])               # the advice is written again for the clean part
        self.assertIn("25 mm square pyramid", cad["answer"])
        self.assertIn("25 × 25 × 30 mm as printed", self.engine.calls[1]["messages"][-1]["content"])

    def test_a_description_that_claims_missing_features_is_rewritten(self):
        # seen live: a plain pyramid described with "rounded corners" and "countersunk screw holes at each corner"
        claim = ("```openscad\nw = 25; // Base width [10:60]\nh = 30; // Height [20:80]\npyramid(base_w = w, h = h);\n```\n"
                 "**What I designed**: a square pyramid with rounded corners and countersunk screw holes at each corner.")
        self.assertEqual(cad_api.false_claims(claim.split("```")[-1], "pyramid(base_w = 25, h = 30);"),
                         ["countersunk", "rounded"])
        self.assertEqual(cad_api.false_claims("A hook with two countersunk screw holes.", "wall_hook();"), [])
        self.assertEqual(cad_api.contents("w = 2;\ntranslate([1, 0, 0]) pyramid(base_w = w); // a cube here\n"), "pyramid")
        answers = iter([[("text", claim)], [("text", "**What I designed**: a plain 25 mm square pyramid, 30 mm tall.")]])
        self.engine.stream = lambda model, messages, **kw: (self.engine.calls.append({"messages": messages, **kw})
                                                            or iter(next(answers)))
        evs = self.design("Design a simple pyramid, 2.5 cm x 2.5 cm")
        fix = next(e["data"] for e in evs if e["type"] == "repair")
        self.assertEqual(fix["kind"], "describe")
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        self.assertNotIn("screw", cad["answer"])
        self.assertIn("plain 25 mm square pyramid", cad["answer"])
        self.assertIn("made of exactly: pyramid", self.engine.calls[1]["messages"][-1]["content"])

    def test_a_good_model_is_confirmed_and_kept(self):
        good = "```openscad\ncube([20, 10, 5]);\n```\n**What I designed**: a 20 × 10 × 5 mm block for testing, in PLA."
        self.engine.stream = lambda model, messages, **kw: iter([("text", good)])
        evs = self.design("A 20 x 10 x 5 mm block")
        self.assertNotIn("repair", [e["type"] for e in evs])
        self.assertNotIn("WARNING", self.checks[0])
        self.assertIn("fills 100 %", self.checks[0])

    def test_code_only_answers_get_the_material_advice_afterwards(self):
        answers = iter([[("text", "```openscad\ncube([20, 10, 5]);\n```")],
                        [("text", "**What I designed**: a 20 × 10 × 5 mm block.\n**Material**: PETG, tough.")]])
        def stream(model, messages, **kw):
            self.engine.calls.append({"messages": messages, **kw})
            return iter(next(answers))
        self.engine.stream = stream
        evs = self.design("A 20 x 10 x 5 block")
        ask = self.engine.calls[1]["messages"][-1]["content"]
        self.assertIn("20 × 10 × 5 mm as printed", ask)
        self.assertIn("**Material**", ask)
        self.assertFalse(self.engine.calls[1]["think"])
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        self.assertIn("**Material**: PETG", cad["answer"])
        self.assertTrue(cad["answer"].startswith("```openscad\ncube([20, 10, 5]);"))

    def test_advice_that_repeats_the_code_falls_back_to_the_material_table(self):
        # seen live 2026-11-05: asked for the advice, the model sent the code again
        code = "```openscad\npyramid(base_w = 25, h = 30);\n```"
        self.engine.stream = lambda model, messages, **kw: (self.engine.calls.append({"messages": messages, **kw})
                                                            or iter([("text", code)]))
        evs = self.design("Design a simple pyramid, 2.5 cm x 2.5 cm")
        ask = self.engine.calls[1]["messages"]
        self.assertEqual(ask[0]["role"], "system")                     # a fresh question, not a continuation
        self.assertIn("Never write code", ask[0]["content"])
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        self.assertEqual(cad["answer"].count("```openscad"), 1)        # the code once, not twice
        self.assertIn("**Material**: PLA", cad["answer"])
        self.assertIn("nozzle 190-220 °C, bed 50-60 °C", cad["answer"])
        self.assertIn("25 × 25 × 30 mm as printed", cad["answer"])

    def test_the_live_unclosed_answer_is_assembled_cleanly(self):
        # live 2026-11-05: the fence was never closed and the text claimed screw holes and rounded edges; the page
        # then showed no text at all and the saved answer held three explanations
        live = ("```openscad\nbase_w = 25;      // Base width [10:60] mm\nh = 25;           // Pyramid height [15:60] mm\n\n"
                "$fn = 48;\n\ndifference() {\n    union() { pyramid(base_w, 0, h); }\n}\n\n\n"
                "**What I designed**: A square-based pyramid with 25 mm width and height. The model includes four corner "
                "screw holes (4 mm diameter) for mounting options. Rounded edges ensure clean printing.\n\n"
                "**Material**: PLA is ideal.\n\n**Print settings**: base down, no supports.")
        self.assertIn("pyramid(base_w, 0, h);", cad_api.code_of(live))
        self.assertTrue(cad_api.prose_of(live).startswith("**What I designed**: A square-based pyramid"))
        self.assertNotIn("pyramid(", cad_api.prose_of(live))
        bad_advice = "openscad\n\n**What I designed**: a pyramid with four corner screw holes and rounded edges."
        answers = iter([[("text", live)], [("text", bad_advice)]])
        self.engine.stream = lambda model, messages, **kw: iter(next(answers))
        evs = self.design("Design a simple pyramid, 2.5 cm x 2.5 cm")
        self.assertEqual([e["data"]["kind"] for e in evs if e["type"] == "repair"], ["describe"])
        cad = next(e["data"] for e in evs if e["type"] == "cad")
        answer = cad["answer"]
        self.assertEqual(answer.count("```"), 2)                       # one closed code block
        self.assertTrue(answer.startswith("```openscad\nbase_w = 25;"))
        self.assertNotIn("screw", answer)
        self.assertEqual(answer.count("**What I designed**"), 1)
        self.assertIn("**What I designed**: pyramid, 25 × 25 × 25 mm as printed.", answer)
        chat = self.app.store.state()["chats"][0]["id"]
        self.assertEqual(self.request("GET", f"/api/chats/{chat}")[1]["messages"][-1]["content"], answer)

    def test_render_with_new_dimensions_and_download(self):
        status, d = self.request("POST", "/api/cad", {"action": "render", "script": GOOD.split("```openscad\n")[1].split("```")[0],
                                                      "values": {"width": 70}, "workspace": "default", "material": "PLA"})
        self.assertEqual(status, 200, d)
        self.assertEqual(round(d["stats"]["size"][0]), 70)
        self.assertEqual(d["values"], {"width": 70})
        status, scad_text = self.request("GET", "/api/cad-file?workspace=default&name=" + d["files"]["scad"], raw=True)
        self.assertEqual(status, 200)
        self.assertIn(b"width = 70; // Width [20:80]", scad_text)
        status, stl = self.request("GET", "/api/cad-file?workspace=default&name=" + d["files"]["stl"], raw=True)
        self.assertEqual(status, 200)
        self.assertEqual(len(stl), 84 + 50 * struct.unpack("<I", stl[80:84])[0])
        # the same model again reuses its files
        again = self.request("POST", "/api/cad", {"action": "render", "script": GOOD.split("```openscad\n")[1].split("```")[0],
                                                  "values": {"width": 70}, "workspace": "default"})[1]
        self.assertEqual(again["files"], d["files"])

    def test_bad_requests(self):
        self.assertEqual(self.request("POST", "/api/cad", {"action": "render", "script": "cub(1);"})[0], 400)
        self.assertEqual(self.request("POST", "/api/cad", {"action": "render", "script": 5})[0], 400)
        self.assertEqual(self.request("POST", "/api/cad", {"action": "nope"})[0], 400)
        self.assertEqual(self.request("POST", "/api/cad", {"action": "design", "chat_id": "x", "message": "hi",
                                                           "model": "qwen3-it:4b"})[0], 400)
        for name in ("../app.py", "x.exe", "a/b.stl", "missing.stl"):
            self.assertEqual(self.request("GET", "/api/cad-file?workspace=default&name=" + name)[0], 404, name)
        big = json.dumps({"action": "render", "script": "cube(1);" + " " * 140000}).encode()
        try:
            status = self.request("POST", "/api/cad", big)[0]
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            status = 413        # refused before the whole body was sent
        self.assertIn(status, (400, 413))


if __name__ == "__main__":
    unittest.main()
