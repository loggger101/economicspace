# -*- coding: utf-8 -*-
"""Build script — assembles modules/*.py into the single-file master.py.

This is a build tool, NOT part of the pipeline.  It performs surgical edits
to each module so they coexist in one file without name collisions:

  • Strip each module's top-of-file docstring (one master docstring will
    cover everything).
  • Strip each module's auto-install block (master has its own consolidated
    installer, including the UTF-8 console fix, at the top).
  • Strip each module's `RUN & PREVIEW` block at the bottom (the master
    orchestrator drives execution instead).
  • Rename each module's `CONFIG` global to a unique name
    (CATALOG_CONFIG, MINERAL_CONFIG, TRANSPORT_CONFIG, CALC_CONFIG) so
    each module's `def build_X(config = CONFIG)` default keeps working.
  • Rename function-name collisions between modules (merge_sources,
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


# ─────────────────────────────────────────────────────────────────────────────
# SURGICAL EDIT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

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
        r'# ─+\n# INSTALLATION\n# ─+\n.*?print\("✅  All packages present"\)\n',
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


# ─────────────────────────────────────────────────────────────────────────────
# READ + PROCESS EACH MODULE
# ─────────────────────────────────────────────────────────────────────────────
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
    check("__main__" not in after, f"{label}: __main__ guard leaked into master")
    # The docstring strip is anchored to the coding line; if it silently
    # no-opped, the module's own docstring becomes a bare string expression
    # partway down master.py and its title contradicts the master's.
    check(not after.lstrip().startswith('"""'),
          f"{label}: module docstring survived the strip")

# ── Rename per-module globals + functions to avoid collisions ────────────────
# Module 1: CONFIG → CATALOG_CONFIG, build_catalog → build_asteroid_catalog
m1 = word_replace(m1, "CONFIG", "CATALOG_CONFIG")
m1 = word_replace(m1, "build_catalog", "build_asteroid_catalog")

# Module 2: CONFIG → MINERAL_CONFIG, merge_sources → merge_mineral_sources,
#           validate → validate_minerals
m2 = word_replace(m2, "CONFIG", "MINERAL_CONFIG")
m2 = word_replace(m2, "merge_sources", "merge_mineral_sources")
m2 = word_replace(m2, "validate",      "validate_minerals")

# Module 3: CONFIG → TRANSPORT_CONFIG, validate → validate_transport
m3 = word_replace(m3, "CONFIG",   "TRANSPORT_CONFIG")
m3 = word_replace(m3, "validate", "validate_transport")

# Module 4: CONFIG → CALC_CONFIG  (no other collisions)
m4 = word_replace(m4, "CONFIG", "CALC_CONFIG")


# ─────────────────────────────────────────────────────────────────────────────
# MASTER HEADER + ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

MASTER_HEADER = '''# -*- coding: utf-8 -*-
"""Master Asteroid Profitability Pipeline (1.4.4)

End-to-end SELF-CONTAINED pipeline that combines all four modules into a
single runnable file.  Copy-paste into Colab / Jupyter / your script and
run top-to-bottom — the orchestrator at the bottom executes everything.

    Stage 1  →  Asteroid Catalog        (modules/catalog.py 1.0.7)
                JPL SBDB + MP3C + SsODNet + NEOWISE
                + PGM_ENRICHMENT_BY_TYPE per-spectral-type factors
    Stage 2  →  Mineral Value Catalog   (modules/mineral_value.py 1.1.5)
                yfinance live + USGS/LME reference + mineralogy
                + sperrylite / laurite / awaruite / native-pgm phases
    Stage 3  →  Transportation Data     (modules/transportation.py 1.2.5)
                Launch vehicles + propellants + Δv segments + ops costs
                (UNCREWED autonomous mining — no crew costs)
    Stage 4  →  Profitability Calc      (modules/calc.py 1.3.7)
                Rocket eq cascade + cost cascade + per-asteroid ranking
                + PGM enrichment applied per asteroid (M-type 2×, V-type 0.2×)

Mission profile: UNCREWED autonomous mining spacecraft throughout (no
crew costs, no life-support overhead).

Output tree (under MASTER_CONFIG.output_dir):
    asteroid_catalog.csv               ← Stage 1 (~30-40 MB at 50k rows)
    rejected_entries.csv               ← Stage 1 (validation rejects)
    mineral_value_catalog.csv          ← Stage 2
    transportation/
        launch_vehicles.csv            ← Stage 3
        propellants.csv                ← Stage 3
        delta_v_segments.csv           ← Stage 3
        operational_costs.csv          ← Stage 3
        transportation_summary.csv     ← Stage 3 (vehicle × prop × segment)
    profitability_catalog.csv          ← Stage 4 (the headline output)

The output directory defaults to /content/asteroid_pipeline on Colab and
./asteroid_pipeline everywhere else; override with the environment variable
ASTEROID_PIPELINE_OUTPUT_DIR or by setting MASTER_CONFIG.output_dir.

Tuning:
    MASTER_CONFIG sits at the bottom of the master config section.  Edit:
        MASTER_CONFIG.output_dir                    (where everything lands)
        MASTER_CONFIG.catalog.jpl_limit             (asteroid catalog size)
        MASTER_CONFIG.calc.nre_amortization_missions (multi-mission NRE split)
        MASTER_CONFIG.calc.use_isru_return_propellant (ISRU on/off)
        MASTER_CONFIG.calc.eval_row_cap             (limit Stage 4 evaluations)
    Or set any sub-config field directly before run_full_pipeline() fires.

GENERATED FILE — do not edit by hand.  Machine-assembled from modules/*.py by
build_master.py; edit the modules and re-run that script.
"""

# ─────────────────────────────────────────────────────────────────────────────
# CONSOLE ENCODING
# ─────────────────────────────────────────────────────────────────────────────
# Windows consoles default to cp1252, which cannot encode the emoji used in
# this file's progress output.  Must happen before the first print().

import sys as _sys
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ─────────────────────────────────────────────────────────────────────────────
# CONSOLIDATED INSTALLATION
# ─────────────────────────────────────────────────────────────────────────────
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
    print(f"📦  Installing: {_master_missing} …")
    _subprocess.check_call(
        [_sys.executable, "-m", "pip", "install", "-q"] + _master_missing
    )
    print("✅  Install complete")
else:
    print("✅  All packages present")

'''


MASTER_ORCHESTRATOR = '''

# ═════════════════════════════════════════════════════════════════════════════
# ║                                                                           ║
# ║   ★  MASTER CONFIG — ONE PLACE TO TUNE EVERYTHING ★                      ║
# ║                                                                           ║
# ║   The MasterConfig wraps the four module-specific configs as properties.  ║
# ║   Each sub-config (CATALOG_CONFIG, MINERAL_CONFIG, TRANSPORT_CONFIG,      ║
# ║   CALC_CONFIG) was instantiated when its module section ran above.  This  ║
# ║   master object centralises the shared output directory and provides a    ║
# ║   single handle for the orchestrator.                                     ║
# ║                                                                           ║
# ═════════════════════════════════════════════════════════════════════════════

from dataclasses import dataclass as _master_dataclass

@_master_dataclass
class MasterConfig:
    """Composes the four module configs.  Edit sub-configs directly:

        MASTER_CONFIG.catalog.jpl_limit = 10_000
        MASTER_CONFIG.calc.use_isru_return_propellant = True
    """
    output_dir: str = _DEFAULT_OUTPUT_DIR

    @property
    def catalog(self):   return CATALOG_CONFIG
    @property
    def mineral(self):   return MINERAL_CONFIG
    @property
    def transport(self): return TRANSPORT_CONFIG
    @property
    def calc(self):      return CALC_CONFIG

    def apply(self):
        """Push master output_dir to every sub-config, create the dir tree."""
        self.catalog.output_dir   = self.output_dir
        self.mineral.output_dir   = self.output_dir
        self.transport.output_dir = self.output_dir
        self.calc.input_dir       = self.output_dir
        self.calc.output_dir      = self.output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(os.path.join(self.output_dir, self.transport.subdir),
                    exist_ok=True)


MASTER_CONFIG = MasterConfig()
MASTER_CONFIG.apply()

print()
print("=" * 75)
print("  ⚙️   MASTER CONFIG READY")
print(f"      Pipeline output  : {MASTER_CONFIG.output_dir}")
print(f"      JPL limit        : {MASTER_CONFIG.catalog.jpl_limit:,} asteroids")
print(f"      Eval row cap     : {MASTER_CONFIG.calc.eval_row_cap:,}")
print(f"      ISRU return      : {MASTER_CONFIG.calc.use_isru_return_propellant}")
print(f"      NRE amortise     : over {MASTER_CONFIG.calc.nre_amortization_missions} mission(s)")
print(f"      Contingency      : {MASTER_CONFIG.calc.contingency_fraction:.0%}")
print("=" * 75)


# ─────────────────────────────────────────────────────────────────────────────
# MASTER ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

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
    print("█" * 75)
    print("  🚀  MASTER ASTEROID PROFITABILITY PIPELINE — v1.4.4")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  output → {master.output_dir}")
    print("█" * 75)

    # ── Stage 1 — Asteroid Catalog ───────────────────────────────────────────
    print()
    print("▔" * 75)
    print("  STAGE 1 — ASTEROID CATALOG (Module 1)")
    print("▔" * 75)
    asteroid_df = build_asteroid_catalog(master.catalog)

    # ── Stage 2 — Mineral Value ──────────────────────────────────────────────
    print()
    print("▔" * 75)
    print("  STAGE 2 — MINERAL VALUE CATALOG (Module 2)")
    print("▔" * 75)
    mineral_df = build_mineral_value_catalog(master.mineral)

    # ── Stage 3 — Transportation ─────────────────────────────────────────────
    print()
    print("▔" * 75)
    print("  STAGE 3 — TRANSPORTATION COSTS (Module 3)")
    print("▔" * 75)
    transport_catalogs = build_transportation_catalog(master.transport)

    # ── Stage 4 — Profitability ──────────────────────────────────────────────
    print()
    print("▔" * 75)
    print("  STAGE 4 — PROFITABILITY ANALYSIS (Module 4)")
    print("▔" * 75)
    profit_df = build_profitability_catalog(master.calc)

    elapsed = (datetime.now() - t0).total_seconds()
    print()
    print("█" * 75)
    print("  ✅  MASTER PIPELINE COMPLETE")
    print(f"      Total elapsed     : {elapsed:.1f}s")
    print(f"      Asteroids         : {len(asteroid_df):,}")
    print(f"      Minerals priced   : {len(mineral_df):,}")
    print(f"      Profitability rows: {len(profit_df):,}")
    print(f"      Viable missions   : {int(profit_df['viable'].sum()) if not profit_df.empty else 0:,}")
    print(f"      Master output dir : {master.output_dir}")
    print("█" * 75)

    return {
        "asteroids":      asteroid_df,
        "minerals":       mineral_df,
        "transportation": transport_catalogs,
        "profitability":  profit_df,
        "master_config":  master,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-RUN
# ─────────────────────────────────────────────────────────────────────────────
# Runs when executed as a script (`python master.py`) or pasted into a Colab /
# Jupyter cell — both give __name__ == "__main__".  Importing this file for its
# functions is side-effect free.  Force either way by setting MASTER_AUTORUN
# before the file executes.

MASTER_AUTORUN = globals().get("MASTER_AUTORUN", __name__ == "__main__")
if MASTER_AUTORUN:
    results = run_full_pipeline(MASTER_CONFIG)
'''


# ─────────────────────────────────────────────────────────────────────────────
# SECTION SEPARATORS
# ─────────────────────────────────────────────────────────────────────────────

def section_banner(name):
    bar = "═" * 73
    return f"\n\n# {bar}\n# {name}\n# {bar}\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# WRITE OUTPUT
# ─────────────────────────────────────────────────────────────────────────────
with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
    f.write(MASTER_HEADER)
    f.write(section_banner("MODULE 1 — ASTEROID CATALOG BUILDER"))
    f.write(m1)
    f.write(section_banner("MODULE 2 — MINERAL VALUE CATALOG"))
    f.write(m2)
    f.write(section_banner("MODULE 3 — TRANSPORTATION DATA"))
    f.write(m3)
    f.write(section_banner("MODULE 4 — PROFITABILITY CALCULATOR"))
    f.write(m4)
    f.write(MASTER_ORCHESTRATOR)

# Verify the generated file is syntactically valid before declaring success.
import py_compile
_check = os.path.join(HERE, ".master_check.pyc")
py_compile.compile(OUT_PATH, doraise=True, cfile=_check)
os.remove(_check)

size = os.path.getsize(OUT_PATH)
with open(OUT_PATH, encoding="utf-8") as f:
    lines = sum(1 for _ in f)
print(f"Wrote: {OUT_PATH}")
print(f"  size : {size:>10,} bytes")
print(f"  lines: {lines:>10,}")
print("  syntax: OK")
