---
name: letterlab-skill
description: Generate, verify and 3D-preview ZCCAD-format G-code for 3D printed letter shells (huruf timbul) from DXF outlines, without opening the ZCCAD application. Use when the user asks to make or check G-code for 3D letters, a letter shell, acrylic-pangkon/pocket seats, colour-switch bands, hem bands, or a prevent-curl frame; when converting a DXF of letters to a print-ready .gcode for the Taesin/Zhencai letter printer; or when asked whether a generated toolpath matches a vendor ZCCAD export.
---

# LetterLab

Produces `.gcode` that the Taesin / DongGuan ZhenCai letter printer accepts, by
reproducing the exact output dialect of ZCCAD ("3D Print Software S528"). The
engine is `work/lettergcode` (pure Python standard library, no pip installs).

Nothing here needs the vendor app running. A vendor export is used only as a
reference file to verify against.

## Non-negotiable rule

A `.gcode` file is **not print-ready** until all four of these pass:

1. `selftest.py` reports `ALL CHECKS PASS` — the engine itself is sound.
2. `dialect_check.py` reports `CONFORMS` — every line shape already exists in a
   real vendor export, and E/mm matches the corpus.
3. `validate_gcode.py` reports `ALL GATES PASS` against a real vendor export that
   used the same parameters.
4. The 3D preview (`gcode3d.py`) has been looked at, and the part, the colour
   bands and the layer count are what the user asked for.

If any is missing, say the output is UNVERIFIED. Never present a generated file
as ready on the strength of "it parsed". Checks 2 and 3 prove the *dialect*; only
the preview and the audit prove the *geometry*.

## Quick start

One command, all four stages:

```bash
python .qoder/skills/letterlab-skill/scripts/selftest.py        # once per session
python .qoder/skills/letterlab-skill/scripts/letterlab.py job \
  --dxf .qoder/skills/letterlab-skill/fixtures/a_golden.dxf \
  --out work/job.gcode \
  --ref A_SAMPLE_50mm.gcode \
  --preview work/job_3d.png
```

Then **read the PNG** with the Read tool and describe what it shows. The report
ends with the gate results, any taper NOTICE, and the absolute paths of both
artefacts.

## Workflow

Mirror the order ZCCAD itself forces, because parameters interact:

```
- [ ] 1. Confirm bed size and where the job sits (--place X,Y, bed is 800x800)
- [ ] 2. Get closed outlines (DXF) and check they are real letters, not noise
- [ ] 3. Set shell geometry: height, layer, bead width, wall passes, spacing
- [ ] 4. Set colour bands: --bands / --glue (zones are heights, not layer counts)
- [ ] 5. Set extras only if asked: --fill, --seat-w, --first-layer-fill
- [ ] 6. Generate, then validate + audit against a vendor reference
- [ ] 7. Render the 3D preview and inspect it
- [ ] 8. Report: file path, layers, filament length, print time, gate verdict
```

**Step 2 is where jobs silently fail.** A DXF that imports with 0 closed rings,
or that carries dimension marks next to the letters, produces an empty or
garbage toolpath. Probe it before generating:

```bash
python .qoder/skills/letterlab-skill/scripts/dxfprobe.py LETTER.dxf
```

That reports closed/open counts, real size in mm, nesting (outer vs holes),
noise candidates and whether it fits the bed. It writes nothing, so it is safe on
read-only inputs outside the workspace. Use `work/preview_dxf.py` instead when
you also want a top-view PNG.

Use `--min-area MM2` to drop dots and dimension marks, `--inside-only` to keep
only contours inside the largest outline.

## Commands

| Need | Command |
|------|---------|
| Engine self-check | `selftest.py` (add `--quick` to skip the slow golden run) |
| Inspect an input DXF | `dxfprobe.py X.dxf [--min-area 2] [--bed 800] [--json]` |
| Full job, verified | `letterlab.py job --dxf X --out Y --ref V` |
| Generate only | `letterlab.py generate --dxf X --out Y [--height 50 ...]` |
| Dialect gates | `letterlab.py validate --gcode Y --ref V` |
| Per-layer diff | `letterlab.py audit --gcode Y --ref V` |
| 3D PNG only | `letterlab.py preview --gcode Y [--width 1.2 --yaw 45 --elev 24]` |
| Numbers only | `letterlab.py preview --gcode Y --stats` |
| Who prints which Z | `tool_zones.py FILE.gcode [--zones]` |
| Is every line vendor-legal? | `dialect_check.py --corpus DIR --test FILE` |

`tool_zones.py` answers "which T covers which millimetres" from the extruding
moves only, so the header purge dance cannot mislead it. Use it to check a colour
plan before printing, and to reverse-engineer a vendor export whose physical
result is known — that is how the `UI n -> T(n-1)` mapping was confirmed against a
real printed part.

All generator flags pass through to `python -m lettergcode`; see
`reference/parameters.md` for what each one means on the machine.

## Verification, and what each gate proves

`validate_gcode.py` compares invariants that decide whether the machine prints
this correctly:

| Gate | Proves |
|------|--------|
| `E/mm` to 1e-6 | extrusion calibration matches; no under/over-extrusion |
| `print Z ladder` | every layer height and the total height |
| `lift Z set` | travel heights, so the head cannot drag across the part |
| `tools` | the T-number sequence, so colour changes happen where intended |
| `markers` | the vendor's block structure (`;calculatePreSide`, `;start printf`) |
| `feedrate set` | only speeds the machine profile actually uses |

`labcheck.py` then answers "how many rings does each layer print, and where do
we differ from the vendor". This is the check that catches missing geometry,
which the structural gates cannot see — it is what found the top-band taper.

`selftest.py` covers the engine rather than one job: INSERT transforms, the
vendor E/mm constant, band-to-layer conversion, hem depth, the golden dialect
gates, a per-layer ring regression, E-modal parsing in the simulator, and the PNG
writer. Run it once per session before trusting any output.

## 3D preview

`gcode3d.py` re-parses the emitted G-code (it does not trust the generator's
internal model) and draws each extruding move as a bead of filament: ISO, TOP
and FRONT panels. Colour = extruder, brightness = height, so a wrong colour
band or a stray layer is visible immediately. It also reports filament length
and estimated print time per nozzle, which is the "calculate before printing"
step.

Render the vendor reference and the generated file and compare the two images
side by side when the user wants proof.

## Known deviations

The generator is **not** byte-equivalent to ZCCAD on every feature. Read
`reference/findings.md` before promising a print-perfect result.

- **Bevel / incline letters are not modelled.** The vendor's top-band wall taper
  is driven by `dbWidthSide` (the UI's oblique width), so it only appears on
  incline letters. A straight-edge letter has oblique width 0 and ZCCAD emits no
  extra passes either — straight jobs are unaffected. Do not add rings to them.
- **`--seat-depth` is the acrylic thickness**, not a free parameter. A 3 mm sheet
  means `--seat-depth 3`, which puts the shoulder at `height - 3`. Confirm the
  ring count collapses back to baseline at that Z before printing.
- **T0/T1 to physical colour is unconfirmed.** Do not run a two-colour job until
  the user says which nozzle holds which filament.

## Deeper reference

- `reference/dialect.md` — the exact G-code format, transcribed from vendor exports and `OutPutG.dll`
- `reference/parameters.md` — every `GcodePara.ini` section, its UI tab, and its effect
- `reference/findings.md` — verified facts, open gaps, and how to add a golden test
