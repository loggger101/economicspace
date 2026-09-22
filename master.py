# -*- coding: utf-8 -*-
"""Master Asteroid Profitability Pipeline (1.30.0)

End-to-end SELF-CONTAINED pipeline that combines all four modules into a
single runnable file.  Copy-paste into Colab / Jupyter / your script and
run top-to-bottom - the orchestrator at the bottom executes everything.

    Stage 1  ->  Asteroid Catalog        (modules/catalog.py 1.1.1)
                JPL SBDB + MP3C + SsODNet + NEOWISE
                + PGM_ENRICHMENT_BY_TYPE per-spectral-type factors
    Stage 2  ->  Mineral Value Catalog   (modules/mineral_value.py 1.9.0)
                yfinance live + USGS/LME reference + mineralogy
                + sperrylite / laurite / awaruite / native-pgm phases
                + destination pricing for EVERY commodity
    Stage 3  ->  Transportation Data     (modules/transportation.py 1.14.0)
                Launch vehicles + propellants + dv segments + ops costs
                (UNCREWED autonomous mining - no crew costs)
    Stage 4  ->  Profitability Calc      (modules/calc.py 1.19.2)
                Rocket eq cascade + cost cascade + per-asteroid ranking
                + PGM enrichment applied per asteroid (M-type 2x, V-type 0.2x)
                + delivery architecture: earth_surface / leo / geo /
                  cislunar / lunar_surface / mars_orbit / mars_surface,
                  beneficiation,
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
    "requests", "pandas", "numpy", "yfinance", "tqdm", "pyarrow", "spacecost",
]
# import-name -> pip argument, for the packages where those differ.  Only
# `spacecost` does: it holds Stage 3's reference tables and is not on PyPI yet,
# so it installs from a TAGGED git ref rather than by name.  The tag is pinned
# rather than tracking main, because an untagged URL would silently change what
# a Colab paste installs.
# IF SPACECOST IS EVER PUBLISHED: put a pinned "spacecost==<version>" in
# requirements.txt
# and delete this dict; nothing else here changes.
_MASTER_PIP_SPEC = {
    "spacecost": "git+https://github.com/loggger101/spacecost@v0.3.0",
}
_master_missing = []
for _pkg in _MASTER_REQUIRED:
    try:
        __import__(_pkg)
    except ImportError:
        _master_missing.append(_MASTER_PIP_SPEC.get(_pkg, _pkg))
if _master_missing:
    print(f"PKG  Installing: {_master_missing} ...")
    _subprocess.check_call(
        [_sys.executable, "-m", "pip", "install", "-q"] + _master_missing
    )
    print("OK  Install complete")
else:
    print("OK  All packages present")



# =========================================================================
# MODULE 1 - ASTEROID CATALOG BUILDER
# =========================================================================


# ==============================================================================
#  ASTEROID MINING PIPELINE; MODULE 1: CATALOG BUILDER
#  Google Colab compatible, runs top-to-bottom as a single cell.
#
#  Active sources:
#    • NASA JPL Small-Body Database (SBDB)  - primary backbone (orbital + phys)
#    • MP3C (Observatoire Côte d'Azur)      - physical-properties compilation;
#                                             may be DNS-blocked from some
#                                             Colab runtimes (returns empty
#                                             gracefully if unreachable)
#    • SsODNet ssoBFT (IMCCE)               - Solar-system Best-estimate Table:
#                                             cross-matched best-of-literature
#                                             diameter, albedo, MASS, DENSITY,
#                                             rotation period, taxonomy, and
#                                             orbital elements for ~1.2 M
#                                             bodies.  Bulk-downloaded once
#                                             as a cached parquet file.
#    • NEOWISE Diameters & Albedos V2.0     - IR-measured diameters + V/NIR
#       (IRSA TAP: neowisesbpropv2)           albedos for ~150 k asteroids;
#                                             upgrades the diameter/albedo
#                                             columns wherever it overlaps.
#
#  The framework is multi-source by design.  To plug in additional catalogs
#  see the ADDITIONAL FETCHERS template section below; merge_sources / dedup
#  / validation work uniformly across however many sources you wire in.
#
#  Pipeline flow:
#    Fetch  →  Merge  →  Validate (failsafes)  →  Enrich  →  Export
# ==============================================================================




# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import json
import os
# Aliased because build_master.py concatenates four modules into one namespace,
# and a bare `time` is a name three of them could plausibly bind to something
# else.  The alias is local to this module's own usage either way.
import time as _time
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from tqdm.auto import tqdm

# The launcher to name in a printed instruction.  `py` is the Windows launcher
# and exists nowhere else, so a hint that says it is wrong advice on the host
# that most needs the hint.  Deliberately not shared with the other modules:
# each has to stay standalone for the Colab paste, and build_master.py's AST
# scan is what catches it if a second copy ever appears.
_PY = "py" if os.name == "nt" else os.path.basename(sys.executable)

# Silence the chronic noise the data libraries emit during a typical run, but
# DON'T globally suppress everything, real RuntimeWarnings (e.g. divide-by-zero
# in our mass calculation) should still surface so we can spot bugs.
for _cat in (DeprecationWarning, FutureWarning, UserWarning):
    warnings.filterwarnings("ignore", category=_cat)

pd.set_option("display.max_columns", None)
# `{:.4g}` (general format) renders small numbers in fixed-point and large ones
# in scientific, so orbital elements still read as e.g. 0.1769 but estimated
# masses display as 9.39e+20 instead of `939000000000000000000.0000`.
pd.set_option("display.float_format", "{:.4g}".format)


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
    # Colab detection.  os.path.isdir("/content") alone is not enough: on
    # Windows a leading "/" is drive-relative, so it tests C:\content -- a
    # directory an earlier run of the pre-fix code may itself have created,
    # which would route output straight back to the path this function
    # exists to avoid.  Require a POSIX platform as well.
    if os.name == "posix" and os.path.isdir("/content"):
        return "/content/asteroid_pipeline"
    return os.path.join(os.getcwd(), "asteroid_pipeline")


_DEFAULT_OUTPUT_DIR = _default_output_dir()


# ═════════════════════════════════════════════════════════════════════════════
# ║                                                                           ║
# ║   ★  USER SETTINGS, EDIT THESE TO TUNE THE PIPELINE  ★                  ║
# ║                                                                           ║
# ║   Every knob the casual user is expected to touch lives in this single    ║
# ║   dataclass.  Each field has a brief note describing what it controls,    ║
# ║   the default value, and (where relevant) the range / common values.      ║
# ║                                                                           ║
# ║   Nothing below this block needs editing for normal use.                  ║
# ║                                                                           ║
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class CatalogConfig:
    """User-editable pipeline configuration.  See per-field comments below."""

    # ─── SOURCE TOGGLES ───────────────────────────────────────────────────────
    # Set any of these to False to skip that source.  An unreachable or empty
    # source is silently tolerated by the pipeline; you don't need to flip the
    # toggle just because a host is down.
    use_jpl:      bool = True   # NASA JPL Small-Body Database     (orbital + physical)
    use_mp3c:     bool = True   # MP3C @ Observatoire Côte d'Azur   (physical compilation)
    use_ssodnet:  bool = True   # SsODNet ssoBFT (IMCCE)            (mass, density, taxonomy, …)
    use_neowise:  bool = True   # NEOWISE V2.0 via IRSA TAP         (IR diameters + albedos)
    # To add a new catalog: write a fetch_<name>(config) function and add a
    # matching `use_<name>: bool = True` line here.

    # ─── FETCH LIMITS & NETWORK ──────────────────────────────────────────────
    # ONE CAP PER SOURCE, and 0 means "no cap, take the whole table".
    #
    # Until v1.1.0 `jpl_limit` was reused as the row cap for every source, which
    # quietly made the catalog SMALLER than any single source.  Each fetcher
    # takes its first N rows ordered by asteroid number, so four sources capped
    # at the same N return substantially the SAME N bodies; the merge then
    # collapses them and the union is ~N rather than 4N.  Raising the shared cap
    # to reach further down one source dragged every other source along with it.
    #
    # Measured 2026-08-08 against the live APIs, which is what the defaults are
    # sized from:
    #     JPL SBDB      1,554,321 asteroids   (139,582 with a measured diameter)
    #     SsODNet        ~1,200,000 rows      (~500 MB parquet, cached)
    #     NEOWISE V2.0     183,412 rows       (143,318 unique bodies w/ diameter)
    #     MP3C           varies; frequently unreachable
    #
    # 0 (unlimited) is the default because JPL is the only source of orbital
    # elements, so a body it does not return cannot be evaluated no matter what
    # the other sources know about it.  The full JPL pull is ~435 MB / ~80 s on
    # a warm connection; NEOWISE unlimited is ~19 MB / ~30 s.  Set a cap if you
    # want a fast interactive run: 50_000 reproduces the pre-v1.1.0 behaviour.
    jpl_limit:       int = 0   # 0 = all 1.55 M asteroids (orbital elements)
    ssodnet_limit:   int = 0   # 0 = whole cached ssoBFT table
    neowise_limit:   int = 0   # 0 = all 183 k NEOWISE rows

    # Ask IRSA for the NEOWISE table as an asynchronous (IVOA UWS) job rather
    # than a single synchronous request.  A sync query holds one connection
    # open for the server-side query AND the ~19 MB transfer, so a proxy
    # timeout anywhere in that window discards the whole result with nothing to
    # retry; that is the 502 that made NEOWISE contribute 0 rows to the run
    # behind the committed cislunar 2x2.  Async runs the job server-side and
    # leaves the result at a stable, re-fetchable URL.  Falls back to the
    # synchronous path on any failure, so turning this off only removes a way
    # to succeed.  Same ADQL and same rows either way, verified byte-identical.
    neowise_use_async: bool = True

    # How long to poll an async NEOWISE job before giving up and falling back.
    # The full table completes in well under a minute; this is a ceiling for a
    # service under load, not an expected wait.
    neowise_async_max_wait_s: int = 900
    mp3c_limit:      int = 0   # 0 = whatever MP3C will serve
    request_timeout: int = 300 # seconds per HTTP request before giving up (5 min)

    # ─── QUALITY GATES  (enforced in validate_and_filter) ────────────────────
    # `min_diameter_km` drops anything below this size.  Default 0.001 km =
    # 1 metre (essentially "keep everything that has a positive diameter").
    # Bump to e.g. 1.0 to focus on >=1-km bodies.
    min_diameter_km: float = 0.001

    # If True, asteroids with no spectral classification (Bus / Tholen) are
    # rejected.  Useful for compositional studies; False keeps more rows.
    require_spectral_type: bool = False

    # ─── DERIVED DIAMETERS  (v1.1.0) ─────────────────────────────────────────
    # validate_and_filter drops any body without a diameter, and only 139,582
    # of JPL's 1,554,321 asteroids have one measured.  1,553,812 have an
    # absolute magnitude H and a valid orbit, and diameter follows from H and
    # the geometric albedo exactly:
    #
    #     D_km = (1329 / sqrt(p_V)) * 10**(-H/5)          (Fowler & Chillemi 1992)
    #
    # so the ONLY thing being estimated is p_V.  With this on, the evaluable
    # population goes from ~139 k to ~1.55 M, an 11x larger catalog whose extra
    # rows carry a diameter uncertain by roughly the square root of the albedo
    # error, and a MASS uncertain by that cubed.  Every such row is tagged
    # `diameter_source = "derived_h_*"`; a measured diameter always wins, and
    # `derived_diameter_is_estimate` gives downstream code a single boolean to
    # filter on.  Turn this off for a measured-only catalog.
    derive_diameter_from_h: bool = True

    # Floor on DERIVED diameters only (km).  Measured diameters are governed by
    # `min_diameter_km` above and are never subject to this.  0.0 keeps every
    # derived body; raise it to trim the sub-kilometre tail, which is most of
    # the 1.4 M and is where the albedo assumption hurts most.
    min_derived_diameter_km: float = 0.0

    # ─── OUTPUT  (where the CSVs land) ───────────────────────────────────────
    # `output_dir` is created at startup if it doesn't exist.  On Colab the
    # default '/content/...' lives in the session sandbox, change to a Drive
    # path like '/content/drive/MyDrive/asteroids' to persist between runs.
    output_dir:        str = _DEFAULT_OUTPUT_DIR
    catalog_filename:  str = "asteroid_catalog.csv"
    rejected_filename: str = "rejected_entries.csv"

    # ─── BULK-DOWNLOAD CACHE  (SsODNet parquet & similar) ────────────────────
    # SsODNet's ssoBFT is ~500 MB.  We cache it once per `cache_max_age_days`
    # and re-use it between runs.  Bump max_age down to force a fresh pull.
    #
    # `cache_dir` controls WHERE the cache lives:
    #   • Empty string (default) → system tmp directory (good for Drive users:
    #                              the ~500 MB parquet does NOT round-trip
    #                              through Drive sync on every run).
    #   • Any absolute path      → that exact directory.
    # If you want the cache co-located with the catalog CSV instead, set this
    # to e.g. f"{output_dir}/_cache".
    cache_dir:           str   = ""

    # How long the ssoBFT parquet cache is reused before it is re-downloaded.
    # That download is ~500 MB, so raise this for repeated offline runs.
    cache_max_age_days:  float = 7.0

    # ─── PREVIEW & SUMMARY DISPLAY  (cosmetic, affects stdout only) ──────────
    preview_rows:           int = 10   # rows shown in CATALOG PREVIEW table
    top_n_spectral_types:   int = 20   # types listed in spectral-distribution bars

    # ─── PIPELINE VERSION  (bump when changing the schema) ───────────────────
    # Stamped into every output CSV, and the only way to tell which code
    # produced a given catalog.  BUMP IT when a change moves any number a run
    # produces.  The rule is ONE-DIRECTIONAL: changing a number means bumping,
    # and a bump does NOT mean a number changed, which is why nothing may read
    # a version as evidence that a result moved.
    # THE CHANGELOG IS versions.md, NOT THIS COMMENT.  It used to be 155 lines
    # of release notes sitting right here, a second copy of a record versions.md
    # already held, which is the documentation form of the defect this project
    # keeps cataloguing; it was also what the dashboard rendered as this field's
    # help text, because ui_meta scrapes a field's comment block.  Moved out on
    # 2026-09-02.  Two places to write, neither of them here:
    #     versions.md > Releases            what the release did, and what it
    #                                       measured to say so
    #     versions.md > Module changelogs   this module's own stamp-by-stamp
    #                                       record: Stage 1 changelog
    pipeline_version: str = "1.2.0"


# Instantiate and create the output dir.  Edit CATALOG_CONFIG values above this line
# (inside the dataclass); DO NOT mutate CATALOG_CONFIG fields here, that defeats the
# purpose of having a single editable source of truth.
CATALOG_CONFIG = CatalogConfig()
os.makedirs(CATALOG_CONFIG.output_dir, exist_ok=True)


def _resolve_cache_dir(config: "CatalogConfig") -> str:
    """
    Return the absolute path of the bulk-download cache.

    If `config.cache_dir` is non-empty, use it verbatim.  Otherwise default to
    a stable per-user location under the system tmp dir; this avoids the 526
    MB SsODNet parquet syncing through Google Drive on every refresh.
    """
    if config.cache_dir:
        path = config.cache_dir
    else:
        import tempfile
        path = os.path.join(tempfile.gettempdir(), "asteroid_pipeline_cache")
    os.makedirs(path, exist_ok=True)
    return path


# Eagerly create the default cache dir so first-run prints reflect the real path
os.makedirs(_resolve_cache_dir(CATALOG_CONFIG), exist_ok=True)

print(f"OK  Configuration loaded - output dir: {CATALOG_CONFIG.output_dir}")
print(f"    Active sources  : "
      f"{', '.join(s for s, on in (('JPL', CATALOG_CONFIG.use_jpl), ('MP3C', CATALOG_CONFIG.use_mp3c), ('SsODNet', CATALOG_CONFIG.use_ssodnet), ('NEOWISE', CATALOG_CONFIG.use_neowise)) if on)}")
def _fmt_limit(n: int) -> str:
    """Render a row cap for the banner; 0 is unlimited, not zero rows."""
    return "unlimited" if not n else f"{n:,}"


print(f"    Fetch limits    : "
      f"JPL {_fmt_limit(CATALOG_CONFIG.jpl_limit)}  |  "
      f"SsODNet {_fmt_limit(CATALOG_CONFIG.ssodnet_limit)}  |  "
      f"NEOWISE {_fmt_limit(CATALOG_CONFIG.neowise_limit)}  |  "
      f"MP3C {_fmt_limit(CATALOG_CONFIG.mp3c_limit)}")
print(f"    Min diameter    : {CATALOG_CONFIG.min_diameter_km} km")
print(f"    Strict taxonomy : {CATALOG_CONFIG.require_spectral_type}")
print(f"    H-derived diam. : "
      f"{'on - bodies with no measured diameter are sized from H + albedo' if CATALOG_CONFIG.derive_diameter_from_h else 'off - measured diameters only'}")


# ─────────────────────────────────────────────────────────────────────────────
# TAXONOMY & COMPOSITION LOOKUP TABLES
# ─────────────────────────────────────────────────────────────────────────────
#
# Bus-DeMeo (2009) taxonomy mapped to mineralogical composition estimates.
# Fractions are APPROXIMATE (literature mean values) and used as defaults
# when no direct measurement exists. density_est_gcm3 is the bulk estimate.

TAXONOMY_COMPOSITION: Dict[str, dict] = {

    # ── C-complex (carbonaceous) ──────────────────────────────────────────────
    "B": {
        "group": "C-complex",
        "composition": "Hydrated silicates, carbon, organics, possible ices",
        "minerals": ["phyllosilicates", "magnetite", "carbon", "organics"],
        "density_est_gcm3":  1.30,
        "metal_fraction":    0.01,
        "silicate_fraction": 0.30,
        "carbon_fraction":   0.30,
        "ice_fraction":      0.20,
        "notes": "Bluest C-complex; possible metamorphic overprint",
    },
    "C": {
        "group": "C-complex",
        "composition": "Carbonaceous: hydrated silicates, organics, carbon",
        "minerals": ["phyllosilicates", "carbon", "organics"],
        "density_est_gcm3":  1.50,
        "metal_fraction":    0.01,
        "silicate_fraction": 0.35,
        "carbon_fraction":   0.25,
        "ice_fraction":      0.15,
        "notes": "Most common asteroid type; CI/CM chondrite analogs",
    },
    "Cb": {
        "group": "C-complex",
        "composition": "Transitional C/B: carbonaceous, moderate hydration",
        "minerals": ["phyllosilicates", "carbon"],
        "density_est_gcm3":  1.40,
        "metal_fraction":    0.01,
        "silicate_fraction": 0.32,
        "carbon_fraction":   0.28,
        "ice_fraction":      0.18,
        "notes": "Intermediate between B and C",
    },
    "Cg": {
        "group": "C-complex",
        "composition": "Cg-type: CM chondrite analog, strong UV dropoff",
        "minerals": ["phyllosilicates", "carbon", "magnetite"],
        "density_est_gcm3":  1.50,
        "metal_fraction":    0.02,
        "silicate_fraction": 0.38,
        "carbon_fraction":   0.22,
        "ice_fraction":      0.12,
        "notes": "Strong UV absorption feature",
    },
    "Cgh": {
        "group": "C-complex",
        "composition": "CH/CK analog: hydrated silicates, olivine",
        "minerals": ["olivine", "phyllosilicates", "magnetite"],
        "density_est_gcm3":  1.60,
        "metal_fraction":    0.03,
        "silicate_fraction": 0.40,
        "carbon_fraction":   0.20,
        "ice_fraction":      0.10,
        "notes": "0.7-μm absorption band; high water content",
    },
    "Ch": {
        "group": "C-complex",
        "composition": "CM2 analog: hydrated silicates, low albedo",
        "minerals": ["phyllosilicates", "magnetite", "carbon"],
        "density_est_gcm3":  1.50,
        "metal_fraction":    0.02,
        "silicate_fraction": 0.38,
        "carbon_fraction":   0.25,
        "ice_fraction":      0.10,
        "notes": "Strongest 0.7-μm feature in C-complex",
    },

    # ── S-complex (silicate / stony) ──────────────────────────────────────────
    "S": {
        "group": "S-complex",
        "composition": "Stony: olivine, pyroxene, nickel-iron mixture",
        "minerals": ["olivine", "pyroxene", "nickel-iron"],
        "density_est_gcm3":  2.70,
        "metal_fraction":    0.15,
        "silicate_fraction": 0.75,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Second-most common type; LL/L chondrite analogs",
    },
    "Sa": {
        "group": "S-complex",
        "composition": "S/A transitional: olivine-dominated stony",
        "minerals": ["olivine", "pyroxene"],
        "density_est_gcm3":  2.80,
        "metal_fraction":    0.12,
        "silicate_fraction": 0.80,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "High olivine / pyroxene ratio",
    },
    "Sk": {
        "group": "S-complex",
        "composition": "S/K transitional stony",
        "minerals": ["olivine", "pyroxene", "oxides"],
        "density_est_gcm3":  2.60,
        "metal_fraction":    0.10,
        "silicate_fraction": 0.78,
        "carbon_fraction":   0.02,
        "ice_fraction":      0.00,
        "notes": "Intermediate S and K spectral features",
    },
    "Sl": {
        "group": "S-complex",
        "composition": "S/L transitional: spinel-bearing stony",
        "minerals": ["olivine", "pyroxene", "spinel"],
        "density_est_gcm3":  2.70,
        "metal_fraction":    0.12,
        "silicate_fraction": 0.78,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Intermediate S and L spectral features",
    },
    "Sq": {
        "group": "S-complex",
        "composition": "S/Q transitional: LL/L ordinary chondrite analog",
        "minerals": ["olivine", "pyroxene", "nickel-iron"],
        "density_est_gcm3":  2.80,
        "metal_fraction":    0.15,
        "silicate_fraction": 0.78,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Possible fresh/unweathered S surface",
    },
    "Sr": {
        "group": "S-complex",
        "composition": "S/R transitional stony",
        "minerals": ["pyroxene", "olivine"],
        "density_est_gcm3":  2.90,
        "metal_fraction":    0.12,
        "silicate_fraction": 0.82,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Intermediate S and R spectral features",
    },
    "Sv": {
        "group": "S-complex",
        "composition": "S/V transitional stony-basaltic",
        "minerals": ["pyroxene", "olivine", "plagioclase"],
        "density_est_gcm3":  3.00,
        "metal_fraction":    0.08,
        "silicate_fraction": 0.85,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Intermediate S and V spectral features",
    },

    # ── X-complex (metallic / enstatite / primitive) ──────────────────────────
    "X": {
        "group": "X-complex",
        "composition": "X-type: possibly metallic or primitive (albedo ambiguous)",
        "minerals": ["nickel-iron", "enstatite", "troilite"],
        "density_est_gcm3":  3.30,
        "metal_fraction":    0.30,
        "silicate_fraction": 0.50,
        "carbon_fraction":   0.05,
        "ice_fraction":      0.00,
        "notes": "Requires albedo to distinguish M, E, or P sub-type.  v1.0.8: "
                 "metal 0.40 → 0.30, tracking the M revision — an unresolved "
                 "X sits between metal-rich M and near-metal-free P.",
    },
    "Xc": {
        "group": "X-complex",
        "composition": "Xc-type: low-albedo metallic, possibly carbonaceous",
        "minerals": ["carbon", "nickel-iron"],
        "density_est_gcm3":  2.50,
        "metal_fraction":    0.25,
        "silicate_fraction": 0.35,
        "carbon_fraction":   0.20,
        "ice_fraction":      0.00,
        "notes": "Low albedo suggests carbonaceous metallic mix",
    },
    "Xe": {
        "group": "X-complex",
        "composition": "Xe-type (M-type analog): metal-rich, metal-silicate mix",
        "minerals": ["nickel-iron", "troilite", "enstatite"],
        "density_est_gcm3":  3.80,
        "metal_fraction":    0.45,
        "silicate_fraction": 0.45,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "High-albedo X; metal-rich but not a bare core.  v1.0.8: "
                 "was 0.75 metal / 5.00 g/cm³ — tracked down alongside M for "
                 "the same measured-density reason.",
    },
    "Xk": {
        "group": "X-complex",
        "composition": "Xk-type: E-chondrite analog, enstatite dominant",
        "minerals": ["enstatite", "nickel-iron", "troilite"],
        "density_est_gcm3":  3.60,
        "metal_fraction":    0.25,
        "silicate_fraction": 0.65,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "E-chondrite analog; high albedo.  v1.0.8: metal 0.50 → 0.25 "
                 "— EH/EL enstatite chondrites carry ~20-25 wt% metal, and "
                 "'enstatite dominant' cannot also be half metal.",
    },

    # ── Other spectral types ──────────────────────────────────────────────────
    "A": {
        "group": "A-type",
        "composition": "Dunite/olivine-rich: possible differentiated mantle fragment",
        "minerals": ["olivine"],
        "density_est_gcm3":  3.20,
        "metal_fraction":    0.05,
        "silicate_fraction": 0.90,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Very strong 1-μm olivine band; rare type",
    },
    "D": {
        "group": "D-type",
        "composition": "Primitive: organics, anhydrous silicates, possible ices",
        "minerals": ["organics", "silicates", "carbon"],
        "density_est_gcm3":  1.20,
        "metal_fraction":    0.01,
        "silicate_fraction": 0.25,
        "carbon_fraction":   0.30,
        "ice_fraction":      0.25,
        "notes": "Featureless red spectrum; Trojan/outer-belt analog",
    },
    "K": {
        "group": "K-type",
        "composition": "CV/CO chondrite analog: olivine, pyroxene, oxides",
        "minerals": ["olivine", "pyroxene", "magnetite"],
        "density_est_gcm3":  2.50,
        "metal_fraction":    0.08,
        "silicate_fraction": 0.72,
        "carbon_fraction":   0.08,
        "ice_fraction":      0.00,
        "notes": "Intermediate C and S features; moderate albedo",
    },
    "L": {
        "group": "L-type",
        "composition": "Spinel-bearing: anhydrous silicates, high albedo",
        "minerals": ["spinel", "olivine", "pyroxene"],
        "density_est_gcm3":  2.80,
        "metal_fraction":    0.05,
        "silicate_fraction": 0.85,
        "carbon_fraction":   0.02,
        "ice_fraction":      0.00,
        "notes": "Unusual spinel absorption; possibly CV3 chondrite",
    },
    "O": {
        "group": "O-type",
        "composition": "Olivine-orthopyroxene mixture (very rare)",
        "minerals": ["olivine", "orthopyroxene"],
        "density_est_gcm3":  2.90,
        "metal_fraction":    0.08,
        "silicate_fraction": 0.85,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Only a handful of known O-types",
    },
    "Q": {
        "group": "Q-type",
        "composition": "Ordinary chondrite: olivine, pyroxene, metal",
        "minerals": ["olivine", "pyroxene", "nickel-iron"],
        "density_est_gcm3":  3.00,
        "metal_fraction":    0.20,
        "silicate_fraction": 0.72,
        "carbon_fraction":   0.02,
        "ice_fraction":      0.00,
        "notes": "Fresh/unweathered ordinary chondrite analog",
    },
    "R": {
        "group": "R-type",
        "composition": "Olivine-pyroxene mantle fragment (rare)",
        "minerals": ["olivine", "pyroxene"],
        "density_est_gcm3":  3.10,
        "metal_fraction":    0.05,
        "silicate_fraction": 0.90,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Very rare; possible differentiated mantle fragment",
    },
    "T": {
        "group": "T-type",
        "composition": "Primitive: organics, troilite, Fe-silicates",
        "minerals": ["troilite", "organics", "silicates"],
        "density_est_gcm3":  1.80,
        "metal_fraction":    0.05,
        "silicate_fraction": 0.40,
        "carbon_fraction":   0.25,
        "ice_fraction":      0.10,
        "notes": "Featureless red; possibly primitive body",
    },
    "V": {
        "group": "V-type",
        "composition": "Basaltic crust fragment (HED meteorite analog)",
        "minerals": ["pyroxene", "plagioclase", "olivine"],
        "density_est_gcm3":  2.90,
        "metal_fraction":    0.05,
        "silicate_fraction": 0.90,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Vestoids / Vesta family; strong pyroxene bands",
    },

    # ── Tholen-only types (no direct Bus-DeMeo equivalent) ────────────────────
    # The Tholen (1984) taxonomy uses a few letters that Bus-DeMeo (2009)
    # subsequently absorbed into the X- and C-complex.  We keep them as
    # first-class entries here so the enrichment step can use a JPL
    # `spec_T` value directly when `spec_B` is empty.
    "M": {
        "group": "X-complex",
        "composition": "Metallic (Tholen): metal-silicate mix, core-fragment affinity",
        "minerals": ["nickel-iron", "troilite", "enstatite"],
        "density_est_gcm3":  3.90,
        "metal_fraction":    0.50,
        "silicate_fraction": 0.45,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Tholen M-type ≈ Bus-DeMeo Xe; high IR albedo, low optical.  "
                 "v1.0.8: was 0.80 metal / 5.30 g/cm³, the pre-Psyche "
                 "'exposed iron core' assumption.  16 Psyche's measured bulk "
                 "density is ~3.8-3.9 g/cm³ (Elkins-Tanton et al. 2020, "
                 "Siltala & Granvik 2021) — far below the 7.8 g/cm³ of iron "
                 "meteorite — and metal content is now put at roughly "
                 "30-60%.  A solid-metal M-type is not supported by any "
                 "measured density.",
    },
    "E": {
        "group": "X-complex",
        "composition": "Enstatite (Tholen): aubrite/E-chondrite analog",
        "minerals": ["enstatite", "nickel-iron"],
        "density_est_gcm3":  3.20,
        "metal_fraction":    0.10,
        "silicate_fraction": 0.85,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "Tholen E-type ≈ Bus-DeMeo Xk; very high albedo (>0.3).  "
                 "v1.0.8: metal 0.30 → 0.10 — aubrites are enstatite "
                 "achondrites and are very nearly metal-free.",
    },
    "P": {
        "group": "C-complex",
        "composition": "Primitive (Tholen): low albedo, organics + silicates",
        "minerals": ["organics", "silicates", "carbon"],
        "density_est_gcm3":  1.80,
        "metal_fraction":    0.02,
        "silicate_fraction": 0.35,
        "carbon_fraction":   0.25,
        "ice_fraction":      0.15,
        "notes": "Tholen P-type ≈ Bus-DeMeo Xc / D; outer-belt primitive",
    },
    "F": {
        "group": "C-complex",
        "composition": "Flat-spectrum carbonaceous (Tholen): dehydrated CM",
        "minerals": ["phyllosilicates", "carbon"],
        "density_est_gcm3":  1.40,
        "metal_fraction":    0.01,
        "silicate_fraction": 0.35,
        "carbon_fraction":   0.28,
        "ice_fraction":      0.15,
        "notes": "Tholen F-type ≈ Bus-DeMeo B; flat featureless spectrum",
    },
    "G": {
        "group": "C-complex",
        "composition": "G-type (Tholen): C-complex with UV dropoff",
        "minerals": ["phyllosilicates", "carbon", "magnetite"],
        "density_est_gcm3":  1.50,
        "metal_fraction":    0.02,
        "silicate_fraction": 0.38,
        "carbon_fraction":   0.22,
        "ice_fraction":      0.12,
        "notes": "Tholen G-type ≈ Bus-DeMeo Cg; Ceres-like",
    },

    # ── Fallback ──────────────────────────────────────────────────────────────
    "Unknown": {
        "group": "Unknown",
        "composition": "Unknown — insufficient spectral data",
        "minerals": [],
        "density_est_gcm3":  None,
        "metal_fraction":    None,
        "silicate_fraction": None,
        "carbon_fraction":   None,
        "ice_fraction":      None,
        "notes": "No spectral classification available",
    },
}

print(f"OK  Taxonomy lookup ready - {len(TAXONOMY_COMPOSITION)} spectral types defined")


# ─────────────────────────────────────────────────────────────────────────────
# PGM ENRICHMENT BY SPECTRAL TYPE  (v1.0.4)
# ─────────────────────────────────────────────────────────────────────────────
# Multiplier applied to the platinum-group-metal (PGM) yields in Module 2's
# "nickel-iron" mineral when valuing an asteroid of this spectral type.
# Baseline 1.0× is calibrated to chondritic / mean-iron-meteorite PGM
# concentration (~37 ppm total PGM+Au in nickel-iron alloy).
#
# Why per-type variation matters:
#   • Differentiated parent bodies (M-type / Xe / E asteroids, fragments
#     of cores or near-core regions) concentrated PGMs into the metal
#     phase during melting, so their nickel-iron grains have ELEVATED PGM
#     vs chondritic average.
#   • Basaltic-crust fragments (V-type, Vesta family) lost their PGM to
#     the core during their parent body's differentiation; their metal
#     grains are PGM-DEPLETED.
#   • Mantle fragments (A, R, O) sit between, partially depleted.
#   • Primitive bodies (C-complex, ordinary chondrites) never differentiated,
#     so PGMs remained uniformly distributed in metal grains → baseline.
#
# These factors only multiply the RARE-METAL portion (Pt, Pd, Ru, Ir, Os,
# Rh, Au) of the nickel-iron yield in Module 4; base metals (Fe, Ni, Co)
# are unaffected.  Conservative midpoints; the literature variance is huge
# (iron meteorite Ir alone ranges 0.01-19 ppm).

PGM_ENRICHMENT_BY_TYPE: Dict[str, float] = {
    # ── Differentiated core fragments, PGMs concentrated by metal-segregation ──
    "M":  2.0,   # Tholen metallic (e.g. 16 Psyche)
    "Xe": 2.0,   # Bus-DeMeo M-analog
    "Xk": 1.5,   # E-chondrite / aubrite analog, partial differentiation
    "X":  1.5,   # X-complex ambiguous (assume partial)
    "Xc": 1.2,   # low-albedo X: partially carbonaceous
    "E":  1.5,   # Tholen enstatite, aubrite analog

    # ── Mantle / lower-mantle fragments: partial PGM depletion ──
    "A":  0.5,   # dunite, olivine-dominated mantle
    "R":  0.5,   # olivine-pyroxene mantle fragment
    "O":  0.5,   # olivine-orthopyroxene (rare, ureilite-class)

    # ── Basaltic crust, PGMs largely extracted into core during differentiation ──
    "V":  0.2,   # Vesta family / HED meteorite analog

    # ── Everything else: baseline 1.0× (chondritic / primitive: get via .get default) ──
    # C, Cb, Cg, Cgh, Ch, B, S, Sa, Sk, Sl, Sq, Sr, Sv, Q, K, L, D, T, P, F, G, Unknown
}


def _by_distinct(col: "pd.Series", fn):
    """`col.apply(fn)` evaluated once per DISTINCT value instead of per row.

    v1.1.1.  Everything this module derives from `spectral_type` is a lookup
    keyed on a taxonomy class, and there are **76 distinct classes across
    1,555,667 rows**, so twelve `.apply()` passes (nine composition fields,
    two capitalisation passes, and the PGM multiplier) were making ~19 million
    calls to produce ~800 answers.  Each of those calls ran `pd.isna` on a
    scalar, which is a pandas dispatch at ~1 µs.  Measured on the real
    1,555,667-row catalog, `enrich_composition` goes **9.09 s -> 2.35 s
    (3.87x)**; that is the whole function, of which the rest (the Tholen and
    albedo fallbacks, the masks, the counts) is unchanged.

    Same finding, and the same fix, as `_parse_minerals_column` in Stage 4, 
    which is the point: the pattern is "a column with few distinct values, one
    Python call per row", and this pipeline has it in both directions.

    `factorize` rather than `unique` + a dict because it is total: NaN is a
    code like any other, so a missing taxonomy cannot fall through a lookup
    that `nan != nan` would silently break.

    ⚠️  The result array is built with `np.empty(..., dtype=object)` and filled,
    NOT `np.array([...])`.  Some of these fields are LISTS (`comp_minerals`),
    and `np.array` of equal-length lists builds a 2-D array instead of an array
    of lists, which would reshape the column rather than fill it.

    ⚠️  `.infer_objects()` at the end is NOT cosmetic, and leaving it off is
    how this change failed its first verification. `Series.apply()` builds its
    result through `maybe_convert_objects`, so a column of floats-and-`None`
    comes back **float64 with NaN**, and a column of floats comes back
    float64 rather than object. Filling an object array and stopping there
    keeps `None` as `None` and the dtype as `object`: 53 rows of
    `comp_metal_fraction` differed on exactly that, and `comp_pgm_enrichment`
    changed dtype under a column whose values were all equal. `infer_objects`
    runs the same conversion `apply` does, so lists stay lists, strings stay
    strings, and the numeric columns land where they always did.

    ⚠️  Values are SHARED across rows that share a class, exactly as
    `.apply()` shared them: `_lookup` returns the object straight out of
    `TAXONOMY_COMPOSITION`, so every C-type row already pointed at one list.
    Stage 1 writes this to CSV and never mutates it.  (Stage 4 re-reads it and
    deliberately does NOT share; see `_parse_minerals_column`.)
    """
    codes, uniques = pd.factorize(col, use_na_sentinel=False)
    resolved = np.empty(len(uniques), dtype=object)
    for i, u in enumerate(uniques):
        resolved[i] = fn(u)
    return pd.Series(resolved[codes], index=col.index,
                     name=col.name).infer_objects()


def pgm_enrichment_for_type(spec_type) -> float:
    """Return the PGM enrichment multiplier for a Bus-DeMeo / Tholen type.

    Default 1.0 (chondritic) for unknown / unlisted types.  Falls back to
    first-character match (e.g. unknown sub-type 'Mq' → 'M' → 2.0) so
    minor sub-type variants inherit the parent class's enrichment.
    """
    if spec_type is None or (isinstance(spec_type, float) and pd.isna(spec_type)):
        return 1.0
    s = str(spec_type).strip()
    if not s:
        return 1.0
    if s in PGM_ENRICHMENT_BY_TYPE:
        return PGM_ENRICHMENT_BY_TYPE[s]
    # Fallback to first letter (e.g. 'Sq2' → 'S' → 1.0)
    return PGM_ENRICHMENT_BY_TYPE.get(s[0], 1.0)


print(f"OK  PGM enrichment table ready - "
      f"{len(PGM_ENRICHMENT_BY_TYPE)} non-baseline spectral types "
      f"(M / Xe = 2.0x, V = 0.2x, A / R / O = 0.5x, others 1.0x)")


# ─────────────────────────────────────────────────────────────────────────────
# JPL SBDB FETCHER  (primary source)
# ─────────────────────────────────────────────────────────────────────────────
JPL_SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"

# Physical + orbital fields available in the SBDB Query API.
# Note: 'density' is NOT in the SBDB query table; it only appears in the
# single-object SBDB detail endpoint.  For our pipeline density now arrives via
# SsODNet (measured) where available, otherwise enrich_composition() fills it
# from the taxonomy-based estimate.
_JPL_FIELDS = [
    "spkid",           # SPK kernel ID
    "pdes",            # primary provisional / numbered designation
    "name",            # name (if officially named)
    "neo",             # near-Earth object flag
    "pha",             # potentially hazardous flag
    "spec_B",          # Bus / Bus-DeMeo spectral classification
    "spec_T",          # Tholen spectral classification
    "diameter",        # effective diameter (km)
    "diameter_sigma",  # 1-σ uncertainty on diameter
    "albedo",          # geometric albedo
    "rot_per",         # rotation period (h)
    "e",               # eccentricity
    "a",               # semi-major axis (AU)
    "q",               # perihelion distance (AU)
    "ad",              # aphelion distance (AU)
    "i",               # inclination (deg)
    "om",              # longitude of ascending node (deg)
    "w",               # argument of perihelion (deg)
    "ma",              # mean anomaly at epoch (deg)
    # epoch, the osculating element epoch as a Julian date (TDB).  `ma` above
    # is "mean anomaly AT EPOCH" and was fetched for nine releases without it,
    # which made it unusable rather than merely unused: a mean anomaly fixes no
    # date without the epoch it is referred to.  Nothing downstream reads any
    # of om / w / ma today, so this changes no number; it is here so that the
    # next Stage 1 run captures it rather than requiring a second full refetch
    # the day somebody wants a real launch window.
    #
    # It must stay PER ROW.  Most bodies share a common epoch, but not all: a
    # 2,000-row NEO sample returned 1,999 at JD 2461200.5 and one at
    # JD 2455562.5, 5,638 days apart.  A hardcoded constant would be silently
    # wrong for exactly the minority most likely to matter.
    "epoch",

    # ── Orbit quality ────────────────────────────────────────────────────────
    # 🚨  THE RANKING IS DERIVED FROM ORBITAL ELEMENTS AND HAD NO IDEA WHICH
    # ELEMENTS WERE ANY GOOD.  `condition_code` is the MPC orbit-uncertainty
    # parameter U, 0 (well determined) to 9 (barely constrained).  Delta-v, and
    # therefore the entire economic ranking, is computed from a, e and i; a
    # body with U = 9 from a four-day arc has elements that are provisional.
    #
    # Measured 2026-09-03 against the profitability catalog on disk: of the top
    # 30 bodies by cost/revenue, 43.3% carry U >= 5 against 13.9% in the
    # population, a 3.1x enrichment at p = 8.3e-05, and the effect is strongest
    # at the very top of the ranking (Q1 35.9%, Q2 5.1%).  That is a winner's
    # curse: ranking on a quantity derived from noisy elements preferentially
    # selects the bodies whose errors happen to flatter them.
    #
    # These are FETCHED, not applied.  Filtering or down-weighting on them
    # changes what the model answers and is a modelling decision; this only
    # makes the information available to make it.  All seven are 100% populated.
    "condition_code",  # MPC orbit uncertainty U, 0 = well determined, 9 = barely
    "data_arc",        # days between first and last observation
    "n_obs_used",      # observations used in the orbit fit
    "rms",             # RMS residual of that fit, arcsec
    "moid",            # Earth minimum orbit intersection distance (AU)
    "class",           # orbit class code: MBA, APO, AMO, ATE, TNO, ...
    "soln_date",       # when the orbit solution was last updated
    "per",             # orbital period (yr)
    "n",               # mean motion (deg/day)
    # H, absolute magnitude.  Added in v1.1.0 and it is the single highest-
    # coverage physical field in the whole pipeline: 1,553,817 of JPL's
    # 1,554,321 asteroids carry one, against 139,582 with a diameter.  Every
    # other source already supplied `absolute_magnitude_h`, so the backbone was
    # the one place it was missing and derive_missing_diameters() needs it on
    # exactly the rows the other sources never reach.
    "H",
]

_JPL_RENAME = {
    "pdes":           "designation",
    # NB: `name` passes through verbatim; no entry needed since the source
    # column is already named `name` in the SBDB JSON response.
    "spec_B":         "spectral_type",          # Bus-DeMeo is preferred primary
    "spec_T":         "spectral_type_tholen",   # kept as secondary
    "diameter":       "diameter_km",
    "diameter_sigma": "diameter_sigma_km",
    # NB: `albedo` passes through verbatim (source name == target name).
    "rot_per":        "rotation_period_h",
    # density: not in SBDB Query API; sourced from SsODNet or estimated downstream
    "a":              "semi_major_axis_au",
    "e":              "eccentricity",
    "q":              "perihelion_au",
    "ad":             "aphelion_au",
    "i":              "inclination_deg",
    "om":             "longitude_asc_node_deg",
    "w":              "arg_perihelion_deg",
    "ma":             "mean_anomaly_deg",
    "epoch":          "element_epoch_jd",
    "condition_code": "orbit_condition_code",
    "data_arc":       "observation_arc_days",
    "n_obs_used":     "n_observations",
    "rms":            "orbit_fit_rms_arcsec",
    "moid":           "earth_moid_au",
    "class":          "orbit_class",
    "soln_date":      "orbit_solution_date",
    "per":            "orbital_period_yr",
    "n":              "mean_motion_deg_day",
    "H":              "absolute_magnitude_h",
    "neo":            "is_neo",
    "pha":            "is_pha",
    "spkid":          "spk_id",
}

_JPL_NUMERIC = [
    "diameter_km", "diameter_sigma_km", "albedo", "rotation_period_h",
    "semi_major_axis_au", "eccentricity", "perihelion_au",
    "aphelion_au", "inclination_deg", "longitude_asc_node_deg",
    "arg_perihelion_deg", "mean_anomaly_deg", "orbital_period_yr",
    "mean_motion_deg_day", "absolute_magnitude_h",
    # SBDB returns the epoch as a STRING ("2461200.5").  It must be coerced
    # here or it lands in the CSV as text, which is the float-typed-identifier
    # trap in the other direction: a number that never compares numerically.
    "element_epoch_jd",
    # Same for the orbit-quality numerics.  `orbit_class` and
    # `orbit_solution_date` are deliberately NOT here: one is a category code
    # and the other a date, and coercing either would silently null it.
    "orbit_condition_code", "observation_arc_days", "n_observations",
    "orbit_fit_rms_arcsec", "earth_moid_au",
]


def fetch_jpl_sbdb(config: CatalogConfig) -> pd.DataFrame:
    """
    Fetch asteroid physical + orbital data from NASA JPL SBDB Query API.

    Strategy:
      • Attempt 1: full field list (spec_B, spec_T, diameter, albedo, …)
      • Attempt 2, minimal safe fields (orbital only + diameter + albedo)
        used as fallback if any field name in attempt 1 is rejected.
    Returns EMPTY DataFrame on any unrecoverable error.
    """
    print("\n  JPL Small-Body Database  (ssd-api.jpl.nasa.gov) ...")

    # Minimal field set guaranteed to exist in every SBDB query response.
    # Used as fallback if the full list causes a 400.
    # `epoch` is carried here as well as in _JPL_FIELDS deliberately: `ma` is in
    # this list, and a mean anomaly without its epoch is unusable, so omitting
    # it from the fallback would reintroduce the exact defect the full list
    # fixes, on precisely the runs where the full list already failed.
    _SAFE_FIELDS = "pdes,name,spkid,neo,pha,diameter,diameter_sigma,albedo,rot_per,e,a,q,ad,i,om,w,ma,epoch,per,n,H,condition_code,data_arc,n_obs_used,rms,moid,class,soln_date"

    base_params = {
        "sb-kind":   "a",           # asteroids only
        "full-prec": "true",
        # NOTE: sb-cond removed, the '>' operator encoding caused HTTP 400.
        #       Filtering by diameter > 0 is handled in Python (validate_and_filter).
    }

    # `limit` is OMITTED entirely when the cap is 0.  SBDB has no server-side
    # maximum, it returns all 1,554,321 asteroids for ~435 MB in ~80 s, and
    # sending `limit=0` would be read as a literal zero-row request rather than
    # as "no limit".
    if config.jpl_limit:
        base_params["limit"] = config.jpl_limit
    else:
        print("     NOTE   No row cap - requesting the full SBDB asteroid table "
              "(~1.55 M rows, ~435 MB).  Set CATALOG_CONFIG.jpl_limit for a faster run.")

    attempts = [
        ("full fields",  {**base_params, "fields": ",".join(_JPL_FIELDS)}),
        ("safe fields",  {**base_params, "fields": _SAFE_FIELDS}),
    ]

    for attempt_name, params in attempts:
        try:
            # Stream the response so we can render a byte-progress bar; the
            # full-50k payload is several MB and otherwise feels like a hang.
            with requests.get(
                JPL_SBDB_URL,
                params=params,
                timeout=config.request_timeout,
                stream=True,
            ) as resp:

                # On 400 print the API error message so future issues are diagnosable
                if resp.status_code == 400:
                    try:
                        api_msg = resp.json().get("message", resp.text[:300])
                    except Exception:
                        api_msg = resp.text[:300]
                    print(f"     WARN  HTTP 400 on {attempt_name} - API says: {api_msg}")
                    continue   # try next attempt

                resp.raise_for_status()

                # Pull the body in chunks while updating a tqdm bar.  If the
                # server reports Content-Length we get a proper percentage;
                # otherwise total=None makes tqdm show an indeterminate bar
                # that still reports bytes-downloaded in real time.
                total_bytes = int(resp.headers.get("content-length") or 0) or None
                chunks: list = []
                with tqdm(
                    total=total_bytes,
                    desc=f"     JPL ({attempt_name})",
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    leave=True,
                    mininterval=0.3,
                ) as pbar:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            chunks.append(chunk)
                            pbar.update(len(chunk))
                body = b"".join(chunks)

            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                print(f"     FAIL  JSON decode failed on {attempt_name}: {exc}")
                continue

            if "data" not in payload or not payload["data"]:
                print(f"     WARN  No data on {attempt_name} - trying next")
                continue

            # SBDB Query API returns "fields" as a plain list of strings
            # e.g. ["pdes", "name", "a", ...] NOT [{"name": "pdes"}, ...]
            raw_fields = payload["fields"]
            field_names = [
                f["name"] if isinstance(f, dict) else str(f)
                for f in raw_fields
            ]
            df = pd.DataFrame(payload["data"], columns=field_names)

            # Rename to standard schema
            df = df.rename(columns={k: v for k, v in _JPL_RENAME.items() if k in df.columns})

            # Coerce numerics
            for col in _JPL_NUMERIC:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # Boolean flags
            for flag in ("is_neo", "is_pha"):
                if flag in df.columns:
                    df[flag] = df[flag].map({"Y": True, "N": False, True: True, False: False})

            df["source_jpl"] = True
            print(f"     OK  {len(df):,} records fetched from JPL SBDB ({attempt_name})")
            return df

        except requests.exceptions.Timeout:
            print(f"     FAIL  Timeout on {attempt_name}")
        except requests.exceptions.ConnectionError:
            print("     FAIL  Connection error - JPL SBDB skipped entirely")
            return pd.DataFrame()
        except requests.exceptions.HTTPError as exc:
            print(f"     FAIL  HTTP {exc.response.status_code} on {attempt_name}")
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            print(f"     FAIL  Parse error ({exc}) on {attempt_name}")
        except Exception as exc:
            print(f"     FAIL  Unexpected error ({exc}) on {attempt_name}")

    print("     FAIL  All JPL SBDB attempts failed - skipped")
    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# ADDITIONAL FETCHERS  (template - drop new fetcher functions in here)
# ─────────────────────────────────────────────────────────────────────────────
#
# Add a new catalog source by writing a fetcher with this signature:
#
#     def fetch_<source_name>(config: CatalogConfig) -> pd.DataFrame:
#         """One-line description of what the source provides."""
#         # 1. Hit the source's API / download endpoint
#         # 2. Parse the response into a DataFrame
#         # 3. Rename columns into the catalog's standard schema:
#         #       designation, name, diameter_km, albedo, density_gcm3,
#         #       semi_major_axis_au, eccentricity, inclination_deg, ...
#         # 4. Tag the rows so the source is recoverable downstream:
#         #       df["source_<name>"] = True
#         # 5. Return the DataFrame (or an empty one on any unrecoverable error)
#
# Then in build_asteroid_catalog() add ONE line:
#
#     sources["<Source>"] = fetch_<source_name>(config) if config.use_<name> else pd.DataFrame()
#
# merge_sources picks it up automatically: dedup, outer-join, NaN-fill all
# work uniformly across however many sources you add.
#
# Notes on choosing a source:
#   - It MUST contribute a `designation` column (numeric-string preferred,
#     e.g. "1" for Ceres) so the merge key is consistent with JPL SBDB.
#   - It SHOULD contribute both `semi_major_axis_au` and `diameter_km` -
#     without these the row will be dropped at validate_and_filter.
#     Physical-only catalogs (e.g. WISE NEATM, which lack orbital
#     elements) cannot stand alone; they need to be joined onto an
#     orbital source first.
#   - Return an empty DataFrame on any unrecoverable error rather than
#     raising; the pipeline handles missing sources gracefully.


# ─────────────────────────────────────────────────────────────────────────────
# SHARED: CANONICAL DESIGNATION
# ─────────────────────────────────────────────────────────────────────────────
# JPL's `pdes` field is the canonical identifier we merge on:
#   • Numbered asteroids → integer string, e.g. "1" (Ceres), "433" (Eros)
#   • Unnumbered         → provisional designation, e.g. "2024 BX1", "1999 KW4"
#
# Other sources spell the same identifier differently: VizieR uses
# "(1) Ceres", some catalogs render "1 Ceres", others zero-pad to "00001".
# This helper collapses every common surface form to the JPL form so the
# merge key is consistent across every source.
#
# CRITICAL CORRECTNESS NOTE
# A naive `^\d+` regex (which earlier versions of this pipeline used) is
# WRONG: for "2024 BX1" it extracts "2024", which would silently fail to
# match JPL's "2024 BX1" in the join AND would dedup-collapse every "2024 X*"
# provisional designation onto a single row.  This helper distinguishes
# numbered-with-name from provisional by checking what follows the digits.

def _extract_canonical_designation(s: pd.Series) -> pd.Series:
    """
    Normalise a Series of raw asteroid designations to JPL-pdes form.

    Surface form               -> Canonical
    --------------------------    ---------
    "1"                           "1"
    "00001"                       "1"             (lstrip zeros)
    "1 Ceres"                     "1"             (number + Title-Case name)
    "433 Eros"                    "433"
    "(1) Ceres"                   "1"             (paren-wrapped number)
    "2024 BX1"                    "2024 BX1"      (PROVISIONAL; KEEP WHOLE)
    "1999 KW4"                    "1999 KW4"
    "Ceres"                       "Ceres"         (bare name, kept as-is)
    "" / NaN / "None"             pd.NA

    Distinguishes numbered-with-name from provisional designations by the
    character class that follows the leading digits: a Title-Case name
    (capital + at least one lowercase) marks a numbered asteroid; ALL-CAPS
    letters that may include digits mark a provisional designation.
    """
    raw = s.astype(str).str.strip()

    # Pre-clean: "(N) Name" → "N Name"
    cleaned = raw.str.replace(
        r"^\s*\(\s*(\d+)\s*\)\s*", r"\1 ", regex=True
    )

    # Pre-clean: "3.0" → "3".  A float-typed identifier column stringified by
    # pandas is the single most likely way a caller hands us a broken key, and
    # it is silent, "3.0" is not null, so nothing downstream complains; it just
    # never joins.  That is exactly how NEOWISE contributed zero rows to every
    # large run before v1.1.0 (see fetch_neowise).  Only a trailing .0 (or .000)
    # is stripped, so a genuine identifier is never truncated.
    cleaned = cleaned.str.replace(r"^(\d+)\.0+$", r"\1", regex=True)

    # Case A: numbered asteroid with a name, extract the leading number.
    # The name part must start with a capital + lowercase letter, which is
    # what distinguishes "1 Ceres" from a provisional like "2024 BX1".
    numbered_with_name = cleaned.str.extract(
        r"^(\d+)\s+[A-Z][a-z]", expand=False
    )

    # Case B: pure number (with possible leading zeros and trailing whitespace).
    pure_number = cleaned.str.extract(r"^(\d+)\s*$", expand=False)

    # Combine: numbered_with_name wins, then pure_number, else keep cleaned.
    result = numbered_with_name
    result = result.where(result.notna(), pure_number)
    result = result.where(result.notna(), cleaned)

    # For purely numeric results, strip leading zeros ("00001" → "1").
    # Don't apply to provisional designations like "1999 KW4".
    is_numeric  = result.str.match(r"^\d+$", na=False)
    stripped_num = result.str.lstrip("0").replace({"": "0"})
    result      = result.where(~is_numeric, stripped_num)

    return result.replace(
        {"": pd.NA, "nan": pd.NA, "NaN": pd.NA, "None": pd.NA, "none": pd.NA}
    )


# ─────────────────────────────────────────────────────────────────────────────
# MP3C FETCHER  (Observatoire de la Côte d'Azur)
# ─────────────────────────────────────────────────────────────────────────────
# MP3C (Minor Planet Physical Properties Catalogue) exposes data via both a
# REST endpoint and an IVOA TAP service.  We try multiple URL shapes because
# the API has shifted between schema versions; the first response that yields
# rows wins.  Documented endpoints:
#   • https://mp3c.oca.eu/api/data?...
#   • https://mp3c.oca.eu/catalogue/Astorbphys?format=json
#   • TAP/ADQL: https://mp3c.oca.eu/tap/sync?REQUEST=doQuery&LANG=ADQL&...
#
# Note: this host may be unreachable from restricted-network runtimes (Colab
# has been observed to fail DNS resolution).  The fetcher returns an empty
# DataFrame gracefully in that case so the pipeline survives.

# MP3C's REST and TAP transports both require an explicit row count, so
# `mp3c_limit = 0` (unlimited) is expressed as a ceiling comfortably above the
# whole catalogue rather than as an absent clause.  MP3C tracks ~1.2 M bodies.
_MP3C_UNLIMITED_ROWS = 2_000_000

_MP3C_REST_ENDPOINTS = [
    "https://mp3c.oca.eu/api/data?format=json&limit={limit}",
    "https://mp3c.oca.eu/catalogue/Astorbphys?format=json&limit={limit}",
    "https://mp3c.oca.eu/catalogue/Astphys?format=json&limit={limit}",
]
# TAP endpoint accepts an ADQL query directly.  Four candidate table names are
# tried (schema-prefixed and bare forms of two known table names) because MP3C
# has changed schema naming between releases.
_MP3C_TAP_URL    = "https://mp3c.oca.eu/tap/sync"
_MP3C_TAP_TABLES = ("mp3c.astorbphys", "mp3c.astphys", "astorbphys", "astphys")

_MP3C_RENAME = {
    # designation (multiple alternatives; whichever exists in the response wins)
    "des":       "designation",
    "number":    "designation",
    "id":        "designation",
    "object":    "designation",
    # `name` passes through verbatim (source name == target name)
    # physical (`albedo` likewise passes through verbatim when present)
    "diameter":  "diameter_km",
    "diam":      "diameter_km",
    "d":         "diameter_km",
    "rho":       "density_gcm3",
    "density":   "density_gcm3",
    "pv":        "albedo",
    "h":         "absolute_magnitude_h",
    "rot_per":   "rotation_period_h",
    "period":    "rotation_period_h",
    # taxonomy
    "taxonomy":  "spectral_type",
    "tax":       "spectral_type",
    "class":     "spectral_type",
    # orbital
    "a":         "semi_major_axis_au",
    "sma":       "semi_major_axis_au",
    "e":         "eccentricity",
    "i":         "inclination_deg",
    "incl":      "inclination_deg",
}
_MP3C_NUMERIC = [
    "diameter_km", "density_gcm3", "albedo", "absolute_magnitude_h",
    "rotation_period_h", "semi_major_axis_au", "eccentricity",
    "inclination_deg",
]


def _mp3c_jsonish_to_df(payload) -> pd.DataFrame:
    """Coerce MP3C's various JSON envelopes into a single DataFrame."""
    if isinstance(payload, list):
        return pd.json_normalize(payload)
    if isinstance(payload, dict):
        for key in ("data", "results", "rows", "asteroids", "objects"):
            if key in payload and isinstance(payload[key], list):
                return pd.json_normalize(payload[key])
    return pd.DataFrame()


def fetch_mp3c(config: CatalogConfig) -> pd.DataFrame:
    """
    Fetch from MP3C.  Tries REST endpoints first, then TAP/ADQL.
    Returns EMPTY DataFrame if every approach fails.
    """
    print("\n  MP3C - Minor Planet Physical Properties Catalogue ...")

    # Both MP3C transports need a number in the query; neither has an
    # "everything" form, so an unlimited (0) config becomes a ceiling larger
    # than the catalogue rather than a missing clause.
    mp3c_rows = config.mp3c_limit or _MP3C_UNLIMITED_ROWS

    # ── Attempt 1: REST endpoints ────────────────────────────────────────────
    for endpoint_tpl in _MP3C_REST_ENDPOINTS:
        url = endpoint_tpl.format(limit=mp3c_rows)
        try:
            r = requests.get(url, timeout=config.request_timeout)
        except requests.exceptions.ConnectionError as exc:
            print(f"     WARN  REST unreachable ({str(exc)[:80]})")
            break  # if DNS fails for the host, no point trying other paths
        except requests.exceptions.Timeout:
            print(f"     WARN  REST timed out on {endpoint_tpl[:60]}...")
            continue
        except Exception as exc:
            print(f"     WARN  REST {type(exc).__name__}: {exc}")
            continue

        if r.status_code != 200 or not r.text.strip():
            continue

        try:
            df = _mp3c_jsonish_to_df(r.json())
        except Exception:
            continue
        if df is not None and not df.empty:
            return _normalise_mp3c_df(df, source_url=url)

    # ── Attempt 2: TAP / ADQL ────────────────────────────────────────────────
    for table in _MP3C_TAP_TABLES:
        adql = f"SELECT TOP {mp3c_rows} * FROM {table}"
        params = {
            "REQUEST": "doQuery",
            "LANG":    "ADQL",
            "FORMAT":  "json",
            "QUERY":   adql,
        }
        try:
            r = requests.get(_MP3C_TAP_URL, params=params,
                             timeout=config.request_timeout)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            print(f"     WARN  TAP unreachable for table '{table}' ({type(exc).__name__})")
            continue
        except Exception as exc:
            print(f"     WARN  TAP {type(exc).__name__}: {exc}")
            continue

        if r.status_code != 200 or not r.text.strip():
            continue

        try:
            df = _mp3c_jsonish_to_df(r.json())
        except Exception:
            continue
        if df is not None and not df.empty:
            return _normalise_mp3c_df(df, source_url=f"TAP:{table}")

    print("     NOTE  MP3C not reachable on any endpoint - continuing without it")
    return pd.DataFrame()


def _normalise_mp3c_df(df: pd.DataFrame, source_url: str) -> pd.DataFrame:
    """Lowercase column names, rename to standard schema, coerce numerics."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns={k: v for k, v in _MP3C_RENAME.items() if k in df.columns})

    # Normalise designation via the shared canonical extractor (correctly
    # preserves provisional designations like "2024 BX1").
    if "designation" in df.columns:
        df["designation"] = _extract_canonical_designation(df["designation"])

    for col in _MP3C_NUMERIC:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["source_mp3c"] = True
    print(f"     OK  {len(df):,} records fetched from MP3C  ({source_url[:80]})")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SsODNet ssoBFT FETCHER  (IMCCE, Solar-system Best-estimate Table)
# ─────────────────────────────────────────────────────────────────────────────
# SsODNet aggregates ~3,000 published catalogs into a single best-estimate
# table for ~1.2 M asteroids.  We pull the bulk Apache-Parquet file
# (~500 MB) ONCE per `cache_max_age_days` and read only the columns we need
# via pyarrow column projection so the in-memory footprint is small.
#
# Schema notes (parquet column names use dotted paths: 244 cols as of the
# 2026-08 release; verify against the cached file, not this comment):
#   Identity:  id, number, name
#   Physical:  diameter.value, diameter.error.{min,max}        (km)
#              albedo.value                                    (geometric)
#              mass.value                                      (kg)
#              density.value                                   (kg/m³ → we convert to g/cm³)
#              absolute_magnitude.H.value                      (mag)
#   Taxonomy:  taxonomy.class, taxonomy.complex
#   Orbital:   orbital_elements.{semi_major_axis,eccentricity,
#                inclination,periapsis_distance,apoapsis_distance,
#                node_longitude,periapsis_argument,mean_anomaly,
#                orbital_period}.value
#   Rotation:  spins.period.value: a LIST column (one row holds every ranked
#              solution); we take the first non-null element.
#
# ⚠️  THE IDENTITY COLUMNS WERE RENAMED (v1.0.9).  ssoBFT used to ship
# `sso_id` / `sso_number` / `sso_name`; it now ships `id` / `number` / `name`.
# Because the projection silently drops columns it cannot find, the fetcher
# went on returning 50,000 rows with NO merge key, and `merge_sources` then
# discarded the entire source with a one-line warning, for a ~500 MB download
# and every literature diameter, density and taxonomy in the catalog.  Six
# other columns drifted at the same time (perihelion → periapsis_distance,
# aphelion → apoapsis_distance, perihelion_argument → periapsis_argument,
# absolute_magnitude.value → absolute_magnitude.H.value, and the three ranked
# spin columns → one list column).
#
# The lesson: a projection that tolerates missing columns MUST still assert
# the ones it cannot work without.  `_SSODNET_REQUIRED` below does that, and
# the fetcher now fails loudly rather than returning an unmergeable frame.
#
# Documentation: https://ssp.imcce.fr/webservices/ssodnet/api/ssobft/
# Bulk file:     https://ssp.imcce.fr/data/ssoBFT-latest_Asteroid.parquet

_SSODNET_PARQUET_URL = "https://ssp.imcce.fr/data/ssoBFT-latest_Asteroid.parquet"
_SSODNET_CACHE_FILE  = "ssoBFT-latest_Asteroid.parquet"

# Columns we WANT.  Asked of pyarrow as a projection; any not present in the
# file's actual schema are silently dropped (handled below).
_SSODNET_WANTED = [
    "id", "number", "name",
    "diameter.value", "diameter.error.min", "diameter.error.max",
    "albedo.value",
    "mass.value",
    "density.value",
    "taxonomy.class", "taxonomy.complex",
    "orbital_elements.semi_major_axis.value",
    "orbital_elements.eccentricity.value",
    "orbital_elements.inclination.value",
    "orbital_elements.periapsis_distance.value",
    "orbital_elements.apoapsis_distance.value",
    "orbital_elements.node_longitude.value",
    "orbital_elements.periapsis_argument.value",
    "orbital_elements.mean_anomaly.value",
    "orbital_elements.orbital_period.value",
    "absolute_magnitude.H.value",
    # Spin / rotation: ssoBFT now stores every ranked solution for a body in
    # ONE list column rather than `spins.<1..5>.period.value` scalars.  The
    # fetcher takes the first non-null element (rank order is preserved).
    "spins.period.value",
]

# Without these three the frame cannot be merged; `merge_sources` keys on
# `designation`, which is built from `number` falling back to `name`.  Losing
# them silently is the failure documented above, so the fetcher treats their
# absence as fatal for this source rather than returning a useless frame.
_SSODNET_REQUIRED = ["number", "name"]

_SSODNET_RENAME = {
    # Identity:
    #   number  → numeric IAU number (e.g. 1 for Ceres).  Used as our merge
    #             key (designation).  Nullable, unnumbered bodies fall back
    #             to `name`.
    #   name    → human-readable name ("Ceres").
    #   id      → IMCCE's quaero-resolved canonical identifier; for numbered
    #             asteroids this is the name string, for unnumbered it's the
    #             provisional designation.  Kept as `ssodnet_id` so a user can
    #             round-trip back to the SsODNet REST API
    #             (ssp.imcce.fr/.../ssocard/<ssodnet_id>).
    # These were sso_number / sso_name / sso_id before the 2026-08 schema
    # change; see the ⚠️ note above before "fixing" them back.
    "number":                                          "designation",
    "name":                                            "name",
    "id":                                              "ssodnet_id",
    "diameter.value":                                  "diameter_km",
    "albedo.value":                                    "albedo",
    "mass.value":                                      "estimated_mass_kg",
    # density: SsODNet stores SI (kg/m³).  Convert to g/cm³ in the body of the
    # fetcher (rename here just standardises the column name).
    "density.value":                                   "density_gcm3",
    "taxonomy.class":                                  "spectral_type",
    "taxonomy.complex":                                "spectral_complex",
    "orbital_elements.semi_major_axis.value":          "semi_major_axis_au",
    "orbital_elements.eccentricity.value":             "eccentricity",
    "orbital_elements.inclination.value":              "inclination_deg",
    "orbital_elements.periapsis_distance.value":       "perihelion_au",
    "orbital_elements.apoapsis_distance.value":        "aphelion_au",
    "orbital_elements.node_longitude.value":           "longitude_asc_node_deg",
    "orbital_elements.periapsis_argument.value":       "arg_perihelion_deg",
    "orbital_elements.mean_anomaly.value":             "mean_anomaly_deg",
    "orbital_elements.orbital_period.value":           "orbital_period_yr",
    "absolute_magnitude.H.value":                      "absolute_magnitude_h",
    # spins.period.value handled separately below; the list is reduced to a
    # single `rotation_period_h` column.
}

_SSODNET_NUMERIC = [
    "diameter_km", "diameter_sigma_km", "albedo",
    "estimated_mass_kg", "density_gcm3",
    "semi_major_axis_au", "eccentricity", "inclination_deg",
    "perihelion_au", "aphelion_au", "longitude_asc_node_deg",
    "arg_perihelion_deg", "mean_anomaly_deg", "orbital_period_yr",
    "absolute_magnitude_h", "rotation_period_h",
]


def _ssodnet_cache_path(config: CatalogConfig) -> str:
    """Where the ~500 MB ssoBFT parquet is cached.

    Through `_resolve_cache_dir`, which defaults to the system temp directory
    rather than beside the CSVs, so a working copy on Google Drive does not
    round-trip half a gigabyte through Drive sync on every run.
    """
    return os.path.join(_resolve_cache_dir(config), _SSODNET_CACHE_FILE)


def _ssodnet_cache_is_fresh(path: str, max_age_days: float) -> bool:
    """Return True if a cached parquet exists and is < max_age_days old."""
    if not os.path.exists(path):
        return False
    age_days = (datetime.now().timestamp() - os.path.getmtime(path)) / 86400.0
    return age_days <= max_age_days


def _download_ssodnet_parquet(dest: str, config: CatalogConfig) -> bool:
    """Stream-download the ssoBFT parquet to `dest` with a tqdm progress bar."""
    try:
        with requests.get(
            _SSODNET_PARQUET_URL,
            timeout=config.request_timeout,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0) or None
            tmp = dest + ".part"
            with open(tmp, "wb") as fh, tqdm(
                total=total,
                desc="     SsODNet ssoBFT",
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                leave=True,
                mininterval=0.5,
            ) as pbar:
                for chunk in resp.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                    if chunk:
                        fh.write(chunk)
                        pbar.update(len(chunk))
            # Windows can briefly hold the freshly-closed file open via the
            # indexer or AV, retry the atomic rename a few times before giving up.
            import time
            for _ in range(8):
                try:
                    os.replace(tmp, dest)
                    break
                except PermissionError:
                    time.sleep(0.5)
            else:
                os.replace(tmp, dest)  # final attempt → raises if still locked
        return True
    except requests.exceptions.Timeout:
        print("     FAIL  SsODNet download timed out")
    except requests.exceptions.ConnectionError as exc:
        print(f"     FAIL  SsODNet unreachable ({str(exc)[:80]})")
    except requests.exceptions.HTTPError as exc:
        print(f"     FAIL  SsODNet HTTP {exc.response.status_code}")
    except Exception as exc:
        print(f"     FAIL  SsODNet download error: {type(exc).__name__}: {exc}")
    # Clean partial file on failure so a retry doesn't trip the freshness check
    try:
        os.remove(dest + ".part")
    except OSError:
        pass
    return False


def fetch_ssodnet(config: CatalogConfig) -> pd.DataFrame:
    """
    Fetch the SsODNet ssoBFT best-estimate table.

    The bulk parquet (~500 MB) is cached at
        {cache_dir}/ssoBFT-latest_Asteroid.parquet
    (system tmp by default; see _resolve_cache_dir) and refreshed only when
    older than config.cache_max_age_days.

    Returns EMPTY DataFrame on any unrecoverable error so the rest of the
    pipeline survives unaffected.
    """
    print("\n   SsODNet ssoBFT  (ssp.imcce.fr) ...")

    # pyarrow is required for column-projection parquet reads.  If somehow it
    # didn't install, fall back to pandas' built-in parquet engine, which is
    # usually pyarrow anyway but may be fastparquet on bare systems.
    try:
        import pyarrow.parquet as pq          # noqa: F401  (engine probe)
        engine = "pyarrow"
    except ImportError:
        print("     WARN  pyarrow not available - falling back to pandas default engine")
        engine = "auto"

    cache_path = _ssodnet_cache_path(config)
    if _ssodnet_cache_is_fresh(cache_path, config.cache_max_age_days):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache_path)) / 3600
        print(f"       Using cached parquet ({age_h:.1f} h old): {cache_path}")
    else:
        print(f"     v   Downloading bulk parquet from {_SSODNET_PARQUET_URL}")
        if not _download_ssodnet_parquet(cache_path, config):
            return pd.DataFrame()

    # Read only the columns that actually exist in the schema (the schema does
    # drift between SsODNet releases).
    try:
        if engine == "pyarrow":
            import pyarrow.parquet as pq
            pf = pq.ParquetFile(cache_path)
            # schema_arrow, NOT schema.  The parquet PHYSICAL schema flattens a
            # list column into its inner path, so `spins.period.value` is absent
            # from pf.schema.names while present in pf.schema_arrow.names, and
            # read(columns=…) expects the arrow-level name.  Testing membership
            # against the physical schema silently drops every nested column.
            schema_names = set(pf.schema_arrow.names)
            cols = [c for c in _SSODNET_WANTED if c in schema_names]
            missing = [c for c in _SSODNET_WANTED if c not in schema_names]
            if missing:
                # SsODNet renames flattened columns between releases, so a few
                # misses are normal and tolerable.  Say which, at every scale, 
                # the old code only spoke up when fewer than 5 columns matched,
                # which is exactly why a release that renamed the IDENTITY
                # columns (and 6 others) passed for healthy: 14 still matched.
                print(f"     NOTE   Schema drift: {len(cols)}/{len(_SSODNET_WANTED)} "
                      f"columns matched, missing {missing}")
            absent_required = [c for c in _SSODNET_REQUIRED if c not in schema_names]
            if absent_required:
                print(f"     FAIL  ssoBFT schema is missing the merge key(s) "
                      f"{absent_required} - cannot build `designation`, so every "
                      f"row would be dropped at merge time.  Skipping SsODNet.")
                print(f"         Inspect the real schema and update "
                      f"_SSODNET_WANTED / _SSODNET_RENAME:")
                print(f"         {_PY} -c \"import pyarrow.parquet as pq; "
                      f"print(pq.ParquetFile(r'{cache_path}').schema_arrow.names)\"")
                return pd.DataFrame()
            df = pf.read(columns=cols).to_pandas()
        else:
            df = pd.read_parquet(cache_path)
            absent_required = [c for c in _SSODNET_REQUIRED if c not in df.columns]
            if absent_required:
                print(f"     FAIL  ssoBFT schema is missing the merge key(s) "
                      f"{absent_required} - skipping SsODNet.")
                return pd.DataFrame()
            df = df[[c for c in _SSODNET_WANTED if c in df.columns]]
    except Exception as exc:
        print(f"     FAIL  Parquet read failed: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    if df.empty:
        print("     WARN  Parquet returned 0 rows")
        return pd.DataFrame()

    # Cap to config.jpl_limit so SsODNet doesn't dominate runtime on small runs.
    # NB: full table is ~1.2 M rows; trimming here keeps merge / dedup fast.
    # IMPORTANT: sort by `number` ASC first so a small-N run gets the LOWEST
    # IAU numbers (Ceres=1, Pallas=2, Juno=3, Vesta=4, …), the most famous
    # bodies, rather than whatever arbitrary order the parquet stores rows in.
    # Unnumbered bodies (number = NaN) are sorted to the end via na_position.
    #
    # This silently stopped working when the column was renamed from
    # `sso_number`: the guard skipped the sort, and the run took an arbitrary
    # 50,000 rows starting around asteroid 367488 instead of Ceres.  The sort
    # key is required now, so the guard cannot silently no-op again.
    if config.ssodnet_limit and len(df) > config.ssodnet_limit:
        df = df.sort_values("number", ascending=True, na_position="last")
        df = df.head(config.ssodnet_limit).copy()
        print(f"        Truncated to first {config.ssodnet_limit:,} rows by number ASC")

    # Reduce the ranked spin solutions to a single rotation_period_h column.
    # ssoBFT used to expose them as `spins.<1..3>.period.value` scalars and now
    # ships ONE list column holding every solution for the body, best rank
    # first.  Take the first non-null element; same "best rank wins, lower
    # ranks fill the gap" behaviour as before, expressed over a list.
    if "spins.period.value" in df.columns:
        def _first_period(v) -> float:
            """Best-ranked rotation period from one body's spin-solution list.

            ssoBFT ships the solutions best-rank-first, so the first non-null
            positive element is the answer, which reproduces the old
            "best rank wins, lower ranks fill the gap" behaviour over a list.
            The `TypeError` arm catches a scalar arriving through a future
            schema change rather than assuming the column stays a list.
            """
            # pyarrow hands back None for absent lists and np.ndarray otherwise.
            if v is None:
                return np.nan
            try:
                for x in v:
                    if x is not None and not pd.isna(x) and float(x) > 0:
                        return float(x)
            except TypeError:          # scalar sneaking through a schema change
                return float(v) if pd.notna(v) else np.nan
            return np.nan

        df["rotation_period_h"] = df["spins.period.value"].apply(_first_period)
        df = df.drop(columns=["spins.period.value"])

    # Derive diameter_sigma_km from the asymmetric (min, max) error pair before
    # we drop the dotted columns.  Average is a reasonable scalar uncertainty.
    if {"diameter.error.min", "diameter.error.max"}.issubset(df.columns):
        sig = (df["diameter.error.min"].astype("float64").abs()
               + df["diameter.error.max"].astype("float64").abs()) / 2.0
        df["diameter_sigma_km"] = sig
        df = df.drop(columns=["diameter.error.min", "diameter.error.max"])

    df = df.rename(columns={k: v for k, v in _SSODNET_RENAME.items() if k in df.columns})

    # Designation: prefer `number` (numbered → "1"), fall back to `name`
    # (provisional designations / unnumbered).
    # IMPORTANT: `number` is int64 in the parquet but pandas casts to float64
    # whenever NaN is present (unnumbered bodies), which would stringify "1" as
    # "1.0".  Cast to the nullable Int64 dtype first so the str() round-trip
    # gives us the bare integer form JPL uses.
    if "designation" in df.columns:
        try:
            df["designation"] = df["designation"].astype("Int64").astype("string")
        except (TypeError, ValueError):
            df["designation"] = df["designation"].astype("string")
        # Fill unnumbered rows from sso_name
        if "name" in df.columns:
            df["designation"] = df["designation"].where(
                df["designation"].notna() & (df["designation"].astype("string") != "<NA>"),
                df["name"].astype("string"),
            )
    elif "name" in df.columns:
        df["designation"] = df["name"]

    if "designation" in df.columns:
        df["designation"] = _extract_canonical_designation(df["designation"])

    # SsODNet density is in kg/m³, convert to g/cm³ to match the pipeline schema.
    if "density_gcm3" in df.columns:
        df["density_gcm3"] = pd.to_numeric(df["density_gcm3"], errors="coerce") / 1000.0

    # Coerce all numerics
    for col in _SSODNET_NUMERIC:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # If aphelion / perihelion are missing but a & e are present, derive them, 
    # cheap and helps with validator coverage.
    if {"semi_major_axis_au", "eccentricity"}.issubset(df.columns):
        if "perihelion_au" not in df.columns or df["perihelion_au"].isna().all():
            df["perihelion_au"] = df["semi_major_axis_au"] * (1 - df["eccentricity"])
        if "aphelion_au" not in df.columns or df["aphelion_au"].isna().all():
            df["aphelion_au"] = df["semi_major_axis_au"] * (1 + df["eccentricity"])

    df["source_ssodnet"] = True
    print(f"     OK  {len(df):,} records ingested from SsODNet ssoBFT "
          f"({len(df.columns)} columns)")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# NEOWISE V2.0 FETCHER  (IRSA TAP, neowisesbpropv2)
# ─────────────────────────────────────────────────────────────────────────────
# NEOWISE Diameters & Albedos V2.0 is a PSI/NEOWISE-team compilation of
# infrared-measured diameters, V/NIR albedos, and beaming parameters for
# ~150 k Solar-system small bodies.  We pull it via IPAC IRSA's TAP service.
#
# Documentation:
#   https://sbn.psi.edu/pds/resource/doi/neowise_2.0.html
#   https://irsa.ipac.caltech.edu/data/WISE/NEOWISE_SB/gator_docs/
#                                       neowisesbprop_colDescriptions.html
# TAP table: neowisesbpropv2
#
# Confirmed schema (CSV column names, lower-case):
#   asteroid_number, prov_desig, comet_desig, mpc_packed_name,
#   absolute_mag, slope_param, mean_jd, n_w1..n_w4, fit_code,
#   diameter, diameter_err, v_albedo, v_albedo_err,
#   ir_albedo, ir_albedo_err, beaming_param, beaming_param_err,
#   stacked_flag, reference, notes, reference2, type, cntr

_NEOWISE_TAP_URL    = "https://irsa.ipac.caltech.edu/TAP/sync"
# IVOA UWS async endpoint.  A synchronous TAP query holds ONE connection open
# for the server-side query AND the whole ~19 MB transfer, so any proxy timeout
# in that window discards the entire result with no retry surface.  That is the
# `502 Proxy Error` that made NEOWISE contribute 0 rows to the run behind the
# committed cislunar 2x2.  Async splits the three phases: the job runs
# server-side with nothing held open, and the result sits at a stable URL that
# can be re-fetched.  Same ADQL, same rows, verified byte-identical.
_NEOWISE_TAP_ASYNC  = "https://irsa.ipac.caltech.edu/TAP/async"
_NEOWISE_TAP_TABLE  = "neowisesbpropv2"

# Terminal UWS phases.  Anything else means the job is still running.
_UWS_TERMINAL = ("COMPLETED", "ERROR", "ABORTED")

_NEOWISE_SELECT = (
    "asteroid_number, prov_desig, absolute_mag, "
    "diameter, diameter_err, "
    "v_albedo, v_albedo_err, ir_albedo, ir_albedo_err, "
    "beaming_param, beaming_param_err, stacked_flag, "
    "fit_code, reference, type"
)

_NEOWISE_RENAME = {
    "diameter":          "diameter_km",
    "diameter_err":      "diameter_sigma_km",
    "v_albedo":          "albedo",
    "v_albedo_err":      "albedo_sigma",
    "ir_albedo":         "albedo_ir",
    "ir_albedo_err":     "albedo_ir_sigma",
    "beaming_param":     "neowise_beaming_param",
    "beaming_param_err": "neowise_beaming_param_sigma",
    "stacked_flag":      "neowise_stacked",
    "absolute_mag":      "absolute_magnitude_h",
    "fit_code":          "neowise_fit_code",   # e.g. "DVB-" = diameter+V-albedo+beaming
    "reference":         "neowise_reference",
    "type":              "neowise_orbit_class",
}

_NEOWISE_NUMERIC = [
    "diameter_km", "diameter_sigma_km", "albedo", "albedo_sigma",
    "albedo_ir", "albedo_ir_sigma", "neowise_beaming_param",
    "neowise_beaming_param_sigma", "absolute_magnitude_h",
]


def _neowise_fetch_async(params: dict, config: CatalogConfig) -> Optional[bytes]:
    """Run the NEOWISE query as an IVOA UWS async job; return the body or None.

    Three phases, and the point of all of them is that nothing is held open
    while the server works:

      1. POST the query to /async.  IRSA answers 303 with a job URL in the
         Location header.  Redirects are NOT followed, because following one
         fetches the job's description page instead of leaving us the URL we
         need to drive its phase endpoints.
      2. POST PHASE=RUN, then poll until a terminal phase.  A poll that raises
         is deliberately NOT fatal: the job is still running server-side, and
         surviving a transient failure here is the entire reason for using
         async rather than sync.
      3. GET the result.  This URL is stable, so a failed transfer is
         retryable in a way a synchronous query's is not.

    Returns None on any failure, which puts the caller back on the sync path.
    """
    try:
        session = requests.Session()
        resp = session.post(
            _NEOWISE_TAP_ASYNC, data=params,
            allow_redirects=False, timeout=config.request_timeout,
        )
        if resp.status_code not in (200, 302, 303):
            print(f"     WARN  async submit returned HTTP {resp.status_code}")
            return None
        job = resp.headers.get("Location")
        if not job:
            print("     WARN  async submit returned no job URL")
            return None
        print(f"     job   {job}")

        session.post(f"{job}/phase", data={"PHASE": "RUN"},
                     timeout=config.request_timeout)

        waited, phase = 0.0, "UNKNOWN"
        while waited < float(config.neowise_async_max_wait_s):
            try:
                phase = session.get(
                    f"{job}/phase", timeout=config.request_timeout,
                ).text.strip()
            except requests.exceptions.RequestException:
                phase = "UNKNOWN"          # keep waiting; the job is server-side
            if phase in _UWS_TERMINAL:
                break
            _time.sleep(2.0)
            waited += 2.0

        if phase != "COMPLETED":
            print(f"     WARN  async job ended in phase {phase}")
            return None

        for attempt in (1, 2, 3):
            try:
                res = session.get(f"{job}/results/result",
                                  timeout=config.request_timeout)
                if res.status_code == 200:
                    return res.content
                print(f"     WARN  result HTTP {res.status_code} "
                      f"(attempt {attempt})")
            except requests.exceptions.RequestException as exc:
                print(f"     WARN  result attempt {attempt}: {type(exc).__name__}")
            _time.sleep(2.0 * attempt)
        return None

    except requests.exceptions.RequestException as exc:
        print(f"     WARN  async TAP unavailable ({type(exc).__name__})")
        return None


def fetch_neowise(config: CatalogConfig) -> pd.DataFrame:
    """
    Fetch NEOWISE V2.0 diameters & albedos via IPAC IRSA's TAP service.

    NEOWISE is a PHYSICAL-only catalog, no orbital elements, so it can't
    stand alone.  Once merged it upgrades diameter / albedo for the ~150k
    rows where it overlaps the JPL backbone.

    Tries the async (UWS) endpoint first and falls back to the synchronous one,
    so the worst case is the behaviour this function had before async existed.
    Both paths return the same bytes for the same ADQL; only their failure
    surfaces differ.  See `_neowise_fetch_async`.

    Returns EMPTY DataFrame on any unrecoverable error.
    """
    print("\n   NEOWISE V2.0 diameters & albedos  (IRSA TAP) ...")

    # ADQL.  `neowise_limit` caps the pull; 0 drops the TOP clause and takes the
    # whole table, which is only ~183 k rows / ~19 MB / ~30 s, small enough
    # that capping it buys almost nothing and costs measured diameters.
    # WHERE clause filters comets server-side and skips rows without ANY
    # identifier, saves bandwidth and avoids a useless dedup pass later.
    # ORDER BY asteroid_number so small-N runs include the low-numbered
    # (most famous) bodies: Ceres, Vesta, etc.
    top = f"TOP {int(config.neowise_limit)} " if config.neowise_limit else ""
    # 🚨  THE ORDER BY MUST BE TOTAL, AND `asteroid_number` ALONE IS NOT.
    #
    # NEOWISE carries 183,408 rows for 143,318 bodies, and 27,864 bodies have
    # more than one.  `deduplicate_catalog` sorts by completeness with
    # `kind="stable"` and keeps the first, so among rows of EQUAL completeness
    # the winner is decided by nothing but the order they arrived in.
    #
    # 27,802 bodies are in exactly that state with DIFFERENT diameters:
    # median spread 11.6%, p90 27.4%, max 86.3%.  Diameter cubes into
    # `estimated_mass_kg`, which is what the whole ranking runs on, so an 11.6%
    # diameter is a 39% mass.
    #
    # Ordering on `asteroid_number` alone leaves those ties for the server to
    # break however it plans the query, and it does not break them the same way
    # twice: a sync and an async pull of the identical ADQL returned the same
    # 183,408 rows with the same content hash in a DIFFERENT order.  So this
    # was never reproducible, and the async path only made it visible.
    #
    # Ordering on enough columns to be total makes the same rows win on every
    # run and every transport.  It deliberately does NOT try to pick the
    # physically best measurement; `fit_code` and `stacked_flag` are the fields
    # that would express that, and choosing among them is a modelling decision,
    # not a reproducibility fix.
    adql = (
        f"SELECT {top}{_NEOWISE_SELECT} "
        f"FROM {_NEOWISE_TAP_TABLE} "
        f"WHERE type != 'comet' "
        f"  AND (asteroid_number IS NOT NULL OR prov_desig IS NOT NULL) "
        f"ORDER BY asteroid_number ASC, prov_desig ASC, diameter ASC, "
        f"diameter_err ASC, v_albedo ASC, ir_albedo ASC, "
        f"beaming_param ASC, fit_code ASC, reference ASC"
    )
    params = {
        "REQUEST": "doQuery",
        "LANG":    "ADQL",
        "FORMAT":  "csv",
        "QUERY":   adql,
    }

    # Async first.  On success the sync block below is skipped; on any failure
    # `body` stays None and the original synchronous path runs unchanged, so
    # this can only add a way to succeed, never remove one.
    body = None
    if config.neowise_use_async:
        body = _neowise_fetch_async(params, config)
        if body is not None:
            print(f"     OK  async TAP returned {len(body):,} bytes")
        else:
            print("     NOTE  falling back to synchronous TAP")

    try:
        if body is None:
            with requests.get(
                _NEOWISE_TAP_URL,
                params=params,
                timeout=config.request_timeout,
                stream=True,
            ) as resp:
                if resp.status_code != 200:
                    snippet = resp.text[:300].replace("\n", " ")
                    print(f"     FAIL  HTTP {resp.status_code} - {snippet}")
                    return pd.DataFrame()

                total_bytes = int(resp.headers.get("content-length") or 0) or None
                chunks: list = []
                with tqdm(
                    total=total_bytes,
                    desc="     NEOWISE",
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    leave=True,
                    mininterval=0.3,
                ) as pbar:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            chunks.append(chunk)
                            pbar.update(len(chunk))
                body = b"".join(chunks)

    except requests.exceptions.Timeout:
        print("     FAIL  NEOWISE TAP timed out")
        return pd.DataFrame()
    except requests.exceptions.ConnectionError as exc:
        print(f"     FAIL  NEOWISE TAP unreachable ({str(exc)[:80]})")
        return pd.DataFrame()
    except Exception as exc:
        print(f"     FAIL  NEOWISE TAP error: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    # IRSA may return one of several non-CSV bodies on failure:
    #   • VOTable error envelope (XML) on a bad ADQL
    #   • HTML 200-with-error-page on a backend hiccup
    #   • empty body
    # Detect each of these explicitly so we don't try to coerce HTML/XML into
    # a DataFrame and end up with garbage rows.
    head = body[:400].lstrip()
    if not head:
        print("     FAIL  TAP returned an empty body")
        return pd.DataFrame()
    if head.startswith(b"<?xml") or head.startswith(b"<VOTABLE"):
        snippet = body[:400].decode("utf-8", errors="replace").replace("\n", " ")
        print(f"     FAIL  TAP returned a VOTable error envelope: {snippet[:200]}")
        return pd.DataFrame()
    if head[:1] == b"<":   # any other tag-leading body (HTML, etc.)
        snippet = body[:400].decode("utf-8", errors="replace").replace("\n", " ")
        print(f"     FAIL  TAP returned a non-CSV body: {snippet[:200]}")
        return pd.DataFrame()
    if not head.lower().startswith(b"asteroid_number"):
        # Expected CSV header from this query begins with `asteroid_number`.
        # Anything else means the schema or query has drifted, fail loud.
        snippet = body[:400].decode("utf-8", errors="replace").replace("\n", " ")
        print(f"     FAIL  TAP body doesn't look like expected CSV: {snippet[:200]}")
        return pd.DataFrame()

    from io import BytesIO
    try:
        df = pd.read_csv(BytesIO(body))
    except Exception as exc:
        print(f"     FAIL  CSV parse failed: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    if df.empty:
        print("     WARN  NEOWISE TAP returned 0 rows")
        return pd.DataFrame()

    # Designation: numbered → `asteroid_number`, unnumbered → `prov_desig`.
    #
    # ⚠️  `asteroid_number` MUST be rendered as an integer, and this is not a
    # cosmetic point; it is the bug that made this entire source a no-op for
    # every large run up to v1.1.0.
    #
    # IRSA types the column by what the result slice happens to contain.  A
    # slice with no unnumbered bodies comes back int64 and `.astype("string")`
    # gives "3"; add one row whose asteroid_number is null and the column is
    # float64, so the same call gives "3.0".  The canonical extractor matches
    # neither `^(\d+)\s*$` nor `^(\d+)\s+[A-Z][a-z]` against "3.0", passes it
    # through unchanged, and the merge key can never equal JPL's "3".  Every
    # NEOWISE row then reached validate_and_filter as a body nothing else had
    # heard of, and was dropped for having no semi-major axis.
    #
    # So it worked at small caps and failed at large ones, which is the worst
    # possible shape: the fetcher still printed its ✅ and its row count, and
    # the only visible trace was neowise_* columns sitting 100% empty in the
    # output CSV.  _extract_canonical_designation strips a trailing ".0"
    # defensively now as well, but do not rely on that and remove this.
    def _as_designation(numbers: pd.Series, prov: Optional[pd.Series]) -> pd.Series:
        """IRSA's asteroid_number as a merge key, or the provisional designation.

        Through `Int64` and only then to string, which is the whole point: IRSA
        types the column float64 whenever the slice holds any unnumbered body,
        and `.astype("string")` on that yields `"3.0"`, which matches no JPL
        `pdes` and is not null either. That cost NEOWISE four releases of
        contributing zero rows. See the block above.
        """
        out = pd.Series(pd.NA, index=numbers.index, dtype="string")
        num = pd.to_numeric(numbers, errors="coerce")
        has_num = num.notna()
        # Int64 first, so 3.0 renders as "3" and not "3.0".
        out[has_num] = num[has_num].astype("Int64").astype("string")
        if prov is not None:
            fallback = prov.astype("string").str.strip()
            out[~has_num] = fallback[~has_num]
        return out.replace({"": pd.NA, "<NA>": pd.NA, "nan": pd.NA})

    if "asteroid_number" in df.columns:
        df["designation"] = _as_designation(
            df["asteroid_number"],
            df["prov_desig"] if "prov_desig" in df.columns else None,
        )
    elif "prov_desig" in df.columns:
        df["designation"] = df["prov_desig"].astype("string").str.strip()

    # Drop the source-identifier columns so the rename + merge stay tidy
    df = df.drop(columns=[c for c in ("asteroid_number", "prov_desig") if c in df.columns])

    # Standard rename + numeric coercion
    df = df.rename(columns={k: v for k, v in _NEOWISE_RENAME.items() if k in df.columns})
    for col in _NEOWISE_NUMERIC:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Coerce the stacked-measurement flag to True/False/NaN to match the
    # boolean convention used by `is_neo`, `is_pha`, `density_measured`, …
    # NEOWISE encodes it as "Y" for stacked measurements and blank otherwise.
    if "neowise_stacked" in df.columns:
        df["neowise_stacked"] = (
            df["neowise_stacked"].astype("string").str.strip().str.upper()
              .map({"Y": True, "N": False, "1": True, "0": False, "": False})
        )

    # Canonicalise designation to JPL-pdes form
    if "designation" in df.columns:
        df["designation"] = _extract_canonical_designation(df["designation"])

    df["source_neowise"] = True
    print(f"     OK  {len(df):,} records fetched from NEOWISE V2.0")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────
def _normalise_designation_key(s: pd.Series) -> pd.Series:
    """
    Normalisation used ONLY for duplicate detection.

    Defers to the shared canonical extractor for the actual designation work
    (collapsing "(1) Ceres", "1 Ceres", "00001" all to "1"; preserving
    "2024 BX1" intact so distinct provisional designations stay distinct),
    then uppercases the result so case variation can't fragment groups.

    This is the SAME logic the fetchers run when they produce `designation`,
    so a designation produced by the JPL pdes field and one produced from
    another catalog's variant form are guaranteed to compare equal as dedup keys.
    """
    return _extract_canonical_designation(s).str.upper().str.strip()


def deduplicate_catalog(
    df: pd.DataFrame,
    key: str = "designation",
    label: str = "catalog",
) -> pd.DataFrame:
    """
    Remove duplicate rows by normalised `key`, keeping the row with the most
    populated columns within each group (i.e. the most-complete record wins,
    not arbitrarily the first one).  Reports counts so the caller can see what
    was collapsed.  Idempotent, safe to call multiple times in the pipeline.

    Used in three places:
      1. inside merge_sources, per source, BEFORE the join, defends against
         source-internal duplicates (e.g. a future catalog returning the same
         asteroid under both numeric and named designations)
      2. inside merge_sources, AFTER the join, catches duplicates introduced
         by designation variants between sources
      3. inside build_asteroid_catalog, AFTER enrichment, final safety net before save
    """
    if df.empty or key not in df.columns:
        return df

    n_before = len(df)

    work = df.copy()
    work["_dedup_key"]    = _normalise_designation_key(work[key])
    work["_completeness"] = work.notna().sum(axis=1)

    # Drop rows whose normalised key is null; they can't be safely grouped.
    null_key = work["_dedup_key"].isna()
    n_null   = int(null_key.sum())
    work     = work[~null_key]

    # Sort by completeness so drop_duplicates(keep='first') keeps the best row.
    work = work.sort_values("_completeness", ascending=False, kind="stable")
    work = work.drop_duplicates(subset=["_dedup_key"], keep="first")
    work = work.drop(columns=["_dedup_key", "_completeness"]).reset_index(drop=True)

    n_removed = n_before - len(work) - n_null

    if n_removed > 0 or n_null > 0:
        msg = []
        if n_removed > 0:
            msg.append(f"{n_removed:,} duplicate(s) collapsed (kept most-complete row)")
        if n_null > 0:
            msg.append(f"{n_null:,} row(s) dropped for null designation")
        print(f"        {label}: " + "; ".join(msg))
    else:
        print(f"     OK   {label}: no duplicates detected")

    return work


# ─────────────────────────────────────────────────────────────────────────────
# DATA MERGER
# ─────────────────────────────────────────────────────────────────────────────
#
# Designed to scale to N sources.  Adding a new catalog later is:
#   1. write fetch_<name>(config) returning a DataFrame keyed on 'designation'
#   2. add a matching `use_<name>: bool = True` toggle to CatalogConfig
#   3. inside build_asteroid_catalog(), populate `sources["<Name>"] = fetch_<name>(...)
#                                          if config.use_<name> else pd.DataFrame()`
# merge_sources / dedup / validation pick the new source up automatically.
#
# The first non-empty source in the dict becomes the BACKBONE; remaining sources
# are merged in with an OUTER join so designations unique to any source are
# retained.  Where a designation appears in multiple sources the backbone's
# value wins and the others fill gaps (never overwrite).
def merge_sources(sources: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Merge an arbitrary set of source DataFrames into a single catalog.

    Args:
        sources: ordered mapping of `source_name -> DataFrame`.  The first
                 non-empty entry is treated as the backbone; the rest are
                 outer-joined supplements that fill gaps.  Each DataFrame is
                 expected to have a 'designation' column.

    Returns:
        Merged + deduplicated DataFrame, or an empty DataFrame if every
        source was empty.
    """
    print("\n  Merging sources ...")

    available = {k: v for k, v in sources.items() if v is not None and not v.empty}

    if not available:
        print("     FAIL  No data from any source - aborting merge")
        return pd.DataFrame()

    # Normalise designation for joining, then dedupe each source on its own
    # (defends against duplicates introduced upstream in any fetcher).
    # Use the shared canonical extractor, it's idempotent so re-running on
    # an already-canonical fetcher output is a no-op, and crucially it returns
    # proper pd.NA for missing values (a naïve .astype(str).str.upper() would
    # turn pd.NA into the literal string "<NA>" and create a ghost dedup key).
    for name, df in available.items():
        n_raw = len(df)
        if "designation" in df.columns:
            df["designation"] = _extract_canonical_designation(df["designation"])
        available[name] = deduplicate_catalog(df, key="designation", label=name)
        # A source that arrives with rows and leaves with none has a broken
        # merge key, not an empty table, and that distinction is invisible in
        # the output: the columns still appear, filled entirely with NaN, and
        # the fetcher has already printed its success line.  NEOWISE did this
        # on every large run up to v1.1.0.  Fail loud.
        if n_raw and available[name].empty:
            print(f"     ALERT  {name} fetched {n_raw:,} rows and NONE survived "
                  f"keying - its `designation` column is unusable, so the whole "
                  f"source is about to contribute nothing.  This is a BUG in "
                  f"fetch_{name.split()[0].lower()}, not an empty upstream table.")

    # First non-empty source becomes the backbone, caller controls precedence
    # via the dict insertion order.
    backbone_name, backbone_df = next(iter(available.items()))
    merged = backbone_df.copy()
    available.pop(backbone_name)
    print(f"       Backbone: {backbone_name}  ({len(merged):,} rows)")

    # Outer-join each remaining source so designations unique to that source
    # are retained.  Backbone values win; supplement values fill NaN gaps.
    for src_name, supp in available.items():
        if "designation" not in supp.columns:
            print(f"     WARN  {src_name} has no 'designation' column - skipped in merge")
            continue

        # Pass every column through, INCLUDING `source_*` flags.  Every
        # fetcher tags itself with a uniquely-named flag (source_jpl,
        # source_ssodnet, source_neowise, source_mp3c)
        # so there's no collision risk; preserving them gives each row a
        # full provenance footprint after the merge.
        fill_cols = [c for c in supp.columns if c != "designation"]

        # Rename supp columns to avoid clobbering backbone
        supp_renamed = supp[["designation"] + fill_cols].copy()
        supp_renamed.columns = (
            ["designation"] + [f"_{c}__{src_name.lower()}" for c in fill_cols]
        )

        before_merge = len(merged)
        # How many of this source's keys the backbone already knows.  Reported
        # because it is the one number that separates "the source is fine and
        # simply overlaps" from "the source's keys join nothing"; a supplement
        # whose overlap is 0 has almost certainly built its designation wrongly,
        # and an outer join hides that by quietly adding every row as new.
        overlap = int(supp["designation"].isin(merged["designation"]).sum())
        merged = merged.merge(supp_renamed, on="designation", how="outer")
        new_rows = len(merged) - before_merge

        for col in fill_cols:
            src_col = f"_{col}__{src_name.lower()}"
            if src_col not in merged.columns:
                continue
            if col in merged.columns:
                merged[col] = merged[col].fillna(merged[src_col])
            else:
                merged.rename(columns={src_col: col}, inplace=True)
                continue
            merged.drop(columns=[src_col], inplace=True)

        print(f"     OK   Merged {src_name}: {len(supp):,} supplement records "
              f"({overlap:,} matched the backbone, +{new_rows:,} new entries)")
        if len(supp) and not overlap:
            print(f"     ALERT  {src_name} matched ZERO backbone designations. "
                  f"Every one of its {len(supp):,} rows entered as a new body "
                  f"with no orbital elements, and validation will drop them "
                  f"all.  Check how fetch_* builds `designation` - a float-typed "
                  f"identifier stringifies to \"3.0\" and joins nothing.")

    # Final post-merge dedup, keeps the most-complete row in each group.
    merged = deduplicate_catalog(merged, key="designation", label="post-merge")

    print(f"     OK  Combined catalog: {len(merged):,} rows x {len(merged.columns)} columns")
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# DERIVED DIAMETERS  (v1.1.0)
# ─────────────────────────────────────────────────────────────────────────────
#
# validate_and_filter drops any body with no diameter, and that single rule is
# what has bounded this pipeline's population since v1.0.0.  Of JPL's 1,554,321
# asteroids only 139,582 have a measured diameter: 9.0%.  1,553,817 have an
# absolute magnitude H.
#
# Diameter follows from H and the geometric albedo with no free parameters:
#
#     D_km = (1329 / sqrt(p_V)) * 10 ** (-H / 5)
#
# (Fowler & Chillemi 1992; the 1329 km constant is 2 AU_km * 10**(-V_sun/5)
# with the Sun's V = -26.762, and is the same constant JPL and the MPC use.)
#
# So the ONLY estimated quantity is p_V, and everything below is about getting
# the best available p_V for each row and recording which one was used.
#
# ⚠️  READ THIS BEFORE TRUSTING A DERIVED ROW.  D scales as p_V**-0.5, and this
# pipeline turns D into MASS as D**3, so mass scales as p_V**-1.5.  Get the
# albedo wrong by 2x and the mass is wrong by 2.8x.  Every consumer that ranks
# on mass is therefore much more exposed to this than the diameter column
# suggests, which is why `diameter_source` and `derived_diameter_is_estimate`
# exist and why nothing here ever overwrites a measurement.
#
# ⚠️  AND THE ALBEDO SAMPLE BELOW IS BIASED, in the optimistic direction.  Both
# tables are medians over the 138,437 bodies that HAVE a measured albedo, and
# those measurements are overwhelmingly NEOWISE, a thermal-infrared survey.
# At a fixed H a darker body must be larger, and a larger warmer body is easier
# for a thermal survey to detect, so the measured sample over-represents dark
# bodies relative to the 1.4 M that were never measured.  A median that is too
# LOW yields a diameter that is too LARGE and a mass that is too large by the
# 1.5 power.  Do not "correct" this by raising the table to taste; that is the
# same move CLAUDE.md rejects for IN_SPACE_UTILITY.  Quantifying it needs a
# debiased size-frequency model, which this module does not have.

# Median measured geometric albedo per spectral type.  DERIVED, not asserted:
# computed 2026-08-08 over every JPL SBDB asteroid with 0 < albedo < 1 and a
# Bus-DeMeo (spec_B) or, failing that, Tholen (spec_T) classification: 1,897
# bodies.  Sample size is carried on each row because it varies by two orders
# of magnitude across the table and a reader deserves to see which entries are
# solid.  Types with n < 5 are deliberately ABSENT rather than guessed; they
# fall through the chain in `_albedo_for_derivation` below.
ALBEDO_BY_SPECTRAL_TYPE: Dict[str, float] = {
    "A":   0.2980,   # n=16
    "B":   0.0670,   # n=65
    "C":   0.0540,   # n=195
    "Cb":  0.0520,   # n=35
    "Cg":  0.0490,   # n=9
    "Cgh": 0.0720,   # n=15
    "Ch":  0.0504,   # n=136
    "D":   0.0509,   # n=39
    "F":   0.0466,   # n=20
    "K":   0.1423,   # n=34
    "L":   0.1680,   # n=35
    "Ld":  0.1610,   # n=12
    "M":   0.1310,   # n=15
    "O":   0.1905,   # n=6
    "P":   0.0435,   # n=22
    "Q":   0.2475,   # n=10
    "S":   0.2439,   # n=534
    "Sa":  0.2650,   # n=33
    "Sk":  0.2340,   # n=19
    "Sl":  0.2240,   # n=51
    "Sq":  0.2760,   # n=59
    "Sr":  0.3180,   # n=17
    "T":   0.0645,   # n=16
    "V":   0.3880,   # n=36
    "X":   0.0855,   # n=156
    "Xc":  0.0750,   # n=61
    "Xe":  0.2090,   # n=27
    "Xk":  0.0955,   # n=42
}

# ⚠️  E-types are the known casualty of the n >= 5 rule.  Only four measured
# E-types carry a JPL taxonomy, so "E" is absent, its root letter is itself, and
# an E-type with no measured albedo therefore falls all the way to its orbital
# bin, which will be far too dark for an enstatite surface (real E-types run
# p_V ~ 0.4-0.5) and will size the body much too large.  It is left absent
# rather than filled from literature so that the table stays one thing, 
# medians over this catalog; instead of a mixture nobody can audit.  E-types
# with a MEASURED albedo are unaffected, and that is most of the ones that
# matter.  Same applies to G and R.

# Median measured geometric albedo by semi-major axis, same 138,437-body
# sample.  THIS is the branch that actually sizes the catalog: a body with a
# taxonomy almost always has a diameter too, so the taxonomy table above fires
# rarely, while ~1.4 M bodies have nothing but H and an orbit.
#
# The gradient is the well-known compositional zoning of the belt, S-complex
# inner, C-complex outer, and it is strong enough to be worth binning for:
# 0.2885 at 1.3-2.0 AU against 0.0660 in the outer belt is a factor of 4.4 in
# albedo, which is a factor of 2.1 in derived diameter and 9.4 in derived mass.
# Bin edges are the classical Kirkwood-gap boundaries, not fitted.
ALBEDO_BY_SEMI_MAJOR_AXIS_AU: Tuple[Tuple[float, float, float, str], ...] = (
    # (a_min, a_max, median p_V, label)
    (0.000,  1.300, 0.1870, "NEA"),                    # n=296
    (1.300,  2.000, 0.2885, "Mars-crosser / inner"),   # n=906
    (2.000,  2.500, 0.1890, "inner belt"),             # n=29,921
    (2.500,  2.820, 0.0860, "middle belt"),            # n=45,912
    (2.820,  3.270, 0.0660, "outer belt"),             # n=57,161
    (3.270,  3.700, 0.0570, "Cybele"),                 # n=1,126
    (3.700,  5.200, 0.0610, "Hilda / Trojan"),         # n=1,884
    (5.200,  1e9,   0.0690, "Centaur / TNO"),          # n=1,228
)

# Overall median across the whole measured sample.  Last resort only: used for
# a body with no albedo, no usable taxonomy and no semi-major axis, which in
# practice cannot happen because validate_and_filter requires an orbit anyway.
ALBEDO_FALLBACK = 0.0780

# D_km = _H_DIAMETER_CONSTANT / sqrt(p_V) * 10**(-H/5)
_H_DIAMETER_CONSTANT = 1329.0


def _albedo_for_derivation(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """
    Best available geometric albedo per row, plus a label saying where it came
    from.  Preference order, most to least trustworthy:

        1. `albedo`                    - a real measurement
        2. ALBEDO_BY_SPECTRAL_TYPE     - exact type, then root letter
        3. ALBEDO_BY_SEMI_MAJOR_AXIS   - the belt's albedo gradient
        4. ALBEDO_FALLBACK             - whole-sample median

    Returns (albedo, source_label) aligned to df.index.
    """
    n = len(df)
    albedo = pd.Series(np.nan, index=df.index, dtype="float64")
    label  = pd.Series("",     index=df.index, dtype="object")

    # ── 1. Measured ───────────────────────────────────────────────────────────
    if "albedo" in df.columns:
        measured = pd.to_numeric(df["albedo"], errors="coerce")
        # An albedo outside (0, 1) is unphysical and shows up in real catalogs
        # as a fit that did not converge.  Reject rather than propagate it into
        # a square root.
        measured = measured.where((measured > 0) & (measured < 1))
        albedo   = albedo.fillna(measured)
        label[measured.notna()] = "measured_albedo"

    # ── 2. Taxonomy ───────────────────────────────────────────────────────────
    # Consult both classification columns; Bus-DeMeo wins where present.  This
    # runs BEFORE enrich_composition, so the albedo-inferred spectral types that
    # step invents are not visible here, which is deliberate.  Inferring a type
    # from albedo and then an albedo from that type would be a closed loop that
    # launders one guess into two columns.
    tax = pd.Series(pd.NA, index=df.index, dtype="object")
    for col in ("spectral_type", "spectral_type_tholen"):
        if col in df.columns:
            candidate = df[col].astype("string").str.strip()
            candidate = candidate.replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
            tax = tax.where(tax.notna(), candidate)

    need = albedo.isna() & tax.notna()
    if need.any():
        def _from_taxonomy(t: object) -> float:
            """Median geometric albedo for a spectral type, or NaN if unknown.

            Falls back to the ROOT letter ("Sq2" to "S"), matching the fallback
            `_lookup()` already uses for composition, so a sub-type nobody
            tabulated still sizes off its complex rather than dropping out of
            the catalog.
            """
            if not isinstance(t, str) or not t:
                return np.nan
            s = t.strip()
            if s in ALBEDO_BY_SPECTRAL_TYPE:
                return ALBEDO_BY_SPECTRAL_TYPE[s]
            # Root letter, matching the fallback _lookup() already uses for
            # composition: "Sq2" → "S".
            return ALBEDO_BY_SPECTRAL_TYPE.get(s[0].upper(), np.nan)

        derived_tax = tax[need].map(_from_taxonomy)
        albedo.loc[need] = derived_tax
        label[need & albedo.notna()] = "taxonomy_albedo"

    # ── 3. Orbital bin ────────────────────────────────────────────────────────
    if "semi_major_axis_au" in df.columns:
        a = pd.to_numeric(df["semi_major_axis_au"], errors="coerce")
        for a_min, a_max, p_v, _lbl in ALBEDO_BY_SEMI_MAJOR_AXIS_AU:
            band = albedo.isna() & a.notna() & (a >= a_min) & (a < a_max)
            albedo.loc[band] = p_v
            label[band] = "orbit_albedo"

    # ── 4. Whole-sample median ────────────────────────────────────────────────
    last = albedo.isna()
    albedo.loc[last] = ALBEDO_FALLBACK
    label[last] = "fallback_albedo"

    assert len(albedo) == n and albedo.notna().all(), \
        "every row must end with an albedo: the fallback cannot be skipped"
    return albedo, label


def derive_missing_diameters(
    df: pd.DataFrame,
    config: CatalogConfig,
) -> pd.DataFrame:
    """
    Fill `diameter_km` from absolute magnitude H where no diameter was measured.

    Runs between merge and validation, because validation is what drops rows
    with no diameter and the entire point is to have one by then.

    Adds two provenance columns, following the `spectral_type_source` /
    `density_measured` convention already used in this module:

        diameter_source                 "measured"
                                        "derived_h_measured_albedo"
                                        "derived_h_taxonomy_albedo"
                                        "derived_h_orbit_albedo"
                                        "derived_h_fallback_albedo"
                                        "none"
        derived_diameter_is_estimate    bool, one thing to filter on

    A measured diameter is NEVER overwritten, whatever the gate is set to.
    """
    df = df.copy()

    if "diameter_km" not in df.columns:
        df["diameter_km"] = np.nan
    diam = pd.to_numeric(df["diameter_km"], errors="coerce")
    measured = diam > 0

    df["diameter_source"] = np.where(measured, "measured", "none")
    df["derived_diameter_is_estimate"] = ~measured

    if not config.derive_diameter_from_h:
        print("\n  Diameter derivation OFF - measured diameters only "
              f"({int(measured.sum()):,} of {len(df):,} rows will survive validation)")
        df["diameter_km"] = diam
        return df

    print("\n  Deriving diameters from absolute magnitude ...")

    if "absolute_magnitude_h" not in df.columns:
        # Every source supplies H, so its total absence means something upstream
        # broke rather than that the data is simply unavailable.  Say so; a
        # silent no-op here costs 1.4 M rows.
        print("     WARN  No `absolute_magnitude_h` column - nothing to derive from. "
              "Check that the JPL fetcher requested the H field.")
        df["diameter_km"] = diam
        return df

    H = pd.to_numeric(df["absolute_magnitude_h"], errors="coerce")
    target = (~measured) & H.notna()
    n_target = int(target.sum())

    if not n_target:
        print("     NOTE   Every row already carries a measured diameter")
        df["diameter_km"] = diam
        return df

    albedo, albedo_label = _albedo_for_derivation(df)

    derived = (
        _H_DIAMETER_CONSTANT / np.sqrt(albedo) * np.power(10.0, -H / 5.0)
    )

    # Floor applies to DERIVED rows only.  A measured diameter below the floor
    # is governed by `min_diameter_km` in validate_and_filter, which is a
    # separate decision about what is worth cataloguing at all.
    if config.min_derived_diameter_km > 0:
        too_small = target & (derived < config.min_derived_diameter_km)
        n_small = int(too_small.sum())
        if n_small:
            print(f"        {n_small:,} derived below "
                  f"{config.min_derived_diameter_km} km - left unfilled "
                  f"(min_derived_diameter_km)")
        target &= ~too_small

    # Guard against a non-finite result reaching the catalog.  H is occasionally
    # absurd in a raw catalog and 10**(-H/5) underflows to 0 for large H.
    target &= np.isfinite(derived) & (derived > 0)

    diam = diam.where(~target, derived)
    df["diameter_km"] = diam
    df.loc[target, "diameter_source"] = (
        "derived_h_" + albedo_label[target].astype(str)
    )
    df["derived_diameter_is_estimate"] = ~measured

    # Publish the albedo this step assumed, in its OWN column, never merged
    # into `albedo`, which must keep meaning "measured".
    #
    # enrich_composition reads it as the last fallback for spectral type, and
    # that is a consistency requirement rather than a convenience.  Assuming
    # p_V = 0.066 for an outer-belt body IS assuming the body is carbonaceous;
    # sizing it on that number and then recording its composition as "Unknown"
    # would leave the catalog holding two incompatible beliefs about the same
    # rock, and "Unknown" carries None for every composition fraction, so the
    # body would get no density, no mass, and be skipped by Stage 4 anyway.
    # That would make the whole derivation pointless: 1.4 M rows with a
    # diameter and nothing to do with it.
    #
    # Note the direction of the dependency, because the reverse WOULD be
    # circular: one assumption (albedo) produces two outputs (size, class).
    # Inferring the class first and then reading an albedo back off the class
    # would launder a single guess into two apparently independent columns.
    df.loc[target, "albedo_assumed_for_diameter"] = albedo[target]

    counts = df["diameter_source"].value_counts()
    print(f"     OK  {int(target.sum()):,} diameters derived  "
          f"(measured kept: {int(measured.sum()):,})")
    for src, n in counts.items():
        if src == "none":
            continue
        print(f"         * {str(src):32s} -> {int(n):,}")
    still = int((pd.to_numeric(df['diameter_km'], errors='coerce').fillna(0) <= 0).sum())
    if still:
        print(f"         * {'no diameter (will be dropped)':32s} -> {still:,}")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATOR  (failsafes)
# ─────────────────────────────────────────────────────────────────────────────
def _log_rejection(df: pd.DataFrame, mask: pd.Series, reason: str) -> dict:
    """Build a rejection-log record for the given mask."""
    count = int(mask.sum())
    examples = (
        df.loc[mask, "designation"].head(5).tolist()
        if count and "designation" in df.columns
        else []
    )
    return {"reason": reason, "rejected_count": count, "examples": str(examples)}


def validate_and_filter(
    df: pd.DataFrame,
    config: CatalogConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Apply validation rules and drop entries with missing critical data.

    Failsafes applied in order:
      1. No designation                                       → drop
      2. No diameter, or diameter ≤ 0                         → drop
      3. Diameter < min_diameter_km                           → drop
      4. No semi-major axis (a)                               → drop
      5. If strict mode: no Bus-DeMeo AND no Tholen type      → drop

    Returns:
        (filtered_df, rejection_log_df)
    """
    print("\n  Validating entries ...")

    if df.empty:
        print("     WARN  Nothing to validate")
        return df.copy(), pd.DataFrame()

    total      = len(df)
    valid_mask = pd.Series(True, index=df.index)
    log        = []

    # ── 1. Designation required ───────────────────────────────────────────────
    if "designation" not in df.columns:
        print("     FAIL  'designation' column missing - cannot build catalog")
        return pd.DataFrame(), pd.DataFrame()

    bad = df["designation"].isna() | (df["designation"].astype(str).str.strip() == "")
    log.append(_log_rejection(df, bad & valid_mask, "Missing designation"))
    valid_mask &= ~bad

    # ── 2/3. Diameter required, positive, and ≥ min_diameter_km ─────────────
    if "diameter_km" in df.columns:
        diam = pd.to_numeric(df["diameter_km"], errors="coerce")

        bad_missing = diam.isna() | (diam <= 0)
        log.append(_log_rejection(df, bad_missing & valid_mask,
                                  "Missing or non-positive diameter"))
        valid_mask &= ~bad_missing

        bad_small = diam < config.min_diameter_km
        log.append(_log_rejection(df, bad_small & valid_mask,
                                  f"diameter < {config.min_diameter_km} km"))
        valid_mask &= ~bad_small
    else:
        log.append({"reason": "diameter_km column absent",
                    "rejected_count": int(valid_mask.sum()), "examples": "N/A"})
        valid_mask[:] = False

    # ── 4. Semi-major axis required ───────────────────────────────────────────
    if "semi_major_axis_au" in df.columns:
        a   = pd.to_numeric(df["semi_major_axis_au"], errors="coerce")
        bad = a.isna() | (a <= 0)
        log.append(_log_rejection(df, bad & valid_mask, "Missing semi-major axis"))
        valid_mask &= ~bad
    else:
        log.append({"reason": "semi_major_axis_au column absent — coordinate mapping disabled",
                    "rejected_count": 0, "examples": "N/A"})
        print("     WARN  No orbital elements - coordinate mapping will be unavailable")

    # ── 5. Strict spectral type (optional) ───────────────────────────────────
    # Validate runs BEFORE enrich_composition's Tholen fallback, so we have to
    # consult `spectral_type` AND `spectral_type_tholen` here, otherwise a row
    # carrying only a Tholen letter (e.g. JPL `spec_T="G"`) would be wrongly
    # rejected, contradicting the CATALOG_CONFIG comment that says strict mode requires
    # "Bus / Tholen".  A row passes if EITHER column has a non-blank value.
    if config.require_spectral_type:
        def _blank(s: pd.Series) -> pd.Series:
            """True where a taxonomy column holds nothing usable.

            NaN and the empty string both count, and so does whitespace: a
            source that writes `" "` for "no classification" would otherwise
            pass strict mode with a blank type.
            """
            return s.isna() | (s.astype(str).str.strip() == "")

        has_bus    = (~_blank(df["spectral_type"]))           if "spectral_type"        in df.columns else pd.Series(False, index=df.index)
        has_tholen = (~_blank(df["spectral_type_tholen"]))    if "spectral_type_tholen" in df.columns else pd.Series(False, index=df.index)

        if not (has_bus.any() or has_tholen.any()):
            log.append({"reason": "no spectral_type / spectral_type_tholen columns (strict mode ON)",
                        "rejected_count": int(valid_mask.sum()), "examples": "N/A"})
            valid_mask[:] = False
        else:
            bad = ~(has_bus | has_tholen)
            log.append(_log_rejection(df, bad & valid_mask,
                                      "Missing Bus AND Tholen spectral type (strict mode ON)"))
            valid_mask &= ~bad

    # ── Apply ─────────────────────────────────────────────────────────────────
    filtered  = df[valid_mask].copy()
    n_kept    = len(filtered)
    n_dropped = total - n_kept

    rejection_df = pd.DataFrame([r for r in log if r["rejected_count"] > 0])

    print(f"     OK  Accepted : {n_kept:,}")
    print(f"     FAIL  Rejected : {n_dropped:,}  ({n_dropped/total*100:.1f}%)")
    if not rejection_df.empty:
        for _, row in rejection_df.iterrows():
            print(f"         * {row['reason']:55s} -> {row['rejected_count']:,} dropped")

    return filtered, rejection_df


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITION ENRICHMENT
# ─────────────────────────────────────────────────────────────────────────────
def enrich_composition(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add composition columns derived from the spectral taxonomy lookup table.

    Steps:
      1. Normalise spectral_type strings  (Title-case, strip blank-ish values).
      2a. Where spectral_type is absent, fall back to spectral_type_tholen.
      2b. Where it's STILL absent, infer a coarse type from geometric albedo.
      2c. Where there is no measured albedo either, fall back to the albedo
          ASSUMED when the diameter was derived from H (v1.1.0).
          A `spectral_type_source` column records provenance:
            • "source"         → arrived from a fetcher (JPL spec_B, SsODNet
                                 taxonomy.class, MP3C taxonomy, …)
            • "tholen"         → filled from spectral_type_tholen (step 2a)
            • "albedo"         → inferred from measured albedo (step 2b)
            • "albedo_assumed" → inferred from the assumed albedo behind an
                                 H-derived diameter (step 2c), the weakest
                                 class, and the bulk of a default v1.1.0 run
            • "unknown"        → still missing after every fallback
      3. Look up TAXONOMY_COMPOSITION fields for each type → `comp_*` cols.
      4. Fill density_gcm3 from taxonomy estimate where no measurement exists;
         `density_measured` flag tracks provenance.
      5. Compute estimated_mass_kg, preserving any value already supplied by a
         fetcher (SsODNet) and filling gaps with (4/3)π r³ ρ from
         diameter × density; `mass_measured` flag tracks provenance.
    """
    print("\n  Enriching composition data ...")
    df = df.copy()

    # ── 1. Normalise spectral_type ────────────────────────────────────────────
    if "spectral_type" not in df.columns:
        df["spectral_type"] = pd.NA

    df["spectral_type"] = (
        df["spectral_type"]
        .astype(str)
        .str.strip()
        .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA, "-": pd.NA,
                  "NaN": pd.NA, "none": pd.NA, "NA": pd.NA})
    )

    # Capitalise to match Bus-DeMeo convention (e.g. "sq" → "Sq")
    def normalise_type(t):
        """One spectral type in Bus-DeMeo capitalisation, or NA.

        First letter upper, rest lower, so "sq" and "SQ" both become "Sq" and
        meet the taxonomy tables' keys. Run through `_by_distinct`, so it is
        called once per class rather than once per row.
        """
        if pd.isna(t) or not isinstance(t, str):
            return pd.NA
        t = t.strip()
        return t[0].upper() + t[1:].lower() if t else pd.NA

    df["spectral_type"] = _by_distinct(df["spectral_type"], normalise_type)

    # `spectral_type_source` tracks WHERE the final classification came from so
    # consumers can filter on confidence:
    #   "source"  - supplied by a fetcher (Bus-DeMeo from JPL spec_B, or a
    #               curated mix from SsODNet / MP3C)
    #   "tholen"  - filled from spectral_type_tholen because Bus wasn't there
    #   "albedo"  - crude inference from geometric albedo
    #   "unknown", still missing after every fallback
    df["spectral_type_source"] = np.where(df["spectral_type"].notna(), "source", "unknown")

    # ── 2a. Fall back to Tholen classification where Bus-DeMeo is missing ────
    # JPL (`spec_T`) supplies Tholen; we hold it in
    # `spectral_type_tholen`.  Most Tholen letters (S, C, X, V, …) overlap with
    # Bus-DeMeo directly; the Tholen-only ones (M, E, P, F, G) are now in
    # TAXONOMY_COMPOSITION too, so the lookup at step 3 handles them uniformly.
    if "spectral_type_tholen" in df.columns:
        tholen = _by_distinct(df["spectral_type_tholen"], normalise_type)
        fill_mask = df["spectral_type"].isna() & tholen.notna()
        df.loc[fill_mask, "spectral_type"]        = tholen[fill_mask]
        df.loc[fill_mask, "spectral_type_source"] = "tholen"
        n_thol = int(fill_mask.sum())
        if n_thol:
            print(f"       Spectral type filled from Tholen for {n_thol:,} entries")

    # ── 2b. Infer from albedo where type is still missing ────────────────────
    def _infer_from_albedo(a: float) -> str:
        """Coarse spectral-type inference from geometric albedo."""
        if a < 0.10: return "C"     # dark      → carbonaceous
        if a < 0.35: return "S"     # moderate  → stony
        return "V"                  # bright    → basaltic or E-type

    if "albedo" in df.columns:
        alb = pd.to_numeric(df["albedo"], errors="coerce")
        infer_mask = df["spectral_type"].isna() & alb.notna()

        df.loc[infer_mask, "spectral_type"]        = alb[infer_mask].apply(_infer_from_albedo)
        df.loc[infer_mask, "spectral_type_source"] = "albedo"
        n_inf = int(infer_mask.sum())
        if n_inf:
            print(f"       Spectral type inferred from albedo for {n_inf:,} entries")

    # ── 2c. Infer from the albedo ASSUMED when the diameter was derived ──────
    # Separate from 2b and separately labelled, because the input is an
    # assumption rather than a measurement.  It exists so a derived body's size
    # and its composition rest on the SAME assumption instead of contradicting
    # each other; see the note in derive_missing_diameters().  Without this the
    # 1.4 M H-derived bodies would all land on TAXONOMY_COMPOSITION["Unknown"],
    # whose fractions are None, so they would carry no density, no mass, and be
    # skipped by Stage 4 for having no mass at all.
    if "albedo_assumed_for_diameter" in df.columns:
        assumed = pd.to_numeric(df["albedo_assumed_for_diameter"], errors="coerce")
        assume_mask = df["spectral_type"].isna() & assumed.notna()

        df.loc[assume_mask, "spectral_type"]        = assumed[assume_mask].apply(_infer_from_albedo)
        df.loc[assume_mask, "spectral_type_source"] = "albedo_assumed"
        n_ass = int(assume_mask.sum())
        if n_ass:
            print(f"       Spectral type inferred from the ASSUMED albedo for "
                  f"{n_ass:,} entries (H-derived diameters)")

    # ── 3. Look up composition fields ────────────────────────────────────────
    # `minerals` and `notes` are included because for a mining-profitability
    # pipeline the dominant minerals + the literature note are first-class
    # outputs; a user looking at one row wants to know what's actually there.
    comp_fields = [
        "group", "composition", "minerals", "notes",
        "density_est_gcm3",
        "metal_fraction", "silicate_fraction", "carbon_fraction", "ice_fraction",
    ]

    def _lookup(spec_type, field):
        """Return composition field for a given spectral type."""
        if pd.isna(spec_type) or not isinstance(spec_type, str):
            return TAXONOMY_COMPOSITION["Unknown"][field]
        if spec_type in TAXONOMY_COMPOSITION:
            return TAXONOMY_COMPOSITION[spec_type][field]
        # Fallback: match first character (e.g. unknown sub-type "Sq2" → "S")
        root = spec_type[0] if spec_type else ""
        if root in TAXONOMY_COMPOSITION:
            return TAXONOMY_COMPOSITION[root][field]
        return TAXONOMY_COMPOSITION["Unknown"][field]

    # One factorisation of `spectral_type`, nine columns read off it.  The
    # codes are identical for every field, so factorising once and indexing
    # nine times is nine passes of C-level take instead of nine of `.apply`.
    _spec_codes, _spec_uniques = pd.factorize(df["spectral_type"],
                                              use_na_sentinel=False)
    for field in comp_fields:
        _vals = np.empty(len(_spec_uniques), dtype=object)
        for _i, _u in enumerate(_spec_uniques):
            _vals[_i] = _lookup(_u, field)
        # `.infer_objects()` for the reason `_by_distinct` documents at length:
        # several of these fields are floats-with-`None`, and `.apply()` would
        # have handed back float64/NaN rather than object/None.
        df[f"comp_{field}"] = pd.Series(_vals[_spec_codes],
                                        index=df.index).infer_objects()

    # ── 3b. PGM enrichment factor (v1.0.4) ────────────────────────────────────
    # Per-spectral-type multiplier applied to platinum-group-metal yields
    # in Module 2's "nickel-iron" mineral.  Differentiated bodies (M-type
    # cores) have ~2× chondritic PGM in their metal phase; basaltic-crust
    # fragments (V-type) ~0.2×.  See PGM_ENRICHMENT_BY_TYPE for the table.
    df["comp_pgm_enrichment"] = _by_distinct(df["spectral_type"],
                                             pgm_enrichment_for_type)
    n_enriched  = int((df["comp_pgm_enrichment"] > 1.0).sum())
    n_depleted  = int((df["comp_pgm_enrichment"] < 1.0).sum())
    if n_enriched or n_depleted:
        print(f"       PGM enrichment: {n_enriched:,} enriched (>1x)  |  "
              f"{n_depleted:,} depleted (<1x)  |  rest baseline (1x)")

    # ── 4. Fill density gap ───────────────────────────────────────────────────
    if "density_gcm3" in df.columns:
        df["density_gcm3"]    = pd.to_numeric(df["density_gcm3"], errors="coerce")
        df["density_measured"] = df["density_gcm3"].notna()
    else:
        df["density_gcm3"]    = np.nan
        df["density_measured"] = False

    df["density_gcm3"] = df["density_gcm3"].fillna(
        pd.to_numeric(df["comp_density_est_gcm3"], errors="coerce")
    )

    n_meas = int(df["density_measured"].sum())
    n_est  = len(df) - n_meas
    print(f"       Density: {n_meas:,} measured  |  {n_est:,} estimated from taxonomy")

    # ── 5. Compute estimated mass (kg) ────────────────────────────────────────
    # Keep any MEASURED mass already supplied by a source (SsODNet).
    # `mass_measured` tracks provenance: True if the value came from a fetcher,
    # False if we derived it here from diameter × density (sphere assumption).
    if "estimated_mass_kg" in df.columns:
        measured = pd.to_numeric(df["estimated_mass_kg"], errors="coerce")
    else:
        measured = pd.Series(np.nan, index=df.index, dtype="float64")
    df["mass_measured"] = measured.notna()

    if "diameter_km" in df.columns:
        diam_m   = pd.to_numeric(df["diameter_km"], errors="coerce") * 1_000.0
        rho_kgm3 = pd.to_numeric(df["density_gcm3"], errors="coerce") * 1_000.0
        derived  = (4 / 3) * np.pi * (diam_m / 2) ** 3 * rho_kgm3
    else:
        derived  = pd.Series(np.nan, index=df.index, dtype="float64")

    # Measured wins; derived fills the gaps.
    df["estimated_mass_kg"] = measured.fillna(derived)

    n_mass_meas = int(df["mass_measured"].sum())
    n_mass_der  = int(df["estimated_mass_kg"].notna().sum()) - n_mass_meas
    print(f"        Mass:    {n_mass_meas:,} measured  |  {n_mass_der:,} derived (diameter x density)")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def build_asteroid_catalog(config: CatalogConfig = CATALOG_CONFIG) -> pd.DataFrame:
    """
    Master entry-point.  Runs the full catalog pipeline:
      1. Fetch from each source
      2. Merge sources
      3. Validate & filter (failsafes)
      4. Enrich with composition data
      5. Sort, tag, and export

    Returns the validated, enriched catalog as a DataFrame.
    Saves CSV + rejection log to config.output_dir.
    """
    t0 = datetime.now()

    print("=" * 65)
    print("    ASTEROID CATALOG PIPELINE  -  MODULE 1: CATALOGING")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  v{config.pipeline_version}")
    print("=" * 65)

    # ── Step 1, Fetch ────────────────────────────────────────────────────────
    # Each entry: "Display name" -> DataFrame (empty if toggled off / failed).
    # To add a new catalog, write a `fetch_<name>(config)` returning a DataFrame
    # keyed on 'designation' and append one line here.  See the ADDITIONAL
    # FETCHERS template section above for the full contract.
    sources: Dict[str, pd.DataFrame] = {
        # JPL is the backbone (first entry → wins on conflicts).  Order of the
        # remaining sources determines which one fills NaN gaps first; SsODNet
        # is placed early because its values are already best-of-literature
        # cross-matches and tend to be more reliable than any single survey.
        "JPL SBDB": fetch_jpl_sbdb(config) if config.use_jpl      else pd.DataFrame(),
        "SsODNet":  fetch_ssodnet(config)  if config.use_ssodnet  else pd.DataFrame(),
        "NEOWISE":  fetch_neowise(config)  if config.use_neowise  else pd.DataFrame(),
        "MP3C":     fetch_mp3c(config)     if config.use_mp3c     else pd.DataFrame(),
        # "<Source>":  fetch_<name>(config) if config.use_<name> else pd.DataFrame(),
    }

    source_counts = {name: len(df) for name, df in sources.items()}
    print(f"\n     Source summary: {source_counts}")

    # ── Step 2, Merge ────────────────────────────────────────────────────────
    merged = merge_sources(sources)
    if merged.empty:
        print("\nFAIL  Pipeline aborted - merge produced no data")
        return pd.DataFrame()

    # ── Step 2b; Derive diameters from H ────────────────────────────────────
    # Must run BEFORE validation: validation is what drops rows with no
    # diameter, and this is what gives them one.
    merged = derive_missing_diameters(merged, config)

    # ── Step 3: Validate & filter ────────────────────────────────────────────
    catalog, rejections = validate_and_filter(merged, config)
    if catalog.empty:
        print("\nFAIL  Pipeline aborted - no entries passed validation")
        return pd.DataFrame()

    # ── Step 4, Composition enrichment ──────────────────────────────────────
    catalog = enrich_composition(catalog)

    # ── Step 4b, Final dedup safety net ─────────────────────────────────────
    # Belt-and-braces: enrichment shouldn't introduce duplicates, but checking
    # here means a CSV written to disk is guaranteed to have unique designations.
    print("\n  Final duplicate sweep ...")
    catalog = deduplicate_catalog(catalog, key="designation", label="final")

    # ── Step 5, Metadata + sort ──────────────────────────────────────────────
    catalog["catalog_date"]      = t0.strftime("%Y-%m-%d")
    catalog["pipeline_version"]  = config.pipeline_version

    if "semi_major_axis_au" in catalog.columns:
        catalog = catalog.sort_values("semi_major_axis_au").reset_index(drop=True)

    # ── Step 6, Save ─────────────────────────────────────────────────────────
    catalog_path  = os.path.join(config.output_dir, config.catalog_filename)
    rejected_path = os.path.join(config.output_dir, config.rejected_filename)

    # lineterminator is pinned because pandas defaults it to os.linesep,
    # which makes a catalog written on Linux differ from the same catalog
    # written on Windows in every line, for no model reason.  CRLF is the
    # existing Windows output, so pinning it changes nothing here.
    catalog.to_csv(catalog_path, index=False, lineterminator="\r\n")
    print(f"\n       Catalog saved  -> {catalog_path}")

    if not rejections.empty:
        # lineterminator is pinned because pandas defaults it to os.linesep,
        # which makes a catalog written on Linux differ from the same catalog
        # written on Windows in every line, for no model reason.  CRLF is the
        # existing Windows output, so pinning it changes nothing here.
        rejections.to_csv(rejected_path, index=False, lineterminator="\r\n")
        print(f"       Rejections log -> {rejected_path}")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - t0).total_seconds()
    print("\n" + "=" * 65)
    print("  OK  CATALOGING COMPLETE")
    print(f"      Entries    : {len(catalog):,}")
    print(f"      Columns    : {len(catalog.columns)}")
    print(f"      Elapsed    : {elapsed:.1f}s")

    # Diameter provenance, alongside the taxonomy provenance the run already
    # prints.  This is the number to read before comparing against a committed
    # result: two runs with the same row count but a different measured /
    # derived split are not the same population.
    if "diameter_source" in catalog.columns:
        vc = catalog["diameter_source"].value_counts()
        n_meas = int(vc.get("measured", 0))
        n_der  = int(len(catalog) - n_meas)
        print(f"      Diameter   : {n_meas:,} measured  |  {n_der:,} derived from H")
        for src, n in vc.items():
            if src == "measured":
                continue
            print(f"                   * {str(src):30s} {int(n):,}")
        if n_der:
            print("      WARN   Derived rows carry an ASSUMED albedo; mass scales as "
                  "p_V**-1.5.\n"
                  "          Filter on `derived_diameter_is_estimate` to get the "
                  "measured-only\n"
                  "          population back out of this catalog.")
    print("=" * 65)

    return catalog


# ─────────────────────────────────────────────────────────────────────────────
# QUERY UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def lookup_asteroid_catalog(catalog: pd.DataFrame, query: str) -> pd.DataFrame:
    """
    Quick lookup by designation or name (case-insensitive substring match).

    Usage:
        lookup_asteroid_catalog(catalog, "Ceres")
        lookup_asteroid_catalog(catalog, "2024 BX1")
        lookup_asteroid_catalog(catalog, "(1) Ceres")

    regex=False, designations and names carry regex metacharacters, which
    pandas' default regex=True would interpret as a pattern: "(1) Ceres"
    silently matched "1 Ceres", and a stray bracket raised re.PatternError.
    """
    q = query.strip().upper()
    mask = (
        catalog["designation"].astype(str).str.upper().str.contains(
            q, na=False, regex=False)
    )
    if "name" in catalog.columns:
        mask |= catalog["name"].astype(str).str.upper().str.contains(
            q, na=False, regex=False)

    results = catalog[mask]
    if results.empty:
        print(f"No entries found matching '{query}'")
    return results


def filter_by_region(catalog: pd.DataFrame, lo_au: float, hi_au: float) -> pd.DataFrame:
    """
    Return catalog entries within a heliocentric distance band (AU).

    Usage:
        mba = filter_by_region(catalog, 2.0, 3.3)   # main belt
        neas = filter_by_region(catalog, 0.0, 1.3)   # NEAs
    """
    if "semi_major_axis_au" not in catalog.columns:
        print("No orbital data available")
        return pd.DataFrame()
    a = pd.to_numeric(catalog["semi_major_axis_au"], errors="coerce")
    return catalog[(a >= lo_au) & (a < hi_au)].copy()


def filter_by_spectral_group(catalog: pd.DataFrame, *groups: str) -> pd.DataFrame:
    """
    Filter by composition group name (e.g. 'C-complex', 'S-complex', 'X-complex').

    Usage:
        metallic = filter_by_spectral_group(catalog, 'X-complex')
        cc = filter_by_spectral_group(catalog, 'C-complex', 'D-type')
    """
    if "comp_group" not in catalog.columns:
        print("No composition group data available")
        return pd.DataFrame()
    return catalog[catalog["comp_group"].isin(groups)].copy()


print("\nOK  Helper utilities available:")
print("    lookup_asteroid_catalog(catalog, 'Ceres')")
print("    filter_by_region(catalog, 2.0, 3.3)   # main-belt slice")
print("    filter_by_spectral_group(catalog, 'X-complex')  # metallic")




# =========================================================================
# MODULE 2 - MINERAL VALUE CATALOG
# =========================================================================




# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import json
import os
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

import spacecost
import requests

for _cat in (DeprecationWarning, FutureWarning, UserWarning):
    warnings.filterwarnings("ignore", category=_cat)

pd.set_option("display.max_columns", None)
pd.set_option("display.float_format", "{:.4g}".format)


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
    # Colab detection.  os.path.isdir("/content") alone is not enough: on
    # Windows a leading "/" is drive-relative, so it tests C:\content -- a
    # directory an earlier run of the pre-fix code may itself have created,
    # which would route output straight back to the path this function
    # exists to avoid.  Require a POSIX platform as well.
    if os.name == "posix" and os.path.isdir("/content"):
        return "/content/asteroid_pipeline"
    return os.path.join(os.getcwd(), "asteroid_pipeline")


_DEFAULT_OUTPUT_DIR = _default_output_dir()


# ═════════════════════════════════════════════════════════════════════════════
# ║                                                                           ║
# ║   ★  USER SETTINGS, EDIT THESE TO TUNE THE PIPELINE  ★                  ║
# ║                                                                           ║
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class MineralValueConfig:
    """User-editable configuration for the mineral-value catalog."""

    # ─── SOURCE TOGGLES ──────────────────────────────────────────────────────
    use_yfinance:        bool = True   # live futures prices via Yahoo Finance
    use_metals_api:      bool = True   # optional metals.dev free tier (DEMO key)
    use_reference_table: bool = True   # curated USGS / LME / mineralogy fallback

    # ─── METALS.DEV (optional, off unless you supply a key) ──────────────────
    # Set to your real API key to enable.  Leaving it as "DEMO" causes the
    # fetcher to silently skip; the demo endpoint is heavily rate-limited.
    metals_api_key: str = "DEMO"
    metals_api_url: str = "https://api.metals.dev/v1/latest"

    # ─── DELIVERY DESTINATION  (drives EVERY price; read this) ──────────────
    # Where the mined material is actually SOLD.  This is the single most
    # consequential field in the pipeline: it selects the market, and the
    # market decides both what a kilogram is worth and which asteroids win.
    #
    #   "earth_surface"; material re-enters and is sold on Earth at
    #                     terrestrial commodity prices.  Water is worth
    #                     ~nothing; platinum is worth $57,000/kg.  Favours
    #                     metal-rich M / X types.
    #   "leo"           - delivered to and sold in low Earth orbit.  Every
    #                     commodity with in-space utility is worth the launch
    #                     cost it avoids ($4,253/kg); precious metals are
    #                     worth nothing, because no orbital market for them
    #                     exists.  Favours water- and metal-rich bulk.
    #   "geo"           - sold at a geostationary servicing depot
    #                     ($12,526/kg).  The only destination in this model
    #                     with a paying customer TODAY: ~550 active
    #                     satellites, and MEV-1 / MEV-2 have already docked
    #                     with commercial GEO spacecraft.  A narrow market
    #                     though; see IN_SPACE_UTILITY_BY_DESTINATION, where
    #                     it is the only destination that discounts the
    #                     METALS rather than the volatiles.
    #   "cislunar"      - sold at a lunar-vicinity (NRHO) depot, worth the
    #                     larger launch cost avoided ($10,810/kg, derived).
    #                     Also the CHEAPEST of the orbital options to reach
    #                     from an asteroid; see Module 4's return-Δv model.
    #   "lunar_surface", sold at a Moon base.  $21,210/kg: nearest
    #                     destination, but airless, so all 5,920 m/s from LEO
    #                     is propulsive.
    #   "mars_orbit"    - sold at a 1-sol Mars-orbit depot ($13,496/kg).  The
    #                     Mars destination that nothing lands on, so it pays
    #                     no entry-survival fraction and, crucially, competes
    #                     with EARTH freight rather than with the Martian
    #                     crust; see IN_SPACE_UTILITY_BY_DESTINATION.
    #   "mars_surface"  - sold at a Mars base.  $45,105/kg: far in Δv, but the
    #                     atmosphere brakes most of the arrival for free.
    #
    # ⚠️  The two surface figures are MARGINAL-TRANSPORT LOWER BOUNDS.  They
    # price the propellant and stages needed to move a kilogram, on a reusable
    # Falcon 9 LEO price, with no first-of-kind development, no programme
    # overhead and no launch-cadence limit.  Real delivered cost today is far
    # higher; CLPS lunar landers run on the order of $1M/kg for ~100 kg
    # payloads.  Treat these as "what it could cost at industrial scale", not
    # "what it costs now".
    #
    # v1.3.0: this used to reprice water only.  It now reprices everything,
    # which is the consistent form of the same correction; see
    # DELIVERY_DESTINATIONS and IN_SPACE_UTILITY below for the numbers, the
    # derivation, and which parts are judgement rather than measurement.
    #
    # ⚠️  Module 4's CALC_CONFIG carries a delivery_destination of its own,
    # and it must MATCH this one; it selects the mission architecture that
    # actually delivers the cargo here.  Module 4 checks and warns.
    delivery_destination: str = "earth_surface"

    # ─── NETWORK ─────────────────────────────────────────────────────────────
    request_timeout: int = 60   # seconds per HTTP request

    # ─── OUTPUT ──────────────────────────────────────────────────────────────
    output_dir:       str = _DEFAULT_OUTPUT_DIR
    catalog_filename: str = "mineral_value_catalog.csv"

    # ─── PRICE UNITS ─────────────────────────────────────────────────────────
    # Every price in this pipeline, live OR reference, is normalised to
    # USD per kilogram before it lands in the output frame.  This constant
    # is the single source of truth for that unit; every column carries the
    # `_usd_per_kg` suffix so the unit is unmistakable downstream.
    PRICE_UNIT: str = "USD/kg"

    # ─── PIPELINE VERSION ────────────────────────────────────────────────────
    # Stamped into every output CSV, and the only way to tell which code
    # produced a given catalog.  BUMP IT when a change moves any number a run
    # produces.  The rule is ONE-DIRECTIONAL: changing a number means bumping,
    # and a bump does NOT mean a number changed, which is why nothing may read
    # a version as evidence that a result moved.
    # THE CHANGELOG IS versions.md, NOT THIS COMMENT.  It used to be 267 lines
    # of release notes sitting right here, a second copy of a record versions.md
    # already held, which is the documentation form of the defect this project
    # keeps cataloguing; it was also what the dashboard rendered as this field's
    # help text, because ui_meta scrapes a field's comment block.  Moved out on
    # 2026-09-02.  Two places to write, neither of them here:
    #     versions.md > Releases            what the release did, and what it
    #                                       measured to say so
    #     versions.md > Module changelogs   this module's own stamp-by-stamp
    #                                       record: Stage 2 changelog
    pipeline_version: str = "1.9.0"

    # ─── DISPLAY ─────────────────────────────────────────────────────────────
    preview_rows:      int = 20   # rows per table in the end-of-run preview
MINERAL_CONFIG = MineralValueConfig()
os.makedirs(MINERAL_CONFIG.output_dir, exist_ok=True)

print(f"OK  Configuration loaded - output dir: {MINERAL_CONFIG.output_dir}")
print(f"    Active sources : "
      f"{', '.join(s for s, on in (('yfinance', MINERAL_CONFIG.use_yfinance), ('metals.dev', MINERAL_CONFIG.use_metals_api and MINERAL_CONFIG.metals_api_key != 'DEMO'), ('reference', MINERAL_CONFIG.use_reference_table)) if on)}")
print(f"    Price unit     : {MINERAL_CONFIG.PRICE_UNIT}  (every numeric price column ends with _usd_per_kg)")
print(f"    Delivery dest  : {MINERAL_CONFIG.delivery_destination}  "
      f"(sets EVERY price - see DELIVERY_DESTINATIONS + IN_SPACE_UTILITY)")


# ─────────────────────────────────────────────────────────────────────────────
# UNIT-CONVERSION HELPERS
# ─────────────────────────────────────────────────────────────────────────────
# yfinance quotes precious metals in USD per troy ounce and copper in
# USD per pound.  USGS quotes base metals in USD per tonne.  We funnel
# everything through these helpers so the output column is always
# `price_usd_per_kg` regardless of the source.

TROY_OZ_PER_KG = 32.150_746_568   # 1 kg = 32.1507... troy oz
LB_PER_KG      = 2.204_622_621    # 1 kg = 2.20462... pounds
KG_PER_TONNE   = 1_000.0


def _per_troy_oz_to_per_kg(usd_per_oz: float) -> float:
    """Precious-metal quote to $/kg. This is the yfinance path (GC=F, SI=F, PL=F, PA=F)."""
    return float(usd_per_oz) * TROY_OZ_PER_KG


def _per_lb_to_per_kg(usd_per_lb: float) -> float:
    """Copper's quote to $/kg. yfinance prices HG=F per pound, alone among these."""
    return float(usd_per_lb) * LB_PER_KG


def _per_tonne_to_per_kg(usd_per_tonne: float) -> float:
    """USGS and LME base-metal quotes to $/kg. Metric tonne, so exactly /1,000."""
    return float(usd_per_tonne) / KG_PER_TONNE


# ─────────────────────────────────────────────────────────────────────────────
# MINERAL REFERENCE TABLE
# ─────────────────────────────────────────────────────────────────────────────
# One row per entity that Module 1's TAXONOMY_COMPOSITION can name OR that the
# user might want to value separately.  Splits cleanly into two kinds:
#
#   • ELEMENTS  - actually tradable commodities, priced by markets.
#                 Live-price columns get filled by the fetchers.
#   • MINERALS  - rock-forming compounds, priced via their valuable elemental
#                 yield (e.g. magnetite = Fe ore; nickel-iron ≈ 90 % Fe + 10 %
#                 Ni by mass).  The `yields` dict maps the mineral onto the
#                 element rows so Module 3 can compute mass × composition ×
#                 yield × price without any extra wiring.
#
# Density values (`density_gcm3`) are bulk physical constants drawn from
# standard mineralogy references (Klein & Hurlbut "Manual of Mineralogy",
# Mindat.org, Webmineral.com).  They do NOT vary by source and never need
# to be re-fetched.
#
# Reference prices (`ref_price_usd_per_kg`) are listed for sources that the
# live fetcher cannot reach (LME metals, non-Pt/Pd PGMs, water-in-space) plus
# every element as a fallback for offline / API-down runs.  `ref_price_date`
# records when each figure was last reviewed so the user can decide whether
# to update it.

# Reference snapshot date for the static price column.  Update this whenever
# you refresh ref_price_usd_per_kg values (the numbers below, when a fresh
# audit re-reviews the static prices, bump this stamp).
_REF_PRICE_DATE = "2026-05-29"


# ─────────────────────────────────────────────────────────────────────────────
# WATER VALUE BY DELIVERY DESTINATION  (v1.2.0)
# ─────────────────────────────────────────────────────────────────────────────
# Water is the pipeline's single most consequential price.  It is ~100% of the
# bulk value of every C / B / D-type asteroid, so whichever number goes here
# determines the entire top of the profitability ranking.
#
# Water has no intrinsic scarcity value; it is worth what it costs to put it
# where the customer is.  So the price is a function of DESTINATION, not of
# the asteroid:
#
#   earth_surface; you flew it down a gravity well to a planet that is 71%
#                   ocean.  It is worth bulk industrial water, and even that
#                   overstates it once you account for the fact that nobody
#                   needs it.  This is what a sample-return architecture
#                   actually delivers.
#   leo           - worth the launch cost it avoids.  $4,250/kg matches the
#                   Falcon 9 reusable $/kg-to-LEO in Module 3, so the two
#                   modules stay consistent by construction.
#   cislunar      - worth the cost of lifting it to lunar vicinity.  Roughly
#                   3× the LEO figure, tracking the Δv difference between LEO
#                   and a TLI/NRHO depot.
#
# BEFORE v1.2.0 this table did not exist and water was hardcoded at the LEO
# figure while Module 4's mission model returned the material to Earth's
# surface; pricing the cargo as if it had been left in orbit.  That single
# inconsistency was worth a factor of ~4 million on C-type asteroids and
# inverted the entire ranking.

# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY DESTINATIONS  -  what a kilogram is worth, and where  (v1.3.0)
# ─────────────────────────────────────────────────────────────────────────────
#
# Material sold in space is worth the launch cost it AVOIDS.  That number is
# not asserted here; it is derived from the rocket equation, from the Δv
# ladder in Module 3's DELTA_V_REFERENCE, and from a real launch price.
#
# 🚨  EVERY CONSTANT AND EVERY LEG THAT USED TO BE HERE IS IN
# `spacecost.delivery` NOW, AND THE SENTENCE THAT STOOD HERE IS WHY:
#
#     Constants below are cross-referenced to Module 3.  They are duplicated
#     rather than imported because Module 2 runs BEFORE Module 3 in the
#     pipeline order (and in the concatenated master.py), so the tables are
#     not in scope.  If you change one of these, change it in Module 3 too.
#
# Nine delta-v retyped by hand, a launch price retyped by hand, three cost
# lines retyped by hand, and a manual-sync instruction holding them together.
#
# ⚠️  THE JUSTIFICATION DIED WHEN STAGE 3 BECAME A PIP PACKAGE, AND IT TOOK
# TWO RELEASES TO NOTICE.  A package has no position in a pipeline: master.py
# installs spacecost in its header, before any stage's code runs, so this
# module imports it exactly as Module 4 does, and a standalone `py
# modules/mineral_value.py` fetches it from the install block at the top of
# this file.  Concatenation order was the whole argument, and concatenation
# order stopped applying.  The general lesson is the one this repo keeps
# paying for: a comment explaining why two copies exist is not a reason they
# still have to.
#
# ⚠️  THE NAMES BELOW STAY BOUND ON PURPOSE, they are not leftovers.
# `campaign/worked_calculation.py` reaches `master._DELIVERY_LEGS`,
# `master._LEO_USD_PER_KG` and `master.delivered_cost_usd_per_kg`, and carries
# all three on its `BORROWED` register.  Re-exporting is what keeps that
# reader working, so deleting an alias here is a breaking change for it rather
# than a tidy-up.
#
# ⚠️  NEVER SPELL A WORD THE BUILD REWRITES.  `build_master.py` renames three
# of this module's top-level names on the way into master.py -- the config
# global, the source-merge helper and the sanity-check function -- as WHOLE
# WORDS over the entire file text, comments and string literals included.
# They are deliberately not spelled out in this paragraph: an earlier draft
# named one, and in master.py the warning came out naming the RENAMED word
# instead, which is the same comment-rewriting trap arriving inside the
# comment about it.  `build_master.py` is the list.  Reach the package
# through `spacecost.`, and read the built master.py rather than this file,
# because they are not the same text.
#
# WHAT MOVED AND WHAT IS STILL TYPED is documented in spacecost/delivery.py.
# The short version: every chain delta-v is a DELTA_V_REFERENCE lookup now, so
# the table is the one authority; the six downleg departure burns are NOT,
# because two of them have no row at all and a third disagrees with its row by
# 2 m/s, and deriving all six uniformly would have moved two published prices
# under a change that moves none.

G0_M_S2 = spacecost.G0_M_S2        # standard gravity, exact by definition

# Falcon 9 reusable $/kg-to-LEO, off `LAUNCH_VEHICLES_REFERENCE` rather than
# typed.  The cheapest operational figure in that table, so every in-space
# price derived from it is a LOWER bound on the launch cost avoided.
_LEO_USD_PER_KG = spacecost.LEO_LAUNCH_USD_PER_KG

# The leg chains.  ⚠️  `None` and `[]` are DIFFERENT and both are used:
# `earth_surface` has no chain and avoids no launch, `leo` has an EMPTY chain
# and avoids the whole LEO price.  `_build_destination_table` below tests
# `is None` for exactly that reason, and a truthiness test there would price
# Earth's surface at 4,253 $/kg.
_DELIVERY_LEGS = spacecost.DELIVERY_CHAINS

delivered_cost_usd_per_kg = spacecost.delivered_cost_usd_per_kg


# Terrestrial bulk-industrial water, for the earth_surface case.  Municipal /
# industrial bulk water runs $0.0005-0.002/kg; asteroid water landed on Earth
# competes with rain.
_EARTH_SURFACE_WATER_USD_PER_KG = 0.001


_DESTINATION_NOTES = {
    "leo":           "Falcon 9 reusable $/kg-to-LEO, straight off Module 3.",
    "geo":           "LEO -> GTO (2,455 m/s), then an apogee burn of 1,836 "
                     "m/s that circularises and removes 28.5 deg of "
                     "inclination at once.  Coplanar that burn would be "
                     "1,478, so 358 m/s of this price is the latitude of the "
                     "launch site.  Dearer per kilogram than a cislunar "
                     "depot, and a far narrower market once it arrives.",
    "cislunar":      "TLI + NRHO insertion (3,600 m/s) on one cryo stage.",
    "lunar_surface": "TLI + LOI (4,050 m/s) on a cryo stage, then powered "
                     "descent (1,870 m/s) on a lander.  No atmosphere, so "
                     "every metre per second is propulsive — the Moon is the "
                     "nearest destination and among the dearest to land on.",
    "mars_orbit":    "TMI (3,600 m/s), then 900 m/s of capture into the "
                     "250 x 33,793 km 1-sol staging orbit (NASA DRA 5.0).  "
                     "Binding an ellipse is far cheaper than circularising: "
                     "the same arrival costs 2,100 m/s into a 200-km orbit.  "
                     "Nothing enters the atmosphere, so unlike mars_surface "
                     "there is no entry-survival fraction on top.",
    "mars_surface":  "TMI (3,600 m/s), then aeroentry surviving 30% of entry "
                     "mass (MSL / Perseverance measured), then 800 m/s of "
                     "retropropulsion.  Mars is far but its atmosphere does "
                     "most of the braking for free.",
}


def _build_destination_table() -> Dict[str, dict]:
    """Materialise the destination table, deriving every in-space price."""
    out = {}
    for key, legs in _DELIVERY_LEGS.items():
        if legs is None:                     # Earth's surface avoids no launch
            out[key] = {
                "usd_per_kg": 0.0,
                "dv_above_leo_m_s": 0.0,
                "basis": "terrestrial market price",
                "notes": "Material delivered to Earth's surface avoids no "
                         "launch, so it is worth its terrestrial commodity "
                         "price and nothing more.",
            }
            continue
        dv_total = sum(l[1] for l in legs if l[0] == "burn")
        cost     = delivered_cost_usd_per_kg(key)
        out[key] = {
            "usd_per_kg": cost,
            "dv_above_leo_m_s": dv_total,
            "basis": ("launch cost avoided (LEO)" if not legs
                      else f"launch cost avoided (LEO + {dv_total:,.0f} m/s"
                           + (" + entry" if any(l[0] == "edl" for l in legs) else "")
                           + ")"),
            "notes": (f"Derived from ${_LEO_USD_PER_KG:,.0f}/kg to LEO "
                      f"(Falcon 9 reusable, Module 3): "
                      + _DESTINATION_NOTES.get(key, "")
                      + f"  Needs {cost / _LEO_USD_PER_KG:,.2f} kg in LEO per "
                        f"kg delivered."),
        }
    return out


DELIVERY_DESTINATIONS: Dict[str, dict] = _build_destination_table()


# ─── DOWNLEG: GETTING IT FROM A DEPOT TO THE TERRESTRIAL MARKET ──────────────
# A commodity with no in-space demand is not worthless at a depot; it is
# worth its Earth price MINUS whatever it costs to fly it the rest of the way
# down.  Someone has to pay that leg; the miner selling at the depot eats it
# in the price.
#
# Moved to `spacecost.delivery` with the delivery chains above, and for the
# same reason: the capsule, TPS and recovery lines were three more
# hand-retyped copies of `OPERATIONAL_COSTS_REFERENCE` rows, and they are read
# off that table now.
#
# The surface cases are punishing, and correctly so: hauling material back UP
# out of a gravity well you just landed in is close to the worst thing you can
# do with it.  Mars in particular ends up costing more to ship home than any
# commodity in this catalog is worth, which is the honest answer; you do not
# mine asteroids to deliver platinum to Mars and then fly it back.
downleg_cost_usd_per_kg = spacecost.downleg_cost_usd_per_kg


# ─── IN-SPACE UTILITY BY COMMODITY ───────────────────────────────────────────
# How much of the launch-cost-avoided a commodity actually captures at an
# in-space destination.  1.0 means it is a drop-in substitute for the same
# mass launched from Earth; 0.0 means there is no in-space market for it at
# all and it can only be sold by flying it down.
#
# ⚠️  THESE ARE ENGINEERING JUDGEMENTS, NOT MEASUREMENTS.  Unlike the price
# above, which is derived from the rocket equation and a real launch price, 
# no market exists yet to calibrate these against.  They are the single
# biggest soft assumption in the in-space case, so they live here as one
# obvious table rather than being buried per-entry.
#
# This table is the BASE PROFILE, and it describes a destination with no local
# resources of any kind: LEO and cislunar, where the only alternative to
# importing a kilogram from an asteroid is launching that kilogram from Earth.
# Planetary surfaces have a third option, dig it up locally, and they get
# per-destination overrides in IN_SPACE_UTILITY_BY_DESTINATION below.
IN_SPACE_UTILITY: Dict[str, float] = {
    # Volatiles, the canonical in-space commodity.  Water is propellant
    # feedstock, radiation shielding, life support and coolant; electrolysis
    # is the only processing step between raw ice and a fuelled depot.
    "water":            1.00,
    # Structural metals.  Discounted for the in-space manufacturing gap:
    # raw Fe-Ni is not a pressure vessel, and the melting / forming plant that
    # turns it into one is not costed anywhere in this pipeline.
    "iron":             0.70,
    "nickel":           0.70,
    "cobalt":           0.70,
    "copper":           0.70,   # wiring, coils, heat exchangers
    "nickel-iron":      0.70,
    "awaruite":         0.70,
    "magnetite":        0.40,   # oxide, needs reduction before it is metal
    "troilite":         0.30,   # sulphur source, minor structural use
    # Silicates.  Usable as bulk radiation shielding and as 3-D-printing /
    # sintering feedstock, but a poor per-kg substitute for engineered
    # structure, and available in quantity from the Moon as well.
    "olivine":          0.25, "pyroxene":        0.25, "orthopyroxene": 0.25,
    "enstatite":        0.25, "plagioclase":     0.25, "spinel":        0.25,
    "phyllosilicates":  0.25, "oxides":          0.25, "silicates":     0.25,
    # Carbon and organics: composites, plastics, agriculture feedstock.
    "carbon":           0.40,
    "organics":         0.20,
    # Everything not listed, the precious metals above all, defaults to 0.0.
    # That does NOT make them worthless at a depot: a zero here means only
    # that nobody in orbit wants the material for its own sake, so it is
    # valued by shipping it down instead (terrestrial price less the downleg).
    # See in_space_price_usd_per_kg.
}
IN_SPACE_UTILITY_DEFAULT = 0.0


# ─── UTILITY BY DESTINATION  (v1.7.0) ────────────────────────────────────────
# Until v1.7.0 one utility table served every in-space destination, so a
# kilogram of olivine was assumed to be worth the same fraction of its freight
# on the surface of Mars as at a propellant depot in LEO.  It is not, and the
# reason is not distance; it is that THE ALTERNATIVE TO IMPORTING IS NOT
# ALWAYS LAUNCHING FROM EARTH.
#
#   LEO, cislunar    Empty space.  Nothing is available locally at any price,
#                    so the only substitute for asteroid material is the same
#                    material launched from Earth.  These keep the base table
#                    above; they are the calibration anchor, and every
#                    override below is defined as a deviation from them.
#   lunar_surface    Sits on 4×10^19 t of silicate regolith containing 5-15 wt%
#                    FeO plus mare ilmenite, and (at the poles) water ice.
#   mars_surface     Sits on metres-thick mid-latitude ground ice (SHARAD /
#                    SWIM), 1-3 wt% hydrated regolith measured by Curiosity's
#                    SAM, a 95.3% CO2 atmosphere, and a globally oxidised
#                    iron-rich crust.
#
# So the correction runs mostly DOWNWARD, and hardest at the destination that
# is furthest away, which inverts the naive reading of the price table above.
# Mars has the dearest freight ($45,105/kg) AND the poorest market for bulk
# asteroid material, because a settlement with an atmosphere and a crust makes
# its own water, carbon and rock.  Do not "fix" that by raising these back up:
# the high delivered cost is what Earth would pay, and the low utility is the
# competition Earth's freight does not face.
#
# Every override runs DOWNWARD.  That is not modesty, it is the only direction
# this table can be moved without the change becoming a way to manufacture
# viability, which is the one thing the in-space case must not be tuned into.
#
# ⚠️  CONSIDERED AND REJECTED: giving the precious metals a small non-zero
# utility (0.05) at the two SURFACE destinations.  The physical argument is
# sound; a crewed base runs fuel cells, electrolysers and Sabatier reactors
# and wants Pt/Pd/Ru catalysts, where a propellant depot genuinely does not.
# It was dropped because this module prices each commodity with ONE $/kg and
# ONE market depth, and in_space_price_usd_per_kg routes on unit price alone.
# Gold at a lunar base would then route "used in space" at $76,060/kg into a
# 25 kg/yr catalyst market, beating a $30,061/kg route into a 3,000,000 kg/yr
# terrestrial one, a five-order-of-magnitude cliff in market depth, invisible
# to the router, that would make precious-metal bodies look worse for a reason
# with no physics in it.  The real behaviour is a blend (sell the first few kg
# in space, fly the rest home) and this pipeline cannot express a blend.
# Restoring it needs a quantity-aware route choice first, not a bigger table.
#
# ⚠️  Softer than the base table, which is already the softest thing in the
# pipeline.  These are judgements about economies that do not exist.
IN_SPACE_UTILITY_BY_DESTINATION: Dict[str, Dict[str, float]] = {
    "leo":      {},                  # base profile, no local resources
    # \U0001f6a8  v1.9.0.  GEO IS THE FIRST DESTINATION WHOSE OVERRIDES RUN DOWNWARD
    # ON THE METALS AND THE ROCK RATHER THAN ON THE VOLATILES, and it is a
    # different ARGUMENT from every block below, not a different number.
    #
    # The lunar and martian overrides are about local SUPPLY: a settlement
    # standing on a crust can dig up its own water and iron, so imported
    # material competes with local mining.  Nothing is mined at GEO and
    # nothing ever will be.  These discounts are about local DEMAND, which is
    # the other half of what this table means: utility is "how good a
    # substitute 1 kg of this is for a LAUNCHED kg here", and nobody launches
    # a kilogram of copper to geostationary orbit.  A GEO depot exists to
    # refuel and service satellites; there is no factory 36,000 km up, no
    # crew, and no construction site.  So the volatiles keep most of their
    # value and the feedstock loses nearly all of it.
    #
    # ⚠️  That makes GEO the destination most sensitive to this table, which
    # is the softest thing in the pipeline.  The price above is derived from
    # the rocket equation; the numbers below are judgement about a market
    # that does not exist yet.  They are also still overrides that run
    # DOWNWARD from the base profile, which is the invariant that keeps this
    # table from becoming a way to manufacture viability.
    "geo": {
        # Propellant feedstock is the whole business case, and water is the
        # feedstock: electrolysed for orbit-raising, or fed to a water
        # thruster directly.  Discounted off the base 1.00 because a depot
        # with no crew has no life support and no coolant loop to fill, which
        # is two of the four uses the base profile is built on.
        "water":            0.80,
        # There is no manufacturing at GEO.  The base profile already
        # discounts raw Fe-Ni to 0.70 for "the melting and forming plant that
        # turns it into a pressure vessel is not costed anywhere in this
        # pipeline"; at GEO that plant is not merely uncosted, it is
        # implausible.  Ni / Co / Cu are discounted here where the two
        # surfaces leave them alone, and the reason is the one above: those
        # overrides are about there being no local ORE, this one is about
        # there being no local FACTORY.
        "iron":             0.15, "nickel":       0.15, "cobalt":     0.15,
        "copper":           0.15, "nickel-iron":  0.15, "awaruite":   0.15,
        "magnetite":        0.05, "troilite":     0.05,
        # Bulk shielding is the one real use for rock here, and GEO spends
        # most of its time outside the magnetosphere, so it is not zero.  It
        # is not 0.25 either: nobody bolts raw olivine to a comsat.
        "olivine":          0.05, "pyroxene":     0.05, "orthopyroxene": 0.05,
        "enstatite":        0.05, "plagioclase":  0.05, "spinel":        0.05,
        "phyllosilicates":  0.05, "oxides":       0.05, "silicates":     0.05,
        # No chemical plant and no agriculture.
        "carbon":           0.05,
        "organics":         0.05,
        # Precious metals stay at the base 0.00 and route down, as everywhere.
    },
    "cislunar": {},                  # base profile, no local resources
    # 🚨  v1.8.0.  mars_orbit TAKES THE BASE PROFILE, AND THE EMPTY DICT IS
    # THE WHOLE POINT.  It will look like an oversight next to the block
    # below, and copying mars_surface's overrides up into it is the one edit
    # that would destroy this destination's meaning.
    #
    # The overrides below exist because a settlement STANDING ON a crust can
    # dig up its own water, iron and rock, so asteroid material competes with
    # local mining.  A depot in a 1-sol orbit competes with nothing of the
    # kind: everything martian is 3,400 km down a gravity well that costs
    # 4,100 m/s of ascent to climb, which is more than the 3,600 m/s of TMI
    # that brought the cargo from Earth in the first place.  The alternative
    # to importing a kilogram HERE is launching that kilogram from Earth,
    # which is the exact condition the base profile is calibrated on.
    #
    # So the ISRU discount that carries the mars_surface result is not a
    # property of Mars, it is a property of being ON Mars, and this
    # destination is the control that says so.
    "mars_orbit": {},                # base profile: the crust is 4,100 m/s away
    "lunar_surface": {
        # Polar ice is real and is the entire premise of a lunar base, but it
        # is in permanently shadowed craters at ~40 K with no sunlight to work
        # by.  Discounted, not eliminated.
        "water":            0.60,
        # Regolith is 5-15 wt% FeO and the mare carries ilmenite; hydrogen
        # reduction and molten regolith electrolysis both work at lab scale.
        "iron":             0.45,
        "nickel-iron":      0.45,
        "awaruite":         0.45,
        "magnetite":        0.25,
        # Ni / Co / Cu are NOT discounted.  No concentrated ore of any of them
        # is known on the Moon, and they are what motors, batteries and wiring
        # are made of; the base table's 0.70 already prices the manufacturing
        # gap.
        # Shipping silicate rock to a body made of silicate rock.  Kept just
        # above zero for the specific phases nobody has demonstrated
        # separating from regolith, not for bulk shielding mass.
        "olivine":          0.03, "pyroxene":       0.03, "orthopyroxene": 0.03,
        "enstatite":        0.03, "plagioclase":    0.03, "spinel":        0.03,
        "phyllosilicates":  0.03, "oxides":         0.03, "silicates":     0.03,
        # Carbon is one of the genuinely scarce elements on the Moon; 
        # solar-wind implantation leaves it at ~100 ppm, which is not a
        # resource.  No discount.
        # Precious metals stay at the base 0.00 and route down; see the
        # rejected-change note above.
    },
    "mars_surface": {
        # Mars has more accessible water than anywhere in the model except
        # Earth.  Importing water to Mars is the least defensible trade the
        # flat table used to permit, and the Mars headline result rested on it.
        "water":            0.25,
        # A globally oxidised, iron-rich crust, plus loose meteoritic iron
        # sitting on the surface (Meridiani "Heat Shield Rock").
        "iron":             0.40,
        "nickel-iron":      0.40,
        "awaruite":         0.40,
        "magnetite":        0.15,
        "troilite":         0.15,   # Mars has abundant crustal sulphate
        # Ni / Co / Cu again undiscounted, no known concentrated martian ore.
        # Basalt, everywhere, for free.
        "olivine":          0.02, "pyroxene":       0.02, "orthopyroxene": 0.02,
        "enstatite":        0.02, "plagioclase":    0.02, "spinel":        0.02,
        "phyllosilicates":  0.02, "oxides":         0.02, "silicates":     0.02,
        # The atmosphere is 95.3% CO2 at ~600 Pa.  Carbon is free on Mars, and
        # Sabatier + electrolysis turns it and the local water into methane and
        # onward feedstock, which is most of what "organics" would be for.
        "carbon":           0.02,
        "organics":         0.05,
        # Precious metals stay at the base 0.00 and route down; see the
        # rejected-change note above.  At Mars that means zero: the $96,394/kg
        # downleg exceeds every terrestrial price in the catalog.
    },
}


def in_space_utility(name: str, destination: str) -> float:
    """How good a substitute 1 kg of `name` is for a launched kg at `destination`.

    Per-destination override first, base profile second, 0.0 last.  An unknown
    destination falls through to the base profile, which is the conservative
    choice: it assumes no local competition, so it can only over-value the
    material, and the caller has already warned about the unknown key.
    """
    dest = str(destination or "").strip().lower()
    override = IN_SPACE_UTILITY_BY_DESTINATION.get(dest, {})
    if name in override:
        return float(override[name])
    return float(IN_SPACE_UTILITY.get(name, IN_SPACE_UTILITY_DEFAULT))


# ─── HOW BIG IS THE MARKET?  (v1.5.0) ────────────────────────────────────────
# Prices in this pipeline were static at the point of sale: a mission could
# return any quantity of platinum and still sell every kilogram at spot.  That
# is the one remaining assumption that flatters the model in a direction
# nothing else corrects, because the whole "just fly more missions" lever; 
# nre_amortization_missions, has no natural stopping point without it.
#
# Terrestrial figures are USGS Mineral Commodity Summaries annual primary
# production.  Bulk commodities Earth has in effective abundance carry a
# deliberately huge number so saturation never binds on them.
ANNUAL_WORLD_PRODUCTION_KG: Dict[str, float] = {
    # Precious: small markets, and the ones asteroid mining always targets
    "osmium":         1.0e3,      # ~1 t/yr, a by-product of a by-product
    "iridium":        7.5e3,      # ~7.5 t
    "rhodium":        2.3e4,      # ~23 t
    "ruthenium":      3.0e4,      # ~30 t
    "platinum":       1.8e5,      # ~180 t
    "palladium":      2.1e5,      # ~210 t
    "gold":           3.0e6,      # ~3,000 t
    "silver":         2.6e7,      # ~26,000 t
    # Base metals; large markets, saturation effectively never binds
    "cobalt":         2.3e8,
    "copper":         2.2e10,
    "nickel":         3.6e9,
    "iron":           1.3e12,     # world pig-iron production
    # Effectively unlimited on Earth
    "water":          1.0e15,
    "carbon":         1.0e12,
    "silicates":      1.0e15,
    "organics":       1.0e12,
}
_UNLIMITED_MARKET_KG = 1.0e15

# What a theoretical in-space base can actually ABSORB per year, all
# commodities competing for the same import budget.
#
# ⚠️  JUDGEMENT, not measurement; no such market exists.  Anchored to
# publicly discussed architectures: a Starship-class refuelling campaign needs
# on the order of 1,000 t of propellant in LEO per Mars departure; an
# Artemis-scale NRHO depot is a fraction of that; surface bases are smaller
# again and would supply much of their own water locally from regolith or ice.
#
# This is what stops a single mission "selling" 40 tonnes of water to a Mars
# outpost at full launch-cost-avoided.  A base that imports 20 t/yr does not
# pay the same price for the 400th tonne as for the first.
IN_SPACE_ANNUAL_DEMAND_KG: Dict[str, float] = {
    "leo":           500_000.0,
    # v1.9.0.  The only row here anchored on hardware that EXISTS: ~550 active
    # geostationary satellites at roughly 70 kg/yr of station-keeping
    # propellant each.  That makes it the smallest in-space market in the
    # table and the one most likely to saturate, which is the point of having
    # it: `earth_surface` is the destination where saturation is numerically
    # inert and 100% of rows run to the fleet ceiling, and nothing anchored
    # the other end.
    "geo":            40_000.0,
    "cislunar":      100_000.0,
    "lunar_surface":  50_000.0,
    # v1.8.0.  LARGER than the surface base it serves, which is the one row of
    # this table that does not fall off with distance.  A Mars-orbit depot is
    # transport infrastructure rather than a settlement: what it holds is the
    # propellant for descent, ascent and the trans-Earth stage, and in DRA 5.0
    # that is tens of tonnes per opportunity against a base's consumables.
    # 60 t/yr is ~128 t per 2.14-year synodic period, roughly one crewed
    # mission's in-space propellant, and still well under cislunar's 100 t.
    "mars_orbit":     60_000.0,
    "mars_surface":   20_000.0,
}


# ─── WHAT THE BUDGET IS SPENT ON  (v1.7.0) ───────────────────────────────────
# The comment above has said "all commodities competing for the same import
# budget" since v1.5.0, but the code handed EVERY commodity the full budget
# independently, so a Mars base that imports 20 t/yr would take 20 t of water
# AND 20 t of platinum AND 20 t of olivine.  That mattered little while the
# precious metals had zero in-space utility everywhere; it stopped being
# harmless the moment v1.7.0 gave them a non-zero utility at a settlement.
#
# Each commodity now gets a SHARE of the destination's annual import mass.
# Shares are per CLASS, and every commodity in a class can absorb the whole
# class share, because within a class they are substitutes; a base wanting
# shielding mass does not care whether it arrives as olivine or pyroxene.
# The four bulk classes partition the budget; the trace slice is additive and
# negligible.
#
# ⚠️  JUDGEMENT, like everything else in this block.  Anchored on what a
# propellant-and-construction outpost actually consumes by mass: propellant
# dominates, structure is next, shielding is bulky but occasional, and
# catalysts are measured in kilograms.
_DEMAND_SHARE_BY_CLASS: Dict[str, float] = {
    "propellant":  0.55,   # water; refuelling is most of any depot's tonnage
    "structural":  0.25,   # metals: pressure vessels, trusses, wire, motors
    "shielding":   0.15,   # bulk silicate: GCR/SPE mass, sintering feedstock
    "chemical":    0.05,   # carbon and organics: composites, agriculture
    "trace":       0.0005, # PGMs and Au/Ag: catalysis and contacts, kg-scale
}

_COMMODITY_CLASS: Dict[str, str] = {
    "water":           "propellant",
    "iron":            "structural", "nickel":       "structural",
    "cobalt":          "structural", "copper":       "structural",
    "nickel-iron":     "structural", "awaruite":     "structural",
    "magnetite":       "structural", "troilite":     "structural",
    "olivine":         "shielding",  "pyroxene":     "shielding",
    "orthopyroxene":   "shielding",  "enstatite":    "shielding",
    "plagioclase":     "shielding",  "spinel":       "shielding",
    "phyllosilicates": "shielding",  "oxides":       "shielding",
    "silicates":       "shielding",
    "carbon":          "chemical",   "organics":     "chemical",
    "platinum":        "trace",      "palladium":    "trace",
    "rhodium":         "trace",      "ruthenium":    "trace",
    "iridium":         "trace",      "osmium":       "trace",
    "gold":            "trace",      "silver":       "trace",
    # v1.7.1: the PGM ORE MINERALS, which were missing.  They are the same
    # metals as the eight rows above; sperrylite is PtAs2, laurite is RuS2,
    # native-pgm is the alloy, so "trace" is the only class they can be in.
    # Absent, they fell through the `.get(..., "shielding")` default below and
    # would have been handed **0.15 of a depot's entire import budget** rather
    # than 0.0005: 75,000 kg/yr at LEO against 250, a factor of 300.
    "sperrylite":      "trace",      "laurite":      "trace",
    "native-pgm":      "trace",
}

# The bulk classes must partition the budget, or the "one import budget"
# framing is a fiction again.  Asserted rather than commented, because the
# failure mode this replaces was exactly a comment that outlived its code.
assert abs(sum(v for k, v in _DEMAND_SHARE_BY_CLASS.items() if k != "trace")
           - 1.0) < 1e-9, "bulk demand shares must sum to 1.0"


def annual_market_kg(
    name: str, destination: str, route: Optional[str] = None,
) -> float:
    """Annual absorbable quantity for `name` at `destination`, in kg/yr.

    `route` is the value_route from in_space_price_usd_per_kg.  It matters
    because THE MARKET THAT SATURATES IS THE ONE YOU ACTUALLY SELL INTO.  A
    commodity with no in-space demand is flown down and sold on Earth, so it
    is bounded by terrestrial annual production, not by a depot's import
    budget; before v1.7.0 platinum at LEO was capped at the depot's 500 t/yr
    when the real constraint is the world's 180 t/yr.

    Passing route=None keeps the in-space ceiling, which is what a caller with
    no routing information should assume at an in-space destination.
    """
    dest = str(destination or "").strip().lower()
    terrestrial = ANNUAL_WORLD_PRODUCTION_KG.get(str(name), _UNLIMITED_MARKET_KG)
    if dest not in IN_SPACE_ANNUAL_DEMAND_KG:
        return terrestrial
    if route == "shipped to Earth":
        return terrestrial
    share = _DEMAND_SHARE_BY_CLASS.get(
        _COMMODITY_CLASS.get(str(name), "shielding"), _DEMAND_SHARE_BY_CLASS["trace"]
    )
    return IN_SPACE_ANNUAL_DEMAND_KG[dest] * share


# ─── IN-SPACE MANUFACTURING  (v1.6.0) ────────────────────────────────────────
# Raw asteroid metal is not a pressure vessel.  Until now the gap between
# "kilogram of Fe-Ni at a depot" and "kilogram of usable structure" was hidden
# inside the 0.70 utility factor, which meant the refining and forming plant
# was assumed into existence and never costed.  It is now explicit and
# derived, so the utility factor means only what it says: how good a
# substitute the finished article is for one launched from Earth.
#
# Two costs, both from Module 3 rates:
#
#   ENERGY   kWh per kg of feedstock, times the capital cost of a Watt in
#            space.  A $800/W-EOL solar train delivering power for 15 years
#            supplies 15 × 8,766 = 131,490 Wh per installed Watt, so energy
#            costs $800 / 131,490 = $0.0061/Wh ≈ $6.08/kWh, roughly 100×
#            terrestrial industrial power, which is the whole reason in-space
#            processing is not obviously free.
#
#   PLANT    $300k/kg of deep-space hardware, at 100 kg/yr of throughput per
#            kg of plant over a 15-year life ⇒ 1,500 kg processed per kg of
#            plant ⇒ $300,000 / 1,500 = $200 per kg processed.
_INSPACE_POWER_USD_PER_W        = 800.0     # Module 3 "Power system (solar + battery)"
_INSPACE_PLANT_LIFE_YR          = 15.0
_INSPACE_PLANT_USD_PER_KG       = 300_000.0 # Module 3 "Mining payload recurring cost"
_INSPACE_PLANT_THROUGHPUT_KG_YR = 100.0     # Module 3 "In-space processing plant throughput"

# Energy to turn raw feedstock into something usable, kWh per kg.
#   water       filtration and phase change only; already nearly a product
#   metals      reduction + melting + forming.  Terrestrial electric-arc /
#               direct-reduction steelmaking runs 4-5 kWh/kg; electrowinning
#               iron is similar.  No carbothermic shortcut in space.
#   silicates   sintering for shielding blocks or print feedstock
#   carbon      pyrolysis / compounding
IN_SPACE_PROCESSING_KWH_PER_KG: Dict[str, float] = {
    "water":            0.5,
    "iron":             5.0,  "nickel":     5.0,  "cobalt": 5.0,  "copper": 5.0,
    "nickel-iron":      5.0,  "awaruite":   5.0,
    "magnetite":        7.0,  # oxide, reduction first
    "troilite":         4.0,
    "olivine":          1.0, "pyroxene":       1.0, "orthopyroxene": 1.0,
    "enstatite":        1.0, "plagioclase":    1.0, "spinel":        1.0,
    "phyllosilicates":  1.0, "oxides":         1.0, "silicates":     1.0,
    "carbon":           2.0,
    "organics":         2.0,
}


def in_space_energy_usd_per_kwh() -> float:
    """Capital cost of a kilowatt-hour delivered in deep space."""
    wh_per_installed_w = _INSPACE_PLANT_LIFE_YR * 365.25 * 24.0
    return _INSPACE_POWER_USD_PER_W / wh_per_installed_w * 1000.0


def in_space_processing_cost_usd_per_kg(name: str) -> float:
    """Cost of refining 1 kg of raw feedstock into a usable in-space product.

    Energy at the in-space capital rate, plus the amortised refinery.  Zero
    for anything with no listed process; the caller then treats it as sold
    as-is, which is the conservative reading.
    """
    kwh = IN_SPACE_PROCESSING_KWH_PER_KG.get(str(name))
    if kwh is None:
        return 0.0
    energy = kwh * in_space_energy_usd_per_kwh()
    plant  = (_INSPACE_PLANT_USD_PER_KG
              / (_INSPACE_PLANT_THROUGHPUT_KG_YR * _INSPACE_PLANT_LIFE_YR))
    return energy + plant


def value_for_destination(destination: str) -> dict:
    """Look up the delivered-value basis for a delivery destination.

    Unknown destinations fall back to earth_surface, the conservative
    choice, rather than silently keeping an in-space premium.
    """
    key = str(destination or "").strip().lower()
    if key not in DELIVERY_DESTINATIONS:
        print(f"     WARN   Unknown delivery_destination {destination!r} - "
              f"falling back to 'earth_surface'.  Valid: "
              f"{', '.join(sorted(DELIVERY_DESTINATIONS))}")
        key = "earth_surface"
    return DELIVERY_DESTINATIONS[key]


def in_space_price_usd_per_kg(
    name: str, destination: str, terrestrial_usd_per_kg: Optional[float],
) -> Optional[Tuple[float, str]]:
    """Value of 1 kg of `name` sitting at `destination`, and how it is realised.

    Returns (usd_per_kg, route), or None at earth_surface, where the
    terrestrial price already stands.

    A kilogram at a depot has two possible fates, and it is worth the better
    of them:

      USE IT IN SPACE.  Worth what an equivalent kilogram delivered from Earth
        would have cost: its purchase price PLUS the launch bill.  Note the
        PLUS, v1.3.0 replaced the terrestrial price with the launch cost,
        which quietly threw the material itself away.  Scaled by
        `in_space_utility`, which is how good a substitute it actually is for
        the launched article.  Only available where demand exists (utility>0).

      SHIP IT DOWN.  Worth the terrestrial price less the cost of the onward
        leg to the surface.  Always available, and it is what puts a real,
        non-zero number on platinum at a depot: nobody in orbit wants
        platinum, but it is still platinum.

    Floored at zero, material too cheap to be worth the freight is worth
    nothing, not a negative.
    """
    dest = value_for_destination(destination)
    if dest["dv_above_leo_m_s"] is None or dest["usd_per_kg"] <= 0.0:
        return None                                   # earth_surface

    terrestrial = float(terrestrial_usd_per_kg or 0.0)
    utility     = in_space_utility(name, destination)

    # v1.6.0: selling into the in-space market means delivering a usable
    # product, not raw rock, so the refinery comes out of the price.
    use_in_space = (terrestrial + utility * dest["usd_per_kg"]
                    - in_space_processing_cost_usd_per_kg(name)
                    if utility > 0 else None)
    ship_to_earth = terrestrial - downleg_cost_usd_per_kg(destination)

    if use_in_space is not None and use_in_space >= ship_to_earth:
        return max(0.0, use_in_space), "used in space"
    return max(0.0, ship_to_earth), "shipped to Earth"


MINERAL_REFERENCE: List[dict] = [

    # ══════════════════════════════════════════════════════════════════════
    # ELEMENTS  (tradable commodities, with live-price tickers where available)
    # ══════════════════════════════════════════════════════════════════════

    {   # ── Iron ─────────────────────────────────────────────────────────
        "name":                  "iron",
        "kind":                  "element",
        "formula":               "Fe",
        "density_gcm3":          7.874,
        "yfinance_ticker":       None,           # iron ore (TIO=F) is CNY/MT, skip
        "yfinance_unit":         None,
        "metals_dev_key":        None,
        "ref_price_usd_per_kg":  0.50,           # steel scrap / refined iron metal
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Priced as refined steel scrap (Q1 2026 mid-range "
                                 "$343/MT US, $400/MT global — $0.34-0.50/kg).  "
                                 "Asteroid mining produces refined iron from "
                                 "nickel-iron alloy, NOT iron ore — so the "
                                 "relevant sale price is steel scrap / refined "
                                 "metal, not the $0.10/kg iron-ore benchmark.",
    },
    {   # ── Nickel ───────────────────────────────────────────────────────
        "name":                  "nickel",
        "kind":                  "element",
        "formula":               "Ni",
        "density_gcm3":          8.908,
        "yfinance_ticker":       None,           # LME, not on yfinance
        "yfinance_unit":         None,
        "metals_dev_key":        "nickel",
        "ref_price_usd_per_kg":  16.50,          # LME nickel ~$16 500/tonne
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "LME 3-month nickel.",
    },
    {   # ── Cobalt ───────────────────────────────────────────────────────
        "name":                  "cobalt",
        "kind":                  "element",
        "formula":               "Co",
        "density_gcm3":          8.86,
        "yfinance_ticker":       None,
        "yfinance_unit":         None,
        "metals_dev_key":        "cobalt",
        "ref_price_usd_per_kg":  33.00,          # LME cobalt ~$33 000/tonne
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "LME cobalt cash; trace constituent of FeNi alloys.",
    },
    {   # ── Copper ───────────────────────────────────────────────────────
        "name":                  "copper",
        "kind":                  "element",
        "formula":               "Cu",
        "density_gcm3":          8.96,
        "yfinance_ticker":       "HG=F",         # COMEX copper, USD / lb
        "yfinance_unit":         "lb",
        "metals_dev_key":        "copper",
        "ref_price_usd_per_kg":  8.80,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "COMEX copper front-month.",
    },
    {   # ── Gold ─────────────────────────────────────────────────────────
        "name":                  "gold",
        "kind":                  "element",
        "formula":               "Au",
        "density_gcm3":          19.32,
        "yfinance_ticker":       "GC=F",         # COMEX gold, USD / troy oz
        "yfinance_unit":         "troy_oz",
        "metals_dev_key":        "gold",
        "ref_price_usd_per_kg":  150_000.0,      # ~$4,700/oz (May 2026)
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "COMEX gold front-month.  Reference $150k/kg = "
                                 "~$4,700/oz; gold ran from $3,335 (May 2025) to "
                                 "$4,732 (May 2026) per Reuters analyst consensus.",
    },
    {   # ── Silver ───────────────────────────────────────────────────────
        "name":                  "silver",
        "kind":                  "element",
        "formula":               "Ag",
        "density_gcm3":          10.49,
        "yfinance_ticker":       "SI=F",         # COMEX silver, USD / troy oz
        "yfinance_unit":         "troy_oz",
        "metals_dev_key":        "silver",
        "ref_price_usd_per_kg":  950.0,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "COMEX silver front-month.",
    },
    {   # ── Platinum ─────────────────────────────────────────────────────
        "name":                  "platinum",
        "kind":                  "element",
        "formula":               "Pt",
        "density_gcm3":          21.45,
        "yfinance_ticker":       "PL=F",         # NYMEX platinum, USD / troy oz
        "yfinance_unit":         "troy_oz",
        "metals_dev_key":        "platinum",
        "ref_price_usd_per_kg":  45_000.0,       # ~$1,400/oz (Heraeus 2026 mid)
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "NYMEX platinum front-month.  Reference $45k/kg = "
                                 "$1,400/oz, mid of Heraeus 2026 forecast "
                                 "$1,300-$1,800/oz.",
    },
    {   # ── Palladium ────────────────────────────────────────────────────
        "name":                  "palladium",
        "kind":                  "element",
        "formula":               "Pd",
        "density_gcm3":          12.02,
        "yfinance_ticker":       "PA=F",         # NYMEX palladium, USD / troy oz
        "yfinance_unit":         "troy_oz",
        "metals_dev_key":        "palladium",
        "ref_price_usd_per_kg":  48_000.0,       # ~$1,495/oz (May 8 2026 LBMA)
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "NYMEX palladium front-month.  Reference $48k/kg = "
                                 "$1,495/oz spot (May 2026, LBMA via lppm.com).",
    },
    {   # ── Rhodium ──────────────────────────────────────────────────────
        "name":                  "rhodium",
        "kind":                  "element",
        "formula":               "Rh",
        "density_gcm3":          12.41,
        "yfinance_ticker":       None,           # no liquid futures market
        "yfinance_unit":         None,
        "metals_dev_key":        "rhodium",
        "ref_price_usd_per_kg":  320_000.0,      # ~$9,950/oz (May 2026 LBMA)
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "OTC quote (Johnson Matthey / LBMA).  Reference "
                                 "$320k/kg = $9,950/oz (May 8 2026 spot).  "
                                 "Trace PGM in M-type / iron-meteorite analogues.",
    },
    {   # ── Iridium ──────────────────────────────────────────────────────
        "name":                  "iridium",
        "kind":                  "element",
        "formula":               "Ir",
        "density_gcm3":          22.56,
        "yfinance_ticker":       None,
        "yfinance_unit":         None,
        "metals_dev_key":        "iridium",
        "ref_price_usd_per_kg":  160_000.0,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "OTC quote.  Trace PGM in iron-meteorite analogues.",
    },
    {   # ── Ruthenium ────────────────────────────────────────────────────
        "name":                  "ruthenium",
        "kind":                  "element",
        "formula":               "Ru",
        "density_gcm3":          12.45,
        "yfinance_ticker":       None,
        "yfinance_unit":         None,
        "metals_dev_key":        "ruthenium",
        "ref_price_usd_per_kg":  16_000.0,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "OTC quote.  Trace PGM.",
    },
    {   # ── Osmium ───────────────────────────────────────────────────────
        "name":                  "osmium",
        "kind":                  "element",
        "formula":               "Os",
        "density_gcm3":          22.59,
        "yfinance_ticker":       None,
        "yfinance_unit":         None,
        "metals_dev_key":        None,           # not on metals.dev
        "ref_price_usd_per_kg":  13_000.0,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Specialty quote; very illiquid.",
    },
    {   # ── Water (the most valuable in-space resource) ───────────────────
        "name":                  "water",
        "kind":                  "element",
        "formula":               "H2O",
        "density_gcm3":          1.00,
        "yfinance_ticker":       None,
        "yfinance_unit":         None,
        "metals_dev_key":        None,
        # This is the TERRESTRIAL price, bulk industrial water, what a
        # kilogram of it is worth once landed.  At an in-space destination
        # apply_delivery_destination() overwrites it with the launch cost
        # avoided; see DELIVERY_DESTINATIONS and IN_SPACE_UTILITY above.
        # Keeping the conservative earth_surface figure here means a bypassed
        # resolver under-values water rather than over-values it.
        "ref_price_usd_per_kg":  0.001,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Price depends entirely on where the water is SOLD, "
                                 "not on the asteroid — see DELIVERY_DESTINATIONS. "
                                 "Set MINERAL_CONFIG.delivery_destination to 'leo' or "
                                 "'cislunar' to price it as launch cost avoided; the "
                                 "default 'earth_surface' prices it as what it is once "
                                 "landed, which is bulk industrial water.",
    },

    # ══════════════════════════════════════════════════════════════════════
    # MINERALS  (rock-forming compounds, priced via elemental yield)
    # ══════════════════════════════════════════════════════════════════════
    # `yields` maps mineral → {element_name: mass-fraction}.  Module 3 will
    # use these to break a mineral mass back into its tradable element masses.

    {   # ── Nickel-iron alloy ─────────────────────────────────────────────
        # Typical iron-meteorite analogue: ~90 % Fe, ~9 % Ni, ~0.5 % Co,
        # plus PGM trace abundances drawn from average chondritic / iron-
        # meteorite compositions (Lodders 2003, Walker 2012).
        "name":                  "nickel-iron",
        "kind":                  "mineral",
        "formula":               "FeNi",
        "density_gcm3":          7.90,
        "yfinance_ticker":       None,
        "yfinance_unit":         None,
        "metals_dev_key":        None,
        "ref_price_usd_per_kg":  None,           # priced via yields, not directly
        "ref_price_date":        None,
        "yields": {
            # Bulk metals, typical IIIAB iron-meteorite Fe-Ni alloy.
            "iron":      0.900,    # ~90 wt% Fe
            "nickel":    0.090,    # 7-10 wt% Ni in IIIAB octahedrites
            "cobalt":    0.005,
            # Platinum-group metals (PGMs).  Siderites average ~30 ppm total
            # PGM (per USGS Bulletin 1214 / Nichiporuk 1965).  Distribution
            # below sums to ~37 ppm total + 1 ppm Au, calibrated to IIIAB
            # medium-octahedrite means.  Ir bumped from 2→4 ppm (range cited
            # at 0.01-19 ppm).  Ru + Os added (were missing in v1.1.0-1.1.1),
            # both concentrate in the metallic phase and are present at
            # 1-5 ppm in nearly every iron meteorite group.
            "platinum":  1.5e-5,   # 15 ppm   (Pt is the dominant PGM)
            "palladium": 1.0e-5,   # 10 ppm
            "ruthenium": 3.0e-6,   #  3 ppm   ★ NEW v1.1.2
            "iridium":   4.0e-6,   #  4 ppm   ↑ from 2 ppm
            "osmium":    2.0e-6,   #  2 ppm   ★ NEW v1.1.2
            "rhodium":   1.5e-6,   #  1.5 ppm  ↓ from 2 (rebalanced for sum)
            "gold":      1.0e-6,   #  1 ppm
        },
        "notes":                 "Iron-meteorite analogue (IIIAB octahedrite mean) — "
                                 "Fe + Ni + trace PGMs + Au.  Total PGM ≈ 37 ppm matches "
                                 "siderite literature.  Yields cover all 6 PGMs as of v1.1.2.",
    },
    {   # ── Magnetite ────────────────────────────────────────────────────
        "name":                  "magnetite",
        "kind":                  "mineral",
        "formula":               "Fe3O4",
        "density_gcm3":          5.17,
        "yields": {"iron": 0.724},   # stoichiometric Fe in Fe3O4
        "ref_price_usd_per_kg":  None,
        "ref_price_date":        None,
        "notes":                 "Iron-oxide ore; priced as Fe content.",
    },
    {   # ── Troilite ─────────────────────────────────────────────────────
        "name":                  "troilite",
        "kind":                  "mineral",
        "formula":               "FeS",
        "density_gcm3":          4.61,
        "yields": {"iron": 0.635},   # stoichiometric Fe in FeS
        "ref_price_usd_per_kg":  None,
        "ref_price_date":        None,
        "notes":                 "Iron sulfide; sulfur ignored (low value).",
    },

    # ══════════════════════════════════════════════════════════════════════
    # RARE-MINERAL PHASES  (v1.1.3, added for PGM-rich inclusions)
    # ══════════════════════════════════════════════════════════════════════
    # These minerals are NOT referenced by Module 1's TAXONOMY_COMPOSITION
    # (which uses "nickel-iron" as the bulk metal carrier).  They are
    # available as targets for user-supplied per-asteroid composition
    # overrides or future spectral-identification work.  Each is a real
    # PGM-bearing phase documented in iron meteorites, chondrites, or
    # ureilites; see references in each row's `notes`.

    {   # ── Sperrylite ────────────────────────────────────────────────────
        # Pt arsenide, the dominant terrestrial Pt ore (Sudbury, Stillwater).
        # Documented in chondritic and iron-meteorite matrix as tiny grains.
        # Atomic masses: Pt 195.08, As 74.92 → Pt mass-fraction = 0.566.
        "name":                  "sperrylite",
        "kind":                  "mineral",
        "formula":               "PtAs2",
        "density_gcm3":          10.6,
        "yields": {"platinum": 0.566},
        "ref_price_usd_per_kg":  None,
        "ref_price_date":        None,
        "notes":                 "Pt arsenide (Pt 56.6 wt%) — dominant terrestrial "
                                 "Pt ore.  Documented in some iron meteorites and "
                                 "in Sudbury impact-melt-class material.  Arsenic "
                                 "is toxic but recoverable; ignored in valuation.",
    },
    {   # ── Laurite ──────────────────────────────────────────────────────
        # Ru sulfide.  Atomic masses: Ru 101.07, S 32.07 → Ru mass-fraction = 0.612.
        # May contain trace Os, Ir as substitutions in real samples.
        "name":                  "laurite",
        "kind":                  "mineral",
        "formula":               "RuS2",
        "density_gcm3":          6.99,
        "yields": {"ruthenium": 0.612, "iridium": 1e-3, "osmium": 1e-3},
        "ref_price_usd_per_kg":  None,
        "ref_price_date":        None,
        "notes":                 "Ru sulfide (Ru 61.2 wt%) with trace Ir / Os "
                                 "substitution.  Found in PGM-bearing chromites "
                                 "and rare iron-meteorite phases.",
    },
    {   # ── Awaruite (PGM-enriched Ni-Fe alloy) ──────────────────────────
        # Naturally-occurring Ni-rich Fe-Ni alloy, distinct from the bulk
        # kamacite/taenite of iron meteorites.  Atomic masses: Ni 58.69 ×3
        # + Fe 55.85 → Ni mass-fraction = 0.759, Fe = 0.241.
        # In terrestrial ophiolites (Josephine, Mojave) awaruite hosts
        # PGMs at 10-100× chondritic, used here as a PGM-enriched analog
        # for asteroid-mining targets that show specific spectral indicators.
        "name":                  "awaruite",
        "kind":                  "mineral",
        "formula":               "Ni3Fe",
        "density_gcm3":          8.10,
        "yields": {
            "nickel":    0.759,
            "iron":      0.241,
            # PGMs concentrated ~5× the nickel-iron baseline yields
            "platinum":  7.5e-5,    # 75 ppm
            "palladium": 5.0e-5,    # 50 ppm
            "iridium":   2.0e-5,    # 20 ppm
            "ruthenium": 1.5e-5,    # 15 ppm
            "osmium":    1.0e-5,    # 10 ppm
            "rhodium":   7.5e-6,    # 7.5 ppm
            "gold":      5.0e-6,    # 5 ppm
        },
        "ref_price_usd_per_kg":  None,
        "ref_price_date":        None,
        "notes":                 "Ni-rich Fe-Ni alloy (Ni 75.9 wt%, Fe 24.1 wt%) with "
                                 "concentrated PGMs (5× nickel-iron baseline).  "
                                 "Terrestrial analog: Josephine / Mojave ophiolites.  "
                                 "Documented in some ureilites and rare meteoritic "
                                 "phases.  Use as a high-grade target where spectral "
                                 "data suggests PGM enrichment beyond bulk Fe-Ni.",
    },
    {   # ── Native PGM ───────────────────────────────────────────────────
        # Generic native platinum-group alloy (Pt-dominant with Pd / Ir /
        # Os / Ru / Rh).  Composition midpoint of placer-class native
        # platinum compositions; iridosmine end-members would be higher Ir/Os.
        # Documented in ureilites and rare iron-meteorite nuggets.
        "name":                  "native-pgm",
        "kind":                  "mineral",
        "formula":               "(Pt,Pd,Ir,Os,Ru,Rh)",
        "density_gcm3":          18.0,            # midpoint of Pt(21.5) and Pd(12)
        "yields": {
            "platinum":  0.70,
            "palladium": 0.15,
            "iridium":   0.08,
            "osmium":    0.05,
            "ruthenium": 0.01,
            "rhodium":   0.01,
        },
        "ref_price_usd_per_kg":  None,
        "ref_price_date":        None,
        "notes":                 "Mixed native PGM alloy (Pt 70 wt%, Pd 15, Ir 8, "
                                 "Os 5, Ru 1, Rh 1).  Implied value ≈ $55k/kg — "
                                 "by far the richest mineral phase in the catalog.  "
                                 "Extremely rare; documented as nuggets in some "
                                 "ureilites, rare iron meteorites, and Os-Ir-Ru "
                                 "alloys.  Reserved for high-confidence per-asteroid "
                                 "override use cases.",
    },
    {   # ── Olivine ──────────────────────────────────────────────────────
        "name":                  "olivine",
        "kind":                  "mineral",
        "formula":               "(Mg,Fe)2SiO4",
        "density_gcm3":          3.32,           # forsterite-fayalite midpoint
        "yields": {"iron": 0.10},                # Fo90 mean Fe content
        "ref_price_usd_per_kg":  0.05,           # industrial olivine sand
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Mg-Fe silicate.  Fa10 mean; bulk industrial use only.",
    },
    {   # ── Pyroxene ─────────────────────────────────────────────────────
        "name":                  "pyroxene",
        "kind":                  "mineral",
        "formula":               "(Mg,Fe,Ca)Si2O6",
        "density_gcm3":          3.40,
        "yields": {"iron": 0.07},
        "ref_price_usd_per_kg":  0.05,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Mg-Fe-Ca chain silicate.",
    },
    {   # ── Orthopyroxene ────────────────────────────────────────────────
        "name":                  "orthopyroxene",
        "kind":                  "mineral",
        "formula":               "(Mg,Fe)2Si2O6",
        "density_gcm3":          3.30,
        "yields": {"iron": 0.07},
        "ref_price_usd_per_kg":  0.05,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Mg-Fe end of the pyroxene series.",
    },
    {   # ── Enstatite ────────────────────────────────────────────────────
        "name":                  "enstatite",
        "kind":                  "mineral",
        "formula":               "MgSiO3",
        "density_gcm3":          3.20,
        "yields": {},                              # Mg/Si silicate, no traded yield
        "ref_price_usd_per_kg":  0.05,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Mg-pyroxene end-member; E-chondrite analogue.",
    },
    {   # ── Plagioclase ──────────────────────────────────────────────────
        "name":                  "plagioclase",
        "kind":                  "mineral",
        "formula":               "(Na,Ca)(Al,Si)4O8",
        "density_gcm3":          2.69,
        "yields": {},
        "ref_price_usd_per_kg":  0.10,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Feldspar group; basaltic-crust marker.",
    },
    {   # ── Spinel ───────────────────────────────────────────────────────
        "name":                  "spinel",
        "kind":                  "mineral",
        "formula":               "MgAl2O4",
        "density_gcm3":          3.64,
        "yields": {},
        "ref_price_usd_per_kg":  0.50,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Mg-Al oxide; high-T refractory.",
    },
    {   # ── Phyllosilicates ──────────────────────────────────────────────
        "name":                  "phyllosilicates",
        "kind":                  "mineral",
        "formula":               "(varies)",
        "density_gcm3":          2.60,
        "yields": {"water": 0.10},               # CM2-class bound-water content
        "ref_price_usd_per_kg":  0.05,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Hydrated clays; valued for releasable bound water.",
    },
    {   # ── Oxides (generic) ─────────────────────────────────────────────
        "name":                  "oxides",
        "kind":                  "mineral",
        "formula":               "(varies)",
        "density_gcm3":          4.00,
        "yields": {"iron": 0.50},
        "ref_price_usd_per_kg":  0.10,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Generic metal-oxide bulk.",
    },
    {   # ── Silicates (generic) ──────────────────────────────────────────
        "name":                  "silicates",
        "kind":                  "mineral",
        "formula":               "(varies)",
        "density_gcm3":          2.80,
        "yields": {},
        "ref_price_usd_per_kg":  0.05,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Catch-all rock-forming silicate bulk.",
    },
    {   # ── Carbon (amorphous / graphitic) ───────────────────────────────
        "name":                  "carbon",
        "kind":                  "mineral",
        "formula":               "C",
        "density_gcm3":          2.10,
        "yields": {},
        "ref_price_usd_per_kg":  0.20,           # bulk industrial carbon black
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Amorphous / graphitic carbon (not gem diamond).",
    },
    {   # ── Organics ─────────────────────────────────────────────────────
        "name":                  "organics",
        "kind":                  "mineral",
        "formula":               "(varies)",
        "density_gcm3":          1.20,
        "yields": {},
        "ref_price_usd_per_kg":  0.50,
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Complex organic macromolecules (kerogen-like).",
    },
]

print(f"OK  Reference table ready - {len(MINERAL_REFERENCE)} entries "
      f"({sum(1 for r in MINERAL_REFERENCE if r['kind'] == 'element')} elements / "
      f"{sum(1 for r in MINERAL_REFERENCE if r['kind'] == 'mineral')} minerals)")


# ─── EVERY COMMODITY MUST BE CLASSIFIED  (v1.7.1) ────────────────────────────
# `annual_market_kg` reads the demand class through
# `_COMMODITY_CLASS.get(name, "shielding")`, and an unrecognised name therefore
# gets 15% of a destination's whole import budget without anyone deciding that.
# Three PGM ore minerals had been doing exactly that since v1.7.0; inertly,
# because their in-space utility is 0 at every destination so the class is
# never read, which is precisely why nobody noticed.  CLAUDE.md's own lesson
# from the RTG branch applies: **an unreachable branch is not a verified
# branch**, and the settlement-catalyst market that would make it reachable is
# recorded there as considered-and-rejected rather than impossible.
#
# Asserted rather than commented, for the same reason the share table above is:
# the failure this replaces was a silent default, and a default that is only
# correct by accident is the quiet-wrong-answer shape this project keeps
# finding.  Adding a commodity now fails loudly at import until it is placed.
_UNCLASSIFIED = sorted(
    {str(r["name"]) for r in MINERAL_REFERENCE} - set(_COMMODITY_CLASS)
)
assert not _UNCLASSIFIED, (
    "every MINERAL_REFERENCE commodity needs a _COMMODITY_CLASS entry, or it "
    f"silently takes the 'shielding' share of every in-space import budget: "
    f"{_UNCLASSIFIED}"
)


# ─────────────────────────────────────────────────────────────────────────────
# YFINANCE FETCHER  (primary live-price source)
# ─────────────────────────────────────────────────────────────────────────────
# Yahoo Finance front-month futures, fetched via the `yfinance` Python lib.
# Returns one row per element with a `yfinance_ticker`; everything else is
# omitted and falls through to the metals.dev / reference table sources.

def fetch_yfinance(config: MineralValueConfig) -> pd.DataFrame:
    """
    Live commodity prices from Yahoo Finance.

    For each entry in MINERAL_REFERENCE with a non-null `yfinance_ticker`,
    download the most recent close price and normalise to USD/kg using the
    entry's `yfinance_unit`.  Returns an empty DataFrame if yfinance fails
    entirely; individual tickers that fail are logged but don't abort.
    """
    print("\n  yfinance  (Yahoo Finance) - fetching live futures ...")

    try:
        import yfinance as yf
    except ImportError:
        print("     FAIL  yfinance not importable - skipped")
        return pd.DataFrame()

    rows = []
    for entry in MINERAL_REFERENCE:
        ticker = entry.get("yfinance_ticker")
        if not ticker:
            continue

        try:
            # `period="5d"` is short enough to be fast yet long enough to
            # survive a single missing close (weekends, holidays).  Take
            # the most recent non-NaN close.
            hist = yf.Ticker(ticker).history(period="5d", auto_adjust=False)
            closes = hist["Close"].dropna() if "Close" in hist else pd.Series(dtype=float)
            if closes.empty:
                print(f"     WARN  {entry['name']:11s} ({ticker}) - no close data")
                continue

            last_close = float(closes.iloc[-1])
            last_date  = closes.index[-1].strftime("%Y-%m-%d")

            unit = entry.get("yfinance_unit")
            if unit == "troy_oz":
                price_kg = _per_troy_oz_to_per_kg(last_close)
            elif unit == "lb":
                price_kg = _per_lb_to_per_kg(last_close)
            elif unit == "tonne":
                price_kg = _per_tonne_to_per_kg(last_close)
            else:
                print(f"     WARN  {entry['name']:11s} ({ticker}) - unknown unit {unit!r}")
                continue

            rows.append({
                "name":              entry["name"],
                "live_price_usd_per_kg": price_kg,
                "live_price_date":   last_date,
                "live_price_source": f"yfinance:{ticker}",
            })
            print(f"     OK  {entry['name']:11s} ({ticker}) "
                  f"= {last_close:>10,.2f} USD/{unit:7s} "
                  f"-> {price_kg:>12,.2f} USD/kg  [{last_date}]")

        except Exception as exc:
            print(f"     FAIL  {entry['name']:11s} ({ticker}) - {type(exc).__name__}: {exc}")

    if not rows:
        print("     WARN  yfinance returned no usable rows")
        return pd.DataFrame()

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# METALS.DEV FETCHER  (optional, secondary)
# ─────────────────────────────────────────────────────────────────────────────
# Free tier of metals.dev returns gold/silver/platinum/palladium + the base
# LME metals in a single JSON call.  Quotes in USD per troy ounce; we
# convert to USD/kg here.  Only runs when the user has supplied a real key.

def fetch_metals_dev(config: MineralValueConfig) -> pd.DataFrame:
    """
    Live metal prices from metals.dev (https://metals.dev).

    Skipped silently if the user hasn't replaced the DEMO key with a real
    one; the demo endpoint is too rate-limited to be useful for a pipeline.
    Returns an empty DataFrame on any HTTP / parse failure.
    """
    if config.metals_api_key == "DEMO" or not config.metals_api_key:
        print("\n  metals.dev - skipped (no API key set; edit MINERAL_CONFIG.metals_api_key)")
        return pd.DataFrame()

    print("\n  metals.dev - fetching live LME / spot prices ...")

    try:
        r = requests.get(
            config.metals_api_url,
            params={
                "api_key":  config.metals_api_key,
                "currency": "USD",
                "unit":     "toz",
            },
            timeout=config.request_timeout,
        )
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:
        print(f"     FAIL  metals.dev failed: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    quotes = payload.get("metals") or payload.get("rates") or {}
    if not quotes:
        print("     WARN  metals.dev returned no `metals` payload")
        return pd.DataFrame()

    date = payload.get("date") or payload.get("timestamp_iso") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    rows = []
    for entry in MINERAL_REFERENCE:
        key = entry.get("metals_dev_key")
        if not key or key not in quotes:
            continue

        try:
            usd_per_toz = float(quotes[key])
            price_kg    = _per_troy_oz_to_per_kg(usd_per_toz)
        except (TypeError, ValueError):
            continue

        rows.append({
            "name":              entry["name"],
            "live_price_usd_per_kg": price_kg,
            "live_price_date":   str(date)[:10],
            "live_price_source": f"metals.dev:{key}",
        })
        print(f"     OK  {entry['name']:11s} = {usd_per_toz:>10,.2f} USD/troy_oz "
              f"-> {price_kg:>12,.2f} USD/kg")

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# REFERENCE-TABLE FETCHER  (always-on fallback)
# ─────────────────────────────────────────────────────────────────────────────
# Materialises MINERAL_REFERENCE into a DataFrame.  Doesn't hit the network,
# so it always succeeds; downstream merge uses it to fill the gaps left by
# the live sources.

def fetch_reference_table(config: MineralValueConfig) -> pd.DataFrame:
    """Static USGS / LME / mineralogy reference data, always available."""
    print("\n  Reference table - loading curated prices + densities ...")

    # Every row here carries its TERRESTRIAL price.  The in-space repricing is
    # applied once, uniformly, after the merge; see apply_delivery_destination,
    # because it has to override live quotes too (platinum's LME price is
    # not what platinum is worth at a cislunar depot).
    rows = []
    for entry in MINERAL_REFERENCE:
        is_water   = entry["name"] == "water"
        ref_price  = (_EARTH_SURFACE_WATER_USD_PER_KG if is_water
                      else entry.get("ref_price_usd_per_kg"))
        value_basis = "terrestrial market price"
        notes      = entry.get("notes", "")
        rows.append({
            "name":                 entry["name"],
            "kind":                 entry["kind"],
            "formula":              entry["formula"],
            "density_gcm3":         entry["density_gcm3"],
            "ref_price_usd_per_kg":     ref_price,
            "ref_price_date":       entry.get("ref_price_date"),
            "ref_price_source":     "USGS/LME/mineralogy reference",
            "value_basis":          value_basis,
            "notes":                notes,
            "yields_json":          json.dumps(entry.get("yields", {})),
        })

    df = pd.DataFrame(rows)
    print(f"     OK  {len(df)} reference rows loaded")
    return df


def apply_delivery_destination(
    catalog: pd.DataFrame, config: MineralValueConfig,
) -> pd.DataFrame:
    """Reprice the whole catalog for the configured delivery destination.

    At `earth_surface` this is a no-op: every commodity keeps the terrestrial
    price the sources supplied.

    At an in-space destination every commodity is revalued to the better of
    its two fates, used in space, or shipped down to the terrestrial market.
    See in_space_price_usd_per_kg for the rule.  Two consequences worth being
    explicit about, because they are the whole point of the field:

      • Bulk material becomes enormously more valuable.  Iron is worth $0.50/kg
        on Earth and ~$2,978/kg in LEO, because a kilogram of structural metal
        already in orbit is a kilogram nobody has to launch.
      • Precious metals lose their in-space premium but keep their value.
        Nobody in orbit wants platinum, so it is priced by shipping it down:
        terrestrial price less the downleg.  ~$31,700/kg in LEO against
        $57,074 on the ground, a real discount, not a wipeout.

    Applied after merge_mineral_sources so it overrides live quotes as well as
    reference ones.
    """
    dest_key = str(config.delivery_destination or "").strip().lower()
    dest     = value_for_destination(dest_key)
    if dest["usd_per_kg"] <= 0.0:
        print(f"\n  Delivery destination '{dest_key}' - terrestrial prices stand.")
        return catalog

    downleg = downleg_cost_usd_per_kg(dest_key)
    print(f"\n   Repricing for delivery to '{dest_key}' ...")
    print(f"     Launch cost avoided : ${dest['usd_per_kg']:,.0f}/kg  ({dest['basis']})")
    print(f"     Downleg to surface  : ${downleg:,.0f}/kg  "
          f"(capsule + TPS + recovery, per kg delivered)")

    catalog = catalog.copy()
    new_price, new_basis, routes = [], [], []
    for name, terrestrial in zip(catalog["name"], catalog["price_usd_per_kg"]):
        t = None if pd.isna(terrestrial) else float(terrestrial)
        result = in_space_price_usd_per_kg(str(name), dest_key, t)
        if result is None:
            new_price.append(terrestrial)
            new_basis.append("terrestrial market price")
            routes.append("terrestrial")
            continue
        price, route = result
        utility = in_space_utility(str(name), dest_key)
        new_price.append(price)
        routes.append(route)
        new_basis.append(
            f"terrestrial + {utility:.2f} x launch cost avoided"
            if route == "used in space" else "terrestrial price less downleg"
        )

    catalog["terrestrial_price_usd_per_kg"] = catalog["price_usd_per_kg"]
    catalog["in_space_utility"] = [
        in_space_utility(str(n), dest_key) for n in catalog["name"]
    ]
    catalog["downleg_cost_usd_per_kg"] = downleg
    catalog["in_space_processing_usd_per_kg"] = [
        in_space_processing_cost_usd_per_kg(str(n)) for n in catalog["name"]
    ]
    catalog["value_route"]     = routes
    catalog["price_usd_per_kg"] = new_price
    catalog["value_basis"]      = new_basis
    catalog["price_basis"]      = "derived-in-space"

    n_use  = routes.count("used in space")
    n_ship = routes.count("shipped to Earth")
    n_zero = int((pd.to_numeric(catalog["price_usd_per_kg"], errors="coerce") == 0).sum())
    print(f"     OK  {n_use} sold in space, {n_ship} shipped down "
          f"({n_zero} worth less than the freight)")
    return catalog


# ─────────────────────────────────────────────────────────────────────────────
# MERGE
# ─────────────────────────────────────────────────────────────────────────────
def merge_mineral_sources(
    reference: pd.DataFrame,
    live_frames: List[pd.DataFrame],
) -> pd.DataFrame:
    """
    Stitch the reference table together with live-price frames.

    The reference table is the spine (one row per mineral/element).  Each
    live-price frame contributes a `live_price_usd_per_kg` column; the first
    live source to provide a quote for a given material wins, and the
    reference fallback fills anything still missing.
    """
    print("\n  Merging sources ...")

    catalog = reference.copy()
    catalog["live_price_usd_per_kg"] = pd.NA
    catalog["live_price_date"]   = pd.NA
    catalog["live_price_source"] = pd.NA

    for live in live_frames:
        if live is None or live.empty:
            continue
        for _, row in live.iterrows():
            mask = catalog["name"] == row["name"]
            if not mask.any():
                continue
            # Only fill if not already filled by an earlier (higher-priority) source
            empty = catalog.loc[mask, "live_price_usd_per_kg"].isna()
            if empty.any():
                idx = catalog.index[mask & catalog["live_price_usd_per_kg"].isna()]
                catalog.loc[idx, "live_price_usd_per_kg"] = row["live_price_usd_per_kg"]
                catalog.loc[idx, "live_price_date"]   = row["live_price_date"]
                catalog.loc[idx, "live_price_source"] = row["live_price_source"]

    # Resolve the final `price_usd_per_kg`: live where available, else reference.
    live = pd.to_numeric(catalog["live_price_usd_per_kg"], errors="coerce")
    ref  = pd.to_numeric(catalog["ref_price_usd_per_kg"],  errors="coerce")
    catalog["price_usd_per_kg"] = live.fillna(ref)
    catalog["price_basis"] = np.where(
        live.notna(), "live",
        np.where(ref.notna(), "reference", "unpriced"),
    )

    n_live = int((catalog["price_basis"] == "live").sum())
    n_ref  = int((catalog["price_basis"] == "reference").sum())
    n_unp  = int((catalog["price_basis"] == "unpriced").sum())
    print(f"     Live prices  : {n_live:>3} entries")
    print(f"     Reference    : {n_ref:>3} entries")
    print(f"     Unpriced     : {n_unp:>3} entries")

    return catalog


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def validate_minerals(catalog: pd.DataFrame) -> pd.DataFrame:
    """Light sanity checks, print warnings, never drop rows."""
    print("\n  Validating catalog ...")

    # ── Unit normalisation guard ─────────────────────────────────────────────
    # Every numeric price column MUST be USD per kilogram.  This block both
    # documents and enforces that invariant: any forgotten conversion (e.g.
    # leaving a value in USD/oz) shows up as an out-of-band magnitude here.
    # Bounds: 0.001 USD/kg (cheap bulk gravel) up to 1e7 USD/kg (well above
    # rhodium); anything outside is almost certainly a unit-conversion bug.
    PRICE_COLS = ["price_usd_per_kg", "live_price_usd_per_kg", "ref_price_usd_per_kg"]
    for col in PRICE_COLS:
        if col not in catalog.columns:
            continue
        vals = pd.to_numeric(catalog[col], errors="coerce")
        suspicious = catalog[
            vals.notna() & ((vals < 1e-3) | (vals > 1e7))
        ]
        if not suspicious.empty:
            print(f"     WARN  {len(suspicious)} rows in {col} outside USD/kg sanity band "
                  f"[0.001, 1e7] - possible unit-conversion bug:")
            for _, r in suspicious.iterrows():
                print(f"          {r['name']}: {r[col]}")
    print(f"     OK  Unit check: all price columns are USD/kg "
          f"(checked {', '.join(c for c in PRICE_COLS if c in catalog.columns)})")

    # Density should be positive and physically plausible (< 25 g/cm³, the
    # densest stable elements top out around osmium / iridium at ~22.6).
    bad_density = catalog[
        (catalog["density_gcm3"].isna())
        | (catalog["density_gcm3"] <= 0)
        | (catalog["density_gcm3"] > 25)
    ]
    if not bad_density.empty:
        print(f"     WARN  {len(bad_density)} rows with implausible density:")
        for _, r in bad_density.iterrows():
            print(f"          {r['name']}: {r['density_gcm3']} g/cm^3")

    # Every mineral should reference at least one known element via `yields`
    # (otherwise Module 3 can't value it).  Bulk silicates legitimately have
    # no yield, that's a warning, not an error.
    known_elements = set(catalog.loc[catalog["kind"] == "element", "name"])
    for _, r in catalog[catalog["kind"] == "mineral"].iterrows():
        try:
            ymap = json.loads(r["yields_json"] or "{}")
        except json.JSONDecodeError:
            print(f"     FAIL  {r['name']}: malformed yields_json")
            continue
        unknown = set(ymap) - known_elements
        if unknown:
            print(f"     WARN  {r['name']}: yields reference unknown elements {sorted(unknown)}")

    print(f"     OK  Validation complete")
    return catalog


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def build_mineral_value_catalog(
    config: MineralValueConfig = MINERAL_CONFIG,
) -> pd.DataFrame:
    """
    Run the full mineral-value pipeline:
      1. Fetch live prices (yfinance, optionally metals.dev)
      2. Load the curated reference table
      3. Merge; live wins, reference fills gaps
      4. Validate
      5. Sort, tag, export
    """
    t0 = datetime.now()

    print("=" * 65)
    print("    MINERAL VALUE PIPELINE - MODULE 2")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  v{config.pipeline_version}")
    print("=" * 65)

    # ── Step 1, Live-price fetchers (in priority order) ─────────────────────
    live_frames = [
        fetch_yfinance(config)    if config.use_yfinance    else pd.DataFrame(),
        fetch_metals_dev(config)  if config.use_metals_api  else pd.DataFrame(),
    ]

    # ── Step 2, Reference spine ─────────────────────────────────────────────
    reference = (
        fetch_reference_table(config)
        if config.use_reference_table else pd.DataFrame()
    )
    if reference.empty:
        print("\nFAIL  Pipeline aborted - reference table disabled and no live data spine")
        return pd.DataFrame()

    # ── Step 3, Merge ───────────────────────────────────────────────────────
    catalog = merge_mineral_sources(reference, live_frames)

    # ── Step 3b; Reprice for the delivery destination ───────────────────────
    # Must follow the merge: at an in-space destination this overrides live
    # quotes too, since a terrestrial spot price is not what a commodity is
    # worth at a depot.
    catalog = apply_delivery_destination(catalog, config)

    # ── Step 4, Validate ────────────────────────────────────────────────────
    catalog = validate_minerals(catalog)

    # ── Step 5, Metadata + sort ─────────────────────────────────────────────
    # How much of each commodity the market can absorb per year, Module 4
    # uses it to apply a demand curve rather than selling any quantity at spot.
    # v1.7.0: routed; a commodity sold by flying it down saturates the
    # TERRESTRIAL market, not the destination's import budget.
    _routes = (catalog["value_route"] if "value_route" in catalog.columns
               else [None] * len(catalog))
    catalog["annual_market_kg"] = [
        annual_market_kg(str(n), config.delivery_destination,
                         None if pd.isna(r) else str(r))
        for n, r in zip(catalog["name"], _routes)
    ]

    catalog["catalog_date"]         = t0.strftime("%Y-%m-%d")
    catalog["pipeline_version"]     = config.pipeline_version
    # Stamped into every row: the water price, and therefore the whole
    # downstream ranking, is meaningless without knowing which destination
    # it was priced for.
    catalog["delivery_destination"] = config.delivery_destination

    catalog = catalog.sort_values(
        ["kind", "price_usd_per_kg"], ascending=[True, False]
    ).reset_index(drop=True)

    # ── Step 6, Save ────────────────────────────────────────────────────────
    out_path = os.path.join(config.output_dir, config.catalog_filename)
    # lineterminator is pinned because pandas defaults it to os.linesep,
    # which makes a catalog written on Linux differ from the same catalog
    # written on Windows in every line, for no model reason.  CRLF is the
    # existing Windows output, so pinning it changes nothing here.
    catalog.to_csv(out_path, index=False, lineterminator="\r\n")
    print(f"\n       Catalog saved -> {out_path}")

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - t0).total_seconds()
    print("\n" + "=" * 65)
    print("  OK  MINERAL VALUE CATALOG COMPLETE")
    print(f"      Entries  : {len(catalog):,}")
    print(f"      Columns  : {len(catalog.columns)}")
    print(f"      Elapsed  : {elapsed:.1f}s")
    print("=" * 65)

    return catalog


# ─────────────────────────────────────────────────────────────────────────────
# QUERY UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def lookup_mineral(catalog: pd.DataFrame, name: str) -> pd.DataFrame:
    """Case-insensitive substring match against the `name` column.

    regex=False; a query like "nickel-iron (alloy)" would otherwise be read
    as a regex pattern rather than the literal substring the docstring
    promises, and an unbalanced bracket would raise re.PatternError.
    """
    q = name.strip().lower()
    return catalog[
        catalog["name"].str.lower().str.contains(q, na=False, regex=False)
    ].copy()


def value_per_kg(catalog: pd.DataFrame, mineral: str) -> Optional[float]:
    """Resolve the final USD/kg price for a single mineral by name."""
    row = catalog[catalog["name"] == mineral]
    if row.empty:
        return None
    val = row["price_usd_per_kg"].iloc[0]
    return float(val) if pd.notna(val) else None


def mineral_to_element_value(
    catalog: pd.DataFrame, mineral: str,
) -> Optional[float]:
    """
    For a MINERAL, compute its implied USD/kg from its elemental yields.
    Returns None if the mineral isn't in the catalog or has no yields.
    """
    row = catalog[catalog["name"] == mineral]
    if row.empty:
        return None
    try:
        yields = json.loads(row["yields_json"].iloc[0] or "{}")
    except json.JSONDecodeError:
        return None
    if not yields:
        return None

    total = 0.0
    for element, fraction in yields.items():
        elem_price = value_per_kg(catalog, element)
        if elem_price is None:
            continue
        total += float(fraction) * elem_price
    return total if total > 0 else None


print("\nOK  Helper utilities available:")
print("    lookup_mineral(catalog, 'gold')")
print("    value_per_kg(catalog, 'platinum')")
print("    mineral_to_element_value(catalog, 'nickel-iron')")




# =========================================================================
# MODULE 3 - TRANSPORTATION DATA
# =========================================================================




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
    # propellant tanks are quoted in the trade.  Enforced by validate_transport() and
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

TRANSPORT_CONFIG = TransportConfig()
os.makedirs(os.path.join(TRANSPORT_CONFIG.output_dir, TRANSPORT_CONFIG.subdir), exist_ok=True)


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
validate_transport = _spacecost_validate


def build_transportation_catalog(
    config: TransportConfig = TRANSPORT_CONFIG,
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
print(f"    Output dir: {os.path.join(TRANSPORT_CONFIG.output_dir, TRANSPORT_CONFIG.subdir)}")




# =========================================================================
# MODULE 4 - PROFITABILITY CALCULATOR
# =========================================================================




# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import ast
import contextlib
import functools
import json
import math
import multiprocessing as mp
import os
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import (Any, Dict, Iterator, List, Mapping, NamedTuple, Optional,
                    Tuple, Union)

import numpy as np
import pandas as pd

# A row of one of the upstream catalogs.  The hot path converts these to plain
# dicts (see _row_to_dict); everything that reads one uses only `.get(key)` and
# `[key]`, which a dict and a Series serve identically.
Row = Mapping[str, Any]

# ─── SPAWNED-WORKER QUIET MODE ───────────────────────────────────────────────
# Windows has no fork, so every parallel worker re-imports this file and would
# replay the startup banner -- 60 lines each, 700+ for a full pool.  The parent
# sets ASTEROID_PIPELINE_WORKER before creating the pool and children inherit
# it.  Flipped to "silenced" rather than cleared so that the SECOND copy of
# this guard in the built master.py (which carries both the master header's and
# this module's) is a no-op instead of leaking another handle.
#
# stderr is deliberately left alone: a worker that dies should still say so.
if os.environ.get("ASTEROID_PIPELINE_WORKER") == "1":
    os.environ["ASTEROID_PIPELINE_WORKER"] = "silenced"
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

for _cat in (DeprecationWarning, FutureWarning, UserWarning):
    warnings.filterwarnings("ignore", category=_cat)

pd.set_option("display.max_columns", None)
pd.set_option("display.float_format", "{:.4g}".format)


# Physical constants
G0_M_S2 = 9.806_65    # standard gravity (matches Module 3)


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
    # Colab detection.  os.path.isdir("/content") alone is not enough: on
    # Windows a leading "/" is drive-relative, so it tests C:\content -- a
    # directory an earlier run of the pre-fix code may itself have created,
    # which would route output straight back to the path this function
    # exists to avoid.  Require a POSIX platform as well.
    if os.name == "posix" and os.path.isdir("/content"):
        return "/content/asteroid_pipeline"
    return os.path.join(os.getcwd(), "asteroid_pipeline")


_DEFAULT_OUTPUT_DIR = _default_output_dir()


# ═════════════════════════════════════════════════════════════════════════════
# ║                                                                           ║
# ║   ★  USER SETTINGS, EDIT THESE TO TUNE THE PIPELINE  ★                  ║
# ║                                                                           ║
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class CalcConfig:
    """User-editable configuration for the profitability calculator."""

    # ─── INPUTS  (where Modules 1-3 wrote their catalogs) ────────────────────
    input_dir:                str = _DEFAULT_OUTPUT_DIR
    asteroid_catalog_file:    str = "asteroid_catalog.csv"
    mineral_catalog_file:     str = "mineral_value_catalog.csv"
    transportation_subdir:    str = "transportation"
    # Inside transportation_subdir:
    launch_vehicles_file:     str = "launch_vehicles.csv"
    propellants_file:         str = "propellants.csv"
    delta_v_segments_file:    str = "delta_v_segments.csv"
    operational_costs_file:   str = "operational_costs.csv"

    # ─── OUTPUT ──────────────────────────────────────────────────────────────
    output_dir:               str = _DEFAULT_OUTPUT_DIR
    output_filename:          str = "profitability_catalog.csv"

    # ─── MISSION HARDWARE (kg) ───────────────────────────────────────────────
    # `m_hardware`     - mining rig + comms + structure that stays at asteroid
    # `m_dry_return`   - return vehicle dry mass (TPS frame + chute + structure,
    #                    NOT the ablative TPS itself which scales with payload)
    mining_hardware_kg:        float = 2_000

    # A FLOOR, not the whole return dry mass: `return_structure_frac_of_payload`
    # adds 15% of the haul on top of it.  Flat 500 kg gave 250:1
    # payload-to-structure against 0.4:1 (Cygnus) to 2:1 (Dragon) for real
    # cargo craft, and nothing else bounded returned mass.
    return_vehicle_dry_kg:     float = 500

    # ─── RETURN VEHICLE SCALES WITH ITS CARGO  (v1.10.0) ─────────────────────
    # `return_vehicle_dry_kg` was the WHOLE dry mass of the return vehicle, a
    # flat 500 kg however much it carried.  Since the payload is solved for
    # rather than specified, that let the cascade load 125 tonnes of ore into a
    # 500 kg can, a payload-to-structure ratio of 250:1, where real cargo
    # spacecraft run between 0.4:1 and 2:1.  Nothing caught it because the only
    # other check on returned mass was the launch vehicle's fairing VOLUME,
    # which a dense metal payload never fills.
    #
    # So the 500 kg becomes a floor, the irreducible avionics, comms, beacon
    # and separation hardware, and a structural fraction of the payload is
    # added on top: tankage, primary structure, cargo restraint, the parachute
    # or the berthing mechanism.  0.15 is deliberately at the light end of the
    # real range because the ablative TPS is already carried separately by
    # `heat_shield_frac_of_payload`, and because a purpose-built ore carrier
    # should beat a crew-rated capsule.  Heritage for the range: Cygnus PCM
    # ~1,500 kg dry for 3,500 kg of cargo (0.43), Dragon ~1.3:1 with crew
    # provisions, OSIRIS-REx's SRC far worse again at sample scale.
    #
    # Set to 0.0 to restore the pre-v1.10.0 fixed-mass behaviour.  Note that
    # doing so also restores an unbounded payload when ISRU is on and the
    # return is propulsive: with no payload-scaling term anywhere in the
    # cascade, nothing but the volume cap limits the haul.
    return_structure_frac_of_payload: float = 0.15

    # ─── MINING MODEL ────────────────────────────────────────────────────────
    # The share of a body one mission may remove.  1.0 means the whole thing
    # is on the table; the mission is then bounded by what the rig can dig in
    # the time (`mining_rate_kg_per_day_per_kg_rig` x
    # `max_mining_duration_yr`), by the return capsule's volume cap, and by
    # the rocket equation, which is where the real limits live.
    #
    # v1.23.0 raised this from 0.05.  The 5% was a stated conservatism about a
    # first mission to a large body and was never derived from anything; what
    # it did on a real population was act as an accidental PAYLOAD SIZING
    # LEVER, because the haul is DERIVED from whichever constraint binds
    # rather than searched.  On the 400-row raw cislunar cell it bound on 3 of
    # 155 bodies, and on the cell winner (2017 KJ5) it clamped the haul to
    # 117,406 kg, which prices better than the 97,875 kg the mass budget
    # chooses unclamped -- so the cap was improving the headline by forcing a
    # smaller mission, for no physical reason.  Swept on that body: 27.39x at
    # 0.01, 16.10x at 0.02, 9.75x at 0.05, then a flat 10.25x from 0.08 up,
    # the plateau being where the cap stops binding at all.
    #
    # Set it below 1.0 to restore a depletion limit.  A value low enough to
    # bind is a value that SIZES the mission, which is the thing this default
    # stops it doing silently.
    max_mining_fraction:       float = 1.0

    # ─── MINING THROUGHPUT  (v1.4.0) ─────────────────────────────────────────
    # Before v1.4.0 the rig could extract any mass instantly: mission duration
    # came only from Δv plus a flat 0.5 yr of station-keeping, whether the
    # mission returned 33 kg or 50 tonnes.  Nothing anywhere connected how
    # much you mined to how long it took.
    #
    # `mining_rate_kg_per_day_per_kg_rig` scales extraction with the rig you
    # actually brought.  0.10 means a 2,000 kg rig moves 200 kg/day of
    # regolith.  There is no flight heritage for sustained asteroid mining, so
    # this is an engineering assumption, not a measurement; it sits here as a
    # single obvious dial rather than being buried as an implicit infinity.
    # For scale, OSIRIS-REx's TAGSAM collected ~122 g in a touch-and-go; a
    # continuous rig is a different machine entirely.
    mining_rate_kg_per_day_per_kg_rig: float = 0.10
    # Hard ceiling on time spent at the asteroid.  Binds the payload: you can
    # only return what you can dig in this long.  Also keeps ops cost and WACC
    # from compounding over an implausible stay.
    max_mining_duration_yr:            float = 3.0
    # Floor on time at the asteroid regardless of how little is mined: 
    # approach, characterisation, proximity ops, departure phasing.
    station_keeping_floor_yr:          float = 0.25

    # ─── BENEFICIATION  (v1.5.0) ─────────────────────────────────────────────
    # Terrestrial mines do not ship ore, they ship CONCENTRATE.  Without this
    # the pipeline flies home run-of-mine regolith at bulk grade, which throws
    # away the only lever that does not require a bigger rocket: the rig can
    # dig far more than the rocket can carry (219,150 kg against ~3,300 kg on
    # a default run), and all of that surplus capacity was modelled as idle.
    #
    # With beneficiation on, the rig processes everything it can dig inside
    # `max_mining_duration_yr`, rejects the gangue, and loads only concentrate.
    # Value is then bounded from both sides, which is what keeps it honest:
    #   • by CONTENT   - you cannot recover more than what you processed,
    #                    times the recovery efficiency
    #   • by PURITY    - you cannot make a concentrate richer than the best
    #                    single phase actually present in the body
    #
    # Concentration is not free.  It costs energy (see the two Module 3 energy
    # rows), the energy costs a power plant, the power plant costs mass, and
    # the mass comes straight out of the payload budget through the same
    # rocket equation.  Module 4 solves that feedback rather than ignoring it.
    #
    # ⚠️  DEFAULT TRUE as of v1.17.0, and unlike the flag below this one is
    # safe to flip on a weak-dominance argument rather than on a measurement:
    # `evaluate_combo` always also prices NOT concentrating (via
    # `beneficiate=False`, which is not the same as ratio 1.0; see the
    # concentration search), so turning this on can only widen the option set.
    # A correctly-implemented search cannot get worse for that, which is the
    # never-worse invariant this project checks after every release.
    #
    # Checked anyway, on the full catalog at cislunar (2026-08-11, calc
    # 1.16.0): 650,921 pairs, max benef/raw 1.000000, ZERO exceptions, and
    # 102,765 bodies (15.79%) declining to concentrate at exactly 1.0, the
    # documented signature, never worse and equal wherever it declines.
    #
    # What it costs is TIME, and that is the only reason it was ever off.  The
    # ratio is NOT typed here, and this comment quoted a stale one for two
    # releases while claiming it came from the dict: it read 4.67x (calc
    # 1.17.7) against a banner deriving 3.42x and then 8.11x.  The current
    # figure is whatever MEASURED_CELL_SECONDS below divides to, the run
    # banner prints it per configuration, and it has ranged from 7.1x (calc
    # 1.16.0) through 4.67x to the cells measured now.  Re-measure there and
    # every banner that quotes it moves with it.
    # Set False for the raw cell (26.7863x), which is what most of the older
    # tables in versions.md were measured at.
    use_beneficiation:         bool  = True
    # Fraction of the valuable phase that actually reports to concentrate.
    # Terrestrial PGM / sulphide flotation circuits run 85-95%; magnetic
    # separation of a metal phase from silicate gangue is mechanically simpler
    # than flotation but has no microgravity flight heritage at all.
    beneficiation_recovery:    float = 0.90
    # Safety cap on feed:concentrate mass ratio.  Terrestrial mills run
    # 100:1 to 1000:1 on PGM ores; 50:1 is deliberately conservative for a
    # first autonomous rig.  The purity bound above usually binds first.
    max_concentration_ratio:   float = 50.0
    # How hard to concentrate is an economic decision, not a setting; see
    # evaluate_combo.  This is how many points the profit sweep samples
    # between "don't concentrate" and "concentrate to pure best phase",
    # plus one refinement pass.  Raising it costs runtime linearly and buys
    # very little; 7 puts the optimum within a few percent.
    concentration_search_steps: int  = 7

    # ─── MODELLING COMPLETENESS  (v1.7.0) ────────────────────────────────────
    # Things the pipeline previously got for free.  They are corrections rather
    # than options, and each one moves numbers; set one to False only to
    # isolate its effect.  Count the block, do not trust a number here: this
    # comment said "Five things" for four releases and the fifth of them, the
    # market term, stopped being a flag at all in v1.21.0.
    #
    # ⚠️  "All default ON" was also true until v1.22.0 and is not now.  The
    # learning curve below defaults OFF, for a reason that is about SCOPE and
    # not about correctness; it is on the second list, with insurance, the cost
    # of capital and mission reliability.  See README, "what the model
    # deliberately does not charge for".
    #
    # LOW-THRUST TRIP TIME.  Electric propulsion paid a Δv penalty but flew
    # its burns instantly on power it did not carry.  With this on, the EP
    # stage is sized to complete its thrusting inside `ep_target_thrust_yr`,
    # the array and thruster mass that demands enters the rocket equation,
    # and the thrusting time enters mission duration.  This is what stops a
    # 3,000 s Isp thruster winning a mass cascade it could only fly over
    # decades.
    model_low_thrust_time:     bool  = True
    ep_target_thrust_yr:       float = 3.0    # thrusting time the EP stage is sized for
    # Reject any mission whose total duration exceeds this.  A 40-year
    # round trip is not a mission, it is a bequest.
    max_mission_duration_yr:   float = 25.0

    # LAUNCH WINDOWS.  Departure needs the target and destination phased,
    # and those alignments recur at the synodic period.  Expected wait after
    # mining completes is half a period.  Counterintuitively this punishes
    # NEAs hardest; their periods are near Earth's, so windows are years
    # apart.
    model_launch_windows:      bool  = True

    # BOUND-WATER LIBERATION.  C/B/D-type "ice" is water locked in
    # phyllosilicates; it has to be baked out at ~700 K, not scooped.  The
    # pipeline was extracting it for free while selling it at full
    # launch-cost-avoided.
    model_water_liberation:    bool  = True

    # LEARNING CURVE on recurring hardware.  Only NRE was amortised across a
    # fleet; the rig cost $300k/kg at unit 1 and unit 500 alike.  Wright's
    # law at 85% is standard for aerospace serial production.  Has NO effect
    # at nre_amortization_missions = 1, where the cumulative average is the
    # first-unit cost by definition.
    #
    # ⚠️  DEFAULT FALSE as of v1.22.0, and it is a SCOPE decision rather than a
    # claim that the curve is wrong, which is the same objection v1.20.0 made
    # to insurance.  Wright's law is a statement about a factory's learning,
    # fitted to programmes that built dozens to hundreds of articles; this
    # pipeline prices the marginal physics of moving a kilogram and its
    # programme ladder routinely proposes N in the tens.  Charging a serial-
    # production discount on top of that credits the answer with an industrial
    # base the run never modelled, and it runs in the generous direction, which
    # is the direction this module refuses everywhere else.
    #
    # Turning it on restores v1.21.2 exactly at any N, and is exactly inert at
    # N = 1 either way, so every single-mission figure in this project is
    # unaffected by the flip.
    model_learning_curve:      bool  = False
    # Wright's-law rate for the flag above: each doubling of cumulative
    # production cuts unit cost to this fraction.  Read ONLY when
    # `model_learning_curve` is True; 1.0 disables the curve on its own.
    learning_curve_rate:       float = 0.85

    # MARKET MODEL.  How much of a delivered kilogram actually sells, and the
    # only term in this module that pushes back on programme scale: N improves
    # five things (NRE/N, autonomy NRE/N, the learning curve, the rig's share,
    # p_mining) and this is the sixth.  Remove the pushback and the objective
    # is monotone in N, which is v1.14.0's failure mode returning.
    #
    #   capacity_cap    v1.21.0 default.  Prices are CONSTANT at any volume;
    #                   what bounds a programme is a hard kg/yr ceiling per
    #                   commodity.  Everything up to the ceiling sells at full
    #                   price and everything past it earns nothing, so this is
    #                   a quantity wall rather than a price discount.  The
    #                   payload knapsack sees the ceilings, so a load that caps
    #                   out on iron fills the rest of the hold with whatever is
    #                   next most valuable.  See `capacity_allowance_kg`.
    #   single_mission  Constant prices, N pinned at 1, no programme search and
    #                   no ceiling.  The question every figure measured before
    #                   calc v1.17.0 was answering.
    #   elasticity      The v1.14.0 demand curve, P/P0 = (1+Q/Qm)^(-1/eps).
    #                   ⚠️  It reproduced v1.14.0 to v1.20.0 bit-identically
    #                   until v1.21.1 gave the composition residual the market
    #                   ceiling it was already priced against.  That defect was
    #                   in the curve too, so fixing it moved the curve: the raw
    #                   cislunar cells by +2.36% and +5.82%, the beneficiated
    #                   ones not at all.  It is the v1.14.0 CURVE, not a
    #                   bug-for-bug replay of v1.20.0.
    #   unbounded       Constant prices and no ceiling at all.  A DIAGNOSTIC,
    #                   not a model: every row runs to `max_fleet_ships` and
    #                   the run says so out loud.
    market_model:              str   = "capacity_cap"

    # The elasticity in P/P0 = (1 + Q/Q_market)^(-1/eps).  0.5 is inelastic,
    # which is right for precious metals: doubling world supply quarters the
    # price.  Raising it makes the market absorb more before the price moves.
    # Read ONLY when `market_model` is "elasticity"; the other three modes hold
    # price flat and bound quantity instead.
    demand_elasticity:         float = 0.5

    # ─── SURPLUS OVER THE CEILING SELLS, AT A DISCOUNT  (v1.22.0) ────────────
    # `capacity_cap` as shipped in v1.21.0 was a hard wall: every kilogram past
    # a commodity's ceiling earned exactly nothing and was reported as
    # `unsold_payload_kg`.  That is the right shape for a market that refuses
    # the sale outright, and it is too strong for most of the ones in this
    # table.  A destination that can absorb 100 t/yr of water at the quoted
    # price does not become unable to take the 101st tonne; it takes it at a
    # price that clears, which is the whole content of a supply curve sloping
    # down.  Abandoning the mass instead models a market with a cliff in it.
    #
    # True sells the surplus at `surplus_price_fraction` of the full price.
    # Ceilings still bind, and they still bound the programme ladder, because
    # the marginal kilogram past the wall is worth strictly less than the one
    # before it -- which is what stops the objective running to
    # `max_fleet_ships`.  What changes is that it is worth something.
    #
    # ⚠️  It reshapes the BENEFICIATED knapsack as well as the raw sale, and
    # that is the half worth understanding.  A concentrated load chooses what
    # it carries, so the discount puts every phase on the market TWICE: once at
    # full price up to its ceiling, once at the discounted price above it.  The
    # greedy walk then interleaves them, and a rich phase's surplus can outrank
    # a poor phase's full-price allowance, which is the correct answer and is
    # not what a wall would have chosen.  See `optimal_payload_mix`.
    #
    # Set False for the v1.21.0 wall, which is what every cell of the 2026-09
    # campaign was measured on.
    sell_surplus_at_discount:  bool  = True
    # What a kilogram past the ceiling fetches, as a fraction of the full
    # quoted price.  0.5 is "half price", the deliberately round number this
    # flag was added for: there is no market study behind it, so it sits here
    # as one obvious dial rather than being buried as an implicit 0.0.  Read
    # ONLY when `sell_surplus_at_discount` is True, and only under
    # `market_model = "capacity_cap"`; 0.0 reproduces the wall exactly.
    surplus_price_fraction:    float = 0.5

    # ─── MODELLING COMPLETENESS, PART 2  (v1.8.0) ────────────────────────────
    # RIG SERVICE LIFE AND TERMINAL VALUE.  The rig was amortised across
    # `nre_amortization_missions` with no upper bound, so a programme could
    # spread one rig across 100 missions of 2 years each: 200 years of duty
    # from a machine chewing rock.  It now has a finite life (Module 3, 15 yr),
    # which CAPS the amortisation, and whatever life is left when the
    # programme ends is credited back at the salvage fraction.
    #
    # The cap is the part that bites: at long stays it makes the rig markedly
    # MORE expensive than the old flat division, not less.  Terminal value is
    # only credited when there is a programme to inherit the rig
    # (nre_amortization_missions > 1), a rig parked at an asteroid nobody
    # returns to is stranded, not an asset.
    model_rig_service_life:    bool  = True

    # MISSION RELIABILITY.  Revenue was certain.  It is not: the launch can
    # fail, the spacecraft can die in transit, and the mining chain has never
    # been demonstrated at all.  Expected revenue is multiplied by
    #     P = p_launch · exp(−T/MTBF) · p_mining
    # while COSTS are still charged in full, which is the conservative and
    # correct treatment; you spend the money either way.  v1.20.0 turned both
    # insurance premiums off and this term is unaffected either way: insurance
    # replaced hardware on failure and never revenue, so there was no double
    # count to remove.
    #
    # ⚠️  DEFAULT FALSE as of v1.22.0, and read what that does and does not
    # say.  It does NOT say the risk is not real.  P is a product of three
    # numbers, and only the first is a measurement: launch reliability is an
    # observed rate over hundreds of flights, cruise survival is an exponential
    # on an assumed MTBF, and `p_mining` is a guess about a machine nobody has
    # ever built.  Multiplying the ANSWER by that guess puts it in every
    # headline ratio while leaving it as legible as the parameter it came from,
    # and the effect is not small: at first-of-kind p_mining the term moves the
    # objective by more than most of the physics in this module.
    #
    # So it becomes a question you ask deliberately rather than a discount
    # baked into the default.  A default run now answers "what does this cost
    # if it works", which is the same framing that makes the two surface
    # delivery prices LOWER BOUNDS, and the risk-weighted question is one flag
    # away.  Set True to restore v1.21.2 and everything measured before it.
    model_reliability:         bool  = False
    # RELIABILITY GROWTH.  The mining chain learns: a programme's second rig
    # is not as likely to jam as its first.  p_mining becomes the FLEET
    # AVERAGE over nre_amortization_missions under the Duane model, capped at
    # a mature ceiling.  Exactly the first-of-kind figure at N = 1.
    # Launch and cruise reliability deliberately do NOT grow; launch vehicles
    # are already mature, and MTBF is a duration exposure, not a heritage
    # question.  ⚠️  INERT while `model_reliability` above is False, which is
    # the default as of v1.22.0: this shapes P, it does not create it.  Left
    # True so that turning reliability back on restores the whole v1.21.2 term
    # rather than half of it.
    model_reliability_growth:  bool  = True

    # CRYOGENIC BOIL-OFF.  Return propellant sits in the tank from launch
    # until the departure burn, years, not hours.  Hydrolox loses ~0.05%/day
    # even with active cooling, which over a 5-year mission means loading 2.5×
    # what the rocket equation says you burn.  Without this, hydrolox wins
    # long missions it could not physically store propellant for.  ISRU return
    # propellant is exempt: it is manufactured at the asteroid on departure.
    model_propellant_boiloff:  bool  = True

    # PROPELLANT TANKAGE (v1.11.0).  A tank's mass scales with the VOLUME it
    # encloses, so leaving it out of the cascade subsidised whichever propellant
    # had the lowest density, which is the same propellant that has the
    # highest Isp, so the error compounded instead of cancelling.  Module 3
    # derives `tank_kg_per_L` per propellant from storage class and density;
    # this flag turns the term on.  Set False to restore v1.10.1 masses.
    model_tank_mass:           bool  = True

    # RADIOISOTOPE POWER (v1.11.0).  Solar is 60 W/kg at 1 AU falling as 1/r²;
    # an RTG is ~5 W/kg everywhere, so they cross at 3.46 AU and a large part
    # of this catalog sits beyond it.  Module 3 has priced RTGs since v1.2.0
    # and nothing read the row, so every main-belt body flew a starved solar
    # array.  Capped because the binding constraint is Pu-238 supply (~1.5 kg/yr
    # of DOE production, ~one flagship RTG a year for the world), not money.
    allow_rtg_power:           bool  = True

    # A SUPPLY cap rather than a money cap.  DOE makes ~1.5 kg of Pu-238 a
    # year, about one flagship RTG for the entire world, so a mission wanting
    # more than this goes back to solar and pays the mass.
    rtg_max_power_w:           float = 5_000.0

    # ─── MODELLING COMPLETENESS, PART 4  (v1.14.0) ───────────────────────────
    # ECLIPSE / NIGHT-SIDE POWER.  `processing_power_w()` computes a CONTINUOUS
    # average draw and the plant was sized straight off it, which assumes the
    # sun never sets on a rig standing on a rotating body.  It does: a surface
    # site is lit about half the time, and asteroid rotation periods run hours,
    # not the 35 minutes of a LEO eclipse.
    #
    # Two separate terms, and only the first is large:
    #   • the array must be OVERSIZED, because the sunlit hours have to run the
    #     load and recharge the store, [(1−f) + f/η]/(1−f) = 2.11× at f = 0.50.
    #     This is a sizing factor, so no W/kg figure could ever have carried it.
    #   • the store itself has to hold the load across the dark period, which is
    #     set by the BODY'S OWN rotation period, so this term is per-asteroid,
    #     and a slow rotator is genuinely a worse place to mine.
    #
    # Exempt: a radioisotope plant (flat output, no night) and the EP array
    # (interplanetary cruise, permanent sunlight).  Both exemptions are physical
    # rather than conservative, and the RTG one has a visible consequence; 
    # eclipse is what finally makes the radioisotope branch worth choosing on
    # more than a rounding number of bodies.
    model_eclipse_power:       bool  = True
    # Median of the 29,288 catalog bodies that have a MEASURED rotation period
    # (2026-08-08).  Used only where the body does not state one, about two
    # thirds of the catalog.  Sub-kilometre bodies run faster (median 6.3 h),
    # so this default is conservative for exactly the small NEAs this model
    # likes: a longer assumed night buys a heavier battery.
    default_rotation_period_h: float = 10.222
    # Slow rotators run to hundreds of hours and a few tumble on ~10,000 h.
    # Sizing a battery for a 40-day night is not an answer, it is a different
    # architecture question (you would fly nuclear, or accept a duty cycle), so
    # the dark period used for STORAGE is clamped and the clamp is reported.
    # 72 h is three days, which is the outside edge of what a chemical battery
    # is a sane answer for.
    max_dark_period_h:         float = 72.0

    # VOLATILE CARGO CONTAINMENT.  The pipeline sells water at every in-space
    # destination and charged nothing to keep it from subliming across a
    # four-year cruise.  That was not a rounding term: the best cislunar
    # missions run ~88% water by mass, so the commodity carrying the entire
    # result was the one flying free.  Module 3's "Volatile cargo containment"
    # row (0.05 kg/kg, sealed and shaded hold) is INCREMENTAL to the 0.15 ore
    # restraint already carried by return_structure_frac_of_payload.
    model_volatile_containment: bool = True

    # ORBITAL REFUELLING (v1.11.0).  A vehicle whose escape payload assumes
    # tanker flights has to pay for them.  Starship's own Module 3 notes field
    # has asked for this since v1.4.0, its 27 t to escape EXCEEDS its 21 t to
    # GTO precisely because it assumes refuelling, and until now its escape
    # payload was priced at one $90M launch.
    #
    # v1.12.0: the charge is real but it belongs to the ESCAPE-DIRECT scenario,
    # which is what the Module 3 note actually asked for and which this module
    # does not have.  Stage 4 reads `payload_leo_kg` / `usd_per_kg_to_leo` and
    # nothing else; the vehicle is a LEO lifter and the stack departs on its
    # own outbound stage, so no mission here is ever refuelled, and v1.11.0
    # was billing $1.08B for a capability it never used.  Setting
    # `escape_direct_launch` True re-arms it, and nothing does that yet.
    charge_tanker_flights:     bool  = True

    # Gates the tanker charge above.  Nothing sets it, because this module has
    # no escape-direct architecture to bill: it reads payload_leo_kg and
    # usd_per_kg_to_leo and nothing else.  Kept wired for the day it does.
    escape_direct_launch:      bool  = False

    # INSURANCE (v1.20.0).  OFF because the charge is IRRELEVANT rather than
    # wrong.  ⚠️  It was the ONLY cost flag here defaulting OFF until v1.22.0,
    # which put the cost of capital, mission reliability and the learning curve
    # on the same footing for the same reason; that sentence is corrected
    # rather than deleted because "the one flag that..." is exactly the kind of
    # claim this repo keeps finding outlived by a later release.  Module 3
    # prices two premiums, a $1.5M third-party liability flat and launch
    # insurance at 10% of (launch + spacecraft book value), and both are real
    # money a real programme pays.  They are not what this pipeline asks.  It
    # prices the marginal physics and hardware of moving a kilogram, on the
    # same "industrial scale, no programme overhead" framing that makes the two
    # surface delivery prices LOWER BOUNDS, and a premium is priced off an
    # underwriter's book rather than off a mass, a Delta-v or a kilowatt.  It
    # is also a second statement of a risk the model already carries
    # explicitly: `model_reliability` discounted revenue by P and charged every
    # cost in full.  ⚠️  That term is OFF by default as of v1.22.0, so the
    # sentence above no longer describes a default run; the two are now off
    # together, and turning either on restores it.
    #
    # Set True to restore both lines and to reproduce anything measured on calc
    # 1.19.2 or earlier.  `liability_cost_usd` and `launch_insurance_cost_usd`
    # stay in the CSV either way, at 0.0 when this is off, so no schema moves
    # and a run that charged them is still one column away from one that did
    # not.
    charge_insurance:          bool  = False

    # LAUNCH ACCELERATION (v1.12.0).  Module 3's `max_accel_g` exists to
    # disqualify the kinetic launchers and was read by nothing.  Spacecraft
    # structures qualify to single-digit g and every rocket in the table is
    # 6 g or less; SpinLaunch is 10,000 g, a light-gas gun 30,000, StarTram 30.
    # 15 g leaves every real launcher untouched with margin and excludes all
    # three, which is exactly what the column was added for.
    max_payload_accel_g:       float = 15.0

    # ─── PER-ASTEROID Δv  (v1.4.0) ───────────────────────────────────────────
    # When True, each asteroid's Δv is derived from its own orbital elements
    # (semi_major_axis_au, eccentricity, inclination_deg) by the patched-conic
    # estimator in asteroid_transfer_dv_km_s.  This is what makes the ranking
    # reflect accessibility rather than composition alone.
    #
    # Set False to restore the pre-v1.4.0 behaviour, where every asteroid in
    # the catalog received the same Δv from the two `default_dv_*` fields
    # below.  Rows whose elements are missing or unusable fall back to those
    # defaults automatically either way.
    use_per_asteroid_dv:       bool  = True
    # Sanity ceiling.  Elements arriving mangled from an upstream source can
    # produce absurd transfers; anything above this is clamped rather than
    # allowed to poison the ranking.  Module 3's most expensive reference
    # segment is the 10.5 km/s main-belt transfer.
    max_dv_outbound_m_s:       float = 20_000

    # ─── Δv DEFAULTS (m/s) ───────────────────────────────────────────────────
    # Applied uniformly to every asteroid (v1.3.5, per-target Asterank Δv
    # override removed alongside the Asterank source).  All missions use
    # the Module 3 reference Δv for "average NEA" by default; edit here
    # per-run to model a specific class.
    default_dv_outbound_m_s:   float = 6_500    # avg NEA per Module 3
    default_dv_return_m_s:     float = 5_500    # propulsive return
    # (a default_mission_duration_yr constant used to sit here; nothing read
    #  it once asteroid_mission_duration_yr() began deriving duration from Δv)

    # ─── DELIVERY DESTINATION  (selects the mission architecture) ────────────
    # MUST MATCH Module 2's MINERAL_CONFIG.delivery_destination.  Module 2
    # decides what a kilogram sells for; this field decides what it costs to
    # put it there, and the two are only consistent when they agree.  A
    # mismatch is checked and warned about loudly in build_profitability_catalog.
    #
    #   "earth_surface": re-entry capsule, Earth recovery campaign, full
    #                     launch + re-entry Part 450 licence.  Cheapest return
    #                     Δv (direct entry needs no capture burn at all), but
    #                     the cargo is worth terrestrial commodity prices.
    #   "leo"           - berthed at an LEO depot.  No re-entry, so no capsule,
    #                     no recovery campaign, launch-only licence.  The most
    #                     EXPENSIVE return Δv in the model: circularising into
    #                     LEO means killing the whole arrival hyperbola.
    #   "geo"           - berthed at a geostationary servicing depot.  The
    #                     only destination in the model with a customer that
    #                     exists today; MEV-1 and MEV-2 have docked with
    #                     commercial GEO satellites already.  Capture is a
    #                     SEARCH over two geometries, not one formula, and it
    #                     pays 23.44 deg of plane change that no other
    #                     destination does; see _geo_capture_dv_km_s.  The
    #                     market is narrow: a depot refuels satellites, so
    #                     the volatiles hold their value and the structural
    #                     metals lose most of theirs.
    #   "cislunar"      - berthed at an NRHO depot.  Same cost savings as LEO,
    #                     and the cheapest return Δv of the orbital options,
    #                     because capture only has to bind the orbit and the
    #                     burn takes the Oberth benefit at low perigee.
    #   "lunar_surface", landed at a Moon base.  Cislunar capture plus
    #                     2.6 km/s of NRHO→LLO→surface, all propulsive; the
    #                     Moon has no atmosphere to brake against.  Carries a
    #                     $200k/kg lander instead of a berthing adapter.
    #   "mars_surface"  - landed at a Mars base.  NOT an Earth return: the
    #                     heliocentric transfer runs from the asteroid's orbit
    #                     to Mars' (1.524 AU), so the departure burn, arrival
    #                     v_infinity and capture are all separately computed
    #                     (_asteroid_to_mars_dv_km_s).  Many NEAs have aphelia
    #                     out near Mars and are genuinely closer to it than to
    #                     Earth.  Aerocapture is available and worth several
    #                     km/s.
    #   "mars_orbit"    - berthed at a 1-sol Mars-orbit depot (250 x 33,793
    #                     km, NASA DRA 5.0).  The same heliocentric transfer
    #                     as mars_surface, stopped one leg early: capture
    #                     BINDS the ellipse rather than circularising, 0.90
    #                     km/s against 2.10, and nothing lands, so there is no
    #                     descent burn and no lander.  Berthing adapter at
    #                     $60k/kg.  Aerocapture available.
    #
    # See DELIVERY_ARCHITECTURES for what each one actually changes.
    delivery_destination:      str   = "earth_surface"

    # ─── WHAT THE PER-ASTEROID SEARCH OPTIMISES  (v1.10.0) ───────────────────
    # Every search in this module, concentration ratio, vehicle, propellant,
    # return mode, propellant sourcing, has to rank candidate missions by
    # something, and until v1.10.0 that something was `profit_usd`.  In this
    # model revenue sits orders of magnitude below cost, so profit is very
    # nearly minus the cost, and maximising it quietly became "pick the
    # cheapest mission", while the project ranked the output by a cost/revenue
    # ratio nothing had optimised.
    #
    #   "cost_revenue_ratio"  maximise profit if any candidate is profitable,
    #                         otherwise minimise cost / revenue.  Default.
    #   "profit"              maximise profit always (pre-v1.10.0 behaviour).
    #
    # See selection_key.
    selection_objective:       str   = "cost_revenue_ratio"

    # ─── PER-ASTEROID ARCHITECTURE SEARCH  (v1.10.0) ─────────────────────────
    # The model has always chosen the launch vehicle and the propellant per
    # asteroid, by profit.  Two other mission-architecture choices were set
    # once for the whole catalog instead, whether to aerocapture, and whether
    # to make return propellant on site, even though the right answer to both
    # varies target by target and for exactly the same reasons.
    #
    # With this on, both become part of the same per-asteroid search: every
    # feasible (return mode × ISRU) combination is priced against every
    # (vehicle × propellant), and the mission that actually gets flown is the
    # most profitable one.  The two flags below stop meaning "do this" and
    # start meaning "this is available"; an option that never pays is simply
    # never chosen.
    #
    # Cost: roughly doubles Stage 4 runtime at destinations where aerocapture
    # is available, and adds a little more on water-bearing bodies where ISRU
    # is feasible.  Set False to price only the config's nominal architecture.
    optimise_architecture_per_asteroid: bool = True

    # ─── AEROCAPTURE  (return via heat shield rather than propulsive) ────────
    # Return Δv is reduced, per asteroid, from its own arrival v_infinity, 
    # but a heat-shield mass overhead is added at the rate from Module 3, and
    # that mass is hauled outbound AND pushed back through the return burn.
    # Only available where the architecture actually enters an atmosphere:
    # earth_surface (direct entry), leo (aerocapture + aerobraking) and
    # mars_surface.  Cislunar and lunar_surface ignore it; see uses_tps().
    use_aerocapture_return:    bool  = True
    aerocapture_dv_savings_m_s: float = 4_000   # fallback only, when elements are unusable
    heat_shield_frac_of_payload: float = 0.15   # TPS mass = 15% of returned payload

    # ─── ISRU  (return propellant manufactured at the asteroid) ──────────────
    # Return propellant is not hauled outbound; it is electrolysed from mined
    # water.  Available only where that is physically possible, a hydrolox
    # stage at a body with a non-zero ice fraction, and the rock it takes to
    # make it is dug, timed, powered and charged like any other feed.  See
    # isru_feed_kg_per_kg_propellant.
    #
    # v1.10.0 flipped this default from False to True.  It used to be False
    # because it was a blanket switch that handed free propellant to bodies
    # with no water and to propellants nobody can synthesise; now that it is
    # gated on the chemistry and costed on the feed, denying it outright would
    # be modelling every mission as having declined an option a real programme
    # would evaluate.
    use_isru_return_propellant:    bool  = True
    # Electrolysis, liquefaction and cryo storage OPEX per kg of propellant
    # made.  The mining, hauling and water-liberation energy are NOT in here; 
    # they are charged through the feed, the dig time and the power plant.
    isru_processing_usd_per_kg:    float = 50.0

    # ─── COST AMORTISATION & FINANCIAL ───────────────────────────────────────
    # Spacecraft development NRE (~$588M for OSIRIS-REx class).  If 1, the
    # first mission carries the full NRE; raise N to spread across a fleet.
    nre_amortization_missions: int   = 1
    # ─── PROGRAMME SCALE AND FLEET SIZE (v1.15.0) ────────────────────────────
    # `nre_amortization_missions` above is N, the programme size, and until
    # v1.15.0 it was an INPUT; the curve of answer-against-N was mapped by
    # re-running the entire pipeline at N = 1, 10, 100.  Three points do not
    # locate an optimum, and since v1.14.0 there IS an interior optimum to
    # locate: making market saturation see the programme's concurrent output
    # turned a monotone curve into one that comes back up.
    #
    # True searches N jointly with vehicle, propellant, return mode, propellant
    # sourcing, rendezvous apsis, power source and concentration ratio, exactly
    # as this module already requires of any architecture axis, and resolves it
    # with `selection_key` like all the others.  `nre_amortization_missions`
    # then becomes the FLOOR of the search rather than the answer.
    #
    # ⚠️  DEFAULT TRUE as of v1.17.0, and this is STILL the one axis in the
    # module that is not a correction.  Everything else on the "stopped giving
    # away" list fixes something the model was getting free; this one changes
    # the QUESTION, from "the best single mission to this rock at N missions"
    # to "the best programme built around it", sizing the fleet, the schedule
    # and N together.  Two different answers to two different questions, and
    # the flag is how you say which you are asking.
    #
    # ⚠️  READ THIS BEFORE QUOTING ANY OLDER TABLE.  Almost every figure in
    # CLAUDE.md and the README predates this default and is N = 1, so a default
    # run no longer reproduces them; set this False to do that.  This comment
    # used to argue the flip would "silently retire every committed figure at
    # once with no way to reproduce them", and the second half of that was the
    # real objection: the two settings had never been measured side by side on
    # the real population, so OFF was the only anchor anyone had.
    #
    # That is no longer true.  The full cislunar 2x2 was measured on the full
    # 1.55 M-row catalog on 2026-08-11 (calc 1.16.0) and is in versions.md, and
    # the OFF cells reproduce their committed values exactly: 26.7863x raw and
    # 20.5895x beneficiated, both unmoved across four releases.  The N = 1
    # answer is now a recorded measurement rather than a thing you would lose.
    #
    # It is NOT free.  Measured at 2.98x runtime on the full raw cislunar cell
    # on calc 1.16.0 (1,307 s -> 3,890 s); on 1.17.7 it is 1.71x (733 s ->
    # 1,253 s), which is MEASURED_CELL_SECONDS below and is where every banner
    # quoting this ratio reads it from.  The cost is real because the 2-D
    # (F, W) search prices 40
    # programmes per surviving candidate against the 1-D ladder's 8.  The
    # sample this release was developed on predicted 1.10x, and v1.15.0's
    # 1-D ladder measured 1.51x; neither carries over.
    #
    # ✅  THE KNOWN GAP THIS COMMENT USED TO DESCRIBE IS CLOSED IN v1.16.0 by
    # `model_programme_calendar` below.  It read: the fleet is only ever the
    # MINIMUM that can fly N missions, because a programme of F ships flying
    # `trips` campaigns each spans `trips × mission_duration` of calendar and
    # nothing charged for it, so buying a second ship only ever added market
    # saturation, and F never wanted to exceed ceil(N / trips).  Fleet size was
    # a one-sided decision.  It is now two-sided, and the search is
    # two-dimensional over (F, W) rather than a ladder over F.
    optimise_programme_scale:  bool  = True
    # Upper bound on the fleet search.  Not a physical limit; it is where the
    # ladder stops.  Market saturation drives revenue toward zero as concurrent
    # output grows, so the objective is eventually monotone WORSE in fleet size
    # and the optimum is interior for any sane market; this exists so a body
    # with an effectively bottomless market cannot run the ladder forever.
    # `build_profitability_catalog` reports how often the winner landed ON this
    # bound, which is the signal that it is binding rather than bounding.
    max_fleet_ships:           int   = 64
    # Points in the coarse geometric sweep over fleet size, before the
    # refinement pass.  Same idiom and same reason as
    # `concentration_search_steps`: geometric so the cheap end is sampled as
    # finely as the expensive end, endpoints always evaluated, one refinement
    # pass around the winner.  Raise it if the fleet curve is being reported at
    # the ladder's spacing rather than at an integer that means something.
    programme_search_steps:    int   = 8
    # v1.15.0.  A rig wears out on DUTY CYCLES as well as on a calendar.
    # "Mining rig service life" is 15 years and this module turned it into a
    # mission count by dividing by the stay, so at a short stay one rig served
    # 12 consecutive campaigns; a bound derived entirely from a figure about
    # not corroding.  Module 3 v1.12.0's "Mining rig maximum trips" is the
    # missing half; `rig_trips_per_ship` takes the min of the two.  False
    # restores the calendar-only cap and reproduces 1.14.2 exactly.
    model_rig_trip_limit:      bool  = True
    # ─── PROGRAMME CALENDAR TIME (v1.16.0) ───────────────────────────────────
    # A programme takes YEARS, and until v1.16.0 it took none of them.  WACC
    # compounds each mission's up-front costs over `mission_duration_yr` and
    # stops, which is right for one mission and wrong for a programme: the bus
    # NRE, the autonomy NRE and the rig are bought ONCE, at t = 0, and then
    # amortised across W campaigns that a single rig can only fly one after
    # another.  Those three lines are carried across the whole programme span
    # and were being compounded over one mission's worth of it.
    #
    # True charges the difference; see `programme_calendar_multipliers` for
    # the derivation and for why the rig's salvage credit is compounded the
    # OTHER way.  Exactly 1.0 at W = 1, so every single-mission figure in this
    # project is untouched, which is every committed figure except the
    # N = 10 / N = 100 curve.
    #
    # It also makes the programme search two-dimensional.  Campaigns-per-ship
    # was not previously a decision, every lever improved with N, so the
    # optimum was always the top of a fleet band, and the calendar charge is
    # the term that pushes back.  See `programme_options`.
    #
    # False restores 1.15.0 exactly: the calendar multipliers become 1.0, the
    # fleet ladder goes back to one dimension at N = F × trips, and
    # `missions_sharing_rig` goes back to `min(N, trips)`.
    model_programme_calendar:  bool  = True
    # Share of the NRE line already paid for inside the per-kg recurring
    # hardware rate.  The Module 3 recurring brackets ($100k-$1M/kg, from
    # NICM / SSCM / Aerospace Corp SMCM) are regressions fitted to total
    # program cost, so they carry a development component.  Charging the full
    # OSIRIS-REx $588.5M NRE on top of them double-books that component.
    # 0.30 is a mid-range de-duplication; set to 0.0 to restore the
    # pre-v1.4.0 behaviour and book both in full.
    nre_recurring_overlap_fraction: float = 0.30
    # COST OF CAPITAL.  Time-value of money: compound up-front costs over
    # mission_duration_yr, bucketed so an end-of-mission line is not inflated
    # by the whole duration.  The rate is Module 3's "Cost of capital (WACC)"
    # row (0.10), not a field here.
    #
    # ⚠️  DEFAULT FALSE as of v1.22.0, and it is the same scope objection as
    # insurance and the learning curve: a discount rate is a statement about
    # whose money this is, and this module does not know.  It prices the
    # marginal physics and hardware of moving a kilogram; 10% compounded over a
    # 5-to-12-year mission is a financing assumption layered on top of that,
    # and it is a LARGE one -- an up-front line is worth roughly twice its face
    # value under it, which is the multiplier v1.20.0 measured on the insurance
    # premium and it applies to every up-front line in the cascade.
    #
    # Two consequences worth knowing before you flip it back:
    #   • it also silences `model_programme_calendar`, whose multipliers are
    #     both exactly 1.0 at wacc = 0 by construction, so the programme's
    #     calendar charge goes with it.  That term IS the time-value of a
    #     programme's span; there is nothing left of it at a zero rate.
    #   • it removes the only term that penalises a long mission for being
    #     long in MONEY.  Duration still binds through the dig, the windows,
    #     the rig's life and `max_mission_duration_yr`, all of which are
    #     physical.
    apply_wacc_compounding:    bool  = False

    # Flat contingency on the whole cost cascade, applied after every other
    # line and before WACC.
    contingency_fraction:      float = 0.20

    # ─── VEHICLE / PROPELLANT SELECTION ──────────────────────────────────────
    # None = use everything operational; set lists to restrict candidates.
    candidate_vehicles:        Optional[List[str]] = None
    candidate_propellants:     Optional[List[str]] = None  # and the same, for propellants

    # False admits Stage 3's development and concept rows.  That is where the
    # 10,000 g launchers live, and max_payload_accel_g is what keeps them out
    # once they are admitted.
    operational_vehicles_only: bool = True
    # v1.11.0.  Module 3 v1.9.0 grew the propellant table from 7 rows to 40,
    # and 17 of the additions are development or concept hardware: nuclear
    # thermal, VASIMR, fusion, an Orion pulse drive.  Left ungated, a search
    # that maximises profit would fly every asteroid on antimatter.  This
    # mirrors `operational_vehicles_only` exactly: True keeps the search to
    # propellants that have actually moved a spacecraft.  Retired rows
    # (mercury ion) are excluded either way.
    operational_propellants_only: bool = True

    # ─── DISPLAY ─────────────────────────────────────────────────────────────
    top_n_preview:             int = 20   # rows in the printed top-N ranking
    # Cap on rows evaluated.  0 = evaluate every row, and that is the default
    # as of v1.13.0.
    #
    # It used to default to 5,000, which silently truncated any real run: Stage
    # 1 v1.1.0 can hand this module ~1.55 M asteroids and the old default threw
    # away 99.7% of them without the word "cap" appearing anywhere except one
    # line of stdout.  A cap is a thing you ask for when you want a fast
    # preview, not something a full pipeline run should discover it inherited.
    #
    # ⚠️  Budget before setting this to 0 on a big catalog.  MEASURED
    # 2026-09-11/13 at cislunar, six physical cores / 12 workers, calc 1.21.2,
    # on the full 1,555,667-row catalog:
    #     raw, N = 1            947 s     650,921 evaluable rows
    #     raw, searched       2,888 s
    #     beneficiated, N = 1 4,967 s     660,253 evaluable rows
    #     beneficiated+search 9,878 s     <- BOTH DEFAULT ON since v1.17.0
    # ⚠️  Do NOT read cislunar as the cheapest destination to run: it is the
    # second cheapest.  `lunar_surface` takes 0.40-0.73x these figures and the
    # other five 0.89-2.95x.  All twenty-eight cells are in MEASURED_DEST_SECONDS
    # below and in README.md; the figures above are that table's cislunar row.
    #
    # ⚠️  DO NOT BUDGET BY SCALING A SMALL RUN.  Scaling a 20,000-row sample
    # predicted 2.2 h for a raw run that took 42 minutes -- a 3.1x
    # overestimate.  Fixed costs (worker startup, loading a 0.88 GB catalog)
    # dominate a small run, and parallel efficiency is much better on a large
    # one, so per-row cost falls sharply with size.  It is not linear.
    #
    # ⚠️  And it misses in BOTH directions: the beneficiated cell sat here as
    # "~2.2 h ESTIMATED" from that same sample's 3.12x ratio, and measured
    # 10.6 h on calc 1.14.0 -- 4.8x the other way.  versions.md's sampling rule
    # is the general statement; the four numbers above are measurements.
    eval_row_cap:              int = 0

    # HOW a cap selects its rows.  Only consulted when eval_row_cap > 0.
    #   "stride", take every Nth row across the whole sorted catalog
    #   "head"   - take the first N rows (the pre-v1.13.0 behaviour)
    #
    # Stride is the default because the catalog reaches this module sorted by
    # semi-major axis, so `head` was never a sample of the catalog; it was the
    # innermost N bodies of it.  At eval_row_cap = 5,000 against a 1.55 M-row
    # catalog that is everything inside roughly 2.1 AU: no outer belt, no
    # Hildas, no Trojans, and a spectral mix skewed hard to S-complex.  Every
    # "quick check before the full run" was being made on a population that
    # does not resemble the full run.
    #
    # Stride keeps the cap deterministic (no RNG, no seed to record) and keeps
    # tied-row ordering stable, which the parallel path depends on -- see the
    # `imap` note about pandas' non-stable quicksort in v1.10.1.
    eval_row_sampling:         str = "stride"

    # ─── PARALLEL EVALUATION  (v1.10.1) ──────────────────────────────────────
    # Every asteroid is evaluated independently of every other one, so the main
    # loop is embarrassingly parallel -- and until v1.10.1 it ran on a single
    # core regardless of the machine.  A full beneficiated destination took
    # ~2,120 s that way on twelve idle threads.
    #
    #   0  - auto.  One worker per logical CPU, scaled down when there are too
    #        few asteroids to repay the spawn cost (no fork on Windows, so each
    #        worker is a fresh interpreter plus a pandas import).
    #   1  - force the serial path.  Use it to profile, or when an outer
    #        harness already runs one process per destination and the cores are
    #        spoken for.
    #  >1  - exactly that many workers, clamped to the CPU count.
    #
    # The answer does not depend on this setting.  Chunks are consumed in
    # submission order, so the result list -- and therefore the output CSV,
    # including the order of any profit_usd ties -- is what the serial loop
    # produced.  That was checked rather than assumed, two ways:
    #   • serial and parallel run over the same rows, CSVs compared by sha256
    #     -- cislunar beneficiated (1,200 and 6,000 rows), earth_surface raw
    #     (4,000 rows, 10 workers), mars_surface beneficiated (2,500 rows,
    #     8 workers, so the separate heliocentric transfer is exercised too).
    #     Byte-identical, all three.
    #   • the full catalog through master.py reproduced the committed table
    #     exactly: cislunar 22.9336x beneficiated (7753, B, 5.405x) and
    #     31.8269x raw.
    # If you change anything in the search, re-run the first of those before
    # trusting a parallel number.
    parallel_workers:          int = 0

    # Skip (vehicle × propellant × return mode × propellant sourcing) candidates
    # that provably cannot close their mass budget, instead of proving it again
    # inside the sizing loop for every power source and every concentration
    # ratio.  See `_combo_can_close` for why this is exact rather than a
    # heuristic: it is the loop's OWN first iteration, evaluated in closed form.
    #
    # The answer does not depend on this setting.  A candidate it prunes is one
    # `max_return_payload_kg` would have reported infeasible on entry, so there
    # is no mission behind it to lose: measured on 68,136 (combo × dv × ISRU)
    # tuples across both settings at cislunar, zero of the pruned candidates
    # produced a result when solved in full.
    #
    # Turn it OFF to check that claim on a population this repo has not tried,
    # or to profile the unpruned search.  Do not turn it off because a number
    # looks wrong; if pruning ever changes an output, that is a BUG in the
    # pre-filter and the two builds should be diffed column by column.
    prune_infeasible_combos:   bool = True

    # ─── PIPELINE VERSION ────────────────────────────────────────────────────
    # Stamped into every output CSV, and the only way to tell which code
    # produced a given catalog.  BUMP IT when a change moves any number a run
    # produces.  The rule is ONE-DIRECTIONAL: changing a number means bumping,
    # and a bump does NOT mean a number changed, which is why nothing may read
    # a version as evidence that a result moved.
    # THE CHANGELOG IS versions.md, NOT THIS COMMENT.  It used to be 1,328 lines
    # of release notes sitting right here, a second copy of a record versions.md
    # already held, which is the documentation form of the defect this project
    # keeps cataloguing; it was also what the dashboard rendered as this field's
    # help text, because ui_meta scrapes a field's comment block.  Moved out on
    # 2026-09-02.  Two places to write, neither of them here:
    #     versions.md > Releases            what the release did, and what it
    #                                       measured to say so
    #     versions.md > Module changelogs   this module's own stamp-by-stamp
    #                                       record: Stage 4 changelog
    pipeline_version: str = "1.23.0"


# ═════════════════════════════════════════════════════════════════════════════
#  MEASURED RUNTIME: the ONE place these numbers live
# ═════════════════════════════════════════════════════════════════════════════
# Wall clock for all twenty-eight cells of the 2026-09 campaign, full
# 1,555,667-row catalog, six physical cores / 12 workers, calc 1.21.2, measured
# 2026-09-11/13.  The same table is in README.md under "Beneficiation", and
# `verify_docs.py` check 9 holds every cell of it to this dict.
#
# 🚨  EVERY user-facing quote of these ratios DERIVES from here: the --help text
# and run banner in run_pipeline.py, the MASTER CALC_CONFIG READY banner
# build_master.py writes into master.py, and the sidebar estimate in ui.py.
# They used to be five hand-copied literals, and they went stale together: the
# superseded 1.16.0 figures ("~7x" beneficiation, "~3x" the programme search)
# were still being PRINTED TO THE USER ON EVERY RUN three releases after the
# measurement that retired them.  A banner is the most-read copy of a number in
# this project and was the least checked.  Re-measure, edit here, and every
# consumer moves with it.
#
# 🚨  CISLUNAR IS NOT THE CHEAPEST DESTINATION TO RUN, AND THIS COMMENT SAID IT
# WAS UNTIL 2026-09-15.  `lunar_surface` is cheaper on ALL FOUR cells -- 0.40x
# to 0.73x -- and on the raw searched cell `geo` (0.89x) and `leo` (0.89x) are
# cheaper too.  The claim was a 20-cell summary nobody re-derived, it was
# carried into this file, ui.py, run_pipeline.py, run.bat, run.sh, README and
# CLAUDE.md, and the 28-cell campaign that retired it is the one these very
# figures come from -- as did the 20-cell one before it, which already had
# lunar_surface at 0.69-0.79x.  The span away from cislunar is 0.73x to 2.95x
# on the default cell, so a destination factor is a RANGE THAT STRADDLES ONE,
# not a penalty.  Derive it from this table (see `dest_cost_span`) rather than
# typing it again.
MEASURED_DEST_SECONDS: Dict[str, Tuple[int, int, int, int]] = {
    # destination: (raw N=1, raw searched, benef N=1, benef + searched)
    # Ordered cheapest-default-cell first, which is NOT the delivery-cost order.
    "lunar_surface": (  633,  1_160,  3_021,  7_253),
    "cislunar":      (  947,  2_888,  4_967,  9_878),
    "geo":           (1_221,  2_558,  7_382, 19_902),
    "earth_surface": (1_747,  3_386, 11_000, 21_860),
    # leo's default cell is the campaign ledger's 27,817 s MINUS a 74.7 min
    # suspension that a wall clock cannot see: `campaign/results.csv` is
    # deliberately left uncorrected, and 23,335 s is the comparable figure.
    # README carries the same number behind a dagger.
    "leo":           (1_426,  2_583,  8_558, 23_335),
    "mars_surface":  (1_799,  3_982, 12_113, 25_270),
    "mars_orbit":    (2_065,  4_399, 13_135, 29_174),
}

# The four cislunar cells, by (use_beneficiation, optimise_programme_scale),
# AT THE CURRENT RELEASE.  Full catalog, 12 workers, measured 2026-09-16; the
# archives and the wall clocks are under `campaign/logs/*calc-1.22.0*`, and
# `verify_docs.py` check 9 reads them rather than trusting these four digits.
#
# 🚨  THIS USED TO BE DERIVED FROM THE CISLUNAR ROW ABOVE, AND UNPICKING THAT
# IS THE POINT RATHER THAN AN OVERSIGHT.  The row above is the 2026-09
# CAMPAIGN: seven destinations, one release, one construction, and what makes
# it worth keeping whole is that a ratio ACROSS destinations is only meaningful
# inside one release.  These four are the same cell one release later, and what
# makes them worth keeping is that they are what a run costs TODAY.  They are
# two measurements of one cell, not two copies of one measurement, so each
# keeps its own authority and neither is edited to agree with the other.
#
# 🚨  AND THE SHAPE MOVED, NOT ONLY THE LEVEL, WHICH IS WHY DERIVING THE
# BANNER FROM THE CAMPAIGN ROW HAD STOPPED BEING HONEST.  The two ratios every
# banner prints:
#
#     ratio                       calc 1.21.2     calc 1.22.0
#     beneficiation, searched        3.42x          8.11x
#     programme search, raw          3.05x          1.96x
#     both on, against raw N = 1    10.43x         15.89x
#
# So the run banner was telling a user that concentrating costs 3.4x while the
# release they were running measures 8.1x.  A banner is the most-read copy of
# a number in this project, which is the whole argument of the block above.
#
# ⚠️  THE CROSS-RELEASE READING OF THAT TABLE IS NOT ONE MEASUREMENT, AND
# NEITHER COLUMN IS A CLEAN RATIO EITHER.  The campaign cells were measured
# across 2026-09-11/13 and these across 2026-09-16, both in separate sessions,
# and this project has already scored what a ratio taken across sessions is
# worth; see `versions.md`, "Runtime: NOT measured".  What is claimed here is
# only that these four are the best available estimate of the cell they name,
# measured at the release doing the running, which is what a banner needs.
#
# ✅  ONE HALF OF THE SHAPE CHANGE IS CORROBORATED WITHOUT A CLOCK, which is
# the reason to believe the beneficiation ratio rose rather than drifted.
# `programme_options_priced` is a deterministic output, so it compares across
# releases the way a wall clock does not: summed over the searched cells it is
# 26.86 M -> 26.76 M on raw (-0.4%) and 27.99 M -> 25.93 M beneficiated
# (-7.4%), on identical row counts and an identical median concentration
# ratio.  The beneficiated searched cell therefore prices FEWER programme
# options and still takes longer, so what moved is the cost of a rung and not
# the number of them -- consistent with this release pricing a second market
# tier inside the payload knapsack, which is walked per rung.
MEASURED_CELL_CALC = "1.22.0"          # the release these four were measured at
MEASURED_CELL_SECONDS: Dict[Tuple[bool, bool], int] = {
    (False, False):     735,   # ore, one mission
    (False, True):    1_439,   # ore, searched
    (True,  False):   4_737,   # concentrate, N = 1
    (True,  True):   11_676,   # both <- DEFAULT ON
}
MEASURED_CELL_ROWS = 1_555_667   # catalog the cells above were measured on


def measured_cell_provenance(current_version: str = None) -> str:
    """" (measured at calc X)" when the cells above are behind the running code.

    Empty when they are current, so a banner reads cleanly on the common path
    and grows a stamp exactly when the figure it prints stops belonging to the
    release printing it.  This file's own rule everywhere else is that a wall
    clock is only ever true of the release it names; a banner that quotes one
    without naming a release is relying on somebody having re-measured.
    """
    if current_version is None:
        current_version = CalcConfig.pipeline_version
    if current_version == MEASURED_CELL_CALC:
        return ""
    return " (measured at calc %s)" % MEASURED_CELL_CALC


def expected_cell_seconds(destination: str, beneficiated: bool = True,
                          search: bool = True) -> int:
    """Best available wall clock for one cell, per destination.

    Cislunar comes from `MEASURED_CELL_SECONDS` (the current release) and every
    other destination from `MEASURED_DEST_SECONDS` (the 2026-09 campaign),
    because that is the newest measurement each one has.  This is what the
    launcher menus quote before somebody commits an afternoon.

    🚨  NEVER TAKE A RATIO OF TWO OF THESE.  Two destinations can come back
    from different releases, and a cross-release ratio is the arithmetic this
    project has failed at repeatedly.  `dest_cost_span` exists for that
    question and deliberately reads the campaign table alone, so every
    destination in it shares one release.
    """
    if destination == "cislunar":
        return MEASURED_CELL_SECONDS[(bool(beneficiated), bool(search))]
    i = (2 if beneficiated else 0) + (1 if search else 0)
    return MEASURED_DEST_SECONDS[destination][i]


def dest_cost_span(beneficiated: bool = True, search: bool = True,
                   base: str = "cislunar"):
    """What a cell costs at the other destinations, relative to `base`.

    Returns `((ratio, name), (ratio, name))` -- cheapest and dearest of every
    destination except `base`, on the cell named by the two flags.  On the
    default cell that is `((0.73, "lunar_surface"), (2.95, "mars_orbit"))`.

    ⚠️  THE LOW END IS BELOW ONE, and that is the whole reason this exists.
    The hand-typed `_DEST_FACTOR = (2.2, 3.0)` it replaced was introduced as
    "how much longer the others run", which assumes a penalty; `lunar_surface`
    is FASTER than cislunar on all four cells.  Callers that print this must
    say "span", not "slower".

    The NAMES come back with the ratios so a caller never has to re-derive
    which destination is which, which is how a second copy of this table would
    get started.
    """
    i = (2 if beneficiated else 0) + (1 if search else 0)
    ref = float(MEASURED_DEST_SECONDS[base][i])
    other = sorted((v[i] / ref, d)
                   for d, v in MEASURED_DEST_SECONDS.items() if d != base)
    return other[0], other[-1]


def beneficiation_cost_ratio(search: bool = False) -> float:
    """How much longer a beneficiated pass takes than a raw one, same search."""
    return (MEASURED_CELL_SECONDS[(True, search)]
            / MEASURED_CELL_SECONDS[(False, search)])


def programme_search_cost_ratio(beneficiated: bool = False) -> float:
    """How much longer the programme search takes than N = 1, same ore."""
    return (MEASURED_CELL_SECONDS[(beneficiated, True)]
            / MEASURED_CELL_SECONDS[(beneficiated, False)])


CALC_CONFIG = CalcConfig()
os.makedirs(CALC_CONFIG.output_dir, exist_ok=True)

print(f"OK  Configuration loaded - output dir: {CALC_CONFIG.output_dir}")
print(f"    Hardware       : {CALC_CONFIG.mining_hardware_kg:,.0f} kg mining rig "
      f"+ {CALC_CONFIG.return_vehicle_dry_kg:,.0f} kg return-capsule dry")
print(f"    Mining cap     : {CALC_CONFIG.max_mining_fraction:.0%} of asteroid mass per mission")
# Default ON as of v1.17.0, and the cost is quoted from MEASURED_CELL_SECONDS
# rather than typed, so a re-measurement cannot leave this banner behind.
print(f"    Beneficiation  : "
      + ("concentrate, ~%.1fx the runtime of a raw pass%s "
         "(search also prices not concentrating at all)"
         % (beneficiation_cost_ratio(CALC_CONFIG.optimise_programme_scale),
            measured_cell_provenance(CALC_CONFIG.pipeline_version))
         if CALC_CONFIG.use_beneficiation else
         "off - run-of-mine ore at bulk grade"))
print(f"    Return mode    : "
      f"{'aerocapture available (per-asteroid dv saving vs TPS mass)' if CALC_CONFIG.use_aerocapture_return else 'propulsive only'}")
print(f"    ISRU           : {'available where the rock has water' if CALC_CONFIG.use_isru_return_propellant else 'off'}")
print(f"    Architecture   : "
      f"{'searched per asteroid' if CALC_CONFIG.optimise_architecture_per_asteroid else 'fixed by config'}")
print(f"    Contingency    : {CALC_CONFIG.contingency_fraction:.0%}  |  "
      f"NRE amortised over {CALC_CONFIG.nre_amortization_missions} mission(s)")
print(f"    Programme      : "
      + ("(fleet <= %d) x (campaigns/ship) searched; N follows (~%.1fx runtime%s)"
         % (CALC_CONFIG.max_fleet_ships,
            programme_search_cost_ratio(CALC_CONFIG.use_beneficiation),
            measured_cell_provenance(CALC_CONFIG.pipeline_version))
         if CALC_CONFIG.optimise_programme_scale else
         f"fixed at N = {CALC_CONFIG.nre_amortization_missions} "
         f"(set optimise_programme_scale to search it)"))
print(f"    Insurance      : "
      + ("third-party liability + launch insurance charged"
         if CALC_CONFIG.charge_insurance else
         "NOT charged - premiums are out of scope for a marginal-cost model"))
# v1.22.0.  The calendar term is time-value, so it is INERT at a zero rate
# however this flag is set: `programme_calendar_multipliers` returns (1.0, 1.0)
# when wacc <= 0, by construction.  A banner that said "charged" while the
# cost of capital was off would be the most-read stale number in the project,
# which is the failure this repo has already shipped once.
print(f"    Calendar       : "
      + ("NOT charged (model_programme_calendar off - reproduces 1.15.0)"
         if not CALC_CONFIG.model_programme_calendar else
         "programme span charged - amortised NRE and rig compound over "
         "T + (W-1)xcadence" if CALC_CONFIG.apply_wacc_compounding else
         "on, but INERT - it is time-value, and the cost of capital is off"))
print(f"    Cost of capital: "
      + ("up-front lines compounded over the mission, bucketed by when spent"
         if CALC_CONFIG.apply_wacc_compounding else
         "NOT charged - a discount rate is out of scope for a marginal-cost "
         "model"))
print(f"    Reliability    : "
      + ("expected revenue x P(launch) x P(cruise) x P(mining); costs in full"
         if CALC_CONFIG.model_reliability else
         "NOT charged - the run answers what it costs IF IT WORKS"))
print(f"    Learning curve : "
      + ("Wright's law at %.0f%% on recurring hardware"
         % (CALC_CONFIG.learning_curve_rate * 100.0)
         if CALC_CONFIG.model_learning_curve else
         "NOT applied - no serial-production discount"))
print(f"    Market         : {CALC_CONFIG.market_model}"
      + ("" if CALC_CONFIG.market_model != "capacity_cap" else
         (" - surplus over a ceiling sells at %.0f%% of price"
          % (CALC_CONFIG.surplus_price_fraction * 100.0)
          if CALC_CONFIG.sell_surplus_at_discount else
          " - surplus over a ceiling is abandoned")))


# ─────────────────────────────────────────────────────────────────────────────
# CATALOG LOADER  (reads Module 1, 2, 3 CSVs)
# ─────────────────────────────────────────────────────────────────────────────
def _load_csv(path: str, label: str) -> pd.DataFrame:
    """Read a CSV with friendly error reporting.

    ⚠️  v1.17.7: `low_memory=False`, and it is about DETERMINISM rather than
    memory.  The default reader infers each column's dtype from CHUNKS, so the
    dtype it lands on depends on how the values happen to be distributed across
    them, which is the same "the dtype depends on the data" hazard that cost
    NEOWISE four releases, one level lower down.  It also emitted
    `DtypeWarning: Columns (3,22) have mixed types` on every single load of the
    1.55 M-row catalog (`is_neo` and `source_jpl`, both bool-plus-NaN), and a
    warning that always fires is a warning nobody reads; this file's own rule
    against suppressing warnings in `catalog.py` cuts the same way here: remove
    the cause so a real one stands out.

    ⚠️  Taken only because it was MEASURED neutral, not because it looks safe:
    on the real 1,555,667-row catalog, single-pass against chunked inference
    gives **0 of 46 columns with a different dtype and 0 with a different
    value**.  A dtype change here would propagate into the mass cascade, which
    is exactly the class of "harmless cleanup" this file keeps declining, so
    if the catalog's schema changes, re-measure before assuming it still holds.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{label} not found at {path}: has the upstream module been run?"
        )
    df = pd.read_csv(path, low_memory=False)
    print(f"       {label:28s} {len(df):>7,} rows  <-  {path}")
    return df


def _parse_minerals_list(cell):
    """Round-trip `comp_minerals` from CSV string back to a Python list.

    Module 1 writes a list-of-strings to CSV; pandas reads it back as a
    string like "['phyllosilicates', 'magnetite']".  We use ast.literal_eval
    because it safely handles None / NaN / empty-list / nested-quotes
    without exec'ing arbitrary code.
    """
    if cell is None or (isinstance(cell, float) and np.isnan(cell)):
        return []
    if isinstance(cell, list):
        return cell
    try:
        result = ast.literal_eval(cell)
        return list(result) if isinstance(result, (list, tuple)) else []
    except (ValueError, SyntaxError):
        return []


def _parse_minerals_column(col: pd.Series) -> pd.Series:
    """`_parse_minerals_list` over a whole column, priced by DISTINCT value.

    v1.17.4.  Composition is assigned from the spectral taxonomy, so this
    column takes **25 distinct values over the full 1,555,667-row catalog**, 
    and it was being `ast.literal_eval`'d once per ROW.  1.55 million parses to
    produce twenty-five answers, measured at **~28 s**: more than the 862 MB
    CSV read that precedes it, more than `integrity_check`, and more than the
    entire mission search on any sample-sized run.

    Nobody had profiled the LOAD.  Every performance release in this project
    (`1.10.1`, `1.14.1`, `1.14.2`, `1.17.1`, `1.17.2`) went after the search,
    because that is where a full-catalog run spends its hours, and a fixed
    ~30 s that a full run can ignore is most of the wall clock of the 150- and
    400-row cells this project actually verifies itself on.

    Same shape as every other memo here (`_OPS_CACHE`, `_PHASE_ORDER_CACHE`,
    `_ops_sizing_constants`): the loop was never the cost, the repetition was.

    ⚠️  Each row gets its OWN list rather than a shared one.  Nothing in this
    module mutates the column; `integrity_check` is its only reader and it
    only iterates, but a 62,000-way alias on a mutable object is exactly the
    quiet kind of trap this repo keeps finding, and 1.55 M list copies cost
    ~0.4 s against the ~28 s the parse cost.  Buy the safety.

    `factorize` rather than `unique` + `map` because it is total: NaN is a
    code like any other, so a missing composition cannot fall through a dict
    lookup that `nan != nan` would break.
    """
    codes, uniques = pd.factorize(col, use_na_sentinel=False)
    parsed = [_parse_minerals_list(u) for u in uniques]
    return pd.Series([list(parsed[c]) for c in codes],
                     index=col.index, name=col.name)


# Which module WRITES each catalog, and the config global carrying that
# module's version.  `stamp_check` reads this to compare a CSV against the code
# that produced it; before v1.19.1 it compared every one of them against
# Module 3, so `asteroids` (1.1.0) and `minerals` (1.7.1) could never match and
# the check fired on every run.
#
# The config names are looked up through `globals()` rather than referenced,
# because in a standalone `calc.py` none of them exist; only the concatenated
# `master.py` has all four in one process.  See `stamp_check`.
_CATALOG_PROVENANCE: Dict[str, Tuple[int, str]] = {
    "asteroids":   (1, "CATALOG_CONFIG"),
    "minerals":    (2, "MINERAL_CONFIG"),
    "vehicles":    (3, "TRANSPORT_CONFIG"),
    "propellants": (3, "TRANSPORT_CONFIG"),
    "delta_v":     (3, "TRANSPORT_CONFIG"),
    "ops":         (3, "TRANSPORT_CONFIG"),
}


def load_all_catalogs(config: CalcConfig) -> Dict[str, pd.DataFrame]:
    """Load and lightly normalise the three upstream catalogs."""
    print("\n  Loading upstream catalogs ...")

    transport_dir = os.path.join(config.input_dir, config.transportation_subdir)

    catalogs = {
        "asteroids": _load_csv(
            os.path.join(config.input_dir, config.asteroid_catalog_file),
            "Module 1 asteroid catalog",
        ),
        "minerals": _load_csv(
            os.path.join(config.input_dir, config.mineral_catalog_file),
            "Module 2 mineral catalog",
        ),
        "vehicles": _load_csv(
            os.path.join(transport_dir, config.launch_vehicles_file),
            "Module 3 launch vehicles",
        ),
        "propellants": _load_csv(
            os.path.join(transport_dir, config.propellants_file),
            "Module 3 propellants",
        ),
        "delta_v": _load_csv(
            os.path.join(transport_dir, config.delta_v_segments_file),
            "Module 3 Δv segments",
        ),
        "ops": _load_csv(
            os.path.join(transport_dir, config.operational_costs_file),
            "Module 3 operational costs",
        ),
    }

    # v1.19.1: the provenance map must name every catalog and no others, or
    # `stamp_check` silently stops checking whichever one was added without it.
    # Asserted here rather than in the check, because HERE is where the two can
    # drift apart: this dict is the definition and the map is the description.
    assert set(catalogs) == set(_CATALOG_PROVENANCE), (
        "load_all_catalogs and _CATALOG_PROVENANCE disagree about: %s"
        % sorted(set(catalogs) ^ set(_CATALOG_PROVENANCE)))

    # Parse Module 1's comp_minerals list-column back into actual lists
    if "comp_minerals" in catalogs["asteroids"].columns:
        catalogs["asteroids"]["comp_minerals"] = _parse_minerals_column(
            catalogs["asteroids"]["comp_minerals"]
        )

    return catalogs


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-MODULE INTEGRITY CHECK
# ─────────────────────────────────────────────────────────────────────────────
def market_config_check(config: CalcConfig) -> None:
    """Refuse a `surplus_price_fraction` outside [0, 1] (v1.22.0).

    A surplus is mass sold PAST a market ceiling, so a fraction above 1.0 says
    a kilogram is worth more for being unsellable, which is not a market model
    anyone means.  It is refused rather than clamped for the reason
    `_market_mode` refuses an unrecognised `market_model`: a silent fallback
    here prices a whole campaign against a model nobody chose, and the only
    symptom is numbers that look slightly generous.

    🚨  AND IT IS NOT MERELY MEANINGLESS, IT INVERTS AN INVARIANT.  The tiered
    knapsack identifies a phase's full-price tier as the first time that phase
    is reached, which is the same question as "the dearer of its two tiers"
    only while the discount is at most full price.  Above 1.0 the discounted
    tier sorts first and draws the market allowance, and the capped load comes
    out worth MORE than the uncapped one -- measured at 1.5 as 945,000 against
    an uncapped 900,000.  That is exactly what `verify.py` check 7 exists to
    catch, so it must not be reachable by configuration.

    Negative is refused on the same line and for a duller reason: it would pay
    the programme to overproduce.
    """
    frac = float(getattr(config, "surplus_price_fraction", 0.0))
    if not 0.0 <= frac <= 1.0:
        raise ValueError(
            "surplus_price_fraction must be between 0.0 and 1.0, not %r. "
            "It is what a kilogram past a market ceiling fetches as a "
            "fraction of the full price; 0.0 is v1.21.0's hard wall and 1.0 "
            "removes the ceiling entirely." % (frac,))


def destination_check(catalogs: Dict[str, pd.DataFrame], config: CalcConfig) -> None:
    """Verify Module 2 priced the material for the destination Module 4 flies to.

    This is the one cross-module mismatch that silently produces a
    plausible-looking but meaningless answer.  Module 2 stamps every row with
    the destination it priced for; if that disagrees with the architecture
    this module is about to cost, the run pairs (say) cislunar-depot prices
    with a re-entry-capsule mission; exactly the inconsistency the
    destination field exists to prevent.
    """
    minerals = catalogs.get("minerals")
    if minerals is None or "delivery_destination" not in minerals.columns:
        print("     WARN   Module 2 catalog carries no `delivery_destination` "
              "column (pre-v1.3.0) - cannot verify pricing matches this "
              "mission architecture.  Re-run Module 2.")
        return

    stamped = str(minerals["delivery_destination"].iloc[0]).strip().lower()
    mine    = str(config.delivery_destination).strip().lower()
    if stamped == mine:
        arch = delivery_architecture(mine)
        print(f"     OK  Delivery destination '{mine}' - {arch['label']}")
        return

    print(f"     FAIL  DESTINATION MISMATCH - the prices and the mission disagree.")
    print(f"          Module 2 priced the material for : {stamped}")
    print(f"          Module 4 is flying it to         : {mine}")
    print(f"        -> Every profit number in this run is meaningless.  Set both")
    print(f"          MINERAL_CONFIG.delivery_destination and")
    print(f"          CALC_CONFIG.delivery_destination to the same value and")
    print(f"          re-run Module 2 before Module 4.")


def integrity_check(catalogs: Dict[str, pd.DataFrame]) -> None:
    """Verify every mineral named by Module 1 is priced by Module 2.

    This catches the silent failure where a future Module 1 taxonomy edit
    introduces a new mineral that Module 2 has no row for, without this
    check, those minerals would simply not contribute to value (silently).
    """
    print("\n  Integrity check - Module 1 <-> Module 2 mineral coverage ...")

    asteroids   = catalogs["asteroids"]
    mineral_set = set(catalogs["minerals"]["name"].astype(str))

    if "comp_minerals" not in asteroids.columns:
        print("     WARN  asteroid catalog has no `comp_minerals` column - skipping check")
        return

    # Every unique mineral name the asteroid catalog references.
    #
    # v1.17.4: over the DISTINCT compositions rather than over every row.  This
    # walked 1.55 million lists: 6.2 million generator steps and 1.55 million
    # `set.update` calls, ~4 s, to build a set of twelve names out of the
    # twenty-five distinct compositions the taxonomy can produce.  Same finding
    # as `_parse_minerals_column` directly above it, and found the same way.
    #
    # A list is not hashable, so the distinct compositions are keyed as tuples
    # and `factorize` reduces them to one entry per composition present.
    #
    # ⚠️  The `isinstance` guard is the OLD loop's guard, kept and not folded
    # into a bare `.map(tuple)`.  `load_all_catalogs` hands this column over
    # already parsed, but nothing forces a caller to, and `tuple()` of the
    # UNPARSED string explodes it into one entry per character, which would
    # report a screenful of one-letter minerals as missing from Module 2.  A
    # loud false alarm in the check that exists to be trusted is still a
    # failure, and skipping non-lists is what the row-by-row walk did.
    referenced = set()
    _, comp_uniques = pd.factorize(
        asteroids["comp_minerals"].map(
            lambda v: tuple(v) if isinstance(v, list) else None),
        use_na_sentinel=False,
    )
    for mins in comp_uniques:
        if isinstance(mins, tuple):
            referenced.update(str(m) for m in mins if m)

    missing = referenced - mineral_set
    extra   = mineral_set - referenced

    if missing:
        print(f"     FAIL  {len(missing)} mineral(s) named by Module 1 but ABSENT in Module 2:")
        for m in sorted(missing):
            print(f"          * {m}")
        print("        -> Module 4 will treat these as zero-value contributions.")
    else:
        print(f"     OK  All {len(referenced)} referenced minerals are priced by Module 2")

    if extra:
        # Not an error; Module 2 prices elements (Au, Pt, …) that Module 1
        # doesn't name directly.  Just informational.
        print(f"     NOTE   Module 2 prices {len(extra)} extra rows not named by Module 1 "
              f"(expected: elements + ice + bulk categories)")

    schema_check(catalogs)
    # The VALUE half of the same question: schema_check asks whether the
    # columns and rows are present, stamp_check asks whether the file was
    # written by the Module 3 in this process.  A catalog can pass the
    # first and fail the second, which is exactly the v1.12.0 argon case.
    stamp_check(catalogs)


# Columns Module 3 v1.9.0 added that Module 4 v1.11.0 needs.  Each maps to the
# behaviour that silently reverts when the column is absent.
_MODULE3_REQUIRED = {
    "propellants": {
        "tank_kg_per_L":  "propellant tankage reverts to ZERO MASS — every tank flies free",
        "status":         "the maturity gate cannot fire; development and concept rows may enter the search",
        "restartable":    "solid motors are not excluded, and a solid cannot fire a return burn",
        "propellantless": "sails are not excluded and report an unbounded payload",
        "thruster_kg_per_n":   "the electric stage is sized on POWER alone — micronewton devices (PPT, electrospray, FEEP) fly as multi-tonne cargo tugs",
        "thruster_efficiency": "every electric thruster reverts to one shared 60% efficiency; a PPT is really ~8% and needs ~9x the array",
    },
    "vehicles": {
        "tanker_flights_for_escape": "orbital refuelling is not charged; a refuelled escape payload is priced at one launch",
        "origin": "non-Earth launch systems are not excluded, and their payload columns are annual throughput",
    },
}

# ── Module 3 ops ROWS this version needs  (v1.14.0) ──────────────────────────
# The ops table is keyed by category, not by column, so a missing figure is a
# missing ROW and `schema_check` above, which tests columns, cannot see it.
# CLAUDE.md names that hole explicitly ("schema_check() checks COLUMNS, not
# VALUES, and that is a real hole"), and it has already cost one full
# measurement pass: the v1.12.0 argon tables were rewritten, Stage 3 was
# re-run, the CSV did not land, and two full-catalog runs were measured against
# the table being replaced with nothing anywhere saying so.
#
# `_ops_value` defaults every one of these, silently and flatteringly, so the
# rows that would revert a MODEL TERM (rather than nudge a price) are named
# here with the behaviour their absence restores.
_MODULE3_REQUIRED_OPS = {
    "Eclipse / night-side dark fraction":
        "the processing plant is sized on a continuous draw — the sun never sets on the rig",
    "Energy storage usable specific energy":
        "night-side energy storage has no specific energy and is not massed",
    "Power-system row baseline dark period":
        "the LEO-eclipse battery inside the 60 W/kg row is charged twice",
    "Volatile cargo containment":
        "water cargo flies with no sealed hold — it is sold at the depot and never kept cold",
    "RTG specific power":
        "the radioisotope branch is unreachable; every distant body flies a 1/r²-starved array",
    "Power processing unit specific mass":
        "the PPU reverts to the lumped 8 kg/kW thruster+PPU figure",
    "Mining rig maximum trips":
        "the rig wears out on a calendar alone — 12 consecutive campaigns at a short stay, "
        "so the fleet never has to grow and programme scale is bounded by nothing",
}


def schema_check(catalogs: Dict[str, pd.DataFrame]) -> None:
    """Warn when an upstream table predates the columns this module reads.

    Stage 3 is the cheap stage, so it is the one people skip re-running, and
    every one of these columns fails SILENTLY when missing, because the code
    that reads them is written to tolerate a pre-v1.9.0 catalog.  Tolerating it
    quietly is how a run ends up flying every propellant tank for free and
    reporting a number that looks like a result.

    This is the same lesson as `_SSODNET_REQUIRED` in Module 1: a projection
    that tolerates missing columns must still ASSERT the ones it cannot work
    without.
    """
    stale = []
    for key, needed in _MODULE3_REQUIRED.items():
        df = catalogs.get(key)
        if df is None:
            continue
        for col, consequence in needed.items():
            if col not in df.columns:
                stale.append((key, col, consequence))

    # v1.14.0: the ops table is row-keyed, so a missing figure is a missing ROW
    # and the column loop above cannot see it.  Same failure, same silence.
    ops = catalogs.get("ops")
    if ops is not None and "category" in ops.columns:
        have = set(ops["category"].astype(str))
        for row, consequence in _MODULE3_REQUIRED_OPS.items():
            if row not in have:
                stale.append(("ops", f"[{row}]", consequence))

    if not stale:
        return
    print(f"\n     WARN  Module 3 catalog is STALE - {len(stale)} column(s)/row(s) "
          f"this version reads are missing:")
    for key, col, consequence in stale:
        print(f"          * {key}.{col}  ->  {consequence}")
    print("        -> Re-run Stage 3 (transportation).  It takes seconds, and "
          "until you do, the numbers below are not comparable to any "
          "committed figure.")


def stamp_check(catalogs: Dict[str, pd.DataFrame]) -> bool:
    """Compare the version STAMPED in each upstream CSV against the module that
    WROTE it.  Returns True when they agree or cannot be compared.

    This closes the half of the staleness problem `schema_check` cannot see.
    That one asks whether the columns and rows this module reads are PRESENT;
    it passes cleanly on a catalog whose VALUES are a release out of date,
    because editing a density or a boil-off rate leaves the schema identical.

    It is not a hypothetical.  During v1.12.0 the argon rows were rewritten,
    Stage 3 was re-run, the CSV did not actually land, and two full-catalog
    runs plus a determinism sweep were measured against the table that was
    being replaced.  Nothing anywhere said so.  The documented mitigation was
    to read Stage 4's row counts against what Stage 3 said it wrote, by eye,
    every time -- which is the kind of habit that works until the day it
    matters.

    What makes this checkable at all is that Stage 3 already stamps its
    `pipeline_version` into every CSV it writes, so the file records the code
    that produced it.  Comparing that to the live module turns "changing any
    number means bumping the version" from a rule someone has to remember into
    one the pipeline enforces on the way past.

    ⚠️  It is a DIAGNOSTIC, not an import.  The four config globals exist only
    when every module is in one process, which is `master.py`, the normal path.
    A standalone `calc.py` run has no way to know what Module 1, 2 or 3
    currently says, so each comparison it cannot make is skipped rather than
    invented.  That is deliberate: the modules hand off through CSVs on disk
    and must not grow an import edge for a warning.

    🚨  v1.19.1 FIXED WHAT THIS COMPARED, AND IT HAD BEEN WRONG SINCE v1.17.8
    SHIPPED IT.  Every frame in `catalogs` was compared against
    `TRANSPORT_CONFIG`, including `asteroids` (written by Module 1) and
    `minerals` (Module 2).  Those can never equal a transportation version, so
    the check fired on **every run**, named the wrong module, and then advised
    "Re-run Stage 3", which is the one action CLAUDE.md documents as destroying
    every `verify.py` baseline you hold.  A check that cries wolf toward a
    destructive remedy is worse than no check, and this one had been doing it
    for two releases.  See `_CATALOG_PROVENANCE`.

    ⚠️  A LAG HERE IS OFTEN DELIBERATE, which is why the wording below reports
    rather than instructs.  catalog v1.1.1 and transportation v1.12.1 both
    changed no CSV byte and deliberately did NOT re-run their stage; their
    release notes say so.  This cannot tell that apart from a write that failed
    to land, because both look like "the file predates the module".  It reports
    the fact and names where the answer is.
    """
    stale, unknown = [], []
    for key, df in sorted(catalogs.items()):
        if df is None or "pipeline_version" not in getattr(df, "columns", ()):
            continue
        provenance = _CATALOG_PROVENANCE.get(key)
        if provenance is None:
            unknown.append(key)           # load_all_catalogs' assert should
            continue                      # have caught this; say so anyway
        stage, config_name = provenance
        live = getattr(globals().get(config_name), "pipeline_version", None)
        if not live:
            continue                      # standalone run: nothing to compare
        for stamped in sorted({str(v) for v in df["pipeline_version"]
                               .dropna().unique()}):
            if stamped != str(live):
                stale.append((key, stage, stamped, str(live)))

    if unknown:
        print(f"\n     WARN  stamp_check has no provenance entry for "
              f"{', '.join(unknown)}; those files were NOT checked.")

    if not stale:
        return not unknown

    print(f"\n     WARN  {len(stale)} upstream CSV(s) were written by a "
          f"different build of the module that owns them:")
    for key, stage, stamped, live in stale:
        print(f"          * {key}.csv stamped {stamped} - "
              f"Stage {stage} in this process is {live}")
    print("        -> The columns and rows are all present, so nothing else "
          "will complain, but a reference VALUE may be a release out of date.")
    print("        -> This may be DELIBERATE. Several releases changed no CSV "
          "byte and chose not to re-run their stage; read the release note in "
          "versions.md before acting on this.")
    print("        -> If you do re-run Stage 1, 2 or 3, it REFETCHES and "
          "overwrites the only copy of its CSV, and every verify.py baseline "
          "stops reproducing. Copy asteroid_pipeline/*.csv first.")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# MINERAL-VALUE LOOKUPS
# ─────────────────────────────────────────────────────────────────────────────
# Rare-metal elements that get scaled by per-asteroid PGM-enrichment
# factor (Module 1 v1.0.4's comp_pgm_enrichment column).  The base metals
# (iron, nickel, cobalt) in nickel-iron alloy are NOT scaled; they are
# bulk Fe-Ni alloy abundance, not PGM enrichment.
RARE_METAL_ELEMENTS: set = {
    "platinum", "palladium", "rhodium",
    "iridium",  "osmium",    "ruthenium",
    "gold",
}


# Same single-slot memo as _OPS_CACHE, for the mineral table.  Every asteroid
# re-prices the same 4 bulk minerals, and nickel-iron alone fans out to ~10
# element lookups, so this is ~19 full-DataFrame scans per asteroid otherwise.
# Holds price and yields side by side since both are keyed by mineral name.
_MINERAL_CACHE: Tuple[Optional[pd.DataFrame], Dict[str, Tuple[Optional[float], str]]] = (None, {})


def _mineral_table(mineral_df: pd.DataFrame) -> Dict[str, Tuple[Optional[float], str]]:
    """name → (price_usd_per_kg, yields_json) mapping, built once and memoised."""
    global _MINERAL_CACHE
    cached_df, mapping = _MINERAL_CACHE
    if cached_df is mineral_df:
        return mapping

    has_yields = "yields_json" in mineral_df.columns
    yields_col = mineral_df["yields_json"] if has_yields else [None] * len(mineral_df)

    mapping = {}
    for name, price, yields in zip(
        mineral_df["name"], mineral_df["price_usd_per_kg"], yields_col,
    ):
        key = str(name)
        if key in mapping:
            continue                      # first match wins, as .iloc[0] did
        mapping[key] = (
            float(price) if pd.notna(price) else None,
            yields if isinstance(yields, str) else "",
        )
    _MINERAL_CACHE = (mineral_df, mapping)
    return mapping


_MARKET_CACHE: Tuple[Optional[pd.DataFrame], Dict[str, float]] = (None, {})


def market_table(mineral_df: pd.DataFrame) -> Optional[Dict[str, float]]:
    """name → annual absorbable quantity (kg/yr), memoised.

    Returns None for a pre-v1.5.0 Module 2 catalog that carries no
    `annual_market_kg` column, which switches saturation modelling off rather
    than silently assuming an infinite market.
    """
    global _MARKET_CACHE
    cached_df, mapping = _MARKET_CACHE
    if cached_df is mineral_df:
        return mapping or None
    if "annual_market_kg" not in mineral_df.columns:
        _MARKET_CACHE = (mineral_df, {})
        return None
    mapping = {}
    for name, qty in zip(mineral_df["name"], mineral_df["annual_market_kg"]):
        if pd.notna(qty):
            mapping.setdefault(str(name), float(qty))
    _MARKET_CACHE = (mineral_df, mapping)
    return mapping or None


def _mineral_price(mineral_df: pd.DataFrame, name: str) -> Optional[float]:
    """Look up `price_usd_per_kg` for a mineral / element by exact name."""
    entry = _mineral_table(mineral_df).get(name)
    return None if entry is None else entry[0]


def _mineral_implied_value(
    mineral_df:     pd.DataFrame,
    mineral_name:   str,
    pgm_enrichment: float = 1.0,
) -> Optional[float]:
    """For a mineral, compute its bulk $/kg from elemental yields.

    Mirrors Module 2's `mineral_to_element_value` but scales the rare-metal
    portion (Pt, Pd, Rh, Ir, Os, Ru, Au) by `pgm_enrichment`, the per-
    asteroid factor sourced from Module 1's comp_pgm_enrichment column.
    Base metals (Fe, Ni, Co) and non-PGM yields are unaffected.

    For pgm_enrichment = 1.0 the behaviour is identical to the v1.3.3
    function (chondritic / mean-iron-meteorite baseline).  For an M-type
    asteroid with comp_pgm_enrichment = 2.0, the PGM portion doubles.

    Returns the direct row price as a fallback if yields are empty.
    """
    entry = _mineral_table(mineral_df).get(mineral_name)
    if entry is None:
        return None

    try:
        yields = json.loads(entry[1] or "{}")
    except (json.JSONDecodeError, TypeError, AttributeError):
        yields = {}

    if not yields:
        return _mineral_price(mineral_df, mineral_name)

    enrichment = float(pgm_enrichment) if pgm_enrichment else 1.0
    total = 0.0
    for element, fraction in yields.items():
        elem_price = _mineral_price(mineral_df, element)
        if elem_price is None:
            continue
        eff_fraction = float(fraction)
        if element in RARE_METAL_ELEMENTS:
            eff_fraction *= enrichment
        total += eff_fraction * elem_price
    return total if total > 0 else _mineral_price(mineral_df, mineral_name)


# ─────────────────────────────────────────────────────────────────────────────
# PER-ASTEROID BULK-MATERIAL $/kg
# ─────────────────────────────────────────────────────────────────────────────
# The asteroid's composition is assumed uniform (per user spec).  Mined
# bulk material is therefore a weighted blend of:
#   metal_fraction      × nickel-iron implied value  (Fe + Ni + Co + PGMs)
#   silicate_fraction   × silicates bulk price       ($0.05/kg-class)
#   carbon_fraction     × carbon bulk price          ($0.20/kg-class)
#   ice_fraction        × water price                ($2,500/kg in-space proxy)
#
# This maps Module 1's broad taxonomy fractions onto the most-appropriate
# Module 2 row.  An X-complex (M-type) asteroid is dominated by metal_frac;
# a C-complex by carbon + silicate + ice; a V-type by silicate.

FRACTION_TO_MINERAL: Dict[str, str] = {
    "comp_metal_fraction":    "nickel-iron",
    "comp_silicate_fraction": "silicates",
    "comp_carbon_fraction":   "carbon",
    "comp_ice_fraction":      "water",
}


# ── Composition is a per-TAXONOMY fact, not a per-row one  (v1.17.6) ────────
# `asteroid_bulk_value_usd_per_kg`, `asteroid_phase_table` and
# `asteroid_best_phase_usd_per_kg` read exactly five values off the row, the
# PGM enrichment and the four taxonomy fractions, and nothing else.  All five
# come out of Module 1's `enrich_composition`, which derives them from
# `spectral_type` alone: 76 distinct types across 1,555,667 rows, collapsing to
# ~25 distinct composition tuples (11 in a 4,000-row stride).
#
# So `evaluate_asteroid` was walking `FRACTION_TO_MINERAL` three times per
# asteroid, with a `pd.isna` on a scalar per entry, at ~1 us each, to
# re-derive one of a couple of dozen answers, once for every body in the
# catalog.  Measured on a 4,000-row stride of the real catalog:
#
#     asteroid_bulk_value_usd_per_kg   14.84 us/row  ->  23.1 s / full pass
#     asteroid_phase_table             13.97 us/row  ->  21.7 s / full pass
#     asteroid_best_phase_usd_per_kg   27.66 us/row  ->  43.0 s / full pass
#
# ~88 s of every full-catalog pass, paid by every row whether or not it turns
# out to be evaluable.  Exactly the pattern v1.17.4 found on both sides of the
# CSV boundary, "a column with few distinct values and one Python call per
# row", in the one place between them that release did not look.
#
# ⚠️  `asteroid_best_phase_usd_per_kg` calls the bulk function itself, so a
# beneficiated run computed the bulk value TWICE per asteroid.  The memo closes
# that as a side effect; it is not a separate change.
#
# Bit-identical by construction: the same key re-runs the same walk over the
# same mineral table, so the cached floats ARE the floats the walk produced.
_COMPOSITION_CACHE: Tuple[Any, Dict[Tuple[Any, ...], Any]] = (None, {})


def _composition_cache(mineral_df: pd.DataFrame) -> Dict[Tuple[Any, ...], Any]:
    """The memo for `mineral_df`, cleared when the frame changes.

    Single-slot on frame IDENTITY, the same shape as `_MINERAL_CACHE`,
    `_MARKET_CACHE` and `_OPS_CACHE`, prices are what the answers are made of,
    so a re-priced Stage 2 catalog must not read a cached value.
    """
    global _COMPOSITION_CACHE
    cached_df, entries = _COMPOSITION_CACHE
    if cached_df is not mineral_df:
        entries = {}
        _COMPOSITION_CACHE = (mineral_df, entries)
    return entries


# The five values the three functions below read, in a fixed order.
_COMPOSITION_KEY_COLS: Tuple[str, ...] = (
    ("comp_pgm_enrichment",) + tuple(FRACTION_TO_MINERAL)
)


class _CompositionValues:
    """The three composition-derived answers, filled in as they are asked for.

    A tiny `__slots__` object rather than a mutable 3-list because the three
    fields are read by name in three different functions and a positional index
    would be one more thing to keep in step -- the same reason
    `_ops_cost_constants` is unpacked in a single statement.  `None` means "not
    computed yet", which is distinguishable from every value these three can
    legitimately return (all are floats, or a list).
    """
    __slots__ = ("bulk", "phases", "best")

    def __init__(self) -> None:
        """All three slots start as None, meaning "not computed yet".

        Distinguishable from every value they can legitimately hold, which are
        all floats or a list, so a miss is never confused with a real answer of
        zero. `__slots__` is what keeps ~25 of these off the per-instance dict.
        """
        self.bulk = None
        self.phases = None
        self.best = None


def _composition_entry(
    entries: Dict[Tuple[Any, ...], "_CompositionValues"], key: Tuple[Any, ...],
) -> "_CompositionValues":
    """The entry for `key`, created empty on first use."""
    hit = entries.get(key)
    if hit is None:
        hit = entries[key] = _CompositionValues()
    return hit


def _composition_key(asteroid_row: Row) -> Optional[Tuple[Any, ...]]:
    """Hashable identity of a row's composition, or None if it is not cacheable.

    ⚠️  NaN and None normalise to the SAME key, and that is required rather
    than convenient: all three consumers test `x is None or pd.isna(x)` and
    take the identical branch either way, so two rows that differ only in how
    their missing value is spelled must share an answer.  A bare `float('nan')`
    key would also never hit, two NaNs are not equal, so the cache would
    silently stop caching for exactly the rows that have gaps, which is the
    quiet-wrong-answer shape in its performance clothing (see `_UNSET` in
    `_isru_propellant_consts`).

    ⚠️  Anything that is not a real number or None returns None, which sends
    the caller down the uncached path rather than inventing a key for a value
    whose branch behaviour has not been checked.  `to_dict("records")` on the
    float64 composition columns yields plain floats, so the fast path is what
    the pipeline actually takes; this is the door for a hand-built row.
    """
    key: List[Any] = []
    for col in _COMPOSITION_KEY_COLS:
        v = asteroid_row.get(col)
        if v is None:
            key.append(None)
        elif isinstance(v, float):
            key.append(None if v != v else v)          # NaN -> None
        elif isinstance(v, int) and not isinstance(v, bool):
            key.append(float(v))
        else:
            return None
    return tuple(key)


def _pgm_enrichment(asteroid_row: Row) -> float:
    """Per-asteroid PGM enrichment, defaulted to the chondritic baseline.

    Module 1 has supplied `comp_pgm_enrichment` since v1.0.4; 1.0 is what an
    older catalog means, not a missing value to reject.
    """
    pgm = asteroid_row.get("comp_pgm_enrichment")
    if pgm is None or pd.isna(pgm):
        return 1.0
    return float(pgm)


def _phase_prices(
    asteroid_row: Row, mineral_df: pd.DataFrame,
) -> Iterator[Tuple[str, float, float]]:
    """(phase, fraction, usd_per_kg) for every phase actually PRESENT.

    The one walk of `FRACTION_TO_MINERAL` shared by `asteroid_phase_table` and
    `asteroid_best_phase_usd_per_kg`, which had it written out twice.  Phases
    with no fraction or no price are skipped; you cannot select what is not
    there.

    ⚠️  `asteroid_bulk_value_usd_per_kg` deliberately does NOT use this: it
    admits a fraction of exactly 0.0 where this skips it.  Unifying the third
    copy would be numerically negligible and would still cost the bit-identity
    every release here is argued from; see the v1.14.2 phase-sort warning.
    """
    pgm_enrichment = _pgm_enrichment(asteroid_row)
    for frac_col, mineral_name in FRACTION_TO_MINERAL.items():
        frac = asteroid_row.get(frac_col)
        if frac is None or pd.isna(frac) or float(frac) <= 0.0:
            continue
        if mineral_name == "nickel-iron":
            price = _mineral_implied_value(mineral_df, mineral_name, pgm_enrichment)
        else:
            price = _mineral_implied_value(mineral_df, mineral_name)
        if price is None:
            continue
        yield mineral_name, float(frac), float(price)


def asteroid_bulk_value_usd_per_kg(
    asteroid_row: Row, mineral_df: pd.DataFrame,
) -> float:
    """Composite USD/kg for the bulk material of one asteroid.

    v1.17.6: memoised per composition: see `_composition_key`.  The walk below
    is unchanged and is still the only statement of the blend; this caches its
    answer.

    v1.3.4, applies per-asteroid PGM enrichment to the metal fraction.
    Module 1 v1.0.4+ provides `comp_pgm_enrichment` (default 1.0× chondritic
    baseline; 2.0× for differentiated M-type cores; 0.2× for V-type basaltic
    crust; 0.5× for mantle fragments).  Multiplies only the rare-metal yields
    in nickel-iron, base metals (Fe, Ni, Co) and non-metal categories
    (silicates, carbon, water) are unaffected.

    v1.3.3, "Other" residual mass (Module 1 fractions sum to 0.73-0.96
    across types) was silently zero-valued; now treated as bulk silicate
    at $0.05/kg floor.
    """
    key = _composition_key(asteroid_row)
    if key is not None:
        entries = _composition_cache(mineral_df)
        hit = entries.get(key)
        if hit is not None and hit.bulk is not None:
            return hit.bulk

    pgm_enrichment = _pgm_enrichment(asteroid_row)

    total    = 0.0
    frac_sum = 0.0
    for frac_col, mineral_name in FRACTION_TO_MINERAL.items():
        frac = asteroid_row.get(frac_col)
        if frac is None or pd.isna(frac):
            continue
        # Only the metal-fraction → nickel-iron lookup is enrichment-sensitive
        # (PGMs ride in the metal phase).  Silicate / carbon / water yields
        # are unaffected by differentiation history.
        if mineral_name == "nickel-iron":
            price = _mineral_implied_value(mineral_df, mineral_name, pgm_enrichment)
        else:
            price = _mineral_implied_value(mineral_df, mineral_name)
        if price is None:
            continue
        f = float(frac)
        total    += f * float(price)
        frac_sum += f

    # Residual "other" mass; value at silicate floor so it doesn't vanish.
    if 0.0 < frac_sum < 1.0:
        other_frac     = 1.0 - frac_sum
        silicate_price = _mineral_price(mineral_df, "silicates") or 0.05
        total += other_frac * float(silicate_price)

    if key is not None:
        _composition_entry(entries, key).bulk = total
    return total


# ─── THE ONE PHASE STAGE 2 HAS NEVER HEARD OF  (v1.21.1) ─────────────────────
# `asteroid_phase_table` invents the composition residual, and Stage 2's mineral
# catalog has no row for it, so `markets.get(name)` missed and it took the
# infinite default: **priced at the `silicates` quote and bounded by nothing.**
#
# That is defect class 1 in market form -- a quantity with a price in one half
# of the model and no counterpart in the other -- and it hid for the same reason
# that class always hides.  Under the v1.14.0 demand curve every OTHER commodity
# in the haul was bounded, so the blended multiplier fell on every row anyway and
# the hole never showed as a hole.  A wall does not blend: a row whose bounded
# commodities all sit inside their ceilings feels nothing at all, and one
# unbounded phase is then the whole of a monotone-in-N objective.
#
# The alias is a MAPPING rather than a new market row on purpose.  The residual
# is not a commodity anybody trades; it is this module's name for "the rest of
# the rock", so inventing a Stage 2 row for it would put a fiction in the
# reference data.  Priced as silicates, bounded as silicates, in one place.
_RESIDUAL_PHASE = "other (bulk silicate)"
_PHASE_MARKET_ALIAS: Dict[str, str] = {_RESIDUAL_PHASE: "silicates"}


def phase_market_key(markets: Optional[Dict[str, float]], phase: str) -> str:
    """The MARKET a phase sells into, which is not always the phase's own name.

    v1.21.2.  `phase_market_kg` answers "how many kg/yr", and two phases can
    get the same answer for two different reasons: because they are the same
    market, or because they happen to have equal ceilings.  Only this function
    can tell those apart, and the difference is a whole allowance.

    ⚠️  IT TAKES `markets` FOR ONE REASON: TO RESOLVE THE ALIAS THE SAME WAY
    `phase_market_kg` DOES.  That function prefers a phase's OWN row and falls
    back to the alias, so a keyless version of this one would disagree with it
    the moment Stage 2 gained a row for an aliased phase -- pooling onto
    `silicates` while drawing a different ceiling.  Nothing today has both, and
    that is exactly when to make two functions agree by construction rather
    than by coincidence.

    🚨  THE ALIAS ABOVE MEANT "ONE SHARED CEILING" AND WAS IMPLEMENTED AS "A
    SECOND COPY OF IT".  v1.21.1 gave the composition residual the `silicates`
    ceiling it was already priced against, which was right, and every consumer
    then asked `phase_market_kg` per PHASE and got the full allowance twice --
    once for `silicates` and once for `other (bulk silicate)`.  The comment
    above already said "priced as silicates, bounded as silicates, in one
    place"; that was the intent, and the code gave each its own place.  The two
    co-occur on 100% of bodies and are a median 84% of the load, so this was
    not a corner.
    """
    if markets and phase in markets:
        return phase
    alias = _PHASE_MARKET_ALIAS.get(phase)
    return alias if alias is not None else phase


def phase_market_kg(markets: Optional[Dict[str, float]], phase: str) -> float:
    """Annual ceiling in kg/yr for one PHASE of the payload, or inf.

    The single place a phase name is turned into a market ceiling, so the
    alias above cannot be honoured at one call site and forgotten at another.
    Infinity is still the answer for a phase with no market and no alias, and
    that is deliberate: it means "nothing here bounds this", which the run
    banner reports rather than silently assuming a number.

    ⚠️  THIS IS A CEILING, NOT AN ENTITLEMENT.  Two phases sharing a market
    each get the same number back from here, and that is correct; what would
    be wrong is spending it twice.  Pair every call with `phase_market_key`
    and pool by that key.  See v1.21.2.
    """
    if not markets:
        return float("inf")
    hit = markets.get(phase)
    if hit is None:
        alias = _PHASE_MARKET_ALIAS.get(phase)
        hit = markets.get(alias) if alias is not None else None
    return float("inf") if hit is None else float(hit)


def asteroid_phase_table(
    asteroid_row: Row, mineral_df: pd.DataFrame,
) -> List[Tuple[str, float, float]]:
    """[(phase, mass_fraction, usd_per_kg)] for one asteroid (v1.6.0).

    The same four taxonomy fractions `asteroid_bulk_value_usd_per_kg` blends,
    but kept SEPARATE so a mission can choose what to load rather than being
    handed the mean.  The residual (Module 1's fractions sum to 0.73-0.96) is
    included as bulk silicate, matching the bulk function's floor treatment.

    Phases with zero fraction are dropped; you cannot select what is not
    there.

    v1.17.6: memoised per composition; see `_composition_key`.

    ⚠️  A COPY of the cached list is returned, deliberately.  Nothing in this
    module mutates a phase table, but v1.17.4 records the other half of that
    argument: handing a million rows one shared mutable object is a trap
    whether or not today's code springs it.  A copy also keeps the aliasing
    exactly as it is now; `_PHASE_ORDER_CACHE` is keyed on list IDENTITY, so
    one list per asteroid is what its single slot was measured against.  The
    copy is ~0.15 us against the ~14 us walk it replaces.
    """
    key = _composition_key(asteroid_row)
    if key is not None:
        entries = _composition_cache(mineral_df)
        hit = entries.get(key)
        if hit is not None and hit.phases is not None:
            return list(hit.phases)

    phases: List[Tuple[str, float, float]] = []
    frac_sum = 0.0
    for mineral_name, frac, price in _phase_prices(asteroid_row, mineral_df):
        phases.append((mineral_name, frac, price))
        frac_sum += frac

    if 0.0 < frac_sum < 1.0:
        # Composition fractions sum to 0.73-0.96; the remainder is undifferentiated
        # rock and is valued at the bulk-silicate floor.  ⚠️  It is priced at the
        # `silicates` QUOTE, which is why `_PHASE_MARKET_ALIAS` below must give it
        # the `silicates` CEILING: a phase that declares itself silicates for
        # price and not for quantity is priced in one half of the model and
        # unbounded in the other.
        silicate_price = _mineral_price(mineral_df, "silicates") or 0.05
        phases.append((_RESIDUAL_PHASE, 1.0 - frac_sum, float(silicate_price)))

    if key is not None:
        _composition_entry(entries, key).phases = list(phases)
    return phases


def saturation_price_multiplier(
    delivered_kg_per_yr: float,
    annual_market_kg:    float,
    elasticity:          float,
) -> float:
    """Price multiplier when a mission's output is material next to the market.

        P / P0 = (1 + Q_new / Q_market) ^ (−1/ε)

    Constant-elasticity demand.  Precious-metal demand is inelastic, 
    ε ≈ 0.5, so doubling world supply quarters the price, which is why
    "return a tonne of platinum" was never the business it looks like on a
    spot-price spreadsheet.  Returns 1.0 when the market swallows the
    quantity without noticing.
    """
    if annual_market_kg <= 0 or delivered_kg_per_yr <= 0 or elasticity <= 0:
        return 1.0
    ratio = delivered_kg_per_yr / annual_market_kg
    if ratio <= 1e-9:
        return 1.0
    return (1.0 + ratio) ** (-1.0 / elasticity)


# ─── CONSTANT PRICES AND A QUANTITY WALL  (v1.21.0) ──────────────────────────
# The four models `CalcConfig.market_model` selects between.  Exported as a
# tuple rather than spelled out again in the dashboard, so the dropdown cannot
# drift from what this module will accept; `ui_meta` resolves it at runtime the
# way it already resolves the destination list.
MARKET_MODELS: Tuple[str, ...] = (
    "capacity_cap", "single_mission", "elasticity", "unbounded",
)


_MARKET_MODE_SET = frozenset(MARKET_MODELS)


def _market_mode(config: CalcConfig) -> str:
    """`config.market_model`, validated, lowercased.

    An unrecognised value is REFUSED rather than quietly defaulted.  A silent
    fallback here is the quiet-wrong-answer shape this module keeps finding:
    a typo would price an entire campaign against a market model nobody chose,
    and the only symptom would be numbers that look slightly generous.

    ⚠️  THIS IS ON THE HOT PATH, TWICE.  `_evaluate_combo_at_ratio` asks once
    per (asteroid x vehicle x propellant x architecture x concentration ratio)
    and `_programme_ladder_cached` asks again for its memo key, so a full
    beneficiated cell calls it ~48 million times.  The normalising path is
    ~303 ns of `str()`, `strip()`, `lower()` and a membership test: **~15 s a
    cell** to re-derive one of four answers, which is defect class 3, a
    quantity asked at a finer granularity than it has answers.

    The fast path is an identity test against the frozen set and costs ~30 ns.
    It hits on every run whose config was not hand-typed, and it is not a cache,
    so there is no staleness to reason about and nothing to bound: a config
    edited between runs is answered from the value it now holds, which is the
    rule this module states for memos and which a memo here would have had to
    honour explicitly.

    `type(raw) is str` rather than `isinstance`: a hair faster, and it is the
    exact question being asked.  A non-string (someone assigning a list) falls
    through to the slow path and is refused there rather than raising
    `TypeError` on an unhashable set lookup.
    """
    raw = getattr(config, "market_model", None)
    if type(raw) is str and raw in _MARKET_MODE_SET:
        return raw
    mode = str(raw or "").strip().lower()
    if mode not in _MARKET_MODE_SET:
        raise ValueError(
            "market_model must be one of %s, not %r"
            % (", ".join(MARKET_MODELS), raw))
    return mode


def capacity_allowance_kg(
    annual_market_kg: float,
    n_missions:       int,
    fleet:            int,
    duration_yr:      float,
    cadence_yr:       float,
) -> float:
    """Kilograms of ONE commodity that ONE delivery may sell (v1.21.0).

    Under `market_model = "capacity_cap"` the price is flat at any volume and
    what bounds a programme is how much the destination can absorb while it
    waits.  So the question is not "what does the 400th tonne fetch" but "how
    long has the market been accumulating since the last delivery".

    ── The window ───────────────────────────────────────────────────────────

    A programme of F ships repeating every `cadence_yr` puts a delivery on the
    market every `cadence / F` years, so in steady state one delivery may sell
    `cap x cadence / F`.  Note that is the same constraint as a RATE test, seen
    from the other side:

        kg <= cap x cadence / F     <=>     kg x F / cadence <= cap

    The FIRST delivery is different, and it is the one exception this function
    makes.  Nothing has arrived yet, so the destination has been importing from
    Earth for the whole outbound-and-back trip: `duration_yr`, which is longer
    than the cadence, because the cadence is only the dig (or the window),
    while the duration is the whole mission.  Over a programme of N deliveries
    the market therefore accumulates for

        duration + (N - 1) x cadence / F

    years in total, and this returns the per-delivery average of that.  At
    N = 1 it is exactly `cap x duration`; as N grows it converges on the steady
    state `cap x cadence / F`.

    ⚠️  IT IS AVERAGED RATHER THAN BRANCHED, deliberately.  Giving delivery one
    the long window and every later delivery the short one is the same model,
    but as a step it puts a discontinuity between N = 1 and N = 2 that hands
    N = 1 a structural advantage no economics produced -- and the ladder would
    then collapse onto N = 1 for a reason that is a rule, not a result.  The
    average is continuous in N and gives the identical answer at both ends.

    ⚠️  `cadence_yr` and NOT `mission_duration_yr` sets the steady state, which
    is a change from the v1.14.0 elasticity term.  That term divided by the
    mission duration, but a rig starts its next campaign as soon as the feed is
    out of the ground; `campaign_cadence_yr` is the interval that actually
    repeats.  Since the duration exceeds the cadence on essentially every body,
    the old denominator UNDERSTATED sustained throughput.  Under a smooth curve
    that is a bias buried in an exponent; under a wall it moves the feasible
    fleet directly, so it stops being ignorable.

    An infinite ceiling (a commodity with no `annual_market_kg` entry, which is
    every bulk commodity and everything sold at `earth_surface`) returns inf
    and nothing ever binds, which is the documented degenerate case rather than
    an oversight.
    """
    cap = float(annual_market_kg)
    if cap <= 0.0:
        return 0.0
    window = _delivery_window_yr(n_missions, fleet, duration_yr, cadence_yr)
    if window <= 0.0:
        return 0.0
    return cap * window


def _delivery_window_yr(
    n_missions: int, fleet: int, duration_yr: float, cadence_yr: float,
) -> float:
    """Years of market accumulation behind ONE delivery of a programme.

    The single statement of the window algebra `capacity_allowance_kg`
    documents.  Split out because the ladder needs the window ONCE per rung and
    then multiplies it by each commodity's own ceiling; calling the per-
    commodity function would re-derive the same five float operations for every
    phase in the haul, ~60 of them per rung and ~40 rungs per candidate.

    Two readers, one derivation.  Writing the expression out again at the call
    site is exactly the "two copies of one algebra drifting apart" hazard the
    mass ledger warns about.
    """
    n      = max(1, int(n_missions))
    f      = max(1, int(fleet))
    first  = max(0.0, float(duration_yr))
    steady = max(0.0, float(cadence_yr)) / f
    return (first + (n - 1) * steady) / n


def _capped_sale_value(
    sale_terms: List[Tuple[float, float, float, str]], window_yr: float,
    surplus_price_frac: float = 0.0,
) -> Tuple[float, float, float]:
    """`(value_usd, unsold_kg, surplus_kg)`, commodities clipped at the ceiling.

    Each kilogram inside the ceiling fetches the full price the mineral catalog
    quotes.  What happens to the kilograms past it is v1.22.0's
    `sell_surplus_at_discount`, and the two answers are reported in different
    columns because they are different events:

      surplus_price_frac = 0.0   a quantity WALL.  The surplus earns nothing
                                 and comes back as `unsold_kg`.  v1.21.0's
                                 model, and what the 2026-09 campaign measured.
      surplus_price_frac > 0.0   the surplus SELLS, at that fraction of the
                                 full price, and comes back as `surplus_kg`
                                 with `unsold_kg` at 0.0.

    ⚠️  ONE MEANING PER COLUMN, and that is why this returns three floats
    rather than reusing `unsold_kg` for both.  Mass that earned nothing and
    mass that earned half are not the same measurement, and a harness that
    counted "unsold" across the flip would have silently changed what it was
    counting -- which is the diagnostic-changes-meaning-under-you failure this
    module has now hit twice.

    ⚠️  Accumulates over `sale_terms` in its own insertion order, exactly as
    the elasticity branch does, and for the same reason: floating-point
    addition is not associative and every verification in this project is a
    bit-identity check.  See the warning in `optimal_payload_mix`.

    Used for the RAW cargo, where the mix is the body's own composition and
    cannot be reshaped.  A beneficiated load goes through `optimal_payload_mix`
    with the same ceilings instead, which spends the freed hold space on the
    next most valuable phase rather than flying the excess unsold -- and, since
    v1.22.0, weighs that against carrying the surplus at the discount.

    🚨  v1.21.2: THE ALLOWANCE IS POOLED PER MARKET, NOT PER PHASE.  Each entry
    carries the market KEY it sells into, and phases sharing a key draw down
    one shared allowance.  Before this the `silicates` phase and the
    composition residual each got the full silicates ceiling, which is one
    market sold twice, on 100% of bodies.

    ⚠️  Insertion order decides WHICH phase is recorded as unsold when a pooled
    allowance runs out.  It does not change `value`, because the only pair that
    shares a key today is priced identically by construction -- the residual is
    priced at the silicates quote.  If a future alias ever joins two phases at
    DIFFERENT prices, this loop would need to spend the allowance on the dearer
    one first, and the order it happens to receive would stop being good
    enough.
    """
    value   = 0.0
    unsold  = 0.0
    surplus = 0.0
    sells   = surplus_price_frac > 0.0
    remaining: Dict[str, float] = {}
    for kg, price, mkt, key in sale_terms:
        allowance = remaining.get(key)
        if allowance is None:
            allowance = mkt * window_yr
        if kg > allowance:
            over = kg - allowance
            value += allowance * price
            if sells:
                # v1.22.0.  The surplus is carried and sold, at a discount.
                # Written as a second term rather than folded into one blended
                # price so the wall's arithmetic is untouched when the flag is
                # off: at `sells` False not one float below differs from
                # v1.21.2, which is what lets the campaign's cells reproduce.
                value   += over * price * surplus_price_frac
                surplus += over
            else:
                unsold  += over
            remaining[key] = 0.0
        else:
            value += kg * price
            remaining[key] = allowance - kg
    return value, unsold, surplus


# Single-slot memo for the knapsack's price ordering (v1.14.2).  The phase table
# is built once per asteroid and never mutated, but `optimal_payload_mix` is
# called ~2,100 times per asteroid in a beneficiated run and re-sorted it every
# time: 325,000 `sorted()` calls plus 1.4 million key-lambda calls per 150
# rows, all re-deriving the same order for the same rock.
#
# Same shape and the same justification as `_OPS_CACHE` below: keyed by object
# identity, with the list itself held in the slot so its id cannot be recycled
# onto a different object, and single-slot rather than a growing dict so a
# long-lived session cannot leak.  A caller that mutates a phase list IN PLACE
# rather than rebinding would read a stale order; nothing in this module does,
# and `asteroid_phase_table` returns a fresh list per asteroid.
#
# ⚠️  What this deliberately does NOT do is sort the phase table at source.  See
# the warning in `optimal_payload_mix`; the table's natural order is
# load-bearing elsewhere, on the last ULP.
_PHASE_ORDER_CACHE: Tuple[Optional[List[Tuple[str, float, float]]],
                          List[Tuple[str, float, float]]] = (None, [])


def optimal_payload_mix(
    payload_kg: float,
    feed_kg:    float,
    phases:     List[Tuple[str, float, float]],
    recovery:   float,
    want_phase: Optional[str] = None,
    caps:       Optional[Dict[str, float]] = None,
    cap_keys:   Optional[Dict[str, str]]   = None,
    surplus_price_frac: float = 0.0,
) -> Union[Dict[str, object], float]:
    """Most valuable payload obtainable from `feed_kg` of this rock (v1.6.0).

    The mission is not sent for a named mineral; it is sent to bring back the
    best load it can assemble from what the target actually contains.  With a
    fixed mass budget and divisible, per-kilogram-priced phases, that is a
    FRACTIONAL KNAPSACK, and greedy selection by $/kg is provably optimal:
    fill the hold with the most valuable phase available, then the next, until
    the hold is full or the feed runs out.

    Separation recovers `recovery` of each phase present in the feed; whatever
    is not loaded is left at the asteroid.

    Returns value, blended $/kg, the chosen mix in kg, the mass fraction the
    best phase makes up, which is the natural read on how well concentrated
    the load actually is, and `surplus_kg`, the mass of that load sold past a
    market ceiling at the discount (v1.22.0; 0.0 on every other path).

    ⚠️  **Do not "fix" this by sorting the phase table at source.**  The greedy
    order is needed HERE and nowhere else, and `phases` arrives in its natural
    (Module 1 fraction) order because the market-saturation block in
    `_evaluate_combo_at_ratio` builds `sold` from it and then accumulates
    `adj_value` by iterating that dict.  Floating-point addition is not
    associative, so reordering the table reorders that sum and moves
    `saturation_multiplier`, `gross_value_usd`, `profit_usd`, `roi` and
    `delivered_value_usd_per_kg` in their last bit.

    Measured, on a 150-row beneficiated cislunar sample: max relative change
    2.8e-16 on 3 of 60 rows, and no vehicle, propellant, concentration ratio or
    power source moved.  Numerically that is nothing.  It is still fatal, because
    every verification this project relies on is a bit-identity check: the
    sha256 CSV diffs, `max |error| 0.000000000 kg`, "124 of 124 columns
    identical".  A sort at source reads like a free cleanup and silently costs
    you the ability to prove a release changed nothing.

    So the ordering is memoised per phase list instead, which leaves the table
    itself untouched.

    ── `want_phase` (v1.17.1) ───────────────────────────────────────────────
    Returns the kilograms of ONE named phase that the greedy walk loads, as a
    bare float, instead of the full result dict.  `_cargo_water_kg` is 97% of
    this function's callers and reads exactly one key, `mix_kg["water"]`, 
    so it was paying for the mix dict, the value accumulation and the
    dominant-phase `max()` over `mix.items()` on every call, then throwing all
    three away.

    It is a short circuit, NOT a second knapsack: the walk below is the only
    statement of the greedy algebra in this module, and `want_phase` only
    decides how much of each pass's result is kept and when to stop.  Writing
    it as a separate water-only function would have been the "two copies of
    this algebra drifting apart" hazard that the mass ledger warns about, for
    no extra speed; the loop is not what costs, the bookkeeping is.

    The answer is bit-identical by construction rather than by measurement:
    `remaining` is decremented in the same order by the same `min`, and the
    take for the requested phase is returned before anything downstream of it
    could perturb it.  Verified anyway; see the release notes.

    ── `caps` (v1.21.0) ─────────────────────────────────────────────────────
    An optional per-phase UPPER BOUND in kilograms, which is what
    `market_model = "capacity_cap"` uses to say how much of each commodity the
    destination can take while it waits.  See `capacity_allowance_kg`.

    ✅  GREEDY IS STILL PROVABLY OPTIMAL.  Per-item quantity limits turn an
    unbounded fractional knapsack into a BOUNDED one, and the bounded form is
    solved exactly by the same walk: sort by $/kg descending and take
    `min(available, allowance, remaining)` of each in turn.  So this is not a
    clamp bolted onto the outside of an optimiser -- which is the shape this
    module warns against, because the content and purity bounds are supposed to
    FALL OUT of the knapsack rather than be re-imposed on it -- it is the
    correct formulation of the same problem with one more constraint.

    The freed hold space is what the caller actually wanted: a load that caps
    out on iron keeps walking down the price order and spends the remaining
    capacity on whatever is next, rather than flying the excess unsold.

    🚨  v1.21.2: `caps` IS KEYED BY MARKET AND IS CONSUMED IN PLACE.  Pass a
    dict you own; this walk decrements it.  Keying it by phase gave two phases
    that sell into one market the full allowance each, which is the defect
    v1.21.2 exists to close, and consuming it is what makes the pool shared
    rather than merely shared-looking.

    `cap_keys` maps a phase name to the market key its allowance lives under,
    and a phase missing from it stands alone.  It is a MAP rather than a call
    to `phase_market_key` here because that function needs the market table to
    resolve an alias the way `phase_market_kg` does, and handing the knapsack
    the whole of Stage 2 to look up five strings would be the wrong seam: the
    caller already knows both, and resolving it there keeps the two lookups
    agreeing in one place.

    ── `surplus_price_frac` (v1.22.0) ───────────────────────────────────────
    What a kilogram past a ceiling fetches, as a fraction of the full price.
    0.0 is v1.21.0's wall: the allowance is a hard upper bound and anything
    past it is simply not loaded.  Above 0.0 the surplus becomes cargo the
    load may CHOOSE to carry, and the knapsack has to decide whether it is
    worth the hold space.

    ✅  GREEDY IS STILL EXACT, and the formulation is the standard one: a
    two-step price schedule is two ITEMS, not a clamp.  Each phase enters the
    walk twice, once at `price` limited by its market allowance and once at
    `price x surplus_price_frac` limited by what is left of the feed, and the
    merged list is sorted by unit price like any other fractional knapsack.
    Every item still has a constant unit value and is divisible, which is the
    only condition greedy needs.

    🚨  THE INTERLEAVING IS THE POINT, and it is why this cannot be done as a
    second pass over the leftovers.  A rich phase's HALF-PRICE surplus can be
    worth more per kilogram than a poor phase's full-price allowance, and when
    it is, the optimal load carries it instead.  Filling the hold with
    everything full-price first and topping up with surplus afterwards is a
    different, strictly worse load; it would also be the "clamp bolted onto
    the outside of an optimiser" shape this docstring warns against three
    paragraphs up.

    ⚠️  ONE WALK, not two.  The tiered sequence is built ahead of the loop and
    the loop below is unchanged for everyone else: `tier_taken` is None on
    every call that is not tiered, so the default path pays one `is None` test
    per phase and no arithmetic.  A second copy of this walk is the hazard the
    `want_phase` note above is about, and it would be a worse one here, because
    this is the copy that decides what a load is worth.

    ⚠️  Tiers are OFF whenever `want_phase` is set, deliberately.  That short
    circuit returns the first take of the named phase and stops, which would
    report the allowance and miss the surplus.  It is not a live combination:
    `want_phase` belongs to `_cargo_water_kg`, on the SIZING path, and the
    sizing path must never pass `caps` at all -- see the warning below.

    ⚠️  `caps=None` must stay bit-identical to the pre-v1.21.0 walk, because
    the `elasticity` market model is the v1.14.0 curve, and it reproduced
    v1.14.0 to v1.20.0 exactly until v1.21.1's residual-ceiling fix moved the
    two raw cells.  The guard below adds
    a branch and no arithmetic; when `caps` is None not one float differs.

    ⚠️  AND THE SIZING PATH MUST NEVER PASS CAPS.  `_cargo_water_kg` calls this
    from inside the fixed-point power solve, so a cap reaching it would make
    the whole MASS cascade a function of fleet size -- the one asymmetry that
    makes the programme ladder affordable to search at all.  Ceilings bound
    what a load may SELL, not what the rig digs or the hull carries; the plant
    is sized for the load the body can assemble and the ship is designed once
    for a fleet that is sized around it.  That runs conservative (the array is
    sized for a richer mix than a capped delivery carries), which is the safe
    direction, and it keeps the ledger internally consistent: the array flown
    is still exactly the array charged.
    """
    if payload_kg <= 0 or not phases:
        return 0.0 if want_phase is not None else {
            "value_usd": 0.0, "usd_per_kg": 0.0, "mix_kg": {},
            "dominant_phase": None, "dominant_frac": 0.0,
            "surplus_kg": 0.0}

    global _PHASE_ORDER_CACHE
    if _PHASE_ORDER_CACHE[0] is not phases:
        _PHASE_ORDER_CACHE = (phases, sorted(phases, key=lambda p: -p[2]))
    by_price = _PHASE_ORDER_CACHE[1]

    # v1.22.0.  The tiered sequence, built only when a surplus can actually be
    # sold.  `tier_taken` doubles as the mode flag and as the per-phase ledger
    # the second tier needs: a phase's discounted tier may only draw on the
    # feed its full-price tier left behind, and the sort guarantees the
    # full-price tier is reached first: same phase, strictly higher unit price,
    # and at `surplus_price_frac == 1.0` the two tie and a stable sort settles
    # it in insertion order, which is full-price first by construction.
    #
    # Not cached: this list depends on the fraction as well as the phase table,
    # it is built once per (programme rung x candidate) rather than per call
    # like `by_price`, and the capped branch is already the rare one -- the
    # ladder's fast path proves nothing binds before ever arriving here.
    tier_taken: Optional[Dict[str, float]] = None
    walk = by_price
    if caps is not None and surplus_price_frac > 0.0 and want_phase is None:
        # Clamped HERE as well as at the resolver that normally feeds it and
        # at `market_config_check`, because this is where the ASSUMPTION lives:
        # above 1.0 the discounted tier would sort ahead of the full-price one,
        # take the market allowance, and make the capped load worth more than
        # the uncapped one.  One min() per tiered build, not per item, and the
        # branch is the rare one.
        frac = surplus_price_frac if surplus_price_frac < 1.0 else 1.0
        tiered: List[Tuple[str, float, float]] = []
        for p_name, p_frac, p_price in by_price:
            tiered.append((p_name, p_frac, p_price))
            tiered.append((p_name, p_frac, p_price * frac))
        tiered.sort(key=lambda p: -p[2])
        walk       = tiered
        tier_taken = {}

    remaining  = float(payload_kg)
    total      = 0.0
    surplus_kg = 0.0
    mix: Dict[str, float] = {}
    for name, frac, price in walk:
        if remaining <= 0:
            break
        # `full_tier` is "this phase has not been reached yet", which is the
        # same question as "this is its full-price tier" by the ordering above.
        # Only the full-price tier draws on a market allowance; the surplus is
        # by definition the part no allowance covers.
        if tier_taken is None:
            available = float(feed_kg) * frac * recovery
            full_tier = True
            had       = 0.0
        else:
            had       = tier_taken.get(name, -1.0)
            full_tier = had < 0.0
            if full_tier:
                had       = 0.0
                available = float(feed_kg) * frac * recovery
            else:
                available = float(feed_kg) * frac * recovery - had
        take      = min(available, remaining)
        if caps is not None and full_tier:
            # v1.21.0.  The bounded-knapsack step.  Clipping `take` and NOT
            # `remaining` is the whole point: the hold space this phase does
            # not get stays available to the next one down the price order.
            #
            # v1.21.2: `caps` is keyed by MARKET, not by phase, and is drawn
            # down as it is spent, so two phases sharing a market share one
            # allowance.  The walk is in descending price order, so the dearer
            # phase draws first, which is the right way to spend a scarce
            # allowance and is why this needs no separate ordering rule.
            key = cap_keys.get(name, name) if cap_keys else name
            allowance = caps.get(key)
            if allowance is not None:
                if allowance < take:
                    take = allowance
                caps[key] = allowance - take
        if tier_taken is not None:
            # Recorded BEFORE the `take <= 0` skip below, and that ordering is
            # load-bearing: a full-price tier whose allowance was already spent
            # takes nothing, and if it went unrecorded its own surplus tier
            # would be read as the full-price one and clipped at the same
            # exhausted allowance -- so the discount would silently never fire
            # on exactly the phases it exists for.
            tier_taken[name] = had + take
        if take <= 0:
            continue
        if want_phase is not None:
            # The caller wants one number.  Stop as soon as it is known;
            # nothing after this point in the walk can change it.
            if name == want_phase:
                return take
            remaining -= take
            continue
        if full_tier:
            mix[name] = take
        else:
            # The same phase, loaded twice at two prices.  `mix_kg` is a mass
            # ledger and must stay one entry per phase; `surplus_kg` is what
            # says how much of it sold at the discount.
            mix[name]   = mix.get(name, 0.0) + take
            surplus_kg += take
        total     += take * price
        remaining -= take

    if want_phase is not None:
        # Never reached in the walk: the hold filled before this phase came up,
        # or the feed had none of it.  `mix_kg.get(want_phase, 0.0)` in the full
        # path returns the same 0.0, including when `loaded <= 0` below would
        # have short-circuited to an empty mix.
        return 0.0

    # Anything the feed could not fill is dead space, the hold flies partly
    # empty rather than being topped up with rock that was never dug.
    loaded = float(payload_kg) - remaining
    if loaded <= 0:
        return {"value_usd": 0.0, "usd_per_kg": 0.0, "mix_kg": {},
                "dominant_phase": None, "dominant_frac": 0.0,
                "surplus_kg": 0.0}

    dominant = max(mix.items(), key=lambda kv: kv[1])
    return {
        "value_usd":      total,
        "usd_per_kg":     total / loaded,
        "loaded_kg":      loaded,
        "mix_kg":         mix,
        "surplus_kg":     surplus_kg,
        "dominant_phase": dominant[0],
        "dominant_frac":  dominant[1] / loaded,
    }


def asteroid_best_phase_usd_per_kg(
    asteroid_row: Row, mineral_df: pd.DataFrame,
) -> float:
    """$/kg of the single most valuable phase actually present (v1.5.0).

    This is the PURITY BOUND on beneficiation.  Concentrating rejects gangue,
    it does not transmute: the richest concentrate physically obtainable from
    a body is 100% of its best phase, so no amount of processing can push the
    delivered $/kg above this number.

    Only phases with a non-zero fraction count; a body with no metal cannot
    be concentrated into metal.  Returns the bulk value as a floor so the
    bound can never sit below the unconcentrated material.

    v1.17.6: memoised per composition; see `_composition_key`.  This is the
    most expensive of the three at 27.7 us/row, because it walks the phases AND
    calls the bulk function, so a beneficiated run derived the bulk blend twice
    per asteroid.
    """
    key = _composition_key(asteroid_row)
    if key is not None:
        entries = _composition_cache(mineral_df)
        hit = entries.get(key)
        if hit is not None and hit.best is not None:
            return hit.best

    best = 0.0
    for _mineral_name, _frac, price in _phase_prices(asteroid_row, mineral_df):
        if price > best:
            best = price

    bulk = asteroid_bulk_value_usd_per_kg(asteroid_row, mineral_df)
    value = max(best, bulk)
    if key is not None:
        # Re-read the cache: the bulk call above may have created the entry.
        _composition_entry(_composition_cache(mineral_df), key).best = value
    return value


# ─────────────────────────────────────────────────────────────────────────────
# BENEFICIATION, TIME AND ENERGY INTENSITY  (v1.5.0)
# ─────────────────────────────────────────────────────────────────────────────
# Concentrating ore in deep space costs three things, and the model charges
# for all three:
#
#   TIME    - the rig has to dig the whole feed, not just the payload.  A 50:1
#             concentration means excavating 50 kg for every kilogram flown
#             home, and that time flows into mission duration, mission ops
#             and WACC compounding exactly like any other stay time.
#   ENERGY  - Module 3 rates excavation at 200 Wh per kg of regolith moved and
#             beneficiation at 500 Wh per kg of product.  Energy over time is
#             power, and power in deep space is a solar array.
#   MASS    - that array has to be launched.  Its mass enters the SAME rocket
#             equation as everything else, so a more aggressive concentration
#             ratio buys grade at the cost of payload.  That feedback loop is
#             solved, not assumed away.
#
# The 1/r² term is what makes this bite for distant targets: a main-belt body
# at 2.7 AU gets 14% of the solar flux an NEA at 1 AU does, so the same
# processing plant weighs seven times as much.

def solar_specific_power_w_per_kg(
    a_au: Optional[float], base_w_per_kg: float,
) -> float:
    """Power-system W/kg at an asteroid's heliocentric distance.

    Photovoltaic output tracks solar flux, which falls as 1/r².  `base_w_per_kg`
    is Module 3's system-level figure quoted at 1 AU.  Missing or absurd
    distances fall back to 1 AU rather than silently producing free power.
    """
    try:
        r = float(a_au)
    except (TypeError, ValueError):
        return float(base_w_per_kg)
    if not (0.1 < r < 100.0):
        return float(base_w_per_kg)
    return float(base_w_per_kg) / (r * r)


# ─────────────────────────────────────────────────────────────────────────────
# POWER SOURCE SELECTION  (v1.11.0)
# ─────────────────────────────────────────────────────────────────────────────
# Module 3 has carried an "RTG (radioisotope power)" row since v1.2.0: $500k
# per Watt-electric, with a note reading "only used past ~3 AU when PV starves",
# and nothing in this module ever read it.  Every asteroid in the catalog
# flew photovoltaics, including the ones at 3.5 AU where the 1/r² term makes
# the array seven times heavier than at 1 AU.  So the main belt was being
# punished for an architecture choice a real mission would simply not make.
#
# The crossover is arithmetic, not a judgement: solar is 60 W/kg at 1 AU and
# falls as 1/r²; an RTG is ~5 W/kg everywhere.  They cross at
#
#     r = sqrt(60 / 5) = 3.46 AU
#
# Inside that, PV is lighter per watt.  Outside it, nothing beats a
# radioisotope, and a meaningful slice of this catalog is outside it.
#
# Two things keep this from becoming a free win for distant bodies:
#
#   • It costs 625× more per watt ($500,000 against $800), so the model buys
#     nuclear only where it is genuinely lighter, and pays for it.
#   • Pu-238 supply is the real constraint.  DOE production is ~1.5 kg/yr,
#     which is roughly one flagship RTG a year for the whole world, and a
#     GPHS-RTG is 290 We.  A few kilowatts is the outside edge of plausible;
#     a 300 kW nuclear-electric stage is not a cost question, it is a
#     national-inventory question.  `rtg_max_power_w` caps it, and above the
#     cap the mission goes back to solar and pays the mass.
#
# Deliberately NOT applied to the electric-propulsion array.  EP on the targets
# this pipeline sizes runs to hundreds of kilowatts, which is two orders above
# anything a radioisotope source can deliver; pricing that as an RTG would
# quietly invent nuclear-electric propulsion, which is a development-status
# propellant row of its own (see Module 3) with a reactor this model does not
# size.  The processing plant is kilowatts and is the honest place for this.

def power_source_for_target(
    solar_w_per_kg: float,
    rtg_w_per_kg:   float,
    required_w:     float,
    max_rtg_w:      float,
) -> Tuple[float, str]:
    """(specific power W/kg, source name) for the processing plant.

    Picks whichever of photovoltaic and radioisotope is LIGHTER, subject to the
    radioisotope cap.  Returns the solar figure unchanged whenever RTG is
    unavailable, so `allow_rtg_power = False` reproduces the pre-v1.11.0
    behaviour exactly.

    v1.14.0, takes the solar figure ALREADY RESOLVED rather than deriving it
    from `a_au` internally.  The caller now hands in an eclipse-effective
    specific power (see `eclipse_effective_w_per_kg`), and that matters: with
    the night-side term in it, a photovoltaic plant is roughly half as good per
    kilogram as its bare 1/r² rating, so the crossover against a radioisotope
    source moves substantially INWARD of the 3.46 AU that the two bare specific
    powers imply.  Comparing bare figures here would have kept choosing a solar
    plant that the mission then had to fly at twice the mass.
    """
    solar = float(solar_w_per_kg)
    if rtg_w_per_kg <= 0 or required_w <= 0:
        return solar, "solar"
    if required_w > max_rtg_w:
        return solar, "solar"           # more power than Pu-238 supply allows
    if rtg_w_per_kg <= solar:
        return solar, "solar"           # inside the crossover; PV is lighter
    return float(rtg_w_per_kg), "rtg"


# ─────────────────────────────────────────────────────────────────────────────
# ECLIPSE / NIGHT-SIDE POWER  (v1.14.0)
# ─────────────────────────────────────────────────────────────────────────────
# `processing_power_w()` returns a CONTINUOUS average draw, energy divided by
# the time available, and the plant was sized straight off it.  That is only
# correct if the sun never sets.  It does: the rig stands on a rotating body,
# roughly half its sky is the ground, and asteroid rotation periods run hours.
#
# Module 3 has carried the 0.50 dark fraction in STORAGE_REFERENCE since v1.9.0
# with "⚠️  Not modelled" written on it, and the note was quoted as a known
# limitation for two releases while nothing consumed it, because Module 4
# loads operational_costs.csv and STORAGE_REFERENCE is exported to a file it
# does not read.  Writing a gap down is not closing it.
#
# Two terms, and it matters that they are separate:
#
#   ARRAY OVERSIZE.  To deliver P continuously through a dark fraction f, the
#   sunlit hours must run the load AND recharge the store:
#
#       installed = P · [(1 − f) + f/η_rt] / (1 − f)
#
#   which is 2.11× at f = 0.50, η_rt = 0.90.  This is a SIZING factor, not a
#   specific mass, which is why no W/kg row could ever have absorbed it however
#   its notes were worded.
#
#   STORAGE.  The store carries the load across one dark period, and the dark
#   period is set by the BODY'S OWN rotation.  So this term is per-asteroid and
#   a slow rotator is genuinely a worse place to mine; a fact the model had no
#   way to express before, despite carrying `rotation_period_h` since v1.0.0.
#
# Both are exempt for a radioisotope plant, whose output is flat, and neither
# applies to the EP array, which is in interplanetary cruise and in permanent
# sunlight.  The RTG exemption is the one with a visible consequence: eclipse
# is what makes the radioisotope branch worth choosing on more than a rounding
# number of bodies.

def dark_period_hours(
    rotation_period_h: Optional[float],
    dark_fraction:     float,
    default_period_h:  float,
    max_dark_h:        float,
) -> Tuple[float, bool]:
    """(hours of darkness per rotation, whether the clamp bound).

    Bodies with no measured rotation, about two thirds of the catalog, take
    the median of the ones that have it.  Slow rotators run to hundreds of
    hours and a few tumblers are catalogued near 10,000; sizing a chemical
    battery for a forty-day night is not an answer but a different
    architecture question, so the dark period is clamped and the clamp is
    reported rather than hidden.
    """
    try:
        period = float(rotation_period_h)
    except (TypeError, ValueError):
        period = float(default_period_h)
    if not np.isfinite(period) or period <= 0:
        period = float(default_period_h)
    dark = period * max(0.0, min(1.0, dark_fraction))
    if dark > max_dark_h:
        return float(max_dark_h), True
    return dark, False


def eclipse_effective_w_per_kg(
    solar_w_per_kg:     float,
    dark_h:             float,
    dark_fraction:      float,
    storage_wh_per_kg:  float,
    storage_efficiency: float,
    baseline_dark_h:    float,
) -> Tuple[float, float]:
    """(effective W/kg for a night-side plant, array oversize factor).

    Both eclipse terms collapse exactly into one effective specific power,
    because both are proportional to the continuous draw P:

        m_plant = P·oversize/w_solar + P·Δh/e_storage
                = P · (oversize/w_solar + Δh/e_storage)

    so 1/(oversize/w_solar + Δh/e_storage) is a W/kg the rest of the module can
    use exactly where it used the bare figure.  That is why this is a specific
    power rather than a mass: it keeps the plant's sizing, its 1/r² behaviour
    and its comparison against a radioisotope source in one currency, and it
    means the RTG crossover is decided on real mass instead of on bare ratings.

    The storage term is charged as an INCREMENT.  "Power system specific mass"
    is 60 W/kg system-level against ROSA's ~150 W/kg at the wing, and part of
    that 2.5× is a battery, so some storage is already bought; Module 3's
    "Power-system row baseline dark period" names how much (0.58 h, a LEO
    eclipse) and only the excess is new mass.  Without that deduction the
    battery is charged twice, and at 0.0056 kg/W against the row's own
    0.0167 kg/W it is a third of the plant, not a nicety.

    `dark_fraction = 0` returns the input unchanged and an oversize of 1.0, so
    a stale Module 3 catalog or `model_eclipse_power = False` reproduces
    v1.13.0 exactly.

    One deliberate conservatism: the oversize factor scales the whole
    PV+PMAD+battery+structure train, including the LEO-class battery already
    inside the 60 W/kg figure, which does not itself need oversizing.  Second
    order against the two terms above, and it runs in the safe direction.
    """
    w = float(solar_w_per_kg)
    if w <= 0:
        return w, 1.0
    f = max(0.0, min(0.95, float(dark_fraction)))
    if f <= 0.0:
        return w, 1.0
    eta = max(0.05, min(1.0, float(storage_efficiency)))
    # Sunlit hours run the load AND recharge the store, and the recharge is
    # lossy.  Exactly 1.0 at f = 0, the permanent-sunlight case a free-flying
    # plant enjoys, which is why the EP array never sees this term.
    oversize = ((1.0 - f) + f / eta) / (1.0 - f)

    kg_per_w = oversize / w
    if storage_wh_per_kg > 0:
        excess_h  = max(0.0, float(dark_h) - max(0.0, float(baseline_dark_h)))
        kg_per_w += excess_h / float(storage_wh_per_kg)
    return (1.0 / kg_per_w if kg_per_w > 0 else w), oversize


# ─────────────────────────────────────────────────────────────────────────────
# LOW-THRUST TRIP TIME  (v1.7.0)
# ─────────────────────────────────────────────────────────────────────────────
# Until now electric propulsion carried a Δv penalty and nothing else: it flew
# its burns instantly and drew no power.  That is the single most flattering
# error left in the model, and it was load-bearing; the best Mars mission in
# v1.6.0 was a 1,500 s argon Hall thruster that would in reality have spent
# years thrusting on megawatts it did not carry.
#
# The physics is not optional.  A thruster's jet power fixes its thrust:
#
#     T = 2·η·P / (Isp·g0)                     [P_jet = ½·ṁ·v_e², T = ṁ·v_e]
#
# and burning m_prop at that thrust takes
#
#     t = m_prop / ṁ = m_prop·(Isp·g0)² / (2·η·P)
#
# So high Isp buys propellant mass at a QUADRATIC cost in time-or-power.  A
# chemical stage does its burn in minutes and this never binds; an electric
# stage thrusts for most of the mission.
#
# Validated against Dawn, which is the only deep-space mission that flew this
# regime for real: Isp 3,100 s, 425 kg of xenon, a 10 kW array at 1 AU, η 0.6.
# Dawn worked at 2.2-3.0 AU, where 1/r² leaves it 1.1-2.1 kW, and the formula
# gives 5.0-9.3 years of thrusting.  Dawn actually thrust for ~5.9 years of
# its 11-year mission.  The 1/r² term is doing the work here, evaluated at
# the 1 AU array rating instead, the same sum gives 1.0 year and is nonsense.
#
# Run that check off `ep_power_required_w` below, the same relation solved for
# P rather than t.  The t-form had its own function until it had gone four
# releases with no caller: the model always picks a trip time and buys the
# array, never the other way round.

def ep_power_required_w(
    m_prop_kg:  float,
    isp_s:      float,
    thrust_yr:  float,
    efficiency: float,
) -> float:
    """Electrical power to expend `m_prop_kg` within `thrust_yr` of thrusting.

    The same relation solved for P.  This is how a real mission is sized:
    you pick an acceptable trip time and buy the array that delivers it.
    """
    if thrust_yr <= 0 or m_prop_kg <= 0:
        return 0.0
    ve = isp_s * G0_M_S2
    seconds = thrust_yr * 365.25 * 24.0 * 3600.0
    return m_prop_kg * ve * ve / (2.0 * efficiency * seconds)


def ep_thrust_required_n(
    m_prop_kg: float,
    isp_s:     float,
    thrust_yr: float,
) -> float:
    """Thrust needed to expend `m_prop_kg` within `thrust_yr` (newtons).

        ṁ = m_prop / t        T = ṁ · ve

    v1.12.0.  This is the quantity the DEVICE has to produce, and it is worth
    noticing that it owes nothing to efficiency; thrust is momentum flux, so
    T = m_prop·ve/t exactly.  Efficiency only decides how much electrical power
    you must supply to get it, which is why the two constraints are separate
    and why sizing on power alone missed one of them entirely.

    Until v1.12.0 nothing computed this. The EP stage was sized on power, and
    power buys thrust at a rate the rocket equation was happy to assume any
    device could deliver, so the search flew pulsed plasma thrusters and
    electrospray emitters, which have flown producing MICRONEWTONS, as
    ten-newton cargo tugs.  See `_THRUSTER_SYSTEMS` in Module 3.
    """
    if thrust_yr <= 0 or m_prop_kg <= 0 or isp_s <= 0:
        return 0.0
    seconds = thrust_yr * 365.25 * 24.0 * 3600.0
    return m_prop_kg * (isp_s * G0_M_S2) / seconds


# ─────────────────────────────────────────────────────────────────────────────
# LAUNCH WINDOWS  (v1.7.0)
# ─────────────────────────────────────────────────────────────────────────────
# Every asteroid was previously assumed departable whenever the mining
# finished.  Real transfers need the target and the destination correctly
# phased, and those alignments recur at the SYNODIC period:
#
#     S = 1 / |1/T_asteroid − 1/T_destination|
#
# The counterintuitive part, and the reason this is worth modelling: NEAs are
# the WORST offenders.  Their orbital periods sit close to Earth's, so the
# phase drifts slowly and windows are years apart, a body at a = 1.13 AU
# (T = 1.20 yr) has a 6-year synodic period with Earth.  A main-belt body at
# 2.7 AU has one of 1.3 years.  Accessibility in Δv and accessibility in
# TIME pull in opposite directions.

def synodic_period_yr(a_asteroid_au: Optional[float], a_dest_au: float) -> float:
    """Years between successive departure windows, capped at 10.

    Bodies whose period nearly matches the destination's have a synodic
    period tending to infinity; the cap stands in for the fact that a real
    mission would accept a worse, non-optimal transfer rather than wait
    forever.
    """
    try:
        a = float(a_asteroid_au)
    except (TypeError, ValueError):
        return 1.0
    if not (0.05 < a < 100.0) or a_dest_au <= 0:
        return 1.0
    t_ast  = a ** 1.5                       # Kepler, years (GM_sun units)
    t_dest = a_dest_au ** 1.5
    denom  = abs(1.0 / t_ast - 1.0 / t_dest)
    if denom <= 1e-9:
        return 10.0
    return min(1.0 / denom, 10.0)


def processing_power_w(
    feed_kg:        float,
    concentrate_kg: float,
    duration_yr:    float,
    dig_wh_per_kg:  float,
    benef_wh_per_kg: float,
) -> float:
    """Continuous electrical power to dig `feed_kg` and concentrate it.

    Energy is charged on the two Module 3 rates; excavation per kg of
    regolith MOVED, beneficiation per kg of product OUT, and divided by the
    time available, because energy over time is power and power is what sizes
    the array.
    """
    if duration_yr <= 0:
        return 0.0
    energy_wh = dig_wh_per_kg * max(feed_kg, 0.0) + benef_wh_per_kg * max(concentrate_kg, 0.0)
    return energy_wh / (duration_yr * 365.25 * 24.0)


def _cargo_water_kg(
    asteroid_row: Row,
    phases:       list,
    payload_kg:   float,
    feed_kg:      float,
    beneficiate:  bool,
    config:       CalcConfig,
    ice_frac:     Optional[float] = None,
) -> float:
    """Water in the delivered CARGO, which has to be baked out of the rock.

    v1.12.0.  Factored out of `_evaluate_combo_at_ratio` because it is now
    needed in two places, inside the sizing loop, where it sets how much array
    the mission has to FLY, and again after the loop, where the mission
    actually flown is priced.  Those two were previously different expressions
    and the second one was larger, so the array for baking cargo water was
    charged in the ledger and never launched.  One function, called twice, is
    what stops that recurring.

    Concentrating changes the answer: the knapsack decides how much water ends
    up in the hold, and it will happily leave water behind for a denser-value
    phase.  Not concentrating means the cargo is the body's own composition, so
    the ice fraction applies directly.

    v1.17.1, both branches, and neither changes an answer:

    * the concentrating branch asks `optimal_payload_mix` for the ONE phase it
      reads rather than building the whole mix and discarding it; see
      `want_phase` there,
    * `ice_frac` is a property of the BODY, so the raw branch's `.get` +
      `pd.isna` + `float` was being re-derived once per candidate per pass of
      the sizing loop.  `AsteroidContext` resolves it once and passes it in;
      None still means "derive it from the row", which keeps this function
      usable on its own.
    """
    if payload_kg <= 0:
        return 0.0
    if beneficiate:
        if not phases:
            return 0.0
        return float(optimal_payload_mix(
            payload_kg, feed_kg, phases, config.beneficiation_recovery,
            want_phase="water",
        ))
    if ice_frac is None:
        ice_frac = asteroid_row.get("comp_ice_fraction")
        if ice_frac is None or pd.isna(ice_frac):
            return 0.0
    return payload_kg * float(ice_frac)


# ─────────────────────────────────────────────────────────────────────────────
# Δv RESOLVER  (v1.4.0, per-asteroid, from orbital elements)
# ─────────────────────────────────────────────────────────────────────────────
# Until v1.4.0 every asteroid in the catalog received the SAME Δv, because
# v1.3.5 removed the per-target Asterank override without replacing it.  The
# consequence was not subtle: on a 150-asteroid run, max_payload_kg,
# total_cost_usd, m_launch_kg, mission_duration_yr, vehicle and propellant
# each had exactly ONE unique value across the whole catalog.  Only
# bulk_value_usd_per_kg varied.  The "profitability ranking" was a ranking of
# spectral types, and orbital accessibility, the single most important
# variable in asteroid mining economics, had no effect at all.  A main-belt
# object at 2.7 AU was costed identically to a co-orbital NEA.
#
# The estimator below is a two-impulse patched-conic rendezvous, which is what
# Shoemaker-Helin approximates and what Module 3's reference table was built
# from.  Given the asteroid's a / e / i:
#
#   1. Transfer ellipse from Earth's orbit (1 AU) to the asteroid's apsis.
#   2. Departure v_infinity = vector difference between the transfer velocity
#      and Earth's orbital velocity, including the plane change for i.
#   3. Δv to leave LEO onto that hyperbola:  √(v_esc² + v_inf²) − v_LEO.
#   4. Δv to match the asteroid's velocity at the apsis (rendezvous, not
#      flyby; a mining mission has to stop).
#
# Return is the mirror image: the apsis-match burn to get back onto an
# Earth-intercept trajectory, then either a propulsive capture at Earth
# (√(v_esc² + v_inf²) − v_LEO again) or an atmospheric entry that costs
# essentially no propellant but buys a heat shield.  This replaces the flat
# `aerocapture_dv_savings_m_s` constant with a per-asteroid saving.
#
# The validation table lives on asteroid_transfer_dv_km_s.  In summary: within
# ~10% of both Module 3's reference table and published mission values, which is
# the accuracy an analytic estimator can honestly claim.  It runs slightly LOW
# against published figures for the easiest co-orbital targets, where real
# mission design finds better transfers than a two-impulse apsis match.
# The floor is the physical one: escaping LEO costs √2·v_LEO − v_LEO ≈
# 3.22 km/s no matter how accessible the target is.
#
# v1.10.0: WHICH apsis to meet the target at is now searched rather than picked
# by rule, and the search is resolved against the destination being flown; see
# asteroid_transfer_options_km_s and asteroid_dv_options.

V_EARTH_KM_S     = 29.784              # Earth mean orbital velocity
MU_EARTH_KM3_S2  = 398_600.4418        # Earth gravitational parameter
R_LEO_KM         = 6_378.14 + 200.0    # 200-km circular parking orbit


# ── Geostationary orbit  (v1.19.0) ───────────────────────────────────────────
# Every quantity here is a constant of the ORBIT, so all of it is resolved once
# at import.  `_geo_capture_dv_km_s` runs twice per catalog row on every
# destination, and re-deriving a per-destination constant per call is defect
# class 3 in CLAUDE.md.
R_GEO_KM = 42_164.14                   # geostationary radius
# Asteroid arrivals are near the ecliptic and GEO is equatorial, so the
# capture burn buys 23.44 deg of plane change as well as the speed change.
# This is the term intuition drops, and it is worth several hundred m/s.
_COS_ECLIPTIC_TILT = math.cos(math.radians(23.44))
_V_GEO_KM_S      = math.sqrt(MU_EARTH_KM3_S2 / R_GEO_KM)
_V_ESC_GEO_KM_S  = math.sqrt(2.0) * _V_GEO_KM_S
_V_LEO_KM_S      = math.sqrt(MU_EARTH_KM3_S2 / R_LEO_KM)
_V_ESC_LEO_KM_S  = math.sqrt(2.0) * _V_LEO_KM_S
# The GEO transfer ellipse, LEO perigee to GEO apogee.
_A_GTO_KM           = (R_LEO_KM + R_GEO_KM) / 2.0
_V_GTO_PERIGEE_KM_S = math.sqrt(MU_EARTH_KM3_S2 * (2.0 / R_LEO_KM - 1.0 / _A_GTO_KM))
_V_GTO_APOGEE_KM_S  = math.sqrt(MU_EARTH_KM3_S2 * (2.0 / R_GEO_KM - 1.0 / _A_GTO_KM))


def _circularise_at_geo_km_s(v_apogee_km_s: float) -> float:
    """One apogee burn that circularises at GEO and removes the plane change.

    Law of cosines, not a sum: a burn that changes speed and direction at once
    costs less than doing both separately, and adding them would overstate
    every GEO arrival in the model.
    """
    return math.sqrt(v_apogee_km_s * v_apogee_km_s
                     + _V_GEO_KM_S * _V_GEO_KM_S
                     - 2.0 * v_apogee_km_s * _V_GEO_KM_S * _COS_ECLIPTIC_TILT)


# Finishing a GTO-shaped capture: 1.836 km/s, and independent of how fast the
# spacecraft arrived, which is why it is a constant rather than a term.
_DV_GTO_APOGEE_TO_GEO_KM_S = _circularise_at_geo_km_s(_V_GTO_APOGEE_KM_S)

# Aerocapture at Earth into an ellipse whose apogee is at GEO, then the same
# apogee burn.  Drag removes the arrival energy whatever it was, so this is
# FLAT in v_infinity: 1.737 km/s at every arrival speed.
#
# ⚠️  It is not an aerobrake TRIM like the LEO case.  At LEO drag can do the
# whole job and the propulsive residue is 100 m/s; at GEO drag can only lower
# the apogee to GEO, and circularising there is still 1.7 km/s of real burn.
# Copying `DV_AEROBRAKE_TRIM_KM_S` here would understate a GEO arrival by 17x.
_A_GEO_AEROCAPTURE_KM = ((6_378.14 + 100.0) + R_GEO_KM) / 2.0
DV_GEO_AEROCAPTURE_ARRIVAL_KM_S = _circularise_at_geo_km_s(
    math.sqrt(MU_EARTH_KM3_S2 * (2.0 / R_GEO_KM - 1.0 / _A_GEO_AEROCAPTURE_KM)))

R_MOON_ORBIT_KM  = 384_400.0           # lunar mean orbital radius
# NRHO insertion at apogee, Module 3 DELTA_V_REFERENCE "TLI → NRHO insertion".
DV_NRHO_INSERTION_KM_S = 0.450
# Periapsis-raise burn to finish an aerobraked capture, Module 3
# "NEA → LEO delivery (aerobraked)".
DV_AEROBRAKE_TRIM_KM_S = 0.100
# Deorbit from a 200-km circular parking orbit onto an entry trajectory.  Small
# but not zero, and the all-propulsive Earth-surface return has to pay it: that
# architecture captures into LEO and then still has to come down.  Standard
# figure for lowering perigee to ~50 km from a 200-km circular orbit.
DV_LEO_DEORBIT_KM_S = 0.100

# ── Lunar surface  (v1.6.0) ──────────────────────────────────────────────────
# From a cislunar (NRHO) depot down to the surface, Module 3 DELTA_V_REFERENCE:
#   NRHO → LLO   0.73 km/s        LLO → surface   1.87 km/s
DV_NRHO_TO_LUNAR_SURFACE_KM_S = 0.730 + 1.870

# ── Mars  (v1.6.0) ───────────────────────────────────────────────────────────
MU_MARS_KM3_S2   = 42_828.37           # Mars gravitational parameter
R_MARS_PARK_KM   = 3_396.2 + 200.0     # 200-km circular parking orbit
A_MARS_AU        = 1.523_679           # Mars semi-major axis
# Terminal propulsive descent after aeroentry, Module 3 "Mars entry → surface".
DV_MARS_RETROPROP_KM_S = 0.800
# Propulsive descent from low Mars orbit with NO atmospheric help; the
# fallback when aerocapture is switched off.  Mirrors the 4.1 km/s ascent.
DV_MARS_POWERED_DESCENT_KM_S = 4.100

# ── Mars orbit depot  (v1.18.0) ──────────────────────────────────────────────
# The 1-sol elliptical staging orbit, 250 x 33,793 km altitude, Module 3
# DELTA_V_REFERENCE "Mars arrival -> 1-sol orbit (MOI)".  Its period is 24.60 h
# against a sol's 24.62, which is where the name comes from, and NASA DRA 5.0
# stages there for the reason NRHO is the cislunar depot: capture only has to
# BIND the orbit, and the burn happens deep at periapsis where Oberth pays.
#
# Both velocities below are constants of the DEPOT, not of the arriving
# candidate, so they are resolved once here rather than per call.  That is
# defect class 3 in CLAUDE.md, "a quantity asked at a finer granularity than it
# has answers", and this function runs twice per catalog row.
R_MARS_1SOL_PERIAPSIS_KM = 3_396.2 +    250.0
R_MARS_1SOL_APOAPSIS_KM  = 3_396.2 + 33_793.0
_A_MARS_1SOL_KM = (R_MARS_1SOL_PERIAPSIS_KM + R_MARS_1SOL_APOAPSIS_KM) / 2.0
_V_ESC_MARS_1SOL_KM_S = math.sqrt(2.0 * MU_MARS_KM3_S2 / R_MARS_1SOL_PERIAPSIS_KM)
_V_ELL_MARS_1SOL_KM_S = math.sqrt(MU_MARS_KM3_S2 * (2.0 / R_MARS_1SOL_PERIAPSIS_KM
                                                    - 1.0 / _A_MARS_1SOL_KM))


def _leo_departure_dv_km_s(v_inf_km_s: float) -> float:
    """Δv to go from circular LEO onto a hyperbola with this v_infinity.

    Symmetric with capture: the same expression gives the propulsive cost of
    arriving from a hyperbola and circularising back into LEO.
    """
    v_leo = math.sqrt(MU_EARTH_KM3_S2 / R_LEO_KM)
    v_esc = math.sqrt(2.0) * v_leo
    return math.sqrt(v_esc * v_esc + v_inf_km_s * v_inf_km_s) - v_leo


def _cislunar_capture_dv_km_s(v_inf_km_s: float) -> float:
    """Δv to capture from an arrival hyperbola into a cislunar (NRHO) depot.

    Two burns, and the first one is where the saving lives:

      1. Capture at LOW PERIGEE into an ellipse whose apogee reaches lunar
         distance.  Burning deep in Earth's well takes the Oberth benefit, so
         killing the hyperbolic excess costs far less here than it would out
         at lunar distance:
             Δv₁ = √(v_esc² + v_inf²) − √(μ(2/r_p − 1/a_ellipse))
      2. NRHO insertion at apogee, Module 3's 450 m/s.

    The result is markedly CHEAPER than circularising into LEO, because LEO
    capture has to kill the entire perigee velocity down to circular while
    this only has to bind the orbit.  At v_inf = 3 km/s: ~0.96 km/s to a
    cislunar depot against ~3.59 km/s to LEO.

    That is the single most consequential fact in the delivery-architecture
    model: the destination that pays the most per kilogram is also the
    cheapest one to reach.
    """
    v_leo = math.sqrt(MU_EARTH_KM3_S2 / R_LEO_KM)
    v_esc = math.sqrt(2.0) * v_leo
    v_hyp = math.sqrt(v_esc * v_esc + v_inf_km_s * v_inf_km_s)
    a_ell = (R_LEO_KM + R_MOON_ORBIT_KM) / 2.0
    v_ell = math.sqrt(MU_EARTH_KM3_S2 * (2.0 / R_LEO_KM - 1.0 / a_ell))
    return max(0.0, v_hyp - v_ell) + DV_NRHO_INSERTION_KM_S


def _geo_capture_dv_km_s(v_inf_km_s: float) -> float:
    """Propulsive Δv to capture from an arrival hyperbola into GEO.

    Two routes, and unlike the cislunar case NEITHER ALWAYS WINS, so both are
    priced and the cheaper is taken:

      (a) DIRECT.  Meet GEO at its own radius and kill the hyperbolic excess
          plus the plane change in one burn out there.  Cheap when the
          spacecraft arrives slowly, because there is little excess to kill
          and the burn is done at a low orbital speed.

      (b) OBERTH.  Capture at LEO perigee into a GTO-shaped ellipse, taking
          the Oberth benefit deep in the well, then circularise and change
          plane at apogee.  The perigee burn is efficient but the apogee burn
          is fixed at 1.730 km/s however the spacecraft got there.

    ⚠️  THAT 1.730 IS NOT MODULE 2's 1.836, AND THE TWO MUST NOT BE
    RECONCILED.  They are the same manoeuvre buying a different plane change.
    Module 2 prices a kilogram LAUNCHED from Earth, which parks at the 28.5
    deg of a Canaveral ascent; this module prices a kilogram ARRIVING from an
    asteroid, which comes in near the ecliptic, 23.44 deg off the equator.
    Coplanar the same burn would be 1.477, so the inclination is worth 253 m/s
    on arrival and 359 on launch.  Making them agree would put a launch
    site's latitude into an interplanetary trajectory.

    (a) wins below v_inf = 3.585 km/s and (b) above it: 2.05 against 2.55 at
    v_inf = 1, and 4.00 against 3.58 at v_inf = 5.  **That is the difference
    from `_cislunar_capture_dv_km_s`, where the Oberth route always wins**,
    and the reason is the apogee burn.  A cislunar depot is captured into by
    BINDING an ellipse, which costs 450 m/s; GEO has to be circularised into,
    which costs four times that and does not fall with arrival speed.

    So the destination that is cheapest to reach from an asteroid is still
    cislunar, at 0.59 km/s against GEO's 2.05, BOTH AT v_inf = 1.  Quote them
    at one arrival speed or not at all: cislunar's oft-quoted 0.96 is its
    v_inf = 3 figure, and pairing that with GEO's v_inf = 1 best case compares
    two different arrivals.  Cislunar wins at every v_inf either way.
    """
    # (a) direct capture at the GEO radius
    v_hyp_at_geo = math.sqrt(_V_ESC_GEO_KM_S * _V_ESC_GEO_KM_S
                             + v_inf_km_s * v_inf_km_s)
    direct = _circularise_at_geo_km_s(v_hyp_at_geo)

    # (b) Oberth capture at low perigee, then the fixed apogee burn
    v_hyp_at_leo = math.sqrt(_V_ESC_LEO_KM_S * _V_ESC_LEO_KM_S
                             + v_inf_km_s * v_inf_km_s)
    oberth = ((v_hyp_at_leo - _V_GTO_PERIGEE_KM_S)
              + _DV_GTO_APOGEE_TO_GEO_KM_S)

    return direct if direct < oberth else oberth


def _transfer_legs_for_apsis(
    a: float, e: float, i: float, r_target: float,
) -> Optional[Dict[str, float]]:
    """Full Δv leg set for rendezvousing at one specific apsis, in km/s.

    Split out of `asteroid_transfer_dv_km_s` in v1.10.0 so both apsides can be
    priced and the cheaper one CHOSEN rather than guessed.  See
    `asteroid_transfer_options_km_s` for why that matters.

    All heliocentric work is in canonical units (Earth orbit radius = 1, Earth
    orbital speed = 1) and converted to km/s at the end.
    """
    if r_target <= 0:
        return None

    # ── 1. Transfer ellipse from r=1 to r=r_target ───────────────────────────
    a_t = (1.0 + r_target) / 2.0
    v_t_at_earth_sq = 2.0 / 1.0 - 1.0 / a_t
    if v_t_at_earth_sq <= 0:
        return None
    v_t_at_earth = math.sqrt(v_t_at_earth_sq)

    # ── 2. v_infinity at Earth departure, plane change included ──────────────
    # Law of cosines between the transfer velocity and Earth's (speed 1).
    cos_i = math.cos(math.radians(i))
    v_inf_sq = v_t_at_earth ** 2 + 1.0 - 2.0 * v_t_at_earth * cos_i
    v_inf = math.sqrt(max(v_inf_sq, 0.0)) * V_EARTH_KM_S

    # ── 3. LEO departure ─────────────────────────────────────────────────────
    dv_depart = _leo_departure_dv_km_s(v_inf)

    # ── 4. Apsis rendezvous burn ─────────────────────────────────────────────
    v_t_at_target_sq = 2.0 / r_target - 1.0 / a_t
    v_ast_at_target_sq = 2.0 / r_target - 1.0 / a
    if v_t_at_target_sq <= 0 or v_ast_at_target_sq <= 0:
        return None
    dv_match = abs(math.sqrt(v_ast_at_target_sq)
                   - math.sqrt(v_t_at_target_sq)) * V_EARTH_KM_S

    dv_out = dv_depart + dv_match

    # ── Return legs ──────────────────────────────────────────────────────────
    # Departing the asteroid costs the same apsis burn in reverse.  What
    # happens on arrival is the delivery architecture, and it differs by
    # destination far more than intuition suggests:
    #
    #   Earth surface, direct entry, no capture burn at all.  The arrival
    #     energy is dumped into a heat shield, whose mass the Module 4 cascade
    #     carries outbound and pushes back through the return burn.
    #   LEO, propulsive, the most expensive option in the model.  LEO is the
    #     deepest of the three destinations, so circularising there means
    #     killing the whole hyperbolic excess AND the escape velocity.
    #   LEO, aerobraked, trades that Δv for TPS mass and months of passes.
    #   Cislunar; cheapest, because capture only has to BIND the orbit, and
    #     the burn happens at low perigee where Oberth pays best.
    #   Lunar surface, cislunar capture, then NRHO→LLO→surface.  Airless, so
    #     that last 2.6 km/s is entirely propulsive.
    #   Mars, not an Earth return at all.  See the separate transfer below.
    dv_leo_capture = _leo_departure_dv_km_s(v_inf)
    dv_cislunar    = _cislunar_capture_dv_km_s(v_inf)

    legs = {
        "dv_out":                 dv_out,
        "v_inf":                  v_inf,
        "r_rendezvous_au":        r_target,
        "ret_earth_surface_aero": dv_match,
        # v1.10.0: capture into LEO and then LAND is not the same manoeuvre as
        # capture into LEO and stay there; the capsule still has to come down.
        # The docstring claimed the deorbit burn all along; it was never added.
        "ret_earth_surface_prop": dv_match + dv_leo_capture + DV_LEO_DEORBIT_KM_S,
        "ret_leo_prop":           dv_match + dv_leo_capture,
        "ret_leo_aero":           dv_match + DV_AEROBRAKE_TRIM_KM_S,
        "ret_cislunar_prop":      dv_match + dv_cislunar,
        # v1.19.0: GEO.  The propulsive route is a search over two capture
        # geometries rather than one formula; see `_geo_capture_dv_km_s`.
        # The aerocaptured route is FLAT in v_infinity because drag removes
        # whatever arrival energy there was, and what is left is the
        # circularisation, which is not a trim.
        "ret_geo_prop":           dv_match + _geo_capture_dv_km_s(v_inf),
        "ret_geo_aero":           dv_match + DV_GEO_AEROCAPTURE_ARRIVAL_KM_S,
        "ret_lunar_surface_prop": dv_match + dv_cislunar
                                  + DV_NRHO_TO_LUNAR_SURFACE_KM_S,
    }

    # ── Mars: a different journey, not a discounted Earth return ─────────────
    # Delivering to Mars does not go near Earth.  The heliocentric transfer
    # runs from the asteroid's orbit to Mars' (1.524 AU), so the departure
    # burn, the arrival v_infinity and the capture are all different numbers.
    # Many NEAs have aphelia out near Mars, which makes them genuinely closer
    # to a Mars base than to Earth; a fact the model can only show if this
    # leg is computed rather than approximated.
    mars = _asteroid_to_mars_dv_km_s(a, e, i, r_target)
    if mars is not None:
        legs.update(mars)
    return legs


def asteroid_transfer_options_km_s(
    a_au: float, e: float, i_deg: float,
) -> List[Dict[str, float]]:
    """Every rendezvous geometry worth pricing for one asteroid (v1.10.0).

    A two-impulse transfer can meet the target at either apsis, and which one
    is cheaper is a property of the individual orbit; not something a rule can
    settle in advance.  Until v1.10.0 the estimator applied one:

        r_target = aphelion if aphelion >= 1 AU else perihelion

    which is right for most main-belt bodies and demonstrably wrong for others.
    The trade is between two terms that move in opposite directions.  Meeting a
    body at aphelion means a long, slow transfer whose arrival speed nearly
    matches the target's, cheap rendezvous, expensive departure.  Meeting it at
    perihelion means a short transfer, but both bodies are moving fast there and
    the match burn is large.  Which term dominates depends on a and e together,
    so it has to be evaluated, not assumed.

    Returns one full leg dict per feasible apsis, each tagged with
    `rendezvous_apsis` and `r_rendezvous_au`.  Callers pick, and because the
    right pick depends on the DESTINATION (a body reached cheaply at aphelion
    may still be a worse Mars target than the same body met at perihelion), the
    choice belongs to `asteroid_dv_options`, which knows where the cargo is
    going, rather than to this function.

    An empty list means the elements were unusable.
    """
    try:
        a = float(a_au); e = float(e); i = float(i_deg)
    except (TypeError, ValueError):
        return []
    if not (a > 0) or not (0.0 <= e < 1.0) or not (0.0 <= i <= 180.0):
        return []

    Q = a * (1.0 + e)
    q = a * (1.0 - e)

    options: List[Dict[str, float]] = []
    for label, r_target in (("aphelion", Q), ("perihelion", q)):
        legs = _transfer_legs_for_apsis(a, e, i, r_target)
        if legs is None:
            continue
        legs["rendezvous_apsis"] = label
        options.append(legs)
        if abs(Q - q) < 1e-9:
            break                      # circular orbit, the apsides coincide
    return options


def asteroid_transfer_dv_km_s(
    a_au: float, e: float, i_deg: float,
) -> Optional[Dict[str, float]]:
    """Patched-conic Δv budget for a rendezvous mission to one asteroid.

    Returns a dict of Δv legs in km/s, or None if the elements are unusable:

        dv_out                  outbound, LEO departure + apsis rendezvous
        v_inf                   arrival hyperbolic excess back at Earth
        r_rendezvous_au         where the transfer meets the target
        rendezvous_apsis        which apsis that is
        ret_earth_surface_aero  direct entry, no capture burn at all
        ret_earth_surface_prop  propulsive capture into LEO, then deorbit
        ret_leo_prop            propulsive capture into LEO
        ret_leo_aero            aerocapture + aerobraking, trim burn only
        ret_cislunar_prop       Oberth capture + NRHO insertion

    v1.5.0, was a 3-tuple (out, return_propulsive, return_aerocapture) when
    Earth's surface was the only destination the pipeline could model.

    v1.10.0; the rendezvous apsis is now searched (see
    `asteroid_transfer_options_km_s`).  This wrapper resolves it against an
    EARTH round trip, which is what the validation figures below were measured
    against; Module 4 itself calls the options function and resolves against
    the destination actually being flown.

    VALIDATED against Module 3's independently-sourced DELTA_V_REFERENCE:
      target                              estimator   reference
      main belt (a=2.7, e=0.1, i=10°)     10.43 km/s   10.5 km/s (Module 3)
      moderate NEA (a=1.2, e=0.3, i=8°)    5.58 km/s    6.5 km/s (Module 3)
      Bennu   (a=1.126, e=0.204, i=6.0°)   4.64 km/s   ~5.1 km/s (published)
      Eros    (a=1.458, e=0.223, i=10.8°)  6.10 km/s   ~6.5 km/s (published)
      Itokawa (a=1.324, e=0.280, i=1.6°)   4.14 km/s   ~4.6 km/s (published)
    Every one of those resolves to the aphelion option, so the figures are
    unchanged by the apsis search; it only moves bodies the old rule got wrong.
    """
    options = asteroid_transfer_options_km_s(a_au, e, i_deg)
    if not options:
        return None
    return min(options, key=lambda o: o["dv_out"] + o["ret_earth_surface_prop"])


def _asteroid_to_mars_dv_km_s(
    a: float, e: float, i_deg: float, r_target: float,
) -> Optional[Dict[str, float]]:
    """Δv from an asteroid to the Martian surface, in km/s.

    Same patched-conic treatment as the Earth legs, but the heliocentric
    transfer terminates at Mars' orbit instead of Earth's, and the capture is
    into Mars' gravity well.

    Returns the propulsive and aerocaptured surface arrivals, or None if the
    transfer geometry does not close.  Mars has an atmosphere, so aerocapture
    is genuinely available, and it is worth several km/s.
    """
    # ── 1. Transfer ellipse from the asteroid's apsis to Mars' orbit ─────────
    a_t = (r_target + A_MARS_AU) / 2.0
    v_t_at_ast_sq  = 2.0 / r_target - 1.0 / a_t
    v_ast_sq       = 2.0 / r_target - 1.0 / a
    v_t_at_mars_sq = 2.0 / A_MARS_AU - 1.0 / a_t
    if min(v_t_at_ast_sq, v_ast_sq, v_t_at_mars_sq) <= 0:
        return None

    # ── 2. Departure burn at the asteroid, plane change included ────────────
    # Law of cosines, same as the Earth-departure treatment: the asteroid's
    # inclination has to be bought out to reach Mars' (nearly co-planar) orbit.
    cos_i = math.cos(math.radians(i_deg))
    dv_dep_sq = (v_t_at_ast_sq + v_ast_sq
                 - 2.0 * math.sqrt(v_t_at_ast_sq * v_ast_sq) * cos_i)
    dv_depart = math.sqrt(max(dv_dep_sq, 0.0)) * V_EARTH_KM_S

    # ── 3. Arrival v_infinity at Mars ───────────────────────────────────────
    v_mars = math.sqrt(1.0 / A_MARS_AU)          # circular, canonical units
    v_inf_mars = abs(math.sqrt(v_t_at_mars_sq) - v_mars) * V_EARTH_KM_S

    # ── 4. Capture and descent ──────────────────────────────────────────────
    v_circ = math.sqrt(MU_MARS_KM3_S2 / R_MARS_PARK_KM)
    v_esc  = math.sqrt(2.0) * v_circ
    dv_capture = math.sqrt(v_esc * v_esc + v_inf_mars * v_inf_mars) - v_circ

    # v1.18.0: capture into the 1-sol DEPOT orbit, which is a different and
    # much cheaper manoeuvre than the circularisation above; at a Hohmann
    # arrival (v_inf 2.65 km/s) it is 0.90 km/s against 2.10.  The saving is
    # the apoapsis that never has to be brought down.
    dv_capture_1sol = (math.sqrt(_V_ESC_MARS_1SOL_KM_S * _V_ESC_MARS_1SOL_KM_S
                                 + v_inf_mars * v_inf_mars)
                       - _V_ELL_MARS_1SOL_KM_S)

    return {
        "v_inf_mars":              v_inf_mars,
        "dv_depart_for_mars":      dv_depart,
        # Aeroentry: the atmosphere absorbs capture AND most of the descent,
        # leaving only terminal retropropulsion.  Paid for in TPS mass.
        "ret_mars_surface_aero":   dv_depart + DV_MARS_RETROPROP_KM_S,
        # All-propulsive: capture into low Mars orbit, then fly the lander
        # down against gravity with no atmospheric help.  Brutal, and the
        # reason nobody plans a Mars mission this way.
        "ret_mars_surface_prop":   dv_depart + dv_capture
                                   + DV_MARS_POWERED_DESCENT_KM_S,
        # ── Mars ORBIT depot (v1.18.0) ───────────────────────────────────────
        # Nothing lands, so neither the retropropulsion nor the powered
        # descent applies and there is no entry-survival fraction on the
        # price side either.  What is left is the departure burn and the
        # capture.
        "ret_mars_orbit_prop":     dv_depart + dv_capture_1sol,
        # Aerocapture into the 1-sol ellipse, then a periapsis-raise burn to
        # get out of the atmosphere: Odyssey and MRO flew exactly this at
        # Mars.  Charged at the Earth aerobrake trim, which is CONSERVATIVE
        # here; the real raise from an aerocapture periapsis to 250 km, taken
        # at a 37,189 km apoapsis, is ~12 m/s against the 100 charged.  The
        # existing sourced constant is preferred over a new invented one for
        # a term this far inside the noise of the departure burn.
        "ret_mars_orbit_aero":     dv_depart + DV_AEROBRAKE_TRIM_KM_S,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY ARCHITECTURE  (v1.5.0)
# ─────────────────────────────────────────────────────────────────────────────
# `delivery_destination` is not a price label; it selects a physically
# different mission.  Each architecture decides which return leg is flown and
# which cost lines exist at all.
#
#   uses_tps        heat shield hauled outbound and pushed back through the
#                   return burn (direct entry, or aerobraked capture)
#   window_phasing_au  the heliocentric orbit a DEPARTURE WINDOW is phased
#                   against; see `window_phasing_au()` below
#   returns_to_earth  the cargo enters the atmosphere.  Drives the re-entry
#                   capsule, the Earth recovery campaign, and the full
#                   launch+re-entry Part 450 licence.
#
# An in-space delivery swaps the re-entry capsule for a berthing adapter, the
# $15M recovery campaign for $2M of depot handover, and the combined licence
# for the launch-only one.

DELIVERY_ARCHITECTURES: Dict[str, dict] = {
    "earth_surface": {
        "returns_to_earth": True,
        "aero_leg":  "ret_earth_surface_aero",
        "prop_leg":  "ret_earth_surface_prop",
        "aero_allowed": True,
        "window_phasing_au": 1.0,
        "label": "re-entry capsule to Earth's surface",
    },
    "leo": {
        "returns_to_earth": False,
        "aero_leg":  "ret_leo_aero",
        "prop_leg":  "ret_leo_prop",
        "aero_allowed": True,     # aerocapture + multi-pass aerobraking
        "window_phasing_au": 1.0,
        "label": "berthed at an LEO depot",
    },
    # v1.19.0.  A depot, so a berthing adapter and no lander, and the cargo
    # never re-enters, so no capsule and no recovery campaign.  Aerocapture is
    # allowed because the arrival passes through Earth's atmosphere on the way
    # in, which is what separates this from `cislunar` directly below.
    "geo": {
        "returns_to_earth": False,
        "aero_leg":  "ret_geo_aero",
        "prop_leg":  "ret_geo_prop",
        "aero_allowed": True,     # aerocapture into a GEO-apogee ellipse
        "window_phasing_au": 1.0,
        "label": "berthed at a geostationary servicing depot",
    },
    "cislunar": {
        "returns_to_earth": False,
        "aero_leg":  None,        # never passes through the atmosphere
        "prop_leg":  "ret_cislunar_prop",
        "aero_allowed": False,
        "window_phasing_au": 1.0,
        "label": "berthed at a cislunar (NRHO) depot",
    },
    "lunar_surface": {
        "returns_to_earth": False,
        "aero_leg":  None,        # the Moon has no atmosphere to brake against
        "prop_leg":  "ret_lunar_surface_prop",
        "aero_allowed": False,
        "needs_lander": True,
        "window_phasing_au": 1.0,
        "label": "landed at a lunar surface base",
    },
    # v1.18.0.  No `needs_lander`, so this carries a $60k/kg berthing adapter
    # rather than the $200k/kg lander mars_surface pays for; a depot is
    # berthed with, not landed on.  That is the second of the two cost lines
    # that separate the Mars pair, the first being the entry-survival
    # fraction on the price side.
    "mars_orbit": {
        "returns_to_earth": False,
        "aero_leg":  "ret_mars_orbit_aero",
        "prop_leg":  "ret_mars_orbit_prop",
        "aero_allowed": True,     # aerocapture into the ellipse; Odyssey / MRO
        # v1.19.2: MARS, not Earth.  A depot in Mars orbit is reached by
        # the same heliocentric transfer as the surface below it.
        "window_phasing_au": A_MARS_AU,
        "label": "berthed at a 1-sol Mars-orbit depot",
    },
    "mars_surface": {
        "returns_to_earth": False,
        "aero_leg":  "ret_mars_surface_aero",
        "prop_leg":  "ret_mars_surface_prop",
        "aero_allowed": True,     # Mars aerocapture is worth several km/s
        "needs_lander": True,
        "window_phasing_au": A_MARS_AU,
        "label": "landed at a Mars surface base",
    },
}


# Asserted rather than defaulted, and asserted at IMPORT.  A `.get(..., 1.0)`
# here would be a silent default of the WRONG value for any destination off
# Earth's orbit, which is the exact defect v1.19.2 fixed: `mars_orbit` shipped
# in v1.18.0 phasing its launch windows against Earth because the test that
# picked Mars named `mars_surface` and nothing else.  A destination that forgets
# to declare this now fails loudly on the way in, next to the table it forgot.
assert all("window_phasing_au" in a for a in DELIVERY_ARCHITECTURES.values()), (
    "DELIVERY_ARCHITECTURES entries missing window_phasing_au: %s"
    % sorted(k for k, a in DELIVERY_ARCHITECTURES.items()
             if "window_phasing_au" not in a))


_ARCH_BY_RAW_KEY: Dict[Any, dict] = {}


def delivery_architecture(destination: str) -> dict:
    """Look up the mission architecture for a delivery destination.

    Unknown destinations fall back to earth_surface, the conservative
    choice, and the one whose cost lines are all present.

    v1.17.1: the resolved answer is memoised on the RAW argument, because
    `mission_cost_usd` calls this once per programme option: 458,337 times on
    a 150-row beneficiated sample with the search on, to normalise the same
    string and index the same dict.  Only the hit path is memoised: an unknown
    destination still falls through and still prints its warning every time,
    which is the loud behaviour that made it a warning.
    """
    try:
        hit = _ARCH_BY_RAW_KEY.get(destination)
    except TypeError:
        hit = None                    # unhashable caller; skip the memo
    if hit is not None:
        return hit

    key = str(destination or "").strip().lower()
    if key not in DELIVERY_ARCHITECTURES:
        print(f"     WARN   Unknown delivery_destination {destination!r} - "
              f"falling back to 'earth_surface'.  Valid: "
              f"{', '.join(sorted(DELIVERY_ARCHITECTURES))}")
        return DELIVERY_ARCHITECTURES["earth_surface"]

    arch = DELIVERY_ARCHITECTURES[key]
    try:
        _ARCH_BY_RAW_KEY[destination] = arch
    except TypeError:
        pass
    return arch


def window_phasing_au(destination: str) -> float:
    """Heliocentric semi-major axis a departure window to `destination` is
    phased against, in AU.

    Launch windows recur at the SYNODIC period between the asteroid and the
    body the cargo is delivered to, so the figure that belongs here is the
    DESTINATION's orbit around the Sun, not Earth's.  Everything in Earth's
    system, LEO, GEO, a cislunar depot, the lunar surface and Earth itself,
    rides Earth's orbit and phases against 1 AU; a Mars delivery waits on
    Earth-Mars alignment whichever end of the well it stops at.

    🚨  v1.19.2.  This existed as a conditional testing `== "mars_surface"`,
    written in two places, and `mars_orbit` therefore phased against EARTH from
    the moment v1.18.0 shipped it: the same heliocentric transfer, the same
    arrival at Mars' orbit, and a launch cadence taken from the wrong planet.
    Measured on a 38,892-row stride sample of the catalog's 1,555,667
    semi-major axes, that is the wrong answer on 99.97% of rows, and it is too
    SHORT on 99.46% of them: the median synodic period goes 1.2976 yr against
    Earth to 3.3033 yr against Mars.
    The `mars_surface` cadence CLAUDE.md records, 3.798 yr raw against ~1.37
    everywhere else, is the same term doing the same thing one leg further
    down, which is what makes the old value visibly wrong rather than merely
    different.

    Reading it off `DELIVERY_ARCHITECTURES` rather than re-testing a name is
    the point: the architecture table is where a destination already declares
    its physical mission, so the next one to be added is asked this question
    where its author is already working, instead of in two conditionals
    thousands of lines away that name a destination it is not.
    """
    return delivery_architecture(destination)["window_phasing_au"]


def uses_tps(config: CalcConfig) -> bool:
    """True when this architecture CAN fly a heat shield.

    Aerocapture is a request, not a guarantee: a cislunar delivery never
    touches the atmosphere, so asking for aerocapture there gets you a
    propulsive capture and no TPS mass.

    v1.10.0: this answers "is aerocapture on the menu", not "is it flown".
    Whether it actually pays is decided per asteroid; see
    `asteroid_dv_options`.
    """
    arch = delivery_architecture(config.delivery_destination)
    return bool(config.use_aerocapture_return and arch["aero_allowed"])


def _dv_fallback_m_s(config: CalcConfig, aero: bool) -> Tuple[float, float]:
    """Uniform reference Δv for a row whose orbital elements are unusable.

    Pre-v1.4.0 behaviour, retained as the fallback.  No elements means no
    v_infinity, so the destination-specific capture cannot be derived;
    approximate it from Module 3's reference figures instead.
    """
    dv_out            = config.default_dv_outbound_m_s
    dv_ret_propulsive = config.default_dv_return_m_s
    if config.delivery_destination == "cislunar":
        # Module 3 "NEA → cislunar NRHO (Oberth capture)" vs "NEA → Earth
        # return (propulsive)": 960 / 5,500 of the propulsive budget.
        dv_ret = dv_ret_propulsive * (960.0 / 5_500.0)
    elif aero:
        dv_ret = max(500.0, dv_ret_propulsive - config.aerocapture_dv_savings_m_s)
    else:
        dv_ret = dv_ret_propulsive
    return dv_out, dv_ret


def asteroid_dv_options(
    asteroid_row: Row, config: CalcConfig,
) -> List[Dict[str, object]]:
    """Every (return mode × rendezvous apsis) worth flying to this asteroid.

    v1.10.0.  Two things that were global settings are properly per-asteroid
    decisions, and both were being made for the whole catalog at once:

    RETURN MODE.  `use_aerocapture_return` FORCED aerocapture wherever the
    architecture allowed it.  But aerocapture is a trade, not a free saving: it
    buys Δv with a heat shield massing 15% of the returned payload, hauled out
    from Earth as dead mass and pushed back through the return burn.  For a
    target arriving slowly the Δv it saves is small and the TPS is not worth
    carrying; for a fast one it is worth several km/s.  Where the crossover
    falls depends on the asteroid's arrival v_infinity and on the stage's Isp,
    so it belongs here with the other per-target choices, alongside the vehicle
    and the propellant; both of which the model has always picked per asteroid.

    RENDEZVOUS APSIS.  Which apsis is cheaper depends on the destination as
    well as the orbit, because the outbound and return legs are priced against
    different bodies: a Mars delivery pays no Earth capture at all, so a
    geometry that is poor for an Earth return can be the best one for Mars.

    Returns a list of dicts with `aero`, `dv_out_m_s`, `dv_ret_m_s`,
    `rendezvous_apsis` and `tps_frac`, best apsis already resolved for each
    return mode.  Never empty: a row with unusable elements gets the single
    uniform-Δv fallback option.
    """
    arch = delivery_architecture(config.delivery_destination)
    # Which return modes exist here at all.  Cislunar and the lunar surface
    # have no atmosphere to brake against, so they are propulsive-only whatever
    # the config asks for.
    modes = [False]
    if config.use_aerocapture_return and arch["aero_allowed"]:
        modes = [True, False] if config.optimise_architecture_per_asteroid else [True]

    options = asteroid_transfer_options_km_s(
        asteroid_row.get("semi_major_axis_au"),
        asteroid_row.get("eccentricity"),
        asteroid_row.get("inclination_deg"),
    ) if config.use_per_asteroid_dv else []

    out: List[Dict[str, object]] = []
    for aero in modes:
        leg = arch["aero_leg"] if aero else arch["prop_leg"]
        best = None
        for legs in options:
            if leg not in legs:
                continue                # Mars geometry that did not close
            dv_out = min(max(legs["dv_out"] * 1_000.0, 3_000.0),
                         config.max_dv_outbound_m_s)
            dv_ret = min(max(legs[leg] * 1_000.0, 300.0),
                         config.max_dv_outbound_m_s)
            # Resolve the apsis against the round trip actually being flown,
            # not against a fixed Earth return.
            if best is None or (dv_out + dv_ret) < (best["dv_out_m_s"] + best["dv_ret_m_s"]):
                best = {"dv_out_m_s": dv_out, "dv_ret_m_s": dv_ret,
                        "rendezvous_apsis": legs["rendezvous_apsis"]}
        if best is None:
            dv_out, dv_ret = _dv_fallback_m_s(config, aero)
            best = {"dv_out_m_s": dv_out, "dv_ret_m_s": dv_ret,
                    "rendezvous_apsis": "reference"}
        best["aero"]     = aero
        best["tps_frac"] = config.heat_shield_frac_of_payload if aero else 0.0
        out.append(best)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# ISRU RETURN PROPELLANT  (v1.10.0, made physical, and made per-asteroid)
# ─────────────────────────────────────────────────────────────────────────────
# `use_isru_return_propellant` was a global switch that, when on, deleted the
# return propellant from the outbound mass cascade for EVERY asteroid and
# charged a flat $50/kg for it.  Three things were wrong with that, and they
# compound:
#
#   1. It did not ask what the body is made of.  An M-type with a
#      comp_ice_fraction of exactly zero manufactured its return propellant
#      out of nothing.
#   2. It did not ask what the propellant IS.  Xenon and argon are noble gases
#      present in asteroids only in trace amounts; RP-1 is a refined
#      hydrocarbon; MMH/NTO needs a nitrogen source asteroids largely lack.
#      None of them can be made at a rubble pile, and the switch made all of
#      them free.
#   3. It charged no feed, no dig time and no energy.  Making propellant means
#      mining and baking MORE rock; that is the whole cost of ISRU, and it was
#      the one part not modelled.
#
# What is makeable from asteroid material starts with hydrolox: water,
# electrolysed, cryo-cooled.  The mass balance is stoichiometric.  Electrolysis
# yields 8 kg of O2 per kg of H2 (mass ratio of O to H2 in H2O).  A hydrolox
# stage runs oxidiser-rich of stoichiometric at an O/F around 6:1, so a
# kilogram of propellant is 1/(1+6) kg of H2, and getting that H2 takes 9x its
# mass in water:
#
#     water per kg of propellant = 9 / (1 + O/F) = 1.286 kg
#
# The surplus oxygen (8/7 produced against 6/7 burnt) is vented; a real depot
# would sell it, but this model has nobody to sell it to at an asteroid.
#
# ── v1.11.0: hydrolox is no longer the only answer ───────────────────────────
# v1.10.0 hardcoded the tuple ("hydrolox",) here, which was right about the
# chemistry it knew and wrong about the question.  Electrolysing water into
# cryogenic hydrogen and oxygen is the HARDEST thing you can do with asteroid
# water, not the only thing: a solar-thermal or electrothermal steam rocket
# boils it and thrusts on the vapour at 1.00 kg of water per kg of propellant
# against hydrolox's 1.286, with no electrolyser, no liquefaction and no
# cryogenic tank.  It buys that at 190 s of Isp against 452.
#
# Which of those wins is a real trade and it varies by body: a wet, easily
# reached target favours cheap propellant, a dry or distant one favours high
# Isp, so it belongs in the per-asteroid architecture search, not in a
# constant.  Module 3 now states the feed ratio and the feed MATERIAL on each
# propellant row (`isru_feed_kg_per_kg`, `isru_feed_material`), and this
# function reads them.
#
# Two feed materials exist:
#   "water"     the ratio is water per kg of propellant, so the REGOLITH to dig
#               is that divided by the body's ice fraction and the recovery.
#   "regolith"  the propellant IS bulk rock (a mass driver's reaction mass), so
#               the ratio is already regolith per kg and no water is required.
#
# Methalox is still deliberately excluded even though C-types carry both carbon
# and water.  It needs a Sabatier loop and a carbon-reduction step that no
# study has costed for asteroid regolith, and asserting a yield for it would be
# inventing a number rather than deriving one.
_HYDROLOX_OF_RATIO         = 6.0
WATER_KG_PER_KG_HYDROLOX   = 9.0 / (1.0 + _HYDROLOX_OF_RATIO)
_ISRU_PROPELLANTS          = ("hydrolox",)


_ISRU_CONSTS_KEY = "_isru_consts"


def _isru_propellant_consts(propellant: Row) -> Optional[Tuple[str, float]]:
    """`(feed material, kg of feed per kg of propellant)` for one propellant.

    None means this propellant can never be made from asteroid material at all,
    whatever the body is, a fact about the ROW, not about the target.

    v1.17.5.  This is the half of `isru_feed_kg_per_kg_propellant` that reads
    only the propellant, and it is the expensive half: on a full propellant
    table roughly four rows in five fall through to the legacy name test, which
    is a `str().strip().lower()` plus a substring scan, to conclude "no", and
    it concluded it once per (asteroid × propellant × Δv option) rather than
    once per run.  Measured at 48,600 of 62,018 calls taking that path on a
    150-row sample.

    Same route as `_prefilter_propellant_consts` and `_sizing_propellant_consts`:
    derived in `candidate_combos`, stashed on the row so it crosses the worker
    boundary, and re-derived on demand for a caller that hand-builds `combos`.
    """
    ratio    = propellant.get("isru_feed_kg_per_kg")
    material = propellant.get("isru_feed_material")

    if ratio is None or (isinstance(ratio, float) and pd.isna(ratio)):
        # Pre-v1.9.0 propellant row with no ISRU columns.  Fall back to the
        # hydrolox name test so an old catalog still behaves as it did.
        name = str(propellant.get("name", "")).strip().lower()
        if not any(tag in name for tag in _ISRU_PROPELLANTS):
            return None
        ratio, material = WATER_KG_PER_KG_HYDROLOX, "water"

    ratio = float(ratio)
    if ratio <= 0:
        return None
    if material not in ("regolith", "water"):
        return None
    return material, ratio


def isru_feed_kg_per_kg_propellant(
    asteroid_row: Row, propellant: Row, config: CalcConfig,
) -> Optional[float]:
    """kg of regolith to dig per kg of ISRU return propellant, or None.

    None means this mission cannot make its own propellant; either the
    propellant is not manufacturable from asteroid material, or this body has
    no water to make it from.  That is a per-(asteroid × propellant) fact, which
    is why it is answered here rather than by a config flag.

    v1.17.5 splits the per-propellant half into `_isru_propellant_consts`; what
    is left is the per-BODY half.  Same arithmetic, same order, same floats.
    """
    consts = propellant.get(_ISRU_CONSTS_KEY, _UNSET)
    if consts is _UNSET:
        # Absent means "not attached", which is NOT the same as "cannot make
        # propellant"; that is a legitimate None.  Hence the sentinel: reading
        # a plain None as an un-attached key would re-derive it on every call
        # for exactly the rows where the answer is no, i.e. most of them.
        consts = _isru_propellant_consts(propellant)
        propellant[_ISRU_CONSTS_KEY] = consts
    if consts is None:
        return None
    material, ratio = consts

    if material == "regolith":
        # Reaction mass is the body itself; no volatiles needed and no
        # separation loss, because nothing is being separated.
        return ratio

    ice_frac = asteroid_row.get("comp_ice_fraction")
    if ice_frac is None or pd.isna(ice_frac) or float(ice_frac) <= 0.0:
        return None

    recovery = max(1e-6, min(1.0, config.beneficiation_recovery))
    return ratio / (float(ice_frac) * recovery)


def mining_duration_yr(payload_kg: float, config: CalcConfig) -> float:
    """Time at the asteroid needed to extract `payload_kg` (years).

    v1.4.0.  Throughput scales with the rig mass actually delivered, so a
    bigger haul costs proportionally more mission-years, which then flows
    into ops cost and WACC compounding.  Floored by station_keeping_floor_yr
    (approach and proximity ops happen regardless).
    """
    rate_kg_per_day = (config.mining_hardware_kg
                       * config.mining_rate_kg_per_day_per_kg_rig)
    if rate_kg_per_day <= 0:
        return config.station_keeping_floor_yr
    dig_yr = float(payload_kg) / (rate_kg_per_day * 365.25)
    return max(config.station_keeping_floor_yr, dig_yr)


def max_payload_by_throughput_kg(config: CalcConfig) -> float:
    """Most material the rig can extract inside max_mining_duration_yr."""
    return (config.mining_hardware_kg
            * config.mining_rate_kg_per_day_per_kg_rig
            * 365.25
            * config.max_mining_duration_yr)


def asteroid_mission_duration_yr(
    dv_out_m_s: float,
    dv_ret_m_s: float,
    config: CalcConfig,
    mining_yr: Optional[float] = None,
) -> float:
    """Estimate full round-trip mission duration (years).

    Cruise legs are calibrated against Module 3's DELTA_V_REFERENCE durations:
        4,500 m/s outbound  →  1.0 yr  one-way
        6,500 m/s           →  1.5 yr
        8,500 m/s           →  2.0 yr
       10,500 m/s           →  3.5 yr
    Approximately linear at ~0.00023 yr per m/s.

    v1.4.0: the middle term is the actual mining duration rather than a flat
    0.5 yr, so returning more material genuinely costs more mission-years.
    Passing mining_yr=None restores the old fixed station-keeping term.
    Bounded below by 1.0 yr (a real mission can't be shorter).
    """
    outbound_yr = max(0.5, 0.000_23 * dv_out_m_s)
    return_yr   = max(0.5, 0.000_23 * dv_ret_m_s)
    stay_yr     = 0.5 if mining_yr is None else float(mining_yr)
    return max(1.0, outbound_yr + stay_yr + return_yr)


# ─────────────────────────────────────────────────────────────────────────────
# CANDIDATE PRE-FILTER  (v1.14.1)
# ─────────────────────────────────────────────────────────────────────────────
# The search was spending ~90% of itself proving missions infeasible, and paying
# the full ~20 us prologue of `_evaluate_combo_at_ratio`: eclipse geometry,
# synodic period, ISRU chemistry, tankage, electric-stage sizing, to reach a
# solver that then rejected the candidate on a dozen flops it could have done
# first.  This does those flops first.
#
# It is EXACT, and the reason is worth stating precisely, because a pruner that
# is merely usually right would be the worst thing that could be added to this
# module.  The sizing loop in `_evaluate_combo_at_ratio` enters its first
# iteration with:
#
#     hardware_kg      = config.mining_hardware_kg   (plant and EP stage are 0)
#     structure_frac   = config.return_structure_frac_of_payload  (no containment)
#     stay_est_yr      = station_keeping_floor_yr + window_wait_yr  (the minimum)
#
# and every subsequent pass can only ADD hardware and LENGTHEN the hold.  More
# hardware shrinks the launch bracket; a longer hold raises the boil-off factor,
# which raises R_ret, which shrinks it again.  So pass 1 is the most optimistic
# cascade the loop will ever evaluate, and `if not cascade["viable"]: return
# None` on pass 1 is a decision no later pass can overturn.
#
# Two further properties are what make it worth hoisting rather than merely
# reordering.  Pass 1 cannot see `power_mode`, because the plant it would size
# does not exist yet; and it cannot see the concentration ratio, because no feed
# has been dug yet.  So the identical refutation was being recomputed once per
# power source and once per point of the concentration sweep, up to eighteen
# times for one dead candidate.
#
# ⚠️  This function and `max_return_payload_kg` are two statements of the same
# algebra, which is exactly the duplication CLAUDE.md warns about ("two copies
# of this algebra drifting apart is how a mass ends up in one cascade and not
# the other").  They are kept adjacent for that reason, and the defence is
# `prune_infeasible_combos = False` plus a column-by-column diff, if the two
# ever disagree, the pruned build drops rows the unpruned one keeps and the
# diff says so immediately.  Change one, re-run that diff.
# Distinguishes "this derived value is not attached yet" from a derived value
# that is legitimately None.  `.get(key)` cannot tell those apart, and reading
# one as the other is how a cache silently stops caching.
_UNSET = object()

_PREFILTER_CONSTS_KEY = "_prefilter_consts"

# Cache-miss sentinel for the search's `_combo_close_terms` memo (v1.14.2).
# `None` is a legitimate CACHED value there; it means "no vehicle in the table
# could close this candidate", so a plain `.get(key)` returning None cannot
# distinguish a miss from a stored refusal, and would recompute every refusal on
# every vehicle, i.e. exactly the work the memo exists to remove.
_UNCACHED = object()

# ─────────────────────────────────────────────────────────────────────────────
# PER-ROW CONSTANTS FOR THE SIZING PATH  (v1.14.2)
# ─────────────────────────────────────────────────────────────────────────────
# The same finding as `_PREFILTER_CONSTS_KEY` one level further in: six
# quantities that `_evaluate_combo_at_ratio` derived on entry are functions of
# (propellant row × config) alone, and one is a function of the vehicle row
# alone.  They were re-parsed out of the row for every SURVIVING candidate: 
# 218,000 times per 150 beneficiated asteroids, and each parse goes through
# `pd.isna`, which is ~700 ns because it is a pandas dispatch on a Python
# scalar.  That alone was ~980,000 `pd.isna` calls per 150 rows.
#
# Attached to the row dict rather than memoised on `id()`, for the same reason
# the pre-filter constants are: the dict is what crosses the multiprocessing
# boundary, so a worker gets the derived values with the row instead of
# rebuilding them, and there is no identity to be recycled.
#
# `tank_frac` is deliberately derived HERE and read by both consumers.  It was
# computed twice from the same two columns, once in
# `_prefilter_propellant_consts`, once in `_evaluate_combo_at_ratio`, which is
# the drift hazard this file keeps naming.  One derivation now, two readers.
_SIZING_CONSTS_KEY  = "_sizing_consts"
_VEHICLE_CONSTS_KEY = "_vehicle_consts"


def _tank_frac_per_kg(propellant: Row, config: CalcConfig) -> float:
    """Tank mass per kg of propellant, or 0.0 where the row cannot state one.

    Module 3 quotes tankage per LITRE because that is what it scales with, a
    tank encloses volume, not mass, so this is the one place the two columns
    are divided.  A row predating Module 3 v1.9.0 has neither column and comes
    through as 0.0, which is exactly `model_tank_mass = False`.
    """
    if not config.model_tank_mass:
        return 0.0
    tank_per_L = propellant.get("tank_kg_per_L")
    rho        = propellant.get("density_kg_per_L")
    if (tank_per_L is not None and rho is not None
            and not pd.isna(tank_per_L) and not pd.isna(rho)
            and float(rho) > 0):
        return max(0.0, float(tank_per_L) / float(rho))
    return 0.0


def _sizing_propellant_consts(
    propellant: Row,
    config:     CalcConfig,
) -> Tuple[float, Optional[float], Optional[float], float, float, float]:
    """(dv_penalty, thruster_eff, thruster_kg_per_n, tank_frac, isp, boiloff).

    `thruster_eff` and `thruster_kg_per_n` are None where the row does not state
    a usable figure, which is what makes the caller fall back to Module 3's
    shared constants exactly as it did before, the two-part test they replace
    ("not null AND in range") collapses to one identity check, and a
    pre-Module-3-v1.10.0 catalog still reproduces v1.11.0.
    """
    eff = propellant.get("thruster_efficiency")
    eff = (float(eff) if eff is not None and not pd.isna(eff) and float(eff) > 0
           else None)

    kgn = propellant.get("thruster_kg_per_n")
    kgn = (float(kgn) if kgn is not None and not pd.isna(kgn) and float(kgn) >= 0
           else None)

    return (
        float(propellant.get("dv_penalty_factor", 1.0) or 1.0),
        eff,
        kgn,
        _tank_frac_per_kg(propellant, config),
        float(propellant["isp_vac_s"]),
        float(propellant.get("boiloff_pct_per_day", 0.0) or 0.0),
    )


def _vehicle_consts(vehicle: Row) -> Tuple[float, float, bool]:
    """`(usable fairing m³, LEO capacity kg, capacity is usable)` for one vehicle.

    v1.17.6 adds the second and third.  `float(vehicle.get("payload_leo_kg", 0)
    or 0)` was written out in THREE places: the search's combo loop, the
    pre-filter probe, and `_evaluate_combo_at_ratio`, and the first of those
    ran it once per (vehicle × propellant) for every asteroid in the catalog:
    142,800 derivations per 400 rows, of seventeen numbers that are fixed for
    the whole run.  Same shape as the fairing volume beside it, and the same
    fix: derived once in `candidate_combos`, stashed on the row so it crosses
    the worker boundary.

    ⚠️  `math.isfinite(cap) and cap > 0` is folded in as the third field rather
    than left to each caller.  Two of the three tested it and one tested only
    `> 0`; both survive, because the two are the same test on a value that
    `float(... or 0)` has already made a real number, but stating it once is
    what stops them drifting apart.
    """
    fairing_m3 = vehicle.get("fairing_volume_m3")
    fairing = (float(fairing_m3)
               if fairing_m3 is not None and not pd.isna(fairing_m3) else 100.0)
    leo_cap = float(vehicle.get("payload_leo_kg", 0) or 0)
    return fairing, leo_cap, (math.isfinite(leo_cap) and leo_cap > 0)


def _prefilter_propellant_consts(
    propellant: Row,
    config:     CalcConfig,
) -> Optional[Tuple[float, float, float, float]]:
    """(isp, dv_penalty, tank_frac, boiloff_pct) for one propellant, or None.

    These depend only on the propellant row and the config, so they are derived
    once per run in `candidate_combos` rather than per (asteroid × candidate).
    None means the row cannot fly at all, no usable Isp, which is the same
    thing `max_return_payload_kg` reports on `isp_s <= 0`.
    """
    try:
        isp = float(propellant["isp_vac_s"])
    except (KeyError, TypeError, ValueError):
        return None
    if not np.isfinite(isp) or isp <= 0:
        return None

    dv_penalty = float(propellant.get("dv_penalty_factor", 1.0) or 1.0)
    tank_frac  = _tank_frac_per_kg(propellant, config)

    boiloff_pct = float(propellant.get("boiloff_pct_per_day", 0.0) or 0.0)
    return isp, dv_penalty, tank_frac, boiloff_pct


def _combo_close_terms(
    consts:          Tuple[float, float, float, float],
    dv_out_m_s:      float,
    dv_ret_m_s:      float,
    tps_frac:        float,
    isru:            bool,
    window_wait_yr:  float,
    config:          CalcConfig,
) -> Optional[Tuple[bool, float, float, float]]:
    """The vehicle-independent half of the pre-filter, or None if nothing closes.

    v1.14.2.  The launch capacity enters this test in exactly one place, the
    final comparison, and it enters MONOTONICALLY: a bigger rocket can never
    turn a candidate that closes into one that does not.  Everything else is a
    function of (propellant × Δv × ISRU).

    That matters because the combo grid is vehicle-major, so the question was
    asked once per vehicle: seventeen evaluations per propellant row per
    asteroid, computing the same two exponentials, the same boil-off inflation
    and the same tankage closure, and differing only in the last line.

    ⚠️  This returns the COEFFICIENTS of that last line rather than the launch
    capacity it implies, and the difference is not stylistic.  `bracket > 0`
    rearranges algebraically to `leo > (hw + k·s·d0·R_ret)·k_out·R_out`, but not
    in floating point, the rearrangement re-associates the arithmetic and moves
    the boundary in the last bit, which for a candidate sitting on it changes
    whether the row survives the prune.  Keeping the same operations in the same
    order on the same values makes the hoist exactly transparent, and the
    per-vehicle remainder (one divide, two subtractions) is not what cost.

    `denom` is vehicle-independent too, so a candidate that fails it returns None
    here rather than being re-refuted per vehicle.
    """
    isp, dv_penalty, t, boiloff_pct = consts
    dv_out = dv_out_m_s * dv_penalty
    dv_ret = dv_ret_m_s * dv_penalty
    if not (math.isfinite(dv_out) and math.isfinite(dv_ret)):
        return None
    if dv_out < 0 or dv_ret < 0:
        return None

    ve = isp * G0_M_S2
    try:
        r_out = math.exp(dv_out / ve)
        r_ret = math.exp(dv_ret / ve)
    except OverflowError:
        return False        # Δv/Isp so extreme the mass ratio overflows

    # Boil-off, at the SHORTEST hold the loop can settle on.  The loop folds it
    # into an effective return Δv and then re-exponentiates; doing both here
    # would be a log/exp round trip to recover the number we already have, so
    # inflate R_ret directly; `r_ret_eff = 1 + (r_ret - 1) · factor` is the
    # substitution the loop makes.  ISRU is exempt: the propellant is made at
    # the asteroid on departure rather than held from launch.
    if config.model_propellant_boiloff and boiloff_pct > 0 and not isru:
        outbound_yr = max(0.5, 0.000_23 * dv_out)
        hold_yr     = outbound_yr + config.station_keeping_floor_yr + window_wait_yr
        r_ret = 1.0 + (r_ret - 1.0) * math.exp(
            boiloff_pct / 100.0 * hold_yr * 365.25)

    if not (math.isfinite(r_out) and math.isfinite(r_ret)):
        return None

    # Tankage closure; t·(R − 1) ≥ 1 means the tank outweighs the propellant's
    # own contribution.  Infeasible, not expensive.
    if t * (r_ret - 1.0) >= 1.0 or t * (r_out - 1.0) >= 1.0:
        return None
    k     = 1.0 / (1.0 - t * (r_ret - 1.0))
    k_out = 1.0 / (1.0 - t * (r_out - 1.0))

    s  = 1.0 + tps_frac
    f  = max(0.0, float(config.return_structure_frac_of_payload))
    d0 = float(config.return_vehicle_dry_kg)
    hw = float(config.mining_hardware_kg)          # the floor: no plant, no EP

    if isru:
        # Return propellant is made on site, but the heat shield, the
        # payload-scaling structure and the empty return tank still launch.
        # Test: base_launch <= leo_capacity_kg.
        return (True, (hw + k * s * d0) * k_out * r_out, 0.0, 0.0)

    denom = k * s * r_ret * (1.0 + f) - 1.0
    if denom <= 0:
        return None
    # Test: leo_capacity_kg / a - b - c > 0, written in exactly that order.
    return (False, k_out * r_out, hw, k * s * d0 * r_ret)


def _closes_with(
    leo_capacity_kg: float,
    terms:           Tuple[bool, float, float, float],
) -> bool:
    """Apply `_combo_close_terms`' coefficients to one vehicle's LEO capacity."""
    isru_form, a, b, c = terms
    if isru_form:
        return a <= leo_capacity_kg
    return leo_capacity_kg / a - b - c > 0


def _ep_device_consts(
    is_electric:           bool,
    thruster_eff_row:      Optional[float],
    thruster_kg_per_n_row: Optional[float],
    ep_eff:                float,
    ep_kg_per_kw:          float,
    ppu_only_kg_per_kw:    float,
) -> Tuple[float, float, float]:
    """`(efficiency, thruster kg/N, PPU kg/kW)` for one propellant's device.

    v1.17.4.  Split out of `_evaluate_combo_at_ratio` so the pre-filter's
    second stage sizes the electric stage off the SAME resolution rather than a
    second copy of it, the hazard this file names under `tank_frac`, which
    spent three releases derived in two places beneath a note claiming it was
    derived in one.

    Both Module 3 figures fall back to the older shared constants when the row
    states no usable value, so a pre-Module-3-v1.10.0 catalog reproduces
    v1.11.0.  `schema_check()` names them, because the fallback is silent and
    flattering.
    """
    eff_used          = ep_eff
    thruster_kg_per_n = 0.0
    ppu_kg_per_kw     = ep_kg_per_kw
    if is_electric:
        if thruster_eff_row is not None:
            eff_used = thruster_eff_row
        if thruster_kg_per_n_row is not None:
            thruster_kg_per_n = thruster_kg_per_n_row
            ppu_kg_per_kw     = ppu_only_kg_per_kw   # thruster counted separately
    return eff_used, thruster_kg_per_n, ppu_kg_per_kw


def _ep_stage_kg(
    cascade:           Dict[str, float],
    isp_s:             float,
    eff:               float,
    ep_w_per_kg:       float,
    ppu_kg_per_kw:     float,
    thruster_kg_per_n: float,
    config:            CalcConfig,
) -> Tuple[float, float, float, float]:
    """Mass of the electric stage that flies `cascade`'s propellant load.

    Returns `(ep_system_kg, ep_power_w, ep_thrust_n, ep_thrust_yr)`.

    Three masses on three different quantities, and keeping them apart is the
    whole point of v1.12.0:
        array      scales with POWER, and 1/r² with distance
        PPU        scales with POWER, flat with distance
        thruster   scales with THRUST; this is the device constraint, and it
                   is what a per-kW figure cannot express.

    v1.17.4 made this a function rather than a block inside the sizing loop,
    because the pre-filter's second stage needs the same number off the same
    pass-1 cascade.  Same operations in the same order on the same values, so
    the extraction is bit-identical rather than merely equal.
    """
    m_prop_total = (float(cascade.get("m_outbound_prop", 0.0))
                    + float(cascade.get("m_return_prop", 0.0)))
    ep_power_w = ep_power_required_w(
        m_prop_total, isp_s, config.ep_target_thrust_yr, eff,
    )
    ep_thrust_n = ep_thrust_required_n(
        m_prop_total, isp_s, config.ep_target_thrust_yr,
    )
    ep_thrust_yr = config.ep_target_thrust_yr if m_prop_total > 0 else 0.0
    array_kg    = ep_power_w / ep_w_per_kg if ep_w_per_kg > 0 else 0.0
    ppu_kg      = ep_power_w / 1000.0 * ppu_kg_per_kw
    thruster_kg = ep_thrust_n * thruster_kg_per_n
    return array_kg + ppu_kg + thruster_kg, ep_power_w, ep_thrust_n, ep_thrust_yr


def _closes_carrying_its_own_stage(
    leo_capacity_kg: float,
    sizing_consts:   Tuple[float, Optional[float], Optional[float],
                           float, float, float],
    ops:             Tuple[float, ...],
    solar_w_per_kg:  float,
    structure_frac:  float,
    window_wait_yr:  float,
    dv_out_m_s:      float,
    dv_ret_m_s:      float,
    tps_frac:        float,
    isru:            bool,
    config:          CalcConfig,
) -> bool:
    """Pre-filter, second stage: can it still close once it carries its THRUSTER?

    ── What this is for ────────────────────────────────────────────────────

    v1.14.1's pre-filter refutes a candidate at PASS 1 of the sizing loop, 
    zero plant, zero electric stage, shortest hold, and its whole argument is
    that pass 1 is the most optimistic pass, so failing it is a decision no
    later pass can overturn.  That is true, and it leaves the obvious next
    question unasked.  Measured at cislunar, beneficiated, programme search on:

        219,054 calls to `_evaluate_combo_at_ratio`
        162,816 of them (74.3%) return None on `if not cascade["viable"]`
                after exactly TWO cascade solves, that is, on PASS 2

    Pass 2 is the first pass that flies the electric stage pass 1 has just
    sized, and on an electric mission that stage is tonnes.  So three quarters
    of the surviving search was paying a ~20 µs prologue and two closed-form
    solves, once per concentration ratio, and again per power source, to
    re-derive one refutation that depends on neither.

    ── Why refusing here is sound, and not a heuristic ─────────────────────

    Viability in `max_return_payload_kg` is `bracket > 0` (no-ISRU) or
    `base_launch <= leo` (ISRU), and BOTH are monotone decreasing in the two
    quantities that grow between pass 1 and pass 2:

      • `hardware_kg`.  Pass 2 flies `rig + plant + ep`, and the plant is >= 0
        by construction, so `rig + ep` is a lower bound on it, and the ep term
        is the SAME at every concentration ratio and every power source,
        because it is sized off pass 1's cascade, which is itself ratio- and
        power-blind.  (The plant is not; that is exactly why it is dropped.)

      • `r_ret`, through boil-off.  Pass 2 holds for `trial_dur + wait`, and
        `trial_dur` is `max(mining_duration_yr(...), station_keeping_floor_yr)`,
        so the hold cannot fall below the floor pass 1 used.  A longer hold
        inflates `r_ret`, which shrinks `bracket`.

    `structure_frac` grows too (containment), and it appears in `denom`, not in
    `bracket`, where a LARGER value can only help viability.  So this test
    runs at pass 1's `structure_frac`; pass 1 was viable, so its `denom` is
    already positive and is identical here, and the only way this returns False
    is the monotone condition.  False therefore means pass 2 is infeasible for
    every ratio and every power source; precisely what the code it replaces
    would have concluded, one solve at a time.

    ⚠️  One-sided, exactly like the first stage.  True still promises nothing:
    the throughput cap, the duration limit, the volume cap and the post-settle
    launch recheck all apply downstream.

    ⚠️  Non-electric candidates return True without touching the solver.  With
    no electric stage `ep` is 0, so this test IS the first stage, which the
    caller has already applied.
    """
    (dv_penalty, thruster_eff_row, thruster_kg_per_n_row,
     tank_frac, isp_s_val, boiloff_pct) = sizing_consts

    if not (config.model_low_thrust_time and dv_penalty > 1.0):
        return True                    # no stage to carry; stage 1 said it all

    (_dig_wh, _benef_wh, _base_w, ep_eff, ep_kg_per_kw,
     _rtg_w, ppu_only_kg_per_kw,
     _df, _swh, _seta, _bdh, _containment) = ops

    eff_used, thruster_kg_per_n, ppu_kg_per_kw = _ep_device_consts(
        True, thruster_eff_row, thruster_kg_per_n_row,
        ep_eff, ep_kg_per_kw, ppu_only_kg_per_kw,
    )

    # The same two lines the sizing function runs before its loop, on the same
    # values, so the solver below sees the identical floats.
    dv_out = dv_out_m_s * dv_penalty
    dv_ret = dv_ret_m_s * dv_penalty

    # And the same boil-off substitution pass 1 makes, at the same shortest
    # hold.  Written in Δv space rather than `_combo_close_terms`' R space
    # because the value has to reach `max_return_payload_kg` bit-for-bit as the
    # loop would have handed it over.
    dv_ret_eff = dv_ret
    if config.model_propellant_boiloff and boiloff_pct > 0 and not isru:
        outbound_yr = max(0.5, 0.000_23 * dv_out)
        stay_est_yr = config.station_keeping_floor_yr + window_wait_yr
        try:
            boiloff_factor = math.exp(
                boiloff_pct / 100.0 * (outbound_yr + stay_est_yr) * 365.25)
            r_ret_raw = math.exp(dv_ret / (isp_s_val * G0_M_S2))
        except OverflowError:
            return True                # let the solver make its own refusal
        r_ret_eff = 1.0 + (r_ret_raw - 1.0) * boiloff_factor
        if not (math.isfinite(r_ret_eff) and r_ret_eff > 0.0):
            return True
        dv_ret_eff = isp_s_val * G0_M_S2 * math.log(r_ret_eff)

    # ⚠️  v1.17.6: written out twice rather than built as a dict and splatted
    # into both calls.  Same arguments in the same order, `**` on a 9-key dict
    # measures 558 ns a call against 146 ns for the keywords, plus 306 ns to
    # build the dict, so the splat was ~1.1 us of a ~16 us function that runs
    # once per surviving (vehicle × propellant × Δv × ISRU).
    dry_return_kg = config.return_vehicle_dry_kg
    pass1 = max_return_payload_kg(
        leo_capacity_kg = leo_capacity_kg,
        isp_s           = isp_s_val,
        dv_out_m_s      = dv_out,
        dv_ret_m_s      = dv_ret_eff,
        hardware_kg     = config.mining_hardware_kg,
        dry_return_kg   = dry_return_kg,
        tps_frac        = tps_frac,
        isru_return     = isru,
        structure_frac  = structure_frac,
        tank_frac       = tank_frac,
    )
    if not pass1["viable"]:
        return False                   # stage 1 already knew this; agree with it

    ep_kg, _pw, _tn, _ty = _ep_stage_kg(
        pass1, isp_s_val, eff_used, solar_w_per_kg,
        ppu_kg_per_kw, thruster_kg_per_n, config,
    )
    if ep_kg <= 0.0:
        return True

    return bool(max_return_payload_kg(
        leo_capacity_kg = leo_capacity_kg,
        isp_s           = isp_s_val,
        dv_out_m_s      = dv_out,
        dv_ret_m_s      = dv_ret_eff,
        hardware_kg     = config.mining_hardware_kg + ep_kg,
        dry_return_kg   = dry_return_kg,
        tps_frac        = tps_frac,
        isru_return     = isru,
        structure_frac  = structure_frac,
        tank_frac       = tank_frac,
    )["viable"])


def _combo_can_close(
    leo_capacity_kg: float,
    consts:          Tuple[float, float, float, float],
    dv_out_m_s:      float,
    dv_ret_m_s:      float,
    tps_frac:        float,
    isru:            bool,
    window_wait_yr:  float,
    config:          CalcConfig,
) -> bool:
    """Could this candidate close its mass budget under ANY downstream choice?

    True means "solve it properly"; False means no power source and no
    concentration ratio can rescue it, because the cascade is already infeasible
    at zero plant mass and the shortest hold.  False is therefore a decision,
    not a guess; see the section header above for why pass 1 dominates.

    Deliberately one-sided.  True does not promise a viable mission: the
    throughput cap, the duration limit, the volume cap and the post-settle
    launch recheck all still apply downstream, and about a quarter of the
    survivors die on one of them.

    ⚠️  v1.17.4: that list named the wrong losses.  All four fire, but 74.3% of
    what survived this test died on the PASS-2 cascade, which is not among
    them; see `_closes_carrying_its_own_stage`, which is now the second stage
    and catches exactly that.  Cheap and sound beats tight and clever here.

    v1.14.2 split the work in two, `_combo_close_terms` for the part that does
    not depend on the vehicle, `_closes_with` for the part that does, because
    the search asks this once per vehicle over a vehicle-major grid.  This
    remains the whole test in one call, for callers outside that loop and as the
    single readable statement of what the pre-filter is.
    """
    if not (math.isfinite(leo_capacity_kg) and leo_capacity_kg > 0):
        return False
    terms = _combo_close_terms(
        consts, dv_out_m_s, dv_ret_m_s, tps_frac, isru, window_wait_yr, config)
    return terms is not None and _closes_with(leo_capacity_kg, terms)


# ─────────────────────────────────────────────────────────────────────────────
# ROCKET-EQUATION RETURN-MISSION SOLVER
# ─────────────────────────────────────────────────────────────────────────────
def _infeasible(r_out: float = 0.0, r_ret: float = 0.0) -> Dict[str, float]:
    """The refusal cascade `max_return_payload_kg` returns on every dead end.

    ⚠️  v1.17.6: module level, not a nested def.  It was defined on every call
    of the solver, 500,860 of them on a 150-row beneficiated+searched sample, 
    at ~99 ns a def, which is ~5% of a 2.1 us function that is the single
    hottest thing in the mass cascade.  A fresh dict per call, exactly as
    before; only the function object stops being rebuilt.
    """
    return {"max_payload_kg": 0.0, "viable": False,
            "r_out": r_out, "r_ret": r_ret,
            "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
            "m_at_asteroid": 0, "m_tps": 0, "m_dry_return": 0,
            "m_tank_return": 0, "m_tank_outbound": 0}


def max_return_payload_kg(
    leo_capacity_kg: float,
    isp_s:           float,
    dv_out_m_s:      float,
    dv_ret_m_s:      float,
    hardware_kg:     float,
    dry_return_kg:   float,
    tps_frac:        float = 0.0,
    isru_return:     bool  = False,
    structure_frac:  float = 0.0,
    tank_frac:       float = 0.0,
) -> Dict[str, float]:
    """Closed-form max returned-payload solver for a return-sample mission.

    Three masses scale with something the solver is trying to find, and all
    three are fully accounted for:

      • HEAT SHIELD, tps_frac × (m_payload + m_dry_return), hauled outbound
        from Earth AND pushed back through the return burn, even though it
        ablates on entry.  Let s = 1 + tps_frac.
      • RETURN-VEHICLE STRUCTURE, structure_frac × m_payload (v1.10.0), the
        primary structure and cargo restraint that a bigger haul needs.
        Let f = structure_frac, so the dry vehicle is d0 + f·m_payload.
      • PROPELLANT TANKAGE, tank_frac × m_propellant (v1.11.0), and this one
        is circular in a way the other two are not, because the tank is sized
        by the propellant and is itself mass the propellant has to push.
        Let t = tank_frac.

    On tankage.  Module 3 derives t per propellant from storage class and
    density (tank_kg_per_L / density_kg_per_L), and it is not a rounding term:
    2.5% for kerolox, 9.7% for hydrolox, 46% for cold gas, 53% for the bare
    hydrogen a nuclear-thermal stage burns.  Leaving it out was a straight
    subsidy to whichever propellant had the lowest density, which is the same
    propellant that has the highest Isp, so the error compounded rather than
    cancelling.

    The two tanks are treated differently, because they are used differently:
      • the RETURN tank flies home with the cargo, so it is dry mass at arrival
        and rides inside m_after_return;
      • the OUTBOUND tank is staged at the asteroid, so it is pushed through
        the outbound burn and then dropped.

    Working backward from arrival:
        m_dry           = d0 + f · m_payload
        m_tps           = tps_frac · (m_payload + m_dry)
        m_tank_ret      = t · m_return_prop
        m_after_return  = s · (m_payload + m_dry) + m_tank_ret
        m_return_prop   = (R_ret − 1) × m_after_return     (zero if ISRU on)

    Substituting m_tank_ret and solving the loop gives a single scalar:

        m_after_return = k · s · (m_payload·(1+f) + d0),
            where k = 1 / (1 − t·(R_ret − 1))

    and k > 1 is precisely the cost of carrying your own tank home.  k → ∞ as
    t·(R_ret − 1) → 1: the tank cannot close, no payload makes it, and the
    combination is infeasible rather than merely expensive.  The same algebra
    on the outbound leg gives k_out = 1/(1 − t·(R_out − 1)).

    So the NO-ISRU closed form generalises to

        m_payload_max =
            (M_LEO/(k_out·R_out) − m_hardware − k·s·d0·R_ret)
            / (k·s·R_ret·(1 + f) − 1)

    and the ISRU form (return propellant made on site, but its TANK still
    launched from Earth) to

        m_payload_max =
            (M_LEO/(k_out·R_out) − m_hardware − k·s·d0) / (k·s·(1 + f) − 1)

    Both reduce to the v1.10.0 expressions exactly at t = 0, where k = k_out =
    1 and k·s·(1+f) − 1 is g.  Side effect worth knowing: with t > 0 the ISRU
    denominator is positive even when g would be zero, which closes the last
    route to an unbounded reported payload.

    Returns a dict with the full mass cascade.  All masses in kg.
    """
    # ── Scalar arithmetic uses `math`, not numpy (v1.14.2) ───────────────────
    # Every argument here is a Python float, and numpy's ufunc dispatch costs
    # ~700 ns on a scalar against ~30-50 ns for the `math` equivalent.  This
    # function is called ~2.2 times per surviving candidate: 387,000 times per
    # 150 beneficiated asteroids, so seven ufunc dispatches were about half its
    # runtime and roughly a quarter of the whole search.
    #
    # `math.exp` and `np.exp` were checked bitwise over 400,000 samples across
    # the (Δv, Isp) range this model spans: zero mismatches.  They differ only
    # in how they OVERFLOW, numpy returns inf and warns, `math` raises, which
    # is why the guard below becomes a try/except rather than an isfinite test.
    # That is the form `_combo_can_close` has always used, so the two statements
    # of this algebra now also agree on their error handling.
    if not math.isfinite(isp_s) or isp_s <= 0:
        return _infeasible()
    if not (math.isfinite(dv_out_m_s) and math.isfinite(dv_ret_m_s)):
        return _infeasible()
    if dv_out_m_s < 0 or dv_ret_m_s < 0:
        return _infeasible()
    if not math.isfinite(leo_capacity_kg) or leo_capacity_kg <= 0:
        return _infeasible()

    try:
        r_out = math.exp(dv_out_m_s / (isp_s * G0_M_S2))
        r_ret = math.exp(dv_ret_m_s / (isp_s * G0_M_S2))
    except OverflowError:
        return _infeasible()      # Δv/Isp so extreme the mass ratio overflows
    s     = 1.0 + tps_frac
    f     = max(0.0, float(structure_frac))
    t     = max(0.0, float(tank_frac))
    # Combined payload-proportional overhead: heat shield plus the structure
    # that scales with the haul.  g = tps_frac exactly when f = 0.
    g     = s * (1.0 + f) - 1.0

    # Tankage closure.  t·(R − 1) ≥ 1 means the tank needed to hold the
    # propellant for this burn outweighs the propellant's own contribution; 
    # the same "the tank cannot close" condition Module 2 hits on δ·R ≥ 1.
    # Infeasible, not expensive.
    if t * (r_ret - 1.0) >= 1.0 or t * (r_out - 1.0) >= 1.0:
        return _infeasible(r_out, r_ret)
    k     = 1.0 / (1.0 - t * (r_ret - 1.0))
    k_out = 1.0 / (1.0 - t * (r_out - 1.0))
    # Launch capacity available to everything except the outbound tank and the
    # outbound propellant.
    launch_budget = leo_capacity_kg / (k_out * r_out)

    if isru_return:
        # ISRU mode: return propellant is manufactured ON the asteroid from
        # mined volatiles, NOT carried up from Earth.  The heat shield, the
        # payload-scaling structure AND the empty return TANK are still
        # launched from Earth; you can make propellant out there, not a
        # pressure vessel, so the launch constraint becomes:
        #
        #   M_LEO ≥ (m_hardware + k·s·(m_payload·(1+f) + d0) − m_payload)
        #           × k_out × R_out
        #
        # ⇒ m_payload_max = (M_LEO/(k_out·R_out) − m_hardware − k·s·d0)
        #                   / (k·s·(1 + f) − 1)
        #
        # v1.10.0 closed the unbounded-payload hole by making g > 0 whenever
        # there is a heat shield or structure scaling; v1.11.0's tank term
        # closes it for good, since k·s·(1+f) − 1 > 0 for any t > 0 even with
        # both of those set to zero.
        denom_isru  = k * s * (1.0 + f) - 1.0
        base_launch = (hardware_kg + k * s * dry_return_kg) * k_out * r_out
        if base_launch > leo_capacity_kg:
            return _infeasible(r_out, r_ret)
        if denom_isru > 0:
            m_payload_launch_max = (
                launch_budget - hardware_kg - k * s * dry_return_kg
            ) / denom_isru
            m_payload_max = max(0.0, m_payload_launch_max)
        else:
            m_payload_max = np.inf   # mining cap binds downstream

        return {
            "max_payload_kg":  m_payload_max,
            "viable":          True,
            "r_out":           r_out,
            "r_ret":           r_ret,
            # Placeholder cascade; evaluate_combo will recompute once the
            # actual capped payload is known (TPS / return-prop / outbound-prop
            # all depend on the final m_payload).
            "m_launch":        base_launch,
            "m_outbound_prop": base_launch - (hardware_kg + k * s * dry_return_kg),
            "m_return_prop":   0.0,
            "m_at_asteroid":   hardware_kg + k * s * dry_return_kg,
            "m_tps":           tps_frac * dry_return_kg,  # baseline TPS for empty payload
            "m_tank_return":   0.0,   # recomputed downstream with the real payload
            "m_tank_outbound": 0.0,
            "k_ret":           k,
            "k_out":           k_out,
        }

    # ── NO-ISRU: return prop is hauled outbound as dead mass ─────────────────
    # m_dry           = d0 + f · m_payload
    # m_after_return  = s · (m_payload + m_dry) = m_payload·(1 + g) + s·d0
    # m_return_prop   = (R_ret − 1) · m_after_return
    # m_at_asteroid   = m_hardware + s·d0·R_ret + m_payload · ((1 + g)·R_ret − 1)
    # M_LEO = m_at_asteroid × R_out
    # ⇒ m_payload_max = (M_LEO/R_out − m_hardware − s·d0·R_ret) / ((1 + g)·R_ret − 1)
    #
    # With f = 0 this is g = tps_frac and (1 + g) = s, i.e. the pre-v1.10.0
    # expression exactly.
    denom   = k * s * r_ret * (1.0 + f) - 1.0
    bracket = launch_budget - hardware_kg - k * s * dry_return_kg * r_ret
    if bracket <= 0 or denom <= 0:
        return _infeasible(r_out, r_ret)

    m_payload_max = bracket / denom
    if m_payload_max <= 0:
        return _infeasible(r_out, r_ret)

    m_dry_return   = dry_return_kg + f * m_payload_max
    m_tps          = tps_frac * (m_payload_max + m_dry_return)
    # m_after_return carries the return tank as well as the cargo, so it is
    # the k-inflated form rather than the bare sum.  Written out from the
    # closed-form solution rather than re-derived, so the two cannot drift.
    m_after_return = k * s * (m_payload_max * (1.0 + f) + dry_return_kg)
    m_return_prop  = m_after_return * (r_ret - 1.0)
    m_tank_return  = t * m_return_prop
    # Everything launched from Earth that reaches the asteroid: hardware, the
    # dry return vehicle, its heat shield, its tank, and the return propellant.
    # (The mined payload is loaded there, so it is not in this sum.)
    m_at_asteroid  = (hardware_kg + m_dry_return + m_tps
                      + m_tank_return + m_return_prop)
    # The outbound tank is staged at the asteroid: pushed through the outbound
    # burn, then dropped.  It scales with the outbound propellant, which scales
    # with it, hence k_out.
    m_outbound_prop = m_at_asteroid * k_out * (r_out - 1.0)
    m_tank_outbound = t * m_outbound_prop
    m_launch       = m_at_asteroid + m_tank_outbound + m_outbound_prop

    return {
        "max_payload_kg":  m_payload_max,
        "viable":          True,
        "r_out":           r_out,
        "r_ret":           r_ret,
        "m_launch":        m_launch,
        "m_outbound_prop": m_outbound_prop,
        "m_return_prop":   m_return_prop,
        "m_at_asteroid":   m_at_asteroid,
        "m_tps":           m_tps,
        "m_dry_return":    m_dry_return,
        "m_tank_return":   m_tank_return,
        "m_tank_outbound": m_tank_outbound,
        # Exported so the caller's recomputation at the CAPPED payload uses the
        # same two scalars rather than re-deriving them.  Two copies of this
        # algebra drifting apart is precisely how a mass ends up in the rocket
        # equation without a matching entry in the ledger.
        "k_ret":           k,
        "k_out":           k_out,
    }


# ─────────────────────────────────────────────────────────────────────────────
# OPERATIONAL-COSTS LOOKUP HELPER
# ─────────────────────────────────────────────────────────────────────────────
# Single-slot memo for the ops table.  mission_cost_usd pulls 9 line items per
# (vehicle × propellant) combo, so a 5,000-asteroid run at 11 vehicles × 7
# propellants issued ~2.5M full-DataFrame boolean scans of a 17-row table: 
# 89% of Module 4's total runtime.  The table is loaded once per run and never
# mutated, so one dict build serves every lookup.
#
# Keyed by object identity, and the frame itself is held in the slot so its id
# can't be recycled onto a different object.  Single-slot (not a growing dict)
# so a long-lived session swapping ops tables can't leak.  A caller that
# mutates ops_df IN PLACE rather than rebinding would read a stale cache, 
# rebuild by passing a fresh frame, which load_all_catalogs already does.
_OPS_CACHE: Tuple[Optional[pd.DataFrame], Dict[str, Optional[float]]] = (None, {})


def mining_success_probability(
    n_missions: int,
    p_first:    float,
    alpha:      float,
    p_mature:   float,
) -> float:
    """Fleet-average probability the mining chain works, over `n_missions`.

    Reliability grows with flight heritage: failure modes get found and
    designed out.  The Duane / AMSAA model has failure probability fall as a
    power law in cumulative production,

        q(n) = q_first · n^(−α),    p(n) = 1 − q(n)

    capped at `p_mature`, because growth is asymptotic; no amount of heritage
    makes a machine that grinds rock in vacuum certain to work.

    Returns the MEAN over missions 1..N, not the terminal value.  That is the
    figure the rest of the cost model needs: NRE and the rig are amortised
    across the whole programme, so the per-mission expected revenue has to be
    the programme average.  Quoting the last mission's reliability would
    credit every mission with heritage that only the last one has.

    Exactly `p_first` at N = 1, so a single-mission run is unaffected.
    """
    n = max(1, int(n_missions))
    q_first = max(0.0, 1.0 - p_first)
    q_floor = max(0.0, 1.0 - p_mature)
    total = 0.0
    for k in range(1, n + 1):
        q = q_first * (k ** -alpha) if alpha > 0 else q_first
        total += 1.0 - max(q, q_floor)
    return total / n


def learning_curve_factor(n_units: int, rate: float) -> float:
    """Cumulative-average cost multiplier for building `n_units` (Wright's law).

    The nth unit costs T1·n^b with b = log₂(rate); an 85% curve means each
    doubling of cumulative production cuts unit cost to 85%.  Standard for
    aerospace serial production and the reason nobody prices the hundredth
    article at the first article's cost.

    Summed exactly rather than integrated; the integral approximation is
    wrong by 30% at N = 1, which is precisely the case that has to come out
    at exactly 1.0 so a single-mission run is unaffected.
    """
    n = max(1, int(n_units))
    if n == 1 or rate >= 1.0 or rate <= 0.0:
        return 1.0
    b = math.log(rate) / math.log(2.0)
    return sum(k ** b for k in range(1, n + 1)) / n


# ─────────────────────────────────────────────────────────────────────────────
# PROGRAMME SCALE AND FLEET SIZE  (v1.15.0)
# ─────────────────────────────────────────────────────────────────────────────
# Both functions above are O(N) sums, and until v1.15.0 that cost nothing
# because N was a config field read a handful of times per run.  It is now a
# searched axis, so they are called once per (candidate × programme), and at
# the top of the ladder N runs into the hundreds, which would put a
# several-hundred-iteration Python loop inside the innermost loop of the search.
#
# Memoised by VALUE, not by identity, because that is what the arguments are:
# `p_first`, `alpha`, `p_mature` and `rate` are constants for a whole run, so
# these caches hold at most one entry per rung of the ladder.  Nothing about the
# arithmetic changes, same function, same arguments, same result, which is the
# only kind of speed-up this module accepts on a release that also moves numbers.
# v1.17.5: memoised with `functools.lru_cache` rather than a hand-rolled dict.
# The hand-rolled version built its key in Python -- `(int(n), float(rate))` is
# two conversions and a tuple allocation before the lookup even starts -- and at
# 455,094 calls apiece that key construction WAS the cost, not the miss.
# `lru_cache` hashes the argument tuple in C: measured on this machine at
# 159 ns -> 92 ns for the two-argument case and 249 ns -> 131 ns for the
# four-argument one.
#
# ⚠️  Value-identical, not merely equivalent, and the `int()` / `float()` calls
# were not doing anything the cache does not.  Python hashes 1, 1.0 and True to
# the same slot and compares them equal, so a caller passing 1.0 where another
# passed 1 hits the SAME entry either way -- which is exactly what the explicit
# normalisation achieved.  Both callers pass an already-normalised int anyway
# (`_mission_cost_tail` builds `n_missions` as `max(1, int(...))`), so the
# conversions were defensive no-ops on every call this module actually makes.
#
# Unbounded, as the dicts were: the key space is one entry per rung of the
# ladder, and `maxsize=None` is also the fastest lru_cache path -- it skips the
# eviction bookkeeping entirely.
#
# ⚠️  v1.17.7: that argument is correct HERE and does not generalise, so read it
# as a claim about these two key spaces rather than as a house style.  Measured
# after an 800-row default cell, both hold **69 entries** against 2.4 M hits --
# `n_missions` is a rung of the ladder and the rates are config constants, so
# the ceiling has a name.  `_calendar_multipliers_cached` reasoned the same way,
# carried `cadence_yr` in its key, and grew to 36,071 entries on the same cell
# (~70 M and 11-18 GB projected on a full catalog) before being bounded.
#
# The rule the pair of them implies: **`maxsize=None` is safe exactly when you
# can NAME the ceiling.  If you cannot, set one.**  A memo whose hit rate is
# local and whose key space is not is a leak wearing an optimisation's clothes.
@functools.lru_cache(maxsize=None)
def _learning_curve_cached(n_units: int, rate: float) -> float:
    """`learning_curve_factor`, memoised on (units, rate).

    Unbounded because the key space is nameable: `n_units` is a rung of the
    programme ladder and `rate` is a config constant. See the block above.
    """
    return learning_curve_factor(n_units, rate)


@functools.lru_cache(maxsize=None)
def _mining_reliability_cached(
    n_missions: int, p_first: float, alpha: float, p_mature: float,
) -> float:
    """`mining_success_probability`, memoised on (missions, and three constants).

    Unbounded on the same argument as `_learning_curve_cached`: the last three
    arguments are config constants and the first is a ladder rung, so the two
    memos together held 69 entries after 2.4 M hits on an 800-row default cell.
    """
    return mining_success_probability(n_missions, p_first, alpha, p_mature)


def rig_trips_per_ship(
    ops_df: pd.DataFrame, config: CalcConfig, stay_yr: float,
) -> Optional[Tuple[int, int, Optional[int]]]:
    """How many consecutive campaigns one rig is good for, at this stay length.

    Returns `(trips, calendar_cap, trip_cap)`, or None when rig service life is
    not modelled at all, in which case one rig serves the entire programme,
    which is what this module did before v1.8.0.

    v1.15.0 adds the second of the two bounds, and the reason it is second
    rather than a refinement of the first is worth stating plainly:

      • `Mining rig service life` is **15 YEARS**.  It is a calendar figure and
        its own Module 3 notes describe a calendar mechanism: corrosion,
        thermal cycling, radiation dose.  Dividing it by the stay produced a
        mission count, and that count was treated as the rig's whole life.
      • Nothing bounded DUTY CYCLES.  At the ~1.25 yr stay the winning cislunar
        mission actually flies, the calendar bound made one rig good for 12
        consecutive mining campaigns, twelve full digs out of a number that
        only ever promised the machine would not have rusted meanwhile.

    A rig parked between campaigns ages slowly.  One cutting rock does not.  So
    the two bounds are independent and the binding one is the MIN: a long-stay
    mission is still calendar-limited, a short-stay one is now cycle-limited,
    which is the correct way round and was the whole gap.

    A missing Module 3 row reverts to calendar-only, silently, exactly as every
    other `_ops_value` default does, which is why the row is named in
    `_MODULE3_REQUIRED_OPS` with the consequence spelled out.
    """
    if not config.model_rig_service_life or stay_yr <= 0:
        return None
    # v1.17.1: both rows come off the memoised cost tuple rather than two
    # `_ops_value` calls apiece.  This runs once per programme option, so with
    # `optimise_programme_scale` on it is ~40x per candidate mission.
    ops_cost     = _ops_cost_constants(ops_df)
    life_yr      = ops_cost[1]
    calendar_cap = max(1, int(life_yr // stay_yr))
    trip_cap: Optional[int] = None
    if config.model_rig_trip_limit:
        raw = ops_cost[3]
        if raw > 0:
            trip_cap = max(1, int(raw))
    trips = calendar_cap if trip_cap is None else min(calendar_cap, trip_cap)
    return trips, calendar_cap, trip_cap


def campaign_cadence_yr(
    stay_yr: float, synodic_yr: float, config: CalcConfig,
) -> float:
    """How often one rig can start another campaign.

    A rig stays at the asteroid and successive campaigns run back to back, so
    the cadence is the DIG, not the whole mission: campaign w+1 begins as soon
    as campaign w's feed is out of the ground, while campaign w's capsule is
    still flying home.  That is `stay_yr`.

    But you can only dispatch the next capsule when a window opens, and this
    module already knows how rarely that is.  If the rig can dig faster than
    Earth and the target line up, the rig idles and the SYNODIC PERIOD is what
    sets the cadence, so the bound is the max of the two, not the stay.

    ⚠️  That lands hardest on exactly the bodies this model likes.  A synodic
    period goes to infinity as a → 1 AU, so a NEA at 1.05 AU can only be
    revisited every ~14 years however fast its rig works, while a main-belt
    body at 3 AU comes round every ~1.6.  Δv accessibility and CADENCE are
    anticorrelated for the same reason Δv accessibility and trip time already
    are, see `synodic_period_yr`, and a programme is where that finally
    costs something, because a single mission pays the wait once and a
    programme of W campaigns pays it W − 1 more times.

    Follows `model_launch_windows`: with windows off the synodic term is not
    merely zeroed here, it is not consulted, exactly as `window_wait_yr` is.
    """
    stay = max(0.0, float(stay_yr))
    if not config.model_launch_windows:
        return stay
    return max(stay, max(0.0, float(synodic_yr)))


def programme_calendar_multipliers(
    missions_per_ship: int, cadence_yr: float, wacc: float,
) -> Tuple[float, float]:
    """Time-value multipliers for the programme-level up-front lines.

    Returns `(cost_multiplier, credit_multiplier)`, both exactly 1.0 at
    W = 1, which is every single-mission figure this project has ever
    published.

    ── What is actually wrong without this ─────────────────────────────────

    This module compounds costs FORWARD to the point of sale and compares them
    against undiscounted revenue; that is the convention `mission_cost_usd`
    already implements with `(1 + W)^T` on the up-front bucket.  Applied to one
    mission it is right.  Applied to a programme it quietly assumes every
    mission in the programme happens at once.

    It does not.  F ships fly W campaigns each, and the campaigns on one ship
    are strictly sequential: one rig, one hole, one dig at a time.  So the
    programme spans `T + (W − 1) × cadence` of calendar, and the articles that
    are bought ONCE at the start and amortised across all of it, the bus NRE,
    the autonomy NRE, and the rig itself, are being carried for far longer
    than one mission duration before the missions they paid for sell anything.

    Note which lines this is and is not.  A per-mission article (the launch,
    the capsule, the propellant, the plant, the electric stage) is bought for
    its own campaign, and that campaign's costs AND its revenue both sit at the
    same point in the programme, shift a whole cash flow and its cost/revenue
    ratio does not move.  Only the amortised lines are stretched, because only
    they are paid at t = 0 for a mission that sells at t = w × cadence.

    ── The arithmetic ──────────────────────────────────────────────────────

    Campaign w (w = 0 … W−1) sells at `T + w × cadence`, so its share of an
    article bought at t = 0 compounds by `(1+W)^(T + w·cadence)`.  Factor out
    the `(1+W)^T` the caller already applies and average over the programme:

        cost   = mean of y^w  for w = 0 … W−1        y = (1 + wacc)^cadence
               = (y^W − 1) / ((y − 1) · W)

    Terminal value runs the other way and must not be given the same factor.
    The rig's salvage credit is received once, at the END of the programme, so
    relative to a campaign that sold at `T + w·cadence` it arrives LATE and is
    worth less, not more:

        credit = mean of y^(w − (W−1))              = (1 − y^-W) / ((1 − 1/y) · W)

    which is ≤ 1 and falls with W.  Compounding a credit forward alongside the
    cost it is netted against would inflate a refund for taking longer to
    collect it, the exact shape of subsidy this module keeps finding, arriving
    this time through a term added to remove one.
    """
    w = max(1, int(missions_per_ship))
    if w == 1 or wacc <= 0.0 or cadence_yr <= 0.0:
        return 1.0, 1.0
    y = (1.0 + wacc) ** cadence_yr
    if y <= 1.0:
        return 1.0, 1.0
    cost   = (y ** w - 1.0) / ((y - 1.0) * w)
    credit = (1.0 - y ** -w) / ((1.0 - 1.0 / y) * w)
    return cost, credit


# v1.17.7: BOUNDED, and it is the only cache in this module that has to be.
#
# Every other memo here keys on something with a small, fixed range: a frame's
# identity, a config value, a fleet size, a rung of the ladder, so it reaches a
# ceiling and sits there: `_learning_curve_cached` and `_mining_reliability_cached`
# hold 69 entries apiece after 2.4 M hits, and `_COMPOSITION_CACHE` holds ~25.
# This one keys on `cadence_yr`, which is `max(stay, synodic)` and therefore a
# fresh float per candidate mission, so it grew LINEARLY with the catalog:
#
#     cap  100 rows ->   3,983 entries       cap 800 rows -> 36,071 entries
#     cap  400 rows ->  17,729 entries       ~45 entries per catalog row
#
# which projects to ~70 M entries and 11-18 GB on a full-catalog default cell,
# against a documented run peak of ~6 GB.  Nothing had caught it because the
# cache landed in v1.17.4 and no full-catalog run has been made since v1.16.0.
#
# The retention was buying nothing.  Replaying the real 223,538-call sequence
# through bounded LRUs, all reuse is local to one candidate mission, v1.17.5's
# per-candidate `rig_cache` already absorbs the cross-option traffic one level
# up, and what reaches here is one ask per distinct (W, cadence) within a
# candidate:
#
#     unbounded     hit rate 83.9%     retained 36,071 entries
#     maxsize 1024  hit rate 83.9%     retained  1,024 entries
#     maxsize   64  hit rate 83.8%     retained     64 entries
#
# 36,071 entries buy 0.1 pp over 64.  1024 is headroom, not a measured need.
#
# ⚠️  This cannot change a single output value, and that is worth stating
# because almost nothing else in this file is safe to say: it is a memo of a
# deterministic pure function, so evicting an entry only forces recomputation
# of the identical float.  Bit-identity holds by CONSTRUCTION rather than by
# rounding, unlike the arithmetic reorderings this project keeps declining.
#
# `functools.lru_cache` also happens to be faster than the hand-rolled dict it
# replaces, because it hashes the argument tuple in C instead of building a key
# tuple in Python first; the same finding v1.17.5 made for the two memos
# above.  Measured on this machine, per hit:
#
#     hand-rolled dict  180.1 ns      lru_cache(1024)   91.0 ns
#     lru_cache(None)    93.4 ns      lru_cache(256)    94.0 ns
#
# so bounding it is not a trade against speed.  Note this retires the "unbounded,
# as the dicts were" reasoning above for THIS function only: that argument rests
# on the key space being small, and here it is not.
@functools.lru_cache(maxsize=1024)
def _calendar_multipliers_cached(
    missions_per_ship: int, cadence_yr: float, wacc: float,
) -> Tuple[float, float]:
    """`programme_calendar_multipliers`, memoised by value.

    v1.17.4, and the same argument as `_learning_curve_cached` and
    `_mining_reliability_cached` directly above, except that this one is not
    an O(N) sum, so it was easy to miss.  It is two `**` calls, which are the
    slowest float operations in the tail.

    The ladder is the F ladder CROSSED WITH W, and this function reads W and
    nothing else the ladder varies: `cadence` and `wacc` are fixed for the
    whole candidate.  So ~40 programme options ask it for at most `trips`
    distinct answers, and `trips` is `min(life / stay, max_trips)` with
    `max_trips` = 5.  Measured at 369,166 calls for 10,741 candidates: about
    eight askings per answer.

    Keyed globally rather than per candidate because the arguments ARE the
    inputs; the same (W, cadence, wacc) is the same pair of multipliers for
    any body, and `w == 1` returns before the cache is touched, so the
    single-mission path is untouched.  Bounded because `cadence_yr` is not:
    see the note above.
    """
    return programme_calendar_multipliers(missions_per_ship, cadence_yr, wacc)


def fleet_search_ladder(f_min: int, f_max: int, steps: int) -> List[int]:
    """Coarse geometric sweep over fleet size.  Endpoints always included.

    Same idiom, and the same argument, as the concentration sweep in
    `evaluate_combo`: geometric rather than linear so the cheap end is sampled
    as finely as the expensive end, because going from one ship to two is a
    doubling of concurrent output and going from 63 to 64 is not.
    """
    f_min = max(1, int(f_min))
    f_max = max(f_min, int(f_max))
    steps = max(2, int(steps))
    if f_max - f_min + 1 <= steps:
        return list(range(f_min, f_max + 1))
    span = f_max / f_min
    out  = {f_min, f_max}
    for i in range(steps):
        out.add(max(f_min, min(f_max, int(round(f_min * span ** (i / (steps - 1)))))))
    return sorted(out)


def fleet_refinement(
    f_best: int, ladder: List[int], f_min: int, f_max: int,
) -> List[int]:
    """The one refinement pass around the coarse winner.

    Two geometric midpoints; the interval between the bracketing rungs is
    exactly what the coarse sweep left unexamined, plus both immediate integer
    neighbours.  The neighbours are not decoration: the answer is a COUNT OF
    SHIPS, and reporting a fleet of 23 when the optimum is 22 is reporting an
    artefact of the ladder's spacing as if it were a result.
    """
    seen = set(ladder)
    out  = {f_best - 1, f_best + 1}
    prev = max((f for f in ladder if f < f_best), default=None)
    nxt  = min((f for f in ladder if f > f_best), default=None)
    if prev is not None:
        out.add(int(round(math.sqrt(prev * f_best))))
    if nxt is not None:
        out.add(int(round(math.sqrt(f_best * nxt))))
    return sorted(f for f in out if f_min <= f <= f_max and f not in seen)


def programme_options(
    rig_trips: Optional[Tuple[int, int, Optional[int]]], config: CalcConfig,
    market_mode: Optional[str] = None,
) -> List[Tuple[int, int, int]]:
    """The `(n_missions, fleet_ships, missions_per_ship)` programmes to price.

    ⚠️  **v1.16.0 RETIRES THE BAND ARGUMENT BELOW, and it is worth reading what
    it said before reading what replaced it.** The argument was sound on the
    model it was written for: within a fleet band every lever improved with N
    and none pushed back, so the best N in a band was its top, N = F × trips,
    and the search could be one-dimensional over F.

    Charging programme calendar time adds the lever that pushes back.  A
    programme of W campaigns per ship carries its NRE and its rig across
    `(W − 1) × cadence` of extra calendar (see
    `programme_calendar_multipliers`), and that cost grows like `y^W` while
    NRE/N falls like 1/N.  An exponential against a hyperbola has an interior
    optimum, so **W is now a genuine decision and the top of the band is
    usually not it.**

    So the search is two-dimensional, over (F, W), with N = F × W:

      • **F is a ladder**: geometric, refined, capped by `max_fleet_ships`,
        exactly as v1.15.0 built it.  It runs to 64 and cannot be enumerated.
      • **W is ENUMERATED EXHAUSTIVELY**, 1 … trips.  No ladder, no refinement
        pass, no unimodality assumption, because `trips` is
        `min(life / stay, max_trips)` and `max_trips` is 5; the whole
        dimension is at most a dozen integers and typically five.  A dimension
        small enough to enumerate should be enumerated rather than argued
        about; v1.15.0's own verification found its one real miss in exactly
        the gap a heuristic leaves.

    Two things this buys beyond correctness:

      • **N = 1 is now literally in the search set** (F = 1, W = 1), rather
        than being dominated by N = trips through the band argument.  The
        never-worse invariant against every committed figure therefore holds
        by inspection instead of by proof.
      • **Non-rectangular programmes stop being mis-booked.**
        `missions_sharing_rig` was `min(N, trips)`, which for N = 7 over 2
        ships claims 5 campaigns on a rig that only ever flies 4.  It is now
        `min(trips, ceil(N / F))`, derived from the fleet like everything else.

    With `model_programme_calendar` off, both of those revert and this function
    returns the v1.15.0 ladder exactly, N = F × trips and all.

    ── Why v1.15.0 searched FLEET SIZE, and N followed (superseded) ─────────

    N, `nre_amortization_missions`, is the programme size, and it enters this
    model in exactly six places: the NRE division, the autonomy-NRE division,
    the rig amortisation, the learning curve, reliability growth, and (since
    v1.14.0) the concurrent output that market saturation prices against.  Group
    them by how they behave and the search collapses:

      • ONE RIG SERVES `trips` MISSIONS BACK TO BACK, so a programme of N needs
        `ceil(N / trips)` rigs and that many missions are in flight at once.
        The saturation multiplier is a function of that COUNT and of nothing
        else about N.
      • WITHIN ONE FLEET BAND, every N with the same `ceil(N / trips)`, the
        multiplier is therefore constant, while NRE/N falls, autonomy NRE/N
        falls, the learning curve falls, the rig's per-mission share falls (or
        holds), and p_mining rises.  Every single lever improves and none
        pushes back.

    So the best N in a band is always the TOP of the band, N = F × trips, and no
    other N can ever be optimal.  The search is over F, exactly `max_fleet_ships`
    integers of which only ~12 are ever evaluated, rather than over N, which
    would be `max_fleet_ships × trips` of them, and which is what "just run it at
    1, 10 and 100" was sampling blindly.

    That is not an approximation and it is not a heuristic.  It is also the
    answer to the question the user asked in the first place: the number of ships
    is the decision variable, and programme size is its consequence.

    Two further consequences worth keeping:

      • N = 1 IS NEVER SKIPPED IN EFFECT.  It sits in band 1, whose top is
        N = trips, and by the argument above N = trips dominates it.  So a
        searched run can never report a worse objective than the N = 1 run every
        committed figure in this project was measured at, which is the
        never-worse invariant this module requires of any new axis, and here it
        holds by construction rather than by measurement.
      • N = F × trips IS ALSO THE ONLY N THE COST MODEL IS EXACTLY RIGHT AT.
        `mining_rig_cost` charges every mission the same share of a fully-used
        rig, so a programme of 13 with trips = 12 books its second rig; used
        once, as though it were worn out.  At a whole multiple there is no
        part-worn rig to mis-book.

    ⚠️  THE BAND ARGUMENT IS PER CANDIDATE, AND `trips` IS NOT A PROPERTY OF THE
    BODY.  It is `min(life / stay, max_trips)`, and the stay depends on how hard
    that candidate concentrates, so two concentration ratios on the same rock
    are two different mission profiles with two different trip lives and two
    different ladders.  That is handled correctly, because this function is
    called per candidate with that candidate's own stay.

    What it exposes is a pre-existing heuristic one level up.  `evaluate_combo`
    sweeps the concentration ratio coarsely and then refines around the WINNER,
    and the winner now depends on N, so a ratio that would have won at some
    other programme size can fall outside the refined region and never be
    priced.  Measured on 2014 JT2 beneficiated: brute-forcing every N from 1 to
    40 finds N = 4 at 30.2597x on a ratio of 3.216 (stay 1.74 yr, trips 4),
    while the ladder reports N = 3 at 30.5535x on a ratio of 5.518 (trips 3): 
    0.97% worse, because 3.216 was never on the grid it searched.  Raising
    `concentration_search_steps` from 7 to 25 makes the ladder return 30.2597x
    on ratio 3.216 exactly, which is what identifies the grid rather than this
    argument as the cause.

    It is documented rather than patched.  Refining around the best two ratios
    would be a heuristic stacked on a heuristic, for a sub-1% effect that the
    existing dial already closes, and `concentration_search_steps` is the dial
    this project already points at for exactly this trade.  It bites only where
    beneficiation is on AND the optimum stay sits near a `life / stay` step.

    With `optimise_programme_scale` off this returns the single configured
    programme, which is the pre-v1.15.0 behaviour exactly.
    """
    # v1.21.0.  `single_mission` is the explicit "one mission, no programme"
    # setting: prices constant, no ceiling, N pinned at 1 whatever
    # `nre_amortization_missions` and `optimise_programme_scale` say.  It is
    # the question almost every figure measured before calc v1.17.0 was
    # answering, and it is on the market-model selector rather than left to a
    # reader to reconstruct from two other flags.
    if (market_mode or _market_mode(config)) == "single_mission":
        return [(1, 1, 1)]

    n_cfg = max(1, int(config.nre_amortization_missions))
    trips = rig_trips[0] if rig_trips is not None else None
    calendar = config.model_programme_calendar

    if trips is None:
        # No service-life cap at all: one rig serves the whole programme, so
        # `concurrent_missions` is 1 for every N and saturation never pushes
        # back.  The objective is then monotone improving in N without bound; 
        # "fly more missions" is free money again, which is precisely the
        # failure v1.14.0 closed.  Searching an unbounded monotone axis reports
        # the ladder's top rung as a result, so it is refused rather than run.
        # `build_profitability_catalog` says so out loud at startup.
        #
        # ⚠️  The calendar charge does NOT rescue this.  With one rig serving
        # everything, W = N and the charge grows without bound too, but so
        # does the amortisation it is charged against, and neither is bounded
        # by anything physical, so the optimum would be an artefact of whichever
        # diverges faster.  Still refused.  (W = N here is not read anyway:
        # `mission_cost_usd` only consults it inside the rig block, which this
        # branch means is switched off.)
        return [(n_cfg, 1, n_cfg)]

    if not config.optimise_programme_scale:
        f = max(1, math.ceil(n_cfg / trips))
        # v1.16.0: campaigns per ship is derived from the fleet.  Off, it is
        # the v1.15.0 expression `min(N, trips)`, which over-counts a
        # non-rectangular programme, and is kept under the gate so the flag
        # reproduces that release rather than something between the two.
        w = min(trips, math.ceil(n_cfg / f)) if calendar else min(n_cfg, trips)
        return [(n_cfg, f, max(1, w))]

    # The configured N is the FLOOR of the search, not the answer: a caller who
    # sets N = 50 is stating a programme they have already committed to, and the
    # search should size the fleet for it and upward rather than propose a
    # smaller one.
    f_min  = max(1, math.ceil(n_cfg / trips))
    f_max  = max(f_min, int(config.max_fleet_ships))
    ladder = fleet_search_ladder(f_min, f_max, config.programme_search_steps)
    if not calendar:
        return [(f * trips, f, trips) for f in ladder]
    # Two-dimensional: the F ladder × every W.  See the docstring for why W is
    # enumerated rather than laddered; it is at most `max_trips` integers.
    return [(f * w, f, w) for f in ladder for w in range(1, trips + 1)]


def _ops_table(ops_df: pd.DataFrame) -> Dict[str, Optional[float]]:
    """category → value mapping for `ops_df`, built once and memoised."""
    global _OPS_CACHE
    cached_df, mapping = _OPS_CACHE
    if cached_df is ops_df:
        return mapping

    mapping = {}
    for cat, val in zip(ops_df["category"], ops_df["value"]):
        key = str(cat)
        if key in mapping:
            continue                      # first match wins, as .iloc[0] did
        mapping[key] = float(val) if pd.notna(val) else None
    _OPS_CACHE = (ops_df, mapping)
    return mapping


def _ops_value(ops_df: pd.DataFrame, category: str, default: float = 0.0) -> float:
    """Pull an operational-cost line-item value from Module 3 by category.

    Absent category and present-but-NaN value both fall back to `default`,
    matching the original row-filter implementation exactly.

    The cache tuple is read inline rather than through `_ops_table()`: this
    runs ~9.6 million times over a full catalog (19 line items per cost
    cascade), and at that count the function call to re-check an identity
    that has already been checked is itself measurable.  `_ops_table` still
    owns building the mapping; this only skips the call on a hit.
    """
    cached_df, mapping = _OPS_CACHE
    if cached_df is not ops_df:
        mapping = _ops_table(ops_df)
    val = mapping.get(category)
    return default if val is None else val


_OPS_SIZING_CACHE: Tuple[Optional[pd.DataFrame], Optional[Tuple[float, ...]]] = (None, None)


def _ops_sizing_constants(ops_df: pd.DataFrame) -> Tuple[float, ...]:
    """The twelve Module 3 rows the coupled sizing loop needs, resolved once.

        (dig Wh/kg, beneficiation Wh/kg, array W/kg at 1 AU,
         EP efficiency, EP thruster+PPU kg/kW, RTG W/kg, PPU-only kg/kW,
         dark fraction, storage Wh/kg usable, storage round-trip efficiency,
         baseline dark hours, volatile containment kg/kg)

    The last two of those are fallbacks rather than the primary path as of
    v1.12.0: EP efficiency and thruster mass are per-technology now (Module 3's
    `_THRUSTER_SYSTEMS`), and the shared constants are what a stale Module 3
    catalog reverts to.

    None of them depends on the asteroid, the vehicle or the propellant, but
    they were being looked up inside `_evaluate_combo_at_ratio`, which runs
    once per (asteroid × vehicle × propellant × architecture × concentration
    ratio), so five constant lookups became ~24 million of them on a
    beneficiated catalog.  Memoised on `ops_df` identity like the other
    reference tables.
    """
    global _OPS_SIZING_CACHE
    cached_df, vals = _OPS_SIZING_CACHE
    if cached_df is ops_df:
        return vals

    vals = (
        _ops_value(ops_df, "Drilling / excavation energy", default=200.0),
        _ops_value(ops_df, "Beneficiation / on-site processing energy", default=500.0),
        _ops_value(ops_df, "Power system specific mass", default=60.0),
        _ops_value(ops_df, "Electric propulsion efficiency", default=0.60),
        _ops_value(ops_df, "Electric thruster + PPU specific mass", default=8.0),
        _ops_value(ops_df, "RTG specific power", default=5.0),
        _ops_value(ops_df, "Power processing unit specific mass", default=4.7),
        # v1.14.0.  The defaults here are the ones that REPRODUCE v1.13.0 rather
        # than the physical figures, deliberately: a dark fraction of 0.0 and a
        # containment fraction of 0.0 mean "this Module 3 catalog predates the
        # rows", and a stale catalog should reproduce the release it belongs to
        # instead of silently half-applying a new term.  `schema_check` names
        # each of them, because reverting quietly is the failure mode.
        _ops_value(ops_df, "Eclipse / night-side dark fraction", default=0.0),
        _ops_value(ops_df, "Energy storage usable specific energy", default=0.0),
        _ops_value(ops_df, "Energy storage round-trip efficiency", default=0.90),
        _ops_value(ops_df, "Power-system row baseline dark period", default=0.0),
        _ops_value(ops_df, "Volatile cargo containment", default=0.0),
    )
    _OPS_SIZING_CACHE = (ops_df, vals)
    return vals


_OPS_COST_CACHE: Tuple[Optional[pd.DataFrame], Optional[Tuple[float, ...]]] = (None, None)


def _ops_cost_constants(ops_df: pd.DataFrame) -> Tuple[float, ...]:
    """The twenty-two Module 3 rows the COST cascade needs, resolved once.

    v1.17.1, and it is v1.10.1's sizing-loop memo applied to the other half of
    the model.  `mission_cost_usd` pulled ~18 of these per call through
    `_ops_value`, and `rig_trips_per_ship` two more; none of which depends on
    the asteroid, the vehicle, the propellant, the architecture or the
    programme option.  They are pure functions of `ops_df`, which is loaded
    once per run and never mutated.

    That was survivable while the cost model ran once per surviving candidate.
    It stopped being survivable in v1.17.0, which turned `optimise_programme_scale`
    ON BY DEFAULT: the programme ladder prices a median of 40 options per
    mission, so every one of those lookups is now multiplied by 40.  Measured
    on a 150-row beneficiated cislunar sample with the search on,
    `_ops_value` was running **8.06 million times**: 11.7% of the profile, to
    re-read twenty-two numbers that never move.

    Ordered, not named, for the same reason `_ops_sizing_constants` is: the
    callers unpack the whole tuple in one statement, which is a single opcode,
    and every read after that is a local.  Keep this list and the unpacking in
    `mission_cost_usd` in the same order; they are checked against each other
    by nothing but review, so the defence is that they are adjacent and the
    gated-off diff is bit-identical.

    ⚠️  Every row is resolved EAGERLY, including the ones only one destination
    or one power source reads.  That is deliberate and it is not a behaviour
    change: `_ops_value` is total (an absent row and a NaN value both fall back
    to the default), so resolving a branch that is not taken costs one dict
    lookup at run start and cannot fail.  The value is then simply not used.
    """
    global _OPS_COST_CACHE
    cached_df, vals = _OPS_COST_CACHE
    if cached_df is ops_df:
        return vals

    vals = (
        _ops_value(ops_df, "Mining payload recurring cost", default=300_000.0),
        _ops_value(ops_df, "Mining rig service life", default=15.0),
        _ops_value(ops_df, "Rig salvage fraction", default=0.50),
        _ops_value(ops_df, "Mining rig maximum trips", default=0.0),
        _ops_value(ops_df, "Surface lander recurring cost", default=200_000.0),
        _ops_value(ops_df, "Return capsule recurring cost", default=150_000.0),
        _ops_value(ops_df, "Berthing adapter recurring cost", default=60_000.0),
        _ops_value(ops_df, "Power system (solar + battery)", default=800.0),
        _ops_value(ops_df, "RTG (radioisotope power)", default=500_000.0),
        _ops_value(ops_df, "Electric propulsion system recurring cost",
                   default=1_500_000.0),
        _ops_value(ops_df, "Propellant tank recurring cost", default=6_000.0),
        _ops_value(ops_df, "Mission operations", default=31_400_000.0),
        _ops_value(ops_df, "Heat shield / TPS for Earth return", default=50_000.0),
        _ops_value(ops_df, "Sample recovery operations", default=15_000_000.0),
        _ops_value(ops_df, "FAA Part 450 licensing compliance", default=2_500_000.0),
        _ops_value(ops_df, "Depot berthing & handover operations", default=2_000_000.0),
        _ops_value(ops_df, "FAA Part 450 licensing (launch only)", default=1_200_000.0),
        _ops_value(ops_df, "Third-party liability insurance", default=1_500_000.0),
        _ops_value(ops_df, "Launch insurance", default=10.0),
        _ops_value(ops_df, "Spacecraft development (NRE)", default=588_500_000.0),
        _ops_value(ops_df, "Autonomous mining control & AI (NRE)",
                   default=200_000_000.0),
        _ops_value(ops_df, "Cost of capital (WACC)", default=0.10),
    )
    _OPS_COST_CACHE = (ops_df, vals)
    return vals


_OPS_RELIABILITY_CACHE: Tuple[Optional[pd.DataFrame],
                              Optional[Tuple[float, ...]]] = (None, None)


def _ops_reliability_constants(ops_df: pd.DataFrame) -> Tuple[float, ...]:
    """The five Module 3 rows the RELIABILITY block needs, resolved once.

    v1.17.6, and the same finding as `_ops_cost_constants` (v1.17.1) and
    `_ops_sizing_constants` (v1.10.1) in the one block between them that still
    read `_ops_value` per candidate.  `_evaluate_combo_at_ratio` pulled all
    five out of the table for every surviving (vehicle × propellant × Δv ×
    ISRU × ratio × power source): 10,741 times on a 150-row sample, for five
    numbers that are fixed for the run.

    Eagerly resolved, like the other two: `_ops_value` is total, so a row that
    is absent falls back to the same default the per-call read would have used.
    """
    global _OPS_RELIABILITY_CACHE
    cached_df, vals = _OPS_RELIABILITY_CACHE
    if cached_df is ops_df:
        return vals

    vals = (
        _ops_value(ops_df, "Launch vehicle reliability", default=0.97),
        _ops_value(ops_df, "Spacecraft mean time between failures", default=30.0),
        _ops_value(ops_df, "Mining system first-of-kind success probability",
                   default=0.85),
        _ops_value(ops_df, "Mining reliability growth exponent", default=0.30),
        _ops_value(ops_df, "Mining system mature success probability", default=0.95),
    )
    _OPS_RELIABILITY_CACHE = (ops_df, vals)
    return vals


# ─────────────────────────────────────────────────────────────────────────────
# MISSION COST CASCADE
# ─────────────────────────────────────────────────────────────────────────────
def _mission_cost_prologue(
    mass_cascade:        Dict[str, float],
    vehicle:             Row,
    propellant:          Row,
    ops_df:              pd.DataFrame,
    config:              CalcConfig,
    mission_duration_yr: float,
    processing_power_w:  float = 0.0,
    stay_yr:             float = 0.0,
    isru_return:         Optional[bool] = None,
    ep_power_w:          float = 0.0,
    power_source:        str   = "solar",
    cadence_yr:          Optional[float] = None,
    rig_trips:           Optional[Tuple[int, int, Optional[int]]] = None,
) -> tuple:
    """The half of `mission_cost_usd` that does not move with programme size.

    v1.17.2.  The ladder in `_price_programme` varies `n_missions` and
    `missions_per_ship` and NOTHING else; every other argument is held fixed
    across a median of 40 options, yet the whole cost cascade was re-derived
    for each of them.  That is ~10 `max()` calls, ~6 dict lookups, ~15 `float()`
    conversions, a `delivery_architecture` call and a 22-tuple unpack, run forty
    times to change three numbers.  This is the same finding as v1.17.1's, one
    level up: that release stopped re-READING the constants, this one stops
    re-DERIVING everything computed from them.

    ── WHY THIS IS BIT-IDENTICAL, WHICH v1.17.1 SAID IT COULD NOT BE ───────────

    That release deferred this split because "it re-associates the final sums,
    and this project's releases are argued from bit-identity".  The premise is
    right and the conclusion does not follow, because every N-dependent line in
    the cascade factors as `<N-independent base> * lc`, and Python evaluates
    `a * b * lc` left to right, as `(a * b) * lc`.  So hoisting `a * b` into a
    name and multiplying by `lc` in the tail is the SAME two operations in the
    SAME order, not an algebraically-equal rearrangement.  Same for
    `nre_total * (1.0 - overlap) / n_missions`, which is `(a * b) / n`.

    🚨  What must NEVER be hoisted is a PARTIAL SUM whose terms interleave with
    N-dependent ones.  `hardware_cost`, `spacecraft_book_value` and
    `upfront_lines` all mix the two, and pre-adding their N-independent members
    would re-associate the addition, numerically negligible and fatal, exactly
    as the v1.14.2 phase-table sort was.  Those three sums are therefore
    restated VERBATIM in `_mission_cost_tail`, term for term and in order, and
    the four or five adds that costs are not what this function was slow for.

    ⚠️  The returned tuple's field order is load-bearing and is unpacked in one
    statement at the top of `_mission_cost_tail`; keep the two together, the
    same discipline `_ops_cost_constants` and its consumer already follow.
    """
    # v1.17.1: the twenty-two Module 3 constants this cascade reads, resolved
    # once per run rather than once per call.  Order matches
    # `_ops_cost_constants`; keep the two together.
    (hw_per_kg, life_yr, salvage, _max_trips_raw,
     lander_per_kg, capsule_earth_per_kg, berthing_per_kg,
     power_per_w, rtg_per_w, ep_drive_per_kw, tank_per_kg,
     ops_per_year, tps_per_kg,
     recovery_earth, licensing_earth, recovery_depot, licensing_depot,
     liability_cost, launch_ins_raw,
     nre_total, autonomy_nre_total, wacc_rate) = _ops_cost_constants(ops_df)

    # ── Insurance (v1.20.0) ──────────────────────────────────────────────────
    # Both premiums are zeroed HERE rather than at their two use sites, so the
    # sums in the tail stay written out term for term and in order.  Adding 0.0
    # to a finite float is exact, so nothing is re-associated and no other line
    # moves; that is the same discipline as the three sums the tail must not
    # pre-add.  See `charge_insurance` for why they are off.
    if not config.charge_insurance:
        liability_cost = 0.0
        launch_ins_raw = 0.0

    cost_per_kg_prop = float(propellant["cost_usd_per_kg"])
    launch_cost      = float(mass_cascade["m_launch"]) * float(vehicle["usd_per_kg_to_leo"])

    # ── Orbital refuelling (v1.11.0, re-keyed v1.12.0) ───────────────────────
    # Some vehicles quote a beyond-LEO payload that assumes being refuelled in
    # orbit first.  Starship is the case in this table, and the tell is in its
    # own numbers: 27 t to escape against 21 t to GTO.  A payload cannot grow
    # with departure energy under any propulsion system, unless the escape
    # figure is for a vehicle that was topped up after reaching orbit.
    #
    # Module 3's row has said so in prose since v1.4.0 and named the fix:
    # "Module 4 should add ~$90M × N_tankers to the ESCAPE-DIRECT SCENARIO for
    # an apples-to-apples comparison."  v1.11.0 implemented the arithmetic and
    # missed the scenario; it levied the charge on every mission.
    #
    # This module has no escape-direct scenario.  It reads `payload_leo_kg` and
    # `usd_per_kg_to_leo` and nothing else (grep the file): the launch vehicle
    # delivers the stack to LEO, and the stack departs on its own outbound
    # stage, which is sized by the rocket equation a few dozen lines up.
    # Starship's 100 t to LEO needs no tankers; refuelling is what buys the
    # ESCAPE figure, which is never read.  So charging 12 flights was billing
    # $1.08B for a capability the mission does not use.
    #
    # It is kept, wired and gated rather than deleted, because the day this
    # module gains a direct-injection architecture the charge becomes correct
    # and the column is already there.  `escape_direct_launch` is the switch;
    # nothing sets it today, which is the honest state of affairs.
    tanker_flights = int(vehicle.get("tanker_flights_for_escape", 0) or 0)
    escape_direct  = bool(getattr(config, "escape_direct_launch", False))
    if config.charge_tanker_flights and escape_direct and tanker_flights > 0:
        tanker_cost = tanker_flights * float(vehicle.get("list_price_usd", 0.0) or 0.0)
    else:
        tanker_cost = 0.0
        tanker_flights = 0 if not escape_direct else tanker_flights
    launch_cost += tanker_cost

    outbound_prop_cost = float(mass_cascade["m_outbound_prop"]) * cost_per_kg_prop
    # v1.10.0: whether this particular mission makes its own propellant is a
    # per-asteroid decision, so it arrives as an argument.  None falls back to
    # the config for callers that have not been updated.
    if isru_return is None:
        isru_return = config.use_isru_return_propellant
    if isru_return:
        # ISRU prop is "ongoing", manufactured at the asteroid over the
        # mining duration, not pre-paid upfront on Earth.
        return_prop_cost = float(mass_cascade["m_return_prop"]) * config.isru_processing_usd_per_kg
        return_prop_is_ongoing = True
    else:
        return_prop_cost = float(mass_cascade["m_return_prop"]) * cost_per_kg_prop
        return_prop_is_ongoing = False

    # Recurring hardware, split into the mining rig (one-way to asteroid,
    # AMORTISABLE across multi-mission programmes since the rig stays put)
    # and the return capsule (fresh per mission, fly-and-die).
    mining_rig_cost_total   = config.mining_hardware_kg * hw_per_kg

    # v1.17.1: `rig_trips` is `(ops_df, config, stay_yr)` and nothing else, and
    # all three are held FIXED across a programme ladder, so the caller that
    # searched (F, W) has already derived it and passes it in, instead of this
    # function re-deriving the same triple once per option.  None keeps the
    # v1.16.0 behaviour for every other caller, so this is a pass-through, not
    # a second derivation: `rig_trips_per_ship` remains the only place the
    # two bounds are resolved.
    if rig_trips is None:
        rig_trips = rig_trips_per_ship(ops_df, config, stay_yr)

    # v1.4.0: the capsule is priced off its OWN rate.  It used to be billed at
    # the mining-payload rate, which treats a parachute-and-heat-shield can as
    # though it were regolith-contact machinery.
    # v1.5.0: and which rate applies depends on where the cargo is going.  An
    # in-space delivery never re-enters, so it carries a passive berthing
    # adapter ($60k/kg) rather than a guided re-entry capsule ($150k/kg).
    # v1.6.0: a surface base needs a LANDER, throttleable descent engines,
    # legs, terminal guidance, which is more machine than either a passive
    # re-entry capsule or a berthing adapter.
    arch = delivery_architecture(config.delivery_destination)
    if arch.get("needs_lander"):
        capsule_per_kg = lander_per_kg
    elif arch["returns_to_earth"]:
        capsule_per_kg = capsule_earth_per_kg
    else:
        capsule_per_kg = berthing_per_kg
    # v1.10.0: bill the return vehicle actually flown.  Its dry mass grows with
    # the haul (return_structure_frac_of_payload), and the cascade records what
    # it came to; charging the 500 kg base rate for a vehicle that massed
    # 19 tonnes would put the mass in the rocket equation and leave the money
    # out of the ledger; the same asymmetry the EP stage had.
    dry_return_flown = float(mass_cascade.get(
        "m_dry_return", config.return_vehicle_dry_kg))
    # ⚠️  v1.17.2: each `*_base` below is the original expression with its
    # trailing `* lc` removed, and nothing else.  The learning curve is applied
    # in the tail because it is the one factor that moves with N.
    capsule_base            = dry_return_flown * capsule_per_kg
    # v1.5.0: the beneficiation plant's solar array, priced per installed Watt
    # off Module 3's power-system row.  Zero unless beneficiation is on; the
    # baseline rig's own power is already implicit in its $/kg recurring rate.
    # v1.11.0: past 3.46 AU the sizing loop may have chosen a radioisotope
    # source because it is LIGHTER there.  It is also 625× more expensive per
    # watt, and charging it at the solar rate would be exactly the asymmetry
    # this codebase keeps finding: a mass in the rocket equation with the
    # wrong price, or none, in the ledger.
    plant_per_w             = (rtg_per_w if power_source == "rtg" else power_per_w)
    power_base              = max(0.0, float(processing_power_w)) * plant_per_w
    # ── Electric propulsion stage (v1.10.0) ──────────────────────────────────
    # v1.7.0 put the EP array and thruster into the ROCKET EQUATION and stopped
    # there: `ep_system_kg` was hauled as mass and never appeared in a single
    # cost line.  A 309 kW, 14-tonne electric stage was therefore free, and
    # electric propulsion won missions on hardware nobody had to buy.  It shows
    # up the moment the selection objective stops preferring the cheapest
    # mission (see selection_key), which is how it was found.
    #
    # Priced in two parts, because they cost wildly different amounts per
    # kilogram: the array off the same $/W row as any other deep-space PV
    # train, the thruster and PPU off Module 3's per-kW propulsion row.
    ep_kw = max(0.0, float(ep_power_w)) / 1000.0
    if ep_kw > 0:
        ep_base = (max(0.0, float(ep_power_w)) * power_per_w
                   + ep_kw * ep_drive_per_kw)
    else:
        ep_base = 0.0
    # ── Propellant tankage (v1.12.0) ─────────────────────────────────────────
    # Module 3 has derived tank mass per propellant since v1.9.0 and this
    # module has flown it through the rocket equation ever since, outbound
    # tank staged at the asteroid, return tank carried home, but nothing ever
    # bought one.  The tank paid its launch $/kg (it is inside `m_launch`) and
    # was manufactured for free.
    #
    # It is a small number, ~0.003-0.1% of mission cost, and that is not the
    # point: the recurring defect in this codebase is a mass in one cascade
    # with no entry in the other, and it is only ever found by checking every
    # term rather than the big ones.  The rate is the cheapest hardware line in
    # Module 3 because a tank is the simplest article in the mission.
    tank_mass = (float(mass_cascade.get("m_tank_return", 0.0))
                 + float(mass_cascade.get("m_tank_outbound", 0.0)))
    tank_base = tank_mass * tank_per_kg if tank_mass > 0 else 0.0

    # Mission ops × duration  (per-asteroid duration from Δv estimator)
    ops_cost     = ops_per_year * mission_duration_yr

    # Heat shield; mass now comes from the actual cascade, not re-derived.
    # v1.14.0: the learning curve applies here too.  An ablative heat shield is
    # consumed on entry and rebuilt for every mission; it is the most literally
    # per-mission article on the vehicle, so Wright's law applies to it exactly
    # as it does to the capsule, the power system, the electric stage and the
    # tankage, all of which already carry `lc`.  It was the one recurring
    # article that did not, for no reason anybody wrote down.  Exactly 1.0 at
    # N = 1, so no single-mission figure moves.
    tps_mass = float(mass_cascade.get("m_tps", 0.0))
    tps_base = tps_mass * tps_per_kg if tps_mass > 0 else 0.0

    # Recovery + regulatory flat costs.  v1.5.0: an in-space delivery replaces
    # the Earth recovery campaign (search aircraft, ships, range clearance,
    # clean-room convoy) with depot handover, and drops the re-entry half of
    # the Part 450 licence.
    if arch["returns_to_earth"]:
        recovery_cost  = recovery_earth
        licensing_cost = licensing_earth
    else:
        recovery_cost  = recovery_depot
        licensing_cost = licensing_depot

    # Launch insurance, percent of (launch + spacecraft book value).
    # Gross value of future revenue is NOT insured, underwriters cover the
    # replacement cost of the launched asset only.
    #
    # v1.12.0: that asset is everything on the rocket, and the book value had
    # drifted behind the mass cascade.  It listed the mining rig and the
    # capsule, which was the whole spacecraft in v1.4.0, but v1.5.0 added a
    # beneficiation power plant, v1.7.0 an electric stage that v1.10.0 finally
    # priced at $1.5M/kW, and v1.9.0 propellant tankage.  A 300 kW electric
    # stage is a nine-figure article and it was being flown uninsured.
    #
    # Note the rig enters at its FULL build cost, not the amortised share:
    # losing it on ascent destroys the whole unit however many missions were
    # meant to share it.  Everything else is per-mission already.
    #
    # v1.14.0: and the heat shield is on the rocket too.  v1.12.0 swept this
    # list against the mass cascade and picked up the power plant, the electric
    # stage and the tankage, but TPS is billed from a different variable and was
    # missed; it is the one item on the launch stack whose cost line sits
    # outside `hardware_cost`.  On an Earth-return mission it is a 15%-of-payload
    # article at $50,000/kg, so it is not a rounding term where it exists at all.
    #
    # v1.20.0: `launch_ins_raw` is 0.0 unless `charge_insurance` is set, so all
    # of the above is the arithmetic that flag restores rather than what a
    # default run pays.  The basis is kept rather than deleted because it took
    # three releases to get right, and it is what a reader turning the flag
    # back on inherits.
    launch_ins_pct        = launch_ins_raw / 100.0

    # Spacecraft bus NRE amortised across N missions, less the share already
    # embedded in the per-kg recurring rate (v1.4.0; see
    # nre_recurring_overlap_fraction).  NICM / SSCM per-kg brackets are
    # regressions on total program cost, so charging full OSIRIS-REx NRE on
    # top of a $300k/kg recurring rate books part of the development twice.
    nre_overlap = min(max(config.nre_recurring_overlap_fraction, 0.0), 1.0)
    nre_base    = nre_total * (1.0 - nre_overlap)

    # ── Time-bucket every line item ──────────────────────────────────────────
    # UPFRONT = paid at year 0 (or earlier, NRE accumulates pre-launch but
    # treated as year-0 lump-sum here).
    # ONGOING = spread evenly over [0, T_mission] → effective year T/2.
    # END     = paid at year T_mission.
    #
    # ⚠️  Only `upfront_lines` mixes N-dependent terms; the other two buckets
    # are wholly N-independent and are therefore finished here, contingency and
    # all.  `upfront_lines` is restated verbatim in the tail.
    ongoing_lines = (
        ops_cost
        + (return_prop_cost if return_prop_is_ongoing else 0.0)
    )
    end_lines     = recovery_cost

    # Contingency reserve applied uniformly across buckets (it's a global
    # reserve fund, not tied to any one cost line).
    cont = 1.0 + config.contingency_fraction
    ongoing_with_cont = ongoing_lines * cont
    end_with_cont     = end_lines    * cont

    # WACC compounding, apply per bucket so end-of-mission costs aren't
    # wrongly inflated by the full duration's compounding factor.
    if config.apply_wacc_compounding:
        wacc          = wacc_rate
        mult_upfront  = (1.0 + wacc) ** mission_duration_yr
        mult_ongoing  = (1.0 + wacc) ** (mission_duration_yr / 2.0)
        mult_end      = 1.0
    else:
        wacc = 0.0
        mult_upfront = mult_ongoing = mult_end = 1.0

    cadence   = (stay_yr if cadence_yr is None else max(0.0, float(cadence_yr)))

    return (
        launch_cost, tanker_cost, tanker_flights,
        outbound_prop_cost, return_prop_cost, return_prop_is_ongoing,
        mining_rig_cost_total, rig_trips, life_yr, salvage,
        # v1.22.0: the flag is resolved to a RATE here, once per candidate,
        # rather than carried as a second field the tail would have to branch
        # on.  1.0 is what `learning_curve_factor` already documents as "no
        # curve", so the term goes exactly inert and the memo's key space does
        # not grow: every run holds one rate either way.  The prologue's field
        # ORDER is load-bearing (see its docstring); this replaces a value in
        # place and adds nothing.
        (config.learning_curve_rate if config.model_learning_curve else 1.0),
        capsule_base, power_base, ep_base, ep_kw, tank_base, tank_mass,
        tps_base, tps_mass,
        ops_cost, recovery_cost, licensing_cost, liability_cost, launch_ins_pct,
        nre_base, autonomy_nre_total,
        cont, config.contingency_fraction,
        mult_upfront, mult_ongoing, mult_end, wacc,
        ongoing_lines, ongoing_with_cont, end_lines, end_with_cont,
        cadence, stay_yr, mission_duration_yr,
        config.model_programme_calendar, config.nre_amortization_missions,
    )


def _mission_cost_tail(
    pro:                 tuple,
    n_missions:          Optional[int] = None,
    missions_per_ship:   Optional[int] = None,
    totals_only:         bool = False,
    rig_cache:           Optional[Dict[Tuple[int, bool],
                                       Tuple[float, ...]]] = None,
) -> Union[Dict[str, float], float]:
    """The half of `mission_cost_usd` that DOES move with programme size.

    v1.17.2.  `pro` is `_mission_cost_prologue`'s tuple; the ladder builds it
    once and calls this once per option.  See that function for why the split
    is bit-identical rather than merely numerically equal, and for the three
    sums that must stay written out term by term.
    """
    (launch_cost, tanker_cost, tanker_flights,
     outbound_prop_cost, return_prop_cost, return_prop_is_ongoing,
     mining_rig_cost_total, rig_trips, life_yr, salvage,
     lc_rate,
     capsule_base, power_base, ep_base, ep_kw, tank_base, tank_mass,
     tps_base, tps_mass,
     ops_cost, recovery_cost, licensing_cost, liability_cost, launch_ins_pct,
     nre_base, autonomy_nre_total,
     cont, contingency_fraction,
     mult_upfront, mult_ongoing, mult_end, wacc,
     ongoing_lines, ongoing_with_cont, end_lines, end_with_cont,
     cadence, stay_yr, mission_duration_yr,
     calendar_on, n_missions_cfg) = pro

    # v1.15.0: programme size is a searched axis, so it arrives as an argument.
    # None falls back to the config for every caller that has not been updated,
    # which keeps a single-programme run bit-identical.
    n_missions              = max(1, int(n_missions if n_missions is not None
                                         else n_missions_cfg))

    # ── Rig service life and terminal value (v1.8.0, cycles v1.15.0) ─────────
    # A rig cannot serve more missions than its life allows.  Whatever life
    # remains when the programme ends is credited at the salvage fraction, 
    # but only if there IS a programme; a rig at an asteroid nobody revisits
    # is stranded, not an asset.
    rig_terminal_value = 0.0
    missions_sharing_rig = n_missions
    _rig_hit = _rig_key = None
    if rig_trips is not None:
        trips, _calendar_cap, trip_cap = rig_trips
        # v1.16.0: how many campaigns one rig actually flies is a property of
        # the FLEET, not of N alone, F ships split N between them.  The caller
        # supplies it because the caller is what searched (F, W).  None keeps
        # the v1.15.0 expression, which is what `model_programme_calendar` off
        # and every pre-v1.16.0 caller get.
        missions_sharing_rig = (min(n_missions, trips) if missions_per_ship is None
                                else max(1, min(int(missions_per_ship), trips)))
        # ── v1.17.5: everything from here to the calendar multipliers is a
        # function of (missions_sharing_rig, n_missions > 1) and the PROLOGUE,
        # and the ladder is the F ladder crossed with W, so ~42 options ask
        # for at most `trips` x 2 distinct answers, and `trips` is
        # `min(life / stay, max_trips)` with `max_trips` = 5.  Same shape as
        # `sat_by_fleet` (v1.17.2) and `_calendar_multipliers_cached` (v1.17.4),
        # one level out: this absorbs that call rather than repeating it.
        #
        # Keyed on `missions_sharing_rig` rather than on `missions_per_ship`
        # so the key is correct on BOTH paths, a caller that passes no
        # `missions_per_ship` derives it from N, and the min/max above is cheap
        # enough to run before the lookup.
        #
        # ⚠️  Bit-identical by construction, not by rounding: the same key
        # re-runs the same arithmetic on the same prologue, so the cached
        # floats ARE the floats the block would have produced.  Opt-in; a
        # `rig_cache` of None is exactly the v1.17.4 code path, which is what
        # `mission_cost_usd` and every other caller still get.
        _rig_key = (missions_sharing_rig, n_missions > 1)
        if rig_cache is not None:
            _rig_hit = rig_cache.get(_rig_key)
        if _rig_hit is None and n_missions > 1:
            # Life USED, and there are now two ways to use it up.  Crediting
            # salvage on remaining calendar years while the rig is mechanically
            # finished would pay a refund on a worn-out machine, the same shape
            # of subsidy this module keeps finding, so the binding utilisation
            # is the larger of the two fractions.  Gated with the cycle cap
            # itself: with `model_rig_trip_limit` off this is exactly the
            # calendar-only expression v1.14.2 used.
            life_used_frac = missions_sharing_rig * stay_yr / life_yr
            if trip_cap is not None:
                life_used_frac = max(life_used_frac, missions_sharing_rig / trips)
            life_used_frac = min(1.0, life_used_frac)
            rig_terminal_value = mining_rig_cost_total * (1.0 - life_used_frac) * salvage
    # v1.17.2: one `max(1, ·)` rather than three.  Deliberately NOT dropped
    # altogether: `missions_sharing_rig` is ≥ 1 in every branch above given
    # `trips` ≥ 1, but that is a property of `rig_trips_per_ship`'s current
    # return rather than of anything asserted here, and this file's own history
    # is full of guards that were correct until a table changed underneath them.
    #
    # ── v1.17.5: the calendar multipliers are resolved HERE, with the rig
    # shares, rather than 60 lines below where they used to sit.  They read
    # `missions_sharing_rig`, `cadence` and `wacc` and nothing computed in
    # between, so this is a move, not a reordering of any arithmetic, and it
    # is what lets one cache entry carry the whole W-dependent block instead of
    # two.  The DELTA that applies them to `total_cost` has not moved; see it
    # below, still written on top of the untouched v1.15.0 sum.
    if _rig_hit is not None:
        (mining_rig_cost, rig_gross_share, rig_credit_share,
         rig_terminal_value, cal_cost, cal_credit) = _rig_hit
    else:
        # v1.17.2: one `max(1, ·)` rather than three.  Deliberately NOT dropped
        # altogether: `missions_sharing_rig` is ≥ 1 in every branch above given
        # `trips` ≥ 1, but that is a property of `rig_trips_per_ship`'s current
        # return rather than of anything asserted here, and this file's own
        # history is full of guards that were correct until a table changed
        # underneath them.
        rig_share_divisor = max(1, missions_sharing_rig)
        mining_rig_cost = ((mining_rig_cost_total - rig_terminal_value)
                           / rig_share_divisor)
        # The same two halves again, kept apart rather than netted, because the
        # programme calendar term compounds them in OPPOSITE directions: the rig
        # is bought at t = 0 and the salvage is collected at the end.  Netting
        # first and applying one multiplier would credit the refund for arriving
        # late.  Read only by the calendar delta below, which is skipped outright
        # when the multipliers are 1.0, so `mining_rig_cost` above stays the
        # arithmetic v1.15.0 performed, in the order it performed it.
        rig_gross_share  = mining_rig_cost_total / rig_share_divisor
        rig_credit_share = rig_terminal_value    / rig_share_divisor
        cal_cost = cal_credit = 1.0
        if calendar_on and missions_sharing_rig > 1:
            cal_cost, cal_credit = _calendar_multipliers_cached(
                missions_sharing_rig, cadence, wacc)
        if rig_cache is not None and _rig_key is not None:
            rig_cache[_rig_key] = (mining_rig_cost, rig_gross_share,
                                   rig_credit_share, rig_terminal_value,
                                   cal_cost, cal_credit)

    # v1.7.0: LEARNING CURVE.  The per-mission articles, the capsule or
    # lander, and the power system, are built N times over a programme, and
    # the Nth costs less than the first.  The mining rig is excluded: when
    # nre_amortization_missions > 1 it is modelled as ONE unit shared across
    # missions, not N units built, so a curve on it would double-count.
    # Exactly 1.0 at N = 1, so a single-mission run is untouched.
    lc = _learning_curve_cached(n_missions, lc_rate)
    capsule_cost            = capsule_base * lc
    power_system_cost       = power_base * lc
    ep_system_cost          = ep_base * lc if ep_kw > 0 else 0.0
    tank_cost               = tank_base * lc if tank_mass > 0 else 0.0
    # 🚨  Term by term, in order.  `mining_rig_cost` is N-dependent and the
    # other four are `base * lc`, so pre-adding the bases and multiplying once
    # would re-associate this sum.  See the prologue's docstring.
    hardware_cost           = (mining_rig_cost + capsule_cost + power_system_cost
                               + ep_system_cost + tank_cost)
    heat_shield_cost        = tps_base * lc if tps_mass > 0 else 0.0

    # 🚨  Term by term, in order, same reason as `hardware_cost`.
    spacecraft_book_value = (mining_rig_cost_total + capsule_cost
                             + power_system_cost + ep_system_cost + tank_cost
                             + heat_shield_cost)
    launch_insurance_cost = launch_ins_pct * (launch_cost + spacecraft_book_value)

    nre_cost    = nre_base / n_missions

    # Autonomous mining control & AI NRE, uncrewed-mission specific (Module 3
    # v1.2.4+ replaced the legacy 'Crew' line item with this).  Amortised the
    # same way as the bus NRE, once developed, the autonomy stack ships on
    # every subsequent identical mission.
    autonomy_nre_cost  = autonomy_nre_total / n_missions

    # 🚨  Term by term, in order, same reason as `hardware_cost`.  Four of
    # these ten are N-dependent and they are interleaved with the six that are
    # not, so there is no prefix of this sum that can be hoisted.
    upfront_lines = (
        launch_cost + outbound_prop_cost + hardware_cost + heat_shield_cost
        + licensing_cost + liability_cost + launch_insurance_cost
        + nre_cost + autonomy_nre_cost
        + (0.0 if return_prop_is_ongoing else return_prop_cost)
    )
    upfront_with_cont = upfront_lines * cont

    # ── Programme calendar time (v1.16.0) ────────────────────────────────────
    # The bucket above compounds every up-front line over ONE mission duration,
    # which silently prices a programme as though all of its missions happened
    # at once.  They cannot: one rig digs one hole at a time, so W campaigns per
    # ship span `T + (W-1) x cadence`, and the three articles bought once at
    # t = 0 and amortised across all of them, bus NRE, autonomy NRE, the rig, 
    # are carried for that whole span.  See `programme_calendar_multipliers`
    # for why only those three, and why the salvage credit runs the other way.
    #
    # Written as a DELTA on top of the untouched v1.15.0 expression rather than
    # as a rebuilt sum.  Both multipliers are exactly 1.0 at W = 1, so the
    # branch is skipped, no term is re-associated, and the released arithmetic
    # is bit-identical, which is the only form this project's verification can
    # actually check, and the reason the phase-table sort was rejected in
    # v1.14.2.
    total_cost = (
        upfront_with_cont * mult_upfront
        + ongoing_with_cont * mult_ongoing
        + end_with_cont     * mult_end
    )
    if cal_cost != 1.0 or cal_credit != 1.0:
        programme_upfront = nre_cost + autonomy_nre_cost + rig_gross_share
        total_cost += ((programme_upfront * (cal_cost - 1.0)
                        - rig_credit_share * (cal_credit - 1.0))
                       * cont * mult_upfront)

    # ── v1.17.1: the programme ladder wants ONE number ───────────────────────
    # `_price_programme` prices a median of 40 options per candidate mission
    # and reads `total_cost` from every one of them; the other ~39 keys are
    # read only for the option that WINS.  Building a 40-key dict to throw 39
    # of them away measures at ~3.4 µs a call on the reference machine, which
    # is a third of this function.  So the ladder asks for the total, and the
    # winner is re-priced once in full at the end.
    #
    # This is an early return, NOT a second code path: every line above it is
    # the same arithmetic in the same order, so the float compared by
    # `_objective_key` is bit-identical to the one the full dict would have
    # carried.  Everything below is either a diagnostic (`wacc_multiplier`,
    # `subtotal`, `contingency_cost`) or the dict itself; nothing below
    # touches `total_cost`.
    if totals_only:
        return total_cost

    # Weighted-average WACC multiplier for diagnostic display
    pre_wacc_total = upfront_with_cont + ongoing_with_cont + end_with_cont
    wacc_multiplier = total_cost / pre_wacc_total if pre_wacc_total > 0 else 1.0

    subtotal         = upfront_lines + ongoing_lines + end_lines
    contingency_cost = subtotal * contingency_fraction

    return {
        "launch_cost":           launch_cost,
        "tanker_cost":           tanker_cost,
        "tanker_flights":        float(tanker_flights),
        "autonomy_nre_cost":     autonomy_nre_cost,
        "mission_duration_yr":   mission_duration_yr,
        "outbound_prop_cost":    outbound_prop_cost,
        "return_prop_cost":      return_prop_cost,
        "hardware_cost":         hardware_cost,
        "mining_rig_cost":       mining_rig_cost,        # amortised portion
        "capsule_cost":          capsule_cost,           # per-mission portion
        "power_system_cost":     power_system_cost,      # beneficiation plant
        "ep_system_cost":        ep_system_cost,         # electric stage
        "tank_cost":             tank_cost,              # propellant tankage
        "tank_mass_kg":          tank_mass,
        "rig_terminal_value":    rig_terminal_value,
        "missions_sharing_rig":  float(missions_sharing_rig),
        "n_missions":            float(n_missions),
        "campaign_cadence_yr":   cadence,
        "programme_span_yr":     (mission_duration_yr
                                  + max(0, missions_sharing_rig - 1) * cadence),
        "programme_calendar_multiplier":        cal_cost,
        "programme_calendar_credit_multiplier": cal_credit,
        "learning_curve_factor": lc,
        "ops_cost":              ops_cost,
        "heat_shield_cost":      heat_shield_cost,
        "tps_mass_kg":           tps_mass,
        "recovery_cost":         recovery_cost,
        "liability_cost":        liability_cost,
        "licensing_cost":        licensing_cost,
        "launch_insurance_cost": launch_insurance_cost,
        "nre_cost":              nre_cost,
        "subtotal_cost":         subtotal,
        "contingency_cost":      contingency_cost,
        "upfront_cost":          upfront_with_cont,
        "ongoing_cost":          ongoing_with_cont,
        "end_of_mission_cost":   end_with_cont,
        "wacc_multiplier_upfront": mult_upfront,
        "wacc_multiplier_ongoing": mult_ongoing,
        "wacc_multiplier_end":     mult_end,
        "wacc_multiplier":         wacc_multiplier,      # weighted average
        "total_cost":            total_cost,
    }


def mission_cost_usd(
    mass_cascade:        Dict[str, float],
    vehicle:             Row,
    propellant:          Row,
    ops_df:              pd.DataFrame,
    config:              CalcConfig,
    mission_duration_yr: float,
    processing_power_w:  float = 0.0,
    stay_yr:             float = 0.0,
    isru_return:         Optional[bool] = None,
    ep_power_w:          float = 0.0,
    power_source:        str   = "solar",
    n_missions:          Optional[int] = None,
    missions_per_ship:   Optional[int] = None,
    cadence_yr:          Optional[float] = None,
    rig_trips:           Optional[Tuple[int, int, Optional[int]]] = None,
    totals_only:         bool = False,
) -> Union[Dict[str, float], float]:
    """Full mission cost breakdown for a given (mass cascade, vehicle, prop).

    Uncrewed autonomous mining mission, no crew cost line.

    v1.17.2: the body is split into `_mission_cost_prologue` (everything that
    does not move with programme size) and `_mission_cost_tail` (everything
    that does), because the programme ladder varies only `n_missions` and
    `missions_per_ship` and was re-deriving the other ~90% of the cascade for
    each of a median 40 options.  This function is their composition and is
    unchanged in signature, in behaviour and, the point of the exercise, in
    the exact floats it returns.  It remains the entry point for every caller
    that prices ONE programme; `_price_programme` builds the prologue itself.

    v1.3.2 accuracy fixes:
      • Heat-shield mass is now sourced from the rocket-eq cascade
        (mass_cascade["m_tps"]) instead of re-derived from payload only; 
        the m_tps in the cascade is what actually got launched.
      • Launch insurance now percent of (launch + hardware) = SPACECRAFT
        book value rather than (launch + gross_value of future revenue),
        matching how real launch insurance is underwritten.
      • Capsule (`return_vehicle_dry_kg`) now carries its own recurring
        manufacturing cost; previously only mining_hardware was costed.
      • WACC compounding is time-bucketed: upfront costs compound at
        (1+W)^T, ongoing (ops + ISRU prop) at (1+W)^(T/2), end-of-mission
        (recovery) at 1.0.  Previous all-to-end overstated time-cost ~5%.

    Takes no payload or gross-value argument.  It used to take both, and
    v1.3.2 left them stranded: the insurance rebasing above removed the only
    read of gross_value_usd, and sample recovery became a flat Module 3 ops
    lookup rather than a per-kg charge, removing the only read of
    payload_returned_kg.  Every cost here now derives from the mass cascade,
    the Module 3 reference tables, and config; nothing scales with the
    revenue the mission is projected to earn, which is the point.

    Line items (every value sourced from Module 3's reference tables):
        UPFRONT     - launch, outbound prop, return prop (if not ISRU),
                      mining-rig hardware (amortised), capsule (per mission),
                      heat shield, NRE (bus + autonomy, amortised),
                      licensing, liability and launch insurance (the last
                      two are 0.0 unless charge_insurance)
        ONGOING     - mission ops × duration_yr, ISRU return prop (if ISRU)
        END-OF-MISSION, sample recovery
        × (1 + contingency_fraction)
        × per-bucket (1 + WACC)^T_bucket        [time-value]
    """
    return _mission_cost_tail(
        _mission_cost_prologue(
            mass_cascade, vehicle, propellant, ops_df, config,
            mission_duration_yr, processing_power_w, stay_yr, isru_return,
            ep_power_w, power_source, cadence_yr, rig_trips),
        n_missions, missions_per_ship, totals_only)

# ─────────────────────────────────────────────────────────────────────────────
# (VEHICLE × PROPELLANT) EVALUATOR FOR ONE ASTEROID
# ─────────────────────────────────────────────────────────────────────────────
class AsteroidContext(NamedTuple):
    """Everything the mission search re-derives that depends only on the BODY.

    v1.14.1.  Every field here is a function of (asteroid × config) and of
    nothing else, not the vehicle, not the propellant, not the return mode, not
    the power source, not the concentration ratio, and every one of them was
    being recomputed inside `_evaluate_combo_at_ratio`, i.e. once per surviving
    candidate.  Profiled at cislunar that is 38,643 calls apiece for 200
    asteroids: `dark_period_hours`, `eclipse_effective_w_per_kg`,
    `solar_specific_power_w_per_kg` and `synodic_period_yr` re-answering the
    same question about the same rock ~190 times over.

    The membership test for this class is that last sentence, not the field
    count: if a quantity varies with the CANDIDATE it does not belong here, and
    if it varies only with the body it should.

    Same shape as v1.10.1's ops-constant memo and the dict-row conversion, and
    the same justification: the arithmetic is unchanged, so the output is
    unchanged, and it is the REPETITION that was costing.

    `ops` is `_ops_sizing_constants`' twelve-tuple, carried through rather than
    unpacked so that adding a Module 3 row does not have to touch this class.
    """
    mineable_kg:           float
    throughput_cap_kg:     float
    structure_frac:        float
    synodic_yr:            float
    window_wait_yr:        float
    ops:                   Tuple[float, ...]
    dark_frac:             float
    dark_h:                float
    dark_clamped:          bool
    solar_w_per_kg:        float
    plant_w_per_kg_solar:  float
    array_oversize_factor: float
    # v1.17.1.  The body's ice fraction, already resolved through the
    # absent/NaN check, so the raw arm of `_cargo_water_kg` stops paying a
    # `pd.isna` per candidate per pass of the sizing loop.  0.0 means "no
    # usable ice column", which multiplies out to the same 0.0 that branch
    # used to return early.
    cargo_ice_frac:        float


def asteroid_context(
    asteroid_row: Row,
    ops_df:       pd.DataFrame,
    config:       CalcConfig,
) -> Optional[AsteroidContext]:
    """Build the per-body constants for one asteroid, or None if it cannot fly.

    None means the row has no usable mass, which is the same thing
    `_evaluate_combo_at_ratio` used to report by returning None on every
    candidate in turn, so the caller bails on the whole asteroid instead of
    discovering it 673 times.
    """
    asteroid_mass = asteroid_row.get("estimated_mass_kg")
    if asteroid_mass is None or pd.isna(asteroid_mass) or asteroid_mass <= 0:
        return None

    ops = _ops_sizing_constants(ops_df)
    base_w_per_kg    = ops[2]
    dark_frac        = ops[7] if config.model_eclipse_power else 0.0
    storage_wh_per_kg, storage_eta, baseline_dark_h = ops[8], ops[9], ops[10]

    # The launch-window wait depends only on the target and the destination, but
    # it is part of the stay, and the stay is how long cryogenic return
    # propellant sits in the tank boiling off.
    a_dest_au = window_phasing_au(config.delivery_destination)
    synodic_yr = synodic_period_yr(asteroid_row.get("semi_major_axis_au"), a_dest_au)

    # The dark period belongs to the BODY.  `dark_clamped` is carried so that a
    # tumbler sized against the ceiling stays visible as such in the output.
    dark_h, dark_clamped = dark_period_hours(
        asteroid_row.get("rotation_period_h"), dark_frac,
        config.default_rotation_period_h, config.max_dark_period_h,
    )
    w_per_kg = solar_specific_power_w_per_kg(
        asteroid_row.get("semi_major_axis_au"), base_w_per_kg,
    )
    w_solar_eff, array_oversize_factor = eclipse_effective_w_per_kg(
        w_per_kg, dark_h, dark_frac,
        storage_wh_per_kg, storage_eta, baseline_dark_h,
    )

    ice_frac = asteroid_row.get("comp_ice_fraction")
    ice_frac = (0.0 if ice_frac is None or pd.isna(ice_frac)
                else float(ice_frac))

    return AsteroidContext(
        mineable_kg           = float(asteroid_mass) * config.max_mining_fraction,
        throughput_cap_kg     = max_payload_by_throughput_kg(config),
        structure_frac        = max(0.0, float(config.return_structure_frac_of_payload)),
        # Reported in full even when launch windows are switched off, which is
        # why it is carried separately from the wait it usually implies.
        synodic_yr            = synodic_yr,
        window_wait_yr        = 0.5 * synodic_yr if config.model_launch_windows else 0.0,
        ops                   = ops,
        dark_frac             = dark_frac,
        dark_h                = dark_h,
        dark_clamped          = dark_clamped,
        solar_w_per_kg        = w_per_kg,
        plant_w_per_kg_solar  = w_solar_eff,
        array_oversize_factor = array_oversize_factor,
        cargo_ice_frac        = ice_frac,
    )


def _evaluate_combo_at_ratio(
    asteroid_row:      Row,
    vehicle:           Row,
    propellant:        Row,
    bulk_value_per_kg: float,
    dv_out_m_s:        float,
    dv_ret_m_s:        float,
    ops_df:            pd.DataFrame,
    config:            CalcConfig,
    best_phase_value_per_kg: Optional[float] = None,
    phases:            Optional[List[Tuple[str, float, float]]] = None,
    target_ratio:      float = 1.0,
    beneficiate:       Optional[bool] = None,
    markets:           Optional[Dict[str, float]] = None,
    aero:              Optional[bool] = None,
    isru:              bool = False,
    rendezvous_apsis:  str = "",
    power_mode:        str  = "solar",
    ctx:               Optional[AsteroidContext] = None,
    market_mode:       Optional[str] = None,
) -> Optional[Dict[str, float]]:
    """Evaluate one (vehicle × propellant × architecture) mission for one asteroid.

    `aero` and `isru` are the return mode and the propellant-sourcing decision
    for THIS candidate mission; v1.10.0 made both per-asteroid searches rather
    than global config settings, so they arrive as arguments.  Passing
    aero=None falls back to what the config allows for the destination.

    Returns None if the mission is infeasible (zero return payload, no
    propellant to make, over the duration limit), or a full result dict
    including profit, ROI, $/kg returned, and the mass + cost cascades.
    """
    vconsts = vehicle.get(_VEHICLE_CONSTS_KEY)        # v1.17.6, see _vehicle_consts
    if vconsts is None:
        vconsts = vehicle[_VEHICLE_CONSTS_KEY] = _vehicle_consts(vehicle)
    leo_cap = vconsts[1]
    if leo_cap <= 0:
        return None
    if best_phase_value_per_kg is None:
        best_phase_value_per_kg = bulk_value_per_kg
    if phases is None:
        phases = []

    # ── Low-thrust Δv penalty (v1.4.0) ───────────────────────────────────────
    # Module 3 tags each propellant with the factor by which a real trajectory
    # exceeds the impulsive Δv budget.  Electric propulsion cannot fly the
    # impulsive burns the reference table assumes; it spirals, and spiralling
    # out of LEO costs roughly twice what an impulsive escape does.  Without
    # this, a 3,000 s Isp thruster wins the mass cascade on a Δv budget it
    # could never actually achieve.
    # ── Per-row constants (v1.14.2) ──────────────────────────────────────────
    # `candidate_combos` attaches these, but a caller that hand-builds `combos`
    # will not have.  Derived on demand in that case rather than defaulted; 
    # absent means unknown, not zero, and defaulting a tank fraction to zero
    # here would silently un-charge tankage, which is the quiet-wrong-answer
    # failure this repo keeps finding.
    sizing_consts = propellant.get(_SIZING_CONSTS_KEY)
    if sizing_consts is None:
        sizing_consts = _sizing_propellant_consts(propellant, config)
        propellant[_SIZING_CONSTS_KEY] = sizing_consts
    (dv_penalty, thruster_eff_row, thruster_kg_per_n_row,
     tank_frac, isp_s_val, boiloff_pct) = sizing_consts

    dv_out_m_s = dv_out_m_s * dv_penalty
    dv_ret_m_s = dv_ret_m_s * dv_penalty

    # v1.5.0: TPS only exists if this architecture actually enters an
    # atmosphere.  A cislunar delivery never does, so asking for aerocapture
    # there yields a propulsive capture and no heat-shield mass.
    # v1.10.0: which return mode this candidate flies is decided by the caller.
    if aero is None:
        aero = uses_tps(config)
    tps_frac = config.heat_shield_frac_of_payload if aero else 0.0

    # ── ISRU feasibility (v1.10.0) ───────────────────────────────────────────
    # Making return propellant is a property of the (asteroid × propellant)
    # pair, not a switch.  A candidate that asks for ISRU where the chemistry
    # does not close is not a mission.
    isru_feed_per_kg_prop = 0.0
    # Water actually baked out per kg of ISRU propellant.  v1.10.0 hardcoded
    # hydrolox's 1.286 everywhere this appeared, which was right while hydrolox
    # was the only ISRU route.  A steam rocket boils 1.00 kg per kg and a mass
    # driver bakes nothing at all, so the liberation energy has to follow the
    # propellant rather than a constant.
    isru_water_per_kg_prop = 0.0
    if isru:
        ratio = isru_feed_kg_per_kg_propellant(asteroid_row, propellant, config)
        if ratio is None:
            return None
        isru_feed_per_kg_prop = float(ratio)
        if propellant.get("isru_feed_material") == "water":
            isru_water_per_kg_prop = float(propellant.get("isru_feed_kg_per_kg") or 0.0)
        elif propellant.get("isru_feed_material") is None:
            isru_water_per_kg_prop = WATER_KG_PER_KG_HYDROLOX   # pre-v1.9.0 row

    # ── Per-body constants (v1.14.1) ─────────────────────────────────────────
    # Mineable mass, the throughput cap, the launch-window wait, the ops-table
    # constants, the dark period and the eclipse-corrected specific power are
    # all functions of (asteroid × config) alone.  They used to be derived here,
    # which meant re-deriving them for every candidate mission; see
    # `AsteroidContext` for the call counts.  `ctx` is built once per asteroid
    # by `evaluate_asteroid`; rebuilding it when a caller does not supply one
    # keeps this function usable on its own.
    if ctx is None:
        ctx = asteroid_context(asteroid_row, ops_df, config)
        if ctx is None:
            return None      # no usable mass; nothing to cap the payload with

    mineable_kg       = ctx.mineable_kg
    throughput_cap_kg = ctx.throughput_cap_kg
    structure_frac    = ctx.structure_frac
    synodic_yr        = ctx.synodic_yr
    window_wait_yr    = ctx.window_wait_yr

    # ── Power-plant feedback loop (v1.5.0, beneficiation only) ───────────────
    # The processing plant's array mass rides in the same rocket equation as
    # everything else, but its size depends on how much feed gets processed,
    # which depends on the payload, which depends on the array mass.  Solve
    # the fixed point instead of assuming it away.  Converges in 2-3 passes
    # because the array is a modest fraction of the rig.
    #
    # With beneficiation OFF no array mass is added at all; the existing
    # 2,000 kg rig figure already carries its own power implicitly, and this
    # keeps a default run bit-identical to v1.4.0.
    # The five `_`-prefixed slots are dead HERE and must still be unpacked; 
    # the tuple's order is the contract with `_ops_sizing_constants`.  They are
    # the eclipse inputs, and v1.14.1 moved the arithmetic that consumed them
    # onto `AsteroidContext` because it is per-BODY.  Read `ctx.dark_*` and
    # `ctx.plant_w_per_kg_solar` below rather than re-deriving from these.
    (dig_wh, benef_wh, _base_w_per_kg, ep_eff, ep_kg_per_kw,
     rtg_w_per_kg, ppu_only_kg_per_kw,
     _dark_frac_raw, _storage_wh_per_kg, _storage_eta, _baseline_dark_h,
     containment_per_kg) = ctx.ops
    # ── Eclipse / night-side power (v1.14.0) ─────────────────────────────────
    # The dark period belongs to the BODY, so it is resolved once per asteroid
    # rather than per candidate mission.  `dark_clamped` is reported so a
    # tumbler sized against the 72 h ceiling is visible as such.
    dark_frac    = ctx.dark_frac        # already zeroed if model_eclipse_power is off
    dark_h       = ctx.dark_h
    dark_clamped = ctx.dark_clamped
    # Solar for the electric-propulsion array always (see power_source_for_target
    # for why a radioisotope source cannot serve hundreds of kilowatts), and for
    # the processing plant until the loop below learns how much power it needs.
    #
    # v1.14.0: the PROCESSING plant is the one that stands in the body's shadow.
    # The EP array does not; it is in interplanetary cruise, in permanent
    # sunlight, so `ep_w_per_kg` keeps the bare 1/r² figure and only the plant
    # takes the night-side penalty.
    w_per_kg              = ctx.solar_w_per_kg
    ep_w_per_kg           = w_per_kg
    w_solar_eff           = ctx.plant_w_per_kg_solar
    array_oversize_factor = ctx.array_oversize_factor
    plant_w_per_kg = w_solar_eff
    power_source   = "solar"

    # ── The power source is a SEARCHED architecture choice (v1.14.0) ─────────
    # It used to be resolved inside the sizing loop by `power_source_for_target`,
    # on MASS alone; take whichever of photovoltaic and radioisotope is lighter
    # at this distance.  That is not the objective this module reports, and the
    # two differ by 625× in price per watt ($500,000 against $800), so the model
    # was buying a nine- or ten-figure radioisotope plant to save array mass and
    # nothing ever asked whether that paid.
    #
    # It went unnoticed because it was unreachable: on v1.12.0 the branch fired
    # on ONE row of 15,566.  Adding the eclipse term makes photovoltaics roughly
    # half as good per kilogram, which moves the crossover from 3.46 AU to about
    # 2.1 AU and puts a third of the catalog on the nuclear side, at which point
    # a mass-only choice is charging a median $1.5B plant, 14% of mission cost,
    # decided by a criterion that cannot see dollars.
    #
    # So it joins the per-asteroid search, exactly as CLAUDE.md requires of any
    # new architecture axis, and `selection_key` resolves it against the same
    # objective as everything else.  `power_mode` is now an instruction, not a
    # question: "rtg" means fly a radioisotope plant or report infeasible, which
    # keeps the two candidates genuinely distinct and leaves solar as the
    # always-available fallback.
    if power_mode == "rtg":
        if rtg_w_per_kg <= 0:
            return None
        plant_w_per_kg = rtg_w_per_kg
        power_source   = "rtg"

    # `beneficiate` lets the caller price a NON-concentrating mission even
    # when the run has beneficiation enabled, so evaluate_combo can offer
    # "just scoop and go" as one of the options it chooses between.
    if beneficiate is None:
        beneficiate = config.use_beneficiation
    if not beneficiate:
        target_ratio = 1.0

    # ── Electric propulsion sizing (v1.7.0) ──────────────────────────────────
    # An electric stage is not a chemical stage with better Isp; it needs a
    # power plant proportional to how fast you want the propellant burnt, and
    # that plant is mass in the same rocket equation.  Sized to finish its
    # thrusting inside ep_target_thrust_yr.  Module 3 tags electric
    # propellants with dv_penalty_factor > 1.
    is_electric = (config.model_low_thrust_time and dv_penalty > 1.0)

    # ── The DEVICE, as distinct from the propellant (v1.12.0) ────────────────
    # Two per-technology figures from Module 3's `_THRUSTER_SYSTEMS`, and the
    # reason they are per-technology rather than one shared constant is that
    # sharing constants is exactly how this went wrong.  Every electric row
    # used to take efficiency 0.60 and a lumped 8 kg/kW, so a pulsed plasma
    # thruster, 8% efficient, 5,000 kg of hardware per newton, was priced
    # identically to a gridded ion engine at 70% and 54 kg/N.  A third of the
    # winning missions in a full cislunar run were PPT.
    #
    # Both fall back to the old shared constants when the column is absent, so
    # a pre-Module-3-v1.10.0 catalog reproduces v1.11.0.  `schema_check()`
    # names them, because the fallback is silent and flattering.
    # v1.14.2: both figures are parsed once per run by
    # `_sizing_propellant_consts`, which reports None where the row states no
    # usable value, so the fallback to Module 3's shared constants is unchanged
    # and a pre-Module-3-v1.10.0 catalog still reproduces v1.11.0.
    # v1.17.4: resolved by `_ep_device_consts`, which the pre-filter's second
    # stage reads too.  ONE definition, two readers; see that function.
    eff_used, thruster_kg_per_n, ppu_kg_per_kw = _ep_device_consts(
        is_electric, thruster_eff_row, thruster_kg_per_n_row,
        ep_eff, ep_kg_per_kw, ppu_only_kg_per_kw,
    )

    # `isp_s_val`, `boiloff_pct` and `tank_frac` all arrive on `sizing_consts`.
    # ── Tankage (v1.11.0) ────────────────────────────────────────────────────
    # Module 3 quotes tank mass per LITRE, because that is what it scales with;
    # the cascade wants it per kilogram of propellant, so divide by density.
    # A propellant row predating Module 3 v1.9.0 has neither column and comes
    # through as 0.0, which reproduces v1.10.1 exactly.
    #
    # ISRU is exempt from boil-off; the propellant is made at the asteroid on
    # departure rather than held from launch.
    models_boiloff = (config.model_propellant_boiloff and boiloff_pct > 0
                      and not isru)

    # ── Coupled sizing loop ──────────────────────────────────────────────────
    # Six quantities depend on one another in a ring, and none of them can be
    # solved first:
    #
    #   payload → return propellant → ISRU feed ─┐
    #      ↑                                     ↓
    #   array mass ← power ← dig time ← total feed
    #      └──────── hold time → boil-off → effective return Δv ───┘
    #
    # Fixed-point iteration solves the ring rather than assuming any leg of it
    # away.  It converges in a handful of passes because each feedback term is
    # a modest fraction of the mass it feeds back into.
    #
    # v1.10.0 pulled two more terms inside this loop.  Boil-off used to be
    # computed once, before the loop, against a hold time that assumed the
    # shortest stay the model allows (station_keeping_floor_yr, 0.25 yr), but
    # the stay is dig time plus the launch-window wait, which together run to
    # YEARS on the targets that most want a cryogenic upper stage.  Hydrolox at
    # 0.05%/day over a 4-year hold loads 2.1x what the rocket equation burns,
    # against the 1.1x the old estimate implied.  The ISRU feed is new for the
    # same reason: it is rock that has to be dug, and dug rock is time.
    #
    # v1.14.0 adds a seventh leg, VOLATILE CONTAINMENT.  A sealed shaded hold
    # scales with the water in the cargo, the water in the cargo comes out of
    # the payload knapsack, and the knapsack is solved against a payload the
    # containment mass helps determine.  Same ring, one more term, and it is
    # handled the same way rather than estimated once outside the loop, which
    # is the mistake v1.12.0 found in the cargo-water array.
    power_system_kg = 0.0
    ep_system_kg    = 0.0
    ep_power_watts  = 0.0
    ep_thrust_yr    = 0.0
    ep_thrust_n     = 0.0
    processing_power_watts = 0.0
    isru_feed_kg    = 0.0
    isru_prop_kg    = 0.0
    dv_ret_eff      = dv_ret_m_s
    boiloff_factor  = 1.0
    stay_est_yr     = config.station_keeping_floor_yr + window_wait_yr
    outbound_yr     = max(0.5, 0.000_23 * dv_out_m_s)
    # Containment rides as an addition to the return vehicle's payload-scaling
    # structure, which is exactly what it is; the hopper holds the cargo, the
    # seal and the shade keep the volatile fraction of it from leaving.  Folding
    # it into `structure_frac` means the closed-form solver carries it with no
    # change to the algebra: it is already the f in (1 + f).
    containment_frac = 0.0
    structure_frac_eff = structure_frac
    # v1.17.1: a Module 3 constant, resolved once instead of once per pass of
    # the loop below AND again at the settle-up.  One lookup, two readers, 
    # the same shape as `tank_frac` in v1.14.2, and for the same reason.
    water_wh = _ops_value(
        ops_df, "Water liberation energy (bound water)", default=2_500.0,
    )
    cascade = None
    for _ in range(12):
        # Boil-off, folded into an EFFECTIVE return Δv: since m_return_prop
        # scales with (R_ret − 1), inflating that term by k is exactly
        # R_eff = 1 + (R_ret − 1)·k, and dv_eff = Isp·g0·ln(R_eff) leaves the
        # closed-form cascade untouched and exact.
        if models_boiloff:
            hold_yr = outbound_yr + stay_est_yr
            boiloff_factor = math.exp(boiloff_pct / 100.0 * hold_yr * 365.25)
            r_ret_raw = math.exp(dv_ret_m_s / (isp_s_val * G0_M_S2))
            r_ret_eff = 1.0 + (r_ret_raw - 1.0) * boiloff_factor
            dv_ret_eff = isp_s_val * G0_M_S2 * math.log(r_ret_eff)

        cascade = max_return_payload_kg(
            leo_capacity_kg = leo_cap,
            isp_s           = isp_s_val,
            dv_out_m_s      = dv_out_m_s,
            dv_ret_m_s      = dv_ret_eff,
            hardware_kg     = config.mining_hardware_kg + power_system_kg + ep_system_kg,
            dry_return_kg   = config.return_vehicle_dry_kg,
            tps_frac        = tps_frac,
            isru_return     = isru,
            structure_frac  = structure_frac_eff,
            tank_frac       = tank_frac,
        )
        if not cascade["viable"]:
            return None

        new_ep_kg = 0.0
        if is_electric:
            # v1.17.4: one definition, two readers, the pre-filter's second
            # stage sizes the same stage off the same pass-1 cascade.
            (new_ep_kg, ep_power_watts,
             ep_thrust_n, ep_thrust_yr) = _ep_stage_kg(
                cascade, isp_s_val, eff_used, ep_w_per_kg,
                ppu_kg_per_kw, thruster_kg_per_n, config,
            )

        # Propellant made on site is dug before it is burnt, so it takes its
        # share of the rig's throughput before any ore does.
        trial_payload = min(cascade["max_payload_kg"], mineable_kg,
                            max(0.0, throughput_cap_kg - isru_feed_kg))
        if trial_payload <= 0:
            return None
        new_isru_feed = 0.0
        new_isru_prop = 0.0
        if isru:
            r_ret = cascade["r_ret"]
            new_isru_prop = ((trial_payload
                              + config.return_vehicle_dry_kg
                              + structure_frac_eff * trial_payload)
                             * (1.0 + tps_frac) * (r_ret - 1.0))
            new_isru_feed = new_isru_prop * isru_feed_per_kg_prop
            if new_isru_feed >= throughput_cap_kg or new_isru_feed >= mineable_kg:
                return None       # the rig cannot dig its own fuel in the time

        trial_feed = (min(trial_payload * target_ratio,
                          max(0.0, throughput_cap_kg - new_isru_feed),
                          max(0.0, mineable_kg - new_isru_feed))
                      if beneficiate else trial_payload)
        trial_dur = max(mining_duration_yr(trial_feed + new_isru_feed, config),
                        config.station_keeping_floor_yr)

        new_power_kg = power_system_kg
        # The dig / concentrate draw is raised only when there is a processing
        # plant to raise it for, with beneficiation off, the 2,000 kg rig's
        # own power is already implicit in its $/kg recurring rate, which is
        # what keeps a raw run identical to v1.4.0.  Water LIBERATION is not
        # covered by that: baking 25 t of water out of phyllosilicate at
        # 2,500 Wh/kg is kilowatts the rig was never sized for, and the cost
        # model has always charged it.  So the draw below is computed whenever
        # either term is non-zero, and the array is sized from the total.
        processing_power_watts = 0.0
        if beneficiate or isru:
            processing_power_watts = processing_power_w(
                trial_feed + new_isru_feed,
                trial_payload if beneficiate else 0.0,
                trial_dur, dig_wh, benef_wh,
            )
        # ── Cargo water, needed by TWO terms as of v1.14.0 ───────────────────
        # The water in the hold sets the liberation energy (and so the array)
        # AND the sealed-hold containment mass (and so the return vehicle's
        # structure).  Computed once per pass and used by both, for the same
        # reason `_cargo_water_kg` exists at all: two expressions for the same
        # quantity is precisely how v1.12.0 ended up charging for an array it
        # never flew.  The knapsack call is the expensive part of this loop, so
        # it is also the reason to compute it once rather than twice.
        need_cargo_water = (config.model_water_liberation
                            or (config.model_volatile_containment
                                and containment_per_kg > 0))
        trial_cargo_water = (
            _cargo_water_kg(asteroid_row, phases, trial_payload, trial_feed,
                            beneficiate, config, ctx.cargo_ice_frac)
            if need_cargo_water else 0.0
        )
        # Containment scales with the VOLATILE fraction of the cargo, so it is
        # a payload-proportional term exactly like the ore restraint it sits on
        # top of, which is what lets it fold into structure_frac and leaves the
        # closed-form solver's algebra untouched.
        new_containment_frac = 0.0
        if config.model_volatile_containment and trial_payload > 0:
            new_containment_frac = (containment_per_kg
                                    * min(1.0, trial_cargo_water / trial_payload))

        if trial_dur > 0 and config.model_water_liberation:
            # Baking water out of rock, on top of digging it.  Two sources and
            # they are charged at the same rate: the water turned into ISRU
            # propellant, and the water sold as CARGO.
            #
            # v1.12.0: the cargo half used to be added AFTER this loop had
            # already sized and flown the array, so its array mass was priced
            # in the ledger and never entered the rocket equation, the mirror
            # image of the free-EP-stage bug, and the comment there asserted
            # the cascade had already flown it.  It had not: `power_system_kg`
            # came out 0.8-2.7% above the figure inside `hardware_total_kg` on
            # every row that liberated cargo water.  Sizing it here closes the
            # loop the same way every other feedback term in this ring is
            # closed, and it is why the term is no longer gated on
            # `beneficiate or isru`, a RAW mission to an icy body liberates
            # cargo water too, and used to pay for that array without flying
            # any of it.
            trial_water = (new_isru_prop * isru_water_per_kg_prop
                           if isru else 0.0)
            trial_water += trial_cargo_water
            if trial_water > 0:
                processing_power_watts += (
                    water_wh * trial_water / (trial_dur * 365.25 * 24.0)
                )

        if processing_power_watts > 0:
            # v1.14.0: the SOURCE is fixed by `power_mode` before the loop, so
            # all that remains inside it is the Pu-238 ceiling, and that is a
            # hard constraint, not a preference.  DOE production is ~1.5 kg/yr,
            # about one flagship RTG a year for the entire world, so a plant
            # over the cap is not expensive, it is unavailable.  Reporting the
            # candidate infeasible is what makes that honest; the solar
            # candidate for the same body is evaluated alongside and survives.
            if power_source == "rtg" and processing_power_watts > config.rtg_max_power_w:
                return None
            new_power_kg = (processing_power_watts / plant_w_per_kg
                            if plant_w_per_kg > 0 else 0.0)
        else:
            new_power_kg = 0.0

        new_stay_yr = trial_dur + window_wait_yr
        converged = (
            abs(new_power_kg - power_system_kg) <= 0.01 * max(new_power_kg, 1.0)
            and abs(new_ep_kg - ep_system_kg) <= 0.01 * max(new_ep_kg, 1.0)
            and abs(new_isru_feed - isru_feed_kg) <= 0.01 * max(new_isru_feed, 1.0)
            and abs(new_stay_yr - stay_est_yr) <= 0.01 * max(new_stay_yr, 1.0)
            # Containment is a fraction, not a mass, so its convergence test is
            # absolute rather than relative: 1e-4 of a payload-scaling term is
            # far below anything that moves a reported number.
            and abs(new_containment_frac - containment_frac) <= 1e-4
        )
        power_system_kg, ep_system_kg = new_power_kg, new_ep_kg
        isru_feed_kg, isru_prop_kg    = new_isru_feed, new_isru_prop
        stay_est_yr                   = new_stay_yr
        containment_frac              = new_containment_frac
        structure_frac_eff            = structure_frac + containment_frac
        if converged:
            break

    if cascade is None or not cascade["viable"]:
        return None
    hardware_total_kg = config.mining_hardware_kg + power_system_kg + ep_system_kg

    # ── Volume cap ───────────────────────────────────────────────────────────
    # Cargo volume = payload mass / bulk density.  Asteroid bulk density
    # (Module 1) is a fair proxy for the mined material's packing density
    # since the user spec'd "uniform composition".  A return capsule occupies
    # a fraction of the fairing, say 25%, when sharing the vehicle with
    # mission hardware and propellant tanks.
    #
    # This rarely binds (a tonne of metal is < 0.2 m³ against an ~80 m³
    # fairing floor) but it is the constraint that keeps the mission physical
    # when the launch-mass constraint goes slack: with ISRU return propellant
    # AND propulsive return (tps_frac = 0), nothing in the rocket equation
    # scales with payload, so max_return_payload_kg legitimately reports an
    # unbounded mass budget.  Left uncapped, `mineable_kg` alone bound the
    # result and a 30 km body returned 7.4e14 kg in a 500 kg capsule for a
    # $7.8e17 "profit" that topped the rankings.  Volume was already computed
    # and compared here, but only as a reported flag; it now binds.
    bulk_density = asteroid_row.get("density_gcm3")
    if bulk_density is None or pd.isna(bulk_density) or float(bulk_density) <= 0:
        bulk_density = 2.0    # default: rocky-asteroid average
    bulk_density_kg_per_L = float(bulk_density)         # g/cm³ ≡ kg/L

    vconsts = vehicle.get(_VEHICLE_CONSTS_KEY)        # v1.14.2, see candidate_combos
    if vconsts is None:
        vconsts = vehicle[_VEHICLE_CONSTS_KEY] = _vehicle_consts(vehicle)
    fairing_m3 = vconsts[0]
    usable_return_m3   = 0.25 * fairing_m3
    volume_capacity_kg = usable_return_m3 * 1000.0 * bulk_density_kg_per_L

    # `volume_fits` keeps its original sense; False means the payload the
    # mission would otherwise have returned does not fit, but the payload is
    # now actually reduced to what does fit.
    # ── Throughput cap (v1.4.0) ──────────────────────────────────────────────
    # You can only return what the rig can actually dig inside the maximum
    # stay.  Previously extraction was instantaneous and unbounded, so a
    # mission's haul was limited only by the rocket equation; the rig might
    # as well have been a vacuum cleaner with infinite suction.
    # v1.5.0: with beneficiation on, the throughput cap bounds the FEED the rig
    # digs, not the payload it flies home; that is the whole point of
    # concentrating.  With it off the semantics are unchanged: throughput caps
    # the payload directly.
    # v1.10.0: propellant made on site is dug from the same rock by the same
    # rig, so it comes off both budgets before any ore is loaded.  That is the
    # cost of ISRU, and it is the part the old flat $50/kg charge left out.
    ore_throughput_kg = max(0.0, throughput_cap_kg - isru_feed_kg)
    ore_mineable_kg   = max(0.0, mineable_kg - isru_feed_kg)

    m_payload_demand = min(cascade["max_payload_kg"], ore_mineable_kg)
    volume_fits      = m_payload_demand <= volume_capacity_kg
    throughput_fits  = m_payload_demand <= ore_throughput_kg
    if beneficiate:
        m_payload = min(m_payload_demand, volume_capacity_kg)
    else:
        m_payload = min(m_payload_demand, volume_capacity_kg, ore_throughput_kg)
    if m_payload <= 0:
        return None

    # ── Beneficiation mass balance ───────────────────────────────────────────
    # Concentrate exactly as far as it pays, and no further.  Once the
    # concentrate reaches the purity bound, 100% of the best phase present, 
    # additional feed buys nothing: the delivered $/kg is already capped, while
    # the extra rock still costs dig time, energy, array mass and WACC.  A real
    # operator stops there, so the model does too.
    #
    #     ratio_to_saturate = best_phase / (bulk x recovery)
    #
    # then bounded by the safety cap, by what the rig can dig in the time
    # allowed, and by what the body can supply.  Where bulk value already
    # equals the best phase (a monomineralic body, pure ice, say) this
    # collapses to 1.0 and beneficiation correctly becomes a no-op.
    if beneficiate:
        feed_kg = min(m_payload * target_ratio, ore_throughput_kg, ore_mineable_kg)
        feed_kg = max(feed_kg, m_payload)          # never less feed than product
        concentration_ratio = feed_kg / m_payload if m_payload > 0 else 1.0
        throughput_fits = feed_kg <= ore_throughput_kg
    else:
        feed_kg = m_payload
        concentration_ratio = 1.0

    return_volume_m3 = m_payload / bulk_density_kg_per_L / 1000.0

    # Recompute the full cascade at the capped payload.  TPS, return-prop,
    # outbound-prop, launch all depend on m_payload, must be redone to
    # reflect the actual mission, not the rocket-eq theoretical max.
    r_ret           = cascade["r_ret"]
    r_out           = cascade["r_out"]
    # ── Settle volatile containment at the payload actually flown (v1.14.0) ──
    # The loop capped the payload by the body's mass and by rig throughput, but
    # the VOLUME cap above can cut it further, and the knapsack's water fraction
    # moves with the payload.  Settled here, before anything downstream reads
    # the structure fraction, for the same reason the power plant is settled
    # below: the mission that gets priced has to be the mission that gets flown.
    cargo_water_kg = 0.0
    if config.model_water_liberation or (config.model_volatile_containment
                                         and containment_per_kg > 0):
        cargo_water_kg = _cargo_water_kg(
            asteroid_row, phases, m_payload, feed_kg, beneficiate, config,
            ctx.cargo_ice_frac,
        )
    containment_frac = 0.0
    if config.model_volatile_containment and m_payload > 0:
        containment_frac = containment_per_kg * min(1.0, cargo_water_kg / m_payload)
    structure_frac_eff = structure_frac + containment_frac
    # v1.10.0: the return vehicle grows with what it carries; see
    # return_structure_frac_of_payload.  v1.14.0 adds the sealed shaded hold for
    # whatever fraction of that cargo is water, which is most of it on the
    # bodies this model likes.
    m_dry_return    = config.return_vehicle_dry_kg + structure_frac_eff * m_payload
    m_containment_kg = containment_frac * m_payload
    m_tps           = tps_frac * (m_payload + m_dry_return)
    # v1.11.0: the same two tankage scalars the solver used, read back rather
    # than re-derived.  k_ret = 1/(1 − t(R_ret−1)) inflates the post-burn mass
    # by the tank that flies home inside it; k_out does the same on the
    # outbound leg for the tank that is staged at the asteroid.  Both are 1.0
    # when model_tank_mass is off, which leaves this block identical to v1.10.1.
    k_ret_c         = float(cascade.get("k_ret", 1.0))
    k_out_c         = float(cascade.get("k_out", 1.0))
    m_after_return  = k_ret_c * (1.0 + tps_frac) * (
        m_payload * (1.0 + structure_frac_eff) + config.return_vehicle_dry_kg)
    m_return_prop   = m_after_return * (r_ret - 1.0)
    m_tank_return   = tank_frac * m_return_prop

    def _downstream_of_hardware(hardware_kg: float):
        """Everything from the asteroid outwards, given the hardware delivered.

        Only the pieces that depend on `hardware_kg`, the payload, the return
        vehicle, its heat shield and its tank are all fixed by m_payload above.
        Factored out because it has to be evaluated TWICE: once to learn how
        much ISRU propellant the mission makes (which sets the dig time, which
        sets the power plant, which is itself hardware), and once more with the
        settled plant mass.  Two hand-written copies of this arithmetic drifting
        apart is precisely how a mass ends up in the rocket equation without a
        matching entry in the ledger.
        """
        # The return TANK is launched from Earth even under ISRU; you can make
        # propellant at an asteroid, not a pressure vessel, so it is inside
        # m_at_asteroid in both branches, and only the propellant drops out.
        at_asteroid = (hardware_kg + m_dry_return + m_tps + m_tank_return
                       + (0.0 if isru else m_return_prop))
        out_prop    = at_asteroid * k_out_c * (r_out - 1.0)
        tank_out    = tank_frac * out_prop
        return at_asteroid, out_prop, tank_out, at_asteroid + tank_out + out_prop

    # Settle the ISRU books at the payload actually flown, so the reported feed
    # and the dig time below describe the same mission the cost model prices.
    if isru:
        isru_prop_kg = m_return_prop
        isru_feed_kg = isru_prop_kg * isru_feed_per_kg_prop
        if isru_feed_kg + feed_kg > throughput_cap_kg + 1e-6:
            return None
    isru_water_kg = isru_prop_kg * isru_water_per_kg_prop if isru else 0.0

    # ── Settle the power plant against the mission actually flown (v1.12.0) ──
    # The sizing loop caps the payload by the body's mass and by rig throughput
    # but not by return-capsule VOLUME, and it estimates the ISRU feed before
    # the final cascade fixes it.  Both are now known, so the plant is
    # re-derived here, and, critically, the cascade is rebuilt afterwards from
    # the result.
    #
    # Until v1.12.0 this ran ~60 lines further down, after `actual_cascade` had
    # already been built.  The array for baking CARGO water was therefore
    # priced in the ledger and never launched: `power_system_kg` came out
    # 0.8-2.7% above the figure inside `hardware_total_kg` on every row that
    # liberated any, and a raw mission to an icy body paid for an array it flew
    # none of.  The comment there claimed "the cascade already flew" it.  It
    # had not.  This is the same asymmetry as the free EP stage, pointing the
    # other way, a price with no mass rather than a mass with no price.
    mining_yr = mining_duration_yr(feed_kg + isru_feed_kg, config)
    processing_power_watts = 0.0
    if beneficiate or isru:
        processing_power_watts = processing_power_w(
            feed_kg + isru_feed_kg, m_payload if beneficiate else 0.0,
            mining_yr, dig_wh, benef_wh,
        )
    water_kg = isru_water_kg
    if config.model_water_liberation:
        # v1.14.0: `cargo_water_kg` was settled above, at this same payload and
        # feed, to size the containment.  Reused rather than recomputed: one
        # quantity, one expression, and one (expensive) knapsack call.
        water_kg += cargo_water_kg
    if water_kg > 0 and mining_yr > 0:
        processing_power_watts += (
            water_wh * water_kg / (mining_yr * 365.25 * 24.0)
        )
    if processing_power_watts > 0:
        # The settled draw is the one that has to fit under the Pu-238 ceiling,
        # since the liberation term is a real addition to it.  Re-checked here
        # rather than trusted from the loop, because the loop sized against an
        # estimated payload and this is the payload actually flown.
        if power_source == "rtg" and processing_power_watts > config.rtg_max_power_w:
            return None
        power_system_kg = (processing_power_watts / plant_w_per_kg
                           if plant_w_per_kg > 0 else 0.0)
    else:
        power_system_kg = 0.0
    hardware_total_kg = config.mining_hardware_kg + power_system_kg + ep_system_kg

    (m_at_asteroid, m_outbound_prop,
     m_tank_outbound, m_launch) = _downstream_of_hardware(hardware_total_kg)
    # The cascade solved the payload against the loop's hardware estimate.  If
    # settling the plant made the hardware HEAVIER, the launch stack has to be
    # rechecked against the vehicle; the closed-form guarantee only holds at
    # the mass it was solved for.
    if m_launch > leo_cap:
        return None

    actual_cascade = {
        "max_payload_kg":  m_payload,
        "viable":          True,
        "r_out":           r_out,
        "r_ret":           r_ret,
        "m_launch":        m_launch,
        "m_outbound_prop": m_outbound_prop,
        "m_return_prop":   m_return_prop,
        "m_at_asteroid":   m_at_asteroid,
        "m_tps":           m_tps,
        "m_dry_return":    m_dry_return,
        "m_tank_return":   m_tank_return,
        "m_tank_outbound": m_tank_outbound,
    }

    # ── Delivered $/kg, the best load assemblable from this rock ────────────
    # Not "go and fetch platinum": fill the hold with the most valuable phases
    # the target actually contains, in whatever ratio maximises the load.  The
    # two honest bounds fall out of the knapsack automatically; you cannot
    # load more of a phase than the processed feed contained (content), and
    # once the hold is pure best-phase there is nothing better to add (purity).
    if beneficiate and phases:
        mix = optimal_payload_mix(
            m_payload, feed_kg, phases, config.beneficiation_recovery,
        )
        delivered_value_per_kg = float(mix["usd_per_kg"])
        gross_value            = float(mix["value_usd"])
        payload_mix            = mix["mix_kg"]
        dominant_phase         = mix["dominant_phase"]
        dominant_frac          = float(mix["dominant_frac"])
    else:
        delivered_value_per_kg = bulk_value_per_kg
        gross_value            = m_payload * bulk_value_per_kg
        payload_mix            = {}
        dominant_phase         = None
        dominant_frac          = 0.0

    # Time is charged on the FEED, not the product: the rig has to dig all
    # of it, and that stay time flows into ops cost and WACC.  ISRU feed counts,
    # propellant made on site is rock the same rig had to move.
    # (`mining_yr` was computed above, where the power plant was settled; it
    # depends only on the feed, which the cascade rebuild does not change.)

    # The launch-window wait was computed above the sizing loop (it depends
    # only on the target and the destination) because it is part of the stay,
    # and the stay is how long cryogenic propellant sits in the tank.
    stay_yr = mining_yr + window_wait_yr

    mission_duration_yr = asteroid_mission_duration_yr(
        dv_out_m_s, dv_ret_m_s, config, mining_yr=stay_yr,
    )
    # ── Low-thrust cruise (v1.7.0) ───────────────────────────────────────────
    # The Δv-linear cruise estimate is calibrated to chemical transfers.  An
    # electric stage thrusts for most of the trip instead, so its duration is
    # governed by burn time, not by an impulsive-transfer fit.
    if is_electric and ep_thrust_yr > 0:
        mission_duration_yr = max(mission_duration_yr, ep_thrust_yr + stay_yr)
    if mission_duration_yr > config.max_mission_duration_yr:
        return None                     # not a mission, a bequest

    # ── Bound-water liberation (v1.7.0) ──────────────────────────────────────
    # C/B/D-type "ice" is water locked into phyllosilicates.  Selling it as
    # water means baking it out at ~700 K first, and that energy was free
    # until now.  Charged on the water actually delivered, on top of the
    # mechanical-separation energy above.
    #
    # v1.10.0: and on the water turned into propellant, which is the same bake
    # for the same reason.  ISRU that pays no liberation energy is ISRU that
    # boils water out of rock for free.
    #
    # Both terms, and the array they size, were settled above, before the
    # cascade was rebuilt, so that the plant in the ledger is the plant in the
    # rocket equation.  `water_kg` is carried down here only to be reported.
    # ── PROGRAMME SCALE AND FLEET SIZE (v1.15.0) ─────────────────────────────
    # Everything above this line is the MASS CASCADE, and none of it depends on
    # how many missions the programme flies.  N enters this module in exactly
    # three places downstream: the cost model, market saturation and
    # reliability growth, and in none of the rocket equation, the fixed-point
    # power solve, the payload knapsack or the concentration sweep.
    #
    # That asymmetry is what makes programme size affordable to SEARCH rather
    # than merely to set: the expensive half of the mission is solved once, and
    # every rung of the fleet ladder is priced off the same cascade.  Running
    # the whole pipeline again at another N, which is how every
    # programme-scale figure in this project was produced, re-solves all of it
    # to change three numbers.
    #
    # See `programme_options` for the search's shape: a LADDER over fleet size
    # crossed with an EXHAUSTIVE enumeration of campaigns-per-ship.  v1.15.0
    # searched fleet size alone, on the argument that the optimum N is always a
    # whole multiple of the rig's trip life; v1.16.0 retires that argument,
    # because programme calendar time is a lever that pushes back inside a band.
    rig_trips        = rig_trips_per_ship(ops_df, config, stay_yr)
    trips_per_ship   = rig_trips[0] if rig_trips is not None else 0
    rig_calendar_cap = rig_trips[1] if rig_trips is not None else 0
    rig_trip_cap     = rig_trips[2] if rig_trips is not None else None
    # v1.16.0.  How often the rig can start again, the dig, unless windows open
    # more slowly than it digs.  Derived once here because it depends on the
    # stay, which is a property of this candidate, and it is read by every rung
    # of the programme search below.
    cadence_yr       = campaign_cadence_yr(stay_yr, synodic_yr, config)

    # ── Market saturation (v1.7.0, programme-aware v1.14.0) ──────────────────
    # The saleable mix and its prices do not depend on the programme either, so
    # they are assembled once, outside the ladder.
    #
    # ⚠️  Built by iterating `sold` in its own insertion order, and accumulated
    # in that same order inside the loop below.  Floating-point addition is not
    # associative and every verification this project relies on is a
    # bit-identity check, so the ORDER of these terms is load-bearing, the same
    # trap documented at length in `optimal_payload_mix`.
    #
    # v1.21.0.  Two market models reach this block and they share everything
    # above the ladder.  `elasticity` is the v1.14.0 term unchanged, and its
    # gate is the same boolean it always was, which is what lets it reproduce
    # the v1.14.0 curve, which reproduced v1.14.0 to v1.20.0 exactly until
    # v1.21.1's residual ceiling moved the two raw cells.
    # `capacity_cap` holds price flat and clips quantity instead.  The other
    # two models (`single_mission`, `unbounded`) price nothing here at all.
    # v1.21.0.  Resolved by the CALLER on the hot path and derived here only
    # when this function is used on its own.  It is a per-RUN config value, and
    # asking for it per candidate cost ~47 s of a full beneficiated cell: 332
    # calls per evaluable row, ~216 M over a catalog, to re-derive one of four
    # answers.  Threaded exactly like `markets`, which is per-run for the same
    # reason.  Defect class 3, and it was introduced by this release rather
    # than found in it.
    if market_mode is None:
        market_mode = _market_mode(config)
    market_ready       = bool(mission_duration_yr > 0
                              and phases and markets is not None)
    saturation_applies = bool(market_ready and market_mode == "elasticity")
    capacity_applies   = bool(market_ready and market_mode == "capacity_cap")
    # v1.22.0.  Resolved once per candidate, next to the mode it belongs to and
    # for the same reason: it is a per-RUN config value, and the ladder below
    # asks the capacity branch for it ~40 times per candidate.  0.0 is the
    # v1.21.0 wall, and both the raw sale and the knapsack take it as "no
    # surplus tier", so the flag is expressed entirely as a number and neither
    # of them has to branch on a boolean.
    #
    # 🚨  CLAMPED TO [0, 1], AND THE UPPER HALF IS LOAD-BEARING RATHER THAN
    # TIDY.  The tiered walk identifies a phase's full-price tier as "the
    # first time this phase is reached", which is only the same question as
    # "the dearer of its two tiers" while the discount is at most full price.
    # Above 1.0 the sort puts the DISCOUNTED tier first, so it draws the
    # market allowance and the full-price remainder does not -- and the load
    # comes out worth more than the uncapped one, which inverts the invariant
    # check 7 exists to enforce.  Measured before this clamp: at 1.5 a load
    # worth 900,000 uncapped priced at 945,000 capped.
    #
    # `build_profitability_catalog` REFUSES an out-of-range value outright, so
    # in a normal run this clamp never fires; it is here because a harness can
    # reach this function without going through that check, and a silently
    # inverted invariant is the worst failure this module has.
    surplus_frac = (min(1.0, max(0.0, float(config.surplus_price_fraction)))
                    if config.sell_surplus_at_discount else 0.0)
    # v1.21.2: (kg, price, ceiling_kg_per_yr, market_key).  The key is what
    # lets every consumer below pool phases that sell into ONE market; see
    # `phase_market_key`.
    sale_terms: List[Tuple[float, float, float, str]] = []
    if saturation_applies or capacity_applies:
        # The mix actually sold: chosen by the optimiser when concentrating,
        # otherwise the body's own proportions.
        if beneficiate and payload_mix:
            sold = dict(payload_mix)
        else:
            frac_sum = sum(f for _n, f, _p in phases)
            sold = {n: m_payload * f / frac_sum for n, f, _p in phases} if frac_sum > 0 else {}
        for phase, kg in sold.items():
            price = next((p for n, _f, p in phases if n == phase), 0.0)
            sale_terms.append((kg, price, phase_market_kg(markets, phase),
                               phase_market_key(markets, phase)))

    # ── Mission reliability (v1.8.0) ─────────────────────────────────────────
    # The terms that do not move with programme size, hoisted for the same
    # reason.  Only `p_mining` grows with N.
    p_launch = p_cruise = p_first = rel_alpha = p_mature = 1.0
    if config.model_reliability:
        # v1.17.6: five Module 3 rows, resolved once per run rather than once
        # per candidate mission.  See `_ops_reliability_constants`.
        (p_launch, mtbf_yr, p_first,
         rel_alpha, p_mature) = _ops_reliability_constants(ops_df)
        p_cruise  = math.exp(-mission_duration_yr / mtbf_yr) if mtbf_yr > 0 else 1.0

    gross_base           = gross_value
    delivered_base       = delivered_value_per_kg

    # ── v1.17.2: the cost cascade's N-independent half, built ONCE ───────────
    # Every argument below is fixed for the whole ladder; `cadence_yr` included,
    # since it is derived from the stay and the synodic period well above this
    # closure.  Only `n_missions` and `missions_per_ship` move, so only the
    # tail is worth re-running.  `mission_cost_usd` is exactly these two calls
    # composed, and it stays the entry point for everyone else.
    cost_prologue = _mission_cost_prologue(
        mass_cascade        = actual_cascade,
        vehicle             = vehicle,
        propellant          = propellant,
        ops_df              = ops_df,
        config              = config,
        mission_duration_yr = mission_duration_yr,
        processing_power_w  = processing_power_watts,
        stay_yr             = stay_yr,
        isru_return         = isru,
        ep_power_w          = ep_power_watts,
        power_source        = power_source,
        cadence_yr          = cadence_yr,
        rig_trips           = rig_trips,
    )
    # Per-candidate, because everything the saturation sum reads besides the
    # fleet belongs to this candidate.  See the read of it below.
    sat_by_fleet: Dict[int, Tuple[float, float, float]] = {}
    # v1.21.0's equivalent for `capacity_cap`, and it is keyed on (N, F) rather
    # than on F alone, because the accumulation window depends on both: the
    # fleet sets how often a delivery arrives and N sets how much of the
    # programme still carries the first delivery's longer wait.  N = F x W over
    # the ladder, so that is one key per rung and the memo buys nothing on its
    # own -- what keeps this cheap is the "does anything bind" test inside,
    # which answers most rungs in a few float comparisons.
    cap_by_programme: Dict[Tuple[int, int],
                          Tuple[float, float, float, float, float]] = {}
    # v1.17.5: the same argument one function further in.  The rig shares and
    # the programme-calendar multipliers are a function of the campaigns one
    # rig flies and of the PROLOGUE, and the ladder crosses ~8 fleets with
    # `trips` ≤ 5 campaigns, so ~42 options ask `_mission_cost_tail` for at
    # most ten distinct answers to that block.  Per-candidate for the same
    # reason `sat_by_fleet` is: every other input to it lives in `cost_prologue`.
    rig_by_share: Dict[Tuple[int, bool], Tuple[float, ...]] = {}

    # ⚠️  v1.17.6: NO annotations on this signature.  It is a nested def, so its
    # annotations are evaluated every time the enclosing function runs, and
    # `Optional[int]` is a `typing` subscript: 331 ns against 95 ns for the
    # bare def, 10,741 times per 150-row sample.  Types: (int, int, int | None,
    # bool).
    def _price_programme(n_missions, fleet, per_ship=None, full=True):
        """Everything downstream of the cascade, for one programme size.

        Returns `(cost, total_cost, gross, saturation_mult, concurrent,
        p_success, p_mining, delivered_per_kg, clearing, unsold_kg)`.  Nothing
        here re-enters the rocket equation; it is one pass of straight-line
        arithmetic over a cascade that is already solved.

        The last two are v1.21.0's and are APPENDED rather than inserted:
        `_objective_key` reads indices 1 and 2 off this tuple positionally on
        every rung of the ladder.

        v1.17.1: `full=False` asks for the total alone and leaves `cost` None.
        The ladder below compares options on `total_cost` and nothing else, so
        it prices cheaply and re-prices the single winner in full, one extra
        call out of ~40, against a 40-key dict built and discarded on every one
        of the other 39.  `total_cost` is the same float either way; see the
        early return in `_mission_cost_tail`.
        """
        c = _mission_cost_tail(cost_prologue, n_missions, per_ship,
                               totals_only = not full, rig_cache = rig_by_share)
        if full:
            total_cost = c["total_cost"]
        else:
            total_cost, c = c, None
        g          = gross_base
        sat        = 1.0
        clearing   = 1.0
        unsold     = 0.0
        surplus_kg = 0.0
        delivered  = delivered_base
        # ── The rate is the PROGRAMME'S, not one mission's (v1.14.0) ─────────
        # This term's own config comment says it exists because "prices were
        # static at the point of sale, so a mission could return any quantity of
        # platinum at spot and the 'fly more missions' lever had no stopping
        # point."  Until v1.14.0 it did not achieve that:
        # `nre_amortization_missions` was read in four places and none of them
        # was here, so a 100-mission programme divided its NRE by 100, grew its
        # reliability, and sold 100 payloads at the price one payload commands.
        #
        # What is on the market at once is the FLEET: one rig serves
        # `trips_per_ship` missions back to back, so F rigs put F payloads in
        # flight concurrently.  v1.15.0 takes that count from the ladder rather
        # than re-deriving it from `missions_sharing_rig`, which is the same
        # number by construction, N = F × trips, and one derivation fewer.
        concurrent = 1.0
        if saturation_applies:
            concurrent = fleet
            # v1.17.2: this block reads `fleet` and nothing else the ladder
            # varies, `sale_terms`, `gross_base`, `m_payload` and the mission
            # duration are all fixed for the candidate, so it is a function of
            # F alone, and the ladder is the F ladder CROSSED WITH W.  It was
            # therefore being recomputed once per W: ~40 options over ~8
            # distinct fleets, so four out of five passes re-derived a sum they
            # had already made.  Memoised per candidate on the integer F.
            #
            # Bit-identical by construction rather than by rounding: the same
            # F re-runs the same `+=` over the same list in the same order, so
            # the cached float IS the float the loop would have produced.  That
            # matters here more than most places; this is the accumulation
            # v1.14.2 found to be load-bearing on the last ULP, which is why
            # the phase table must not be sorted at source.
            entry = sat_by_fleet.get(fleet)
            if entry is None:
                # v1.21.2: the RATE that moves a price is the market's total
                # throughput, not one phase's share of it.  Two phases selling
                # into one market depress it together, and asking the curve per
                # phase asked it twice about half the quantity each time, which
                # is a smaller haircut than the truth.  Pooled first, then each
                # phase's revenue is discounted at its MARKET's multiplier.
                pooled: Dict[str, float] = {}
                for kg, _price, _mkt, key in sale_terms:
                    pooled[key] = pooled.get(key, 0.0) + kg
                mult: Dict[str, float] = {}
                adj = 0.0
                for kg, price, mkt, key in sale_terms:
                    m_key = mult.get(key)
                    if m_key is None:
                        m_key = mult[key] = saturation_price_multiplier(
                            pooled[key] * concurrent / mission_duration_yr,
                            mkt,
                            config.demand_elasticity,
                        )
                    adj += kg * price * m_key
                entry = sat_by_fleet[fleet] = (
                    adj,
                    adj / gross_base if gross_base > 0 else sat,
                    adj / m_payload  if m_payload  > 0 else 0.0,
                )
            g, sat, delivered = entry
        elif capacity_applies:
            # ── v1.21.0.  CONSTANT PRICE, BOUNDED QUANTITY ──────────────────
            # Every kilogram inside the ceiling fetches exactly what the
            # mineral catalog quotes, so `saturation_multiplier` stays 1.0
            # here: no price moved for the market's own customers.  What the
            # programme loses is what it cannot place at that price, reported
            # separately as `market_clearing_fraction`, `unsold_payload_kg` and
            # `surplus_payload_kg` so no column has two meanings.
            #
            # v1.22.0: what happens past the ceiling is `surplus_frac`.  At 0.0
            # the surplus fetches nothing and this is v1.21.0's wall; above it
            # the surplus sells at that fraction of full price, which still
            # bounds the ladder -- the marginal kilogram past the wall is worth
            # strictly less than the one before it, so another ship still adds
            # its whole cost against a falling marginal revenue.
            #
            # This is what bounds the ladder.  A bigger fleet delivers more
            # often, so each delivery gets a shorter accumulation window; past
            # the point where the ceilings bind, another ship adds its full
            # cost and only part of its revenue, and the objective turns over
            # on its own instead of running to `max_fleet_ships`.
            concurrent = fleet
            ckey  = (n_missions, fleet)
            entry = cap_by_programme.get(ckey)
            if entry is None:
                window = _delivery_window_yr(
                    n_missions, fleet, mission_duration_yr, cadence_yr)
                # The fast path, and it is the common one at small fleets.  If
                # no commodity reaches its ceiling then the load sells whole
                # and the optimiser would only rediscover `gross_base`.  Same
                # shape as v1.14.1's pre-filter: prove nothing binds in a few
                # float comparisons rather than paying to be told.
                # v1.21.2: pooled, for the same reason the sale is.  Testing
                # per phase let a load slip through this fast path while the
                # SHARED silicates allowance was already over, and the fast
                # path returns `gross_base`, i.e. no ceiling at all.
                agg: Dict[str, Tuple[float, float]] = {}
                for kg, _price, mkt, key in sale_terms:
                    prev = agg.get(key)
                    agg[key] = (kg + prev[0], mkt) if prev is not None else (kg, mkt)
                binds = False
                for kg, mkt in agg.values():
                    if kg > mkt * window:
                        binds = True
                        break
                if not binds:
                    entry = (gross_base, 1.0, 0.0, delivered_base, 0.0)
                elif beneficiate and payload_mix:
                    # RESHAPE.  Concentrating means the hold's contents are
                    # chosen, so a load that caps out on one phase re-fills the
                    # freed space with the next most valuable one instead of
                    # flying the excess unsold.  The ceilings go INTO the
                    # knapsack, where they are per-item upper bounds and greedy
                    # stays exact; see `optimal_payload_mix`.
                    # v1.21.2: one entry per MARKET rather than per phase, so
                    # `silicates` and the composition residual draw on one
                    # allowance instead of two.  A fresh dict per call because
                    # the walk consumes it.
                    caps_by_market: Dict[str, float] = {}
                    cap_keys: Dict[str, str] = {}
                    for nm, _f, _p in phases:
                        k = phase_market_key(markets, nm)
                        cap_keys[nm] = k
                        if k not in caps_by_market:
                            caps_by_market[k] = phase_market_kg(markets, nm) * window
                    capped = optimal_payload_mix(
                        m_payload, feed_kg, phases,
                        config.beneficiation_recovery,
                        caps=caps_by_market, cap_keys=cap_keys,
                        surplus_price_frac=surplus_frac,
                    )
                    cvalue = float(capped["value_usd"])
                    # Measured against the UNCAPPED load, not against the hold.
                    # `m_payload - loaded` would also count capacity the feed
                    # could never have filled, which is a poor rock rather than
                    # a full market, and the fast path above reports 0.0 for
                    # exactly that case.  One meaning per column: mass lost to
                    # the CEILINGS.
                    loaded_free = sum(payload_mix.values())
                    entry  = (
                        cvalue,
                        cvalue / gross_base if gross_base > 0 else 1.0,
                        max(0.0, loaded_free - float(capped.get("loaded_kg", 0.0))),
                        cvalue / m_payload if m_payload > 0 else 0.0,
                        float(capped.get("surplus_kg", 0.0)),
                    )
                else:
                    # RAW ore cannot be reshaped: the cargo is the body's own
                    # composition, so whatever is past a ceiling simply does not
                    # sell.  The hold still flies and is still paid for, which
                    # is why this is the branch that punishes scale hardest.
                    cvalue, cunsold, csurplus = _capped_sale_value(
                        sale_terms, window, surplus_frac)
                    entry = (
                        cvalue,
                        cvalue / gross_base if gross_base > 0 else 1.0,
                        cunsold,
                        cvalue / m_payload if m_payload > 0 else 0.0,
                        csurplus,
                    )
                cap_by_programme[ckey] = entry
            g, clearing, unsold, delivered, surplus_kg = entry
        # Revenue was certain.  It is not: the launch fails, the spacecraft dies
        # on the way, or the mining chain does not work when it arrives.  Costs
        # are charged in FULL, which is correct; you spend the money either
        # way.  v1.20.0's `charge_insurance` does not reach this term: a
        # premium replaced hardware rather than revenue, so there was no
        # double count here to begin with and none is created by removing it.
        ps = 1.0
        pm = 1.0
        if config.model_reliability:
            # v1.9.0: the mining chain LEARNS, so p_mining is the fleet average
            # over the programme rather than the first-of-kind figure held flat.
            # Launch and cruise reliability deliberately do not grow; launch
            # vehicles are mature, and MTBF is a duration exposure rather than a
            # heritage question.
            pm = (_mining_reliability_cached(n_missions, p_first, rel_alpha, p_mature)
                  if config.model_reliability_growth else p_first)
            ps = max(0.0, min(1.0, p_launch * p_cruise * pm))
            g *= ps
        # v1.21.0 appends rather than inserts: `_objective_key` reads indices
        # 1 and 2 off this tuple positionally, and the ladder compares on them.
        # v1.22.0 appends `surplus_kg` for the same reason, at index 10.
        return (c, total_cost, g, sat, concurrent, ps, pm, delivered,
                clearing, unsold, surplus_kg)

    # v1.17.1: the ladder prices on totals and the winner is rebuilt in full
    # once, below.  `single` is the common case, the search off, one option, 
    # and it skips the rebuild entirely by pricing in full straight away.
    programmes, fleet_ladder = _programme_ladder_cached(
        rig_trips, config, market_mode)
    single       = len(programmes) == 1
    # v1.17.6: the ranking objective is a config field, so it is resolved once
    # here rather than re-read on every rung below.  See `_objective_key`.
    on_profit    = _selects_on_profit(config.selection_objective)
    best_n, best_f, best_w = programmes[0]
    best_priced  = _price_programme(best_n, best_f, best_w, full=single)
    best_pkey    = _objective_key(
        best_priced[2] - best_priced[1],
        best_priced[2], best_priced[1], config, on_profit)
    priced_count = 1

    for n_missions, fleet, per_ship in programmes[1:]:
        cand = _price_programme(n_missions, fleet, per_ship, full=False)
        priced_count += 1
        key = _objective_key(cand[2] - cand[1], cand[2], cand[1], config, on_profit)
        if key > best_pkey:
            best_pkey, best_priced = key, cand
            best_n, best_f, best_w = n_missions, fleet, per_ship

    # One refinement pass around the coarse winner, on the same geometric
    # spacing plus both integer neighbours; see `fleet_refinement`.  Skipped
    # entirely when the programme is not being searched, which is the default
    # and the path every committed figure was measured on.
    #
    # v1.16.0: refined at the winner's OWN campaigns-per-ship.  W is enumerated
    # exhaustively, so it needs no refinement of its own, but it does need to
    # be held fixed while F moves, because N = F × W and refining F against some
    # other W would price a programme the search never proposed.
    if len(programmes) > 1:
        for fleet in _fleet_refinement_cached(best_f, fleet_ladder):
            n_missions = fleet * best_w
            cand = _price_programme(n_missions, fleet, best_w, full=False)
            priced_count += 1
            key = _objective_key(cand[2] - cand[1], cand[2], cand[1], config, on_profit)
            if key > best_pkey:
                best_pkey, best_priced = key, cand
                best_n, best_f = n_missions, fleet

    # The winning programme is the only one whose full cost breakdown is
    # reported, so it is the only one that has to be built.  Re-priced rather
    # than cached because the ladder above carried floats: same arguments, same
    # deterministic arithmetic, same dict the old code returned.
    if best_priced[0] is None:
        best_priced = _price_programme(best_n, best_f, best_w, full=True)

    # `_total_cost` is the same float as `cost["total_cost"]` on the full path;
    # the expressions below keep reading the dict so nothing downstream moved.
    (cost, _total_cost, gross_value, saturation_mult, concurrent_missions,
     p_success, p_mining, delivered_value_per_kg,
     market_clearing, unsold_payload_kg, surplus_payload_kg) = best_priced

    profit               = gross_value - cost["total_cost"]
    roi                  = profit / cost["total_cost"] if cost["total_cost"] > 0 else np.nan
    usd_per_kg_cost      = cost["total_cost"] / m_payload if m_payload > 0 else np.nan

    arch = delivery_architecture(config.delivery_destination)
    return {
        "vehicle":              vehicle["name"],
        "propellant":           propellant["name"],
        "delivery_destination": config.delivery_destination,
        # v1.21.0.  Stamped for exactly the reason `delivery_destination` and
        # `pipeline_version` are: it identifies the run.  Four market models
        # give the same code four different answers -- 20% to 49% apart on the
        # sampled cislunar cells -- so a `pipeline_version` alone no longer
        # says what produced a catalog, and an archived CSV that cannot say
        # which model priced it cannot be compared with anything.
        #
        # NOT provenance, so `verify.py` does not strip it before hashing:
        # `catalog_date` and `pipeline_version` are stripped because they move
        # without the model moving, and this is the opposite -- it moves only
        # when the model does, and two runs that differ in it SHOULD differ.
        "market_model":         market_mode,
        "delivery_arch":        arch["label"],
        "returns_to_earth":     arch["returns_to_earth"],
        "flies_tps":            tps_frac > 0.0,
        # ── Per-asteroid architecture choices (v1.10.0) ─────────────────────
        "aerocapture_return":   bool(aero),
        "isru_return":          bool(isru),
        "isru_propellant_kg":   isru_prop_kg,
        "isru_feed_kg":         isru_feed_kg,
        "rendezvous_apsis":     rendezvous_apsis,
        "dv_out_m_s":           dv_out_m_s,
        "dv_ret_m_s":           dv_ret_m_s,
        "isp_s":                float(propellant["isp_vac_s"]),
        "dv_penalty_factor":    dv_penalty,
        "mission_duration_yr":  mission_duration_yr,
        "mining_duration_yr":   mining_yr,
        "max_payload_kg":       m_payload,
        "throughput_cap_kg":    throughput_cap_kg,
        "throughput_fits":      throughput_fits,
        # ── Beneficiation (v1.5.0) ──────────────────────────────────────────
        "beneficiation":            beneficiate,
        "feed_processed_kg":        feed_kg,
        "concentration_ratio":      concentration_ratio,
        "delivered_value_usd_per_kg": delivered_value_per_kg,
        "best_phase_usd_per_kg":    best_phase_value_per_kg,
        # What the optimiser actually chose to load
        "payload_dominant_phase":   dominant_phase,
        "payload_dominant_frac":    dominant_frac,
        "payload_mix":              (
            "; ".join(f"{k} {v:,.0f}kg" for k, v in
                      sorted(payload_mix.items(), key=lambda kv: -kv[1]))
            if payload_mix else ""
        ),
        # True when the concentrate is at the purity ceiling, i.e. grade, not
        # processing capacity, is what limits the delivered value.  Compared
        # against the delivered figure itself (with a relative tolerance)
        # rather than re-deriving it, so a feed clipped by throughput or by
        # the body's own mass reports honestly as NOT saturated.
        "purity_bound_binds":       bool(
            beneficiate
            and best_phase_value_per_kg > 0
            and delivered_value_per_kg >= best_phase_value_per_kg * (1.0 - 1e-9)
        ),
        # ── v1.7.0 modelling completeness ──────────────────────────────────
        "is_electric":              is_electric,
        "ep_power_w":               ep_power_watts,
        "ep_system_kg":             ep_system_kg,
        "ep_thrust_yr":             ep_thrust_yr,
        # ── v1.12.0 device-level sizing ────────────────────────────────────
        "ep_thrust_n":              ep_thrust_n,
        "thruster_kg_per_n":        thruster_kg_per_n,
        "thruster_kg":              ep_thrust_n * thruster_kg_per_n,
        "thruster_efficiency":      eff_used if is_electric else float("nan"),
        "thrust_scaling":           propellant.get("thrust_scaling"),
        "synodic_period_yr":        synodic_yr,
        "launch_window_wait_yr":    window_wait_yr,
        "water_liberated_kg":       water_kg,
        "saturation_multiplier":    saturation_mult,
        # v1.21.0.  Two columns rather than overloading the one above, because
        # a price multiplier and a quantity clip are different claims and a
        # column that means one thing in one market model and another thing in
        # the next is the ambiguity this project keeps paying for.
        #   saturation_multiplier    a PRICE multiplier; 1.0 unless the market
        #                            model is `elasticity`
        #   market_clearing_fraction share of the assembled load's gross value
        #                            that cleared the ceilings; 1.0 unless the
        #                            model is `capacity_cap` and one bound
        #   unsold_payload_kg        payload mass that earned NOTHING because
        #                            a ceiling refused it: ore flown past one
        #                            when raw, load the knapsack could not
        #                            place under them when beneficiated.  NOT
        #                            hold space a poor feed failed to fill,
        #                            which is 0.0 here and has always been the
        #                            knapsack's own behaviour
        #   surplus_payload_kg       v1.22.0.  Payload mass sold PAST a ceiling
        #                            at `surplus_price_fraction` of full price.
        #                            Two columns rather than one because they
        #                            are two events, and a single "mass over
        #                            the ceiling" column would have changed
        #                            meaning under `sell_surplus_at_discount`
        #                            without changing its name.  Under the
        #                            v1.22.0 default this is where the mass
        #                            goes and `unsold_payload_kg` is 0.0; set
        #                            the flag False and they swap over
        "market_clearing_fraction": market_clearing,
        "unsold_payload_kg":        unsold_payload_kg,
        "surplus_payload_kg":       surplus_payload_kg,
        "p_success":                p_success,
        "p_mining":                 p_mining if config.model_reliability else 1.0,
        "boiloff_factor":           boiloff_factor,
        "dv_ret_effective_m_s":     dv_ret_eff,
        # v1.15.0: read back out of the winning programme rather than
        # re-derived from the config, which would report the curve for a
        # programme size the mission was not priced at the moment N is searched.
        "learning_curve_factor":    cost["learning_curve_factor"],
        "processing_power_w":       processing_power_watts,
        "power_system_kg":          power_system_kg,
        "power_w_per_kg_at_target":  plant_w_per_kg,
        "power_source":             power_source,
        "hardware_total_kg":        hardware_total_kg,
        # ── v1.14.0 eclipse / night-side power ─────────────────────────────
        # `power_w_per_kg_at_target` above is now the EFFECTIVE figure (array
        # oversize and night storage folded in); the bare 1/r² rating is kept
        # beside it so the size of the penalty is legible per row rather than
        # having to be reverse-engineered from two constants.
        "solar_w_per_kg_bare":      w_per_kg,
        "array_oversize_factor":    array_oversize_factor,
        "dark_period_h":            dark_h,
        "dark_period_clamped":      dark_clamped,
        "rotation_period_h":        asteroid_row.get("rotation_period_h"),
        # ── v1.14.0 volatile cargo containment ─────────────────────────────
        "cargo_water_kg":           cargo_water_kg,
        "containment_frac":         containment_frac,
        "m_containment_kg":         m_containment_kg,
        # ── v1.14.0 programme-aware market saturation ──────────────────────
        # Kept with its exact v1.14.0 semantics: 1.0 whenever the saturation
        # term is switched off, so that a gated-off build still reproduces
        # that release byte for byte.  `fleet_ships` below is the unconditional
        # count and is the one to read.
        "concurrent_missions":      concurrent_missions,
        # ── v1.15.0 programme scale and fleet size ─────────────────────────
        # `programme_missions` is N and `fleet_ships` is F, and the invariant
        # between them is N = F × trips_per_ship whenever the search is on.
        # With it off, N is whatever the config said and F is the fleet that
        # size implies, the two columns still describe the same programme,
        # they are just not being chosen.
        "programme_missions":       float(best_n),
        "fleet_ships":              float(best_f),
        "trips_per_ship":           float(trips_per_ship),
        "rig_trips_calendar_cap":   float(rig_calendar_cap),
        # True where the CYCLE bound is what retires the rig rather than the
        # calendar one.  Worth reporting per row rather than assuming: the two
        # bounds swap over at a stay of life/trips (3 yr at 15 yr and 5 trips),
        # so a long-stay mission is still calendar-limited and reads False here.
        "rig_trip_limit_binds":     bool(
            rig_trip_cap is not None and trips_per_ship == rig_trip_cap
            and rig_trip_cap < rig_calendar_cap),
        # How many rungs of the fleet ladder this mission actually paid for.
        # 1 means the programme was set, not searched.
        "programme_options_priced": float(priced_count),
        # ── v1.16.0 programme calendar time ────────────────────────────────
        # `missions_per_ship` is W, the second dimension of the programme
        # search, and the invariant is N = F × W wherever the search is on.
        # It is NOT `trips_per_ship`: trips is what the rig could do, W is what
        # the programme chose to ask of it, and the gap between them is the
        # calendar charge declining to use up the machine.
        "missions_per_ship":        cost["missions_sharing_rig"],
        "campaign_cadence_yr":      cost["campaign_cadence_yr"],
        # Cadence is the DIG unless windows open more slowly than the rig digs,
        # in which case it is the synodic period.  True where the window binds,
        # which is where a programme to this body is paced by orbital mechanics
        # rather than by mining rate.
        "cadence_window_bound":     bool(
            config.model_launch_windows
            and cost["campaign_cadence_yr"] > stay_yr + 1e-12),
        "programme_span_yr":        cost["programme_span_yr"],
        # 1.0 means no calendar charge was levied; either W = 1, or the term
        # is switched off.  This is the multiplier on the AMORTISED up-front
        # lines only (bus NRE, autonomy NRE, rig), not on mission cost.
        "programme_calendar_multiplier": cost["programme_calendar_multiplier"],
        # ── v1.11.0 storage and refuelling ─────────────────────────────────
        "tank_mass_frac":           tank_frac,
        "m_tank_return_kg":         float(actual_cascade.get("m_tank_return", 0.0)),
        "m_tank_outbound_kg":       float(actual_cascade.get("m_tank_outbound", 0.0)),
        "propellant_storage_class": propellant.get("storage_class"),
        "tanker_flights":           cost.get("tanker_flights", 0.0),
        "tanker_cost_usd":          cost.get("tanker_cost", 0.0),
        "isru_feed_material":       propellant.get("isru_feed_material"),
        "return_bulk_density_kg_per_L": bulk_density_kg_per_L,
        "return_volume_m3":     return_volume_m3,
        "fairing_volume_m3":    fairing_m3,
        "volume_fits":          volume_fits,
        "m_dry_return_kg":      m_dry_return,
        "m_launch_kg":          m_launch,
        "m_outbound_prop_kg":   m_outbound_prop,
        "m_return_prop_kg":     m_return_prop,
        "m_at_asteroid_kg":     m_at_asteroid,
        "bulk_value_usd_per_kg": bulk_value_per_kg,
        "gross_value_usd":      gross_value,
        "total_cost_usd":       cost["total_cost"],
        "profit_usd":           profit,
        "roi":                  roi,
        "usd_per_kg_cost":      usd_per_kg_cost,
        # Cost breakdown, per-line items
        "launch_cost_usd":           cost["launch_cost"],
        "outbound_prop_cost_usd":    cost["outbound_prop_cost"],
        "return_prop_cost_usd":      cost["return_prop_cost"],
        "hardware_cost_usd":         cost["hardware_cost"],
        "mining_rig_cost_usd":       cost["mining_rig_cost"],   # amortised
        "capsule_cost_usd":          cost["capsule_cost"],      # per mission
        "power_system_cost_usd":     cost["power_system_cost"],
        "ep_system_cost_usd":        cost["ep_system_cost"],
        "tank_cost_usd":             cost["tank_cost"],
        "rig_terminal_value_usd":    cost["rig_terminal_value"],
        "missions_sharing_rig":      cost["missions_sharing_rig"],
        "ops_cost_usd":              cost["ops_cost"],
        "tps_mass_kg":               cost["tps_mass_kg"],
        "heat_shield_cost_usd":      cost["heat_shield_cost"],
        "recovery_cost_usd":         cost["recovery_cost"],
        "liability_cost_usd":        cost["liability_cost"],
        "licensing_cost_usd":        cost["licensing_cost"],
        "launch_insurance_cost_usd": cost["launch_insurance_cost"],
        "nre_cost_usd":              cost["nre_cost"],
        "autonomy_nre_cost_usd":     cost["autonomy_nre_cost"],
        "contingency_cost_usd":      cost["contingency_cost"],
        # Time-bucketed cost components (post-contingency, pre-WACC)
        "upfront_cost_usd":          cost["upfront_cost"],
        "ongoing_cost_usd":          cost["ongoing_cost"],
        "end_of_mission_cost_usd":   cost["end_of_mission_cost"],
        "wacc_multiplier_upfront":   cost["wacc_multiplier_upfront"],
        "wacc_multiplier_ongoing":   cost["wacc_multiplier_ongoing"],
        "wacc_multiplier":           cost["wacc_multiplier"],   # weighted avg
    }


def selection_key(
    result: Optional[Dict[str, float]], config: CalcConfig,
) -> Tuple[float, float]:
    """Ranking key for choosing between candidate missions.  Higher is better.

    v1.10.0.  Every per-asteroid search in this module: over concentration
    ratio, over vehicle, over propellant, over return mode, used to pick the
    candidate with the highest `profit_usd`.  That is the right objective for a
    firm, and it is the wrong one for this model, for a reason the README and
    CLAUDE.md have documented for several versions without the code acting on
    it: revenue here is orders of magnitude below cost, so

        profit_usd = gross_value_usd − total_cost_usd ≈ −total_cost_usd

    and maximising it degenerates into minimising cost.  The mission that got
    selected was the CHEAPEST one, not the one that came closest to viability,
    and then the whole project ranked the results by a cost/revenue ratio that
    nothing had optimised.  The symptom is unmissable once you look for it:
    widening the search space could make an asteroid's reported ratio WORSE,
    because a newly-available cheaper-and-far-less-productive mission won on
    profit.  A search whose answer degrades when given more options is not
    optimising the quantity being reported.

    So the objective is lexicographic, which costs nothing and is honest at
    both ends of the regime:

      • If any candidate actually turns a profit, maximise PROFIT.  That is a
        real operator's objective and the ratio is no longer the interesting
        number once you are above water.
      • If none does, which is every default configuration today, minimise
        COST / REVENUE.  That is the question the model exists to answer:
        how close to viable can this rock be made to come?

    Because (1, x) beats (0, y) for any x and y, a profitable candidate always
    outranks an unprofitable one and the two regimes never mix.

    Set `selection_objective = "profit"` to restore the pre-v1.10.0 behaviour.
    """
    if result is None:
        return (-np.inf, -np.inf)
    return _objective_key(
        float(result.get("profit_usd", -np.inf)),
        float(result.get("gross_value_usd", 0.0) or 0.0),
        float(result.get("total_cost_usd", 0.0) or 0.0),
        config,
    )


# The selection objective is a free-text config field, normalised on every read.
# It is read once per programme option, so the normalisation ran ~458k times on
# a 150-row sample to answer a question whose input is fixed for the run.
# Keyed on the RAW value rather than on `id(config)`: the raw string IS the
# input, so two configs naming the same objective share one entry, and a config
# edited between runs is still answered correctly.
_SELECTION_ON_PROFIT: Dict[Any, bool] = {}


def _selects_on_profit(objective: Any) -> bool:
    """Whether `selection_objective` names the raw-profit ranking.

    Memoised because it is a string parse in the innermost loop of the search.
    The parse itself is untouched -- this caches its answer, it does not change
    what counts as "profit".
    """
    try:
        hit = _SELECTION_ON_PROFIT.get(objective)
    except TypeError:            # unhashable: parse it and cache nothing
        return str(objective).strip().lower() == "profit"
    if hit is None:
        hit = _SELECTION_ON_PROFIT[objective] = (
            str(objective).strip().lower() == "profit")
    return hit


def _objective_key(
    profit: float, gross: float, cost: float, config: CalcConfig,
    on_profit: Optional[bool] = None,
) -> Tuple[float, float]:
    """`selection_key`'s ranking algebra, over loose scalars.

    v1.15.0 split this out because the programme-scale search ranks candidates
    before any result dict exists, building one per rung of the fleet ladder
    just to read three fields back out of it would allocate a ~130-key dict per
    comparison.  It is a split for the caller's convenience and NOT a second
    statement of the rule: `selection_key` is defined as this function, so the
    two cannot drift, which is the failure mode this file warns about wherever
    algebra appears twice (see `_combo_can_close`).

    v1.17.5: the objective is read through `_selects_on_profit`, which memoises
    the string normalisation.  `str(x).strip().lower()` measures 93 ns against a
    dict lookup's 31 ns, and this function is called 457,776 times on a 150-row
    beneficiated+searched sample -- once per rung of every programme ladder --
    to re-derive one boolean from a config field that cannot change mid-solve.
    The comparison it feeds is unchanged, so both returned floats are the same
    floats.

    v1.17.6: `on_profit` lets a caller that ranks many candidates against ONE
    config hand the answer in, which is the programme ladder; it called this
    444,353 times on that sample against 10,741 candidate missions, so even a
    dict lookup was being made 41 times more often than the question was asked.
    None keeps the read, so every other caller is untouched.  This is still one
    statement of the rule: the branches and both returned floats are unchanged,
    and `on_profit` can only carry what `_selects_on_profit` would have said.
    """
    if on_profit is None:
        on_profit = _selects_on_profit(config.selection_objective)
    if on_profit:
        return (0.0, profit)
    if profit > 0:
        return (1.0, profit)
    if gross <= 0:
        return (-1.0, -cost)          # no revenue at all, lose the least
    return (0.0, -(cost / gross))


def saturation_ratio(
    phases: List[Tuple[str, float, float]], recovery: float, cap: float,
) -> float:
    """Feed:concentrate ratio that just fills the hold with pure best phase.

        feed x frac_best x recovery >= payload  ⇒  ratio >= 1 / (frac_best x recovery)

    Above this the knapsack has nothing better to load, so grade stops
    improving while dig time, energy and array mass keep climbing.  It is the
    upper end of the useful search range, not necessarily the optimum.
    """
    if not phases:
        return 1.0
    best_frac = max(phases, key=lambda p: p[2])[1]
    denom = best_frac * recovery
    if denom <= 0:
        return 1.0
    return max(1.0, min(1.0 / denom, cap))


def evaluate_combo(
    asteroid_row:      Row,
    vehicle:           Row,
    propellant:        Row,
    bulk_value_per_kg: float,
    dv_out_m_s:        float,
    dv_ret_m_s:        float,
    ops_df:            pd.DataFrame,
    config:            CalcConfig,
    best_phase_value_per_kg: Optional[float] = None,
    phases:            Optional[List[Tuple[str, float, float]]] = None,
    markets:           Optional[Dict[str, float]] = None,
    aero:              Optional[bool] = None,
    isru:              bool = False,
    rendezvous_apsis:  str = "",
    power_mode:        str  = "solar",
    ctx:               Optional[AsteroidContext] = None,
    market_mode:       Optional[str] = None,
) -> Optional[Dict[str, float]]:
    """Best mission for one (asteroid × vehicle × propellant × architecture),
    optimising over how hard to concentrate.  "Best" is `selection_key`, which
    is not simply the highest profit; see there.

    Without beneficiation there is nothing to choose: one solve at ratio 1.0.

    With it, the concentration ratio is a genuine economic decision rather
    than a setting.  Digging more feed raises the grade of the load, but the
    gain SATURATES once the hold is pure best-phase, while the costs do not:
    every extra kilogram of feed still costs dig time (which compounds through
    ops and WACC), processing energy, and the solar array mass to supply it,
    and that array mass comes straight out of the payload budget.

    So the value curve is concave and the cost curve is not, which puts the
    optimum strictly inside the range on most targets.  An earlier version
    drove the ratio to saturation on principle and made cislunar missions
    ~12% worse than not concentrating at all.  This searches instead.

    The search is a coarse sweep from 1.0 to the saturation ratio, refined
    once around the winner.  Both endpoints are always evaluated, so the
    answer can never be worse than either "don't concentrate" or
    "concentrate fully".
    """
    solve = lambda r, b=True: _evaluate_combo_at_ratio(
        asteroid_row, vehicle, propellant, bulk_value_per_kg,
        dv_out_m_s, dv_ret_m_s, ops_df, config,
        best_phase_value_per_kg=best_phase_value_per_kg,
        phases=phases, target_ratio=r, beneficiate=b, markets=markets,
        market_mode=market_mode,
        aero=aero, isru=isru, rendezvous_apsis=rendezvous_apsis,
        power_mode=power_mode, ctx=ctx,
    )

    if not config.use_beneficiation:
        return solve(1.0, False)

    # Baseline: don't concentrate at all.  Not the same as concentrating at
    # ratio 1.0; that would still pay the separation recovery loss, the
    # processing energy and the array mass for no grade improvement.
    # Including it makes beneficiation an OPTION rather than an obligation,
    # so the answer can never be worse than simply scooping and leaving.
    best = solve(1.0, False)
    best_key = selection_key(best, config)
    best_r = 1.0

    r_max = saturation_ratio(
        phases or [], config.beneficiation_recovery, config.max_concentration_ratio,
    )
    if r_max <= 1.0:
        return best

    # Coarse sweep, geometric so the cheap end is sampled as finely as the
    # expensive end.  Endpoints included explicitly.
    n = max(2, int(config.concentration_search_steps))
    candidates = [r_max ** (i / (n - 1)) for i in range(n)]

    for r in candidates:
        res = solve(r)
        key = selection_key(res, config)
        if res is not None and key > best_key:
            best_key, best, best_r = key, res, r

    # One refinement pass around the winner, on the same geometric spacing.
    if best is not None and n > 2:
        step = r_max ** (1.0 / (n - 1))
        for r in (best_r / (step ** 0.5), best_r * (step ** 0.5)):
            if not (1.0 <= r <= r_max):
                continue
            res = solve(r)
            key = selection_key(res, config)
            if res is not None and key > best_key:
                best_key, best = key, res
    return best


def _row_to_dict(row: Row) -> Dict[str, Any]:
    """A catalog row as a plain dict, for the inner search.

    Every consumer of an asteroid / vehicle / propellant row in this module
    reads it with `.get(key)` or `[key]` and nothing else, and a dict serves
    both identically -- but pandas resolves each one through the index
    machinery at ~5 us a lookup.  The search does roughly 7,400 of them per
    asteroid (77 vehicle x propellant combos x the architecture and
    concentration axes), which measured at ~38% of total runtime: a third of
    the run was spent re-deriving positions in an index that never changes.

    Converting once per row and then hitting a hash table costs one to_dict()
    and buys all of it back.

    This is value-preserving, not merely close.  `Series.to_dict()` unboxes
    numpy scalars to their Python equivalents -- np.float64 to float, np.int64
    to int -- and np.float64 IS a C double, so every downstream `float(...)`,
    `math.exp`, and comparison sees the identical bit pattern.  Verified by
    diffing a full catalog CSV against the pre-change output.

    Already-dict rows (the parallel workers hand these back and forth) are
    returned as-is rather than copied; nothing in the search mutates a row.
    """
    if isinstance(row, dict):
        return row
    return row.to_dict()


def _truthy(series: pd.Series, default: bool) -> pd.Series:
    """Boolean coercion that survives a CSV round-trip.

    These flags reach Module 4 through a file, and the round-trip is only
    lossless while every row states the column: pandas then infers dtype bool
    and `.astype(bool)` is correct.  Add ONE row that omits it and the column
    comes back as object, at which point `.astype(bool)` reads the *string*
    "False" as True and NaN as True, so a propellant that cannot fly this
    mission profile would silently rejoin the search, and nothing would say so.

    That is the failure mode this repo keeps finding: a guard that turns a
    wrong answer into a quiet one.  Parse the strings, and let `default` decide
    what a MISSING value means rather than letting truthiness decide it.
    """
    if series.dtype == bool:
        return series
    parsed = series.map(
        lambda v: v if isinstance(v, (bool, np.bool_))
        else (None if v is None or (isinstance(v, float) and pd.isna(v))
              else str(v).strip().lower() in ("true", "1", "yes", "t"))
    )
    return parsed.fillna(default).astype(bool)


def candidate_combos(
    catalogs: Dict[str, pd.DataFrame],
    config:   CalcConfig,
) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Every (vehicle, propellant) pair that passes the CalcConfig filters.

    The filters depend only on `config`, never on the asteroid, so the whole
    cross-join is built once per run and reused for every row.  Doing it
    inside the per-asteroid loop re-ran two DataFrame copies plus ~88
    `iterrows()` Series constructions for each of N asteroids.

    Rows come back as dicts (v1.10.1) -- see _row_to_dict.  These are also
    what gets shipped to the parallel workers, and a dict pickles far more
    cheaply than a Series.
    """
    vdf = catalogs["vehicles"]
    if config.operational_vehicles_only and "status" in vdf.columns:
        vdf = vdf[vdf["status"] == "operational"]
    # v1.11.0.  Module 3 v1.9.0 added lunar-origin launch systems (a mass
    # driver and an elevator) whose $/kg is an order of magnitude below any
    # rocket.  They are unreachable here for a structural reason rather than a
    # maturity one: this module departs from Earth, and their payload columns
    # are ANNUAL THROUGHPUT rather than per-launch mass, so reading them would
    # not merely be optimistic, it would be a unit error.
    if "origin" in vdf.columns:
        vdf = vdf[vdf["origin"] == "earth_surface"]
    # ── Launch acceleration (v1.12.0) ────────────────────────────────────────
    # Module 3 added `max_accel_g` in v1.9.0 specifically to disqualify the
    # kinetic launchers, and said so in the column's own documentation; "it is
    # in this table because it is DISQUALIFYING for the kinetic launchers", 
    # and then nothing read it.  The gate was maturity alone, which happens to
    # exclude them today only because SpinLaunch and the light-gas gun are
    # tagged `concept`.  Flip `operational_vehicles_only` off and a 10,000 g
    # slingshot at $6,250/kg enters the search and wins on price, because
    # nothing in this module knows it would powder the mining rig.
    #
    # That is not a cost trade.  Spacecraft structures qualify to single-digit
    # g; the kinetic launchers run 10,000-30,000 g and StarTram 30 g.  They can
    # pass propellant, water and steel billets, and they destroy every optic,
    # reaction wheel, radio and rig in the catalog.  A launcher that can lift
    # only consumables genuinely changes a mining programme's economics, but
    # this pipeline flies ONE manifest and cannot express the split, so the
    # honest answer is to exclude them rather than to fly hardware on them.
    if "max_accel_g" in vdf.columns:
        accel = pd.to_numeric(vdf["max_accel_g"], errors="coerce")
        # NaN passes: a row that does not state its acceleration is an ordinary
        # rocket by omission, not a railgun.  Same defensive default as the
        # rest of the Module 3 reads.
        vdf = vdf[~(accel > config.max_payload_accel_g)]
    if config.candidate_vehicles is not None:
        vdf = vdf[vdf["name"].isin(config.candidate_vehicles)]

    pdf = catalogs["propellants"]
    # ── Propellant gating (v1.11.0) ──────────────────────────────────────────
    # Three filters, and only the first is about maturity.  The other two are
    # about whether a propellant can fly THIS mission profile at all, and they
    # apply regardless of how flight-proven it is:
    #
    #   restartable    An asteroid return fires its second burn years after the
    #                  first.  A solid motor cannot be relit, so APCP is
    #                  excluded permanently despite being TRL 9.
    #   propellantless A sail has no mass ratio, so the rocket equation reports
    #                  that it moves any payload for free.  Real sails run
    #                  ~0.1 mm/s² and fall as 1/r²; sizing one needs a
    #                  thrust-limited trajectory solver this module does not
    #                  have.  Excluded rather than allowed to report infinity.
    if config.operational_propellants_only and "status" in pdf.columns:
        pdf = pdf[pdf["status"] == "operational"]
    elif "status" in pdf.columns:
        pdf = pdf[pdf["status"] != "retired"]
    if "restartable" in pdf.columns:
        pdf = pdf[_truthy(pdf["restartable"], default=True)]
    if "propellantless" in pdf.columns:
        pdf = pdf[~_truthy(pdf["propellantless"], default=False)]
    if config.candidate_propellants is not None:
        pdf = pdf[pdf["name"].isin(config.candidate_propellants)]

    propellant_rows = [_row_to_dict(row) for _, row in pdf.iterrows()]
    # v1.14.1: the four scalars the candidate pre-filter needs depend only on
    # the propellant row and the config, so they are derived here, once per
    # run, on the same dict every asteroid will read, rather than re-parsed out
    # of the row for each of the ~1.4 billion (asteroid × candidate) tuples a
    # full catalog produces.  Stashed on the row itself so it crosses the worker
    # boundary with everything else; `_PREFILTER_CONSTS_KEY` is private and
    # nothing else in the module reads it.
    for propellant in propellant_rows:
        propellant[_PREFILTER_CONSTS_KEY] = _prefilter_propellant_consts(
            propellant, config)
        # v1.14.2: and the six the SIZING path needs, for the same reason and
        # by the same route.  See `_sizing_propellant_consts`.
        propellant[_SIZING_CONSTS_KEY] = _sizing_propellant_consts(
            propellant, config)
        # v1.17.5: and the ISRU feed pair, for the same reason and by the same
        # route.  See `_isru_propellant_consts`.
        propellant[_ISRU_CONSTS_KEY] = _isru_propellant_consts(propellant)
    vehicle_rows = [_row_to_dict(v) for _, v in vdf.iterrows()]
    for vehicle in vehicle_rows:
        vehicle[_VEHICLE_CONSTS_KEY] = _vehicle_consts(vehicle)
    return [
        (vehicle, propellant)
        for vehicle in vehicle_rows
        for propellant in propellant_rows
    ]


# ── The ladder is a function of `trips` and the config  (v1.17.6) ──────────
# `programme_options` builds ~42 tuples, and `fleet_refinement` its four more,
# once per SURVIVING CANDIDATE: 10,741 times on a 150-row beneficiated+searched
# sample, for a list whose only asteroid-dependent input is `trips`, which is
# `min(life / stay, max_trips)` and therefore one of a handful of small
# integers.  Together they measured ~3.6% of that cell.
#
# The sorted fleet ladder the refinement pass needs is derived from the same
# tuples (`sorted({f for _n, f, _w in programmes})`), so it is cached alongside
# rather than rebuilt per candidate.
#
# ⚠️  Private, and `programme_options` is untouched.  That function is the
# single readable statement of the search's shape and the entry point for
# anyone outside this loop; this only stops the loop asking it the same
# question 10,741 times.
#
# ⚠️  The lists are shared, not copied, and nothing may mutate them; both are
# iterated and indexed and nothing more.  Keyed on the config VALUES the two
# functions read rather than on `id(config)`, so a config edited between runs
# is answered correctly (the same argument `_selects_on_profit` makes).
_PROGRAMME_LADDER_CACHE: Dict[Tuple[Any, ...],
                              Tuple[List[Tuple[int, int, int]], List[int]]] = {}
_FLEET_REFINEMENT_CACHE: Dict[Tuple[int, Tuple[int, ...]], List[int]] = {}


def _programme_ladder_cached(
    rig_trips: Optional[Tuple[int, int, Optional[int]]], config: CalcConfig,
    market_mode: Optional[str] = None,
) -> Tuple[List[Tuple[int, int, int]], List[int]]:
    """`(programme_options(...), sorted fleet ladder)`, memoised.

    `market_mode` arrives resolved from `_evaluate_combo_at_ratio`, which has
    already paid for it; deriving it again here doubled the hot-path cost this
    release introduced.  None means "derive it", for a standalone caller.
    """
    if market_mode is None:
        market_mode = _market_mode(config)
    key = (rig_trips[0] if rig_trips is not None else None,
           int(config.nre_amortization_missions),
           bool(config.model_programme_calendar),
           bool(config.optimise_programme_scale),
           int(config.max_fleet_ships),
           int(config.programme_search_steps),
           # v1.21.0: `single_mission` collapses the ladder to one rung, so the
           # market model is part of what this memo answers.  A memo keyed on
           # the config VALUES a function reads, never on `id(config)`.
           market_mode)
    hit = _PROGRAMME_LADDER_CACHE.get(key)
    if hit is None:
        programmes = programme_options(rig_trips, config, market_mode)
        hit = _PROGRAMME_LADDER_CACHE[key] = (
            programmes, sorted({f for _n, f, _w in programmes}))
    return hit


def _fleet_refinement_cached(f_best: int, ladder: List[int]) -> List[int]:
    """`fleet_refinement(f_best, ladder, ladder[0], ladder[-1])`, memoised."""
    key = (f_best, tuple(ladder))
    hit = _FLEET_REFINEMENT_CACHE.get(key)
    if hit is None:
        hit = _FLEET_REFINEMENT_CACHE[key] = fleet_refinement(
            f_best, ladder, ladder[0], ladder[-1])
    return hit


def _prefilter_probe(
    asteroid_row: Row,
    combos:       List[Tuple[Dict[str, Any], Dict[str, Any]]],
    config:       CalcConfig,
) -> Tuple[int, int]:
    """(candidates considered, candidates kept) for one asteroid.

    Mirrors the loop nest in `evaluate_asteroid` exactly, same axes, same
    order, same test, so the printed rate describes the search that is about
    to run rather than an approximation of it.  Diagnostic only; nothing in the
    pipeline consumes the answer.
    """
    window_wait_yr = 0.0
    if config.model_launch_windows:
        a_dest_au = window_phasing_au(config.delivery_destination)
        window_wait_yr = 0.5 * synodic_period_yr(
            asteroid_row.get("semi_major_axis_au"), a_dest_au)

    dv_options   = asteroid_dv_options(asteroid_row, config)
    isru_allowed = (config.use_isru_return_propellant
                    and config.optimise_architecture_per_asteroid)

    seen = kept = 0
    for vehicle, propellant in combos:
        isru_modes = [False]
        if config.use_isru_return_propellant and isru_feed_kg_per_kg_propellant(
                asteroid_row, propellant, config) is not None:
            isru_modes = [False, True] if isru_allowed else [True]
        pf_consts = propellant.get(_PREFILTER_CONSTS_KEY)
        vconsts   = vehicle.get(_VEHICLE_CONSTS_KEY)
        leo_cap   = (vconsts[1] if vconsts is not None
                     else _vehicle_consts(vehicle)[1])
        for dv_opt in dv_options:
            for isru in isru_modes:
                seen += 1
                # `_combo_can_close` rather than the split form the search uses
                # (v1.14.2): this is a diagnostic, it runs once per asteroid, and
                # composing the two halves here would put a third copy of the
                # test in the file.  The one-call form is defined as exactly that
                # composition, so the rate it reports is still the search's.
                if pf_consts is not None and _combo_can_close(
                        leo_cap, pf_consts,
                        float(dv_opt["dv_out_m_s"]), float(dv_opt["dv_ret_m_s"]),
                        (config.heat_shield_frac_of_payload
                         if bool(dv_opt["aero"]) else 0.0),
                        isru, window_wait_yr, config):
                    kept += 1
    return seen, kept


def evaluate_asteroid(
    asteroid_row: Row,
    catalogs:     Dict[str, pd.DataFrame],
    config:       CalcConfig,
    combos:       Optional[List[Tuple[Dict[str, Any], Dict[str, Any]]]] = None,
) -> Optional[dict]:
    """Pick the highest-profit mission for one asteroid.

    The search space is (vehicle × propellant × return mode × propellant
    sourcing × concentration ratio), and every axis of it is resolved for THIS
    asteroid.  v1.10.0 added the last two architecture axes: before it, the
    return mode and whether to make propellant on site were set once for the
    whole catalog, which meant a body whose best mission was an aerocaptured
    return was flown propulsively, or vice versa, purely because of what some
    other asteroid needed.

    Returns a single result dict (best mission) or None if nothing is viable.

    `combos` is the precomputed candidate cross-join from candidate_combos().
    Left as None it is rebuilt per call, correct but slow, so the main loop
    builds it once and passes it in.

    `asteroid_row` may be a Series or a dict; it is normalised to a dict here,
    once, because the search below reads it thousands of times.
    """
    asteroid_row = _row_to_dict(asteroid_row)

    minerals = catalogs["minerals"]
    ops_df   = catalogs["ops"]

    # Bulk $/kg for this asteroid's blended composition
    bulk_value = asteroid_bulk_value_usd_per_kg(asteroid_row, minerals)
    if bulk_value <= 0:
        return None

    # Everything about this BODY that the mission search would otherwise
    # re-derive per candidate: mineable mass, throughput cap, launch-window
    # wait, ops constants, dark period, eclipse-corrected specific power
    # (v1.14.1).  None means no usable mass, which no candidate could rescue.
    ctx = asteroid_context(asteroid_row, ops_df, config)
    if ctx is None:
        return None
    # Purity bound for beneficiation, the richest concentrate obtainable.
    # Computed once per asteroid rather than per combo; it depends only on
    # composition and prices.
    # Phase table for the load optimiser, and the purity ceiling for reporting.
    # Both depend only on composition and prices, so compute once per asteroid
    # rather than once per (vehicle x propellant) combo.
    # v1.7.0: the phase table is needed even without beneficiation, because
    # the market model prices each commodity in the haul separately.
    phases  = asteroid_phase_table(asteroid_row, minerals)
    markets = market_table(minerals)
    # v1.21.0.  A per-RUN config value, resolved beside `markets` and threaded
    # the same way.  Asked once per CANDIDATE it was 332 calls per evaluable
    # row and ~47 s of a full beneficiated cell; asked here it is one.
    market_mode = _market_mode(config)
    best_phase_value = (asteroid_best_phase_usd_per_kg(asteroid_row, minerals)
                        if config.use_beneficiation else bulk_value)

    # Return modes worth flying to this body, each with its own best
    # rendezvous apsis already resolved against the destination.
    dv_options = asteroid_dv_options(asteroid_row, config)

    if combos is None:
        combos = candidate_combos(catalogs, config)

    # Whether to make return propellant on site is a (target × propellant)
    # question; it needs water in the rock AND a stage that can burn what
    # water makes, so it is decided inside the combo loop rather than here.
    isru_allowed = (config.use_isru_return_propellant
                    and config.optimise_architecture_per_asteroid)

    # ── Power sources worth pricing for this body (v1.14.0) ──────────────────
    # A radioisotope plant is only ever a candidate where it would be LIGHTER
    # than photovoltaics, which depends on the body's distance and, since the
    # eclipse term, on its rotation.  Both are properties of the asteroid, so
    # the filter is resolved once here rather than per candidate mission, and
    # inner-system bodies never pay for a second pass.
    #
    # `power_source_for_target` keeps its job as the MASS comparator; what
    # changed in v1.14.0 is that its answer generates a candidate instead of
    # being the decision.  Probed at 1 W, any positive draw under the ceiling
    # answers "could nuclear ever be lighter here", and the ceiling itself is
    # enforced per candidate against the real draw.
    power_modes = ["solar"]
    if config.allow_rtg_power:
        (_dw, _bw, _base_w, _ee, _ekw,
         _rtg_w, _ppu, _df, _swh, _seta, _bdh, _cpk) = _ops_sizing_constants(ops_df)
        _bare = solar_specific_power_w_per_kg(
            asteroid_row.get("semi_major_axis_au"), _base_w)
        _dark, _ = dark_period_hours(
            asteroid_row.get("rotation_period_h"),
            _df if config.model_eclipse_power else 0.0,
            config.default_rotation_period_h, config.max_dark_period_h,
        )
        _eff, _ = eclipse_effective_w_per_kg(
            _bare, _dark, _df if config.model_eclipse_power else 0.0,
            _swh, _seta, _bdh,
        )
        if power_source_for_target(
                _eff, _rtg_w, 1.0, config.rtg_max_power_w)[1] == "rtg":
            power_modes.append("rtg")

    # ── Candidate pre-filter (v1.14.1) ───────────────────────────────────────
    # The launch-window wait is part of the shortest stay the sizing loop can
    # settle on, so the pre-filter has to price boil-off at the same hold the
    # loop's first pass would.  Taken from `ctx` rather than recomputed, so the
    # two cannot drift.
    prefilter      = bool(getattr(config, "prune_infeasible_combos", True))
    window_wait_yr = ctx.window_wait_yr

    # Keep the best candidate under the selection objective; see
    # selection_key for why that is not simply the highest profit.
    # Whether ISRU chemistry closes is a (target × PROPELLANT) question and the
    # combo grid is vehicle-major, so asking it per combo asked it once per
    # vehicle: 36 times for each of the 41 propellant rows, for every asteroid
    # in the catalog.  Memoised on the propellant's identity, which is stable:
    # `candidate_combos` builds one dict per propellant row and shares it across
    # every vehicle pairing (v1.14.1).
    # ⚠️  v1.17.6: ONE entry carrying everything the loop below reads off a
    # propellant, not four lookups for four of them.  The grid is vehicle-major,
    # so `isru_modes`, the two pre-filter constant tuples and the identity key
    # were each resolved once per (vehicle × propellant): 714,000 lookups per
    # 2,000 rows for 21 propellants' worth of answers.  Same shape as
    # `sat_by_fleet` and `rig_by_share` in the ladder: the question was asked at
    # a finer granularity than it has answers.
    prop_cache: Dict[int, Tuple[List[bool], Any, Any, int]] = {}
    # And the vehicle-independent half of the pre-filter, for the same reason
    # (v1.14.2).  Keyed by (propellant identity × Δv option × ISRU), which is
    # everything `_combo_close_terms` reads, so seventeen vehicles now share one
    # evaluation instead of recomputing it each.  `dv_options` is this asteroid's
    # own list, so the index is a stable key within this call.
    close_terms_cache: Dict[Tuple[int, int, bool],
                            Optional[Tuple[bool, float, float, float]]] = {}

    # v1.17.6: the Δv options resolved to plain scalars once per asteroid.  All
    # three call sites below re-read them out of the dict and re-ran `float()` /
    # `bool()` / `str()` on every (combo × Δv × ISRU) iteration, for a list this
    # asteroid has two or three entries in.  Values and types are unchanged; only
    # the conversions stop repeating.
    dv_resolved = [
        (i,
         float(o["dv_out_m_s"]),
         float(o["dv_ret_m_s"]),
         (config.heat_shield_frac_of_payload if bool(o["aero"]) else 0.0),
         bool(o["aero"]),
         str(o["rendezvous_apsis"]))
        for i, o in enumerate(dv_options)
    ]

    best     = None
    best_key = (-np.inf, -np.inf)
    for vehicle, propellant in combos:
        pkey  = id(propellant)
        pinfo = prop_cache.get(pkey)
        if pinfo is None:
            isru_modes = [False]
            if config.use_isru_return_propellant and isru_feed_kg_per_kg_propellant(
                    asteroid_row, propellant, config) is not None:
                # Feasible here.  Price both when searching; otherwise take ISRU
                # as the config's instruction and fly it wherever it is possible.
                isru_modes = [False, True] if isru_allowed else [True]
            # `candidate_combos` attaches these, but a caller that hand-builds
            # `combos` will not have.  Derive on demand rather than treating the
            # missing key as "no usable Isp"; that reads as infeasible and would
            # prune the ENTIRE search silently, which is the quiet-wrong-answer
            # failure this repo keeps finding.  Absent means unknown, not dead.
            if prefilter and _PREFILTER_CONSTS_KEY not in propellant:
                propellant[_PREFILTER_CONSTS_KEY] = _prefilter_propellant_consts(
                    propellant, config)
            # v1.17.4: the pre-filter's second stage sizes the electric stage, so
            # it reads the SIZING constants rather than the pre-filter's four.
            # `candidate_combos` attaches these; a caller that hand-builds
            # `combos` will not have, and absent means unknown rather than dead, 
            # so the second stage is skipped rather than allowed to refute on a
            # default.
            pinfo = prop_cache[pkey] = (
                isru_modes,
                propellant.get(_PREFILTER_CONSTS_KEY) if prefilter else None,
                propellant.get(_SIZING_CONSTS_KEY) if prefilter else None,
                pkey,
            )
        isru_modes, pf_consts, sizing_consts, pkey = pinfo
        vconsts   = vehicle.get(_VEHICLE_CONSTS_KEY)
        if vconsts is None:
            vconsts = vehicle[_VEHICLE_CONSTS_KEY] = _vehicle_consts(vehicle)
        _fairing, leo_cap, leo_ok = vconsts
        for dv_i, dv_out, dv_ret, dv_tps, dv_aero, dv_apsis in dv_resolved:
            for isru in isru_modes:
                # Sits ABOVE the power-source loop on purpose: pass 1 of the
                # sizing loop runs at zero plant mass, so it cannot tell the two
                # power sources apart and would refute both identically.
                #
                # pf_consts is None only when the propellant states no usable
                # Isp, which `max_return_payload_kg` rejects on entry too, so
                # pruning it here agrees with the solver rather than pre-empting
                # it.
                #
                # v1.14.2 splits the test at the vehicle boundary; see
                # `_combo_close_terms`.  The composition is exactly
                # `_combo_can_close`, in the same operations in the same order.
                if prefilter:
                    if pf_consts is None or not leo_ok:
                        continue
                    ckey  = (pkey, dv_i, isru)
                    terms = close_terms_cache.get(ckey, _UNCACHED)
                    if terms is _UNCACHED:
                        terms = _combo_close_terms(
                            pf_consts, dv_out, dv_ret, dv_tps,
                            isru, window_wait_yr, config)
                        close_terms_cache[ckey] = terms
                    if terms is None or not _closes_with(leo_cap, terms):
                        continue
                    # ── Stage 2 (v1.17.4) ────────────────────────────────────
                    # Stage 1 refutes at pass 1 of the sizing loop, which flies
                    # no electric stage because pass 1 is what SIZES one.  On
                    # the real population 74.3% of the candidates that get past
                    # stage 1 then die on pass 2, when that stage becomes mass,
                    # and they die identically at every concentration ratio
                    # and every power source, because the stage is sized off a
                    # cascade that can see neither.
                    #
                    # Sits here rather than inside `evaluate_combo` for exactly
                    # that reason: one evaluation per (vehicle × propellant ×
                    # Δv × ISRU) replaces one per ratio per power source, which
                    # is ~8 to ~16 of them.  See the function for why refusing
                    # here is a decision rather than a guess.
                    if sizing_consts is not None and not _closes_carrying_its_own_stage(
                            leo_cap, sizing_consts, ctx.ops,
                            ctx.solar_w_per_kg, ctx.structure_frac,
                            window_wait_yr, dv_out, dv_ret, dv_tps,
                            isru, config):
                        continue
                for power_mode in power_modes:
                    result = evaluate_combo(
                        asteroid_row, vehicle, propellant,
                        bulk_value, dv_out, dv_ret,
                        ops_df, config,
                        best_phase_value_per_kg=best_phase_value,
                        phases=phases, markets=markets,
                        market_mode=market_mode,
                        aero=dv_aero, isru=isru,
                        rendezvous_apsis=dv_apsis,
                        power_mode=power_mode, ctx=ctx,
                    )
                    if result is None:
                        continue
                    key = selection_key(result, config)
                    if key > best_key:
                        best_key = key
                        best     = result

    if best is None:
        return None

    # Tag with asteroid identifiers + carried-through fields
    best.update({
        "designation":              asteroid_row.get("designation"),
        "name":                     asteroid_row.get("name"),
        "spectral_type":            asteroid_row.get("spectral_type"),
        "comp_group":               asteroid_row.get("comp_group"),
        "diameter_km":              asteroid_row.get("diameter_km"),
        "estimated_mass_kg":        asteroid_row.get("estimated_mass_kg"),
        "density_gcm3":             asteroid_row.get("density_gcm3"),
        "semi_major_axis_au":       asteroid_row.get("semi_major_axis_au"),
        "is_neo":                   asteroid_row.get("is_neo"),
        "comp_metal_fraction":      asteroid_row.get("comp_metal_fraction"),
        "comp_silicate_fraction":   asteroid_row.get("comp_silicate_fraction"),
        "comp_carbon_fraction":     asteroid_row.get("comp_carbon_fraction"),
        "comp_ice_fraction":        asteroid_row.get("comp_ice_fraction"),
        "comp_pgm_enrichment":      asteroid_row.get("comp_pgm_enrichment"),
    })

    return best


# ─────────────────────────────────────────────────────────────────────────────
# PARALLEL EVALUATION  (v1.10.1)
# ─────────────────────────────────────────────────────────────────────────────
# Asteroids do not interact.  `evaluate_asteroid` reads the reference catalogs,
# writes nothing outside its own return value, and touches no global except
# three identity-keyed lookup caches, so the main loop is embarrassingly
# parallel and had been running on one core.
#
# What makes this more than a one-line change is Windows.  There is no fork, so
# every worker is a fresh interpreter that has to reconstruct the parent before
# it can unpickle the first task, and it does that by importing the parent's
# __main__.  Which module that is depends on how the pipeline was launched, and
# one of the three launch paths is actively hostile; see _spawn_environment.

_WORKER_CTX: Dict[str, Any] = {}


def _worker_init(
    minerals: pd.DataFrame,
    ops:      pd.DataFrame,
    combos:   List[Tuple[Dict[str, Any], Dict[str, Any]]],
    config:   CalcConfig,
) -> None:
    """Seed one worker with the read-only state every chunk needs.

    Sent once per worker rather than once per chunk.  Only two of the upstream
    catalogs reach the inner search; minerals (prices, market depths) and ops
    (Module 3's reference rows), and both are a few dozen rows.  The asteroid
    catalog is never shipped whole; a worker only ever receives the block it is
    about to evaluate.
    """
    _WORKER_CTX["catalogs"] = {"minerals": minerals, "ops": ops}
    _WORKER_CTX["combos"]   = combos
    _WORKER_CTX["config"]   = config


# Rows are handed to the search a BLOCK at a time, not one at a time (v1.17.4).
# 256 is the same figure `_chunk_frame` floors a worker block at, and for the
# same reason: big enough that the per-call overhead disappears, small enough
# that nothing large is ever materialised.
_ROW_DICT_BLOCK = 256


def _iter_row_dicts(df: pd.DataFrame, block: int = _ROW_DICT_BLOCK):
    """Yield each row of `df` as a plain dict, converting a block at a time.

    v1.17.4.  `iterrows()` builds a pandas Series per row and `_row_to_dict`
    then throws it away: 67.3 µs a row on the 46-column catalog, against
    **17.0 µs** for `DataFrame.to_dict("records")` over a block. That is ~50 µs
    on every row of the catalog whether or not it turns out to be evaluable:
    ~67-78 s on a full cislunar pass, which is ~5-6% of the raw cell.

    ⚠️  Value- AND type-preserving, which is the only reason it is allowed.
    Checked cell by cell over a 20,000-row sample: **zero value mismatches and
    zero type mismatches**. Both routes unbox numpy scalars to their Python
    equivalents, and `np.float64` IS a C double; the same argument v1.10.1
    made when it introduced `_row_to_dict`, and the four-cell bit-identity diff
    is what confirms it end to end.

    ⚠️  Block at a time, NOT `df.to_dict("records")` in one go. The serial path
    hands this the whole 1.55 M-row catalog, and materialising 1.55 M dicts at
    once would cost several GB for no gain; the conversion is amortised at
    256 rows just as well as at 1.5 million.
    """
    n = len(df)
    for i in range(0, n, block):
        for row in df.iloc[i:i + block].to_dict("records"):
            yield row


def _evaluate_chunk(chunk: pd.DataFrame) -> List[dict]:
    """Evaluate one contiguous block of asteroids inside a worker.

    Converting rows here rather than in the parent is deliberate: the cost
    lands on a worker instead of on the single core the parent has to itself,
    and both paths hand `evaluate_asteroid` identical input because both go
    through `_iter_row_dicts`.
    """
    catalogs = _WORKER_CTX["catalogs"]
    combos   = _WORKER_CTX["combos"]
    config   = _WORKER_CTX["config"]

    out: List[dict] = []
    for row in _iter_row_dicts(chunk):
        result = evaluate_asteroid(row, catalogs, config, combos)
        if result is not None:
            out.append(result)
    return out


# Measured on the reference machine (6 physical / 12 logical cores, working
# copy on Google Drive), catalog v1.0.9, cislunar, beneficiated:
#
#   pool startup      6.8 s for 6 workers, 13.4 s for 12 -- ~1.1 s each, and
#                     LINEAR, so every extra worker costs its own second
#                     before it does any work.  Import time, not process
#                     creation:
#                     each worker reads and executes the 590 kB master.py
#                     twice (once as __mp_main__, once when unpickling), and
#                     on a Drive File Stream working copy those reads
#                     serialise.  A local-disk checkout starts faster.
#   per asteroid      ~29 ms beneficiated, ~3 ms raw
#   scaling net of    2 -> 1.95x   4 -> 3.43x   6 -> 4.48x
#   startup           8 -> 4.89x  12 -> 5.24x
#   full catalog      2,120 s -> 137 s beneficiated, 140 s -> 33 s raw
#
# So the useful ceiling is set by the six PHYSICAL cores (hyperthreading adds
# ~17% on this branch-heavy pure-Python workload, not 2x), and whether it is
# worth going near it depends entirely on how much work there is.  At 3,000
# beneficiated rows, 12 workers is SLOWER end to end than 6 -- 28.5 s against
# 25.3 s -- because the extra six spend longer starting than they save.
#
# Rows one worker should get before it is worth starting: enough that its
# share of the search outweighs its startup by ~10x.  Raw asteroids are ~9x
# cheaper to evaluate than beneficiated ones, so they need proportionally
# more.  The raw threshold is the more conservative of the two on purpose --
# a raw destination now finishes in about half a minute either way, so there
# is nothing to win there and a pool that fails to repay itself to lose.
_ROWS_PER_WORKER_BENEFICIATED = 400
_ROWS_PER_WORKER_RAW          = 6_000


def _resolve_worker_count(config: CalcConfig, n_rows: int) -> int:
    """How many worker processes to run.  1 means take the serial path.

    An explicit `parallel_workers` is obeyed (clamped to the CPU count and to
    the number of rows).  Auto mode additionally refuses to start workers that
    cannot repay their own startup, which is what keeps a 400-row interactive
    run from spending thirteen seconds building a pool for nine seconds of
    work.
    """
    cpus      = os.cpu_count() or 1
    requested = int(getattr(config, "parallel_workers", 0) or 0)

    n = cpus if requested <= 0 else requested
    n = max(1, min(n, cpus, n_rows))
    if requested <= 0:
        per_worker = (_ROWS_PER_WORKER_BENEFICIATED if config.use_beneficiation
                      else _ROWS_PER_WORKER_RAW)
        n = min(n, max(1, n_rows // per_worker))
    return max(1, n)


def _chunk_frame(work_df: pd.DataFrame, n_workers: int) -> List[pd.DataFrame]:
    """Split the catalog into blocks sized for load balance and overhead both.

    Asteroids are not equally expensive, the number of viable return modes,
    whether ISRU is even possible, and the width of the concentration sweep all
    vary per body, so one block per worker would leave most cores idle waiting
    on whichever block drew the expensive tail.  Aim for ~16 blocks per worker,
    and floor the block at 8 rows so pickling never starts to rival a ~60 ms
    unit of work.
    """
    size = max(8, min(len(work_df) // (n_workers * 16), 256))
    return [work_df.iloc[i:i + size] for i in range(0, len(work_df), size)]


@contextlib.contextmanager
def _spawn_environment():
    """Hold the two things a spawned worker needs to come up correctly.

    **The main module.**  multiprocessing rebuilds the parent in each worker
    from `__main__`: it prefers `__main__.__spec__.name` and imports that, and
    falls back to executing `__main__.__file__`.  Run as a script, `__main__`
    IS this file and the fallback does the right thing.  Driven from `ui.py` it
    does not, Streamlit installs a synthetic module named `__main__` whose
    `__file__` points at `ui.py`, so the fallback runs the entire Streamlit app
    inside every worker.  That is not a theoretical hazard; a three-worker pool
    was observed executing the app three times before this was written.
    Pointing `__spec__` at this module instead makes each worker import the
    pipeline, which is what it needs anyway.

    **Quiet workers.**  That import replays the startup banner: 60 lines per
    worker, 700+ for a full pool, interleaved into the run log the UI is
    parsing.  The env var is read at the top of this file by the child.

    Both are held for the pool's whole lifetime rather than just its
    construction, so that a worker respawned mid-run comes up the same way as
    its siblings.  The restore writes back to the module object captured here,
    not to whatever `sys.modules["__main__"]` says later, so a concurrent
    Streamlit rerun swapping in a fresh `__main__` cannot be clobbered by it.
    """
    prev_env = os.environ.get("ASTEROID_PIPELINE_WORKER")
    os.environ["ASTEROID_PIPELINE_WORKER"] = "1"

    main = sys.modules.get("__main__")
    own  = sys.modules.get(__name__)
    spec = getattr(own, "__spec__", None)
    # Leave it alone when __main__ is already this module (running as a script),
    # or already carries a spec of its own (`python -m ...`), or when we have no
    # spec to offer (this module is itself __main__, or was exec'd).
    pin = (main is not None and own is not None and main is not own
           and spec is not None and getattr(main, "__spec__", None) is None)
    if pin:
        main.__spec__ = spec
    try:
        yield
    finally:
        if pin:
            main.__spec__ = None
        if prev_env is None:
            os.environ.pop("ASTEROID_PIPELINE_WORKER", None)
        else:
            os.environ["ASTEROID_PIPELINE_WORKER"] = prev_env


def _evaluate_in_parallel(
    work_df:     pd.DataFrame,
    catalogs:    Dict[str, pd.DataFrame],
    config:      CalcConfig,
    combos:      List[Tuple[Dict[str, Any], Dict[str, Any]]],
    n_workers:   int,
    on_progress,
) -> Optional[List[dict]]:
    """Run the per-asteroid search across `n_workers` processes.

    Returns the result list, or None if no pool could be started; the caller
    then falls back to the serial loop.  Only pool CONSTRUCTION is guarded that
    way: a failure once the work is under way propagates, because a bug in the
    search silently costing half an hour of redone serial work is worse than a
    crash.

    Chunks are consumed with `imap`, which yields in submission order, so the
    result list is exactly what the serial loop would have appended.  That
    matters beyond tidiness: the caller sorts on `profit_usd` with pandas'
    default quicksort, which is not stable, so a different arrival order could
    permute tied rows and make two runs of the same code disagree.
    """
    chunks = _chunk_frame(work_df, n_workers)

    with _spawn_environment():
        try:
            pool = mp.get_context("spawn").Pool(
                processes   = n_workers,
                initializer = _worker_init,
                initargs    = (catalogs["minerals"], catalogs["ops"],
                               combos, config),
            )
        except (OSError, ValueError, RuntimeError, ImportError) as exc:
            print(f"     WARN   Could not start worker processes ({exc}) - "
                  f"evaluating in a single process")
            return None

        results: List[dict] = []
        try:
            for chunk, found in zip(chunks, pool.imap(_evaluate_chunk, chunks)):
                results.extend(found)
                on_progress(len(chunk))
            pool.close()
        except BaseException:
            pool.terminate()
            raise
        finally:
            pool.join()
    return results


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def build_profitability_catalog(config: CalcConfig = CALC_CONFIG) -> pd.DataFrame:
    """Run the full Module 4 calculation pipeline."""
    t0 = datetime.now()
    print("=" * 75)
    print("    PROFITABILITY PIPELINE - MODULE 4")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  v{config.pipeline_version}")
    print("=" * 75)

    # ── Step 1, Load catalogs ───────────────────────────────────────────────
    catalogs = load_all_catalogs(config)

    # ── Step 2, Integrity checks ────────────────────────────────────────────
    integrity_check(catalogs)
    destination_check(catalogs, config)
    market_config_check(config)

    # ── Step 3, Iterate asteroids ───────────────────────────────────────────
    asteroids = catalogs["asteroids"]

    # Filter to rows with the minimum data needed to be evaluable
    needed_cols = ["estimated_mass_kg", "comp_metal_fraction",
                   "comp_silicate_fraction", "comp_carbon_fraction",
                   "comp_ice_fraction"]
    missing_cols = [c for c in needed_cols if c not in asteroids.columns]
    if missing_cols:
        print(f"\nFAIL  Asteroid catalog missing required columns: {missing_cols}")
        print("     Has Module 1 been re-run with enrich_composition?  Aborting.")
        return pd.DataFrame()

    mass_ok = pd.to_numeric(asteroids["estimated_mass_kg"], errors="coerce") > 0
    work_df = asteroids[mass_ok].copy()
    print(f"\n  Evaluating {len(work_df):,} asteroids with positive mass "
          f"(skipped {len(asteroids) - len(work_df):,} without)")

    if config.eval_row_cap and len(work_df) > config.eval_row_cap:
        n_before = len(work_df)
        if config.eval_row_sampling == "head":
            work_df = work_df.head(config.eval_row_cap)
            how = "first N rows"
        else:
            # Evenly-spaced stride across the catalog in its incoming order,
            # which Module 1 sorts by semi-major axis.  `head` therefore sampled
            # only the innermost bodies; a stride spans the whole belt.
            #
            # np.linspace over positions (not a fixed ::k step) so the requested
            # count is hit exactly for any cap, and the endpoints are included.
            # Deterministic, so two runs of identical code still produce
            # identical CSVs -- the property v1.10.1 exists to protect.
            idx = np.unique(
                np.linspace(0, n_before - 1, config.eval_row_cap).round().astype(int)
            )
            work_df = work_df.iloc[idx]
            how = f"every ~{n_before / max(len(idx), 1):.1f}th row, evenly spaced"
        print(f"        Capped at {len(work_df):,} of {n_before:,} rows "
              f"({how}; eval_row_cap / eval_row_sampling in CALC_CONFIG)")

    # Candidate (vehicle × propellant) grid is config-driven, not asteroid-
    # driven, build it once and hand it to every evaluation.
    combos = candidate_combos(catalogs, config)
    if not combos:
        print("\nFAIL  No candidate vehicle x propellant combinations after "
              "filtering - check operational_vehicles_only / candidate_* in CALC_CONFIG.")
        return pd.DataFrame()
    print(f"       {len(combos):,} vehicle x propellant combinations per asteroid")

    # ── How much the pre-filter is actually removing (v1.14.1) ───────────────
    # Probed rather than tallied.  A running count would have to come back from
    # every worker, which means changing what a chunk returns, and the number is
    # a property of the POPULATION, a stride probe answers it to well inside
    # the precision anyone reads it at.
    #
    # Print it because the failure mode is silence.  If a future Δv model, ops
    # table or vehicle set makes the pre-filter stop firing, the run simply gets
    # slower and nothing says why; and a rate that jumps to ~100% means it is
    # eating the catalog, which is the shape of a genuine bug.  Both are visible
    # here and nowhere else.
    if config.prune_infeasible_combos and len(work_df) > 0:
        probe_idx = np.unique(
            np.linspace(0, len(work_df) - 1, min(200, len(work_df)))
            .round().astype(int)
        )
        seen = kept = 0
        for prow in _iter_row_dicts(work_df.iloc[probe_idx]):
            seen_row, kept_row = _prefilter_probe(prow, combos, config)
            seen += seen_row
            kept += kept_row
        if seen:
            print(f"        Pre-filter keeps {kept / seen * 100:.1f}% of "
                  f"candidates ({seen - kept:,} of {seen:,} pruned on a "
                  f"{len(probe_idx)}-row probe; prune_infeasible_combos)")

    n = len(work_df)

    # Lightweight progress report every ~1%.
    #
    # This was every 10% until the UI needed to draw a progress bar off it.
    # A full beneficiated catalog takes ~20 minutes, so ten ticks is one
    # every two minutes, and a bar that sits still that long is
    # indistinguishable from a hung process.  Every 1% costs 100 lines of
    # stdout on a long run, nothing at all on a run under 100 rows, and no
    # measurable time -- the print is dwarfed by evaluate_asteroid().
    #
    # The message FORMAT is load-bearing: ui.py parses "i / n evaluated"
    # out of the stream to size its bar.  Change the wording and the bar
    # silently falls back to indeterminate.
    #
    # v1.10.1: driven by a callback, because the parallel path reports a chunk
    # at a time rather than a row at a time.  Both paths tick the same counter
    # and print the same line; only the granularity differs.
    progress = {"done": 0, "pct": 0}

    def report(rows_done: int) -> None:
        """Tick the evaluated-row counter and print on each whole percent.

        A CALLBACK rather than a loop counter because the parallel path reports
        a chunk at a time and the serial path a row at a time; both tick the
        same counter and print the same line, so only the granularity differs.

        ⚠️  The wording is load-bearing: `ui.py`'s `ProgressScan` regexes
        "i / n evaluated" out of the stream to size its bar, and rewording this
        silently drops the dashboard back to an indeterminate bar.
        """
        progress["done"] += rows_done
        i = progress["done"]
        if n >= 100 and (i * 100) // n != progress["pct"]:
            progress["pct"] = (i * 100) // n
            print(f"     ... {i:,} / {n:,} evaluated  ({progress['pct']}%)")

    results = None
    n_workers = _resolve_worker_count(config, n)
    if n_workers > 1:
        print(f"       {n_workers} worker processes "
              f"({os.cpu_count()} logical CPUs, parallel_workers="
              f"{config.parallel_workers or 'auto'})")
        results = _evaluate_in_parallel(
            work_df, catalogs, config, combos, n_workers, report,
        )

    if results is None:                       # serial path, or no pool started
        progress["done"] = progress["pct"] = 0
        results = []
        for asteroid in _iter_row_dicts(work_df):
            result = evaluate_asteroid(asteroid, catalogs, config, combos)
            if result is not None:
                results.append(result)
            report(1)

    if not results:
        print("\nFAIL  No viable evaluations - every asteroid failed.")
        return pd.DataFrame()

    df = pd.DataFrame(results)

    # ── Step 4, Rank + tag ──────────────────────────────────────────────────
    df["catalog_date"]     = t0.strftime("%Y-%m-%d")
    df["pipeline_version"] = config.pipeline_version
    df = df.sort_values("profit_usd", ascending=False).reset_index(drop=True)

    # Sanity flags for downstream
    df["viable"]      = df["profit_usd"] > 0
    df["profit_M$"]   = df["profit_usd"] / 1e6   # for human-readable preview
    df["gross_M$"]    = df["gross_value_usd"] / 1e6
    df["cost_M$"]     = df["total_cost_usd"] / 1e6

    # ── Step 5, Export ──────────────────────────────────────────────────────
    out_path = os.path.join(config.output_dir, config.output_filename)
    # lineterminator is pinned because pandas defaults it to os.linesep,
    # which makes a catalog written on Linux differ from the same catalog
    # written on Windows in every line, for no model reason.  CRLF is the
    # existing Windows output, so pinning it changes nothing here.
    df.to_csv(out_path, index=False, lineterminator="\r\n")
    print(f"\n       Profitability catalog -> {out_path}  ({len(df):,} rows)")

    # ── What the architecture search actually chose ──────────────────────────
    # Worth printing rather than burying in the CSV: if every row picks the
    # same return mode, the search is costing runtime and buying nothing, and
    # you want to know that.  If the split is real, so is the effect.
    if config.optimise_architecture_per_asteroid:
        bits = []
        if "aerocapture_return" in df.columns:
            n_aero = int(df["aerocapture_return"].sum())
            bits.append(f"{n_aero:,} aerocapture / {len(df) - n_aero:,} propulsive")
        if "isru_return" in df.columns and int(df["isru_return"].sum()):
            bits.append(f"{int(df['isru_return'].sum()):,} make their own propellant")
        if "rendezvous_apsis" in df.columns:
            n_peri = int((df["rendezvous_apsis"] == "perihelion").sum())
            if n_peri:
                bits.append(f"{n_peri:,} rendezvous at perihelion")
        if bits:
            print(f"       Architecture chosen: {'  |  '.join(bits)}")

    # ── What the programme search chose (v1.15.0) ────────────────────────────
    # Same argument as the block above, and it matters more here, because the
    # two ways this axis can be reported as a result while being an artefact are
    # both visible from these three numbers:
    #
    #   • EVERY ROW AT THE LADDER'S TOP means `max_fleet_ships` is BINDING, not
    #     bounding.  That happens when nothing pushes back on scale; a payload
    #     whose commodities have no `annual_market_kg` entry gets an infinite
    #     market, market saturation returns 1.0 forever, and the objective is
    #     then monotone in N.  Reporting the top rung of a monotone ladder is
    #     reporting where the loop stopped, and it is exactly the failure
    #     v1.14.0 closed.
    #   • EVERY ROW AT F = 1 means the fleet never wanted to grow, so the axis
    #     is costing runtime and buying nothing.
    if config.optimise_programme_scale and not config.model_rig_service_life:
        print("     WARN   optimise_programme_scale is ON but model_rig_service_life "
              "is OFF, so one rig serves any programme, nothing is ever "
              "concurrent, and the market cannot push back. The search "
              "is refused rather than run - it would report the ladder's top "
              "rung as a result. See programme_options().")
    # v1.21.0.  The SAME failure by the other route, and until this release it
    # was unguarded: the branch above tests one of the two ways to leave the
    # ladder monotone, and `market_model` is the other.  It was never possible
    # to reach before, because the market term was a flag nothing else keyed
    # off; it is a four-valued selector now and two of the four values leave
    # nothing pushing back on N.
    elif config.optimise_programme_scale and _market_mode(config) == "unbounded":
        print("     WARN   market_model is 'unbounded' with optimise_programme_scale "
              "ON, so prices never move, no ceiling binds, and every lever "
              "improves with N. The objective is monotone and every row will "
              "run to max_fleet_ships. That is a DIAGNOSTIC, not a result - "
              "read the fleet column as 'where the loop stopped'.")
    elif config.optimise_programme_scale and "fleet_ships" in df.columns:
        f = df["fleet_ships"]
        at_cap = int((f >= config.max_fleet_ships).sum())
        print(f"       Programme chosen: fleet median {f.median():.0f} ship(s), "
              f"max {f.max():.0f}  |  N median {df['programme_missions'].median():.0f}, "
              f"max {df['programme_missions'].max():.0f}  |  "
              f"{int((f <= 1).sum()):,} single-ship")
        if "trips_per_ship" in df.columns:
            binds = df["rig_trip_limit_binds"]
            print(f"       Rig life: {df['trips_per_ship'].median():.0f} trips median "
                  f"(calendar cap {df['rig_trips_calendar_cap'].median():.0f})  |  "
                  f"cycle bound binds on {binds.mean():.1%} of rows")
        if at_cap:
            print(f"     WARN   {at_cap:,} row(s) ({at_cap/len(df):.1%}) sit AT "
                  f"max_fleet_ships = {config.max_fleet_ships}. The ladder is "
                  f"binding, not bounding - check those rows have a finite "
                  f"market before reading their N as an optimum.")
        # v1.21.0.  The line above has always said "check those rows have a
        # finite market"; under a quantity WALL the run can answer that itself,
        # and it has to, because a wall does not blend the way the elasticity
        # curve did.  A row every ceiling clears is monotone in N again, so the
        # share of rows nothing bound is the real health check on this term.
        #
        # Asked as a QUESTION OF THE POPULATION rather than by naming a
        # destination.  `earth_surface` is the cell this is expected to fire on
        # (its ceilings are terrestrial production, 1e12-1e15 kg/yr, so nothing
        # can bind and it stays monotone in N exactly as it was before this
        # release), but hard-coding that name is the defect calc v1.19.2 fixed:
        # a conditional naming one member of a set instead of asking the set.
        if "market_clearing_fraction" in df.columns:
            bound = int((df["market_clearing_fraction"] < 1.0).sum())
            share = bound / len(df) if len(df) else 0.0
            print(f"       Market ceilings: bound {bound:,} row(s) "
                  f"({share:.1%})  |  median clearing "
                  f"{df['market_clearing_fraction'].median():.4f}")
            if bound == 0:
                print( "     WARN   NO row was bound by a market ceiling, so "
                       "nothing pushed back on programme size anywhere in this "
                       "run. Every N here is the ladder's top rung, not an "
                       "optimum. Expected at earth_surface, whose ceilings are "
                       "world production; anywhere else it means the payloads "
                       "are too small to reach a ceiling, or the destination "
                       "has no annual_market_kg entries.")
            elif share < 0.10 and at_cap:
                print(f"     WARN   only {share:.1%} of rows were bound by a "
                      f"ceiling while {at_cap:,} sit at max_fleet_ships. The "
                      f"unbound rows are monotone in N; read their fleet size "
                      f"as where the loop stopped.")

    n_viable = int(df["viable"].sum())
    elapsed  = (datetime.now() - t0).total_seconds()
    print("\n" + "=" * 75)
    print("  OK  PROFITABILITY ANALYSIS COMPLETE")
    print(f"      Evaluated  : {n:,} asteroids")
    print(f"      Viable     : {n_viable:,}  ({n_viable/n*100:.1f}% turn a profit)")
    print(f"      Unviable   : {n - n_viable:,}")
    print(f"      Elapsed    : {elapsed:.1f}s")
    print("=" * 75)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# QUERY UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def top_profitable(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Top-N most profitable asteroids."""
    return df.sort_values("profit_usd", ascending=False).head(n)


def filter_viable(df: pd.DataFrame) -> pd.DataFrame:
    """Asteroids where at least one (vehicle × propellant) yields positive profit."""
    return df[df["viable"]].copy()


def lookup_asteroid(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Find by designation OR name (case-insensitive substring match).

    regex=False, designations and names carry regex metacharacters ("(1)
    Ceres", "1999 RQ36"), which pandas' default regex=True would interpret
    as a pattern: "(1) CERES" silently matched "1 CERES", and a stray
    bracket raised re.PatternError.  Literal substring is what's wanted.
    """
    q = query.strip().upper()
    mask = df["designation"].astype(str).str.upper().str.contains(
        q, na=False, regex=False)
    if "name" in df.columns:
        mask |= df["name"].astype(str).str.upper().str.contains(
            q, na=False, regex=False)
    return df[mask]


print("\nOK  Helper utilities available:")
print("    top_profitable(catalog, 20)")
print("    filter_viable(catalog)")
print("    lookup_asteroid(catalog, 'Bennu')")




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
        """Where the mined material is sold.

        Valid values are the keys of `DELIVERY_DESTINATIONS`, which is the
        live list and is deliberately not restated here: this docstring was
        still naming three of the seven when it was found.
        """
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
    print("    MASTER ASTEROID PROFITABILITY PIPELINE - v1.30.0")
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
