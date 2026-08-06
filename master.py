# -*- coding: utf-8 -*-
"""Master Asteroid Profitability Pipeline (1.7.0)

End-to-end SELF-CONTAINED pipeline that combines all four modules into a
single runnable file.  Copy-paste into Colab / Jupyter / your script and
run top-to-bottom — the orchestrator at the bottom executes everything.

    Stage 1  →  Asteroid Catalog        (modules/catalog.py 1.0.8)
                JPL SBDB + MP3C + SsODNet + NEOWISE
                + PGM_ENRICHMENT_BY_TYPE per-spectral-type factors
    Stage 2  →  Mineral Value Catalog   (modules/mineral_value.py 1.4.0)
                yfinance live + USGS/LME reference + mineralogy
                + sperrylite / laurite / awaruite / native-pgm phases
                + destination pricing for EVERY commodity
    Stage 3  →  Transportation Data     (modules/transportation.py 1.5.0)
                Launch vehicles + propellants + Δv segments + ops costs
                (UNCREWED autonomous mining — no crew costs)
    Stage 4  →  Profitability Calc      (modules/calc.py 1.6.0)
                Rocket eq cascade + cost cascade + per-asteroid ranking
                + PGM enrichment applied per asteroid (M-type 2×, V-type 0.2×)
                + delivery architecture: earth_surface / leo / cislunar /
                  lunar_surface / mars_surface, plus beneficiation

Mission profile: UNCREWED autonomous mining spacecraft throughout (no
crew costs, no life-support overhead).

DELIVERY DESTINATION — set MINERAL_CONFIG.delivery_destination and
CALC_CONFIG.delivery_destination TO THE SAME VALUE.  Stage 2 decides what a
kilogram sells for; Stage 4 decides what it costs to put it there, and the
answer is only meaningful when they agree.  Stage 4 checks and warns.

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



# ═════════════════════════════════════════════════════════════════════════
# MODULE 1 — ASTEROID CATALOG BUILDER
# ═════════════════════════════════════════════════════════════════════════


# ==============================================================================
#  ASTEROID MINING PIPELINE — MODULE 1: CATALOG BUILDER
#  Google Colab compatible — runs top-to-bottom as a single cell.
#
#  Active sources:
#    • NASA JPL Small-Body Database (SBDB)  — primary backbone (orbital + phys)
#    • MP3C (Observatoire Côte d'Azur)      — physical-properties compilation;
#                                             may be DNS-blocked from some
#                                             Colab runtimes (returns empty
#                                             gracefully if unreachable)
#    • SsODNet ssoBFT (IMCCE)               — Solar-system Best-estimate Table:
#                                             cross-matched best-of-literature
#                                             diameter, albedo, MASS, DENSITY,
#                                             rotation period, taxonomy, and
#                                             orbital elements for ~1.2 M
#                                             bodies.  Bulk-downloaded once
#                                             as a cached parquet file.
#    • NEOWISE Diameters & Albedos V2.0     — IR-measured diameters + V/NIR
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
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import requests
from tqdm.auto import tqdm

# Silence the chronic noise the data libraries emit during a typical run, but
# DON'T globally suppress everything — real RuntimeWarnings (e.g. divide-by-zero
# in our mass calculation) should still surface so we can spot bugs.
for _cat in (DeprecationWarning, FutureWarning, UserWarning):
    warnings.filterwarnings("ignore", category=_cat)

pd.set_option("display.max_columns", None)
# `{:.4g}` (general format) renders small numbers in fixed-point and large ones
# in scientific — so orbital elements still read as e.g. 0.1769 but estimated
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
# ║   ★  USER SETTINGS — EDIT THESE TO TUNE THE PIPELINE  ★                  ║
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
    # `jpl_limit` is also reused as a row cap for the other sources.  Bigger =
    # more complete catalog, slower run.  JPL accepts up to ~250,000.
    # 50,000 covers all numbered asteroids through roughly the year-2000 era;
    # the run takes a couple of minutes and the saved CSV is ~30-40 MB.
    jpl_limit:       int = 50_000  # max rows returned per source
    request_timeout: int = 300     # seconds per HTTP request before giving up (5 min)

    # ─── QUALITY GATES  (enforced in validate_and_filter) ────────────────────
    # `min_diameter_km` drops anything below this size.  Default 0.001 km =
    # 1 metre (essentially "keep everything that has a positive diameter").
    # Bump to e.g. 1.0 to focus on >=1-km bodies.
    min_diameter_km: float = 0.001

    # If True, asteroids with no spectral classification (Bus / Tholen) are
    # rejected.  Useful for compositional studies; False keeps more rows.
    require_spectral_type: bool = False

    # ─── OUTPUT  (where the CSVs land) ───────────────────────────────────────
    # `output_dir` is created at startup if it doesn't exist.  On Colab the
    # default '/content/...' lives in the session sandbox — change to a Drive
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
    cache_max_age_days:  float = 7.0

    # ─── PREVIEW & SUMMARY DISPLAY  (cosmetic, affects stdout only) ──────────
    preview_rows:           int = 10   # rows shown in CATALOG PREVIEW table
    top_n_spectral_types:   int = 20   # types listed in spectral-distribution bars

    # ─── PIPELINE VERSION  (bump when changing the schema) ───────────────────
    # 1.0.3 — initial release with NEOWISE + SsODNet integration
    # 1.0.4 — added PGM_ENRICHMENT_BY_TYPE table + comp_pgm_enrichment column.
    #         Per-spectral-type multiplier for the rare-metal (Pt, Pd, Ru, Ir,
    #         Os, Rh, Au) portion of the metal-fraction value.  Differentiated
    #         core fragments (M / Xe = 2.0×), basaltic crust (V = 0.2×), mantle
    #         fragments (A / R / O = 0.5×).  Consumed by Module 4 v1.3.4.
    # 1.0.6 — lookup_asteroid_catalog() passes regex=False.  Designations and names
    #         carry regex metacharacters, and pandas' str.contains defaults to
    #         regex=True, so the "substring match" the docstring promised was
    #         really a pattern match: lookup_asteroid_catalog(cat, "(1) Ceres")
    #         silently matched "1 Ceres", and any unbalanced bracket raised
    #         re.PatternError.  No other behaviour change.
    # 1.0.5 — removed Asterank source (asterank.com/api).  Dropped:
    #         • fetch_asterank() function + _ASTERANK_* constants
    #         • use_asterank toggle from CatalogConfig
    #         • "Asterank" entry from build_asteroid_catalog's sources dict
    #         • Asterank-only output columns (provisional_des, delta_v_kms,
    #           estimated_value_usd, estimated_profit_usd, accessibility_score,
    #           source_asterank).  Module 4 v1.3.5+ no longer uses these.
    #         Active sources reduced to: JPL SBDB, SsODNet, NEOWISE, MP3C.
    # 1.0.7 — renumbering, no behaviour change.  This project was briefly
    #         developed in two places at once and both shipped different code
    #         as 1.0.6, so that stamp is ambiguous.  The reconciled module is
    #         1.0.7 because it matches neither parent.  Treat any CSV stamped
    #         1.0.6 as undated and re-run rather than trusting the number.
    # 1.0.8 — realism audit: X-complex metal fractions were pre-Psyche.
    #         M-type carried 0.80 metal at 5.30 g/cm³ — the "exposed iron
    #         core" picture.  No M-type has ever been measured near that
    #         density: 16 Psyche is ~3.8-3.9 g/cm³ (Elkins-Tanton 2020,
    #         Siltala & Granvik 2021) against 7.8 for iron meteorite, and
    #         metal content is now put at ~30-60%.  Revised:
    #             type   metal  0.80→0.50   density 5.30→3.90   (M)
    #                    metal  0.75→0.45   density 5.00→3.80   (Xe)
    #                    metal  0.50→0.25   density 3.80→3.60   (Xk)
    #                    metal  0.40→0.30   density 3.50→3.30   (X)
    #                    metal  0.30→0.10   density 3.50→3.20   (E)
    #         Xk/E were independently inconsistent — both are described as
    #         enstatite-dominant, and aubrites are near metal-free.
    #         Fraction sums per type are unchanged, so the v1.3.3 residual
    #         silicate floor behaves exactly as before.  Lowers M-type bulk
    #         value; raises nothing.
    pipeline_version: str = "1.0.8"


# Instantiate and create the output dir.  Edit CATALOG_CONFIG values above this line
# (inside the dataclass) — DO NOT mutate CATALOG_CONFIG fields here, that defeats the
# purpose of having a single editable source of truth.
CATALOG_CONFIG = CatalogConfig()
os.makedirs(CATALOG_CONFIG.output_dir, exist_ok=True)


def _resolve_cache_dir(config: "CatalogConfig") -> str:
    """
    Return the absolute path of the bulk-download cache.

    If `config.cache_dir` is non-empty, use it verbatim.  Otherwise default to
    a stable per-user location under the system tmp dir — this avoids the 526
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

print(f"✅  Configuration loaded — output dir: {CATALOG_CONFIG.output_dir}")
print(f"    Active sources  : "
      f"{', '.join(s for s, on in (('JPL', CATALOG_CONFIG.use_jpl), ('MP3C', CATALOG_CONFIG.use_mp3c), ('SsODNet', CATALOG_CONFIG.use_ssodnet), ('NEOWISE', CATALOG_CONFIG.use_neowise)) if on)}")
print(f"    Fetch limit     : {CATALOG_CONFIG.jpl_limit:,} asteroids per source")
print(f"    Min diameter    : {CATALOG_CONFIG.min_diameter_km} km")
print(f"    Strict taxonomy : {CATALOG_CONFIG.require_spectral_type}")


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

print(f"✅  Taxonomy lookup ready — {len(TAXONOMY_COMPOSITION)} spectral types defined")


# ─────────────────────────────────────────────────────────────────────────────
# PGM ENRICHMENT BY SPECTRAL TYPE  (v1.0.4)
# ─────────────────────────────────────────────────────────────────────────────
# Multiplier applied to the platinum-group-metal (PGM) yields in Module 2's
# "nickel-iron" mineral when valuing an asteroid of this spectral type.
# Baseline 1.0× is calibrated to chondritic / mean-iron-meteorite PGM
# concentration (~37 ppm total PGM+Au in nickel-iron alloy).
#
# Why per-type variation matters:
#   • Differentiated parent bodies (M-type / Xe / E asteroids — fragments
#     of cores or near-core regions) concentrated PGMs into the metal
#     phase during melting, so their nickel-iron grains have ELEVATED PGM
#     vs chondritic average.
#   • Basaltic-crust fragments (V-type, Vesta family) lost their PGM to
#     the core during their parent body's differentiation — their metal
#     grains are PGM-DEPLETED.
#   • Mantle fragments (A, R, O) sit between — partially depleted.
#   • Primitive bodies (C-complex, ordinary chondrites) never differentiated,
#     so PGMs remained uniformly distributed in metal grains → baseline.
#
# These factors only multiply the RARE-METAL portion (Pt, Pd, Ru, Ir, Os,
# Rh, Au) of the nickel-iron yield in Module 4 — base metals (Fe, Ni, Co)
# are unaffected.  Conservative midpoints; the literature variance is huge
# (iron meteorite Ir alone ranges 0.01–19 ppm).

PGM_ENRICHMENT_BY_TYPE: Dict[str, float] = {
    # ── Differentiated core fragments — PGMs concentrated by metal-segregation ──
    "M":  2.0,   # Tholen metallic (e.g. 16 Psyche)
    "Xe": 2.0,   # Bus-DeMeo M-analog
    "Xk": 1.5,   # E-chondrite / aubrite analog, partial differentiation
    "X":  1.5,   # X-complex ambiguous (assume partial)
    "Xc": 1.2,   # low-albedo X — partially carbonaceous
    "E":  1.5,   # Tholen enstatite, aubrite analog

    # ── Mantle / lower-mantle fragments — partial PGM depletion ──
    "A":  0.5,   # dunite, olivine-dominated mantle
    "R":  0.5,   # olivine-pyroxene mantle fragment
    "O":  0.5,   # olivine-orthopyroxene (rare, ureilite-class)

    # ── Basaltic crust — PGMs largely extracted into core during differentiation ──
    "V":  0.2,   # Vesta family / HED meteorite analog

    # ── Everything else: baseline 1.0× (chondritic / primitive — get via .get default) ──
    # C, Cb, Cg, Cgh, Ch, B, S, Sa, Sk, Sl, Sq, Sr, Sv, Q, K, L, D, T, P, F, G, Unknown
}


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


print(f"✅  PGM enrichment table ready — "
      f"{len(PGM_ENRICHMENT_BY_TYPE)} non-baseline spectral types "
      f"(M / Xe = 2.0×, V = 0.2×, A / R / O = 0.5×, others 1.0×)")


# ─────────────────────────────────────────────────────────────────────────────
# JPL SBDB FETCHER  (primary source)
# ─────────────────────────────────────────────────────────────────────────────
JPL_SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"

# Physical + orbital fields available in the SBDB Query API.
# Note: 'density' is NOT in the SBDB query table — it only appears in the
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
    "per",             # orbital period (yr)
    "n",               # mean motion (deg/day)
]

_JPL_RENAME = {
    "pdes":           "designation",
    # NB: `name` passes through verbatim — no entry needed since the source
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
    "per":            "orbital_period_yr",
    "n":              "mean_motion_deg_day",
    "neo":            "is_neo",
    "pha":            "is_pha",
    "spkid":          "spk_id",
}

_JPL_NUMERIC = [
    "diameter_km", "diameter_sigma_km", "albedo", "rotation_period_h",
    "semi_major_axis_au", "eccentricity", "perihelion_au",
    "aphelion_au", "inclination_deg", "longitude_asc_node_deg",
    "arg_perihelion_deg", "mean_anomaly_deg", "orbital_period_yr",
    "mean_motion_deg_day",
]


def fetch_jpl_sbdb(config: CatalogConfig) -> pd.DataFrame:
    """
    Fetch asteroid physical + orbital data from NASA JPL SBDB Query API.

    Strategy:
      • Attempt 1 — full field list (spec_B, spec_T, diameter, albedo, …)
      • Attempt 2 — minimal safe fields (orbital only + diameter + albedo)
        used as fallback if any field name in attempt 1 is rejected.
    Returns EMPTY DataFrame on any unrecoverable error.
    """
    print("\n📡  JPL Small-Body Database  (ssd-api.jpl.nasa.gov) …")

    # Minimal field set guaranteed to exist in every SBDB query response.
    # Used as fallback if the full list causes a 400.
    _SAFE_FIELDS = "pdes,name,spkid,neo,pha,diameter,diameter_sigma,albedo,rot_per,e,a,q,ad,i,om,w,ma,per,n"

    base_params = {
        "sb-kind":   "a",           # asteroids only
        "limit":     config.jpl_limit,
        "full-prec": "true",
        # NOTE: sb-cond removed — the '>' operator encoding caused HTTP 400.
        #       Filtering by diameter > 0 is handled in Python (validate_and_filter).
    }

    attempts = [
        ("full fields",  {**base_params, "fields": ",".join(_JPL_FIELDS)}),
        ("safe fields",  {**base_params, "fields": _SAFE_FIELDS}),
    ]

    for attempt_name, params in attempts:
        try:
            # Stream the response so we can render a byte-progress bar — the
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
                    print(f"     ⚠️  HTTP 400 on {attempt_name} — API says: {api_msg}")
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
                print(f"     ❌  JSON decode failed on {attempt_name}: {exc}")
                continue

            if "data" not in payload or not payload["data"]:
                print(f"     ⚠️  No data on {attempt_name} — trying next")
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
            print(f"     ✅  {len(df):,} records fetched from JPL SBDB ({attempt_name})")
            return df

        except requests.exceptions.Timeout:
            print(f"     ❌  Timeout on {attempt_name}")
        except requests.exceptions.ConnectionError:
            print("     ❌  Connection error — JPL SBDB skipped entirely")
            return pd.DataFrame()
        except requests.exceptions.HTTPError as exc:
            print(f"     ❌  HTTP {exc.response.status_code} on {attempt_name}")
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            print(f"     ❌  Parse error ({exc}) on {attempt_name}")
        except Exception as exc:
            print(f"     ❌  Unexpected error ({exc}) on {attempt_name}")

    print("     ❌  All JPL SBDB attempts failed — skipped")
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
# Other sources spell the same identifier differently — VizieR uses
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
    "2024 BX1"                    "2024 BX1"      (PROVISIONAL — KEEP WHOLE)
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

    # Case A: numbered asteroid with a name — extract the leading number.
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
    print("\n🔭  MP3C — Minor Planet Physical Properties Catalogue …")

    # ── Attempt 1: REST endpoints ────────────────────────────────────────────
    for endpoint_tpl in _MP3C_REST_ENDPOINTS:
        url = endpoint_tpl.format(limit=config.jpl_limit)
        try:
            r = requests.get(url, timeout=config.request_timeout)
        except requests.exceptions.ConnectionError as exc:
            print(f"     ⚠️  REST unreachable ({str(exc)[:80]})")
            break  # if DNS fails for the host, no point trying other paths
        except requests.exceptions.Timeout:
            print(f"     ⚠️  REST timed out on {endpoint_tpl[:60]}…")
            continue
        except Exception as exc:
            print(f"     ⚠️  REST {type(exc).__name__}: {exc}")
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
        adql = f"SELECT TOP {config.jpl_limit} * FROM {table}"
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
            print(f"     ⚠️  TAP unreachable for table '{table}' ({type(exc).__name__})")
            continue
        except Exception as exc:
            print(f"     ⚠️  TAP {type(exc).__name__}: {exc}")
            continue

        if r.status_code != 200 or not r.text.strip():
            continue

        try:
            df = _mp3c_jsonish_to_df(r.json())
        except Exception:
            continue
        if df is not None and not df.empty:
            return _normalise_mp3c_df(df, source_url=f"TAP:{table}")

    print("     ℹ️  MP3C not reachable on any endpoint — continuing without it")
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
    print(f"     ✅  {len(df):,} records fetched from MP3C  ({source_url[:80]})")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SsODNet ssoBFT FETCHER  (IMCCE — Solar-system Best-estimate Table)
# ─────────────────────────────────────────────────────────────────────────────
# SsODNet aggregates ~3,000 published catalogs into a single best-estimate
# table for ~1.2 M asteroids.  We pull the bulk Apache-Parquet file
# (~500 MB) ONCE per `cache_max_age_days` and read only the columns we need
# via pyarrow column projection so the in-memory footprint is small.
#
# Schema notes (parquet column names use dotted paths — 915 cols total):
#   Identity:  sso_id, sso_number, sso_name
#   Physical:  diameter.value, diameter.error.{min,max}        (km)
#              albedo.value                                    (geometric)
#              mass.value                                      (kg)
#              density.value                                   (kg/m³ → we convert to g/cm³)
#              absolute_magnitude.value                        (mag)
#   Taxonomy:  taxonomy.class, taxonomy.complex
#   Orbital:   orbital_elements.{semi_major_axis,eccentricity,
#                inclination,perihelion,aphelion,node_longitude,
#                perihelion_argument,mean_anomaly,orbital_period}.value
#   Rotation:  spins.<1..5>.period.value  (ranked best-of solutions, plural,
#                                          1-indexed; we coalesce ranks 1-3)
#
# Documentation: https://ssp.imcce.fr/webservices/ssodnet/api/ssobft/
# Bulk file:     https://ssp.imcce.fr/data/ssoBFT-latest_Asteroid.parquet

_SSODNET_PARQUET_URL = "https://ssp.imcce.fr/data/ssoBFT-latest_Asteroid.parquet"
_SSODNET_CACHE_FILE  = "ssoBFT-latest_Asteroid.parquet"

# Columns we WANT.  Asked of pyarrow as a projection; any not present in the
# file's actual schema are silently dropped (handled below).
_SSODNET_WANTED = [
    "sso_id", "sso_number", "sso_name",
    "diameter.value", "diameter.error.min", "diameter.error.max",
    "albedo.value",
    "mass.value",
    "density.value",
    "taxonomy.class", "taxonomy.complex",
    "orbital_elements.semi_major_axis.value",
    "orbital_elements.eccentricity.value",
    "orbital_elements.inclination.value",
    "orbital_elements.perihelion.value",
    "orbital_elements.aphelion.value",
    "orbital_elements.node_longitude.value",
    "orbital_elements.perihelion_argument.value",
    "orbital_elements.mean_anomaly.value",
    "orbital_elements.orbital_period.value",
    "absolute_magnitude.value",
    # Spin / rotation: ssoBFT exposes up to 5 ranked-best spin solutions as
    # `spins.<1..5>.period.value` (plural, 1-indexed).  Pull the top-3 ranks;
    # the fetcher coalesces them — first non-NaN wins → maximises coverage.
    "spins.1.period.value", "spins.2.period.value", "spins.3.period.value",
]

_SSODNET_RENAME = {
    # Identity:
    #   sso_number  → numeric IAU number (e.g. "1" for Ceres).  Used as our
    #                 merge key (designation).
    #   sso_name    → human-readable name ("Ceres").
    #   sso_id      → IMCCE's quaero-resolved canonical identifier; for
    #                 numbered asteroids this is the name string, for
    #                 unnumbered it's the provisional designation.  Kept as
    #                 `ssodnet_id` so a user can round-trip back to the
    #                 SsODNet REST API (ssp.imcce.fr/.../ssocard/<ssodnet_id>).
    "sso_number":                                      "designation",
    "sso_name":                                        "name",
    "sso_id":                                          "ssodnet_id",
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
    "orbital_elements.perihelion.value":               "perihelion_au",
    "orbital_elements.aphelion.value":                 "aphelion_au",
    "orbital_elements.node_longitude.value":           "longitude_asc_node_deg",
    "orbital_elements.perihelion_argument.value":      "arg_perihelion_deg",
    "orbital_elements.mean_anomaly.value":             "mean_anomaly_deg",
    "orbital_elements.orbital_period.value":           "orbital_period_yr",
    "absolute_magnitude.value":                        "absolute_magnitude_h",
    # spins.<n>.period.value handled separately below — they're coalesced
    # into a single `rotation_period_h` column.
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
            # indexer or AV — retry the atomic rename a few times before giving up.
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
        print("     ❌  SsODNet download timed out")
    except requests.exceptions.ConnectionError as exc:
        print(f"     ❌  SsODNet unreachable ({str(exc)[:80]})")
    except requests.exceptions.HTTPError as exc:
        print(f"     ❌  SsODNet HTTP {exc.response.status_code}")
    except Exception as exc:
        print(f"     ❌  SsODNet download error: {type(exc).__name__}: {exc}")
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
    (system tmp by default — see _resolve_cache_dir) and refreshed only when
    older than config.cache_max_age_days.

    Returns EMPTY DataFrame on any unrecoverable error so the rest of the
    pipeline survives unaffected.
    """
    print("\n🛰️   SsODNet ssoBFT  (ssp.imcce.fr) …")

    # pyarrow is required for column-projection parquet reads.  If somehow it
    # didn't install, fall back to pandas' built-in parquet engine — which is
    # usually pyarrow anyway but may be fastparquet on bare systems.
    try:
        import pyarrow.parquet as pq          # noqa: F401  (engine probe)
        engine = "pyarrow"
    except ImportError:
        print("     ⚠️  pyarrow not available — falling back to pandas default engine")
        engine = "auto"

    cache_path = _ssodnet_cache_path(config)
    if _ssodnet_cache_is_fresh(cache_path, config.cache_max_age_days):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache_path)) / 3600
        print(f"     💾  Using cached parquet ({age_h:.1f} h old): {cache_path}")
    else:
        print(f"     ⬇️   Downloading bulk parquet from {_SSODNET_PARQUET_URL}")
        if not _download_ssodnet_parquet(cache_path, config):
            return pd.DataFrame()

    # Read only the columns that actually exist in the schema (the schema does
    # drift between SsODNet releases).
    try:
        if engine == "pyarrow":
            import pyarrow.parquet as pq
            pf = pq.ParquetFile(cache_path)
            schema_names = set(pf.schema.names)
            cols = [c for c in _SSODNET_WANTED if c in schema_names]
            missing = [c for c in _SSODNET_WANTED if c not in schema_names]
            if missing:
                # Common — SsODNet uses different flattened names per release.
                # Only surface this when essentially nothing matched.
                if len(cols) < 5:
                    print(f"     ⚠️  Schema only matched {len(cols)} of {len(_SSODNET_WANTED)} expected columns")
            df = pf.read(columns=cols).to_pandas()
        else:
            df = pd.read_parquet(cache_path)
            df = df[[c for c in _SSODNET_WANTED if c in df.columns]]
    except Exception as exc:
        print(f"     ❌  Parquet read failed: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    if df.empty:
        print("     ⚠️  Parquet returned 0 rows")
        return pd.DataFrame()

    # Cap to config.jpl_limit so SsODNet doesn't dominate runtime on small runs.
    # NB: full table is ~1.2 M rows; trimming here keeps merge / dedup fast.
    # IMPORTANT: sort by sso_number ASC first so a small-N run gets the LOWEST
    # IAU numbers (Ceres=1, Pallas=2, Juno=3, Vesta=4, …) — the most famous
    # bodies — rather than whatever arbitrary order the parquet stores rows in.
    # Unnumbered bodies (sso_number = NaN) are sorted to the end via na_position.
    if config.jpl_limit and len(df) > config.jpl_limit:
        if "sso_number" in df.columns:
            df = df.sort_values("sso_number", ascending=True, na_position="last")
        df = df.head(config.jpl_limit).copy()
        print(f"     ✂️   Truncated to first {config.jpl_limit:,} rows by sso_number ASC")

    # Coalesce the ranked spin solutions (spins.1 > spins.2 > spins.3) into a
    # single rotation_period_h column.  Best-rank wins per row; lower-ranked
    # values fill gaps where the best rank is NaN — maximises coverage.
    spin_cols = [c for c in ("spins.1.period.value",
                             "spins.2.period.value",
                             "spins.3.period.value") if c in df.columns]
    if spin_cols:
        rot = df[spin_cols[0]].astype("float64")
        for c in spin_cols[1:]:
            rot = rot.fillna(df[c].astype("float64"))
        df["rotation_period_h"] = rot
        df = df.drop(columns=spin_cols)

    # Derive diameter_sigma_km from the asymmetric (min, max) error pair before
    # we drop the dotted columns.  Average is a reasonable scalar uncertainty.
    if {"diameter.error.min", "diameter.error.max"}.issubset(df.columns):
        sig = (df["diameter.error.min"].astype("float64").abs()
               + df["diameter.error.max"].astype("float64").abs()) / 2.0
        df["diameter_sigma_km"] = sig
        df = df.drop(columns=["diameter.error.min", "diameter.error.max"])

    df = df.rename(columns={k: v for k, v in _SSODNET_RENAME.items() if k in df.columns})

    # Designation: prefer sso_number (numbered → "1"), fall back to sso_name
    # (provisional designations / unnumbered).
    # IMPORTANT: sso_number is int64 in the parquet but pandas casts to float64
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

    # SsODNet density is in kg/m³ — convert to g/cm³ to match the pipeline schema.
    if "density_gcm3" in df.columns:
        df["density_gcm3"] = pd.to_numeric(df["density_gcm3"], errors="coerce") / 1000.0

    # Coerce all numerics
    for col in _SSODNET_NUMERIC:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # If aphelion / perihelion are missing but a & e are present, derive them —
    # cheap and helps with validator coverage.
    if {"semi_major_axis_au", "eccentricity"}.issubset(df.columns):
        if "perihelion_au" not in df.columns or df["perihelion_au"].isna().all():
            df["perihelion_au"] = df["semi_major_axis_au"] * (1 - df["eccentricity"])
        if "aphelion_au" not in df.columns or df["aphelion_au"].isna().all():
            df["aphelion_au"] = df["semi_major_axis_au"] * (1 + df["eccentricity"])

    df["source_ssodnet"] = True
    print(f"     ✅  {len(df):,} records ingested from SsODNet ssoBFT "
          f"({len(df.columns)} columns)")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# NEOWISE V2.0 FETCHER  (IRSA TAP — neowisesbpropv2)
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
_NEOWISE_TAP_TABLE  = "neowisesbpropv2"

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


def fetch_neowise(config: CatalogConfig) -> pd.DataFrame:
    """
    Fetch NEOWISE V2.0 diameters & albedos via IPAC IRSA's TAP service.

    NEOWISE is a PHYSICAL-only catalog — no orbital elements — so it can't
    stand alone.  Once merged it upgrades diameter / albedo for the ~150k
    rows where it overlaps the JPL backbone.

    Returns EMPTY DataFrame on any unrecoverable error.
    """
    print("\n🌡️   NEOWISE V2.0 diameters & albedos  (IRSA TAP) …")

    # ADQL.  Cap to config.jpl_limit so a 50k-cap run doesn't drag in the full
    # 150k-row catalog (and overflow the merge dedup budget for big runs).
    # WHERE clause filters comets server-side and skips rows without ANY
    # identifier — saves bandwidth and avoids a useless dedup pass later.
    # ORDER BY asteroid_number so small-N runs include the low-numbered
    # (most famous) bodies — Ceres, Vesta, etc.
    adql = (
        f"SELECT TOP {int(config.jpl_limit)} {_NEOWISE_SELECT} "
        f"FROM {_NEOWISE_TAP_TABLE} "
        f"WHERE type != 'comet' "
        f"  AND (asteroid_number IS NOT NULL OR prov_desig IS NOT NULL) "
        f"ORDER BY asteroid_number ASC"
    )
    params = {
        "REQUEST": "doQuery",
        "LANG":    "ADQL",
        "FORMAT":  "csv",
        "QUERY":   adql,
    }

    try:
        with requests.get(
            _NEOWISE_TAP_URL,
            params=params,
            timeout=config.request_timeout,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                snippet = resp.text[:300].replace("\n", " ")
                print(f"     ❌  HTTP {resp.status_code} — {snippet}")
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
        print("     ❌  NEOWISE TAP timed out")
        return pd.DataFrame()
    except requests.exceptions.ConnectionError as exc:
        print(f"     ❌  NEOWISE TAP unreachable ({str(exc)[:80]})")
        return pd.DataFrame()
    except Exception as exc:
        print(f"     ❌  NEOWISE TAP error: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    # IRSA may return one of several non-CSV bodies on failure:
    #   • VOTable error envelope (XML) on a bad ADQL
    #   • HTML 200-with-error-page on a backend hiccup
    #   • empty body
    # Detect each of these explicitly so we don't try to coerce HTML/XML into
    # a DataFrame and end up with garbage rows.
    head = body[:400].lstrip()
    if not head:
        print("     ❌  TAP returned an empty body")
        return pd.DataFrame()
    if head.startswith(b"<?xml") or head.startswith(b"<VOTABLE"):
        snippet = body[:400].decode("utf-8", errors="replace").replace("\n", " ")
        print(f"     ❌  TAP returned a VOTable error envelope: {snippet[:200]}")
        return pd.DataFrame()
    if head[:1] == b"<":   # any other tag-leading body (HTML, etc.)
        snippet = body[:400].decode("utf-8", errors="replace").replace("\n", " ")
        print(f"     ❌  TAP returned a non-CSV body: {snippet[:200]}")
        return pd.DataFrame()
    if not head.lower().startswith(b"asteroid_number"):
        # Expected CSV header from this query begins with `asteroid_number`.
        # Anything else means the schema or query has drifted — fail loud.
        snippet = body[:400].decode("utf-8", errors="replace").replace("\n", " ")
        print(f"     ❌  TAP body doesn't look like expected CSV: {snippet[:200]}")
        return pd.DataFrame()

    from io import BytesIO
    try:
        df = pd.read_csv(BytesIO(body))
    except Exception as exc:
        print(f"     ❌  CSV parse failed: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    if df.empty:
        print("     ⚠️  NEOWISE TAP returned 0 rows")
        return pd.DataFrame()

    # Designation: numbered → `asteroid_number`, unnumbered → `prov_desig`.
    if "asteroid_number" in df.columns and "prov_desig" in df.columns:
        num   = df["asteroid_number"].astype("string")
        prov  = df["prov_desig"].astype("string")
        chosen = num.where(num.notna() & (num != "") & (num != "<NA>"), prov)
        df["designation"] = chosen
    elif "asteroid_number" in df.columns:
        df["designation"] = df["asteroid_number"].astype("string")
    elif "prov_desig" in df.columns:
        df["designation"] = df["prov_desig"].astype("string")

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
    print(f"     ✅  {len(df):,} records fetched from NEOWISE V2.0")
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
    was collapsed.  Idempotent — safe to call multiple times in the pipeline.

    Used in three places:
      1. inside merge_sources, per source, BEFORE the join — defends against
         source-internal duplicates (e.g. a future catalog returning the same
         asteroid under both numeric and named designations)
      2. inside merge_sources, AFTER the join — catches duplicates introduced
         by designation variants between sources
      3. inside build_asteroid_catalog, AFTER enrichment — final safety net before save
    """
    if df.empty or key not in df.columns:
        return df

    n_before = len(df)

    work = df.copy()
    work["_dedup_key"]    = _normalise_designation_key(work[key])
    work["_completeness"] = work.notna().sum(axis=1)

    # Drop rows whose normalised key is null — they can't be safely grouped.
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
        print(f"     🗑   {label}: " + "; ".join(msg))
    else:
        print(f"     ✔   {label}: no duplicates detected")

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
    print("\n🔀  Merging sources …")

    available = {k: v for k, v in sources.items() if v is not None and not v.empty}

    if not available:
        print("     ❌  No data from any source — aborting merge")
        return pd.DataFrame()

    # Normalise designation for joining, then dedupe each source on its own
    # (defends against duplicates introduced upstream in any fetcher).
    # Use the shared canonical extractor — it's idempotent so re-running on
    # an already-canonical fetcher output is a no-op, and crucially it returns
    # proper pd.NA for missing values (a naïve .astype(str).str.upper() would
    # turn pd.NA into the literal string "<NA>" and create a ghost dedup key).
    for name, df in available.items():
        if "designation" in df.columns:
            df["designation"] = _extract_canonical_designation(df["designation"])
        available[name] = deduplicate_catalog(df, key="designation", label=name)

    # First non-empty source becomes the backbone — caller controls precedence
    # via the dict insertion order.
    backbone_name, backbone_df = next(iter(available.items()))
    merged = backbone_df.copy()
    available.pop(backbone_name)
    print(f"     🦴  Backbone: {backbone_name}  ({len(merged):,} rows)")

    # Outer-join each remaining source so designations unique to that source
    # are retained.  Backbone values win; supplement values fill NaN gaps.
    for src_name, supp in available.items():
        if "designation" not in supp.columns:
            print(f"     ⚠️  {src_name} has no 'designation' column — skipped in merge")
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

        print(f"     ✔   Merged {src_name}: {len(supp):,} supplement records "
              f"(+{new_rows:,} new entries)")

    # Final post-merge dedup — keeps the most-complete row in each group.
    merged = deduplicate_catalog(merged, key="designation", label="post-merge")

    print(f"     ✅  Combined catalog: {len(merged):,} rows × {len(merged.columns)} columns")
    return merged


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
    print("\n🔍  Validating entries …")

    if df.empty:
        print("     ⚠️  Nothing to validate")
        return df.copy(), pd.DataFrame()

    total      = len(df)
    valid_mask = pd.Series(True, index=df.index)
    log        = []

    # ── 1. Designation required ───────────────────────────────────────────────
    if "designation" not in df.columns:
        print("     ❌  'designation' column missing — cannot build catalog")
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
        print("     ⚠️  No orbital elements — coordinate mapping will be unavailable")

    # ── 5. Strict spectral type (optional) ───────────────────────────────────
    # Validate runs BEFORE enrich_composition's Tholen fallback, so we have to
    # consult `spectral_type` AND `spectral_type_tholen` here — otherwise a row
    # carrying only a Tholen letter (e.g. JPL `spec_T="G"`) would be wrongly
    # rejected, contradicting the CATALOG_CONFIG comment that says strict mode requires
    # "Bus / Tholen".  A row passes if EITHER column has a non-blank value.
    if config.require_spectral_type:
        def _blank(s: pd.Series) -> pd.Series:
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

    print(f"     ✅  Accepted : {n_kept:,}")
    print(f"     ❌  Rejected : {n_dropped:,}  ({n_dropped/total*100:.1f}%)")
    if not rejection_df.empty:
        for _, row in rejection_df.iterrows():
            print(f"         • {row['reason']:55s} → {row['rejected_count']:,} dropped")

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
          A `spectral_type_source` column records provenance:
            • "source"  → arrived from a fetcher (JPL spec_B, SsODNet
                          taxonomy.class, MP3C taxonomy, …)
            • "tholen"  → filled from spectral_type_tholen (step 2a)
            • "albedo"  → inferred from geometric albedo (step 2b)
            • "unknown" → still missing after every fallback
      3. Look up TAXONOMY_COMPOSITION fields for each type → `comp_*` cols.
      4. Fill density_gcm3 from taxonomy estimate where no measurement exists;
         `density_measured` flag tracks provenance.
      5. Compute estimated_mass_kg, preserving any value already supplied by a
         fetcher (SsODNet) and filling gaps with (4/3)π r³ ρ from
         diameter × density; `mass_measured` flag tracks provenance.
    """
    print("\n🧪  Enriching composition data …")
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
        if pd.isna(t) or not isinstance(t, str):
            return pd.NA
        t = t.strip()
        return t[0].upper() + t[1:].lower() if t else pd.NA

    df["spectral_type"] = df["spectral_type"].apply(normalise_type)

    # `spectral_type_source` tracks WHERE the final classification came from so
    # consumers can filter on confidence:
    #   "source"  — supplied by a fetcher (Bus-DeMeo from JPL spec_B, or a
    #               curated mix from SsODNet / MP3C)
    #   "tholen"  — filled from spectral_type_tholen because Bus wasn't there
    #   "albedo"  — crude inference from geometric albedo
    #   "unknown" — still missing after every fallback
    df["spectral_type_source"] = np.where(df["spectral_type"].notna(), "source", "unknown")

    # ── 2a. Fall back to Tholen classification where Bus-DeMeo is missing ────
    # JPL (`spec_T`) supplies Tholen; we hold it in
    # `spectral_type_tholen`.  Most Tholen letters (S, C, X, V, …) overlap with
    # Bus-DeMeo directly; the Tholen-only ones (M, E, P, F, G) are now in
    # TAXONOMY_COMPOSITION too, so the lookup at step 3 handles them uniformly.
    if "spectral_type_tholen" in df.columns:
        tholen = df["spectral_type_tholen"].apply(normalise_type)
        fill_mask = df["spectral_type"].isna() & tholen.notna()
        df.loc[fill_mask, "spectral_type"]        = tholen[fill_mask]
        df.loc[fill_mask, "spectral_type_source"] = "tholen"
        n_thol = int(fill_mask.sum())
        if n_thol:
            print(f"     🔡  Spectral type filled from Tholen for {n_thol:,} entries")

    # ── 2b. Infer from albedo where type is still missing ────────────────────
    if "albedo" in df.columns:
        alb = pd.to_numeric(df["albedo"], errors="coerce")
        infer_mask = df["spectral_type"].isna() & alb.notna()

        def _infer_from_albedo(a: float) -> str:
            """Coarse spectral-type inference from geometric albedo."""
            if a < 0.10: return "C"     # dark      → carbonaceous
            if a < 0.35: return "S"     # moderate  → stony
            return "V"                  # bright    → basaltic or E-type

        df.loc[infer_mask, "spectral_type"]        = alb[infer_mask].apply(_infer_from_albedo)
        df.loc[infer_mask, "spectral_type_source"] = "albedo"
        n_inf = int(infer_mask.sum())
        if n_inf:
            print(f"     🔎  Spectral type inferred from albedo for {n_inf:,} entries")

    # ── 3. Look up composition fields ────────────────────────────────────────
    # `minerals` and `notes` are included because for a mining-profitability
    # pipeline the dominant minerals + the literature note are first-class
    # outputs — a user looking at one row wants to know what's actually there.
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

    for field in comp_fields:
        df[f"comp_{field}"] = df["spectral_type"].apply(lambda t: _lookup(t, field))

    # ── 3b. PGM enrichment factor (v1.0.4) ────────────────────────────────────
    # Per-spectral-type multiplier applied to platinum-group-metal yields
    # in Module 2's "nickel-iron" mineral.  Differentiated bodies (M-type
    # cores) have ~2× chondritic PGM in their metal phase; basaltic-crust
    # fragments (V-type) ~0.2×.  See PGM_ENRICHMENT_BY_TYPE for the table.
    df["comp_pgm_enrichment"] = df["spectral_type"].apply(pgm_enrichment_for_type)
    n_enriched  = int((df["comp_pgm_enrichment"] > 1.0).sum())
    n_depleted  = int((df["comp_pgm_enrichment"] < 1.0).sum())
    if n_enriched or n_depleted:
        print(f"     💎  PGM enrichment: {n_enriched:,} enriched (>1×)  |  "
              f"{n_depleted:,} depleted (<1×)  |  rest baseline (1×)")

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
    print(f"     📊  Density: {n_meas:,} measured  |  {n_est:,} estimated from taxonomy")

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
    print(f"     ⚖️   Mass:    {n_mass_meas:,} measured  |  {n_mass_der:,} derived (diameter × density)")

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
    print("  🚀  ASTEROID CATALOG PIPELINE  —  MODULE 1: CATALOGING")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  v{config.pipeline_version}")
    print("=" * 65)

    # ── Step 1 — Fetch ────────────────────────────────────────────────────────
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

    # ── Step 2 — Merge ────────────────────────────────────────────────────────
    merged = merge_sources(sources)
    if merged.empty:
        print("\n❌  Pipeline aborted — merge produced no data")
        return pd.DataFrame()

    # ── Step 3 — Validate & filter ────────────────────────────────────────────
    catalog, rejections = validate_and_filter(merged, config)
    if catalog.empty:
        print("\n❌  Pipeline aborted — no entries passed validation")
        return pd.DataFrame()

    # ── Step 4 — Composition enrichment ──────────────────────────────────────
    catalog = enrich_composition(catalog)

    # ── Step 4b — Final dedup safety net ─────────────────────────────────────
    # Belt-and-braces: enrichment shouldn't introduce duplicates, but checking
    # here means a CSV written to disk is guaranteed to have unique designations.
    print("\n🧹  Final duplicate sweep …")
    catalog = deduplicate_catalog(catalog, key="designation", label="final")

    # ── Step 5 — Metadata + sort ──────────────────────────────────────────────
    catalog["catalog_date"]      = t0.strftime("%Y-%m-%d")
    catalog["pipeline_version"]  = config.pipeline_version

    if "semi_major_axis_au" in catalog.columns:
        catalog = catalog.sort_values("semi_major_axis_au").reset_index(drop=True)

    # ── Step 6 — Save ─────────────────────────────────────────────────────────
    catalog_path  = os.path.join(config.output_dir, config.catalog_filename)
    rejected_path = os.path.join(config.output_dir, config.rejected_filename)

    catalog.to_csv(catalog_path, index=False)
    print(f"\n     💾  Catalog saved  → {catalog_path}")

    if not rejections.empty:
        rejections.to_csv(rejected_path, index=False)
        print(f"     💾  Rejections log → {rejected_path}")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - t0).total_seconds()
    print("\n" + "=" * 65)
    print("  ✅  CATALOGING COMPLETE")
    print(f"      Entries    : {len(catalog):,}")
    print(f"      Columns    : {len(catalog.columns)}")
    print(f"      Elapsed    : {elapsed:.1f}s")
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

    regex=False — designations and names carry regex metacharacters, which
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


print("\n✅  Helper utilities available:")
print("    lookup_asteroid_catalog(catalog, 'Ceres')")
print("    filter_by_region(catalog, 2.0, 3.3)   # main-belt slice")
print("    filter_by_spectral_group(catalog, 'X-complex')  # metallic")




# ═════════════════════════════════════════════════════════════════════════
# MODULE 2 — MINERAL VALUE CATALOG
# ═════════════════════════════════════════════════════════════════════════




# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import json
import math
import os
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
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
# ║   ★  USER SETTINGS — EDIT THESE TO TUNE THE PIPELINE  ★                  ║
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
    # fetcher to silently skip — the demo endpoint is heavily rate-limited.
    metals_api_key: str = "DEMO"
    metals_api_url: str = "https://api.metals.dev/v1/latest"

    # ─── DELIVERY DESTINATION  (drives EVERY price — read this) ──────────────
    # Where the mined material is actually SOLD.  This is the single most
    # consequential field in the pipeline: it selects the market, and the
    # market decides both what a kilogram is worth and which asteroids win.
    #
    #   "earth_surface" — material re-enters and is sold on Earth at
    #                     terrestrial commodity prices.  Water is worth
    #                     ~nothing; platinum is worth $57,000/kg.  Favours
    #                     metal-rich M / X types.
    #   "leo"           — delivered to and sold in low Earth orbit.  Every
    #                     commodity with in-space utility is worth the launch
    #                     cost it avoids ($4,253/kg); precious metals are
    #                     worth nothing, because no orbital market for them
    #                     exists.  Favours water- and metal-rich bulk.
    #   "cislunar"      — sold at a lunar-vicinity (NRHO) depot, worth the
    #                     larger launch cost avoided ($10,810/kg, derived).
    #                     Also the CHEAPEST of the orbital options to reach
    #                     from an asteroid — see Module 4's return-Δv model.
    #   "lunar_surface" — sold at a Moon base.  $21,210/kg: nearest
    #                     destination, but airless, so all 5,920 m/s from LEO
    #                     is propulsive.
    #   "mars_surface"  — sold at a Mars base.  $45,105/kg: far in Δv, but the
    #                     atmosphere brakes most of the arrival for free.
    #
    # ⚠️  The two surface figures are MARGINAL-TRANSPORT LOWER BOUNDS.  They
    # price the propellant and stages needed to move a kilogram, on a reusable
    # Falcon 9 LEO price, with no first-of-kind development, no programme
    # overhead and no launch-cadence limit.  Real delivered cost today is far
    # higher — CLPS lunar landers run on the order of $1M/kg for ~100 kg
    # payloads.  Treat these as "what it could cost at industrial scale", not
    # "what it costs now".
    #
    # v1.3.0: this used to reprice water only.  It now reprices everything,
    # which is the consistent form of the same correction — see
    # DELIVERY_DESTINATIONS and IN_SPACE_UTILITY below for the numbers, the
    # derivation, and which parts are judgement rather than measurement.
    #
    # ⚠️  Module 4's CALC_CONFIG carries a delivery_destination of its own,
    # and it must MATCH this one — it selects the mission architecture that
    # actually delivers the cargo here.  Module 4 checks and warns.
    delivery_destination: str = "earth_surface"

    # ─── NETWORK ─────────────────────────────────────────────────────────────
    request_timeout: int = 60   # seconds per HTTP request

    # ─── OUTPUT ──────────────────────────────────────────────────────────────
    output_dir:       str = _DEFAULT_OUTPUT_DIR
    catalog_filename: str = "mineral_value_catalog.csv"

    # ─── PRICE UNITS ─────────────────────────────────────────────────────────
    # Every price in this pipeline — live OR reference — is normalised to
    # USD per kilogram before it lands in the output frame.  This constant
    # is the single source of truth for that unit; every column carries the
    # `_usd_per_kg` suffix so the unit is unmistakable downstream.
    PRICE_UNIT: str = "USD/kg"

    # ─── PIPELINE VERSION ────────────────────────────────────────────────────
    # 1.1.0 — initial release
    # 1.1.1 — cross-file audit cleanup (May 2026):
    #         • removed unused imports (`field` from dataclasses, `Dict` from typing)
    #         • refreshed _REF_PRICE_DATE stamp 2026-01-15 → 2026-05-29
    # 1.1.4 — lookup_mineral() passes regex=False.  pandas' str.contains
    #         defaults to regex=True, so a query containing metacharacters —
    #         "nickel-iron (alloy)" — was read as a pattern rather than the
    #         literal substring the docstring promises, and an unbalanced
    #         bracket raised re.PatternError.  No other behaviour change.
    # 1.1.3 — added rare-mineral phase entries (Option 3 from low-value audit):
    #         • sperrylite  PtAs2     56.6% Pt  → ~$25k/kg implied
    #         • laurite     RuS2      61.2% Ru  → ~$10k/kg implied
    #         • awaruite    Ni3Fe     75.9% Ni + 5× PGM-enriched → ~$25k/kg
    #         • native-pgm  (Pt,Pd,Ir,Os,Ru,Rh) → ~$55k/kg
    #         These are NOT referenced by default in Module 1's TAXONOMY
    #         (which uses bulk "nickel-iron" as the metal carrier).  They are
    #         available targets for per-asteroid composition overrides or
    #         future spectral-identification work — the integrity check in
    #         Module 4 will report them as informational "extra" rows.
    # 1.1.2 — calibration pass — fix low-value bugs found in Module 4 output:
    #         • Iron price $0.12 → $0.50/kg.  Old number was the iron-ore
    #           benchmark; mining produces refined Fe metal from nickel-iron
    #           alloy, so the correct sale price is steel scrap ($0.25-0.50/kg).
    #         • Gold $85k → $150k/kg (~$4,700/oz, May 2026 vs Jan-stamped value).
    #         • Platinum $31.5k → $45k/kg (~$1,400/oz, Heraeus 2026 forecast mid).
    #         • Palladium $32k → $48k/kg (~$1,495/oz, LBMA May 2026).
    #         • Rhodium $150k → $320k/kg (~$9,950/oz, LBMA May 2026).
    #         • Water $2,500 → $4,250/kg.  Was based on legacy Falcon 9 launch
    #           cost; now matches Module 3 v1.2.4 reusable Falcon 9 $4,253/kg-to-LEO.
    #         • nickel-iron yields: added ruthenium (3 ppm) + osmium (2 ppm) —
    #           previously missing despite being in the element catalog.
    #           Iridium 2 → 4 ppm; rhodium 2 → 1.5 ppm (rebalanced for ~37 ppm
    #           total PGM matching siderite literature).
    #         Numerical impact (hand-verified):
    #           nickel-iron implied value  $3.26 → $4.60/kg  (+41%)
    #           M-type bulk value          $2.61 → $3.69/kg  (+41%)
    #           C-type bulk value          $375  → $638/kg   (+70%, water-driven)
    #           B-type bulk value          $500  → $850/kg   (+70%, water-driven)
    # 1.1.5 — renumbering, no behaviour change.  This project was briefly
    #         developed in two places at once and both shipped different code
    #         as 1.1.4, so that stamp is ambiguous.  The reconciled module is
    #         1.1.5 because it matches neither parent.  Treat any CSV stamped
    #         1.1.4 as undated and re-run rather than trusting the number.
    # 1.2.0 — realism audit: water is now priced by DELIVERY DESTINATION.
    #         Water was hardcoded at $4,250/kg — explicitly "the cost-to-LEO
    #         of launching an equivalent water mass", i.e. the value of water
    #         sitting in orbit — while Module 4's mission model flies the
    #         cargo back down and lands it in a re-entry capsule.  Water on
    #         Earth's surface is worth bulk-industrial rates.
    #         The error was not marginal.  Measured across a real catalog,
    #         water was 99.9-100.0% of the bulk value of EVERY water-bearing
    #         type, so the entire profitability ranking was a proxy for
    #         ice_fraction:
    #             type   bulk $/kg   from water   share
    #             D       1,062.63     1,062.50   100.0%
    #             B         850.13       850.00   100.0%
    #             C         637.63       637.50   100.0%
    #             M           5.90         0.00     0.0%
    #         New WATER_VALUE_BY_DESTINATION table + delivery_destination
    #         config field (earth_surface / leo / cislunar).  Default is
    #         earth_surface, which is what the Module 4 architecture actually
    #         delivers — so C-type bulk value drops 637.63 → 0.13 $/kg and
    #         the ranking inverts to metal-rich types.  Set 'leo' to recover
    #         the old numbers, but only alongside a mission model that
    #         actually stops at LEO.
    #         New output columns: value_basis, delivery_destination.
    # 1.3.0 — IN-SPACE DELIVERY: destination pricing generalised from water to
    #         EVERY commodity.  Paired with Module 3 v1.4.0 / Module 4 v1.5.0.
    #         v1.2.0 repriced water by destination and left every other
    #         commodity at its terrestrial spot price, which is the same
    #         inconsistency v1.2.0 existed to fix, just moved: iron delivered
    #         to LEO was still valued at scrap-steel rates while the water
    #         beside it in the same capsule was valued at launch cost avoided.
    #         • WATER_VALUE_BY_DESTINATION → DELIVERY_DESTINATIONS, and the
    #           in-space prices are now DERIVED rather than tabulated.  The
    #           old cislunar figure was "~3x the LEO figure" by assertion;
    #           it is now $4,253/kg-to-LEO carried a further 3,600 m/s
    #           (Module 3's TLI + NRHO insertion) by an Isp 465 s stage of
    #           dry-mass fraction 0.10, via the rocket equation in
    #           delivered_cost_usd_per_kg().  That lands at $10,809/kg —
    #           15% below the old hand-waved $12,750, and now traceable.
    #             earth_surface  $0/kg avoided (terrestrial prices stand)
    #             leo            $4,253/kg
    #             cislunar      $10,809/kg
    #         • A kilogram at a depot is worth the BETTER OF TWO FATES, and
    #           the choice is made per commodity:
    #             USED IN SPACE   terrestrial price PLUS in_space_utility x
    #                             launch cost avoided.  Note the PLUS — the
    #                             launch bill is what delivering it saves, on
    #                             top of the material itself.
    #             SHIPPED DOWN    terrestrial price MINUS the downleg
    #                             (downleg_cost_usd_per_kg): capsule + TPS +
    #                             recovery, derived from the same Module 3
    #                             rates Module 4 charges for an Earth return,
    #                             plus the depot-departure burn.  ~$25,400/kg
    #                             from LEO, ~$27,300/kg from NRHO.  Coming
    #                             down is far cheaper than going up.
    #           This is what puts an honest number on platinum at a depot:
    #           nobody in orbit wants it, but it is still platinum, so it is
    #           priced by shipping it home rather than written off.
    #         • New IN_SPACE_UTILITY table: how good a substitute each
    #           commodity is for the launched article.  Water 1.00, structural
    #           metals 0.70, silicates 0.25, carbon 0.40, organics 0.20, and
    #           0.00 for the precious metals — which routes them down the
    #           ship-to-Earth branch rather than zeroing them.
    #           THESE ARE JUDGEMENTS, not measurements; they are the softest
    #           assumption in the in-space case and live in one table for that
    #           reason.
    #         • New apply_delivery_destination() step runs after merge_mineral_sources
    #           so it overrides LIVE quotes as well as reference ones.
    #         Numerical impact at LEO / cislunar (earth_surface unchanged):
    #           nickel-iron  $4.73/kg  -> $2,978  / $7,567   (used in space)
    #           water        $0.001    -> $4,253  / $10,810  (used in space)
    #           platinum     $56,695   -> $31,285 / $29,378  (shipped down)
    #           gold        $138,882   -> $113,472/ $111,565 (shipped down)
    #         New output columns: terrestrial_price_usd_per_kg,
    #         in_space_utility, downleg_cost_usd_per_kg, value_route.
    # 1.4.0 — SURFACE DESTINATIONS: lunar_surface and mars_surface.  Paired
    #         with Module 3 v1.5.0 and Module 4 v1.6.0.  Prices for the three
    #         existing destinations are UNCHANGED.
    #         • delivered_cost_usd_per_kg now walks a CHAIN OF LEGS
    #           (_DELIVERY_LEGS) backwards from the payload instead of taking
    #           one lumped Δv.  Staging is worth roughly 2x on a lunar
    #           landing — a single stage flying the whole 5,920 m/s needs
    #           10.96 kg in LEO per kg landed against 4.99 kg for the
    #           TLI/LOI-tug + lander pair that would actually be flown — so
    #           lumping it would have overstated the Moon by 2x.
    #         • New "edl" leg type for atmospheric arrival, carrying a
    #           surviving-mass fraction rather than a Δv.  Mars uses 0.30,
    #           measured from MSL (3,257 kg entry -> 899 kg rover, 27.6%) and
    #           Perseverance (3,440 -> 1,025, 29.8%).
    #         • New _LANDER_DRY_MASS_FRAC 0.20 — Apollo LM descent stage flew
    #           2,134 kg dry on 8,200 kg propellant.  A lander is structurally
    #           much heavier than a cryo tug for the same propellant load.
    #         Delivered cost, and the mass that has to reach LEO for it:
    #             leo             1.00 kg/kg      $4,253/kg
    #             cislunar        2.54 kg/kg     $10,810/kg
    #             lunar_surface   4.99 kg/kg     $21,210/kg
    #             mars_surface   10.61 kg/kg     $45,105/kg
    #         Downlegs (shipping back to the terrestrial market) rise the same
    #         way: $25,410 from LEO, $27,317 from NRHO, $44,939 from the Moon,
    #         $96,394 from Mars.  The last exceeds the terrestrial price of
    #         platinum, so platinum delivered to a Mars base is worth exactly
    #         nothing — which is the correct answer, not a bug.
    #         ⚠️  Both surface figures are marginal-transport LOWER BOUNDS —
    #         no NRE, no programme overhead, no cadence limit.  CLPS lunar
    #         landers really cost ~$1M/kg today at ~100 kg scale.
    pipeline_version: str = "1.4.0"

    # ─── DISPLAY ─────────────────────────────────────────────────────────────
    preview_rows: int = 20


MINERAL_CONFIG = MineralValueConfig()
os.makedirs(MINERAL_CONFIG.output_dir, exist_ok=True)

print(f"✅  Configuration loaded — output dir: {MINERAL_CONFIG.output_dir}")
print(f"    Active sources : "
      f"{', '.join(s for s, on in (('yfinance', MINERAL_CONFIG.use_yfinance), ('metals.dev', MINERAL_CONFIG.use_metals_api and MINERAL_CONFIG.metals_api_key != 'DEMO'), ('reference', MINERAL_CONFIG.use_reference_table)) if on)}")
print(f"    Price unit     : {MINERAL_CONFIG.PRICE_UNIT}  (every numeric price column ends with _usd_per_kg)")
print(f"    Delivery dest  : {MINERAL_CONFIG.delivery_destination}  "
      f"(sets EVERY price — see DELIVERY_DESTINATIONS + IN_SPACE_UTILITY)")


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
    return float(usd_per_oz) * TROY_OZ_PER_KG


def _per_lb_to_per_kg(usd_per_lb: float) -> float:
    return float(usd_per_lb) * LB_PER_KG


def _per_tonne_to_per_kg(usd_per_tonne: float) -> float:
    return float(usd_per_tonne) / KG_PER_TONNE


# ─────────────────────────────────────────────────────────────────────────────
# MINERAL REFERENCE TABLE
# ─────────────────────────────────────────────────────────────────────────────
# One row per entity that Module 1's TAXONOMY_COMPOSITION can name OR that the
# user might want to value separately.  Splits cleanly into two kinds:
#
#   • ELEMENTS  — actually tradable commodities, priced by markets.
#                 Live-price columns get filled by the fetchers.
#   • MINERALS  — rock-forming compounds, priced via their valuable elemental
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
# you refresh ref_price_usd_per_kg values (the numbers below — when a fresh
# audit re-reviews the static prices, bump this stamp).
_REF_PRICE_DATE = "2026-05-29"


# ─────────────────────────────────────────────────────────────────────────────
# WATER VALUE BY DELIVERY DESTINATION  (v1.2.0)
# ─────────────────────────────────────────────────────────────────────────────
# Water is the pipeline's single most consequential price.  It is ~100% of the
# bulk value of every C / B / D-type asteroid, so whichever number goes here
# determines the entire top of the profitability ranking.
#
# Water has no intrinsic scarcity value — it is worth what it costs to put it
# where the customer is.  So the price is a function of DESTINATION, not of
# the asteroid:
#
#   earth_surface — you flew it down a gravity well to a planet that is 71%
#                   ocean.  It is worth bulk industrial water, and even that
#                   overstates it once you account for the fact that nobody
#                   needs it.  This is what a sample-return architecture
#                   actually delivers.
#   leo           — worth the launch cost it avoids.  $4,250/kg matches the
#                   Falcon 9 reusable $/kg-to-LEO in Module 3, so the two
#                   modules stay consistent by construction.
#   cislunar      — worth the cost of lifting it to lunar vicinity.  Roughly
#                   3× the LEO figure, tracking the Δv difference between LEO
#                   and a TLI/NRHO depot.
#
# BEFORE v1.2.0 this table did not exist and water was hardcoded at the LEO
# figure while Module 4's mission model returned the material to Earth's
# surface — pricing the cargo as if it had been left in orbit.  That single
# inconsistency was worth a factor of ~4 million on C-type asteroids and
# inverted the entire ranking.

# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY DESTINATIONS  —  what a kilogram is worth, and where  (v1.3.0)
# ─────────────────────────────────────────────────────────────────────────────
#
# Material sold in space is worth the launch cost it AVOIDS.  That number is
# not asserted here — it is derived from the rocket equation, from the Δv
# ladder in Module 3's DELTA_V_REFERENCE, and from a real launch price.
#
# Constants below are cross-referenced to Module 3.  They are duplicated
# rather than imported because Module 2 runs BEFORE Module 3 in the pipeline
# order (and in the concatenated master.py), so the tables are not in scope.
# If you change one of these, change it in Module 3 too.

G0_M_S2 = 9.806_65                 # standard gravity, exact by definition

# Falcon 9 reusable $/kg-to-LEO — Module 3 LAUNCH_VEHICLES ($74M / 17.4 t).
# This is the cheapest operational figure in that table, so every in-space
# price derived from it is a LOWER bound on the launch cost avoided.
_LEO_USD_PER_KG = 4_253.0

# The stages that would have carried the payload up if you had launched it.
# Isp 465 s = hydrolox upper stage (Module 3 PROPELLANTS: LH2/LOX, 450-465 s
# vacuum).  Dry-mass fraction 0.10 is mid-range for a cryogenic upper stage
# (Centaur V ~0.08, DCSS ~0.11) — stage dry mass / (dry + propellant).
_TUG_ISP_S            = 465.0
_TUG_DRY_MASS_FRAC    = 0.10
# A LANDER is structurally much heavier than a tug for the same propellant
# load: throttleable engines, landing legs, terminal-guidance sensors.
# Apollo LM descent stage flew 2,134 kg dry on 8,200 kg of propellant = 0.21.
_LANDER_DRY_MASS_FRAC = 0.20

# Fraction of Mars ENTRY mass that survives to be useful payload on the
# surface.  Aeroshell, backshell, parachute and descent stage are all
# discarded.  Measured, not assumed:
#     MSL           entry 3,257 kg  ->  rover   899 kg  = 27.6%
#     Perseverance  entry 3,440 kg  ->  rover 1,025 kg  = 29.8%
# 0.30 takes the better of the two and is generous to Mars — larger entry
# vehicles should scale better than MSL's sky-crane, but nothing that size
# has flown.
_MARS_LANDED_MASS_FRACTION = 0.30

# ─── DELIVERY LEG CHAINS ─────────────────────────────────────────────────────
# Each destination is a SEQUENCE of legs above LEO, flown by real stages, and
# the mass ratios chain.  Modelling it leg-by-leg rather than as one big Δv
# matters: staging is worth a great deal, and a single-stage lunar lander
# burning 5,920 m/s would come out roughly twice as expensive as the two-stage
# chain that would actually be flown.
#
# Every Δv here appears in Module 3's DELTA_V_REFERENCE.
#   ("burn", Δv m/s, Isp s, dry fraction)  — a propulsive leg
#   ("edl",  surviving mass fraction)      — atmospheric entry, descent, landing
_DELIVERY_LEGS: Dict[str, Optional[List[tuple]]] = {
    "earth_surface": None,                       # already at the market
    "leo": [],                                   # nothing above LEO
    "cislunar": [
        ("burn", 3_600.0, _TUG_ISP_S, _TUG_DRY_MASS_FRAC),      # TLI + NRHO insertion
    ],
    "lunar_surface": [
        ("burn", 4_050.0, _TUG_ISP_S, _TUG_DRY_MASS_FRAC),      # TLI + LOI
        ("burn", 1_870.0, _TUG_ISP_S, _LANDER_DRY_MASS_FRAC),   # powered descent
    ],
    "mars_surface": [
        ("burn", 3_600.0, _TUG_ISP_S, _TUG_DRY_MASS_FRAC),      # TMI
        ("edl",  _MARS_LANDED_MASS_FRACTION),                   # aeroentry + landing
        ("burn",   800.0, _TUG_ISP_S, _LANDER_DRY_MASS_FRAC),   # retropropulsion
    ],
}


def _stage_mass_ratio(dv_m_s: float, isp_s: float, dry_mass_frac: float) -> float:
    """Initial mass needed per kg of payload for one propulsive leg.

        R  = exp(Δv / (Isp·g0))                        rocket equation
        p  = (R − 1)(1 + d)                            propellant per kg payload
        δ  = d / (d + p)   ⇒   d = δ(R−1) / (1 − δR)   stage dry mass
        m0 = R (1 + d)                                 total mass to start with

    Returns inf when δ·R ≥ 1 — the tank cannot close on that Δv and no amount
    of propellant will fix it.
    """
    if dv_m_s <= 0:
        return 1.0
    r = math.exp(float(dv_m_s) / (isp_s * G0_M_S2))
    if dry_mass_frac * r >= 1.0:
        return float("inf")
    d = dry_mass_frac * (r - 1.0) / (1.0 - dry_mass_frac * r)
    return r * (1.0 + d)


def delivered_cost_usd_per_kg(
    destination:    str,
    leo_usd_per_kg: float = _LEO_USD_PER_KG,
) -> float:
    """Cost of putting 1 kg of payload at `destination`, launched from Earth.

    This is the "launch cost avoided" that gives asteroid material its
    in-space value.  Derived, not tabulated: walk the destination's leg chain
    BACKWARDS from the payload, multiplying up the mass each leg demands, then
    charge the whole stack at the LEO launch price.

    An `edl` leg divides rather than multiplies — surviving 30% of entry mass
    means you must arrive with 1/0.30 = 3.33 kg for every kg that lands.
    """
    legs = _DELIVERY_LEGS.get(str(destination or "").strip().lower())
    if legs is None:
        return 0.0                       # earth_surface avoids no launch at all

    mass = 1.0                           # kg that must exist at the start of the chain
    for leg in reversed(legs):
        if leg[0] == "edl":
            frac = float(leg[1])
            mass = mass / frac if frac > 0 else float("inf")
        else:
            _, dv, isp, dry = leg
            mass *= _stage_mass_ratio(dv, isp, dry)
        if not math.isfinite(mass):
            return float("inf")
    return float(leo_usd_per_kg) * mass


# Terrestrial bulk-industrial water, for the earth_surface case.  Municipal /
# industrial bulk water runs $0.0005-0.002/kg — asteroid water landed on Earth
# competes with rain.
_EARTH_SURFACE_WATER_USD_PER_KG = 0.001


_DESTINATION_NOTES = {
    "leo":           "Falcon 9 reusable $/kg-to-LEO, straight off Module 3.",
    "cislunar":      "TLI + NRHO insertion (3,600 m/s) on one cryo stage.",
    "lunar_surface": "TLI + LOI (4,050 m/s) on a cryo stage, then powered "
                     "descent (1,870 m/s) on a lander.  No atmosphere, so "
                     "every metre per second is propulsive — the Moon is the "
                     "nearest destination and among the dearest to land on.",
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
# A commodity with no in-space demand is not worthless at a depot — it is
# worth its Earth price MINUS whatever it costs to fly it the rest of the way
# down.  Someone has to pay that leg; the miner selling at the depot eats it
# in the price.
#
# Derived from the same Module 3 rates Module 4 charges for an Earth-return
# mission, so the two sides of the pipeline cannot drift apart:
#
#   capsule dry mass  0.10 x payload             @ $150,000/kg   (Module 3
#                                                 "Return capsule recurring")
#   TPS               0.15 x (payload + capsule) @  $50,000/kg   (Module 3
#                                                 "Heat shield / TPS", and
#                                                 0.15 is Module 4's
#                                                 heat_shield_frac_of_payload)
#   recovery campaign $15,000,000 over a nominal 10 t batch       (Module 3
#                                                 "Sample recovery operations")
#   departure burn    rocket-equation mass penalty for leaving the depot
#
# Coming down is far cheaper than going up — you need a heat shield, not a
# launch vehicle — which is why these numbers are a fraction of the
# launch-cost-avoided figures above.
_DOWNLEG_CAPSULE_DRY_FRAC   = 0.10
_DOWNLEG_TPS_FRAC           = 0.15
_DOWNLEG_CAPSULE_USD_PER_KG = 150_000.0
_DOWNLEG_TPS_USD_PER_KG     =  50_000.0
_DOWNLEG_RECOVERY_USD       = 15_000_000.0
_DOWNLEG_BATCH_KG           = 10_000.0
# Δv to leave the destination onto an Earth-return trajectory, entering
# directly.  All from Module 3's DELTA_V_REFERENCE.
#   leo           — deorbit burn, ~120 m/s
#   cislunar      — NRHO departure, ~450 m/s (symmetric with insertion)
#   lunar_surface — ascent to LLO (1,870) + trans-Earth injection (~850)
#   mars_surface  — Mars ascent (4,100) + TEI from LMO (2,100)
# The surface cases are punishing, and correctly so: hauling material back UP
# out of a gravity well you just landed in is close to the worst thing you can
# do with it.  Mars in particular ends up costing more to ship home than any
# commodity in this catalog is worth, which is the honest answer — you do not
# mine asteroids to deliver platinum to Mars and then fly it back.
_DOWNLEG_DEPARTURE_DV_M_S = {
    "leo":            120.0,
    "cislunar":       450.0,
    "lunar_surface": 2_720.0,
    "mars_surface":  6_200.0,
}


def downleg_cost_usd_per_kg(destination: str) -> float:
    """Cost of moving 1 kg from an in-space depot to the terrestrial market.

    Returns 0.0 for earth_surface — the material is already there.
    """
    key = str(destination or "").strip().lower()
    if key not in _DOWNLEG_DEPARTURE_DV_M_S:
        return 0.0
    capsule_kg = _DOWNLEG_CAPSULE_DRY_FRAC
    tps_kg     = _DOWNLEG_TPS_FRAC * (1.0 + capsule_kg)
    hardware   = (capsule_kg * _DOWNLEG_CAPSULE_USD_PER_KG
                  + tps_kg * _DOWNLEG_TPS_USD_PER_KG)
    recovery   = _DOWNLEG_RECOVERY_USD / _DOWNLEG_BATCH_KG
    # Departure burn shows up as extra mass to be built and flown.
    r = math.exp(_DOWNLEG_DEPARTURE_DV_M_S[key] / (_TUG_ISP_S * G0_M_S2))
    return (hardware + recovery) * r


# ─── IN-SPACE UTILITY BY COMMODITY ───────────────────────────────────────────
# How much of the launch-cost-avoided a commodity actually captures at an
# in-space destination.  1.0 means it is a drop-in substitute for the same
# mass launched from Earth; 0.0 means there is no in-space market for it at
# all and it can only be sold by flying it down.
#
# ⚠️  THESE ARE ENGINEERING JUDGEMENTS, NOT MEASUREMENTS.  Unlike the price
# above — which is derived from the rocket equation and a real launch price —
# no market exists yet to calibrate these against.  They are the single
# biggest soft assumption in the in-space case, so they live here as one
# obvious table rather than being buried per-entry.
IN_SPACE_UTILITY: Dict[str, float] = {
    # Volatiles — the canonical in-space commodity.  Water is propellant
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
    "magnetite":        0.40,   # oxide — needs reduction before it is metal
    "troilite":         0.30,   # sulphur source, minor structural use
    # Silicates.  Usable as bulk radiation shielding and as 3-D-printing /
    # sintering feedstock, but a poor per-kg substitute for engineered
    # structure, and available in quantity from the Moon as well.
    "olivine":          0.25, "pyroxene":        0.25, "orthopyroxene": 0.25,
    "enstatite":        0.25, "plagioclase":     0.25, "spinel":        0.25,
    "phyllosilicates":  0.25, "oxides":          0.25, "silicates":     0.25,
    # Carbon and organics — composites, plastics, agriculture feedstock.
    "carbon":           0.40,
    "organics":         0.20,
    # Everything not listed — the precious metals above all — defaults to 0.0.
    # That does NOT make them worthless at a depot: a zero here means only
    # that nobody in orbit wants the material for its own sake, so it is
    # valued by shipping it down instead (terrestrial price less the downleg).
    # See in_space_price_usd_per_kg.
}
IN_SPACE_UTILITY_DEFAULT = 0.0


def value_for_destination(destination: str) -> dict:
    """Look up the delivered-value basis for a delivery destination.

    Unknown destinations fall back to earth_surface — the conservative
    choice — rather than silently keeping an in-space premium.
    """
    key = str(destination or "").strip().lower()
    if key not in DELIVERY_DESTINATIONS:
        print(f"     ⚠️   Unknown delivery_destination {destination!r} — "
              f"falling back to 'earth_surface'.  Valid: "
              f"{', '.join(sorted(DELIVERY_DESTINATIONS))}")
        key = "earth_surface"
    return DELIVERY_DESTINATIONS[key]


def in_space_price_usd_per_kg(
    name: str, destination: str, terrestrial_usd_per_kg: Optional[float],
) -> Optional[Tuple[float, str]]:
    """Value of 1 kg of `name` sitting at `destination`, and how it is realised.

    Returns (usd_per_kg, route) — or None at earth_surface, where the
    terrestrial price already stands.

    A kilogram at a depot has two possible fates, and it is worth the better
    of them:

      USE IT IN SPACE.  Worth what an equivalent kilogram delivered from Earth
        would have cost: its purchase price PLUS the launch bill.  Note the
        PLUS — v1.3.0 replaced the terrestrial price with the launch cost,
        which quietly threw the material itself away.  Scaled by
        `in_space_utility`, which is how good a substitute it actually is for
        the launched article.  Only available where demand exists (utility>0).

      SHIP IT DOWN.  Worth the terrestrial price less the cost of the onward
        leg to the surface.  Always available, and it is what puts a real,
        non-zero number on platinum at a depot: nobody in orbit wants
        platinum, but it is still platinum.

    Floored at zero — material too cheap to be worth the freight is worth
    nothing, not a negative.
    """
    dest = value_for_destination(destination)
    if dest["dv_above_leo_m_s"] is None or dest["usd_per_kg"] <= 0.0:
        return None                                   # earth_surface

    terrestrial = float(terrestrial_usd_per_kg or 0.0)
    utility     = IN_SPACE_UTILITY.get(name, IN_SPACE_UTILITY_DEFAULT)

    use_in_space = (terrestrial + utility * dest["usd_per_kg"]
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
        "yfinance_ticker":       None,           # iron ore (TIO=F) is CNY/MT — skip
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
        # This is the TERRESTRIAL price — bulk industrial water, what a
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
    # MINERALS  (rock-forming compounds — priced via elemental yield)
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
            # Bulk metals — typical IIIAB iron-meteorite Fe-Ni alloy.
            "iron":      0.900,    # ~90 wt% Fe
            "nickel":    0.090,    # 7-10 wt% Ni in IIIAB octahedrites
            "cobalt":    0.005,
            # Platinum-group metals (PGMs).  Siderites average ~30 ppm total
            # PGM (per USGS Bulletin 1214 / Nichiporuk 1965).  Distribution
            # below sums to ~37 ppm total + 1 ppm Au, calibrated to IIIAB
            # medium-octahedrite means.  Ir bumped from 2→4 ppm (range cited
            # at 0.01-19 ppm).  Ru + Os added (were missing in v1.1.0-1.1.1)
            # — both concentrate in the metallic phase and are present at
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
    # RARE-MINERAL PHASES  (v1.1.3 — added for PGM-rich inclusions)
    # ══════════════════════════════════════════════════════════════════════
    # These minerals are NOT referenced by Module 1's TAXONOMY_COMPOSITION
    # (which uses "nickel-iron" as the bulk metal carrier).  They are
    # available as targets for user-supplied per-asteroid composition
    # overrides or future spectral-identification work.  Each is a real
    # PGM-bearing phase documented in iron meteorites, chondrites, or
    # ureilites — see references in each row's `notes`.

    {   # ── Sperrylite ────────────────────────────────────────────────────
        # Pt arsenide — the dominant terrestrial Pt ore (Sudbury, Stillwater).
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
        # PGMs at 10-100× chondritic — used here as a PGM-enriched analog
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
        "yields": {},                              # Mg/Si silicate — no traded yield
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

print(f"✅  Reference table ready — {len(MINERAL_REFERENCE)} entries "
      f"({sum(1 for r in MINERAL_REFERENCE if r['kind'] == 'element')} elements / "
      f"{sum(1 for r in MINERAL_REFERENCE if r['kind'] == 'mineral')} minerals)")


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
    entirely — individual tickers that fail are logged but don't abort.
    """
    print("\n💰  yfinance  (Yahoo Finance) — fetching live futures …")

    try:
        import yfinance as yf
    except ImportError:
        print("     ❌  yfinance not importable — skipped")
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
                print(f"     ⚠️  {entry['name']:11s} ({ticker}) — no close data")
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
                print(f"     ⚠️  {entry['name']:11s} ({ticker}) — unknown unit {unit!r}")
                continue

            rows.append({
                "name":              entry["name"],
                "live_price_usd_per_kg": price_kg,
                "live_price_date":   last_date,
                "live_price_source": f"yfinance:{ticker}",
            })
            print(f"     ✅  {entry['name']:11s} ({ticker}) "
                  f"= {last_close:>10,.2f} USD/{unit:7s} "
                  f"→ {price_kg:>12,.2f} USD/kg  [{last_date}]")

        except Exception as exc:
            print(f"     ❌  {entry['name']:11s} ({ticker}) — {type(exc).__name__}: {exc}")

    if not rows:
        print("     ⚠️  yfinance returned no usable rows")
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
    one — the demo endpoint is too rate-limited to be useful for a pipeline.
    Returns an empty DataFrame on any HTTP / parse failure.
    """
    if config.metals_api_key == "DEMO" or not config.metals_api_key:
        print("\n🔗  metals.dev — skipped (no API key set; edit MINERAL_CONFIG.metals_api_key)")
        return pd.DataFrame()

    print("\n🔗  metals.dev — fetching live LME / spot prices …")

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
        print(f"     ❌  metals.dev failed: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    quotes = payload.get("metals") or payload.get("rates") or {}
    if not quotes:
        print("     ⚠️  metals.dev returned no `metals` payload")
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
        print(f"     ✅  {entry['name']:11s} = {usd_per_toz:>10,.2f} USD/troy_oz "
              f"→ {price_kg:>12,.2f} USD/kg")

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# REFERENCE-TABLE FETCHER  (always-on fallback)
# ─────────────────────────────────────────────────────────────────────────────
# Materialises MINERAL_REFERENCE into a DataFrame.  Doesn't hit the network,
# so it always succeeds; downstream merge uses it to fill the gaps left by
# the live sources.

def fetch_reference_table(config: MineralValueConfig) -> pd.DataFrame:
    """Static USGS / LME / mineralogy reference data — always available."""
    print("\n📚  Reference table — loading curated prices + densities …")

    # Every row here carries its TERRESTRIAL price.  The in-space repricing is
    # applied once, uniformly, after the merge — see apply_delivery_destination
    # — because it has to override live quotes too (platinum's LME price is
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
    print(f"     ✅  {len(df)} reference rows loaded")
    return df


def apply_delivery_destination(
    catalog: pd.DataFrame, config: MineralValueConfig,
) -> pd.DataFrame:
    """Reprice the whole catalog for the configured delivery destination.

    At `earth_surface` this is a no-op: every commodity keeps the terrestrial
    price the sources supplied.

    At an in-space destination every commodity is revalued to the better of
    its two fates — used in space, or shipped down to the terrestrial market.
    See in_space_price_usd_per_kg for the rule.  Two consequences worth being
    explicit about, because they are the whole point of the field:

      • Bulk material becomes enormously more valuable.  Iron is worth $0.50/kg
        on Earth and ~$2,978/kg in LEO, because a kilogram of structural metal
        already in orbit is a kilogram nobody has to launch.
      • Precious metals lose their in-space premium but keep their value.
        Nobody in orbit wants platinum, so it is priced by shipping it down:
        terrestrial price less the downleg.  ~$31,700/kg in LEO against
        $57,074 on the ground — a real discount, not a wipeout.

    Applied after merge_mineral_sources so it overrides live quotes as well as
    reference ones.
    """
    dest_key = str(config.delivery_destination or "").strip().lower()
    dest     = value_for_destination(dest_key)
    if dest["usd_per_kg"] <= 0.0:
        print(f"\n🌍  Delivery destination '{dest_key}' — terrestrial prices stand.")
        return catalog

    downleg = downleg_cost_usd_per_kg(dest_key)
    print(f"\n🛰️   Repricing for delivery to '{dest_key}' …")
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
        utility = IN_SPACE_UTILITY.get(str(name), IN_SPACE_UTILITY_DEFAULT)
        new_price.append(price)
        routes.append(route)
        new_basis.append(
            f"terrestrial + {utility:.2f} x launch cost avoided"
            if route == "used in space" else "terrestrial price less downleg"
        )

    catalog["terrestrial_price_usd_per_kg"] = catalog["price_usd_per_kg"]
    catalog["in_space_utility"] = [
        IN_SPACE_UTILITY.get(str(n), IN_SPACE_UTILITY_DEFAULT) for n in catalog["name"]
    ]
    catalog["downleg_cost_usd_per_kg"] = downleg
    catalog["value_route"]     = routes
    catalog["price_usd_per_kg"] = new_price
    catalog["value_basis"]      = new_basis
    catalog["price_basis"]      = "derived-in-space"

    n_use  = routes.count("used in space")
    n_ship = routes.count("shipped to Earth")
    n_zero = int((pd.to_numeric(catalog["price_usd_per_kg"], errors="coerce") == 0).sum())
    print(f"     ✅  {n_use} sold in space, {n_ship} shipped down "
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
    print("\n🔗  Merging sources …")

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
    """Light sanity checks — print warnings, never drop rows."""
    print("\n🔎  Validating catalog …")

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
            print(f"     ⚠️  {len(suspicious)} rows in {col} outside USD/kg sanity band "
                  f"[0.001, 1e7] — possible unit-conversion bug:")
            for _, r in suspicious.iterrows():
                print(f"          {r['name']}: {r[col]}")
    print(f"     ✅  Unit check: all price columns are USD/kg "
          f"(checked {', '.join(c for c in PRICE_COLS if c in catalog.columns)})")

    # Density should be positive and physically plausible (< 25 g/cm³, the
    # densest stable elements top out around osmium / iridium at ~22.6).
    bad_density = catalog[
        (catalog["density_gcm3"].isna())
        | (catalog["density_gcm3"] <= 0)
        | (catalog["density_gcm3"] > 25)
    ]
    if not bad_density.empty:
        print(f"     ⚠️  {len(bad_density)} rows with implausible density:")
        for _, r in bad_density.iterrows():
            print(f"          {r['name']}: {r['density_gcm3']} g/cm³")

    # Every mineral should reference at least one known element via `yields`
    # (otherwise Module 3 can't value it).  Bulk silicates legitimately have
    # no yield — that's a warning, not an error.
    known_elements = set(catalog.loc[catalog["kind"] == "element", "name"])
    for _, r in catalog[catalog["kind"] == "mineral"].iterrows():
        try:
            ymap = json.loads(r["yields_json"] or "{}")
        except json.JSONDecodeError:
            print(f"     ❌  {r['name']}: malformed yields_json")
            continue
        unknown = set(ymap) - known_elements
        if unknown:
            print(f"     ⚠️  {r['name']}: yields reference unknown elements {sorted(unknown)}")

    print(f"     ✅  Validation complete")
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
      3. Merge — live wins, reference fills gaps
      4. Validate
      5. Sort, tag, export
    """
    t0 = datetime.now()

    print("=" * 65)
    print("  💎  MINERAL VALUE PIPELINE — MODULE 2")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  v{config.pipeline_version}")
    print("=" * 65)

    # ── Step 1 — Live-price fetchers (in priority order) ─────────────────────
    live_frames = [
        fetch_yfinance(config)    if config.use_yfinance    else pd.DataFrame(),
        fetch_metals_dev(config)  if config.use_metals_api  else pd.DataFrame(),
    ]

    # ── Step 2 — Reference spine ─────────────────────────────────────────────
    reference = (
        fetch_reference_table(config)
        if config.use_reference_table else pd.DataFrame()
    )
    if reference.empty:
        print("\n❌  Pipeline aborted — reference table disabled and no live data spine")
        return pd.DataFrame()

    # ── Step 3 — Merge ───────────────────────────────────────────────────────
    catalog = merge_mineral_sources(reference, live_frames)

    # ── Step 3b — Reprice for the delivery destination ───────────────────────
    # Must follow the merge: at an in-space destination this overrides live
    # quotes too, since a terrestrial spot price is not what a commodity is
    # worth at a depot.
    catalog = apply_delivery_destination(catalog, config)

    # ── Step 4 — Validate ────────────────────────────────────────────────────
    catalog = validate_minerals(catalog)

    # ── Step 5 — Metadata + sort ─────────────────────────────────────────────
    catalog["catalog_date"]         = t0.strftime("%Y-%m-%d")
    catalog["pipeline_version"]     = config.pipeline_version
    # Stamped into every row: the water price — and therefore the whole
    # downstream ranking — is meaningless without knowing which destination
    # it was priced for.
    catalog["delivery_destination"] = config.delivery_destination

    catalog = catalog.sort_values(
        ["kind", "price_usd_per_kg"], ascending=[True, False]
    ).reset_index(drop=True)

    # ── Step 6 — Save ────────────────────────────────────────────────────────
    out_path = os.path.join(config.output_dir, config.catalog_filename)
    catalog.to_csv(out_path, index=False)
    print(f"\n     💾  Catalog saved → {out_path}")

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - t0).total_seconds()
    print("\n" + "=" * 65)
    print("  ✅  MINERAL VALUE CATALOG COMPLETE")
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

    regex=False — a query like "nickel-iron (alloy)" would otherwise be read
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


print("\n✅  Helper utilities available:")
print("    lookup_mineral(catalog, 'gold')")
print("    value_per_kg(catalog, 'platinum')")
print("    mineral_to_element_value(catalog, 'nickel-iron')")




# ═════════════════════════════════════════════════════════════════════════
# MODULE 3 — TRANSPORTATION DATA
# ═════════════════════════════════════════════════════════════════════════




# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import os
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

import numpy as np
import pandas as pd

for _cat in (DeprecationWarning, FutureWarning, UserWarning):
    warnings.filterwarnings("ignore", category=_cat)

pd.set_option("display.max_columns", None)
pd.set_option("display.float_format", "{:.4g}".format)


# ═════════════════════════════════════════════════════════════════════════════
# ║                                                                           ║
# ║   ★  USER SETTINGS — EDIT THESE TO TUNE THE PIPELINE  ★                  ║
# ║                                                                           ║
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
    # Colab detection.  os.path.isdir("/content") alone is not enough: on
    # Windows a leading "/" is drive-relative, so it tests C:\content -- a
    # directory an earlier run of the pre-fix code may itself have created,
    # which would route output straight back to the path this function
    # exists to avoid.  Require a POSIX platform as well.
    if os.name == "posix" and os.path.isdir("/content"):
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
    request_timeout: int = 60

    # ─── OUTPUT ──────────────────────────────────────────────────────────────
    output_dir:       str = _DEFAULT_OUTPUT_DIR
    # Four sub-files land in `<output_dir>/transportation/`:
    #     launch_vehicles.csv, propellants.csv,
    #     delta_v_segments.csv, operational_costs.csv
    # plus one composite summary file (vehicle × segment × propellant):
    #     transportation_summary.csv
    subdir:           str = "transportation"

    # ─── UNIT INVARIANT ──────────────────────────────────────────────────────
    # All monetary values in this pipeline are USD.  All physical quantities
    # use SI (kg, m, s, m/s).  Volumes in litres (not m³) because that is how
    # propellant tanks are quoted in the trade.  Enforced by validate_transport() and
    # carried in each output column's name (`_usd_per_kg`, `_m_per_s`, …)
    # rather than by config fields — CURRENCY / MASS_UNIT / DV_UNIT /
    # TIME_UNIT constants lived here but nothing ever read them, so they
    # documented an invariant they did not actually enforce.

    # ─── ISRU (In-Situ Resource Utilization) ─────────────────────────────────
    # If True, the return-leg propellant is assumed to be manufactured from
    # the asteroid's own water/regolith — its $/kg drops to the on-asteroid
    # processing cost (`isru_processing_usd_per_kg`) rather than the launched
    # propellant cost.  Default False = conservative (haul fuel both ways).
    isru_return_propellant:        bool  = False
    isru_processing_usd_per_kg:    float = 50.0   # rough lit estimate

    # ─── CONTINGENCY ─────────────────────────────────────────────────────────
    # Industry-standard mission-cost contingency.  20 % is typical for a
    # well-characterised flight programme; 35-50 % for first-of-kind.
    contingency_fraction: float = 0.20

    # ─── PIPELINE VERSION ────────────────────────────────────────────────────
    # 1.2.0 — initial release
    # 1.2.1 — May 2026 source-audit: launch prices re-cited, hydrazine $700→$75/kg,
    #         xenon $1.5k→$10k/kg, argon $1→$10/kg, H3 LEO 6.5→16.5t,
    #         SLS $2.5B→$4.1B, Falcon 9 $70→$74M, every notes field source-tagged.
    # 1.2.2 — second-pass sanity sweep:
    #         • SLS LEO 42t→105t (was confused with TLI figure); $/kg recalc
    #         • Falcon Heavy LEO 63.8t→57t to match the partial-reuse $97M price
    #         • Xenon density 5.4→2.0 g/cm³ (5.4 was physically impossible)
    #         • Starship escape: caveat that 27t assumes orbital refueling
    #         • Crew + Mining-payload-recurring rows: citations added
    # 1.2.3 — third-pass deep audit:
    #         • Falcon 9 GTO 8.3t→5.5t (8.3t was expendable; row is reusable)
    #         • Falcon 9 escape 4.0t→2.5t (4.0t was Mars-transfer, not C3=0 reusable)
    #         • mission_cost_breakdown: fixed rocket-equation bug — outbound
    #           prop now correctly includes return-prop dead-mass when ISRU off
    #           (was understating launch mass by ~110% in worked example)
    #         • Unused Optional import removed; docstring version stub generalised
    #         • Blend math hand-verified: ρ_kerolox=1.015, ρ_hydrolox=0.361,
    #           ρ_methalox=0.833, ρ_MMH/NTO=1.159 kg/L — all consistent.
    # 1.2.4 — switched to UNCREWED autonomous-only mission model:
    #         • Replaced 'Crew (if crewed mission)' row ($400M/crew-yr) with
    #           'Autonomous mining control & AI (NRE)' ($200M per program)
    #         • All downstream Module 4 cost cascades now uncrewed by design;
    #           no life-support / crew-habitat mass overhead anywhere
    # 1.2.5 — portability, no change to any number produced:
    #         • output_dir defaults via _default_output_dir() instead of a
    #           hardcoded /content/asteroid_pipeline, which on Windows
    #           silently resolved to C:\content
    #         • stdout/stderr forced to UTF-8 before the first print — the
    #           emoji progress output crashed cp1252 consoles instantly
    #         • RUN & PREVIEW moved under a main-guard so importing the
    #           module no longer triggers a full run
    # 1.3.0 — realism audit.  Two additions, both consumed by Module 4 v1.4.0:
    #         • New `dv_penalty_factor` column on PROPELLANTS_REFERENCE.
    #           The rocket equation does not care about thrust, but
    #           trajectories do: a milli-newton electric stage cannot fly the
    #           impulsive burns DELTA_V_REFERENCE assumes.  Spiralling out of
    #           LEO costs ~7 km/s against ~3.2 km/s impulsive.  Chemical
    #           systems carry 1.0; electric carry 1.5.  Without it, Isp
    #           3,000 s wins the payload cascade on a Δv budget it cannot
    #           achieve.
    #         • New OPERATIONAL_COSTS row "Return capsule recurring cost" at
    #           $150k/kg.  Module 4 was billing the return capsule at the
    #           $300k/kg mining-payload rate, pricing a parachute-and-heat-
    #           shield can as regolith-contact machinery.
    #         New output column on propellants.csv: dv_penalty_factor.
    # 1.4.0 — IN-SPACE DELIVERY ARCHITECTURE.  Reference data for selling the
    #         mined material at an in-space destination instead of flying it
    #         down.  Paired with Module 2 v1.3.0 and Module 4 v1.5.0.
    #         Nothing existing changed value; this release is additive, so
    #         every number a v1.3.0 earth_surface run produced is unchanged.
    #         • 6 new DELTA_V_REFERENCE segments: the delivery ladder above
    #           LEO (TLI 3,150 / NRHO insertion 450 / LEO→NRHO 3,600 m/s) and
    #           the three asteroid return legs quoted at v_inf = 3 km/s
    #           (LEO propulsive 3,626, cislunar Oberth capture 944, LEO
    #           aerobraked 100 m/s).  The LEO→NRHO figure is what Module 2
    #           integrates to price material sold at a cislunar depot.
    #         • 3 new OPERATIONAL_COSTS rows: "Berthing adapter recurring
    #           cost" ($60k/kg — replaces the re-entry capsule for in-space
    #           delivery), "Depot berthing & handover operations" ($2M —
    #           replaces the $15M Earth recovery campaign), and "FAA Part 450
    #           licensing (launch only)" ($1.2M — no re-entry licence).
    #         The headline physical result these encode: cislunar is BOTH
    #         cheaper to reach from an asteroid than LEO (960 vs 3,590 m/s,
    #         because capture can take the Oberth benefit and NRHO is barely
    #         bound) AND worth more per kg on arrival.  Earth's surface is the
    #         cheapest to reach and worth the least.
    # 1.5.0 — SURFACE DESTINATIONS.  Reference data for delivering to a lunar
    #         or Mars surface base.  Paired with Module 2 v1.4.0 and Module 4
    #         v1.6.0.  Additive again — no existing number changed.
    #         • 8 new DELTA_V_REFERENCE segments: the lunar descent chain
    #           (TLI→LOI 900, NRHO→LLO 730, LLO→surface 1,870, and the
    #           LEO→lunar-surface total of 5,920 m/s), and the Mars chain
    #           (TMI 3,600, entry→surface retropropulsion 800, plus the
    #           surface→LMO 4,100 and LMO→Earth 2,100 return legs).
    #         • 1 new OPERATIONAL_COSTS row: "Surface lander recurring cost"
    #           at $200k/kg — a lander is active where a re-entry capsule is
    #           passive, so it sits above the $150k/kg capsule and below the
    #           $300k/kg mining rig.
    #         The Moon is the awkward case these numbers expose: it is the
    #         CLOSEST destination and among the most expensive to land on,
    #         because there is no atmosphere and every metre per second of
    #         the 5,920 m/s from LEO is paid propulsively.  Mars is four
    #         times further in Δv terms from Earth but gets most of its
    #         arrival braking free from an atmosphere.
    pipeline_version: str = "1.5.0"
    preview_rows:     int = 15


TRANSPORT_CONFIG = TransportConfig()
os.makedirs(os.path.join(TRANSPORT_CONFIG.output_dir, TRANSPORT_CONFIG.subdir), exist_ok=True)

print(f"✅  Configuration loaded — output dir: "
      f"{os.path.join(TRANSPORT_CONFIG.output_dir, TRANSPORT_CONFIG.subdir)}")
print(f"    Active sources : "
      f"{', '.join(s for s, on in (('yfinance', TRANSPORT_CONFIG.use_yfinance), ('reference', TRANSPORT_CONFIG.use_reference_table)) if on)}")
print(f"    ISRU return    : {TRANSPORT_CONFIG.isru_return_propellant}  "
      f"(processing cost {TRANSPORT_CONFIG.isru_processing_usd_per_kg:.0f} USD/kg if on)")
print(f"    Contingency    : {TRANSPORT_CONFIG.contingency_fraction:.0%}")


# ─────────────────────────────────────────────────────────────────────────────
# UNIT CONVERSION HELPERS
# ─────────────────────────────────────────────────────────────────────────────
# yfinance commodity quotes arrive in legacy units (USD/bbl, USD/MMBtu,
# USD/gallon).  Everything funnels through these helpers so output columns
# carry the explicit `_usd_per_kg` / `_usd_per_L` suffix.

G0_M_S2          = 9.806_65          # standard gravity, used in rocket equation
LITRES_PER_GAL   = 3.785_411_784     # US gallon → litre
LITRES_PER_BBL   = 158.987_294_928   # oil barrel → litre

# Approximate mass densities of liquid commodities at storage conditions.
# Used to map yfinance per-volume quotes onto per-mass propellant prices.
COMMODITY_DENSITY_KG_PER_L = {
    "crude_oil":       0.870,   # WTI ~32° API
    "heating_oil":     0.845,   # No. 2 distillate; kerosene/RP-1 proxy
    "rbob_gasoline":   0.740,
    "natural_gas":     0.422,   # methane LIQUID at boiling point (LNG/LCH4)
}


def _per_bbl_to_per_kg(usd_per_bbl: float, fluid: str) -> float:
    """Convert a $/barrel oil quote to $/kg using the named fluid's density."""
    rho = COMMODITY_DENSITY_KG_PER_L[fluid]
    return float(usd_per_bbl) / (LITRES_PER_BBL * rho)


def _per_gal_to_per_kg(usd_per_gal: float, fluid: str) -> float:
    """Convert a $/gallon quote to $/kg."""
    rho = COMMODITY_DENSITY_KG_PER_L[fluid]
    return float(usd_per_gal) / (LITRES_PER_GAL * rho)


def _per_mmbtu_to_per_kg_ng(usd_per_mmbtu: float) -> float:
    """
    Henry-Hub natural gas trades in $/MMBtu (1 MMBtu = 10⁶ BTU).
    1 kg LNG ≈ 50 MJ ≈ 0.04739 MMBtu.  So $/kg = $/MMBtu × 0.04739.
    """
    return float(usd_per_mmbtu) * 0.047_39


# ─────────────────────────────────────────────────────────────────────────────
# LAUNCH VEHICLE REFERENCE TABLE
# ─────────────────────────────────────────────────────────────────────────────
# One row per vehicle.  $/kg-to-LEO is the headline figure; $/kg-to-GTO and
# $/kg-to-escape are list_price_usd divided by the corresponding published
# payload mass for that destination — every row in this table uses real
# manufacturer / agency figures, not rules-of-thumb.
#
# For reusable vehicles the payload masses MUST be self-consistent with the
# stated list price's recovery mode (e.g. Falcon Heavy partial-reuse $97M
# pairs with ~57 t LEO, NOT the 63.8 t all-expendable max).  Watch for
# refueling-architecture caveats on Starship escape numbers.
#
# Sources cited inline in each row's `notes`; reference_year tags staleness.

_REF_YEAR_LAUNCH = 2026

LAUNCH_VEHICLES_REFERENCE: List[dict] = [
    {
        "name":                          "Falcon 9 (reusable)",
        "operator":                      "SpaceX",
        "status":                        "operational",
        "payload_leo_kg":                17_400,
        "payload_gto_kg":                 5_500,    # reusable drone-ship (8,300 is EXPENDABLE)
        "payload_escape_kg":              2_500,    # C3=0 reusable estimate (~$120M expendable lifts 4,020)
        "fairing_volume_m3":                145,
        "list_price_usd":            74_000_000,    # SatBase 2026-02 price hike (was $70M)
        "usd_per_kg_to_leo":              4_253,    # 74M / 17,400
        "usd_per_kg_to_gto":             13_455,    # 74M / 5,500
        "usd_per_kg_to_escape":          29_600,    # 74M / 2,500
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: SpaceX list price (raised to $74M Feb 2026 per SatBase) + "
                 "Falcon 9 Payload User's Guide.  All payload figures are the "
                 "drone-ship recovery (reusable) config.  Expendable mode lifts "
                 "5.5→8.3 t GTO and ~4 t to escape but costs ~$120M.",
    },
    {
        "name":                          "Falcon Heavy (reusable side cores)",
        "operator":                      "SpaceX",
        "status":                        "operational",
        "payload_leo_kg":                57_000,    # partial-reusable config (Wikipedia 2026)
        "payload_gto_kg":                 8_000,    # partial-reusable GTO
        "payload_escape_kg":              3_500,    # partial-reusable interplanetary
        "fairing_volume_m3":                145,
        "list_price_usd":            97_000_000,    # SpaceX list price, partial reusable
        "usd_per_kg_to_leo":              1_702,    # 97M / 57,000
        "usd_per_kg_to_gto":             12_125,    # 97M / 8,000
        "usd_per_kg_to_escape":          27_714,    # 97M / 3,500
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: SpaceX $97M for partial-reusable config (side cores "
                 "recovered, center core expended).  All payload figures "
                 "self-consistent with this config.  All-expendable mode lifts "
                 "63.8 t LEO / 26.7 t GTO but costs ~$150M (Wikipedia 2026).",
    },
    {
        "name":                          "Starship (projected)",
        "operator":                      "SpaceX",
        "status":                        "development",
        "payload_leo_kg":               100_000,    # fully reusable lower bound
        "payload_gto_kg":                21_000,    # single-launch, no refuel
        "payload_escape_kg":             27_000,    # WITH orbital refueling
        "fairing_volume_m3":              1_000,
        "list_price_usd":            90_000_000,    # Voyager Technologies contract 2026
        "usd_per_kg_to_leo":                900,    # 90M / 100,000
        "usd_per_kg_to_gto":              4_286,    # 90M / 21,000
        "usd_per_kg_to_escape":           3_333,    # 90M / 27,000 — see CAVEAT below
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: SpaceX-Voyager Technologies dedicated-launch contract "
                 "disclosed 2026 at $90M.  LEO at lower bound of 100-150 t fully-"
                 "reusable range, pending orbital qualification.  "
                 "CAVEAT: escape payload (27 t) > GTO (21 t) only because the "
                 "escape figure assumes orbital refueling (8-16 tanker flights). "
                 "Module 4 should add ~$90M × N_tankers to the escape-direct "
                 "scenario for an apples-to-apples comparison.",
    },
    {
        "name":                          "SLS Block 1B (Cargo)",
        "operator":                      "NASA",
        "status":                        "operational",
        "payload_leo_kg":               105_000,    # Block 1B Cargo LEO (NASA SLS factsheet)
        "payload_gto_kg":                41_000,    # GTO via EUS (~scaled to BLEO=42t)
        "payload_escape_kg":             42_000,    # TLI / interplanetary (NASA Artemis)
        "fairing_volume_m3":                340,
        "list_price_usd":         4_100_000_000,    # NASA OIG IG-24-015 fully-burdened
        "usd_per_kg_to_leo":             39_048,    # 4.1B / 105,000
        "usd_per_kg_to_gto":            100_000,    # 4.1B / 41,000
        "usd_per_kg_to_escape":          97_619,    # 4.1B / 42,000
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: NASA OIG IG-24-015 reports $4.1B per flight fully-burdened "
                 "(vehicle + Orion + service module + ground ops); OIG calls "
                 "'unsustainable'.  Payload masses from NASA SLS Block 1B Cargo "
                 "factsheet: 105 t LEO / 42 t TLI.",
    },
    {
        "name":                          "Atlas V 551",
        "operator":                      "ULA",
        "status":                        "operational",
        "payload_leo_kg":                18_850,
        "payload_gto_kg":                 8_900,
        "payload_escape_kg":              6_500,
        "fairing_volume_m3":                233,
        "list_price_usd":           153_000_000,
        "usd_per_kg_to_leo":              8_117,
        "usd_per_kg_to_gto":             17_191,
        "usd_per_kg_to_escape":          23_538,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: ULA RocketBuilder $153M base; government missions add "
                 "$30-80M for mission-assurance overhead (per SpaceNews 2024).",
    },
    {
        "name":                          "Vulcan Centaur VC6",
        "operator":                      "ULA",
        "status":                        "operational",
        "payload_leo_kg":                27_200,
        "payload_gto_kg":                14_400,
        "payload_escape_kg":              7_200,
        "fairing_volume_m3":                233,
        "list_price_usd":           110_000_000,
        "usd_per_kg_to_leo":              4_044,
        "usd_per_kg_to_gto":              7_639,
        "usd_per_kg_to_escape":          15_278,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: ULA / SpaceInsider 2025 — $110M starting price for "
                 "VC6 config (6 SRBs).  Payloads from ULA datasheet.",
    },
    {
        "name":                          "New Glenn",
        "operator":                      "Blue Origin",
        "status":                        "operational",   # promoted: 3 successful flights, 1st reuse Apr 2026
        "payload_leo_kg":                45_000,
        "payload_gto_kg":                13_600,
        "payload_escape_kg":              7_000,
        "fairing_volume_m3":                480,
        "list_price_usd":            68_000_000,
        "usd_per_kg_to_leo":              1_511,
        "usd_per_kg_to_gto":              5_000,
        "usd_per_kg_to_escape":           9_714,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Geekwire / Blue Origin May 2026 ($68-110M range, used "
                 "low end as customer base price).  First booster reuse Apr 2026.",
    },
    {
        "name":                          "Electron",
        "operator":                      "Rocket Lab",
        "status":                        "operational",
        "payload_leo_kg":                   320,
        "payload_gto_kg":                     0,
        "payload_escape_kg":                  0,
        "fairing_volume_m3":               1.85,
        "list_price_usd":             7_500_000,
        "usd_per_kg_to_leo":             23_438,
        "usd_per_kg_to_gto":              np.nan,
        "usd_per_kg_to_escape":           np.nan,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Rocket Lab Form 10-Q FY2026 Q1 — $7.5M / 320 kg LEO. "
                 "Small-sat dedicated; useful for prospector probes only.",
    },
    {
        "name":                          "Soyuz-2.1b",
        "operator":                      "Roscosmos",
        "status":                        "operational",
        "payload_leo_kg":                 8_300,    # Wikipedia 2026
        "payload_gto_kg":                 3_250,    # with Fregat upper stage
        "payload_escape_kg":              2_400,
        "fairing_volume_m3":                 80,
        "list_price_usd":            48_500_000,    # Glavkosmos 2018 with Fregat
        "usd_per_kg_to_leo":              5_843,
        "usd_per_kg_to_gto":             14_923,
        "usd_per_kg_to_escape":          20_208,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Glavkosmos / TASS 2018 price ($48.5M w/ Fregat). "
                 "Effectively unavailable to Western customers under sanctions.",
    },
    {
        "name":                          "Ariane 6 (A64)",
        "operator":                      "ArianeGroup / ESA",
        "status":                        "operational",
        "payload_leo_kg":                21_500,    # ESA datasheet
        "payload_gto_kg":                11_500,
        "payload_escape_kg":              8_000,
        "fairing_volume_m3":                124,
        "list_price_usd":           115_000_000,    # €100M+ per SpaceNexus 2026
        "usd_per_kg_to_leo":              5_349,
        "usd_per_kg_to_gto":             10_000,
        "usd_per_kg_to_escape":          14_375,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: ESA Ariane 6 overview + SpaceNexus 2026 ($77-115M range). "
                 "Four-booster A64 config; 30+ flights booked end-2025.",
    },
    {
        "name":                          "Long March 5",
        "operator":                      "CASC (China)",
        "status":                        "operational",
        "payload_leo_kg":                25_000,
        "payload_gto_kg":                14_000,
        "payload_escape_kg":              8_200,
        "fairing_volume_m3":                157,
        "list_price_usd":           110_000_000,    # estimate; pricing opaque
        "usd_per_kg_to_leo":              4_400,
        "usd_per_kg_to_gto":              7_857,
        "usd_per_kg_to_escape":          13_415,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Wikipedia / China-in-Space — payload masses authoritative; "
                 "$110M is an estimate (Chinese commercial pricing is opaque). "
                 "Chang'e-5 and Tianwen-1 launch heritage.",
    },
    {
        "name":                          "H3 (24L)",
        "operator":                      "MHI / JAXA",
        "status":                        "operational",
        "payload_leo_kg":                16_500,    # H3-24L per Wikipedia 2026 (was 6,500 — wrong)
        "payload_gto_kg":                 6_500,
        "payload_escape_kg":              4_000,
        "fairing_volume_m3":                184,
        "list_price_usd":            51_000_000,    # JAXA target ¥5B
        "usd_per_kg_to_leo":              3_091,    # 51M / 16,500
        "usd_per_kg_to_gto":              7_846,
        "usd_per_kg_to_escape":          12_750,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: JAXA H3 program target ¥5B (~$51M) per JAXA / Payload Space. "
                 "Successor to H-IIA targeting ~50% cost reduction.",
    },
]

print(f"✅  Launch vehicles reference loaded — {len(LAUNCH_VEHICLES_REFERENCE)} vehicles")


# ─────────────────────────────────────────────────────────────────────────────
# PROPELLANT REFERENCE TABLE
# ─────────────────────────────────────────────────────────────────────────────
# Each entry describes a propellant SYSTEM as actually used.  For bipropellants
# the listed values are the COMBINED mixture (oxidiser + fuel), weighted by
# the stage's typical oxidiser-to-fuel mass ratio.  This is what matters for
# the rocket equation, since the rocket spits out the combined mass.
#
# Vacuum Isp (s) is the interplanetary-relevant value — sea-level Isp is
# lower and only matters for the first stage of a launch vehicle (already
# baked into LAUNCH_VEHICLES_REFERENCE's $/kg-to-orbit).
#
# Density (kg/L) is the bulk combined density of fuel + oxidiser at storage
# conditions, weighted by mass.  Used for tank-sizing in Module 4.
#
# Cost (USD/kg) is the COMBINED cost of mixed propellant.  Live commodity
# prices (kerosene via heating oil, methane via natural gas) fill these
# from yfinance where applicable; the rest are OTC specialty-gas quotes.

# ─── LOW-THRUST Δv PENALTY  (v1.3.0) ─────────────────────────────────────────
# The rocket equation is indifferent to thrust, but trajectories are not.  A
# high-Isp electric stage cannot perform the impulsive burns the reference Δv
# table assumes: with milli-newton thrust it spirals, and a spiral is strictly
# more expensive in Δv than the equivalent impulsive manoeuvre.
#
#   • Escaping from LEO impulsively costs ~3.2 km/s.  Spiralling out costs
#     ~7 km/s — essentially the whole LEO orbital velocity — because thrust
#     is applied against a continuously rotating velocity vector.
#   • Interplanetary low-thrust transfers land in the same territory, running
#     ~1.3-2× the impulsive Δv depending on thrust-to-mass.
#
# `dv_penalty_factor` multiplies the mission Δv when Module 4 evaluates that
# propellant.  Without it, electric propulsion wins the payload cascade on an
# impulsive Δv budget it cannot actually fly.  1.5 is a mid-range figure; it
# does not capture the OTHER low-thrust cost, which is trip time — a spiral
# adds months to years that this pipeline's duration model does not yet see.
_LOW_THRUST_DV_PENALTY = 1.5

_REF_YEAR_PROP = 2026

# Helper: combined Isp / density / cost for a fuel + oxidiser pair, weighted
# by the stage mixture ratio (oxidiser-to-fuel by mass).
def _blend(of_ratio: float, fuel: dict, ox: dict) -> dict:
    """
    Blend fuel + oxidiser into a combined-propellant dict.
    of_ratio = mass(oxidiser) / mass(fuel) at stoichiometric / stage design.
    """
    fuel_frac = 1.0 / (1.0 + of_ratio)
    ox_frac   = of_ratio / (1.0 + of_ratio)
    # combined density (mass-weighted reciprocal — volumes add)
    rho = 1.0 / (fuel_frac / fuel["density_kg_per_L"]
                 + ox_frac  / ox["density_kg_per_L"])
    cost_kg = fuel_frac * fuel["cost_usd_per_kg"] + ox_frac * ox["cost_usd_per_kg"]
    return {
        "density_kg_per_L":   rho,
        "ref_cost_usd_per_kg": cost_kg,
        "fuel_mass_fraction":  fuel_frac,
        "ox_mass_fraction":    ox_frac,
    }


# Reference component prices ($/kg) — these are intermediate, used only to
# build the combined propellant rows below.  Values verified May 2026
# against the cited authoritative sources.
#
#   RP-1       Haltermann Solutions / SpaceInsider — typical $2-3/kg in bulk
#   LH2        NASA contract pricing 2024-25, ~$6/kg base + handling overhead
#   LCH4       Mobius Market Research 2024, ~$400/tonne open-market liquid
#   LOX        Astronautix / aqua-calc — bulk industrial cryogen ~$0.20/kg
#   N2O4       DOD Aerospace Standard Prices FY20 reference
#   MMH        DOD Aerospace Standard Prices FY20 reference
#   Hydrazine  DOD Standard Prices FY20 ($30.5/kg) to commercial AIAA ($75.8/kg)
#   Xenon      SETS Space / EFC 2024 — 99.999% purity ~$10,000/kg.
#              Density: NSTAR/Dawn supercritical storage ~2.0 g/cm³
#              (NBP liquid Xe = 3.057 g/cm³ is unreachable in flight tanks).
#   Argon      SETS Space 2024 — bulk industrial ~$7-15/kg.
#              Density: NBP liquid 1.395 g/cm³ (high-pressure gas ~0.5 g/cm³).
_COMPONENTS = {
    "RP-1":      {"density_kg_per_L": 0.810, "cost_usd_per_kg":      2.50},
    "LH2":       {"density_kg_per_L": 0.0708,"cost_usd_per_kg":     10.00},  # base + handling
    "LCH4":      {"density_kg_per_L": 0.422, "cost_usd_per_kg":      0.40},  # ~$400/tonne open market
    "LOX":       {"density_kg_per_L": 1.141, "cost_usd_per_kg":      0.20},
    "N2O4":      {"density_kg_per_L": 1.450, "cost_usd_per_kg":     35.00},
    "MMH":       {"density_kg_per_L": 0.870, "cost_usd_per_kg":    100.00},
    "Hydrazine": {"density_kg_per_L": 1.010, "cost_usd_per_kg":     75.00},  # DOD ref + handling
    "Xenon":     {"density_kg_per_L": 2.000, "cost_usd_per_kg": 10_000.00},  # supercritical Hall-thruster storage
    "Argon":     {"density_kg_per_L": 1.395, "cost_usd_per_kg":     10.00},  # liquid NBP (cryogenic storage)
}

_kerolox    = _blend(2.30, _COMPONENTS["RP-1"],      _COMPONENTS["LOX"])
_hydrolox   = _blend(6.00, _COMPONENTS["LH2"],       _COMPONENTS["LOX"])
_methalox   = _blend(3.60, _COMPONENTS["LCH4"],      _COMPONENTS["LOX"])
_mmh_nto    = _blend(1.65, _COMPONENTS["MMH"],       _COMPONENTS["N2O4"])

PROPELLANTS_REFERENCE: List[dict] = [
    {
        "name":                  "kerolox  (RP-1 / LOX)",
        "type":                  "bipropellant",
        "dv_penalty_factor":     1.0,
        "isp_vac_s":             340,
        "exhaust_vel_m_per_s":   340 * G0_M_S2,
        "density_kg_per_L":      _kerolox["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _kerolox["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _kerolox["ref_cost_usd_per_kg"] * _kerolox["density_kg_per_L"],
        "yfinance_proxy":        "heating_oil",   # RP-1 ≈ refined kerosene
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Workhorse 1st-stage propellant (Falcon 9, Atlas V kerolox).  "
                 "Vac Isp 340 s per RocketCEA / Astronautix.  Combined cost "
                 "weighted at 1:2.30 RP-1:LOX mix ratio.",
    },
    {
        "name":                  "hydrolox  (LH2 / LOX)",
        "type":                  "bipropellant",
        "dv_penalty_factor":     1.0,
        "isp_vac_s":             452,
        "exhaust_vel_m_per_s":   452 * G0_M_S2,
        "density_kg_per_L":      _hydrolox["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _hydrolox["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _hydrolox["ref_cost_usd_per_kg"] * _hydrolox["density_kg_per_L"],
        "yfinance_proxy":        None,            # LH2 has no spot ticker
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Highest chemical Isp.  Vac Isp 452 s per RS-25 / RL-10 datasheets. "
                 "LH2 base price $3-6/kg (NASA contracts); bulk-handling overhead "
                 "lifts effective cost to ~$10/kg.  Used on SLS, Centaur.",
    },
    {
        "name":                  "methalox  (LCH4 / LOX)",
        "type":                  "bipropellant",
        "dv_penalty_factor":     1.0,
        "isp_vac_s":             380,
        "exhaust_vel_m_per_s":   380 * G0_M_S2,
        "density_kg_per_L":      _methalox["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _methalox["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _methalox["ref_cost_usd_per_kg"] * _methalox["density_kg_per_L"],
        "yfinance_proxy":        "natural_gas",   # CH4 tracks NG=F (Henry Hub)
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Raptor (Starship) & BE-4 (Vulcan / New Glenn) engines.  "
                 "Vac Isp 380 s per SpaceX Raptor public data.  LCH4 ~$400/tonne "
                 "open-market per Mobius Market Research 2024.  ISRU-makeable on Mars.",
    },
    {
        "name":                  "MMH / NTO  (hypergolic)",
        "type":                  "bipropellant",
        "dv_penalty_factor":     1.0,
        "isp_vac_s":             336,
        "exhaust_vel_m_per_s":   336 * G0_M_S2,
        "density_kg_per_L":      _mmh_nto["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _mmh_nto["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _mmh_nto["ref_cost_usd_per_kg"] * _mmh_nto["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Storable hypergolic — standard for deep-space manoeuvring "
                 "(OMS, RCS, OSIRIS-REx propulsion).  Vac Isp 336 s per "
                 "Astronautix N2O4/MMH datasheet.  Pricing from DOD FY20 standards.",
    },
    {
        "name":                  "Hydrazine  (monoprop)",
        "type":                  "monopropellant",
        "dv_penalty_factor":     1.0,
        "isp_vac_s":             220,
        "exhaust_vel_m_per_s":   220 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Hydrazine"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Hydrazine"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Hydrazine"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Hydrazine"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Attitude control + small Δv.  Cat-bed decomposition.  "
                 "Vac Isp 220 s (Astronautix Hydrazine page).  "
                 "Pricing: DOD FY20 standard $30.5/kg, commercial $75.8/kg "
                 "(AIAA 2024).  Used $75/kg conservative for aerospace.",
    },
    {
        "name":                  "Xenon  (Hall / ion)",
        "type":                  "electric",
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "isp_vac_s":             3_000,
        "exhaust_vel_m_per_s":   3_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Xenon"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Xenon"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Xenon"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Xenon"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "10× the Isp of chemical; low thrust ⇒ months of burn.  "
                 "Used by Dawn, BepiColombo, NEXT-C.  "
                 "SETS Space 2024: $5-12k/kg for 99.999% aerospace-grade Xe; "
                 "used $10k/kg (2023 EFC reference).",
    },
    {
        "name":                  "Argon  (Hall / ion)",
        "type":                  "electric",
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "isp_vac_s":             1_500,
        "exhaust_vel_m_per_s":   1_500 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Argon"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Argon"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Argon"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Argon"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Starlink-V2 thruster choice (SpaceX claims 2.4× thrust, 1.5× Isp "
                 "of their previous Kr design).  Bulk industrial $7-15/kg per "
                 "SETS Space 2024; used $10/kg midpoint.",
    },
]

print(f"✅  Propellant reference loaded — {len(PROPELLANTS_REFERENCE)} fuel systems")


# ─────────────────────────────────────────────────────────────────────────────
# MISSION Δv REFERENCE TABLE
# ─────────────────────────────────────────────────────────────────────────────
# Typical Δv (m/s) and trip duration (yr) for each segment of a round-trip
# asteroid mining mission.  Sources: NASA NTRS, JPL design handbooks,
# Asterank's mission-design statistics.  Δv values are representative
# means — Module 4 should override per-asteroid using the orbital elements
# from Module 1 (semi_major_axis_au, eccentricity, inclination) where
# tighter accuracy is needed.

DELTA_V_REFERENCE: List[dict] = [
    {"segment": "surface  →  LEO ascent",         "dv_m_per_s":  9_400, "duration_yr": 0.001,
     "notes": "Textbook value including gravity + drag losses (NASA SP-125, "
              "Curtis 'Orbital Mechanics for Engineering Students').  "
              "Already priced into LAUNCH_VEHICLES."},
    {"segment": "LEO  →  GTO",                    "dv_m_per_s":  2_440, "duration_yr": 0.001,
     "notes": "Standard GEO transfer Δv (NASA orbital mechanics handbook)."},
    {"segment": "LEO  →  Earth escape (C3=0)",    "dv_m_per_s":  3_200, "duration_yr": 0.003,
     "notes": "C3=0 escape from 200-km LEO; same magnitude as TLI."},
    {"segment": "LEO  →  easy NEA (low-Δv class)","dv_m_per_s":  4_500, "duration_yr": 1.0,
     "notes": "Per Elvis et al. 2011 (arXiv:1105.4152): ultra-low Δv NEAs are "
              "~65 of 6699 known NEOs as of 2010 — bottom decile of accessibility."},
    {"segment": "LEO  →  average NEA",            "dv_m_per_s":  6_500, "duration_yr": 1.5,
     "notes": "Median NEA Δv per low-Δv NEA survey (arXiv:1406.5027); "
              "matches OSIRIS-REx Bennu mission profile."},
    {"segment": "LEO  →  hard NEA",               "dv_m_per_s":  8_500, "duration_yr": 2.0,
     "notes": "Upper-decile NEA (inclined or eccentric); approaches MBA territory."},
    {"segment": "LEO  →  main-belt asteroid",     "dv_m_per_s": 10_500, "duration_yr": 3.5,
     "notes": "Per Taylor et al. 2018 'Δv map of Main Belt Asteroids' "
              "(Acta Astronautica 146:73) — Hohmann transfer to ~2.7 AU."},
    {"segment": "Asteroid station-keeping",       "dv_m_per_s":    200, "duration_yr": 0.5,
     "notes": "Proximity ops, sample retrieval — OSIRIS-REx station-keeping budget."},
    {"segment": "NEA  →  Earth return (propulsive)","dv_m_per_s":  5_500, "duration_yr": 1.5,
     "notes": "Symmetric to outbound; powered Earth-return with no aerobraking."},
    {"segment": "NEA  →  Earth return (aerocap)", "dv_m_per_s":  1_500, "duration_yr": 1.5,
     "notes": "Aerocapture reduces propulsive Δv by ~4 km/s (heat-shield mass "
              "penalty captured separately under operational_costs TPS row)."},
    {"segment": "Main belt  →  Earth return",     "dv_m_per_s":  7_500, "duration_yr": 4.0,
     "notes": "Per Taylor 2018 — long cruise; favours electric propulsion."},
    {"segment": "Lunar surface  →  LEO",          "dv_m_per_s":  5_900, "duration_yr": 0.01,
     "notes": "Apollo Lunar Module ascent + plane change — reference for lunar-relay arch."},

    # ── Delivery ladder above LEO  (v1.4.0) ──────────────────────────────────
    # These price the "launch cost avoided" for material sold in space, and
    # give Module 4 the return-leg budget for a non-Earth-surface delivery.
    {"segment": "LEO  →  TLI (trans-lunar injection)", "dv_m_per_s": 3_150, "duration_yr": 0.01,
     "notes": "Apollo TLI 3.05-3.20 km/s (NASA SP-4029 / Apollo-by-the-Numbers). "
              "Effectively the same burn as LEO→Earth-escape, 50 m/s cheaper "
              "because the Moon is bound rather than at C3=0."},
    {"segment": "TLI  →  NRHO insertion",         "dv_m_per_s":    450, "duration_yr": 0.01,
     "notes": "Near-rectilinear halo orbit insertion for Gateway / Orion, "
              "~0.4-0.45 km/s (NASA Gateway NRHO trade studies, Whitley & "
              "Martinez 2016 'Options for Staging Orbits in Cis-Lunar Space'). "
              "NRHO is the cheapest usefully-stable cislunar depot orbit."},
    {"segment": "LEO  →  cislunar NRHO depot",    "dv_m_per_s":  3_600, "duration_yr": 0.02,
     "notes": "TLI + NRHO insertion.  This is the Δv that a kilogram of "
              "asteroid material delivered to NRHO AVOIDS having to be lifted "
              "through — it sets the cislunar sale price in Module 2."},

    # ── Lunar surface  (v1.5.0) ──────────────────────────────────────────────
    {"segment": "TLI  →  low lunar orbit (LOI)", "dv_m_per_s":    900, "duration_yr": 0.01,
     "notes": "Apollo lunar-orbit insertion, 0.9 km/s (NASA SP-4029).  Larger "
              "than NRHO insertion because LLO is a much more tightly bound "
              "orbit — which is exactly why NRHO is the cheaper depot."},
    {"segment": "NRHO  →  low lunar orbit",      "dv_m_per_s":    730, "duration_yr": 0.01,
     "notes": "Gateway-to-LLO transfer, ~0.73 km/s (Whitley & Martinez 2016). "
              "The price a cislunar depot pays to service the surface."},
    {"segment": "LLO  →  lunar surface (descent)", "dv_m_per_s": 1_870, "duration_yr": 0.001,
     "notes": "Apollo LM powered descent, 1.87 km/s including hover and "
              "terminal guidance reserve (NASA SP-4029).  No atmosphere means "
              "no aerobraking is available — every metre per second is paid "
              "for propulsively, which is why the Moon is expensive to reach "
              "despite being close."},
    {"segment": "LEO  →  lunar surface",         "dv_m_per_s":  5_920, "duration_yr": 0.02,
     "notes": "TLI (3,150) + LOI (900) + descent (1,870).  Sets the "
              "lunar-base sale price in Module 2.  Apollo's LEO-to-surface "
              "budget was ~6 km/s, which this matches."},

    # ── Mars  (v1.5.0) ───────────────────────────────────────────────────────
    {"segment": "LEO  →  trans-Mars injection",  "dv_m_per_s":  3_600, "duration_yr": 0.7,
     "notes": "Minimum-energy Hohmann TMI at a favourable opportunity; the "
              "real figure swings 3.6-4.3 km/s across the 26-month synodic "
              "cycle (NASA DRA 5.0).  The low end is used, so the delivered "
              "cost is a LOWER bound."},
    {"segment": "Mars entry  →  surface (retroprop)", "dv_m_per_s": 800, "duration_yr": 0.001,
     "notes": "Terminal propulsive descent after aeroentry and parachutes. "
              "MSL's sky-crane phase used ~0.4 km/s; Starship-class EDL "
              "estimates run 0.5-1.0 km/s for supersonic retropropulsion of a "
              "heavy lander.  Mid-range taken.  The aeroshell and parachute "
              "mass is carried separately as a landed-mass fraction — see "
              "Module 2's _MARS_LANDED_MASS_FRACTION."},
    {"segment": "Mars surface  →  low Mars orbit", "dv_m_per_s": 4_100, "duration_yr": 0.001,
     "notes": "Mars ascent including gravity and drag losses (NASA DRA 5.0 "
              "MAV sizing).  Relevant only to the downleg — shipping material "
              "OFF Mars — and it is brutal enough that nothing mined for a "
              "Mars base is worth flying home."},
    {"segment": "Low Mars orbit  →  Earth (TEI)", "dv_m_per_s": 2_100, "duration_yr": 0.7,
     "notes": "Trans-Earth injection from LMO (NASA DRA 5.0)."},

    # ── Asteroid return legs by delivery destination  (v1.4.0) ───────────────
    # Reference magnitudes only; Module 4 computes these per-asteroid from the
    # actual arrival v_infinity.  Quoted here at v_inf = 3 km/s, a typical NEA
    # return, so the three architectures can be compared at a glance.
    {"segment": "NEA  →  LEO delivery (propulsive)", "dv_m_per_s": 3_626, "duration_yr": 1.5,
     "notes": "Circularising into LEO from a v_inf=3 km/s arrival hyperbola: "
              "sqrt(v_esc^2 + v_inf^2) - v_circ at 200 km.  The most expensive "
              "destination to reach propulsively — LEO sits deepest in the well "
              "of the three, which is exactly why material there is worth most "
              "per kg and costs most to deliver.  Computed by Module 4's "
              "_leo_departure_dv_km_s; excludes the asteroid-departure burn."},
    {"segment": "NEA  →  cislunar NRHO (Oberth capture)", "dv_m_per_s": 944, "duration_yr": 1.6,
     "notes": "Capture at a low perigee into an ellipse reaching lunar distance "
              "(494 m/s at v_inf=3 km/s, taking the Oberth benefit of burning "
              "deep in the well), then NRHO insertion at apogee (450 m/s). "
              "3.8x cheaper than propulsive LEO capture, and the destination "
              "is worth MORE per kg — the two effects compound.  Computed by "
              "Module 4's _cislunar_capture_dv_km_s; excludes the "
              "asteroid-departure burn.  The advantage widens as arrival "
              "energy falls: 5.6x at v_inf=1 km/s, 2.7x at 5 km/s."},
    {"segment": "NEA  →  LEO delivery (aerobraked)", "dv_m_per_s": 100, "duration_yr": 2.0,
     "notes": "Aerocapture into a high ellipse, then multi-pass aerobraking to "
              "circularise; drag does the work, so the propulsive cost is only "
              "the periapsis-raise burn out of the atmosphere.  Mars Odyssey / "
              "MRO flew this for real, saving ~1.2 km/s over ~6 months of "
              "passes (JPL).  Buys Δv with TPS mass and MONTHS of time — the "
              "duration figure carries that."},
]

print(f"✅  Mission Δv reference loaded — {len(DELTA_V_REFERENCE)} trajectory segments")


# ─────────────────────────────────────────────────────────────────────────────
# OPERATIONAL COSTS REFERENCE TABLE
# ─────────────────────────────────────────────────────────────────────────────
# Fixed and recurring overhead.  Each row's `notes` field carries an
# inline citation; representative anchors include NASA OIG audit IG-24-015
# (SLS), the OSIRIS-REx mission cost breakdown (Planetary Society / NASA),
# NASA DSN Mission Operations & Communications Services catalog 820-100-H,
# Gallagher / Plane Talking 2024 space-insurance market update, the
# Damodaran NYU Stern industry cost-of-capital tables, and the Mars 2020 /
# Perseverance autonomy program for the autonomous-control NRE anchor.
#
# Mission profile: every line item here assumes an UNCREWED autonomous
# mining spacecraft (v1.2.4+).  No crew costs anywhere in the table.

_REF_YEAR_OPS = 2026

OPERATIONAL_COSTS_REFERENCE: List[dict] = [
    {
        "category":         "Spacecraft development (NRE)",
        "unit":             "USD per program",
        "value":            588_500_000,        # OSIRIS-REx actual
        "range_low":        100_000_000,
        "range_high":     2_000_000_000,
        "notes": "Anchor: OSIRIS-REx spacecraft development = $588.5M actual "
                 "(Planetary Society / NASA budget breakdown).  Discovery-class "
                 "deep-space platform.  Range covers SmallSat ($100M) → flagship ($2B+).",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Mining payload recurring cost",
        "unit":             "USD per kg of mining hardware",
        "value":            300_000,
        "range_low":        100_000,
        "range_high":     1_000_000,
        "notes": "Burdened recurring hardware cost for deep-space-rated mining "
                 "equipment.  Anchor: Aerospace Corp Small Mission Cost Model "
                 "and NASA NICM bracket recurring deep-space hardware at "
                 "$100k-$1M/kg.  Asteroid-mining rigs trend mid-range due to "
                 "regolith-contact mechanisms.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Return capsule recurring cost",
        "unit":             "USD per kg of return-capsule dry mass",
        "value":            150_000,
        "range_low":         50_000,
        "range_high":       400_000,
        "notes": "v1.3.0.  Was previously billed at the mining-payload rate "
                 "($300k/kg), which over-prices it: a sample-return capsule is "
                 "structure + TPS frame + parachute + beacon, with no "
                 "regolith-contact mechanisms, no manipulator, no power or "
                 "propulsion system, and no science payload.  Stardust and the "
                 "OSIRIS-REx SRC are the heritage.  Half the mining-rig rate; "
                 "range spans a bare capsule to one with active thermal and "
                 "guided entry.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Berthing adapter recurring cost",
        "unit":             "USD per kg of delivery-vehicle dry mass",
        "value":             60_000,
        "range_low":         30_000,
        "range_high":       150_000,
        "notes": "v1.4.0.  In-space delivery (LEO / cislunar depot) replaces the "
                 "re-entry capsule with a passive berthing adapter + cargo "
                 "carrier: structure, latches, grapple fixture, RF beacon.  No "
                 "TPS, no parachute, no guided-entry GNC, no flotation or "
                 "beacon-for-recovery.  Priced well under the $150k/kg re-entry "
                 "capsule rate and near the low end of the NICM/SSCM recurring "
                 "bracket, since it is the simplest deep-space-rated structure "
                 "in the catalog.  Heritage: Cygnus PCM, Dragon trunk, the "
                 "passive half of the NASA Docking System.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Surface lander recurring cost",
        "unit":             "USD per kg of lander dry mass",
        "value":            200_000,
        "range_low":        100_000,
        "range_high":       500_000,
        "notes": "v1.5.0.  Delivering to a lunar or Mars SURFACE base needs a "
                 "lander, not a berthing adapter: throttleable descent "
                 "engines, landing legs, terminal guidance and hazard "
                 "avoidance, plus the GNC to fly it.  More capable than the "
                 "$150k/kg re-entry capsule (which is passive after entry) "
                 "and less than the $300k/kg regolith-contact mining rig.  "
                 "Heritage: Apollo LM descent stage, and the CLPS landers "
                 "(Intuitive Machines Nova-C, Astrobotic Peregrine, Blue "
                 "Moon MK1).  A Mars lander carries the TPS row on top, "
                 "because it has to survive entry as well as land.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Depot berthing & handover operations",
        "unit":             "USD per delivery",
        "value":            2_000_000,
        "range_low":          500_000,
        "range_high":       8_000_000,
        "notes": "v1.4.0.  In-space counterpart to 'Sample recovery operations'. "
                 "Rendezvous-and-proximity-operations support, depot crew or "
                 "robotic-arm time, cargo survey and handover.  Far cheaper than "
                 "an Earth recovery campaign: no search aircraft, no ships, no "
                 "range clearance, no clean-room convoy.  Scaled from ISS "
                 "visiting-vehicle berthing ops rather than the $15M OSIRIS-REx "
                 "UTTR recovery.  ESTIMATE — no commercial depot exists yet.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Heat shield / TPS for Earth return",
        "unit":             "USD per kg of TPS mass",
        "value":             50_000,
        "range_low":         20_000,
        "range_high":       150_000,
        "notes": "Flight-rated PICA-X / AVCOAT-class TPS material + manufacturing. "
                 "Required for the aerocapture-return Δv segment.  NOTE: NASA / "
                 "SpaceX have not published a per-kg PICA-X cost; figure is an "
                 "engineering estimate.  Stardust / OSIRIS-REx capsule heritage "
                 "(see NTRS 20140005558 for material data).",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Mission operations",
        "unit":             "USD per mission-year",
        "value":             31_400_000,        # OSIRIS-REx $283M / 9 yr
        "range_low":         15_000_000,
        "range_high":       100_000_000,
        "notes": "Anchor: OSIRIS-REx prime ops = $283M over 9 yr = $31.4M/yr "
                 "(NASA / Planetary Society).  Ground team + mission control + planning. "
                 "Range covers SmallSat ($15M) → flagship ($100M+).",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Deep Space Network time",
        "unit":             "USD per DSN hour (34-m dish)",
        "value":            1_530,              # FY09 $1057 × 1.45 CPI
        "range_low":        1_000,
        "range_high":       4_000,
        "notes": "DSN aperture fee for 34-m antenna.  NASA Mission Operations "
                 "and Communications Services (MOCS) cited $1057/hr in FY09; "
                 "CPI-adjusted to 2026 ≈ $1530/hr.  70-m apertures ~$4k/hr. "
                 "Authoritative current rates: dse.jpl.nasa.gov/ext/ calculator.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "FAA Part 450 licensing compliance",
        "unit":             "USD per program",
        "value":            2_500_000,
        "range_low":        1_000_000,
        "range_high":       5_000_000,
        "notes": "FAA does not charge an application fee; cost is internal "
                 "engineering + legal + safety-case work for 14 CFR Part 450 "
                 "compliance (FAA.gov / Congress.gov R48582).  First-of-kind "
                 "re-entry missions (asteroid sample return) trend upper-end. "
                 "v1.4.0: this row is the LAUNCH + RE-ENTRY figure; a mission "
                 "delivering to an in-space depot never re-enters and carries "
                 "the launch-only row below instead.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "FAA Part 450 licensing (launch only)",
        "unit":             "USD per program",
        "value":            1_200_000,
        "range_low":          600_000,
        "range_high":       2_500_000,
        "notes": "v1.4.0.  Part 450 covers launch AND re-entry as separately "
                 "licensed activities (14 CFR 450.1).  A mission that delivers "
                 "to LEO or a cislunar depot performs no re-entry, so it drops "
                 "the re-entry safety case, the debris-casualty-expectation "
                 "analysis for the landing footprint, and the range/airspace "
                 "coordination that dominate the first-of-kind sample-return "
                 "figure.  Roughly half the combined licence, which is where "
                 "routine launch-only Part 450 compliance sits.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Third-party liability insurance",
        "unit":             "USD per launch",
        "value":            1_500_000,
        "range_low":          500_000,
        "range_high":       3_000_000,
        "notes": "FAA-mandated Maximum Probable Loss coverage — statute caps at "
                 "$500M third-party / $100M US-government per 14 CFR Part 450. "
                 "Premium covers ground/air harm; distinct from payload insurance.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Launch insurance",
        "unit":             "percent of launch+payload value",
        "value":           10.0,                # 2024 market post-Intelsat 33e loss
        "range_low":        5.0,
        "range_high":      15.0,
        "notes": "Market rate per Plane Talking (Gallagher) Q1 2024 — premiums "
                 "rose from ~6% (early 2023) to ~10% post-Intelsat 33e loss. "
                 "First-of-kind vehicles at upper end.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Communications relay & data downlink",
        "unit":             "USD per Mbit returned",
        "value":            50,
        "range_low":        10,
        "range_high":       200,
        "notes": "Ka-band; relevant only for high-rate science / 3-D maps.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Power system (solar + battery)",
        "unit":             "USD per Watt-end-of-life",
        "value":            800,
        "range_low":        500,
        "range_high":     1_500,
        "notes": "Burdened recurring cost for a deep-space PV+battery train.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Power system specific mass",
        "unit":             "Watts per kg of power system, at 1 AU",
        "value":            60,
        "range_low":        30,
        "range_high":      150,
        "notes": "v1.4.0.  SYSTEM-level, not array-level: photovoltaic wing + "
                 "PMAD + battery + deployment structure.  ROSA / iROSA "
                 "roll-out arrays demonstrate ~150 W/kg at the wing (NASA "
                 "ROSA flight demo, ISS iROSA 2021+), but batteries, "
                 "regulation and structure roughly halve that at the system "
                 "level, and a mining rig needs power through eclipse and "
                 "through the night side of a rotating body.  60 W/kg is "
                 "mid-range for a deep-space PV train.  Scales as 1/r^2 with "
                 "heliocentric distance — Module 4 applies that per asteroid, "
                 "which is why main-belt targets are punished so hard once "
                 "processing power is modelled.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "RTG (radioisotope power)",
        "unit":             "USD per Watt-electric",
        "value":            500_000,
        "range_low":        200_000,
        "range_high":     1_000_000,
        "notes": "Pu-238 supply-constrained (NASA / DOE target 1.5 kg/yr production "
                 "by 2026).  Historical Russian Pu-238 ~$2.5M/kg; with 6-8% RTG "
                 "conversion efficiency a 50-W RTG costs ~$1M just in fuel "
                 "(Space.com / NASA NIAC).  Only used past ~3 AU when PV starves.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Drilling / excavation energy",
        "unit":             "Watt-hours per kg of regolith extracted",
        "value":            200,
        "range_low":         50,
        "range_high":       500,
        "notes": "Range derived from Zacny et al. (NIAC studies on asteroid / "
                 "lunar regolith excavation) — loose regolith ≲50 Wh/kg, "
                 "consolidated rock ≳500 Wh/kg.  Pairs with the power-system "
                 "row to size mining rig (kg-extracted per installed-kW-hr).",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Beneficiation / on-site processing energy",
        "unit":             "Watt-hours per kg of refined product",
        "value":            500,
        "range_low":        100,
        "range_high":     2_000,
        "notes": "Magnetic / electrostatic / thermal concentration to ~50% purity. "
                 "Lunar / asteroid ISRU literature (NASA Money-Mass-ematics 2023). "
                 "Trades in-flight energy for a much smaller return-mass × prop bill.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Autonomous mining control & AI (NRE)",
        "unit":             "USD per program",
        "value":            200_000_000,
        "range_low":         50_000_000,
        "range_high":       500_000_000,
        "notes": "Pipeline assumes fully UNCREWED autonomous mining — no life "
                 "support, no crew habitat.  This line item captures the "
                 "one-time NRE for autonomous regolith-assessment vision, "
                 "sample-collection control logic, station-keeping autonomy, "
                 "and remote-fault-recovery software.  Anchor: Mars 2020 / "
                 "Perseverance autonomy stack ≈ $150M of $2.4B program; "
                 "asteroid mining trends upper end of range due to longer "
                 "Earth-spacecraft light-time (decisions must be local) and "
                 "novel regolith-contact mechanics.  Treated as in addition "
                 "to the bus 'Spacecraft development (NRE)' line above.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Sample recovery operations",
        "unit":             "USD per recovery",
        "value":             15_000_000,
        "range_low":          5_000_000,
        "range_high":        30_000_000,
        "notes": "Search-and-recovery teams, helicopters / ships, clean-room transport, "
                 "range coverage.  Modelled on OSIRIS-REx UTTR landing (Sept 2023). "
                 "NOTE: NASA has not published a standalone recovery-ops figure; "
                 "$15M is an order-of-magnitude estimate from the broader $283M / 9 yr "
                 "operations envelope — refine with project-specific data when available.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Cost of capital (WACC)",
        "unit":             "annualised fraction",
        "value":            0.10,
        "range_low":        0.075,             # Boeing 7.5% floor
        "range_high":       0.15,
        "notes": "Boeing 7.5% / Howmet 8.3% WACC (ValueInvesting.io 2026) as the "
                 "industrial floor; asteroid-mining ventures carry a startup risk "
                 "premium to ~10-15% (Damodaran NYU Stern industry tables).  "
                 "A 7-yr mission at 10% WACC ⇒ ~1.95× capital multiplier on Day-1 spend. "
                 "Module 4 should compound this across mission_duration_yr.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Contingency reserve",
        "unit":             "percent of total mission cost",
        "value":            TRANSPORT_CONFIG.contingency_fraction * 100,
        "range_low":        15.0,
        "range_high":       50.0,
        "notes": "Industry-standard; first-of-kind missions carry the upper end.",
        "reference_year":   _REF_YEAR_OPS,
    },
]

print(f"✅  Operational costs reference loaded — "
      f"{len(OPERATIONAL_COSTS_REFERENCE)} categories")


# ─────────────────────────────────────────────────────────────────────────────
# YFINANCE FETCHER  (live commodity proxies for liquid propellants)
# ─────────────────────────────────────────────────────────────────────────────
# yfinance gives us:
#   • HO=F  NY heating oil  → No. 2 distillate, the standard RP-1 proxy
#                              (kerosene chemistry is essentially No. 1 / No. 2)
#                              Quote: USD per US gallon.
#   • NG=F  Henry-Hub natural gas → methane (LCH4) proxy
#                              Quote: USD per MMBtu.
#   • CL=F  WTI crude oil   → upstream cross-check on HO=F
#                              Quote: USD per barrel.
# Each updates the matching propellant's `live_cost_usd_per_kg` column.

_YFINANCE_TICKERS = {
    # ticker  : (commodity_name_for_print, quote_unit, fluid_density_key)
    "HO=F":   ("Heating oil (kerosene/RP-1 proxy)", "gallon",  "heating_oil"),
    "NG=F":   ("Natural gas (CH4/LCH4 proxy)",     "MMBtu",   "natural_gas"),
    "CL=F":   ("WTI crude (cross-check)",          "barrel",  "crude_oil"),
}

def fetch_yfinance_fuel_prices(
    config: TransportConfig,
) -> pd.DataFrame:
    """
    Live commodity quotes for the liquid-propellant proxies.

    Returns a small DataFrame with one row per propellant that has a
    `yfinance_proxy` key in PROPELLANTS_REFERENCE.  Columns:
        name, live_cost_usd_per_kg, live_cost_usd_per_L,
        live_price_date, live_price_source.
    """
    print("\n⛽  yfinance  (Yahoo Finance) — live fuel commodity prices …")

    try:
        import yfinance as yf
    except ImportError:
        print("     ❌  yfinance not importable — skipped")
        return pd.DataFrame()

    # Step 1 — pull commodity quotes
    commodity_usd_per_kg: Dict[str, dict] = {}
    for ticker, (label, unit, fluid_key) in _YFINANCE_TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d", auto_adjust=False)
            closes = hist["Close"].dropna() if "Close" in hist else pd.Series(dtype=float)
            if closes.empty:
                print(f"     ⚠️  {label} ({ticker}) — no close data")
                continue

            last_close = float(closes.iloc[-1])
            last_date  = closes.index[-1].strftime("%Y-%m-%d")

            if unit == "gallon":
                usd_per_kg = _per_gal_to_per_kg(last_close, fluid_key)
            elif unit == "MMBtu":
                usd_per_kg = _per_mmbtu_to_per_kg_ng(last_close)
            elif unit == "barrel":
                usd_per_kg = _per_bbl_to_per_kg(last_close, fluid_key)
            else:
                print(f"     ⚠️  {label} — unrecognised unit {unit!r}")
                continue

            commodity_usd_per_kg[fluid_key] = {
                "usd_per_kg":   usd_per_kg,
                "ticker":       ticker,
                "raw_quote":    last_close,
                "raw_unit":     unit,
                "quote_date":   last_date,
            }
            print(f"     ✅  {label:38s} ({ticker}) = "
                  f"{last_close:>8,.2f} USD/{unit:6s} "
                  f"→ {usd_per_kg:>7.3f} USD/kg  [{last_date}]")

        except Exception as exc:
            print(f"     ❌  {label} ({ticker}) — {type(exc).__name__}: {exc}")

    if not commodity_usd_per_kg:
        print("     ⚠️  yfinance returned no commodity quotes")
        return pd.DataFrame()

    # Step 2 — map onto propellants via `yfinance_proxy`.  Bipropellants
    # have a fuel proxy only; the LOX/N2O4 oxidiser cost stays at reference.
    # We blend the live fuel cost back in using the stored mass fractions.
    rows = []
    for prop in PROPELLANTS_REFERENCE:
        proxy_key = prop.get("yfinance_proxy")
        if not proxy_key or proxy_key not in commodity_usd_per_kg:
            continue
        proxy = commodity_usd_per_kg[proxy_key]

        if prop["name"].startswith("kerolox"):
            # RP-1 fraction was 1/(1+2.30) of the combined mass
            fuel_frac = 1.0 / (1.0 + 2.30)
            ox_cost   = _COMPONENTS["LOX"]["cost_usd_per_kg"]
            live_cost = fuel_frac * proxy["usd_per_kg"] + (1 - fuel_frac) * ox_cost
        elif prop["name"].startswith("methalox"):
            fuel_frac = 1.0 / (1.0 + 3.60)
            ox_cost   = _COMPONENTS["LOX"]["cost_usd_per_kg"]
            live_cost = fuel_frac * proxy["usd_per_kg"] + (1 - fuel_frac) * ox_cost
        else:
            live_cost = proxy["usd_per_kg"]

        rows.append({
            "name":                  prop["name"],
            "live_cost_usd_per_kg":  live_cost,
            "live_cost_usd_per_L":   live_cost * prop["density_kg_per_L"],
            "live_price_date":       proxy["quote_date"],
            "live_price_source":     f"yfinance:{proxy['ticker']}",
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# REFERENCE-TABLE LOADERS  (always-on)
# ─────────────────────────────────────────────────────────────────────────────
def load_launch_vehicles() -> pd.DataFrame:
    print("\n🚀  Loading launch-vehicles reference …")
    df = pd.DataFrame(LAUNCH_VEHICLES_REFERENCE)
    print(f"     ✅  {len(df)} vehicles")
    return df


def load_propellants() -> pd.DataFrame:
    print("\n🔥  Loading propellants reference …")
    df = pd.DataFrame(PROPELLANTS_REFERENCE)
    print(f"     ✅  {len(df)} propellant systems")
    return df


def load_delta_v() -> pd.DataFrame:
    print("\n📐  Loading mission Δv reference …")
    df = pd.DataFrame(DELTA_V_REFERENCE)
    print(f"     ✅  {len(df)} trajectory segments")
    return df


def load_operational_costs() -> pd.DataFrame:
    print("\n🏢  Loading operational-costs reference …")
    df = pd.DataFrame(OPERATIONAL_COSTS_REFERENCE)
    print(f"     ✅  {len(df)} cost categories")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# ROCKET-EQUATION HELPERS
# ─────────────────────────────────────────────────────────────────────────────
# The Tsiolkovsky rocket equation gives the mass of propellant required to
# impart a given Δv to a payload:
#
#       Δv = Isp · g₀ · ln(m₀ / m_f)
#   ⇒   m_prop  =  m_payload · (exp(Δv / (Isp · g₀)) − 1)
#
# These helpers are what Module 4 will use to convert orbital geometry into
# USD.  Vectorised — accept arrays or scalars indifferently.

def propellant_mass_for_dv(
    payload_kg, delta_v_m_per_s, isp_s, g0=G0_M_S2,
):
    """
    Mass of propellant required to push `payload_kg` through `delta_v_m_per_s`
    using a stage with vacuum specific impulse `isp_s`.

    Returns the propellant mass (kg).  Vectorised over arrays.
    """
    mass_ratio = np.exp(np.asarray(delta_v_m_per_s) / (np.asarray(isp_s) * g0))
    return np.asarray(payload_kg) * (mass_ratio - 1.0)


def cost_per_dv_usd_per_kg(
    propellant_cost_usd_per_kg, isp_s, delta_v_m_per_s, g0=G0_M_S2,
):
    """
    The headline normalised metric.  Returns the USD of propellant required
    to move 1 kg of payload through `delta_v_m_per_s` using this propellant.

    This is the rocket equivalent of "fuel cost per km" for a car.
    """
    m_prop_per_kg_payload = propellant_mass_for_dv(
        1.0, delta_v_m_per_s, isp_s, g0,
    )
    return float(m_prop_per_kg_payload) * float(propellant_cost_usd_per_kg)


def build_transportation_summary(
    launch_df:      pd.DataFrame,
    propellant_df:  pd.DataFrame,
    delta_v_df:     pd.DataFrame,
    config:         TransportConfig = TRANSPORT_CONFIG,
) -> pd.DataFrame:
    """
    Cross-join (vehicle × in-space-segment × propellant) into a long-form
    table of normalised costs.  This is what Module 4 reads to pick the
    cheapest viable combination for any asteroid.

    Output rows:  (vehicle, segment, propellant) tuples with the columns
        launch_usd_per_kg
        in_space_prop_usd_per_kg_payload     ← rocket-equation cost
        total_usd_per_kg_payload_to_segment_end
        propellant_mass_per_kg_payload
        segment_duration_yr
    """
    print("\n🧮  Building (vehicle × segment × propellant) cost summary …")

    # Only price IN-SPACE Δv with the propellant table — surface ascent is
    # already baked into the launch vehicle's $/kg-to-LEO.
    in_space = delta_v_df[
        ~delta_v_df["segment"].str.contains("surface", case=False)
    ].copy()

    rows = []
    for _, lv in launch_df.iterrows():
        # Use the LEO price as the baseline cost to "lift" the payload to
        # the start of every in-space segment.  Module 4 can switch this
        # to escape-class numbers for deep-space-direct injections.
        leo_cost_per_kg = lv["usd_per_kg_to_leo"]

        for _, seg in in_space.iterrows():
            for _, p in propellant_df.iterrows():
                cost_per_kg = float(p["cost_usd_per_kg"])
                isp         = float(p["isp_vac_s"])
                dv          = float(seg["dv_m_per_s"])

                prop_per_payload = float(propellant_mass_for_dv(1.0, dv, isp))
                in_space_cost    = prop_per_payload * cost_per_kg

                rows.append({
                    "vehicle":                                lv["name"],
                    "vehicle_status":                         lv["status"],
                    "segment":                                seg["segment"],
                    "segment_dv_m_per_s":                     dv,
                    "segment_duration_yr":                    seg["duration_yr"],
                    "propellant":                             p["name"],
                    "propellant_isp_s":                       isp,
                    "propellant_cost_usd_per_kg":             cost_per_kg,
                    "launch_usd_per_kg_to_leo":               leo_cost_per_kg,
                    "propellant_mass_per_kg_payload":         prop_per_payload,
                    "in_space_prop_usd_per_kg_payload":       in_space_cost,
                    "total_usd_per_kg_payload_to_segment_end":
                        leo_cost_per_kg + in_space_cost,
                })

    summary = pd.DataFrame(rows)
    print(f"     ✅  {len(summary):,} (vehicle × segment × propellant) rows")
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# MERGE LIVE INTO REFERENCE
# ─────────────────────────────────────────────────────────────────────────────
def merge_propellant_prices(
    reference: pd.DataFrame, live: pd.DataFrame,
) -> pd.DataFrame:
    """
    Fold live yfinance prices into the propellant reference table.  Output
    `cost_usd_per_kg` and `cost_usd_per_L` resolve to live where available,
    reference where not — same pattern as Module 2.
    """
    print("\n🔗  Merging live + reference propellant prices …")

    out = reference.copy()
    out["live_cost_usd_per_kg"] = pd.NA
    out["live_cost_usd_per_L"]  = pd.NA
    out["live_price_date"]      = pd.NA
    out["live_price_source"]    = pd.NA

    if not live.empty:
        for _, row in live.iterrows():
            mask = out["name"] == row["name"]
            if not mask.any():
                continue
            idx = out.index[mask]
            out.loc[idx, "live_cost_usd_per_kg"] = row["live_cost_usd_per_kg"]
            out.loc[idx, "live_cost_usd_per_L"]  = row["live_cost_usd_per_L"]
            out.loc[idx, "live_price_date"]     = row["live_price_date"]
            out.loc[idx, "live_price_source"]   = row["live_price_source"]

    live_kg = pd.to_numeric(out["live_cost_usd_per_kg"], errors="coerce")
    ref_kg  = pd.to_numeric(out["ref_cost_usd_per_kg"],  errors="coerce")
    out["cost_usd_per_kg"] = live_kg.fillna(ref_kg)

    live_L = pd.to_numeric(out["live_cost_usd_per_L"], errors="coerce")
    ref_L  = pd.to_numeric(out["ref_cost_usd_per_L"],  errors="coerce")
    out["cost_usd_per_L"]  = live_L.fillna(ref_L)

    out["price_basis"] = np.where(
        live_kg.notna(), "live",
        np.where(ref_kg.notna(), "reference", "unpriced"),
    )

    n_live = int((out["price_basis"] == "live").sum())
    n_ref  = int((out["price_basis"] == "reference").sum())
    print(f"     Live  : {n_live} | Reference : {n_ref}")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
def validate_transport(
    launch_df:      pd.DataFrame,
    propellant_df:  pd.DataFrame,
    delta_v_df:     pd.DataFrame,
    ops_df:         pd.DataFrame,
) -> None:
    """Print sanity warnings.  Never raises."""
    print("\n🔎  Validating catalog …")

    # ── Launch $/kg sanity band ──────────────────────────────────────────────
    # 100 USD/kg (Starship optimistic floor) … 100 000 USD/kg (SLS-equivalent).
    bad_launch = launch_df[
        (launch_df["usd_per_kg_to_leo"] < 100)
        | (launch_df["usd_per_kg_to_leo"] > 100_000)
    ]
    if not bad_launch.empty:
        print(f"     ⚠️  {len(bad_launch)} launch rows outside "
              f"$100-$100 000 / kg-to-LEO sanity band:")
        for _, r in bad_launch.iterrows():
            print(f"          {r['name']}: {r['usd_per_kg_to_leo']:,.0f}")

    # ── Propellant Isp sanity band ───────────────────────────────────────────
    # 150 s (cold-gas) … 5 000 s (very high-Isp ion).
    bad_isp = propellant_df[
        (propellant_df["isp_vac_s"] < 150) | (propellant_df["isp_vac_s"] > 5_000)
    ]
    if not bad_isp.empty:
        print(f"     ⚠️  {len(bad_isp)} propellant rows with implausible Isp:")
        for _, r in bad_isp.iterrows():
            print(f"          {r['name']}: {r['isp_vac_s']} s")

    # ── Propellant $/kg sanity band ──────────────────────────────────────────
    bad_prop_cost = propellant_df[
        (propellant_df["cost_usd_per_kg"] < 0.1)
        | (propellant_df["cost_usd_per_kg"] > 10_000)
    ]
    if not bad_prop_cost.empty:
        print(f"     ⚠️  {len(bad_prop_cost)} propellant rows outside "
              f"$0.10-$10k / kg sanity band:")
        for _, r in bad_prop_cost.iterrows():
            print(f"          {r['name']}: {r['cost_usd_per_kg']:,.2f}")

    # ── Δv sanity band ───────────────────────────────────────────────────────
    bad_dv = delta_v_df[
        (delta_v_df["dv_m_per_s"] < 50) | (delta_v_df["dv_m_per_s"] > 20_000)
    ]
    if not bad_dv.empty:
        print(f"     ⚠️  {len(bad_dv)} Δv rows outside 50-20 000 m/s sanity band:")
        for _, r in bad_dv.iterrows():
            print(f"          {r['segment']}: {r['dv_m_per_s']} m/s")

    print(f"     ✅  Unit invariants: launch USD/kg | propellant USD/kg + USD/L | "
          f"Δv m/s | ops USD per unit")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def build_transportation_catalog(
    config: TransportConfig = TRANSPORT_CONFIG,
) -> Dict[str, pd.DataFrame]:
    """
    Run the full transportation-cost pipeline.  Returns a dict of frames:
        {
          "launch_vehicles":   DataFrame,
          "propellants":       DataFrame,
          "delta_v_segments":  DataFrame,
          "operational_costs": DataFrame,
          "summary":           DataFrame,  # vehicle × segment × propellant
        }
    """
    t0 = datetime.now()

    print("=" * 75)
    print("  🛰️   TRANSPORTATION COST PIPELINE — MODULE 3")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  v{config.pipeline_version}")
    print("=" * 75)

    # ── Step 1 — Reference tables (always-on) ────────────────────────────────
    launch_df = load_launch_vehicles()
    prop_ref  = load_propellants()
    dv_df     = load_delta_v()
    ops_df    = load_operational_costs()

    # ── Step 2 — Live commodity proxies ──────────────────────────────────────
    live_prop = (
        fetch_yfinance_fuel_prices(config) if config.use_yfinance else pd.DataFrame()
    )

    # ── Step 3 — Merge live into propellant reference ────────────────────────
    prop_df = merge_propellant_prices(prop_ref, live_prop)

    # ── Step 4 — Validation ──────────────────────────────────────────────────
    validate_transport(launch_df, prop_df, dv_df, ops_df)

    # ── Step 5 — Composite summary ───────────────────────────────────────────
    summary_df = build_transportation_summary(launch_df, prop_df, dv_df, config)

    # ── Step 6 — Metadata + export ───────────────────────────────────────────
    out_dir = os.path.join(config.output_dir, config.subdir)
    stamp   = t0.strftime("%Y-%m-%d")
    for df in (launch_df, prop_df, dv_df, ops_df, summary_df):
        df["catalog_date"]     = stamp
        df["pipeline_version"] = config.pipeline_version

    files = {
        "launch_vehicles.csv":          launch_df,
        "propellants.csv":              prop_df,
        "delta_v_segments.csv":         dv_df,
        "operational_costs.csv":        ops_df,
        "transportation_summary.csv":   summary_df,
    }
    for fname, df in files.items():
        path = os.path.join(out_dir, fname)
        df.to_csv(path, index=False)
        print(f"     💾  {fname:32s} → {path}  ({len(df):,} rows)")

    elapsed = (datetime.now() - t0).total_seconds()
    print("\n" + "=" * 75)
    print("  ✅  TRANSPORTATION CATALOG COMPLETE")
    print(f"      Tables   : {len(files)}")
    print(f"      Elapsed  : {elapsed:.1f}s")
    print("=" * 75)

    return {
        "launch_vehicles":   launch_df,
        "propellants":       prop_df,
        "delta_v_segments":  dv_df,
        "operational_costs": ops_df,
        "summary":           summary_df,
    }


# ─────────────────────────────────────────────────────────────────────────────
# QUERY UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def cheapest_launch_to(
    catalog: Dict[str, pd.DataFrame],
    destination: str = "leo",       # "leo" | "gto" | "escape"
    min_payload_kg: float = 0.0,
    operational_only: bool = True,
) -> pd.DataFrame:
    """Rank launch vehicles by $/kg to a given destination."""
    col = {"leo":    "usd_per_kg_to_leo",
           "gto":    "usd_per_kg_to_gto",
           "escape": "usd_per_kg_to_escape"}[destination.lower()]
    pay = {"leo":    "payload_leo_kg",
           "gto":    "payload_gto_kg",
           "escape": "payload_escape_kg"}[destination.lower()]

    df = catalog["launch_vehicles"].copy()
    if operational_only:
        df = df[df["status"] == "operational"]
    df = df[df[pay] >= min_payload_kg]
    return df.sort_values(col).reset_index(drop=True)


def cheapest_propellant_for(
    catalog: Dict[str, pd.DataFrame],
    delta_v_m_per_s: float,
) -> pd.DataFrame:
    """Rank propellants by USD-per-kg-payload to apply this Δv (rocket eq.)."""
    df = catalog["propellants"].copy()
    df["usd_per_kg_payload_for_dv"] = df.apply(
        lambda r: cost_per_dv_usd_per_kg(
            r["cost_usd_per_kg"], r["isp_vac_s"], delta_v_m_per_s,
        ),
        axis=1,
    )
    return df[["name", "isp_vac_s", "cost_usd_per_kg",
               "usd_per_kg_payload_for_dv"]].sort_values(
        "usd_per_kg_payload_for_dv",
    ).reset_index(drop=True)


def mission_cost_breakdown(
    catalog: Dict[str, pd.DataFrame],
    payload_kg:         float,
    delta_v_outbound:   float,
    delta_v_return:     float,
    launch_vehicle:     str,
    propellant:         str,
    mission_duration_yr: float,
    hardware_kg:        float = 0.0,
    config:             TransportConfig = TRANSPORT_CONFIG,
) -> dict:
    """
    Full end-to-end USD breakdown for one mission scenario.

    Returns dict with: launch_usd, outbound_prop_usd, return_prop_usd,
    hardware_usd, ops_usd, contingency_usd, total_usd, usd_per_kg_returned.
    """
    lv  = catalog["launch_vehicles"].set_index("name").loc[launch_vehicle]
    p   = catalog["propellants"].set_index("name").loc[propellant]
    ops = catalog["operational_costs"].set_index("category")

    isp = p["isp_vac_s"]

    # ── Return-leg propellant — solved first because it sits on the outbound
    # leg as dead mass (unless ISRU manufactures it at the asteroid).
    #
    #   m_prop_return = m_payload × (exp(Δv_ret / (Isp·g₀)) − 1)
    return_prop_kg = float(propellant_mass_for_dv(
        payload_kg, delta_v_return, isp,
    ))
    return_prop_cost_kg = (
        config.isru_processing_usd_per_kg
        if config.isru_return_propellant
        else p["cost_usd_per_kg"]
    )
    return_prop_usd = return_prop_kg * return_prop_cost_kg

    # ── Outbound-leg propellant — must push (payload + hardware + return_prop)
    # through Δv_outbound.  This is the bug-fix vs naive `propellant_mass_for_dv
    # (payload + hardware)`: omitting return_prop_kg understates outbound mass
    # and gives optimistic launch + propellant numbers.
    #
    # If ISRU is enabled, return prop is made at the asteroid, so it does NOT
    # sit on the outbound leg; outbound_dry collapses to (payload + hardware).
    outbound_dry = (
        payload_kg + hardware_kg
        if config.isru_return_propellant
        else payload_kg + hardware_kg + return_prop_kg
    )
    outbound_prop_kg = float(propellant_mass_for_dv(
        outbound_dry, delta_v_outbound, isp,
    ))

    # Launch lifts (outbound_dry + outbound_prop_kg) to LEO
    launch_mass    = outbound_dry + outbound_prop_kg
    launch_usd     = launch_mass * lv["usd_per_kg_to_leo"]
    outbound_prop_usd = outbound_prop_kg * p["cost_usd_per_kg"]

    # Hardware recurring + dev amortised
    hw_recurring_per_kg = ops.loc["Mining payload recurring cost", "value"]
    hardware_usd = hardware_kg * hw_recurring_per_kg

    # Mission ops — per-year × duration
    ops_per_year = ops.loc["Mission operations", "value"]
    ops_usd = ops_per_year * mission_duration_yr

    subtotal = launch_usd + outbound_prop_usd + return_prop_usd + hardware_usd + ops_usd
    contingency_usd = subtotal * config.contingency_fraction
    total_usd       = subtotal + contingency_usd

    return {
        "launch_usd":            launch_usd,
        "outbound_prop_usd":     outbound_prop_usd,
        "return_prop_usd":       return_prop_usd,
        "hardware_usd":          hardware_usd,
        "ops_usd":               ops_usd,
        "contingency_usd":       contingency_usd,
        "total_usd":             total_usd,
        "usd_per_kg_returned":   total_usd / payload_kg if payload_kg > 0 else np.nan,
        "outbound_prop_kg":      outbound_prop_kg,
        "return_prop_kg":        return_prop_kg,
        "launched_mass_kg":      launch_mass,
    }


print("\n✅  Helper utilities available:")
print("    cheapest_launch_to(catalog, 'leo', min_payload_kg=5000)")
print("    cheapest_propellant_for(catalog, 6500)   # Δv in m/s")
print("    mission_cost_breakdown(catalog, payload_kg=1000, "
      "delta_v_outbound=6500, delta_v_return=5500, "
      "launch_vehicle='Falcon Heavy (reusable side cores)', "
      "propellant='methalox  (LCH4 / LOX)', mission_duration_yr=3)")




# ═════════════════════════════════════════════════════════════════════════
# MODULE 4 — PROFITABILITY CALCULATOR
# ═════════════════════════════════════════════════════════════════════════




# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import ast
import json
import math
import os
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

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
# ║   ★  USER SETTINGS — EDIT THESE TO TUNE THE PIPELINE  ★                  ║
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
    # `m_hardware`     — mining rig + comms + structure that stays at asteroid
    # `m_dry_return`   — return capsule dry mass (TPS frame + chute + structure,
    #                    NOT the ablative TPS itself which scales with payload)
    mining_hardware_kg:        float = 2_000
    return_vehicle_dry_kg:     float = 500

    # ─── MINING MODEL ────────────────────────────────────────────────────────
    # Single mission can never strip-mine the whole asteroid.  Cap at this
    # fraction of total mass.  5% is conservative for a first mission to a
    # hundreds-of-kilometre body.
    max_mining_fraction:       float = 0.05

    # ─── MINING THROUGHPUT  (v1.4.0) ─────────────────────────────────────────
    # Before v1.4.0 the rig could extract any mass instantly: mission duration
    # came only from Δv plus a flat 0.5 yr of station-keeping, whether the
    # mission returned 33 kg or 50 tonnes.  Nothing anywhere connected how
    # much you mined to how long it took.
    #
    # `mining_rate_kg_per_day_per_kg_rig` scales extraction with the rig you
    # actually brought.  0.10 means a 2,000 kg rig moves 200 kg/day of
    # regolith.  There is no flight heritage for sustained asteroid mining, so
    # this is an engineering assumption, not a measurement — it sits here as a
    # single obvious dial rather than being buried as an implicit infinity.
    # For scale, OSIRIS-REx's TAGSAM collected ~122 g in a touch-and-go; a
    # continuous rig is a different machine entirely.
    mining_rate_kg_per_day_per_kg_rig: float = 0.10
    # Hard ceiling on time spent at the asteroid.  Binds the payload: you can
    # only return what you can dig in this long.  Also keeps ops cost and WACC
    # from compounding over an implausible stay.
    max_mining_duration_yr:            float = 3.0
    # Floor on time at the asteroid regardless of how little is mined —
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
    #   • by CONTENT   — you cannot recover more than what you processed,
    #                    times the recovery efficiency
    #   • by PURITY    — you cannot make a concentrate richer than the best
    #                    single phase actually present in the body
    #
    # Concentration is not free.  It costs energy (see the two Module 3 energy
    # rows), the energy costs a power plant, the power plant costs mass, and
    # the mass comes straight out of the payload budget through the same
    # rocket equation.  Module 4 solves that feedback rather than ignoring it.
    use_beneficiation:         bool  = False
    # Fraction of the valuable phase that actually reports to concentrate.
    # Terrestrial PGM / sulphide flotation circuits run 85-95%; magnetic
    # separation of a metal phase from silicate gangue is mechanically simpler
    # than flotation but has no microgravity flight heritage at all.
    beneficiation_recovery:    float = 0.90
    # Safety cap on feed:concentrate mass ratio.  Terrestrial mills run
    # 100:1 to 1000:1 on PGM ores; 50:1 is deliberately conservative for a
    # first autonomous rig.  The purity bound above usually binds first.
    max_concentration_ratio:   float = 50.0
    # How hard to concentrate is an economic decision, not a setting — see
    # evaluate_combo.  This is how many points the profit sweep samples
    # between "don't concentrate" and "concentrate to pure best phase",
    # plus one refinement pass.  Raising it costs runtime linearly and buys
    # very little; 7 puts the optimum within a few percent.
    concentration_search_steps: int  = 7

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
    # Applied uniformly to every asteroid (v1.3.5 — per-target Asterank Δv
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
    #   "earth_surface" — re-entry capsule, Earth recovery campaign, full
    #                     launch + re-entry Part 450 licence.  Cheapest return
    #                     Δv (direct entry needs no capture burn at all), but
    #                     the cargo is worth terrestrial commodity prices.
    #   "leo"           — berthed at an LEO depot.  No re-entry, so no capsule,
    #                     no recovery campaign, launch-only licence.  The most
    #                     EXPENSIVE return Δv in the model: circularising into
    #                     LEO means killing the whole arrival hyperbola.
    #   "cislunar"      — berthed at an NRHO depot.  Same cost savings as LEO,
    #                     and the cheapest return Δv of the orbital options,
    #                     because capture only has to bind the orbit and the
    #                     burn takes the Oberth benefit at low perigee.
    #   "lunar_surface" — landed at a Moon base.  Cislunar capture plus
    #                     2.6 km/s of NRHO→LLO→surface, all propulsive — the
    #                     Moon has no atmosphere to brake against.  Carries a
    #                     $200k/kg lander instead of a berthing adapter.
    #   "mars_surface"  — landed at a Mars base.  NOT an Earth return: the
    #                     heliocentric transfer runs from the asteroid's orbit
    #                     to Mars' (1.524 AU), so the departure burn, arrival
    #                     v_infinity and capture are all separately computed
    #                     (_asteroid_to_mars_dv_km_s).  Many NEAs have aphelia
    #                     out near Mars and are genuinely closer to it than to
    #                     Earth.  Aerocapture is available and worth several
    #                     km/s.
    #
    # See DELIVERY_ARCHITECTURES for what each one actually changes.
    delivery_destination:      str   = "earth_surface"

    # ─── AEROCAPTURE  (return via heat shield rather than propulsive) ────────
    # When True, return Δv is reduced by `aerocapture_dv_savings_m_s` but a
    # heat-shield mass overhead is added at the rate from Module 3.
    # Only honoured where the architecture actually enters an atmosphere:
    # earth_surface (direct entry) and leo (aerocapture + aerobraking).
    # A cislunar delivery ignores it — see uses_tps().
    use_aerocapture_return:    bool  = True
    aerocapture_dv_savings_m_s: float = 4_000   # matches Module 3 NEA-return-aerocap
    heat_shield_frac_of_payload: float = 0.15   # TPS mass = 15% of returned payload

    # ─── ISRU  (propellant manufactured at asteroid — Module 3 toggle) ───────
    # When True, return propellant is "free" at-launch (not hauled outbound)
    # but adds an on-asteroid processing cost from Module 3.
    use_isru_return_propellant:    bool  = False
    isru_processing_usd_per_kg:    float = 50.0

    # ─── COST AMORTISATION & FINANCIAL ───────────────────────────────────────
    # Spacecraft development NRE (~$588M for OSIRIS-REx class).  If 1, the
    # first mission carries the full NRE; raise N to spread across a fleet.
    nre_amortization_missions: int   = 1
    # Share of the NRE line already paid for inside the per-kg recurring
    # hardware rate.  The Module 3 recurring brackets ($100k-$1M/kg, from
    # NICM / SSCM / Aerospace Corp SMCM) are regressions fitted to total
    # program cost, so they carry a development component.  Charging the full
    # OSIRIS-REx $588.5M NRE on top of them double-books that component.
    # 0.30 is a mid-range de-duplication; set to 0.0 to restore the
    # pre-v1.4.0 behaviour and book both in full.
    nre_recurring_overlap_fraction: float = 0.30
    # Time-value of money — compound up-front costs over mission_duration_yr.
    apply_wacc_compounding:    bool  = True
    contingency_fraction:      float = 0.20

    # ─── VEHICLE / PROPELLANT SELECTION ──────────────────────────────────────
    # None = use everything operational; set lists to restrict candidates.
    candidate_vehicles:        Optional[List[str]] = None
    candidate_propellants:     Optional[List[str]] = None
    operational_vehicles_only: bool = True

    # ─── DISPLAY ─────────────────────────────────────────────────────────────
    top_n_preview:             int = 20
    # When the input catalog is large (>50k asteroids), evaluation can take
    # minutes.  Cap to a manageable subset for interactive runs.  Set to 0
    # to evaluate every row.
    eval_row_cap:              int = 5_000

    # ─── PIPELINE VERSION ────────────────────────────────────────────────────
    # 1.3.0 — initial profitability calculator
    # 1.3.1 — switched to UNCREWED autonomous-mission model (paired with
    #         Module 3 v1.2.4):
    #         • Added 'autonomy_nre_cost' line item to mission_cost_usd —
    #           sourced from Module 3's new 'Autonomous mining control & AI
    #           (NRE)' row (replaces legacy 'Crew' row)
    #         • Docstring + cascade comments updated to explicitly state no
    #           crew cost, no life-support, no human in the loop past LEO
    # 1.3.2 — deep accuracy audit (5 fixes, all numerically verified):
    #         • TPS mass now lives IN the rocket-eq cascade — was costed but
    #           not pushed.  Reduces max payload by ~32% on a typical NEA.
    #           New closed-form: m_p_max = (M_LEO/R_out − m_hw
    #             − s·m_dry·R_ret) / (s·R_ret − 1)   where s = 1 + tps_frac.
    #         • Launch insurance basis fixed: now % of (launch + spacecraft
    #           book value), was wrongly % of (launch + future revenue).
    #         • Capsule recurring cost added: dry_return × $/kg-recurring.
    #           Previously the 500-kg capsule had no manufacturing cost.
    #         • Mining-rig vs capsule cost split: rig amortises across
    #           nre_amortization_missions (stays at asteroid), capsule
    #           is per-mission (fly-and-die).
    #         • WACC compounding time-bucketed: upfront × (1+W)^T,
    #           ongoing × (1+W)^(T/2), end × 1.0  (was all to end).
    # 1.3.6 — correctness + performance.  No change to any number produced by
    #         a default-config run (verified bitwise across all 53 numeric
    #         output columns on a 500-asteroid catalog):
    #         • Return-payload is now bounded by return-capsule VOLUME, not
    #           just by mining fraction.  With use_isru_return_propellant=True
    #           AND use_aerocapture_return=False, tps_frac collapses to 0 and
    #           nothing in the rocket equation scales with payload, so the
    #           launch-mass constraint went slack: a 30 km body "returned"
    #           7.4e14 kg in a 500 kg capsule for a $7.8e17 profit that topped
    #           the rankings.  The volume check already existed and already
    #           flagged it (volume_fits=False) but was never applied.  It now
    #           caps the payload; that case yields 144,000 kg / -$2.67e9.
    #           Both sane toggle combinations are unchanged to the bit.
    #         • lookup_asteroid() passes regex=False — designations carry
    #           regex metacharacters, so "(1) Ceres" silently matched
    #           "1 Ceres" and an unbalanced bracket raised re.PatternError.
    #         • Ops-cost and mineral-price lookups memoised; candidate
    #           vehicle × propellant grid hoisted out of the per-asteroid
    #           loop (it depends only on config).  Module 4 went from
    #           8 to 469 asteroids/s — a 5,000-row run is ~11s, was ~10.6min.
    # 1.3.5 — removed Asterank-dependent code (paired with Module 1 v1.0.5):
    #         • asteroid_dv_m_s no longer reads asteroid_row["delta_v_kms"];
    #           all missions use config.default_dv_outbound_m_s / return.
    #         • Output dict no longer emits asterank_value_usd /
    #           asterank_profit_usd / asterank_accessibility columns.
    #         No behavioural change for catalogs without Asterank columns
    #         (which is now every catalog) — v1.3.4 already fell back to
    #         defaults when the field was absent.
    # 1.3.4 — per-asteroid PGM enrichment (paired with Module 1 v1.0.4
    #         + Module 2 v1.1.3).  Three changes:
    #         • Added RARE_METAL_ELEMENTS = {Pt, Pd, Rh, Ir, Os, Ru, Au}.
    #         • _mineral_implied_value() now takes a `pgm_enrichment`
    #           multiplier — scales rare-metal yields only, leaves base
    #           metals (Fe, Ni, Co) untouched.
    #         • asteroid_bulk_value_usd_per_kg() pulls comp_pgm_enrichment
    #           from each asteroid row and applies it to the nickel-iron
    #           mineral lookup only.  Default 1.0× (chondritic) preserves
    #           v1.3.3 behaviour for catalogs from M1 < v1.0.4.
    #         Hand-verified per-type effect:
    #           Type   Enrich  nickel-iron $/kg   asteroid bulk $/kg
    #           ----   ------  ----------------   ------------------
    #           M, Xe   2.0×   $4.60 → $7.10      $3.69 → $5.69  (+54%)
    #           X, E    1.5×   $4.60 → $5.85      —              (+30%-ish)
    #           A, R    0.5×   $4.60 → $3.35      —              (−9% to −20%)
    #           V       0.2×   $4.60 → $2.60      $0.28 → $0.18  (−36%)
    #           others  1.0×   unchanged          unchanged
    #         For a 9,865-kg M-type return: gross $36k → $56k (+54%).
    #         C/B-type water-rich asteroids are unaffected (no metal phase).
    # 1.3.3 — fix silent under-counting in asteroid_bulk_value_usd_per_kg:
    #         • Module 1's 4 composition fractions sum to 0.76-0.96
    #           depending on taxonomy class; the residual (4-24%) was
    #           silently zero-valued.  Now treated as bulk silicate floor
    #           (≈$0.05/kg) — adds 0.2-1.2% to gross value, more honest.
    #         • Pairs with Module 2 v1.1.2's price + yield calibration:
    #           refined-iron Fe $0.50/kg (was iron-ore $0.12), Au $150k,
    #           Pt $45k, Pd $48k, Rh $320k, Water $4,250/kg (Falcon 9
    #           reusable launch cost-savings), plus Ru/Os added to and
    #           Ir bumped in nickel-iron PGM yields.
    #         Combined hand-verified effect (Module 4 output):
    #           Asteroid bulk USD/kg   OLD      NEW
    #           M-type                $2.61   $3.69    (+41%)
    #           S/Q-type              $0.6    $0.85    (+39%)
    #           C-type                $375    $638     (+70%, water-driven)
    #           B-type                $500    $850     (+70%, water-driven)
    #         For a single Falcon Heavy + methalox aerocapture mission
    #         (9.9 t returned), C-type gross value rises $3.7M → $6.3M.
    #         Single-mission profitability is still tough but the top of
    #         the rankings now shows realistic million-dollar gross values
    #         for water-bearing C/B-type targets.
    # 1.3.7 — renumbering, no behaviour change.  This project was briefly
    #         developed in two places at once and both shipped different code
    #         as 1.3.6, so that stamp is ambiguous.  The reconciled module is
    #         1.3.7 because it matches neither parent.  Treat any CSV stamped
    #         1.3.6 as undated and re-run rather than trusting the number.
    # 1.4.0 — realism audit.  Every number this module produces changes.
    #         • PER-ASTEROID Δv.  v1.3.5 removed the Asterank per-target
    #           override and never replaced it, so every asteroid received
    #           identical Δv.  Measured on a 150-row run, max_payload_kg,
    #           total_cost_usd, m_launch_kg, mission_duration_yr, vehicle and
    #           propellant each had exactly ONE unique value catalog-wide;
    #           only bulk_value_usd_per_kg varied.  The profitability ranking
    #           was a spectral-type ranking, and a main-belt body was costed
    #           the same as a co-orbital NEA.  New patched-conic estimator
    #           (asteroid_transfer_dv_km_s) from a / e / i, validated to
    #           within ~10% of Module 3's table and of published Bennu /
    #           Eros / Itokawa figures.  Aerocapture saving is now
    #           per-asteroid rather than a flat 4,000 m/s.
    #           Toggle: use_per_asteroid_dv.
    #         • MINING THROUGHPUT.  Extraction was instantaneous and
    #           unbounded — duration came only from Δv plus a flat 0.5 yr,
    #           whether the mission returned 33 kg or 50 tonnes.  Payload is
    #           now capped by what the rig can dig inside
    #           max_mining_duration_yr, and the actual dig time flows into
    #           mission duration, ops cost and WACC.
    #           Config: mining_rate_kg_per_day_per_kg_rig, and see
    #           mining_duration_yr() / max_payload_by_throughput_kg().
    #         • LOW-THRUST Δv PENALTY.  Applies Module 3 v1.3.0's
    #           dv_penalty_factor, so electric propulsion no longer wins the
    #           mass cascade on an impulsive budget it cannot fly.
    #         • COST DE-DUPLICATION.  The return capsule is priced off
    #           Module 3's new capsule rate ($150k/kg) instead of the
    #           mining-payload rate ($300k/kg), and
    #           nre_recurring_overlap_fraction removes the development share
    #           already embedded in the per-kg recurring brackets.
    #           Set that field to 0.0 to restore the old double-booking.
    #         New output columns: dv_penalty_factor, mining_duration_yr,
    #         throughput_cap_kg, throughput_fits.
    # 1.5.0 — IN-SPACE DELIVERY ARCHITECTURE.  Paired with Module 2 v1.3.0 and
    #         Module 3 v1.4.0.  `delivery_destination` was a Module 2 price
    #         label that Module 4 ignored: whatever it said, this module flew a
    #         re-entry capsule to Earth's surface and costed a full recovery
    #         campaign.  Setting it to 'cislunar' therefore priced the cargo at
    #         a depot while paying to land it in Utah — the exact inconsistency
    #         the field was added to prevent.  It is now an architecture
    #         selector that Module 4 honours, and the two modules are checked
    #         against each other at load time (destination_check).
    #         • RETURN Δv IS NOW PER-DESTINATION, derived per asteroid from the
    #           arrival v_infinity rather than assumed.  asteroid_transfer_dv_km_s
    #           returns a dict of legs instead of a 3-tuple.  New
    #           _cislunar_capture_dv_km_s captures at low perigee into an
    #           ellipse reaching lunar distance (taking the Oberth benefit),
    #           then inserts into NRHO at apogee.
    #           At v_inf = 3 km/s the three architectures cost:
    #               earth_surface (direct entry)  dv_match + 0      km/s
    #               cislunar (Oberth + NRHO)      dv_match + 0.96   km/s
    #               leo (propulsive capture)      dv_match + 3.59   km/s
    #           LEO is the most expensive destination to reach AND worth less
    #           per kg than cislunar — the two effects compound, and the
    #           ranking now shows it.
    #         • COST LINES SWAP BY ARCHITECTURE.  An in-space delivery carries
    #           a $60k/kg berthing adapter instead of a $150k/kg re-entry
    #           capsule, $2M of depot handover instead of a $15M Earth recovery
    #           campaign, and the $1.2M launch-only Part 450 licence instead of
    #           the $2.5M launch+re-entry one.
    #         • TPS IS ARCHITECTURE-GATED (uses_tps).  A cislunar delivery never
    #           enters an atmosphere, so use_aerocapture_return is ignored there
    #           and no heat-shield mass enters the cascade.  LEO honours it as
    #           aerocapture + multi-pass aerobraking.
    #         earth_surface runs are UNCHANGED to the bit — the architecture
    #         table reproduces the old code path exactly for that destination.
    #         New output columns: delivery_destination, delivery_arch,
    #         returns_to_earth, flies_tps.
    #
    #         BENEFICIATION (use_beneficiation, default False — off preserves
    #         v1.4.0 output bit-for-bit).  The pipeline flew home run-of-mine
    #         regolith at bulk grade while the rig's own throughput cap sat 66x
    #         above the rocket-equation payload limit and never bound: all that
    #         processing capacity was modelled as idle.  Terrestrial mines ship
    #         concentrate, not ore.  With it on:
    #         • The throughput cap now bounds the FEED, not the payload.  The
    #           rig digs everything it can reach inside max_mining_duration_yr
    #           and loads only concentrate.
    #         • THE LOAD IS OPTIMISED, NOT SPECIFIED.  A mission is not sent
    #           for a named mineral; it brings back the most valuable load it
    #           can assemble from what the target actually contains.  With a
    #           fixed mass budget and divisible per-kg-priced phases that is a
    #           fractional knapsack, so greedy selection by $/kg is provably
    #           optimal: fill the hold with the best phase available, then the
    #           next, until full or the feed runs out (optimal_payload_mix,
    #           over asteroid_phase_table).
    #           Both honest bounds fall out of it automatically — CONTENT (you
    #           cannot load more of a phase than the processed feed held, times
    #           beneficiation_recovery) and PURITY (once the hold is pure best
    #           phase there is nothing better to add).  Worked example, M-type
    #           at 50% metal / 45% silicate, recovery 0.90:
    #               feed 1.0x -> $5,135/kg, hold 90% full, in-situ ratios
    #               feed 2.0x -> $7,081/kg, 90% metal
    #               feed 2.2x -> $7,567/kg, 100% metal — saturated
    #               feed 5.0x -> $7,567/kg, no further gain
    #           The saturation ratio is 1/(frac_best x recovery), which is what
    #           sets target_ratio.
    #         • TIME is charged on the feed: mining_duration_yr now takes
    #           feed_kg, so a 50:1 ratio costs 50x the dig time, which flows
    #           into mission duration, ops cost and WACC.
    #         • ENERGY and MASS are charged and FED BACK.  Module 3's 200 Wh/kg
    #           excavation and 500 Wh/kg beneficiation rates over the stay time
    #           give a continuous power draw; Module 3's new 60 W/kg-at-1-AU
    #           power-system row, scaled 1/r^2 by the target's semi-major axis,
    #           turns that into array mass; the array enters the SAME rocket
    #           equation as the rig, so grade is bought with payload.  The
    #           circular dependency (payload -> feed -> power -> mass -> payload)
    #           is solved by fixed-point iteration, not assumed away.
    #         New config: use_beneficiation, beneficiation_recovery,
    #         max_concentration_ratio.
    #         New output columns: beneficiation, feed_processed_kg,
    #         concentration_ratio, delivered_value_usd_per_kg,
    #         best_phase_usd_per_kg, purity_bound_binds, payload_mix,
    #         payload_dominant_phase, payload_dominant_frac,
    #         processing_power_w, power_system_kg, power_w_per_kg_at_target,
    #         hardware_total_kg, power_system_cost_usd.
    # 1.6.0 — SURFACE DESTINATIONS: lunar_surface and mars_surface.  Paired
    #         with Module 2 v1.4.0 and Module 3 v1.5.0.  The three existing
    #         destinations are unchanged; an earth_surface run is still
    #         bit-identical to v1.4.0.
    #         • Lunar surface = cislunar capture + 2.6 km/s of NRHO→LLO→
    #           surface (Module 3), entirely propulsive.  No TPS: there is no
    #           atmosphere, so use_aerocapture_return is ignored, exactly as
    #           for cislunar.
    #         • MARS IS A DIFFERENT JOURNEY, not a discounted Earth return.
    #           New _asteroid_to_mars_dv_km_s runs the same patched-conic
    #           treatment but terminates the heliocentric transfer at Mars'
    #           orbit (1.524 AU) rather than Earth's, so the departure burn,
    #           the arrival v_infinity and the capture into Mars' well are all
    #           computed separately.  Modelling it as "Earth return minus
    #           something" would have hidden the interesting part: plenty of
    #           NEAs have aphelia near Mars and are genuinely more accessible
    #           from a Mars base than from Earth.
    #           Aerocapture IS available at Mars and is worth several km/s, so
    #           mars_surface carries TPS where lunar_surface cannot.
    #         • Surface deliveries carry a $200k/kg lander (Module 3's new
    #           row) rather than a $60k/kg berthing adapter or a $150k/kg
    #           re-entry capsule — a lander flies itself down.
    #         New Δv legs on asteroid_transfer_dv_km_s: ret_lunar_surface_prop,
    #         ret_mars_surface_aero, ret_mars_surface_prop, v_inf_mars,
    #         dv_depart_for_mars.
    pipeline_version: str = "1.6.0"


CALC_CONFIG = CalcConfig()
os.makedirs(CALC_CONFIG.output_dir, exist_ok=True)

print(f"✅  Configuration loaded — output dir: {CALC_CONFIG.output_dir}")
print(f"    Hardware       : {CALC_CONFIG.mining_hardware_kg:,.0f} kg mining rig "
      f"+ {CALC_CONFIG.return_vehicle_dry_kg:,.0f} kg return-capsule dry")
print(f"    Mining cap     : {CALC_CONFIG.max_mining_fraction:.0%} of asteroid mass per mission")
print(f"    Return mode    : "
      f"{'aerocapture (−' + str(int(CALC_CONFIG.aerocapture_dv_savings_m_s)) + ' m/s + TPS mass)' if CALC_CONFIG.use_aerocapture_return else 'propulsive'}")
print(f"    ISRU           : {CALC_CONFIG.use_isru_return_propellant}")
print(f"    Contingency    : {CALC_CONFIG.contingency_fraction:.0%}  |  "
      f"NRE amortised over {CALC_CONFIG.nre_amortization_missions} mission(s)")


# ─────────────────────────────────────────────────────────────────────────────
# CATALOG LOADER  (reads Module 1, 2, 3 CSVs)
# ─────────────────────────────────────────────────────────────────────────────
def _load_csv(path: str, label: str) -> pd.DataFrame:
    """Read a CSV with friendly error reporting."""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{label} not found at {path} — has the upstream module been run?"
        )
    df = pd.read_csv(path)
    print(f"     📥  {label:28s} {len(df):>7,} rows  ←  {path}")
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


def load_all_catalogs(config: CalcConfig) -> Dict[str, pd.DataFrame]:
    """Load and lightly normalise the three upstream catalogs."""
    print("\n📂  Loading upstream catalogs …")

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

    # Parse Module 1's comp_minerals list-column back into actual lists
    if "comp_minerals" in catalogs["asteroids"].columns:
        catalogs["asteroids"]["comp_minerals"] = (
            catalogs["asteroids"]["comp_minerals"].apply(_parse_minerals_list)
        )

    return catalogs


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-MODULE INTEGRITY CHECK
# ─────────────────────────────────────────────────────────────────────────────
def destination_check(catalogs: Dict[str, pd.DataFrame], config: CalcConfig) -> None:
    """Verify Module 2 priced the material for the destination Module 4 flies to.

    This is the one cross-module mismatch that silently produces a
    plausible-looking but meaningless answer.  Module 2 stamps every row with
    the destination it priced for; if that disagrees with the architecture
    this module is about to cost, the run pairs (say) cislunar-depot prices
    with a re-entry-capsule mission — exactly the inconsistency the
    destination field exists to prevent.
    """
    minerals = catalogs.get("minerals")
    if minerals is None or "delivery_destination" not in minerals.columns:
        print("     ⚠️   Module 2 catalog carries no `delivery_destination` "
              "column (pre-v1.3.0) — cannot verify pricing matches this "
              "mission architecture.  Re-run Module 2.")
        return

    stamped = str(minerals["delivery_destination"].iloc[0]).strip().lower()
    mine    = str(config.delivery_destination).strip().lower()
    if stamped == mine:
        arch = delivery_architecture(mine)
        print(f"     ✅  Delivery destination '{mine}' — {arch['label']}")
        return

    print(f"     ❌  DESTINATION MISMATCH — the prices and the mission disagree.")
    print(f"          Module 2 priced the material for : {stamped}")
    print(f"          Module 4 is flying it to         : {mine}")
    print(f"        → Every profit number in this run is meaningless.  Set both")
    print(f"          MINERAL_CONFIG.delivery_destination and")
    print(f"          CALC_CONFIG.delivery_destination to the same value and")
    print(f"          re-run Module 2 before Module 4.")


def integrity_check(catalogs: Dict[str, pd.DataFrame]) -> None:
    """Verify every mineral named by Module 1 is priced by Module 2.

    This catches the silent failure where a future Module 1 taxonomy edit
    introduces a new mineral that Module 2 has no row for — without this
    check, those minerals would simply not contribute to value (silently).
    """
    print("\n🔗  Integrity check — Module 1 ↔ Module 2 mineral coverage …")

    asteroids   = catalogs["asteroids"]
    mineral_set = set(catalogs["minerals"]["name"].astype(str))

    if "comp_minerals" not in asteroids.columns:
        print("     ⚠️  asteroid catalog has no `comp_minerals` column — skipping check")
        return

    # Every unique mineral name the asteroid catalog references
    referenced = set()
    for mins in asteroids["comp_minerals"]:
        if isinstance(mins, list):
            referenced.update(str(m) for m in mins if m)

    missing = referenced - mineral_set
    extra   = mineral_set - referenced

    if missing:
        print(f"     ❌  {len(missing)} mineral(s) named by Module 1 but ABSENT in Module 2:")
        for m in sorted(missing):
            print(f"          • {m}")
        print("        → Module 4 will treat these as zero-value contributions.")
    else:
        print(f"     ✅  All {len(referenced)} referenced minerals are priced by Module 2")

    if extra:
        # Not an error — Module 2 prices elements (Au, Pt, …) that Module 1
        # doesn't name directly.  Just informational.
        print(f"     ℹ️   Module 2 prices {len(extra)} extra rows not named by Module 1 "
              f"(expected: elements + ice + bulk categories)")


# ─────────────────────────────────────────────────────────────────────────────
# MINERAL-VALUE LOOKUPS
# ─────────────────────────────────────────────────────────────────────────────
# Rare-metal elements that get scaled by per-asteroid PGM-enrichment
# factor (Module 1 v1.0.4's comp_pgm_enrichment column).  The base metals
# (iron, nickel, cobalt) in nickel-iron alloy are NOT scaled — they are
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
    portion (Pt, Pd, Rh, Ir, Os, Ru, Au) by `pgm_enrichment` — the per-
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


def asteroid_bulk_value_usd_per_kg(
    asteroid_row: pd.Series, mineral_df: pd.DataFrame,
) -> float:
    """Composite USD/kg for the bulk material of one asteroid.

    v1.3.4 — applies per-asteroid PGM enrichment to the metal fraction.
    Module 1 v1.0.4+ provides `comp_pgm_enrichment` (default 1.0× chondritic
    baseline; 2.0× for differentiated M-type cores; 0.2× for V-type basaltic
    crust; 0.5× for mantle fragments).  Multiplies only the rare-metal yields
    in nickel-iron — base metals (Fe, Ni, Co) and non-metal categories
    (silicates, carbon, water) are unaffected.

    v1.3.3 — "Other" residual mass (Module 1 fractions sum to 0.76-0.96
    across types) was silently zero-valued; now treated as bulk silicate
    at $0.05/kg floor.
    """
    pgm_enrichment = asteroid_row.get("comp_pgm_enrichment")
    if pgm_enrichment is None or pd.isna(pgm_enrichment):
        pgm_enrichment = 1.0    # chondritic baseline when M1 < v1.0.4
    pgm_enrichment = float(pgm_enrichment)

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

    # Residual "other" mass — value at silicate floor so it doesn't vanish.
    if 0.0 < frac_sum < 1.0:
        other_frac     = 1.0 - frac_sum
        silicate_price = _mineral_price(mineral_df, "silicates") or 0.05
        total += other_frac * float(silicate_price)

    return total


def asteroid_phase_table(
    asteroid_row: pd.Series, mineral_df: pd.DataFrame,
) -> List[Tuple[str, float, float]]:
    """[(phase, mass_fraction, usd_per_kg)] for one asteroid (v1.6.0).

    The same four taxonomy fractions `asteroid_bulk_value_usd_per_kg` blends,
    but kept SEPARATE so a mission can choose what to load rather than being
    handed the mean.  The residual (Module 1's fractions sum to 0.76-0.96) is
    included as bulk silicate, matching the bulk function's floor treatment.

    Phases with zero fraction are dropped — you cannot select what is not
    there.
    """
    pgm_enrichment = asteroid_row.get("comp_pgm_enrichment")
    if pgm_enrichment is None or pd.isna(pgm_enrichment):
        pgm_enrichment = 1.0
    pgm_enrichment = float(pgm_enrichment)

    phases: List[Tuple[str, float, float]] = []
    frac_sum = 0.0
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
        phases.append((mineral_name, float(frac), float(price)))
        frac_sum += float(frac)

    if 0.0 < frac_sum < 1.0:
        silicate_price = _mineral_price(mineral_df, "silicates") or 0.05
        phases.append(("other (bulk silicate)", 1.0 - frac_sum, float(silicate_price)))

    return phases


def optimal_payload_mix(
    payload_kg: float,
    feed_kg:    float,
    phases:     List[Tuple[str, float, float]],
    recovery:   float,
) -> Dict[str, object]:
    """Most valuable payload obtainable from `feed_kg` of this rock (v1.6.0).

    The mission is not sent for a named mineral — it is sent to bring back the
    best load it can assemble from what the target actually contains.  With a
    fixed mass budget and divisible, per-kilogram-priced phases, that is a
    FRACTIONAL KNAPSACK, and greedy selection by $/kg is provably optimal:
    fill the hold with the most valuable phase available, then the next, until
    the hold is full or the feed runs out.

    Separation recovers `recovery` of each phase present in the feed; whatever
    is not loaded is left at the asteroid.

    Returns value, blended $/kg, the chosen mix in kg, and the mass fraction
    the best phase makes up — which is the natural read on how well
    concentrated the load actually is.
    """
    if payload_kg <= 0 or not phases:
        return {"value_usd": 0.0, "usd_per_kg": 0.0, "mix_kg": {},
                "dominant_phase": None, "dominant_frac": 0.0}

    remaining = float(payload_kg)
    total     = 0.0
    mix: Dict[str, float] = {}
    for name, frac, price in sorted(phases, key=lambda p: -p[2]):
        if remaining <= 0:
            break
        available = float(feed_kg) * frac * recovery
        take      = min(available, remaining)
        if take <= 0:
            continue
        mix[name]  = take
        total     += take * price
        remaining -= take

    # Anything the feed could not fill is dead space — the hold flies partly
    # empty rather than being topped up with rock that was never dug.
    loaded = float(payload_kg) - remaining
    if loaded <= 0:
        return {"value_usd": 0.0, "usd_per_kg": 0.0, "mix_kg": {},
                "dominant_phase": None, "dominant_frac": 0.0}

    dominant = max(mix.items(), key=lambda kv: kv[1])
    return {
        "value_usd":      total,
        "usd_per_kg":     total / loaded,
        "loaded_kg":      loaded,
        "mix_kg":         mix,
        "dominant_phase": dominant[0],
        "dominant_frac":  dominant[1] / loaded,
    }


def asteroid_best_phase_usd_per_kg(
    asteroid_row: pd.Series, mineral_df: pd.DataFrame,
) -> float:
    """$/kg of the single most valuable phase actually present (v1.5.0).

    This is the PURITY BOUND on beneficiation.  Concentrating rejects gangue,
    it does not transmute: the richest concentrate physically obtainable from
    a body is 100% of its best phase, so no amount of processing can push the
    delivered $/kg above this number.

    Only phases with a non-zero fraction count — a body with no metal cannot
    be concentrated into metal.  Returns the bulk value as a floor so the
    bound can never sit below the unconcentrated material.
    """
    pgm_enrichment = asteroid_row.get("comp_pgm_enrichment")
    if pgm_enrichment is None or pd.isna(pgm_enrichment):
        pgm_enrichment = 1.0
    pgm_enrichment = float(pgm_enrichment)

    best = 0.0
    for frac_col, mineral_name in FRACTION_TO_MINERAL.items():
        frac = asteroid_row.get(frac_col)
        if frac is None or pd.isna(frac) or float(frac) <= 0.0:
            continue
        if mineral_name == "nickel-iron":
            price = _mineral_implied_value(mineral_df, mineral_name, pgm_enrichment)
        else:
            price = _mineral_implied_value(mineral_df, mineral_name)
        if price is not None and float(price) > best:
            best = float(price)

    bulk = asteroid_bulk_value_usd_per_kg(asteroid_row, mineral_df)
    return max(best, bulk)


# ─────────────────────────────────────────────────────────────────────────────
# BENEFICIATION — TIME AND ENERGY INTENSITY  (v1.5.0)
# ─────────────────────────────────────────────────────────────────────────────
# Concentrating ore in deep space costs three things, and the model charges
# for all three:
#
#   TIME    — the rig has to dig the whole feed, not just the payload.  A 50:1
#             concentration means excavating 50 kg for every kilogram flown
#             home, and that time flows into mission duration, mission ops
#             and WACC compounding exactly like any other stay time.
#   ENERGY  — Module 3 rates excavation at 200 Wh per kg of regolith moved and
#             beneficiation at 500 Wh per kg of product.  Energy over time is
#             power, and power in deep space is a solar array.
#   MASS    — that array has to be launched.  Its mass enters the SAME rocket
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


def processing_power_w(
    feed_kg:        float,
    concentrate_kg: float,
    duration_yr:    float,
    dig_wh_per_kg:  float,
    benef_wh_per_kg: float,
) -> float:
    """Continuous electrical power to dig `feed_kg` and concentrate it.

    Energy is charged on the two Module 3 rates — excavation per kg of
    regolith MOVED, beneficiation per kg of product OUT — and divided by the
    time available, because energy over time is power and power is what sizes
    the array.
    """
    if duration_yr <= 0:
        return 0.0
    energy_wh = dig_wh_per_kg * max(feed_kg, 0.0) + benef_wh_per_kg * max(concentrate_kg, 0.0)
    return energy_wh / (duration_yr * 365.25 * 24.0)


# ─────────────────────────────────────────────────────────────────────────────
# Δv RESOLVER  (v1.4.0 — per-asteroid, from orbital elements)
# ─────────────────────────────────────────────────────────────────────────────
# Until v1.4.0 every asteroid in the catalog received the SAME Δv, because
# v1.3.5 removed the per-target Asterank override without replacing it.  The
# consequence was not subtle: on a 150-asteroid run, max_payload_kg,
# total_cost_usd, m_launch_kg, mission_duration_yr, vehicle and propellant
# each had exactly ONE unique value across the whole catalog.  Only
# bulk_value_usd_per_kg varied.  The "profitability ranking" was a ranking of
# spectral types, and orbital accessibility — the single most important
# variable in asteroid mining economics — had no effect at all.  A main-belt
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
#      flyby — a mining mission has to stop).
#
# Return is the mirror image: the apsis-match burn to get back onto an
# Earth-intercept trajectory, then either a propulsive capture at Earth
# (√(v_esc² + v_inf²) − v_LEO again) or an atmospheric entry that costs
# essentially no propellant but buys a heat shield.  This replaces the flat
# `aerocapture_dv_savings_m_s` constant with a per-asteroid saving.
#
# VALIDATED against Module 3's independently-sourced DELTA_V_REFERENCE:
#   target                        estimator   Module 3 table
#   main belt (a=2.7, e=0.1, i=10°)  10.43 km/s   10.5 km/s  (Module 3)
#   moderate NEA (a=1.2, e=0.3, i=8°) 5.58 km/s    6.5 km/s  (Module 3 avg NEA)
#   Bennu    (a=1.126, e=0.204, i=6.0°)  4.64 km/s   ~5.1 km/s (published)
#   Eros     (a=1.458, e=0.223, i=10.8°) 6.10 km/s   ~6.5 km/s (published)
#   Itokawa  (a=1.324, e=0.280, i=1.6°)  4.14 km/s   ~4.6 km/s (published)
# Within ~10% of both the reference table and published mission values, which
# is the accuracy an analytic estimator can honestly claim.  It runs slightly
# LOW against published figures for the easiest co-orbital targets, where real
# mission design finds better transfers than a two-impulse apsis match.
# The floor is the physical one: escaping LEO costs √2·v_LEO − v_LEO ≈
# 3.22 km/s no matter how accessible the target is.

AU_KM            = 1.495_978_707e8     # astronomical unit
V_EARTH_KM_S     = 29.784              # Earth mean orbital velocity
MU_EARTH_KM3_S2  = 398_600.4418        # Earth gravitational parameter
R_LEO_KM         = 6_378.14 + 200.0    # 200-km circular parking orbit


R_MOON_ORBIT_KM  = 384_400.0           # lunar mean orbital radius
# NRHO insertion at apogee, Module 3 DELTA_V_REFERENCE "TLI → NRHO insertion".
DV_NRHO_INSERTION_KM_S = 0.450
# Periapsis-raise burn to finish an aerobraked capture, Module 3
# "NEA → LEO delivery (aerobraked)".
DV_AEROBRAKE_TRIM_KM_S = 0.100

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
# Propulsive descent from low Mars orbit with NO atmospheric help — the
# fallback when aerocapture is switched off.  Mirrors the 4.1 km/s ascent.
DV_MARS_POWERED_DESCENT_KM_S = 4.100


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
      2. NRHO insertion at apogee — Module 3's 450 m/s.

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


def asteroid_transfer_dv_km_s(
    a_au: float, e: float, i_deg: float,
) -> Optional[Dict[str, float]]:
    """Patched-conic Δv budget for a rendezvous mission to one asteroid.

    Returns a dict of Δv legs in km/s, or None if the elements are unusable:

        dv_out                  outbound, LEO departure + apsis rendezvous
        v_inf                   arrival hyperbolic excess back at Earth
        ret_earth_surface_aero  direct entry — no capture burn at all
        ret_earth_surface_prop  propulsive capture into LEO, then deorbit
        ret_leo_prop            propulsive capture into LEO
        ret_leo_aero            aerocapture + aerobraking, trim burn only
        ret_cislunar_prop       Oberth capture + NRHO insertion

    v1.5.0 — was a 3-tuple (out, return_propulsive, return_aerocapture) when
    Earth's surface was the only destination the pipeline could model.

    All heliocentric work is done in canonical units (Earth orbit radius = 1,
    Earth orbital speed = 1) and converted to km/s at the end.
    """
    try:
        a = float(a_au); e = float(e); i = float(i_deg)
    except (TypeError, ValueError):
        return None
    if not (a > 0) or not (0.0 <= e < 1.0) or not (0.0 <= i <= 180.0):
        return None

    # Rendezvous at the apsis nearer to reachable transfer geometry.  For the
    # overwhelming majority (a > 1) that is aphelion; for wholly-interior
    # orbits (Atira-class) it is perihelion.
    Q = a * (1.0 + e)
    q = a * (1.0 - e)
    r_target = Q if Q >= 1.0 else q
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
    #   Earth surface, direct entry — no capture burn at all.  The arrival
    #     energy is dumped into a heat shield, whose mass the Module 4 cascade
    #     carries outbound and pushes back through the return burn.
    #   LEO, propulsive — the most expensive option in the model.  LEO is the
    #     deepest of the three destinations, so circularising there means
    #     killing the whole hyperbolic excess AND the escape velocity.
    #   LEO, aerobraked — trades that Δv for TPS mass and months of passes.
    #   Cislunar — cheapest, because capture only has to BIND the orbit, and
    #     the burn happens at low perigee where Oberth pays best.
    #   Lunar surface — cislunar capture, then NRHO→LLO→surface.  Airless, so
    #     that last 2.6 km/s is entirely propulsive.
    #   Mars — not an Earth return at all.  See the separate transfer below.
    dv_leo_capture = _leo_departure_dv_km_s(v_inf)
    dv_cislunar    = _cislunar_capture_dv_km_s(v_inf)

    legs = {
        "dv_out":                 dv_out,
        "v_inf":                  v_inf,
        "ret_earth_surface_aero": dv_match,
        "ret_earth_surface_prop": dv_match + dv_leo_capture,
        "ret_leo_prop":           dv_match + dv_leo_capture,
        "ret_leo_aero":           dv_match + DV_AEROBRAKE_TRIM_KM_S,
        "ret_cislunar_prop":      dv_match + _cislunar_capture_dv_km_s(v_inf),
        "ret_lunar_surface_prop": dv_match + dv_cislunar
                                  + DV_NRHO_TO_LUNAR_SURFACE_KM_S,
    }

    # ── Mars: a different journey, not a discounted Earth return ─────────────
    # Delivering to Mars does not go near Earth.  The heliocentric transfer
    # runs from the asteroid's orbit to Mars' (1.524 AU), so the departure
    # burn, the arrival v_infinity and the capture are all different numbers.
    # Many NEAs have aphelia out near Mars, which makes them genuinely closer
    # to a Mars base than to Earth — a fact the model can only show if this
    # leg is computed rather than approximated.
    mars = _asteroid_to_mars_dv_km_s(a, e, i, r_target)
    if mars is not None:
        legs.update(mars)
    return legs


def _asteroid_to_mars_dv_km_s(
    a: float, e: float, i_deg: float, r_target: float,
) -> Optional[Dict[str, float]]:
    """Δv from an asteroid to the Martian surface, in km/s.

    Same patched-conic treatment as the Earth legs, but the heliocentric
    transfer terminates at Mars' orbit instead of Earth's, and the capture is
    into Mars' gravity well.

    Returns the propulsive and aerocaptured surface arrivals, or None if the
    transfer geometry does not close.  Mars has an atmosphere, so aerocapture
    is genuinely available — and it is worth several km/s.
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
    }


# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY ARCHITECTURE  (v1.5.0)
# ─────────────────────────────────────────────────────────────────────────────
# `delivery_destination` is not a price label — it selects a physically
# different mission.  Each architecture decides which return leg is flown and
# which cost lines exist at all.
#
#   uses_tps        heat shield hauled outbound and pushed back through the
#                   return burn (direct entry, or aerobraked capture)
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
        "label": "re-entry capsule to Earth's surface",
    },
    "leo": {
        "returns_to_earth": False,
        "aero_leg":  "ret_leo_aero",
        "prop_leg":  "ret_leo_prop",
        "aero_allowed": True,     # aerocapture + multi-pass aerobraking
        "label": "berthed at an LEO depot",
    },
    "cislunar": {
        "returns_to_earth": False,
        "aero_leg":  None,        # never passes through the atmosphere
        "prop_leg":  "ret_cislunar_prop",
        "aero_allowed": False,
        "label": "berthed at a cislunar (NRHO) depot",
    },
    "lunar_surface": {
        "returns_to_earth": False,
        "aero_leg":  None,        # the Moon has no atmosphere to brake against
        "prop_leg":  "ret_lunar_surface_prop",
        "aero_allowed": False,
        "needs_lander": True,
        "label": "landed at a lunar surface base",
    },
    "mars_surface": {
        "returns_to_earth": False,
        "aero_leg":  "ret_mars_surface_aero",
        "prop_leg":  "ret_mars_surface_prop",
        "aero_allowed": True,     # Mars aerocapture is worth several km/s
        "needs_lander": True,
        "label": "landed at a Mars surface base",
    },
}


def delivery_architecture(destination: str) -> dict:
    """Look up the mission architecture for a delivery destination.

    Unknown destinations fall back to earth_surface — the conservative
    choice, and the one whose cost lines are all present.
    """
    key = str(destination or "").strip().lower()
    if key not in DELIVERY_ARCHITECTURES:
        print(f"     ⚠️   Unknown delivery_destination {destination!r} — "
              f"falling back to 'earth_surface'.  Valid: "
              f"{', '.join(sorted(DELIVERY_ARCHITECTURES))}")
        key = "earth_surface"
    return DELIVERY_ARCHITECTURES[key]


def uses_tps(config: CalcConfig) -> bool:
    """True when this architecture actually flies a heat shield.

    Aerocapture is a request, not a guarantee: a cislunar delivery never
    touches the atmosphere, so asking for aerocapture there gets you a
    propulsive capture and no TPS mass.
    """
    arch = delivery_architecture(config.delivery_destination)
    return bool(config.use_aerocapture_return and arch["aero_allowed"])


def asteroid_dv_m_s(asteroid_row: pd.Series, config: CalcConfig) -> Tuple[float, float]:
    """Return (Δv_outbound, Δv_return) in m/s for one asteroid.

    The return leg depends on the delivery destination as well as on the
    asteroid — v1.5.0.  Uses the per-asteroid estimator when Module 1 supplied
    usable orbital elements, and falls back to the CalcConfig reference
    defaults when it did not.  Set `config.use_per_asteroid_dv = False` to
    force the old uniform behaviour for every row.
    """
    arch = delivery_architecture(config.delivery_destination)
    aero = uses_tps(config)
    leg  = arch["aero_leg"] if aero else arch["prop_leg"]

    estimate = None
    if config.use_per_asteroid_dv:
        estimate = asteroid_transfer_dv_km_s(
            asteroid_row.get("semi_major_axis_au"),
            asteroid_row.get("eccentricity"),
            asteroid_row.get("inclination_deg"),
        )

    if estimate is not None:
        dv_out = estimate["dv_out"] * 1_000.0
        dv_ret = estimate[leg] * 1_000.0
        # Clamp against physically silly extremes (bad elements upstream).
        dv_out = min(max(dv_out, 3_000.0), config.max_dv_outbound_m_s)
        dv_ret = min(max(dv_ret, 300.0),  config.max_dv_outbound_m_s)
        return dv_out, dv_ret

    # ── Fallback: uniform reference Δv (pre-v1.4.0 behaviour) ────────────────
    # No orbital elements means no v_infinity, so the destination-specific
    # capture cannot be derived.  Approximate it from the reference figures:
    # the aerocapture saving for an Earth return, and Module 3's reference
    # return legs for the in-space destinations.
    dv_out             = config.default_dv_outbound_m_s
    dv_ret_propulsive  = config.default_dv_return_m_s
    if config.delivery_destination == "cislunar":
        # Module 3 "NEA → cislunar NRHO (Oberth capture)" vs "NEA → Earth
        # return (propulsive)": 960 / 5,500 of the propulsive budget.
        dv_ret = dv_ret_propulsive * (960.0 / 5_500.0)
    elif aero:
        dv_ret = max(500.0, dv_ret_propulsive - config.aerocapture_dv_savings_m_s)
    else:
        dv_ret = dv_ret_propulsive
    return dv_out, dv_ret


def mining_duration_yr(payload_kg: float, config: CalcConfig) -> float:
    """Time at the asteroid needed to extract `payload_kg` (years).

    v1.4.0.  Throughput scales with the rig mass actually delivered, so a
    bigger haul costs proportionally more mission-years — which then flows
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
# ROCKET-EQUATION RETURN-MISSION SOLVER
# ─────────────────────────────────────────────────────────────────────────────
def max_return_payload_kg(
    leo_capacity_kg: float,
    isp_s:           float,
    dv_out_m_s:      float,
    dv_ret_m_s:      float,
    hardware_kg:     float,
    dry_return_kg:   float,
    tps_frac:        float = 0.0,
    isru_return:     bool  = False,
) -> Dict[str, float]:
    """Closed-form max returned-payload solver for a return-sample mission.

    Heat shield (`tps_frac` > 0) is fully accounted for: TPS mass = tps_frac
    × (m_payload + m_dry_return) is hauled outbound from Earth AND pushed
    through the return burn (even though it ablates during atmospheric
    entry).  Let s = 1 + tps_frac.

    Working backward from Earth landing:
        m_after_return  = m_payload + m_dry_return + m_tps
                        = s · (m_payload + m_dry_return)
        m_before_return = m_after_return × R_ret
        m_return_prop   = (R_ret − 1) × m_after_return     (zero if ISRU on)

        m_at_asteroid     = m_hardware + m_dry_return + m_tps + m_return_prop
                            (the mined payload is loaded HERE, not brought)
        m_before_outbound = m_at_asteroid × R_out
        m_outbound_prop   = (R_out − 1) × m_at_asteroid

        m_launch = m_at_asteroid × R_out

    NO-ISRU closed form:
        m_payload_max =
            (M_LEO/R_out − m_hardware − m_dry_return · s · R_ret) /
            (s · R_ret − 1)

    Returns a dict with the full mass cascade.  All masses in kg.
    """
    def _infeasible(r_out=0.0, r_ret=0.0):
        return {"max_payload_kg": 0.0, "viable": False,
                "r_out": r_out, "r_ret": r_ret,
                "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
                "m_at_asteroid": 0, "m_tps": 0}

    if not np.isfinite(isp_s) or isp_s <= 0:
        return _infeasible()
    if not (np.isfinite(dv_out_m_s) and np.isfinite(dv_ret_m_s)):
        return _infeasible()
    if dv_out_m_s < 0 or dv_ret_m_s < 0:
        return _infeasible()
    if not np.isfinite(leo_capacity_kg) or leo_capacity_kg <= 0:
        return _infeasible()

    r_out = float(np.exp(dv_out_m_s / (isp_s * G0_M_S2)))
    r_ret = float(np.exp(dv_ret_m_s / (isp_s * G0_M_S2)))
    if not (np.isfinite(r_out) and np.isfinite(r_ret)):
        return _infeasible()      # Δv/Isp so extreme the mass ratio overflows
    s     = 1.0 + tps_frac

    if isru_return:
        # ISRU mode: return propellant is manufactured ON the asteroid from
        # mined volatiles, NOT carried up from Earth.  TPS is still launched
        # from Earth (must scale with planned m_payload), so the launch
        # constraint becomes:
        #
        #   M_LEO ≥ (m_hardware + m_dry_return + m_tps) × R_out
        #         = (m_hardware + s·m_dry_return + tps_frac·m_payload) × R_out
        #
        # ⇒ m_payload_launch_max = (M_LEO/R_out − m_hardware − s·m_dry_return) / tps_frac
        #   (and =∞ when tps_frac=0, i.e. propulsive return — mining cap binds)
        base_launch = (hardware_kg + s * dry_return_kg) * r_out
        if base_launch > leo_capacity_kg:
            return {"max_payload_kg": 0.0, "viable": False,
                    "r_out": r_out, "r_ret": r_ret,
                    "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
                    "m_at_asteroid": 0, "m_tps": 0}
        if tps_frac > 0:
            m_payload_launch_max = (
                leo_capacity_kg / r_out - hardware_kg - s * dry_return_kg
            ) / tps_frac
            m_payload_max = max(0.0, m_payload_launch_max)
        else:
            m_payload_max = np.inf   # mining cap binds downstream

        return {
            "max_payload_kg":  m_payload_max,
            "viable":          True,
            "r_out":           r_out,
            "r_ret":           r_ret,
            # Placeholder cascade — evaluate_combo will recompute once the
            # actual capped payload is known (TPS / return-prop / outbound-prop
            # all depend on the final m_payload).
            "m_launch":        base_launch,
            "m_outbound_prop": base_launch - (hardware_kg + s * dry_return_kg),
            "m_return_prop":   0.0,
            "m_at_asteroid":   hardware_kg + s * dry_return_kg,
            "m_tps":           tps_frac * dry_return_kg,  # baseline TPS for empty payload
        }

    # ── NO-ISRU: return prop is hauled outbound as dead mass ─────────────────
    # m_after_return  = s · (m_payload + m_dry_return)
    # m_return_prop   = (R_ret − 1) · s · (m_payload + m_dry_return)
    # m_at_asteroid   = m_hardware + s · m_dry_return × R_ret + m_payload · (s·R_ret − 1)
    # M_LEO = m_at_asteroid × R_out
    # ⇒ m_payload_max = (M_LEO/R_out − m_hardware − s·m_dry_return·R_ret) / (s·R_ret − 1)
    denom   = s * r_ret - 1.0
    bracket = leo_capacity_kg / r_out - hardware_kg - s * dry_return_kg * r_ret
    if bracket <= 0 or denom <= 0:
        return {"max_payload_kg": 0.0, "viable": False,
                "r_out": r_out, "r_ret": r_ret,
                "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
                "m_at_asteroid": 0, "m_tps": 0}

    m_payload_max = bracket / denom
    if m_payload_max <= 0:
        return {"max_payload_kg": 0.0, "viable": False,
                "r_out": r_out, "r_ret": r_ret,
                "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
                "m_at_asteroid": 0, "m_tps": 0}

    m_tps          = tps_frac * (m_payload_max + dry_return_kg)
    m_after_return = m_payload_max + dry_return_kg + m_tps
    m_return_prop  = m_after_return * (r_ret - 1.0)
    m_at_asteroid  = hardware_kg + dry_return_kg + m_tps + m_return_prop
    m_outbound_prop = m_at_asteroid * (r_out - 1.0)
    m_launch       = m_at_asteroid + m_outbound_prop

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
    }


# ─────────────────────────────────────────────────────────────────────────────
# OPERATIONAL-COSTS LOOKUP HELPER
# ─────────────────────────────────────────────────────────────────────────────
# Single-slot memo for the ops table.  mission_cost_usd pulls 9 line items per
# (vehicle × propellant) combo, so a 5,000-asteroid run at 11 vehicles × 7
# propellants issued ~2.5M full-DataFrame boolean scans of a 17-row table —
# 89% of Module 4's total runtime.  The table is loaded once per run and never
# mutated, so one dict build serves every lookup.
#
# Keyed by object identity, and the frame itself is held in the slot so its id
# can't be recycled onto a different object.  Single-slot (not a growing dict)
# so a long-lived session swapping ops tables can't leak.  A caller that
# mutates ops_df IN PLACE rather than rebinding would read a stale cache —
# rebuild by passing a fresh frame, which load_all_catalogs already does.
_OPS_CACHE: Tuple[Optional[pd.DataFrame], Dict[str, Optional[float]]] = (None, {})


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
    """
    val = _ops_table(ops_df).get(category)
    return default if val is None else val


# ─────────────────────────────────────────────────────────────────────────────
# MISSION COST CASCADE
# ─────────────────────────────────────────────────────────────────────────────
def mission_cost_usd(
    mass_cascade:        Dict[str, float],
    vehicle:             pd.Series,
    propellant:          pd.Series,
    ops_df:              pd.DataFrame,
    config:              CalcConfig,
    mission_duration_yr: float,
    processing_power_w:  float = 0.0,
) -> Dict[str, float]:
    """Full mission cost breakdown for a given (mass cascade, vehicle, prop).

    Uncrewed autonomous mining mission — no crew cost line.

    v1.3.2 accuracy fixes:
      • Heat-shield mass is now sourced from the rocket-eq cascade
        (mass_cascade["m_tps"]) instead of re-derived from payload only —
        the m_tps in the cascade is what actually got launched.
      • Launch insurance now percent of (launch + hardware) = SPACECRAFT
        book value rather than (launch + gross_value of future revenue),
        matching how real launch insurance is underwritten.
      • Capsule (`return_vehicle_dry_kg`) now carries its own recurring
        manufacturing cost — previously only mining_hardware was costed.
      • WACC compounding is time-bucketed: upfront costs compound at
        (1+W)^T, ongoing (ops + ISRU prop) at (1+W)^(T/2), end-of-mission
        (recovery) at 1.0.  Previous all-to-end overstated time-cost ~5%.

    Takes no payload or gross-value argument.  It used to take both, and
    v1.3.2 left them stranded: the insurance rebasing above removed the only
    read of gross_value_usd, and sample recovery became a flat Module 3 ops
    lookup rather than a per-kg charge, removing the only read of
    payload_returned_kg.  Every cost here now derives from the mass cascade,
    the Module 3 reference tables, and config — nothing scales with the
    revenue the mission is projected to earn, which is the point.

    Line items (every value sourced from Module 3's reference tables):
        UPFRONT     — launch, outbound prop, return prop (if not ISRU),
                      mining-rig hardware (amortised), capsule (per mission),
                      heat shield, NRE (bus + autonomy, amortised),
                      licensing, liability, launch insurance
        ONGOING     — mission ops × duration_yr, ISRU return prop (if ISRU)
        END-OF-MISSION — sample recovery
        × (1 + contingency_fraction)
        × per-bucket (1 + WACC)^T_bucket        [time-value]
    """
    cost_per_kg_prop = float(propellant["cost_usd_per_kg"])
    launch_cost      = float(mass_cascade["m_launch"]) * float(vehicle["usd_per_kg_to_leo"])

    outbound_prop_cost = float(mass_cascade["m_outbound_prop"]) * cost_per_kg_prop
    if config.use_isru_return_propellant:
        # ISRU prop is "ongoing" — manufactured at the asteroid over the
        # mining duration, not pre-paid upfront on Earth.
        return_prop_cost = float(mass_cascade["m_return_prop"]) * config.isru_processing_usd_per_kg
        return_prop_is_ongoing = True
    else:
        return_prop_cost = float(mass_cascade["m_return_prop"]) * cost_per_kg_prop
        return_prop_is_ongoing = False

    # Recurring hardware — split into the mining rig (one-way to asteroid,
    # AMORTISABLE across multi-mission programmes since the rig stays put)
    # and the return capsule (fresh per mission — fly-and-die).
    hw_per_kg               = _ops_value(ops_df, "Mining payload recurring cost", default=300_000.0)
    mining_rig_cost_total   = config.mining_hardware_kg * hw_per_kg
    mining_rig_cost         = mining_rig_cost_total / max(1, config.nre_amortization_missions)
    # v1.4.0: the capsule is priced off its OWN rate.  It used to be billed at
    # the mining-payload rate, which treats a parachute-and-heat-shield can as
    # though it were regolith-contact machinery.
    # v1.5.0: and which rate applies depends on where the cargo is going.  An
    # in-space delivery never re-enters, so it carries a passive berthing
    # adapter ($60k/kg) rather than a guided re-entry capsule ($150k/kg).
    # v1.6.0: a surface base needs a LANDER — throttleable descent engines,
    # legs, terminal guidance — which is more machine than either a passive
    # re-entry capsule or a berthing adapter.
    arch = delivery_architecture(config.delivery_destination)
    if arch.get("needs_lander"):
        capsule_per_kg = _ops_value(ops_df, "Surface lander recurring cost", default=200_000.0)
    elif arch["returns_to_earth"]:
        capsule_per_kg = _ops_value(ops_df, "Return capsule recurring cost", default=150_000.0)
    else:
        capsule_per_kg = _ops_value(ops_df, "Berthing adapter recurring cost", default=60_000.0)
    capsule_cost            = config.return_vehicle_dry_kg * capsule_per_kg   # per-mission
    # v1.5.0: the beneficiation plant's solar array, priced per installed Watt
    # off Module 3's power-system row.  Zero unless beneficiation is on — the
    # baseline rig's own power is already implicit in its $/kg recurring rate.
    power_per_w             = _ops_value(ops_df, "Power system (solar + battery)", default=800.0)
    power_system_cost       = max(0.0, float(processing_power_w)) * power_per_w
    hardware_cost           = mining_rig_cost + capsule_cost + power_system_cost

    # Mission ops × duration  (per-asteroid duration from Δv estimator)
    ops_per_year = _ops_value(ops_df, "Mission operations", default=31_400_000.0)
    ops_cost     = ops_per_year * mission_duration_yr

    # Heat shield — mass now comes from the actual cascade, not re-derived.
    tps_mass = float(mass_cascade.get("m_tps", 0.0))
    if tps_mass > 0:
        tps_per_kg       = _ops_value(ops_df, "Heat shield / TPS for Earth return", default=50_000.0)
        heat_shield_cost = tps_mass * tps_per_kg
    else:
        heat_shield_cost = 0.0

    # Recovery + regulatory flat costs.  v1.5.0: an in-space delivery replaces
    # the Earth recovery campaign (search aircraft, ships, range clearance,
    # clean-room convoy) with depot handover, and drops the re-entry half of
    # the Part 450 licence.
    if arch["returns_to_earth"]:
        recovery_cost  = _ops_value(ops_df, "Sample recovery operations",        default=15_000_000.0)
        licensing_cost = _ops_value(ops_df, "FAA Part 450 licensing compliance", default=2_500_000.0)
    else:
        recovery_cost  = _ops_value(ops_df, "Depot berthing & handover operations", default=2_000_000.0)
        licensing_cost = _ops_value(ops_df, "FAA Part 450 licensing (launch only)", default=1_200_000.0)
    liability_cost  = _ops_value(ops_df, "Third-party liability insurance",  default=1_500_000.0)

    # Launch insurance — percent of (launch + spacecraft book value).
    # Spacecraft book value at launch = recurring hardware cost (mining rig +
    # capsule).  Gross value of future revenue is NOT insured — insurance
    # underwriters cover replacement cost of the launched asset only.
    launch_ins_pct        = _ops_value(ops_df, "Launch insurance", default=10.0) / 100.0
    spacecraft_book_value = mining_rig_cost_total + capsule_cost
    launch_insurance_cost = launch_ins_pct * (launch_cost + spacecraft_book_value)

    # Spacecraft bus NRE amortised across N missions, less the share already
    # embedded in the per-kg recurring rate (v1.4.0 — see
    # nre_recurring_overlap_fraction).  NICM / SSCM per-kg brackets are
    # regressions on total program cost, so charging full OSIRIS-REx NRE on
    # top of a $300k/kg recurring rate books part of the development twice.
    nre_total   = _ops_value(ops_df, "Spacecraft development (NRE)", default=588_500_000.0)
    nre_overlap = min(max(config.nre_recurring_overlap_fraction, 0.0), 1.0)
    nre_cost    = nre_total * (1.0 - nre_overlap) / max(1, config.nre_amortization_missions)

    # Autonomous mining control & AI NRE — uncrewed-mission specific (Module 3
    # v1.2.4+ replaced the legacy 'Crew' line item with this).  Amortised the
    # same way as the bus NRE — once developed, the autonomy stack ships on
    # every subsequent identical mission.
    autonomy_nre_total = _ops_value(
        ops_df, "Autonomous mining control & AI (NRE)", default=200_000_000.0,
    )
    autonomy_nre_cost  = autonomy_nre_total / max(1, config.nre_amortization_missions)

    # ── Time-bucket every line item ──────────────────────────────────────────
    # UPFRONT = paid at year 0 (or earlier — NRE accumulates pre-launch but
    # treated as year-0 lump-sum here).
    # ONGOING = spread evenly over [0, T_mission] → effective year T/2.
    # END     = paid at year T_mission.
    upfront_lines = (
        launch_cost + outbound_prop_cost + hardware_cost + heat_shield_cost
        + licensing_cost + liability_cost + launch_insurance_cost
        + nre_cost + autonomy_nre_cost
        + (0.0 if return_prop_is_ongoing else return_prop_cost)
    )
    ongoing_lines = (
        ops_cost
        + (return_prop_cost if return_prop_is_ongoing else 0.0)
    )
    end_lines     = recovery_cost

    # Contingency reserve applied uniformly across buckets (it's a global
    # reserve fund, not tied to any one cost line).
    cont = 1.0 + config.contingency_fraction
    upfront_with_cont = upfront_lines * cont
    ongoing_with_cont = ongoing_lines * cont
    end_with_cont     = end_lines    * cont

    # WACC compounding — apply per bucket so end-of-mission costs aren't
    # wrongly inflated by the full duration's compounding factor.
    if config.apply_wacc_compounding:
        wacc          = _ops_value(ops_df, "Cost of capital (WACC)", default=0.10)
        mult_upfront  = (1.0 + wacc) ** mission_duration_yr
        mult_ongoing  = (1.0 + wacc) ** (mission_duration_yr / 2.0)
        mult_end      = 1.0
    else:
        wacc = 0.0
        mult_upfront = mult_ongoing = mult_end = 1.0

    total_cost = (
        upfront_with_cont * mult_upfront
        + ongoing_with_cont * mult_ongoing
        + end_with_cont     * mult_end
    )

    # Weighted-average WACC multiplier for diagnostic display
    pre_wacc_total = upfront_with_cont + ongoing_with_cont + end_with_cont
    wacc_multiplier = total_cost / pre_wacc_total if pre_wacc_total > 0 else 1.0

    subtotal         = upfront_lines + ongoing_lines + end_lines
    contingency_cost = subtotal * config.contingency_fraction

    return {
        "launch_cost":           launch_cost,
        "autonomy_nre_cost":     autonomy_nre_cost,
        "mission_duration_yr":   mission_duration_yr,
        "outbound_prop_cost":    outbound_prop_cost,
        "return_prop_cost":      return_prop_cost,
        "hardware_cost":         hardware_cost,
        "mining_rig_cost":       mining_rig_cost,        # amortised portion
        "capsule_cost":          capsule_cost,           # per-mission portion
        "power_system_cost":     power_system_cost,      # beneficiation plant
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


# ─────────────────────────────────────────────────────────────────────────────
# (VEHICLE × PROPELLANT) EVALUATOR FOR ONE ASTEROID
# ─────────────────────────────────────────────────────────────────────────────
def _evaluate_combo_at_ratio(
    asteroid_row:      pd.Series,
    vehicle:           pd.Series,
    propellant:        pd.Series,
    bulk_value_per_kg: float,
    dv_out_m_s:        float,
    dv_ret_m_s:        float,
    ops_df:            pd.DataFrame,
    config:            CalcConfig,
    best_phase_value_per_kg: Optional[float] = None,
    phases:            Optional[List[Tuple[str, float, float]]] = None,
    target_ratio:      float = 1.0,
    beneficiate:       Optional[bool] = None,
) -> Optional[Dict[str, float]]:
    """Evaluate one (vehicle × propellant) combination for one asteroid.

    Returns None if the combo is infeasible (zero return payload), or a
    full result dict including profit, ROI, $/kg returned, and the mass
    + cost cascades.
    """
    leo_cap = float(vehicle.get("payload_leo_kg", 0) or 0)
    if leo_cap <= 0:
        return None
    if best_phase_value_per_kg is None:
        best_phase_value_per_kg = bulk_value_per_kg
    if phases is None:
        phases = []

    # ── Low-thrust Δv penalty (v1.4.0) ───────────────────────────────────────
    # Module 3 tags each propellant with the factor by which a real trajectory
    # exceeds the impulsive Δv budget.  Electric propulsion cannot fly the
    # impulsive burns the reference table assumes — it spirals, and spiralling
    # out of LEO costs roughly twice what an impulsive escape does.  Without
    # this, a 3,000 s Isp thruster wins the mass cascade on a Δv budget it
    # could never actually achieve.
    dv_penalty = float(propellant.get("dv_penalty_factor", 1.0) or 1.0)
    dv_out_m_s = dv_out_m_s * dv_penalty
    dv_ret_m_s = dv_ret_m_s * dv_penalty

    # v1.5.0: TPS only exists if this architecture actually enters an
    # atmosphere.  A cislunar delivery never does, so asking for aerocapture
    # there yields a propulsive capture and no heat-shield mass.
    tps_frac = config.heat_shield_frac_of_payload if uses_tps(config) else 0.0

    # Cap the returned payload by what the asteroid can supply
    asteroid_mass = asteroid_row.get("estimated_mass_kg")
    if asteroid_mass is None or pd.isna(asteroid_mass) or asteroid_mass <= 0:
        return None
    mineable_kg = float(asteroid_mass) * config.max_mining_fraction

    # ── Power-plant feedback loop (v1.5.0, beneficiation only) ───────────────
    # The processing plant's array mass rides in the same rocket equation as
    # everything else, but its size depends on how much feed gets processed,
    # which depends on the payload, which depends on the array mass.  Solve
    # the fixed point instead of assuming it away.  Converges in 2-3 passes
    # because the array is a modest fraction of the rig.
    #
    # With beneficiation OFF no array mass is added at all — the existing
    # 2,000 kg rig figure already carries its own power implicitly, and this
    # keeps a default run bit-identical to v1.4.0.
    dig_wh   = _ops_value(ops_df, "Drilling / excavation energy", default=200.0)
    benef_wh = _ops_value(ops_df, "Beneficiation / on-site processing energy", default=500.0)
    base_w_per_kg = _ops_value(ops_df, "Power system specific mass", default=60.0)
    w_per_kg = solar_specific_power_w_per_kg(
        asteroid_row.get("semi_major_axis_au"), base_w_per_kg,
    )

    # `beneficiate` lets the caller price a NON-concentrating mission even
    # when the run has beneficiation enabled, so evaluate_combo can offer
    # "just scoop and go" as one of the options it chooses between.
    if beneficiate is None:
        beneficiate = config.use_beneficiation
    if not beneficiate:
        target_ratio = 1.0

    power_system_kg = 0.0
    processing_power_watts = 0.0
    cascade = None
    for _ in range(6):
        cascade = max_return_payload_kg(
            leo_capacity_kg = leo_cap,
            isp_s           = float(propellant["isp_vac_s"]),
            dv_out_m_s      = dv_out_m_s,
            dv_ret_m_s      = dv_ret_m_s,
            hardware_kg     = config.mining_hardware_kg + power_system_kg,
            dry_return_kg   = config.return_vehicle_dry_kg,
            tps_frac        = tps_frac,
            isru_return     = config.use_isru_return_propellant,
        )
        if not cascade["viable"]:
            return None
        if not beneficiate:
            break

        # Provisional payload for sizing purposes — the caps below refine it,
        # but the array only needs to be sized to the right order.
        trial_payload = min(cascade["max_payload_kg"], mineable_kg,
                            max_payload_by_throughput_kg(config))
        if trial_payload <= 0:
            return None
        trial_feed = min(trial_payload * target_ratio,
                         max_payload_by_throughput_kg(config), mineable_kg)
        trial_dur  = max(mining_duration_yr(trial_feed, config),
                         config.station_keeping_floor_yr)
        processing_power_watts = processing_power_w(
            trial_feed, trial_payload, trial_dur, dig_wh, benef_wh,
        )
        new_power_kg = processing_power_watts / w_per_kg if w_per_kg > 0 else 0.0
        if abs(new_power_kg - power_system_kg) <= 0.01 * max(new_power_kg, 1.0):
            power_system_kg = new_power_kg
            break
        power_system_kg = new_power_kg

    if cascade is None or not cascade["viable"]:
        return None
    hardware_total_kg = config.mining_hardware_kg + power_system_kg

    # ── Volume cap ───────────────────────────────────────────────────────────
    # Cargo volume = payload mass / bulk density.  Asteroid bulk density
    # (Module 1) is a fair proxy for the mined material's packing density
    # since the user spec'd "uniform composition".  A return capsule occupies
    # a fraction of the fairing — say 25% — when sharing the vehicle with
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
    # and compared here, but only as a reported flag — it now binds.
    bulk_density = asteroid_row.get("density_gcm3")
    if bulk_density is None or pd.isna(bulk_density) or float(bulk_density) <= 0:
        bulk_density = 2.0    # default: rocky-asteroid average
    bulk_density_kg_per_L = float(bulk_density)         # g/cm³ ≡ kg/L

    fairing_m3 = vehicle.get("fairing_volume_m3")
    fairing_m3 = float(fairing_m3) if fairing_m3 is not None and not pd.isna(fairing_m3) else 100.0
    usable_return_m3   = 0.25 * fairing_m3
    volume_capacity_kg = usable_return_m3 * 1000.0 * bulk_density_kg_per_L

    # `volume_fits` keeps its original sense — False means the payload the
    # mission would otherwise have returned does not fit — but the payload is
    # now actually reduced to what does fit.
    # ── Throughput cap (v1.4.0) ──────────────────────────────────────────────
    # You can only return what the rig can actually dig inside the maximum
    # stay.  Previously extraction was instantaneous and unbounded, so a
    # mission's haul was limited only by the rocket equation — the rig might
    # as well have been a vacuum cleaner with infinite suction.
    # v1.5.0: with beneficiation on, the throughput cap bounds the FEED the rig
    # digs, not the payload it flies home — that is the whole point of
    # concentrating.  With it off the semantics are unchanged: throughput caps
    # the payload directly.
    throughput_cap_kg = max_payload_by_throughput_kg(config)

    m_payload_demand = min(cascade["max_payload_kg"], mineable_kg)
    volume_fits      = m_payload_demand <= volume_capacity_kg
    throughput_fits  = m_payload_demand <= throughput_cap_kg
    if beneficiate:
        m_payload = min(m_payload_demand, volume_capacity_kg)
    else:
        m_payload = min(m_payload_demand, volume_capacity_kg, throughput_cap_kg)
    if m_payload <= 0:
        return None

    # ── Beneficiation mass balance ───────────────────────────────────────────
    # Concentrate exactly as far as it pays, and no further.  Once the
    # concentrate reaches the purity bound — 100% of the best phase present —
    # additional feed buys nothing: the delivered $/kg is already capped, while
    # the extra rock still costs dig time, energy, array mass and WACC.  A real
    # operator stops there, so the model does too.
    #
    #     ratio_to_saturate = best_phase / (bulk x recovery)
    #
    # then bounded by the safety cap, by what the rig can dig in the time
    # allowed, and by what the body can supply.  Where bulk value already
    # equals the best phase (a monomineralic body — pure ice, say) this
    # collapses to 1.0 and beneficiation correctly becomes a no-op.
    if beneficiate:
        feed_kg = min(m_payload * target_ratio, throughput_cap_kg, mineable_kg)
        feed_kg = max(feed_kg, m_payload)          # never less feed than product
        concentration_ratio = feed_kg / m_payload if m_payload > 0 else 1.0
        throughput_fits = feed_kg <= throughput_cap_kg
    else:
        feed_kg = m_payload
        concentration_ratio = 1.0

    return_volume_m3 = m_payload / bulk_density_kg_per_L / 1000.0

    # Recompute the full cascade at the capped payload.  TPS, return-prop,
    # outbound-prop, launch all depend on m_payload — must be redone to
    # reflect the actual mission, not the rocket-eq theoretical max.
    r_ret           = cascade["r_ret"]
    r_out           = cascade["r_out"]
    m_tps           = tps_frac * (m_payload + config.return_vehicle_dry_kg)
    m_after_return  = m_payload + config.return_vehicle_dry_kg + m_tps
    m_return_prop   = m_after_return * (r_ret - 1.0)
    m_at_asteroid   = (hardware_total_kg + config.return_vehicle_dry_kg + m_tps
                       + (0.0 if config.use_isru_return_propellant else m_return_prop))
    m_outbound_prop = m_at_asteroid * (r_out - 1.0)
    m_launch        = m_at_asteroid + m_outbound_prop

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
    }

    # ── Delivered $/kg — the best load assemblable from this rock ────────────
    # Not "go and fetch platinum": fill the hold with the most valuable phases
    # the target actually contains, in whatever ratio maximises the load.  The
    # two honest bounds fall out of the knapsack automatically — you cannot
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
    # of it, and that stay time flows into ops cost and WACC.
    mining_yr           = mining_duration_yr(feed_kg, config)
    mission_duration_yr = asteroid_mission_duration_yr(
        dv_out_m_s, dv_ret_m_s, config, mining_yr=mining_yr,
    )
    # Re-derive the plant's power at the final feed / payload / duration so the
    # cost matches the mission actually flown, not the sizing pass.
    if beneficiate:
        processing_power_watts = processing_power_w(
            feed_kg, m_payload, mining_yr, dig_wh, benef_wh,
        )
    cost                = mission_cost_usd(
        mass_cascade        = actual_cascade,
        vehicle             = vehicle,
        propellant          = propellant,
        ops_df              = ops_df,
        config              = config,
        mission_duration_yr = mission_duration_yr,
        processing_power_w  = processing_power_watts,
    )

    profit               = gross_value - cost["total_cost"]
    roi                  = profit / cost["total_cost"] if cost["total_cost"] > 0 else np.nan
    usd_per_kg_cost      = cost["total_cost"] / m_payload if m_payload > 0 else np.nan

    arch = delivery_architecture(config.delivery_destination)
    return {
        "vehicle":              vehicle["name"],
        "propellant":           propellant["name"],
        "delivery_destination": config.delivery_destination,
        "delivery_arch":        arch["label"],
        "returns_to_earth":     arch["returns_to_earth"],
        "flies_tps":            tps_frac > 0.0,
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
        # True when the concentrate is at the purity ceiling — i.e. grade, not
        # processing capacity, is what limits the delivered value.  Compared
        # against the delivered figure itself (with a relative tolerance)
        # rather than re-deriving it, so a feed clipped by throughput or by
        # the body's own mass reports honestly as NOT saturated.
        "purity_bound_binds":       bool(
            beneficiate
            and best_phase_value_per_kg > 0
            and delivered_value_per_kg >= best_phase_value_per_kg * (1.0 - 1e-9)
        ),
        "processing_power_w":       processing_power_watts,
        "power_system_kg":          power_system_kg,
        "power_w_per_kg_at_target":  w_per_kg,
        "hardware_total_kg":        hardware_total_kg,
        "return_bulk_density_kg_per_L": bulk_density_kg_per_L,
        "return_volume_m3":     return_volume_m3,
        "fairing_volume_m3":    fairing_m3,
        "volume_fits":          volume_fits,
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
        # Cost breakdown — per-line items
        "launch_cost_usd":           cost["launch_cost"],
        "outbound_prop_cost_usd":    cost["outbound_prop_cost"],
        "return_prop_cost_usd":      cost["return_prop_cost"],
        "hardware_cost_usd":         cost["hardware_cost"],
        "mining_rig_cost_usd":       cost["mining_rig_cost"],   # amortised
        "capsule_cost_usd":          cost["capsule_cost"],      # per mission
        "power_system_cost_usd":     cost["power_system_cost"],
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
    asteroid_row:      pd.Series,
    vehicle:           pd.Series,
    propellant:        pd.Series,
    bulk_value_per_kg: float,
    dv_out_m_s:        float,
    dv_ret_m_s:        float,
    ops_df:            pd.DataFrame,
    config:            CalcConfig,
    best_phase_value_per_kg: Optional[float] = None,
    phases:            Optional[List[Tuple[str, float, float]]] = None,
) -> Optional[Dict[str, float]]:
    """Best mission for one (asteroid × vehicle × propellant), profit-maximising
    over how hard to concentrate.

    Without beneficiation there is nothing to choose: one solve at ratio 1.0.

    With it, the concentration ratio is a genuine economic decision rather
    than a setting.  Digging more feed raises the grade of the load — but the
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
        phases=phases, target_ratio=r, beneficiate=b,
    )

    if not config.use_beneficiation:
        return solve(1.0, False)

    # Baseline: don't concentrate at all.  Not the same as concentrating at
    # ratio 1.0 — that would still pay the separation recovery loss, the
    # processing energy and the array mass for no grade improvement.
    # Including it makes beneficiation an OPTION rather than an obligation,
    # so the answer can never be worse than simply scooping and leaving.
    best = solve(1.0, False)
    best_profit = best["profit_usd"] if best is not None else -np.inf
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
        if res is not None and res["profit_usd"] > best_profit:
            best_profit, best, best_r = res["profit_usd"], res, r

    # One refinement pass around the winner, on the same geometric spacing.
    if best is not None and n > 2:
        step = r_max ** (1.0 / (n - 1))
        for r in (best_r / (step ** 0.5), best_r * (step ** 0.5)):
            if not (1.0 <= r <= r_max):
                continue
            res = solve(r)
            if res is not None and res["profit_usd"] > best_profit:
                best_profit, best = res["profit_usd"], res
    return best


def candidate_combos(
    catalogs: Dict[str, pd.DataFrame],
    config:   CalcConfig,
) -> List[Tuple[pd.Series, pd.Series]]:
    """Every (vehicle, propellant) pair that passes the CalcConfig filters.

    The filters depend only on `config`, never on the asteroid, so the whole
    cross-join is built once per run and reused for every row.  Doing it
    inside the per-asteroid loop re-ran two DataFrame copies plus ~88
    `iterrows()` Series constructions for each of N asteroids.
    """
    vdf = catalogs["vehicles"]
    if config.operational_vehicles_only and "status" in vdf.columns:
        vdf = vdf[vdf["status"] == "operational"]
    if config.candidate_vehicles is not None:
        vdf = vdf[vdf["name"].isin(config.candidate_vehicles)]

    pdf = catalogs["propellants"]
    if config.candidate_propellants is not None:
        pdf = pdf[pdf["name"].isin(config.candidate_propellants)]

    propellant_rows = [row for _, row in pdf.iterrows()]
    return [
        (vehicle, propellant)
        for _, vehicle in vdf.iterrows()
        for propellant in propellant_rows
    ]


def evaluate_asteroid(
    asteroid_row: pd.Series,
    catalogs:     Dict[str, pd.DataFrame],
    config:       CalcConfig,
    combos:       Optional[List[Tuple[pd.Series, pd.Series]]] = None,
) -> Optional[dict]:
    """Pick the highest-profit (vehicle × propellant) combo for one asteroid.

    Returns a single result dict (best combo) or None if no combo is viable.

    `combos` is the precomputed candidate cross-join from candidate_combos().
    Left as None it is rebuilt per call — correct but slow, so the main loop
    builds it once and passes it in.
    """
    minerals = catalogs["minerals"]
    ops_df   = catalogs["ops"]

    # Bulk $/kg for this asteroid's blended composition
    bulk_value = asteroid_bulk_value_usd_per_kg(asteroid_row, minerals)
    if bulk_value <= 0:
        return None
    # Purity bound for beneficiation — the richest concentrate obtainable.
    # Computed once per asteroid rather than per combo; it depends only on
    # composition and prices.
    # Phase table for the load optimiser, and the purity ceiling for reporting.
    # Both depend only on composition and prices, so compute once per asteroid
    # rather than once per (vehicle x propellant) combo.
    if config.use_beneficiation:
        phases           = asteroid_phase_table(asteroid_row, minerals)
        best_phase_value = asteroid_best_phase_usd_per_kg(asteroid_row, minerals)
    else:
        phases           = []
        best_phase_value = bulk_value

    dv_out, dv_ret = asteroid_dv_m_s(asteroid_row, config)

    if combos is None:
        combos = candidate_combos(catalogs, config)

    # Keep the highest-profit candidate
    best       = None
    best_profit = -np.inf
    for vehicle, propellant in combos:
        result = evaluate_combo(
            asteroid_row, vehicle, propellant,
            bulk_value, dv_out, dv_ret,
            ops_df, config,
            best_phase_value_per_kg=best_phase_value,
            phases=phases,
        )
        if result is None:
            continue
        if result["profit_usd"] > best_profit:
            best_profit = result["profit_usd"]
            best        = result

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
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def build_profitability_catalog(config: CalcConfig = CALC_CONFIG) -> pd.DataFrame:
    """Run the full Module 4 calculation pipeline."""
    t0 = datetime.now()
    print("=" * 75)
    print("  💰  PROFITABILITY PIPELINE — MODULE 4")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  v{config.pipeline_version}")
    print("=" * 75)

    # ── Step 1 — Load catalogs ───────────────────────────────────────────────
    catalogs = load_all_catalogs(config)

    # ── Step 2 — Integrity checks ────────────────────────────────────────────
    integrity_check(catalogs)
    destination_check(catalogs, config)

    # ── Step 3 — Iterate asteroids ───────────────────────────────────────────
    asteroids = catalogs["asteroids"]

    # Filter to rows with the minimum data needed to be evaluable
    needed_cols = ["estimated_mass_kg", "comp_metal_fraction",
                   "comp_silicate_fraction", "comp_carbon_fraction",
                   "comp_ice_fraction"]
    missing_cols = [c for c in needed_cols if c not in asteroids.columns]
    if missing_cols:
        print(f"\n❌  Asteroid catalog missing required columns: {missing_cols}")
        print("     Has Module 1 been re-run with enrich_composition?  Aborting.")
        return pd.DataFrame()

    mass_ok = pd.to_numeric(asteroids["estimated_mass_kg"], errors="coerce") > 0
    work_df = asteroids[mass_ok].copy()
    print(f"\n🪐  Evaluating {len(work_df):,} asteroids with positive mass "
          f"(skipped {len(asteroids) - len(work_df):,} without)")

    if config.eval_row_cap and len(work_df) > config.eval_row_cap:
        work_df = work_df.head(config.eval_row_cap)
        print(f"     ✂️   Capped at {config.eval_row_cap:,} rows for this run "
              f"(eval_row_cap in CALC_CONFIG)")

    # Candidate (vehicle × propellant) grid is config-driven, not asteroid-
    # driven — build it once and hand it to every evaluation.
    combos = candidate_combos(catalogs, config)
    if not combos:
        print("\n❌  No candidate vehicle × propellant combinations after "
              "filtering — check operational_vehicles_only / candidate_* in CALC_CONFIG.")
        return pd.DataFrame()
    print(f"     🔧  {len(combos):,} vehicle × propellant combinations per asteroid")

    n = len(work_df)
    results = []
    last_report = 0
    for i, (_, asteroid) in enumerate(work_df.iterrows(), 1):
        result = evaluate_asteroid(asteroid, catalogs, config, combos)
        if result is not None:
            results.append(result)
        # Lightweight progress report every ~10%
        if n >= 100 and (i * 10) // n != last_report:
            last_report = (i * 10) // n
            print(f"     … {i:,} / {n:,} evaluated  ({last_report * 10}%)")

    if not results:
        print("\n❌  No viable evaluations — every asteroid failed.")
        return pd.DataFrame()

    df = pd.DataFrame(results)

    # ── Step 4 — Rank + tag ──────────────────────────────────────────────────
    df["catalog_date"]     = t0.strftime("%Y-%m-%d")
    df["pipeline_version"] = config.pipeline_version
    df = df.sort_values("profit_usd", ascending=False).reset_index(drop=True)

    # Sanity flags for downstream
    df["viable"]      = df["profit_usd"] > 0
    df["profit_M$"]   = df["profit_usd"] / 1e6   # for human-readable preview
    df["gross_M$"]    = df["gross_value_usd"] / 1e6
    df["cost_M$"]     = df["total_cost_usd"] / 1e6

    # ── Step 5 — Export ──────────────────────────────────────────────────────
    out_path = os.path.join(config.output_dir, config.output_filename)
    df.to_csv(out_path, index=False)
    print(f"\n     💾  Profitability catalog → {out_path}  ({len(df):,} rows)")

    n_viable = int(df["viable"].sum())
    elapsed  = (datetime.now() - t0).total_seconds()
    print("\n" + "=" * 75)
    print("  ✅  PROFITABILITY ANALYSIS COMPLETE")
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

    regex=False — designations and names carry regex metacharacters ("(1)
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


print("\n✅  Helper utilities available:")
print("    top_profitable(catalog, 20)")
print("    filter_viable(catalog)")
print("    lookup_asteroid(catalog, 'Bennu')")




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

    One exception: set the delivery destination HERE, not on a sub-config —

        MASTER_CONFIG.delivery_destination = "cislunar"

    Stage 2 and Stage 4 each carry a delivery_destination, and they must
    agree: Stage 2 decides what a kilogram sells for, Stage 4 decides the
    architecture that puts it there.  Setting them apart prices the cargo at
    a depot while paying to land it in Utah.  This property writes both.
    """
    output_dir: str = _DEFAULT_OUTPUT_DIR

    @property
    def delivery_destination(self) -> str:
        """Where the mined material is sold — 'earth_surface', 'leo', 'cislunar'."""
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
print("  ⚙️   MASTER CONFIG READY")
print(f"      Pipeline output  : {MASTER_CONFIG.output_dir}")
print(f"      JPL limit        : {MASTER_CONFIG.catalog.jpl_limit:,} asteroids")
print(f"      Eval row cap     : {MASTER_CONFIG.calc.eval_row_cap:,}")
print(f"      Delivery dest    : {MASTER_CONFIG.delivery_destination}")
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
    print("  🚀  MASTER ASTEROID PROFITABILITY PIPELINE — v1.7.0")
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
