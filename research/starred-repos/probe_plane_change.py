# -*- coding: utf-8 -*-
"""Where the plane change is paid: a measurement, not an argument.

Module 4's `_transfer_legs_for_apsis` bundles the ENTIRE inclination change
into the Earth-departure v_infinity (law of cosines against Earth's velocity)
and then takes a COPLANAR scalar speed difference at the rendezvous apsis.
That is one self-consistent patched conic, and it is a RULE rather than a
search: the same shape calc v1.10.0 replaced when it stopped guessing the
rendezvous apsis and started pricing both.

Three placements of the same plane change, numpy only, no new dependency:

    A   all of it at departure       (the shipped model, delta = i)
    B   all of it at the rendezvous  (delta = 0)
    C   split it, best delta wins    (A and B are its endpoints)

C >= A by construction, so the never-worse invariant holds for free and needs
no new argument.

This script READS ONLY.  It does not import master, does not build a stage,
and does not write to `asteroid_pipeline/`, so it cannot invalidate a
`.verify` baseline.

Usage:
    py research/starred-repos/probe_plane_change.py
    py research/starred-repos/probe_plane_change.py path/to/asteroid_catalog.csv
"""

import sys

import numpy as np
import pandas as pd

# Mirrored from modules/calc.py.  Deliberately copied rather than imported:
# importing calc.py fires its INSTALLATION block, which pip-installs into the
# live environment, and this probe must not disturb a measurement host.
V_EARTH_KM_S    = 29.784
MU_EARTH_KM3_S2 = 398_600.4418
R_LEO_KM        = 6_378.14 + 200.0

_V_LEO = np.sqrt(MU_EARTH_KM3_S2 / R_LEO_KM)
_V_ESC = np.sqrt(2.0) * _V_LEO

DEFAULT_CATALOG = "asteroid_pipeline/asteroid_catalog.csv"

# The five bodies asteroid_transfer_dv_km_s's docstring is validated against.
# Reproducing these to four decimals is what says this probe is measuring the
# shipped model and not a different one.
REFERENCE = pd.DataFrame({
    "body":              ["main belt ref", "moderate NEA", "Bennu", "Eros", "Itokawa"],
    "semi_major_axis_au": [2.700, 1.200, 1.126, 1.458, 1.324],
    "eccentricity":       [0.100, 0.300, 0.204, 0.223, 0.280],
    "inclination_deg":    [10.00, 8.000, 6.000, 10.80, 1.600],
    "docstring_dv_out":   [10.43, 5.580, 4.640, 6.100, 4.140],
})


def leo_departure_dv_km_s(v_inf_km_s):
    """Delta-v from circular LEO onto a hyperbola with this v_infinity.

    Vectorised copy of `_leo_departure_dv_km_s` in modules/calc.py.
    """
    return np.sqrt(_V_ESC ** 2 + v_inf_km_s ** 2) - _V_LEO


def dv_out_km_s(a, i_deg, r_target, delta_deg):
    """Outbound delta-v with `delta_deg` of the plane change taken at departure.

    All heliocentric work is in canonical units (Earth orbit radius = 1, Earth
    orbital speed = 1) and converted to km/s at the end, matching Module 4.

    delta_deg == i_deg reproduces the shipped model exactly.
    """
    i     = np.radians(i_deg)
    delta = np.radians(delta_deg)
    a_t   = (1.0 + r_target) / 2.0

    v_t_earth  = np.sqrt(np.clip(2.0 / 1.0      - 1.0 / a_t, 1e-12, None))
    v_t_target = np.sqrt(np.clip(2.0 / r_target - 1.0 / a_t, 1e-12, None))
    v_ast      = np.sqrt(np.clip(2.0 / r_target - 1.0 / a,   1e-12, None))

    # Departure: vector difference against Earth's velocity, carrying `delta`.
    v_inf = np.sqrt(np.clip(
        v_t_earth ** 2 + 1.0 - 2.0 * v_t_earth * np.cos(delta), 0.0, None,
    )) * V_EARTH_KM_S

    # Arrival: vector difference against the asteroid, carrying the rest.
    dv_match = np.sqrt(np.clip(
        v_t_target ** 2 + v_ast ** 2
        - 2.0 * v_t_target * v_ast * np.cos(i - delta), 0.0, None,
    )) * V_EARTH_KM_S

    return leo_departure_dv_km_s(v_inf) + dv_match


def best_split(a, i_deg, r_target, steps=181):
    """Scan the departure share of the plane change; return (dv, fraction)."""
    best = np.full(np.shape(a), np.inf, dtype=float)
    frac = np.zeros(np.shape(a), dtype=float)
    for f in np.linspace(0.0, 1.0, steps):
        dv = dv_out_km_s(a, i_deg, r_target, i_deg * f)
        hit = dv < best
        best = np.where(hit, dv, best)
        frac = np.where(hit, f, frac)
    return best, frac


def check_reference():
    """Reproduce the docstring's five validated figures, model A and model C."""
    r = REFERENCE.copy()
    a = r["semi_major_axis_au"].to_numpy(float)
    e = r["eccentricity"].to_numpy(float)
    i = r["inclination_deg"].to_numpy(float)
    Q = a * (1.0 + e)

    r["model_A"] = dv_out_km_s(a, i, Q, i)
    r["model_C"], r["dep_frac"] = best_split(a, i, Q, steps=361)
    r["saving"]  = r["model_A"] - r["model_C"]
    r["A_minus_docstring"] = r["model_A"] - r["docstring_dv_out"]

    print("REFERENCE BODIES  (model A must reproduce the docstring)")
    print(r.to_string(index=False, float_format=lambda x: f"{x:9.4f}"))
    worst = r["A_minus_docstring"].abs().max()
    print(f"\n  worst |model A - docstring| = {worst:.4f} km/s "
          f"({'OK' if worst < 0.01 else 'MISMATCH -- this probe is not the shipped model'})")


def survey(df, label, stride=40):
    """Price all three placements over a stride sample of the real catalog."""
    d = df.iloc[::stride]
    a = d["semi_major_axis_au"].to_numpy(float)
    e = d["eccentricity"].to_numpy(float)
    i = d["inclination_deg"].to_numpy(float)
    Q = a * (1.0 + e)

    A = dv_out_km_s(a, i, Q, i)
    B = dv_out_km_s(a, i, Q, 0.0)
    C, frac = best_split(a, i, Q)

    ok = np.isfinite(A) & np.isfinite(C) & (A > 0)
    A, B, C, frac, i = A[ok], B[ok], C[ok], frac[ok], i[ok]
    saving = A - C
    rel    = saving / A

    print(f"\n{label}  (n = {ok.sum():,}, stride 1-in-{stride})")
    print(f"  A  all-at-departure (shipped) : median {np.median(A):8.3f} km/s")
    print(f"  B  all-at-arrival             : median {np.median(B):8.3f} km/s")
    print(f"  C  best split                 : median {np.median(C):8.3f} km/s")
    print(f"  C never worse than A          : {bool(np.all(C <= A + 1e-9))}")
    print(f"  saving A-C   median {np.median(saving):7.4f}  mean {saving.mean():7.4f}"
          f"  p90 {np.percentile(saving, 90):7.4f}  max {saving.max():8.4f} km/s")
    print(f"  relative     median {np.median(rel) * 100:6.2f}%  mean {rel.mean() * 100:6.2f}%"
          f"  p90 {np.percentile(rel, 90) * 100:6.2f}%  max {rel.max() * 100:6.2f}%")
    print(f"  shipped rule already optimal  : {(frac > 0.999).sum():,}"
          f"  ({(frac > 0.999).mean() * 100:.2f}%)")
    print(f"  rows saving > 0.5 km/s        : {(saving > 0.5).sum():,}"
          f"  ({(saving > 0.5).mean() * 100:.2f}%)")
    print(f"  rows saving > 1.0 km/s        : {(saving > 1.0).sum():,}"
          f"  ({(saving > 1.0).mean() * 100:.2f}%)")
    print(f"  median optimal departure share of i : {np.median(frac):.3f}")
    steep = i > 15.0
    if steep.any():
        print(f"  i > 15 deg (n={steep.sum():,}) : median saving "
              f"{np.median(saving[steep]):.4f} km/s "
              f"({np.median(rel[steep]) * 100:.2f}%)")


def main():
    """Run the reference check, then the catalog survey."""
    check_reference()
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CATALOG
    cols = ["semi_major_axis_au", "eccentricity", "inclination_deg"]
    df = pd.read_csv(path, usecols=cols, low_memory=False)
    df = df[(df["semi_major_axis_au"] > 0)
            & (df["eccentricity"] >= 0) & (df["eccentricity"] < 1)]
    survey(df, "FULL CATALOG")


if __name__ == "__main__":
    main()
