"""Probe a DXF before generating: what will actually become toolpath.

Reports entity census, closed/open counts, real-world size, nesting depth,
noise candidates and the bed placement envelope. Writes nothing, so it is safe
on read-only inputs outside the workspace.

  python dxfprobe.py FILE.dxf [--min-area 2] [--bed 800] [--json]

Use it to answer "why did the generator say no closed contours" and "how big is
this really", both of which change the parameters you should pick.
"""
from __future__ import annotations

import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def find_repo():
    """Walk up from this script until the directory holding work/lettergcode is found."""
    d = os.path.abspath(HERE)
    while True:
        if os.path.isdir(os.path.join(d, "work", "lettergcode")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


REPO = os.environ.get("LETTERLAB_ENGINE") or find_repo()
if REPO:
    sys.path.append(os.path.join(REPO, "work"))

try:
    from lettergcode import dxf, geom
except ImportError:
    print("lettergcode engine not found; set LETTERLAB_ENGINE to the repo root")
    raise SystemExit(2)


def ring_area(r):
    s = 0.0
    n = len(r)
    for i in range(n):
        x0, y0 = r[i]
        x1, y1 = r[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def depth_of(r, others):
    """How many other rings contain this ring's first point (0 = outermost)."""
    d = 0
    for o in others:
        if o is r or len(o) < 3:
            continue
        if geom.point_in_contours(r[0], [o]):
            d += 1
    return d


def probe(path, min_area=2.0, bed=800.0):
    rep = {"file": os.path.abspath(path),
           "exists": os.path.exists(path)}
    if not rep["exists"]:
        return rep
    rep["bytes"] = os.path.getsize(path)

    raw = list(dxf._pairs(path))
    rep["entity_census"] = dict(collections.Counter(
        v for code, v in raw if code == 0))

    ents = dxf.read_dxf(path)
    rep["sources"] = dict(collections.Counter(e["source"] for e in ents))
    rings, chains = dxf.close_rings(ents)
    rings = [geom.dedupe(r) for r in rings if len(geom.dedupe(r)) >= 3]
    chains = [geom.dedupe(c) for c in chains if len(c) >= 2]
    rep["closed_rings"] = len(rings)
    rep["open_chains"] = len(chains)

    areas = sorted(abs(ring_area(r)) for r in rings)
    if areas:
        rep["ring_area_mm2"] = {"min": round(areas[0], 2),
                                "median": round(areas[len(areas) // 2], 2),
                                "max": round(areas[-1], 2)}
    rep["noise_candidates"] = sum(1 for a in areas if a < min_area)

    if rings:
        x0, y0, x1, y1 = geom.bbox(rings)
        rep["bbox_mm"] = {"w": round(x1 - x0, 2), "h": round(y1 - y0, 2),
                          "x0": round(x0, 2), "y0": round(y0, 2),
                          "x1": round(x1, 2), "y1": round(y1, 2)}
        depths = collections.Counter(depth_of(r, rings) for r in rings)
        rep["nesting"] = {"outer": depths.get(0, 0), "holes": depths.get(1, 0),
                          "deeper": sum(c for k, c in depths.items() if k >= 2)}
        if x1 - x0 > bed or y1 - y0 > bed:
            rep["fit"] = ("DOES NOT FIT: %.1f x %.1f mm exceeds the %.0f mm bed - "
                          "scale the DXF or split the job" % (x1 - x0, y1 - y0, bed))
        else:
            rep["fit"] = "fits the %.0f mm bed; centred placement would be --place %.0f,%.0f" % (
                bed, (bed - (x1 - x0)) / 2.0, (bed - (y1 - y0)) / 2.0)
    if not rings and chains:
        rep["note"] = ("no closed rings; the generator will fall back to treating "
                       "each open chain as a ring, which prints the outline twice "
                       "and is usually not what a logo needs - close the gaps first")
    if not rings and not chains:
        rep["note"] = ("nothing importable. Check whether the geometry is inside a "
                       "BLOCK with an INSERT, or an external reference (XREF)")
    return rep


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    path = argv[0]
    min_area = 2.0
    bed = 800.0
    if "--min-area" in argv:
        min_area = float(argv[argv.index("--min-area") + 1])
    if "--bed" in argv:
        bed = float(argv[argv.index("--bed") + 1])
    rep = probe(path, min_area=min_area, bed=bed)
    if "--json" in argv:
        print(json.dumps(rep, indent=2))
        return 0
    print("file            : %s (%s bytes)" % (rep.get("file"), rep.get("bytes")))
    print("entities        : %s" % rep.get("entity_census"))
    print("flattened from  : %s" % rep.get("sources"))
    print("closed rings    : %d   open chains: %d" %
          (rep["closed_rings"], rep["open_chains"]))
    if "ring_area_mm2" in rep:
        print("ring area mm2   : %s" % rep["ring_area_mm2"])
    print("noise < %.1f mm2 : %d" % (min_area, rep["noise_candidates"]))
    if "bbox_mm" in rep:
        b = rep["bbox_mm"]
        print("size            : %.2f x %.2f mm" % (b["w"], b["h"]))
        print("nesting         : %s" % rep["nesting"])
        print("bed             : %s" % rep["fit"])
    if "note" in rep:
        print("NOTE            : %s" % rep["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
