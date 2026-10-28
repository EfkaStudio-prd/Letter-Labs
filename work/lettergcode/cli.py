"""Command line front-end:  python -m lettergcode --dxf letter.dxf --out job.gcode"""
from __future__ import annotations

import argparse
import os
import sys
import time

from .job import Job
from .params import Params

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


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="lettergcode",
        description="Generate ZCCAD-compatible G-code for 3D letter shells.")
    ap.add_argument("--dxf", required=True, help="input DXF with the letter outlines")
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
    args = ap.parse_args(argv)

    if not os.path.exists(args.dxf):
        ap.error(f"DXF not found: {args.dxf}")
    out = args.out or os.path.splitext(args.dxf)[0] + ".gcode"

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

    if args.show_params:
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
    job = Job(par, args.dxf, cell=args.cell, offset=offset, place=place,
              fill=args.fill, hem=not args.no_hem,
              min_area=args.min_area, max_area=args.max_area).load()
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
