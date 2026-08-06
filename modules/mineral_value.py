# -*- coding: utf-8 -*-
"""mineral_value — Module 2 of the Asteroid Profitability Pipeline.

Builds a catalog of CURRENT market prices and bulk DENSITIES for every
mineral / element that appears in Module 1's TAXONOMY_COMPOSITION table.
Downstream profitability scoring multiplies asteroid mass × composition
fraction × mineral_price to estimate $/asteroid.

Pipeline flow:
    Fetch live prices  →  Merge with reference table  →  Validate  →  Export

Active sources:
    • yfinance  (Yahoo Finance)    — live futures prices for gold (GC=F),
                                     silver (SI=F), platinum (PL=F),
                                     palladium (PA=F), copper (HG=F).
                                     Free, no API key.
    • USGS Mineral Commodity      — curated fallback prices for the LME
      Summaries + LME reference     metals (Ni, Co, Al, Pb, Zn, Sn, Fe ore)
                                    and the trace PGMs that yfinance does
                                    not expose (Rh, Ir, Ru, Os).  These are
                                    stamped with `reference_date` so the
                                    user knows how stale they are.
    • In-pipeline mineralogy      — densities, chemical formulas, and the
      reference (Klein & Hurlbut    relevant elemental yield fractions for
       "Manual of Mineralogy"       every mineral named in the Module 1
       + Mindat / Webmineral)       taxonomy table.  Physical constants —
                                    they do not change between runs.

Adding a new mineral / element:
    Drop a new row into MINERAL_REFERENCE below.  The fetcher / merger
    work uniformly across however many entries you add.
"""

# ─────────────────────────────────────────────────────────────────────────────
# INSTALLATION
# ─────────────────────────────────────────────────────────────────────────────
# Auto-installs missing packages.  Safe to re-run.

# Windows consoles default to cp1252, which cannot encode the emoji used in
# this file's progress output -- force UTF-8 before anything prints.
import sys as _sys
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import subprocess, sys

_REQUIRED_PKGS = ["requests", "pandas", "numpy", "yfinance"]
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
    print("✅  Install complete")
else:
    print("✅  All packages present")


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import json
import os
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

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
    pipeline_version: str = "1.1.5"

    # ─── DISPLAY ─────────────────────────────────────────────────────────────
    preview_rows: int = 20


CONFIG = MineralValueConfig()
os.makedirs(CONFIG.output_dir, exist_ok=True)

print(f"✅  Configuration loaded — output dir: {CONFIG.output_dir}")
print(f"    Active sources : "
      f"{', '.join(s for s, on in (('yfinance', CONFIG.use_yfinance), ('metals.dev', CONFIG.use_metals_api and CONFIG.metals_api_key != 'DEMO'), ('reference', CONFIG.use_reference_table)) if on)}")
print(f"    Price unit     : {CONFIG.PRICE_UNIT}  (every numeric price column ends with _usd_per_kg)")


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
        "ref_price_usd_per_kg":  4_250.0,        # Falcon 9 reusable $/kg-to-LEO
        "ref_price_date":        _REF_PRICE_DATE,
        "notes":                 "Priced as the cost-to-LEO of launching an equivalent "
                                 "water mass from Earth — i.e. the SAVINGS from "
                                 "sourcing water in-space rather than launching it.  "
                                 "$4,250/kg matches Module 3 v1.2.4 Falcon 9 reusable "
                                 "$/kg-to-LEO ($4,253).  For TLI / cislunar customers "
                                 "the value would be 2-4× higher (launch cost to "
                                 "those orbits is much greater).",
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
        print("\n🔗  metals.dev — skipped (no API key set; edit CONFIG.metals_api_key)")
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

    rows = []
    for entry in MINERAL_REFERENCE:
        rows.append({
            "name":                 entry["name"],
            "kind":                 entry["kind"],
            "formula":              entry["formula"],
            "density_gcm3":         entry["density_gcm3"],
            "ref_price_usd_per_kg":     entry.get("ref_price_usd_per_kg"),
            "ref_price_date":       entry.get("ref_price_date"),
            "ref_price_source":     "USGS/LME/mineralogy reference",
            "notes":                entry.get("notes", ""),
            "yields_json":          json.dumps(entry.get("yields", {})),
        })

    df = pd.DataFrame(rows)
    print(f"     ✅  {len(df)} reference rows loaded")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MERGE
# ─────────────────────────────────────────────────────────────────────────────
def merge_sources(
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
def validate(catalog: pd.DataFrame) -> pd.DataFrame:
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
    config: MineralValueConfig = CONFIG,
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
    catalog = merge_sources(reference, live_frames)

    # ── Step 4 — Validate ────────────────────────────────────────────────────
    catalog = validate(catalog)

    # ── Step 5 — Metadata + sort ─────────────────────────────────────────────
    catalog["catalog_date"]     = t0.strftime("%Y-%m-%d")
    catalog["pipeline_version"] = config.pipeline_version

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


# ─────────────────────────────────────────────────────────────────────────────
# RUN & PREVIEW
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    catalog = build_mineral_value_catalog(CONFIG)

    if not catalog.empty:

        PREVIEW_COLS = [
            "name", "kind", "formula", "density_gcm3",
            "price_usd_per_kg", "price_basis",
            "live_price_source", "live_price_date",
            "ref_price_date",
        ]
        show = [c for c in PREVIEW_COLS if c in catalog.columns]

        print(f"\n{'='*75}")
        print(f"  📋  MINERAL VALUE CATALOG — first {CONFIG.preview_rows} entries")
        print(f"{'='*75}")
        print(catalog[show].head(CONFIG.preview_rows).to_string(index=False))

        # ── Mineral implied-value cross-check ─────────────────────────────────────
        print(f"\n{'='*75}")
        print("  🧪  MINERAL IMPLIED VALUE (USD/kg, computed from elemental yields)")
        print(f"{'='*75}")
        for _, r in catalog[catalog["kind"] == "mineral"].iterrows():
            implied = mineral_to_element_value(catalog, r["name"])
            if implied is None:
                print(f"  {r['name']:18s} —  (no yields defined)")
            else:
                print(f"  {r['name']:18s}  implied ≈ {implied:>14,.2f}  USD/kg")
