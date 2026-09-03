# -*- coding: utf-8 -*-
"""Run ONE campaign cell: (destination x beneficiation x programme search).

Copies the frozen Stage 2 catalog for the destination into place, runs Stage 4
only, times it, extracts the headline + population statistics, archives the
output CSV gzipped, and appends one row to campaign/results.csv.

Stages 1 and 3 are NEVER run here.  Stage 2 is never re-fetched -- it is copied
from campaign/stage2/, which was priced once on 2026-08-23 for all five
destinations with verified-identical live prices.

    python campaign/run_cell.py <destination> <raw|benef> <off|on>
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

# The 20-cell campaign was measured at 12 workers, so 12 is what the wall
# clocks in the ledger mean and it stays the default.  CAMPAIGN_WORKERS
# overrides it for a host with a different core count -- the DGX Spark has 20.
# Worker count cannot move a RESULT (verify.py check 3 holds serial and
# parallel to the same hash), so this is a wall-clock dial only; a ledger row
# measured at a different width is still a valid cell, just not a comparable
# time.
WORKERS = int(os.environ.get("CAMPAIGN_WORKERS", "12"))

# `open(log, "w")` and the gzip archive both assume these exist.  They are
# committed with content on this machine but `campaign/cells/` is gitignored,
# so a fresh clone has no `cells/` at all and the first cell dies AFTER paying
# for the run.
for _d in (os.path.join(CAMP, "logs"), os.path.join(CAMP, "cells")):
    os.makedirs(_d, exist_ok=True)

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
    """The headline and population statistics for one finished cell.

    Everything the ledger records about a cell that is not a wall clock: the
    winner and its whole architecture, the programme structure, and the
    population shares (propellant, vehicle, aerocapture, RTG, ISRU).

    The shares are the point, not the headline. A best-case cell is a poor
    detector for anything wrong below the top: v1.12.0's argon fix moved NEITHER
    cislunar headline while changing the chosen propellant for a quarter of the
    catalog, and it was the share breakdown and the evaluable-row count that
    caught it.
    """
    import pandas as pd
    p = pd.read_csv(path, low_memory=False)
    p["_obj"] = p["total_cost_usd"] / p["gross_value_usd"]
    ok = p[p["_obj"].notna() & (p["_obj"] > 0)]
    b = ok.nsmallest(1, "_obj").iloc[0]

    def share(col, val=None, true_like=False):
        """Percentage of rows where `col` equals `val`, as a rounded float.

        `true_like` handles a boolean read back from CSV, which arrives as the
        STRING "True": `.astype(bool)` would read that, and NaN, as True. An
        absent column returns "" rather than 0, because a cell from an older
        build did not measure 0% of anything, it did not have the column.
        """
        if col not in p.columns:
            return ""
        s = p[col]
        if true_like:
            return round(100.0 * s.astype(str).str.lower().isin(["true", "1", "1.0"]).mean(), 4)
        return round(100.0 * (s == val).mean(), 4)

    def top_shares(col, n=6):
        """The n commonest values of `col` as "name=pct%; ..." for the ledger.

        Six is enough for the propellant and vehicle splits every destination
        table in the docs is built from, and it goes into one CSV cell so the
        ledger stays one row per campaign cell.
        """
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
    """Copy the frozen Stage 2 catalog into place, run Stage 4, archive, record.

    The ledger row is appended whether the cell succeeded or failed, with `rc`
    recording which, because that is what makes `run_queue.py` resumable: a
    missing row means "never attempted", not "attempted and lost".

    Stage 2 is COPIED from `campaign/stage2/`, never re-fetched. Re-running
    Stage 3 or a live Stage 2 mid-campaign would move the inputs underneath
    every cell already measured, and the previous prices are not recoverable.
    """
    dest, ore, search = sys.argv[1], sys.argv[2], sys.argv[3]
    assert ore in ("raw", "benef") and search in ("off", "on")
    cell = f"{dest}__{ore}__search-{search}"

    src2 = os.path.join(CAMP, "stage2", f"mineral_value_catalog.{dest}.csv")
    if not os.path.exists(src2):
        sys.exit(f"missing frozen Stage 2 catalog: {src2}")
    shutil.copyfile(src2, STAGE2_LIVE)

    cmd = [
        sys.executable, os.path.join(ROOT, "run_pipeline.py"),
        "--stages", "4", "--destination", dest, "--rows", "0",
        "--workers", str(WORKERS), "--yes",
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
