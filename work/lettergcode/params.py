"""Parameter model reconstructed from GcodePara.ini and the OutPutG.dll IL.

Every field name here mirrors the vendor's own identifiers so that the values in
S528\\GcodePara.ini can be mapped 1:1. Section names are the INI section names.
"""
from __future__ import annotations

import configparser
import math
from dataclasses import dataclass, field, fields


def _layers_for(mm, h):
    """Layer index a height maps to, the way ZCCAD computes it: floor + 1.

    Proven on four independent exports whose requested height is known:

        30 mm / 0.3  -> 101 layers, top z=30.30   (`welcome tes.gcode`, `1.gcode`)
        50 mm / 0.3  -> 167 layers, top z=50.10   (`A_SAMPLE_50mm.gcode`, `TES .gcode`)
        30 mm / 0.5  ->  61 layers, top z=30.50   (`Welcome new tes.gcode`)

    `ceil` agrees with all three except where the division is exact, and an exact
    division is precisely the 30 mm case: ceil gives 100, the vendor gives 101.
    ZCCAD always rounds up by one extra layer, so the part is never short.

    Used for both the total layer count and cumulative colour-band boundaries;
    callers must pass a CUMULATIVE height for bands, not the per-band height.

    The epsilon absorbs float noise: 30 / 0.3 evaluates to 100.00000000000001
    and must floor to 100, not 101.
    """
    if not h or h <= 0:
        return 1
    return max(1, int(math.floor(mm / h + 1e-9)) + 1)


def _f(v, default=0.0):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def _i(v, default=0):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def _b(v, default=False):
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return default


@dataclass
class LetterShell:
    """[letterShell] - the shell / wall definition."""
    iSideLineSel: int = 0
    bPrintDir: bool = True
    dbHeightShell: float = 5.0
    dbWidthSide: float = 0.0
    dbHeightTop: float = 0.0
    dbHeightLow: float = 0.0
    dbHeightLayer: float = 0.3
    dbOffsetPreSide: float = 15.0
    iNumPreSide: int = 2
    dbWidthKnife: float = 0.4
    dbThicknessOrigin: float = 1.2
    iThichnessType: int = 0
    dbThichnessCompensate: float = 0.0
    iThichnessCount: int = 1
    dbHeightPin: float = 0.0
    dbWidthSidePin: float = 0.0
    dbThichnessHeight: float = 0.0
    dbThichnessOffset: float = 0.8
    dbThicknessCompensate: float = 0.0
    sCurFileName: str = ""


@dataclass
class ColorControl:
    """[colorControl] - extruder / colour change definition."""
    iLayerNum: int = 2
    dbLayerOffset: float = 0.0
    dbLayerHeight: list = field(default_factory=lambda: [3, 2, 5, 8, 8, 8, 8])
    iLayerGlueNo: list = field(default_factory=lambda: [1, 2, 1, 1, 1, 1, 1])
    bNozzleUsed: bool = False
    dbNozzleOffset: float = 1.0
    iNozzleCount: int = 1
    iSpeed: int = 2400
    dbGlueWidth: float = 1.2


@dataclass
class Surround:
    """[surroundSide] - the hem ("kelim") band around the letter rim.

    dbHeight1 is the one field the path generator needs: it is the thickness of
    the band at the top of the letter where only the wall line is printed and the
    fill is held back.  Both sample jobs agree on it (0.9 mm = 3 x 0.3 layers).
    """
    dbHeight: float = 2.2
    dbWtop: float = 2.0
    dbWbottom: float = 2.0
    dbGlueOffset: float = 0.8
    dbGlueWidth: float = 1.2
    dbHeight1: float = 0.9
    dbHeight2: float = 3.0
    dbWidth: float = 3.0
    dbOffsetFlat: float = 0.8
    dbOffsetSharp: float = 0.4
    dbBoardPosX: float = 300.0
    dbBoardPosY: float = 300.0
    dbBoardHeight: float = 5.0
    iSpeed: int = 2400


@dataclass
class Seat:
    """Acrylic pocket at the top rim ("pangkon").

    The wall doubles in thickness for the last `depth` millimetres, so a sheet
    drops into the gap and rests on the shoulder; the top `depth` mm then print
    the outer lip alone.  No vendor INI field describes this - the numbers come
    from the customer drawing layer `4_POCKET_ATAS_5.2mm` (5.2 mm total rim =
    2.0 mm lip + 3.2 mm pocket for a 3 mm acrylic).

    width : pocket width in plan (acrylic thickness + clearance)
    depth : pocket depth in Z - the lip height above the shoulder
    land  : flat full-thickness shoulder kept under the pocket
    ramp  : Z length over which the wall thickens below that shoulder, so the
            extra lines never start in mid air
    """
    width: float = 0.0
    depth: float = 5.0
    land: float = 2.0
    ramp: float = 10.0


@dataclass
class Printf3DBase:
    """[printf3D_base] - speeds, temperatures, machine dialect."""
    strCurFilePath: str = "output.gcode"
    iSpeedWork: int = 1500
    iSpeedZ: int = 1200
    iSpeedGlueAhead: int = 3600
    iSpeedGlueBack: int = 3600
    iSpeedFirstLayer: int = 1800
    dbDisGluePoint: float = 50.0
    iSpeedIdle: int = 18000
    dbHeightIdle: float = 0.3
    dbEndPosGluePoint: float = 0.0
    iT0: int = 220
    iT1: int = 220
    bHeadTear: bool = False
    dbDisClear: float = 8.0
    dbDisIdle: float = 1200.0
    dbDisEarlyOff: float = 0.0
    iMachineSel: int = 1
    bNonPullback: bool = False
    dbHeightIdleSta: float = 0.3


@dataclass
class GluePara:
    """[gluePara] - the extrusion (E) calibration model."""
    dbStuffWidth: float = 1.75
    dbDisGlueBack: float = 3.0
    dbCompensateNear: float = 0.01
    dbCompensateFar: float = 0.02
    dbCompensateDis: float = 50.0
    dbDisOriginBack: float = 0.0
    iSpeedColorSwitch: int = 1200
    dbDisColorBack: float = 85.0
    dbCompensateColor: float = 5.0
    dbCompensateNear_: list = field(default_factory=lambda: [0.1, 0.1, 0.1])
    dbCompensateFar_: list = field(default_factory=lambda: [0.1, 0.1, 0.1])
    dbCompensateDis_: list = field(default_factory=lambda: [30, 30, 30])
    iSpeedColorBack: int = 1200
    dbPointGap: float = 0.0


#: Divisor recovered from OutPutG.dll::getCurGlueDistance.  The method computes
#:   local1 = (speed/60) * L^3 / (A * W^2)
#:   E      = local1 * (|d|/(speed/60)) * (L/W)  ==  |d| * L^3 / (A * W^3 * ... )
#: which simplifies to the closed form used below.
GLUE_CONST_A = 2.40104211897525


@dataclass
class Params:
    """Aggregate of every INI section the generator needs."""
    let: LetterShell = field(default_factory=LetterShell)
    col: ColorControl = field(default_factory=ColorControl)
    pri: Printf3DBase = field(default_factory=Printf3DBase)
    glu: GluePara = field(default_factory=GluePara)
    sur: Surround = field(default_factory=Surround)
    seat: Seat = field(default_factory=Seat)
    #: The "reverse printf" button is not stored in the INI; it only flips the
    #: order the colour bands are printed in (last configured band first).
    reverse_zones: bool = False

    # ------------------------------------------------------------------ E model
    @property
    def glue_width(self) -> float:
        """Effective extruded line width `w` (dbThicknessOrigin + compensation)."""
        return self.let.dbThicknessOrigin + self.let.dbThicknessCompensate

    @property
    def e_per_mm(self) -> float:
        """Filament mm per path mm, exactly as OutPutG.getCurGlueDistance returns."""
        w = self.glue_width
        d = self.glu.dbStuffWidth
        return (w / d) ** 3 / GLUE_CONST_A

    # ------------------------------------------------------------------ layers
    @property
    def layer_count(self) -> int:
        return _layers_for(self.let.dbHeightShell, self.let.dbHeightLayer)

    @property
    def wall_thickness(self) -> float:
        """Physical plan width of the printed wall (n lines of glue_width)."""
        n = 1 + max(1, int(self.let.iThichnessCount))
        return self.let.dbThichnessOffset * (n - 1) + self.glue_width

    def layer_z(self, idx: int) -> float:
        """Z of layer `idx` (0-based). Layer 0 sits at one layer-height above 0."""
        return round((idx + 1) * self.let.dbHeightLayer, 6)

    @property
    def hem_layers(self) -> int:
        """Top layers that carry the hem band only (surroundSide.dbHeight1).

        0.9 mm / 0.3 mm = 3 layers, which is exactly what every vendor export
        shows: the fill stops one band below the top and the wall runs on alone.
        """
        h = self.let.dbHeightLayer or 0.3
        if self.sur.dbHeight1 <= 0:
            return 0
        return max(0, min(self.layer_count, int(round(self.sur.dbHeight1 / h))))

    @property
    def color_switch_z(self) -> float:
        """Z of the first colour change (layer boundary), or a huge number."""
        plan = self.band_plan()
        first = plan[0] if plan else 1
        for i, glue in enumerate(plan):
            if glue != first:
                return self.layer_z(i)
        return float("inf")

    def band_plan(self):
        """iLayerGlueNo value for every layer, indexed from the bottom up.

        Verified against three vendor exports: the bands run in the configured
        order (bottom up) unless the "reverse printf" button flipped them, each
        band is snapped to round(height / layer) layers or replaced by whatever
        is left when it is the last one printed, and the band's `iLayerGlueNo`
        value `g` drives nozzle T(g-1): glue 1 -> T0, glue 2 -> T1.
        """
        total = self.layer_count
        h = self.let.dbHeightLayer or 0.3
        n = max(1, int(self.col.iLayerNum))
        heights = [_f(v) for v in self.col.dbLayerHeight[:n]]
        glues = [int(v) for v in self.col.iLayerGlueNo[:n]]
        while len(heights) < n:
            heights.append(0.0)
        while len(glues) < n:
            glues.append(glues[-1] if glues else 1)
        zones = list(zip(heights, glues))
        if self.reverse_zones:
            zones.reverse()
        plan = []
        cum = 0.0
        for i, (hi, gl) in enumerate(zones):
            if i == len(zones) - 1:
                k = total - len(plan)
            else:
                # cumulative, not per-band: ZCCAD's boundary for a 10 mm band is
                # layer 34 and for 10+30 mm it is layer 134, which only a
                # cumulative floor+1 reproduces.
                cum += hi
                k = _layers_for(cum, h) - len(plan)
            plan.extend([gl] * max(0, k))
        plan = plan[:total]
        while len(plan) < total:
            plan.append(zones[-1][1])
        return plan

    def glue_no_for_layer(self, idx: int) -> int:
        """Extruder index (1-based) for a 0-based layer number."""
        plan = self.band_plan()
        if not plan:
            return 1
        return plan[max(0, min(int(idx), len(plan) - 1))]

    def glue_no_for_z(self, z: float) -> int:
        """Extruder index for a given layer Z (1-based, as in iLayerGlueNo)."""
        if self.let.dbHeightLayer <= 0:
            return self.glue_no_for_layer(0)
        idx = int(round(z / self.let.dbHeightLayer)) - 1
        return self.glue_no_for_layer(max(0, idx))

    # ------------------------------------------------------------------ loading
    @classmethod
    def from_ini(cls, path: str) -> "Params":
        cp = configparser.ConfigParser(strict=False)
        cp.optionxform = str            # keep the vendor's camelCase keys
        with open(path, "r", encoding="latin-1") as fh:
            cp.read_file(fh)
        p = cls()

        def pull(section, obj):
            if not cp.has_section(section):
                return
            known = {f.name: f for f in fields(obj)}
            for key, raw in cp.items(section):
                if key in known:
                    default = known[key].default
                    if isinstance(default, bool):
                        setattr(obj, key, _b(raw, default))
                    elif isinstance(default, int):
                        setattr(obj, key, _i(raw, default))
                    elif isinstance(default, float):
                        setattr(obj, key, _f(raw, default))
                    else:
                        setattr(obj, key, raw)
                # array keys:  dbLayerHeight[0] / iLayerGlueNo[1] / ...
                elif "[" in key and key.endswith("]"):
                    base, _, idx = key.partition("[")
                    idx = idx.rstrip("]")
                    if not idx.isdigit():
                        continue
                    target = getattr(obj, base, None)
                    if isinstance(target, list):
                        slot = int(idx)
                        while len(target) <= slot:
                            target.append(0.0 if isinstance(target[-1], float) else 0)
                        is_float = isinstance(target[0], float) if target else True
                        target[slot] = _f(raw) if is_float else _i(raw)
                elif key.startswith("dbCompensate") and "[" in key:
                    pass

        pull("letterShell", p.let)
        pull("colorControl", p.col)
        pull("printf3D_base", p.pri)
        pull("gluePara", p.glu)
        pull("surroundSide", p.sur)

        # The per-extruder compensation triples are stored as three parallel arrays.
        for i in range(3):
            for src, dst in (("dbCompensateNear", "dbCompensateNear_"),
                             ("dbCompensateFar", "dbCompensateFar_"),
                             ("dbCompensateDis", "dbCompensateDis_")):
                key = f"{src}[{i}]"
                if cp.has_option("gluePara", key):
                    getattr(p.glu, dst)[i] = _f(cp.get("gluePara", key))
        return p

    # -------------------------------------------------------------- machine sel
    @property
    def extruder_count(self) -> int:
        """Number of extruders referenced by the colour plan."""
        used = [int(v) for v in self.col.iLayerGlueNo[: max(1, self.col.iLayerNum)]]
        return max(max(used) + 1 if used and min(used) == 0 else max(used), 2)

    def tool_no(self, glue_no: int) -> int:
        """Map a 1-based iLayerGlueNo value onto the T number used in G-code.

        Measured on the vendor exports: glue 1 -> T0, glue 2 -> T1 (a two
        colour job loads 1/2 and the file contains T0/T1, never T1/T2).
        """
        return max(0, int(glue_no) - 1)
