# -*- coding: utf-8 -*-
"""transportation, Module 3 of the Asteroid Profitability Pipeline.

THE TABLES ARE NOT IN THIS FILE ANY MORE.  They live in `spacecost`, an
independent package, and this module is the adapter that drives it:

    https://github.com/loggger101/spacecost

Why they left.  Two thirds of this module was annotated reference data --
launch vehicles, propellants, delta-v segments, operational costs and storage
systems, every row cited -- and nothing in its schema knew what an asteroid
was.  A launch price is useful to anyone costing a mission, so the tables
became a package other projects can cite, and this pipeline became its
first consumer.  The table sizes are not spelled here; the ready banner
prints them.

WHAT THIS FILE STILL OWNS, and why each did not move:

    two defaults        `TransportConfig` is spacecost's `SpacecostConfig`
                        with two defaults this project's rather than a
                        library's: `output_dir` points into
                        `asteroid_pipeline/`, and `quote_snapshot` names the
                        recorded fuel quotes the tables are priced from.
                        Every other field, its default and its dashboard help
                        are the package's
    the RUN & PREVIEW    the standalone-module behaviour every stage here has

THE CSVs ARE THE PACKAGE'S, BYTE FOR BYTE.  spacecost was extracted by slicing
source line ranges rather than by re-typing anything, and this module passes
its config straight to `spacecost.build_catalog`.

`pipeline_version` IS NOT A NUMBER THIS MODULE OWNS.  It is spacecost's DATA
CONTRACT, inherited with the config, so it moves when the package's moves and
at no other time.  What each repin moved, and which frozen set it left under
`campaign/stage3/`, is in versions.md's
[Stage 3 changelog](../versions.md#stage-3-changelog-modulestransportationpy).

RE-RUNNING STAGE 3 IS SAFE.  Since spacecost v0.14.0 it prices fuel from a
recorded quote snapshot (`quote_snapshot` below) rather than fetching live, so
a re-run rebuilds the same tables byte for byte, on any day and offline.  It
used to re-fetch live fuel prices over the only copy of the tables every
committed measurement and every `.verify` baseline was taken against, which is
why `campaign/stage3/` holds hand-frozen copies; those stay as history.

Active sources:
    - spacecost (the reference tables, cited per row)  launch, propellant,
                                                       dv, operational,
                                                       storage, environments
    - spacecost's recorded fuel quotes                 Yahoo Finance closes of
                                                       HO=F (RP-1) and NG=F
                                                       (methane), recorded once

Pipeline flow:
    Recorded fuel quotes  ->  Load spacecost tables  ->  Merge  ->  Validate
                          ->  Compute normalised cost-per-dv  ->  Export
"""

# ─────────────────────────────────────────────────────────────────────────────
# INSTALLATION
# ─────────────────────────────────────────────────────────────────────────────
try:
    from . import _runtime
except ImportError:                 # run as a script: modules/ is on sys.path
    import _runtime

_REQUIRED_PKGS = ["requests", "pandas", "numpy", "spacecost"]
_runtime.install(_REQUIRED_PKGS)


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import os
import sys
import warnings
from dataclasses import dataclass
from typing import Dict

import pandas as pd

import spacecost

for _cat in (DeprecationWarning, FutureWarning, UserWarning):
    warnings.filterwarnings("ignore", category=_cat)

pd.set_option("display.max_columns", None)
pd.set_option("display.float_format", "{:.4g}".format)


# ═════════════════════════════════════════════════════════════════════════════
#                                                                             #
#      USER SETTINGS, EDIT THESE TO TUNE THE PIPELINE                         #
#                                                                             #
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class TransportConfig(spacecost.SpacecostConfig):
    """Stage 3's dials: spacecost's own, with the two defaults that are this
    pipeline's.  The dashboard shows each field's help from spacecost's
    config.py, and these two from here."""

    # ─── SOURCE TOGGLES ──────────────────────────────────────────────────────
    # The recorded fuel quotes Stage 3 prices from: a snapshot committed in
    # spacecost (spacecost/quotes/), so re-running Stage 3 rebuilds the same
    # tables, offline, on any day.  Every current measurement was taken on
    # tables built from `fuel-2026-10-17`'s closes, so pinning it moved no
    # number.  A newer snapshot is a repin that moves prices: record
    # it in versions.md.  `use_yfinance` (off) fetches today's quotes instead,
    # which nothing can reproduce; spacecost refuses the two together.
    quote_snapshot: str = "fuel-2026-10-17"

    # ─── OUTPUT ──────────────────────────────────────────────────────────────
    # The seven CSVs land in `<output_dir>/transportation/`, where Stage 4
    # reads them.
    output_dir:   str = _runtime.DEFAULT_OUTPUT_DIR

CONFIG = TransportConfig()
os.makedirs(os.path.join(CONFIG.output_dir, CONFIG.subdir), exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# THE REFERENCE TABLES, RE-EXPORTED
# ─────────────────────────────────────────────────────────────────────────────
# The same objects, not copies.  They are re-exported rather than reached
# through `spacecost.` because things read them as attributes of THIS module:
# `verify_docs.py` check 3 holds README's row counts to them, Stage 2 and
# Stage 4 read the delta-v, launch and storage rows in master.py, and the
# banner below counts all six.
#
# ⚠️  ONLY WHAT SOMETHING READS.  Until master v1.36.0 this block mirrored the
# package's whole surface -- unit constants, every loader, the rocket-equation
# and query helpers -- "so that a consumer never re-derives what it cannot
# see".  Nothing here or in master.py read eleven of them; they were a second
# listing of spacecost's `__all__`, which is the one to read.  Reach anything
# else through `spacecost.`, and add a line here only for a reader.
LAUNCH_VEHICLES_REFERENCE   = spacecost.LAUNCH_VEHICLES_REFERENCE
PROPELLANTS_REFERENCE       = spacecost.PROPELLANTS_REFERENCE
DELTA_V_REFERENCE           = spacecost.DELTA_V_REFERENCE
OPERATIONAL_COSTS_REFERENCE = spacecost.OPERATIONAL_COSTS_REFERENCE
STORAGE_REFERENCE           = spacecost.STORAGE_REFERENCE
ENVIRONMENTS_REFERENCE      = spacecost.ENVIRONMENTS_REFERENCE


# Sanity bands over the loaded tables; prints warnings and never raises.  An
# ALIAS rather than a wrapper, because a function whose whole body forwards its
# arguments is a layer with no reader: `help()` on it would show this file's
# paraphrase instead of the real docstring.
#
# Module 2 defines a `validate` too, so `master.validate` is refused as
# ambiguous; master.py binds this one as `validate_transport`.
validate = spacecost.validate


def build_transportation_catalog(
    config: TransportConfig = CONFIG,
) -> Dict[str, pd.DataFrame]:
    """Run Stage 3: build every reference table and write the seven CSVs.

    Delegates to `spacecost.build_catalog`, which is the same code this file
    used to hold: six reference tables and the composite summary.

    Returns a dict of frames:
        {launch_vehicles, propellants, delta_v_segments, operational_costs,
         storage_systems, environments, summary}

    `environments` arrived with the v1.15.0 contract and is the one key a
    caller written against v1.14.0 will not know.  Nothing in Stage 4 reads
    it; it is returned because a build that writes a file and leaves it out of
    its own return value has two answers to what it built.
    """
    # A library is silent by default and a pipeline STAGE reports progress, so
    # verbosity is turned on for the call and put back afterwards.  Restored in
    # a `finally` because an exception here must not leave the package chatty
    # for whatever runs next in the same process -- the dashboard, for one.
    spacecost.set_verbose(True)
    try:
        return spacecost.build_catalog(config)
    finally:
        spacecost.set_verbose(False)


print(f"OK  Stage 3 ready - spacecost {spacecost.__version__}, "
      f"data contract {spacecost.DATA_VERSION}")
print(f"    Tables    : {len(LAUNCH_VEHICLES_REFERENCE)} vehicles, "
      f"{len(PROPELLANTS_REFERENCE)} propellants, "
      f"{len(DELTA_V_REFERENCE)} dv segments, "
      f"{len(OPERATIONAL_COSTS_REFERENCE)} ops rows, "
      f"{len(STORAGE_REFERENCE)} storage systems, "
      f"{len(ENVIRONMENTS_REFERENCE)} environments")
print(f"    Output dir: {os.path.join(CONFIG.output_dir, CONFIG.subdir)}")


# ─────────────────────────────────────────────────────────────────────────────
# RUN & PREVIEW
# ─────────────────────────────────────────────────────────────────────────────
# Only self-runs when executed directly; importing this module is side-effect free.
if __name__ == "__main__":

    if not _runtime.confirm_overwrite(
            [os.path.join(CONFIG.output_dir, CONFIG.subdir, f)
                   for f in ("launch_vehicles.csv", "propellants.csv",
                             "delta_v_segments.csv", "operational_costs.csv",
                             "storage_systems.csv", "environments.csv",
                             "transportation_summary.csv")],
            "Stage 3 rebuilds every reference table from fuel quotes %s."
            % CONFIG.quote_snapshot):
        print("  Cancelled; nothing was fetched and nothing was written.")
        sys.exit(1)

    catalog = build_transportation_catalog(CONFIG)

    if catalog and not catalog["launch_vehicles"].empty:
        print(f"\n{'='*75}")
        print("    LAUNCH VEHICLES - cheapest $/kg-to-LEO first")
        print(f"{'='*75}")
        lv_cols = ["name", "operator", "status", "payload_leo_kg",
                   "usd_per_kg_to_leo", "usd_per_kg_to_gto", "usd_per_kg_to_escape"]
        print(catalog["launch_vehicles"].sort_values("usd_per_kg_to_leo")[
            lv_cols
        ].head(CONFIG.preview_rows).to_string(index=False))

        print(f"\n{'='*75}")
        print("    PROPELLANTS - Isp, density, cost  (live where available)")
        print(f"{'='*75}")
        p_cols = ["name", "type", "isp_vac_s", "density_kg_per_L",
                  "cost_usd_per_kg", "cost_usd_per_L", "price_basis"]
        print(catalog["propellants"][p_cols].to_string(index=False))

        print(f"\n{'='*75}")
        print("    PROPELLANT COST PER kg OF PAYLOAD - at dv = 6 500 m/s "
              "(median NEA)")
        print(f"{'='*75}")
        print(spacecost.cheapest_propellant_for(catalog, 6_500)
              .to_string(index=False))
