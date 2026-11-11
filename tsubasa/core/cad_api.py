"""3D Print mode: the model designs a printable part as OpenSCAD code, Tsubasa builds the mesh, checks it and saves
STL + SCAD files in the workspace. Dimensions become editable parameters that rebuild the part without the model.

The model thinks first (deep reasoning, a large token budget) because a wrong dimension wastes a print. If the code
does not build, the exact error goes back to the model for up to two repairs.
"""
import base64
import hashlib
import re
import struct
import threading

from core import extract
from core.cad import geometry, helpers, materials, parts, scad
from core.cad.geometry import CadError
from core.modes_api import Stream, _chat, _locked

CODE = re.compile(r"```(?:openscad|scad)?[ \t]*\r?\n(.*?)```", re.S | re.I)
OPEN = re.compile(r"```(?:openscad|scad)[ \t]*\r?\n(.*)$", re.S | re.I)
# The user asked for several parts on purpose (then separate pieces are right).
MULTI = re.compile(r"\b(sets?|pairs?|several|multiple|copies|pieces|parts|separate|\d+\s*(?:x|×|pcs)|"
                   r"(?:two|three|four|five|six|eight|ten|\d+)\s+(?:of\s+them|identical|matching))\b", re.I)


def _split_unclosed(body):
    """An unclosed block runs on into the explanation: (code, prose), split at the first line that is prose
    (**Material**, ## …, 1. …, "Material: PLA …", or a plain sentence)."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        t = line.strip()
        if t and not t.startswith(("//", "/*", "*/")) and (
                re.match(r"(\*\*|#{1,6}\s|\d+\.\s|[-•]\s)", t)
                or (re.match(r"[A-Z][A-Za-z /()-]{2,40}:\s", t) and ";" not in t)
                or (len(t.split()) >= 7 and not re.search(r"[;{}()=\[\]]", t))):
            return "\n".join(lines[:i]).strip(), "\n".join(lines[i:]).strip()
    return body.strip(), ""


def code_of(answer, last=False):
    """The model's OpenSCAD: the first (or last) closed code block, or an openscad block the model never closed."""
    blocks = [b.strip() for b in CODE.findall(answer) if b.strip()]
    if blocks:
        return blocks[-1] if last else blocks[0]
    m = OPEN.search(answer)
    return (_split_unclosed(m.group(1))[0] or None) if m else None


def prose_of(answer):
    """The explanation without any code: closed blocks removed, an unclosed block's code removed but the text
    after it kept, stray fence lines dropped."""
    text = CODE.sub("", answer)
    m = OPEN.search(text)
    if m:
        text = text[:m.start()] + "\n" + _split_unclosed(m.group(1))[1]
    lines = [ln for ln in text.splitlines() if not re.fullmatch(r"\s*(`{3,}\w*|openscad|scad)\s*", ln, re.I)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


MAX_TRIS_VIEW = 120_000

RULES = """You are {name} in 3D Print mode: an expert product designer and 3D-printing engineer. You design parts that
print well, as OpenSCAD code. Think it through before you write anything: list every feature with its exact size and
position, check that every feature touches the one it attaches to, check each number against what the user asked,
then write clean code. All reasoning belongs in your thinking, never in code comments.

How to write the model:
- Units are millimetres. Model the part AS IT IS USED, in real-world directions: X = left-right, Y = front-back
  (away from a wall), Z = up. Something on a wall has its back on the wall plane y = 0 and sticks out towards +Y.
  Example: a towel hook has its back plate from y = 0 to y = 5, standing in X (width) and Z (height); the arm
  starts on the plate's front face and goes out in +Y; "the tip turns up" means +Z. Tsubasa then lays the finished
  part flat for printing by itself (largest flat face on the bed), so do not rotate it for the printer.
- Start with the parameters the user may want to change, one per line: name = value; // Label [min:max]
  Every size the user gave must be a parameter with exactly the user's value. If a size is not given, choose a
  sensible one and say so in the answer. Then derive everything else from the parameters.
- Design only what was asked. Do not add holes, mounts, text or decorations the user did not ask for; if an extra
  would help, suggest it in words in the answer instead.
- Comments are short labels (a few words). No questions, no "wait", no alternatives inside the code.
- OpenSCAD syntax: sin, cos and tan take DEGREES. A function is one expression (function half(x) = x / 2;),
  never braces with return. Modules hold shapes: module name(args) {{ ... }}. Variables are set once per scope.
- Use only: cube, sphere, cylinder, polyhedron, square, circle, polygon, linear_extrude, rotate_extrude, translate,
  rotate, scale, mirror, hull, union, difference, intersection, for, if, let, modules and functions.
  Not available: minkowski, offset, text, import, surface. Round edges with hull() of cylinders or spheres.

{helpers}

- Set $fn = 48 for round features ($fn = 96 only for large, visible curves).
- When subtracting, make cutters 0.5 mm longer on each side (e.g. translate([0, 0, -0.5]) cylinder(h = t + 1, ...))
  so faces never coincide.
- Make it printable: a flat base, walls ≥ 1.2 mm, holes +0.2 mm, 0.2-0.3 mm clearance for fits, overhangs ≤ 45° (or
  45° chamfers), loads along the layers, no parts floating in the air. Everything must be one connected solid unless
  the user asked for several parts (then place them side by side on the bed).

A small example of the style (an L-bracket; your part will be different):
```openscad
leg = 30;        // Leg length [15:100]
width = 20;      // Bracket width [10:60]
thick = 4;       // Wall thickness [2:8]
hole_d = 4.2;    // Screw hole diameter [3:8]
$fn = 48;
difference() {{
  union() {{
    cube([leg, width, thick]);                       // base leg on the bed
    cube([thick, width, leg]);                       // upright leg
    hull() {{                                        // 45° gusset, no overhang
      translate([thick, width / 2 - 2, thick]) cube([0.01, 4, leg / 2]);
      translate([thick, width / 2 - 2, thick]) cube([leg / 2, 4, 0.01]);
    }}
  }}
  translate([leg * 0.65, width / 2, -0.5]) cylinder(h = thick + 1, d = hole_d);
  translate([-0.5, width / 2, leg * 0.65]) rotate([0, 90, 0]) cylinder(h = thick + 1, d = hole_d);
}}
```

If a picture is attached, study it: identify the object, its parts, proportions and how it is used, then model it.
Proportions come from the picture; absolute size from the user's dimensions (or a stated, sensible assumption).

Answer in this order:
1. One ```openscad code block with the complete model.
2. **What I designed**: 2-4 sentences with the key dimensions.
3. **Material**: the best material from the list for this use, and why (one alternative too).
4. **Print settings**: orientation on the bed, layer height, walls, infill, supports yes/no, nozzle and bed temperature.
5. **Check before printing**: 1-3 things to verify (e.g. measure the shaft first).

{materials}

{rules}

Printer: build volume {bed} mm. Material the user prefers: {material}."""


def latest_script(app, cid):
    with app.store.connect() as db:
        rows = db.execute("SELECT content FROM messages WHERE chat=? AND role='assistant' AND state='complete' "
                          "ORDER BY id DESC LIMIT 6", (cid,)).fetchall()
    for r in rows:
        code = code_of(r["content"])
        if code:
            return code
    return None


def build(script, overrides=None, timeout=45):
    """Build in a worker thread with a large stack (deep CSG trees), within a time limit."""
    out = {}
    def work():
        try:
            polys, echo = scad.build(helpers.with_helpers(script), overrides)
            # The designer draws the part as used; it is printed lying on its best face, on the bed at z = 0.
            out["drawn"] = polys
            out["polys"], turned = geometry.lay_flat(polys)
            out["echo"] = echo + (["TURNED: " + turned] if turned else [])
        except CadError as exc:
            out["error"] = str(exc)
        except RecursionError:
            out["error"] = "The model is too deeply nested to build."
        except Exception as exc:  # noqa: BLE001 - any interpreter bug must come back as a message, not a crash
            out["error"] = f"Could not build the model ({type(exc).__name__}: {exc})."
    threading.stack_size(192 * 1024 * 1024)     # Windows refuses 256 MB and more
    t = threading.Thread(target=work, daemon=True)
    t.start()
    threading.stack_size(0)
    t.join(timeout)
    if t.is_alive():
        raise CadError(f"Building the model took longer than {timeout} s; use fewer segments or simpler shapes.")
    if "error" in out:
        raise CadError(out["error"])
    return out["polys"], out["echo"], out["drawn"]


def report(polys, material, infill, bed):
    st = geometry.stats(polys)
    est = materials.estimates(st["volume_mm3"], material, infill, area_mm2=st["area_mm2"])
    warnings = []
    size = st["size"]
    if any(s > b for s, b in zip(size, bed)):
        warnings.append(f"The part ({size[0]:.0f} × {size[1]:.0f} × {size[2]:.0f} mm) is larger than the build volume "
                        f"({bed[0]} × {bed[1]} × {bed[2]} mm): scale it down, split it, or rotate it.")
    if st["overhang_pct"] > 12:
        warnings.append(f"{st['overhang_pct']:.0f} % of the surface overhangs more than 45°: add supports or turn the part.")
    if min(size) < 0.8:
        warnings.append("One dimension is under 0.8 mm, too thin to print reliably.")
    loose = geometry.pieces(polys)
    st["pieces"] = len(loose)
    if len(loose) > 1:
        warnings.append(f"The model is {len(loose)} separate pieces. Fine for a set of parts; otherwise the pieces "
                        "must be joined, or the print falls apart.")
    return st, est, warnings


# Shapes whose bounding box is far from full: a part that fills its box is not one of them.
FILL_HINTS = [(re.compile(r"\b(pyramids?|cones?|conical|spikes?|obelisks?|tetrahedr\w*)\b", re.I), 0.6,
               "a pyramid or cone fills only about 26-33 % of its bounding box"),
              (re.compile(r"\b(spheres?|balls?|globes?|orbs?|spherical)\b", re.I), 0.75,
               "a sphere fills about 52 % of its bounding box")]


# Features an explanation may claim, and the code that would have to be there for the claim to be true.
CLAIMS = [(re.compile(r"\b(holes?|screws?|countersunk|countersink|mounting)\b", re.I),
           re.compile(r"\b(cylinder|screw_hole|slot|tube|wall_hook|l_bracket|mount_plate|cable_clip|knob|hose_adapter)\s*\(")),
          (re.compile(r"\b(rounded|fillets?|filleted|round(ed)? (corners|edges))\b", re.I),
           re.compile(r"\b(rounded_plate|rounded_box|hull|sphere|wall_hook|box|mount_plate|cylinder|path_rod|rod)\s*\(")),
          (re.compile(r"\b(gussets?|ribs?|struts?|braces?)\b", re.I),
           re.compile(r"\b(l_bracket|wall_hook|phone_stand|hull|polygon|cube|linear_extrude)\s*\(")),
          (re.compile(r"\blid\b", re.I), re.compile(r"\b(box|cube|rounded_plate|cylinder)\s*\(")),
          (re.compile(r"\b(text|letter(s|ing)?|engrav\w*|emboss\w*)\b", re.I), re.compile(r"\btext\s*\("))]


def false_claims(text, script):
    """Features the explanation names that the code does not have (seen live: 'screw holes' on a plain pyramid)."""
    code = re.sub(r"//[^\n]*", "", helpers.with_helpers(script).split("// ---- Tsubasa building blocks")[0])
    return [m.group(0) for said, needs in CLAIMS for m in [said.search(text)] if m and not needs.search(code)]


def contents(script):
    """The shapes and ready-made parts the model is made of, as the code calls them."""
    code = re.sub(r"//[^\n]*", "", script)
    names = list(dict.fromkeys(m.group(1) for m in re.finditer(r"\b([a-z_]\w*)\s*\(", code)
                               if m.group(1) in set(scad.OBJECTS) | set(helpers.HELPERS) | set(parts.PARTS)
                               and m.group(1) not in ("translate", "rotate", "scale", "mirror", "color", "echo", "union",
                                                         "difference", "intersection", "render", "group")))
    return ", ".join(names) or "basic shapes"


ADVISOR = """You are a 3D-printing engineer. You explain a finished 3D-printable part to its owner: what it is,
which material suits it and how to print it. Be concrete and short. Never write code.

{materials}

The owner prefers {material} unless another material is clearly better for this use."""


def basic_advice(material, infill, st, turned, made_of):
    """The essentials from the material table, when the model gives no advice at all."""
    m = materials.MATERIALS.get(material, materials.MATERIALS["PLA"])
    resin = m["nozzle"] == "SLA/MSLA"
    temps = "resin printer: wash and UV-cure the part after printing" if resin else \
        f"nozzle {m['nozzle']} °C, bed {m['bed']} °C"
    supports = "yes, about {:.0f} % of the surface overhangs more than 45°".format(st["overhang_pct"]) \
        if st["overhang_pct"] > 12 else "not needed"
    return (f"**What I designed**: {made_of.replace('_', ' ')}, {st['size'][0]:.0f} × {st['size'][1]:.0f} × "
            f"{st['size'][2]:.0f} mm as printed.\n\n**Material**: {material}: {m['good']}. Watch out: {m['weak']}.\n\n"
            f"**Print settings**: {turned.rstrip('.')}; 0.2 mm layers, 3 walls (1.2 mm), {round(infill * 100)} % "
            f"infill, supports {supports}; {temps}.\n\n**Check before printing**: compare the size with the place "
            "the part goes, and watch the first layer stick.")


def measure(polys):
    """What was built, in words a model can compare with the request."""
    st = geometry.stats(polys)
    box = st["size"][0] * st["size"][1] * st["size"][2] or 1.0
    total = sum(geometry._poly_area(p) for p in polys) or 1.0
    dirs = {}
    for p in polys:
        k = (round(p.n[0], 2), round(p.n[1], 2), round(p.n[2], 2))
        dirs[k] = dirs.get(k, 0.0) + geometry._poly_area(p)
    flat = sum(1 for a in dirs.values() if a > total * 0.02)
    return {"size": st["size"], "fill": st["volume_mm3"] / box, "faces": flat, "pieces": len(geometry.pieces(polys))}


def shape_check_note(message, drawn, script, pick=None):
    m = measure(drawn)
    warn = ""
    for rx, limit, fact in FILL_HINTS:
        if rx.search(message) and m["fill"] > limit:
            warn = (f"\nWARNING: it fills {m['fill'] * 100:.0f} % of its box, but {fact}: it is NOT the shape asked "
                    "for. Correct it.")
    keep = f" It uses the ready-made {pick}(); if you change it, keep using that module." if pick and pick in script else ""
    return (f"I built your model and measured it: {m['size'][0]:g} × {m['size'][1]:g} × {m['size'][2]:g} mm, it fills "
            f"{m['fill'] * 100:.0f} % of its bounding box (a box is 100 %, a cylinder 79 %, a sphere 52 %, a pyramid "
            f"33 %, a cone 26 %), it has about {m['faces']} distinct flat face directions (a box has 6, a square "
            f"pyramid 5) and {m['pieces']} piece(s).{warn}\nThe request was: \"{message.strip()[:600]}\"\n"
            f"Does the model have the shape, the features and the sizes asked for, and nothing the user did not ask "
            f"for (no invented holes or mounts)?{keep} If it does, answer with the "
            "single word OK. If not, send the corrected complete model in one ```openscad block and one sentence "
            "saying what was wrong.")


def mesh_b64(polys):
    floats = geometry.mesh_floats(polys)
    if len(floats) // 9 > MAX_TRIS_VIEW:
        raise CadError(f"The model has more than {MAX_TRIS_VIEW:,} triangles; lower $fn.")
    return base64.b64encode(struct.pack(f"<{len(floats)}f", *floats)).decode()


def save(app, workspace, polys, script, stem):
    root = app.tools.files.root(workspace)
    # Named by the source, so rebuilding the same model (e.g. reopening the chat) reuses its files.
    stem = re.sub(r"[^\w-]+", "-", stem.lower()).strip("-")[:40] or "design"
    tag = hashlib.sha1(script.encode("utf-8")).hexdigest()[:8]
    names = {"stl": f"{stem}-{tag}.stl", "scad": f"{stem}-{tag}.scad"}
    (root / names["stl"]).write_bytes(geometry.stl(polys, stem))
    (root / names["scad"]).write_text(helpers.with_helpers(script), encoding="utf-8")
    return names


def options(body):
    material = body.get("material") if body.get("material") in materials.MATERIALS else "PLA"
    try:
        infill = min(max(float(body.get("infill", 0.2)), 0.05), 1.0)
    except (TypeError, ValueError):
        infill = 0.2
    bed = body.get("bed")
    if not (isinstance(bed, list) and len(bed) == 3 and all(isinstance(v, (int, float)) and 20 <= v <= 2000 for v in bed)):
        bed = [220, 220, 250]
    return material, infill, bed


def result(app, workspace, polys, script, overrides, material, infill, bed, stem, echo):
    st, est, warnings = report(polys, material, infill, bed)
    st["orientation"] = next((e[8:] for e in echo if e.startswith("TURNED: ")), "As designed.")
    warnings += [e[9:] for e in echo if e.startswith("SKIPPED: ")]
    if any("MULTIPART" in e for e in echo):      # a set on purpose (a box and its lid, several clips)
        warnings = [w for w in warnings if "separate pieces" not in w]
    echo = [e for e in echo if not e.startswith(("TURNED: ", "SKIPPED: ")) and "MULTIPART" not in e]
    files = save(app, workspace, polys, script if not overrides else apply_overrides(script, overrides), stem)
    return {"stats": st, "estimate": est, "warnings": warnings, "params": scad.parameters(script),
            "values": overrides or {}, "mesh": mesh_b64(polys), "files": files, "echo": echo[:20]}


def apply_overrides(script, values):
    """The SCAD file with the edited parameter values written in, so it matches the STL."""
    def sub(m):
        name = m.group(1)
        if name not in values:
            return m.group(0)
        v = values[name]
        text = ("true" if v else "false") if isinstance(v, bool) else f"{v:g}"
        return f"{name} = {text};" + (f" // {m.group(3)}" if m.group(3) else "")
    return scad.PARAM.sub(sub, script)


def handle(handler, body):
    app, action = handler.app, body.get("action")
    if action == "materials":
        return handler.reply(200, {"materials": {k: {kk: v[kk] for kk in ("density", "nozzle", "bed", "heat", "price", "difficulty", "good", "weak")}
                                                 for k, v in materials.MATERIALS.items()}})
    if action == "render":
        script, values = body.get("script"), body.get("values") or {}
        if not isinstance(script, str) or not isinstance(values, dict):
            return handler.reply(400, {"error": "Send the model source and parameter values."})
        material, infill, bed = options(body)
        try:
            app.images.workspace(body.get("workspace", "default"))
            clean = {k: v for k, v in values.items() if isinstance(k, str) and isinstance(v, (int, float, bool))}
            polys, echo, _ = build(script, clean)
            return handler.reply(200, result(app, body.get("workspace", "default"), polys, script, clean, material,
                                             infill, bed, body.get("name") or "design", echo))
        except (CadError, ValueError) as exc:
            return handler.reply(400, {"error": str(exc)})
    if action != "design":
        return handler.reply(400, {"error": "Unknown 3D Print action."})
    message, model = body.get("message"), body.get("model")
    try:
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 12000:
            raise ValueError("Describe what to design in 1-12,000 characters.")
        _chat(app, body.get("chat_id"))
        app.client.require_model(model)
    except ValueError as exc:
        return handler.reply(400, {"error": str(exc)})
    if not _locked(handler):
        return
    material, infill, bed = options(body)
    cid, saved, answer, thinking = body["chat_id"], None, "", []
    try:
        with Stream(handler) as s:
            with app.store.connect() as db:
                workspace = db.execute("SELECT workspace FROM chats WHERE id=?", (cid,)).fetchone()[0]
            messages = app.store.context(cid, message.strip())
            settings = app.store.state()["settings"]
            system = RULES.format(name=settings["assistant_name"], materials=materials.prompt_table(), helpers=parts.DOC + "\n\n" + helpers.DOC,
                                  rules=materials.DESIGN_RULES, bed=" × ".join(str(int(v)) for v in bed), material=material)
            system += app.store.instructions(cid)
            current = latest_script(app, cid)
            if current:
                system += ("\n\nThe current design in this chat (change it as the user asks, keep what they did not "
                           "mention, and always send the complete file):\n```openscad\n" + current + "\n```")
            messages[0] = {"role": "system", "content": system}
            # A first design that matches a ready-made part starts from it (the note is not saved in the chat).
            pick = None if current else parts.suggest(message)
            if pick and isinstance(messages[-1].get("content"), str):
                messages[-1] = {**messages[-1], "content": messages[-1]["content"] + parts.hint(pick)}
                s.emit("part", pick)
            vision = any(m.get("id") == model and m.get("supports_vision") for m in app.client.models())
            if any(m["role"] == "user" and isinstance(m.get("content"), str) and extract.HINT.search(m["content"]) for m in messages):
                messages, notes = extract.attach(messages, app.tools.files.root(workspace), vision)
                if notes:
                    s.emit("attach_notes", notes)
            saved = app.store.begin(cid, message.strip())
            reasons = any(m.get("id") == model and m.get("supports_reasoning") for m in app.client.models())
            think = body.get("think", True) is not False and (reasons or model.startswith(("qwen3.5", "qwen-liberty3.5")))
            s.emit("status", "Thinking the design through…" if think else "Designing…")
            try:
                # The reasoning shares the token budget with the answer: leave room for both.
                for kind, value in app.client.stream(model, messages, max_tokens=12288 if think else 4096,
                                                     cancelled=s.cancelled, think=think):
                    if kind == "text":
                        answer += value
                        s.emit("text", value)
                    elif kind == "thinking":
                        thinking.append(value)
                        s.emit("thinking", value)
                if s.cancelled.is_set():
                    raise CadError("Stopped.")
                attempts, reviewed, fallback, explain, mark, checked, trims = 0, False, None, "", 0, False, 0

                def redo(note, deep):
                    """Ask the model again with the exact problem; deep = think again (spatial fixes need it)."""
                    nonlocal answer, explain, mark
                    rest = prose_of(answer).strip()
                    if len(rest) > 40:      # keep the explanation: a repair often sends only the code
                        explain = rest
                    fix = messages + [{"role": "assistant", "content": answer}, {"role": "user", "content": note}]
                    answer, mark = "", len(thinking)
                    s.emit("text_reset", {})
                    for kind, value in app.client.stream(model, fix, max_tokens=8192 if deep else 4096,
                                                         cancelled=s.cancelled, think=deep):
                        if kind == "text":
                            answer += value
                            s.emit("text", value)
                        elif kind == "thinking":
                            thinking.append(value)
                            s.emit("thinking", value)
                    if s.cancelled.is_set():
                        raise CadError("Stopped.")

                while True:
                    script = code_of(answer)
                    if not script:
                        # Thinking models sometimes write the finished code while thinking and then only describe
                        # it: use the last complete block from this round's thinking (and keep it in the answer).
                        script = code_of("".join(thinking[mark:]), last=True)
                        if script:
                            answer = f"```openscad\n{script}\n```\n\n{answer.strip()}"
                    try:
                        if not script:
                            raise CadError("The answer had no OpenSCAD code block.")
                        s.emit("status", "Building the 3D model…")
                        polys, echo, drawn = build(script)
                    except CadError as exc:
                        attempts += 1
                        if attempts > 2 or s.cancelled.is_set():
                            if fallback:        # the review's version broke: keep the version that built
                                answer, script, polys, echo = fallback
                                break
                            raise CadError(f"{exc} Ask again, or say what to change.") from exc
                        s.emit("status", f"The model did not build ({exc}). Fixing it…")
                        s.emit("repair", {"error": str(exc), "attempt": attempts, "kind": "build"})
                        simpler = (f"\nThe simplest correct model is the parameter lines and one {pick}(...) call with named "
                                   f"arguments: {pick}() already has its holes and strength features. Remove anything "
                                   "you invented around it." if pick else "")
                        redo(f"Building that OpenSCAD code failed: {exc}{simpler}\nSend the corrected complete model in "
                             "one ```openscad block (close it with ```), then the same sections as before. Use only the "
                             "supported functions and the ready-made modules.", False)
                        continue
                    # Review: a part that falls apart is the commonest mistake of a small model. One deep retry.
                    multi = MULTI.search(message) or any("MULTIPART" in e for e in echo)
                    loose = [] if reviewed or multi else geometry.pieces(drawn)
                    if len(loose) > 1:
                        reviewed, fallback = True, (answer, script, polys, echo)
                        where = "; ".join(f"piece {i + 1}: x {p['min'][0]:g} to {p['max'][0]:g}, y {p['min'][1]:g} to "
                                          f"{p['max'][1]:g}, z {p['min'][2]:g} to {p['max'][2]:g} mm"
                                          for i, p in enumerate(loose[:6]))
                        s.emit("status", f"The model is {len(loose)} separate pieces. Joining them…")
                        s.emit("repair", {"error": f"{len(loose)} separate pieces that do not touch", "attempt": 1,
                                          "kind": "review"})
                        redo(f"I built your model and measured it. It is {len(loose)} separate pieces that do not touch, "
                             f"so it would fall apart: {where}.\nCheck every feature's position against the request "
                             "(X left-right, Y out from the wall, Z up; where each feature attaches) "
                             "and make everything one connected solid: parts that join must overlap by at least 1 mm. "
                             "Send the corrected complete model in one ```openscad block, then the same sections.", think)
                        attempts = 0
                        continue
                    # A ready-made part with shapes around it that nobody asked for (screw holes in a pyramid): keep
                    # the user's sizes and the part, drop the extras; the advice is then written for the clean part.
                    added = parts.extras(script, pick, message) if pick and trims < 2 else []
                    clean = parts.strip_to_part(script, pick) if added else None
                    if clean:
                        trims += 1
                        s.emit("repair", {"error": ", ".join(added), "attempt": trims, "kind": "trim"})
                        fallback, attempts, mark, explain = (answer, script, polys, echo), 0, len(thinking), ""
                        answer = f"```openscad\n{clean}\n```"
                        s.emit("text_reset", {})
                        s.emit("text", answer)
                        continue
                    # Shape check: the model may describe one shape and draw another (a "pyramid" that was a cube).
                    # Tell it what was really built and let it confirm or correct, once.
                    if not checked and not s.cancelled.is_set():
                        checked = True
                        s.emit("status", "Checking the shape against your request…")
                        verdict = ""
                        for kind, value in app.client.stream(model, messages + [
                                {"role": "assistant", "content": answer},
                                {"role": "user", "content": shape_check_note(message, drawn, script, pick)}],
                                max_tokens=1500, cancelled=s.cancelled, think=False):
                            if kind == "text":
                                verdict += value
                        if s.cancelled.is_set():
                            raise CadError("Stopped.")
                        fixed = code_of(verdict)
                        if fixed and fixed.strip() != script.strip():
                            why = next((ln.strip(" *-") for ln in prose_of(verdict).splitlines()
                                        if len(ln.strip()) > 12), "the shape did not match the request")
                            s.emit("repair", {"error": why[:160], "attempt": 1, "kind": "check"})
                            rest = prose_of(answer).strip()
                            if len(rest) > 40:
                                explain = rest
                            fallback, attempts, mark = (answer, script, polys, echo), 0, len(thinking)
                            answer = verdict
                            s.emit("text_reset", {})
                            s.emit("text", verdict)
                            continue
                    break
                # The answer is assembled here, not taken as the model wrote it: the code block is the model that
                # was really built (always closed), then the explanation, checked against that model.
                prose = prose_of(answer)
                if len(prose) < 40 and explain:
                    prose = prose_of(explain)
                wrong = false_claims(prose, script)
                if wrong:
                    # The explanation describes features the part does not have: rewrite it from the real model.
                    s.emit("repair", {"error": ", ".join(wrong), "attempt": 1, "kind": "describe"})
                    prose = ""
                if len(prose) < 40:
                    # No (true) explanation: the material and print advice is half the value, so ask for it once
                    # more as a fresh question grounded in what was built (asked as a continuation of the code
                    # turn, the model repeated the code instead, live 2026-11-05).
                    st0 = geometry.stats(polys)
                    turned = next((e[8:] for e in echo if e.startswith("TURNED: ")), "printed as drawn")
                    facts = (f"{st0['size'][0]:.0f} × {st0['size'][1]:.0f} × {st0['size'][2]:.0f} mm as printed, "
                             f"{st0['volume_mm3'] / 1000:.1f} cm³ of solid, {st0['overhang_pct']:.0f} % overhang beyond 45°, "
                             f"{turned.rstrip('.')}")
                    s.emit("status", "Writing the material and print advice…")
                    s.emit("text_reset", {})
                    s.emit("text", f"```openscad\n{script}\n```\n\n")
                    ask = [{"role": "system", "content": ADVISOR.format(materials=materials.prompt_table(),
                                                                         material=material)},
                           {"role": "user", "content":
                        f"The request was: \"{message.strip()[:600]}\"\nThe finished model builds: {facts}. It is "
                        f"made of exactly: {contents(script)}; describe only what is in it (no holes, rounding or "
                        f"other features it does not have). Its OpenSCAD code:\n{script}\n\nWrite these sections, "
                        "without any code: **What I designed** (2-4 sentences with the key dimensions), **Material** "
                        "(the best material from the list for this use and why, plus one alternative), **Print "
                        "settings** (orientation, layer height, walls, infill, supports, nozzle and bed temperature), "
                        "**Check before printing** (1-3 points)."}]
                    extra = ""
                    for kind, value in app.client.stream(model, ask, max_tokens=900, cancelled=s.cancelled, think=False):
                        if kind == "text":
                            extra += value
                            s.emit("text", value)
                    prose = prose_of(extra)
                    if len(prose) < 40 or false_claims(prose, script):
                        prose = basic_advice(material, infill, st0, turned, contents(script))
                answer = f"```openscad\n{script}\n```\n\n{prose}"
                stem = re.sub(r"\W+", " ", message.strip().split("\n")[0])[:40]
                s.emit("status", "Checking printability…")
                s.emit("cad", {**result(app, workspace, polys, script, None, material, infill, bed, stem, echo),
                               "script": script, "answer": answer})
            except (OSError, RuntimeError) as exc:
                s.emit("error", str(exc) if isinstance(exc, RuntimeError) else "The AI engine is not answering.")
            except CadError as exc:
                s.emit("error", str(exc))
            app.store.finish(saved, answer.strip(), "".join(thinking), "stopped" if s.cancelled.is_set() else "complete")
            saved = None
            s.emit("done", {"cancelled": s.cancelled.is_set(), "model": model})
    finally:
        if saved:
            app.store.finish(saved, answer.strip(), "".join(thinking), "stopped")
        app.operation.release()


def download(handler, query):
    """GET /api/cad-file?workspace=…&name=…: an STL or SCAD file from the workspace, as a download."""
    from urllib.parse import quote
    try:
        w, name = query.get("workspace", ["default"])[0], query.get("name", [""])[0]
        handler.app.images.workspace(w)
        if not re.fullmatch(r"[\w-]{1,80}\.(stl|scad)", name):
            raise ValueError("Unknown file.")
        path = handler.app.tools.files.path(handler.app.tools.files.root(w), name)
        data = path.read_bytes()
    except (ValueError, OSError):
        return handler.reply(404, {"error": "File not found."})
    handler.send_response(200)
    handler.send_header("Content-Type", "model/stl" if name.endswith(".stl") else "text/plain; charset=utf-8")
    handler.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(name))
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
