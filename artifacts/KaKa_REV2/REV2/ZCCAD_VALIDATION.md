ZCCAD NATIVE VALIDATION - 21 Nov 2026
=====================================
Software: ZCCAD (3D Print Software S528.exe), machine type ZC-80.

WHAT WAS CHECKED IN THE OPEN APPLICATION
  1. Imported "ADve tes.dxf" via Import. SUCCESS - the letters A D v e
     render in the canvas with start markers. Evidence: 01_ZCCAD_import_ADve.png
  2. Letter Shell parameters displayed by ZCCAD:
       layer height 0.30 mm  (matches REV2)
       wall thickness 1.20 mm, line count 1  (REV2 uses 2 loops = 2.0 mm)
       letter height 15 mm, knife width 0.4 mm
       line height 0.3 mm, line offset 0.8 mm
       around offset 15 mm, around count 2
  3. InFill dialog: Panel filling ON, Fill spacing 1.20 mm
     (matches REV2 HATCH_STEP 1.2 mm). Evidence: 03_ZCCAD_infill_spacing.png
  4. file output dialog: print speed 38 mm/s, first speed 30 mm/s,
     move speed 300 mm/s, temperature1/2 220 C, machine ZC-80.
     Evidence: 02_ZCCAD_file_output_params.png
  5. Native G-code exported to ZCCAD_native_ADve.gcode. Its header/footer
     is the same dialect family as REV2:
       ";This G_Code provided by DongGuan ZhenCai Lmt"
       M104/M109 S... T0/T1, G21, G90, G82, G28, G1 Z15 F...,
       G92 E0, T0/T1 unload/load 85 mm, M117, M106 S255,
       footer park + E-85 + M84/M107 + heaters 30 C.
     Native uses F2280 Z-lift and F1140 reload; REV2 uses F3000/F1500.

LIMIT / NOT RESOLVED
  Native "get path" reported "current extruder length: 0.000 m" with the
  current UI state, so the exported native file contains no deposition
  moves. A native toolpath could therefore NOT be compared move-by-move
  with ADve_ZCCAD_REV2.gcode. The DXF itself imports correctly; this is a
  ZCCAD contour/side selection matter in the open session, not a file
  corruption. No printer transmission was attempted.

PARAMETER DIFFERENCES TO REVIEW
  temperature: ZCCAD dialog 220 C (K profile) vs REV2 230 C (later M+I print)
  wall: ZCCAD 1.2 mm / 1 line per contour vs REV2 2 loops / 2.0 mm
  print speed: ZCCAD 38 mm/s vs REV2 40 -> 50 mm/s ramp
