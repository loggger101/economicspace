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
| 2 | `modules/mineral_value.py` | 1.5.0 | Live yfinance futures, USGS/LME reference prices, in-pipeline mineralogy, destination pricing for every commodity |
| 3 | `modules/transportation.py` | 1.6.0 | Launch vehicles, propellants, Δv segments (incl. the delivery ladder above LEO), operational costs |
| 4 | `modules/calc.py` | 1.7.0 | Per-asteroid Δv, in-space delivery architecture, beneficiation, rocket-equation mass cascade + cost cascade → net profit, ROI, $/kg-returned |

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
| `MASTER_CONFIG.delivery_destination` | `"earth_surface"` | **Read [Where the material is sold](#where-the-material-is-sold) before changing.** Sets every price *and* the mission architecture. One of `earth_surface`, `leo`, `cislunar`, `lunar_surface`, `mars_surface`. Writes Stage 2 and Stage 4 together — never set the two sub-configs separately |
| `.calc.use_beneficiation` | `False` | Return concentrate instead of run-of-mine ore. Charges the extra dig time, processing energy and solar-array mass. See [Beneficiation](#beneficiation) |
| `.calc.beneficiation_recovery` | `0.90` | Fraction of the valuable phase reporting to concentrate |
| `.calc.max_concentration_ratio` | `50.0` | Safety cap on feed:concentrate. The purity bound normally binds first |
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

Drive also corrupts git's stat cache. When git writes a file during checkout
and immediately stats it, Drive reports a placeholder size of 16384 bytes
rather than the real one, and git caches that in the index. Every later
`git status` sees the mismatch and reports the file modified *without reading
it* — a differing size is normally conclusive proof of a change. The tell is
`git status` and `git diff` disagreeing, and the consequence is that
`git checkout` and `git merge --ff-only` abort on phantom changes, so a merged
PR fails to land locally.

`.githooks/drive-restat.sh` repairs it automatically via `post-checkout`,
`post-merge` and `post-rewrite`. A fresh clone opts in once:

```bash
git config core.hooksPath .githooks
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

Nothing mined has an intrinsic price — it is worth whatever it costs to put
an equivalent kilogram where the customer already is. The destination sets
both what the cargo sells for (Stage 2) and what the mission costs to fly
(Stage 4), and **both stages carry the field, so both must be set**:

```python
MASTER_CONFIG.delivery_destination = "cislunar"   # writes Stage 2 and Stage 4
```

Setting only one is the classic error — it prices the cargo at a depot while
still paying to land it in Utah. Stage 4's `destination_check()` refuses to
let that pass quietly.

### What a kilogram is worth

In-space prices are the launch cost avoided, **derived** rather than
tabulated: Falcon 9 reusable $/kg-to-LEO, carried further by walking a chain
of real stages backwards from the payload (`delivered_cost_usd_per_kg` over
`_DELIVERY_LEGS`). Staging is modelled leg-by-leg because it matters — a
single stage flying the whole 5,920 m/s to the lunar surface needs 10.96 kg
in LEO per kg landed against 4.99 kg for the tug-plus-lander pair that would
actually be flown.

| Destination | Launch cost avoided | kg in LEO per kg | Chain |
|-------------|--------------------|------------------|-------|
| `earth_surface` *(default)* | — | — | Terrestrial commodity prices |
| `leo` | $4,253/kg | 1.00 | Falcon 9 reusable $/kg-to-LEO |
| `cislunar` | $10,810/kg | 2.54 | TLI + NRHO insertion (3,600 m/s), cryo tug |
| `lunar_surface` | $21,210/kg | 4.99 | TLI + LOI (4,050 m/s) tug, then 1,870 m/s lander |
| `mars_surface` | $45,105/kg | 10.61 | TMI (3,600 m/s), aeroentry at 30% surviving mass, 800 m/s retroprop |

Mars' entry survival fraction is measured, not assumed: MSL landed 899 kg of
a 3,257 kg entry mass (27.6%) and Perseverance 1,025 of 3,440 (29.8%). The
lander dry-mass fraction of 0.20 is the Apollo LM descent stage (2,134 kg dry
on 8,200 kg of propellant).

⚠️ **The two surface figures are marginal-transport lower bounds.** They price
propellant and stages on a reusable Falcon 9 LEO price, with no first-of-kind
development, no programme overhead and no cadence limit. Real delivered cost
today is far higher — CLPS lunar landers run on the order of $1M/kg at ~100 kg
scale. Read them as "what it could cost at industrial scale", not "what it
costs now".

A kilogram sitting at a depot is worth **the better of its two fates**, and
the pipeline picks per commodity:

- **Used in space** — worth its terrestrial price **plus** the launch bill
  delivering it avoids, scaled by `IN_SPACE_UTILITY` (water 1.00, structural
  metals 0.70, silicates 0.25, carbon 0.40, organics 0.20). Note the *plus*:
  the launch cost is on top of the material, not instead of it.
- **Shipped down** — worth its terrestrial price **minus** the downleg:
  capsule + TPS + recovery + depot-departure burn, derived from the same
  Stage 3 rates Stage 4 charges for an Earth return. ~$25,400/kg from LEO,
  ~$27,300/kg from NRHO. Coming down is far cheaper than going up.

This is what puts an honest number on platinum at a depot. Its in-space
utility is 0.00 — nobody in orbit wants platinum — but it is still platinum,
so it is priced by shipping it home rather than written off:

| Commodity | `earth_surface` | `leo` | `cislunar` | Route |
|-----------|----------------|-------|------------|-------|
| water | $0.001/kg | $4,253 | $10,810 | used in space |
| iron | $0.50/kg | $2,978 | $7,567 | used in space |
| nickel | $16.50/kg | $2,994 | $7,583 | used in space |
| platinum | $56,695/kg | $31,285 | $29,378 | shipped down |
| gold | $138,882/kg | $113,472 | $111,565 | shipped down |
| rhodium | $320,000/kg | $294,590 | $292,683 | shipped down |

Note that cislunar is *worse* than LEO for anything shipped down — it is
further from the customer. The `value_route` column records which fate was
chosen for every row.

⚠️ The prices and the downleg are derived; the utility fractions are
**engineering judgements**. They are the softest assumption in the pipeline
and live in one table for exactly that reason.

### What it costs to get there

The destination is a different mission, not a different label:

| | `earth_surface` | `leo` | `cislunar` | `lunar_surface` | `mars_surface` |
|---|---|---|---|---|---|
| Delivery vehicle | re-entry capsule $150k/kg | berthing adapter $60k/kg | berthing adapter $60k/kg | lander $200k/kg | lander $200k/kg |
| Arrival ops | $15M recovery | $2M handover | $2M handover | $2M handover | $2M handover |
| Licensing | $2.5M launch + re-entry | $1.2M launch only | $1.2M launch only | $1.2M launch only | $1.2M launch only |
| Heat shield | yes | only if aerobraking | never | never (airless) | yes |

**Cislunar is cheaper to reach than LEO and worth more per kilogram.** This
reads as a bug and is not one: capturing into LEO must kill the entire
arrival hyperbola, while capturing into an NRHO depot only has to *bind* the
orbit, with the burn taking the Oberth benefit at low perigee. The advantage
widens as arrival energy falls — 5.6× at v_inf = 1 km/s, 2.7× at 5 km/s.

**Mars is a different journey, not a discounted Earth return.**
`_asteroid_to_mars_dv_km_s` runs the heliocentric transfer from the
asteroid's orbit to Mars' (1.524 AU), so the departure burn, arrival
v_infinity and capture are computed separately. That matters because plenty
of asteroids are genuinely more accessible from Mars than from Earth — and
approximating the leg would have hidden it entirely:

| Target | → Earth surface | → cislunar | → lunar surface | → Mars surface |
|--------|----------------|-----------|-----------------|----------------|
| Bennu-like (a = 1.13) | **0.75** | 1.96 | 4.56 | 5.14 |
| Mars-crosser (a = 1.46) | 0.78 | 2.33 | 4.93 | **3.28** |
| Main belt (a = 2.70) | 4.13 | 7.32 | 9.92 | **3.84** |

km/s of return Δv. A main-belt body is cheaper to deliver to Mars than to
Earth. The Moon is the awkward one — nearest in distance, but airless, so
every metre per second of arrival is propulsive.

Every output row carries `delivery_destination`, `delivery_arch` and
`value_basis`, so a CSV cannot be read without knowing which assumption
produced it.

## Beneficiation

Off by default (`CALC_CONFIG.use_beneficiation`). Terrestrial mines ship
concentrate, not ore; without this the pipeline flies home run-of-mine
regolith at bulk grade while the rig's own throughput capacity — 66× the
rocket-equation payload limit on a default run — sits idle.

Switched on, the rig digs surplus feed, rejects the gangue, and loads
concentrate.

### The load is optimised, not specified

A mission is not sent for a named mineral — it brings back **the most
valuable load it can assemble from what the target actually contains**. With
a fixed mass budget and divisible, per-kilogram-priced phases, that is a
fractional knapsack, so greedy selection by $/kg is provably optimal: fill
the hold with the best phase available, then the next, until full or the feed
runs out (`optimal_payload_mix` over `asteroid_phase_table`).

Both honest bounds fall out of it automatically — you cannot load more of a
phase than the processed feed contained, and once the hold is pure best-phase
there is nothing better to add. On an M-type at 50% metal / 45% silicate with
0.90 recovery:

| Feed | Delivered | Load |
|------|-----------|------|
| 1.0× | $5,135/kg | hold 90% full, in-situ ratios |
| 2.0× | $7,081/kg | 90% metal |
| 2.2× | $7,567/kg | 100% metal — saturated |
| 5.0× | $7,567/kg | no further gain |

### How hard to concentrate is an economic decision

Grade saturates; costs do not. Every extra kilogram of feed still costs dig
time (compounding through ops and WACC), processing energy, and the solar
array mass to supply it — and that array mass comes out of the payload
budget. So the optimum is usually *strictly inside* the range, and
`evaluate_combo` searches for it rather than assuming it.

The search always includes **not concentrating at all** as a baseline, so
beneficiation is an option rather than an obligation and can never make a
mission worse. On a cislunar run it declines on 1.4% of targets; where it
does concentrate, the chosen ratio is typically ~7×, never the 50× cap.

Costs charged, all of which the search trades against:

- **Time.** Dig time is charged on the *feed*, not the product.
- **Energy and mass.** Stage 3's 200 Wh/kg excavation and 500 Wh/kg
  beneficiation rates over the stay time give a power draw; Stage 3's
  60 W/kg-at-1-AU power-system row, scaled 1/r² by the target's semi-major
  axis, turns that into array mass; the array flies in the same rocket
  equation as everything else. Payload → feed → power → mass → payload is a
  real circular dependency, solved by fixed-point iteration.

⚠️ The search costs runtime: roughly **10× slower** on the beneficiation path
(~5 s → ~55 s for 1,959 asteroids). Tune with
`.calc.concentration_search_steps`.

The 1/r² term punishes distant targets hard (cislunar delivery, 1,959-body
run):

| Semi-major axis | W/kg at target | Mean array mass |
|-----------------|---------------|-----------------|
| < 1.2 AU | 51.5 | 4 kg |
| 1.8–2.5 AU | 11.4 | 41 kg |
| > 3.2 AU | 4.7 | 226 kg |

### Combined effect

Cost/revenue ratio across the same 1,959 asteroids (lower is better; 1.0
would be breakeven):

| | plain (best / median) | beneficiated (best / median) |
|---|---|---|
| `earth_surface` | 151,266× / 21,883,237× | 151,266× / 17,616,717× |
| `leo` | 262× / 5,145× | 177× / 2,595× |
| `cislunar` | 62× / 2,973× | 62× / 1,397× |
| `lunar_surface` | 133× / 2,074× | 71× / 951× |
| `mars_surface` | 25× / 442× | **14× / 110×** |

Beneficiation roughly **halves** the gap for a typical target. At cislunar it
declines to concentrate on the single best body — already water-rich enough
that grinding more rock costs more than it returns.

Still **zero viable missions** anywhere, but Mars closes the gap by ~4 orders
of magnitude from the default and lands within a factor of ~14.

These figures are ~6× worse than the v1.6.0 release, and deliberately so —
v1.7.0 closed five modelling gaps that all flattered the answer. The old
headline of 2.2× at Mars was a 1,500 s Hall thruster flying instantly on
power it never carried. With low-thrust trip time modelled, electric
propulsion falls from 12% of winning combos to 2%, and Mars settles at 14×.
See [What the model now charges for](#what-the-model-now-charges-for).

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

- **Nothing is viable, in any configuration.** Zero asteroids turn a profit on
  a default run, and that is the honest answer rather than a bug. Fixed costs
  (development NRE, autonomy NRE, rig, capsule, contingency, WACC) run to
  billions, while the best bulk material is worth a few dollars per kg. The
  best case the model can currently reach — cislunar delivery plus
  beneficiation — still comes in ~36× short. There is no "don't fly" option,
  so the ranking is really *which target loses least*.
- **Rank by `total_cost_usd / gross_value_usd`, not `profit_usd`.** Revenue is
  orders of magnitude below cost in most configurations, so `profit_usd`
  reduces to `-total_cost_usd` and `top_profitable()` becomes a pure cost
  ranking — a Δv table wearing a profit label.
- **Cheap launch does not rescue this.** Launch is ~2.3% of a mission. Zeroing
  it entirely improves the ratio by 2.3%.
- **In-space utility fractions are judgements.** `IN_SPACE_UTILITY` decides how
  much of the launch-cost-avoided each commodity captures, and no market
  exists to calibrate it against. It is the softest number in the pipeline.
- **In-space manufacturing is not costed.** Raw Fe-Ni is not a pressure
  vessel. The 0.70 utility factor is a stand-in for a refining and forming
  plant that appears nowhere in the cost model.
- **Low-thrust trajectories are sized, not optimised.** Trip time and power
  are now modelled (see [What the model now charges for](#what-the-model-now-charges-for)),
  but the EP stage is sized to a fixed target thrusting time rather than having
  its trajectory jointly optimised against payload and arrival date.
- **The mining rate has no flight heritage.** No one has sustained-mined an
  asteroid, so `mining_rate_kg_per_day_per_kg_rig` is an engineering
  assumption. It is a single obvious dial rather than a hidden infinity, but
  it is still an assumption.
- **Δv is analytic, not trajectory-optimised.** The patched-conic estimator
  lands within ~10% of published figures and slightly high on the easiest
  co-orbital targets, where real mission design finds better transfers.
- **Launch windows are statistical, not ephemeris-based.** The synodic period
  gives an expected wait; the model does not compute actual departure dates,
  so it cannot tell you *which* window.
- **Composition is uniform.** Each asteroid is its taxonomy class's mean
  composition all the way through — no core/mantle structure, no regolith
  versus bedrock, no ore grade. Beneficiation concentrates *against that mean*,
  so the purity bound is the class's best phase rather than a real assay.
- **Beneficiation has no flight heritage either.** Magnetic and electrostatic
  separation in microgravity, on a rotating body, with no water and no
  gravity-fed classification, has never been demonstrated. The 0.90 recovery
  is borrowed from terrestrial flotation circuits.
- **Concentrate density is approximated by bulk density** in the volume cap. A
  metal concentrate is denser than the parent body, so the volume constraint
  is conservative.
- **C-type "ice" is bound water** in phyllosilicates, not accessible ice. The
  energy to liberate it is now charged (2,500 Wh/kg), but the extraction
  hardware — kilns, condensers, cold traps — is not sized or costed.

## What the model now charges for

v1.7.0 closed five gaps that all pushed the answer the same way — towards
optimism. Each defaults ON; set the flag to `False` to isolate its effect.

**Low-thrust trip time** (`model_low_thrust_time`). Electric propulsion used
to pay a Δv penalty and nothing else — it flew its burns instantly on power
it never carried. A thruster's power fixes its thrust, so burning `m_prop`
takes `m_prop·(Isp·g0)² / (2·η·P)`: **high specific impulse buys propellant
mass at a quadratic cost in time-or-power.** The EP stage is now sized to
finish inside `ep_target_thrust_yr` (3.0 by default), and the array plus
thruster/PPU mass that demands goes into the same rocket equation as
everything else. A typical electric winner now hauls ~4,900 kg of power
system against a 2,000 kg mining rig.

Validated against Dawn — the only mission that has flown this regime. At its
2.2–3.0 AU operating distance the formula gives 5.0–9.3 years of thrusting;
Dawn actually thrust ~5.9 years. The 1/r² term does the work: evaluated at
Dawn's 1 AU array rating the same sum gives 1.0 year and is nonsense.

**Launch windows** (`model_launch_windows`). Departure needs phasing, and
alignments recur at the synodic period, so expected wait after mining is half
a period. This punishes **NEAs hardest**, which is the opposite of the Δv
story:

| Semi-major axis | Period | Synodic with Earth |
|---|---|---|
| 1.05 AU | 1.08 yr | **10.0 yr** |
| 1.13 AU | 1.20 yr | 6.0 yr |
| 2.70 AU | 4.44 yr | 1.3 yr |

A body whose period nearly matches Earth's drifts in phase very slowly.
Accessibility in Δv and accessibility in *time* pull in opposite directions,
and only one of them was modelled before.

**Bound-water liberation** (`model_water_liberation`). C/B/D-type "ice" is
water locked into phyllosilicates — it has to be baked out at ~700 K, not
scooped. Stage 3 charges 2,500 Wh per kg of water, derived from heating the
rock through dehydroxylation plus the enthalpy of dehydration plus
vaporisation, and matching the 1–3 kWh/kg in the ISRU literature. The
pipeline had been extracting it for free and selling it at full
launch-cost-avoided.

**Learning curve** (`learning_curve_rate`, 0.85). Wright's law on the
per-mission articles — capsule/lander and power system. The amortised mining
rig is excluded because it is modelled as one shared unit, not N built.
Exactly 1.0 at `nre_amortization_missions = 1`, so a single-mission run is
untouched; 0.44 at N = 100.

**Market saturation** (`model_market_saturation`). `P/P0 = (1 + Q/Q_market)^(−1/ε)`
against Stage 2's `annual_market_kg`, with ε = 0.5 (precious-metal demand is
inelastic). Returning 180 t/yr of platinum doubles world supply and quarters
the price. Delivering 6.6 t/yr of water to a 20 t/yr Mars base cuts it to
0.57. Without this, `nre_amortization_missions` had no natural stopping
point — you could amortise development across a fleet whose output would
have destroyed the price justifying it.

World production is USGS; the in-space absorption ceilings (LEO 500 t/yr,
cislunar 100 t, lunar surface 50 t, Mars 20 t) are **judgement, not
measurement** — no such market exists.

### Net effect on a default earth_surface run

| | v1.6.0 | v1.7.0 |
|---|---|---|
| Electric share of winning combos | 12% | **2%** |
| Median mission duration | 3.49 yr | 4.12 yr (+18%) |
| Median total cost | $2.59 B | $2.77 B (+7.3%) |
| Rows with no feasible mission | 0 | 47 |

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
