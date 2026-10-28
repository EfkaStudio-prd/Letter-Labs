"""G-code writer reproducing the ZCCAD / OutPutG.dll output dialect.

Every template in this file was transcribed from S528\\temp.gcode and confirmed
against the IL of OutPutG.writeGcodeHead / writeGcodeTear / writeGcode_G00 /
thichnessProcess / calculatePreSide.  Number formatting matches .NET
Double.ToString(): 15 significant digits, shortest form.
"""
from __future__ import annotations

import math

from . import geom
from .params import Params

#: The vendor adds a fixed 0.1 mm of filament right after every recover move
#: (`G1 F.. Z.. E{acc + 0.1}` in thichnessProcess).  It is part of the running
#: absolute extrusion counter, so it must be written back.
PRIME_EPS = 0.1


def g(v) -> str:
    """Format a double exactly like .NET double.ToString() with InvariantCulture."""
    if v == int(v) and abs(v) < 1e15:
        # .NET prints 0 as "0", 5 as "5", 0.3 as "0.3"
        pass
    s = "%.15g" % float(v)
    if s == "-0":
        return "0"
    return s


def zg(v) -> str:
    """Z values in the vendor file always show up fully trimmed (0.3, 2.7, 5.4)."""
    return g(round(float(v), 6))


class GCodeWriter:
    """Streams the vendor-compatible G-code for one job."""

    def __init__(self, par: Params, out):
        self.p = par
        self.out = out
        self.acc = {}            # per-tool absolute extrusion counter (dbGlueLen)
        self.pos = (0.0, 0.0)
        self.z = 0.0
        self.tool = None
        self._need_start_marker = True
        self._lines = 0

    # ------------------------------------------------------------------ output
    def w(self, line=""):
        self.out.write(line + "\n")
        self._lines += 1

    # --------------------------------------------------------------- properties
    @property
    def idle(self):
        return self.p.pri.iSpeedIdle

    @property
    def glue_back(self):
        return self.p.pri.iSpeedGlueBack

    @property
    def work_speed(self):
        return self.p.pri.iSpeedWork

    @property
    def first_layer_speed(self):
        return self.p.pri.iSpeedFirstLayer

    def lift(self, h):
        return h + self.p.pri.dbHeightIdle

    def e_for(self, length):
        return length * self.p.e_per_mm

    def tool_for_glue(self, glue_no):
        n = self.p.extruder_count
        return max(0, n - int(glue_no))

    # ------------------------------------------------------------------- header
    def write_head(self, tools):
        pr = self.p
        self.w(";This G_Code provided by DongGuan ZhenCai Lmt")
        self.w(";G code start")
        for t in tools:
            temp = pr.pri.iT1 if t else pr.pri.iT0
            self.w(f"M104 S{temp} T{t}")
            self.w(f"M109 S{temp} T{t}")
        self.w("G21")
        self.w("G90")
        self.w("G82")
        self.w("G28")
        self.w("G1 Z15 F1500")
        self.w("G92 E0")
        if len(tools) >= 2:
            # purge dance captured verbatim from temp.gcode: T0 -> T1 -> T1 -> T0
            back = g(pr.glu.dbDisColorBack)
            a, b = tools[0], tools[-1]
            self.w(f"T{a}")
            self.w(f"G1 E-{back} F{pr.glu.iSpeedColorSwitch}")
            self.w("G92 E0")
            self.w(f"T{b}")
            self.w(f"G1 E{back} F750")
            self.w("G92 E0")
            self.w(f"T{b}")
            self.w(f"G1 E-{back} F{pr.glu.iSpeedColorSwitch}")
            self.w("G92 E0")
            self.w(f"T{a}")
            self.w(f"G1 E{back} F750")
            self.w("G92 E0")
            self.w(f"T{a}")
        else:
            self.w(f"T{tools[0]}")
            self.w("G92 E0")
        self.w("M117 Printing...")
        self.w("M106 S255")

    # ------------------------------------------------------- initial positioning
    def write_initial_switch(self, first_tool):
        pr = self.p
        idle = self.idle
        self.w(";extruder switch")
        self.w("G92 E0")
        self.w("G91")
        self.w(f"G0 X5 Y5 F{idle}")
        self.w(f"G0 F{idle} Z0")
        self.w("G90")
        self.w(f"G1 F{pr.glu.iSpeedColorSwitch} E-{g(pr.glu.dbDisColorBack / 2)}")
        # The vendor always parks T0 at its print temperature here because in the
        # two-colour jobs it is needed a few layers later.  In a single-colour job
        # T0 never runs, so holding it at 220 C only makes it drool - leave it cold.
        active = {self.tool_for_glue(glue) for glue in pr.band_plan()} or {0}
        self.w(f"M104 S{pr.pri.iT0 if 0 in active else 0} T0")
        self.w(f"T{first_tool}")
        self.w("G92 E0")
        self.w("G90")
        self.tool = first_tool
        self.acc.setdefault(first_tool, 0.0)

    # --------------------------------------------------------------- pre-side
    def write_pre_side(self, rings, h):
        """First-layer safety line around the letter.

        `rings` are closed offset outlines, outermost first.  The vendor prints
        them as ONE continuous flow: pass 0 primes with dbDisClear millimetres
        from a point dbDisGlueBack away, later passes only travel (no retract,
        no prime) and the single retract happens after the last pass.
        """
        pr = self.p
        if not rings:
            return
        idle = self.idle
        fl = self.first_layer_speed
        self.w(";calculatePreSide start")
        for k, ring in enumerate(rings):
            ring = list(ring)
            if geom.dist(ring[0], ring[-1]) > 1e-9:
                ring.append(ring[0])
            x0, y0 = ring[0]
            self.w(";start printf")
            if k == 0:
                d = pr.glu.dbDisGlueBack
                self.w(f"G0 F{idle // 2} X{g(x0)} Y{g(y0)}")
                self.w(f"G0 F{idle} Z{zg(h + 0.1)}")
                self.w(f"G0 F{idle} X{g(x0)} Y{g(y0)}")
                self.w(f"G0 F{idle} Z{zg(h)}")
                self.w(f"G0 F{idle} X{g(x0 - d)} Y{g(y0 - d)} "
                       f"Z{zg(h + 2 * pr.pri.dbHeightIdle)}")
                acc = self.acc.get(self.tool, 0.0) + pr.pri.dbDisClear
                self.acc[self.tool] = acc
                self.w(f"G1 F{fl} E{g(acc)}")
                self.w(f"G1 F{fl} Z{zg(h)}")
                self.w(f"G1 F{fl} X{g(x0)} Y{g(y0)}")
                self._extrude_open(ring, lead=False)
            else:
                self.w(f"G0 F{idle} X{g(x0)} Y{g(y0)}")
                self.w(f"G0 F{idle} Z{zg(h + 0.1)}")
                self.w(f"G0 F{idle} X{g(x0)} Y{g(y0)}")
                self.w(f"G0 F{idle} Z{zg(h)}")
                self.w(f"G1 F{fl} X{g(x0)} Y{g(y0)}")
                self._extrude_open(ring, lead=False)
        acc = self.acc.get(self.tool, 0.0) - pr.glu.dbDisGlueBack
        self.w(f"G1 F{fl} E{g(acc)}")
        self.w(f"G0 F{idle} Z{zg(h)}")
        self.w(f"G0 F{idle} Z{zg(h + 0.1)}")
        self.w(";calculatePreSide end")
        self._need_start_marker = True

    # ------------------------------------------------------------ colour switch
    def write_color_switch(self, new_tool, h):
        pr = self.p
        idle = self.idle
        prev = self.tool
        acc_prev = self.acc.get(prev, 0.0)
        self.w(";extruder switch")
        self.w("G92 E0")
        self.w("G91")
        self.w(f"G1 F{pr.glu.iSpeedColorSwitch} E-{g(pr.glu.dbDisColorBack)}")
        temp = pr.pri.iT0 if new_tool == 0 else pr.pri.iT1
        self.w(f"M104 S{temp} T0")
        self.w(f"T{new_tool}")
        self.w("G92 E0")
        self.w("G90")
        self.w(f"G1 F{self.work_speed} E{g(pr.glu.dbDisColorBack)}")
        acc = pr.glu.dbDisColorBack + pr.glu.dbCompensateColor
        self.acc[new_tool] = acc
        self.w(f"G1 F{self.work_speed} E{g(acc)}")
        self.tool = new_tool
        self._need_start_marker = True
        # keep the previous accumulator intact for when we switch back
        self.acc[prev] = acc_prev

    # ----------------------------------------------------------------- contours
    def begin_block(self):
        self._need_start_marker = True

    def contour(self, pts, h, is_block_first=False, speed=None):
        """Emit one closed contour at height h."""
        pts = geom.dedupe(pts)
        if len(pts) < 3:
            return
        # drop the duplicate closing vertex; the vendor's rings are open lists
        if geom.dist(pts[0], pts[-1]) < 1e-6:
            pts = pts[:-1]
        if len(pts) < 3:
            return
        x0, y0 = pts[0]
        idle = self.idle
        lift = self.lift(h)
        # The vendor feeds each block's first contour with iSpeedFirstLayer and
        # every later contour with iSpeedWork (arr.gcode: F1800 then F3600).
        # Using the first-layer speed everywhere halves the wall speed.
        s = speed if speed is not None else (
            self.first_layer_speed if is_block_first else self.work_speed)

        if self._need_start_marker:
            self.w(";start printf")
            self._need_start_marker = False

        if is_block_first:
            self.w(f"G0 F{idle} X{g(x0)} Y{g(y0)}")
            self.w(f"G0 F{idle} Z{zg(lift)}")
            self.w(f"G0 F{idle} X{g(x0)} Y{g(y0)}")
            self.w(f"G0 F{idle} Z{zg(h)}")
            acc = self.acc.get(self.tool, 0.0) + PRIME_EPS
            self.acc[self.tool] = acc
            self.w(f"G1 F{s} E{g(acc)}")
            self.w(f"G1 F{s} X{g(x0)} Y{g(y0)}")
        else:
            self.w(f"G0 F{idle} Z{zg(lift)}")
            self.w(f"G0 F{idle} X{g(x0)} Y{g(y0)}")
            self.w(f"G0 F{idle} X{g(x0)} Y{g(y0)} Z{zg(h)}")
            self.w(f"G0 F{idle} X{g(x0)} Y{g(y0)}")
            acc = self.acc.get(self.tool, 0.0)
            self.w(f"G1 F{self.glue_back} X{g(x0)} Y{g(y0)} E{g(acc)}")
            acc += PRIME_EPS
            self.acc[self.tool] = acc
            self.w(f"G1 F{self.glue_back} Z{zg(h)} E{g(acc)}")
            self.w(f"G1 F{s} X{g(x0)} Y{g(y0)}")

        self.pos = (x0, y0)
        self.z = h
        self._extrude_closed(pts)

    def _extrude_closed(self, pts):
        acc = self.acc.get(self.tool, 0.0)
        e = e_per = self.p.e_per_mm
        prev = pts[0]
        for cur in pts[1:]:
            d = geom.dist(prev, cur)
            if d < 1e-9:
                continue
            acc += d * e_per
            self.w(f"G1 X{g(cur[0])} Y{g(cur[1])} E{g(acc)}")
            prev = cur
        d = geom.dist(prev, pts[0])
        if d > 1e-9:
            acc += d * e_per
            self.w(f"G1 X{g(pts[0][0])} Y{g(pts[0][1])} E{g(acc)}")
        self.acc[self.tool] = acc
        self.pos = pts[0]

    def _extrude_open(self, pts, speed=None, lead=True):
        acc = self.acc.get(self.tool, 0.0)
        e_per = self.p.e_per_mm
        sp = speed or self.first_layer_speed
        if lead:
            self.w(f"G1 F{sp} X{g(pts[0][0])} Y{g(pts[0][1])}")
        prev = pts[0]
        for cur in pts[1:]:
            d = geom.dist(prev, cur)
            if d < 1e-9:
                continue
            acc += d * e_per
            self.w(f"G1 X{g(cur[0])} Y{g(cur[1])} E{g(acc)}")
            prev = cur
        self.acc[self.tool] = acc
        self.pos = pts[-1]

    def contour_end(self, h):
        """Retract + lift after a contour (matches the vendor epilogue)."""
        acc = self.acc.get(self.tool, 0.0) - self.p.glu.dbDisGlueBack
        self.w(f"G1 F{self.glue_back} E{g(acc)}")
        self.w(f"G0 F{self.idle} Z{zg(self.lift(h))}")

    def first_layer_fill(self, rings, h, spacing=0.8, angle=45.0):
        """Optional solid hatch on the first layer for bed adhesion."""
        for ring in rings:
            for stroke in geom.zigzag_fill(ring, spacing, angle):
                if len(stroke) < 2:
                    continue
                self.w(f"G0 F{self.idle} Z{zg(self.lift(h))}")
                self.w(f"G0 F{self.idle} X{g(stroke[0][0])} Y{g(stroke[0][1])}")
                self.w(f"G0 F{self.idle} X{g(stroke[0][0])} Y{g(stroke[0][1])} Z{zg(h)}")
                acc = self.acc.get(self.tool, 0.0)
                self.w(f"G1 F{self.glue_back} X{g(stroke[0][0])} Y{g(stroke[0][1])} E{g(acc)}")
                acc += PRIME_EPS
                self.acc[self.tool] = acc
                self.w(f"G1 F{self.glue_back} Z{zg(h)} E{g(acc)}")
                self.w(f"G1 F{self.work_speed} X{g(stroke[0][0])} Y{g(stroke[0][1])}")
                self._extrude_open(stroke, speed=self.work_speed)
                self.w(f"G1 F{self.glue_back} E{g(self.acc[self.tool] - self.p.glu.dbDisGlueBack)}")
                self.w(f"G0 F{self.idle} Z{zg(self.lift(h))}")

    # -------------------------------------------------------------------- footer
    def write_tail(self, last_xy, h):
        pr = self.p
        idle = self.idle
        acc = self.acc.get(self.tool, 0.0) - pr.glu.dbDisGlueBack
        self.w(f"G1 F{self.glue_back} E{g(acc)}")
        self.w(f"G0 F{idle} Z{zg(self.lift(h))}")
        self.w(f"G0 F{idle} Z{zg(self.lift(h))}")
        self.w(f"G0 F{idle} X{g(last_xy[0])} Y{g(last_xy[1])}")
        self.w(f"G0 F{idle} X{g(last_xy[0])} Y{g(last_xy[1])} Z{zg(self.lift(h))}")
        self.w(";G code end")
        self.w("G91")
        self.w(f"G0 X5 Y5 F{idle}")
        end_pos = pr.pri.dbEndPosGluePoint
        if end_pos < pr.let.dbHeightShell:
            self.w(f"G0 F{idle} Z{zg(end_pos)}")
        self.w("G90")
        self.w(f"G0 X750 Y750 F{idle}")
        self.w("G92 E0")
        self.w("G91")
        self.w(f"G1 F{pr.glu.iSpeedColorSwitch} E-{g(pr.glu.dbDisColorBack)}")
        self.w("M84")
        self.w("G90")
        self.w("M107")
        for t in sorted({self.tool, 0, 1}):
            temp = pr.pri.iT0 if t == 0 else pr.pri.iT1
            self.w(f"M104 S30 T{t}")
        self.w("M106 S0")
        self.w(";End of Gcode")


def _rect_ring(x0, y0, x1, y1, step=1.0):
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    out = []
    for i in range(4):
        a = corners[i]
        b = corners[(i + 1) % 4]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(math.ceil(d / step)))
        for k in range(n):
            t = k / n
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out
