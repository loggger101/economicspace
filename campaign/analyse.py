# -*- coding: utf-8 -*-
"""Build a destination's 2x2 table and run the invariants the repo requires.

Definitions are the ones CLAUDE.md pins down, and each has cost someone an hour:
  objective          total_cost_usd / gross_value_usd   (there is NO
                     cost_revenue_ratio column)
  r                  the LOWER setting's ratio over the HIGHER's (benef / raw)
  median improvement median(1 - r), the fractional REDUCTION -- not
                     median(1/r - 1), which reads 74.0% for a 42.5% result
  mass ledger        hardware_total_kg == 2000 (CONFIG constant, not a column)
                     + power_system_kg + ep_system_kg

    py campaign/analyse.py <destination>
    py campaign/analyse.py --all
"""
import gzip
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CELLS = os.path.join(ROOT, "campaign", "cells")
RIG_KG = 2000.0
# ⚠️  The five the campaign measured, not every destination the model has;
# `mars_orbit` and `geo` landed afterwards and have no cells to analyse.  See
# the note in run_queue.py.
DESTS = ["cislunar", "lunar_surface", "leo", "mars_surface", "earth_surface"]


def load(dest, ore, search):
    """One archived cell as a frame, with the objective added, or None if absent.

    `float_precision="round_trip"` is mandatory and is the fourth entry in
    `verify.py`'s table of harness bugs: the default CSV float parser is fast
    rather than correctly rounded and returns a float64 one ULP from the one
    written, so a comparison built on it reports differences that are not there.
    It belongs HERE, in a comparison, and never in Stage 4's own loader, where it
    would move every number in the model.
    """
    p = os.path.join(CELLS, f"{dest}__{ore}__search-{search}.csv.gz")
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rb") as fh:
        df = pd.read_csv(fh, low_memory=False, float_precision="round_trip")
    df["_obj"] = df["total_cost_usd"] / df["gross_value_usd"]
    return df


def best(df):
    """(best objective, evaluable rows) for one cell. Lower is better.

    Evaluable means the objective is finite and positive, which is the same
    population every headline in the docs is quoted over; a row with no feasible
    mission carries NaN and is not a zero.
    """
    ok = df[df["_obj"].notna() & (df["_obj"] > 0)]
    return ok["_obj"].min(), len(ok)


def never_worse(lo, hi, label):
    """lo = the richer option set (must never be worse than hi)."""
    if lo is None or hi is None:
        return f"  {label:34s} -- one side missing"
    a = lo[["designation", "_obj"]].dropna().rename(columns={"_obj": "lo"})
    b = hi[["designation", "_obj"]].dropna().rename(columns={"_obj": "hi"})
    j = a.merge(b, on="designation", how="inner")
    if j.empty:
        return f"  {label:34s} !! EMPTY JOIN -- not a pass"
    r = j["lo"] / j["hi"]
    worse = int((r > 1.0 + 1e-12).sum())
    med = (1.0 - r).median()
    declined = int((r >= 1.0 - 1e-12).sum())
    flag = "OK " if worse == 0 else "!! "
    return (f"  {flag}{label:32s} pairs {len(j):>8,} | max {r.max():.6f} | "
            f"worse {worse} | declined {declined:,} | median +{med*100:.1f}%")


def mass_ledger(df, label):
    """Assert `hardware_total_kg == rig + power_system_kg + ep_system_kg`, exactly.

    The one-line check for CLAUDE.md's first defect class, a mass in one cascade
    with no price in the other. ⚠️  `mining_hardware_kg` is NOT a column: the rig
    is the config constant `RIG_KG`, and writing the assertion verbatim against
    the CSV raises `KeyError`, which it has done to two harnesses.

    An EMPTY frame reports as a failure rather than passing quietly. A check
    that cannot run must never say it passed.
    """
    if df is None:
        return f"  {label:34s} -- missing"
    if df.empty:
        return f"  !! {label:32s} EMPTY -- not a pass"
    err = (df["hardware_total_kg"] - RIG_KG - df["power_system_kg"] - df["ep_system_kg"]).abs()
    mx = err.max()
    flag = "OK " if mx < 1e-6 else "!! "
    return f"  {flag}{label:32s} rows {len(df):>8,} | max |error| {mx:.9f} kg"


def programme_invariants(df, label):
    """The three structural facts a searched cell must satisfy.

    `N == F x W` on every row and `W > trips` never are hard invariants; `W <
    trips` is a COUNT rather than a check, and it is the interesting one,
    because it is the number of bodies that decline to use up the rig. A 400-row
    sample reported it as zero and was read as "the 2-D search is not yet
    load-bearing"; the full population puts it at 2,077 rows at cislunar.

    ⚠️  Only meaningful with the search ON. At N = 1, W = 1 and `trips` is 2-5,
    so a search-OFF cell reports ~100% trivially.
    """
    if df is None or df.empty:
        return f"  {label:34s} -- missing"
    n, f, w = df["programme_missions"], df["fleet_ships"], df["missions_per_ship"]
    t = df["trips_per_ship"]
    nfw = int((n != f * w).sum())
    wgt = int((w > t).sum())
    wlt = int((w < t).sum())
    flag = "OK " if (nfw == 0 and wgt == 0) else "!! "
    return (f"  {flag}{label:32s} N!=FxW {nfw} | W>trips {wgt} | "
            f"W<trips {wlt:,} ({100.0*wlt/len(df):.3f}%) | "
            f"fleet med {f.median():.0f} max {f.max():.0f} | N med {n.median():.0f}")


def report(dest):
    """Print one destination's 2x2 table, then every invariant, to stdout."""
    print(f"\n{'='*78}\n  {dest.upper()}\n{'='*78}")
    cells = {(o, s): load(dest, o, s) for o in ("raw", "benef") for s in ("off", "on")}
    have = {k: v for k, v in cells.items() if v is not None}
    if not have:
        print("  no cells archived yet")
        return

    print("\n  best cost/revenue (lower is better, 1.0 = breakeven)")
    print(f"  {'':14s} {'search OFF (N=1)':>20s} {'search ON':>20s}")
    for o in ("raw", "benef"):
        row = f"  {o:14s}"
        for s in ("off", "on"):
            df = cells[(o, s)]
            row += f" {(f'{best(df)[0]:.4f}x' if df is not None else '-'):>20s}"
        print(row)
    print("\n  evaluable rows")
    for o in ("raw", "benef"):
        row = f"  {o:14s}"
        for s in ("off", "on"):
            df = cells[(o, s)]
            row += f" {(f'{best(df)[1]:,}' if df is not None else '-'):>20s}"
        print(row)

    print("\n  never-worse (a richer option set must never report worse)")
    print(never_worse(cells[("benef", "off")], cells[("raw", "off")], "benef <= raw, search OFF"))
    print(never_worse(cells[("benef", "on")], cells[("raw", "on")], "benef <= raw, search ON"))
    print(never_worse(cells[("raw", "on")], cells[("raw", "off")], "search ON <= OFF, raw"))
    print(never_worse(cells[("benef", "on")], cells[("benef", "off")], "search ON <= OFF, benef"))

    print("\n  mass ledger  hardware_total == 2000 + power + ep")
    for (o, s), df in sorted(have.items()):
        print(mass_ledger(df, f"{o}, search {s}"))

    print("\n  programme structure (searched cells)")
    for o in ("raw", "benef"):
        df = cells[(o, "on")]
        if df is not None:
            print(programme_invariants(df, f"{o}, search on"))


def main():
    """Report on the named destinations, or on all five by default."""
    args = sys.argv[1:]
    targets = DESTS if (not args or args[0] == "--all") else args
    for d in targets:
        report(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
