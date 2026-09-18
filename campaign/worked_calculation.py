# -*- coding: utf-8 -*-
"""The worked-calculation document for the campaign's BEST cell, re-derived.

The document is a derivation of one cell: every equation, substitution and
result behind the best case on disk, in the order the model evaluates them.
This builds it.  ⚠️  A PAGE COUNT IS DELIBERATELY NOT STATED, here or in
`campaign/README.md`.  Both said "20-page" while the document rendered at
twelve, which is this repo's standing failure mode -- a number in prose that
nothing checks -- committed about the file that exists to avoid it.

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
accessors -- the config, `_ops_value`, `RARE_METAL_ELEMENTS`,
`_PHASE_MARKET_ALIAS` and the catalog loaders -- plus ONE deliberate borrowing
that is not data: the SHAPE of the programme ladder.  Nothing here calls
`max_return_payload_kg`, `_evaluate_combo_at_ratio`, `evaluate_combo`,
`optimal_payload_mix` or `mission_cost_usd`.

🚨  AND THIS PARAGRAPH SAID "never a solver ... or the programme ladder"
WHILE `programme_ladder` CALLED `_programme_ladder_cached`, twelve hundred
lines below, under its own docstring explaining why that is deliberate.  One
file disagreed with itself about its own independence, and the document's
FOOTER carried the same denial to every reader.  It also called the model's
night-side derate and its synodic period -- the plant and the clock, two of
the things that sentence NAMES as written out here.  Those two are written out
now; the remedy for the rest is the one this repo prescribes for a number that
nothing checks.  The claim is DERIVED: `BORROWED` is the register,
`model_borrows` walks this file's own AST against it, and the footer prints
what it finds, so a borrowing added tomorrow discloses itself rather than
waiting for somebody to remember a sentence.  `verify_docs.py` check 16 fails
on a borrow that is on no row, and on a row that matches no borrow.

That is what makes the check at the end worth running: two statements of one
model, compared column by column.  `--verify` runs it and prints nothing else.

THE SHAPE IS NO LONGER PINNED, AND THE PROSE IS DERIVED WITH IT.  This
paragraph used to say the opposite, and said it for a release after it stopped
being true: there was a `PINNED` cell constant, `main()` refused any other, and
the document's sentences were written for one beneficiated, propulsively
returned, solar-powered mission to a water-rich body.  Every destination and
every architecture the search can choose derives now -- aerocapture and its
heat shield, ISRU, chemical and electric propulsion, RTG power, raw ore as well
as concentrate -- and the opening sentence NAMES the vehicle, propellant,
return mode, propellant sourcing, power source and rendezvous apsis it found on
the row.  The constant is gone and so is the refusal.

WHAT THE GUARD REFUSES NOW is coverage rather than identity, and it is per
axis rather than one shape tuple, so a refusal names only the axes that
actually fail: an unknown destination, `model_rig_service_life` off (which
stops being a dial and becomes a different programme), a power source that is
neither solar nor RTG, and a fallback delta-v pair, which is not a geometry and
so has no transfer to write out.  A document that quietly describes the wrong
body is still the failure this file exists to prevent; what stops it is now the
derivation reading its terms off the ROW, every one of them with a compared
column behind it, rather than a constant somebody has to remember to move.

    py campaign/worked_calculation.py            # derive, check, write the HTML
    py campaign/worked_calculation.py --pdf      # and render it with Chrome
    py campaign/worked_calculation.py --verify   # derive and check, write nothing
    py campaign/worked_calculation.py --audit    # and audit the page for completeness
    py campaign/worked_calculation.py --cell X   # a named cell, guard bypassed
    py campaign/worked_calculation.py --sweep    # one mission per architecture
"""
import argparse
import csv
import gzip
import json
import math
import os
import re
import subprocess
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMP = os.path.join(ROOT, "campaign")
LEDGER = os.path.join(CAMP, "results.csv")
sys.path.insert(0, ROOT)

# The live catalog a Stage 4 run leaves behind.  This is the DEFAULT source:
# "the best case of the run you just did" is the question this script answers,
# and the campaign archives are the special case rather than the normal one.
CATALOG = os.path.join(ROOT, "asteroid_pipeline", "profitability_catalog.csv")

# Physics the model fixes at import; restated here rather than imported so the
# derivation owns its own constants.
G0 = 9.80665
V_EARTH = 29.784
MU_EARTH = 398_600.4418
R_LEO = 6_378.14 + 200.0
R_MOON = 384_400.0
DV_NRHO = 0.450
# The capsule still has to come down: capture into LEO and then land is not
# the same manoeuvre as capture into LEO and stay there.
DV_LEO_DEORBIT = 0.100
# Periapsis raise that finishes an aerobraked capture.  It is a TRIM, which is
# what separates LEO from GEO below.
DV_AEROBRAKE_TRIM = 0.100
# NRHO down to the lunar surface: 0.730 to LLO, then 1.870 to the ground, and
# all of it propulsive because there is no air.
DV_NRHO_TO_LUNAR_SURFACE = 0.730 + 1.870


# Mass below this is float residue rather than a measurement: see `walled` in
# `terms_in_force`, which is the one inference in this file that turns on it.
# Far above the ~1e-11 kg a cleared load leaves behind, far below any mass the
# model can mean.
UNSOLD_FLOOR_KG = 1e-6


def hours(years):
    """Hours in `years`, associated the way the model associates it.

    🚨  `y * 365.25 * 24.0` IS NOT `y * 8766.0`, AND THE DIFFERENCE IS REAL.
    Float multiplication does not associate: the model writes
    `duration_yr * 365.25 * 24.0`, which rounds twice, and a pre-multiplied
    8766.0 rounds once.  They disagree in the last bit on 28% of the durations
    this model produces, which is enough to move a power draw, an array mass
    and every cost downstream of it off bit-exact and into "agrees to 1e-16".
    That is still agreement, and it is not the standard this project argues
    its releases from.  One rounding is not more accurate than two here; it is
    just a different number, and the one that matters is the model's.
    """
    return (years * 365.25) * 24.0

# ── Geostationary orbit ──────────────────────────────────────────────────────
# Every quantity here belongs to the ORBIT rather than to any candidate, so it
# is resolved once.  An asteroid arrives near the ecliptic and GEO is
# equatorial, so a capture burn there buys 23.44 deg of plane change as well as
# the speed change, and that is the term intuition drops.
R_GEO = 42_164.14
COS_ECLIPTIC_TILT = math.cos(math.radians(23.44))
V_GEO = math.sqrt(MU_EARTH / R_GEO)
V_ESC_GEO = math.sqrt(2.0) * V_GEO
V_LEO_CIRC = math.sqrt(MU_EARTH / R_LEO)
V_ESC_LEO = math.sqrt(2.0) * V_LEO_CIRC
A_GTO = (R_LEO + R_GEO) / 2.0
V_GTO_PERIGEE = math.sqrt(MU_EARTH * (2.0 / R_LEO - 1.0 / A_GTO))
V_GTO_APOGEE = math.sqrt(MU_EARTH * (2.0 / R_GEO - 1.0 / A_GTO))

# ── Mars ─────────────────────────────────────────────────────────────────────
MU_MARS = 42_828.37
R_MARS_PARK = 3_396.2 + 200.0
A_MARS_AU = 1.523_679
# Terminal retropropulsion after an aeroentry, and the powered descent that
# replaces it when there is no atmospheric help.
DV_MARS_RETROPROP = 0.800
DV_MARS_POWERED_DESCENT = 4.100
# The 1-sol staging ellipse, 250 x 33,793 km altitude.  A depot is captured
# into the way NRHO is: the burn only has to BIND the orbit, deep at
# periapsis where Oberth pays, and the apoapsis never comes down.
R_MARS_1SOL_PERI = 3_396.2 + 250.0
R_MARS_1SOL_APO = 3_396.2 + 33_793.0
A_MARS_1SOL = (R_MARS_1SOL_PERI + R_MARS_1SOL_APO) / 2.0
V_ESC_MARS_1SOL = math.sqrt(2.0 * MU_MARS / R_MARS_1SOL_PERI)
V_ELL_MARS_1SOL = math.sqrt(MU_MARS * (2.0 / R_MARS_1SOL_PERI - 1.0 / A_MARS_1SOL))


def circularise_at_geo(v_apogee):
    """One apogee burn that circularises at GEO and takes out the plane change.

    A law of cosines rather than a sum: a burn that changes speed and direction
    at once costs less than doing each separately, and adding them would
    overstate every GEO arrival in the model.
    """
    return math.sqrt(v_apogee * v_apogee + V_GEO * V_GEO
                     - 2.0 * v_apogee * V_GEO * COS_ECLIPTIC_TILT)


# Finishing a GTO-shaped capture, and flat in arrival speed because the apogee
# burn does not know how the spacecraft got to apogee.
DV_GTO_APOGEE_TO_GEO = circularise_at_geo(V_GTO_APOGEE)
# Aerocapture at Earth into an ellipse whose apogee is at GEO, then that same
# apogee burn.  ⚠️  NOT an aerobrake trim: at LEO drag can do the whole job and
# 100 m/s of residue finishes it, while at GEO drag can only lower the apogee
# and circularising is still 1.7 km/s of real burn.  Seventeen times the trim,
# so the two must not be conflated.
A_GEO_AEROCAPTURE = ((6_378.14 + 100.0) + R_GEO) / 2.0
DV_GEO_AEROCAPTURE_ARRIVAL = circularise_at_geo(
    math.sqrt(MU_EARTH * (2.0 / R_GEO - 1.0 / A_GEO_AEROCAPTURE)))


# The cruise-time fit, in years per m/s of delta-v.  Calibrated on CHEMICAL
# transfers, which is why an electric stage takes a thrust-time floor instead
# of this; see `mass_and_clock`.
TAU_CRUISE_FIT_YR_PER_M_S = 0.00023

# 🚨  THE CONSTANTS THE DERIVATION FIXES AT IMPORT, HANDED TO THE DOCUMENT
# RATHER THAN RETYPED IN IT.  Every one of these already appears in an
# expression above; what this dict adds is a NAME the renderer can print a
# value against, so a nomenclature table can be a view of the derivation
# instead of a second copy of it.  Nothing here is read by the derivation, and
# nothing may be added here that is not already defined above: a constant whose
# only definition is this dict is a number the model does not use.
PHYSICS = {
    "g0": G0,
    "mu_earth": MU_EARTH,
    "v_earth": V_EARTH,
    "r_leo": R_LEO,
    "r_moon": R_MOON,
    "dv_nrho": DV_NRHO,
    "dv_leo_deorbit": DV_LEO_DEORBIT,
    "dv_aerobrake_trim": DV_AEROBRAKE_TRIM,
    "dv_nrho_to_lunar_surface": DV_NRHO_TO_LUNAR_SURFACE,
    "r_geo": R_GEO,
    "v_geo": V_GEO,
    "mu_mars": MU_MARS,
    "a_mars_au": A_MARS_AU,
    "tau_fit": TAU_CRUISE_FIT_YR_PER_M_S,
}


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


def _release_key(stamp):
    """A calc stamp as a sortable tuple, so "1.9.0" is older than "1.22.0".

    ⚠️  STRING ORDER IS NOT VERSION ORDER, and this repo has a module whose
    stamps run past .9: compared as text, "1.9.0" sorts ABOVE "1.22.0" and the
    selection would call the older model the newer one.  Anything unparseable
    sorts oldest rather than raising, because a stamp this cannot read is a
    reason to prefer a stamp it can.
    """
    parts = []
    for piece in str(stamp).split("."):
        try:
            parts.append(int(piece))
        except ValueError:
            return (-1,)
    return tuple(parts) or (-1,)


def candidate_sources(catalog_path):
    """Every finished result on disk, as (objective, kind, name) triples.

    🚨  THE DOCUMENT IS ABOUT ONE MISSION, so this exists to make "which one"
    a measurement rather than an accident of which file got passed in.  A
    seven-destination sweep leaves seven catalogs or twenty-eight archived
    cells behind, and every one of them has a best case; only the best of the
    best is worth a document, and the others are not runners-up in the same
    sense -- they are answers to different questions about different places.

    The live catalog is included because the normal case is "I just ran
    something"; the campaign ledger is included because the normal case for a
    SWEEP is that it went through the harness.  Both, so neither has to be
    remembered.
    """
    found = []
    if os.path.exists(catalog_path):
        try:
            row = run_winner(catalog_path)
            found.append((float(row["total_cost_usd"])
                          / float(row["gross_value_usd"]),
                          "catalog", catalog_path,
                          str(row.get("pipeline_version") or "?")))
        except SystemExit:
            pass
    if os.path.exists(LEDGER):
        for r in ledger_rows():
            if not r.get("best_obj"):
                continue
            archive = os.path.join(CAMP, "cells", "%s.csv.gz" % r["cell"])
            if os.path.exists(archive):
                found.append((float(r["best_obj"]), "cell", r["cell"],
                              r.get("calc_version") or "?"))
    return sorted(found)


def unseen_archives():
    """Re-measured archives this comparison deliberately cannot pick.

    🚨  A SELECTION THAT CANNOT SEE A FILE MUST SAY SO, AND THIS ONE DID NOT.
    `campaign/run_cell.py` archives a re-measurement under a name carrying its
    release -- `cislunar__benef__search-on__calc-1.22.0.csv.gz` -- precisely
    so that it can never be mistaken for one of the campaign's own cells, and
    `candidate_sources` looks only at the live catalog and at cells named in
    the LEDGER.  Both halves of that are right and the combination was silent:
    with a 2x2 re-measured, the best result on disk sat in a suffixed archive
    while the run announced a different cell as "the best case" and said
    nothing about the four files it had not looked at.

    ✅  LISTING IS NOT SELECTING, which is the distinction that makes this
    safe.  What was declined, for good reasons, was making the SELECTION glob
    this directory -- that would undo the property the suffix exists for.
    Telling the reader what is here, and which flag reaches it, takes nothing
    away from that.
    """
    cells = os.path.join(CAMP, "cells")
    if not os.path.isdir(cells):
        return []
    known = {r["cell"] for r in ledger_rows()} if os.path.exists(LEDGER) else set()
    out = []
    for name in sorted(os.listdir(cells)):
        if not name.endswith(".csv.gz"):
            continue
        if name[:-len(".csv.gz")] not in known:
            out.append(os.path.join("campaign", "cells", name))
    return out


def run_setting(archived, cfg, told=None):
    """Whether the RUN that produced this row had beneficiation on.

    🚨  THIS IS NOT THE SAME QUESTION AS "DID THIS MISSION CONCENTRATE",
    AND THE MODEL ASKS THE FIRST ONE.  `best_phase_usd_per_kg` is the PURITY
    BOUND the search was given -- the richest hold obtainable, 100% of the best
    phase present -- and calc writes it from `config.use_beneficiation`, not
    from what the winning candidate chose.  A raw run was never given a bound,
    so it reports the bulk value instead.

    🚨  SO A BODY THAT DECLINES TO CONCENTRATE INSIDE A BENEFICIATED RUN
    CARRIES A BOUND ITS OWN MISSION DOES NOT USE, and that is 15.8% of bodies,
    not a corner.  Reading the row's `beneficiation` column here derived the
    bulk value against a row holding the phase maximum: 61% out on 2021 TN102,
    which `--sweep` found on its first run because the DOCUMENT's subject is
    always the best case and the best case never declines.

    ⚠️  IT IS NOT RECOVERABLE FROM THE ROW, AND THAT WAS MEASURED RATHER
    THAN ASSUMED.  The same body run raw and run beneficiated-but-declining
    produces rows identical in 142 of 143 columns; the only one that differs is
    `best_phase_usd_per_kg` itself.  Inferring the flag from that column would
    be deciding the answer from the answer, which is the "check that cannot
    fail" shape this repo has now been caught by twice.

    ✅  THE FILE ANSWERS IT, AND THE FILE IS NOT THE ROW.  Three sources, in
    order: a row that DID concentrate settles it alone; a caller who knows says
    so (`--cell` reads the ledger's own `ore` column, which is the campaign's
    record of that run); and otherwise the catalog the row came from is asked,
    because a raw run's output contains no concentrating row anywhere.  The
    live config is the last resort and the weakest, since it describes this
    process rather than the run that wrote the file.

    Either way the check is the guard: a wrong answer here fails loudly on this
    one column instead of printing a confident wrong page.
    """
    if bool(archived["beneficiation"]):
        return True
    if told is not None:
        return bool(told)
    told = archived.attrs.get("run_beneficiated") if hasattr(archived, "attrs") \
        else None
    if told is not None:
        return bool(told)
    return bool(getattr(cfg, "use_beneficiation", False))


def terms_in_force(row, cfg):
    """Which optional cost terms the row being documented actually carries.

    🚨  READ OFF THE ROW, NOT OFF THE LIVE CONFIG, and that is the whole point.
    This script derives a document ABOUT one row, and that row was produced by
    whatever config was in force when it was written -- which is not
    necessarily what `CALC_CONFIG` holds now.  An archived calc 1.21.2 cell
    charges reliability, the learning curve and the cost of capital; a calc
    1.22.0 run charges none of them and sells the surplus past a ceiling.
    Deriving one against the other produces a document that disagrees with its
    own subject, and the check at the end would report it as a DIFFER on
    fifteen columns rather than as what it is.

    Each term has a diagnostic column that is exactly 1.0 (or absent) when the
    term is off, which is what makes this inferable at all:

      wacc         `wacc_multiplier_upfront` is 1.0 at a zero rate
      reliability  `p_success` is 1.0 when revenue is not discounted
      learning     `learning_curve_factor` is 1.0 when no curve is applied
      surplus      `surplus_payload_kg` does not exist before calc 1.22.0

    ⚠️  `learning_curve_factor` is ALSO 1.0 at N = 1 with the curve on, because
    the cumulative average of one unit is the first unit.  Reading that as
    "off" is harmless precisely because it is inert there: both readings
    produce the same arithmetic, which is why this infers rather than refuses.

    🚨  THE SURPLUS FLAG AND THE SURPLUS FRACTION ARE DIFFERENT QUESTIONS, AND
    ONLY ONE OF THEM HAS TO COME FROM THE CONFIG.  `sell_surplus_at_discount`
    defaults True since calc 1.22.0, so a `--no-surplus-sales` run -- the
    v1.21.0 hard wall, which is what every cell of the 2026-09 campaign was
    measured on -- is a row the live config would describe backwards.  The row
    settles it: `unsold_payload_kg` and `surplus_payload_kg` are EXCLUSIVE by
    construction, so mass past a ceiling landing in the first is positive proof
    the run abandoned it.  Where both are zero no ceiling bound and the two
    readings load the same hold, so either is correct.

    ⚠️  What is genuinely not recoverable is the FRACTION, because a mass does
    not carry the price it fetched.  That one still comes from the config, and
    it only matters on a row that actually sold a surplus.

    🚨  EIGHT MORE DIALS ARE STILL READ FROM THE LIVE CONFIG, AND THE REASON
    THAT IS SAFE IS NOT THAT THEY NEVER MOVE.  It is that every one of them has
    a column in the compared set, so a config that disagrees with the row
    fails the check loudly instead of producing a confident wrong document.
    The table is here because the safety is a property of `comparable()` rather
    than of this function, and deleting a column from there would quietly
    remove it:

      dial                        the column that catches a disagreement
      model_launch_windows        launch_window_wait_yr
      model_propellant_boiloff    boiloff_factor
      model_water_liberation      water_liberated_kg
      model_programme_calendar    programme_calendar_multiplier
      max_fleet_ships             programme_options_priced
      programme_search_steps      programme_options_priced
      concentration_search_steps  concentration_ratio
      demand_elasticity           saturation_multiplier
      surplus_price_fraction      surplus_payload_kg, market_clearing_fraction
      model_rig_trip_limit        rig_terminal_value_usd   <- see below
      every scalar (contingency,  whichever mass or cost it scales; none of
      rig mass, structure frac,   them is recoverable from a row, and every
      heat-shield frac, ...)      one of them moves a compared column

    Read from the ROW and therefore incapable of disagreeing: the destination,
    the market model, insurance, reliability, the learning curve, the cost of
    capital, the surplus flag, the programme search, `model_tank_mass` (via
    `tank_mass_frac`), `model_eclipse_power` (via `array_oversize_factor`) and
    `model_low_thrust_time` (via `ep_thrust_yr`).  `model_rig_service_life` is
    refused by name, because off it is a different programme rather than a dial.

    🚨  `model_rig_trip_limit` IS THE ONE DIAL A ROW CANNOT SETTLE, and it is
    worth knowing why rather than looking for a column that would.  Off, the
    rig keeps its calendar bound and loses its duty-cycle one -- and wherever
    the calendar binds first, which is most rows, `trips_per_ship` comes out
    the same either way and `rig_trip_limit_binds` reads False in both cases.
    The two readings differ only in the SALVAGE credit, through
    `life_used_frac`, so `rig_terminal_value_usd` is what catches it.  Do not
    "fix" this by trying both and keeping whichever matches: that is fitting a
    model to a desired output, which this repo has already declined once.

    ⚠️  **A FLAG WHOSE DEFAULT HAS RECENTLY MOVED IS THE DANGEROUS ONE**, and
    that is the whole lesson of the surplus flag above: it was read from the
    config for one release while `sell_surplus_at_discount` defaulted False,
    which made config and row agree by luck.  calc 1.22.0 flipped it, and every
    hard-wall row -- the entire 2026-09 campaign, and any `--no-surplus-sales`
    run -- started being read backwards.  Measured on a 400-row hard-wall cell
    before the fix: **five columns DIFFER**, `gross_value_usd` among them, by
    0.93%.  **When a default moves in calc, re-ask which side of this line the
    flag is on.**
    """
    def col(name):
        """The row's value for `name`, or None when it has no such column."""
        if name not in row:
            return None
        value = row[name]
        return None if pd.isna(value) else float(value)

    wacc_mult = col("wacc_multiplier_upfront")
    # 🚨  THE MARKET MODEL IS ON THE ROW, so it is read rather than assumed.
    # Four values, and they are not degrees of one thing: `elasticity` bends
    # the price as a market fills, `capacity_cap` holds the price and clips the
    # quantity, and `single_mission` and `unbounded` bound nothing at all.
    # Deriving one against another moves the revenue on every row and the
    # objective with it, and the only column that would notice is
    # `saturation_multiplier`, which is identically 1.0 in three of the four.
    market = (str(row["market_model"]) if "market_model" in row
              and not pd.isna(row["market_model"]) else "capacity_cap")
    # Insurance is two lines and either of them being non-zero is proof the
    # flag was on.  Absent columns mean a row too old to carry them, which is
    # the same thing as not charging them.
    liability = col("liability_cost_usd") or 0.0
    launch_ins = col("launch_insurance_cost_usd") or 0.0
    # Positive proof the run refused the sale rather than discounting it.
    #
    # 🚨  A MILLIGRAM FLOOR, AND A BARE `> 0.0` HERE IS A DEFECT WITH A
    # MEASURED BLAST RADIUS.  The knapsack subtracts what it sold from what it
    # loaded, so a load that cleared leaves one ULP rather than an exact zero:
    # up to 1.455e-11 kg on 1,891 rows of the cislunar beneficiated searched
    # cell.  The tempting reading is that this is harmless because a row with
    # residue sold no surplus.  It is not: **1,769 of those 1,891 rows carry a
    # REAL surplus above a milligram**, and all 1,891 are ceiling-bound.  So a
    # bare test declares those rows hard-walled, `surplus_frac` comes back 0.0,
    # and the derivation prices a load that actually sold a discounted tier as
    # though it had been abandoned -- which is this file's own
    # flipped-default failure arriving from the other side, and it was measured
    # there at five columns differing and `gross_value_usd` by 0.93%.
    #
    # ⚠️  The check at the end WOULD catch it, loudly, which is the argument
    # for the compared column set and not an argument for leaving this.  A
    # document nobody can build is better than a wrong one and worse than a
    # right one.  `verify.py` check 7 takes the same floor, for the same
    # residue, on the same two columns.
    walled = (col("unsold_payload_kg") or 0.0) > UNSOLD_FLOOR_KG
    p_succ = col("p_success")
    lc = col("learning_curve_factor")
    has_surplus_col = "surplus_payload_kg" in row

    return {
        "wacc": True if wacc_mult is None else wacc_mult != 1.0,
        "reliability": True if p_succ is None else p_succ != 1.0,
        "learning": True if lc is None else lc != 1.0,
        # Pre-1.22.0 rows have no such column and are therefore hard-wall rows.
        # ⚠️  AND ONLY WHERE A CEILING EXISTS TO BE PAST.  Three of the four
        # market models bound nothing, so there is no surplus for a second
        # price tier to apply to and reporting one would describe a mechanism
        # that did not run.
        "surplus_frac": (
            max(0.0, min(1.0, float(cfg.surplus_price_fraction)))
            if has_surplus_col and market == "capacity_cap" and not walled
            and getattr(cfg, "sell_surplus_at_discount", False)
            else 0.0),
        # Whether the run SEARCHED the programme, which the row records
        # directly: `programme_options_priced` is how many rungs were costed,
        # and 1 means the ladder never ran.  Without this the derivation
        # searches a ladder the run did not, picks an N the run did not fly,
        # and then disagrees with the row about eleven columns for a reason
        # that has nothing to do with arithmetic.
        "searched": (col("programme_options_priced") or 1.0) > 1.0,
        "n_fixed": int(col("programme_missions") or 1),
        "f_fixed": int(col("fleet_ships") or 1),
        "w_fixed": int(col("missions_per_ship") or 1),
        "market": market,
        "insurance": liability > 0.0 or launch_ins > 0.0,
        "inferred_from_row": wacc_mult is not None,
        "stamp": (str(row["pipeline_version"])
                  if "pipeline_version" in row else "unknown"),
    }


def _rig_life_modelled(row):
    """Whether the run bounded the rig's life at all.

    ⚠️  WRITTEN OUT RATHER THAN `float(row.get(col) or 1) > 0`, because 0.0 is
    FALSY and that spelling reads "the calendar cap is zero" as "the column is
    absent" -- the guard failing open on precisely the row it exists to refuse.
    An absent column means a row too old to report it, which is a modelled rig.
    """
    if "rig_trips_calendar_cap" not in row:
        return True
    value = row["rig_trips_calendar_cap"]
    return bool(pd.isna(value)) or float(value) > 0


def row_destination(row):
    """Where the row being documented was delivering.

    Off the ROW, and off the live config only when the row predates the column.
    Everything destination-shaped keys on this: the return legs, the Stage 2
    prices and their market ceilings, the launch-window phasing, and three cost
    lines.  One answer, read once, so those cannot disagree with each other --
    which is exactly what they did until 2026-09-14.
    """
    import master
    if "delivery_destination" in row and not pd.isna(row["delivery_destination"]):
        return str(row["delivery_destination"])
    return str(master.CALC_CONFIG.delivery_destination)


# One entry, keyed on the file's identity rather than on its name: the default
# path asks for the same catalog twice, once to rank the sources and once to
# fetch the subject, and a full-catalog cell is 1.1 GB.
_WINNER_CACHE = {}


def run_winner(path, designation=None):
    """The best row of a Stage 4 output catalog, or a named one, with provenance.

    🚨  `--designation` USED TO READ THE FILE ITSELF, AND SO GOT A ROW
    WITH NO PROVENANCE ON IT.  Three things are properties of the FILE rather
    than of the row -- the evaluable population, its size, and whether the run
    had beneficiation on -- and `main` fetched a named row with a bare
    `read_csv`, which attaches none of them.  `run_setting` then fell through
    its file source to its LAST resort, the live config, whose
    `use_beneficiation` is True: so a named row out of a RAW catalog was
    derived against the beneficiated purity bound.  Measured on 2005 TH50 of
    `earth_surface__raw__search-on`, `best_phase_usd_per_kg` came out 5.28x
    the row's, and the page also told the reader the best case beat a
    population of zero.

    ⚠️  IT IS THE SAME DEFECT CLAUDE.md RECORDS FOR THE SURPLUS TIER -- a
    reader inferring a run from the live config -- in the one path that
    bypassed the machinery built to stop it.  The remedy is this repo's "one
    definition with two readers": the row is picked HERE either way, so
    whatever is attached to the winner is attached to a named row too and a
    caller cannot get one without the other.  It also removes a second read of
    a file this function had already loaded.

    🚨  READ ONCE PER FILE.  `candidate_sources` asks for the live
    catalog's best case in order to rank the sources, and then `main` asks the
    same question of the same file to get its subject: two pandas reads of
    1.1 GB to answer one question, which was most of the wall clock of a
    default run.  The memo is keyed on path, size and mtime, so a catalog
    rewritten between two calls in one process is read again rather than
    answered from a stale frame.

    ⚠️  NOT the first row.  The file is sorted by `profit_usd` descending and
    the project ranks on `total_cost_usd / gross_value_usd`; those are
    different questions, and README says so where it documents the column
    order.  The best CASE is the lowest ratio.
    """
    if not os.path.exists(path):
        sys.exit("no catalog at %s\nRun Stage 4 first, or pass --cell to "
                 "document an archived campaign cell instead." % path)
    stat = os.stat(path)
    key = (os.path.abspath(path), stat.st_size, stat.st_mtime_ns,
           designation)
    if key in _WINNER_CACHE:
        return _WINNER_CACHE[key]
    frame = pd.read_csv(path, low_memory=False, float_precision="round_trip",
                        dtype={"designation": str})
    if not len(frame):
        sys.exit("%s has no rows" % path)
    usable = frame[frame["gross_value_usd"] > 0]
    if not len(usable):
        sys.exit("%s has no row with positive gross value" % path)
    if designation is None:
        ratio = usable["total_cost_usd"] / usable["gross_value_usd"]
        row = usable.loc[ratio.idxmin()]
    else:
        hit = frame[frame["designation"] == designation]
        if not len(hit):
            sys.exit("%s is not in %s" % (designation, path))
        row = hit.iloc[0]
    # Carried on the row rather than returned separately, so no caller's
    # signature changes and nothing has to remember to thread it.  "The best
    # case" is not a measurement until the page says what it beat.
    row.attrs["population"] = int(len(usable))
    row.attrs["rows"] = int(len(frame))
    # ✅  THE FILE ANSWERS WHAT THE ROW CANNOT.  A run's `use_beneficiation`
    # is invisible in a row that declined to concentrate -- see `run_setting`
    # -- but a RAW run's catalog contains no concentrating row at all, and a
    # beneficiated one is mostly concentrating rows.  That is a property of the
    # file rather than of the row, and it costs nothing here because the frame
    # is already in memory.
    row.attrs["run_beneficiated"] = bool(frame["beneficiation"].astype(str)
                                         .str.lower().isin(["true", "1"]).any())
    _WINNER_CACHE[key] = row
    return row


def row_shape(archived):
    """The architecture axes a row carries, as the renderer branches on them.

    ONE DEFINITION WITH TWO READERS.  `context` needs it to decide what this
    cascade can express and the renderer branches its prose on it; `--sweep`
    needs the same answer about rows it has not derived yet, to find a covering
    set.  Two copies of "what shape is this mission" is the defect this repo
    catalogues first, so there is one and both call it.

    Every value is read off the ROW.  See `terms_in_force` for the same
    argument about the cost terms, and `row_destination` for the destination.
    """
    return dict(beneficiated=bool(archived["beneficiation"]),
                aero=bool(archived["aerocapture_return"]),
                isru=bool(archived["isru_return"]),
                power=str(archived["power_source"]),
                apsis=str(archived["rendezvous_apsis"]),
                # 🚨  TWO DIFFERENT QUESTIONS, AND ONLY ONE OF THEM IS THE
                # PROPELLANT.  A delta-v penalty above 1 marks an electric
                # row and is applied to the legs UNCONDITIONALLY, but whether
                # an electric STAGE is sized for it is `model_low_thrust_time`
                # as well.  With that flag off the model charges the penalty
                # and flies no array, no PPU and no thruster, and there is no
                # thrust-time floor on the duration.  `ep_thrust_yr` is the
                # model's own answer to "was a stage sized", so it is read
                # rather than re-derived from the propellant row.
                penalised=float(archived["dv_penalty_factor"]) > 1.0,
                electric=(float(archived["ep_thrust_yr"]) > 0.0
                          if "ep_thrust_yr" in archived
                          and not pd.isna(archived["ep_thrust_yr"])
                          else float(archived["dv_penalty_factor"]) > 1.0))


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
    hits, total = [], 0
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        header = fh.readline()
        for line in fh:
            total += 1
            if needle in line:
                hits.append(line)
    frame = pd.read_csv(_lines(header, hits), float_precision="round_trip",
                        dtype={"designation": str})
    frame = frame[frame["designation"] == designation]
    if len(frame) != 1:
        sys.exit("expected one row for %s in %s, found %d"
                 % (designation, cell, len(frame)))
    row = frame.iloc[0]
    # Counted while streaming, which costs nothing: the loop above already
    # touches every line.  An archived cell holds evaluable rows only, so this
    # is the evaluable population and not the catalog.
    row.attrs["population"] = total
    row.attrs["rows"] = total
    return row


def catalog_body(designation):
    """The Stage 1 catalog row for one body, streamed out of the 862 MB CSV.

    🚨  `designation` IS READ AS A STRING, EXPLICITLY.  A numbered asteroid's
    designation looks like an integer, so when every line this streams back
    happens to be a numbered one, `read_csv` infers `int64` for the column and
    the `== "69260"` below matches nothing -- "expected one row, found 0" on a
    body that is right there.  It is the dtype-inferred-from-the-data trap this
    repo catalogues: it works on a slice containing one provisional
    designation and fails on a slice that does not.
    """
    return catalog_bodies([designation])[designation]


def catalog_bodies(designations):
    """The Stage 1 rows for SEVERAL bodies, in one pass over the 862 MB CSV.

    🚨  A PASS PER BODY IS THE COST THAT DECIDES WHETHER A SWEEP IS AFFORDABLE.
    One document reads one body and the pass is the price of admission; a
    covering sweep reads eight, and eight passes over 862 MB is most of the
    run.  The file is streamed once and every needle is matched against the
    same line, which costs no more than the first body did.

    `catalog_body` is this with one designation, kept because a single lookup
    reads better at the call sites and because its docstring carries the dtype
    trap that applies to both.
    """
    path = os.path.join(ROOT, "asteroid_pipeline", "asteroid_catalog.csv")
    if not os.path.exists(path):
        sys.exit("missing %s; run_pipeline.py --check-inputs explains this" % path)
    wanted = [(str(d), "%s," % str(d)) for d in dict.fromkeys(designations)]
    hits = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        header = fh.readline()
        for line in fh:
            for _d, needle in wanted:
                if needle in line:
                    hits.append(line)
                    break
    frame = pd.read_csv(_lines(header, hits), low_memory=False,
                        float_precision="round_trip",
                        dtype={"designation": str})
    out = {}
    for des, _needle in wanted:
        hit = frame[frame["designation"] == des]
        if len(hit) != 1:
            sys.exit("expected one catalog row for %s, found %d"
                     % (des, len(hit)))
        out[des] = hit.iloc[0]
    return out


def _lines(header, rows):
    """A file-like over a header plus some matched lines, for `read_csv`."""
    import io
    return io.StringIO(header + "".join(rows))


def mineral_catalog_for(dest):
    """The Stage 2 catalog priced for `dest`, and a note saying where it came from.

    🚨  A STAGE 2 CATALOG IS PRICED FOR ONE DESTINATION AND IS WRONG FOR EVERY
    OTHER, which is the same trap `preflight()` refuses a run over, arriving
    here from the other side.  Both halves of the file are destination-
    specific: `delivered_value_usd_per_kg` is what a kilogram fetches THERE,
    and `annual_market_kg` is ROUTED, so a commodity flown home is bounded by
    world production while the same commodity sold at a depot is bounded by
    that depot's import budget.  Reading the live catalog for an archived
    `geo` cell would price martian-depot ore at cislunar rates and bound it
    against cislunar ceilings, and nothing would raise.

    The live catalog is used when it says it is the right one, because that is
    the normal case for "the run I just did".  Otherwise the campaign's frozen
    per-destination catalogs are the authority, and they are the ones the
    archived cells were actually measured against.  A destination with neither
    is a refusal rather than a substitution.
    """
    import master
    live = os.path.join(ROOT, "asteroid_pipeline",
                        master.CALC_CONFIG.mineral_catalog_file)
    if os.path.exists(live):
        head = pd.read_csv(live, nrows=1)
        if ("delivery_destination" in head
                and str(head["delivery_destination"].iloc[0]) == dest):
            return live, "the live Stage 2 catalog"
    frozen = os.path.join(CAMP, "stage2",
                          "mineral_value_catalog.%s.csv" % dest)
    if os.path.exists(frozen):
        return frozen, "campaign/stage2, frozen 2026-09-09"
    sys.exit("no Stage 2 catalog priced for %r.\n"
             "  the live catalog is priced for another destination and there "
             "is no frozen one at\n  %s\n"
             "Run Stage 2 for that destination, or document a cell whose "
             "prices are on disk." % (dest, frozen))


def reference_tables(dest):
    """Module 2's mineral catalog and Module 3's four tables, as loaded.

    Read through `master`'s own loader so the dtypes and the list-column
    parsing are the pipeline's, not a second opinion about them.  The mineral
    catalog is chosen by DESTINATION; see `mineral_catalog_for`.
    """
    import master
    cfg = master.CALC_CONFIG
    cfg.input_dir = os.path.join(ROOT, "asteroid_pipeline")
    tdir = os.path.join(cfg.input_dir, cfg.transportation_subdir)
    minerals_path, minerals_from = mineral_catalog_for(dest)
    return {
        "minerals_from": minerals_from,
        "minerals": master._load_csv(minerals_path, "M2"),
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
    residual.  Module 1's fractions sum to 0.73-0.96 and the remainder is
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


# How close two statements of one quantity have to be before the difference
# is float association rather than a disagreement.  🚨  IT IS READ BY THREE
# THINGS -- the comparison below, the line the run prints, and the sentence in
# the document's footer -- and until 2026-09-17 it was TYPED into all three,
# so tightening it would have left the page claiming the old bound while the
# check enforced the new one.  The footer carries it out of `check()` now.
CLOSE_TOL = 1e-12


def taxonomy_fraction_span():
    """How far short of 1.0 Module 1's taxonomy fractions actually fall.

    🚨  THIS WAS TYPED INTO THE DOCUMENT AS "between 0.73 and 0.96", AND THE
    SAME PAIR OF DIGITS HAS ALREADY BEEN WRONG ONCE IN THIS REPO.  It read
    0.76-0.96 in CLAUDE.md and in seven places in code until 2026-09-15 --
    somebody had read the `C` row, which sums to exactly 0.76, and generalised
    it to the whole complex when `Cgh` sums to 0.73.  It was wrong at birth
    rather than gone stale, because nothing had ever executed it, and the
    correction then reached the docs and left the code copies standing, one of
    which this document RENDERED to a reader for a day.

    So it is computed.  The interval is a consequence, and what the page
    asserts is the PROPERTY behind it: every real class sums to strictly less
    than one, which is what guarantees there is a residual for the bulk
    silicate floor to catch.  An interval would go red the day somebody
    re-measures a taxonomy row, which is a legitimate act; the property would
    not.  That is `verify_stage1.py` check 2's distinction, applied here.

    `Unknown` is the deliberate exception -- all four fractions are `None`, so
    the residual is the whole body -- and is excluded rather than skipped
    quietly.
    """
    import master
    fields = [column[len("comp_"):] for column in master.FRACTION_TO_MINERAL]
    sums, absent = {}, []
    for name, row in master.TAXONOMY_COMPOSITION.items():
        values = [row.get(field) for field in fields]
        if any(v is None for v in values):
            absent.append(name)
            continue
        sums[name] = sum(float(v) for v in values)
    assert sums, "no taxonomy class carries a full set of fractions"
    low, high = min(sums.values()), max(sums.values())
    assert high < 1.0, (
        "a taxonomy class sums to %r, so it leaves no residual for the "
        "bulk-silicate floor: %s"
        % (high, [n for n, s in sums.items() if s >= 1.0]))
    return {
        "low": low, "high": high, "classes": len(sums),
        "at_low": sorted(n for n, s in sums.items() if s == low),
        "at_high": sorted(n for n, s in sums.items() if s == high),
        "unfractioned": sorted(absent),
    }


def market_ceilings(minerals):
    """{phase: (market key, kg/yr)}, with the residual pooled onto silicates."""
    import master
    caps = dict(zip(minerals["name"], minerals["annual_market_kg"]))
    return caps, dict(master._PHASE_MARKET_ALIAS)


def knapsack(payload_kg, feed_kg, phases, recovery, caps=None, keys=None,
             surplus_frac=0.0):
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

    `surplus_frac` is calc 1.22.0's second price tier: what a kilogram past a
    ceiling fetches, as a fraction of the full price.  At 0.0 this is the
    v1.21.0 wall and not one float below differs from it.  Above 0.0 every
    phase enters the walk TWICE, once at full price bounded by its allowance
    and once at the discount bounded by what the feed has left, and the merged
    list is sorted by unit price like any other fractional knapsack.  Greedy
    stays exact because a two-step price schedule is two items rather than a
    clamp, and the interleaving is the point: a rich phase's discounted surplus
    can outrank a poor phase's full-price allowance, and where it does the
    optimal hold carries it instead.
    """
    tiers = []
    for name, frac, price in sorted(phases, key=lambda p: -p[2]):
        tiers.append((name, frac, price, True))
        if caps is not None and surplus_frac > 0.0:
            tiers.append((name, frac, price * min(1.0, surplus_frac), False))
    # Stable, so a phase's full-price tier still precedes its discounted one
    # when the fraction is exactly 1.0 and the two prices tie.
    tiers.sort(key=lambda t: -t[2])

    remaining, total, mix = float(payload_kg), 0.0, {}
    surplus, taken = 0.0, {}
    # The walk itself, recorded rung by rung so the document can show WHY each
    # phase took what it took.  Nothing below reads it: it is appended to and
    # never consulted, which is what makes it safe to add to a function every
    # release is argued from.  A hold table without the supply beside it is a
    # list of answers, and the two bounds -- you cannot load more of a phase
    # than the feed contained, and the hold fills -- are invisible without it.
    walk = []
    for name, frac, price, full in tiers:
        if remaining <= 0:
            walk.append({"phase": name, "price": price, "full": full,
                         "supply": float(feed_kg) * frac * recovery,
                         "available": 0.0, "allowance": None, "hold": 0.0,
                         "take": 0.0, "stopped": True})
            continue
        take = min(float(feed_kg) * frac * recovery - taken.get(name, 0.0),
                   remaining)
        step = {"phase": name, "price": price, "full": full,
                "supply": float(feed_kg) * frac * recovery,
                "available": (float(feed_kg) * frac * recovery
                              - taken.get(name, 0.0)),
                "allowance": None, "hold": remaining, "stopped": False}
        if full and caps is not None:
            key = (keys or {}).get(name, name)
            allowance = caps.get(key)
            if allowance is not None:
                step["allowance"] = allowance
                take = min(take, allowance)
                caps[key] = allowance - take
        # Recorded before the skip: a full tier whose allowance is spent takes
        # nothing, and if that went unrecorded its own surplus tier would be
        # read as the full one and clipped at the same exhausted allowance.
        taken[name] = taken.get(name, 0.0) + take
        step["take"] = take
        walk.append(step)
        if take <= 0:
            continue
        mix[name] = mix.get(name, 0.0) + take
        if not full:
            surplus += take
        total += take * price
        remaining -= take
    loaded = float(payload_kg) - remaining
    return {"mix": mix, "value": total, "loaded": loaded, "surplus": surplus,
            "walk": walk,
            "usd_per_kg": total / loaded if loaded > 0 else 0.0}


def raw_hold(payload_kg, phases):
    """The hold of a run-of-mine mission: the body's own proportions.

    Nothing is chosen here, which is the whole difference from the
    beneficiated case.  A raw mission digs what it flies and flies what it
    digs, so the mix is the composition scaled to the payload, and the phase
    fractions are normalised because they sum to 0.73-0.96 rather than to 1:
    the residual is bulk silicate that the phase table prices separately.

    No `recovery` term appears, and that is not an omission.  Separation
    recovery is the fraction of a phase that reports to CONCENTRATE, and a
    mission that does not concentrate never pays it.
    """
    frac_sum = sum(f for _n, f, _p in phases)
    if frac_sum <= 0:
        return {"mix": {}, "value": 0.0, "loaded": 0.0, "surplus": 0.0,
                "usd_per_kg": 0.0}
    mix = {n: payload_kg * f / frac_sum for n, f, _p in phases}
    value = sum(mix[n] * p for n, _f, p in phases)
    return {"mix": mix, "value": value, "loaded": float(payload_kg),
            "surplus": 0.0,
            "usd_per_kg": value / payload_kg if payload_kg > 0 else 0.0}


def raw_sale(load, phases, caps, keys, surplus_frac):
    """What a run-of-mine hold actually sells, clipped per market.

    The hold is fixed, so unlike the beneficiated case there is nothing to
    optimise: each phase sells what it can inside its market's allowance, and
    what is past it either earns nothing or earns the discount, exactly as in
    the sale the model runs for raw cargo.

    Accumulated in the phase table's own order rather than by price, because
    that is the order the model's `_capped_sale_value` walks and floating-point
    addition is not associative.  The two have to agree to the last bit for the
    check at the end to mean anything.
    """
    price = {n: p for n, _f, p in phases}
    remaining = dict(caps)
    value = unsold = surplus = 0.0
    # Recorded and never read here, exactly as in `knapsack`: the document
    # needs to show which phase met its ceiling and by how much, and a sale
    # reported only by its total cannot say.
    walk = []
    for name, kg in load["mix"].items():
        key = keys.get(name, name)
        allowance = remaining.get(key, float("inf"))
        if kg > allowance:
            over = kg - allowance
            value += allowance * price[name]
            if surplus_frac > 0.0:
                value += over * price[name] * surplus_frac
                surplus += over
            else:
                unsold += over
            remaining[key] = 0.0
            walk.append({"phase": name, "price": price[name], "hold": kg,
                         "allowance": allowance, "full": allowance,
                         "over": over, "bound": True})
        else:
            value += kg * price[name]
            remaining[key] = allowance - kg
            walk.append({"phase": name, "price": price[name], "hold": kg,
                         "allowance": allowance, "full": kg,
                         "over": 0.0, "bound": False})
    return {"mix": dict(load["mix"]), "value": value, "loaded": load["loaded"],
            "surplus": surplus, "unsold": unsold, "walk": walk,
            "usd_per_kg": value / load["loaded"] if load["loaded"] else 0.0}


# -------------------------------------------------------------- rate ledger
# Every reference-table constant the derivation reads, recorded as it is read.
#
# 🚨  THE RATES ARE THE HALF A COLUMN AUDIT CANNOT SEE.  A column audit asks
# whether every quantity the model OUTPUT is on the page; it is silent about
# the constants that produced them, because a rate is an input and no output
# column names it.  A dig time with no rig throughput beside it, a power draw
# with none of its three energy rates, an electric stage with no per-newton
# figure: each is a number the page asks a reader to take on trust.
#
# ✅  SO THE LIST IS RECORDED RATHER THAN TYPED.  A hand-maintained list of
# rates to look for is a second copy of what the derivation reads, and this
# repo has a file full of what happens to second copies.  `val` and the two
# `Recorded` rows below log every constant they hand out, so the audit's list
# IS the derivation's list, and a rate added to the cascade tomorrow joins the
# audit with no edit here.
# Every reference-table read of the CURRENT derivation; the audit's list of
# rates to look for is this, rather than a list somebody maintains.
#
# 🚨  IT IS PER DOCUMENT, AND A SWEEP BUILDS SEVERAL IN ONE
# PROCESS.  Left to accumulate, mission two is audited against every rate
# mission one read as well as its own, and reports as incomplete a page that
# shows everything it actually used.  That is what made `--sweep --audit`
# disagree with a single `--audit` of the same row: the first mission came out
# clean and every one after it inherited the last one's reads.  `build` clears
# it, so "the rates this derivation read" means this one.
RATE_LOG = []


def record_rate(table, field, value):
    """Log one reference-table read, if it is a number worth showing."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    # A zero rate has nothing to show and matches anything; see the same
    # exclusion in the column audit, and for the same reason.
    if number == number and number != 0.0:
        RATE_LOG.append((table, field, number))
    return value


class Recorded(object):
    """A reference-table row that logs which of its fields were read.

    ⚠️  IT MUST STAY A PROXY AND NOT A COPY.  `C["pro"]` and `C["veh"]` are
    read again in the cost cascade, hundreds of lines from here, and those
    reads are rates too -- `cost_usd_per_kg` and `usd_per_kg_to_leo` are two
    of the largest lines in the answer.  A dict snapshot taken at construction
    would record the fields this function happens to touch and miss those.
    """

    def __init__(self, row, table):
        """Wrap one row of `table`, which is named so the log can say where."""
        self._row = row
        self._table = table

    def __getitem__(self, field):
        """The field, logged.  This is the read the derivation mostly makes."""
        return record_rate(self._table, field, self._row[field])

    def get(self, field, default=None):
        """The field if the table carries it, logged; otherwise `default`.

        ⚠️  A DEFAULT IS NOT A RATE AND MUST NOT BE LOGGED AS ONE.  A column
        an older table does not have is a fallback this derivation chose, not
        a constant a reader could look up, so the miss returns before
        `record_rate` sees it.
        """
        if field not in self._row:
            return default
        return record_rate(self._table, field, self._row.get(field, default))

    def __contains__(self, field):
        """Membership, unlogged: asking is not reading."""
        return field in self._row

    def raw(self, field, default=None):
        """The field, UNLOGGED: asking what the table says is not using it.

        ⚠️  READING IS NOT SPENDING, AND THAT IS THE WHOLE RULE.
        `run_propellant_price` compares the table against the price the row was
        actually costed at, so it has to read the table even when it then
        declines to use it; logging that read would put a rate on the audit's
        list that no cost line on the page spends, which is the audit's own
        complaint about a rate a branch cannot use, arriving from the other
        side.  The value that IS used is logged, once, by the caller.  The
        other use is the run's own report, which names the propellant it
        substituted a price for -- a label, not a rate.

        ⚠️  SO REACH FOR `__getitem__` UNLESS YOU CAN SAY WHY THE READ IS
        NOT A USE.  This is a way past the rate audit, and an unexplained call
        is a rate that quietly stopped being checked.
        """
        return self._row.get(field, default)


# ------------------------------------------------- the price the RUN paid
def run_propellant_price(pro, archived):
    """($/kg the run was costed at, the table's figure if it has since moved).

    🚨  A STAGE 3 TABLE ON DISK IS NOT NECESSARILY THE ONE THE RUN READ,
    AND NOTHING ABOUT A REFETCHED PRICE LOOKS WRONG.  Every other architecture
    term this derivation needs is read off the ROW for exactly this reason --
    the tank fraction, the eclipse flag, the window wait, the ore setting --
    and the propellant price was the one input still taken from whatever
    `propellants.csv` happens to hold today.  Three of the live-priced
    propellants were refetched on 2026-09-17 and moved by up to 4.2%, so every
    archived chemical mission stopped reproducing: measured on
    `earth_surface__raw__search-on`, 2005 TH50 came out **7 columns DIFFER**,
    the two propellant lines by 1.660e-03 relative and five totals downstream
    of them by ~1.5e-08.

    ✅  AND THE PRICE WAS RECOVERABLE FROM THE ROW ALL ALONG.  A Stage 4
    output carries the cost and the mass, so their ratio IS the input:
    measured constant per propellant across a cell, and the round trip is
    bit-exact on 3,916 of 4,000 rows and inside 1e-12 on the other 84.  This
    is CLAUDE.md's "an input you cannot recover from a backup may still be
    recoverable from an output that was priced with it", taken from a one-off
    rescue to the normal path.

    ⚠️  THE TABLE WINS WHEN THE TWO AGREE, and that is not a nicety.
    Recovering by division introduces a rounding the run never made, so
    snapping to the table's own float where nothing has moved is what keeps
    the unmoved cells bit-exact rather than merely close -- which is the
    standard this project argues its releases from.

    ⚠️  OUTBOUND, NEVER THE RETURN.  Propellant made on site is billed at
    `isru_processing_usd_per_kg` and not at the propellant's price at all, so
    the return pair recovers the wrong number on exactly the missions ISRU
    exists for.  The outbound leg is always bought.
    """
    table_price = float(pro.raw("cost_usd_per_kg"))
    cost = archived.get("outbound_prop_cost_usd")
    mass = archived.get("m_outbound_prop_kg")
    used, moved = table_price, None
    if cost is not None and mass is not None:
        try:
            cost, mass = float(cost), float(mass)
        except (TypeError, ValueError):
            cost = mass = float("nan")
        # A row that bought no outbound propellant divides by zero and knows
        # nothing about the price; so does one too old to carry the columns.
        if mass > 0.0 and cost == cost and mass == mass:
            recovered = cost / mass
            if abs(recovered - table_price) > 1e-9 * max(1.0, abs(table_price)):
                used, moved = recovered, table_price
    # Logged ONCE, on the value actually spent.  See `Recorded.raw`.
    record_rate("M3 propellants", "cost_usd_per_kg", used)
    return used, moved


# ------------------------------------------------------- the night-side plant
def eclipse_derate(w_bare, dark_h, dark_fraction, storage_wh_per_kg,
                   storage_efficiency, baseline_dark_h):
    """(effective W/kg for a plant that spends half its time in shadow, oversize).

    🚨  THIS WAS CALLED OUT OF THE PIPELINE WHILE THE FOOTER TOLD THE READER
    THE PLANT WAS DERIVED HERE.  It is the single largest correction on the
    plant -- the battery term alone is about a third of it -- and the page
    already carried all six of its inputs, so what was borrowed was the
    arithmetic and nothing else.  See `model_borrows`.

    Both eclipse terms are proportional to the continuous draw P, so they
    collapse into one specific power the rest of the cascade can use exactly
    where it used the bare 1/r^2 figure:

        m_plant = P*oversize/w + P*dh/e_store = P * (oversize/w + dh/e_store)

    The array is oversized because sunlit hours run the load AND recharge the
    store, and the recharge is lossy.  The storage term is an INCREMENT: the
    60 W/kg system-level rating already carries a LEO-class battery, and
    Module 3 names how much (`Power-system row baseline dark period`), so only
    the excess is new mass.  Charging the whole dark period would buy that
    battery twice.

    ⚠️  WRITTEN TERM FOR TERM, NOT TIDIED.  Float multiplication does not
    associate, and this file argues its agreement in the last bit; the
    `(1 - f) + f/eta` over `(1 - f)` is the model's association and a cancelled
    version of it is a different number.  Same rule as `hours`.
    """
    w = float(w_bare)
    if w <= 0:
        return w, 1.0
    f = max(0.0, min(0.95, float(dark_fraction)))
    # Exactly 1.0 at f = 0: permanent sunlight, which is what a free-flying EP
    # array enjoys and why it never takes this term.
    if f <= 0.0:
        return w, 1.0
    eta = max(0.05, min(1.0, float(storage_efficiency)))
    oversize = ((1.0 - f) + f / eta) / (1.0 - f)
    kg_per_w = oversize / w
    if storage_wh_per_kg > 0:
        excess_h = max(0.0, float(dark_h) - max(0.0, float(baseline_dark_h)))
        kg_per_w += excess_h / float(storage_wh_per_kg)
    return (1.0 / kg_per_w if kg_per_w > 0 else w), oversize


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
    veh = Recorded(veh[veh["name"] == archived["vehicle"]].iloc[0],
                   "Module 3 vehicles")
    pro = tables["propellants"]
    pro = Recorded(pro[pro["name"] == archived["propellant"]].iloc[0],
                   "Module 3 propellants")

    shape = row_shape(archived)
    # PER AXIS, not one monolithic comparison.  The old guard tested the whole
    # shape tuple against a single supported shape, so a raw mission -- which
    # is what the quick and standard presets fly, and therefore the commonest
    # run anybody makes -- was refused with a message that named five axes as
    # wrong when only one of them was.  Each axis now says for itself whether
    # this cascade covers it, and the refusal names only the ones that do not.
    #
    # `beneficiated` takes both values as of 2026-09-14.  The other four are
    # genuinely not implemented here: aerocapture adds a TPS mass that is
    # hauled out and pushed back, ISRU rewrites where the return propellant
    # comes from, a radioisotope plant is sized on a different W/kg, and the
    # chemical case has no electric stage to solve for.
    # 🚨  THE DESTINATION IS A SHAPE AXIS TOO, AND IT WAS THE ONE NOBODY
    # NOTICED.  `_legs` used to hard-code the cislunar capture while `context`
    # read the destination off the LIVE config for the delivery ladder, the
    # delivered price and the synodic period.  Those disagreed silently: the
    # config said earth_surface, the geometry was cislunar, and the document
    # printed earth_surface at the top of a cislunar derivation.  It reproduced
    # the row only because the row WAS cislunar.  The destination now comes
    # from the row and drives the legs, the prices, the phasing and the cost
    # rates together, so there is one answer rather than three.
    dest = row_destination(archived)
    arch = master.DELIVERY_ARCHITECTURES.get(dest)
    unsupported = [
        name for name, ok in (
            # Every destination and every architecture the search can
            # choose derives now, so what is left here is the one case that is
            # not an architecture at all.
            ("delivery to %r" % dest, arch is not None),
            # 🚨  `model_rig_service_life` OFF IS NOT A DIAL, IT IS A
            # DIFFERENT PROGRAMME.  The rig stops being retired at all and one
            # of them serves the whole campaign, so `trips_per_ship` and the
            # calendar cap both come back 0 and the rig's amortisation, its
            # salvage credit and the whole `W < trips` structure stop meaning
            # what this cascade means by them.  The model itself warns when it
            # is combined with the programme search.  Refused by name rather
            # than approximated.
            ("rig service life not modelled", _rig_life_modelled(archived)),
            ("power source %r" % shape["power"],
             shape["power"] in ("solar", "rtg")),
            # A fallback delta-v pair rather than a real geometry, which the
            # model emits when a row's orbital elements do not close.  There is
            # no transfer to write out, so there is nothing to derive.
            ("rendezvous apsis %r" % shape["apsis"],
             shape["apsis"] in ("aphelion", "perihelion")),
        ) if not ok
    ]
    if unsupported:
        sys.exit("this derivation does not cover: %s\n"
                 "  row shape %r\n"
                 "Extend the cascade before pointing the document at it, or "
                 "pass --designation to document a body whose winning mission "
                 "this cascade can express."
                 % (", ".join(unsupported), shape))

    # A replaced config rather than a mutated global, the same construction
    # the programme ladder uses: the three destination reads below have to
    # agree with the row, and nothing else in the process should change.
    cfg = master.CALC_CONFIG
    if cfg.delivery_destination != dest:
        import dataclasses
        cfg = dataclasses.replace(cfg, delivery_destination=dest)
    benef = shape["beneficiated"]
    rows = set(ops["category"])

    def val(item, used=True):
        """One Module 3 row, or a failure.

        🚨  `used` IS WHAT THE PAGE'S OWN BRANCH ASKS, and it
        exists because the audit compares against what this derivation READ.
        A chemical mission reads the power-processing figure and can do nothing
        with it: no electric stage is sized, so no page shows it, and logging
        it as a rate would report the page incomplete for a number it has no
        business printing.  The rule is the one the `comp_group` false positive
        established -- share the page's condition rather than exempt the row --
        so the predicate here is the same shape flag the renderer branches on.

        `_ops_value` falls back to a default when the row is absent, which is
        silent and flattering: a renamed row would leave this document quietly
        computing on a constant the tables no longer hold.  A name that does
        not resolve is a finding, so it raises.
        """
        if item not in rows:
            sys.exit("Module 3 has no row named %r; the ops table was renamed "
                     "underneath this derivation." % item)
        value = master._ops_value(ops, item, default=float("nan"))
        return record_rate("Module 3 operations", item, value) if used else value

    a_au = float(body["semi_major_axis_au"])

    # Eclipse-derated specific power for the plant that stands on the body, and
    # the bare 1/r^2 figure for the array that never leaves sunlight.
    w_bare = val("Power system specific mass") / (a_au * a_au)
    rot_h = body.get("rotation_period_h")
    rot_h = (float(rot_h) if rot_h is not None and not pd.isna(rot_h)
             else cfg.default_rotation_period_h)
    # ⚠️  A NIGHT IS HALF A ROTATION, UP TO A CEILING.  A slow rotator would
    # otherwise buy a storage bank sized for a week of darkness, so the model
    # clamps it; the clamp has an output column of its own, which is the
    # model's own statement that it is worth reporting.
    rot_measured = not pd.isna(body.get("rotation_period_h"))
    dark_clamped = rot_h / 2.0 > cfg.max_dark_period_h
    dark_h = min(rot_h / 2.0, cfg.max_dark_period_h)
    # 🚨  `model_eclipse_power` ZEROES THE DARK FRACTION, AND THE ROW SAYS SO.
    # With the flag off the plant takes the bare 1/r^2 figure and the oversize
    # factor is exactly 1.0, which is the one value it can never otherwise
    # reach: the Module 3 dark fraction is a positive constant and `dark_h` is
    # positive on every body.  So an oversize of 1.0 in the row IS the flag,
    # and reading it here is what stops the derivation flying roughly twice
    # the array the run did.
    row_oversize = archived.get("array_oversize_factor")
    eclipse_on = (True if row_oversize is None or pd.isna(row_oversize)
                  else float(row_oversize) != 1.0)
    # ⚠️  AND IT ZEROES THE REPORTED DARK PERIOD TOO, not only the fraction.
    # `dark_period_h` is a column and the document prints it in words, so a
    # derivation that kept quoting the body's rotation would describe a
    # night-side penalty the run did not take.
    if not eclipse_on:
        dark_h = 0.0
    w_plant, oversize = eclipse_derate(
        w_bare, dark_h,
        val("Eclipse / night-side dark fraction") if eclipse_on else 0.0,
        val("Energy storage usable specific energy"),
        val("Energy storage round-trip efficiency"),
        val("Power-system row baseline dark period"))

    # 🚨  `tank_mass_frac` IS A COLUMN, so `model_tank_mass` is a switch the
    # ROW settles and the config must not.  Turning it off is not a rounding:
    # it removes k_out and k_ret from the cascade entirely, and deriving a
    # tanked mission against an untanked row moved 48 of 85 quantities,
    # `campaign_cadence_yr` among them by 46%.  The Module 3 derivation is kept
    # as the fallback for a row too old to carry the column.
    row_tank = archived.get("tank_mass_frac")
    tank_frac = (float(row_tank) if row_tank is not None and not pd.isna(row_tank)
                 else (float(pro["tank_kg_per_L"]) / float(pro["density_kg_per_L"])
                       if cfg.model_tank_mass else 0.0))

    prop_usd_per_kg, prop_moved = run_propellant_price(pro, archived)

    row_wait = archived.get("launch_window_wait_yr")
    windows_on = (bool(cfg.model_launch_windows)
                  if row_wait is None or pd.isna(row_wait)
                  else float(row_wait) > 0.0)

    trip_cap_m3 = int(val("Mining rig maximum trips"))
    row_trips = archived.get("trips_per_ship")
    rig_trip_limit = not (row_trips is not None and not pd.isna(row_trips)
                          and trip_cap_m3 > 0 and float(row_trips) > trip_cap_m3)

    ice_frac = (0.0 if body.get("comp_ice_fraction") is None
                or pd.isna(body.get("comp_ice_fraction"))
                else float(body["comp_ice_fraction"]))
    isru_feed_per_kg = isru_water_per_kg = 0.0
    if shape["isru"]:
        material = str(pro.get("isru_feed_material") or "").strip().lower()
        feed_ratio = float(pro.get("isru_feed_kg_per_kg") or 0.0)
        if material == "regolith":
            isru_feed_per_kg = feed_ratio
        elif material == "water" and ice_frac > 0:
            isru_water_per_kg = feed_ratio
            isru_feed_per_kg = feed_ratio / (
                ice_frac * max(1e-6, min(1.0, cfg.beneficiation_recovery)))
        else:
            sys.exit("the row says it made %r on site, and Module 3 gives no "
                     "feed material this body can supply.\n"
                     "  material %r, ice fraction %g" % (
                         str(archived["propellant"]), material, ice_frac))
    # The launch cost avoided, which is where an in-space price comes from.
    # Read as the leg chain rather than as one number so the document can show
    # the stage that produces it; one `burn` leg for a cislunar depot.
    # 🚨  `or []` WOULD DESTROY THE ONE DISTINCTION THAT MATTERS
    # HERE.  Module 2 keys on identity: `earth_surface` maps to None and avoids
    # no launch at all, `leo` maps to `[]` and avoids the whole LEO price with
    # nothing to fly above it.  Flattening the first into the second made the
    # Earth's surface price its non-existent chain at 4,253 $/kg, which is what
    # `delivery_chain` and the renderer both test with `is not None`.
    legs = master._DELIVERY_LEGS.get(cfg.delivery_destination)
    # 🚨  THE FOUR COLUMNS BEHIND EVERY PRICE IN THE PHASE TABLE, so the page
    # can show where a delivered price comes from instead of asserting it.
    # Stage 2 writes them all: a commodity USED at the destination is worth its
    # terrestrial quote PLUS its utility share of the launch cost avoided, less
    # what refining it on site costs; one flown HOME is worth its terrestrial
    # quote less the downleg, floored at zero.  Which of the two happened is
    # `value_route`, and it is the column that explains why ruthenium prices at
    # exactly zero beside rhodium at six figures.
    # 🚨  `earth_surface` HAS NONE OF THESE COLUMNS, AND THAT IS STRUCTURAL
    # RATHER THAN A STALE ARTIFACT.  A kilogram landed on Earth avoids no
    # launch, so Stage 2 writes no utility, no downleg and no route for it:
    # six of the seven destinations carry the five columns and the seventh
    # carries none.  Reading them unconditionally raised `KeyError` on the one
    # destination whose whole point is that the chain does not apply, which is
    # this repo's own "a column the file does not have" trap arriving in the
    # document.  An empty dict is the right answer there, and the renderer
    # already has a branch for a destination with no delivery legs.
    needed = ("terrestrial_price_usd_per_kg", "in_space_utility",
              "downleg_cost_usd_per_kg", "in_space_processing_usd_per_kg",
              "value_route", "price_usd_per_kg")
    price_parts = {}
    if all(column in tables["minerals"].columns for column in needed):
        for _i, m in tables["minerals"].iterrows():
            price_parts[str(m["name"])] = {
                "terrestrial": float(m["terrestrial_price_usd_per_kg"]),
                "utility": float(m["in_space_utility"]),
                "downleg": float(m["downleg_cost_usd_per_kg"]),
                "refining": float(m["in_space_processing_usd_per_kg"]),
                "route": str(m["value_route"]),
                "delivered": float(m["price_usd_per_kg"]),
            }
    return dict(
        cfg=cfg, body=body, veh=veh, pro=pro, ops=ops, val=val,
        minerals=tables["minerals"], legs=legs, price_parts=price_parts,
        physics=PHYSICS,
        leo_usd_per_kg=master._LEO_USD_PER_KG,
        p_l=master.delivered_cost_usd_per_kg(cfg.delivery_destination),
        a_au=a_au, e=float(body["eccentricity"]),
        inc=float(body["inclination_deg"]),
        rho=float(body["density_gcm3"]),
        H=float(body["absolute_magnitude_h"]),
        albedo=float(body["albedo_assumed_for_diameter"]),
        # None when the catalog has no measurement, which is what sends
        # `derive_body` down the H-and-albedo route.
        d_measured=(None if "diameter_km" not in body
                    or pd.isna(body["diameter_km"])
                    else float(body["diameter_km"])),
        # ⚠️  WHERE THE DIAMETER CAME FROM IS A STAGE 1 QUESTION, AND THE
        # COLUMN THAT ANSWERS IT IS NOT `diameter_km`.  Stage 1 writes its own
        # H-and-albedo derivation back INTO `diameter_km`, so that column is
        # populated on every row and `derive_body` takes the measured branch
        # on every body -- which is correct arithmetic and a useless answer to
        # "was this measured".  `diameter_source` is the one that knows.  It is
        # carried for the document alone; nothing derived reads it.
        d_source=(str(body["diameter_source"])
                  if "diameter_source" in body
                  and not pd.isna(body["diameter_source"]) else "unknown"),
        # The albedo a reader should be shown, which is NOT the one the
        # fallback derivation reads: `albedo_assumed_for_diameter` is
        # populated only where an albedo had to be assumed, so on a body with
        # a real measurement it is NaN and the page printed "nan".
        albedo_measured=(None if "albedo" not in body
                         or pd.isna(body["albedo"])
                         else float(body["albedo"])),
        isp=float(pro["isp_vac_s"]),
        ve=float(pro["isp_vac_s"]) * G0,
        dv_penalty=float(pro["dv_penalty_factor"]),
        # Module 3 tags an electric propellant with a delta-v penalty above 1,
        # which is what the model itself tests, so this is the same question
        # asked of the same column rather than a name test on the row.
        electric=shape["electric"],
        isru=shape["isru"],
        power_source=shape["power"],
        # 🚨  THE PROCESSING PLANT AND THE EP ARRAY DO NOT SHARE A FIGURE.
        # The plant stands on a rotating body and spends about half its time in
        # shadow, so it is the eclipse-derated one; a radioisotope source is
        # flat at about 5 W/kg wherever it is and takes neither the 1/r^2 nor
        # the night-side penalty.
        plant_w_per_kg=(val("RTG specific power") if shape["power"] == "rtg"
                        else w_plant),
        plant_usd_per_w=val("RTG (radioisotope power)" if shape["power"] == "rtg"
                            else "Power system (solar + battery)"),
        boiloff_pct=float(pro.get("boiloff_pct_per_day") or 0.0),
        # 🚨  THE PRICE THE RUN PAID, WHICH IS NOT ALWAYS THE PRICE ON
        # DISK.  Read off the row like every other term the run settled; see
        # `run_propellant_price`.  `prop_moved` is the table's own figure when
        # the two disagree, and None when they do not, so the run can say so.
        prop_usd_per_kg=prop_usd_per_kg, prop_moved=prop_moved,
        tank_frac=tank_frac,
        leo_cap=float(veh["payload_leo_kg"]),
        fairing_m3=float(veh["fairing_volume_m3"]),
        thruster_eff=float(pro["thruster_efficiency"]),
        thruster_kg_per_n=float(pro["thruster_kg_per_n"]),
        ppu_kg_per_kw=val("Power processing unit specific mass",
                          used=shape["electric"]),
        w_bare=w_bare, w_plant=w_plant, oversize=oversize, dark_h=dark_h,
        rot_h=rot_h, rot_measured=rot_measured, dark_clamped=dark_clamped,
        max_dark_h=cfg.max_dark_period_h,
        # Read off the ROW, like every other architecture choice: these are
        # what the search settled on, not what this derivation decided.
        thrust_scaling=(str(archived["thrust_scaling"])
                        if "thrust_scaling" in archived
                        and not pd.isna(archived["thrust_scaling"])
                        else "unknown"),
        storage_class=str(pro.get("storage_class")
                          or pro.get("propellant_storage_class") or "unknown"),
        arch_label=(str(archived["delivery_arch"])
                    if "delivery_arch" in archived
                    and not pd.isna(archived["delivery_arch"]) else ""),
        comp_group=(str(archived["comp_group"])
                    if "comp_group" in archived
                    and not pd.isna(archived["comp_group"]) else ""),
        # The 1 AU rating the 1/r^2 derating starts from, and the three storage
        # figures the night-side oversize is computed against.  All four are
        # Module 3 rows the page consumed silently: an oversize factor with
        # none of its inputs beside it is a number asking to be trusted.
        w_1au=val("Power system specific mass"),
        # 🚨  BOTH RATES ON EVERY ROW, NOT JUST THE ONE THIS MISSION FLEW.
        # `plant_w_per_kg` above is whichever source won, so the page could
        # say what this plant manages and not why the model chose it.  The
        # crossover distance is the whole argument -- solar falls as 1/r^2
        # and a radioisotope source does not, so they cross at
        # sqrt(w_solar / w_rtg) -- and it was TYPED into the prose as "3.46
        # AU", three releases away from either number it is made of.
        rtg_w_per_kg=val("RTG specific power"),
        dark_frac=val("Eclipse / night-side dark fraction") if eclipse_on else 0.0,
        storage_wh_per_kg=val("Energy storage usable specific energy"),
        storage_eff=val("Energy storage round-trip efficiency"),
        baseline_dark_h=val("Power-system row baseline dark period"),
        dig_wh=val("Drilling / excavation energy"),
        benef_wh=val("Beneficiation / on-site processing energy"),
        water_wh=val("Water liberation energy (bound water)"),
        contain_per_kg=val("Volatile cargo containment"),
        destination=dest,
        # The interval Module 1's taxonomy fractions actually span, and the
        # classes at each end.  Derived rather than quoted: see the docstring.
        frac_span=taxonomy_fraction_span(),
        # Which return leg this row flew.  Aerocapture is a TRADE rather than a
        # saving: it buys dv with a heat shield massing a fraction of the
        # returned stack, hauled out from Earth as dead mass and pushed back
        # through the return burn.  For a slow-arriving target the dv it saves
        # is small and the shield is not worth carrying, which is why the model
        # prices both and this reads which one won.
        # The architecture declares which leg each mode flies, so this reads
        # the table rather than assembling a name and hoping it exists.  A
        # destination with no atmosphere has no aero leg at all, and a row that
        # claimed one there would index None and fail loudly.
        return_leg=(arch["aero_leg"] if shape["aero"] else arch["prop_leg"]),
        tps_frac=(cfg.heat_shield_frac_of_payload if shape["aero"] else 0.0),
        arch=arch,
        # 🚨  THREE COST LINES ARE DECIDED BY THE DESTINATION, NOT BY THE
        # MISSION, and getting any of them from the wrong branch moves the
        # answer by more than most model terms do.  The vehicle that meets the
        # cargo is a $200k/kg LANDER at a surface base, a $150k/kg guided
        # re-entry capsule if it comes home, and a $60k/kg passive berthing
        # adapter at a depot.  An Earth return also pays a $15M recovery
        # campaign and the full launch-and-re-entry licence, where an in-space
        # delivery pays $2M of depot handover and the launch-only one.
        capsule_per_kg=val("Surface lander recurring cost"
                           if arch.get("needs_lander")
                           else "Return capsule recurring cost"
                           if arch["returns_to_earth"]
                           else "Berthing adapter recurring cost"),
        recovery_usd=val("Sample recovery operations"
                         if arch["returns_to_earth"]
                         else "Depot berthing & handover operations"),
        licensing_usd=val("FAA Part 450 licensing compliance"
                          if arch["returns_to_earth"]
                          else "FAA Part 450 licensing (launch only)"),
        tps_per_kg=val("Heat shield / TPS for Earth return"),
        beneficiated=benef,
        # A body property, resolved once: the raw branch of the cargo-water
        # question reads it directly.  Absent or NaN means no ice at all.
        ice_frac=ice_frac,
        # 🚨  WHAT A MISSION CAN MAKE ITS OWN PROPELLANT FROM IS A FACT ABOUT
        # THE PROPELLANT *AND* THE BODY, which is why it cannot be a config
        # flag.  Two feed materials exist.  "water" states water per kilogram
        # of propellant, so the REGOLITH to dig is that divided by the body's
        # ice fraction and the separation recovery -- a dry body therefore
        # cannot make hydrolox at any price.  "regolith" means the propellant
        # IS bulk rock, a mass driver's reaction mass, so the ratio is already
        # regolith per kilogram and no water is needed at all.
        isru_feed_per_kg_prop=isru_feed_per_kg,
        isru_water_per_kg_prop=isru_water_per_kg,
        # ⚠️  `model_rig_trip_limit` OFF LEAVES THE CALENDAR BOUND ALONE AND
        # DROPS THE DUTY-CYCLE ONE, and the row shows it: `trips_per_ship`
        # above Module 3's own maximum can only mean the cap was not applied.
        # Where the calendar binds first the two readings agree, so this is
        # inert exactly where it cannot be checked.
        rig_trip_limit=rig_trip_limit,
        # 🚨  `model_launch_windows` OFF IS NOT A SMALL DIAL.  The wait is half
        # a synodic period, which at Mars is over a year, and it lands in the
        # STAY -- so a derivation that adds one the run did not lengthens the
        # mission, can push it past `max_mission_duration_yr`, and then reports
        # that no concentration ratio closes a mission on a body that closes
        # fine.  A synodic period is never zero, so a zero wait in the row can
        # only mean the term was off.
        windows=windows_on,
        recovery=cfg.beneficiation_recovery,
        rate_kg_yr=cfg.mining_hardware_kg
        * cfg.mining_rate_kg_per_day_per_kg_rig * 365.25,
    )


def delivery_chain(C):
    """The launch cost avoided, leg by leg, with every stage's own arithmetic.

    This is where an in-space price comes from and it had been READ off
    `master` as a single number.  Reading it is not wrong; printing it is,
    because `p_L` is the largest term in every delivered price on the page and
    the document's whole claim is that its figures are derived rather than
    quoted.  So the chain is walked here as Module 2 walks it -- backwards from
    the payload, each leg multiplying up the mass the one above it demands --
    and the answer is compared against Module 2's own at the end.

        R  = exp(dv / (Isp g0))          rocket equation
        d  = delta (R - 1) / (1 - delta R)   stage dry mass per kg of payload
        m0 = R (1 + d)                   mass at the start of the leg

    An `edl` leg DIVIDES rather than multiplying: surviving 30% of entry mass
    means arriving with 1/0.30 kg for every kilogram that lands.

    🚨  AN EMPTY CHAIN IS NOT A MISSING ONE, AND `if C["legs"]`
    READ THEM AS THE SAME THING.  Module 2 distinguishes them by identity:
    `earth_surface` maps to None and avoids no launch at all, while `leo` maps
    to `[]` -- nothing to fly ABOVE LEO, and the launch TO LEO avoided in full.
    Walking an empty chain leaves the mass at 1.0, so the price is the
    LEO $/kg itself, which is why Module 2 returns 4,253 where this returned
    zero.  Found by `--sweep`, on the first `leo` mission this derivation had
    ever been pointed at: it is the model's most-used in-space destination and
    the assertion at the end of `build` refused every one of them.
    """
    mass, steps = 1.0, []
    for leg in reversed(C["legs"] or []):
        before = mass
        if leg[0] == "edl":
            frac = float(leg[1])
            mass = mass / frac if frac > 0 else float("inf")
            steps.append({"kind": "edl", "surviving": frac, "before": before,
                          "after": mass})
            continue
        _kind, dv, isp, dry = leg
        r = math.exp(float(dv) / (float(isp) * G0))
        d = dry * (r - 1.0) / (1.0 - dry * r) if dry * r < 1.0 else float("inf")
        m0 = r * (1.0 + d)
        mass *= m0
        steps.append({"kind": "burn", "dv": float(dv), "isp": float(isp),
                      "dry": float(dry), "ve": float(isp) * G0, "R": r, "d": d,
                      "m0": m0, "before": before, "after": mass})
    return {"steps": steps, "kg_in_leo": mass,
            "usd_per_kg": (C["leo_usd_per_kg"] * mass
                           if C["legs"] is not None else 0.0)}


def derive_body(C):
    """Diameter, then the mass of a sphere of that size.

    🚨  A MEASURED DIAMETER WINS, and deriving one anyway is not a harmless
    second opinion.  `albedo_assumed_for_diameter` is only populated when an
    albedo had to be ASSUMED, so on a body that already has a measurement it
    is NaN, and the H-and-albedo route silently produces a NaN diameter, a NaN
    mass and a NaN mineable mass.  Nothing raises: the cascade simply fails
    every comparison it makes and the sweep reports that no concentration
    ratio closes, which is a true sentence about a body that closes fine.
    """
    measured = C.get("d_measured")
    if measured is not None and measured > 0:
        d_km, route = measured, "measured"
    else:
        d_km = 1329.0 / math.sqrt(C["albedo"]) * 10.0 ** (-C["H"] / 5.0)
        route = "derived from H and albedo"
    r_m = d_km / 2.0 * 1000.0
    vol = 4.0 / 3.0 * math.pi * r_m ** 3
    mass = C["rho"] * 1000.0 * vol
    return dict(d_km=d_km, r_m=r_m, r3=r_m ** 3, vol=vol, mass=mass,
                diameter_route=route, diameter_source=C.get("d_source"),
                mineable=C["cfg"].max_mining_fraction * mass)


def _geo_capture(v_inf):
    """Propulsive capture into GEO, whichever of two routes is cheaper.

    Unlike the cislunar case NEITHER ALWAYS WINS, so both are priced:

      direct  meet GEO at its own radius and kill the hyperbolic excess and
              the plane change together, out where orbital speed is low.
              Cheap when the spacecraft arrives slowly.
      Oberth  capture at LEO perigee into a GTO-shaped ellipse, taking the
              benefit deep in the well, then circularise at apogee.  The
              perigee burn is efficient; the apogee burn is fixed however the
              spacecraft got there, which is why this route does not always
              win.

    That fixed apogee burn is the difference from a cislunar depot, which is
    captured into by BINDING an ellipse at 450 m/s.  GEO has to be
    CIRCULARISED into, which costs four times as much and does not fall with
    arrival speed.
    """
    direct = circularise_at_geo(math.sqrt(V_ESC_GEO ** 2 + v_inf ** 2))
    oberth = ((math.sqrt(V_ESC_LEO ** 2 + v_inf ** 2) - V_GTO_PERIGEE)
              + DV_GTO_APOGEE_TO_GEO)
    return direct if direct < oberth else oberth


def _mars_legs(C, r_target):
    """The Mars return legs, which are a different journey and not a discount.

    DELIVERING TO MARS DOES NOT GO NEAR EARTH, so none of the Earth-side
    arithmetic applies to the return half. The heliocentric transfer runs from
    the asteroid's apsis to Mars' orbit, so the departure burn, the arrival
    v_infinity and the capture are three different numbers, and the apsis match
    burn that every Earth return pays does not appear at all. Approximating
    this off the Earth legs would erase the whole point: a main-belt body can
    be CHEAPER to deliver to Mars than to Earth.

    Returns None where the geometry does not close, which is what the
    destination's absence from the leg set then means.
    """
    a_t = (r_target + A_MARS_AU) / 2.0
    v_t_at_ast_sq = 2.0 / r_target - 1.0 / a_t
    v_ast_sq = 2.0 / r_target - 1.0 / C["a_au"]
    v_t_at_mars_sq = 2.0 / A_MARS_AU - 1.0 / a_t
    if min(v_t_at_ast_sq, v_ast_sq, v_t_at_mars_sq) <= 0:
        return None
    cos_i = math.cos(math.radians(C["inc"]))
    dv_dep_sq = (v_t_at_ast_sq + v_ast_sq
                 - 2.0 * math.sqrt(v_t_at_ast_sq * v_ast_sq) * cos_i)
    depart = math.sqrt(max(dv_dep_sq, 0.0)) * V_EARTH
    v_mars = math.sqrt(1.0 / A_MARS_AU)
    v_inf_mars = abs(math.sqrt(v_t_at_mars_sq) - v_mars) * V_EARTH
    v_circ = math.sqrt(MU_MARS / R_MARS_PARK)
    v_esc = math.sqrt(2.0) * v_circ
    capture = math.sqrt(v_esc ** 2 + v_inf_mars ** 2) - v_circ
    capture_1sol = (math.sqrt(V_ESC_MARS_1SOL ** 2 + v_inf_mars ** 2)
                    - V_ELL_MARS_1SOL)
    return dict(
        v_inf_mars=v_inf_mars, mars_depart=depart,
        mars_capture=capture, mars_capture_1sol=capture_1sol,
        # The atmosphere absorbs the capture and most of the descent, leaving
        # terminal retropropulsion; paid for in heat-shield mass instead.
        ret_mars_surface_aero=depart + DV_MARS_RETROPROP,
        # All-propulsive: capture into low Mars orbit, then fly a lander down
        # against gravity with no help at all.  Brutal, and the reason nobody
        # plans a Mars mission this way.
        ret_mars_surface_prop=depart + capture + DV_MARS_POWERED_DESCENT,
        # A depot: nothing lands, so neither descent term applies.
        ret_mars_orbit_prop=depart + capture_1sol,
        # Aerocapture into the 1-sol ellipse and then a periapsis raise, which
        # Odyssey and MRO both flew.  Charged at the Earth aerobrake trim,
        # which is conservative here and far inside the departure burn's noise.
        ret_mars_orbit_aero=depart + DV_AEROBRAKE_TRIM,
        # What each Mars leg is MADE OF, for the document.  Nothing reads this
        # but the page; it is here rather than there because a breakdown
        # assembled beside the prose is a second opinion about the arithmetic,
        # and the two would drift the first time a leg changed.
        arrival={
            "ret_mars_surface_aero": [
                ("asteroid departure for Mars, plane change included", depart),
                ("terminal retropropulsion after aeroentry",
                 DV_MARS_RETROPROP)],
            "ret_mars_surface_prop": [
                ("asteroid departure for Mars, plane change included", depart),
                ("capture into low Mars orbit", capture),
                ("powered descent with no atmospheric help",
                 DV_MARS_POWERED_DESCENT)],
            "ret_mars_orbit_prop": [
                ("asteroid departure for Mars, plane change included", depart),
                ("capture into the 1-sol depot ellipse", capture_1sol)],
            "ret_mars_orbit_aero": [
                ("asteroid departure for Mars, plane change included", depart),
                ("periapsis raise out of the atmosphere",
                 DV_AEROBRAKE_TRIM)],
        },
    )


def _legs(C, r_target):
    """Departure and arrival legs for a rendezvous at one apsis.

    The outbound half is the same wherever the cargo is going: an ellipse from
    Earth's orbit out to the apsis, and a burn to match the target there.  What
    differs by destination is entirely what happens on ARRIVAL, and it differs
    by more than intuition suggests.  Every return leg this function can price
    is returned; `derive_dv` picks the one the row actually flew.

        cislunar, propulsive   capture only has to BIND the orbit, and the
                               burn takes the Oberth benefit at low perigee
        lunar surface          that capture, then NRHO to LLO to the ground,
                               entirely propulsive because there is no air
        LEO, propulsive        the deepest Earth destination, so it kills the
                               escape velocity as well as the excess
        LEO, aerobraked        drag does the whole job bar a 100 m/s trim
        GEO                    two capture geometries, neither always cheaper
        earth surface, aero    direct entry: no capture burn AT ALL, the
                               arrival energy goes into a heat shield
        earth surface, prop    capture into LEO, then a deorbit burn
        Mars, either depot     a separate heliocentric transfer; see
                               `_mars_legs`, which shares none of this

    The keys are the model's own leg names, so `derive_dv` can index them with
    the same `ret_<destination>_<mode>` string the delivery architecture
    declares.  Spelling them any other way would need a translation table, and
    a translation table is a second opinion about which leg is which.
    """
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
    # Capture into LEO is the expensive one: it kills the escape velocity as
    # well as the hyperbolic excess.  It is the departure burn run backwards,
    # which is why one expression serves both.
    leo_capture = v_hyp - v_leo
    cislunar_capture = max(0.0, v_hyp - v_ell) + DV_NRHO
    geo_capture = _geo_capture(v_inf)
    legs = dict(a_t=a_t, v_t=v_t, cos_i=cos_i, v_inf_sq=v_inf_sq,
                v_inf_canon=math.sqrt(max(v_inf_sq, 0.0)), v_inf=v_inf,
                v_leo=v_leo, v_esc=v_esc, v_hyp=v_hyp, a_ell=a_ell,
                v_ell=v_ell, v_ast=math.sqrt(2.0 / r_target - 1.0 / C["a_au"]),
                v_tr=math.sqrt(2.0 / r_target - 1.0 / a_t),
                match=match, depart=v_hyp - v_leo,
                out=v_hyp - v_leo + match,
                leo_capture=leo_capture, geo_capture=geo_capture,
                cap=cislunar_capture,
                ret_cislunar_prop=match + cislunar_capture,
                ret_lunar_surface_prop=(match + cislunar_capture
                                        + DV_NRHO_TO_LUNAR_SURFACE),
                ret_leo_prop=match + leo_capture,
                ret_leo_aero=match + DV_AEROBRAKE_TRIM,
                ret_geo_prop=match + geo_capture,
                ret_geo_aero=match + DV_GEO_AEROCAPTURE_ARRIVAL,
                ret_earth_surface_aero=match,
                ret_earth_surface_prop=match + leo_capture + DV_LEO_DEORBIT)
    legs["arrival"] = {
        "ret_cislunar_prop": [
            ("asteroid departure, apsis match burn", match),
            ("capture: bind the orbit at low perigee, then NRHO insertion",
             cislunar_capture)],
        "ret_lunar_surface_prop": [
            ("asteroid departure, apsis match burn", match),
            ("cislunar capture", cislunar_capture),
            ("NRHO to low lunar orbit to the surface, all propulsive",
             DV_NRHO_TO_LUNAR_SURFACE)],
        "ret_leo_prop": [
            ("asteroid departure, apsis match burn", match),
            ("capture into LEO: the escape velocity as well as the excess",
             leo_capture)],
        "ret_leo_aero": [
            ("asteroid departure, apsis match burn", match),
            ("periapsis-raise trim after aerobraking", DV_AEROBRAKE_TRIM)],
        "ret_geo_prop": [
            ("asteroid departure, apsis match burn", match),
            ("capture into GEO, cheaper of the direct and Oberth routes",
             geo_capture)],
        "ret_geo_aero": [
            ("asteroid departure, apsis match burn", match),
            ("circularise at GEO after aerocapture",
             DV_GEO_AEROCAPTURE_ARRIVAL)],
        "ret_earth_surface_aero": [
            ("asteroid departure, apsis match burn", match)],
        "ret_earth_surface_prop": [
            ("asteroid departure, apsis match burn", match),
            ("capture into LEO", leo_capture),
            ("deorbit burn: the capsule still has to come down",
             DV_LEO_DEORBIT)],
    }
    mars = _mars_legs(C, r_target)
    if mars is not None:
        arrival = dict(legs["arrival"])
        arrival.update(mars.pop("arrival"))
        legs.update(mars)
        legs["arrival"] = arrival
    return legs


def derive_dv(C):
    """Two-impulse patched conic at both apsides; the cheaper round trip wins.

    ⚠️  THE APSIS IS RESOLVED AGAINST THE ROUND TRIP ACTUALLY BEING FLOWN, not
    against a fixed Earth return.  The outbound leg is the same either way but
    the return is not, so a geometry that is poor for one destination or one
    return mode can be the best for another, and resolving it once for all of
    them would quietly fly the wrong transfer.
    """
    q_au = C["a_au"] * (1.0 - C["e"])
    big_q = C["a_au"] * (1.0 + C["e"])
    aph, peri = _legs(C, big_q), _legs(C, q_au)
    lam = C["dv_penalty"]
    key = C["return_leg"]
    ceiling = C["cfg"].max_dv_outbound_m_s

    def bounded(km_s, floor):
        """One leg in m/s, floored and clamped BEFORE the low-thrust penalty.

        🚨  THE ORDER IS LOAD-BEARING.  The model floors the raw leg at 3,000
        m/s outbound and 300 m/s on the return and THEN multiplies by the
        electric penalty, so a body whose return leg is under the floor comes
        out at 300 x lambda and not at its own value x lambda.  Applying the
        penalty first and never flooring gave 332.8 m/s where the row says
        450.0, which is exactly 300 x 1.5 -- a body cheap enough to arrive at
        that the floor is the whole answer.
        """
        return min(max(km_s * 1000.0, floor), ceiling)

    rounds = {"aphelion": bounded(aph["out"], 3000.0) + bounded(aph[key], 300.0),
              "perihelion": (bounded(peri["out"], 3000.0)
                             + bounded(peri[key], 300.0))}
    chosen = aph if rounds["aphelion"] <= rounds["perihelion"] else peri
    return dict(q_au=q_au, Q_au=big_q, aph=aph, peri=peri,
                apsis=("aphelion" if chosen is aph else "perihelion"),
                aph_round=rounds["aphelion"] / 1000.0,
                peri_round=rounds["perihelion"] / 1000.0,
                # The three terms between a geometry and a flown leg, reported
                # so the page can show them IN ORDER.  Floor first, then the
                # penalty: a body cheap enough to arrive at pays the floor
                # times the penalty rather than its own value times it, and a
                # document that showed only the product could not say which.
                floor_out=3000.0, floor_ret=300.0, ceiling=ceiling,
                penalty=lam, r_target=(big_q if chosen is aph else q_au),
                raw_out=chosen["out"] * 1000.0,
                raw_ret=chosen[key] * 1000.0,
                floored_out=bounded(chosen["out"], 3000.0),
                floored_ret=bounded(chosen[key], 300.0),
                dv_out=lam * bounded(chosen["out"], 3000.0),
                dv_ret=lam * bounded(chosen[key], 300.0))


# ------------------------------------------------------- the mass cascade
def _ratios(C, dv_out, dv_ret):
    """Mass ratios and tankage closures for one pair of delta-vs.

    Rebuilt per pass rather than once, because boil-off makes the RETURN ratio
    a function of how long the propellant sits in the tank, and that depends on
    the stay, which depends on the payload the ratio is being solved for.

    `k = 1/(1 - t(R - 1))` is the cost of carrying your own tank, and k growing
    without bound is the tank failing to close: infeasible rather than merely
    expensive, which is the same condition Module 2 hits on delta*R >= 1.
    """
    t = C["tank_frac"]
    r_out = math.exp(dv_out / C["ve"])
    r_ret = math.exp(dv_ret / C["ve"])
    if t * (r_ret - 1.0) >= 1.0 or t * (r_out - 1.0) >= 1.0:
        return None
    k_out = 1.0 / (1.0 - t * (r_out - 1.0))
    k_ret = 1.0 / (1.0 - t * (r_ret - 1.0))
    return {"t": t, "R_out": r_out, "R_ret": r_ret,
            "k_out": k_out, "k_ret": k_ret,
            "budget": C["leo_cap"] / (k_out * r_out)}


def _cascade(C, R, hardware_kg, struct_frac):
    """The closed-form payload solve, at one hardware mass and one f.

    Working backward from arrival, with the return tank inside the post-burn
    mass and the outbound tank staged at the asteroid.

    TWO FORMS, AND THE DIFFERENCE IS ONE FACTOR OF R_ret.  Carrying the return
    propellant up from Earth means it is pushed through the outbound burn as
    dead mass, so it appears multiplied by the outbound mass ratio; making it
    at the asteroid means it never rides the outbound leg at all.  What does
    NOT drop out under ISRU is the return TANK: you can make propellant out
    there, not a pressure vessel, so the empty tank is launched either way.
    """
    t, k_ret, k_out = R["t"], R["k_ret"], R["k_out"]
    d0 = C["cfg"].return_vehicle_dry_kg
    # s = 1 + tps_frac, and it multiplies the WHOLE returned stack rather than
    # adding to the structure fraction: the heat shield is sized on the payload
    # AND the dry return mass, because it is what the two of them arrive
    # behind.  At tps_frac = 0 it is exactly 1.0 and not one float below
    # differs from the propulsive case.
    s_tps = 1.0 + C["tps_frac"]
    if C["isru"]:
        denom = k_ret * s_tps * (1.0 + struct_frac) - 1.0
        bracket = R["budget"] - hardware_kg - k_ret * s_tps * d0
        if denom <= 0 or bracket <= 0:
            return None
        m_pay = bracket / denom
        dry = m_pay * (1.0 + struct_frac) + d0
        m_tps = C["tps_frac"] * dry
        m_after = k_ret * s_tps * dry
        m_rprop = m_after * (R["R_ret"] - 1.0)
        # The propellant is made there, so only the tank and the dry stack ride
        # the outbound leg.
        m_at = hardware_kg + d0 + struct_frac * m_pay + m_tps + t * m_rprop
    else:
        denom = k_ret * R["R_ret"] * (1.0 + struct_frac) * s_tps - 1.0
        bracket = R["budget"] - hardware_kg - k_ret * d0 * R["R_ret"] * s_tps
        if denom <= 0 or bracket <= 0:
            return None
        m_pay = bracket / denom
        dry = m_pay * (1.0 + struct_frac) + d0
        m_tps = C["tps_frac"] * dry
        m_after = k_ret * s_tps * dry
        m_rprop = m_after * (R["R_ret"] - 1.0)
        m_at = (hardware_kg + d0 + struct_frac * m_pay + m_tps
                + t * m_rprop + m_rprop)
    m_oprop = m_at * k_out * (R["R_out"] - 1.0)
    # The one coefficient both branches turn on, reported rather than left for
    # a reader to reassemble.  `coef` is what multiplies the returning stack:
    # k_ret * s_tps, times R_ret when the return propellant is carried up from
    # Earth and not when it is made on site.  denom and bracket are then one
    # expression each in it, which is what makes the two branches one solve
    # rather than two, and it is the line the document shows.
    return dict(m_pay=m_pay, denom=denom, bracket=bracket, m_after=m_after,
                m_rprop=m_rprop, m_at=m_at, m_oprop=m_oprop, m_tps=m_tps,
                m_prop=m_oprop + m_rprop, s_tps=s_tps, d0=d0,
                struct_frac=struct_frac, hardware_kg=hardware_kg,
                coef=(k_ret * s_tps if C["isru"]
                      else k_ret * s_tps * R["R_ret"]))


def _ep_stage(C, m_prop):
    """Array, PPU and thruster for a stage that burns `m_prop` in t_burn.

    Three masses on two different quantities.  The array and the PPU scale with
    POWER; the thruster scales with THRUST, which owes nothing to efficiency,
    and that is the constraint a per-kW figure cannot express.

    All zero on a chemical stage.  A chemical mission flies impulsive burns, so
    there is no thrust time to size for and no power train to carry, and the
    zeros are what make the two shapes one code path rather than two.
    """
    if not C["electric"] or m_prop <= 0:
        return dict(power=0.0, thrust=0.0, array=0.0, ppu=0.0, thruster=0.0,
                    mass=0.0, thrust_yr=0.0)
    seconds = C["cfg"].ep_target_thrust_yr * 365.25 * 24.0 * 3600.0
    power = m_prop * C["ve"] ** 2 / (2.0 * C["thruster_eff"] * seconds)
    thrust = m_prop * C["ve"] / seconds
    # ⚠️  THE EP ARRAY TAKES THE BARE 1/r^2 FIGURE AND NOT THE ECLIPSE-DERATED
    # ONE.  It is in interplanetary cruise, in permanent sunlight; the
    # PROCESSING plant is the one standing in the body's shadow.  Using the
    # derated figure here would roughly double the array on every electric
    # mission in the model.
    array = power / C["w_bare"]
    ppu = power / 1000.0 * C["ppu_kg_per_kw"]
    thruster = thrust * C["thruster_kg_per_n"]
    return dict(power=power, thrust=thrust, array=array, ppu=ppu,
                thruster=thruster, mass=array + ppu + thruster,
                thrust_yr=C["cfg"].ep_target_thrust_yr)


# The last guard the cascade refused on, for the message when every rung fails.
# Recorded rather than returned, so that `return None` stays one word at each
# of the nine sites that use it: a cascade that reported its own reason through
# its return value would have to be unpacked by every caller of every rung.
REFUSAL = []


def refuse(reason):
    """Record why the cascade could not close, and return the None it returns.

    🚨  THE MESSAGE WAS ABOUT THE WRONG THING.  When no rung of
    the ratio ladder closed, the derivation said "no concentration ratio closes
    a mission on this body" -- on a RAW row, where no ratio is involved and
    what actually refused was the launch stack against the vehicle's capacity.
    A refusal that names the wrong constraint sends the next reader to the
    wrong file.
    """
    REFUSAL.append(reason)
    return None


def mass_and_clock(C, B, DV, ratio):
    """The coupled sizing loop, then the mission actually flown.

    Seven quantities in one ring: payload sets the feed, the feed sets the dig
    and the power, the power sets the array, the array is hardware, and hardware
    comes out of the payload; and separately the payload sets the water in the
    hold, which sets the sealed containment, which is payload-proportional and
    so folds into f.  ISRU adds an eighth, because propellant made on site is
    rock the same rig has to dig before any ore, and boil-off a ninth, because
    the stay decides how much of the return propellant is still there.  Fixed-
    point iteration solves the ring rather than assuming any leg of it away.

    TWO THINGS THE MODEL DOES THAT LOOK LIKE OVERSIGHTS AND ARE NOT, and both
    have to be reproduced or the launch mass comes out over the vehicle.  The
    cascade is NOT re-solved once the loop converges: the payload carried
    forward is the last one solved INSIDE the loop, at the previous pass's
    hardware.  And the electric stage is never re-sized after that either, so it
    is sized on a propellant load a couple of kilograms above the one the
    settled stack flies.  Only the plant, the seal and the ISRU books are
    settled.
    """
    cfg = C["cfg"]
    isru = C["isru"]
    # 🚨  ISRU IS EXEMPT FROM BOIL-OFF, and not as a kindness: the propellant
    # is made at the asteroid on departure rather than held in a tank from
    # launch, so there is no hold time for it to boil away over.
    models_boiloff = (cfg.model_propellant_boiloff and C["boiloff_pct"] > 0
                      and not isru)
    outbound_yr = max(0.5, TAU_CRUISE_FIT_YR_PER_M_S * DV["dv_out"])
    throughput = C["rate_kg_yr"] * cfg.max_mining_duration_yr
    phases = C["phases"]
    plant_kg = ep_kg = 0.0
    isru_feed = isru_prop = 0.0
    struct = cfg.return_structure_frac_of_payload
    # 🚨  THE STAY IS IN THE CONVERGENCE TEST, AND LEAVING IT OUT COSTS A PASS.
    # It feeds nothing else unless the propellant boils off, so it reads like a
    # term that cannot matter -- and it does not matter to any VALUE, only to
    # WHEN the loop stops.  The model carries the last in-loop cascade rather
    # than re-solving at the settled hardware, so a loop that breaks one pass
    # early carries a different payload, and every mass downstream of it moves
    # by about a tenth of a percent.  Cislunar happened to agree;
    # `earth_surface` came out 0.06% over the vehicle and the cascade correctly
    # refused a mission the model flies.  Initialised exactly as the model
    # does, at the floor plus the wait.
    stay_est = cfg.station_keeping_floor_yr + DV["window_wait"]
    dv_ret_eff = DV["dv_ret"]
    boiloff_factor = 1.0
    passes, cas, ep, R = [], None, None, None

    for i in range(12):
        if models_boiloff:
            # Folded into an EFFECTIVE return delta-v rather than bolted onto
            # the cascade: m_return_prop scales with (R_ret - 1), so inflating
            # that term by the boil-off factor is exactly
            # R_eff = 1 + (R_ret - 1) * k, and the closed form is untouched.
            hold_yr = outbound_yr + stay_est
            boiloff_factor = math.exp(C["boiloff_pct"] / 100.0 * hold_yr * 365.25)
            r_ret_raw = math.exp(DV["dv_ret"] / C["ve"])
            dv_ret_eff = C["ve"] * math.log(1.0 + (r_ret_raw - 1.0) * boiloff_factor)
        R = _ratios(C, DV["dv_out"], dv_ret_eff)
        if R is None:
            return refuse("the tank cannot close: delta (R - 1) >= 1 on this propellant")
        hw_in = cfg.mining_hardware_kg + plant_kg + ep_kg
        cas = _cascade(C, R, hw_in, struct)
        if cas is None:
            return refuse("the mass cascade does not converge at this hardware mass")
        ep = _ep_stage(C, cas["m_prop"])
        trial_pay = min(cas["m_pay"], B["mineable"],
                        max(0.0, throughput - isru_feed))
        if trial_pay <= 0:
            return refuse("no payload is left once the rig, the plant and the feed are paid")
        new_isru_prop = new_isru_feed = 0.0
        if isru:
            # Propellant made on site is dug before it is burnt, so it takes
            # its share of the rig's throughput ahead of any ore.  A rig that
            # cannot dig its own fuel in the time allowed does not fly.
            new_isru_prop = ((trial_pay + cfg.return_vehicle_dry_kg
                              + struct * trial_pay)
                             * (1.0 + C["tps_frac"]) * (R["R_ret"] - 1.0))
            new_isru_feed = new_isru_prop * C["isru_feed_per_kg_prop"]
            if new_isru_feed >= throughput or new_isru_feed >= B["mineable"]:
                return refuse("the ISRU feed alone exceeds what the rig can dig or the body allows")
        # A raw mission digs exactly what it flies: there is no feed above
        # the payload, so no ratio, and the hold is the body's own mix.
        trial_feed = (min(trial_pay * ratio,
                          max(0.0, throughput - new_isru_feed),
                          max(0.0, B["mineable"] - new_isru_feed))
                      if C["beneficiated"] else trial_pay)
        trial_dig = max((trial_feed + new_isru_feed) / C["rate_kg_yr"],
                        cfg.station_keeping_floor_yr)
        # 🚨  RAW WATER IS THE BODY'S ICE FRACTION, NOT THE HOLD'S WATER PHASE.
        # Concentrating lets the knapsack decide how much water to carry, and
        # it will leave water behind for a denser-value phase; not
        # concentrating means the cargo IS the body's composition, so the ice
        # fraction applies directly.  Deriving it from the phase mix instead
        # gave this body a water cargo the model does not fly, and therefore a
        # 194 kg solar plant the model does not launch -- which moved the
        # payload by 0.7% and every cost downstream of it.
        water = (knapsack(trial_pay, trial_feed, phases,
                          C["recovery"])["mix"].get("water", 0.0)
                 if C["beneficiated"] else trial_pay * C["ice_frac"])
        # 🚨  A RAW, NON-ISRU MISSION SIZES NO PLANT FOR ITS DIG.  The model
        # calls `processing_power_w` only when beneficiating or making
        # propellant, so for run-of-mine ore the ONLY thing that can create a
        # draw is water liberation -- and a body with no ice therefore flies no
        # power system at all.  Charging the dig here gave one mission a 194 kg
        # plant the model never launches.  The dig still costs TIME, which is
        # what bounds the payload; it just does not cost watts.
        draw = 0.0
        if C["beneficiated"] or isru:
            draw += (C["dig_wh"] * (trial_feed + new_isru_feed)
                     + (C["benef_wh"] * trial_pay if C["beneficiated"] else 0.0)
                     ) / hours(trial_dig)
        liberated = 0.0
        if cfg.model_water_liberation:
            liberated = (new_isru_prop * C["isru_water_per_kg_prop"]
                         if isru else 0.0) + water
            if liberated > 0:
                draw += C["water_wh"] * liberated / hours(trial_dig)
        # A radioisotope plant is not expensive over the ceiling, it is
        # UNAVAILABLE: DOE produces about 1.5 kg of Pu-238 a year, roughly one
        # flagship RTG for the whole world.
        if C["power_source"] == "rtg" and draw > cfg.rtg_max_power_w:
            return refuse("the radioisotope plant exceeds `rtg_max_power_w`")
        new_plant = draw / C["plant_w_per_kg"] if draw > 0 else 0.0
        new_frac = C["contain_per_kg"] * min(1.0, water / trial_pay)
        new_stay = trial_dig + DV["window_wait"]
        passes.append({"n": i + 1, "hw_in": hw_in, "f_used": struct,
                       "m_pay": cas["m_pay"], "ep": ep["mass"],
                       "plant": new_plant, "feed": trial_feed,
                       "dig": trial_dig, "water": water, "c_frac": new_frac,
                       "stay": new_stay, "isru_feed": new_isru_feed})
        held = struct - cfg.return_structure_frac_of_payload
        # Five tests, in the model's own order and with its own tolerances:
        # three masses and the stay relative at 1%, the containment fraction
        # absolute at 1e-4 because it is a fraction and not a mass.
        settled = (abs(new_plant - plant_kg) <= 0.01 * max(new_plant, 1.0)
                   and abs(ep["mass"] - ep_kg) <= 0.01 * max(ep["mass"], 1.0)
                   and abs(new_isru_feed - isru_feed) <= 0.01 * max(new_isru_feed, 1.0)
                   and abs(new_stay - stay_est) <= 0.01 * max(new_stay, 1.0)
                   and abs(new_frac - held) <= 1e-4)
        plant_kg, ep_kg = new_plant, ep["mass"]
        isru_feed, isru_prop = new_isru_feed, new_isru_prop
        stay_est = new_stay
        struct = cfg.return_structure_frac_of_payload + new_frac
        if settled:
            break

    # The mission actually flown: the loop's payload, capped by volume, with
    # the plant, the seal and the ISRU books re-settled on it and the stack
    # rebuilt underneath.  Propellant made on site comes off BOTH budgets
    # before any ore is loaded, which is the cost of ISRU and the part a flat
    # $/kg charge left out.
    vol_cap = 0.25 * C["fairing_m3"] * 1000.0 * C["rho"]
    ore_throughput = max(0.0, throughput - isru_feed)
    ore_mineable = max(0.0, B["mineable"] - isru_feed)
    demand = min(cas["m_pay"], ore_mineable)
    # ⚠️  THE THROUGHPUT CAP BOUNDS DIFFERENT THINGS IN THE TWO ORE STATES.
    # Concentrating means the rig digs FEED and flies product, so throughput
    # caps the feed below and not the payload here; not concentrating means the
    # two are the same rock and it caps the payload directly.
    m_pay = (min(demand, vol_cap) if C["beneficiated"]
             else min(demand, vol_cap, ore_throughput))
    if m_pay <= 0:
        return refuse("no payload is left once the rig, the plant and the feed are paid")
    feed = (max(min(m_pay * ratio, ore_throughput, ore_mineable), m_pay)
            if C["beneficiated"] else m_pay)
    load = (knapsack(m_pay, feed, phases, C["recovery"])
            if C["beneficiated"] else raw_hold(m_pay, phases))
    water = (load["mix"].get("water", 0.0) if C["beneficiated"]
             else m_pay * C["ice_frac"])
    c_frac = C["contain_per_kg"] * min(1.0, water / m_pay)
    f_eff = cfg.return_structure_frac_of_payload + c_frac

    d0 = cfg.return_vehicle_dry_kg
    m_dry = d0 + f_eff * m_pay
    # The heat shield is sized on the stack it arrives behind, so it is
    # re-settled here on the payload the mission actually flies, exactly as
    # the plant and the seal are.  Zero on a propulsive return.
    m_tps = C["tps_frac"] * (m_pay + m_dry)
    m_after = R["k_ret"] * (1.0 + C["tps_frac"]) * (m_pay * (1.0 + f_eff) + d0)
    m_rprop = m_after * (R["R_ret"] - 1.0)
    m_tank_ret = R["t"] * m_rprop
    if isru:
        # Settled at the payload actually flown, so the feed and the dig time
        # below describe the same mission the cost model prices.  ⚠️  The
        # re-check is against the rig's WHOLE throughput, not against the ore
        # budget computed above: that budget was netted off the LOOP's estimate
        # of the ISRU feed, and this is the settled one.
        isru_prop = m_rprop
        isru_feed = isru_prop * C["isru_feed_per_kg_prop"]
        if isru_feed + feed > throughput + 1e-6:
            return refuse("the feed exceeds what the rig can dig in the time")
    isru_water = isru_prop * C["isru_water_per_kg_prop"] if isru else 0.0

    dig_yr = max((feed + isru_feed) / C["rate_kg_yr"],
                 cfg.station_keeping_floor_yr)
    draw = 0.0
    if C["beneficiated"] or isru:
        draw += (C["dig_wh"] * (feed + isru_feed)
                 + (C["benef_wh"] * m_pay if C["beneficiated"] else 0.0)
                 ) / hours(dig_yr)
    liberated = isru_water + (water if cfg.model_water_liberation else 0.0)
    if liberated > 0:
        draw += C["water_wh"] * liberated / hours(dig_yr)
    if C["power_source"] == "rtg" and draw > cfg.rtg_max_power_w:
        return refuse("the radioisotope plant exceeds `rtg_max_power_w`")
    plant_kg = draw / C["plant_w_per_kg"] if draw > 0 else 0.0
    hw = cfg.mining_hardware_kg + plant_kg + ep["mass"]

    # Under ISRU only the empty tank rides the outbound leg; the propellant is
    # made at the far end.
    m_at = (hw + m_dry + m_tps + m_tank_ret
            + (0.0 if isru else m_rprop))
    m_oprop = m_at * R["k_out"] * (R["R_out"] - 1.0)
    m_tank_out = R["t"] * m_oprop
    m_launch = m_at + m_tank_out + m_oprop
    if m_launch > C["leo_cap"]:
        return refuse("the launch stack exceeds the vehicle's capacity to LEO")

    stay = dig_yr + DV["window_wait"]
    t_out = max(0.5, TAU_CRUISE_FIT_YR_PER_M_S * DV["dv_out"])
    t_back = max(0.5, TAU_CRUISE_FIT_YR_PER_M_S * DV["dv_ret"])
    chem = t_out + stay + t_back
    # The delta-v-linear cruise estimate is calibrated to CHEMICAL transfers.
    # An electric stage thrusts for most of the trip instead, so its duration
    # is governed by burn time and not by an impulsive-transfer fit; a chemical
    # stage has no such floor, and applying one would lengthen every chemical
    # mission in the model by years.
    electric_floor = (ep["thrust_yr"] + stay) if ep["thrust_yr"] > 0 else 0.0
    duration = max(1.0, chem, electric_floor)
    if duration > cfg.max_mission_duration_yr:
        return refuse("the mission runs past `max_mission_duration_yr`")
    cadence = max(stay, DV["synodic"])
    calendar_cap = max(1, int(C["val"]("Mining rig service life") // stay))
    trips = (min(calendar_cap, int(C["val"]("Mining rig maximum trips")))
             if C["rig_trip_limit"] else calendar_cap)
    return {"R": R, "passes": passes, "cascade": cas, "ep": ep, "m_tps": m_tps,
            # The hardware the closed form was SOLVED at, which is the previous
            # pass's, against the hardware the stack actually flies.  The
            # difference is the whole of the launch-mass margin -- the loop does
            # not re-solve at its own fixed point -- and it is the one identity
            # on the page that checks the cascade against itself.
            "hw_solved": passes[-1]["hw_in"], "f_solved": passes[-1]["f_used"],
            "throughput": throughput, "vol_cap": vol_cap, "m_pay": m_pay,
            "feed": feed, "ratio": feed / m_pay, "load": load, "water": water,
            "c_frac": c_frac, "f_eff": f_eff, "m_containment": c_frac * m_pay,
            "plant": plant_kg, "draw": draw, "hw": hw, "m_dry": m_dry,
            "m_after": m_after, "m_rprop": m_rprop, "m_tank_ret": m_tank_ret,
            "m_at": m_at, "m_oprop": m_oprop, "m_tank_out": m_tank_out,
            "m_launch": m_launch, "ret_vol": m_pay / C["rho"] / 1000.0,
            "dig_yr": dig_yr, "stay": stay, "chem_fit": chem,
            "electric_floor": electric_floor, "duration": duration,
            "cadence": cadence, "calendar_cap": calendar_cap, "trips": trips,
            "t_out": t_out, "t_back": t_back, "isru_prop": isru_prop,
            "isru_feed": isru_feed, "isru_water": isru_water,
            "liberated": liberated, "boiloff_factor": boiloff_factor,
            "dv_ret_eff": dv_ret_eff}


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
    # A LOOKUP, not a computation: it reads `window_phasing_au` off the
    # destination's row in `DELIVERY_ARCHITECTURES`, which is the table where a
    # destination declares its own physical mission.  On the register as data.
    a_dest = master.window_phasing_au(C["cfg"].delivery_destination)
    t_ast = C["a_au"] ** 1.5
    t_dest = a_dest ** 1.5
    # 🚨  THE SYNODIC PERIOD WAS CALLED OUT OF THE PIPELINE, in the
    # function whose docstring restates why it is counterintuitive, under a
    # footer telling the reader the clock was derived here.  Both guards are
    # reproduced rather than assumed away: they are not decoration, and the
    # second one is the whole reason a near-destination body does not report an
    # infinite wait.  See `model_borrows`.
    if not (0.05 < C["a_au"] < 100.0) or a_dest <= 0:
        # Not a geometry this term can speak about; the model answers one year
        # rather than refusing, and so does this.
        synodic = 1.0
    else:
        denom = abs(1.0 / t_ast - 1.0 / t_dest)
        # A body whose period matches the destination's has windows that never
        # come round.  The cap stands in for a real mission accepting a worse
        # transfer rather than waiting forever, and it BINDS: it is the value
        # every co-orbital body in the catalog reports.
        synodic = 10.0 if denom <= 1e-9 else min(1.0 / denom, 10.0)
    return {"t_ast": t_ast, "t_dest": t_dest, "a_dest": a_dest,
            "synodic": synodic,
            "window_wait": 0.5 * synodic if C["windows"] else 0.0}


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
    mode = C["terms"]["market"]
    # 🚨  TWO OF THE FOUR MODELS BOUND NOTHING, and that is a statement about
    # the model rather than a shortcut.  `unbounded` is labelled a diagnostic
    # because it sells any quantity at spot, which is the free lunch every
    # other mode exists to refuse; `single_mission` declines to ask the
    # question at all by pinning the programme at one mission.  Both therefore
    # take the uncapped hold, and neither has a window to compute.
    if mode in ("unbounded", "single_mission"):
        free = M["load"]
        return {"window": float("inf"), "allow": {}, "capped": free,
                "gross_base": free["value"], "surplus_frac": 0.0, "sat": 1.0,
                "clearing": 1.0, "unsold": 0.0, "surplus": 0.0, "mode": mode,
                "delivered": free["value"] / M["m_pay"] if M["m_pay"] else 0.0}
    window = ((M["duration"] + (n_missions - 1) * (M["cadence"] / fleet))
              / n_missions)
    if mode == "elasticity":
        return _elastic_sale(C, M, fleet, window)
    caps, keys = {}, {}
    for name, _frac, _price in C["phases"]:
        key = C["market_keys"].get(name, name)
        keys[name] = key
        caps.setdefault(key, C["market_kg"].get(key, float("inf")) * window)
    frac = C["terms"]["surplus_frac"]
    if C["beneficiated"]:
        capped = knapsack(M["m_pay"], M["feed"], C["phases"], C["recovery"],
                          caps=dict(caps), keys=keys, surplus_frac=frac)
    else:
        # Raw ore cannot be reshaped: the cargo is the body's own composition,
        # so a ceiling clips the sale rather than steering the hold.  That is
        # why this branch is a sale and the one above is a knapsack.
        capped = raw_sale(M["load"], C["phases"], caps, keys, frac)
    free = M["load"]
    # Two mass columns, and they are exclusive: mass past a ceiling is either
    # abandoned or discounted, never both.  Which one carries it is the run's
    # `sell_surplus_at_discount`, so the derivation reports whichever the row
    # it is documenting would have reported.
    # The beneficiated case measures loss as hold space the ceilings kept
    # empty; the raw case cannot, because the hold is unchanged and the loss is
    # in the SALE.  Each branch reports the one its own mechanism produces.
    #
    # 🚨  `sum(mix)` ON THE FREE SIDE AND `loaded` ON THE CAPPED SIDE, WHICH
    # LOOKS LIKE AN INCONSISTENCY AND IS THE MODEL'S OWN ARITHMETIC.  calc
    # subtracts `sum(payload_mix.values())` from the knapsack's `loaded_kg`,
    # and `loaded_kg` is `payload_kg - remaining`, an accumulated subtraction.
    # Those are two associations of one quantity, so when the ceilings keep no
    # hold space at all the difference is not 0.0 but one ULP: 1.455e-11 kg on
    # 1,891 rows of the cislunar beneficiated searched cell.
    #
    # Taking `free["loaded"]` on both sides is tidier, cancels exactly, and is
    # WRONG here for the reason this repo already wrote down about
    # `y * 365.25 * 24.0`: one rounding is not more accurate than two, it is a
    # different number, and the one that matters is the model's.  Matching the
    # association moves this column from "differs by 100%" -- 0.0 against a
    # residue is a relative error of 1.0 however small the residue -- to
    # bit-exact.
    lost = (capped["unsold"] if "unsold" in capped
            else max(0.0, sum(free["mix"].values()) - capped["loaded"]))
    return {"window": window, "allow": caps, "capped": capped, "mode": mode,
            "gross_base": free["value"], "surplus_frac": frac,
            "clearing": capped["value"] / free["value"] if free["value"] else 1.0,
            "unsold": lost, "surplus": capped.get("surplus", 0.0),
            "delivered": capped["value"] / M["m_pay"] if M["m_pay"] else 0.0}


def _elastic_sale(C, M, fleet, window):
    """The constant-elasticity demand curve, which is what `elasticity` prices.

        P / P0 = (1 + Q / Qm) ^ (-1/eps)

    Precious-metal demand is inelastic, so at the committed eps = 0.5 doubling
    world supply QUARTERS the price, which is why "return a tonne of platinum"
    was never the business a spot-price spreadsheet makes it look.

    🚨  THE RATE THAT MOVES A PRICE IS THE MARKET'S, NOT ONE PHASE'S SHARE OF
    IT.  Two phases selling into one market depress it together, so the
    quantities are POOLED per market key and each phase's revenue is then
    discounted at its market's multiplier.  Asking the curve per phase asks it
    twice about half the quantity each time, which is a strictly smaller
    haircut than the truth.

    ⚠️  And the quantity is the PROGRAMME's, not one mission's: what is on the
    market at once is the fleet, because one rig serves its campaigns back to
    back while F rigs put F payloads in flight concurrently.  Before v1.14.0
    this term read one mission, so a hundred-mission programme sold a hundred
    payloads at the price one payload commands.
    """
    free = M["load"]
    sold, price = free["mix"], {n: p for n, _f, p in C["phases"]}
    pooled = {}
    for phase, kg in sold.items():
        key = C["market_keys"].get(phase, phase)
        pooled[key] = pooled.get(key, 0.0) + kg
    mult, adj = {}, 0.0
    for phase, kg in sold.items():
        key = C["market_keys"].get(phase, phase)
        if key not in mult:
            mult[key] = saturation_multiplier(
                pooled[key] * fleet / M["duration"],
                C["market_kg"].get(key, 0.0), C["cfg"].demand_elasticity)
        adj += kg * price.get(phase, 0.0) * mult[key]
    capped = dict(free, value=adj,
                  usd_per_kg=adj / free["loaded"] if free["loaded"] else 0.0)
    return {"window": window, "allow": {}, "capped": capped,
            "gross_base": free["value"], "surplus_frac": 0.0,
            "mode": "elasticity", "multipliers": mult, "pooled": pooled,
            # ⚠️  THE TWO DIAGNOSTICS ARE NOT INTERCHANGEABLE AND THIS IS
            # WHERE THEY CROSS OVER.  A demand curve moves the PRICE, so the
            # haircut lands in `saturation_multiplier` and nothing goes
            # unsold: `market_clearing_fraction` is 1.0 because every kilogram
            # cleared, at a worse price.  A hard ceiling is the mirror image.
            # Reporting one where the model reports the other reads as a clean
            # result rather than a swapped one.
            "sat": adj / free["value"] if free["value"] else 1.0,
            "clearing": 1.0, "unsold": 0.0, "surplus": 0.0,
            "delivered": adj / M["m_pay"] if M["m_pay"] else 0.0}


def saturation_multiplier(delivered_kg_per_yr, annual_market_kg, elasticity):
    """The demand curve's price multiplier, 1.0 where the market shrugs."""
    if annual_market_kg <= 0 or delivered_kg_per_yr <= 0 or elasticity <= 0:
        return 1.0
    ratio = delivered_kg_per_yr / annual_market_kg
    if ratio <= 1e-9:
        return 1.0
    return (1.0 + ratio) ** (-1.0 / elasticity)


def reliability(C, M, n_missions):
    """Launch, cruise and mining, multiplied; costs are charged in full anyway.

    Only the mining term grows with the programme.  Launch vehicles are already
    mature and MTBF is a duration exposure rather than a heritage question, so
    neither of those learns.
    """
    val = C["val"]
    if not C["terms"]["reliability"]:
        # calc 1.22.0 default.  Revenue is not discounted, and the document
        # says which question that makes the answer to: what it costs IF IT
        # WORKS.  Every term is reported as 1.0 rather than omitted, so the
        # document's table has the same shape either way.
        return {"p_launch": 1.0, "p_cruise": 1.0, "mtbf": float("inf"),
                "p_mining": 1.0, "terms": [], "p_succ": 1.0, "off": True}
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
            "p_mining": p_mining, "terms": terms, "off": False,
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
    terms = C["terms"]
    # Wright's law, or exactly 1.0 when the run did not apply it.  1.0 is what
    # the model's own `learning_curve_factor` reports in that case, so the
    # check below compares like with like rather than skipping the column.
    lc = (sum(k ** math.log(cfg.learning_curve_rate, 2)
              for k in range(1, n_missions + 1)) / n_missions
          if terms["learning"] else 1.0)
    rig_total = cfg.mining_hardware_kg * val("Mining payload recurring cost")
    share = max(1, min(per_ship, M["trips"]))
    # 🚨  TWO WAYS TO USE UP A RIG, AND THE SECOND ONE IS GATED WITH THE CAP
    # THAT CREATES IT.  Crediting salvage on remaining calendar years while the
    # machine is mechanically finished would refund a worn-out rig, so the
    # binding utilisation is the larger of the two fractions -- but with
    # `model_rig_trip_limit` off there is no cycle cap and the calendar term
    # stands alone.  Taking the max unconditionally drove `used` to 1.0 and
    # zeroed a salvage credit the run actually collected.
    used = share * M["stay"] / val("Mining rig service life")
    if C["rig_trip_limit"] and M["trips"] > 0:
        used = max(used, share / M["trips"])
    used = min(1.0, used)
    terminal = (rig_total * (1.0 - used) * val("Rig salvage fraction")
                if n_missions > 1 else 0.0)
    rig_share = (rig_total - terminal) / share

    # Resolved once in `context`, off the ROW where the row knows better than
    # the table on disk.  Reading `C["pro"]["cost_usd_per_kg"]` here is what
    # made every archived chemical mission fail to reproduce.
    prop_cost = C["prop_usd_per_kg"]
    # Whether there is an electric stage to price at all, which is also whether
    # the page has anywhere to show the two rates that price it.
    has_ep = M["ep"]["power"] > 0.0
    lines = {
        "launch": M["m_launch"] * float(C["veh"]["usd_per_kg_to_leo"]),
        "oprop": M["m_oprop"] * prop_cost,
        # 🚨  PROPELLANT MADE ON SITE IS NOT BOUGHT ON EARTH, and it is not
        # paid for at year zero either: it is manufactured at the asteroid over
        # the mining duration, so it is an ONGOING line rather than an up-front
        # one and misses the full up-front compounding.
        "rprop": M["m_rprop"] * (cfg.isru_processing_usd_per_kg if C["isru"]
                                 else prop_cost),
        "rig": rig_share,
        # The vehicle that meets the cargo: a lander, a re-entry capsule or a
        # berthing adapter, resolved per destination in `context`.  Billed on
        # the return vehicle ACTUALLY FLOWN, whose dry mass grows with the
        # haul, rather than on the 500 kg base article.
        "capsule": M["m_dry"] * C["capsule_per_kg"] * lc,
        # The heat shield is the most literally per-mission article on the
        # vehicle -- it is consumed on entry and rebuilt for the next flight --
        # so the learning curve applies to it exactly as it does to the
        # capsule.  Zero on a propulsive return, and it sits OUTSIDE the
        # hardware subtotal because it is not hardware that comes home.
        "tps": M["m_tps"] * C["tps_per_kg"] * lc,
        # Priced off the source actually flown.  A radioisotope watt costs
        # 625 times a solar one, so charging the solar rate for a nuclear plant
        # would be exactly the asymmetry this codebase keeps finding: a mass in
        # the rocket equation with the wrong price in the ledger.
        "plant": M["draw"] * C["plant_usd_per_w"] * lc,
        # The EP array is priced at the SOLAR rate even on a radioisotope
        # mission, because nuclear heat runs the processing plant and the
        # thruster still flies panels.  Both rates are only rates for a page
        # that has an electric stage to show them on; see `val`.
        "ep": (M["ep"]["power"]
               * val("Power system (solar + battery)", used=has_ep)
               + M["ep"]["power"] / 1000.0
               * val("Electric propulsion system recurring cost",
                     used=has_ep)) * lc,
        "tank": ((M["m_tank_ret"] + M["m_tank_out"])
                 * val("Propellant tank recurring cost") * lc),
    }
    hardware = (lines["rig"] + lines["capsule"] + lines["plant"]
                + lines["ep"] + lines["tank"])
    ops = M["duration"] * val("Mission operations")
    ongoing_lines = ops + (lines["rprop"] if C["isru"] else 0.0)
    nre = (val("Spacecraft development (NRE)")
           * (1.0 - cfg.nre_recurring_overlap_fraction) / n_missions)
    autonomy = val("Autonomous mining control & AI (NRE)") / n_missions
    licensing = C["licensing_usd"]
    handover = C["recovery_usd"]
    # 🚨  UNDERWRITERS COVER THE REPLACEMENT COST OF THE LAUNCHED ASSET, not
    # the revenue it was going to earn, and that asset is EVERYTHING on the
    # rocket.  The rig enters at its full build cost rather than its amortised
    # share, because losing it on ascent destroys the whole unit however many
    # missions were meant to share it; everything else is per-mission already.
    # The heat shield is on the list too and is the one item whose cost line
    # sits outside the hardware subtotal, which is how it came to be flown
    # uninsured for two releases.
    liability = launch_ins = 0.0
    if terms["insurance"]:
        liability = val("Third-party liability insurance")
        book = (rig_total + lines["capsule"] + lines["plant"] + lines["ep"]
                + lines["tank"] + lines["tps"])
        launch_ins = val("Launch insurance") / 100.0 * (lines["launch"] + book)

    # 🚨  TERM BY TERM, IN THE MODEL'S OWN ORDER.  Four of these are
    # N-dependent and they are interleaved with the ones that are not, so no
    # prefix of this sum can be pre-added without re-associating it.  The two
    # zeros are third-party liability and launch insurance, which calc 1.20.0
    # took out of scope; they are kept as terms rather than deleted so that
    # turning `charge_insurance` back on is an edit to a value and not to the
    # shape of the sum.
    upfront_lines = (lines["launch"] + lines["oprop"] + hardware + lines["tps"]
                     + licensing + liability + launch_ins + nre + autonomy
                     + (0.0 if C["isru"] else lines["rprop"]))
    cont = 1.0 + cfg.contingency_fraction
    # A zero rate is not a special case anywhere below: the multipliers come
    # out at exactly 1.0, and the programme calendar block is already guarded
    # on `y > 1.0`, so it goes inert on its own.  That is the same structure
    # the model has, and it is why calc 1.22.0 could turn the cost of capital
    # off without touching the calendar term.
    wacc = val("Cost of capital (WACC)") if terms["wacc"] else 0.0
    mult_up = (1.0 + wacc) ** M["duration"]
    mult_on = (1.0 + wacc) ** (M["duration"] / 2.0)
    upfront = upfront_lines * cont
    ongoing = ongoing_lines * cont
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
            "handover": handover, "liability": liability,
            "launch_ins": launch_ins, "rig_total": rig_total, "used": used,
            "terminal": terminal, "rig_gross_share": rig_total / share,
            "rig_credit_share": terminal / share, "share": share,
            "upfront_lines": upfront_lines, "upfront": upfront,
            "ongoing": ongoing, "end": end, "wacc": wacc,
            "mult_up": mult_up, "mult_on": mult_on, "y": y,
            "cal_cost": cal_cost, "cal_credit": cal_credit,
            "programme_upfront": nre + autonomy + rig_total / share,
            "delta": delta, "total": total + delta,
            "contingency": cfg.contingency_fraction
            * (upfront_lines + ongoing_lines + handover),
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
    import dataclasses
    import master
    rig = (M["trips"], M["calendar_cap"],
           int(C["val"]("Mining rig maximum trips")) or None)
    # 🚨  THE LADDER FOLLOWS THE ROW, NOT THE LIVE CONFIG.  `_programme_ladder_cached`
    # reads `optimise_programme_scale` and `nre_amortization_missions`, and the
    # run being documented may have set either differently from whatever the
    # module holds now -- a `quick` preset run is N = 1 with no search, while
    # the module default searches.  Derived against the live config instead,
    # the ladder proposes programmes the run never priced, picks one, and then
    # disagrees with the row about eleven columns for a reason that is not
    # arithmetic.  A REPLACED config rather than a mutated one: the cache is
    # keyed on the values these functions read, so a copy is answered correctly
    # and the global is left alone.
    terms = C["terms"]
    cfg = C["cfg"]
    if (cfg.optimise_programme_scale != terms["searched"]
            or (not terms["searched"]
                and cfg.nre_amortization_missions != terms["n_fixed"])):
        cfg = dataclasses.replace(
            cfg, optimise_programme_scale=terms["searched"],
            nre_amortization_missions=(terms["n_fixed"]
                                       if not terms["searched"]
                                       else cfg.nre_amortization_missions))
    programmes, fleets = master._programme_ladder_cached(
        rig, cfg, master._market_mode(cfg))
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

    del REFUSAL[:]
    priced = [(kind, r, at(r)) for kind, r in rungs]
    live = [p for p in priced if p[2]]
    if not live:
        why = REFUSAL[-1] if REFUSAL else "the cascade refused without saying why"
        hauled = float(B["mineable"])
        row_pay = float(C["archived_payload"] or 0.0)
        hint = ""
        if row_pay and hauled > row_pay * 1.000001:
            # ⚠️  THE COMMONEST CAUSE IS A DIAL, NOT THE BODY.
            # `max_mining_fraction` went 0.05 -> 1.0 in calc 1.23.0 and is read
            # from the LIVE config, so a row written before that is re-derived
            # with a haul up to twenty times the one its run took -- and the
            # stack it builds then fails against the vehicle.  The row's own
            # payload against this derivation's depletion allowance is what
            # says so, and it costs nothing to check before blaming the body.
            hint = ("\n  This derivation allows %.0f kg to be mined and the "
                    "row hauled %.0f kg.\n  A run made before calc 1.23.0 "
                    "capped it at 5%% of the body: re-run with\n"
                    "  --max-mining-fraction 0.05 to derive it as that run "
                    "did." % (hauled, row_pay))
        sys.exit("no mission closes on this body at any concentration ratio.\n"
                 "  The cascade refused because %s.%s" % (why, hint))
    best_r = min(live, key=lambda p: p[2]["ladder"]["best"]["obj"])[1]
    step = r_max ** (1.0 / (steps - 1))
    for ratio in (best_r / step ** 0.5, best_r * step ** 0.5):
        if 1.0 <= ratio <= r_max:
            priced.append(("refine", ratio, at(ratio)))
    winner = min((p for p in priced if p[2]),
                 key=lambda p: p[2]["ladder"]["best"]["obj"])
    return {"r_max": r_max, "step": step, "rungs": priced, "winner": winner}


# ------------------------------------------------- the dial the row refutes
def mining_cap_note(C, B):
    """A line naming `max_mining_fraction` when the ROW disproves this one.

    🚨  THE CAP CAN BIND SILENTLY, AND THE LOUD HALF WAS THE ONLY
    HALF ANYBODY HAD SEEN.  When a too-LOOSE cap makes this derivation
    over-dig, the launch stack fails against the vehicle and
    `concentration_sweep` refuses with a hint naming the dial.  When it is too
    TIGHT the mission still closes: the derivation digs less, picks a different
    concentration ratio and a different fleet, and writes a confident document
    about a smaller mission.  Measured on a 158-row insurance cell swept with
    `--max-mining-fraction 0.05` against rows run at 1.0: 53 columns DIFFER,
    `feed_processed_kg` 117,405 against 209,809 and `fleet_ships` 3 against 5,
    with every MASS agreeing to 5.7e-05 -- which is the signature of a search
    that landed elsewhere rather than of arithmetic that went wrong.

    ✅  THE TEST IS ONE-SIDED, AND AIRTIGHT IN THAT DIRECTION.  An
    allowance ABOVE the haul proves nothing, because a cap that does not bind
    is supposed to sit above it -- which is why the refusal uses that only as a
    hint, after something else has already failed.  An allowance BELOW the haul
    is different in kind: the run being documented actually mined that much, so
    its own cap permitted it, and a cap permitting less is provably not the one
    that run used.

    ⚠️  ONE OVERRIDE, EVERY SOURCE.  `--max-mining-fraction`
    replaces the field on the live config, so a sweep mixing archived cells
    with cells built at the current default cannot be right for both at once.
    That is what this line is for: it names the row the dial is wrong for,
    instead of leaving fifty differing columns to be read as a defect.
    """
    # ⚠️  THE FEED, NOT THE PAYLOAD.  The allowance limits how much
    # regolith may be DUG; `archived_payload` is what comes HOME, and on a raw
    # mission those differ by orders of magnitude.  The first version of this
    # compared the allowance against the payload, so it never fired on the very
    # case it was written for: the numbers were 117,405 against 39,546 where
    # the comparison that matters was 117,405 against a feed of 209,809.
    # Measured, not reasoned about -- the body is 2,348,111 kg, 5% of it is
    # 117,405.5, and the derived feed came out 117,405.54, so the cap had bound
    # to the digit while the row had dug 8.9% of the body.
    row_feed = C.get("archived_feed")
    try:
        allowance = float(B["mineable"])
        dug = float(row_feed)
    except (TypeError, ValueError, KeyError):
        return ""
    if not (dug > 0.0 and allowance > 0.0):
        return ""
    # Equal is the ordinary case: the cap is exactly what bound that run too.
    if allowance >= dug * 0.999999:
        return ""
    return ("\n    max_mining_fraction is %g here, which allows %.0f kg of this "
            "body to be dug,\n    and the row records a feed of %.0f kg -- so "
            "the run that wrote it was\n    not capped the way this process "
            "is.  That alone re-picks the ratio and\n    the fleet, and every "
            "column downstream of them."
            % (C["cfg"].max_mining_fraction, allowance, dug))


# -------------------------------------------------------------- verification
def check(derived, archived):
    """Every derived quantity against the archived row, column by column.

    The document's footer quotes what this returns, so it is measured on every
    build rather than copied forward.  A pure float comparison is the right
    test here and a tolerance is the wrong one: these are two statements of the
    same arithmetic, so anything past the last bit or two is a finding.

    🚨  A QUANTITY THE ROW HAS NO COLUMN FOR IS SKIPPED, AND THE SKIP IS
    REPORTED RATHER THAN SWALLOWED.  Skipping is right -- a calc 1.21.2 archive
    has no `surplus_payload_kg`, and refusing over it would make every archived
    cell unverifiable -- but a silent skip is this repo's most-catalogued
    harness defect, and it is worse here than usual: the compared COUNT is the
    only thing the footer prints, so a column renamed upstream would quietly
    shrink the check while it still announced that everything agreed.  The
    names come back with the result and the caller prints them.
    """
    exact = close = 0
    worst, worst_name, bad, skipped, names = 0.0, "", [], [], []
    for name, ours in sorted(derived.items()):
        if name not in archived:
            skipped.append(name)
            continue
        names.append(name)
        theirs = float(archived[name])
        if ours == theirs:
            exact += 1
            continue
        rel = abs(ours - theirs) / max(abs(theirs), 1e-30)
        if rel > worst:
            worst, worst_name = rel, name
        if rel < CLOSE_TOL:
            close += 1
        else:
            bad.append((name, ours, theirs, rel))
    return {"n": exact + close + len(bad), "exact": exact, "close": close,
            "bad": bad, "worst": worst, "worst_name": worst_name,
            "skipped": skipped, "names": names, "tol": CLOSE_TOL}


def comparable(C, B, DV, M, P, ladder):
    """The derived quantities that have a named column in the archived row."""
    rev, rel, cst = P["rev"], P["rel"], P["cost"]
    return {
        "diameter_km": B["d_km"], "estimated_mass_kg": B["mass"],
        "dv_out_m_s": DV["dv_out"], "dv_ret_m_s": DV["dv_ret"],
        "max_payload_kg": M["m_pay"], "feed_processed_kg": M["feed"],
        "concentration_ratio": M["ratio"], "cargo_water_kg": M["water"],
        "containment_frac": M["c_frac"], "m_containment_kg": M["m_containment"],
        "m_dry_return_kg": M["m_dry"], "m_return_prop_kg": M["m_rprop"],
        "tps_mass_kg": M["m_tps"],
        "m_tank_return_kg": M["m_tank_ret"], "m_at_asteroid_kg": M["m_at"],
        "m_outbound_prop_kg": M["m_oprop"], "m_tank_outbound_kg": M["m_tank_out"],
        "m_launch_kg": M["m_launch"], "power_system_kg": M["plant"],
        "processing_power_w": M["draw"], "ep_system_kg": M["ep"]["mass"],
        "ep_power_w": M["ep"]["power"], "ep_thrust_n": M["ep"]["thrust"],
        "hardware_total_kg": M["hw"], "mining_duration_yr": M["dig_yr"],
        # The axes the cislunar cells could not exercise, each with a column of
        # its own so that turning one on is checked rather than assumed.  Every
        # one of them is exactly zero (or 1.0) on the mission shape that does
        # not use it, which is what makes them safe to compare on every row.
        "ep_thrust_yr": M["ep"]["thrust_yr"], "thruster_kg": M["ep"]["thruster"],
        "isru_propellant_kg": M["isru_prop"], "isru_feed_kg": M["isru_feed"],
        "water_liberated_kg": M["liberated"],
        "boiloff_factor": M["boiloff_factor"],
        # 🚨  THESE FOUR PIN SWITCHES RATHER THAN QUANTITIES, and they are the
        # answer to "what could make the document wrong without making it
        # fail".  `programme_options_priced` pins the LADDER's shape, so
        # `max_fleet_ships` and `programme_search_steps` cannot differ from the
        # run while the winner coincides -- which would print a table of rungs
        # the run never priced beside a correct answer.  The eclipse pair pins
        # `model_eclipse_power`, `max_dark_period_h` and the rotation fallback,
        # all of which the page states in words.  `tanker_cost_usd` pins the
        # orbital-refuelling charge, which this cascade does not express and
        # which would otherwise hide inside `launch_cost_usd`.
        "programme_options_priced": float(len(ladder["coarse"])
                                          + len(ladder["refine"])),
        "array_oversize_factor": C["oversize"],
        "dark_period_h": C["dark_h"],
        "tanker_cost_usd": 0.0,
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
        "surplus_payload_kg": rev["surplus"],
        "delivered_value_usd_per_kg": rev["delivered"],
        # 1.0 under every model but the demand curve, and this is asserted
        # against the row rather than assumed: `verify.py` check 7 holds the
        # same invariant from the other side.
        "saturation_multiplier": rev.get("sat", 1.0),
        "p_mining": rel["p_mining"], "p_success": rel["p_succ"],
        "gross_value_usd": P["expected"], "learning_curve_factor": cst["lc"],
        "launch_cost_usd": cst["lines"]["launch"],
        "outbound_prop_cost_usd": cst["lines"]["oprop"],
        "return_prop_cost_usd": cst["lines"]["rprop"],
        "capsule_cost_usd": cst["lines"]["capsule"],
        "power_system_cost_usd": cst["lines"]["plant"],
        "ep_system_cost_usd": cst["lines"]["ep"],
        "tank_cost_usd": cst["lines"]["tank"],
        "heat_shield_cost_usd": cst["lines"]["tps"],
        "hardware_cost_usd": cst["hardware"],
        "mining_rig_cost_usd": cst["lines"]["rig"],
        "rig_terminal_value_usd": cst["terminal"],
        "missions_sharing_rig": cst["share"], "ops_cost_usd": cst["ops"],
        "nre_cost_usd": cst["nre"], "autonomy_nre_cost_usd": cst["autonomy"],
        "licensing_cost_usd": cst["licensing"],
        "liability_cost_usd": cst["liability"],
        "launch_insurance_cost_usd": cst["launch_ins"],
        "recovery_cost_usd": cst["handover"],
        "contingency_cost_usd": cst["contingency"],
        "upfront_cost_usd": cst["upfront"], "ongoing_cost_usd": cst["ongoing"],
        "end_of_mission_cost_usd": cst["end"],
        "wacc_multiplier_upfront": cst["mult_up"],
        "wacc_multiplier_ongoing": cst["mult_on"],
        "programme_calendar_multiplier": cst["cal_cost"],
        "total_cost_usd": cst["total"],
        # 🚨  THE THREE SUMMARY COLUMNS, DERIVED RATHER THAN LEFT TO THE
        # READER.  `profit_usd` is the one the output CSV is SORTED by while
        # the project ranks on the ratio, which is a trap this module's own
        # `run_winner` exists to avoid -- so a document that shows the ratio
        # and not the profit leaves the reader unable to see why the file is
        # ordered as it is.  All three are one line each off quantities
        # already derived, and deriving them is what puts them in the check.
        "profit_usd": P["expected"] - cst["total"],
        "roi": ((P["expected"] - cst["total"]) / cst["total"]
                if cst["total"] > 0 else float("nan")),
        "usd_per_kg_cost": (cst["total"] / M["m_pay"] if M["m_pay"] > 0
                            else float("nan")),
        "bulk_value_usd_per_kg": C["bulk"],
        # The PURITY BOUND: the richest hold obtainable, which is 100% of the
        # best phase present.  A raw RUN was never given one, so the model
        # reports the bulk value instead of a bound that does not bind.
        # 🚨  THE CONDITION IS THE RUN'S SETTING, NOT THIS MISSION'S.  A
        # body that declines to concentrate inside a beneficiated run still
        # carries the bound its search was given; see `run_setting`, which is
        # where the measurement behind that sentence lives.  The model takes
        # the floor too, because a bound below the bulk value would not be one.
        "best_phase_usd_per_kg": (max([C["bulk"]] + [p[2] for p in C["phases"]])
                                  if C["run_beneficiated"] else C["bulk"]),
    }


# -------------------------------------------------------------------- driver
CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
]


def build(archived, label, body=None, run_beneficiated=None):
    """Derive one winner end to end, and check it against its own row.

    `archived` is the row being documented, from wherever it came: a live
    Stage 4 catalog or a gzipped campaign archive.  The derivation does not
    care which, and deliberately: "the best case of this run" and "the best
    cell of that campaign" are the same question asked of different artefacts.
    """
    designation = str(archived["designation"])
    # The rate log belongs to THIS derivation; see RATE_LOG.
    del RATE_LOG[:]
    # `body` is passed in by `--sweep`, which reads every body it needs in ONE
    # pass over the 862 MB catalog rather than one pass each; see
    # `catalog_bodies`.  A single document still just asks for its own.
    if body is None:
        body = catalog_body(designation)
    # The prices have to be chosen before anything is derived, and they are
    # chosen by the ROW's destination rather than by the config, for the same
    # reason the legs are.  See `mineral_catalog_for`.
    tables = reference_tables(row_destination(archived))
    C = context(body, archived, tables)
    # Before anything is derived: what the ROW charges decides what the
    # derivation charges.  See `terms_in_force`.
    C["terms"] = terms_in_force(archived, C["cfg"])
    C["run_beneficiated"] = run_setting(archived, C["cfg"], run_beneficiated)
    # Only ever read to EXPLAIN a disagreement; the cascade derives both of
    # these itself and never consults them.  The feed is the one the mining cap
    # is comparable with -- the cap limits what may be DUG, and the payload is
    # what comes home.  See `mining_cap_note`.
    C["archived_payload"] = float(archived.get("max_payload_kg") or 0.0)
    C["archived_feed"] = float(archived.get("feed_processed_kg") or 0.0)
    phases, alloy, yields = phase_table(body, tables["minerals"])
    caps, alias = market_ceilings(tables["minerals"])
    C["phases"] = phases
    C["alloy"] = alloy
    C["yields"] = yields
    # The three things needed to reproduce the alloy price on the page.  It is
    # the only price in the model that is not a row lookup, so a document that
    # printed it and not its inputs would be asking to be trusted.
    import master as _m
    C["element_price"] = dict(zip(tables["minerals"]["name"],
                                  tables["minerals"]["price_usd_per_kg"]))
    C["rare_metals"] = set(_m.RARE_METAL_ELEMENTS)
    C["kappa"] = float(body.get("comp_pgm_enrichment") or 1.0)
    C["bulk"] = sum(f * p for _n, f, p in phases)
    C["market_kg"] = caps
    C["market_keys"] = {n: (n if n in caps else alias.get(n, n))
                        for n, _f, _p in phases}
    C["chain"] = delivery_chain(C)
    # ⚠️  DERIVED AND THEN HELD TO MODULE 2's OWN ANSWER.  Walking the chain
    # here is what lets the page show it; agreeing with `delivered_cost_usd_per_kg`
    # to the last bit is what says the walk is the model's and not a second
    # opinion about it.  A destination with no legs prices at zero on both
    # sides, which is the Earth's surface and not a failure.
    if abs(C["chain"]["usd_per_kg"] - C["p_l"]) > 1e-9 * max(1.0, C["p_l"]):
        sys.exit("the delivery chain derived here gives %.10f $/kg and "
                 "Module 2 gives %.10f; the leg walk has drifted from "
                 "`delivered_cost_usd_per_kg`."
                 % (C["chain"]["usd_per_kg"], C["p_l"]))
    B = derive_body(C)
    DV = derive_dv(C)
    DV.update(derive_periods(C))
    sweep = concentration_sweep(C, B, DV)
    _kind, ratio, won = sweep["winner"]
    M, ladder = won["M"], won["ladder"]
    P = ladder["best"]
    result = check(comparable(C, B, DV, M, P, ladder), archived)
    C["population"] = int(getattr(archived, "attrs", {}).get("population") or 0)
    return {"C": C, "B": B, "DV": DV, "M": M, "P": P, "ladder": ladder,
            "sweep": sweep, "ratio": ratio, "archived": archived,
            "check": result, "cell": label, "designation": designation,
            # 🚨  THE FOOTER'S OWN CLAIM, DERIVED.  It used to be a typed
            # sentence saying this file reads nothing from the model but
            # reference data, and that was false in four places.  Scanned off
            # this file's AST now, so a borrow added tomorrow discloses itself
            # on the next render whether or not anybody remembers the footer.
            "borrows": borrowed_shape(),
            "terms": C["terms"]}


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


def describe_terms(terms):
    """One line naming the optional terms the documented row carries."""
    on = [name for name, live in (("reliability", terms["reliability"]),
                                  ("learning curve", terms["learning"]),
                                  ("cost of capital", terms["wacc"]),
                                  ("insurance", terms["insurance"])) if live]
    if terms["surplus_frac"] > 0:
        on.append("surplus at %.0f%%" % (terms["surplus_frac"] * 100.0))
    return ", ".join(on) if on else "none (physics only)"


# ---------------------------------------------------------- completeness
# 🚨  A CHECK THAT THE NUMBERS ARE RIGHT IS NOT A CHECK THAT THE PAGE IS
# COMPLETE, and the two failures look identical from inside `check`: zero
# differing, every time.  A quantity that is never DISPLAYED is never compared
# either, so the check above is silent about anything the page leaves out --
# and it was silent about `hardware_cost_usd`, whose five components were all
# printed and whose sum was not, and about `profit_usd`, which is the column
# the output CSV is sorted by.
#
# ✅  SO COMPLETENESS IS MEASURED SEPARATELY, AND IT IS MEASURED HERE RATHER
# THAN FROM MEMORY.  This audit has been run by hand once per release and
# thrown away each time; on its last run it found cost lines rendering at two
# significant figures, a ceiling the page never mentioned, and text columns
# that decide how a number beside them should be read.  A check that finds
# defects on every run it is given and is then discarded is this repo's most
# expensive habit -- `verify.py`'s header is a list of what it has cost.  It
# is a subcommand now, and on its first run as one it found the zero-plant
# branch asserting a specific power whose three terms were nowhere on the
# page.
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")

# The page is allowed to change a number's UNIT and not its value: dollars
# render in millions, metres per second in kilometres, fractions as percent.
# ⚠️  EVERY SCALE ADDED HERE WEAKENS THE AUDIT, because each one is another
# chance for a column to match a number it has nothing to do with.  So the
# run prints how many columns each scale accounted for: a page that suddenly
# needs `percent` or `billions` for a dozen of them is matching by
# coincidence, and the tally is the only warning of that a clean run gives.
# ⚠️  `1e6` IS THE ONE THAT RUNS THE OTHER WAY, AND IT IS NOT A NEW
# LICENCE.  calc writes `gross_M$`, `cost_M$` and `profit_M$`, which are three
# columns the page already shows divided by a million; they matched only while
# `musd` happened to render those same three in millions, so making `musd` fall
# back to dollars on a small line took them off the page in the audit's eyes
# while the reader could see them perfectly.  The page is allowed to change a
# number's unit and not its value -- this is that sentence for a column that
# arrives already scaled.
SCALES = ((1.0, "as is"), (1e-6, "millions"), (1e-3, "thousands"),
          (1e-9, "billions"), (100.0, "percent"), (1e3, "x1000"),
          (1e6, "M$ column"))

# How tightly a page number has to pin a value before the match counts as
# evidence.  One percent is two significant figures, which every formatter on
# the page clears comfortably -- `fmt` shows at least one decimal, `prec`
# shows twelve significant figures, and `musd` scales its precision to the
# size of the line.  It is the bare integers that this excludes, and they are
# matched exactly or not at all.
RESOLUTION = 0.01

# Columns a complete page is not expected to print, each with its reason.
# ⚠️  ADD A ROW WHEN YOU HAVE READ THE FINDING AND DECIDED TO KEEP IT, never
# to quiet a red line you have not read.  Every row here is a claim that the
# page is better without the number, and each one was argued once.
NOT_SHOWN = {
    "catalog_date": "when the run happened, not what it computed",
}


def rendered_text(html_text):
    """The page as a reader sees it: tags out, entities back, one string.

    Tags become a space rather than nothing, so that two numbers in adjacent
    cells cannot be concatenated into a third number that appears on no part
    of the page.
    """
    import html as html_module
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html_text)
    text = re.sub(r"<[^>]+>", " ", text)
    return html_module.unescape(text)


def page_numbers(text):
    """Every number the page shows, with the precision it was shown at.

    A number printed with `d` decimals states its value to within half of the
    last place, so each pair carries its own tolerance and the caller never
    has to guess one.  An exponential rendering carries its tolerance the same
    way: `1.234e-06` is precise to 0.0005e-06, not to 0.0005.
    """
    found = []
    for token in NUMBER.finditer(text):
        raw = token.group(0).replace(",", "").lower()
        try:
            value = float(raw)
        except ValueError:
            continue
        mantissa, marker, exponent = raw.partition("e")
        decimals = len(mantissa.partition(".")[2])
        half = 0.5 * (10.0 ** -decimals) * (10.0 ** (int(exponent) if marker
                                                     else 0))
        found.append((value, half))
    return found


def on_page(value, numbers, slack=0.0):
    """The scale at which the page shows `value`, or None if it does not.

    `slack` is the uncertainty in `value` ITSELF, which is zero for a float
    off the row and is not zero for a number recovered from a rounded string:
    `payload_mix` states its masses to the kilogram, so a hold of 98,618.4 kg
    reaches here as 98,618 and would miss a page that printed the true figure.
    The two tolerances add, in the units the comparison is made in.

    🚨  A MATCH IS ONLY EVIDENCE IF THE PAGE NUMBER IS PRECISE ENOUGH TO BE
    ONE, AND THE FIRST VERSION OF THIS FUNCTION WAS NOT.  Consistency with a
    rounding is the whole test, so a page printing a bare `0` was consistent
    with any cost in the model once the audit was allowed to look in billions,
    and a bare `3` with anything from 2.5 to 3.5 at six different scales.
    MEASURED RATHER THAN FEARED: every numeric column was moved by 31% and
    **99 of 100 still matched**, which is a check that reports clean and means
    nothing -- the exact failure this repo files under a diagnostic that
    agrees with itself perfectly.  A page number must now pin the value to
    within `RESOLUTION`, or print it exactly; the same perturbation now
    matches 3 of 100.
    """
    for scale, name in SCALES:
        target = value * scale
        room = half_room = slack * abs(scale)
        for shown, half in numbers:
            gap = abs(target - shown)
            # Printed exactly, at whatever precision: an integer rendered as
            # an integer is the commonest case and carries no rounding at all.
            if gap <= abs(target) * 1e-12:
                return name
            room = half + half_room
            if (gap <= room * (1.0 + 1e-9)
                    and room <= RESOLUTION * abs(target)):
                return name
    return None


def composite(word):
    """A text cell split into the words and numbers it is made of, or None.

    Returns None for a cell that is a single word, which is the ordinary case
    and wants the substring test instead.  A cell with digits in it is taken
    apart: `nickel-iron 98,618kg; silicates 40,785kg` becomes three names and
    three masses, each of which the page has to account for separately.
    """
    if not NUMBER.search(word):
        return None
    parts = []
    for piece in re.split(r"[;,]?\s+", word):
        piece = piece.strip()
        if not piece:
            continue
        number = NUMBER.match(piece)
        if number and number.group(0) not in ("-",):
            raw = number.group(0).replace(",", "")
            try:
                parts.append(("number", float(raw), len(raw.partition(".")[2])))
            except ValueError:
                parts.append(("word", piece, 0))
        else:
            # A trailing unit is not a word the page owes the reader: `98,618kg`
            # is one number wearing its unit, and the unit is on the page's own
            # column header rather than beside the figure.
            stripped = re.sub(r"^[^A-Za-z]*|[^A-Za-z)]*$", "", piece)
            if stripped:
                parts.append(("word", stripped, 0))
    return parts or None


def composite_part_on_page(part, text, numbers):
    """One piece of a composite cell: a word to find or a number to match."""
    kind, value, decimals = part
    if kind == "word":
        return value.lower() in text.lower()
    return on_page(value, numbers, slack=0.5 * (10.0 ** -decimals)) is not None


def audit_columns(row, text, numbers, skip=None):
    """Every column of the row against the rendered page.

    ⚠️  A ZERO MATCHES ANYTHING AND IS THEREFORE NOT EVIDENCE.  A raw mission
    carries a third of its ISRU and heat-shield columns at 0.0, and a page
    that happens to print a zero anywhere would let the audit congratulate
    itself on every one of them.  They are counted apart, and the summary
    quotes the non-zero total, which is the number that means something.
    """
    missing, shown, zeros, exempt = [], [], [], []
    skip = NOT_SHOWN if skip is None else skip
    for column in row.index:
        value = row[column]
        if column in skip:
            exempt.append(column)
            continue
        if value is None or (not isinstance(value, str) and pd.isna(value)):
            zeros.append(column)
            continue
        if isinstance(value, str):
            # A text column is a WORD the page has to say, and it usually
            # decides how a number beside it should be read: `thrust_scaling`
            # is what separates a conventional thruster's specific mass from a
            # replicated device's, and the figure alone does not say which.
            word = str(value).strip()
            if not word:
                zeros.append(column)
                continue
            if word.lower() in text.lower():
                shown.append((column, "verbatim"))
                continue
            if word.replace("_", " ").lower() in text.lower():
                shown.append((column, "words"))
                continue
            # 🚨  AND WHEN IT IS NOT A WORD AT ALL, TAKE IT APART.
            # `payload_mix` is three phase names and three masses in one cell,
            # and asking whether that whole string appears on the page asks
            # the wrong question: the page renders the same hold as a TABLE,
            # so the audit reports a gap that is a punctuation difference.  A
            # text column carrying digits is a sentence of numbers, and every
            # part of it is checked on its own -- a stronger test than the
            # substring above, because it holds the hold table to the row
            # phase by phase and kilogram by kilogram.
            # ⚠️  THE ORDER MATTERS AND IS NOT COSMETIC.  `pipeline_version`
            # is `1.22.0`, which a number-splitter reads as 1.22 and a version
            # is not a measurement; trying the whole string first means only
            # the cells that really are composites are ever taken apart.
            parts = composite(word)
            if parts:
                absent = [part for part in parts
                          if not composite_part_on_page(part, text, numbers)]
                if absent:
                    missing.append((column, "; ".join(str(p[1])
                                                      for p in absent)))
                else:
                    shown.append((column, "part by part"))
                continue
            missing.append((column, word))
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == 0.0:
            zeros.append(column)
            continue
        scale = on_page(number, numbers)
        if scale:
            shown.append((column, scale))
        else:
            missing.append((column, number))
    return {"missing": missing, "shown": shown, "zeros": zeros,
            "exempt": exempt}


def audit_rates(text, numbers):
    """Every reference-table constant the derivation read, against the page.

    🚨  ASK OF EVERY DISPLAYED NUMBER: COULD A READER REPRODUCE IT FROM WHAT
    IS ALSO ON THE PAGE?  Where the answer is no, the page is asking to be
    trusted, which is the one thing a worked calculation must never do.  A dig
    time cannot be checked without the rig's throughput, and a power draw
    cannot be checked without the three energy rates behind it.  Neither of
    those is an output column, so `audit_columns` cannot see either.
    """
    missing, shown = [], []
    seen = set()
    for table, field, value in RATE_LOG:
        if (table, field) in seen:
            continue
        seen.add((table, field))
        scale = on_page(value, numbers)
        if scale:
            shown.append((table, field, value, scale))
        else:
            missing.append((table, field, value))
    return {"missing": missing, "shown": shown}


# The factor the audit moves every number by to measure itself.  Not round,
# deliberately: 1.3 would land on a page that happens to print both a value
# and a third of it, and this audit exists because a plausible-looking
# coincidence is exactly what it is bad at telling from a real match.
PERTURBATION = 1.317


def discrimination(row, text, numbers):
    """How often the audit matches a number the page has never contained.

    🚨  A COMPLETENESS MATCHER THAT ACCEPTS ANY ROUNDING ACCEPTS EVERYTHING,
    and it looks identical to one that works: both print a clean line.  The
    first version of this audit matched **99 of 100** columns after every one
    of them had been moved by 31%, because a page printing a bare `0` is
    consistent with any cost in the model once six unit scales are allowed.
    So the audit measures itself, on every run, against the same page: move
    every number and count how many still find a home.  A few percent is the
    floor -- the page holds hundreds of numbers and some collision is
    inevitable -- and anything approaching the column count means the matcher
    has stopped discriminating and the clean line above it means nothing.
    """
    fake = row.copy()
    moved = 0
    for column in row.index:
        value = row[column]
        if isinstance(value, str) or value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number == number and number != 0.0:
            fake[column] = number * PERTURBATION
            moved += 1
    out = audit_columns(fake, text, numbers)
    hits = sum(1 for column, _how in out["shown"]
               if not isinstance(row[column], str))
    return hits, moved


def not_shown(row):
    """The columns this page is not expected to print, for THIS row.

    ⚠️  MOST OF IT IS A CONSTANT AND ONE ENTRY IS NOT, WHICH IS THE POINT.
    Whether the page owes the reader `comp_group` depends on the row: the
    header prints the taxonomy group only where it says something the spectral
    letter does not, so on a `D` / `D-type` body the column is deliberately
    absent and on an `M` / `X-complex` body it is deliberately there.  A flat
    exemption would cover both and stop checking the case that matters, so
    the question is asked of the renderer, which owns the rule.
    """
    import worked_calculation_doc
    out = dict(NOT_SHOWN)
    if worked_calculation_doc.group_restates_type(
            row.get("comp_group"), row.get("spectral_type")):
        out["comp_group"] = ("the spectral letter already says it; the header "
                             "drops a group that only restates the type")
    return out


# ──────────────────────────────────── what this derivation borrows
# 🚨  A PAGE THAT DERIVES EVERY FIGURE CAN STILL TYPE A CLAIM ABOUT
# ITSELF, AND THIS ONE DID.  The Verification footer told every reader that
# "the transfer, the tankage, the mass cascade and its fixed point, the
# electric stage, the plant, the knapsack, the clock, the ceilings and the
# whole cost cascade are written out from the equations here, not called out
# of the pipeline", and that "what it reads from the model is reference data
# and table accessors".  That was FALSE in four places, three of them inside
# things the same sentence NAMES:
#
#   the plant  -> `eclipse_effective_w_per_kg`, the night-side derate, whose
#                 battery term is about a third of the plant mass
#   the clock  -> `synodic_period_yr`, Kepler plus a cap that BINDS
#   the price  -> `delivered_cost_usd_per_kg`, printed in the substitution
#                 table three paragraphs below the chain that derives it
#   the ladder -> `_programme_ladder_cached`, which the module docstring also
#                 denied while `programme_ladder`'s own docstring, twelve
#                 hundred lines below, explained why it is deliberate
#
# The first two are written out now.  The third prints its own answer.  The
# fourth stays, because reproducing the search's SHAPE by hand would be a
# second opinion about what the search proposed rather than a check on what it
# concluded -- so it is DISCLOSED instead, which is the thing a footer denying
# it could never do.
#
# ⚠️  THE LESSON IS NARROWER THAN "DERIVE EVERYTHING" AND IS THE ONE THIS
# REPO KEEPS ARRIVING AT: a claim about a number rots exactly like the number,
# and nothing was checking this one because it carries no digit.  Check 14
# reads every digit reaching prose; it cannot read a sentence that asserts
# which functions a file calls.  So the sentence is DERIVED now, off the
# register below, by walking this file's own AST.  Add a borrow and the
# footer says so on the next render whether or not anybody edits it.

# Every attribute of `master` this file may touch, and what kind of borrowing
# it is.  ⚠️  `data` is a reference table, a config or an accessor into one:
# the footer's claim covers these and they need no disclosure.  `shape` is a
# DECISION borrowed on purpose, and the footer names every one of them.
#
# ⚠️  ADD A ROW WHEN YOU HAVE DECIDED TO BORROW, never to quiet a red line.
# A row nothing matches is a permission still being granted for a call
# somebody has since removed, which is how an allowlist stops being a decision
# -- the same rule `TYPED_OK` is under.
BORROWED = {
    "CALC_CONFIG": ("data", "the run's own config"),
    "DELIVERY_ARCHITECTURES": ("data", "the destination table"),
    "FRACTION_TO_MINERAL": ("data", "composition column -> mineral name"),
    "RARE_METAL_ELEMENTS": ("data", "which elements price as rare metals"),
    "TAXONOMY_COMPOSITION": ("data", "Module 1's taxonomy fractions"),
    "_DELIVERY_LEGS": ("data", "the leg chain `delivery_chain` walks itself"),
    "_LEO_USD_PER_KG": ("data", "Module 3's launch price"),
    "_PHASE_MARKET_ALIAS": ("data", "phase -> market key"),
    "_RESIDUAL_PHASE": ("data", "the name of the composition residual"),
    "_load_csv": ("data", "the CSV loader, so the tables are read as the run read them"),
    "_ops_value": ("data", "a row out of the operational table"),
    "window_phasing_au": ("data", "a lookup into DELIVERY_ARCHITECTURES"),
    "delivered_cost_usd_per_kg": (
        "data", "compared against this file's own chain, never printed"),
    "_market_mode": ("shape", "which market model the ladder is keyed on"),
    "_programme_ladder_cached": (
        "shape", "which (N, F, W) the search proposed; every value is priced here"),
    "_fleet_refinement_cached": (
        "shape", "the fleet refinement pass around the coarse winner"),
}


def model_borrows(path=None):
    """What this file takes from `master`, and anything not on the register.

    Walks the AST rather than grepping, so an alias (`import master as _m`) is
    followed and a `master` in a comment or a docstring is not counted.
    Returns `(borrows, findings)`: the first is what the footer discloses, the
    second is what a checker fails on.

    ⚠️  THE SECOND LIST HAS TWO HALVES AND BOTH ARE FINDINGS.  A call with
    no row is a borrowing nobody decided; a row with no call is a decision
    nobody has read since the call went away.
    """
    import ast
    if path is None:
        path = os.path.abspath(__file__)
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    aliases = {a.asname or a.name for node in ast.walk(tree)
               if isinstance(node, ast.Import)
               for a in node.names if a.name == "master"}
    owner = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                owner.setdefault(n, node.name)
    seen = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in aliases):
            seen.setdefault(node.attr, []).append(
                (node.lineno, owner.get(node.lineno, "<module>")))
    findings = []
    for attr in sorted(seen):
        if attr not in BORROWED:
            where = ", ".join("%s:%d" % (fn, ln) for ln, fn in seen[attr])
            findings.append(
                (seen[attr][0][0], attr,
                 "borrowed from the model and on no register row (%s)" % where))
    for attr in sorted(set(BORROWED) - set(seen)):
        findings.append((0, attr, "on the register and borrowed nowhere: %s"
                         % BORROWED[attr][1]))
    borrows = {a: BORROWED[a] for a in seen if a in BORROWED}
    return borrows, findings


def borrowed_shape(path=None):
    """The `shape` borrows alone, as (name, why) pairs, for the footer.

    Sorted, because the footer is prose and prose that reorders itself between
    renders is a diff nobody can read.
    """
    borrows, _findings = model_borrows(path)
    return sorted((name, why) for name, (kind, why) in borrows.items()
                  if kind == "shape")


# ─────────────────────────────────────────────────── the typed-number lint
# 🚨  A NUMBER IN PROSE IS A NUMBER WAITING TO ROT, AND THIS DOCUMENT HAS
# ALREADY SHIPPED TWO.  The composition sentence asserted that Module 1's
# fractions "sum to between 0.73 and 0.96" and the power note that solar and a
# radioisotope source "cross near 3.46 AU"; both were correct on the day they
# were written, neither was ever executed, and the first pair had already been
# WRONG at birth elsewhere in this repo -- 0.76 for four years, because
# somebody read the `C` row and generalised it to the complex.  The document
# whose whole claim is that nothing in it is typed was rendering both to a
# reader.
#
# The remedy this repo prescribes for a number nothing checks is a checker or
# a deletion, never a correction.  Both of those became derivations; this is
# what stops the third one arriving.  It reads the renderer's own source and
# fails on any digit reaching PROSE -- `para`, `note` and a heading -- that is
# not on the register below.
#
# ⚠️  PROSE, NOT ARITHMETIC.  A `deriv` row exists to show `365.25 * 24 *
# 3600`, and an `eq` block exists to show the equation's own constants; a
# lint that flagged those would be asking the page to stop being a
# derivation.  The distinction is what the number is DOING: a substitution
# displays a constant the reader is meant to check, a sentence asserts one
# they are meant to believe.
PROSE_CALLS = ("para", "note")

# A digit that survives in prose, and why it is allowed to.  ⚠️  ADD A ROW
# WHEN YOU HAVE DECIDED TO KEEP THE NUMBER, never to quiet a red line.  Each
# row is a claim that the value cannot go stale -- because it is definitional,
# because it names something outside this model, or because it is symbolic.
TYPED_OK = {
    "1": "symbolic or a name: 1 AU, 1/r2, (R - 1), Module 1",
    "2": "symbolic or a name: the exponent in 1/r2, Stage 2",
    "1.0": "breakeven, which is what the ratio MEANS rather than a measurement",
    "1.5": "DOE Pu-238 production, kg/yr: a fact about the world, not this model",
    "1.21": "calc 1.21.0, naming the release that shipped the hard ceiling",
    "2026": "the 2026-09 campaign, naming a measurement rather than making one",
}


def prose_numbers(path=None):
    """Every digit-bearing token the renderer writes into a SENTENCE.

    Walks the source rather than the page, because the page cannot tell a
    number that was derived from one that was typed -- they render
    identically, which is the whole difficulty.  A format string reaching
    `para` counts; its `%s` holes do not, because those are the derived half.
    """
    import ast
    if path is None:
        path = os.path.join(CAMP, "worked_calculation_doc.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    token = re.compile(r"(?<![\w.#-])\d[\d,]*(?:\.\d+)?(?![\w])")
    found, used = [], set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in PROSE_CALLS):
            continue
        for inner in ast.walk(node):
            if not (isinstance(inner, ast.Constant)
                    and isinstance(inner.value, str)):
                continue
            for match in token.finditer(inner.value):
                word = match.group(0)
                if word in TYPED_OK:
                    used.add(word)
                    continue
                context = inner.value[max(0, match.start() - 60):
                                      match.end() + 60]
                found.append((inner.lineno, word,
                              " ".join(context.split())))
    # 🚨  AND A REGISTER ROW NOTHING MATCHES IS A ROW NOBODY READ.  The
    # register is a list of numbers the document has AGREED to keep typed, so
    # an entry with nothing behind it is a permission still being granted for
    # a sentence that has since been rewritten -- which is how an allowlist
    # quietly stops being a decision and starts being a way past the check.
    for word in sorted(set(TYPED_OK) - used):
        found.append((0, word, "on the register and in no sentence: %s"
                      % TYPED_OK[word]))
    return found


def audit_verdict(incomplete, typed):
    """The one-line verdict, naming which of the two complaints was raised."""
    if incomplete and typed:
        return "*** THE PAGE IS INCOMPLETE AND ASSERTS A TYPED NUMBER ***"
    if incomplete:
        return "*** THE PAGE IS INCOMPLETE ***"
    return "*** THE PAGE ASSERTS A NUMBER NOTHING DERIVES ***"


def report_audit(row, html_text, quiet=False):
    """Run the audit against the rendered page and print what it finds.

    `quiet` returns the counts and prints nothing, which is what `--sweep`
    needs: one line per mission rather than eight, with the detail a run away
    for any mission that reports a finding.

    Returns `(incomplete, typed)`, kept apart because they are different
    complaints and one message cannot carry both: a missing column or rate
    means the page does not SHOW something, and a typed number means it shows
    something it should not have been able to assert.  Folding them into one
    total made a prose finding print "THE PAGE IS INCOMPLETE" about a page
    that is complete.
    """
    say = (lambda *a: None) if quiet else print
    text = rendered_text(html_text)
    numbers = page_numbers(text)
    cols = audit_columns(row, text, numbers, skip=not_shown(row))
    rates = audit_rates(text, numbers)
    say("  page      %d numbers, %d distinct"
          % (len(numbers), len(set(n for n, _ in numbers))))
    say("  columns   %d of %d non-zero shown, %d zero or blank, %d not "
          "expected" % (len(cols["shown"]),
                        len(cols["shown"]) + len(cols["missing"]),
                        len(cols["zeros"]), len(cols["exempt"])))
    tally = {}
    for _column, how in cols["shown"] + [(t, h) for t, _f, _v, h
                                         in rates["shown"]]:
        tally[how] = tally.get(how, 0) + 1
    say("  matched   %s"
          % ", ".join("%s %d" % (how, n)
                      for how, n in sorted(tally.items(), key=lambda kv:
                                           -kv[1])))
    for column, value in cols["missing"]:
        say("     ! column not on the page  %-34s %r" % (column, value))
    say("  rates     %d of %d reference constants shown"
          % (len(rates["shown"]), len(rates["shown"]) + len(rates["missing"])))
    for table, field, value in rates["missing"]:
        say("     ! rate not on the page    %-34s %r  (%s)"
              % (field, value, table))
    hits, moved = discrimination(row, text, numbers)
    say("  matcher   %d of %d values still matched after moving every one "
          "by %.1f%%" % (hits, moved, (PERTURBATION - 1.0) * 100.0))
    typed = prose_numbers()
    say("  prose     %d typed number(s) in a sentence, %d on the register"
          % (len(typed), len(TYPED_OK)))
    for line, word, context in typed:
        where = ("line %d" % line) if line else "on the register, unused"
        say("     ! number typed in prose    %-10s %s: %s"
              % (word, where, context[:90]))
    return len(cols["missing"]) + len(rates["missing"]), len(typed)


# ---------------------------------------------------------------- the sweep
# The axes a document's PROSE branches on, plus the two that decide which
# cascade runs at all.  This is the coverage question, and it is not the same
# question as either audit: those ask whether ONE page is right and whole, this
# asks how much of the space of pages has ever been rendered.
SWEEP_AXES = ("dest", "beneficiated", "searched", "aero", "isru", "power",
              "apsis", "electric", "plant", "capture", "market", "terms")
# 🚨  AN AXIS IS A BRANCH THE PAGE TAKES, NOT A FACT ABOUT THE
# MISSION.  `plant` and `capture` were added when the renderer's own line
# coverage showed 28 lines no swept mission had ever rendered: the zero-plant
# section, which only a raw mission carrying no ice reaches, and the propulsive
# Earth or LEO return, which every aerocaptured mission skips.  Both were
# invisible to a cover built from `aero` and `beneficiated` alone, because
# those were satisfied by OTHER missions -- a raw ISRU mission covers "raw",
# and an aerocaptured LEO mission covers "leo".
#
# 🚨  AND `market` IS WHY THE SAME SWEEP COVERED DIFFERENT LINES
# TWICE RUNNING.  The sale section branches on the market MODEL, on whether a
# ceiling bound the load, and on whether the surplus past it sold -- none of
# which is an architecture, so two covers that both satisfied every
# architectural axis exercised different halves of it, and the second reported
# MORE uncovered lines than the first.  A coverage report that moves when
# nothing moved is a coverage report nobody can act on.


def sweep_signature(row):
    """A row's coverage signature: its shape, its destination and its size.

    Built on `row_shape` rather than beside it, so the axes a sweep covers are
    the axes the renderer branches on, by construction rather than by memory.

    🚨  THIS IS THE AUTHORITY AND `scan_shapes` IS AN
    OPTIMISATION.  The scan reads the same eight axes off raw CSV columns
    because parsing whole rows to sort them is what made the first sweep
    unaffordable, and two readings of one definition is exactly how a
    definition drifts.  So the sweep checks: every mission it derives has its
    scanned signature compared against this one, on the parsed row, and a
    disagreement is a failure rather than a curiosity.
    """
    sig = dict(row_shape(row))
    sig["dest"] = row_destination(row)
    sig["searched"] = float(row.get("programme_missions") or 1) > 1
    sig["plant"] = float(row.get("power_system_kg") or 0.0) > 0.0
    sig["capture"] = "%s/%s" % (sig["dest"], "aero" if sig["aero"] else "prop")
    # 🚨  THE OPTIONAL TERMS ARE BRANCHES, AND `terms_in_force`
    # IS THEIR LIST.  Insurance has a paragraph, a cost line and a rate of its
    # own; so do reliability, the learning curve and the cost of capital.  None
    # of them is an architecture, so a cover built from architectures alone
    # never asked for a page that charges any of them -- and every cell on disk
    # has all four switched off, which is why those sections had never rendered
    # at all.  With this axis a `--source` cell that charges one is picked.
    sig["terms"] = term_state(row)
    sig["market"] = market_state(
        str(row.get("market_model") or "capacity_cap"),
        float(row.get("market_clearing_fraction") or 1.0),
        float(row.get("surplus_payload_kg") or 0.0),
        float(row.get("unsold_payload_kg") or 0.0))
    return tuple((k, sig[k]) for k in SWEEP_AXES)


def term_state(row):
    """Which optional cost terms a row carries, as the page branches on them.

    The same four `terms_in_force` infers, read the same way: each has a
    diagnostic column that sits at its inert value when the term is off.
    """
    def num(name, default):
        """One column as a float, with a default for absent or blank."""
        value = row.get(name)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    return "%s%s%s%s" % (
        "i" if num("launch_insurance_cost_usd", 0.0) > 0.0 else "-",
        "r" if num("p_success", 1.0) < 1.0 else "-",
        "l" if num("learning_curve_factor", 1.0) != 1.0 else "-",
        "w" if num("wacc_multiplier_upfront", 1.0) != 1.0 else "-")


def market_state(mode, clearing, surplus_kg, unsold_kg):
    """How the load SOLD, as the sale section branches on it.

    Three questions, and the page reads differently for each answer: which
    market model priced it, whether a ceiling bound the load at all, and
    whether what was past the ceiling sold at a discount or was abandoned.
    The milligram floor is the one `verify.py` check 7 takes, because both mass
    columns are formed by subtraction and a hold the ceilings did not shrink
    leaves a ULP rather than a zero.
    """
    tail = ("surplus" if surplus_kg > 1e-6 else
            "unsold" if unsold_kg > 1e-6 else "whole")
    return "%s/%s/%s" % (mode, "bound" if clearing < 1.0 else "clear", tail)


def _sig_from_cells(cells, idx):
    """The signature of one CSV row, from raw cells by column index.

    ⚠️  THE REFERENCE IMPLEMENTATION, kept because `scan_shapes`
    was rewritten to read the same answer out of pandas and the two were
    compared on a real archive before the faster one was trusted.  A rewrite
    proved against nothing is a rewrite whose bugs look like data.  These are
    the same fields `row_shape` reads, taken as text.
    """
    def num(name, default=0.0):
        """One cell as a float, or `default` when it is blank or absent."""
        try:
            return float(cells[idx[name]]) if name in idx else default
        except (ValueError, IndexError):
            return default

    def flag(name):
        """One cell as a bool, the way a CSV spells one."""
        return str(cells[idx[name]]).strip().lower() in ("true", "1")

    return (("dest", cells[idx["delivery_destination"]]),
            ("beneficiated", flag("beneficiation")),
            ("searched", num("programme_missions", 1.0) > 1.0),
            ("aero", flag("aerocapture_return")),
            ("isru", flag("isru_return")),
            ("power", cells[idx["power_source"]]),
            ("apsis", cells[idx["rendezvous_apsis"]]),
            ("electric", (num("ep_thrust_yr") > 0.0 if "ep_thrust_yr" in idx
                          else num("dv_penalty_factor", 1.0) > 1.0)),
            ("plant", num("power_system_kg", 0.0) > 0.0),
            ("terms", "%s%s%s%s" % (
                "i" if num("launch_insurance_cost_usd", 0.0) > 0.0 else "-",
                "r" if num("p_success", 1.0) < 1.0 else "-",
                "l" if num("learning_curve_factor", 1.0) != 1.0 else "-",
                "w" if num("wacc_multiplier_upfront", 1.0) != 1.0 else "-")),
            ("market", market_state(
                cells[idx["market_model"]] if "market_model" in idx
                else "capacity_cap",
                num("market_clearing_fraction", 1.0),
                num("surplus_payload_kg", 0.0),
                num("unsold_payload_kg", 0.0))),
            ("capture", "%s/%s" % (cells[idx["delivery_destination"]],
                                   "aero" if flag("aerocapture_return")
                                   else "prop")))


def scan_shapes(path, chunk_rows=250_000):
    """The cheapest mission of each distinct architecture in one Stage 4 output.

    🚨  PARSED BY pandas, NOT BY `csv.reader`.  The first version
    of this read every field of every row in Python to look at eight of them,
    and a five-source sweep was still scanning after forty minutes -- which
    makes a ritual of the command that exists to replace one.  This reads only
    the columns the axes need, in chunks, and reduces each chunk with a
    groupby: the architectures are what survive, so memory is the number of
    ARCHITECTURES rather than the number of rows either way.

    ⚠️  THE VALUES MUST BE THE ONES `_sig_from_cells` PRODUCES, not
    merely equivalent ones: a signature is a dict key, and `"True"` and `True`
    are different keys.  The two implementations were compared on a real
    archive before this one replaced the other.

    Returns `({signature: (objective, designation)}, any_beneficiated, rows)`.
    The second is the file's own answer to a question a declining row cannot
    settle about itself (see `run_setting`); the third is the evaluable
    population, counted here because the pass is already reading every row and
    the page quotes it.
    """
    need = ("designation", "total_cost_usd", "gross_value_usd",
            "delivery_destination", "beneficiation", "power_source",
            "rendezvous_apsis")
    optional = ("aerocapture_return", "isru_return", "dv_penalty_factor",
                "programme_missions", "ep_thrust_yr")
    head = pd.read_csv(path, nrows=0)
    for column in need:
        if column not in head.columns:
            # Not a skip.  A file without these is not a Stage 4 output, and a
            # sweep that quietly scanned nothing would print the same clean
            # line as one that scanned everything.
            sys.exit("%s has no %r column; it is not a Stage 4 catalog"
                     % (os.path.basename(path), column))
    optional = optional + ("power_system_kg", "market_model",
                           "market_clearing_fraction", "surplus_payload_kg",
                           "unsold_payload_kg", "launch_insurance_cost_usd",
                           "p_success", "learning_curve_factor",
                           "wacc_multiplier_upfront")
    usecols = list(need) + [c for c in optional if c in head.columns]

    def truthy(frame, column):
        """One column as the bools a CSV spells, absent reading as False."""
        if column not in frame.columns:
            return pd.Series(False, index=frame.index)
        return frame[column].astype(str).str.strip().str.lower().isin(
            ("true", "1"))

    def number(frame, column, default):
        """One column as floats, with `default` for absent, blank or unparseable."""
        if column not in frame.columns:
            return pd.Series(default, index=frame.index, dtype=float)
        return pd.to_numeric(frame[column], errors="coerce").fillna(default)

    best, any_benef, rows = {}, False, 0
    reader = pd.read_csv(path, usecols=usecols, chunksize=chunk_rows,
                         low_memory=False, dtype={"designation": str})
    for chunk in reader:
        rows += len(chunk)
        value = number(chunk, "gross_value_usd", 0.0)
        cost = number(chunk, "total_cost_usd", 0.0)
        keep = value > 0.0
        if not keep.any():
            continue
        chunk = chunk[keep]
        benef = truthy(chunk, "beneficiation")
        any_benef = any_benef or bool(benef.any())
        axes = pd.DataFrame({
            "dest": chunk["delivery_destination"].astype(str),
        "plant": number(chunk, "power_system_kg", 0.0) > 0.0,
            "beneficiated": benef,
            "searched": number(chunk, "programme_missions", 1.0) > 1.0,
            "aero": truthy(chunk, "aerocapture_return"),
            "isru": truthy(chunk, "isru_return"),
            "power": chunk["power_source"].astype(str),
            "apsis": chunk["rendezvous_apsis"].astype(str),
            "electric": (number(chunk, "ep_thrust_yr", 0.0) > 0.0
                         if "ep_thrust_yr" in chunk.columns
                         else number(chunk, "dv_penalty_factor", 1.0) > 1.0),
        }, index=chunk.index)
        axes["capture"] = (axes["dest"] + "/"
                           + axes["aero"].map({True: "aero", False: "prop"}))
        mode = (chunk["market_model"].astype(str) if "market_model"
                in chunk.columns else pd.Series("capacity_cap",
                                                index=chunk.index))
        clearing = number(chunk, "market_clearing_fraction", 1.0)
        surplus = number(chunk, "surplus_payload_kg", 0.0)
        unsold = number(chunk, "unsold_payload_kg", 0.0)
        axes["market"] = [market_state(m, c, s_kg, u_kg) for m, c, s_kg, u_kg
                          in zip(mode, clearing, surplus, unsold)]
        flags = zip(number(chunk, "launch_insurance_cost_usd", 0.0) > 0.0,
                    number(chunk, "p_success", 1.0) < 1.0,
                    number(chunk, "learning_curve_factor", 1.0) != 1.0,
                    number(chunk, "wacc_multiplier_upfront", 1.0) != 1.0)
        axes["terms"] = ["".join(c if on else "-" for c, on
                                 in zip("irlw", row_flags))
                         for row_flags in flags]
        axes["_obj"] = (cost[keep] / value[keep])
        axes["_des"] = chunk["designation"].astype(str)
        winners = axes.loc[axes.groupby(list(SWEEP_AXES), dropna=False,
                                        observed=True)["_obj"].idxmin()]
        for _i, row in winners.iterrows():
            sig = tuple((axis, row[axis]) for axis in SWEEP_AXES)
            obj = float(row["_obj"])
            if sig not in best or obj < best[sig][0]:
                best[sig] = (obj, str(row["_des"]))
    return best, any_benef, rows


def rows_for(path, designations, population=None):
    """Full rows for several bodies out of one Stage 4 output, in ONE pass.

    🚨  ONE PASS PER SOURCE, NOT ONE PER MISSION.  `--sweep` picks
    its missions from a scan and then needs each winner's whole row.  Asking
    `archived_winner` for them re-streamed a 350-500 MB archive once per
    mission, and `catalog_row` re-streamed 1.1 GB, which is where the first
    sweep's forty minutes went: the scans themselves are seconds.

    `population` is attached to each row the way `archived_winner` attaches it,
    because the document quotes what its subject was the best OF.
    """
    opener = gzip.open if path.endswith(".gz") else open
    wanted = [(str(d), "%s," % str(d)) for d in dict.fromkeys(designations)]
    hits = []
    with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
        header = fh.readline()
        for line in fh:
            for _d, needle in wanted:
                if needle in line:
                    hits.append(line)
                    break
    frame = pd.read_csv(_lines(header, hits), low_memory=False,
                        float_precision="round_trip",
                        dtype={"designation": str})
    out = {}
    for des, _needle in wanted:
        hit = frame[frame["designation"] == des]
        if len(hit) != 1:
            sys.exit("expected one row for %s in %s, found %d"
                     % (des, os.path.basename(path), len(hit)))
        row = hit.iloc[0]
        if population is not None:
            row.attrs["population"] = int(population)
            row.attrs["rows"] = int(population)
        out[des] = row
    return out


def source_label(path):
    """A name for one Stage 4 output that another one cannot collide with.

    🚨  EVERY STAGE 4 CATALOG IS CALLED `profitability_catalog.csv`,
    so a sweep that keyed its sources by basename silently merged the live
    catalog with every `--source` cell: one entry survived, rows were fetched
    from whichever path won, and the architectures the other cells were passed
    in FOR came out of the wrong file.  The directory is what distinguishes
    them, so the label carries it.
    """
    parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
    name = os.path.basename(path)
    if os.path.abspath(path) == os.path.abspath(CATALOG):
        return name
    return "%s/%s" % (parent, name)


def sweep_sources(extra=None):
    """Where architectures can be found, in the order that reaches most.

    The live catalog first, because it is the current release and the page
    people actually get; then the archived cells, ordered so that each new one
    reaches a DESTINATION none before it did, then an ore state or programme
    setting none before it did, and repeats last.  The ledger names all three
    per cell, so the spread is known before anything is opened -- which matters,
    because opening one costs a pass over 350-500 MB.
    """
    sources = []
    # ⚠️  NAMED SOURCES FIRST, because a caller who passes one is
    # asking for exactly it.  This is how a branch that NOTHING on disk reaches
    # gets rendered at all: three of the renderer's sections belong to terms
    # every archived cell has switched off -- insurance, the unbounded and
    # single-mission market models -- so the only way to exercise them is a
    # small cell run with them ON, written somewhere harmless and passed here.
    for path in (extra or []):
        if not os.path.exists(path):
            sys.exit("no Stage 4 output at %s" % path)
        sources.append(("catalog", source_label(path), path, open))
    if os.path.exists(CATALOG):
        sources.append(("catalog", source_label(CATALOG), CATALOG, open))
    rows = ledger_rows() if os.path.exists(LEDGER) else []
    ordered = sorted(rows, key=lambda r: (r.get("destination") or "",
                                          r.get("ore") or "",
                                          r.get("search") or ""))
    # ⚠️  THREE WAVES, BECAUSE A DESTINATION IS NOT THE ONLY
    # AXIS.  Ordering by new destination alone filled every slot a default
    # sweep has with the seven destinations' first cells, which are all
    # search-off -- so `searched` never appeared on disk and the sweep reported
    # a covered space it had not looked at.  A new ore state or programme
    # setting is worth a slot too, and anything left over is a repeat.
    seen_dest, seen_mode = set(), set()
    waves = []
    for r in ordered:
        archive = os.path.join(CAMP, "cells", "%s.csv.gz" % r["cell"])
        if not os.path.exists(archive):
            continue
        dest = r.get("destination") or ""
        mode = (r.get("ore") or "", r.get("search") or "")
        if dest not in seen_dest:
            wave, seen_dest = 0, seen_dest | {dest}
        elif mode not in seen_mode:
            wave = 1
        else:
            wave = 2
        seen_mode.add(mode)
        waves.append((wave, r["cell"], archive))
    for _wave, cell, archive in sorted(waves, key=lambda w: w[0]):
        sources.append(("cell", cell, archive, gzip.open))
    return sources


def sweep_candidates(max_sources, extra=None):
    """Every architecture the scanned sources hold, with its best mission.

    Returns the architectures, and per source what the scan learned about the
    file: its path, its evaluable population, and whether it is the output of a
    beneficiated run -- the one thing a declining row cannot say about itself.
    See `run_setting`.
    """
    found, about = {}, {}
    # 🚨  THE CAP IS ON WHAT WAS DISCOVERED, NEVER ON WHAT WAS
    # ASKED FOR.  `sweep_sources` puts named sources first and says, in as many
    # words, that "a caller who passes one is asking for exactly it" -- and a
    # plain `[:max_sources]` over the whole list then threw them away again.
    # With `--max-sources 1` and four `--source` arguments, three were silently
    # dropped and the sweep reported a clean cover of a space it had never
    # opened, which is the one failure mode a coverage tool has that matters.
    #
    # ✅  AND IT MAKES `--max-sources 0` MEAN SOMETHING USEFUL: sweep
    # the named sources and nothing else, which skips the pass over the 1.1 GB
    # live catalog and every 350-500 MB archive.  That is what turns the
    # optional-term sweep from a half-hour job into a cheap one.
    named = len(extra or [])
    sources = sweep_sources(extra)
    sources = sources[:named] + sources[named:named + max(0, max_sources)]
    for kind, name, path, _opener in sources:
        print("  scanning  %s" % name)
        shapes, any_benef, rows = scan_shapes(path)
        about[path] = {"path": path, "beneficiated": any_benef, "rows": rows,
                       "kind": kind, "label": name}
        for sig, (obj, des) in shapes.items():
            if sig not in found or obj < found[sig][0]:
                found[sig] = (obj, kind, path, des)
    return found, about


def cover(found, max_shapes):
    """The smallest set of missions that shows every axis value at least once.

    Greedy set cover over (axis, value) pairs, cheapest mission breaking ties,
    which keeps each entry the best mission of its kind rather than an
    arbitrary one.

    🚨  IT IS A COVER, NOT A SAMPLE.  Deriving every architecture on disk
    would be hundreds of documents; deriving one per axis VALUE is what answers
    "has this cascade ever run on an RTG mission at all", which is the question
    a hand-picked ritual of four shapes could not answer and never claimed to.
    """
    want = {}
    for sig in found:
        for axis, value in sig:
            want.setdefault(axis, set()).add(value)
    todo = {(axis, value) for axis, values in want.items() for value in values}
    chosen = []
    while todo and len(chosen) < max_shapes:
        def gain(item):
            """Sort key: most uncovered pairs first, cheapest mission on a tie."""
            return (-len([p for p in item[0] if p in todo]), item[1][0])
        sig, (obj, kind, name, des) = min(found.items(), key=gain)
        new = [p for p in sig if p in todo]
        if not new:
            break
        chosen.append((sig, obj, kind, name, des))
        todo -= set(new)
        del found[sig]
    return chosen, todo, want


def describe_signature(sig):
    """One line naming the architecture a swept mission flies."""
    d = dict(sig)
    return " | ".join([
        str(d["dest"]),
        "beneficiated" if d["beneficiated"] else "raw",
        "searched" if d["searched"] else "N = 1",
        "aerocapture" if d["aero"] else "propulsive",
        "ISRU" if d["isru"] else "propellant bought",
        "plant" if d["plant"] else "no plant",
        str(d["market"]),
        "terms " + str(d["terms"]),
        str(d["power"]),
        str(d["apsis"]),
        "electric" if d["electric"] else "chemical"])


def ore_of(path):
    """The ore state the campaign recorded for one archived cell, or None.

    Takes the archive PATH, because a sweep keys its sources by path: every
    Stage 4 catalog shares one basename and only the path tells two apart.

    The ledger is the only surviving statement of a run's `use_beneficiation`
    for an archived row that declined to concentrate; see `run_setting`.
    """
    cell = os.path.basename(path)
    for suffix in (".csv.gz", ".csv"):
        if cell.endswith(suffix):
            cell = cell[:-len(suffix)]
    led = next((r for r in ledger_rows() if r["cell"] == cell), None)
    if not led or not led.get("ore"):
        return None
    return led["ore"].strip().lower().startswith("benef")


def renderer_lines():
    """Every line of the renderer that COULD execute, from its own code objects.

    Read out of the compiled module rather than by parsing it, so a line that
    carries no code -- a blank, a comment, the continuation of an expression --
    is never counted as unrendered.  Every function and comprehension is a code
    object of its own, and they are walked recursively.

    ⚠️  THE MODULE'S OWN LINES ARE NOT IN IT, and leaving them in
    made every `def` and every module constant read as never rendered: they run
    at IMPORT, which is before any tracer is installed, so they would be 185
    findings that are nothing but the shape of the measurement.  The question
    is which lines of the renderer's FUNCTIONS have ever run.
    """
    import dis
    import io
    import worked_calculation_doc as doc
    top = compile(io.open(doc.__file__, encoding="utf-8").read(),
                  doc.__file__, "exec")
    # 🚨  A MODULE-LEVEL COMPREHENSION IS NOT A BRANCH.  It has a
    # code object of its own and it runs at import, so it can never be traced
    # and would sit in the report forever as one line nobody can cover.  A
    # comprehension INSIDE a function is wanted, and it arrives through its
    # parent, so the filter is only on what the module itself holds.
    inner = ("<genexpr>", "<listcomp>", "<dictcomp>", "<setcomp>")
    seen, todo = set(), [c for c in top.co_consts
                         if hasattr(c, "co_code") and c.co_name not in inner]
    while todo:
        code = todo.pop()
        for _offset, line in dis.findlinestarts(code):
            if line:
                seen.add(line)
        todo += [c for c in code.co_consts if hasattr(c, "co_code")]
    return seen


def render_traced(out, hit):
    """Render one document, recording which renderer lines ran.

    🚨  THE PAGE IS CODE, AND ITS BRANCHES ARE THE PROSE.  A
    section whose early return no mission has ever taken is a paragraph nobody
    has read in the shape it was written for -- the `leo` chain branch sat
    wrong for as long as it sat unrendered.  `settrace` costs a factor of ten
    on a render measured in milliseconds, which is nothing beside the pass over
    the archive that fetched the row.
    """
    import sys as _sys
    import worked_calculation_doc as doc
    path = doc.__file__

    def tracer(frame, event, _arg):
        """Record every line executed in the renderer, and keep tracing.

        A `call` counts as well as a `line`: since Python 3.11 a function's
        `def` line carries its RESUME instruction, so it is an executable line
        that no line event ever reports, and counting only lines reported every
        function in the file as one line short of rendered.
        """
        if frame.f_code.co_filename == path and event in ("call", "line"):
            hit.add(frame.f_lineno)
        return tracer

    _sys.settrace(tracer)
    try:
        return doc.document(out)
    finally:
        _sys.settrace(None)


def report_coverage(hit):
    """Name the renderer's branches that no swept mission rendered.

    ⚠️  GROUPED BY FUNCTION, because a bare list of line numbers
    is a number nobody acts on.  What is actionable is "this section has a
    branch nothing on disk takes", and the answer is either a mission that
    would take it or a branch that should not be there.
    """
    import ast
    import io
    import worked_calculation_doc as doc
    source = io.open(doc.__file__, encoding="utf-8").read()
    tree = ast.parse(source)
    owner, lines = {}, source.split("\n")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                owner[n] = node.name
    executable = renderer_lines()
    missed = sorted(executable - hit)
    by_fn = {}
    for line in missed:
        by_fn.setdefault(owner.get(line, "<module>"), []).append(line)
    print("\n  RENDERER COVERAGE")
    print("    %d of %d executable lines rendered by the missions above, "
          "%d never" % (len(executable & hit), len(executable), len(missed)))
    for fn, got in sorted(by_fn.items(), key=lambda kv: -len(kv[1])):
        first = got[0]
        text = lines[first - 1].strip() if first <= len(lines) else ""
        print("    %-22s %3d line(s), first at %d: %s"
              % (fn, len(got), first, text[:66]))
    return missed


def sweep(args):
    """Derive one mission per architecture on disk, and report the coverage.

    🚨  THIS WAS A HAND-RUN RITUAL, WHICH IS TO SAY A CHECK THAT DID NOT
    EXIST.  Every release of this document has been "VERIFIED on four mission
    shapes", picked by whoever wrote the release note, rebuilt from the
    previous note each time and thrown away after -- the habit `verify.py`'s
    own header is a list of the cost of, and the one `--audit` closed for the
    completeness question one release ago.  The shapes are FOUND now: every
    architecture on disk, the cheapest mission flying each, and a cover of the
    axis values between them.

    ⚠️  A SHAPE NOTHING ON DISK FLIES IS REPORTED, NOT PASSED OVER.  The
    interesting answer is usually the empty one -- a branch the renderer
    carries that no run has ever exercised is the "unreachable branch is not a
    verified branch" case exactly -- and a sweep that reported only what it
    derived would look identical whether the space was covered or nearly bare.
    """
    found, about = sweep_candidates(args.max_sources, args.source)
    if not found:
        sys.exit("nothing to sweep: no Stage 4 catalog and no archived cell.")
    chosen, uncovered, want = cover(dict(found), args.max_shapes)
    print("  found     %d architecture(s) across %d axes"
          % (len(found), len(want)))
    print("  covering  %d mission(s)\n" % len(chosen))

    bodies = catalog_bodies([des for _s, _o, _k, _n, des in chosen])
    # One pass per SOURCE for the chosen rows; see `rows_for`.
    per_source = {}
    for _sig, _obj, _kind, path, des in chosen:
        per_source.setdefault(path, []).append(des)
    rows = {}
    for path, wanted in per_source.items():
        meta = about[path]
        rows[path] = rows_for(meta["path"], wanted, population=meta["rows"])

    failures, audited, refused, hit = 0, 0, 0, set()
    # Axis values a mission actually DERIVED.  A refusal covers nothing: it is
    # the cover's claim that fails, not only the mission, and a coverage table
    # that counted refused missions reported values whose page never rendered.
    derived_values = set()
    for sig, obj, kind, path, des in chosen:
        label = "%s  %s" % (about[path]["label"], des)
        try:
            told = ore_of(path) if kind == "cell" else None
            out = build(rows[path][des], label, body=bodies[des],
                        run_beneficiated=(told if told is not None
                                          else about[path]["beneficiated"]))
        except SystemExit as exc:
            # ⚠️  A REFUSAL IS A RESULT.  `context` declines the shapes this
            # cascade does not cover, by name, and finding out which those are
            # is half of what a sweep is for -- so it is counted and reported
            # rather than ending the run.
            print("  %-52s REFUSED" % label)
            # ⚠️  THE WHOLE MESSAGE.  A refusal names the guard
            # that fired and, where the cause is a dial this process reads from
            # the live config rather than from the row, the flag that would
            # settle it -- and printing only the first line threw exactly that
            # away, on the rows where it is the difference between a defect and
            # a release boundary.
            for line in str(exc).splitlines():
                print("      %s" % line.strip())
            refused += 1
            continue
        derived_values |= set(sig)
        c = out["check"]
        # Rendered even without `--audit`, because the coverage question is
        # about the PAGE and a mission that is only derived renders nothing.
        html = render_traced(out, hit)
        # The scan said this row was one architecture; `row_shape` says what it
        # is.  See `sweep_signature`: the scan is a fast path, not a second
        # definition, and this is what keeps it honest.
        seen = sweep_signature(rows[path][des])
        if seen != sig:
            print("  %-52s *** SCAN AND ROW DISAGREE ***" % label)
            print("      scanned %s" % describe_signature(sig))
            print("      row     %s" % describe_signature(seen))
            failures += 1
        note = ""
        if args.audit:
            incomplete, typed = report_audit(rows[path][des], html, quiet=True)
            audited += 1
            note = ("  audit clean" if not (incomplete or typed)
                    else "  *** audit: %d incomplete, %d typed ***"
                    % (incomplete, typed))
            if incomplete or typed:
                failures += 1
        if c["bad"]:
            failures += 1
        print("  %-52s %8.3fx  %d quantities, %d DIFFER%s"
              % (label, obj, c["n"], len(c["bad"]), note))
        print("      %s" % describe_signature(sig))
        for nm, ours, theirs, rel in c["bad"]:
            print("      ! %-28s derived %r  row %r  rel %.3e"
                  % (nm, ours, theirs, rel))
        # ⚠️  A SWEEP IS WHERE THIS BITES, because one
        # `--max-mining-fraction` covers every source and archived cells and
        # current ones want different ones.  Named per mission, not once.
        if c["bad"]:
            note = mining_cap_note(out["C"], out["B"])
            if note:
                for line in note.strip("\n").splitlines():
                    print("      %s" % line.strip())

    report_coverage(hit)
    print("\n  COVERAGE, over what is on disk")
    never = {(a, v) for a, values in want.items() for v in values
             if (a, v) not in derived_values}
    for axis in SWEEP_AXES:
        values = sorted(str(v) for v in want.get(axis, ()))
        missing = sorted(str(v) for a, v in never if a == axis)
        print("    %-13s %-56s%s"
              % (axis, ", ".join(values) or "-",
                 "NOT DERIVED: " + ", ".join(missing) if missing else ""))
    print("\n  %d derived, %d audited, %d refused, %d failure(s)"
          % (len(chosen) - refused, audited, refused, failures))
    if never:
        print("  %d axis value(s) on disk went underived; raise --max-shapes, "
              "or read\n  the refusals above, which say what would derive them"
              % len(never))
    return 1 if (failures or refused or never) else 0


def main():
    """Derive the best case of a run, check it, and write the document."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    # ⚠️  `default=None` RATHER THAN THE PATH, so that "the user passed
    # --catalog" is a different state from "the user passed nothing".  With the
    # path as the default they are indistinguishable, and the auto-select below
    # then overrode an EXPLICIT --catalog whenever its value happened to equal
    # the default -- which is exactly the path anyone would type.  Found by a
    # sweep whose live-catalog job silently documented an archived cell.
    ap.add_argument("--catalog", default=None,
                    help="a Stage 4 output catalog (default: the last run's)")
    ap.add_argument("--cell",
                    help="a campaign cell archive instead of a live catalog")
    ap.add_argument("--designation",
                    help="document this body instead of the run's best case")
    ap.add_argument("--pdf", action="store_true", help="also render the PDF")
    ap.add_argument("--verify", action="store_true",
                    help="derive and check only; write nothing")
    ap.add_argument("--audit", action="store_true",
                    help="also audit the rendered page for completeness")
    ap.add_argument("--out", default=os.path.join(CAMP, "worked_calculation"),
                    help="output path without an extension")
    ap.add_argument("--sweep", action="store_true",
                    help="derive one mission per architecture on disk and "
                         "report the coverage; writes nothing")
    ap.add_argument("--max-sources", type=int, default=4, metavar="N",
                    dest="max_sources",
                    help="Stage 4 outputs to scan for architectures "
                         "(default: 4); each costs a streaming pass")
    ap.add_argument("--max-shapes", type=int, default=10, metavar="N",
                    dest="max_shapes",
                    help="missions to derive in a sweep (default: 10)")
    ap.add_argument("--max-mining-fraction", type=float, default=None,
                    metavar="F", dest="max_mining_fraction",
                    help="the depletion cap the RUN used, when it is not the "
                         "live default: calc moved it from 0.05 to 1.0 in "
                         "1.23.0, and a row written before that hauls less "
                         "than this derivation would")
    ap.add_argument("--source", action="append", metavar="CSV",
                    help="another Stage 4 output for --sweep to scan, ahead of "
                         "the live catalog; repeatable. A cell run with a term "
                         "no archived cell carries is how a sweep reaches the "
                         "page's branches for it")
    args = ap.parse_args()

    # ⚠️  A DIAL SET HERE IS SET FOR THE WHOLE PROCESS, which is
    # right for one document and right for a sweep of cells from one campaign,
    # and wrong for a sweep that mixes releases -- which is why the refusal
    # NAMES it rather than this guessing per row.
    if args.max_mining_fraction is not None:
        import master
        master.CALC_CONFIG.max_mining_fraction = args.max_mining_fraction

    # A sweep answers a different question from a document and shares only the
    # derivation, so it is dispatched before any of the source-picking below:
    # there is no single subject to pick.
    if args.sweep:
        return sweep(args)

    # Where the row comes from, and nothing else, is what `--cell` changes.
    # With neither flag, every source on disk is compared and the single best
    # mission wins; see `candidate_sources`.
    if not args.cell and args.catalog is None and not args.designation:
        args.catalog = CATALOG
        found = candidate_sources(args.catalog)
        if not found:
            sys.exit("nothing to document: no Stage 4 catalog at %s and no "
                     "completed campaign cell with an archive.\nRun Stage 4, "
                     "or pass --catalog." % args.catalog)
        # 🚨  RANK WITHIN ONE RELEASE, NOT ACROSS THEM.  Naming the release
        # on both lines was the previous fix and it was half of one: the
        # ordering still put a calc 1.21.2 cell and a 1.22.0 catalog in one
        # sort, and 4.5298x at the newer stamp came out "better" than 6.6622x
        # at the older, which is a cheaper MODEL rather than a better mission.
        # A reader who saw "best case" had no way to know the comparison was
        # between two models.  The newest release present wins the tie by
        # construction now, and every older one is named and set aside, which
        # is this repo's standing rule about wall clocks applied to objectives:
        # a figure is only ever true of the release it names.
        newest = max(found, key=lambda f: _release_key(f[3]))[3]
        aside = [f for f in found if f[3] != newest]
        found = [f for f in found if f[3] == newest]
        best_obj, kind, name, release = found[0]
        for older in sorted({f[3] for f in aside}, key=_release_key,
                            reverse=True):
            best_older = min(f[0] for f in aside if f[3] == older)
            print("  set aside %d result(s) at calc %s (best %.4fx), which is "
                  "a different model" % (sum(1 for f in aside if f[3] == older),
                                         older, best_older))
        if len(found) > 1:
            # ⚠️  NAME THE RELEASE ON BOTH LINES.  The ledger is a
            # single-release artifact by design and the live catalog is
            # whatever ran last, so this ranking routinely puts two different
            # models in one ordering: 4.5298x at calc 1.22.0 came out "best"
            # over 6.6622x at 1.21.2, which is not a better mission so much as
            # a cheaper model.  The comparison is still worth making -- it is
            # how you find the document's subject -- but it has to be legible
            # as what it is.  This repo's standing rule about wall clocks
            # applies unchanged to objectives: a figure is only ever true of
            # the release it names.
            print("  compared  %d finished result(s) at calc %s; best is %s "
                  "at %.4fx" % (len(found), release, name, best_obj))
            runner = found[1]
            print("  runner-up %s at %.4fx (calc %s)"
                  % (runner[2], runner[0], runner[3]))
        elif aside:
            print("  compared  1 result at calc %s; best is %s at %.4fx"
                  % (release, name, best_obj))
        missed = unseen_archives()
        if missed:
            print("  NOT compared: %d archive(s) under a release suffix, which"
                  " this\n                selection cannot pick by design. To"
                  " document one:" % len(missed))
            for path in missed:
                print("                  --catalog %s" % path)
        if kind == "cell":
            args.cell = name
        else:
            args.catalog = name

    if args.catalog is None:
        args.catalog = CATALOG
    if args.cell:
        if args.designation:
            winner = archived_winner(args.cell, args.designation)
        else:
            row = next((r for r in ledger_rows() if r["cell"] == args.cell),
                       None)
            if row is None:
                sys.exit("no completed ledger row for cell %r; pass "
                         "--designation to name the body yourself" % args.cell)
            winner = archived_winner(args.cell, row["winner"])
        label = args.cell
    else:
        # ⚠️  THROUGH `run_winner` EVEN WHEN A BODY IS NAMED.  This
        # re-read the catalog itself and handed `build` a row carrying none of
        # the file's provenance, so the derivation inferred the run's ore
        # setting from the LIVE CONFIG.  See `run_winner`.
        winner = run_winner(args.catalog, args.designation or None)
        label = os.path.basename(args.catalog)

    # ⚠️  THE LEDGER KNOWS WHAT THE ROW CANNOT SAY.  `--cell` names a cell
    # whose ore state the campaign recorded, which is the one place the run's
    # `use_beneficiation` survives for an archived row; see `run_setting`.
    told = None
    if args.cell:
        led = next((r for r in ledger_rows() if r["cell"] == args.cell), None)
        if led and led.get("ore"):
            told = led["ore"].strip().lower().startswith("benef")
    out = build(winner, label, run_beneficiated=told)
    terms = out["terms"]
    obj = float(winner["total_cost_usd"]) / float(winner["gross_value_usd"])
    print("  source    %s" % label)
    print("  best case %s at %.4fx  (calc %s)"
          % (out["designation"], obj, terms["stamp"]))
    print("  charging  %s" % describe_terms(terms))
    print("  market    %s" % terms["market"])
    # ⚠️  A SUBSTITUTED INPUT MUST SAY SO.  The propellant price comes off
    # the row when the Stage 3 table on disk has moved since the run, which is
    # the only reason an archived chemical mission reproduces at all -- and a
    # derivation that silently used a different input from the one the reader
    # can look up would be the quietest kind of wrong.  Silent when the table
    # still agrees, which is every run on an unmoved table.
    if out["C"]["prop_moved"] is not None:
        print("  propellant %s priced off the ROW at %.12g $/kg; the Stage 3 "
              "table on disk now says %.12g, so it has been refetched since "
              "this run"
              % (str(out["C"]["pro"].raw("name")),
                 out["C"]["prop_usd_per_kg"], out["C"]["prop_moved"]))
    c = out["check"]
    print("  derived   %d quantities: %d bit-exact, %d within %g, %d DIFFER"
          % (c["n"], c["exact"], c["close"], c["tol"], len(c["bad"])))
    print("  worst     %.3e relative  (%s)" % (c["worst"], c["worst_name"]))
    if c["skipped"]:
        print("  skipped   %d quantity(s) the row has no column for: %s"
              % (len(c["skipped"]), ", ".join(c["skipped"])))
    for name, ours, theirs, rel in c["bad"]:
        print("     ! %-32s derived %r  row %r  rel %.3e"
              % (name, ours, theirs, rel))
    if c["bad"]:
        print("\n*** THE DERIVATION AND THE MODEL DISAGREE ***")
        # ⚠️  THE FIRST HYPOTHESIS SHOULD BE A CONFIG DIAL, NOT A DEFECT.  Most
        # of what this derivation needs it reads off the row, but a handful of
        # dials are still read from the live config, and a run made with any of
        # them set differently lands here rather than in a wrong document.
        # `terms_in_force` lists them beside the column that catches each.
        print("    Before suspecting the model or this derivation: a dial read")
        print("    from the LIVE config may disagree with the run that made")
        print("    this row.  See the table in `terms_in_force` for which")
        print("    dials those are and which column catches each.")
        # One of those dials can be RULED IN rather than merely suspected, so
        # it is named outright instead of leaving the reader the whole table.
        note = mining_cap_note(out["C"], out["B"])
        if note:
            print(note.lstrip("\n"))
        return 1
    if args.verify and not args.audit:
        print("  OK  derivation reproduces the row")
        return 0

    # ⚠️  THE AUDIT NEEDS THE PAGE, so it is rendered even under `--verify`.
    # The two questions are different and the second one cannot be asked
    # without the answer to the first: `check` asks whether the numbers are
    # right, `report_audit` asks whether they are all there.
    import worked_calculation_doc
    html = worked_calculation_doc.document(out)
    incomplete, typed = (report_audit(winner, html) if args.audit else (0, 0))
    if args.verify:
        if incomplete or typed:
            print("\n%s" % audit_verdict(incomplete, typed))
            return 1
        print("  OK  derivation reproduces the row")
        return 0
    html_path = args.out + ".html"
    with open(html_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("  wrote     %s  (%d chars)" % (html_path, len(html)))
    if args.pdf and render_pdf(html_path, args.out + ".pdf"):
        print("  wrote     %s" % (args.out + ".pdf"))
    if incomplete or typed:
        print("\n%s" % audit_verdict(incomplete, typed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
