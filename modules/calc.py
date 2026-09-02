# -*- coding: utf-8 -*-
"""calc, Module 4 of the Asteroid Profitability Pipeline.

Reads the catalogs produced by Modules 1-3 and computes, for every asteroid:

    1.  How much of each mineral category is present  (Module 1 × mass)
    2.  Gross value of the returned material           (Module 2 × yields)
    3.  Round-trip mission cost                        (Module 3 + rocket eq.)
    4.  Net profit, ROI, and $/kg-returned-cost        (the headline number)

The mission model is a return-sample architecture, UNCREWED throughout; 
the spacecraft is an autonomous mining platform with no life-support, no
crew habitat, and no human in the loop past LEO injection:

    Earth launch  →  LEO  →  outbound burn  →  asteroid rendezvous
        →  autonomous station-keeping + mining
        →  return burn  →  Earth re-entry  (sample-return capsule)

Mass cascade (no ISRU, default conservative):
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
ablates during entry.  This is a significant accuracy fix, omitting it
overstates max payload by ~30%.

`m_payload_returned` is solved closed-form against the vehicle's
payload-to-LEO capacity (s = 1 + tps_frac):
    m_payload_returned_max =
        (M_LEO / R_out − m_hardware − m_dry_return · s · R_ret) / (s · R_ret − 1)

Cost line-items (all from Module 3's reference tables; no values are
re-introduced here):
    launch + outbound prop + return prop + mining hardware recurring
    + mission ops × mission_duration_yr  + heat shield (if aerocapture)
    + sample recovery + 3rd-party liability + launch insurance %
    + spacecraft bus NRE / N_missions_amortization
    + autonomous mining control & AI NRE / N_missions_amortization
    × (1 + contingency_fraction)
    × (1 + WACC)^mission_duration_yr      ← time-value of money

Note: there is NO crew cost line in this cascade; every mission is
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
    print(f"PKG  Installing: {_missing} ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q"] + _missing
    )
    print("OK  Install complete")
else:
    print("OK  All packages present")


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import ast
import contextlib
import functools
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
# ║   ★  USER SETTINGS, EDIT THESE TO TUNE THE PIPELINE  ★                  ║
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
    # `m_hardware`     - mining rig + comms + structure that stays at asteroid
    # `m_dry_return`   - return vehicle dry mass (TPS frame + chute + structure,
    #                    NOT the ablative TPS itself which scales with payload)
    mining_hardware_kg:        float = 2_000

    # A FLOOR, not the whole return dry mass: `return_structure_frac_of_payload`
    # adds 15% of the haul on top of it.  Flat 500 kg gave 250:1
    # payload-to-structure against 0.4:1 (Cygnus) to 2:1 (Dragon) for real
    # cargo craft, and nothing else bounded returned mass.
    return_vehicle_dry_kg:     float = 500

    # ─── RETURN VEHICLE SCALES WITH ITS CARGO  (v1.10.0) ─────────────────────
    # `return_vehicle_dry_kg` was the WHOLE dry mass of the return vehicle, a
    # flat 500 kg however much it carried.  Since the payload is solved for
    # rather than specified, that let the cascade load 125 tonnes of ore into a
    # 500 kg can, a payload-to-structure ratio of 250:1, where real cargo
    # spacecraft run between 0.4:1 and 2:1.  Nothing caught it because the only
    # other check on returned mass was the launch vehicle's fairing VOLUME,
    # which a dense metal payload never fills.
    #
    # So the 500 kg becomes a floor, the irreducible avionics, comms, beacon
    # and separation hardware, and a structural fraction of the payload is
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
    # this is an engineering assumption, not a measurement; it sits here as a
    # single obvious dial rather than being buried as an implicit infinity.
    # For scale, OSIRIS-REx's TAGSAM collected ~122 g in a touch-and-go; a
    # continuous rig is a different machine entirely.
    mining_rate_kg_per_day_per_kg_rig: float = 0.10
    # Hard ceiling on time spent at the asteroid.  Binds the payload: you can
    # only return what you can dig in this long.  Also keeps ops cost and WACC
    # from compounding over an implausible stay.
    max_mining_duration_yr:            float = 3.0
    # Floor on time at the asteroid regardless of how little is mined: 
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
    #   • by CONTENT   - you cannot recover more than what you processed,
    #                    times the recovery efficiency
    #   • by PURITY    - you cannot make a concentrate richer than the best
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
    # `beneficiate=False`, which is not the same as ratio 1.0; see the
    # concentration search), so turning this on can only widen the option set.
    # A correctly-implemented search cannot get worse for that, which is the
    # never-worse invariant this project checks after every release.
    #
    # Checked anyway, on the full catalog at cislunar (2026-08-11, calc
    # 1.16.0): 650,921 pairs, max benef/raw 1.000000, ZERO exceptions, and
    # 102,765 bodies (15.79%) declining to concentrate at exactly 1.0, the
    # documented signature, never worse and equal wherever it declines.
    #
    # What it costs is TIME, and that is the only reason it was ever off: a
    # full beneficiated cislunar pass measured 9,300 s against raw's 1,307 s
    # on calc 1.16.0, a ratio of 7.1x.  Six performance-only releases later it
    # is 3,424 s against 733 s, a ratio of 4.67x (2026-08-24, full catalog).
    # Both figures come from MEASURED_CELL_SECONDS below; re-measure there
    # and every banner that quotes them moves with it.
    # Set False for the raw cell (26.7863x), which is what most of the older
    # tables in versions.md were measured at.
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
    # How hard to concentrate is an economic decision, not a setting; see
    # evaluate_combo.  This is how many points the profit sweep samples
    # between "don't concentrate" and "concentrate to pure best phase",
    # plus one refinement pass.  Raising it costs runtime linearly and buys
    # very little; 7 puts the optimum within a few percent.
    concentration_search_steps: int  = 7

    # ─── MODELLING COMPLETENESS  (v1.7.0) ────────────────────────────────────
    # Five things the pipeline previously got for free.  All default ON; 
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
    # NEAs hardest; their periods are near Earth's, so windows are years
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

    # The elasticity in P/P0 = (1 + Q/Q_market)^(-1/eps).  0.5 is inelastic,
    # which is right for precious metals: doubling world supply quarters the
    # price.  Raising it makes the market absorb more before the price moves.
    demand_elasticity:         float = 0.5

    # ─── MODELLING COMPLETENESS, PART 2  (v1.8.0) ────────────────────────────
    # RIG SERVICE LIFE AND TERMINAL VALUE.  The rig was amortised across
    # `nre_amortization_missions` with no upper bound, so a programme could
    # spread one rig across 100 missions of 2 years each: 200 years of duty
    # from a machine chewing rock.  It now has a finite life (Module 3, 15 yr),
    # which CAPS the amortisation, and whatever life is left when the
    # programme ends is credited back at the salvage fraction.
    #
    # The cap is the part that bites: at long stays it makes the rig markedly
    # MORE expensive than the old flat division, not less.  Terminal value is
    # only credited when there is a programme to inherit the rig
    # (nre_amortization_missions > 1), a rig parked at an asteroid nobody
    # returns to is stranded, not an asset.
    model_rig_service_life:    bool  = True

    # MISSION RELIABILITY.  Revenue was certain.  It is not: the launch can
    # fail, the spacecraft can die in transit, and the mining chain has never
    # been demonstrated at all.  Expected revenue is multiplied by
    #     P = p_launch · exp(−T/MTBF) · p_mining
    # while COSTS are still charged in full, which is the conservative and
    # correct treatment; you spend the money either way.  Launch insurance
    # already in the cost model replaces hardware on failure, not revenue, so
    # there is no double count.
    model_reliability:         bool  = True
    # RELIABILITY GROWTH.  The mining chain learns: a programme's second rig
    # is not as likely to jam as its first.  p_mining becomes the FLEET
    # AVERAGE over nre_amortization_missions under the Duane model, capped at
    # a mature ceiling.  Exactly the first-of-kind figure at N = 1.
    # Launch and cruise reliability deliberately do NOT grow; launch vehicles
    # are already mature, and MTBF is a duration exposure, not a heritage
    # question.
    model_reliability_growth:  bool  = True

    # CRYOGENIC BOIL-OFF.  Return propellant sits in the tank from launch
    # until the departure burn, years, not hours.  Hydrolox loses ~0.05%/day
    # even with active cooling, which over a 5-year mission means loading 2.5×
    # what the rocket equation says you burn.  Without this, hydrolox wins
    # long missions it could not physically store propellant for.  ISRU return
    # propellant is exempt: it is manufactured at the asteroid on departure.
    model_propellant_boiloff:  bool  = True

    # PROPELLANT TANKAGE (v1.11.0).  A tank's mass scales with the VOLUME it
    # encloses, so leaving it out of the cascade subsidised whichever propellant
    # had the lowest density, which is the same propellant that has the
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

    # A SUPPLY cap rather than a money cap.  DOE makes ~1.5 kg of Pu-238 a
    # year, about one flagship RTG for the entire world, so a mission wanting
    # more than this goes back to solar and pays the mass.
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
    #     load and recharge the store, [(1−f) + f/η]/(1−f) = 2.11× at f = 0.50.
    #     This is a sizing factor, so no W/kg figure could ever have carried it.
    #   • the store itself has to hold the load across the dark period, which is
    #     set by the BODY'S OWN rotation period, so this term is per-asteroid,
    #     and a slow rotator is genuinely a worse place to mine.
    #
    # Exempt: a radioisotope plant (flat output, no night) and the EP array
    # (interplanetary cruise, permanent sunlight).  Both exemptions are physical
    # rather than conservative, and the RTG one has a visible consequence; 
    # eclipse is what finally makes the radioisotope branch worth choosing on
    # more than a rounding number of bodies.
    model_eclipse_power:       bool  = True
    # Median of the 29,288 catalog bodies that have a MEASURED rotation period
    # (2026-08-08).  Used only where the body does not state one, about two
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
    # has asked for this since v1.4.0, its 27 t to escape EXCEEDS its 21 t to
    # GTO precisely because it assumes refuelling, and until now its escape
    # payload was priced at one $90M launch.
    #
    # v1.12.0: the charge is real but it belongs to the ESCAPE-DIRECT scenario,
    # which is what the Module 3 note actually asked for and which this module
    # does not have.  Stage 4 reads `payload_leo_kg` / `usd_per_kg_to_leo` and
    # nothing else; the vehicle is a LEO lifter and the stack departs on its
    # own outbound stage, so no mission here is ever refuelled, and v1.11.0
    # was billing $1.08B for a capability it never used.  Setting
    # `escape_direct_launch` True re-arms it, and nothing does that yet.
    charge_tanker_flights:     bool  = True

    # Gates the tanker charge above.  Nothing sets it, because this module has
    # no escape-direct architecture to bill: it reads payload_leo_kg and
    # usd_per_kg_to_leo and nothing else.  Kept wired for the day it does.
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
    # Applied uniformly to every asteroid (v1.3.5, per-target Asterank Δv
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
    #   "earth_surface": re-entry capsule, Earth recovery campaign, full
    #                     launch + re-entry Part 450 licence.  Cheapest return
    #                     Δv (direct entry needs no capture burn at all), but
    #                     the cargo is worth terrestrial commodity prices.
    #   "leo"           - berthed at an LEO depot.  No re-entry, so no capsule,
    #                     no recovery campaign, launch-only licence.  The most
    #                     EXPENSIVE return Δv in the model: circularising into
    #                     LEO means killing the whole arrival hyperbola.
    #   "cislunar"      - berthed at an NRHO depot.  Same cost savings as LEO,
    #                     and the cheapest return Δv of the orbital options,
    #                     because capture only has to bind the orbit and the
    #                     burn takes the Oberth benefit at low perigee.
    #   "lunar_surface", landed at a Moon base.  Cislunar capture plus
    #                     2.6 km/s of NRHO→LLO→surface, all propulsive; the
    #                     Moon has no atmosphere to brake against.  Carries a
    #                     $200k/kg lander instead of a berthing adapter.
    #   "mars_surface"  - landed at a Mars base.  NOT an Earth return: the
    #                     heliocentric transfer runs from the asteroid's orbit
    #                     to Mars' (1.524 AU), so the departure burn, arrival
    #                     v_infinity and capture are all separately computed
    #                     (_asteroid_to_mars_dv_km_s).  Many NEAs have aphelia
    #                     out near Mars and are genuinely closer to it than to
    #                     Earth.  Aerocapture is available and worth several
    #                     km/s.
    #   "mars_orbit"    - berthed at a 1-sol Mars-orbit depot (250 x 33,793
    #                     km, NASA DRA 5.0).  The same heliocentric transfer
    #                     as mars_surface, stopped one leg early: capture
    #                     BINDS the ellipse rather than circularising, 0.90
    #                     km/s against 2.10, and nothing lands, so there is no
    #                     descent burn and no lander.  Berthing adapter at
    #                     $60k/kg.  Aerocapture available.
    #
    # See DELIVERY_ARCHITECTURES for what each one actually changes.
    delivery_destination:      str   = "earth_surface"

    # ─── WHAT THE PER-ASTEROID SEARCH OPTIMISES  (v1.10.0) ───────────────────
    # Every search in this module, concentration ratio, vehicle, propellant,
    # return mode, propellant sourcing, has to rank candidate missions by
    # something, and until v1.10.0 that something was `profit_usd`.  In this
    # model revenue sits orders of magnitude below cost, so profit is very
    # nearly minus the cost, and maximising it quietly became "pick the
    # cheapest mission", while the project ranked the output by a cost/revenue
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
    # once for the whole catalog instead, whether to aerocapture, and whether
    # to make return propellant on site, even though the right answer to both
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
    # Return Δv is reduced, per asteroid, from its own arrival v_infinity, 
    # but a heat-shield mass overhead is added at the rate from Module 3, and
    # that mass is hauled outbound AND pushed back through the return burn.
    # Only available where the architecture actually enters an atmosphere:
    # earth_surface (direct entry), leo (aerocapture + aerobraking) and
    # mars_surface.  Cislunar and lunar_surface ignore it; see uses_tps().
    use_aerocapture_return:    bool  = True
    aerocapture_dv_savings_m_s: float = 4_000   # fallback only, when elements are unusable
    heat_shield_frac_of_payload: float = 0.15   # TPS mass = 15% of returned payload

    # ─── ISRU  (return propellant manufactured at the asteroid) ──────────────
    # Return propellant is not hauled outbound; it is electrolysed from mined
    # water.  Available only where that is physically possible, a hydrolox
    # stage at a body with a non-zero ice fraction, and the rock it takes to
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
    # made.  The mining, hauling and water-liberation energy are NOT in here; 
    # they are charged through the feed, the dig time and the power plant.
    isru_processing_usd_per_kg:    float = 50.0

    # ─── COST AMORTISATION & FINANCIAL ───────────────────────────────────────
    # Spacecraft development NRE (~$588M for OSIRIS-REx class).  If 1, the
    # first mission carries the full NRE; raise N to spread across a fleet.
    nre_amortization_missions: int   = 1
    # ─── PROGRAMME SCALE AND FLEET SIZE (v1.15.0) ────────────────────────────
    # `nre_amortization_missions` above is N, the programme size, and until
    # v1.15.0 it was an INPUT; the curve of answer-against-N was mapped by
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
    # run no longer reproduces them; set this False to do that.  This comment
    # used to argue the flip would "silently retire every committed figure at
    # once with no way to reproduce them", and the second half of that was the
    # real objection: the two settings had never been measured side by side on
    # the real population, so OFF was the only anchor anyone had.
    #
    # That is no longer true.  The full cislunar 2x2 was measured on the full
    # 1.55 M-row catalog on 2026-08-11 (calc 1.16.0) and is in versions.md, and
    # the OFF cells reproduce their committed values exactly: 26.7863x raw and
    # 20.5895x beneficiated, both unmoved across four releases.  The N = 1
    # answer is now a recorded measurement rather than a thing you would lose.
    #
    # It is NOT free.  Measured at 2.98x runtime on the full raw cislunar cell
    # on calc 1.16.0 (1,307 s -> 3,890 s); on 1.17.7 it is 1.71x (733 s ->
    # 1,253 s), which is MEASURED_CELL_SECONDS below and is where every banner
    # quoting this ratio reads it from.  The cost is real because the 2-D
    # (F, W) search prices 40
    # programmes per surviving candidate against the 1-D ladder's 8.  The
    # sample this release was developed on predicted 1.10x, and v1.15.0's
    # 1-D ladder measured 1.51x; neither carries over.
    #
    # ✅  THE KNOWN GAP THIS COMMENT USED TO DESCRIBE IS CLOSED IN v1.16.0 by
    # `model_programme_calendar` below.  It read: the fleet is only ever the
    # MINIMUM that can fly N missions, because a programme of F ships flying
    # `trips` campaigns each spans `trips × mission_duration` of calendar and
    # nothing charged for it, so buying a second ship only ever added market
    # saturation, and F never wanted to exceed ceil(N / trips).  Fleet size was
    # a one-sided decision.  It is now two-sided, and the search is
    # two-dimensional over (F, W) rather than a ladder over F.
    optimise_programme_scale:  bool  = True
    # Upper bound on the fleet search.  Not a physical limit; it is where the
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
    # 12 consecutive campaigns; a bound derived entirely from a figure about
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
    # True charges the difference; see `programme_calendar_multipliers` for
    # the derivation and for why the rig's salvage credit is compounded the
    # OTHER way.  Exactly 1.0 at W = 1, so every single-mission figure in this
    # project is untouched, which is every committed figure except the
    # N = 10 / N = 100 curve.
    #
    # It also makes the programme search two-dimensional.  Campaigns-per-ship
    # was not previously a decision, every lever improved with N, so the
    # optimum was always the top of a fleet band, and the calendar charge is
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
    # Time-value of money; compound up-front costs over mission_duration_yr.
    apply_wacc_compounding:    bool  = True

    # Flat contingency on the whole cost cascade, applied after every other
    # line and before WACC.
    contingency_fraction:      float = 0.20

    # ─── VEHICLE / PROPELLANT SELECTION ──────────────────────────────────────
    # None = use everything operational; set lists to restrict candidates.
    candidate_vehicles:        Optional[List[str]] = None
    candidate_propellants:     Optional[List[str]] = None  # and the same, for propellants

    # False admits Stage 3's development and concept rows.  That is where the
    # 10,000 g launchers live, and max_payload_accel_g is what keeps them out
    # once they are admitted.
    operational_vehicles_only: bool = True
    # v1.11.0.  Module 3 v1.9.0 grew the propellant table from 7 rows to 40,
    # and 17 of the additions are development or concept hardware: nuclear
    # thermal, VASIMR, fusion, an Orion pulse drive.  Left ungated, a search
    # that maximises profit would fly every asteroid on antimatter.  This
    # mirrors `operational_vehicles_only` exactly: True keeps the search to
    # propellants that have actually moved a spacecraft.  Retired rows
    # (mercury ion) are excluded either way.
    operational_propellants_only: bool = True

    # ─── DISPLAY ─────────────────────────────────────────────────────────────
    top_n_preview:             int = 20   # rows in the printed top-N ranking
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
    # 2026-08-24 at cislunar, six physical cores / 12 workers, calc 1.17.7, on
    # the full 1,555,667-row catalog:
    #     raw, N = 1            733 s     650,921 evaluable rows
    #     raw, searched       1,253 s
    #     beneficiated, N = 1 3,424 s     660,253 evaluable rows
    #     beneficiated+search 5,692 s     <- BOTH DEFAULT ON since v1.17.0
    # cislunar is the CHEAPEST destination; leo, mars_surface and earth_surface
    # cost 2.1-2.7x more per cell.  All twenty are in README.md.
    #
    # ⚠️  DO NOT BUDGET BY SCALING A SMALL RUN.  Scaling a 20,000-row sample
    # predicted 2.2 h for a raw run that took 42 minutes -- a 3.1x
    # overestimate.  Fixed costs (worker startup, loading a 0.88 GB catalog)
    # dominate a small run, and parallel efficiency is much better on a large
    # one, so per-row cost falls sharply with size.  It is not linear.
    #
    # ⚠️  And it misses in BOTH directions: the beneficiated cell sat here as
    # "~2.2 h ESTIMATED" from that same sample's 3.12x ratio, and measured
    # 10.6 h on calc 1.14.0 -- 4.8x the other way.  versions.md's sampling rule
    # is the general statement; the four numbers above are measurements.
    eval_row_cap:              int = 0

    # HOW a cap selects its rows.  Only consulted when eval_row_cap > 0.
    #   "stride", take every Nth row across the whole sorted catalog
    #   "head"   - take the first N rows (the pre-v1.13.0 behaviour)
    #
    # Stride is the default because the catalog reaches this module sorted by
    # semi-major axis, so `head` was never a sample of the catalog; it was the
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
    #   0  - auto.  One worker per logical CPU, scaled down when there are too
    #        few asteroids to repay the spawn cost (no fork on Windows, so each
    #        worker is a fresh interpreter plus a pandas import).
    #   1  - force the serial path.  Use it to profile, or when an outer
    #        harness already runs one process per destination and the cores are
    #        spoken for.
    #  >1  - exactly that many workers, clamped to the CPU count.
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
    # is no mission behind it to lose: measured on 68,136 (combo × dv × ISRU)
    # tuples across both settings at cislunar, zero of the pruned candidates
    # produced a result when solved in full.
    #
    # Turn it OFF to check that claim on a population this repo has not tried,
    # or to profile the unpruned search.  Do not turn it off because a number
    # looks wrong; if pruning ever changes an output, that is a BUG in the
    # pre-filter and the two builds should be diffed column by column.
    prune_infeasible_combos:   bool = True

    # ─── PIPELINE VERSION ────────────────────────────────────────────────────
    # Stamped into every output CSV, and the only way to tell which code
    # produced a given catalog.  BUMP IT when a change moves any number a run
    # produces.  The rule is ONE-DIRECTIONAL: changing a number means bumping,
    # and a bump does NOT mean a number changed, which is why nothing may read
    # a version as evidence that a result moved.
    # THE CHANGELOG IS versions.md, NOT THIS COMMENT.  It used to be 1,328 lines
    # of release notes sitting right here, a second copy of a record versions.md
    # already held, which is the documentation form of the defect this project
    # keeps cataloguing; it was also what the dashboard rendered as this field's
    # help text, because ui_meta scrapes a field's comment block.  Moved out on
    # 2026-09-02.  Two places to write, neither of them here:
    #     versions.md > Releases            what the release did, and what it
    #                                       measured to say so
    #     versions.md > Module changelogs   this module's own stamp-by-stamp
    #                                       record: Stage 4 changelog
    pipeline_version: str = "1.18.0"


# ═════════════════════════════════════════════════════════════════════════════
#  MEASURED RUNTIME: the ONE place these numbers live
# ═════════════════════════════════════════════════════════════════════════════
# Wall clock for the four cislunar cells, full 1,555,667-row catalog, six
# physical cores / 12 workers, calc 1.17.7, measured 2026-08-24.  All twenty
# cells are tabulated in README.md under "Beneficiation".
#
# 🚨  EVERY user-facing quote of these ratios DERIVES from this dict: the
# --help text and run banner in run_pipeline.py, the MASTER CONFIG READY banner
# build_master.py writes into master.py, and the sidebar estimate in ui.py.
# They used to be five hand-copied literals, and they went stale together: the
# superseded 1.16.0 figures ("~7x" beneficiation, "~3x" the programme search)
# were still being PRINTED TO THE USER ON EVERY RUN three releases after the
# measurement that retired them.  A banner is the most-read copy of a number in
# this project and was the least checked.  Re-measure, edit here, and every
# consumer moves with it; `verify_docs.py` check 9 holds README's own table to
# the same values.
#
# ⚠️  These are CISLUNAR, the cheapest destination.  leo, mars_surface and
# earth_surface cost 2.1-2.7x more per cell.
MEASURED_CELL_SECONDS: Dict[Tuple[bool, bool], int] = {
    # (use_beneficiation, optimise_programme_scale): seconds
    (False, False):   733,   # run-of-mine ore, one mission
    (False, True):  1_253,   # run-of-mine ore, programme searched
    (True,  False): 3_424,   # concentrate, one mission
    (True,  True):  5_692,   # concentrate + programme search  <- BOTH DEFAULT ON
}
MEASURED_CELL_ROWS = 1_555_667   # catalog the cells above were measured on


def beneficiation_cost_ratio(search: bool = False) -> float:
    """How much longer a beneficiated pass takes than a raw one, same search."""
    return (MEASURED_CELL_SECONDS[(True, search)]
            / MEASURED_CELL_SECONDS[(False, search)])


def programme_search_cost_ratio(beneficiated: bool = False) -> float:
    """How much longer the programme search takes than N = 1, same ore."""
    return (MEASURED_CELL_SECONDS[(beneficiated, True)]
            / MEASURED_CELL_SECONDS[(beneficiated, False)])


CONFIG = CalcConfig()
os.makedirs(CONFIG.output_dir, exist_ok=True)

print(f"OK  Configuration loaded - output dir: {CONFIG.output_dir}")
print(f"    Hardware       : {CONFIG.mining_hardware_kg:,.0f} kg mining rig "
      f"+ {CONFIG.return_vehicle_dry_kg:,.0f} kg return-capsule dry")
print(f"    Mining cap     : {CONFIG.max_mining_fraction:.0%} of asteroid mass per mission")
# Default ON as of v1.17.0, and the cost is quoted from MEASURED_CELL_SECONDS
# rather than typed, so a re-measurement cannot leave this banner behind.
print(f"    Beneficiation  : "
      + ("concentrate, ~%.1fx the runtime of a raw pass "
         "(search also prices not concentrating at all)"
         % beneficiation_cost_ratio(CONFIG.optimise_programme_scale)
         if CONFIG.use_beneficiation else
         "off - run-of-mine ore at bulk grade"))
print(f"    Return mode    : "
      f"{'aerocapture available (per-asteroid dv saving vs TPS mass)' if CONFIG.use_aerocapture_return else 'propulsive only'}")
print(f"    ISRU           : {'available where the rock has water' if CONFIG.use_isru_return_propellant else 'off'}")
print(f"    Architecture   : "
      f"{'searched per asteroid' if CONFIG.optimise_architecture_per_asteroid else 'fixed by config'}")
print(f"    Contingency    : {CONFIG.contingency_fraction:.0%}  |  "
      f"NRE amortised over {CONFIG.nre_amortization_missions} mission(s)")
print(f"    Programme      : "
      + ("(fleet <= %d) x (campaigns/ship) searched; N follows (~%.1fx runtime)"
         % (CONFIG.max_fleet_ships,
            programme_search_cost_ratio(CONFIG.use_beneficiation))
         if CONFIG.optimise_programme_scale else
         f"fixed at N = {CONFIG.nre_amortization_missions} "
         f"(set optimise_programme_scale to search it)"))
print(f"    Calendar       : "
      + ("programme span charged - amortised NRE and rig compound over "
         "T + (W-1)xcadence" if CONFIG.model_programme_calendar else
         "NOT charged (model_programme_calendar off - reproduces 1.15.0)"))


# ─────────────────────────────────────────────────────────────────────────────
# CATALOG LOADER  (reads Module 1, 2, 3 CSVs)
# ─────────────────────────────────────────────────────────────────────────────
def _load_csv(path: str, label: str) -> pd.DataFrame:
    """Read a CSV with friendly error reporting.

    ⚠️  v1.17.7: `low_memory=False`, and it is about DETERMINISM rather than
    memory.  The default reader infers each column's dtype from CHUNKS, so the
    dtype it lands on depends on how the values happen to be distributed across
    them, which is the same "the dtype depends on the data" hazard that cost
    NEOWISE four releases, one level lower down.  It also emitted
    `DtypeWarning: Columns (3,22) have mixed types` on every single load of the
    1.55 M-row catalog (`is_neo` and `source_jpl`, both bool-plus-NaN), and a
    warning that always fires is a warning nobody reads; this file's own rule
    against suppressing warnings in `catalog.py` cuts the same way here: remove
    the cause so a real one stands out.

    ⚠️  Taken only because it was MEASURED neutral, not because it looks safe:
    on the real 1,555,667-row catalog, single-pass against chunked inference
    gives **0 of 46 columns with a different dtype and 0 with a different
    value**.  A dtype change here would propagate into the mass cascade, which
    is exactly the class of "harmless cleanup" this file keeps declining, so
    if the catalog's schema changes, re-measure before assuming it still holds.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{label} not found at {path}: has the upstream module been run?"
        )
    df = pd.read_csv(path, low_memory=False)
    print(f"       {label:28s} {len(df):>7,} rows  <-  {path}")
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


def _parse_minerals_column(col: pd.Series) -> pd.Series:
    """`_parse_minerals_list` over a whole column, priced by DISTINCT value.

    v1.17.4.  Composition is assigned from the spectral taxonomy, so this
    column takes **25 distinct values over the full 1,555,667-row catalog**, 
    and it was being `ast.literal_eval`'d once per ROW.  1.55 million parses to
    produce twenty-five answers, measured at **~28 s**: more than the 862 MB
    CSV read that precedes it, more than `integrity_check`, and more than the
    entire mission search on any sample-sized run.

    Nobody had profiled the LOAD.  Every performance release in this project
    (`1.10.1`, `1.14.1`, `1.14.2`, `1.17.1`, `1.17.2`) went after the search,
    because that is where a full-catalog run spends its hours, and a fixed
    ~30 s that a full run can ignore is most of the wall clock of the 150- and
    400-row cells this project actually verifies itself on.

    Same shape as every other memo here (`_OPS_CACHE`, `_PHASE_ORDER_CACHE`,
    `_ops_sizing_constants`): the loop was never the cost, the repetition was.

    ⚠️  Each row gets its OWN list rather than a shared one.  Nothing in this
    module mutates the column; `integrity_check` is its only reader and it
    only iterates, but a 62,000-way alias on a mutable object is exactly the
    quiet kind of trap this repo keeps finding, and 1.55 M list copies cost
    ~0.4 s against the ~28 s the parse cost.  Buy the safety.

    `factorize` rather than `unique` + `map` because it is total: NaN is a
    code like any other, so a missing composition cannot fall through a dict
    lookup that `nan != nan` would break.
    """
    codes, uniques = pd.factorize(col, use_na_sentinel=False)
    parsed = [_parse_minerals_list(u) for u in uniques]
    return pd.Series([list(parsed[c]) for c in codes],
                     index=col.index, name=col.name)


def load_all_catalogs(config: CalcConfig) -> Dict[str, pd.DataFrame]:
    """Load and lightly normalise the three upstream catalogs."""
    print("\n  Loading upstream catalogs ...")

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
        catalogs["asteroids"]["comp_minerals"] = _parse_minerals_column(
            catalogs["asteroids"]["comp_minerals"]
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
    with a re-entry-capsule mission; exactly the inconsistency the
    destination field exists to prevent.
    """
    minerals = catalogs.get("minerals")
    if minerals is None or "delivery_destination" not in minerals.columns:
        print("     WARN   Module 2 catalog carries no `delivery_destination` "
              "column (pre-v1.3.0) - cannot verify pricing matches this "
              "mission architecture.  Re-run Module 2.")
        return

    stamped = str(minerals["delivery_destination"].iloc[0]).strip().lower()
    mine    = str(config.delivery_destination).strip().lower()
    if stamped == mine:
        arch = delivery_architecture(mine)
        print(f"     OK  Delivery destination '{mine}' - {arch['label']}")
        return

    print(f"     FAIL  DESTINATION MISMATCH - the prices and the mission disagree.")
    print(f"          Module 2 priced the material for : {stamped}")
    print(f"          Module 4 is flying it to         : {mine}")
    print(f"        -> Every profit number in this run is meaningless.  Set both")
    print(f"          MINERAL_CONFIG.delivery_destination and")
    print(f"          CALC_CONFIG.delivery_destination to the same value and")
    print(f"          re-run Module 2 before Module 4.")


def integrity_check(catalogs: Dict[str, pd.DataFrame]) -> None:
    """Verify every mineral named by Module 1 is priced by Module 2.

    This catches the silent failure where a future Module 1 taxonomy edit
    introduces a new mineral that Module 2 has no row for, without this
    check, those minerals would simply not contribute to value (silently).
    """
    print("\n  Integrity check - Module 1 <-> Module 2 mineral coverage ...")

    asteroids   = catalogs["asteroids"]
    mineral_set = set(catalogs["minerals"]["name"].astype(str))

    if "comp_minerals" not in asteroids.columns:
        print("     WARN  asteroid catalog has no `comp_minerals` column - skipping check")
        return

    # Every unique mineral name the asteroid catalog references.
    #
    # v1.17.4: over the DISTINCT compositions rather than over every row.  This
    # walked 1.55 million lists: 6.2 million generator steps and 1.55 million
    # `set.update` calls, ~4 s, to build a set of twelve names out of the
    # twenty-five distinct compositions the taxonomy can produce.  Same finding
    # as `_parse_minerals_column` directly above it, and found the same way.
    #
    # A list is not hashable, so the distinct compositions are keyed as tuples
    # and `factorize` reduces them to one entry per composition present.
    #
    # ⚠️  The `isinstance` guard is the OLD loop's guard, kept and not folded
    # into a bare `.map(tuple)`.  `load_all_catalogs` hands this column over
    # already parsed, but nothing forces a caller to, and `tuple()` of the
    # UNPARSED string explodes it into one entry per character, which would
    # report a screenful of one-letter minerals as missing from Module 2.  A
    # loud false alarm in the check that exists to be trusted is still a
    # failure, and skipping non-lists is what the row-by-row walk did.
    referenced = set()
    _, comp_uniques = pd.factorize(
        asteroids["comp_minerals"].map(
            lambda v: tuple(v) if isinstance(v, list) else None),
        use_na_sentinel=False,
    )
    for mins in comp_uniques:
        if isinstance(mins, tuple):
            referenced.update(str(m) for m in mins if m)

    missing = referenced - mineral_set
    extra   = mineral_set - referenced

    if missing:
        print(f"     FAIL  {len(missing)} mineral(s) named by Module 1 but ABSENT in Module 2:")
        for m in sorted(missing):
            print(f"          * {m}")
        print("        -> Module 4 will treat these as zero-value contributions.")
    else:
        print(f"     OK  All {len(referenced)} referenced minerals are priced by Module 2")

    if extra:
        # Not an error; Module 2 prices elements (Au, Pt, …) that Module 1
        # doesn't name directly.  Just informational.
        print(f"     NOTE   Module 2 prices {len(extra)} extra rows not named by Module 1 "
              f"(expected: elements + ice + bulk categories)")

    schema_check(catalogs)
    # The VALUE half of the same question: schema_check asks whether the
    # columns and rows are present, stamp_check asks whether the file was
    # written by the Module 3 in this process.  A catalog can pass the
    # first and fail the second, which is exactly the v1.12.0 argon case.
    stamp_check(catalogs)


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
# missing ROW and `schema_check` above, which tests columns, cannot see it.
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

    Stage 3 is the cheap stage, so it is the one people skip re-running, and
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
    print(f"\n     WARN  Module 3 catalog is STALE - {len(stale)} column(s)/row(s) "
          f"this version reads are missing:")
    for key, col, consequence in stale:
        print(f"          * {key}.{col}  ->  {consequence}")
    print("        -> Re-run Stage 3 (transportation).  It takes seconds, and "
          "until you do, the numbers below are not comparable to any "
          "committed figure.")


def stamp_check(catalogs: Dict[str, pd.DataFrame]) -> bool:
    """Compare the transportation version STAMPED in each Stage 3 CSV against
    the Module 3 in this process.  Returns True when they agree or cannot be
    compared.

    This closes the half of the staleness problem `schema_check` cannot see.
    That one asks whether the columns and rows this module reads are PRESENT;
    it passes cleanly on a catalog whose VALUES are a release out of date,
    because editing a density or a boil-off rate leaves the schema identical.

    It is not a hypothetical.  During v1.12.0 the argon rows were rewritten,
    Stage 3 was re-run, the CSV did not actually land, and two full-catalog
    runs plus a determinism sweep were measured against the table that was
    being replaced.  Nothing anywhere said so.  The documented mitigation was
    to read Stage 4's row counts against what Stage 3 said it wrote, by eye,
    every time -- which is the kind of habit that works until the day it
    matters.

    What makes this checkable at all is that Stage 3 already stamps its
    `pipeline_version` into every CSV it writes, so the file records the code
    that produced it.  Comparing that to the live module turns "changing any
    number means bumping the version" from a rule someone has to remember into
    one the pipeline enforces on the way past.

    ⚠️  It is a DIAGNOSTIC, not an import.  `TRANSPORT_CONFIG` exists only when
    both modules are in one process, which is `master.py`, the normal path.  A
    standalone `calc.py` run has no way to know what Module 3 currently says
    and this returns True rather than inventing a complaint it cannot support.
    That is deliberate: the modules hand off through CSVs on disk and must not
    grow an import edge for a warning.
    """
    transport = globals().get("TRANSPORT_CONFIG")
    live = getattr(transport, "pipeline_version", None)
    if not live:
        return True                       # standalone calc.py: nothing to compare

    mismatched = []
    for key, df in sorted(catalogs.items()):
        if df is None or "pipeline_version" not in getattr(df, "columns", ()):
            continue
        stamps = {str(v) for v in df["pipeline_version"].dropna().unique()}
        for stamped in sorted(stamps):
            if stamped != str(live):
                mismatched.append((key, stamped))

    if not mismatched:
        return True

    print(f"\n     WARN  Module 3 catalog was written by a DIFFERENT "
          f"transportation build (this process is {live}):")
    for key, stamped in mismatched:
        print(f"          * {key}.csv stamped {stamped}")
    print("        -> The columns are all present, so nothing else will "
          "complain, but a reference VALUE may be a release out of date.")
    print("        -> Re-run Stage 3 (transportation) before trusting any "
          "number below, or before comparing one to a committed figure.")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# MINERAL-VALUE LOOKUPS
# ─────────────────────────────────────────────────────────────────────────────
# Rare-metal elements that get scaled by per-asteroid PGM-enrichment
# factor (Module 1 v1.0.4's comp_pgm_enrichment column).  The base metals
# (iron, nickel, cobalt) in nickel-iron alloy are NOT scaled; they are
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
    portion (Pt, Pd, Rh, Ir, Os, Ru, Au) by `pgm_enrichment`, the per-
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


# ── Composition is a per-TAXONOMY fact, not a per-row one  (v1.17.6) ────────
# `asteroid_bulk_value_usd_per_kg`, `asteroid_phase_table` and
# `asteroid_best_phase_usd_per_kg` read exactly five values off the row, the
# PGM enrichment and the four taxonomy fractions, and nothing else.  All five
# come out of Module 1's `enrich_composition`, which derives them from
# `spectral_type` alone: 76 distinct types across 1,555,667 rows, collapsing to
# ~25 distinct composition tuples (11 in a 4,000-row stride).
#
# So `evaluate_asteroid` was walking `FRACTION_TO_MINERAL` three times per
# asteroid, with a `pd.isna` on a scalar per entry, at ~1 us each, to
# re-derive one of a couple of dozen answers, once for every body in the
# catalog.  Measured on a 4,000-row stride of the real catalog:
#
#     asteroid_bulk_value_usd_per_kg   14.84 us/row  ->  23.1 s / full pass
#     asteroid_phase_table             13.97 us/row  ->  21.7 s / full pass
#     asteroid_best_phase_usd_per_kg   27.66 us/row  ->  43.0 s / full pass
#
# ~88 s of every full-catalog pass, paid by every row whether or not it turns
# out to be evaluable.  Exactly the pattern v1.17.4 found on both sides of the
# CSV boundary, "a column with few distinct values and one Python call per
# row", in the one place between them that release did not look.
#
# ⚠️  `asteroid_best_phase_usd_per_kg` calls the bulk function itself, so a
# beneficiated run computed the bulk value TWICE per asteroid.  The memo closes
# that as a side effect; it is not a separate change.
#
# Bit-identical by construction: the same key re-runs the same walk over the
# same mineral table, so the cached floats ARE the floats the walk produced.
_COMPOSITION_CACHE: Tuple[Any, Dict[Tuple[Any, ...], Any]] = (None, {})


def _composition_cache(mineral_df: pd.DataFrame) -> Dict[Tuple[Any, ...], Any]:
    """The memo for `mineral_df`, cleared when the frame changes.

    Single-slot on frame IDENTITY, the same shape as `_MINERAL_CACHE`,
    `_MARKET_CACHE` and `_OPS_CACHE`, prices are what the answers are made of,
    so a re-priced Stage 2 catalog must not read a cached value.
    """
    global _COMPOSITION_CACHE
    cached_df, entries = _COMPOSITION_CACHE
    if cached_df is not mineral_df:
        entries = {}
        _COMPOSITION_CACHE = (mineral_df, entries)
    return entries


# The five values the three functions below read, in a fixed order.
_COMPOSITION_KEY_COLS: Tuple[str, ...] = (
    ("comp_pgm_enrichment",) + tuple(FRACTION_TO_MINERAL)
)


class _CompositionValues:
    """The three composition-derived answers, filled in as they are asked for.

    A tiny `__slots__` object rather than a mutable 3-list because the three
    fields are read by name in three different functions and a positional index
    would be one more thing to keep in step -- the same reason
    `_ops_cost_constants` is unpacked in a single statement.  `None` means "not
    computed yet", which is distinguishable from every value these three can
    legitimately return (all are floats, or a list).
    """
    __slots__ = ("bulk", "phases", "best")

    def __init__(self) -> None:
        """All three slots start as None, meaning "not computed yet".

        Distinguishable from every value they can legitimately hold, which are
        all floats or a list, so a miss is never confused with a real answer of
        zero. `__slots__` is what keeps ~25 of these off the per-instance dict.
        """
        self.bulk = None
        self.phases = None
        self.best = None


def _composition_entry(
    entries: Dict[Tuple[Any, ...], "_CompositionValues"], key: Tuple[Any, ...],
) -> "_CompositionValues":
    """The entry for `key`, created empty on first use."""
    hit = entries.get(key)
    if hit is None:
        hit = entries[key] = _CompositionValues()
    return hit


def _composition_key(asteroid_row: Row) -> Optional[Tuple[Any, ...]]:
    """Hashable identity of a row's composition, or None if it is not cacheable.

    ⚠️  NaN and None normalise to the SAME key, and that is required rather
    than convenient: all three consumers test `x is None or pd.isna(x)` and
    take the identical branch either way, so two rows that differ only in how
    their missing value is spelled must share an answer.  A bare `float('nan')`
    key would also never hit, two NaNs are not equal, so the cache would
    silently stop caching for exactly the rows that have gaps, which is the
    quiet-wrong-answer shape in its performance clothing (see `_UNSET` in
    `_isru_propellant_consts`).

    ⚠️  Anything that is not a real number or None returns None, which sends
    the caller down the uncached path rather than inventing a key for a value
    whose branch behaviour has not been checked.  `to_dict("records")` on the
    float64 composition columns yields plain floats, so the fast path is what
    the pipeline actually takes; this is the door for a hand-built row.
    """
    key: List[Any] = []
    for col in _COMPOSITION_KEY_COLS:
        v = asteroid_row.get(col)
        if v is None:
            key.append(None)
        elif isinstance(v, float):
            key.append(None if v != v else v)          # NaN -> None
        elif isinstance(v, int) and not isinstance(v, bool):
            key.append(float(v))
        else:
            return None
    return tuple(key)


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
    with no fraction or no price are skipped; you cannot select what is not
    there.

    ⚠️  `asteroid_bulk_value_usd_per_kg` deliberately does NOT use this: it
    admits a fraction of exactly 0.0 where this skips it.  Unifying the third
    copy would be numerically negligible and would still cost the bit-identity
    every release here is argued from; see the v1.14.2 phase-sort warning.
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

    v1.17.6: memoised per composition: see `_composition_key`.  The walk below
    is unchanged and is still the only statement of the blend; this caches its
    answer.

    v1.3.4, applies per-asteroid PGM enrichment to the metal fraction.
    Module 1 v1.0.4+ provides `comp_pgm_enrichment` (default 1.0× chondritic
    baseline; 2.0× for differentiated M-type cores; 0.2× for V-type basaltic
    crust; 0.5× for mantle fragments).  Multiplies only the rare-metal yields
    in nickel-iron, base metals (Fe, Ni, Co) and non-metal categories
    (silicates, carbon, water) are unaffected.

    v1.3.3, "Other" residual mass (Module 1 fractions sum to 0.76-0.96
    across types) was silently zero-valued; now treated as bulk silicate
    at $0.05/kg floor.
    """
    key = _composition_key(asteroid_row)
    if key is not None:
        entries = _composition_cache(mineral_df)
        hit = entries.get(key)
        if hit is not None and hit.bulk is not None:
            return hit.bulk

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

    # Residual "other" mass; value at silicate floor so it doesn't vanish.
    if 0.0 < frac_sum < 1.0:
        other_frac     = 1.0 - frac_sum
        silicate_price = _mineral_price(mineral_df, "silicates") or 0.05
        total += other_frac * float(silicate_price)

    if key is not None:
        _composition_entry(entries, key).bulk = total
    return total


def asteroid_phase_table(
    asteroid_row: Row, mineral_df: pd.DataFrame,
) -> List[Tuple[str, float, float]]:
    """[(phase, mass_fraction, usd_per_kg)] for one asteroid (v1.6.0).

    The same four taxonomy fractions `asteroid_bulk_value_usd_per_kg` blends,
    but kept SEPARATE so a mission can choose what to load rather than being
    handed the mean.  The residual (Module 1's fractions sum to 0.76-0.96) is
    included as bulk silicate, matching the bulk function's floor treatment.

    Phases with zero fraction are dropped; you cannot select what is not
    there.

    v1.17.6: memoised per composition; see `_composition_key`.

    ⚠️  A COPY of the cached list is returned, deliberately.  Nothing in this
    module mutates a phase table, but v1.17.4 records the other half of that
    argument: handing a million rows one shared mutable object is a trap
    whether or not today's code springs it.  A copy also keeps the aliasing
    exactly as it is now; `_PHASE_ORDER_CACHE` is keyed on list IDENTITY, so
    one list per asteroid is what its single slot was measured against.  The
    copy is ~0.15 us against the ~14 us walk it replaces.
    """
    key = _composition_key(asteroid_row)
    if key is not None:
        entries = _composition_cache(mineral_df)
        hit = entries.get(key)
        if hit is not None and hit.phases is not None:
            return list(hit.phases)

    phases: List[Tuple[str, float, float]] = []
    frac_sum = 0.0
    for mineral_name, frac, price in _phase_prices(asteroid_row, mineral_df):
        phases.append((mineral_name, frac, price))
        frac_sum += frac

    if 0.0 < frac_sum < 1.0:
        silicate_price = _mineral_price(mineral_df, "silicates") or 0.05
        phases.append(("other (bulk silicate)", 1.0 - frac_sum, float(silicate_price)))

    if key is not None:
        _composition_entry(entries, key).phases = list(phases)
    return phases


def saturation_price_multiplier(
    delivered_kg_per_yr: float,
    annual_market_kg:    float,
    elasticity:          float,
) -> float:
    """Price multiplier when a mission's output is material next to the market.

        P / P0 = (1 + Q_new / Q_market) ^ (−1/ε)

    Constant-elasticity demand.  Precious-metal demand is inelastic, 
    ε ≈ 0.5, so doubling world supply quarters the price, which is why
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
# time: 325,000 `sorted()` calls plus 1.4 million key-lambda calls per 150
# rows, all re-deriving the same order for the same rock.
#
# Same shape and the same justification as `_OPS_CACHE` below: keyed by object
# identity, with the list itself held in the slot so its id cannot be recycled
# onto a different object, and single-slot rather than a growing dict so a
# long-lived session cannot leak.  A caller that mutates a phase list IN PLACE
# rather than rebinding would read a stale order; nothing in this module does,
# and `asteroid_phase_table` returns a fresh list per asteroid.
#
# ⚠️  What this deliberately does NOT do is sort the phase table at source.  See
# the warning in `optimal_payload_mix`; the table's natural order is
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

    The mission is not sent for a named mineral; it is sent to bring back the
    best load it can assemble from what the target actually contains.  With a
    fixed mass budget and divisible, per-kilogram-priced phases, that is a
    FRACTIONAL KNAPSACK, and greedy selection by $/kg is provably optimal:
    fill the hold with the most valuable phase available, then the next, until
    the hold is full or the feed runs out.

    Separation recovers `recovery` of each phase present in the feed; whatever
    is not loaded is left at the asteroid.

    Returns value, blended $/kg, the chosen mix in kg, and the mass fraction
    the best phase makes up, which is the natural read on how well
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
    every verification this project relies on is a bit-identity check: the
    sha256 CSV diffs, `max |error| 0.000000000 kg`, "124 of 124 columns
    identical".  A sort at source reads like a free cleanup and silently costs
    you the ability to prove a release changed nothing.

    So the ordering is memoised per phase list instead, which leaves the table
    itself untouched.

    ── `want_phase` (v1.17.1) ───────────────────────────────────────────────
    Returns the kilograms of ONE named phase that the greedy walk loads, as a
    bare float, instead of the full result dict.  `_cargo_water_kg` is 97% of
    this function's callers and reads exactly one key, `mix_kg["water"]`, 
    so it was paying for the mix dict, the value accumulation and the
    dominant-phase `max()` over `mix.items()` on every call, then throwing all
    three away.

    It is a short circuit, NOT a second knapsack: the walk below is the only
    statement of the greedy algebra in this module, and `want_phase` only
    decides how much of each pass's result is kept and when to stop.  Writing
    it as a separate water-only function would have been the "two copies of
    this algebra drifting apart" hazard that the mass ledger warns about, for
    no extra speed; the loop is not what costs, the bookkeeping is.

    The answer is bit-identical by construction rather than by measurement:
    `remaining` is decremented in the same order by the same `min`, and the
    take for the requested phase is returned before anything downstream of it
    could perturb it.  Verified anyway; see the release notes.
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
            # The caller wants one number.  Stop as soon as it is known; 
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

    # Anything the feed could not fill is dead space, the hold flies partly
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

    Only phases with a non-zero fraction count; a body with no metal cannot
    be concentrated into metal.  Returns the bulk value as a floor so the
    bound can never sit below the unconcentrated material.

    v1.17.6: memoised per composition; see `_composition_key`.  This is the
    most expensive of the three at 27.7 us/row, because it walks the phases AND
    calls the bulk function, so a beneficiated run derived the bulk blend twice
    per asteroid.
    """
    key = _composition_key(asteroid_row)
    if key is not None:
        entries = _composition_cache(mineral_df)
        hit = entries.get(key)
        if hit is not None and hit.best is not None:
            return hit.best

    best = 0.0
    for _mineral_name, _frac, price in _phase_prices(asteroid_row, mineral_df):
        if price > best:
            best = price

    bulk = asteroid_bulk_value_usd_per_kg(asteroid_row, mineral_df)
    value = max(best, bulk)
    if key is not None:
        # Re-read the cache: the bulk call above may have created the entry.
        _composition_entry(_composition_cache(mineral_df), key).best = value
    return value


# ─────────────────────────────────────────────────────────────────────────────
# BENEFICIATION, TIME AND ENERGY INTENSITY  (v1.5.0)
# ─────────────────────────────────────────────────────────────────────────────
# Concentrating ore in deep space costs three things, and the model charges
# for all three:
#
#   TIME    - the rig has to dig the whole feed, not just the payload.  A 50:1
#             concentration means excavating 50 kg for every kilogram flown
#             home, and that time flows into mission duration, mission ops
#             and WACC compounding exactly like any other stay time.
#   ENERGY  - Module 3 rates excavation at 200 Wh per kg of regolith moved and
#             beneficiation at 500 Wh per kg of product.  Energy over time is
#             power, and power in deep space is a solar array.
#   MASS    - that array has to be launched.  Its mass enters the SAME rocket
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
# Module 3 has carried an "RTG (radioisotope power)" row since v1.2.0: $500k
# per Watt-electric, with a note reading "only used past ~3 AU when PV starves",
# and nothing in this module ever read it.  Every asteroid in the catalog
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
# radioisotope, and a meaningful slice of this catalog is outside it.
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
# anything a radioisotope source can deliver; pricing that as an RTG would
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

    v1.14.0, takes the solar figure ALREADY RESOLVED rather than deriving it
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
# `processing_power_w()` returns a CONTINUOUS average draw, energy divided by
# the time available, and the plant was sized straight off it.  That is only
# correct if the sun never sets.  It does: the rig stands on a rotating body,
# roughly half its sky is the ground, and asteroid rotation periods run hours.
#
# Module 3 has carried the 0.50 dark fraction in STORAGE_REFERENCE since v1.9.0
# with "⚠️  Not modelled" written on it, and the note was quoted as a known
# limitation for two releases while nothing consumed it, because Module 4
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
#   a slow rotator is genuinely a worse place to mine; a fact the model had no
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

    Bodies with no measured rotation, about two thirds of the catalog, take
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
    # lossy.  Exactly 1.0 at f = 0, the permanent-sunlight case a free-flying
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
# error left in the model, and it was load-bearing; the best Mars mission in
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
# its 11-year mission.  The 1/r² term is doing the work here, evaluated at
# the 1 AU array rating instead, the same sum gives 1.0 year and is nonsense.
#
# Run that check off `ep_power_required_w` below, the same relation solved for
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
    noticing that it owes nothing to efficiency; thrust is momentum flux, so
    T = m_prop·ve/t exactly.  Efficiency only decides how much electrical power
    you must supply to get it, which is why the two constraints are separate
    and why sizing on power alone missed one of them entirely.

    Until v1.12.0 nothing computed this. The EP stage was sized on power, and
    power buys thrust at a rate the rocket equation was happy to assume any
    device could deliver, so the search flew pulsed plasma thrusters and
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
# phase drifts slowly and windows are years apart, a body at a = 1.13 AU
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

    Energy is charged on the two Module 3 rates; excavation per kg of
    regolith MOVED, beneficiation per kg of product OUT, and divided by the
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
    needed in two places, inside the sizing loop, where it sets how much array
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
      reads rather than building the whole mix and discarding it; see
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
# Δv RESOLVER  (v1.4.0, per-asteroid, from orbital elements)
# ─────────────────────────────────────────────────────────────────────────────
# Until v1.4.0 every asteroid in the catalog received the SAME Δv, because
# v1.3.5 removed the per-target Asterank override without replacing it.  The
# consequence was not subtle: on a 150-asteroid run, max_payload_kg,
# total_cost_usd, m_launch_kg, mission_duration_yr, vehicle and propellant
# each had exactly ONE unique value across the whole catalog.  Only
# bulk_value_usd_per_kg varied.  The "profitability ranking" was a ranking of
# spectral types, and orbital accessibility, the single most important
# variable in asteroid mining economics, had no effect at all.  A main-belt
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
#      flyby; a mining mission has to stop).
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
# by rule, and the search is resolved against the destination being flown; see
# asteroid_transfer_options_km_s and asteroid_dv_options.

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
# Propulsive descent from low Mars orbit with NO atmospheric help; the
# fallback when aerocapture is switched off.  Mirrors the 4.1 km/s ascent.
DV_MARS_POWERED_DESCENT_KM_S = 4.100

# ── Mars orbit depot  (v1.18.0) ──────────────────────────────────────────────
# The 1-sol elliptical staging orbit, 250 x 33,793 km altitude, Module 3
# DELTA_V_REFERENCE "Mars arrival -> 1-sol orbit (MOI)".  Its period is 24.60 h
# against a sol's 24.62, which is where the name comes from, and NASA DRA 5.0
# stages there for the reason NRHO is the cislunar depot: capture only has to
# BIND the orbit, and the burn happens deep at periapsis where Oberth pays.
#
# Both velocities below are constants of the DEPOT, not of the arriving
# candidate, so they are resolved once here rather than per call.  That is
# defect class 3 in CLAUDE.md, "a quantity asked at a finer granularity than it
# has answers", and this function runs twice per catalog row.
R_MARS_1SOL_PERIAPSIS_KM = 3_396.2 +    250.0
R_MARS_1SOL_APOAPSIS_KM  = 3_396.2 + 33_793.0
_A_MARS_1SOL_KM = (R_MARS_1SOL_PERIAPSIS_KM + R_MARS_1SOL_APOAPSIS_KM) / 2.0
_V_ESC_MARS_1SOL_KM_S = math.sqrt(2.0 * MU_MARS_KM3_S2 / R_MARS_1SOL_PERIAPSIS_KM)
_V_ELL_MARS_1SOL_KM_S = math.sqrt(MU_MARS_KM3_S2 * (2.0 / R_MARS_1SOL_PERIAPSIS_KM
                                                    - 1.0 / _A_MARS_1SOL_KM))


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
      2. NRHO insertion at apogee, Module 3's 450 m/s.

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
    #   Earth surface, direct entry, no capture burn at all.  The arrival
    #     energy is dumped into a heat shield, whose mass the Module 4 cascade
    #     carries outbound and pushes back through the return burn.
    #   LEO, propulsive, the most expensive option in the model.  LEO is the
    #     deepest of the three destinations, so circularising there means
    #     killing the whole hyperbolic excess AND the escape velocity.
    #   LEO, aerobraked, trades that Δv for TPS mass and months of passes.
    #   Cislunar; cheapest, because capture only has to BIND the orbit, and
    #     the burn happens at low perigee where Oberth pays best.
    #   Lunar surface, cislunar capture, then NRHO→LLO→surface.  Airless, so
    #     that last 2.6 km/s is entirely propulsive.
    #   Mars, not an Earth return at all.  See the separate transfer below.
    dv_leo_capture = _leo_departure_dv_km_s(v_inf)
    dv_cislunar    = _cislunar_capture_dv_km_s(v_inf)

    legs = {
        "dv_out":                 dv_out,
        "v_inf":                  v_inf,
        "r_rendezvous_au":        r_target,
        "ret_earth_surface_aero": dv_match,
        # v1.10.0: capture into LEO and then LAND is not the same manoeuvre as
        # capture into LEO and stay there; the capsule still has to come down.
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
    # to a Mars base than to Earth; a fact the model can only show if this
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
    is cheaper is a property of the individual orbit; not something a rule can
    settle in advance.  Until v1.10.0 the estimator applied one:

        r_target = aphelion if aphelion >= 1 AU else perihelion

    which is right for most main-belt bodies and demonstrably wrong for others.
    The trade is between two terms that move in opposite directions.  Meeting a
    body at aphelion means a long, slow transfer whose arrival speed nearly
    matches the target's, cheap rendezvous, expensive departure.  Meeting it at
    perihelion means a short transfer, but both bodies are moving fast there and
    the match burn is large.  Which term dominates depends on a and e together,
    so it has to be evaluated, not assumed.

    Returns one full leg dict per feasible apsis, each tagged with
    `rendezvous_apsis` and `r_rendezvous_au`.  Callers pick, and because the
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
            break                      # circular orbit, the apsides coincide
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
        ret_earth_surface_aero  direct entry, no capture burn at all
        ret_earth_surface_prop  propulsive capture into LEO, then deorbit
        ret_leo_prop            propulsive capture into LEO
        ret_leo_aero            aerocapture + aerobraking, trim burn only
        ret_cislunar_prop       Oberth capture + NRHO insertion

    v1.5.0, was a 3-tuple (out, return_propulsive, return_aerocapture) when
    Earth's surface was the only destination the pipeline could model.

    v1.10.0; the rendezvous apsis is now searched (see
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
    unchanged by the apsis search; it only moves bodies the old rule got wrong.
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
    is genuinely available, and it is worth several km/s.
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

    # v1.18.0: capture into the 1-sol DEPOT orbit, which is a different and
    # much cheaper manoeuvre than the circularisation above; at a Hohmann
    # arrival (v_inf 2.65 km/s) it is 0.90 km/s against 2.10.  The saving is
    # the apoapsis that never has to be brought down.
    dv_capture_1sol = (math.sqrt(_V_ESC_MARS_1SOL_KM_S * _V_ESC_MARS_1SOL_KM_S
                                 + v_inf_mars * v_inf_mars)
                       - _V_ELL_MARS_1SOL_KM_S)

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
        # ── Mars ORBIT depot (v1.18.0) ───────────────────────────────────────
        # Nothing lands, so neither the retropropulsion nor the powered
        # descent applies and there is no entry-survival fraction on the
        # price side either.  What is left is the departure burn and the
        # capture.
        "ret_mars_orbit_prop":     dv_depart + dv_capture_1sol,
        # Aerocapture into the 1-sol ellipse, then a periapsis-raise burn to
        # get out of the atmosphere: Odyssey and MRO flew exactly this at
        # Mars.  Charged at the Earth aerobrake trim, which is CONSERVATIVE
        # here; the real raise from an aerocapture periapsis to 250 km, taken
        # at a 37,189 km apoapsis, is ~12 m/s against the 100 charged.  The
        # existing sourced constant is preferred over a new invented one for
        # a term this far inside the noise of the departure burn.
        "ret_mars_orbit_aero":     dv_depart + DV_AEROBRAKE_TRIM_KM_S,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DELIVERY ARCHITECTURE  (v1.5.0)
# ─────────────────────────────────────────────────────────────────────────────
# `delivery_destination` is not a price label; it selects a physically
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
    # v1.18.0.  No `needs_lander`, so this carries a $60k/kg berthing adapter
    # rather than the $200k/kg lander mars_surface pays for; a depot is
    # berthed with, not landed on.  That is the second of the two cost lines
    # that separate the Mars pair, the first being the entry-survival
    # fraction on the price side.
    "mars_orbit": {
        "returns_to_earth": False,
        "aero_leg":  "ret_mars_orbit_aero",
        "prop_leg":  "ret_mars_orbit_prop",
        "aero_allowed": True,     # aerocapture into the ellipse; Odyssey / MRO
        "label": "berthed at a 1-sol Mars-orbit depot",
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

    Unknown destinations fall back to earth_surface, the conservative
    choice, and the one whose cost lines are all present.

    v1.17.1: the resolved answer is memoised on the RAW argument, because
    `mission_cost_usd` calls this once per programme option: 458,337 times on
    a 150-row beneficiated sample with the search on, to normalise the same
    string and index the same dict.  Only the hit path is memoised: an unknown
    destination still falls through and still prints its warning every time,
    which is the loud behaviour that made it a warning.
    """
    try:
        hit = _ARCH_BY_RAW_KEY.get(destination)
    except TypeError:
        hit = None                    # unhashable caller; skip the memo
    if hit is not None:
        return hit

    key = str(destination or "").strip().lower()
    if key not in DELIVERY_ARCHITECTURES:
        print(f"     WARN   Unknown delivery_destination {destination!r} - "
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
    Whether it actually pays is decided per asteroid; see
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
    and the propellant; both of which the model has always picked per asteroid.

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
# ISRU RETURN PROPELLANT  (v1.10.0, made physical, and made per-asteroid)
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
#      mining and baking MORE rock; that is the whole cost of ISRU, and it was
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
# The surplus oxygen (8/7 produced against 6/7 burnt) is vented; a real depot
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
# Which of those wins is a real trade and it varies by body: a wet, easily
# reached target favours cheap propellant, a dry or distant one favours high
# Isp, so it belongs in the per-asteroid architecture search, not in a
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


_ISRU_CONSTS_KEY = "_isru_consts"


def _isru_propellant_consts(propellant: Row) -> Optional[Tuple[str, float]]:
    """`(feed material, kg of feed per kg of propellant)` for one propellant.

    None means this propellant can never be made from asteroid material at all,
    whatever the body is, a fact about the ROW, not about the target.

    v1.17.5.  This is the half of `isru_feed_kg_per_kg_propellant` that reads
    only the propellant, and it is the expensive half: on a full propellant
    table roughly four rows in five fall through to the legacy name test, which
    is a `str().strip().lower()` plus a substring scan, to conclude "no", and
    it concluded it once per (asteroid × propellant × Δv option) rather than
    once per run.  Measured at 48,600 of 62,018 calls taking that path on a
    150-row sample.

    Same route as `_prefilter_propellant_consts` and `_sizing_propellant_consts`:
    derived in `candidate_combos`, stashed on the row so it crosses the worker
    boundary, and re-derived on demand for a caller that hand-builds `combos`.
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
    if material not in ("regolith", "water"):
        return None
    return material, ratio


def isru_feed_kg_per_kg_propellant(
    asteroid_row: Row, propellant: Row, config: CalcConfig,
) -> Optional[float]:
    """kg of regolith to dig per kg of ISRU return propellant, or None.

    None means this mission cannot make its own propellant; either the
    propellant is not manufacturable from asteroid material, or this body has
    no water to make it from.  That is a per-(asteroid × propellant) fact, which
    is why it is answered here rather than by a config flag.

    v1.17.5 splits the per-propellant half into `_isru_propellant_consts`; what
    is left is the per-BODY half.  Same arithmetic, same order, same floats.
    """
    consts = propellant.get(_ISRU_CONSTS_KEY, _UNSET)
    if consts is _UNSET:
        # Absent means "not attached", which is NOT the same as "cannot make
        # propellant"; that is a legitimate None.  Hence the sentinel: reading
        # a plain None as an un-attached key would re-derive it on every call
        # for exactly the rows where the answer is no, i.e. most of them.
        consts = _isru_propellant_consts(propellant)
        propellant[_ISRU_CONSTS_KEY] = consts
    if consts is None:
        return None
    material, ratio = consts

    if material == "regolith":
        # Reaction mass is the body itself; no volatiles needed and no
        # separation loss, because nothing is being separated.
        return ratio

    ice_frac = asteroid_row.get("comp_ice_fraction")
    if ice_frac is None or pd.isna(ice_frac) or float(ice_frac) <= 0.0:
        return None

    recovery = max(1e-6, min(1.0, config.beneficiation_recovery))
    return ratio / (float(ice_frac) * recovery)


def mining_duration_yr(payload_kg: float, config: CalcConfig) -> float:
    """Time at the asteroid needed to extract `payload_kg` (years).

    v1.4.0.  Throughput scales with the rig mass actually delivered, so a
    bigger haul costs proportionally more mission-years, which then flows
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
# the full ~20 us prologue of `_evaluate_combo_at_ratio`: eclipse geometry,
# synodic period, ISRU chemistry, tankage, electric-stage sizing, to reach a
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
# power source and once per point of the concentration sweep, up to eighteen
# times for one dead candidate.
#
# ⚠️  This function and `max_return_payload_kg` are two statements of the same
# algebra, which is exactly the duplication CLAUDE.md warns about ("two copies
# of this algebra drifting apart is how a mass ends up in one cascade and not
# the other").  They are kept adjacent for that reason, and the defence is
# `prune_infeasible_combos = False` plus a column-by-column diff, if the two
# ever disagree, the pruned build drops rows the unpruned one keeps and the
# diff says so immediately.  Change one, re-run that diff.
# Distinguishes "this derived value is not attached yet" from a derived value
# that is legitimately None.  `.get(key)` cannot tell those apart, and reading
# one as the other is how a cache silently stops caching.
_UNSET = object()

_PREFILTER_CONSTS_KEY = "_prefilter_consts"

# Cache-miss sentinel for the search's `_combo_close_terms` memo (v1.14.2).
# `None` is a legitimate CACHED value there; it means "no vehicle in the table
# could close this candidate", so a plain `.get(key)` returning None cannot
# distinguish a miss from a stored refusal, and would recompute every refusal on
# every vehicle, i.e. exactly the work the memo exists to remove.
_UNCACHED = object()

# ─────────────────────────────────────────────────────────────────────────────
# PER-ROW CONSTANTS FOR THE SIZING PATH  (v1.14.2)
# ─────────────────────────────────────────────────────────────────────────────
# The same finding as `_PREFILTER_CONSTS_KEY` one level further in: six
# quantities that `_evaluate_combo_at_ratio` derived on entry are functions of
# (propellant row × config) alone, and one is a function of the vehicle row
# alone.  They were re-parsed out of the row for every SURVIVING candidate: 
# 218,000 times per 150 beneficiated asteroids, and each parse goes through
# `pd.isna`, which is ~700 ns because it is a pandas dispatch on a Python
# scalar.  That alone was ~980,000 `pd.isna` calls per 150 rows.
#
# Attached to the row dict rather than memoised on `id()`, for the same reason
# the pre-filter constants are: the dict is what crosses the multiprocessing
# boundary, so a worker gets the derived values with the row instead of
# rebuilding them, and there is no identity to be recycled.
#
# `tank_frac` is deliberately derived HERE and read by both consumers.  It was
# computed twice from the same two columns, once in
# `_prefilter_propellant_consts`, once in `_evaluate_combo_at_ratio`, which is
# the drift hazard this file keeps naming.  One derivation now, two readers.
_SIZING_CONSTS_KEY  = "_sizing_consts"
_VEHICLE_CONSTS_KEY = "_vehicle_consts"


def _tank_frac_per_kg(propellant: Row, config: CalcConfig) -> float:
    """Tank mass per kg of propellant, or 0.0 where the row cannot state one.

    Module 3 quotes tankage per LITRE because that is what it scales with, a
    tank encloses volume, not mass, so this is the one place the two columns
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
    shared constants exactly as it did before, the two-part test they replace
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


def _vehicle_consts(vehicle: Row) -> Tuple[float, float, bool]:
    """`(usable fairing m³, LEO capacity kg, capacity is usable)` for one vehicle.

    v1.17.6 adds the second and third.  `float(vehicle.get("payload_leo_kg", 0)
    or 0)` was written out in THREE places: the search's combo loop, the
    pre-filter probe, and `_evaluate_combo_at_ratio`, and the first of those
    ran it once per (vehicle × propellant) for every asteroid in the catalog:
    142,800 derivations per 400 rows, of seventeen numbers that are fixed for
    the whole run.  Same shape as the fairing volume beside it, and the same
    fix: derived once in `candidate_combos`, stashed on the row so it crosses
    the worker boundary.

    ⚠️  `math.isfinite(cap) and cap > 0` is folded in as the third field rather
    than left to each caller.  Two of the three tested it and one tested only
    `> 0`; both survive, because the two are the same test on a value that
    `float(... or 0)` has already made a real number, but stating it once is
    what stops them drifting apart.
    """
    fairing_m3 = vehicle.get("fairing_volume_m3")
    fairing = (float(fairing_m3)
               if fairing_m3 is not None and not pd.isna(fairing_m3) else 100.0)
    leo_cap = float(vehicle.get("payload_leo_kg", 0) or 0)
    return fairing, leo_cap, (math.isfinite(leo_cap) and leo_cap > 0)


def _prefilter_propellant_consts(
    propellant: Row,
    config:     CalcConfig,
) -> Optional[Tuple[float, float, float, float]]:
    """(isp, dv_penalty, tank_frac, boiloff_pct) for one propellant, or None.

    These depend only on the propellant row and the config, so they are derived
    once per run in `candidate_combos` rather than per (asteroid × candidate).
    None means the row cannot fly at all, no usable Isp, which is the same
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

    v1.14.2.  The launch capacity enters this test in exactly one place, the
    final comparison, and it enters MONOTONICALLY: a bigger rocket can never
    turn a candidate that closes into one that does not.  Everything else is a
    function of (propellant × Δv × ISRU).

    That matters because the combo grid is vehicle-major, so the question was
    asked once per vehicle: seventeen evaluations per propellant row per
    asteroid, computing the same two exponentials, the same boil-off inflation
    and the same tankage closure, and differing only in the last line.

    ⚠️  This returns the COEFFICIENTS of that last line rather than the launch
    capacity it implies, and the difference is not stylistic.  `bracket > 0`
    rearranges algebraically to `leo > (hw + k·s·d0·R_ret)·k_out·R_out`, but not
    in floating point, the rearrangement re-associates the arithmetic and moves
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
    # inflate R_ret directly; `r_ret_eff = 1 + (r_ret - 1) · factor` is the
    # substitution the loop makes.  ISRU is exempt: the propellant is made at
    # the asteroid on departure rather than held from launch.
    if config.model_propellant_boiloff and boiloff_pct > 0 and not isru:
        outbound_yr = max(0.5, 0.000_23 * dv_out)
        hold_yr     = outbound_yr + config.station_keeping_floor_yr + window_wait_yr
        r_ret = 1.0 + (r_ret - 1.0) * math.exp(
            boiloff_pct / 100.0 * hold_yr * 365.25)

    if not (math.isfinite(r_out) and math.isfinite(r_ret)):
        return None

    # Tankage closure; t·(R − 1) ≥ 1 means the tank outweighs the propellant's
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


def _ep_device_consts(
    is_electric:           bool,
    thruster_eff_row:      Optional[float],
    thruster_kg_per_n_row: Optional[float],
    ep_eff:                float,
    ep_kg_per_kw:          float,
    ppu_only_kg_per_kw:    float,
) -> Tuple[float, float, float]:
    """`(efficiency, thruster kg/N, PPU kg/kW)` for one propellant's device.

    v1.17.4.  Split out of `_evaluate_combo_at_ratio` so the pre-filter's
    second stage sizes the electric stage off the SAME resolution rather than a
    second copy of it, the hazard this file names under `tank_frac`, which
    spent three releases derived in two places beneath a note claiming it was
    derived in one.

    Both Module 3 figures fall back to the older shared constants when the row
    states no usable value, so a pre-Module-3-v1.10.0 catalog reproduces
    v1.11.0.  `schema_check()` names them, because the fallback is silent and
    flattering.
    """
    eff_used          = ep_eff
    thruster_kg_per_n = 0.0
    ppu_kg_per_kw     = ep_kg_per_kw
    if is_electric:
        if thruster_eff_row is not None:
            eff_used = thruster_eff_row
        if thruster_kg_per_n_row is not None:
            thruster_kg_per_n = thruster_kg_per_n_row
            ppu_kg_per_kw     = ppu_only_kg_per_kw   # thruster counted separately
    return eff_used, thruster_kg_per_n, ppu_kg_per_kw


def _ep_stage_kg(
    cascade:           Dict[str, float],
    isp_s:             float,
    eff:               float,
    ep_w_per_kg:       float,
    ppu_kg_per_kw:     float,
    thruster_kg_per_n: float,
    config:            CalcConfig,
) -> Tuple[float, float, float, float]:
    """Mass of the electric stage that flies `cascade`'s propellant load.

    Returns `(ep_system_kg, ep_power_w, ep_thrust_n, ep_thrust_yr)`.

    Three masses on three different quantities, and keeping them apart is the
    whole point of v1.12.0:
        array      scales with POWER, and 1/r² with distance
        PPU        scales with POWER, flat with distance
        thruster   scales with THRUST; this is the device constraint, and it
                   is what a per-kW figure cannot express.

    v1.17.4 made this a function rather than a block inside the sizing loop,
    because the pre-filter's second stage needs the same number off the same
    pass-1 cascade.  Same operations in the same order on the same values, so
    the extraction is bit-identical rather than merely equal.
    """
    m_prop_total = (float(cascade.get("m_outbound_prop", 0.0))
                    + float(cascade.get("m_return_prop", 0.0)))
    ep_power_w = ep_power_required_w(
        m_prop_total, isp_s, config.ep_target_thrust_yr, eff,
    )
    ep_thrust_n = ep_thrust_required_n(
        m_prop_total, isp_s, config.ep_target_thrust_yr,
    )
    ep_thrust_yr = config.ep_target_thrust_yr if m_prop_total > 0 else 0.0
    array_kg    = ep_power_w / ep_w_per_kg if ep_w_per_kg > 0 else 0.0
    ppu_kg      = ep_power_w / 1000.0 * ppu_kg_per_kw
    thruster_kg = ep_thrust_n * thruster_kg_per_n
    return array_kg + ppu_kg + thruster_kg, ep_power_w, ep_thrust_n, ep_thrust_yr


def _closes_carrying_its_own_stage(
    leo_capacity_kg: float,
    sizing_consts:   Tuple[float, Optional[float], Optional[float],
                           float, float, float],
    ops:             Tuple[float, ...],
    solar_w_per_kg:  float,
    structure_frac:  float,
    window_wait_yr:  float,
    dv_out_m_s:      float,
    dv_ret_m_s:      float,
    tps_frac:        float,
    isru:            bool,
    config:          CalcConfig,
) -> bool:
    """Pre-filter, second stage: can it still close once it carries its THRUSTER?

    ── What this is for ────────────────────────────────────────────────────

    v1.14.1's pre-filter refutes a candidate at PASS 1 of the sizing loop, 
    zero plant, zero electric stage, shortest hold, and its whole argument is
    that pass 1 is the most optimistic pass, so failing it is a decision no
    later pass can overturn.  That is true, and it leaves the obvious next
    question unasked.  Measured at cislunar, beneficiated, programme search on:

        219,054 calls to `_evaluate_combo_at_ratio`
        162,816 of them (74.3%) return None on `if not cascade["viable"]`
                after exactly TWO cascade solves, that is, on PASS 2

    Pass 2 is the first pass that flies the electric stage pass 1 has just
    sized, and on an electric mission that stage is tonnes.  So three quarters
    of the surviving search was paying a ~20 µs prologue and two closed-form
    solves, once per concentration ratio, and again per power source, to
    re-derive one refutation that depends on neither.

    ── Why refusing here is sound, and not a heuristic ─────────────────────

    Viability in `max_return_payload_kg` is `bracket > 0` (no-ISRU) or
    `base_launch <= leo` (ISRU), and BOTH are monotone decreasing in the two
    quantities that grow between pass 1 and pass 2:

      • `hardware_kg`.  Pass 2 flies `rig + plant + ep`, and the plant is >= 0
        by construction, so `rig + ep` is a lower bound on it, and the ep term
        is the SAME at every concentration ratio and every power source,
        because it is sized off pass 1's cascade, which is itself ratio- and
        power-blind.  (The plant is not; that is exactly why it is dropped.)

      • `r_ret`, through boil-off.  Pass 2 holds for `trial_dur + wait`, and
        `trial_dur` is `max(mining_duration_yr(...), station_keeping_floor_yr)`,
        so the hold cannot fall below the floor pass 1 used.  A longer hold
        inflates `r_ret`, which shrinks `bracket`.

    `structure_frac` grows too (containment), and it appears in `denom`, not in
    `bracket`, where a LARGER value can only help viability.  So this test
    runs at pass 1's `structure_frac`; pass 1 was viable, so its `denom` is
    already positive and is identical here, and the only way this returns False
    is the monotone condition.  False therefore means pass 2 is infeasible for
    every ratio and every power source; precisely what the code it replaces
    would have concluded, one solve at a time.

    ⚠️  One-sided, exactly like the first stage.  True still promises nothing:
    the throughput cap, the duration limit, the volume cap and the post-settle
    launch recheck all apply downstream.

    ⚠️  Non-electric candidates return True without touching the solver.  With
    no electric stage `ep` is 0, so this test IS the first stage, which the
    caller has already applied.
    """
    (dv_penalty, thruster_eff_row, thruster_kg_per_n_row,
     tank_frac, isp_s_val, boiloff_pct) = sizing_consts

    if not (config.model_low_thrust_time and dv_penalty > 1.0):
        return True                    # no stage to carry; stage 1 said it all

    (_dig_wh, _benef_wh, _base_w, ep_eff, ep_kg_per_kw,
     _rtg_w, ppu_only_kg_per_kw,
     _df, _swh, _seta, _bdh, _containment) = ops

    eff_used, thruster_kg_per_n, ppu_kg_per_kw = _ep_device_consts(
        True, thruster_eff_row, thruster_kg_per_n_row,
        ep_eff, ep_kg_per_kw, ppu_only_kg_per_kw,
    )

    # The same two lines the sizing function runs before its loop, on the same
    # values, so the solver below sees the identical floats.
    dv_out = dv_out_m_s * dv_penalty
    dv_ret = dv_ret_m_s * dv_penalty

    # And the same boil-off substitution pass 1 makes, at the same shortest
    # hold.  Written in Δv space rather than `_combo_close_terms`' R space
    # because the value has to reach `max_return_payload_kg` bit-for-bit as the
    # loop would have handed it over.
    dv_ret_eff = dv_ret
    if config.model_propellant_boiloff and boiloff_pct > 0 and not isru:
        outbound_yr = max(0.5, 0.000_23 * dv_out)
        stay_est_yr = config.station_keeping_floor_yr + window_wait_yr
        try:
            boiloff_factor = math.exp(
                boiloff_pct / 100.0 * (outbound_yr + stay_est_yr) * 365.25)
            r_ret_raw = math.exp(dv_ret / (isp_s_val * G0_M_S2))
        except OverflowError:
            return True                # let the solver make its own refusal
        r_ret_eff = 1.0 + (r_ret_raw - 1.0) * boiloff_factor
        if not (math.isfinite(r_ret_eff) and r_ret_eff > 0.0):
            return True
        dv_ret_eff = isp_s_val * G0_M_S2 * math.log(r_ret_eff)

    # ⚠️  v1.17.6: written out twice rather than built as a dict and splatted
    # into both calls.  Same arguments in the same order, `**` on a 9-key dict
    # measures 558 ns a call against 146 ns for the keywords, plus 306 ns to
    # build the dict, so the splat was ~1.1 us of a ~16 us function that runs
    # once per surviving (vehicle × propellant × Δv × ISRU).
    dry_return_kg = config.return_vehicle_dry_kg
    pass1 = max_return_payload_kg(
        leo_capacity_kg = leo_capacity_kg,
        isp_s           = isp_s_val,
        dv_out_m_s      = dv_out,
        dv_ret_m_s      = dv_ret_eff,
        hardware_kg     = config.mining_hardware_kg,
        dry_return_kg   = dry_return_kg,
        tps_frac        = tps_frac,
        isru_return     = isru,
        structure_frac  = structure_frac,
        tank_frac       = tank_frac,
    )
    if not pass1["viable"]:
        return False                   # stage 1 already knew this; agree with it

    ep_kg, _pw, _tn, _ty = _ep_stage_kg(
        pass1, isp_s_val, eff_used, solar_w_per_kg,
        ppu_kg_per_kw, thruster_kg_per_n, config,
    )
    if ep_kg <= 0.0:
        return True

    return bool(max_return_payload_kg(
        leo_capacity_kg = leo_capacity_kg,
        isp_s           = isp_s_val,
        dv_out_m_s      = dv_out,
        dv_ret_m_s      = dv_ret_eff,
        hardware_kg     = config.mining_hardware_kg + ep_kg,
        dry_return_kg   = dry_return_kg,
        tps_frac        = tps_frac,
        isru_return     = isru,
        structure_frac  = structure_frac,
        tank_frac       = tank_frac,
    )["viable"])


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
    not a guess; see the section header above for why pass 1 dominates.

    Deliberately one-sided.  True does not promise a viable mission: the
    throughput cap, the duration limit, the volume cap and the post-settle
    launch recheck all still apply downstream, and about a quarter of the
    survivors die on one of them.

    ⚠️  v1.17.4: that list named the wrong losses.  All four fire, but 74.3% of
    what survived this test died on the PASS-2 cascade, which is not among
    them; see `_closes_carrying_its_own_stage`, which is now the second stage
    and catches exactly that.  Cheap and sound beats tight and clever here.

    v1.14.2 split the work in two, `_combo_close_terms` for the part that does
    not depend on the vehicle, `_closes_with` for the part that does, because
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
def _infeasible(r_out: float = 0.0, r_ret: float = 0.0) -> Dict[str, float]:
    """The refusal cascade `max_return_payload_kg` returns on every dead end.

    ⚠️  v1.17.6: module level, not a nested def.  It was defined on every call
    of the solver, 500,860 of them on a 150-row beneficiated+searched sample, 
    at ~99 ns a def, which is ~5% of a 2.1 us function that is the single
    hottest thing in the mass cascade.  A fresh dict per call, exactly as
    before; only the function object stops being rebuilt.
    """
    return {"max_payload_kg": 0.0, "viable": False,
            "r_out": r_out, "r_ret": r_ret,
            "m_launch": 0, "m_outbound_prop": 0, "m_return_prop": 0,
            "m_at_asteroid": 0, "m_tps": 0, "m_dry_return": 0,
            "m_tank_return": 0, "m_tank_outbound": 0}


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

      • HEAT SHIELD, tps_frac × (m_payload + m_dry_return), hauled outbound
        from Earth AND pushed back through the return burn, even though it
        ablates on entry.  Let s = 1 + tps_frac.
      • RETURN-VEHICLE STRUCTURE, structure_frac × m_payload (v1.10.0), the
        primary structure and cargo restraint that a bigger haul needs.
        Let f = structure_frac, so the dry vehicle is d0 + f·m_payload.
      • PROPELLANT TANKAGE, tank_frac × m_propellant (v1.11.0), and this one
        is circular in a way the other two are not, because the tank is sized
        by the propellant and is itself mass the propellant has to push.
        Let t = tank_frac.

    On tankage.  Module 3 derives t per propellant from storage class and
    density (tank_kg_per_L / density_kg_per_L), and it is not a rounding term:
    2.5% for kerolox, 9.7% for hydrolox, 46% for cold gas, 53% for the bare
    hydrogen a nuclear-thermal stage burns.  Leaving it out was a straight
    subsidy to whichever propellant had the lowest density, which is the same
    propellant that has the highest Isp, so the error compounded rather than
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
    # ── Scalar arithmetic uses `math`, not numpy (v1.14.2) ───────────────────
    # Every argument here is a Python float, and numpy's ufunc dispatch costs
    # ~700 ns on a scalar against ~30-50 ns for the `math` equivalent.  This
    # function is called ~2.2 times per surviving candidate: 387,000 times per
    # 150 beneficiated asteroids, so seven ufunc dispatches were about half its
    # runtime and roughly a quarter of the whole search.
    #
    # `math.exp` and `np.exp` were checked bitwise over 400,000 samples across
    # the (Δv, Isp) range this model spans: zero mismatches.  They differ only
    # in how they OVERFLOW, numpy returns inf and warns, `math` raises, which
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
    # propellant for this burn outweighs the propellant's own contribution; 
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
        # launched from Earth; you can make propellant out there, not a
        # pressure vessel, so the launch constraint becomes:
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
            # Placeholder cascade; evaluate_combo will recompute once the
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
    # with it, hence k_out.
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
# propellants issued ~2.5M full-DataFrame boolean scans of a 17-row table: 
# 89% of Module 4's total runtime.  The table is loaded once per run and never
# mutated, so one dict build serves every lookup.
#
# Keyed by object identity, and the frame itself is held in the slot so its id
# can't be recycled onto a different object.  Single-slot (not a growing dict)
# so a long-lived session swapping ops tables can't leak.  A caller that
# mutates ops_df IN PLACE rather than rebinding would read a stale cache, 
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

    capped at `p_mature`, because growth is asymptotic; no amount of heritage
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

    Summed exactly rather than integrated; the integral approximation is
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
# searched axis, so they are called once per (candidate × programme), and at
# the top of the ladder N runs into the hundreds, which would put a
# several-hundred-iteration Python loop inside the innermost loop of the search.
#
# Memoised by VALUE, not by identity, because that is what the arguments are:
# `p_first`, `alpha`, `p_mature` and `rate` are constants for a whole run, so
# these caches hold at most one entry per rung of the ladder.  Nothing about the
# arithmetic changes, same function, same arguments, same result, which is the
# only kind of speed-up this module accepts on a release that also moves numbers.
# v1.17.5: memoised with `functools.lru_cache` rather than a hand-rolled dict.
# The hand-rolled version built its key in Python -- `(int(n), float(rate))` is
# two conversions and a tuple allocation before the lookup even starts -- and at
# 455,094 calls apiece that key construction WAS the cost, not the miss.
# `lru_cache` hashes the argument tuple in C: measured on this machine at
# 159 ns -> 92 ns for the two-argument case and 249 ns -> 131 ns for the
# four-argument one.
#
# ⚠️  Value-identical, not merely equivalent, and the `int()` / `float()` calls
# were not doing anything the cache does not.  Python hashes 1, 1.0 and True to
# the same slot and compares them equal, so a caller passing 1.0 where another
# passed 1 hits the SAME entry either way -- which is exactly what the explicit
# normalisation achieved.  Both callers pass an already-normalised int anyway
# (`_mission_cost_tail` builds `n_missions` as `max(1, int(...))`), so the
# conversions were defensive no-ops on every call this module actually makes.
#
# Unbounded, as the dicts were: the key space is one entry per rung of the
# ladder, and `maxsize=None` is also the fastest lru_cache path -- it skips the
# eviction bookkeeping entirely.
#
# ⚠️  v1.17.7: that argument is correct HERE and does not generalise, so read it
# as a claim about these two key spaces rather than as a house style.  Measured
# after an 800-row default cell, both hold **69 entries** against 2.4 M hits --
# `n_missions` is a rung of the ladder and the rates are config constants, so
# the ceiling has a name.  `_calendar_multipliers_cached` reasoned the same way,
# carried `cadence_yr` in its key, and grew to 36,071 entries on the same cell
# (~70 M and 11-18 GB projected on a full catalog) before being bounded.
#
# The rule the pair of them implies: **`maxsize=None` is safe exactly when you
# can NAME the ceiling.  If you cannot, set one.**  A memo whose hit rate is
# local and whose key space is not is a leak wearing an optimisation's clothes.
@functools.lru_cache(maxsize=None)
def _learning_curve_cached(n_units: int, rate: float) -> float:
    """`learning_curve_factor`, memoised on (units, rate).

    Unbounded because the key space is nameable: `n_units` is a rung of the
    programme ladder and `rate` is a config constant. See the block above.
    """
    return learning_curve_factor(n_units, rate)


@functools.lru_cache(maxsize=None)
def _mining_reliability_cached(
    n_missions: int, p_first: float, alpha: float, p_mature: float,
) -> float:
    """`mining_success_probability`, memoised on (missions, and three constants).

    Unbounded on the same argument as `_learning_curve_cached`: the last three
    arguments are config constants and the first is a ladder rung, so the two
    memos together held 69 entries after 2.4 M hits on an 800-row default cell.
    """
    return mining_success_probability(n_missions, p_first, alpha, p_mature)


def rig_trips_per_ship(
    ops_df: pd.DataFrame, config: CalcConfig, stay_yr: float,
) -> Optional[Tuple[int, int, Optional[int]]]:
    """How many consecutive campaigns one rig is good for, at this stay length.

    Returns `(trips, calendar_cap, trip_cap)`, or None when rig service life is
    not modelled at all, in which case one rig serves the entire programme,
    which is what this module did before v1.8.0.

    v1.15.0 adds the second of the two bounds, and the reason it is second
    rather than a refinement of the first is worth stating plainly:

      • `Mining rig service life` is **15 YEARS**.  It is a calendar figure and
        its own Module 3 notes describe a calendar mechanism: corrosion,
        thermal cycling, radiation dose.  Dividing it by the stay produced a
        mission count, and that count was treated as the rig's whole life.
      • Nothing bounded DUTY CYCLES.  At the ~1.25 yr stay the winning cislunar
        mission actually flies, the calendar bound made one rig good for 12
        consecutive mining campaigns, twelve full digs out of a number that
        only ever promised the machine would not have rusted meanwhile.

    A rig parked between campaigns ages slowly.  One cutting rock does not.  So
    the two bounds are independent and the binding one is the MIN: a long-stay
    mission is still calendar-limited, a short-stay one is now cycle-limited,
    which is the correct way round and was the whole gap.

    A missing Module 3 row reverts to calendar-only, silently, exactly as every
    other `_ops_value` default does, which is why the row is named in
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
    sets the cadence, so the bound is the max of the two, not the stay.

    ⚠️  That lands hardest on exactly the bodies this model likes.  A synodic
    period goes to infinity as a → 1 AU, so a NEA at 1.05 AU can only be
    revisited every ~14 years however fast its rig works, while a main-belt
    body at 3 AU comes round every ~1.6.  Δv accessibility and CADENCE are
    anticorrelated for the same reason Δv accessibility and trip time already
    are, see `synodic_period_yr`, and a programme is where that finally
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
    W = 1, which is every single-mission figure this project has ever
    published.

    ── What is actually wrong without this ─────────────────────────────────

    This module compounds costs FORWARD to the point of sale and compares them
    against undiscounted revenue; that is the convention `mission_cost_usd`
    already implements with `(1 + W)^T` on the up-front bucket.  Applied to one
    mission it is right.  Applied to a programme it quietly assumes every
    mission in the programme happens at once.

    It does not.  F ships fly W campaigns each, and the campaigns on one ship
    are strictly sequential: one rig, one hole, one dig at a time.  So the
    programme spans `T + (W − 1) × cadence` of calendar, and the articles that
    are bought ONCE at the start and amortised across all of it, the bus NRE,
    the autonomy NRE, and the rig itself, are being carried for far longer
    than one mission duration before the missions they paid for sell anything.

    Note which lines this is and is not.  A per-mission article (the launch,
    the capsule, the propellant, the plant, the electric stage) is bought for
    its own campaign, and that campaign's costs AND its revenue both sit at the
    same point in the programme, shift a whole cash flow and its cost/revenue
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
    collect it, the exact shape of subsidy this module keeps finding, arriving
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


# v1.17.7: BOUNDED, and it is the only cache in this module that has to be.
#
# Every other memo here keys on something with a small, fixed range: a frame's
# identity, a config value, a fleet size, a rung of the ladder, so it reaches a
# ceiling and sits there: `_learning_curve_cached` and `_mining_reliability_cached`
# hold 69 entries apiece after 2.4 M hits, and `_COMPOSITION_CACHE` holds ~25.
# This one keys on `cadence_yr`, which is `max(stay, synodic)` and therefore a
# fresh float per candidate mission, so it grew LINEARLY with the catalog:
#
#     cap  100 rows ->   3,983 entries       cap 800 rows -> 36,071 entries
#     cap  400 rows ->  17,729 entries       ~45 entries per catalog row
#
# which projects to ~70 M entries and 11-18 GB on a full-catalog default cell,
# against a documented run peak of ~6 GB.  Nothing had caught it because the
# cache landed in v1.17.4 and no full-catalog run has been made since v1.16.0.
#
# The retention was buying nothing.  Replaying the real 223,538-call sequence
# through bounded LRUs, all reuse is local to one candidate mission, v1.17.5's
# per-candidate `rig_cache` already absorbs the cross-option traffic one level
# up, and what reaches here is one ask per distinct (W, cadence) within a
# candidate:
#
#     unbounded     hit rate 83.9%     retained 36,071 entries
#     maxsize 1024  hit rate 83.9%     retained  1,024 entries
#     maxsize   64  hit rate 83.8%     retained     64 entries
#
# 36,071 entries buy 0.1 pp over 64.  1024 is headroom, not a measured need.
#
# ⚠️  This cannot change a single output value, and that is worth stating
# because almost nothing else in this file is safe to say: it is a memo of a
# deterministic pure function, so evicting an entry only forces recomputation
# of the identical float.  Bit-identity holds by CONSTRUCTION rather than by
# rounding, unlike the arithmetic reorderings this project keeps declining.
#
# `functools.lru_cache` also happens to be faster than the hand-rolled dict it
# replaces, because it hashes the argument tuple in C instead of building a key
# tuple in Python first; the same finding v1.17.5 made for the two memos
# above.  Measured on this machine, per hit:
#
#     hand-rolled dict  180.1 ns      lru_cache(1024)   91.0 ns
#     lru_cache(None)    93.4 ns      lru_cache(256)    94.0 ns
#
# so bounding it is not a trade against speed.  Note this retires the "unbounded,
# as the dicts were" reasoning above for THIS function only: that argument rests
# on the key space being small, and here it is not.
@functools.lru_cache(maxsize=1024)
def _calendar_multipliers_cached(
    missions_per_ship: int, cadence_yr: float, wacc: float,
) -> Tuple[float, float]:
    """`programme_calendar_multipliers`, memoised by value.

    v1.17.4, and the same argument as `_learning_curve_cached` and
    `_mining_reliability_cached` directly above, except that this one is not
    an O(N) sum, so it was easy to miss.  It is two `**` calls, which are the
    slowest float operations in the tail.

    The ladder is the F ladder CROSSED WITH W, and this function reads W and
    nothing else the ladder varies: `cadence` and `wacc` are fixed for the
    whole candidate.  So ~40 programme options ask it for at most `trips`
    distinct answers, and `trips` is `min(life / stay, max_trips)` with
    `max_trips` = 5.  Measured at 369,166 calls for 10,741 candidates: about
    eight askings per answer.

    Keyed globally rather than per candidate because the arguments ARE the
    inputs; the same (W, cadence, wacc) is the same pair of multipliers for
    any body, and `w == 1` returns before the cache is touched, so the
    single-mission path is untouched.  Bounded because `cadence_yr` is not:
    see the note above.
    """
    return programme_calendar_multipliers(missions_per_ship, cadence_yr, wacc)


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

    Two geometric midpoints; the interval between the bracketing rungs is
    exactly what the coarse sweep left unexamined, plus both immediate integer
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

      • **F is a ladder**: geometric, refined, capped by `max_fleet_ships`,
        exactly as v1.15.0 built it.  It runs to 64 and cannot be enumerated.
      • **W is ENUMERATED EXHAUSTIVELY**, 1 … trips.  No ladder, no refinement
        pass, no unimodality assumption, because `trips` is
        `min(life / stay, max_trips)` and `max_trips` is 5; the whole
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

    N, `nre_amortization_missions`, is the programme size, and it enters this
    model in exactly six places: the NRE division, the autonomy-NRE division,
    the rig amortisation, the learning curve, reliability growth, and (since
    v1.14.0) the concurrent output that market saturation prices against.  Group
    them by how they behave and the search collapses:

      • ONE RIG SERVES `trips` MISSIONS BACK TO BACK, so a programme of N needs
        `ceil(N / trips)` rigs and that many missions are in flight at once.
        The saturation multiplier is a function of that COUNT and of nothing
        else about N.
      • WITHIN ONE FLEET BAND, every N with the same `ceil(N / trips)`, the
        multiplier is therefore constant, while NRE/N falls, autonomy NRE/N
        falls, the learning curve falls, the rig's per-mission share falls (or
        holds), and p_mining rises.  Every single lever improves and none
        pushes back.

    So the best N in a band is always the TOP of the band, N = F × trips, and no
    other N can ever be optimal.  The search is over F, exactly `max_fleet_ships`
    integers of which only ~12 are ever evaluated, rather than over N, which
    would be `max_fleet_ships × trips` of them, and which is what "just run it at
    1, 10 and 100" was sampling blindly.

    That is not an approximation and it is not a heuristic.  It is also the
    answer to the question the user asked in the first place: the number of ships
    is the decision variable, and programme size is its consequence.

    Two further consequences worth keeping:

      • N = 1 IS NEVER SKIPPED IN EFFECT.  It sits in band 1, whose top is
        N = trips, and by the argument above N = trips dominates it.  So a
        searched run can never report a worse objective than the N = 1 run every
        committed figure in this project was measured at, which is the
        never-worse invariant this module requires of any new axis, and here it
        holds by construction rather than by measurement.
      • N = F × trips IS ALSO THE ONLY N THE COST MODEL IS EXACTLY RIGHT AT.
        `mining_rig_cost` charges every mission the same share of a fully-used
        rig, so a programme of 13 with trips = 12 books its second rig; used
        once, as though it were worn out.  At a whole multiple there is no
        part-worn rig to mis-book.

    ⚠️  THE BAND ARGUMENT IS PER CANDIDATE, AND `trips` IS NOT A PROPERTY OF THE
    BODY.  It is `min(life / stay, max_trips)`, and the stay depends on how hard
    that candidate concentrates, so two concentration ratios on the same rock
    are two different mission profiles with two different trip lives and two
    different ladders.  That is handled correctly, because this function is
    called per candidate with that candidate's own stay.

    What it exposes is a pre-existing heuristic one level up.  `evaluate_combo`
    sweeps the concentration ratio coarsely and then refines around the WINNER,
    and the winner now depends on N, so a ratio that would have won at some
    other programme size can fall outside the refined region and never be
    priced.  Measured on 2014 JT2 beneficiated: brute-forcing every N from 1 to
    40 finds N = 4 at 30.2597x on a ratio of 3.216 (stay 1.74 yr, trips 4),
    while the ladder reports N = 3 at 30.5535x on a ratio of 5.518 (trips 3): 
    0.97% worse, because 3.216 was never on the grid it searched.  Raising
    `concentration_search_steps` from 7 to 25 makes the ladder return 30.2597x
    on ratio 3.216 exactly, which is what identifies the grid rather than this
    argument as the cause.

    It is documented rather than patched.  Refining around the best two ratios
    would be a heuristic stacked on a heuristic, for a sub-1% effect that the
    existing dial already closes, and `concentration_search_steps` is the dial
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
        # back.  The objective is then monotone improving in N without bound; 
        # "fly more missions" is free money again, which is precisely the
        # failure v1.14.0 closed.  Searching an unbounded monotone axis reports
        # the ladder's top rung as a result, so it is refused rather than run.
        # `build_profitability_catalog` says so out loud at startup.
        #
        # ⚠️  The calendar charge does NOT rescue this.  With one rig serving
        # everything, W = N and the charge grows without bound too, but so
        # does the amortisation it is charged against, and neither is bounded
        # by anything physical, so the optimum would be an artefact of whichever
        # diverges faster.  Still refused.  (W = N here is not read anyway:
        # `mission_cost_usd` only consults it inside the rig block, which this
        # branch means is switched off.)
        return [(n_cfg, 1, n_cfg)]

    if not config.optimise_programme_scale:
        f = max(1, math.ceil(n_cfg / trips))
        # v1.16.0: campaigns per ship is derived from the fleet.  Off, it is
        # the v1.15.0 expression `min(N, trips)`, which over-counts a
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
    # enumerated rather than laddered; it is at most `max_trips` integers.
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
    owns building the mapping; this only skips the call on a hit.
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
    they were being looked up inside `_evaluate_combo_at_ratio`, which runs
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
    `_ops_value`, and `rig_trips_per_ship` two more; none of which depends on
    the asteroid, the vehicle, the propellant, the architecture or the
    programme option.  They are pure functions of `ops_df`, which is loaded
    once per run and never mutated.

    That was survivable while the cost model ran once per surviving candidate.
    It stopped being survivable in v1.17.0, which turned `optimise_programme_scale`
    ON BY DEFAULT: the programme ladder prices a median of 40 options per
    mission, so every one of those lookups is now multiplied by 40.  Measured
    on a 150-row beneficiated cislunar sample with the search on,
    `_ops_value` was running **8.06 million times**: 11.7% of the profile, to
    re-read twenty-two numbers that never move.

    Ordered, not named, for the same reason `_ops_sizing_constants` is: the
    callers unpack the whole tuple in one statement, which is a single opcode,
    and every read after that is a local.  Keep this list and the unpacking in
    `mission_cost_usd` in the same order; they are checked against each other
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


_OPS_RELIABILITY_CACHE: Tuple[Optional[pd.DataFrame],
                              Optional[Tuple[float, ...]]] = (None, None)


def _ops_reliability_constants(ops_df: pd.DataFrame) -> Tuple[float, ...]:
    """The five Module 3 rows the RELIABILITY block needs, resolved once.

    v1.17.6, and the same finding as `_ops_cost_constants` (v1.17.1) and
    `_ops_sizing_constants` (v1.10.1) in the one block between them that still
    read `_ops_value` per candidate.  `_evaluate_combo_at_ratio` pulled all
    five out of the table for every surviving (vehicle × propellant × Δv ×
    ISRU × ratio × power source): 10,741 times on a 150-row sample, for five
    numbers that are fixed for the run.

    Eagerly resolved, like the other two: `_ops_value` is total, so a row that
    is absent falls back to the same default the per-call read would have used.
    """
    global _OPS_RELIABILITY_CACHE
    cached_df, vals = _OPS_RELIABILITY_CACHE
    if cached_df is ops_df:
        return vals

    vals = (
        _ops_value(ops_df, "Launch vehicle reliability", default=0.97),
        _ops_value(ops_df, "Spacecraft mean time between failures", default=30.0),
        _ops_value(ops_df, "Mining system first-of-kind success probability",
                   default=0.85),
        _ops_value(ops_df, "Mining reliability growth exponent", default=0.30),
        _ops_value(ops_df, "Mining system mature success probability", default=0.95),
    )
    _OPS_RELIABILITY_CACHE = (ops_df, vals)
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
    `missions_per_ship` and NOTHING else; every other argument is held fixed
    across a median of 40 options, yet the whole cost cascade was re-derived
    for each of them.  That is ~10 `max()` calls, ~6 dict lookups, ~15 `float()`
    conversions, a `delivery_architecture` call and a 22-tuple unpack, run forty
    times to change three numbers.  This is the same finding as v1.17.1's, one
    level up: that release stopped re-READING the constants, this one stops
    re-DERIVING everything computed from them.

    ── WHY THIS IS BIT-IDENTICAL, WHICH v1.17.1 SAID IT COULD NOT BE ───────────

    That release deferred this split because "it re-associates the final sums,
    and this project's releases are argued from bit-identity".  The premise is
    right and the conclusion does not follow, because every N-dependent line in
    the cascade factors as `<N-independent base> * lc`, and Python evaluates
    `a * b * lc` left to right, as `(a * b) * lc`.  So hoisting `a * b` into a
    name and multiplying by `lc` in the tail is the SAME two operations in the
    SAME order, not an algebraically-equal rearrangement.  Same for
    `nre_total * (1.0 - overlap) / n_missions`, which is `(a * b) / n`.

    🚨  What must NEVER be hoisted is a PARTIAL SUM whose terms interleave with
    N-dependent ones.  `hardware_cost`, `spacecraft_book_value` and
    `upfront_lines` all mix the two, and pre-adding their N-independent members
    would re-associate the addition, numerically negligible and fatal, exactly
    as the v1.14.2 phase-table sort was.  Those three sums are therefore
    restated VERBATIM in `_mission_cost_tail`, term for term and in order, and
    the four or five adds that costs are not what this function was slow for.

    ⚠️  The returned tuple's field order is load-bearing and is unpacked in one
    statement at the top of `_mission_cost_tail`; keep the two together, the
    same discipline `_ops_cost_constants` and its consumer already follow.
    """
    # v1.17.1: the twenty-two Module 3 constants this cascade reads, resolved
    # once per run rather than once per call.  Order matches
    # `_ops_cost_constants`; keep the two together.
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
    # with departure energy under any propulsion system, unless the escape
    # figure is for a vehicle that was topped up after reaching orbit.
    #
    # Module 3's row has said so in prose since v1.4.0 and named the fix:
    # "Module 4 should add ~$90M × N_tankers to the ESCAPE-DIRECT SCENARIO for
    # an apples-to-apples comparison."  v1.11.0 implemented the arithmetic and
    # missed the scenario; it levied the charge on every mission.
    #
    # This module has no escape-direct scenario.  It reads `payload_leo_kg` and
    # `usd_per_kg_to_leo` and nothing else (grep the file): the launch vehicle
    # delivers the stack to LEO, and the stack departs on its own outbound
    # stage, which is sized by the rocket equation a few dozen lines up.
    # Starship's 100 t to LEO needs no tankers; refuelling is what buys the
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
        # ISRU prop is "ongoing", manufactured at the asteroid over the
        # mining duration, not pre-paid upfront on Earth.
        return_prop_cost = float(mass_cascade["m_return_prop"]) * config.isru_processing_usd_per_kg
        return_prop_is_ongoing = True
    else:
        return_prop_cost = float(mass_cascade["m_return_prop"]) * cost_per_kg_prop
        return_prop_is_ongoing = False

    # Recurring hardware, split into the mining rig (one-way to asteroid,
    # AMORTISABLE across multi-mission programmes since the rig stays put)
    # and the return capsule (fresh per mission, fly-and-die).
    mining_rig_cost_total   = config.mining_hardware_kg * hw_per_kg

    # v1.17.1: `rig_trips` is `(ops_df, config, stay_yr)` and nothing else, and
    # all three are held FIXED across a programme ladder, so the caller that
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
    # v1.6.0: a surface base needs a LANDER, throttleable descent engines,
    # legs, terminal guidance, which is more machine than either a passive
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
    # out of the ledger; the same asymmetry the EP stage had.
    dry_return_flown = float(mass_cascade.get(
        "m_dry_return", config.return_vehicle_dry_kg))
    # ⚠️  v1.17.2: each `*_base` below is the original expression with its
    # trailing `* lc` removed, and nothing else.  The learning curve is applied
    # in the tail because it is the one factor that moves with N.
    capsule_base            = dry_return_flown * capsule_per_kg
    # v1.5.0: the beneficiation plant's solar array, priced per installed Watt
    # off Module 3's power-system row.  Zero unless beneficiation is on; the
    # baseline rig's own power is already implicit in its $/kg recurring rate.
    # v1.11.0: past 3.46 AU the sizing loop may have chosen a radioisotope
    # source because it is LIGHTER there.  It is also 625× more expensive per
    # watt, and charging it at the solar rate would be exactly the asymmetry
    # this codebase keeps finding: a mass in the rocket equation with the
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
    # module has flown it through the rocket equation ever since, outbound
    # tank staged at the asteroid, return tank carried home, but nothing ever
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

    # Heat shield; mass now comes from the actual cascade, not re-derived.
    # v1.14.0: the learning curve applies here too.  An ablative heat shield is
    # consumed on entry and rebuilt for every mission; it is the most literally
    # per-mission article on the vehicle, so Wright's law applies to it exactly
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

    # Launch insurance, percent of (launch + spacecraft book value).
    # Gross value of future revenue is NOT insured, underwriters cover the
    # replacement cost of the launched asset only.
    #
    # v1.12.0: that asset is everything on the rocket, and the book value had
    # drifted behind the mass cascade.  It listed the mining rig and the
    # capsule, which was the whole spacecraft in v1.4.0, but v1.5.0 added a
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
    # missed; it is the one item on the launch stack whose cost line sits
    # outside `hardware_cost`.  On an Earth-return mission it is a 15%-of-payload
    # article at $50,000/kg, so it is not a rounding term where it exists at all.
    launch_ins_pct        = launch_ins_raw / 100.0

    # Spacecraft bus NRE amortised across N missions, less the share already
    # embedded in the per-kg recurring rate (v1.4.0; see
    # nre_recurring_overlap_fraction).  NICM / SSCM per-kg brackets are
    # regressions on total program cost, so charging full OSIRIS-REx NRE on
    # top of a $300k/kg recurring rate books part of the development twice.
    nre_overlap = min(max(config.nre_recurring_overlap_fraction, 0.0), 1.0)
    nre_base    = nre_total * (1.0 - nre_overlap)

    # ── Time-bucket every line item ──────────────────────────────────────────
    # UPFRONT = paid at year 0 (or earlier, NRE accumulates pre-launch but
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

    # WACC compounding, apply per bucket so end-of-mission costs aren't
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
    rig_cache:           Optional[Dict[Tuple[int, bool],
                                       Tuple[float, ...]]] = None,
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
    # remains when the programme ends is credited at the salvage fraction, 
    # but only if there IS a programme; a rig at an asteroid nobody revisits
    # is stranded, not an asset.
    rig_terminal_value = 0.0
    missions_sharing_rig = n_missions
    _rig_hit = _rig_key = None
    if rig_trips is not None:
        trips, _calendar_cap, trip_cap = rig_trips
        # v1.16.0: how many campaigns one rig actually flies is a property of
        # the FLEET, not of N alone, F ships split N between them.  The caller
        # supplies it because the caller is what searched (F, W).  None keeps
        # the v1.15.0 expression, which is what `model_programme_calendar` off
        # and every pre-v1.16.0 caller get.
        missions_sharing_rig = (min(n_missions, trips) if missions_per_ship is None
                                else max(1, min(int(missions_per_ship), trips)))
        # ── v1.17.5: everything from here to the calendar multipliers is a
        # function of (missions_sharing_rig, n_missions > 1) and the PROLOGUE,
        # and the ladder is the F ladder crossed with W, so ~42 options ask
        # for at most `trips` x 2 distinct answers, and `trips` is
        # `min(life / stay, max_trips)` with `max_trips` = 5.  Same shape as
        # `sat_by_fleet` (v1.17.2) and `_calendar_multipliers_cached` (v1.17.4),
        # one level out: this absorbs that call rather than repeating it.
        #
        # Keyed on `missions_sharing_rig` rather than on `missions_per_ship`
        # so the key is correct on BOTH paths, a caller that passes no
        # `missions_per_ship` derives it from N, and the min/max above is cheap
        # enough to run before the lookup.
        #
        # ⚠️  Bit-identical by construction, not by rounding: the same key
        # re-runs the same arithmetic on the same prologue, so the cached
        # floats ARE the floats the block would have produced.  Opt-in; a
        # `rig_cache` of None is exactly the v1.17.4 code path, which is what
        # `mission_cost_usd` and every other caller still get.
        _rig_key = (missions_sharing_rig, n_missions > 1)
        if rig_cache is not None:
            _rig_hit = rig_cache.get(_rig_key)
        if _rig_hit is None and n_missions > 1:
            # Life USED, and there are now two ways to use it up.  Crediting
            # salvage on remaining calendar years while the rig is mechanically
            # finished would pay a refund on a worn-out machine, the same shape
            # of subsidy this module keeps finding, so the binding utilisation
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
    #
    # ── v1.17.5: the calendar multipliers are resolved HERE, with the rig
    # shares, rather than 60 lines below where they used to sit.  They read
    # `missions_sharing_rig`, `cadence` and `wacc` and nothing computed in
    # between, so this is a move, not a reordering of any arithmetic, and it
    # is what lets one cache entry carry the whole W-dependent block instead of
    # two.  The DELTA that applies them to `total_cost` has not moved; see it
    # below, still written on top of the untouched v1.15.0 sum.
    if _rig_hit is not None:
        (mining_rig_cost, rig_gross_share, rig_credit_share,
         rig_terminal_value, cal_cost, cal_credit) = _rig_hit
    else:
        # v1.17.2: one `max(1, ·)` rather than three.  Deliberately NOT dropped
        # altogether: `missions_sharing_rig` is ≥ 1 in every branch above given
        # `trips` ≥ 1, but that is a property of `rig_trips_per_ship`'s current
        # return rather than of anything asserted here, and this file's own
        # history is full of guards that were correct until a table changed
        # underneath them.
        rig_share_divisor = max(1, missions_sharing_rig)
        mining_rig_cost = ((mining_rig_cost_total - rig_terminal_value)
                           / rig_share_divisor)
        # The same two halves again, kept apart rather than netted, because the
        # programme calendar term compounds them in OPPOSITE directions: the rig
        # is bought at t = 0 and the salvage is collected at the end.  Netting
        # first and applying one multiplier would credit the refund for arriving
        # late.  Read only by the calendar delta below, which is skipped outright
        # when the multipliers are 1.0, so `mining_rig_cost` above stays the
        # arithmetic v1.15.0 performed, in the order it performed it.
        rig_gross_share  = mining_rig_cost_total / rig_share_divisor
        rig_credit_share = rig_terminal_value    / rig_share_divisor
        cal_cost = cal_credit = 1.0
        if calendar_on and missions_sharing_rig > 1:
            cal_cost, cal_credit = _calendar_multipliers_cached(
                missions_sharing_rig, cadence, wacc)
        if rig_cache is not None and _rig_key is not None:
            rig_cache[_rig_key] = (mining_rig_cost, rig_gross_share,
                                   rig_credit_share, rig_terminal_value,
                                   cal_cost, cal_credit)

    # v1.7.0: LEARNING CURVE.  The per-mission articles, the capsule or
    # lander, and the power system, are built N times over a programme, and
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

    # 🚨  Term by term, in order, same reason as `hardware_cost`.
    spacecraft_book_value = (mining_rig_cost_total + capsule_cost
                             + power_system_cost + ep_system_cost + tank_cost
                             + heat_shield_cost)
    launch_insurance_cost = launch_ins_pct * (launch_cost + spacecraft_book_value)

    nre_cost    = nre_base / n_missions

    # Autonomous mining control & AI NRE, uncrewed-mission specific (Module 3
    # v1.2.4+ replaced the legacy 'Crew' line item with this).  Amortised the
    # same way as the bus NRE, once developed, the autonomy stack ships on
    # every subsequent identical mission.
    autonomy_nre_cost  = autonomy_nre_total / n_missions

    # 🚨  Term by term, in order, same reason as `hardware_cost`.  Four of
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
    # t = 0 and amortised across all of them, bus NRE, autonomy NRE, the rig, 
    # are carried for that whole span.  See `programme_calendar_multipliers`
    # for why only those three, and why the salvage credit runs the other way.
    #
    # Written as a DELTA on top of the untouched v1.15.0 expression rather than
    # as a rebuilt sum.  Both multipliers are exactly 1.0 at W = 1, so the
    # branch is skipped, no term is re-associated, and the released arithmetic
    # is bit-identical, which is the only form this project's verification can
    # actually check, and the reason the phase-table sort was rejected in
    # v1.14.2.
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
    # `subtotal`, `contingency_cost`) or the dict itself; nothing below
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

    Uncrewed autonomous mining mission, no crew cost line.

    v1.17.2: the body is split into `_mission_cost_prologue` (everything that
    does not move with programme size) and `_mission_cost_tail` (everything
    that does), because the programme ladder varies only `n_missions` and
    `missions_per_ship` and was re-deriving the other ~90% of the cascade for
    each of a median 40 options.  This function is their composition and is
    unchanged in signature, in behaviour and, the point of the exercise, in
    the exact floats it returns.  It remains the entry point for every caller
    that prices ONE programme; `_price_programme` builds the prologue itself.

    v1.3.2 accuracy fixes:
      • Heat-shield mass is now sourced from the rocket-eq cascade
        (mass_cascade["m_tps"]) instead of re-derived from payload only; 
        the m_tps in the cascade is what actually got launched.
      • Launch insurance now percent of (launch + hardware) = SPACECRAFT
        book value rather than (launch + gross_value of future revenue),
        matching how real launch insurance is underwritten.
      • Capsule (`return_vehicle_dry_kg`) now carries its own recurring
        manufacturing cost; previously only mining_hardware was costed.
      • WACC compounding is time-bucketed: upfront costs compound at
        (1+W)^T, ongoing (ops + ISRU prop) at (1+W)^(T/2), end-of-mission
        (recovery) at 1.0.  Previous all-to-end overstated time-cost ~5%.

    Takes no payload or gross-value argument.  It used to take both, and
    v1.3.2 left them stranded: the insurance rebasing above removed the only
    read of gross_value_usd, and sample recovery became a flat Module 3 ops
    lookup rather than a per-kg charge, removing the only read of
    payload_returned_kg.  Every cost here now derives from the mass cascade,
    the Module 3 reference tables, and config; nothing scales with the
    revenue the mission is projected to earn, which is the point.

    Line items (every value sourced from Module 3's reference tables):
        UPFRONT     - launch, outbound prop, return prop (if not ISRU),
                      mining-rig hardware (amortised), capsule (per mission),
                      heat shield, NRE (bus + autonomy, amortised),
                      licensing, liability, launch insurance
        ONGOING     - mission ops × duration_yr, ISRU return prop (if ISRU)
        END-OF-MISSION, sample recovery
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
    nothing else, not the vehicle, not the propellant, not the return mode, not
    the power source, not the concentration ratio, and every one of them was
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
    candidate in turn, so the caller bails on the whole asteroid instead of
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
    for THIS candidate mission; v1.10.0 made both per-asteroid searches rather
    than global config settings, so they arrive as arguments.  Passing
    aero=None falls back to what the config allows for the destination.

    Returns None if the mission is infeasible (zero return payload, no
    propellant to make, over the duration limit), or a full result dict
    including profit, ROI, $/kg returned, and the mass + cost cascades.
    """
    vconsts = vehicle.get(_VEHICLE_CONSTS_KEY)        # v1.17.6, see _vehicle_consts
    if vconsts is None:
        vconsts = vehicle[_VEHICLE_CONSTS_KEY] = _vehicle_consts(vehicle)
    leo_cap = vconsts[1]
    if leo_cap <= 0:
        return None
    if best_phase_value_per_kg is None:
        best_phase_value_per_kg = bulk_value_per_kg
    if phases is None:
        phases = []

    # ── Low-thrust Δv penalty (v1.4.0) ───────────────────────────────────────
    # Module 3 tags each propellant with the factor by which a real trajectory
    # exceeds the impulsive Δv budget.  Electric propulsion cannot fly the
    # impulsive burns the reference table assumes; it spirals, and spiralling
    # out of LEO costs roughly twice what an impulsive escape does.  Without
    # this, a 3,000 s Isp thruster wins the mass cascade on a Δv budget it
    # could never actually achieve.
    # ── Per-row constants (v1.14.2) ──────────────────────────────────────────
    # `candidate_combos` attaches these, but a caller that hand-builds `combos`
    # will not have.  Derived on demand in that case rather than defaulted; 
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
    # which meant re-deriving them for every candidate mission; see
    # `AsteroidContext` for the call counts.  `ctx` is built once per asteroid
    # by `evaluate_asteroid`; rebuilding it when a caller does not supply one
    # keeps this function usable on its own.
    if ctx is None:
        ctx = asteroid_context(asteroid_row, ops_df, config)
        if ctx is None:
            return None      # no usable mass; nothing to cap the payload with

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
    # With beneficiation OFF no array mass is added at all; the existing
    # 2,000 kg rig figure already carries its own power implicitly, and this
    # keeps a default run bit-identical to v1.4.0.
    # The five `_`-prefixed slots are dead HERE and must still be unpacked; 
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
    # The EP array does not; it is in interplanetary cruise, in permanent
    # sunlight, so `ep_w_per_kg` keeps the bare 1/r² figure and only the plant
    # takes the night-side penalty.
    w_per_kg              = ctx.solar_w_per_kg
    ep_w_per_kg           = w_per_kg
    w_solar_eff           = ctx.plant_w_per_kg_solar
    array_oversize_factor = ctx.array_oversize_factor
    plant_w_per_kg = w_solar_eff
    power_source   = "solar"

    # ── The power source is a SEARCHED architecture choice (v1.14.0) ─────────
    # It used to be resolved inside the sizing loop by `power_source_for_target`,
    # on MASS alone; take whichever of photovoltaic and radioisotope is lighter
    # at this distance.  That is not the objective this module reports, and the
    # two differ by 625× in price per watt ($500,000 against $800), so the model
    # was buying a nine- or ten-figure radioisotope plant to save array mass and
    # nothing ever asked whether that paid.
    #
    # It went unnoticed because it was unreachable: on v1.12.0 the branch fired
    # on ONE row of 15,566.  Adding the eclipse term makes photovoltaics roughly
    # half as good per kilogram, which moves the crossover from 3.46 AU to about
    # 2.1 AU and puts a third of the catalog on the nuclear side, at which point
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
    # An electric stage is not a chemical stage with better Isp; it needs a
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
    # thruster, 8% efficient, 5,000 kg of hardware per newton, was priced
    # identically to a gridded ion engine at 70% and 54 kg/N.  A third of the
    # winning missions in a full cislunar run were PPT.
    #
    # Both fall back to the old shared constants when the column is absent, so
    # a pre-Module-3-v1.10.0 catalog reproduces v1.11.0.  `schema_check()`
    # names them, because the fallback is silent and flattering.
    # v1.14.2: both figures are parsed once per run by
    # `_sizing_propellant_consts`, which reports None where the row states no
    # usable value, so the fallback to Module 3's shared constants is unchanged
    # and a pre-Module-3-v1.10.0 catalog still reproduces v1.11.0.
    # v1.17.4: resolved by `_ep_device_consts`, which the pre-filter's second
    # stage reads too.  ONE definition, two readers; see that function.
    eff_used, thruster_kg_per_n, ppu_kg_per_kw = _ep_device_consts(
        is_electric, thruster_eff_row, thruster_kg_per_n_row,
        ep_eff, ep_kg_per_kw, ppu_only_kg_per_kw,
    )

    # `isp_s_val`, `boiloff_pct` and `tank_frac` all arrive on `sizing_consts`.
    # ── Tankage (v1.11.0) ────────────────────────────────────────────────────
    # Module 3 quotes tank mass per LITRE, because that is what it scales with;
    # the cascade wants it per kilogram of propellant, so divide by density.
    # A propellant row predating Module 3 v1.9.0 has neither column and comes
    # through as 0.0, which reproduces v1.10.1 exactly.
    #
    # ISRU is exempt from boil-off; the propellant is made at the asteroid on
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
    # shortest stay the model allows (station_keeping_floor_yr, 0.25 yr), but
    # the stay is dig time plus the launch-window wait, which together run to
    # YEARS on the targets that most want a cryogenic upper stage.  Hydrolox at
    # 0.05%/day over a 4-year hold loads 2.1x what the rocket equation burns,
    # against the 1.1x the old estimate implied.  The ISRU feed is new for the
    # same reason: it is rock that has to be dug, and dug rock is time.
    #
    # v1.14.0 adds a seventh leg, VOLATILE CONTAINMENT.  A sealed shaded hold
    # scales with the water in the cargo, the water in the cargo comes out of
    # the payload knapsack, and the knapsack is solved against a payload the
    # containment mass helps determine.  Same ring, one more term, and it is
    # handled the same way rather than estimated once outside the loop, which
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
    # structure, which is exactly what it is; the hopper holds the cargo, the
    # seal and the shade keep the volatile fraction of it from leaving.  Folding
    # it into `structure_frac` means the closed-form solver carries it with no
    # change to the algebra: it is already the f in (1 + f).
    containment_frac = 0.0
    structure_frac_eff = structure_frac
    # v1.17.1: a Module 3 constant, resolved once instead of once per pass of
    # the loop below AND again at the settle-up.  One lookup, two readers, 
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
            # v1.17.4: one definition, two readers, the pre-filter's second
            # stage sizes the same stage off the same pass-1 cascade.
            (new_ep_kg, ep_power_watts,
             ep_thrust_n, ep_thrust_yr) = _ep_stage_kg(
                cascade, isp_s_val, eff_used, ep_w_per_kg,
                ppu_kg_per_kw, thruster_kg_per_n, config,
            )

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
        # plant to raise it for, with beneficiation off, the 2,000 kg rig's
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
        # top of, which is what lets it fold into structure_frac and leaves the
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
            # in the ledger and never entered the rocket equation, the mirror
            # image of the free-EP-stage bug, and the comment there asserted
            # the cascade had already flown it.  It had not: `power_system_kg`
            # came out 0.8-2.7% above the figure inside `hardware_total_kg` on
            # every row that liberated cargo water.  Sizing it here closes the
            # loop the same way every other feedback term in this ring is
            # closed, and it is why the term is no longer gated on
            # `beneficiate or isru`, a RAW mission to an icy body liberates
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
            # all that remains inside it is the Pu-238 ceiling, and that is a
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
            # absolute rather than relative: 1e-4 of a payload-scaling term is
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
    # a fraction of the fairing, say 25%, when sharing the vehicle with
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
    # and compared here, but only as a reported flag; it now binds.
    bulk_density = asteroid_row.get("density_gcm3")
    if bulk_density is None or pd.isna(bulk_density) or float(bulk_density) <= 0:
        bulk_density = 2.0    # default: rocky-asteroid average
    bulk_density_kg_per_L = float(bulk_density)         # g/cm³ ≡ kg/L

    vconsts = vehicle.get(_VEHICLE_CONSTS_KEY)        # v1.14.2, see candidate_combos
    if vconsts is None:
        vconsts = vehicle[_VEHICLE_CONSTS_KEY] = _vehicle_consts(vehicle)
    fairing_m3 = vconsts[0]
    usable_return_m3   = 0.25 * fairing_m3
    volume_capacity_kg = usable_return_m3 * 1000.0 * bulk_density_kg_per_L

    # `volume_fits` keeps its original sense; False means the payload the
    # mission would otherwise have returned does not fit, but the payload is
    # now actually reduced to what does fit.
    # ── Throughput cap (v1.4.0) ──────────────────────────────────────────────
    # You can only return what the rig can actually dig inside the maximum
    # stay.  Previously extraction was instantaneous and unbounded, so a
    # mission's haul was limited only by the rocket equation; the rig might
    # as well have been a vacuum cleaner with infinite suction.
    # v1.5.0: with beneficiation on, the throughput cap bounds the FEED the rig
    # digs, not the payload it flies home; that is the whole point of
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
    # concentrate reaches the purity bound, 100% of the best phase present, 
    # additional feed buys nothing: the delivered $/kg is already capped, while
    # the extra rock still costs dig time, energy, array mass and WACC.  A real
    # operator stops there, so the model does too.
    #
    #     ratio_to_saturate = best_phase / (bulk x recovery)
    #
    # then bounded by the safety cap, by what the rig can dig in the time
    # allowed, and by what the body can supply.  Where bulk value already
    # equals the best phase (a monomineralic body, pure ice, say) this
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
    # outbound-prop, launch all depend on m_payload, must be redone to
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
    # v1.10.0: the return vehicle grows with what it carries; see
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

        Only the pieces that depend on `hardware_kg`, the payload, the return
        vehicle, its heat shield and its tank are all fixed by m_payload above.
        Factored out because it has to be evaluated TWICE: once to learn how
        much ISRU propellant the mission makes (which sets the dig time, which
        sets the power plant, which is itself hardware), and once more with the
        settled plant mass.  Two hand-written copies of this arithmetic drifting
        apart is precisely how a mass ends up in the rocket equation without a
        matching entry in the ledger.
        """
        # The return TANK is launched from Earth even under ISRU; you can make
        # propellant at an asteroid, not a pressure vessel, so it is inside
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
    # re-derived here, and, critically, the cascade is rebuilt afterwards from
    # the result.
    #
    # Until v1.12.0 this ran ~60 lines further down, after `actual_cascade` had
    # already been built.  The array for baking CARGO water was therefore
    # priced in the ledger and never launched: `power_system_kg` came out
    # 0.8-2.7% above the figure inside `hardware_total_kg` on every row that
    # liberated any, and a raw mission to an icy body paid for an array it flew
    # none of.  The comment there claimed "the cascade already flew" it.  It
    # had not.  This is the same asymmetry as the free EP stage, pointing the
    # other way, a price with no mass rather than a mass with no price.
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
        # feed, to size the containment.  Reused rather than recomputed: one
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
    # rechecked against the vehicle; the closed-form guarantee only holds at
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

    # ── Delivered $/kg, the best load assemblable from this rock ────────────
    # Not "go and fetch platinum": fill the hold with the most valuable phases
    # the target actually contains, in whatever ratio maximises the load.  The
    # two honest bounds fall out of the knapsack automatically; you cannot
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
    # of it, and that stay time flows into ops cost and WACC.  ISRU feed counts,
    # propellant made on site is rock the same rig had to move.
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
    # Both terms, and the array they size, were settled above, before the
    # cascade was rebuilt, so that the plant in the ledger is the plant in the
    # rocket equation.  `water_kg` is carried down here only to be reported.
    # ── PROGRAMME SCALE AND FLEET SIZE (v1.15.0) ─────────────────────────────
    # Everything above this line is the MASS CASCADE, and none of it depends on
    # how many missions the programme flies.  N enters this module in exactly
    # three places downstream: the cost model, market saturation and
    # reliability growth, and in none of the rocket equation, the fixed-point
    # power solve, the payload knapsack or the concentration sweep.
    #
    # That asymmetry is what makes programme size affordable to SEARCH rather
    # than merely to set: the expensive half of the mission is solved once, and
    # every rung of the fleet ladder is priced off the same cascade.  Running
    # the whole pipeline again at another N, which is how every
    # programme-scale figure in this project was produced, re-solves all of it
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
    # v1.16.0.  How often the rig can start again, the dig, unless windows open
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
    # bit-identity check, so the ORDER of these terms is load-bearing, the same
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
        # v1.17.6: five Module 3 rows, resolved once per run rather than once
        # per candidate mission.  See `_ops_reliability_constants`.
        (p_launch, mtbf_yr, p_first,
         rel_alpha, p_mature) = _ops_reliability_constants(ops_df)
        p_cruise  = math.exp(-mission_duration_yr / mtbf_yr) if mtbf_yr > 0 else 1.0

    gross_base           = gross_value
    delivered_base       = delivered_value_per_kg

    # ── v1.17.2: the cost cascade's N-independent half, built ONCE ───────────
    # Every argument below is fixed for the whole ladder; `cadence_yr` included,
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
    # v1.17.5: the same argument one function further in.  The rig shares and
    # the programme-calendar multipliers are a function of the campaigns one
    # rig flies and of the PROLOGUE, and the ladder crosses ~8 fleets with
    # `trips` ≤ 5 campaigns, so ~42 options ask `_mission_cost_tail` for at
    # most ten distinct answers to that block.  Per-candidate for the same
    # reason `sat_by_fleet` is: every other input to it lives in `cost_prologue`.
    rig_by_share: Dict[Tuple[int, bool], Tuple[float, ...]] = {}

    # ⚠️  v1.17.6: NO annotations on this signature.  It is a nested def, so its
    # annotations are evaluated every time the enclosing function runs, and
    # `Optional[int]` is a `typing` subscript: 331 ns against 95 ns for the
    # bare def, 10,741 times per 150-row sample.  Types: (int, int, int | None,
    # bool).
    def _price_programme(n_missions, fleet, per_ship=None, full=True):
        """Everything downstream of the cascade, for one programme size.

        Returns `(cost, total_cost, gross, saturation_mult, concurrent,
        p_success, p_mining, delivered_per_kg)`.  Nothing here re-enters the
        rocket equation; it is one pass of straight-line arithmetic over a
        cascade that is already solved.

        v1.17.1: `full=False` asks for the total alone and leaves `cost` None.
        The ladder below compares options on `total_cost` and nothing else, so
        it prices cheaply and re-prices the single winner in full, one extra
        call out of ~40, against a 40-key dict built and discarded on every one
        of the other 39.  `total_cost` is the same float either way; see the
        early return in `_mission_cost_tail`.
        """
        c = _mission_cost_tail(cost_prologue, n_missions, per_ship,
                               totals_only = not full, rig_cache = rig_by_share)
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
        # number by construction, N = F × trips, and one derivation fewer.
        concurrent = 1.0
        if saturation_applies:
            concurrent = fleet
            # v1.17.2: this block reads `fleet` and nothing else the ladder
            # varies, `sale_terms`, `gross_base`, `m_payload` and the mission
            # duration are all fixed for the candidate, so it is a function of
            # F alone, and the ladder is the F ladder CROSSED WITH W.  It was
            # therefore being recomputed once per W: ~40 options over ~8
            # distinct fleets, so four out of five passes re-derived a sum they
            # had already made.  Memoised per candidate on the integer F.
            #
            # Bit-identical by construction rather than by rounding: the same
            # F re-runs the same `+=` over the same list in the same order, so
            # the cached float IS the float the loop would have produced.  That
            # matters here more than most places; this is the accumulation
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
        # are charged in FULL, which is correct; you spend the money either way,
        # and launch insurance replaces hardware, not revenue, so this is not
        # a double count.
        ps = 1.0
        pm = 1.0
        if config.model_reliability:
            # v1.9.0: the mining chain LEARNS, so p_mining is the fleet average
            # over the programme rather than the first-of-kind figure held flat.
            # Launch and cruise reliability deliberately do not grow; launch
            # vehicles are mature, and MTBF is a duration exposure rather than a
            # heritage question.
            pm = (_mining_reliability_cached(n_missions, p_first, rel_alpha, p_mature)
                  if config.model_reliability_growth else p_first)
            ps = max(0.0, min(1.0, p_launch * p_cruise * pm))
            g *= ps
        return c, total_cost, g, sat, concurrent, ps, pm, delivered

    # v1.17.1: the ladder prices on totals and the winner is rebuilt in full
    # once, below.  `single` is the common case, the search off, one option, 
    # and it skips the rebuild entirely by pricing in full straight away.
    programmes, fleet_ladder = _programme_ladder_cached(rig_trips, config)
    single       = len(programmes) == 1
    # v1.17.6: the ranking objective is a config field, so it is resolved once
    # here rather than re-read on every rung below.  See `_objective_key`.
    on_profit    = _selects_on_profit(config.selection_objective)
    best_n, best_f, best_w = programmes[0]
    best_priced  = _price_programme(best_n, best_f, best_w, full=single)
    best_pkey    = _objective_key(
        best_priced[2] - best_priced[1],
        best_priced[2], best_priced[1], config, on_profit)
    priced_count = 1

    for n_missions, fleet, per_ship in programmes[1:]:
        cand = _price_programme(n_missions, fleet, per_ship, full=False)
        priced_count += 1
        key = _objective_key(cand[2] - cand[1], cand[2], cand[1], config, on_profit)
        if key > best_pkey:
            best_pkey, best_priced = key, cand
            best_n, best_f, best_w = n_missions, fleet, per_ship

    # One refinement pass around the coarse winner, on the same geometric
    # spacing plus both integer neighbours; see `fleet_refinement`.  Skipped
    # entirely when the programme is not being searched, which is the default
    # and the path every committed figure was measured on.
    #
    # v1.16.0: refined at the winner's OWN campaigns-per-ship.  W is enumerated
    # exhaustively, so it needs no refinement of its own, but it does need to
    # be held fixed while F moves, because N = F × W and refining F against some
    # other W would price a programme the search never proposed.
    if len(programmes) > 1:
        for fleet in _fleet_refinement_cached(best_f, fleet_ladder):
            n_missions = fleet * best_w
            cand = _price_programme(n_missions, fleet, best_w, full=False)
            priced_count += 1
            key = _objective_key(cand[2] - cand[1], cand[2], cand[1], config, on_profit)
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
        # True when the concentrate is at the purity ceiling, i.e. grade, not
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
        # Kept with its exact v1.14.0 semantics: 1.0 whenever the saturation
        # term is switched off, so that a gated-off build still reproduces
        # that release byte for byte.  `fleet_ships` below is the unconditional
        # count and is the one to read.
        "concurrent_missions":      concurrent_missions,
        # ── v1.15.0 programme scale and fleet size ─────────────────────────
        # `programme_missions` is N and `fleet_ships` is F, and the invariant
        # between them is N = F × trips_per_ship whenever the search is on.
        # With it off, N is whatever the config said and F is the fleet that
        # size implies, the two columns still describe the same programme,
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
        # 1.0 means no calendar charge was levied; either W = 1, or the term
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
        # Cost breakdown, per-line items
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

    v1.10.0.  Every per-asteroid search in this module: over concentration
    ratio, over vehicle, over propellant, over return mode, used to pick the
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
      • If none does, which is every default configuration today, minimise
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


# The selection objective is a free-text config field, normalised on every read.
# It is read once per programme option, so the normalisation ran ~458k times on
# a 150-row sample to answer a question whose input is fixed for the run.
# Keyed on the RAW value rather than on `id(config)`: the raw string IS the
# input, so two configs naming the same objective share one entry, and a config
# edited between runs is still answered correctly.
_SELECTION_ON_PROFIT: Dict[Any, bool] = {}


def _selects_on_profit(objective: Any) -> bool:
    """Whether `selection_objective` names the raw-profit ranking.

    Memoised because it is a string parse in the innermost loop of the search.
    The parse itself is untouched -- this caches its answer, it does not change
    what counts as "profit".
    """
    try:
        hit = _SELECTION_ON_PROFIT.get(objective)
    except TypeError:            # unhashable: parse it and cache nothing
        return str(objective).strip().lower() == "profit"
    if hit is None:
        hit = _SELECTION_ON_PROFIT[objective] = (
            str(objective).strip().lower() == "profit")
    return hit


def _objective_key(
    profit: float, gross: float, cost: float, config: CalcConfig,
    on_profit: Optional[bool] = None,
) -> Tuple[float, float]:
    """`selection_key`'s ranking algebra, over loose scalars.

    v1.15.0 split this out because the programme-scale search ranks candidates
    before any result dict exists, building one per rung of the fleet ladder
    just to read three fields back out of it would allocate a ~130-key dict per
    comparison.  It is a split for the caller's convenience and NOT a second
    statement of the rule: `selection_key` is defined as this function, so the
    two cannot drift, which is the failure mode this file warns about wherever
    algebra appears twice (see `_combo_can_close`).

    v1.17.5: the objective is read through `_selects_on_profit`, which memoises
    the string normalisation.  `str(x).strip().lower()` measures 93 ns against a
    dict lookup's 31 ns, and this function is called 457,776 times on a 150-row
    beneficiated+searched sample -- once per rung of every programme ladder --
    to re-derive one boolean from a config field that cannot change mid-solve.
    The comparison it feeds is unchanged, so both returned floats are the same
    floats.

    v1.17.6: `on_profit` lets a caller that ranks many candidates against ONE
    config hand the answer in, which is the programme ladder; it called this
    444,353 times on that sample against 10,741 candidate missions, so even a
    dict lookup was being made 41 times more often than the question was asked.
    None keeps the read, so every other caller is untouched.  This is still one
    statement of the rule: the branches and both returned floats are unchanged,
    and `on_profit` can only carry what `_selects_on_profit` would have said.
    """
    if on_profit is None:
        on_profit = _selects_on_profit(config.selection_objective)
    if on_profit:
        return (0.0, profit)
    if profit > 0:
        return (1.0, profit)
    if gross <= 0:
        return (-1.0, -cost)          # no revenue at all, lose the least
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
    is not simply the highest profit; see there.

    Without beneficiation there is nothing to choose: one solve at ratio 1.0.

    With it, the concentration ratio is a genuine economic decision rather
    than a setting.  Digging more feed raises the grade of the load, but the
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
    # ratio 1.0; that would still pay the separation recovery loss, the
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
    "False" as True and NaN as True, so a propellant that cannot fly this
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
    # kinetic launchers, and said so in the column's own documentation; "it is
    # in this table because it is DISQUALIFYING for the kinetic launchers", 
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
    # only consumables genuinely changes a mining programme's economics, but
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
    # the propellant row and the config, so they are derived here, once per
    # run, on the same dict every asteroid will read, rather than re-parsed out
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
        # v1.17.5: and the ISRU feed pair, for the same reason and by the same
        # route.  See `_isru_propellant_consts`.
        propellant[_ISRU_CONSTS_KEY] = _isru_propellant_consts(propellant)
    vehicle_rows = [_row_to_dict(v) for _, v in vdf.iterrows()]
    for vehicle in vehicle_rows:
        vehicle[_VEHICLE_CONSTS_KEY] = _vehicle_consts(vehicle)
    return [
        (vehicle, propellant)
        for vehicle in vehicle_rows
        for propellant in propellant_rows
    ]


# ── The ladder is a function of `trips` and the config  (v1.17.6) ──────────
# `programme_options` builds ~42 tuples, and `fleet_refinement` its four more,
# once per SURVIVING CANDIDATE: 10,741 times on a 150-row beneficiated+searched
# sample, for a list whose only asteroid-dependent input is `trips`, which is
# `min(life / stay, max_trips)` and therefore one of a handful of small
# integers.  Together they measured ~3.6% of that cell.
#
# The sorted fleet ladder the refinement pass needs is derived from the same
# tuples (`sorted({f for _n, f, _w in programmes})`), so it is cached alongside
# rather than rebuilt per candidate.
#
# ⚠️  Private, and `programme_options` is untouched.  That function is the
# single readable statement of the search's shape and the entry point for
# anyone outside this loop; this only stops the loop asking it the same
# question 10,741 times.
#
# ⚠️  The lists are shared, not copied, and nothing may mutate them; both are
# iterated and indexed and nothing more.  Keyed on the config VALUES the two
# functions read rather than on `id(config)`, so a config edited between runs
# is answered correctly (the same argument `_selects_on_profit` makes).
_PROGRAMME_LADDER_CACHE: Dict[Tuple[Any, ...],
                              Tuple[List[Tuple[int, int, int]], List[int]]] = {}
_FLEET_REFINEMENT_CACHE: Dict[Tuple[int, Tuple[int, ...]], List[int]] = {}


def _programme_ladder_cached(
    rig_trips: Optional[Tuple[int, int, Optional[int]]], config: CalcConfig,
) -> Tuple[List[Tuple[int, int, int]], List[int]]:
    """`(programme_options(...), sorted fleet ladder)`, memoised."""
    key = (rig_trips[0] if rig_trips is not None else None,
           int(config.nre_amortization_missions),
           bool(config.model_programme_calendar),
           bool(config.optimise_programme_scale),
           int(config.max_fleet_ships),
           int(config.programme_search_steps))
    hit = _PROGRAMME_LADDER_CACHE.get(key)
    if hit is None:
        programmes = programme_options(rig_trips, config)
        hit = _PROGRAMME_LADDER_CACHE[key] = (
            programmes, sorted({f for _n, f, _w in programmes}))
    return hit


def _fleet_refinement_cached(f_best: int, ladder: List[int]) -> List[int]:
    """`fleet_refinement(f_best, ladder, ladder[0], ladder[-1])`, memoised."""
    key = (f_best, tuple(ladder))
    hit = _FLEET_REFINEMENT_CACHE.get(key)
    if hit is None:
        hit = _FLEET_REFINEMENT_CACHE[key] = fleet_refinement(
            f_best, ladder, ladder[0], ladder[-1])
    return hit


def _prefilter_probe(
    asteroid_row: Row,
    combos:       List[Tuple[Dict[str, Any], Dict[str, Any]]],
    config:       CalcConfig,
) -> Tuple[int, int]:
    """(candidates considered, candidates kept) for one asteroid.

    Mirrors the loop nest in `evaluate_asteroid` exactly, same axes, same
    order, same test, so the printed rate describes the search that is about
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
        vconsts   = vehicle.get(_VEHICLE_CONSTS_KEY)
        leo_cap   = (vconsts[1] if vconsts is not None
                     else _vehicle_consts(vehicle)[1])
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
    return was flown propulsively, or vice versa, purely because of what some
    other asteroid needed.

    Returns a single result dict (best mission) or None if nothing is viable.

    `combos` is the precomputed candidate cross-join from candidate_combos().
    Left as None it is rebuilt per call, correct but slow, so the main loop
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
    # re-derive per candidate: mineable mass, throughput cap, launch-window
    # wait, ops constants, dark period, eclipse-corrected specific power
    # (v1.14.1).  None means no usable mass, which no candidate could rescue.
    ctx = asteroid_context(asteroid_row, ops_df, config)
    if ctx is None:
        return None
    # Purity bound for beneficiation, the richest concentrate obtainable.
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
    # question; it needs water in the rock AND a stage that can burn what
    # water makes, so it is decided inside the combo loop rather than here.
    isru_allowed = (config.use_isru_return_propellant
                    and config.optimise_architecture_per_asteroid)

    # ── Power sources worth pricing for this body (v1.14.0) ──────────────────
    # A radioisotope plant is only ever a candidate where it would be LIGHTER
    # than photovoltaics, which depends on the body's distance and, since the
    # eclipse term, on its rotation.  Both are properties of the asteroid, so
    # the filter is resolved once here rather than per candidate mission, and
    # inner-system bodies never pay for a second pass.
    #
    # `power_source_for_target` keeps its job as the MASS comparator; what
    # changed in v1.14.0 is that its answer generates a candidate instead of
    # being the decision.  Probed at 1 W, any positive draw under the ceiling
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

    # Keep the best candidate under the selection objective; see
    # selection_key for why that is not simply the highest profit.
    # Whether ISRU chemistry closes is a (target × PROPELLANT) question and the
    # combo grid is vehicle-major, so asking it per combo asked it once per
    # vehicle: 36 times for each of the 41 propellant rows, for every asteroid
    # in the catalog.  Memoised on the propellant's identity, which is stable:
    # `candidate_combos` builds one dict per propellant row and shares it across
    # every vehicle pairing (v1.14.1).
    # ⚠️  v1.17.6: ONE entry carrying everything the loop below reads off a
    # propellant, not four lookups for four of them.  The grid is vehicle-major,
    # so `isru_modes`, the two pre-filter constant tuples and the identity key
    # were each resolved once per (vehicle × propellant): 714,000 lookups per
    # 2,000 rows for 21 propellants' worth of answers.  Same shape as
    # `sat_by_fleet` and `rig_by_share` in the ladder: the question was asked at
    # a finer granularity than it has answers.
    prop_cache: Dict[int, Tuple[List[bool], Any, Any, int]] = {}
    # And the vehicle-independent half of the pre-filter, for the same reason
    # (v1.14.2).  Keyed by (propellant identity × Δv option × ISRU), which is
    # everything `_combo_close_terms` reads, so seventeen vehicles now share one
    # evaluation instead of recomputing it each.  `dv_options` is this asteroid's
    # own list, so the index is a stable key within this call.
    close_terms_cache: Dict[Tuple[int, int, bool],
                            Optional[Tuple[bool, float, float, float]]] = {}

    # v1.17.6: the Δv options resolved to plain scalars once per asteroid.  All
    # three call sites below re-read them out of the dict and re-ran `float()` /
    # `bool()` / `str()` on every (combo × Δv × ISRU) iteration, for a list this
    # asteroid has two or three entries in.  Values and types are unchanged; only
    # the conversions stop repeating.
    dv_resolved = [
        (i,
         float(o["dv_out_m_s"]),
         float(o["dv_ret_m_s"]),
         (config.heat_shield_frac_of_payload if bool(o["aero"]) else 0.0),
         bool(o["aero"]),
         str(o["rendezvous_apsis"]))
        for i, o in enumerate(dv_options)
    ]

    best     = None
    best_key = (-np.inf, -np.inf)
    for vehicle, propellant in combos:
        pkey  = id(propellant)
        pinfo = prop_cache.get(pkey)
        if pinfo is None:
            isru_modes = [False]
            if config.use_isru_return_propellant and isru_feed_kg_per_kg_propellant(
                    asteroid_row, propellant, config) is not None:
                # Feasible here.  Price both when searching; otherwise take ISRU
                # as the config's instruction and fly it wherever it is possible.
                isru_modes = [False, True] if isru_allowed else [True]
            # `candidate_combos` attaches these, but a caller that hand-builds
            # `combos` will not have.  Derive on demand rather than treating the
            # missing key as "no usable Isp"; that reads as infeasible and would
            # prune the ENTIRE search silently, which is the quiet-wrong-answer
            # failure this repo keeps finding.  Absent means unknown, not dead.
            if prefilter and _PREFILTER_CONSTS_KEY not in propellant:
                propellant[_PREFILTER_CONSTS_KEY] = _prefilter_propellant_consts(
                    propellant, config)
            # v1.17.4: the pre-filter's second stage sizes the electric stage, so
            # it reads the SIZING constants rather than the pre-filter's four.
            # `candidate_combos` attaches these; a caller that hand-builds
            # `combos` will not have, and absent means unknown rather than dead, 
            # so the second stage is skipped rather than allowed to refute on a
            # default.
            pinfo = prop_cache[pkey] = (
                isru_modes,
                propellant.get(_PREFILTER_CONSTS_KEY) if prefilter else None,
                propellant.get(_SIZING_CONSTS_KEY) if prefilter else None,
                pkey,
            )
        isru_modes, pf_consts, sizing_consts, pkey = pinfo
        vconsts   = vehicle.get(_VEHICLE_CONSTS_KEY)
        if vconsts is None:
            vconsts = vehicle[_VEHICLE_CONSTS_KEY] = _vehicle_consts(vehicle)
        _fairing, leo_cap, leo_ok = vconsts
        for dv_i, dv_out, dv_ret, dv_tps, dv_aero, dv_apsis in dv_resolved:
            for isru in isru_modes:
                # Sits ABOVE the power-source loop on purpose: pass 1 of the
                # sizing loop runs at zero plant mass, so it cannot tell the two
                # power sources apart and would refute both identically.
                #
                # pf_consts is None only when the propellant states no usable
                # Isp, which `max_return_payload_kg` rejects on entry too, so
                # pruning it here agrees with the solver rather than pre-empting
                # it.
                #
                # v1.14.2 splits the test at the vehicle boundary; see
                # `_combo_close_terms`.  The composition is exactly
                # `_combo_can_close`, in the same operations in the same order.
                if prefilter:
                    if pf_consts is None or not leo_ok:
                        continue
                    ckey  = (pkey, dv_i, isru)
                    terms = close_terms_cache.get(ckey, _UNCACHED)
                    if terms is _UNCACHED:
                        terms = _combo_close_terms(
                            pf_consts, dv_out, dv_ret, dv_tps,
                            isru, window_wait_yr, config)
                        close_terms_cache[ckey] = terms
                    if terms is None or not _closes_with(leo_cap, terms):
                        continue
                    # ── Stage 2 (v1.17.4) ────────────────────────────────────
                    # Stage 1 refutes at pass 1 of the sizing loop, which flies
                    # no electric stage because pass 1 is what SIZES one.  On
                    # the real population 74.3% of the candidates that get past
                    # stage 1 then die on pass 2, when that stage becomes mass,
                    # and they die identically at every concentration ratio
                    # and every power source, because the stage is sized off a
                    # cascade that can see neither.
                    #
                    # Sits here rather than inside `evaluate_combo` for exactly
                    # that reason: one evaluation per (vehicle × propellant ×
                    # Δv × ISRU) replaces one per ratio per power source, which
                    # is ~8 to ~16 of them.  See the function for why refusing
                    # here is a decision rather than a guess.
                    if sizing_consts is not None and not _closes_carrying_its_own_stage(
                            leo_cap, sizing_consts, ctx.ops,
                            ctx.solar_w_per_kg, ctx.structure_frac,
                            window_wait_yr, dv_out, dv_ret, dv_tps,
                            isru, config):
                        continue
                for power_mode in power_modes:
                    result = evaluate_combo(
                        asteroid_row, vehicle, propellant,
                        bulk_value, dv_out, dv_ret,
                        ops_df, config,
                        best_phase_value_per_kg=best_phase_value,
                        phases=phases, markets=markets,
                        aero=dv_aero, isru=isru,
                        rendezvous_apsis=dv_apsis,
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
# three identity-keyed lookup caches, so the main loop is embarrassingly
# parallel and had been running on one core.
#
# What makes this more than a one-line change is Windows.  There is no fork, so
# every worker is a fresh interpreter that has to reconstruct the parent before
# it can unpickle the first task, and it does that by importing the parent's
# __main__.  Which module that is depends on how the pipeline was launched, and
# one of the three launch paths is actively hostile; see _spawn_environment.

_WORKER_CTX: Dict[str, Any] = {}


def _worker_init(
    minerals: pd.DataFrame,
    ops:      pd.DataFrame,
    combos:   List[Tuple[Dict[str, Any], Dict[str, Any]]],
    config:   CalcConfig,
) -> None:
    """Seed one worker with the read-only state every chunk needs.

    Sent once per worker rather than once per chunk.  Only two of the upstream
    catalogs reach the inner search; minerals (prices, market depths) and ops
    (Module 3's reference rows), and both are a few dozen rows.  The asteroid
    catalog is never shipped whole; a worker only ever receives the block it is
    about to evaluate.
    """
    _WORKER_CTX["catalogs"] = {"minerals": minerals, "ops": ops}
    _WORKER_CTX["combos"]   = combos
    _WORKER_CTX["config"]   = config


# Rows are handed to the search a BLOCK at a time, not one at a time (v1.17.4).
# 256 is the same figure `_chunk_frame` floors a worker block at, and for the
# same reason: big enough that the per-call overhead disappears, small enough
# that nothing large is ever materialised.
_ROW_DICT_BLOCK = 256


def _iter_row_dicts(df: pd.DataFrame, block: int = _ROW_DICT_BLOCK):
    """Yield each row of `df` as a plain dict, converting a block at a time.

    v1.17.4.  `iterrows()` builds a pandas Series per row and `_row_to_dict`
    then throws it away: 67.3 µs a row on the 46-column catalog, against
    **17.0 µs** for `DataFrame.to_dict("records")` over a block. That is ~50 µs
    on every row of the catalog whether or not it turns out to be evaluable:
    ~67-78 s on a full cislunar pass, which is ~5-6% of the raw cell.

    ⚠️  Value- AND type-preserving, which is the only reason it is allowed.
    Checked cell by cell over a 20,000-row sample: **zero value mismatches and
    zero type mismatches**. Both routes unbox numpy scalars to their Python
    equivalents, and `np.float64` IS a C double; the same argument v1.10.1
    made when it introduced `_row_to_dict`, and the four-cell bit-identity diff
    is what confirms it end to end.

    ⚠️  Block at a time, NOT `df.to_dict("records")` in one go. The serial path
    hands this the whole 1.55 M-row catalog, and materialising 1.55 M dicts at
    once would cost several GB for no gain; the conversion is amortised at
    256 rows just as well as at 1.5 million.
    """
    n = len(df)
    for i in range(0, n, block):
        for row in df.iloc[i:i + block].to_dict("records"):
            yield row


def _evaluate_chunk(chunk: pd.DataFrame) -> List[dict]:
    """Evaluate one contiguous block of asteroids inside a worker.

    Converting rows here rather than in the parent is deliberate: the cost
    lands on a worker instead of on the single core the parent has to itself,
    and both paths hand `evaluate_asteroid` identical input because both go
    through `_iter_row_dicts`.
    """
    catalogs = _WORKER_CTX["catalogs"]
    combos   = _WORKER_CTX["combos"]
    config   = _WORKER_CTX["config"]

    out: List[dict] = []
    for row in _iter_row_dicts(chunk):
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
    cannot repay their own startup, which is what keeps a 400-row interactive
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

    Asteroids are not equally expensive, the number of viable return modes,
    whether ISRU is even possible, and the width of the concentration sweep all
    vary per body, so one block per worker would leave most cores idle waiting
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
    does not, Streamlit installs a synthetic module named `__main__` whose
    `__file__` points at `ui.py`, so the fallback runs the entire Streamlit app
    inside every worker.  That is not a theoretical hazard; a three-worker pool
    was observed executing the app three times before this was written.
    Pointing `__spec__` at this module instead makes each worker import the
    pipeline, which is what it needs anyway.

    **Quiet workers.**  That import replays the startup banner: 60 lines per
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

    Returns the result list, or None if no pool could be started; the caller
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
            print(f"     WARN   Could not start worker processes ({exc}) - "
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
def build_profitability_catalog(config: CalcConfig = CONFIG) -> pd.DataFrame:
    """Run the full Module 4 calculation pipeline."""
    t0 = datetime.now()
    print("=" * 75)
    print("    PROFITABILITY PIPELINE - MODULE 4")
    print(f"      {t0.strftime('%Y-%m-%d %H:%M:%S')}  |  v{config.pipeline_version}")
    print("=" * 75)

    # ── Step 1, Load catalogs ───────────────────────────────────────────────
    catalogs = load_all_catalogs(config)

    # ── Step 2, Integrity checks ────────────────────────────────────────────
    integrity_check(catalogs)
    destination_check(catalogs, config)

    # ── Step 3, Iterate asteroids ───────────────────────────────────────────
    asteroids = catalogs["asteroids"]

    # Filter to rows with the minimum data needed to be evaluable
    needed_cols = ["estimated_mass_kg", "comp_metal_fraction",
                   "comp_silicate_fraction", "comp_carbon_fraction",
                   "comp_ice_fraction"]
    missing_cols = [c for c in needed_cols if c not in asteroids.columns]
    if missing_cols:
        print(f"\nFAIL  Asteroid catalog missing required columns: {missing_cols}")
        print("     Has Module 1 been re-run with enrich_composition?  Aborting.")
        return pd.DataFrame()

    mass_ok = pd.to_numeric(asteroids["estimated_mass_kg"], errors="coerce") > 0
    work_df = asteroids[mass_ok].copy()
    print(f"\n  Evaluating {len(work_df):,} asteroids with positive mass "
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
        print(f"        Capped at {len(work_df):,} of {n_before:,} rows "
              f"({how}; eval_row_cap / eval_row_sampling in CONFIG)")

    # Candidate (vehicle × propellant) grid is config-driven, not asteroid-
    # driven, build it once and hand it to every evaluation.
    combos = candidate_combos(catalogs, config)
    if not combos:
        print("\nFAIL  No candidate vehicle x propellant combinations after "
              "filtering - check operational_vehicles_only / candidate_* in CONFIG.")
        return pd.DataFrame()
    print(f"       {len(combos):,} vehicle x propellant combinations per asteroid")

    # ── How much the pre-filter is actually removing (v1.14.1) ───────────────
    # Probed rather than tallied.  A running count would have to come back from
    # every worker, which means changing what a chunk returns, and the number is
    # a property of the POPULATION, a stride probe answers it to well inside
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
        for prow in _iter_row_dicts(work_df.iloc[probe_idx]):
            seen_row, kept_row = _prefilter_probe(prow, combos, config)
            seen += seen_row
            kept += kept_row
        if seen:
            print(f"        Pre-filter keeps {kept / seen * 100:.1f}% of "
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
        """Tick the evaluated-row counter and print on each whole percent.

        A CALLBACK rather than a loop counter because the parallel path reports
        a chunk at a time and the serial path a row at a time; both tick the
        same counter and print the same line, so only the granularity differs.

        ⚠️  The wording is load-bearing: `ui.py`'s `ProgressScan` regexes
        "i / n evaluated" out of the stream to size its bar, and rewording this
        silently drops the dashboard back to an indeterminate bar.
        """
        progress["done"] += rows_done
        i = progress["done"]
        if n >= 100 and (i * 100) // n != progress["pct"]:
            progress["pct"] = (i * 100) // n
            print(f"     ... {i:,} / {n:,} evaluated  ({progress['pct']}%)")

    results = None
    n_workers = _resolve_worker_count(config, n)
    if n_workers > 1:
        print(f"       {n_workers} worker processes "
              f"({os.cpu_count()} logical CPUs, parallel_workers="
              f"{config.parallel_workers or 'auto'})")
        results = _evaluate_in_parallel(
            work_df, catalogs, config, combos, n_workers, report,
        )

    if results is None:                       # serial path, or no pool started
        progress["done"] = progress["pct"] = 0
        results = []
        for asteroid in _iter_row_dicts(work_df):
            result = evaluate_asteroid(asteroid, catalogs, config, combos)
            if result is not None:
                results.append(result)
            report(1)

    if not results:
        print("\nFAIL  No viable evaluations - every asteroid failed.")
        return pd.DataFrame()

    df = pd.DataFrame(results)

    # ── Step 4, Rank + tag ──────────────────────────────────────────────────
    df["catalog_date"]     = t0.strftime("%Y-%m-%d")
    df["pipeline_version"] = config.pipeline_version
    df = df.sort_values("profit_usd", ascending=False).reset_index(drop=True)

    # Sanity flags for downstream
    df["viable"]      = df["profit_usd"] > 0
    df["profit_M$"]   = df["profit_usd"] / 1e6   # for human-readable preview
    df["gross_M$"]    = df["gross_value_usd"] / 1e6
    df["cost_M$"]     = df["total_cost_usd"] / 1e6

    # ── Step 5, Export ──────────────────────────────────────────────────────
    out_path = os.path.join(config.output_dir, config.output_filename)
    df.to_csv(out_path, index=False)
    print(f"\n       Profitability catalog -> {out_path}  ({len(df):,} rows)")

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
            print(f"       Architecture chosen: {'  |  '.join(bits)}")

    # ── What the programme search chose (v1.15.0) ────────────────────────────
    # Same argument as the block above, and it matters more here, because the
    # two ways this axis can be reported as a result while being an artefact are
    # both visible from these three numbers:
    #
    #   • EVERY ROW AT THE LADDER'S TOP means `max_fleet_ships` is BINDING, not
    #     bounding.  That happens when nothing pushes back on scale; a payload
    #     whose commodities have no `annual_market_kg` entry gets an infinite
    #     market, market saturation returns 1.0 forever, and the objective is
    #     then monotone in N.  Reporting the top rung of a monotone ladder is
    #     reporting where the loop stopped, and it is exactly the failure
    #     v1.14.0 closed.
    #   • EVERY ROW AT F = 1 means the fleet never wanted to grow, so the axis
    #     is costing runtime and buying nothing.
    if config.optimise_programme_scale and not config.model_rig_service_life:
        print("     WARN   optimise_programme_scale is ON but model_rig_service_life "
              "is OFF, so one rig serves any programme, nothing is ever "
              "concurrent, and market saturation cannot push back. The search "
              "is refused rather than run - it would report the ladder's top "
              "rung as a result. See programme_options().")
    elif config.optimise_programme_scale and "fleet_ships" in df.columns:
        f = df["fleet_ships"]
        at_cap = int((f >= config.max_fleet_ships).sum())
        print(f"       Programme chosen: fleet median {f.median():.0f} ship(s), "
              f"max {f.max():.0f}  |  N median {df['programme_missions'].median():.0f}, "
              f"max {df['programme_missions'].max():.0f}  |  "
              f"{int((f <= 1).sum()):,} single-ship")
        if "trips_per_ship" in df.columns:
            binds = df["rig_trip_limit_binds"]
            print(f"       Rig life: {df['trips_per_ship'].median():.0f} trips median "
                  f"(calendar cap {df['rig_trips_calendar_cap'].median():.0f})  |  "
                  f"cycle bound binds on {binds.mean():.1%} of rows")
        if at_cap:
            print(f"     WARN   {at_cap:,} row(s) ({at_cap/len(df):.1%}) sit AT "
                  f"max_fleet_ships = {config.max_fleet_ships}. The ladder is "
                  f"binding, not bounding - check those rows have a finite "
                  f"market before reading their N as an optimum.")

    n_viable = int(df["viable"].sum())
    elapsed  = (datetime.now() - t0).total_seconds()
    print("\n" + "=" * 75)
    print("  OK  PROFITABILITY ANALYSIS COMPLETE")
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

    regex=False, designations and names carry regex metacharacters ("(1)
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


print("\nOK  Helper utilities available:")
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
        print(f"    TOP {CONFIG.top_n_preview} MOST PROFITABLE ASTEROIDS")
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
        print("    PROFITABILITY BY COMPOSITION GROUP")
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
        print("    WINNING VEHICLE x PROPELLANT COMBINATIONS")
        print(f"{'='*95}")
        if "vehicle" in catalog.columns and "propellant" in catalog.columns:
            combo = (
                catalog.groupby(["vehicle", "propellant"])
                       .size().reset_index(name="n_asteroids")
                       .sort_values("n_asteroids", ascending=False)
            )
            print(combo.head(15).to_string(index=False))

        # ── Cost-component diagnostic ────────────────────────────────────────────
        # Average dollar breakdown; tells the user WHERE the money is going.
        # If launch dominates → consider a cheaper vehicle; if NRE/hardware
        # dominates → multi-mission amortisation will help; if WACC dominates →
        # shorter mission duration is the lever.  Shows breakdown for viable
        # missions when there are any, else for all evaluated rows so the user
        # can still diagnose what would need to change to become profitable.
        cost_cols = [c for c in catalog.columns if c.endswith("_cost_usd")]
        viable_df = catalog[catalog["viable"]]
        diag_df, label = (viable_df, "viable missions") if not viable_df.empty else (catalog, "ALL evaluated (no viable mission yet — try cheaper hardware / multi-mission NRE / Starship)")
        print(f"\n{'='*95}")
        print(f"    AVERAGE COST BREAKDOWN  ({label}, USD)")
        print(f"{'='*95}")
        if cost_cols and not diag_df.empty:
            means = diag_df[cost_cols].mean().sort_values(ascending=False)
            bar_scale = means.max() / 50 if means.max() > 0 else 1
            for col, val in means.items():
                bar = "█" * max(1, int(val / bar_scale))
                cat = col.replace("_cost_usd", "").replace("_", " ")
                print(f"  {cat:25s} {bar:<52s}  ${val:>15,.0f}")
