"""Prove a generated file uses ONLY the vendor's instruction vocabulary.

`labcheck.py` compares geometry. `validate_gcode.py` compares value sets. This
compares the one thing they both miss: the *shape* of every line. A file can match
every numeric gate and still contain an instruction the firmware has never seen.

Method: mask every coordinate/extrusion/feed value but keep command numbers
(`G0 G1 G21 ... M104 M106 ... T0 T1 T2`) intact, then require that the test file's
masked-line set is a SUBSET of the union taken from real exports.

  python dialect_check.py --corpus DIR [--test FILE ...] [--min-support 0.8]

A line shape the vendor never writes is a NOVEL line and fails the check. So does
an E/mm that disagrees with the corpus, or a marker that most vendor files carry
and the test file omits.

Exit code 0 only when every test file conforms.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
# Mask only the value, keep the letter. Coordinates, extrusion and feedrate are
# the things that legitimately differ between jobs.
MASK = re.compile(r"([XYZEF])\s*" + NUM)
RT = re.compile(r"^T(\d+)$")
RX = re.compile(r"([XYZEF])\s*(" + NUM + r")")

# A shape seen in fewer than this fraction of the corpus is a feature, not a rule
DEFAULT_SUPPORT = 0.8


def shape(line):
    return MASK.sub(r"\1#", line.strip())


def scan(path):
    """Return (shapes, e_per_mm_samples, markers) for one file."""
    shapes = set()
    markers = []
    ratios = []
    x = y = z = 0.0
    e_abs = 0.0
    rel = False
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            s = raw.strip()
            if not s:
                continue
            if s.startswith(";"):
                markers.append(s)
                continue
            if RT.match(s):
                shapes.add(shape(s))
                continue
            if s.startswith("G92"):
                v = {k: float(n) for k, n in RX.findall(s)}
                if "E" in v:
                    e_abs = v["E"]
                shapes.add(shape(s))
                continue
            if s == "G90":
                rel = False
                shapes.add(s)
                continue
            if s == "G91":
                rel = True
                shapes.add(s)
                continue
            if not (s.startswith("G1") or s.startswith("G0")):
                # any other command must still be a shape the vendor writes
                shapes.add(shape(s))
                continue

            shapes.add(shape(s))
            v = {k: float(n) for k, n in RX.findall(s)}
            nx = x + v["X"] if (rel and "X" in v) else v.get("X", x)
            ny = y + v["Y"] if (rel and "Y" in v) else v.get("Y", y)
            nz = z + v["Z"] if (rel and "Z" in v) else v.get("Z", z)
            if "E" in v:
                if rel:
                    de = v["E"]
                else:
                    de = v["E"] - e_abs
                    e_abs = v["E"]
            else:
                de = 0.0
            if s.startswith("G1") and de > 1e-9:
                d = ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5
                if d > 1e-6:
                    ratios.append(de / d)
            x, y, z = nx, ny, nz
    return shapes, ratios, markers


def main(argv):
    corpus = []
    tests = []
    support = DEFAULT_SUPPORT
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--corpus":
            i += 1
            corpus.append(argv[i])
        elif a == "--test":
            i += 1
            tests.append(argv[i])
        elif a == "--min-support":
            i += 1
            support = float(argv[i])
        else:
            tests.append(a)
        i += 1

    files = []
    for c in corpus:
        if os.path.isdir(c):
            files += [os.path.join(c, n) for n in sorted(os.listdir(c))
                      if n.lower().endswith(".gcode")]
        else:
            files.append(c)
    if not files:
        print(__doc__)
        return 2

    vocab = {}          # shape -> an example real line
    shape_hits = Counter()
    marker_hits = Counter()
    all_ratios = []
    n_ok = 0
    print("== corpus ==")
    for f in files:
        sh, ratios, mk = scan(f)
        r = sorted(ratios)
        med = r[len(r) // 2] if r else None
        # a file whose E/mm is orders of magnitude off is a broken export, not a
        # reference: it writes near-zero extrusion and cannot have printed
        broken = med is not None and not (0.01 < med < 10)
        print("   %-34s shapes=%3d  E/mm=%-14s %s"
              % (os.path.basename(f), len(sh),
                 ("%.9f" % med) if med is not None else "-",
                 "EXCLUDED (broken E)" if broken else ""))
        if broken:
            continue
        n_ok += 1
        for s in sh:
            vocab.setdefault(s, "")
            shape_hits[s] += 1
        for m in set(mk):
            marker_hits[m] += 1
        all_ratios += ratios

    all_ratios.sort()
    ref = all_ratios[len(all_ratios) // 2]
    print("\n   usable files    : %d" % n_ok)
    print("   vocabulary      : %d distinct line shapes" % len(vocab))
    print("   E/mm reference  : %.12f" % ref)

    required = {m for m, c in marker_hits.items() if c / n_ok >= support}
    print("   required markers: %d (present in >=%.0f%% of files)"
          % (len(required), support * 100))
    for m in sorted(required):
        print("        %s" % m)

    if not tests:
        return 0

    bad = 0
    for t in tests:
        print("\n== test: %s ==" % os.path.basename(t))
        sh, ratios, mk = scan(t)
        novel = sorted(sh - set(vocab))
        r = sorted(ratios)
        emm = r[len(r) // 2] if r else 0.0
        dev = abs(emm - ref) / ref if ref else 1.0
        missing = sorted(required - set(mk))
        ok = not novel and dev < 1e-6 and not missing

        print("   line shapes   : %d" % len(sh))
        print("   novel shapes  : %d %s" % (len(novel), "" if not novel else "<-- UNKNOWN TO VENDOR"))
        for s in novel[:10]:
            print("        %s" % s)
        print("   E/mm median   : %.12f  (delta %.2e)  %s"
              % (emm, dev, "PASS" if dev < 1e-6 else "FAIL"))
        print("   markers       : %d present, %d required missing %s"
              % (len(mk), len(missing), "" if not missing else "<-- MISSING"))
        for m in missing:
            print("        %s" % m)
        print("   verdict       : %s" % ("CONFORMS" if ok else "DOES NOT CONFORM"))
        if not ok:
            bad += 1

    print("\n%d/%d test files conform" % (len(tests) - bad, len(tests)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
