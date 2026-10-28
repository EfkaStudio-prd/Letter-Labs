# Validation report

Every claim below was measured, not inferred. Where a claim is weaker than it
looks, it says so.

---

## 1. The reference pair is genuine

The strongest evidence in this repo is a real 1:1 vendor input/output pair:

```
A SAMPLE.dxf  ->  A_SAMPLE_50mm.gcode
```

Confirmed by matching the printed outline against the DXF: the export prints a
`79.90 x 100.00 mm` outer boundary with a `17.87 x 42.33 mm` counter, and the DXF
contains exactly that pair. The other 28 contours in the DXF are a legend block
and are excluded by `--min-area`.

Parameters of that export: height 50 mm, layer 0.3 mm, bead 1.2 mm, 1 inset pass,
spacing 0.8 mm, colour bands `10 / 30 / 10` with glue `1 / 2 / 1`, oblique width
20, bottom height 10, panel height 5.

---

## 2. Header and footer are byte-identical

```
VENDOR (A_SAMPLE_50mm.gcode)     GENERATED
;This G_Code provided by ...     ;This G_Code provided by ...
;G code start                    ;G code start
M104 S220 T0                     M104 S220 T0
M109 S220 T0                     M109 S220 T0
M104 S220 T1                     M104 S220 T1
M109 S220 T1                     M109 S220 T1
G21 / G90 / G82 / G28            G21 / G90 / G82 / G28
```

Tail, both files:

```
G1 F1200 E-85
M84
G90
M107
M104 S30 T0
M104 S30 T1
M106 S0
;End of Gcode
```

The vendor emits one heat block per **configured** tool. Every file in the corpus is
a 2- or 3-tool job, so those heat 2 or 3 nozzles. A single-colour job here emits
only the block for the tool its band plan references. That case does not occur in
the 13-file corpus, so the vendor's behaviour for it is unconfirmed — but the lines
it uses (`M104 S220 T0` / `M109 S220 T0`) are vendor shapes either way.

Never `M104 S0`. No export in the corpus contains that line; see
[DIALECT_CORPUS.md](DIALECT_CORPUS.md) for the defect that came from emitting it.

---

## 3. All eight structural gates pass

`validate_gcode.py A_SAMPLE_50mm.gcode TEST1_A_50mm_ref.gcode`

| Gate | Reference | Generated | Delta | Result |
|---|---|---|---|---|
| E/mm mean | 0.134285714286 | 0.134285714286 | 8.4e-14 | PASS |
| E/mm min | 0.134285713688 | 0.134285713683 | 5.2e-12 | PASS |
| E/mm max | 0.134285715060 | 0.134285714817 | 2.4e-10 | PASS |
| print Z ladder | 167 values | 167 values | identical | PASS |
| lift Z set | 169 values | 169 values | identical | PASS |
| tool sequence | `0,1,1,0,0,0,1,0` | `0,1,1,0,0,0,1,0` | identical | PASS |
| markers | 12, same order | 12, same order | identical | PASS |
| feedrate set | `{750,1200,1500,1800,3600,9000,18000}` | same set | identical | PASS |

Retract amounts also match exactly: `{-3.0, -85.0, -42.5}` at the same
frequencies up to geometry differences.

---

## 4. Line-vocabulary test (the strict format check)

The structural gates compare *sets* of values. This test is stricter: it asks
whether **any line shape we emit is absent from the vendor corpus**.

Method: take the 13 supplied exports (11 distinct files, 12 usable, **36 distinct
line shapes**), mask only coordinate/extrusion/feed values, and keep command
numbers (`G0 G1 G21 G28 G82 G90 G91 G92 M104 M106 M107 M109 M117 M84 T0 T1 T2`)
intact. Then diff. `2.gcode` is excluded automatically because its E channel is
broken (total extrusion 0.0 mm over 61.7 m of path).

| File | Shapes emitted | Not found in a vendor file |
|---|---|---|
| `TEST1_A_50mm_ref.gcode` | 31 | **0** |
| `TEST2_BALI_40mm.gcode` | 27 | **0** |
| `TEST3_WELCOME_30mm.gcode` | 31 | **0** |
| `TEST4_BALI_10mm_smoke.gcode` | 27 | **0** |

Nothing is invented. Every line uses a form a real ZCCAD export already
contains: no custom commands, no foreign flavour, no comments the firmware could
choke on.

---

## 5. Geometry: where we match and where we do not

`labcheck.py` compares ring count and path length **per layer**, which is the only
check that sees missing geometry.

Against `A_SAMPLE_50mm.gcode` over `z = 0.6 .. 30 mm`:

```
99 probes, 0 mismatches
```

Above `z = 35` the vendor prints 32 extra layers: ring count steps
`4 -> 5 -> 6 -> 7 -> 8` at `z = 35.7, 38.1, 40.8, 43.2`, then returns to 4 at
`z = 45.3`. Path length 178.8 m vs our 152.9 m.

**This is not a defect.** The taper offset in `OutKF.updateCoor` is
`dbWidthSide / V8`, i.e. the UI's *oblique width*. That reference export was made
with oblique width 20, so those layers are **bevel geometry**. A straight-edge
letter has oblique width 0, bottom height 0 and panel height 0; the offset
evaluates to 0 and ZCCAD emits no extra passes either. Straight jobs match.

Bevel/incline letters are **not implemented**, and that is the only material
geometry gap.

---

## 6. Acrylic pocket verified from the emitted G-code

`TEST2_BALI_40mm.gcode`, 40 mm shell (134 layers, top z=40.20), `--seat-w 3.2
--seat-depth 3`:

```
60 rings/layer   baseline: 30 contours x 2 wall passes
88   from z=27.9   ramp begins (shoulder - land - ramp)
160  from z=35.4   full pocket wall
60   from z=37.5   lip only
```

The shoulder is at `40.20 - 3 = 37.20`, so the first lip-only layer is 37.50 and
the pocket is exactly 3 mm deep for a 3 mm sheet, matching the vendor footstep
rule `pos = letter height - acrylic`.

Numbers here are revision 2. Revision 1 (133 layers, top 39.90) had the shoulder
at 36.90 and the collapse at 37.20.

Two defects were found and fixed while establishing this:

1. The engine default for `--seat-depth` was 5.0 while the orchestrator had no
   passthrough for it, so **every** seat job silently built a 5 mm pocket. A 3 mm
   sheet would rattle. Default is now 3.0 and the flag passes through.
2. The taper NOTICE fired on straight-edge jobs where the vendor would emit
   nothing. It is now scoped to `dbWidthSide > 0`.

---

## 7. Engine self-check: 10/10

```
PASS T1  INSERT scale/rotate/translate      box1=(100,50,120,70) box2=(-10,0,0,10)
PASS T2  block-only drawing imports         1 entity recovered from the block
PASS T3  vendor E/mm constant               0.134285714286 == 0.134285714286
PASS T4  bands mm -> whole layers           [(1,33),(2,100),(1,34)] n=167
PASS T5  hem band = 3 top layers
PASS T6  golden dialect gates               validate_gcode rc=0
PASS T7  per-layer ring count (z 0.6..30)   99 probes, 0 mismatches
PASS T8  simulator tool/layer/E-modal
PASS T9  simulator honours modal F          0.0556 min, expected 0.0556
PASS T10 PNG writer emits a decodable file
10/10 checks passed - ALL CHECKS PASS
```

T9 exists because a real bug was found: the simulator ignored modal `F`, so
vertex lines with no `F` word were timed at a default and print time was reported
at roughly double. `G1 X.. Y.. E..` carries no `F` in this dialect.

---

## 8. DXF input coverage, tested on real files

| File | Result |
|---|---|
| `A SAMPLE.dxf` | 30 entities, spline-heavy, 2 real contours + legend block |
| `Bali Kita Kita Logo.dxf` | 30 SPLINE -> **30 closed rings**, 0 open chains, 0 noise, 300.00 x 172.07 mm |
| `Tes 3d print+machine Layout.dxf` | logo **plus** an 800 x 800 bed rectangle; `--max-area 100000` drops the frame, 31 rings in -> 30 out |
| `S528/special_shape/*.dxf` | geometry lives in a `BLOCK`; the reader now resolves it (was 0 rings) |

`Bali Kita Kita Logo.dxf` is the useful one: a real-world spline-heavy file that
flattens perfectly, independent of our own fixture.

---

## 9. Bed coordinates

The machine origin is a **bed corner**, not the centre. Established from
`A_SAMPLE_50mm.gcode`: the part sits centred at about `(400, 398)` inside a
`0..800` space and the footer parks at `X750 Y750`.

Therefore a layout DXF whose bed rectangle is centred on the origin maps as
`bed = DXF - frame_min`. For the Bali layout that puts the logo at
`--place 459.82,27.38` — 40 mm from the right edge, 27 mm from the front, exactly
as drawn.

---

## 10. Physical run

A vendor export in this exact dialect has been printed on the machine:
`5 (2).gcode`, 414,726 bytes, md5 `e5cd7abb4cc5af4c6c4f93c281ddfdb6`. Full
analysis, photos and the filament mapping are in
[PHYSICAL_RUN.md](PHYSICAL_RUN.md).

Headline results:

- 15.00 mm tall, 0.30 mm layers, part 100.07 x 150.00 mm, exactly 2 tools.
- `T1` prints z 0.30 .. 5.10, then `T0` prints z 5.10 .. 15.00. The switch lands
  precisely on layer 17.
- Spool order 1/2/3 = transparent / white / transparent resolves to
  `T0` / `T1` / `T2`, matching the printed part.
- This engine reproduces that structure: `--height 15 --bands 5.1,9.9 --glue 2,1`
  gives `T1` from 0.30 and `T0` from 5.10.

What that does **not** prove: the printed file was written by ZCCAD, not by this
engine. The machine and the dialect are proven; a LetterLab file is not.

---

## 11. What is still unproven

| Item | Why | Consequence |
|---|---|---|
| A LetterLab file on hardware | Only a vendor export has been printed | **The final gate. Print `TEST4` first.** |
| Dimensional accuracy | Never measured on a printed part | Wall thickness, pocket fit and overall size are unverified against the spec |
| `T2` | Loaded but never used in the confirmed print | Third colour route untested |
| Bevel / incline letters | Not implemented | Straight-edge only |
| Vendor export for the Bali shape | Does not exist | `TEST2/3/4` inherit dialect proof from `TEST1`; their geometry is unaudited against a vendor twin |
| Taper pass-count rule above the band | Only one sampled export | Not needed while bevel is unimplemented |
