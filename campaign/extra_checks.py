# -*- coding: utf-8 -*-
"""Two checks CLAUDE.md insists on, across every archived cell.

1. max_fleet_ships ceiling.  Rows at the 64-ship ceiling are bodies whose
   payloads have no finite market to saturate, so the objective is monotone in
   N and the ladder's top rung is where the loop STOPPED -- a diagnostic, not
   an optimum.
2. `replicated`-scaling thrusters (FEEP / PPT / electrospray).  The test is NOT
   "do any survive" -- thruster_kg_per_n is a mass penalty, not a threshold --
   it is "does one ever WIN".
"""
import glob
import gzip
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPL = ("FEEP", "PPT", "electrospray", "Electrospray", "Pulsed plasma")

print(f"{'cell':42s} {'fleet@64':>14s} {'repl rows':>12s} {'best repl':>12s} {'rank':>7s} {'vs best':>8s}")
for p in sorted(glob.glob(os.path.join(ROOT, "campaign", "cells", "*.csv.gz"))):
    cell = os.path.basename(p)[:-7]
    with gzip.open(p, "rb") as fh:
        d = pd.read_csv(fh, low_memory=False, float_precision="round_trip",
                        usecols=["designation", "total_cost_usd", "gross_value_usd",
                                 "propellant", "fleet_ships"])
    d["obj"] = d.total_cost_usd / d.gross_value_usd
    ok = d[d.obj.notna() & (d.obj > 0)].sort_values("obj").reset_index(drop=True)
    ceil_n = int((d.fleet_ships >= 64).sum())
    ceil_s = f"{ceil_n:,} ({100.0*ceil_n/len(d):.2f}%)"
    mask = ok.propellant.astype(str).str.contains("|".join(REPL), case=False, regex=True)
    rep = ok[mask]
    if len(rep):
        rank = int(rep.index[0]) + 1
        print(f"{cell:42s} {ceil_s:>14s} {len(rep):>12,} {rep.obj.iloc[0]:>12.4f} "
              f"{rank:>7,} {rep.obj.iloc[0]/ok.obj.iloc[0]:>7.2f}x")
    else:
        print(f"{cell:42s} {ceil_s:>14s} {0:>12,} {'-':>12s} {'-':>7s} {'-':>8s}")
