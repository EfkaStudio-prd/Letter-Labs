# Manual map: ZCCAD field -> INI key -> CLI flag -> status

Every row below answers one question: *if I know the vendor manual, how do I ask
this generator for the same thing?*

Status legend: **OK** implemented · **~** partial / different mechanism ·
**NO** not implemented.

Field names are the vendor's own identifiers verbatim, including its typos
(`Thichness`, `Basplate`, `printf`).

---

## Toolbar / File & layout

| Manual label | INI | CLI | Status |
|---|---|---|---|
| Machine layout size (Wid x High) | not stored | `--bed` / `--place X,Y` (bed is 800x800) | OK |
| Import DXF | `sCurFileName` (last file only) | `--dxf FILE` | OK |
| Page center | UI state | `--place` | OK |
| Ro (rotate) | UI state | rotate in the source CAD | NO |
| Auto Layout | UI state | `--place` per job | ~ |
| Horizontal mirror | UI state | mirror in the source CAD | NO |
| Combine / Break Up | UI state | not needed: all contours are used | OK |
| Export DXF / Baseplate | `[baseplateGet]` `strCurPathBasplate[i]` | — | NO |

Layout drawings often carry the 800x800 bed as real geometry. Use
`--max-area MM2` to drop it, otherwise the frame prints as a giant border.

---

## Letter Shell — shape

| Manual label | INI | CLI | Status |
|---|---|---|---|
| letter height | `dbHeightShell` | `--height MM` | OK |
| layer height | `dbHeightLayer` | `--layer MM` | OK |
| letter type: line / incline / curve | `iThichnessType`, `iSideLineSel` | — | **NO** (straight edge only) |
| oblique width | `dbWidthSide` | — | **NO** (bevel only) |
| bottom height | `dbHeightLow` | — | **NO** (bevel only) |
| panel height | `dbHeightTop` | — | **NO** (bevel only) |
| around offset (pre-side frame) | `dbOffsetPreSide` | from INI; `--no-pre-side` disables | OK |
| around count | `iNumPreSide` | from INI | OK |
| reverse printf | not stored | `--reverse-zones` | ~ |
| select special side | `special_shape\*.dxf` | — | NO |
| knife width (acrylic cutter) | `dbWidthKnife` | — | NO (not a nozzle; irrelevant to G-code) |

---

## Letter Shell — wall

| Manual label | INI | CLI | Status |
|---|---|---|---|
| wall thickness | `dbThicknessOrigin` | `--width MM` | OK |
| wall compensate | `dbThicknessCompensate` | from INI | OK |
| line count | `iThichnessCount` | `--passes N` | OK |
| line offset | `dbThichnessOffset` | `--spacing MM` | OK |
| line height | `dbThichnessHeight` | — | **NO** |
| inner height (hole height) | — | — | **NO** |
| font bevel width (hole bevel) | — | — | **NO** |

Ring count per layer = `iThichnessCount + 1` levels x number of contours. An "O"
has two contours, so `--passes 1` prints 4 rings on it, not 2.

---

## Color Switch

| Manual label | INI | CLI | Status |
|---|---|---|---|
| count (zones) | `iLayerNum` | implied by `--bands` | OK |
| layer-1 .. layer-7 height | `dbLayerHeight[0..6]` | `--bands 10,30,10` (mm) | OK |
| extruder per zone | `iLayerGlueNo[0..6]` | `--glue 1,2,1` | OK |
| offset | `dbLayerOffset` | — | **NO** |
| nozzle-2 effective | `bNozzleUsed`, `dbNozzleOffset`, `iNozzleCount` | — | **NO** |
| extruder width | `dbGlueWidth` | `--width` | ~ |
| speed | `iSpeed` | `--speed` | OK |

Zones are **heights in millimetres, not layer counts**. UI extruder `n` maps to
`T(n-1)`, so UI 1 -> `T0`, UI 2 -> `T1`. The last zone absorbs the remaining
layers, so zone heights need not sum to `--height`.

**T0/T1 physical colour is unconfirmed.** Do not run a two-colour job until the
nozzle-to-filament mapping is known.

---

## Footstep (acrylic / PVC seat)

| Manual label | INI | CLI | Status |
|---|---|---|---|
| pos | `[footStep] dbPos[i]` | derived: `height - --seat-depth` | ~ |
| height | `dbHeight[i]` | — | **NO** (no V step) |
| width | `dbWidth[i]` | `--seat-w MM` | ~ |
| thick (flat step) | `dbGlueThickness` | `--layer` x layers | ~ |
| offset | `dbGlueOffsetXY` | `--seat-ramp` (closest equivalent) | ~ |
| speed | `iSpeed` | `--speed` | ~ |

This generator does not reproduce `[footStep]`. It builds an equivalent acrylic
pocket directly with `--seat-w` / `--seat-depth` / `--seat-land` / `--seat-ramp`,
which is a different mechanism with the same result: the wall thickens below a
shoulder and stops at it, leaving a lip-free ring for the sheet.

`--seat-depth` **is the sheet thickness**. A 3 mm sheet means `--seat-depth 3`,
which puts the shoulder at `height - 3` — the same rule the manual gives as
`step 2 pos = letter height - acrylic`.

---

## Prevent Curl

| Manual label | INI | CLI | Status |
|---|---|---|---|
| outer / inner | `bCurlUsedOut` / `bCurlUsedIn` | — | **NO** |
| press width | `dbCurlPressureWidth` | — | **NO** |
| extruder width | `dbCurlGlueWidth` | — | **NO** |
| height | `dbCurlHeight` | — | **NO** |
| length | `dbCurlLong` | — | **NO** |
| width | `dbCurlWidth` | — | **NO** |
| V-shaped width | `dbCurlGap` | — | **NO** |

The anti-curl **frame** that this generator does print is a different feature: it
comes from `[letterShell] dbOffsetPreSide` / `iNumPreSide` and is emitted as the
`;calculatePreSide start .. end` block. Do not confuse the two.

---

## Connect Letter

All fields in `[connectWord]`: `bUsed`, `bType`, `dbWidth`, `dbHeight`,
`dbHeightLow`, `dbOffsetSupport`, `dbExtra`, `dbRow`. **Not implemented.**

Note from the manual: `dbHeightLow` is labelled *bottom width* in the UI but
actually means bottom **height**.

---

## Surround Side (hem / lip)

| Manual label | INI | CLI | Status |
|---|---|---|---|
| flat effective | `bUsedFlat`, `dbOffsetFlat` | hem band (on by default) | ~ |
| sharp effective | `bUsedSharp`, `dbOffsetSharp` | — | **NO** |
| inner / outer | `bUsed`, `bOutside` | — | ~ |
| surround height | `dbHeight1` | 3 top layers at 0.3 mm | OK |
| sharp height | `dbHeight2` | — | **NO** |
| width | `dbWidth` | — | ~ |
| speed | from `[printf3D_base]` | `--speed` | ~ |

`dbHeight1 = 0.9` is 3 layers at 0.3 mm: both vendor exports stop the fill exactly
3 layers below the top and run the wall alone. That is why the hem band is
3 top layers, not 1.

---

## Fill Panel

| Manual label | INI | CLI | Status |
|---|---|---|---|
| panel printf | `[panelFill] iType` | `--fill` | ~ |
| fill spacing | `dbFillSpacing` | `--fill-spacing MM` | OK |
| boundary distance | `dbBoundaryDis` | — | **NO** |
| angle | `dbAngle` | fixed 45 | ~ |
| fill type 1 height (face) | `panelFill.dbHeight` | `--first-layer-fill` | ~ |
| fill type 2 height (back) | `iType2` | — | **NO** |
| inner width (inset contour) | `dbInWidth` (0.8) | — | **NO** |
| separate extruder | `iExtruder` | — | **NO** |
| grid support | `[bottomFill]` | — | **NO** |
| floor fill | `[bottomFill]` | — | **NO** |
| pattern (blue geometry) | `[panelFill]` pattern fields | — | **NO** |

Fill is the least complete area. `--fill` produces a simple hatch; the vendor's
two-stage face/back fill with inset contours and separate extruders is not
reproduced.

---

## Baseplate

`[baseplateGet]` writes a **DXF** for CNC cutting, not G-code. **Not implemented.**
It is a separate CAM job in any case: the DXF carries geometry only, no toolpath.

---

## File Output / Machine parameters

| Manual label | INI | CLI | Status |
|---|---|---|---|
| printing speed | `[printf3D_base] iSpeedWork` | `--speed` (mm/min) | OK |
| first layer speed | `iSpeedFirstLayer` | `--first-speed` | OK |
| movespeed | `iSpeedIdle` | from INI | OK |
| nozzle 1 / 2 temperature | `iT0`, `iT1` | from INI | OK |
| machine type (ZC-60/80/120) | `iMachineSel` | — | **NO** |
| printf by S-shaped | — | — | **NO** |
| non pullback | `bNonPullback` | from INI | ~ |
| material diameter | `[gluePara] dbStuffWidth` | from INI (1.75) | OK |
| back distance | `dbDisGlueBack` | from INI (3 mm) | OK |
| switch distance | `[gluePara] dbDisColorBack` | from INI (85 mm) | OK |
| switch compensate | `dbCompensateColor` | from INI (5 mm) | OK |
| hold up high 1 / 2 | `[printf3D_base] dbHeightIdle` | from INI (0.3) | OK |
| idle distance | `dbDisIdle` | from INI | OK |
| end position | `dbEndPosGluePoint` | from INI | OK |
| extruder clear | `dbDisClear` | from INI | OK |
| early close | `dbDisEarlyOff` | from INI | OK |
| Z axis speed | `iSpeedZ` | from INI (1200) | OK |
| near / far shortage | `dbCompensateNear/Far` | from INI | OK |

The vendor ships `iSpeedWork=1500`, which is slow. The cleanest measured vendor
print (`arr.gcode`) runs 3600 work / 1800 first layer. Ask for
`--speed 3600 --first-speed 1800` explicitly rather than trusting the INI.

---

## Booleans that are silently off

Several features require *both* a non-zero value and a flag. Two that already bit
this project:

- `dbWidthSide = 0` means no bevel taper, even when `dbHeightTop` / `dbHeightLow`
  are non-zero. A straight-edge letter therefore emits no extra wall passes.
- `dbThichnessHeight` must exceed 0.1 and `iThichnessCount` must be at least 2
  before `thichnessProcess_Height` does anything.

When a vendor field appears to have no effect, check its gate before assuming the
model is wrong.
