# G-code artifact manifest

## Download

The four files are published as **Release assets**, not as repository files: the
largest is 65 MB, which bloats git history permanently. Download them here:

**<https://github.com/EfkaStudio-prd/Letter-Labs/releases/tag/v1.0-gcode>**

```
https://github.com/EfkaStudio-prd/Letter-Labs/releases/download/v1.0-gcode/TEST1_A_50mm_ref.gcode
https://github.com/EfkaStudio-prd/Letter-Labs/releases/download/v1.0-gcode/TEST2_BALI_40mm.gcode
https://github.com/EfkaStudio-prd/Letter-Labs/releases/download/v1.0-gcode/TEST3_WELCOME_30mm.gcode
https://github.com/EfkaStudio-prd/Letter-Labs/releases/download/v1.0-gcode/TEST4_BALI_10mm_smoke.gcode
https://github.com/EfkaStudio-prd/Letter-Labs/releases/download/v1.0-gcode/SHA256SUMS.txt
```

Upload integrity was confirmed by comparing each local file against the digest
GitHub computes server-side: all four matched exactly.

## Identity

Each file is pinned here by SHA-256, so any copy on disk can be proven to be the
validated one.

| File | Bytes | SHA-256 | Job |
|---|---|---|---|
| `TEST1_A_50mm_ref.gcode` | 8,950,246 | `e4b6fd0eb4c07245b568c59b56efe5fc961db60c1182756484ca47c45c6c197e` | vendor cross-check, letter A, 50 mm, 2-colour |
| `TEST2_BALI_40mm.gcode` | 68,688,642 | `bddc810c4f47f92438b365e4f08bc77986be535c1bf065438d65c4ebd48bc93e` | **production job**, Bali Kita Kita logo, 40 mm, 1-colour, 3 mm pocket |
| `TEST3_WELCOME_30mm.gcode` | 25,547,111 | `8f8283331b0d0972599f9d6a26f3e15a2beaf0b75e39cbafd5f6b7b12d8dada5` | 2-colour band test, 30 mm |
| `TEST4_BALI_10mm_smoke.gcode` | 14,882,290 | `30661ad627848a2fba31e05540149bc125a317084d7740a9ce6353cd0d911060` | **print this first**, 10 mm machine proof |

### Revision 2

These files were regenerated after the corpus audit found three defects (see
`docs/DIALECT_CORPUS.md`): a nozzle was cooled with `M104 S0` before its own first
layer, band boundaries rounded instead of rounded up, and nothing checked the
instruction vocabulary. Layer counts therefore changed for heights that are not a
whole multiple of 0.3 mm — a 40 mm job is now 134 layers to z=40.20, not 133 to
z=39.90. **Hash values from revision 1 no longer apply.**

Verify a local copy:

```bash
python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" TEST2_BALI_40mm.gcode
```

---

## Simulated results

Numbers produced by `gcode3d.py` re-parsing the emitted file, not from the
generator's internal model.

| File | Layers | Size (mm) | Tools | Print time | Filament |
|---|---|---|---|---|---|
| `TEST1_A_50mm_ref` | 167 | 109.8 x 125.6 x 49.8 | T0, T1 | 43 min | 21 m |
| `TEST2_BALI_40mm` | 134 | 325.7 x 196.4 x 40.2 | T0 | 336 min | 162 m |
| `TEST3_WELCOME_30mm` | 100 | 327.9 x 173.8 x 29.7 | T0, T1 | 201 min | 97 m |
| `TEST4_BALI_10mm_smoke` | 34 | 325.7 x 196.4 x 10.2 | T0 | 71 min | 34 m |

---

## Reproducing them

```bash
# TEST1 - vendor cross-check
python .qoder/skills/letterlab-skill/scripts/letterlab.py job \
  --dxf .qoder/skills/letterlab-skill/fixtures/a_source.dxf \
  --out work/TEST1_A_50mm_ref.gcode --ref A_SAMPLE_50mm.gcode \
  --height 50 --layer 0.3 --width 1.2 --passes 1 --spacing 0.8 \
  --bands 10,30,10 --glue 1,2,1 --speed 3600 --first-speed 1800 \
  --preview work/TEST1_A_50mm_ref_3d.png

# TEST2 - production job, 3 mm acrylic pocket
python .qoder/skills/letterlab-skill/scripts/letterlab.py job \
  --dxf "Tes 3d print+machine Layout.dxf" \
  --out work/TEST2_BALI_40mm.gcode \
  --height 40 --layer 0.3 --width 1.2 --passes 1 --spacing 0.8 \
  --bands 40 --glue 1 \
  --seat-w 3.2 --seat-depth 3 --seat-land 2 --seat-ramp 10 \
  --max-area 100000 --place 459.82,27.38 \
  --speed 3600 --first-speed 1800 \
  --preview work/TEST2_BALI_40mm_3d.png

# TEST3 - colour bands
python .qoder/skills/letterlab-skill/scripts/letterlab.py job \
  --dxf "Welcome (1).dxf" --out work/TEST3_WELCOME_30mm.gcode \
  --height 30 --layer 0.3 --width 1.2 --passes 1 --spacing 0.8 \
  --bands 10,20 --glue 1,2 --min-area 2 --place 240,300 \
  --speed 3600 --first-speed 1800 \
  --preview work/TEST3_WELCOME_30mm_3d.png

# TEST4 - machine smoke test, no pocket
python .qoder/skills/letterlab-skill/scripts/letterlab.py job \
  --dxf "Tes 3d print+machine Layout.dxf" \
  --out work/TEST4_BALI_10mm_smoke.gcode \
  --height 10 --layer 0.3 --width 1.2 --passes 1 --spacing 0.8 \
  --bands 10 --glue 1 --max-area 100000 --place 459.82,27.38 \
  --speed 3600 --first-speed 1800 \
  --preview work/TEST4_BALI_10mm_smoke_3d.png
```

Exact byte identity on re-run is not guaranteed: the DXF reader's spline
flattening is deterministic, but vendor INI values change between sessions. Use
the ring-count audit, not the file hash, to decide whether two runs are
equivalent.
