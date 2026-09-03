# What the starred repositories are worth to this pipeline

A pass over the 17 non-agent-tooling repositories starred on `loggger101`,
read against this pipeline's actual code rather than against their READMEs.

**The five findings below are measurements taken on this repo's own catalog,
not summaries of somebody else's project.** Each has a probe script beside this
file that reproduces it. The per-repository inventory, with licences and the
specific files worth reading, is in [`SOURCES.md`](SOURCES.md).

✅  **APPLIED 2026-09-03 as catalog `1.2.0` / master `1.23.0`.** F5 and the
NEOWISE async patch are in `modules/catalog.py`; F3's gap is closed by
`probe_pandas_dtypes` in `platform_check.py`; F3's stale prose is corrected in
CLAUDE.md; F4's headline is now a documented limitation in README. See
[versions.md > catalog v1.2.0](../../versions.md#catalog-v120).

🚨  **F1 WAS NOT APPLIED, DELIBERATELY.** F4 measures it as making the model
worse in every inclination band. See the reversal table in F4.

🚨  **AND VERIFYING THE NEOWISE PATCH FOUND A THIRD DEFECT THAT WAS ON NO
PLAN.** Its `ORDER BY` named only `asteroid_number`, which is not total over a
table holding 183,408 rows for 143,318 bodies, so `deduplicate_catalog`'s
stable sort resolved **27,802 bodies by arrival order alone**, with a median
diameter spread of 11.6% and a maximum of 86.3%. Diameter cubes into mass. It
surfaced only because the patch was verified by comparing both transports
rather than by reasoning that they must agree; the two returned the same
content hash in a different order. Fixed in the same release, and it is the
only item in it that moves a number. Full write-up in `versions.md`.

The rest of this document is the audit as written before any of that, kept as
the measurement record.

---

## F1. Two orbital elements are fetched, stored, and read by nothing

Module 1 writes six orbital elements per body. Module 4 reads three.

| column | populated | read by `calc.py` | read by `mineral_value.py` |
|---|---|---|---|
| `semi_major_axis_au` | 1,555,667 | yes | - |
| `eccentricity` | 1,555,667 | yes | - |
| `inclination_deg` | 1,555,667 | yes | - |
| **`longitude_asc_node_deg`** | **1,555,667** | **no** | **no** |
| **`arg_perihelion_deg`** | **1,555,667** | **no** | **no** |
| **`mean_anomaly_deg`** | **1,555,667** | **no** | **no** |
| `mean_motion_deg_day` | 1,555,485 | no | no |
| `orbital_period_yr` | 1,555,667 | no | no |

100% populated, zero references outside Module 1. `grep -c` in each module
confirms it.

### What that costs, measured

`_transfer_legs_for_apsis` bundles the **entire** inclination change into the
Earth-departure `v_infinity` by law of cosines, then takes a coplanar scalar
speed difference at the rendezvous apsis. That is self-consistent, and it is a
**rule**, not a search: exactly the shape v1.10.0 replaced when it stopped
guessing the rendezvous apsis and started pricing both.

`probe_plane_change.py` prices three placements of the same plane change, with
numpy only and no new dependency:

- **A**, all of it at departure. This is the shipped model.
- **B**, all of it at the rendezvous.
- **C**, split it, and take the best split. A and B are its endpoints, so
  **C is never worse than A by construction**, and the never-worse invariant
  holds without a new argument.

The probe reproduces every validated figure in `asteroid_transfer_dv_km_s`'s
docstring to four decimals, which is what says it is measuring the shipped
model and not a different one:

| body | docstring | probe (model A) | model C | saving |
|---|---|---|---|---|
| main belt ref (a=2.7, e=0.1, i=10) | 10.43 | **10.4285** | 9.6633 | 0.7652 |
| moderate NEA (a=1.2, e=0.3, i=8) | 5.58 | **5.5828** | 5.4367 | 0.1461 |
| Bennu | 4.64 | **4.6391** | 4.5922 | 0.0469 |
| Eros | 6.10 | **6.0919** | 5.8851 | 0.2068 |
| Itokawa | 4.14 | **4.1344** | 4.1323 | 0.0021 |

On a 1-in-40 stride of the real catalog, n = 38,892:

```
A  all-at-departure (shipped) : median  9.904 km/s
B  all-at-arrival             : median  9.610 km/s
C  best split                 : median  9.442 km/s
C never worse than A          : True

saving A-C   median 0.4692   mean 0.8672   p90 2.0887   max 54.9577 km/s
relative     median 4.87%    mean 7.17%    p90 16.74%   max 83.51%

rows where the shipped rule is already optimal : 3  (0.01%)
rows saving > 0.5 km/s : 19,038 (48.95%)
rows saving > 1.0 km/s : 12,062 (31.01%)
median optimal fraction of i taken at departure : 0.356
i > 15 deg subset (n=6,279) : median saving 2.2910 km/s (17.86%)
```

**The shipped placement is optimal on 3 rows out of 38,892.** The median body
wants about a third of its plane change at departure and the rest on arrival.

### Cautions before acting on this

⚠️  **It makes the estimator MORE optimistic, and it was already optimistic.**
The docstring's own comparison has the estimator below published mission Δv on
all three real bodies (Bennu 4.64 against ~5.1, Eros 6.10 against ~6.5, Itokawa
4.14 against ~4.6). Model C widens that gap rather than closing it, so this
change cannot be sold as "closer to the published numbers".

🚨  **This paragraph originally explained that gap as "a free two-impulse
optimum should beat a real mission, which pays for fixed launch dates and
finite burns". F4 measured it and that explanation is WRONG.** A free
two-impulse optimum with real geometry comes out **above** the published figure
on all three bodies, not below it. The estimator is not beating real missions
by being unconstrained; it is understating the transfer. The correction is kept
visible rather than quietly rewritten, because a plausible mechanism asserted
without measurement is exactly what this repo's own notes warn about.

⚠️  **It moves every number in the model.** Δv feeds the mass cascade, so a
median 4.87% cut to `dv_out` changes payload, cost, ratio, and ranking on
essentially every evaluable row. That is a full re-measurement of the campaign,
not a point release.

🚨  **AND THE ONE THAT DECIDES IT, ADDED AFTER F4 WAS MEASURED: DO NOT MAKE
THIS CHANGE ON ITS OWN. IT MAKES THE MODEL WORSE.** F1 is a real overcharge, but the
estimator carries a larger *under*charge of opposite sign, and the two
partially cancel. Removing only the overcharge exposes the undercharge in full.
See F4, which measures both on the same bodies. **This paragraph supersedes the
recommendation this document originally made.**

### What the starred repos add here

`Ω` and `ω` are what a real transfer needs and model C still does not use:
it splits the plane change but does not place it at the line of nodes, which is
where `Ω` and `ω` decide the true cost. Getting that right means a Lambert
solve, and that is now built: see [`orbital.py`](orbital.py) and F4.

---

## F2. Composition rests on a taxonomy that is guessed for 93% of the bodies that matter

Every value in this model flows from `comp_metal_fraction`,
`comp_carbon_fraction`, `comp_ice_fraction` and `comp_pgm_enrichment`, and all
four are looked up from `spectral_type` through `TAXONOMY_COMPOSITION`. So the
reliability of `spectral_type` is the reliability of the answer.

### Provenance, on this catalog

| population | rows | taxonomy from a real source |
|---|---|---|
| all bodies | 1,555,667 | 171,007 (11.0%) |
| **NEOs** | **42,088** | **2,937 (6.98%)** |

`albedo_assumed` covers 1,300,139 rows overall and **37,957 of 42,088 NEOs
(90.2%)**. The NEOs are the economically decisive population, and their
composition is inferred from albedo alone on nine bodies in ten.

### Where a second opinion exists, it disagrees a third of the time

The PDS3 archive `EAR_A_I0035_5_SDSSTAX_V1_1` (SDSS-based asteroid taxonomy,
Carvano et al. 2010) gives 63,468 numbered asteroids an independent class from
u'g'r'i'z' photometry. I found it through **juliensimon/space-datasets**, which
carries the fixed-width column specs; the archive itself is 7.5 MB and live.

44,061 of them join this catalog, and **every one already has
`spectral_type_source = "source"`**, so SDSS adds no coverage. What it adds is
a check, and the check does not pass:

```
first letter agrees                      : 27,505 / 44,061  (62.4%)
comp_group agrees                        : 29,126 / 44,061  (66.1%)
comp_group agrees, SDSS score >= 60      : 70.4%   (n = 10,133)
```

The disagreements land where the money is:

| SsODNet says | SDSS says | bodies | metal fraction |
|---|---|---|---|
| S-complex | L-type | 3,604 | 0.15 -> 0.05 |
| **X-complex** | **C-complex** | **2,611** | **0.30 -> 0.01** |
| S-complex | Q-type | 1,009 | 0.15 -> 0.20 |
| C-complex | X-complex | 719 | 0.01 -> 0.30 |

Carried through `TAXONOMY_COMPOSITION`:

```
metal  fraction changes on 14,864 bodies (33.7%)  median |delta| 0.100  max 0.490
carbon fraction changes on 15,394 bodies (34.9%)  median |delta| 0.050  max 0.290
ice    fraction changes on  7,866 bodies (17.9%)  median |delta| 0.150  max 0.250
```

### The part that makes it worse rather than better

🚨  **The second opinion does not reach the population that decides the
result.** SDSS is a main-belt survey of numbered bodies; only **3,874 of 42,088
NEOs (9.2%)** are even numbered, and none of the top 25 rows of the profitability
catalog on disk joins it at all. So the 33.9% disagreement rate is measured
where two surveys overlap, and the bodies that actually win have **one**
classification, no second opinion, and a 90.2% chance that the one they have was
guessed from albedo.

This is not an argument for a bigger taxonomy table. It is an argument that
`comp_*` is a **distribution, not a scalar**, and the model reports a point
estimate of it. That is what **pymc-devs/pymc** is for, and it is the only use
of that star that survives contact with this codebase: put a categorical prior
over `spectral_type` for `albedo_assumed` rows, propagate it through the value
model, and report the ranking with a credible interval instead of a number.
The 33.9% cross-survey disagreement is the calibration data for that prior.

---

## F3. The interpreter and pandas moved under the repo, and CLAUDE.md's correction is now itself stale

Found incidentally: a script of mine failed with
`ArrowNotImplementedError: ... (large_string, double)`, which is a pandas 3.0
Arrow-backed string dtype, not a pandas 2.x object dtype.

CLAUDE.md's Environment section carries a 🚨 block, dated 2026-09-03, asserting
that the section wrongly said 3.14 and that **"3.14 HAS NEVER BEEN INSTALLED ON
THIS MACHINE"**, with `py -0` quoted as evidence. On this host, right now:

```
py -c "import sys; print(sys.version)"  ->  3.14.6
py -0                                   ->  -V:3.14 *        Python 3.14 (64-bit)
                                            -V:Astral/CPython3.11.16
```

**3.13 is not installed at all any more**, and `py` resolves to 3.14.6.

| | `platform_reference.json` | live now |
|---|---|---|
| python | 3.13.9 | **3.14.6** |
| numpy | 2.2.6 | **2.5.2** |
| pandas | 2.3.3 | **3.0.5** |
| cpu_count | 12 | **14** |

`requirements-lock.txt` and the `Dockerfile` both still pin 3.13.9 / numpy
2.2.6 / pandas 2.3.3.

### The good news is real, and it is the repo's own tool that says so

```
py platform_check.py
  ALL PROBES MATCH.  Cell hashes computed on this host are
  directly comparable with the ones committed in versions.md.
```

Every libm probe, every numpy probe, the CSV CRLF pin and the float round-trip
hash all match across a two-minor-version interpreter jump and a **major**
pandas version. That vindicates `platform_check.py` exactly as designed.

### The gap it cannot see

⚠️  `platform_check.py` probes libm, numpy kernels, and CSV float round-trip.
It does **not** probe pandas dtype inference, and pandas 3.0's headline change
is precisely that: object columns now infer as Arrow-backed `str`. That is the
same surface as three traps CLAUDE.md already documents by name:

- `.astype(bool)` reading `"False"` and `NaN` as `True`, whose whole premise is
  that **"the dtype is inferred from the data"**
- the empty string that is not `NaN` "except that in a CSV it is", trap 3 of the
  three that produced one identical symptom in `verify.py`
- `_truthy(series, default=...)`, which exists to make the missing-value case
  explicit

**Suggested, and not applied:** add three probes to `platform_check.py`, an
all-empty object column written and re-read, a bool column with one missing
value, and a float column round-tripped through `to_csv`/`read_csv` at default
precision. Those are the three that would go quiet under a dtype change, and
they are cheap.

---

## F4. The estimator is optimistic by ~11%, and F1 is the smaller of two errors that cancel

The second pass built what the first pass said was missing: a validated Lambert
solver, so the closed-form estimator can be measured against a real optimised
transfer instead of against five hand-picked bodies.

### The solver is validated, not asserted

[`orbital.py`](orbital.py) implements Izzo (2015) from the paper, plus a Kepler
solver and `elements_to_state` adapted from skyfield (MIT, attributed in the
file). Three independent checks:

| check | result |
|---|---|
| Vallado Example 7-5, geocentric | `v1` and `v2` to **7.4e-07 km/s**, the precision the reference is quoted at |
| round trip: propagate a known orbit, Lambert must recover its velocity | **1e-13 to 1e-14 km/s** over 120, 250 and 400 day arcs |
| Kepler residual over 20,000 random (e, M) | max `abs(E - e sinE - M)` = **4.4e-16** |

### The oracle, and what it says

[`probe_lambert.py`](probe_lambert.py) runs a porkchop per body: Lambert solves
over departure epoch crossed with time of flight, minimising
`leo_departure(|v1 - v_earth|) + |v2 - v_asteroid|` in real 3-D geometry using
all five elements. Departure is scanned over a full synodic period, so the
result is date-free, which is the fair comparison because **the shipped
estimator is date-free too**.

400 bodies, random sample, seed 1:

```
shipped closed form : median   9.957 km/s
Lambert oracle      : median  11.288 km/s
gap (oracle-shipped): median  +1.296 km/s   mean +1.349
relative            : median +11.89%        mean +11.17%

shipped estimator OPTIMISTIC (below the achievable optimum) on 86.0% of bodies

  i < 5 deg    n=102   median gap +1.102 km/s  (+11.25%)
  5-15 deg     n=235   median gap +1.669 km/s  (+14.49%)
  i > 15 deg   n= 63   median gap +0.503 km/s  ( +3.32%)
```

✅  **Converged.** Doubling the time-of-flight window and nearly quadrupling the
grid moves the median gap from +1.181 to +1.124 km/s, under 5%, with zero
bodies at the window boundary:

```
0.25-4.0 yr, 40x34         median oracle 10.540   gap +1.181   0/40 at cap
0.25-8.0 yr, 40x60         median oracle 10.510   gap +1.156   0/40 at cap
0.25-8.0 yr, 72x90 (fine)  median oracle 10.465   gap +1.124   0/40 at cap
```

### The oracle is itself optimistic, so the truth is bracketed

Run against the three real bodies whose published Δv the estimator's docstring
quotes, using their actual `Ω` and `ω` from SBDB:

| body | shipped | oracle | published | shipped - published | oracle - published |
|---|---|---|---|---|---|
| Bennu | 4.640 | 5.395 | 5.10 | **-0.460** | +0.295 |
| Eros | 6.101 | 7.638 | 6.50 | **-0.399** | +1.138 |
| Itokawa | 4.137 | 5.062 | 4.60 | **-0.463** | +0.462 |

**The published figure sits between the two, every time.** The shipped
estimator is low by a strikingly consistent 0.40 to 0.46 km/s; the oracle is
high, because it allows no deep-space manoeuvre, no gravity assist and only
zero-revolution transfers, all of which a real trajectory designer uses.

So the honest statement is: **the estimator understates, the direction is
robust across 400 bodies and three published missions, and the magnitude is
between 0.4 and 1.3 km/s** depending on population. It also explains the
docstring's own unexplained observation that the estimator reads 8 to 12% below
published on all three bodies. That gap is the model's geometry, not the price
of real mission constraints.

### 🚨 The reversal: F1 and F4 have opposite signs and partially cancel

Both models plus the oracle, on the same 200 bodies:

| band | n | shipped error | after the F1 fix | verdict |
|---|---|---|---|---|
| i < 5 deg | 54 | -1.139 | -1.288 | **WORSE** (abs err 1.139 -> 1.288) |
| 5-15 deg | 119 | -1.601 | -2.312 | **WORSE** (abs err 1.601 -> 2.312) |
| **i > 15 deg** | 27 | **-0.533** | **-2.656** | **WORSE** (abs err 1.438 -> 2.656) |
| ALL | 200 | -1.296 | -1.888 | **WORSE** (abs err 1.390 -> 1.888) |

Negative means the model understates the cost.

**Fixing F1 alone makes the estimator worse in every inclination band, and
worst where F1 looked most attractive.** At i > 15 degrees, F1 promised a 17.86%
saving and the residual error there is only -0.533 km/s, so taking the saving
drives the error to -2.656 and nearly doubles it.

The mechanism is legible: the shipped model **overcharges the plane change** and
**undercharges the transfer geometry**, the two are of opposite sign, and the
cancellation is accidental and inclination-dependent. It is not a calibration,
because nobody chose it, and it is not stable, because the two terms scale
differently with inclination.

⚠️  This is the "do not fix a result that looks wrong" rule arriving with
evidence. F1 was measured correctly and read as an improvement because it was
measured against **the model's own internal consistency** rather than against
an external truth. The oracle is the external truth, and it inverts the
conclusion. **Neither term should move without the other.**

---

## F5. `mean_anomaly_deg` is stored without its epoch, so it cannot be used

`_JPL_FIELDS` in `modules/catalog.py` requests `ma`, commented in that file as
"mean anomaly at epoch (deg)". It does not request `epoch`, and the catalog has
no epoch column. A mean anomaly without the epoch it refers to fixes no date,
so `mean_anomaly_deg` is not merely unread (F1), it is **unreadable**.

Verified against the live API, a read-only probe that writes nothing:

```
GET ssd-api.jpl.nasa.gov/sbdb_query.api?fields=pdes,epoch,ma,a,e,i,om,w,n&sb-kind=a&limit=5
  fields: ['pdes','epoch','ma','a','e','i','om','w','n']
  ['1','2461200.5','274.42','2.766','0.0797','10.59','80.25','73.29','0.2143']
```

`epoch` is a valid SBDB field returned as JD TDB. The fix is one entry in
`_JPL_FIELDS` and one in `_JPL_RENAME`.

⚠️  **It must be per row, not a constant.** In a 2,000-row NEO sample the
epochs were not uniform: 1,999 at JD 2461200.5 and one at JD 2455562.5, a
spread of 5,638 days. A hardcoded common epoch would be silently wrong for a
small fraction, which is the quiet-wrong-answer shape.

ℹ️  F4 does not need the epoch and is unaffected by this: scanning departure
over a full synodic period visits every relative phase, so the date-free
optimum is epoch-independent. The epoch matters the moment anyone wants a
**dated** launch window rather than a best-case one.

---

## What I would do, in order

1. **Correct CLAUDE.md's Environment section** (F3). It is the one fact the
   machine answers in a second, the retraction block is now wrong in the other
   direction, and it is the second time this paragraph has rotted. Consider
   deleting the version from prose entirely and pointing at `platform_check.py`,
   which derives it. Decide separately whether to re-pin the lockfile and the
   Dockerfile to 3.14.6, or to reinstall 3.13.9 and keep the reference host.
2. **Add the three pandas dtype probes** to `platform_check.py` (F3). Cheap,
   and it closes the one blast radius the current probes miss.
3. **Take the SDSS table as a committed input** (F2). 7.5 MB, fixed-width, no
   dependency, no API key, and it never changes, so it does not have the
   "Stage 1 refetch changes the catalog" problem. It buys a measured
   disagreement rate, which is the input to any honest error bar.
4. **Add `epoch` to the SBDB field list** (F5). One line in `_JPL_FIELDS`, one
   in `_JPL_RENAME`. It changes no number in a run, and without it
   `mean_anomaly_deg` is dead weight in every CSV the pipeline has ever
   written. Doing it now means the next Stage 1 run captures it; doing it later
   means another full refetch.
5. **Apply the async-TAP NEOWISE fetcher** ([`patch_neowise_async.py`](patch_neowise_async.py)),
   which falls back to the current sync path, so its worst case is today's
   behaviour. Measured byte-identical output against the live service.
6. 🚨  **Do NOT ship F1 on its own.** F4 measures it against an external truth
   and it makes the estimator worse in every inclination band. If the Δv model
   is opened at all, both terms move together, and the target is the oracle,
   not the model's own internal consistency. That is a research project, not a
   release: the honest interim position is that **the pipeline's Δv is
   optimistic by roughly 0.4 to 1.3 km/s and the entire campaign inherits
   that**, which is worth writing down in `README.md` whether or not anything
   is fixed.
7. Everything else in `SOURCES.md` is optional, and several of the stars are
   worth less to this project than they look. Read the verdict column before
   spending time.

⚠️  **Items 1 to 5 are all cheap and none of them moves a number a run
produces.** Item 6 is the opposite on both counts. That split is deliberate:
this pass found one thing worth a lot and several things worth a little, and
the expensive one is the one that needs a decision rather than a patch.

## Licence hazard, one paragraph

This repo has **no LICENSE file**. Four of the seventeen stars are copyleft:
**nyx** and **julie-dujardin/space-map** are AGPL-3.0, **CamPyRoS** is GPL-3.0,
**Celestia** is GPL-2.0. Copying code from any of them makes this pipeline
copyleft. Physics is not copyrightable and reimplementing a published algorithm
from its equations is fine; lifting a function body is not. Everything else
starred is MIT, BSD-3, Apache-2.0 or MPL-2.0 and is safe to vendor with
attribution. Per-repo detail is in `SOURCES.md`.
