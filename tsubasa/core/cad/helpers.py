"""Tested building blocks for the 3D Print designer, written in plain OpenSCAD.

A small local model composes these far more reliably than raw geometry (a bent hook arm is one path_rod() call, a
countersunk screw hole one screw_hole() cutter). They are appended after the model's code, only those it uses and
does not define itself, so line numbers in error messages stay the model's own and the saved .scad file opens in
real OpenSCAD too.
"""
import re

HELPERS = {
    "rounded_plate": """
// rounded_plate([x, y, z], r): a block with rounded vertical edges, corner at the origin, standing on z = 0
module rounded_plate(size, r = 3) {
  rr = min(r, size[0] / 2 - 0.01, size[1] / 2 - 0.01);
  hull() for (x = [rr, size[0] - rr], y = [rr, size[1] - rr]) translate([x, y, 0]) cylinder(h = size[2], r = rr);
}""",
    "rounded_box": """
// rounded_box([x, y, z], r): a block with all edges rounded, corner at the origin
module rounded_box(size, r = 2) {
  rr = min(r, size[0] / 2 - 0.01, size[1] / 2 - 0.01, size[2] / 2 - 0.01);
  hull() for (x = [rr, size[0] - rr], y = [rr, size[1] - rr], z = [rr, size[2] - rr]) translate([x, y, z]) sphere(r = rr);
}""",
    "rod": """
// rod(a, b, d): a round bar from point a to point b with diameter d (rounded ends)
module rod(a, b, d) { hull() { translate(a) sphere(d = d); translate(b) sphere(d = d); } }""",
    "path_rod": """
// path_rod([p0, p1, p2, ...], d): a round bar through the points (hook arms, handles, bent wire shapes)
module path_rod(points, d) {
  assert(is_list(points) && len(points) >= 2 && is_list(points[0]), "path_rod() takes ONE list of points: path_rod([[x, y, z], [x, y, z], ...], d = 6)");
  for (i = [0 : len(points) - 2]) hull() { translate(points[i]) sphere(d = d); translate(points[i + 1]) sphere(d = d); }
}""",
    "screw_hole": """
// screw_hole(d, depth, head_d, countersunk): a CUTTER for difference(). The shaft goes from z = 0 up to z = depth,
// the screw head sits at the top face (z = depth). d is the screw size; 0.3 mm clearance is added.
module screw_hole(d = 4, depth = 5, head_d = 0, countersunk = true) {
  hd = head_d > 0 ? head_d : 2 * d;
  translate([0, 0, -0.5]) cylinder(h = depth + 1, d = d + 0.3);
  if (countersunk) translate([0, 0, depth - (hd - d) / 2]) cylinder(h = (hd - d) / 2 + 0.5, d1 = d + 0.3, d2 = hd + 1 + 0.3);
  else translate([0, 0, depth - d * 0.6]) cylinder(h = d * 0.6 + 0.5, d = hd + 0.3);
}""",
    "tube": """
// tube(od, id, h): a hollow cylinder standing on z = 0
module tube(od, id, h) { difference() { cylinder(h = h, d = od); translate([0, 0, -0.5]) cylinder(h = h + 1, d = id); } }""",
    "slot": """
// slot(length, d, h): a rounded slot along X centred on the origin, standing on z = 0 (solid; use it as a cutter too)
module slot(length, d, h) { hull() for (x = [-length / 2, length / 2]) translate([x, 0, 0]) cylinder(h = h, d = d); }""",
    "chamfer_cube": """
// chamfer_cube([x, y, z], c): a block with 45° chamfered vertical edges, corner at the origin, standing on z = 0
module chamfer_cube(size, c = 1) {
  linear_extrude(height = size[2]) polygon([[c, 0], [size[0] - c, 0], [size[0], c], [size[0], size[1] - c],
    [size[0] - c, size[1]], [c, size[1]], [0, size[1] - c], [0, c]]);
}""",
}

DOC = """Ready-made modules (use them; they are added automatically, do not copy them):
- rounded_plate([x, y, z], r = 3): block with rounded vertical edges, corner at the origin, on z = 0.
- rounded_box([x, y, z], r = 2): block with all edges rounded, corner at the origin.
- chamfer_cube([x, y, z], c = 1): block with 45° chamfered vertical edges, corner at the origin.
- rod(a, b, d): round bar from point a to point b, diameter d.
- path_rod([p0, p1, p2, ...], d): round bar through several points (hook arms, handles, bent shapes).
- tube(od, id, h): hollow cylinder on z = 0.
- slot(length, d, h): rounded slot along X, centred, on z = 0.
- screw_hole(d = 4, depth = 5, head_d = 0, countersunk = true): CUTTER for difference(); shaft from z = 0 to
  z = depth, head at the top (z = depth). Place it with translate() under the face where the screw head goes.
To stand a plate up against a wall (y = 0 to y = t, height in Z):
  translate([0, t, 0]) rotate([90, 0, 0]) rounded_plate([w, h, t], 3);
and a screw hole through it, head on the front (+Y) face:
  translate([x, 0, z]) rotate([-90, 0, 0]) screw_hole(4, t);"""


def used(script):
    """The helpers and ready-made parts the script calls but does not define itself (parts bring their blocks)."""
    from core.cad import parts
    every = {**HELPERS, **parts.PARTS}
    own = set(re.findall(r"\bmodule\s+([A-Za-z_]\w*)", script))
    names = [n for n in every if n not in own and re.search(r"\b" + n + r"\s*\(", script)]
    for n in list(names):
        for need in parts.NEEDS.get(n, []):
            if need not in names and need not in own:
                names.append(need)
    return names


def with_helpers(script):
    from core.cad import parts
    every = {**HELPERS, **parts.PARTS}
    names = used(script)
    if not names:
        return script
    return script.rstrip() + "\n\n// ---- Tsubasa building blocks (plain OpenSCAD) ----" + "".join(every[n] for n in names) + "\n"
