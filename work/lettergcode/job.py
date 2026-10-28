"""Job pipeline: DXF -> rings -> wall passes -> G-code.

Mirrors OutKF.calculateSideSlope():
    read DXF -> merge/clean -> split at 0.5 mm -> per layer:
        pre-side (first layer only) -> wall pass 0 -> wall pass 1..n
        -> next layer, switching extruder when the colour plane is crossed.
"""
from __future__ import annotations

import math
import os

from . import dxf, geom
from .gcode import GCodeWriter
from .params import Params


def rotate_to_nearest(ring, x, y):
    """Start a ring at the vertex closest to (x, y) - the vendor's findStartPos."""
    best = 0
    bd = float("inf")
    for i, (px, py) in enumerate(ring):
        d = (px - x) ** 2 + (py - y) ** 2
        if d < bd:
            bd = d
            best = i
    return ring[best:] + ring[:best]


def order_rings(rings, start, reverse=False):
    """Greedy nearest-neighbour ordering so travel moves stay short."""
    pool = list(rings)
    if reverse:
        pool.reverse()
    out = []
    cx, cy = start
    while pool:
        best = None
        bi = 0
        for i, ring in enumerate(pool):
            r = rotate_to_nearest(ring, cx, cy)
            if best is None:
                best, bi = r, i
            else:
                d0 = (r[0][0] - cx) ** 2 + (r[0][1] - cy) ** 2
                d1 = (best[0][0] - cx) ** 2 + (best[0][1] - cy) ** 2
                if d0 < d1:
                    best, bi = r, i
        out.append(best)
        pool.pop(bi)
        # next search starts from the ring's own start (the vendor returns there)
        cx, cy = best[0]
    return out


def simplify(ring, tol=0.01):
    r = geom.drop_collinear(ring, tol)
    if len(r) < 3:
        return ring
    return r


def _ring_area(r):
    s = 0.0
    for i in range(len(r)):
        x0, y0 = r[i]
        x1, y1 = r[(i + 1) % len(r)]
        s += x0 * y1 - x1 * y0
    return s / 2.0


def _ring_area_of(r):
    return abs(_ring_area(r))


def outer_rings(rings):
    """Rings that are not nested inside another ring (the letter silhouettes).

    The acrylic pocket is cut from the outside in, so only the outer boundary
    may grow: a counter that grew by the pocket width would leave the lip
    overhanging the hole, which cannot be printed without support.
    """
    out = []
    for i, r in enumerate(rings):
        if len(r) < 3:
            continue
        depth = 0
        for j, other in enumerate(rings):
            if i == j or len(other) < 3:
                continue
            if geom.point_in_contours(r[0], [other]):
                depth += 1
        if depth % 2 == 0:
            out.append(r)
    return out


class Job:
    def __init__(self, par: Params, dxf_path, cell=0.25, pad=2.0,
                 offset=(0.0, 0.0), place=None, fill=False, hem=True,
                 inside_only=False, seat_w=0.0, seat_lip=0.0,
                 min_area=0.0, max_area=0.0):
        self.p = par
        self.dxf_path = dxf_path
        self.cell = cell
        self.pad = pad
        self.offset = offset
        self.place = place
        self.fill = fill
        self.hem = hem
        self.inside_only = inside_only
        self.seat_w = seat_w
        self.seat_lip = seat_lip
        self.min_area = min_area
        self.max_area = max_area
        self.rings = []
        self.chains = []
        self.field = None
        self.seat_field = None
        self._seat_cache = {}
        self.min_gap = 1.0

    # ---------------------------------------------------------------- loading
    def load(self):
        ents = dxf.read_dxf(self.dxf_path)
        rings, chains = dxf.close_rings(ents)
        rings = [geom.dedupe(r) for r in rings if len(geom.dedupe(r)) >= 3]
        chains = [geom.dedupe(c) for c in chains if len(c) >= 2]
        if not rings and chains:
            # open geometry: treat each chain as a ring so a shell can be printed
            rings = chains
            chains = []
        if not rings:
            raise SystemExit(f"no closed contours found in {self.dxf_path}")
        if self.min_area > 0:
            # Drawings carry dimension marks and decorative dots next to the
            # letter; anything below min_area is noise for a 50 mm shell.
            rings = [r for r in rings if _ring_area_of(r) >= self.min_area]
            if not rings:
                raise SystemExit(f"no contour above --min-area in {self.dxf_path}")
        if self.max_area > 0:
            # Layout drawings carry the machine-bed rectangle as geometry. Printing
            # it would lay an 800 mm border across the whole job, so anything above
            # this area is treated as frame, not artwork.
            kept = [r for r in rings if _ring_area_of(r) <= self.max_area]
            if not kept:
                raise SystemExit("--max-area dropped every contour; raise it")
            rings = kept
        if self.inside_only:
            # Drawings often carry dimension marks or a second test object beside
            # the letter; keep only the contours that live inside the largest one.
            rings.sort(key=lambda r: -abs(_ring_area(r)))
            x0, y0, x1, y1 = geom.bbox([rings[0]])
            keep = []
            for r in rings:
                a, b, c, d = geom.bbox([r])
                if a >= x0 - 0.5 and b >= y0 - 0.5 and c <= x1 + 0.5 and d <= y1 + 0.5:
                    keep.append(r)
            rings = keep
        dx, dy = self.offset
        if self.place is not None:
            x0, y0, _, _ = geom.bbox(rings)
            dx += self.place[0] - x0
            dy += self.place[1] - y0
        if dx or dy:
            rings = [[(x + dx, y + dy) for x, y in r] for r in rings]
            chains = [[(x + dx, y + dy) for x, y in c] for c in chains]
        self.rings = rings
        self.chains = chains
        return self

    # --------------------------------------------------------------- distance
    def build_field(self, max_offset):
        x0, y0, x1, y1 = geom.bbox(self.rings)
        m = max_offset + self.pad
        self.field = geom.Field(self.rings, x0 - m, y0 - m, x1 + m, y1 + m, self.cell)
        return self.field

    def build_seat_field(self):
        """Distance field of the outer boundaries only, used for the pocket."""
        if self.p.seat.width <= 0:
            return None
        outer = outer_rings(self.rings)
        if not outer:
            return None
        x0, y0, x1, y1 = geom.bbox(self.rings)
        m = self.p.seat.width + self.p.wall_thickness + self.pad
        self.seat_field = geom.Field(outer, x0 - m, y0 - m, x1 + m, y1 + m, self.cell)
        return self.seat_field

    def seat_levels(self, li, layer_n):
        """Extra wall lines that build the acrylic pocket on this layer.

        Below the shoulder the wall grows by `seat.width`; at and above the
        shoulder only the outer wall prints, which leaves the pocket the sheet
        rests in.  The thickness ramps in over `seat.ramp` mm so no extra line
        ever starts over air.
        """
        s = self.p.seat
        if s.width <= 0 or self.seat_field is None:
            return []
        h = self.p.layer_z(li)
        top = round(layer_n * self.p.let.dbHeightLayer, 6)
        z_seat = top - s.depth
        if h > z_seat + 1e-6:
            return []                       # inside the pocket: lip only
        step = self.p.let.dbThichnessOffset or 0.8
        # the seat is measured from the innermost wall line, not the contour
        wall = max(1, int(self.p.let.iThichnessCount)) * step
        inset = wall + s.width
        if s.ramp > 0:
            z0 = z_seat - s.land - s.ramp
            t = (h - z0) / s.ramp
            if t < 1.0:
                inset = wall + s.width * max(0.0, t)
        out = []
        d = wall + step
        while d <= inset + 1e-6:
            out.append(self._seat_rings(d))
            d += step
        return out

    def _seat_rings(self, d):
        key = round(d, 4)
        rings = self._seat_cache.get(key)
        if rings is None:
            rings = [simplify(r) for r in self.seat_field.iso(-d) if len(r) >= 3]
            self._seat_cache[key] = rings
        return rings

    def passes(self):
        """Wall passes per layer: pass 0 is the DXF contour, pass k is inset k*offset.

        temp.gcode prints exactly ONE pass on every layer above the first
        (154.62 x 110.54 = the raw outline) for iThichnessCount = 1, so the
        trace count maps directly onto the pass count - not n + 1.

        The Fill tool adds one more inset line: the WELCOME test export shows 8
        contours -> 22 rings per layer, every extra ring sitting exactly
        dbThichnessOffset (0.8 mm) inside the wall, holes growing by the same
        amount.  Nothing else changes, so the fill is one extra iso level.
        """
        n = max(1, int(self.p.let.iThichnessCount))
        off = self.p.let.dbThichnessOffset
        out = [self.rings]
        # iThichnessCount = 1 means the contour plus one inset line: the two
        # parallel walls visible in the printed sample.
        for k in range(1, n + 1 + (1 if self.fill else 0)):
            delta = -k * off
            iso = self.field.iso(delta) if self.field else []
            iso = [simplify(r) for r in iso if len(r) >= 3]
            out.append(iso)
        return out

    def first_layer_extra(self):
        """Extra inner wall the vendor prints on layer 0 only (154.62 -> 153.02).

        Not emitted: temp.gcode adds it to outer boundaries but NOT to hole
        boundaries, and picking the two apart needs a material-side test that is
        not worth guessing.  Callers may pass these rings in explicitly.
        """
        return []

    def pre_side_rings(self):
        """Safety line: offset outlines of the letter, outermost pass first.

        temp.gcode shows the vendor offsets the *outline* by dbOffsetPreSide
        (154.62 + 2*15 = 184.62 mm for its bbox) rather than drawing a
        rectangle, and spaces iNumPreSide passes by dbThicknessOrigin.
        """
        p = self.p
        o = p.let.dbOffsetPreSide
        n = max(0, p.let.iNumPreSide)
        if o <= 0 or n <= 0 or self.field is None:
            return []
        step = p.let.dbThicknessOrigin or 1.2
        out = []
        for k in range(n):
            level = o - k * step
            if level <= 0:
                break
            for r in self.field.iso(level):
                r = geom.drop_collinear(r, 0.15)
                if len(r) >= 3:
                    out.append(r)
        return out

    # ------------------------------------------------------------------ render
    def render(self, out_path, pre_side=True, first_layer_fill=False,
               fill_spacing=None, progress=None):
        p = self.p
        off_total = max(0.0, p.let.iThichnessCount) * p.let.dbThichnessOffset
        side = p.let.dbOffsetPreSide + p.let.dbThicknessOrigin * max(0, p.let.iNumPreSide)
        self.build_field(max(off_total, side))

        passes = self.passes()
        extra = self.first_layer_extra()
        layer_n = p.layer_count
        hem_n = p.hem_layers if self.hem else 0
        if p.seat.width > 0:
            self.build_seat_field()

        tools = sorted({_tool(p, p.glue_no_for_layer(i)) for i in range(layer_n)})
        if not tools:
            tools = [0]
        first_tool = _tool(p, p.glue_no_for_layer(0))

        with open(out_path, "w", encoding="ascii", newline="\n") as fh:
            w = GCodeWriter(p, fh)
            w.write_head(tools)
            w.write_initial_switch(first_tool)

            if pre_side:
                w.write_pre_side(self.pre_side_rings(), p.layer_z(0))

            pos = (w.pos[0], w.pos[1])
            cur_tool = first_tool
            cur_glue = p.glue_no_for_layer(0)
            block_first = True

            for li in range(layer_n):
                h = p.layer_z(li)
                glue = p.glue_no_for_layer(li)
                if glue != cur_glue:
                    w.write_color_switch(_tool(p, glue), h)
                    cur_tool = _tool(p, glue)
                    cur_glue = glue
                    block_first = True

                layer_rings = []
                # The hem: the top dbHeight1 band prints the walls alone.  Both
                # vendor exports drop the fill loops for their last 3 layers and
                # keep every wall pass, so only the trailing fill pass goes.
                use = passes
                if hem_n and self.fill and li >= layer_n - hem_n:
                    use = passes[:-1]
                for k, ring_set in enumerate(use):
                    ordered = order_rings(ring_set, pos, reverse=(k > 0))
                    layer_rings.extend(ordered)
                # acrylic pocket: extra lines inside the wall, below the shoulder
                for ring_set in self.seat_levels(li, layer_n):
                    layer_rings.extend(order_rings(ring_set, pos))
                if li == 0 and extra:
                    layer_rings.extend(order_rings(extra, pos))

                for ri, ring in enumerate(layer_rings):
                    first = block_first and ri == 0
                    w.contour(ring, h, is_block_first=first)
                    w.contour_end(h)
                    pos = ring[0]
                    if first:
                        block_first = False

                if first_layer_fill and li == 0:
                    sp = fill_spacing or p.let.dbThicknessOrigin
                    w.first_layer_fill(self.rings, h, spacing=sp)
                    w.begin_block()
                    block_first = True

                if progress:
                    progress(li + 1, layer_n)

            w.write_tail(pos, p.layer_z(layer_n - 1))
        return out_path


def _tool(p: Params, glue_no: int) -> int:
    """iLayerGlueNo (1-based) -> T number: glue 1 -> T0, glue 2 -> T1."""
    return p.tool_no(glue_no)


def generate(ini_path, dxf_path, out_path, cell=0.25, pre_side=True,
             first_layer_fill=False, layer_override=None, height_override=None,
             theme=None, progress=None, fill=False, hem=True):
    par = Params.from_ini(ini_path) if ini_path and os.path.exists(ini_path) else Params()
    if layer_override:
        par.let.dbHeightLayer = float(layer_override)
    if height_override:
        par.let.dbHeightShell = float(height_override)
    job = Job(par, dxf_path, cell=cell, fill=fill, hem=hem).load()
    job.render(out_path, pre_side=pre_side, first_layer_fill=first_layer_fill,
               progress=progress)
    return par, job
