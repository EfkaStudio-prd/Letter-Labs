"""Per-layer toolpath audit: ring counts, path length and extruded volume.

Compares two G-code files layer by layer so a structural difference shows up as
"layer 12 prints 6 rings, the reference prints 4" instead of "the files differ".

  python labcheck.py FILE.gcode                    # audit one file
  python labcheck.py REF.gcode MINE.gcode          # side-by-side per layer

A "ring" is one continuous extruding polyline at a fixed Z; a move that
retracts (dE < 0) or travels without extrusion closes the current ring.
"""
from __future__ import annotations

import math
import re
import sys

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
RX = re.compile(r"([XYZEF])\s*(" + NUM + ")")


def audit(path):
    """Return {z: {'rings': n, 'len': mm, 'pts': n}} plus file-level totals."""
    layers = {}
    x = y = z = 0.0
    e = 0.0
    rel = False
    open_ring = False
    tool = 0
    tools_by_z = {}
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            t = raw.strip()
            if not t or t[0] == ";":
                continue
            if t.startswith("G90"):
                rel = False
                continue
            if t.startswith("G91"):
                rel = True
                continue
            if t.startswith("M83"):
                continue
            m = re.match(r"^T(\d+)$", t)
            if m:
                tool = int(m.group(1))
                continue
            if t.startswith("G92"):
                v = dict((k, float(a)) for k, a in RX.findall(t))
                if "E" in v:
                    e = v["E"]
                continue
            if not t.startswith(("G0", "G1")):
                continue
            v = dict((k, float(a)) for k, a in RX.findall(t))
            nx = x + v["X"] if rel and "X" in v else v.get("X", x)
            ny = y + v["Y"] if rel and "Y" in v else v.get("Y", y)
            nz = z + v["Z"] if rel and "Z" in v else v.get("Z", z)
            de = 0.0
            if "E" in v:
                if rel:
                    de = v["E"]
                    e += v["E"]
                else:
                    de = v["E"] - e
                    e = v["E"]
            d = math.hypot(nx - x, ny - y)
            ext = de > 1e-9 and d > 1e-9
            L = layers.setdefault(round(nz, 4), {"rings": 0, "len": 0.0, "pts": 0,
                                                 "tools": set()})
            if ext:
                if not open_ring or abs(nz - z) > 1e-9:
                    L["rings"] += 1
                    open_ring = True
                L["len"] += d
                L["pts"] += 1
                L["tools"].add(tool)
                tools_by_z.setdefault(round(nz, 4), set()).add(tool)
            else:
                open_ring = False
            x, y, z = nx, ny, nz
    return layers, tools_by_z


def summarize(tag, layers):
    rings = sum(v["rings"] for v in layers.values())
    length = sum(v["len"] for v in layers.values())
    pts = sum(v["pts"] for v in layers.values())
    zs = sorted(layers)
    print("%-6s layers=%d  rings=%d  extruding path=%.1f m  points=%d  z %.2f..%.2f"
          % (tag, len(zs), rings, length / 1000.0, pts, zs[0], zs[-1]))
    per = {}
    for z in zs:
        r = layers[z]["rings"]
        per.setdefault(r, []).append(z)
    print("       ring-count histogram: " + ", ".join(
        "%d rings on %d layer(s)" % (k, len(v)) for k, v in sorted(per.items())))
    return per


def main(argv):
    if len(argv) < 1:
        print(__doc__)
        return 2
    la, ta = audit(argv[0])
    per_a = summarize("REF", la)
    if len(argv) < 2:
        return 0
    lb, tb = audit(argv[1])
    per_b = summarize("MINE", lb)
    print("\n== per-layer ring diff (first 20 mismatches) ==")
    zs = sorted(set(la) | set(lb))
    bad = 0
    for z in zs:
        ra = la.get(z, {}).get("rings", 0)
        rb = lb.get(z, {}).get("rings", 0)
        if ra != rb:
            bad += 1
            if bad <= 20:
                da = la.get(z, {}).get("len", 0.0)
                db = lb.get(z, {}).get("len", 0.0)
                print("  z=%-8.2f ref %d rings / %7.1f mm   mine %d rings / %7.1f mm"
                      % (z, ra, da, rb, db))
    print("  total layers with a ring-count difference: %d of %d" % (bad, len(zs)))
    print("\n== path length per extruder ==")
    tools_a = {}
    for z, ts in ta.items():
        for t in ts:
            tools_a[t] = tools_a.get(t, 0.0) + la[z]["len"]
    tools_b = {}
    for z, ts in tb.items():
        for t in ts:
            tools_b[t] = tools_b.get(t, 0.0) + lb[z]["len"]
    for t in sorted(set(tools_a) | set(tools_b)):
        print("  T%d  ref %8.1f m   mine %8.1f m" %
              (t, tools_a.get(t, 0.0) / 1000, tools_b.get(t, 0.0) / 1000))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
