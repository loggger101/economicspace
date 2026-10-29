# -*- coding: utf-8 -*-
"""Re-price a body under each composition class it could be, and report the spread.

MODEL.md, "For most NEOs the taxonomy is a guess, and the guess is a coin
flip": nine in ten NEOs have no measured class, so the catalog builder assumes
an albedo from the orbit and reads the composition off it, and Stage 4 prices
that guess as a fact. Scored against the NEOs that do have a measured class,
the guess is right about half the time (starred-repos F11).

This tool takes rows of the profitability catalog (the top N by default),
and for each NEO whose class was guessed from an assumed albedo it evaluates
the same body four ways, once per class it could be (C-complex, S-complex,
X-complex, and the commonest other class among NEOs with a measured one), with
`calc.evaluate_asteroid` and the live config. Each variant takes its
composition columns from a donor row of that class, and its size from the
body's H at that class's median albedo, because the builder sized the body
from the albedo it guessed: a C-type is about twice the diameter of an S-type
at the same H, and eight times the mass. It then weights the four results by
F11's empirical prior and reports the objective
(`total_cost_usd / gross_value_usd`) per class, its prior-weighted range, and
the chance the body is better or worse than the guess says.

It WRITES NOTHING: it never calls `build_profitability_catalog`, and prints
to stdout unless `--out` names a CSV. It reads the catalogs Stage 4 reads, so
the destination must match the installed Stage 2 table (`--destination`,
refused otherwise, as `run_pipeline.preflight` refuses).

F11's prior is biased toward bright S-types, because bodies with a measured
class are the ones spectroscopy reached first; the spread is a lower bound on
how far a guessed C could be from the truth, and the S weights are generous.

    py campaign/composition_range.py --destination cislunar
    py campaign/composition_range.py --destination cislunar --top 50 --out range.csv

Run from the repository root: Stage 4 reads `asteroid_pipeline/` relative to
the working directory.
"""

import argparse
import dataclasses
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from modules import calc  # noqa: E402

CLASSES = ["C-complex", "S-complex", "X-complex"]

# starred-repos F11 (FOURTH-PASS.md, measured 2026-10-29 on data-2026-10-21b):
# among the 2,943 NEOs with a source class, the share of each true class for
# each class the albedo_assumed rule would give, by H. Cells with fewer than 30
# bodies take the pooled row for their rule. Columns: C, S, X, Other.
F11_PRIOR = {
    "C": [((0, 18), [0.308, 0.455, 0.090, 0.147]),
          ((18, 20), [0.300, 0.436, 0.100, 0.164]),
          ((20, 22), [0.286, 0.375, 0.196, 0.143]),
          ((22, 99), [0.294, 0.453, 0.104, 0.148])],      # pooled (n = 29 and 3)
    "S": [((0, 18), [0.157, 0.545, 0.059, 0.239]),
          ((18, 20), [0.193, 0.529, 0.103, 0.175]),
          ((20, 22), [0.193, 0.517, 0.092, 0.198]),
          ((22, 25), [0.159, 0.492, 0.147, 0.201]),
          ((25, 99), [0.137, 0.544, 0.187, 0.132])],
}

# AsteroidCatalog asteroid_catalog/derive.py ALBEDO_BY_SPECTRAL_TYPE (catalog
# 92f7739): the median measured albedo of each class the builder sizes with.
ALBEDO_BY_TYPE = {"C": 0.0620, "S": 0.2340, "X": 0.0800, "Q": 0.2520, "V": 0.3355,
                  "L": 0.2030, "K": 0.1840, "A": 0.2620, "D": 0.0820, "B": 0.0670}

# What a donor row lends a variant: everything the builder derived from the class.
COMPOSITION_COLS = ["spectral_type", "comp_class", "comp_group", "comp_composition",
                    "comp_minerals", "comp_notes", "comp_density_est_gcm3",
                    "comp_metal_fraction", "comp_silicate_fraction", "comp_carbon_fraction",
                    "comp_ice_fraction", "comp_phases", "comp_phases_detailed",
                    "comp_pgm_enrichment"]


def diameter_km(h, albedo):
    """The H-albedo-diameter relation, as AsteroidCatalog derive.py evaluates it.

    The same operations in the same order, so a body sized at the builder's
    own albedo comes back to the last bit.
    """
    return 1329.0 / np.sqrt(albedo) * np.power(10.0, -h / 5.0)


def mass_kg(diameter, density_gcm3):
    """physics.sphere_volume_m3 then enrich.py's density * 1000 * volume, in that order."""
    vol_m3 = np.pi / 6.0 * (np.float64(diameter) * 1_000.0) ** 3
    return density_gcm3 * 1_000.0 * vol_m3


def prior_for(rule_letter, h):
    for (lo, hi), p in F11_PRIOR[rule_letter]:
        if lo <= h < hi:
            return np.array(p)
    return None


def representative_type(group):
    """'C-complex' -> 'C', 'Q-type' -> 'Q'."""
    return str(group).split("-")[0]


def pick_donors(asteroids, other_group):
    """One source-typed row per class to lend its composition columns."""
    src = asteroids[asteroids["spectral_type_source"].astype(str).eq("source")]
    donors = {}
    for group in CLASSES + [other_group]:
        t = representative_type(group)
        exact = src[src["spectral_type"].astype(str).eq(t) & src["comp_class"].astype(str).eq(t)]
        if exact.empty:
            exact = src[src["comp_group"].astype(str).eq(group)]
        donors[group] = exact.iloc[0]
    return donors


def commonest_other(asteroids):
    """The commonest class outside C, S and X among NEOs with a measured class."""
    neo = asteroids["is_neo"].astype(str).str.lower().isin(["true", "1"])
    src = asteroids[neo & asteroids["spectral_type_source"].astype(str).eq("source")]
    other = src[~src["comp_group"].astype(str).isin(CLASSES)]["comp_group"]
    return other.value_counts().index[0]


def variant(row, donor, group, keep_size=False):
    """The body as if it were `group`: the donor's composition, re-sized at that class's albedo.

    `keep_size` keeps the row's own diameter, density and mass, which the
    self-check uses to test the composition copy on its own.
    """
    v = dict(row)
    for c in COMPOSITION_COLS:
        if c in donor.index:
            v[c] = donor[c]
    if keep_size:
        return v
    t = representative_type(group)
    rho = float(donor["comp_density_est_gcm3"])
    # The builder labels a diameter it sized from H `derived_h_orbit_albedo`
    # (and sets `derived_diameter_is_estimate`); only those depend on the
    # guessed class. A measured diameter is kept.
    derived = str(row.get("diameter_source", "")).strip().lower().startswith("derived") \
        or str(row.get("derived_diameter_is_estimate", "")).strip().lower() in ("true", "1")
    if derived:
        d = diameter_km(float(row["absolute_magnitude_h"]), ALBEDO_BY_TYPE.get(t, 0.15))
        v["diameter_km"] = d
    else:
        d = float(row["diameter_km"])
    v["density_gcm3"] = rho
    v["estimated_mass_kg"] = mass_kg(d, rho)
    return v


def objective(result):
    if result is None:
        return np.nan
    gross = float(result.get("gross_value_usd") or 0.0)
    return float(result["total_cost_usd"]) / gross if gross > 0 else np.inf


def main():
    ap = argparse.ArgumentParser(description="composition as a range, for the top of the ranking")
    ap.add_argument("--destination", required=True,
                    help="must match the destination the installed Stage 2 table priced for")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--out", default=None, help="write the per-class table here (CSV)")
    args = ap.parse_args()

    config = dataclasses.replace(calc.CONFIG, delivery_destination=args.destination)
    catalogs = calc.load_all_catalogs(config)
    stamped = str(catalogs["minerals"]["delivery_destination"].iloc[0]).strip().lower()
    if stamped != args.destination.strip().lower():
        raise SystemExit(f"Stage 2 on disk priced for {stamped!r}, not {args.destination!r}; "
                         "every number would be meaningless. Pass --destination "
                         f"{stamped} or install that destination's prices.")
    combos = calc.candidate_combos(catalogs, config)
    asteroids = catalogs["asteroids"]
    asteroids["designation"] = asteroids["designation"].astype(str).str.strip()

    prof_path = os.path.join(config.output_dir, config.output_filename)
    top = pd.read_csv(prof_path, usecols=["designation"], nrows=args.top, dtype={"designation": str})
    top["rank"] = np.arange(1, len(top) + 1)
    other = commonest_other(asteroids)
    donors = pick_donors(asteroids, other)
    groups = CLASSES + [other]
    print(f"\n  classes priced: {', '.join(groups)}  (donors: "
          + ", ".join(f"{g} {d['designation']}" for g, d in donors.items()) + ")")

    by_des = asteroids.set_index("designation")
    rows, checks = [], []
    for t in top.itertuples():
        if t.designation not in by_des.index:
            continue
        row = by_des.loc[t.designation]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        row = row.to_dict()
        row["designation"] = t.designation
        neo = str(row.get("is_neo")).lower() in ("true", "1")
        guessed = str(row.get("spectral_type_source")) == "albedo_assumed"
        if not (neo and guessed):
            rows.append({"rank": t.rank, "designation": t.designation, "priced": "not a guessed NEO"})
            continue
        rule = "C" if str(row.get("comp_group")) == "C-complex" else "S"
        p = prior_for(rule, float(row["absolute_magnitude_h"]))
        assigned = objective(calc.evaluate_asteroid(row, catalogs, config, combos))
        # Self-check, two parts. (1) The assigned class's donor composition on
        # the row's own size must give the catalog row to the last bit, or the
        # donor columns are not what the builder used. (2) The sizing formula
        # at the builder's own albedo must give the catalog's diameter to 1e-12
        # (not to the bit: the builder's floats went through numpy's array
        # paths and a CSV round trip, which a scalar recomputation cannot
        # follow exactly).
        rebuilt = objective(calc.evaluate_asteroid(
            variant(row, donors[row.get("comp_group")], row.get("comp_group"), keep_size=True),
            catalogs, config, combos))
        d_gap = abs(diameter_km(float(row["absolute_magnitude_h"]),
                                float(row["albedo_assumed_for_diameter"]))
                    / float(row["diameter_km"]) - 1.0)
        checks.append((t.designation, assigned, rebuilt, d_gap))
        if not (rebuilt == assigned or (np.isnan(rebuilt) and np.isnan(assigned))) or d_gap > 1e-12:
            raise SystemExit(f"SELF-CHECK FAILED on {t.designation}: the assigned composition"
                             f" gives {rebuilt!r} against the catalog row's {assigned!r};"
                             f" the sizing formula is {d_gap:.1e} from the catalog's diameter")
        ratios = [objective(calc.evaluate_asteroid(variant(row, donors[g], g), catalogs, config, combos))
                  for g in groups]
        r = np.array(ratios, float)
        ok = np.isfinite(r)
        w = p * ok
        rec = {"rank": t.rank, "designation": t.designation, "priced": "yes",
               "H": row["absolute_magnitude_h"], "assigned": row.get("comp_group"),
               "objective_assigned": assigned}
        for g, x, pg in zip(groups, ratios, p):
            rec[f"objective_{representative_type(g)}"] = x
            rec[f"p_{representative_type(g)}"] = pg
        rec["objective_prior_mean"] = float(np.sum(w * np.where(ok, r, 0)) / w.sum()) if w.sum() else np.nan
        rec["objective_best"] = float(np.nanmin(r)) if ok.any() else np.nan
        rec["objective_worst"] = float(np.nanmax(np.where(ok, r, np.nan))) if ok.any() else np.nan
        rec["p_better_than_assigned"] = float(np.sum(p * (ok & (r < assigned - 1e-12))))
        rec["p_unflyable"] = float(np.sum(p * ~ok))
        rows.append(rec)

    out = pd.DataFrame(rows)
    priced = out[out.priced == "yes"]
    worst_d = max((c[3] for c in checks), default=0.0)
    print(f"\n  SELF-CHECK  the assigned class's donor composition reproduces {len(checks)} of"
          f" {len(checks)} catalog rows bit for bit; the sizing formula matches the catalog's"
          f" diameters to {worst_d:.1e} (OK)")
    print(f"\n  top {args.top} rows: {len(out)} found in the catalog, {len(priced)} guessed NEOs priced"
          f" four ways (objective = total cost / gross value, lower is better)\n")
    cols = ["rank", "designation", "assigned", "H", "objective_assigned"] + \
           [f"objective_{representative_type(g)}" for g in groups] + \
           ["objective_prior_mean", "p_better_than_assigned", "p_unflyable"]
    print(priced[cols].to_string(index=False, float_format=lambda v: f"{v:.4g}"))
    if len(priced):
        spread = priced.objective_worst / priced.objective_best
        print(f"\n  worst / best class objective: median {spread.median():.3g}x;"
              f" prior-weighted objective / assigned: median"
              f" {(priced.objective_prior_mean / priced.objective_assigned).median():.3g}")
    if args.out:
        out.to_csv(args.out, index=False)
        print(f"\n  wrote {args.out}")


if __name__ == "__main__":
    main()
