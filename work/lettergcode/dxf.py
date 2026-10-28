"""Minimal ASCII DXF reader (pure stdlib) for the entities ZCCAD emits.

Supported: LINE, LWPOLYLINE, POLYLINE/VERTEX, ARC, CIRCLE, ELLIPSE, SPLINE,
and INSERT of BLOCK content (scale / rotation / rectangular arrays).
Everything is flattened into closed or open polylines in millimetres, which is
what the vendor's GetVectorDXF() eventually produces as GroupPoint lists.
"""
from __future__ import annotations

import math

Point = tuple


# --------------------------------------------------------------------- tokenizer
def _pairs(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    i = 0
    out = []
    while i + 1 < len(lines):
        code = lines[i].strip()
        val = lines[i + 1].strip()
        try:
            out.append((int(code), val))
        except ValueError:
            pass
        i += 2
    return out


def _entities(pairs):
    """Yield (type, [ (code, value), ... ]) for entities in the ENTITIES section."""
    for section, block, etype, data in _all_entities(pairs):
        if section == "ENTITIES":
            yield etype, data


def _all_entities(pairs):
    """Yield (section, block_name, etype, data) for BLOCKS and ENTITIES.

    Geometry parked inside a BLOCK definition is invisible to a reader that only
    walks ENTITIES, which is how a drawing can import as zero contours. CorelDRAW
    and Illustrator export that way constantly, and so do the vendor's own
    special_shape files, so both sections are collected here and joined by INSERT.
    """
    section = None
    cur_type = None
    cur = []
    cur_block = None
    for code, val in pairs:
        if code == 0:
            if cur_type is not None and section in ("BLOCKS", "ENTITIES"):
                yield section, cur_block, cur_type, cur
            cur_type = val
            cur = []
            if val in ("ENDSEC", "EOF"):
                section = None
                cur_block = None
            continue
        if cur_type == "SECTION" and code == 2:
            section = val
            continue
        if section == "BLOCKS":
            if cur_type == "BLOCK" and code == 2:
                cur_block = val
            elif cur_type == "ENDBLK":
                cur_block = None
        if cur_type is not None:
            cur.append((code, val))
    if cur_type is not None and section in ("BLOCKS", "ENTITIES"):
        yield section, cur_block, cur_type, cur


def _g(d, code, default=None):
    if code in d:
        return d[code][-1]
    return default


def _gf(d, code, default=0.0):
    try:
        return float(_g(d, code, default))
    except (TypeError, ValueError):
        return default


def _gi(d, code, default=0):
    try:
        return int(float(_g(d, code, default)))
    except (TypeError, ValueError):
        return default


def _pts(d, cx=10, cy=20):
    xs = d.get(cx, [])
    ys = d.get(cy, [])
    n = min(len(xs), len(ys))
    out = []
    for i in range(n):
        try:
            out.append((float(xs[i]), float(ys[i])))
        except ValueError:
            pass
    return out


# --------------------------------------------------------------------- geometry
def _arc(cx, cy, r, a0, a1, seg_deg=5.0):
    """Tessellate a CCW arc from a0 to a1 degrees."""
    if a1 <= a0:
        a1 += 360.0
    n = max(2, int(math.ceil((a1 - a0) / seg_deg)))
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)))
            for k in range(n + 1)]


def _bulge(p1, p2, bulge, seg_deg=5.0):
    """Expand a polyline bulge segment into an arc."""
    if abs(bulge) < 1e-12:
        return [p1, p2]
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    chord = math.hypot(dx, dy)
    if chord < 1e-12:
        return [p1]
    theta = 4.0 * math.atan(bulge)          # sweep angle, signed
    r = chord / (2.0 * math.sin(abs(theta) / 2.0))
    # centre sits on the perpendicular bisector
    mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    h = math.sqrt(max(0.0, r * r - (chord / 2.0) ** 2))
    sign = 1.0 if theta > 0 else -1.0
    nx, ny = -dy / chord, dx / chord
    dist_c = r * math.cos(abs(theta) / 2.0)
    cx = mx - nx * dist_c * sign
    cy = my - ny * dist_c * sign
    a0 = math.degrees(math.atan2(p1[1] - cy, p1[0] - cx))
    a1 = math.degrees(math.atan2(p2[1] - cy, p2[0] - cx))
    sweep = math.degrees(theta)
    if sweep > 0 and a1 <= a0:
        a1 += 360.0
    if sweep < 0 and a1 >= a0:
        a1 -= 360.0
    n = max(2, int(math.ceil(abs(sweep) / seg_deg)))
    out = []
    for k in range(n + 1):
        ang = math.radians(a0 + (a1 - a0) * k / n)
        out.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return out


def _nurbs(ctrl, knots, weights, degree, samples=None):
    """Evaluate a NURBS curve with De Boor's algorithm."""
    n = len(ctrl)
    if n < 2:
        return list(ctrl)
    if degree < 1:
        degree = 1
    if len(knots) != n + degree + 1:
        # synthesise a clamped uniform knot vector
        inner = n - degree - 1
        knots = ([0.0] * (degree + 1)
                 + [i / (inner + 1) for i in range(1, inner + 1)]
                 + [1.0] * (degree + 1))
    if len(weights) != n:
        weights = [1.0] * n
    samples = samples or max(16, int(n * max(4, 8 / max(1, degree))))
    t0, t1 = knots[degree], knots[n]
    if t1 <= t0:
        t1 = t0 + 1.0
    out = []
    for s in range(samples + 1):
        u = t0 + (t1 - t0) * s / samples
        # locate span
        k = degree
        for i in range(degree, n):
            if knots[i] <= u < knots[i + 1]:
                k = i
                break
        else:
            k = n - 1
        d = []
        for j in range(degree + 1):
            idx = max(0, min(n - 1, k - degree + j))
            w = weights[idx]
            d.append([ctrl[idx][0] * w, ctrl[idx][1] * w, w])
        for r in range(1, degree + 1):
            for j in range(degree, r - 1, -1):
                i = k - degree + j
                den = knots[i + degree + 1 - r] - knots[i] if i + degree + 1 - r < len(knots) else 0.0
                a = 0.0 if abs(den) < 1e-12 else (u - knots[i]) / den
                for c in range(3):
                    d[j][c] = (1.0 - a) * d[j - 1][c] + a * d[j][c]
        w = d[degree][2]
        if abs(w) < 1e-12:
            out.append((d[degree][0], d[degree][1]))
        else:
            out.append((d[degree][0] / w, d[degree][1] / w))
    return out


# --------------------------------------------------------------------- reader
def read_dxf(path, seg_deg=5.0):
    """Return a list of dicts: {'pts': [...], 'closed': bool, 'source': str}."""
    raw = list(_pairs(path))
    blocks = {}
    model = []
    inserts = []
    for section, block, etype, data in _all_entities(raw):
        if section == "BLOCKS":
            if etype not in ("BLOCK", "ENDBLK") and block:
                blocks.setdefault(block, []).append((etype, data))
        elif section == "ENTITIES":
            if etype == "INSERT":
                inserts.append(data)
            elif etype not in ("BLOCK", "ENDBLK"):
                model.append((etype, data))

    out = _collect(model, seg_deg)

    for data in inserts:
        g = {}
        for code, val in data:
            g.setdefault(code, []).append(val)
        seq = blocks.get(_g(g, 2))
        if not seq:
            continue                      # unresolved or deleted block
        part = _collect(seq, seg_deg)
        for sx, sy, tx, ty in _insert_offsets(g):
            for p in part:
                pts = [(_xform(pt[0], pt[1], sx, sy, tx, ty, _gf(g, 50))
                        ) for pt in p["pts"]]
                out.append({"pts": pts, "closed": p["closed"],
                            "source": "INSERT/" + p["source"]})

    # A drawing whose only geometry sits in a block with no INSERT (the vendor's
    # special_shape library) still has to import. Use it rather than reporting an
    # empty page, but say so - a title block would be picked up the same way.
    if not out and len(blocks) == 1:
        name, seq = next(iter(blocks.items()))
        if not name.startswith("*"):
            import sys
            print("warning: %s has no model-space geometry; using block '%s'"
                  % (path, name), file=sys.stderr)
            out.extend(_collect(seq, seg_deg))
    return out


def _insert_offsets(g):
    """Yield (scale_x, scale_y, x, y) for an INSERT and any rectangular array."""
    sx = _gf(g, 41, 1.0) or 1.0
    sy = _gf(g, 42, 1.0) or 1.0
    x0, y0 = _gf(g, 10), _gf(g, 20)
    cols = max(1, _gi(g, 70, 1))
    rows = max(1, _gi(g, 71, 1))
    dx = _gf(g, 44, 0.0)
    dy = _gf(g, 45, 0.0)
    for c in range(cols):
        for r in range(rows):
            yield sx, sy, x0 + c * dx, y0 + r * dy


def _xform(x, y, sx, sy, tx, ty, rot_deg):
    """DXF INSERT order: scale about the block origin, rotate, then translate."""
    x, y = x * sx, y * sy
    if rot_deg:
        a = math.radians(rot_deg)
        ca, sa = math.cos(a), math.sin(a)
        x, y = x * ca - y * sa, x * sa + y * ca
    return (x + tx, y + ty)


def _collect(seq, seg_deg):
    out = []
    pending_poly = None
    verts = []

    for etype, d in seq:
        grouped = {}
        for code, val in d:
            grouped.setdefault(code, []).append(val)

        if etype == "LINE":
            p1 = (_gf(grouped, 10), _gf(grouped, 20))
            p2 = (_gf(grouped, 11), _gf(grouped, 21))
            if p1 != p2:
                out.append({"pts": [p1, p2], "closed": False, "source": "LINE"})

        elif etype == "LWPOLYLINE":
            pts = _pts(grouped)
            bulges = [float(b) for b in grouped.get(42, ["0"])]
            flags = _gi(grouped, 70, 0)
            closed = bool(flags & 1)
            chain = _apply_bulges(pts, bulges, closed, seg_deg)
            out.append({"pts": chain, "closed": closed, "source": "LWPOLYLINE"})

        elif etype == "POLYLINE":
            pending_poly = _gi(grouped, 70, 0)
            verts = []

        elif etype == "VERTEX":
            verts.append(((_gf(grouped, 10), _gf(grouped, 20)), _gf(grouped, 42, 0.0)))

        elif etype == "SEQEND":
            if verts:
                pts = [v[0] for v in verts]
                bulges = [v[1] for v in verts]
                closed = bool((pending_poly or 0) & 1)
                chain = _apply_bulges(pts, bulges, closed, seg_deg)
                out.append({"pts": chain, "closed": closed, "source": "POLYLINE"})
            verts = []
            pending_poly = None

        elif etype == "ARC":
            cx, cy = _gf(grouped, 10), _gf(grouped, 20)
            r = _gf(grouped, 40)
            a0, a1 = _gf(grouped, 50), _gf(grouped, 51)
            if r > 0:
                out.append({"pts": _arc(cx, cy, r, a0, a1, seg_deg),
                            "closed": False, "source": "ARC"})

        elif etype == "CIRCLE":
            cx, cy = _gf(grouped, 10), _gf(grouped, 20)
            r = _gf(grouped, 40)
            if r > 0:
                pts = _arc(cx, cy, r, 0.0, 360.0, seg_deg)
                out.append({"pts": pts[:-1], "closed": True, "source": "CIRCLE"})

        elif etype == "ELLIPSE":
            cx, cy = _gf(grouped, 10), _gf(grouped, 20)
            mx, my = _gf(grouped, 11, 1.0), _gf(grouped, 21, 0.0)
            ratio = _gf(grouped, 40, 1.0)
            t0 = _gf(grouped, 41, 0.0)
            t1 = _gf(grouped, 42, 2 * math.pi)
            a_len = math.hypot(mx, my)
            b_len = a_len * ratio
            rot = math.atan2(my, mx)
            n = max(16, int(abs(t1 - t0) / math.radians(seg_deg)))
            pts = []
            for k in range(n + 1):
                t = t0 + (t1 - t0) * k / n
                x = a_len * math.cos(t)
                y = b_len * math.sin(t)
                pts.append((cx + x * math.cos(rot) - y * math.sin(rot),
                            cy + x * math.sin(rot) + y * math.cos(rot)))
            closed = abs((t1 - t0) - 2 * math.pi) < 1e-6
            out.append({"pts": pts[:-1] if closed else pts,
                        "closed": closed, "source": "ELLIPSE"})

        elif etype == "SPLINE":
            ctrl = _pts(grouped, 10, 20)
            knots = [float(k) for k in grouped.get(40, [])]
            weights = [float(k) for k in grouped.get(41, [])]
            degree = _gi(grouped, 71, 3)
            fit = _pts(grouped, 11, 21)
            if len(ctrl) >= 2:
                pts = _nurbs(ctrl, knots, weights, degree)
            elif len(fit) >= 2:
                pts = fit
            else:
                continue
            flags = _gi(grouped, 70, 0)
            closed = bool(flags & 1) and math.hypot(pts[0][0] - pts[-1][0],
                                                    pts[0][1] - pts[-1][1]) < 1e-6
            out.append({"pts": pts, "closed": closed, "source": "SPLINE"})
    return out


def _apply_bulges(pts, bulges, closed, seg_deg):
    if len(pts) < 2:
        return list(pts)
    out = []
    n = len(pts)
    last = n if closed else n - 1
    for i in range(last):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        b = bulges[i] if i < len(bulges) else 0.0
        seg = _bulge(p1, p2, b, seg_deg)
        if out and math.hypot(out[-1][0] - seg[0][0], out[-1][1] - seg[0][1]) < 1e-9:
            out.extend(seg[1:])
        else:
            out.extend(seg)
    if closed and out and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-9:
        out.pop()
    return out


def close_rings(entities, tol=1e-3):
    """Split entities into closed rings and open polylines; close near-misses."""
    rings, chains = [], []
    for e in entities:
        pts = e["pts"]
        if len(pts) < 2:
            continue
        gap = math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
        if e["closed"] or gap <= tol:
            rings.append(list(pts))
        else:
            chains.append(list(pts))
    return rings, chains
