KA KA / KK HONEYCOMB - G-CODE PACKAGE (2026-11-21)
========================================================================

SOURCE
  Test shape: "Ka Ka.dxf" (K + a, 138.462 x 80.669 mm).
  Its layer 01_HONEYCOMB_OPENINGS_5AF_W1p2 holds the 3 closed shell
  splines used for the wall file; face holes were not walled.
  Production STLs: KK_HONEYCOMB_FACE_RevA.stl (461.082 x 247.929 x 1.5 mm)
                  K Frame STL.stl (461.082 x 247.929 x 25 mm).

FILES
  01_KaKa_ZCCAD_wall_2mm_brim.gcode
     ZCCAD-dialect REPLICA, generated from the Ka Ka DXF shell.
     2.0 mm wall (2 loops at -0.6/-1.4 mm), 100 layers x 0.25 = 25 mm,
     8 mm brim x 1 layer + dense base layers 1-2, T2 only.
     Smooth edge: spline flattened at 0.02 mm chord deviation.
     Flow 0.11296821 mm/mm, F1260/F1200 base, F2100 wall, F840 lead,
     retract 3 mm @F1800, restore @F4800, prime 0.1 mm + G4 P200.
     372,182 lines; 160.55 m deposit path; 18.14 m filament; ~54 g PLA.
     Mechanically validated: 100 layers, no G0 with E, no E during Z,
     XY within bed, replayed E matches the generator.

  02_KaKa_Orca_face_1p5mm.gcode / 03_KaKa_Orca_frame_25mm.gcode
     REAL OrcaSlicer 2.5.0-dev headless output (--slice 0), sliced from
     the two STLs above. CLI overrides used: printable area 800x800,
     height 65, nozzle 1.2 mm, absolute E.
     IMPORTANT: the installed Iguana presets inherit system profiles and
     could NOT be resolved in headless mode, so these files use Orca
     defaults: nozzle 200 C, bed 35 C, 0.3 mm profile was NOT applied
     (first layer 0.2 mm). Before any print, select
     "0.30mm Channel Letter @Iguana" + "Iguana 800 - 1.2 Nozzle" +
     "Iguana PLA @Iguana" in the Orca GUI and re-slice, or correct the
     temperature/bed G-code. Do NOT run these as-is.

STATUS / LIMITS
  - Dialect replica only: G82, firmware response, adhesion, flow and
    physical print are UNVERIFIED. No print was attempted.
  - From ABCD100 RevA: head/gantry swept clearance for tall sequential
    objects was NEVER verified. Check before running any tall job.
  - Nothing was sent to any printer or over Wi-Fi. No vendor binary
    was patched and no licence check was bypassed.
  - The ZCCAD file is the "Ka Ka" TEST piece; the Orca files are the
    full-size production STLs because Orca cannot import the DXF.

SHA-256
  2762b1b41a0c2121503910a2a8d41d58456c17a7a4e6088fb99aad9f06aa71a5  01_KaKa_ZCCAD_wall_2mm_brim.gcode
  2f0abfd672444c911e31685b840c41a71abcb2bf4d4975dd46903058697a5a11  02_KaKa_Orca_face_1p5mm.gcode
  048316185ed21a10dda465cd613ab50ec0f5fbed1e42c566bb5672fe93457021  03_KaKa_Orca_frame_25mm.gcode
  adfeee8fa9064877f3b296963985dbc8d6536599bb57e75ef3452216d7dee4e8  00_toolpath_preview_KaKa.png
  e7257cbf097c46f38ec9583e8080306ed73b3bda0ec30ebe4422d6ce6213102c  generate_kaka_gcode.py
