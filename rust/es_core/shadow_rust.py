# -*- coding: utf-8 -*-
"""Shadow run: every `_evaluate_combo_at_ratio` computed twice, compared.

    python rust/es_core/shadow_rust.py OUT_DIR ROWS [run_pipeline flags...]
    python rust/es_core/shadow_rust.py --expect-defect OUT_DIR ROWS ...

Runs Stage 4 in-process (one worker; OUT_DIR must hold Stage 1-3 outputs and
is written to).  Every call of `_evaluate_combo_at_ratio`, the top-level ones
and every recursive repair inside them, is evaluated in BOTH modes:

    python  the Python solver and the Python sizing loop
    rust    es_core.Solver and es_core.SizingLoop

and the two results must be identical: same type, same keys in order,
floats and numpy scalars equal as bit patterns, recursively.  The call then
returns the result of the mode its caller is in, so a Python-mode call is
Python all the way down and a Rust-mode call is Rust all the way down.

Exit 0 only if every call matched and the Rust loop answered most calls
itself (a gate that only exercised the fallback proves nothing).
`--expect-defect` (a `planted_loop_defect` or `planted_defect` build) exits 0
only if the shadow comparison CATCHES the plant.
"""
import math
import os
import struct
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
import numpy as np            # noqa: E402
import modules.calc as calc   # noqa: E402
import es_core                # noqa: E402
assert calc._ES_LOOP is None and not isinstance(calc.max_return_payload_kg, es_core.Solver)
if tuple(es_core.SizingLoop.STATE_NAMES) != calc._ES_STATE_NAMES:
    raise SystemExit("es_core STATE_NAMES differ from calc's: rebuild es_core")
calc.max_return_payload_kg = es_core.Solver(calc.max_return_payload_kg, calc.G0_M_S2)
assert calc._ES_LADDER is None
# audit=True: every rung Rust prices is also priced by Python's
# `_price_programme` and must match bit for bit (total_cost and g).  Result
# comparison alone cannot see a one-ulp rung drift that flips no winner.
RS_LADDER = es_core.ProgrammeLadder(audit=True)
_LOOP = es_core.SizingLoop(calc.G0_M_S2, calc._ES_UNSET,
                           calc._DAMP_MIN_STEP, calc._DAMP_EXTRA_PASSES)
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


calc._ES_LOOP = CountingLoop()

args = sys.argv[1:]
expect_defect = False
if args and args[0] == "--expect-defect":
    expect_defect, args = True, args[1:]
# --set field=value (repeatable, before OUT_DIR): a CalcConfig dial for this
# run only, to reach loop paths the defaults never take.  Applied to
# calc.CONFIG, which the run reads; printed so the run says what it ran.
import ast   # noqa: E402
while args and args[0] == "--set":
    field, _, value = args[1].partition("=")
    if not hasattr(calc.CONFIG, field):
        raise SystemExit("--set: CalcConfig has no field %r" % field)
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

MODES = {"python": (PY_SOLVER, None, None), "rust": (RS_SOLVER, RS_LOOP, RS_LADDER)}
current = ["rust"]          # the mode a top-level call (from evaluate_combo) is in
stats = {"calls": 0, "mismatch": 0, "py_s": 0.0, "rs_s": 0.0}
shown = []


def bits(x):
    return struct.pack("<d", x)


def same(a, b, path="", diffs=None):
    """Identical to any downstream reader?  Collects differing paths."""
    if type(a) is not type(b):
        diffs.append("%s type %s vs %s" % (path, type(a).__name__, type(b).__name__))
        return
    if isinstance(a, float):
        if bits(a) != bits(b):
            diffs.append("%s %s vs %s" % (path, bits(a).hex(), bits(b).hex()))
    elif isinstance(a, np.generic):
        if a.tobytes() != b.tobytes():
            diffs.append("%s np %r vs %r" % (path, a, b))
    elif isinstance(a, dict):
        if list(a) != list(b):
            diffs.append("%s keys differ" % path)
            return
        for k in a:
            same(a[k], b[k], "%s.%s" % (path, k), diffs)
    elif isinstance(a, (list, tuple)):
        if len(a) != len(b):
            diffs.append("%s len %d vs %d" % (path, len(a), len(b)))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            same(x, y, "%s[%d]" % (path, i), diffs)
    elif a is None or isinstance(a, (str, bool, int)):
        if a != b:
            diffs.append("%s %r vs %r" % (path, a, b))
    else:
        # Anything else would need its own rule; refuse to call it equal.
        if not (a is b or a == b):
            diffs.append("%s unhandled %s" % (path, type(a).__name__))


def run_in(mode, a, kw):
    saved = (current[0], calc.max_return_payload_kg, calc._ES_LOOP, calc._ES_LADDER)
    current[0] = mode
    calc.max_return_payload_kg, calc._ES_LOOP, calc._ES_LADDER = MODES[mode]
    t0 = time.perf_counter()
    try:
        return ORIG(*a, **kw)
    finally:
        stats["py_s" if mode == "python" else "rs_s"] += time.perf_counter() - t0
        current[0], calc.max_return_payload_kg, calc._ES_LOOP, calc._ES_LADDER = saved


def shadow(*a, **kw):
    caller_mode = current[0]
    r_py = run_in("python", a, kw)
    r_rs = run_in("rust", a, kw)
    stats["calls"] += 1
    diffs = []
    same(r_py, r_rs, "result", diffs)
    if diffs:
        stats["mismatch"] += 1
        if len(shown) < 5:
            shown.append(diffs[:6])
    return r_py if caller_mode == "python" else r_rs


calc._evaluate_combo_at_ratio = shadow

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
unexercised = [k for k, v in coverage.items() if v == 0 and k != "fallback"]
print("UNEXERCISED by this sample: " + (", ".join(unexercised) or "none"))
print("TIME    in python-mode calls %.1f s, in rust-mode calls %.1f s (inclusive, nested calls counted in both)"
      % (stats["py_s"], stats["rs_s"]))
if expect_defect:
    caught = stats["mismatch"] > 0 or RS_LADDER.stats()["selfcheck_mismatch"] > 0
    print("PLANT", "CAUGHT" if caught else "MISSED")
    sys.exit(0 if caught else 1)
lst = RS_LADDER.stats()
ladder_share = lst["fast"] / max(1, lst["fast"] + lst["fallback"])
print("LADDER  %.1f%% of ladders in Rust; self-check mismatches %d" % (100 * ladder_share, lst["selfcheck_mismatch"]))
ok = (stats["mismatch"] == 0 and stats["calls"] > 0 and share > 0.5
      and ladder_share > 0.5 and lst["selfcheck_mismatch"] == 0)
print("VERDICT", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
