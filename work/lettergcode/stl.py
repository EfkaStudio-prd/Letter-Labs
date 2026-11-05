"""Pure Python standard library STL parser, 3D slicer, and job runner.

Supports:
  1. Binary STL and ASCII STL reading
  2. Fast plane-triangle slice at any Z level
  3. Robust loop stitching via spatial hash
  4. Both dialect families:
     - 'zccad': Taesin / Iguana letter printer dialect (GCodeWriter)
     - 'universal': generic FDM / Bambu Lab / Marlin dialect (UniversalWriter)
"""
from __future__ import annotations

import math
import os
import re
import struct
from collections import defaultdict
from typing import List, Tuple, Dict, Optional

from . import geom
from .gcode import GCodeWriter
from .params import Params
from .machines import MachineProfile, get_profile
from .universal import UniversalWriter, UniversalOpts, e_per_mm, hatch

Point2D = Tuple[float, float]
Point3D = Tuple[float, float, float]
Triangle = Tuple[Point3D, Point3D, Point3D]


# ====================================================================== STL IO
def read_stl(path: str) -> Tuple[List[Triangle], Tuple[float, float, float, float, float, float]]:
    """Read binary or ASCII STL file using pure stdlib.

    Returns (triangles, (xmin, ymin, zmin, xmax, ymax, zmax)).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"STL file not found: {path}")

    size = os.path.getsize(path)
    if size < 84:
        raise ValueError(f"File too small to be an STL: {path}")

    with open(path, "rb") as fh:
        header = fh.read(80)
        tri_count_bytes = fh.read(4)
        n_tri = struct.unpack("<I", tri_count_bytes)[0]
        expected_bin_size = 84 + n_tri * 50

        # Check if binary
        if size == expected_bin_size:
            raw = fh.read(n_tri * 50)
            triangles = []
            stride = 50
            fmt = "<12f"
            offset = 0
            xmin = ymin = zmin = float("inf")
            xmax = ymax = zmax = float("-inf")

            for _ in range(n_tri):
                f = struct.unpack_from(fmt, raw, offset)
                offset += stride
                v1 = (f[3], f[4], f[5])
                v2 = (f[6], f[7], f[8])
                v3 = (f[9], f[10], f[11])
                triangles.append((v1, v2, v3))

                for v in (v1, v2, v3):
                    if v[0] < xmin: xmin = v[0]
                    if v[0] > xmax: xmax = v[0]
                    if v[1] < ymin: ymin = v[1]
                    if v[1] > ymax: ymax = v[1]
                    if v[2] < zmin: zmin = v[2]
                    if v[2] > zmax: zmax = v[2]

            return triangles, (xmin, ymin, zmin, xmax, ymax, zmax)

    # ASCII fallback
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        triangles = []
        cur_verts = []
        xmin = ymin = zmin = float("inf")
        xmax = ymax = zmax = float("-inf")

        for line in fh:
            line = line.strip()
            if line.startswith("vertex"):
                parts = line.split()
                if len(parts) >= 4:
                    vx, vy, vz = float(parts[1]), float(parts[2]), float(parts[3])
                    cur_verts.append((vx, vy, vz))
                    if vx < xmin: xmin = vx
                    if vx > xmax: xmax = vx
                    if vy < ymin: ymin = vy
                    if vy > ymax: ymax = vy
                    if vz < zmin: zmin = vz
                    if vz > zmax: zmax = vz
                    if len(cur_verts) == 3:
                        triangles.append((cur_verts[0], cur_verts[1], cur_verts[2]))
                        cur_verts = []

    if not triangles:
        raise ValueError(f"No valid triangles found in {path}")
    return triangles, (xmin, ymin, zmin, xmax, ymax, zmax)


# ====================================================================== SLICER
def slice_mesh_at_z(triangles: List[Triangle], z0: float, tol: float = 0.05,
                    simplify_tol: float = 0.05) -> List[List[Point2D]]:
    """Compute cross-section rings of 3D triangle mesh at height z0."""
    segments = []

    for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in triangles:
        minz = min(az, bz, cz)
        maxz = max(az, bz, cz)
        if minz > z0 or maxz < z0:
            continue

        da = az - z0
        db = bz - z0
        dc = cz - z0
        # Nudge exact planar hits slightly to avoid topological ambiguity
        if da == 0.0: da = 1e-6
        if db == 0.0: db = 1e-6
        if dc == 0.0: dc = 1e-6

        sa, sb, sc = da > 0, db > 0, dc > 0
        if sa == sb == sc:
            continue

        pts = []
        if sa != sb:
            t = (z0 - az) / (bz - az)
            pts.append((ax + t * (bx - ax), ay + t * (by - ay)))
        if sb != sc:
            t = (z0 - bz) / (cz - bz)
            pts.append((bx + t * (cx - bx), by + t * (cy - by)))
        if sc != sa:
            t = (z0 - cz) / (az - cz)
            pts.append((cx + t * (ax - cx), cy + t * (ay - cy)))

        if len(pts) == 2:
            segments.append((pts[0], pts[1]))

    if not segments:
        return []

    # Stitch segments into closed loops with spatial hash
    cell_size = tol
    def cell(p):
        return (int(math.floor(p[0] / cell_size)), int(math.floor(p[1] / cell_size)))

    grid = defaultdict(list)
    for i, (p1, p2) in enumerate(segments):
        grid[cell(p1)].append((p1, i, True))
        grid[cell(p2)].append((p2, i, False))

    def find_nearest(p, exclude_set):
        cx, cy = cell(p)
        best_d = tol
        best_idx = None
        best_pt = None
        best_is_start = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for pt, s_idx, is_start in grid.get((cx + dx, cy + dy), []):
                    if s_idx in exclude_set:
                        continue
                    d = math.hypot(pt[0] - p[0], pt[1] - p[1])
                    if d < best_d:
                        best_d = d
                        best_pt = pt
                        best_idx = s_idx
                        best_is_start = is_start
        return best_idx, best_pt, best_is_start

    used = set()
    loops = []

    for i, (p1, p2) in enumerate(segments):
        if i in used:
            continue
        used.add(i)
        chain = [p1, p2]

        while True:
            cur = chain[-1]
            match_idx, match_pt, is_start = find_nearest(cur, used)
            if match_idx is None:
                break
            used.add(match_idx)
            sp1, sp2 = segments[match_idx]
            nxt = sp2 if is_start else sp1
            chain.append(nxt)
            if math.hypot(chain[0][0] - nxt[0], chain[0][1] - nxt[1]) < tol:
                break

        if math.hypot(chain[0][0] - chain[-1][0], chain[0][1] - chain[-1][1]) >= tol:
            while True:
                cur = chain[0]
                match_idx, match_pt, is_start = find_nearest(cur, used)
                if match_idx is None:
                    break
                used.add(match_idx)
                sp1, sp2 = segments[match_idx]
                prev_pt = sp1 if not is_start else sp2
                chain.insert(0, prev_pt)
                if math.hypot(chain[0][0] - chain[-1][0], chain[0][1] - chain[-1][1]) < tol:
                    break

        if len(chain) >= 3 and math.hypot(chain[0][0] - chain[-1][0], chain[0][1] - chain[-1][1]) < tol:
            loop = chain[:-1]
            if simplify_tol > 0:
                loop = geom.drop_collinear(loop, simplify_tol)
            if len(loop) >= 3:
                loops.append(loop)

    return loops


# ====================================================================== STL JOB
class STLJob:
    """Represents a 3D STL slicing and G-code generation job."""

    def __init__(self, par: Params, stl_path: str, scale: float = 0.0,
                 offset: Tuple[float, float] = (0.0, 0.0), place: Optional[Tuple[float, float]] = None,
                 fit_bed: bool = False, center_bed: bool = True):
        self.p = par
        self.stl_path = stl_path
        self.triangles, self.raw_bounds = read_stl(stl_path)
        self.scale_factor = scale if scale > 0 else 1.0
        self.offset = offset
        self.place = place
        self.fit_bed = fit_bed
        self.center_bed = center_bed

        # Ground the mesh so z_min = 0.0
        minx, miny, minz, maxx, maxy, maxz = self.raw_bounds
        z_shift = -minz
        s = self.scale_factor
        self.triangles = [
            (
                (t[0][0] * s, t[0][1] * s, (t[0][2] + z_shift) * s),
                (t[1][0] * s, t[1][1] * s, (t[1][2] + z_shift) * s),
                (t[2][0] * s, t[2][1] * s, (t[2][2] + z_shift) * s),
            )
            for t in self.triangles
        ]

        xs = [v[0] for t in self.triangles for v in t]
        ys = [v[1] for t in self.triangles for v in t]
        zs = [v[2] for t in self.triangles for v in t]
        self.bounds = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

        # Height
        mesh_h = self.bounds[5] - self.bounds[2]
        if par.let.dbHeightShell <= 0.0 or par.let.dbHeightShell == 50.0:  # default INI
            par.let.dbHeightShell = round(mesh_h, 2)
        self.height = par.let.dbHeightShell
        self.layer_h = par.let.dbHeightLayer or 0.3
        self.layer_n = max(1, int(math.ceil(self.height / self.layer_h)))

        # Cache of sliced layers
        self._layer_cache = {}

    def slice_at_z(self, z: float) -> List[List[Point2D]]:
        k = round(z, 3)
        if k not in self._layer_cache:
            self._layer_cache[k] = slice_mesh_at_z(self.triangles, z)
        return self._layer_cache[k]

    def prepare_placement(self, bed_w: float, bed_h: float):
        """Scale and place mesh onto the printer bed."""
        x0, y0, _, x1, y1, _ = self.bounds
        w = x1 - x0
        h = y1 - y0

        scale = 1.0
        if self.fit_bed and bed_w > 0 and bed_h > 0:
            margin = 15.0
            avail_w = bed_w - margin * 2
            avail_h = bed_h - margin * 2
            if w > avail_w or h > avail_h:
                scale = min(avail_w / max(w, 1.0), avail_h / max(h, 1.0))
                self.triangles = [
                    (
                        ((t[0][0] - x0) * scale, (t[0][1] - y0) * scale, t[0][2]),
                        ((t[1][0] - x0) * scale, (t[1][1] - y0) * scale, t[1][2]),
                        ((t[2][0] - x0) * scale, (t[2][1] - y0) * scale, t[2][2]),
                    )
                    for t in self.triangles
                ]
                self._layer_cache.clear()
                x0, y0 = 0.0, 0.0
                x1, y1 = w * scale, h * scale
                self.bounds = (x0, y0, self.bounds[2], x1, y1, self.bounds[5])
                w, h = x1 - x0, y1 - y0

        dx, dy = self.offset
        if self.place is not None:
            dx += self.place[0] - x0
            dy += self.place[1] - y0
        elif self.center_bed and bed_w > 0 and bed_h > 0:
            cx = (x0 + x1) / 2.0
            cy = (y0 + y1) / 2.0
            dx += (bed_w / 2.0) - cx
            dy += (bed_h / 2.0) - cy
        elif x0 < 10.0 or y0 < 10.0:
            # ensure positive coordinates
            if x0 < 10.0: dx += 10.0 - x0
            if y0 < 10.0: dy += 10.0 - y0

        if abs(dx) > 1e-4 or abs(dy) > 1e-4:
            self.triangles = [
                (
                    (t[0][0] + dx, t[0][1] + dy, t[0][2]),
                    (t[1][0] + dx, t[1][1] + dy, t[1][2]),
                    (t[2][0] + dx, t[2][1] + dy, t[2][2]),
                )
                for t in self.triangles
            ]
            self._layer_cache.clear()
            bx0, by0, bz0, bx1, by1, bz1 = self.bounds
            self.bounds = (bx0 + dx, by0 + dy, bz0, bx1 + dx, by1 + dy, bz1)

    # ---------------------------------------------------------------- RENDER ZCCAD
    def render_zccad(self, out_path: str, pre_side: bool = True, progress=None):
        """Render to Taesin / Iguana / ZCCAD printer dialect."""
        p = self.p
        bed_size = (800.0, 800.0)  # default Iguana machine bed
        self.prepare_placement(bed_size[0], bed_size[1])

        tools = sorted({p.tool_no(p.glue_no_for_layer(i)) for i in range(self.layer_n)})
        if not tools:
            tools = [0]
        first_tool = p.tool_no(p.glue_no_for_layer(0))

        # Pre-side ring from layer 0 bounds
        l0_rings = self.slice_at_z(p.layer_z(0))
        if not l0_rings and self.layer_n > 1:
            l0_rings = self.slice_at_z(p.layer_z(1))

        with open(out_path, "w", encoding="ascii", newline="\n") as fh:
            w = GCodeWriter(p, fh)
            w.write_head(tools)
            w.write_initial_switch(first_tool)

            if pre_side and l0_rings:
                # Use outer bbox to make clean pre-side frame
                bx0, by0, bx1, by1 = geom.bbox(l0_rings)
                pad = 12.0
                frame = [(bx0 - pad, by0 - pad), (bx1 + pad, by0 - pad),
                         (bx1 + pad, by1 + pad), (bx0 - pad, by1 + pad)]
                w.write_pre_side([frame], p.layer_z(0))

            pos = (w.pos[0], w.pos[1])
            cur_tool = first_tool
            cur_glue = p.glue_no_for_layer(0)
            block_first = True

            for li in range(self.layer_n):
                z = p.layer_z(li)
                glue = p.glue_no_for_layer(li)
                if glue != cur_glue:
                    w.write_color_switch(p.tool_no(glue), z)
                    cur_tool = p.tool_no(glue)
                    cur_glue = glue
                    block_first = True

                rings = self.slice_at_z(z)
                ordered_rings = []
                pool = list(rings)
                cur_pt = pos
                while pool:
                    best_i = 0
                    best_d = float("inf")
                    for i, r in enumerate(pool):
                        d = (r[0][0] - cur_pt[0]) ** 2 + (r[0][1] - cur_pt[1]) ** 2
                        if d < best_d:
                            best_d = d
                            best_i = i
                    r = pool.pop(best_i)
                    ordered_rings.append(r)
                    cur_pt = r[0]

                for ri, ring in enumerate(ordered_rings):
                    first = block_first and ri == 0
                    w.contour(ring, z, is_block_first=first)
                    w.contour_end(z)
                    pos = ring[0]
                    if first:
                        block_first = False

                if progress:
                    progress(li + 1, self.layer_n)

            w.write_tail(pos, p.layer_z(self.layer_n - 1))

    # ------------------------------------------------------------ RENDER UNIVERSAL
    def render_universal(self, profile: MachineProfile, out_path: str,
                         opts: UniversalOpts, progress=None):
        """Render to standard Marlin / Bambu Lab dialect."""
        p = self.p
        self.prepare_placement(profile.bed_x, profile.bed_y)

        # Check bounds
        bx0, by0, _, bx1, by1, _ = self.bounds
        if bx0 < 0 or by0 < 0 or bx1 > profile.bed_x or by1 > profile.bed_y:
            raise ValueError(
                f"STL part ({bx1 - bx0:.1f}x{by1 - by0:.1f} mm) does not fit {profile.name} "
                f"bed ({profile.bed_x}x{profile.bed_y} mm). Use --fit-bed to scale down."
            )

        with open(out_path, "w", encoding="ascii", newline="\n") as fh:
            w = UniversalWriter(profile, p, fh, opts)
            w.write_head()

            # Skirt on layer 0
            l0_rings = self.slice_at_z(p.layer_z(0))
            if not l0_rings and self.layer_n > 1:
                l0_rings = self.slice_at_z(p.layer_z(1))

            if opts.skirt_lines > 0 and l0_rings:
                bx0, by0, bx1, by1 = geom.bbox(l0_rings)
                gap = opts.skirt_gap
                for sk_i in range(opts.skirt_lines):
                    pad = gap + sk_i * w.width
                    sk_ring = [(bx0 - pad, by0 - pad), (bx1 + pad, by0 - pad),
                               (bx1 + pad, by1 + pad), (bx0 - pad, by1 + pad)]
                    w.open_path(sk_ring, p.layer_z(0), w.pro.first_layer_speed, typ="SKIRT")

            plan_tools = sorted({p.tool_no(p.glue_no_for_layer(i)) for i in range(self.layer_n)})
            first_tool = p.tool_no(p.glue_no_for_layer(0))
            pos = (0.0, 0.0)

            for li in range(self.layer_n):
                z = p.layer_z(li)
                tool = first_tool
                if len(plan_tools) > 1 and opts.multitool:
                    tool = p.tool_no(p.glue_no_for_layer(li))

                w.layer_start(li, z, tool)
                solid = (li < opts.solid_bottom) or (li >= self.layer_n - opts.solid_top)

                rings = self.slice_at_z(z)
                ordered_rings = []
                pool = list(rings)
                cur_pt = pos
                while pool:
                    best_i = 0
                    best_d = float("inf")
                    for i, r in enumerate(pool):
                        d = (r[0][0] - cur_pt[0]) ** 2 + (r[0][1] - cur_pt[1]) ** 2
                        if d < best_d:
                            best_d = d
                            best_i = i
                    r = pool.pop(best_i)
                    ordered_rings.append(r)
                    cur_pt = r[0]

                for ri, ring in enumerate(ordered_rings):
                    speed = w.pro.first_layer_speed if li == 0 else w.pro.work_speed
                    base = "WALL-OUTER" if ri == 0 else "WALL-INNER"
                    w.open_path(ring, z, speed, typ=("SOLID-" + base) if solid else base)
                    pos = ring[0]

                # Infill if solid or infill requested
                infill_wanted = (opts.infill_density > 0 or solid) and len(rings) >= 1
                if infill_wanted:
                    spacing = w.infill_spacing(solid)
                    if spacing > 0:
                        ang = 0.0 if li % 2 == 0 else 90.0 if solid else (45.0 if li % 2 == 0 else 135.0)
                        lines = hatch(rings, spacing, ang)
                        speed = w.pro.first_layer_speed if li == 0 else w.pro.work_speed
                        typ = "SOLID-INFILL" if solid else "INFILL"
                        for line in lines:
                            w.open_path(line, z, speed, typ=typ, closed=False)
                        if lines:
                            pos = lines[-1][-1]

                if progress:
                    progress(li + 1, self.layer_n)

            w.write_tail(p.layer_z(self.layer_n - 1))

        return {
            "len_by_tool": {t: round(l / 1000.0, 3) for t, l in w.len_by_tool.items()},
            "e_by_tool": {t: round(e / 1000.0, 3) for t, e in w.e_by_tool.items()},
            "est_time_min": round(w.time_s / 60.0, 1),
        }
