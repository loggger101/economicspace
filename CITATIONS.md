# Citations, sources and attribution

Where every number, dataset and borrowed line of code in this pipeline came
from, and what each one obliges you to do.

## What this file is, and what it is not

🚨  **It is the authority for REFERENCES, not for VALUES.** This project's
standing rule is that two copies of one measurement is a bug, so this file does
**not** restate what any source says. A propellant density, a vehicle price or
a Delta-v figure is cited inline, in the `notes` field of the row that carries
it (in [spacecost](https://github.com/loggger101/spacecost) for Stage 3's
tables, in `modules/*.py` for the rest), and that row stays the authority for
the number. What lives here is the bibliographic reference, the licence, and the
attribution obligation.

| you want | read |
|---|---|
| which number came from where | the `notes` field on the row: spacecost's tables, or `modules/*.py` |
| how to cite a source, or what it obliges | **this file** |
| what the pipeline currently answers | [`README.md`](README.md) |
| what the model does with a number | [`MODEL.md`](MODEL.md) |
| what a number used to be | [`versions.md`](versions.md) |

⚠️  **Two sources ask to be cited and it is a condition of use, not a
courtesy.** They are marked 🔔 below. If any figure derived from this pipeline
is published, those citations travel with it.

---

## 1. Upstream data sources

The four asteroid surveys reach this pipeline inside a published
[AsteroidCatalog](https://github.com/loggger101/AsteroidCatalog) release,
which Stage 1 installs; nothing here fetches them. Their endpoints, table names
and fetch details are in that repository's `CITATIONS.md`, which is the
authority for them and is not restated here. What stays here is what a figure
from THIS pipeline owes them. The commodity prices below are fetched by
Stages 2 and 3 at run time. None is vendored.

### 🔔 IMCCE SsODNet / ssoBFT

Best-of-literature compilation: diameter, albedo, mass, density, rotation and
taxonomy, and since catalog data contract 1.4.0 the first source for mass.

> Berthier, J., Carry, B., Vachier, F., et al. (2023). *Astronomy &
> Astrophysics.* SsODNet: Solar system Open Database Network.

**The service asks explicitly**: "For any use of the table, we ask the citation
of the article: Berthier et al., 2023." It further asks that, where possible,
the bibliographic references of the underlying articles be published too, since
ssoBFT is a compilation of other people's measurements.

### 🔔 NEOWISE Diameters and Albedos V2.0

Infrared diameters and albedos for ~150,000 asteroids.

> Mainzer, A., Bauer, J., Cutri, R., Grav, T., Kramer, E., Masiero, J.,
> Sonnett, S., and Wright, E., Eds. (2019). *NEOWISE Diameters and Albedos
> V2.0*, urn:nasa:pds:neowise_diameters_albedos::2.0. NASA Planetary Data
> System. https://doi.org/10.26033/18S3-2Z54

### NASA JPL Small-Body Database (SBDB)

The orbital and physical backbone: designations, elements, H, diameter, albedo,
taxonomy, the element epoch and the orbit-quality fields.

⚠️  `condition_code` is the **MPC orbit uncertainty parameter U**, and its
definition belongs to the Minor Planet Center rather than to JPL. It runs 0
(well determined) to 9 (barely constrained), and what it means for this
pipeline's ranking is in
[starred-repos' `SPACE-MAP.md`](https://github.com/loggger101/starred-repos/blob/main/SPACE-MAP.md).

### MP3C (Observatoire de la Cote d'Azur)

Physical-properties compilation, used as a supplement. MP3C asks to be
acknowledged by name rather than through a single paper
(`https://mp3c.oca.eu/citations/`).

### Commodity prices

- **yfinance** (Yahoo Finance): live futures for the metals that trade as
  futures contracts.
- **USGS Mineral Commodity Summaries** and **LME reference prices**: the
  curated fallback table for metals yfinance does not expose. Cited per row in
  `modules/mineral_value.py`.
- **metals.dev**: optional, off by default. The key defaults to `"DEMO"`, which
  skips the fetcher.
- **U.S. Geological Survey, *Mineral Commodity Summaries 2025*** (published
  2025-01-31): the order of the 2024 prices and world production behind the
  rows mineral_value 1.11.0 added (sulfur, chromium, titanium, gallium,
  germanium, rhenium, tungsten, molybdenum, ammonia). Approximate, and dated
  to the publication rather than to a quote. Phosphorus and CO2 are trade
  prices USGS does not carry; their rows say so.
- **U.S. Geological Survey, *Mineral Commodity Summaries 2026***: the iron row
  (No. 1 heavy melting steel scrap composite, 2025 average), the tungsten note
  (Rotterdam APT during 2025) and cobalt's world mine production (mineral_value
  1.12.3 and 1.13.0); the comments beside the carbonates price (crushed stone,
  average unit value 2025e) and iron's world pig-iron production
  (General_Research rc-144, rc-154).
- **World Bank, *Commodity Markets (Pink Sheet)* monthly prices**: the nickel
  and copper reference prices, May 2026 averages (mineral_value 1.13.0).
- **LBMA precious-metal prices**: the silver and platinum reference prices,
  the fixings on 2026-05-29 (mineral_value 1.13.0).
- **Johnson Matthey, *PGM Market Report* (May 2026)**: the iridium and
  ruthenium reference prices, its Q1-2026 base prices (mineral_value 1.13.0).
  JM's terms reserve its price data, so the row quotes the figure and the
  report, and this repository carries no copy.

### In-space demand

- **McDowell, J., *Space Activities in 2025*** (General Catalog of Artificial
  Space Objects, Rev 1.2), Table 22: the count of active geostationary
  payloads behind the `geo` absorption ceiling (mineral_value 1.13.0).
- **Kornuta et al. 2019**, *Commercial Lunar Propellant Architecture* (REACH
  13:100026), and **Northrop Grumman 2024**, *DARPA LunA-10 Lunar Rail Network
  study*: lunar propellant demand forecasts recorded beside the cislunar and
  lunar-surface ceilings as anchors, not used as values (master v1.45.0).

### Mineral composition

- **The mineral phases** in each taxonomy class (catalog data contract 1.7.0)
  come from AsteroidCatalog's `asteroid_catalog/mineralogy.py`, which cites a
  meteorite analogue per class (Dunn et al. 2010; King et al. 2015; Howard et
  al. 2015; Alexander et al. 2007; Mittlefehldt 2015; Sunshine et al. 2008;
  Rubin et al. 2019; Hiroi et al. 2001). That repository is the authority for
  them and is not restated here.
- **The trace metals of meteoritic Fe-Ni** in the `nickel-iron` yields (Cu,
  Ga, Ge, Mo, W, Re) are order-of-magnitude means over the common iron
  meteorite groups: Scott, E. R. D. & Wasson, J. T. (1975), *Classification
  and properties of iron meteorites*, Rev. Geophys. Space Phys. 13, 527.

### Assumptions named rather than modelled

Cited in MODEL.md's [What the model does not capture](MODEL.md#what-the-model-does-not-capture)
to say what a held-fixed assumption ignores; neither reaches a value.

- **Terzi, F. & Nicoli, F. (2026)**, *From Sputnik to Starship: Estimating the
  experience curve of space launch technology*, PNAS Nexus,
  doi:10.1093/pnasnexus/pgag217: the launch-cost experience curve beside the
  flat launch prices (General_Research rc-025).
- **Metzger, P. T., Zacny, K. & Morrison, P. (2020)**, *Thermal Extraction of
  Volatiles from Lunar and Asteroid Regolith in Axisymmetric Crank-Nicolson
  Modeling*, J. Aerospace Engineering, doi:10.1061/(ASCE)AS.1943-5525.0001165:
  the drill's cool-down time the dig clock does not carry (General_Research
  rc-029).

⚠️  Prices are fetched live, so a figure derived from this pipeline is a
figure **on a date**. `catalog_date` is stamped into every output CSV for
exactly this reason; quote it.

### Facts the comments state

Cited in code comments, or in MODEL.md, beside a value they explain; none
reaches a value. The rc- numbers are General_Research revision candidates.

- **NASA Office of Inspector General (2023)**, *NASA's Management of Its
  Radioisotope Power Systems Program*, IG-23-010,
  <https://oig.nasa.gov/docs/IG-23-010.pdf>: DOE's Pu-238 production goal and
  its shortfall (p27) and an MMRTG's fuel load (Table 1, p13), the reasons
  calc gives for `rtg_max_power_w` (General_Research rc-120).
- **NASA NSSDCA, *Mars Fact Sheet***,
  <https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html>: the CO2 and
  N2 fractions and surface pressure behind `mars_surface`'s utility comments in
  mineral_value (General_Research rc-165).
- **Kabemba, Mutombo & Waters (2025)**, *A Predictive Geometallurgical
  Framework for Flotation Kinetics in Complex Platinum Group Metal Orebodies*,
  Minerals 15:701, doi:10.3390/min15070701; and **Liddell, Adams, Smith &
  Muller (2019)**, *Kell hydrometallurgical extraction of precious and base
  metals from flotation concentrates*, J. SAIMM: terrestrial flotation recovery
  and refinery extraction beside `beneficiation_recovery` (rc-122).
- **Bogmans, Pescatori, Petrella, Prifti & Stuermer (2024)**, *The Power of
  Prices: How Fast Do Commodity Markets Adjust to Shocks?*, IMF Working Paper
  2024/077, doi:10.5089/9798400271953.001.A001: measured metal demand
  elasticities beside `demand_elasticity` (rc-123).
- **Whitley, S. & Shinn, S. (2012)**, *The Economics of NASA Mission Cost
  Reserves*, IEEE Aerospace Conference, NTRS 20120002314; and **National
  Research Council (2010)**, *Controlling Cost Growth of NASA Earth and Space
  Science Missions*: reserve consumption and cost growth beside
  `contingency_fraction` (rc-124).
- **Chen, G. & McLennan, D. D. (2004)**, *A Study of Learning Curve Impact on
  Three Identical Small Spacecraft*, NTRS 20040035806: the one measured
  spacecraft learning case beside `learning_curve_rate` (rc-127).
- **Sowers, G. (2020)**, *Thermal Mining of Ices on Cold Solar System Bodies*,
  NIAC Phase I final report; **Schuler, Nick, Leucht, Langton & Smith (2022)**,
  *ISRU Pilot Excavator: Bucket Drum Scaling Experimental Results*, ASCE Earth
  and Space; and **Giel et al. (2025)**, *Design and Development of a Modular
  Bucket Drum Excavator for Lunar ISRU*, arXiv:2511.00492: plant and tool
  throughputs beside `mining_rate_kg_per_day_per_kg_rig` (rc-136).
- **NASA Office of Inspector General (2018)**, *Audit of Commercial Resupply
  Services to the International Space Station*, IG-18-016; and **Motiwala,
  Mathias & Mattenberger (2014)**, *Conceptual Launch Vehicle and Spacecraft
  Design for Risk Assessment*, NTRS 20150000182: cargo-vehicle upmass and
  stage structural fractions beside `return_structure_frac_of_payload`
  (rc-137).
- **Sjauw, McGuire & Freeh (2016)**, *Mission Design Considerations for Mars
  Cargo of the Human Spaceflight Architecture Team's Evolvable Mars Campaign*,
  AIAA, NTRS 20160010261: a solar-electric cargo stage's Earth-Mars trip time
  beside `ep_target_thrust_yr` (rc-138).
- **Northrop Grumman (2016)**, *Propulsion Products Catalog* (OSR No.
  16-S-1432), STAR 48B pages: the motor-case fraction MODEL.md's tankage table
  holds the APCP class against (rc-179).

---

### Sources read only by the research probes

Not pipeline inputs, and not cited here: no stage fetches them and none of
them reaches a CSV. They are the external oracles (JPL NHATS and Horizons,
NEODyS, Asterank, the Bus-DeMeo taxonomy) that
[starred-repos' `SECOND-PASS.md`](https://github.com/loggger101/starred-repos/blob/main/SECOND-PASS.md)
measures the model against, and section 1 of
[that repo's `CITATIONS.md`](https://github.com/loggger101/starred-repos/blob/main/CITATIONS.md)
cites them beside the probes that read them.

---

## 2. Data committed to this repository

None. The one dataset that was, the SDSS-based Asteroid Taxonomy V1.1 table
(`sdsstax_ast.tab`, read only by a research probe), moved with the probes to
[starred-repos](https://github.com/loggger101/starred-repos) on 2026-10-20,
and its citation, a condition of use, is section 2 of
[that repo's `CITATIONS.md`](https://github.com/loggger101/starred-repos/blob/main/CITATIONS.md).

---

## 3. Code adapted from other projects

### skyfield, MIT

`orbital.py`'s one function, `elements_to_state`, is adapted from
`skyfield/keplerlib.py`.

```
Copyright (c) 2013-2018 Brandon Rhodes
MIT License
```

What changed: `elements_to_state` is `ele_to_vec` restricted to the elliptical case and re-expressed in terms of the semi-major
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

The Izzo (2015) Lambert solver and the Kepler starter of arXiv:2108.03215 are
not in this repository: they live in starred-repos' `orbital.py`, with
`probe_lambert.py`, their one caller, and section 4 of
[that repo's `CITATIONS.md`](https://github.com/loggger101/starred-repos/blob/main/CITATIONS.md)
cites them.

### Textbook relations the verification worksheet cites

`campaign/verification_sheet.py`'s backing part names the source of a step
whose relation is a textbook one (its `RELATIONS` register). Every other step
is the model's own arithmetic on cited inputs, and nothing here covers it.

> Sutton, G. P. and Biblarz, O. (2017). *Rocket Propulsion Elements*, 9th
> ed. Wiley. The rocket equation, exhaust velocity, thrust and jet power.

> Vallado, D. A. (2013). *Fundamentals of Astrodynamics and Applications*,
> 4th ed. Microcosm Press. Vis-viva, circular and escape speed, the combined
> plane change, Kepler's third law and the synodic period.

> Fowler, J. W. and Chillemi, J. R. (1992). IRAS asteroid data processing.
> In Tedesco, E. F. et al., *The IRAS Minor Planet Survey*, Phillips
> Laboratory technical report PL-TR-92-2049. Diameter from absolute
> magnitude and albedo.

> Wright, T. P. (1936). Factors affecting the cost of airplanes. *Journal of
> the Aeronautical Sciences* 3(4), 122-128. The learning curve: each doubling
> of units built costs a fixed fraction of the last.

Three of the derivation's own constants (`campaign/worked_calculation.py`)
are cited on the worksheet to the documents below; each agrees with the
constant to the figures it publishes.

> Petit, G. and Luzum, B. (eds.) (2010). *IERS Conventions (2010)*, IERS
> Technical Note 36, Table 1.1. Earth's gravitational parameter, `MU_EARTH`.

> NASA NSSDCA, *Earth Fact Sheet* and *Moon Fact Sheet*,
> <https://nssdc.gsfc.nasa.gov/planetary/factsheet/>. Earth's mean orbital
> velocity, `V_EARTH`; Earth's semi-major axis, the 1 au every Earth-system
> destination's launch windows are phased against (`window_phasing_au` in
> calc's `DELIVERY_ARCHITECTURES`); and the Moon's semi-major axis, `R_MOON`.

`DV_NRHO` is not cited here: it restates spacecost's delta-v row
`TLI → NRHO insertion`, whose notes carry its source, and the worksheet quotes
that row.

---

## 5. Repositories audited, and what was taken from each

The survey of 17 repositories, and the licence position for every one of them,
is section 5 of
[starred-repos' `CITATIONS.md`](https://github.com/loggger101/starred-repos/blob/main/CITATIONS.md).
What reached this repository from them is one thing: skyfield's code, adapted
into `orbital.py` and credited in section 3. typpo/spacekit's per-body Kepler
solve is the technique behind `ui.py`'s orbit diagram, but no line of it was
read into this repository.

🚨  **Nothing here is derived from any of the four copyleft projects** the
survey read (julie-dujardin/space-map and nyx-space/nyx, AGPL-3.0;
cuspaceflight/CamPyRoS, GPL-3.0; CelestiaProject/Celestia, GPL-2.0).

---

## 6. Software this pipeline depends on

⚠️  **spacecost** is this project's own, extracted from Stage 3 and MIT licensed; it is pinned to tag `v0.12.0` and carries every launch, propellant, Delta-v, operational and storage row, with the citations for them, and since `v0.3.0` the delivery chains Stage 2 prices through.

⚠️  **asteroid_catalog** is this project's own too, extracted from Stage 1 and
MIT licensed. It carries the four survey fetchers, the cross-match, the
H-derivation and the Bus-DeMeo composition table, and it is not installed
here: Stage 1 downloads one of its published catalog releases (data, not
code), pinned by `CatalogConfig.catalog_release`. **The upstream citations
travel with it**: its own `CITATIONS.md` carries every survey's endpoint and
citation in full, each release's notes repeat them, and section 1 above is
this repository's statement of what it owes them.

Runtime, from `requirements.txt`: **requests**, **pandas**, **numpy**,
**yfinance**, **tqdm**, and **spacecost**. Dashboard, from `requirements-ui.txt`:
**streamlit**. Campaign tooling: **quietqueue**, from `requirements-campaign.txt`,
and **psutil**, from `requirements-lock.txt` only.
Exact pins are in `requirements-lock.txt`; do not
restate them here.

---

## 7. Where citations live in the code

This file does not duplicate them. It says where they are.

| what | where its sources are cited |
|---|---|
| launch vehicles, propellants, storage systems, Delta-v segments, operational costs | the `notes` field of each row in the [`spacecost`](https://github.com/loggger101/spacecost) package, with `reference_year` tagging staleness. They left `modules/transportation.py` at master v1.25.0; that repo's `CITATIONS.md` is their bibliography now |
| commodity prices and market depths | per-commodity in `modules/mineral_value.py` |
| taxonomy to composition | `TAXONOMY_COMPOSITION` in `asteroid_catalog/taxonomy.py`; Stage 1 installs the copy each catalog release was built with, as `catalog_taxonomy.json` |
| the delivery LEG CHAINS and the downleg (tug and lander dry-mass fractions, the Mars entry survival fraction) | `spacecost/delivery.py`, since master v1.30.0; `modules/mineral_value.py` re-exports them and cites nothing itself |
| delivery architectures and utility factors | `modules/mineral_value.py` and `modules/calc.py`; these are **engineering judgements**, not measurements, and MODEL.md says so |

⚠️  **The utility factors are the softest assumption in the pipeline** and have
no citation because there is nothing to cite. They are a dial (MODEL.md,
[What a kilogram is worth](MODEL.md#what-a-kilogram-is-worth)); this note is
here so that nobody reads the gap in this file as an oversight.

---

## 8. Citing this pipeline

There is no published paper. The code is MIT ([`LICENSE`](LICENSE)); the
data it fetches and the code adapted into it are licensed as sections 1 to 3
say.

If a result from it is quoted, the reproducible identifiers are the
`pipeline_version` and `catalog_date` stamped into every output CSV, plus the
git commit. A number without those is not reproducible, which is the point
[`versions.md`](versions.md) exists to make.
