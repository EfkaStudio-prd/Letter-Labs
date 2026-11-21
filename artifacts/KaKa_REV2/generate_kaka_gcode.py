"""
Ka Ka test piece -> ZCCAD-dialect wall G-code.

Dialect and constants are taken verbatim from the validated T25RC / ABCD100 RevA
jobs (GCODE_SETTINGS.md, build_job.py, T1_walls_only_25mm_original.gcode):
  flow 0.11296821 mm filament per mm of deposit, layer 0.25, T2 only,
  F1260/F1200 base, F2100 walls, F840 lead, F1800 retract, prime 0.1 + G4 P200.
Smooth edge = spline flattening at 0.02 mm chord deviation (not control polygon).
No printer/Wi-Fi transmission. Output is UNVERIFIED until physically printed.
"""
import math
import os
import hashlib
import ezdxf
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

SRC = r'C:\Users\Pongo\Downloads\Project KITA KITA\Ka Ka.dxf'
OUT = r'C:\Users\Pongo\Downloads\Project KITA KITA\GCODE_OUTPUT'
os.makedirs(OUT, exist_ok=True)
GCODE = os.path.join(OUT, '01_KaKa_ZCCAD_wall_2mm_brim.gcode')

# ---------------- geometry ----------------
doc = ezdxf.readfile(SRC)
splines = [e for e in doc.modelspace()
           if e.dxftype() == 'SPLINE' and e.dxf.layer == '01_HONEYCOMB_OPENINGS_5AF_W1p2']
assert len(splines) == 3, len(splines)
polys = [Polygon(np.array([[q[0], q[1]] for q in e.flattening(distance=0.02)])) for e in splines]
assert all(p.is_valid for p in polys)

# K stem+arms (area 2857.9) and 'a' outer (3835.0) with its circular counter (1013.2)
big = max(polys, key=lambda p: p.area)              # 'a' outer
small = min(polys, key=lambda p: p.area)            # counter
kpoly = [p for p in polys if p is not big and p is not small][0]
region_a = Polygon(big.exterior.coords, [small.exterior.coords])
regions = [kpoly, region_a]
merge = unary_union(regions)

# centre on the 800 x 800 Iguana bed
minx, miny, maxx, maxy = merge.bounds
tx, ty = 400.0 - (minx + maxx) / 2.0, 400.0 - (miny + maxy) / 2.0
from shapely.affinity import translate
regions = [translate(r, xoff=tx, yoff=ty) for r in regions]

FLOW = 0.11296821
LAYERS = 100
LH = 0.25
WALL_INSETS = (0.6, 1.4)
BRIM_D = [7.4 - i for i in range(8)]   # 7.4 .. 0.4 mm, 8 loops, 8 mm wide

def rings(geom):
    out = []
    geoms = geom.geoms if hasattr(geom, 'geoms') else [geom]
    for g in geoms:
        if g.is_empty:
            continue
        if g.geom_type == 'Polygon':
            out += [list(g.exterior.coords)] + [list(i.coords) for i in g.interiors]
        elif g.geom_type == 'MultiPolygon':
            out += rings(g)
    return [r for r in out if len(r) >= 4]

wall_rings = []
for r in regions:
    for d in WALL_INSETS:
        wall_rings += rings(r.buffer(-d, join_style=2))
brim_rings = rings(unary_union([Polygon(r.exterior).buffer(d, join_style=2)
                                for r in regions for d in BRIM_D]))

# ---------------- dialect writer ----------------
header = [
    ';KA KA TEST PIECE - ZCCAD DIALECT REPLICA - WALL ONLY 2.0 mm x 25 mm',
    ';Source: Ka Ka.dxf layer 01_HONEYCOMB_OPENINGS_5AF_W1p2 (K + a shell outlines)',
    f';Source outline {maxx-minx:.4f} x {maxy-miny:.4f} mm, translated to bed centre (400,400)',
    ';Smooth edge: cubic spline flattened at 0.02 mm chord deviation, NOT control polygon',
    ';Wall thickness 2.0 mm: 2 loops at -0.6 and -1.4 mm, 1.2 mm nozzle',
    ';Base: 8 mm brim x 1 layer at 20 mm/s + dense base wall layers 1-2 at 21/20 mm/s',
    ';Layers 0.25 mm x 100 = 25.00 mm. Walls 35 mm/s, lead 14 mm/s, explicit F per move',
    ';DIALECT REPLICA - NOT NATIVE ZCCAD. G82/firmware, adhesion and physical print UNVERIFIED.',
    ';Single colour: UI slot 3 = CLEAR PLA / T2. No colour change, no purge box.',
    ';MACHINE_INIT',
    'M140 S0 ; unheated bed',
    'M104 S230 T0', 'M109 S230 T0',
    'M104 S230 T1', 'M109 S230 T1',
    'G21', 'G90', 'G82', 'G28',
    'G1 Z15 F3000',
    'G0 F12000 X425.4626 Y472.4718',
    ';IM_LOAD_UNLOAD_INIT_NOT_A_PRINT_PATH',
    'G92 E0', 'T2', 'G1 E85 F1500', 'G92 E0', 'T2',
    'M117 Printing...', 'M106 S255',
]
footer = [
    ';PRINT_BODY_END',
    'G0 F12000 Z35.000', 'G91', 'G0 X5 Y5 F12000', 'G0 F12000 Z0', 'G90',
    'G0 X750 Y750 F12000', 'G92 E0', 'G91', 'G1 F1800 E-85', 'M84', 'M107',
    'M104 S30 T0', 'M104 S30 T1', 'M106 S0', ';End of Gcode',
]

class Writer:
    def __init__(self, lines):
        self.lines = list(lines)
        self.e = 0.0
        self.retracted = False
        self.z = None
        self.deposit_mm = 0.0
        self.speed_counts = {}

    def add(self, s):
        self.lines.append(s)

    def travel(self, x, y, z):
        lift = max(self.z if self.z is not None else 0.0, z) + 0.6
        self.add(f'G0 F12000 X{x:.5f} Y{y:.5f}')
        if lift > z + 1e-9:
            self.add(f'G0 F12000 Z{lift:.4f}')
        self.add(f'G0 F12000 Z{z:.4f}')
        self.z = z

    def path(self, pts, z, feed, feature):
        if len(pts) < 3:
            return
        self.add(f';PATH_BEGIN {feature} Z{z:.4f}')
        self.travel(pts[0][0], pts[0][1], z)
        if self.retracted:
            self.e += 3.0
            self.add(f'G1 E{self.e:.6f} F4800')
            self.retracted = False
        self.e += 0.1
        self.add(f'G1 E{self.e:.6f} F60')
        self.add('G4 P200')
        # seam at left-most point; 3.5 mm slow lead along the loop before it
        n = len(pts)
        s = int(np.argmin([p[0] for p in pts]))
        seq = [pts[(s + k) % n] for k in range(n)] + [pts[s]]
        lens = [math.dist(seq[i], seq[i + 1]) for i in range(len(seq) - 1)]
        k = 0
        back = 0.0
        while k < len(lens) - 1 and back < 3.5:
            back += lens[-(k + 1)]
            k += 1
        lead = list(reversed(seq[len(seq) - 1 - k:len(seq) - 1]))
        self.add(';INTERNAL_LEAD')
        for a, b in zip(lead[:-1], lead[1:]):
            d = math.dist(a, b)
            self.e += d * FLOW
            self.deposit_mm += d
            self.speed_counts[840] = self.speed_counts.get(840, 0) + 1
            self.add(f'G1 X{b[0]:.5f} Y{b[1]:.5f} E{self.e:.6f} F840')
        for a, b in zip(seq[:-1], seq[1:]):
            d = math.dist(a, b)
            if d < 1e-6:
                continue
            self.e += d * FLOW
            self.deposit_mm += d
            self.speed_counts[feed] = self.speed_counts.get(feed, 0) + 1
            self.add(f'G1 X{b[0]:.5f} Y{b[1]:.5f} E{self.e:.6f} F{feed}')
        if self.e > 30:
            self.e -= 3.0
            self.add(f'G1 E{self.e:.6f} F1800')
            self.retracted = True
        self.add(f'G0 F12000 Z{z + 0.6:.4f}')
        self.z = z + 0.6
        self.add(';PATH_END')

w = Writer(header)
# Layer 1: brim outside -> base walls. Layer 2: base walls. Layers 3-100: walls.
for layer in range(1, LAYERS + 1):
    z = round(layer * LH, 4)
    w.add(f';LAYER {layer} Z={z:.3f} {"BASE" if layer <= 2 else "WALL"}')
    if layer == 1:
        for r in brim_rings:
            w.path(r, z, 1200, 'BRIM_8MM')
    feed = 1260 if layer == 1 else (1200 if layer == 2 else 2100)
    for r in wall_rings:
        w.path(r, z, feed, 'WALL_2MM')
w.lines += footer

with open(GCODE, 'w', encoding='ascii', newline='\n') as f:
    f.write('\n'.join(w.lines) + '\n')

print('source_bbox_mm', [round(v, 3) for v in (maxx-minx, maxy-miny)])
print('brim_rings', len(brim_rings), 'wall_rings', len(wall_rings))
filament_mm = w.deposit_mm * FLOW
print('lines', len(w.lines), 'deposit_path_m', round(w.deposit_mm/1000, 3))
print('filament_m', round(filament_mm/1000, 3),
      'filament_g', round(filament_mm * 2.405 * 1.24 / 1000, 1))
print('speeds', w.speed_counts)
print('bytes', os.path.getsize(GCODE))
print('sha256', hashlib.sha256(open(GCODE,'rb').read()).hexdigest())
print('out', GCODE)
