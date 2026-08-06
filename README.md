# economicspace — Asteroid Mining Profitability Pipeline

End-to-end pipeline that estimates, for every asteroid it can pull data on, the
net profit of an **uncrewed autonomous mining and sample-return mission**.

It chains four stages: build an asteroid catalog from public astronomy
databases → price the minerals those asteroids contain → cost the
transportation → run the rocket-equation and cost cascade to produce a ranked
profitability table.

## Layout

```
build_master.py        Build tool: assembles modules/ into master.py
master.py              GENERATED single-file pipeline — do not edit by hand
modules/
    catalog.py         Stage 1 — asteroid catalog
    mineral_value.py   Stage 2 — mineral prices + densities
    transportation.py  Stage 3 — launch / propellant / Δv / ops costs
    calc.py            Stage 4 — profitability calculation
```

Each module is a standalone file: run it directly to build just that stage, or
import it for its functions without triggering a run. They share no Python
imports — stages hand off through CSVs on disk, not through each other's
namespaces (see [Stage dependencies](#stage-dependencies)).

| Stage | Module | Version | What it does |
|-------|--------|---------|--------------|
| 1 | `modules/catalog.py` | 1.0.8 | JPL SBDB + MP3C + SsODNet ssoBFT + NEOWISE; merge, dedupe, validate, enrich with per-spectral-type PGM factors |
| 2 | `modules/mineral_value.py` | 1.2.0 | Live yfinance futures, USGS/LME reference prices, in-pipeline mineralogy, destination-priced water |
| 3 | `modules/transportation.py` | 1.3.0 | Launch vehicles, propellants, Δv segments, operational costs |
| 4 | `modules/calc.py` | 1.4.0 | Per-asteroid Δv, rocket-equation mass cascade + cost cascade → net profit, ROI, $/kg-returned |

## Running it

Python 3.9+ (developed and run on 3.13). Then:

```bash
pip install -r requirements.txt
```

Run the whole pipeline as one self-contained file:

```bash
python master.py
```

Or run a single stage:

```bash
python modules/transportation.py
```

`master.py` is also designed to be pasted straight into a Colab or Jupyter cell
— it auto-installs its own dependencies and runs top-to-bottom.

### Stage dependencies

Stages 1, 2 and 3 are independent of each other and can be run in any order or
alone. **Stage 4 is not** — `modules/calc.py` reads the CSVs the other three
wrote, so it needs a populated `output_dir` before it will do anything. Run the
full `master.py` at least once, or run stages 1–3 individually first.

### What a first run costs

- **Stage 1** dominates. At the default `jpl_limit = 50_000` it takes a couple
  of minutes and writes a ~30–40 MB CSV.
- SsODNet's ssoBFT table is a **~500 MB parquet bulk download** on first run.
  It is cached and re-used for `cache_max_age_days` (7 by default). The cache
  lives in the system temp directory, deliberately *not* under `output_dir` —
  on a Google Drive working copy that keeps half a gigabyte from re-syncing
  every run. Point `CATALOG_CONFIG.cache_dir` somewhere else if you want it
  co-located.
- **Stage 4** is fast since v1.3.7 — roughly 470 asteroids/s, so the default
  5,000-row cap finishes in ~10 s. Raising `eval_row_cap` scales linearly.
- Every source is failure-tolerant: an unreachable host returns empty and the
  run continues on what it did get. MP3C in particular is often DNS-blocked
  from Colab runtimes. You do not need to flip a source toggle just because a
  host is down.

### Output location

Defaults to `/content/asteroid_pipeline` on Colab and `./asteroid_pipeline`
everywhere else. Override with an environment variable:

```bash
ASTEROID_PIPELINE_OUTPUT_DIR=/path/to/output python master.py
```

or in code, via `MASTER_CONFIG.output_dir`.

### Tuning

`MASTER_CONFIG` sits near the bottom of `master.py` and exposes the four
module configs as `.catalog`, `.mineral`, `.transport` and `.calc`. The levers
that actually move the answer:

| Knob | Default | Effect |
|------|---------|--------|
| `MASTER_CONFIG.output_dir` | platform-dependent | Where everything lands |
| `.mineral.delivery_destination` | `"earth_surface"` | **Read [Where the material is sold](#where-the-material-is-sold) before changing.** Sets the water price, and water dominates C/B/D-type value |
| `.calc.use_per_asteroid_dv` | `True` | Δv from each asteroid's own orbital elements. `False` gives every asteroid the same Δv |
| `.calc.mining_rate_kg_per_day_per_kg_rig` | `0.10` | Extraction throughput per kg of rig; caps payload and sets time at the asteroid |
| `.calc.max_mining_duration_yr` | `3.0` | Ceiling on time at the asteroid — binds how much you can return |
| `.calc.nre_recurring_overlap_fraction` | `0.30` | Development share already inside the per-kg recurring rate; `0.0` books both in full |
| `.catalog.jpl_limit` | `50_000` | Catalog size; also caps every other source. JPL accepts ~250k |
| `.catalog.min_diameter_km` | `0.001` | Size floor. Raise to `1.0` to study km-class bodies only |
| `.catalog.require_spectral_type` | `False` | `True` drops untyped rows — fewer asteroids, but every one has a composition |
| `.catalog.use_jpl` / `use_mp3c` / `use_ssodnet` / `use_neowise` | all `True` | Per-source toggles. Turning off SsODNet skips the 500 MB download |
| `.calc.eval_row_cap` | `5_000` | Stage-4 evaluation cap; `0` evaluates every row |
| `.calc.max_mining_fraction` | `0.05` | Share of asteroid mass one mission may remove |
| `.calc.use_aerocapture_return` | `True` | Trades 4,000 m/s of return Δv for a TPS mass penalty (15% of payload) |
| `.calc.use_isru_return_propellant` | `False` | Return propellant made at the asteroid instead of hauled out |
| `.calc.nre_amortization_missions` | `1` | Spread ~$588M development NRE across a fleet |
| `.calc.contingency_fraction` | `0.20` | Flat contingency on the cost cascade |
| `.calc.apply_wacc_compounding` | `True` | Time-value of money, bucketed by when each cost is incurred |
| `.mineral.metals_api_key` | `"DEMO"` | Set a real metals.dev key to enable that source; `"DEMO"` silently skips |

The two toggles worth understanding together are `use_isru_return_propellant`
and `use_aerocapture_return`. With ISRU on *and* aerocapture off, nothing in
the rocket equation scales with returned payload, so the launch-mass
constraint goes slack. Stage 4 v1.3.6+ handles this by binding the return
capsule's **volume** limit instead — without it, a 30 km body "returns"
7.4e14 kg in a 500 kg capsule and tops the rankings with a fictional
$7.8e17 profit.

Importing `master.py` is side-effect free, so you can drive it yourself:

```python
import master
results = master.run_full_pipeline()
```

## Rebuilding master.py

`master.py` is **generated**. Edit the modules, then:

```bash
python build_master.py
```

The build strips each module's docstring, auto-install block, and
`RUN & PREVIEW` section, renames each `CONFIG` global to a unique name
(`CATALOG_CONFIG`, `MINERAL_CONFIG`, `TRANSPORT_CONFIG`, `CALC_CONFIG`),
resolves cross-module function-name collisions, then syntax-checks the result.
The build fails loudly rather than emitting a silently-wrong `master.py`.

Paths are resolved relative to `build_master.py`, so the repo works from any
location.

After writing `master.py` the build re-parses it and reports any top-level
name defined twice. Python silently lets the last definition win, so a
collision introduced by a module edit would otherwise land unnoticed and the
master would quietly run the wrong function — syntax-checking cannot see it.
A clean build ends with `names : no unexpected shadowed definitions`. If it
instead lists a name, either add a `word_replace()` rename in `build_master.py`
or, if the duplication is deliberate and identical in every copy, add the name
to `_EXPECTED_DUPES`.

Commit the rebuilt `master.py` alongside the module change — it is tracked,
and `git status` after a build is the check that the two are in sync.

## Working copy

The working tree lives in Google Drive, but the git directory does **not** —
`.git` here is a one-line pointer file rather than a directory:

```
gitdir: C:/Users/Owner/repos/economicspace.git
```

That keeps thousands of loose objects out of Drive sync. The cost is that the
external git directory stores the working tree's absolute path in its
`core.worktree` setting, so **renaming or moving this folder breaks git** —
`git status` starts failing with `fatal: this operation must be run in a work
tree` while `git log` keeps working, which makes it look like a stranger
problem than it is. Repoint it:

```bash
git config --file "C:/Users/Owner/repos/economicspace.git/config" core.worktree "<new absolute path>"
```

`.gitattributes` pins `*.py` to LF, because the sources get pasted into Colab
and Jupyter, which expect LF. Git for Windows sets `core.autocrlf=true` in its
system config by default, so without that pin a checkout here would rewrite
every file to CRLF.

## Output

```
<output_dir>/
    asteroid_catalog.csv               ← Stage 1 (~30–40 MB at 50k rows)
    rejected_entries.csv               ← Stage 1 (validation rejects)
    mineral_value_catalog.csv          ← Stage 2
    transportation/
        launch_vehicles.csv            ← Stage 3
        propellants.csv                ← Stage 3
        delta_v_segments.csv           ← Stage 3
        operational_costs.csv          ← Stage 3
        transportation_summary.csv     ← Stage 3
    profitability_catalog.csv          ← Stage 4 (the headline output)
```

Output files are gitignored — they are regenerated by every run.

### Reading `profitability_catalog.csv`

One row per asteroid — the best (vehicle × propellant) combination found for
it — sorted by `profit_usd` descending. Roughly 60 columns; the ones to look
at first:

| Column | Meaning |
|--------|---------|
| `designation`, `name`, `spectral_type`, `comp_group` | Which asteroid, and what it's made of |
| `viable` | `profit_usd > 0`. The headline filter |
| `profit_M$`, `gross_M$`, `cost_M$` | Same numbers as the `_usd` columns, in millions, for reading |
| `roi` | `profit / total_cost` |
| `usd_per_kg_cost` | Mission cost per kg actually returned — the cleanest cross-asteroid comparison |
| `vehicle`, `propellant`, `isp_s` | The winning combination |
| `dv_out_m_s`, `dv_ret_m_s` | Per-asteroid Δv from its own orbital elements, including any low-thrust penalty |
| `dv_penalty_factor` | 1.0 for chemical, 1.5 for electric — electric can't fly impulsive burns |
| `max_payload_kg` | Material actually returned, after the mining-fraction, rocket-equation, volume and throughput caps |
| `mining_duration_yr` | Time at the asteroid to dig that payload; floors at `station_keeping_floor_yr` |
| `throughput_cap_kg`, `throughput_fits` | Most the rig could dig in `max_mining_duration_yr`, and whether that bound bit |
| `bulk_value_usd_per_kg` | Stage-2 prices × Stage-1 composition × PGM enrichment |
| `volume_fits` | `False` means the capsule volume cap bound the payload, not the mass budget |
| `m_launch_kg`, `m_outbound_prop_kg`, `m_return_prop_kg`, `m_at_asteroid_kg`, `tps_mass_kg` | The mass cascade |
| `*_cost_usd` (15 of them) | The cost cascade, line by line — launch, propellant, hardware, ops, TPS, recovery, liability, licensing, insurance, NRE, autonomy NRE, contingency |
| `upfront_cost_usd`, `ongoing_cost_usd`, `end_of_mission_cost_usd`, `wacc_multiplier*` | Cost by time bucket, and the WACC factor applied to each |
| `pipeline_version`, `catalog_date` | Which version of Stage 4 produced this row, and when |

Running `python modules/calc.py` directly (rather than `master.py`) also
prints a top-20 table, a breakdown by composition group, the winning
vehicle × propellant combinations, and a bar chart of where the money goes.
That last one is the fastest way to see which lever matters: launch-dominated
means try a cheaper vehicle, NRE-dominated means amortise across missions,
WACC-dominated means shorten the mission.

Every mineral price column carries a `_usd_per_kg` suffix — prices are
normalised to USD/kg on the way in, everywhere, so the unit is never in
question downstream.

## Where the material is sold

This is the single most consequential setting in the pipeline, so it gets its
own section.

Water has no intrinsic scarcity value — it is worth whatever it costs to put
it where the customer is. `MINERAL_CONFIG.delivery_destination` sets that:

| Destination | Water | Basis |
|-------------|-------|-------|
| `earth_surface` *(default)* | $0.001/kg | Terrestrial bulk industrial water |
| `leo` | $4,250/kg | Falcon 9 reusable $/kg-to-LEO avoided |
| `cislunar` | $12,750/kg | Cost of lifting it to a TLI/NRHO depot |

That choice decides the entire ranking, because water is **99.9–100% of the
bulk value of every water-bearing asteroid type**:

| Type | Bulk $/kg (`leo`) | From water | Share |
|------|------------------|-----------|-------|
| D | 1,062.63 | 1,062.50 | 100.0% |
| B | 850.13 | 850.00 | 100.0% |
| C | 637.63 | 637.50 | 100.0% |
| M | 5.90 | 0.00 | 0.0% |

Under `earth_surface`, C-type bulk value falls from $637.63 to **$0.13/kg** and
the ranking inverts from carbonaceous types to metal-rich ones.

The default is `earth_surface` because that is what Stage 4's mission model
actually does — it ends in a sample-return capsule on the ground. Setting
`leo` recovers the larger numbers, but only makes sense alongside an
architecture that stops in orbit; Stage 4 still costs a full re-entry, so the
combination over-values the mission. Every output row carries
`delivery_destination` and `value_basis` so a CSV can't be read without
knowing which assumption produced it.

## Mission model

Return-sample architecture, uncrewed throughout — no life support, no crew
habitat, no human in the loop past LEO injection:

```
Earth launch → LEO → outbound burn → asteroid rendezvous
    → autonomous station-keeping + mining
    → return burn → Earth re-entry (sample-return capsule)
```

## What the model does not capture

Stated plainly so results aren't over-read:

- **Nothing is viable.** On a default run, zero asteroids turn a profit, and
  that is the honest answer rather than a bug. Fixed costs (development NRE,
  autonomy NRE, rig, capsule, contingency, WACC) run to billions, while the
  best bulk material is worth a few dollars per kg. There is no "don't fly"
  option, so the ranking is really *which target loses least* — and since
  return material costs more than it earns, the optimiser converges on the
  smallest mission that still closes.
- **Trip time for low-thrust is not modelled.** Electric propulsion carries a
  Δv penalty but not the months-to-years a spiral actually adds.
- **The mining rate has no flight heritage.** No one has sustained-mined an
  asteroid, so `mining_rate_kg_per_day_per_kg_rig` is an engineering
  assumption. It is a single obvious dial rather than a hidden infinity, but
  it is still an assumption.
- **Δv is analytic, not trajectory-optimised.** The patched-conic estimator
  lands within ~10% of published figures and slightly high on the easiest
  co-orbital targets, where real mission design finds better transfers.
- **No launch windows, phasing, or synodic periods.** Every asteroid is
  assumed reachable whenever you like.
- **Prices are static at the point of sale.** Returning enough platinum to
  move the platinum market would move the platinum market; at the payloads
  this model produces (grams of PGM), that never binds.
- **Composition is uniform.** Each asteroid is its taxonomy class's mean
  composition all the way through — no core/mantle structure, no regolith
  versus bedrock, no ore grade.
- **C-type "ice" is bound water** in phyllosilicates, not accessible ice. The
  energy to liberate it is not modelled.

## Data sources

- **NASA JPL Small-Body Database (SBDB)** — orbital + physical backbone
- **MP3C** (Observatoire de la Côte d'Azur) — physical-properties compilation
- **SsODNet ssoBFT** (IMCCE) — best-of-literature diameter, albedo, mass, density, rotation, taxonomy for ~1.2M bodies
- **NEOWISE Diameters & Albedos V2.0** (IRSA TAP) — IR diameters + albedos for ~150k asteroids
- **yfinance** — live futures prices (metals; fuel-cost proxies)
- **USGS Mineral Commodity Summaries + LME** — reference prices for metals yfinance doesn't expose
- **metals.dev** — optional; set `MINERAL_CONFIG.metals_api_key` (defaults to `"DEMO"`, i.e. skipped)

## History

Earlier version-suffixed copies of every module (`Master(1.4.0).py`,
`CalcPipeline(1.3.0).py`, the original Colab notebook, and the rest) were
removed once the code moved into git — version history lives in commits now.
They remain retrievable from the import commit `84ae606`:

```bash
git show --name-only 84ae606                              # what was imported
git show '84ae606:CalcPipeline(1.3.0).py' > restored.py   # restore one
```

`Profitability Pipeline(1.0.2).ipynb` is worth knowing about specifically: it
is the original Colab notebook, and it is not a duplicate of any `.py` here.
It is the only surviving copy of Module 1 v1.0.3, Module 2 v1.1.0, Module 3
v1.2.0 and Module 4 v1.3.2, which were overwritten in place before any of
this was under version control.

```bash
git show '84ae606:Profitability Pipeline(1.0.2).ipynb' > notebook.ipynb
```

### The parallel-repo divergence

This project was briefly developed in two places at once, and both copies
shipped different code under the *same* `pipeline_version` — `1.0.6`, `1.1.4`
and `1.3.6` each meant two different things depending on which copy you read.
That is precisely the failure `pipeline_version` exists to prevent, since it
is stamped into every output CSV.

The two were reconciled in `5ecafa1`, and the merged modules were renumbered
(catalog `1.0.7`, mineral_value `1.1.5`, calc `1.3.7`, master `1.4.4`) because
they match neither parent. Any CSV produced before that merge carries an
ambiguous version stamp — treat `1.0.6` / `1.1.4` / `1.3.6` output as
undated and re-run rather than trusting the number.
