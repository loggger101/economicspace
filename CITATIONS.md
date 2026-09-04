# Citations, sources and attribution

Where every number, dataset and borrowed line of code in this pipeline came
from, and what each one obliges you to do.

## What this file is, and what it is not

🚨  **It is the authority for REFERENCES, not for VALUES.** This project's
standing rule is that two copies of one measurement is a bug, so this file does
**not** restate what any source says. A propellant density, a vehicle price or
a Delta-v figure is cited inline, in the `notes` field of the row that carries
it in `modules/transportation.py`, and that row stays the authority for the
number. What lives here is the bibliographic reference, the licence, and the
attribution obligation.

| you want | read |
|---|---|
| which number came from where | the `notes` field on the row, in `modules/*.py` |
| how to cite a source, or what it obliges | **this file** |
| what the pipeline currently answers | [`README.md`](README.md) |
| what a number used to be | [`versions.md`](versions.md) |

⚠️  **Two sources ask to be cited and it is a condition of use, not a
courtesy.** They are marked 🔔 below. If any figure derived from this pipeline
is published, those citations travel with it.

---

## 1. Upstream data sources

Fetched at run time by Stages 1 to 3. None is vendored.

### 🔔 IMCCE SsODNet / ssoBFT

Best-of-literature compilation: diameter, albedo, mass, density, rotation and
taxonomy. Fetched as a bulk parquet by `fetch_ssodnet` in `modules/catalog.py`.

> Berthier, J., Carry, B., Vachier, F., et al. (2023). *Astronomy &
> Astrophysics.* SsODNet: Solar system Open Database Network.

**The service asks explicitly**: "For any use of the table, we ask the citation
of the article: Berthier et al., 2023." It further asks that, where possible,
the bibliographic references of the underlying articles be published too, since
ssoBFT is a compilation of other people's measurements.

- API: `https://ssp.imcce.fr/webservices/ssodnet/api/ssobft`
- Bulk file: `https://ssp.imcce.fr/data/ssoBFT-latest_Asteroid.parquet`

### 🔔 NEOWISE Diameters and Albedos V2.0

Infrared diameters and albedos for ~150,000 asteroids. Fetched over IPAC IRSA's
TAP service by `fetch_neowise`.

> Mainzer, A., Bauer, J., Cutri, R., Grav, T., Kramer, E., Masiero, J.,
> Sonnett, S., and Wright, E., Eds. (2019). *NEOWISE Diameters and Albedos
> V2.0*, urn:nasa:pds:neowise_diameters_albedos::2.0. NASA Planetary Data
> System. https://doi.org/10.26033/18S3-2Z54

- TAP endpoint: `https://irsa.ipac.caltech.edu/TAP` (table `neowisesbpropv2`)
- Dataset landing page: `https://sbn.psi.edu/pds/resource/doi/neowise_2.0.html`

### NASA JPL Small-Body Database (SBDB)

The orbital and physical backbone: designations, elements, H, diameter, albedo,
taxonomy and, since catalog `1.2.0`, the element epoch and orbit-quality
fields.

- Query API: `https://ssd-api.jpl.nasa.gov/sbdb_query.api`
- Field discovery: `https://ssd-api.jpl.nasa.gov/sbdb_query.api?info=field`

⚠️  `condition_code` is the **MPC orbit uncertainty parameter U**, and its
definition belongs to the Minor Planet Center rather than to JPL. It runs 0
(well determined) to 9 (barely constrained), and what it means for this
pipeline's ranking is in
[`research/starred-repos/SPACE-MAP.md`](research/starred-repos/SPACE-MAP.md).

### MP3C (Observatoire de la Cote d'Azur)

Physical-properties compilation, used as a supplement.

- `https://mp3c.oca.eu/` (REST and TAP interfaces; both are tried)

### Commodity prices

- **yfinance** (Yahoo Finance): live futures for the metals that trade as
  futures contracts.
- **USGS Mineral Commodity Summaries** and **LME reference prices**: the
  curated fallback table for metals yfinance does not expose. Cited per row in
  `modules/mineral_value.py`.
- **metals.dev**: optional, off by default. The key defaults to `"DEMO"`, which
  skips the fetcher.

⚠️  Prices are fetched live, so a figure derived from this pipeline is a
figure **on a date**. `catalog_date` is stamped into every output CSV for
exactly this reason; quote it.

---

### Sources read only by the research probes

Not pipeline inputs. Nothing below is fetched by any stage, and none of it
reaches a CSV; they are the external oracles
[`research/starred-repos/SECOND-PASS.md`](research/starred-repos/SECOND-PASS.md)
measures the model against.

- **NASA JPL NHATS**, `https://ssd-api.jpl.nasa.gov/nhats.api`. Optimised
  round-trip delta-v and mission duration for the near-Earth asteroids
  accessible to human spaceflight. Read by
  `research/starred-repos/probe_nhats.py`.
- **NASA JPL Horizons**, `https://ssd-api.jpl.nasa.gov/horizons.api`, and the
  **NAIF** kernel archive. Recommended in F7 for bounding the two-body error in
  F4's Lambert oracle; not yet used.
- **NEODyS** (University of Pisa and SpaceDyS),
  `https://newton.spacedys.com/neodys/`. Per-object orbital elements with the
  full 6x6 covariance. Recommended in F9; not yet used.
- **Asterank**, `http://www.asterank.com/api/asterank`, MIT. Used for its `dv`
  column only, which is the **Shoemaker-Helin** closed-form delta-v
  approximation. Its economic columns return degenerate values through the
  public endpoint and are not used.

  > Shoemaker, E. M. and Helin, E. F. (1978). *Earth-approaching asteroids as
  > targets for exploration.* NASA CP-2053, pp. 245-256.

- **Bus-DeMeo asteroid taxonomy**, PDS Small Bodies Node bundle
  `urn:nasa:pds:ast.bus-demeo.taxonomy`. Fetched and inspected in the second
  pass; not committed and not used by any stage.

  > DeMeo, F. E., Binzel, R. P., Slivan, S. M., and Bus, S. J. (2009). *An
  > extension of the Bus asteroid taxonomy into the near-infrared.* Icarus,
  > 202(1), 160-180.

---

## 2. Data committed to this repository

### 🔔 SDSS-based Asteroid Taxonomy V1.1

`research/starred-repos/sdsstax_ast.tab`, 7.5 MB, committed because it is
static and small. 63,468 numbered asteroids with an independent taxonomic
class from u'g'r'i'z' photometry.

Dataset, as the archive's own `CITATION_DESC` gives it:

> Hasselmann, P. H., Carvano, J. M., and Lazzaro, D., *SDSS-based Asteroid
> Taxonomy V1.1.* EAR-A-I0035-5-SDSSTAX-V1.1. NASA Planetary Data System,
> 2012.

The method paper, which is what a scientific claim should cite:

> Carvano, J. M., Hasselmann, P. H., Lazzaro, D., and Mothe-Diniz, T. (2010).
> *SDSS-based taxonomic classification and orbital distribution of main belt
> asteroids.* Astronomy & Astrophysics 510, A43.
> https://doi.org/10.1051/0004-6361/200913322

The underlying survey:

> Ivezic, Z. et al. (2001). *Solar System Objects Observed in the Sloan
> Digital Sky Survey Commissioning Data.* The Astronomical Journal 122, 2749.

- Archive: `https://sbnarchive.psi.edu/pds3/non_mission/EAR_A_I0035_5_SDSSTAX_V1_1/`

⚠️  **Cite the papers, not this repository**, for any published result that
rests on this table. NASA PDS data is in the public domain; the scientific
credit is not.

ℹ️  The column layout was transcribed from the archive's own `.lbl` files, by
way of `juliensimon/space-datasets` (MIT), which had already done the
transcription. See section 5.

---

## 3. Code adapted from other projects

### skyfield, MIT

`research/starred-repos/orbital.py`, the functions `kepler_E`, `true_anomaly`
and `elements_to_state`, are adapted from `skyfield/keplerlib.py`.

```
Copyright (c) 2013-2018 Brandon Rhodes
MIT License
```

What changed: `kepler_E` keeps skyfield's starter and quartic Newton step but
drops the scalar early return so it broadcasts over arrays, and clips `e` away
from 0 and 1 rather than raising. `elements_to_state` is `ele_to_vec`
restricted to the elliptical case and re-expressed in terms of the semi-major
axis rather than the semi-latus rectum, because that is the column this catalog
stores.

**Obligation: the copyright notice and the MIT permission notice must travel
with any distribution.** This section satisfies that.

- `https://github.com/skyfielders/python-skyfield`

---

## 4. Algorithms implemented from published papers

An algorithm described in a paper is not a copyrightable expression, so
implementing one from its equations carries no licence obligation. It carries a
citation obligation, which is what this section is.

### Lambert's problem

`lambert_izzo` and its helpers in `research/starred-repos/orbital.py` are
implemented from:

> Izzo, D. (2015). *Revisiting Lambert's problem.* Celestial Mechanics and
> Dynamical Astronomy 121(1), 1-15.

🚨  **Deliberately not copied from an implementation.** The two obvious ones to
have taken it from are **pykep** (MPL-2.0) and **nyx** (AGPL-3.0), and the
second would have made this pipeline AGPL. The paper route was chosen for that
reason.

Validated against a published worked example:

> Vallado, D. A. *Fundamentals of Astrodynamics and Applications*, Example 7-5.

Agreement is 7.4e-07 km/s, which is the precision the reference is quoted to.
See [`research/starred-repos/FINDINGS.md`](research/starred-repos/FINDINGS.md)
F4.

### Kepler's equation

The starter and quartic Newton iteration in `kepler_E` follow:

> arXiv:2108.03215

reached by way of skyfield's implementation, which is credited in section 3.

---

## 5. Repositories audited, and what was taken from each

A survey of 17 repositories is recorded in
[`research/starred-repos/`](research/starred-repos/). Most were read and
nothing was taken. This table is the licence position for all of them.

Read twice: the second pass is in
[`SECOND-PASS.md`](research/starred-repos/SECOND-PASS.md), and it moved rows
here, because a repository can add exactly the thing it was rejected for
lacking. The licence column is the part that does not go stale.

| repository | licence | what was taken |
|---|---|---|
| skyfielders/python-skyfield | MIT | **code**, adapted; see section 3 |
| juliensimon/space-datasets | MIT | **the PDS3 column layout** for the SDSS table (section 2), and the JPL NHATS endpoint used by `probe_nhats.py` |
| astropy/astroquery | BSD-3 | nothing. It showed that IRSA's async TAP was the right approach; the implementation here is written against `requests`. Its NEODyS client is where the covariance service was found |
| julie-dujardin/space-map | **AGPL-3.0** | nothing. It showed that SBDB publishes a field list, which is how `condition_code` was found missing |
| Z3Prover/z3 | MIT | nothing yet |
| Pyomo/pyomo | BSD-3 | nothing |
| pymc-devs/pymc | Apache-2.0 | nothing yet |
| mesa/mesa | Apache-2.0 | nothing |
| OpenSCvx/OpenSCvx | Apache-2.0 | nothing |
| esa/pygmo2 | MPL-2.0 | nothing |
| pola-rs/polars | MIT | nothing |
| typpo/spacekit | MIT | nothing |
| duncaneddy/brahe | MIT | nothing yet. Its native SPICE reader and Horizons SPK client are the recommended way to bound F4's oracle |
| Small-Bodies-Node/pds4_tools | BSD-3 (Univ. of Maryland) | nothing |
| nyx-space/nyx | **AGPL-3.0** | nothing |
| cuspaceflight/CamPyRoS | **GPL-3.0** | nothing |
| CelestiaProject/Celestia | **GPL-2.0** | nothing |

🚨  **Nothing is derived from any of the four copyleft projects.** They are
listed because they were read, and because listing them is the record that they
were read and not copied.

⚠️  **Read the licence file, not the API label.** `pds4_tools` reports as
having no licence on GitHub because its BSD-3 text sits in a file named
`LICENSES`, which the detector does not recognise. "No licence" means all
rights reserved, so that failure runs in the dangerous direction.

---

## 6. Software this pipeline depends on

Runtime, from `requirements.txt`: **requests**, **pandas**, **numpy**,
**yfinance**, **tqdm**, **pyarrow**. Dashboard, from `requirements-ui.txt`:
**streamlit**, **psutil**. Exact pins are in `requirements-lock.txt`; do not
restate them here.

---

## 7. Where citations live in the code

This file does not duplicate them. It says where they are.

| what | where its sources are cited |
|---|---|
| launch vehicles, propellants, storage systems, Delta-v segments, operational costs | the `notes` field of each row in `modules/transportation.py`, with `reference_year` tagging staleness |
| commodity prices and market depths | per-commodity in `modules/mineral_value.py` |
| taxonomy to composition | `TAXONOMY_COMPOSITION` in `modules/catalog.py` |
| delivery architectures and utility factors | `modules/mineral_value.py` and `modules/calc.py`; these are **engineering judgements**, not measurements, and README says so |

⚠️  **The utility factors are the softest assumption in the pipeline** and have
no citation because there is nothing to cite. They are a dial. README's "What a
kilogram is worth" says this, and it is repeated here so that nobody reads a
gap in this file as an oversight.

---

## 8. Citing this pipeline

There is no published paper, and **no LICENSE file**, so no licence is granted
by default: all rights are reserved until one is added. Anyone relying on this
should raise that first.

If a result from it is quoted, the reproducible identifiers are the
`pipeline_version` and `catalog_date` stamped into every output CSV, plus the
git commit. A number without those is not reproducible, which is the point
[`versions.md`](versions.md) exists to make.
