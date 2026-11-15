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
  `a + b`, and on x86 the NaN that survives depends on operand order.

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
| e2e catalogs, benef/search, 150 rows, 1 worker | byte-identical (Python/Rust/Python) |
| e2e catalogs, raw, 2,000 rows, 1 worker | byte-identical |
| e2e catalogs, benef/search, 400 rows, 4-worker spawn pool | byte-identical (first attempt ran out of memory reading the catalog while a shadow ran alongside; rerun alone) |
| guards: `=yes`, planted build, extension missing | each raises at import |

**Speed**, `bench_rust.py`: the search only, Python and Rust alternating on
every asteroid in one process, with every result also compared:

| sample | Python | Rust | speed-up |
|---|---|---|---|
| cislunar raw, no search, 300 rows | 18.3 ms/asteroid | 11.4 ms/asteroid | 1.59x |
| cislunar benef/search, 60 rows | 289.8 ms/asteroid | 215.1 ms/asteroid | 1.35x |

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

**The next port is programme pricing.** That means the ladder loop over
`_price_programme`, with `_mission_cost_tail`, `_objective_key` and
`_capped_sale_value` (spacevalue). If it ran ~10x faster, the beneficiated
search would gain ~2x on top of today (Amdahl: 1 / (0.45 + 0.055)), about
2.7x against pure Python. The knapsack is the one after; it lives in
spacevalue, so a Rust copy is a second implementation that must stay in
step with that repository.

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

## The gate (all of it must pass, and the plants must be caught)

| tool | checks | needs |
|---|---|---|
| `capture.py` | records every real solver call in a sample run | Stage 1-3 outputs in a scratch dir |
| `verify_rust.py --capture *.pkl` | `exp` and `log` bitwise; solver replay; 300k hostile fuzz; fast-path share | the captures |
| `verify_rust.py --expect-defect` | the `planted_defect` build is CAUGHT | that build installed |
| `shadow_rust.py OUT ROWS ...` | every `_evaluate_combo_at_ratio` call, including each recursive repair, computed all-Python and all-Rust and compared recursively, bit for bit; loop share | a scratch output dir |
| `shadow_rust.py --expect-defect` | the `planted_loop_defect` build is CAUGHT | that build installed |
| `e2e_rust.py OUT ROWS WORKERS ...` | Stage 4 run Python, Rust, Python: `profitability_catalog.csv` byte-identical, in-process and through the pool | a scratch output dir |
| `bench_rust.py OUT ROWS ...` | timing only, but every asteroid's two results are also compared | a scratch output dir |
| `sample_profile.py [--rust] OUT ROWS STACKS.txt ...`, then `analyse_profile.py STACKS.txt` | where search time goes; sizes the next port | a scratch output dir |

**The two plants need different gates, and that is the point of having
both.** The shadow compares final results, and it MISSED the solver plant:
that one-ulp error lands on the in-loop cascade's `m_tank_outbound`, which
the settle-up after the loop recomputes, so it never reaches a result. The
solver replay compares the solver's own output and catches it. A field a
later stage overwrites is invisible to an end-to-end check.

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
- Port further. Next would be the knapsack (`spacevalue.cargo`, another
  repository, so a second copy that must stay in step) and programme pricing
  (`_price_programme`). Size each with `bench_rust.py`, not cProfile.
