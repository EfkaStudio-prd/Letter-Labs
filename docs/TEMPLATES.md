# Style templates — base parameters per job style

A template captures the parameter set of a **job that already worked**: geometry
kind, wall passes, colour bands, seat/pangkon numbers, family and profile.
Daily work then changes only a few important values (size, height, colours)
instead of retyping every flag — and the interactive 3D preview
(`letterlab.py ... --html viewer.html`) shows the shape before anything runs.

## Format & lookup

Flat JSON, one file per style, keys named after CLI destinations
(`TEMPLATE_KEYS` in `work/lettergcode/templates.py`).  Lookup for
`--template NAME` scans in order:

1. `NAME` as a path as given
2. `<repo>/work/templates/NAME[.json]`
3. `<repo>/templates/NAME[.json]`

Unknown keys print a warning and are ignored; load errors abort the job.

**Application order: INI defaults → template → explicit CLI flags.**  A flag
typed on the command line always wins; the template only fills holes.  Boolean
store_true flags only ever move false→true, so a template cannot undo an
operator's typed `--no-hem`.  The multitool knob is a documented exception:
`multitool: false` sets `--no-multitool` unless the operator typed it too.

## Shipped templates (`work/templates/`)

| file | style | family-aware | notes |
|---|---|---|---|
| `ring_500_h80_pangkon.json` | cincin/pangkon 500 mm, dinding 80 mm, acrylic pocket on top | zccad & universal | from the verified BKK_C500 circle job; `--fit-bed` recommended on a 256 mm bed |
| `letter_block_40.json` | plain blocky letter 40 mm | both | good baseline for `A`-class glyphs |
| `coupon_h8_shelf.json` | test coupon h 8 mm, 3-line walls, 2 passes | zccad | C500 doc LANGKAH 1 numbers; walls+solid only — the template engine has no bottom-shelf, the TOP pocket is the only seat it models |
| `welcome_2band_30mm.json` | WELCOME 30 mm, two colour bands 15+15 | zccad | glue `[1,2]` pixel bands |
| `demo_small.json` | 20 mm demo, single colour | universal | pins `glue: [1]` so the vendor 2-band plan cannot leak in |

Keep `REFERENCE_GCODE_NOTES.md` next to them: it parses the three successful
hardware prints (machine settings, style tiers, the K-letter base sample) and
is the source of the proven numbers quoted in
[`docs/UNIVERSAL.md`](UNIVERSAL.md).

## Rules of thumb

- A template **without a `glue` key inherits the vendor two-band plan** —
  single-colour templates MUST pin `glue: [1]`, otherwise the job will try to
  swap nozzles on a single-head machine.
- `glue` in JSON is a LIST (`[1,2,1]`), bottom-up in height bands.  The loader
  converts it to the CLI string `1,2,1`.
- `min_area`/`max_area` are mm² — a layout DXF with a machine-bed rectangle on
  it usually wants `max_area` so the rectangle is dropped, not printed.
- Test a template with `--show-params` first: the resolved wall width, band
  layers and pocket geometry are printed before any G-code is written.
