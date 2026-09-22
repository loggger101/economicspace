# -*- coding: utf-8 -*-
"""transportation, Module 3 of the Asteroid Profitability Pipeline.

THE TABLES ARE NOT IN THIS FILE ANY MORE.  They live in `spacecost`, an
independent package, and this module is the adapter that drives it:

    https://github.com/loggger101/spacecost

Why they left.  Two thirds of this module was annotated reference data --
36 launch vehicles, 41 propellants, 33 delta-v segments, 44 operational costs
and 20 storage systems, every row cited -- and nothing in its schema knew what
an asteroid was.  A launch price is useful to anyone costing a mission, so the
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

RE-RUN STAGE 3 WHEN A ROW CHANGES, NOT WHEN A STAMP DOES.  A repin does not
require a restamp: Stage 4 reads no column this contract moved, so leaving the
CSVs at the older stamp costs one `stamp_check()` line and nothing else, where
re-running re-fetches live fuel prices over the only copy of the tables every
committed measurement and every `.verify` baseline was taken against.  The
campaign's inputs are frozen at 2026-09-09 on purpose.

🚨  THE FILES ON DISK ARE AT 1.15.0 ALL THE SAME, dated 2026-09-17, because
this module was run directly while somebody smoke-tested the repin -- before
the guard below existed.  Three live-priced propellant rows moved with it.  The
frozen values are recorded in
[transportation v1.15.0](../versions.md#transportation-v1150--master-v1290);
they were recoverable only because an archived Stage 4 cell had been priced
with them.

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
# Windows consoles default to cp1252, which cannot encode every character this
# file's progress output can carry -- force UTF-8 before anything prints.
import sys as _sys
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import subprocess, sys

# `spacecost` is not on PyPI yet, so it installs from git.  The mapping is
# import-name -> pip argument, because for this one package those differ and a
# bare name in the install list would resolve to nothing.
# IF SPACECOST IS EVER PUBLISHED: replace the URL with a pinned version
# ("spacecost==0.1.0") and delete `_PIP_SPEC`; the rest of the block is already
# shaped for it.  Keep `requirements.txt` in step -- verify_docs check 7 holds
# the two to each other.
_REQUIRED_PKGS = ["requests", "pandas", "numpy", "yfinance", "spacecost"]
_PIP_SPEC = {
    "spacecost": "git+https://github.com/loggger101/spacecost@v0.3.1",
}
_missing = []
for _pkg in _REQUIRED_PKGS:
    try:
        __import__(_pkg)
    except ImportError:
        _missing.append(_PIP_SPEC.get(_pkg, _pkg))

if _missing:
    print(f"PKG  Installing: {_missing} ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q"] + _missing
    )
    print("OK  Install complete")
else:
    print("OK  All packages present")


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import dataclasses
import os
import warnings
from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd

import spacecost

# NEVER SPELL A NAME THE BUILD REWRITES.  `build_master.py` concatenates the
# four stage modules into `master.py` and resolves collisions with
# `word_replace`, a whole-word regex over the ENTIRE file text -- comments and
# string literals included, not only code.  For this module it rewrites two
# words: the config global, and the sanity-check function Module 2 also
# defines.
#
# ALIASING THE LOCAL NAME IS NOT ENOUGH, and that is the trap.  In
# `from spacecost import X as _y` the imported name X is still a bare word, so
# it gets rewritten too and the import then fails against a package with no
# such attribute.  That happened here, on the first build, and it surfaced in a
# docs check rather than in anything looking at Stage 3.
#
# The package exports a collision-proof second name for the one function that
# collides, and that is what is imported.  Everywhere else in this file, reach
# the package through `spacecost.` -- and read the built master.py rather than
# assuming, because this file and its concatenated copy are not the same text.
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
# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT OUTPUT LOCATION
# ─────────────────────────────────────────────────────────────────────────────
# Colab keeps its scratch space at /content.  Anywhere else (local Windows,
# Linux, CI) that path is meaningless -- on Windows it silently resolves to
# C:\content -- so fall back to an ./asteroid_pipeline dir under the CWD.

def _default_output_dir() -> str:
    """Colab-aware default output directory."""
    env = os.environ.get("ASTEROID_PIPELINE_OUTPUT_DIR")
    if env:
        return env
    if os.path.isdir("/content") and _sys.platform != "win32":
        return "/content/asteroid_pipeline"
    return os.path.join(os.getcwd(), "asteroid_pipeline")


_DEFAULT_OUTPUT_DIR = _default_output_dir()



@dataclass
class TransportConfig:
    """User-editable configuration for the transportation-cost catalog."""

    # ─── SOURCE TOGGLES ──────────────────────────────────────────────────────
    use_yfinance:        bool = True   # live commodity fuel prices
    use_reference_table: bool = True   # curated launch / propellant / Δv / ops

    # ─── NETWORK ─────────────────────────────────────────────────────────────
    request_timeout: int = 60   # seconds per HTTP call; a timeout is a soft failure

    # ─── OUTPUT ──────────────────────────────────────────────────────────────
    output_dir:       str = _DEFAULT_OUTPUT_DIR
    # Five sub-files land in `<output_dir>/transportation/`:
    #     launch_vehicles.csv, propellants.csv, delta_v_segments.csv,
    #     operational_costs.csv, storage_systems.csv   (the last new in v1.9.0)
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
    pipeline_version: str = "1.15.0"
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
# single-sourced and cannot drift; the ten-field dial surface is mirrored under
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
# through `spacecost.` because several things read them as attributes of THIS
# module: `verify_docs.py` check 3 holds README's row counts to them, and the
# dashboard renders them.  Re-exporting keeps every such caller working
# unchanged.
LAUNCH_VEHICLES_REFERENCE   = spacecost.LAUNCH_VEHICLES_REFERENCE
PROPELLANTS_REFERENCE       = spacecost.PROPELLANTS_REFERENCE
DELTA_V_REFERENCE           = spacecost.DELTA_V_REFERENCE
OPERATIONAL_COSTS_REFERENCE = spacecost.OPERATIONAL_COSTS_REFERENCE
STORAGE_REFERENCE           = spacecost.STORAGE_REFERENCE
# The sixth, new in the v1.15.0 contract.  Nothing in Stage 4 reads it yet; it
# is re-exported on the same terms as the other five so that this module's
# surface is the package's surface rather than the subset somebody needed on
# the day.
ENVIRONMENTS_REFERENCE      = spacecost.ENVIRONMENTS_REFERENCE

# Physical constants and unit helpers, likewise.
G0_M_S2                     = spacecost.G0_M_S2
LITRES_PER_GAL              = spacecost.LITRES_PER_GAL
LITRES_PER_BBL              = spacecost.LITRES_PER_BBL
COMMODITY_DENSITY_KG_PER_L  = spacecost.COMMODITY_DENSITY_KG_PER_L

# Loaders, rocket-equation helpers and the query utilities.
load_launch_vehicles         = spacecost.load_launch_vehicles
load_propellants             = spacecost.load_propellants
load_delta_v                 = spacecost.load_delta_v
load_operational_costs       = spacecost.load_operational_costs
load_storage                 = spacecost.load_storage
load_environments            = spacecost.load_environments
propellant_mass_for_dv       = spacecost.propellant_mass_for_dv
cost_per_dv_usd_per_kg       = spacecost.cost_per_dv_usd_per_kg
build_transportation_summary = spacecost.build_transportation_summary
cheapest_launch_to           = spacecost.cheapest_launch_to
cheapest_propellant_for      = spacecost.cheapest_propellant_for
mission_cost_breakdown       = spacecost.mission_cost_breakdown


# Sanity bands over the loaded tables; prints warnings and never raises.  An
# ALIAS rather than a wrapper, because a function whose whole body forwards its
# arguments is a layer with no reader: `help()` on it would show this file's
# paraphrase instead of the real docstring.
#
# `build_master.py` rewrites this name on the way into master.py, because
# Module 2 defines one that collides.  That rewrite is exactly why the target is
# imported under a private alias at the top of this file, and why the package
# exports a second, collision-proof name for it.
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

    # ── OVERWRITE GUARD ──────────────────────────────────────────────────────
    # A FETCHING stage writes over the only copy of its inputs, and there is no
    # undo: every `.verify` baseline and every committed measurement was taken
    # against the files this run is about to replace.  `run_pipeline.py` has
    # asked before doing that since 2026-08-23; running THIS FILE went nowhere
    # near that guard, which is the hole somebody fell into on 2026-09-17 while
    # smoke-testing an import, re-fetching three live propellant prices over the
    # campaign's frozen tables.
    #
    # ⚠️  Mirrored, not shared: a stage module is standalone by construction and
    # cannot import a helper.  `verify_docs.py` check 15 holds the three copies
    # to each other, so edit one and the docs harness names the other two.
    def _confirm_overwrite(paths, what):
        """True when it is safe to overwrite `paths`; ask the user if it is not.

        Refuses on EOF rather than hanging, because stdin here may be a
        scheduled task's dead handle -- the `set /p` trap in `run.bat`, which
        waits forever instead of failing.  `--yes` skips the question, which is
        what a scripted caller passes.
        """
        existing = [p for p in paths if os.path.exists(p)]
        if not existing or "--yes" in sys.argv:
            return True
        print("")
        print("  " + "=" * 71)
        print("  THIS RE-FETCHES LIVE DATA AND OVERWRITES WHAT IS ON DISK")
        print("  " + "=" * 71)
        print("  %s" % what)
        for p in existing[:8]:
            print("    %s" % p)
        if len(existing) > 8:
            print("    ... and %d more" % (len(existing) - 8))
        print("")
        print("  The values on disk are the only copy.  Any verify.py baseline")
        print("  or archived measurement taken against them stops reproducing,")
        print("  and that looks exactly like a code regression.")
        print("")
        try:
            return input("  Type 'yes' to overwrite: ").strip().lower() == "yes"
        except (EOFError, KeyboardInterrupt):
            print("")
            print("  No console to confirm on (stdin is not a terminal).")
            print("  Pass --yes if overwriting them is what you meant.")
            return False

    if not _confirm_overwrite(
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
        print(cheapest_propellant_for(catalog, 6_500).to_string(index=False))
