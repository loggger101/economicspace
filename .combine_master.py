# -*- coding: utf-8 -*-
"""Combiner script — produces Master(<MASTER_VERSION>).py from the four modules.

This script is a one-shot build tool, NOT part of the pipeline.  It performs
surgical edits to each module so they coexist in one file without name
collisions:

  • Strip each module's top-of-file docstring (one master docstring will
    cover everything).
  • Strip each module's auto-install subprocess block (master has its own
    consolidated installer at the top).
  • Strip each module's `RUN & PREVIEW` block at the bottom (the master
    orchestrator drives execution instead).
  • Rename each module's `CONFIG` global to a unique name
    (CATALOG_CONFIG, MINERAL_CONFIG, TRANSPORT_CONFIG, CALC_CONFIG) so
    each module's `def build_X(config = CONFIG)` default keeps working.
  • Rename function-name collisions between modules (merge_sources,
    validate, build_catalog).

Run once via:  py .combine_master.py
"""
import re
import os
import sys

# Every diagnostic below is decorated with ✅ / ⚠️ / ✗.  Windows picks the
# locale code page (cp1252 here) for a redirected stdout, so `py
# .combine_master.py > build.log` would die with UnicodeEncodeError on the
# first of those — losing the build report, and losing the collision and
# strip warnings in exactly the case you kept a log to read them.  A live
# console is unaffected; this only matters when redirected.
for _stream in (sys.stdout, sys.stderr):
    _stream.reconfigure(encoding="utf-8")

PROJECT = r"G:/My Drive/Profitability Pipeline"

# Bump these four when a module is revised, and MASTER_VERSION with them.
# Every version string in the generated file is derived from these — nothing
# below hard-codes a number, so the built Master can't disagree with itself.
M1_VERSION = "1.0.6"
M2_VERSION = "1.1.4"
M3_VERSION = "1.2.4"
M4_VERSION = "1.3.6"
MASTER_VERSION = "1.4.3"

M1_PATH  = os.path.join(PROJECT, f"profitability_pipeline({M1_VERSION}).py")
M2_PATH  = os.path.join(PROJECT, f"MineralValue({M2_VERSION}).py")
M3_PATH  = os.path.join(PROJECT, f"TransportationData({M3_VERSION}).py")
M4_PATH  = os.path.join(PROJECT, f"CalcPipeline({M4_VERSION}).py")
OUT_PATH = os.path.join(PROJECT, f"Master({MASTER_VERSION}).py")


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
    """Remove the auto-install subprocess block.
    The block always ends with the print('All packages present') line."""
    return re.sub(
        r'# ─+\n# INSTALLATION\n# ─+\n.*?print\("✅  All packages present"\)\n',
        '', content, count=1, flags=re.DOTALL
    )


def strip_run_preview_block(content):
    """Remove everything from the `RUN & PREVIEW` section to end of file."""
    pattern = re.compile(r'\n# ─+\n# RUN [^\n]*\n# ─+.*', flags=re.DOTALL)
    return pattern.sub('\n', content)


def word_replace(content, old, new):
    """Replace a whole-word identifier (won't touch substrings)."""
    return re.sub(r'\b' + re.escape(old) + r'\b', new, content)


def prepare(path, label):
    """Read a module and apply all three strips, insisting each one bites.

    Every strip above is anchored to a literal the four modules happen to
    share.  A module edit that moves or renames its anchor turns that strip
    into a silent no-op and the text it should have cut lands in the master
    instead: a duplicate install block, a leaked module docstring, or —
    worst — the module's auto-run block firing partway down the file, so
    that stage re-runs while the master is still being imported.  None of
    those are name collisions, so the post-build check below would not
    notice.  Fail here instead, naming the module and the anchor that moved.
    """
    content = read(path)
    for strip, what in (
        (strip_top_docstring,     "module docstring"),
        (strip_install_block,     "auto-install block"),
        (strip_run_preview_block, "RUN & PREVIEW block"),
    ):
        stripped = strip(content)
        if stripped == content:
            raise SystemExit(
                f"✗ {label} ({os.path.basename(path)}): could not find the "
                f"{what} to strip.\n"
                f"  The anchor it keys off moved or was renamed — update "
                f"{strip.__name__}() in .combine_master.py to match."
            )
        content = stripped
    return content


# ─────────────────────────────────────────────────────────────────────────────
# READ + PROCESS EACH MODULE
# ─────────────────────────────────────────────────────────────────────────────
# Read each module and strip its docstring, install block and auto-run block.
m1 = prepare(M1_PATH, "Module 1")
m2 = prepare(M2_PATH, "Module 2")
m3 = prepare(M3_PATH, "Module 3")
m4 = prepare(M4_PATH, "Module 4")

# ── Rename per-module globals + functions to avoid collisions ────────────────
# Module 1: CONFIG → CATALOG_CONFIG, build_catalog → build_asteroid_catalog,
#           lookup_asteroid → lookup_asteroid_catalog
# Modules 1 and 4 both define lookup_asteroid — M1's searches the Stage-1
# asteroid catalog, M4's searches the Stage-4 profitability catalog.  M4's
# was silently winning and both help texts advertised the same name.  M4
# keeps the plain name (the profitability catalog is the headline output);
# M1's is renamed, and word_replace fixes its docstring + help text to match.
m1 = word_replace(m1, "CONFIG", "CATALOG_CONFIG")
m1 = word_replace(m1, "build_catalog", "build_asteroid_catalog")
m1 = word_replace(m1, "lookup_asteroid", "lookup_asteroid_catalog")

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

# Templates use @@TOKEN@@ placeholders rather than f-strings: the generated
# code is full of literal { } from its own f-strings, which would have to be
# doubled up everywhere.  fill_versions() below does the substitution.

MASTER_HEADER = '''# -*- coding: utf-8 -*-
"""Master Asteroid Profitability Pipeline (@@MASTER@@)

End-to-end SELF-CONTAINED pipeline that combines all four modules into a
single runnable file.  Copy-paste into Colab / Jupyter / your script and
run top-to-bottom — the orchestrator at the bottom executes everything.

    Stage 1  →  Asteroid Catalog        (Module 1, profitability_pipeline @@M1@@)
                JPL SBDB + MP3C + SsODNet + NEOWISE
                (Asterank removed in module v1.0.5)
                + PGM_ENRICHMENT_BY_TYPE per-spectral-type factors
    Stage 2  →  Mineral Value Catalog   (Module 2, MineralValue @@M2@@)
                yfinance live + USGS/LME reference + mineralogy
                + sperrylite / laurite / awaruite / native-pgm phases
    Stage 3  →  Transportation Data     (Module 3, TransportationData @@M3@@)
                Launch vehicles + propellants + Δv segments + ops costs
                (UNCREWED autonomous mining — no crew costs)
    Stage 4  →  Profitability Calc      (Module 4, CalcPipeline @@M4@@)
                Rocket eq cascade + cost cascade + per-asteroid ranking
                + PGM enrichment applied per asteroid (M-type 2×, V-type 0.2×)
                (Asterank Δv override removed in module v1.3.5)

Mission profile: UNCREWED autonomous mining spacecraft throughout (no
crew costs, no life-support overhead).

Output tree (under MASTER_CONFIG.output_dir, default /content/asteroid_pipeline):
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

Tuning:
    MASTER_CONFIG sits at the bottom of the master config section.  Edit:
        MASTER_CONFIG.output_dir                    (where everything lands)
        MASTER_CONFIG.catalog.jpl_limit             (asteroid catalog size)
        MASTER_CONFIG.calc.nre_amortization_missions (multi-mission NRE split)
        MASTER_CONFIG.calc.use_isru_return_propellant (ISRU on/off)
        MASTER_CONFIG.calc.eval_row_cap             (limit Stage 4 evaluations)
    Or set any sub-config field directly before run_full_pipeline() fires.

This file was machine-assembled from the four source modules by
.combine_master.py — to regenerate, re-run that script.
"""

# ─────────────────────────────────────────────────────────────────────────────
# CONSOLIDATED INSTALLATION
# ─────────────────────────────────────────────────────────────────────────────
# Union of every package required by the four modules.  Auto-installs at
# import time; safe to re-run.

import subprocess as _subprocess
import sys as _sys

_MASTER_REQUIRED = [
    "requests", "pandas", "numpy", "yfinance",
    "astropy", "astroquery", "tqdm", "pyarrow",
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
    output_dir: str = "/content/asteroid_pipeline"

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
    print("  🚀  MASTER ASTEROID PROFITABILITY PIPELINE — v@@MASTER@@")
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
# Default invocation — Colab / Jupyter / `python Master(@@MASTER@@).py`.
# To skip the auto-run (e.g. importing this file for its functions), set
#     MASTER_AUTORUN = False
# before importing, or comment out the call below.

MASTER_AUTORUN = globals().get("MASTER_AUTORUN", True)
if MASTER_AUTORUN:
    results = run_full_pipeline(MASTER_CONFIG)
'''


# ─────────────────────────────────────────────────────────────────────────────
# SECTION SEPARATORS
# ─────────────────────────────────────────────────────────────────────────────

def section_banner(name):
    bar = "═" * 73
    return f"\n\n# {bar}\n# {name}\n# {bar}\n\n"


def fill_versions(text):
    """Substitute the @@TOKEN@@ version placeholders in a template."""
    for token, value in (
        ("@@MASTER@@", MASTER_VERSION),
        ("@@M1@@", M1_VERSION), ("@@M2@@", M2_VERSION),
        ("@@M3@@", M3_VERSION), ("@@M4@@", M4_VERSION),
    ):
        text = text.replace(token, value)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# WRITE OUTPUT
# ─────────────────────────────────────────────────────────────────────────────
with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(fill_versions(MASTER_HEADER))
    f.write(section_banner("MODULE 1 — ASTEROID CATALOG BUILDER"))
    f.write(m1)
    f.write(section_banner("MODULE 2 — MINERAL VALUE CATALOG"))
    f.write(m2)
    f.write(section_banner("MODULE 3 — TRANSPORTATION DATA"))
    f.write(m3)
    f.write(section_banner("MODULE 4 — PROFITABILITY CALCULATOR"))
    f.write(m4)
    f.write(fill_versions(MASTER_ORCHESTRATOR))

# ─────────────────────────────────────────────────────────────────────────────
# POST-BUILD CHECKS
# ─────────────────────────────────────────────────────────────────────────────
# The renames above are maintained by hand, so a new collision introduced by
# a module edit would otherwise land silently — Python just lets the later
# definition win, and the master would quietly run the wrong function.  Parse
# what we actually wrote and say so.
import ast
from collections import defaultdict

with open(OUT_PATH, encoding="utf-8") as f:
    built = f.read()

try:
    tree = ast.parse(built)
except SyntaxError as e:
    raise SystemExit(f"✗ generated file does not parse: line {e.lineno}: {e.msg}")

top_level = defaultdict(list)
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        top_level[node.name].append(node.lineno)

collisions = {k: v for k, v in top_level.items() if len(v) > 1}

size  = os.path.getsize(OUT_PATH)
lines = built.count("\n") + 1
print(f"Wrote: {OUT_PATH}")
print(f"  size : {size:>10,} bytes")
print(f"  lines: {lines:>10,}")
print(f"  parse: OK")

if collisions:
    print(f"  ⚠️   {len(collisions)} shadowed top-level name(s) — the LAST "
          f"definition wins at runtime:")
    for name, linenos in sorted(collisions.items()):
        print(f"        {name}  defined at lines {linenos}")
    print("        → add a word_replace() rename above, or confirm the "
          "surviving definition is the one you want.")
else:
    print(f"  names: no shadowed top-level definitions")
