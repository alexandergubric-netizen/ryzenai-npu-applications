"""Ready-made parametric parts for the 3D Print designer, in plain OpenSCAD, each tested to build as one printable
solid (tests/test_cad.py). The local model is good at choosing a part and its sizes and weak at composing raw 3D
geometry, so for common objects it calls one of these with the user's dimensions and adds or cuts extra features.

All parts are drawn AS USED: X left-right, Y out from the wall / towards the back, Z up. Tsubasa lays the result flat
for printing. They use the building blocks in helpers.py, which are appended with them.
"""

PARTS = {
    "wall_hook": """
// wall_hook(): back plate on the wall (y = 0), a round arm out in +Y with an upturned tip, a strut under the arm,
// countersunk screw holes above the arm. arm_len = reach from the wall to the front of the arm.
module wall_hook(plate_w = 40, plate_h = 60, plate_t = 5, arm_len = 45, tip_up = 15, arm_d = 10, arm_z = 0,
                 screws = 2, screw_d = 4, countersunk = true) {
  az = arm_z > 0 ? arm_z : plate_h * 0.35;
  reach = max(arm_len - arm_d / 2, plate_t + arm_d / 2);
  root = max(plate_t - 1, arm_d / 2);                    // the arm starts in the plate, never behind its back face
  difference() {
    union() {
      translate([-plate_w / 2, plate_t, 0]) rotate([90, 0, 0]) rounded_plate([plate_w, plate_h, plate_t], min(4, plate_w / 4));
      path_rod([[0, root, az], [0, reach, az], [0, reach, az + tip_up]], arm_d);
      hull() {                                            // strut under the arm, against the plate
        translate([0, max(plate_t - 1, arm_d * 0.45), az]) sphere(d = arm_d * 0.9);
        translate([0, max(plate_t - 1, arm_d * 0.35), max(az - arm_d * 1.8, arm_d * 0.45)]) sphere(d = arm_d * 0.7);
        translate([0, plate_t + (reach - plate_t) * 0.4, az]) sphere(d = arm_d * 0.8);
      }
    }
    for (x = screws >= 2 ? [-plate_w / 4, plate_w / 4] : [0])
      translate([x, 0, plate_h * 0.8]) rotate([-90, 0, 0]) screw_hole(screw_d, plate_t, 0, countersunk);
  }
}""",
    "l_bracket": """
// l_bracket(): a shelf / angle bracket. Wall leg on y = 0 going up (Z), shelf leg along +Y on z = 0,
// two triangular gussets at the sides, one countersunk hole in each leg.
module l_bracket(wall_leg = 40, shelf_leg = 40, width = 20, thick = 4, hole_d = 4.2, gussets = true) {
  g = max(2, thick * 0.75);
  difference() {
    union() {
      translate([-width / 2, 0, 0]) cube([width, thick, wall_leg]);
      translate([-width / 2, 0, 0]) cube([width, shelf_leg, thick]);
      if (gussets) for (x = [-width / 2, width / 2 - g])
        translate([x, 0, 0]) rotate([90, 0, 90]) linear_extrude(height = g)
          polygon([[thick - 0.5, thick - 0.5], [shelf_leg * 0.75, thick - 0.5], [thick - 0.5, wall_leg * 0.75]]);
    }
    translate([0, 0, wall_leg * 0.65]) rotate([-90, 0, 0]) screw_hole(hole_d, thick, 0, true);
    translate([0, shelf_leg * 0.65, 0]) screw_hole(hole_d, thick, 0, true);
  }
}""",
    "box": """
// box(): an open-top box with rounded corners standing on z = 0, centred; with lid = true a matching push-fit lid
// is placed next to it (upside down, ready to print). Sizes are outside dimensions.
module box(w = 60, d = 40, h = 30, wall = 2, floor = 2, r = 3, lid = true, lid_t = 2, lip = 4, clearance = 0.3) {
  echo("MULTIPART");
  translate([-w / 2, -d / 2, 0]) difference() {
    rounded_plate([w, d, h], r);
    translate([wall, wall, floor]) rounded_plate([w - 2 * wall, d - 2 * wall, h], max(0.5, r - wall));
  }
  if (lid) translate([w / 2 + 10, -d / 2, 0]) {
    rounded_plate([w, d, lid_t], r);
    translate([wall + clearance, wall + clearance, lid_t - 0.01])
      difference() {
        rounded_plate([w - 2 * (wall + clearance), d - 2 * (wall + clearance), lip], max(0.5, r - wall));
        translate([1.6, 1.6, -0.5]) rounded_plate([w - 2 * (wall + clearance) - 3.2, d - 2 * (wall + clearance) - 3.2, lip + 1], max(0.5, r - wall - 1.6));
      }
  }
}""",
    "phone_stand": """
// phone_stand(): a desk stand. The phone leans back on a rest at `angle` degrees from the desk, its bottom edge held
// by a front lip; slot = phone thickness incl. case. A cable slot runs through the lip and base.
module phone_stand(width = 70, angle = 65, slot = 12, lip_h = 10, rest_len = 90, depth = 90, thick = 5, cable_slot = true) {
  y0 = depth * 0.35;                                        // foot of the rest
  top = [y0 + rest_len * cos(angle), thick + rest_len * sin(angle)];
  difference() {
    translate([-width / 2, 0, 0]) rotate([90, 0, 90]) linear_extrude(height = width) union() {
      square([depth, thick]);                                                    // base
      polygon([[y0, 0], [y0 + thick / sin(angle), 0], [top[0] + thick / sin(angle), top[1]], top]);   // rest
      polygon([[top[0] * 0.55 + y0 * 0.45 + thick, (top[1] - thick) * 0.55 + thick],
               [depth, thick - 0.01], [depth - thick * 1.5, thick - 0.01],
               [top[0] * 0.55 + y0 * 0.45, (top[1] - thick) * 0.55 + thick - thick * 1.2]]);              // strut
      translate([y0 - slot - thick, 0]) square([thick, lip_h + thick]);                                 // lip
    }
    if (cable_slot) translate([-6, y0 - slot - thick - 1, -1]) cube([12, slot + thick + 2, lip_h + thick + 2]);
  }
}""",
    "cable_clip": """
// cable_clip(): a screw-down clip for a cable running along X, on a desk or wall surface at z = 0. The ring opens at
// the top so the cable snaps in. count > 1 places a row of clips next to each other.
module cable_clip(cable_d = 6, width = 8, wall = 2, screw_d = 3.5, count = 1) {
  if (count > 1) echo("MULTIPART");
  od = cable_d + 2 * wall;
  for (i = [0 : count - 1]) translate([i * (width + 6), 0, 0]) difference() {
    union() {
      translate([-width / 2, -od / 2 - 2 * screw_d - 2, 0]) cube([width, od + 4 * screw_d + 4, wall]);    // tab
      translate([-width / 2, 0, od / 2]) rotate([0, 90, 0]) cylinder(h = width, d = od);
    }
    translate([-width / 2 - 1, 0, od / 2]) rotate([0, 90, 0]) cylinder(h = width + 2, d = cable_d);
    translate([-width / 2 - 1, -cable_d * 0.38, od / 2 + cable_d * 0.25]) cube([width + 2, cable_d * 0.76, od]);  // snap opening
    for (y = [-od / 2 - screw_d - 1, od / 2 + screw_d + 1]) translate([0, y, 0]) screw_hole(screw_d, wall, 0, false);
  }
}""",
    "knob": """
// knob(): a round control knob with grip ribs and a D-shaft hole from below. flat = across-flat size of the shaft
// (= shaft_d for a round shaft).
module knob(d = 30, h = 15, shaft_d = 6, flat = 4.5, depth = 12, ribs = 24) {
  difference() {
    union() {
      cylinder(h = h, d = d - 1);
      for (i = [0 : ribs - 1]) rotate([0, 0, i * 360 / ribs]) translate([d / 2 - 1, 0, 0]) cylinder(h = h, d = 2, $fn = 12);
      translate([0, 0, h - 0.01]) cylinder(h = 1, d1 = d - 1, d2 = d - 3);
    }
    translate([0, 0, -0.5]) intersection() {
      cylinder(h = depth + 0.5, d = shaft_d + 0.2);
      translate([-(shaft_d + 1) / 2, -(shaft_d + 1) / 2, 0]) cube([shaft_d + 1, flat + 0.1 + (shaft_d + 1) / 2 - shaft_d / 2, depth + 0.5]);
    }
    translate([0, 0, h + 0.2]) sphere(d = d * 0.35);                      // finger dimple
  }
}""",
    "hose_adapter": """
// hose_adapter(): joins two round hoses or pipes: an outer diameter d1 end and a d2 end with a cone between.
// Wall is the wall thickness; the bore runs straight through. Standing on z = 0 along Z.
module hose_adapter(d1 = 20, d2 = 15, len1 = 20, len2 = 20, cone = 10, wall = 2) {
  rotate_extrude() polygon([
    [d1 / 2 - wall, 0], [d1 / 2, 0], [d1 / 2, len1], [d2 / 2, len1 + cone], [d2 / 2, len1 + cone + len2],
    [d2 / 2 - wall, len1 + cone + len2], [d2 / 2 - wall, len1 + cone], [d1 / 2 - wall, len1]]);
}""",
    "pyramid": """
// pyramid(): a pyramid standing on z = 0, centred, with a rectangular base; top_w > 0 makes a frustum (flat top).
module pyramid(base_w = 25, base_d = 0, h = 25, top_w = 0, top_d = 0) {
  bd = base_d > 0 ? base_d : base_w;
  tw = max(top_w, 0.01);
  td = top_d > 0 ? top_d : (top_w > 0 ? top_w * bd / base_w : 0.01);
  hull() {
    translate([-base_w / 2, -bd / 2, 0]) cube([base_w, bd, 0.01]);
    translate([-tw / 2, -td / 2, h - 0.01]) cube([tw, td, 0.01]);
  }
}""",
    "mount_plate": """
// mount_plate(): a flat plate on z = 0, centred, with rounded corners and a countersunk hole near each corner.
module mount_plate(w = 80, d = 50, t = 4, hole_d = 4.2, inset = 6, r = 4, countersunk = true) {
  difference() {
    translate([-w / 2, -d / 2, 0]) rounded_plate([w, d, t], r);
    for (x = [-w / 2 + inset, w / 2 - inset], y = [-d / 2 + inset, d / 2 - inset]) translate([x, y, 0]) screw_hole(hole_d, t, 0, countersunk);
  }
}""",
}

import re

# Requests that match a ready-made part: the hint goes at the end of the user's message, where a small model
# follows it (a long system prompt alone was ignored in live tests, 2026-11-04).
MATCH = [
    (re.compile(r"\b(hook|hanger)s?\b", re.I), "wall_hook"),
    (re.compile(r"\b(l[- ]?bracket|angle bracket|shelf (bracket|support)|corner bracket|bracket)s?\b", re.I), "l_bracket"),
    (re.compile(r"\b(box|boxes|container|organi[sz]er|tray|case with (a )?lid)\b", re.I), "box"),
    (re.compile(r"\b(phone|tablet|smartphone)\b.*\b(stand|holder|dock)\b|\b(stand|holder|dock)\b.*\b(phone|tablet)\b", re.I), "phone_stand"),
    (re.compile(r"\bcable\b.*\b(clip|holder|clamp)s?\b|\b(clip|clamp)s?\b.*\bcable", re.I), "cable_clip"),
    (re.compile(r"\b(knob|dial|potentiometer cap)s?\b", re.I), "knob"),
    (re.compile(r"\b(hose|pipe|tube|vacuum)\b.*\b(adapter|reducer|connector|coupler)s?\b|"
                r"\b(adapter|reducer|connector|coupler)s?\b.*\b(hose|pipe|tube|vacuum)\b|\breducer\b", re.I), "hose_adapter"),
    (re.compile(r"\b(mount(ing)? plate|base plate|backplate with (four|4) holes)\b", re.I), "mount_plate"),
    (re.compile(r"\b(pyramids?|obelisks?|frustums?)\b", re.I), "pyramid"),
]


# Shapes a model adds around a ready-made part, and the words that would mean the user asked for them.
SHAPES = re.compile(r"\b(cube|cylinder|sphere|polyhedron|square|circle|polygon|linear_extrude|rotate_extrude|hull|"
                    r"minkowski|rounded_plate|rounded_box|chamfer_cube|rod|path_rod|screw_hole|tube|slot)\s*\(")
JUSTIFY = [(re.compile(r"^(cylinder|screw_hole|tube|slot|circle)$"),
            re.compile(r"hole|screw|mount|bolt|magnet|pin|peg|shaft|axle|rod|insert|nail|drain|slot", re.I)),
           (re.compile(r"^(cube|rounded_plate|rounded_box|chamfer_cube|square|polygon|linear_extrude|polyhedron)$"),
            re.compile(r"\bbase\b|plate|stand|block|slab|platform|step|ledge|tab|foot|feet|plinth|pedestal|notch|groove", re.I)),
           (re.compile(r"^(sphere|rod|path_rod|hull|rotate_extrude)$"),
            re.compile(r"round|ball|sphere|knob|handle|dome|bar|arm|loop|ring", re.I))]


def _call_span(script, name):
    """(start, end) of the first `name(...)` call statement including its ';', or None."""
    m = re.search(r"\b" + name + r"\s*\(", script)
    if not m:
        return None
    depth, i = 0, m.end() - 1
    while i < len(script):
        if script[i] == "(":
            depth += 1
        elif script[i] == ")":
            depth -= 1
            if depth == 0:
                j = i + 1
                while j < len(script) and script[j] in " \t":
                    j += 1
                return (m.start(), j + 1 if j < len(script) and script[j] == ";" else i + 1)
        i += 1
    return None


def extras(script, part, message):
    """Shapes the script adds around `part` that the request gives no reason for (e.g. screw holes in a pyramid)."""
    span = _call_span(script, part)
    if not span or re.search(r"\bmodule\s+" + part + r"\b", script):
        return []
    rest = script[:span[0]] + script[span[1]:]
    rest = re.sub(r"//[^\n]*|/\*.*?\*/", "", rest, flags=re.S)
    found = sorted({m.group(1) for m in SHAPES.finditer(rest)})
    unjustified = []
    for name in found:
        rule = next((words for kinds, words in JUSTIFY if kinds.match(name)), None)
        if not (rule and rule.search(message)):
            unjustified.append(name)
    return unjustified if len(unjustified) == len(found) else []   # all unasked: trim; some asked: leave it


def strip_to_part(script, part):
    """The top-level parameter lines and the one part call: the ready-made part as the user asked for it."""
    span = _call_span(script, part)
    if not span:
        return None
    keep, depth = [], 0
    for line in script.splitlines():
        code = re.sub(r"//.*", "", line)
        if depth == 0 and re.match(r"\s*\$?[A-Za-z_]\w*\s*=\s*[^;{}]+;\s*$", code):
            keep.append(line.rstrip())
        depth += code.count("{") - code.count("}")
    call = re.sub(r"\s+", " ", script[span[0]:span[1]]).strip()
    return "\n".join(keep + ["", call if call.endswith(";") else call + ";"])


def suggest(message):
    """The ready-made part that fits the request, or None."""
    for rx, name in MATCH:
        if rx.search(message):
            return name
    return None


def hint(name):
    sig = next((line.strip("- ").strip() for line in DOC.splitlines() if line.strip().startswith("- " + name + "(")), name + "()")
    return (f"\n\n(Tsubasa note: this matches the ready-made part {name}(). Start from it: the parameter lines with my "
            f"sizes, then one call {sig.split(':')[0]} with those parameters as named arguments. The part already "
            "has its holes, rounding and strength features, so usually that call is the whole model; add or cut "
            "extra features with union()/difference() only if I asked for something it does not have. Do not redraw "
            "it from cubes and cylinders.)")


# Which building blocks each part uses (they are appended before it).
NEEDS = {"wall_hook": ["rounded_plate", "path_rod", "screw_hole"], "l_bracket": ["screw_hole"],
         "box": ["rounded_plate"], "phone_stand": [], "cable_clip": ["screw_hole"], "knob": [],
         "hose_adapter": [], "mount_plate": ["rounded_plate", "screw_hole"], "pyramid": []}

DOC = """Ready-made parts (tested, printable; USE ONE when the request matches, with the user's sizes as arguments,
and add or cut extra features around it with union() / difference()). All are drawn as used:
- wall_hook(plate_w = 40, plate_h = 60, plate_t = 5, arm_len = 45, tip_up = 15, arm_d = 10, arm_z = 0, screws = 2,
  screw_d = 4, countersunk = true): towel/coat hook, complete with its countersunk screw holes and a strut under
  the arm. arm_len = reach from the wall; arm_z = arm height (0 = auto).
- l_bracket(wall_leg = 40, shelf_leg = 40, width = 20, thick = 4, hole_d = 4.2, gussets = true): shelf/angle bracket.
- box(w = 60, d = 40, h = 30, wall = 2, floor = 2, r = 3, lid = true, lid_t = 2, lip = 4, clearance = 0.3):
  open box (outside sizes) plus a push-fit lid printed next to it.
- phone_stand(width = 70, angle = 65, slot = 12, lip_h = 10, rest_len = 90, depth = 90, thick = 5, cable_slot = true):
  desk stand; slot = phone thickness with case.
- cable_clip(cable_d = 6, width = 8, wall = 2, screw_d = 3.5, count = 1): snap-in clip(s) that screw down.
- knob(d = 30, h = 15, shaft_d = 6, flat = 4.5, depth = 12, ribs = 24): knob for a D-shaft (flat = shaft_d if round).
- hose_adapter(d1 = 20, d2 = 15, len1 = 20, len2 = 20, cone = 10, wall = 2): joins two hose sizes.
- mount_plate(w = 80, d = 50, t = 4, hole_d = 4.2, inset = 6, r = 4, countersunk = true): plate with 4 corner holes.
- pyramid(base_w = 25, base_d = 0, h = 25, top_w = 0, top_d = 0): pyramid on a rectangular base (base_d = 0 means
  square); top_w > 0 gives a frustum with a flat top.
Other basic solids are plain calls (write them directly, no module needed):
  cylinder(h = 30, r1 = 10, r2 = 0);                           // cone
  cylinder(h = 20, r = 8, $fn = 6);                            // hexagonal prism
  rotate([90, 0, 90]) linear_extrude(height = 20) polygon([[0, 0], [40, 0], [0, 15]]);   // wedge / ramp
  intersection() { sphere(r = 15); translate([-15, -15, 0]) cube(30); }                   // dome
Example: a 50 mm wide towel hook reaching 60 mm:
  width = 50; // Plate width [30:100]
  reach = 60; // Reach from the wall [30:120]
  wall_hook(plate_w = width, plate_h = 70, arm_len = reach, tip_up = 15);"""
