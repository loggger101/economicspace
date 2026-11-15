# -*- coding: utf-8 -*-
"""Per-asteroid timing, Python vs Rust, interleaved in one process.

    python rust/es_core/bench_rust.py OUT_DIR ROWS [run_pipeline flags...]

Runs Stage 4 in-process (one worker; OUT_DIR must hold Stage 1-3 outputs and
is written to).  Every `evaluate_asteroid` call is made twice, once in each
mode, alternating which goes first, so load swings on the machine land on
both sides alike (CLAUDE.md: time two builds in ONE process).  The two
results must also be identical, which makes this a third equality check.

CSV loading, the pool and writing are excluded: this measures the search.
"""
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
os.environ.pop("ECONOMICSPACE_RUST", None)
sys.path.insert(0, REPO)
os.chdir(REPO)
import numpy as np            # noqa: E402
import modules.calc as calc   # noqa: E402
import es_core                # noqa: E402

if es_core.planted_defect():
    raise SystemExit("planted build installed; benchmark the real one")
PY = (calc.max_return_payload_kg, None, None)
RS = (es_core.Solver(calc.max_return_payload_kg, calc.G0_M_S2),
      es_core.SizingLoop(calc.G0_M_S2, calc._ES_UNSET,
                         calc._DAMP_MIN_STEP, calc._DAMP_EXTRA_PASSES),
      es_core.ProgrammeLadder())
ORIG = calc.evaluate_asteroid
t = {"py": 0.0, "rs": 0.0}
n = {"rows": 0, "differ": 0}


def bits_equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, float):
        return struct.pack("<d", a) == struct.pack("<d", b)
    if isinstance(a, np.generic):
        return a.tobytes() == b.tobytes()
    if isinstance(a, dict):
        return list(a) == list(b) and all(bits_equal(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(bits_equal(x, y) for x, y in zip(a, b))
    return a == b


def timed(mode, *a, **kw):
    calc.max_return_payload_kg, calc._ES_LOOP, calc._ES_LADDER = mode
    t0 = time.perf_counter()
    r = ORIG(*a, **kw)
    return r, time.perf_counter() - t0


def bench(*a, **kw):
    first_py = n["rows"] % 2 == 0
    if first_py:
        rp, dp = timed(PY, *a, **kw)
        rr, dr = timed(RS, *a, **kw)
    else:
        rr, dr = timed(RS, *a, **kw)
        rp, dp = timed(PY, *a, **kw)
    t["py"] += dp
    t["rs"] += dr
    n["rows"] += 1
    if not bits_equal(rp, rr):
        n["differ"] += 1
    calc.max_return_payload_kg, calc._ES_LOOP, calc._ES_LADDER = PY
    return rp


calc.evaluate_asteroid = bench
import run_pipeline           # noqa: E402
out_dir, rows, flags = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.argv = ["run_pipeline.py", "--stages", "4", "--rows", rows,
            "--workers", "1", "--output", out_dir] + flags
try:
    run_pipeline.main()
except SystemExit:
    pass
fast, slow = RS[1].counts()
print()
print("BENCH  %d asteroids, %d with differing results" % (n["rows"], n["differ"]))
print("       python %.1f s (%.1f ms/asteroid), rust %.1f s (%.1f ms/asteroid): %.2fx"
      % (t["py"], 1e3 * t["py"] / max(1, n["rows"]), t["rs"],
         1e3 * t["rs"] / max(1, n["rows"]), t["py"] / max(t["rs"], 1e-9)))
print("       sizing loops in Rust %d, handed to Python %d" % (fast, slow))
print("       ladder %s" % dict(sorted(RS[2].stats().items())))
sys.exit(0 if n["differ"] == 0 and n["rows"] > 0 else 1)
