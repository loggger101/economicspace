# ==============================================================================
#  ASTEROID MINING PIPELINE — MODULE 1: CATALOG BUILDER
#  Google Colab compatible — runs top-to-bottom as a single cell.
#
#  Sources (only those that reliably return data from a Colab runtime):
#    • NASA JPL Small-Body Database (SBDB)            — primary backbone
#    • CDS VizieR WISE NEATM (Masiero 2011 + 2017)    — diameter / albedo
#
#  Previously attempted but removed because they were either unreachable from
#  the runtime (MP3C, PDS SBN, RELAB — DNS / firewall failures) or hung the
#  pipeline (VizieR Carry density / Bus-DeMeo taxonomy — astroquery + HTTP
#  both time out).  If those services become reachable again they can be added
#  back from git history.
#
#  Pipeline flow:
#    Fetch  →  Merge  →  Validate (failsafes)  →  Enrich  →  Export
# ==============================================================================


# ─────────────────────────────────────────────────────────────────────────────
# INSTALLATION
# ─────────────────────────────────────────────────────────────────────────────
#
# Auto-installs any missing packages.  Safe to re-run; skips already-installed.

import subprocess, sys

_REQUIRED_PKGS = [
    "requests", "pandas", "numpy", "astropy",
    "astroquery", "tqdm", "tabulate",
]
_missing = []
for _pkg in _REQUIRED_PKGS:
    try:
        __import__(_pkg)
    except ImportError:
        _missing.append(_pkg)

if _missing:
    print(f"📦  Installing: {_missing} …")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q"] + _missing
    )
    print("✅  Done — continue to Cell 2")
else:
    print("✅  All packages present")


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import io
import json
import os
import threading
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
from tqdm.auto import tqdm

warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", None)
pd.set_option("display.float_format", "{:.4f}".format)


@dataclass
class CatalogConfig:
    """Central configuration — edit these values to tune the pipeline."""

    # ── Required fields: an entry is DROPPED if any of these are null/invalid
    required_fields: List[str] = field(
        default_factory=lambda: [
            "designation",       # primary identifier
            "diameter_km",       # needed for value/mass calculations
            "semi_major_axis_au",# needed for coordinate mapping
        ]
    )

    # ── Source toggles (set False to skip a source)
    use_jpl:    bool = True
    use_vizier: bool = True

    # ── Fetch limits & timeouts
    jpl_limit:       int   = 5000   # max asteroids returned by JPL query
    request_timeout: int   = 30     # seconds per HTTP request
    request_delay:   float = 0.3    # polite delay between requests (seconds)

    # ── Quality thresholds
    min_diameter_km:       float = 0.001  # exclude objects smaller than this
    require_spectral_type: bool  = False  # True = strict; reject if no taxonomy

    # ── Output
    output_dir:        str = "/content/asteroid_pipeline"
    catalog_filename:  str = "asteroid_catalog.csv"
    rejected_filename: str = "rejected_entries.csv"
    log_filename:      str = "pipeline_log.txt"

    # ── Pipeline version (bump when you change the schema)
    pipeline_version: str = "1.0.0"


CONFIG = CatalogConfig()
os.makedirs(CONFIG.output_dir, exist_ok=True)

print(f"✅  Configuration loaded — output dir: {CONFIG.output_dir}")
print(f"    Required fields : {CONFIG.required_fields}")
print(f"    JPL fetch limit : {CONFIG.jpl_limit:,} asteroids")
print(f"    Strict taxonomy : {CONFIG.require_spectral_type}")


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
        "density_est_gcm3":  3.50,
        "metal_fraction":    0.40,
        "silicate_fraction": 0.40,
        "carbon_fraction":   0.05,
        "ice_fraction":      0.00,
        "notes": "Requires albedo to distinguish M, E, or P sub-type",
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
        "composition": "Xe-type (M-type analog): metallic, nickel-iron dominant",
        "minerals": ["nickel-iron", "troilite", "enstatite"],
        "density_est_gcm3":  5.00,
        "metal_fraction":    0.75,
        "silicate_fraction": 0.15,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "High-albedo X; likely metallic core fragment",
    },
    "Xk": {
        "group": "X-complex",
        "composition": "Xk-type: E-chondrite analog, enstatite dominant",
        "minerals": ["enstatite", "nickel-iron", "troilite"],
        "density_est_gcm3":  3.80,
        "metal_fraction":    0.50,
        "silicate_fraction": 0.40,
        "carbon_fraction":   0.01,
        "ice_fraction":      0.00,
        "notes": "E-chondrite analog; high albedo",
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
# JPL SBDB FETCHER  (primary source)
# ─────────────────────────────────────────────────────────────────────────────
JPL_SBDB_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"

# Physical + orbital fields available in the SBDB Query API.
# FIX: 'taxspec_type' is not a valid SBDB field — the correct names are
#      'spec_B' (Bus/Bus-DeMeo) and 'spec_T' (Tholen).
#      'density' is NOT in the query table; it comes only from the single-object
#      SBDB detail endpoint and must be filled from taxonomy estimates later.
_JPL_FIELDS = [
    "spkid",           # SPK kernel ID
    "pdes",            # primary provisional / numbered designation
    "name",            # name (if officially named)
    "neo",             # near-Earth object flag
    "pha",             # potentially hazardous flag
    "spec_B",          # Bus / Bus-DeMeo spectral classification  ← was taxspec_type
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
    "name":           "name",
    "spec_B":         "spectral_type",          # Bus-DeMeo is preferred primary
    "spec_T":         "spectral_type_tholen",   # kept as secondary
    "diameter":       "diameter_km",
    "diameter_sigma": "diameter_sigma_km",
    "albedo":         "albedo",
    "rot_per":        "rotation_period_h",
    # density not available from SBDB query table; filled from taxonomy in Cell 10
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
    Spectral taxonomy not available from SBDB query table is supplemented
    by VizieR (Cell 6b).  Returns EMPTY DataFrame on any unrecoverable error.
    """
    print("\n📡  [1/2] JPL Small-Body Database  (ssd-api.jpl.nasa.gov) …")

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
            resp = requests.get(
                JPL_SBDB_URL,
                params=params,
                timeout=config.request_timeout,
            )

            # On 400 print the API error message so future issues are diagnosable
            if resp.status_code == 400:
                try:
                    api_msg = resp.json().get("message", resp.text[:300])
                except Exception:
                    api_msg = resp.text[:300]
                print(f"     ⚠️  HTTP 400 on {attempt_name} — API says: {api_msg}")
                continue   # try next attempt

            resp.raise_for_status()
            payload = resp.json()

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
# CDS VIZIER FETCHER  (Colab-reliable supplement)
# ─────────────────────────────────────────────────────────────────────────────
#
# CDS VizieR (Strasbourg) is reliably accessible from Colab and hosts the same
# underlying datasets that PDS SBN and RELAB serve:
#   • WISE NEATM 2011  (Masiero, J/ApJS/202/19)  — diameters + albedos
#   • WISE NEATM 2017  (Masiero, J/AJ/152/63)    — expanded diameter/albedo coverage
#   • Carry 2012       (J/P&SS/73/98)             — measured bulk densities
#   • Bus-DeMeo 2009   (J/Icarus/202/160)         — spectral taxonomy
#
# FIX vs previous version: use query_constraints() NOT get_catalogs().
# get_catalogs() returns a ReadMe/summary table as result[0]; query_constraints()
# with explicit column names targets the asteroid data table directly.

_VIZIER_QUERIES = [
    {
        # Masiero+2011 "Main Belt Asteroids with WISE/NEOWISE. I.": ApJ 741, 68.
        # The previous ID 'J/ApJS/202/19' returns SDSS-style photometric data
        # (rmag/imag/zmag) and is the WRONG catalog.  The correct VizieR ID is
        # 'J/ApJ/741/68'.  Masiero 2012 (Trojans) and 2014 added as size fallbacks.
        "ids":     ["J/ApJ/741/68", "J/ApJ/759/14", "J/ApJ/791/121"],
        "name":    "WISE NEATM 2011",
        "rename": {
            "num":    "designation",
            "name":   "name",
            "diam":   "diameter_km",
            "e_diam": "diameter_sigma_km",
            "pv":     "albedo",
            "e_pv":   "albedo_sigma",
            "pir":    "albedo_ir",
        },
    },
    {
        "ids":     ["J/AJ/152/63"],
        "name":    "WISE NEATM 2017",
        "rename": {
            "num":    "designation",
            "name":   "name",
            "diam":   "diameter_km",
            "e_diam": "diameter_sigma_km",
            "pv":     "albedo",
        },
    },
]

# Order matters: tried left-to-right when 'designation' is absent after rename.
_VIZIER_DESIG_FALLBACK = (
    "num", "number", "n_", "id", "ast", "_1",
    "name", "object", "asteroid", "des", "pdes", "target",
)

_VIZIER_STD_COLS = {
    "designation", "name", "spectral_type",
    "diameter_km", "diameter_sigma_km",
    "albedo", "albedo_sigma",
    "density_gcm3", "density_sigma_gcm3",
}

_VIZIER_NUMERIC_COLS = [
    "diameter_km", "diameter_sigma_km", "albedo",
    "albedo_sigma", "density_gcm3", "density_sigma_gcm3",
]


def _vizier_normalise_designation(s: pd.Series) -> pd.Series:
    """
    Coerce a VizieR designation/name column to JPL-compatible designations.

    Handles forms like '(1) Ceres', '(433)Eros', '00001', '2024 BX1', 'Ceres'.
    Prefers the leading numeric (parenthesised or plain) when present, since
    that matches JPL SBDB's `pdes` field; otherwise keeps the bare name.
    """
    raw = s.astype(str).str.strip()
    # Strip leading parens around a number \u2014 '(1) Ceres' \u2192 '1 Ceres'
    cleaned = raw.str.replace(r"^\s*\(\s*(\d+)\s*\)\s*", r"\1 ", regex=True)
    # Pull leading integer if present
    leading_num = cleaned.str.extract(r"^(\d+)", expand=False)
    # If no leading integer, fall back to the trimmed name (handles '2024 BX1' too)
    result = leading_num.where(leading_num.notna(), cleaned)
    return (
        result.str.strip()
        .str.lstrip("0")
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )


# Primary terms = strong evidence the table holds asteroid physical / taxonomic
# data.  A table with ZERO primary matches is rejected even if it has rows —
# without this, an SDSS-style photometry sub-table (rmag/imag/zmag/...) was being
# preferred over the actual NEATM data for catalogs with multiple tables.
_VIZIER_PRIMARY_TERMS = (
    "diam", "albedo", "pv", "density", "rho",
    "class", "tax", "spec", "tholen", "smass", "demeo", "bus",
)
# Secondary terms break ties between tables that all have primary data.
_VIZIER_SECONDARY_TERMS = (
    "name", "num", "object", "asteroid", "target",
    "mag", "period", "rot", "mass", "type",
)


def _pick_vizier_data_table(tables, short_name: str) -> Optional[pd.DataFrame]:
    """
    Pick the best asteroid-data table from a VizieR TableList.

    A table is rejected unless at least ONE column name matches a primary
    asteroid-data term (diameter / albedo / density / taxonomy / etc.).  Among
    qualifying tables, rank by (primary_score, secondary_score, row_count).
    """
    candidates: List[Tuple[int, int, int, pd.DataFrame]] = []
    for tbl in tables:
        try:
            df = tbl.to_pandas()
        except Exception:
            continue
        if df.empty:
            continue
        df.columns = [
            c.split("(")[0].split("[")[0].strip().lower() for c in df.columns
        ]
        primary = sum(
            1 for c in df.columns if any(t in c for t in _VIZIER_PRIMARY_TERMS)
        )
        if primary == 0:
            continue  # not an asteroid-physics table (e.g. stellar photometry)
        secondary = sum(
            1 for c in df.columns if any(t in c for t in _VIZIER_SECONDARY_TERMS)
        )
        candidates.append((primary, secondary, len(df), df))

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x[0], -x[1], -x[2]))
    return candidates[0][3]


# Mirrors of CDS VizieR for the direct-HTTP fallback. Tried in order; first
# mirror to return a parseable TSV wins.  Multi-mirror coverage matters because
# the Strasbourg primary occasionally rate-limits or returns blank pages.
_VIZIER_HTTP_MIRRORS = (
    "https://vizier.cds.unistra.fr",
    "https://vizier.cfa.harvard.edu",
    "https://vizier.nao.ac.jp",
)


def _parse_vizier_tsv(text: str) -> Optional[pd.DataFrame]:
    """
    Parse VizieR's asu-tsv response.  Format:
        # metadata lines (RESOURCE, Name, Title, etc.)
        # ---Table:  J/.../tableN
        # ----------------
        col1<TAB>col2<TAB>col3        <- header
        unit1<TAB>unit2<TAB>unit3     <- unit row (optional)
        ---<TAB>---<TAB>---           <- dash separator (optional)
        data1<TAB>data2<TAB>data3     <- data rows
        ...
    """
    lines = text.splitlines()

    # Find header line: first non-comment, non-blank, tab-bearing line
    header_idx = -1
    for i, line in enumerate(lines):
        if not line.strip() or line.startswith("#"):
            continue
        if "\t" in line:
            header_idx = i
            break
    if header_idx < 0:
        return None

    header = [c.strip() for c in lines[header_idx].split("\t")]

    # Skip unit row(s) and dash separator(s) after the header.
    data_start = header_idx + 1
    while data_start < len(lines):
        ln = lines[data_start]
        if not ln.strip() or ln.startswith("#"):
            data_start += 1
            continue
        fields = ln.split("\t")
        # Dash separator: every non-empty field is just hyphens
        if all((not f.strip()) or set(f.strip()) <= {"-"} for f in fields):
            data_start += 1
            continue
        break

    data_lines = [
        l for l in lines[data_start:]
        if l.strip() and not l.startswith("#")
    ]
    if not data_lines:
        return None

    try:
        csv_text = "\t".join(header) + "\n" + "\n".join(data_lines)
        df = pd.read_csv(
            io.StringIO(csv_text),
            sep="\t",
            engine="python",
            on_bad_lines="skip",
            dtype=str,        # keep raw; coerce numerics later
        )
    except Exception:
        return None

    if df.empty:
        return None

    # Drop any residual dash-only rows that slipped through
    first_col = df.columns[0]
    mask = df[first_col].astype(str).str.fullmatch(r"-+\s*", na=False)
    df = df[~mask].reset_index(drop=True)
    return df if not df.empty else None


def _vizier_fetch_via_http(
    cat_id: str, max_rows: int = 5000, timeout: float = 30.0,
) -> Optional[pd.DataFrame]:
    """
    Fetch a VizieR catalog via the public asu-tsv endpoint, bypassing astroquery.

    Astroquery has been observed to hang indefinitely on certain catalog IDs
    (e.g. those containing '&' or '+') and to return empty TableLists for
    others; a plain HTTP GET is more predictable and supports the same
    catalog-name parameter.  Tries multiple VizieR mirrors in order.
    """
    params = {
        "-source":  cat_id,
        "-out":     "*",
        "-out.max": str(max_rows),
    }
    for base in _VIZIER_HTTP_MIRRORS:
        url = f"{base}/viz-bin/asu-tsv"
        try:
            r = requests.get(url, params=params, timeout=timeout)
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError):
            continue
        except Exception:
            continue
        if r.status_code != 200 or len(r.text) < 50:
            continue
        df = _parse_vizier_tsv(r.text)
        if df is not None and not df.empty:
            return df
    return None


def _call_with_timeout(fn, timeout_s: float):
    """
    Run `fn()` in a daemon thread and raise TimeoutError if it doesn't return
    within `timeout_s` seconds.  Needed because astroquery's `timeout=` argument
    does not enforce a hard cap on the underlying SSL read — observed in
    production hanging indefinitely on get_catalogs('J/P&SS/73/98').
    """
    box: Dict[str, object] = {"value": None, "exc": None, "done": False}

    def runner():
        try:
            box["value"] = fn()
        except BaseException as e:
            box["exc"] = e
        finally:
            box["done"] = True

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join(timeout_s)
    if not box["done"]:
        # Thread is still running; we orphan it (daemon) and bail.
        raise TimeoutError(f"call exceeded {timeout_s:.0f}s")
    if box["exc"] is not None:
        raise box["exc"]  # type: ignore[misc]
    return box["value"]


def _df_has_primary_columns(df: pd.DataFrame) -> bool:
    """True if the dataframe has at least one asteroid-primary column."""
    return any(
        any(t in str(c).lower() for t in _VIZIER_PRIMARY_TERMS)
        for c in df.columns
    )


def _vizier_fetch_best_table(
    v, cat_ids: List[str], short_name: str, per_call_timeout: float = 30.0
) -> Optional[pd.DataFrame]:
    """
    Try each candidate catalog ID using three independent methods:
      1. astroquery's get_catalogs        — usually fastest when it works
      2. astroquery's query_constraints   — different code path, sometimes works
                                            when get_catalogs returns empty
      3. direct HTTP to VizieR's asu-tsv  — bypasses astroquery entirely; the
                                            only reliable option for catalogs
                                            that hang or return empty above

    Enforces a per-call wall-clock timeout (orphans hung threads).  Returns the
    FIRST DataFrame the strict picker / primary-column check accepts, falling
    through to the next method/ID otherwise.
    """
    for cid in cat_ids:
        # Astroquery methods return TableList; HTTP returns DataFrame directly.
        # Wrapping in a uniform "returns a DataFrame or None" interface.
        def via_get_catalogs(c=cid):
            tables = v.get_catalogs(c)
            if tables is None or len(tables) == 0:
                return None
            return _pick_vizier_data_table(tables, short_name)

        def via_query_constraints(c=cid):
            tables = v.query_constraints(catalog=c)
            if tables is None or len(tables) == 0:
                return None
            return _pick_vizier_data_table(tables, short_name)

        def via_direct_http(c=cid):
            df = _vizier_fetch_via_http(
                c, max_rows=5000, timeout=per_call_timeout,
            )
            if df is None:
                return None
            # Normalise column names so the primary-column check matches
            df.columns = [
                str(col).split("(")[0].split("[")[0].strip().lower()
                for col in df.columns
            ]
            return df if _df_has_primary_columns(df) else None

        methods = (
            ("get_catalogs",      via_get_catalogs),
            ("query_constraints", via_query_constraints),
            ("direct_http",       via_direct_http),
        )

        for method_name, method in methods:
            try:
                df = _call_with_timeout(method, per_call_timeout)
            except TimeoutError:
                print(f"     ⏱  {short_name}: {method_name}('{cid}') timed out after {per_call_timeout:.0f}s")
                continue
            except Exception as exc:
                print(f"     …  {short_name}: {method_name}('{cid}') raised {type(exc).__name__}: {str(exc)[:90]}")
                continue

            if df is None or df.empty:
                continue

            # Announce when we had to fall back from the primary route
            if cid != cat_ids[0] or method_name != "get_catalogs":
                marker = "\U0001f310" if method_name == "direct_http" else "\U0001f504"
                print(f"     {marker}  {short_name}: using '{cid}' via {method_name}")
            return df
    return None


def fetch_vizier(config: CatalogConfig) -> pd.DataFrame:
    """
    Fetch asteroid physical properties and taxonomy from CDS VizieR.

    Strategy:
      1. Call Vizier.get_catalogs(cat_id) to retrieve all tables in the catalog
         (this works for catalogs that have no usable constraint column, where
         the previous query_constraints({}) call silently returned nothing).
      2. Iterate through every table and pick the largest one whose columns
         look astronomically relevant (skips ReadMe/notes tables).
      3. Apply per-catalog rename + a generous designation fallback list
         (now includes 'name', 'object', 'asteroid', 'target').
      4. Normalise designations so VizieR's '(1) Ceres' matches JPL's '1'.

    Returns EMPTY DataFrame if astroquery is unavailable or all catalogs fail.
    """
    print("\n\U0001f4e1  [2/2] CDS VizieR WISE NEATM  (vizier.cds.unistra.fr) \u2026")

    try:
        from astroquery.vizier import Vizier
    except ImportError:
        print("     \u26a0\ufe0f  astroquery not installed \u2014 run Cell 1 to auto-install")
        return pd.DataFrame()

    frames: List[pd.DataFrame] = []

    for q in _VIZIER_QUERIES:
        cat_ids    = q["ids"]
        short_name = q["name"]
        try:
            v = Vizier(
                columns=["**"],            # ** = ALL data columns, not just default
                row_limit=config.jpl_limit,
                timeout=60,
            )
            df = _vizier_fetch_best_table(
                v, cat_ids, short_name, per_call_timeout=30.0,
            )

            if df is None:
                print(f"     \u26a0\ufe0f  {short_name}: no usable asteroid table found (tried IDs: {cat_ids})")
                continue

            # DEBUG: log actual columns so future column-name drift is diagnosable
            print(f"     \U0001f50e  {short_name} columns: {list(df.columns)[:12]}")

            # Apply catalog-specific rename map
            rename_applied: Dict[str, str] = {}
            for src_col, dst_col in q["rename"].items():
                match = next(
                    (c for c in df.columns
                     if c == src_col or c.startswith(src_col + "_") or c == src_col + "."),
                    None,
                )
                if match and match not in rename_applied and dst_col not in rename_applied.values():
                    rename_applied[match] = dst_col
            df = df.rename(columns=rename_applied)

            # Generous designation fallback hunt
            if "designation" not in df.columns:
                for cand in _VIZIER_DESIG_FALLBACK:
                    if cand in df.columns:
                        df["designation"] = df[cand]
                        break

            if "designation" not in df.columns:
                print(f"     \u26a0\ufe0f  {short_name}: cannot identify designation \u2014 skipped")
                continue

            # Normalise designation so '(1) Ceres' matches JPL's '1'
            df["designation"] = _vizier_normalise_designation(df["designation"])
            df = df.dropna(subset=["designation"])
            if df.empty:
                print(f"     \u26a0\ufe0f  {short_name}: no valid designations after cleaning")
                continue

            # Keep only schema-standard columns
            df = df[[c for c in df.columns if c in _VIZIER_STD_COLS]].copy()

            # Coerce numeric columns
            for col in _VIZIER_NUMERIC_COLS:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            src_tag = f"source_vizier_{cat_ids[0].replace('/', '_').replace('&', '').replace('+', '')}"
            df[src_tag] = True
            frames.append(df)

            # Detailed report on what data arrived
            n_diam = int(df["diameter_km"].notna().sum())  if "diameter_km"   in df.columns else 0
            n_alb  = int(df["albedo"].notna().sum())        if "albedo"        in df.columns else 0
            n_rho  = int(df["density_gcm3"].notna().sum())  if "density_gcm3" in df.columns else 0
            n_tax  = int(df["spectral_type"].notna().sum()) if "spectral_type" in df.columns else 0
            print(f"     \u2705  {short_name}: {len(df):,} entries  "
                  f"(diam={n_diam:,}, albedo={n_alb:,}, density={n_rho}, taxonomy={n_tax})")

        except Exception as exc:
            print(f"     \u26a0\ufe0f  {short_name} ({cat_ids[0]}) failed: {type(exc).__name__}: {exc}")

    if not frames:
        print("     \u2139\ufe0f  No VizieR catalogs retrieved \u2014 continuing without them")
        return pd.DataFrame()

    # Merge all VizieR frames on designation (fill-in, no overwrite)
    merged = frames[0]
    for extra in frames[1:]:
        fill_cols = [
            c for c in extra.columns
            if c not in ("designation",) and not c.startswith("source_")
        ]
        extra_slim = extra[["designation"] + fill_cols].copy()
        extra_slim.columns = ["designation"] + [f"_{c}__v" for c in fill_cols]
        merged = merged.merge(extra_slim, on="designation", how="outer")
        for col in fill_cols:
            src = f"_{col}__v"
            if src not in merged.columns:
                continue
            if col in merged.columns:
                merged[col] = merged[col].fillna(merged[src])
                merged.drop(columns=[src], inplace=True)
            else:
                merged.rename(columns={src: col}, inplace=True)

    merged["source_vizier"] = True
    print(f"     \u2705  VizieR combined: {len(merged):,} records, "
          f"{len(merged.columns)} columns")
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────
def _normalise_designation_key(s: pd.Series) -> pd.Series:
    """
    Aggressive normalisation used ONLY for duplicate detection.

    Collapses '00001', '1', ' 1 ', '(1)', '1 Ceres' all to '1' so the same
    asteroid stored under different surface forms in different sources is
    recognised as a single entity.
    """
    return (
        s.astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"^\s*\(\s*(\d+)\s*\).*$", r"\1", regex=True)  # '(1) Ceres' → '1'
        .str.extract(r"^(\d+)|^(.+?)$", expand=False)               # leading int or bare
        .bfill(axis=1).iloc[:, 0]                                    # collapse two-col result
        .str.strip()
        .str.lstrip("0")
        .replace({"": pd.NA, "NAN": pd.NA, "NONE": pd.NA, "0": pd.NA})
    )


def deduplicate_catalog(
    df: pd.DataFrame,
    key: str = "designation",
    label: str = "catalog",
) -> pd.DataFrame:
    """
    Remove duplicate rows by normalised `key`, keeping the row with the most
    populated columns within each group (i.e. the most-complete record wins,
    not arbitrarily the first one).  Reports counts so the caller can see what
    was collapsed.

    Idempotent — safe to call multiple times across the pipeline.
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
def merge_sources(
    jpl_df:    pd.DataFrame,
    vizier_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge JPL and VizieR DataFrames into a single catalog.

    Strategy:
      - JPL SBDB is the primary backbone (most complete orbital coverage).
      - VizieR ONLY fills in columns that are NULL in the backbone — never
        overwrites existing values.
      - Merge key is 'designation' (normalised to UPPERCASE, stripped).
    """
    print("\n🔀  Merging sources …")

    sources = {"JPL": jpl_df, "VizieR": vizier_df}
    available = {k: v for k, v in sources.items() if not v.empty}

    if not available:
        print("     ❌  No data from any source — aborting merge")
        return pd.DataFrame()

    # Normalise designation for joining, then dedupe each source on its own
    # (defends against duplicates introduced upstream in the fetchers — e.g.
    # WISE 2011 + WISE 2017 sharing some asteroids in the VizieR combined frame).
    for name, df in available.items():
        if "designation" in df.columns:
            df["designation"] = (
                df["designation"]
                .astype(str)
                .str.strip()
                .str.upper()
                .replace({"NAN": np.nan, "NONE": np.nan, "": np.nan})
            )
        available[name] = deduplicate_catalog(df, key="designation", label=name)

    # Use JPL as backbone if available, otherwise the first available source
    if "JPL" in available:
        merged = available.pop("JPL").copy()
    else:
        first_key = next(iter(available))
        merged = available.pop(first_key).copy()
        print(f"     ⚠️  JPL unavailable — using {first_key} as backbone")

    # Fill gaps from supplementary sources
    for src_name, supp in available.items():
        if "designation" not in supp.columns:
            print(f"     ⚠️  {src_name} has no 'designation' column — skipped in merge")
            continue

        fill_cols = [
            c for c in supp.columns
            if c not in ("designation",) and not c.startswith("source_")
        ]

        # Rename supp columns to avoid clobbering backbone
        supp_renamed = supp[["designation"] + fill_cols].copy()
        supp_renamed.columns = (
            ["designation"] + [f"_{c}__{src_name.lower()}" for c in fill_cols]
        )

        merged = merged.merge(supp_renamed, on="designation", how="left")

        # Fill NaNs in backbone from supplementary
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

        print(f"     ✔   Merged {src_name}: {len(supp):,} supplement records")

    # De-duplicate on designation (keep first / most complete row)
    before = len(merged)
    merged = merged.drop_duplicates(subset=["designation"], keep="first")
    dupes = before - len(merged)
    if dupes:
        print(f"     🗑   Removed {dupes:,} duplicate designations")

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
      1. No designation                → drop
      2. No diameter, or diameter ≤ 0 → drop
      3. Diameter < min_diameter_km   → drop
      4. No semi-major axis (a)       → drop
      5. If strict mode: no spectral type → drop

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

    # ── 2. Diameter required and positive ────────────────────────────────────
    if "diameter_km" in df.columns:
        diam = pd.to_numeric(df["diameter_km"], errors="coerce")
        bad  = diam.isna() | (diam <= 0)
        log.append(_log_rejection(df, bad & valid_mask, "Missing or non-positive diameter"))
        valid_mask &= ~bad
    else:
        # No diameter column at all
        log.append({"reason": "diameter_km column absent", "rejected_count": int(valid_mask.sum()), "examples": "N/A"})
        valid_mask[:] = False

    # ── 3. Minimum diameter threshold ────────────────────────────────────────
    if "diameter_km" in df.columns:
        diam = pd.to_numeric(df["diameter_km"], errors="coerce")
        bad  = diam < config.min_diameter_km
        log.append(_log_rejection(df, bad & valid_mask, f"diameter < {config.min_diameter_km} km"))
        valid_mask &= ~bad

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
    if config.require_spectral_type:
        if "spectral_type" in df.columns:
            bad = df["spectral_type"].isna() | (df["spectral_type"].astype(str).str.strip() == "")
            log.append(_log_rejection(df, bad & valid_mask, "Missing spectral type (strict mode ON)"))
            valid_mask &= ~bad
        else:
            log.append({"reason": "spectral_type column absent (strict mode ON)",
                        "rejected_count": int(valid_mask.sum()), "examples": "N/A"})
            valid_mask[:] = False

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
      1. Normalise spectral_type strings.
      2. Where spectral_type is absent but albedo is known, infer a coarse type.
      3. Look up all TAXONOMY_COMPOSITION fields for each type.
      4. Fill density_gcm3 from taxonomy estimate where no measurement exists.
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
    df["spectral_type_inferred"] = False

    # ── 2. Infer from albedo where type is missing ────────────────────────────
    if "albedo" in df.columns:
        alb = pd.to_numeric(df["albedo"], errors="coerce")
        infer_mask = df["spectral_type"].isna() & alb.notna()

        def _infer_from_albedo(a: float) -> str:
            """Coarse spectral-type inference from geometric albedo."""
            if a < 0.10:  return "C"    # dark  → carbonaceous
            if a < 0.20:  return "S"    # moderate → stony
            if a < 0.35:  return "S"
            return "V"                  # bright → basaltic or E-type

        df.loc[infer_mask, "spectral_type"] = alb[infer_mask].apply(_infer_from_albedo)
        df.loc[infer_mask, "spectral_type_inferred"] = True
        n_inf = int(infer_mask.sum())
        if n_inf:
            print(f"     🔎  Spectral type inferred from albedo for {n_inf:,} entries")

    # ── 3. Look up composition fields ────────────────────────────────────────
    comp_fields = [
        "group", "composition", "density_est_gcm3",
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
    if "diameter_km" in df.columns:
        diam_m   = pd.to_numeric(df["diameter_km"], errors="coerce") * 1_000.0
        rho_kgm3 = pd.to_numeric(df["density_gcm3"], errors="coerce") * 1_000.0
        df["estimated_mass_kg"] = (4 / 3) * np.pi * (diam_m / 2) ** 3 * rho_kgm3
    else:
        df["estimated_mass_kg"] = np.nan

    return df


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────
def build_catalog(config: CatalogConfig = CONFIG) -> pd.DataFrame:
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
    jpl_df    = fetch_jpl_sbdb(config) if config.use_jpl    else pd.DataFrame()
    vizier_df = fetch_vizier(config)   if config.use_vizier else pd.DataFrame()

    source_counts = {
        "JPL SBDB": len(jpl_df),
        "VizieR":   len(vizier_df),
    }
    print(f"\n     Source summary: {source_counts}")

    # ── Step 2 — Merge ────────────────────────────────────────────────────────
    merged = merge_sources(jpl_df, vizier_df)
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
def lookup_asteroid(catalog: pd.DataFrame, query: str) -> pd.DataFrame:
    """
    Quick lookup by designation or name (case-insensitive substring match).

    Usage:
        lookup_asteroid(catalog, "Ceres")
        lookup_asteroid(catalog, "2024 BX1")
    """
    q = query.strip().upper()
    mask = (
        catalog["designation"].astype(str).str.upper().str.contains(q, na=False)
    )
    if "name" in catalog.columns:
        mask |= catalog["name"].astype(str).str.upper().str.contains(q, na=False)

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
print("    lookup_asteroid(catalog, 'Ceres')")
print("    filter_by_region(catalog, 2.0, 3.3)   # main-belt slice")
print("    filter_by_spectral_group(catalog, 'X-complex')  # metallic")


# ─────────────────────────────────────────────────────────────────────────────
# RUN & PREVIEW
# ─────────────────────────────────────────────────────────────────────────────
# ┌─────────────────────────────────────────────────────────────────┐
# │  OPTIONAL TWEAKS — edit CONFIG values here before running       │
# │  CONFIG.jpl_limit = 500      # quick test run                   │
# │  CONFIG.require_spectral_type = True   # strict mode            │
# └─────────────────────────────────────────────────────────────────┘

catalog = build_catalog(CONFIG)

if not catalog.empty:

    # ── Column preview ─────────────────────────────────────────────────────────
    PREVIEW_COLS = [
        "designation", "name", "spectral_type", "comp_group",
        "diameter_km", "density_gcm3", "density_measured",
        "albedo", "semi_major_axis_au", "eccentricity", "inclination_deg",
        "comp_composition", "estimated_mass_kg",
    ]
    show = [c for c in PREVIEW_COLS if c in catalog.columns]

    print(f"\n{'='*65}")
    print(f"  📋  CATALOG PREVIEW  —  first 10 entries")
    print(f"{'='*65}")
    print(catalog[show].head(10).to_string(index=False))

    # ── Spectral distribution ─────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  📊  SPECTRAL TYPE DISTRIBUTION")
    print(f"{'='*65}")
    if "spectral_type" in catalog.columns:
        dist = catalog["spectral_type"].value_counts()
        bar_scale = max(dist.values) / 40 if len(dist) else 1
        for spec, n in dist.head(20).items():
            bar = "█" * max(1, int(n / bar_scale))
            print(f"  {str(spec):8s} {bar:<42s} {n:>6,}")
        if len(dist) > 20:
            print(f"  … and {len(dist)-20} more types")

    # ── Size histogram ────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  📏  SIZE DISTRIBUTION")
    print(f"{'='*65}")
    if "diameter_km" in catalog.columns:
        d = pd.to_numeric(catalog["diameter_km"], errors="coerce")
        bins   = [(0, 0.1), (0.1, 1), (1, 10), (10, 100), (100, 500), (500, 1e9)]
        labels = ["<0.1 km", "0.1–1 km", "1–10 km", "10–100 km", "100–500 km", ">500 km"]
        for (lo, hi), label in zip(bins, labels):
            n = int(((d >= lo) & (d < hi)).sum())
            bar = "█" * min(int(n / max(1, len(catalog)) * 50), 50)
            print(f"  {label:12s} {bar:<52s} {n:,}")

    # ── Orbital regions ───────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  🌌  ORBITAL REGION DISTRIBUTION")
    print(f"{'='*65}")
    if "semi_major_axis_au" in catalog.columns:
        a = pd.to_numeric(catalog["semi_major_axis_au"], errors="coerce")
        regions = [
            (0.0,  1.0,  "Near-Sun / Aten class"),
            (1.0,  1.7,  "NEA / Apollo / Amor"),
            (1.7,  2.5,  "Inner Main Belt"),
            (2.5,  3.3,  "Middle Main Belt"),
            (3.3,  4.0,  "Outer Main Belt"),
            (4.0,  5.4,  "Jupiter Trojans region"),
            (5.4, 30.1,  "Outer solar system"),
            (30.1, 1e9,  "Trans-Neptunian / KBO"),
        ]
        for lo, hi, name in regions:
            n = int(((a >= lo) & (a < hi)).sum())
            if n > 0:
                print(f"  {name:30s} {n:>8,}  ({n/len(catalog)*100:4.1f}%)")

    # ── Composition group summary ─────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  🧪  COMPOSITION GROUP BREAKDOWN")
    print(f"{'='*65}")
    if "comp_group" in catalog.columns:
        grp = catalog["comp_group"].value_counts()
        for g, n in grp.items():
            print(f"  {str(g):20s} {n:>8,}  ({n/len(catalog)*100:4.1f}%)")

    # ── Data completeness report ──────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  📈  DATA COMPLETENESS")
    print(f"{'='*65}")
    key_cols = [
        "designation", "name", "spectral_type", "diameter_km",
        "albedo", "density_gcm3", "density_measured",
        "semi_major_axis_au", "eccentricity", "inclination_deg",
        "comp_composition", "estimated_mass_kg",
    ]
    for col in key_cols:
        if col in catalog.columns:
            pct = catalog[col].notna().mean() * 100
            bar = "█" * int(pct / 2)
            print(f"  {col:30s} {bar:<50s} {pct:5.1f}%")
