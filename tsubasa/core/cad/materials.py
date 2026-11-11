"""3D printing materials: what each is good for, how to print it, and its density for weight estimates.

Values are typical datasheet ranges for common brands (temperatures in °C, density in g/cm³, price in €/kg for
1 kg spools in 2025-2026). They feed the model's advice and the weight, cost and time estimates in 3D Print mode.
"""

MATERIALS = {
    "PLA": dict(density=1.24, nozzle="190-220", bed="50-60", heat=55, price=20, difficulty="easy",
                good="easiest to print, stiff, sharp detail, low warping; decorative parts, prototypes, indoor fixtures",
                weak="softens around 55 °C (car interiors, sun), brittle under impact, poor outdoors long-term"),
    "PLA+ / Tough PLA": dict(density=1.23, nozzle="200-230", bed="50-65", heat=58, price=22, difficulty="easy",
                good="like PLA but less brittle; clips, brackets, everyday functional parts indoors",
                weak="still softens near 60 °C"),
    "PETG": dict(density=1.27, nozzle="230-250", bed="70-85", heat=75, price=22, difficulty="easy-medium",
                 good="tough, slightly flexible, good layer adhesion, water and chemical resistant, food-contact grades exist; outdoor-ish and mechanical parts",
                 weak="strings, sticks too well to bare PEI (use glue stick as release), less stiff than PLA"),
    "ABS": dict(density=1.04, nozzle="230-260", bed="95-110", heat=95, price=22, difficulty="medium-hard",
                good="heat resistant, tough, can be acetone-smoothed; car parts, enclosures",
                weak="warps and cracks without an enclosure, fumes (ventilate), not UV stable"),
    "ASA": dict(density=1.07, nozzle="240-260", bed="90-110", heat=95, price=27, difficulty="medium-hard",
                good="like ABS but UV and weather resistant; outdoor parts, garden, car exterior",
                weak="needs an enclosure, fumes"),
    "TPU 95A": dict(density=1.21, nozzle="220-240", bed="40-60", heat=80, price=30, difficulty="medium",
                    good="rubber-like and flexible; phone cases, seals, feet, bumpers, gaskets",
                    weak="print slowly (20-30 mm/s), direct-drive extruder preferred, hard to bridge"),
    "Nylon (PA6/PA12)": dict(density=1.10, nozzle="250-280", bed="70-100", heat=120, price=45, difficulty="hard",
                             good="very tough, wear resistant, low friction; gears, hinges, living hinges, clips",
                             weak="absorbs moisture (dry before printing), warps, needs enclosure"),
    "PC (polycarbonate)": dict(density=1.20, nozzle="260-300", bed="100-120", heat=115, price=40, difficulty="hard",
                               good="very strong and heat resistant, clear grades; demanding mechanical parts",
                               weak="high temperatures, enclosure, strong warping"),
    "PLA-CF / PETG-CF": dict(density=1.30, nozzle="220-260", bed="60-80", heat=65, price=35, difficulty="medium",
                             good="stiff, matte, dimensionally accurate; drone frames, jigs, brackets",
                             weak="abrasive: needs a hardened-steel nozzle; more brittle than unfilled"),
    "Resin (standard)": dict(density=1.15, nozzle="SLA/MSLA", bed="-", heat=50, price=35, difficulty="medium",
                             good="finest detail and smooth surfaces; miniatures, jewellery masters, small precise parts",
                             weak="brittle, needs washing and UV curing, uncured resin is toxic (gloves, ventilation)"),
    "Resin (tough/ABS-like)": dict(density=1.12, nozzle="SLA/MSLA", bed="-", heat=60, price=45, difficulty="medium",
                                   good="detailed and less brittle than standard resin; snap fits, small functional parts",
                                   weak="same handling as standard resin"),
}

DESIGN_RULES = """FDM design rules (0.4 mm nozzle):
- Walls at least 1.2 mm (3 lines) for strength, 0.8 mm minimum; tops/bottoms at least 0.8 mm.
- Clearance between moving or fitted parts: 0.2-0.3 mm per side; press fit 0.1 mm; holes print about 0.1-0.2 mm small (enlarge them).
- Overhangs up to 45° print without support; chamfer (45°) instead of rounding the bottom edges; bridges up to about 30 mm.
- Parts are weakest between layers: orient so loads run along the layers (e.g. print hooks and brackets on their side).
- Flat side down for bed adhesion; avoid tall thin towers; add a brim for small footprints.
- Screws: use heat-set inserts (hole = insert outer diameter minus 0.1 mm) or self-tapping holes (screw diameter minus 0.5 mm).
- Text and details: at least 0.6 mm wide and 0.4 mm deep/high.
- Infill 15-25 % for most parts, 40-100 % for strong mechanical parts; more walls add more strength than more infill.
- Typical print speed for planning: about 10-15 cm³ of plastic per hour (0.2 mm layers)."""


def prompt_table():
    lines = []
    for name, m in MATERIALS.items():
        lines.append(f"- {name}: nozzle {m['nozzle']} °C, bed {m['bed']} °C, softens ≈{m['heat']} °C, {m['difficulty']}; "
                     f"good: {m['good']}; watch out: {m['weak']}.")
    return "Materials:\n" + "\n".join(lines)


def estimates(volume_mm3, material="PLA", infill=0.2, walls_mm=1.2, area_mm2=None):
    """Rough plastic use: shells (area × wall thickness) plus infill of the rest, capped at a solid part."""
    m = MATERIALS.get(material) or MATERIALS["PLA"]
    solid = volume_mm3 / 1000.0                           # cm³
    shell = min(solid, (area_mm2 or 0) * walls_mm / 1000.0)
    used = min(solid, shell + max(solid - shell, 0) * infill)
    grams = used * m["density"]
    return {"material": material, "solid_cm3": round(solid, 2), "printed_cm3": round(used, 2), "grams": round(grams, 1),
            "cost_eur": round(grams / 1000 * m["price"], 2), "hours": round(used / 12.0, 2), "infill": infill}
