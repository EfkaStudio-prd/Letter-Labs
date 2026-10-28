# GcodePara.ini — every section, its UI tab, what it does

`S528/GcodePara.ini` is the live parameter state of ZCCAD. The app rewrites it
on every `get path`, so it is the authoritative record of what produced the
adjacent `temp.gcode`. Diff it against `work/backup_gui/GcodePara.before.ini` to
see what a UI change actually did.

Field names below are the vendor's own identifiers, including its typos
(`Thichness`, `Basplate`). Keep them verbatim when quoting to a user.

## [letterShell] — "Cangkang Surat" (Letter Shell)

The wall itself. Everything here changes the part's structure.

| Field | Meaning |
|-------|---------|
| `dbHeightShell` | total printed wall height in mm. Layers = this / `dbHeightLayer` |
| `dbHeightLayer` | layer height in mm (0.3 in the shipped profile) |
| `dbThicknessOrigin` | bead width `w` in mm; drives the E model |
| `dbThicknessCompensate` | added to bead width |
| `iThichnessCount` | number of **inset** wall passes beyond the outline |
| `dbThichnessOffset` | spacing between wall passes in mm (0.8) |
| `iThichnessType` | selects the wall-building mode (0 = plain) |
| `dbThichnessHeight` | Z threshold for the thickness variants; must be > 0.1 for them to act |
| `dbThichnessCompensate` | per-pass compensation |
| `dbWidthSide` | horizontal run of the side profile — used by `calculateRectSupport` / `rectSupportProcess` |
| `dbHeightTop` | top segment of the side profile — used by `updateCoor` |
| `dbHeightLow` | lower segment of the side profile — used by `updateCoor` |
| `dbOffsetPreSide` | how far outside the outline the prevent-curl frame sits |
| `iNumPreSide` | how many frame passes to print |
| `dbWidthKnife` | **acrylic cutting tool size, not a nozzle** |
| `dbHeightPin` / `dbWidthSidePin` / `dbThichnessHeight` / `dbThichnessOffset` | pin/joint features, unused in flat letter jobs |
| `bPrintDir` | print direction flag |
| `iSideLineSel` | side line selection, driven by `button17_Click` |
| `sCurFileName` | last DXF loaded into the app |

`iThichnessCount = 1` means the outline plus one inset line: the two parallel
walls visible on a printed sample. Ring count per layer =
`iThichnessCount + 1` levels x number of contours.

## [colorControl] — "Penggantian Warna" (Colour Switch)

| Field | Meaning |
|-------|---------|
| `iLayerNum` | how many colour zones are configured |
| `dbLayerHeight[0..6]` | **height in mm of each zone, not a layer count** |
| `iLayerGlueNo[0..6]` | glue/extruder index per zone; `g` maps to `T(g-1)` |
| `dbLayerOffset` | offset applied to zone boundaries |
| `bNozzleUsed` / `dbNozzleOffset` / `iNozzleCount` | multi-nozzle selection |
| `iSpeed` | zone print speed mm/min |
| `dbGlueWidth` | bead width for the zone |

Zones are printed bottom-up in the configured order; the reverse-print button
flips that. The last zone absorbs whatever layers remain, so the zone heights do
not have to sum to `dbHeightShell`.

## [printf3D_base] — machine and speeds

| Field | Meaning |
|-------|---------|
| `strCurFilePath` | last chosen output path (may point at a non-existent `D:\`) |
| `iSpeedWork` / `iSpeedFirstLayer` | wall speed / first contour of each block |
| `iSpeedIdle` | travel, typically 18000 |
| `iSpeedZ` | Z move speed, 1200 |
| `iSpeedGlueAhead` / `iSpeedGlueBack` | extrude / retract feedrate |
| `iSpeedIdle` used for all `G0` | |
| `dbHeightIdle` | travel lift above the current layer (0.3) |
| `dbHeightIdleSta` | standby lift |
| `dbDisIdle` | idle distance |
| `dbDisClear` | prime amount at the start of the pre-side frame |
| `dbDisEarlyOff` | early fan/heat-off distance |
| `iT0` / `iT1` | nozzle temperatures per tool |
| `bHeadTear` | head-tear (stringing) behaviour |
| `bNonPullback` | disable pullback |
| `iMachineSel` | machine profile selector, 1 in the current setup |
| `dbEndPosGluePoint` / `dbDisGluePoint` | glue-point / end Z position |

The vendor ships `iSpeedWork=1500`. The production profile measured from the
cleanest vendor print (`arr.gcode`) is 3600 work / 1800 first-layer, so ask for
`--speed 3600 --first-speed 1800` explicitly.

## [gluePara] — extrusion calibration

| Field | Meaning |
|-------|---------|
| `dbStuffWidth` | filament diameter (1.75) — the `d` in the E model |
| `dbDisGlueBack` | retract after each contour (3 mm) |
| `dbCompensateNear` / `dbCompensateFar` / `dbCompensateDis` | corner/short-segment compensation |
| `dbCompensateNear[0..2]` etc. | per-extruder compensation triples |
| `dbDisColorBack` | purge/retract amount at a colour switch (85 mm) |
| `iSpeedColorSwitch` / `iSpeedColorBack` | feedrates around a colour change |
| `dbCompensateColor` | extra prime after a colour switch (5 mm) |
| `dbDisOriginBack` / `dbPointGap` | origin retract / point gap |

## [surroundSide] — "Sisi Sekitar" (hem / lip band)

| Field | Meaning |
|-------|---------|
| `bUsed` / `bOutside` | enable the band, inside or outside |
| `dbHeight1` | **thickness of the top band where fill is held back** (0.9 mm = 3 layers at 0.3) |
| `dbHeight2` | second band height (3 mm) |
| `dbWidth` | band width (3 mm) |
| `dbGlueOffset` / `dbGlueWidth` | band line spacing / width |
| `bUsedFlat` / `dbOffsetFlat` | flat lip, offset 0.8 |
| `bUsedSharp` / `dbOffsetSharp` | sharp lip, offset 0.4 |
| `bUsedBoard` / `dbBoardPosX/Y/Height` | backing board placement |

`dbHeight1` is the one field the path generator needs today: both vendor exports
stop the fill exactly 3 layers below the top and run the wall alone.

## [preventCurl] — "Rok Anti Lengkung" (anti-curl skirt)

`dbCurlBaseOffset` 3, `dbCurlPressureWidth` 0.5, `dbCurlGlueWidth` 1.2,
`dbCurlHeight` 0.3, `dbCurlWidth` 3, `dbCurlLong` 10, `dbCurlGap` 3,
`bCurlUsedOut` / `bCurlUsedIn`, plus a `bGrid*` reinforcement grid and
`bVcurl*` V-openings and `bMini*` micro band. All disabled in the current INI.
The prevent-curl **frame** (`dbOffsetPreSide` / `iNumPreSide`) lives in
`[letterShell]` and *is* active — do not confuse the two.

## [footStep] — "Jejak Kaki" (footstep)

Seven slots of `bUsed[i]`, `dbPos[i]`, `dbHeight[i]`, `dbWtop[i]`,
`dbWbottom[i]`, `dbWidth[i]`, plus `dbGlueOffsetXY`, `dbGlueWidth`,
`dbGlueThickness`, `iSpeed`. Builds small feet under the letter. All slots off
currently.

## [connectWord] — "Penghubung Huruf"

`bUsed`, `bType`, `dbWidth`, `dbHeight`, `dbHeightLow`, `dbOffsetSupport`,
`dbExtra`, `dbRow`. Joins letters into one run so bridges span the gaps. Note
from the manual: "bottom width" here actually means bottom **height**.

## [bottomFill] and [panelFill] — "Pencetakan panel" / pola panel

Two-stage fill. `iType` / `iType2` choose fill type 1 / type 2; `dbInWidth`
("inner width", e.g. 0.8) creates the **inset contour**, which is distinct from
anything in `[letterShell]`. `iExtruder` picks the nozzle for each stage.
`panelFill.dbHeight` is a face-profile segment, not printed fill thickness.

## [surfaceCalculate], [ThousandColor], [boardCompensate], [baseplateGet]

Light-pocket and glue-point calculation, gradient colour, bed levelling
compensation, and baseplate DXF import (`strCurPathBasplate[i]`, which the vendor
defaults to a non-existent `D:\`). None are reproduced by the generator.

## Not stored in the INI

The reverse-print button only flips band order at generate time — pass
`--reverse-zones`. The `Combine` step and per-letter selection are UI state, not
parameters.
