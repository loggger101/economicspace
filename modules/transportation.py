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
    # Five sub-files land in `<output_dir>/transportation/`:
    #     launch_vehicles.csv, propellants.csv, delta_v_segments.csv,
    #     operational_costs.csv, storage_systems.csv   (the last new in v1.9.0)
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
    pipeline_version: str = "1.9.0"
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
    "Argon":     {"density_kg_per_L": 1.395, "cost_usd_per_kg":     10.00, "storage_class": "mild_cryogen"},     # liquid NBP (cryogenic storage)

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
        "storage_class":         "mild_cryogen",
        "tank_kg_per_L":         _tank_kg_per_L("mild_cryogen"),
        "isru_feed_kg_per_kg":   None,
        "isru_feed_material":    None,
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
        "boiloff_pct_per_day":   0.0,
        "isp_vac_s":             4_000,
        "exhaust_vel_m_per_s":   4_000 * G0_M_S2,
        "density_kg_per_L":      _COMPONENTS["Argon"]["density_kg_per_L"],
        "ref_cost_usd_per_kg":   _COMPONENTS["Argon"]["cost_usd_per_kg"],
        "ref_cost_usd_per_L":    _COMPONENTS["Argon"]["cost_usd_per_kg"]
                                 * _COMPONENTS["Argon"]["density_kg_per_L"],
        "yfinance_proxy":        None,
        "reference_year":        _REF_YEAR_PROP,
        "notes": "Ad Astra's VX-200SS ran 100 hours at 80 kW in 2021.  RF-heated "
                 "plasma in a magnetic nozzle, and the headline feature is "
                 "throttleable Isp — trade thrust against efficiency in flight, "
                 "which is precisely the freedom a fixed-Isp table cannot "
                 "express.  Modelled here at a single 4,000 s point, which "
                 "understates it; capturing the variable-Isp advantage needs the "
                 "same trajectory optimiser the sails do.",
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
                 "⚠️  NOT modelled in Module 4.  The pipeline prices water as a "
                 "commodity at every in-space destination and has never charged "
                 "anything to keep it through a four-year cruise.  Water is a "
                 "large part of why the volatile-rich B and C types win, so this "
                 "gap runs in the optimistic direction on the current answer.",
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
                 "⚠️  Not modelled.  Module 4's processing_power_w() computes a "
                 "continuous average draw and sizes the array off it, so it "
                 "implicitly assumes the sun never sets.  A real rig either "
                 "carries the storage or mines at half duty cycle; either way "
                 "the current figure is optimistic.",
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
    store_df  = load_storage()

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
