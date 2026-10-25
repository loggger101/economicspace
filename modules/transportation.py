# -*- coding: utf-8 -*-
"""transportation, Module 3 of the Asteroid Profitability Pipeline.

THE TABLES ARE NOT IN THIS FILE ANY MORE.  They live in `spacecost`, an
independent package, and this module is the adapter that drives it:

    https://github.com/loggger101/spacecost

Why they left.  Two thirds of this module was annotated reference data --
launch vehicles, propellants, delta-v segments, operational costs and storage
systems, every row cited -- and nothing in its schema knew what an asteroid
was.  The table sizes are not spelled here; the ready banner prints them.  A launch price is useful to anyone costing a mission, so the
tables became a package other projects can cite, and this pipeline became its
first consumer.

AND A TABLE HAS NOW ARRIVED THAT NEVER LIVED HERE, which is the split paying
for itself in the direction nobody designed it for.  spacecost v0.2.0 adds
`environments`: 23 destinations of solar flux, dark period and one-way light
time, the multipliers three `operational_costs` rows are already silent
functions of, since 60 W/kg is a figure AT 1 AU.  Stage 4 derives its own
1/r^2 array scaling and does not read the table, so it moves no number here.
It is re-exported and written like the other five anyway, because a consumer
that can see five tables of six is a consumer that will one day re-derive the
sixth.

WHAT THIS FILE STILL OWNS, and why each did not move:

    TransportConfig     the dials, because two of the defaults are this
                        project's rather than a library's: `output_dir` points
                        into `asteroid_pipeline/`, and `use_yfinance` is True
                        because a pipeline STAGE is expected to fetch, where a
                        library must not
    the output location  where Stage 4 will look for the CSVs
    the RUN & PREVIEW    the standalone-module behaviour every stage here has

THE CSVs ARE UNCHANGED, BYTE FOR BYTE, AND THAT IS THE POINT.  spacecost was
extracted by slicing source line ranges rather than by re-typing anything, and
both its test suite and this repo's `verify_stage3.py` assert every file is
identical through this path and through the package's own.

`pipeline_version` IS NOT A NUMBER THIS MODULE OWNS.  It is spacecost's DATA
CONTRACT, mirrored here, and `verify_stage3.py` check 2 asserts the two are
equal -- so it moves when the package's moves and at no other time.  v0.1.1 ->
v0.2.0 took it 1.14.0 -> 1.15.0 for the sixth table.  No pre-existing VALUE
moved: the five inherited tables are byte-identical to the 1.14.0 build once
the two provenance columns are stripped.

🚨  v0.4.0 TOOK IT 1.15.0 -> 1.16.0 AND VALUES DID MOVE, which is the first
repin since the split that re-prices anything.  The launch table was
re-audited from 36 rows to 76, SLS Block 1B went `concept`, Falcon Heavy
(reusable)'s unsourced 57 t became 30 t, and every ranged figure is now the
geometric centre of its band.  Stage 4 searches every `operational` row, so its
grid went from 17 vehicles to 48.  The paragraph below still holds for a stamp
that moves alone; this one moved rows, so adopting it means re-running Stage 3,
and that is a decision about the baselines rather than a chore.  See
[master v1.35.0](../versions.md#master-v1350--mineral_value-v1100--transportation-v1160).

⚠️  v0.5.0 TOOK IT 1.16.0 -> 1.17.0 AND MOVED ONE COLUMN THAT STAGE 4 READS.
Every `fairing_volume_m3` is now derived from a cited drawing, or left blank
with a reason, under a new `fairing_basis` column.  That is the volume cap
Stage 4 enforces, so adopting it moves any mission the cap binds on; a blank
is still flown at calc's `DEFAULT_FAIRING_VOLUME_M3`.  The grid stays 48
vehicles.  Adopting it on disk is the same decision as v0.4.0's.  See
[master v1.37.0](../versions.md#master-v1370--transportation-v1170--catalog-v160).

v0.5.2 TOOK IT 1.17.0 -> 1.17.2 AND MOVED NO VALUE: notes cells only (v0.5.1's
two withdrawn citations and v0.5.2's twenty-one corrected ones).  Stage 4 reads
no `notes`, so the tables on disk stay at 1.17.0 under the rule below, and the
one `stamp_check()` line that says so is expected.  See
[master v1.44.0](../versions.md#master-v1440--transportation-v1172).

v0.5.3 TOOK IT 1.17.2 -> 1.17.3 AND MOVED NO VALUE: four more notes cells
(Psyche, Didymos and two Mars delta-v rows).  The tables on disk stay where
they are for the same reason.  See
[master v1.45.0](../versions.md#master-v1450--mineral_value-v1123--transportation-v1173).

v0.6.0 TOOK IT 1.17.3 -> 1.18.0 AND MOVED FOUR VALUES: Atlas V 551, Minotaur
IV and Pegasus XL carried to 2026 dollars, and Deep Space Network time
re-derived.  A row changed, so the tables on disk were rebuilt, by REPLAYING
the three fuel quotes the 1.17.0 `propellants.csv` recorded rather than
fetching: every other value is the one those tables held.  The 1.17.0 set is
frozen under `campaign/stage3/spacecost-0.5.0/`.  See
[master v1.46.0](../versions.md#master-v1460--mineral_value-v1130--transportation-v1180).

v0.6.1 TOOK IT 1.18.0 -> 1.18.1 AND MOVED NO VALUE: four notes cells (the
reliability growth exponent, Starship and the two hypergolics).  The tables
on disk stay at 1.18.0 under the rule below.  See
[master v1.48.0](../versions.md#master-v1480--transportation-v1181).

v0.7.0 TOOK IT 1.18.1 -> 1.19.0 AND MOVED TWO PRICES, Electron and Pegasus
XL, neither of which any mission can fly.  A row changed, so the tables on
disk were rebuilt by replaying the recorded fuel quotes, with the 1.18.0 set
frozen under `campaign/stage3/spacecost-0.6.0/`.  See
[master v1.49.0](../versions.md#master-v1490--transportation-v1190).

v0.8.0 TOOK IT 1.19.0 -> 1.20.0 AND MOVED THE LEO PRICE ANCHOR: Falcon Heavy
(expendable)'s band now tops out at NASA's $178M, so its centre is $163M,
$2,555/kg, and every delivered price above LEO moves with it.  Stage 2
follows to mineral_value 1.14.0.  The 1.19.0 set is frozen under
`campaign/stage3/spacecost-0.7.0/`.  See
[master v1.50.0](../versions.md#master-v1500--mineral_value-v1140--transportation-v1200).

v0.9.0 TOOK IT 1.20.0 -> 1.21.0 AND MOVED THE LUNAR DESCENT: 1,870 -> 2,050
m/s, what Apollo 15-17 flew, with a new 1,850 m/s ascent row for the
downleg.  Only `lunar_surface` moves.  The 1.20.0 set is frozen under
`campaign/stage3/spacecost-0.8.0/`.  See
[master v1.52.0](../versions.md#master-v1520--calc-v1300--mineral_value-v1150--transportation-v1210).

v0.10.0 TOOK IT 1.21.0 -> 1.22.0 AND MADE KRYPTON A BAND: $300 -> $794/kg,
the geometric centre of $300 (INL bulk) and $2,100 (SETS flight grade).
No delivered price moves, so Stage 2 stays 1.15.0.  The 1.21.0 set is
frozen under `campaign/stage3/spacecost-0.9.0/`.  See
[master v1.53.0](../versions.md#master-v1530--transportation-v1220).

v0.12.0 TOOK IT 1.22.0 -> 1.23.0 AND ADDED WHAT MAKING ISRU PROPELLANT COSTS:
an `isru_processing_wh_per_kg` column (hydrolox 15,200 Wh/kg, the rows that
burn their feed as it comes 0.0) and an "ISRU propellant plant throughput" ops
row (7.28 kg/yr per kg).  No existing value moved; v0.11.0 had moved no table.
The 1.22.0 set is frozen under `campaign/stage3/spacecost-0.10.0/`.  See
[master v1.55.0](../versions.md#master-v1550--calc-v1320--transportation-v1230).

RE-RUN STAGE 3 WHEN A ROW CHANGES, NOT WHEN A STAMP DOES.  A repin does not
require a restamp: Stage 4 reads no column this contract moved, so leaving the
CSVs at the older stamp costs one `stamp_check()` line and nothing else, where
re-running re-fetches live fuel prices over the only copy of the tables every
committed measurement and every `.verify` baseline was taken against.  The
campaign's inputs are frozen at 2026-09-09 on purpose.

The files on the reference host were re-run at 1.16.0 on 2026-09-24, when
master v1.35.0 adopted spacecost v0.4.0 on disk.  The 2026-09-09 tables the
28-cell campaign flew are frozen under `campaign/stage3/`; see
[the data on disk adopts it](../versions.md#the-data-on-disk-adopts-it-2026-09-24).
They were re-run again at 1.17.0 on 2026-09-28, adopting spacecost v0.5.0,
and the 1.16.0 set is frozen under `campaign/stage3/spacecost-0.4.0/`; see
[the second adoption](../versions.md#the-data-on-disk-adopts-it-2026-09-28).

    to re-check that claim:   py verify_stage3.py

Active sources:
    - spacecost (the reference tables, cited per row)  launch, propellant,
                                                       dv, operational,
                                                       storage, environments
    - yfinance  (Yahoo Finance)                        live commodity prices as
                                                       proxies for RP-1 (HO=F),
                                                       methane (NG=F), and a
                                                       crude cross-check (CL=F)

Pipeline flow:
    Fetch live fuel prices  ->  Load spacecost tables  ->  Merge  ->  Validate
                            ->  Compute normalised cost-per-dv  ->  Export
"""

# ─────────────────────────────────────────────────────────────────────────────
# INSTALLATION
# ─────────────────────────────────────────────────────────────────────────────
try:
    from . import _runtime
except ImportError:                 # run as a script: modules/ is on sys.path
    import _runtime

_REQUIRED_PKGS = ["requests", "pandas", "numpy", "yfinance", "spacecost"]
_runtime.install(_REQUIRED_PKGS)


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import dataclasses
import os
import sys
import warnings
from dataclasses import dataclass
from typing import Dict

import pandas as pd

import spacecost

from spacecost import validate_tables as _spacecost_validate
from spacecost import build_catalog as _spacecost_build_catalog

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
class TransportConfig:
    """User-editable configuration for the transportation-cost catalog."""

    # ─── SOURCE TOGGLES ──────────────────────────────────────────────────────
    use_yfinance:        bool = True   # live commodity fuel prices
    use_reference_table: bool = True   # curated launch / propellant / Δv / ops

    # ─── NETWORK ─────────────────────────────────────────────────────────────
    request_timeout: int = 60   # seconds per HTTP call; a timeout is a soft failure

    # ─── OUTPUT ──────────────────────────────────────────────────────────────
    output_dir:       str = _runtime.DEFAULT_OUTPUT_DIR
    # Six reference tables land in `<output_dir>/transportation/`:
    #     launch_vehicles.csv, propellants.csv, delta_v_segments.csv,
    #     operational_costs.csv, storage_systems.csv, environments.csv
    # plus one composite summary file (vehicle × segment × propellant):
    #     transportation_summary.csv
    subdir:           str = "transportation"

    # ─── UNIT INVARIANT ──────────────────────────────────────────────────────
    # All monetary values in this pipeline are USD.  All physical quantities
    # use SI (kg, m, s, m/s).  Volumes in litres (not m³) because that is how
    # propellant tanks are quoted in the trade.  Enforced by validate() and
    # carried in each output column's name (`_usd_per_kg`, `_m_per_s`, …)
    # rather than by config fields, CURRENCY / MASS_UNIT / DV_UNIT /
    # TIME_UNIT constants lived here but nothing ever read them, so they
    # documented an invariant they did not actually enforce.

    # ─── ISRU (In-Situ Resource Utilization) ─────────────────────────────────
    # If True, the return-leg propellant is assumed to be manufactured from
    # the asteroid's own water/regolith; its $/kg drops to the on-asteroid
    # processing cost (`isru_processing_usd_per_kg`) rather than the launched
    # propellant cost.  Default False = conservative (haul fuel both ways).
    isru_return_propellant:        bool  = False
    isru_processing_usd_per_kg:    float = 50.0   # rough lit estimate

    # ─── CONTINGENCY ─────────────────────────────────────────────────────────
    # Industry-standard mission-cost contingency.  20 % is typical for a
    # well-characterised flight programme; 35-50 % for first-of-kind.
    contingency_fraction: float = 0.20

    # ─── PIPELINE VERSION ────────────────────────────────────────────────────
    # Stamped into every output CSV, and the only way to tell which code
    # produced a given catalog.  BUMP IT when a change moves any number a run
    # produces.  The rule is ONE-DIRECTIONAL: changing a number means bumping,
    # and a bump does NOT mean a number changed, which is why nothing may read
    # a version as evidence that a result moved.
    # THE CHANGELOG IS versions.md, NOT THIS COMMENT.  It used to be 313 lines
    # of release notes sitting right here, a second copy of a record versions.md
    # already held, which is the documentation form of the defect this project
    # keeps cataloguing; it was also what the dashboard rendered as this field's
    # help text, because ui_meta scrapes a field's comment block.  Moved out on
    # 2026-09-02.  Two places to write, neither of them here:
    #     versions.md > Releases            what the release did, and what it
    #                                       measured to say so
    #     versions.md > Module changelogs   this module's own stamp-by-stamp
    #                                       record: Stage 3 changelog
    pipeline_version: str = "1.23.0"
    preview_rows:     int = 15   # rows per table in the end-of-run preview

CONFIG = TransportConfig()
os.makedirs(os.path.join(CONFIG.output_dir, CONFIG.subdir), exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# THE DIALS MUST MATCH THE PACKAGE THEY DRIVE
# ─────────────────────────────────────────────────────────────────────────────
# `TransportConfig` is the one thing that did NOT move to spacecost, because
# two of its defaults belong to this pipeline rather than to a library.  That
# makes it the one surface that can silently drift out of step with the package:
# a field added in spacecost would be invisible here, and a field added here
# would be silently dropped on the way in.
#
# So it is asserted rather than trusted, and THAT is what makes this split safe
# where the project's own parallel-repo divergence was not.  The DATA is
# single-sourced and cannot drift; the dial surface is mirrored under
# a check that fails the import rather than the run.
def _check_config_surface() -> None:
    """Fail loudly if this module's dials and spacecost's have diverged."""
    mine   = {f.name for f in dataclasses.fields(TransportConfig)}
    theirs = {f.name for f in dataclasses.fields(spacecost.SpacecostConfig)}
    if mine != theirs:
        raise SystemExit(
            "STAGE 3 SETTINGS DRIFT: modules/transportation.py and spacecost "
            "no longer describe the same settings.\n"
            f"    only here      : {sorted(mine - theirs)}\n"
            f"    only spacecost : {sorted(theirs - mine)}\n"
            "Add the field to whichever side lacks it, or this run is "
            "configured by one and executed by the other."
        )


_check_config_surface()


def _as_spacecost(config: "TransportConfig"):
    """This module's dials as the package's, field for field.

    Built from `dataclasses.fields` rather than by listing names, so a field
    added on both sides carries over with no edit here.  `_check_config_surface`
    above is what makes that safe.
    """
    return spacecost.SpacecostConfig(**{
        f.name: getattr(config, f.name) for f in dataclasses.fields(config)
    })


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
validate = _spacecost_validate


def build_transportation_catalog(
    config: TransportConfig = CONFIG,
) -> Dict[str, pd.DataFrame]:
    """Run Stage 3: build every reference table and write the seven CSVs.

    Delegates to `spacecost.build_catalog`, which is the same code this file
    used to hold.  Six reference tables and the composite summary, every one
    byte-identical through this path and through the package's own, which is
    what `verify_stage3.py` check 3 asserts file by file.

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
        return _spacecost_build_catalog(_as_spacecost(config))
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
            "Stage 3 re-fetches live fuel prices and rewrites every reference table."):
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
