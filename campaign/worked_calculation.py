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
                          "catalog", catalog_path))
        except SystemExit:
            pass
    if os.path.exists(LEDGER):
        for r in ledger_rows():
            if not r.get("best_obj"):
                continue
            archive = os.path.join(CAMP, "cells", "%s.csv.gz" % r["cell"])
            if os.path.exists(archive):
                found.append((float(r["best_obj"]), "cell", r["cell"]))
    return sorted(found)


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
    walled = (col("unsold_payload_kg") or 0.0) > 0.0
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


def run_winner(path):
    """The best row of a Stage 4 output catalog, by the project's objective.

    ⚠️  NOT the first row.  The file is sorted by `profit_usd` descending and
    the project ranks on `total_cost_usd / gross_value_usd`; those are
    different questions, and README says so where it documents the column
    order.  The best CASE is the lowest ratio.
    """
    if not os.path.exists(path):
        sys.exit("no catalog at %s\nRun Stage 4 first, or pass --cell to "
                 "document an archived campaign cell instead." % path)
    frame = pd.read_csv(path, low_memory=False, float_precision="round_trip",
                        dtype={"designation": str})
    if not len(frame):
        sys.exit("%s has no rows" % path)
    usable = frame[frame["gross_value_usd"] > 0]
    if not len(usable):
        sys.exit("%s has no row with positive gross value" % path)
    ratio = usable["total_cost_usd"] / usable["gross_value_usd"]
    return usable.loc[ratio.idxmin()]


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
    frame = pd.read_csv(_lines(header, hits), float_precision="round_trip",
                        dtype={"designation": str})
    frame = frame[frame["designation"] == designation]
    if len(frame) != 1:
        sys.exit("expected one row for %s in %s, found %d"
                 % (designation, cell, len(frame)))
    return frame.iloc[0]


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
    path = os.path.join(ROOT, "asteroid_pipeline", "asteroid_catalog.csv")
    if not os.path.exists(path):
        sys.exit("missing %s; run_pipeline.py --check-inputs explains this" % path)
    needle = "%s," % designation
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        header = fh.readline()
        hits = [line for line in fh if needle in line]
    frame = pd.read_csv(_lines(header, hits), low_memory=False,
                        float_precision="round_trip",
                        dtype={"designation": str})
    frame = frame[frame["designation"] == designation]
    if len(frame) != 1:
        sys.exit("expected one catalog row for %s, found %d"
                 % (designation, len(frame)))
    return frame.iloc[0]


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
    for name, frac, price, full in tiers:
        if remaining <= 0:
            break
        take = min(float(feed_kg) * frac * recovery - taken.get(name, 0.0),
                   remaining)
        if full and caps is not None:
            key = (keys or {}).get(name, name)
            allowance = caps.get(key)
            if allowance is not None:
                take = min(take, allowance)
                caps[key] = allowance - take
        # Recorded before the skip: a full tier whose allowance is spent takes
        # nothing, and if that went unrecorded its own surplus tier would be
        # read as the full one and clipped at the same exhausted allowance.
        taken[name] = taken.get(name, 0.0) + take
        if take <= 0:
            continue
        mix[name] = mix.get(name, 0.0) + take
        if not full:
            surplus += take
        total += take * price
        remaining -= take
    loaded = float(payload_kg) - remaining
    return {"mix": mix, "value": total, "loaded": loaded, "surplus": surplus,
            "usd_per_kg": total / loaded if loaded > 0 else 0.0}


def raw_hold(payload_kg, phases):
    """The hold of a run-of-mine mission: the body's own proportions.

    Nothing is chosen here, which is the whole difference from the
    beneficiated case.  A raw mission digs what it flies and flies what it
    digs, so the mix is the composition scaled to the payload, and the phase
    fractions are normalised because they sum to 0.76-0.96 rather than to 1:
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
        else:
            value += kg * price[name]
            remaining[key] = allowance - kg
    return {"mix": dict(load["mix"]), "value": value, "loaded": load["loaded"],
            "surplus": surplus, "unsold": unsold,
            "usd_per_kg": value / load["loaded"] if load["loaded"] else 0.0}


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
    w_plant, oversize = master.eclipse_effective_w_per_kg(
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
        destination=dest,
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
    return dict(m_pay=m_pay, denom=denom, bracket=bracket, m_after=m_after,
                m_rprop=m_rprop, m_at=m_at, m_oprop=m_oprop, m_tps=m_tps,
                m_prop=m_oprop + m_rprop)


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
    outbound_yr = max(0.5, 0.00023 * DV["dv_out"])
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
            return None
        hw_in = cfg.mining_hardware_kg + plant_kg + ep_kg
        cas = _cascade(C, R, hw_in, struct)
        if cas is None:
            return None
        ep = _ep_stage(C, cas["m_prop"])
        trial_pay = min(cas["m_pay"], B["mineable"],
                        max(0.0, throughput - isru_feed))
        if trial_pay <= 0:
            return None
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
                return None
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
            return None
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
        return None
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
            return None
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
        return None
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
        return None

    stay = dig_yr + DV["window_wait"]
    t_out = max(0.5, 0.00023 * DV["dv_out"])
    t_back = max(0.5, 0.00023 * DV["dv_ret"])
    chem = t_out + stay + t_back
    # The delta-v-linear cruise estimate is calibrated to CHEMICAL transfers.
    # An electric stage thrusts for most of the trip instead, so its duration
    # is governed by burn time and not by an impulsive-transfer fit; a chemical
    # stage has no such floor, and applying one would lengthen every chemical
    # mission in the model by years.
    electric_floor = (ep["thrust_yr"] + stay) if ep["thrust_yr"] > 0 else 0.0
    duration = max(1.0, chem, electric_floor)
    if duration > cfg.max_mission_duration_yr:
        return None
    cadence = max(stay, DV["synodic"])
    calendar_cap = max(1, int(C["val"]("Mining rig service life") // stay))
    trips = (min(calendar_cap, int(C["val"]("Mining rig maximum trips")))
             if C["rig_trip_limit"] else calendar_cap)
    return {"R": R, "passes": passes, "cascade": cas, "ep": ep, "m_tps": m_tps,
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
    a_dest = master.window_phasing_au(C["cfg"].delivery_destination)
    t_ast = C["a_au"] ** 1.5
    synodic = master.synodic_period_yr(C["a_au"], a_dest)
    return {"t_ast": t_ast, "a_dest": a_dest, "synodic": synodic,
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
    lost = (capped["unsold"] if "unsold" in capped
            else max(0.0, free["loaded"] - capped["loaded"]))
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

    prop_cost = float(C["pro"]["cost_usd_per_kg"])
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
        "ep": (M["ep"]["power"] * val("Power system (solar + battery)")
               + M["ep"]["power"] / 1000.0
               * val("Electric propulsion system recurring cost")) * lc,
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
    worst, worst_name, bad, skipped = 0.0, "", [], []
    for name, ours in sorted(derived.items()):
        if name not in archived:
            skipped.append(name)
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
            "bad": bad, "worst": worst, "worst_name": worst_name,
            "skipped": skipped}


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
        # The PURITY BOUND, and only a concentrating mission has one: the
        # richest hold obtainable is 100% of the best phase present.  A raw
        # mission cannot be concentrated past its own composition, so the model
        # leaves this at the bulk value rather than quoting a bound that does
        # not bind -- which is why this reads 4,917 and not 7,305 on a body
        # whose best phase is nickel-iron.
        "best_phase_usd_per_kg": (max(p[2] for p in C["phases"])
                                  if C["beneficiated"] else C["bulk"]),
    }


# -------------------------------------------------------------------- driver
CHROME = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
]


def build(archived, label):
    """Derive one winner end to end, and check it against its own row.

    `archived` is the row being documented, from wherever it came: a live
    Stage 4 catalog or a gzipped campaign archive.  The derivation does not
    care which, and deliberately: "the best case of this run" and "the best
    cell of that campaign" are the same question asked of different artefacts.
    """
    designation = str(archived["designation"])
    body = catalog_body(designation)
    # The prices have to be chosen before anything is derived, and they are
    # chosen by the ROW's destination rather than by the config, for the same
    # reason the legs are.  See `mineral_catalog_for`.
    tables = reference_tables(row_destination(archived))
    C = context(body, archived, tables)
    # Before anything is derived: what the ROW charges decides what the
    # derivation charges.  See `terms_in_force`.
    C["terms"] = terms_in_force(archived, C["cfg"])
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
    B = derive_body(C)
    DV = derive_dv(C)
    DV.update(derive_periods(C))
    sweep = concentration_sweep(C, B, DV)
    _kind, ratio, won = sweep["winner"]
    M, ladder = won["M"], won["ladder"]
    P = ladder["best"]
    result = check(comparable(C, B, DV, M, P, ladder), archived)
    return {"C": C, "B": B, "DV": DV, "M": M, "P": P, "ladder": ladder,
            "sweep": sweep, "ratio": ratio, "archived": archived,
            "check": result, "cell": label, "designation": designation,
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
    ap.add_argument("--out", default=os.path.join(CAMP, "worked_calculation"),
                    help="output path without an extension")
    args = ap.parse_args()

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
        best_obj, kind, name = found[0]
        if len(found) > 1:
            print("  compared  %d finished results; best is %s at %.4fx"
                  % (len(found), name, best_obj))
            runner = found[1]
            print("  runner-up %s at %.4fx" % (runner[2], runner[0]))
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
        winner = run_winner(args.catalog)
        if args.designation:
            frame = pd.read_csv(args.catalog, low_memory=False,
                                float_precision="round_trip",
                                dtype={"designation": str})
            hit = frame[frame["designation"] == args.designation]
            if not len(hit):
                sys.exit("%s is not in %s" % (args.designation, args.catalog))
            winner = hit.iloc[0]
        label = os.path.basename(args.catalog)

    out = build(winner, label)
    terms = out["terms"]
    obj = float(winner["total_cost_usd"]) / float(winner["gross_value_usd"])
    print("  source    %s" % label)
    print("  best case %s at %.4fx  (calc %s)"
          % (out["designation"], obj, terms["stamp"]))
    print("  charging  %s" % describe_terms(terms))
    print("  market    %s" % terms["market"])
    c = out["check"]
    print("  derived   %d quantities: %d bit-exact, %d within 1e-12, %d DIFFER"
          % (c["n"], c["exact"], c["close"], len(c["bad"])))
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
        return 1
    if args.verify:
        print("  OK  derivation reproduces the row")
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
