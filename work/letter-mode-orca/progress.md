# Letter Mode plan — progress

## Task 3: model and template contract — implemented and verified (2026-11-18)

Earlier ruling (kept for the record): Task 3 was paused because the host had no C++ toolchain and
Orca's test suite is CMake/Catch2, so a red-green loop was impossible without a material machine change.

That blocker is gone. MSYS2 is installed at `C:\msys64` with UCRT64 g++ 16.2.0, CMake 4.5.0 and
Ninja 1.13.2 (`C:\msys64\ucrt64\bin` is on the user PATH).

### What was added

- `src/libslic3r/LetterMode/Template.hpp` / `.cpp`
  - pins `TEMPLATE_SCHEMA = "efka.letter-mode-template"` and `TEMPLATE_VERSION = 1`;
  - requires a non-empty `machine_id`, optional `profile_id` pin, and a `parameters` object that
    keeps original ZCCAD IDs and vendor values verbatim;
  - rejects unknown schema, unreadable version, missing/empty identity, mismatched identity pins,
    non-primitive parameter values, and values that contradict a supplied `FieldSpec`
    (boolean/integer/number/enum/text kind, declared unit, established bounds);
  - serialises with `nlohmann::json::dump(2)`, which round-trips doubles at full precision;
  - `save`/`load` are UI-independent.
- `src/libslic3r/CMakeLists.txt`: registers both files (after `LayOnFace.*`).
- `tests/libslic3r/test_letter_mode_template.cpp`: 8 test cases / 27 assertions;
  `tests/libslic3r/CMakeLists.txt` registers the test next to `test_instance_lock.cpp`.

### Evidence

- RED: compiling the test alone failed only on `libslic3r/LetterMode/Template.hpp: No such file`.
- GREEN: standalone Catch2 build with `g++.exe -std=c++17`
  (sources: test + `catch_amalgamated.cpp` + `Template.cpp`) → `All tests passed (27 assertions in 8 test cases)`
  in 18.1 s. Compile command uses `-I src -I deps_src -I tests/catch2/extras` plus a throwaway
  `catch2/catch_test_macros.hpp` shim that forwards to `catch_amalgamated.hpp`; the repository test
  file itself still uses the modular Catch2 header the real build expects.
- Not verified: the full `libslic3r_tests` CMake target. A build attempt inside the existing WSL
  podman builder hit the VM's memory cap, froze the distro (`Wsl/Service/0x8007274c`) and had to be
  terminated. The WSL VM is now capped at 6 GB / 2 GB swap and is used for 9Router only; heavy
  parallel Orca builds are not viable on this 15.7 GB host.

### Known gaps carried forward

- `FieldSpec` is a mechanism, not vendor data. No ZCCAD range, unit or enum table has been declared
  yet; those must come from `docs/re/zccad-parameter-map.csv` once its duplicated header columns are
  cleaned, and only for rows with real evidence.
- The WSL clone `/home/efka/OrcaSlicer-LetterMode-build` received the same three files for future
  build work, but the authoritative branch remains the Windows worktree
  `.worktrees/letter-mode` (`feat/letter-mode-ui`, still uncommitted).
