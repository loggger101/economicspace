# -*- coding: utf-8 -*-
"""Release verification harness for the asteroid profitability pipeline.

Run this before and after any change to Stage 4.  It is the five checks every
release in CLAUDE.md argues from, written down once instead of rebuilt from
memory each time:

    1. bit-identity    four cells, column by column and by hash, vs a baseline
    2. prune on/off    the pre-filter agrees with the unpruned search
    3. serial/parallel a worker sees what its parent sees
    4. mass ledger     hardware_total_kg == rig + plant + ep, exactly
    5. never-worse     beneficiated <= raw, and searched <= N = 1

Typical use.  The ORDER matters: the baseline must be captured before the first
edit, exactly as every release note in CLAUDE.md says it was.

    py verify.py baseline           # on a clean tree, BEFORE editing
    ...make the change...
    py build_master.py
    py verify.py check              # bit-identity + every invariant

Other entry points:

    py verify.py check --skip prune parallel  # ~5 min: bit-identity + 4 + 5
    py verify.py check --cells raw benef      # a subset
    py verify.py invariants                   # 4 and 5 only; needs no baseline
    py verify.py baseline --tag 1.17.6        # keep several around

SCOPE.  This covers STAGE 4 and nothing else.  It never re-runs Stages 1-3 --
deliberately, because a Stage 1 run fetches a different catalog (JPL adds bodies
daily) and a Stage 3 run re-fetches live prices, either of which moves the
inputs underneath the comparison.  The consequence is that a change to Stage 1,
2 or 3 can pass every check here and still be wrong: v1.12.1's propellant-flag
fix lives in Stage 3's validate(), which Stage 4 never calls, and had to be
checked by running that function under `-W error::FutureWarning` instead.  If
you change an upstream module, this file is not your evidence.

BUDGET.  A full `check` builds ~20 cells and takes roughly HALF AN HOUR on the
reference machine.  Most of that is check 2, because turning the pre-filter off
is what v1.14.1 and v1.17.4 exist to avoid -- an unpruned cell runs the whole
search.  Iterate with `--skip prune parallel` (~5 min, and it still catches any
change to any number), then run the full set once before committing.  A
verification you will not run is worse than a slow one.

WHY THIS FILE EXISTS
--------------------
Every release so far wrote these checks from scratch and threw them away, and
CLAUDE.md records what that cost -- eleven harness bugs, three of which produced
conclusions that were written down before being caught:

  v1.15.0   two cells recorded as "cislunar" that ran against earth_surface
            prices, because CALC_CONFIG defaults to earth_surface while the
            on-disk Stage 2 catalog is whatever destination was last built
  v1.15.0   a brute-force sweep truncated at N = 24 read as a counter-example
            to the very thing it was truncating
  v1.17.1   a parquet round trip rendered None as nan, so three identical
            object columns compared as different -- "a broken checker looks
            exactly like a broken release"
  v1.17.3   only pipeline_version stripped before hashing, so midnight falling
            mid-run made catalog_date differ, and that read as a defect
            confined to the beneficiation path
  v1.17.4   ImportError: No module named master -- a harness that loads the
            pipeline through spec_from_file_location never puts it in
            sys.modules, so _spawn_environment cannot pin it and every worker
            tries to rebuild the parent from a module it cannot import
  v1.17.5   KeyError on mining_hardware_kg -- the rig is a CONFIG CONSTANT and
            not an output column, so the mass-ledger identity as CLAUDE.md
            states it does not run verbatim against the CSV
  1.17.7    cost_revenue_ratio -- there is no such column; the objective is
            total_cost_usd / gross_value_usd
  1.17.7    median improvement quoted as median(1/r - 1) = 74.0%, where
            CLAUDE.md's committed convention is median(1 - r) = 42.5%
  1.17.7    column_diff compared two Series directly, so pandas aligned them on
            the index LABEL -- and build_profitability_catalog returns rows
            SORTED by the objective, so a live frame's index is scrambled while
            the same frame re-read from CSV has a fresh RangeIndex.  Every float
            column read as differing while the file hashed identical.  Found by
            this file on the first run it was written for, and the reason both
            a hash AND a column diff are reported: when they disagree, the hash
            is the one that is right.
  1.17.7    pd.read_csv without float_precision="round_trip".  The default C
            parser is a FAST float reader that is not correctly rounded, so a
            baseline read back came out one ULP off what was written --
            119898.18458829961 -> 119898.1845882996.  Same symptom as the row
            above (64 of 139 columns DIFFER against four byte-identical
            hashes) and a completely different cause, so it had to be
            diagnosed twice.  Neither the default nor "high" round-trips.
  1.17.7    the empty string compared as different from NaN.  An all-empty
            object column (payload_mix, payload_dominant_phase on a raw cell)
            writes as bare commas and reads back as float64-of-NaN, so a live
            "" met a nan.  A CSV cannot represent that difference, so the hash
            cannot see it either -- and a comparator stricter than the artefact
            it compares reports failures that do not exist.

Traps 9, 10 and 11 are three DIFFERENT causes of one identical symptom: columns
reported as DIFFER beside a byte-identical hash.  Each had to be found
separately, because fixing one moved the count and nothing else.  That is the
argument for the whole file.

Each is defended against below, at the line that would otherwise reproduce it.
Add to that list rather than starting a twelfth harness.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.abspath(__file__))


# -----------------------------------------------------------------------------
# LOADING THE PIPELINE
# -----------------------------------------------------------------------------
def load_master():
    """Import the built master.py in the one way the worker pool tolerates.

    MUST be `import master` by name with the repo on sys.path.  Loading it
    through spec_from_file_location("master", path) + exec_module works
    perfectly in serial and then fails in the pool: the module never lands in
    sys.modules under its own __name__, so _spawn_environment's `own` resolves
    to None, `pin` is False, and every worker executes THIS FILE as __main__
    instead -- that is, re-runs the whole verification once per worker.  The
    assert is what turns that into a failure rather than a mystery.
    """
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        import master as m
    assert sys.modules.get("master") is m and m.__spec__ is not None, (
        "master must be imported BY NAME with the repo on sys.path -- see "
        "_spawn_environment in calc.py"
    )
    return m


# -----------------------------------------------------------------------------
# CELLS
# -----------------------------------------------------------------------------
# The four cells every release in CLAUDE.md is verified on, at the caps it uses.
# Beneficiated cells run at 150 rows because they are ~7x raw; raw at 400.
CELLS: Dict[str, Dict[str, Any]] = {
    "raw":          dict(use_beneficiation=False, optimise_programme_scale=False,
                         eval_row_cap=400),
    "raw+search":   dict(use_beneficiation=False, optimise_programme_scale=True,
                         eval_row_cap=400),
    "benef":        dict(use_beneficiation=True,  optimise_programme_scale=False,
                         eval_row_cap=150),
    "benef+search": dict(use_beneficiation=True,  optimise_programme_scale=True,
                         eval_row_cap=150),
}

# BOTH of these come out before hashing, and the second is the one that has
# already cost a release.  pipeline_version is obvious.  catalog_date is stamped
# from the wall clock, so a run that straddles midnight disagrees with itself --
# and a full beneficiated cell is ~10 h, so a full-catalog 2x2 CANNOT be run
# inside one calendar date.  Any comparison of those cells hits this.
PROVENANCE = ("pipeline_version", "catalog_date")

DESTINATION = "cislunar"      # what the on-disk Stage 2 catalog is priced for


def run_cell(m, name: str, *, workers: int = 1, **override):
    """Build one profitability cell and return the frame.

    delivery_destination is set EXPLICITLY.  CALC_CONFIG defaults to
    earth_surface while the on-disk Stage 2 catalog is whatever destination was
    last built, so importing calc and calling straight off gives a mismatched
    run that prices the cargo at one place and pays to deliver it to another.
    destination_check() shouts on STDOUT -- exactly where a harness that filters
    output is least likely to be listening -- so the shout is asserted on rather
    than hoped for.
    """
    spec = dict(CELLS[name])
    spec.update(override)

    C = m.CALC_CONFIG
    C.delivery_destination    = DESTINATION
    C.eval_row_sampling       = "stride"
    C.parallel_workers        = workers
    C.prune_infeasible_combos = True
    for k, v in spec.items():
        setattr(C, k, v)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        df = m.build_profitability_catalog(C)
    if "MISMATCH" in buf.getvalue():
        raise AssertionError(
            f"destination mismatch in cell {name!r}: the Stage 2 catalog on "
            f"disk is not priced for {DESTINATION}"
        )
    return df


# -----------------------------------------------------------------------------
# COMPARING TWO RUNS
# -----------------------------------------------------------------------------
def _comparable(df):
    """The frame with every provenance column removed.

    Column ORDER is left alone deliberately.  Sorting them would be tidier and
    would silently make every hash this file prints incomparable with the eight
    already committed in CLAUDE.md -- which is the whole point of printing one.
    """
    return df[[c for c in df.columns if c not in PROVENANCE]]


def _csv(df) -> str:
    """The canonical text a cell hashes to.

    The baseline stored on disk IS these bytes, so a hash comparison is a byte
    comparison of the file and needs no parsing at all -- which is why the hash
    is the authority here and the column diff is the diagnostic.

    to_csv writes floats at repr precision, so nothing is lost on the way OUT.
    Reading them back is the lossy direction: see _read_baseline.
    """
    return _comparable(df).to_csv(index=False)


def cell_hash(df) -> str:
    return hashlib.sha256(_csv(df).encode("utf-8")).hexdigest()[:16]


def column_diff(a, b) -> Tuple[int, int, List[str]]:
    """(identical, compared, differing) over the shared non-provenance columns.

    Compared POSITIONALLY, via .to_numpy(), and that is not a detail.
    build_profitability_catalog returns its rows SORTED by the objective, so a
    live frame carries a scrambled index while the same frame re-read from CSV
    carries a fresh RangeIndex.  Comparing the two Series directly makes pandas
    align on the index LABEL, so nearly every float column reports as differing
    while the file hashes identical -- which is the ninth entry in this file's
    header, found by this very function on the run it was written for.  The
    hash said MATCH and the column diff said DIFFER, and the hash was right.

    Nulls are normalised to one spelling before comparing.  A parquet round trip
    renders a None in an object column back as nan, so a naive per-column
    astype(str) reports thrust_scaling, isru_feed_material and name as differing
    when they are identical -- v1.17.1 lost time to exactly that.
    """
    shared = [c for c in a.columns if c in b.columns and c not in PROVENANCE]
    differing = []
    for c in shared:
        x, y = a[c], b[c]
        if len(x) != len(y):
            differing.append(c)
            continue
        if x.dtype.kind == "f" and y.dtype.kind == "f":
            xv, yv = x.to_numpy(), y.to_numpy()
            same = bool(((xv == yv) | (_isnan(xv) & _isnan(yv))).all())
        else:
            same = _blanks(x) == _blanks(y)
        if not same:
            differing.append(c)
    return len(shared) - len(differing), len(shared), differing


def _blanks(s) -> list:
    """A column as a list with every spelling of "nothing here" collapsed to None.

    None, NaN and the EMPTY STRING all become None, and that last one is trap
    #11.  An all-empty object column written by to_csv is a run of bare commas,
    and read_csv types that column as float64-of-NaN -- so a live `""` comes
    back as `nan` and a naive comparison calls them different.  They are not:
    a CSV cannot represent the difference, so the file's own hash cannot see it
    either, and a comparator stricter than the artefact it compares reports
    failures that do not exist.  `payload_mix` and `payload_dominant_phase` are
    empty on every row of a raw cell and were the last two columns to fall.
    """
    return [None if (v is None or v != v or v == "") else v
            for v in s.to_numpy().tolist()]


def _isnan(v):
    import numpy as np
    return np.isnan(v)


def _read_baseline(pd, path):
    """Read a baseline cell back WITHOUT losing the last bit of every float.

    float_precision="round_trip" is mandatory, and leaving it off is trap #10 in
    the header.  pandas' default C parser is a fast float reader that is NOT
    correctly rounded, so it returns a float64 one ULP away from the one that
    was written -- `119898.18458829961` comes back as `119898.1845882996`.
    Neither "high" nor the default round-trips; only "round_trip" does.

    That produced the same symptom as trap #9 and had to be diagnosed
    separately: 64 of 139 columns reported as DIFFER while all four cells
    hashed byte-identical to the baseline.  Same family as the pyarrow CSV
    engine v1.17.4 measured and rejected -- a different float parser rounding
    differently in the last ULP -- and the same lesson: a comparison is only as
    exact as the slackest step in it.

    NOTE this says nothing about the pipeline itself.  load_all_catalogs reads
    with the default parser too, so the model's inputs go through the same
    slightly-inexact reader on every run -- which is deterministic, and is
    therefore why bit-identity holds at all.  Do not "fix" that: changing
    float_precision there would move every number in the model.
    """
    return pd.read_csv(path, low_memory=False, float_precision="round_trip")


# -----------------------------------------------------------------------------
# THE FIVE CHECKS
# -----------------------------------------------------------------------------
def check_mass_ledger(m, frames: Dict[str, Any]) -> bool:
    """hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg.

    The rig is a CONFIG CONSTANT, not an output column.  The identity as
    CLAUDE.md states it raises KeyError if run verbatim against the CSV, which
    is what happened on v1.17.5's first attempt.
    """
    rig = m.CALC_CONFIG.mining_hardware_kg
    ok = True
    for name, df in frames.items():
        if df.empty:
            print(f"  {name:13s} (no rows)")
            continue
        err = float((df["hardware_total_kg"] - rig
                     - df["power_system_kg"] - df["ep_system_kg"]).abs().max())
        good = err < 1e-6
        ok &= good
        print(f"  {name:13s} max |error| {err:.9f} kg  {'OK' if good else 'FAIL'}")
    return ok


def _ratio(df):
    """The objective this project ranks on.

    There is no cost_revenue_ratio column.  Rank by
    total_cost_usd / gross_value_usd: ranking by profit_usd degenerates into a
    pure cost ranking, which is a delta-v table wearing a profit label.
    """
    return df["total_cost_usd"] / df["gross_value_usd"]


# Both never-worse comparisons join two cells on `designation`, so the two
# sides must be sampled at the SAME cap or the join is a subset of the smaller
# one and the counts mean nothing.  The bit-identity cells above deliberately
# do not share a cap (beneficiated is ~7x raw, so it runs at 150), which is why
# this check runs its own.  400 is the cap the committed figures use.
NEVER_WORSE_CAP = 400


def check_never_worse(m) -> bool:
    """Both invariants: beneficiated <= raw, and searched <= N = 1.

    "median improvement" is median(1 - searched/unsearched) -- the fractional
    REDUCTION in the ratio.  median(1/r - 1) is a different number for the same
    result (42.5% against 74.0%) and is not the convention the committed
    figures use.
    """
    cap = dict(eval_row_cap=NEVER_WORSE_CAP)
    side = {name: run_cell(m, name, **cap)
            for name in ("raw", "benef", "raw+search", "benef+search")}

    ok = True
    pairs = (("benef",        "raw",   "benef <= raw"),
             ("raw+search",   "raw",   "search <= N=1"),
             ("benef+search", "benef", "search <= N=1 (benef)"))
    for lo, hi, label in pairs:
        a, b = side[hi], side[lo]
        if a.empty or b.empty:
            continue
        j = (a[["designation"]].assign(r_hi=_ratio(a))
             .merge(b[["designation"]].assign(r_lo=_ratio(b)), on="designation"))
        if j.empty:
            continue
        r = j["r_lo"] / j["r_hi"]
        worse = int((r > 1 + 1e-12).sum())
        ok &= worse == 0
        print(f"  {label:22s} pairs {len(j):5d} | max {r.max():.6f} | "
              f"worse {worse} | declined {int((r == 1.0).sum()):4d} | "
              f"median +{(1 - r).median() * 100:.1f}%")
    return ok


def check_prune(m, names: List[str],
                already: Optional[Dict[str, Any]] = None) -> bool:
    """The pre-filter must agree with the unpruned search, column for column.

    Required after ANY change to _combo_can_close, _combo_close_terms,
    _closes_with, _closes_carrying_its_own_stage or anything they read.  Those
    are two statements of the same algebra, kept adjacent on purpose; this is
    the diff that says so when they drift apart.

    `already` lets check 1 hand over the prune-ON cells it has just built --
    they are the same run with the same config, so rebuilding them would be
    four more catalog loads for four identical frames.  The prune-OFF side is
    always built here, and it is the slow half anyway: turning the pre-filter
    off is what v1.14.1 and v1.17.4 exist to avoid.
    """
    already = already or {}
    ok = True
    for name in names:
        on = already.get(name)
        if on is None:
            on = run_cell(m, name)
        off = run_cell(m, name, prune_infeasible_combos=False)
        m.CALC_CONFIG.prune_infeasible_combos = True
        same, total, diff = column_diff(_comparable(on), _comparable(off))
        h1, h2 = cell_hash(on), cell_hash(off)
        good = (h1 == h2) and not diff
        ok &= good
        print(f"  {name:13s} {same}/{total} identical | {h1} vs {h2} | "
              f"{'MATCH' if good else 'DIFFER ' + ','.join(diff[:4])}")
    return ok


def check_parallel(m, names: List[str], workers: int = 8) -> bool:
    """Serial and parallel must be byte-identical.

    Required after any change to the search, and the check that catches a worker
    seeing different reference data from its parent -- module-level memos are
    PER PROCESS, and several are attached to the propellant and vehicle dicts
    that get pickled across the boundary.

    More workers is not always faster.  On a small cap the 862 MB catalog load
    and ~1.1 s per-worker startup dominate, and 8 workers regularly comes out
    SLOWER than serial.  The hash is what this check is for; the wall clock is
    not a result.
    """
    ok = True
    for name in names:
        t0 = time.perf_counter(); a = run_cell(m, name, workers=1)
        ta = time.perf_counter() - t0
        t0 = time.perf_counter(); b = run_cell(m, name, workers=workers)
        tb = time.perf_counter() - t0
        h1, h2 = cell_hash(a), cell_hash(b)
        good = h1 == h2
        ok &= good
        print(f"  {name:13s} serial {ta:6.1f}s | {workers}w {tb:6.1f}s | "
              f"{len(a):4d} rows | {h1} {'MATCH' if good else 'DIFFER'}")
    return ok


# -----------------------------------------------------------------------------
# BASELINE
# -----------------------------------------------------------------------------
def baseline_dir(tag: str) -> str:
    return os.path.join(REPO, ".verify", f"baseline-{tag}")


def _cell_file(d: str, name: str) -> str:
    return os.path.join(d, name.replace("+", "_") + ".csv")


def cmd_baseline(args) -> int:
    m = load_master()
    d = baseline_dir(args.tag)
    os.makedirs(d, exist_ok=True)
    index: Dict[str, Any] = {}
    print(f"\nBaseline -> {d}\n")
    for name in args.cells:
        t0 = time.perf_counter()
        df = run_cell(m, name)
        text = _csv(df)
        with open(_cell_file(d, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        index[name] = {"sha16": h, "rows": int(len(df)),
                       "cap": CELLS[name]["eval_row_cap"]}
        print(f"  {name:13s} {len(df):4d} rows | {h} | "
              f"{time.perf_counter() - t0:5.1f}s")
    index["_meta"] = {"destination": DESTINATION,
                      "calc_version": m.CALC_CONFIG.pipeline_version}
    with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    print(f"\nWrote {len(args.cells)} cells at calc "
          f"{index['_meta']['calc_version']}")
    return 0


def cmd_check(args) -> int:
    import pandas as pd

    m = load_master()
    d = baseline_dir(args.tag)
    index: Dict[str, Any] = {}
    if os.path.isfile(os.path.join(d, "index.json")):
        with open(os.path.join(d, "index.json"), encoding="utf-8") as f:
            index = json.load(f)
    else:
        print(f"\n(no baseline at {d} -- check 1 will only report hashes)")

    ok = True
    frames: Dict[str, Any] = {}

    was = index.get("_meta", {}).get("calc_version", "?")
    print(f"\n1. BIT-IDENTITY vs baseline "
          f"(calc {was} -> {m.CALC_CONFIG.pipeline_version})")
    for name in args.cells:
        df = run_cell(m, name)
        frames[name] = df
        h = cell_hash(df)
        if name not in index:
            print(f"  {name:13s} {len(df):4d} rows | {h} | (not in baseline)")
            continue
        old = _read_baseline(pd, _cell_file(d, name))
        same, total, diff = column_diff(_comparable(df), old)
        good = (h == index[name]["sha16"]) and not diff
        ok &= good
        print(f"  {name:13s} {same}/{total} identical | {h} | "
              f"{'MATCH' if good else 'DIFFER ' + ','.join(diff[:4])}")

    print("\n2. PRUNE ON vs OFF")
    if "prune" in args.skip:
        print("  (skipped)")
    else:
        ok &= check_prune(m, args.cells, already=frames)

    print("\n3. SERIAL vs PARALLEL")
    if "parallel" in args.skip:
        print("  (skipped)")
    else:
        searched = [c for c in args.cells if "search" in c]
        ok &= check_parallel(m, searched or args.cells[:1])

    print("\n4. MASS LEDGER")
    ok &= check_mass_ledger(m, frames)

    print("\n5. NEVER-WORSE")
    ok &= check_never_worse(m)

    print("\n" + ("ALL CHECKS PASSED" if ok else "*** FAILURES ABOVE ***"))
    return 0 if ok else 1


def cmd_invariants(args) -> int:
    """Checks 4 and 5 only -- no baseline needed, so this runs on any tree."""
    m = load_master()
    frames = {name: run_cell(m, name) for name in args.cells}
    print("\n4. MASS LEDGER")
    ok = check_mass_ledger(m, frames)
    print("\n5. NEVER-WORSE")
    ok &= check_never_worse(m)
    print("\n" + ("OK" if ok else "*** FAILURES ABOVE ***"))
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Release verification harness (see the module docstring).")
    p.add_argument("command", choices=("baseline", "check", "invariants"))
    p.add_argument("--tag", default="head",
                   help="baseline name under .verify/ (default: head)")
    p.add_argument("--cells", nargs="+", default=list(CELLS),
                   choices=list(CELLS), metavar="CELL",
                   help="subset of: " + ", ".join(CELLS))
    p.add_argument("--skip", nargs="*", default=[], choices=("prune", "parallel"),
                   help="checks to skip while iterating")
    args = p.parse_args(argv)
    return {"baseline": cmd_baseline,
            "check": cmd_check,
            "invariants": cmd_invariants}[args.command](args)


if __name__ == "__main__":
    # The guard is load-bearing: check 3 starts a process pool, and on Windows a
    # worker rebuilds the parent by importing __main__.
    raise SystemExit(main())
