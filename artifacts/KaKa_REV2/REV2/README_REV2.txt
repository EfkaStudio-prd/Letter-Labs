KA KA / ADve TEST - REV2 G-CODE (updated from real print validation)
======================================================================
Source shape : ADve tes.dxf (A D v e, 156.15 x 43.63 mm, 7 closed splines)
Output       : ADve_ZCCAD_REV2.gcode
Template     : letter_settings_rev2.json  (reusable parameter set)

WHAT CHANGED FROM REV1
  layer 0.25 -> 0.30 mm
  E/mm 0.11296821 -> 0.1342857 (measured from the printed k.gcode)
  T0/T1 230 C, bed unheated
  integrated slow hatch base + 8 mm pre-side brim on layers 1-3 (30 mm/s)
  pangkon lips: 0.6/1.2/1.8 mm at Z3.6 and Z11.4 (40 mm/s)
  wall speed ramp 40 -> 50 mm/s; continuous across layer changes
  seam / stop-and-go moved INSIDE the letter lead-in
  no G0 with E, no extrusion while Z changes

MECHANICAL VALIDATION (pass)
  84 layers (Z 0.3 .. 25.2), 0 motion-rule violations
  replayed E/mm = 0.134286 (matches the printed reference)
  131.05 m deposit path, 17.60 m filament, ~52.5 g PLA
  XY inside the 800 x 800 bed

LIMITS
  Dialect REPLICA. Native ZCCAD import, G82 firmware response, adhesion,
  head/gantry clearance and physical print of this REV2 file are NOT verified.
  Nothing was transmitted to a printer or network.
