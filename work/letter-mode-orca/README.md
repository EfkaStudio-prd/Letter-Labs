# Letter Mode in OrcaSlicer — work in progress (review copy)

This folder is a **review copy of uncommitted work** from the separate worktree
`C:\Users\Pongo\Downloads\OrcaSlicer-LetterMode\.worktrees\letter-mode`
(branch `feat/letter-mode-ui`, pinned base `12c9ee81` / OrcaSlicer 2.6.0-dev).

## Contents

- `src/libslic3r/LetterMode/Template.hpp` / `.cpp` — template contract,
  schema `efka.letter-mode-template` v1, required `machine_id`, verbatim ZCCAD
  parameter IDs, `FieldSpec` validation.
- `tests/libslic3r/test_letter_mode_template.cpp` — 8 test cases / 27 assertions.
- `CMakeLists.diff` — the two CMake registration edits.
- `progress.md` — task log and known gaps.

## Status and known gaps

- Tests pass **RED→GREEN standalone** with MSYS2 UCRT64 g++ (18.1 s).
- The full `libslic3r_tests` target never linked: the WSL/Podman builder
  exhausted the 6 GB VM memory cap.
- Not built or tested on macOS/Linux yet. Not production-ready.
- The pre-existing dirty file `scripts/linux.d/debian` in the original worktree
  is user work and is **deliberately excluded** from this package.
- No fork remote exists; `origin` still points at upstream
  `OrcaSlicer/OrcaSlicer`, so this code has not been pushed anywhere.
