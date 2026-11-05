"""Universal FDM G-code: the letter geometry on a generic printer.

Family `universal` re-uses exactly the layer geometry the ZCCAD path produces
(Job passes / hem / acrylic pocket) and streams it out in standard Marlin
G-code that a Bambu Lab class printer accepts:

  * absolute XYZ, relative E (M83) - no vendor extrusion counter anywhere
  * retraction on every long travel, optional z hop
  * skirt / brim on layer 0, solid bottom and top layers, walls, infill
  * per-layer markers a slicer-class viewer can scrub:
        ;LAYER_CHANGE ;LAYER:n ;HEIGHT:z ;TYPE:WALL-OUTER|WALL-INNER|
        SOLID-...|INFILL|SOLID-INFILL|SKIRT|BRIM
  * fan ramp on the configured layer, first-layer nozzle temperature bump,
    park + cooldown tail

Extrusion uses the honest FDM flow model

    E = path_mm * line_width * layer_height / (pi * (filament_dia / 2) ** 2)

while the vendor dialect keeps its cubic model (params.e_per_mm).  The two
must never be confused inside one file; the family switch is the boundary.

Infill is a scanline rectilinear hatch clipped against the interior iso-
contours with the same even-odd technique geom.Field._sign() uses, so it
cannot invent geometry the distance field does not know.  `concentric`
instead simply prints more wall passes all the way in - the letter-shell
look, identical to --fill on the ZCCAD path.

stdlib-only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import geom
from .machines import MachineProfile
from .params import Params
from .job import outer_rings, order_rings


def _num(v, dp=3):
    """Short fixed-point decimal (no exponent), trailing zeros trimmed."""
    t = ("%.*f" % (dp, float(v))).rstrip("0").rstrip(".")
    if t in ("-0", "", "-"):
        t = "0"
    return t


def e_per_mm(profile: MachineProfile, width: float, layer: float) -> float:
    if width <= 0 or layer <= 0:
        return 0.0
    r = profile.filament_dia / 2.0
    return (width * layer) / (math.pi * r * r)


@dataclass
class UniversalOpts:
    infill_density: float = 15.0         # %, 0 disables infill
    infill_pattern: str = "rectilinear"  # rectilinear | concentric
    solid_bottom: int = 3                # solid base layers (3 layers = 0.9 mm alas, from TES IM)
    solid_top: int = 2                   # solid layers at the part top
    skirt_lines: int = 2
    skirt_gap: float = 6.0
    brim: float = 0.0
    multitool: bool = True               # honour colour bands -> T switches
    scale: float = 0.0                   # multiply DXF coords (0 = unchanged)
    fit_bed: bool = False                # scale down (only) to fit the bed
    center_bed: bool = True              # put the part in the middle of bed


class UniversalWriter:
    """Streams standard FDM G-code for one job."""

    def __init__(self, profile: MachineProfile, par: Params, out,
                 opts: UniversalOpts):
        self.pro = profile
        self.p = par
        self.out = out
        self.o = opts
        self.width = par.glue_width
        self.layer_h = par.let.dbHeightLayer
        self.e_mm = e_per_mm(profile, self.width, self.layer_h)
        self.pos = (0.0, 0.0)
        self.z = 0.0
        self.tool = 0
        self._retracted = False
        self._lines = 0
        self.len_by_tool = {0: 0.0}
        self.e_by_tool = {0: 0.0}
        self.time_s = 0.0

    # ---------------------------------------------------------------- output
    def w(self, line=""):
        self.out.write(line + "\n")
        self._lines += 1

    # ------------------------------------------------------------------ flow
    def e_for(self, length: float) -> float:
        return length * self.e_mm

    def _book(self, de, run):
        self.e_by_tool[self.tool] = self.e_by_tool.get(self.tool, 0.0) + de
        self.len_by_tool[self.tool] = \
            self.len_by_tool.get(self.tool, 0.0) + run
        self.time_s += run / self.pro.retract_feed * 60.0

    def _retract(self):
        if self._retracted:
            return
        r = self.pro.retract_mm
        self.w("G1 E-%s F%d" % (_num(r, 2), self.pro.retract_feed))
        self._retracted = True
        self.e_by_tool[self.tool] = self.e_by_tool.get(self.tool, 0.0) - r
        self.time_s += r / self.pro.retract_feed * 60.0

    def _unretract(self, extra=0.0):
        total = self.pro.retract_mm + self.pro.restart_extra + extra
        if self._retracted:
            self.w("G1 E%s F%d" % (_num(total, 2), self.pro.retract_feed))
            self._retracted = False
            self.e_by_tool[self.tool] = \
                self.e_by_tool.get(self.tool, 0.0) + total
            self.time_s += total / self.pro.retract_feed * 60.0
        elif extra > 0:
            self.w("G1 E%s F%d" % (_num(extra, 2), self.pro.retract_feed))
            self.e_by_tool[self.tool] = \
                self.e_by_tool.get(self.tool, 0.0) + extra
            self.time_s += extra / self.pro.retract_feed * 60.0

    def travel(self, x, y, z=None):
        """Move without extruding.  Raise to the travel Z first, retract on
        long hops, XY second, and land on the layer Z only afterwards, so the
        nozzle never drags through the previous layer's beads."""
        dist = math.hypot(x - self.pos[0], y - self.pos[1])
        self.time_s += dist / self.pro.travel_speed * 60.0
        target_z = self.z if z is None else (self.z + self.pro.z_hop
                                            if self.pro.z_hop > 0 and
                                            dist >= self.pro.retract_min_dist
                                            else max(self.z, z))
        if target_z - self.z > 1e-6:
            self.w("G0 F%d Z%s" % (self.pro.z_speed, _num(target_z)))
            self.time_s += (target_z - self.z) / self.pro.z_speed * 60.0
            self.z = target_z
        if dist >= self.pro.retract_min_dist:
            self._retract()
        self.w("G0 F%d X%s Y%s" % (self.pro.travel_speed, _num(x), _num(y)))
        if z is not None and abs(z - self.z) > 1e-6:
            self.w("G0 F%d Z%s" % (self.pro.z_speed, _num(z)))
            self.time_s += abs(z - self.z) / self.pro.z_speed * 60.0
            self.z = z
        self.pos = (x, y)

    def open_path(self, pts, z, speed, typ="WALL-INNER", closed=True,
                  prime=0.0):
        """Extrude `pts`: retract, travel to start, unretract(+prime), run."""
        d = geom.dedupe(pts)
        if len(d) < 2:
            return
        if closed and geom.dist(d[0], d[-1]) > 1e-9:
            d.append(d[0])
        run = 0.0
        for i in range(1, len(d)):
            run += math.dist(d[i - 1], d[i])
        if run < 1e-9:
            return
        self.w(";TYPE:%s" % typ)
        self.travel(d[0][0], d[0][1], z=z)
        self._unretract(prime)
        # z-hop travel left the nozzle up; drop it to the layer exactly once
        if abs(self.z - z) > 1e-6:
            self.w("G0 F%d Z%s" % (self.pro.z_speed, _num(z)))
            self.time_s += abs(z - self.z) / self.pro.z_speed * 60.0
            self.z = z
        de = self.e_for(run)
        self.e_by_tool[self.tool] = self.e_by_tool.get(self.tool, 0.0) + de
        self.len_by_tool[self.tool] = \
            self.len_by_tool.get(self.tool, 0.0) + run
        self.time_s += run / speed * 60.0
        for i in range(1, len(d)):
            seg = math.dist(d[i - 1], d[i])
            self.w("G1 F%d X%s Y%s E%s"
                   % (speed, _num(d[i][0]), _num(d[i][1]),
                      _num(self.e_for(seg), 5)))
        self.pos = (d[-1][0], d[-1][1])

    # ---------------------------------------------------------------- header
    def write_head(self, first_tool=0):
        pro = self.pro
        bed = pro.bed_temp or 0
        fb = pro.first_layer_bed or bed
        self.w("; LetterLab universal FDM output")
        self.w("; profile: %s" % pro.name)
        if fb > 0:
            self.w("M140 S%d" % fb)
        if pro.first_layer_temp:
            self.w("M104 S%d T0" % pro.first_layer_temp)
            self.w("M109 S%d T0" % pro.first_layer_temp)
        if fb > 0:
            self.w("M190 S%d" % fb)
        self.w("G90")
        self.w("M83")
        self.w("G28")
        start_z = min(pro.z_max, max(10.0, pro.z_hop or 0.0))
        self.w("G0 F%d Z%s" % (pro.z_speed, _num(start_z)))
        self.z = start_z
        self.w("M107")
        self.tool = first_tool

    # ---------------------------------------------------------------- layers
    def layer_start(self, idx, z, tool=0):
        pro = self.pro
        self.w(";LAYER_CHANGE")
        self.w(";LAYER:%d" % idx)
        self.w(";HEIGHT:%s" % _num(z))
        if idx == 1 and pro.nozzle_temp != pro.first_layer_temp:
            self.w("M104 S%d T%d" % (pro.nozzle_temp, self.tool))
        if idx == 2 and pro.bed_temp and \
                (pro.first_layer_bed or pro.bed_temp) != pro.bed_temp:
            self.w("M140 S%d" % pro.bed_temp)
        if idx == pro.fan_layer:
            self.w("M106 S%d" % pro.fan_layer_speed)
        elif idx == pro.fan_layer + 1:
            self.w("M106 S%d" % pro.fan_value)
        if tool != self.tool:
            self.w("T%d" % tool)
            self.tool = tool
            if pro.prime_blob > 0:
                self._unretract(pro.prime_blob)

    # ------------------------------------------------------------------ tail
    def write_tail(self, top_z):
        pro = self.pro
        park_x = 0.0 if pro.home_corner == "min" else pro.bed_x
        self._retract()
        self.w("M106 S0")
        self.w("M104 S0 T0")
        if pro.bed_temp:
            self.w("M140 S0")
        self._unretract()
        self.w("; print complete")
        self.w("G0 F%d Z%s" % (pro.z_speed, _num(min(pro.z_max, top_z + 20))))
        self.w("G0 F%d X%s Y%s" % (pro.travel_speed, _num(park_x), _num(0.0)))
        self.w("M84")

    # ------------------------------------------------------- infill geometry
    def infill_spacing(self, solid: bool) -> float:
        if solid:
            return max(self.width * 0.45, 0.45)
        if self.o.infill_density <= 0:
            return 0.0
        return self.width / (self.o.infill_density / 100.0)


# ------------------------------------------------------------- hatch fill
def hatch(clip_rings, spacing, angle_deg):
    """Scanline hatch clipped by even-odd parity against closed `clip_rings`.

    Returns open polylines serpentine-ordered per scanline.  `angle_deg`
    rotates the hatch: 0 = along +X.
    """
    if spacing <= 0 or not clip_rings:
        return []
    a = math.radians(angle_deg)
    ca, sa = math.cos(-a), math.sin(-a)

    def rot(p):
        x, y = p
        return (x * ca - y * sa, x * sa + y * ca)

    def back(p):
        u, v = p
        return (u * math.cos(a) - v * math.sin(a),
                u * math.sin(a) + v * math.cos(a))

    edges = []
    ys = []
    for ring in clip_rings:
        r = [rot(p) for p in ring]
        n = len(r)
        if n < 3:
            continue
        ys.extend(v for _, v in r)
        for i in range(n):
            (ax, ay), (bx, by) = r[i], r[(i + 1) % n]
            if ay != by:
                edges.append((ax, ay, bx, by))
    if not edges:
        return []
    ymin, ymax = min(ys), max(ys)
    lines = []
    y = ymin + spacing * 0.5
    flip = False
    while y <= ymax:
        xs = []
        for ax, ay, bx, by in edges:
            if (ay > y) != (by > y):
                t = (y - ay) / (by - ay)
                xs.append(ax + t * (bx - ax))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            xa, xb = xs[k], xs[k + 1]
            if xb - xa < 0.3:
                continue
            if flip:
                xa, xb = xb, xa
            lines.append([back((xa, y)), back((xb, y))])
        y += spacing
        flip = not flip
    return lines


def nearest_order(rings, pos):
    """Greedy nearest-start ordering - the engine's own ring ordering."""
    return order_rings(rings, pos)


# ------------------------------------------------------------ full pipeline
def _fit_job_to_bed(job, profile: MachineProfile, opts: UniversalOpts,
                    width: float):
    """Scale / translate the geometry for a universal machine bed.

    `fit_bed` only ever shrinks: it keeps a called-out 500 mm letter
    meaningful on a 256 mm bed by multiplying the DXF coordinates, not by
    shrinking the printed layer heights.  A scale factor that still leaves
    the part wider than the bed raises, because off-bed G-code can crash a
    printer.  Skirt/brim margin is kept around the part, and the part is
    centred when `center_bed` is on."""
    if opts.scale <= 0 and not opts.fit_bed and not opts.center_bed:
        return 0.0
    s = opts.scale if opts.scale > 0 else 1.0
    x0, y0, x1, y1 = geom.bbox(job.rings)
    bw, bh = x1 - x0, y1 - y0
    if opts.fit_bed and min(profile.bed_x, profile.bed_y) > 0:
        keep = max(2.0, opts.skirt_gap + (opts.skirt_lines + 2) * width)
        limit_x = max(2.0, min(profile.bed_x, profile.bed_max_x or
                               profile.bed_x) - 2 * keep)
        limit_y = max(2.0, min(profile.bed_y, profile.bed_max_y or
                               profile.bed_y) - 2 * keep)
        if bw > limit_x or bh > limit_y:
            s = min(s, min(limit_x / bw, limit_y / bh))
    if s > 0 and abs(s - 1.0) > 1e-9:
        job.rings = [[(x * s, y * s) for x, y in r] for r in job.rings]
        job.chains = [[(x * s, y * s) for x, y in c] for c in job.chains]
        job.field = None
        job.seat_field = None
    if opts.center_bed:
        x0, y0, x1, y1 = geom.bbox(job.rings)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = (profile.bed_x / 2 - cx), (profile.bed_y / 2 - cy)
        if dx or dy:
            job.rings = [[(x + dx, y + dy) for x, y in r] for r in job.rings]
            job.chains = [[(x + dx, y + dy) for x, y in c] for c in job.chains]
            job.field = None
            job.seat_field = None
    # final contract: the part itself must sit on the bed
    x0, y0, x1, y1 = geom.bbox(job.rings)
    if (x0 < -0.01 or y0 < -0.01
            or x1 > (profile.bed_max_x or profile.bed_x) + 0.01
            or y1 > (profile.bed_max_y or profile.bed_y) + 0.01):
        raise SystemExit(
            "universal: part %gx%g mm does not fit the %s bed %gx%g "
            "(tune --scale or --fit-bed)"
            % (x1 - x0, y1 - y0, profile.name, profile.bed_x, profile.bed_y))
    return s


def render_universal(job, profile: MachineProfile, out_path, opts: UniversalOpts,
                     progress=None):
    """Write a complete universal-family file for a loaded Job."""
    w = UniversalWriter(profile, job.p, open(out_path, "w", encoding="ascii",
                                             newline="\n"), opts)
    try:
        _emit(job, profile, w, progress)
    finally:
        w.out.close()
    return dict(
        lines=w._lines,
        len_by_tool={k: round(v / 1000.0, 1) for k, v in
                     sorted(w.len_by_tool.items())},
        e_by_tool={k: round(v / 1000.0, 2) for k, v in
                   sorted(w.e_by_tool.items())},
        est_time_min=round(w.time_s / 60.0, 1),
    )


def _emit(job, profile, w: UniversalWriter, progress=None):
    p = job.p
    _fit_job_to_bed(job, profile, w.o, w.width)
    off_total = max(0.0, p.let.iThichnessCount) * p.let.dbThichnessOffset
    infill_extra = (w.infill_spacing(solid=True) if w.o.infill_density > 0
                    else 0.0)
    field_pad = max(off_total, infill_extra) + w.width * 2 + job.pad
    skirt_pad = (w.o.skirt_gap + 2 * w.width + w.o.skirt_lines * w.width
                 if (w.o.skirt_lines or w.o.brim > 0) else 0.0)
    job.build_field(field_pad)
    if skirt_pad:
        outer = outer_rings(job.rings)
        skirt_field = None
        if outer:
            x0, y0, x1, y1 = geom.bbox(job.rings)
            m = skirt_pad + job.pad
            skirt_field = geom.Field(outer, x0 - m, y0 - m, x1 + m, y1 + m,
                                     job.cell)
    layer_n = p.layer_count
    hem_n = p.hem_layers if job.hem else 0
    if p.seat.width > 0:
        job.build_seat_field()

    # colour plan: T switches only when multitool is on and bands require it
    plan_tools = []
    for i in range(layer_n):
        t = p.tool_no(p.glue_no_for_layer(i))
        if t not in plan_tools:
            plan_tools.append(t)
    if not (w.o.multitool and len(plan_tools) > 1):
        plan_tools = [plan_tools[0]]
    first_tool = plan_tools[0]

    w.write_head(first_tool)

    # -- skirt / brim around the silhouettes ---------------------------------
    if skirt_field is not None:
        z0 = p.layer_z(0)
        for k in range(w.o.skirt_lines):
            lvl = w.o.skirt_gap + k * w.width
            if lvl <= 0:
                continue
            for r in skirt_field.iso(lvl):
                r = geom.drop_collinear(r, 0.15)
                if len(r) >= 3:
                    w.open_path(r, z0, w.pro.first_layer_speed, typ="SKIRT")
        k = 1 if w.o.skirt_lines else 0
        while w.o.brim > 0 and k * w.width <= w.o.brim and k <= 64:
            for r in skirt_field.iso(k * w.width):
                r = geom.drop_collinear(r, 0.15)
                if len(r) >= 3:
                    w.open_path(r, z0, w.pro.first_layer_speed, typ="BRIM")
            k += 1

    pos = (0.0, 0.0)
    hatch_angle_base = 45.0
    for li in range(layer_n):
        z = p.layer_z(li)
        tool = first_tool
        if len(plan_tools) > 1:
            t = p.tool_no(p.glue_no_for_layer(li))
            if t in plan_tools:
                tool = t
        w.layer_start(li, z, tool)

        solid = (li < w.o.solid_bottom) or (li >= layer_n - w.o.solid_top)
        passes = job.passes()
        hem_here = hem_n and li >= layer_n - hem_n
        if hem_here:
            passes = passes[:-1] if (len(passes) > 1) else passes

        rings_here = []
        for k, ring_set in enumerate(passes):
            ordered = nearest_order(ring_set, pos)
            rings_here.extend(ordered)
        for ring_set in job.seat_levels(li, layer_n):
            rings_here.extend(nearest_order(ring_set, pos))

        for ri, ring in enumerate(rings_here):
            if len(ring) < 3:
                continue
            speed = w.pro.first_layer_speed if li == 0 else w.pro.work_speed
            base = "WALL-OUTER" if ri == 0 else "WALL-INNER"
            w.open_path(ring, z, speed, typ=("SOLID-" + base) if solid else base)
            pos = ring[0]

        # infill between the last wall pass and the interior boundary
        infill_wanted = (w.o.infill_density > 0 or solid) and not hem_here
        if infill_wanted:
            if w.o.infill_pattern == "concentric":
                # extra wall passes at the infill spacing all the way in
                step = w.infill_spacing(solid)
                d = off_total + step
                clip_guard = 0
                while d < 400.0 and clip_guard < 400:
                    rings = [geom.drop_collinear(r, 0.15)
                             for r in job.field.iso(-d) if len(r) >= 3]
                    if not rings:
                        break
                    for r in nearest_order(rings, pos):
                        speed = w.pro.first_layer_speed if li == 0 \
                            else w.pro.work_speed
                        typ = "SOLID-INFILL" if solid else "INFILL"
                        w.open_path(r, z, speed, typ=typ)
                        pos = r[0]
                    d += step
                    clip_guard += 1
            else:
                clip = [r for r in job.field.iso(-(off_total + w.width * 0.5))
                        if len(r) >= 3]
                spacing = w.infill_spacing(solid)
                if spacing > 0 and clip:
                    if solid:
                        ang = 0.0 if li % 2 == 0 else 90.0
                    else:
                        ang = hatch_angle_base if li % 2 == 0 \
                            else hatch_angle_base + 90.0
                    lines = hatch(clip, spacing, ang)
                    speed = w.pro.first_layer_speed if li == 0 \
                        else w.pro.work_speed
                    typ = "SOLID-INFILL" if solid else "INFILL"
                    for line in lines:
                        w.open_path(line, z, speed, typ=typ, closed=False)
                    if lines:
                        pos = lines[-1][-1]
        if progress:
            progress(li + 1, layer_n)
    w.write_tail(p.layer_z(layer_n - 1))
