# Why ZCCAD's `get path` force-closes, and how to prove the cause

Documented because it cost several hours and the failure looks random when it is
not. This is about operating the vendor app, which matters while the two toolchains
are being compared.

## Symptom

Clicking `get path` terminates `3D Print Software S528.exe` outright. Windows
records:

```
.NET Runtime 1026
  System.NullReferenceException
     at ?.?(OutPutG.WorkData)
     at LitCAD.Windows.MainWin.DispYdxP()
     at OutPutG.OutKF.thread_pro_func()
Application Error 1000
  Exception code: 0xc0000005   Faulting module: unknown
```

The `Fault offset` differs on every crash, which invites a memory-corruption
theory. It is not corruption — the managed stack is identical every time. The
offset is just where the CLR happened to be.

## Cause

`GcodePara.ini` → `[letterShell]` → **`iSideLineSel = -1`**, meaning the
`letter type` dropdown has no committed selection.

```
iSideLineSel = -1
  -> the side-profile builder matches no case
  -> no geometry produced
  -> temp.gcode gets a header and a footer and nothing between them
  -> DispYdxP() dereferences the missing result
  -> process dies
```

Proven by direct comparison: a known-good session had `iSideLineSel=1`, the
crashing session `-1`, with every other field equivalent.

## How the app gets into that state

Setting the combobox **programmatically** — UIA value assignment, or writing to the
inner edit — changes the displayed text to `line` but never fires
`SelectedIndexChanged`. The UI looks correct while the stored index stays `-1`.

Anything that automates this window without real mouse interaction can leave it
there. A human clicking the dropdown and picking an item cannot.

## The two-minute diagnosis

Check `S528\temp.gcode` immediately after clicking `get path`:

| Size | Markers present | Meaning |
|---|---|---|
| ~468 bytes / 43 lines | `;G code start`, header, then straight to `;G code end` | **zero geometry** — `letter type` unset |
| hundreds of KB | `;calculatePreSide start`, `;start printf` | geometry produced, safe to continue |

A crashed run leaves exactly this file, which is the fastest possible signal:

```
;This G_Code provided by DongGuan ZhenCai Lmt
;G code start
M104 S220 T0
M109 S220 T0
M104 S220 T1
M109 S220 T1
G21
G90
G82
G28
G1 Z15 F3600
G92 E0
T0
G1 E-85 F1200
...
M106 S255
;G code end          <- nothing printed between this and the header
G91
...
;End of Gcode
```

## Fix

1. Open the `letter type` dropdown **with the mouse** and click `line`.
2. Confirm `S528\GcodePara.ini` now reads `iSideLineSel=1`.
3. Re-select the letter, then `get path`.

Fallback without touching the UI: stop the app, set `iSideLineSel=1` in
`S528\GcodePara.ini`, restart.

## What is NOT the cause

Each of these was tested against real exports and ruled out:

| Suspect | Evidence against |
|---|---|
| The DXF being imported | `AC1018` (2004) with `$INSUNITS=4` (mm), identical to a file that exported fine |
| Self-touching contours | the file that exports cleanly has the same spline-seam artefact |
| `panel printf` enabled | geometry is already empty before any fill logic runs |
| Colour-zone config | `iLayerNum=1`, `dbLayerHeight[0]=30` was correct at crash time |
| 32-bit address space / low RAM | the exception is a deterministic `NullReference`, not OOM |
| Lost canvas selection | plausible, but the discriminator is `iSideLineSel`, not selection |

## Note on `S528\log`

The app's own log is buffered and is **lost when the process dies**. Sessions that
crashed leave no entries, so an absent log line is not evidence that code did not
run. Do not use it to date a crash.
