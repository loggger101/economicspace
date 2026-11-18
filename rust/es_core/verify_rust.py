# -*- coding: utf-8 -*-
"""Is the Rust solver the Python solver, bit for bit?  (prototype gate)

    python rust/es_core/verify_rust.py [--capture FILE.pkl ...] [--fuzz N]
    python rust/es_core/verify_rust.py --expect-defect ...

Five checks, each of which must pass before ECONOMICSPACE_RUST=1 is trusted:

  1. exp     `f64::exp` (what the Rust solver calls) against `math.exp` on
             every exponent the captured calls produce, a dense sweep of the
             model's range, and the overflow edge.  Bitwise.
  2. log     `f64::ln` against `math.log`, the same way.
  3. replay  every captured real call (capture.py's pickles) through both
             solvers: same keys in the same order, same value TYPES, floats
             equal as bit patterns.
  4. fuzz    random and hostile arguments (inf, nan, -0.0, subnormals, ints
             past 2**53, numpy scalars, bools, None, missing keywords): same
             result or the same exception type and message.
  5. counts  the fast path really ran ON THE REPLAY, counted over the replay
             alone (the fuzz is mostly hostile calls and would dilute it; a
             replay answered by the fallback compares the Python with itself).

`--expect-defect` inverts the verdict for a build made with
`--features planted_defect` (a one-ulp error in one output): it exits 0 only
if the replay check CATCHES the plant.  A check that cannot fail on a planted
defect is not a check (house rule).

Exit 0 = every check passed (or, with --expect-defect, the plant was caught).
"""
from __future__ import annotations

import argparse
import math
import os
import pickle
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
os.environ.pop("ECONOMICSPACE_RUST", None)   # import the PYTHON solver

import numpy as np            # noqa: E402
import es_core                # noqa: E402
import bitsame                # noqa: E402  (this script's folder)
import modules.calc as calc   # noqa: E402

PY = calc.max_return_payload_kg
assert not isinstance(PY, es_core.Solver), "calc imported with Rust swapped in"
RS = es_core.Solver(PY, calc.G0_M_S2)


bits, same, outcome = bitsame.bits, bitsame.same, bitsame.outcome


# ── 1. exp ───────────────────────────────────────────────────────────────────
def check_exp(records) -> int:
    xs = []
    g0 = calc.G0_M_S2
    for _args, kw, _res in records:
        isp = kw.get("isp_s")
        if isinstance(isp, (int, float)) and isp > 0 and math.isfinite(isp):
            for k in ("dv_out_m_s", "dv_ret_m_s"):
                dv = kw.get(k)
                if isinstance(dv, (int, float)) and math.isfinite(dv):
                    xs.append(dv / (isp * g0))
    rng = random.Random(4045)
    xs += [rng.uniform(0.0, 60.0) for _ in range(2_000_000)]
    xs += [rng.uniform(0.0, 709.78) for _ in range(200_000)]
    xs += [0.0, -0.0, 5e-324, 1e-300, 1.0, 709.782712893384,
           math.nextafter(709.782712893384, 0.0), 700.0, -745.2, -746.0]
    rs = es_core.exp_many(xs)
    bad = 0
    for x, r in zip(xs, rs):
        try:
            p = math.exp(x)
        except OverflowError:
            p = math.inf          # the solver maps this to "refuse" either way
        if bits(p) != bits(r):
            bad += 1
            if bad <= 5:
                print("    exp mismatch x=%r python=%r rust=%r" % (x, p, r))
    print("  exp     %s  %d exponents, %d mismatches"
          % ("PASS" if not bad else "FAIL", len(xs), bad))
    return bad


def check_log() -> int:
    """`f64::ln` (the sizing loop's boil-off term) against `math.log`."""
    rng = random.Random(4046)
    xs = [1.0 + rng.uniform(0.0, 3.0) for _ in range(1_000_000)]
    xs += [math.exp(rng.uniform(0.0, 50.0)) for _ in range(1_000_000)]
    xs += [10.0 ** rng.uniform(-300, 300) for _ in range(200_000)]
    xs += [1.0, math.nextafter(1.0, 2.0), math.nextafter(1.0, 0.0), 5e-324,
           1.7976931348623157e308, math.inf]
    rs = es_core.log_many(xs)
    bad = sum(1 for x, r in zip(xs, rs) if bits(math.log(x)) != bits(r))
    print("  log     %s  %d arguments, %d mismatches"
          % ("PASS" if not bad else "FAIL", len(xs), bad))
    return bad


# ── 2. replay ────────────────────────────────────────────────────────────────
def check_replay(records) -> int:
    bad = 0
    for args, kw, recorded in records:
        assert not args, "calc.py calls the solver by keyword only"
        p = outcome(PY, **kw)
        r = outcome(RS, **kw)
        # The recording is the third witness: Python today must still say
        # what Python said when the capture ran.
        if not (p[0] == "ok" and same(p[1], recorded)):
            print("    python no longer reproduces its own capture:", kw)
            bad += 1
        elif not same(p, r):
            bad += 1
            if bad <= 5:
                diff = [k for k in p[1] if not same(p[1].get(k), r[1].get(k) if r[0] == "ok" else None)]
                print("    replay mismatch on", kw, "keys:", diff)
    print("  replay  %s  %d calls, %d mismatches"
          % ("PASS" if not bad else "FAIL", len(records), bad))
    return bad


# ── 3. fuzz ──────────────────────────────────────────────────────────────────
NAMES = ["leo_capacity_kg", "isp_s", "dv_out_m_s", "dv_ret_m_s",
         "hardware_kg", "dry_return_kg", "tps_frac", "isru_return",
         "structure_frac", "tank_frac"]
HOSTILE = [0.0, -0.0, -1.0, 5e-324, 1e-300, 1e308, math.inf, -math.inf,
           math.nan, 0, 1, -3, 5000, 2**53, 2**53 + 1, -(2**53) - 1, 10**400,
           np.float64(3.5), np.float32(2.0), np.int64(7), True, False, None,
           "3.0"]


def plausible(rng, name):
    if name == "leo_capacity_kg":
        return rng.choice([rng.uniform(1e3, 2.5e5), float(rng.randint(1000, 150000))])
    if name == "isp_s":
        return rng.uniform(200.0, 9000.0)
    if name in ("dv_out_m_s", "dv_ret_m_s"):
        return rng.uniform(0.0, 25000.0)
    if name in ("hardware_kg", "dry_return_kg"):
        return rng.choice([rng.uniform(0.0, 50000.0), rng.randint(0, 50000)])
    if name == "isru_return":
        return rng.random() < 0.5
    return rng.choice([0.0, rng.uniform(0.0, 0.6), rng.uniform(0.0, 3.0)])


def check_fuzz(n: int) -> int:
    rng = random.Random(2026)
    bad = 0
    for i in range(n):
        kw = {k: plausible(rng, k) for k in NAMES}
        roll = rng.random()
        if roll < 0.35:                        # one or two hostile values
            for _ in range(rng.choice([1, 2])):
                kw[rng.choice(NAMES)] = rng.choice(HOSTILE)
        elif roll < 0.45:                      # drop optional / required args
            for k in rng.sample(NAMES, rng.choice([1, 2])):
                kw.pop(k)
        elif roll < 0.5:                       # an unknown keyword
            kw["tank_fraction"] = 0.1
        p, r = outcome(PY, **kw), outcome(RS, **kw)
        if not same(p, r):
            bad += 1
            if bad <= 5:
                print("    fuzz mismatch", kw)
                if p[0] == r[0] == "ok":
                    for k in p[1]:
                        if not same(p[1][k], r[1].get(k)):
                            show = lambda v: bits(v).hex() if isinstance(v, float) else repr(v)
                            print("      %s py %s rs %s" % (k, show(p[1][k]), show(r[1].get(k))))
                else:
                    print("      py:", p, "\n      rs:", r)
    print("  fuzz    %s  %d calls, %d mismatches"
          % ("PASS" if not bad else "FAIL", n, bad))
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capture", nargs="*", default=[])
    ap.add_argument("--fuzz", type=int, default=300_000)
    ap.add_argument("--expect-defect", action="store_true")
    a = ap.parse_args()

    if es_core.planted_defect() != a.expect_defect:
        print("build mismatch: planted_defect()=%s but --expect-defect=%s"
              % (es_core.planted_defect(), a.expect_defect))
        return 2

    records = []
    for path in a.capture:
        with open(path, "rb") as fh:
            got = pickle.load(fh)
        print("  loaded %d captured calls from %s" % (len(got), os.path.basename(path)))
        records += got
    if not records:
        print("no captured calls: pass --capture (a replay of nothing proves nothing)")
        return 2

    fails = {}
    fails["exp"] = check_exp(records)
    fails["log"] = check_log()
    c0 = RS.counts()
    fails["replay"] = check_replay(records)
    c1 = RS.counts()
    fails["fuzz"] = check_fuzz(a.fuzz)
    c2 = RS.counts()
    fast, slow = c1[0] - c0[0], c1[1] - c0[1]
    share = fast / max(1, fast + slow)
    ok_counts = fast > 0 and share > 0.5
    print("  counts  %s  replay: fast path %d, Python fallback %d (%.1f%% fast);"
          " fuzz: fast %d, fallback %d (not gated)"
          % ("PASS" if ok_counts else "FAIL", fast, slow, 100 * share,
             c2[0] - c1[0], c2[1] - c1[1]))
    fails["counts"] = 0 if ok_counts else 1

    # Not a gate: the per-call cost of each solver on the captured calls,
    # interleaved three times in this one process.
    import time
    kws = [kw for _a, kw, _r in records]
    tp, tr = [], []
    for _ in range(3):
        for fn, acc in ((PY, tp), (RS, tr)):
            t0 = time.perf_counter()
            for kw in kws:
                fn(**kw)
            acc.append(time.perf_counter() - t0)
    print("  bench   python %.0f ns/call, rust %.0f ns/call (%.1fx), best of 3"
          % (1e9 * min(tp) / len(kws), 1e9 * min(tr) / len(kws), min(tp) / min(tr)))

    if a.expect_defect:
        caught = fails["replay"] > 0
        print("PLANT %s: the replay check %s the one-ulp defect"
              % ("CAUGHT" if caught else "MISSED", "saw" if caught else "did NOT see"))
        return 0 if caught else 1
    total = sum(fails.values())
    print("VERDICT", "PASS" if not total else "FAIL")
    return 0 if not total else 1


if __name__ == "__main__":
    sys.exit(main())
