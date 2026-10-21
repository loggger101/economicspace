# -*- coding: utf-8 -*-
"""Classical orbital elements to heliocentric state vectors, numpy only.

`ui.py`'s orbit diagram draws each body's ellipse with `elements_to_state`,
which is all this file carries.  It is adapted from skyfield (MIT, Brandon
Rhodes), `skyfield/keplerlib.py`; the copyright and permission notices, and
what was changed, are in the repo-root CITATIONS.md, which is the single
authority for attribution here.

The Kepler solver, the propagator and the Izzo (2015) Lambert solver that
used to sit beside it belong to the starred-repo audit, whose
`probe_lambert.py` is their one caller, and live in its copy of this file
(https://github.com/loggger101/starred-repos).  Nothing here calls them.

No dependency beyond numpy.  Nothing here imports master or touches
`asteroid_pipeline/`.
"""

import numpy as np

# The Sun's gravitational parameter, `elements_to_state`'s default `mu`.  The
# diagram passes `a` in AU and reads only the position, which `mu` does not
# reach.
MU_SUN_KM3_S2 = 1.32712440018e11


def elements_to_state(a, e, i, raan, argp, nu, mu=MU_SUN_KM3_S2):
    """Heliocentric state vectors from classical elements.

    Adapted from skyfield's `keplerlib.ele_to_vec` (MIT, Brandon Rhodes),
    restricted to the elliptical case and re-expressed in terms of the
    semi-major axis rather than the semi-latus rectum, because that is what
    this catalog stores.

    Angles in RADIANS, `a` in km.  Returns (r, v) each shaped (3, ...) in km
    and km/s.
    """
    a = np.asarray(a, float); e = np.asarray(e, float)
    i = np.asarray(i, float); raan = np.asarray(raan, float)
    argp = np.asarray(argp, float); nu = np.asarray(nu, float)

    p = a * (1.0 - e * e)                    # semi-latus rectum
    r = p / (1.0 + e * np.cos(nu))
    h = np.sqrt(p * mu)
    u = nu + argp                            # argument of latitude

    cO, sO = np.cos(raan), np.sin(raan)
    cu, su = np.cos(u), np.sin(u)
    ci, si = np.cos(i), np.sin(i)

    X = r * (cO * cu - sO * su * ci)
    Y = r * (sO * cu + cO * su * ci)
    Z = r * (si * su)

    k = h * e / (r * p) * np.sin(nu)
    Xd = X * k - h / r * (cO * su + sO * cu * ci)
    Yd = Y * k - h / r * (sO * su - cO * cu * ci)
    Zd = Z * k + h / r * si * cu

    return np.array([X, Y, Z]), np.array([Xd, Yd, Zd])
