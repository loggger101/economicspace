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
def build_profitability_catalog(config: CalcConfig = CONFIG) -> pd.DataFrame:
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
