# T25RC — G-code settings that pass (validated)

Reference settings for the two letter-T jobs that print correctly on the Iguana
800. Every value here comes from `work/lettergcode/t25c.py` (dialect REV B) and
is pinned by the SHA-256 of the emitted file, so a local copy can be proven
identical to the one this document describes.

Both `.gcode` files live in `artifacts/` and are tracked by git (an explicit
exception to the `*.gcode` ignore rule, added in this revision). Total added
weight is 415 KB, which does not bloat history the way the 65 MB release assets
would.

---

## 1. Machine and material

| Setting | Value |
|---|---|
| Printer | Iguana 800 (Marlin), bed 800 x 800, build height 65 mm |
| Nozzles | 1.2 mm, brass |
| Bed | unheated (`M140 S0`), no adhesion aid |
| Material | PLA 1.75 mm |
| Nozzle temp | 230 °C, held on every tool that prints |
| Fan | 100 % (`M106 S255`) from layer 1 |
| Flow constant | `K_WALL = 21.423382 / 189.6408 = 0.112976...` mm filament per mm of deposit |
| E reset | `G92 E0` before every block; E is never trusted across blocks |
| Tool change | unload 85 mm at F1800, `T[n]`, reload 85 mm at F1500 |

Filament cross-section used for the gram figures below:
`π × (1.75/2)² = 2.405 mm²`, density 1.24 g/cm³.

---

## 2. Geometry constants (shared by both jobs)

| Constant | Value | Meaning |
|---|---|---|
| `LH` | 0.25 mm | layer height |
| `SPACING` | 1.0478 mm | nominal row spacing |
| `FILL_INSET` | 1.3 mm | face fill inset from the outline |
| `WALL_INSETS` | 0.6 / 1.4 / 2.4 / 3.4 / 4.4 / 5.4 | wall loop insets, loop 0 outermost |
| `FLANGE_LAYERS` | 3 | front flange, 0.75 mm proud of the face side |
| `STEP_LAYERS` | 3 | layers per shelf step |
| `RIM_LAYERS` | 32 | 8.0 mm rebate above the shelf |
| `LEAD_LOOP` | 3.5 mm | anchor → seam on loop paths |
| `LEAD_FILL` | 3.0 mm | along the first fill row |
| `WIPE_FILL` | 2.0 mm | wipe back along the last fill row |
| `LIFT` | 0.6 mm | travel clearance above layer Z |
| `RETRACT` | 3.0 mm | |
| `PRIME_STD` / `PRIME_BIG` | 0.100 / 0.300 mm | |
| Purge box | (378, 200) → (422, 240) | outside the letter |
| `PAD_LAYERS` | 8 | purge pad ring layers, printed with the face |
| `RING_INSETS` | 0.0 / 1.5 / 3.0 | three concentric purge rings |
| Bed centre | (400, 400) | |
| Expected bbox | 314.267, 275.831 → 485.733, 524.169 | |
| Expected stem | 64.925 mm wide | |

### Feedrates (mm/min)

| Key | Value | Used for |
|---|---|---|
| `F_TRAVEL` | 12000 | travel |
| `F_WALL` | 2100 | walls |
| `F_FACEWALL` | 1890 | face perimeter |
| `F_FILL` | 1680 | face fill |
| `F_LEAD` / `F_WIPE` | 840 / 1800 | lead-in, wipe |
| `F_RETRACT` / `F_RECOVER` | 1800 / 4800 | |
| `F_PRIME` | 60 | prime line |
| `F_PURGE` | 1680 | purge rings |
| `F_LOAD` / `F_UNLOAD` | 1500 / 1800 | filament load |

---

## 3. Job T1 — walls only, 25 mm

**Purpose:** the wall/pangkon shell on its own, single colour, so the clear
letter can be checked before the face and the second colour enter the picture.

| Item | Value |
|---|---|
| Source DXF | `T 1.dxf` |
| Output | `artifacts/T1_walls_only_25mm.gcode` |
| Layers | 100 (Z 0.250 → 25.000) |
| Tool | **T2 only** (UI slot 3 = CLEAR PLA) |
| Colour changes | none, no purge box |
| Start-up | direct `T2` load, `T0`/`T1` may be empty |
| Bytes | 127 394 |
| Lines | 4 076 |
| SHA-256 | `95536c95ff2c753389fba19f0514f40778302e4e7f96f60d7f95622261621442` |
| Filament deposited | **21.88 m / 65.3 g** |
| Purge pad | 0.39 m |

### Layer plan

| Layers | Role | Loops (insets) |
|---|---|---|
| 1–3 | `WALL_LEDGE` (front flange) | 2, 1, 0 |
| 4–56 | `WALL` | 1, 0 |
| 57–68 | `WALL_LEDGE` (4-step shelf ladder) | deepest = 2+step, down to 0 |
| 69–100 | `WALL_RIM` (8 mm rebate) | 1, 0 |

Shelf floor at Z = (100 − 32) × 0.25 = **17.00 mm**.

---

## 4. Job T2 — face closed, 27 mm, two colours

**Purpose:** the full letter. Black face, clear body, single run.

| Item | Value |
|---|---|
| Source DXF | `T2.dxf` |
| Output | `artifacts/T2_face_closed_27mm.gcode` |
| Layers | 108 (Z 0.250 → 27.000) |
| Face | 8 layers × 0.25 = **2.0 mm**, solid, light-tight, serpentine 0/90 |
| Tools | **T0 = BLACK PLA** (UI slot 1), **T2 = CLEAR PLA** (UI slot 3) |
| Bytes | 288 013 |
| Lines | 8 236 |
| SHA-256 | `c29a3649210415549b4751fc0e72bcd3b66e67be3187c9de1e38d06e5a9c3239` |
| Filament deposited | **42.62 m / 127.1 g** total |
| — T0 black | 20.69 m / 61.7 g |
| — T2 clear | 21.93 m / 65.4 g |
| Purge (pad + rings) | 0.67 m |

### Layer plan

| Layers | Role |
|---|---|
| 1–8 | `FACE_BLACK` — `FACE_WALL` loops + fill + purge-pad rings |
| 9 (Z 2.250) | colour change `T0` → `T2`, internal purge rings on the pad |
| 10–11 | `WALL_LEDGE` front flange |
| 12–64 | `WALL` plain |
| 65–76 | `WALL_LEDGE` 4-step shelf ladder |
| 77–108 | `WALL_RIM` 8 mm rebate |

Shelf floor at Z = (108 − 32) × 0.25 = **19.00 mm**.

Machine sequence at start: `T0` unload → `T1` load → `T1` unload → `T0` load,
i.e. the two empty slots are primed out of the way before the first deposition.

---

## 5. Verified totals

| Job | Layers | Z max | Filament | PLA mass | Tool split |
|---|---|---|---|---|---|
| T1 walls only | 100 | 25.00 mm | 21.88 m | 65.3 g | T2 100 % |
| T2 face closed | 108 | 27.00 mm | 42.62 m | 127.1 g | T0 48.5 % / T2 51.5 % |

Both figures are measured from the emitted file by replaying `E` deltas with
`G92 E0` boundaries honoured — not from the generator's internal model.

> **Note on the OrcaSlicer number.** The OrcaSlicer screenshot in this folder
> (`orcaslicer_filament_usage.png`) reports 86.26 m / 257.26 g because that run
> used the *0.40 mm General 3D* process with 15 % sparse infill and a 0.40 mm
> layer. It is a different process, not a contradiction of the 42.62 m above.
> For the channel-letter job use the `0.30mm Channel Letter @Iguana` preset,
> which is tracked in `work/presets/orcaslicer/`.

---

## 6. Reproducing

The DXFs the generator reads are archived in this same folder, so the job is
self-contained — no dependency on the original download directory:

```bash
python work/lettergcode/t25c.py --dxf-dir artifacts/T25RC
```

Writes both files into `artifacts/`. Verify:

```bash
python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" artifacts/T1_walls_only_25mm.gcode
python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" artifacts/T2_face_closed_27mm.gcode
```

Expected: the two hashes in the tables above.

**Verified 2026-11-18:** a clean regeneration into an empty directory from
`artifacts/T25RC/T 1.dxf` and `artifacts/T25RC/T2.dxf` produced both files
**byte-identical** to the committed ones — same size, same SHA-256. The output is
deterministic, so the hash is a valid identity check for this job (unlike the
older vendor-dialect jobs, which depend on session-specific INI values).

---

## 7. Status

| Check | Result |
|---|---|
| Physical print, T1 walls only | **passes** — user-confirmed |
| Physical print, T2 face closed | **passes** — user-confirmed |
| Byte-identical in `T Cetak/`, repo, and clean re-run | yes — all three agree |
| Dialect gates T28–T34 | skipped in CI: needs `D:\T25RC.gcode` vendor export + job DXFs |

