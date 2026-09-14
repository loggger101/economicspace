# -*- coding: utf-8 -*-
"""The worked-calculation document for the campaign's BEST cell, re-derived.

`~/Documents/<body>_calculation.pdf` is a 20-page derivation of one cell: every
equation, substitution and result behind the campaign's lowest cost/revenue
ratio, in the order the model evaluates them.  This builds it.

WHY IT IS A SCRIPT AND NOT A DOCUMENT.  The first one was written by hand, for
2014 WE121 at 9.5435x, and it was stale nine hours later: it was compiled on
2026-09-10 against a campaign still in flight, and the beneficiated cislunar
cell finished on 09-11 at 6.6622x on a different body.  A hand-typed document
cannot survive that, and this repo already knows why -- a number spelled out in
prose is a number waiting to rot.  So every figure the document prints is
DERIVED here and none is typed, and the two searches that pick the cell are run
rather than quoted.

WHAT "INDEPENDENT" MEANS, precisely, because the document's footer claims it.
The chain below is written out from the equations rather than called: the
patched-conic transfer, the tankage closure, the mass cascade and its fixed
point, the electric stage, the eclipse-derated plant, the payload knapsack, the
clock, the capacity ceilings, the reliability product and the whole cost
cascade.  What it DOES read from `master` is reference data and table
accessors, never a solver: the config, `_ops_value`, `RARE_METAL_ELEMENTS`,
`_PHASE_MARKET_ALIAS` and the catalog loaders.  Nothing here calls
`max_return_payload_kg`, `_evaluate_combo_at_ratio`, `evaluate_combo`,
`optimal_payload_mix`, `mission_cost_usd` or the programme ladder.

That is what makes the check at the end worth running: two statements of one
model, compared column by column.  `--verify` runs it and prints nothing else.

THE SHAPE IS PINNED AND THE PROSE IS PINNED, DELIBERATELY.  The document
explains a beneficiated, propulsively-returned, solar-powered, electric mission
to a body whose value is mostly water, and its sentences say so.  The numbers
would follow any cell; the prose would not.  So `main()` refuses when the
ledger's best cell is not the pinned one, names both, and says what to do.  A
document that quietly describes the wrong body is the failure this file exists
to prevent, and a silent success is worse than a red check.

    py campaign/worked_calculation.py            # derive, check, write the HTML
    py campaign/worked_calculation.py --pdf      # and render it with Chrome
    py campaign/worked_calculation.py --verify   # derive and check, write nothing
    py campaign/worked_calculation.py --cell X   # a named cell, guard bypassed
"""
import argparse
import csv
import gzip
import json
import math
import os
import subprocess
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMP = os.path.join(ROOT, "campaign")
LEDGER = os.path.join(CAMP, "results.csv")
sys.path.insert(0, ROOT)

# The cell the prose describes.  See the module docstring for why this is
# pinned rather than followed.
PINNED_CELL = "cislunar__benef__search-on"
PINNED_BODY = "2021 CX5"

# Physics the model fixes at import; restated here rather than imported so the
# derivation owns its own constants.
G0 = 9.80665
V_EARTH = 29.784
MU_EARTH = 398_600.4418
R_LEO = 6_378.14 + 200.0
R_MOON = 384_400.0
DV_NRHO = 0.450
HOURS_PER_YR = 365.25 * 24.0


def ledger_rows():
    """Every completed cell in `campaign/results.csv`, as dicts."""
    with open(LEDGER, newline="", encoding="utf-8") as fh:
        return [r for r in csv.DictReader(fh) if r.get("rc") == "0"]


def best_cell(rows):
    """The ledger row with the lowest objective, which is the campaign's best."""
    done = [r for r in rows if r.get("best_obj")]
    if not done:
        sys.exit("no completed cells in %s" % LEDGER)
    return min(done, key=lambda r: float(r["best_obj"]))


def archived_winner(cell, designation):
    """The winner's full row out of a gzipped cell archive.

    Streamed and matched on the raw line, because the archive is 350-500 MB
    compressed and is NOT sorted by the objective: the first row of
    `cislunar__benef__search-on` scores 1,266x.  Reading it with pandas costs
    several GB to answer one question about one row.
    """
    path = os.path.join(CAMP, "cells", "%s.csv.gz" % cell)
    if not os.path.exists(path):
        sys.exit("missing cell archive: %s\n"
                 "campaign/cells/ is gitignored; re-run the cell or copy it in."
                 % path)
    needle = "%s," % designation
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        header = fh.readline()
        hits = [line for line in fh if needle in line]
    frame = pd.read_csv(_lines(header, hits), float_precision="round_trip")
    frame = frame[frame["designation"] == designation]
    if len(frame) != 1:
        sys.exit("expected one row for %s in %s, found %d"
                 % (designation, cell, len(frame)))
    return frame.iloc[0]


def catalog_body(designation):
    """The Stage 1 catalog row for one body, streamed out of the 862 MB CSV."""
    path = os.path.join(ROOT, "asteroid_pipeline", "asteroid_catalog.csv")
    if not os.path.exists(path):
        sys.exit("missing %s; run_pipeline.py --check-inputs explains this" % path)
    needle = "%s," % designation
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        header = fh.readline()
        hits = [line for line in fh if needle in line]
    frame = pd.read_csv(_lines(header, hits), low_memory=False,
                        float_precision="round_trip")
    frame = frame[frame["designation"] == designation]
    if len(frame) != 1:
        sys.exit("expected one catalog row for %s, found %d"
                 % (designation, len(frame)))
    return frame.iloc[0]


def _lines(header, rows):
    """A file-like over a header plus some matched lines, for `read_csv`."""
    import io
    return io.StringIO(header + "".join(rows))


def reference_tables():
    """Module 2's mineral catalog and Module 3's four tables, as loaded.

    Read through `master`'s own loader so the dtypes and the list-column
    parsing are the pipeline's, not a second opinion about them.
    """
    import master
    cfg = master.CALC_CONFIG
    cfg.input_dir = os.path.join(ROOT, "asteroid_pipeline")
    tdir = os.path.join(cfg.input_dir, cfg.transportation_subdir)
    return {
        "minerals": master._load_csv(
            os.path.join(cfg.input_dir, cfg.mineral_catalog_file), "M2"),
        "vehicles": master._load_csv(
            os.path.join(tdir, cfg.launch_vehicles_file), "M3 vehicles"),
        "propellants": master._load_csv(
            os.path.join(tdir, cfg.propellants_file), "M3 propellants"),
        "ops": master._load_csv(
            os.path.join(tdir, cfg.operational_costs_file), "M3 ops"),
    }


# ----------------------------------------------------------------- pricing
def phase_table(body, minerals):
    """[(phase, mass fraction, $/kg)] for one body, derived from Module 2.

    The four taxonomy fractions priced separately rather than blended, plus the
    residual.  Module 1's fractions sum to 0.76-0.96 and the remainder is
    undifferentiated rock, valued at the silicate quote and drawing the silicate
    ceiling; pricing it as silicates and bounding it as something else is the
    defect calc v1.21.2 closed.

    `nickel-iron` is the one phase whose price is not a row lookup: it is an
    alloy, so it is the yield-weighted sum of its elements with the body's own
    PGM enrichment on the rare metals.
    """
    import master
    price = dict(zip(minerals["name"], minerals["price_usd_per_kg"]))
    kappa = float(body.get("comp_pgm_enrichment") or 1.0)
    yields = {}
    row = minerals[minerals["name"] == "nickel-iron"]
    if len(row):
        raw = row.iloc[0].get("yields_json")
        if isinstance(raw, str) and raw.strip():
            yields = json.loads(raw)

    alloy = 0.0
    for element, fraction in yields.items():
        if element not in price:
            continue
        share = float(fraction)
        if element in master.RARE_METAL_ELEMENTS:
            share *= kappa
        alloy += share * float(price[element])

    phases, total = [], 0.0
    for column, mineral in master.FRACTION_TO_MINERAL.items():
        frac = body.get(column)
        if frac is None or pd.isna(frac) or float(frac) <= 0:
            continue
        value = alloy if mineral == "nickel-iron" else float(price[mineral])
        phases.append((mineral, float(frac), value))
        total += float(frac)
    if 0.0 < total < 1.0:
        phases.append((master._RESIDUAL_PHASE, 1.0 - total,
                       float(price["silicates"])))
    return phases, alloy, yields


def market_ceilings(minerals):
    """{phase: (market key, kg/yr)}, with the residual pooled onto silicates."""
    import master
    caps = dict(zip(minerals["name"], minerals["annual_market_kg"]))
    return caps, dict(master._PHASE_MARKET_ALIAS)


def knapsack(payload_kg, feed_kg, phases, recovery, caps=None, keys=None):
    """The most valuable hold assemblable from this feed.

    A greedy fractional knapsack in descending price order, which is exact here
    because the phases are divisible and priced per kg.  Both honest bounds fall
    out of it rather than being imposed: you cannot load more of a phase than
    the processed feed contained, and once the hold is pure best-phase there is
    nothing better to add.

    `caps` is keyed by MARKET and is consumed as it is spent, so two phases
    selling into one market share one allowance.  Clipping the take and not the
    remaining hold is the whole point of the bounded form: the space a capped
    phase does not get stays available to the next one down.
    """
    remaining, total, mix = float(payload_kg), 0.0, {}
    for name, frac, price in sorted(phases, key=lambda p: -p[2]):
        if remaining <= 0:
            break
        take = min(float(feed_kg) * frac * recovery, remaining)
        if caps is not None:
            key = (keys or {}).get(name, name)
            allowance = caps.get(key)
            if allowance is not None:
                take = min(take, allowance)
                caps[key] = allowance - take
        if take <= 0:
            continue
        mix[name] = take
        total += take * price
        remaining -= take
    loaded = float(payload_kg) - remaining
    return {"mix": mix, "value": total, "loaded": loaded,
            "usd_per_kg": total / loaded if loaded > 0 else 0.0}


# ------------------------------------------------------------------ context
def context(body, archived, tables):
    """Everything about this body and architecture that no search varies.

    The searched CHOICES arrive from the archived row -- vehicle, propellant,
    rendezvous apsis, return mode, propellant sourcing, power source -- because
    the document explains the arithmetic GIVEN the architecture the search
    picked, and shows the two searches that picked it in section 9.  Everything
    those choices imply is derived here.
    """
    import master
    ops = tables["ops"]
    veh = tables["vehicles"]
    veh = veh[veh["name"] == archived["vehicle"]].iloc[0]
    pro = tables["propellants"]
    pro = pro[pro["name"] == archived["propellant"]].iloc[0]

    shape = dict(beneficiated=bool(archived["beneficiation"]),
                 aero=bool(archived["aerocapture_return"]),
                 isru=bool(archived["isru_return"]),
                 power=str(archived["power_source"]),
                 apsis=str(archived["rendezvous_apsis"]),
                 electric=float(archived["dv_penalty_factor"]) > 1.0)
    expected = dict(beneficiated=True, aero=False, isru=False, power="solar",
                    apsis="aphelion", electric=True)
    if shape != expected:
        sys.exit("this derivation covers one mission shape and the archived row "
                 "is a different one.\n  expected %s\n  archived %s\n"
                 "Extend the cascade before pointing the document at it."
                 % (expected, shape))

    cfg = master.CALC_CONFIG
    rows = set(ops["category"])

    def val(item):
        """One Module 3 row, or a failure.

        `_ops_value` falls back to a default when the row is absent, which is
        silent and flattering: a renamed row would leave this document quietly
        computing on a constant the tables no longer hold.  A name that does
        not resolve is a finding, so it raises.
        """
        if item not in rows:
            sys.exit("Module 3 has no row named %r; the ops table was renamed "
                     "underneath this derivation." % item)
        return master._ops_value(ops, item, default=float("nan"))

    a_au = float(body["semi_major_axis_au"])

    # Eclipse-derated specific power for the plant that stands on the body, and
    # the bare 1/r^2 figure for the array that never leaves sunlight.
    w_bare = val("Power system specific mass") / (a_au * a_au)
    rot_h = body.get("rotation_period_h")
    rot_h = (float(rot_h) if rot_h is not None and not pd.isna(rot_h)
             else cfg.default_rotation_period_h)
    dark_h = min(rot_h / 2.0, cfg.max_dark_period_h)
    w_plant, oversize = master.eclipse_effective_w_per_kg(
        w_bare, dark_h, val("Eclipse / night-side dark fraction"),
        val("Energy storage usable specific energy"),
        val("Energy storage round-trip efficiency"),
        val("Power-system row baseline dark period"))

    tank_frac = (float(pro["tank_kg_per_L"]) / float(pro["density_kg_per_L"])
                 if cfg.model_tank_mass else 0.0)
    # The launch cost avoided, which is where an in-space price comes from.
    # Read as the leg chain rather than as one number so the document can show
    # the stage that produces it; one `burn` leg for a cislunar depot.
    legs = master._DELIVERY_LEGS.get(cfg.delivery_destination) or []
    return dict(
        cfg=cfg, body=body, veh=veh, pro=pro, ops=ops, val=val,
        minerals=tables["minerals"], legs=legs,
        leo_usd_per_kg=master._LEO_USD_PER_KG,
        p_l=master.delivered_cost_usd_per_kg(cfg.delivery_destination),
        a_au=a_au, e=float(body["eccentricity"]),
        inc=float(body["inclination_deg"]),
        rho=float(body["density_gcm3"]),
        H=float(body["absolute_magnitude_h"]),
        albedo=float(body["albedo_assumed_for_diameter"]),
        isp=float(pro["isp_vac_s"]),
        ve=float(pro["isp_vac_s"]) * G0,
        dv_penalty=float(pro["dv_penalty_factor"]),
        tank_frac=tank_frac,
        leo_cap=float(veh["payload_leo_kg"]),
        fairing_m3=float(veh["fairing_volume_m3"]),
        thruster_eff=float(pro["thruster_efficiency"]),
        thruster_kg_per_n=float(pro["thruster_kg_per_n"]),
        ppu_kg_per_kw=val("Power processing unit specific mass"),
        w_bare=w_bare, w_plant=w_plant, oversize=oversize, dark_h=dark_h,
        rot_h=rot_h,
        dig_wh=val("Drilling / excavation energy"),
        benef_wh=val("Beneficiation / on-site processing energy"),
        water_wh=val("Water liberation energy (bound water)"),
        contain_per_kg=val("Volatile cargo containment"),
        recovery=cfg.beneficiation_recovery,
        rate_kg_yr=cfg.mining_hardware_kg
        * cfg.mining_rate_kg_per_day_per_kg_rig * 365.25,
    )


def derive_body(C):
    """Diameter from H and albedo, then the mass of a sphere of that size."""
    d_km = 1329.0 / math.sqrt(C["albedo"]) * 10.0 ** (-C["H"] / 5.0)
    r_m = d_km / 2.0 * 1000.0
    vol = 4.0 / 3.0 * math.pi * r_m ** 3
    mass = C["rho"] * 1000.0 * vol
    return dict(d_km=d_km, r_m=r_m, r3=r_m ** 3, vol=vol, mass=mass,
                mineable=C["cfg"].max_mining_fraction * mass)


def _legs(C, r_target):
    """Departure and cislunar-capture legs for a rendezvous at one apsis."""
    a_t = (1.0 + r_target) / 2.0
    v_t = math.sqrt(2.0 - 1.0 / a_t)
    cos_i = math.cos(math.radians(C["inc"]))
    v_inf_sq = v_t ** 2 + 1.0 - 2.0 * v_t * cos_i
    v_inf = math.sqrt(max(v_inf_sq, 0.0)) * V_EARTH
    v_leo = math.sqrt(MU_EARTH / R_LEO)
    v_esc = math.sqrt(2.0) * v_leo
    v_hyp = math.sqrt(v_esc ** 2 + v_inf ** 2)
    a_ell = (R_LEO + R_MOON) / 2.0
    v_ell = math.sqrt(MU_EARTH * (2.0 / R_LEO - 1.0 / a_ell))
    match = abs(math.sqrt(2.0 / r_target - 1.0 / C["a_au"])
                - math.sqrt(2.0 / r_target - 1.0 / a_t)) * V_EARTH
    return dict(a_t=a_t, v_t=v_t, cos_i=cos_i, v_inf_sq=v_inf_sq,
                v_inf_canon=math.sqrt(max(v_inf_sq, 0.0)), v_inf=v_inf,
                v_leo=v_leo, v_esc=v_esc, v_hyp=v_hyp, a_ell=a_ell,
                v_ell=v_ell, v_ast=math.sqrt(2.0 / r_target - 1.0 / C["a_au"]),
                v_tr=math.sqrt(2.0 / r_target - 1.0 / a_t),
                match=match, depart=v_hyp - v_leo,
                out=v_hyp - v_leo + match,
                cap=max(0.0, v_hyp - v_ell) + DV_NRHO,
                ret=match + max(0.0, v_hyp - v_ell) + DV_NRHO)


def derive_dv(C):
    """Two-impulse patched conic at both apsides; the cheaper round trip wins."""
    q_au = C["a_au"] * (1.0 - C["e"])
    big_q = C["a_au"] * (1.0 + C["e"])
    aph, peri = _legs(C, big_q), _legs(C, q_au)
    lam = C["dv_penalty"]
    return dict(q_au=q_au, Q_au=big_q, aph=aph, peri=peri,
                aph_round=aph["out"] + aph["ret"],
                peri_round=peri["out"] + peri["ret"],
                dv_out=lam * aph["out"] * 1000.0,
                dv_ret=lam * aph["ret"] * 1000.0)


# ------------------------------------------------------- the mass cascade
def _cascade(C, R, hardware_kg, struct_frac):
    """The closed-form payload solve, at one hardware mass and one f.

    Working backward from arrival, with the return tank inside the post-burn
    mass and the outbound tank staged at the asteroid.  k = 1/(1 - t(R - 1)) is
    the cost of carrying your own tank, and k growing without bound is the tank
    failing to close, which is infeasible rather than merely expensive.
    """
    t, k_ret, k_out = R["t"], R["k_ret"], R["k_out"]
    d0 = C["cfg"].return_vehicle_dry_kg
    denom = k_ret * R["R_ret"] * (1.0 + struct_frac) - 1.0
    bracket = R["budget"] - hardware_kg - k_ret * d0 * R["R_ret"]
    if denom <= 0 or bracket <= 0:
        return None
    m_pay = bracket / denom
    m_after = k_ret * (m_pay * (1.0 + struct_frac) + d0)
    m_rprop = m_after * (R["R_ret"] - 1.0)
    m_at = hardware_kg + d0 + struct_frac * m_pay + t * m_rprop + m_rprop
    m_oprop = m_at * k_out * (R["R_out"] - 1.0)
    return dict(m_pay=m_pay, denom=denom, bracket=bracket, m_after=m_after,
                m_rprop=m_rprop, m_at=m_at, m_oprop=m_oprop,
                m_prop=m_oprop + m_rprop)


def _ep_stage(C, m_prop):
    """Array, PPU and thruster for a stage that burns `m_prop` in t_burn.

    Three masses on two different quantities.  The array and the PPU scale with
    POWER; the thruster scales with THRUST, which owes nothing to efficiency,
    and that is the constraint a per-kW figure cannot express.
    """
    seconds = C["cfg"].ep_target_thrust_yr * 365.25 * 24.0 * 3600.0
    power = m_prop * C["ve"] ** 2 / (2.0 * C["thruster_eff"] * seconds)
    thrust = m_prop * C["ve"] / seconds
    array = power / C["w_bare"]
    ppu = power / 1000.0 * C["ppu_kg_per_kw"]
    thruster = thrust * C["thruster_kg_per_n"]
    return dict(power=power, thrust=thrust, array=array, ppu=ppu,
                thruster=thruster, mass=array + ppu + thruster)


def mass_and_clock(C, B, DV, ratio):
    """The coupled sizing loop, then the mission actually flown.

    Seven quantities in one ring: payload sets the feed, the feed sets the dig
    and the power, the power sets the array, the array is hardware, and hardware
    comes out of the payload; and separately the payload sets the water in the
    hold, which sets the sealed containment, which is payload-proportional and
    so folds into f.  Fixed-point iteration solves it.

    TWO THINGS THE MODEL DOES THAT LOOK LIKE OVERSIGHTS AND ARE NOT, and both
    have to be reproduced or the launch mass comes out over the vehicle.  The
    cascade is NOT re-solved once the loop converges: the payload carried
    forward is the last one solved INSIDE the loop, at the previous pass's
    hardware.  And the electric stage is never re-sized after that either, so it
    is sized on a propellant load a couple of kilograms above the one the
    settled stack flies.  Only the plant and the containment are settled.
    """
    cfg = C["cfg"]
    t = C["tank_frac"]
    R = {"t": t,
         "R_out": math.exp(DV["dv_out"] / C["ve"]),
         "R_ret": math.exp(DV["dv_ret"] / C["ve"])}
    if t * (R["R_ret"] - 1.0) >= 1.0 or t * (R["R_out"] - 1.0) >= 1.0:
        return None
    R["k_out"] = 1.0 / (1.0 - t * (R["R_out"] - 1.0))
    R["k_ret"] = 1.0 / (1.0 - t * (R["R_ret"] - 1.0))
    R["budget"] = C["leo_cap"] / (R["k_out"] * R["R_out"])

    throughput = C["rate_kg_yr"] * cfg.max_mining_duration_yr
    phases = C["phases"]
    plant_kg = ep_kg = 0.0
    struct = cfg.return_structure_frac_of_payload
    passes, cas, ep = [], None, None

    for i in range(12):
        hw_in = cfg.mining_hardware_kg + plant_kg + ep_kg
        cas = _cascade(C, R, hw_in, struct)
        if cas is None:
            return None
        ep = _ep_stage(C, cas["m_prop"])
        trial_pay = min(cas["m_pay"], B["mineable"], throughput)
        if trial_pay <= 0:
            return None
        trial_feed = min(trial_pay * ratio, throughput, B["mineable"])
        trial_dig = max(trial_feed / C["rate_kg_yr"], cfg.station_keeping_floor_yr)
        water = knapsack(trial_pay, trial_feed, phases,
                         C["recovery"])["mix"].get("water", 0.0)
        draw = ((C["dig_wh"] * trial_feed + C["benef_wh"] * trial_pay
                 + C["water_wh"] * water) / (trial_dig * HOURS_PER_YR))
        new_plant = draw / C["w_plant"]
        new_frac = C["contain_per_kg"] * min(1.0, water / trial_pay)
        passes.append({"n": i + 1, "hw_in": hw_in, "f_used": struct,
                       "m_pay": cas["m_pay"], "ep": ep["mass"],
                       "plant": new_plant, "feed": trial_feed,
                       "dig": trial_dig, "water": water, "c_frac": new_frac})
        held = struct - cfg.return_structure_frac_of_payload
        settled = (abs(new_plant - plant_kg) <= 0.01 * max(new_plant, 1.0)
                   and abs(ep["mass"] - ep_kg) <= 0.01 * max(ep["mass"], 1.0)
                   and abs(new_frac - held) <= 1e-4)
        plant_kg, ep_kg = new_plant, ep["mass"]
        struct = cfg.return_structure_frac_of_payload + new_frac
        if settled:
            break

    # The mission actually flown: the loop's payload, capped by volume, with the
    # plant and the seal re-settled on it and the stack rebuilt underneath.
    vol_cap = 0.25 * C["fairing_m3"] * 1000.0 * C["rho"]
    m_pay = min(min(cas["m_pay"], B["mineable"]), vol_cap)
    feed = max(min(m_pay * ratio, throughput, B["mineable"]), m_pay)
    load = knapsack(m_pay, feed, phases, C["recovery"])
    water = load["mix"].get("water", 0.0)
    c_frac = C["contain_per_kg"] * min(1.0, water / m_pay)
    f_eff = cfg.return_structure_frac_of_payload + c_frac
    dig_yr = feed / C["rate_kg_yr"]
    draw = ((C["dig_wh"] * feed + C["benef_wh"] * m_pay + C["water_wh"] * water)
            / (dig_yr * HOURS_PER_YR))
    plant_kg = draw / C["w_plant"]
    hw = cfg.mining_hardware_kg + plant_kg + ep["mass"]

    d0 = cfg.return_vehicle_dry_kg
    m_dry = d0 + f_eff * m_pay
    m_after = R["k_ret"] * (m_pay * (1.0 + f_eff) + d0)
    m_rprop = m_after * (R["R_ret"] - 1.0)
    m_tank_ret = t * m_rprop
    m_at = hw + m_dry + m_tank_ret + m_rprop
    m_oprop = m_at * R["k_out"] * (R["R_out"] - 1.0)
    m_tank_out = t * m_oprop
    m_launch = m_at + m_tank_out + m_oprop
    if m_launch > C["leo_cap"]:
        return None

    stay = dig_yr + DV["window_wait"]
    t_out = max(0.5, 0.00023 * DV["dv_out"])
    t_back = max(0.5, 0.00023 * DV["dv_ret"])
    chem = t_out + stay + t_back
    electric = cfg.ep_target_thrust_yr + stay
    duration = max(1.0, chem, electric)
    if duration > cfg.max_mission_duration_yr:
        return None
    cadence = max(stay, DV["synodic"])
    calendar_cap = max(1, int(C["val"]("Mining rig service life") // stay))
    trips = min(calendar_cap, int(C["val"]("Mining rig maximum trips")))
    return {"R": R, "passes": passes, "cascade": cas, "ep": ep,
            "throughput": throughput, "vol_cap": vol_cap, "m_pay": m_pay,
            "feed": feed, "ratio": feed / m_pay, "load": load, "water": water,
            "c_frac": c_frac, "f_eff": f_eff, "m_containment": c_frac * m_pay,
            "plant": plant_kg, "draw": draw, "hw": hw, "m_dry": m_dry,
            "m_after": m_after, "m_rprop": m_rprop, "m_tank_ret": m_tank_ret,
            "m_at": m_at, "m_oprop": m_oprop, "m_tank_out": m_tank_out,
            "m_launch": m_launch, "ret_vol": m_pay / C["rho"] / 1000.0,
            "dig_yr": dig_yr, "stay": stay, "chem_fit": chem,
            "electric_floor": electric, "duration": duration,
            "cadence": cadence, "calendar_cap": calendar_cap, "trips": trips,
            "t_out": t_out, "t_back": t_back}


# --------------------------------------------------------- periods and money
def derive_periods(C):
    """Orbital period, synodic period and the expected wait for a window.

    The counterintuitive part is worth restating where it is computed: a
    synodic period runs away as the body's period approaches the
    destination's, so a near-Earth body has windows YEARS apart while a
    main-belt one comes round every year and a half.  Accessibility in
    delta-v and accessibility in TIME pull against each other.
    """
    import master
    a_dest = master.window_phasing_au(C["cfg"].delivery_destination)
    t_ast = C["a_au"] ** 1.5
    synodic = master.synodic_period_yr(C["a_au"], a_dest)
    return {"t_ast": t_ast, "a_dest": a_dest, "synodic": synodic,
            "window_wait": 0.5 * synodic if C["cfg"].model_launch_windows else 0.0}


def revenue(C, M, n_missions, fleet):
    """What one delivery of an N-mission programme actually sells.

    Constant prices and a bounded quantity: every kilogram inside a
    commodity's ceiling fetches the catalog quote and every kilogram past it
    fetches nothing, so no price moves and `saturation_multiplier` stays 1.0.

    The window is the point.  A bigger fleet delivers more often, so each
    delivery gets a shorter slice of the market's annual capacity, and past the
    point where the ceilings bite another ship adds its whole cost and only
    part of its revenue.  That is what turns the programme ladder over instead
    of letting it run to the fleet cap.

    A CONCENTRATED load can be reshaped and a raw one cannot, which is why the
    ceilings go INTO the knapsack rather than clipping its answer: a hold that
    caps out on carbon re-fills the freed space with the next phase down the
    price order instead of flying the excess unsold.
    """
    window = ((M["duration"] + (n_missions - 1) * (M["cadence"] / fleet))
              / n_missions)
    caps, keys = {}, {}
    for name, _frac, _price in C["phases"]:
        key = C["market_keys"].get(name, name)
        keys[name] = key
        caps.setdefault(key, C["market_kg"].get(key, float("inf")) * window)
    capped = knapsack(M["m_pay"], M["feed"], C["phases"], C["recovery"],
                      caps=dict(caps), keys=keys)
    free = M["load"]
    return {"window": window, "allow": caps, "capped": capped,
            "gross_base": free["value"],
            "clearing": capped["value"] / free["value"] if free["value"] else 1.0,
            "unsold": max(0.0, free["loaded"] - capped["loaded"]),
            "delivered": capped["value"] / M["m_pay"] if M["m_pay"] else 0.0}


def reliability(C, M, n_missions):
    """Launch, cruise and mining, multiplied; costs are charged in full anyway.

    Only the mining term grows with the programme.  Launch vehicles are already
    mature and MTBF is a duration exposure rather than a heritage question, so
    neither of those learns.
    """
    val = C["val"]
    p_launch = val("Launch vehicle reliability")
    mtbf = val("Spacecraft mean time between failures")
    q1 = 1.0 - val("Mining system first-of-kind success probability")
    alpha = val("Mining reliability growth exponent")
    q_max = val("Mining system mature success probability")
    p_cruise = math.exp(-M["duration"] / mtbf) if mtbf > 0 else 1.0
    terms = [1.0 - max(q1 * k ** -alpha, 1.0 - q_max)
             for k in range(1, n_missions + 1)]
    p_mining = sum(terms) / n_missions
    return {"p_launch": p_launch, "p_cruise": p_cruise, "mtbf": mtbf,
            "p_mining": p_mining, "terms": terms,
            "p_succ": max(0.0, min(1.0, p_launch * p_cruise * p_mining))}


def cost(C, M, n_missions, per_ship):
    """The whole cost cascade for one mission of an N-mission programme.

    Four buckets and three multipliers.  Up-front money is compounded forward
    to the point of sale over the mission; ongoing money over half of it;
    end-of-mission money not at all, because it is paid there.

    The fourth term is the one a single mission never sees.  W campaigns on one
    rig are strictly sequential, so the three articles bought once at t = 0 and
    amortised across all of them are carried for the whole programme span, not
    for one mission duration.  It is written as a delta on top of the
    single-mission sum rather than as a rebuilt one, which is how the model
    keeps a W = 1 run bit-identical to the release before the term existed.
    """
    cfg, val = C["cfg"], C["val"]
    lc = sum(k ** math.log(cfg.learning_curve_rate, 2)
             for k in range(1, n_missions + 1)) / n_missions
    rig_total = cfg.mining_hardware_kg * val("Mining payload recurring cost")
    share = max(1, min(per_ship, M["trips"]))
    used = min(1.0, max(share * M["stay"] / val("Mining rig service life"),
                        share / M["trips"]))
    terminal = (rig_total * (1.0 - used) * val("Rig salvage fraction")
                if n_missions > 1 else 0.0)
    rig_share = (rig_total - terminal) / share

    prop_cost = float(C["pro"]["cost_usd_per_kg"])
    lines = {
        "launch": M["m_launch"] * float(C["veh"]["usd_per_kg_to_leo"]),
        "oprop": M["m_oprop"] * prop_cost,
        "rprop": M["m_rprop"] * prop_cost,
        "rig": rig_share,
        "capsule": M["m_dry"] * val("Berthing adapter recurring cost") * lc,
        "plant": M["draw"] * val("Power system (solar + battery)") * lc,
        "ep": (M["ep"]["power"] * val("Power system (solar + battery)")
               + M["ep"]["power"] / 1000.0
               * val("Electric propulsion system recurring cost")) * lc,
        "tank": ((M["m_tank_ret"] + M["m_tank_out"])
                 * val("Propellant tank recurring cost") * lc),
    }
    hardware = (lines["rig"] + lines["capsule"] + lines["plant"]
                + lines["ep"] + lines["tank"])
    ops = M["duration"] * val("Mission operations")
    nre = (val("Spacecraft development (NRE)")
           * (1.0 - cfg.nre_recurring_overlap_fraction) / n_missions)
    autonomy = val("Autonomous mining control & AI (NRE)") / n_missions
    licensing = val("FAA Part 450 licensing (launch only)")
    handover = val("Depot berthing & handover operations")

    upfront_lines = (lines["launch"] + lines["oprop"] + hardware + 0.0
                     + licensing + 0.0 + 0.0 + nre + autonomy + lines["rprop"])
    cont = 1.0 + cfg.contingency_fraction
    wacc = val("Cost of capital (WACC)")
    mult_up = (1.0 + wacc) ** M["duration"]
    mult_on = (1.0 + wacc) ** (M["duration"] / 2.0)
    upfront = upfront_lines * cont
    ongoing = ops * cont
    end = handover * cont
    total = upfront * mult_up + ongoing * mult_on + end

    y = (1.0 + wacc) ** M["cadence"]
    cal_cost = cal_credit = 1.0
    if cfg.model_programme_calendar and share > 1 and y > 1.0:
        cal_cost = (y ** share - 1.0) / ((y - 1.0) * share)
        cal_credit = (1.0 - y ** -share) / ((1.0 - 1.0 / y) * share)
    delta = 0.0
    if cal_cost != 1.0 or cal_credit != 1.0:
        programme_upfront = nre + autonomy + rig_total / share
        delta = ((programme_upfront * (cal_cost - 1.0)
                  - (terminal / share) * (cal_credit - 1.0)) * cont * mult_up)
    return {"lc": lc, "lines": lines, "hardware": hardware, "ops": ops,
            "nre": nre, "autonomy": autonomy, "licensing": licensing,
            "handover": handover, "rig_total": rig_total, "used": used,
            "terminal": terminal, "rig_gross_share": rig_total / share,
            "rig_credit_share": terminal / share, "share": share,
            "upfront_lines": upfront_lines, "upfront": upfront,
            "ongoing": ongoing, "end": end, "wacc": wacc,
            "mult_up": mult_up, "mult_on": mult_on, "y": y,
            "cal_cost": cal_cost, "cal_credit": cal_credit,
            "programme_upfront": nre + autonomy + rig_total / share,
            "delta": delta, "total": total + delta,
            "contingency": cfg.contingency_fraction
            * (upfront_lines + ops + handover),
            "span": M["duration"] + max(0, share - 1) * M["cadence"]}


def price_programme(C, M, n_missions, fleet, per_ship):
    """Revenue, reliability, cost and the objective at one rung of the ladder."""
    rev = revenue(C, M, n_missions, fleet)
    rel = reliability(C, M, n_missions)
    cst = cost(C, M, n_missions, per_ship)
    expected = rev["capped"]["value"] * rel["p_succ"]
    return {"n": n_missions, "f": fleet, "w": per_ship, "rev": rev, "rel": rel,
            "cost": cst, "expected": expected,
            "obj": cst["total"] / expected if expected > 0 else float("inf")}


# ------------------------------------------------------------- the searches
def programme_ladder(C, M):
    """Every (N, F, W) the search prices, and the objective at each.

    The LADDER'S SHAPE is read from `master` and its VALUES are derived here.
    That split is deliberate: which programmes get priced is the search's
    structure, and reproducing it by hand would be a second opinion about what
    the search proposed rather than a check on what it concluded.

    F is a geometric ladder refined once around the winner; W is enumerated
    exhaustively, because it runs 1..trips and trips is at most five.  A
    dimension small enough to enumerate should be enumerated rather than
    argued about.
    """
    import master
    rig = (M["trips"], M["calendar_cap"],
           int(C["val"]("Mining rig maximum trips")) or None)
    programmes, fleets = master._programme_ladder_cached(
        rig, C["cfg"], master._market_mode(C["cfg"]))
    coarse = [price_programme(C, M, n, f, w) for n, f, w in programmes]
    best = min(coarse, key=lambda p: p["obj"])
    refine = []
    if len(programmes) > 1:
        for fleet in master._fleet_refinement_cached(best["f"], fleets):
            refine.append(price_programme(C, M, fleet * best["w"], fleet,
                                          best["w"]))
    everything = coarse + refine
    return {"coarse": coarse, "refine": refine, "fleets": fleets,
            "best": min(everything, key=lambda p: p["obj"])}


def concentration_sweep(C, B, DV):
    """How hard to concentrate, priced rather than assumed.

    Digging more feed raises the grade of the load, but the gain SATURATES once
    the hold is pure best-phase while the costs do not: every extra kilogram
    still costs dig time, which compounds through operations and the cost of
    capital, plus processing energy and the array mass to supply it.  So the
    value curve is concave and the cost curve is not, and the optimum is
    usually strictly interior.

    The baseline of not concentrating at all is priced too, which is what makes
    beneficiation an option rather than an obligation.  It is not the same as a
    ratio of 1.0: that would still pay the separation recovery loss and the
    array mass for no grade gain.
    """
    cfg = C["cfg"]
    best_frac = max(C["phases"], key=lambda p: p[2])[1]
    r_max = max(1.0, min(1.0 / (best_frac * C["recovery"]),
                         cfg.max_concentration_ratio))
    steps = max(2, int(cfg.concentration_search_steps))
    rungs = [("coarse", r_max ** (i / (steps - 1))) for i in range(steps)]

    def at(ratio):
        """One point of the sweep: the cascade, then its own best programme."""
        M = mass_and_clock(C, B, DV, ratio)
        if M is None:
            return None
        return {"M": M, "ladder": programme_ladder(C, M)}

    priced = [(kind, r, at(r)) for kind, r in rungs]
    live = [p for p in priced if p[2]]
    if not live:
        sys.exit("no concentration ratio closes a mission on this body")
    best_r = min(live, key=lambda p: p[2]["ladder"]["best"]["obj"])[1]
    step = r_max ** (1.0 / (steps - 1))
    for ratio in (best_r / step ** 0.5, best_r * step ** 0.5):
        if 1.0 <= ratio <= r_max:
            priced.append(("refine", ratio, at(ratio)))
    winner = min((p for p in priced if p[2]),
                 key=lambda p: p[2]["ladder"]["best"]["obj"])
    return {"r_max": r_max, "step": step, "rungs": priced, "winner": winner}


# -------------------------------------------------------------- verification
def check(derived, archived):
    """Every derived quantity against the archived row, column by column.

    The document's footer quotes what this returns, so it is measured on every
    build rather than copied forward.  A pure float comparison is the right
    test here and a tolerance is the wrong one: these are two statements of the
    same arithmetic, so anything past the last bit or two is a finding.
    """
    exact = close = 0
    worst, worst_name, bad = 0.0, "", []
    for name, ours in sorted(derived.items()):
        if name not in archived:
            continue
        theirs = float(archived[name])
        if ours == theirs:
            exact += 1
            continue
        rel = abs(ours - theirs) / max(abs(theirs), 1e-30)
        if rel > worst:
            worst, worst_name = rel, name
        if rel < 1e-12:
            close += 1
        else:
            bad.append((name, ours, theirs, rel))
    return {"n": exact + close + len(bad), "exact": exact, "close": close,
            "bad": bad, "worst": worst, "worst_name": worst_name}


def comparable(C, B, DV, M, P):
    """The derived quantities that have a named column in the archived row."""
    rev, rel, cst = P["rev"], P["rel"], P["cost"]
    return {
        "diameter_km": B["d_km"], "estimated_mass_kg": B["mass"],
        "dv_out_m_s": DV["dv_out"], "dv_ret_m_s": DV["dv_ret"],
        "max_payload_kg": M["m_pay"], "feed_processed_kg": M["feed"],
        "concentration_ratio": M["ratio"], "cargo_water_kg": M["water"],
        "containment_frac": M["c_frac"], "m_containment_kg": M["m_containment"],
        "m_dry_return_kg": M["m_dry"], "m_return_prop_kg": M["m_rprop"],
        "m_tank_return_kg": M["m_tank_ret"], "m_at_asteroid_kg": M["m_at"],
        "m_outbound_prop_kg": M["m_oprop"], "m_tank_outbound_kg": M["m_tank_out"],
        "m_launch_kg": M["m_launch"], "power_system_kg": M["plant"],
        "processing_power_w": M["draw"], "ep_system_kg": M["ep"]["mass"],
        "ep_power_w": M["ep"]["power"], "ep_thrust_n": M["ep"]["thrust"],
        "hardware_total_kg": M["hw"], "mining_duration_yr": M["dig_yr"],
        "return_volume_m3": M["ret_vol"], "tank_mass_frac": C["tank_frac"],
        "synodic_period_yr": DV["synodic"],
        "launch_window_wait_yr": DV["window_wait"],
        "mission_duration_yr": M["duration"],
        "campaign_cadence_yr": M["cadence"],
        "rig_trips_calendar_cap": M["calendar_cap"],
        "trips_per_ship": M["trips"], "programme_missions": P["n"],
        "fleet_ships": P["f"], "missions_per_ship": P["w"],
        "programme_span_yr": cst["span"],
        "market_clearing_fraction": rev["clearing"],
        "unsold_payload_kg": rev["unsold"],
        "delivered_value_usd_per_kg": rev["delivered"],
        "saturation_multiplier": 1.0,
        "p_mining": rel["p_mining"], "p_success": rel["p_succ"],
        "gross_value_usd": P["expected"], "learning_curve_factor": cst["lc"],
        "launch_cost_usd": cst["lines"]["launch"],
        "outbound_prop_cost_usd": cst["lines"]["oprop"],
        "return_prop_cost_usd": cst["lines"]["rprop"],
        "capsule_cost_usd": cst["lines"]["capsule"],
        "power_system_cost_usd": cst["lines"]["plant"],
        "ep_system_cost_usd": cst["lines"]["ep"],
        "tank_cost_usd": cst["lines"]["tank"],
        "hardware_cost_usd": cst["hardware"],
        "mining_rig_cost_usd": cst["lines"]["rig"],
        "rig_terminal_value_usd": cst["terminal"],
        "missions_sharing_rig": cst["share"], "ops_cost_usd": cst["ops"],
        "nre_cost_usd": cst["nre"], "autonomy_nre_cost_usd": cst["autonomy"],
        "licensing_cost_usd": cst["licensing"],
        "recovery_cost_usd": cst["handover"],
        "contingency_cost_usd": cst["contingency"],
        "upfront_cost_usd": cst["upfront"], "ongoing_cost_usd": cst["ongoing"],
        "end_of_mission_cost_usd": cst["end"],
        "wacc_multiplier_upfront": cst["mult_up"],
        "wacc_multiplier_ongoing": cst["mult_on"],
        "programme_calendar_multiplier": cst["cal_cost"],
        "total_cost_usd": cst["total"],
        "bulk_value_usd_per_kg": C["bulk"],
        "best_phase_usd_per_kg": max(p[2] for p in C["phases"]),
    }


# -------------------------------------------------------------------- driver
CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
]


def build(cell, designation):
    """Derive one cell end to end, and check it against its archived row."""
    archived = archived_winner(cell, designation)
    body = catalog_body(designation)
    tables = reference_tables()
    C = context(body, archived, tables)
    phases, alloy, yields = phase_table(body, tables["minerals"])
    caps, alias = market_ceilings(tables["minerals"])
    C["phases"] = phases
    C["alloy"] = alloy
    C["yields"] = yields
    C["bulk"] = sum(f * p for _n, f, p in phases)
    C["market_kg"] = caps
    C["market_keys"] = {n: (n if n in caps else alias.get(n, n))
                        for n, _f, _p in phases}
    B = derive_body(C)
    DV = derive_dv(C)
    DV.update(derive_periods(C))
    sweep = concentration_sweep(C, B, DV)
    _kind, ratio, won = sweep["winner"]
    M, ladder = won["M"], won["ladder"]
    P = ladder["best"]
    result = check(comparable(C, B, DV, M, P), archived)
    return {"C": C, "B": B, "DV": DV, "M": M, "P": P, "ladder": ladder,
            "sweep": sweep, "ratio": ratio, "archived": archived,
            "check": result, "cell": cell, "designation": designation}


def render_pdf(html_path, pdf_path):
    """Print the document with headless Chrome, which is what made the first."""
    exe = next((p for p in CHROME if os.path.exists(p)), None)
    if exe is None:
        print("  no Chrome or Edge found; the HTML is written, print it by hand")
        return False
    subprocess.run([exe, "--headless", "--disable-gpu", "--no-sandbox",
                    "--no-pdf-header-footer",
                    "--print-to-pdf=%s" % pdf_path, html_path],
                   check=True, capture_output=True)
    return os.path.exists(pdf_path)


def main():
    """Find the best cell, derive it, check it, and write the document."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cell", help="a named cell instead of the ledger's best")
    ap.add_argument("--pdf", action="store_true", help="also render the PDF")
    ap.add_argument("--verify", action="store_true",
                    help="derive and check only; write nothing")
    ap.add_argument("--out", default=os.path.join(CAMP, "worked_calculation"),
                    help="output path without an extension")
    args = ap.parse_args()

    rows = ledger_rows()
    top = best_cell(rows)
    cell = args.cell or top["cell"]
    if args.cell is None and cell != PINNED_CELL:
        sys.exit(
            "THE BEST CELL HAS MOVED AND THE PROSE HAS NOT.\n"
            "  ledger best : %s  (%s at %sx)\n"
            "  pinned here : %s  (%s)\n"
            "The arithmetic below would follow the new cell; the sentences "
            "would not.\nRead the new winner, rewrite the prose in "
            "worked_calculation_doc.py, repoint\nPINNED_CELL and PINNED_BODY, "
            "and run again.  Use --cell to derive it meanwhile."
            % (top["cell"], top["winner"], top["best_obj"],
               PINNED_CELL, PINNED_BODY))
    row = next((r for r in rows if r["cell"] == cell), None)
    if row is None:
        sys.exit("no completed ledger row for cell %r" % cell)

    print("  cell      %s" % cell)
    print("  winner    %s (%s) at %sx" % (row["winner"], row["spectral"],
                                          row["best_obj"]))
    out = build(cell, row["winner"])
    c = out["check"]
    print("  derived   %d quantities: %d bit-exact, %d within 1e-12, %d DIFFER"
          % (c["n"], c["exact"], c["close"], len(c["bad"])))
    print("  worst     %.3e relative  (%s)" % (c["worst"], c["worst_name"]))
    for name, ours, theirs, rel in c["bad"]:
        print("     ! %-32s derived %r  archived %r  rel %.3e"
              % (name, ours, theirs, rel))
    if c["bad"]:
        print("\n*** THE DERIVATION AND THE MODEL DISAGREE ***")
        return 1
    if args.verify:
        print("  OK  derivation reproduces the archived row")
        return 0

    import worked_calculation_doc
    html = worked_calculation_doc.document(out)
    html_path = args.out + ".html"
    with open(html_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("  wrote     %s  (%d chars)" % (html_path, len(html)))
    if args.pdf and render_pdf(html_path, args.out + ".pdf"):
        print("  wrote     %s" % (args.out + ".pdf"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
