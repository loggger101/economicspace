# -*- coding: utf-8 -*-
"""Master Asteroid Profitability Pipeline: the import surface.

    Stage 1  ->  modules/catalog.py         downloads the pinned catalog release
    Stage 2  ->  modules/mineral_value.py   prices every commodity per destination
    Stage 3  ->  modules/transportation.py  launch, propellant, delta-v, ops tables
    Stage 4  ->  modules/calc.py            mission search, cost cascade, ranking

`import master` (by name, with the repo on sys.path) imports the four stage
modules from the `modules` package, gives each config the name the entry points
use (CATALOG_CONFIG, MINERAL_CONFIG, TRANSPORT_CONFIG, CALC_CONFIG), and adds
MasterConfig and run_full_pipeline.  Any other attribute is looked up in the
four modules by `__getattr__` below; a name two modules define differently is
refused rather than resolved, so `master.CONFIG` and `master.validate` raise.

DELIVERY DESTINATION - set MASTER_CONFIG.delivery_destination, which writes
MINERAL_CONFIG.delivery_destination and CALC_CONFIG.delivery_destination
together.  Stage 2 decides what a kilogram sells for; Stage 4 decides what it
costs to put it there, and the answer is only meaningful when they agree.

The output directory defaults to ./asteroid_pipeline (/content/asteroid_pipeline
on Colab); override it with the environment variable
ASTEROID_PIPELINE_OUTPUT_DIR or MASTER_CONFIG.output_dir.

`python master.py` runs all four stages, and Stages 1-3 re-fetch live inputs
and overwrite their CSVs.  run_pipeline.py is the entry point that asks first.
"""

MASTER_VERSION = "1.57.0"

# The package's __init__ fixes the console encoding and silences spawned
# workers before any module prints.  Imported in stage order.
from modules import catalog, mineral_value, transportation, calc  # noqa: E402

import os                                                          # noqa: E402
from datetime import datetime                                      # noqa: E402

# -----------------------------------------------------------------------------
# THE NAMES THE ENTRY POINTS USE FOR WHAT EACH MODULE CALLS ITS OWN
# -----------------------------------------------------------------------------
# Every module names its config `CONFIG`, and Modules 2 and 3 each define a
# `validate`; the entry points use these names for them.
CATALOG_CONFIG         = catalog.CONFIG
build_asteroid_catalog = catalog.build_catalog
MINERAL_CONFIG         = mineral_value.CONFIG
validate_minerals      = mineral_value.validate
TRANSPORT_CONFIG       = transportation.CONFIG
validate_transport     = transportation.validate
CALC_CONFIG            = calc.CONFIG

# What the orchestrator below reads by bare name.  A module-level __getattr__
# answers `master.X` from outside, never a lookup inside this file, so these
# have to be bound here.  `_DEFAULT_OUTPUT_DIR` is calc's: all four modules
# compute it with the same function.
from modules.mineral_value import build_mineral_value_catalog      # noqa: E402
from modules.transportation import build_transportation_catalog    # noqa: E402
from modules.calc import (                                         # noqa: E402
    _DEFAULT_OUTPUT_DIR, MEASURED_CELL_SECONDS, beneficiation_cost_ratio,
    build_profitability_catalog, measured_cell_provenance,
    programme_search_cost_ratio)


# -----------------------------------------------------------------------------
# EVERY OTHER NAME: FORWARDED TO THE MODULE THAT DEFINES IT
# -----------------------------------------------------------------------------
# Looked up on every access rather than copied at import, so a global a module
# rebinds later (its caches) is never served stale.
_MODULES = (calc, transportation, mineral_value, catalog)

# Bound in more than one module, as EQUAL values that are not the same object.
# Anything else two modules both bind is refused unless every copy is the same
# object (a shared import such as `pd`).
_IDENTICAL_COPIES = frozenset({
    "G0_M_S2",                # mineral_value takes spacecost's; calc repeats it
    "_default_output_dir",    # the same body in all four modules
    "_DEFAULT_OUTPUT_DIR",    # what that function returned, in each of them
})


def _owner(name):
    """The module `master.<name>` is read from, or AttributeError saying why not."""
    owners = [m for m in _MODULES if name in vars(m)]
    if not owners:
        raise AttributeError(f"module 'master' has no attribute {name!r}")
    first = vars(owners[0])[name]
    if (len(owners) > 1 and name not in _IDENTICAL_COPIES
            and any(vars(m)[name] is not first for m in owners[1:])):
        raise AttributeError(
            f"master.{name} is ambiguous: "
            + ", ".join(m.__name__ for m in owners)
            + " each define it.  Read it from the module you mean.")
    return owners[0]


def __getattr__(name):
    """PEP 562: `master.<name>` for anything not bound in this file."""
    if name.startswith("__"):
        raise AttributeError(f"module 'master' has no attribute {name!r}")
    return getattr(_owner(name), name)


# =============================================================================
# |                                                                           |
# |   *  MASTER CONFIG - ONE PLACE TO TUNE EVERYTHING *                      |
# |                                                                           |
# |   The MasterConfig wraps the four module-specific configs as properties.  |
# |   Each sub-config (CATALOG_CONFIG, MINERAL_CONFIG, TRANSPORT_CONFIG,      |
# |   CALC_CONFIG) was instantiated when its module was imported above.  This |
# |   master object centralises the shared output directory and provides a    |
# |   single handle for the orchestrator.                                     |
# |                                                                           |
# =============================================================================

from dataclasses import dataclass as _master_dataclass

@_master_dataclass
class MasterConfig:
    """Composes the four module configs.  Edit sub-configs directly:

        MASTER_CONFIG.catalog.catalog_release = "data-YYYY-MM-DD"
        MASTER_CONFIG.calc.use_isru_return_propellant = True

    One exception: set the delivery destination HERE, not on a sub-config -

        MASTER_CONFIG.delivery_destination = "cislunar"

    Stage 2 and Stage 4 each carry a delivery_destination, and they must
    agree: Stage 2 decides what a kilogram sells for, Stage 4 decides the
    architecture that puts it there.  Setting them apart prices the cargo at
    a depot while paying to land it in Utah.  This property writes both.
    """
    output_dir: str = _DEFAULT_OUTPUT_DIR

    @property
    def delivery_destination(self) -> str:
        """Where the mined material is sold.

        Valid values are the keys of `DELIVERY_DESTINATIONS`, which is the
        live list and is deliberately not restated here: this docstring was
        still naming three of the seven when it was found.
        """
        return self.mineral.delivery_destination

    @delivery_destination.setter
    def delivery_destination(self, value: str) -> None:
        """Write both copies, Stage 2's and Stage 4's, in one assignment."""
        self.mineral.delivery_destination = value
        self.calc.delivery_destination    = value

    @property
    def catalog(self):
        """Stage 1's config, `modules.catalog.CONFIG`."""
        return CATALOG_CONFIG

    @property
    def mineral(self):
        """Stage 2's config, `modules.mineral_value.CONFIG`."""
        return MINERAL_CONFIG

    @property
    def transport(self):
        """Stage 3's config, `modules.transportation.CONFIG`."""
        return TRANSPORT_CONFIG

    @property
    def calc(self):
        """Stage 4's config, `modules.calc.CONFIG`."""
        return CALC_CONFIG

    def apply(self):
        """Push master output_dir to every sub-config, create the dir tree.

        Also re-asserts the delivery destination across Stage 2 and Stage 4,
        so a sub-config edited directly cannot leave the two disagreeing.
        """
        self.catalog.output_dir   = self.output_dir
        self.mineral.output_dir   = self.output_dir
        self.transport.output_dir = self.output_dir
        self.calc.input_dir       = self.output_dir
        self.calc.output_dir      = self.output_dir
        self.delivery_destination = self.mineral.delivery_destination
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, self.transport.subdir),
                    exist_ok=True)


MASTER_CONFIG = MasterConfig()
MASTER_CONFIG.apply()

print()
print("=" * 75)
print("     MASTER CONFIG READY")
print(f"      Pipeline output  : {MASTER_CONFIG.output_dir}")
print(f"      Catalog release  : {MASTER_CONFIG.catalog.catalog_release}")
print(f"      Eval row cap     : {MASTER_CONFIG.calc.eval_row_cap:,}")
print(f"      Delivery dest    : {MASTER_CONFIG.delivery_destination}")
print(f"      ISRU return      : {'available where the rock supplies the propellant' if MASTER_CONFIG.calc.use_isru_return_propellant else 'off'}")
print(f"      Propellants      : {'flown hardware only' if MASTER_CONFIG.calc.operational_propellants_only else 'INCLUDING development / concept'}")
print(f"      Tank mass        : {'in the rocket equation' if MASTER_CONFIG.calc.model_tank_mass else 'off'}")
print(f"      Architecture     : {'searched per asteroid' if MASTER_CONFIG.calc.optimise_architecture_per_asteroid else 'fixed by config'}")
print(f"      NRE amortise     : over {MASTER_CONFIG.calc.nre_amortization_missions} mission(s)")
# Both of the next two default ON as of calc v1.17.0 and between them cost
# MEASURED_CELL_SECONDS[(True, True)] / [(False, False)] times the runtime of
# the raw single-mission run most of the older tables in versions.md were
# measured at.  Print them so a long run is never a mystery, and QUOTE THE
# RATIOS FROM THAT DICT rather than typing them: the numbers here were
# hand-copied once and printed the superseded 1.16.0 figures for three
# releases after the measurement that retired them.
_both_on = (MEASURED_CELL_SECONDS[(True, True)]
            / MEASURED_CELL_SECONDS[(False, False)])
_meas_at = measured_cell_provenance(MASTER_CONFIG.calc.pipeline_version)
print(f"      Beneficiation    : "
      + ("ON - concentrate, not run-of-mine ore (~%.1fx runtime%s; "
         "False for the raw cell)"
         % (beneficiation_cost_ratio(MASTER_CONFIG.calc.optimise_programme_scale),
            _meas_at)
         if MASTER_CONFIG.calc.use_beneficiation else
         "off - flying run-of-mine ore at bulk grade"))
print(f"      Programme        : "
      + ("(fleet <= %d) x (campaigns/ship) searched; N follows (~%.1fx runtime%s)"
         % (MASTER_CONFIG.calc.max_fleet_ships,
            programme_search_cost_ratio(MASTER_CONFIG.calc.use_beneficiation),
            _meas_at)
         if MASTER_CONFIG.calc.optimise_programme_scale else
         "fixed size (set calc.optimise_programme_scale to search it)"))
if MASTER_CONFIG.calc.use_beneficiation and MASTER_CONFIG.calc.optimise_programme_scale:
    print(f"                         both on: ~{_both_on:.1f}x the raw N = 1 cell")
# calc v1.21.0.  On the banner for the same reason Beneficiation and Programme
# are: it changes what the run ANSWERS, not merely how long it takes.  The same
# code gives four answers 20% to 49% apart on the sampled cislunar cells, so a
# banner that does not name the market model leaves the reader unable to say
# what the catalog beneath it means.
print(f"      Market model     : "
      + {"capacity_cap":
         "capacity_cap - constant prices, a kg/yr ceiling per commodity",
         "single_mission":
         "single_mission - constant prices, N = 1, no ceiling",
         "elasticity":
         "elasticity - the demand curve, i.e. the pre-v1.21.0 answer",
         "unbounded":
         "unbounded - DIAGNOSTIC: nothing bounds programme size",
         }.get(MASTER_CONFIG.calc.market_model,
               str(MASTER_CONFIG.calc.market_model)))
print(f"      Contingency      : {MASTER_CONFIG.calc.contingency_fraction:.0%}")
print("=" * 75)


# -----------------------------------------------------------------------------
# MASTER ORCHESTRATOR
# -----------------------------------------------------------------------------

def run_full_pipeline(master: MasterConfig = None) -> dict:
    """Run all four module pipelines end-to-end in sequence.

    Stage 1 (asteroid catalog) writes CSVs that Stage 4 (profitability)
    reads.  Stages 2 + 3 also write CSVs that Stage 4 consumes.  All four
    must run in order on a fresh output dir; on a re-run, intermediate
    CSVs are overwritten by their owning stage.
    """
    if master is None:
        master = MASTER_CONFIG
    master.apply()

    t0 = datetime.now()
    print()
    print("#" * 75)
    print(f"    MASTER ASTEROID PROFITABILITY PIPELINE - v{MASTER_VERSION}")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  output -> {master.output_dir}")
    print("#" * 75)

    # -- Stage 1 - Asteroid Catalog -------------------------------------------
    print()
    print("-" * 75)
    print("  STAGE 1 - ASTEROID CATALOG (Module 1)")
    print("-" * 75)
    asteroid_df = build_asteroid_catalog(master.catalog)

    # -- Stage 2 - Mineral Value ----------------------------------------------
    print()
    print("-" * 75)
    print("  STAGE 2 - MINERAL VALUE CATALOG (Module 2)")
    print("-" * 75)
    mineral_df = build_mineral_value_catalog(master.mineral)

    # -- Stage 3 - Transportation ---------------------------------------------
    print()
    print("-" * 75)
    print("  STAGE 3 - TRANSPORTATION COSTS (Module 3)")
    print("-" * 75)
    transport_catalogs = build_transportation_catalog(master.transport)

    # -- Stage 4 - Profitability ----------------------------------------------
    print()
    print("-" * 75)
    print("  STAGE 4 - PROFITABILITY ANALYSIS (Module 4)")
    print("-" * 75)
    profit_df = build_profitability_catalog(master.calc)

    elapsed = (datetime.now() - t0).total_seconds()
    print()
    print("#" * 75)
    print("  OK  MASTER PIPELINE COMPLETE")
    print(f"      Total elapsed     : {elapsed:.1f}s")
    print(f"      Asteroids         : {len(asteroid_df):,}")
    print(f"      Minerals priced   : {len(mineral_df):,}")
    print(f"      Profitability rows: {len(profit_df):,}")
    print(f"      Viable missions   : {int(profit_df['viable'].sum()) if not profit_df.empty else 0:,}")
    print(f"      Master output dir : {master.output_dir}")
    print("#" * 75)

    return {
        "asteroids":      asteroid_df,
        "minerals":       mineral_df,
        "transportation": transport_catalogs,
        "profitability":  profit_df,
        "master_config":  master,
    }


# -----------------------------------------------------------------------------
# RUN AS A SCRIPT
# -----------------------------------------------------------------------------
# `python master.py` runs all four stages.  Importing this file runs none.

if __name__ == "__main__":
    results = run_full_pipeline(MASTER_CONFIG)
