# 3D printing reference

## Choosing a material (FDM filament)
- **PLA**: easiest to print, stiff, detailed, low warp. Softens at about 55 °C, so it is not for cars, dishwashers or full sun. Nozzle 190-220 °C, bed 50-60 °C. Good for prototypes, decor, indoor holders and organisers.
- **PLA+ / Tough PLA**: less brittle PLA for clips and brackets indoors.
- **PETG**: tough, a little flexible, good layer bonding, resists water and many chemicals, works outdoors for moderate use; food-contact grades exist (the printed surface still traps bacteria). Nozzle 230-250 °C, bed 70-85 °C. Strings: lower the temperature, tune retraction, dry the filament.
- **ABS**: heat resistant (≈95 °C), tough, acetone-smoothable. Needs an enclosure (it warps and cracks) and ventilation (styrene fumes).
- **ASA**: ABS that resists UV and weather; the choice for outdoor and car-exterior parts. Enclosure needed.
- **TPU (95A shore)**: rubber-like; seals, feet, phone cases, vibration dampers. Print slowly (20-30 mm/s), direct drive preferred, little or no retraction.
- **Nylon (PA6/PA12)**: toughest common filament; gears, hinges, wear parts, living hinges. Dry it (it absorbs water within hours), enclosure, glue or a PEI/garolite bed.
- **Polycarbonate (PC)**: very strong, heat resistant to ≈115 °C, needs 260-300 °C and an enclosure.
- **Carbon-fibre filled (PLA-CF, PETG-CF, PA-CF)**: stiff, matte, accurate; abrasive, so use a hardened-steel nozzle.
- **Resin (MSLA/SLA)**: finest detail and smoothest surface; standard resin is brittle, tough/ABS-like resin less so. Wash in IPA, UV cure, wear gloves (uncured resin irritates skin).

Quick picks: an indoor organiser or holder → PLA. A clip or hook that flexes → PETG or PLA+. Outdoors or in a car → ASA (or PETG in the shade). Hot water or a dishwasher → PP or PC, not PLA. Flexible parts → TPU. Gears and hinges → nylon or PETG. A miniature → resin.

## Design rules (0.4 mm nozzle, 0.2 mm layers)
- Wall thickness: at least 1.2 mm (3 lines); 0.8 mm is the practical minimum. Top and bottom skins at least 0.8 mm (4 layers).
- Holes print smaller: add 0.1-0.2 mm to the diameter. Horizontal holes print slightly oval: make them teardrop-shaped or ream them.
- Fits: sliding or moving fit 0.2-0.3 mm clearance per side; press fit 0.05-0.1 mm; snap fits: about 1 mm undercut on PETG or nylon.
- Overhangs: up to 45° from vertical without support. Prefer 45° chamfers to fillets on downward-facing edges. Bridges up to about 30 mm.
- Strength: parts are 30-60 % weaker across layers than along them. Orient so bending and tension run along the layers (print hooks, brackets and clips on their side).
- First layer: a flat face down; use a brim for small or tall parts; avoid sharp corners on large flat parts (they lift).
- Screws and threads: heat-set brass inserts give the strongest threads (hole = insert diameter minus 0.1 mm, about 1.5 × the insert length deep). For self-tapping screws, use a hole of screw diameter minus 0.5 mm. Printed threads work from M8 upwards.
- Text and fine details: at least 0.6 mm wide and 0.4 mm raised or sunk.
- Infill: 15-25 % for most parts, 40 %+ for mechanical parts. More walls (3-4) add more strength than more infill.
- Tolerances: typical printers are accurate to ±0.1-0.2 mm. Print a test piece for important fits.

## Slicer settings starting points
- Layer height: 0.2 mm standard; 0.12 mm for detail; 0.28 mm for speed.
- Walls 3, top 5, bottom 4 layers; infill gyroid or grid at 20 %.
- Supports: tree supports for organic shapes, normal for flat overhangs; support interface for clean surfaces.
- Cooling: 100 % fan for PLA, 30-50 % for PETG, 0-20 % for ABS and ASA.

## Estimating
- Weight = printed volume (cm³) × density (PLA 1.24, PETG 1.27, ABS 1.04, ASA 1.07, TPU 1.21, nylon 1.10, PC 1.20 g/cm³).
- Time: about 10-15 cm³ of plastic per hour on a standard printer at 0.2 mm layers (faster on modern high-speed printers).
- Cost: grams × price per gram (PLA ≈ €0.02/g).
