"""T25C — T-letter light-box generator, replica of the T25RC REV B dialect.

Reference of record: D:\\T25RC.gcode (T25RC REV B - REVISED FOR PRODUCTION &
TESTING, proven on the machine). Every marker, speed, E rule and seam rule in
this file was measured from that file:

  layer         ;LAYER n Z=z.zzz TAG          (n*0.25 mm, TAG = FACE_*/WALL_CLEAR)
  path          ;PATH_BEGIN i ROLE ... ;PATH_END
  loop tag      ;FACE_WALL_LOOP_n / WALL_LOOP_n / WALL_LEDGE_LOOP_n /
                WALL_RIM_LOOP_n  (index = inset ladder: 0:-0.6 1:-1.4 2:-2.4 ...)
  seam          every loop starts/ends at S(d) = C + (-d, +d); loops printed
                innermost first, CW, joined by short connectors (F840, K E)
  anchor        I = S(d_first) + 3.5 mm diagonal into the hollow; travel and
                WIPE_NO_E target; PRIME_E_ONLY blob sits there (proven)
  lead          loops: 3.5 mm anchor->seam; fills: 3.0 mm along the row
  wipe          loops: back to anchor; fills: 2.0 mm back along the last row
  E             absolute cumulative; EVERY deposit move = length * K_WALL;
                retract 3.0 / recover 3.0; prime 0.100 (0.300 for purge path);
                G92 E0 only at start and after the colour-change load
  speeds        travel 12000, wall 2100, face-wall 1260(L1)/1890, fill
                1260(L1)/1680, lead+connectors 840, wipe/retract 1800,
                recover 4800, prime 60, purge 1680, load 1500/3000, unload 1800
  z lift        travel height = layer Z + 0.6
  fill          solid face: perimeters first, then serpentine rows at pitch =
                band/ceil(band/1.0478), inset 1.3 from the outline, horizontal
                on odd layers / vertical on even layers, path cut where the
                band span changes (proven L1 path 3 starts at 484.4332,466.7718)

Job decisions (user-confirmed): T1 walls only (CLEAR slot 3 / T2 tool), T2
face 2 mm BLACK (slot 1 / T0) + 25 mm walls, both 0.25 mm layers, bottom
flange -2.4 mm (3 layers), top shelf ladder -2.4..-5.4 (4 steps x 3 layers),
8 mm rebate above the shelf closed by PVC. Purge before the colour change =
3 concentric rings around a 44x40 pad placed OUTSIDE the letter at
(378..422, 200..240); the pad itself is 8 black ring layers printed with the
face so the rings never print in the air. T1 has no colour change, no pad.

Known reference artifact NOT replicated: on its face layers the reference
splits the bar-band rows near the stem/bar junction into short truncated
paths (its scanline stumbles on the skewed DXF edges), leaving ~4 mm gaps in
the face. This generator fills every band row full-width (light-tight face,
per the "tutup halus/rapat" requirement); the verified checkpoints of the
band model (band boundaries, pitch, global serpentine parity, L1 path 3
start, lead/wipe discipline) still match the reference exactly.

Pure stdlib (no shapely/numpy on this machine).
"""
from __future__ import annotations

import math
import os
import sys

# --------------------------------------------------------------------------
# dialect constants (measured, see module docstring)
# --------------------------------------------------------------------------
LH = 0.25
K_WALL = 21.423382 / 189.6408          # E per mm of deposit (filament mm)
SPACING = 1.0478                        # nominal row spacing
FILL_INSET = 1.3                        # face fill inset from the outline
WALL_INSETS = {0: 0.6, 1: 1.4, 2: 2.4, 3: 3.4, 4: 4.4, 5: 5.4}
FLANGE_LAYERS = 3                       # bottom/front flange at -2.4
STEP_LAYERS = 3                         # layers per shelf step
RIM_LAYERS = 32                         # 8 mm rebate above the shelf
LEAD_LOOP = 3.5                         # anchor -> seam (loop paths)
LEAD_FILL = 3.0                         # along the first row (fill paths)
WIPE_FILL = 2.0                         # wipe back along the last row
LIFT = 0.6                              # travel height above layer Z
RETRACT = 3.0
PRIME_STD = 0.100
PRIME_BIG = 0.300
SEAM_DIAG = 3.5 / math.sqrt(2.0)        # anchor offset = 2.4748737

F_TRAVEL = 12000
F_WALL = 2100
F_FACEWALL_L1 = 1260
F_FACEWALL = 1890
F_FILL_L1 = 1260
F_FILL = 1680
F_LEAD = 840
F_WIPE = 1800
F_RETRACT = 1800
F_RECOVER = 4800
F_PRIME = 60
F_PURGE = 1680
F_LOAD = 1500
F_LOAD_CC = 3000
F_UNLOAD = 1800

BOX = (378.0, 200.0, 422.0, 240.0)      # purge/pad box, OUTSIDE the letter
PAD_LAYERS = 8
RING_INSETS = (0.0, 1.5, 3.0)

BED_CENTRE = (400.0, 400.0)
EXPECT_BBOX = (314.2668, 275.8310, 485.7332, 524.1690)
EXPECT_STEM = 64.925                    # stem width at the raw outline
GEOM_TOL = 0.02


# --------------------------------------------------------------------------
# small geometry (pure python)
# --------------------------------------------------------------------------
def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def signed_area(ring):
    s = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def bbox(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def rdp(pts, eps):
    """Douglas-Peucker on an open chain."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i0, i1 = stack.pop()
        if i1 <= i0 + 1:
            continue
        ax, ay = pts[i0]
        bx, by = pts[i1]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-12
        best, bi = -1.0, -1
        for i in range(i0 + 1, i1):
            px, py = pts[i]
            d = abs((px - ax) * dy - (py - ay) * dx) / L
            if d > best:
                best, bi = d, i
        if best > eps:
            keep[bi] = True
            stack.append((i0, bi))
            stack.append((bi, i1))
    return [p for p, k in zip(pts, keep) if k]


def rdp_ring(pts, eps):
    """Douglas-Peucker for a CLOSED ring (no duplicate end point): split at
    the two farthest-apart vertices and simplify each chain."""
    n = len(pts)
    a = 0
    b = max(range(n), key=lambda i: dist(pts[i], pts[0]))
    if b == a:
        return list(pts)
    ch1 = rdp(pts[a:b + 1], eps)
    ch2 = rdp(pts[b:] + [pts[a]], eps)
    return ch1[:-1] + ch2[:-1]


def line_isect(p0, p1, q0, q1):
    """Intersection of two infinite lines through p0-p1 and q0-q1."""
    x1, y1 = p0
    x2, y2 = p1
    x3, y3 = q0
    x4, y4 = q1
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        raise ValueError("parallel inset edges")
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def inset_miter(ring, d):
    """Inward miter offset of a CW ring (interior on the right).

    Output vertex i corresponds to input vertex i, so a ring that starts at
    the seam corner yields an inset ring that starts at S(d).
    """
    n = len(ring)
    edges = []
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        nx, ny = dy / L, -dx / L          # inward normal for CW
        edges.append(((x0 + nx * d, y0 + ny * d), (x1 + nx * d, y1 + ny * d)))
    out = []
    for i in range(n):
        out.append(line_isect(edges[i - 1][0], edges[i - 1][1],
                              edges[i][0], edges[i][1]))
    return out


def _unify_bar_undersides(poly, tol=1.0):
    """The T has exactly two interior horizontal edges (the bar undersides).
    The job DXFs draw them up to ~0.3 mm apart; the proven reference outline
    shares one Y (the outermost = lower one). Snap them together."""
    n = len(poly)
    ys = [p[1] for p in poly]
    y0, y1 = min(ys), max(ys)
    hits = [i for i in range(n)
            if abs(poly[i][1] - poly[(i + 1) % n][1]) <= 1e-9
            and y0 + 0.5 * tol < poly[i][1] < y1 - 0.5 * tol]
    if len(hits) == 2:
        y = min(poly[i][1] for i in hits)
        for i in hits:
            j = (i + 1) % n
            poly[i] = (poly[i][0], y)
            poly[j] = (poly[j][0], y)
    return poly


def _snap_orthogonal(poly, dev=1.0, min_len=20.0):
    """Snap long near-axis edges of a closed polygon, updating the shared
    vertices (outermost coordinate wins, matching the reference outline),
    then drop consecutive duplicates."""
    n = len(poly)
    pts = [list(p) for p in poly]
    for i in range(n):
        j = (i + 1) % n
        ax, ay = pts[i]
        bx, by = pts[j]
        dx, dy = bx - ax, by - ay
        if math.hypot(dx, dy) < min_len:
            continue
        if abs(dy) <= dev and abs(dy) < abs(dx):
            y = max(ay, by)
            pts[i][1] = pts[j][1] = y
        elif abs(dx) <= dev and abs(dx) < abs(dy):
            x = max(ax, bx)
            pts[i][0] = pts[j][0] = x
    out = []
    for p in pts:
        q = (p[0], p[1])
        if not out or dist(out[-1], q) > 1e-6:
            out.append(q)
    if len(out) > 1 and dist(out[0], out[-1]) <= 1e-6:
        out.pop()
    return out


def load_outline(dxf_path):
    """Read the T outline from the job DXF, simplify to the 8-gon, centre it
    on the bed, normalise to CW starting at the concave-right seam corner C
    with the next vertex down the stem."""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [here, os.path.dirname(here),
             r"C:\Users\Pongo\Downloads\3D Print Software S528\3D Print Software S528"
             r"\_publish\Letter-Labs\work"]
    for p in cands:
        if p not in sys.path and os.path.isdir(p):
            sys.path.insert(0, p)
    from lettergcode import dxf, geom          # noqa: PLC0415

    ents = dxf.read_dxf(dxf_path)
    rings, _chains = dxf.close_rings(ents)
    rings = [geom.dedupe(r) for r in rings if len(geom.dedupe(r)) >= 3]

    def area(r):
        return abs(signed_area(r))

    rings.sort(key=area, reverse=True)
    ring = rings[0]                      # largest ring = the T outline
    ring = [tuple(p) for p in ring]
    # The job DXFs are drawn slightly askew (top/underside edges deviate up to
    # ~0.9 mm from axis-aligned). The proven reference outline is perfectly
    # orthogonal, so simplify, then snap near-axis long edges.
    poly = None
    for eps in (0.35, 0.5, 0.8, 1.0, 1.2, 1.5):
        cand = rdp_ring(ring, eps)
        cand = [list(p) for p in _snap_orthogonal(cand)]
        _unify_bar_undersides(cand)
        cand = [tuple(p) for p in cand]
        if len(cand) == 8:
            poly = cand
            break
    if poly is None:
        raise ValueError("outline did not simplify to the 8-gon")

    # centre on the bed
    x0, y0, x1, y1 = bbox(poly)
    poly = [(x + (BED_CENTRE[0] - (x0 + x1) / 2.0),
             y + (BED_CENTRE[1] - (y0 + y1) / 2.0)) for x, y in poly]

    # checks against the proven reference geometry
    bx0, by0, bx1, by1 = bbox(poly)
    for got, want in zip((bx0, by0, bx1, by1), EXPECT_BBOX):
        if abs(got - want) > GEOM_TOL:
            raise ValueError("outline bbox %s != reference %s"
                             % ((bx0, by0, bx1, by1), EXPECT_BBOX))
    stem = None
    xs = sorted(set(round(v[0], 3) for v in poly))
    for i in range(len(xs) - 1):
        for j in range(i + 1, len(xs)):
            w = xs[j] - xs[i]
            if abs(w - EXPECT_STEM) < 0.5:
                stem = w
    if stem is None:
        raise ValueError("stem width not found in outline")

    # CW (interior on the right)
    if signed_area(poly) > 0:
        poly.reverse()

    # start at the concave-right corner C = reflex vertex with max X,
    # next vertex = the one down the stem
    def cross_prev(a, b, c):
        return (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])

    reflex = [i for i in range(len(poly))
              if cross_prev(poly[i - 1], poly[i], poly[(i + 1) % len(poly)]) > 0]
    if len(reflex) != 2:
        raise ValueError("expected 2 reflex corners on the T, got %d" % len(reflex))
    ci = max(reflex, key=lambda i: poly[i][0])
    poly = poly[ci:] + poly[:ci]
    if poly[1][1] > poly[0][1]:
        poly = [poly[0]] + list(reversed(poly[1:]))
    return poly


# --------------------------------------------------------------------------
# writer
# --------------------------------------------------------------------------
class Writer:
    """Emits the T25RC REV B dialect with self-consistent E bookkeeping.

    E for every deposit move is length * K_WALL computed from the same rounded
    coordinates that are printed, so the file's own E/mm is exactly K_WALL
    (the reference file wobbles at the 1e-4 level from its own rounding)."""

    def __init__(self):
        self.lines = []
        self.e = 0.0
        self.cx = self.cy = 0.0
        self.cz = 0.0
        self.path_n = 0
        self.layer_n = 0

    def c(self, s):
        self.lines.append(s)

    # -- motion ------------------------------------------------------------
    def travel(self, xy):
        x, y = round(xy[0], 4), round(xy[1], 4)
        self.c("G0 F%d X%.4f Y%.4f" % (F_TRAVEL, x, y))
        self.cx, self.cy = x, y

    def drop(self, z):
        self.c("G0 F%d Z%.3f" % (F_TRAVEL, z))
        self.cz = z

    def lift(self):
        self.c("G0 F%d Z%.3f" % (F_TRAVEL, self.cz + LIFT))
        self.cz += LIFT

    def deposit_to(self, xy, f, k=K_WALL):
        x, y = round(xy[0], 4), round(xy[1], 4)
        d = math.hypot(x - self.cx, y - self.cy)
        self.e += d * k
        self.c("G1 X%.4f Y%.4f E%.6f F%d" % (x, y, self.e, f))
        self.cx, self.cy = x, y

    def prime(self, amount, dwell):
        self.c(";PRIME_E_ONLY %.3f" % amount)
        self.e += amount
        self.c("G1 E%.6f F%d" % (self.e, F_PRIME))
        self.c("G4 P%d" % dwell)

    def recover(self):
        self.c(";RECOVER_E_ONLY %.1f" % RETRACT)
        self.e += RETRACT
        self.c("G1 E%.6f F%d" % (self.e, F_RECOVER))

    def retract(self):
        self.c(";RETRACT_E_ONLY %.1f" % RETRACT)
        self.e -= RETRACT
        self.c("G1 E%.6f F%d" % (self.e, F_RETRACT))

    # -- path skeleton -----------------------------------------------------
    def path_begin(self, role, target, z, recover=True,
                   prime=PRIME_STD, dwell=200, lift_first=False):
        self.path_n += 1
        self.c(";PATH_BEGIN %d %s" % (self.path_n, role))
        if lift_first:
            self.lift()
        self.travel(target)
        self.drop(z)
        if recover:
            self.recover()
        self.prime(prime, dwell)
        self.c(";DEPOSIT_BEGIN %s" % role)

    def path_end(self, wipe_xy):
        self.c(";WIPE_NO_E")
        x, y = round(wipe_xy[0], 4), round(wipe_xy[1], 4)
        self.c("G0 F%d X%.4f Y%.4f" % (F_WIPE, x, y))
        self.cx, self.cy = x, y
        self.retract()
        self.lift()
        self.c(";PATH_END")

    # -- letter loops ------------------------------------------------------
    def loop_path(self, role, loops, z, f_loop, tag_fmt, recover=True):
        """One path of concentric CW loops, innermost first.

        loops: list of (inset, tag_index) deepest first. The polygon for each
        inset already starts at S(d) because the outline starts at C."""
        d0 = loops[0][0]
        seam0 = (round(self.C[0] - d0, 4), round(self.C[1] + d0, 4))
        anchor = (round(seam0[0] - SEAM_DIAG, 4),
                  round(seam0[1] + SEAM_DIAG, 4))
        self.path_begin(role, anchor, z, recover=recover)
        self.c(";INTERNAL_LEAD")
        self.deposit_to(seam0, F_LEAD)
        for idx, (d, ti) in enumerate(loops):
            self.c(";%s" % (tag_fmt % ti))
            poly = inset_miter(self.outline, d)
            for v in poly[1:]:
                self.deposit_to(v, f_loop)
            self.deposit_to(poly[0], f_loop)          # close at S(d)
            if idx + 1 < len(loops):
                dn = loops[idx + 1][0]
                nxt = (round(self.C[0] - dn, 4), round(self.C[1] + dn, 4))
                self.deposit_to(nxt, F_LEAD)          # connector to next loop
        self.path_end(anchor)

    # -- face fill ---------------------------------------------------------
    def fill_paths(self, z, layer_i):
        poly = inset_miter(self.outline, FILL_INSET)
        horizontal = (layer_i % 2 == 1)
        rows = fill_rows(poly, horizontal)
        f = F_FILL_L1 if layer_i == 1 else F_FILL

        # split into paths where the band (span) changes
        paths, cur = [], [rows[0]]
        for prev, row in zip(rows, rows[1:]):
            if row[3] != prev[3]:
                paths.append(cur)
                cur = [row]
            else:
                cur.append(row)
        paths.append(cur)

        for gi_g, grp in enumerate(paths):
            g0 = grp[0][4]
            pos, lo, hi, _band, _gi = grp[0]
            start = (pos, lo) if g0 % 2 == 0 else (pos, hi)
            if horizontal:
                start = (start[1], start[0])      # (x, y)
            # the reference gives the first fill path of layer 1 a big prime
            big = (layer_i == 1 and gi_g == 0)
            self.path_begin("FACE_FILL", start, z,
                            prime=PRIME_BIG if big else PRIME_STD,
                            dwell=500 if big else 200)
            self.c(";INTERNAL_LEAD")
            along = (hi - lo) if g0 % 2 == 0 else (lo - hi)
            sign = 1.0 if along > 0 else -1.0
            lead_end = (start[0] + sign * LEAD_FILL, start[1]) if horizontal \
                else (start[0], start[1] + sign * LEAD_FILL)
            self.deposit_to(lead_end, F_LEAD)
            self.c(";FACE_FILL")
            # the first row runs from the lead to the far end in the travel
            # direction (odd parity rows start at the hi side)
            row_end = (lo, pos) if g0 % 2 == 1 else (hi, pos)
            if not horizontal:
                row_end = (pos, lo) if g0 % 2 == 1 else (pos, hi)
            self.deposit_to(row_end, f)
            for (_p, _lo, _hi, _b, gi) in grp[1:]:
                row = rows[gi]
                pos2, lo2, hi2, _b2, _g2 = row[0], row[1], row[2], row[3], row[4]
                s2 = (pos2, lo2) if gi % 2 == 0 else (pos2, hi2)
                e2 = (pos2, hi2) if gi % 2 == 0 else (pos2, lo2)
                if horizontal:
                    s2, e2 = (s2[1], s2[0]), (e2[1], e2[0])
                self.deposit_to(s2, f)                # perpendicular jog
                self.deposit_to(e2, f)                # the row
            last = grp[-1]
            lp, llo, lhi, _b, lgi = last
            lend = (lhi, lp) if lgi % 2 == 0 else (llo, lp)
            if horizontal:
                lend = (lend[1], lend[0])
            lstart = (lp, llo) if lgi % 2 == 0 else (lp, lhi)
            if horizontal:
                lstart = (lstart[1], lstart[0])
            dx = lend[0] - lstart[0]
            dy = lend[1] - lstart[1]
            L = math.hypot(dx, dy) or 1e-12
            wipe = (lend[0] - dx / L * WIPE_FILL, lend[1] - dy / L * WIPE_FILL)
            self.path_end(wipe)

    # -- pad / purge rings -------------------------------------------------
    @staticmethod
    def ring_rect(d):
        x0, y0, x1, y1 = BOX
        return [(x1 - d, y1 - d), (x1 - d, y0 + d),
                (x0 + d, y0 + d), (x0 + d, y1 - d)]

    def rings_path(self, role, z, recover, prime, dwell, f_ring, f_conn,
                   tag_fmt, lift_first=False):
        anchor = (round(BOX[2] - SEAM_DIAG, 4), round(BOX[3] - SEAM_DIAG, 4))
        seam0 = (BOX[2], BOX[3])
        self.path_begin(role, anchor, z, recover=recover,
                        prime=prime, dwell=dwell, lift_first=lift_first)
        self.c(";INTERNAL_LEAD")
        self.deposit_to(seam0, F_LEAD)
        for i, d in enumerate(RING_INSETS):
            self.c(";%s" % (tag_fmt % (i + 1)))
            rect = self.ring_rect(d)
            for v in rect[1:]:
                self.deposit_to(v, f_ring)
            self.deposit_to(rect[0], f_ring)
            if i + 1 < len(RING_INSETS):
                nd = RING_INSETS[i + 1]
                self.deposit_to((BOX[2] - nd, BOX[3] - nd), f_conn)
        self.path_end(anchor)

    # -- colour change -----------------------------------------------------
    def colour_change(self, z):
        """Verbatim T0_TO_T2 change of the reference, at the pad anchor."""
        anchor = (round(BOX[2] - SEAM_DIAG, 4), round(BOX[3] - SEAM_DIAG, 4))
        self.c(";COLOUR_CHANGE T0_TO_T2")
        self.travel(anchor)
        self.c("G0 F%d Z%.3f" % (F_TRAVEL, z))
        self.cz = z
        self.c("G92 E0")
        self.c("G91")
        self.c("G1 E-85 F%d" % F_UNLOAD)
        self.c("M104 S230 T0")
        self.c("T2")
        self.c("G92 E0")
        self.c("G90")
        self.c("G1 E85 F%d" % F_LOAD_CC)
        self.c("G92 E0")
        self.e = 0.0
        self.c(";COLOUR_PURGE_LOAD_END")


# --------------------------------------------------------------------------
# fill row model
# --------------------------------------------------------------------------
def _span_at(poly, axis_val, horizontal):
    """Extent of the polygon along the row axis at a given position."""
    hits = []
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if horizontal:
            if (y0 <= axis_val) != (y1 <= axis_val):
                t = (axis_val - y0) / (y1 - y0)
                hits.append(x0 + t * (x1 - x0))
        else:
            if (x0 <= axis_val) != (x1 <= axis_val):
                t = (axis_val - x0) / (x1 - x0)
                hits.append(y0 + t * (y1 - y0))
    if len(hits) < 2:
        raise ValueError("degenerate fill span")
    return min(hits), max(hits)


def fill_rows(poly, horizontal):
    """Global row list: [(pos, lo, hi, band_idx, global_idx), ...] ordered by
    band then position, matching the proven band/ceil band/SPACING pitch."""
    if horizontal:
        events = sorted(set(round(v[1], 6) for v in poly))
    else:
        events = sorted(set(round(v[0], 6) for v in poly))
    rows = []
    gi = 0
    for bi in range(len(events) - 1):
        a, b = events[bi], events[bi + 1]
        mid = (a + b) / 2.0
        lo, hi = _span_at(poly, mid, horizontal)
        rng = b - a
        n = int(math.ceil(rng / SPACING - 1e-9))
        p = rng / n
        last = (bi == len(events) - 2)
        for k in range(0, n + 1 if last else n):
            rows.append((a + k * p, lo, hi, bi, gi))
            gi += 1
    return rows


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------
def _machine_header(w, title, source, extra_comments):
    w.c(";T25RC REV B DIALECT REPLICA - %s" % title)
    w.c(";Source %s, unchanged scale, translated to bed centre" % source)
    w.c(";DXF outline 171.4665 x 248.3380 mm")
    w.c(";Wall thickness: 2.0 mm (2 loops: -0.6 mm outer and -1.4 mm inner)")
    w.c(";Layers 0.25 mm. UNVERIFIED - pending first physical print.")
    for s in extra_comments:
        w.c(";%s" % s)
    w.c(";MACHINE_INIT")
    w.c("M140 S0 ; unheated bed")
    w.c("M104 S230 T0")
    w.c("M109 S230 T0")
    w.c("M104 S230 T1")
    w.c("M109 S230 T1")
    w.c("G21")
    w.c("G90")
    w.c("G82")
    w.c("G28")
    w.c("G1 Z15 F3000")
    w.c("G0 F%d X425.4626 Y472.4718" % F_TRAVEL)
    w.c(";IM_LOAD_UNLOAD_INIT_NOT_A_PRINT_PATH")


def _footer(w):
    w.c(";PRINT_BODY_END")
    w.c("G0 F%d Z35.000" % F_TRAVEL)
    w.c("G91")
    w.c("G0 X5 Y5 F%d" % F_TRAVEL)
    w.c("G0 F%d Z0" % F_TRAVEL)
    w.c("G90")
    w.c("G0 X750 Y750 F%d" % F_TRAVEL)
    w.c("G92 E0")
    w.c("G91")
    w.c("G1 F%d E-85" % F_RETRACT)
    w.c("M84")
    w.c("G90")
    w.c("M107")
    w.c("M104 S30 T0")
    w.c("M104 S30 T1")
    w.c("M106 S0")
    w.c(";End of Gcode")


def _wall_plan(layer, total_layers):
    """Return (role, loops) for one wall layer of a walls-only letter.

    Flange at the face side, then plain wall, then the 4-step shelf ladder,
    then the 8 mm rim. Layer numbers count from the face side (layer 1 =
    first layer above the face / on the bed)."""
    rim_start = total_layers - RIM_LAYERS + 1          # first rim layer
    ledge_end = rim_start - 1
    ledge_start = ledge_end - 4 * STEP_LAYERS + 1
    flange_end = FLANGE_LAYERS

    def loops(insets):
        return [(WALL_INSETS[i], i) for i in insets]

    if layer <= flange_end:
        return "WALL_LEDGE", loops((2, 1, 0))
    if layer >= rim_start:
        return "WALL_RIM", loops((1, 0))
    if layer < ledge_start:
        return "WALL", loops((1, 0))
    step = (layer - ledge_start) // STEP_LAYERS          # 0..3
    deepest = 2 + step
    return "WALL_LEDGE", loops(tuple(range(deepest, -1, -1)))


def build_t1(dxf_path, out_path):
    """T1: walls only, 100 layers (25 mm), CLEAR PLA (T2), no colour change."""
    w = Writer()
    w.outline = load_outline(dxf_path)
    w.C = w.outline[0]
    total = 100
    rim_start = total - RIM_LAYERS + 1                  # 69
    ledge_start = rim_start - 4 * STEP_LAYERS           # 57
    shelf_floor = (total - RIM_LAYERS) * LH             # Z=17.0
    _machine_header(w, "T LETTER WALLS ONLY 25MM (T1)",
                    "T 1.dxf (T Cetak)",
                    ["Job: walls only, single colour. UI slot 3 = CLEAR PLA / T2.",
                     "Pangkon front: %d-layer flange at -2.4 mm on the bed (L1-L%d)."
                     % (FLANGE_LAYERS, FLANGE_LAYERS),
                     "Pangkon back: %d-layer x %d-step chamfer ladder (L%d-L%d), "
                     "shelf floor Z=%.2f mm; rebate 8.0 mm (L%d-L%d, closed by"
                     " PVC cover)." % (4 * STEP_LAYERS, 4, ledge_start,
                                       rim_start - 1, shelf_floor,
                                       rim_start, total),
                     "Loop ladder -1.4 to -5.4 mm: PVC shelf rests 4.0 mm"
                     " inside the rim wall.",
                     "No colour change, no purge box (single filament).",
                     "Start-up: direct T2 load (no T0/T1 shuffle, slots may be empty)."])
    w.c("G92 E0")
    w.c("T2")
    w.c("G1 E85 F%d" % F_LOAD)
    w.c("G92 E0")
    w.c("T2")
    w.c("M117 Printing...")
    w.c("M106 S255")

    for layer in range(1, total + 1):
        z = round(layer * LH, 3)
        w.layer_n = layer
        w.c(";LAYER %d Z=%.3f WALL_CLEAR" % (layer, z))
        role, loops = _wall_plan(layer, total)
        tag = {"WALL": ";WALL_LOOP_%d", "WALL_LEDGE": ";WALL_LEDGE_LOOP_%d",
               "WALL_RIM": ";WALL_RIM_LOOP_%d"}[role]
        f = F_FACEWALL_L1 if layer == 1 else F_WALL
        w.loop_path(role, loops, z, f, tag[1:],
                    recover=(layer > 1))
    _footer(w)
    with open(out_path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(w.lines) + "\n")
    return w


def build_t2(dxf_path, out_path):
    """T2: face 2 mm BLACK (T0) + walls 25 mm CLEAR (T2), 108 layers total."""
    w = Writer()
    w.outline = load_outline(dxf_path)
    w.C = w.outline[0]
    total = 108
    face_layers = 8
    wall_total = total - face_layers                     # 100
    rim_start = wall_total - RIM_LAYERS + 1              # wall-relative 69
    ledge_start = rim_start - 4 * STEP_LAYERS            # 57
    shelf_floor = (total - RIM_LAYERS) * LH              # Z=19.0
    _machine_header(w, "T LETTER FACE CLOSED 27MM (T2)",
                    "T2.dxf (T Cetak)",
                    ["Job: face + walls, 2 colours. UI slot 1 = BLACK PLA / T0,",
                     "UI slot 3 = CLEAR PLA / T2 (heated by the machine on select,",
                     "as in the proven reference - no explicit T2 M104 here).",
                     "Face: 2.0 mm solid BLACK (8 layers), perimeters first,",
                     "100% light-tight, serpentine 0/90 alternating.",
                     "Pangkon front: %d-layer flange at -2.4 mm on the face (L9-L11)."
                     % FLANGE_LAYERS,
                     "Pangkon back: %d-layer x %d-step chamfer ladder (L%d-L%d), "
                     "shelf floor Z=%.2f mm; rebate 8.0 mm (L%d-L%d, closed by"
                     " PVC cover)." % (4 * STEP_LAYERS, 4,
                                       face_layers + ledge_start,
                                       face_layers + rim_start - 1, shelf_floor,
                                       face_layers + rim_start, total),
                     "Loop ladder -1.4 to -5.4 mm: PVC shelf rests 4.0 mm"
                     " inside the rim wall.",
                     "Purge: 3 concentric rings around a 44x40 pad OUTSIDE the",
                     "letter at (378-422, 200-240); pad = %d black ring layers" % PAD_LAYERS,
                     "printed with the face; rings printed once at Z=2.250."])
    w.c("G92 E0")
    w.c("T0")
    w.c("G1 E-85 F%d" % F_UNLOAD)
    w.c("G92 E0")
    w.c("T1")
    w.c("G1 E85 F%d" % F_LOAD)
    w.c("G92 E0")
    w.c("T1")
    w.c("G1 E-85 F%d" % F_UNLOAD)
    w.c("G92 E0")
    w.c("T0")
    w.c("G1 E85 F%d" % F_LOAD)
    w.c("G92 E0")
    w.c("T0")
    w.c("M117 Printing...")
    w.c("M106 S255")

    for layer in range(1, face_layers + 1):
        z = round(layer * LH, 3)
        w.layer_n = layer
        w.c(";LAYER %d Z=%.3f FACE_BLACK" % (layer, z))
        w.loop_path("FACE_WALL",
                    [(WALL_INSETS[1], 1), (WALL_INSETS[0], 0)], z,
                    F_FACEWALL_L1 if layer == 1 else F_FACEWALL,
                    "FACE_WALL_LOOP_%d", recover=(layer > 1))
        w.fill_paths(z, layer)
        w.rings_path("PURGE_PAD", z, True, PRIME_STD, 200,
                     F_FACEWALL_L1 if layer == 1 else F_FACEWALL,
                     F_LEAD, "PURGE_PAD_RING_%d")

    # colour change + purge rings on top of the pad
    z_cc = round((face_layers + 1) * LH, 3)
    w.colour_change(z_cc)
    w.rings_path("INTERNAL_PURGE", z_cc, False, PRIME_BIG, 500,
                 F_PURGE, F_PURGE, "PURGE_RING_%d", lift_first=True)

    for layer in range(face_layers + 1, total + 1):
        n = layer - face_layers                          # wall layer number
        z = round(layer * LH, 3)
        w.layer_n = layer
        w.c(";LAYER %d Z=%.3f WALL_CLEAR" % (layer, z))
        role, loops = _wall_plan(n, wall_total)
        tag = {"WALL": ";WALL_LOOP_%d", "WALL_LEDGE": ";WALL_LEDGE_LOOP_%d",
               "WALL_RIM": ";WALL_RIM_LOOP_%d"}[role]
        w.loop_path(role, loops, z, F_WALL, tag[1:])
    _footer(w)
    with open(out_path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(w.lines) + "\n")
    return w


def main(argv):
    dxf_dir = r"C:\Users\Pongo\Downloads\T Cetak"
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(repo, "artifacts")
    if "--dxf-dir" in argv:
        dxf_dir = argv[argv.index("--dxf-dir") + 1]
    if "--out-dir" in argv:
        out_dir = argv[argv.index("--out-dir") + 1]
    os.makedirs(out_dir, exist_ok=True)
    p1 = os.path.join(out_dir, "T1_walls_only_25mm.gcode")
    p2 = os.path.join(out_dir, "T2_face_closed_27mm.gcode")
    build_t1(os.path.join(dxf_dir, "T 1.dxf"), p1)
    print("wrote", p1)
    build_t2(os.path.join(dxf_dir, "T2.dxf"), p2)
    print("wrote", p2)


if __name__ == "__main__":
    main(sys.argv[1:])
