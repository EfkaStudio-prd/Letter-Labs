"""Universal FDM machine profiles for the `--family universal` output.

The ZCCAD dialect is hard-wired to the Taesin / ZhenCai letter machines.  This
module answers a different question: the same letter geometry should also print
on a generic FDM printer (Bambu Lab class), so it needs standard Marlin-family
G-code - homing, relative E (M83), retraction, fan ramp, layer markers.

Speeds and temperatures are anchored on hardware evidence from the three
successful vendor letter prints (Iguana / Taesin letter printer, PLA):

  reference            layers  z-span    hotend  print F (mm/min)   travel F
  "5"  (5 (3).gcode)   52      15.3 mm   220 C   3000 main, 1800 first, 2400 detail
  "arr" (arr.gcode)    20      15.0 mm   220 C   3000/2400/1800/1500 feature-tiered
  "TES IM"                 170     50.7 mm   230 C   3000 main, 1800 detail

All three step the Z axis 0.3 mm per layer, matching the vendor INI
(dbHeightLayer=0.3).  Speeds are in mm/min like everything else in this
generator; 3000 mm/min = 50 mm/s and 1800 mm/min = 30 mm/s.  The universal
profiles below quote the PROVEN values for the standard paths and keep the
conservative tier only as a starting point - confirm a small job first anyway
(see docs/UNIVERSAL.md).

Field names are plain English on purpose: they are written into template JSON
files that operators edit, unlike the vendor INI fields which are never changed.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MachineProfile:
    name: str
    bed_x: float                 # printable X, mm
    bed_y: float
    bed_max_x: float = 0.0       # physical travel limit; 0 -> bed_x
    bed_max_y: float = 0.0
    z_max: float = 250.0
    nozzle_temp: int = 220        # vendor-proven PLA letter value (arr / "5")
    first_layer_temp: int = 220
    bed_temp: int = 55           # 0 -> never emit M140/M190
    first_layer_bed: int = 0     # 0 -> same as bed_temp
    hotend_count: int = 1        # T numbers 0..n-1 are addressable
    # retraction
    retract_mm: float = 1.0
    retract_feed: int = 2400     # mm/min
    restart_extra: float = 0.0   # mm pushed back on unretract
    retract_min_dist: float = 2.0  # travels shorter than this never retract
    z_hop: float = 0.0           # mm lifted during retract travels
    # speeds (mm/min)
    travel_speed: int = 9000
    work_speed: int = 3600
    first_layer_speed: int = 1800
    z_speed: int = 900
    # fan
    fan_value: int = 255         # M106 S value once the ramp layer is reached
    fan_layer: int = 2           # layer index (0-based) the fan turns on at
    fan_layer_speed: int = 128   # ramped value used on the first fan layer
    # flow model
    filament_dia: float = 1.75
    # marker dialect
    layer_marker_style: str = "bambu"   # ";LAYER_CHANGE / ;LAYER:n / ;HEIGHT:z"
    speed_units: str = "mm/min"         # Marlin-family; the vendor is the same
    home_corner: str = "min"            # nozzle parks at the bed minimum
    prime_blob: float = 2.0             # E mm pushed after switching nozzle

    def clamp_x(self, v: float) -> float:
        return max(0.0, min(v, self.bed_max_x or self.bed_x))

    def clamp_y(self, v: float) -> float:
        return max(0.0, min(v, self.bed_max_y or self.bed_y))

    def bed_for_header(self) -> tuple:
        return (self.bed_x, self.bed_y)


#: canonical profiles; `--profile` names must match these keys
PROFILES = {
    "marlin-generic": MachineProfile(
        name="Marlin generic 300x300",
        bed_x=300.0, bed_y=300.0, bed_max_x=305.0, bed_max_y=305.0,
        z_max=400.0,
        nozzle_temp=215, first_layer_temp=220, bed_temp=55, first_layer_bed=60,
        retract_mm=1.0, retract_feed=2400, restart_extra=0.0,
        retract_min_dist=2.0, z_hop=0.0,
        travel_speed=9000, work_speed=3000, first_layer_speed=1800,
        z_speed=900,
        fan_value=255, fan_layer=2, fan_layer_speed=192,
        layer_marker_style="marlin",
    ),
    "bambu-generic": MachineProfile(
        name="Bambu Lab generic 256x256",
        bed_x=256.0, bed_y=256.0, bed_max_x=256.0, bed_max_y=256.0,
        z_max=250.0,
        nozzle_temp=215, first_layer_temp=220, bed_temp=35, first_layer_bed=35,
        retract_mm=0.8, retract_feed=5400, restart_extra=0.0,
        retract_min_dist=1.5, z_hop=0.4,
        travel_speed=15000, work_speed=3000, first_layer_speed=1800,
        z_speed=1200,
        fan_value=255, fan_layer=2, fan_layer_speed=128,
        layer_marker_style="bambu",
    ),
    "x1c": MachineProfile(
        name="Bambu Lab X1 / X1C / X1E",
        bed_x=256.0, bed_y=256.0, bed_max_x=256.0, bed_max_y=256.0,
        z_max=250.0,
        nozzle_temp=215, first_layer_temp=220, bed_temp=35, first_layer_bed=35,
        retract_mm=0.8, retract_feed=5400, restart_extra=0.0,
        retract_min_dist=1.5, z_hop=0.4,
        travel_speed=15000, work_speed=3000, first_layer_speed=1800,
        z_speed=1200,
        fan_value=255, fan_layer=2, fan_layer_speed=128,
        layer_marker_style="bambu",
    ),
}


def get_profile(name: str) -> MachineProfile:
    key = (name or "").strip().lower()
    if key in PROFILES:
        return PROFILES[key]
    raise SystemExit(
        f"unknown --profile {name!r}; available: " + ", ".join(sorted(PROFILES)))
