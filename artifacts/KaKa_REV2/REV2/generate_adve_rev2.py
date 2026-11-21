"""
ADve tes.dxf -> ZCCAD-dialect G-code, REV2 parameters.

Parameter provenance: 08_Hasil Akhir dan validasi/Validasi update parameter fix.pdf
(three annotated parameter sets from the user's own successfully printed parts),
plus measured values from 08_Hasil Akhir dan validasi/k.gcode and
TES_IM_M_I_original.gcode.

REV2 changes vs REV1:
  layer 0.25 -> 0.30 mm; flow 0.11296821 -> 0.1342857 E/mm
  230 C on T0/T1; bed unheated
  strong integrated base: slow hatch + pre-side brim on layers 1-3
  speed ramp: base/pre-side 30 mm/s, walls 40 then 50 mm/s
  pangkon lips: 3 lines at 0.6/1.2/1.8 mm inset, 40 mm/s, Z3.6 and Z11.4
  seam and stop-and-go moved INSIDE the letter; walls continuous across layers
  no G0 with E, no extrusion while Z changes
"""
import os, math, hashlib, ezdxf, numpy as np
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union

SRC = r'C:\Users\Pongo\Downloads\asset-7c9d82210199498c\ZCCAD_Arsip_20261118\08_Hasil Akhir dan validasi\ADve tes.dxf'
OUT = r'C:\Users\Pongo\Downloads\Project KITA KITA\GCODE_OUTPUT\REV2'
os.makedirs(OUT, exist_ok=True)
GCODE = os.path.join(OUT, 'ADve_ZCCAD_REV2.gcode')

# ---------------- parameters (validated revision) ----------------
LH          = 0.30
LAYERS      = 84          # 84 x 0.30 = 25.20 mm
FLOW        = 0.1342857   # measured from printed k.gcode: 0.067142857 / 0.5 mm
TEMP        = 230
F_BASE      = 1800        # 30 mm/s  slow hatch / pre-side
F_PANGKON   = 2400        # 40 mm/s
F_WALL_LOW  = 2400        # 40 mm/s layers 4-10
F_WALL      = 3000        # 50 mm/s layers 11+
F_LEAD      = 1800        # 30 mm/s inside lead-in
F_RETRACT   = 3600        # 60 mm/s
F_RECOVER   = 4800        # 80 mm/s
F_TRAVEL    = 18000       # 300 mm/s
RETRACT     = 3.0
PRIME       = 0.1
WALL_INSETS = (0.6, 1.4)  # 2 loops -> 2.0 mm wall
BASE_LAYERS = 3
PANGKON_Z   = (3.6, 11.4)
PANGKON_D   = (0.6, 1.2, 1.8)
BRIM_D      = [0.6 + 0.6*i for i in range(8)]   # 8 mm wide
HATCH_STEP  = 1.2

# ---------------- geometry ----------------
doc = ezdxf.readfile(SRC)
splines = [e for e in doc.modelspace() if e.dxftype() == 'SPLINE']
polys = [Polygon(np.array([[q[0], q[1]] for q in e.flattening(distance=0.02)])) for e in splines]
polys = [p for p in polys if p.is_valid]
outers = [p for p in polys if not any(q is not p and q.area > p.area and q.covers(p) for q in polys)]
regions = []
for o in outers:
    holes = [h.exterior.coords for h in polys if h is not o and o.covers(h)]
    regions.append(Polygon(o.exterior.coords, holes))
merge = unary_union(regions)
minx, miny, maxx, maxy = merge.bounds
from shapely.affinity import translate
tx, ty = 400.0 - (minx+maxx)/2, 400.0 - (miny+maxy)/2
regions = [translate(r, xoff=tx, yoff=ty) for r in regions]

def rings(geom):
    out=[]
    gs = geom.geoms if hasattr(geom,'geoms') else [geom]
    for g in gs:
        if g.is_empty: continue
        if g.geom_type=='Polygon':
            out += [list(g.exterior.coords)] + [list(i.coords) for i in g.interiors]
        elif g.geom_type=='MultiPolygon': out += rings(g)
    return [r for r in out if len(r)>=4]

wall_rings=[]
for r in regions:
    for d in WALL_INSETS:
        wall_rings += rings(r.buffer(-d, join_style=2))
brim_rings = rings(unary_union([Polygon(r.exterior).buffer(d, join_style=2)
                                for r in regions for d in BRIM_D]))
pangkon_rings=[]
for z in PANGKON_Z:
    for r in regions:
        for d in PANGKON_D:
            pangkon_rings.append((z, rings(r.buffer(-d, join_style=2))))

# hatch fill (slow solid base) - horizontal serpentine inside each region
hatch=[]
for r in regions:
    inner = r.buffer(-0.6, join_style=2)
    y = math.floor((miny+ty)/HATCH_STEP)*HATCH_STEP
    while y < maxy+ty:
        seg = inner.intersection(LineString([(minx+tx-5,y),(maxx+tx+5,y)]))
        gs = seg.geoms if hasattr(seg,'geoms') else [seg]
        for g in gs:
            if g.geom_type=='LineString' and g.length>0.5:
                hatch.append(list(g.coords))
        y += HATCH_STEP

# ---------------- writer ----------------
header=[
 ';ADve tes.dxf -> ZCCAD DIALECT REPLICA Rev2 (parameters from physical print validation)',
 ';Source: ADve tes.dxf, 7 closed splines, 156.15 x 43.63 mm, centred on 800x800 bed',
 ';Layer 0.30 mm x 84 = 25.20 mm; flow 0.1342857 mm/mm (measured from printed k.gcode)',
 ';T0/T1 = 230 C, unheated bed. T2 clear only, no colour change.',
 ';BASE: slow 30 mm/s hatch + 8 mm pre-side brim on layers 1-3 (prevents corner lift)',
 ';PANGKON: 3 lines 0.6/1.2/1.8 mm at Z3.6 and Z11.4, 40 mm/s',
 ';WALL: 2 loops -0.6/-1.4 mm, 40 mm/s then 50 mm/s, continuous across layers',
 ';SEAM / STOP-AND-GO moved INSIDE the letter lead-in; no G0 with E; no E during Z.',
 ';REVISION SOURCE: Validasi update parameter fix.pdf (user print, 22 Oct) + k.gcode.',
 ';DIALECT REPLICA - native ZCCAD, G82 firmware response and physical print UNVERIFIED.',
 ';MACHINE_INIT',
 'M140 S0',
 f'M104 S{TEMP} T0', f'M109 S{TEMP} T0',
 f'M104 S{TEMP} T1', f'M109 S{TEMP} T1',
 'G21','G90','G82','G28','G1 Z15 F3000',
 'G92 E0','T0','G1 E-85 F1200','G92 E0',
 'T1','G1 E85 F1500','G92 E0',
 'T1','G1 E-85 F1200','G92 E0',
 'T0','G1 E85 F1500','G92 E0','T0',
 'M117 Printing...','M106 S255',
]
footer=[';PRINT_BODY_END','G0 F12000 Z35.000','G91','G0 X5 Y5 F18000','G0 F18000 Z0','G90',
 'G0 X750 Y750 F18000','G92 E0','G91',f'G1 F{F_RETRACT} E-85','M84','M107',
 'M104 S30 T0','M104 S30 T1','M106 S0',';End of Gcode']

class W:
    def __init__(self,lines):
        self.l=list(lines); self.e=0.0; self.z=0.0; self.retr=False; self.dep=0.0; self.F={}
    def add(self,s): self.l.append(s)
    def travel(self,x,y,z):
        lift=max(self.z,z)+0.6
        self.add(f'G0 F{F_TRAVEL} X{x:.5f} Y{y:.5f}')
        if lift>z+1e-9: self.add(f'G0 F{F_TRAVEL} Z{lift:.4f}')
        self.add(f'G0 F{F_TRAVEL} Z{z:.4f}'); self.z=z
    def unload(self,z):
        if self.retr:
            self.e+=RETRACT; self.add(f'G1 E{self.e:.6f} F{F_RECOVER}'); self.retr=False
    def retract(self,z):
        self.e-=RETRACT; self.add(f'G1 E{self.e:.6f} F{F_RETRACT}'); self.retr=True
    def prime(self):
        self.e+=PRIME; self.add(f'G1 E{self.e:.6f} F{F_LEAD}'); self.add('G4 P200')
    def seg(self,a,b,f):
        d=math.dist(a,b)
        if d<1e-6: return
        self.e+=d*FLOW; self.dep+=d; self.F[f]=self.F.get(f,0)+1
        self.add(f'G1 X{b[0]:.5f} Y{b[1]:.5f} E{self.e:.6f} F{f}')
    def ring(self,pts,z,f,feature,inside_lead=True):
        self.add(f';PATH_BEGIN {feature} Z{z:.4f}')
        self.travel(pts[0][0],pts[0][1],z); self.unload(z); self.prime()
        n=len(pts); s=int(np.argmin([p[0] for p in pts]))
        seq=[pts[(s+k)%n] for k in range(n)]+[pts[s]]
        if inside_lead:
            p=seq[0]; q=seq[1]
            # 2.0 mm lead starting INSIDE the material, toward the seam
            vx,vy=q[0]-p[0],q[1]-p[1]; L=math.hypot(vx,vy) or 1
            inn=(p[0]-2.0*vx/L, p[1]-2.0*vy/L)
            self.add(';INTERNAL_LEAD')
            self.travel(inn[0],inn[1],z)
            self.seg(inn,p,F_LEAD)
        for a,b in zip(seq[:-1],seq[1:]): self.seg(a,b,f)
        self.retract(z)
        self.add(f'G0 F{F_TRAVEL} Z{z+0.6:.4f}'); self.z=z+0.6
        self.add(';PATH_END')
    def continuous_wall(self,pts,f):
        """One closed loop printed on every layer without retract/prime at Z changes."""
        n=len(pts); s=int(np.argmin([p[0] for p in pts]))
        seq=[pts[(s+k)%n] for k in range(n)]+[pts[s]]
        p,q=seq[0],seq[1]
        vx,vy=q[0]-p[0],q[1]-p[1]; L=math.hypot(vx,vy) or 1
        inn=(p[0]-2.0*vx/L,p[1]-2.0*vy/L)
        self.add(';WALL_CONTINUOUS_BEGIN')
        self.travel(inn[0],inn[1],0.3); self.unload(0.3); self.prime()
        self.add(';INTERNAL_LEAD'); self.seg(inn,p,F_LEAD)
        for layer in range(1,LAYERS+1):
            z=round(layer*LH,4)
            self.add(f';LAYER {layer} Z={z:.3f} WALL_CONTINUOUS')
            if layer>1: self.add(f'G0 F{F_TRAVEL} Z{z:.4f}'); self.z=z
            layer_f = F_WALL_LOW if layer <= 10 else F_WALL
            for a,b in zip(seq[:-1],seq[1:]): self.seg(a,b,layer_f)
        self.retract(LAYERS*LH)
        self.add(f'G0 F{F_TRAVEL} Z{LAYERS*LH+0.6:.4f}'); self.z=LAYERS*LH+0.6
        self.add(';WALL_CONTINUOUS_END')
    def hatch_path(self,seg,z,f):
        self.add(';BASE_HATCH')
        self.travel(seg[0][0],seg[0][1],z); self.unload(z); self.prime()
        for a,b in zip(seg[:-1],seg[1:]): self.seg(a,b,f)
        self.retract(z)
        self.add(f'G0 F{F_TRAVEL} Z{z+0.6:.4f}'); self.z=z+0.6
        self.add(';PATH_END')

w=W(header)
# layers 1-3: brim + solid hatch base, all slow
for layer in range(1,BASE_LAYERS+1):
    z=round(layer*LH,4)
    w.add(f';LAYER {layer} Z={z:.3f} BASE')
    if layer==1:
        for r in brim_rings: w.ring(r,z,F_BASE,'PRE_SIDE_BRIM_8MM')
    for s in hatch: w.hatch_path(s,z,F_BASE)
# pangkon lips at the two validated heights
for z,ringset in pangkon_rings:
    for r in ringset: w.ring(r,z,F_PANGKON,'PANGKON_LIP')
# continuous walls: low speed first 10 layers, then 50 mm/s
for pts in wall_rings:
    w.continuous_wall(pts,F_WALL_LOW)

with open(GCODE,'w',encoding='ascii',newline='\n') as f: f.write('\n'.join(w.l)+'\n')
print('regions',len(regions),'wall_rings',len(wall_rings),'brim',len(brim_rings),'hatch_segments',len(hatch))
print('lines',len(w.l),'deposit_path_m',round(w.dep/1000,3),'filament_m',round(w.dep*FLOW/1000,3))
print('filament_g',round(w.dep*FLOW*2.405*1.24/1000,1))
print('F counts',w.F)
print('bytes',os.path.getsize(GCODE))
print('sha256',hashlib.sha256(open(GCODE,'rb').read()).hexdigest())
print(GCODE)
