# -*- coding: utf-8 -*-
"""Run ONE campaign cell: (destination x beneficiation x programme search).

Copies the frozen Stage 2 catalog for the destination into place, runs Stage 4
only, times it, extracts the headline + population statistics, archives the
output CSV gzipped, and appends one row to campaign/results.csv.

Stages 1 and 3 are NEVER run here.  Stage 2 is never re-fetched -- it is copied
from campaign/stage2/, which was priced once on 2026-08-23 for all five
destinations with verified-identical live prices.

    py campaign/run_cell.py <destination> <raw|benef> <off|on>
"""
import csv
import gzip
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMP = os.path.join(ROOT, "campaign")
OUT = os.path.join(ROOT, "asteroid_pipeline", "profitability_catalog.csv")
STAGE2_LIVE = os.path.join(ROOT, "asteroid_pipeline", "mineral_value_catalog.csv")
LEDGER = os.path.join(CAMP, "results.csv")

FIELDS = [
    "cell", "destination", "ore", "search", "started", "wall_s", "rc",
    "rows_out", "evaluable", "best_obj", "winner", "winner_name", "spectral",
    "vehicle", "propellant", "conc_ratio", "power_source",
    "programme_missions", "fleet_ships", "missions_per_ship", "trips_per_ship",
    "programme_span_yr", "payload_kg", "saturation", "p_mining",
    "aerocapture_share", "rtg_share", "isru_share",
    "prop_shares", "vehicle_shares",
    "calc_version", "catalog_date", "archive",
]


def extract(path, dest, ore, search):
    import pandas as pd
    p = pd.read_csv(path, low_memory=False)
    p["_obj"] = p["total_cost_usd"] / p["gross_value_usd"]
    ok = p[p["_obj"].notna() & (p["_obj"] > 0)]
    b = ok.nsmallest(1, "_obj").iloc[0]

    def share(col, val=None, true_like=False):
        if col not in p.columns:
            return ""
        s = p[col]
        if true_like:
            return round(100.0 * s.astype(str).str.lower().isin(["true", "1", "1.0"]).mean(), 4)
        return round(100.0 * (s == val).mean(), 4)

    def top_shares(col, n=6):
        if col not in p.columns:
            return ""
        vc = p[col].value_counts(normalize=True).head(n) * 100
        return "; ".join(f"{k}={v:.2f}%" for k, v in vc.items())

    return {
        "rows_out": len(p),
        "evaluable": int(ok.shape[0]),
        "best_obj": f"{b['_obj']:.4f}",
        "winner": b.get("designation"),
        "winner_name": b.get("name"),
        "spectral": b.get("spectral_type"),
        "vehicle": b.get("vehicle"),
        "propellant": b.get("propellant"),
        "conc_ratio": round(float(b.get("concentration_ratio", float("nan"))), 4),
        "power_source": b.get("power_source"),
        "programme_missions": b.get("programme_missions"),
        "fleet_ships": b.get("fleet_ships"),
        "missions_per_ship": b.get("missions_per_ship"),
        "trips_per_ship": b.get("trips_per_ship"),
        "programme_span_yr": round(float(b.get("programme_span_yr", float("nan"))), 4),
        "payload_kg": round(float(b.get("max_payload_kg", float("nan"))), 2),
        "saturation": round(float(b.get("saturation_multiplier", float("nan"))), 4),
        "p_mining": round(float(b.get("p_mining", float("nan"))), 4),
        "aerocapture_share": share("aerocapture_return", true_like=True),
        "rtg_share": share("power_source", "rtg"),
        "isru_share": (round(100.0 * (p["isru_propellant_kg"].fillna(0) > 0).mean(), 4)
                       if "isru_propellant_kg" in p.columns else ""),
        "prop_shares": top_shares("propellant"),
        "vehicle_shares": top_shares("vehicle"),
        "calc_version": str(p["pipeline_version"].iloc[0]) if "pipeline_version" in p.columns else "",
        "catalog_date": str(p["catalog_date"].iloc[0]) if "catalog_date" in p.columns else "",
    }


def main():
    dest, ore, search = sys.argv[1], sys.argv[2], sys.argv[3]
    assert ore in ("raw", "benef") and search in ("off", "on")
    cell = f"{dest}__{ore}__search-{search}"

    src2 = os.path.join(CAMP, "stage2", f"mineral_value_catalog.{dest}.csv")
    if not os.path.exists(src2):
        sys.exit(f"missing frozen Stage 2 catalog: {src2}")
    shutil.copyfile(src2, STAGE2_LIVE)

    cmd = [
        "py", os.path.join(ROOT, "run_pipeline.py"),
        "--stages", "4", "--destination", dest, "--rows", "0",
        "--workers", "12", "--yes",
        "--beneficiated" if ore == "benef" else "--raw",
        "--search" if search == "on" else "--no-search",
    ]
    log = os.path.join(CAMP, "logs", f"{cell}.log")
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{started}] START {cell}", flush=True)
    print("  " + " ".join(cmd), flush=True)

    t0 = time.time()
    with open(log, "w", encoding="utf-8", errors="replace") as fh:
        rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT)
    wall = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] DONE  rc={rc} wall={wall:,.0f}s ({wall/3600:.2f} h)", flush=True)

    row = {f: "" for f in FIELDS}
    row.update(cell=cell, destination=dest, ore=ore, search=search,
               started=started, wall_s=round(wall, 1), rc=rc, archive="")

    if rc == 0 and os.path.exists(OUT):
        arch = os.path.join(CAMP, "cells", f"{cell}.csv.gz")
        with open(OUT, "rb") as fi, gzip.open(arch, "wb", compresslevel=6) as fo:
            shutil.copyfileobj(fi, fo, length=16 << 20)
        row["archive"] = os.path.relpath(arch, ROOT)
        try:
            row.update(extract(OUT, dest, ore, search))
        except Exception as exc:                      # noqa: BLE001
            print(f"  !! extraction failed: {exc}", flush=True)
        print(f"  best {row['best_obj']}x | evaluable {row['evaluable']:,} | "
              f"winner {row['winner']} ({row['spectral']}) | archive {row['archive']}", flush=True)
    else:
        print(f"  !! cell FAILED (rc={rc}); see {log}", flush=True)

    new = not os.path.exists(LEDGER) or os.path.getsize(LEDGER) == 0
    with open(LEDGER, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"  ledger += {cell}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
