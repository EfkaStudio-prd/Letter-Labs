# Letter-Labs

G-code generator for **3D printed letter shells** (*huruf timbul*) that reproduces
the exact output dialect of **ZCCAD** (`3D Print Software S528`), the software
shipped with Taesin / DongGuan ZhenCai letter printers.

The point is to produce a print-ready `.gcode` **without opening the vendor
application**, so a job can be driven from a script, a web app, or an agent.

Engine: pure Python standard library. No pip installs, no numpy, no shapely.

---

## Download the G-code

The generated files are published as release assets:

**<https://github.com/EfkaStudio-prd/Letter-Labs/releases/tag/v1.0-gcode>**

| File | Job | Layers | Time | Filament |
|---|---|---|---|---|
| `TEST4_BALI_10mm_smoke.gcode` | machine proof, 10 mm — **print this first** | 34 | 70 min | 34 m |
| `TEST2_BALI_40mm.gcode` | production job, 40 mm, 3 mm acrylic pocket | 134 | 335 min | 162 m |
| `TEST1_A_50mm_ref.gcode` | vendor cross-check, 2-colour | 167 | 43 min | 21 m |
| `TEST3_WELCOME_30mm.gcode` | 2-colour band test | 101 | 202 min | 97 m |
| `SHA256SUMS.txt` | checksums for all of the above | — | — | — |

Integrity is pinned twice: in `SHA256SUMS.txt` on the release, and in
[`artifacts/MANIFEST.md`](artifacts/MANIFEST.md) in the repo.

---

## Status

| Area | State |
|---|---|
| G-code dialect vs vendor export | **Verified** — 8/8 structural gates, 0 line-shape deviation |
| Geometry vs vendor export | **Verified** for straight-edge letters (0 ring-count mismatches over 99 layer probes) |
| Acrylic pocket (pangkon) | **Verified** from emitted G-code |
| DXF input | LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE, ELLIPSE, SPLINE (NURBS), INSERT of BLOCK |
| Bevel / incline letters | **Not implemented** (see [Scope limits](#scope-limits)) |
| Physical machine run | **Vendor dialect confirmed** on hardware; a LetterLab-generated file has not yet been printed — see [docs/PHYSICAL_RUN.md](docs/PHYSICAL_RUN.md) |

---

## Quick start

```bash
# 0. pre-flight: what will actually become toolpath?
python .qoder/skills/letterlab-skill/scripts/dxfprobe.py LETTER.dxf

# 1. full job: generate -> validate -> audit -> 3D preview
python .qoder/skills/letterlab-skill/scripts/letterlab.py job \
  --dxf .qoder/skills/letterlab-skill/fixtures/a_source.dxf \
  --out out/A_50mm.gcode \
  --ref out/A_SAMPLE_50mm.gcode \
  --height 50 --layer 0.3 --width 1.2 --passes 1 --spacing 0.8 \
  --bands 10,30,10 --glue 1,2,1 \
  --speed 3600 --first-speed 1800 \
  --preview out/A_50mm_3d.png

# 2. engine self-check (10 independent tests)
python .qoder/skills/letterlab-skill/scripts/selftest.py
```

A vendor reference file is only needed as a **comparison target**. The generator
never calls the vendor software.

### Running the tests in a fresh clone

`selftest.py` runs 8 of its 10 checks with nothing but this repo. T6 and T7 need a
vendor export plus `S528/GcodePara.ini`, which are **not** distributed here, so
they report `SKIP` and the summary states plainly that the dialect is not proven
by that run. Drop a vendor `.gcode` next to `work/` and the matching
`S528/GcodePara.ini` in place and they run for real.

```
8/8 checks passed
SKIPPED (no vendor artifact to compare against): T6 golden dialect gates, T7 per-layer ring count
  -> the dialect is NOT proven by this run.
```

A `SKIP` is deliberately not a pass. Do not read a green run as dialect proof
unless T6 and T7 actually executed.

---

## Golden rule

A `.gcode` is **not print-ready** until all four pass:

1. `selftest.py` reports `ALL CHECKS PASS`
2. `dialect_check.py` reports `CONFORMS` — every line shape already exists in a
   real vendor export
3. `validate_gcode.py` reports `ALL GATES PASS` against a vendor export built with
   the same parameters
4. The 3D preview has been looked at, and the part / colour bands / layer count
   are what was asked for

Structural gates prove the *dialect*. Only the preview and the per-layer audit
prove the *geometry*.

---

## Repository layout

```
.qoder/skills/letterlab-skill/     the skill
  SKILL.md                         workflow + the three gates
  scripts/letterlab.py             orchestrator: job | generate | validate | audit | preview
  scripts/gcode3d.py               G-code -> 3D bead simulation -> PNG
  scripts/labcheck.py              per-layer ring count / path length diff
  scripts/validate_gcode.py        structural dialect gates
  scripts/dxfprobe.py              pre-flight DXF inspection
  scripts/dialect_check.py         line-vocabulary subset vs a vendor corpus
  scripts/tool_zones.py            which T covers which Z millimetres
  scripts/selftest.py              12-test engine verification
  reference/dialect.md             exact G-code format
  reference/parameters.md          every GcodePara.ini section -> UI tab -> effect
  reference/findings.md            verified facts, open gaps, golden test recipe
  fixtures/a_source.dxf            letter "A" recovered from a vendor export

work/lettergcode/                  the engine
  params.py  dxf.py  geom.py  gcode.py  job.py  cli.py

docs/
  VALIDATION_REPORT.md             the measured evidence
  DIALECT_CORPUS.md                the dialect derived from 14 real exports
  PHYSICAL_RUN.md                  a vendor export and its real printed part
  ZCCAD_CRASH.md                   why the vendor app force-closes on `get path`
  MANUAL_MAP.md                    vendor manual -> field -> INI key -> CLI flag
  PRODUCTION_CHECKLIST.md          pre-flight list before sending to the machine

artifacts/
  *.png                            3D simulations of each validated job
  physical_run/*.jpg               photographs of a confirmed print
  MANIFEST.md                      SHA-256 of the generated G-code
```

`work/lettergcode/` sits at that exact path on purpose: the skill scripts locate
the engine by walking up from their own directory until they find
`work/lettergcode`. Moving it breaks the resolution.

---

## What each script proves

| Gate | Proves |
|---|---|
| `E/mm` to 1e-6 | extrusion calibration matches; no under/over-extrusion |
| `print Z ladder` | every layer height and the total height |
| `lift Z set` | travel heights, so the head cannot drag across the part |
| `tools` | the `T` sequence, so colour changes land where intended |
| `markers` | the vendor's block structure (`;calculatePreSide`, `;start printf`) |
| `feedrate set` | only speeds the machine profile actually uses |

`labcheck.py` then answers *"how many rings does each layer print, and where do we
differ from the vendor"* — the check that catches missing geometry, which none of
the structural gates can see.

---

## Scope limits

- **Bevel / incline letters are not modelled.** The vendor's top-band wall taper
  is driven by `dbWidthSide` (the UI's *oblique width*), so it only appears on
  incline letters. A straight-edge letter has oblique width 0 and ZCCAD emits no
  extra passes either — straight jobs are unaffected. Do not add rings to them.
- **`--seat-depth` is the acrylic thickness**, not a free parameter. A 3 mm sheet
  means `--seat-depth 3`, which puts the pocket shoulder at `height - 3`. Verify
  by ring count, not by the report.
- **`T0`/`T1` to physical colour is confirmed for one machine setup**: slot 1 ->
  `T0` = transparent, slot 2 -> `T1` = white, slot 3 -> `T2` = transparent, derived
  from a printed part and its G-code. Re-confirm if the spools are reloaded in a
  different order.

---

## Provenance

Dialect and parameter names were recovered from the shipped vendor artifacts:
`S528/GcodePara.ini`, `S528/*.gcode` exports, the `S528/special_shape/` library,
`work/manual.txt` (the factory manual), and the IL of `OutPutG.dll::OutKF`
(`writeGcodeHead`, `writeGcodeTear`, `writeGcode_G00`, `thichnessProcess`,
`calculatePreSide`, `updateCoor`).

No vendor binary, DLL, licence dongle file, or vendor G-code export is
redistributed in this repository. Only our own source, our own documentation, and
trivial test geometry are committed.

Field names from the vendor's INI and the managed stack traces quoted in
`docs/ZCCAD_CRASH.md` are included as interface documentation — they are what any
operator can read out of the shipped `GcodePara.ini` and the Windows application
event log.
