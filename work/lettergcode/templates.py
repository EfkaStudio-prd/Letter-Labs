"""Style template loader for LetterLab.

A template captures the parameters of a job that already worked - geometry,
speeds, colour bands, family and profile.  Daily work then changes only the
few important numbers (size, height, colours) instead of re-typing every
flag, and the interactive 3D preview shows the shape before anything is
printed.

A template is a flat JSON file.  Keys match CLI destinations:

    family, profile          - which emitter / machine profile to use
    height, layer            - dbHeightShell / dbHeightLayer (mm)
    width, passes, spacing   - bead width, extra wall passes, pass offset
    fill, hem                - booleans (hem false means "run fill to top")
    bands, glue              - lists of numbers, bottom up
    seat_w, seat_depth, seat_land, seat_ramp - acrylic pocket
    pre_passes, speed, first_speed, min_area, max_area
    infill, infill_pattern, solid_bottom, solid_top
    skirt_lines, skirt_gap, brim, scale
    fit_bed, multitool       - booleans

Application order: INI defaults -> template -> explicit CLI flags.  A flag
typed on the command line always wins; the template only fills holes.

Search order for `--template NAME`:
  1. NAME as a path as given
  2. <repo>/work/templates/NAME[.json]
  3. <repo>/templates/NAME[.json]
"""
from __future__ import annotations

import json
import os

#: keys a template may carry; anything else is reported, not applied
TEMPLATE_KEYS = frozenset({
    "name", "description",
    "family", "profile",
    "height", "layer", "width", "passes", "spacing",
    "fill", "hem",
    "bands", "glue",
    "seat_w", "seat_depth", "seat_land", "seat_ramp",
    "pre_passes", "speed", "first_speed",
    "min_area", "max_area",
    "infill", "infill_pattern", "solid_bottom", "solid_top",
    "skirt_lines", "skirt_gap", "brim",
    "scale", "fit_bed", "multitool",
})


def template_dirs():
    """Candidate directories, most specific first."""
    here = os.path.dirname(os.path.abspath(__file__))          # work/lettergcode
    work = os.path.dirname(here)
    repo = os.path.dirname(work)
    return [os.path.join(work, "templates"),
            os.path.join(repo, "templates")]


def find_template(name_or_path):
    cand = [name_or_path]
    for d in template_dirs():
        cand.append(os.path.join(d, name_or_path))
        if not str(name_or_path).lower().endswith(".json"):
            cand.append(os.path.join(d, str(name_or_path) + ".json"))
    seen = set()
    for c in cand:
        c = os.path.abspath(c)
        if c in seen:
            continue
        seen.add(c)
        if os.path.exists(c):
            return c
    return None


def load_template(name_or_path):
    """Return (data, path) for a template.  Unknown keys warn, never crash."""
    path = find_template(name_or_path)
    if path is None:
        raise SystemExit(
            "template %r not found; looked in %s"
            % (name_or_path, " ; ".join(template_dirs())))
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise SystemExit("template %s unreadable: %s" % (path, exc))
    if not isinstance(data, dict):
        raise SystemExit("template %s is not a JSON object" % path)
    bad = [k for k in data if k not in TEMPLATE_KEYS]
    if bad:
        print("template %s: ignoring unknown key(s): %s"
              % (os.path.basename(path), ", ".join(sorted(bad))))
    return data, path


def apply_template(args_ns, tpl):
    """Fill unset members of a parsed argparse namespace from `tpl`.

    Explicit CLI flags keep their values - only holes are filled.  Boolean
    store_true flags move only upward (false -> true); a template cannot
    undo a flag the operator typed.
    """
    holed = ("height", "layer", "width", "passes", "spacing",
             "speed", "first_speed", "pre_passes",
             "seat_w", "seat_depth", "seat_land", "seat_ramp",
             "min_area", "max_area",
             "infill", "infill_pattern", "solid_bottom", "solid_top",
             "skirt_lines", "skirt_gap", "brim",
             "scale", "profile", "family",
             "bands", "glue")
    for key in holed:
        if key in tpl and getattr(args_ns, key, None) is None:
            setattr(args_ns, key, tpl[key])
    # numbers can arrive as JSON numbers; bands/glue lists become CLI strings
    if isinstance(getattr(args_ns, "bands", None), (list, tuple)):
        args_ns.bands = ",".join(str(v) for v in args_ns.bands)
    if isinstance(getattr(args_ns, "glue", None), (list, tuple)):
        args_ns.glue = ",".join(str(int(v)) for v in args_ns.glue)
    for flag_key, dest in (("fill", "fill"), ("fit_bed", "fit_bed")):
        if flag_key in tpl and tpl[flag_key]:
            setattr(args_ns, dest, True)
    # multitool: only move off -> on template-driven; a typed --no-multitool
    # always wins (store_true default cannot be told apart, so False wins)
    if "multitool" in tpl and not getattr(args_ns, "no_multitool", False):
        args_ns.no_multitool = not bool(tpl["multitool"])
    if "hem" in tpl and not tpl["hem"]:
        args_ns.no_hem = True
