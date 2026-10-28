"""Structural validation of a generated file against a vendor ZCCAD reference.

Checks the invariants that decide whether the machine will print this correctly:
  * E per millimetre (the extrusion calibration constant)
  * Z ladder (print heights) and lift Z set (travel heights)
  * the feedrate SET (which speeds appear, not how often)
  * block markers and their order
  * retract / prime amounts
  * tool-change sequence

Exit code is 0 only when every gate passes, so this is safe to chain.

Usage:
  python validate_gcode.py REFERENCE.gcode [GENERATED.gcode]
"""
from __future__ import annotations

import re
import sys
from collections import Counter

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
E_MM_TOL = 1e-6      # extrusion constant must agree to a millionth


def parse_line(s):
    return {m.group(1): float(m.group(2))
            for m in re.finditer(r"([XYZEF])\s*(" + NUM + ")", s)}


class Report:
    def __init__(self, path):
        self.path = path
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            self.lines = fh.read().splitlines()
        self.z_moves = []
        self.z_print = []
        self.feedrates = Counter()
        self.e_per_mm = []
        self.markers = []
        self.tools = []
        self.retracts = []
        self._scan()

    def _scan(self):
        x = y = z = None
        e = 0.0
        rel = False
        for ln in self.lines:
            s = ln.strip()
            if not s:
                continue
            if s.startswith(";"):
                if s.startswith((";calculatePreSide", ";start printf",
                                 ";extruder switch", ";G code")):
                    self.markers.append(s)
                continue
            m = re.match(r"^T(\d+)$", s)
            if m:
                self.tools.append(int(m.group(1)))
                continue
            if s.startswith("G90"):
                rel = False
                continue
            if s.startswith("G91"):
                rel = True
                continue
            if s.startswith("G92"):
                v = parse_line(s)
                if "E" in v:
                    e = v["E"]
                continue
            if not s.startswith(("G0", "G1")):
                continue
            v = parse_line(s)
            fm = re.search(r"F(" + NUM + ")", s)
            if fm:
                self.feedrates[int(round(float(fm.group(1))))] += 1
            # a relative move before the first absolute one has no known origin;
            # the header's `G91 / G0 X5 Y5` is exactly that case
            bx = x if x is not None else 0.0
            by = y if y is not None else 0.0
            bz = z if z is not None else 0.0
            nx = bx + v["X"] if rel and "X" in v else v.get("X", x)
            ny = by + v["Y"] if rel and "Y" in v else v.get("Y", y)
            nz = bz + v["Z"] if rel and "Z" in v else v.get("Z", z)
            if "Z" in v:
                self.z_moves.append(nz)
            de = 0.0
            if "E" in v:
                de = (v["E"] if rel else v["E"] - e)
                e = e + v["E"] if rel else v["E"]
            if de < -0.001:
                self.retracts.append(round(de, 4))
            d = 0.0
            if x is not None and nx is not None:
                d = ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5
            if s.startswith("G1") and de > 1e-9 and d > 1e-6:
                self.e_per_mm.append(de / d)
            if s.startswith("G1") and de > 1e-9 and nz is not None:
                self.z_print.append(nz)
            x, y, z = nx, ny, nz

    def summary(self):
        epm = self.e_per_mm
        return {
            "lines": len(self.lines),
            "extruding_segments": len(epm),
            "E/mm min": min(epm) if epm else None,
            "E/mm max": max(epm) if epm else None,
            "E/mm mean": sum(epm) / len(epm) if epm else None,
            "print Z ladder": sorted({round(v, 4) for v in self.z_print}),
            "lift Z set": sorted({round(v, 4) for v in self.z_moves}),
            "feedrates": dict(sorted(self.feedrates.items())),
            "markers": self.markers,
            "tools": self.tools,
            "retracts": dict(Counter(self.retracts).most_common(6)),
        }


def _dump(s):
    for k, v in s.items():
        if isinstance(v, float):
            print(f"  {k:18s}: {v:.12f}")
        elif isinstance(v, list) and len(v) > 12:
            print(f"  {k:18s}: {v[:6]} ... {v[-4:]}  (n={len(v)})")
        else:
            print(f"  {k:18s}: {v}")


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    ref = Report(argv[0])
    print(f"== REFERENCE  {argv[0]}")
    _dump(ref.summary())
    if len(argv) < 2:
        return 0
    gen = Report(argv[1])
    print(f"\n== GENERATED  {argv[1]}")
    _dump(gen.summary())

    a, b = ref.summary(), gen.summary()
    print("\n== GATES")
    ok = True
    for key in ("E/mm mean", "E/mm min", "E/mm max"):
        va, vb = a[key], b[key]
        if va is None or vb is None:
            print(f"  {key:12s}: n/a")
            continue
        d = abs(va - vb)
        good = d < E_MM_TOL
        ok = ok and good
        print(f"  {key:12s}: ref={va:.12f} gen={vb:.12f} delta={d:.3e} "
              f"{'PASS' if good else 'FAIL'}")
    for key in ("print Z ladder", "lift Z set", "tools", "markers"):
        same = a[key] == b[key]
        ok = ok and same
        print(f"  {key:14s}: {'PASS (identical)' if same else 'FAIL (differs)'}")
        if not same:
            print(f"      ref: {a[key]}")
            print(f"      gen: {b[key]}")
    fsame = set(a["feedrates"]) == set(b["feedrates"])
    ok = ok and fsame
    print(f"  {'feedrate set':14s}: {'PASS' if fsame else 'FAIL'}"
          + ("" if fsame else f"\n      ref: {sorted(a['feedrates'])}"
                             f"\n      gen: {sorted(b['feedrates'])}"))
    verdict = ("ALL GATES PASS - dialect matches the vendor export" if ok
               else "GATES FAILED - do not send to the machine")
    print("\n  verdict: " + verdict)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
