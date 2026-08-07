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
    pipeline_version: str = "1.10.0"


CONFIG = CalcConfig()
os.makedirs(CONFIG.output_dir, exist_ok=True)

print(f"✅  Configuration loaded — output dir: {CONFIG.output_dir}")
print(f"    Hardware       : {CONFIG.mining_hardware_kg:,.0f} kg mining rig "
      f"+ {CONFIG.return_vehicle_dry_kg:,.0f} kg return-capsule dry")
print(f"    Mining cap     : {CONFIG.max_mining_fraction:.0%} of asteroid mass per mission")
print(f"    Return mode    : "
      f"{'aerocapture available (per-asteroid Δv saving vs TPS mass)' if CONFIG.use_aerocapture_return else 'propulsive only'}")
print(f"    ISRU           : {'available where the rock has water' if CONFIG.use_isru_return_propellant else 'off'}")
print(f"    Architecture   : "
      f"{'searched per asteroid' if CONFIG.optimise_architecture_per_asteroid else 'fixed by config'}")
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

def low_thrust_burn_time_yr(
    m_prop_kg:  float,
    isp_s:      float,
    power_w:    float,
    efficiency: float,
) -> float:
    """Years of continuous thrusting to expend `m_prop_kg` at `power_w`.

        t = m_prop · (Isp·g0)² / (2·η·P)

    Returns inf for zero power — a thruster with no supply never finishes.
    """
    if power_w <= 0 or m_prop_kg <= 0 or isp_s <= 0:
        return 0.0 if m_prop_kg <= 0 else float("inf")
    ve = isp_s * G0_M_S2
    seconds = m_prop_kg * ve * ve / (2.0 * efficiency * power_w)
    return seconds / (365.25 * 24.0 * 3600.0)


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
    asteroid_row: pd.Series, config: CalcConfig,
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


def asteroid_dv_m_s(asteroid_row: pd.Series, config: CalcConfig) -> Tuple[float, float]:
    """(Δv_outbound, Δv_return) in m/s for one asteroid, in m/s.

    Kept as the single-answer form for interactive use and for callers that
    want the config's nominal return mode rather than the optimised one.  The
    pipeline itself uses `asteroid_dv_options`, which returns every mode worth
    evaluating and lets the profit search choose.
    """
    aero = uses_tps(config)
    for opt in asteroid_dv_options(asteroid_row, config):
        if bool(opt["aero"]) == aero:
            return float(opt["dv_out_m_s"]), float(opt["dv_ret_m_s"])
    return _dv_fallback_m_s(config, aero)


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
# What is actually makeable from asteroid material is hydrolox: water,
# electrolysed, cryo-cooled.  That is the architecture every asteroid-ISRU
# study proposes and the only one this model can honestly price.
#
# The mass balance is stoichiometric.  Electrolysis yields 8 kg of O2 per kg of
# H2 (mass ratio of O to H2 in H2O).  A hydrolox stage runs oxidiser-rich of
# stoichiometric at an O/F around 6:1, so a kilogram of propellant is
# 1/(1+6) kg of H2, and getting that H2 takes 9x its mass in water:
#
#     water per kg of propellant = 9 / (1 + O/F) = 1.286 kg
#
# The surplus oxygen (8/7 produced against 6/7 burnt) is vented — a real depot
# would sell it, but this model has nobody to sell it to at an asteroid.
#
# Methalox is deliberately NOT included even though C-types carry both carbon
# and water.  It needs a Sabatier loop and a carbon-reduction step that no
# study has costed for asteroid regolith, and asserting a yield for it would be
# inventing a number rather than deriving one.
_HYDROLOX_OF_RATIO         = 6.0
WATER_KG_PER_KG_HYDROLOX   = 9.0 / (1.0 + _HYDROLOX_OF_RATIO)
_ISRU_PROPELLANTS          = ("hydrolox",)


def isru_feed_kg_per_kg_propellant(
    asteroid_row: pd.Series, propellant: pd.Series, config: CalcConfig,
) -> Optional[float]:
    """kg of regolith to dig per kg of ISRU return propellant, or None.

    None means this mission cannot make its own propellant — either the
    propellant is not manufacturable from asteroid material, or this body has
    no water to make it from.  That is a per-(asteroid × propellant) fact, which
    is why it is answered here rather than by a config flag.
    """
    name = str(propellant.get("name", "")).strip().lower()
    if not any(tag in name for tag in _ISRU_PROPELLANTS):
        return None

    ice_frac = asteroid_row.get("comp_ice_fraction")
    if ice_frac is None or pd.isna(ice_frac) or float(ice_frac) <= 0.0:
        return None

    recovery = max(1e-6, min(1.0, config.beneficiation_recovery))
    return WATER_KG_PER_KG_HYDROLOX / (float(ice_frac) * recovery)


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
    structure_frac:  float = 0.0,
) -> Dict[str, float]:
    """Closed-form max returned-payload solver for a return-sample mission.

    Two masses scale with the payload and both are fully accounted for:

      • HEAT SHIELD, tps_frac × (m_payload + m_dry_return) — hauled outbound
        from Earth AND pushed back through the return burn, even though it
        ablates on entry.  Let s = 1 + tps_frac.
      • RETURN-VEHICLE STRUCTURE, structure_frac × m_payload (v1.10.0) — the
        tankage, primary structure and cargo restraint that a bigger haul
        needs.  Let f = structure_frac, so the dry vehicle is d0 + f·m_payload.

    Working backward from arrival:
        m_dry           = d0 + f · m_payload
        m_tps           = tps_frac · (m_payload + m_dry)
        m_after_return  = m_payload + m_dry + m_tps = s · (m_payload + m_dry)
        m_before_return = m_after_return × R_ret
        m_return_prop   = (R_ret − 1) × m_after_return     (zero if ISRU on)

        m_at_asteroid     = m_hardware + m_dry + m_tps + m_return_prop
                            (the mined payload is loaded HERE, not brought)
        m_before_outbound = m_at_asteroid × R_out
        m_outbound_prop   = (R_out − 1) × m_at_asteroid

        m_launch = m_at_asteroid × R_out

    Writing g = s·(1 + f) − 1 for the combined payload-proportional overhead,
    m_at_asteroid collapses to

        m_hardware + s·d0·R_ret + m_payload · ((1 + g)·R_ret − 1)

    so the NO-ISRU closed form is

        m_payload_max =
            (M_LEO/R_out − m_hardware − s·d0·R_ret) / ((1 + g)·R_ret − 1)

    which reduces to the pre-v1.10.0 expression exactly when f = 0, since g
    then equals tps_frac and (1 + g) equals s.

    Returns a dict with the full mass cascade.  All masses in kg.
    """
    def _infeasible(r_out=0.0, r_ret=0.0):
        return {"max_payload_kg": 0.0, "viable": False,
                "r_out": r_out, "r_ret": r_ret,
                "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
                "m_at_asteroid": 0, "m_tps": 0, "m_dry_return": 0}

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
    f     = max(0.0, float(structure_frac))
    # Combined payload-proportional overhead: heat shield plus the structure
    # that scales with the haul.  g = tps_frac exactly when f = 0.
    g     = s * (1.0 + f) - 1.0

    if isru_return:
        # ISRU mode: return propellant is manufactured ON the asteroid from
        # mined volatiles, NOT carried up from Earth.  The heat shield and the
        # payload-scaling structure are still launched from Earth, so the
        # launch constraint becomes:
        #
        #   M_LEO ≥ (m_hardware + m_dry + m_tps) × R_out
        #         = (m_hardware + s·d0 + g·m_payload) × R_out
        #
        # ⇒ m_payload_launch_max = (M_LEO/R_out − m_hardware − s·d0) / g
        #
        # v1.10.0: g is only zero when there is no heat shield AND no structure
        # scaling — i.e. only if return_structure_frac_of_payload is explicitly
        # set to 0.  That combination is what used to let the cascade report an
        # unbounded payload with nothing but the volume cap to stop it.
        base_launch = (hardware_kg + s * dry_return_kg) * r_out
        if base_launch > leo_capacity_kg:
            return {"max_payload_kg": 0.0, "viable": False,
                    "r_out": r_out, "r_ret": r_ret,
                    "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
                    "m_at_asteroid": 0, "m_tps": 0, "m_dry_return": 0}
        if g > 0:
            m_payload_launch_max = (
                leo_capacity_kg / r_out - hardware_kg - s * dry_return_kg
            ) / g
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
    # m_dry           = d0 + f · m_payload
    # m_after_return  = s · (m_payload + m_dry) = m_payload·(1 + g) + s·d0
    # m_return_prop   = (R_ret − 1) · m_after_return
    # m_at_asteroid   = m_hardware + s·d0·R_ret + m_payload · ((1 + g)·R_ret − 1)
    # M_LEO = m_at_asteroid × R_out
    # ⇒ m_payload_max = (M_LEO/R_out − m_hardware − s·d0·R_ret) / ((1 + g)·R_ret − 1)
    #
    # With f = 0 this is g = tps_frac and (1 + g) = s, i.e. the pre-v1.10.0
    # expression exactly.
    denom   = (1.0 + g) * r_ret - 1.0
    bracket = leo_capacity_kg / r_out - hardware_kg - s * dry_return_kg * r_ret
    if bracket <= 0 or denom <= 0:
        return {"max_payload_kg": 0.0, "viable": False,
                "r_out": r_out, "r_ret": r_ret,
                "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
                "m_at_asteroid": 0, "m_tps": 0, "m_dry_return": 0}

    m_payload_max = bracket / denom
    if m_payload_max <= 0:
        return {"max_payload_kg": 0.0, "viable": False,
                "r_out": r_out, "r_ret": r_ret,
                "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
                "m_at_asteroid": 0, "m_tps": 0, "m_dry_return": 0}

    m_dry_return   = dry_return_kg + f * m_payload_max
    m_tps          = tps_frac * (m_payload_max + m_dry_return)
    m_after_return = m_payload_max + m_dry_return + m_tps
    m_return_prop  = m_after_return * (r_ret - 1.0)
    m_at_asteroid  = hardware_kg + m_dry_return + m_tps + m_return_prop
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
        "m_dry_return":    m_dry_return,
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
    stay_yr:             float = 0.0,
    isru_return:         Optional[bool] = None,
    ep_power_w:          float = 0.0,
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
    hw_per_kg               = _ops_value(ops_df, "Mining payload recurring cost", default=300_000.0)
    mining_rig_cost_total   = config.mining_hardware_kg * hw_per_kg
    n_missions              = max(1, config.nre_amortization_missions)

    # ── Rig service life and terminal value (v1.8.0) ─────────────────────────
    # A rig cannot serve more missions than its life allows.  Whatever life
    # remains when the programme ends is credited at the salvage fraction —
    # but only if there IS a programme; a rig at an asteroid nobody revisits
    # is stranded, not an asset.
    rig_terminal_value = 0.0
    missions_sharing_rig = n_missions
    if config.model_rig_service_life and stay_yr > 0:
        life_yr = _ops_value(ops_df, "Mining rig service life", default=15.0)
        salvage = _ops_value(ops_df, "Rig salvage fraction", default=0.50)
        missions_rig_can_serve = max(1, int(life_yr // stay_yr))
        missions_sharing_rig   = min(n_missions, missions_rig_can_serve)
        if n_missions > 1:
            life_used_frac = min(1.0, missions_sharing_rig * stay_yr / life_yr)
            rig_terminal_value = mining_rig_cost_total * (1.0 - life_used_frac) * salvage
    mining_rig_cost = ((mining_rig_cost_total - rig_terminal_value)
                       / max(1, missions_sharing_rig))
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
    # v1.7.0: LEARNING CURVE.  The per-mission articles — the capsule or
    # lander, and the power system — are built N times over a programme, and
    # the Nth costs less than the first.  The mining rig is excluded: when
    # nre_amortization_missions > 1 it is modelled as ONE unit shared across
    # missions, not N units built, so a curve on it would double-count.
    # Exactly 1.0 at N = 1, so a single-mission run is untouched.
    lc = learning_curve_factor(config.nre_amortization_missions, config.learning_curve_rate)
    # v1.10.0: bill the return vehicle actually flown.  Its dry mass grows with
    # the haul (return_structure_frac_of_payload), and the cascade records what
    # it came to; charging the 500 kg base rate for a vehicle that massed
    # 19 tonnes would put the mass in the rocket equation and leave the money
    # out of the ledger — the same asymmetry the EP stage had.
    dry_return_flown = float(mass_cascade.get(
        "m_dry_return", config.return_vehicle_dry_kg))
    capsule_cost            = dry_return_flown * capsule_per_kg * lc
    # v1.5.0: the beneficiation plant's solar array, priced per installed Watt
    # off Module 3's power-system row.  Zero unless beneficiation is on — the
    # baseline rig's own power is already implicit in its $/kg recurring rate.
    power_per_w             = _ops_value(ops_df, "Power system (solar + battery)", default=800.0)
    power_system_cost       = max(0.0, float(processing_power_w)) * power_per_w * lc
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
        ep_drive_per_kw = _ops_value(
            ops_df, "Electric propulsion system recurring cost", default=1_500_000.0,
        )
        ep_system_cost = (max(0.0, float(ep_power_w)) * power_per_w
                          + ep_kw * ep_drive_per_kw) * lc
    else:
        ep_system_cost = 0.0
    hardware_cost           = (mining_rig_cost + capsule_cost + power_system_cost
                               + ep_system_cost)

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
    nre_cost    = nre_total * (1.0 - nre_overlap) / n_missions

    # Autonomous mining control & AI NRE — uncrewed-mission specific (Module 3
    # v1.2.4+ replaced the legacy 'Crew' line item with this).  Amortised the
    # same way as the bus NRE — once developed, the autonomy stack ships on
    # every subsequent identical mission.
    autonomy_nre_total = _ops_value(
        ops_df, "Autonomous mining control & AI (NRE)", default=200_000_000.0,
    )
    autonomy_nre_cost  = autonomy_nre_total / n_missions

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
        "ep_system_cost":        ep_system_cost,         # electric stage
        "rig_terminal_value":    rig_terminal_value,
        "missions_sharing_rig":  float(missions_sharing_rig),
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
    markets:           Optional[Dict[str, float]] = None,
    aero:              Optional[bool] = None,
    isru:              bool = False,
    rendezvous_apsis:  str = "",
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
    dv_penalty = float(propellant.get("dv_penalty_factor", 1.0) or 1.0)
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
    if isru:
        ratio = isru_feed_kg_per_kg_propellant(asteroid_row, propellant, config)
        if ratio is None:
            return None
        isru_feed_per_kg_prop = float(ratio)

    # Cap the returned payload by what the asteroid can supply
    asteroid_mass = asteroid_row.get("estimated_mass_kg")
    if asteroid_mass is None or pd.isna(asteroid_mass) or asteroid_mass <= 0:
        return None
    mineable_kg = float(asteroid_mass) * config.max_mining_fraction
    throughput_cap_kg = max_payload_by_throughput_kg(config)
    structure_frac = max(0.0, float(config.return_structure_frac_of_payload))

    # ── Launch window (v1.7.0) ───────────────────────────────────────────────
    # Hoisted above the sizing loop in v1.10.0: the wait depends only on the
    # target and the destination, but it is part of the stay, and the stay is
    # how long cryogenic return propellant sits in the tank boiling off.
    a_dest_au = (A_MARS_AU
                 if str(config.delivery_destination).strip().lower() == "mars_surface"
                 else 1.0)
    synodic_yr     = synodic_period_yr(asteroid_row.get("semi_major_axis_au"), a_dest_au)
    window_wait_yr = 0.5 * synodic_yr if config.model_launch_windows else 0.0

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

    # ── Electric propulsion sizing (v1.7.0) ──────────────────────────────────
    # An electric stage is not a chemical stage with better Isp — it needs a
    # power plant proportional to how fast you want the propellant burnt, and
    # that plant is mass in the same rocket equation.  Sized to finish its
    # thrusting inside ep_target_thrust_yr.  Module 3 tags electric
    # propellants with dv_penalty_factor > 1.
    is_electric = (config.model_low_thrust_time
                   and float(propellant.get("dv_penalty_factor", 1.0) or 1.0) > 1.0)
    ep_eff        = _ops_value(ops_df, "Electric propulsion efficiency", default=0.60)
    ep_kg_per_kw  = _ops_value(ops_df, "Electric thruster + PPU specific mass", default=8.0)

    isp_s_val   = float(propellant["isp_vac_s"])
    boiloff_pct = float(propellant.get("boiloff_pct_per_day", 0.0) or 0.0)
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
    power_system_kg = 0.0
    ep_system_kg    = 0.0
    ep_power_watts  = 0.0
    ep_thrust_yr    = 0.0
    processing_power_watts = 0.0
    isru_feed_kg    = 0.0
    isru_prop_kg    = 0.0
    dv_ret_eff      = dv_ret_m_s
    boiloff_factor  = 1.0
    stay_est_yr     = config.station_keeping_floor_yr + window_wait_yr
    outbound_yr     = max(0.5, 0.000_23 * dv_out_m_s)
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
            structure_frac  = structure_frac,
        )
        if not cascade["viable"]:
            return None

        new_ep_kg = 0.0
        if is_electric:
            m_prop_total = (float(cascade.get("m_outbound_prop", 0.0))
                            + float(cascade.get("m_return_prop", 0.0)))
            ep_power_watts = ep_power_required_w(
                m_prop_total, isp_s_val, config.ep_target_thrust_yr, ep_eff,
            )
            ep_thrust_yr = config.ep_target_thrust_yr if m_prop_total > 0 else 0.0
            # Array (scales 1/r²) plus thruster + PPU (does not).
            array_kg  = ep_power_watts / w_per_kg if w_per_kg > 0 else 0.0
            drive_kg  = ep_power_watts / 1000.0 * ep_kg_per_kw
            new_ep_kg = array_kg + drive_kg

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
                              + structure_frac * trial_payload)
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
        if beneficiate or isru:
            processing_power_watts = processing_power_w(
                trial_feed + new_isru_feed,
                trial_payload if beneficiate else 0.0,
                trial_dur, dig_wh, benef_wh,
            )
            if isru and new_isru_prop > 0 and trial_dur > 0:
                # Baking the water out of the rock, on top of digging it.
                water_wh = _ops_value(
                    ops_df, "Water liberation energy (bound water)", default=2_500.0,
                )
                processing_power_watts += (
                    water_wh * new_isru_prop * WATER_KG_PER_KG_HYDROLOX
                    / (trial_dur * 365.25 * 24.0)
                )
            new_power_kg = processing_power_watts / w_per_kg if w_per_kg > 0 else 0.0

        new_stay_yr = trial_dur + window_wait_yr
        converged = (
            abs(new_power_kg - power_system_kg) <= 0.01 * max(new_power_kg, 1.0)
            and abs(new_ep_kg - ep_system_kg) <= 0.01 * max(new_ep_kg, 1.0)
            and abs(new_isru_feed - isru_feed_kg) <= 0.01 * max(new_isru_feed, 1.0)
            and abs(new_stay_yr - stay_est_yr) <= 0.01 * max(new_stay_yr, 1.0)
        )
        power_system_kg, ep_system_kg = new_power_kg, new_ep_kg
        isru_feed_kg, isru_prop_kg    = new_isru_feed, new_isru_prop
        stay_est_yr                   = new_stay_yr
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
    # v1.10.0: the return vehicle grows with what it carries — see
    # return_structure_frac_of_payload.
    m_dry_return    = config.return_vehicle_dry_kg + structure_frac * m_payload
    m_tps           = tps_frac * (m_payload + m_dry_return)
    m_after_return  = m_payload + m_dry_return + m_tps
    m_return_prop   = m_after_return * (r_ret - 1.0)
    m_at_asteroid   = (hardware_total_kg + m_dry_return + m_tps
                       + (0.0 if isru else m_return_prop))
    m_outbound_prop = m_at_asteroid * (r_out - 1.0)
    m_launch        = m_at_asteroid + m_outbound_prop

    # Settle the ISRU books at the payload actually flown, so the reported feed
    # and the dig time below describe the same mission the cost model prices.
    if isru:
        isru_prop_kg = m_return_prop
        isru_feed_kg = isru_prop_kg * isru_feed_per_kg_prop
        if isru_feed_kg + feed_kg > throughput_cap_kg + 1e-6:
            return None
    isru_water_kg = isru_prop_kg * WATER_KG_PER_KG_HYDROLOX if isru else 0.0

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
    mining_yr = mining_duration_yr(feed_kg + isru_feed_kg, config)

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

    # Re-derive the plant's power at the final feed / payload / duration so the
    # cost matches the mission actually flown, not the sizing pass.
    if beneficiate or isru:
        processing_power_watts = processing_power_w(
            feed_kg + isru_feed_kg, m_payload if beneficiate else 0.0,
            mining_yr, dig_wh, benef_wh,
        )
    # ── Bound-water liberation (v1.7.0) ──────────────────────────────────────
    # C/B/D-type "ice" is water locked into phyllosilicates.  Selling it as
    # water means baking it out at ~700 K first, and that energy was free
    # until now.  Charged on the water actually delivered, on top of the
    # mechanical-separation energy above.
    #
    # v1.10.0: and on the water turned into propellant, which is the same bake
    # for the same reason.  ISRU that pays no liberation energy is ISRU that
    # boils water out of rock for free.
    water_kg = isru_water_kg
    if config.model_water_liberation:
        if beneficiate and payload_mix:
            water_kg += float(payload_mix.get("water", 0.0))
        elif not beneficiate:
            ice_frac = asteroid_row.get("comp_ice_fraction")
            if ice_frac is not None and not pd.isna(ice_frac):
                water_kg += m_payload * float(ice_frac)
    if water_kg > 0 and mining_yr > 0:
        water_wh = _ops_value(
            ops_df, "Water liberation energy (bound water)", default=2_500.0,
        )
        processing_power_watts += (
            water_wh * water_kg / (mining_yr * 365.25 * 24.0)
        )
        # That extra power needs extra array, which the cascade already
        # flew; recording it keeps the reported plant honest.
        if w_per_kg > 0:
            power_system_kg = processing_power_watts / w_per_kg
    cost                = mission_cost_usd(
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
    )

    # ── Market saturation (v1.7.0) ───────────────────────────────────────────
    # Selling is not free of consequence.  A mission that returns a
    # meaningful fraction of a commodity's annual market moves the price it
    # is being valued at.  Applied to the delivered RATE (kg per mission-year)
    # against Module 2's annual_market_kg, per commodity where the payload mix
    # is known, and on the payload as a whole otherwise.
    saturation_mult = 1.0
    if (config.model_market_saturation and mission_duration_yr > 0
            and phases and markets is not None):
        # The mix actually sold: chosen by the optimiser when concentrating,
        # otherwise the body's own proportions.
        if beneficiate and payload_mix:
            sold = dict(payload_mix)
        else:
            frac_sum = sum(f for _n, f, _p in phases)
            sold = {n: m_payload * f / frac_sum for n, f, _p in phases} if frac_sum > 0 else {}
        adj_value = 0.0
        for phase, kg in sold.items():
            price = next((p for n, _f, p in phases if n == phase), 0.0)
            adj_value += kg * price * saturation_price_multiplier(
                kg / mission_duration_yr,
                markets.get(phase, float("inf")),
                config.demand_elasticity,
            )
        if gross_value > 0:
            saturation_mult = adj_value / gross_value
        gross_value = adj_value
        delivered_value_per_kg = gross_value / m_payload if m_payload > 0 else 0.0

    # ── Mission reliability (v1.8.0) ─────────────────────────────────────────
    # Revenue was certain.  It is not.  Three independent ways to get nothing:
    # the launch fails, the spacecraft dies on the way, or the mining chain —
    # which has never been demonstrated anywhere — does not work when it
    # arrives.  Costs are still charged in FULL, which is both conservative
    # and correct: you spend the money either way.  The launch insurance
    # already in the cost model replaces hardware, not revenue, so this is not
    # a double count.
    p_success = 1.0
    if config.model_reliability:
        p_launch = _ops_value(ops_df, "Launch vehicle reliability", default=0.97)
        mtbf_yr  = _ops_value(ops_df, "Spacecraft mean time between failures", default=30.0)
        # v1.9.0: the mining chain LEARNS.  A programme's second rig is not as
        # likely to jam as its first, so p_mining is the fleet average over
        # nre_amortization_missions rather than the first-of-kind figure held
        # flat forever.  Launch and cruise reliability do not grow here —
        # launch vehicles are already mature, and MTBF is a duration exposure
        # rather than a heritage question.
        p_first = _ops_value(
            ops_df, "Mining system first-of-kind success probability", default=0.85,
        )
        if config.model_reliability_growth:
            p_mining = mining_success_probability(
                config.nre_amortization_missions, p_first,
                _ops_value(ops_df, "Mining reliability growth exponent", default=0.30),
                _ops_value(ops_df, "Mining system mature success probability", default=0.95),
            )
        else:
            p_mining = p_first
        p_cruise = math.exp(-mission_duration_yr / mtbf_yr) if mtbf_yr > 0 else 1.0
        p_success = max(0.0, min(1.0, p_launch * p_cruise * p_mining))
        gross_value *= p_success

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
        "synodic_period_yr":        synodic_yr,
        "launch_window_wait_yr":    window_wait_yr,
        "water_liberated_kg":       water_kg,
        "saturation_multiplier":    saturation_mult,
        "p_success":                p_success,
        "p_mining":                 p_mining if config.model_reliability else 1.0,
        "boiloff_factor":           boiloff_factor,
        "dv_ret_effective_m_s":     dv_ret_eff,
        "learning_curve_factor":    learning_curve_factor(
                                        config.nre_amortization_missions,
                                        config.learning_curve_rate),
        "processing_power_w":       processing_power_watts,
        "power_system_kg":          power_system_kg,
        "power_w_per_kg_at_target":  w_per_kg,
        "hardware_total_kg":        hardware_total_kg,
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
    profit = float(result.get("profit_usd", -np.inf))
    if str(config.selection_objective).strip().lower() == "profit":
        return (0.0, profit)
    if profit > 0:
        return (1.0, profit)
    gross = float(result.get("gross_value_usd", 0.0) or 0.0)
    cost  = float(result.get("total_cost_usd", 0.0) or 0.0)
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
    markets:           Optional[Dict[str, float]] = None,
    aero:              Optional[bool] = None,
    isru:              bool = False,
    rendezvous_apsis:  str = "",
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

    # Keep the best candidate under the selection objective — see
    # selection_key for why that is not simply the highest profit.
    best     = None
    best_key = (-np.inf, -np.inf)
    for vehicle, propellant in combos:
        isru_modes = [False]
        if config.use_isru_return_propellant and isru_feed_kg_per_kg_propellant(
                asteroid_row, propellant, config) is not None:
            # Feasible here.  Price both when searching; otherwise take ISRU as
            # the config's instruction and fly it wherever it is possible.
            isru_modes = [False, True] if isru_allowed else [True]
        for dv_opt in dv_options:
            for isru in isru_modes:
                result = evaluate_combo(
                    asteroid_row, vehicle, propellant,
                    bulk_value,
                    float(dv_opt["dv_out_m_s"]), float(dv_opt["dv_ret_m_s"]),
                    ops_df, config,
                    best_phase_value_per_kg=best_phase_value,
                    phases=phases, markets=markets,
                    aero=bool(dv_opt["aero"]), isru=isru,
                    rendezvous_apsis=str(dv_opt["rendezvous_apsis"]),
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
        if n >= 100 and (i * 100) // n != last_report:
            last_report = (i * 100) // n
            print(f"     … {i:,} / {n:,} evaluated  ({last_report}%)")

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
