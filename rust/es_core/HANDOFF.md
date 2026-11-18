# Handoff: the Rust prototype, from here to a merge

Written 2026-11-16 on host `fartbutt` (user `Loggg`) for an agent continuing
on `DESKTOP-PJS73RO` (user `Owner`) with no access to the conversation that
built this.  Read this file, then [README.md](README.md) (what the port is,
what it measured, the gate), then the repo's `CLAUDE.md`.  The README's
"Before this could merge" list is the authority for WHAT is left; this file
says how to pick it up.

## State

- **economicspace** branch `rust-solver-prototype`, **spacevalue** branch
  `rust-cargo-prototype`.  Both are local commits only (no upstream) unless the
  user has pushed them since; the two machines see them through OneDrive's copy
  of `.git`.  Never work on a branch from both machines at once, never
  `git stash`, and read `git status` with CLAUDE.md's phantom-modification
  rule in mind.
- Nothing on `main` imports any of it.  `ECONOMICSPACE_RUST` unset (the
  default) runs the Python path; `ECONOMICSPACE_RUST=1` swaps in `es_core`
  (sizing loop, programme ladder, solver) and spacevalue's
  `spacevalue_cargo_rs` (knapsack, capped sale), and refuses to import if
  either is missing or is a planted build.
- The default (Python) path also changed on the branch, though no number
  should move: `payload_mix` is formatted for the winner only, and calc reads
  through `_rust_sizing_loop` only in Rust mode.  See "Evidence" below for what
  proves the output unchanged.
- The user's verdict on 2026-11-16: not merged, because the items in the
  README's list are open.  Do not merge to `main` until they are closed; the
  user decides the merge (`gh pr merge` may be refused by the permission
  classifier: hand over the command then).

## Evidence so far (this host only, cislunar only)

- The full gate (`gate/gate_all.sh`) passed 27 of 27 steps on 2026-11-16 at
  commit `1a040af`, every plant caught; e2e catalogs byte-identical
  (`2dab2c78dfb39cbc` benef/search 150 rows, in process and pooled;
  `f4289dfb5177ef59` raw/search 2000).
- That run used the scratchpad copy of the gate.  The repo copy,
  `gate/gate_all.sh` (29 steps: it adds the two check 8 guard steps), and
  `gate/make_workdir.sh` have NOT yet run end to end; only their plants and
  the work-dir checks ran here.  Their first full run is item 1 below: a
  failure there may be the script, not the port.
- verify.py against `main` at `e1fee40`: Python mode passes all 8 checks;
  Rust mode matches on 1 and 3-7 and refuses 8 as designed.  Details in the
  section of that name at the end.

## The gate on DESKTOP-PJS73RO (2026-11-17, item 1 closed)

- `gate/gate_all.sh` at `3a41fa5`, cislunar: **29 of 29 steps OK, bad 0**,
  every plant caught.  Host: python 3.13.9, numpy 2.2.6, pandas 2.3.3, rustc
  1.100.0; `platform_check.py` libm and numpy rows all match the reference
  (pandas `str_dtype` differs, as expected on pandas 2.x).
- Cross-host: `ECONOMICSPACE_RUST=1 verify.py baseline` here gives the four
  hashes in "verify.py against main" below exactly (raw `53b7aa2e987ae8c5`,
  raw+search `3ab1013489eb949f`, benef `0bf60835f283d92a`, benef+search
  `42e9f43b76d344db`).  So the Rust build agrees across the two hosts.
- **The e2e hashes cannot be compared across hosts or days.** `e2e_rust.py`
  hashes the whole CSV, and `catalog_date` is the run's date.  Here they were
  `250f485f4136aef0` (benef/search 150, both pool sizes) and
  `b437969187922396` (raw/search 2000), Python equal to Rust in each.  Compare
  verify.py's cell hashes across hosts instead, since they strip provenance.
- `make_workdir.sh` as first committed could not build `cap_ben.pkl`:
  `preflight()` refuses mars_surface against the copied cislunar Stage 2
  table, and `capture.py` swallows the `SystemExit`, which left a capture of 0
  calls.  It now installs mars_surface's table from the pinned release into
  `WORKDIR/out_mars` and refuses an empty capture.  Captured here: raw 482,631
  calls, benef 1,485,398.
- This host's `python` is the Microsoft Store alias.  The gate scripts call
  `python`, and maturin and PyO3 need a real `python.exe` on PATH, so put the
  interpreter's directory first on PATH (a bash shim is not enough).

## Items 2 and 3 closed on DESKTOP-PJS73RO (2026-11-17, at `cc51d5c`)

- **Item 3, the fallback counters**: Stage 4 now prints one line per
  component (solver, loop, loop knapsack, ladder, cargo) at the end of
  `build_profitability_catalog`, summed over the pool's workers (each chunk
  returns its counter delta), WARNs when a component ran entirely in Python,
  and raises when the ladder's self-check mismatched outside the gate.
  Checked on 40 rows benef/search cislunar: serial and 4 workers give the same
  totals and the same CSV; a planted mismatch raises; an all-fallback ladder
  WARNs.  `verify.py` and the gate's e2e harness silence Stage 4's console, so
  the line does not appear in their logs.
- verify.py at `cc51d5c` against the Rust-mode baseline
  `rust-3a41fa5-desktop`: Python mode ALL CHECKS PASSED (check 1 MATCH on all
  four cells, check 2 MATCH with each pruner off, checks 3-7 clean, check 8
  violations 0 with both plants caught); Rust mode check 1 and 3-7 MATCH,
  check 8 NOT VERIFIED (exit 1, by design).  Python mode matching a Rust-mode
  baseline is a cross-mode result too.
- **Item 2, the gate at three destinations**, each **29 of 29 OK, bad 0**,
  every share 100% Rust, 0 fallbacks, 0 ladder self-check mismatches, e2e
  catalogs byte-identical Python = Rust (hashes are of this day's run only):

  | DEST | e2e 150 benef/search | e2e 2000 raw/search | speed-up 150 serial / 150 pool 4 / 2000 |
  |---|---|---|---|
  | cislunar | `250f485f4136aef0` | `b437969187922396` | 1.50x / 1.25x / 1.33x |
  | geo | `45847d4957f0dfc7` | `3147c3bb413e8cd0` | 1.64x / 1.28x / 1.39x |
  | mars_surface | `65152589ce8ea20a` | `fe7d5980a5858084` | 1.44x / 1.28x / 1.32x |

- Shadow `PATHS`, boil-off loops (shadow_benef / shadow_raw / shadow_dials):
  cislunar 0 / 0 / 562, geo 2067 / 0 / 725, mars_surface 721 / 0 / 2608.  So
  the boil-off path is now exercised in the benef shadow, which cislunar
  never reached.  **`flown_load` is 0 at every destination and in every
  shadow: no gate has exercised that path yet**; a cell that reaches it is
  the remaining coverage gap.
- Setup per destination: a separate work dir (`C:\Users\Owner\es_gate_<D>`),
  that destination's Stage 2 installed into it with
  `run_pipeline.py --stages 2 --destination <D> --output <W>/out --yes`, and
  the two captures copied from the cislunar work dir (they are recorded at
  fixed destinations, raw at cislunar and benef at mars_surface, whatever
  `DEST` is).

## Item 4 closed on DESKTOP-PJS73RO (2026-11-17, at `c036c80`)

- `ProgrammeLadder.run` takes an optional `rung_hook`; calc passes
  `_ES_LADDER_HOOK` (None by default, so nothing is collected).  Once per
  ladder Rust answers, never on a fallback, the hook receives the total of
  every rung Rust priced without calling `_price_programme`, the ones check
  8's `_mission_cost_tail` wrapper cannot see.  Check 8 installs it in Rust
  mode, prints a "Rust ladder:" line per cell, and fails a searched cell whose
  Rust-priced rungs never break the planted floor.
- verify.py at `c036c80`: **Rust mode now passes check 8** (`--skip prune`,
  exit 0; check 1 and 3-7 MATCH as before), and its check 8 counts equal
  Python mode's to the rung on all four cells (raw+search 2,167,749 rungs of
  which 1,722,382 priced in Rust alone; benef+search 13,397,065, of which
  11,849,288).  Python mode `--skip prune parallel`: all checks run passed,
  same counts.
- The gate is now **32 steps** (the two refusal steps are replaced by
  `check8_parity`, `plant_check8_nohook`, `plant_check8_half`,
  `check8_parity_ladder_only` and `plant_planted_hook_defect`, and builds 9
  wheels): **32 of 32 OK, bad 0** at cislunar, e2e hashes as earlier that
  day.  `gate/plants/check8_guard.py` runs check 8 on raw+search 40 and
  benef+search 12 in both modes and holds every count equal.  The thinned
  hook and the `planted_hook_defect` build each PASS check 8 alone and fail
  only parity: that is why parity, not check 8's own blindness test, is the
  gate step.  Python-mode counts are cached in `WORKDIR/check8_py.json` for
  the steps after the first.
- Check 8's hook was not re-run at geo or mars_surface: its cells are
  verify.py's, which are cislunar whatever `DEST` is.

## Setting up the desktop

1. Toolchain (install what is missing; the user allowed installing anything
   needed): rustup stable `x86_64-pc-windows-msvc`, the MSVC Build Tools with
   the Windows SDK, `pip install maturin==1.9.6`.  `cargo --version` from Git
   Bash needs `export PATH="$HOME/.cargo/bin:$PATH"`.
2. Both checkouts next to each other under the GitHub folder, on the branches
   above (es_core's `Cargo.toml` reaches `../../../spacevalue/rust/cargo_core`
   by path; that path is itself an open item).
3. `py platform_check.py` and `py tree_check.py` in economicspace.  A library
   version that differs from `platform_reference.json` is not a defect, but
   record it with the gate result.
4. A work directory OUTSIDE OneDrive, e.g. `C:\Users\Owner\es_gate`:

       bash rust/es_core/gate/make_workdir.sh /c/Users/Owner/es_gate

   It copies Stage 1-3's outputs from `asteroid_pipeline/` (gitignored but in
   the synced folder; if it is missing on the desktop, copy it from this host,
   never regenerate it) and records the two solver captures (~40 min).

## The gate

    bash rust/es_core/gate/gate_all.sh /c/Users/Owner/es_gate > /c/Users/Owner/es_gate/gate_all.log 2>&1

About 75 minutes.  Run it in the background and wait for it to finish; never
run a second Stage 4 process beside it (two over the full catalog ran a 32 GB
host out of memory).  Read the `SUMMARY`: every line `OK`, `bad 0`.  A step
with `want 1` must fail (a plant or a guard refusing).  It reinstalls
`es_core` and `spacevalue_cargo_rs` several times and leaves the good builds
installed.  Never edit `modules/`, `verify.py` or the gate scripts while it
runs: its subprocesses import them as they start.

At another destination: `DEST=geo bash .../make_workdir.sh WORKDIR` names
the command that installs that destination's Stage 2 table into the work dir
(never into `asteroid_pipeline/`); then `DEST=geo bash .../gate_all.sh
WORKDIR`.  Use a separate WORKDIR per destination.

## Order of work (each closes an item in the README's list)

1. **Gate on the desktop** at cislunar.  This is the cross-host question:
   `exp`/`log` come from each host's C runtime, and nothing else has compared
   the two machines' Rust builds.  Compare the e2e hashes with the ones above.
   If they differ, first establish whether the Python legs differ too (a
   host difference, not a port defect: CLAUDE.md's Environment section).
2. (Closed 2026-11-17: geo and mars_surface, above.  `flown_load` still
   unreached.)  **Gate at more destinations**, at least one surface (`earth_surface` or
   `mars_surface`) and `geo`.  Watch the shadow's `PATHS` line for loop paths
   that cislunar never reached.
3. (Closed 2026-11-17 at `5b13784`/`cc51d5c`, gate re-run 29/29.)
   **Print the fallback counters** at the end of Stage 4, summed over
   workers, and make a ladder self-check mismatch outside the gate an error.
   A code change in calc: re-run the gate after it.
4. (Closed 2026-11-17 at `c036c80`, above.)
   **A hook for verify.py check 8 inside the Rust ladder**, so check 8 can
   audit Rust mode instead of refusing.  Its guard plant is
   `gate/plants/check8_guard.py`; update it with the hook.
5. **spacevalue first**: CI building and testing `rust/cargo_core` and
   `cargo_py` (spacevalue's `rust/README.md` lists what that needs), ship
   `spacevalue_cargo_rs` with the package (a wheel or an extra), merge, tag.
   That is a spacevalue release; follow its CLAUDE.md.
6. **Pin es_core's `spacevalue_cargo_core` by git tag**, the tag
   `requirements.txt` pins spacevalue to, with a check holding the two
   together (as `verify_docs.py` check 7 holds the Python pins); decide how
   the `es_core` wheel is built and installed (`_runtime.install()`, the
   requirements files) and wire the gate into CI.
7. **One full campaign cell with `ECONOMICSPACE_RUST=1`**, its hash against
   the archived cell (`campaign/run_cell.py`; read CLAUDE.md's warning about
   it overwriting the archive first: archive with a suffix).
8. **Release notes**: versions.md's Releases and Module changelogs (the
   branch moves no number, so calc's stamp may stay; say so, as the "moved
   without moving a number" table does), and a PR to `main`.

## Gotchas learned building it

- Build outside OneDrive (`CARGO_TARGET_DIR=$HOME/.cargo-target/<name>`);
  inside it maturin fails with "output path is not a writable directory".
- `cargo test --lib` for es_core needs Python's directory on `PATH` (PyO3
  links it); `gate_all.sh` does this.
- A gate that compares Rust with Rust, or Python with Python, passes on
  nothing.  Each comparison in the gate also checks the share that actually
  ran in Rust, and each has a plant proving it fails.  Keep that shape for
  anything you add: plant the failure first.
- The shadow misses a defect in a field a later stage overwrites (the solver
  plant); the replay catches it.  Do not drop either.
- Timing two builds in separate sessions measures the session.  The README's
  "How to price a change" section says how the speed rows were taken.
- Python's stdout is cp1252: print ASCII.  Never `python - <<EOF`; write a
  script file and run it with `< /dev/null`.

## verify.py against main

Run 2026-11-16 on this host, at branch commit `1a040af` (tree clean in the
model paths; only the gate scripts, this file and the README uncommitted).
The baseline was taken from `main` at `e1fee40` (master 1.76.0, calc 1.46.0)
in a separate worktree, provenance "model paths clean", and copied to
`.verify/baseline-main-e1fee40` (gitignored, so it is NOT on the desktop:
take a new one there with `git worktree add <dir> main` and
`py verify.py baseline --tag main-<sha>` inside it).

| cell | hash (baseline = branch) |
|---|---|
| raw | `53b7aa2e987ae8c5` |
| raw+search | `3ab1013489eb949f` |
| benef | `0bf60835f283d92a` |
| benef+search | `42e9f43b76d344db` |

- **Python mode** (`ECONOMICSPACE_RUST` unset), full check: ALL CHECKS
  PASSED, exit 0. Check 1 MATCH on all four cells (151/151 rows each);
  check 2 MATCH with the prune, the combo bound and the rung bound each off;
  checks 3-7 clean; check 8 violations 0 on every cell, its planted floor
  caught.  So the branch moves no number on the default path.
- **Rust mode** (`ECONOMICSPACE_RUST=1`, `--skip prune`): check 1 MATCH on
  all four cells with the same hashes, check 3 MATCH serial and pooled,
  checks 4-7 clean; check 8 printed NOT VERIFIED and the run exited 1.  That
  refusal is the designed behaviour (item 4 of the order below removes it),
  not a failure of the port.  Rust mode was the faster leg: benef+search
  serial 56.4 s against Python's 145.3 s in this one session (a single
  pairing, not a measurement; the README's speed rows are the measured
  ones).
