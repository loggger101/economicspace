# -*- coding: utf-8 -*-
"""Shadow run: every `_evaluate_combo_at_ratio` computed twice, compared.

    python rust/es_core/shadow_rust.py [--set FIELD=VALUE ...] OUT_DIR ROWS [run_pipeline flags...]
    python rust/es_core/shadow_rust.py --expect-defect [--set ...] OUT_DIR ROWS ...

Runs Stage 4 in-process (one worker; OUT_DIR must hold Stage 1-3 outputs and
is written to).  Every call of `_evaluate_combo_at_ratio`, the top-level ones
and every recursive repair inside them, is evaluated in BOTH modes:

    python  the Python solver, sizing loop, programme ladder and cargo calls
    rust    es_core.Solver, es_core.SizingLoop, es_core.ProgrammeLadder (in
            audit mode) and calc's cargo calls through spacevalue_cargo_rs

and the two results must be identical: same type, same keys in order,
floats and numpy scalars equal as bit patterns, recursively.  The call then
returns the result of the mode its caller is in, so a Python-mode call is
Python all the way down and a Rust-mode call is Rust all the way down.
Solver calls made OUTSIDE the evaluator (the pre-filter and the combo bound)
are answered by both solvers and compared the same way.

Exit 0 only if every comparison matched, the ladder's self-check found
nothing, and each Rust path that ran (loop, ladder, in-loop knapsack, calc's
cargo calls) answered most of its calls itself: a gate that only exercised
the fallback compares the Python with itself and proves nothing.
`--expect-defect` (an es_core build with any `planted_*` feature) exits 0
only if a comparison or the ladder's self-check CATCHES the plant.  A
planted spacevalue_cargo_rs is run WITHOUT --expect-defect (that flag keys on
es_core's build) and must exit 1 with VERDICT FAIL.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

# calc is imported in plain Python mode and the Rust objects are built HERE,
# exactly as calc builds them, because calc (rightly) refuses a planted build
# and this harness must be able to load one.  No bypass lives in calc.py.
os.environ.pop("ECONOMICSPACE_RUST", None)
sys.path.insert(0, REPO)
os.chdir(REPO)
import modules.calc as calc   # noqa: E402
import bitsame                # noqa: E402  (this script's folder)
import es_core                # noqa: E402
assert calc._ES_LOOP is None and not isinstance(calc.max_return_payload_kg, es_core.Solver)
calc.max_return_payload_kg = es_core.Solver(calc.max_return_payload_kg, calc.G0_M_S2)
assert calc._ES_LADDER is None
# audit=True: every rung Rust prices is also priced by Python's
# `_price_programme` and must match bit for bit (total_cost and g).  Result
# comparison alone cannot see a one-ulp rung drift that flips no winner.
RS_LADDER = es_core.ProgrammeLadder(audit=True)
_LOOP = calc._rust_sizing_loop(es_core)
KIND_NAMES = {0: "fallback", 1: "refuse", 2: "done", 3: "refit_feed", 4: "refit_plant"}
coverage = {k: 0 for k in KIND_NAMES.values()}
coverage.update({"done_damped": 0, "done_not_converged": 0, "relax_on": 0,
                 "isru": 0, "electric": 0, "rtg": 0, "boiloff": 0,
                 "refinery": 0, "flown_load": 0, "payload_cap": 0})


class CountingLoop:
    """Delegates to the real SizingLoop and counts which paths ran, so a
    pass is a pass over the paths that were actually exercised."""

    def run(self, **kw):
        r = _LOOP.run(**kw)
        coverage[KIND_NAMES[r[0]]] += 1
        if r[0] == 2:
            st = dict(zip(calc._ES_STATE_NAMES, r[1]))
            coverage["done_damped"] += st["damped_here"] > 0
            coverage["done_not_converged"] += not st["converged"]
        for flag, key in (("relax", "relax_on"), ("isru", "isru"),
                          ("is_electric", "electric"), ("power_is_rtg", "rtg"),
                          ("models_boiloff", "boiloff"), ("has_refinery", "refinery"),
                          ("size_ep_on_flown_load", "flown_load")):
            coverage[key] += bool(kw[flag])
        coverage["payload_cap"] += kw["payload_cap_kg"] is not None
        return r

    def counts(self):
        return _LOOP.counts()

    def knapsack_counts(self):
        return _LOOP.knapsack_counts()


calc._ES_LOOP = CountingLoop()

args = sys.argv[1:]
expect_defect = False
if args and args[0] == "--expect-defect":
    expect_defect, args = True, args[1:]
# --set field=value (repeatable, before OUT_DIR): a CalcConfig dial for this
# run only, to reach loop paths the defaults never take.  Applied to
# calc.CONFIG, which the run reads; printed so the run says what it ran.
import ast   # noqa: E402
# run_pipeline writes these from its own flags after --set has run, so a
# --set of one would print SET and then not take effect: use the flag.
CLI_OWNED = ("eval_row_cap", "use_beneficiation", "optimise_programme_scale",
             "delivery_destination")
while args and args[0] == "--set":
    field, _, value = args[1].partition("=")
    if not hasattr(calc.CONFIG, field):
        raise SystemExit("--set: CalcConfig has no field %r" % field)
    if field in CLI_OWNED:
        raise SystemExit("--set: %s is set by run_pipeline's own flags "
                         "(--rows, --raw/--beneficiated, --search, --destination)"
                         % field)
    setattr(calc.CONFIG, field, ast.literal_eval(value))
    print("SET     %s = %r" % (field, getattr(calc.CONFIG, field)))
    args = args[2:]
out_dir, rows, flags = args[0], args[1], args[2:]
if es_core.planted_defect() != expect_defect:
    raise SystemExit("build mismatch: planted_defect()=%s, --expect-defect=%s"
                     % (es_core.planted_defect(), expect_defect))

RS_SOLVER = calc.max_return_payload_kg
assert isinstance(RS_SOLVER, es_core.Solver)
PY_SOLVER = RS_SOLVER.__wrapped__
RS_LOOP = calc._ES_LOOP
assert RS_LOOP is not None
ORIG = calc._evaluate_combo_at_ratio

# calc's Python-side cargo calls, routed to spacevalue's Rust crate in Rust
# mode exactly as calc routes them (`_rust_cargo`), swapped per mode below.
import spacevalue_cargo_rs   # noqa: E402
PY_CARGO = (calc._capped_sale_value, calc._hold_refining)
RS_CARGO = calc._rust_cargo(spacevalue_cargo_rs, calc._hold_refining)
MODES = {"python": (PY_SOLVER, None, None) + PY_CARGO,
         "rust": (RS_SOLVER, RS_LOOP, RS_LADDER) + RS_CARGO}
SWAP = ("max_return_payload_kg", "_ES_LOOP", "_ES_LADDER",
        "_capped_sale_value", "_hold_refining")
current = ["rust"]          # the mode a top-level call (from evaluate_combo) is in
stats = {"calls": 0, "mismatch": 0, "py_s": 0.0, "rs_s": 0.0,
         "outside_calls": 0, "outside_mismatch": 0}
shown = []


def run_in(mode, a, kw):
    saved = (current[0],) + tuple(getattr(calc, n) for n in SWAP)
    current[0] = mode
    for n, v in zip(SWAP, MODES[mode]):
        setattr(calc, n, v)
    t0 = time.perf_counter()
    try:
        return ORIG(*a, **kw)
    finally:
        stats["py_s" if mode == "python" else "rs_s"] += time.perf_counter() - t0
        current[0] = saved[0]
        for n, v in zip(SWAP, saved[1:]):
            setattr(calc, n, v)


def shadow(*a, **kw):
    caller_mode = current[0]
    r_py = run_in("python", a, kw)
    r_rs = run_in("rust", a, kw)
    stats["calls"] += 1
    d = bitsame.diffs(r_py, r_rs, "result")
    if d:
        stats["mismatch"] += 1
        if len(shown) < 5:
            shown.append(d[:6])
    return r_py if caller_mode == "python" else r_rs


calc._evaluate_combo_at_ratio = shadow


def dual_solver(*a, **kw):
    """The solver as seen OUTSIDE `_evaluate_combo_at_ratio`: the pre-filter
    (`_combo_can_close`, `_closes_carrying_its_own_stage`) and the combo bound
    call it there, so run_in's per-mode swap never reaches them.  Both solvers
    answer every such call and must agree bit for bit; a solver bug that only
    moves pruning would otherwise be invisible to this shadow."""
    r_py = bitsame.outcome(PY_SOLVER, *a, **kw)
    r_rs = bitsame.outcome(RS_SOLVER, *a, **kw)
    stats["outside_calls"] += 1
    d = bitsame.diffs(r_py, r_rs, "solver")
    if d:
        stats["outside_mismatch"] += 1
        if len(shown) < 5:
            shown.append(d[:6])
    if r_py[0] == "raised":
        return PY_SOLVER(*a, **kw)      # re-raise the Python's own exception
    return r_py[1]


calc.max_return_payload_kg = dual_solver
SV_COUNTS0 = spacevalue_cargo_rs.counts()

import run_pipeline           # noqa: E402
sys.argv = ["run_pipeline.py", "--stages", "4", "--rows", rows,
            "--workers", "1", "--output", out_dir] + flags
t0 = time.perf_counter()
try:
    run_pipeline.main()
except SystemExit:
    pass
wall = time.perf_counter() - t0

fast, slow = RS_LOOP.counts()
share = fast / max(1, fast + slow)
print()
print("SHADOW  %d calls compared, %d mismatches" % (stats["calls"], stats["mismatch"]))
for d in shown:
    print("   ", "; ".join(d))
print("LOOP    answered in Rust %d, handed to Python %d (%.1f%% Rust)" % (fast, slow, 100 * share))
print("PATHS   " + ", ".join("%s %d" % kv for kv in coverage.items()))
print("LADDER  " + ", ".join("%s %d" % kv for kv in sorted(RS_LADDER.stats().items())))
knative, kcall = RS_LOOP.knapsack_counts()
kshare = knative / max(1, knative + kcall)
print("KNAP    knapsack evaluations inside Rust-answered loops: in Rust %d, calling back %d (%.1f%% Rust)"
      % (knative, kcall, 100 * kshare))
print("OUTSIDE solver calls outside the evaluator (pre-filter, bound) %d compared, %d mismatches"
      % (stats["outside_calls"], stats["outside_mismatch"]))
sv_fast, sv_slow = (n - n0 for n, n0 in zip(spacevalue_cargo_rs.counts(), SV_COUNTS0))
sv_share = sv_fast / max(1, sv_fast + sv_slow)
print("CARGO   calc's cargo calls answered by spacevalue_cargo_rs %d, handed to Python %d (%.1f%% Rust)"
      % (sv_fast, sv_slow, 100 * sv_share))
unexercised = [k for k, v in coverage.items() if v == 0 and k != "fallback"]
print("UNEXERCISED by this sample: " + (", ".join(unexercised) or "none"))
print("TIME    in python-mode calls %.1f s, in rust-mode calls %.1f s (inclusive, nested calls counted in both)"
      % (stats["py_s"], stats["rs_s"]))
if expect_defect:
    caught = (stats["mismatch"] > 0 or stats["outside_mismatch"] > 0
              or RS_LADDER.stats()["selfcheck_mismatch"] > 0)
    print("PLANT", "CAUGHT" if caught else "MISSED")
    sys.exit(0 if caught else 1)
lst = RS_LADDER.stats()
ladder_share = lst["fast"] / max(1, lst["fast"] + lst["fallback"])
print("LADDER  %.1f%% of ladders in Rust; self-check mismatches %d" % (100 * ladder_share, lst["selfcheck_mismatch"]))
# A path that ran must have been answered mostly in Rust, or the comparison
# was Python vs Python.  The in-loop knapsack is gated only where it ran (a
# raw hold never runs it); calc's cargo calls must have reached Rust at all,
# since a route that bypassed spacevalue_cargo_rs would leave both counts 0.
ok = (stats["mismatch"] == 0 and stats["calls"] > 0 and share > 0.5
      and ladder_share > 0.5 and lst["selfcheck_mismatch"] == 0
      and stats["outside_calls"] > 0 and stats["outside_mismatch"] == 0
      and (knative + kcall == 0 or kshare > 0.5)
      and sv_fast > 0 and sv_share > 0.5)
print("VERDICT", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
