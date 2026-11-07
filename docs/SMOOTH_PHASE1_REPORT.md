# Smooth profile — Fase 1 report (brief SMOOTH_ZCCAD_BRIEF_R0 §8, §9)

Status: **UNVERIFIED** — every file below has passed all file-level gates
(selftest T17–T26 + dialect check), but **no coupon has been printed on the
machine yet**. Nothing in this profile is production-ready until Dwi's physical
coupons pass (§ "Tugas operator"). This report is the Fase-1 record; the spiral
coupons C2/C4 and the spiral gate itself belong to Fase 2 and are **not**
included.

Branch `feat/smooth-profile` · generated 2026-11-07 · selftest **26/26
ALL CHECKS PASS** (full run, T6 golden rc=0, T7 99 probes 0 mismatches — the
vendor-exact branch is untouched).

## Coupon list

The physical gate plan (brief §9) is one file per coupon, 1 colour `T0`,
height 20 mm, layer 0.3, 1 wall, ±10–20 min each:

| ID | Shape | Mode | In this report |
|---|---|---|---|
| C1 | serif I (20 × 80 mm) | smooth | file ready below |
| C2 | I | smooth + spiral | **Fase 2 — not built** |
| C3 | letter A (±80 mm, `a_golden.dxf --scale 0.8`) | smooth | file ready below |
| C4 | A | smooth + spiral | **Fase 2 — not built** |

---

## Job C1 — `coupon_C1_I_serif_20mm.gcode`

```
path    : artifacts/smooth/coupon_C1_I_serif_20mm.gcode   (28,023 bytes)
sha256  : 53e101f42d15f5110ccf91165878447e3e560d7b91001ae73a07d4a2aec44a28
command : python -m lettergcode --dxf .qoder/skills/letterlab-skill/fixtures/i_serif.dxf
          --out artifacts/smooth/coupon_C1_I_serif_20mm.gcode
          --family zccad --profile smooth --height 20 --layer 0.3 --walls 1
          --pre-passes 1 --place 40,40
```

| Property | Value |
|---|---|
| Layers (0.3 mm) | **67** (vendor rule floor(20/0.3)+1) |
| Contours × walls | 1 × 1, spacing auto 1.1356 mm |
| Work speed / nozzle | F2700 (45 mm/s) @ 230 °C |
| Path printed | 15.0 m |
| Filament (net absolute E) | 1.5 m ≈ **4.4 g PLA** |
| Stops per layer | **0** (limit 0 = kontur − 1) |
| Retractions | 0 |
| Seam | (54.0, 114.0) — the concave corner where the top serif lands on the stem; identical on all 67 layers, shift measured 0.000 mm |
| Bed bbox (plastic + pre-side frame) | x 25.1..75.0 · y 22.3..130.7 of 800×800 — margin 22.3 mm ≥ 15 |

Gate results:

| Gate | Result | Detail |
|---|---|---|
| T17 walls exact | PASS | 67 printed blocks = 1×1×67 (no vendor "+1") |
| T18 auto spacing | PASS | 1.1356 = w − h(1−π/4) |
| T19 E/mm anchor | PASS | median 0.134285714286 vs anchor, delta 2.8e−12 (≪ ±0.5 %) |
| T20 stops/layer | PASS | 0 vs limit 0 |
| T21 seam locked | PASS | shift 0.000 mm (limit 0.5) |
| T22 bed gate | PASS | margin 22.3 mm ≥ 15 |
| T23 dialect | **CONFORMS** | 26 line shapes, 0 novel; 74 markers present, 0 required missing; E/mm delta 2.8e−12; corpus `C:\Users\Pongo\Documents\G-Code`, 15 usable files |
| T24 spiral | n/a | engine refuses `--spiral` with the Phase-2 note (stub gate); the real spiral gate needs Fase 2 |
| T25 prime guard | PASS | 1 primed block, all primes follow `G92 E0`, push 3.10 mm |
| T26 speed↔temp | PASS | F2700 → 230 °C header |

Previews (regenerate with the command above; G-code itself is git-ignored):

- `artifacts/smooth/coupon_C1_I_serif_20mm_3d.png`
- `artifacts/smooth/coupon_C1_I_serif_20mm_3d.html`
- independent re-parse (`gcode3d.py`): 755 segments / 914 moves, box 50.0 × 105.55 × 19.8 mm, est. print 7.9 min, filament 1.44 m — the generator's own estimate says 11.2 min (hops, prime and layer-time floor included; the machine is the referee).

## Job C3 — `coupon_C3_A_20mm.gcode`

```
path    : artifacts/smooth/coupon_C3_A_20mm.gcode   (625,351 bytes)
sha256  : 7cc4b20637e7191cfaa338b1878cf9564d98b613bb54cb10edeb20dd8c5278fe
command : python -m lettergcode --dxf .qoder/skills/letterlab-skill/fixtures/a_golden.dxf
          --scale 0.8 --out artifacts/smooth/coupon_C3_A_20mm.gcode
          --family zccad --profile smooth --height 20 --layer 0.3 --walls 1
          --pre-passes 1 --place 40,40
```

| Property | Value |
|---|---|
| Layers (0.3 mm) | **67** |
| Contours × walls | 2 × 1 (outer + counter hole), spacing auto 1.1356 mm |
| Work speed / nozzle | F2700 (45 mm/s) @ 230 °C |
| Path printed | 24.4 m |
| Filament (net absolute E) | 3.3 m ≈ **10.0 g PLA** |
| Stops per layer | **1** (limit 1 = kontur − 1). Travel order alternates outer/inner every layer (brief 4.3) so the between-contour gap is always bridged by one wipe+retract+hop |
| Retractions | 67 (one per layer) |
| Seam | outer (82.03, 58.08), hole (72.02, 105.1) — each contour keeps its own vertex on every layer, shift 0.000 mm; the contour traversal order swaps between layers by design |
| Bed bbox | x 25.1..118.8 · y 22.3..130.7 of 800×800 — margin 22.3 mm ≥ 15 |

Gate results:

| Gate | Result | Detail |
|---|---|---|
| T17 walls exact | PASS | 134 printed blocks = 2×1×67 |
| T18 auto spacing | PASS | 1.1356 mm |
| T19 E/mm anchor | PASS | median exact vs 0.134285714286, delta 2.8e−12 |
| T20 stops/layer | PASS | 1 ≤ kontur − 1 |
| T21 seam locked | PASS | shift 0.000 mm |
| T22 bed gate | PASS | margin 22.3 mm |
| T23 dialect | **CONFORMS** | 26 line shapes, 0 novel; 141 markers, 0 missing |
| T24 spiral | n/a | stub-refused (Fase 2) |
| T25 prime guard | PASS | 68 primed blocks (layers + 1 header), push 3.10 mm, all guarded |
| T26 speed↔temp | PASS | 230 °C header |

Previews:

- `artifacts/smooth/coupon_C3_A_20mm_3d.png`
- `artifacts/smooth/coupon_C3_A_20mm_3d.html`
- independent re-parse: 12,339 segments / 13,034 moves, box 93.75 × 105.55 × 19.8 mm, est. 11.35 min, filament 3.31 m.

## Tugas operator (brief §9 — physical acceptance)

Print C1 and C3 on the Taesin/Zhencai machine, 1 colour. Confirm the spool
order for the job **before printing** (do not assume the old letter-M photo
mapping — docs/PHYSICAL_RUN.md records an unresolved slot-1 conflict: Dwi says
slot 1 = black vs doc "transparent"; the engine never encodes colour to T).

1. **C1 pass if**: seam sits in the corner without a bump/bulge ("bintil"),
   wall surface flat, wall thickness with a caliper **1.1–1.3 mm** (nominal
   1.2 mm at spacing 1.1356 with rounded caps).
2. **C3 pass if**: exactly one stop per layer (heard at the wipe+hop), no
   stringing on the outside face, and both contours keep the same seam
   position per layer.
3. Photograph front + seam close-up, measure wall thickness, then log the
   outcome in `docs/PHYSICAL_RUN.md` with both SHA-256s above.
4. If the first pass lacks plastic: raise the far shortage `+0.1` per step. If
   bumps persist: lower shortage or add coast `+0.2` (brief §9).

Only after both coupons pass may the label go **VERIFIED** and the auto
speed-class (small/large) be trusted. Until then every smooth job stays
UNVERIFIED, printed at the operator's own risk.

## Reproduce anywhere

```bash
python .qoder/skills/letterlab-skill/scripts/selftest.py   # 26/26, ALL CHECKS PASS
python -m lettergcode --dxf ... --family zccad --profile smooth --height 20 \
  --layer 0.3 --walls 1 --pre-passes 1 --place 40,40 --out coupon.gcode
python .qoder/skills/letterlab-skill/scripts/dialect_check.py \
  --corpus "$HOME/Documents/G-Code" --test coupon.gcode    # CONFORMS
python .qoder/skills/letterlab-skill/scripts/gcode3d.py coupon.gcode --out x.png   # PNG
python .qoder/skills/letterlab-skill/scripts/gcode3d.py coupon.gcode --html x.html --bed 800,800
```

The G-code files are intentionally not committed (`*.gcode` is git-ignored);
the SHA-256 values above pin the validated bytes on disk.
