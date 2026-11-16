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
   searches (`single`) are not routed through it.
4. **The knapsack inside the sizing loop** (`_hold_refining`, and
   `_cargo_water_kg`'s concentrating branch). This port lives in
   **spacevalue**, which owns the knapsack: its `rust/cargo_core` crate, on
   spacevalue's branch `rust-cargo-prototype`, held there to the golden
   fixture and a fuzz against the Python by `tests/test_cargo_rust.py`.
   es_core links that crate directly, so the loop no longer calls back into
   Python for it. calc.py passes `cargo=(refinery, phases, recovery)`, the
   same three objects its two callbacks close over; if they do not read
   exactly, the callbacks still answer.

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
hold) are callbacks into the same Python functions.

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

## Measured (2026-11-15, this host, calc 1.46.0)

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

The two pairs of rows were taken in different sessions and the machine was
busier for the second: compare the speed-up within a row, never a Python
column across rows. A raw run without search never builds a ladder (one
programme), so its second row measures the solver and loop again. Whole
Stage 4 runs (`e2e_rust.py`, loading included) gained 1.31x on
benef/search 150 rows, 1.27x on benef/search 400 rows over 4 workers, and
1.21x on raw/search 2,000 rows. With the knapsack: 1.36x, 1.55x and 1.22x.
A raw hold never runs the knapsack, so raw gains nothing from it.

The solver alone gave no measurable gain per run, because at about 1.3 us a
call the Python boundary costs more than the arithmetic. The loop crosses
once per candidate and pays. What remains is the Python around the loop
(programme pricing, the knapsack, mission cost) and in `evaluate_combo`.

**Do not size the next port from cProfile.** It charged the loop's callees
about 70 s of 116 s. The interleaved benchmark says the loop and solver
together were worth much less: per-call profiling inflates functions called
millions of times. Measure with `bench_rust.py`.

## Where the time goes now (2026-11-15, Rust mode, cislunar)

`sample_profile.py` (a stack sampler, ~1 ms, no per-call overhead) and
`analyse_profile.py`. Shares are of search time, i.e. samples inside
`evaluate_asteroid`. The sampler is trusted because it predicts the
measured speed-up: the loop is 40.9% of search in Python mode and 14.7% in
Rust mode, which implies 1.44x against `bench_rust.py`'s measured 1.35x.

| beneficiated + search, 60 rows | share of search |
|---|---|
| programme / fleet ladder in `_evaluate_combo_at_ratio`: `_price_programme` per rung (34% inclusive), `_mission_cost_tail` (13% self), `_objective_key` (6%), `_capped_sale_value` (3%) | ~55% |
| the Rust sizing loop call, including its knapsack callbacks | ~15% |
| settling the power plant against the mission flown | ~12% |
| everything else (containment settle, market saturation, cost prologue, delivered $/kg) | under ~10% together |
| the knapsack, `spacevalue.cargo.optimal_payload_mix`, across all of the above | ~12% inclusive |
| repairs re-solving a whole candidate, `_refit_to_plant_ceiling` | ~31% inclusive (an algorithmic cost; a port speeds it up but does not remove it) |

| raw, no search, 300 rows | share of search |
|---|---|
| pre-filter and combo bound (`_closes_carrying_its_own_stage`, `_combo_key_bound`) | ~23% |
| programme ladder and pricing | ~23% |
| settling the power plant | ~15% |
| the Rust sizing loop call | ~11% |
| `evaluate_asteroid`'s own work | ~8% |

Two cautions for anyone timing a sample:
- On a 300-row raw run, search was 13% of wall time; the rest was loading
  the 1.58 M-row catalog. A small run's wall clock measures the loader. On
  a full cell (hours) the search dominates.
- The beneficiated + search cells are the expensive ones (the campaign's
  longest), so their profile is the one to port against.

That profile sized the ladder port: programme pricing was ~55% of
beneficiated search. It is now ported (see the 1.80x row above).

**After the ladder port** (benef/search, 60 rows, Rust mode, same tools):

| section | share of search |
|---|---|
| the Rust ladder call, including the rungs it hands back to `_price_programme` (11% inclusive) and `_capped_sale_value` (5%) | ~33% |
| the Rust sizing loop call, including its knapsack callbacks | ~30% |
| settling the power plant | ~9% |
| containment settle, market saturation, cost prologue, delivered $/kg | ~3% each |
| the knapsack across all of the above: `_hold_refining` (22% inclusive), `optimal_payload_mix` (16%) | the largest Python cost left |
| repairs, `_refit_to_plant_ceiling` | ~28% inclusive |

That profile pointed at the knapsack, which is now ported inside the sizing
loop (see item 4 under "What it ports"). The knapsack calls still made from
Python (the plant settle after the loop, repairs, and the capped rungs the
ladder hands to `_price_programme`) still run the Python. Profile again
before choosing the next port.

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
    python -m maturin build --release --features planted_knapsack_defect -o dist-plantknap

es_core needs spacevalue checked out next to economicspace, on the branch
`rust-cargo-prototype` (`Cargo.toml` reaches `../../../spacevalue/rust/cargo_core`).

## The gate (all of it must pass, and the plants must be caught)

| tool | checks | needs |
|---|---|---|
| `capture.py` | records every real solver call in a sample run | Stage 1-3 outputs in a scratch dir |
| `verify_rust.py --capture *.pkl` | `exp` and `log` bitwise; solver replay; 300k hostile fuzz; fast-path share | the captures |
| `verify_rust.py --expect-defect` | the `planted_defect` build is CAUGHT | that build installed |
| `shadow_rust.py OUT ROWS ...` | every `_evaluate_combo_at_ratio` call, including each recursive repair, computed all-Python and all-Rust and compared recursively, bit for bit; loop and ladder share; the ladder in audit mode | a scratch output dir |
| `shadow_rust.py --expect-defect` | the `planted_loop_defect`, `planted_ladder_defect` and `planted_knapsack_defect` builds are each CAUGHT | that build installed |
| `shadow_rust.py --set field=value ...` | the same, with a `CalcConfig` dial set for the run, to reach paths the defaults never take | |
| `e2e_rust.py OUT ROWS WORKERS ...` | Stage 4 run Python, Rust, Python: `profitability_catalog.csv` byte-identical, in-process and through the pool | a scratch output dir |
| `bench_rust.py OUT ROWS ...` | timing only, but every asteroid's two results are also compared | a scratch output dir |
| `sample_profile.py [--rust] OUT ROWS STACKS.txt ...`, then `analyse_profile.py STACKS.txt` | where search time goes; sizes the next port | a scratch output dir |

**The two plants need different gates, and that is the point of having
both.** The shadow compares final results, and it MISSED the solver plant:
that one-ulp error lands on the in-loop cascade's `m_tank_outbound`, which
the settle-up after the loop recomputes, so it never reaches a result. The
solver replay compares the solver's own output and catches it. A field a
later stage overwrites is invisible to an end-to-end check.

**The ladder plant taught the same lesson a third time.** It flips one ulp of
a rung's `total_cost`. The result comparison missed it: a one-ulp drift
almost never changes which rung wins, and the winner is re-priced by Python
anyway. The ladder's own self-check (every rung Python priced, Rust's total
held to Python's) caught it, 17,471 times on the sample. So the shadow builds
the ladder with `ProgrammeLadder(audit=True)`, which also prices every rung
Rust settled alone through Python and compares `total_cost` and `g` bit for
bit, and the shadow fails on any self-check mismatch. Audit mode is for the
gate only: it does the Python work it exists to skip.

`calc.py` refuses to start with a planted build installed, and it refuses
`ECONOMICSPACE_RUST=1` when es_core is missing. The shadow and the benchmark
build their Rust objects themselves rather than through that guard, so no
bypass lives in calc.py.

## Before this could merge (not done)

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
- Merge spacevalue's `rust-cargo-prototype` first, with CI building and
  testing the crate there (its `rust/README.md` lists what that needs).
- Port further only after a new profile. Size it with `bench_rust.py`, not
  cProfile.
- The ladder's port of `_mission_cost_tail` is a second copy of a cost model
  that releases change. A calc release touching the tail, the prologue tuple's
  order or the rung bound must re-run the audited shadow, or the Rust ladder
  will silently fall back (self-check) or, worse, agree on a sample and
  differ elsewhere.
