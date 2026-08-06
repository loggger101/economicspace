# -*- coding: utf-8 -*-
"""transportation — Module 3 of the Asteroid Profitability Pipeline.

Builds a reference catalog of every cost that sits between "asteroid in
space" and "refined material delivered to its market":

    Launch  +  Transit propellant  +  Mining ops  +  Return  +  Contingency

Each cost is normalised to a comparable unit so Module 4 can compose them:

    • Launch        →  USD per kg of payload to destination
    • Propellant    →  USD per kg, USD per L, AND USD per (kg·Δv) — the
                       rocket-equivalent of "fuel cost per km"
    • Mission Δv    →  m/s and trip duration (yr) per trajectory leg
    • Operational   →  USD per mission-year and USD per kg-payload

Active sources:
    • yfinance  (Yahoo Finance)  — live commodity prices used as proxies
                                   for RP-1 (heating oil HO=F), methane
                                   (natural gas NG=F), and a crude oil
                                   cross-check (CL=F).  Free, no API key.
    • Curated reference          — launch-vehicle pricing, propellant
      (public filings, May 2026)   chemistry, Δv values, and operational
                                   costs.  Every reference row carries an
                                   inline citation in its `notes` field
                                   and a `reference_year` stamp.

Authoritative sources used for the static reference tables (all values
verified May 2026):
    • SatBase 2026-02 SpaceX price update         → Falcon 9 / Falcon Heavy list price
    • SpaceX Voyager Technologies contract 2026   → Starship dedicated price
    • NASA OIG IG-24-015                          → SLS per-flight cost
    • ULA RocketBuilder + SpaceNews 2024-2026     → Atlas V, Vulcan Centaur pricing
    • Wikipedia (Vulcan, New Glenn, Ariane 6, H3) → cross-checked payload masses
    • Blue Origin / Geekwire (Apr 2026)           → New Glenn list price + payload
    • Rocket Lab Form 10-Q (FY2026 Q1)            → Electron pricing
    • TASS / Glavkosmos (2018, escalated)         → Soyuz-2.1b pricing
    • Mobius / Energy CG (2024)                   → LCH4 commodity pricing
    • DOD Aerospace Standard Prices (FY20)        → Hydrazine / MMH / N2O4
    • SETS Space / Electric Propulsion (2024)     → Xenon / argon ion pricing
    • NASA DSN Services Catalog 820-100-H         → DSN aperture fee (FY09 base)
    • NASA Planetary Society / Wikipedia          → OSIRIS-REx mission total cost
    • Plane Talking / Slingshot Aerospace (2024)  → Launch insurance market rate
    • Damodaran NYU Stern, Boeing/Howmet WACC     → Cost-of-capital benchmark
    • arXiv 1105.4152, 1406.5027                  → NEO Δv accessibility distribution
    • NASA Mars 2020 / Perseverance autonomy      → Autonomous mining control NRE

Mission profile assumption (v1.2.4+):
    All missions in this pipeline are UNCREWED — fully autonomous mining
    spacecraft.  No life-support mass, no crew habitat, no crew-related
    operations or return-vehicle uplift.  The 'Autonomous mining control
    & AI (NRE)' line item under operational_costs captures the
    autonomy-software development overhead that this design pays in
    exchange for not paying crew costs.

Pipeline flow:
    Fetch live fuel prices  →  Load reference tables  →  Merge  →  Validate
                            →  Compute normalised cost-per-Δv  →  Export
"""

# ─────────────────────────────────────────────────────────────────────────────
# INSTALLATION
# ─────────────────────────────────────────────────────────────────────────────
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
    # propellant tanks are quoted in the trade.  Enforced by validate() and
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
    pipeline_version: str = "1.7.0"
    preview_rows:     int = 15


CONFIG = TransportConfig()
os.makedirs(os.path.join(CONFIG.output_dir, CONFIG.subdir), exist_ok=True)

print(f"✅  Configuration loaded — output dir: "
      f"{os.path.join(CONFIG.output_dir, CONFIG.subdir)}")
print(f"    Active sources : "
      f"{', '.join(s for s, on in (('yfinance', CONFIG.use_yfinance), ('reference', CONFIG.use_reference_table)) if on)}")
print(f"    ISRU return    : {CONFIG.isru_return_propellant}  "
      f"(processing cost {CONFIG.isru_processing_usd_per_kg:.0f} USD/kg if on)")
print(f"    Contingency    : {CONFIG.contingency_fraction:.0%}")


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
        "dv_penalty_factor":     _LOW_THRUST_DV_PENALTY,
        "boiloff_pct_per_day":   0.0,   # Stored supercritical at ambient temperature; no boil-off.
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
                 "8 kg/kW allows for feed system and structure.",
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
        "value":            0.75,
        "range_low":        0.50,
        "range_high":       0.95,
        "notes": "v1.7.0.  Nobody has ever sustained-mined an asteroid.  This "
                 "is the probability that the excavation and beneficiation "
                 "chain works at all once it arrives — separate from the "
                 "spacecraft surviving the trip.  Anchors: OSIRIS-REx's TAGSAM "
                 "collected far more than planned but its sample head jammed "
                 "open; Hayabusa's first sampler failed to fire; Philae's "
                 "harpoons did not deploy.  Regolith-contact mechanisms are "
                 "where deep-space missions actually fail.  Drops toward 0.95 "
                 "for a repeat mission with flight heritage — raise it "
                 "alongside nre_amortization_missions.",
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
        "value":            CONFIG.contingency_fraction * 100,
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
    config:         TransportConfig = CONFIG,
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
def validate(
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
    config: TransportConfig = CONFIG,
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
    validate(launch_df, prop_df, dv_df, ops_df)

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
    config:             TransportConfig = CONFIG,
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


# ─────────────────────────────────────────────────────────────────────────────
# RUN & PREVIEW
# ─────────────────────────────────────────────────────────────────────────────
# Only self-runs when executed directly; importing this module is side-effect free.
if __name__ == "__main__":
    catalog = build_transportation_catalog(CONFIG)

    if catalog and not catalog["launch_vehicles"].empty:

        # ── Launch vehicles preview ──────────────────────────────────────────────
        print(f"\n{'='*75}")
        print(f"  🚀  LAUNCH VEHICLES — cheapest $/kg-to-LEO first")
        print(f"{'='*75}")
        lv_cols = ["name", "operator", "status", "payload_leo_kg",
                   "usd_per_kg_to_leo", "usd_per_kg_to_gto", "usd_per_kg_to_escape"]
        print(catalog["launch_vehicles"].sort_values("usd_per_kg_to_leo")[
            lv_cols
        ].head(CONFIG.preview_rows).to_string(index=False))

        # ── Propellant preview ───────────────────────────────────────────────────
        print(f"\n{'='*75}")
        print(f"  🔥  PROPELLANTS — Isp, density, cost  (live where available)")
        print(f"{'='*75}")
        p_cols = ["name", "type", "isp_vac_s", "density_kg_per_L",
                  "cost_usd_per_kg", "cost_usd_per_L", "price_basis"]
        print(catalog["propellants"][p_cols].to_string(index=False))

        # ── Δv reference preview ─────────────────────────────────────────────────
        print(f"\n{'='*75}")
        print(f"  📐  MISSION Δv SEGMENTS")
        print(f"{'='*75}")
        print(catalog["delta_v_segments"][
            ["segment", "dv_m_per_s", "duration_yr", "notes"]
        ].to_string(index=False))

        # ── Operational costs preview ────────────────────────────────────────────
        print(f"\n{'='*75}")
        print(f"  🏢  OPERATIONAL COSTS")
        print(f"{'='*75}")
        print(catalog["operational_costs"][
            ["category", "value", "unit", "range_low", "range_high"]
        ].to_string(index=False))

        # ── Cost-per-Δv comparison (the headline normalised metric) ──────────────
        print(f"\n{'='*75}")
        print(f"  🧮  PROPELLANT COST PER kg OF PAYLOAD — at Δv = 6 500 m/s "
              f"(median NEA)")
        print(f"{'='*75}")
        headline = cheapest_propellant_for(catalog, 6_500)
        print(headline.to_string(index=False))

        # ── Worked-example mission cost ──────────────────────────────────────────
        print(f"\n{'='*75}")
        print(f"  💼  WORKED EXAMPLE — 1 000-kg payload, LEO → avg NEA → return")
        print(f"{'='*75}")
        example = mission_cost_breakdown(
            catalog,
            payload_kg          = 1_000,
            delta_v_outbound    = 6_500,
            delta_v_return      = 5_500,
            launch_vehicle      = "Falcon Heavy (reusable side cores)",
            propellant          = "methalox  (LCH4 / LOX)",
            mission_duration_yr = 3.0,
            hardware_kg         = 2_000,
        )
        for k, v in example.items():
            if isinstance(v, float):
                print(f"    {k:28s} : {v:>18,.0f}")
            else:
                print(f"    {k:28s} : {v}")
