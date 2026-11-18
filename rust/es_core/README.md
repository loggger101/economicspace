# es_core: opt-in Rust for Stage 4 (prototype)

**Status:** a prototype on branch `rust-solver-prototype`. Not merged and not
used by default. Nothing changes unless `ECONOMICSPACE_RUST=1` is set.

## What it ports

1. **`max_return_payload_kg`**, the closed-form return-mission solver
   (`es_core.Solver`). It is called millions of times per run.
2. **The coupled sizing loop** inside `_evaluate_combo_at_ratio`: the
   `while passes < pass_limit:` fixed point over plant, EP stage, refinery,
   ISRU feed, stay and containment (`es_core.SizingLoop`, `src/sizing.rs`).
   Rust runs the whole loop in one crossing per candidate and hands back
   what the loop would leave behind. Everything before the loop (its
   inputs) and after it (the settle-up, pricing and programme search) stays
   Python.
3. **The programme / fleet ladder** in `_evaluate_combo_at_ratio`
   (`es_core.ProgrammeLadder`, `src/ladder.rs`): the walk over rungs
   `(n_missions, fleet, wave)` that prices each with
   `_price_programme(full=False)` and keeps the best `_objective_key`. Rust
   returns only the CHOICE `(best_n, best_f, best_w, priced_count)`; calc.py
   then re-prices the winner in full exactly as it always does, so every
   number in the row is still Python's. `_mission_cost_tail(totals_only=True)`
   is ported line for line. The memoised helpers (calendar, learning curve,
   mining reliability, fleet refinement) are called back. A rung whose market
   answer is not trivial (elasticity, or a capacity ceiling that binds and
   survives the incumbent bound) is priced by calling Python's
   `_price_programme` itself, and Rust's own `total_cost` for that rung must
   equal Python's bit for bit, or the whole ladder falls back. Single-programme
   searches (`single`) are not routed through it. The memoised helpers'
   answers are kept ACROSS ladders too (a shared memo in the
   `ProgrammeLadder`): each is a pure function of its arguments, so the float
   Python returned for a key is the answer for it. Keys are float bit
   patterns, used only for non-zero, non-NaN exact floats, where bit equality
   is Python's cache equality; anything else asks Python as before.
4. **The knapsack inside the sizing loop** (`_hold_refining`, and
   `_cargo_water_kg`'s concentrating branch). This port lives in
   **spacevalue**, which owns the knapsack: its `rust/cargo_core` crate, on
   spacevalue's branch `rust-cargo-prototype`, held there to the golden
   fixture and a fuzz against the Python by `tests/test_cargo_rust.py`.
   es_core links that crate directly, so the loop no longer calls back into
   Python for it. calc.py passes `cargo=(refinery, phases, recovery)`, the
   same three objects its two callbacks close over; if they do not read
   exactly, the callbacks still answer.
5. **The knapsack calls calc.py makes from Python** (outside the loop): every
   `_capped_sale_value` (the capped rungs the ladder hands to
   `_price_programme`) and every `_hold_refining` on a knapsack hold (the
   containment and plant settles, repairs). calc.py rebinds both names to
   spacevalue's own Python extension, `spacevalue_cargo_rs` (the same crate,
   which falls back to spacevalue's Python on any input it cannot reproduce
   exactly). A raw hold stays Python: it is one multiply, cheaper than the
   crossing (`_rust_cargo` in calc.py says which goes where).

The loop can end five ways, and calc.py takes each exactly as the Python
loop would:

| kind | the Python loop's | calc.py then |
|---|---|---|
| 0 FALLBACK | (not a case Rust reproduces exactly) | runs its own loop, untouched |
| 1 REFUSE | `return None` | returns None |
| 2 DONE | converged, or out of passes | assigns the state, skips its loop |
| 3 REFIT_FEED | `return _refit_to_feed_budget(...)` | assigns the state, makes that call |
| 4 REFIT_PLANT | `return _refit_to_plant_ceiling(...)` | assigns the state, makes that call |

The refits recurse into `_evaluate_combo_at_ratio`, so Python makes them.
The knapsack calls inside the loop (beneficiated cargo water and the refinery
hold) are answered in Rust (item 4); the Python callbacks remain for an input
the crate cannot read exactly.

The ladder returns kind 0 FALLBACK (calc.py runs its own ladder, untouched)
or kind 2 DONE with the choice.

## The contract: bit-identity, not "close enough"

Both objects return what the Python returns:

- the same keys in the same order;
- the same value types (the refusal cascade's masses are Python `int` 0);
- the same floats, compared as bit patterns;
- the same exceptions;
- the same locals, assigned or unassigned, for the loop.

Anything the Rust path cannot be sure of goes back to Python untouched:

- numpy scalars, ints past 2⁵³, or bools in float slots;
- an int where the value could be carried into the state unchanged (an int
  there would be a different Python type);
- a division by zero, an `exp` overflow, or a `log` of a non-positive
  number (Python raises; Rust would not);
- a callback returning anything other than the exact types;
- any NaN in the answer. NaN sign is not portable: LLVM may commute
  `a + b`, and on x86 the NaN that survives depends on operand order. In
  the ladder a NaN key also falls back, because CPython compares tuples
  holding NaN by object identity first;
- for the ladder, a self-check mismatch on any rung Python priced.

## Measured (2026-11-15 and 2026-11-16, this host, calc 1.46.0)

| check | result |
|---|---|
| `exp` bitwise vs `math.exp` | 5,331,256 exponents, 0 mismatches |
| `log` bitwise vs `math.log` | 2,200,006 arguments, 0 mismatches |
| solver replay of captured real calls (cislunar raw 150 rows + benef/search 60 rows) | 1,565,623 calls, 0 mismatches |
| solver hostile fuzz | 300,000 calls, 0 mismatches |
| solver plant (one ulp in `m_tank_outbound`) | caught by replay and fuzz |
| loop shadow, cislunar raw, 100 rows | 51,404 calls, 0 mismatches, 100% of loops in Rust |
| loop shadow, cislunar benef/search, 40 rows | 238,570 calls, 0 mismatches, 100% of loops in Rust |
| loop shadow, cislunar benef/search, 120 rows | 541,536 calls, 0 mismatches; refuse, done, both refits, damped, non-converged, relax, ISRU, electric, RTG, refinery, payload cap all exercised |
| loop shadow, raw, pre-filter and combo bound off, 25 rows | 133,228 calls, 0 mismatches; boil-off on 22,640 |
| loop shadow, benef/search, pre-filter off, `size_ep_on_flown_load=True`, 8 rows | 154,551 calls, 0 mismatches; flown-load sizing on all |
| loop plant (one ulp in the damping blend) | caught by the shadow |
| ladder, audited shadow, benef/search, 40 rows | 238,570 calls, 0 mismatches; 132,766 ladders, all in Rust; 4,523,214 rungs settled in Rust, 280,140 priced by Python, 506,980 bound-skipped; 0 self-check mismatches |
| ladder, audited shadow, `model_reliability=True`, 12 rows | 83,834 calls, 0 mismatches, 0 self-check mismatches |
| ladder, audited shadow, `apply_wacc_compounding` and `model_learning_curve` on, 12 rows | 177,133 calls, 0 mismatches, 0 self-check mismatches |
| ladder, audited shadow, `market_model='elasticity'`, 12 rows | 47,440 calls, 0 mismatches; every rung priced by Python (elasticity is always a callback), so correct but no faster |
| ladder, audited shadow, raw/search, 60 rows | 21,152 calls, 0 mismatches, 0 self-check mismatches |
| ladder, audited shadow, `selection_objective='profit'`, 12 rows | 129,285 calls, 0 mismatches, 0 self-check mismatches |
| ladder plant (one ulp in a rung's `total_cost`) | caught by the self-check (17,471 rungs), not by the result comparison |
| knapsack in the loop, shadow, benef/search, 40 rows | 238,570 calls, 0 mismatches; the knapsack answered in Rust in 100% of sizing loops |
| knapsack in the loop, shadow, raw/search, 60 rows | 21,152 calls, 0 mismatches |
| knapsack in the loop, shadow, `model_refinery=False`, 12 rows | 72,761 calls, 0 mismatches |
| knapsack in the loop, shadow, `model_detailed_phases=False`, 12 rows | 64,257 calls, 0 mismatches |
| knapsack plant (`planted_knapsack_defect`, spacevalue's feature: one ulp in every take) | caught by the shadow (1,990 mismatches) |
| e2e catalogs, benef/search, 150 rows, 1 worker | byte-identical (Python/Rust/Python), before and after the ladder port |
| e2e catalogs, raw, 2,000 rows, 1 worker | byte-identical; with the ladder, also raw/search 2,000 rows |
| e2e catalogs, benef/search, 400 rows, 4-worker spawn pool | byte-identical, before and after the ladder port (the first attempt ran out of memory reading the catalog while a shadow ran alongside; rerun alone) |
| e2e catalogs with the knapsack in Rust: benef/search 150 rows, benef/search 400 rows over 4 workers, raw/search 2,000 rows | byte-identical, the same hashes as every run above |
| e2e catalogs with calc's own cargo calls in Rust too (item 5): benef/search 150 rows, benef/search 400 rows over 4 workers, raw/search 2,000 rows | byte-identical; whole Stage 4 runs 1.70x, 1.36x and 1.32x (one run each, so read them as levels, not as this change's share) |
| guards: `=yes`, planted build, extension missing | each raises at import |

**Speed**, `bench_rust.py`: the search only, Python and Rust alternating on
every asteroid in one process, with every result also compared:

| sample | ported | Python | Rust | speed-up |
|---|---|---|---|---|
| cislunar raw, no search, 300 rows | solver + loop | 18.3 ms/asteroid | 11.4 ms/asteroid | 1.59x |
| cislunar benef/search, 60 rows | solver + loop | 289.8 ms/asteroid | 215.1 ms/asteroid | 1.35x |
| cislunar raw, no search, 300 rows | + ladder | 41.0 ms/asteroid | 25.2 ms/asteroid | 1.63x |
| cislunar benef/search, 60 rows | + ladder | 575.5 ms/asteroid | 319.5 ms/asteroid | 1.80x |
| cislunar raw, no search, 300 rows | + knapsack | 21.8 ms/asteroid | 13.8 ms/asteroid | 1.57x |
| cislunar benef/search, 60 rows | + knapsack | 335.6 ms/asteroid | 157.3 ms/asteroid | 2.13x |

The pairs of rows were taken in different sessions and the machine was
busier for the later ones: compare the speed-up within a row, never a Python
column across rows. A raw run without search never builds a ladder (one
programme), so its later rows measure the solver and loop again. Whole
Stage 4 runs (`e2e_rust.py`, loading included) gained 1.31x on
benef/search 150 rows, 1.27x on benef/search 400 rows over 4 workers, and
1.21x on raw/search 2,000 rows. With the knapsack: 1.36x, 1.55x and 1.22x.
A raw hold never runs the knapsack, so raw gains nothing from it.

The solver alone gave no measurable gain per run, because at about 1.3 us a
call the Python boundary costs more than the arithmetic. The loop crosses
once per candidate and pays. What Python is left after the later ports is
in the profile under "Where the time goes now".

**Do not size the next port from cProfile.** It charged the loop's callees
about 70 s of 116 s. The interleaved benchmark says the loop and solver
together were worth much less: per-call profiling inflates functions called
millions of times. Size a port with `bench_rust.py` (whole asteroids,
interleaved) and a small change with per-call paired timing (see "How to
price a change").

## Where the time goes now (2026-11-16, Rust mode, cislunar)

`sample_profile.py` (a stack sampler, ~1 ms, no per-call overhead) and
`analyse_profile.py`. Shares are of search time, i.e. samples inside
`evaluate_asteroid`. The sampler is trusted because it predicts the
measured speed-up: the loop is 40.9% of search in Python mode and 14.7% in
Rust mode, which implies 1.44x against `bench_rust.py`'s measured 1.35x.
It misreads one thing: a line Rust calls back into reads high, because
Rust's own time is charged to it (see "How to price a change").

With everything in "What it ports" on (benef/search 60 rows, raw/search 400
rows), by section of `_evaluate_combo_at_ratio`:

| section | benef/search | raw/search |
|---|---|---|
| the Rust ladder call | ~35% | ~29% |
| settling the power plant against the mission flown | ~16% | ~10% |
| the Rust sizing loop call | ~12% | ~8% |
| capped rungs the ladder hands back to Python (`_price_programme`, `_mission_cost_tail`) | ~4% (~7% with the callback line) | ~3% (~5%) |

On raw cells the pre-filter and combo bound are the largest Python cost
left: `_closes_carrying_its_own_stage`, `_pass1_cascade` and
`_combo_key_bound` are ~18% of search by self time (~3% on benef). Both
are listed under "Open candidates" below.

How the profile moved, port by port (benef/search 60 rows unless named;
each figure is the one that chose the next port):

1. Before any loop work: programme pricing ~55% of search (the ladder);
   on raw, no search, 300 rows, the pre-filter and combo bound ~23%.
   Repairs (`_refit_to_plant_ceiling`, re-solving a whole candidate) were
   ~31% inclusive: an algorithmic cost a port speeds up but cannot remove.
2. After the ladder port: the knapsack was the largest Python cost left,
   `_hold_refining` 22% inclusive and `optimal_payload_mix` 16%.
3. After the knapsack port (item 4): the Rust ladder call ~51% by section,
   the plant settle ~16%, the result dict ~6%, `selection_key` ~5%; the
   knapsack calls calc made from Python were then routed to Rust (item 5).

Two cautions for anyone timing a sample:
- On a 300-row raw run, search was 13% of wall time; the rest was loading
  the 1.58 M-row catalog. A small run's wall clock measures the loader. On
  a full cell (hours) the search dominates.
- The beneficiated + search cells are the expensive ones (the campaign's
  longest), so their profile is the one to port against.

## How to price a change (and how not to)

Three measurements of the same change, the ladder memo below, gave 10.1%,
0.8% and 2.3%. Only the last was right, and the way each went wrong is the
lesson.

- **The sampler, 10.1%.** It charged that much of beneficiated search to one
  line, the ladder's `learning=` callback. Most of it was Rust's own ladder
  time charged to the last Python frame Rust had called back into. A line
  Rust calls back into reads high; the Rust dispatch line reads low.
- **A whole-asteroid A/B, 0.8%.** Rust with the memo against Rust without,
  alternating per asteroid. Per-asteroid timing noise on this host is
  +/-2-5%: an A/A control (identical arms) "saved" 2.7% +/- 2.4%, and two
  runs of the same A/B gave -5.1% and +4.7%. One run of it decides nothing.
- **Per-call paired timing, 2.3%.** Each call of the thing that changed
  (here `ProgrammeLadder.run`) is made twice on the same inputs, once per
  arm, order alternating, results compared; the savings are summed against
  the search time with the duplicates taken out. Over 41,649 ladders it
  measured 2.44% +/- 0.08% and, rerun, 2.13% +/- 0.07%. This is the method.
The paired-timing harnesses used here were one-off scripts and are not
committed: write one per change (it wraps the changed call, runs both arms on
the same arguments, and fails on any differing result).

The same profile charged ~15% to the two lines that enter a repair
(`return _evaluate_combo_at_ratio(...)` and `return
_refit_to_plant_ceiling(...)`). `sys.monitoring` on the evaluator measured
the frame itself: entering costs 2.8 us and tearing down 6.1 us per call
(123,577 calls; a 220-local, 64-cell frame), together ~7-9% of Rust-mode
search. That is real, and only a port of the evaluator itself removes it.
Garbage collection is not it: with the collector off, alternating per
asteroid, the time did not move and no collection ran.

## Small changes, measured (2026-11-15 and 2026-11-16, per-call paired timing)

| change | gate | saving (share of Rust-mode search) | verdict |
|---|---|---|---|
| ladder: remember `learning`, `calendar` and `mining_rel` ACROSS calls (`ProgrammeLadder`'s shared memo, keyed on Python's own cache equality; `memo=False` turns it off for measuring) | audited shadow (default, and reliability + WACC + learning), 0 mismatches; `planted_memo_defect` (one ulp on memo hits) caught by the rung self-check | benef/search 2.44% +/- 0.08%, rerun 2.13% +/- 0.07%; reliability + WACC + learning 5.81% +/- 0.07%; raw/search 1.45% +/- 0.17% | **kept** |
| `payload_mix` formatted only for the winner (calc.py: `_format_payload_mix` in `evaluate_asteroid`), not for every candidate | e2e catalogs byte-identical in all three runs, Python legs included (the default path changed too) | 103,658 discarded strings at 6.2 us: 2.7% of benef/search; 0.07% raw | **kept** |
| calc's Python-side `_capped_sale_value` and knapsack `_hold_refining` answered by `spacevalue_cargo_rs` (item 5 above) | shadow (benef/search 40, raw/search 60, reliability + WACC + learning 12), 0 mismatches; spacevalue's `planted_knapsack_defect` build caught (21,789 and 163 mismatching calls); e2e: see Measured | `_capped_sale_value` 3.42% +/- 0.02% of benef/search, 6.91% +/- 0.03% of raw/search; `_hold_refining` 1.70% benef, but 1.14% SLOWER on raw holds, hence knapsack holds only; `optimal_payload_mix` 0.07%, not routed | **kept** |
| keyword reading: `SizingLoop.run` finds each name's slot with one `match` (`slot`, generated from `F_NAMES`, `F_INT_OK` and `B_NAMES`) instead of a linear search of each table; `ProgrammeLadder.run` reads into a fixed array (`run_input`, generated from `RUN_REQUIRED` and `RUN_OPTIONAL`) instead of a per-call `HashMap` of owned strings | the full gate, 27 steps, every plant caught; `slot_matches_tables` and `run_input_matches_tables` hold each generated match to its tables (each failed on a planted mismatch) | reading cost per call 2.0-2.5 to 0.8-1.2 us (loop) and 3.0-3.5 to 0.6-0.9 us (ladder); at the bench's 41,065 loops and 14,273 ladders that is about 0.07-0.11 s of 8.5 s, ~1% of benef/search | **kept** for the simpler code (no per-call allocation, no hand-kept name lists to drift); under the bar as a speed-up |
| `Solver.viable(**kw)` for the pre-filter, skipping the 18-key result dict (built, measured, then removed) | 1,665,623 calls (1,565,623 captured + 100,000 fuzzed), 0 mismatches; plant caught | benef/search 0.17%; raw 1.59% +/- 0.12%; raw/search 1.33% +/- 0.05% | declined: under CLAUDE.md's ~2% bar everywhere |
| remembering a combo's ratio solves inside `evaluate_combo` (the same ratio solved twice) | counted, not built | 6 repeats in 48,241 solves (0.01%) | declined: there is almost nothing to remember |
| sharing pass 1, the EP stage floor and the second solve between the pre-filter (`_closes_carrying_its_own_stage`) and the combo bound (`_combo_key_bound`) | not built | sampler estimate ~0.5% of benef/search, ~1.5-3% of raw (not measured per call) | declined as an easy win: under the bar on the expensive cells, and it changes what the bound's admissibility proof reads (CLAUDE.md: a change to pass 1's inputs re-proves the bound) |

### Open candidates (sized by the sampler only, not built)

Each is above the ~2% bar on the sampler's figure, and each is a real port
rather than an easy win. Measure one per call (the method above) before
starting it.

- **Price the ladder's capped rungs in `ladder.rs`.** The capacity branch of
  `_price_programme` (window or wave clock, `_capped_sale_value`, the
  reshaped knapsack with caps) and `_mission_cost_tail`, using
  `spacevalue_cargo_core`, which es_core already links, rather than calling
  back through Python. ~4% of benef search and ~3% of raw, at most ~7% and
  ~5%. It touches the rung
  ceiling's proof: check 8 audits every capped sale, and a change to the
  capacity branch re-proves `_rung_gross_ceiling`.
- **Port the raw pre-filter and combo bound** (`_closes_carrying_its_own_stage`,
  `_pass1_cascade`, `_combo_key_bound`): ~18% of raw search, ~3% of benef.
  The bound is admissible by a term-by-term proof, and `verify.py` check 8
  must catch a planted floor on the Rust bound before it can be trusted.

## Build

You need rustup (stable, `x86_64-pc-windows-msvc`), the MSVC Build Tools
with the Windows SDK, and `pip install maturin==1.9.6`. Build outside
OneDrive: inside the synced folder, build scripts fail with "output path is
not a writable directory", and the folder would sync gigabytes.

    export CARGO_TARGET_DIR="$HOME/.cargo-target/es_core"
    cd rust/es_core
    python -m maturin build --release -o dist
    python -m pip install --force-reinstall --no-deps dist/es_core-*.whl

The planted copies, which only the gate uses:

    python -m maturin build --release --features planted_defect -o dist-plant
    python -m maturin build --release --features planted_loop_defect -o dist-plantloop
    python -m maturin build --release --features planted_ladder_defect -o dist-plantladder
    python -m maturin build --release --features planted_memo_defect -o dist-plantmemo
    python -m maturin build --release --features planted_knapsack_defect -o dist-plantknap

es_core needs spacevalue checked out next to economicspace, on the branch
`rust-cargo-prototype` (`Cargo.toml` reaches `../../../spacevalue/rust/cargo_core`).
Rust mode also needs spacevalue's Python extension, built there:

    export CARGO_TARGET_DIR="$HOME/.cargo-target/spacevalue_cargo"
    cd ../../../spacevalue/rust/cargo_py     # from rust/es_core
    python -m maturin build --release -o dist
    python -m pip install --force-reinstall --no-deps dist/spacevalue_cargo_rs-*.whl

and its planted copy, for the gate, with `--features planted_knapsack_defect`.

## The gate (all of it must pass, and the plants must be caught)

`gate/gate_all.sh WORKDIR` runs all of it in order: it builds the good and
planted wheels, runs every row below, and swaps the builds in and out. It
ends with a summary of each step's exit code against what it must be.
`gate/make_workdir.sh WORKDIR` prepares the work directory (a copy of Stage
1-3's outputs and the two captures). The plants that are not cargo features
live in `gate/plants/`. [HANDOFF.md](HANDOFF.md) says how to run it on
another host.

| tool | checks | needs |
|---|---|---|
| `capture.py` | records every real solver call in a sample run | Stage 1-3 outputs in a scratch dir |
| `verify_rust.py --capture *.pkl` | `exp` and `log` bitwise; solver replay; 300k hostile fuzz; fast-path share of the replay alone | the captures |
| `verify_rust.py --expect-defect` | the `planted_defect` build is CAUGHT | that build installed |
| `shadow_rust.py OUT ROWS ...` | every `_evaluate_combo_at_ratio` call, including each recursive repair, computed all-Python and all-Rust and compared recursively, bit for bit; every solver call outside it (pre-filter, combo bound) answered by both solvers and compared; the ladder in audit mode; the Rust share of each path that ran (loop, ladder, in-loop knapsack evaluations, calc's cargo calls) | a scratch output dir |
| `shadow_rust.py --expect-defect` | the `planted_defect`, `planted_loop_defect`, `planted_ladder_defect`, `planted_memo_defect` and `planted_knapsack_defect` builds are each CAUGHT | that build installed |
| `shadow_rust.py OUT ROWS ...` with spacevalue's planted `spacevalue_cargo_rs` installed | VERDICT FAIL, with mismatches (the shadow swaps calc's cargo calls per mode too) | that build installed |
| `shadow_rust.py --set field=value ...` | the same, with a `CalcConfig` dial set for the run, to reach paths the defaults never take | |
| `e2e_rust.py OUT ROWS WORKERS ...` | Stage 4 run Python, Rust, Python: `profitability_catalog.csv` byte-identical, in-process and through the pool; the catalog is deleted before each run and a run that writes none fails | a scratch output dir |
| `bench_rust.py OUT ROWS ...` | timing only, but every asteroid's two results are also compared; Rust mode is everything `ECONOMICSPACE_RUST=1` turns on (since 2026-11-16 including calc's cargo calls, item 5; the speed rows above were taken without them) | a scratch output dir |
| `cargo test --release --lib` in `rust/es_core` | each generated keyword `match` (`slot`, `run_input`) agrees with the name tables it was generated from, both ways | the Python directory on `PATH` (PyO3 links it) |
| `sample_profile.py [--rust] OUT ROWS STACKS.txt ...`, then `analyse_profile.py STACKS.txt` | where search time goes; sizes the next port | a scratch output dir |

`verify_rust.py`, `shadow_rust.py` and `bench_rust.py` compare results
through one rule, `bitsame.py`: same type, same keys in order, floats and
numpy scalars equal as bit patterns, recursively (its `__main__` is a
self-check of the edge cases: NaN, -0.0, int against float, key order).

**The two plants need different gates, and that is the point of having
both.** The shadow compares final results, and it MISSED the solver plant:
that one-ulp error lands on the in-loop cascade's `m_tank_outbound`, which
the settle-up after the loop recomputes, so it never reaches a result. The
solver replay compares the solver's own output and catches it. A field a
later stage overwrites is invisible to an end-to-end check. (Since the
review of 2026-11-16 the shadow also compares every solver call made
outside the evaluator, by the pre-filter and the combo bound, where the
solver's whole output is read; it now catches this plant too, 38,298 of
63,039 such calls on benef/search 40 rows. The replay stays the gate that
compares every field.)

**The ladder plant taught the same lesson a third time.** It flips one ulp of
a rung's `total_cost`. The result comparison missed it: a one-ulp drift
almost never changes which rung wins, and the winner is re-priced by Python
anyway. The ladder's own self-check (every rung Python priced, Rust's total
held to Python's) caught it, 17,471 times on the sample. So the shadow builds
the ladder with `ProgrammeLadder(audit=True)`, which also prices every rung
Rust settled alone through Python and compares `total_cost` and `g` bit for
bit, and the shadow fails on any self-check mismatch. Audit mode is for the
gate only: it does the Python work it exists to skip.

With `ECONOMICSPACE_RUST=1`, `calc.py` refuses to start when either
extension is a planted build or is missing (unset, it imports neither). The shadow and the benchmark
build their Rust objects themselves rather than through that guard, so no
bypass lives in calc.py.

## Before this could merge (not done)

[HANDOFF.md](HANDOFF.md) puts these in the order to do them.

- Run the gate on `DESKTOP-PJS73RO`. `platform_check.py` proves numpy
  parity between hosts, not that the C runtime's `exp` and `log` match.
- Run the gate at the other destinations. So far it has run on cislunar
  only, because the scratch directory holds cislunar Stage 2 prices. Every
  loop path has been reached there (the shadow's `PATHS` line counts them),
  boil-off and flown-load sizing only with dials set for the purpose.
- Don't run gate jobs side by side. Two Stage 4 processes reading the
  1.58 M-row catalog at once ran this host out of memory.
- Wire the gate into `verify.py` and CI; decide how the wheel is pinned and
  installed (`_runtime.install()`, the requirements files).
- Run one full campaign cell with `ECONOMICSPACE_RUST=1` and compare its hash
  with the archived cell.
- Pin `spacevalue_cargo_core` by git tag, the same tag as the spacevalue pin
  in `requirements.txt`, with a check holding the two together (as check 7
  holds the Python pins). Today it is a path into the sibling checkout, which
  only this machine has.
- Ship `spacevalue_cargo_rs` with spacevalue (one wheel, or an extra) so
  Rust mode does not need a second hand-built extension, and pin it with the
  same tag.
- Merge spacevalue's `rust-cargo-prototype` first, with CI building and
  testing the crate there (its `rust/README.md` lists what that needs).
- Port further only with a measured case. A profile names candidates; an
  A/B in one process (or a call count times a per-call saving) prices them.
  Not cProfile, and not the sampler's share for a line Rust calls back into.
  What is left is mostly the body of `_evaluate_combo_at_ratio` (plant
  settle, cascade rebuild, final pricing, the result dict, repairs): a port
  of the evaluator, not another piece of it.
- (Done 2026-11-17.) Report fallbacks from production runs: Stage 4 now
  prints each counter (Solver, SizingLoop, ProgrammeLadder,
  `spacevalue_cargo_rs`) at its end, summed over the pool's workers, WARNs on
  a component that ran entirely in Python, and raises on a ladder self-check
  mismatch outside the gate.
- (Done 2026-11-17.) `verify.py` check 8 (the combo and rung bounds) wraps
  `_mission_cost_tail`, which the Rust ladder bypasses for the rungs it prices
  itself. The ladder now hands those totals to `calc._ES_LADDER_HOOK`
  (`rung_hook`, once per ladder it answers, never on a fallback), check 8
  installs it in Rust mode, and a searched cell whose Rust-priced rungs never
  break the planted floor fails as blind. The gate's `check8_guard.py` holds
  every check 8 count in Rust mode to Python mode's exactly; dropping the
  hook, thinning it, and the `planted_hook_defect` build each fail it.
- Two edges a later change could make real (review of 2026-11-16, neither
  reachable today): calc's `_rust_cargo` wrapper tests `phases` for truth
  before `_hold_refining` would have returned on `payload_kg <= 0`, so a
  numpy-array `phases` would raise where Python returns (calc passes a list);
  and the ladder's shared memo answers `learning`, `calendar` and
  `mining_rel` without calling back, so a harness that monkeypatched one of
  those cached functions mid-process would get stale answers (none does).
- The ladder's port of `_mission_cost_tail` is a second copy of a cost model
  that releases change. A calc release touching the tail, the prologue tuple's
  order or the rung bound must re-run the audited shadow, or the Rust ladder
  will silently fall back (self-check) or, worse, agree on a sample and
  differ elsewhere.
