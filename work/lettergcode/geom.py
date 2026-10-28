"""Pure-stdlib polygon geometry: resampling, signed distance field, iso-contours.

The vendor offsets contours with Clipper (clipper_library.dll).  We cannot use
Clipper from Python without a build, so the same result is obtained by sampling
a signed distance field and extracting iso-contours with marching squares.  That
is slower than Clipper but has two useful properties: it can never produce a
self-intersecting ring, and overlapping letters are merged into one silhouette
automatically.

Sign convention: negative inside material, positive outside.
"""
from __future__ import annotations

import math

Point = tuple


# --------------------------------------------------------------------- basics
def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def polyline_length(pts, closed=False):
    total = 0.0
    for i in range(1, len(pts)):
        total += dist(pts[i - 1], pts[i])
    if closed and len(pts) > 2:
        total += dist(pts[-1], pts[0])
    return total


def signed_area(pts):
    """>0 for counter-clockwise rings (standard maths convention)."""
    n = len(pts)
    if n < 3:
        return 0.0
    acc = 0.0
    x0, y0 = pts[-1]
    for x, y in pts:
        acc += x0 * y - x * y0
        x0, y0 = x, y
    return acc * 0.5


def bbox(contours):
    xs = [p[0] for c in contours for p in c]
    ys = [p[1] for c in contours for p in c]
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def dedupe(pts, eps=1e-9):
    out = []
    for p in pts:
        if not out or dist(out[-1], p) > eps:
            out.append(p)
    return out


def resample(pts, step, closed=False):
    """Densify a polyline so no segment exceeds `step` (vendor uses 0.5 mm)."""
    if len(pts) < 2 or step <= 0:
        return list(pts)
    src = list(pts) + ([pts[0]] if closed else [])
    out = [src[0]]
    for i in range(1, len(src)):
        a, b = src[i - 1], src[i]
        d = dist(a, b)
        if d <= 1e-12:
            continue
        n = int(math.ceil(d / step))
        for k in range(1, n + 1):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    if closed and out and dist(out[0], out[-1]) < 1e-9:
        out.pop()
    return out


def drop_collinear(pts, tol=1e-4):
    """Remove points whose deviation from the neighbour chord is below tol."""
    if len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        ab = dist(a, b)
        ac = dist(a, c)
        if ab < 1e-12 or ac < 1e-12:
            continue
        cross = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        if cross / ac > tol:
            out.append(b)
    out.append(pts[-1])
    return out


def resample_mixed(pts, step, straight_tol=1e-3):
    """Densify only where needed: straight runs are kept, curves get `step`.

    The vendor's dasanWorkPoint() splits every contour at a fixed 0.5 mm which
    yields long straight runs of identical points.  Reproducing that exactly is
    wasteful, so straight stretches are emitted as single moves; the machine
    firmware interpolates them identically.
    """
    return resample(drop_collinear(pts, straight_tol), step, closed=False)


# ------------------------------------------------------------- even-odd inside
def point_in_contours(pt, contours):
    """Even-odd containment over all rings -> correct handling of letter counters."""
    x, y = pt
    inside = False
    for ring in contours:
        n = len(ring)
        if n < 3:
            continue
        j = n - 1
        for i in range(n):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > y) != (yj > y):
                t = (y - yi) / (yj - yi)
                if x < xi + t * (xj - xi):
                    inside = not inside
            j = i
    return inside


# ------------------------------------------------------------------ distance field
class Field:
    """Signed distance field of a set of closed rings on a regular grid."""

    def __init__(self, contours, x0, y0, x1, y1, cell):
        self.contours = contours
        self.cell = cell
        self.x0 = x0
        self.y0 = y0
        self.nx = max(2, int(math.ceil((x1 - x0) / cell)) + 1)
        self.ny = max(2, int(math.ceil((y1 - y0) / cell)) + 1)
        self.d = [1e30] * (self.nx * self.ny)
        self._seed()
        self._chamfer()
        self._sign()

    # -- rasterise every ring segment at distance 0 --------------------------
    def _seed(self, step_frac=0.4):
        nx, ny, cell = self.nx, self.ny, self.cell
        d = self.d
        for ring in self.contours:
            n = len(ring)
            if n < 2:
                continue
            for i in range(n):
                ax, ay = ring[i]
                bx, by = ring[(i + 1) % n]
                seg = math.hypot(bx - ax, by - ay)
                steps = max(1, int(seg / (cell * step_frac)))
                for k in range(steps + 1):
                    t = k / steps
                    gx = int(round((ax + (bx - ax) * t - self.x0) / cell))
                    gy = int(round((ay + (by - ay) * t - self.y0) / cell))
                    if 0 <= gx < nx and 0 <= gy < ny:
                        d[gy * nx + gx] = 0.0

    # -- two-pass chamfer distance transform (3-4 weights) -------------------
    def _chamfer(self):
        nx, ny, d = self.nx, self.ny, self.d
        a, b = self.cell, self.cell * 1.4142135
        inf = 1e30
        # forward
        for y in range(ny):
            row = y * nx
            for x in range(nx):
                i = row + x
                v = d[i]
                if x:
                    if d[i - 1] + a < v:
                        v = d[i - 1] + a
                if y:
                    if d[i - nx] + a < v:
                        v = d[i - nx] + a
                    if x:
                        if d[i - nx - 1] + b < v:
                            v = d[i - nx - 1] + b
                    if x + 1 < nx:
                        if d[i - nx + 1] + b < v:
                            v = d[i - nx + 1] + b
                if v < inf and v > 0:
                    d[i] = v
        # backward
        for y in range(ny - 1, -1, -1):
            row = y * nx
            for x in range(nx - 1, -1, -1):
                i = row + x
                v = d[i]
                if x + 1 < nx:
                    if d[i + 1] + a < v:
                        v = d[i + 1] + a
                if y + 1 < ny:
                    if d[i + nx] + a < v:
                        v = d[i + nx] + a
                    if x + 1 < nx:
                        if d[i + nx + 1] + b < v:
                            v = d[i + nx + 1] + b
                    if x:
                        if d[i + nx - 1] + b < v:
                            v = d[i + nx - 1] + b
                if v < inf and v > 0:
                    d[i] = v

    # -- apply the inside/outside sign via scanline even-odd ----------------
    def _sign(self):
        nx, ny, cell, d = self.nx, self.ny, self.cell, self.d
        y0 = self.y0
        edges = []
        for ring in self.contours:
            n = len(ring)
            if n < 3:
                continue
            for i in range(n):
                ax, ay = ring[i]
                bx, by = ring[(i + 1) % n]
                if ay != by:
                    edges.append((ax, ay, bx, by))
        for y in range(ny):
            wy = y0 + y * cell
            xs = []
            for ax, ay, bx, by in edges:
                if (ay > wy) != (by > wy):
                    t = (wy - ay) / (by - ay)
                    xs.append(ax + t * (bx - ax))
            if not xs:
                continue
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                xa, xb = xs[k], xs[k + 1]
                ia = max(0, int(math.ceil((xa - self.x0) / cell)))
                ib = min(nx - 1, int(math.floor((xb - self.x0) / cell)))
                row = y * nx
                for x in range(ia, ib + 1):
                    d[row + x] = -d[row + x]

    # -- sampling -----------------------------------------------------------
    def at(self, gx, gy):
        if gx < 0 or gy < 0 or gx >= self.nx or gy >= self.ny:
            return self.cell * 4.0
        return self.d[gy * self.nx + gx]

    def value(self, x, y):
        fx = (x - self.x0) / self.cell
        fy = (y - self.y0) / self.cell
        gx = max(0, min(self.nx - 2, int(fx)))
        gy = max(0, min(self.ny - 2, int(fy)))
        tx = fx - gx
        ty = fy - gy
        v00 = self.at(gx, gy)
        v10 = self.at(gx + 1, gy)
        v01 = self.at(gx, gy + 1)
        v11 = self.at(gx + 1, gy + 1)
        return (v00 * (1 - tx) * (1 - ty) + v10 * tx * (1 - ty)
                + v01 * (1 - tx) * ty + v11 * tx * ty)

    # -- marching squares ---------------------------------------------------
    def iso(self, level, min_points=6):
        """Closed rings where field == level, oriented so material is on the left."""
        nx, ny, cell = self.nx, self.ny, self.cell
        x0, y0, f = self.x0, self.y0, self.d
        segs = []

        def interp(gx1, gy1, v1, gx2, gy2, v2):
            den = v2 - v1
            t = 0.5 if abs(den) < 1e-12 else (level - v1) / den
            x = x0 + (gx1 + (gx2 - gx1) * t) * cell
            y = y0 + (gy1 + (gy2 - gy1) * t) * cell
            return (x, y)

        for y in range(ny - 1):
            row = y * nx
            for x in range(nx - 1):
                v0 = f[row + x]          # (x,   y)
                v1 = f[row + x + 1]      # (x+1, y)
                v2 = f[row + nx + x + 1]  # (x+1, y+1)
                v3 = f[row + nx + x]      # (x,   y+1)
                case = (v0 < level) | ((v1 < level) << 1) | ((v2 < level) << 2) | ((v3 < level) << 3)
                if case == 0 or case == 15:
                    continue
                # edge crossings, counter-clockwise around the cell
                top = interp(x, y, v0, x + 1, y, v1) if (v0 < level) != (v1 < level) else None
                right = interp(x + 1, y, v1, x + 1, y + 1, v2) if (v1 < level) != (v2 < level) else None
                bot = interp(x + 1, y + 1, v2, x, y + 1, v3) if (v2 < level) != (v3 < level) else None
                left = interp(x, y + 1, v3, x, y, v0) if (v3 < level) != (v0 < level) else None
                # case table orients every segment so that the material side
                # (field < level) is on its left; complementary cases reverse.
                if case == 1:
                    segs.append((left, top))
                elif case == 2:
                    segs.append((top, right))
                elif case == 3:
                    segs.append((left, right))
                elif case == 4:
                    segs.append((right, bot))
                elif case == 5:
                    segs.append((left, top))
                    segs.append((right, bot))
                elif case == 6:
                    segs.append((top, bot))
                elif case == 7:
                    segs.append((left, bot))
                elif case == 8:
                    segs.append((bot, left))
                elif case == 9:
                    segs.append((bot, top))
                elif case == 10:
                    segs.append((top, right))
                    segs.append((bot, left))
                elif case == 11:
                    segs.append((bot, right))
                elif case == 12:
                    segs.append((right, left))
                elif case == 13:
                    segs.append((right, top))
                elif case == 14:
                    segs.append((top, left))
        return _chain(segs, min_points)


# ------------------------------------------------------------------ ring chaining
def _key(p, q=1e5):
    return (round(p[0] * q), round(p[1] * q))


def _chain(segs, min_points=6):
    """Join directed segments into closed rings."""
    from collections import defaultdict
    starts = defaultdict(list)
    for idx, (a, b) in enumerate(segs):
        starts[_key(a)].append(idx)
    used = [False] * len(segs)
    rings = []
    for idx in range(len(segs)):
        if used[idx]:
            continue
        used[idx] = True
        ring = [segs[idx][0], segs[idx][1]]
        while True:
            cand = starts.get(_key(ring[-1]))
            nxt = None
            if cand:
                for c in cand:
                    if not used[c]:
                        nxt = c
                        break
            if nxt is None:
                break
            used[nxt] = True
            ring.append(segs[nxt][1])
            if _key(ring[-1]) == _key(ring[0]):
                break
        if len(ring) >= min_points and _key(ring[0]) == _key(ring[-1]):
            rings.append(ring[:-1])
    return rings


# ------------------------------------------------------------------ helpers
def offset_rings(field, delta, min_points=6):
    """Iso-contour of the field at `delta` (negative = inward = thicker wall)."""
    return field.iso(delta, min_points=min_points)


def zigzag_fill(ring_outer, spacing, angle_deg=45.0):
    """Parallel-line fill of a closed ring; returns a list of open polylines."""
    if not ring_outer or len(ring_outer) < 3:
        return []
    a = math.radians(angle_deg)
    ca, sa = math.cos(-a), math.sin(-a)
    rot = [(x * ca - y * sa, x * sa + y * ca) for x, y in ring_outer]
    xs = [p[0] for p in rot]
    ys = [p[1] for p in rot]
    y = min(ys) + spacing * 0.5
    out = []
    flip = False
    rca, rsa = math.cos(a), math.sin(a)
    while y < max(ys):
        xs_hit = []
        n = len(rot)
        for i in range(n):
            x1, y1 = rot[i]
            x2, y2 = rot[(i + 1) % n]
            if (y1 > y) != (y2 > y):
                t = (y - y1) / (y2 - y1)
                xs_hit.append(x1 + t * (x2 - x1))
        xs_hit.sort()
        for k in range(0, len(xs_hit) - 1, 2):
            xa, xb = xs_hit[k], xs_hit[k + 1]
            if xb - xa < 1e-6:
                continue
            if flip:
                xa, xb = xb, xa
            p1 = (xa * rca - y * rsa, xa * rsa + y * rca)
            p2 = (xb * rca - y * rsa, xb * rsa + y * rca)
            out.append([p1, p2])
            flip = not flip
        y += spacing
    return out
