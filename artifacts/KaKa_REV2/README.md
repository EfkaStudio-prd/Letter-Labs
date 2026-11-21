# Ka Ka / REV2 — review package

Published for technician review on 2026-11-21.

## What is here

- `REV2/` — final parameter revision derived from the user's own physically
  printed parts and the three-page validation PDF:
  - `ADve_ZCCAD_REV2.gcode` — generated from `ADve tes.dxf`
  - `letter_settings_rev2.json` — reusable parameter set for the next template
  - `ZCCAD_VALIDATION.md` — native ZCCAD checks, differences and limits
  - `REV2/*.png` — ZCCAD import, file-output parameters, in-fill spacing
  - `generate_adve_rev2.py` — deterministic generator
  - `ZCCAD_native_ADve.gcode` — native export (header/footer only, see report)
- `01_KaKa_ZCCAD_wall_2mm_brim.gcode` — REV1 output, kept for comparison
- `generate_kaka_gcode.py`, `README_REV1.txt` — REV1 generator and notes

## Status

REV2 passed mechanical checks: 84 layers, 0 motion-rule violations, replayed
E/mm 0.134286 matching the printed reference. Native ZCCAD confirmed the DXF
import, 0.30 mm layer height and 1.20 mm in-fill spacing. The native `get path`
returned 0.000 m extrusion in the open session, so native and generated
toolpaths were **not** compared move-by-move.

Nothing here has been sent to a printer. The ZCCAD G-code is a dialect replica,
not a native export; physical print of REV2 is not verified.
