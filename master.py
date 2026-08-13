# -*- coding: utf-8 -*-
"""Master Asteroid Profitability Pipeline (1.20.3)

End-to-end SELF-CONTAINED pipeline that combines all four modules into a
single runnable file.  Copy-paste into Colab / Jupyter / your script and
run top-to-bottom — the orchestrator at the bottom executes everything.

    Stage 1  →  Asteroid Catalog        (modules/catalog.py 1.1.0)
                JPL SBDB + MP3C + SsODNet + NEOWISE
                + PGM_ENRICHMENT_BY_TYPE per-spectral-type factors
    Stage 2  →  Mineral Value Catalog   (modules/mineral_value.py 1.7.0)
                yfinance live + USGS/LME reference + mineralogy
                + sperrylite / laurite / awaruite / native-pgm phases
                + destination pricing for EVERY commodity
    Stage 3  →  Transportation Data     (modules/transportation.py 1.11.0)
                Launch vehicles + propellants + Δv segments + ops costs
                (UNCREWED autonomous mining — no crew costs)
    Stage 4  →  Profitability Calc      (modules/calc.py 1.14.0)
                Rocket eq cascade + cost cascade + per-asteroid ranking
                + PGM enrichment applied per asteroid (M-type 2×, V-type 0.2×)
                + delivery architecture: earth_surface / leo / cislunar /
                  lunar_surface / mars_surface, beneficiation,
                  low-thrust trip time, launch windows, learning curve,
                  market saturation, rig service life + terminal value,
                  mission reliability + growth, cryogenic boil-off,
                  in-space manufacturing

Mission profile: UNCREWED autonomous mining spacecraft throughout (no
crew costs, no life-support overhead).

DELIVERY DESTINATION — set MINERAL_CONFIG.delivery_destination and
CALC_CONFIG.delivery_destination TO THE SAME VALUE.  Stage 2 decides what a
kilogram sells for; Stage 4 decides what it costs to put it there, and the
answer is only meaningful when they agree.  Stage 4 checks and warns.

Output tree (under MASTER_CONFIG.output_dir):
    asteroid_catalog.csv               ← Stage 1 (~0.88 GB at the 1.55 M-row
                                          default; set catalog.jpl_limit lower)
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
        MASTER_CONFIG.calc.use_isru_return_propellant (make ISRU available)
        MASTER_CONFIG.calc.optimise_architecture_per_asteroid
                                                    (search return mode + ISRU
                                                     per target; ~2x runtime)
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
# SPAWNED-WORKER QUIET MODE
# ─────────────────────────────────────────────────────────────────────────────
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
from typing import Dict, Optional, Tuple

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
    # ONE CAP PER SOURCE, and 0 means "no cap — take the whole table".
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
    # want a fast interactive run — 50_000 reproduces the pre-v1.1.0 behaviour.
    jpl_limit:       int = 0   # 0 = all 1.55 M asteroids (orbital elements)
    ssodnet_limit:   int = 0   # 0 = whole cached ssoBFT table
    neowise_limit:   int = 0   # 0 = all 183 k NEOWISE rows
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
    # population goes from ~139 k to ~1.55 M — an 11x larger catalog whose extra
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
    # 1.0.9 — SsODNet was being fetched and then thrown away.  ssoBFT renamed
    #         its identity columns (sso_number/sso_name/sso_id → number/name/
    #         id), the column projection tolerated the loss, and merge_sources
    #         then dropped the whole source for having no `designation`.  A
    #         ~500 MB download and every literature diameter, density,
    #         rotation and TAXONOMY in it went in the bin, silently, behind
    #         one ⚠️ line.  Six more columns had drifted with it:
    #             perihelion            → periapsis_distance
    #             aphelion              → apoapsis_distance
    #             perihelion_argument   → periapsis_argument
    #             absolute_magnitude.value → absolute_magnitude.H.value
    #             spins.<1..3>.period.value → spins.period.value (now a LIST)
    #         Three separate things kept it quiet, all now fixed:
    #           • the drift warning only fired when <5 of 24 columns matched.
    #             14 matched, so losing every merge key read as healthy.  It
    #             now always reports, and _SSODNET_REQUIRED makes the identity
    #             columns fatal for the source instead of silently useless.
    #           • the row-cap sort key `sso_number` sat behind an
    #             `if in df.columns` guard, so truncation silently stopped
    #             sorting and took an arbitrary 50,000 rows starting near
    #             asteroid 367488 rather than Ceres.  Sort key is now required.
    #           • pq.ParquetFile.schema is the PHYSICAL schema, which names a
    #             nested list column by its inner path, so `spins.period.value`
    #             read as absent.  Membership is tested against schema_arrow,
    #             which is what read(columns=…) actually accepts.
    #         EFFECT — this changes the evaluated population, so it changes
    #         every downstream number.  Same run, sources otherwise identical
    #         (JPL 50k, NEOWISE 50k, MP3C unreachable):
    #             catalog entries            35,098 →  35,807
    #             taxonomy MEASURED           1,854 →  24,675
    #                 (source + tholen; was 1,358 + 496)
    #             taxonomy GUESSED from albedo 33,235 → 11,131
    #             density measured                0 →     438
    #             V-type bodies               3,988 →   2,614
    #         The V-type count is the tell that the old catalog was wrong:
    #         V-types are rare, and 3,988 of them was an artefact of guessing
    #         taxonomy from albedo.  Verified against literature after the
    #         fix — Ceres 939.4 km / 2.162 g/cm³ / 9.074 h / C, Vesta 522.8 /
    #         3.411 / 5.342 h / V, Pallas B, Psyche X, Eros 5.27 h / S.
    #         Any CSV stamped 1.0.8 or earlier was built on the degraded
    #         catalog — re-run rather than trusting it.
    # 1.1.0 — POPULATION RELEASE.  Three things, all of which change how many
    #         asteroids exist downstream, so every number moves.
    #
    #         (a) NEOWISE was contributing NOTHING, silently.  IRSA returns
    #             `asteroid_number` as float64 whenever the result slice holds
    #             any unnumbered body, so `.astype("string")` built the
    #             designation "3.0" rather than "3".
    #             _extract_canonical_designation matches neither `^(\d+)\s*$`
    #             nor `^(\d+)\s+[A-Z][a-z]` against "3.0", so it passed the
    #             value through unchanged and the merge key could never equal
    #             JPL's "3".  Every NEOWISE row then died at validation for
    #             having no semi-major axis.  The tell in a committed CSV is
    #             all seven neowise_* columns present and 100% empty while the
    #             fetcher printed "✅ 183,408 records fetched".
    #             SCALE-DEPENDENT AND THEREFORE INVISIBLE: at a small cap the
    #             slice is all-numbered, the dtype is int64, and it works.  It
    #             broke at exactly the row counts nobody spot-checks.
    #             Fixed at the source (format the number as an integer) and
    #             defensively in _extract_canonical_designation, which now
    #             strips a trailing ".0" from any source.
    #             Population effect is small — JPL SBDB already ingests NEOWISE
    #             diameters, so this recovers only 27 bodies JPL lacks — but it
    #             restores IR albedo, beaming parameter and diameter
    #             uncertainties for ~132,700 bodies that had none.
    #
    #         (b) ONE ROW CAP PER SOURCE, and 0 now means unlimited.  A single
    #             shared `jpl_limit` capped four sources that each take their
    #             lowest-numbered N bodies, so the sources overlapped almost
    #             perfectly and the union was ~N rather than 4N.  See the
    #             FETCH LIMITS block.  Defaults are now unlimited.
    #
    #         (c) DIAMETER DERIVED FROM H where none was measured, gated behind
    #             `derive_diameter_from_h`.  See DERIVED DIAMETERS above and
    #             ALBEDO_BY_SPECTRAL_TYPE / ALBEDO_BY_SEMI_MAJOR_AXIS_AU below.
    #
    #         EFFECT, measured 2026-08-08 against the live APIs:
    #             JPL asteroids available            1,554,321
    #             ...with a MEASURED diameter          139,582
    #             ...with H and a valid orbit        1,553,812
    #             catalog at jpl_limit=200,000          89,367  (v1.0.9)
    #             catalog, measured diameters only     ~139,600  (v1.1.0, gate off)
    #             catalog, H-derived enabled         ~1,553,800  (v1.1.0, default)
    #         Any CSV stamped 1.0.9 or earlier was built on at most 89,367
    #         bodies and is not comparable row-for-row with a 1.1.0 run.
    pipeline_version: str = "1.1.0"


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
      f"{'on — bodies with no measured diameter are sized from H + albedo' if CATALOG_CONFIG.derive_diameter_from_h else 'off — measured diameters only'}")


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
    # H — absolute magnitude.  Added in v1.1.0 and it is the single highest-
    # coverage physical field in the whole pipeline: 1,553,817 of JPL's
    # 1,554,321 asteroids carry one, against 139,582 with a diameter.  Every
    # other source already supplied `absolute_magnitude_h`, so the backbone was
    # the one place it was missing and derive_missing_diameters() needs it on
    # exactly the rows the other sources never reach.
    "H",
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
    _SAFE_FIELDS = "pdes,name,spkid,neo,pha,diameter,diameter_sigma,albedo,rot_per,e,a,q,ad,i,om,w,ma,per,n,H"

    base_params = {
        "sb-kind":   "a",           # asteroids only
        "full-prec": "true",
        # NOTE: sb-cond removed — the '>' operator encoding caused HTTP 400.
        #       Filtering by diameter > 0 is handled in Python (validate_and_filter).
    }

    # `limit` is OMITTED entirely when the cap is 0.  SBDB has no server-side
    # maximum — it returns all 1,554,321 asteroids for ~435 MB in ~80 s — and
    # sending `limit=0` would be read as a literal zero-row request rather than
    # as "no limit".
    if config.jpl_limit:
        base_params["limit"] = config.jpl_limit
    else:
        print("     ℹ️   No row cap — requesting the full SBDB asteroid table "
              "(~1.55 M rows, ~435 MB).  Set CATALOG_CONFIG.jpl_limit for a faster run.")

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

    # Pre-clean: "3.0" → "3".  A float-typed identifier column stringified by
    # pandas is the single most likely way a caller hands us a broken key, and
    # it is silent — "3.0" is not null, so nothing downstream complains; it just
    # never joins.  That is exactly how NEOWISE contributed zero rows to every
    # large run before v1.1.0 (see fetch_neowise).  Only a trailing .0 (or .000)
    # is stripped, so a genuine identifier is never truncated.
    cleaned = cleaned.str.replace(r"^(\d+)\.0+$", r"\1", regex=True)

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
    print("\n🔭  MP3C — Minor Planet Physical Properties Catalogue …")

    # Both MP3C transports need a number in the query — neither has an
    # "everything" form — so an unlimited (0) config becomes a ceiling larger
    # than the catalogue rather than a missing clause.
    mp3c_rows = config.mp3c_limit or _MP3C_UNLIMITED_ROWS

    # ── Attempt 1: REST endpoints ────────────────────────────────────────────
    for endpoint_tpl in _MP3C_REST_ENDPOINTS:
        url = endpoint_tpl.format(limit=mp3c_rows)
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
# Schema notes (parquet column names use dotted paths — 244 cols as of the
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
#   Rotation:  spins.period.value — a LIST column (one row holds every ranked
#              solution); we take the first non-null element.
#
# ⚠️  THE IDENTITY COLUMNS WERE RENAMED (v1.0.9).  ssoBFT used to ship
# `sso_id` / `sso_number` / `sso_name`; it now ships `id` / `number` / `name`.
# Because the projection silently drops columns it cannot find, the fetcher
# went on returning 50,000 rows with NO merge key, and `merge_sources` then
# discarded the entire source with a one-line warning — for a ~500 MB download
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

# Without these three the frame cannot be merged — `merge_sources` keys on
# `designation`, which is built from `number` falling back to `name`.  Losing
# them silently is the failure documented above, so the fetcher treats their
# absence as fatal for this source rather than returning a useless frame.
_SSODNET_REQUIRED = ["number", "name"]

_SSODNET_RENAME = {
    # Identity:
    #   number  → numeric IAU number (e.g. 1 for Ceres).  Used as our merge
    #             key (designation).  Nullable — unnumbered bodies fall back
    #             to `name`.
    #   name    → human-readable name ("Ceres").
    #   id      → IMCCE's quaero-resolved canonical identifier; for numbered
    #             asteroids this is the name string, for unnumbered it's the
    #             provisional designation.  Kept as `ssodnet_id` so a user can
    #             round-trip back to the SsODNet REST API
    #             (ssp.imcce.fr/.../ssocard/<ssodnet_id>).
    # These were sso_number / sso_name / sso_id before the 2026-08 schema
    # change — see the ⚠️ note above before "fixing" them back.
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
    # spins.period.value handled separately below — the list is reduced to a
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
            # schema_arrow, NOT schema.  The parquet PHYSICAL schema flattens a
            # list column into its inner path, so `spins.period.value` is absent
            # from pf.schema.names while present in pf.schema_arrow.names — and
            # read(columns=…) expects the arrow-level name.  Testing membership
            # against the physical schema silently drops every nested column.
            schema_names = set(pf.schema_arrow.names)
            cols = [c for c in _SSODNET_WANTED if c in schema_names]
            missing = [c for c in _SSODNET_WANTED if c not in schema_names]
            if missing:
                # SsODNet renames flattened columns between releases, so a few
                # misses are normal and tolerable.  Say which, at every scale —
                # the old code only spoke up when fewer than 5 columns matched,
                # which is exactly why a release that renamed the IDENTITY
                # columns (and 6 others) passed for healthy: 14 still matched.
                print(f"     ℹ️   Schema drift: {len(cols)}/{len(_SSODNET_WANTED)} "
                      f"columns matched, missing {missing}")
            absent_required = [c for c in _SSODNET_REQUIRED if c not in schema_names]
            if absent_required:
                print(f"     ❌  ssoBFT schema is missing the merge key(s) "
                      f"{absent_required} — cannot build `designation`, so every "
                      f"row would be dropped at merge time.  Skipping SsODNet.")
                print(f"         Inspect the real schema and update "
                      f"_SSODNET_WANTED / _SSODNET_RENAME:")
                print(f"         py -c \"import pyarrow.parquet as pq; "
                      f"print(pq.ParquetFile(r'{cache_path}').schema_arrow.names)\"")
                return pd.DataFrame()
            df = pf.read(columns=cols).to_pandas()
        else:
            df = pd.read_parquet(cache_path)
            absent_required = [c for c in _SSODNET_REQUIRED if c not in df.columns]
            if absent_required:
                print(f"     ❌  ssoBFT schema is missing the merge key(s) "
                      f"{absent_required} — skipping SsODNet.")
                return pd.DataFrame()
            df = df[[c for c in _SSODNET_WANTED if c in df.columns]]
    except Exception as exc:
        print(f"     ❌  Parquet read failed: {type(exc).__name__}: {exc}")
        return pd.DataFrame()

    if df.empty:
        print("     ⚠️  Parquet returned 0 rows")
        return pd.DataFrame()

    # Cap to config.jpl_limit so SsODNet doesn't dominate runtime on small runs.
    # NB: full table is ~1.2 M rows; trimming here keeps merge / dedup fast.
    # IMPORTANT: sort by `number` ASC first so a small-N run gets the LOWEST
    # IAU numbers (Ceres=1, Pallas=2, Juno=3, Vesta=4, …) — the most famous
    # bodies — rather than whatever arbitrary order the parquet stores rows in.
    # Unnumbered bodies (number = NaN) are sorted to the end via na_position.
    #
    # This silently stopped working when the column was renamed from
    # `sso_number`: the guard skipped the sort, and the run took an arbitrary
    # 50,000 rows starting around asteroid 367488 instead of Ceres.  The sort
    # key is required now, so the guard cannot silently no-op again.
    if config.ssodnet_limit and len(df) > config.ssodnet_limit:
        df = df.sort_values("number", ascending=True, na_position="last")
        df = df.head(config.ssodnet_limit).copy()
        print(f"     ✂️   Truncated to first {config.ssodnet_limit:,} rows by number ASC")

    # Reduce the ranked spin solutions to a single rotation_period_h column.
    # ssoBFT used to expose them as `spins.<1..3>.period.value` scalars and now
    # ships ONE list column holding every solution for the body, best rank
    # first.  Take the first non-null element — same "best rank wins, lower
    # ranks fill the gap" behaviour as before, expressed over a list.
    if "spins.period.value" in df.columns:
        def _first_period(v) -> float:
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

    # ADQL.  `neowise_limit` caps the pull; 0 drops the TOP clause and takes the
    # whole table, which is only ~183 k rows / ~19 MB / ~30 s — small enough
    # that capping it buys almost nothing and costs measured diameters.
    # WHERE clause filters comets server-side and skips rows without ANY
    # identifier — saves bandwidth and avoids a useless dedup pass later.
    # ORDER BY asteroid_number so small-N runs include the low-numbered
    # (most famous) bodies — Ceres, Vesta, etc.
    top = f"TOP {int(config.neowise_limit)} " if config.neowise_limit else ""
    adql = (
        f"SELECT {top}{_NEOWISE_SELECT} "
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
    #
    # ⚠️  `asteroid_number` MUST be rendered as an integer, and this is not a
    # cosmetic point — it is the bug that made this entire source a no-op for
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
            print(f"     🚨  {name} fetched {n_raw:,} rows and NONE survived "
                  f"keying — its `designation` column is unusable, so the whole "
                  f"source is about to contribute nothing.  This is a BUG in "
                  f"fetch_{name.split()[0].lower()}, not an empty upstream table.")

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
        # How many of this source's keys the backbone already knows.  Reported
        # because it is the one number that separates "the source is fine and
        # simply overlaps" from "the source's keys join nothing" — a supplement
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

        print(f"     ✔   Merged {src_name}: {len(supp):,} supplement records "
              f"({overlap:,} matched the backbone, +{new_rows:,} new entries)")
        if len(supp) and not overlap:
            print(f"     🚨  {src_name} matched ZERO backbone designations. "
                  f"Every one of its {len(supp):,} rows entered as a new body "
                  f"with no orbital elements, and validation will drop them "
                  f"all.  Check how fetch_* builds `designation` — a float-typed "
                  f"identifier stringifies to \"3.0\" and joins nothing.")

    # Final post-merge dedup — keeps the most-complete row in each group.
    merged = deduplicate_catalog(merged, key="designation", label="post-merge")

    print(f"     ✅  Combined catalog: {len(merged):,} rows × {len(merged.columns)} columns")
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# DERIVED DIAMETERS  (v1.1.0)
# ─────────────────────────────────────────────────────────────────────────────
#
# validate_and_filter drops any body with no diameter, and that single rule is
# what has bounded this pipeline's population since v1.0.0.  Of JPL's 1,554,321
# asteroids only 139,582 have a measured diameter — 9.0%.  1,553,817 have an
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
# those measurements are overwhelmingly NEOWISE — a thermal-infrared survey.
# At a fixed H a darker body must be larger, and a larger warmer body is easier
# for a thermal survey to detect, so the measured sample over-represents dark
# bodies relative to the 1.4 M that were never measured.  A median that is too
# LOW yields a diameter that is too LARGE and a mass that is too large by the
# 1.5 power.  Do not "correct" this by raising the table to taste — that is the
# same move CLAUDE.md rejects for IN_SPACE_UTILITY.  Quantifying it needs a
# debiased size-frequency model, which this module does not have.

# Median measured geometric albedo per spectral type.  DERIVED, not asserted:
# computed 2026-08-08 over every JPL SBDB asteroid with 0 < albedo < 1 and a
# Bus-DeMeo (spec_B) or, failing that, Tholen (spec_T) classification — 1,897
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
# bin — which will be far too dark for an enstatite surface (real E-types run
# p_V ~ 0.4-0.5) and will size the body much too large.  It is left absent
# rather than filled from literature so that the table stays one thing —
# medians over this catalog — instead of a mixture nobody can audit.  E-types
# with a MEASURED albedo are unaffected, and that is most of the ones that
# matter.  Same applies to G and R.

# Median measured geometric albedo by semi-major axis, same 138,437-body
# sample.  THIS is the branch that actually sizes the catalog: a body with a
# taxonomy almost always has a diameter too, so the taxonomy table above fires
# rarely, while ~1.4 M bodies have nothing but H and an orbit.
#
# The gradient is the well-known compositional zoning of the belt — S-complex
# inner, C-complex outer — and it is strong enough to be worth binning for:
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

# Overall median across the whole measured sample.  Last resort only — used for
# a body with no albedo, no usable taxonomy and no semi-major axis, which in
# practice cannot happen because validate_and_filter requires an orbit anyway.
ALBEDO_FALLBACK = 0.0780

# D_km = _H_DIAMETER_CONSTANT / sqrt(p_V) * 10**(-H/5)
_H_DIAMETER_CONSTANT = 1329.0


def _albedo_for_derivation(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """
    Best available geometric albedo per row, plus a label saying where it came
    from.  Preference order, most to least trustworthy:

        1. `albedo`                    — a real measurement
        2. ALBEDO_BY_SPECTRAL_TYPE     — exact type, then root letter
        3. ALBEDO_BY_SEMI_MAJOR_AXIS   — the belt's albedo gradient
        4. ALBEDO_FALLBACK             — whole-sample median

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
    # step invents are not visible here — which is deliberate.  Inferring a type
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
        "every row must end with an albedo — the fallback cannot be skipped"
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
        derived_diameter_is_estimate    bool — one thing to filter on

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
        print("\n📐  Diameter derivation OFF — measured diameters only "
              f"({int(measured.sum()):,} of {len(df):,} rows will survive validation)")
        df["diameter_km"] = diam
        return df

    print("\n📐  Deriving diameters from absolute magnitude …")

    if "absolute_magnitude_h" not in df.columns:
        # Every source supplies H, so its total absence means something upstream
        # broke rather than that the data is simply unavailable.  Say so — a
        # silent no-op here costs 1.4 M rows.
        print("     ⚠️  No `absolute_magnitude_h` column — nothing to derive from. "
              "Check that the JPL fetcher requested the H field.")
        df["diameter_km"] = diam
        return df

    H = pd.to_numeric(df["absolute_magnitude_h"], errors="coerce")
    target = (~measured) & H.notna()
    n_target = int(target.sum())

    if not n_target:
        print("     ℹ️   Every row already carries a measured diameter")
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
            print(f"     ✂️   {n_small:,} derived below "
                  f"{config.min_derived_diameter_km} km — left unfilled "
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

    # Publish the albedo this step assumed, in its OWN column — never merged
    # into `albedo`, which must keep meaning "measured".
    #
    # enrich_composition reads it as the last fallback for spectral type, and
    # that is a consistency requirement rather than a convenience.  Assuming
    # p_V = 0.066 for an outer-belt body IS assuming the body is carbonaceous;
    # sizing it on that number and then recording its composition as "Unknown"
    # would leave the catalog holding two incompatible beliefs about the same
    # rock — and "Unknown" carries None for every composition fraction, so the
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
    print(f"     ✅  {int(target.sum()):,} diameters derived  "
          f"(measured kept: {int(measured.sum()):,})")
    for src, n in counts.items():
        if src == "none":
            continue
        print(f"         • {str(src):32s} → {int(n):,}")
    still = int((pd.to_numeric(df['diameter_km'], errors='coerce').fillna(0) <= 0).sum())
    if still:
        print(f"         • {'no diameter (will be dropped)':32s} → {still:,}")

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
      2c. Where there is no measured albedo either, fall back to the albedo
          ASSUMED when the diameter was derived from H (v1.1.0).
          A `spectral_type_source` column records provenance:
            • "source"         → arrived from a fetcher (JPL spec_B, SsODNet
                                 taxonomy.class, MP3C taxonomy, …)
            • "tholen"         → filled from spectral_type_tholen (step 2a)
            • "albedo"         → inferred from measured albedo (step 2b)
            • "albedo_assumed" → inferred from the assumed albedo behind an
                                 H-derived diameter (step 2c) — the weakest
                                 class, and the bulk of a default v1.1.0 run
            • "unknown"        → still missing after every fallback
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
            print(f"     🔎  Spectral type inferred from albedo for {n_inf:,} entries")

    # ── 2c. Infer from the albedo ASSUMED when the diameter was derived ──────
    # Separate from 2b and separately labelled, because the input is an
    # assumption rather than a measurement.  It exists so a derived body's size
    # and its composition rest on the SAME assumption instead of contradicting
    # each other — see the note in derive_missing_diameters().  Without this the
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
            print(f"     🔎  Spectral type inferred from the ASSUMED albedo for "
                  f"{n_ass:,} entries (H-derived diameters)")

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

    # ── Step 2b — Derive diameters from H ────────────────────────────────────
    # Must run BEFORE validation: validation is what drops rows with no
    # diameter, and this is what gives them one.
    merged = derive_missing_diameters(merged, config)

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
            print(f"                   • {str(src):30s} {int(n):,}")
        if n_der:
            print("      ⚠️   Derived rows carry an ASSUMED albedo; mass scales as "
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
    # 1.5.0 — market-size data for Module 4 v1.7.0's saturation model.
    #         Prices were static at the point of sale: a mission could return
    #         any quantity of platinum and sell every kilogram at spot, which
    #         left the "fly more missions" lever with no stopping point.
    #         • ANNUAL_WORLD_PRODUCTION_KG — USGS primary production.  The
    #           targets asteroid mining always names are the small ones:
    #           osmium ~1 t/yr, iridium 7.5 t, rhodium 23 t, platinum 180 t.
    #         • IN_SPACE_ANNUAL_DEMAND_KG — what a theoretical base can absorb
    #           per year, all commodities competing for one import budget.
    #           LEO 500 t, cislunar 100 t, lunar surface 50 t, Mars 20 t.
    #           ⚠️  JUDGEMENT, not measurement — no such market exists.
    #         New output column: annual_market_kg (destination-aware).
    # 1.6.0 — IN-SPACE MANUFACTURING is now costed instead of assumed.  The
    #         gap between "kilogram of Fe-Ni at a depot" and "kilogram of
    #         usable structure" used to hide inside the 0.70 utility factor,
    #         so the refinery was assumed into existence and never paid for.
    #         Now explicit and derived from Module 3 rates:
    #           energy  kWh/kg x $6.08/kWh -- the capital cost of a kilowatt
    #                   hour in deep space ($800/W-EOL over a 15-yr life),
    #                   about 100x terrestrial industrial power
    #           plant   $300k/kg of hardware at 100 kg/yr throughput per kg
    #                   over 15 years = $200 per kg refined
    #         Metals take 5 kWh/kg (electric-arc / direct-reduction
    #         steelmaking is 4-5 kWh/kg terrestrially and there is no
    #         carbothermic shortcut in vacuum), silicates 1, carbon 2,
    #         water 0.5.  Deducted from the "used in space" route only --
    #         material shipped down is refined on Earth.
    #         The utility factor now means only what it says: how good a
    #         substitute the finished article is for a launched one.
    #         New output column: in_space_processing_usd_per_kg.
    # 1.7.0 — UTILITY IS PER DESTINATION, and the import budget is per
    #         commodity.  One utility table used to serve every in-space
    #         destination, so olivine captured the same fraction of its freight
    #         on the surface of Mars — a planet made of olivine — as at a
    #         propellant depot in empty space.  The missing term is not
    #         distance, it is LOCAL COMPETITION: the alternative to importing
    #         is not always launching from Earth.
    #         • IN_SPACE_UTILITY_BY_DESTINATION overrides the base table per
    #           destination.  LEO and cislunar keep the base profile unchanged
    #           — nothing is available locally there at any price, so they are
    #           the calibration anchor.  The two surfaces are discounted
    #           against what they can dig up:
    #             water        1.00 -> 0.60 Moon (PSR ice, ~40 K, no sunlight)
    #                               -> 0.25 Mars (metres-thick ground ice,
    #                                  1-3 wt% hydrated regolith per SAM)
    #             iron/FeNi    0.70 -> 0.45 Moon (5-15 wt% FeO + ilmenite)
    #                               -> 0.40 Mars (oxidised crust; loose
    #                                  meteoritic iron at Meridiani)
    #             silicates    0.25 -> 0.03 Moon / 0.02 Mars (it is the ground)
    #             carbon       0.40 -> 0.02 Mars (95.3% CO2 atmosphere); NOT
    #                                  discounted on the Moon, where carbon is
    #                                  ~100 ppm solar-wind implantation
    #             Ni/Co/Cu     undiscounted everywhere — no concentrated ore is
    #                                  known on either body
    #           Every override runs DOWNWARD.  Raising a utility is how this
    #           table becomes a viability dial, so a settlement catalyst market
    #           for the PGMs was considered and rejected — see the note on
    #           IN_SPACE_UTILITY_BY_DESTINATION for why it needs a
    #           quantity-aware route choice first.
    #         • _DEMAND_SHARE_BY_CLASS splits the destination import budget
    #           that IN_SPACE_ANNUAL_DEMAND_KG has described as shared since
    #           v1.5.0 but never actually divided — every commodity used to get
    #           the whole budget to itself.  Propellant 0.55 / structural 0.25 /
    #           shielding 0.15 / chemical 0.05, plus a 0.0005 trace slice that
    #           binds only if anyone ever gives the PGMs in-space utility.  So
    #           Mars absorbs 11 t/yr of water where it used to absorb 20 t/yr
    #           of every commodity independently.
    #           Measured effect, raw, full catalog: this alone costs LEO 9.8%
    #           and cislunar 46.6%, at destinations with NO utility override at
    #           all.  Cislunar takes the bigger hit off the smaller budget.
    #         • annual_market_kg is now ROUTED.  The market that saturates is
    #           the one you sell into, so a commodity flown down is bounded by
    #           terrestrial annual production, not by a depot's import budget.
    #           It runs in BOTH directions and which way depends on the
    #           commodity: platinum at LEO tightens (the depot's 500 t/yr
    #           becomes the world's real 180 t/yr) while gold loosens (500 t/yr
    #           becomes 3,000 t/yr).  Net effect on the best case is negative
    #           at every destination measured.
    #         Prices still RISE with distance — Mars freight is 10.6 kg-in-LEO
    #         per kg delivered and that dominates — but they no longer rise as
    #         fast as the freight does, and the volatiles that carried the Mars
    #         result rise least.  Water at Mars is 2.7x its LEO price now,
    #         against 11x before.
    #         Numerical impact on price (mars_surface):
    #           water     $44,902 -> $11,073   iron    $31,344 -> $17,812
    #           olivine   $11,070 ->    $696   carbon  $17,831 ->    $691
    #           nickel    unchanged at $31,360 (undiscounted)
    #           platinum  unchanged at $0 (downleg still exceeds spot)
    pipeline_version: str = "1.7.0"

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
#
# This table is the BASE PROFILE, and it describes a destination with no local
# resources of any kind: LEO and cislunar, where the only alternative to
# importing a kilogram from an asteroid is launching that kilogram from Earth.
# Planetary surfaces have a third option — dig it up locally — and they get
# per-destination overrides in IN_SPACE_UTILITY_BY_DESTINATION below.
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


# ─── UTILITY BY DESTINATION  (v1.7.0) ────────────────────────────────────────
# Until v1.7.0 one utility table served every in-space destination, so a
# kilogram of olivine was assumed to be worth the same fraction of its freight
# on the surface of Mars as at a propellant depot in LEO.  It is not, and the
# reason is not distance — it is that THE ALTERNATIVE TO IMPORTING IS NOT
# ALWAYS LAUNCHING FROM EARTH.
#
#   LEO, cislunar    Empty space.  Nothing is available locally at any price,
#                    so the only substitute for asteroid material is the same
#                    material launched from Earth.  These keep the base table
#                    above — they are the calibration anchor, and every
#                    override below is defined as a deviation from them.
#   lunar_surface    Sits on 4×10^19 t of silicate regolith containing 5–15 wt%
#                    FeO plus mare ilmenite, and (at the poles) water ice.
#   mars_surface     Sits on metres-thick mid-latitude ground ice (SHARAD /
#                    SWIM), 1–3 wt% hydrated regolith measured by Curiosity's
#                    SAM, a 95.3% CO2 atmosphere, and a globally oxidised
#                    iron-rich crust.
#
# So the correction runs mostly DOWNWARD, and hardest at the destination that
# is furthest away — which inverts the naive reading of the price table above.
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
# sound — a crewed base runs fuel cells, electrolysers and Sabatier reactors
# and wants Pt/Pd/Ru catalysts, where a propellant depot genuinely does not.
# It was dropped because this module prices each commodity with ONE $/kg and
# ONE market depth, and in_space_price_usd_per_kg routes on unit price alone.
# Gold at a lunar base would then route "used in space" at $76,060/kg into a
# 25 kg/yr catalyst market, beating a $30,061/kg route into a 3,000,000 kg/yr
# terrestrial one — a five-order-of-magnitude cliff in market depth, invisible
# to the router, that would make precious-metal bodies look worse for a reason
# with no physics in it.  The real behaviour is a blend (sell the first few kg
# in space, fly the rest home) and this pipeline cannot express a blend.
# Restoring it needs a quantity-aware route choice first, not a bigger table.
#
# ⚠️  Softer than the base table, which is already the softest thing in the
# pipeline.  These are judgements about economies that do not exist.
IN_SPACE_UTILITY_BY_DESTINATION: Dict[str, Dict[str, float]] = {
    "leo":      {},                  # base profile — no local resources
    "cislunar": {},                  # base profile — no local resources
    "lunar_surface": {
        # Polar ice is real and is the entire premise of a lunar base, but it
        # is in permanently shadowed craters at ~40 K with no sunlight to work
        # by.  Discounted, not eliminated.
        "water":            0.60,
        # Regolith is 5–15 wt% FeO and the mare carries ilmenite; hydrogen
        # reduction and molten regolith electrolysis both work at lab scale.
        "iron":             0.45,
        "nickel-iron":      0.45,
        "awaruite":         0.45,
        "magnetite":        0.25,
        # Ni / Co / Cu are NOT discounted.  No concentrated ore of any of them
        # is known on the Moon, and they are what motors, batteries and wiring
        # are made of — the base table's 0.70 already prices the manufacturing
        # gap.
        # Shipping silicate rock to a body made of silicate rock.  Kept just
        # above zero for the specific phases nobody has demonstrated
        # separating from regolith, not for bulk shielding mass.
        "olivine":          0.03, "pyroxene":       0.03, "orthopyroxene": 0.03,
        "enstatite":        0.03, "plagioclase":    0.03, "spinel":        0.03,
        "phyllosilicates":  0.03, "oxides":         0.03, "silicates":     0.03,
        # Carbon is one of the genuinely scarce elements on the Moon —
        # solar-wind implantation leaves it at ~100 ppm, which is not a
        # resource.  No discount.
        # Precious metals stay at the base 0.00 and route down — see the
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
        # Ni / Co / Cu again undiscounted — no known concentrated martian ore.
        # Basalt, everywhere, for free.
        "olivine":          0.02, "pyroxene":       0.02, "orthopyroxene": 0.02,
        "enstatite":        0.02, "plagioclase":    0.02, "spinel":        0.02,
        "phyllosilicates":  0.02, "oxides":         0.02, "silicates":     0.02,
        # The atmosphere is 95.3% CO2 at ~600 Pa.  Carbon is free on Mars, and
        # Sabatier + electrolysis turns it and the local water into methane and
        # onward feedstock — which is most of what "organics" would be for.
        "carbon":           0.02,
        "organics":         0.05,
        # Precious metals stay at the base 0.00 and route down — see the
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
# nothing else corrects, because the whole "just fly more missions" lever —
# nre_amortization_missions — has no natural stopping point without it.
#
# Terrestrial figures are USGS Mineral Commodity Summaries annual primary
# production.  Bulk commodities Earth has in effective abundance carry a
# deliberately huge number so saturation never binds on them.
ANNUAL_WORLD_PRODUCTION_KG: Dict[str, float] = {
    # Precious — small markets, and the ones asteroid mining always targets
    "osmium":         1.0e3,      # ~1 t/yr, a by-product of a by-product
    "iridium":        7.5e3,      # ~7.5 t
    "rhodium":        2.3e4,      # ~23 t
    "ruthenium":      3.0e4,      # ~30 t
    "platinum":       1.8e5,      # ~180 t
    "palladium":      2.1e5,      # ~210 t
    "gold":           3.0e6,      # ~3,000 t
    "silver":         2.6e7,      # ~26,000 t
    # Base metals — large markets, saturation effectively never binds
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
# ⚠️  JUDGEMENT, not measurement — no such market exists.  Anchored to
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
    "cislunar":      100_000.0,
    "lunar_surface":  50_000.0,
    "mars_surface":   20_000.0,
}


# ─── WHAT THE BUDGET IS SPENT ON  (v1.7.0) ───────────────────────────────────
# The comment above has said "all commodities competing for the same import
# budget" since v1.5.0, but the code handed EVERY commodity the full budget
# independently — so a Mars base that imports 20 t/yr would take 20 t of water
# AND 20 t of platinum AND 20 t of olivine.  That mattered little while the
# precious metals had zero in-space utility everywhere; it stopped being
# harmless the moment v1.7.0 gave them a non-zero utility at a settlement.
#
# Each commodity now gets a SHARE of the destination's annual import mass.
# Shares are per CLASS, and every commodity in a class can absorb the whole
# class share, because within a class they are substitutes — a base wanting
# shielding mass does not care whether it arrives as olivine or pyroxene.
# The four bulk classes partition the budget; the trace slice is additive and
# negligible.
#
# ⚠️  JUDGEMENT, like everything else in this block.  Anchored on what a
# propellant-and-construction outpost actually consumes by mass: propellant
# dominates, structure is next, shielding is bulky but occasional, and
# catalysts are measured in kilograms.
_DEMAND_SHARE_BY_CLASS: Dict[str, float] = {
    "propellant":  0.55,   # water — refuelling is most of any depot's tonnage
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
    budget — before v1.7.0 platinum at LEO was capped at the depot's 500 t/yr
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
#            costs $800 / 131,490 = $0.0061/Wh ≈ $6.08/kWh — roughly 100×
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
    "magnetite":        7.0,  # oxide — reduction first
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
    for anything with no listed process — the caller then treats it as sold
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
    # How much of each commodity the market can absorb per year — Module 4
    # uses it to apply a demand curve rather than selling any quantity at spot.
    # v1.7.0: routed — a commodity sold by flying it down saturates the
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
    # 1.6.0 — data for the modelling gaps Module 4 v1.7.0 closes.  Additive;
    #         no existing number changed.
    #         • "Electric thruster + PPU specific mass" 8 kg/kW and
    #           "Electric propulsion efficiency" 0.60.  Together with the
    #           existing power-system row these make low-thrust TRIP TIME
    #           computable: T = 2·η·P/(Isp·g0), and a burn lasting
    #           m_prop·(Isp·g0)²/(2·η·P).  Until now electric propulsion paid
    #           a Δv penalty but flew instantly and drew no power.
    #         • "Water liberation energy (bound water)" 2,500 Wh/kg.  C-type
    #           water is bound in phyllosilicates and has to be baked out;
    #           the pipeline was extracting it for free.
    # 1.7.0 — data for Module 4 v1.8.0's rig terminal value, in-space
    #         manufacturing, reliability and boil-off models.  Additive.
    #         • New `boiloff_pct_per_day` column on PROPELLANTS_REFERENCE.
    #           Hydrolox 0.05%/day is the one that bites: over a 5-year
    #           mission that is 2.5x the return propellant, which is exactly
    #           why no flown mission has ever done a deep-space arrival burn
    #           on hydrolox after a multi-year cruise.  Storables and the
    #           electrics are 0.
    #         • 6 new OPERATIONAL_COSTS rows: launch reliability 0.97,
    #           spacecraft MTBF 30 yr, first-of-kind mining success 0.75,
    #           rig service life 15 yr, rig salvage fraction 0.50, and
    #           in-space plant throughput 100 kg/yr per kg of plant.
    # 1.8.0 — two rows for Module 4 v1.9.0's reliability-growth model:
    #         "Mining reliability growth exponent" 0.30 (Duane alpha, bottom
    #         of MIL-HDBK-189's active-growth band -- appropriate for hardware
    #         that flies once every few years with no test fleet) and
    #         "Mining system mature success probability" 0.95 (asymptotic
    #         ceiling; mature spacecraft mechanisms run 97-99% and a
    #         continuously-operating excavator is harder than a one-shot
    #         deployment).
    # 1.8.1 — recalibrated "Mining system first-of-kind success probability"
    #         0.75 -> 0.85.  The v1.7.0 note cited three failures and none of
    #         the successes; the full regolith-contact record is 11/13.  Notes
    #         now list the whole tally, both ways of counting Hayabusa, and
    #         why sustained-operation risk is not double-counted here.
    # 1.8.2 — new ops row: "Electric propulsion system recurring cost",
    #         $1.5M per kW of thruster + PPU (NEXT-C anchored, range
    #         $0.5-3M/kW).  Module 4 v1.7.0 put the electric stage's array and
    #         thruster into the ROCKET EQUATION and never into any cost line,
    #         so a 309 kW / 14-tonne EP system was free — and once Module 4
    #         v1.10.0 stopped selecting missions by "cheapest", electric
    #         propulsion won everywhere on hardware nobody had to buy.  The
    #         array is priced off the existing $800/W power-system row; this
    #         row covers only the propulsion train.  Adds one category (35).
    # 1.9.0 — CATALOG COMPLETENESS AUDIT.  The three reference tables held what
    #         somebody happened to list, not what exists, and the omissions were
    #         not neutral — they all ran in the same direction.  Paired with
    #         Module 4 v1.11.0.
    #         • PROPELLANTS 7 → 40.  Sixteen additions have FLOWN and were
    #           simply absent: solid APCP, UDMH/NTO, Aerozine-50, green
    #           monoprop, HTP monoprop and bipropellant, cold gas, krypton
    #           (the most-flown electric propellant by unit count), iodine,
    #           water electrothermal and water ion, hydrazine arcjet,
    #           electrospray, FEEP, PPT, and mercury ion (retired, banned).
    #           Seven more are in development (NTP, NEP, solar-thermal, solar
    #           steam, VASIMR, MPD, metal/water) and nine are concepts
    #           (Li/F2/H2, CO/LOX, mass driver, Orion pulse, fusion, antimatter,
    #           magsail, tether, beamed laser-thermal).
    #         • TANK MASS IS DERIVED, NOT IGNORED.  New `storage_class` and
    #           `tank_kg_per_L` per row.  density_kg_per_L had been computed and
    #           exported since v1.2.0 and read by NOTHING, so every low-density
    #           propellant flew its tank for free.  Anchored on flight articles:
    #           hydrolox lands at 9.7% of propellant mass against Centaur's
    #           measured ~9.7%, APCP at 6.9% against Star 48B's 6.4%, cold gas
    #           at 46%.  Bare LH2 pays 53%, which is what nuclear thermal now
    #           has to earn its 900 s against.
    #         • New `status` / `trl` / `restartable` / `propellantless` /
    #           `isru_feed_kg_per_kg` / `isru_feed_material` / `first_flight`
    #           columns.  status gates the search exactly as it already did for
    #           vehicles.  restartable=False takes solids out permanently — a
    #           return burn fires years after launch — and propellantless=True
    #           takes sails out, because infinite Isp otherwise reports an
    #           unbounded payload.  isru_feed_* generalises what Module 4 had
    #           hardcoded as "hydrolox only": a steam rocket burns asteroid
    #           water at 1.00 kg feed per kg propellant against hydrolox's
    #           1.286, and a mass driver throws raw regolith.
    #         • LAUNCH VEHICLES 12 → 36.  Six operational (LVM3, Ariane 62,
    #           Long March 7, Vega C, PSLV-XL, Alpha), two retired (Delta IV
    #           Heavy, H-IIA — the vehicle that launched Hayabusa2), eight in
    #           development (Neutron, Terran R, Nova, Eclipse, Zhuque-3,
    #           Tianlong-3, Long March 9 and 10), and eight NON-ROCKET concepts
    #           (SpinLaunch, light-gas gun, StarTram, Skylon, Sea Dragon, lunar
    #           mass driver, lunar and Earth space elevators).
    #         • New `launch_type` / `origin` / `trl` / `max_accel_g` /
    #           `tanker_flights_for_escape` columns.  max_accel_g is the one
    #           that matters: the kinetic launchers are not expensive, they are
    #           10,000-30,000 g and can lift propellant but not a mining rig.
    #           tanker_flights_for_escape finally implements what the Starship
    #           row's own notes had asked for since v1.4.0.
    #         • NEW TABLE: STORAGE_REFERENCE, 20 systems across four domains
    #           (propellant tankage and cryocooling, cargo containment, onboard
    #           energy storage, in-space depots), exported as
    #           storage_systems.csv.  Storage was previously one column.
    #         • New ops row "RTG specific power" 5.0 W/kg, and the RTG cost row
    #           — present since v1.2.0 and never read by anything — is now
    #           consumed by Module 4.  Crossover against the 60 W/kg solar row
    #           is 3.46 AU, and this catalog runs well past it.
    # 1.10.0 — realism audit of the v1.9.0 tables.  Three changes, two of which
    #         move every number.
    #         • THRUSTER SYSTEMS: the DEVICE, as distinct from the propellant.
    #           This table has always been half propellant and half propulsion
    #           system (isp_vac_s, restartable and dv_penalty_factor are device
    #           properties), and it carried nothing about whether the device can
    #           be BUILT at the size Module 4 flies.  So Module 4 sized an
    #           electric stage on power alone and a third of its winning
    #           missions were pulsed plasma thrusters — 860 uN in flight, asked
    #           for ~10 N.  New `_THRUSTER_SYSTEMS` block supplies
    #           `thruster_kg_per_n`, `thruster_efficiency` and `thrust_scaling`
    #           per technology, every figure anchored on a flight or ground
    #           article.  The `continuous` / `replicated` split is the physics:
    #           a discharge or beam you can enlarge stays at 6-90 kg/N however
    #           big you build it; discrete emitters, needles and pulses are
    #           stuck at 2,500-10,000 kg/N forever.  `_apply_thruster_data`
    #           RAISES on an electric row with no entry rather than defaulting,
    #           and tests dv_penalty_factor > 1 to match Module 4's own
    #           is_electric test — keying off `type` would have missed
    #           nuclear_electric, direct fusion drive and antimatter, and it
    #           caught all three.
    #         • NEW OPS ROW "Power processing unit specific mass" 4.7 kg/kW,
    #           splitting the lumped 8 kg/kW "thruster + PPU".  A per-kW figure
    #           cannot express a per-newton constraint, which is what allowed
    #           the above.
    #         • ARGON WAS A FREE RESOURCE, and the row said so itself.  It
    #           carried liquid-argon density (1.395 kg/L, which only exists at
    #           its 87.3 K boiling point) with a boil-off of ZERO, and its own
    #           two comments — "liquid NBP (cryogenic storage)" and "stored
    #           supercritical at ambient temperature" — sat three lines apart.
    #           The combination bought the lightest tank of any gas here, 2.1%
    #           of propellant mass, AND exemption from the hold-time penalty
    #           every other cryogen pays.  Measured at cislunar, argon was
    #           chosen for 25.0% of raw winners and 27.3% of beneficiated ones;
    #           correctly bottled it takes 2.4% and 0.0%, and 1,059 bodies stop
    #           being feasible.  It also carried the whole Mars result at both
    #           settings, which has not been re-run.  Note what did NOT move:
    #           both cislunar headline ratios are bit-identical either way,
    #           because the best missions were never flying argon.
    #           Split into the two real articles: `ArgonSC`, supercritical in a
    #           COPV at 18 MPa and 0.30 kg/L, which is what has FLOWN (no
    #           spacecraft has ever carried cryogenic argon), and `ArgonLIQ`,
    #           the liquid feed a multi-tonne stage would want, tagged
    #           `development` and paying derived boil-off.  Honestly bottled,
    #           argon pays 22.9% of its own mass in tankage — worse than
    #           krypton's 12.5% and xenon's 1.9%, because it is the LIGHTEST of
    #           the three and tank fraction goes as 1/M once pressure cancels.
    #           Density derived two ways (Peng-Robinson and generalised
    #           compressibility), boil-off derived from this table's own LOX
    #           figure.  See _COMPONENTS and _LAR_BOILOFF_PCT_PER_DAY.
    #         • NEW OPS ROW "Propellant tank recurring cost", $6,000/kg,
    #           Centaur-derived.  Module 3 has produced tank MASS since v1.9.0
    #           and Module 4 has flown it since, and nothing ever bought one.
    #         Propellants 40 → 41 (23 operational, 8 development).
    # 1.11.0 — the reference DATA was right and unreachable.  Four new
    #         OPERATIONAL_COSTS rows, and not one of them is a new measurement:
    #         every figure already existed in STORAGE_REFERENCE, where it had
    #         been sitting behind a "⚠️  Not modelled in Module 4" note since
    #         v1.9.0.  Module 4 loads operational_costs.csv and does NOT load
    #         storage_systems.csv, so the whole table was documentation.
    #         That is a new instance of the prescriptive-comment failure this
    #         project keeps finding, with a twist worth naming: v1.9.0 wrote
    #         down the gap, the gap was quoted in CLAUDE.md as a known
    #         limitation for two releases, and writing it down was mistaken for
    #         closing it.  A table nobody reads is not a model.
    #         • "Eclipse / night-side dark fraction" 0.50.  The sun sets on a
    #           rig anchored to a rotating body.  This is a SIZING factor, so no
    #           W/kg row could ever have absorbed it.
    #         • "Energy storage usable specific energy" 104 Wh/kg — 130 Wh/kg
    #           system-level Li-ion × 0.80 DoD, folded so a consumer cannot
    #           forget the DoD.
    #         • "Power-system row baseline dark period" 0.58 h.  The deduction
    #           that stops the battery being charged twice, and the resolution
    #           of a contradiction: "Power system specific mass" claimed to
    #           cover both a LEO eclipse and an asteroid night, which no single
    #           number can.  That claim is removed from its notes.  Same shape
    #           as argon in v1.10.0 — a row asserting two incompatible physical
    #           states — and it is worth noticing that the argon audit did not
    #           catch it, because it was looking at propellants.
    #         • "Volatile cargo containment" 0.05 kg/kg.  Water sold at a depot
    #           has to still be water on arrival.  The best cislunar missions
    #           are ~88% water by mass, so this is the largest single unpriced
    #           item the model had left, not a rounding term.
    #         No propellant, vehicle or Δv figure moved.  Every number Module 4
    #         produces does, because it can now read these.
    # 1.12.0 — ONE new OPERATIONAL_COSTS row, and it is the missing half of a
    #         bound this table has carried since v1.7.0.
    #         • "Mining rig maximum trips" 5 (range 2-12).  "Mining rig service
    #           life" is 15 YEARS, and Module 4 turned that into a mission count
    #           by dividing by the stay — so at the ~1.25 yr stay the winning
    #           cislunar mission actually flies, one rig served 12 consecutive
    #           campaigns.  Calendar time is not what wears out a machine that
    #           cuts rock; duty cycles are, and nothing in this table said how
    #           many.  A rig idle between campaigns ages slowly and one digging
    #           continuously does not.
    #           ⚠️  JUDGEMENT, and the row says so at length.  Nothing has ever
    #           mined an asteroid twice, so it is bracketed between terrestrial
    #           mining plant (major overhaul at ~2-3 yr of continuous duty, 2-3
    #           rebuilds before retirement — in a workshop that does not exist
    #           at an asteroid) and the flight record for regolith-contact
    #           mechanisms (single-campaign by design, or failed inside one).
    #           5 is the optimistic reading of both.
    #         No propellant, vehicle, Δv or storage figure moved.
    pipeline_version: str = "1.12.0"
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

# ─── SCHEMA ADDED v1.9.0 ─────────────────────────────────────────────────────
# Five fields, applied to every row by _apply_launch_defaults() below so that a
# conventional rocket only has to state what makes it unusual:
#
#   launch_type    chemical_rocket | kinetic | maglev | gun | airbreathing |
#                  tether.  The table used to assume every launcher was a
#                  chemical rocket, which meant the alternatives could not be
#                  written down at all — not that they had been rejected.
#   origin         earth_surface | lunar_surface.  A lunar mass driver or
#                  elevator is a launch system whose $/kg is an order of
#                  magnitude below anything on this list, and it is only
#                  reachable AFTER there is something on the Moon.  Module 4
#                  models Earth departure only, so non-Earth origins are gated.
#   trl            Technology readiness, 1-9, same scale as the propellants.
#   max_accel_g    Peak axial acceleration the payload sees.  A rocket is 4-6 g.
#                  It is in this table because it is DISQUALIFYING for the
#                  kinetic launchers: SpinLaunch is ~10,000 g and a gun is
#                  ~30,000 g, which passes propellant and steel and destroys
#                  every mining rig, optic and reaction wheel in the catalog.
#   tanker_flights_for_escape
#                  Refuelling flights the escape-payload figure assumes.  Zero
#                  for everything that reaches escape in one launch.  Starship's
#                  own notes field has said "Module 4 should add ~$90M ×
#                  N_tankers" since v1.4.0 and nothing ever did, so its 27 t to
#                  escape was being priced at one launch.  Now it is a column
#                  rather than a sentence, and Module 4 reads it.
_LAUNCH_DEFAULTS = {
    "launch_type":               "chemical_rocket",
    "origin":                    "earth_surface",
    "trl":                       9,
    "max_accel_g":               6.0,
    "tanker_flights_for_escape": 0,
}

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
        "trl":                           6,
        # v1.9.0: the escape figure below assumes orbital refuelling.  SpaceX
        # has quoted 8-16 tanker flights for a fully-fuelled departure stage;
        # 12 is the midpoint.  Module 4 now charges them.
        "tanker_flights_for_escape":     12,
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

    # ═════════════════════════════════════════════════════════════════════════
    # OPERATIONAL — added v1.9.0.  Mostly the non-Western and small-lift end,
    # which the table had skipped entirely.  None of these will win a heavy
    # asteroid mission; they are here so "cheapest $/kg" is a claim about the
    # whole market rather than about twelve vehicles somebody happened to list.
    # ═════════════════════════════════════════════════════════════════════════
    {
        "name":                          "LVM3 (GSLV Mk III)",
        "operator":                      "ISRO",
        "status":                        "operational",
        "payload_leo_kg":                10_000,
        "payload_gto_kg":                 4_000,
        "payload_escape_kg":              2_000,
        "fairing_volume_m3":                110,
        "list_price_usd":            51_000_000,
        "usd_per_kg_to_leo":              5_100,
        "usd_per_kg_to_gto":             12_750,
        "usd_per_kg_to_escape":          25_500,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: ISRO / NSIL commercial rate ~$51M; payloads from the "
                 "ISRO LVM3 user manual.  Flew Chandrayaan-3 and two OneWeb "
                 "batches.  India's heaviest, and the cheapest human-rated-class "
                 "vehicle on this list per launch.",
    },
    {
        "name":                          "Ariane 6 (A62)",
        "operator":                      "ArianeGroup / ESA",
        "status":                        "operational",
        "payload_leo_kg":                10_300,
        "payload_gto_kg":                 4_500,
        "payload_escape_kg":              3_000,
        "fairing_volume_m3":                124,
        "list_price_usd":            80_000_000,
        "usd_per_kg_to_leo":              7_767,
        "usd_per_kg_to_gto":             17_778,
        "usd_per_kg_to_escape":          26_667,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: ESA Ariane 6 overview — the two-booster config, "
                 "roughly €70M against A64's €115M.  Worse $/kg than A64, which "
                 "is the usual result when a vehicle is flown below its "
                 "designed lift.",
    },
    {
        "name":                          "Long March 7",
        "operator":                      "CASC (China)",
        "status":                        "operational",
        "payload_leo_kg":                13_500,
        "payload_gto_kg":                 7_000,
        "payload_escape_kg":              4_000,
        "fairing_volume_m3":                111,
        "list_price_usd":            60_000_000,    # estimate; pricing opaque
        "usd_per_kg_to_leo":              4_444,
        "usd_per_kg_to_gto":              8_571,
        "usd_per_kg_to_escape":          15_000,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: CASC / Wikipedia payload figures; $60M is an estimate "
                 "on the same basis as the Long March 5 row — Chinese "
                 "commercial pricing is not published.  Kerolox, Tianzhou "
                 "cargo heritage.",
    },
    {
        "name":                          "Vega C",
        "operator":                      "Avio / ESA",
        "status":                        "operational",
        "payload_leo_kg":                 3_300,
        "payload_gto_kg":                     0,
        "payload_escape_kg":                  0,
        "fairing_volume_m3":                 47,
        "list_price_usd":            37_000_000,
        "usd_per_kg_to_leo":             11_212,
        "usd_per_kg_to_gto":             np.nan,
        "usd_per_kg_to_escape":          np.nan,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Avio / ESA — ~€34M.  Solid first three stages, "
                 "restartable AVUM+ upper.  Small-lift; useful for a prospector "
                 "probe, not for a mining rig.",
    },
    {
        "name":                          "PSLV-XL",
        "operator":                      "ISRO",
        "status":                        "operational",
        "payload_leo_kg":                 3_800,
        "payload_gto_kg":                 1_425,
        "payload_escape_kg":              1_100,
        "fairing_volume_m3":                 34,
        "list_price_usd":            31_000_000,
        "usd_per_kg_to_leo":              8_158,
        "usd_per_kg_to_gto":             21_754,
        "usd_per_kg_to_escape":          28_182,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: ISRO / NSIL.  Flew Chandrayaan-1 and Mars Orbiter "
                 "Mission — the cheapest vehicle that has actually delivered a "
                 "payload to another planet, which is the only reason a "
                 "3.8 t launcher is in this table.",
    },
    {
        "name":                          "Alpha",
        "operator":                      "Firefly Aerospace",
        "status":                        "operational",
        "payload_leo_kg":                 1_030,
        "payload_gto_kg":                     0,
        "payload_escape_kg":                  0,
        "fairing_volume_m3":                 22,
        "list_price_usd":            15_000_000,
        "usd_per_kg_to_leo":             14_563,
        "usd_per_kg_to_gto":             np.nan,
        "usd_per_kg_to_escape":          np.nan,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Firefly published price.  Small-lift kerolox.  Listed "
                 "for market completeness at the bottom end.",
    },

    # ═════════════════════════════════════════════════════════════════════════
    # RETIRED — flew, will not fly again.  Kept for the same reason mercury ion
    # is kept in the propellant table: so that a historical $/kg figure found
    # elsewhere can be identified as unavailable rather than as an oversight.
    # ═════════════════════════════════════════════════════════════════════════
    {
        "name":                          "Delta IV Heavy",
        "operator":                      "ULA",
        "status":                        "retired",
        "payload_leo_kg":                28_790,
        "payload_gto_kg":                14_220,
        "payload_escape_kg":             10_000,
        "fairing_volume_m3":                310,
        "list_price_usd":           440_000_000,
        "usd_per_kg_to_leo":             15_283,
        "usd_per_kg_to_gto":             30_942,
        "usd_per_kg_to_escape":          44_000,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Last flight April 2024 (NROL-70).  Hydrolox, three cores, and "
                 "the launcher that sent Parker Solar Probe to the highest "
                 "departure energy ever flown.  Replaced by Vulcan.",
    },
    {
        "name":                          "H-IIA 204",
        "operator":                      "MHI / JAXA",
        "status":                        "retired",
        "payload_leo_kg":                15_000,
        "payload_gto_kg":                 6_000,
        "payload_escape_kg":              3_600,
        "fairing_volume_m3":                122,
        "list_price_usd":            90_000_000,
        "usd_per_kg_to_leo":              6_000,
        "usd_per_kg_to_gto":             15_000,
        "usd_per_kg_to_escape":          25_000,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Last flight June 2025 (GOSAT-GW), 49 flights and one failure. "
                 "Launched Hayabusa2 — the most relevant flight heritage in "
                 "this entire table to what this pipeline models.  Succeeded "
                 "by H3.",
    },

    # ═════════════════════════════════════════════════════════════════════════
    # DEVELOPMENT — announced, hardware in test, not yet flown to orbit.
    # Gated out of Module 4 by operational_vehicles_only, same as Starship.
    # Prices are targets, and launch-vehicle targets are optimistic by
    # construction; treat every list_price_usd here as a floor.
    # ═════════════════════════════════════════════════════════════════════════
    {
        "name":                          "Neutron",
        "operator":                      "Rocket Lab",
        "status":                        "development",
        "trl":                           6,
        "payload_leo_kg":                13_000,    # reusable; 15,000 expendable
        "payload_gto_kg":                 1_500,
        "payload_escape_kg":              1_000,
        "fairing_volume_m3":                113,
        "list_price_usd":            55_000_000,
        "usd_per_kg_to_leo":              4_231,
        "usd_per_kg_to_gto":             36_667,
        "usd_per_kg_to_escape":          55_000,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Rocket Lab investor materials — ~$50-55M, 13 t LEO "
                 "reusable.  Methalox, captive fairing, first-stage return. "
                 "Beyond-LEO capability is thin: the upper stage is sized for "
                 "constellation work, so the escape figure is poor for the class.",
    },
    {
        "name":                          "Terran R",
        "operator":                      "Relativity Space",
        "status":                        "development",
        "trl":                           5,
        "payload_leo_kg":                33_500,
        "payload_gto_kg":                 5_500,
        "payload_escape_kg":              4_000,
        "fairing_volume_m3":                340,
        "list_price_usd":            70_000_000,    # not published; class estimate
        "usd_per_kg_to_leo":              2_090,
        "usd_per_kg_to_gto":             12_727,
        "usd_per_kg_to_escape":          17_500,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Relativity published payload figures; price is an "
                 "estimate against the Falcon 9 / New Glenn class, since "
                 "Relativity has not published one.  Methalox, reusable first "
                 "stage, largely additively manufactured.",
    },
    {
        "name":                          "Nova",
        "operator":                      "Stoke Space",
        "status":                        "development",
        "trl":                           5,
        "payload_leo_kg":                 5_000,    # fully reusable; 7,000 expendable
        "payload_gto_kg":                 1_200,
        "payload_escape_kg":                800,
        "fairing_volume_m3":                 80,
        "list_price_usd":            25_000_000,
        "usd_per_kg_to_leo":              5_000,
        "usd_per_kg_to_gto":             20_833,
        "usd_per_kg_to_escape":          31_250,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Stoke Space published figures.  The only vehicle in "
                 "this table besides Starship designed for FULL reuse including "
                 "the second stage — an actively-cooled regeneratively-shielded "
                 "upper stage.  If that works, the $/kg here is a ceiling rather "
                 "than a floor, which is the opposite of every other row.",
    },
    {
        "name":                          "Eclipse (MLV)",
        "operator":                      "Firefly / Northrop Grumman",
        "status":                        "development",
        "trl":                           5,
        "payload_leo_kg":                16_300,
        "payload_gto_kg":                 3_000,
        "payload_escape_kg":              2_000,
        "fairing_volume_m3":                160,
        "list_price_usd":            80_000_000,
        "usd_per_kg_to_leo":              4_908,
        "usd_per_kg_to_gto":             26_667,
        "usd_per_kg_to_escape":          40_000,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Firefly / Northrop announcements.  Formerly MLV; "
                 "16.3 t LEO on a reusable methalox first stage.",
    },
    {
        "name":                          "Zhuque-3",
        "operator":                      "LandSpace (China)",
        "status":                        "development",
        "trl":                           6,
        "payload_leo_kg":                21_000,    # expendable; 18,300 reusable
        "payload_gto_kg":                 6_000,
        "payload_escape_kg":              4_000,
        "fairing_volume_m3":                190,
        "list_price_usd":            30_000_000,    # estimate; pricing opaque
        "usd_per_kg_to_leo":              1_429,
        "usd_per_kg_to_gto":              5_000,
        "usd_per_kg_to_escape":           7_500,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: LandSpace published payloads; price estimated on the "
                 "same opaque basis as the other Chinese rows.  Stainless "
                 "methalox with a returning first stage — the closest analogue "
                 "to Falcon 9 outside SpaceX, and its estimated $/kg to LEO is "
                 "the lowest on this table after Starship.  That estimate is "
                 "doing a lot of work; treat the ranking, not the number.",
    },
    {
        "name":                          "Tianlong-3",
        "operator":                      "Space Pioneer (China)",
        "status":                        "development",
        "trl":                           5,
        "payload_leo_kg":                17_000,
        "payload_gto_kg":                 5_000,
        "payload_escape_kg":              3_000,
        "fairing_volume_m3":                150,
        "list_price_usd":            25_000_000,    # estimate
        "usd_per_kg_to_leo":              1_471,
        "usd_per_kg_to_gto":              5_000,
        "usd_per_kg_to_escape":           8_333,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: Space Pioneer announcements; price estimated. "
                 "Kerolox, reusable first stage intended.",
    },
    {
        "name":                          "Long March 10",
        "operator":                      "CASC (China)",
        "status":                        "development",
        "trl":                           5,
        "payload_leo_kg":                70_000,
        "payload_gto_kg":                31_000,
        "payload_escape_kg":             27_000,    # TLI, crewed lunar architecture
        "fairing_volume_m3":                310,
        "list_price_usd":           200_000_000,    # estimate
        "usd_per_kg_to_leo":              2_857,
        "usd_per_kg_to_gto":              6_452,
        "usd_per_kg_to_escape":           7_407,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: CASC crewed-lunar-programme disclosures; price "
                 "estimated.  70 t LEO / 27 t TLI targeting a 2030 crewed lunar "
                 "landing.  Would be the best $/kg-to-escape on this table if "
                 "the price estimate holds, which is a large if.",
    },
    {
        "name":                          "Long March 9",
        "operator":                      "CASC (China)",
        "status":                        "development",
        "trl":                           3,
        "payload_leo_kg":               150_000,
        "payload_gto_kg":                65_000,
        "payload_escape_kg":             50_000,
        "fairing_volume_m3":              1_000,
        "list_price_usd":           500_000_000,    # estimate
        "usd_per_kg_to_leo":              3_333,
        "usd_per_kg_to_gto":              7_692,
        "usd_per_kg_to_escape":          10_000,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Source: CASC roadmap presentations; the design has been "
                 "revised repeatedly, most recently toward a reusable "
                 "Starship-like configuration, and no flight date before the "
                 "mid-2030s is credible.  TRL 3.  Present because it is the "
                 "only announced vehicle in the Starship class that is not "
                 "Starship.",
    },

    # ═════════════════════════════════════════════════════════════════════════
    # NON-ROCKET LAUNCH — concept.  Every one of these promises a $/kg an order
    # of magnitude below the chemical rockets above, and every one is gated out
    # of Module 4.  Two things to read here rather than the price column:
    #
    #   • max_accel_g.  The kinetic launchers do not have a cost problem, they
    #     have a payload problem.  10,000 g passes bulk propellant, water and
    #     steel billets.  It does not pass a mining rig, a solar array, an
    #     optic, a reaction wheel or a radio.  A launch system that can only
    #     lift consumables changes the economics of a mining programme without
    #     lifting any of its hardware, and this pipeline has no way to express
    #     a split manifest.
    #   • origin.  A lunar mass driver or elevator beats everything here on
    #     $/kg and cannot be used until something is already on the Moon.
    #     Module 4 departs from Earth, so those rows are unreachable by
    #     construction rather than merely immature.
    # ═════════════════════════════════════════════════════════════════════════
    {
        "name":                          "SpinLaunch Orbital",
        "operator":                      "SpinLaunch",
        "status":                        "concept",
        "launch_type":                   "kinetic",
        "trl":                           4,
        "max_accel_g":                   10_000.0,
        "payload_leo_kg":                   200,
        "payload_gto_kg":                     0,
        "payload_escape_kg":                  0,
        "fairing_volume_m3":                0.6,
        "list_price_usd":             1_250_000,
        "usd_per_kg_to_leo":              6_250,
        "usd_per_kg_to_gto":             np.nan,
        "usd_per_kg_to_escape":          np.nan,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "A vacuum centrifuge throws the vehicle to ~2 km/s and a small "
                 "rocket stage does the rest.  The suborbital accelerator flew "
                 "test articles in 2022, so this is a real machine, not a paper "
                 "one — TRL 4.  ~10,000 g at release is the whole story: the "
                 "company's own manifest talk is propellant and bulk materials. "
                 "The $/kg here is the published target and assumes a cadence "
                 "nobody has demonstrated.",
    },
    {
        "name":                          "Light-gas gun (orbital)",
        "operator":                      "Green Launch / HARP lineage",
        "status":                        "concept",
        "launch_type":                   "gun",
        "trl":                           3,
        "max_accel_g":                   30_000.0,
        "payload_leo_kg":                    30,
        "payload_gto_kg":                     0,
        "payload_escape_kg":                  0,
        "fairing_volume_m3":               0.05,
        "list_price_usd":               300_000,
        "usd_per_kg_to_leo":             10_000,
        "usd_per_kg_to_gto":             np.nan,
        "usd_per_kg_to_escape":          np.nan,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Gerald Bull's HARP put a 180 kg slug to 180 km in 1966 — the "
                 "altitude record for a gun still stands.  Orbital insertion "
                 "needs a kick stage, and ~30,000 g means the kick stage has to "
                 "survive it too.  Hydrogen-driven light-gas guns reach ~7 km/s "
                 "in the laboratory.  Payload-limited to consumables forever.",
    },
    {
        "name":                          "StarTram (maglev)",
        "operator":                      "concept — Powell & Maise",
        "status":                        "concept",
        "launch_type":                   "maglev",
        "trl":                           2,
        "max_accel_g":                     30.0,
        "payload_leo_kg":                40_000,
        "payload_gto_kg":                15_000,
        "payload_escape_kg":             10_000,
        "fairing_volume_m3":                200,
        "list_price_usd":             1_600_000,
        "usd_per_kg_to_leo":                 40,
        "usd_per_kg_to_gto":                107,
        "usd_per_kg_to_escape":             160,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Superconducting maglev accelerator in an evacuated tube, "
                 "exiting at altitude through a magnetically-levitated tether. "
                 "The Gen-1 cargo variant is quoted near $40/kg — two orders "
                 "below anything flying — on a claimed ~$20B of infrastructure "
                 "and 30 g, which is survivable by hardware unlike the two rows "
                 "above.  TRL 2: no element of the launch tube has been built. "
                 "The $/kg assumes the capital is already sunk and the traffic "
                 "exists to amortise it, which is the assumption doing all the "
                 "work in every entry in this section.",
    },
    {
        "name":                          "Skylon / SABRE",
        "operator":                      "concept — Reaction Engines",
        "status":                        "concept",
        "launch_type":                   "airbreathing",
        "trl":                           4,
        "max_accel_g":                     3.0,
        "payload_leo_kg":                15_000,
        "payload_gto_kg":                 4_000,
        "payload_escape_kg":              2_000,
        "fairing_volume_m3":                140,
        "list_price_usd":            15_000_000,
        "usd_per_kg_to_leo":              1_000,
        "usd_per_kg_to_gto":              3_750,
        "usd_per_kg_to_escape":           7_500,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Air-breathing single-stage-to-orbit spaceplane: a precooler "
                 "chills Mach-5 intake air in ~1/100 s so a rocket engine can "
                 "breathe it to Mach 5.5, then closes the cycle. The precooler "
                 "was demonstrated at Mach-5 conditions in 2019 and is the only "
                 "part that was.  Reaction Engines Ltd entered administration in "
                 "October 2024 — status 'concept' here is a statement about the "
                 "company as much as the technology.",
    },
    {
        "name":                          "Sea Dragon",
        "operator":                      "concept — Truax / Aerojet 1962",
        "status":                        "concept",
        "launch_type":                   "chemical_rocket",
        "trl":                           2,
        "max_accel_g":                     4.0,
        "payload_leo_kg":               550_000,
        "payload_gto_kg":               200_000,
        "payload_escape_kg":            150_000,
        "fairing_volume_m3":              6_000,
        "list_price_usd":           300_000_000,
        "usd_per_kg_to_leo":                545,
        "usd_per_kg_to_gto":              1_500,
        "usd_per_kg_to_escape":           2_000,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Truax's 1962 sea-launched pressure-fed two-stage vehicle: "
                 "550 t to LEO, 23 m in diameter, built to shipyard tolerances "
                 "in 8 mm steel rather than to aerospace ones.  TRW reviewed the "
                 "design and found it sound.  It is here because it is the "
                 "canonical demonstration that launch cost is an engineering "
                 "CHOICE about tolerance and scale, not a physical constant — "
                 "the entire premise the $/kg column rests on.",
    },
    {
        "name":                          "Lunar mass driver",
        "operator":                      "concept — O'Neill 1974",
        "status":                        "concept",
        "launch_type":                   "kinetic",
        "origin":                        "lunar_surface",
        "trl":                           3,
        "max_accel_g":                    1_000.0,
        "payload_leo_kg":               100_000,     # per year, to lunar escape — see notes
        "payload_gto_kg":                     0,
        "payload_escape_kg":            100_000,
        "fairing_volume_m3":               np.nan,
        "list_price_usd":             1_000_000,
        "usd_per_kg_to_leo":                 10,
        "usd_per_kg_to_gto":             np.nan,
        "usd_per_kg_to_escape":              10,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "Electromagnetically launch lunar regolith to escape velocity "
                 "— 2.4 km/s, against Earth's 11.2 — with no atmosphere in the "
                 "way.  O'Neill and Snow built and ran a prototype at Princeton "
                 "in 1977.  The $/kg is electricity and amortisation, and it is "
                 "roughly two hundred times below the cheapest rocket here.\n"
                 "⚠️  The payload columns are ANNUAL THROUGHPUT, not per-launch "
                 "mass, and the origin is the lunar surface.  Module 4 departs "
                 "from Earth and prices a discrete launch, so it cannot read "
                 "either column correctly — which is why origin is gated rather "
                 "than merely status.  This row is a marker for a delivery "
                 "architecture the pipeline does not model, not an input to it.",
    },
    {
        "name":                          "Lunar space elevator",
        "operator":                      "concept — Pearson 1979",
        "status":                        "concept",
        "launch_type":                   "tether",
        "origin":                        "lunar_surface",
        "trl":                           2,
        "max_accel_g":                      0.2,
        "payload_leo_kg":                50_000,     # per year — see notes
        "payload_gto_kg":                     0,
        "payload_escape_kg":             50_000,
        "fairing_volume_m3":               np.nan,
        "list_price_usd":               500_000,
        "usd_per_kg_to_leo":                 10,
        "usd_per_kg_to_gto":             np.nan,
        "usd_per_kg_to_escape":              10,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "A tether from the lunar surface through Earth-Moon L1. "
                 "Unlike an Earth elevator this needs NO new material: the "
                 "Moon's shallow well and the L1 balance point put the required "
                 "specific strength inside what Zylon and M5 already deliver "
                 "(Pearson 1979; Eubanks & Radley 2016).  It is a manufacturing "
                 "and capital problem, not a materials-science one — the single "
                 "most under-appreciated entry in this table.\n"
                 "⚠️  Same caveats as the lunar mass driver: annual throughput, "
                 "lunar origin, gated.",
    },
    {
        "name":                          "Earth space elevator",
        "operator":                      "concept — Artsutanov 1960",
        "status":                        "concept",
        "launch_type":                   "tether",
        "trl":                           1,
        "max_accel_g":                      0.1,
        "payload_leo_kg":                20_000,     # per year — see notes
        "payload_gto_kg":                20_000,
        "payload_escape_kg":             20_000,
        "fairing_volume_m3":               np.nan,
        "list_price_usd":             2_000_000,
        "usd_per_kg_to_leo":                100,
        "usd_per_kg_to_gto":                100,
        "usd_per_kg_to_escape":             100,
        "reference_year":          _REF_YEAR_LAUNCH,
        "notes": "The one that needs a material nobody has.  A geostationary "
                 "tether wants ~50-100 GPa·cm³/g of specific strength; carbon "
                 "nanotube achieves it in single tubes millimetres long and "
                 "nothing has been spun into a macroscopic fibre within an "
                 "order of magnitude of it.  TRL 1, and unlike every other row "
                 "here the gap is physics of materials rather than money.  "
                 "Listed so that its absence is not read as an oversight, and "
                 "so the LUNAR elevator two rows up is not tarred with it.",
    },
]

_LAUNCH_STATUS_VALUES = {"operational", "development", "concept", "retired"}


def _apply_launch_defaults(rows: List[dict]) -> None:
    """Fill the v1.9.0 schema fields on rows that do not state them.

    Keeps a conventional expendable rocket's entry to the fields that make it
    that particular rocket, rather than restating `launch_type =
    "chemical_rocket"` twenty times.  Mutates in place, once, at import.
    """
    for row in rows:
        for key, default in _LAUNCH_DEFAULTS.items():
            row.setdefault(key, default)
        if row["status"] not in _LAUNCH_STATUS_VALUES:
            raise ValueError(
                f"launch vehicle {row['name']!r} has status {row['status']!r}; "
                f"Module 4 gates on this field, so it must be one of "
                f"{sorted(_LAUNCH_STATUS_VALUES)}"
            )


_apply_launch_defaults(LAUNCH_VEHICLES_REFERENCE)

print(f"✅  Launch vehicles reference loaded — {len(LAUNCH_VEHICLES_REFERENCE)} vehicles "
      f"({sum(1 for v in LAUNCH_VEHICLES_REFERENCE if v['status'] == 'operational')} operational, "
      f"{sum(1 for v in LAUNCH_VEHICLES_REFERENCE if v['status'] == 'development')} development, "
      f"{sum(1 for v in LAUNCH_VEHICLES_REFERENCE if v['status'] == 'concept')} concept, "
      f"{sum(1 for v in LAUNCH_VEHICLES_REFERENCE if v['status'] == 'retired')} retired)")


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

# ─── STORAGE CLASS AND TANKAGE MASS  (v1.9.0) ────────────────────────────────
# Until v1.9.0 this table computed `density_kg_per_L`, exported it, and nothing
# ever used it.  That is not a cosmetic gap: the mass a tank adds scales with
# the VOLUME it encloses, not with the propellant mass inside it, so leaving it
# out hands the low-density propellants a free ride.  LH2 is 0.0708 kg/L
# against kerolox at 1.015 — fourteen times the tank per kilogram burnt — and
# the model was awarding hydrolox its 452 s with no volumetric penalty at all.
# It is the same failure shape as the v1.10.0 electric stage: a mass in the
# rocket equation with no line anywhere else.
#
# `storage_class` is the taxonomy, and it is what decides how a kilogram is
# actually held:
#
#   deep_cryogen      LH2 at 20 K.  Thick MLI, vapour-cooled shields, the
#                     worst boil-off of anything that flies.
#   mild_cryogen      LOX 90 K / LCH4 112 K / LAr 87 K.  One thermal system
#                     serves oxidiser and fuel — the methalox argument.
#   storable_liquid   Hypergols, hydrazine, HTP, ionic liquids.  Room
#                     temperature, indefinitely.
#   benign_liquid     Water.  Storable, non-toxic, freezes rather than boils,
#                     and the only class this pipeline can MAKE on site.
#   supercritical_gas Xe / Kr / GN2 in a COPV.  Tank mass is set by storage
#                     pressure, not by insulation.
#   sublimating_solid Iodine, PTFE, liquid-metal reservoirs.  Near-ambient
#                     pressure, so the tank is almost free — this is iodine's
#                     entire pitch.
#   solid_motor       APCP.  The "tank" is a loaded case that also takes
#                     chamber pressure and thrust.
#   propellantless    Sails and tethers.  No tank at all.
#
# ── Deriving kg of tank per litre ────────────────────────────────────────────
# A thin-walled sphere at internal pressure p has hoop stress σ = p·r/2t, so
# t = p·r/2σ and
#
#     m_tank = 4πr²·t·ρ_mat = 2πr³·p·ρ_mat/σ = 1.5 · p · V / (σ/ρ)_mat
#
# — exactly proportional to volume, independent of size.  For a low-pressure
# liquid tank the ullage pressure term alone underpredicts (bosses, baffles,
# PMDs, mounts and thrust structure are not pressure-driven), so the base
# figure is taken from flight articles rather than from the formula:
#
#     Shuttle ET          26,535 kg dry / 2,058,000 L  = 0.0129 kg/L
#     Falcon 9 stage 2    ~3,500 kg struct / 105,900 L = 0.033  kg/L
#     Centaur III         ~1,880 kg struct /  54,000 L = 0.035  kg/L
#
# 0.025 kg/L sits between the ET (which is a big dumb tank, so cheap per litre)
# and the two upper stages (which carry avionics and thrust structure in the
# figures above).  Class multipliers are then anchored one article each — see
# _STORAGE_CLASS_TANK_MULT.
#
# ⚠️  SOFT, and it errs the safe way.  Real tank mass is the pressure term
# (∝ V, exact) plus insulation and minimum-gauge terms (∝ area, so ∝ V^⅔).
# Collapsing both into ∝ V therefore OVERSTATES the penalty on a very large
# tank and understates it on a very small one.  NASA's large NTP studies get
# an LH2 tank down near 12-15% of propellant mass at ~38 t of hydrogen; this
# model gives ~53% because its stages hold tonnes, not tens of tonnes.  The
# direction is deliberate: the propellants that most want a generous tank
# model are the speculative ones, and this pipeline does not exist to
# manufacture viability for them.
_TANK_BASE_KG_PER_L = 0.025

# Burst performance factor PV/W for a flight-qualified composite-overwrapped
# pressure vessel, ~40 km (× g0 = 392 kJ/kg).  Standard COPV figure of merit;
# NASA-STD-(I)-5019 class hardware.  Burst is taken at 1.5 × operating.
_COPV_PERFORMANCE_J_PER_KG = 392_000.0

# Passive boil-off for LIQUID argon, %/day.  Derived from the LOX rate already
# in this table rather than asserted, because the whole point of the v1.10.0
# argon split is that a cryogen has to pay what a cryogen costs.
#
# The kerolox row is 0.015%/day and its own comment says why: RP-1 is storable
# and only the LOX half boils, weighted by the mix ratio.  At O/F 2.30 the LOX
# mass fraction is 2.30/3.30 = 0.697, so LOX alone is 0.015/0.697 = 0.0215%/day.
#
# Scaling that to argon at the same tank and the same MLI, boil-off is heat leak
# over the energy it takes to boil the contents, so two ratios:
#
#   heat leak        ∝ ΔT     (300 − 87.3) / (300 − 90.2)      = 1.014
#   energy to boil   ∝ ρ·h_fg  (1.141 × 213.1) / (1.395 × 161.1) = 1.082
#
# giving 0.0215 × 1.014 × 1.082 = 0.0236, rounded to 0.024%/day.  Argon boils
# slightly FASTER than oxygen: 3 K colder, and its latent heat per litre is 8%
# lower.  Over a four-year hold that is a factor of 1.41 on the return
# propellant — small next to hydrolox's 2.1, and not nothing.
_LAR_BOILOFF_PCT_PER_DAY = 0.024

# ─────────────────────────────────────────────────────────────────────────────
# THRUSTER SYSTEMS  (v1.10.0) — the DEVICE, as distinct from the propellant
# ─────────────────────────────────────────────────────────────────────────────
# PROPELLANTS_REFERENCE has always been half a propellant table and half a
# propulsion-system table — `isp_vac_s`, `restartable` and `dv_penalty_factor`
# are properties of the DEVICE, not of the chemical.  What it never carried was
# anything about whether the device can be built at the size this pipeline
# flies, and that omission ran one way:
#
#     Module 4 sized an electric stage by POWER alone.  Buy enough kilowatts
#     and any entry in the table became a cargo tug.
#
# So a full cislunar run had a third of its winning missions on PULSED PLASMA
# THRUSTERS and a quarter on ELECTROSPRAY — devices that have flown, and have
# flown producing MICRONEWTONS.  EO-1's PPT was 860 µN.  LISA Pathfinder's
# colloid thrusters were 5-30 µN each.  The pipeline was asking them for ~10 N.
#
# Note the asymmetry this closes, and it is the same one the user spotted:
# LAUNCH is modelled as an integrated vehicle with a payload it can actually
# lift, while IN-SPACE propulsion was modelled as a bare specific impulse.  One
# side had a capacity limit and the other did not.
#
# Two columns fix it, and neither is a threshold — the mass does the work, the
# same way propellant tankage disqualifies low-density propellants without
# anyone naming a cutoff:
#
#   thruster_kg_per_n   Thruster-head mass per newton of thrust.  Module 4
#                       derives the thrust its mission needs (T = ṁ·ve, which
#                       is just momentum flux and owes nothing to efficiency)
#                       and multiplies.  A device that makes µN per kilogram
#                       reports thousands of tonnes of thruster and dies in the
#                       rocket equation.  No cutoff, no judgement call.
#
#   thruster_efficiency Total thrust efficiency, replacing the single global
#                       0.60 that every electric row shared.  This one is
#                       nearly as decisive as the mass: a PPT converts about
#                       8% of its input into jet power against a gridded ion
#                       thruster's 70%, so it needs ~9x the array for the same
#                       thrust — and the array is mass too.
#
# `thrust_scaling` records WHY a device lands where it does, and it is the real
# physical divide:
#
#   continuous   Thrust comes from a plasma discharge or a beam whose area you
#                can enlarge.  Scaling up means building a BIGGER device, so
#                kg/N stays roughly flat with size and lands at 6-90 kg/N
#                across every mature technology here.
#   replicated   Thrust comes from discrete emitters, needles or pulses.
#                Scaling up means building MORE devices, so kg/N is fixed by
#                the single unit and never improves — 2,500-10,000 kg/N.
#                Accion's own literature puts a cargo-scale electrospray at
#                "millions of emitters"; that sentence was already in this
#                table's notes field and nothing read it.
#
# Every figure below is thruster HEAD mass over demonstrated thrust, from a
# flight or ground article.  The PPU is separate and scales with power — see
# the "Power processing unit specific mass" ops row — because a PPU is a power
# converter and does not care what it is feeding.
#
# ⚠️  The replicated figures are deliberately GENEROUS to the technology.
# Electrospray is entered at 10,000 kg/N when ST7-DRS heads work out nearer
# 20,000-100,000; the conclusion does not depend on which end you take, and
# taking the favourable end means nobody can claim the result was engineered.
#
# ⚠️  Iodine is the judgement call in this table, and it matters because iodine
# wins most of the catalog.  Its only FLIGHT unit is ThrustMe's 1.1 mN cubesat
# thruster, which works out near 1,100 kg/N — but that is a scale artifact of a
# 1U device, not a property of iodine.  Iodine runs in Hall and gridded
# thrusters whose bodies are the same hardware xenon uses; what it genuinely
# costs is a heated feed line and corrosion-tolerant materials.  So it is
# entered as Hall-class mass with a penalty (60 against xenon Hall's 30), and
# `status` cannot express that its cargo-scale heritage is ground-test only.
# If you want to be harsh with iodine, this is the number to move — but move it
# for a reason, and record the reason.
_THRUSTER_SYSTEMS = {
    # name fragment           kg/N     η     scaling        anchor
    "Xenon  (Hall / ion)":      (54.0, 0.70, "continuous"),  # NEXT-C 12.7 kg / 236 mN, 70% total
    "Krypton  (Hall)":          (35.0, 0.45, "continuous"),  # SPT-140 body, Kr ~85% of Xe thrust and ~10 pts less efficient
    "Argon  (Hall / ion)":      (40.0, 0.40, "continuous"),  # same body again; Ar lower still
    "Argon  (Hall / ion, cryogenic)": (40.0, 0.40, "continuous"),
    "Iodine  (Hall / gridded)": (60.0, 0.45, "continuous"),  # see the iodine caveat above
    "Water  (gridded ion / ECR)": (80.0, 0.35, "continuous"),  # ECR ion; water is hard to ionise cleanly
    "Water  (electrothermal / resistojet)": (10.0, 0.75, "continuous"),  # resistojet: high thrust density, low Isp
    "Hydrazine arcjet":         ( 6.0, 0.35, "continuous"),  # MR-509 1.5 kg / 258 mN
    "Mercury ion  (RETIRED)":   (54.0, 0.65, "continuous"),  # gridded-ion class
    "Nuclear electric  (NEP, xenon)": (54.0, 0.70, "continuous"),
    "VASIMR  (argon, variable Isp)":  (53.0, 0.50, "continuous"),  # VX-200 ~300 kg / 5.7 N
    "MPD  (lithium magnetoplasmadynamic)": (40.0, 0.40, "continuous"),
    # ── Concepts.  UNANCHORED, and they are here so the guard below cannot be
    # satisfied by silence.  Both are gated out of the default search by
    # `operational_propellants_only`; if you ever ungate them, these two
    # numbers are the ones to distrust first.  Direct fusion drive is pinned to
    # Princeton's PFRC-2 sketch (a few newtons from a ~10 t engine).  For
    # antimatter there is no engineering basis whatsoever, so it is given the
    # same figures rather than anything flattering — an unanchored row should
    # never be the reason something wins.
    "Direct fusion drive":      (2_000.0, 0.50, "continuous"),
    "Antimatter-catalysed":     (2_000.0, 0.50, "continuous"),
    # ── Replicated: thrust per EMITTER, so mass is linear in thrust forever ──
    "Electrospray  (ionic liquid)": (10_000.0, 0.65, "replicated"),  # TILE-3 ~100 µN/kg-class; generous end
    "FEEP  (indium field emission)": (2_500.0, 0.60, "replicated"),  # Enpulsion IFM Nano 0.35 mN / 0.9 kg
    "PPT  (PTFE pulsed plasma)":     (5_000.0, 0.08, "replicated"),  # EO-1 PPT 860 µN / 4.9 kg; PPT efficiency is 5-13%
}


def _apply_thruster_data(df: pd.DataFrame) -> None:
    """Attach device-level columns to the propellant frame, in place.

    Chemical and propellantless rows get NaN — they are not electric, Module 4
    never sizes a power plant for them, and a number there would imply a
    constraint that does not apply.  Any ELECTRIC row missing from
    `_THRUSTER_SYSTEMS` raises rather than defaulting: a silent default is how
    a micronewton thruster got flown as a cargo tug in the first place.

    "Electric" is tested as `dv_penalty_factor > 1`, which is the SAME test
    Module 4 uses to decide whether to size a power plant (`is_electric` in
    `_evaluate_combo_at_ratio`).  Keying off `type` instead would have let
    `nuclear_electric` through — it is electric propulsion, it draws the
    penalty, and it is not spelled "electric".
    """
    kg_per_n, eff, scaling = [], [], []
    for _, row in df.iterrows():
        name = str(row["name"])
        entry = _THRUSTER_SYSTEMS.get(name)
        if entry is None:
            if float(row.get("dv_penalty_factor", 1.0) or 1.0) > 1.0:
                raise KeyError(
                    f"electric propellant {name!r} has no _THRUSTER_SYSTEMS "
                    f"entry — add one with an anchor rather than letting "
                    f"Module 4 size it on power alone"
                )
            kg_per_n.append(float("nan"))
            eff.append(float("nan"))
            scaling.append(None)
            continue
        kg_per_n.append(entry[0])
        eff.append(entry[1])
        scaling.append(entry[2])
    df["thruster_kg_per_n"]   = kg_per_n
    df["thruster_efficiency"] = eff
    df["thrust_scaling"]      = scaling


_STORAGE_CLASS_TANK_MULT = {
    # class            × base   anchor
    "storable_liquid":   1.00,  # 0.025 kg/L → NTO at 1.45 kg/L is 1.7% of propellant mass
    "benign_liquid":     0.90,  # water; no cryo insulation, no toxicity handling
    "mild_cryogen":      1.15,  # LOX at 1.141 kg/L → 2.5%; MLI but no vapour-cooled shield
    "deep_cryogen":      1.50,  # LH2; hydrolox blend lands at 10.4% vs Centaur's ~9.7% measured
    "sublimating_solid": 0.45,  # iodine at 4.93 kg/L → 0.23%; a heated reservoir, not a tank
    "solid_motor":       5.00,  # APCP at 1.80 kg/L → 6.9%; Star 48B burnout/propellant is 6.4%
    "propellantless":    0.00,
}


def _tank_kg_per_L(storage_class: str, pressure_mpa: float = 0.3) -> float:
    """kg of tankage per litre of propellant stored, by storage class.

    `pressure_mpa` is read only for `supercritical_gas`, where the tank is a
    COPV and its mass is set by storage pressure rather than by insulation.
    Everything else takes a flight-anchored multiple of _TANK_BASE_KG_PER_L.
    """
    if storage_class == "supercritical_gas":
        # 1.5·p/(PV/W) is kg per CUBIC METRE (Pa / (J/kg) = kg/m³); this table
        # quotes tankage per LITRE, so divide by 1,000.
        return 1.5 * (float(pressure_mpa) * 1e6) / _COPV_PERFORMANCE_J_PER_KG / 1_000.0
    try:
        return _TANK_BASE_KG_PER_L * _STORAGE_CLASS_TANK_MULT[storage_class]
    except KeyError:
        raise KeyError(
            f"unknown storage_class {storage_class!r} — add it to "
            f"_STORAGE_CLASS_TANK_MULT with an anchor, do not default it"
        ) from None


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
    # Combined tankage.  Fuel and oxidiser sit in SEPARATE tanks at different
    # temperatures, so the two contributions are summed over their own volumes
    # rather than averaged — which is the whole reason hydrolox is punished and
    # methalox is not: LOX and LCH4 share a thermal class, LOX and LH2 do not.
    v_fuel = fuel_frac / fuel["density_kg_per_L"]
    v_ox   = ox_frac   / ox["density_kg_per_L"]
    tank_per_kg = (
        v_fuel * _tank_kg_per_L(fuel["storage_class"], fuel.get("pressure_mpa", 0.3))
        + v_ox * _tank_kg_per_L(ox["storage_class"],   ox.get("pressure_mpa", 0.3))
    )
    return {
        "density_kg_per_L":   rho,
        "ref_cost_usd_per_kg": cost_kg,
        "fuel_mass_fraction":  fuel_frac,
        "ox_mass_fraction":    ox_frac,
        "tank_kg_per_L":       tank_per_kg * rho,
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
#
# v1.9.0 added `storage_class` to every component (and `pressure_mpa` to the
# supercritical ones) so tankage mass can be derived rather than guessed, plus
# the components needed by the propellants the table had been missing:
#
#   UDMH       Wikipedia / Astronautix — Proton and Long March heritage.
#              ~$80/kg; Chinese and Russian production, no Western market.
#   Aerozine-50 50/50 UDMH-hydrazine by mass, Titan / Apollo SPS.
#   HTP-98     98% hydrogen peroxide.  Bulk ~$5/kg (Evonik / Peroxide Propulsion
#              propellant-grade quotes 2024).  Cheapest storable oxidiser there is.
#   GN2        Cold gas.  Nitrogen is nearly free; the COPV is the whole cost.
#              Stored at 30 MPa, ρ ≈ 0.25 kg/L.
#   Krypton    Bulk industrial ~$300/kg (air-separation by-product; roughly 30×
#              cheaper than Xe and about 10× more abundant in air).  Stored
#              supercritical at ~18 MPa, ρ ≈ 0.55 kg/L — much worse than Xe,
#              which is why the tank term matters here.
#   Iodine     ~$60/kg technical grade.  ρ 4.93 kg/L as a SOLID at ambient
#              pressure: the densest storable electric propellant known.
#   Water      Spaceflight-grade deionised, ~$2/kg delivered.  The only entry
#              in this table an asteroid can supply.
#   ASCENT     AF-M315E hydroxylammonium-nitrate monoprop.  ~$500/kg reflects
#              pilot-scale production, not chemistry — GPIM flew ~1 kg of it.
#   APCP       Ammonium-perchlorate composite, HTPB binder + Al.  ~$15/kg for
#              the grain; the case and nozzle dominate the article cost.
#   PTFE       Teflon bar stock for pulsed-plasma thrusters, ~$25/kg.
#   EMI-BF4    Ionic liquid for electrospray, ~$2,000/kg at research volume.
#   Indium     FEEP propellant, ~$250/kg; ρ 7.31 kg/L liquid.
#   Mercury    Historic ion propellant (SERT-II, ATS-6).  ~$60/kg, ρ 13.53 —
#              still the best storage density ever flown, and banned under the
#              2013 Minamata Convention.  Present so the record is complete.
#   Lithium    MPD-thruster propellant, ~$80/kg, heated liquid reservoir.
#   Ammonia    Arcjet / resistojet working fluid, ~$1.50/kg bulk.
#   LF2        Liquid fluorine, ~$20/kg.  Highest-performing practical oxidiser
#              and completely unflyable — see the Li/F2/H2 row.
#   Al-powder  Aluminium fuel for ALICE-class metal/water propellants, ~$3/kg.
#   CO         Carbon monoxide, liquid at 81 K.  Makeable from carbonaceous
#              regolith; pairs with LOX for a fully-ISRU chemical stage.
_COMPONENTS = {
    "RP-1":      {"density_kg_per_L": 0.810, "cost_usd_per_kg":      2.50, "storage_class": "storable_liquid"},
    "LH2":       {"density_kg_per_L": 0.0708,"cost_usd_per_kg":     10.00, "storage_class": "deep_cryogen"},   # base + handling
    "LCH4":      {"density_kg_per_L": 0.422, "cost_usd_per_kg":      0.40, "storage_class": "mild_cryogen"},   # ~$400/tonne open market
    "LOX":       {"density_kg_per_L": 1.141, "cost_usd_per_kg":      0.20, "storage_class": "mild_cryogen"},
    "N2O4":      {"density_kg_per_L": 1.450, "cost_usd_per_kg":     35.00, "storage_class": "storable_liquid"},
    "MMH":       {"density_kg_per_L": 0.870, "cost_usd_per_kg":    100.00, "storage_class": "storable_liquid"},
    "Hydrazine": {"density_kg_per_L": 1.010, "cost_usd_per_kg":     75.00, "storage_class": "storable_liquid"},  # DOD ref + handling
    "Xenon":     {"density_kg_per_L": 2.000, "cost_usd_per_kg": 10_000.00, "storage_class": "supercritical_gas", "pressure_mpa": 10.0},
    # v1.10.0.  Argon used to be ONE component carrying liquid-argon density
    # (1.395 kg/L, normal boiling point 87.3 K) with the storage class of a
    # cryogen and a boil-off of zero — the row's own two comments said "liquid
    # NBP (cryogenic storage)" and "stored supercritical at ambient
    # temperature" three lines apart.  You cannot have both: 1.395 kg/L only
    # exists at 87 K, and at 87 K it boils.  The combination handed argon the
    # lightest tank of any gas in the table AND exemption from the hold-time
    # penalty every other cryogen pays, which is a free resource rather than a
    # propellant.  Split into the two real articles instead, and let Module 4's
    # per-asteroid search decide which one a mission flies.
    #
    #   ArgonSC   what has actually flown.  Every noble-gas EP system ever
    #             launched — xenon on Dawn/BepiColombo/SMART-1, krypton on
    #             Starlink v1, argon on Starlink V2 — stores its propellant
    #             supercritical in a COPV at ambient temperature.  Density is
    #             derived below, not asserted.
    #   ArgonLIQ  the large-stage architecture: liquid at 87.3 K under MLI,
    #             which is how you would really feed a multi-tonne NEP stage.
    #             Studied, never flown, so the propellant row built on it is
    #             tagged `development` and the default search excludes it.
    #
    # ArgonSC density: Peng-Robinson at 293.15 K / 18 MPa (the same bottle
    # pressure as the krypton row) gives Z = 0.919 and ρ = 0.321 kg/L; a
    # generalised-compressibility reading at Tr = 1.945, Pr = 3.70 gives
    # Z ≈ 0.99 and ρ = 0.298.  0.30 is the round figure between them.
    #
    # Note the result barely moves with pressure, and that is the physics
    # rather than a coincidence: COPV mass goes as 1.5·p/(PV/W) and stored
    # density goes as p·M/(ZRT), so the tank FRACTION is ~1.5·Z·R·T/(M·(PV/W))
    # — pressure cancels and molar mass is what is left.  Argon at 30 MPa pays
    # 22.3% against 22.9% at 18 MPa.  Xenon 1.9% / krypton 12.5% / argon 22.9%
    # is just M = 131.3 / 83.8 / 39.9 read backwards, and it is the whole
    # reason a cheap propellant is not automatically a good one.
    "ArgonSC":   {"density_kg_per_L": 0.300, "cost_usd_per_kg":     10.00, "storage_class": "supercritical_gas", "pressure_mpa": 18.0},
    "ArgonLIQ":  {"density_kg_per_L": 1.395, "cost_usd_per_kg":     10.00, "storage_class": "mild_cryogen"},     # liquid at NBP 87.3 K

    # ── v1.9.0 additions ─────────────────────────────────────────────────────
    "UDMH":      {"density_kg_per_L": 0.793, "cost_usd_per_kg":     80.00, "storage_class": "storable_liquid"},
    "Aerozine50":{"density_kg_per_L": 0.903, "cost_usd_per_kg":     90.00, "storage_class": "storable_liquid"},
    "HTP-98":    {"density_kg_per_L": 1.431, "cost_usd_per_kg":      5.00, "storage_class": "storable_liquid"},
    "GN2":       {"density_kg_per_L": 0.250, "cost_usd_per_kg":      1.00, "storage_class": "supercritical_gas", "pressure_mpa": 30.0},
    "Krypton":   {"density_kg_per_L": 0.550, "cost_usd_per_kg":    300.00, "storage_class": "supercritical_gas", "pressure_mpa": 18.0},
    "Iodine":    {"density_kg_per_L": 4.930, "cost_usd_per_kg":     60.00, "storage_class": "sublimating_solid"},
    "Water":     {"density_kg_per_L": 1.000, "cost_usd_per_kg":      2.00, "storage_class": "benign_liquid"},
    "ASCENT":    {"density_kg_per_L": 1.470, "cost_usd_per_kg":    500.00, "storage_class": "storable_liquid"},
    "APCP":      {"density_kg_per_L": 1.800, "cost_usd_per_kg":     15.00, "storage_class": "solid_motor"},
    "PTFE":      {"density_kg_per_L": 2.200, "cost_usd_per_kg":     25.00, "storage_class": "sublimating_solid"},
    "EMI-BF4":   {"density_kg_per_L": 1.240, "cost_usd_per_kg":  2_000.00, "storage_class": "storable_liquid"},
    "Indium":    {"density_kg_per_L": 7.310, "cost_usd_per_kg":    250.00, "storage_class": "sublimating_solid"},
    "Mercury":   {"density_kg_per_L":13.530, "cost_usd_per_kg":     60.00, "storage_class": "storable_liquid"},
    "Lithium":   {"density_kg_per_L": 0.534, "cost_usd_per_kg":     80.00, "storage_class": "storable_liquid"},
    "Ammonia":   {"density_kg_per_L": 0.682, "cost_usd_per_kg":      1.50, "storage_class": "storable_liquid"},
    "LF2":       {"density_kg_per_L": 1.505, "cost_usd_per_kg":     20.00, "storage_class": "mild_cryogen"},
    "Al-powder": {"density_kg_per_L": 2.700, "cost_usd_per_kg":      3.00, "storage_class": "solid_motor"},
    "CO":        {"density_kg_per_L": 0.789, "cost_usd_per_kg":      1.00, "storage_class": "mild_cryogen"},
}

_kerolox    = _blend(2.30, _COMPONENTS["RP-1"],      _COMPONENTS["LOX"])
_hydrolox   = _blend(6.00, _COMPONENTS["LH2"],       _COMPONENTS["LOX"])
_methalox   = _blend(3.60, _COMPONENTS["LCH4"],      _COMPONENTS["LOX"])
_mmh_nto    = _blend(1.65, _COMPONENTS["MMH"],       _COMPONENTS["N2O4"])
_udmh_nto   = _blend(2.60, _COMPONENTS["UDMH"],      _COMPONENTS["N2O4"])
_a50_nto    = _blend(2.00, _COMPONENTS["Aerozine50"],_COMPONENTS["N2O4"])
_htp_rp1    = _blend(7.00, _COMPONENTS["RP-1"],      _COMPONENTS["HTP-98"])
_co_lox     = _blend(0.57, _COMPONENTS["CO"],        _COMPONENTS["LOX"])
_al_water   = _blend(1.00, _COMPONENTS["Al-powder"], _COMPONENTS["Water"])
# Li/F2/H2 tripropellant: Rocketdyne's 1960s test-stand mixture.  Blended in
# two steps because _blend takes a pair — lithium against fluorine first, then
# the hydrogen folded in as the "fuel" against that pair as the "oxidiser".
# 2Li + F2 → 2LiF is stoichiometric at F2/Li = 2.73; the engine ran fuel-rich
# at roughly 2.0, with hydrogen at ~8% of total mass as a low-molecular-weight
# working fluid.  Approximate — the row is gated out and the exact split moves
# Isp by a few seconds, not by a category.
_li_f2      = _blend(2.00, _COMPONENTS["Lithium"],   _COMPONENTS["LF2"])
_lifh       = _blend(11.3, _COMPONENTS["LH2"],
                     {"density_kg_per_L": _li_f2["density_kg_per_L"],
                      "cost_usd_per_kg":  _li_f2["ref_cost_usd_per_kg"],
                      "storage_class":    "mild_cryogen"})

# ─── MATURITY GATE  (v1.9.0) ─────────────────────────────────────────────────
# `status` on a propellant means exactly what it means on a launch vehicle, and
# Module 4 filters on it the same way (`operational_propellants_only`):
#
#   operational   Has flown and moved a real spacecraft.  In the default search.
#   development   Hardware exists and has been fired, but not in flight.
#   concept       Designed on paper, or demonstrated only as physics.
#   retired       Flew, and will not fly again — kept so the record is complete
#                 and so nobody re-derives it as a bright idea.
#
# Two flags matter as much as the status, because they disqualify a propellant
# from THIS mission profile regardless of how mature it is:
#
#   restartable   A return mission fires its second burn years after launch.
#                 A solid motor cannot do that, so APCP is in the table and
#                 permanently out of the search.  Documented, not silent.
#   propellantless Sails and tethers have no mass ratio, so the rocket equation
#                 says a sail can move any payload for free.  It cannot — its
#                 characteristic acceleration is ~0.1 mm/s², which is fine for a
#                 6 kg cubesat and meaningless for a hold full of ore.  Flagged
#                 so Module 4 excludes them rather than reporting infinite
#                 payload.  Sizing a sail properly needs a thrust-limited
#                 trajectory model this pipeline does not have.
#
# `isru_feed_kg_per_kg` / `isru_feed_material` generalise what used to be a
# hardcoded hydrolox-only check.  A propellant an asteroid can supply is worth
# far more than its Isp suggests, and water is not the only route: a steam
# rocket burns the water directly at 1.0 kg feed per kg propellant against
# hydrolox's 1.286, and a mass driver throws raw regolith.

PROPELLANTS_REFERENCE: List[dict] = [
    # ═════════════════════════════════════════════════════════════════════════
    # OPERATIONAL — chemical
    # ═════════════════════════════════════════════════════════════════════════
    {
        "name":                  "kerolox  (RP-1 / LOX)",
        "type":                  "bipropellant",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1957,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "mild_cryogen",
        "tank_kg_per_L":         _kerolox["tank_kg_per_L"],
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.015,   # RP-1 is storable; the LOX half boils.  Weighted by the 1:2.30 mix ratio.
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
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1961,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "deep_cryogen",
        "tank_kg_per_L":         _hydrolox["tank_kg_per_L"],
        # Stoichiometric water demand for an ISRU hydrolox stage: electrolysis
        # yields 8 kg O2 per kg H2, and a 6:1 O/F stage burns 9/(1+6) kg of
        # water per kg of propellant.  This is the number Module 4 used to
        # carry as a hardcoded constant for the only ISRU propellant it knew.
        "isru_feed_kg_per_kg":   9.0 / 7.0,
        "isru_feed_material":    "water",
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.05,   # The worst case by far.  LH2 boils at 20 K and has the lowest heat of vaporisation of any propellant; even with multi-layer insulation and an active cryocooler, long-duration storage runs 0.03-0.1%/day.  This is why no flown mission has ever performed a deep-space arrival burn on hydrolox after a multi-year cruise -- Centaur is rated for hours of loiter, not years.
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
        "status":                "operational",
        "trl":                   9,
        "first_flight":          2023,   # Zhuque-2, first methalox vehicle to orbit (Jul 2023)
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "mild_cryogen",
        "tank_kg_per_L":         _methalox["tank_kg_per_L"],
        # Sabatier from asteroid water plus carbonaceous CO2 is possible in
        # principle, but it needs a carbon source AND hydrogen AND a reactor,
        # and this pipeline prices neither the reactor nor the carbon.  Left
        # unavailable rather than credited on a maybe.
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.012,   # LCH4 boils at 112 K, close enough to LOX (90 K) that a single thermal system serves both -- the 'space-storable cryogen' argument for methalox.
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
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1965,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _mmh_nto["tank_kg_per_L"],
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,   # Storable at room temperature indefinitely.  Voyager still had usable hydrazine after 45 years.
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
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1960,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("storable_liquid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,   # Storable indefinitely.
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
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1998,   # Deep Space 1 / NSTAR
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "supercritical_gas",
        "tank_kg_per_L":         _tank_kg_per_L("supercritical_gas", 10.0),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,   # Stored supercritical at ambient temperature; no boil-off.
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
        "status":                "operational",
        "trl":                   9,
        "first_flight":          2023,   # Starlink V2 mini
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "supercritical_gas",
        "tank_kg_per_L":         _tank_kg_per_L("supercritical_gas", 18.0),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,   # Ambient-temperature COPV; nothing to boil.
        "isp_vac_s":             1_500,
        "exhaust_vel_m_per_s":   1_500 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["ArgonSC"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["ArgonSC"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["ArgonSC"]["cost_usd_per_kg"]
                                 * _COMPONENTS["ArgonSC"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Starlink-V2 thruster choice (SpaceX claims 2.4× thrust, 1.5× Isp "
                 "of their previous Kr design).  Bulk industrial $7-15/kg per "
                 "SETS Space 2024; used $10/kg midpoint.\n"
                 "v1.10.0: stored SUPERCRITICAL at 18 MPa and ambient "
                 "temperature, 0.30 kg/L, which is what has flown — no spacecraft "
                 "has ever carried cryogenic argon.  Until v1.10.0 this row took "
                 "liquid-argon density (1.395 kg/L, 87.3 K) and a boil-off of "
                 "zero at the same time, which gave it the lightest tank of any "
                 "gas here and no cryogenic hold penalty.  Honestly stored it "
                 "pays 22.9% of its own mass in COPV against krypton's 12.5% and "
                 "xenon's 1.9% — argon is the LIGHTEST noble gas, so it is the "
                 "worst of the three to bottle, and $10/kg does not buy that "
                 "back.  The cryogenic article is a separate row below.",
    },

    # ═════════════════════════════════════════════════════════════════════════
    # OPERATIONAL — chemical, added v1.9.0
    # ═════════════════════════════════════════════════════════════════════════
    {
        "name":                  "UDMH / NTO  (hypergolic)",
        "type":                  "bipropellant",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1965,   # Proton-K
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _udmh_nto["tank_kg_per_L"],
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             318,
        "exhaust_vel_m_per_s":   318 * G0_M_S2,
        "density_kg_per_L":      _udmh_nto["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _udmh_nto["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _udmh_nto["ref_cost_usd_per_kg"] * _udmh_nto["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Proton and Long March heritage; still the most-flown storable "
                 "bipropellant by tonnage.  Vac Isp 318 s (Astronautix N2O4/UDMH) "
                 "at 2.6 O/F.  Slightly worse than MMH/NTO and considerably more "
                 "carcinogenic — present for completeness, not because it wins.",
    },
    {
        "name":                  "Aerozine-50 / NTO  (hypergolic)",
        "type":                  "bipropellant",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1964,   # Titan II / Apollo SPS
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _a50_nto["tank_kg_per_L"],
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             320,
        "exhaust_vel_m_per_s":   320 * G0_M_S2,
        "density_kg_per_L":      _a50_nto["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _a50_nto["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _a50_nto["ref_cost_usd_per_kg"] * _a50_nto["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "50/50 UDMH-hydrazine by mass.  Apollo Service Propulsion System "
                 "and the Titan family; the engine that had to light after eight "
                 "days in cislunar space and always did.  Vac Isp 320 s "
                 "(Astronautix AJ10-137).",
    },
    {
        "name":                  "Green monoprop  (ASCENT / AF-M315E)",
        "type":                  "monopropellant",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          2019,   # NASA GPIM
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("storable_liquid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             235,
        "exhaust_vel_m_per_s":   235 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["ASCENT"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["ASCENT"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["ASCENT"]["cost_usd_per_kg"]
                                 * _COMPONENTS["ASCENT"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Hydroxylammonium nitrate monoprop.  Flown on NASA's Green "
                 "Propellant Infusion Mission (2019); the Swedish LMP-103S "
                 "equivalent flew earlier on PRISMA (2010).  Isp 235 s and "
                 "ρ 1.47 kg/L beat hydrazine on BOTH counts — ~50% more "
                 "density-impulse — and it is not acutely toxic, which is a "
                 "ground-handling saving this model does not price.  The $500/kg "
                 "is pilot-scale production, not chemistry.",
    },
    {
        "name":                  "HTP  (98% peroxide monoprop)",
        "type":                  "monopropellant",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1949,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("storable_liquid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.002,   # slow catalytic self-decomposition, not boil-off; ~1%/yr in a passivated tank
        "isp_vac_s":             165,
        "exhaust_vel_m_per_s":   165 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["HTP-98"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["HTP-98"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["HTP-98"]["cost_usd_per_kg"]
                                 * _COMPONENTS["HTP-98"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Silver-screen decomposition.  Centaur RCS, Soyuz turbopump gas "
                 "generator, Black Arrow.  Cheapest propellant in this table at "
                 "~$5/kg and the lowest Isp of any liquid in it — the reason it "
                 "is here is the boil-off column: 0.002%/day is self-"
                 "decomposition, not evaporation, so unlike a cryogen the loss "
                 "does not accelerate with mission length.",
    },
    {
        "name":                  "HTP / RP-1  (peroxide bipropellant)",
        "type":                  "bipropellant",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1969,   # Black Arrow R1
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _htp_rp1["tank_kg_per_L"],
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.002,
        "isp_vac_s":             320,
        "exhaust_vel_m_per_s":   320 * G0_M_S2,
        "density_kg_per_L":      _htp_rp1["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _htp_rp1["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _htp_rp1["ref_cost_usd_per_kg"] * _htp_rp1["density_kg_per_L"],
        "yfinance_proxy":        "heating_oil",
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Black Arrow flew HTP/kerosene to orbit in 1971 — the only "
                 "British orbital launch.  Isp 320 s vac at 7:1 O/F, ρ 1.30 kg/L, "
                 "fully storable, and the cheapest bipropellant here.  The "
                 "combination that keeps getting rediscovered and keeps losing to "
                 "kerolox on Isp.",
    },
    {
        "name":                  "Cold gas  (GN2)",
        "type":                  "cold_gas",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1961,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "supercritical_gas",
        "tank_kg_per_L":         _tank_kg_per_L("supercritical_gas", 30.0),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             70,
        "exhaust_vel_m_per_s":   70 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["GN2"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["GN2"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["GN2"]["cost_usd_per_kg"]
                                 * _COMPONENTS["GN2"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "The simplest thruster that exists and the worst.  Isp 70 s, and "
                 "at 30 MPa the COPV masses 46% of the nitrogen it holds — the "
                 "clearest demonstration in this table of why tankage belongs in "
                 "the rocket equation.  Present as the floor of the Isp range, "
                 "not as a candidate.",
    },
    {
        "name":                  "Solid  (APCP)",
        "type":                  "solid",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1958,
        "restartable":           False,   # ← disqualifying: see notes
        "propellantless":        False,
        "storage_class":         "solid_motor",
        "tank_kg_per_L":         _tank_kg_per_L("solid_motor"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             285,
        "exhaust_vel_m_per_s":   285 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["APCP"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["APCP"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["APCP"]["cost_usd_per_kg"]
                                 * _COMPONENTS["APCP"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Star 48B / Orion 38 class kick motor.  Vac Isp 286 s, ρ 1.80 "
                 "kg/L, storable for decades, and the case masses only 6.9% of "
                 "the grain (Star 48B burnout 129 kg on 2,010 kg loaded = 6.4%, "
                 "which is what the solid_motor multiplier is anchored to).\n"
                 "restartable=False, and that is disqualifying HERE: an asteroid "
                 "return fires its second burn years after the first, and a solid "
                 "cannot be relit or throttled.  It stays in the table because "
                 "'we did not consider solids' and 'solids cannot fly this "
                 "profile' are different statements and only one of them is true.",
    },

    # ═════════════════════════════════════════════════════════════════════════
    # OPERATIONAL — electric, added v1.9.0
    # ═════════════════════════════════════════════════════════════════════════
    {
        "name":                  "Krypton  (Hall)",
        "type":                  "electric",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          2019,   # Starlink v1.0
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "supercritical_gas",
        "tank_kg_per_L":         _tank_kg_per_L("supercritical_gas", 18.0),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             2_000,
        "exhaust_vel_m_per_s":   2_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Krypton"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Krypton"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Krypton"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Krypton"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "The most-flown electric propellant by unit count — every "
                 "Starlink v1.0 Hall thruster ran krypton, because Xe supply "
                 "cannot feed a constellation.  ~30× cheaper than xenon at "
                 "$300/kg, ~2/3 the Isp, and a materially worse tank: 0.55 kg/L "
                 "supercritical against xenon's 2.0 means the COPV masses 12.5% "
                 "of the propellant against xenon's 1.9%.  Whether it beats "
                 "xenon is exactly the kind of trade this table now lets the "
                 "search resolve rather than assume.",
    },
    {
        "name":                  "Iodine  (Hall / gridded)",
        "type":                  "electric",
        "status":                "operational",
        "trl":                   8,
        "first_flight":          2020,   # ThrustMe NPT30-I2 on Beihangkongshi-1
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "sublimating_solid",
        "tank_kg_per_L":         _tank_kg_per_L("sublimating_solid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             2_000,
        "exhaust_vel_m_per_s":   2_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Iodine"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Iodine"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Iodine"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Iodine"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "First iodine electric propulsion in orbit: ThrustMe's NPT30-I2 "
                 "on Beihangkongshi-1, Nov 2020 (Rafalskyi et al., Nature 599, "
                 "2021).  Stored as a SOLID at ambient pressure, ρ 4.93 kg/L, so "
                 "the reservoir masses 0.23% of the propellant against xenon's "
                 "1.9% — by a wide margin the best storage density ever flown "
                 "outside mercury.  Cost $60/kg.  The catch is condensable "
                 "exhaust plating out on cold surfaces, which is a "
                 "contamination problem this model does not price.",
    },
    {
        "name":                  "Water  (electrothermal / resistojet)",
        "type":                  "electric",
        "status":                "operational",
        "trl":                   8,
        "first_flight":          2022,   # HYDROS-C (Tethers Unlimited), Momentus Vigoride, Pale Blue
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "benign_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("benign_liquid"),
        "isru_feed_kg_per_kg":   1.0,
        "isru_feed_material":    "water",
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             190,
        "exhaust_vel_m_per_s":   190 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Water"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Water"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Water"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Water"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Steam.  Resistively or microwave heated, Isp 150-220 s.  Flown "
                 "by Tethers Unlimited's HYDROS-C (ISS deploy 2022), Momentus' "
                 "microwave electrothermal Vigoride, and Pale Blue's water "
                 "resistojet.\n"
                 "The point is not the Isp, which is terrible.  It is "
                 "isru_feed_kg_per_kg = 1.0: an asteroid supplies this propellant "
                 "DIRECTLY, with no electrolysis, no cryocooler and no 1.286 "
                 "stoichiometric markup.  Hydrolox needs 1.29 kg of water per kg "
                 "of propellant and a liquefaction plant; steam needs 1.00 and a "
                 "hotplate.  Whether 190 s bought that cheaply beats 452 s bought "
                 "expensively is a real question and the search now gets to "
                 "answer it per asteroid.",
    },
    {
        "name":                  "Water  (gridded ion / ECR)",
        "type":                  "electric",
        "status":                "operational",
        "trl":                   7,
        "first_flight":          2023,   # Pale Blue water ion thruster
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "benign_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("benign_liquid"),
        "isru_feed_kg_per_kg":   1.0,
        "isru_feed_material":    "water",
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             900,
        "exhaust_vel_m_per_s":   900 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Water"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Water"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Water"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Water"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Ionise the steam instead of just heating it: Isp 800-1,000 s on "
                 "the same tank of water.  Pale Blue flew a water ion thruster in "
                 "2023; ESA and JAXA both have ECR water thrusters in "
                 "qualification.  Same ISRU story as the resistojet at ~5× the "
                 "Isp, for a much larger power plant — which this pipeline sizes "
                 "and charges, so the trade is honest.",
    },
    {
        "name":                  "Hydrazine arcjet",
        "type":                  "electric",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1993,   # Telstar 401 / A2100 MR-510
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("storable_liquid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             600,
        "exhaust_vel_m_per_s":   600 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Hydrazine"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Hydrazine"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Hydrazine"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Hydrazine"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Aerojet MR-510, 600 s vac on 2 kW — flown on Lockheed A2100 "
                 "comsats since 1993 and largely displaced by Hall thrusters "
                 "since.  Sits in the gap between chemical and true electric: "
                 "3× hydrazine's Isp at ~100 mN, so it needs far less power per "
                 "newton than a Hall thruster and far less patience than an ion "
                 "engine.  Ammonia arcjets reach ~500 s on a cheaper propellant.",
    },
    {
        "name":                  "Electrospray  (ionic liquid)",
        "type":                  "electric",
        "status":                "operational",
        "trl":                   8,
        "first_flight":          2016,   # LISA Pathfinder ST7-DRS colloid thrusters
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("storable_liquid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             2_500,
        "exhaust_vel_m_per_s":   2_500 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["EMI-BF4"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["EMI-BF4"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["EMI-BF4"]["cost_usd_per_kg"]
                                 * _COMPONENTS["EMI-BF4"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Ionic liquid (EMI-BF4) extracted electrostatically from an "
                 "emitter array — no ionisation chamber, no neutraliser "
                 "discharge, no pressurant.  Flew on LISA Pathfinder's ST7-DRS "
                 "at micronewton precision (2016); Accion's TILE flies "
                 "commercially.  Isp 2,500 s and a room-temperature liquid tank, "
                 "but thrust per emitter is microscopic — scaling to a cargo "
                 "stage means millions of emitters, which is a manufacturing "
                 "problem, not a physics one.",
    },
    {
        "name":                  "FEEP  (indium field emission)",
        "type":                  "electric",
        "status":                "operational",
        "trl":                   8,
        "first_flight":          2016,   # LISA Pathfinder / earlier GOCE caesium ion
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "sublimating_solid",
        "tank_kg_per_L":         _tank_kg_per_L("sublimating_solid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             6_000,
        "exhaust_vel_m_per_s":   6_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Indium"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Indium"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Indium"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Indium"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Liquid indium wicked to a needle tip and field-evaporated. "
                 "ENPULSION's IFM Nano flies on hundreds of smallsats.  Isp "
                 "4,000-8,000 s — the highest of anything operational — at "
                 "ρ 7.31 kg/L in an unpressurised reservoir.  Thrust is tens of "
                 "micronewtons per emitter.  This is the high-Isp end of the "
                 "flown record, and the pipeline's power model is what stops it "
                 "running away with the answer.",
    },
    {
        "name":                  "PPT  (PTFE pulsed plasma)",
        "type":                  "electric",
        "status":                "operational",
        "trl":                   9,
        "first_flight":          1968,   # LES-6
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "sublimating_solid",
        "tank_kg_per_L":         _tank_kg_per_L("sublimating_solid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             1_000,
        "exhaust_vel_m_per_s":   1_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["PTFE"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["PTFE"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["PTFE"]["cost_usd_per_kg"]
                                 * _COMPONENTS["PTFE"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "A Teflon bar ablated by a capacitor discharge — the oldest "
                 "electric propulsion in service (LES-6, 1968; EO-1, 2000). "
                 "Isp ~1,000 s, solid propellant, no tank, no valves, no feed "
                 "system at all.  Efficiency is ~10%, an order below a Hall "
                 "thruster, which is why it never scaled past attitude control.",
    },
    {
        "name":                  "Mercury ion  (RETIRED)",
        "type":                  "electric",
        "status":                "retired",
        "trl":                   9,
        "first_flight":          1970,   # SERT-II
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("storable_liquid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             3_000,
        "exhaust_vel_m_per_s":   3_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Mercury"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Mercury"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Mercury"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Mercury"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "SERT-II (1970) and ATS-6 flew mercury ion engines.  ρ 13.53 "
                 "kg/L is still the best propellant storage density ever flown "
                 "and $60/kg is a fiftieth of xenon, so on this table's columns "
                 "alone it looks like the obvious winner.\n"
                 "It is banned.  The 2013 Minamata Convention on Mercury "
                 "prohibits it, and a 2019 attempt to fly a mercury-propelled "
                 "constellation was abandoned after the ionised-mercury plume "
                 "was shown to return to Earth's atmosphere.  status='retired' "
                 "keeps it out of the search permanently — it is here so that "
                 "the next person to notice the density has the answer already.",
    },
    {
        "name":                  "Solar sail  (photonic)",
        "type":                  "propellantless",
        "status":                "operational",
        "trl":                   8,
        "first_flight":          2010,   # IKAROS
        "restartable":           True,
        "propellantless":        True,
        "storage_class":         "propellantless",
        "tank_kg_per_L":         0.0,
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             np.inf,
        "exhaust_vel_m_per_s":   np.inf,
        "density_kg_per_L":      np.nan,
        "ref_cost_usd_per_kg":   0.0,
        "ref_cost_usd_per_L":    0.0,
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "IKAROS (2010) was the first sail to be propelled by sunlight; "
                 "LightSail 2 (2019) raised its own apogee; NEA Scout (2022) "
                 "deployed but was lost; ACS3 (2024) demonstrated composite "
                 "booms.\n"
                 "Isp is infinite, which is exactly the problem: the rocket "
                 "equation says a sail moves any payload for zero propellant, "
                 "so an unguarded model reports an unbounded result.  Real sails "
                 "run ~0.1 mm/s² of characteristic acceleration at 1 AU — fine "
                 "for a 6 kg cubesat, meaningless for a hold of ore, and falling "
                 "as 1/r² besides.  propellantless=True makes Module 4 exclude "
                 "it.  Pricing sails properly needs a thrust-limited trajectory "
                 "solver, which is the same gap that keeps the EP stage sized to "
                 "a fixed thrust duration.",
    },

    # ═════════════════════════════════════════════════════════════════════════
    # DEVELOPMENT — built and fired, not yet flown
    # ═════════════════════════════════════════════════════════════════════════
    {
        "name":                  "Nuclear thermal  (LH2, NTP)",
        "type":                  "nuclear_thermal",
        "status":                "development",
        "trl":                   5,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "deep_cryogen",
        "tank_kg_per_L":         _tank_kg_per_L("deep_cryogen"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.05,   # bare LH2, no oxidiser to average against — the worst in the table
        "isp_vac_s":             900,
        "exhaust_vel_m_per_s":   900 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["LH2"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["LH2"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["LH2"]["cost_usd_per_kg"]
                                 * _COMPONENTS["LH2"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Heat hydrogen in a fission core: twice the Isp of the best "
                 "chemistry at full chemical thrust.  NERVA's NRX/XE ran on a "
                 "test stand at 825 s in 1968; DRACO targeted 900 s before being "
                 "descoped in 2025.  TRL 5 — the reactor physics is 60 years "
                 "proven and nothing has flown.\n"
                 "This row is the clearest case for the v1.9.0 tank model.  Bare "
                 "LH2 at 0.0708 kg/L pays 53% of its own mass in tankage and "
                 "0.05%/day in boil-off with no oxidiser to average against, so "
                 "a large part of the 900 s is handed straight back on a "
                 "multi-year mission.  Before v1.9.0 the model would have taken "
                 "the Isp and charged nothing for either.  The reactor's own "
                 "mass and cost are ALSO not modelled — so this row is still "
                 "optimistic, and gated out of the default search accordingly.",
    },
    {
        "name":                  "Nuclear electric  (NEP, xenon)",
        "type":                  "nuclear_electric",
        "status":                "development",
        "trl":                   4,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "supercritical_gas",
        "tank_kg_per_L":         _tank_kg_per_L("supercritical_gas", 10.0),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             5_000,
        "exhaust_vel_m_per_s":   5_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Xenon"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Xenon"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Xenon"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Xenon"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "A fission reactor driving high-power ion or Hall thrusters. "
                 "The one architecture that breaks this pipeline's binding "
                 "constraint on electric propulsion — power at distance, which "
                 "PV loses as 1/r².  Kilopower/KRUSTY ran a 1 kWe reactor in "
                 "2018; MW-class flight units are TRL 3-4.\n"
                 "⚠️  Module 4 sizes electric power off the PV row and its 1/r² "
                 "term.  A nuclear source does not scale that way, so selecting "
                 "this propellant WITHOUT teaching the power model about it "
                 "would still charge a solar array's mass.  Gated out until "
                 "that is fixed; the row exists so the gap is visible.",
    },
    {
        "name":                  "Solar thermal  (LH2)",
        "type":                  "solar_thermal",
        "status":                "development",
        "trl":                   4,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "deep_cryogen",
        "tank_kg_per_L":         _tank_kg_per_L("deep_cryogen"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.05,
        "isp_vac_s":             800,
        "exhaust_vel_m_per_s":   800 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["LH2"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["LH2"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["LH2"]["cost_usd_per_kg"]
                                 * _COMPONENTS["LH2"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Concentrate sunlight onto a hydrogen heat exchanger: NTP's Isp "
                 "without the reactor.  Ground-tested by the USAF Solar Orbit "
                 "Transfer Vehicle programme in the 1990s (Isp 700-900 s "
                 "demonstrated); never flown.  Suffers the same 1/r² starvation "
                 "as PV, so it is a near-Sun technology — which is the opposite "
                 "of where the main belt is.",
    },
    {
        "name":                  "Solar thermal steam  (water)",
        "type":                  "solar_thermal",
        "status":                "development",
        "trl":                   4,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "benign_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("benign_liquid"),
        "isru_feed_kg_per_kg":   1.0,
        "isru_feed_material":    "water",
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             190,
        "exhaust_vel_m_per_s":   190 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Water"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Water"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Water"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Water"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Honeybee Robotics' WINE ('World Is Not Enough') mined simulant, "
                 "boiled the water and thrusted on the steam inside a vacuum "
                 "chamber in 2018 — the only end-to-end asteroid-ISRU propulsion "
                 "demonstration there has ever been.  Isp ~190 s, no electrical "
                 "conversion loss, and 1.0 kg of asteroid water per kg of "
                 "propellant.  This is the propellant the concept of a "
                 "self-refuelling mining craft is actually built on, and it was "
                 "absent from this table until v1.9.0.",
    },
    {
        "name":                  "VASIMR  (argon, variable Isp)",
        "type":                  "electric",
        "status":                "development",
        "trl":                   5,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "mild_cryogen",
        "tank_kg_per_L":         _tank_kg_per_L("mild_cryogen"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   _LAR_BOILOFF_PCT_PER_DAY,
        "isp_vac_s":             4_000,
        "exhaust_vel_m_per_s":   4_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["ArgonLIQ"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["ArgonLIQ"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["ArgonLIQ"]["cost_usd_per_kg"]
                                 * _COMPONENTS["ArgonLIQ"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Ad Astra's VX-200SS ran 100 hours at 80 kW in 2021.  RF-heated "
                 "plasma in a magnetic nozzle, and the headline feature is "
                 "throttleable Isp — trade thrust against efficiency in flight, "
                 "which is precisely the freedom a fixed-Isp table cannot "
                 "express.  Modelled here at a single 4,000 s point, which "
                 "understates it; capturing the variable-Isp advantage needs the "
                 "same trajectory optimiser the sails do.\n"
                 "Cryogenic argon feed, because a 100 kW-class stage moves "
                 "propellant by the tonne and no COPV is a sensible way to carry "
                 "tonnes of a gas this light.  v1.10.0: it therefore pays "
                 "cryogenic boil-off, which it was exempt from before.",
    },
    {
        "name":                  "Argon  (Hall / ion, cryogenic)",
        "type":                  "electric",
        "status":                "development",
        "trl":                   4,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "mild_cryogen",
        "tank_kg_per_L":         _tank_kg_per_L("mild_cryogen"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   _LAR_BOILOFF_PCT_PER_DAY,
        "isp_vac_s":             1_500,
        "exhaust_vel_m_per_s":   1_500 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["ArgonLIQ"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["ArgonLIQ"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["ArgonLIQ"]["cost_usd_per_kg"]
                                 * _COMPONENTS["ArgonLIQ"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "v1.10.0.  The other half of the argon split — same 1,500 s Hall "
                 "thruster as the operational row, fed from a liquid tank at "
                 "87.3 K instead of an 18 MPa bottle.  It is the architecture a "
                 "multi-tonne stage would actually want: 1.395 kg/L against "
                 "0.30 buys a 2.1% tank against 22.9%, which is the single "
                 "biggest storage swing in this table.\n"
                 "DEVELOPMENT, not operational, and the distinction is the point. "
                 "Liquid argon is routine on the ground and has never flown on a "
                 "spacecraft; no EP system has ever carried a cryogen.  Tagging "
                 "it operational would let the default search fly an article "
                 "nobody has built, which is exactly what the pre-v1.10.0 argon "
                 "row did by accident.  The honest version of that row is these "
                 "two, and the tank saving now costs what it really costs: "
                 "boil-off over a multi-year hold, on the same terms as every "
                 "other cryogen here.",
    },
    {
        "name":                  "MPD  (lithium magnetoplasmadynamic)",
        "type":                  "electric",
        "status":                "development",
        "trl":                   4,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "storable_liquid",
        "tank_kg_per_L":         _tank_kg_per_L("storable_liquid"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             4_000,
        "exhaust_vel_m_per_s":   4_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Lithium"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Lithium"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Lithium"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Lithium"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Lithium Lorentz Force Accelerator — the highest thrust density "
                 "of any electric thruster, and the only class that could plausibly "
                 "move hundreds of tonnes.  Ground-tested at Princeton and by "
                 "RIAME (Moscow) at 100+ kW; needs megawatts to be interesting, "
                 "which is why it is bracketed with NEP rather than with PV.",
    },
    {
        "name":                  "Metal / water  (ALICE, Al + H2O)",
        "type":                  "bipropellant",
        "status":                "development",
        "trl":                   3,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "solid_motor",
        "tank_kg_per_L":         _al_water["tank_kg_per_L"],
        "isru_feed_kg_per_kg":   0.5,
        "isru_feed_material":    "water",
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             210,
        "exhaust_vel_m_per_s":   210 * G0_M_S2,
        "density_kg_per_L":      _al_water["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _al_water["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _al_water["ref_cost_usd_per_kg"] * _al_water["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Nano-aluminium burnt in water — Purdue/NASA ALICE flew a "
                 "sounding rocket in 2009.  Isp only 210 s, but BOTH components "
                 "are asteroid-derivable: metallic aluminium from silicate "
                 "reduction and water from phyllosilicates.  isru_feed is 0.5 "
                 "because half the mixture is metal, which this pipeline does "
                 "not yet model refining — so the figure is a placeholder for "
                 "the water half only and the row is gated out.",
    },

    # ═════════════════════════════════════════════════════════════════════════
    # CONCEPT — designed, or demonstrated only as physics
    # ═════════════════════════════════════════════════════════════════════════
    {
        "name":                  "Li / F2 / H2  (tripropellant)",
        "type":                  "tripropellant",
        "status":                "concept",
        "trl":                   3,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "mild_cryogen",
        "tank_kg_per_L":         _lifh["tank_kg_per_L"],
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.04,
        "isp_vac_s":             542,
        "exhaust_vel_m_per_s":   542 * G0_M_S2,
        "density_kg_per_L":      _lifh["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _lifh["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _lifh["ref_cost_usd_per_kg"] * _lifh["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "542 s is the highest specific impulse ever MEASURED from a "
                 "chemical rocket — Rocketdyne, test stand, 1960s.  It is in "
                 "this table as the ceiling of chemistry, so that '452 s is the "
                 "best chemical Isp' is not quietly assumed.\n"
                 "It will never fly.  The exhaust is hydrogen fluoride, the "
                 "oxidiser is liquid fluorine, and the fuel is molten lithium; "
                 "the ground handling is beyond hazardous and into "
                 "unpermittable.  status='concept' at TRL 3 despite a real "
                 "firing, because engineering feasibility is not the binding "
                 "constraint here.",
    },
    {
        "name":                  "CO / LOX  (carbonaceous ISRU)",
        "type":                  "bipropellant",
        "status":                "concept",
        "trl":                   3,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "mild_cryogen",
        "tank_kg_per_L":         _co_lox["tank_kg_per_L"],
        # NOT declared ISRU-makeable, despite being the entry here most obviously
        # aimed at it.  The feed is set by the body's CARBON fraction, not by a
        # flat regolith ratio: 1 kg of propellant at O/F 0.57 is 0.637 kg of CO,
        # which is 0.274 kg of carbon, so a 3 wt% carbonaceous body owes ~9 kg of
        # rock per kg burnt — and a 1 wt% body owes 27.  Module 4 has no
        # carbon-fed ISRU path, and stating a single number here would be
        # inventing one rather than deriving it, exactly as with methalox.
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.012,
        "isp_vac_s":             260,
        "exhaust_vel_m_per_s":   260 * G0_M_S2,
        "density_kg_per_L":      _co_lox["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _co_lox["ref_cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _co_lox["ref_cost_usd_per_kg"] * _co_lox["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Carbon monoxide burnt in oxygen, both from carbonaceous "
                 "regolith or a CO2 atmosphere.  Isp ~260 s — poor — but it is "
                 "the only chemical bipropellant makeable from a C-type asteroid "
                 "without any hydrogen at all, which matters because hydrogen is "
                 "the scarce element out there, not carbon or oxygen.  Studied "
                 "extensively for Mars (Zubrin); never built.\n"
                 "The ISRU columns are deliberately null — see the comment "
                 "above them.  This is the row where 'obviously ISRU' and "
                 "'this model can price it' come apart.",
    },
    {
        "name":                  "Mass driver  (regolith reaction mass)",
        "type":                  "kinetic",
        "status":                "concept",
        "trl":                   3,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "sublimating_solid",   # raw rock in a hopper; no pressure vessel
        "tank_kg_per_L":         _tank_kg_per_L("sublimating_solid"),
        "isru_feed_kg_per_kg":   1.0,
        "isru_feed_material":    "regolith",
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             306,     # 3 km/s slug velocity / g0 — see notes
        "exhaust_vel_m_per_s":   3_000,
        "density_kg_per_L":      2.000,   # loose regolith bulk density
        "ref_cost_usd_per_kg":   0.10,    # the rock is free; this is handling
        "ref_cost_usd_per_L":    0.20,
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Electromagnetically accelerate buckets of raw regolith and "
                 "throw them overboard.  O'Neill and Snow built a working "
                 "prototype at Princeton in 1977 (40 g); the concept predates "
                 "every other entry in this table as an asteroid-mining "
                 "proposal, and it was missing from it.\n"
                 "Isp is a derived equivalence, not a chemistry: a 3 km/s slug "
                 "velocity is 3,000/9.807 = 306 s.  The reaction mass is the "
                 "asteroid, so isru_feed_material='regolith' at 1.0 and the "
                 "$/kg is handling only.  What it costs is POWER, continuously, "
                 "and its thrust is a stream of discrete impulses — neither of "
                 "which this pipeline's propulsion model can express, hence "
                 "concept and gated.",
    },
    {
        "name":                  "Nuclear pulse  (Orion)",
        "type":                  "nuclear_pulse",
        "status":                "concept",
        "trl":                   2,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "solid_motor",
        "tank_kg_per_L":         _tank_kg_per_L("solid_motor"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             10_000,
        "exhaust_vel_m_per_s":   10_000 * G0_M_S2,
        "density_kg_per_L":      1.500,
        # ORDER-OF-MAGNITUDE ESTIMATE.  A pulse unit is mostly tungsten/
        # polyethylene propellant around a small fissile core, so the average
        # $/kg is nowhere near the ~$4-6M/kg of weapons-grade plutonium
        # itself — but there is no commodity price for a nuclear shaped
        # charge, and there will not be one.  $50k/kg is a placeholder that
        # keeps the row from looking cheap; do not read it as a quote.
        "ref_cost_usd_per_kg":   50_000.0,
        "ref_cost_usd_per_L":    75_000.0,
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Detonate shaped nuclear charges against a pusher plate. "
                 "Designed in full engineering detail by General Atomics "
                 "1958-1965 — Dyson and Taylor's programme produced vehicle "
                 "layouts, not sketches — and killed by the 1963 Partial Test "
                 "Ban Treaty.  Isp 10,000 s at MEGANEWTON thrust is the only "
                 "entry here that is both high-Isp and high-thrust, which is why "
                 "it keeps being revisited.  TRL 2 and permanently "
                 "unpermittable; present because 'never designed' would be false.",
    },
    {
        "name":                  "Direct fusion drive",
        "type":                  "fusion",
        "status":                "concept",
        "trl":                   2,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "supercritical_gas",
        "tank_kg_per_L":         _tank_kg_per_L("supercritical_gas", 10.0),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             10_000,
        "exhaust_vel_m_per_s":   10_000 * G0_M_S2,
        "density_kg_per_L":      0.100,
        # He-3 is quoted around $1,400-2,000 per gram, so ~$1.5M/kg, and the
        # D-He3 mix is mostly deuterium (~$1,000/kg).  ORDER-OF-MAGNITUDE
        # ESTIMATE at $1M/kg for the blend; there is no market, and world He-3
        # supply is a few kg a year from tritium decay.
        "ref_cost_usd_per_kg":   1_000_000.0,
        "ref_cost_usd_per_L":    100_000.0,
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Princeton Plasma Physics Lab's PFRC-2 field-reversed "
                 "configuration, aneutronic D-He3, studied under NASA NIAC. "
                 "Isp 10,000+ s at ~5 N/MW.  TRL 2: the confinement scheme is "
                 "under experimental test and net-positive fusion of any kind "
                 "has not been demonstrated in a flight-relevant device.",
    },
    {
        "name":                  "Antimatter-catalysed",
        "type":                  "antimatter",
        "status":                "concept",
        "trl":                   1,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "supercritical_gas",
        "tank_kg_per_L":         _tank_kg_per_L("supercritical_gas", 10.0),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             100_000,
        "exhaust_vel_m_per_s":   100_000 * G0_M_S2,
        "density_kg_per_L":      0.100,
        # $62.5 trillion per GRAM is the figure NASA/CERN quote, which is
        # 6.25e16 USD/kg — not the 1e15 an earlier draft of this row carried.
        # The whole propellant load is not antimatter (a few micrograms
        # initiate microfission in a much larger charge), so this is the
        # antihydrogen price applied as if it were, i.e. an upper bound and
        # explicitly not a mission cost.
        "ref_cost_usd_per_kg":   6.25e16,
        "ref_cost_usd_per_L":    6.25e15,
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Antiproton-initiated microfission (Penn State AIMStar, NASA "
                 "NIAC).  The Isp column is the reason it appears in every "
                 "propulsion survey; the cost column is the reason it appears in "
                 "no mission plan.  CERN's antiproton production, scaled, prices "
                 "antihydrogen near $10^15/kg, and world annual production is "
                 "measured in nanograms.  TRL 1.  It is here to close the table "
                 "at the physical ceiling.",
    },
    {
        "name":                  "Magnetic sail / electric sail",
        "type":                  "propellantless",
        "status":                "concept",
        "trl":                   3,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        True,
        "storage_class":         "propellantless",
        "tank_kg_per_L":         0.0,
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             np.inf,
        "exhaust_vel_m_per_s":   np.inf,
        "density_kg_per_L":      np.nan,
        "ref_cost_usd_per_kg":   0.0,
        "ref_cost_usd_per_L":    0.0,
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Deflect the solar WIND rather than sunlight — Zubrin's "
                 "magsail, or Janhunen's electric sail with charged tethers. "
                 "Thrust per kilogram of hardware beats a photon sail beyond "
                 "~1 AU because solar-wind dynamic pressure falls more slowly "
                 "than the model's PV does.  ESTCube-1 (2013) and Aalto-1 "
                 "failed to deploy their tethers, so nothing has been "
                 "demonstrated in flight.  Excluded by propellantless=True for "
                 "the same reason as the photon sail.",
    },
    {
        "name":                  "Momentum-exchange tether",
        "type":                  "propellantless",
        "status":                "concept",
        "trl":                   4,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        True,
        "storage_class":         "propellantless",
        "tank_kg_per_L":         0.0,
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             np.inf,
        "exhaust_vel_m_per_s":   np.inf,
        "density_kg_per_L":      np.nan,
        "ref_cost_usd_per_kg":   0.0,
        "ref_cost_usd_per_L":    0.0,
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "A rotating tether catches a payload and throws it, moving "
                 "momentum between cargoes instead of expending propellant. "
                 "YES2 (2007) deployed 31.7 km of tether and reentered a "
                 "capsule; HASTOL and MXER were studied to PDR.  Genuinely "
                 "propellantless for a two-way traffic pattern, which is exactly "
                 "what a mining programme is — but it is INFRASTRUCTURE with its "
                 "own capital cost and orbit, not a propellant a spacecraft "
                 "carries, and this pipeline has no way to amortise a facility "
                 "across missions.  That is the modelling gap, not the physics.",
    },
    {
        "name":                  "Beamed laser-thermal  (H2)",
        "type":                  "beamed_energy",
        "status":                "concept",
        "trl":                   3,
        "first_flight":          None,
        "restartable":           True,
        "propellantless":        False,
        "storage_class":         "deep_cryogen",
        "tank_kg_per_L":         _tank_kg_per_L("deep_cryogen"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
        "dv_penalty_factor":     1.0,
        "boiloff_pct_per_day":   0.05,
        "isp_vac_s":             900,
        "exhaust_vel_m_per_s":   900 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["LH2"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["LH2"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["LH2"]["cost_usd_per_kg"]
                                 * _COMPONENTS["LH2"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Leave the power plant at home and beam it: NTP's Isp with no "
                 "reactor aboard.  Kare's laser-thermal work and the 2022 "
                 "McGill/UCLA laser-thermal Mars study put Isp near 900 s.  Same "
                 "amortisation problem as the tether — the expensive part is a "
                 "ground or orbital laser array shared across missions, which "
                 "this pipeline cannot represent.",
    },
]

print(f"✅  Propellant reference loaded — {len(PROPELLANTS_REFERENCE)} fuel systems "
      f"({sum(1 for p in PROPELLANTS_REFERENCE if p['status'] == 'operational')} operational, "
      f"{sum(1 for p in PROPELLANTS_REFERENCE if p['status'] == 'development')} development, "
      f"{sum(1 for p in PROPELLANTS_REFERENCE if p['status'] == 'concept')} concept, "
      f"{sum(1 for p in PROPELLANTS_REFERENCE if p['status'] == 'retired')} retired)")


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
        "category":         "Propellant tank recurring cost",
        "unit":             "USD per kg of tank dry mass",
        "value":              6_000,
        "range_low":          3_000,
        "range_high":        25_000,
        "notes": "v1.10.0.  Module 3 has derived tank MASS per propellant since "
                 "v1.9.0 (tank_kg_per_L) and Module 4 has flown it through the "
                 "rocket equation since then — but nothing ever priced it, so "
                 "the tank paid its launch $/kg and cost nothing to build.  That "
                 "is the same mass-without-a-price asymmetry as the free "
                 "electric-propulsion stage, just smaller.\n"
                 "Derived from Centaur III, the closest flight article: ~1,880 kg "
                 "of stage structure, ~$30M for the stage against ~$20M for the "
                 "RL10 it carries, so ~$10M of structure ≈ $5,300/kg.  Rounded "
                 "up to $6,000 and quoted as a LOWER BOUND, consistent with the "
                 "rest of this table: Centaur is a mature production article and "
                 "a deep-space tank holding propellant for four years needs "
                 "insulation Centaur does not carry.  The upper end of the range "
                 "is where a one-off, long-duration cryogenic tank plausibly "
                 "lands.\n"
                 "It is deliberately the CHEAPEST hardware rate here — below the "
                 "$60k/kg passive berthing adapter — because a tank is the "
                 "simplest article in the mission: no mechanisms, no docking "
                 "interface, no re-entry.  Do not read its small effect as a "
                 "reason to drop it; the point of the line is that every "
                 "kilogram in the mass cascade has one.",
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
                 "level.  60 W/kg is "
                 "mid-range for a deep-space PV train.  Scales as 1/r^2 with "
                 "heliocentric distance — Module 4 applies that per asteroid, "
                 "which is why main-belt targets are punished so hard once "
                 "processing power is modelled.\n"
                 "v1.11.0: this row USED to claim it also covered 'power "
                 "through eclipse and through the night side of a rotating "
                 "body', and that claim has been removed because it was not "
                 "true and could not be.  A specific mass cannot express a "
                 "sizing factor, and the storage duration it implies is a LEO "
                 "eclipse, not an asteroid night — see 'Power-system row "
                 "baseline dark period', which names what this figure really "
                 "carries so Module 4 can charge the increment above it.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Electric thruster + PPU specific mass",
        "unit":             "kg per kW of input electrical power",
        "value":            8,
        "range_low":        5,
        "range_high":       15,
        "notes": "v1.6.0.  Thruster, power-processing unit, gimbals, xenon/argon "
                 "feed system, tankage and thermal — NOT the solar array, which "
                 "is carried separately by the 'Power system specific mass' row "
                 "and scales 1/r^2.  NASA NEXT-C: 7 kW thruster ~13.5 kg + PPU "
                 "~34 kg ≈ 7 kg/kW.  Gateway AEPS: 12.5 kW Hall, similar class. "
                 "8 kg/kW allows for feed system and structure.\n"
                 "⚠️  SUPERSEDED for Module 4 v1.12.0 and retained as the "
                 "fallback for a stale catalog.  Lumping thruster and PPU into "
                 "one per-kW figure is what let a micronewton device be sized "
                 "as a cargo tug: buy the kilowatts and you got the thrust.  "
                 "They scale on different quantities — a PPU is a power "
                 "converter (kg/kW, the row below) and a thruster head makes "
                 "momentum (kg/N, per technology, in _THRUSTER_SYSTEMS).",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Power processing unit specific mass",
        "unit":             "kg per kW of input electrical power",
        "value":            4.7,
        "range_low":        3.0,
        "range_high":       8.0,
        "notes": "v1.10.0.  The PPU alone, split out of the combined row above. "
                 "NASA NEXT-C: 34.5 kg of PPU at 7.4 kW = 4.66 kg/kW.  A PPU "
                 "converts bus power to the discharge and does not care what it "
                 "is feeding, so it is the half of the old 8 kg/kW that really "
                 "does scale with POWER.  The other half — the thruster head — "
                 "scales with THRUST and is per-technology, because that is "
                 "exactly where a pulsed plasma thruster and a gridded ion "
                 "engine stop being interchangeable.  Together they reproduce "
                 "NEXT-C: 4.7 x 7.4 + 54 x 0.236 = 47.5 kg against 47.2 kg "
                 "measured (12.7 kg thruster + 34.5 kg PPU).",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Electric propulsion system recurring cost",
        "unit":             "USD per kW of input electrical power (thruster + PPU)",
        "value":            1_500_000,
        "range_low":          500_000,
        "range_high":       3_000_000,
        "notes": "v1.8.2.  Recurring cost of the electric PROPULSION train — "
                 "thruster, power-processing unit, gimbals, feed system, "
                 "thermal.  NOT the solar array, which is priced separately "
                 "off the 'Power system (solar + battery)' row at $/W and is "
                 "far cheaper per kilogram.\n"
                 "Anchor: a NASA NEXT-C flight string is a 7 kW gridded-ion "
                 "thruster plus PPU at roughly 47 kg, procured in the "
                 "$10-15M-per-string class as a flight article — call it "
                 "$1.5-2M/kW.  High-power Hall systems buy down from there: "
                 "Psyche's SPT-140 strings and Gateway's 12.5 kW AEPS are "
                 "cheaper per kilowatt than NEXT-C, which is why the range "
                 "runs down to $500k/kW and why the figure should be expected "
                 "to fall if multi-hundred-kW deep-space EP is ever built.\n"
                 "SOFT: no multi-hundred-kW deep-space electric stage has "
                 "flown, and this pipeline sizes some missions at 300 kW — "
                 "six times the largest article yet built.  Extrapolating a "
                 "per-kW price that far is a judgement, not a quote.  It is "
                 "here because the alternative was worse: before v1.8.2 the "
                 "electric stage entered the rocket equation as mass and "
                 "appeared in NO cost line at all, so a 14-tonne, 309 kW "
                 "propulsion system was free and electric propulsion won on "
                 "hardware nobody had to buy.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Electric propulsion efficiency",
        "unit":             "fraction of input power converted to jet power",
        "value":            0.60,
        "range_low":        0.45,
        "range_high":       0.72,
        "notes": "v1.6.0.  Total efficiency (anode × mass-utilisation × PPU). "
                 "Hall thrusters run 0.50-0.60; gridded ion (NEXT) reaches "
                 "0.65-0.70 at high specific impulse.  Sets thrust for a given "
                 "power: T = 2·η·P / (Isp·g0), which is what makes low-thrust "
                 "trip time computable at all.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Water liberation energy (bound water)",
        "unit":             "Watt-hours per kg of water extracted",
        "value":            2_500,
        "range_low":        1_000,
        "range_high":       5_000,
        "notes": "v1.6.0.  C/B/D-type 'ice' is not ice — it is water bound into "
                 "phyllosilicates, and getting it out means heating the rock "
                 "past dehydroxylation, not melting a cube.  Arithmetic for a "
                 "10 wt% hydrated body, per kg of WATER recovered: heat 10 kg "
                 "of rock from ~200 K to ~700 K at c_p ≈ 800 J/kg·K = 4.0 MJ; "
                 "dehydroxylation enthalpy of serpentine ≈ 250 kJ/kg of rock "
                 "= 2.5 MJ; vaporise and capture 1 kg of water = 2.26 MJ. "
                 "Total ≈ 8.8 MJ/kg = 2,440 Wh/kg.  Matches the 1-3 kWh/kg "
                 "range in the asteroid-ISRU literature (Colorado School of "
                 "Mines / NASA ISRU studies).  Charged ON TOP of the generic "
                 "beneficiation row, which covers mechanical separation only.",
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
                 "(Space.com / NASA NIAC).  Only used past ~3 AU when PV starves.\n"
                 "v1.9.0: this row existed from v1.2.0 and NOTHING READ IT.  A "
                 "3.5 AU target flew a photovoltaic array starved by 1/r² with "
                 "no nuclear alternative anywhere in the model, which is the "
                 "reason main-belt bodies were punished as hard as they were. "
                 "Module 4 now picks whichever of PV and RTG is lighter for the "
                 "target's heliocentric distance and pays the corresponding "
                 "rate — this one, or the $800/W solar row.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "RTG specific power",
        "unit":             "Watts-electric per kg of RTG",
        "value":            5.0,
        "range_low":        2.4,
        "range_high":       5.5,
        "notes": "v1.9.0.  The nuclear counterpart to 'Power system specific "
                 "mass', and the reason it is a separate row: this one does NOT "
                 "scale with heliocentric distance.\n"
                 "GPHS-RTG (Cassini, New Horizons, Galileo): 290 We at 56 kg = "
                 "5.2 W/kg.  MMRTG (Curiosity, Perseverance): 110 We at 45 kg = "
                 "2.4 W/kg, worse because it is qualified to run in an "
                 "atmosphere as well as vacuum.  5.0 W/kg takes the "
                 "deep-space-only design.\n"
                 "The crossover against the 60 W/kg-at-1-AU solar row is at "
                 "sqrt(60/5) = 3.46 AU: inside that, PV is lighter per watt; "
                 "outside it, nothing beats a radioisotope.  RTGs cost ~625× "
                 "more per watt ($500k vs $800), so the model buys the smallest "
                 "one that does the job, which is exactly how real outer-planet "
                 "missions are sized.  Supply is the real constraint and it is "
                 "NOT priced here: DOE Pu-238 production runs ~1.5 kg/yr, "
                 "enough for roughly one flagship RTG a year for the entire "
                 "world, so any programme flying more than a couple of these "
                 "does not have a cost problem, it has an allocation problem.",
        "reference_year":   _REF_YEAR_OPS,
    },
    # ── Eclipse and night-side operation  (v1.11.0) ──────────────────────────
    # Three rows that together let Module 4 stop assuming the sun never sets on
    # the processing plant.  They were derivable from STORAGE_REFERENCE before
    # this release and unreachable, because Module 4 loads operational_costs.csv
    # and does not load storage_systems.csv — which is exactly why the "⚠️  Not
    # modelled" note on the storage row survived a release that was looking for
    # unread columns.
    {
        "category":         "Eclipse / night-side dark fraction",
        "unit":             "fraction of the time a surface rig sees no sun",
        "value":            0.50,
        "range_low":        0.35,
        "range_high":       0.55,
        "notes": "v1.11.0.  A rig anchored to a rotating body stands on a "
                 "surface that is lit half the time, by geometry — the same "
                 "0.50 STORAGE_REFERENCE has carried since v1.9.0, moved here "
                 "so Module 4 can actually read it.  Ranges below 0.5 for a "
                 "high-latitude or near-polar emplacement on a body with "
                 "obliquity, above it for an equatorial site with local "
                 "horizon shadowing.\n"
                 "This is a SIZING factor, not a specific mass, and that is why "
                 "no W/kg figure can absorb it: to deliver P continuously "
                 "through a dark fraction f you must INSTALL "
                 "P·[(1−f) + f/η_rt]/(1−f) of generating capacity, because the "
                 "sunlit hours have to run the load and recharge the store as "
                 "well.  At f = 0.50 and η_rt = 0.90 that is 2.11×.\n"
                 "The alternative architecture is to mine at half duty cycle "
                 "and take twice the stay time instead; Module 4 sizes the "
                 "storage rather than halving the duty, which is the choice "
                 "that leaves mission duration comparable across bodies.\n"
                 "Does NOT apply to a radioisotope source — an RTG's output is "
                 "flat — and does not apply to the electric-propulsion array, "
                 "which is in interplanetary cruise and in permanent sunlight.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Energy storage usable specific energy",
        "unit":             "usable Watt-hours per kg of storage system",
        "value":            104,
        "range_low":         70,
        "range_high":       160,
        "notes": "v1.11.0.  130 Wh/kg at the system level (STORAGE_REFERENCE "
                 "'Li-ion battery (system level)': cells reach 250-300 Wh/kg "
                 "and packaging, harness, balancing and thermal roughly halve "
                 "it) × 0.80 depth of discharge = 104 Wh/kg USABLE.  DoD is "
                 "folded in here rather than carried as a fourth row because "
                 "a consumer that forgets to apply it silently oversizes the "
                 "mission by 25%, and this table's job is to hand Module 4 the "
                 "number it should divide by.\n"
                 "A regenerative fuel cell (400 Wh/kg, TRL 5) is the obvious "
                 "architecture for a multi-hour dark period and would cut this "
                 "term by ~4×; it is not taken, because nothing has flown one "
                 "and this row is the operational choice.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Energy storage round-trip efficiency",
        "unit":             "fraction of stored energy recovered",
        "value":            0.90,
        "range_low":        0.80,
        "range_high":       0.95,
        "notes": "v1.11.0.  Charge and discharge losses through the cells and "
                 "the regulator.  Li-ion cells alone run 0.92-0.96 round trip; "
                 "0.90 takes the loss through PMAD as well.  This is the term "
                 "that makes the array oversize worse than the naive 1/(1−f): "
                 "the energy that goes through the store has to be generated "
                 "twice over, once for the load and once for the loss.  At "
                 "f = 0.50 it is the difference between 2.00× and 2.11×.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Power-system row baseline dark period",
        "unit":             "hours of darkness already covered by the 60 W/kg row",
        "value":            0.58,
        "range_low":        0.0,
        "range_high":       1.2,
        "notes": "v1.11.0.  The deduction that stops Module 4 double-charging "
                 "the battery.  'Power system specific mass' is 60 W/kg "
                 "SYSTEM-level against ROSA's ~150 W/kg at the wing, and part "
                 "of that 2.5× is a battery — so some storage is already paid "
                 "for and only the INCREMENT above it is new.\n"
                 "0.58 h is the standard LEO eclipse (35 min of a ~92 min "
                 "orbit), which is the storage duration a conventional "
                 "deep-space PV train is specified against.  Arithmetic: 0.58 h "
                 "of 1 W at 104 Wh/kg usable is 0.0056 kg/W, against the row's "
                 "own 1/60 = 0.0167 kg/W of total plant — a third of it, which "
                 "is why deducting it matters rather than being a nicety.\n"
                 "⚠️  The 'Power system specific mass' row's own notes claim it "
                 "covers 'power through eclipse and through the night side of a "
                 "rotating body'.  It cannot cover both: an asteroid with a "
                 "10 h rotation is dark for 5 h, roughly 9× the LEO figure, and "
                 "no single specific mass can be right for both duty cycles. "
                 "That contradiction is the argon failure in a new place — a "
                 "reference row asserting two incompatible states at once — and "
                 "this row resolves it by naming which of the two the 60 W/kg "
                 "figure actually is.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Volatile cargo containment",
        "unit":             "kg of containment per kg of volatile cargo",
        "value":            0.05,
        "range_low":        0.03,
        "range_high":       0.12,
        "notes": "v1.11.0.  Water sold at a depot has to still be water when it "
                 "arrives.  Exposed ice in sunlight at 1 AU sits far above its "
                 "sublimation threshold and is simply gone over a multi-year "
                 "cruise; shaded, sealed and blanketed it is stable for "
                 "decades.  So the charge is a sealed shaded hold — no power, "
                 "no cryocooler, but real mass.\n"
                 "Carried in STORAGE_REFERENCE since v1.9.0 with '⚠️  NOT "
                 "modelled in Module 4' on it, and duplicated here because that "
                 "table is not one Module 4 loads.  It is INCREMENTAL to the "
                 "0.15 ore-restraint fraction Module 4 already flies as "
                 "`return_structure_frac_of_payload`: the hopper holds the "
                 "cargo, the seal and shade keep the volatile fraction of it "
                 "from leaving.  That reading is what makes the storage row's "
                 "own 'heavier than an ore hopper' true at a value below 0.15.\n"
                 "Charged on WATER only, which is what the citation covers. "
                 "Carbon and organics are refractory at these temperatures and "
                 "ride in the hopper like rock.",
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
        "category":         "Launch vehicle reliability",
        "unit":             "probability of a successful launch",
        "value":            0.97,
        "range_low":        0.90,
        "range_high":       0.99,
        "notes": "v1.7.0.  Falcon 9 has flown >99% success over 300+ flights; "
                 "a first-flight or low-cadence vehicle sits near 0.90.  0.97 "
                 "is a fleet-representative figure for an operational booster "
                 "on a high-value payload.  Distinct from launch insurance, "
                 "which replaces the HARDWARE on failure — it does not "
                 "replace the revenue the mission would have earned.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Spacecraft mean time between failures",
        "unit":             "years of deep-space operation",
        "value":            30,
        "range_low":        15,
        "range_high":       60,
        "notes": "v1.7.0.  Exponential survival: P = exp(-T/MTBF).  Anchors "
                 "span the record — Voyager 1/2 past 45 years, New Horizons "
                 "19+, Dawn 11 (ended on hydrazine exhaustion, not failure), "
                 "against Akatsuki's orbit-insertion loss and Hayabusa's "
                 "near-total systems failure at 4 years.  30 years puts a "
                 "5-year mission at 85% survival, which matches the broad "
                 "deep-space record.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Mining system first-of-kind success probability",
        "unit":             "probability the rig works as designed",
        "value":            0.85,
        "range_low":        0.70,
        "range_high":       0.95,
        "notes": "v1.8.1.  Probability the excavation and beneficiation chain "
                 "works once it arrives — separate from the spacecraft "
                 "surviving the trip.  Counted from the actual flight record "
                 "of regolith-contact mechanisms rather than from the "
                 "failures alone, which is what v1.7.0's 0.75 did and it was "
                 "unfairly harsh:\n"
                 "  SUCCEEDED (10): Apollo 15-17 drills and scoops; Luna 16 / "
                 "20 / 24 drills; Stardust aerogel; Phoenix arm (sticky soil "
                 "delayed delivery but it worked); Curiosity drill (feed "
                 "mechanism failed 2016, recovered by feed-extended drilling); "
                 "Hayabusa2 sampler and SCI impactor, both touchdowns clean; "
                 "OSIRIS-REx TAGSAM, 121.6 g against a 60 g requirement; "
                 "Perseverance coring drill; Chang'e 5 and 6 drill + scoop.\n"
                 "  PARTIAL (1): Hayabusa — the projectile never fired, but "
                 "contact dust was still collected and returned.\n"
                 "  FAILED (2): Philae's harpoon pyrotechnics; InSight's HP3 "
                 "mole, which could not get purchase in Martian regolith.\n"
                 "That is 11/13 = 0.85 counting Hayabusa as the success it "
                 "ultimately was, or 10/13 = 0.77 counting it as a loss.  "
                 "0.85 is taken because Hayabusa did return its sample.\n"
                 "The honest caveat is that NONE of these is sustained "
                 "mining — they are one-shot or short-campaign collections of "
                 "grams to kilograms, not a rig moving 200 kg/day for years "
                 "with no maintenance.  0.85 is therefore the demonstrated "
                 "mechanism rate, and the sustained-operation risk on top of "
                 "it is carried by the spacecraft MTBF term rather than "
                 "double-counted here.  Grows with flight heritage — see "
                 "'Mining reliability growth exponent'.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Mining reliability growth exponent",
        "unit":             "Duane / AMSAA growth parameter (alpha)",
        "value":            0.30,
        "range_low":        0.10,
        "range_high":       0.60,
        "notes": "v1.9.0.  Reliability is not static across a programme — it "
                 "grows as failure modes are found and designed out.  The "
                 "Duane model has failure probability fall as n^(-alpha) with "
                 "cumulative production, and MIL-HDBK-189 puts alpha at "
                 "0.3-0.6 for an ACTIVE reliability-growth programme (one that "
                 "root-causes every anomaly and feeds fixes back) against "
                 "0.1-0.2 for passive fielding.  0.30 is the bottom of the "
                 "active band — appropriate for hardware that flies once every "
                 "few years, where each mission is a slow, expensive lesson "
                 "and there is no test fleet to accelerate the learning.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Mining system mature success probability",
        "unit":             "asymptotic ceiling on rig success probability",
        "value":            0.95,
        "range_low":        0.85,
        "range_high":       0.99,
        "notes": "v1.9.0.  Growth is asymptotic, not unbounded — no amount of "
                 "flight heritage makes a machine that grinds rock in vacuum "
                 "certain to work.  0.95 is where mature, high-cycle "
                 "spacecraft MECHANISMS sit: solar-array and antenna "
                 "deployments run ~97-99% across the fleet record, and a "
                 "continuously-operating excavator is harder than a one-shot "
                 "deployment.  Without this ceiling the Duane curve would "
                 "eventually promise certainty, which no mechanism earns.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Mining rig service life",
        "unit":             "years of operation before wear-out",
        "value":            15,
        "range_low":        5,
        "range_high":       30,
        "notes": "v1.7.0.  Caps how many missions one rig can actually serve, "
                 "which the old flat amortisation ignored — you cannot spread "
                 "a rig across 100 missions of 2 years each.  Bounded by "
                 "abrasive wear on regolith-contact mechanisms, thermal "
                 "cycling and radiation, not by propellant.  ISS-class "
                 "hardware is rated 15-30 years; a machine chewing rock is at "
                 "the low end.  Whatever life is left when the programme ends "
                 "is credited back as terminal value.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Mining rig maximum trips",
        "unit":             "mining campaigns before wear-out",
        "value":            5,
        "range_low":        2,
        "range_high":       12,
        "notes": "v1.12.0.  The SECOND half of rig service life, and the half "
                 "that was missing: 'Mining rig service life' above is a "
                 "CALENDAR bound, and calendar time is not what wears out a "
                 "machine that cuts rock.  Duty cycles are.  A rig sitting idle "
                 "between campaigns ages slowly; one digging continuously eats "
                 "cutting surfaces, seals and bearings on unweathered, angular, "
                 "never-water-rounded regolith.  Module 4 took min(years/stay) "
                 "alone, so at a short stay one rig served 12 consecutive "
                 "campaigns on the strength of a number that only ever said it "
                 "would not corrode meanwhile.  ⚠️  JUDGEMENT, and there is no "
                 "flight heritage for it — nothing has ever mined an asteroid "
                 "twice.  Bracketed from the two nearest analogues, which "
                 "disagree in the useful direction.  TERRESTRIAL: mobile mining "
                 "plant reaches major overhaul near 15,000-25,000 operating "
                 "hours (~2-3 yr of continuous duty, i.e. ~2 campaigns at this "
                 "model's ~1.25 yr stay) and survives 2-3 rebuilds before the "
                 "frame is retired — but every one of those rebuilds happens in "
                 "a workshop, and there is no workshop at an asteroid.  FLIGHT: "
                 "every regolith-contact mechanism ever flown was single-"
                 "campaign by design or failed inside one — TAGSAM fired once, "
                 "Philae's harpoons did not fire, InSight's mole never buried "
                 "itself, and Curiosity's drill lost its feed mechanism partway "
                 "through its first decade.  5 is therefore already the "
                 "optimistic reading of both: rebuild-interval life, achieved "
                 "un-rebuilt.  range_low 2 is one overhaul interval; "
                 "range_high 12 restores the pre-v1.12.0 behaviour, where the "
                 "calendar bound was the only bound.  Set Module 4's "
                 "`model_rig_trip_limit = False` for that exactly.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "Rig salvage fraction",
        "unit":             "fraction of remaining book value recoverable",
        "value":            0.50,
        "range_low":        0.00,
        "range_high":       0.80,
        "notes": "v1.7.0.  A part-worn rig parked on a specific asteroid is "
                 "worth something to whoever goes there next and nothing to "
                 "anyone else — an illiquid, location-locked asset with a "
                 "market of approximately one buyer.  Half of remaining book "
                 "value is a deliberately unheroic haircut.  Set 0.0 to "
                 "model abandonment.",
        "reference_year":   _REF_YEAR_OPS,
    },
    {
        "category":         "In-space processing plant throughput",
        "unit":             "kg processed per year per kg of plant",
        "value":            100,
        "range_low":        20,
        "range_high":       500,
        "notes": "v1.7.0.  Sizes the refinery that turns raw asteroid feedstock "
                 "into something a depot can actually build with.  Terrestrial "
                 "smelters run 1,000x their own mass per year; 100x is a heavy "
                 "derating for microgravity, no convection, no gravity-fed "
                 "materials handling and full autonomy.  Combined with the "
                 "$300k/kg recurring hardware rate this sets the capital "
                 "charge per kg refined.",
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
# STORAGE SYSTEMS REFERENCE TABLE  (v1.9.0)
# ─────────────────────────────────────────────────────────────────────────────
# Storage was the largest unmodelled block in this pipeline.  Before v1.9.0 the
# entire treatment of it was one column — `boiloff_pct_per_day` — and a
# `density_kg_per_L` that was computed, exported, and read by nothing.  Four
# distinct things were missing, and they fail in different ways:
#
#   propellant  Tank mass scales with VOLUME, so leaving it out subsidises
#               every low-density propellant.  Now derived per propellant in
#               PROPELLANTS_REFERENCE; the rows here are the shared constants
#               that derivation rests on, plus the active-cooling option, which
#               is the only way to trade mass and power against boil-off.
#   cargo       The mined mass has to be HELD.  Ore needs restraint against the
#               return burn; volatiles need to still be there after four years
#               of cruise.  This pipeline sells water at an in-space depot and
#               has never once asked what keeps it from subliming on the way.
#   energy      A rotating body spends roughly half its time in the dark and
#               the mining rig does not stop.  Storage, not generation, is what
#               sets the power system's mass in that regime — and past ~3 AU
#               photovoltaics stop being the answer at all.
#   depot       Propellant left in orbit for someone else to collect.  The
#               entry that makes Starship's escape payload mean anything.
#
# Rows are reference data.  What Module 4 consumes has a matching entry in
# OPERATIONAL_COSTS_REFERENCE, because that is the table `_ops_value()` reads;
# this table is the taxonomy and the citations behind those numbers.

_REF_YEAR_STORAGE = 2026

STORAGE_REFERENCE: List[dict] = [
    # ── PROPELLANT STORAGE ───────────────────────────────────────────────────
    {
        "name":            "Low-pressure liquid propellant tank",
        "domain":          "propellant",
        "unit":            "kg of tank per litre of propellant",
        "value":           _TANK_BASE_KG_PER_L,
        "range_low":       0.013,
        "range_high":      0.035,
        "status":          "operational",
        "trl":             9,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "The base figure every non-pressurised storage class in "
                 "PROPELLANTS_REFERENCE multiplies.  Bracketed by three flight "
                 "articles: Shuttle ET 0.0129 kg/L (big dumb tank, cheap per "
                 "litre), Falcon 9 stage 2 ~0.033, Centaur III ~0.035 (the last "
                 "two include thrust structure and avionics mounts).  Derivation "
                 "and the ∝V-vs-∝V^⅔ caveat are at _TANK_BASE_KG_PER_L.",
    },
    {
        "name":            "COPV burst performance factor",
        "domain":          "propellant",
        "unit":            "J per kg (PV/W)",
        "value":           _COPV_PERFORMANCE_J_PER_KG,
        "range_low":       250_000,
        "range_high":      600_000,
        "status":          "operational",
        "trl":             9,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "~40 km × g0.  Sets tank mass for every supercritical-gas "
                 "propellant: m/V = 1.5·p_operating/(PV/W).  This is why xenon "
                 "at 10 MPa pays 1.9% of its mass in tankage and krypton at "
                 "18 MPa pays 12.5% — the cheaper propellant needs the heavier "
                 "bottle, and the trade did not exist in this model before.",
    },
    {
        "name":            "Multi-layer insulation (passive)",
        "domain":          "propellant",
        "unit":            "kg per m² of tank surface",
        "value":           1.2,
        "range_low":       0.5,
        "range_high":      3.0,
        "status":          "operational",
        "trl":             9,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "60-layer aluminised-Mylar blanket, the passive baseline behind "
                 "every boiloff_pct_per_day figure in the propellant table. "
                 "Carried inside the storage-class tank multipliers rather than "
                 "as a separate area term, because this pipeline never computes "
                 "a tank's surface area — only its volume.",
    },
    {
        "name":            "Zero-boil-off cryocooler (20 K)",
        "domain":          "propellant",
        "unit":            "W electrical input per W lifted at 20 K",
        "value":           80.0,
        "range_low":       50.0,
        "range_high":      150.0,
        "status":          "development",
        "trl":             5,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Reverse-turbo-Brayton.  Carnot at 20 K against a 300 K reject "
                 "is 14 W/W and real machines run 15-25% of Carnot, so 50-150 "
                 "W/W.  NASA's ZBO and eCryo programmes have run 20 K coolers on "
                 "the ground; nothing has flown on a propellant tank.\n"
                 "This is the row that turns boil-off from a fact into a CHOICE: "
                 "spend array mass and power, keep the hydrogen.  Module 4 does "
                 "not offer that choice yet — it applies boiloff_pct_per_day "
                 "passively — so hydrolox is charged the full 0.05%/day with no "
                 "option to buy it down.  That is conservative for hydrolox and "
                 "it is a known gap, not a modelling decision.",
    },
    {
        "name":            "Cryocooler specific mass (20 K)",
        "domain":          "propellant",
        "unit":            "kg per W lifted at 20 K",
        "value":           5.0,
        "range_low":       2.0,
        "range_high":      15.0,
        "status":          "development",
        "trl":             5,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Cold head, compressor, recuperator and radiator.  Pairs with "
                 "the row above: a tank leaking 20 W needs ~100 kg of machine "
                 "and ~1.6 kW of electrical power to hold it at zero boil-off, "
                 "and the array for that 1.6 kW is another ~27 kg at 1 AU and "
                 "~240 kg at 3 AU.  Which is why zero-boil-off is a near-Sun "
                 "answer and passive tolerance is the far one.",
    },
    {
        "name":            "Vapour-cooled shield",
        "domain":          "propellant",
        "unit":            "fraction of passive boil-off removed",
        "value":           0.40,
        "range_low":       0.25,
        "range_high":      0.60,
        "status":          "operational",
        "trl":             8,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Route the boil-off gas through a shield on its way overboard "
                 "and it intercepts heat that would have boiled more.  Free in "
                 "power, cheap in mass, and it only works while something is "
                 "already boiling.  Flown on ground and airborne cryogenic "
                 "systems; the 0.05%/day hydrolox figure already assumes a "
                 "good passive stack including this.",
    },

    # ── CARGO / ORE CONTAINMENT ──────────────────────────────────────────────
    {
        "name":            "Bulk ore restraint (bag / hopper)",
        "domain":          "cargo",
        "unit":            "kg of containment per kg of ore",
        "value":           0.15,
        "range_low":       0.08,
        "range_high":      0.30,
        "status":          "development",
        "trl":             4,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Tankage, primary structure and cargo restraint for loose "
                 "regolith.  This is the number Module 4 carries as "
                 "`return_structure_frac_of_payload`, recorded here so the "
                 "cargo side of storage has a citation of its own.  Real cargo "
                 "spacecraft run 0.4:1 to 2:1 payload-to-structure; 0.15 is "
                 "aggressive and assumes dense ore in a body-mounted hopper "
                 "rather than a pressurised hold.  Before v1.10.0 it was zero "
                 "and the cascade happily loaded 125 t of ore into a 500 kg can.",
    },
    {
        "name":            "Volatile cargo containment (water ice)",
        "domain":          "cargo",
        "unit":            "kg of containment per kg of volatile cargo",
        "value":           0.05,
        "range_low":       0.03,
        "range_high":      0.12,
        "status":          "development",
        "trl":             4,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Water sold at a depot has to still be water on arrival.  In "
                 "vacuum at 1 AU, exposed ice in sunlight sits well above its "
                 "sublimation threshold and is simply gone; shaded and blanketed "
                 "it is stable for decades.  So the cost is a sealed, shaded "
                 "hold — heavier than an ore hopper, far lighter than a cryogen "
                 "tank, and no active power.\n"
                 "✅  MODELLED as of Module 4 v1.14.0, through the "
                 "'Volatile cargo containment' OPERATIONAL_COSTS row — this "
                 "table is not one Module 4 loads, which is why the figure sat "
                 "here unread for two releases while the pipeline priced water "
                 "at every in-space destination and charged nothing to keep it "
                 "through a four-year cruise.  It was not a rounding term: the "
                 "best cislunar missions run ~88% water by mass, so the "
                 "commodity carrying the result was the one flying free.",
    },
    {
        "name":            "Sintered / consolidated cargo",
        "domain":          "cargo",
        "unit":            "Wh per kg of ore consolidated",
        "value":           350,
        "range_low":       150,
        "range_high":      800,
        "status":          "concept",
        "trl":             3,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Melt or sinter the concentrate into billets and the restraint "
                 "problem mostly goes away — a solid block needs mounts, not a "
                 "hopper, and it cannot migrate under thrust or leak dust into "
                 "mechanisms.  Trades containment mass for processing energy at "
                 "a body where power is the binding constraint.  Studied for "
                 "lunar regolith (microwave sintering); not demonstrated on "
                 "asteroid material.",
    },
    {
        "name":            "Dust mitigation and seals",
        "domain":          "cargo",
        "unit":            "kg per kg of mining hardware",
        "value":           0.08,
        "range_low":       0.03,
        "range_high":      0.20,
        "status":          "development",
        "trl":             5,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Regolith fines are the failure mode that ended Apollo's "
                 "surface EVAs early and jammed InSight's mole.  In microgravity "
                 "the dust does not settle at all — Hayabusa2's impactor "
                 "experiment showed ejecta persisting for hours.  Labyrinth "
                 "seals, electrodynamic screens and bellows on every joint. "
                 "Folded into the mining-rig recurring rate in this pipeline "
                 "rather than charged separately; listed so it is visible.",
    },

    # ── ONBOARD ENERGY STORAGE ───────────────────────────────────────────────
    {
        "name":            "Li-ion battery (system level)",
        "domain":          "energy",
        "unit":            "Wh per kg",
        "value":           130,
        "range_low":       90,
        "range_high":      200,
        "status":          "operational",
        "trl":             9,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Cells reach 250-300 Wh/kg; packaging, harness, cell balancing "
                 "and thermal roughly halve it at the system level.  Already "
                 "inside the 60 W/kg 'Power system specific mass' row rather "
                 "than added to it — that row is explicitly PV + PMAD + battery "
                 "+ structure, which is why it is 60 W/kg against ROSA's ~150 "
                 "W/kg at the wing.",
    },
    {
        "name":            "Regenerative fuel cell",
        "domain":          "energy",
        "unit":            "Wh per kg",
        "value":           400,
        "range_low":       250,
        "range_high":      700,
        "status":          "development",
        "trl":             5,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Electrolyse water in the light, run it back through a fuel "
                 "cell in the dark.  3× a battery's energy density and it gets "
                 "better the longer the dark period, because tank mass and "
                 "converter mass are separate — which is the opposite of a "
                 "battery.  For a mining rig on a rotating body it is the "
                 "obvious architecture, and it stores the one consumable the "
                 "asteroid itself supplies.  Studied by NASA for lunar night "
                 "survival; not flown.",
    },
    {
        "name":            "Flywheel energy storage",
        "domain":          "energy",
        "unit":            "Wh per kg",
        "value":           100,
        "range_low":       40,
        "range_high":      180,
        "status":          "development",
        "trl":             6,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Unlimited cycle life and it doubles as a momentum wheel, which "
                 "a rotating-body operation needs anyway.  NASA G2 flywheel ran "
                 "on the ground at 60,000 rpm; the ISS flight unit was cancelled. "
                 "Energy density is no better than lithium, so it only wins where "
                 "cycle count or attitude control dominates.",
    },
    {
        "name":            "Eclipse / night-side power fraction",
        "domain":          "energy",
        "unit":            "fraction of mission time without sunlight",
        "value":           0.50,
        "range_low":       0.35,
        "range_high":      0.55,
        "status":          "operational",
        "trl":             9,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "A rig anchored to a rotating body is in shadow about half the "
                 "time — typical asteroid rotation periods run 2-20 h, so the "
                 "dark period is hours, not the 35 minutes of a LEO eclipse. "
                 "Sizing storage for it roughly DOUBLES the power system for a "
                 "given continuous draw.\n"
                 "✅  MODELLED as of Module 4 v1.14.0, through the "
                 "'Eclipse / night-side dark fraction', 'Energy storage usable "
                 "specific energy' and 'Power-system row baseline dark period' "
                 "OPERATIONAL_COSTS rows.  Module 4 now installs "
                 "[(1−f) + f/η]/(1−f) = 2.11× the continuous draw and adds the "
                 "storage the body's OWN rotation period demands, less what the "
                 "60 W/kg row already carries.  Radioisotope plants are exempt "
                 "and the EP array is exempt — one is flat with time, the other "
                 "is in permanent sunlight.",
    },
    {
        "name":            "RTG specific power",
        "domain":          "energy",
        "unit":            "W-electric per kg",
        "value":           5.0,
        "range_low":       2.4,
        "range_high":      5.5,
        "status":          "operational",
        "trl":             9,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "GPHS-RTG: 290 We at 56 kg = 5.2 W/kg (Cassini, New Horizons). "
                 "MMRTG: 110 We at 45 kg = 2.4 W/kg (Curiosity, Perseverance) — "
                 "worse, because it is designed to work in an atmosphere too. "
                 "Flat with heliocentric distance, which is the entire point: "
                 "at 1 AU the 60 W/kg solar row beats it twelve times over, at "
                 "3 AU solar falls to 6.7 W/kg and they cross, and past ~3.2 AU "
                 "nuclear wins outright.  The pipeline's catalog runs well past "
                 "3 AU.",
    },
    {
        "name":            "Fission surface power (Kilopower class)",
        "domain":          "energy",
        "unit":            "W-electric per kg",
        "value":           6.7,
        "range_low":       0.7,
        "range_high":      15.0,
        "status":          "development",
        "trl":             5,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "KRUSTY demonstrated a 1 kWe uranium-molybdenum reactor with "
                 "Stirling conversion in 2018 — the first new US space reactor "
                 "test in decades.  A 10 kWe flight unit is designed around "
                 "~1,500 kg, so 6.7 W/kg, and unlike an RTG it scales: the "
                 "reactor mass is dominated by shielding and radiator, not by "
                 "fuel.  The only power source in this table that could run a "
                 "hundred-kilowatt beneficiation plant at 3 AU.",
    },

    # ── IN-SPACE PROPELLANT DEPOTS ───────────────────────────────────────────
    {
        "name":            "Orbital propellant depot (cryogenic)",
        "domain":          "depot",
        "unit":            "% of stored mass lost per day",
        "value":           0.03,
        "range_low":       0.01,
        "range_high":      0.10,
        "status":          "development",
        "trl":             5,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "A depot beats a spacecraft tank on boil-off for one geometric "
                 "reason: heat leak scales with area and capacity with volume, "
                 "so a big tank leaks proportionally less.  It can also afford "
                 "the cryocooler and the sunshade that a departure stage cannot. "
                 "Nothing has flown; SpaceX's propellant-transfer demonstration "
                 "is the nearest thing in progress.",
    },
    {
        "name":            "Depot refuelling flights to escape",
        "domain":          "depot",
        "unit":            "tanker launches per fully-fuelled departure",
        "value":           12,
        "range_low":       8,
        "range_high":      16,
        "status":          "development",
        "trl":             4,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "SpaceX's own range for filling a Starship in LEO before a "
                 "high-energy departure.  Carried on the vehicle row as "
                 "`tanker_flights_for_escape` and charged by Module 4 from "
                 "v1.9.0.  Before that, Starship's 27 t to escape — which is "
                 "larger than its GTO payload precisely BECAUSE it assumes "
                 "refuelling — was priced at a single $90M launch.  The vehicle "
                 "row had said so in prose since v1.4.0.",
    },
    {
        "name":            "In-space propellant transfer loss",
        "domain":          "depot",
        "unit":            "fraction of transferred mass lost per transfer",
        "value":           0.03,
        "range_low":       0.01,
        "range_high":      0.08,
        "status":          "development",
        "trl":             4,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "Chill-down of the receiving tank, residuals in the transfer "
                 "line, and ullage settling.  Cryogenic transfer in microgravity "
                 "has been done at small scale (Robotic Refueling Mission, "
                 "storables) and never at stage scale.  Not modelled by Module 4 "
                 "— tanker flights are charged, transfer losses are not.",
    },
    {
        "name":            "ISRU propellant depot (asteroid water)",
        "domain":          "depot",
        "unit":            "USD per kg of propellant delivered to depot",
        "value":           50.0,
        "range_low":       20.0,
        "range_high":      200.0,
        "status":          "concept",
        "trl":             3,
        "reference_year":  _REF_YEAR_STORAGE,
        "notes": "The endpoint the whole pipeline points at: water mined, "
                 "electrolysed or simply boiled, and left in orbit for the next "
                 "vehicle.  Carried as `isru_processing_usd_per_kg` in Module 4, "
                 "where it prices the ISRU return propellant a mission makes for "
                 "ITSELF.  Selling propellant to a third party is a different "
                 "market with a different depth, and Module 2 does not price it "
                 "— the in-space demand ceilings cover materials, not fuel.",
    },
]

print(f"✅  Storage reference loaded — {len(STORAGE_REFERENCE)} systems "
      f"({len({s['domain'] for s in STORAGE_REFERENCE})} domains)")


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
    _apply_thruster_data(df)
    n_rep = int((df["thrust_scaling"] == "replicated").sum())
    print(f"     ✅  {len(df)} propellant systems "
          f"({n_rep} thrust by replication — see _THRUSTER_SYSTEMS)")
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


def load_storage() -> pd.DataFrame:
    print("\n🗄️   Loading storage-systems reference …")
    df = pd.DataFrame(STORAGE_REFERENCE)
    print(f"     ✅  {len(df)} storage systems")
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
    # The band applies to things that FLY.  v1.9.0 added non-rocket concepts
    # quoting $10-100/kg, which would trip a $100 floor built around Starship —
    # and tripping it would be meaningless, because those figures are
    # infrastructure amortisations rather than launch prices.  Concepts are
    # checked against a wider band of their own; only the flying fleet is held
    # to $100-$100,000.
    flying = launch_df[launch_df["status"].isin(["operational", "development",
                                                 "retired"])]
    bad_launch = flying[
        (flying["usd_per_kg_to_leo"] < 100)
        | (flying["usd_per_kg_to_leo"] > 100_000)
    ]
    if not bad_launch.empty:
        print(f"     ⚠️  {len(bad_launch)} flying launch rows outside "
              f"$100-$100 000 / kg-to-LEO sanity band:")
        for _, r in bad_launch.iterrows():
            print(f"          {r['name']}: {r['usd_per_kg_to_leo']:,.0f}")

    concepts = launch_df[launch_df["status"] == "concept"]
    bad_concept = concepts[
        (concepts["usd_per_kg_to_leo"] < 1)
        | (concepts["usd_per_kg_to_leo"] > 100_000)
    ]
    if not bad_concept.empty:
        print(f"     ⚠️  {len(bad_concept)} concept launch rows outside "
              f"$1-$100 000 / kg-to-LEO:")
        for _, r in bad_concept.iterrows():
            print(f"          {r['name']}: {r['usd_per_kg_to_leo']:,.0f}")

    # ── Payload g-load  (v1.9.0) ─────────────────────────────────────────────
    # Not a sanity check on the data — a capability check on the fleet.  Above
    # ~50 g a launcher can carry consumables and not machinery, which changes
    # what it is FOR rather than how much it costs.
    rough = launch_df[launch_df["max_accel_g"] > 50]
    if not rough.empty:
        print(f"     ℹ️   {len(rough)} launchers exceed 50 g and can lift bulk "
              f"material only, not mining hardware:")
        for _, r in rough.iterrows():
            print(f"          {r['name']}: {r['max_accel_g']:,.0f} g")

    # ── Propellant Isp sanity band ───────────────────────────────────────────
    # v1.9.0 widened this from 150-5,000 s, which was the range of the seven
    # propellants the table used to hold.  The floor is now cold gas (70 s) and
    # the ceiling nuclear pulse (10,000 s); anything outside 40-200,000 s is a
    # typo rather than a technology.  Propellantless rows carry Isp = inf by
    # construction and are excluded, not warned about.
    finite_isp = propellant_df[~propellant_df["propellantless"].astype(bool)]
    bad_isp = finite_isp[
        (finite_isp["isp_vac_s"] < 40) | (finite_isp["isp_vac_s"] > 200_000)
    ]
    if not bad_isp.empty:
        print(f"     ⚠️  {len(bad_isp)} propellant rows with implausible Isp:")
        for _, r in bad_isp.iterrows():
            print(f"          {r['name']}: {r['isp_vac_s']} s")

    # ── Propellant $/kg sanity band ──────────────────────────────────────────
    # Also widened: iodine at $60/kg and antimatter at $1e15/kg are both real
    # entries.  The band now only catches a missing or negative price.
    priced = propellant_df[~propellant_df["propellantless"].astype(bool)]
    bad_prop_cost = priced[
        (priced["cost_usd_per_kg"] <= 0)
        | (~np.isfinite(pd.to_numeric(priced["cost_usd_per_kg"], errors="coerce")))
    ]
    if not bad_prop_cost.empty:
        print(f"     ⚠️  {len(bad_prop_cost)} propellant rows with a missing or "
              f"non-positive price:")
        for _, r in bad_prop_cost.iterrows():
            print(f"          {r['name']}: {r['cost_usd_per_kg']}")

    # ── Tankage sanity  (v1.9.0) ─────────────────────────────────────────────
    # tank_kg_per_L / density is the fraction of its own mass a propellant pays
    # in tankage.  Above ~1.0 the tank outweighs its contents, which is real for
    # nothing in this table and would signal a density or storage-class error.
    tank_frac = (pd.to_numeric(propellant_df["tank_kg_per_L"], errors="coerce")
                 / pd.to_numeric(propellant_df["density_kg_per_L"], errors="coerce"))
    bad_tank = propellant_df[tank_frac > 1.0]
    if not bad_tank.empty:
        print(f"     ⚠️  {len(bad_tank)} propellant rows whose tank outweighs "
              f"the propellant:")
        for i, r in bad_tank.iterrows():
            print(f"          {r['name']}: {tank_frac[i]:.2f} kg tank / kg propellant")

    # ── Maturity gate is populated ───────────────────────────────────────────
    _VALID_STATUS = {"operational", "development", "concept", "retired"}
    bad_status = propellant_df[~propellant_df["status"].isin(_VALID_STATUS)]
    if not bad_status.empty:
        print(f"     ⚠️  {len(bad_status)} propellant rows with an unrecognised "
              f"status (Module 4 gates on this):")
        for _, r in bad_status.iterrows():
            print(f"          {r['name']}: {r['status']!r}")

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
    store_df  = load_storage()

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
    for df in (launch_df, prop_df, dv_df, ops_df, store_df, summary_df):
        df["catalog_date"]     = stamp
        df["pipeline_version"] = config.pipeline_version

    files = {
        "launch_vehicles.csv":          launch_df,
        "propellants.csv":              prop_df,
        "delta_v_segments.csv":         dv_df,
        "operational_costs.csv":        ops_df,
        "storage_systems.csv":          store_df,
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
        "storage_systems":   store_df,
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
import contextlib
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
    # `m_dry_return`   — return vehicle dry mass (TPS frame + chute + structure,
    #                    NOT the ablative TPS itself which scales with payload)
    mining_hardware_kg:        float = 2_000
    return_vehicle_dry_kg:     float = 500

    # ─── RETURN VEHICLE SCALES WITH ITS CARGO  (v1.10.0) ─────────────────────
    # `return_vehicle_dry_kg` was the WHOLE dry mass of the return vehicle, a
    # flat 500 kg however much it carried.  Since the payload is solved for
    # rather than specified, that let the cascade load 125 tonnes of ore into a
    # 500 kg can — a payload-to-structure ratio of 250:1, where real cargo
    # spacecraft run between 0.4:1 and 2:1.  Nothing caught it because the only
    # other check on returned mass was the launch vehicle's fairing VOLUME,
    # which a dense metal payload never fills.
    #
    # So the 500 kg becomes a floor — the irreducible avionics, comms, beacon
    # and separation hardware — and a structural fraction of the payload is
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
    #
    # ⚠️  DEFAULT TRUE as of v1.17.0, and unlike the flag below this one is
    # safe to flip on a weak-dominance argument rather than on a measurement:
    # `evaluate_combo` always also prices NOT concentrating (via
    # `beneficiate=False`, which is not the same as ratio 1.0 — see the
    # concentration search), so turning this on can only widen the option set.
    # A correctly-implemented search cannot get worse for that, which is the
    # never-worse invariant this project checks after every release.
    #
    # Checked anyway, on the full catalog at cislunar (2026-08-11, calc
    # 1.16.0): 650,921 pairs, max benef/raw 1.000000, ZERO exceptions, and
    # 102,765 bodies (15.79%) declining to concentrate at exactly 1.0 — the
    # documented signature, never worse and equal wherever it declines.
    #
    # What it costs is TIME, and that is the only reason it was ever off: a
    # full beneficiated cislunar pass measured 9,300 s against raw's 1,307 s,
    # a ratio of 7.1x.  Set False for the raw cell (26.7863x), which is what
    # most of the older tables in CLAUDE.md were measured at.
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
    # How hard to concentrate is an economic decision, not a setting — see
    # evaluate_combo.  This is how many points the profit sweep samples
    # between "don't concentrate" and "concentrate to pure best phase",
    # plus one refinement pass.  Raising it costs runtime linearly and buys
    # very little; 7 puts the optimum within a few percent.
    concentration_search_steps: int  = 7

    # ─── MODELLING COMPLETENESS  (v1.7.0) ────────────────────────────────────
    # Five things the pipeline previously got for free.  All default ON —
    # they are corrections, not options, and each one moves numbers.  Set any
    # to False only to isolate its effect.
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
    # NEAs hardest — their periods are near Earth's, so windows are years
    # apart.
    model_launch_windows:      bool  = True

    # BOUND-WATER LIBERATION.  C/B/D-type "ice" is water locked in
    # phyllosilicates; it has to be baked out at ~700 K, not scooped.  The
    # pipeline was extracting it for free while selling it at full
    # launch-cost-avoided.
    model_water_liberation:    bool  = True

    # LEARNING CURVE on recurring hardware.  Only NRE amortised across a
    # fleet; the rig cost $300k/kg at unit 1 and unit 500 alike.  Wright's
    # law at 85% is standard for aerospace serial production.  Has NO effect
    # at nre_amortization_missions = 1, where the cumulative average is the
    # first-unit cost by definition.
    learning_curve_rate:       float = 0.85   # 1.0 disables

    # MARKET SATURATION.  Prices were static at the point of sale, so a
    # mission could return any quantity of platinum at spot and the
    # "fly more missions" lever had no stopping point.  Constant-elasticity
    # demand: P/P0 = (1 + Q/Q_market)^(-1/ε).  Precious-metal demand is
    # inelastic (ε ≈ 0.5), so doubling world supply quarters the price.
    model_market_saturation:   bool  = True
    demand_elasticity:         float = 0.5

    # ─── MODELLING COMPLETENESS, PART 2  (v1.8.0) ────────────────────────────
    # RIG SERVICE LIFE AND TERMINAL VALUE.  The rig was amortised across
    # `nre_amortization_missions` with no upper bound, so a programme could
    # spread one rig across 100 missions of 2 years each — 200 years of duty
    # from a machine chewing rock.  It now has a finite life (Module 3, 15 yr),
    # which CAPS the amortisation, and whatever life is left when the
    # programme ends is credited back at the salvage fraction.
    #
    # The cap is the part that bites: at long stays it makes the rig markedly
    # MORE expensive than the old flat division, not less.  Terminal value is
    # only credited when there is a programme to inherit the rig
    # (nre_amortization_missions > 1) — a rig parked at an asteroid nobody
    # returns to is stranded, not an asset.
    model_rig_service_life:    bool  = True

    # MISSION RELIABILITY.  Revenue was certain.  It is not: the launch can
    # fail, the spacecraft can die in transit, and the mining chain has never
    # been demonstrated at all.  Expected revenue is multiplied by
    #     P = p_launch · exp(−T/MTBF) · p_mining
    # while COSTS are still charged in full, which is the conservative and
    # correct treatment — you spend the money either way.  Launch insurance
    # already in the cost model replaces hardware on failure, not revenue, so
    # there is no double count.
    model_reliability:         bool  = True
    # RELIABILITY GROWTH.  The mining chain learns: a programme's second rig
    # is not as likely to jam as its first.  p_mining becomes the FLEET
    # AVERAGE over nre_amortization_missions under the Duane model, capped at
    # a mature ceiling.  Exactly the first-of-kind figure at N = 1.
    # Launch and cruise reliability deliberately do NOT grow — launch vehicles
    # are already mature, and MTBF is a duration exposure, not a heritage
    # question.
    model_reliability_growth:  bool  = True

    # CRYOGENIC BOIL-OFF.  Return propellant sits in the tank from launch
    # until the departure burn — years, not hours.  Hydrolox loses ~0.05%/day
    # even with active cooling, which over a 5-year mission means loading 2.5×
    # what the rocket equation says you burn.  Without this, hydrolox wins
    # long missions it could not physically store propellant for.  ISRU return
    # propellant is exempt: it is manufactured at the asteroid on departure.
    model_propellant_boiloff:  bool  = True

    # PROPELLANT TANKAGE (v1.11.0).  A tank's mass scales with the VOLUME it
    # encloses, so leaving it out of the cascade subsidised whichever propellant
    # had the lowest density — which is the same propellant that has the
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
    #     load and recharge the store — [(1−f) + f/η]/(1−f) = 2.11× at f = 0.50.
    #     This is a sizing factor, so no W/kg figure could ever have carried it.
    #   • the store itself has to hold the load across the dark period, which is
    #     set by the BODY'S OWN rotation period — so this term is per-asteroid,
    #     and a slow rotator is genuinely a worse place to mine.
    #
    # Exempt: a radioisotope plant (flat output, no night) and the EP array
    # (interplanetary cruise, permanent sunlight).  Both exemptions are physical
    # rather than conservative, and the RTG one has a visible consequence —
    # eclipse is what finally makes the radioisotope branch worth choosing on
    # more than a rounding number of bodies.
    model_eclipse_power:       bool  = True
    # Median of the 29,288 catalog bodies that have a MEASURED rotation period
    # (2026-08-08).  Used only where the body does not state one — about two
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
    # has asked for this since v1.4.0 — its 27 t to escape EXCEEDS its 21 t to
    # GTO precisely because it assumes refuelling — and until now its escape
    # payload was priced at one $90M launch.
    #
    # v1.12.0: the charge is real but it belongs to the ESCAPE-DIRECT scenario,
    # which is what the Module 3 note actually asked for and which this module
    # does not have.  Stage 4 reads `payload_leo_kg` / `usd_per_kg_to_leo` and
    # nothing else — the vehicle is a LEO lifter and the stack departs on its
    # own outbound stage — so no mission here is ever refuelled, and v1.11.0
    # was billing $1.08B for a capability it never used.  Setting
    # `escape_direct_launch` True re-arms it, and nothing does that yet.
    charge_tanker_flights:     bool  = True
    escape_direct_launch:      bool  = False

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

    # ─── WHAT THE PER-ASTEROID SEARCH OPTIMISES  (v1.10.0) ───────────────────
    # Every search in this module — concentration ratio, vehicle, propellant,
    # return mode, propellant sourcing — has to rank candidate missions by
    # something, and until v1.10.0 that something was `profit_usd`.  In this
    # model revenue sits orders of magnitude below cost, so profit is very
    # nearly minus the cost, and maximising it quietly became "pick the
    # cheapest mission" — while the project ranked the output by a cost/revenue
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
    # once for the whole catalog instead — whether to aerocapture, and whether
    # to make return propellant on site — even though the right answer to both
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
    # Return Δv is reduced — per asteroid, from its own arrival v_infinity —
    # but a heat-shield mass overhead is added at the rate from Module 3, and
    # that mass is hauled outbound AND pushed back through the return burn.
    # Only available where the architecture actually enters an atmosphere:
    # earth_surface (direct entry), leo (aerocapture + aerobraking) and
    # mars_surface.  Cislunar and lunar_surface ignore it — see uses_tps().
    use_aerocapture_return:    bool  = True
    aerocapture_dv_savings_m_s: float = 4_000   # fallback only, when elements are unusable
    heat_shield_frac_of_payload: float = 0.15   # TPS mass = 15% of returned payload

    # ─── ISRU  (return propellant manufactured at the asteroid) ──────────────
    # Return propellant is not hauled outbound; it is electrolysed from mined
    # water.  Available only where that is physically possible — a hydrolox
    # stage at a body with a non-zero ice fraction — and the rock it takes to
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
    # made.  The mining, hauling and water-liberation energy are NOT in here —
    # they are charged through the feed, the dig time and the power plant.
    isru_processing_usd_per_kg:    float = 50.0

    # ─── COST AMORTISATION & FINANCIAL ───────────────────────────────────────
    # Spacecraft development NRE (~$588M for OSIRIS-REx class).  If 1, the
    # first mission carries the full NRE; raise N to spread across a fleet.
    nre_amortization_missions: int   = 1
    # ─── PROGRAMME SCALE AND FLEET SIZE (v1.15.0) ────────────────────────────
    # `nre_amortization_missions` above is N, the programme size, and until
    # v1.15.0 it was an INPUT — the curve of answer-against-N was mapped by
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
    # run no longer reproduces them — set this False to do that.  This comment
    # used to argue the flip would "silently retire every committed figure at
    # once with no way to reproduce them", and the second half of that was the
    # real objection: the two settings had never been measured side by side on
    # the real population, so OFF was the only anchor anyone had.
    #
    # That is no longer true.  The full cislunar 2x2 was measured on the full
    # 1.55 M-row catalog on 2026-08-11 (calc 1.16.0) and is in CLAUDE.md, and
    # the OFF cells reproduce their committed values exactly — 26.7863x raw and
    # 20.5895x beneficiated, both unmoved across four releases.  The N = 1
    # answer is now a recorded measurement rather than a thing you would lose.
    #
    # It is NOT free.  Measured at 2.98x runtime on the full raw cislunar cell
    # (1,307 s -> 3,890 s), because the 2-D (F, W) search prices a median of 40
    # programmes per surviving candidate against the 1-D ladder's 8.  The
    # sample this release was developed on predicted 1.10x, and v1.15.0's
    # 1-D ladder measured 1.51x; neither carries over.
    #
    # ✅  THE KNOWN GAP THIS COMMENT USED TO DESCRIBE IS CLOSED IN v1.16.0 by
    # `model_programme_calendar` below.  It read: the fleet is only ever the
    # MINIMUM that can fly N missions, because a programme of F ships flying
    # `trips` campaigns each spans `trips × mission_duration` of calendar and
    # nothing charged for it — so buying a second ship only ever added market
    # saturation, and F never wanted to exceed ceil(N / trips).  Fleet size was
    # a one-sided decision.  It is now two-sided, and the search is
    # two-dimensional over (F, W) rather than a ladder over F.
    optimise_programme_scale:  bool  = True
    # Upper bound on the fleet search.  Not a physical limit — it is where the
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
    # 12 consecutive campaigns — a bound derived entirely from a figure about
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
    # True charges the difference — see `programme_calendar_multipliers` for
    # the derivation and for why the rig's salvage credit is compounded the
    # OTHER way.  Exactly 1.0 at W = 1, so every single-mission figure in this
    # project is untouched, which is every committed figure except the
    # N = 10 / N = 100 curve.
    #
    # It also makes the programme search two-dimensional.  Campaigns-per-ship
    # was not previously a decision — every lever improved with N, so the
    # optimum was always the top of a fleet band — and the calendar charge is
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
    # Time-value of money — compound up-front costs over mission_duration_yr.
    apply_wacc_compounding:    bool  = True
    contingency_fraction:      float = 0.20

    # ─── VEHICLE / PROPELLANT SELECTION ──────────────────────────────────────
    # None = use everything operational; set lists to restrict candidates.
    candidate_vehicles:        Optional[List[str]] = None
    candidate_propellants:     Optional[List[str]] = None
    operational_vehicles_only: bool = True
    # v1.11.0.  Module 3 v1.9.0 grew the propellant table from 7 rows to 40,
    # and 17 of the additions are development or concept hardware — nuclear
    # thermal, VASIMR, fusion, an Orion pulse drive.  Left ungated, a search
    # that maximises profit would fly every asteroid on antimatter.  This
    # mirrors `operational_vehicles_only` exactly: True keeps the search to
    # propellants that have actually moved a spacecraft.  Retired rows
    # (mercury ion) are excluded either way.
    operational_propellants_only: bool = True

    # ─── DISPLAY ─────────────────────────────────────────────────────────────
    top_n_preview:             int = 20
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
    # 2026-08-08 at cislunar, six physical cores / 12 workers, on the full
    # 1,554,351-row v1.1.0 catalog:
    #     raw           2,539 s (42 min), 668,004 evaluable rows, 1.06 GB out
    #     beneficiated  ~2.2 h ESTIMATED, not yet measured
    #
    # ⚠️  DO NOT BUDGET BY SCALING A SMALL RUN.  Scaling a 20,000-row sample
    # predicted 2.2 h for that raw run and it took 42 minutes -- a 3.1x
    # overestimate.  Fixed costs (worker startup, loading a 0.88 GB catalog)
    # dominate a small run, and parallel efficiency is much better on a large
    # one, so per-row cost falls sharply with size.  It is not linear.
    eval_row_cap:              int = 0

    # HOW a cap selects its rows.  Only consulted when eval_row_cap > 0.
    #   "stride" — take every Nth row across the whole sorted catalog
    #   "head"   — take the first N rows (the pre-v1.13.0 behaviour)
    #
    # Stride is the default because the catalog reaches this module sorted by
    # semi-major axis, so `head` was never a sample of the catalog — it was the
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
    #   0  — auto.  One worker per logical CPU, scaled down when there are too
    #        few asteroids to repay the spawn cost (no fork on Windows, so each
    #        worker is a fresh interpreter plus a pandas import).
    #   1  — force the serial path.  Use it to profile, or when an outer
    #        harness already runs one process per destination and the cores are
    #        spoken for.
    #  >1  — exactly that many workers, clamped to the CPU count.
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
    # is no mission behind it to lose — measured on 68,136 (combo × dv × ISRU)
    # tuples across both settings at cislunar, zero of the pruned candidates
    # produced a result when solved in full.
    #
    # Turn it OFF to check that claim on a population this repo has not tried,
    # or to profile the unpruned search.  Do not turn it off because a number
    # looks wrong; if pruning ever changes an output, that is a BUG in the
    # pre-filter and the two builds should be diffed column by column.
    prune_infeasible_combos:   bool = True

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
    # 1.7.0 — MODELLING COMPLETENESS.  Five things the pipeline previously got
    #         for free.  Unlike v1.5.0/1.6.0 these are CORRECTIONS, not new
    #         options: they default ON and every number moves.  Paired with
    #         Module 2 v1.5.0 and Module 3 v1.6.0.
    #         • LOW-THRUST TRIP TIME.  Electric propulsion paid a Δv penalty
    #           but flew its burns instantly on power it never carried.  A
    #           thruster's power fixes its thrust, T = 2ηP/(Isp·g0), so
    #           burning m_prop takes m_prop(Isp·g0)²/(2ηP) — high Isp buys
    #           propellant mass at a QUADRATIC cost in time-or-power.  The EP
    #           stage is now sized to finish inside ep_target_thrust_yr, its
    #           array (1/r²) and thruster/PPU mass enter the rocket equation,
    #           and the thrusting time enters mission duration.  Validated
    #           against Dawn: 5.0-9.3 yr predicted at its 2.2-3.0 AU operating
    #           distance against ~5.9 yr actually flown.
    #           This was load-bearing — v1.6.0's headline Mars result was a
    #           1,500 s Hall thruster that would have needed 48 kW and a
    #           4-tonne array at 2.26 AU.
    #         • LAUNCH WINDOWS.  Departure needs phasing, and alignments recur
    #           at the synodic period, so expected wait after mining is half a
    #           period.  Punishes NEAs hardest — a body at a = 1.05 AU has a
    #           10-year synodic period with Earth against 1.3 years for a
    #           main-belt object.  Δv accessibility and TIME accessibility
    #           pull in opposite directions and only one was modelled.
    #         • BOUND-WATER LIBERATION.  C/B/D "ice" is water in
    #           phyllosilicates, baked out at ~700 K, not scooped: 2,500 Wh
    #           per kg of water (Module 3).  It was being extracted free and
    #           sold at full launch-cost-avoided.
    #         • LEARNING CURVE.  Wright's law at 85% on the per-mission
    #           articles (capsule/lander, power system).  The amortised mining
    #           rig is excluded — it is one shared unit, not N built.  Exactly
    #           1.0 at nre_amortization_missions = 1, so a single-mission run
    #           is untouched.
    #         • MARKET SATURATION.  P/P0 = (1 + Q/Q_market)^(-1/ε) against
    #           Module 2's annual_market_kg.  Returning 180 t/yr of platinum
    #           doubles world supply and quarters the price; delivering 6.6
    #           t/yr of water to a 20 t/yr Mars base cuts it to 0.57.  Without
    #           this the "fly more missions" lever had no stopping point.
    #         New config: model_low_thrust_time, ep_target_thrust_yr,
    #         max_mission_duration_yr, model_launch_windows,
    #         model_water_liberation, learning_curve_rate,
    #         model_market_saturation, demand_elasticity.
    #         New output columns: is_electric, ep_power_w, ep_system_kg,
    #         ep_thrust_yr, synodic_period_yr, launch_window_wait_yr,
    #         water_liberated_kg, saturation_multiplier, learning_curve_factor.
    # 1.8.0 — MODELLING COMPLETENESS, PART 2.  Four more corrections, all
    #         default ON.  Paired with Module 2 v1.6.0 and Module 3 v1.7.0.
    #         • RIG SERVICE LIFE + TERMINAL VALUE.  The rig was amortised
    #           across nre_amortization_missions with no upper bound, so a
    #           programme could spread one machine across 100 missions of two
    #           years each -- 200 years of duty from something chewing rock.
    #           A 15-year life now CAPS the amortisation, and the cap makes
    #           long-stay programmes markedly MORE expensive, not less:
    #           at a 2-year stay one rig serves 7 missions, not 100, so the
    #           per-mission charge is 13.8x what the old flat division gave.
    #           Life left when the programme ends is credited at the salvage
    #           fraction (0.50) -- but only when nre_amortization_missions > 1.
    #           A rig parked at an asteroid nobody revisits is stranded, not
    #           an asset, so a single-mission run is unchanged.
    #         • MISSION RELIABILITY.  Revenue was certain.  Expected revenue
    #           is now p_launch(0.97) x exp(-T/MTBF)(30 yr) x p_mining(0.75),
    #           about 0.62 for a 5-year mission.  COSTS are charged in full,
    #           which is the correct treatment -- you spend the money either
    #           way -- and launch insurance replaces hardware, not revenue, so
    #           there is no double count.  p_mining is the honest one: nobody
    #           has ever sustained-mined an asteroid, and regolith-contact
    #           mechanisms are where deep-space missions fail.
    #         • CRYOGENIC BOIL-OFF.  Return propellant sits in the tank from
    #           launch to the departure burn -- years.  Hydrolox loses
    #           0.05%/day even actively cooled, so a 5-year hold means loading
    #           ~2.5x what the rocket equation burns.  Folded into an
    #           effective return Δv, which leaves the closed-form cascade
    #           exact: since m_return_prop scales with (R-1), inflating that
    #           term by k is R_eff = 1 + (R-1)k.  ISRU is exempt.
    #           Without this, hydrolox won long missions it could not
    #           physically store propellant for.
    #         • IN-SPACE MANUFACTURING is costed in Module 2 v1.6.0 rather
    #           than hidden inside the 0.70 utility factor -- ~$230/kg for
    #           metals, energy at $6.08/kWh (the capital cost of a Watt in
    #           deep space) plus $200/kg of amortised refinery.
    #         New config: model_rig_service_life, model_reliability,
    #         model_propellant_boiloff.
    #         New output columns: p_success, boiloff_factor,
    #         dv_ret_effective_m_s, rig_terminal_value_usd,
    #         missions_sharing_rig.
    # 1.9.0 — RELIABILITY GROWTH.  p_mining was pinned at its first-of-kind
    #         0.75 however many missions a programme flew, which was the one
    #         place the model was pessimistic rather than optimistic: a fleet
    #         that has flown ten rigs has found and fixed failure modes the
    #         first one discovered the hard way.
    #         Duane / AMSAA: q(n) = q_first * n^(-alpha), alpha = 0.30 from
    #         MIL-HDBK-189's active-growth band, capped at a 0.95 mature
    #         ceiling because growth is asymptotic -- no heritage makes a
    #         machine grinding rock in vacuum certain to work.
    #         Reported as the MEAN over missions 1..N, not the terminal value.
    #         That is what the rest of the cost model needs: NRE and the rig
    #         are amortised across the whole programme, so per-mission
    #         expected revenue must use the programme average.  Quoting the
    #         last mission's reliability would credit every mission with
    #         heritage only the last one has.
    #             N=1   p_mining 0.750  (unchanged -- single-mission runs
    #                                    are bit-identical to v1.8.0)
    #             N=10           0.838
    #             N=100          0.912
    #         Launch and cruise reliability deliberately do not grow: launch
    #         vehicles are already mature, and MTBF is a duration exposure
    #         rather than a heritage question.
    #         New config: model_reliability_growth.
    #         New output column: p_mining.
    # 1.9.1 — recalibrated the first-of-kind mining success probability from
    #         0.75 to 0.85.  The old figure was counted from failures alone
    #         (OSIRIS-REx's jammed flap, Hayabusa's dead projectile, Philae's
    #         harpoons) with none of the successes, which is selection bias.
    #         The full regolith-contact flight record is 10 clean successes
    #         (Apollo, Luna 16/20/24, Stardust, Phoenix, Curiosity,
    #         Hayabusa2, OSIRIS-REx, Perseverance, Chang'e 5 and 6), one
    #         partial (Hayabusa returned its sample despite the sampler
    #         failing) and two failures (Philae's harpoons, InSight's mole):
    #         11/13 = 0.85, or 0.77 if Hayabusa is counted as a loss.  0.85
    #         is taken because Hayabusa did return its sample.
    #         Sustained-operation risk is NOT double-counted here — none of
    #         those missions was sustained mining, and the exposure is
    #         already carried by the spacecraft MTBF term.
    #         Effect: P(success) on a 5-year mission rises 0.62 -> 0.70, and
    #         every cost/revenue ratio improves ~13%.
    # 1.10.0 — PER-ASTEROID ARCHITECTURE SEARCH, plus three physical
    #         corrections it exposed.  Every number this module produces
    #         changes; the committed result tables need re-measuring.
    #         • RETURN MODE IS NOW CHOSEN, NOT SET.  use_aerocapture_return
    #           forced aerocapture on every asteroid wherever the destination
    #           allowed it.  But aerocapture is a trade, not a saving: it buys
    #           Δv with a heat shield massing 15% of the returned payload,
    #           hauled outbound as dead mass and pushed back through the return
    #           burn.  Whether that pays depends on the target's arrival
    #           v_infinity and on the stage's Isp — both per-asteroid.  Both
    #           modes are now priced and the profitable one flown.  The flag
    #           now means "available", not "mandatory".
    #         • RENDEZVOUS APSIS IS NOW SEARCHED.  The Δv estimator met every
    #           target at its aphelion unless the whole orbit was interior to
    #           Earth's.  That rule is right for most main-belt bodies and
    #           wrong for others: meeting at aphelion means a slow transfer
    #           with a cheap match burn and an expensive departure, meeting at
    #           perihelion the reverse, and which dominates is a property of
    #           a and e together.  Both are priced now, and — because the two
    #           legs are costed against different bodies — the winner is
    #           resolved against the DESTINATION, so a body best met at
    #           aphelion for an Earth return can be met at perihelion for Mars.
    #           New asteroid_transfer_options_km_s / asteroid_dv_options.
    #         • ISRU IS NOW PHYSICAL, AND PER-ASTEROID.  The old switch deleted
    #           the return propellant from the cascade for EVERY asteroid and
    #           charged $50/kg.  It never asked what the body was made of (an
    #           M-type with zero ice made propellant out of nothing), never
    #           asked what the propellant was (xenon and argon are noble gases;
    #           the switch synthesised them at a rubble pile), and never
    #           charged the feed, the dig time or the bake-out energy — which
    #           is the entire cost of ISRU.  Now: hydrolox only, at bodies with
    #           a non-zero ice fraction, at the stoichiometric 1.286 kg of
    #           water per kg of propellant, and the rock it takes comes off the
    #           rig's throughput and the body's mineable mass BEFORE any ore is
    #           loaded, costs dig time, and pays the 2,500 Wh/kg liberation
    #           energy through the same power plant and the same rocket
    #           equation as everything else.  Default flipped False -> True:
    #           gated and costed, it is an option a real programme would
    #           evaluate, and denying it outright was its own distortion.
    #         • BOIL-OFF NOW USES THE REAL HOLD TIME.  It was computed once,
    #           before the sizing loop, against a stay of station_keeping_floor_yr
    #           (0.25 yr) — but the stay is dig time plus the launch-window
    #           wait, which run to years on exactly the targets that want a
    #           cryogenic stage.  Now solved inside the fixed point with the
    #           other coupled terms.  Hydrolox on a 4-year hold loads 2.1x what
    #           it burns, against the ~1.1x the old estimate implied.
    #         • EARTH-SURFACE PROPULSIVE RETURN PAYS ITS DEORBIT BURN.  The leg
    #           was documented as "capture into LEO, then deorbit" and priced
    #           as capture only, making it numerically identical to ret_leo_prop.
    #           +100 m/s.
    #         New config: optimise_architecture_per_asteroid.
    #         New output columns: aerocapture_return, isru_return,
    #         isru_propellant_kg, isru_feed_kg, rendezvous_apsis.
    # 1.10.1 — PERFORMANCE ONLY.  NO NUMBER IN THIS MODULE'S OUTPUT CHANGES.
    #         Verified, not asserted: serial and parallel runs of the same
    #         rows produce byte-identical CSVs (sha256 compared, cislunar and
    #         earth_surface, beneficiated and raw), and the pre-change build
    #         produces the same file as the post-change one.  The five-
    #         destination tables and the programme-scale curve stand as
    #         measured on 1.10.0 — do NOT re-measure them on account of this
    #         version.  The stamp moves only so that a CSV still names the
    #         code that produced it.
    #         • THE MAIN LOOP IS PARALLEL.  Asteroids are independent, so the
    #           search was always embarrassingly parallel, and it had always
    #           run on exactly one core.  New `parallel_workers`; chunks are
    #           consumed in submission order so the row order — and therefore
    #           the tie order under the non-stable sort — is unchanged.
    #         • CATALOG ROWS ARE DICTS IN THE HOT PATH.  Every consumer reads
    #           a row with `.get(key)` / `[key]` and nothing else, but pandas
    #           resolves each through the index at ~5 us; the search does
    #           ~7,400 per asteroid.  That was ~38% of total runtime spent
    #           re-deriving positions in an index that never changes.
    #           Series.to_dict() unboxes numpy scalars to Python ones, which
    #           is value-preserving — np.float64 IS a C double.  1.73x.
    #         • The five ops-table constants the sizing loop needs are
    #           memoised instead of looked up per (asteroid × vehicle ×
    #           propellant × architecture × ratio) — ~24M lookups of five
    #           unchanging numbers.  A further 1.09x.
    #         Net ~1.9x per core, ~7x wall-clock on 12 threads.
    # 1.11.0 — STORAGE, AND A MUCH WIDER CATALOG.  Pairs with Module 3 v1.9.0,
    #         which took the propellant table from 7 rows to 40 and the vehicle
    #         table from 12 to 36.  Every number moves.
    #         • PROPELLANT TANKAGE IS IN THE ROCKET EQUATION.  Module 3 has
    #           computed `density_kg_per_L` since v1.2.0 and NOTHING read it,
    #           so a tank's mass — which scales with VOLUME, not with the
    #           propellant mass inside it — was free.  That was a straight
    #           subsidy to whichever propellant had the lowest density, which
    #           is the same propellant that has the highest Isp, so the error
    #           compounded rather than cancelling.  The closed form generalises
    #           with two scalars: k = 1/(1 − t(R_ret−1)) on the return leg,
    #           where the tank flies home with the cargo, and k_out on the
    #           outbound leg, where it is staged at the asteroid.  Both are 1
    #           at t = 0, so `model_tank_mass = False` reproduces v1.10.1
    #           exactly.  t(R−1) ≥ 1 is "the tank cannot close" and is
    #           infeasible rather than expensive.
    #         • THE MATURITY GATE NOW APPLIES TO PROPELLANTS.  17 of Module 3's
    #           new rows are development or concept hardware; ungated, a
    #           profit-maximising search flies every asteroid on antimatter.
    #           `operational_propellants_only` mirrors the vehicle flag.  Two
    #           further filters are about the mission profile rather than
    #           maturity and apply regardless: `restartable` excludes solids
    #           (a return burn fires years after launch and a solid cannot be
    #           relit) and `propellantless` excludes sails (infinite Isp
    #           otherwise reports an unbounded payload).
    #         • THE RTG ROW IS FINALLY READ.  Module 3 has priced radioisotope
    #           power since v1.2.0, with a note saying it is for past ~3 AU,
    #           and no code ever looked at it — so every main-belt body flew a
    #           photovoltaic array starved by 1/r².  Solar is 60 W/kg at 1 AU
    #           and an RTG is 5 W/kg everywhere, so they cross at 3.46 AU.
    #           Capped by `rtg_max_power_w` because the binding constraint is
    #           Pu-238 supply (~1.5 kg/yr of DOE production), not money, and
    #           charged at its own $500k/W rather than the $800/W solar rate.
    #           Deliberately not applied to the EP array — see
    #           power_source_for_target.
    #         • ORBITAL REFUELLING IS CHARGED.  Starship's escape payload
    #           EXCEEDS its GTO payload, which is only possible because the
    #           escape figure assumes tanker flights.  Module 3's row has said
    #           so in prose since v1.4.0, including the fix; this implements it
    #           via `tanker_flights_for_escape`.  12 flights at list price is
    #           $1.08B on top of a $90M launch.
    #         • ISRU IS NO LONGER HYDROLOX-ONLY.  v1.10.0 hardcoded the tuple
    #           ("hydrolox",), which was right about the chemistry it knew and
    #           wrong about the question: electrolysing water to cryogenic
    #           hydrogen is the HARDEST thing to do with asteroid water, not
    #           the only one.  A steam rocket boils it at 1.00 kg of water per
    #           kg of propellant against hydrolox's 1.286, with no
    #           electrolyser and no cryogenic tank, and buys that at 190 s
    #           against 452.  Which wins varies by body, so it belongs in the
    #           per-asteroid search.  Feed ratio and feed MATERIAL now come off
    #           the propellant row, and the water-liberation energy follows the
    #           propellant instead of a constant.
    #         • Lunar-origin launch systems are excluded structurally rather
    #           than by status: this module departs from Earth, and their
    #           payload columns are annual throughput, so reading them would be
    #           a unit error rather than merely optimism.
    #         New output columns: tank_mass_frac, m_tank_return_kg,
    #         m_tank_outbound_kg, propellant_storage_class, power_source,
    #         tanker_flights, tanker_cost_usd, isru_feed_material.
    # 1.12.0 — a realism audit.  Every item is a term that existed on one side
    #         of the model and not the other, and all of them move the answer
    #         the same way: WORSE.  Full catalog at cislunar, raw 31.7712x ->
    #         33.2342x (+4.60%), beneficiated 22.4665x -> 23.9169x (+6.46%).
    #         Cislunar is still the best case and its winner is unchanged
    #         (7753 B, now concentrating 5.311x).
    #         ⚠️  THE RATIOS ARE NOT THE HEADLINE.  Evaluable rows HALVED,
    #         ~31,000 -> ~15,500, because half the catalog was closing its mass
    #         budget on a micronewton thruster sized as a cargo tug.  Those
    #         missions were never physical.  Any per-row comparison against a
    #         v1.11.0 catalog compares different populations.
    #         • THE DEVICE WAS NEVER MODELLED, ONLY THE PROPELLANT — the
    #           largest correction here.  Launch is an integrated vehicle with
    #           a payload it can lift; in-space propulsion was a bare Isp.  One
    #           side had a capacity limit and the other did not.  The EP stage
    #           was sized on POWER alone, so 31.8% of raw winners were PULSED
    #           PLASMA THRUSTERS (EO-1: 860 uN) and 24.3% ELECTROSPRAY (ST7-DRS:
    #           5-30 uN each), being asked for ~7-10 N.  Fixed by MASS, not by a
    #           threshold: `ep_thrust_required_n` (T = m_prop*ve/t, which owes
    #           nothing to efficiency) times Module 3's per-technology
    #           `thruster_kg_per_n`.  A uN/kg device reports thousands of tonnes
    #           of thruster and fails to close on its own, exactly as a
    #           low-density propellant does on tankage.  `thruster_efficiency`
    #           likewise replaces one shared 0.60 — a PPT is ~8%, a gridded ion
    #           thruster 70%, so the array differs ~9x.  The lumped 8 kg/kW
    #           "thruster + PPU" row is split: PPU scales with POWER (4.7 kg/kW,
    #           NEXT-C), thruster head with THRUST.  Zero replicated-scaling
    #           devices survive; chemical propulsion stops being extinct
    #           (hydrolox 5.5% of rows).
    #         ⚠️  The ARGON fix below moved NEITHER headline cell — the best
    #         missions at cislunar were never flying argon — while changing the
    #         chosen propellant for a quarter of the catalog (argon 25.0% ->
    #         2.4% of raw winners, 27.3% -> 0.0% beneficiated) and making 1,059
    #         bodies infeasible.  Read that before using a single best-case
    #         cell as a regression test: it is blind to a change that is wrong
    #         everywhere except at the top.  The propellant-share breakdown and
    #         the evaluable-row count are what caught it.
    #         • THE CARGO-WATER ARRAY WAS PRICED AND NEVER FLOWN.  Liberation
    #           energy for water sold as cargo was added to `processing_power_w`
    #           AFTER the cascade had been built, so `power_system_kg` came out
    #           0.8-2.7% above the figure inside `hardware_total_kg` on every
    #           row that liberated any — and the comment there asserted the
    #           cascade had already flown it.  97 of 357 sample rows violated
    #           `hardware_total_kg == mining_hardware_kg + power_system_kg +
    #           ep_system_kg`, by up to 408 kg.  Now zero.  This is the free-EP
    #           -stage bug pointing the other way: a price with no mass.
    #           A RAW mission to an icy body was the worse case — it paid for an
    #           array and flew none of it, because the sizing loop skipped the
    #           term entirely unless beneficiating.
    #         • PROPELLANT TANKAGE HAD NO COST LINE.  Flown through the rocket
    #           equation since v1.11.0, charged its launch $/kg, and built for
    #           free.  ~0.003-0.1% of mission cost; kept because the recurring
    #           defect in this codebase is a mass in one cascade with no entry
    #           in the other, and those are only found by checking every term.
    #         • LAUNCH INSURANCE UNDER-BOOKED THE SPACECRAFT.  Book value was
    #           rig + capsule, which was the whole vehicle in v1.4.0.  It never
    #           picked up the v1.5.0 power plant, the v1.10.0-priced electric
    #           stage or v1.11.0 tankage — a 300 kW electric stage is a
    #           nine-figure article and it was flying uninsured.
    #         • THE TANKER CHARGE WAS KEYED TO THE WRONG SCENARIO.  Module 3's
    #           note asked for it "in the ESCAPE-DIRECT scenario"; v1.11.0
    #           levied it on every mission.  This module reads `payload_leo_kg`
    #           and `usd_per_kg_to_leo` and nothing else, so the vehicle is a
    #           LEO lifter and the stack departs on its own stage — no mission
    #           here is refuelled.  Gated behind `escape_direct_launch`, which
    #           nothing sets.  This is the one item that runs the other way, and
    #           it is currently inert because Starship is `development`.
    #         • `max_accel_g` WAS EXPORTED AND READ BY NOBODY.  Module 3 added
    #           it in v1.9.0 expressly to disqualify the kinetic launchers.
    #           Only maturity was excluding them; ungated, a 10,000 g slingshot
    #           at $6,250/kg wins on price and powders the rig.
    #           `max_payload_accel_g` = 15 g.
    #         New config: escape_direct_launch, max_payload_accel_g.
    #         New output column: tank_cost_usd.
    # 1.13.0 — POPULATION RELEASE.  No change to the mission model at all: not
    #         one term, coefficient or search axis moved, and a run over the
    #         same rows produces the same numbers.  What changed is how many
    #         rows arrive and which ones a cap keeps.
    #         • `eval_row_cap` DEFAULTS TO 0 (evaluate everything) instead of
    #           5,000.  Module 1 v1.1.0 can hand this module ~1.55 M asteroids
    #           and the old default discarded 99.7% of them behind a single
    #           line of stdout.  Every published figure in CLAUDE.md was
    #           measured with the cap explicitly set to 0 through the UI, so
    #           this makes the default agree with documented practice rather
    #           than changing what a documented run does.
    #         • CAPPED RUNS NOW SAMPLE, THEY DO NOT TRUNCATE.  The catalog
    #           arrives sorted by semi-major axis, so `.head(n)` returned the
    #           innermost n bodies — at 5,000 rows of a 1.55 M-row catalog,
    #           everything inside ~2.1 AU, with no outer belt, no Hildas, no
    #           Trojans and an S-complex-skewed spectral mix.  A "quick check
    #           before the full run" was therefore made on a population that
    #           does not resemble the full run.  `eval_row_sampling = "stride"`
    #           takes evenly-spaced rows across the whole catalog; "head"
    #           restores the old behaviour exactly.
    #           ⚠️  THIS CHANGES THE NUMBERS ANY CAPPED RUN PRODUCES.  It does
    #           not change an uncapped one, which is every figure on record.
    #         Stride is deterministic (np.linspace over positions, no RNG), so
    #         the serial/parallel byte-identity property of v1.10.1 survives.
    #         New config: eval_row_sampling.
    # 1.14.0 — realism audit.  Five findings, and the first three are all the
    #         same shape: a term that was WRITTEN DOWN as missing and then
    #         quoted as a known limitation until being written down was mistaken
    #         for being fixed.  Module 3 has carried every figure below since
    #         its v1.9.0, in STORAGE_REFERENCE, behind "⚠️  Not modelled in
    #         Module 4" — and Module 4 does not load storage_systems.csv, so the
    #         whole table was documentation.  They are moved to
    #         OPERATIONAL_COSTS, which this module does read, in Module 3 v1.11.0.
    #         All of them move the answer the same way: worse.
    #         • VOLATILE CARGO CONTAINMENT.  The pipeline sells water at every
    #           in-space destination and charged NOTHING to keep it from
    #           subliming across a multi-year cruise.  That is not a rounding
    #           term — the best cislunar missions run ~88% water by mass, so the
    #           commodity carrying the entire result was the one flying free.
    #           0.05 kg/kg of sealed shaded hold, INCREMENTAL to the 0.15 ore
    #           restraint, folded into `structure_frac` so the closed-form
    #           solver carries it with no change to its algebra, and settled at
    #           the payload actually flown rather than the loop's estimate.
    #         • THE SUN NEVER SET ON THE PROCESSING PLANT.
    #           `processing_power_w()` returns a CONTINUOUS average draw and the
    #           plant was sized straight off it, which is only right if the rig
    #           is never in shadow.  It stands on a rotating body.  Two terms:
    #           an array OVERSIZE of [(1−f) + f/η]/(1−f) = 2.11×, which is a
    #           sizing factor and therefore something no W/kg row could ever
    #           have absorbed however its notes were worded; and storage sized
    #           on the BODY'S OWN rotation period, which finally makes
    #           `rotation_period_h` — carried since Module 1 v1.0.0 and read by
    #           nothing — a quantity the model uses.  Both collapse exactly into
    #           an effective W/kg (see `eclipse_effective_w_per_kg`), so the RTG
    #           comparison is now decided on real plant mass and its crossover
    #           moves well inside 3.46 AU.  Exempt: radioisotope plants (flat
    #           output) and the EP array (permanent sunlight).
    #         • MARKET SATURATION COULD NOT SEE THE PROGRAMME.  Its own config
    #           comment says it exists because "the 'fly more missions' lever had
    #           no stopping point", and it never read
    #           `nre_amortization_missions` — that name appears in exactly four
    #           places and none of them was here.  A 100-mission programme
    #           divided its NRE by 100, grew its reliability, and sold 100
    #           payloads at the price one payload commands.  The rate is now the
    #           programme's concurrent output, ceil(N / missions_sharing_rig),
    #           derived from the rig service-life cap this module already
    #           computes.  Exactly 1 at N = 1, so no committed figure moves.
    #         • TPS was the one recurring article with no learning curve, while
    #           the capsule, power system, electric stage and tankage all carry
    #           one.  An ablative shield is the most literally per-mission
    #           article on the vehicle.
    #         • TPS was also missing from the INSURED book value.  v1.12.0 swept
    #           that list against the mass cascade and caught the plant, the
    #           electric stage and the tankage; TPS is billed from a different
    #           variable and was missed.
    #         Also: `schema_check` now checks Module 3 ROWS as well as columns.
    #         The ops table is row-keyed, so a missing figure was invisible to a
    #         column test — the exact hole CLAUDE.md names, and the one that
    #         cost a full measurement pass in v1.12.0.
    #         New config: model_eclipse_power, default_rotation_period_h,
    #         max_dark_period_h, model_volatile_containment.
    #         New output columns: solar_w_per_kg_bare, array_oversize_factor,
    #         dark_period_h, dark_period_clamped, rotation_period_h,
    #         cargo_water_kg, containment_frac, m_containment_kg,
    #         concurrent_missions.
    # 1.14.1 — PERFORMANCE ONLY.  NO NUMBER IN THIS MODULE'S OUTPUT CHANGES.
    #         Same contract as 1.10.1, and verified the same way rather than
    #         asserted: a pruned build and an unpruned one produce byte-
    #         identical CSVs, and the stamp moves only so that a CSV still names
    #         the code that produced it.  Do NOT re-measure the v1.14.0 tables
    #         on account of this version.
    #         • THE SEARCH SPENT ~85-94% OF ITSELF PROVING MISSIONS INFEASIBLE.
    #           Profiled at cislunar: of 134,538 calls to
    #           `_evaluate_combo_at_ratio` for 200 raw asteroids, 8,292 reached
    #           the cost model — 6.2%.  Beneficiated, 19,445 of 266,584 — 7.3%.
    #           The other 90-odd per cent paid ~20 us of prologue (eclipse,
    #           synodic period, ISRU chemistry, tankage, EP sizing) so that
    #           `max_return_payload_kg` could tell them what a dozen flops
    #           already knew.
    #         • THE FIXED POINT'S FIRST ITERATION IS ITS MOST OPTIMISTIC ONE,
    #           and it is closed form.  It runs at hardware = mining_hardware_kg
    #           (the plant and the electric stage are both still zero), at
    #           containment_frac = 0, and at the shortest stay the model allows.
    #           Every later pass only adds mass and lengthens the hold, both of
    #           which shrink the launch bracket.  So if pass 1 does not close,
    #           nothing downstream does.  `_combo_can_close` evaluates exactly
    #           that condition up front.
    #         • AND IT IS INDEPENDENT OF TWO AXES THE LOOP WAS RE-RUNNING IT
    #           FOR.  Pass 1 cannot see `power_mode` (no plant yet) or the
    #           concentration ratio (no feed yet), so a combo that could not
    #           close was being re-refuted once per power source and once per
    #           point of the concentration sweep — nine times over, which is
    #           why a dead candidate costs 305 us beneficiated against 32 us
    #           raw.  Hoisting the test above both loops kills the sweep whole.
    #         Measured at cislunar: 70.6% of raw (combo × dv × ISRU) tuples
    #         pruned and 69.5% of beneficiated ones, with ZERO of them
    #         producing a result when solved in full.
    #         • PER-BODY CONSTANTS WERE RE-DERIVED PER CANDIDATE.  The dark
    #           period, the eclipse-corrected specific power, the 1/r² solar
    #           figure, the synodic period, the mineable mass and the throughput
    #           cap are functions of (asteroid × config) and of nothing else,
    #           and all six were computed inside `_evaluate_combo_at_ratio` —
    #           38,643 times apiece for 200 asteroids, re-answering the same
    #           question about the same rock. `AsteroidContext` computes them
    #           once per body. Same shape and same justification as 1.10.1's
    #           ops-constant memo: the arithmetic is unchanged, the REPETITION
    #           was the cost.
    #         Measured against HEAD, same rows, serial: raw 7.86 s → 4.07 s
    #         (1.93x), beneficiated 28.07 s → 16.73 s (1.68x), every one of 124
    #         output columns identical and sha256 matching in both.
    #         New config: prune_infeasible_combos (default True — off restores
    #         the 1.14.0 search exactly, and is the diff to run if an output
    #         ever moves).
    #         New stdout line: the pruned-candidate count, so that a population
    #         where the pre-filter stops firing is visible rather than silent.
    # 1.14.2  PERFORMANCE ONLY — every number identical to 1.14.1, same contract
    #         as 1.10.1 and 1.14.1. The stamp moves so a CSV still names the code
    #         that produced it. DO NOT re-measure any table on account of it.
    #         Four findings, and the first is the largest single item ever found
    #         in this module:
    #         • SCALAR ARITHMETIC WAS GOING THROUGH NUMPY. `max_return_payload_kg`
    #           and `_combo_can_close` called `np.isfinite` and `np.exp` on
    #           Python floats. Measured here: np.isfinite 698 ns against
    #           math.isfinite 32 ns, float(np.exp(x)) 694 ns against math.exp
    #           47 ns — ufunc dispatch on a scalar, 15-22x. Seven of them per
    #           call to a function invoked 496,000 times per 150 beneficiated
    #           asteroids was about half that function and a quarter of the
    #           search. math.exp was checked BITWISE against np.exp over 400,000
    #           samples spanning this model's (Δv, Isp) range: zero mismatches.
    #         • THE KNAPSACK RE-SORTED THE SAME PHASE LIST ~2,100 times per
    #           asteroid. Memoised per list (`_PHASE_ORDER_CACHE`) rather than
    #           sorted at source — see the warning in `optimal_payload_mix`, the
    #           table's natural order is load-bearing on the last ULP.
    #         • SIX PER-PROPELLANT CONSTANTS AND ONE PER-VEHICLE were re-parsed
    #           per surviving candidate, each through `pd.isna` — ~980,000
    #           pd.isna calls per 150 rows. Attached to the row dict in
    #           `candidate_combos` like the pre-filter constants, so they cross
    #           the worker boundary too. `tank_frac` had been derived twice from
    #           the same two columns; one derivation now, two readers.
    #         • THE PRE-FILTER IS MONOTONE IN LAUNCH CAPACITY, so seventeen
    #           vehicles were re-deriving one propellant's exponentials, boil-off
    #           and tankage closure. Split into `_combo_close_terms` (no vehicle)
    #           and `_closes_with` (vehicle). The coefficients are hoisted rather
    #           than the threshold they imply, because rearranging `bracket > 0`
    #           re-associates the arithmetic and would move the prune boundary.
    #         Measured against HEAD, same rows, one process, serial: raw 2.70 s →
    #         1.13 s (2.39x), beneficiated 9.19 s → 4.51 s (2.04x), every one of
    #         124 output columns identical and sha256 matching in both.
    #         Measured and NOT taken: hoisting the ratio-independent prologue out
    #         of the concentration sweep. Instrumented at 7.6% of a beneficiated
    #         run, so ~6.7% recoverable — too little to justify splitting a
    #         570-line function with ~40 locals crossing the seam. Items above
    #         removed most of what made that prologue expensive.
    # 1.15.0 — PROGRAMME SCALE BECOMES A SEARCHED AXIS, and the rig finally wears
    #         out on something other than a calendar.  Paired with Module 3
    #         v1.12.0.  Two findings, and the first is a correction that runs the
    #         usual direction (worse) while the second is an optimisation that
    #         can only run the other way.
    #         • THE RIG HAD NO CYCLE LIMIT.  `missions_sharing_rig` was
    #           min(N, life_yr // stay_yr) and `life_yr` is a CALENDAR figure —
    #           15 years of "will not have corroded meanwhile".  At the ~1.25 yr
    #           stay the winning cislunar mission actually flies that made one rig
    #           good for 12 consecutive campaigns, on the strength of a number
    #           that never claimed to bound duty cycles.  Calendar time is not
    #           what wears out a machine that cuts rock.  Module 3's new "Mining
    #           rig maximum trips" (5, range 2-12) is the other bound, and
    #           `rig_trips_per_ship` takes the MIN of the two — so a long-stay
    #           mission is still calendar-limited and a short-stay one is now
    #           cycle-limited, which is the correct way round.
    #           Gated by `model_rig_trip_limit` (default True); False restores
    #           1.14.2 exactly.
    #         • PROGRAMME SIZE WAS AN INPUT TO A MODEL THAT KNOWS WHAT IT COSTS.
    #           v1.14.0 made market saturation see `nre_amortization_missions`
    #           and thereby made the programme-scale curve TURN — the optimum N
    #           became interior.  Nothing then searched for it: N stayed a config
    #           field and the curve was mapped by re-running the whole pipeline at
    #           N = 1, 10, 100.  Three points do not locate an optimum, and this
    #           file's own tables say so.
    #           `optimise_programme_scale` (default False) searches it instead,
    #           jointly with every other architecture axis.  Two structural facts
    #           make that nearly free rather than |N| times the work:
    #             1. N ENTERS NOTHING IN THE MASS CASCADE.  It appears in
    #                `mission_cost_usd`, the saturation block and the reliability
    #                block, and nowhere else — so the rocket equation, the fixed
    #                point, the knapsack and the concentration sweep are all
    #                solved ONCE per candidate and the whole programme ladder is
    #                priced off the result.
    #             2. THE OPTIMUM N IS ALWAYS AN EXACT MULTIPLE OF trips_per_ship.
    #                Within one fleet band the concurrent output — and therefore
    #                the saturation multiplier — is constant, while NRE/N, the
    #                learning curve, the rig share and p_mining all improve
    #                strictly with N.  So the best N in the band is its top, N =
    #                F × trips.  The search is therefore over the FLEET, F, and N
    #                follows; every N that cannot be optimal is skipped without
    #                being evaluated.  See `programme_options`.
    #           Which also answers the user-facing question directly: the number
    #           of ships in the fleet IS the decision variable, and programme size
    #           is its consequence.
    #         MEASURED, full 1,554,353-row catalog, cislunar, raw, 12 workers,
    #         both cells in one process (2026-08-11), 650,516 evaluable each:
    #           search OFF  26.7863x  1,306 s   2021 CX5, New Glenn, xenon,  N=1
    #           search ON   14.1730x  1,978 s   2021 CX5, New Glenn, iodine, N=5
    #         Never-worse on the whole population: 650,516 pairs, 0 worse,
    #         650,515 improved, median improvement 45.3%.  N = F x trips on every
    #         row.  Fleet median 2, max 64; 2,393 rows (0.37%) sit AT
    #         max_fleet_ships and are flagged on stdout — those are bodies with no
    #         finite market, where the objective is monotone and the ladder's top
    #         rung is where the loop stopped rather than an optimum.
    #         The OFF cell REPRODUCES the committed 1.14.0 figures exactly — ratio,
    #         evaluable rows, winner, vehicle, propellant, payload to the kg,
    #         saturation multiplier, p_mining, RTG share and the propellant split —
    #         so 1.14.1's and 1.14.2's bit-identity claims and this release's
    #         inertness at N = 1 all now hold on 1.55 M bodies at once, rather than
    #         on the 150-2,500-row samples each was argued from.
    #         ⚠️  The search costs 1.51x runtime, NOT the 1.04-1.13x a 2,500-row
    #         sample showed.  Third time a stride sample has mispredicted
    #         full-catalog runtime here, and the first time it did so for a RATIO
    #         between two settings rather than an absolute wall clock — the ladder
    #         is priced per SURVIVING candidate, and the sample's survivors are not
    #         the population's.
    #         New config: model_rig_trip_limit, optimise_programme_scale,
    #         max_fleet_ships, programme_search_steps.
    #         New output columns: programme_missions, fleet_ships, trips_per_ship,
    #         rig_trips_calendar_cap, rig_trip_limit_binds,
    #         programme_options_priced.
    # v1.16.0 PROGRAMME CALENDAR TIME.  A programme took years and was charged for
    #         none of them, and that was the last item this module's own config
    #         comment named as an open gap.
    #         • THE AMORTISED LINES WERE CARRIED FOR FREE.  WACC compounds each
    #           mission's up-front costs over `mission_duration_yr` — right for one
    #           mission, wrong for a programme.  The bus NRE, the autonomy NRE and
    #           the rig are bought ONCE at t = 0 and amortised across W campaigns
    #           that one rig can only fly one after another, so they are carried
    #           across `T + (W-1) x cadence` of calendar and were compounded over
    #           `T`.  `programme_calendar_multipliers` charges the difference as a
    #           closed-form mean over the programme, exactly 1.0 at W = 1.
    #           Terminal value gets the RECIPROCAL series, because salvage is
    #           collected at the END: compounding a refund forward alongside the
    #           cost it is netted against would pay a bonus for taking longer to
    #           collect it.
    #         • CADENCE IS THE DIG, OR THE WINDOW, WHICHEVER IS SLOWER.  Successive
    #           campaigns on one rig are paced by the stay — but a capsule can only
    #           be dispatched when a window opens, so `campaign_cadence_yr` takes
    #           the max of the stay and the synodic period.  That lands hardest on
    #           NEAs, whose synodic periods run to a decade, and they are what this
    #           model likes.  A single mission pays that wait once; a programme of
    #           W pays it W-1 more times.
    #         • THE BAND ARGUMENT IS RETIRED AND THE SEARCH IS 2-D.  v1.15.0 could
    #           search fleet size alone because within a band every lever improved
    #           with N and none pushed back.  The calendar charge is the lever that
    #           pushes back — it grows like y^W against NRE/N falling like 1/N — so
    #           campaigns-per-ship is now a real decision with an interior optimum.
    #           F stays a ladder; W is ENUMERATED EXHAUSTIVELY, because it is at
    #           most `max_trips` integers and a dimension small enough to enumerate
    #           should not be argued about.  N = 1 is consequently IN the search
    #           set rather than dominated by it.
    #         • `missions_sharing_rig` is derived from the fleet, min(trips,
    #           ceil(N/F)), rather than min(N, trips) — which claimed 5 campaigns
    #           on a rig that flies 4 whenever N was not a whole multiple.
    #         Gated by `model_programme_calendar` (default True); False restores
    #         1.15.0 exactly, in all four respects.
    #         ⚠️  INERT AT W = 1, hence at N = 1, hence on every committed cell in
    #         CLAUDE.md and the README except the N = 10 / N = 100 curve, which is
    #         a 1.14.0 measurement and moves.
    #         New config: model_programme_calendar.
    #         New output columns: missions_per_ship, campaign_cadence_yr,
    #         cadence_window_bound, programme_span_yr,
    #         programme_calendar_multiplier.
    # v1.17.0 DEFAULTS: BENEFICIATION ON, PROGRAMME SEARCH ON.  No model term,
    #         coefficient, table value or search axis moved.  An explicitly
    #         configured run produces bit-identical output to 1.16.0; what moves
    #         is what you get when you configure NOTHING, which is the whole
    #         point of the bump — the rule in CLAUDE.md is that changing any
    #         number a run produces means bumping, and the default run's numbers
    #         change.  Same contract as 1.10.1 / 1.14.1 / 1.14.2 (a stamp that
    #         does not mean the model moved), for a different reason: those were
    #         performance, this is configuration.
    #         • `use_beneficiation` False -> True.  Weakly dominant by
    #           construction — the search always also prices `beneficiate=False`
    #           — so this cannot make any row's objective worse.  Verified on
    #           the full catalog: 650,921 cislunar pairs, max benef/raw
    #           1.000000, zero exceptions, 15.79% declining at exactly 1.0.
    #           Costs 7.1x runtime (1,307 s -> 9,300 s raw -> beneficiated).
    #         • `optimise_programme_scale` False -> True.  NOT weakly dominant
    #           in the same sense — it is a change of QUESTION, from the best
    #           single mission to the best programme — but never-worse against
    #           N = 1 holds by construction since v1.16.0 put (F, W) = (1, 1) in
    #           the search set.  Verified: 650,921 pairs, max searched/unsearched
    #           1.000000, zero worse, median improvement 42.4%.
    #           Costs 2.98x runtime (1,307 s -> 3,890 s).
    #         ⚠️  A DEFAULT RUN NO LONGER REPRODUCES THE OLDER TABLES, because
    #         almost all of them are N = 1 raw.  Both flags restore them, and
    #         both OFF cells were re-measured on the full catalog on 2026-08-11
    #         and reproduce EXACTLY: 26.7863x raw (unmoved across 1.14.0 ->
    #         1.16.0) and 20.5895x beneficiated.  Nothing was retired; the
    #         defaults just stopped answering the smallest question by default.
    #
    # 1.17.1  PERFORMANCE ONLY — every number identical, the stamp moves only so
    #         that a CSV still names the code that produced it.  FOURTH such
    #         stamp after 1.10.1 / 1.14.1 / 1.14.2, and the first aimed at the
    #         COST cascade rather than the mass cascade — because v1.17.0 made
    #         `optimise_programme_scale` a default, and the programme ladder
    #         prices a median of 40 options per candidate mission, so every
    #         per-call cost in `mission_cost_usd` is now multiplied by 40.
    #         Measured (interleaved A/B, both builds in one process, best of 5,
    #         cislunar stride samples):
    #             raw, search off            1.04x
    #             beneficiated, search off   1.29x
    #             raw, search on             1.25x
    #             beneficiated + search      1.35x   <- the v1.17.0 DEFAULT
    #         • `_ops_cost_constants` — the 22 Module 3 rows the cost cascade
    #           reads, memoised on `ops_df` identity exactly as v1.10.1 did for
    #           the sizing loop.  `_ops_value` was running 8.06 MILLION times on
    #           a 150-row beneficiated+search sample, 11.7% of the profile, to
    #           re-read numbers that never move.  `rig_trips_per_ship` reads the
    #           same tuple.
    #         • `optimal_payload_mix(want_phase=...)` — `_cargo_water_kg` is
    #           97.3% of that function's callers and reads ONE key of the mix,
    #           so it was building the mix dict, the value sum and the
    #           dominant-phase max() and discarding all three.
    #         • `AsteroidContext.cargo_ice_frac` — a per-BODY quantity that the
    #           raw arm of `_cargo_water_kg` was re-deriving (`.get` + `pd.isna`
    #           + `float`) per candidate per pass of the sizing loop.
    #         • `mission_cost_usd(totals_only=True)` — the ladder compares
    #           options on `total_cost` alone; building a 40-key dict to discard
    #           39 of them measures ~3.4 us a call.  Early return before the
    #           dict, winner re-priced once in full.
    #         • `rig_trips` passed into `mission_cost_usd` — it is
    #           (ops_df, config, stay_yr), all three fixed across a ladder.
    #         • `delivery_architecture` memoised on its raw argument (458,337
    #           calls to normalise one string).  Warning path deliberately not
    #           memoised, so an unknown destination still shouts every time.
    #         Verified: four cells (raw / benef / raw+search / benef+search)
    #         135/135 columns bit-identical with sha256 MATCH against HEAD;
    #         serial vs 8 workers byte-identical on benef+search (1,500-row
    #         stride) and raw+search (2,500-row stride); mass ledger exact at
    #         0.000000000 kg on three cells; both never-worse invariants hold
    #         (max 1.000000, zero exceptions).
    #
    # 1.17.2  PERFORMANCE ONLY — every number identical.  FIFTH such stamp after
    #         1.10.1 / 1.14.1 / 1.14.2 / 1.17.1, and the second in a row aimed
    #         at the programme ladder, because that is where v1.17.0's default
    #         flip put the work.  Measured (interleaved A/B, both builds in one
    #         process, best of 7, cislunar stride samples, TWO independent
    #         passes which agreed to within 0.02x on every cell):
    #             raw, search off            1.01x / 0.99x
    #             beneficiated, search off   1.02x / 1.00x
    #             raw, search on             1.46x / 1.45x
    #             beneficiated + search      1.35x / 1.37x  <- v1.17.0's DEFAULT
    #         ⚠️  Two passes, because ONE is not a measurement on this host: a
    #         best-of-5 pass taken while the machine was loaded put the inert
    #         "beneficiated, search off" cell at 1.19x, and HEAD's own absolute
    #         times moved 30-45% between passes.  The RATIOS on the searched
    #         cells held across all of it; the inert cells did not, and would
    #         have been reported as a gain from a single pass.
    #         ⚠️  Note the SHAPE of that table, which is the release in one
    #         picture and is the opposite of 1.17.1's: the two search-off cells
    #         are inert to within noise, because both items remove work that
    #         only exists when a LADDER exists.  A run with
    #         `optimise_programme_scale` off gains nothing here and should not
    #         be expected to.
    #         • `mission_cost_usd` SPLIT into `_mission_cost_prologue` (the ~90%
    #           that does not move with programme size) and `_mission_cost_tail`
    #           (the ~30 arithmetic ops that do).  The ladder builds the
    #           prologue once and calls the tail per option, instead of
    #           re-deriving ~10 max() calls, ~6 dict lookups, ~15 float()
    #           conversions, a `delivery_architecture` call and a 22-tuple
    #           unpack forty times over to change three numbers.
    #           🚨  v1.17.1's "what this release does NOT close" section named
    #           this and REFUSED it, on the grounds that it "re-associates the
    #           final sums" and so would cost the bit-identity every release
    #           here is argued from.  The premise is right and the conclusion
    #           does not follow: every N-dependent line factors as
    #           `<N-independent base> * lc`, and `a * b * lc` is ALREADY
    #           evaluated as `(a * b) * lc`, so hoisting `a * b` is the same two
    #           operations in the same order rather than an algebraic
    #           rearrangement.  What genuinely cannot be hoisted is a partial
    #           SUM interleaved with N-dependent terms, and `hardware_cost`,
    #           `spacecraft_book_value` and `upfront_lines` are therefore
    #           restated verbatim in the tail.  The distinction is the whole
    #           release; see `_mission_cost_prologue`'s docstring.
    #         • The market-saturation sum memoised per FLEET inside
    #           `_price_programme`.  It reads F and nothing else the ladder
    #           varies, and the ladder is the F ladder crossed with W — so ~40
    #           options over ~8 distinct fleets re-derived the same sum five
    #           times each.  Bit-identical by construction: the same F re-runs
    #           the same `+=` over the same list in the same order.
    #         • `max(1, missions_sharing_rig)` computed once instead of three
    #           times in the tail.
    #         Verified: four cells (raw / benef / raw+search / benef+search)
    #         135/135 columns bit-identical with sha256 MATCH against HEAD;
    #         serial vs 8 workers byte-identical on benef+search and raw+search;
    #         mass ledger exact at 0.000000000 kg; both never-worse invariants
    #         hold (max 1.000000, zero exceptions).
    #
    # 1.17.3  DEAD CODE AND DUPLICATION REMOVED — every number identical.  SIXTH
    #         stamp that does not mean the numbers moved, and the first for
    #         neither performance nor a default flip: nothing here is meant to
    #         make the module faster, only smaller and harder to drift.
    #         • `low_thrust_burn_time_yr` DELETED — no caller in four releases.
    #           It is the t-form of `ep_power_required_w`, and this model always
    #           picks a trip time and buys the array rather than the reverse.
    #           ⚠️  Its section comment carries the DAWN VALIDATION (5.0-9.3 yr
    #           predicted at 2.2-3.0 AU against ~5.9 yr flown, and 1.0 yr if the
    #           1/r² term is lost), which is load-bearing and was KEPT, re-
    #           anchored on `ep_power_required_w`.  Do not delete that comment
    #           on the grounds that the function it sat above is gone.
    #         • `asteroid_dv_m_s` DELETED — no caller.  Its docstring claimed it
    #           was kept "for interactive use", and nothing advertised it, which
    #           is the opposite of `cheapest_launch_to` in Module 3 (dead to the
    #           pipeline, but named in that module's own preview output).
    #         • `_tank_frac_per_kg` — ONE derivation of tank mass per kg, read by
    #           `_sizing_propellant_consts` and `_prefilter_propellant_consts`.
    #           🚨  v1.14.2 claimed to have closed this ("one derivation now, two
    #           readers") and had in fact MOVED the second copy, which still
    #           divided the same two columns ten lines away under a comment
    #           saying it matched the first "exactly".  A note that documented an
    #           intention as an accomplishment, and it survived a release argued
    #           entirely from bit-identity because nothing a hash can see was
    #           wrong.
    #         • `_phase_prices` / `_pgm_enrichment` — the walk of
    #           FRACTION_TO_MINERAL existed THREE times.  The two byte-identical
    #           copies (`asteroid_phase_table`, `asteroid_best_phase_usd_per_kg`)
    #           are now one generator.  ⚠️  `asteroid_bulk_value_usd_per_kg` is
    #           deliberately NOT folded in: it admits a fraction of exactly 0.0
    #           where the others skip it, and unifying it would be numerically
    #           negligible and would still cost the bit-identity this project
    #           argues from — the v1.14.2 phase-sort lesson.
    #         • Five slots of the `ctx.ops` unpack in `_evaluate_combo_at_ratio`
    #           `_`-prefixed.  They are dead HERE only — the tuple's ORDER is the
    #           contract with `_ops_sizing_constants`, so they must still be
    #           unpacked, and v1.14.1 moved the arithmetic that read them onto
    #           `AsteroidContext` because it is per-body.
    #         Verified: four cells (raw / benef / raw+search / benef+search)
    #         139/139 columns bit-identical with sha256 MATCH against 1.17.2,
    #         less the two PROVENANCE columns; serial vs 8 workers byte-identical
    #         on raw+search and benef+search; mass ledger exact at
    #         0.000000000 kg; both never-worse invariants hold.
    #         🚨  Those provenance columns are `pipeline_version` AND
    #         `catalog_date`, and the second one is not obvious.  An earlier
    #         pass dropped only the version and reported the two BENEFICIATED
    #         cells as differing; the entire difference was `catalog_date`,
    #         because midnight fell between the raw cells and the beneficiated
    #         ones.  Half a run dated 08-12 and half 08-13 looks precisely like
    #         a real defect confined to the beneficiation path.  A full
    #         beneficiated cell is ~10 h, so a 2x2 CANNOT be run inside one
    #         date: strip every provenance column before hashing.
    pipeline_version: str = "1.17.3"


CALC_CONFIG = CalcConfig()
os.makedirs(CALC_CONFIG.output_dir, exist_ok=True)

print(f"✅  Configuration loaded — output dir: {CALC_CONFIG.output_dir}")
print(f"    Hardware       : {CALC_CONFIG.mining_hardware_kg:,.0f} kg mining rig "
      f"+ {CALC_CONFIG.return_vehicle_dry_kg:,.0f} kg return-capsule dry")
print(f"    Mining cap     : {CALC_CONFIG.max_mining_fraction:.0%} of asteroid mass per mission")
# Default ON as of v1.17.0 and worth ~7x the runtime of a raw pass, so say so
# up front rather than leaving a two-and-a-half-hour run unexplained.
print(f"    Beneficiation  : "
      + ("concentrate (search also prices not concentrating at all)"
         if CALC_CONFIG.use_beneficiation else
         "off — run-of-mine ore at bulk grade"))
print(f"    Return mode    : "
      f"{'aerocapture available (per-asteroid Δv saving vs TPS mass)' if CALC_CONFIG.use_aerocapture_return else 'propulsive only'}")
print(f"    ISRU           : {'available where the rock has water' if CALC_CONFIG.use_isru_return_propellant else 'off'}")
print(f"    Architecture   : "
      f"{'searched per asteroid' if CALC_CONFIG.optimise_architecture_per_asteroid else 'fixed by config'}")
print(f"    Contingency    : {CALC_CONFIG.contingency_fraction:.0%}  |  "
      f"NRE amortised over {CALC_CONFIG.nre_amortization_missions} mission(s)")
print(f"    Programme      : "
      + (f"(fleet ≤ {CALC_CONFIG.max_fleet_ships}) × (campaigns/ship) searched; N follows"
         if CALC_CONFIG.optimise_programme_scale else
         f"fixed at N = {CALC_CONFIG.nre_amortization_missions} "
         f"(set optimise_programme_scale to search it)"))
print(f"    Calendar       : "
      + ("programme span charged — amortised NRE and rig compound over "
         "T + (W−1)×cadence" if CALC_CONFIG.model_programme_calendar else
         "NOT charged (model_programme_calendar off — reproduces 1.15.0)"))


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

    schema_check(catalogs)


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
# missing ROW and `schema_check` above — which tests columns — cannot see it.
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

    Stage 3 is the cheap stage, so it is the one people skip re-running — and
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
    print(f"\n     ⚠️  Module 3 catalog is STALE — {len(stale)} column(s)/row(s) "
          f"this version reads are missing:")
    for key, col, consequence in stale:
        print(f"          • {key}.{col}  →  {consequence}")
    print("        → Re-run Stage 3 (transportation).  It takes seconds, and "
          "until you do, the numbers below are not comparable to any "
          "committed figure.")


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
    with no fraction or no price are skipped — you cannot select what is not
    there.

    ⚠️  `asteroid_bulk_value_usd_per_kg` deliberately does NOT use this: it
    admits a fraction of exactly 0.0 where this skips it.  Unifying the third
    copy would be numerically negligible and would still cost the bit-identity
    every release here is argued from — see the v1.14.2 phase-sort warning.
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

    # Residual "other" mass — value at silicate floor so it doesn't vanish.
    if 0.0 < frac_sum < 1.0:
        other_frac     = 1.0 - frac_sum
        silicate_price = _mineral_price(mineral_df, "silicates") or 0.05
        total += other_frac * float(silicate_price)

    return total


def asteroid_phase_table(
    asteroid_row: Row, mineral_df: pd.DataFrame,
) -> List[Tuple[str, float, float]]:
    """[(phase, mass_fraction, usd_per_kg)] for one asteroid (v1.6.0).

    The same four taxonomy fractions `asteroid_bulk_value_usd_per_kg` blends,
    but kept SEPARATE so a mission can choose what to load rather than being
    handed the mean.  The residual (Module 1's fractions sum to 0.76-0.96) is
    included as bulk silicate, matching the bulk function's floor treatment.

    Phases with zero fraction are dropped — you cannot select what is not
    there.
    """
    phases: List[Tuple[str, float, float]] = []
    frac_sum = 0.0
    for mineral_name, frac, price in _phase_prices(asteroid_row, mineral_df):
        phases.append((mineral_name, frac, price))
        frac_sum += frac

    if 0.0 < frac_sum < 1.0:
        silicate_price = _mineral_price(mineral_df, "silicates") or 0.05
        phases.append(("other (bulk silicate)", 1.0 - frac_sum, float(silicate_price)))

    return phases


def saturation_price_multiplier(
    delivered_kg_per_yr: float,
    annual_market_kg:    float,
    elasticity:          float,
) -> float:
    """Price multiplier when a mission's output is material next to the market.

        P / P0 = (1 + Q_new / Q_market) ^ (−1/ε)

    Constant-elasticity demand.  Precious-metal demand is inelastic —
    ε ≈ 0.5 — so doubling world supply quarters the price, which is why
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


# Single-slot memo for the knapsack's price ordering (v1.14.2).  The phase table
# is built once per asteroid and never mutated, but `optimal_payload_mix` is
# called ~2,100 times per asteroid in a beneficiated run and re-sorted it every
# time — 325,000 `sorted()` calls plus 1.4 million key-lambda calls per 150
# rows, all re-deriving the same order for the same rock.
#
# Same shape and the same justification as `_OPS_CACHE` below: keyed by object
# identity, with the list itself held in the slot so its id cannot be recycled
# onto a different object, and single-slot rather than a growing dict so a
# long-lived session cannot leak.  A caller that mutates a phase list IN PLACE
# rather than rebinding would read a stale order — nothing in this module does,
# and `asteroid_phase_table` returns a fresh list per asteroid.
#
# ⚠️  What this deliberately does NOT do is sort the phase table at source.  See
# the warning in `optimal_payload_mix` — the table's natural order is
# load-bearing elsewhere, on the last ULP.
_PHASE_ORDER_CACHE: Tuple[Optional[List[Tuple[str, float, float]]],
                          List[Tuple[str, float, float]]] = (None, [])


def optimal_payload_mix(
    payload_kg: float,
    feed_kg:    float,
    phases:     List[Tuple[str, float, float]],
    recovery:   float,
    want_phase: Optional[str] = None,
) -> Union[Dict[str, object], float]:
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
    every verification this project relies on is a bit-identity check — the
    sha256 CSV diffs, `max |error| 0.000000000 kg`, "124 of 124 columns
    identical".  A sort at source reads like a free cleanup and silently costs
    you the ability to prove a release changed nothing.

    So the ordering is memoised per phase list instead, which leaves the table
    itself untouched.

    ── `want_phase` (v1.17.1) ───────────────────────────────────────────────
    Returns the kilograms of ONE named phase that the greedy walk loads, as a
    bare float, instead of the full result dict.  `_cargo_water_kg` is 97% of
    this function's callers and reads exactly one key — `mix_kg["water"]` —
    so it was paying for the mix dict, the value accumulation and the
    dominant-phase `max()` over `mix.items()` on every call, then throwing all
    three away.

    It is a short circuit, NOT a second knapsack: the walk below is the only
    statement of the greedy algebra in this module, and `want_phase` only
    decides how much of each pass's result is kept and when to stop.  Writing
    it as a separate water-only function would have been the "two copies of
    this algebra drifting apart" hazard that the mass ledger warns about, for
    no extra speed — the loop is not what costs, the bookkeeping is.

    The answer is bit-identical by construction rather than by measurement:
    `remaining` is decremented in the same order by the same `min`, and the
    take for the requested phase is returned before anything downstream of it
    could perturb it.  Verified anyway — see the release notes.
    """
    if payload_kg <= 0 or not phases:
        return 0.0 if want_phase is not None else {
            "value_usd": 0.0, "usd_per_kg": 0.0, "mix_kg": {},
            "dominant_phase": None, "dominant_frac": 0.0}

    global _PHASE_ORDER_CACHE
    if _PHASE_ORDER_CACHE[0] is not phases:
        _PHASE_ORDER_CACHE = (phases, sorted(phases, key=lambda p: -p[2]))
    by_price = _PHASE_ORDER_CACHE[1]

    remaining = float(payload_kg)
    total     = 0.0
    mix: Dict[str, float] = {}
    for name, frac, price in by_price:
        if remaining <= 0:
            break
        available = float(feed_kg) * frac * recovery
        take      = min(available, remaining)
        if take <= 0:
            continue
        if want_phase is not None:
            # The caller wants one number.  Stop as soon as it is known —
            # nothing after this point in the walk can change it.
            if name == want_phase:
                return take
            remaining -= take
            continue
        mix[name]  = take
        total     += take * price
        remaining -= take

    if want_phase is not None:
        # Never reached in the walk: the hold filled before this phase came up,
        # or the feed had none of it.  `mix_kg.get(want_phase, 0.0)` in the full
        # path returns the same 0.0, including when `loaded <= 0` below would
        # have short-circuited to an empty mix.
        return 0.0

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
    asteroid_row: Row, mineral_df: pd.DataFrame,
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
    best = 0.0
    for _mineral_name, _frac, price in _phase_prices(asteroid_row, mineral_df):
        if price > best:
            best = price

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


# ─────────────────────────────────────────────────────────────────────────────
# POWER SOURCE SELECTION  (v1.11.0)
# ─────────────────────────────────────────────────────────────────────────────
# Module 3 has carried an "RTG (radioisotope power)" row since v1.2.0 — $500k
# per Watt-electric, with a note reading "only used past ~3 AU when PV starves"
# — and nothing in this module ever read it.  Every asteroid in the catalog
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
# radioisotope — and a meaningful slice of this catalog is outside it.
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
# anything a radioisotope source can deliver — pricing that as an RTG would
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

    v1.14.0 — takes the solar figure ALREADY RESOLVED rather than deriving it
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
# `processing_power_w()` returns a CONTINUOUS average draw — energy divided by
# the time available — and the plant was sized straight off it.  That is only
# correct if the sun never sets.  It does: the rig stands on a rotating body,
# roughly half its sky is the ground, and asteroid rotation periods run hours.
#
# Module 3 has carried the 0.50 dark fraction in STORAGE_REFERENCE since v1.9.0
# with "⚠️  Not modelled" written on it, and the note was quoted as a known
# limitation for two releases while nothing consumed it — because Module 4
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
#   a slow rotator is genuinely a worse place to mine — a fact the model had no
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

    Bodies with no measured rotation — about two thirds of the catalog — take
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
    # lossy.  Exactly 1.0 at f = 0 — the permanent-sunlight case a free-flying
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
# error left in the model, and it was load-bearing — the best Mars mission in
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
# its 11-year mission.  The 1/r² term is doing the work here — evaluated at
# the 1 AU array rating instead, the same sum gives 1.0 year and is nonsense.
#
# Run that check off `ep_power_required_w` below — the same relation solved for
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
    noticing that it owes nothing to efficiency — thrust is momentum flux, so
    T = m_prop·ve/t exactly.  Efficiency only decides how much electrical power
    you must supply to get it, which is why the two constraints are separate
    and why sizing on power alone missed one of them entirely.

    Until v1.12.0 nothing computed this. The EP stage was sized on power, and
    power buys thrust at a rate the rocket equation was happy to assume any
    device could deliver — so the search flew pulsed plasma thrusters and
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
# phase drifts slowly and windows are years apart — a body at a = 1.13 AU
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

    Energy is charged on the two Module 3 rates — excavation per kg of
    regolith MOVED, beneficiation per kg of product OUT — and divided by the
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
    needed in two places — inside the sizing loop, where it sets how much array
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
      reads rather than building the whole mix and discarding it — see
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
# The validation table lives on asteroid_transfer_dv_km_s.  In summary: within
# ~10% of both Module 3's reference table and published mission values, which is
# the accuracy an analytic estimator can honestly claim.  It runs slightly LOW
# against published figures for the easiest co-orbital targets, where real
# mission design finds better transfers than a two-impulse apsis match.
# The floor is the physical one: escaping LEO costs √2·v_LEO − v_LEO ≈
# 3.22 km/s no matter how accessible the target is.
#
# v1.10.0: WHICH apsis to meet the target at is now searched rather than picked
# by rule, and the search is resolved against the destination being flown — see
# asteroid_transfer_options_km_s and asteroid_dv_options.

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
        "r_rendezvous_au":        r_target,
        "ret_earth_surface_aero": dv_match,
        # v1.10.0: capture into LEO and then LAND is not the same manoeuvre as
        # capture into LEO and stay there — the capsule still has to come down.
        # The docstring claimed the deorbit burn all along; it was never added.
        "ret_earth_surface_prop": dv_match + dv_leo_capture + DV_LEO_DEORBIT_KM_S,
        "ret_leo_prop":           dv_match + dv_leo_capture,
        "ret_leo_aero":           dv_match + DV_AEROBRAKE_TRIM_KM_S,
        "ret_cislunar_prop":      dv_match + dv_cislunar,
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


def asteroid_transfer_options_km_s(
    a_au: float, e: float, i_deg: float,
) -> List[Dict[str, float]]:
    """Every rendezvous geometry worth pricing for one asteroid (v1.10.0).

    A two-impulse transfer can meet the target at either apsis, and which one
    is cheaper is a property of the individual orbit — not something a rule can
    settle in advance.  Until v1.10.0 the estimator applied one:

        r_target = aphelion if aphelion >= 1 AU else perihelion

    which is right for most main-belt bodies and demonstrably wrong for others.
    The trade is between two terms that move in opposite directions.  Meeting a
    body at aphelion means a long, slow transfer whose arrival speed nearly
    matches the target's — cheap rendezvous, expensive departure.  Meeting it at
    perihelion means a short transfer, but both bodies are moving fast there and
    the match burn is large.  Which term dominates depends on a and e together,
    so it has to be evaluated, not assumed.

    Returns one full leg dict per feasible apsis, each tagged with
    `rendezvous_apsis` and `r_rendezvous_au`.  Callers pick — and because the
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
            break                      # circular orbit — the apsides coincide
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
        ret_earth_surface_aero  direct entry — no capture burn at all
        ret_earth_surface_prop  propulsive capture into LEO, then deorbit
        ret_leo_prop            propulsive capture into LEO
        ret_leo_aero            aerocapture + aerobraking, trim burn only
        ret_cislunar_prop       Oberth capture + NRHO insertion

    v1.5.0 — was a 3-tuple (out, return_propulsive, return_aerocapture) when
    Earth's surface was the only destination the pipeline could model.

    v1.10.0 — the rendezvous apsis is now searched (see
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
    unchanged by the apsis search — it only moves bodies the old rule got wrong.
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


_ARCH_BY_RAW_KEY: Dict[Any, dict] = {}


def delivery_architecture(destination: str) -> dict:
    """Look up the mission architecture for a delivery destination.

    Unknown destinations fall back to earth_surface — the conservative
    choice, and the one whose cost lines are all present.

    v1.17.1: the resolved answer is memoised on the RAW argument, because
    `mission_cost_usd` calls this once per programme option — 458,337 times on
    a 150-row beneficiated sample with the search on — to normalise the same
    string and index the same dict.  Only the hit path is memoised: an unknown
    destination still falls through and still prints its warning every time,
    which is the loud behaviour that made it a warning.
    """
    try:
        hit = _ARCH_BY_RAW_KEY.get(destination)
    except TypeError:
        hit = None                    # unhashable caller — skip the memo
    if hit is not None:
        return hit

    key = str(destination or "").strip().lower()
    if key not in DELIVERY_ARCHITECTURES:
        print(f"     ⚠️   Unknown delivery_destination {destination!r} — "
              f"falling back to 'earth_surface'.  Valid: "
              f"{', '.join(sorted(DELIVERY_ARCHITECTURES))}")
        return DELIVERY_ARCHITECTURES["earth_surface"]

    arch = DELIVERY_ARCHITECTURES[key]
    try:
        _ARCH_BY_RAW_KEY[destination] = arch
    except TypeError:
        pass
    return arch


def uses_tps(config: CalcConfig) -> bool:
    """True when this architecture CAN fly a heat shield.

    Aerocapture is a request, not a guarantee: a cislunar delivery never
    touches the atmosphere, so asking for aerocapture there gets you a
    propulsive capture and no TPS mass.

    v1.10.0: this answers "is aerocapture on the menu", not "is it flown".
    Whether it actually pays is decided per asteroid — see
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
    and the propellant — both of which the model has always picked per asteroid.

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
# ISRU RETURN PROPELLANT  (v1.10.0 — made physical, and made per-asteroid)
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
#      mining and baking MORE rock — that is the whole cost of ISRU, and it was
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
# The surplus oxygen (8/7 produced against 6/7 burnt) is vented — a real depot
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
# Which of those wins is a real trade and it varies by body — a wet, easily
# reached target favours cheap propellant, a dry or distant one favours high
# Isp — so it belongs in the per-asteroid architecture search, not in a
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


def isru_feed_kg_per_kg_propellant(
    asteroid_row: Row, propellant: Row, config: CalcConfig,
) -> Optional[float]:
    """kg of regolith to dig per kg of ISRU return propellant, or None.

    None means this mission cannot make its own propellant — either the
    propellant is not manufacturable from asteroid material, or this body has
    no water to make it from.  That is a per-(asteroid × propellant) fact, which
    is why it is answered here rather than by a config flag.
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

    if material == "regolith":
        # Reaction mass is the body itself; no volatiles needed and no
        # separation loss, because nothing is being separated.
        return ratio

    if material != "water":
        return None

    ice_frac = asteroid_row.get("comp_ice_fraction")
    if ice_frac is None or pd.isna(ice_frac) or float(ice_frac) <= 0.0:
        return None

    recovery = max(1e-6, min(1.0, config.beneficiation_recovery))
    return ratio / (float(ice_frac) * recovery)


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
# CANDIDATE PRE-FILTER  (v1.14.1)
# ─────────────────────────────────────────────────────────────────────────────
# The search was spending ~90% of itself proving missions infeasible, and paying
# the full ~20 us prologue of `_evaluate_combo_at_ratio` — eclipse geometry,
# synodic period, ISRU chemistry, tankage, electric-stage sizing — to reach a
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
# power source and once per point of the concentration sweep — up to eighteen
# times for one dead candidate.
#
# ⚠️  This function and `max_return_payload_kg` are two statements of the same
# algebra, which is exactly the duplication CLAUDE.md warns about ("two copies
# of this algebra drifting apart is how a mass ends up in one cascade and not
# the other").  They are kept adjacent for that reason, and the defence is
# `prune_infeasible_combos = False` plus a column-by-column diff — if the two
# ever disagree, the pruned build drops rows the unpruned one keeps and the
# diff says so immediately.  Change one, re-run that diff.
_PREFILTER_CONSTS_KEY = "_prefilter_consts"

# Cache-miss sentinel for the search's `_combo_close_terms` memo (v1.14.2).
# `None` is a legitimate CACHED value there — it means "no vehicle in the table
# could close this candidate" — so a plain `.get(key)` returning None cannot
# distinguish a miss from a stored refusal, and would recompute every refusal on
# every vehicle, i.e. exactly the work the memo exists to remove.
_UNCACHED = object()

# ─────────────────────────────────────────────────────────────────────────────
# PER-ROW CONSTANTS FOR THE SIZING PATH  (v1.14.2)
# ─────────────────────────────────────────────────────────────────────────────
# The same finding as `_PREFILTER_CONSTS_KEY` one level further in: six
# quantities that `_evaluate_combo_at_ratio` derived on entry are functions of
# (propellant row × config) alone, and one is a function of the vehicle row
# alone.  They were re-parsed out of the row for every SURVIVING candidate —
# 218,000 times per 150 beneficiated asteroids — and each parse goes through
# `pd.isna`, which is ~700 ns because it is a pandas dispatch on a Python
# scalar.  That alone was ~980,000 `pd.isna` calls per 150 rows.
#
# Attached to the row dict rather than memoised on `id()`, for the same reason
# the pre-filter constants are: the dict is what crosses the multiprocessing
# boundary, so a worker gets the derived values with the row instead of
# rebuilding them, and there is no identity to be recycled.
#
# `tank_frac` is deliberately derived HERE and read by both consumers.  It was
# computed twice from the same two columns — once in
# `_prefilter_propellant_consts`, once in `_evaluate_combo_at_ratio` — which is
# the drift hazard this file keeps naming.  One derivation now, two readers.
_SIZING_CONSTS_KEY  = "_sizing_consts"
_VEHICLE_CONSTS_KEY = "_vehicle_consts"


def _tank_frac_per_kg(propellant: Row, config: CalcConfig) -> float:
    """Tank mass per kg of propellant, or 0.0 where the row cannot state one.

    Module 3 quotes tankage per LITRE because that is what it scales with — a
    tank encloses volume, not mass — so this is the one place the two columns
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
    shared constants exactly as it did before — the two-part test they replace
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


def _vehicle_consts(vehicle: Row) -> float:
    """Usable fairing volume in m³, defaulted for a row that does not state one."""
    fairing_m3 = vehicle.get("fairing_volume_m3")
    return (float(fairing_m3)
            if fairing_m3 is not None and not pd.isna(fairing_m3) else 100.0)


def _prefilter_propellant_consts(
    propellant: Row,
    config:     CalcConfig,
) -> Optional[Tuple[float, float, float, float]]:
    """(isp, dv_penalty, tank_frac, boiloff_pct) for one propellant, or None.

    These depend only on the propellant row and the config, so they are derived
    once per run in `candidate_combos` rather than per (asteroid × candidate).
    None means the row cannot fly at all — no usable Isp — which is the same
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

    v1.14.2.  The launch capacity enters this test in exactly one place — the
    final comparison — and it enters MONOTONICALLY: a bigger rocket can never
    turn a candidate that closes into one that does not.  Everything else is a
    function of (propellant × Δv × ISRU).

    That matters because the combo grid is vehicle-major, so the question was
    asked once per vehicle: seventeen evaluations per propellant row per
    asteroid, computing the same two exponentials, the same boil-off inflation
    and the same tankage closure, and differing only in the last line.

    ⚠️  This returns the COEFFICIENTS of that last line rather than the launch
    capacity it implies, and the difference is not stylistic.  `bracket > 0`
    rearranges algebraically to `leo > (hw + k·s·d0·R_ret)·k_out·R_out`, but not
    in floating point — the rearrangement re-associates the arithmetic and moves
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
    # inflate R_ret directly — `r_ret_eff = 1 + (r_ret - 1) · factor` is the
    # substitution the loop makes.  ISRU is exempt: the propellant is made at
    # the asteroid on departure rather than held from launch.
    if config.model_propellant_boiloff and boiloff_pct > 0 and not isru:
        outbound_yr = max(0.5, 0.000_23 * dv_out)
        hold_yr     = outbound_yr + config.station_keeping_floor_yr + window_wait_yr
        r_ret = 1.0 + (r_ret - 1.0) * math.exp(
            boiloff_pct / 100.0 * hold_yr * 365.25)

    if not (math.isfinite(r_out) and math.isfinite(r_ret)):
        return None

    # Tankage closure — t·(R − 1) ≥ 1 means the tank outweighs the propellant's
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
    not a guess — see the section header above for why pass 1 dominates.

    Deliberately one-sided.  True does not promise a viable mission: the
    throughput cap, the duration limit, the volume cap and the post-settle
    launch recheck all still apply downstream, and about a quarter of the
    survivors die on one of them.  Cheap and sound beats tight and clever here.

    v1.14.2 split the work in two — `_combo_close_terms` for the part that does
    not depend on the vehicle, `_closes_with` for the part that does — because
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

      • HEAT SHIELD, tps_frac × (m_payload + m_dry_return) — hauled outbound
        from Earth AND pushed back through the return burn, even though it
        ablates on entry.  Let s = 1 + tps_frac.
      • RETURN-VEHICLE STRUCTURE, structure_frac × m_payload (v1.10.0) — the
        primary structure and cargo restraint that a bigger haul needs.
        Let f = structure_frac, so the dry vehicle is d0 + f·m_payload.
      • PROPELLANT TANKAGE, tank_frac × m_propellant (v1.11.0) — and this one
        is circular in a way the other two are not, because the tank is sized
        by the propellant and is itself mass the propellant has to push.
        Let t = tank_frac.

    On tankage.  Module 3 derives t per propellant from storage class and
    density (tank_kg_per_L / density_kg_per_L), and it is not a rounding term:
    2.5% for kerolox, 9.7% for hydrolox, 46% for cold gas, 53% for the bare
    hydrogen a nuclear-thermal stage burns.  Leaving it out was a straight
    subsidy to whichever propellant had the lowest density, which is the same
    propellant that has the highest Isp — so the error compounded rather than
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
    def _infeasible(r_out=0.0, r_ret=0.0):
        return {"max_payload_kg": 0.0, "viable": False,
                "r_out": r_out, "r_ret": r_ret,
                "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
                "m_at_asteroid": 0, "m_tps": 0, "m_dry_return": 0,
                "m_tank_return": 0, "m_tank_outbound": 0}

    # ── Scalar arithmetic uses `math`, not numpy (v1.14.2) ───────────────────
    # Every argument here is a Python float, and numpy's ufunc dispatch costs
    # ~700 ns on a scalar against ~30-50 ns for the `math` equivalent.  This
    # function is called ~2.2 times per surviving candidate — 387,000 times per
    # 150 beneficiated asteroids — so seven ufunc dispatches were about half its
    # runtime and roughly a quarter of the whole search.
    #
    # `math.exp` and `np.exp` were checked bitwise over 400,000 samples across
    # the (Δv, Isp) range this model spans: zero mismatches.  They differ only
    # in how they OVERFLOW — numpy returns inf and warns, `math` raises — which
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
    # propellant for this burn outweighs the propellant's own contribution —
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
        # launched from Earth — you can make propellant out there, not a
        # pressure vessel — so the launch constraint becomes:
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
            # Placeholder cascade — evaluate_combo will recompute once the
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
    # with it — hence k_out.
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

    capped at `p_mature`, because growth is asymptotic — no amount of heritage
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

    Summed exactly rather than integrated — the integral approximation is
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
# searched axis, so they are called once per (candidate × programme) — and at
# the top of the ladder N runs into the hundreds, which would put a
# several-hundred-iteration Python loop inside the innermost loop of the search.
#
# Memoised by VALUE, not by identity, because that is what the arguments are:
# `p_first`, `alpha`, `p_mature` and `rate` are constants for a whole run, so
# these caches hold at most one entry per rung of the ladder.  Nothing about the
# arithmetic changes — same function, same arguments, same result — which is the
# only kind of speed-up this module accepts on a release that also moves numbers.
_LEARNING_CURVE_CACHE: Dict[Tuple[int, float], float] = {}
_MINING_RELIABILITY_CACHE: Dict[Tuple[int, float, float, float], float] = {}


def _learning_curve_cached(n_units: int, rate: float) -> float:
    key = (int(n_units), float(rate))
    val = _LEARNING_CURVE_CACHE.get(key)
    if val is None:
        val = learning_curve_factor(n_units, rate)
        _LEARNING_CURVE_CACHE[key] = val
    return val


def _mining_reliability_cached(
    n_missions: int, p_first: float, alpha: float, p_mature: float,
) -> float:
    key = (int(n_missions), float(p_first), float(alpha), float(p_mature))
    val = _MINING_RELIABILITY_CACHE.get(key)
    if val is None:
        val = mining_success_probability(n_missions, p_first, alpha, p_mature)
        _MINING_RELIABILITY_CACHE[key] = val
    return val


def rig_trips_per_ship(
    ops_df: pd.DataFrame, config: CalcConfig, stay_yr: float,
) -> Optional[Tuple[int, int, Optional[int]]]:
    """How many consecutive campaigns one rig is good for, at this stay length.

    Returns `(trips, calendar_cap, trip_cap)`, or None when rig service life is
    not modelled at all — in which case one rig serves the entire programme,
    which is what this module did before v1.8.0.

    v1.15.0 adds the second of the two bounds, and the reason it is second
    rather than a refinement of the first is worth stating plainly:

      • `Mining rig service life` is **15 YEARS**.  It is a calendar figure and
        its own Module 3 notes describe a calendar mechanism — corrosion,
        thermal cycling, radiation dose.  Dividing it by the stay produced a
        mission count, and that count was treated as the rig's whole life.
      • Nothing bounded DUTY CYCLES.  At the ~1.25 yr stay the winning cislunar
        mission actually flies, the calendar bound made one rig good for 12
        consecutive mining campaigns — twelve full digs out of a number that
        only ever promised the machine would not have rusted meanwhile.

    A rig parked between campaigns ages slowly.  One cutting rock does not.  So
    the two bounds are independent and the binding one is the MIN: a long-stay
    mission is still calendar-limited, a short-stay one is now cycle-limited,
    which is the correct way round and was the whole gap.

    A missing Module 3 row reverts to calendar-only, silently, exactly as every
    other `_ops_value` default does — which is why the row is named in
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
    sets the cadence — so the bound is the max of the two, not the stay.

    ⚠️  That lands hardest on exactly the bodies this model likes.  A synodic
    period goes to infinity as a → 1 AU, so a NEA at 1.05 AU can only be
    revisited every ~14 years however fast its rig works, while a main-belt
    body at 3 AU comes round every ~1.6.  Δv accessibility and CADENCE are
    anticorrelated for the same reason Δv accessibility and trip time already
    are — see `synodic_period_yr` — and a programme is where that finally
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
    W = 1 — which is every single-mission figure this project has ever
    published.

    ── What is actually wrong without this ─────────────────────────────────

    This module compounds costs FORWARD to the point of sale and compares them
    against undiscounted revenue; that is the convention `mission_cost_usd`
    already implements with `(1 + W)^T` on the up-front bucket.  Applied to one
    mission it is right.  Applied to a programme it quietly assumes every
    mission in the programme happens at once.

    It does not.  F ships fly W campaigns each, and the campaigns on one ship
    are strictly sequential — one rig, one hole, one dig at a time.  So the
    programme spans `T + (W − 1) × cadence` of calendar, and the articles that
    are bought ONCE at the start and amortised across all of it — the bus NRE,
    the autonomy NRE, and the rig itself — are being carried for far longer
    than one mission duration before the missions they paid for sell anything.

    Note which lines this is and is not.  A per-mission article (the launch,
    the capsule, the propellant, the plant, the electric stage) is bought for
    its own campaign, and that campaign's costs AND its revenue both sit at the
    same point in the programme — shift a whole cash flow and its cost/revenue
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
    collect it — the exact shape of subsidy this module keeps finding, arriving
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

    Two geometric midpoints — the interval between the bracketing rungs is
    exactly what the coarse sweep left unexamined — plus both immediate integer
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

      • **F is a ladder** — geometric, refined, capped by `max_fleet_ships`,
        exactly as v1.15.0 built it.  It runs to 64 and cannot be enumerated.
      • **W is ENUMERATED EXHAUSTIVELY**, 1 … trips.  No ladder, no refinement
        pass, no unimodality assumption, because `trips` is
        `min(life / stay, max_trips)` and `max_trips` is 5 — the whole
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

    N — `nre_amortization_missions` — is the programme size, and it enters this
    model in exactly six places: the NRE division, the autonomy-NRE division,
    the rig amortisation, the learning curve, reliability growth, and (since
    v1.14.0) the concurrent output that market saturation prices against.  Group
    them by how they behave and the search collapses:

      • ONE RIG SERVES `trips` MISSIONS BACK TO BACK, so a programme of N needs
        `ceil(N / trips)` rigs and that many missions are in flight at once.
        The saturation multiplier is a function of that COUNT and of nothing
        else about N.
      • WITHIN ONE FLEET BAND — every N with the same `ceil(N / trips)` — the
        multiplier is therefore constant, while NRE/N falls, autonomy NRE/N
        falls, the learning curve falls, the rig's per-mission share falls (or
        holds), and p_mining rises.  Every single lever improves and none
        pushes back.

    So the best N in a band is always the TOP of the band, N = F × trips, and no
    other N can ever be optimal.  The search is over F, exactly `max_fleet_ships`
    integers of which only ~12 are ever evaluated — rather than over N, which
    would be `max_fleet_ships × trips` of them, and which is what "just run it at
    1, 10 and 100" was sampling blindly.

    That is not an approximation and it is not a heuristic.  It is also the
    answer to the question the user asked in the first place: the number of ships
    is the decision variable, and programme size is its consequence.

    Two further consequences worth keeping:

      • N = 1 IS NEVER SKIPPED IN EFFECT.  It sits in band 1, whose top is
        N = trips, and by the argument above N = trips dominates it.  So a
        searched run can never report a worse objective than the N = 1 run every
        committed figure in this project was measured at — which is the
        never-worse invariant this module requires of any new axis, and here it
        holds by construction rather than by measurement.
      • N = F × trips IS ALSO THE ONLY N THE COST MODEL IS EXACTLY RIGHT AT.
        `mining_rig_cost` charges every mission the same share of a fully-used
        rig, so a programme of 13 with trips = 12 books its second rig — used
        once — as though it were worn out.  At a whole multiple there is no
        part-worn rig to mis-book.

    ⚠️  THE BAND ARGUMENT IS PER CANDIDATE, AND `trips` IS NOT A PROPERTY OF THE
    BODY.  It is `min(life / stay, max_trips)`, and the stay depends on how hard
    that candidate concentrates — so two concentration ratios on the same rock
    are two different mission profiles with two different trip lives and two
    different ladders.  That is handled correctly, because this function is
    called per candidate with that candidate's own stay.

    What it exposes is a pre-existing heuristic one level up.  `evaluate_combo`
    sweeps the concentration ratio coarsely and then refines around the WINNER,
    and the winner now depends on N — so a ratio that would have won at some
    other programme size can fall outside the refined region and never be
    priced.  Measured on 2014 JT2 beneficiated: brute-forcing every N from 1 to
    40 finds N = 4 at 30.2597x on a ratio of 3.216 (stay 1.74 yr, trips 4),
    while the ladder reports N = 3 at 30.5535x on a ratio of 5.518 (trips 3) —
    0.97% worse, because 3.216 was never on the grid it searched.  Raising
    `concentration_search_steps` from 7 to 25 makes the ladder return 30.2597x
    on ratio 3.216 exactly, which is what identifies the grid rather than this
    argument as the cause.

    It is documented rather than patched.  Refining around the best two ratios
    would be a heuristic stacked on a heuristic, for a sub-1% effect that the
    existing dial already closes — and `concentration_search_steps` is the dial
    this project already points at for exactly this trade.  It bites only where
    beneficiation is on AND the optimum stay sits near a `life / stay` step.

    With `optimise_programme_scale` off this returns the single configured
    programme, which is the pre-v1.15.0 behaviour exactly.
    """
    n_cfg = max(1, int(config.nre_amortization_missions))
    trips = rig_trips[0] if rig_trips is not None else None
    calendar = config.model_programme_calendar

    if trips is None:
        # No service-life cap at all: one rig serves the whole programme, so
        # `concurrent_missions` is 1 for every N and saturation never pushes
        # back.  The objective is then monotone improving in N without bound —
        # "fly more missions" is free money again, which is precisely the
        # failure v1.14.0 closed.  Searching an unbounded monotone axis reports
        # the ladder's top rung as a result, so it is refused rather than run.
        # `build_profitability_catalog` says so out loud at startup.
        #
        # ⚠️  The calendar charge does NOT rescue this.  With one rig serving
        # everything, W = N and the charge grows without bound too — but so
        # does the amortisation it is charged against, and neither is bounded
        # by anything physical, so the optimum would be an artefact of whichever
        # diverges faster.  Still refused.  (W = N here is not read anyway:
        # `mission_cost_usd` only consults it inside the rig block, which this
        # branch means is switched off.)
        return [(n_cfg, 1, n_cfg)]

    if not config.optimise_programme_scale:
        f = max(1, math.ceil(n_cfg / trips))
        # v1.16.0: campaigns per ship is derived from the fleet.  Off, it is
        # the v1.15.0 expression `min(N, trips)` — which over-counts a
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
    # enumerated rather than laddered — it is at most `max_trips` integers.
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
    owns building the mapping — this only skips the call on a hit.
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
    they were being looked up inside `_evaluate_combo_at_ratio` — which runs
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
    `_ops_value`, and `rig_trips_per_ship` two more — none of which depends on
    the asteroid, the vehicle, the propellant, the architecture or the
    programme option.  They are pure functions of `ops_df`, which is loaded
    once per run and never mutated.

    That was survivable while the cost model ran once per surviving candidate.
    It stopped being survivable in v1.17.0, which turned `optimise_programme_scale`
    ON BY DEFAULT: the programme ladder prices a median of 40 options per
    mission, so every one of those lookups is now multiplied by 40.  Measured
    on a 150-row beneficiated cislunar sample with the search on,
    `_ops_value` was running **8.06 million times** — 11.7% of the profile, to
    re-read twenty-two numbers that never move.

    Ordered, not named, for the same reason `_ops_sizing_constants` is: the
    callers unpack the whole tuple in one statement, which is a single opcode,
    and every read after that is a local.  Keep this list and the unpacking in
    `mission_cost_usd` in the same order — they are checked against each other
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
    `missions_per_ship` and NOTHING else — every other argument is held fixed
    across a median of 40 options — yet the whole cost cascade was re-derived
    for each of them.  That is ~10 `max()` calls, ~6 dict lookups, ~15 `float()`
    conversions, a `delivery_architecture` call and a 22-tuple unpack, run forty
    times to change three numbers.  This is the same finding as v1.17.1's, one
    level up: that release stopped re-READING the constants, this one stops
    re-DERIVING everything computed from them.

    ── WHY THIS IS BIT-IDENTICAL, WHICH v1.17.1 SAID IT COULD NOT BE ───────────

    That release deferred this split because "it re-associates the final sums,
    and this project's releases are argued from bit-identity".  The premise is
    right and the conclusion does not follow, because every N-dependent line in
    the cascade factors as `<N-independent base> * lc` — and Python evaluates
    `a * b * lc` left to right, as `(a * b) * lc`.  So hoisting `a * b` into a
    name and multiplying by `lc` in the tail is the SAME two operations in the
    SAME order, not an algebraically-equal rearrangement.  Same for
    `nre_total * (1.0 - overlap) / n_missions`, which is `(a * b) / n`.

    🚨  What must NEVER be hoisted is a PARTIAL SUM whose terms interleave with
    N-dependent ones.  `hardware_cost`, `spacecraft_book_value` and
    `upfront_lines` all mix the two, and pre-adding their N-independent members
    would re-associate the addition — numerically negligible and fatal, exactly
    as the v1.14.2 phase-table sort was.  Those three sums are therefore
    restated VERBATIM in `_mission_cost_tail`, term for term and in order, and
    the four or five adds that costs are not what this function was slow for.

    ⚠️  The returned tuple's field order is load-bearing and is unpacked in one
    statement at the top of `_mission_cost_tail` — keep the two together, the
    same discipline `_ops_cost_constants` and its consumer already follow.
    """
    # v1.17.1: the twenty-two Module 3 constants this cascade reads, resolved
    # once per run rather than once per call.  Order matches
    # `_ops_cost_constants` — keep the two together.
    (hw_per_kg, life_yr, salvage, _max_trips_raw,
     lander_per_kg, capsule_earth_per_kg, berthing_per_kg,
     power_per_w, rtg_per_w, ep_drive_per_kw, tank_per_kg,
     ops_per_year, tps_per_kg,
     recovery_earth, licensing_earth, recovery_depot, licensing_depot,
     liability_cost, launch_ins_raw,
     nre_total, autonomy_nre_total, wacc_rate) = _ops_cost_constants(ops_df)

    cost_per_kg_prop = float(propellant["cost_usd_per_kg"])
    launch_cost      = float(mass_cascade["m_launch"]) * float(vehicle["usd_per_kg_to_leo"])

    # ── Orbital refuelling (v1.11.0, re-keyed v1.12.0) ───────────────────────
    # Some vehicles quote a beyond-LEO payload that assumes being refuelled in
    # orbit first.  Starship is the case in this table, and the tell is in its
    # own numbers: 27 t to escape against 21 t to GTO.  A payload cannot grow
    # with departure energy under any propulsion system — unless the escape
    # figure is for a vehicle that was topped up after reaching orbit.
    #
    # Module 3's row has said so in prose since v1.4.0 and named the fix:
    # "Module 4 should add ~$90M × N_tankers to the ESCAPE-DIRECT SCENARIO for
    # an apples-to-apples comparison."  v1.11.0 implemented the arithmetic and
    # missed the scenario — it levied the charge on every mission.
    #
    # This module has no escape-direct scenario.  It reads `payload_leo_kg` and
    # `usd_per_kg_to_leo` and nothing else (grep the file): the launch vehicle
    # delivers the stack to LEO, and the stack departs on its own outbound
    # stage, which is sized by the rocket equation a few dozen lines up.
    # Starship's 100 t to LEO needs no tankers — refuelling is what buys the
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
    mining_rig_cost_total   = config.mining_hardware_kg * hw_per_kg

    # v1.17.1: `rig_trips` is `(ops_df, config, stay_yr)` and nothing else, and
    # all three are held FIXED across a programme ladder — so the caller that
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
    # v1.6.0: a surface base needs a LANDER — throttleable descent engines,
    # legs, terminal guidance — which is more machine than either a passive
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
    # out of the ledger — the same asymmetry the EP stage had.
    dry_return_flown = float(mass_cascade.get(
        "m_dry_return", config.return_vehicle_dry_kg))
    # ⚠️  v1.17.2: each `*_base` below is the original expression with its
    # trailing `* lc` removed, and nothing else.  The learning curve is applied
    # in the tail because it is the one factor that moves with N.
    capsule_base            = dry_return_flown * capsule_per_kg
    # v1.5.0: the beneficiation plant's solar array, priced per installed Watt
    # off Module 3's power-system row.  Zero unless beneficiation is on — the
    # baseline rig's own power is already implicit in its $/kg recurring rate.
    # v1.11.0: past 3.46 AU the sizing loop may have chosen a radioisotope
    # source because it is LIGHTER there.  It is also 625× more expensive per
    # watt, and charging it at the solar rate would be exactly the asymmetry
    # this codebase keeps finding — a mass in the rocket equation with the
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
    # module has flown it through the rocket equation ever since — outbound
    # tank staged at the asteroid, return tank carried home — but nothing ever
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

    # Heat shield — mass now comes from the actual cascade, not re-derived.
    # v1.14.0: the learning curve applies here too.  An ablative heat shield is
    # consumed on entry and rebuilt for every mission — it is the most literally
    # per-mission article on the vehicle — so Wright's law applies to it exactly
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

    # Launch insurance — percent of (launch + spacecraft book value).
    # Gross value of future revenue is NOT insured — underwriters cover the
    # replacement cost of the launched asset only.
    #
    # v1.12.0: that asset is everything on the rocket, and the book value had
    # drifted behind the mass cascade.  It listed the mining rig and the
    # capsule, which was the whole spacecraft in v1.4.0 — but v1.5.0 added a
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
    # missed — it is the one item on the launch stack whose cost line sits
    # outside `hardware_cost`.  On an Earth-return mission it is a 15%-of-payload
    # article at $50,000/kg, so it is not a rounding term where it exists at all.
    launch_ins_pct        = launch_ins_raw / 100.0

    # Spacecraft bus NRE amortised across N missions, less the share already
    # embedded in the per-kg recurring rate (v1.4.0 — see
    # nre_recurring_overlap_fraction).  NICM / SSCM per-kg brackets are
    # regressions on total program cost, so charging full OSIRIS-REx NRE on
    # top of a $300k/kg recurring rate books part of the development twice.
    nre_overlap = min(max(config.nre_recurring_overlap_fraction, 0.0), 1.0)
    nre_base    = nre_total * (1.0 - nre_overlap)

    # ── Time-bucket every line item ──────────────────────────────────────────
    # UPFRONT = paid at year 0 (or earlier — NRE accumulates pre-launch but
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

    # WACC compounding — apply per bucket so end-of-mission costs aren't
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
        config.learning_curve_rate,
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
    # remains when the programme ends is credited at the salvage fraction —
    # but only if there IS a programme; a rig at an asteroid nobody revisits
    # is stranded, not an asset.
    rig_terminal_value = 0.0
    missions_sharing_rig = n_missions
    if rig_trips is not None:
        trips, _calendar_cap, trip_cap = rig_trips
        # v1.16.0: how many campaigns one rig actually flies is a property of
        # the FLEET, not of N alone — F ships split N between them.  The caller
        # supplies it because the caller is what searched (F, W).  None keeps
        # the v1.15.0 expression, which is what `model_programme_calendar` off
        # and every pre-v1.16.0 caller get.
        missions_sharing_rig = (min(n_missions, trips) if missions_per_ship is None
                                else max(1, min(int(missions_per_ship), trips)))
        if n_missions > 1:
            # Life USED, and there are now two ways to use it up.  Crediting
            # salvage on remaining calendar years while the rig is mechanically
            # finished would pay a refund on a worn-out machine — the same shape
            # of subsidy this module keeps finding — so the binding utilisation
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
    rig_share_divisor = max(1, missions_sharing_rig)
    mining_rig_cost = ((mining_rig_cost_total - rig_terminal_value)
                       / rig_share_divisor)
    # The same two halves again, kept apart rather than netted, because the
    # programme calendar term compounds them in OPPOSITE directions: the rig is
    # bought at t = 0 and the salvage is collected at the end.  Netting first
    # and applying one multiplier would credit the refund for arriving late.
    # Read only by the calendar block below, which is skipped outright when the
    # multipliers are 1.0 — so `mining_rig_cost` above stays the arithmetic
    # v1.15.0 performed, in the order it performed it.
    rig_gross_share  = mining_rig_cost_total / rig_share_divisor
    rig_credit_share = rig_terminal_value    / rig_share_divisor

    # v1.7.0: LEARNING CURVE.  The per-mission articles — the capsule or
    # lander, and the power system — are built N times over a programme, and
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

    # 🚨  Term by term, in order — same reason as `hardware_cost`.
    spacecraft_book_value = (mining_rig_cost_total + capsule_cost
                             + power_system_cost + ep_system_cost + tank_cost
                             + heat_shield_cost)
    launch_insurance_cost = launch_ins_pct * (launch_cost + spacecraft_book_value)

    nre_cost    = nre_base / n_missions

    # Autonomous mining control & AI NRE — uncrewed-mission specific (Module 3
    # v1.2.4+ replaced the legacy 'Crew' line item with this).  Amortised the
    # same way as the bus NRE — once developed, the autonomy stack ships on
    # every subsequent identical mission.
    autonomy_nre_cost  = autonomy_nre_total / n_missions

    # 🚨  Term by term, in order — same reason as `hardware_cost`.  Four of
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
    # t = 0 and amortised across all of them — bus NRE, autonomy NRE, the rig —
    # are carried for that whole span.  See `programme_calendar_multipliers`
    # for why only those three, and why the salvage credit runs the other way.
    #
    # Written as a DELTA on top of the untouched v1.15.0 expression rather than
    # as a rebuilt sum.  Both multipliers are exactly 1.0 at W = 1, so the
    # branch is skipped, no term is re-associated, and the released arithmetic
    # is bit-identical — which is the only form this project's verification can
    # actually check, and the reason the phase-table sort was rejected in
    # v1.14.2.
    cal_cost  = cal_credit = 1.0
    if calendar_on and missions_sharing_rig > 1:
        cal_cost, cal_credit = programme_calendar_multipliers(
            missions_sharing_rig, cadence, wacc)

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
    # `subtotal`, `contingency_cost`) or the dict itself — nothing below
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

    Uncrewed autonomous mining mission — no crew cost line.

    v1.17.2: the body is split into `_mission_cost_prologue` (everything that
    does not move with programme size) and `_mission_cost_tail` (everything
    that does), because the programme ladder varies only `n_missions` and
    `missions_per_ship` and was re-deriving the other ~90% of the cascade for
    each of a median 40 options.  This function is their composition and is
    unchanged in signature, in behaviour and — the point of the exercise — in
    the exact floats it returns.  It remains the entry point for every caller
    that prices ONE programme; `_price_programme` builds the prologue itself.

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
    nothing else — not the vehicle, not the propellant, not the return mode, not
    the power source, not the concentration ratio — and every one of them was
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
    candidate in turn — so the caller bails on the whole asteroid instead of
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
    a_dest_au = (A_MARS_AU
                 if str(config.delivery_destination).strip().lower() == "mars_surface"
                 else 1.0)
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
) -> Optional[Dict[str, float]]:
    """Evaluate one (vehicle × propellant × architecture) mission for one asteroid.

    `aero` and `isru` are the return mode and the propellant-sourcing decision
    for THIS candidate mission — v1.10.0 made both per-asteroid searches rather
    than global config settings, so they arrive as arguments.  Passing
    aero=None falls back to what the config allows for the destination.

    Returns None if the mission is infeasible (zero return payload, no
    propellant to make, over the duration limit), or a full result dict
    including profit, ROI, $/kg returned, and the mass + cost cascades.
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
    # ── Per-row constants (v1.14.2) ──────────────────────────────────────────
    # `candidate_combos` attaches these, but a caller that hand-builds `combos`
    # will not have.  Derived on demand in that case rather than defaulted —
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
    # which meant re-deriving them for every candidate mission — see
    # `AsteroidContext` for the call counts.  `ctx` is built once per asteroid
    # by `evaluate_asteroid`; rebuilding it when a caller does not supply one
    # keeps this function usable on its own.
    if ctx is None:
        ctx = asteroid_context(asteroid_row, ops_df, config)
        if ctx is None:
            return None      # no usable mass — nothing to cap the payload with

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
    # With beneficiation OFF no array mass is added at all — the existing
    # 2,000 kg rig figure already carries its own power implicitly, and this
    # keeps a default run bit-identical to v1.4.0.
    # The five `_`-prefixed slots are dead HERE and must still be unpacked —
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
    # The EP array does not — it is in interplanetary cruise, in permanent
    # sunlight — so `ep_w_per_kg` keeps the bare 1/r² figure and only the plant
    # takes the night-side penalty.
    w_per_kg              = ctx.solar_w_per_kg
    ep_w_per_kg           = w_per_kg
    w_solar_eff           = ctx.plant_w_per_kg_solar
    array_oversize_factor = ctx.array_oversize_factor
    plant_w_per_kg = w_solar_eff
    power_source   = "solar"

    # ── The power source is a SEARCHED architecture choice (v1.14.0) ─────────
    # It used to be resolved inside the sizing loop by `power_source_for_target`,
    # on MASS alone — take whichever of photovoltaic and radioisotope is lighter
    # at this distance.  That is not the objective this module reports, and the
    # two differ by 625× in price per watt ($500,000 against $800), so the model
    # was buying a nine- or ten-figure radioisotope plant to save array mass and
    # nothing ever asked whether that paid.
    #
    # It went unnoticed because it was unreachable: on v1.12.0 the branch fired
    # on ONE row of 15,566.  Adding the eclipse term makes photovoltaics roughly
    # half as good per kilogram, which moves the crossover from 3.46 AU to about
    # 2.1 AU and puts a third of the catalog on the nuclear side — at which point
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
    # An electric stage is not a chemical stage with better Isp — it needs a
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
    # thruster — 8% efficient, 5,000 kg of hardware per newton — was priced
    # identically to a gridded ion engine at 70% and 54 kg/N.  A third of the
    # winning missions in a full cislunar run were PPT.
    #
    # Both fall back to the old shared constants when the column is absent, so
    # a pre-Module-3-v1.10.0 catalog reproduces v1.11.0.  `schema_check()`
    # names them, because the fallback is silent and flattering.
    eff_used            = ep_eff
    thruster_kg_per_n   = 0.0
    ppu_kg_per_kw       = ep_kg_per_kw
    # v1.14.2: both figures are parsed once per run by
    # `_sizing_propellant_consts`, which reports None where the row states no
    # usable value — so the fallback to Module 3's shared constants is unchanged
    # and a pre-Module-3-v1.10.0 catalog still reproduces v1.11.0.
    if is_electric:
        if thruster_eff_row is not None:
            eff_used = thruster_eff_row
        if thruster_kg_per_n_row is not None:
            thruster_kg_per_n = thruster_kg_per_n_row
            ppu_kg_per_kw     = ppu_only_kg_per_kw   # thruster now counted separately

    # `isp_s_val`, `boiloff_pct` and `tank_frac` all arrive on `sizing_consts`.
    # ── Tankage (v1.11.0) ────────────────────────────────────────────────────
    # Module 3 quotes tank mass per LITRE, because that is what it scales with;
    # the cascade wants it per kilogram of propellant, so divide by density.
    # A propellant row predating Module 3 v1.9.0 has neither column and comes
    # through as 0.0, which reproduces v1.10.1 exactly.
    #
    # ISRU is exempt from boil-off — the propellant is made at the asteroid on
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
    # shortest stay the model allows (station_keeping_floor_yr, 0.25 yr) — but
    # the stay is dig time plus the launch-window wait, which together run to
    # YEARS on the targets that most want a cryogenic upper stage.  Hydrolox at
    # 0.05%/day over a 4-year hold loads 2.1x what the rocket equation burns,
    # against the 1.1x the old estimate implied.  The ISRU feed is new for the
    # same reason: it is rock that has to be dug, and dug rock is time.
    #
    # v1.14.0 adds a seventh leg — VOLATILE CONTAINMENT.  A sealed shaded hold
    # scales with the water in the cargo, the water in the cargo comes out of
    # the payload knapsack, and the knapsack is solved against a payload the
    # containment mass helps determine.  Same ring, one more term, and it is
    # handled the same way rather than estimated once outside the loop — which
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
    # structure, which is exactly what it is — the hopper holds the cargo, the
    # seal and the shade keep the volatile fraction of it from leaving.  Folding
    # it into `structure_frac` means the closed-form solver carries it with no
    # change to the algebra: it is already the f in (1 + f).
    containment_frac = 0.0
    structure_frac_eff = structure_frac
    # v1.17.1: a Module 3 constant, resolved once instead of once per pass of
    # the loop below AND again at the settle-up.  One lookup, two readers —
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
            m_prop_total = (float(cascade.get("m_outbound_prop", 0.0))
                            + float(cascade.get("m_return_prop", 0.0)))
            ep_power_watts = ep_power_required_w(
                m_prop_total, isp_s_val, config.ep_target_thrust_yr, eff_used,
            )
            ep_thrust_n = ep_thrust_required_n(
                m_prop_total, isp_s_val, config.ep_target_thrust_yr,
            )
            ep_thrust_yr = config.ep_target_thrust_yr if m_prop_total > 0 else 0.0
            # Three masses on three different quantities, and keeping them
            # apart is the whole point of v1.12.0:
            #   array      scales with POWER, and 1/r² with distance
            #   PPU        scales with POWER, flat with distance
            #   thruster   scales with THRUST — this is the device constraint,
            #              and it is what a per-kW figure cannot express.
            array_kg    = ep_power_watts / ep_w_per_kg if ep_w_per_kg > 0 else 0.0
            ppu_kg      = ep_power_watts / 1000.0 * ppu_kg_per_kw
            thruster_kg = ep_thrust_n * thruster_kg_per_n
            new_ep_kg   = array_kg + ppu_kg + thruster_kg

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
        # plant to raise it for — with beneficiation off, the 2,000 kg rig's
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
        # top of — which is what lets it fold into structure_frac and leaves the
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
            # in the ledger and never entered the rocket equation — the mirror
            # image of the free-EP-stage bug, and the comment there asserted
            # the cascade had already flown it.  It had not: `power_system_kg`
            # came out 0.8-2.7% above the figure inside `hardware_total_kg` on
            # every row that liberated cargo water.  Sizing it here closes the
            # loop the same way every other feedback term in this ring is
            # closed, and it is why the term is no longer gated on
            # `beneficiate or isru` — a RAW mission to an icy body liberates
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
            # all that remains inside it is the Pu-238 ceiling — and that is a
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
            # absolute rather than relative — 1e-4 of a payload-scaling term is
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

    fairing_m3 = vehicle.get(_VEHICLE_CONSTS_KEY)     # v1.14.2, see candidate_combos
    if fairing_m3 is None:
        fairing_m3 = _vehicle_consts(vehicle)
        vehicle[_VEHICLE_CONSTS_KEY] = fairing_m3
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
        feed_kg = min(m_payload * target_ratio, ore_throughput_kg, ore_mineable_kg)
        feed_kg = max(feed_kg, m_payload)          # never less feed than product
        concentration_ratio = feed_kg / m_payload if m_payload > 0 else 1.0
        throughput_fits = feed_kg <= ore_throughput_kg
    else:
        feed_kg = m_payload
        concentration_ratio = 1.0

    return_volume_m3 = m_payload / bulk_density_kg_per_L / 1000.0

    # Recompute the full cascade at the capped payload.  TPS, return-prop,
    # outbound-prop, launch all depend on m_payload — must be redone to
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
    # v1.10.0: the return vehicle grows with what it carries — see
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

        Only the pieces that depend on `hardware_kg` — the payload, the return
        vehicle, its heat shield and its tank are all fixed by m_payload above.
        Factored out because it has to be evaluated TWICE: once to learn how
        much ISRU propellant the mission makes (which sets the dig time, which
        sets the power plant, which is itself hardware), and once more with the
        settled plant mass.  Two hand-written copies of this arithmetic drifting
        apart is precisely how a mass ends up in the rocket equation without a
        matching entry in the ledger.
        """
        # The return TANK is launched from Earth even under ISRU — you can make
        # propellant at an asteroid, not a pressure vessel — so it is inside
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
    # re-derived here — and, critically, the cascade is rebuilt afterwards from
    # the result.
    #
    # Until v1.12.0 this ran ~60 lines further down, after `actual_cascade` had
    # already been built.  The array for baking CARGO water was therefore
    # priced in the ledger and never launched: `power_system_kg` came out
    # 0.8-2.7% above the figure inside `hardware_total_kg` on every row that
    # liberated any, and a raw mission to an icy body paid for an array it flew
    # none of.  The comment there claimed "the cascade already flew" it.  It
    # had not.  This is the same asymmetry as the free EP stage, pointing the
    # other way — a price with no mass rather than a mass with no price.
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
        # feed, to size the containment.  Reused rather than recomputed — one
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
    # rechecked against the vehicle — the closed-form guarantee only holds at
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
    # of it, and that stay time flows into ops cost and WACC.  ISRU feed counts
    # — propellant made on site is rock the same rig had to move.
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
    # Both terms — and the array they size — were settled above, before the
    # cascade was rebuilt, so that the plant in the ledger is the plant in the
    # rocket equation.  `water_kg` is carried down here only to be reported.
    # ── PROGRAMME SCALE AND FLEET SIZE (v1.15.0) ─────────────────────────────
    # Everything above this line is the MASS CASCADE, and none of it depends on
    # how many missions the programme flies.  N enters this module in exactly
    # three places downstream — the cost model, market saturation and
    # reliability growth — and in none of the rocket equation, the fixed-point
    # power solve, the payload knapsack or the concentration sweep.
    #
    # That asymmetry is what makes programme size affordable to SEARCH rather
    # than merely to set: the expensive half of the mission is solved once, and
    # every rung of the fleet ladder is priced off the same cascade.  Running
    # the whole pipeline again at another N — which is how every
    # programme-scale figure in this project was produced — re-solves all of it
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
    # v1.16.0.  How often the rig can start again — the dig, unless windows open
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
    # bit-identity check, so the ORDER of these terms is load-bearing — the same
    # trap documented at length in `optimal_payload_mix`.
    saturation_applies = bool(
        config.model_market_saturation and mission_duration_yr > 0
        and phases and markets is not None)
    sale_terms: List[Tuple[float, float, float]] = []
    if saturation_applies:
        # The mix actually sold: chosen by the optimiser when concentrating,
        # otherwise the body's own proportions.
        if beneficiate and payload_mix:
            sold = dict(payload_mix)
        else:
            frac_sum = sum(f for _n, f, _p in phases)
            sold = {n: m_payload * f / frac_sum for n, f, _p in phases} if frac_sum > 0 else {}
        for phase, kg in sold.items():
            price = next((p for n, _f, p in phases if n == phase), 0.0)
            sale_terms.append((kg, price, markets.get(phase, float("inf"))))

    # ── Mission reliability (v1.8.0) ─────────────────────────────────────────
    # The terms that do not move with programme size, hoisted for the same
    # reason.  Only `p_mining` grows with N.
    p_launch = p_cruise = p_first = rel_alpha = p_mature = 1.0
    if config.model_reliability:
        p_launch  = _ops_value(ops_df, "Launch vehicle reliability", default=0.97)
        mtbf_yr   = _ops_value(ops_df, "Spacecraft mean time between failures", default=30.0)
        p_first   = _ops_value(
            ops_df, "Mining system first-of-kind success probability", default=0.85)
        rel_alpha = _ops_value(ops_df, "Mining reliability growth exponent", default=0.30)
        p_mature  = _ops_value(
            ops_df, "Mining system mature success probability", default=0.95)
        p_cruise  = math.exp(-mission_duration_yr / mtbf_yr) if mtbf_yr > 0 else 1.0

    gross_base           = gross_value
    delivered_base       = delivered_value_per_kg

    # ── v1.17.2: the cost cascade's N-independent half, built ONCE ───────────
    # Every argument below is fixed for the whole ladder — `cadence_yr` included,
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

    def _price_programme(n_missions: int, fleet: int, per_ship: Optional[int] = None,
                         full: bool = True):
        """Everything downstream of the cascade, for one programme size.

        Returns `(cost, total_cost, gross, saturation_mult, concurrent,
        p_success, p_mining, delivered_per_kg)`.  Nothing here re-enters the
        rocket equation; it is one pass of straight-line arithmetic over a
        cascade that is already solved.

        v1.17.1: `full=False` asks for the total alone and leaves `cost` None.
        The ladder below compares options on `total_cost` and nothing else, so
        it prices cheaply and re-prices the single winner in full — one extra
        call out of ~40, against a 40-key dict built and discarded on every one
        of the other 39.  `total_cost` is the same float either way; see the
        early return in `_mission_cost_tail`.
        """
        c = _mission_cost_tail(cost_prologue, n_missions, per_ship,
                               totals_only = not full)
        if full:
            total_cost = c["total_cost"]
        else:
            total_cost, c = c, None
        g         = gross_base
        sat       = 1.0
        delivered = delivered_base
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
        # number by construction — N = F × trips — and one derivation fewer.
        concurrent = 1.0
        if saturation_applies:
            concurrent = fleet
            # v1.17.2: this block reads `fleet` and nothing else the ladder
            # varies — `sale_terms`, `gross_base`, `m_payload` and the mission
            # duration are all fixed for the candidate — so it is a function of
            # F alone, and the ladder is the F ladder CROSSED WITH W.  It was
            # therefore being recomputed once per W: ~40 options over ~8
            # distinct fleets, so four out of five passes re-derived a sum they
            # had already made.  Memoised per candidate on the integer F.
            #
            # Bit-identical by construction rather than by rounding: the same
            # F re-runs the same `+=` over the same list in the same order, so
            # the cached float IS the float the loop would have produced.  That
            # matters here more than most places — this is the accumulation
            # v1.14.2 found to be load-bearing on the last ULP, which is why
            # the phase table must not be sorted at source.
            entry = sat_by_fleet.get(fleet)
            if entry is None:
                adj = 0.0
                for kg, price, mkt in sale_terms:
                    adj += kg * price * saturation_price_multiplier(
                        kg * concurrent / mission_duration_yr,
                        mkt,
                        config.demand_elasticity,
                    )
                entry = sat_by_fleet[fleet] = (
                    adj,
                    adj / gross_base if gross_base > 0 else sat,
                    adj / m_payload  if m_payload  > 0 else 0.0,
                )
            g, sat, delivered = entry
        # Revenue was certain.  It is not: the launch fails, the spacecraft dies
        # on the way, or the mining chain does not work when it arrives.  Costs
        # are charged in FULL, which is correct — you spend the money either way
        # — and launch insurance replaces hardware, not revenue, so this is not
        # a double count.
        ps = 1.0
        pm = 1.0
        if config.model_reliability:
            # v1.9.0: the mining chain LEARNS, so p_mining is the fleet average
            # over the programme rather than the first-of-kind figure held flat.
            # Launch and cruise reliability deliberately do not grow — launch
            # vehicles are mature, and MTBF is a duration exposure rather than a
            # heritage question.
            pm = (_mining_reliability_cached(n_missions, p_first, rel_alpha, p_mature)
                  if config.model_reliability_growth else p_first)
            ps = max(0.0, min(1.0, p_launch * p_cruise * pm))
            g *= ps
        return c, total_cost, g, sat, concurrent, ps, pm, delivered

    # v1.17.1: the ladder prices on totals and the winner is rebuilt in full
    # once, below.  `single` is the common case — the search off, one option —
    # and it skips the rebuild entirely by pricing in full straight away.
    programmes   = programme_options(rig_trips, config)
    single       = len(programmes) == 1
    best_n, best_f, best_w = programmes[0]
    best_priced  = _price_programme(best_n, best_f, best_w, full=single)
    best_pkey    = _objective_key(
        best_priced[2] - best_priced[1],
        best_priced[2], best_priced[1], config)
    priced_count = 1

    for n_missions, fleet, per_ship in programmes[1:]:
        cand = _price_programme(n_missions, fleet, per_ship, full=False)
        priced_count += 1
        key = _objective_key(cand[2] - cand[1], cand[2], cand[1], config)
        if key > best_pkey:
            best_pkey, best_priced = key, cand
            best_n, best_f, best_w = n_missions, fleet, per_ship

    # One refinement pass around the coarse winner, on the same geometric
    # spacing plus both integer neighbours — see `fleet_refinement`.  Skipped
    # entirely when the programme is not being searched, which is the default
    # and the path every committed figure was measured on.
    #
    # v1.16.0: refined at the winner's OWN campaigns-per-ship.  W is enumerated
    # exhaustively, so it needs no refinement of its own — but it does need to
    # be held fixed while F moves, because N = F × W and refining F against some
    # other W would price a programme the search never proposed.
    if len(programmes) > 1:
        ladder = sorted({f for _n, f, _w in programmes})
        for fleet in fleet_refinement(best_f, ladder, ladder[0], ladder[-1]):
            n_missions = fleet * best_w
            cand = _price_programme(n_missions, fleet, best_w, full=False)
            priced_count += 1
            key = _objective_key(cand[2] - cand[1], cand[2], cand[1], config)
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
     p_success, p_mining, delivered_value_per_kg) = best_priced

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
        # Kept with its exact v1.14.0 semantics — 1.0 whenever the saturation
        # term is switched off — so that a gated-off build still reproduces
        # that release byte for byte.  `fleet_ships` below is the unconditional
        # count and is the one to read.
        "concurrent_missions":      concurrent_missions,
        # ── v1.15.0 programme scale and fleet size ─────────────────────────
        # `programme_missions` is N and `fleet_ships` is F, and the invariant
        # between them is N = F × trips_per_ship whenever the search is on.
        # With it off, N is whatever the config said and F is the fleet that
        # size implies — the two columns still describe the same programme,
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
        # 1.0 means no calendar charge was levied — either W = 1, or the term
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
        # Cost breakdown — per-line items
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

    v1.10.0.  Every per-asteroid search in this module — over concentration
    ratio, over vehicle, over propellant, over return mode — used to pick the
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
      • If none does — which is every default configuration today — minimise
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


def _objective_key(
    profit: float, gross: float, cost: float, config: CalcConfig,
) -> Tuple[float, float]:
    """`selection_key`'s ranking algebra, over loose scalars.

    v1.15.0 split this out because the programme-scale search ranks candidates
    before any result dict exists — building one per rung of the fleet ladder
    just to read three fields back out of it would allocate a ~130-key dict per
    comparison.  It is a split for the caller's convenience and NOT a second
    statement of the rule: `selection_key` is defined as this function, so the
    two cannot drift, which is the failure mode this file warns about wherever
    algebra appears twice (see `_combo_can_close`).
    """
    if str(config.selection_objective).strip().lower() == "profit":
        return (0.0, profit)
    if profit > 0:
        return (1.0, profit)
    if gross <= 0:
        return (-1.0, -cost)          # no revenue at all — lose the least
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
) -> Optional[Dict[str, float]]:
    """Best mission for one (asteroid × vehicle × propellant × architecture),
    optimising over how hard to concentrate.  "Best" is `selection_key`, which
    is not simply the highest profit — see there.

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
        phases=phases, target_ratio=r, beneficiate=b, markets=markets,
        aero=aero, isru=isru, rendezvous_apsis=rendezvous_apsis,
        power_mode=power_mode, ctx=ctx,
    )

    if not config.use_beneficiation:
        return solve(1.0, False)

    # Baseline: don't concentrate at all.  Not the same as concentrating at
    # ratio 1.0 — that would still pay the separation recovery loss, the
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
    "False" as True and NaN as True — so a propellant that cannot fly this
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
    # kinetic launchers, and said so in the column's own documentation — "it is
    # in this table because it is DISQUALIFYING for the kinetic launchers" —
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
    # only consumables genuinely changes a mining programme's economics — but
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
    # the propellant row and the config, so they are derived here — once per
    # run, on the same dict every asteroid will read — rather than re-parsed out
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
    vehicle_rows = [_row_to_dict(v) for _, v in vdf.iterrows()]
    for vehicle in vehicle_rows:
        vehicle[_VEHICLE_CONSTS_KEY] = _vehicle_consts(vehicle)
    return [
        (vehicle, propellant)
        for vehicle in vehicle_rows
        for propellant in propellant_rows
    ]


def _prefilter_probe(
    asteroid_row: Row,
    combos:       List[Tuple[Dict[str, Any], Dict[str, Any]]],
    config:       CalcConfig,
) -> Tuple[int, int]:
    """(candidates considered, candidates kept) for one asteroid.

    Mirrors the loop nest in `evaluate_asteroid` exactly — same axes, same
    order, same test — so the printed rate describes the search that is about
    to run rather than an approximation of it.  Diagnostic only; nothing in the
    pipeline consumes the answer.
    """
    window_wait_yr = 0.0
    if config.model_launch_windows:
        a_dest_au = (A_MARS_AU
                     if str(config.delivery_destination).strip().lower() == "mars_surface"
                     else 1.0)
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
        leo_cap   = float(vehicle.get("payload_leo_kg", 0) or 0)
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
    return was flown propulsively — or vice versa — purely because of what some
    other asteroid needed.

    Returns a single result dict (best mission) or None if nothing is viable.

    `combos` is the precomputed candidate cross-join from candidate_combos().
    Left as None it is rebuilt per call — correct but slow, so the main loop
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
    # re-derive per candidate — mineable mass, throughput cap, launch-window
    # wait, ops constants, dark period, eclipse-corrected specific power
    # (v1.14.1).  None means no usable mass, which no candidate could rescue.
    ctx = asteroid_context(asteroid_row, ops_df, config)
    if ctx is None:
        return None
    # Purity bound for beneficiation — the richest concentrate obtainable.
    # Computed once per asteroid rather than per combo; it depends only on
    # composition and prices.
    # Phase table for the load optimiser, and the purity ceiling for reporting.
    # Both depend only on composition and prices, so compute once per asteroid
    # rather than once per (vehicle x propellant) combo.
    # v1.7.0: the phase table is needed even without beneficiation, because
    # market saturation prices each commodity in the haul separately.
    phases  = asteroid_phase_table(asteroid_row, minerals)
    markets = market_table(minerals)
    best_phase_value = (asteroid_best_phase_usd_per_kg(asteroid_row, minerals)
                        if config.use_beneficiation else bulk_value)

    # Return modes worth flying to this body, each with its own best
    # rendezvous apsis already resolved against the destination.
    dv_options = asteroid_dv_options(asteroid_row, config)

    if combos is None:
        combos = candidate_combos(catalogs, config)

    # Whether to make return propellant on site is a (target × propellant)
    # question — it needs water in the rock AND a stage that can burn what
    # water makes — so it is decided inside the combo loop rather than here.
    isru_allowed = (config.use_isru_return_propellant
                    and config.optimise_architecture_per_asteroid)

    # ── Power sources worth pricing for this body (v1.14.0) ──────────────────
    # A radioisotope plant is only ever a candidate where it would be LIGHTER
    # than photovoltaics, which depends on the body's distance and — since the
    # eclipse term — on its rotation.  Both are properties of the asteroid, so
    # the filter is resolved once here rather than per candidate mission, and
    # inner-system bodies never pay for a second pass.
    #
    # `power_source_for_target` keeps its job as the MASS comparator; what
    # changed in v1.14.0 is that its answer generates a candidate instead of
    # being the decision.  Probed at 1 W — any positive draw under the ceiling
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

    # Keep the best candidate under the selection objective — see
    # selection_key for why that is not simply the highest profit.
    # Whether ISRU chemistry closes is a (target × PROPELLANT) question and the
    # combo grid is vehicle-major, so asking it per combo asked it once per
    # vehicle — 36 times for each of the 41 propellant rows, for every asteroid
    # in the catalog.  Memoised on the propellant's identity, which is stable:
    # `candidate_combos` builds one dict per propellant row and shares it across
    # every vehicle pairing (v1.14.1).
    isru_mode_cache: Dict[int, List[bool]] = {}
    # And the vehicle-independent half of the pre-filter, for the same reason
    # (v1.14.2).  Keyed by (propellant identity × Δv option × ISRU), which is
    # everything `_combo_close_terms` reads — so seventeen vehicles now share one
    # evaluation instead of recomputing it each.  `dv_options` is this asteroid's
    # own list, so the index is a stable key within this call.
    close_terms_cache: Dict[Tuple[int, int, bool],
                            Optional[Tuple[bool, float, float, float]]] = {}

    best     = None
    best_key = (-np.inf, -np.inf)
    for vehicle, propellant in combos:
        isru_modes = isru_mode_cache.get(id(propellant))
        if isru_modes is None:
            isru_modes = [False]
            if config.use_isru_return_propellant and isru_feed_kg_per_kg_propellant(
                    asteroid_row, propellant, config) is not None:
                # Feasible here.  Price both when searching; otherwise take ISRU
                # as the config's instruction and fly it wherever it is possible.
                isru_modes = [False, True] if isru_allowed else [True]
            isru_mode_cache[id(propellant)] = isru_modes
        # `candidate_combos` attaches these, but a caller that hand-builds
        # `combos` will not have.  Derive on demand rather than treating the
        # missing key as "no usable Isp" — that reads as infeasible and would
        # prune the ENTIRE search silently, which is the quiet-wrong-answer
        # failure this repo keeps finding.  Absent means unknown, not dead.
        if prefilter and _PREFILTER_CONSTS_KEY not in propellant:
            propellant[_PREFILTER_CONSTS_KEY] = _prefilter_propellant_consts(
                propellant, config)
        pf_consts = propellant.get(_PREFILTER_CONSTS_KEY) if prefilter else None
        leo_cap   = float(vehicle.get("payload_leo_kg", 0) or 0)
        leo_ok    = math.isfinite(leo_cap) and leo_cap > 0
        pkey      = id(propellant)
        for dv_i, dv_opt in enumerate(dv_options):
            for isru in isru_modes:
                # Sits ABOVE the power-source loop on purpose: pass 1 of the
                # sizing loop runs at zero plant mass, so it cannot tell the two
                # power sources apart and would refute both identically.
                #
                # pf_consts is None only when the propellant states no usable
                # Isp, which `max_return_payload_kg` rejects on entry too — so
                # pruning it here agrees with the solver rather than pre-empting
                # it.
                #
                # v1.14.2 splits the test at the vehicle boundary — see
                # `_combo_close_terms`.  The composition is exactly
                # `_combo_can_close`, in the same operations in the same order.
                if prefilter:
                    if pf_consts is None or not leo_ok:
                        continue
                    ckey  = (pkey, dv_i, isru)
                    terms = close_terms_cache.get(ckey, _UNCACHED)
                    if terms is _UNCACHED:
                        terms = _combo_close_terms(
                            pf_consts,
                            float(dv_opt["dv_out_m_s"]), float(dv_opt["dv_ret_m_s"]),
                            (config.heat_shield_frac_of_payload
                             if bool(dv_opt["aero"]) else 0.0),
                            isru, window_wait_yr, config)
                        close_terms_cache[ckey] = terms
                    if terms is None or not _closes_with(leo_cap, terms):
                        continue
                for power_mode in power_modes:
                    result = evaluate_combo(
                        asteroid_row, vehicle, propellant,
                        bulk_value,
                        float(dv_opt["dv_out_m_s"]), float(dv_opt["dv_ret_m_s"]),
                        ops_df, config,
                        best_phase_value_per_kg=best_phase_value,
                        phases=phases, markets=markets,
                        aero=bool(dv_opt["aero"]), isru=isru,
                        rendezvous_apsis=str(dv_opt["rendezvous_apsis"]),
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
# three identity-keyed lookup caches — so the main loop is embarrassingly
# parallel and had been running on one core.
#
# What makes this more than a one-line change is Windows.  There is no fork, so
# every worker is a fresh interpreter that has to reconstruct the parent before
# it can unpickle the first task, and it does that by importing the parent's
# __main__.  Which module that is depends on how the pipeline was launched, and
# one of the three launch paths is actively hostile — see _spawn_environment.

_WORKER_CTX: Dict[str, Any] = {}


def _worker_init(
    minerals: pd.DataFrame,
    ops:      pd.DataFrame,
    combos:   List[Tuple[Dict[str, Any], Dict[str, Any]]],
    config:   CalcConfig,
) -> None:
    """Seed one worker with the read-only state every chunk needs.

    Sent once per worker rather than once per chunk.  Only two of the upstream
    catalogs reach the inner search — minerals (prices, market depths) and ops
    (Module 3's reference rows) — and both are a few dozen rows.  The asteroid
    catalog is never shipped whole; a worker only ever receives the block it is
    about to evaluate.
    """
    _WORKER_CTX["catalogs"] = {"minerals": minerals, "ops": ops}
    _WORKER_CTX["combos"]   = combos
    _WORKER_CTX["config"]   = config


def _evaluate_chunk(chunk: pd.DataFrame) -> List[dict]:
    """Evaluate one contiguous block of asteroids inside a worker.

    Iterating with `iterrows()` here rather than pre-converting rows in the
    parent is deliberate on both counts: it is the same call the serial loop
    makes, so both paths hand `evaluate_asteroid` identical input, and the
    conversion cost lands on a worker instead of on the single core the parent
    has to itself.
    """
    catalogs = _WORKER_CTX["catalogs"]
    combos   = _WORKER_CTX["combos"]
    config   = _WORKER_CTX["config"]

    out: List[dict] = []
    for _, row in chunk.iterrows():
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
    cannot repay their own startup — which is what keeps a 400-row interactive
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

    Asteroids are not equally expensive — the number of viable return modes,
    whether ISRU is even possible, and the width of the concentration sweep all
    vary per body — so one block per worker would leave most cores idle waiting
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
    does not — Streamlit installs a synthetic module named `__main__` whose
    `__file__` points at `ui.py`, so the fallback runs the entire Streamlit app
    inside every worker.  That is not a theoretical hazard; a three-worker pool
    was observed executing the app three times before this was written.
    Pointing `__spec__` at this module instead makes each worker import the
    pipeline, which is what it needs anyway.

    **Quiet workers.**  That import replays the startup banner — 60 lines per
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

    Returns the result list, or None if no pool could be started — the caller
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
            print(f"     ⚠️   Could not start worker processes ({exc}) — "
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
        print(f"     ✂️   Capped at {len(work_df):,} of {n_before:,} rows "
              f"({how}; eval_row_cap / eval_row_sampling in CALC_CONFIG)")

    # Candidate (vehicle × propellant) grid is config-driven, not asteroid-
    # driven — build it once and hand it to every evaluation.
    combos = candidate_combos(catalogs, config)
    if not combos:
        print("\n❌  No candidate vehicle × propellant combinations after "
              "filtering — check operational_vehicles_only / candidate_* in CALC_CONFIG.")
        return pd.DataFrame()
    print(f"     🔧  {len(combos):,} vehicle × propellant combinations per asteroid")

    # ── How much the pre-filter is actually removing (v1.14.1) ───────────────
    # Probed rather than tallied.  A running count would have to come back from
    # every worker, which means changing what a chunk returns, and the number is
    # a property of the POPULATION — a stride probe answers it to well inside
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
        for _, prow in work_df.iloc[probe_idx].iterrows():
            seen_row, kept_row = _prefilter_probe(_row_to_dict(prow),
                                                  combos, config)
            seen += seen_row
            kept += kept_row
        if seen:
            print(f"     ✂️   Pre-filter keeps {kept / seen * 100:.1f}% of "
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
        progress["done"] += rows_done
        i = progress["done"]
        if n >= 100 and (i * 100) // n != progress["pct"]:
            progress["pct"] = (i * 100) // n
            print(f"     … {i:,} / {n:,} evaluated  ({progress['pct']}%)")

    results = None
    n_workers = _resolve_worker_count(config, n)
    if n_workers > 1:
        print(f"     ⚡  {n_workers} worker processes "
              f"({os.cpu_count()} logical CPUs, parallel_workers="
              f"{config.parallel_workers or 'auto'})")
        results = _evaluate_in_parallel(
            work_df, catalogs, config, combos, n_workers, report,
        )

    if results is None:                       # serial path, or no pool started
        progress["done"] = progress["pct"] = 0
        results = []
        for _, asteroid in work_df.iterrows():
            result = evaluate_asteroid(asteroid, catalogs, config, combos)
            if result is not None:
                results.append(result)
            report(1)

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
            print(f"     🧭  Architecture chosen: {'  |  '.join(bits)}")

    # ── What the programme search chose (v1.15.0) ────────────────────────────
    # Same argument as the block above, and it matters more here, because the
    # two ways this axis can be reported as a result while being an artefact are
    # both visible from these three numbers:
    #
    #   • EVERY ROW AT THE LADDER'S TOP means `max_fleet_ships` is BINDING, not
    #     bounding.  That happens when nothing pushes back on scale — a payload
    #     whose commodities have no `annual_market_kg` entry gets an infinite
    #     market, market saturation returns 1.0 forever, and the objective is
    #     then monotone in N.  Reporting the top rung of a monotone ladder is
    #     reporting where the loop stopped, and it is exactly the failure
    #     v1.14.0 closed.
    #   • EVERY ROW AT F = 1 means the fleet never wanted to grow, so the axis
    #     is costing runtime and buying nothing.
    if config.optimise_programme_scale and not config.model_rig_service_life:
        print("     ⚠️   optimise_programme_scale is ON but model_rig_service_life "
              "is OFF, so one rig serves any programme, nothing is ever "
              "concurrent, and market saturation cannot push back. The search "
              "is refused rather than run — it would report the ladder's top "
              "rung as a result. See programme_options().")
    elif config.optimise_programme_scale and "fleet_ships" in df.columns:
        f = df["fleet_ships"]
        at_cap = int((f >= config.max_fleet_ships).sum())
        print(f"     🚢  Programme chosen: fleet median {f.median():.0f} ship(s), "
              f"max {f.max():.0f}  |  N median {df['programme_missions'].median():.0f}, "
              f"max {df['programme_missions'].max():.0f}  |  "
              f"{int((f <= 1).sum()):,} single-ship")
        if "trips_per_ship" in df.columns:
            binds = df["rig_trip_limit_binds"]
            print(f"     🔧  Rig life: {df['trips_per_ship'].median():.0f} trips median "
                  f"(calendar cap {df['rig_trips_calendar_cap'].median():.0f})  |  "
                  f"cycle bound binds on {binds.mean():.1%} of rows")
        if at_cap:
            print(f"     ⚠️   {at_cap:,} row(s) ({at_cap/len(df):.1%}) sit AT "
                  f"max_fleet_ships = {config.max_fleet_ships}. The ladder is "
                  f"binding, not bounding — check those rows have a finite "
                  f"market before reading their N as an optimum.")

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
print(f"      ISRU return      : {'available where the rock supplies the propellant' if MASTER_CONFIG.calc.use_isru_return_propellant else 'off'}")
print(f"      Propellants      : {'flown hardware only' if MASTER_CONFIG.calc.operational_propellants_only else 'INCLUDING development / concept'}")
print(f"      Tank mass        : {'in the rocket equation' if MASTER_CONFIG.calc.model_tank_mass else 'off'}")
print(f"      Architecture     : {'searched per asteroid' if MASTER_CONFIG.calc.optimise_architecture_per_asteroid else 'fixed by config'}")
print(f"      NRE amortise     : over {MASTER_CONFIG.calc.nre_amortization_missions} mission(s)")
# Both of the next two default ON as of calc v1.17.0 and between them cost
# ~20x the runtime of the raw single-mission run most of the older tables in
# CLAUDE.md were measured at.  Print them so a long run is never a mystery.
print(f"      Beneficiation    : "
      + ("ON — concentrate, not run-of-mine ore (~7x runtime; False for the raw cell)"
         if MASTER_CONFIG.calc.use_beneficiation else
         "off — flying run-of-mine ore at bulk grade"))
print(f"      Programme        : "
      + (f"(fleet ≤ {MASTER_CONFIG.calc.max_fleet_ships}) x (campaigns/ship) searched; "
         f"N follows (~3x runtime)"
         if MASTER_CONFIG.calc.optimise_programme_scale else
         "fixed size (set calc.optimise_programme_scale to search it)"))
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
    print("  🚀  MASTER ASTEROID PROFITABILITY PIPELINE — v1.20.3")
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
