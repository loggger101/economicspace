# -*- coding: utf-8 -*-
"""NHATS and Shoemaker-Helin as INDEPENDENT delta-v oracles for the NEO population.

FINDINGS.md F4 measures the shipped estimator against a Lambert oracle built in
this repo and validated on three published missions. That is one instrument,
and it is ours. This probe adds two that were built by other people:

    NHATS   ssd-api.jpl.nasa.gov/nhats.api, JPL's own numerically optimised
            ROUND-TRIP delta-v for every NEA it finds a viable trajectory for.
            7,033 bodies, free, no kernels, one HTTP call.
    S-H     the Shoemaker-Helin closed form, as published by Asterank over
            ~600k bodies. The standard analytic NEO delta-v approximation,
            i.e. the same KIND of model as the shipped one.

The pair is the point. Agreement with S-H says the shipped estimator is a
well-behaved member of its own family; disagreement with NHATS says what that
family costs against a really optimised trajectory. Neither is reachable from
inside this repo's own code, which is what makes them worth the HTTP call.

Two traps this probe is written around, both hit while building it:

  1. THE APSIS IS A SEARCH. `asteroid_transfer_dv_km_s` prices BOTH apsides and
     the architecture search takes the winner, so a probe that prices only
     aphelion is not measuring the shipped model. Aphelion alone reported 43
     bodies whose ONE-WAY leg exceeded JPL's ROUND TRIP, and a rank agreement
     of 0.4006. Pricing both gives 14 and 0.5976. The first reading was a
     broken checker, which is what this repo says a broken checker always
     looks like.
  2. ASTERANK'S KEY IS A FLOAT. `pdes` arrives as float64, so 433 stringifies
     as "433.0", joins nothing, and says nothing about it: 1,000 rows in and 0
     out. It goes through Int64 here, per CLAUDE.md's merge-key rule. That is
     the NEOWISE defect wearing a different hat.

This script READS ONLY. It fetches two public read-only APIs, does not import
master, does not build a stage, and does not write to `asteroid_pipeline/`, so
it cannot invalidate a `.verify` baseline.

Usage:
    py research/starred-repos/probe_nhats.py
    py research/starred-repos/probe_nhats.py --asterank
    py research/starred-repos/probe_nhats.py --catalog path/to/asteroid_catalog.csv
"""

import argparse
import json
import urllib.request

import numpy as np
import pandas as pd

# Mirrored from modules/calc.py, for the reason probe_plane_change.py gives:
# importing calc.py fires its INSTALLATION block, which pip-installs into the
# live environment, and a probe must not disturb a measurement host.
V_EARTH_KM_S    = 29.784
MU_EARTH_KM3_S2 = 398_600.4418
R_LEO_KM        = 6_378.14 + 200.0

_V_LEO = np.sqrt(MU_EARTH_KM3_S2 / R_LEO_KM)
_V_ESC = np.sqrt(2.0) * _V_LEO

DEFAULT_CATALOG = "asteroid_pipeline/asteroid_catalog.csv"
NHATS_URL    = "https://ssd-api.jpl.nasa.gov/nhats.api"
ASTERANK_URL = ("http://www.asterank.com/api/asterank"
                "?query=%7B%22neo%22%3A%22Y%22%7D&limit=1000")

# The five bodies asteroid_transfer_dv_km_s's docstring is validated against.
# All five resolve to aphelion, which is why an aphelion-only probe reproduces
# them and is still not the shipped model. Reproducing these is necessary and
# NOT sufficient; see trap 1 in the module docstring.
REFERENCE = pd.DataFrame({
    "body":              ["main belt ref", "moderate NEA", "Bennu", "Eros", "Itokawa"],
    "semi_major_axis_au": [2.700, 1.200, 1.126, 1.458, 1.324],
    "eccentricity":       [0.100, 0.300, 0.204, 0.223, 0.280],
    "inclination_deg":    [10.00, 8.000, 6.000, 10.80, 1.600],
    "docstring_dv_out":   [10.43, 5.580, 4.640, 6.100, 4.140],
})


def leo_departure_dv_km_s(v_inf_km_s):
    """Delta-v from circular LEO onto a hyperbola with this v_infinity."""
    return np.sqrt(_V_ESC ** 2 + v_inf_km_s ** 2) - _V_LEO


def dv_out_at_apsis(a, i_deg, r_target):
    """Outbound delta-v meeting the target at `r_target`.

    Whole plane change at departure, coplanar speed difference at the
    rendezvous: a vectorised copy of `_transfer_legs_for_apsis`.
    """
    i   = np.radians(i_deg)
    a_t = (1.0 + r_target) / 2.0

    v_t_earth  = np.sqrt(np.clip(2.0 / 1.0      - 1.0 / a_t, 1e-12, None))
    v_t_target = np.sqrt(np.clip(2.0 / r_target - 1.0 / a_t, 1e-12, None))
    v_ast      = np.sqrt(np.clip(2.0 / r_target - 1.0 / a,   1e-12, None))

    v_inf = np.sqrt(np.clip(
        v_t_earth ** 2 + 1.0 - 2.0 * v_t_earth * np.cos(i), 0.0, None,
    )) * V_EARTH_KM_S
    dv_match = np.sqrt(np.clip(
        v_t_target ** 2 + v_ast ** 2 - 2.0 * v_t_target * v_ast, 0.0, None,
    )) * V_EARTH_KM_S

    return leo_departure_dv_km_s(v_inf) + dv_match


def dv_out_shipped(a, e, i_deg):
    """Both apsides priced, cheaper taken. Returns (dv, which_apsis).

    This, and not the aphelion branch alone, is the shipped model: v1.10.0
    stopped guessing the rendezvous apsis and started pricing both.
    """
    Q = a * (1.0 + e)
    q = a * (1.0 - e)
    aph = dv_out_at_apsis(a, i_deg, Q)
    per = dv_out_at_apsis(a, i_deg, q)
    take_per = per < aph
    return np.where(take_per, per, aph), np.where(take_per, "perihelion", "aphelion")


def check_reference():
    """Reproduce the docstring's five validated figures."""
    r = REFERENCE.copy()
    a = r["semi_major_axis_au"].to_numpy(float)
    e = r["eccentricity"].to_numpy(float)
    i = r["inclination_deg"].to_numpy(float)
    r["model"], r["apsis"] = dv_out_shipped(a, e, i)
    r["delta"] = r["model"] - r["docstring_dv_out"]

    print("REFERENCE BODIES  (must reproduce asteroid_transfer_dv_km_s's docstring)")
    print(r.to_string(index=False, float_format=lambda x: f"{x:9.4f}"))
    worst = r["delta"].abs().max()
    ok = worst < 0.01
    print(f"\n  worst |model - docstring| = {worst:.4f} km/s "
          f"({'OK' if ok else 'MISMATCH -- this probe is not the shipped model'})")
    return ok


def load_catalog(path):
    """Elements and designation, filtered to usable orbits."""
    cols = ["designation", "semi_major_axis_au", "eccentricity", "inclination_deg"]
    df = pd.read_csv(path, usecols=cols, low_memory=False)
    df["designation"] = df["designation"].astype(str).str.strip()
    return df[(df["semi_major_axis_au"] > 0)
              & (df["eccentricity"] >= 0) & (df["eccentricity"] < 1)]


def fetch_nhats():
    """JPL's optimised round-trip delta-v per NEA."""
    with urllib.request.urlopen(NHATS_URL, timeout=180) as fh:
        rows = json.load(fh)["data"]
    n = pd.DataFrame(rows)
    n["nhats_dv"] = n["min_dv"].apply(
        lambda x: float(x["dv"]) if isinstance(x, dict) else np.nan)
    n["nhats_dur_d"] = n["min_dur"].apply(
        lambda x: float(x["dur"]) if isinstance(x, dict) else np.nan)
    # `occ` is the MPC orbit condition code, the same U that SPACE-MAP.md
    # measured a 3.1x enrichment of at the top of the profitability ranking.
    n["occ"] = pd.to_numeric(n["occ"], errors="coerce")
    n = n.rename(columns={"des": "designation"})
    n["designation"] = n["designation"].astype(str).str.strip()
    return n[["designation", "nhats_dv", "nhats_dur_d", "n_via_traj", "occ"]].dropna(
        subset=["nhats_dv"])


def fetch_asterank():
    """Shoemaker-Helin delta-v, keyed BOTH ways.

    `pdes` is float64 on arrival, so it goes through Int64 before it is ever a
    string. Keying on the provisional designation as well is what lets the
    unnumbered bodies join, and they are most of the NHATS set.
    """
    with urllib.request.urlopen(ASTERANK_URL, timeout=180) as fh:
        d = pd.DataFrame(json.load(fh))
    d["dv_sh"] = pd.to_numeric(d["dv"], errors="coerce")
    numbered = pd.to_numeric(d["pdes"], errors="coerce").astype("Int64").astype(str)
    provisional = d["prov_des"].astype(str).str.strip()
    keyed = pd.concat([
        pd.DataFrame({"designation": numbered,    "dv_sh": d["dv_sh"]}),
        pd.DataFrame({"designation": provisional, "dv_sh": d["dv_sh"]}),
    ])
    keyed = keyed[keyed["designation"].ne("<NA>") & keyed["designation"].ne("")]
    return keyed.dropna(subset=["dv_sh"]).drop_duplicates("designation")


def report_nhats(m):
    """One-way against round-trip, the rank agreement, and the orbit quality."""
    d  = m["dv_out_shipped"].to_numpy(float)
    rt = m["nhats_dv"].to_numpy(float)
    over = d > rt

    print(f"\nNHATS  (n = {len(m):,} joined)")
    print(f"  perihelion rendezvous wins    : {(m.apsis == 'perihelion').sum():,}"
          f"  ({(m.apsis == 'perihelion').mean() * 100:.1f}%)")
    print(f"  shipped one-way        median : {np.median(d):7.3f} km/s")
    print(f"  NHATS round-trip (JPL) median : {np.median(rt):7.3f} km/s")
    print(f"  ratio one-way / round-trip    : median {np.median(d / rt):.4f}"
          f"  p90 {np.percentile(d / rt, 90):.4f}  max {(d / rt).max():.4f}")
    print(f"  ONE-WAY EXCEEDS ROUND TRIP    : {over.sum():,} / {len(d):,}"
          f"  ({over.mean() * 100:.2f}%)   <- structurally impossible")
    if over.any():
        v = m[over]
        print(f"    those bodies: median a {v.semi_major_axis_au.median():.3f}"
              f"  e {v.eccentricity.median():.3f}"
              f"  i {v.inclination_deg.median():.2f} deg"
              f"  max excess {(v.dv_out_shipped - v.nhats_dv).max():.3f} km/s")

    rho = m[["dv_out_shipped", "nhats_dv"]].corr(method="spearman").iloc[0, 1]
    print(f"\n  rank agreement with JPL (Spearman) : {rho:.4f}")
    for lab, sel in (("U <= 2", m.occ <= 2), ("U <= 4", m.occ <= 4),
                     ("U >= 5", m.occ >= 5)):
        s = m[sel.fillna(False)]
        if len(s) < 30:
            continue
        r = s[["dv_out_shipped", "nhats_dv"]].corr(method="spearman").iloc[0, 1]
        print(f"    {lab:8s} n = {len(s):6,}   {r:.4f}")

    q = int(m["occ"].notna().sum())
    print("\n  orbit quality of the ACCESSIBLE population:")
    print(f"    U >= 5 : {(m.occ >= 5).sum():,} / {q:,}"
          f"  ({(m.occ >= 5).sum() / q * 100:.1f}%)"
          f"   against 13.9% of the catalog (SPACE-MAP.md)")


def report_asterank(m):
    """The shipped estimator against the published closed form."""
    gap = m["dv_sh"] - m["dv_out_shipped"]
    rho = m[["dv_out_shipped", "dv_sh"]].corr(method="spearman").iloc[0, 1]
    print(f"\nSHOEMAKER-HELIN  (n = {len(m):,} joined)")
    print(f"  shipped one-way  median : {m.dv_out_shipped.median():7.3f} km/s")
    print(f"  Shoemaker-Helin  median : {m.dv_sh.median():7.3f} km/s")
    print(f"  gap S-H minus shipped   : median {gap.median():+.3f}"
          f"  mean {gap.mean():+.3f}"
          f"  p10 {np.percentile(gap, 10):+.3f}"
          f"  p90 {np.percentile(gap, 90):+.3f}")
    print(f"  shipped BELOW S-H       : {(gap > 0).sum():,} / {len(m):,}"
          f"  ({(gap > 0).mean() * 100:.1f}%)")
    print(f"  rank agreement (Spearman) : {rho:.4f}")


def main():
    """Reference check, then NHATS, then optionally Shoemaker-Helin."""
    ap = argparse.ArgumentParser(description="NHATS delta-v cross-check")
    ap.add_argument("--catalog", default=DEFAULT_CATALOG)
    ap.add_argument("--asterank", action="store_true",
                    help="also compare against the Shoemaker-Helin closed form")
    ap.add_argument("--out", default=None, help="write the joined frame here")
    args = ap.parse_args()

    if not check_reference():
        return

    cat = load_catalog(args.catalog)
    print(f"\ncatalog: {len(cat):,} usable rows")

    n = fetch_nhats()
    print(f"NHATS  : {len(n):,} NEAs from JPL")
    m = n.merge(cat, on="designation", how="inner")
    print(f"joined : {len(m):,}  ({len(m) / len(n) * 100:.1f}% of NHATS)")

    m["dv_out_shipped"], m["apsis"] = dv_out_shipped(
        m.semi_major_axis_au.to_numpy(float),
        m.eccentricity.to_numpy(float),
        m.inclination_deg.to_numpy(float))
    m = m[np.isfinite(m["dv_out_shipped"])]
    report_nhats(m)

    if args.asterank:
        sh = fetch_asterank()
        s = sh.merge(cat, on="designation", how="inner")
        if s.empty:
            print("\nSHOEMAKER-HELIN: joined 0 rows -- check the merge key")
        else:
            s["dv_out_shipped"], s["apsis"] = dv_out_shipped(
                s.semi_major_axis_au.to_numpy(float),
                s.eccentricity.to_numpy(float),
                s.inclination_deg.to_numpy(float))
            report_asterank(s[np.isfinite(s["dv_out_shipped"])])

    if args.out:
        m.to_csv(args.out, index=False)
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
