# ZCCAD / Taesin G-code dialect

Transcribed from vendor exports (`A_SAMPLE_50mm.gcode`, `S528/temp.gcode`) and
confirmed against the IL of `OutPutG.dll::OutKF` (`writeGcodeHead`,
`writeGcodeTear`, `writeGcode_G00`, `thichnessProcess`, `calculatePreSide`,
`updateCoor`). Every line shape below appears literally in a vendor file.

## File skeleton

```
;This G_Code provided by DongGuan ZhenCai Lmt
;G code start
<heat each tool that will run>
G21 G90 G82 G28
G1 Z15 F1500
G92 E0
<purge dance, only when 2+ tools>
M117 Printing...
M106 S255
;extruder switch            <- initial positioning + first tool select
;calculatePreSide start     <- prevent-curl frame, first layer only
;start printf
...contours, bottom layer to top...
;G code end
<park, unlock, cool down>
;End of Gcode
```

## Header

One heat block per **configured** tool. Every export in the 13-file corpus is a 2-
or 3-tool job, so those heat 2 or 3 nozzles:

```
M104 S220 T0
M109 S220 T0
M104 S220 T1
M109 S220 T1
G21
G90
G82
G28
G1 Z15 F1500
G92 E0
```

`G82` = absolute extrusion. The purge dance that follows primes both channels by
`dbDisColorBack` (85 mm at a two-tool setup):

```
T0 / G1 E-85 F1200 / G92 E0
T1 / G1 E85 F750    / G92 E0
T1 / G1 E-85 F1200  / G92 E0
T0 / G1 E85 F750    / G92 E0
T0
```

`F1200` is `iSpeedColorSwitch` (retract side), `F750` is the fixed prime side.

## Initial positioning

```
;extruder switch
G92 E0
G91
G0 X5 Y5 F18000
G0 F18000 Z0
G90
G1 F1200 E-42.5        <- half of dbDisColorBack
M104 S220 T0
T0
G92 E0
G90
```

## Contour emission

Two shapes, and which one is used matters for speed. The **first contour of a
block** primes from a standstill:

```
;start printf
G0 F18000 X{x} Y{y}
G0 F18000 Z{h+0.3}
G0 F18000 X{x} Y{y}
G0 F18000 Z{h}
G1 F{speed} E{acc+0.1}
G1 F{speed} X{x} Y{y}
G1 X.. Y.. E..          <- one line per vertex, E is a running absolute counter
```

Every **later contour in the same block** uses the recover move instead:

```
G0 F18000 Z{h+0.3}
G0 F18000 X{x} Y{y}
G0 F18000 X{x} Y{y} Z{h}
G0 F18000 X{x} Y{y}
G1 F3600 X{x} Y{y} E{acc}
G1 F3600 Z{h} E{acc+0.1}
G1 F{work} X{x} Y{y}
```

Then the epilogue after each closed contour:

```
G1 F3600 E{acc-3}       <- dbDisGlueBack retract
G0 F18000 Z{h+0.3}
```

`+0.3` is `dbHeightIdle`, the travel lift.

**Speed rule that costs 2.4x if missed:** the first contour of a block runs at
`iSpeedFirstLayer` (1800), all later contours in that block run at
`iSpeedWork` (3600). Applying the first-layer speed everywhere halves wall speed.

## Colour switch

Emitted when the band plan changes extruder, at the layer boundary:

```
;extruder switch
G92 E0
G91
G1 F1200 E-85
M104 S{temp of new tool} T0
T{new}
G92 E0
G90
G1 F3600 E85
G1 F3600 E{85 + dbCompensateColor}
```

The `M104 ... T0` line always parks T0 at its print temperature; in a
single-colour job T0 never runs, so leaving it at 220 only makes it drool.

## Footer

```
;G code end
G91
G0 X5 Y5 F18000
G0 F18000 Z0
G90
G0 X750 Y750 F18000
G92 E0
G91
G1 F1200 E-85
M84
G90
M107
M104 S30 T0
M104 S30 T1
M106 S0
;End of Gcode
```

`G0 X750 Y750` is the park position and is the hard evidence for the usable bed
envelope: the machine layout in ZCCAD is 800x800.

## Extrusion model

Recovered from `OutPutG.getCurGlueDistance`, which computes

```
local1 = (speed/60) * L^3 / (A * W^2)
E      = local1 * (|d|/(speed/60)) * (L/W)
```

This collapses to a constant filament-mm per path-mm:

```
w = dbThicknessOrigin + dbThicknessCompensate      effective bead width
e_per_mm = (w / dbStuffWidth)^3 / 2.40104211897525
```

`GLUE_CONST_A = 2.40104211897525` was fitted from the vendor's own arithmetic.
At the shipped values (w=1.2, dbStuffWidth=1.75) it gives **E/mm =
0.134285714286**, which matches a vendor export to 8e-14.

## Modal rules the parser must honour

- `G91` makes X, Y, Z **and E** relative. The vendor retracts with
  `G91 / G1 F1200 E-85` and then restores `G90`. Reading E as always-absolute
  turns every retract into a bogus 85 mm extrusion.
- `G92 E0` rebases the absolute counter. Deltas are only meaningful since the
  last rebase.
- `E` is a running total within a block; the writer must carry it, never re-emit
  a per-move relative amount.

## Number formatting

Values are written like .NET `Double.ToString()` with invariant culture: up to 15
significant digits, trailing zeros trimmed, no padding. `"%.15g"` reproduces it.
Z is additionally rounded to 6 decimals. Coordinates are **not** fixed to 3
decimals — the vendor emits `Y335.30710675`.

## Layer and band model

- Layer count = `round(dbHeightShell / dbHeightLayer)`; layer *i* sits at
  `Z = (i+1) * dbHeightLayer`.
- `[colorControl]` zones are **heights in mm, not layer counts**: each zone's
  `dbLayerHeight` becomes `round(h / dbHeightLayer)` layers, and the last zone
  absorbs whatever is left.
- `iLayerGlueNo` value `g` drives nozzle `T(g-1)`: glue 1 -> T0, glue 2 -> T1.
- The reverse-print button flips the zone order (last configured band first).
