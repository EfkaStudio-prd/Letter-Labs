"""Audit which tool prints which Z band in a ZCCAD export.

Tracks modal tool state and records every *extruding* move, so header purge
dances (which switch T at a fixed Z) do not pollute the zone map.

  python tool_zones.py FILE.gcode [--gcode-tool]
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
RXY = re.compile(r"X(" + NUM + r")")
RYY = re.compile(r"Y(" + NUM + r")")
RZ = re.compile(r"Z(" + NUM + r")")
RE = re.compile(r"E(" + NUM + r")")


def audit(path):
    tool = 0
    x = y = z = 0.0
    e = 0.0
    rel = False
    per_z = defaultdict(lambda: {"tools": set(), "rings": 0, "len": 0.0, "e": 0.0})
    order = []                      # (z, tool) the first time this tool prints here
    seen = set()
    prev_xy = None
    open_ring = False

    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for ln in fh:
            s = ln.strip()
            if not s or s[0] in ";#":
                continue
            m = re.match(r"^T(\d+)$", s)
            if m:
                tool = int(m.group(1))
                continue
            if s == "G90":
                rel = False
                continue
            if s == "G91":
                rel = True
                continue
            if not s.startswith("G1"):
                continue

            mx, my, mz, me = (RXY.search(s), RYY.search(s), RZ.search(s), RE.search(s))
            nx = x + float(mx.group(1)) if (rel and mx) else (float(mx.group(1)) if mx else x)
            ny = y + float(my.group(1)) if (rel and my) else (float(my.group(1)) if my else y)
            nz = z + float(mz.group(1)) if (rel and mz) else (float(mz.group(1)) if mz else z)
            de = float(me.group(1)) if me else 0.0

            if nz != z or (nx, ny) != (x, y):
                d = ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5
                k = round(z, 3)
                if de > 1e-9:
                    if not open_ring:
                        per_z[k]["rings"] += 1
                        open_ring = True
                    per_z[k]["tools"].add(tool)
                    per_z[k]["len"] += d
                    per_z[k]["e"] += de
                    if tool not in seen:
                        seen.add(tool)
                        order.append((k, tool))
                elif de < -1e-9:
                    open_ring = False          # retract closes the ring
            x, y, z = nx, ny, nz
    return per_z, order


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    per_z, order = audit(argv[0])
    zs = sorted(per_z)

    print("== first layer each tool prints =")
    for k, t in order:
        print("   T%d first prints at z=%.2f" % (t, k))

    print("\n== per-layer tool map ==")
    prev = None
    for k in zs:
        key = tuple(sorted(per_z[k]["tools"]))
        if key != prev:
            band_from = k
            print("   z>=%-6.2f  tools=%-8s rings/layer at start=%d"
                  % (k, ",".join("T%d" % t for t in key), per_z[k]["rings"]))
            prev = key

    print("\n== Z band per tool (mm) ==")
    by_tool = defaultdict(list)
    for k in zs:
        for t in per_z[k]["tools"]:
            by_tool[t].append(k)
    for t in sorted(by_tool):
        lo, hi = min(by_tool[t]), max(by_tool[t])
        layer_m = sum(per_z[k]["len"] for k in zs if t in per_z[k]["tools"]) / 1000.0
        fil_m = sum(per_z[k]["e"] for k in zs if t in per_z[k]["tools"]) / 1000.0
        print("   T%-2d z %6.2f .. %6.2f  (%5.2f mm tall, %4d layers)  path %7.1f m  fil %6.2f m"
              % (t, lo, hi, hi - lo, len(by_tool[t]), layer_m, fil_m))

    print("\n== distinct Z %d, range %.2f .. %.2f ==" % (len(zs), zs[0], zs[-1]))
    if "--zones" in argv:
        print("\n== every layer ==")
        for k in zs:
            print("   z=%6.2f  tools=%-8s rings=%4d  len=%8.1f mm"
                  % (k, ",".join("T%d" % t for t in sorted(per_z[k]["tools"])),
                     per_z[k]["rings"], per_z[k]["len"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
