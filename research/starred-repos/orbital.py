# -*- coding: utf-8 -*-
"""Orbital mechanics helpers the pipeline does not have, numpy only.

Module 4 prices transfers from three elements (a, e, i) with a closed-form
patched conic that meets the target at an apsis.  The catalog carries three
MORE elements that nothing reads (`longitude_asc_node_deg`,
`arg_perihelion_deg`, `mean_anomaly_deg`), and those are what a real transfer
needs.  This module supplies the pieces required to use them.

WHAT IS HERE AND WHERE IT CAME FROM

    kepler_E, true_anomaly       adapted from skyfield (MIT, Brandon Rhodes),
    elements_to_state            `skyfield/keplerlib.py`.  The copyright and
                                 permission notices, and what was changed, are
                                 in the repo-root CITATIONS.md, which is the
                                 single authority for attribution here.
    lambert_izzo                 implemented from Izzo (2015), "Revisiting
                                 Lambert's problem", Celest Mech Dyn Astr
                                 121:1-15.  Algorithm from the paper, not
                                 copied from any implementation.

WHAT THIS IS FOR, AND WHAT IT IS NOT FOR

    ⚠️  A Lambert solve is NOT a drop-in replacement for
    `asteroid_transfer_dv_km_s`.  A real transfer needs a grid over departure
    epoch and time of flight (a porkchop) per body, which is thousands of
    solves per asteroid against 1.55 M asteroids.  The pipeline's whole
    architecture search already runs in ~1.6 h on the default cell; this would
    end that.

    ✅  What it IS for is a VALIDATION ORACLE on a sample: take a few hundred
    bodies, find the true minimum two-impulse delta-v with real phasing, and
    measure how far the closed-form estimator is from it.  That number does
    not exist anywhere in this project, and the estimator's docstring compares
    against five hand-picked bodies.

    See `probe_lambert.py`, which does exactly that.

No dependency beyond numpy.  Nothing here imports master or touches
`asteroid_pipeline/`.
"""

import numpy as np

# ── Constants, matching modules/calc.py where they overlap ──────────────────
MU_SUN_KM3_S2 = 1.32712440018e11
AU_KM         = 1.495978707e8
V_EARTH_KM_S  = 29.784
DAY_S         = 86400.0

_TWO_PI = 2.0 * np.pi


# ═══════════════════════════════════════════════════════════════════════════
#  KEPLER
# ═══════════════════════════════════════════════════════════════════════════

def kepler_E(e, M, tol=1e-13, max_iter=60):
    """Solve Kepler's equation M = E - e sin E for the eccentric anomaly.

    Vectorised over both arguments.  Uses the starter of arXiv:2108.03215 and
    a quartic Newton step, which is the scheme skyfield's
    `keplerlib.eccentric_anomaly` uses; adapted from it (MIT) rather than
    copied verbatim so it can broadcast over arrays without its scalar
    early-exit.

    Elliptical orbits only (0 <= e < 1), which is every row this catalog keeps.
    """
    e = np.asarray(e, dtype=float)
    M = np.asarray(M, dtype=float)

    # Wrap to (-pi, pi] and exploit the odd symmetry of Kepler's equation.
    M = (M + np.pi) % _TWO_PI - np.pi
    sign = np.where(M < 0.0, -1.0, 1.0)
    M = np.abs(M)

    e_safe = np.clip(e, 1e-12, 1.0 - 1e-12)
    ebar = 0.25 * np.pi / e_safe - 1.0
    E = 0.5 * np.pi * ebar * (
        np.sign(ebar) * np.sqrt(1.0 + M / (e_safe * ebar * ebar)) - 1.0
    )
    E = np.where(np.isfinite(E), E, M)

    for _ in range(max_iter):
        f1 = 1.0 - e_safe * np.cos(E)
        f2 = e_safe * np.sin(E)
        f = E - f2 - M
        dE = f * f1 / (f1 * f1 - 0.5 * f * f2)
        E = E - dE
        if np.all(np.abs(dE) < tol):
            break

    return E * sign


def true_anomaly(e, E):
    """True anomaly from eccentricity and eccentric anomaly, elliptical case."""
    e = np.asarray(e, dtype=float)
    E = np.asarray(E, dtype=float)
    return 2.0 * np.arctan2(
        np.sqrt(1.0 + e) * np.sin(0.5 * E),
        np.sqrt(1.0 - e) * np.cos(0.5 * E),
    )


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


def propagate_elements(a, e, i, raan, argp, M0, dt_s, mu=MU_SUN_KM3_S2):
    """State vectors `dt_s` seconds after the epoch at which mean anomaly was M0."""
    a = np.asarray(a, float)
    n = np.sqrt(mu / a ** 3)                 # mean motion, rad/s
    M = np.asarray(M0, float) + n * np.asarray(dt_s, float)
    E = kepler_E(e, M)
    nu = true_anomaly(e, E)
    return elements_to_state(a, e, i, raan, argp, nu, mu)


# ═══════════════════════════════════════════════════════════════════════════
#  LAMBERT  (Izzo 2015)
# ═══════════════════════════════════════════════════════════════════════════

def _hyp2f1b(x):
    """The 2F1(3, 1; 5/2; x) series Izzo uses in the Battin regime."""
    if x >= 1.0:
        return np.inf
    total = 1.0
    term = 1.0
    ii = 0.0
    while True:
        term = term * (3.0 + ii) * (1.0 + ii) / (2.5 + ii) * x / (ii + 1.0)
        new = total + term
        if new == total:
            return total
        total = new
        ii += 1.0


def _tof_x(x, lam, N):
    """Non-dimensional time of flight for the free parameter x (Izzo eq. 9-20)."""
    battin, lagrange = 0.01, 0.2
    dist = abs(x - 1.0)

    if lagrange > dist > battin:                      # Lagrange form
        a = 1.0 / (1.0 - x * x)
        if a > 0.0:
            alfa = 2.0 * np.arccos(np.clip(x, -1.0, 1.0))
            beta = 2.0 * np.arcsin(np.clip(np.sqrt(lam * lam / a), -1.0, 1.0))
            if lam < 0.0:
                beta = -beta
            return (a * np.sqrt(a)
                    * ((alfa - np.sin(alfa)) - (beta - np.sin(beta)) + _TWO_PI * N)) / 2.0
        alfa = 2.0 * np.arccosh(x)
        beta = 2.0 * np.arcsinh(np.sqrt(-lam * lam / a))
        if lam < 0.0:
            beta = -beta
        return -a * np.sqrt(-a) * ((beta - np.sinh(beta)) - (alfa - np.sinh(alfa))) / 2.0

    K = lam * lam
    E = x * x - 1.0
    rho = abs(E)
    z = np.sqrt(1.0 + K * E)

    if dist < battin:                                 # Battin series
        eta = z - lam * x
        S1 = 0.5 * (1.0 - lam - x * eta)
        Q = (4.0 / 3.0) * _hyp2f1b(S1)
        return (eta ** 3 * Q + 4.0 * lam * eta) / 2.0 + N * np.pi / rho ** 1.5

    y = np.sqrt(rho)                                   # Lancaster form
    g = x * z - lam * E
    if E < 0.0:
        d = N * np.pi + np.arccos(np.clip(g, -1.0, 1.0))
    else:
        d = np.log(max(y * (z - lam * x) + g, 1e-300))
    return (x - lam * z - d / y) / E


def _dtof_dx(x, T, lam):
    """First three derivatives of the time of flight with respect to x."""
    ll = lam * lam
    if abs(x - 1.0) < 1e-11:                           # parabolic limit
        d1 = 0.4 * (ll * lam - 1.0)
        d2 = 0.4 * (ll * ll * lam - 1.0)
        d3 = d2
        return d1, d2, d3
    umx2 = 1.0 - x * x
    y = np.sqrt(1.0 - ll * umx2)
    d1 = 1.0 / umx2 * (3.0 * T * x - 2.0 + 2.0 * ll * lam * x / y)
    d2 = 1.0 / umx2 * (3.0 * T + 5.0 * x * d1 + 2.0 * (1.0 - ll) * ll * lam / y ** 3)
    d3 = 1.0 / umx2 * (7.0 * x * d2 + 8.0 * d1 - 6.0 * (1.0 - ll) * ll * ll * lam / y ** 5)
    return d1, d2, d3


def _householder(T, x0, lam, N, tol=1e-13, max_iter=40):
    """Householder root find on the time-of-flight equation."""
    x = x0
    for _ in range(max_iter):
        y = _tof_x(x, lam, N)
        fr = y - T
        if abs(fr) < tol:
            return x
        d1, d2, d3 = _dtof_dx(x, y, lam)
        den = d1 * d1 - fr * d2 / 2.0
        num = d1 * d1 - fr * d2 / 2.0
        step = fr * (num) / (d1 * (den) - fr * fr * d3 / 6.0) if d1 != 0.0 else 0.0
        # Householder third order, written the way Izzo states it
        step = fr * (d1 * d1 - fr * d2 / 2.0) / (
            d1 * (d1 * d1 - fr * d2) + d3 * fr * fr / 6.0
        )
        x = x - step
        if abs(step) < tol:
            return x
    return x


def lambert_izzo(r1, r2, tof_s, mu=MU_SUN_KM3_S2, prograde=True, revs=0):
    """Solve Lambert's problem: the transfer connecting r1 to r2 in `tof_s`.

    Implemented from Izzo (2015), "Revisiting Lambert's problem".  Returns
    (v1, v2) in km/s, or (None, None) if the geometry is degenerate.

    `r1`, `r2` are 3-vectors in km.  Only the zero-revolution solution is
    returned when `revs` is 0, which is the case a minimum-energy transfer
    search wants.
    """
    r1 = np.asarray(r1, float); r2 = np.asarray(r2, float)
    tof_s = float(tof_s)
    if tof_s <= 0:
        return None, None

    R1 = np.linalg.norm(r1); R2 = np.linalg.norm(r2)
    if R1 == 0 or R2 == 0:
        return None, None

    c_vec = r2 - r1
    c = np.linalg.norm(c_vec)
    s = 0.5 * (R1 + R2 + c)

    i_r1 = r1 / R1
    i_r2 = r2 / R2
    i_h = np.cross(i_r1, i_r2)
    nh = np.linalg.norm(i_h)
    if nh == 0:
        return None, None
    i_h = i_h / nh

    lam2 = max(0.0, 1.0 - c / s)
    lam = np.sqrt(lam2)

    if i_h[2] < 0.0:                                   # retrograde geometry
        lam = -lam
        i_t1 = np.cross(i_r1, i_h)
        i_t2 = np.cross(i_r2, i_h)
    else:
        i_t1 = np.cross(i_h, i_r1)
        i_t2 = np.cross(i_h, i_r2)
    i_t1 /= np.linalg.norm(i_t1)
    i_t2 /= np.linalg.norm(i_t2)

    if not prograde:
        lam = -lam
        i_t1 = -i_t1
        i_t2 = -i_t2

    T = np.sqrt(2.0 * mu / (s ** 3)) * tof_s

    # Initial guess for the single-revolution branch (Izzo section 4.2).
    T0 = np.arccos(np.clip(lam, -1.0, 1.0)) + lam * np.sqrt(max(0.0, 1.0 - lam * lam))
    T1 = 2.0 / 3.0 * (1.0 - lam ** 3)
    if T >= T0:
        x0 = (T0 / T) ** (2.0 / 3.0) - 1.0
    elif T < T1:
        x0 = 2.5 * T1 * (T1 - T) / (T * (1.0 - lam ** 5)) + 1.0
    else:
        x0 = (T0 / T) ** (np.log2(T1 / T0)) - 1.0

    x = _householder(T, x0, lam, revs)

    gamma = np.sqrt(mu * s / 2.0)
    rho = (R1 - R2) / c
    sigma = np.sqrt(max(0.0, 1.0 - rho * rho))

    y = np.sqrt(max(0.0, 1.0 - lam * lam * (1.0 - x * x)))
    Vr1 = gamma * ((lam * y - x) - rho * (lam * y + x)) / R1
    Vr2 = -gamma * ((lam * y - x) + rho * (lam * y + x)) / R2
    Vt1 = gamma * sigma * (y + lam * x) / R1
    Vt2 = gamma * sigma * (y + lam * x) / R2

    v1 = Vr1 * i_r1 + Vt1 * i_t1
    v2 = Vr2 * i_r2 + Vt2 * i_t2
    return v1, v2
