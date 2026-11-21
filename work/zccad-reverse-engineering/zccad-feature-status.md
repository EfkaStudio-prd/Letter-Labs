# ZCCAD feature inventory and evidence status

Date: 2026-11-18. Companion field-level inventory: `zccad-parameter-map.csv` (230 INI key rows from live `S528/GcodePara.ini`). **Values in that CSV are observed runtime settings only, not defaults or recommended template values.** Existing dirty INI changes may be the user's current experiment. Original field spellings, including vendor typos, are preserved.

## Status meanings

- **VERIFIED**: behavior matched against a vendor export with matching geometry/parameters or exact source output corroborated by sample.
- **INFERRED**: decompiled algorithm/model or UI/INI implies the behavior, but matching output/physical result not established.
- **UNKNOWN**: competing evidence or no reliable mapping/value; do not pick a silent default.
- **UNSUPPORTED**: current independent `work/lettergcode` generator does not implement it.
- **PARTIAL**: named subset is verified; other modes/branches are not.

## Features

| Feature / original section | User-facing label candidate | Evidence status | Current independent engine | UX implication |
|---|---|---|---|---|
| `[letterShell]` | Letter Shell | PARTIAL | Straight DXF outlines, layer height/height, width/pass spacing, pre-side frame are implemented. Bevel/top taper remains a documented gap; pins/joints and some line modes not modeled. | Group basic shell controls; hide/disable unimplemented shape modes with a reason. Never imply all “letter type” values are supported. |
| `[colorControl]` | Color Switch / Material Zones | PARTIAL | Heights are mm converted to layers; zone plan and `g-1 -> Tn` are modeled and tested. Physical nozzle labels are not confirmed. Nozzle-offset/multi-nozzle modes not reproduced. | Display per-zone height and tool; identify T numbers, require verified machine map before multi-color production. |
| `[footStep]` | Footstep / Pangkon | PARTIAL/UNVERIFIED | Current generator has separate top/bottom acrylic-seat/pocket features; not a proven reproduction of all seven vendor `footStep` slots and output rules. | Do not map the UI controls to seat implementation as if same; keep experimental until matched G-code/print. |
| `[preventCurl]` | Prevent Curl | PARTIAL | Vendor pre-side frame (`letterShell.dbOffsetPreSide`, `iNumPreSide`) exists; preventCurl pressure/skirt, grid, V-curl and mini-rim sections are unsupported. | Separate “start frame” from “anti-curl skirt”; leave unsupported controls disabled, not no-op. |
| `[connectWord]` | Connect Letter | UNSUPPORTED | No equivalent in current generator. | Keep visible for feature parity inventory, disabled until implemented and verified. |
| `[surroundSide]` | Surround Side / Top Lip | PARTIAL | `dbHeight1` hem/fill-stop behavior is modeled; flat/sharp lip, surrounding geometry, board modes are not fully modeled. | Separate verified hem function from unsupported lip/board geometry. |
| `[bottomFill]` | Bottom Fill | UNSUPPORTED | No equivalent. | Don't expose active UI control yet. |
| `[panelFill]` | Panel Fill | UNSUPPORTED | No equivalent. | Don't expose active UI control yet. |
| `[ThousandColor]` | Thousand Color / Gradient | UNSUPPORTED | No equivalent. | Disabled. |
| `[surfaceCalculate]` | Light / Bottom / Glue Surface | UNSUPPORTED | No equivalent. | Disabled; needs separate evidence. |
| `[boardCompensate]` | Board Compensation | UNSUPPORTED | No equivalent. | Disabled; requires machine calibration evidence. |
| `[baseplateGet]` | Baseplate DXF | UNSUPPORTED | No equivalent. | Disabled; do not accept path strings that point to absent vendor-specific drives. |
| `[printf3D_base]` | Machine & Output | PARTIAL | A subset of start/end, travel, first-layer/work speeds, temperature, park, etc. is represented. Machine selectors and full interactions aren't implemented. | Profile-specific controls; show units. Never infer one universal machine value. |
| `[gluePara]` | Extrusion & Tool Change | PARTIAL | Filament/bead E model, retract, selected tool-change/purge behaviors are represented. Near/far compensation and every branch not verified. | Advanced group; calibrated machine profile and tool mapping needed. |

## Directly verified implementation facts

- Matching golden pair in existing LetterLab notes: `fixtures/a_golden.dxf` → `A_SAMPLE_50mm.gcode`, 50 mm shell, 0.3 mm layer, 10/30/10 mm bands, glue index 1/2/1, width 1.2, one inset pass.
- Existing analysis reports its eight dialect gates matched for the paired reference; separate bevel/top band geometry still differs. Do not generalize the golden result to all modes.
- E/mm formula and sample value are in `reference/dialect.md`; selftest `--quick` passed 10/10 local checks, but skipped slow T6/T7 golden compare.
- Some values disagree across the generic manual/template, tracked machine profiles and real G-code. Use paired evidence; do not treat current `S528/GcodePara.ini` values as product defaults.

## Unknowns that block production behavior

1. Physical UI extruder number ↔ actual filament/nozzle labels (repo explicitly says unconfirmed); physical confirmation needed.
2. Default UI values vs profile-specific saved values; live INI is user-edited and must not be copied as canonical preset.
3. Full behavior/shape consequences for enabled Footstep, Prevent Curl, Connect Letter, Panel Fill, Baseplate, ThousandColor, surface/board compensation.
4. Bevel/taper emission count rule; only one relevant vendor example and it is not explained well enough to fit safely.
5. STEP/STL letter projection rule; no vendor evidence establishes which plane or what to do with counters, bevels or non-uniform solids.
6. G-code startup/purge branches for one, two or three tools and all `bNozzleUsed` combinations; compare matching corpus before implementing.

## UI name rule

Friendly label is presentation only; keep exact original section/key as stable `source_id`. Example: `Tinggi shell` (`dbHeightShell`, `letterShell`) — range/step only when evidenced; exact mm input always. Similar control values are grouped by feature tab in `zccad-parameter-map.csv`; the table intentionally does not invent explanatory ranges/defaults.
