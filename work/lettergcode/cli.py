"""Command line front-end:  python -m lettergcode --dxf letter.dxf --out job.gcode"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

from .job import Job
from .params import Params
from .templates import apply_template, load_template

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INI = os.path.join(os.path.dirname(os.path.dirname(HERE)), "S528", "GcodePara.ini")


def _pair(text):
    if not text:
        return None
    try:
        a, b = text.split(",")
        return (float(a), float(b))
    except ValueError:
        raise SystemExit(f"expected X,Y but got {text!r}")


# ---------------------------------------------------------------------------
# smooth profile (--family zccad --profile smooth, SMOOTH_ZCCAD_BRIEF_R0)

def _smooth_neutralize(args, par):
    """Machine-level field values a smooth job always asserts.

    Without --bands/--glue the colour plan collapses to a single band of glue
    1 (T0): Params() defaults ask for two bands and one of the four defects
    the smooth profile exists to fix is exactly that kind of surprise.  The
    speed/temp values the engine needs live in GcodePara.ini on the shop
    machine, which never ships with the repo, so they are set explicitly.
    The equipment-level fields the vendor writer consumes directly come from
    write_head/write_initial_switch/write_pre_side, which stay byte-identical
    to the vendor-exact pipeline (only the path plan changes).
    """
    if not args.bands and not args.glue:
        par.col.iLayerNum = 1
        par.col.dbLayerHeight = [par.let.dbHeightShell]
        par.col.iLayerGlueNo = [1]
    par.pri.iSpeedIdle = 12000
    par.pri.iSpeedFirstLayer = 1800
    par.pri.dbDisClear = 30.0
    par.glu.iSpeedGlueBack = 1800


def _smooth_median(values):
    vs = sorted(values)
    return vs[len(vs) // 2] if vs else None


def _run_smooth(args, ap, out, t0, par):
    import hashlib

    from .smooth import (BED, E_ANCHOR, SmoothJob, SmoothOpts, audit_file,
                         auto_wall_spacing, e_per_mm)

    if args.stl:
        raise SystemExit("smooth covers DXF letters only in Phase 1 "
                         "(brief section 9); 3D STL imports stay with the "
                         "other families")
    if args.seat_w:
        raise SystemExit("--seat-w builds the vendor-style seat; smooth "
                         "plans the pocket itself, use --pangkon MM")
    if args.passes is not None:
        raise SystemExit("--passes keeps the vendor '+1 line' quirk; on "
                         "smooth, wall count is --walls (T17)")

    t0 = time.time()
    place = _pair(args.place)
    offset = _pair(args.offset) or (0.0, 0.0)
    opts = SmoothOpts.from_args(args)
    job = SmoothJob(par, args.dxf, opts=opts, cell=args.cell,
                    min_area=args.min_area, max_area=args.max_area,
                    scale=(args.scale or 0.0), offset=offset,
                    place=place).load()
    stats = job.render(out, pre_side=not args.no_pre_side,
                       progress=lambda i, n: print(
                           f"\r  layer {i}/{n}", end="", file=sys.stderr))
    if sys.stderr.isatty():
        print("", file=sys.stderr)
    aud = audit_file(out, preside_prime=job.preside_prime)
    n = sum(1 for _ in open(out, "r", encoding="ascii", errors="replace"))

    sha = ""
    with open(out, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()

    h = par.let.dbHeightLayer
    w = par.glue_width
    want_spacing = auto_wall_spacing(w, h)
    spacing_ok = abs(stats["spacing"] - want_spacing) < 1e-9
    ratios = [b["gain"] / b["gain_len"] for b in aud["blocks"]
              if b["gain_len"] > 50.0 and not b["preside"]]
    med_e = _smooth_median(ratios)
    e_ok = med_e is not None and abs(med_e / E_ANCHOR - 1.0) <= 0.005
    want_stops = max(0, stats["contours"] - 1)
    got_stops = (max(aud["stops_by_layer"].values())
                 if aud["stops_by_layer"] else 0)
    stops_ok = got_stops <= want_stops
    seam_shift = 0.0
    for positions in stats["seam"].values():
        if len(positions) < 2:
            continue
        pts = list(positions.values())
        for i in range(1, len(pts)):
            seam_shift = max(seam_shift, ((pts[i][0] - pts[0][0]) ** 2
                                          + (pts[i][1] - pts[0][1]) ** 2)
                             ** 0.5)
    seam_ok = seam_shift <= 0.5
    bb = aud["bbox"]
    bed_ok = bb is not None and bb[0] >= 0.0 and bb[1] >= 0.0 \
        and bb[2] <= BED[0] and bb[3] <= BED[1]
    prime_ok = aud["prime_guarded"]

    print(out)
    print(f"  sha256    : {sha}")
    print(f"  contours  : {stats['contours']}   walls: {stats['walls']}"
          f"   spacing: {stats['spacing']:.4f} mm"
          f"   E/mm: {stats['e_per_mm']:.9f}")
    print(f"  layers    : {stats['layers']}   layer: {h} mm"
          f"   work F{stats['f_work']} ({stats['f_work'] / 60.0:.0f} mm/s)"
          f"   nozzle {stats['temp']} C"
          + (f"  [{stats['speed_note']}]" if stats["speed_note"] else ""))
    fil = sum(aud["e_used"].values())
    print(f"  filament  : {fil / 1000:,.1f} m net absolute E"
          f"  (~{fil * math.pi * (1.75 / 2.0) ** 2 * 0.00124:,.1f} g PLA)")
    print(f"  path      : {aud['printed_mm'] / 1000:,.1f} m printed"
          f"   stops/layer: {got_stops} (limit {want_stops})"
          f"   retracts: {aud['retracts']}")
    print(f"  estimate  : {stats['est_time_min']:.1f} min"
          f"   (first run - verify on the machine)")
    print(f"  bed gate  : x {bb[0]:.1f}..{bb[2]:.1f}  y {bb[1]:.1f}..{bb[3]:.1f}"
          f"  of {BED[0]:.0f}x{BED[1]:.0f}")
    for warn in stats["warnings"]:
        print(f"  warning   : {warn}")
    print()
    print("  gates (brief section 4):")
    print("    T17 walls exact      : "
          + ("PASS" if len(aud["printed_blocks"])
             == stats["contours"] * stats["walls"] * stats["layers"]
             else "FAIL") + f"  ({len(aud['printed_blocks'])} printed blocks "
          f"= {stats['contours']}x{stats['walls']}x{stats['layers']})")
    print(f"    T18 spacing (auto)   : "
          + ("PASS" if spacing_ok else "FAIL")
          + f"  {stats['spacing']:.4f} = w-h(1-pi/4) = "
          f"{want_spacing:.4f}")
    print(f"    T19 E/mm anchor      : "
          + ("PASS" if e_ok else "FAIL")
          + (f"  %.9f median vs %.9f (d %.2f%%) +/-0.5%%"
             % (med_e, E_ANCHOR, (med_e / E_ANCHOR - 1) * 100)))
    print(f"    T20 stops/layer      : "
          + ("PASS" if stops_ok else "FAIL")
          + f"  max {got_stops} vs {want_stops} (kontur-1)")
    print(f"    T21 seam locked      : "
          + ("PASS" if seam_ok else "FAIL")
          + f"  max shift {seam_shift:.3f} mm vs 0.5")
    print(f"    T22 inside the bed   : " + ("PASS" if bed_ok else "FAIL")
          + f"   margin {min(bb[0], bb[1], BED[0] - bb[2], BED[1] - bb[3]):.1f}"
          f" mm vs >= {opts.bed_margin:.0f}")
    print(f"    T23 dialect subset   : run dialect_check.py separately")
    print(f"    T25 primes follow G92: "
          + ("PASS" if prime_ok else "FAIL")
          + f"  ({aud['blocks_with_push']} primed blocks)")
    print()
    print("  UNVERIFIED - nothing from this profile is machine-ready until the")
    print("  coupons print clean; see docs/SMOOTH_PHASE1_REPORT.md (brief 0)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="lettergcode",
        description="Generate ZCCAD-compatible G-code for 3D letter shells.")
    ap.add_argument("--dxf", default=None, help="input DXF with the letter outlines")
    ap.add_argument("--stl", default=None, help="input 3D STL file (binary or ASCII)")
    ap.add_argument("--out", default=None, help="output .gcode path")
    ap.add_argument("--ini", default=DEFAULT_INI, help="GcodePara.ini to inherit parameters")
    ap.add_argument("--height", type=float, default=None, help="override dbHeightShell (mm)")
    ap.add_argument("--layer", type=float, default=None, help="override dbHeightLayer (mm)")
    ap.add_argument("--width", type=float, default=None, help="override dbThicknessOrigin (mm)")
    ap.add_argument("--passes", type=int, default=None, help="override iThichnessCount")
    ap.add_argument("--spacing", type=float, default=None, help="override dbThichnessOffset (mm)")
    ap.add_argument("--fill", action="store_true",
                    help="add the Fill inset line (dbThichnessOffset inside the wall)")
    ap.add_argument("--no-hem", action="store_true",
                    help="run the fill to the top instead of stopping it at the "
                         "surroundSide.dbHeight1 hem band")
    ap.add_argument("--bands", default=None, metavar="MM,MM",
                    help="colour band thicknesses from the bottom up; the last band "
                         "takes whatever is left of --height")
    ap.add_argument("--glue", default=None, metavar="N,N",
                    help="iLayerGlueNo per band, bottom up (1=>T0, 2=>T1, 3=>T2)")
    ap.add_argument("--reverse-zones", action="store_true",
                    help="print the bands last-first, matching the app's reverse "
                         "printf button")
    ap.add_argument("--seat-w", type=float, default=0.0, metavar="MM",
                    help="acrylic pocket width in plan (sheet thickness + clearance); "
                         "0 keeps the plain wall")
    ap.add_argument("--seat-depth", type=float, default=3.0, metavar="MM",
                    help="pocket depth in Z = lip height above the shoulder")
    ap.add_argument("--seat-land", type=float, default=2.0, metavar="MM",
                    help="flat full-thickness shoulder kept under the pocket")
    ap.add_argument("--seat-ramp", type=float, default=10.0, metavar="MM",
                    help="Z over which the wall thickens below the shoulder")
    ap.add_argument("--min-area", type=float, default=0.0, metavar="MM2",
                    help="drop closed contours smaller than this (dimension marks, "
                         "decorative dots)")
    ap.add_argument("--max-area", type=float, default=0.0, metavar="MM2",
                    help="drop closed contours larger than this - use it when the "
                         "DXF carries the machine-bed rectangle as geometry, so the "
                         "layout frame is not printed as a border")
    ap.add_argument("--speed", type=int, default=None,
                    help="override iSpeedWork in mm/min (arr.gcode profile: 3600)")
    ap.add_argument("--first-speed", type=int, default=None,
                    help="override iSpeedFirstLayer in mm/min")
    ap.add_argument("--cell", type=float, default=0.25,
                    help="distance-field resolution in mm (default 0.25)")
    ap.add_argument("--no-pre-side", action="store_true", help="skip the prevent-curl frame")
    ap.add_argument("--pre-passes", type=int, default=None, metavar="N",
                    help="number of prevent-curl frame passes (INI iNumPreSide). "
                         "The vendor emits one ';start printf' marker per pass")
    ap.add_argument("--first-layer-fill", action="store_true",
                    help="hatch the first layer solid for bed adhesion")
    ap.add_argument("--fill-spacing", type=float, default=0.8)
    ap.add_argument("--show-params", action="store_true", help="dump the resolved parameters")
    ap.add_argument("--place", default=None, metavar="X,Y",
                    help="translate the job so its bounding box starts at X,Y")
    ap.add_argument("--offset", default=None, metavar="DX,DY", help="translate the job by DX,DY")
    # ------------------------------------------------------------- family -----
    ap.add_argument("--family", default=None, choices=["zccad", "universal"],
                    help="output family: 'zccad' = vendor-compatible letter "
                         "shell dialect (default), 'universal' = standard "
                         "Marlin-class FDM G-code for generic printers "
                         "(Bambu Lab class). The ZCCAD pipeline is untouched "
                         "by the universal branch.")
    ap.add_argument("--profile", default=None, metavar="NAME",
                    help="universal: machine profile (marlin-generic, "
                         "bambu-generic, x1c); --bed overrides its size")
    ap.add_argument("--template", default=None, metavar="NAME",
                    help="style template JSON (name of a file in "
                         "work/templates/ or a path). INI -> template -> "
                         "CLI flags, so typed flags always win")
    # ---------------------------------------------------------- universal -----
    ap.add_argument("--infill", type=float, default=None, metavar="PCT",
                    help="universal: infill density percent, 0 = walls only")
    ap.add_argument("--infill-pattern", default=None,
                    choices=["rectilinear", "concentric"],
                    help="universal: infill style (default rectilinear)")
    ap.add_argument("--solid-bottom", dest="solid_bottom", type=int, default=None,
                    metavar="N", help="universal: solid base layers (default 2)")
    ap.add_argument("--solid-top", dest="solid_top", type=int, default=None,
                    metavar="N", help="universal: solid top layers (default 2)")
    ap.add_argument("--skirt-lines", dest="skirt_lines", type=int, default=None,
                    metavar="N", help="universal: skirt loops on layer 0 (default 2)")
    ap.add_argument("--skirt-gap", dest="skirt_gap", type=float, default=None,
                    metavar="MM", help="universal: skirt distance from the part")
    ap.add_argument("--brim", type=float, default=None, metavar="MM",
                    help="universal: brim width on layer 0, 0 = off")
    ap.add_argument("--no-multitool", dest="no_multitool", action="store_true",
                    help="universal: collapse the colour plan to one tool "
                         "instead of emitting T switches")
    ap.add_argument("--scale", type=float, default=None, metavar="S",
                    help="universal: rescale DXF coordinates by S before "
                         "printing (e.g. 0.5); 0 / omitted leaves size alone")
    ap.add_argument("--fit-bed", dest="fit_bed", action="store_true",
                    help="universal: shrink (never grow) so the part + skirt "
                         "fits the profile bed; oversized after scaling "
                         "still fails")
    ap.add_argument("--bed", default=None, metavar="X,Y",
                    help="universal: override the profile bed size in mm")
    # --------------------------------------------- smooth (zccad, brief R0) --
    ap.add_argument("--walls", type=int, default=None, metavar="N",
                    help="smooth: printed wall lines per contour, no vendor "
                         "+1 quirk (T17); default 1")
    ap.add_argument("--wall-spacing", default=None, metavar="AUTO|MM",
                    help="smooth: distance between wall bead centres; "
                         "auto = width - layer*(1-pi/4) so rounded caps just "
                         "touch (T18)")
    ap.add_argument("--seam", default=None, metavar="CORNER|BACK|X,Y",
                    help="smooth: locked seam placement (T21); default corner")
    ap.add_argument("--no-alternate-order", dest="no_alternate_order",
                    action="store_true",
                    help="smooth: keep the same contour order every layer "
                         "instead of alternating (default alternates, T20)")
    ap.add_argument("--coast", type=float, default=None, metavar="MM",
                    help="smooth: path length printed with frozen E before a "
                         "loop closes (default 0.6)")
    ap.add_argument("--hop", type=float, default=None, metavar="MM",
                    help="smooth: Z lift that rides with each retract "
                         "(default 0.6)")
    ap.add_argument("--min-layer-time", type=float, default=None, metavar="S",
                    help="smooth: slow a layer down when it would finish "
                         "faster than this (default 10 s, floor F1200)")
    ap.add_argument("--speed-class", default=None, metavar="SMALL|LARGE|AUTO",
                    help="smooth: work speed from the design size (T26); "
                         "default auto")
    ap.add_argument("--work-speed", type=int, default=None, metavar="FMM",
                    help="smooth: explicit wall feed in mm/min, overrides "
                         "--speed-class and sets the T26 temperature")
    ap.add_argument("--bed-margin", type=float, default=None, metavar="MM",
                    help="smooth: warn when plastic+pre-side frame sits "
                         "closer than this to a bed edge (default 15)")
    ap.add_argument("--pangkon", type=float, default=None, metavar="MM",
                    help="smooth: acrylic thickness for the top pocket "
                         "(3.0 = seat 3.6 mm below the lip); 0 = off")
    ap.add_argument("--pangkon-back", dest="pangkon_back",
                    action="store_true",
                    help="smooth: also cut the pocket mirrored near the bed")
    ap.add_argument("--spiral", dest="spiral", action="store_true",
                    help="smooth: continuous Z spiral - accepted here but "
                         "Phase 2; the engine rejects it politely for now")
    args = ap.parse_args(argv)

    tpl = None
    if args.template:
        tpl, tpl_path = load_template(args.template)
        print(f"template           : {os.path.basename(tpl_path)}")
        if tpl.get("description"):
            print(f"                     {tpl['description']}")
        apply_template(args, tpl)
    args.family = args.family or (tpl or {}).get("family") or "zccad"
    args.profile = args.profile or (tpl or {}).get("profile")

    if not args.dxf and not args.stl:
        ap.error("Either --dxf or --stl must be provided")
    if args.dxf and args.stl:
        ap.error("Cannot specify both --dxf and --stl; choose one")

    input_file = args.stl or args.dxf
    if not os.path.exists(input_file):
        ap.error(f"Input file not found: {input_file}")
    out = args.out or os.path.splitext(input_file)[0] + ".gcode"

    par = Params.from_ini(args.ini) if os.path.exists(args.ini) else Params()
    if args.height is not None:
        par.let.dbHeightShell = args.height
    if args.layer is not None:
        par.let.dbHeightLayer = args.layer
    if args.width is not None:
        par.let.dbThicknessOrigin = args.width
    if args.passes is not None:
        par.let.iThichnessCount = args.passes
    if args.spacing is not None:
        par.let.dbThichnessOffset = args.spacing
    if args.speed is not None:
        par.pri.iSpeedWork = args.speed
    if args.first_speed is not None:
        par.pri.iSpeedFirstLayer = args.first_speed
    if args.seat_w > 0:
        par.seat.width = args.seat_w
        par.seat.depth = args.seat_depth
        par.seat.land = args.seat_land
        par.seat.ramp = args.seat_ramp
    if args.pre_passes is not None:
        # iNumPreSide: the pre-side frame emits one `;start printf` per pass, so
        # this changes the marker count and must be explicit when comparing
        # against a reference export.
        par.let.iNumPreSide = max(0, int(args.pre_passes))
    if args.bands:
        vals = [float(v) for v in args.bands.split(",") if v.strip()]
        if not vals:
            ap.error("--bands needs at least one thickness")
        par.col.dbLayerHeight = vals
        par.col.iLayerNum = len(vals)
    if args.glue:
        g = [int(v) for v in args.glue.split(",") if v.strip()]
        if not g:
            ap.error("--glue needs at least one extruder number")
        par.col.iLayerGlueNo = g + [g[-1]] * max(0, par.col.iLayerNum - len(g))
        par.col.iLayerGlueNo = par.col.iLayerGlueNo[:max(1, par.col.iLayerNum)]
    par.reverse_zones = args.reverse_zones

    # ------------------------------------------------- smooth profile dispatch
    t0 = time.time()
    smooth = args.family == "zccad" and (args.profile or "") == "smooth"
    if smooth:
        _smooth_neutralize(args, par)
        return _run_smooth(args, ap, out, t0, par)

    if args.show_params:
        print(f"family             : {args.family}"
              + (f"  profile: {args.profile}" if args.family == "universal" else ""))
        print(f"ini                : {args.ini}")
        print(f"height / layer     : {par.let.dbHeightShell} / {par.let.dbHeightLayer}"
              f"  -> {par.layer_count} layers")
        print(f"wall width         : {par.glue_width} mm"
              f"   passes={1 + par.let.iThichnessCount} @ {par.let.dbThichnessOffset} mm")
        print(f"E per mm           : {par.e_per_mm:.10f}  ({(par.glue_width / par.glu.dbStuffWidth) ** 3:.6f} / A)")
        runs = []
        for glue in par.band_plan():
            if runs and runs[-1][0] == glue:
                runs[-1][1] += 1
            else:
                runs.append([glue, 1])
        print("colour plan        : " + "  ".join(
            f"{c}L glue{g}->T{par.tool_no(g)}" for g, c in runs)
              + ("   [reversed]" if par.reverse_zones else ""))
        print(f"fill / hem         : {'on' if args.fill else 'off'}"
              f"  hem={'off' if args.no_hem else f'{par.hem_layers} top layers'}")
        if par.seat.width > 0:
            lip = par.wall_thickness
            print(f"acrylic pocket     : {par.seat.width} mm wide x {par.seat.depth} mm deep"
                  f"   rim {lip + par.seat.width:.1f} mm = {lip:.1f} lip + {par.seat.width:.1f}"
                  f"   shoulder z {par.layer_count * par.let.dbHeightLayer - par.seat.depth:.2f}")
        else:
            print("acrylic pocket     : off")
        print(f"speeds             : work {par.pri.iSpeedWork}  first {par.pri.iSpeedFirstLayer}"
              f"  idle {par.pri.iSpeedIdle}  z {par.pri.iSpeedZ}  mm/min")
        print()

    t0 = time.time()
    place = _pair(args.place)
    offset = _pair(args.offset) or (0.0, 0.0)

    if args.stl:
        from .stl import STLJob
        stl_job = STLJob(par, args.stl, scale=(args.scale or 0.0),
                         offset=offset, place=place,
                         fit_bed=bool(args.fit_bed), center_bed=True)

        if args.family == "universal":
            from .machines import get_profile
            from .universal import UniversalOpts
            profile = get_profile(args.profile or "bambu-generic")
            if args.bed:
                bx, by = _pair(args.bed)
                profile.bed_x, profile.bed_y = float(bx), float(by)
            if args.speed is not None:
                profile.work_speed = int(args.speed)
            if args.first_speed is not None:
                profile.first_layer_speed = int(args.first_speed)
            opts = UniversalOpts(
                infill_density=(args.infill if args.infill is not None else 0.0),
                infill_pattern=(args.infill_pattern or "rectilinear"),
                solid_bottom=(args.solid_bottom if args.solid_bottom is not None else 3),
                solid_top=(args.solid_top if args.solid_top is not None else 0),
                skirt_lines=(args.skirt_lines if args.skirt_lines is not None else 2),
                skirt_gap=(args.skirt_gap if args.skirt_gap is not None else 6.0),
                brim=(args.brim or 0.0),
                multitool=not args.no_multitool,
                scale=(args.scale or 0.0),
                fit_bed=bool(args.fit_bed),
                center_bed=True)
            rep = stl_job.render_universal(profile, out, opts,
                                           progress=lambda i, n: print(
                                               f"\r  layer {i}/{n}", end="",
                                               file=sys.stderr))
            if sys.stderr.isatty():
                print("", file=sys.stderr)
            n = sum(1 for _ in open(out, "r", encoding="ascii", errors="replace"))
            print(f"{out}")
            print(f"  triangles: {len(stl_job.triangles):,}")
            print(f"  layers   : {stl_job.layer_n}")
            print(f"  lines    : {n}")
            print(f"  bed      : {profile.bed_x} x {profile.bed_y} mm  ({profile.name})")
            for t, ln in sorted(rep["len_by_tool"].items()):
                print(f"  T{t}        : path {ln} m, filament {rep['e_by_tool'].get(t, 0.0)} m")
            print(f"  estimate : {rep['est_time_min']} min   (first run - verify on the machine)")
            print(f"  time     : {time.time() - t0:.1f} s")
            return 0

        stl_job.render_zccad(out, pre_side=not args.no_pre_side,
                             progress=lambda i, n: print(
                                 f"\r  layer {i}/{n}", end="", file=sys.stderr))
        if sys.stderr.isatty():
            print("", file=sys.stderr)
        n = sum(1 for _ in open(out, "r", encoding="ascii", errors="replace"))
        print(f"{out}")
        print(f"  triangles: {len(stl_job.triangles):,}")
        print(f"  layers   : {stl_job.layer_n}")
        print(f"  lines    : {n}")
        print(f"  time     : {time.time() - t0:.1f} s")
        return 0

    job = Job(par, args.dxf, cell=args.cell, offset=offset, place=place,
              fill=args.fill, hem=not args.no_hem,
              min_area=args.min_area, max_area=args.max_area).load()

    if args.family == "universal":
        from .machines import get_profile
        from .universal import UniversalOpts, render_universal
        profile = get_profile(args.profile or "bambu-generic")
        if args.bed:
            bx, by = _pair(args.bed)
            profile.bed_x, profile.bed_y = float(bx), float(by)
        # typed mm/min speeds move the profile, matching the zccad overrides
        if args.speed is not None:
            profile.work_speed = int(args.speed)
        if args.first_speed is not None:
            profile.first_layer_speed = int(args.first_speed)
        opts = UniversalOpts(
            infill_density=(args.infill if args.infill is not None else 15.0),
            infill_pattern=(args.infill_pattern or "rectilinear"),
            solid_bottom=(args.solid_bottom if args.solid_bottom is not None
                          else 2),
            solid_top=(args.solid_top if args.solid_top is not None else 2),
            skirt_lines=(args.skirt_lines if args.skirt_lines is not None
                         else 2),
            skirt_gap=(args.skirt_gap if args.skirt_gap is not None else 6.0),
            brim=(args.brim or 0.0),
            multitool=not args.no_multitool,
            scale=(args.scale or 0.0),
            fit_bed=bool(args.fit_bed),
            center_bed=True)
        rep = render_universal(job, profile, out, opts,
                               progress=lambda i, n: print(
                                   f"\r  layer {i}/{n}", end="",
                                   file=sys.stderr))
        if sys.stderr.isatty():
            print("", file=sys.stderr)
        n = sum(1 for _ in open(out, "r", encoding="ascii", errors="replace"))
        print(f"{out}")
        print(f"  contours : {len(job.rings)}")
        print(f"  layers   : {par.layer_count}")
        print(f"  lines    : {n}")
        print(f"  bed      : {profile.bed_x} x {profile.bed_y} mm"
              f"  ({profile.name})")
        for t, ln in sorted(rep["len_by_tool"].items()):
            print(f"  T{t}        : path {ln} m,"
                  f" filament {rep['e_by_tool'].get(t, 0.0)} m")
        print(f"  estimate : {rep['est_time_min']} min   "
              f"(first run - verify on the machine)")
        print(f"  time     : {time.time() - t0:.1f} s")
        return 0

    job.render(out, pre_side=not args.no_pre_side,
               first_layer_fill=args.first_layer_fill,
               fill_spacing=args.fill_spacing,
               progress=lambda i, n: print(f"\r  layer {i}/{n}", end="", file=sys.stderr))
    if sys.stderr.isatty():
        print("", file=sys.stderr)

    # apply the geometry overrides that generate() does not know about
    n = sum(1 for _ in open(out, "r", encoding="ascii", errors="replace"))
    print(f"{out}")
    print(f"  contours : {len(job.rings)}")
    print(f"  layers   : {par.layer_count}")
    print(f"  lines    : {n}")
    print(f"  time     : {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
