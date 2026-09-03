# Per-repository inventory

The 17 non-agent-tooling stars, each read against this pipeline rather than
against its own README. `mattpocock/skills` and `NousResearch/hermes-agent`
were excluded as requested.

**Read the verdict column first.** Five of these are worth real work, five are
worth a specific narrow thing, and seven are worth less to this project than
their star counts suggest. Saying so is the point of the exercise.

Licences were read from each repo's own LICENSE, not from the GitHub label:
four came back `NOASSERTION` and resolved to MIT (z3), BSD-3 (Pyomo),
Apache-2.0 (PyMC) and MIT (space-datasets, code only, data licensed per source).

⚠️  **And one came back `NONE` and is not unlicensed.** `pds4_tools` carries
BSD-3 from the University of Maryland in a file named `LICENSES`, which
GitHub's detector does not recognise, so the API reports no licence at all.
That is the general lesson: **the API label is a guess, the file is the
licence**, and the failure direction is the dangerous one, since "no licence"
means all rights reserved and would have ruled out a repo that is in fact
permissive.

---

## Tier 1: worth real work

### astropy/astroquery, BSD-3-Clause

Maintained clients for three of the four upstreams `modules/catalog.py` hand
rolls with `requests`.

| file | what it covers | relevance here |
|---|---|---|
| `astroquery/ipac/irsa/core.py` | IRSA TAP, `query_tap(adql, async_job=True)` | **direct replacement** for `fetch_neowise`'s sync TAP call |
| `astroquery/jplhorizons/core.py` | Horizons `ephemerides` / `elements` / `vectors` | real state vectors for launch-window validation |
| `astroquery/jplsbdb/core.py` | SBDB, one object per call | **not** a replacement for the bulk `sbdb_query.api` fetch |
| `astroquery/mpc/core.py` | MPC orbits and observations | a fifth source, if wanted |

Two things matter:

- ✅ **`Irsa.query_tap(..., async_job=True)` is the fix for the NEOWISE
  outage.** CLAUDE.md records IRSA returning `502 Proxy Error` all evening and
  contributing 0 rows to the committed cislunar 2x2. `_NEOWISE_TAP_URL` is
  posted **synchronously**, so a slow or proxied query dies as a 502. Async TAP
  submits a job, polls, and collects, which is what the IRSA service is built
  for at this row count. This is a small, self-contained change to one fetcher.
- ⚠️  **`jplsbdb` will not replace `fetch_jpl_sbdb`.** Its `query_async` takes a
  single `targetid`; the pipeline uses the bulk `sbdb_query.api`, which
  astroquery does not wrap. Keep the hand-rolled bulk fetcher.

`Horizons.vectors()` is one HTTP call per body, so it cannot run over 1.55 M
rows. Its use here is as a **validation oracle** on a few hundred sampled
bodies, which is exactly what F1 needs and nothing more.

### juliensimon/space-datasets, MIT (pipeline code; data per source)

The highest information-per-byte star in the set. Someone else solving the same
four-source small-body ingestion problem, and publishing frozen Parquet.

| file | why it matters |
|---|---|
| `scripts/update-sdss-taxonomy.py` | **the PDS3 fixed-width column specs for the SDSS taxonomy archive.** This is where F2's data came from |
| `scripts/update-sbdb.py` | a second implementation of the bulk SBDB fetch, worth diffing against `fetch_jpl_sbdb` |
| `scripts/update-neowise.py` | ditto for NEOWISE |
| `LICENSE_AUDIT.md` | a per-dataset licence audit, which this repo does not have and arguably needs |

The datasets are on HuggingFace as Parquet with no API keys. That is directly
relevant to CLAUDE.md's "THE INPUTS ARE NOT IN GIT, AND THAT IS WHAT STOPS A
SECOND HOST FIRST": a frozen, versioned, redistributable mirror is a better
answer for the Spark host than copying 868 MB by hand.

⚠️  It does **not** solve the reproducibility problem on its own. Those
datasets auto-update on a schedule, so pinning a revision is mandatory if they
are ever used as a campaign input.

### skyfielders/python-skyfield, MIT

The only pure-Python, permissively licensed way to turn the six elements this
catalog already carries into real positions.

| file | what to take |
|---|---|
| `skyfield/keplerlib.py` | `ele_to_vec(p, e, i, Om, w, v, mu)`, `eccentric_anomaly(e, M)`, `propagate()` |
| `skyfield/data/mpc.py` | `load_mpcorb_dataframe`, `mpcorb_orbit(row, ts, gm)`, vectorised over a DataFrame |
| `skyfield/constants.py` | GM values, AU, day lengths |

`ele_to_vec` is about 50 lines and is the piece F1 needs to place the plane
change at the line of nodes instead of splitting it blindly. It can be
reimplemented in numpy against the repo's existing six columns without adding a
dependency, which suits a project with six.

### pymc-devs/pymc, Apache-2.0

Earned its place by F2 and not before it. The composition of 90.2% of NEOs is
guessed from albedo, and where a second opinion exists the two surveys disagree
on composition group 33.9% of the time. That is a distribution the model
currently reports as a scalar.

The shape of the model is small: a categorical prior over `spectral_type`
conditioned on albedo and orbital class, calibrated on the 44,061 bodies with
two independent classifications, propagated through `TAXONOMY_COMPOSITION` into
`comp_*` and out to the objective.

⚠️  **Do not put PyMC in `_MASTER_REQUIRED`.** This belongs in an offline
uncertainty harness beside `verify.py`, not in the pipeline. A sampler in the
hot path would destroy the bit-identity every release here is argued from.

### Z3Prover/z3, MIT

The only star that speaks to CLAUDE.md's one open structural item, and it
speaks to the hard half of it.

> "Branch-and-bound on the objective ... needs an **admissible** upper bound on
> `selection_key` ... a bound that is occasionally too tight silently drops
> winners, and it drops them **without changing the row count**, which is the
> one failure mode none of `verify.py`'s six checks would catch."

Z3's `nlsat` is a complete decision procedure for polynomial real arithmetic,
so a candidate bound can be **proved** admissible over a bounded domain rather
than spot-checked. The trick that makes the mass cascade tractable for it:
`math.exp(dv/ve)` is transcendental and outside NRA, but substituting
`R = exp(dv/ve)` as a free real with `R >= 1` makes the whole cascade
polynomial in R. Prove the bound for all valid R and the transcendental never
enters.

⚠️  Offline proof tool, not a runtime dependency. And it proves a bound is
admissible; it does not find one for you.

---

## Tier 2: worth one specific narrow thing

| repo | licence | the one thing | verdict |
|---|---|---|---|
| **nyx-space/nyx** | **AGPL-3.0** | `nyx-core/src/tools/lambert/{godding,izzo}.rs`, two production Lambert solvers, plus `tests/GMAT_scripts/` as a validation corpus against GMAT | 🚨 **read, do not copy.** AGPL. Reimplement Gooding or Izzo from the published papers, or use pykep |
| **typpo/spacekit** | MIT | `src/KeplerParticles.ts` uploads a, e, i, Ω, ω, M as GPU vertex attributes and solves Kepler **in the vertex shader** | the right technique for drawing 1.55 M bodies in `ui.py`. Genuinely applicable, and the only visualisation star that is |
| **Small-Bodies-Node/pds4_tools** | **BSD-3 (Univ. of Maryland)** | `pds4_read` for PDS4 archives | ⚠️ **it does not read the SDSS table.** That archive is PDS**3**; this library is PDS4 only. F2's loader is 20 lines of `read_fwf` and needs nothing. Useful only if a PDS4 small-body archive is ever wanted |
| **esa/pygmo2** | MPL-2.0 | 26 global optimisers, all stochastic or local | ⚠️ **wrong tool for the search.** None gives an admissible bound, so none can replace the exhaustive ladder without losing the never-worse invariant. Its real use is **calibration**: finding which `IN_SPACE_UTILITY_BY_DESTINATION` vector flips a destination, i.e. sensitivity on the softest assumption in the pipeline |
| **Pyomo/pyomo** | BSD-3 | algebraic MINLP modelling | ⚠️ expressing an 8,200-line simulation as an algebraic model is a rewrite, not an adoption. Worth it only if the programme-scale search is ever re-posed as a formal MINLP |

**esa/pykep is the star you are missing.** MPL-2.0, from the same ESA group as
pygmo, and it is the one that carries the interplanetary content pygmo does not:
`lambert_problem`, `udpla/keplerian` (a planet defined by orbital elements,
which is exactly what an asteroid is here), and `leg_sims_flanagan`, the
standard low-thrust leg model. That last one bears directly on
`dv_penalty_factor`, which is currently a scalar fudge standing in for the fact
that "the rocket equation ignores thrust; trajectories don't". Sims-Flanagan on
a few hundred sampled bodies would let that fudge be **calibrated** rather than
asserted.

---

## Tier 3: thin for this project, and why

| repo | licence | verdict |
|---|---|---|
| **pola-rs/polars** | MIT | 🚨 **the bit-identity trap applies.** CLAUDE.md already measured `pd.read_csv(engine="pyarrow")` at 4.8x and **rejected** it because its float parser rounds differently in the last ULP, moving `estimated_mass_kg` by 1e-13 relative. Polars has its own Rust CSV parser and lands in the same place. The 862 MB load is real cost and Parquet was already measured at 19.7 s to 2.1 s and declined for contract reasons, so polars is buying a saving the repo has already decided it does not want at that price |
| **cuspaceflight/CamPyRoS** | **GPL-3.0** | ⚠️ **weakest physics match in the set.** `campyros/heating.py` is 1,776 lines of real aerothermodynamics, but it is **ascent regime**: Prandtl-Meyer, oblique shocks, ideal-gas air. No Sutton-Graves, no Tauber-Sutton. Aerocapture from an asteroid return arrives at 8 to 12 km/s where dissociation and ionisation dominate and ideal-gas correlations are simply wrong. Using it for TPS sizing would be worse than the current mass fraction. Also GPL |
| **CelestiaProject/Celestia** | GPL-2.0 | the repo ships the renderer, not the catalogs. Only `test/data/nearstars.stc`. The asteroid `.ssc` data lives in separate content repos. Little here, and GPL |
| **julie-dujardin/space-map** | **AGPL-3.0** | 🚨 **this row was wrong; see [SPACE-MAP.md](SPACE-MAP.md).** Audited properly it is the most valuable star of the seventeen: its SBDB mirror discovers the field list via `?info=field` instead of hardcoding it, which is how `condition_code` was found missing. The code stays unusable (AGPL); the API knowledge does not carry a licence |
| **duncaneddy/brahe** | MIT | good library, wrong domain: Earth-orbit operations, ground stations, EOP, TLEs, space weather. Nothing heliocentric. `brahe/constants.py` is the only file worth a look |
| **mesa/mesa** | Apache-2.0 | agent-based modelling. The honest hook is that `saturation_price_multiplier` is a static elasticity with a single seller, and the `earth_surface` cells show it going numerically inert (multiplier 1.0 to within 2.3e-11, 100% of rows at the fleet ceiling). Multiple competing miners is a real question. But it is a **different model**, not an improvement to this one, and this repo's whole discipline is bit-identity, which an agent simulation does not have |
| **OpenSCvx/OpenSCvx** | Apache-2.0 | successive convexification on a JAX backend, with `examples/abstract/impulsive.py`. Permissively licensed and genuinely capable, but the examples are robotics and aircraft; there is no orbital transfer example, and JAX is a heavy dependency for a project with six. pykep's Sims-Flanagan gets to the same place with less |

---

## Files pulled during this pass

Working copies are in the session scratchpad, not committed, since most are
large or copyleft. Everything is re-fetchable with the commands below.

```bash
# astroquery small-body clients
curl -sL https://raw.githubusercontent.com/astropy/astroquery/HEAD/astroquery/ipac/irsa/core.py
curl -sL https://raw.githubusercontent.com/astropy/astroquery/HEAD/astroquery/jplhorizons/core.py

# skyfield element handling
curl -sL https://raw.githubusercontent.com/skyfielders/python-skyfield/HEAD/skyfield/keplerlib.py
curl -sL https://raw.githubusercontent.com/skyfielders/python-skyfield/HEAD/skyfield/data/mpc.py

# space-datasets: the SDSS PDS3 column specs
curl -sL https://raw.githubusercontent.com/juliensimon/space-datasets/HEAD/scripts/update-sdss-taxonomy.py

# spacekit GPU Kepler propagation
curl -sL https://raw.githubusercontent.com/typpo/spacekit/HEAD/src/KeplerParticles.ts

# the SDSS taxonomy archive itself (7.5 MB, static, no key)
curl -sL https://sbnarchive.psi.edu/pds3/non_mission/EAR_A_I0035_5_SDSSTAX_V1_1/data/sdsstax_ast_table.tab
```

⚠️  Every URL above is a **fetch**, and none of them touches
`asteroid_pipeline/`. None is a Stage 1, 2 or 3 run, so none invalidates a
`.verify` baseline. That distinction is the one CLAUDE.md spends a whole
section on and it is worth restating: reading somebody's source is free,
re-running a stage is not.
