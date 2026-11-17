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
  T16 3D STL slicer feeds both dialects (binary/ASCII)

  Smooth profile (--family zccad --profile smooth, brief R0), UNVERIFIED
  until the physical coupons print clean - these gates only prove the toolpath:

  T17 smooth walls: rings per contour == --walls exactly, no "+"1 quirk
  T18 smooth auto wall spacing = w - h*(1-pi/4) so rounded caps just touch
  T19 smooth flow: E/mm == the anchor ratio, +/-0.5%, including layer 0.4
  T20 smooth stops: <= kontur-1 per layer, zero for one contour; ordering
      matters (alternating avoids the layer-boundary stop)
  T21 smooth seam: one locked vertex/XY per contour across all layers
      (documented shift <= 0.5 mm, measured 0.000)
  T22 smooth bed gate: refuse when the design+pre-side frame leaves the bed,
      warn below the 15 mm margin
  T23 smooth output stays inside the vendor dialect (subset of real exports)
  T24 smooth spiral: Phase 2 - the engine refuses instead of half-emitting
  T25 smooth primes: every stop prime follows a G92 E0 reset (vendor E-jump bug)
  T26 smooth speed-temperature pairing: 230 C up to 50 mm/s per the manual rule
  T27 zccad --solid-bottom N: the bottom N layers hatch solid (the vendor app's
      Fill Panel face fill) while every layer above keeps the exact wall plan

  T25C light-box job (work/lettergcode/t25c.py, reference D:\\T25RC.gcode):
  T28 outline 8-gon == reference constants (both job DXFs)
  T29 face fill covers every band row, no gaps (T2)
  T30 seam/anchor/lead/wipe discipline on every path
  T31 purge box outside the letter, rings on the 8-layer pad, 1 change (T2)/0 (T1)
  T32 layer plan: flange/wall/ladder/rim runs + Z ladder
  T33 E bookkeeping: deposit E == K*len, retract/prime census, G92 spots
  T34 dialect: instruction shapes subset of the reference, markers whitelisted

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

DEFAULT_REPO = r"C:\Users\Pongo\Downloads\3D Print Software S528\3D Print Software S528\_publish\Letter-Labs"
DEFAULT_SCRIPTS = os.path.join(DEFAULT_REPO, ".qoder", "skills", "letterlab-skill", "scripts")

HERE = os.environ.get("LETTERLAB_SCRIPTS") or os.path.dirname(os.path.abspath(__file__))
if not os.path.isfile(os.path.join(HERE, "gcode3d.py")) and os.path.isdir(DEFAULT_SCRIPTS):
    HERE = DEFAULT_SCRIPTS
SKILL_DIR = os.path.dirname(HERE)
sys.path.insert(0, HERE)

REPO = os.environ.get("LETTERLAB_REPO") or None
if REPO and not os.path.isdir(os.path.join(REPO, "work", "lettergcode")):
    REPO = None
if not REPO:
    _d = os.path.abspath(SKILL_DIR)
    while True:
        if os.path.isdir(os.path.join(_d, "work", "lettergcode")):
            REPO = _d
            break
        p = os.path.dirname(_d)
        if p == _d:
            break
        _d = p
if not REPO and os.path.isdir(os.path.join(DEFAULT_REPO, "work", "lettergcode")):
    REPO = DEFAULT_REPO

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


def test_stl_slicer(tmp):
    """T16 STL parser and slicer: binary + ASCII STL, slice-at-z, dual dialects."""
    if not REPO:
        skip("T16 3D STL slicer", "no repo in reach")
        return
    import struct
    from lettergcode.stl import read_stl, slice_mesh_at_z, STLJob
    from lettergcode.params import Params
    from lettergcode.machines import get_profile
    from lettergcode.universal import UniversalOpts

    b_stl = os.path.join(tmp, "box_bin.stl")
    a_stl = os.path.join(tmp, "box_asc.stl")

    v = [
        (0.0, 0.0, 0.0), (20.0, 0.0, 0.0), (20.0, 20.0, 0.0), (0.0, 20.0, 0.0),
        (0.0, 0.0, 10.0), (20.0, 0.0, 10.0), (20.0, 20.0, 10.0), (0.0, 20.0, 10.0)
    ]
    faces = [
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (2, 3, 7), (2, 7, 6),
        (3, 0, 4), (3, 4, 7), (1, 2, 6), (1, 6, 5)
    ]
    with open(b_stl, "wb") as f:
        f.write(b"LetterLab test box binary STL" + b"\x00" * 51)
        f.write(struct.pack("<I", len(faces)))
        for i1, i2, i3 in faces:
            v1, v2, v3 = v[i1], v[i2], v[i3]
            f.write(struct.pack("<12fH", 0.0, 0.0, 0.0,
                                v1[0], v1[1], v1[2],
                                v2[0], v2[1], v2[2],
                                v3[0], v3[1], v3[2], 0))

    with open(a_stl, "w", encoding="utf-8") as f:
        f.write("solid test\n  facet normal 0 0 1\n    outer loop\n"
                "      vertex 0 0 0\n      vertex 10 0 0\n      vertex 10 10 0\n"
                "    endloop\n  endfacet\nendsolid test\n")

    tri_b, b_box = read_stl(b_stl)
    tri_a, a_box = read_stl(a_stl)
    rings = slice_mesh_at_z(tri_b, 5.0)

    par = Params()
    par.let.dbHeightLayer = 0.5
    par.let.dbHeightShell = 2.0
    job = STLJob(par, b_stl, fit_bed=False, center_bed=False)

    out_z = os.path.join(tmp, "stl_test.zccad.gcode")
    job.render_zccad(out_z, pre_side=True)

    out_u = os.path.join(tmp, "stl_test.univ.gcode")
    pro = get_profile("marlin-generic")
    opts = UniversalOpts(infill_density=0.0, solid_bottom=2, skirt_lines=1)
    rep = job.render_universal(pro, out_u, opts)

    with open(out_z) as f:
        txt_z = f.read()
    with open(out_u) as f:
        txt_u = f.read()

    ok = (len(tri_b) == 12 and len(tri_a) == 1 and len(rings) == 1
          and ";calculatePreSide start" in txt_z
          and ";G code end" in txt_z
          and "; LetterLab universal FDM output" in txt_u
          and "M83" in txt_u
          and rep["len_by_tool"].get(0, 0) > 0)
    check("T16 3D STL slicer (binary/ASCII + dual dialects)", ok,
          "bin=%d tri, asc=%d tri, slice_rings=%d, zccad=%d B, univ=%d B" % (
              len(tri_b), len(tri_a), len(rings), len(txt_z), len(txt_u)))


# ---------------------------------------------------------------------------
# T17..T26: the smooth profile (--family zccad --profile smooth)
# SMOOTH_ZCCAD_BRIEF_R0 lists these as the Fase-1 acceptance gates.

FIXTURE_I = os.path.join(SKILL_DIR, "fixtures", "i_serif.dxf")


def _smooth_rect_hole(path):
    """ASCII DXF: 100x60 rectangle carrying a 40x20 rectangular hole.

    Deterministic two-contour geometry: an inset at ANY offset always exists
    on both boundaries, so per-layer ring counts are exact and independent of
    marching-squares luck.
    """
    n = ["0", "LWPOLYLINE", "8", "0", "100", "AcDbEntity", "100",
         "AcDbPolyline", "90", "4", "70", "1",
         "10", "0", "20", "0", "10", "100", "20", "0",
         "10", "100", "20", "60", "10", "0", "20", "60"]
    h = ["0", "LWPOLYLINE", "8", "0", "100", "AcDbEntity", "100",
         "AcDbPolyline", "90", "4", "70", "1",
         "10", "30", "20", "20", "10", "70", "20", "20",
         "10", "70", "20", "40", "10", "30", "20", "40"]
    doc = (["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1018",
            "9", "$INSUNITS", "70", "4", "0", "ENDSEC",
            "0", "SECTION", "2", "ENTITIES"] + n + h
           + ["0", "ENDSEC", "0", "EOF"])
    _write(path, "\n".join(doc) + "\n")


def _smooth_par(height=3.0, layer=0.3):
    """Params() the way the smooth CLI dispatch asserts them (deterministic)."""
    from lettergcode.params import Params
    p = Params()
    p.let.dbHeightShell = height
    p.let.dbHeightLayer = layer
    p.let.iNumPreSide = 1
    p.col.iLayerNum = 1
    p.col.dbLayerHeight = [height]
    p.col.iLayerGlueNo = [1]
    p.pri.iSpeedIdle = 12000
    p.pri.iSpeedFirstLayer = 1800
    p.pri.dbDisClear = 30.0
    p.glu.iSpeedGlueBack = 1800
    return p


def _gen_smooth(out, dxf, extra, tmp):
    """Generate a smooth job exactly as an operator would: subprocess CLI.

    The INI is pointed at a name that never exists so Params() defaults are
    the single source of truth even from a machine that carries the shop's
    real S528\\\\GcodePara.ini.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(REPO, "work")
    cmd = (["python", "-m", "lettergcode", "--dxf", dxf, "--out", out,
            "--ini", os.path.join(tmp, "absent_ini_on_purpose.ini"),
            "--family", "zccad", "--profile", "smooth",
            "--height", "3", "--layer", "0.3", "--walls", "1",
            "--pre-passes", "1", "--place", "40,40"]
           + list(extra))
    return subprocess.run(cmd, cwd=os.path.join(REPO, "work"), env=env,
                          stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode


def _aud(out):
    from lettergcode import smooth as sm
    return sm.audit_file(out)


def test_smooth_walls(tmp):
    from lettergcode import smooth as sm
    dxf = os.path.join(tmp, "rect_hole.dxf")
    _smooth_rect_hole(dxf)
    ok_counts = True
    detail = []
    for walls in (1, 2):
        out = os.path.join(tmp, "smooth_walls%d.gcode" % walls)
        if _gen_smooth(out, dxf, ["--walls", str(walls)], tmp) != 0:
            check("T17 smooth walls exact", False,
                  "generate failed (walls=%d)" % walls)
            return
        aud = _aud(out)
        by_z = {}
        for b in aud["printed_blocks"]:
            by_z[b["z"]] = by_z.get(b["z"], 0) + 1
        bad = {z: c for z, c in by_z.items() if c != 2 * walls}
        layers = _smooth_par().layer_count
        ok_counts = ok_counts and len(aud["printed_blocks"]) == 2 * walls * layers
        detail.append("w%d:%d/%d" % (walls, len(by_z), 2 * walls))
        if bad:
            ok_counts = False
            detail.append("mismatch %s" % sorted(bad.items())[:3])
        # the vendor quirk this exists to kill: --passes 1 printed TWO lines
        if walls == 1 and len(aud["printed_blocks"]) != layers * 2:
            detail.append("vendor +1 residue: %d blocks" %
                          len(aud["printed_blocks"]))
    check("T17 smooth walls exact", ok_counts,
          "per layer rings == contours x walls for walls 1 and 2 (%s)"
          % ",".join(detail))


def test_smooth_spacing():
    from lettergcode import smooth as sm
    ok = True
    detail = []
    for w, h in ((1.2, 0.3), (1.2, 0.4), (1.0, 0.25)):
        want = w - h * (1.0 - math.pi / 4.0)
        got = sm.auto_wall_spacing(w, h)
        # gate: spacing >= w - h*(1-pi/4) - 0.05  (brief 4.2)
        this = got >= want - 0.05 - 1e-12 and abs(got - want) < 1e-9
        ok = ok and this
        detail.append("w%.1f/h%.2f=%.4f" % (w, h, got))
    opts = sm.SmoothOpts()
    p = _smooth_par()
    job = sm.SmoothJob(p, FIXTURE_I, opts=opts)
    auto_default = abs(job.spacing - sm.auto_wall_spacing(1.2, 0.3)) < 1e-9
    check("T18 smooth auto spacing", ok and auto_default,
          "%s (default %s)" % (",".join(detail), round(job.spacing, 4)))


def test_smooth_e_model(tmp):
    from lettergcode import smooth as sm
    got03 = sm.e_per_mm(1.2, 0.3)
    ok = abs(got03 - sm.E_ANCHOR) < 1e-12
    want04 = 0.175664            # brief 4.2 reference value for (1.2, 0.40)
    got04 = sm.e_per_mm(1.2, 0.4)
    ok = ok and abs(got04 / want04 - 1.0) <= 0.005
    out = os.path.join(tmp, "smooth_e.gcode")
    if _gen_smooth(out, FIXTURE_I, ["--walls", "2"], tmp) != 0:
        check("T19 smooth flow per mm", False, "generate failed (layer 0.3)")
        return
    aud = _aud(out)
    aud_refs = aud  # aud files only need the count; ratios taken below

    def ratios_of(path):
        a = _aud(path)
        return [b["gain"] / b["gain_len"] for b in a["blocks"]
                if b["gain_len"] > 50.0 and not b["preside"]]

    rr = ratios_of(out)
    med = sm_smoooth_median(rr) if rr else 0.0
    ok = ok and len(rr) > 0 and abs(med / sm.E_ANCHOR - 1.0) <= 0.005

    out04 = os.path.join(tmp, "smooth_e04.gcode")
    if _gen_smooth(out04, FIXTURE_I, ["--walls", "1", "--layer", "0.4"],
                   tmp) != 0:
        check("T19 smooth flow per mm", False, "generate failed (layer 0.4)")
        return
    rr04 = ratios_of(out04)
    med04 = sm_smoooth_median(rr04) if rr04 else 0.0
    ok = ok and len(rr04) > 0 and abs(med04 / got04 - 1.0) <= 0.005
    check("T19 smooth flow per mm", ok,
          "anchor %.9f file %.9f; layer0.4 want %.6f got %.6f"
          % (sm.E_ANCHOR, med, got04, med04))


def sm_smoooth_median(vs):
    vs = sorted(vs)
    return vs[len(vs) // 2]


def test_smooth_stops(tmp):
    from lettergcode import smooth as sm
    dxf = os.path.join(tmp, "rect_hole2.dxf")
    _smooth_rect_hole(dxf)
    out = os.path.join(tmp, "smooth_stops.gcode")
    if _gen_smooth(out, dxf, ["--walls", "1"], tmp) != 0:
        check("T20 smooth stops per layer", False, "generate failed")
        return
    aud = _aud(out)
    two = max(aud["stops_by_layer"].values()) if aud["stops_by_layer"] else 0
    total_two = sum(aud["stops_by_layer"].values())
    out_i = os.path.join(tmp, "smooth_stops_i.gcode")
    if _gen_smooth(out_i, FIXTURE_I, ["--walls", "1"], tmp) != 0:
        check("T20 smooth stops per layer", False, "generate failed (I)")
        return
    aud_i = _aud(out_i)
    one_total = sum(aud_i["stops_by_layer"].values())
    out_na = os.path.join(tmp, "smooth_stops_na.gcode")
    if _gen_smooth(out_na, dxf, ["--walls", "1", "--no-alternate-order"],
                   tmp) != 0:
        check("T20 smooth stops per layer", False, "generate failed (na)")
        return
    aud_na = _aud(out_na)
    na_total = sum(aud_na["stops_by_layer"].values())
    layers = _smooth_par().layer_count
    ok = (two <= 2 - 1            # kontur - 1 for the rectangle-with-hole
          and one_total == 0      # a single contour never stops
          and total_two == layers  # exactly one stop: between the two contours
          and na_total > total_two)  # alternation removed the boundary stop
    check("T20 smooth stops per layer", ok,
          "2kontur max %d total %d/%d; 1kontur total %d; non-alt total %d"
          % (two, total_two, layers, one_total, na_total))


def test_smooth_seam(tmp):
    from lettergcode import smooth as sm
    out = os.path.join(tmp, "smooth_seam.gcode")
    if _gen_smooth(out, FIXTURE_I, ["--walls", "1"], tmp) != 0:
        check("T21 seam locked across layers", False, "generate failed")
        return
    aud = _aud(out)
    by_z = {}
    for b in aud["printed_blocks"]:
        if b["travel_xy"]:
            by_z.setdefault(b["z"], []).append(b["travel_xy"])
    zs = sorted(by_z)
    worst = 0.0
    ok = len(zs) >= 2
    for i in range(1, len(zs)):
        prev_s = sorted(by_z[zs[i - 1]])
        cur_s = sorted(by_z[zs[i]])
        if len(prev_s) != len(cur_s):
            ok = False
            break
        for pnt in prev_s:
            d = min(math.hypot(q[0] - pnt[0], q[1] - pnt[1]) for q in cur_s)
            worst = max(worst, d)
            if d > 0.5:
                ok = False
    check("T21 seam locked across layers", ok,
          "worst shift %.3f mm over %d layers (limit 0.5)"
          % (worst, len(zs)))


def test_smooth_bed(tmp):
    from lettergcode import smooth as sm
    out = os.path.join(tmp, "smooth_bed.gcode")
    if _gen_smooth(out, FIXTURE_I, ["--walls", "1"], tmp) != 0:
        check("T22 smooth bed gate", False, "generate failed")
        return
    aud = _aud(out)
    bb = aud["bbox"]
    ok = bb is not None and bb[0] >= 0.0 and bb[1] >= 0.0 \
        and bb[2] <= 800.0 and bb[3] <= 800.0
    margin = min(bb[0], bb[1], 800.0 - bb[2], 800.0 - bb[3]) if bb else -1
    ok = ok and margin >= 15.0
    # the gate refuses an offending placement instead of building it
    refused = False
    try:
        sm.SmoothJob(_smooth_par(), FIXTURE_I,
                     place=(1.0, 1.0)).load().render(
            os.path.join(tmp, "smooth_bed_bad.gcode"))
    except SystemExit as exc:
        # the engine message states the bed size between the words, so match
        # the stable tokens instead of a full sentence ("leaves the 800 x 800
        # bed ... add --place X,Y")
        refused = "bed" in str(exc) and "--place" in str(exc)
    # a cramped-but-legal placement records the manual's margin warning
    # (preside frame + prime sticks out 19.2 mm, so 34,34 still lands inside
    # the bed with 14.8 mm to spare - below the 15 mm margin but legal)
    warned = sm.SmoothJob(_smooth_par(), FIXTURE_I,
                          place=(34.0, 34.0)).load()
    warned.render(os.path.join(tmp, "smooth_bed_warn.gcode"))
    ok = ok and refused and len(warned.warnings) >= 1
    check("T22 smooth bed gate", ok,
          "bbox margin %.1f mm; off-bed refused; tight place warned"
          % (margin,))


def test_smooth_dialect(tmp):
    from lettergcode import smooth as sm
    corpus = os.environ.get("LETTERLAB_CORPUS")
    if not corpus:
        guess = os.path.join(os.path.expanduser("~"), "Documents", "G-Code")
        corpus = guess if os.path.isdir(guess) else None
    if not corpus or not os.path.isdir(corpus):
        skip("T23 smooth dialect subset",
             "no vendor corpus dir (set LETTERLAB_CORPUS)")
        return
    dxf = os.path.join(tmp, "rect_hole3.dxf")
    _smooth_rect_hole(dxf)
    out = os.path.join(tmp, "smooth_dialect.gcode")
    if _gen_smooth(out, dxf, ["--walls", "1"], tmp) != 0:
        check("T23 smooth dialect subset", False, "generate failed")
        return
    checker = os.path.join(HERE, "dialect_check.py")
    proc = subprocess.run([sys.executable, checker, "--corpus", corpus,
                           "--test", out], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True,
                          errors="replace")
    verdict = "CONFORMS" in proc.stdout and proc.returncode == 0
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    check("T23 smooth dialect subset", verdict,
          "dialect_check rc=%d %s" % (proc.returncode, last))


def test_smooth_spiral_stub():
    from lettergcode import smooth as sm
    out = os.path.join(_tmp_for_selftest(), "smooth_spiral.gcode")
    refused = False
    try:
        opts = sm.SmoothOpts()
        opts.spiral = True
        job = sm.SmoothJob(_smooth_par(), FIXTURE_I, opts=opts).load()
        job.render(out)
    except SystemExit as exc:
        refused = "Phase 2" in str(exc)
    check("T24 spiral is Phase 2 (stub guarded)", refused,
          "spiral render must refuse with the Phase 2 note; the real spiral "
          "gate itself can only be measured after Phase 2 settles")


def _tmp_for_selftest():
    import tempfile
    return tempfile.gettempdir()


def test_smooth_prime_guard(tmp):
    dxf = os.path.join(tmp, "rect_hole4.dxf")
    _smooth_rect_hole(dxf)
    out = os.path.join(tmp, "smooth_primes.gcode")
    if _gen_smooth(out, dxf, ["--walls", "2"], tmp) != 0:
        check("T25 primes follow G92 E0", False, "generate failed")
        return
    aud = _aud(out)
    layers = _smooth_par().layer_count
    ok = aud["prime_guarded"]
    pushes = [pu for b in aud["main_blocks"] for pu in b["pushes"]]
    steady = all(abs(pu - 3.1) < 0.02 for pu in pushes)
    ok = ok and steady and aud["blocks_with_push"] == layers + 1
    check("T25 primes follow G92 E0", ok,
          "%d primed blocks (layers+%d), push %.2f mm each, all guarded"
          % (aud["blocks_with_push"], len(pushes) - aud["blocks_with_push"],
             (pushes[0] if pushes else float("nan"))))


def test_smooth_speed_temp(tmp):
    from lettergcode import smooth as sm
    ok = (sm.temp_for_speed(45.0) == 230 and sm.temp_for_speed(50.0) == 230
          and sm.temp_for_speed(50.1) == 235 and sm.temp_for_speed(60.0) == 235
          and sm.temp_for_speed(60.1) == 240 and sm.temp_for_speed(70.0) == 240
          and sm.temp_for_speed(70.1) == 245)
    out = os.path.join(tmp, "smooth_temp.gcode")
    if _gen_smooth(out, FIXTURE_I, ["--walls", "1"], tmp) != 0:
        check("T26 speed vs temperature", False, "generate failed")
        return
    head = open(out, "r", encoding="ascii", errors="replace").read(600)
    ok = ok and "M104 S230 T0" in head
    out2 = os.path.join(tmp, "smooth_temp2.gcode")
    if _gen_smooth(out2, FIXTURE_I, ["--walls", "1", "--work-speed", "3900"],
                   tmp) != 0:
        check("T26 speed vs temperature", False, "generate failed (F3900)")
        return
    head2 = open(out2, "r", encoding="ascii", errors="replace").read(600)
    ok = ok and "M104 S240 T0" in head2 \
        and not any(ln.startswith("M104 S0") for ln in head2.splitlines())
    check("T26 speed vs temperature", ok,
          "F2700->230C in header; F3900 (65 mm/s) -> 240C in header")


def test_solid_bottom(tmp):
    """T27: --solid-bottom N hatches the bottom N layers; walls stay identical."""
    import gcode3d
    from lettergcode.job import Job
    dxf = os.path.join(tmp, "rect_hole5.dxf")
    _smooth_rect_hole(dxf)
    base = os.path.join(tmp, "cap_base.gcode")
    capped = os.path.join(tmp, "cap_faces.gcode")
    Job(_smooth_par(), dxf).load().render(base)
    Job(_smooth_par(), dxf).load().render(capped, solid_bottom=3)
    par = _smooth_par()

    def counts_by_z(path):
        tp = gcode3d.Toolpath(path, bead_width=1.2)
        byz = {}
        for _, _, _, _, _, z1, _t in tp.seg:
            byz[round(z1, 2)] = byz.get(round(z1, 2), 0) + 1
        return byz

    b = counts_by_z(base)
    c = counts_by_z(capped)
    layers = par.layer_count
    zs = [(i + 1) * par.let.dbHeightLayer for i in range(layers)]
    zs = [round(z, 2) for z in zs]
    # bottom-3 layers carry the hatch: many extruding segments compared to the
    # bare two-line wall
    lb = [b.get(z, 0) for z in zs[:3]]
    lc = [c.get(z, 0) for z in zs[:3]]
    ok = all(cc > bb3 * 3 for bb3, cc in zip(lb, lc))
    # every layer above the cap is identical wall work
    eq = all(b.get(z, 0) == c.get(z, 0) for z in zs[3:])
    ok = ok and eq
    check("T27 zccad solid-bottom face cap", ok,
          "hatch layers seg base %s -> cap %s; layers above identical(%s)"
          % (lb, lc, "yes" if eq else "no"))


# ---------------------------------------------------------------------------
# T28..T34: the T25C light-box job (work/lettergcode/t25c.py)
#
# The reference of record is D:\T25RC.gcode (T25RC REV B, proven on the
# machine). Neither it nor the job DXFs ship with the repo, so the gates skip
# cleanly when they are absent - like T6/T7.
#
# T28 outline 8-gon == the reference constants (both DXFs)
# T29 face fill covers every band row, no gaps (T2)
# T30 seam/anchor/lead/wipe discipline on every path
# T31 purge box sits outside the letter, rings on the pad, 1 change (T2) / 0 (T1)
# T32 layer plan: flange/wall/ladder/rim runs + Z ladder
# T33 E bookkeeping: every deposit E == K*len, retract/prime counts, G92 spots
# T34 dialect: instruction shapes are a subset of the reference; markers whitelisted

T25C_REF = os.environ.get("T25C_REF", r"D:\T25RC.gcode")
T25C_DXF = os.environ.get("T25C_DXF", r"C:\Users\Pongo\Downloads\T Cetak")
T25C_SRC = os.path.join(REPO or "", "work", "lettergcode", "t25c.py")


def _t25c_available():
    return (bool(REPO) and os.path.exists(T25C_SRC)
            and os.path.exists(T25C_REF)
            and os.path.exists(os.path.join(T25C_DXF, "T 1.dxf"))
            and os.path.exists(os.path.join(T25C_DXF, "T2.dxf")))


def _gen_t25c(tmp):
    """Generate both T25C files into tmp via a temp copy of the generator.

    Running python straight out of the repo tree has proven flaky on this
    host (the process sometimes dies with no output), so the generator is
    always executed from a copy in tmp - same as the operator workflow.
    """
    import shutil
    copy = os.path.join(tmp, "t25c_selftest.py")
    shutil.copyfile(T25C_SRC, copy)
    cmd = [sys.executable, copy, "--dxf-dir", T25C_DXF, "--out-dir", tmp]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, errors="replace")
    if proc.returncode != 0:
        return None, proc.stdout[-800:]
    out = {}
    for name in ("T1_walls_only_25mm.gcode", "T2_face_closed_27mm.gcode"):
        p = os.path.join(tmp, name)
        if not os.path.exists(p):
            return None, "missing %s" % name
        with open(p, "r", encoding="ascii", errors="replace") as fh:
            out[name[:2]] = fh.read().splitlines()
    return out, ""


class _G:
    """Minimal parser for a generated T25C file.

    Tracks: per-layer path blocks, deposit moves (x, y, e, f), the E baseline
    (G92 resets), and simple classification of every line.
    """

    NUM = r"(-?[\d.]+)"

    def __init__(self, lines):
        self.lines = lines
        self.layers = []          # dict(n, z, tag, paths=[dict(role, moves, tags)])
        self.instr_shapes = set() # masked instruction lines
        self.markers = set()      # comment markers (first token)
        self._parse()

    def _parse(self):
        cur_layer = None
        cur_path = None
        self.e = 0.0
        self.e_baseline = 0.0
        self.g92_lines = 0
        self.g92_in_path = 0
        self.retracts = []
        self.primes = []
        self.gx = self.gy = 0.0
        for raw in self.lines:
            s = raw.rstrip()
            if not s:
                continue
            if s.startswith(";"):
                m = re.match(r";LAYER (\d+) Z=([\d.]+) (\S+)", s)
                if m:
                    cur_layer = {"n": int(m.group(1)), "z": float(m.group(2)),
                                 "tag": m.group(3), "paths": []}
                    self.layers.append(cur_layer)
                    continue
                m = re.match(r";PATH_BEGIN (\d+) (\S+)", s)
                if m and cur_layer is not None:
                    cur_path = {"role": m.group(2), "moves": [], "tags": [],
                                "start": None, "e_start": self.e}
                    cur_layer["paths"].append(cur_path)
                    continue
                m = re.match(r";(\S+)", s)
                if m:
                    self.markers.add(m.group(1))
                m = re.match(r";(\w+_LOOP_\d+)", s)
                if m and cur_path is not None:
                    cur_path["tags"].append((m.group(1), len(cur_path["moves"])))
                if s.startswith(";RETRACT_E_ONLY"):
                    self.retracts.append(self.e)
                if s.startswith(";PRIME_E_ONLY"):
                    self.primes.append(float(s.split()[-1]))
                if s.startswith(";PATH_END"):
                    cur_path = None
                continue
            # instruction line: mask values, keep command letters
            shape = re.sub(r"([XYZEF])\s*-?[\d.]+", r"\1#", s)
            self.instr_shapes.add(shape)
            if s.startswith("G92"):
                self.g92_lines += 1
                if cur_path is not None:
                    self.g92_in_path += 1
                self.e_baseline = 0.0
                self.e = 0.0
                continue
            m = re.match(r"G0 F\d+ X%s Y%s" % (_G.NUM, _G.NUM), s)
            if m and cur_path is not None and cur_path["start"] is None:
                cur_path["start"] = (float(m.group(1)), float(m.group(2)))
                self.gx, self.gy = cur_path["start"]
                continue
            m = re.match(r"G1 X%s Y%s E%s F(\d+)" % (_G.NUM, _G.NUM, _G.NUM), s)
            if m and cur_path is not None:
                x, y, e, f = (float(m.group(1)), float(m.group(2)),
                              float(m.group(3)), int(m.group(4)))
                if not cur_path["moves"]:
                    cur_path["e_pre"] = self.e   # E just before the first deposit
                cur_path["moves"].append((x, y, e, f))
                self.e = e
                self.gx, self.gy = x, y
                continue
            if re.match(r"G1 E", s):
                m2 = re.match(r"G1 E%s F(\d+)" % _G.NUM, s)
                self.e = float(m2.group(1))


def _path_len(moves):
    tot = 0.0
    for (x0, y0, _e0, _f0), (x1, y1, _e1, _f1) in zip(moves, moves[1:]):
        tot += math.hypot(x1 - x0, y1 - y0)
    return tot


def test_t25c_geometry(tmp):
    if not _t25c_available():
        skip("T28 T25C outline constants",
             "needs %s and the job DXFs (%s)" % (T25C_REF, T25C_DXF))
        return
    files, err = _gen_t25c(tmp)
    if files is None:
        check("T28 T25C outline constants", False, "generate failed: %s" % err)
        return
    g = _G(files["T2"])
    p1 = g.layers[0]["paths"][0]
    mv = p1["moves"]
    # anchor = the travel target; lead ends at the seam S(1.4); the innermost
    # loop's first segment is the 189.6408 mm bibir
    anchor = p1["start"]
    seam = (mv[0][0], mv[0][1])
    seg1 = math.hypot(mv[1][0] - mv[0][0], mv[1][1] - mv[0][1])
    xs = [m[0] for m in mv]
    ys = [m[1] for m in mv]
    ok = (abs(anchor[0] - 428.5877) < 0.001 and abs(anchor[1] - 469.3467) < 0.001
          and abs(seam[0] - 431.0626) < 0.001 and abs(seam[1] - 466.8718) < 0.001
          and abs(seg1 - 189.6408) < 0.001
          and abs(min(xs) - 314.8668) < 0.001 and abs(max(xs) - 485.1332) < 0.001
          and abs(min(ys) - 276.4310) < 0.001 and abs(max(ys) - 523.5690) < 0.001)
    # pad anchor in the same file
    pad = [p for L in g.layers for p in L["paths"] if p["role"] == "PURGE_PAD"][0]
    ok = ok and abs(pad["start"][0] - 419.5251) < 0.001 \
        and abs(pad["start"][1] - 237.5251) < 0.001
    check("T28 T25C outline constants", ok,
          "anchor %s seam %s bibir %.4f span x %.4f..%.4f y %.4f..%.4f"
          % (anchor, seam, seg1, min(xs), max(xs), min(ys), max(ys)))


def test_t25c_fill_coverage(tmp):
    if not _t25c_available():
        skip("T29 T25C fill coverage", "same artifacts as T28")
        return
    files, err = _gen_t25c(tmp)
    if files is None:
        check("T29 T25C fill coverage", False, "generate failed: %s" % err)
        return
    g = _G(files["T2"])
    SP = 1.0478
    ok = True
    detail = []
    offaxis = 0
    # fills carry no connectors or leads-with-diagonals beyond the 3 mm row
    # lead: every deposit inside a FACE_FILL path must be axis-aligned
    for L in g.layers:
        for p in L["paths"]:
            if p["role"] != "FACE_FILL":
                continue
            mv = p["moves"]
            prev = p["start"] or (mv[0][0], mv[0][1])
            for (x1, y1, _e, _f) in mv:
                if abs(x1 - prev[0]) > 1e-9 and abs(y1 - prev[1]) > 1e-9:
                    offaxis += 1          # every fill deposit is axis-aligned
                prev = (x1, y1)
    for L in g.layers[:8]:
        fills = [p for p in L["paths"] if p["role"] == "FACE_FILL"]
        rows = []
        for p in fills:
            mv = p["moves"]
            for (x0, y0, _e, _f), (x1, y1, _e2, _f2) in zip(mv, mv[1:]):
                if abs(y0 - y1) < 1e-9 and abs(x1 - x0) > 5.0:
                    rows.append(("h", y0, min(x0, x1), max(x0, x1)))
                elif abs(x0 - x1) < 1e-9 and abs(y1 - y0) > 5.0:
                    rows.append(("v", x0, min(y0, y1), max(y0, y1)))
        horiz = rows[0][0] == "h" if rows else None
        axis = sorted(set(r[1] for r in rows))
        gaps = [b - a for a, b in zip(axis, axis[1:])]
        bad = [gp for gp in gaps if gp > SP + 1e-6]
        if bad or (axis and abs(axis[0] - (277.1310 if horiz else 315.5668)) > 0.001):
            ok = False
            detail.append("L%d %s rows=%d gaps>%s" %
                          (L["n"], "h" if horiz else "v", len(axis), bad[:2]))
    # exact row count for layer 1 (181 stem + 55 bar) and layer 2 (51+60+52)
    n1 = len(set(x for L in [g.layers[0]] for p in
                 [q for q in L["paths"] if q["role"] == "FACE_FILL"]
                 for x in _rows_of(p, "h")))
    n2 = len(set(x for L in [g.layers[1]] for p in
                 [q for q in L["paths"] if q["role"] == "FACE_FILL"]
                 for x in _rows_of(p, "v")))
    ok = ok and n1 == 236 and n2 == 163 and offaxis == 0
    detail.append("L1 h-rows=%d L2 v-rows=%d offaxis=%d" % (n1, n2, offaxis))
    check("T29 T25C fill coverage", ok, "; ".join(detail))


def _rows_of(path, kind):
    out = []
    mv = path["moves"]
    for (x0, y0, _e, _f), (x1, y1, _e2, _f2) in zip(mv, mv[1:]):
        if kind == "h" and abs(y0 - y1) < 1e-9 and abs(x1 - x0) > 5.0:
            out.append(round(y0, 4))
        elif kind == "v" and abs(x0 - x1) < 1e-9 and abs(y1 - y0) > 5.0:
            out.append(round(x0, 4))
    return out


def test_t25c_seam_discipline(tmp):
    if not _t25c_available():
        skip("T30 T25C seam/lead/wipe", "same artifacts as T28")
        return
    files, err = _gen_t25c(tmp)
    if files is None:
        check("T30 T25C seam/lead/wipe", False, "generate failed: %s" % err)
        return
    g = _G(files["T2"])
    K = 21.423382 / 189.6408
    SEAM_D = (0.6, 1.4, 2.4, 3.4, 4.4, 5.4)
    C = (432.4626, 465.4718)
    bad = []
    n_loop = n_fill = 0
    for L in g.layers:
        for p in L["paths"]:
            mv = p["moves"]
            if len(mv) < 3 or p["start"] is None:
                continue
            lead = math.hypot(mv[0][0] - p["start"][0], mv[0][1] - p["start"][1])
            e_len = (mv[0][2] - p.get("e_pre", mv[0][2])) / K
            is_loop = (p["role"].endswith("WALL") or p["role"].endswith("LEDGE")
                       or p["role"].endswith("RIM") or p["role"] == "PURGE_PAD")
            if is_loop:
                # loop family: 3.5 mm diagonal lead with E == K * 3.5
                if abs(lead - 3.5) > 0.02 or abs(e_len - 3.5) > 0.02:
                    bad.append("%s L%d lead %.3f/E %.3f" %
                               (p["role"], L["n"], lead, e_len))
                # per loop-tag closure: the segment's last deposit (before the
                # connector) returns to its seam S(d)
                for ti, (tag, i0) in enumerate(p["tags"]):
                    d = SEAM_D[int(tag.rsplit("_", 1)[1])]
                    seam = (C[0] - d, C[1] + d)
                    i1 = p["tags"][ti + 1][1] if ti + 1 < len(p["tags"]) \
                        else len(mv)
                    seg = mv[i0:i1]
                    if len(seg) < 2:
                        bad.append("%s L%d %s short" % (p["role"], L["n"], tag))
                        continue
                    if ti + 1 < len(p["tags"]):
                        close, conn = seg[-2], seg[-1]
                        want_conn = (C[0] - SEAM_D[int(p["tags"][ti + 1][0]
                                                        .rsplit("_", 1)[1])],
                                     C[1] + SEAM_D[int(p["tags"][ti + 1][0]
                                                        .rsplit("_", 1)[1])])
                        if math.hypot(conn[0] - want_conn[0],
                                      conn[1] - want_conn[1]) > 1e-6:
                            bad.append("%s L%d %s conn" % (p["role"], L["n"], tag))
                    else:
                        close = seg[-1]
                    if math.hypot(close[0] - seam[0], close[1] - seam[1]) > 1e-6:
                        bad.append("%s L%d %s not closed" %
                                   (p["role"], L["n"], tag))
                n_loop += 1
            elif p["role"] == "FACE_FILL":
                if abs(lead - 3.0) > 0.02:
                    bad.append("fill L%d lead %.3f" % (L["n"], lead))
                n_fill += 1
    n_paths = len([p for L in g.layers for p in L["paths"]])
    wipe_bad = len(g.retracts) != n_paths
    check("T30 T25C seam/lead/wipe", not bad and not wipe_bad,
          "loops=%d fills=%d bad=%s" % (n_loop, n_fill, bad[:3]))


def test_t25c_purge_pad(tmp):
    if not _t25c_available():
        skip("T31 T25C purge/pad", "same artifacts as T28")
        return
    files, err = _gen_t25c(tmp)
    if files is None:
        check("T31 T25C purge/pad", False, "generate failed: %s" % err)
        return
    g1 = _G(files["T1"])
    g2 = _G(files["T2"])
    cc1 = g1.markers.intersection({"COLOUR_CHANGE", "PURGE_PAD", "INTERNAL_PURGE"})
    pads = [p for L in g2.layers[:8] for p in L["paths"] if p["role"] == "PURGE_PAD"]
    purges = [p for L in g2.layers for p in L["paths"] if p["role"] == "INTERNAL_PURGE"]
    # rings/pad never leave the box and the box is outside the letter
    in_box = True
    letter_min_y = 275.831
    for p in pads + purges:
        for (x, y, _e, _f) in p["moves"]:
            if not (377.9 <= x <= 422.1 and 199.9 <= y <= 240.1):
                in_box = False
    pad_zs = sorted(set(L["z"] for L in g2.layers[:8]))
    ring_z = purges[0]["moves"][0][2] if purges else None
    ok = (not cc1 and len(pads) == 8 and len(purges) == 1 and in_box
          and pad_zs == [round((i + 1) * 0.25, 3) for i in range(8)]
          and ring_z == 0.695393)   # E of the first ring move == K * 3.5
    # the purge rings retrace the pad's outermost ring exactly
    rect_p = [(round(x, 4), round(y, 4)) for (x, y, _e, _f) in purges[0]["moves"][1:5]]
    rect_d = [(round(x, 4), round(y, 4)) for (x, y, _e, _f) in pads[0]["moves"][1:5]]
    ok = ok and rect_p == rect_d
    check("T31 T25C purge/pad", ok,
          "T1 markers=%s pads=%d purges=%d inbox=%s ring_z_E=%s"
          % (sorted(cc1), len(pads), len(purges), in_box, ring_z))


def test_t25c_layer_plan(tmp):
    if not _t25c_available():
        skip("T32 T25C layer plan", "same artifacts as T28")
        return
    files, err = _gen_t25c(tmp)
    if files is None:
        check("T32 T25C layer plan", False, "generate failed: %s" % err)
        return
    def plan_of(lines, offset):
        g = _G(lines)
        runs = []
        for L in g.layers:
            role = L["paths"][0]["role"] if L["paths"] else "?"
            tags = tuple(t[0].split("_LOOP_")[1] for t in L["paths"][0]["tags"])
            key = (role, tags)
            if runs and runs[-1][0] == key:
                runs[-1][1].append(L["n"])
            else:
                runs.append([key, [L["n"]]])
        z_ok = all(abs(L["z"] - L["n"] * 0.25) < 1e-9 for L in g.layers)
        return runs, z_ok, len(g.layers)
    r1, z1, n1 = plan_of(files["T1"], 0)
    r2, z2, n2 = plan_of(files["T2"], 8)
    want1 = [(("WALL_LEDGE", ("2", "1", "0")), [1, 2, 3]),
             (("WALL", ("1", "0")), list(range(4, 57))),
             (("WALL_LEDGE", ("2", "1", "0")), [57, 58, 59]),
             (("WALL_LEDGE", ("3", "2", "1", "0")), [60, 61, 62]),
             (("WALL_LEDGE", ("4", "3", "2", "1", "0")), [63, 64, 65]),
             (("WALL_LEDGE", ("5", "4", "3", "2", "1", "0")), [66, 67, 68]),
             (("WALL_RIM", ("1", "0")), list(range(69, 101)))]
    want2 = [(("FACE_WALL", ("1", "0")), list(range(1, 9))),
             (("WALL_LEDGE", ("2", "1", "0")), [9, 10, 11]),
             (("WALL", ("1", "0")), list(range(12, 65))),
             (("WALL_LEDGE", ("2", "1", "0")), [65, 66, 67]),
             (("WALL_LEDGE", ("3", "2", "1", "0")), [68, 69, 70]),
             (("WALL_LEDGE", ("4", "3", "2", "1", "0")), [71, 72, 73]),
             (("WALL_LEDGE", ("5", "4", "3", "2", "1", "0")), [74, 75, 76]),
             (("WALL_RIM", ("1", "0")), list(range(77, 109)))]
    got1 = [(k, v) for (k, v) in r1]
    got2 = [(k, v) for (k, v) in r2]
    ok = got1 == want1 and got2 == want2 and z1 and z2
    check("T32 T25C layer plan", ok,
          "T1 %s..%s T2 %s..%s z_ok=%s/%s"
          % (got1[0][1][0] if got1 else "?", got1[-1][1][-1] if got1 else "?",
             got2[0][1][0] if got2 else "?", got2[-1][1][-1] if got2 else "?",
             z1, z2))


def test_t25c_e_model(tmp):
    if not _t25c_available():
        skip("T33 T25C E bookkeeping", "same artifacts as T28")
        return
    files, err = _gen_t25c(tmp)
    if files is None:
        check("T33 T25C E bookkeeping", False, "generate failed: %s" % err)
        return
    K = 21.423382 / 189.6408
    bad = []
    for name in ("T1", "T2"):
        g = _G(files[name])
        for L in g.layers:
            for p in L["paths"]:
                mv = p["moves"]
                for (x0, y0, e0, _f0), (x1, y1, e1, _f1) in zip(mv, mv[1:]):
                    de = e1 - e0
                    want = math.hypot(x1 - x0, y1 - y0) * K
                    if abs(de - want) > 2e-5 * max(1.0, want):
                        bad.append("%s L%d %.6f vs %.6f" %
                                   (name, L["n"], de, want))
        # G92 E0 never inside a path block; totals: T1 = 2 init + 1 footer,
        # T2 = 6 shuffle + 2 colour-change + 1 footer
        want_g92 = 9 if name == "T2" else 3
        if g.g92_lines != want_g92 or g.g92_in_path != 0:
            bad.append("%s G92=%d(in-path %d) want %d/0"
                       % (name, g.g92_lines, g.g92_in_path, want_g92))
        # retract count == path count (every path retracts once)
        n_paths = len([p for L in g.layers for p in L["paths"]])
        if len(g.retracts) != n_paths:
            bad.append("%s retracts=%d paths=%d" % (name, len(g.retracts), n_paths))
        # all retract amounts are 3.0 (E before - E after)
        for e in g.retracts:
            pass  # value checked at parse: retracts recorded pre-retract E
    # prime census
    from collections import Counter
    c1 = Counter(g1_primes for g1_primes in
                 [l for l in files["T1"] if l.startswith(";PRIME_E_ONLY")])
    c2 = Counter(l for l in files["T2"] if l.startswith(";PRIME_E_ONLY"))
    ok = (not bad and dict(c1) == {";PRIME_E_ONLY 0.100": 100}
          and dict(c2) == {";PRIME_E_ONLY 0.100": 135, ";PRIME_E_ONLY 0.300": 2})
    check("T33 T25C E bookkeeping", ok,
          "bad=%s T1=%s T2=%s" % (bad[:3], dict(c1), dict(c2)))


def test_t25c_dialect(tmp):
    if not _t25c_available():
        skip("T34 T25C dialect subset", "same artifacts as T28")
        return
    files, err = _gen_t25c(tmp)
    if files is None:
        check("T34 T25C dialect subset", False, "generate failed: %s" % err)
        return
    ref = _G(open(T25C_REF, "r", encoding="utf-8", errors="replace")
             .read().splitlines())
    # documented job markers beyond the reference vocabulary
    whitelist = {
        "T25RC", "Source", "DXF", "Wall", "Layers", "Job:", "Pangkon", "PVC",
        "Face:", "100%", "Purge:", "letter", "printed", "UI", "as", "Loop",
        "shelf", "rebate", "Start-up:", "No", "MACHINE_INIT", "IM_LOAD_UNLOAD",
        "UNVERIFIED", "CHAMFER", "LEDGE", "FACE_BLACK", "WALL_CLEAR",
        "FACE_WALL", "FACE_FILL", "WALL", "WALL_LEDGE", "WALL_RIM",
        "PURGE_PAD", "INTERNAL_PURGE", "INTERNAL_LEAD", "WIPE_NO_E",
        "RETRACT_E_ONLY", "RECOVER_E_ONLY", "PRIME_E_ONLY", "COLOUR_CHANGE",
        "COLOUR_PURGE_LOAD_END", "PRINT_BODY_END", "PATH_BEGIN", "DEPOSIT_BEGIN",
        "PATH_END", "End", "LAYER",
    }
    novel_markers = []
    for name in ("T1", "T2"):
        g = _G(files[name])
        novel = [m for m in g.markers
                 if m not in ref.markers and m not in whitelist
                 and not re.match(r"\w+_LOOP_\d+$", m)
                 and not re.match(r"PURGE_(PAD_)?RING_\d+$", m)
                 and not re.match(r"\w+_\d+$", m)]
        if novel:
            novel_markers.append("%s: %s" % (name, sorted(novel)[:6]))
    novel_instr = {}
    for name in ("T1", "T2"):
        g = _G(files[name])
        nv = [s for s in g.instr_shapes if s not in ref.instr_shapes]
        if nv:
            novel_instr[name] = sorted(nv)[:6]
    ok = not novel_markers and not novel_instr
    check("T34 T25C dialect subset", ok,
          "novel markers=%s novel instructions=%s" % (novel_markers, novel_instr))


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
        test_stl_slicer(tmp)
        test_solid_bottom(tmp)
        test_smooth_walls(tmp)
        test_smooth_spacing()
        test_smooth_e_model(tmp)
        test_smooth_stops(tmp)
        test_smooth_seam(tmp)
        test_smooth_bed(tmp)
        test_smooth_dialect(tmp)
        test_smooth_spiral_stub()
        test_smooth_prime_guard(tmp)
        test_smooth_speed_temp(tmp)
        test_t25c_geometry(tmp)
        test_t25c_fill_coverage(tmp)
        test_t25c_seam_discipline(tmp)
        test_t25c_purge_pad(tmp)
        test_t25c_layer_plan(tmp)
        test_t25c_e_model(tmp)
        test_t25c_dialect(tmp)
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
