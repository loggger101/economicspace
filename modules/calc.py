# -*- coding: utf-8 -*-
"""calc — Module 4 of the Asteroid Profitability Pipeline.

Reads the catalogs produced by Modules 1-3 and computes, for every asteroid:

    1.  How much of each mineral category is present  (Module 1 × mass)
    2.  Gross value of the returned material           (Module 2 × yields)
    3.  Round-trip mission cost                        (Module 3 + rocket eq.)
    4.  Net profit, ROI, and $/kg-returned-cost        (the headline number)

The mission model is a return-sample architecture, UNCREWED throughout —
the spacecraft is an autonomous mining platform with no life-support, no
crew habitat, and no human in the loop past LEO injection:

    Earth launch  →  LEO  →  outbound burn  →  asteroid rendezvous
        →  autonomous station-keeping + mining
        →  return burn  →  Earth re-entry  (sample-return capsule)

Mass cascade (no ISRU — default conservative):
        m_dry_return + m_payload_returned + m_tps
                     ← landed on Earth (aerocapture-ablated TPS already lost)
        × (R_ret = exp(Δv_ret / Isp·g₀))
        = mass on departure from asteroid
              + m_hardware (stays at asteroid)
                     ← arrived at asteroid
        × (R_out = exp(Δv_out / Isp·g₀))
        = m_launch lifted to LEO

The heat shield mass `m_tps = tps_frac × (m_payload + m_dry_return)` is
fully accounted for in the cascade (v1.3.2+): it is hauled outbound as
dead mass AND must be pushed back through the return burn even though it
ablates during entry.  This is a significant accuracy fix — omitting it
overstates max payload by ~30%.

`m_payload_returned` is solved closed-form against the vehicle's
payload-to-LEO capacity (s = 1 + tps_frac):
    m_payload_returned_max =
        (M_LEO / R_out − m_hardware − m_dry_return · s · R_ret) / (s · R_ret − 1)

Cost line-items (all from Module 3's reference tables — no values are
re-introduced here):
    launch + outbound prop + return prop + mining hardware recurring
    + mission ops × mission_duration_yr  + heat shield (if aerocapture)
    + sample recovery + 3rd-party liability + launch insurance %
    + spacecraft bus NRE / N_missions_amortization
    + autonomous mining control & AI NRE / N_missions_amortization
    × (1 + contingency_fraction)
    × (1 + WACC)^mission_duration_yr      ← time-value of money

Note: there is NO crew cost line in this cascade — every mission is
modelled as uncrewed/autonomous (Module 3 v1.2.4+ removed the legacy
'Crew' line item and replaced it with the autonomous-control NRE).

Pipeline flow:
    Load 3 upstream catalogs  →  integrity check  →  per-asteroid bulk price
        →  rocket-eq solve max payload  →  cost cascade  →  profit + rank
        →  CSV export
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

_REQUIRED_PKGS = ["pandas", "numpy"]
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

    # ─── AEROCAPTURE  (return via heat shield rather than propulsive) ────────
    # When True, return Δv is reduced by `aerocapture_dv_savings_m_s` but a
    # heat-shield mass overhead is added at the rate from Module 3.
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
    pipeline_version: str = "1.4.0"


CONFIG = CalcConfig()
os.makedirs(CONFIG.output_dir, exist_ok=True)

print(f"✅  Configuration loaded — output dir: {CONFIG.output_dir}")
print(f"    Hardware       : {CONFIG.mining_hardware_kg:,.0f} kg mining rig "
      f"+ {CONFIG.return_vehicle_dry_kg:,.0f} kg return-capsule dry")
print(f"    Mining cap     : {CONFIG.max_mining_fraction:.0%} of asteroid mass per mission")
print(f"    Return mode    : "
      f"{'aerocapture (−' + str(int(CONFIG.aerocapture_dv_savings_m_s)) + ' m/s + TPS mass)' if CONFIG.use_aerocapture_return else 'propulsive'}")
print(f"    ISRU           : {CONFIG.use_isru_return_propellant}")
print(f"    Contingency    : {CONFIG.contingency_fraction:.0%}  |  "
      f"NRE amortised over {CONFIG.nre_amortization_missions} mission(s)")


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


def _leo_departure_dv_km_s(v_inf_km_s: float) -> float:
    """Δv to go from circular LEO onto a hyperbola with this v_infinity.

    Symmetric with capture: the same expression gives the propulsive cost of
    arriving from a hyperbola and circularising back into LEO.
    """
    v_leo = math.sqrt(MU_EARTH_KM3_S2 / R_LEO_KM)
    v_esc = math.sqrt(2.0) * v_leo
    return math.sqrt(v_esc * v_esc + v_inf_km_s * v_inf_km_s) - v_leo


def asteroid_transfer_dv_km_s(
    a_au: float, e: float, i_deg: float,
) -> Optional[Tuple[float, float, float]]:
    """Patched-conic Δv budget for a rendezvous mission to one asteroid.

    Returns (dv_out, dv_return_propulsive, dv_return_aerocapture) in km/s,
    or None if the elements are unusable.

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
    # Departing the asteroid costs the same apsis burn in reverse.  Arriving
    # at Earth then either costs a propulsive capture, or nothing propulsive
    # at all if you enter the atmosphere (paid for in heat-shield mass
    # instead, which the Module 4 cascade already carries).
    dv_ret_propulsive = dv_match + _leo_departure_dv_km_s(v_inf)
    dv_ret_aerocapture = dv_match

    return dv_out, dv_ret_propulsive, dv_ret_aerocapture


def asteroid_dv_m_s(asteroid_row: pd.Series, config: CalcConfig) -> Tuple[float, float]:
    """Return (Δv_outbound, Δv_return) in m/s for one asteroid.

    Uses the per-asteroid estimator when Module 1 supplied usable orbital
    elements, and falls back to the CalcConfig reference defaults when it did
    not.  Set `config.use_per_asteroid_dv = False` to force the old uniform
    behaviour for every row.
    """
    estimate = None
    if config.use_per_asteroid_dv:
        estimate = asteroid_transfer_dv_km_s(
            asteroid_row.get("semi_major_axis_au"),
            asteroid_row.get("eccentricity"),
            asteroid_row.get("inclination_deg"),
        )

    if estimate is not None:
        dv_out_km, dv_ret_prop_km, dv_ret_aero_km = estimate
        dv_out = dv_out_km * 1_000.0
        dv_ret = (dv_ret_aero_km if config.use_aerocapture_return
                  else dv_ret_prop_km) * 1_000.0
        # Clamp against physically silly extremes (bad elements upstream).
        dv_out = min(max(dv_out, 3_000.0), config.max_dv_outbound_m_s)
        dv_ret = min(max(dv_ret, 300.0),  config.max_dv_outbound_m_s)
        return dv_out, dv_ret

    # ── Fallback: uniform reference Δv (pre-v1.4.0 behaviour) ────────────────
    dv_out             = config.default_dv_outbound_m_s
    dv_ret_propulsive  = config.default_dv_return_m_s
    if config.use_aerocapture_return:
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
    capsule_per_kg          = _ops_value(ops_df, "Return capsule recurring cost", default=150_000.0)
    capsule_cost            = config.return_vehicle_dry_kg * capsule_per_kg   # per-mission
    hardware_cost           = mining_rig_cost + capsule_cost

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

    # Recovery + regulatory flat costs
    recovery_cost   = _ops_value(ops_df, "Sample recovery operations",       default=15_000_000.0)
    liability_cost  = _ops_value(ops_df, "Third-party liability insurance",  default=1_500_000.0)
    licensing_cost  = _ops_value(ops_df, "FAA Part 450 licensing compliance", default=2_500_000.0)

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
def evaluate_combo(
    asteroid_row:      pd.Series,
    vehicle:           pd.Series,
    propellant:        pd.Series,
    bulk_value_per_kg: float,
    dv_out_m_s:        float,
    dv_ret_m_s:        float,
    ops_df:            pd.DataFrame,
    config:            CalcConfig,
) -> Optional[Dict[str, float]]:
    """Evaluate one (vehicle × propellant) combination for one asteroid.

    Returns None if the combo is infeasible (zero return payload), or a
    full result dict including profit, ROI, $/kg returned, and the mass
    + cost cascades.
    """
    leo_cap = float(vehicle.get("payload_leo_kg", 0) or 0)
    if leo_cap <= 0:
        return None

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

    tps_frac = (
        config.heat_shield_frac_of_payload
        if config.use_aerocapture_return else 0.0
    )

    cascade = max_return_payload_kg(
        leo_capacity_kg = leo_cap,
        isp_s           = float(propellant["isp_vac_s"]),
        dv_out_m_s      = dv_out_m_s,
        dv_ret_m_s      = dv_ret_m_s,
        hardware_kg     = config.mining_hardware_kg,
        dry_return_kg   = config.return_vehicle_dry_kg,
        tps_frac        = tps_frac,
        isru_return     = config.use_isru_return_propellant,
    )
    if not cascade["viable"]:
        return None

    # Cap the returned payload by what the asteroid can supply
    asteroid_mass = asteroid_row.get("estimated_mass_kg")
    if asteroid_mass is None or pd.isna(asteroid_mass) or asteroid_mass <= 0:
        return None
    mineable_kg = float(asteroid_mass) * config.max_mining_fraction

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
    throughput_cap_kg = max_payload_by_throughput_kg(config)

    m_payload_demand = min(cascade["max_payload_kg"], mineable_kg)
    volume_fits      = m_payload_demand <= volume_capacity_kg
    throughput_fits  = m_payload_demand <= throughput_cap_kg
    m_payload        = min(m_payload_demand, volume_capacity_kg, throughput_cap_kg)
    if m_payload <= 0:
        return None

    return_volume_m3 = m_payload / bulk_density_kg_per_L / 1000.0

    # Recompute the full cascade at the capped payload.  TPS, return-prop,
    # outbound-prop, launch all depend on m_payload — must be redone to
    # reflect the actual mission, not the rocket-eq theoretical max.
    r_ret           = cascade["r_ret"]
    r_out           = cascade["r_out"]
    m_tps           = tps_frac * (m_payload + config.return_vehicle_dry_kg)
    m_after_return  = m_payload + config.return_vehicle_dry_kg + m_tps
    m_return_prop   = m_after_return * (r_ret - 1.0)
    m_at_asteroid   = (config.mining_hardware_kg + config.return_vehicle_dry_kg + m_tps
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

    gross_value         = m_payload * bulk_value_per_kg
    mining_yr           = mining_duration_yr(m_payload, config)
    mission_duration_yr = asteroid_mission_duration_yr(
        dv_out_m_s, dv_ret_m_s, config, mining_yr=mining_yr,
    )
    cost                = mission_cost_usd(
        mass_cascade        = actual_cascade,
        vehicle             = vehicle,
        propellant          = propellant,
        ops_df              = ops_df,
        config              = config,
        mission_duration_yr = mission_duration_yr,
    )

    profit               = gross_value - cost["total_cost"]
    roi                  = profit / cost["total_cost"] if cost["total_cost"] > 0 else np.nan
    usd_per_kg_cost      = cost["total_cost"] / m_payload if m_payload > 0 else np.nan

    return {
        "vehicle":              vehicle["name"],
        "propellant":           propellant["name"],
        "dv_out_m_s":           dv_out_m_s,
        "dv_ret_m_s":           dv_ret_m_s,
        "isp_s":                float(propellant["isp_vac_s"]),
        "dv_penalty_factor":    dv_penalty,
        "mission_duration_yr":  mission_duration_yr,
        "mining_duration_yr":   mining_yr,
        "max_payload_kg":       m_payload,
        "throughput_cap_kg":    throughput_cap_kg,
        "throughput_fits":      throughput_fits,
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
def build_profitability_catalog(config: CalcConfig = CONFIG) -> pd.DataFrame:
    """Run the full Module 4 calculation pipeline."""
    t0 = datetime.now()
    print("=" * 75)
    print("  💰  PROFITABILITY PIPELINE — MODULE 4")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  v{config.pipeline_version}")
    print("=" * 75)

    # ── Step 1 — Load catalogs ───────────────────────────────────────────────
    catalogs = load_all_catalogs(config)

    # ── Step 2 — Integrity check ─────────────────────────────────────────────
    integrity_check(catalogs)

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
              f"(eval_row_cap in CONFIG)")

    # Candidate (vehicle × propellant) grid is config-driven, not asteroid-
    # driven — build it once and hand it to every evaluation.
    combos = candidate_combos(catalogs, config)
    if not combos:
        print("\n❌  No candidate vehicle × propellant combinations after "
              "filtering — check operational_vehicles_only / candidate_* in CONFIG.")
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


# ─────────────────────────────────────────────────────────────────────────────
# RUN & PREVIEW
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    catalog = build_profitability_catalog(CONFIG)

    if not catalog.empty:

        # ── Top-N preview ────────────────────────────────────────────────────────
        print(f"\n{'='*95}")
        print(f"  🏆  TOP {CONFIG.top_n_preview} MOST PROFITABLE ASTEROIDS")
        print(f"{'='*95}")
        preview_cols = [
            "designation", "name", "spectral_type", "comp_group",
            "estimated_mass_kg", "max_payload_kg",
            "bulk_value_usd_per_kg", "gross_M$", "cost_M$", "profit_M$", "roi",
            "vehicle", "propellant",
        ]
        show = [c for c in preview_cols if c in catalog.columns]
        print(catalog[show].head(CONFIG.top_n_preview).to_string(index=False))

        # ── Summary by composition group ─────────────────────────────────────────
        print(f"\n{'='*95}")
        print("  📊  PROFITABILITY BY COMPOSITION GROUP")
        print(f"{'='*95}")
        if "comp_group" in catalog.columns:
            grp = catalog.groupby("comp_group").agg(
                n             = ("designation", "count"),
                viable_n      = ("viable", "sum"),
                mean_profit_M = ("profit_M$", "mean"),
                best_profit_M = ("profit_M$", "max"),
                mean_roi      = ("roi", "mean"),
            ).sort_values("best_profit_M", ascending=False)
            print(grp.to_string())

        # ── Vehicle / propellant selection summary ───────────────────────────────
        print(f"\n{'='*95}")
        print("  🚀  WINNING VEHICLE × PROPELLANT COMBINATIONS")
        print(f"{'='*95}")
        if "vehicle" in catalog.columns and "propellant" in catalog.columns:
            combo = (
                catalog.groupby(["vehicle", "propellant"])
                       .size().reset_index(name="n_asteroids")
                       .sort_values("n_asteroids", ascending=False)
            )
            print(combo.head(15).to_string(index=False))

        # ── Cost-component diagnostic ────────────────────────────────────────────
        # Average dollar breakdown — tells the user WHERE the money is going.
        # If launch dominates → consider a cheaper vehicle; if NRE/hardware
        # dominates → multi-mission amortisation will help; if WACC dominates →
        # shorter mission duration is the lever.  Shows breakdown for viable
        # missions when there are any, else for all evaluated rows so the user
        # can still diagnose what would need to change to become profitable.
        cost_cols = [c for c in catalog.columns if c.endswith("_cost_usd")]
        viable_df = catalog[catalog["viable"]]
        diag_df, label = (viable_df, "viable missions") if not viable_df.empty else (catalog, "ALL evaluated (no viable mission yet — try cheaper hardware / multi-mission NRE / Starship)")
        print(f"\n{'='*95}")
        print(f"  💵  AVERAGE COST BREAKDOWN  ({label}, USD)")
        print(f"{'='*95}")
        if cost_cols and not diag_df.empty:
            means = diag_df[cost_cols].mean().sort_values(ascending=False)
            bar_scale = means.max() / 50 if means.max() > 0 else 1
            for col, val in means.items():
                bar = "█" * max(1, int(val / bar_scale))
                cat = col.replace("_cost_usd", "").replace("_", " ")
                print(f"  {cat:25s} {bar:<52s}  ${val:>15,.0f}")
