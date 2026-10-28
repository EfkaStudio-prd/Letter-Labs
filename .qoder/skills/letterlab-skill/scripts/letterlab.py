"""LetterLab - one command from vector input to a print-ready, verified job.

  python letterlab.py job --dxf LETTER.dxf --out JOB.gcode [--ref VENDOR.gcode]
                          [--height 50] [--layer 0.3] [--passes 1] [--fill]
                          [--bands 10,30,10] [--glue 1,2,1] [--seat-w 3.2] ...

Runs, in order:
  1. generate  - the lettergcode engine writes ZCCAD-dialect G-code
  2. validate  - structural gates against a vendor reference (needs --ref)
  3. audit     - per-layer ring/length diff (needs --ref)
  4. preview   - 3D bead simulation rendered to PNG from the emitted G-code

The engine is never imported by path guesswork: LETTERLAB_ENGINE wins, otherwise
the nearest ancestor containing work/lettergcode is used.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(os.path.dirname(HERE))


def find_repo(start):
    d = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(d, "work", "lettergcode")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            raise SystemExit(
                "lettergcode engine not found. Set LETTERLAB_ENGINE to the "
                "directory that contains work/lettergcode.")
        d = parent


def engine_dir():
    return os.environ.get("LETTERLAB_ENGINE") or find_repo(SKILL_ROOT)


PASS = "PASS"
FAIL = "FAIL"


def run(cmd, cwd=None, env=None):
    e = dict(os.environ)
    if env:
        e.update(env)
    sys.stdout.flush()          # keep our headers above the child's output
    return subprocess.run(cmd, cwd=cwd, env=e)


def cmd_generate(a, rest=None):
    repo = engine_dir()
    cli = ["python", "-m", "lettergcode", "--dxf", a.dxf, "--out", a.out]
    if a.ini:
        cli += ["--ini", a.ini]
    else:
        cli += ["--ini", os.path.join(repo, "S528", "GcodePara.ini")]
    for flag, val in (("--height", a.height), ("--layer", a.layer),
                      ("--width", a.width), ("--spacing", a.spacing),
                      ("--speed", a.speed), ("--first-speed", a.first_speed),
                      ("--bands", a.bands), ("--glue", a.glue),
                      ("--seat-w", a.seat_w), ("--min-area", a.min_area),
                      ("--max-area", a.max_area), ("--seat-depth", a.seat_depth),
                      ("--seat-land", a.seat_land), ("--seat-ramp", a.seat_ramp),
                      ("--place", a.place), ("--offset", a.offset),
                      ("--cell", a.cell), ("--fill-spacing", a.fill_spacing)):
        if val is not None and val != "":
            cli += [flag, str(val)]
    if a.passes is not None:
        cli += ["--passes", str(a.passes)]
    for flag, on in (("--fill", a.fill), ("--no-hem", a.no_hem),
                     ("--reverse-zones", a.reverse_zones),
                     ("--no-pre-side", a.no_pre_side),
                     ("--first-layer-fill", a.first_layer_fill),
                     ("--show-params", a.show_params)):
        if on:
            cli.append(flag)
    print("$ " + " ".join(cli))
    env = {"PYTHONPATH": os.path.join(repo, "work")}
    return run(cli, cwd=os.path.join(repo, "work"), env=env).returncode


def cmd_validate(a):
    return run(["python", os.path.join(HERE, "validate_gcode.py"), a.ref, a.gcode]).returncode


def cmd_audit(a):
    # labcheck labels argv[0] REF and argv[1] MINE
    argv = ["python", os.path.join(HERE, "labcheck.py")]
    argv += [a.ref, a.gcode] if a.ref else [a.gcode]
    return run(argv).returncode


def cmd_preview(a):
    argv = ["python", os.path.join(HERE, "gcode3d.py"), a.gcode,
            "--out", a.out or (os.path.splitext(a.gcode)[0] + "_3d.png"),
            "--width", str(a.width or 1.2),
            "--yaw", str(a.yaw), "--elev", str(a.elev)]
    if a.stats:
        argv.append("--stats")
    return run(argv).returncode


def taper_notice(ini_path, height_override=None):
    """Warn when the job is tall enough for the vendor's top-band wall taper.

    OutKF.updateCoor adds progressively deeper inset passes of the outer boundary
    between (dbHeightShell - dbHeightLow - dbHeightTop) and (dbHeightShell -
    dbHeightTop). This generator does not emit them, so in that band our wall is
    thinner than ZCCAD's. Below the band the two are identical.
    """
    try:
        sys.path.append(os.path.join(engine_dir(), "work"))
        from lettergcode.params import Params
    except Exception:
        return None
    p = Params.from_ini(ini_path) if ini_path and os.path.exists(ini_path) else Params()
    if height_override:
        p.let.dbHeightShell = float(height_override)
    h = p.let.dbHeightShell
    start = h - p.let.dbHeightTop - p.let.dbHeightLow
    # updateCoor's offset is dbWidthSide / V8, so the taper run IS the UI's
    # "oblique width". A straight-edge letter has oblique width 0, bottom height
    # 0 and panel height 0 - it emits no extra passes, and warning there would be
    # a false alarm on every straight job.
    if (p.let.dbWidthSide <= 0.001 or p.let.dbHeightTop <= 0
            or p.let.dbHeightLow <= 0 or start <= 0.001):
        return None
    band = h - p.let.dbHeightTop - start
    return ("top-band wall taper: ZCCAD adds inset wall passes from z=%.1f to "
            "z=%.1f mm (dbHeightLow=%.1f, dbHeightTop=%.1f). This build does NOT "
            "emit them, so the wall in that %.1f mm band is thinner than a ZCCAD "
            "print. Below z=%.1f mm the output is identical."
            % (start, h - p.let.dbHeightTop, p.let.dbHeightLow,
               p.let.dbHeightTop, band, start))


def cmd_job(a):
    repo = engine_dir()
    print("== 1/4 generate")
    gen_argv = argparse.Namespace(**vars(a))
    rc = cmd_generate(gen_argv)
    if rc != 0:
        print("generate failed", file=sys.stderr)
        return rc
    gates = []
    if a.ref:
        print("\n== 2/4 validate against vendor reference")
        rc_v = cmd_validate(argparse.Namespace(ref=a.ref, gcode=a.out))
        gates.append(("structural gates", rc_v == 0))
        print("\n== 3/4 per-layer audit")
        cmd_audit(argparse.Namespace(gcode=a.out, ref=a.ref))
    else:
        print("\n== 2/4 validate  SKIPPED (no --ref given)")
        print("== 3/4 audit      SKIPPED (no --ref given)")
    print("\n== 4/4 3D preview")
    rc_p = cmd_preview(argparse.Namespace(gcode=a.out, out=a.preview,
                                          width=a.width, yaw=a.yaw,
                                          elev=a.elev, stats=False))
    gates.append(("preview rendered", rc_p == 0))
    notice = taper_notice(a.ini or os.path.join(repo, "S528", "GcodePara.ini"),
                          a.height)
    print("\n===== LETTERLAB REPORT =====")
    print("  gcode   : " + os.path.abspath(a.out))
    if a.preview:
        print("  preview : " + os.path.abspath(a.preview))
    for name, good in gates:
        print(f"  {name:18s}: {PASS if good else FAIL}")
    if notice:
        print("\n  NOTICE: " + notice)
    if not a.ref:
        print("  NOTE: no --ref supplied, so the output is UNVERIFIED against "
              "a vendor export. Attach one before printing.")
    return 0 if all(g for _, g in gates) else 1


def build(argv):
    ap = argparse.ArgumentParser(prog="letterlab", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_gen(p):
        p.add_argument("--dxf", help="input DXF with the letter outlines")
        p.add_argument("--out", help="output .gcode path")
        p.add_argument("--ini", default=None, help="GcodePara.ini (default: repo S528\\)")
        p.add_argument("--height", default=None)
        p.add_argument("--layer", default=None)
        p.add_argument("--width", default=None, help="dbThicknessOrigin / bead width mm")
        p.add_argument("--passes", type=int, default=None)
        p.add_argument("--spacing", default=None)
        p.add_argument("--speed", default=None)
        p.add_argument("--first-speed", dest="first_speed", default=None)
        p.add_argument("--bands", default=None)
        p.add_argument("--glue", default=None)
        p.add_argument("--seat-w", dest="seat_w", default=None,
                       help="acrylic pocket width in mm (wall gets wider below the "
                            "shoulder so a sheet drops in)")
        p.add_argument("--seat-depth", dest="seat_depth", default=None,
                       help="pocket depth in Z = the ACTUAL acrylic thickness. The "
                            "vendor's footstep rule is pos = height - acrylic, so a "
                            "3 mm sheet means --seat-depth 3")
        p.add_argument("--seat-land", dest="seat_land", default=None)
        p.add_argument("--seat-ramp", dest="seat_ramp", default=None)
        p.add_argument("--min-area", dest="min_area", default=None)
        p.add_argument("--max-area", dest="max_area", default=None,
                       help="drop contours larger than this mm2 (machine-bed "
                            "rectangle in a layout DXF)")
        p.add_argument("--place", default=None)
        p.add_argument("--offset", default=None)
        p.add_argument("--cell", default=None)
        p.add_argument("--fill-spacing", dest="fill_spacing", default=None)
        p.add_argument("--fill", action="store_true")
        p.add_argument("--no-hem", dest="no_hem", action="store_true")
        p.add_argument("--reverse-zones", dest="reverse_zones", action="store_true")
        p.add_argument("--no-pre-side", dest="no_pre_side", action="store_true")
        p.add_argument("--first-layer-fill", dest="first_layer_fill", action="store_true")
        p.add_argument("--show-params", dest="show_params", action="store_true")

    g = sub.add_parser("generate", help="run the lettergcode engine")
    add_gen(g)
    g.set_defaults(fn=cmd_generate)

    v = sub.add_parser("validate", help="structural gates vs a vendor reference")
    v.add_argument("--gcode", required=True)
    v.add_argument("--ref", required=True)
    v.set_defaults(fn=cmd_validate)

    u = sub.add_parser("audit", help="per-layer ring/length audit")
    u.add_argument("--gcode", required=True)
    u.add_argument("--ref")
    u.set_defaults(fn=cmd_audit)

    q = sub.add_parser("preview", help="3D bead simulation PNG from G-code")
    q.add_argument("--gcode", required=True)
    q.add_argument("--out")
    q.add_argument("--width", type=float, default=1.2)
    q.add_argument("--yaw", type=float, default=45)
    q.add_argument("--elev", type=float, default=24)
    q.add_argument("--stats", action="store_true")
    q.set_defaults(fn=cmd_preview)

    j = sub.add_parser("job", help="generate + validate + audit + preview")
    add_gen(j)
    j.add_argument("--ref", default=None, help="vendor G-code to verify against")
    j.add_argument("--preview", default=None, help="PNG path for the 3D preview")
    j.add_argument("--yaw", type=float, default=45)
    j.add_argument("--elev", type=float, default=24)
    j.set_defaults(fn=cmd_job)

    return ap.parse_args(argv)


def _abs(a):
    """The engine runs with cwd=<repo>/work, so every user path must be absolute."""
    for name in ("dxf", "out", "ini", "ref", "preview"):
        v = getattr(a, name, None)
        if v:
            setattr(a, name, os.path.abspath(v))
    return a


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    a = _abs(build(argv))
    if a.cmd in ("generate", "job") and not getattr(a, "dxf", None):
        print("--dxf is required", file=sys.stderr)
        return 2
    if a.cmd == "job" and not a.out:
        a.out = os.path.splitext(os.path.basename(a.dxf))[0] + ".gcode"
    if a.cmd == "job" and not a.preview:
        a.preview = os.path.splitext(a.out)[0] + "_3d.png"
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
