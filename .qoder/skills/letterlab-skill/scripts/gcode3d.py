"""G-code -> 3D bead simulator + PNG renderer. Pure stdlib, no numpy/matplotlib.

Re-parses an emitted toolpath (it does NOT trust the generator's internal model),
rebuilds every extruding move as a bead of molten filament, and rasterises the
result into an isometric view, a top view and a front view, one PNG panel each.

This is the "Verify" step of an Aspire-style workflow: if the picture is wrong,
the print is wrong, and the numbers below the picture say how long it will take.

usage:
  python gcode3d.py FILE.gcode [--out preview.png] [--width 1.2]
                              [--yaw 45] [--elev 24] [--scale auto]
                              [--tools 0,1] [--stats] [--max-seg 1500000]

Colour is per extruder (T number), brightness is per Z, so a wrong colour band
or a layer that should not be there is visible immediately.
"""
from __future__ import annotations

import math
import re
import struct
import sys
import zlib

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
RX = re.compile(r"([XYZEFTG])\s*(" + NUM + ")")

#: per-extruder base colours (R, G, B) - matches the app's own filament swatches
TOOL_COLORS = [
    (232, 74, 60),    # T0  red
    (48, 118, 214),   # T1  blue
    (46, 174, 96),    # T2  green
    (238, 178, 36),   # T3  amber
    (156, 92, 200),   # T4  violet
    (230, 230, 230),  # T5  white
]


# --------------------------------------------------------------------- parsing
class Toolpath:
    """Extruding segments recovered from raw G-code.

    Modal state is honoured: G90/G91 switches XYZ *and* E between absolute and
    relative (the vendor retracts with `G91` + `G1 E-85`, then restores `G90`),
    and G92 E0 rebases the absolute counter, so E deltas are only meaningful
    against the value carried since the last rebase.
    """

    def __init__(self, path, max_seg=1500000, bead_width=1.2):
        self.seg = []            # (x0,y0,z0,x1,y1,z1,tool)
        self.bead_width = bead_width
        self.tools = set()
        self.len_by_tool = {}
        self.e_by_tool = {}     # filament actually committed, summed from E
        self.time_by_tool = {}   # seconds, from the F word on each move
        self.zs = set()
        self.bounds = None       # (xmin,ymin,zmin,xmax,ymax,zmax)
        self.moves = 0
        self.truncated = False
        self._x = self._y = self._z = 0.0
        self._e = 0.0            # absolute E counter since last G92
        self._tool = 0
        self._rel = False
        self._f = 0.0            # modal feedrate, mm/min
        self._trunc = max_seg
        self._parse(path)
        self._bounds()

    # -- helpers ------------------------------------------------------------
    def _feed(self):
        """Current modal feedrate in mm/min. F is modal: the vendor emits `G1 X.. Y..
        E..` with no F word for every vertex after the first, so timing those moves
        at a default rather than the inherited value roughly doubles the estimate."""
        return self._f if self._f and self._f > 0 else 1800.0

    def _push(self, nx, ny, nz, d, f, de):
        if d <= 1e-9:
            return
        if len(self.seg) >= self._trunc:
            self.truncated = True
            return
        t = self._tool
        self.seg.append((self._x, self._y, self._z, nx, ny, nz, t))
        self.len_by_tool[t] = self.len_by_tool.get(t, 0.0) + d
        self.e_by_tool[t] = self.e_by_tool.get(t, 0.0) + de
        self.time_by_tool[t] = self.time_by_tool.get(t, 0.0) + d / self._feed() * 60.0
        self.zs.add(round(nz, 4))

    def _parse(self, path):
        with open(path, "r", encoding="ascii", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line[0] == ";":
                    continue
                if line.startswith("M82"):
                    self._rel = False
                    continue
                if line.startswith("M83"):
                    self._rel = True
                    continue
                m = re.match(r"^T(\d+)$", line)
                if m:
                    self._tool = int(m.group(1))
                    self.tools.add(self._tool)
                    continue
                if line.startswith("G92"):
                    v = dict((k, float(x)) for k, x in RX.findall(line))
                    if "E" in v:
                        self._e = v["E"]
                    continue
                if not (line.startswith("G0") or line.startswith("G1")
                        or line.startswith("G00") or line.startswith("G01")):
                    if line.startswith("G90"):
                        self._rel = False
                    elif line.startswith("G91"):
                        self._rel = True
                    continue
                self.tools.add(self._tool)
                v = dict((k, float(x)) for k, x in RX.findall(line))
                f = v.get("F", 0.0)
                if f > 0:
                    self._f = f          # F is modal, it persists to later lines
                nx = self._x + v["X"] if self._rel and "X" in v else v.get("X", self._x)
                ny = self._y + v["Y"] if self._rel and "Y" in v else v.get("Y", self._y)
                nz = self._z + v["Z"] if self._rel and "Z" in v else v.get("Z", self._z)
                de = 0.0
                if "E" in v:
                    if self._rel:
                        de = v["E"]
                        # absolute counter keeps running through relative moves
                        self._e += v["E"]
                    else:
                        de = v["E"] - self._e
                        self._e = v["E"]
                d2d = math.hypot(nx - self._x, ny - self._y)
                dz = nz - self._z
                d3 = math.sqrt(d2d * d2d + dz * dz)
                self.moves += 1
                if de > 1e-9 and d3 > 1e-9:
                    self._push(nx, ny, nz, d3, f, de)
                self._x, self._y, self._z = nx, ny, nz

    def _bounds(self):
        if not self.seg:
            return
        mn = [float("inf")] * 3
        mx = [float("-inf")] * 3
        for s in self.seg:
            for i, (a, b) in enumerate(((s[0], s[3]), (s[1], s[4]), (s[2], s[5]))):
                mn[i] = min(mn[i], a, b)
                mx[i] = max(mx[i], a, b)
        self.bounds = (mn[0], mn[1], mn[2], mx[0], mx[1], mx[2])

    # -- public -------------------------------------------------------------
    @property
    def total_len(self):
        return sum(self.len_by_tool.values())

    @property
    def total_e(self):
        return sum(self.e_by_tool.values())

    @property
    def total_time(self):
        return sum(self.time_by_tool.values())

    def stats(self):
        b = self.bounds or (0, 0, 0, 0, 0, 0)
        return {
            "segments": len(self.seg),
            "moves": self.moves,
            "layers": len(self.zs),
            "size_mm": (round(b[3] - b[0], 2), round(b[4] - b[1], 2), round(b[5] - b[2], 2)),
            "tools": sorted(self.tools),
            "length_by_tool_mm": {k: round(v, 1) for k, v in sorted(self.len_by_tool.items())},
            "time_by_tool_min": {k: round(v / 60.0, 2) for k, v in sorted(self.time_by_tool.items())},
            "est_print_time_min": round(self.total_time / 60.0, 1),
            # toolpath length and consumed filament are different numbers; the
            # first is path mm, the second is what the extruder actually feeds
            "toolpath_total_m": round(self.total_len / 1000.0, 3),
            "filament_by_tool_m": {k: round(v / 1000.0, 2)
                                   for k, v in sorted(self.e_by_tool.items())},
            "filament_total_m": round(self.total_e / 1000.0, 3),
        }


# ------------------------------------------------------------------ rasteriser
class Image:
    """RGB24 framebuffer with convex-quad fill and 2x supersampling."""

    def __init__(self, w, h, bg=(24, 26, 30), ss=2):
        self.w, self.h, self.ss = w, h, ss
        self.bw, self.bh = w * ss, h * ss
        self.buf = bytearray(self.bw * self.bh * 3)
        self.clear(bg)

    def clear(self, bg):
        row = bytes(bg) * self.bw
        blank = row * self.bh
        self.buf[:] = blank

    def quad(self, pts, color):
        """Scanline-fill a convex polygon given as 4 (x, y) screen-space points."""
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(self.bh - 1, int(max(ys)))
        if y1 < y0 or len(pts) < 3:
            return
        n = len(pts)
        buf = self.buf
        bw = self.bw
        r, g, b = color
        pr = bytes((r, g, b))
        for py in range(y0, y1 + 1):
            cy = py + 0.5
            inter = []
            for i in range(n):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % n]
                if ay == by:
                    continue
                if (ay <= cy < by) or (by <= cy < ay):
                    inter.append(ax + (cy - ay) * (bx - ax) / (by - ay))
            if len(inter) < 2:
                continue
            inter.sort()
            for k in range(0, len(inter) - 1, 2):
                sx = max(0, int(inter[k] + 0.5))
                ex = min(bw - 1, int(inter[k + 1]))
                if ex < sx:
                    continue
                off = (py * bw + sx) * 3
                buf[off:off + (ex - sx + 1) * 3] = pr * (ex - sx + 1)

    def downsample(self):
        """Box filter 2x2 -> 1x for smooth bead edges."""
        ss, bw, bh = self.ss, self.bw, self.bh
        out = bytearray(self.w * self.h * 3)
        f = float(ss * ss)
        buf = self.buf
        for y in range(self.h):
            for x in range(self.w):
                i = (y * ss * bw + x * ss) * 3
                r = g = b = 0
                for dy in range(ss):
                    o = i + dy * bw * 3
                    for dx in range(ss * 3):
                        v = buf[o + dx]
                        c = dx % 3
                        if c == 0:
                            r += v
                        elif c == 1:
                            g += v
                        else:
                            b += v
                j = (y * self.w + x) * 3
                out[j] = min(255, int(r / f))
                out[j + 1] = min(255, int(g / f))
                out[j + 2] = min(255, int(b / f))
        return bytes(out)


def write_png(path, w, h, rgb):
    """Minimal RGB24 PNG writer (stdlib zlib only)."""
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)                      # filter type 0 per scanline
        raw += rgb[y * stride:(y + 1) * stride]
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


# ------------------------------------------------------------------- projector
class Projector:
    """Orthographic camera. `elev` is how far ABOVE the part the camera sits.

    The rotation puts the camera on the +depth side, so a positive world-space
    pitch would look up at the underside; `elev` is negated here so that a
    positive angle gives the usual 'seen from above and in front' picture.
    """

    def __init__(self, bounds, w, h, yaw=45.0, elev=24.0, margin=0.08):
        self.a = math.radians(yaw)
        self.p = math.radians(-elev)
        self.w, self.h = w, h
        xa, ya, za, xb, yb, zb = bounds
        cx, cy, cz = (xa + xb) / 2, (ya + yb) / 2, (za + zb) / 2
        self.c = (cx, cy, cz)
        # project all 8 extents corners to find the screen footprint
        us = []
        vs = []
        for x in (xa, xb):
            for y in (ya, yb):
                for z in (za, zb):
                    u, v, _ = self._raw(x - cx, y - cy, z - cz)
                    us.append(u)
                    vs.append(v)
        span_u = (max(us) - min(us)) or 1.0
        span_v = (max(vs) - min(vs)) or 1.0
        self.s = min(w * (1 - 2 * margin) / span_u, h * (1 - 2 * margin) / span_v)
        self.ou = w / 2.0
        self.ov = h / 2.0

    def _raw(self, x, y, z):
        ca, sa = math.cos(self.a), math.sin(self.a)
        cp, sp = math.cos(self.p), math.sin(self.p)
        u = x * ca - y * sa
        v = x * sa + y * ca
        sy = z * cp - v * sp
        depth = v * cp + z * sp
        return u, sy, depth

    def to(self, x, y, z):
        u, sy, depth = self._raw(x - self.c[0], y - self.c[1], z - self.c[2])
        return self.ou + u * self.s, self.ov - sy * self.s, depth


def shade(base, k):
    return tuple(max(0, min(255, int(c * k))) for c in base)


def draw_panel(img, proj, tp, zmin, zmax, width_px, only=None):
    """Painter's algorithm: the camera looks along +depth, so far (large depth)
    beads are laid first and the beads nearest the camera cover them."""
    order = []
    for i, s in enumerate(tp.seg):
        t = s[6]
        if only is not None and t not in only:
            continue
        _, _, depth = proj.to((s[0] + s[3]) / 2, (s[1] + s[4]) / 2, (s[2] + s[5]) / 2)
        order.append((depth, i))
    order.sort(reverse=True)
    rng = (zmax - zmin) or 1.0
    for depth, i in order:
        s = tp.seg[i]
        x0, y0, z0, x1, y1, z1, tool = s[0], s[1], s[2], s[3], s[4], s[5], s[6]
        a = proj.to(x0, y0, z0)
        b = proj.to(x1, y1, z1)
        base = TOOL_COLORS[tool % len(TOOL_COLORS)]
        k = 0.58 + 0.52 * ((z0 - zmin) / rng)
        if depth > 0:
            k *= 0.94
        col = shade(base, k)
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            img.quad(disc(a[0], a[1], width_px), col)
            continue
        nx, ny = -dy / L, dx / L
        hw = width_px / 2.0 * img.ss
        pts = [(a[0] + nx * hw, a[1] + ny * hw),
               (b[0] + nx * hw, b[1] + ny * hw),
               (b[0] - nx * hw, b[1] - ny * hw),
               (a[0] - nx * hw, a[1] - ny * hw)]
        img.quad(pts, col)


def disc(cx, cy, r, n=8):
    return [(cx + r * math.cos(2 * math.pi * i / n),
             cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def blit(img, x, y, glyph, color):
    ss = img.ss
    for gy, bits in enumerate(glyph):
        for gx in range(5):
            if bits & (1 << (4 - gx)):
                x0 = (x + gx) * ss
                y0 = (y + gy) * ss
                img.quad([(x0, y0), (x0 + ss, y0), (x0 + ss, y0 + ss), (x0, y0 + ss)], color)


# 5x7 font, rows top to bottom; anything unlisted renders as a gap
_FONT_DATA = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "H": ("10001", "10001", "10001", "01110", "10001", "10001", "10001"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "N": ("10001", "11001", "11001", "10101", "10011", "10011", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("00010", "00100", "00010", "00010", "00010", "00100", "00010"),
    "=": ("00000", "11111", "00000", "00000", "11111", "00000", "00000"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "M": ("10001", "11011", "10101", "10001", "10001", "10001", "10001"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "G1": ("0",),
}


def _init_font():
    FONT = {}
    for ch, rows in _FONT_DATA.items():
        if len(rows) != 7:
            continue
        glyph = []
        for r in rows:
            v = 0
            for i, c in enumerate(r):
                if c == "1":
                    v |= 1 << (4 - i)
            glyph.append(v)
        FONT[ch] = glyph
    return FONT


FONT = _init_font()


def arg(argv, name, default=None):
    if name in argv:
        return argv[argv.index(name) + 1]
    return default


def main(argv):
    if not argv or "--help" in argv or argv[0] in ("-h",):
        print(__doc__)
        return 0
    src = argv[0]
    out = arg(argv, "--out", re.sub(r"\.gcode$", "", src, flags=re.I) + "_3d.png")
    width = float(arg(argv, "--width", "1.2"))
    yaw = float(arg(argv, "--yaw", "45"))
    elev = float(arg(argv, "--elev", "24"))
    only = None
    if arg(argv, "--tools"):
        only = {int(t) for t in arg(argv, "--tools").split(",")}
    max_seg = int(arg(argv, "--max-seg", "1500000"))

    tp = Toolpath(src, max_seg=max_seg, bead_width=width)
    if not tp.seg:
        print("no extruding segments found - is this a ZCCAD/letter export?")
        return 2
    st = tp.stats()
    for k, v in st.items():
        print(f"  {k:20s}: {v}")
    if "--stats" in argv:
        return 0

    W, H = 1360, 470
    gap = 10
    pw = (W - 2 * gap) // 3
    img = Image(W, H, bg=(24, 26, 30), ss=2)
    b = tp.bounds
    zmin, zmax = b[2], b[5]
    views = [("ISO", yaw, elev), ("TOP", 0.0, 89.0), ("FRONT", 0.0, 0.0)]
    for i, (label, ya_, el_) in enumerate(views):
        ox = i * (pw + gap)
        proj = Projector(b, pw, H - 60, yaw=ya_, elev=el_, margin=0.07)
        # bead width in screen pixels for THIS view, clamped so a single wall
        # still reads as a line instead of a blob on long thin jobs
        wpx = max(1.4, min(9.0, width * proj.s))
        sub = SubImage(img, ox, 30, pw, H - 60)
        draw_panel(sub, proj, tp, zmin, zmax, wpx, only)
        text_overlay_line(img, ox + 4, 8, label, (200, 200, 200))
    caption = "%d seg  %d layers  %s mm  %dm fil  %dm path  %d min" % (
        st["segments"], st["layers"], "x".join(str(v) for v in st["size_mm"]),
        round(st["filament_total_m"]), round(st["toolpath_total_m"]),
        int(st["est_print_time_min"]))
    text_overlay_line(img, 6, H - 16, caption, (215, 215, 215))
    rgb = img.downsample()
    write_png(out, W, H, rgb)
    print("wrote", out)
    if tp.truncated:
        print("NOTE: truncated at --max-seg %d (raise it for the full picture)" % max_seg)
    return 0


class SubImage:
    """A window into a shared framebuffer: only offsets the drawing calls."""

    def __init__(self, img, x0, y0, w, h):
        self.img = img
        self.ss = img.ss
        self.x0, self.y0 = x0 * img.ss, y0 * img.ss
        self.w, self.h = w, h

    def quad(self, pts, color):
        # the projector already returns image-space rows (y grows downwards)
        shifted = [(self.x0 + p[0], self.y0 + p[1]) for p in pts]
        self.img.quad(shifted, color)


def text_overlay_line(img, x, y, text, color):
    pen = x
    for ch in text.upper():
        g = FONT.get(ch)
        if g:
            blit(img, pen, y, g, color)
            pen += 6
        elif ch == " ":
            pen += 4
        else:
            pen += 4


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
