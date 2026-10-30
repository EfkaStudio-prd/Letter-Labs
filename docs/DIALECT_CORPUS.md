# Dialect derived from 14 real exports

A dialect is not "the shape of one file". It is what every real export agrees on.
This document records the measurement, the invariants that fell out of it, and the
defects it exposed in the generator.

Reproduce with:

```bash
# against your own folder of vendor exports
python .qoder/skills/letterlab-skill/scripts/corpus_audit.py  DIR
python .qoder/skills/letterlab-skill/scripts/dialect_check.py --corpus DIR --test JOB.gcode
```

The vendor exports themselves are **not** in this repository (see `README.md`
→ Provenance), so reproduce by pointing `--corpus` at a folder of exports you
obtained from your own machine.

## The corpus

14 files supplied as known-good exports. `5.gcode`, `5 (1).gcode` and `5 (2).gcode`
are byte-identical (md5 `e5cd7abb4cc5af4c6c4f93c281ddfdb6`), so there are 12
distinct files.

| File | Layers | Z range | Layer h | Tools | Footprint mm | Path | Distinct line shapes |
|---|---|---|---|---|---|---|---|
| `1.gcode` | 101 | 0.3 – 30.3 | 0.3 | T0,T1 | 145.06 x 182.28 | 128.2 m | 31 |
| `2.gcode` | 50 | 0.3 – 15.0 | 0.3 | T0,T1 | 145.06 x 182.28 | 61.7 m | 31 |
| `5.gcode` (= 5(1), 5(2)) | 50 | 0.3 – 15.0 | 0.3 | T0,T1 | 145.05 x 182.28 | 97.3 m | 31 |
| `arr.gcode` | 18 printed | 0.3 – 15.0 | 0.3 | T0,T1 | 184.63 x 140.50 | 50.1 m | 31 |
| `TES .gcode` | 167 | 0.3 – 50.1 | 0.3 | **T0,T1,T2** | 135.34 x 110.00 | 143.2 m | 32 |
| `Welcome new tes.gcode` | 62 printed | 0.5 – 30.5 | **0.5** | T0,T1 | 388.39 x 132.69 | 88.1 m | 31 |
| `test .gcode` | 50 | 0.3 – 15.0 | 0.3 | T0,T1 | 215.06 x 201.73 | 83.7 m | 31 |
| `test 1.gcode` | 50 | 0.3 – 15.0 | 0.3 | T0,T1 | 245.61 x 207.67 | 83.7 m | 31 |
| `test 2.gcode` | 50 | 0.3 – 15.0 | 0.3 | T0,T1 | 351.70 x 207.82 | 42.2 m | 31 |
| `W_bevel_30mm_BRAIN_R0.gcode` | 100 | 0.3 – 30.0 | 0.3 | T0,T1 | 79.87 x 95.11 | 54.8 m | 31 |
| `W_tegak_15mm_BRAIN_R0.gcode` | 50 | 0.3 – 15.0 | 0.3 | T0,T1 | 79.87 x 95.11 | 40.3 m | 31 |
| `welcome_tes_ZCCAD.gcode` | 101 | 0.3 – 30.3 | 0.3 | **T0 only** | 321.17 x 82.92 | 196.8 m | 31 |

### The 30 mm export that settled the layer rule

`welcome tes.gcode` is the single most useful file in the corpus: it is a real ZCCAD
export where the requested height is known to be **30 mm**, and it contains
**101 layers ending at z = 30.30**. That is `floor(30 / 0.3) + 1`, not
`ceil(30 / 0.3)` = 100.

Cross-checked against every other export with a known height:

| Requested | Rule `floor(H/h)+1` | Observed | Matches |
|---|---|---|---|
| 30 mm / 0.3 | 101 → z 30.30 | `welcome tes`, `1.gcode` | yes |
| 50 mm / 0.3 | 167 → z 50.10 | `A_SAMPLE_50mm`, `TES` | yes |
| 30 mm / 0.5 | 61 → z 30.50 | `Welcome new tes` | yes |
| 40 mm / 0.3 | 134 → z 40.20 | — | consistent |
| 10 mm / 0.3 | 34 → z 10.20 | — | consistent |

`ceil` agrees everywhere except an exact multiple, and 30 mm is exactly that case.
ZCCAD deliberately overshoots by one layer so a part is never short.

Also from this file: **`;extruder switch` is not universal.** It appears in every 2-
and 3-tool export and is entirely absent from this single-tool one, so it is
required only when the colour plan actually prints with more than one tool.

`arr.gcode` and `Welcome new tes.gcode` report fewer printed layers than the Z
range implies because a tool change skips one layer height — see *Quirks* below.

## Two files are not usable as references

**`2.gcode` has a broken E channel.** It moves 61.7 m of toolpath while the total
extrusion sums to **0.0 mm** (E/mm median 1.34e-07, i.e. a millionth of every other
file). It cannot have printed anything. Excluded from the reference set by
`dialect_check.py` automatically.

**`W_bevel_30mm_BRAIN_R0` and `W_tegak_15mm_BRAIN_R0` are this project's own
output**, not vendor exports. Their E/mm is 0.134285758 / 0.134285708 — the drift
signature of accumulated float deltas — and their naming follows our test
convention, not the vendor's. They are left in the corpus because they are within
tolerance, but they carry no independent authority.

## Invariants

| Property | Value | Notes |
|---|---|---|
| First comment | `;This G_Code provided by DongGuan ZhenCai Lmt` | 11/11 |
| E per mm | `0.134285714286` | 10/10 valid files |
| Tool rule | UI slot `n` → `T(n-1)` | holds in every file |
| Layer height | parameter | 0.3 in ten files, **0.5** in `Welcome new tes` |
| Feedrates | parameter | sets differ per file |
| Retracts | `-3.0`, `-42.5`, `-85.0` | `-3` contour, `-42.5` half, `-85` switch |
| Line shapes | 36 distinct across the whole corpus | the entire vocabulary |

### Required markers

Present in at least 80% of the valid files, so a conforming file must carry them:

```
;This G_Code provided by DongGuan ZhenCai Lmt
;G code start
;G code end
;End of Gcode
;calculatePreSide start
;calculatePreSide end
;start printf
;extruder switch
```

`;Y max,preventCurlUpDateCoor` appears only when the anti-curl frame is active, so
it is a feature marker, not a rule.

### G and M code set

`G0 G1 G21 G28 G82 G90 G91 G92`, `M84 M104 M106 M107 M109 M117`.
Nothing else appears in 11 real exports.

## Quirks that matter for byte-level equality

**A tool change skips one layer height.** `5 (2).gcode` prints z=5.10 then z=5.70;
`5.40` exists only as `G0` travel, never `G1` extrusion. `TES .gcode` does the same
at 10.20/10.50 and 40.20/40.50. So a ZCCAD colour change leaves a 0.3 mm band with
no extrusion. This generator prints every layer, so its colour-change band is
continuous. Structural difference, not a defect.

**Bands round UP.** `TES .gcode` requests a 10 mm first band and puts the boundary
at z=10.20, which is 34 layers, not the 33 that `10 / 0.3 = 33.33` rounds to.

## Three defects this corpus exposed in the generator

### 1. `M104 S0 T0` — the nozzle was switched off before its own first layer

No file in the corpus contains `M104 S0`. The footer uses `M104 S30 Tn`; the header
uses `M104 S220/S230 Tn`. The generator wrote `M104 S0 T0` in the initial switch
block for single-colour jobs, which turns T0 off one line before `T0` starts
printing.

Root cause: a **second, inverted** tool-mapping implementation in the writer
(`extruder_count - glue`) disagreed with `Params.tool_no` (`glue - 1`). A glue-1
job resolved to T1, so the "is T0 active" test failed and the code cooled it.

Fixed: the writer delegates to `Params.tool_no`, and the line is always
`M104 S<iT0> T0` like the vendor. Guarded by selftest T11 and T12.

### 2. Band boundaries and layer count use floor+1, not ceil

A 10 mm band became 33 layers and ZCCAD makes 34, so the rule was changed to
`ceil`. A real 30 mm export later showed that was still wrong: ZCCAD's rule is
`floor(H/h) + 1`, which for 10 mm also gives 34 but for an exact 30 mm gives 101
rather than 100.

Fixed in `params._layers_for`, with the cumulative-height correction in
`band_plan` (the 10+30 mm boundary is layer 134, which only a cumulative formula
reproduces). Guarded by selftest T4.

### 3. Nothing checked the instruction vocabulary

The existing gates compared *values*. They could not see an instruction the
firmware has never received. `dialect_check.py` closes that: mask the coordinates,
keep the command numbers, and require the test file's line shapes to be a subset of
the corpus's 36.

## Result after the fixes

```
$ dialect_check.py --corpus work/corpus --test TEST1..TEST4
TEST1_A_50mm_ref.gcode     novel 0   E/mm 0.134285714286   CONFORMS
TEST2_BALI_40mm.gcode      novel 0   E/mm 0.134285714284   CONFORMS
TEST3_WELCOME_30mm.gcode   novel 0   E/mm 0.134285714285   CONFORMS
TEST4_BALI_10mm_smoke.gcode novel 0  E/mm 0.134285714284   CONFORMS
4/4 test files conform
```

And the 3-tool zone map now matches the vendor export layer for layer:

| | bottom band | boundary | middle band | boundary | top band |
|---|---|---|---|---|---|
| `TES .gcode` (vendor) | T2 → 10.20 | 10.20 | T1 → 40.20 | 40.20 | T2 → 50.10 |
| generated (`--bands 10,30,10 --glue 3,2,3`) | T2 → 10.20 | 10.20 | T1 → 40.20 | 40.20 | T2 → 50.10 |
