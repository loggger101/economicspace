# -*- coding: utf-8 -*-
"""Build script - assembles modules/*.py into the single-file master.py.

This is a build tool, NOT part of the pipeline.  It performs surgical edits
to each module so they coexist in one file without name collisions:

  * Strip each module's top-of-file docstring (one master docstring will
    cover everything).
  * Strip each module's auto-install block (master has its own consolidated
    installer, including the UTF-8 console fix, at the top).
  * Strip each module's `RUN & PREVIEW` block at the bottom (the master
    orchestrator drives execution instead).
  * Rename each module's `CONFIG` global to a unique name
    (CATALOG_CONFIG, MINERAL_CONFIG, TRANSPORT_CONFIG, CALC_CONFIG) so
    each module's `def build_X(config = CONFIG)` default keeps working.
  * Rename function-name collisions between modules (merge_sources,
    validate, build_catalog).

Paths are resolved relative to this file, so the repo can live anywhere.

Run via:  python build_master.py
"""
import re
import os

HERE     = os.path.dirname(os.path.abspath(__file__))
MODULES  = os.path.join(HERE, "modules")
M1_PATH  = os.path.join(MODULES, "catalog.py")
M2_PATH  = os.path.join(MODULES, "mineral_value.py")
M3_PATH  = os.path.join(MODULES, "transportation.py")
M4_PATH  = os.path.join(MODULES, "calc.py")
OUT_PATH = os.path.join(HERE, "master.py")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# -----------------------------------------------------------------------------
# SURGICAL EDIT HELPERS
# -----------------------------------------------------------------------------

def strip_top_docstring(content):
    """Remove the leading `# -*- coding -*-` line plus the triple-quoted module
    docstring that follows."""
    m = re.match(r'^# -\*- coding[^\n]*\n"""', content)
    if not m:
        return content
    # Find the closing triple-quote
    end = content.find('"""', m.end())
    if end == -1:
        return content
    # Skip past closing """ and one newline
    after = end + 3
    if after < len(content) and content[after] == "\n":
        after += 1
    return content[after:]


def strip_install_block(content):
    """Remove the auto-install block (which also carries the per-module UTF-8
    console fix).  The block always ends with the 'All packages present' line."""
    return re.sub(
        r'# ─+\n# INSTALLATION\n# ─+\n.*?print\("OK  All packages present"\)\n',
        '', content, count=1, flags=re.DOTALL
    )


def strip_run_preview_block(content):
    """Remove everything from the `RUN & PREVIEW` section to end of file.

    In the modules that region is wrapped in `if __name__ == "__main__":` so
    the module stays importable; master.py gets the orchestrator instead.
    """
    pattern = re.compile(r'\n# ─+\n# RUN [^\n]*\n# ─+.*', flags=re.DOTALL)
    return pattern.sub('\n', content)


def word_replace(content, old, new):
    """Replace a whole-word identifier (won't touch substrings)."""
    return re.sub(r'\b' + re.escape(old) + r'\b', new, content)


def check(condition, message):
    """Fail the build loudly rather than emitting a silently-wrong master.py."""
    if not condition:
        raise SystemExit(f"BUILD FAILED: {message}")


# -----------------------------------------------------------------------------
# READ + PROCESS EACH MODULE
# -----------------------------------------------------------------------------
m1 = read(M1_PATH)
m2 = read(M2_PATH)
m3 = read(M3_PATH)
m4 = read(M4_PATH)

for label, before in (("catalog", m1), ("mineral_value", m2),
                      ("transportation", m3), ("calc", m4)):
    check("# INSTALLATION" in before, f"{label}: no INSTALLATION block to strip")
    check("# RUN & PREVIEW" in before, f"{label}: no RUN & PREVIEW block to strip")
    check(before.startswith('# -*- coding'),
          f"{label}: no leading coding line, so the docstring strip cannot anchor")

# Strip docstrings, install blocks, auto-run blocks
m1 = strip_top_docstring(m1)
m1 = strip_install_block(m1)
m1 = strip_run_preview_block(m1)

m2 = strip_top_docstring(m2)
m2 = strip_install_block(m2)
m2 = strip_run_preview_block(m2)

m3 = strip_top_docstring(m3)
m3 = strip_install_block(m3)
m3 = strip_run_preview_block(m3)

m4 = strip_top_docstring(m4)
m4 = strip_install_block(m4)
m4 = strip_run_preview_block(m4)

for label, after in (("catalog", m1), ("mineral_value", m2),
                     ("transportation", m3), ("calc", m4)):
    check("# INSTALLATION" not in after, f"{label}: INSTALLATION block survived")
    check("# RUN & PREVIEW" not in after, f"{label}: RUN & PREVIEW block survived")
    # Catches a RUN & PREVIEW block that survived the strip.  This tested for
    # the bare substring "__main__" until calc v1.10.1, when the parallel
    # evaluator started referring to the name on purpose: a spawned worker
    # rebuilds the parent from sys.modules["__main__"], so _spawn_environment
    # has to read and repoint it.  The guard's actual signature is the `if`,
    # and every other mention in the four modules is either that comment or a
    # `type(exc).__name__` in an error message - so test for the guard rather
    # than for the word, which is what the failure message always claimed.
    check("if __name__ ==" not in after,
          f"{label}: __main__ guard leaked into master")
    # The docstring strip is anchored to the coding line; if it silently
    # no-opped, the module's own docstring becomes a bare string expression
    # partway down master.py and its title contradicts the master's.
    check(not after.lstrip().startswith('"""'),
          f"{label}: module docstring survived the strip")

# -- Rename per-module globals + functions to avoid collisions ----------------
# Module 1: CONFIG -> CATALOG_CONFIG, build_catalog -> build_asteroid_catalog,
#           lookup_asteroid -> lookup_asteroid_catalog
# Modules 1 and 4 both define lookup_asteroid, and they are not the same
# function: Module 1's searches the Stage-1 asteroid catalog, Module 4's
# searches the Stage-4 profitability catalog.  Concatenated, Module 4's wins
# and Module 1's is unreachable - while both modules' help text still tells
# you to call `lookup_asteroid(catalog, ...)`.  Following Module 1's advice
# therefore ran Module 4's function against the wrong frame.  Module 4 keeps
# the plain name (the profitability catalog is the headline output); Module
# 1's is renamed, and word_replace rewrites its help text to match.
m1 = word_replace(m1, "CONFIG", "CATALOG_CONFIG")
m1 = word_replace(m1, "build_catalog", "build_asteroid_catalog")
m1 = word_replace(m1, "lookup_asteroid", "lookup_asteroid_catalog")

# Module 2: CONFIG -> MINERAL_CONFIG, merge_sources -> merge_mineral_sources,
#           validate -> validate_minerals
m2 = word_replace(m2, "CONFIG", "MINERAL_CONFIG")
m2 = word_replace(m2, "merge_sources", "merge_mineral_sources")
m2 = word_replace(m2, "validate",      "validate_minerals")

# Module 3: CONFIG -> TRANSPORT_CONFIG, validate -> validate_transport
m3 = word_replace(m3, "CONFIG",   "TRANSPORT_CONFIG")
m3 = word_replace(m3, "validate", "validate_transport")

# Module 4: CONFIG -> CALC_CONFIG  (no other collisions)
m4 = word_replace(m4, "CONFIG", "CALC_CONFIG")


# -----------------------------------------------------------------------------
# MASTER HEADER + ORCHESTRATOR
# -----------------------------------------------------------------------------

MASTER_HEADER = '''# -*- coding: utf-8 -*-
"""Master Asteroid Profitability Pipeline (1.20.8)

End-to-end SELF-CONTAINED pipeline that combines all four modules into a
single runnable file.  Copy-paste into Colab / Jupyter / your script and
run top-to-bottom - the orchestrator at the bottom executes everything.

    Stage 1  ->  Asteroid Catalog        (modules/catalog.py 1.1.0)
                JPL SBDB + MP3C + SsODNet + NEOWISE
                + PGM_ENRICHMENT_BY_TYPE per-spectral-type factors
    Stage 2  ->  Mineral Value Catalog   (modules/mineral_value.py 1.7.0)
                yfinance live + USGS/LME reference + mineralogy
                + sperrylite / laurite / awaruite / native-pgm phases
                + destination pricing for EVERY commodity
    Stage 3  ->  Transportation Data     (modules/transportation.py 1.11.0)
                Launch vehicles + propellants + dv segments + ops costs
                (UNCREWED autonomous mining - no crew costs)
    Stage 4  ->  Profitability Calc      (modules/calc.py 1.14.0)
                Rocket eq cascade + cost cascade + per-asteroid ranking
                + PGM enrichment applied per asteroid (M-type 2x, V-type 0.2x)
                + delivery architecture: earth_surface / leo / cislunar /
                  lunar_surface / mars_surface, beneficiation,
                  low-thrust trip time, launch windows, learning curve,
                  market saturation, rig service life + terminal value,
                  mission reliability + growth, cryogenic boil-off,
                  in-space manufacturing

Mission profile: UNCREWED autonomous mining spacecraft throughout (no
crew costs, no life-support overhead).

DELIVERY DESTINATION - set MINERAL_CONFIG.delivery_destination and
CALC_CONFIG.delivery_destination TO THE SAME VALUE.  Stage 2 decides what a
kilogram sells for; Stage 4 decides what it costs to put it there, and the
answer is only meaningful when they agree.  Stage 4 checks and warns.

Output tree (under MASTER_CONFIG.output_dir):
    asteroid_catalog.csv               <- Stage 1 (~0.88 GB at the 1.55 M-row
                                          default; set catalog.jpl_limit lower)
    rejected_entries.csv               <- Stage 1 (validation rejects)
    mineral_value_catalog.csv          <- Stage 2
    transportation/
        launch_vehicles.csv            <- Stage 3
        propellants.csv                <- Stage 3
        delta_v_segments.csv           <- Stage 3
        operational_costs.csv          <- Stage 3
        transportation_summary.csv     <- Stage 3 (vehicle x prop x segment)
    profitability_catalog.csv          <- Stage 4 (the headline output)

The output directory defaults to /content/asteroid_pipeline on Colab and
./asteroid_pipeline everywhere else; override with the environment variable
ASTEROID_PIPELINE_OUTPUT_DIR or by setting MASTER_CONFIG.output_dir.

Tuning:
    MASTER_CONFIG sits at the bottom of the master config section.  Edit:
        MASTER_CONFIG.output_dir                    (where everything lands)
        MASTER_CONFIG.catalog.jpl_limit             (asteroid catalog size)
        MASTER_CONFIG.calc.nre_amortization_missions (multi-mission NRE split)
        MASTER_CONFIG.calc.use_isru_return_propellant (make ISRU available)
        MASTER_CONFIG.calc.optimise_architecture_per_asteroid
                                                    (search return mode + ISRU
                                                     per target; ~2x runtime)
        MASTER_CONFIG.calc.eval_row_cap             (limit Stage 4 evaluations)
    Or set any sub-config field directly before run_full_pipeline() fires.

GENERATED FILE - do not edit by hand.  Machine-assembled from modules/*.py by
build_master.py; edit the modules and re-run that script.
"""

# -----------------------------------------------------------------------------
# CONSOLE ENCODING
# -----------------------------------------------------------------------------
# Windows consoles default to cp1252, which cannot encode the emoji used in
# this file's progress output.  Must happen before the first print().

import sys as _sys
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# -----------------------------------------------------------------------------
# SPAWNED-WORKER QUIET MODE
# -----------------------------------------------------------------------------
# Stage 4 evaluates asteroids across a process pool.  Windows has no fork, so
# every worker re-imports this file and would replay all four module banners --
# 60 lines each, 700+ for a full pool, interleaved into the run log the UI
# parses.  Stage 4's parent sets ASTEROID_PIPELINE_WORKER before creating the
# pool; children inherit it.  Must sit above the first print(), which is why it
# is here rather than in the calc section far below.
#
# Flipped to "silenced" rather than cleared so that calc's own copy of this
# guard -- the modules each carry one, for when they are run standalone -- is a
# no-op here instead of leaking a second handle.
#
# stderr is deliberately left alone: a worker that dies should still say so.

import os as _os
if _os.environ.get("ASTEROID_PIPELINE_WORKER") == "1":
    _os.environ["ASTEROID_PIPELINE_WORKER"] = "silenced"
    _sys.stdout = open(_os.devnull, "w", encoding="utf-8")

# -----------------------------------------------------------------------------
# CONSOLIDATED INSTALLATION
# -----------------------------------------------------------------------------
# Union of every package required by the four modules.  Auto-installs at
# import time; safe to re-run.

import subprocess as _subprocess

_MASTER_REQUIRED = [
    "requests", "pandas", "numpy", "yfinance", "tqdm", "pyarrow",
]
_master_missing = []
for _pkg in _MASTER_REQUIRED:
    try:
        __import__(_pkg)
    except ImportError:
        _master_missing.append(_pkg)
if _master_missing:
    print(f"PKG  Installing: {_master_missing} ...")
    _subprocess.check_call(
        [_sys.executable, "-m", "pip", "install", "-q"] + _master_missing
    )
    print("OK  Install complete")
else:
    print("OK  All packages present")

'''


MASTER_ORCHESTRATOR = '''

# =============================================================================
# |                                                                           |
# |   *  MASTER CONFIG - ONE PLACE TO TUNE EVERYTHING *                      |
# |                                                                           |
# |   The MasterConfig wraps the four module-specific configs as properties.  |
# |   Each sub-config (CATALOG_CONFIG, MINERAL_CONFIG, TRANSPORT_CONFIG,      |
# |   CALC_CONFIG) was instantiated when its module section ran above.  This  |
# |   master object centralises the shared output directory and provides a    |
# |   single handle for the orchestrator.                                     |
# |                                                                           |
# =============================================================================

from dataclasses import dataclass as _master_dataclass

@_master_dataclass
class MasterConfig:
    """Composes the four module configs.  Edit sub-configs directly:

        MASTER_CONFIG.catalog.jpl_limit = 10_000
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
        """Where the mined material is sold - 'earth_surface', 'leo', 'cislunar'."""
        return self.mineral.delivery_destination

    @delivery_destination.setter
    def delivery_destination(self, value: str) -> None:
        self.mineral.delivery_destination = value
        self.calc.delivery_destination    = value

    @property
    def catalog(self):   return CATALOG_CONFIG
    @property
    def mineral(self):   return MINERAL_CONFIG
    @property
    def transport(self): return TRANSPORT_CONFIG
    @property
    def calc(self):      return CALC_CONFIG

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
print(f"      JPL limit        : {MASTER_CONFIG.catalog.jpl_limit:,} asteroids")
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
print(f"      Beneficiation    : "
      + ("ON - concentrate, not run-of-mine ore (~%.1fx runtime; "
         "False for the raw cell)"
         % beneficiation_cost_ratio(MASTER_CONFIG.calc.optimise_programme_scale)
         if MASTER_CONFIG.calc.use_beneficiation else
         "off - flying run-of-mine ore at bulk grade"))
print(f"      Programme        : "
      + ("(fleet <= %d) x (campaigns/ship) searched; N follows (~%.1fx runtime)"
         % (MASTER_CONFIG.calc.max_fleet_ships,
            programme_search_cost_ratio(MASTER_CONFIG.calc.use_beneficiation))
         if MASTER_CONFIG.calc.optimise_programme_scale else
         "fixed size (set calc.optimise_programme_scale to search it)"))
if MASTER_CONFIG.calc.use_beneficiation and MASTER_CONFIG.calc.optimise_programme_scale:
    print(f"                         both on: ~{_both_on:.1f}x the raw N = 1 cell")
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
    print("    MASTER ASTEROID PROFITABILITY PIPELINE - v1.20.8")
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
# AUTO-RUN
# -----------------------------------------------------------------------------
# Runs when executed as a script (`python master.py`) or pasted into a Colab /
# Jupyter cell - both give __name__ == "__main__".  Importing this file for its
# functions is side-effect free.  Force either way by setting MASTER_AUTORUN
# before the file executes.

MASTER_AUTORUN = globals().get("MASTER_AUTORUN", __name__ == "__main__")
if MASTER_AUTORUN:
    results = run_full_pipeline(MASTER_CONFIG)
'''


# -----------------------------------------------------------------------------
# SECTION SEPARATORS
# -----------------------------------------------------------------------------

def section_banner(name):
    bar = "=" * 73
    return f"\n\n# {bar}\n# {name}\n# {bar}\n\n"


# -----------------------------------------------------------------------------
# WRITE OUTPUT
# -----------------------------------------------------------------------------
with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
    f.write(MASTER_HEADER)
    f.write(section_banner("MODULE 1 - ASTEROID CATALOG BUILDER"))
    f.write(m1)
    f.write(section_banner("MODULE 2 - MINERAL VALUE CATALOG"))
    f.write(m2)
    f.write(section_banner("MODULE 3 - TRANSPORTATION DATA"))
    f.write(m3)
    f.write(section_banner("MODULE 4 - PROFITABILITY CALCULATOR"))
    f.write(m4)
    f.write(MASTER_ORCHESTRATOR)

# Verify the generated file is syntactically valid before declaring success.
import py_compile
_check = os.path.join(HERE, ".master_check.pyc")
py_compile.compile(OUT_PATH, doraise=True, cfile=_check)
os.remove(_check)

# -- Shadowed top-level names -------------------------------------------------
# The renames above are maintained by hand, so a collision introduced by a
# module edit lands silently: Python just lets the last definition win, and
# the master quietly runs the wrong function.  Syntax-checking cannot see it.
# Parse what we actually wrote and report.
#
# Some duplication is by design - each module is standalone-runnable, so the
# ones listed here are expected and identical in every copy.  Anything else
# is a real collision.
import ast as _ast
from collections import defaultdict as _defaultdict

_EXPECTED_DUPES = {
    # every module resolves its own default output dir when run alone
    "_default_output_dir", "_DEFAULT_OUTPUT_DIR",
    # standard gravity: Module 3 defines it, Module 4 repeats it verbatim
    "G0_M_S2",
}

with open(OUT_PATH, encoding="utf-8") as f:
    _built = f.read()

_top = _defaultdict(list)
for _node in _ast.parse(_built).body:
    if isinstance(_node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
        _top[_node.name].append(_node.lineno)
    elif isinstance(_node, _ast.Assign):
        for _t in _node.targets:
            if isinstance(_t, _ast.Name):
                _top[_t.id].append(_node.lineno)

_collisions = {k: v for k, v in _top.items()
               if len(v) > 1 and k not in _EXPECTED_DUPES}

size = os.path.getsize(OUT_PATH)
with open(OUT_PATH, encoding="utf-8") as f:
    lines = sum(1 for _ in f)
print(f"Wrote: {OUT_PATH}")
print(f"  size : {size:>10,} bytes")
print(f"  lines: {lines:>10,}")
print("  syntax: OK")

if _collisions:
    print(f"  WARN   {len(_collisions)} shadowed top-level name(s) - the LAST "
          f"definition wins at runtime:")
    for _name, _linenos in sorted(_collisions.items()):
        print(f"        {_name}  defined at lines {_linenos}")
    print("        -> add a word_replace() rename above, or list the name in "
          "_EXPECTED_DUPES if the duplication is deliberate.")
else:
    print("  names : no unexpected shadowed definitions")
