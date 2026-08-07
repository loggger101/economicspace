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
| 1 | `modules/catalog.py` | 1.0.9 | JPL SBDB + MP3C + SsODNet ssoBFT + NEOWISE; merge, dedupe, validate, enrich with per-spectral-type PGM factors |
| 2 | `modules/mineral_value.py` | 1.6.0 | Live yfinance futures, USGS/LME reference prices, in-pipeline mineralogy, destination pricing for every commodity |
| 3 | `modules/transportation.py` | 1.8.2 | Launch vehicles, propellants, Δv segments (incl. the delivery ladder above LEO), operational costs |
| 4 | `modules/calc.py` | 1.10.0 | Per-asteroid Δv **and mission architecture**, in-space delivery, beneficiation, rocket-equation mass cascade + cost cascade → net profit, ROI, $/kg-returned |

## Running it

Python 3.9+ (developed and run on 3.13). Then:

```bash
pip install -r requirements.txt
```

On Windows, invoke the launcher `py` rather than `python` — a bare `python`
hits the Microsoft Store alias and exits without running anything. Every
`python …` command below becomes `py …`.

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
| `.calc.use_aerocapture_return` | `True` | Makes aerocapture *available*. Trades return Δv for a TPS mass penalty (15% of payload); Stage 4 prices both and flies whichever pays, per asteroid |
| `.calc.use_isru_return_propellant` | `True` | Makes ISRU *available*: hydrolox only, at bodies with water, with the extra rock dug, timed and charged |
| `.calc.optimise_architecture_per_asteroid` | `True` | Search return mode and propellant sourcing per target rather than fixing them catalog-wide |
| `.calc.selection_objective` | `"cost_revenue_ratio"` | What the per-asteroid search maximises. `"profit"` restores pre-v1.10.0 behaviour |
| `.calc.return_structure_frac_of_payload` | `0.15` | Return-vehicle structure as a fraction of the haul, on top of the 500 kg base |
| `.calc.nre_amortization_missions` | `1` | Spread ~$588M development NRE across a fleet |
| `.calc.contingency_fraction` | `0.20` | Flat contingency on the cost cascade |
| `.calc.apply_wacc_compounding` | `True` | Time-value of money, bucketed by when each cost is incurred |
| `.mineral.metals_api_key` | `"DEMO"` | Set a real metals.dev key to enable that source; `"DEMO"` silently skips |

`use_isru_return_propellant` and `use_aerocapture_return` changed meaning in
Stage 4 v1.10.0. They used to *force* an architecture on the whole catalog;
they now say it is **available**, and Stage 4 prices every feasible
combination per asteroid and flies the one that pays. ISRU is additionally
gated on physics — hydrolox only, at a body with a non-zero ice fraction — and
the rock it takes to make the propellant is dug, timed and charged like any
other feed.

Historically the dangerous corner was ISRU on *and* aerocapture off: nothing
in the rocket equation scaled with returned payload, so the launch-mass
constraint went slack and a 30 km body "returned" 7.4e14 kg in a 500 kg
capsule for a fictional $7.8e17 profit. Stage 4 v1.3.6 bound the return
**volume** to stop it; v1.10.0 closes it properly, because
`return_structure_frac_of_payload` puts a payload-proportional term back into
the cascade. Set that to `0.0` and the corner reopens.

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

One row per asteroid — the best mission found for it, across vehicle ×
propellant × return mode × propellant sourcing × rendezvous apsis ×
concentration ratio — sorted by `profit_usd` descending. Note that the *file*
is sorted by profit while the *search* that produced each row optimises
`selection_objective` (cost/revenue by default); those are different questions
and the sort order is the less useful of the two. Roughly 65 columns; the ones
to look at first:

| Column | Meaning |
|--------|---------|
| `designation`, `name`, `spectral_type`, `comp_group` | Which asteroid, and what it's made of |
| `viable` | `profit_usd > 0`. The headline filter |
| `profit_M$`, `gross_M$`, `cost_M$` | Same numbers as the `_usd` columns, in millions, for reading |
| `roi` | `profit / total_cost` |
| `usd_per_kg_cost` | Mission cost per kg actually returned — the cleanest cross-asteroid comparison |
| `vehicle`, `propellant`, `isp_s` | The winning combination |
| `aerocapture_return`, `isru_return` | The architecture the search chose **for this asteroid**. Both used to be catalog-wide settings |
| `rendezvous_apsis` | `aphelion`, `perihelion` or `reference` — which apsis the transfer meets the target at, resolved against the destination |
| `isru_propellant_kg`, `isru_feed_kg` | Return propellant made on site, and the rock dug to make it. That feed comes off the throughput and mineable-mass budgets before any ore is loaded |
| `dv_out_m_s`, `dv_ret_m_s` | Per-asteroid Δv from its own orbital elements, including any low-thrust penalty |
| `dv_penalty_factor` | 1.0 for chemical, 1.5 for electric — electric can't fly impulsive burns |
| `max_payload_kg` | Material actually returned, after the mining-fraction, rocket-equation, volume and throughput caps |
| `mining_duration_yr` | Time at the asteroid to dig that payload; floors at `station_keeping_floor_yr` |
| `throughput_cap_kg`, `throughput_fits` | Most the rig could dig in `max_mining_duration_yr`, and whether that bound bit |
| `bulk_value_usd_per_kg` | Stage-2 prices × Stage-1 composition × PGM enrichment |
| `volume_fits` | `False` means the capsule volume cap bound the payload, not the mass budget |
| `m_launch_kg`, `m_outbound_prop_kg`, `m_return_prop_kg`, `m_at_asteroid_kg`, `tps_mass_kg` | The mass cascade |
| `m_dry_return_kg` | Return-vehicle dry mass actually flown — the 500 kg base plus `return_structure_frac_of_payload` of the haul. Compare it to `max_payload_kg`: a ratio far above ~7:1 means something has gone slack |
| `ep_system_kg`, `ep_power_w`, `ep_system_cost_usd` | The electric stage. Before v1.10.0 the first two existed and the third did not, which is exactly the bug |
| `*_cost_usd` (16 of them) | The cost cascade, line by line — launch, propellant, hardware, EP stage, ops, TPS, recovery, liability, licensing, insurance, NRE, autonomy NRE, contingency |
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

## Programme scale is now the strongest lever

With reliability growth in, `nre_amortization_missions` finally does what its
name suggests — and the two v1.8.0/v1.9.0 models pull against each other in a
way worth understanding. Mars, beneficiated:

⚠️ **Not re-measured since calc v1.9.1.** The N=1 anchor alone has since moved
from 25.2× to 51.82× (calc v1.10.0 + mineral_value v1.7.0), and Mars is no
longer the best case — cislunar is. The reliability and rig-sharing columns
are unaffected, and the *shape* of the argument is what this table is for, but
the cost/revenue column is stale and the curve wants rebuilding at cislunar.

| Programme | `p_mining` | `P(success)` | Missions sharing one rig | Best cost/revenue (stale) |
|---|---|---|---|---|
| 1 mission | 0.850 | 0.698 | 1 | 25.2× |
| 10 missions | 0.902 | 0.741 | 7 (capped) | 6.9× |
| 100 missions | 0.943 | 0.775 | 7 (capped) | **5.3×** |

Going from 10 to 100 missions buys much less than going from 1 to 10, and the
reason is the rig service-life cap: at this stay length one rig serves seven
missions, so the 8th mission buys a whole new rig. NRE keeps amortising,
reliability keeps growing, but the hardware does not get cheaper past that
point.

That is the honest shape of the "just fly more missions" argument — real, but
sublinear, and bounded by market saturation at the far end.

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
  delivering it avoids, scaled by the in-space utility factor (base profile:
  water 1.00, structural metals 0.70, silicates 0.25, carbon 0.40, organics
  0.20), less the cost of refining it into a usable article on site. Note the
  *plus*: the launch cost is on top of the material, not instead of it.
- **Shipped down** — worth its terrestrial price **minus** the downleg:
  capsule + TPS + recovery + depot-departure burn, derived from the same
  Stage 3 rates Stage 4 charges for an Earth return. ~$25,400/kg from LEO,
  ~$27,300/kg from NRHO. Coming down is far cheaper than going up.

This is what puts an honest number on platinum at a depot. Its in-space
utility is 0.00 — nobody in orbit wants platinum — but it is still platinum,
so it is priced by shipping it home rather than written off:

| Commodity | `earth_surface` | `leo` | `cislunar` | `lunar_surface` | `mars_surface` | Route |
|-----------|----------------|-------|------------|-----------------|----------------|-------|
| water | $0.001/kg | $4,050 | $10,607 | $12,523 | $11,073 | used in space |
| iron | $0.50/kg | $2,747 | $7,337 | $9,315 | $17,812 | used in space |
| nickel | $16.50/kg | $2,763 | $7,353 | $14,633 | $31,360 | used in space |
| platinum | $55,692/kg | $30,282 | $28,375 | $10,753 | $0 | shipped down |
| gold | $137,959/kg | $112,549 | $110,642 | $93,020 | $41,565 | shipped down |
| rhodium | $320,000/kg | $294,590 | $292,683 | $275,061 | $223,606 | shipped down |
| olivine | $0.05/kg | $857 | $2,496 | $430 | $696 | used in space |
| carbon | $0.20/kg | $1,489 | $4,112 | $8,272 | $690 | used in space |

Precious-metal rows carry a live spot quote, so they move between runs; the
rest are reference prices. Four things in that table are worth reading twice:

- **Cislunar is worse than LEO for anything shipped down** — it is further from
  the customer, and the downleg is what sets the price.
- **Platinum at Mars is exactly $0.** The $96,394/kg downleg from Mars exceeds
  every terrestrial price in the catalog, and there is no Martian buyer. That
  is the correct answer, not a bug.
- **Water is worth more on the lunar surface than on Mars** ($12,523 vs
  $11,073) despite Mars costing 2.1× as much to reach, because Mars has its own
  ice and the Moon's is in permanently shadowed craters.
- **Olivine is worth less on the Moon than in LEO** ($430 vs $857) even though
  the Moon costs 5× as much to reach. Shipping rock to a body made of rock is
  not a business.

The `value_route` column records which fate was chosen for every row.

⚠️ The prices and the downleg are derived; the utility fractions are
**engineering judgements**. They are the softest assumption in the pipeline
and live in one table for exactly that reason.

#### Utility is per destination, because the alternative to importing isn't
#### always launching (v1.7.0)

The freight table above says what Earth would pay to put a kilogram somewhere.
It does **not** say whether anyone there wants it — and that answer is not a
function of distance. It is a function of what the destination can dig up for
itself.

- **LEO and cislunar** are empty space. Nothing is available locally at any
  price, so the only substitute for asteroid material is the same material
  launched from Earth. These carry the base profile unchanged, and every other
  destination is defined as a deviation from them.
- **The lunar surface** sits on silicate regolith carrying 5–15 wt% FeO plus
  mare ilmenite, and on polar water ice. Water drops to 0.60 (the ice is in
  permanently shadowed craters at ~40 K with no sunlight to work by), iron and
  Fe-Ni to 0.45, silicates to 0.03. Carbon is *not* discounted — solar-wind
  implantation leaves it at ~100 ppm, which is not a resource.
- **The Martian surface** has metres-thick mid-latitude ground ice, 1–3 wt%
  hydrated regolith measured by Curiosity's SAM, a 95.3% CO₂ atmosphere and a
  globally oxidised crust. Water drops to 0.25, carbon to 0.02, silicates to
  0.02, iron to 0.40.
- **Nickel, cobalt and copper are undiscounted everywhere.** No concentrated
  ore of any of them is known on either body, and they are what motors,
  batteries and wiring are made of.

Two things worth not "fixing". First, **every override runs downward** — that
is the only direction this table can move without becoming a way to manufacture
viability, which is the one thing the in-space case must not be tuned into. A
settlement catalyst market for the PGMs was considered and rejected; the reason
is in the note above `IN_SPACE_UTILITY_BY_DESTINATION`, and it is a routing
limitation, not a judgement about Mars.

Second, **prices still rise with distance** — Mars freight is 10.6 kg-in-LEO
per kg delivered and that dominates. They just no longer rise as fast as the
freight does, and the volatiles that carried the Mars result rise least: water
at Mars is 2.7× its LEO price now, against 11× before.

The import budget is split too. `IN_SPACE_ANNUAL_DEMAND_KG` has described
itself as one shared budget since v1.5.0 while the code handed *every*
commodity the whole thing, so a 20 t/yr Mars base would absorb 20 t of water
and 20 t of platinum and 20 t of olivine. `_DEMAND_SHARE_BY_CLASS` now
partitions it — propellant 0.55, structural 0.25, shielding 0.15, chemical
0.05 — and `annual_market_kg` is routed, so a commodity flown home saturates
the **terrestrial** market rather than a depot's import budget. Platinum at LEO
was capped at the depot's 500 t/yr against the world's actual 180 t/yr.

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

⚠️ The search costs runtime: roughly **8× slower** on the beneficiation path.
On the v1.0.9 catalog (35,778 asteroids) one destination is ~140 s raw against
~1,100 s beneficiated, so re-measuring all five is a couple of hours. Tune with
`.calc.concentration_search_steps`.

The 1/r² term punishes distant targets hard (cislunar delivery, measured on a
1,959-body pre-v1.0.9 run; the ratios between rows are the point, not the
absolute masses):

| Semi-major axis | W/kg at target | Mean array mass |
|-----------------|---------------|-----------------|
| < 1.2 AU | 51.5 | 4 kg |
| 1.8–2.5 AU | 11.4 | 41 kg |
| > 3.2 AU | 4.7 | 226 kg |

### Combined effect

Cost/revenue ratio (lower is better; 1.0 would be breakeven), catalog v1.0.9 /
calc v1.10.0 / mineral_value v1.7.0, full catalog — 35,807 asteroids fetched,
~29,600–35,000 evaluable per destination. The v1.6.0 column is the previous
Stage 2 pricing, run in the **same process on identical code**, so the
difference is the pricing change and nothing else:

| | raw v1.6.0 → **v1.7.0** | beneficiated v1.6.0 → **v1.7.0** | best target (v1.7.0, beneficiated) |
|---|---|---|---|
| `earth_surface` | 46,049.9× → 46,071.3× | 25,110× → _(pending)_ | 4660 Nereus, Xe, 2.5× |
| `leo` | 65.97× → 72.45× | 47.17× → 48.13× | 4015 Wilson-Harrington, B, 5.5× |
| `cislunar` | 21.71× → 31.83× | 19.02× → **22.93×** | 7753, B, 5.4× |
| `lunar_surface` | 25.54× → 75.83× | 21.42× → 40.61× | 7753, B, 4.8× |
| `mars_surface` | 16.59× → 70.41× | **11.86×** → 51.82× | 6178, P, 7.1× |

`earth_surface` is the **control** — in-space pricing does not apply there, so
its +0.05% raw movement is the run-to-run noise floor from live quotes shifting
between loops. Everything above ~0.05% is real.

Still **zero viable missions** anywhere.

#### Mars is no longer the best case — cislunar is

This reverses `1a5e0c8`, where Mars took the lead. Mars was best *because*
Stage 2 credited it full launch-cost-avoided for water and carbon at a
destination with metres-thick mid-latitude ground ice and a 95.3% CO₂
atmosphere. Once v1.7.0 prices that local competition, Mars goes from best of
the four in-space destinations to **worst** (+337%), and cislunar wins at
22.93× — because an NRHO depot is the one destination with no local resources
at all, so it takes no ISRU discount. Its +20.6% is entirely the routed market
cap.

The Mars winner changes identity three times as the discount bites — 35678 (D)
→ 4015 Wilson-Harrington (B) → 8651 (M) → 6178 (P) — which is the tell that
this is compositional, not a rescaling. Discount the volatiles and the
optimiser walks away from hydrated bodies. The Moon moves the *opposite* way,
its winner shifting toward a B-type, because lunar water only falls to 0.60
against Mars's 0.25.

**LEO barely moves under beneficiation** (+2.0%) despite +9.8% raw, with an
unchanged winner and concentration ratio: concentrating to 5.5× shifts the
payload mix off the commodity whose ceiling moved.

#### Beneficiation now helps everywhere, cislunar included

⚠️ This **retires the `fa263ad` finding** that cislunar was the one destination
where the optimiser declined to concentrate the best body (39.79× either way).
It no longer reproduces — cislunar goes 21.71× → 19.02× at v1.6.0 pricing and
31.83× → 22.93× at v1.7.0, concentrating 2.5× and 5.4×.

It was retired by **calc v1.10.0, not by the pricing change** — the v1.6.0
column above already concentrates. v1.10.0 replaced the selection objective,
and "declines to concentrate" turns out to have been an artefact of optimising
`profit_usd` while reporting a ratio. So the old warning has inverted: don't
repeat "the optimiser declines to concentrate at cislunar" either. What
survives is the weaker, still-true claim that the decision belongs to the
(target × destination) pair rather than to the target.

⚠️ **The release progression below has not been re-measured** and predates both
calc v1.10.0 and mineral_value v1.7.0. It is kept because the *discipline* it
records is the point — every step was a correction, and the last two moved the
number down. The digits are stale, and the series now wants rebuilding against
cislunar rather than Mars, whose N=1 anchor has moved from 25× to 51.82×.

| Release | Mars | What it started charging for |
|---|---|---|
| v1.6.0 | 2.2× | — |
| v1.7.0 | 14× | low-thrust trip time, launch windows, bound-water energy, learning curve, market saturation |
| v1.8.0 | 39× | rig service life, mission reliability, cryogenic boil-off, in-space manufacturing |
| v1.9.1 | 34× | reliability growth, and `p_mining` recalibrated 0.75 → 0.85 on the full flight record |
| catalog v1.0.9 | **25×** | nothing new — restored SsODNet, which had been downloaded and then discarded on every run, taking measured taxonomy from ~1,850 to ~24,675 bodies |
| v1.10.0 | *not yet measured* | the electric propulsion stage and the return vehicle's structure — both flown as mass, neither billed — plus a per-asteroid architecture search and a fixed selection objective |

### What changed in v1.10.0

Two of these are the same bug in two places: **a mass entered the rocket
equation and never entered the ledger.** That is the failure mode to watch for
here, because the mass cascade and the cost cascade live in different
functions and nothing checks that every kilogram in one has a price in the
other.

- **The electric propulsion stage was free.** v1.7.0 sized the EP array and
  thruster, pushed them through the rocket equation, and never passed them to
  the cost model. A 309 kW, 14-tonne electric stage cost nothing. Now priced:
  the array off the existing $800/W row, the thruster and PPU off a new
  $1.5M/kW Stage-3 row anchored on NEXT-C.
- **The return vehicle did not grow with its cargo.** A flat 500 kg however
  much it carried, so the cascade loaded 125 tonnes of ore into a half-tonne
  can — 250:1 payload-to-structure, against 0.4:1 to 2:1 for real cargo
  spacecraft. `return_structure_frac_of_payload` fixes it, and the closed-form
  payload solver carries the term exactly.
- **The search optimised the wrong thing.** Every per-asteroid search picked
  the highest `profit_usd`. Since revenue here sits orders of magnitude below
  cost, that is `≈ −total_cost_usd`, so it quietly meant "pick the cheapest
  mission" — while this README ranked the output by a cost/revenue ratio
  nothing had optimised. The tell was unmissable once looked for: adding
  options could make a target's reported ratio *worse*. `selection_key` now
  maximises profit when anything is profitable and minimises cost/revenue
  otherwise.
- **Aerocapture and ISRU became per-asteroid choices**, and ISRU became
  physical: hydrolox only, at bodies with water, at 1.286 kg of water per kg
  of propellant, with the extra rock dug, timed and charged. The old switch
  synthesised *xenon* at a rubble pile.
- **The rendezvous apsis is searched, not assumed**, and resolved against the
  destination — a body best met at aphelion for an Earth return can be best
  met at perihelion for Mars. Published validation figures are unaffected.

The first two both flattered electric propulsion and large hauls, so v1.10.0
was expected to move the headline number *up* before the architecture search
pulled it back down. **Measured: the architecture search dominates.** Mars
beneficiated went 25.2× on v1.9.1 to 11.86× on v1.10.0 at unchanged v1.6.0
pricing — better, not worse, despite two new charges. Resolving aerocapture,
ISRU, apsis and propellant per asteroid is worth more than the EP stage and
the return structure cost.

If a change suddenly improves these by an order of magnitude, suspect it has
switched one of the twelve models off rather than found something. See
[What the model charges for](#what-the-model-charges-for).

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
  best case the model can currently reach — `cislunar` delivery plus
  beneficiation — still comes in ~23× short at a single mission. There is no
  "don't fly" option, so the ranking is really *which target loses least*.
  (This was `mars_surface` at ~25× until mineral_value v1.7.0 priced the
  local resources a planetary surface already has; Mars is now ~52×. The
  100-mission figure has not been re-measured since catalog v1.0.9.)
- **Rank by `total_cost_usd / gross_value_usd`, not `profit_usd`.** Revenue is
  orders of magnitude below cost in most configurations, so `profit_usd`
  reduces to `-total_cost_usd` and `top_profitable()` becomes a pure cost
  ranking — a Δv table wearing a profit label. Until v1.10.0 the *search
  inside* Stage 4 had the same flaw for the same reason, and nothing had
  optimised the ratio this README ranks by. See `selection_key`.
- **Cheap launch does not rescue this.** Launch is ~2.3% of a mission. Zeroing
  it entirely improves the ratio by 2.3%.
- **In-space utility fractions are judgements.** `IN_SPACE_UTILITY` and its
  per-destination overrides decide how much of the launch-cost-avoided each
  commodity captures, and no market exists to calibrate them against. They are
  the softest numbers in the pipeline, and the per-destination discounts added
  in v1.7.0 are softer still — they are judgements about economies that do not
  exist. They are held to running *downward* for that reason.
- **Low-thrust trajectories are sized, not optimised.** Trip time and power
  are now modelled (see [What the model now charges for](#what-the-model-charges-for)),
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
- **The refinery is priced but not flown.** In-space manufacturing is charged
  per kg against the material's value; the plant's mass is not added to any
  mission's rocket equation, because it belongs to the buyer at the depot
  rather than to the mining mission.
- **Boil-off hold time is estimated, not integrated.** It uses the Δv-derived
  cruise plus the stay, not an actual thermal model over the real trajectory.
- **C-type "ice" is bound water** in phyllosilicates, not accessible ice. The
  energy to liberate it is now charged (2,500 Wh/kg), but the extraction
  hardware — kilns, condensers, cold traps — is not sized or costed.

## What the model charges for

Twelve models in total, added across four releases. Each defaults ON; set the
flag to `False` to isolate its effect. The five below closed gaps in v1.7.0
that all pushed the answer the same way — towards optimism; the five after
them arrived in v1.8.0 and v1.9.0, and one of those pushed back the other way.
The last two are v1.10.0 and are a different species: not gaps in what the
model charged for, but **masses it flew and never billed at all**.

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
the price. Delivering 6.6 t/yr of water to a Mars base that can absorb 11 t/yr
of it cuts the price to 0.39. Without this, `nre_amortization_missions` had no
natural stopping point — you could amortise development across a fleet whose
output would have destroyed the price justifying it.

World production is USGS; the in-space absorption ceilings (LEO 500 t/yr,
cislunar 100 t, lunar surface 50 t, Mars 20 t) are **judgement, not
measurement** — no such market exists. Since v1.7.0 those are destination
*totals* split across commodity classes rather than a figure each commodity
gets to itself, so the Mars water ceiling is 0.55 × 20 t = 11 t/yr; and the
ceiling follows the **value route**, so anything flown home is bounded by
terrestrial production instead.

### Added in v1.8.0 and v1.9.0

Four in v1.8.0 — rig service life, mission reliability, cryogenic boil-off,
in-space manufacturing — plus **Reliability growth** in v1.9.0, which is kept
next to Mission reliability below rather than in release order because the two
only make sense read together.

**Rig service life and terminal value** (`model_rig_service_life`). The rig
was amortised across `nre_amortization_missions` with no upper bound, so a
programme could spread one machine across 100 missions of two years each —
200 years of duty from something chewing rock. A 15-year life now *caps* the
amortisation, and the cap makes long-stay programmes markedly **more**
expensive, not less:

| Stay per mission | Missions one rig can serve | Charge vs. old flat ÷100 |
|---|---|---|
| 0.25 yr | 60 | 1.7× |
| 1.0 yr | 15 | 6.7× |
| 2.0 yr | 7 | **13.8×** |

Life remaining when the programme ends is credited at the salvage fraction
(0.50) — but only when `nre_amortization_missions > 1`. A rig parked at an
asteroid nobody revisits is stranded, not an asset, so a single-mission run
is unaffected.

**Mission reliability** (`model_reliability`). Revenue was certain. Expected
revenue is now `p_launch(0.97) × exp(−T/MTBF)(30 yr) × p_mining(0.85)` —
about 0.70 for a five-year mission. **Costs are still charged in full**,
which is both conservative and correct: you spend the money whether or not it
works. Launch insurance in the cost model replaces hardware, not revenue, so
there is no double count.

`p_mining` is counted from the actual flight record of regolith-contact
mechanisms, not from the failures alone:

| | Missions |
|---|---|
| **Succeeded** (10) | Apollo 15–17 drills/scoops; Luna 16/20/24; Stardust aerogel; Phoenix arm; Curiosity drill (feed mechanism failed 2016, recovered by feed-extended drilling); Hayabusa2 sampler + SCI impactor; OSIRIS-REx TAGSAM (121.6 g against a 60 g requirement); Perseverance corer; Chang'e 5 and 6 |
| **Partial** (1) | Hayabusa — projectile never fired, but contact dust was still collected and returned |
| **Failed** (2) | Philae's harpoon pyrotechnics; InSight's HP³ mole, which could not get purchase in Martian regolith |

That is **11/13 = 0.85** counting Hayabusa as the success it ultimately was,
or 0.77 counting it as a loss. 0.85 is taken because Hayabusa did return its
sample. An earlier release used 0.75, counted from the failures alone — which
was selection bias, and below even the pessimistic reading.

The honest caveat: none of these is *sustained* mining. They are one-shot or
short-campaign collections of grams to kilograms, not a rig moving 200 kg/day
for years without maintenance. 0.85 is the demonstrated **mechanism** rate;
the sustained-operation exposure is carried by the spacecraft MTBF term
rather than double-counted here.

**Reliability growth** (`model_reliability_growth`, v1.9.0). `p_mining` used
to sit at its first-of-kind 0.75 no matter how many missions a programme
flew — the one
place the model was *pessimistic* rather than optimistic. A fleet that has
flown ten rigs has found and designed out failure modes the first one
discovered the hard way.

Duane/AMSAA: failure probability falls as a power law in cumulative
production, `q(n) = q_first · n^(−α)` with α = 0.30, the bottom of
MIL-HDBK-189's *active* growth band — appropriate for hardware that flies
once every few years with no test fleet to accelerate the learning. Capped at
a 0.95 mature ceiling, because growth is asymptotic: mature spacecraft
mechanisms run 97–99%, and a continuously-operating excavator is harder than
a one-shot deployment.

| Programme size | `p_mining` (fleet average) |
|---|---|
| 1 | 0.850 |
| 10 | 0.902 |
| 100 | 0.943 |

Reported as the **mean over missions 1..N, not the terminal value.** NRE and
the rig are amortised across the whole programme, so per-mission expected
revenue has to use the programme average — quoting the last mission's
reliability would credit every mission with heritage only the last one has.
Exactly 0.850 at N = 1, so single-mission runs use the first-of-kind figure.

Launch and cruise reliability deliberately do *not* grow: launch vehicles are
already mature, and MTBF is a duration exposure rather than a heritage
question.

**Cryogenic boil-off** (`model_propellant_boiloff`). Return propellant sits
in the tank from launch until the departure burn — years, not hours. Loading
per kg actually burned:

| Hold | hydrolox (0.05%/day) | methalox (0.012%) | storable (0%) |
|---|---|---|---|
| 1 yr | 1.20× | 1.04× | 1.00× |
| 5 yr | **2.49×** | 1.25× | 1.00× |
| 8 yr | 4.31× | 1.42× | 1.00× |

Folded into an effective return Δv, which leaves the closed-form cascade
exact: since `m_return_prop` scales with `(R−1)`, inflating that term by `k`
is `R_eff = 1 + (R−1)k`. ISRU return propellant is exempt — it is
manufactured at the asteroid on departure. Without this, hydrolox won long
missions it could not physically have stored propellant for.

v1.10.0 fixed the hold time this table is read with. It was computed once,
before the sizing loop, against a stay of `station_keeping_floor_yr` — 0.25 yr,
the *shortest* stay the model permits — when the real stay is dig time plus
the launch-window wait, which runs to years on exactly the targets that want a
cryogenic upper stage. The prose said "years, not hours" while the arithmetic
said three months. It is now solved inside the same fixed point as the power
plant and the ISRU feed.

**The electric propulsion stage** (v1.10.0). v1.7.0 sized the EP array and
thruster, pushed both through the rocket equation, and never passed either to
the cost model — so a 309 kW, 14-tonne electric stage was free, and electric
propulsion won missions on hardware nobody had to buy. Priced in two parts,
because they cost wildly different amounts per kilogram: the **array** off the
existing $800/W-EOL power-system row, the **thruster and PPU** off a new Stage-3
row at **$1.5M/kW**, anchored on a NEXT-C flight string (7 kW, ~47 kg, in the
$10–15M class) with a $0.5–3M/kW range because high-power Hall systems buy down
from there. Flagged soft in the notes: this pipeline sizes some missions at
300 kW, six times the largest article ever built.

**Return-vehicle structure** (`return_structure_frac_of_payload`, 0.15). The
return vehicle's dry mass was a flat 500 kg however much it carried, so the
cascade loaded 125 tonnes of ore into a half-tonne can — **250:1
payload-to-structure**, against 0.4:1 (Cygnus PCM) to 2:1 (Dragon) for real
cargo spacecraft. Nothing caught it because the only other bound on returned
mass was the launch vehicle's fairing *volume*, which dense ore never fills.
The 500 kg is now a floor — avionics, comms, beacon, separation hardware — and
15% of the payload is added for tankage, primary structure and cargo restraint.
Deliberately at the light end of the real range, since the ablative TPS is
already carried separately and an ore carrier should beat a crew-rated capsule.
The closed-form payload solver carries the term exactly: writing `g = s(1+f) − 1`
for the combined payload-proportional overhead, it reduces to the pre-v1.10.0
expression when `f = 0`.

**In-space manufacturing** (Stage 2). Raw Fe-Ni is not a pressure vessel, and
the gap used to hide inside the 0.70 utility factor — the refinery was
assumed into existence and never costed. Now explicit, ~$230/kg for metals:

- **Energy** at **$6.08/kWh** — the capital cost of a kilowatt-hour in deep
  space ($800/W-EOL over a 15-year life), roughly 100× terrestrial industrial
  power, which is why in-space processing is not obviously free. Metals take
  5 kWh/kg; terrestrial electric-arc steelmaking is 4–5 kWh/kg and there is
  no carbothermic shortcut in vacuum.
- **Plant** at **$200/kg refined** — $300k/kg of deep-space hardware at
  100 kg/yr throughput per kg of plant over 15 years.

Deducted from the *used in space* route only; material shipped down is
refined on Earth. The utility factor now means only what it says.

### Net effect on a default earth_surface run

| | v1.6.0 | v1.7.0 | v1.8.0 |
|---|---|---|---|
| Electric share of winning combos | 12% | 2% | varies by destination |
| Median mission duration | 3.49 yr | 4.12 yr | 4.1 yr |
| Expected revenue multiplier | 1.00 | 1.00 | **0.67** (reliability) |
| Rows with no feasible mission | 0 | 47 | 85 |

## Data sources

- **NASA JPL Small-Body Database (SBDB)** — orbital + physical backbone
- **MP3C** (Observatoire de la Côte d'Azur) — physical-properties compilation
- **SsODNet ssoBFT** (IMCCE) — best-of-literature diameter, albedo, mass, density, rotation, taxonomy for ~1.2M bodies
- **NEOWISE Diameters & Albedos V2.0** (IRSA TAP) — IR diameters + albedos for ~150k asteroids
- **yfinance** — live futures prices (metals; fuel-cost proxies)
- **USGS Mineral Commodity Summaries + LME** — reference prices for metals yfinance doesn't expose
- **metals.dev** — optional; set `MINERAL_CONFIG.metals_api_key` (defaults to `"DEMO"`, i.e. skipped)

### Source outages change the population, not just the coverage

Sources fail soft by design — an unreachable host returns empty and the run
continues. What that hides is that **the number of asteroids evaluated, and
their taxonomy mix, can change by an order of magnitude between runs.**

Where a spectral type cannot be sourced, Stage 1 infers a coarse one from
geometric albedo and records that in `spectral_type_source`
(`source` / `tholen` / `albedo` / `unknown`).

This is not hypothetical. Until catalog v1.0.9, SsODNet was downloaded in full
(~500 MB), parsed, and then **discarded at merge time on every run** — ssoBFT
had renamed its identity columns, the column projection tolerated the loss,
and the source was dropped for having no `designation`:

| | before v1.0.9 | after |
|---|---|---|
| taxonomy measured | 1,854 | **24,675** |
| taxonomy guessed from albedo | 33,235 | **11,131** |
| density measured | 0 | **438** |
| V-type bodies | 3,988 | 2,614 |

The V-type count is the giveaway — V-types are genuinely rare, and 3,988 of
them was an artefact of guessing taxonomy from albedo. **Every figure in this
README committed before v1.0.9 was measured on that degraded catalog**, which
is why they quote "across 1,959 asteroids".

**So check `spectral_type_source` before comparing a run against a committed
number.** The run banner reporting a source as "Active" only means it was
*enabled*, not that it returned anything — read the `Source summary: {...}`
dict and the `Spectral type inferred from albedo for N entries` line instead.

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
