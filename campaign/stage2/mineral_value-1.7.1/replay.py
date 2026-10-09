"""Rebuild this directory's Stage 2 tables from the quotes one of them recorded.

The 2026-08 campaign (calc 1.17.7) priced five destinations on 2026-08-23
with mineral_value 1.7.1, and only the cislunar table survived, in a local
inputs backup.  It records the five yfinance quotes it used in
`live_price_*`, so the other four are rebuilt by running Stage 2 AS IT WAS
(modules/mineral_value.py at bf1f43d, read out of git) with those quotes fed
back in as the live frame.  Nothing is fetched and nothing under
asteroid_pipeline/ is written.

Two proofs, and the second is the one that matters:

  1. this script rebuilds cislunar too, and it must equal the surviving table
     in every column but `catalog_date`, or the script exits 1;
  2. every 2026-08 archive cell derives against these tables with 0 DIFFER on
     the compared columns, gross value and revenue among them
     (`campaign/verification_sheet.py --check --catalog <cell>`).

The four rebuilt files carry `catalog_date` 2026-08-23, the date their
contents are priced at and the date the originals were written, so
`worked_calculation.run_could_read` offers them to exactly the rows that ran
on them.  Run it to confirm the four committed files are what it builds:

    py campaign/stage2/mineral_value-1.7.1/replay.py
"""
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
COMMIT = "bf1f43d"
DESTS = ("cislunar", "lunar_surface", "leo", "mars_surface", "earth_surface")
DATE = "2026-08-23"


def read(path):
    """A Stage 2 table, read so a float comes back as the float written."""
    return pd.read_csv(path, float_precision="round_trip")


def main():
    """Rebuild every table and compare it with the committed one."""
    work = tempfile.mkdtemp(prefix="mv171_")
    src = os.path.join(work, "mineral_value_171.py")
    with open(src, "w", encoding="utf-8", newline="") as fh:
        fh.write(subprocess.run(
            ["git", "show", "%s:modules/mineral_value.py" % COMMIT],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            check=True).stdout)
    spec = importlib.util.spec_from_file_location("mineral_value_171", src)
    m = importlib.util.module_from_spec(spec)
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(m)
    cfg = m.CONFIG
    assert cfg.pipeline_version == "1.7.1", cfg.pipeline_version

    survivor = read(os.path.join(HERE, "mineral_value_catalog.cislunar.csv"))
    quotes = survivor.loc[survivor["live_price_usd_per_kg"].notna(),
                          ["name", "live_price_usd_per_kg", "live_price_date",
                           "live_price_source"]].reset_index(drop=True)
    m.fetch_yfinance = lambda _config: quotes.copy()
    cfg.use_metals_api = False
    ok = True
    for dest in DESTS:
        out = os.path.join(work, dest)
        os.makedirs(out)
        cfg.output_dir = out
        cfg.delivery_destination = dest
        with contextlib.redirect_stdout(io.StringIO()):
            m.build_mineral_value_catalog(cfg)
        built = read(os.path.join(out, cfg.catalog_filename))
        built["catalog_date"] = DATE
        committed = read(os.path.join(HERE,
                                      "mineral_value_catalog.%s.csv" % dest))
        same = (list(built.columns) == list(committed.columns)
                and built.astype(str).equals(committed.astype(str)))
        print("  %-14s %d rows  %s" % (dest, len(built),
                                       "IDENTICAL" if same else "*** DIFFER ***"))
        ok &= same
    print("OK  every table is what the recorded quotes rebuild" if ok
          else "*** A TABLE IS NOT WHAT THE RECORDED QUOTES REBUILD ***")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
