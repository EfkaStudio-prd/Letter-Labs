# Verified facts, open gaps, and golden tests

Read this before claiming a job is print-perfect. Each item is tagged by how it
was established.

## Verified against a vendor export

The golden pair is `fixtures/a_golden.dxf` -> `A_SAMPLE_50mm.gcode`: a real
ZCCAD export at `dbHeightShell=50`, `dbHeightLayer=0.3`, bands `10/30/10` with
glue `1/2/1`, bead 1.2 mm, 1 inset pass, spacing 0.8 mm.

With that reference, the generator passes **all eight structural gates**:

| Gate | Result |
|------|--------|
| E/mm mean | delta 8.3e-14 |
| E/mm min / max | delta 1.3e-11 / 2.9e-10 |
| print Z ladder | identical, 167 layers |
| lift Z set | identical, 170 values |
| tool sequence | identical `0,1,1,0,0,0,1,0` |
| markers | identical, same order |
| feedrate set | identical `{750,1200,1500,1800,3600,9000,18000}` |

The 3D preview of both files is visually indistinguishable: same outline, same
red/blue/red band stack, same prevent-curl foot.

**So the dialect is right.** What is not yet right is the amount of geometry in
one specific Z band, below.

## OPEN GAP 1 — top-band wall taper (bevel letters only)

**Scope correction.** The taper run in `updateCoor` is `dbWidthSide / V8`, i.e. the
UI's **oblique width**. A straight-edge letter has oblique width 0, bottom height
0 and panel height 0, so the offset evaluates to 0 and ZCCAD emits no extra
passes at all. The gap therefore applies **only to incline/bevel letters**, which
this engine does not model. `letterlab.py job` now suppresses the NOTICE when
`dbWidthSide <= 0.001`, so a straight job is no longer flagged.

The vendor reference that exhibits the taper (`A_SAMPLE_50mm.gcode`) was exported
with oblique width 20, so its 32 extra layers are bevel geometry, not a generic
wall feature. Do not "fix" it by adding rings to a straight job.

`labcheck.py A_SAMPLE_50mm.gcode job.gcode` reports (this is still true today):

```
REF    rings=748  extruding path=178.8 m
MINE   rings=670  extruding path=152.9 m
total layers with a ring-count difference: 32 of 169
```

The vendor's ring count per layer steps up near the top and back down:

| Z from | rings/layer |
|--------|-------------|
| 0.60 | 4 |
| 35.70 | 5 |
| 38.10 | 6 |
| 40.80 | 7 |
| 43.20 | 8 |
| 45.30 | 4 |

Measured ring insets show the extra rings are **deeper insets of the outer
boundary only** — holes never gain a ring — each about 1.0 mm further in than
the previous one, spaced ~2.4-2.7 mm (8-9 layers) apart.

The band `[dbHeightShell - dbHeightLow - dbHeightTop, dbHeightShell -
dbHeightTop]` = `[50 - 10 - 5, 50 - 5]` = `[35.0, 45.0]` matches the observed
`35.7 .. 45.0` window to within a layer.

`IL` confirms the owner: `letterShell.dbHeightTop` and `dbHeightLow` are read
only by `OutKF.updateCoor(StreamWriter, WorkData, Int32 n, Double h, WorkData
wd_new, Double& outCurOffset)`, which takes an `outCurOffset` — i.e. it grows the
wall as it rises. `dbWidthSide` belongs to a different routine,
`calculateRectSupport` / `rectSupportProcess`.

**Not yet recovered:** the exact rule that turns the taper offset into a pass count.
`letterlab.py job` now prints a NOTICE with the band whenever the job is tall
enough for it. Until this is closed, do not treat a tall letter from this
generator as identical to a ZCCAD print: its upper band has a thinner wall.

### What updateCoor actually computes

Recovered from the IL of `OutKF.updateCoor(sw, wd, n, h, wd_new, outCurOffset)`
(`n` = layer index, `h` = layer height), for the `bPrintDir == false` path that
the shipped INI selects:

```
V10 = dbHeightShell - dbHeightTop - dbHeightLow        # band start, 35 here
if V10 > 0.001:
    V8 = abs(V10 / h) + 1                             # 117.667
    V7 = dbWidthSide / V8                             # 0.170 mm/layer
V11 = int(dbHeightLow / h) + 1                         # 34
z   = n * h

if z <= dbHeightLow:              taper = V7 * V8                 # = dbWidthSide
elif z > V10 + dbHeightLow:       taper = 0
else:                             taper = V7 * max(0, V8 - (n - V11))
```

So `taper` falls linearly from `dbWidthSide` (20 mm) at z = dbHeightLow to 0 at
z = V10 + dbHeightLow = 45, and the value is handed to `extraPoint`, which emits
inset geometry. `dbWidthSide` is therefore the *run* of the taper and
`dbHeightLow`/`dbHeightTop` place it in Z.

Measured emission from the vendor file, which this formula does not yet explain
cleanly: extra passes appear at z = 35.7, 38.1, 40.8, 43.2 (8, 9, 8 layers
apart) and the pass count is 4 -> 5 -> 6 -> 7 -> 8, then back to 4 above 45. The
extra passes are deeper insets of the outer boundary at the normal
`dbThichnessOffset` spacing. A pass-count rule fitted to those four boundaries is
overfitting one sample; derive it from a controlled pair of exports instead.

### HYPOTHESIS (unconfirmed, but the geometry lines up too well to ignore)

`updateCoor`'s band may be **ZCCAD's own acrylic shoulder** - the same feature the
generator implements by hand as `Seat` / `--seat-w`.

Set `seat.depth = dbHeightTop` and `seat.ramp = dbHeightLow` and `seat.land = 0`
and the two bands become identical:

```
vendor updateCoor   : [H - top - low,  H - top]  = [25.0, 35.0]  for H=40
this generator seat : [z_seat-land-ramp, z_seat] = [24.9, 34.9]  (z_seat = H-depth)
```

Both then do the same thing: add progressively deeper inset lines of the outer
boundary through the band, and stop adding them for the top `dbHeightTop` mm,
which is exactly how a pocket is left for a sheet to rest in.

If this is right, GAP 1 closes by *parameterising* rather than reverse-engineering
a mystery curve: `dbWidthSide` is the pocket run, `dbHeightLow` the ramp, and
`dbHeightTop` the lip. It also explains why the observed run in `A_SAMPLE_50mm`
stopped at ~5 mm rather than the nominal 20 mm - the taper is bounded by the
counter it runs into.

**Not proven.** Confirm by exporting one job from ZCCAD with `dbWidthSide` changed
and nothing else, and checking whether the extra passes move outward by the same
amount. Until then treat the seat model and the vendor taper as two different
things that happen to agree.

## Acrylic pocket: depth must equal the sheet thickness

The pocket is built by `seat_levels()`, not by any vendor INI field. `z_seat =
top - seat.depth`, so `--seat-depth` **is** the panel thickness and the vendor's
footstep rule (`pos = letter height - acrylic`) is satisfied automatically: a
3 mm sheet with a 40 mm shell puts the shoulder at z=37.

The engine default used to be 5.0 mm, and the orchestrator had no
`--seat-depth` passthrough at all, so every `--seat-w` job silently built a 5 mm
pocket. Fixed: default is now 3.0 and `--seat-depth` / `--seat-land` /
`--seat-ramp` pass through from `letterlab.py`. Verify with the ring profile —
the count must collapse back to the baseline at `height - acrylic`:

```
from z=27.60 :  88 rings/layer   <- ramp begins (shoulder - land - ramp)
from z=35.10 :  160 rings/layer  <- full pocket wall
from z=37.20 :   60 rings/layer  <- lip only: 40 - 3 = 3 mm pocket
```

## New flag: --max-area (layout-frame exclusion)

A DXF that carries the machine-bed rectangle as geometry (the natural way to show
where a job sits on the bed) would otherwise print that rectangle as an 800 mm
border. `--max-area MM2` drops contours above an area threshold, so a layout
reference file can be used directly and still yield only the artwork. Verified on
`Tes 3d print+machine Layout.dxf`: 31 closed rings in, 30 contours out, the
640 000 mm2 bed rectangle dropped.

## CLOSED (was reported as a gap in error) — "first-layer extra rings"

An earlier revision of this file claimed the vendor prints 6 rings on layer 0
while we print 4. **That was wrong.** The two extra rings at z = 0.3 are the two
`calculatePreSide` frame passes (bbox 345.10..454.85 and 346.40..453.55, i.e. the
outline offset by `dbOffsetPreSide` = 15 mm and then 15 - 1.2 mm), which this
generator emits identically. Both files show 6 rings at z = 0.3, and selftest T7
confirms 0 ring-count mismatches across the 99 probed layers from z = 0.6 to 30.
The real difference is confined to the taper band above.

## FIXED — DXF geometry inside BLOCK / INSERT

`lettergcode/dxf.py` used to walk only the ENTITIES section, so any drawing whose
shapes live in a BLOCK imported as zero contours. It now:

- collects BLOCKS and ENTITIES together and expands `INSERT` with scale (41/42),
  rotation (50) and rectangular arrays (70/71, 44/45), applying DXF's
  scale-then-rotate-then-translate order about the block origin;
- falls back to the single non-anonymous block when a drawing has no model-space
  geometry at all, printing a warning to stderr (this is what the vendor's
  `special_shape` library needs).

Covered by selftest T1 and T2. `work/w7.dxf` now yields 1 entity where it
previously yielded 0. Caveat on the fallback: a drawing that has *only* a title
block and no real content would be picked up too — the warning is there so it is
visible rather than silent.

## OPEN GAP 2 — nozzle-to-filament mapping unconfirmed

`iLayerGlueNo` value `g` -> `T(g-1)` is derived from code inspection and from
what two-colour vendor exports contain; it has **never been checked against the
physical labels on the machine's nozzles**. A wrong map heats and extrudes the
wrong nozzle. Confirm with the user before running a two-colour job.

## Unmodelled INI sections

`[footStep]`, `[preventCurl]` (skirt/grid/V-curl, distinct from the pre-side
frame), `[connectWord]`, `[bottomFill]`, `[panelFill]`, `[surfaceCalculate]`,
`[ThousandColor]`, `[boardCompensate]`, `[baseplateGet]`. All are disabled in the
shipped INI, so they do not affect current comparisons — but any of them enabled
in the app will produce a file this generator cannot reproduce.

## Established facts worth not re-deriving

- `GLUE_CONST_A = 2.40104211897525`, `e_per_mm = (w / dbStuffWidth)^3 / A`.
- Bead width `w = dbThicknessOrigin + dbThicknessCompensate`.
- Colour zones are **heights in mm**, converted with `round(h / dbHeightLayer)`;
  the last zone absorbs the remainder.
- Hem band = `surroundSide.dbHeight1 / dbHeightLayer` top layers where fill is
  suppressed and the wall continues. Both exports agree: 3 layers at 0.9 mm.
- First contour of a block at `iSpeedFirstLayer`, later contours at `iSpeedWork`.
- `G91` makes E relative too.
- Bed envelope 800x800, park at `G0 X750 Y750`.
- ZCCAD's own required order is: bed size -> Import -> frame -> **Combine** ->
  select all characters -> shell params -> `get path` -> `file output`. Skipping
  Combine yields a ~466 byte file with an empty toolpath.
- `S528/temp.gcode` is scratch state, overwritten on every `get path`. Copy it
  somewhere else immediately after taking a reference.
- The app has no `D:` drive; `strCurFilePath` pointing at `D:\` never writes.

## Adding a golden test

1. In ZCCAD, set the parameters you want and run `get path`.
2. Copy `S528/temp.gcode` to a permanent name **and** snapshot
   `S528/GcodePara.ini` beside it — the INI is what makes the reference
   reproducible.
3. Recover the input outlines: `python work/w2dxf.py REF.gcode out.dxf 3.0`
   grabs the rings at one layer. Keep only the pass-0 rings (the coarse ones the
   vendor prints first; its own offset passes follow with far more vertices).
4. Save the DXF into `fixtures/`, record the parameter set in this file, and run
   `letterlab.py job --dxf fixtures/X.dxf --out work/X.gcode --ref REF.gcode`.

`fixtures/a_golden.dxf` was built this way from `A_SAMPLE_50mm.gcode`.

## Tooling notes

- Everything is standard-library Python. No numpy, no matplotlib, no PIL. The
  3D renderer writes PNG with `zlib` + `struct` and a hand-built 5x7 bitmap font.
- `gcode3d.py` renders a 242k-segment file (9.8 MB G-code) in about 10 s.
- The vendor `.exe` and `OutPutG.dll`, `ParaMeter.dll`, `MatterLib.dll`,
  `NestingLibPort.dll`, `lcdb.dll`, `INDALLB.dll` are all managed .NET and fully
  decompilable. `SamGeom*.dll` (up to 20 MB) and `dog_windows_*.dll` are native.
- Only the .NET *runtime* is installed, so `dotnet tool install -g ilspycmd`
  fails until an SDK is added. `work/ildump.ps1` is the current substitute: it
  reflects over an assembly and disassembles method bodies to IL with resolved
  tokens, which is enough to read control flow and field access.
