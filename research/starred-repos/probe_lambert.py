# -*- coding: utf-8 -*-
"""How far is the closed-form delta-v estimator from a real optimised transfer?

`asteroid_transfer_dv_km_s`'s docstring validates against five hand-picked
bodies and reads 8 to 12% below published mission delta-v on the three real
ones.  Nothing in the project measures the estimator against a true
two-impulse optimum on the actual population, because the project has no
Lambert solver.  `orbital.py` supplies one, and this is that measurement.

WHAT IS COMPARED

  shipped   `_transfer_legs_for_apsis` in closed form: the transfer ellipse
            runs 1 AU -> apsis, the WHOLE inclination change is bundled into
            the departure v_infinity, and the rendezvous burn is a coplanar
            scalar speed difference.  Uses a, e, i.

  oracle    a porkchop: Lambert solves over a grid of departure epoch and
            time of flight, minimising
                leo_departure(|v1 - v_earth|) + |v2 - v_asteroid|
            with the real 3-D geometry.  Uses a, e, i, RAAN, argp.

WHY THE EPOCH DOES NOT MATTER HERE

  The shipped estimator is DATE-FREE: it has no epoch, no launch date, and no
  phasing.  So the honest comparison is against the date-free optimum, and
  that is what scanning departure over a full synodic period gives, since
  every relative phase occurs inside one.  The catalog's `mean_anomaly_deg`
  would fix an absolute date, and it cannot be used for that anyway; see the
  epoch note in FINDINGS.md.

  ⚠️  So the oracle is an UPPER BOUND on how good a real mission could be.  A
  mission with a fixed launch date does worse.  That direction matters: the
  estimator is already optimistic, and the oracle is optimistic too.

Earth is modelled as a Keplerian orbit on the JPL J2000 mean elements, which
is right to about 1e-4 AU.  That is far below the differences being measured.

This script READS ONLY.  It does not import master, builds no stage, and
writes nothing to `asteroid_pipeline/`.

Usage:
    py research/starred-repos/probe_lambert.py
    py research/starred-repos/probe_lambert.py --n 400 --seed 7
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import orbital as ob  # noqa: E402

# Mirrored from modules/calc.py.
V_EARTH_KM_S    = 29.784
MU_EARTH_KM3_S2 = 398_600.4418
R_LEO_KM        = 6_378.14 + 200.0
_V_LEO = np.sqrt(MU_EARTH_KM3_S2 / R_LEO_KM)
_V_ESC = np.sqrt(2.0) * _V_LEO

# JPL J2000 mean elements for the Earth-Moon barycentre.
EARTH = dict(
    a=1.00000261 * ob.AU_KM,
    e=0.01671123,
    i=np.radians(-0.00001531),
    raan=0.0,
    argp=np.radians(102.93768193),
    M0=np.radians(-2.47311027),
)

DEFAULT_CATALOG = "asteroid_pipeline/asteroid_catalog.csv"


def leo_departure_dv_km_s(v_inf):
    """Delta-v from circular LEO onto a hyperbola with this v_infinity."""
    return np.sqrt(_V_ESC ** 2 + v_inf ** 2) - _V_LEO


def shipped_dv_out(a_au, e, i_deg):
    """The closed-form outbound delta-v, exactly as Module 4 computes it.

    Prices both apsides and returns the cheaper, matching
    `asteroid_transfer_options_km_s` resolved on `dv_out`.
    """
    best = np.inf
    for r_target in (a_au * (1.0 + e), a_au * (1.0 - e)):
        if r_target <= 0:
            continue
        a_t = (1.0 + r_target) / 2.0
        v_te_sq = 2.0 - 1.0 / a_t
        v_tt_sq = 2.0 / r_target - 1.0 / a_t
        v_at_sq = 2.0 / r_target - 1.0 / a_au
        if v_te_sq <= 0 or v_tt_sq <= 0 or v_at_sq <= 0:
            continue
        v_te = np.sqrt(v_te_sq)
        v_inf = np.sqrt(max(v_te ** 2 + 1.0 - 2.0 * v_te * np.cos(np.radians(i_deg)), 0.0))
        dv = (leo_departure_dv_km_s(v_inf * V_EARTH_KM_S)
              + abs(np.sqrt(v_at_sq) - np.sqrt(v_tt_sq)) * V_EARTH_KM_S)
        best = min(best, dv)
    return best


def oracle_dv_out(row, n_dep=40, n_tof=34, tof_lo_yr=0.25, tof_hi_yr=4.0):
    """Minimum two-impulse outbound delta-v over a departure x TOF porkchop."""
    a = float(row.semi_major_axis_au) * ob.AU_KM
    e = float(row.eccentricity)
    i = np.radians(float(row.inclination_deg))
    raan = np.radians(float(row.longitude_asc_node_deg))
    argp = np.radians(float(row.arg_perihelion_deg))
    M0 = np.radians(float(row.mean_anomaly_deg))

    # Scan departure over one synodic period so every relative phase occurs.
    p_ast = float(row.semi_major_axis_au) ** 1.5
    denom = abs(1.0 / p_ast - 1.0)
    syn_yr = min(1.0 / denom, 12.0) if denom > 1e-9 else 12.0

    t_dep = np.linspace(0.0, syn_yr * 365.25 * ob.DAY_S, n_dep, endpoint=False)
    tofs = np.linspace(tof_lo_yr, tof_hi_yr, n_tof) * 365.25 * ob.DAY_S

    best = np.inf
    best_at = None
    for td in t_dep:
        rE, vE = ob.propagate_elements(EARTH["a"], EARTH["e"], EARTH["i"],
                                       EARTH["raan"], EARTH["argp"], EARTH["M0"], td)
        rE = rE.ravel(); vE = vE.ravel()
        for tf in tofs:
            rA, vA = ob.propagate_elements(a, e, i, raan, argp, M0, td + tf)
            rA = rA.ravel(); vA = vA.ravel()
            try:
                v1, v2 = ob.lambert_izzo(rE, rA, tf)
            except (ValueError, FloatingPointError):
                continue
            if v1 is None or not np.all(np.isfinite(v1)) or not np.all(np.isfinite(v2)):
                continue
            v_inf = np.linalg.norm(v1 - vE)
            dv = leo_departure_dv_km_s(v_inf) + np.linalg.norm(v2 - vA)
            if dv < best:
                best = dv
                best_at = (td / (365.25 * ob.DAY_S), tf / (365.25 * ob.DAY_S))
    return best, best_at


def main():
    """Sample the catalog, run both models, and report the gap."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--catalog", default=DEFAULT_CATALOG)
    ap.add_argument("--n", type=int, default=250, help="bodies to sample")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cols = ["designation", "semi_major_axis_au", "eccentricity", "inclination_deg",
            "longitude_asc_node_deg", "arg_perihelion_deg", "mean_anomaly_deg", "is_neo"]
    df = pd.read_csv(args.catalog, usecols=cols, low_memory=False)
    df = df[(df["semi_major_axis_au"] > 0.3) & (df["semi_major_axis_au"] < 6.0)
            & (df["eccentricity"] >= 0) & (df["eccentricity"] < 0.9)].dropna(subset=cols[1:7])
    sample = df.sample(n=min(args.n, len(df)), random_state=args.seed)

    print(f"sampled {len(sample):,} bodies from {len(df):,} usable rows "
          f"(seed {args.seed})")
    print("running the porkchop oracle; this is the slow part ...\n")

    rows = []
    for k, r in enumerate(sample.itertuples(), 1):
        ship = shipped_dv_out(float(r.semi_major_axis_au), float(r.eccentricity),
                              float(r.inclination_deg))
        orac, at = oracle_dv_out(r)
        if not np.isfinite(orac) or not np.isfinite(ship):
            continue
        rows.append((r.designation, float(r.semi_major_axis_au), float(r.eccentricity),
                     float(r.inclination_deg), ship, orac, at[1] if at else np.nan))
        if k % 50 == 0:
            print(f"  {k}/{len(sample)} ...")

    out = pd.DataFrame(rows, columns=["designation", "a_au", "e", "i_deg",
                                      "shipped", "oracle", "best_tof_yr"])
    out["gap"] = out["oracle"] - out["shipped"]
    out["rel"] = out["gap"] / out["oracle"]

    print(f"\nRESULT  (n = {len(out):,} bodies solved)")
    print(f"  shipped closed form : median {out['shipped'].median():7.3f} km/s")
    print(f"  Lambert oracle      : median {out['oracle'].median():7.3f} km/s")
    print(f"  gap (oracle-shipped): median {out['gap'].median():+7.3f} km/s   "
          f"mean {out['gap'].mean():+7.3f}")
    print(f"  relative to oracle  : median {out['rel'].median() * 100:+6.2f}%  "
          f"mean {out['rel'].mean() * 100:+6.2f}%")
    opt = (out["shipped"] < out["oracle"] - 1e-6).mean() * 100
    print(f"\n  shipped estimator OPTIMISTIC (below the achievable optimum) "
          f"on {opt:.1f}% of bodies")
    print(f"  shipped estimator conservative on {100 - opt:.1f}%")
    for lo, hi, name in [(0, 5, "i < 5 deg"), (5, 15, "5-15 deg"), (15, 90, "i > 15 deg")]:
        m = (out["i_deg"] >= lo) & (out["i_deg"] < hi)
        if m.sum():
            print(f"    {name:12s} n={m.sum():4d}  median gap {out.loc[m,'gap'].median():+7.3f} km/s"
                  f"  ({out.loc[m,'rel'].median() * 100:+6.2f}%)")
    print(f"\n  best time of flight: median {out['best_tof_yr'].median():.2f} yr, "
          f"range {out['best_tof_yr'].min():.2f} to {out['best_tof_yr'].max():.2f}")

    print("\n  worst 8 underestimates (oracle much higher than shipped):")
    print(out.nlargest(8, "gap")[["designation", "a_au", "e", "i_deg",
                                  "shipped", "oracle", "gap"]]
          .to_string(index=False, float_format=lambda x: f"{x:8.3f}"))


if __name__ == "__main__":
    main()
