# Production checklist

Print this, or keep it open, and tick it every time. The order matters: a failure
early makes every later number meaningless.

---

## A. Before generating

| # | Check | How |
|---|---|---|
| A1 | DXF exported as AutoCAD **2004**, units **millimetres**, text as **curves** | source CAD export dialog |
| A2 | Contours are closed and real, no dimension marks or dots | `dxfprobe.py FILE.dxf` — read *closed* / *open* / *noise* |
| A3 | Layout drawing's bed rectangle will not print | if present, pass `--max-area 100000` |
| A4 | Part fits the bed | `dxfprobe.py` reports size and bed fit |
| A5 | Height, layer, wall width chosen | `<40 cm` -> wall 1.2 mm; `>40 cm` -> 1.3 mm; layer 0.3 mm |
| A6 | Colour zones are **heights in mm**, and they cover the full height | `--bands` last zone absorbs the remainder |
| A7 | Acrylic thickness measured, not assumed | pocket depth = that number |
| A8 | **T0/T1 physical colour known** | if not, run single colour only |

---

## B. Before trusting the file

| # | Check | How | Must show |
|---|---|---|---|
| B1 | Engine sound | `selftest.py` | `ALL CHECKS PASS` |
| B2 | Dialect matches vendor | `validate_gcode.py REF.gcode NEW.gcode` | `ALL GATES PASS` |
| B3 | Geometry matches vendor per layer | `labcheck.py REF.gcode NEW.gcode` | no unexplained ring diff |
| B4 | Pocket depth is real | `labcheck.py NEW.gcode`, watch the ring profile | count collapses to baseline at `height - acrylic` |
| B5 | Shape is correct | look at the PNG | the actual letters, right colour bands |
| B6 | Layer count | report line `layers` | `round(height / 0.3)` |
| B7 | Time and filament are sensible | report lines `est_print_time_min`, `filament_total_m` | matches expectation |

If B2 or B3 had no reference file, the output is **UNVERIFIED** — say so out
loud, do not present it as ready.

---

## C. Before pressing start on the machine

| # | Check |
|---|---|
| C1 | Nozzles clean, 1 and 2 both heated to the same temperature |
| C2 | Bed levelled, and the placement matches the physical bed, not just the screen |
| C3 | Filament diameter is 1.75 mm, and the spool has more than the reported metres |
| C4 | The pre-side frame fits on the bed — it extends `around offset` outside the outline |
| C5 | You are printing the **smoke test first** if this is a new shape or a new machine |
| C6 | The file on the USB drive is the one that passed B1-B7, match the SHA-256 |

---

## D. First-print verification, in this order

| # | Print | Why | Expected |
|---|---|---|---|
| D1 | `TEST4_BALI_10mm_smoke.gcode` | proves the machine accepts this dialect: header, pre-side frame, layer timing | 34 layers, 71 min, 34 m |
| D2 | `TEST2_BALI_40mm.gcode` | the real job | 134 layers, 336 min, 162 m |
| D3 | `TEST3_WELCOME_30mm.gcode` | colour switch only after C1/A8 are settled | 100 layers, 2 tools |

---

## E. After the first print, measure and record

| # | Check | What to write down |
|---|---|---|
| E1 | Wall thickness at mid-height | actual mm vs `--width` |
| E2 | Total height | actual mm vs `--height` |
| E3 | Pocket depth | does a 3 mm sheet sit flush, no rattle, no force |
| E4 | Layer adhesion | any gap between the two wall passes -> reduce `--spacing` |
| E5 | Stringing | reduce travel lift or drop temperature 5 C |
| E6 | Corners lifting | this is a bed adhesion problem; do not "fix" it by changing the model |

Write the numbers into a test log. A single measured print is worth more than any
number of simulated ones.

---

## F. Hard stops

Do not ship a file if any of these is true:

- No vendor reference was compared **and** nobody has printed this shape before.
- A two-colour job with unknown nozzle-to-filament mapping.
- A bevel or incline letter — this generator only does straight edges.
- `labcheck.py` shows a ring-count difference that has not been explained.
- The SHA-256 of the file on the machine differs from the validated one.
