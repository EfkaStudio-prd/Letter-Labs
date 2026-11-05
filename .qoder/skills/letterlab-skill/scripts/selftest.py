"""LetterLab self-check: run this before trusting any generated G-code.

Standalone test suite, standard library only. It checks the parts that can
silently produce a bad print:

  T1  DXF INSERT of BLOCK content is scaled, rotated and translated correctly
  T2  a drawing whose geometry lives only in a block still imports
  T3  the extrusion constant reproduces the vendor's E/mm
  T4  colour bands convert from millimetres of height to whole layers
  T5  the hem band is the expected number of top layers
  T6  golden regression: regenerate the fixture and pass every dialect gate
  T7  per-layer ring count matches the vendor where the two should agree
  T8  the 3D simulator re-parses our own output into the right layer/tool set
  T10 the simulator honours the modal F word when estimating print time
  T9  the PNG writer emits a real, decodable PNG
  T13 --family universal (Marlin): M83 present, no vendor markers, bed-honest
      XY, layer markers match H/L and the E word equals path*w*h/area per move
  T14 style templates: shipped JSONs load, explicit CLI values win
  T15 the interactive HTML viewer writes a self-contained webgl file

  python selftest.py            # all tests
  python selftest.py --quick    # skip the slow golden regression (T6/T7)
"""
from __future__ import annotations

import argparse
import math
import os
import re
import struct
import subprocess
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
sys.path.insert(0, HERE)

REPO = None
_d = os.path.abspath(SKILL_DIR)
while True:
    if os.path.isdir(os.path.join(_d, "work", "lettergcode")):
        REPO = _d
        break
    p = os.path.dirname(_d)
    if p == _d:
        break
    _d = p

if REPO:
    # appended, never inserted: work/ also holds an older validate_gcode.py with a
    # different signature, and this directory's copies are the canonical ones
    sys.path.append(os.path.join(REPO, "work"))

FIXTURE = os.path.join(SKILL_DIR, "fixtures", "a_golden.dxf")
GOLDEN_REF = os.path.join(REPO or "", "A_SAMPLE_50mm.gcode") if REPO else None

RESULTS = []
SKIPPED = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("  %-4s %-52s %s" % ("PASS" if ok else "FAIL", name, detail))


def skip(name, why):
    """A test that cannot run because a vendor artifact is absent.

    Not a pass: the caller must not report dialect proof it did not obtain. The
    summary prints the skipped names so they stay visible.
    """
    SKIPPED.append(name)
    print("  %-4s %-52s %s" % ("SKIP", name, why))


def _write(path, text):
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        fh.write(text)


def _dxf_with_block():
    """A 10x10 square in block SQ, inserted scaled/rotated, in AC1018 ASCII."""
    ents = ["0", "SECTION", "2", "ENTITIES"]
    ents += ["0", "INSERT", "8", "0", "2", "SQ",
             "10", "100.0", "20", "50.0", "41", "2.0", "42", "2.0", "50", "0"]
    ents += ["0", "INSERT", "8", "0", "2", "SQ",
             "10", "0.0", "20", "0.0", "41", "1.0", "42", "1.0", "50", "90"]
    ents += ["0", "ENDSEC"]
    blocks = ["0", "SECTION", "2", "BLOCKS",
              "0", "BLOCK", "8", "0", "2", "SQ", "10", "0.0", "20", "0.0", "30", "0.0",
              "0", "LWPOLYLINE", "8", "0", "100", "AcDbEntity", "100", "AcDbPolyline",
              "90", "4", "70", "1",
              "10", "0", "20", "0", "10", "10", "20", "0",
              "10", "10", "20", "10", "10", "0", "20", "10",
              "0", "ENDBLK", "8", "0",
              "0", "ENDSEC"]
    return (["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1018",
             "9", "$INSUNITS", "70", "4", "0", "ENDSEC"]
            + blocks + ents + ["0", "EOF"])


def _dxf_block_only():
    """Geometry that lives in a BLOCK and is never INSERTed.

    Real drawings do this - the vendor's own special_shape library does - and a
    reader that walks only the ENTITIES section returns nothing. Synthesised
    here rather than read from disk so the test travels with the repo.
    """
    blocks = ["0", "SECTION", "2", "BLOCKS",
              "0", "BLOCK", "8", "0", "2", "ONLYBLK",
              "10", "0.0", "20", "0.0", "30", "0.0",
              "0", "LWPOLYLINE", "8", "0",
              "100", "AcDbEntity", "100", "AcDbPolyline",
              "90", "4", "70", "1",
              "10", "0", "20", "0", "10", "10", "20", "0",
              "10", "10", "20", "10", "10", "0", "20", "10",
              "0", "ENDBLK", "8", "0", "0", "ENDSEC"]
    ents = ["0", "SECTION", "2", "ENTITIES", "0", "ENDSEC"]
    return (["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1018",
             "9", "$INSUNITS", "70", "4", "0", "ENDSEC"]
            + blocks + ents + ["0", "EOF"])


def test_insert_transform(tmp):
    if REPO is None:
        check("T1 INSERT scale/rotate/translate", False, "engine not found")
        return
    from lettergcode import dxf, geom
    path = os.path.join(tmp, "inserts.dxf")
    _write(path, "\n".join(_dxf_with_block()) + "\n")
    rings, chains = dxf.close_rings(dxf.read_dxf(path))
    rings = [r for r in rings if len(r) >= 3]
    if len(rings) != 2:
        check("T1 INSERT scale/rotate/translate", False,
              "expected 2 rings from 2 INSERTs, got %d" % len(rings))
        return
    b1 = geom.bbox([rings[0]])
    # INSERT 1: 10 mm square scaled x2 at (100,50) -> 20 mm, origin at 100,50
    ok1 = (abs(b1[0] - 100) < 1e-6 and abs(b1[1] - 50) < 1e-6
           and abs(b1[2] - 120) < 1e-6 and abs(b1[3] - 70) < 1e-6)
    b2 = geom.bbox([rings[1]])
    # INSERT 2: rotated 90 deg about the block origin -> x in -10..0, y in 0..10
    ok2 = (abs(b2[0] + 10) < 1e-6 and abs(b2[1] - 0) < 1e-6
           and abs(b2[2] - 0) < 1e-6 and abs(b2[3] - 10) < 1e-6)
    srcs = {e["source"] for e in dxf.read_dxf(path)}
    check("T1 INSERT scale/rotate/translate", ok1 and ok2 and "INSERT/" in
          list(srcs)[0], "box1=%s box2=%s src=%s" %
          (tuple(round(v, 2) for v in b1), tuple(round(v, 2) for v in b2),
           sorted(srcs)))


def test_block_only_fallback(tmp):
    if REPO is None:
        check("T2 block-only drawing imports", False, "engine not found")
        return
    from lettergcode import dxf
    path = os.path.join(tmp, "block_only.dxf")
    _write(path, "\n".join(_dxf_block_only()) + "\n")
    ents = dxf.read_dxf(path)
    check("T2 block-only drawing imports", len(ents) >= 1,
          "%d entities recovered from the block" % len(ents))


def test_e_model():
    from lettergcode.params import Params
    p = Params()
    p.let.dbThicknessOrigin = 1.2
    p.let.dbThicknessCompensate = 0.0
    p.glu.dbStuffWidth = 1.75
    got = p.e_per_mm
    want = 0.134285714286
    check("T3 vendor E/mm constant", abs(got - want) < 1e-9,
          "got %.12f want %.12f" % (got, want))


def test_band_plan():
    from lettergcode.params import Params
    p = Params()
    p.let.dbHeightShell = 50.0
    p.let.dbHeightLayer = 0.3
    p.col.iLayerNum = 3
    p.col.dbLayerHeight = [10, 30, 10] + [8] * 4
    p.col.iLayerGlueNo = [1, 2, 1] + [1] * 4
    plan = p.band_plan()
    runs = []
    for glue in plan:
        if runs and runs[-1][0] == glue:
            runs[-1][1] += 1
        else:
            runs.append([glue, 1])
    got = [(g, c) for g, c in runs]
    # ZCCAD rounds a band UP: 10 mm is 34 layers (z=10.20), measured on the
    # 3-tool vendor export TES .gcode. The last band takes the remainder.
    want = [(1, 34), (2, 100), (1, 33)]
    check("T4 bands mm -> whole layers", got == want and len(plan) == 167,
          "%s (n=%d)" % (got, len(plan)))


def test_hem():
    from lettergcode.params import Params
    p = Params()
    p.let.dbHeightShell = 50.0
    p.let.dbHeightLayer = 0.3
    p.sur.dbHeight1 = 0.9
    check("T5 hem band = 3 top layers", p.hem_layers == 3,
          "hem_layers=%d" % p.hem_layers)


def _gen(out):
    return _gen_args(out, [])


# The golden reference A_SAMPLE_50mm.gcode was built with these exact parameters.
# They must be passed explicitly: the live S528\GcodePara.ini changes whenever
# someone works in the GUI, and reading height from it silently compared a 30 mm
# job against a 50 mm reference.
GOLDEN_ARGS = ["--height", "50", "--layer", "0.3", "--width", "1.2",
               "--passes", "1", "--spacing", "0.8",
               "--bands", "10,30,10", "--glue", "1,2,1",
               "--speed", "3600", "--first-speed", "1800", "--pre-passes", "2"]


def _gen_args(out, extra):
    """Generate with the golden parameters, then any test-specific overrides.

    Later options win in argparse, so `extra` can override `--height` and
    `--bands` for tests that need a different job shape.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(REPO, "work")
    cmd = (["python", "-m", "lettergcode", "--dxf", FIXTURE, "--out", out,
            "--ini", os.path.join(REPO, "S528", "GcodePara.ini")]
           + GOLDEN_ARGS + list(extra))
    return subprocess.run(cmd, cwd=os.path.join(REPO, "work"), env=env,
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode


def _vendor_refs_present():
    """Both the vendor export and its INI are needed to compare dialect.

    Neither ships with this repo: they are vendor artifacts. A public clone
    therefore has to be told to supply them instead of silently failing.
    """
    ini = os.path.join(REPO or "", "S528", "GcodePara.ini")
    return bool(REPO and GOLDEN_REF and os.path.exists(GOLDEN_REF)
                and os.path.exists(FIXTURE) and os.path.exists(ini))


def test_golden_gates(tmp):
    if not _vendor_refs_present():
        skip("T6 golden dialect gates",
             "needs a vendor export + S528/GcodePara.ini (absent by design)")
        return False
    out = os.path.join(tmp, "selftest_job.gcode")
    if _gen(out) != 0:
        check("T6 golden dialect gates", False, "generate failed")
        return False
    import validate_gcode as vg
    rc = vg.main([GOLDEN_REF, out])
    check("T6 golden dialect gates", rc == 0, "validate_gcode rc=%d" % rc)
    return True


def test_golden_rings(ok_to_run, tmp):
    if not ok_to_run:
        skip("T7 per-layer ring count", "needs the same vendor export as T6")
        return
    import labcheck
    tmp_out = os.path.join(tmp, "selftest_ring.gcode")
    if _gen(tmp_out) != 0:
        check("T7 per-layer ring count", False, "generate failed")
        return
    ref, _ = labcheck.audit(GOLDEN_REF)
    mine, _ = labcheck.audit(tmp_out)
    # layers below the vendor's taper band must agree exactly
    probe = [z for z in sorted(ref) if 0.6 <= z <= 30.0]
    bad = [z for z in probe if ref.get(z, {}).get("rings") != mine.get(z, {}).get("rings")]
    check("T7 per-layer ring count (z 0.6..30)", not bad,
          "%d probes, %d mismatches%s" % (len(probe), len(bad),
                                          "" if not bad else " e.g. z=%s" % bad[:3]))
    try:
        os.remove(tmp_out)
    except OSError:
        pass


def test_simulator(tmp):
    import gcode3d
    src = os.path.join(tmp, "tiny.gcode")
    _write(src, "\n".join([
        ";G code start", "G21", "G90", "G28", "G92 E0", "T0", "G92 E0",
        "G0 F18000 X10 Y10", "G0 F18000 Z0.3",
        "G1 F1800 X10 Y10 E0.1",
        "G1 X20 Y10 E1.442857142857",
        "G1 X20 Y20 E2.885714285714",
        "G1 X10 Y20 E4.328571428571",
        "G1 X10 Y10 E5.771428571428",
        "G91", "G1 F1200 E-3", "G90",
        "T1", "G92 E0",
        "G0 F18000 Z0.6",
        "G1 F3600 X30 Y30 E0.1",
        "G1 X40 Y30 E1.542857142857",
        "G1 X40 Y40 E2.985714285714",
        ";End of Gcode"]) + "\n")
    tp = gcode3d.Toolpath(src, bead_width=1.2)
    st = tp.stats()
    ok_tools = st["tools"] == [0, 1]
    ok_layers = st["layers"] == 2
    # the T1 block is a relative-E move; it must still count as extrusion
    ok_rel = 1 in tp.len_by_tool and tp.len_by_tool[1] > 20
    check("T8 simulator tool/layer/E-modal", ok_tools and ok_layers and ok_rel,
          "tools=%s layers=%d len=%s" % (st["tools"], st["layers"],
                                         {k: round(v, 1) for k, v in st["length_by_tool_mm"].items()}))


def test_no_zero_temp(tmp):
    """A job must never cool the nozzle it is about to print with.

    Found on a real defect: a second, inverted tool-mapping implementation made a
    glue-1 job resolve to T1, so the writer emitted `M104 S0 T0` one line before
    `T0` started the first layer. None of the 13 vendor exports in the corpus
    contains `M104 S0` at all - the footer uses `M104 S30 Tn`.
    """
    import re
    if REPO is None:
        check("T11 single-colour keeps its nozzle hot", False, "engine not found")
        return
    out = os.path.join(tmp, "one_colour.gcode")
    if _gen_args(out, ["--height", "3", "--bands", "3", "--glue", "1"]) != 0:
        check("T11 single-colour keeps its nozzle hot", False, "generate failed")
        return
    zero = 0
    hot = 0
    with open(out, "r", encoding="ascii", errors="replace") as fh:
        for ln in fh:
            m = re.match(r"^M104 S(\d+) T0$", ln.strip())
            if m:
                if int(m.group(1)) == 0:
                    zero += 1
                else:
                    hot += 1
    check("T11 single-colour keeps its nozzle hot", zero == 0 and hot >= 1,
          "M104 S0 x%d, M104 S<temp> T0 x%d (vendor: zero S0)" % (zero, hot))


def test_glue_mapping():
    """One rule only: glue g -> T(g-1), for every band count."""
    if REPO is None:
        check("T12 glue index maps to T(g-1)", False, "engine not found")
        return
    from lettergcode.params import Params
    p = Params()
    got = [p.tool_no(g) for g in (1, 2, 3)]
    ok = got == [0, 1, 2]
    check("T12 glue index maps to T(g-1)", ok, "tool_no(1,2,3) -> %s" % got)


def test_modal_feed(tmp):
    """F is modal. Most vertex lines carry no F word, so a simulator that times
    them at a default instead of the inherited value reports roughly double the
    print time - which is the number a job gets scheduled on."""
    import gcode3d
    e = 0.0
    lines = ["G90", "T0", "G92 E0", "G1 F3600 X0 Y0 Z0.3 E0.1"]
    x = 0.0
    for _ in range(20):
        x += 10.0
        e += 10 * 0.134285714286
        lines.append("G1 X%.1f Y0 E%.6f" % (x, e))   # no F word at all
    src = os.path.join(tmp, "modalf.gcode")
    _write(src, "\n".join(lines) + "\n")
    tp = gcode3d.Toolpath(src)
    mins = tp.total_time / 60.0            # total_time is seconds
    want = 200.0 / 3600.0                  # 200 mm at 3600 mm/min = 0.0556 min
    ok = abs(mins - want) < 0.001
    check("T10 simulator honours modal F", ok,
          "%.4f min, expected %.4f (double that means F is not treated as modal)"
          % (mins, want))


def test_png_writer(tmp):
    import gcode3d
    img = gcode3d.Image(4, 3, bg=(10, 20, 30), ss=2)
    img.quad([(0, 0), (8, 0), (8, 8), (0, 8)], (255, 0, 0))
    path = os.path.join(tmp, "probe.png")
    gcode3d.write_png(path, 4, 3, img.downsample())
    with open(path, "rb") as fh:
        blob = fh.read()
    sig_ok = blob[:8] == b"\x89PNG\r\n\x1a\n"
    # walk the chunks, verify every CRC (that is what a decoder does) and keep IDAT
    i, tags, crc_ok, idat = 8, [], True, b""
    while i + 8 <= len(blob):
        ln = struct.unpack(">I", blob[i:i + 4])[0]
        tag = blob[i + 4:i + 8]
        data = blob[i + 8:i + 8 + ln]
        crc = struct.unpack(">I", blob[i + 8 + ln:i + 12 + ln])[0]
        tags.append(tag)
        crc_ok = crc_ok and crc == (zlib.crc32(tag + data) & 0xFFFFFFFF)
        if tag == b"IDAT":
            idat += data
        i += 12 + ln
    idat_ok = False
    if idat:
        raw = zlib.decompress(idat)
        # 4 px wide, 3 rows, RGB (3 bytes) plus one filter byte per scanline
        idat_ok = len(raw) == 3 * (4 * 3 + 1)
    check("T9 PNG writer emits a decodable file",
          sig_ok and tags == [b"IHDR", b"IDAT", b"IEND"] and crc_ok and idat_ok,
          "chunks=%s crc=%s idat=%s" % (tags, crc_ok, idat_ok))


def test_universal_family(tmp):
    """T13 structural gates for --family universal output (Marlin dialect)."""
    if not REPO:
        skip("T13 universal family gates", "no lettergcode engine in reach")
        return
    out = os.path.join(tmp, "selftest_universal.gcode")
    layer = 0.3
    height = 50.0
    if _gen_args(out, ["--family", "universal", "--profile", "bambu-generic",
                       "--fit-bed",
                       "--height", str(height), "--layer", str(layer)]) != 0:
        check("T13 universal family gates", False, "generate failed")
        return
    want_layers = int(height / layer) + 1
    m83 = 0
    banned = 0
    layer_markers = 0
    e_sum = 0.0
    path_sum = 0.0
    xy_oob = 0
    prev = (0.0, 0.0)
    x = y = 0.0
    with open(out, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            s = raw.strip()
            if not s:
                continue
            if s.startswith(";"):
                if s.startswith(";LAYER:"):
                    layer_markers += 1
                if "extruder switch" in s.lower():
                    banned += 1
                continue
            up = s.split(";", 1)[0].strip().upper()
            if up == "M83":
                m83 += 1
                continue
            if up == "M82":
                banned += 1             # universal files must stay M83-only
                continue
            m = re.match(r"^(G0|G1)\b", up)
            if not m:
                continue
            fx = re.search(r"\sX([-\d.]+)", up)
            fy = re.search(r"\sY([-\d.]+)", up)
            fe = re.search(r"\sE(-?[\d.]+)", up)
            if fx: x = float(fx.group(1))
            if fy: y = float(fy.group(1))
            if fe and (fx or fy):
                # M83: the E word on a printing move is that move's filament
                # delta, so the honesty check is exact - no state to track.
                e_sum += max(float(fe.group(1)), 0.0)
                path_sum += math.hypot(x - prev[0], y - prev[1])
                if not (0.01 <= x <= 256.0 and 0.01 <= y <= 256.0):
                    xy_oob += 1
            if fx or fy:
                prev = (x, y)
    # E per path mm for the bambu wall width 1.2 / layer 0.3 on 1.75 mm PLA:
    # 1.2*0.3/(pi*0.875**2) = 0.149680...
    e_mm = 1.2 * layer / (math.pi * (1.75 / 2.0) ** 2)
    checks = [
        ("M83 once", m83 == 1, "M83=%d" % m83),
        ("no vendor markers", banned == 0, "switch/abs-E=%d" % banned),
        ("layer markers == int(H/L)+1", layer_markers == want_layers,
         "markers=%d want=%d" % (layer_markers, want_layers)),
        ("no out-of-bed XY", xy_oob == 0, "oob=%d" % xy_oob),
        ("E honesty ~ path*w*h/Af",
         path_sum > 1000 and abs(e_sum - path_sum * e_mm) /
         max(e_sum, 1.0) < 0.02,
         "E=%.1f mm for %.0f mm path" % (e_sum, path_sum)),
    ]
    bad = [n for n, ok2, _d in checks if not ok2]
    check("T13 universal family gates", not bad,
          "; ".join("%s[%s]" % (n, "ok" if ok2 else d)
                    for n, ok2, _d in checks))


def test_templates(tmp):
    """T14 template loader: every shipped template parses and CLI wins."""
    if not REPO:
        skip("T14 template loader/contract", "no lettergcode engine in reach")
        return
    try:
        sys.path.index(os.path.join(REPO, "work"))
    except ValueError:
        sys.path.append(os.path.join(REPO, "work"))
    from lettergcode import templates as T
    names = sorted(f for f in os.listdir(os.path.join(REPO, "work", "templates"))
                   if f.endswith(".json"))
    ok = bool(names)
    detail = "%d templates: %s" % (len(names), ", ".join(names))
    for n in names:
        try:
            data, path = T.load_template(n[:-5])
        except SystemExit as exc:
            ok = False
            detail += " [LOAD FAIL %s: %s]" % (n, exc)
            continue
        if "name" not in data and "title" not in data:
            ok = False
            detail += " [%s: no name/title]" % n
    # order contract: explicit CLI value beats the template
    ns = argparse.Namespace(height=None, layer=None, width=None, passes=None,
                            spacing=None, speed=None, first_speed=None,
                            pre_passes=None, seat_w=None, seat_depth=None,
                            seat_land=None, seat_ramp=None, min_area=None,
                            max_area=None, infill=44.0, infill_pattern=None,
                            solid_bottom=None, solid_top=None, skirt_lines=None,
                            skirt_gap=None, brim=None, scale=None,
                            profile=None, family="universal", bands=None,
                            glue=None, no_multitool=False, no_hem=False)
    try:
        T.apply_template(ns, {"infill": 12.0, "family": "zccad",
                              "glue": [1], "fill": True})
        order_ok = (ns.infill == 44.0 and ns.family == "universal"
                    and ns.glue == "1"
                    and ns.fill is True)
    except Exception as exc:                       # noqa: BLE001
        order_ok = False
        detail += " [apply crashed: %r]" % exc
    check("T14 templates parse + CLI-typed wins", ok and order_ok, detail)


def test_html_writer(tmp):
    """T15 the interactive viewer writer produces a self-contained HTML file."""
    if not REPO:
        skip("T15 HTML viewer writer", "no gcode3d module in reach")
        return
    import gcode3d
    src = os.path.join(tmp, "tiny_uni.gcode")
    # minimal universal-dialect job: G90 XYZ + M83 relative E
    body = ["G21", "G90", "M83", ";LAYER:0",
            "G0 F15000 X10 Y10",
            "G1 F3000 X110 Y10 E14.968", "G1 X110 Y110 E29.936",
            "G1 X10 Y110 E44.904", "G1 X10 Y10 E59.872"]
    _write(src, "\n".join(body) + "\n")
    tp = gcode3d.Toolpath(src, bead_width=1.2)
    st = tp.stats()
    html = os.path.join(tmp, "selftest_viewer.html")
    from gcode_html import write_viewer
    write_viewer(tp, st, html, (256, 256), cap=4000, width=1.2,
                 name="selftest")
    with open(html, "rb") as fh:
        blob = fh.read()
    ok = (blob[:15] == b"<!DOCTYPE html>"
          and b"<canvas" in blob and b"getContext" in blob
          and b"</html>" in blob
          and len(blob) < 2 * 1024 * 1024)
    check("T15 HTML viewer self-contained", ok,
          "%d bytes, canvas=%s close=%s" % (len(blob),
                                            b"<canvas" in blob,
                                            b"</html>" in blob))


def main(argv):
    import tempfile
    quick = "--quick" in argv
    print("LetterLab self-check")
    print("  repo    : %s" % (REPO or "NOT FOUND"))
    print("  fixture : %s" % FIXTURE)
    print("  golden  : %s" % (GOLDEN_REF or "NOT FOUND"))
    print()
    with tempfile.TemporaryDirectory() as tmp:
        test_insert_transform(tmp)
        test_block_only_fallback(tmp)
        test_e_model()
        test_band_plan()
        test_hem()
        ran = True
        if quick:
            print("  SKIP T6/T7 (--quick)")
        else:
            ran = test_golden_gates(tmp)
            test_golden_rings(ran, tmp)
        test_simulator(tmp)
        test_modal_feed(tmp)
        test_no_zero_temp(tmp)
        test_glue_mapping()
        test_png_writer(tmp)
        test_universal_family(tmp)
        test_templates(tmp)
        test_html_writer(tmp)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n%d/%d checks passed" % (len(RESULTS) - len(failed), len(RESULTS)))
    if SKIPPED:
        print("SKIPPED (no vendor artifact to compare against): "
              + ", ".join(SKIPPED))
        print("  -> the dialect is NOT proven by this run. Supply a vendor "
              "export and S528/GcodePara.ini, then re-run without --quick.")
    if failed:
        print("FAILED: " + ", ".join(failed))
        print("\nDo not send G-code produced by this build to the machine until "
              "the failures are explained or fixed.")
        return 1
    print("ALL CHECKS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
