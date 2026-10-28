# Physical run — confirmed on the machine

This is the only evidence in the project that comes from a real print, not from a
file. It matters because every other check can be satisfied by a toolpath that
would still fail on hardware.

## The file

```
name : 5 (2).gcode
bytes: 414,726
md5  : e5cd7abb4cc5af4c6c4f93c281ddfdb6
note : byte-identical to 5 (1).gcode (same md5), so it is one export kept twice
```

Published by ZCCAD, printed successfully on the Taesin / DongGuan ZhenCai letter
printer.

## What the file contains

| Property | Value |
|---|---|
| Layer height | 0.30 mm |
| Total height | 15.00 mm |
| Printed layers | 49 (one layer height is skipped, see below) |
| Part footprint | 100.07 x 150.00 mm |
| Tools used | **2** — `T1` and `T0` |
| Tool change | at z = 5.10 mm (layer 17) |

Tool bands, measured from the extruding moves only (header purge dances are
excluded):

| Tool | Z range | Height | Layers |
|---|---|---|---|
| `T1` | 0.30 .. 5.10 | 4.80 mm | 17 |
| `T0` | 5.10 .. 15.00 | 9.90 mm | 33 |

17 + 33 - 1 = 49, because layer 5.10 prints with both tools as the transition.

## Filament mapping

The operator loaded three spools in this order:

```
slot 1 = transparent
slot 2 = white
slot 3 = transparent
```

Cross-referencing that order with the tool bands and with the printed result
gives a consistent mapping on two independent lines of evidence:

| UI slot | G-code tool | Filament | Printed band |
|---|---|---|---|
| 1 | `T0` | transparent | top 9.90 mm |
| 2 | `T1` | white | bottom 4.80 mm |
| 3 | `T2` | transparent | unused in this job |

Why this is not a guess:

1. ZCCAD writes `T(n-1)` for UI extruder `n`, so UI 1 -> `T0` and UI 2 -> `T1`.
2. The file prints `T1` first (bottom) and `T0` second (top). The photos show a
   pale opaque band occupying roughly the bottom third and a translucent band
   above it. 4.80 / 15.00 = 32%, which is the bottom third.
3. Slot 3 is loaded but never referenced, which is why only two tools appear.

**Confirm the two-row mapping above before relying on it.** A photograph can
distinguish "pale" from "translucent", not "transparent" from "frosted white".

## Consequences for this project

Settled:

- The dialect runs on the machine. Header, `;extruder switch`, `;calculatePreSide`,
  `;start printf`, footer, `T` commands — all accepted.
- Two tools in one job works, and the colour change happens exactly on a layer
  boundary.
- Colour zones are **heights in millimetres**, quantised to whole layers. 5.10 mm
  is exactly 17 x 0.30.
- The pre-side frame is printed on layer 0 and is wider than the part
  (145 mm vs 100 mm at z = 0.30), so it must always be checked against the bed.

Reproduced by this engine: an equivalent job
(`--height 15 --bands 5.1,9.9 --glue 2,1`) produces the same structure —
`T1` from 0.30 to 5.10, then `T0` from 5.10 to 15.00. The zone arithmetic and the
`UI n -> T(n-1)` mapping are therefore both correct.

Not settled by this run:

- It is a **vendor export**, not a LetterLab export. It proves the machine and the
  dialect; it does not prove that a file written by this engine prints correctly.
- No measurement was taken of wall thickness, pocket fit or dimensional accuracy.
- `T2` remains untested on hardware.

## One vendor quirk worth knowing

The vendor skips a printed layer at the tool change: `Z5.4` appears only in `G0`
travel moves, never in a `G1` extrusion. The sequence goes 5.10 -> 5.70.

Consequence: a ZCCAD colour-change print has a 0.3 mm band with no extrusion at
the boundary. This engine prints every layer, including 5.40, so its tool-change
band is continuous. That is a structural difference, not a defect — but do not
expect byte-level layer-for-layer equality with a vendor file at a colour change.

## Photos

| File | Shows |
|---|---|
| `print_M_side.jpg` | the letter M from the side: bottom band pale, upper band translucent, hollow shell with visible wall |
| `print_on_bed.jpg` | the first layer on the bed, single contour, pre-side frame absent or already removed |
| `print_Z_top.jpg` | the letter Z from above: pocket opening, wall thickness, colour boundary |
