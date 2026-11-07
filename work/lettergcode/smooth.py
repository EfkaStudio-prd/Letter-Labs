"""Smooth profile: Bambu-class wall planning inside the ZCCAD dialect.

Phase 1 of SMOOTH_ZCCAD_BRIEF_R0 (6 Nov 2026).  Every line emitted here keeps
an exact shape from the vendor corpus (``dialect_check.py`` must report
CONFORMS with no novel shapes); only the *path planning* changes.  Nothing from
this module is trusted for production until coupons C1..C4 are printed,
measured and photographed on the machine: the label for all output stays
**UNVERIFIED** (see docs/SMOOTH_PHASE1_REPORT.md).

What the smooth profile does, per brief section 4:

* ring count per contour == ``--walls`` exactly (the vendor pipeline's
  ``iThichnessCount + 1`` behaviour is NOT inherited and NOT changed there,
  selftest T17);
* bead-area flow model anchored on the vendor's proven E/mm constant
  (0.134285714286 at 1.2 x 0.3, T3).  The vendor does NOT rescale E with
  layer height (``Welcome new tes.gcode`` at layer 0.5 keeps the vendor
  constant), which is exact for vendor output but under-extrudes a thicker
  layer; smooth computes ``E/mm = anchor * A(w, h) / A(1.2, 0.3)`` instead
  (T19);
* wall spacing defaults to ``auto = w - h * (1 - pi/4)`` so rounded bead caps
  just touch instead of overlapping 0.4 mm like the vendor defaults
  (T18);
* contour-by-contour order, alternating between layers (brief 4.3), so the
  layer change rides on an already-open contour: zero retracts at layer
  boundaries and ``contours - 1`` stops per layer (T20);
* a locked seam per contour, chosen at a concave corner near Y-max
  (fallback: sharpest convex corner, fallback: Y-max point), the same vertex
  and the same XY every layer (T21), then a 0.6 mm coast before the loop
  closes;
* retract only when switching contours, wipe before retracts, hop only with
  a retract, unretract at 80 mm/s plus a small prime;
* ``G92 E0`` before every prime that follows a stop (T25) - the vendor bug
  found in ``test .gcode`` / ``test 1.gcode`` / ``test 2.gcode`` re-advances
  absolute E without a reset;
* a bed gate: the outline, the pre-side frame and the pre-side prime points
  must sit inside the 800 x 800 bed; a margin below ``--bed-margin`` mm warns
  (T22).

The vendor-exact pipeline (``Job.render``, plain ``--family zccad``) is
untouched by this module.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from . import geom
from .gcode import GCodeWriter, g, zg
from .job import Job, simplify
from .params import Params

#: Iguana / Taesin letter printer bed, as measured on the vendor exports.
BED = (800.0, 800.0)

#: The vendor's measured extrusion constant at 1.2 mm width and 0.3 mm layer
#: (dialect corpus invariant, 10/10 valid exports).  Not re-derived here.
E_ANCHOR = 0.134285714286


def bead_area(w: float, h: float) -> float:
    """Slic3r-style bead cross-section: (w - h)*h rectangle + round cap."""
    w = float(w)
    h = float(h)
    if h <= 0.0 or w <= 0.0:
        raise ValueError("bead width and layer height must be positive")
    if h > w:
        raise ValueError("layer %g is taller than bead width %g" % (h, w))
    return (w - h) * h + math.pi * h * h / 4.0


def anchor_area() -> float:
    """Bead area of the vendor's proven calibration point (1.2 x 0.3)."""
    return bead_area(1.2, 0.3)


def e_per_mm(w: float, h: float) -> float:
    """Filament mm per path mm at bead (w, h).

    Anchored on the vendor constant; only the cross-section ratio scales.
    Brief 4.2 sanity:  (1.2, 0.40) -> 0.175664   (1.2, 0.36) -> 0.159316
    """
    return E_ANCHOR * bead_area(w, h) / anchor_area()


def auto_wall_spacing(w: float, h: float) -> float:
    """Centre spacing between adjacent wall beads so round caps just touch."""
    return w - h * (1.0 - math.pi / 4.0)


def temp_for_speed(speed_mm_s: float) -> int:
    """Nozzle temperature rule (brief 4.1 / T26).

    230 degC is the proven setting for wall speeds up to 50 mm/s (TES IM,
    printed clean).  Faster bands come from the vendor manual verse and stay
    UNVERIFIED until a coupon prints at that speed.
    """
    s = float(speed_mm_s)
    if s <= 50.0:
        return 230
    if s <= 60.0:
        return 235
    if s <= 70.0:
        return 240
    return 245


def speed_class_feed(bbox_dim: float, klass: str) -> tuple[int, str]:
    """Work-speed feed (mm/min) chosen from the design size (brief 4.1).

    Returns (feed, note); note is a manual-verse reminder or empty.
    """
    klass = (klass or "auto").lower()
    if klass == "small":
        return 2400, ""
    if klass == "large":
        return 3000, ""
    if bbox_dim <= 300.0:
        return 2700, ""
    if bbox_dim <= 600.0:
        return 3000, ""
    return 3000, ("design spans %.0f mm; the vendor manual allows 50-80 mm/s "
                  "(F3000-F4800) for 30-60 cm letters - raise the speed only "
                  "after a coupon proves it" % bbox_dim)


@dataclass
class SmoothOpts:
    """Everything the smooth profile plans differently from the vendor."""

    walls: int = 1
    wall_spacing: float | None = None       # None = auto (w - h(1 - pi/4))
    seam: str | tuple = "corner"            # "corner" | "back" | ("XY", x, y)
    alternate: bool = True                  # alternating contour order
    coast: float = 0.6                      # mm printed with a frozen E
    hop: float = 0.6                        # Z lift that rides with a retract
    wipe: bool = True                       # back 2 mm along the path first
    wipe_mm: float = 2.0
    prime: float = 0.1                      # extra filament pushed on unretract
    min_layer_time: float = 10.0            # seconds; floor speed min_f
    speed_class: str = "auto"               # small | large | auto
    work_f: int | None = None               # explicit F overrides the class
    unretract_f: int = 4800                 # push @ 80 mm/s
    retract_f: int = 1800                   # retract @ 30 mm/s
    first_f: int = 1800                     # layer 1 @ 30 mm/s
    postswitch_f: int = 1800                # first contour after a colour switch
    pocket_f: int = 2400                    # pangkon / seat rings @ 40 mm/s
    min_f: int = 1200                       # min layer speed 20 mm/s
    bed_margin: float = 15.0                # warn inside this many mm
    spiral: bool = False                    # Phase 2, rejected for now
    pangkon: float = 0.0                    # acrylic pocket depth (0 = off)
    pangkon_back: bool = False              # mirror the seat near the bed

    @classmethod
    def from_args(cls, args) -> "SmoothOpts":
        o = cls()
        if getattr(args, "walls", None) is not None:
            o.walls = max(1, int(args.walls))
        if getattr(args, "wall_spacing", None):
            s = str(args.wall_spacing).strip().lower()
            if s not in ("", "auto"):
                o.wall_spacing = float(s)
        if getattr(args, "seam", None):
            o.seam = _parse_seam(args.seam)
        o.alternate = not getattr(args, "no_alternate_order", False)
        if getattr(args, "coast", None) is not None:
            o.coast = max(0.0, float(args.coast))
        if getattr(args, "hop", None) is not None:
            o.hop = max(0.0, float(args.hop))
        if getattr(args, "min_layer_time", None) is not None:
            o.min_layer_time = max(0.0, float(args.min_layer_time))
        if getattr(args, "speed_class", None):
            o.speed_class = str(args.speed_class)
        if getattr(args, "work_speed", None) is not None:
            o.work_f = int(args.work_speed)
        if getattr(args, "bed_margin", None) is not None:
            o.bed_margin = max(0.0, float(args.bed_margin))
        if getattr(args, "pangkon", None):
            o.pangkon = max(0.0, float(args.pangkon))
        o.pangkon_back = bool(getattr(args, "pangkon_back", False))
        return o


def _parse_seam(text) -> str | tuple:
    s = str(text).strip().lower()
    if s in ("corner", "corner-y", "auto"):
        return "corner"
    if s == "back":
        return "back"
    try:
        a, b = s.split(",")
        return ("XY", float(a), float(b))
    except ValueError:
        raise SystemExit("--seam expects corner|back|X,Y, got %r" % text)


# ---------------------------------------------------------------------------
# seam planning (brief 4.4 / T21)

def _turn_deflections(pts):
    """(index, deflection_rad, concave?) per vertex of a closed ring."""
    n = len(pts)
    ccw = geom.signed_area(pts) > 0.0
    out = []
    for i in range(n):
        a = pts[i - 1]
        b = pts[i]
        c = pts[(i + 1) % n]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        l1 = math.hypot(*v1)
        l2 = math.hypot(*v2)
        if l1 < 1e-12 or l2 < 1e-12:
            continue
        v1 = (v1[0] / l1, v1[1] / l1)
        v2 = (v2[0] / l2, v2[1] / l2)
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        dot = v1[0] * v2[0] + v1[1] * v2[1]
        deflect = math.atan2(abs(cross), dot)
        concave = (cross < 0.0) if ccw else (cross > 0.0)
        out.append((i, deflect, concave))
    return out


def pick_seam_index(ring, mode="corner"):
    """Locked seam vertex for one ring (brief 4.4).

    1. a concave corner with > 30 deg turn, preferring the Y-max side;
    2. otherwise the sharpest convex corner (> 30 deg);
    3. otherwise (round ring) the Y-max vertex.
    ``mode`` may be ("XY", x, y) to force the vertex nearest that point.
    """
    pts = list(ring)
    if not isinstance(mode, str):
        best = 0
        bd = float("inf")
        for i, p in enumerate(pts):
            d = (p[0] - mode[1]) ** 2 + (p[1] - mode[2]) ** 2
            if d < bd:
                bd = d
                best = i
        return best
    n = len(pts)
    if n <= 3:
        return 0
    if mode == "back":
        # seam at the vertex nearest Y-min: the back side of the sign
        best = 0
        by = float("inf")
        for i, p in enumerate(pts):
            if p[1] < by:
                by = p[1]
                best = i
        return best
    ymax = max(p[1] for p in pts)
    turns = _turn_deflections(pts)
    concave = [(i, d) for i, d, c in turns if c and d > math.radians(30.0)]
    if concave:
        i, _ = max(concave, key=lambda t: (pts[t[0]][1], pts[t[0]][0]))
        return i
    convex = [(i, d) for i, d, c in turns if (not c) and d > math.radians(30.0)]
    if convex:
        i, _ = max(convex, key=lambda t: (t[1], pts[t[0]][1]))
        return i
    best = 0
    for i, p in enumerate(pts):
        if p[1] > pts[best][1] + 1e-9:
            best = i
    return best


# ---------------------------------------------------------------------------

class SmoothJob(Job):
    """Letter wall shells planned the modern way, emitted in vendor dialect."""

    def __init__(self, par: Params, dxf_path, opts: SmoothOpts | None = None,
                 cell=0.25, min_area=0.0, max_area=0.0,
                 scale=0.0, offset=(0.0, 0.0), place=None):
        super().__init__(par, dxf_path, cell=cell, offset=(0.0, 0.0),
                         place=None, fill=False, hem=False,
                         min_area=min_area, max_area=max_area)
        self.o = opts or SmoothOpts()
        self.o.retract_mm = float(par.glu.dbDisGlueBack)
        self.smm_scale = float(scale or 0.0) or 1.0
        self.smm_offset = tuple(offset or (0.0, 0.0))
        self.smm_place = place
        self.w_width = float(par.glue_width)
        self.h_layer = float(par.let.dbHeightLayer)
        self.spacing = (self.o.wall_spacing
                        if self.o.wall_spacing
                        else auto_wall_spacing(self.w_width, self.h_layer))
        self.e_pm = e_per_mm(self.w_width, self.h_layer)
        self._insets = {}
        self._pocket_by_gid = {}
        self._seam_cache = {}
        self._gid_of = {}
        self.temp = None
        self.preside_prime = []
        self.stats = {}
        self.warnings = []

    # ------------------------------------------------------------------ load
    def load(self):
        super().load()
        if abs(self.smm_scale - 1.0) > 1e-12:
            s = self.smm_scale
            self.rings = [[(x * s, y * s) for x, y in r] for r in self.rings]
            self.chains = [[(x * s, y * s) for x, y in c] for c in self.chains]
        dx, dy = self.smm_offset
        if self.smm_place is not None:
            x0, y0, _, _ = geom.bbox(self.rings)
            dx += self.smm_place[0] - x0
            dy += self.smm_place[1] - y0
        if dx or dy:
            self.rings = [[(x + dx, y + dy) for x, y in r] for r in self.rings]
            self.chains = [[(x + dx, y + dy) for x, y in c] for c in self.chains]
        return self

    # ----------------------------------------------------------------- setup
    def prepare(self, pre_side=True):
        """Field, inset sets, pockets, seam map, speed table - before render."""
        p = self.p
        o = self.o
        extent = max(0.0, (o.walls - 1) * self.spacing)
        if o.pangkon > 0:
            extent = max(extent, 1.8)
        side = p.let.dbOffsetPreSide + p.let.dbThicknessOrigin \
            * max(0, p.let.iNumPreSide)
        self.build_field(max(extent, side))

        self._gid_of = {id(r): i for i, r in enumerate(self.rings)}

        for k in range(1, o.walls):
            level = -(k * self.spacing)
            iso = [simplify(r) for r in self.field.iso(level)
                   if len(r) >= 6]
            map_by_gid = {i: [] for i in range(len(self.rings))}
            for r in iso:
                gid = self._nearest_contour(r)
                map_by_gid[gid].append(r)
                self._gid_of[id(r)] = gid
            self._insets[k] = map_by_gid

        self._pocket_by_gid = {}
        if o.pangkon > 0:
            for delta in (1.8, 1.2, 0.6):
                iso = [simplify(r) for r in self.field.iso(-delta)
                       if len(r) >= 6]
                map_by_gid = {i: [] for i in range(len(self.rings))}
                for r in iso:
                    gid = self._nearest_contour(r)
                    map_by_gid[gid].append(r)
                    self._gid_of[id(r)] = gid
                for gid, rs in map_by_gid.items():
                    self._pocket_by_gid.setdefault(gid, []).extend(rs)

        # seat layers: floor of the pocket sits at lip - (thickness + 0.6)
        self.pocket_layers = set()
        if o.pangkon > 0:
            h = self.h_layer
            lip = p.layer_z(p.layer_count - 1)
            idx = max(0, int(round((lip - (o.pangkon + 0.6)) / h)) - 1)
            self.pocket_layers.add(min(idx, p.layer_count - 1))
            if o.pangkon_back:
                back = max(0, int(round((o.pangkon + 0.6) / h)) - 1)
                self.pocket_layers.add(min(back, p.layer_count - 1))

        self._resolve_speeds()
        return self

    def _nearest_contour(self, ring) -> int:
        r0 = ring[0]
        best, bd = 0, float("inf")
        for i, base in enumerate(self.rings):
            d = min((r0[0] - q[0]) ** 2 + (r0[1] - q[1]) ** 2 for q in base)
            if d < bd:
                bd = d
                best = i
        return best

    def _resolve_speeds(self):
        o = self.o
        if self.rings:
            x0, y0, x1, y1 = geom.bbox(self.rings)
            self.bbox_dim = max(x1 - x0, y1 - y0)
        else:
            self.bbox_dim = 0.0
        if o.work_f:
            self.f_work = int(o.work_f)
            self.speed_note = ""
        else:
            self.f_work, self.speed_note = speed_class_feed(
                self.bbox_dim, o.speed_class)
        self.f_work = max(600, int(self.f_work))
        self.temp = temp_for_speed(self.f_work / 60.0)
        # single source of truth: the writer's head/switch lines read these
        self.p.pri.iT0 = self.p.pri.iT1 = self.temp
        self.p.pri.iSpeedWork = self.f_work

    def _bed_gate(self, pre_side=True):
        """Extruding-plastic must sit inside the bed; inside 15 mm warn (T22)."""
        p = self.p
        x0, y0, x1, y1 = geom.bbox(self.rings)
        if pre_side and p.let.dbOffsetPreSide > 0 and p.let.iNumPreSide > 0:
            side = p.let.dbOffsetPreSide \
                + p.let.dbThicknessOrigin * max(0, p.let.iNumPreSide)
            x0 -= side + p.glu.dbDisGlueBack
            y0 -= side + p.glu.dbDisGlueBack
            x1 += side
            y1 += side
        if x0 < 0.0 or y0 < 0.0 or x1 > BED[0] or y1 > BED[1]:
            raise SystemExit(
                "smooth job leaves the %.0f x %.0f bed "
                "(plastic bbox + pre-side frame: %.1f %.1f .. %.1f %.1f); "
                "add --place X,Y to move it"
                % (BED[0], BED[1], x0, y0, x1, y1))
        if x0 < self.o.bed_margin or y0 < self.o.bed_margin \
                or BED[0] - x1 < self.o.bed_margin \
                or BED[1] - y1 < self.o.bed_margin:
            self.warnings.append(
                "design sits %.1f..%.1f / %.1f..%.1f mm from the bed edges; "
                "the vendor manual asks for >= 15 mm" % (x0, y0,
                                                        BED[0] - x1, BED[1] - y1))

    # -------------------------------------------------------------- planning
    def layer_plan(self, li):
        """[(ring, gid, pocket?)] for one layer.

        Group order alternates every layer (brief 4.3); inside one contour the
        innermost wall prints first and the face line last, sorted deepest
        pocket ring first.
        """
        plan = []
        groups = list(range(len(self.rings)))
        if self.o.alternate and li % 2 == 1:
            groups.reverse()
        pockets = li in getattr(self, "pocket_layers", ())
        for gid in groups:
            for k in range(self.o.walls - 1, 0, -1):
                for r in self._insets.get(k, {}).get(gid, ()):
                    plan.append((r, gid, False))
            plan.append((self.rings[gid], gid, False))
            if pockets:
                for r in self._pocket_by_gid.get(gid, ()):
                    plan.append((r, gid, True))
        return plan

    def _speeds_table(self):
        """Per-layer wall feed with the min-layer-time cap applied."""
        o = self.o
        min_t = max(0.0, o.min_layer_time)
        table = []
        self.layer_lengths = []
        self.layer_len_total = 0.0
        for li in range(self.p.layer_count):
            L = 0.0
            for ring, _gid, _pk in self.layer_plan(li):
                L += geom.polyline_length(ring, closed=True)
            self.layer_lengths.append(L)
            self.layer_len_total += L
            f = self.f_work
            if li == 0:
                f = min(f, o.first_f)
            if min_t > 0.0 and L > 0.0:
                cap = L / min_t * 60.0
                f = min(f, max(o.min_f, int(round(cap))))
            table.append(int(max(o.min_f, f)))
        self.f_ring = table

    # ----------------------------------------------------------------- output
    def render(self, out_path, pre_side=True, progress=None):
        """Emit the smooth job; returns a stats dict for the CLI report."""
        p = self.p
        o = self.o
        if o.walls < 1:
            raise SystemExit("--walls must be >= 1")
        if o.spiral:
            raise SystemExit("--spiral is Phase 2 (brief section 5); this "
                             "build plans contour-by-contour walls only - "
                             "implement the spiral after the Fase 1 coupons "
                             "are verified on the machine")
        if not self.rings:
            raise SystemExit("no contours loaded")
        self.prepare(pre_side=pre_side)
        self._bed_gate(pre_side=pre_side)
        self._speeds_table()

        self._writer = None
        blocks = 0
        work_len = 0.0
        travel_len = 0.0
        retracts = 0
        planned_stops = [0] * p.layer_count
        seam_map = {}
        est_work_s = 0.0

        tools = sorted({_tool(p, p.glue_no_for_layer(i))
                        for i in range(p.layer_count)})
        if not tools:
            tools = [0]
        first_tool = _tool(p, p.glue_no_for_layer(0))

        with open(out_path, "w", encoding="ascii", newline="\n") as fh:
            w = GCodeWriter(p, fh)
            self._writer = w
            w.write_head(tools)
            w.write_initial_switch(first_tool)

            pre_rings = self.pre_side_rings() if pre_side else []
            if pre_rings:
                w.write_pre_side(pre_rings, p.layer_z(0))
                d = p.glu.dbDisGlueBack
                for ring in pre_rings:
                    self.preside_prime.append((ring[0][0] - d,
                                               ring[0][1] - d))

            # flatten the whole job into one sequential stream so every close
            # knows exactly which approach the NEXT ring will need
            stream = []
            for li in range(p.layer_count):
                for ring, gid, pk in self.layer_plan(li):
                    stream.append((li, ring, gid, pk))

            cur_glue = p.glue_no_for_layer(0)
            prev_li = prev_gid = None
            first_entry = True

            for j, (li, ring, gid, pk) in enumerate(stream):
                h = p.layer_z(li)
                glue = p.glue_no_for_layer(li)
                post_switch = glue != cur_glue
                if post_switch:
                    w.write_color_switch(_tool(p, glue), h)
                    cur_glue = glue

                pts = self._seam_rotate(ring)
                if len(pts) < 3:
                    prev_li, prev_gid = li, gid
                    first_entry = False
                    continue

                f = o.pocket_f if pk else self.f_ring[li]
                if post_switch and not pk:
                    f = min(f, o.postswitch_f)

                # ---- classify this approach (the previous close already ran)
                if first_entry:
                    kind = "start"          # after the pre-side's own retract
                elif post_switch:
                    kind = "switch"
                elif gid == prev_gid and li == prev_li:
                    kind = "adjacent"       # insets/pockets inside one contour
                elif gid == prev_gid and li == prev_li + 1:
                    kind = "lift"           # boundary on an open contour
                else:
                    kind = "stop"
                    planned_stops[li] += 1

                xy0 = pts[0]
                # ---- approach
                travel_len += geom.dist(w.pos, xy0)
                w.w(";start printf")
                blocks += 1
                if kind in ("start", "stop"):
                    w.w(f"G0 F{p.pri.iSpeedIdle} "
                        f"X{g(xy0[0])} Y{g(xy0[1])} Z{zg(h)}")
                    w.w("G92 E0")
                    push = self.o.retract_mm + self.o.prime
                    w.acc[w.tool] = push
                    w.w(f"G1 F{o.unretract_f} E{g(push)}")
                elif kind == "adjacent":
                    w.w(f"G0 F{f} X{g(xy0[0])} Y{g(xy0[1])}")
                else:                       # lift | switch
                    w.w(f"G0 F{f} X{g(xy0[0])} Y{g(xy0[1])} Z{zg(h)}")

                printed, gain_len, e_end = self._print_ring(w, pts, h, f)
                work_len += printed
                est_work_s += printed / (f / 60.0)
                key = self._seam_key(ring)
                seam_map.setdefault(key, {})[li] = (xy0[0], xy0[1])

                # ---- close for whatever the next ring needs
                nxt = stream[j + 1] if j + 1 < len(stream) else None
                if nxt is None:
                    pass                    # write_tail does the final retract
                else:
                    nli, _nring, ngid, _npk = nxt
                    if p.glue_no_for_layer(nli) != cur_glue:
                        self._close_wipe(w, pts, e_end)
                    elif ngid == gid and nli in (li, li + 1):
                        pass                # flow continues across the inset
                    else:
                        self._close_stop(w, pts, e_end, h)
                        retracts += 1
                        est_work_s += 0.4

                prev_li, prev_gid = li, gid
                first_entry = False

            write_pos = w.pos
            w.write_tail(write_pos, p.layer_z(p.layer_count - 1))

        total_est_s = est_work_s + (1.2 if pre_rings else 0.0)
        self.stats = {
            "layers": p.layer_count,
            "contours": len(self.rings),
            "walls": o.walls,
            "spacing": self.spacing,
            "e_per_mm": self.e_pm,
            "f_work": self.f_work,
            "temp": self.temp,
            "speed_note": self.speed_note,
            "speed_class": o.speed_class if not o.work_f else "explicit",
            "stops_by_layer": planned_stops,
            "seam": seam_map,
            "seam_mode": o.seam,
            "pocket_layers": sorted(self.pocket_layers),
            "blocks": blocks,
            "retracts": retracts,
            "work_len": work_len,
            "travel_len": travel_len,
            "est_time_min": total_est_s / 60.0,
            "warnings": list(self.warnings),
        }
        return self.stats

    # ------------------------------------------------------------ primitives
    def _seam_rotate(self, ring):
        """Dedupe, drop the closing vertex, rotate to the locked seam."""
        pts = geom.dedupe(ring)
        if len(pts) >= 3:
            if geom.dist(pts[0], pts[-1]) < 1e-6:
                pts = pts[:-1]
        if len(pts) < 3:
            return pts
        idx = self._seam_for(pts)
        return pts[idx:] + pts[:idx]

    def _seam_for(self, pts):
        mode = self.o.seam
        if not isinstance(mode, str):
            return pick_seam_index(pts, mode)
        return pick_seam_index(pts, mode)

    def _seam_key(self, ring):
        """Stable identity for a ring across layers (vertex count + SHAPE)."""
        return (len(ring),
                round(ring[0][0], 3), round(ring[0][1], 3),
                round(ring[1][0], 3))

    def _print_ring(self, w, pts, h, f):
        """Extrude one closed ring from its seam, coasting the tail.

        Returns (printed_len, gain_len, e_end).
        """
        epm = self.e_pm
        acc = w.acc.get(w.tool, 0.0)
        n = len(pts)
        total = geom.polyline_length(pts, closed=True)
        coast = min(self.o.coast, total * 0.2) if self.o.coast > 0.0 else 0.0
        printed = 0.0
        gain_len = 0.0
        first = True
        remaining = total
        for i in range(n):
            a = pts[i]
            b = pts[(i + 1) % n]
            d = geom.dist(a, b)
            if d < 1e-9:
                continue
            remaining -= d
            if remaining >= coast - 1e-9:   # still laying fresh plastic
                acc += d * epm
                gain_len += d
            e_word = f"E{g(acc)}"
            if first:
                w.w(f"G1 F{f} X{g(b[0])} Y{g(b[1])} {e_word}")
                first = False
            else:
                w.w(f"G1 X{g(b[0])} Y{g(b[1])} {e_word}")
            printed += d
            w.pos = (b[0], b[1])
        w.acc[w.tool] = acc
        w.z = h
        return printed, gain_len, acc

    def _close_wipe(self, w, pts, e_end):
        """Back off along the path to relieve pressure; no retract here.

        The ring has just closed back on the seam (``pts[0]``), so wiping
        means stepping from there back toward ``pts[-1]``.  Used before a
        colour switch (which does its own large retraction) and inside the
        stop epilogue.
        """
        o = self.o
        if not (o.wipe and o.wipe_mm > 0.0) or len(pts) < 2:
            return 0.0
        a = pts[-1]
        b = pts[0]
        vec = (b[0] - a[0], b[1] - a[1])
        L = math.hypot(*vec)
        if L < 1e-9:
            return 0.0
        step = min(o.wipe_mm, L * 0.9)
        q = (b[0] - vec[0] / L * step, b[1] - vec[1] / L * step)
        e = w.acc.get(w.tool, e_end) - step * self.e_pm
        w.acc[w.tool] = e
        w.w(f"G1 F{o.retract_f} X{g(q[0])} Y{g(q[1])} E{g(e)}")
        w.pos = q
        return 0.0

    def _close_stop(self, w, pts, e_end, h):
        """Wipe, retract, hop - the full stop epilogue (brief 4.3)."""
        o = self.o
        self._close_wipe(w, pts, e_end)
        e = w.acc.get(w.tool, e_end) - self.o.retract_mm
        w.acc[w.tool] = e
        w.w(f"G1 F{o.retract_f} E{g(e)}")
        w.w(f"G0 F{self.p.pri.iSpeedIdle} Z{zg(h + o.hop)}")
        return 0.0


def _tool(par: Params, glue_no: int) -> int:
    return par.tool_no(glue_no)


# ---------------------------------------------------------------------------
# independent file audit used by gates T17-T26 and the CLI report

_NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
_RE_WORDS = re.compile(r"([XYZEF])(%s)" % _NUM)
_RE_TOOL = re.compile(r"^T(\d+)\s*$")


def audit_file(path, extra_plastic=(), preside_prime=()):
    """Parse a ZCCAD/letter file back into structural facts (no engine use).

    Returns dict:
      blocks - one entry per ``;start printf`` marker: z, tool, printed path
               length, extrusion gain/length (for an honest E/mm), bare-E
               pushes, and whether each push followed a G92 E0;
      stops_by_layer - full retracts (bare-E at the retract speed) bucketed by
               layer Z, excluding the pre-side frame and the final tail
               retract (a stop only counts if printing resumes later);
      bbox - plastic bounding box (extruding moves + supplied prime points).
    """
    x = y = z = 0.0
    e_running = 0.0
    tool = 0
    relative = False
    in_preside = False
    after_end = False
    blocks = []
    cur = None
    stops_raw = []                      # (z_bucket, markers_seen)
    markers = 0
    retracts = 0
    plastic = list(extra_plastic) + list(preside_prime)
    e_used = {}
    e_reset = True      # True right after G92 E0: a push is guarded until the
                        # next real extrusion consumes the reset

    def close_block():
        nonlocal cur
        if cur is not None:
            blocks.append(cur)
            cur = None

    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            s = raw.strip()
            if not s:
                continue
            if s.startswith(";"):
                if s == ";G code end":
                    after_end = True
                elif s == ";calculatePreSide start":
                    in_preside = True
                elif s == ";calculatePreSide end":
                    in_preside = False
                elif s == ";start printf" and not after_end:
                    close_block()
                    cur = {"z": z, "tool": tool, "printed": 0.0,
                           "gain": 0.0, "gain_len": 0.0, "loss": 0.0,
                           "pushes": [], "g92": 0, "g92_guarded": True,
                           "travel_xy": None, "preside": in_preside}
                    markers += 1
                continue
            up = s.split(";", 1)[0].strip().upper()
            if not up:
                continue
            if up == "G91":
                relative = True
                continue
            if up == "G90":
                relative = False
                continue
            if up.startswith("G92"):
                words = dict(_RE_WORDS.findall(up))
                if "E" in words:
                    e_running = float(words["E"])
                    e_reset = abs(float(words["E"])) < 1e-9
                    if cur is not None:
                        cur["g92"] += 1
                continue
            m = _RE_TOOL.match(up)
            if m:
                tool = int(m.group(1))
                continue
            if not (up.startswith("G0") or up.startswith("G1")):
                continue
            words = dict(_RE_WORDS.findall(up))
            if relative:
                # header/footer G91 shuffles move by delta
                if "X" in words:
                    x += float(words["X"])
                if "Y" in words:
                    y += float(words["Y"])
                if "Z" in words:
                    z += float(words["Z"])
                if "E" in words:
                    e_running += float(words["E"])
                continue
            new_x = float(words["X"]) if "X" in words else x
            new_y = float(words["Y"]) if "Y" in words else y
            if "Z" in words:
                z = float(words["Z"])
            dx = new_x - x
            dy = new_y - y
            moved = ("X" in words) or ("Y" in words)
            L = math.hypot(dx, dy)
            has_e = "E" in words
            if after_end:
                x, y = new_x, new_y
                continue

            if has_e:
                ne = float(words["E"])
                dE = ne - e_running
                f = float(words.get("F", 0.0))
                if moved:
                    if cur is not None:
                        cur["printed"] += L     # extruding, coast or wipe path
                        cur["z"] = z            # the print's own layer height
                    plastic.append((new_x, new_y))
                    if dE > 1e-9:
                        if cur is not None:
                            cur["gain"] += dE
                            cur["gain_len"] += L
                        e_reset = False
                    elif dE < -1e-9 and cur is not None:
                        cur["loss"] -= dE       # wipe stroke
                else:                           # bare-E: prime or retract
                    if dE > 1e-9:
                        if cur is not None:
                            if not e_reset:
                                cur["g92_guarded"] = False
                            cur["pushes"].append(round(dE, 6))
                    elif dE < -0.5:
                        if abs(f - 1800.0) < 1.0 and not in_preside:
                            retracts += 1
                            stops_raw.append((round(z, 2), markers))
                    e_reset = False if dE > 1e-9 else e_reset
                if cur is not None:
                    e_used[tool] = e_used.get(tool, 0.0) + dE
                e_running = ne
            elif moved and cur is not None:
                # an XY travel inside a block records where printing begins
                cur["travel_xy"] = (new_x, new_y)
            x, y = new_x, new_y
    close_block()

    stops_by_layer = {}
    total_markers = markers
    for zb, m_done in stops_raw:
        if m_done < total_markers:          # more printing happens after it
            stops_by_layer[zb] = stops_by_layer.get(zb, 0) + 1

    if plastic:
        xs = [p[0] for p in plastic]
        ys = [p[1] for p in plastic]
        bbox = (min(xs), min(ys), max(xs), max(ys))
    else:
        bbox = None

    main_blocks = [b for b in blocks if not b["preside"]]
    printed_blocks = [b for b in main_blocks if b["printed"] > 0.5]
    return {
        "blocks": blocks,
        "main_blocks": main_blocks,
        "printed_blocks": printed_blocks,
        "markers": markers,
        "retracts": retracts,
        "stops_by_layer": stops_by_layer,
        "bbox": bbox,
        "tools": sorted({b["tool"] for b in printed_blocks} | set(e_used)),
        "e_used": e_used,
        "prime_guarded": all(b["g92_guarded"] for b in main_blocks),
        "blocks_with_push": sum(1 for b in main_blocks if b["pushes"]),
        "printed_mm": sum(b["printed"] for b in main_blocks),
    }
