"""Breakdown a corpus of ZCCAD exports, then derive what is INVARIANT.

The point: a dialect is not "the shape of one file". It is the set of properties
every real export shares. This tool measures each file and reports, per property,
whether all files agree (invariant), most agree (likely invariant with variants),
or they scatter (a parameter, not a rule).

  python corpus_audit.py FILE... [--ref FILE] [--detail]
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, OrderedDict

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
RX = re.compile(r"([XYZEF])\s*(" + NUM + r")")
RT = re.compile(r"^T(\d+)$")
RM = re.compile(r"^M(\d+)")
RG = re.compile(r"^(G\d+)")
RCOMMENT = re.compile(r"^;")


def parse(path):
    st = OrderedDict()
    st["file"] = os.path.basename(path)
    st["bytes"] = os.path.getsize(path)

    comments = []
    tools = []
    feedrates = Counter()
    markers = []
    retracts = Counter()
    primes = Counter()
    gcodes = Counter()
    mcodes = Counter()
    e_per_mm = []
    zs_print = set()
    zs_lift = set()
    xs = []
    ys = []
    path_mm = 0.0
    e_total = 0.0
    lines = 0
    x = y = z = 0.0
    e = 0.0
    e_abs = 0.0          # ZCCAD writes ABSOLUTE E, so deltas must be derived
    rel = False
    tool = 0
    pending_first_move = True

    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            lines += 1
            s = raw.strip()
            if not s:
                continue
            if RCOMMENT.match(s):
                comments.append(s)
                if ";" in s and len(s) > 1 and not s[1].isalnum():
                    continue
                markers.append(s)
                continue

            m = RT.match(s)
            if m:
                tool = int(m.group(1))
                tools.append(tool)
                continue
            mg = RG.match(s)
            if mg:
                gcodes[mg.group(1)] += 1
            mm = RM.match(s)
            if mm:
                mcodes["M" + mm.group(1)] += 1
            if s.startswith("G92"):
                v = {k: float(n) for k, n in RX.findall(s)}
                if "E" in v:
                    e_abs = v["E"]
                continue
            if s in ("G90", "G28"):
                if s == "G90":
                    rel = False
                continue
            if s == "G91":
                rel = True
                continue
            if not s.startswith("G1") and not s.startswith("G0"):
                continue

            vals = {k: float(v) for k, v in RX.findall(s)}
            f = vals.get("F")
            if f:
                feedrates[int(f)] += 1
            nx = x + vals["X"] if (rel and "X" in vals) else vals.get("X", x)
            ny = y + vals["Y"] if (rel and "Y" in vals) else vals.get("Y", y)
            nz = z + vals["Z"] if (rel and "Z" in vals) else vals.get("Z", z)
            if "E" in vals:
                if rel:
                    de = vals["E"]
                else:
                    de = vals["E"] - e_abs      # absolute E -> increment
                    e_abs = vals["E"]
            else:
                de = 0.0

            d = ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5
            if nz != z:
                zs_lift.add(round(nz, 3))
            if s.startswith("G1") and de > 1e-9:
                zs_print.add(round(z, 3))
                if d > 1e-6:
                    e_per_mm.append(de / d)
                    path_mm += d
                    e_total += de
                    xs.append(nx)
                    ys.append(ny)
            elif s.startswith("G1") and de < -1e-9:
                retracts[round(de, 2)] += 1
            elif s.startswith("G1") and "E" in vals and de > 1e-9 and d <= 1e-6:
                primes[round(de, 3)] += 1
            x, y, z = nx, ny, nz
            e += de

    zp = sorted(zs_print)
    st["lines"] = lines
    st["markers"] = markers
    st["tools_seq"] = tools
    st["tool_set"] = sorted({t for t in tools})
    st["feedrate_set"] = sorted(feedrates)
    st["gcodes"] = dict(sorted(gcodes.items()))
    st["mcodes"] = dict(sorted(mcodes.items()))
    st["retracts"] = dict(sorted(retracts.items()))
    st["print_layers"] = len(zp)
    st["z_lo"] = zp[0] if zp else None
    st["z_hi"] = zp[-1] if zp else None
    st["lift_z_n"] = len(zs_lift)
    if zp:
        diffs = Counter(round(zp[i + 1] - zp[i], 3) for i in range(len(zp) - 1))
        st["layer_heights"] = dict(diffs.most_common(4))
    else:
        st["layer_heights"] = {}
    if e_per_mm:
        s = sorted(e_per_mm)
        st["e_mm_mean"] = round(sum(e_per_mm) / len(e_per_mm), 12)
        st["e_mm_min"] = round(s[0], 12)
        st["e_mm_max"] = round(s[-1], 12)
    else:
        st["e_mm_mean"] = st["e_mm_min"] = st["e_mm_max"] = None
    st["bbox"] = (round(max(xs) - min(xs), 2), round(max(ys) - min(ys), 2)) if xs else None
    st["path_m"] = round(path_mm / 1000.0, 1)
    st["e_total_mm"] = round(e_total, 1)
    st["first_comment"] = comments[0] if comments else ""
    return st


def show(st, detail=False):
    print("=" * 78)
    print("%s   %s bytes   %s lines" % (st["file"], format(st["bytes"], ","), format(st["lines"], ",")))
    print("  first comment : %s" % st["first_comment"])
    print("  print layers  : %s   Z %s .. %s"
          % (st["print_layers"], st["z_lo"], st["z_hi"]))
    print("  layer heights : %s" % st["layer_heights"])
    print("  tools         : %s" % st["tool_set"])
    print("  tool sequence : %s" % st["tools_seq"])
    print("  feedrates     : %s" % st["feedrate_set"])
    print("  retracts      : %s" % st["retracts"])
    print("  E/mm mean     : %s" % st["e_mm_mean"])
    print("  part bbox mm  : %s   extruding path %s m   total E %s mm"
          % (st["bbox"], st["path_m"], st["e_total_mm"]))
    if detail:
        print("  G codes       : %s" % st["gcodes"])
        print("  M codes       : %s" % st["mcodes"])
        print("  lift Z count  : %s" % st["lift_z_n"])
    print("  markers (%d)  :" % len(st["markers"]))
    for m in st["markers"]:
        print("      %s" % m)


def invariant(rows):
    n = len(rows)
    print("\n" + "=" * 78)
    print("INVARIANTS ACROSS %d FILES" % n)
    print("=" * 78)

    def report(label, values, show_all=True):
        cnt = Counter(values)
        if len(cnt) == 1:
            print("  INVARIANT  %-22s %s" % (label, cnt.most_common(1)[0][0]))
        else:
            top, k = cnt.most_common(1)[0]
            print("  %-9s  %-22s %d/%d = %s"
                  % ("COMMON" if k == n else "VARIES", label, k, n, top))
            if len(cnt) <= 4 and len(cnt) > 1:
                for v, c in cnt.most_common():
                    print("             %-22s %d file(s): %s" % ("", c, v))

    report("first comment", [r["first_comment"] for r in rows])
    report("tool set", [tuple(r["tool_set"]) for r in rows])
    report("feedrate set", [tuple(r["feedrate_set"]) for r in rows])
    report("retract amounts", [tuple(r["retracts"]) for r in rows])
    report("layer heights", [tuple(r["layer_heights"]) for r in rows])
    report("E/mm mean", [r["e_mm_mean"] for r in rows])
    print("\n  per-file scale (a file whose total E is tiny is not a real part):")
    for r in rows:
        print("      %-32s bbox=%-18s path=%9s m  totalE=%10s mm"
              % (r["file"], r["bbox"], r["path_m"], r["e_total_mm"]))
    report("G-code set", [tuple(r["gcodes"]) for r in rows])
    report("M-code set", [tuple(r["mcodes"]) for r in rows])

    print("\n  marker vocabulary (which markers appear, and in how many files):")
    mc = Counter()
    for r in rows:
        for m in set(r["markers"]):
            mc[m] += 1
    for m, c in mc.most_common():
        print("      %2d/%d  %s" % (c, n, m))

    print("\n  marker ORDER, per file:")
    seen = Counter(tuple(r["markers"]) for r in rows)
    for seq, c in seen.most_common():
        print("      %d file(s): %s" % (c, " -> ".join(s.lstrip(";") for s in seq)))

    print("\n  tool sequence, per file:")
    for r in rows:
        print("      %-32s %s" % (r["file"], r["tools_seq"]))


def main(argv):
    files = [a for a in argv if not a.startswith("-")]
    detail = "--detail" in argv
    if not files:
        print(__doc__)
        return 2
    expanded = []
    for f in files:
        if os.path.isdir(f):
            for n in sorted(os.listdir(f)):
                if n.lower().endswith(".gcode"):
                    expanded.append(os.path.join(f, n))
        else:
            expanded.append(f)
    rows = [parse(f) for f in expanded]
    for r in rows:
        show(r, detail)
    invariant(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
