# es_core: opt-in Rust for Stage 4 (prototype)

**Status:** a prototype on branch `rust-solver-prototype`. Not merged and not
used by default. Nothing changes unless `ECONOMICSPACE_RUST=1` is set.

## What it ports

So far, one function: `modules/calc.py::max_return_payload_kg`, the
closed-form solver for the return-mission mass cascade. A 2,000-row cislunar
profile (raw, no search, one worker) called it **5.1 M times**, taking 31 s of
the 160 s spent in `evaluate_asteroid`. It sits under
`_evaluate_combo_at_ratio`, which takes 72% of that time; that subtree is the
next candidate (see the end of this file).

## What the prototype measured (2026-11-15, this host, calc 1.46.0)

| check | result |
|---|---|
| `exp` bitwise vs `math.exp` | 5,331,256 exponents, 0 mismatches |
| replay of captured real calls (cislunar raw/no-search 150 rows + benef/search 60 rows) | 1,565,623 calls, 0 mismatches |
| hostile fuzz | 300,000 calls, 0 mismatches |
| share answered by Rust | 94.5% (the rest fell back to Python by design) |
| planted one-ulp defect | caught by replay (1,193,378 calls) and fuzz |
| e2e cislunar raw/no-search, 2,000 rows, 1 worker | byte-identical catalogs |
| e2e cislunar benef/search, 150 rows, 1 worker | byte-identical catalogs |
| e2e cislunar benef/search, 400 rows, 4-worker spawn pool | byte-identical catalogs |
| guards: `=yes`, planted build, extension missing | each raises at import |
| per call | Python ~2.9 us, Rust ~1.3 us (2.2-2.4x) |
| whole Stage 4 run | no measurable change (1.00-1.10x, inside run-to-run noise of ~30 s) |

**The speed result is the lesson.** At about 1.3 us per call, most of the
Rust call is spent building the `**kwargs` dict and the 14-key result dict;
the arithmetic is nanoseconds. Porting leaves one at a time across the
Python boundary cannot pay. The gain has to come from porting a whole
subtree (`_evaluate_combo_at_ratio` and everything under it), so the
boundary is crossed once per combo rather than millions of times.

Two traps the gate found and the code now handles:
- **NaN sign.** LLVM may commute `a + b`, and on x86 the NaN that survives
  depends on operand order. Rust returned +NaN where Python returned -NaN.
  Any result containing a NaN is now recomputed by Python.
- **Ints.** Half the real calls pass `int` masses. They are accepted up to
  2**53 (exact conversion), except `tps_frac`, because `tps_frac *
  dry_return_kg` with two ints is a Python int.

## The contract: bit-identity, not "close enough"

`es_core.Solver(python_fn, G0_M_S2)` is a callable that returns the same
result as the Python function:

- the same keys in the same order;
- the same value types (the refusal cascade's masses are Python `int` 0);
- the same floats, compared as bit patterns;
- the same exceptions.

The fast path takes only keyword calls that use calc.py's argument names.
Each argument must be an exact `float` or an exact `int` with |n| ≤ 2⁵³
(`tps_frac` must be a `float`), and `isru_return` must be an exact `bool`.
Anything else goes to the Python function untouched: numpy scalars, larger
ints, bools in float slots, a positional call, a missing or unknown keyword,
or a divisor that is exactly zero.

## Build

You need rustup (stable, `x86_64-pc-windows-msvc`), the MSVC Build Tools
with the Windows SDK, and `pip install maturin==1.9.6`.

    export CARGO_TARGET_DIR="$HOME/.cargo-target/es_core"   # NOT inside OneDrive
    cd rust/es_core
    python -m maturin build --release -o dist

`target/` inside the synced folder fails: build scripts there report
"output path is not a writable directory", and the folder would sync
gigabytes of build output anyway.
    python -m pip install --force-reinstall dist/es_core-*.whl

The planted-defect copy, which only the gate uses:

    python -m maturin build --release --features planted_defect -o dist-plant

## The gate (all of it must pass)

1. `capture.py` runs a sample and records every real solver call
   (args, kwargs, result).
2. `verify_rust.py --capture *.pkl` runs four checks: `exp` bitwise against
   `math.exp`, a replay of every captured call, a 300k-call hostile fuzz,
   and a count proving the fast path actually ran.
3. `verify_rust.py --expect-defect` on the planted build must report
   `PLANT CAUGHT`. A check that cannot fail is not a check.
4. `e2e_rust.py OUT ROWS WORKERS ...` runs Stage 4 as Python, then Rust, then
   Python again. All three `profitability_catalog.csv` files must be
   byte-identical, in-process (`--workers 1`) and through the spawn pool.

`calc.py` refuses to start with a planted build installed, and it refuses
`ECONOMICSPACE_RUST=1` when es_core is missing.

## Before this could merge (not done)

- Run the gate on `DESKTOP-PJS73RO`. `platform_check.py` proves numpy
  parity between hosts; it does not prove the C runtime's `exp` matches
  there.
- Wire the gate into `verify.py` as a check and add a CI job that builds the
  wheel.
- Decide how the wheel is pinned and installed (`_runtime.install()`, the
  requirements files).
- Run one full campaign cell with `ECONOMICSPACE_RUST=1` and compare its hash
  with the archived cell.
- Port the `_evaluate_combo_at_ratio` subtree. This leaf alone saves only a
  modest share of a run.
