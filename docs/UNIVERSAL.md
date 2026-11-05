# Universal family — standard Marlin G-code for generic FDM printers

`--family universal` emits the SAME letter geometry the vendor pipeline handles,
in dialect any modern printer understands: homing, absolute XYZ, relative
extrusion (`M83`), physical retraction, fan ramping and `;LAYER:` markers.  The
prime target is the Bambu Lab class machine, but nothing in the output is
Bambu-specific.

One file, one family.  A universal file never contains vendor-dialect moves
(`;extruder switch`, cubic `E85` purges, the `Z0.4`→`Z0.3`→`Z0.9` approach
trick), and a zccad file never contains `M83` retraction.  The switch is a
hard boundary; mixing is checked by the selftest (T13).

## Command

```bash
python .qoder/skills/letterlab-skill/scripts/letterlab.py generate \
  --dxf LETTER.dxf --out A_40mm_universal.gcode \
  --family universal --profile bambu-generic \
  --height 40 --layer 0.3 --width 1.2 --passes 2 --spacing 0.8 \
  --fit-bed --infill 20 --show-params \
  --preview A_40mm_universal_3d.png \
  --html A_40mm_universal.html
```

The companion `--html` path writes the interactive WebGL viewer (single
self-contained file: orbit, zoom, layer slider + play simulation, tool toggles,
bed outline, HUD stats).  It works for both families because the viewer parses
G-code, not the generator.

## Machine profiles (`work/lettergcode/machines.py`)

| profile | bed | hotspot | travel | work | retract | z-hop | |
|---|---|---|---|---|---|---|---|
| `marlin-generic` | 300×300 | 215/220 °C | 9000 | 3000 | 1.0 @2400 | 0 | Marlin markers |
| `bambu-generic`  | 256×256 | 215/220 °C | 15000 | 3000 | 0.8 @5400 | 0.4 | `;LAYER_CHANGE` |
| `x1c`            | 256×256 | 215/220 °C | 15000 | 3000 | 0.8 @5400 | 0.4 | `;LAYER_CHANGE` |

Layer height defaults to the vendor INI value (0.3 mm) and is what the three
successful reference prints on the letter printer used.  `--bed X,Y` overrides
the bed size; `--fit-bed` shrinks a part that would not fit (it never grows);
`--scale` multiplies the DXF coordinates; the job is centred on the bed.

### Where the numbers come from

Three vendor exports that printed cleanly on the letter machine were torn down
(see [`work/templates/REFERENCE_GCODE_NOTES.md`](../work/templates/REFERENCE_GCODE_NOTES.md)):
layer 0.3 mm everywhere, hotend 220 °C on the letter machine (`"5"` and
`"arr"`, 230 °C on the 50 mm-tall `"TES IM"`), work speed 3000 mm/min
(50 mm/s) dominant, 1800 mm/min (30 mm/s) on approach or small features.
The universal profiles quote these proven values for the standard paths.

## Extrusion honesty

Every emitted `G1 X.. Y.. E..` in `M83` mode pushes exactly

```
E = path_length * bead_width * layer_height / (pi * filament_radius^2)
```

for that move — `1.2 * 0.3 / (pi * 0.875^2) = 0.14968 mm filament per mm of
path` for the standard bead.  The selftest re-parses the output and compares
the sum of the E words against the sum of the path lengths (T13).  The vendor
dialect's `E` is meaningless in filament mm; do NOT feed a vendor export to the
universal honesty math and do not reuse vendor `e_per_mm` here.

## Colour (multi-tool) handling

The letter geometry's colour bands (glue indices, e.g. `--glue 1,2,1`) map to
tool numbers `T0..Tn` by the same mapping the vendor uses.  `--no-multitool`
keeps one nozzle: the bands collapse into `T0` paths.  A universal template
without an explicit `glue` key inherits the vendor 2-band plan, so
single-colour templates must pin `glue: [1]`.

## Contract

- CLI keeps `center_bed=True` (there is no flag to uncentre); `--scale 0`
  without `--fit-bed` keeps the DXF geometry unshrunk.
- The universal output stays UNVERIFIED against vendor dialect gates by design;
  it is checked by T13 (structure), T15 (viewer), the 3D preview and optionally
  the per-layer audit (`letterlab.py preview --gcode ... --stats`, or
  `labcheck.py FILE.gcode`).
- zccad pipeline untouched: selftest T6/T7 still gate it when a vendor export
  is supplied.
