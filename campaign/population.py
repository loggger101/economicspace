# -*- coding: utf-8 -*-
"""Every per-cell POPULATION table the docs carry, from one pass over the cells.

The 2026-09 campaign extracted the winner row and ran the invariants and nothing
more, so the propellant shares, the vehicle shares, the rig's two bounds, the
cadence and the saturation diagnostics stayed 2026-08 `elasticity` figures with
insurance charged, each under a heading saying so.  Every column needed to close
that gap is already in the archived cells, so it costs a read rather than a
re-run.  This is that read.

IT IS THE AUTHORITY FOR THESE TABLES FROM THE 28-CELL CAMPAIGN ONWARD, and
`rig_bounds.py` and `extra_checks.py` are its predecessors.  They are kept
rather than deleted, for one reason that is worth stating so nobody tidies them
away: `archive-2026-08_calc-1.17.7/FINDINGS.md` names them as the scripts that
produced the 2026-08 record, so removing them would strand that sentence.  Run
THIS one for anything current.  Their definitions are carried over unchanged,
deliberately, so a 2026-08 figure recomputed here is comparable with the
committed one.

One pass rather than three is the engineering reason it exists at all: each
predecessor decompressed the same ~11 GB on its own, and the tables they produce
are read side by side in a single section of CLAUDE.md, so three passes that can
be run at three different times against three different cell sets is exactly the
shape this repo's rules are written against.

THE DENOMINATOR IS THE EVALUABLE POPULATION, AND IT IS NOT A CHOICE HERE.
`run_cell.py` archives what `build_profitability_catalog` returns, which is
already filtered, so an archived cell holds evaluable rows ONLY: cislunar raw
searched is 650,921 rows and 650,921 evaluable.  Every percentage below is
therefore over the same population every headline in the docs is quoted over,
and CLAUDE.md's warning about the two right answers for "bodies declining to
concentrate" does not reach these tables.  Do not add an `_obj > 0` filter
believing it changes something; it is kept only as the assertion that it does
not.

    py campaign/population.py            # derive; skips cells already done
    py campaign/population.py --report   # render the tables from the JSON
    py campaign/population.py --force    # re-derive everything
    py campaign/population.py --tag calc-1.22.0           # a re-measurement
    py campaign/population.py --report --tag calc-1.22.0  # and its tables

A `--tag` reads cells archived under a suffix, which is how a cell re-run at a
later release is kept on disk without being mistaken for the campaign's own.
The filter runs both ways: a tagged run sees only tagged cells and an untagged
run only untagged ones, so a re-measurement can never contribute a row to the
campaign's tables.  See `cell_paths`, which composes an exact filename rather
than searching the directory, and `UNSOLD_FLOOR_KG`, which is the one
threshold in this file that turns on float residue.
"""
import argparse
import glob
import gzip
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CELLS = os.path.join(ROOT, "campaign", "cells")
OUT = os.path.join(ROOT, "campaign", "population")

# Cheapest destination first, matching run_queue.py and analyse.py.  Reading the
# order off a list rather than sorting keeps the rendered tables in the order the
# docs already present them in.
DESTS = ["cislunar", "lunar_surface", "geo", "mars_orbit",
         "leo", "mars_surface", "earth_surface"]

# Only what a table below actually reads.  `usecols` is what keeps a cell at
# ~17 s rather than minutes, and it RAISES on a column the file does not have,
# which is the behaviour wanted here: a cell archived by an older release that
# cannot answer one of these tables should say so rather than render a blank
# column that reads as a measurement.
COLS = ["designation", "spectral_type", "total_cost_usd", "gross_value_usd",
        "propellant", "vehicle", "thrust_scaling", "max_payload_kg",
        "rig_trip_limit_binds", "cadence_window_bound", "campaign_cadence_yr",
        "programme_span_yr", "missions_per_ship", "trips_per_ship",
        "fleet_ships", "programme_missions", "programme_calendar_multiplier",
        "saturation_multiplier", "market_clearing_fraction",
        "unsold_payload_kg", "aerocapture_return", "isru_return",
        "concentration_ratio"]

# The fleet ceiling `max_fleet_ships` stops the ladder at.  A row here is the
# ladder's top rung, which is where the loop STOPPED rather than an optimum.
FLEET_CEILING = 64

# 🚨  A MILLIGRAM, AND A BARE `> 0` IS WRONG HERE BY THREE ORDERS OF MAGNITUDE.
# The payload knapsack subtracts what it sold from what it loaded, so a load
# that cleared completely leaves one ULP behind rather than an exact zero:
# measured at 1.455e-11 kg, 1.9e-16 of the payload, on the cislunar
# beneficiated searched cell.  `verify.py` check 7 already learned this and
# took a floor; this file was written afterwards and took the naive test, which
# is this repo's standing failure of fixing one half of a defect class.
#
# What it cost: the calc 1.22.0 cell reports **1,891 unsold rows on a bare test
# and 0 on this one**, and zero is the truth -- v1.22.0 sells the surplus past
# a ceiling rather than abandoning it, so the column is retired by
# construction.  A table saying 1,891 would have contradicted check 7 about the
# same population, which is exactly the two-checks-disagreeing tell this repo
# looks for.  The committed 1.21.2 figure was wrong more quietly: 65,373
# against a true 64,759, because 614 of those rows are residue and the rest are
# real abandonment.
#
# Far above any float residue and far below any mass the model can mean: the
# smallest real unsold load in the 1.21.2 cells is many kilograms.
UNSOLD_FLOOR_KG = 1e-6

# Shares below this are stored but not PRINTED.  The JSON keeps every
# distinct value because a claim can turn on a 0.01 pp difference; a table
# a person reads should not carry twenty rows of noise to say so.
DISPLAY_FLOOR = 0.05


def truthy(s):
    """A flag column as a real boolean mask, whatever the CSV made of it.

    A flag read back from CSV arrives as the STRING "True" when anything in the
    column forced object dtype, and `.astype(bool)` reads that string, and
    `NaN`, as True.  pandas happens to infer real `bool` for these columns
    today, on cells where every row states the flag; the moment one does not,
    it is object and the naive read is silently wrong for exactly the rows most
    likely to be new.  Same trap as the pipeline's own `_truthy`.
    """
    if s.dtype == object:
        return s.astype(str).str.lower().isin(["true", "1", "1.0"])
    return s.fillna(False).astype(bool) if s.isna().any() else s.astype(bool)


def pct(mask):
    """A mask as a percentage of its own length, or NaN when there is nothing."""
    return 100.0 * float(mask.mean()) if len(mask) else float("nan")


def shares(series):
    """Every distinct value of a column, as a percentage of the rows.

    NOT truncated to the commonest few, which was the first version and was
    wrong for the reason this repo keeps re-learning: a share below the cut is
    indistinguishable from a share of zero, and the docs carry a claim -- that
    ISRU tracks hydrolox to within 0.03 pp at every destination -- that is
    decided exactly there.  The grid is a few dozen vehicles and propellants
    at most, so keeping all of them costs nothing.

    Missing is dropped rather than counted: `propellant` is NaN on no row, but
    `thrust_scaling` is NaN on every chemical mission, and a share table that
    silently carries a NaN bucket reads as a propellant nobody can name.
    """
    v = series.dropna()
    if not len(v):
        return []
    return [(str(k), 100.0 * int(n) / len(series)) for k, n in v.value_counts().items()]


def derive(path):
    """Every statistic the docs tables need, for one archived cell."""
    with gzip.open(path, "rb") as fh:
        # round_trip is mandatory in anything that compares or reproduces a
        # committed figure: the default float parser is fast rather than
        # correctly rounded and returns a float64 one ULP from the one written.
        d = pd.read_csv(fh, low_memory=False, float_precision="round_trip",
                        usecols=COLS)

    obj = d["total_cost_usd"] / d["gross_value_usd"]
    evaluable = int((obj.notna() & (obj > 0)).sum())

    cycle = pct(truthy(d["rig_trip_limit_binds"]))
    window = pct(truthy(d["cadence_window_bound"]))
    repl = d["thrust_scaling"].astype(str).str.lower().eq("replicated")

    # Rank of the best `replicated` mission, and how far off the winner it is.
    # The test is whether one WINS, never whether any survive: thruster_kg_per_n
    # is a mass penalty rather than a threshold, and the survivor count spans
    # 400x across destinations on one model and one catalog, so a claim built on
    # it is a statement about the population and not about the gate.
    order = obj.sort_values().index
    ranked_repl = repl.reindex(order).to_numpy().nonzero()[0]
    best_obj = float(obj.loc[order[0]])
    if len(ranked_repl):
        row = d.loc[order[ranked_repl[0]]]
        repl_best = {"rank": int(ranked_repl[0]) + 1,
                     "obj": float(obj.loc[order[ranked_repl[0]]]),
                     "margin": float(obj.loc[order[ranked_repl[0]]]) / best_obj,
                     "designation": str(row["designation"]),
                     "propellant": str(row["propellant"])}
    else:
        repl_best = None

    win = d.loc[order[0]]
    at_ceiling = d["fleet_ships"] >= FLEET_CEILING

    return {
        "rows": int(len(d)),
        "evaluable": evaluable,
        "objective": best_obj,
        "winner": {k: (None if pd.isna(win[k]) else
                       (float(win[k]) if k in ("max_payload_kg", "fleet_ships",
                                               "programme_missions",
                                               "concentration_ratio")
                        else str(win[k])))
                   for k in ("designation", "spectral_type", "propellant",
                             "vehicle", "max_payload_kg", "fleet_ships",
                             "programme_missions", "concentration_ratio")},
        # The rig's two bounds.  cycle is `max_trips`, calendar is life / stay;
        # window is the synodic period, dig is the mining rate.  Each pair is
        # exhaustive, so only one of each is stored and the doc table prints
        # both halves.
        "cycle_pct": cycle,
        "window_pct": window,
        "cadence_median": float(d["campaign_cadence_yr"].median()),
        "span_median": float(d["programme_span_yr"].median()),
        "calendar_mult_median": float(d["programme_calendar_multiplier"].median()),
        "calendar_mult_max": float(d["programme_calendar_multiplier"].max()),
        # W < trips is only meaningful with the search ON: at N = 1, W = 1 and
        # trips is 2-5, so a search-OFF cell reports ~100% trivially.
        "w_lt_trips_pct": pct(d["missions_per_ship"] < d["trips_per_ship"]),
        "w_gt_trips": int((d["missions_per_ship"] > d["trips_per_ship"]).sum()),
        "fleet_median": float(d["fleet_ships"].median()),
        "fleet_max": float(d["fleet_ships"].max()),
        "n_median": float(d["programme_missions"].median()),
        "n_max": float(d["programme_missions"].max()),
        "at_ceiling": int(at_ceiling.sum()),
        "at_ceiling_pct": pct(at_ceiling),
        "sat_min": float(d["saturation_multiplier"].min()),
        "sat_median": float(d["saturation_multiplier"].median()),
        "sat_max": float(d["saturation_multiplier"].max()),
        "clearing_min": float(d["market_clearing_fraction"].min()),
        "clearing_median": float(d["market_clearing_fraction"].median()),
        "bound_pct": pct(d["market_clearing_fraction"] < 1.0),
        "unsold_rows": int((d["unsold_payload_kg"] > UNSOLD_FLOOR_KG).sum()),
        "propellants": shares(d["propellant"]),
        "vehicles": shares(d["vehicle"]),
        "aerocapture_pct": pct(truthy(d["aerocapture_return"])),
        "isru_pct": pct(truthy(d["isru_return"])),
        "repl_rows": int(repl.sum()),
        # Which `replicated` technologies survive at all.  The standing finding
        # is that every survivor anywhere is FEEP, not one PPT and not one
        # electrospray row, because only the lightest of the three (2,500 kg/N
        # against 5,000 and 10,000) ever closes a mass budget.  A count alone
        # cannot say that, and the claim is about which technology rather than
        # how many rows.
        "repl_propellants": shares(d["propellant"][repl]),
        "repl_best": repl_best,
    }


def cell_paths(tag=None):
    """Every archived cell, destination order first and raw before beneficiated.

    Sorting by the filename would put `earth_surface` first and interleave the
    four settings of each destination alphabetically, which is neither the order
    the docs tables are read in nor the order the campaign ran them in.

    🚨  `tag` READS A RE-MEASUREMENT, AND IT IS A SUFFIX RATHER THAN A GLOB ON
    PURPOSE.  A cell re-run at a later release is archived as
    `<cell>__calc-<ver>.csv.gz` precisely so it cannot be mistaken for the
    campaign's own cell, and this function composing an EXACT filename is what
    makes that true.  Globbing `campaign/cells/` would be shorter and would
    undo it: every re-measurement would then be picked up as though it were a
    destination of the campaign.  So a tag still builds one name per cell, and
    a tag with nothing behind it yields nothing rather than falling back to the
    untagged cell, which would silently derive the wrong release.
    """
    out = []
    suffix = f"__{tag}" if tag else ""
    for dest in DESTS:
        for ore in ("raw", "benef"):
            for search in ("off", "on"):
                name = f"{dest}__{ore}__search-{search}{suffix}"
                p = os.path.join(CELLS, name + ".csv.gz")
                if os.path.exists(p):
                    out.append((name, p))
    return out


def run(force, tag=None):
    """Derive every cell that has no JSON yet, printing one line each."""
    os.makedirs(OUT, exist_ok=True)
    todo = cell_paths(tag)
    if tag and not todo:
        # Not a skip.  A tag naming no cell is a typo or a missing archive, and
        # deriving the campaign's cells instead would answer a question nobody
        # asked, in a file named after the one they did.
        print(f"no archived cell carries the tag {tag!r} under campaign/cells")
        return 1
    where = f"campaign/cells tagged {tag}" if tag else "campaign/cells"
    print(f"{len(todo)} cells under {where}")
    for name, path in todo:
        dest = os.path.join(OUT, name + ".json")
        if os.path.exists(dest) and not force:
            print(f"  skip  {name}")
            continue
        stats = derive(path)
        # newline="\n" because .gitattributes pins *.json to eol=lf.  Text mode
        # on Windows would write CRLF, git would normalise it on commit, and the
        # working tree would read as modified forever after: the Drive
        # stat-cache symptom this repo already has a hook for, arriving from a
        # second direction.  Nothing here is hashed, so this is tidiness rather
        # than the CRLF pin the five CSV writers carry for the opposite reason.
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(stats, fh, indent=1, sort_keys=True)
        print(f"  OK    {name:42s} {stats['evaluable']:>9,} rows  "
              f"best {stats['objective']:.4f}x")
    missing = [n for n, _ in todo if not os.path.exists(os.path.join(OUT, n + ".json"))]
    if missing:
        print(f"*** {len(missing)} cells did not derive: {', '.join(missing)}")
        return 1
    return 0


def load_all(tag=None):
    """Every derived cell, keyed by name, or an empty dict if none are derived.

    ⚠️  THE TAG IS STRIPPED FROM THE KEY, AND THAT IS WHAT KEEPS `report`
    UNTOUCHED.  It composes fourteen cell keys of the form
    `<dest>__<ore>__search-<s>`, and threading a suffix through every one of
    them is fourteen chances to thread it through thirteen.  Selecting the JSON
    here instead means the tables are rendered by the same code whichever
    release produced the cells, which is also what makes the two comparable.

    The filter runs BOTH ways: a tagged run loads only tagged cells and an
    untagged run loads only untagged ones, so a re-measurement sitting in the
    output directory can never contribute a row to the campaign's own tables.
    """
    got = {}
    suffix = f"__{tag}" if tag else None
    for p in sorted(glob.glob(os.path.join(OUT, "*.json"))):
        name = os.path.basename(p)[:-5]
        if suffix:
            if not name.endswith(suffix):
                continue
            name = name[:-len(suffix)]
        elif "__calc-" in name:
            continue
        with open(p, encoding="utf-8") as fh:
            got[name] = json.load(fh)
    return got


def _label(ore, search):
    """The column heading the docs use for one of the four settings."""
    return f"{'raw' if ore == 'raw' else 'benef'} {'ON' if search == 'on' else 'N=1'}"


def report(tag=None):
    """Render every table, in the shape the docs carry them in.

    Printed rather than written: a table that is going into a document should be
    read before it is pasted, and this repo's standing failure is prose that no
    longer agrees with the table beneath it.

    With a `tag` the tables cover that re-measurement alone, which normally
    means one destination of the seven; the rest of every table reads "-", and
    that is the honest rendering rather than a gap to be filled from the
    campaign.
    """
    got = load_all(tag)
    if not got:
        if tag:
            print(f"nothing derived for tag {tag!r}; "
                  f"run --tag {tag} without --report first")
            return 1
        print("nothing derived yet; run without --report first")
        return 1
    if tag:
        print(f"== cells tagged {tag}; every other destination reads '-' ==")
    settings = [("raw", "off"), ("raw", "on"), ("benef", "off"), ("benef", "on")]

    print("\n== THE RIG'S TWO BOUNDS: cycle / calendar, % of evaluable rows ==")
    print(f"{'destination':16s} " + " ".join(f"{_label(o, s):>16s}" for o, s in settings))
    for dest in DESTS:
        cells = [got.get(f"{dest}__{o}__search-{s}") for o, s in settings]
        row = " ".join("%16s" % ("%.2f / %.2f" % (c["cycle_pct"], 100 - c["cycle_pct"])
                                 if c else "-") for c in cells)
        print(f"{dest:16s} {row}")

    print("\n== WHAT SETS THE PACE: window / dig, and the median cadence ==")
    print(f"{'destination':16s} {'raw N=1':>16s} {'benef N=1':>16s} "
          f"{'cadence raw':>12s} {'cadence benef':>14s} {'span raw ON':>12s} "
          f"{'span benef ON':>14s}")
    for dest in DESTS:
        r = got.get(f"{dest}__raw__search-off")
        b = got.get(f"{dest}__benef__search-off")
        rs = got.get(f"{dest}__raw__search-on")
        bs = got.get(f"{dest}__benef__search-on")
        if not r:
            continue
        print(f"{dest:16s} "
              f"{'%.2f / %.2f' % (r['window_pct'], 100 - r['window_pct']):>16s} "
              f"{('%.2f / %.2f' % (b['window_pct'], 100 - b['window_pct'])) if b else '-':>16s} "
              f"{r['cadence_median']:>12.3f} {b['cadence_median'] if b else float('nan'):>14.3f} "
              f"{rs['span_median'] if rs else float('nan'):>12.2f} "
              f"{bs['span_median'] if bs else float('nan'):>14.2f}")

    print("\n== W < trips, % of rows (meaningful with the search ON only) ==")
    print(f"{'destination':16s} {'raw ON':>10s} {'benef ON':>10s} "
          f"{'fleet med':>10s} {'N med':>8s} {'W>trips':>9s}")
    for dest in DESTS:
        r = got.get(f"{dest}__raw__search-on")
        b = got.get(f"{dest}__benef__search-on")
        if not r:
            continue
        print(f"{dest:16s} {r['w_lt_trips_pct']:>9.2f}% "
              f"{(b['w_lt_trips_pct'] if b else float('nan')):>9.2f}% "
              f"{r['fleet_median']:>10.0f} {r['n_median']:>8.0f} "
              f"{r['w_gt_trips']:>9d}")

    print("\n== PROPELLANT SHARES, % of evaluable rows ==")
    for dest in DESTS:
        if not got.get(f"{dest}__raw__search-off"):
            continue
        print(f"\n  {dest}")
        names = []
        for o, s in settings:
            c = got.get(f"{dest}__{o}__search-{s}")
            names += [n for n, _ in (c["propellants"] if c else [])]
        for name in dict.fromkeys(names):
            vals, keep = [], False
            for o, s in settings:
                c = got.get(f"{dest}__{o}__search-{s}")
                hit = dict(c["propellants"]).get(name) if c else None
                keep = keep or (hit is not None and hit >= DISPLAY_FLOOR)
                vals.append("%.2f" % hit if hit is not None else "-")
            if keep:
                print(f"    {name:34s} " + " ".join(f"{v:>8s}" for v in vals))

    print("\n== LAUNCH VEHICLE SHARES, % of evaluable rows ==")
    for dest in DESTS:
        if not got.get(f"{dest}__raw__search-off"):
            continue
        print(f"\n  {dest}")
        names = []
        for o, s in settings:
            c = got.get(f"{dest}__{o}__search-{s}")
            names += [n for n, _ in (c["vehicles"] if c else [])]
        for name in dict.fromkeys(names):
            vals, keep = [], False
            for o, s in settings:
                c = got.get(f"{dest}__{o}__search-{s}")
                hit = dict(c["vehicles"]).get(name) if c else None
                keep = keep or (hit is not None and hit >= DISPLAY_FLOOR)
                vals.append("%.2f" % hit if hit is not None else "-")
            if keep:
                print(f"    {name:34s} " + " ".join(f"{v:>8s}" for v in vals))

    print("\n== THE CEILING DIAGNOSTIC, searched cells ==")
    print(f"{'cell':34s} {'at fleet cap':>16s} {'clearing min':>13s} "
          f"{'clearing med':>13s} {'bound%':>8s} {'unsold rows':>12s}")
    for dest in DESTS:
        for o in ("raw", "benef"):
            c = got.get(f"{dest}__{o}__search-on")
            if not c:
                continue
            print(f"{dest + ' ' + o:34s} "
                  f"{'%s (%.2f%%)' % (format(c['at_ceiling'], ','), c['at_ceiling_pct']):>16s} "
                  f"{c['clearing_min']:>13.6f} {c['clearing_median']:>13.6f} "
                  f"{c['bound_pct']:>7.3f}% {c['unsold_rows']:>12,}")

    print("\n== REPLICATED-SCALING THRUSTERS: does one ever WIN ==")
    print(f"{'cell':34s} {'rows':>10s} {'rank':>9s} {'margin':>9s} {'body':>12s}")
    for dest in DESTS:
        for o, s in settings:
            c = got.get(f"{dest}__{o}__search-{s}")
            if not c:
                continue
            rb = c["repl_best"]
            cell = f"{dest} {_label(o, s)}"
            if rb:
                print(f"{cell:34s} {c['repl_rows']:>10,} {rb['rank']:>9,} "
                      f"{rb['margin']:>8.2f}x {rb['designation']:>12s}")
            else:
                print(f"{cell:34s} {0:>10,} {'none':>9s} {'-':>9s} {'-':>12s}")

    print("\n== AEROCAPTURE AND ISRU, % of evaluable rows ==")
    print(f"{'destination':16s} " + " ".join(f"{_label(o, s):>16s}" for o, s in settings))
    for dest in DESTS:
        cells = [got.get(f"{dest}__{o}__search-{s}") for o, s in settings]
        row = " ".join("%16s" % ("%.2f / %.2f" % (c["aerocapture_pct"], c["isru_pct"])
                                 if c else "-") for c in cells)
        print(f"{dest:16s} {row}")

    print("\n== WINNERS ==")
    print(f"{'cell':34s} {'body':>12s} {'type':>6s} {'propellant':>26s} "
          f"{'vehicle':>16s} {'objective':>11s} {'payload kg':>12s} {'N':>6s}")
    for dest in DESTS:
        for o, s in settings:
            c = got.get(f"{dest}__{o}__search-{s}")
            if not c:
                continue
            w = c["winner"]
            print(f"{dest + ' ' + _label(o, s):34s} {str(w['designation']):>12s} "
                  f"{str(w['spectral_type']):>6s} {str(w['propellant'])[:26]:>26s} "
                  f"{str(w['vehicle'])[:16]:>16s} {c['objective']:>10.4f}x "
                  f"{(w['max_payload_kg'] or 0):>12,.0f} "
                  f"{(w['programme_missions'] or 0):>6,.0f}")
    return 0


def main():
    """Derive, or report, depending on the flags."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", action="store_true",
                    help="render the tables from the JSON already derived")
    ap.add_argument("--force", action="store_true",
                    help="re-derive cells that already have a JSON")
    ap.add_argument("--tag", default=None,
                    help="read cells archived under a suffix, e.g. calc-1.22.0")
    a = ap.parse_args()
    return report(a.tag) if a.report else run(a.force, a.tag)


if __name__ == "__main__":
    raise SystemExit(main())
