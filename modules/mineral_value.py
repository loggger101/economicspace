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
    #         • New apply_delivery_destination() step runs after merge_sources
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


CONFIG = MineralValueConfig()
os.makedirs(CONFIG.output_dir, exist_ok=True)

print(f"✅  Configuration loaded — output dir: {CONFIG.output_dir}")
print(f"    Active sources : "
      f"{', '.join(s for s, on in (('yfinance', CONFIG.use_yfinance), ('metals.dev', CONFIG.use_metals_api and CONFIG.metals_api_key != 'DEMO'), ('reference', CONFIG.use_reference_table)) if on)}")
print(f"    Price unit     : {CONFIG.PRICE_UNIT}  (every numeric price column ends with _usd_per_kg)")
print(f"    Delivery dest  : {CONFIG.delivery_destination}  "
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

    Applied after merge_sources so it overrides live quotes as well as
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

    # ── Step 3b — Reprice for the delivery destination ───────────────────────
    # Must follow the merge: at an in-space destination this overrides live
    # quotes too, since a terrestrial spot price is not what a commodity is
    # worth at a depot.
    catalog = apply_delivery_destination(catalog, config)

    # ── Step 4 — Validate ────────────────────────────────────────────────────
    catalog = validate(catalog)

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
