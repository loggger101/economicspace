# economicspace — Asteroid Mining Profitability Pipeline

End-to-end pipeline that estimates, for every asteroid it can pull data on, the
net profit of an **uncrewed autonomous mining and sample-return mission**.

It chains four stages: build an asteroid catalog from public astronomy
databases → price the minerals those asteroids contain → cost the
transportation → run the rocket-equation and cost cascade to produce a ranked
profitability table.

## Layout

```
Dashboard.vbs          Double-click this: opens the dashboard, no terminal
launch_ui.py           What it runs -- starts the server, owns the stop button
run.bat                Windows launcher: a terminal menu over everything below
run_pipeline.py        Headless CLI the launcher drives (presets + flags)
build_master.py        Build tool: assembles modules/ into master.py
verify.py              Release verification: the six checks every change runs
master.py              GENERATED single-file pipeline — do not edit by hand
ui.py                  Streamlit front end (optional): configure, run, inspect
ui_meta.py             Config introspection + curation for ui.py
modules/
    catalog.py         Stage 1 — asteroid catalog
    mineral_value.py   Stage 2 — mineral prices + densities
    transportation.py  Stage 3 — launch / propellant / Δv / ops costs
    calc.py            Stage 4 — profitability calculation
```

`run.bat`, `run_pipeline.py`, `ui.py` and `ui_meta.py` sit at the root rather
than in `modules/` on purpose:
`build_master.py` concatenates everything in that directory into `master.py`
and asserts a specific header/footer shape on each file. All four are
consumers of the built `master.py`, not stages of it.

Each module is a standalone file: run it directly to build just that stage, or
import it for its functions without triggering a run. They share no Python
imports — stages hand off through CSVs on disk, not through each other's
namespaces (see [Stage dependencies](#stage-dependencies)).

| Stage | Module | Version | What it does |
|-------|--------|---------|--------------|
| 1 | `modules/catalog.py` | 1.1.1 | JPL SBDB + MP3C + SsODNet ssoBFT + NEOWISE; merge, dedupe, validate, enrich with per-spectral-type PGM factors |
| 2 | `modules/mineral_value.py` | 1.7.1 | Live yfinance futures, USGS/LME reference prices, in-pipeline mineralogy, destination pricing for every commodity, per-destination ISRU discounts |
| 3 | `modules/transportation.py` | 1.12.1 | 36 launch vehicles (incl. non-rocket concepts), 41 propellants with storage class and tankage, Δv segments (incl. the delivery ladder above LEO), operational costs, storage systems |
| 4 | `modules/calc.py` | 1.17.7 | Per-asteroid Δv **and mission architecture** — and, by default since 1.17.0, **programme size, fleet size and schedule** — in-space delivery, beneficiation, rocket-equation mass cascade (incl. tankage) + cost cascade → net profit, ROI, $/kg-returned |

⚠️  That version column is checked against the modules' own `pipeline_version`
fields, and it has rotted before: it read catalog 1.1.0 / transportation 1.12.0
/ **calc 1.16.0** until 2026-08-21, when calc was four releases past it. The
authority is the dataclass field in each module, never this table.

## Running it

### On Windows: double-click `Dashboard.vbs`

That opens the dashboard in your browser with **no terminal window at any
point**. A small control panel appears while the server boots -- it says what
is happening, opens the browser once the port actually answers, and stops the
server when you close it. That window is what you close when you are done.

It installs Streamlit on first use if you do not have it, reuses the dashboard
it started earlier rather than opening a second one, and writes the server's
output to `.launcher/dashboard-<port>.log` so a failed start is still
diagnosable with no console to have watched it.

**The dashboard opens ready to re-run Stage 4 and nothing else.** Stages 1-3
each re-fetch live data and overwrite the only copy of their CSV on disk, so a
cached stage starts unticked and the destination selector is preselected to
whatever the catalog on disk is already priced for. Tick a fetching stage and
it tells you what that will overwrite. This is the loop you want almost every
time: the catalogs are expensive to rebuild and Stage 4 is the stage whose
answer you are actually changing.

Why a `.vbs` and not a `.bat`: cmd creates its window before the first line of
a batch file runs, and a shortcut set to "Minimized" still puts one on the
taskbar. Windows Script Host is the only launcher that can start a process with
no window at all. It decides nothing itself -- which port, whether a
dashboard is already up, what to do when Streamlit is missing, all of that
lives in `launch_ui.py` where it can be read and tested.

### On Windows, from a terminal: `run.bat`

`run.bat` is the whole pipeline behind a menu -- the same dashboard, plus the
headless runs, verification and the build. It finds Python, offers to install
anything missing, and dispatches. It takes an argument if you would rather skip
the menu:

```
run.bat ui         open the dashboard (hands off to Dashboard.vbs, then
                   closes this window -- no terminal stays up)
run.bat quick      400-row sample, all four stages
run.bat rerun      Stage 4 only, against the catalogs already on disk
run.bat standard   20,000-row sample, Stage 4 only
run.bat full       THE PIPELINE DEFAULTS (HOURS TO DAYS)
run.bat verify     verify.py against the committed baseline
run.bat build      rebuild master.py from modules/
```

It is a launcher and nothing else — every path through it goes through
`run_pipeline.py` or `ui.py`, and from there through `master.py`. No model
behaviour lives in it.

⚠️  **The presets exist because the pipeline's own defaults are a very long
run.** Since calc v1.17.0 a configure-nothing run is the full 1.55 M-row
catalog, beneficiated, with the programme search on — a cell nobody has ever
measured end to end, whose measured neighbours put it in the tens of hours.
That is the right default for the model and a hostile one for a double-click,
so `quick` and `standard` cap the rows and fly run-of-mine ore at N = 1. The
row cap is a **stride sample across the whole belt**, not the innermost N
bodies — see calc v1.13.0.

**`full` is the only preset that overrides nothing**, and every run says so
explicitly: each setting is printed marked `[default]`, or
`[default: <the value it replaced>]`, so a run is never ambiguous about which
question it answered.

```
  Destination  : cislunar             [default: earth_surface]
  Asteroids    : all (1.55 M)         [default]
  Stage 4 rows : 400 (stride sample)  [default: every row]
  Ore          : run-of-mine          [default: beneficiated (~7x slower)]
```

Those labels are read from the config dataclasses at runtime, not hardcoded, and
`run_pipeline.py` warns on stdout if `full` ever stops matching the declared
defaults — so flipping a default in a module cannot leave the label behind.

The launcher also sets the **delivery destination in one prompt**, which
`run_pipeline.py` writes through `MASTER_CONFIG` so Stage 2 and Stage 4 cannot
disagree.

### Headless, on any platform

`run_pipeline.py` is the launcher's engine and works on its own:

```bash
py run_pipeline.py --preset quick
py run_pipeline.py --destination cislunar --raw --no-search --rows 5000
py run_pipeline.py --stages 4 --destination cislunar --preset full --yes
py run_pipeline.py --help
```

`--stages` takes digits, so `--stages 4` reuses the CSVs already on disk for
the other three — the normal working loop, and what saves the 224-second
catalog rebuild.

**Give `--stages 4` an explicit `--destination`.** Stage 2 decides what a
kilogram sells for and Stage 4 decides the architecture that puts it there, so
the two must agree — and both configs default to `earth_surface` while the
catalog on disk is whatever destination was last priced. A Stage-4-only run
that disagrees is refused before it starts, with the destination the catalog
actually holds named in the message, so this costs you one flag rather than a
wasted run.

### From source

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

### The UI

There is an optional Streamlit front end for editing config, running stages and
browsing results:

```bash
pip install -r requirements-ui.txt
```

```bash
py -m streamlit run ui.py
```

It imports `master.py` (side-effect free, since the auto-run is guarded on
`__name__`) and drives `MASTER_CONFIG`, so it is exactly the documented way to
tune the orchestrator, with a browser attached. Three things worth knowing:

- **Every config field is introspected**, not hand-listed, so a field added to
  any of the four dataclasses appears automatically. The help text on each
  field is scraped from that field's own comment block in the module source.
  A curated ⭐ Common tab pins the dials that actually move results.
- **Stages are individually selectable and reuse the CSVs on disk.** Re-running
  Stage 4 alone against a cached catalog is the normal working loop, and it
  saves the 224-second catalog rebuild a full run repeats. Pair it with
  `eval_row_cap` — at the v1.1.0 catalog size an uncapped Stage 4 is hours, and
  since calc v1.13.0 a capped one is a representative sample of the whole belt
  rather than the innermost N bodies. Skipping Stage 2
  after changing the destination is blocked rather than merely warned about,
  because a mineral catalog priced for one destination and a mission flown to
  another produces meaningless numbers that still look plausible.
- **Each run writes `ui_run_config.json`** beside the outputs: the full config
  snapshot, the stages run, and the diff from defaults. `pipeline_version`
  identifies the code that produced a CSV but not the configuration, and this
  repo's recurring failure is a number nobody can trace.

The UI ranks by `total_cost_usd / gross_value_usd` rather than `profit_usd`,
for the reason given in [Reading `profitability_catalog.csv`](#reading-profitability_catalogcsv).
It reads and displays only; every number still comes from the pipeline.

### Stage dependencies

Stages 1, 2 and 3 are independent of each other and can be run in any order or
alone. **Stage 4 is not** — `modules/calc.py` reads the CSVs the other three
wrote, so it needs a populated `output_dir` before it will do anything. Run the
full `master.py` at least once, or run stages 1–3 individually first.

### What a first run costs

> ⚠️  **These figures changed by more than an order of magnitude in catalog
> v1.1.0.** Every row cap now defaults to unlimited, and the catalog went from
> 89,367 asteroids to **1,554,400**. A default end-to-end run is no longer a
> coffee break — budget an afternoon, and set the caps if you want the old
> behaviour back.

- **Stage 1** takes **224 s** at the unlimited default and writes a **0.88 GB**
  CSV (measured 2026-08-08, warm SsODNet cache, ~6 GB peak RAM). The JPL pull
  alone is 1,554,321 asteroids / 401 MB / 24 s. Set `jpl_limit = 50_000` to
  reproduce the pre-v1.1.0 couple-of-minutes, ~30–40 MB run.
- SsODNet's ssoBFT table is a **~500 MB parquet bulk download** on first run.
  It is cached and re-used for `cache_max_age_days` (7 by default). The cache
  lives in the system temp directory, deliberately *not* under `output_dir` —
  on a Google Drive working copy that keeps half a gigabyte from re-syncing
  every run. Point `CATALOG_CONFIG.cache_dir` somewhere else if you want it
  co-located.
- **Stage 4 is now the long pole by far**, because `eval_row_cap` defaults to
  `0` (evaluate everything) and "everything" is 1.55 M rows. Measured at
  cislunar on six physical cores / 12 workers: **2,539 s raw** (42 min,
  668,004 evaluable rows, 1.06 GB output). Beneficiated is *estimated* at
  ~2.2 h and is not yet measured. Set `eval_row_cap` for anything
  interactive — as of calc v1.13.0 a capped run is an evenly-spaced sample of
  the whole belt rather than the innermost N bodies, so it is actually
  representative.
- **The two big dials, if a full run is more than you want:**
  `catalog.jpl_limit` bounds how many asteroids exist, and
  `catalog.derive_diameter_from_h = False` drops the catalog from ~1.55 M to
  ~149,600 by keeping only bodies with a *measured* diameter.
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
| `.catalog.jpl_limit` | `0` | Asteroids fetched from JPL; `0` = all 1,554,321. The only source of orbital elements, so it bounds the catalog |
| `.catalog.ssodnet_limit` / `neowise_limit` / `mp3c_limit` | `0` | Per-source caps, `0` = unlimited. One shared cap until v1.1.0, which made the catalog smaller than any single source |
| `.catalog.derive_diameter_from_h` | `True` | Size bodies with no measured diameter from H + an assumed albedo. `False` → ~149,600 rows instead of ~1,554,400 |
| `.catalog.min_derived_diameter_km` | `0.0` | Floor on *derived* diameters only. Trims the sub-km tail, where the albedo assumption hurts most |
| `.catalog.min_diameter_km` | `0.001` | Size floor. Raise to `1.0` to study km-class bodies only |
| `.catalog.require_spectral_type` | `False` | `True` drops untyped rows — fewer asteroids, but every one has a composition |
| `.catalog.use_jpl` / `use_mp3c` / `use_ssodnet` / `use_neowise` | all `True` | Per-source toggles. Turning off SsODNet skips the 500 MB download |
| `.calc.eval_row_cap` | `0` | Stage-4 evaluation cap; `0` evaluates every row. Was `5_000`, which discarded 99.7% of a v1.1.0 catalog |
| `.calc.eval_row_sampling` | `"stride"` | How a cap picks rows. `"stride"` samples the whole belt evenly; `"head"` is the pre-v1.13.0 innermost-N behaviour |
| `.calc.parallel_workers` | `0` | Stage-4 worker processes. `0` picks a count from the CPU count and the amount of work; `1` forces the single-core path. See [Parallel evaluation](#parallel-evaluation) |
| `.calc.max_mining_fraction` | `0.05` | Share of asteroid mass one mission may remove |
| `.calc.use_aerocapture_return` | `True` | Makes aerocapture *available*. Trades return Δv for a TPS mass penalty (15% of payload); Stage 4 prices both and flies whichever pays, per asteroid |
| `.calc.use_isru_return_propellant` | `True` | Makes ISRU *available* at bodies whose composition supplies the propellant, with the extra rock dug, timed and charged |
| `.calc.operational_propellants_only` | `True` | Restrict the search to propellants that have flown. `False` admits Stage 3's development and concept rows — nuclear thermal, VASIMR, fusion, Orion pulse |
| `.calc.model_tank_mass` | `True` | Put propellant tankage in the rocket equation. Tank mass scales with volume, so this is what stops low-density propellants flying their tanks for free |
| `.calc.allow_rtg_power` | `True` | Let the processing plant use radioisotope power where it is lighter than solar (past 3.46 AU), capped by `rtg_max_power_w` |
| `.calc.charge_tanker_flights` | `True` | Charge the orbital-refuelling flights a vehicle's escape payload assumes |
| `.calc.optimise_architecture_per_asteroid` | `True` | Search return mode and propellant sourcing per target rather than fixing them catalog-wide |
| `.calc.selection_objective` | `"cost_revenue_ratio"` | What the per-asteroid search maximises. `"profit"` restores pre-v1.10.0 behaviour |
| `.calc.return_structure_frac_of_payload` | `0.15` | Return-vehicle structure as a fraction of the haul, on top of the 500 kg base |
| `.calc.nre_amortization_missions` | `1` | Programme size N. With the search on it is the FLOOR rather than the answer |
| `.calc.optimise_programme_scale` | `False` | Search programme size and fleet size per asteroid instead of setting N. Changes the question the run answers, so it is off by default — every figure here is off, at N = 1 |
| `.calc.max_fleet_ships` | `64` | Where the fleet ladder stops. Rows piling up against it mean their payloads have no finite market, not that bigger is better — the run says so |
| `.calc.programme_search_steps` | `8` | Rungs in the coarse fleet sweep, before one refinement pass. Same idiom as `concentration_search_steps` |
| `.calc.model_rig_trip_limit` | `True` | Cap rig life in duty CYCLES as well as calendar years. Inert at N = 1 |
| `.calc.model_programme_calendar` | `True` | Charge the calendar a programme actually spans — the NRE and rig are bought once and carried across every campaign. Inert at N = 1; also what makes the programme search two-dimensional |
| `.calc.contingency_fraction` | `0.20` | Flat contingency on the cost cascade |
| `.calc.apply_wacc_compounding` | `True` | Time-value of money, bucketed by when each cost is incurred |
| `.mineral.metals_api_key` | `"DEMO"` | Set a real metals.dev key to enable that source; `"DEMO"` silently skips |

`use_isru_return_propellant` and `use_aerocapture_return` changed meaning in
Stage 4 v1.10.0. They used to *force* an architecture on the whole catalog;
they now say it is **available**, and Stage 4 prices every feasible
combination per asteroid and flies the one that pays. ISRU is additionally
gated on physics — the propellant has to be makeable from what the body is
actually made of — and the rock it takes is dug, timed and charged like any
other feed.

Stage 4 v1.11.0 widened what "makeable" means. v1.10.0 allowed hydrolox and
nothing else, which was right about the chemistry it knew and wrong about the
question: electrolysing water into cryogenic hydrogen and oxygen is the
*hardest* thing you can do with asteroid water. A steam rocket boils it and
thrusts on the vapour at **1.00 kg of water per kg of propellant** against
hydrolox's 1.286, with no electrolyser, no liquefaction and no cryogenic tank
— and buys that at 190 s of specific impulse against 452. Which trade wins
varies by body, so it is resolved in the per-asteroid search rather than
assumed. Stage 3 states the feed ratio and the feed material on each
propellant row.

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

### Parallel evaluation

Stage 4 evaluates each asteroid independently of every other one, so since calc
**v1.10.1** it does that across a process pool instead of on one core. On a
6-core / 12-thread machine a full beneficiated destination went from ~2,120 s
to **137 s**, and raw from ~140 s to **33 s**.

**No number changes.** v1.10.1 is a performance release and its output was
bit-identical to v1.10.0's — verified by sha256-diffing serial against parallel
CSVs over the same rows, and by reproducing the then-committed cislunar cells
from the full catalog (22.9336× beneficiated, same winner and concentration
ratio; 31.8269× raw). Chunks are consumed in submission order specifically so
that the row order, and therefore the ordering of `profit_usd` ties under a
non-stable sort, is unchanged.

⚠️  **Both the timings and the cislunar figures in the two paragraphs above
belong to v1.10.1 and the old 89,367-row catalog.** v1.11.0 made the search
4.6× wider (357 combinations per asteroid against 77), catalog v1.1.0 then made
the catalog 17× bigger, and v1.14.0 added a power-source search axis. None of
that is a performance regression. As of 2026-08-09 a full cislunar destination
measures **5,350 s raw / 38,072 s beneficiated**, and the cislunar cells are
**26.7863× / 20.5895×**. Current timings are in
[Beneficiation](#beneficiation).

Roughly 1.9× of the gain is single-threaded and applies even at
`parallel_workers = 1`: catalog rows are converted to plain dicts before the
inner search (pandas resolved ~7,400 index lookups per asteroid, ~38% of the
whole run), and the sizing loop's five Stage-3 constants are memoised rather
than looked up ~24 million times.

Leave `parallel_workers` at `0` unless you have a reason:

- **`1`** forces the serial path — for profiling, or when an outer harness is
  already running one process per destination and the cores are spoken for.
- **A specific count** is obeyed, clamped to the CPU count.

Auto mode will not start a worker that cannot repay its own startup, so short
interactive runs stay serial. That matters more than it sounds: startup is
~1.1 s per worker and **linear**, because each worker re-imports the 590 kB
`master.py` (Windows has no fork), and on a Google Drive working copy those
reads serialise. At 3,000 beneficiated rows, twelve workers is slower end to
end than six. The useful ceiling is the **physical** core count — hyperthreading
adds ~17% on this branch-heavy pure-Python workload, not 2×.

One trap worth knowing if you extend this. A spawned worker rebuilds the parent
by importing `__main__`, and under Streamlit `__main__` is a synthetic module
whose `__file__` points at `ui.py` — so a plain `Pool()` executes the entire
Streamlit app once per worker. `_spawn_environment` in `modules/calc.py`
repoints `__main__.__spec__` at the pipeline module to prevent it, and sets an
env var that keeps the workers' re-import from replaying the startup banner
sixty lines at a time into the run log the UI is parsing.

**That guard has a precondition, and it fails silently when it is not met.**
It finds the module to point at with `sys.modules[__name__]`, so `master.py`
has to actually be in `sys.modules` under its own name. Loading it with
`importlib.util.spec_from_file_location(...)` + `exec_module(...)` — the
obvious way to write a measurement harness against an absolute path — never
registers it, the pin quietly does not happen, and every worker falls back to
executing your harness as `__main__` instead. If your driver script re-runs
itself once per worker, this is why. Put the repo on `sys.path` and
`import master` by name:

```python
sys.path.insert(0, REPO)
import master as m
assert sys.modules.get("master") is m and m.__spec__ is not None
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

## Verifying a change

Almost every release of Stage 4 is argued from **bit-identity**: the claim is
not "the numbers look right", it is "these are the same floats, and here is the
hash". `verify.py` is those checks, committed:

```bash
py verify.py baseline --tag 1.17.7
```

Run that on a clean tree **before** editing. It builds four cells — raw and
beneficiated, each with the programme search off and on — and writes their CSVs
and hashes under `.verify/` (gitignored). Then make the change, rebuild, and:

```bash
py verify.py check --tag 1.17.7
```

which runs all five:

| # | check | catches |
|---|---|---|
| 1 | bit-identity vs the baseline | any change to any number, column by column and by hash |
| 2 | pre-filter on vs off | the pruner and the solver drifting apart — they are two statements of one algebra |
| 3 | serial vs 8 workers | a worker seeing different reference data from its parent |
| 4 | mass ledger | a kilogram in the rocket equation with no price in the ledger |
| 5 | never-worse | a search optimising something other than what it reports |
| 6 | Stage 2 tables | a judgement-table edit that moved a number, or a commodity falling through a silent default |

`py verify.py invariants` runs 4, 5 and 6 only and needs no baseline, so it
works on any tree and is the fast way to check an upstream table edit;
`--cells` takes a subset.

⚠️  A full `check` builds about twenty cells and takes **roughly half an hour**.
Most of that is check 2 — turning the pre-filter off is exactly what v1.14.1 and
v1.17.4 exist to avoid, so an unpruned cell runs the entire search. Iterate with

```bash
py verify.py check --skip prune parallel
```

which is ~5 minutes and still catches any change to any number, then run the
full set once before committing. A verification you will not run is worse than
a slow one.

**Why it is committed rather than rewritten each time.** Before 2026-08-21
every release built these checks from scratch and threw them away, and
`CLAUDE.md` records eleven harness bugs that came out of it — three of which
produced conclusions that were written down or acted on before being caught:
a comparison that stripped only one of the two provenance columns, so midnight
falling mid-run read as a defect in the beneficiation path; two cells recorded
as `cislunar` that had actually run against `earth_surface` prices; and a
column diff that reported 64 of 139 columns as differing against a file that
hashed byte-identical. Each of those traps is now defended against at the line
that would otherwise reproduce it, and `verify.py`'s header lists all eleven.
Add to that list rather than starting a twelfth harness.

That last one is worth knowing about before you write any comparison of your
own, because it had **three independent causes** producing one identical
symptom, and fixing each moved the count and nothing else:

1. pandas aligned two Series on the index **label**, and
   `build_profitability_catalog` returns rows sorted by the objective, so a
   live frame's index is scrambled against a CSV's fresh `RangeIndex`;
2. `read_csv`'s default float parser is fast rather than correctly rounded, so
   values came back one ULP off — only `float_precision="round_trip"` fixes it;
3. an all-empty object column writes as bare commas and reads back as
   float64-of-`NaN`, so a live `""` met a `nan`.

It is also why the report prints **both** a hash and a column diff: when they
disagree, the hash is the one that is right, and the disagreement is itself the
signal that the comparator is broken rather than the release.

The four hashes it prints reproduce the ones committed for calc v1.17.4 and
v1.17.6 exactly, which is what makes it a replacement for those harnesses
rather than another one to have to trust.

⚠️  **It covers Stage 4 and nothing else.** It does not re-run Stages 1–3,
deliberately: a Stage 1 run fetches a different catalog (JPL adds bodies daily)
and a Stage 3 run re-fetches live metal and fuel prices, either of which would
move the inputs underneath the comparison and invalidate every baseline in the
same session. The consequence is that **a change to an upstream module can pass
every check here and still be wrong** — v1.12.1's propellant-flag fix lives in
Stage 3's `validate()`, which Stage 4 never calls, and had to be checked by
running that function under `-W error::FutureWarning` instead. If you change
Stage 1, 2 or 3, this file is not your evidence.

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
    asteroid_catalog.csv               ← Stage 1 (~0.88 GB at the 1.55M default;
                                          ~30–40 MB at jpl_limit = 50_000)
    rejected_entries.csv               ← Stage 1 (validation rejects)
    mineral_value_catalog.csv          ← Stage 2
    transportation/
        launch_vehicles.csv            ← Stage 3
        propellants.csv                ← Stage 3
        delta_v_segments.csv           ← Stage 3
        operational_costs.csv          ← Stage 3
        storage_systems.csv            ← Stage 3 (new in 1.9.0)
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
way worth understanding.

Cislunar, beneficiated, rebuilt 2026-08-07 on calc v1.10.0 + mineral_value
v1.7.0. It sat at Mars until then; the curve belongs at whichever destination
is the best case, and that is no longer Mars:

| Programme | `p_mining` | `P(success)` | Missions sharing one rig | Best cost/revenue | Winning vehicle |
|---|---|---|---|---|---|
| 1 mission | 0.850 | 0.646 | 1 | 22.93× | Falcon Heavy |
| 10 missions | 0.902 | 0.708 | 4 (capped) | 9.85× | New Glenn |
| 100 missions | 0.943 | 0.739 | 4 (capped) | **7.28×** | New Glenn |

> 🚨  **THE SHAPE OF THIS TABLE IS WRONG, not just its levels.** It was
> measured on a model in which market saturation could not see
> `nre_amortization_missions` at all — so a 100-mission programme divided its
> NRE by 100, grew its reliability, and sold 100 payloads at the price **one**
> payload commands. Every lever pointed the same way and nothing pushed back,
> which is exactly what that term was written to prevent.
>
> Fixed in v1.14.0: the rate is the programme's **concurrent** output,
> `ceil(N / missions_sharing_rig)`. Exactly 1 at N = 1, so no single-mission
> figure moves. On a 6,000-row raw cislunar sample the curve stops being
> monotone and **turns**:
>
> | N | v1.13.0 | **v1.14.0** | concurrent | saturation multiplier |
> |---|---|---|---|---|
> | 1 | 38.4050× | 38.7886× | 1 | 0.7451 |
> | 10 | 16.0296× | **16.4745×** | 1 | 0.7773 |
> | 100 | **10.8935×** | **20.3246×** | 10 | **0.4279** |
>
> **The optimum programme size is interior, around N = 10.** "Fly more
> missions" is not an unbounded lever and never should have looked like one.

#### Rebuilt on the full catalog, 2026-08-10 — cislunar, raw

All 1,554,400 rows, calc v1.14.0. N = 1 is the measured headline cell; N = 10
and N = 100 are separate full runs against the same catalog and Stage 2 pass.

| N | best cost/revenue | `p_mining` | saturation multiplier | concurrent missions | rig serves | winner | vehicle / propellant | payload |
|---|---|---|---|---|---|---|---|---|
| 1 | 26.7863× | 0.850 | 0.6873 | 1 | 1 | 2021 CX5 (D) | New Glenn / xenon | 93,312 kg |
| 10 | **13.5836×** | 0.902 | 0.7785 | 1 | 10 | 2002 AT4 (D) | New Glenn / krypton | 42,597 kg |
| 100 | 18.3605× | 0.943 | 0.5423 | **9** | 12 | 2021 CX5 (D) | H3 (24L) / iodine | 19,495 kg |

**The curve turns, and the optimum is interior** — −49.3% at N = 10, then back
up to −31.5% at N = 100. Scale still helps overall; it just stops helping
monotonically.

Why, reading the columns:

- **At N = 10 nothing is concurrent.** One rig serves all ten missions back to
  back, so `concurrent_missions` is still **1**, the market never sees two
  payloads at once, and the saturation multiplier actually *improves* (0.6873 →
  0.7785). NRE per mission falls 10×, `p_mining` grows 0.850 → 0.902. Every
  lever points the same way — which is why the pre-v1.14.0 model looked
  plausible here.
- **At N = 100 the rig cap binds.** One rig serves 12 missions at this stay
  length, so a hundred-mission programme needs ⌈100/12⌉ = **9 rigs flying at
  once** and the multiplier collapses to 0.5423. That is the turn.

Two things not to read as constants: **the rig cap is 12 here, not the 4 of the
older curve** (it is `life / stay`, and this winner flies 4.2–4.4 yr), and **the
winning vehicle gets *smaller* with scale** — New Glenn → New Glenn → H3 (24L),
with payload falling 93,312 → 42,597 → 19,495 kg. Saturation punishes volume,
so at programme scale the model prefers more, smaller missions. The old model
could not express that, because saturation could not see N at all.

⚠️  Three points, so "near N = 10" is the lowest of the points sampled, not a
located optimum. And this is the **raw** curve — the beneficiated one above is
not superseded by it, it is simply unmeasured (~21 h for the pair).

> ✅  **v1.15.0 locates the optimum instead of sampling it**, and three points
> was never the right tool: **the best N is always an exact whole multiple of
> the rig's trip life**, so 1 / 10 / 100 sample a grid whose points mostly
> cannot be optimal. Within one fleet band the concurrent output — and so the
> saturation multiplier — is constant while NRE/N, the learning curve, the rig
> share and `p_mining` all improve, which puts the band's best at its top,
> N = F × trips.
>
> So `optimise_programme_scale` searches the **fleet** and lets N follow. It
> costs **2.98× runtime, not 12×** — measured on the full raw cislunar cell,
> 1,307 s → 3,890 s, on the two-dimensional v1.16.0 search; v1.15.0's
> one-dimensional ladder measured 1.51× and that figure does not carry over —
> because programme size touches nothing
> in the mass cascade — the rocket equation, the power fixed point, the payload
> knapsack and the concentration sweep are all solved once per candidate and the
> whole ladder is priced off the result.
>
> On a 2,500-row raw cislunar sample it moves the best cell **42.0081× →
> 21.7341×**, choosing fleets of 1–8 ships (N = 5–40). ⚠️  That is a sample, and
> turning it on changes the question from "the best single mission to this rock"
> to "the best programme built around it". Almost every figure in this README is
> the former.
>
> 🚨  **"default OFF" was true until calc v1.17.0 — it is now default ON**,
> along with `use_beneficiation`. Set both False to reproduce the tables in this
> README. The full cislunar 2×2 is measured on the full catalog and both
> search-OFF cells reproduce exactly; see
> [Combined effect](#combined-effect).
>
> 🚨  **v1.16.0 RETIRES THE BAND ARGUMENT IN THAT PARAGRAPH.** "Within one fleet
> band every lever improves and none pushes back" was true of a model in which
> a programme took no time. Charging programme calendar time adds the lever that
> pushes back — it grows like `y^W` against NRE/N falling like `1/N` — so
> campaigns-per-ship has an interior optimum and the band's top is often not it.
> The search is now two-dimensional over (fleet × campaigns-per-ship), with the
> second dimension **enumerated exhaustively** rather than laddered, because it
> is at most five integers. Measured on a 400-row raw cislunar sample: the
> searched cell goes **31.0693× → 33.7977×** (+8.8%), the median fleet grows
> from **1 ship to 2**. Still inert at N = 1.
>
> ⚠️  **The "12 of 168 bodies decline to use up the rig" figure that used to end
> that sentence was the STALE-TABLE variant and did not belong here.** It comes
> from re-running the sample against the archived 43-row Module 3 ops table, in
> which the v1.15.0 trip cap is absent and `trips` reaches 20. On the **current
> 44-row table** the sample gives W = `trips` on all 168 rows, which is why
> CLAUDE.md records the 2-D search as "necessary but not yet load-bearing".
>
> ✅  **Settled on the full catalog, 2026-08-11: W < `trips` on 2,077 of 650,921
> rows (0.319%).** The effect is real on the current table and simply too rare
> for 400 bodies to show. The search is load-bearing; the sample could not see
> it.

⚠️  **This curve has also not been rebuilt since v1.11.0.** Its N = 1 anchor is
the old 22.93×; that cell measured 22.4665× on v1.11.0 and now measures
**20.5895×** on v1.14.0, so the levels are ~10% optimistic on top of the shape
problem above. `p_mining` and the rig cap are the two columns that do carry
over — `p_mining` is a function of N alone, and the rig cap is a property of
the mission profile.

Going from 10 to 100 missions buys much less than going from 1 to 10, and the
reason is the rig service-life cap: at this stay length one rig serves four
missions, so the 5th buys a whole new rig. NRE keeps amortising, reliability
keeps growing, but the hardware does not get cheaper past that point.

⚠️  **That cap was a calendar, and it was doing less work than it looks.**
"Mining rig service life" is 15 **years** — corrosion, thermal cycling,
radiation — and dividing it by the stay was the only bound on how many missions
one rig served, so at a short stay it stretched to twelve consecutive digs.
Nothing bounded duty cycles. v1.15.0 adds Module 3's "Mining rig maximum trips"
(5, a documented judgement) and takes the min, so short-stay missions are now
cycle-limited and long-stay ones stay calendar-limited. Inert at N = 1 — the
same 60.9284× either way on a 400-row sample — so no figure in this README
moves for it.

That is the honest shape of the "just fly more missions" argument — real, but
sublinear, and bounded by market saturation at the far end. Note it does not
reach viability: a hundred-mission programme to a cislunar depot still loses
about seven dollars for every one it earns.

Two details worth not mistaking for constants. The rig cap is `life / stay`, so
**4 here where the old Mars curve read 7** — it is a property of the
destination's mission profile. And the winning vehicle **switches** from Falcon
Heavy to New Glenn at N ≥ 10: once NRE is spread across a programme, the
per-mission launch bill stops dominating and a bigger vehicle starts paying.
`p_mining` is the one column that carries over unchanged (0.850 / 0.902 /
0.943), because Duane/AMSAA growth is a function of N alone.

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

## The propulsion and storage catalog

Stage 3 v1.9.0 rewrote the reference tables to hold the field rather than a
sample of it. The previous tables held what somebody had happened to list, and
the omissions were not random — everything missing was either an option the
search never got to consider or a cost the model never got to charge.

### Propellants — 40 rows

Each carries specific impulse, blended density, $/kg, boil-off rate, a
low-thrust Δv penalty, and (new in v1.9.0) a **storage class**, a derived
**tankage mass**, a maturity **status**, and whether the asteroid itself can
supply it.

| Status | Count | Rows |
|---|---|---|
| operational | 23 | kerolox, hydrolox, methalox, MMH/NTO, UDMH/NTO, Aerozine-50/NTO, hydrazine, green monoprop (ASCENT), HTP mono + bi, cold gas, solid APCP, xenon, krypton, argon, iodine, water electrothermal, water ion, hydrazine arcjet, electrospray, FEEP, PPT, solar sail |
| development | 7 | nuclear thermal, nuclear electric, solar-thermal H2, solar-thermal steam, VASIMR, MPD, metal/water (ALICE) |
| concept | 9 | Li/F2/H2, CO/LOX, mass driver, Orion nuclear pulse, direct fusion drive, antimatter, magsail/e-sail, momentum tether, beamed laser-thermal |
| retired | 1 | mercury ion — banned under the Minamata Convention |

**Only the 23 operational rows are in the default search, and only 21 of those
can fly this mission profile.** Solid APCP is excluded because it cannot be
relit for a return burn years later; the solar sail because it is
propellantless and the rocket equation would report that it moves any payload
for free. Set `operational_propellants_only = False` to admit the rest — but
understand that a profit-maximising search will then fly every asteroid on
antimatter, which is why the gate exists.

Three of the additions matter more than the row count suggests:

- **Krypton** is, by unit count, the most-flown electric propellant in history
  — every Starlink v1.0 Hall thruster ran it — and it was absent. It is 30×
  cheaper than xenon at two-thirds the Isp, and it pays for that with a much
  worse tank (0.55 kg/L supercritical against xenon's 2.0, so 12.5% of its own
  mass in COPV against 1.9%).
- **Iodine** stores as a *solid* at ambient pressure, ρ 4.93 kg/L, so its
  reservoir is 0.2% of the propellant it holds — the best storage density of
  anything flying. ThrustMe flew it in 2020. It wins a large share of targets
  in the current model precisely because of that.
- **Water, electrothermally heated**, is the propellant the idea of a
  self-refuelling mining craft actually rests on: 1.00 kg of asteroid water
  per kg of propellant against hydrolox's 1.286, with no electrolyser and no
  cryogenic tank, at 190 s of Isp against 452. Honeybee's WINE demonstrated
  the full mine-boil-thrust loop in a vacuum chamber in 2018.

### Storage classes and tankage

Tank mass scales with the **volume** enclosed, not the propellant mass inside
it. `tank_kg_per_L` is derived per class — a flight-anchored multiple of
0.025 kg/L for the unpressurised classes, and `1.5·p/(PV/W)` off a 40 km COPV
performance factor for the pressurised ones.

The percentage column below is therefore a *consequence* of the named
propellant's density, not a property of the class: two propellants in the same
class pay different fractions if they store at different densities, which is
the whole point of putting volume in the model.

| Storage class | Named propellant | Tank as % of that propellant's mass |
|---|---|---|
| sublimating solid | iodine (4.93 kg/L) | 0.2% |
| supercritical gas, 10 MPa | xenon (2.0 kg/L) | 1.9% |
| storable liquid | MMH/NTO (1.16 kg/L) | 2.2% |
| benign liquid | water (1.0 kg/L) | 2.3% |
| mild cryogen | LOX (1.14 kg/L) | 2.5% |
| solid motor | APCP (1.80 kg/L) | 6.9% — Star 48B measures 6.4% |
| deep cryogen, blended | hydrolox (0.361 kg/L) | 9.7% — Centaur III measures ~9.7% |
| supercritical gas, 18 MPa | krypton (0.55 kg/L) | 12.5% |
| supercritical gas, 30 MPa | cold gas N2 (0.25 kg/L) | 46% |
| deep cryogen, neat | LH2 for NTP (0.0708 kg/L) | 53% |

### Launch vehicles — 36 rows

17 operational and Earth-based (the default search), plus development vehicles
(Neutron, Terran R, Nova, Eclipse, Zhuque-3, Tianlong-3, Long March 9 and 10,
Starship), two retired, and eight **non-rocket** concepts.

On the non-rocket rows, read `max_accel_g` before the price. SpinLaunch is
~10,000 g and a light-gas gun ~30,000 g: that passes propellant, water and
steel billets and destroys every mining rig, optic, reaction wheel and radio
in the catalog. They do not have a cost problem, they have a payload problem,
and this pipeline cannot represent a split manifest.

The lunar mass driver and lunar space elevator are excluded structurally
rather than by maturity — Stage 4 departs from Earth, and their payload
columns are annual throughput, so reading them would be a unit error. The
**lunar elevator** is the one worth not dismissing: unlike Earth's it needs no
new material, because the Moon's shallow gravity well and the Earth-Moon L1
balance point put the required specific strength inside what Zylon and M5
already deliver (Pearson 1979; Eubanks & Radley 2016).

### Storage systems — 20 rows

A new `storage_systems.csv`, covering four domains that had previously been
represented by a single column:

- **propellant** — the tankage constants above, MLI, vapour-cooled shields,
  and zero-boil-off cryocoolers (80 W of input per W lifted at 20 K, ~5 kg/W)
- **cargo** — bulk ore restraint, volatile containment, sintering, dust seals
- **energy** — Li-ion, regenerative fuel cells, flywheels, RTGs, Kilopower-class
  fission, and the eclipse fraction that should be sizing all of them
- **depot** — cryogenic depot boil-off, tanker flights per departure, transfer
  losses, ISRU propellant depots

Stage 4 reads the tankage figures, the RTG rows and the tanker count. It does
**not** read the volatile-containment, eclipse or cryocooler rows — those are
documented gaps, and all three currently run in the optimistic direction. See
[What the model does not capture](#what-the-model-does-not-capture).

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
(Measured 2026-08-07: declines on 1.365%, median ratio 7.41×, maximum 22.2×
against a cap of 50.)

"Can never make a mission worse" is checkable rather than assumed, and as of
2026-08-07 it has been checked: joining the raw and beneficiated catalogs on
`designation` across all five destinations, 165,843 pairs, the beneficiated
cost/revenue is never higher — worst case exactly 1.0000, which is the decline
falling back on the baseline. If that maximum ever exceeds 1.0, the search is
optimising something other than what gets reported.

Costs charged, all of which the search trades against:

- **Time.** Dig time is charged on the *feed*, not the product.
- **Energy and mass.** Stage 3's 200 Wh/kg excavation and 500 Wh/kg
  beneficiation rates over the stay time give a power draw; Stage 3's
  60 W/kg-at-1-AU power-system row, scaled 1/r² by the target's semi-major
  axis, turns that into array mass; the array flies in the same rocket
  equation as everything else. Payload → feed → power → mass → payload is a
  real circular dependency, solved by fixed-point iteration.

⚠️ The search costs runtime: roughly **7× slower** on the beneficiation path.
Current figures, calc **v1.14.0** on six physical cores / 12 workers, the full
1,554,400-row catalog, measured 2026-08-09:

| destination | raw | beneficiated |
|---|---|---|
| `cislunar` | **5,350 s** (89 min) | **38,072 s** (10.6 h) |
| `lunar_surface` | 5,118 s | not run |
| `leo` | 10,063 s | not run |
| `mars_surface` | 10,275 s | not run |
| `earth_surface` | 10,670 s | not run |

The complete raw row is 11.5 h; the whole ten-cell sweep is **~3.5 days**,
including a Stage 2 re-run per destination. Tune with
`.calc.concentration_search_steps`, and cap `.calc.eval_row_cap` for anything
interactive.

⚠️ **Every figure in that table is calc v1.14.0. v1.14.1 made the search 1.7–1.9×
faster and v1.14.2 a further 2.0–2.4×, neither changing any output**, so they are
all high by a compounded factor of roughly **3.4–4.6×** — deliberately not
scaled, because these are measurements and no cell has been re-run on either
release. v1.14.1 skips candidates that provably cannot close
their mass budget instead of re-deriving that fact once per power source and
once per point of the concentration sweep; on the full catalog it prunes
**75.9%** of them. Note that 75.9% pruned is only 1.7–1.9× faster, because the
quarter that survive are the expensive ones. The control is on the Common tab
under **Hopeless candidates**; `.calc.prune_infeasible_combos = False` restores
the v1.14.0 search exactly.

⚠️ **That same switch now controls two stages.** v1.17.4 added a second one that
refutes at pass **2** of the sizing loop — the first pass that carries the
electric stage — and it kills a further **84–86%** of what stage 1 lets
through. Turning the switch off restores the pre-v1.14.1 search, not the
v1.14.1 one.

🚨 **Do not budget these from a sample.** A stride sample has now mispredicted
full-catalog runtime on this pipeline by **3.1× high** (v1.13.0's raw estimate)
and **4.8× low** (v1.14.0's beneficiated estimate — ~2.2 h predicted against
10.6 h measured), for opposite reasons: fixed costs dominate a small run, while
a stride sample under-represents the expensive tail of the concentration sweep.
Budget from a measured full run of the same cell.

The older figures, calc **v1.11.0** on the old 89,367-row catalog, are kept
only because the *ratios between destinations* are still roughly how to reason
about relative cost — the absolute seconds are two orders of magnitude out of
date: cislunar 89 s / 462 s, lunar_surface 84 / 437, mars_surface 158 / 966,
leo 177 / 948, earth_surface 174 / 1,017.

These have moved three times for three unrelated reasons, so always check
which release a quoted timing belongs to:

- **v1.10.0 and earlier** — ~140 s raw / ~2,120 s beneficiated, single core.
  The 2026-08-07 reproduction took about three and a half hours.
- **v1.10.1** — ~33 s / ~137 s. A pure performance release that changed no
  output; see [Parallel evaluation](#parallel-evaluation).
- **v1.11.0** — the table above. Also not a code regression: the search is
  4.6× wider (357 vehicle × propellant combinations per asteroid against 77),
  because the propellant table went from 7 usable rows to 21.

The beneficiated figure has now moved twice, for opposite reasons, and only one
of them touched a result. It was **1,100 s until it was measured again** (ratio
8×), both written before v1.10.0 made the architecture search per-asteroid: the
two searches multiply, because every concentration ratio is priced against
every vehicle × propellant × return mode × ISRU choice × apsis rather than
against one nominal architecture. Two independent runs on 2026-08-07 gave
2,122 s and 2,124 s, so that one was the model getting more expensive rather
than the measurement being noisy. Then v1.10.1 took it to 137 s by using the
other eleven threads and by not looking every catalog row up through a pandas
index a few thousand times per asteroid.

The 1/r² term punishes distant targets hard (cislunar delivery, measured on a
1,959-body pre-v1.0.9 run; the ratios between rows are the point, not the
absolute masses):

| Semi-major axis | W/kg at target | Mean array mass |
|-----------------|---------------|-----------------|
| < 1.2 AU | 51.5 | 4 kg |
| 1.8–2.5 AU | 11.4 | 41 kg |
| > 3.2 AU | 4.7 | 226 kg |

### Combined effect

#### The full cislunar 2×2 — full catalog, calc v1.16.0, measured 2026-08-11

Both settings of beneficiation × both settings of the programme search, at
`cislunar`, on a 1,555,667-row catalog (1,555,618 with positive mass), 12
workers, one Stage 1/2/3 pass. **These supersede the cislunar row of the
destination table below**, which they also reproduce.

| | search OFF (N = 1) | search ON |
|---|---|---|
| **raw** | **26.7863×** | **15.4273×** |
| **beneficiated** | **20.5895×** | **13.1443×** |

Evaluable 650,921 raw / 660,253 beneficiated. Runtimes 1,307 s / 3,890 s raw and
9,300 s / 24,587 s beneficiated — beneficiation is ~7× and the programme search
~3×, so the 2×2 spans **18.8×** in wall clock corner to corner.

**13.1443× is the best cislunar figure this model has produced**, and it is what
calc v1.17.0's two flipped defaults return **at cislunar**. It is still a factor
of 13 from breakeven, so the project's headline is unchanged: **a default run
produces zero viable missions, and that is the correct answer.**

⚠️  It is **not** "the default run" — `delivery_destination` still defaults to
`earth_surface`, so a configure-nothing v1.17.0 run is beneficiated + searched
at `earth_surface`, which has never been measured. Only the two flags moved.

⚠️  The two columns are **not comparable** — one is the best single mission to a
rock, the other the best programme built around it (here: 10 missions, 2 ships,
17 years). The improvement is a change of question, not a saving.

The same body, **2021 CX5** (D-type, 82 m, a = 1.626 AU), wins all four cells on
a New Glenn — while its propellant goes xenon → iodine → iodine → **argon** and
its payload falls **93,312 → 34,573 kg**, which is market saturation preferring
more, smaller missions at programme scale.

**Both search-OFF cells reproduce their committed v1.14.0 values exactly**, four
releases later and on a catalog that has grown by 1,267 bodies — same winner
(2021 CX5, D-type), same vehicle, same propellant, same payload in kilograms,
same concentration ratio, same propellant shares. That is a stronger check than
the byte-identity diffs v1.14.1/v1.14.2/v1.15.0 argued from, because those
compared identical rows and this compares a different population.

As of **calc v1.17.0 the bottom-right cell is what the default FLAGS produce**
(at this destination — the default destination is still `earth_surface`); the
top-left is what almost every other table in this README is. Set
`use_beneficiation = False` and `optimise_programme_scale = False` to reproduce
them.

#### Current results — full catalog, calc v1.14.0, measured 2026-08-09

The 1,554,400-row catalog v1.1.0 (1,554,353 with positive mass), Stage 2 re-run
per destination, transportation v1.11.0, calc v1.14.0, master v1.17.0, on
`master.py` rebuilt from the modules with a clean `git status`. 12 workers.

| destination | raw | evaluable | beneficiated | evaluable |
|---|---|---|---|---|
| **`cislunar`** | **26.7863×** | 650,516 | **20.5895×** | 659,847 |
| `lunar_surface` | 63.3505× | 585,710 | *not measured* | — |
| `leo` | 71.1055× | 776,266 | *not measured* | — |
| `mars_surface` | 74.6748× | 730,858 | *not measured* | — |
| `earth_surface` | 43,721.0072× | 783,742 | *not measured* | — |

**Cislunar is still the best case, at 20.5895×** — 2.4× clear of the next
destination on raw. Still **zero viable missions** anywhere.

Winners, raw: **2021 CX5** (D, 82 m, a = 1.626 AU) at both `cislunar` and
`lunar_surface`, **2018 DT** (M) at `leo`, **8651** (M) at `mars_surface`,
**2016 PN38** (M) at `earth_surface`. Beneficiated at cislunar it is 2021 CX5
again, concentrating 3.519× on iodine where raw flies xenon.

⚠️  **Only the cislunar raw cell is a delta.** 25.7035× → **26.7863×
(+4.21%)** against v1.13.0 on the same catalog — the expected direction, since
every item in v1.14.0 removes something the model was getting free. The other
four raw cells had **never been run on this catalog**, so they are first
measurements, not changes. And cislunar beneficiated had never been run either:
20.5895× is **not** a move from 23.9169×, which was measured on 15,566 rows
against this cell's 659,847.

⚠️  **The four non-cislunar beneficiated cells are still unmeasured** — 10 to
20 hours each on six cores, and they were not run. The v1.11.0 table below is
the last figure they have; it is three releases and a 17× population behind, so
read it for structure and not as a number.

**8651 (M) is still the Mars raw winner**, the same body as v1.10.x and
v1.11.0. Surviving a 17× population increase *and* three releases of model
change is a stronger statement about the separate Mars heliocentric transfer
than any ratio here.

**The destination ordering has shifted** — cislunar < lunar < leo < mars, where
v1.11.0 raw ran cislunar < mars < leo < lunar. Mars went from best-of-the-rest
to worst, which is v1.14.0's containment charge landing on exactly the
volatile-rich missions the Mars result used to be carried by.

**Xenon has taken over from iodine.** Raw shares by destination:

| destination | xenon | iodine | water ion | krypton | hydrolox |
|---|---|---|---|---|---|
| `cislunar` | 42.6% | 25.2% | 15.6% | 8.0% | 8.1% |
| `lunar_surface` | 42.3% | 10.3% | 20.7% | 22.6% | 3.8% |
| `mars_surface` | 57.8% | 19.9% | — | 15.4% | 2.1% |
| `leo` | 76.0% | 13.6% | — | 4.4% | 1.9% |
| `earth_surface` | 74.7% | 13.5% | — | 5.5% | 1.9% |

That retires v1.11.0's "iodine wins nine of the ten cells". Chemical propulsion
is **not** extinct — hydrolox holds 1.9–8.1% everywhere.

**Aerocapture resolves per destination on its own**: 95.8% of `earth_surface`
rows, 93.1% of `leo`, 82.0% of `mars_surface`, and **0.00% at `cislunar` and
`lunar_surface`**, which is the airless-destination behaviour falling out of
the search rather than being asserted.

**RTG share** runs 3.96% (`lunar_surface`) to 8.46% (`earth_surface`) raw, and
10.83% at cislunar beneficiated. v1.14.0 measured 3.9% on a 6,000-row sample —
which turns out to be almost exactly right for one destination and less than
half the true figure for another, so quote the range rather than the sample.

Verification, all passing: never-worse holds exactly on the cislunar pair
(650,516 pairs, max benef/raw 1.000000, zero exceptions, 102,703 declined); the
mass-ledger identity `hardware_total_kg == mining + power + ep` holds to
**0.000000000 kg** on every row of all six cells; serial and parallel output is
byte-identical (sha256 MATCH).

> 🚨  **Every cell in every results table BELOW this point is stale**, for two
> compounding reasons: catalog v1.1.0 took the population from 89,367 to
> 1,554,400 bodies, and calc v1.14.0 then changed the model. They are kept
> because their *structure* — which destination wins and why, what
> beneficiation does, which effects the model is sensitive to — is still how to
> read this pipeline. Do not quote their numbers.
>
> On the catalog change specifically: **the gain was the row cap, not the
> H-derived diameters.** The best body on a *measured* diameter was 2016 GS2 at
> 27.0173×, and it was excluded by the cap, never for lacking a diameter. The
> old catalog also held **zero unnumbered asteroids** — all 89,367 rows were
> numbered, 1 to 199,994 — because JPL returns rows in SPK-ID order, so no
> provisional-designation body could enter at *any* cap below the full table.
> The new catalog has 658,490 of them, and recently-discovered NEAs are mostly
> unnumbered.

Cost/revenue ratio (lower is better; 1.0 would be breakeven), catalog v1.0.9 /
calc v1.10.0 / mineral_value v1.7.0, full catalog — 35,807 asteroids fetched,
~29,600–35,000 evaluable per destination. The v1.6.0 column is the previous
Stage 2 pricing, run in the **same process on identical code**, so the
difference is the pricing change and nothing else:

| | raw v1.6.0 → **v1.7.0** | beneficiated v1.6.0 → **v1.7.0** | best target (v1.7.0, beneficiated) |
|---|---|---|---|
| `earth_surface` | 46,049.9× → 46,071.3× | 25,110× → 25,038.5×† | 4660 Nereus, Xe, 2.5× |
| `leo` | 65.97× → 72.45× | 47.17× → 48.13× | 4015 Wilson-Harrington, B, 5.5× |
| `cislunar` | 21.71× → 31.83× | 19.02× → **22.93×** | 7753, B, 5.4× |
| `lunar_surface` | 25.54× → 75.83× | 21.42× → 40.61× | 7753, B, 4.8× |
| `mars_surface` | 16.59× → 70.41× | **11.86×** → 51.82× | 6178, P, 7.1× |

† Measured 2026-08-07 in a separate process, not in the paired run, so its
−0.3% is quote drift rather than the pricing change.

`earth_surface` is the **control** — in-space pricing does not apply there, so
its +0.05% raw movement is the run-to-run noise floor from live quotes shifting
between loops within one process. Over longer gaps it is larger: see the
reproduction below, where the control moved ~0.4% in under a day and nothing
else moved at all.

Still **zero viable missions** anywhere.

#### Re-measured on v1.12.0, 2026-08-08 — cislunar only, current

Stage 3 v1.10.0 + Stage 4 v1.12.0, full catalog, against the same on-disk
Stage 2 catalog the v1.11.0 cislunar cells used.

| | v1.11.0 | **v1.12.0** | Δ | winner | evaluable |
|---|---|---|---|---|---|
| `cislunar` raw | 31.7712× | **33.2342×** | **+4.60%** | 4660 Nereus, iodine | **15,407** |
| `cislunar` beneficiated | 22.4665× | **23.9169×** | **+6.46%** | 7753, B, 5.31× | **15,566** |

**Cislunar is still the best case, now at 23.9169×**, and its winner is
unchanged. Both cells got *worse*, which is the whole shape of the release:
every item in it is a term that existed on one side of the model and not the
other. See [What changed in v1.12.0](#what-changed-in-v1120).

⚠️  **The ratios are not the headline — the population is.** Evaluable rows
roughly halved, ~31,000 → ~15,500, because about half the catalog was closing
its mass budget only on a micronewton thruster the model was happy to sell as
a cargo tug. Those are not missions that got more expensive; they were never
physical. Any per-row comparison against a v1.11.0 catalog compares different
populations.

⚠️  **"Chemical propulsion is extinct in this model" is retired.** Hydrolox now
wins 5.5% of cislunar rows and methalox 0.1%. It was never a physical result.

> ⚠️  **The other four destinations have NOT been re-run on v1.12.0.** The
> v1.11.0 table immediately below is stale for them. Both of the changes that
> move numbers — argon's storage class and the cargo-water power plant — are
> properties of the *mission*, so they move every destination, and
> `earth_surface` is not a control for either. `mars_surface` is the cell most
> likely to have moved a lot: it was the one destination winning on argon.

#### Measured on v1.11.0, 2026-08-08 (superseded at cislunar, stale elsewhere)

Stage 3 v1.9.0 + Stage 4 v1.11.0. Ten cells, one destination at a time, Stage 2
re-run for each; the asteroid catalog was reused, since Stage 1 is untouched by
this release and re-fetching would only add quote drift to a comparison about
the mission model.

| destination | raw v1.10.x | **raw v1.11.0** | benef v1.10.x | **benef v1.11.0** | v1.11.0 winner (benef) |
|---|---|---|---|---|---|
| `earth_surface` | 45,893.7× | 45,236.50× | 25,038.5× | 26,256.72× | 4660 Nereus, Xe, 2.47× |
| `leo` | 72.4520× | 71.0459× | 48.1286× | 51.2223× | 5620, D, 4.44× |
| `cislunar` | 31.8269× | 31.7712× | **22.9336×** | **22.4665×** | 7753, B, 4.96× |
| `lunar_surface` | 75.8315× | 75.5110× | 40.6132× | 37.8133× | 7753, B, 4.82× |
| `mars_surface` | 70.4063× | 70.4346× | 51.8161× | 51.9597× | 6178, P, 7.07× |

**Cislunar was still the best case at v1.11.0, at 22.4665×, and it improved.**
Four of the five beneficiated winners keep their v1.10.x identity *and*
concentration ratio; only `leo` moved, from 4015 Wilson-Harrington (B, 5.5×).
On v1.12.0 cislunar is **23.9169×** and still the best case; on v1.14.0 it is
**20.5895×** and still the best case.

⚠️  That sentence read "on v1.12.0 cislunar is 22.7353×" until 2026-08-09.
**That number was never measured** — it appears in no table in either file and
contradicts v1.12.0's own verification block, which records 23.9169×. Corrected
rather than carried forward.

Two mechanisms pull against each other here and the split between the raw and
beneficiated columns is the evidence for both:

- **The wider search can only help.** 21 operational propellants against 7, and
  a strictly larger option set cannot make a correctly-implemented search
  worse. Raw moves −0.18% to −1.94% at every destination, which is that effect
  on its own.
- **Tank mass can only hurt, in proportion to mass ratio**, since
  `k = 1/(1 − t(R−1))` diverges as `t(R−1) → 1`. Beneficiation means more feed,
  more power, a longer stay and more propellant, so beneficiated is where it
  bites — +6.4% at `leo`, and still net −6.9% at `lunar_surface` where the
  search gain wins.

**Iodine takes nine of the ten cells**, which is the tank term talking rather
than a coincidence: it stores as a solid at ambient pressure at 4.93 kg/L and
pays 0.2% of its own mass in tankage against xenon's 1.9%. Chemical propulsion
is effectively extinct in this model.

Note what that implies. Tankage is only ~0.7% of launch mass in the *winning*
missions, because the search routes around it. Its effect is not a cost it
adds — it is **which propellant it disqualifies**.

Mars was the exception on both counts: it moves +0.04% / +0.28% and was the
only destination that did not adopt iodine, winning on argon at both settings.

> ⚠️  **The propellant shares here are stale as of v1.12.0** — the figures used
> to read "iodine 52% of winners and argon 36%" across `earth_surface`. Argon's
> storage class changed in v1.12.0 and its tank fraction went 2.1% → 22.9%,
> because the old row was carrying liquid-argon density *and* zero boil-off at
> the same time. The mechanism above survives and is in fact sharpened by it:
> argon had been taking a quarter to a third of the winners on a tank exemption
> it should never have had. On v1.12.0 at cislunar the split is iodine 58.6% /
> PPT 29.0% / electrospray 11.0% beneficiated, and PPT 31.8% / iodine 26.8% /
> electrospray 24.3% raw — **argon falls from 27.3% to 0.0% and from 25.0% to
> 2.4%.** The Mars claim in the paragraph above should be assumed wrong until
> Mars is re-run: Mars was the destination winning on argon.

#### Reproduced end to end, 2026-08-07 (superseded, correct for v1.10.x)

All ten cells were re-measured through the UI from a catalog re-downloaded that
morning — the first check of these tables against a separate run rather than
against the process that produced them.

| destination | raw | beneficiated |
|---|---|---|
| `earth_surface` | 45,893.7× (table: 46,071.3×) | 25,038.5× (was pending) |
| `leo` | 72.4520× (72.45×) | 48.1286× (48.13×) |
| `cislunar` | 31.8269× (31.83×) | **22.9336×** (22.93×) |
| `lunar_surface` | 75.8315× (75.83×) | 40.6132× (40.61×) |
| `mars_surface` | 70.4063× (70.41×) | 51.8161× (51.82×) |

Every in-space cell came back to the hundredth, as did every winner and
concentration ratio — and the `earth_surface` beneficiated cell landed on 4660
Nereus at 2.5×, exactly the target the table had predicted for the cell it could
not fill. The catalog also rebuilt to its reference shape: 35,807 rows, 24,675
measured taxonomies against 11,131 albedo-guessed, 2,614 V-types.

The two `earth_surface` cells were the only ones to move (−0.39% raw, −0.28%
beneficiated), which is the control doing its job: it is priced off live
terrestrial quotes, while an in-space kilogram is dominated by a
launch-cost-avoided term derived from constants.

This establishes that the pipeline is deterministic given its inputs — the
architecture search, the concentration sweep and the fixed-point power solve all
had to land identically for it to hold. It does not revalidate the model.
Reproducing a number says nothing about whether the number is right.

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

⚠️ **The release progression below is a per-release series and has not been
re-measured** — rebuilding it means re-running old code, not re-running the
current model, which is why the 2026-08-07 sweep did not touch it. It is kept
because the *discipline* it records is the point: every step was a correction,
and the last two moved the number down. Read it as a shape, not as current
figures — this column tracks Mars, which is no longer the best case, and the
best case now anchors at 22.93× at cislunar.

| Release | Mars | What it started charging for |
|---|---|---|
| v1.6.0 | 2.2× | — |
| v1.7.0 | 14× | low-thrust trip time, launch windows, bound-water energy, learning curve, market saturation |
| v1.8.0 | 39× | rig service life, mission reliability, cryogenic boil-off, in-space manufacturing |
| v1.9.1 | 34× | reliability growth, and `p_mining` recalibrated 0.75 → 0.85 on the full flight record |
| catalog v1.0.9 | **25×** | nothing new — restored SsODNet, which had been downloaded and then discarded on every run, taking measured taxonomy from ~1,850 to ~24,675 bodies |
| v1.10.0 | **11.86×** | the electric propulsion stage and the return vehicle's structure — both flown as mass, neither billed — plus a per-asteroid architecture search and a fixed selection objective |

The whole column is at **v1.6.0 pricing**, which is what makes it a series about
the calc model rather than about Stage 2. Do not read the last row against the
51.82× in the tables above: that is the same code at v1.7.0 pricing, and the
difference between the two is the local-resource discount, not a release.

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
  physical: hydrolox at bodies with water, at 1.286 kg of water per kg of
  propellant, with the extra rock dug, timed and charged. The old switch
  synthesised *xenon* at a rubble pile. (Hydrolox was the *only* route
  v1.10.0 allowed; v1.11.0 added the water-fed thermal and electric options
  at 1.00 kg per kg — see the ISRU note under [Tuning](#tuning).)
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
switched one of the twenty models off rather than found something. See
[What the model charges for](#what-the-model-charges-for).

### What changed in mineral_value v1.7.1

**No number.** All 31 rows of the Stage 2 catalog recompute identically, and the
four Stage 4 cells are bit-identical. The stamp moves so a catalog still names
the code that built it.

The first audit pass Stage 2 has ever had, and it found one thing. A commodity's
share of a depot's import budget is looked up as
`_COMMODITY_CLASS.get(name, "shielding")`, and three rows had no entry —
**sperrylite (PtAs₂), laurite (RuS₂) and native-pgm**. They were taking the
shielding share, **15% of a destination's entire import budget**, where the
eight PGM *elements* all take the trace slice at **0.05%**. That is 75,000 kg/yr
at LEO against 250 — a factor of 300, for the ore minerals of exactly those
metals.

It is inert today, and that is why it survived: their in-space utility is 0.0 at
every destination, so the price router always ships them to Earth and the class
is never read. But the settlement catalyst market that would make it reachable
is recorded in `CLAUDE.md` as *considered and rejected*, not impossible — so
this is the same shape as the RTG branch: **an unreachable branch is not a
verified branch.** Reclassified to trace, with an assert that now fails at
import if any commodity is unclassified.

Measured and deliberately not fixed: **`nickel-iron` has no terrestrial market
ceiling**, so at `earth_surface` it never saturates — and it is one of only four
phases Stage 4 sells. Correcting it to world pig-iron production moves the
saturation multiplier by 7.7×10⁻⁸ at one mission's output and 7.7×10⁻⁵ at
programme scale: nothing, but enough to break bit-identity on a destination not
re-measured since calc v1.14.0.

Stage 1 was audited in the same pass and needed no changes. Its taxonomy table
covers the real population to **99.997%** — of 75 distinct spectral types across
1.55 M rows, only `Z` (36 rows) and `U` (4) resolve to nothing, and the cascade
fails safe by excluding them rather than mispricing them.

### What changed in v1.17.7

**No number, and for once that is not the point.** Every stamp before this one
went after cost, or a default, or dead code. This one fixes a **defect** — and
one that no cell in this repo could have shown, because the run that shows it
has not been made since v1.16.0.

**A cache grew without bound.** `_CALENDAR_CACHE` memoised a pair of programme
calendar multipliers on `(campaigns-per-ship, cadence, WACC)`. The first two of
those are small; the third, `cadence`, is `max(stay, synodic period)` — a fresh
float for **every candidate mission**. So unlike every other memo in the module,
which reaches a ceiling and sits there, this one grew **linearly with the
catalog**: ~45 entries per catalog row, or 3,983 / 17,729 / 36,071 entries at
caps of 100 / 400 / 800 rows. On a full-catalog default cell that projects to
**~70 million entries and 11–18 GB**, against a documented run peak of ~6 GB.

**The retention was buying 0.1 pp.** Replaying the real 223,538-call sequence
through bounded LRUs, all reuse turns out to be local to one candidate mission —
v1.17.5's per-candidate rig cache already absorbs the cross-option traffic:

```
unbounded     hit rate 83.9%   retained 36,071 entries
maxsize 1024  hit rate 83.9%   retained  1,024 entries
maxsize   64  hit rate 83.8%   retained     64 entries
```

Now `functools.lru_cache(maxsize=1024)`, confirmed flat at 1,024 entries at
every cap with the hit rate unchanged. **This cannot change an output value by
construction rather than by rounding** — it is a memo of a pure function, so
evicting an entry only forces recomputation of the identical float. That makes
it the one shape of optimisation this project can take for free, unlike the
arithmetic reorderings it has repeatedly declined. It is also *faster*:
`lru_cache` hashes in C, 180 → 91 ns per hit, and bounding costs nothing against
`maxsize=None`.

**Two smaller items.** `_load_csv` now reads with `low_memory=False` — not for
memory, but because the default reader infers dtypes from *chunks*, so the dtype
depends on how values fall across them, and it emitted a `DtypeWarning` on every
single load (a warning that always fires is one nobody reads). Measured neutral
first: 0 of 46 columns change dtype or value. And in Stage 3, the two propellant
sanity bands selected rows with `.astype(bool)` on a flag that reads `NaN` as
**True**, so a future propellant row omitting it would be silently classed as a
sail and dropped from both checks — the trap this repo already documents, in the
one place it had not been fixed. It is now `.ne(True)`, which is total across
both dtypes; the obvious `.fillna(False).astype(bool)` was written first and
rejected, because pandas raises a deprecation warning on the object path — that
is, exactly when the fix would fire.

Verified with the newly committed `verify.py` rather than a harness rebuilt from
memory — see [Verifying a change](#verifying-a-change), and note that writing
that file turned up **five** fresh harness bugs of its own, three of them
producing the identical "columns DIFFER against a byte-identical hash" symptom
from three unrelated causes.

### What changed in v1.17.6

**No number.** A performance release on the same contract as v1.10.1, v1.14.1,
v1.14.2, v1.17.1, v1.17.2, v1.17.4 and v1.17.5 — the stamp moves so a CSV still
names the code that produced it, and every measured cell stands as measured.

Three releases in a row went at the **programme ladder**. This one goes at the
**per-row walk** — the work every one of 1,555,618 catalog rows pays whether or
not it turns out to be evaluable — which makes it the first performance stamp
here worth more on the *raw* cell than on the default one.

**Composition is a per-taxonomy fact, and it was being derived per row.** The
three functions that price an asteroid's material — the bulk blend, the phase
table and the purity ceiling — read five values off the row and nothing else,
and all five come from Module 1's taxonomy: 76 spectral types collapse to about
**25 distinct composition tuples across 1.55 million rows**. They were walking
the mineral table three times per asteroid, with a `pandas.isna` on a scalar per
entry, to re-derive one of a couple of dozen answers. Memoised on the
composition: **14.84 → 1.21 µs**, **13.97 → 1.25 µs** and **27.66 → 1.28 µs**
per row, or ~88 s off every full beneficiated pass. This is the same finding
v1.17.4 made on *both sides* of the CSV boundary, now found in the place between
them: **a column with few distinct values and one Python call per row.**

**Six smaller items, all the same sentence.** The refusal helper inside the
rocket-equation solver was a nested `def`, rebuilt on all ~500,000 calls of the
hottest function in the model (~5% of it). The programme ladder itself is a
function of the rig's trip life and the config, and was being rebuilt per
candidate (~3.6% of the default cell). The vehicle's LEO capacity was derived in
three separate places, once per candidate, for seventeen numbers fixed for the
run. The Δv options, the per-propellant constants, and five reliability table
rows were each asked for at a finer granularity than they have answers.

| cell | HEAD | **v1.17.6** | speed-up | per-row |
|---|---|---|---|---|
| raw, 6,000 rows | 18.61 / 19.15 s | **16.28 / 16.14 s** | **1.14-1.19×** | **1.15×** |
| beneficiated, 800 rows | 13.49 / 13.73 s | **12.96 / 12.81 s** | **1.04-1.07×** | **1.05×** |
| raw + search, 3,000 rows | 16.71 / 16.58 s | **14.42 / 14.33 s** | **1.16×** | **1.18×** |
| beneficiated + search (default), 800 rows | 22.81 / 22.55 s | **20.51 / 20.45 s** | **1.10-1.11×** | **1.12×** |

Interleaved A/B, both builds in one process, cells alternated, best of 3, run
twice.

🚨 **This is the first release here whose ratio depends on the row cap, and
the caps above are deliberately large.** At the 150/400-row caps every previous
release measured itself on, the same build honestly reads **1.03-1.10×** — a
capped run pays a fixed ~1.6 s of catalog integrity check and pre-filter probe
that does not move and does not scale. **Quote the cap with the ratio.**

Verified the way every release here is: four cells 139/139 columns bit-identical
against HEAD with sha256 MATCH (less both provenance columns), and the four
hashes are the ones v1.17.4 committed, so they now reproduce across two
releases; pre-filter on vs off identical on all four; serial vs 8 workers
byte-identical on the two searched cells, matching v1.17.4's committed hashes;
mass ledger exact at 0.000000000 kg; both never-worse invariants holding with
zero exceptions, the searched-vs-unsearched median landing on +42.5% against the
committed full-catalog +42.4%.

### What changed in v1.17.5

**No number.** A performance release on the same contract as v1.10.1, v1.14.1,
v1.14.2, v1.17.1, v1.17.2 and v1.17.4 — the stamp moves so a CSV still names
the code that produced it, and every measured cell in this file stands as
measured.

Third release in a row aimed at the **programme ladder**, which is where
v1.17.0's default flip put the work: it prices a median of ~42 programme
options for every candidate mission, so anything re-derived per option is
re-derived forty times to change three numbers.

**One cache entry now carries the whole W-dependent block.** The rig cost
shares and the programme-calendar multipliers are a function of how many
campaigns one rig flies — of W — and of a prologue that is fixed for the
candidate. They are not a function of N. With W running `1 … trips` and
`trips` capped at 5, ~42 options were asking for at most ten distinct answers.

🚨 **CLAUDE.md had already measured this item and declined it at 3.2%.** What
moved it over the bar was not a re-measurement but the *neighbour*: the
calendar multipliers sixty lines below share the same key, and v1.17.4 had just
memoised them separately. Folding both into one entry makes the second lookup
disappear rather than survive. **Price the block, not the line.**

**Three smaller items, all of them repetition rather than arithmetic.** The two
O(N) memos (`learning_curve_factor`, `mining_success_probability`) were building
their dictionary keys in Python — two conversions and a tuple allocation before
the lookup started, at 455,094 calls apiece — and now hash in C via
`functools.lru_cache`: 159 → 92 ns and 249 → 131 ns. `_objective_key` ran
`str(x).strip().lower()` on all 457,776 calls to re-derive one boolean from a
config field fixed for the run. And `isru_feed_kg_per_kg_propellant` re-answered
a per-*propellant* question once per candidate: four rows in five fall through
to a legacy name test — a string normalisation plus a substring scan — to
conclude "no".

| cell | HEAD | **v1.17.5** | speed-up |
|---|---|---|---|
| raw, search off | 1.186 s | **1.175 s** | **1.01×** |
| beneficiated, search off | 2.260 s | **2.256 s** | **1.00×** |
| raw, search on | 2.262 s | **2.127 s** | **1.06×** |
| beneficiated + search (the default) | 4.283 s | **4.029 s** | **1.06×** |

Interleaved A/B, both builds in one process, cells alternated, best of 4.

🚨 **This is the smallest performance stamp in the project, and the flatness is
the finding.** Every item removes work that only exists when a ladder exists,
so both search-OFF cells are inert and should be. Six perf releases have now
run through this search; what is left in the ladder is per-option overhead
measured in tens of nanoseconds. **Do not expect another 1.5× from this path.**
(v1.17.6 did not get one from it — its 3.6% ladder item is the ladder being
*rebuilt* per candidate, not anything inside a rung.)

Verified the way every release here is: four cells 135/135 columns
bit-identical against HEAD with sha256 MATCH (less both provenance columns —
`pipeline_version` *and* `catalog_date`); pre-filter on vs off identical on all
four; serial vs 8 workers byte-identical; mass ledger exact at 0.000000000 kg;
both never-worse invariants holding with zero exceptions.

**Also: one dead constant removed** (`AU_KM`, unreferenced across all four
modules, `ui.py`, `ui_meta.py` and `build_master.py`), and a fresh mechanical
scan of every top-level definition, dataclass field and import found nothing
else — v1.17.3's conclusion holding one release later.

### What changed in v1.17.4

**No number.** A performance release on the same contract as v1.10.1, v1.14.1,
v1.14.2, v1.17.1 and v1.17.2 — the stamp moves so a CSV still names the code
that produced it, and every measured cell in this file stands as measured.

Two findings, in the two places five previous performance releases never
looked: the **catalog load**, and **pass 2** of the sizing loop.

**Nobody had profiled the load.** `comp_minerals` is a list-column that pandas
reads back as a string, and Stage 4 was `ast.literal_eval`-ing it once per row.
Composition is assigned from the spectral taxonomy, so that column takes **25
distinct values across all 1,555,667 rows** — 1.55 million parses to produce
twenty-five answers, costing more than the 862 MB CSV read in front of it.
`integrity_check` then walked the same 1.55 M lists to build a set of fourteen
names. Both now go by distinct value: **13.0×** on the parse, **3.2×** on the
walk, and the parsed column verified identical element for element.

**The pre-filter refuted at pass 1 and never asked about pass 2.** v1.14.1's
filter is sound and its argument is that pass 1 is the loop's most optimistic
pass. Measured on the real population, of 219,054 candidate solves **162,816
(74.3%) die on pass 2** — the first pass that flies the electric stage pass 1
has just sized, which on an electric mission is tonnes. That stage is the same
at every concentration ratio and every power source, so the identical
refutation was being re-derived 8 to 16 times. Asking once per (vehicle ×
propellant × Δv × ISRU) cuts candidate solves **219,054 → 32,342** and cascade
solves **500,860 → 183,677**.

🚨 **It is a decision, not a bound.** Viability is monotone decreasing in
`hardware_kg` and in `r_ret`, and both only grow from pass 1 to pass 2 — the
plant is ≥ 0, and the hold is floored at `station_keeping_floor_yr`. Nothing is
approximated, which is what separates this from the branch-and-bound on the
objective that CLAUDE.md still warns against.

| cell | HEAD | **v1.17.4** | speed-up |
|---|---|---|---|
| raw, search off | 1.854 s | **1.223 s** | **1.52×** |
| beneficiated, search off | 4.901 s | **2.486 s** | **1.97×** |
| raw, search on | 3.160 s | **2.369 s** | **1.33×** |
| beneficiated + search (the default) | 6.533 s | **4.157 s** | **1.57×** |
| *load + integrity check* | *30.38 s* | ***15.36 s*** | ***1.98×*** |
| *row → dict walk, per row* | *61.0 µs* | ***17.7 µs*** | ***3.44×*** |

Interleaved A/B, both builds in one process, cells alternated, best of 3.

**Every row was converted through a pandas Series it did not need.** Both the
serial loop and the workers walked the catalog with `iterrows()`, and
`_row_to_dict` threw the Series away — 61 µs a row against **17.7 µs** for
`to_dict("records")` over a 256-row block. That is ~50 µs on every catalog row
whether or not it is evaluable, so ~67-78 s a pass, about **5-6% of the raw cislunar
cell**. Value- and type-preserving, checked cell by cell over 20,000 rows.

**And the same finding upstream, shipped as catalog v1.1.1.**
`enrich_composition` resolved everything keyed on `spectral_type` once per row
— nine composition fields, two capitalisation passes, the PGM multiplier, twelve
`.apply()` passes making ~19 M Python calls to produce the ~800 answers that 76
taxonomy classes can give. **9.09 s → 2.35 s**, all 12 derived columns
identical. It is the *same column* Stage 4 fixes at the other end of the CSV
boundary, which is the useful part: the pattern to look for is **a column with
few distinct values and one Python call per row**, and this pipeline had it on
both sides of its own output file.

🚨 **Two fast options were measured and rejected.** `pd.read_csv(engine=
"pyarrow")` takes the 862 MB read from 17.9 s to **3.7 s** with identical
dtypes — and rounds floats differently in the last ULP, moving
`estimated_mass_kg` by a relative 1e-13. Physically nothing, and fatal: mass is
what the ranking runs on and every release here is argued from bit-identity.
And `builtins.max` is **not** worth inlining — the "~6× cheaper" figure this
project has quoted since v1.14.2 is stale, because Python 3.13 specialises
two-argument `max`; re-measured it is 1.2–2.4×, so the whole item is ~0.6%.

⚠️ **The shape is the opposite of v1.17.2's.** That release is inert with the
search off and worth 1.45× with it on, because it removes ladder work; this one
lands on the mass cascade, so it is worth most where there is *no* ladder. And
the load saving does not scale with the row cap at all — it is half the wall
clock of a 400-row cell and 0.2% of a full beneficiated one. **A single ratio
for this release is meaningless without the row count.**

Verified: four cells 139/139 columns bit-identical with sha256 MATCH; prune on
vs off and stage 2 active vs neutralised both identical on all four; serial vs
8 workers byte-identical with the search on; mass ledger exact; both
never-worse invariants hold. And pairwise — **every one of 20,533 tuples the
new stage killed was then solved in full at every power mode and every ratio,
and none produced a mission.** That last check is the one that matters: a
filter that is too tight drops a candidate without changing any row count, so
no output diff could see it.

### What changed in v1.14.1

**No number.** A performance release on the same contract as v1.10.1: the stamp
moves so a CSV still names the code that produced it, and every measured cell in
this file stands as measured on v1.14.0.

The search was spending ~90% of itself proving missions infeasible the
expensive way. Of 134,538 candidate solves for 200 raw asteroids at cislunar,
**8,292 reached the cost model — 6.2%**; beneficiated it is 7.3%. The rest paid
a ~20 µs prologue (eclipse geometry, synodic period, ISRU chemistry, tankage,
electric-stage sizing) to reach a solver that rejected them on a dozen flops.

Those flops now come first. The trick is that the sizing loop's **first**
iteration runs at zero plant mass, zero containment and the shortest possible
hold, so it is the most optimistic pass the loop will ever take — and it is
closed form. If it does not close, nothing downstream does. It is also blind to
the power source (no plant yet) and to the concentration ratio (no feed yet),
which is why the identical refutation was being recomputed up to eighteen times
for one dead candidate.

The second half of the release is the same lesson in a different place: the dark
period, the eclipse-corrected specific power, the 1/r² solar figure, the synodic
period, the mineable mass and the throughput cap are functions of the **body**
alone, and all six were being recomputed for every candidate — 38,643 times
apiece for 200 asteroids. `AsteroidContext` computes them once per asteroid.

| | v1.14.0 | **v1.14.1** | speed-up | output |
|---|---|---|---|---|
| raw, 400 rows | 7.86 s | **4.07 s** | **1.93×** | 124/124 columns identical, sha256 MATCH |
| beneficiated, 150 rows | 28.07 s | **16.73 s** | **1.68×** | 124/124 columns identical, sha256 MATCH |

On the full catalog it prunes **75.9%** of candidates. ⚠️ **That is not a 4×.**
The quarter that survive are the expensive ones — full cascade, cost model,
whole concentration sweep — so three quarters of the candidates are well under
half of the work. Do not quote the prune rate as a speed-up.

Soundness was checked three ways rather than argued: 68,136 (candidate × Δv ×
ISRU) tuples were pruned *and* solved in full, and none of the pruned ones
produced a result; calls to `mission_cost_usd` are **8,292 before and 8,292
after** while total solves fall 134,538 → 38,443; and serial vs 8 workers is
byte-identical. `.calc.prune_infeasible_combos = False` restores the v1.14.0
search exactly, and is the diff to run if an output ever moves.

> ✅ **This is stage 1 of two as of v1.17.4**, which asked the question this
> release did not: what happens at pass **2**. Pass 2 is the first pass that
> flies the electric stage pass 1 has just sized, and **74.3% of everything
> that survives stage 1 dies there** — identically at every concentration ratio
> and every power source, because that stage is sized off a cascade blind to
> both. Same flag, same restore, same diff. See "What changed in v1.17.4".

**The GPU was tested and rejected**, on an RTX 2080 Ti: fp64 `exp` over 40M
elements is **1.695 s on the card against 0.222 s on the CPU** — 7.6× slower,
which is the consumer 1:32 FP64 rate. fp32 is faster and unusable, because every
check this project relies on is a bit-identity check. RAM is not a constraint
either: the run peaks near 6 GB of 64 GB.

### What changed in v1.16.0

**A programme took decades and was charged for none of them.** One correction,
inert at N = 1 — verified as 141 of 141 columns identical, sha256 MATCH, with
the term on and off — so every measured cell in this file stands.

Stage 4 compounds a mission's up-front costs by `(1+W)^T` over that mission's
own duration. For one mission that is right. For a programme it assumes every
mission happens at once, and they cannot: one rig digs one hole at a time, so W
campaigns on a ship are strictly sequential. The lines that were being carried
free are the **amortised** ones — the bus NRE, the autonomy NRE and the rig —
because those alone are bought once, at t = 0, and divided across missions that
sell years apart. A mission's own articles are unaffected: shift a whole cash
flow later and its cost/revenue ratio does not move.

The charge is a closed-form mean over the programme, exactly 1.0 at one campaign
per ship. **Salvage gets the reciprocal series**, because it is collected at the
*end* — compounding a refund forward alongside the cost it is netted against
would pay a bonus for taking longer to collect it.

**The cadence is the dig, or the launch window, whichever is slower** — and on
a 400-row raw cislunar sample **the window binds on 165 of 168 rows**. The rig
stays at the asteroid, so campaign w+1 starts as soon as w's feed is out of the
ground; but a capsule can only be dispatched when Earth and the target line up,
and a synodic period diverges as *a* → 1 AU. A NEA at 1.05 AU can only be
revisited every ~14 years however fast its rig works. A single mission pays that
wait once; a programme of W pays it W−1 more times.

**It retires the band argument and makes the programme search two-dimensional.**
v1.15.0 could ladder fleet size alone because within a band every lever improved
with N and none pushed back. Calendar time is the lever that pushes back, so
campaigns-per-ship became a real decision: fleet stays a ladder, campaigns-per-
ship is **enumerated exhaustively** (it is at most five integers). Measured on
the sample: the searched cell **31.0693× → 33.7977×**, median penalty 5.3%, no
row improved, median fleet **1 → 2 ships**, median N **5 → 10**.

⚠️  **On that sample the band argument would still have given the right answer**
— campaigns-per-ship comes out at the rig's trip life on all 168 rows. The proof
is what broke, not the answer: once a lever pushes back, a dimension whose
optimum is no longer guaranteed has to be searched rather than assumed. It does
bite when trips are longer — against the older Stage 3 table, where nothing
capped duty cycles and trips reached 20, 12 of 168 bodies choose to retire a rig
early rather than pay the calendar to use it up.

Brute-forced rather than argued: every (fleet × campaigns-per-ship) on a 20 × 8
grid, priced exhaustively, per body. **Campaigns-per-ship is exact on 49 of 49
bodies**; the search is worse than brute force on 5, by at most **0.027%**, and
every one of those is the inherited fleet ladder landing one ship off.

⚠️  **Read the loader's `Module 3 operational costs  44 rows` line before
trusting any programme figure.** Against the archived 43-row table from the
v1.14.0 campaign the trip cap is silently absent, campaigns-per-ship runs to 20
instead of 5, and every programme number changes. `schema_check()` names it on
stdout; this bit during measurement.

### What changed in v1.15.0

**Programme size stopped being an input.** Two items, both inert at N = 1, so
every measured cell in this file stands.

**The rig wore out on a calendar, and the calendar was never the bound.**
`missions_sharing_rig` was `min(N, life / stay)`, and `life` is "Mining rig
service life" = **15 YEARS** — a figure whose own Stage 3 notes describe
corrosion, thermal cycling and radiation dose. Dividing it by the stay gave a
mission count, and nothing anywhere bounded **duty cycles**, so at the ~1.25 yr
stay the winning cislunar mission flies, one rig was good for **twelve
consecutive digs** on the strength of a number that only ever promised it would
not have rusted meanwhile. A rig parked between campaigns ages slowly; one
cutting rock does not.

Stage 3 v1.12.0 adds **"Mining rig maximum trips" = 5** (range 2–12) and the min
of the two bounds is taken, so long stays stay calendar-limited and short ones
are now cycle-limited. ⚠️ The 5 is a **judgement** — nothing has ever mined an
asteroid twice — bracketed between terrestrial mining plant (overhaul at ~2–3 yr
of continuous duty, in a workshop that does not exist at an asteroid) and the
flight record for regolith-contact mechanisms (single-campaign by design, or
failed inside one: TAGSAM, Philae, InSight's mole, Curiosity's drill). It also
stops terminal value refunding a mechanically-finished rig for its unused
calendar years.

**Programme size and fleet size became a searched axis.** v1.14.0 made market
saturation see N and thereby made the scale curve *turn*; nothing then searched
for the turn, and the curve was mapped by re-running the whole pipeline at
N = 1, 10, 100. Two structural facts make searching it cost **1.51× runtime,
not 12×** (measured on the full catalog; a 2,500-row sample said 1.13×):

1. **N enters nothing in the mass cascade.** It appears in the cost model,
   the saturation block and the reliability block, and in none of the rocket
   equation, the power fixed point, the payload knapsack or the concentration
   sweep. The expensive half is solved once and the whole ladder priced off it.
2. **The optimum N is always an exact multiple of the rig's trip life.** Within
   one fleet band the concurrent output — and so the saturation multiplier — is
   constant while NRE/N, the learning curve, the rig share and `p_mining` all
   improve, so the band's best is its top, N = F × trips. **So the search is over
   the FLEET and N follows**, and every N that cannot be optimal is skipped
   without being priced.

> 🚨  **Point 2 is retired by v1.16.0 — "always" is now "usually".** The proof
> was "every lever improves and none pushes back", and programme calendar time
> pushes back. Campaigns-per-ship is searched now, exhaustively, and the search
> is two-dimensional. Point 1 is untouched and is what still makes it cheap.

That is also the answer to the question in plain terms: **the number of ships is
the decision variable and programme size is its consequence.**

Brute-forced rather than asserted, because it is the load-bearing claim: every
integer N from 1 to 60 was evaluated exhaustively for 20 raw bodies and 1 to 24
for 32 beneficiated ones. Raw is exact everywhere — 0 exceptions, ratios matching
to four decimals. Beneficiated has **one genuine miss in 52 bodies, at 0.97%**,
and it is not the band argument: it is the concentration sweep's greedy
refinement, which now depends on N, failing to price a ratio that would have won
at a different programme size. Raising `concentration_search_steps` from 7 to 25
makes the ladder return the brute-force optimum exactly, which is what identifies
the grid rather than the fleet argument as the cause.

#### Measured on the full catalog (2026-08-11)

Both cells, all **1,554,353 rows** at cislunar raw, one process, 12 workers,
**650,516 evaluable** in each:

| | search off (N = 1) | search on |
|---|---|---|
| best cost/revenue | **26.7863×** | **14.1730×** (−47.1%) |
| winner | 2021 CX5 (D), New Glenn, **xenon** | 2021 CX5 (D), New Glenn, **iodine** |
| N / fleet | 1 / 1 | **5 / 1** |
| wall clock | 1,306 s | 1,978 s (**1.51×**) |

Never-worse holds on the whole population — **650,516 pairs, 0 worse, 650,515
improved, median improvement 45.3%.** `N = F × trips` on every single row. Fleet
sizes: 46.8% of bodies want one ship, median 2, and 0.37% pile up against
`max_fleet_ships` (bodies whose payloads have no finite market — the run flags
them).

🚨 **Run 1 reproduces the committed v1.14.0 cell exactly** — ratio, evaluable
rows, winner, vehicle, propellant, payload to the kilogram, saturation
multiplier, `p_mining`, RTG share, and the whole propellant split. v1.14.1 and
v1.14.2 argued bit-identity from ≤2,500-row samples and v1.15.0 argued inertness
from 400; **all three now hold on 1.55 million bodies at once.** The run also
measures those two performance releases at **4.10×** on a full cell, inside the
projected 3.4–4.6×.

🚨 **And one claim did not survive.** This release originally recorded
**1.04–1.13×** runtime for the search, from a 2,500-row sample. On the full
catalog it is **1.51×** — the sample understated it by ~1.4×. That is the third
time a stride sample has mispredicted full-catalog runtime here, in both
directions, and it extends the standing rule from absolute wall clocks to
*ratios between two settings*. Every other number in the release came out where
the sample said; only the runtime moved.

⚠️ **Default ON as of calc v1.17.0** (it was OFF at this release), and it is
still the one axis in Stage 4 that is not a correction: it changes the question
from "the best single mission to this rock" to "the best programme built around
it". Almost every figure in this README is the former, at N = 1 — set
`optimise_programme_scale = False` to reproduce them.

### What changed in v1.14.2

**No number.** The third performance-only stamp, same contract as v1.10.1 and
v1.14.1. Every measured cell in this file stands as measured on v1.14.0.

| | v1.14.1 | **v1.14.2** | speed-up | output |
|---|---|---|---|---|
| raw, 400 rows | 2.70 s | **1.13 s** | **2.39×** | 124/124 columns identical, sha256 MATCH |
| beneficiated, 150 rows | 9.19 s | **4.51 s** | **2.04×** | 124/124 columns identical, sha256 MATCH |

A bigger step than v1.14.1's, and **none of it came from the algorithm** — the
search does the same work in the same order. It had been doing it through the
wrong machinery.

**The model's arithmetic was going through numpy, one scalar at a time.** The
two most-called functions in the module applied `np.isfinite` and `np.exp` to
plain Python floats. On the reference machine `np.isfinite` costs **698 ns**
against `math.isfinite`'s **32 ns**, and `float(np.exp(x))` **694 ns** against
`math.exp`'s **47 ns** — 15–22×, because a ufunc call on a scalar builds a 0-d
array, resolves a dtype loop and boxes the result. That is the right price
amortised over a million elements and the wrong one for a single float. The
solver makes seven of them per call and is called half a million times per 150
beneficiated asteroids. `math.exp` was checked **bitwise** against `np.exp` over
400,000 samples spanning the model's Δv/Isp range before the swap: zero
mismatches.

**Three hoists.** The payload knapsack re-sorted the same phase list ~2,100
times per asteroid; six per-propellant constants and one per-vehicle were
re-parsed for every surviving candidate, each through `pd.isna` (another pandas
dispatch on a scalar — ~980,000 calls per 150 rows); and the infeasibility
pre-filter turns out to be **monotone in launch capacity**, so seventeen vehicles
were each re-deriving one propellant's exponentials, boil-off and tankage
closure only to differ on the final comparison.

🚨 **One of those hoists is a trap, and it is the most transferable thing in this
release.** Sorting the phase table at source — the obvious way to hoist the
knapsack's sort — *changes the output*. The market-saturation block accumulates
value by iterating a dict built from that table, and floating-point addition is
not associative, so the table's natural order is load-bearing on the last ULP.
The measured effect is **2.8e-16** on 3 of 60 rows with no winner moving:
numerically nothing, and still fatal, because every claim this project makes
about a release is argued from bit-identity. *A change can be numerically
negligible and still destroy the evidence.* The same reasoning is why the
pre-filter hoist carries the coefficients of its final comparison rather than the
launch capacity they algebraically imply — that rearrangement would move the
prune boundary in the last bit, and there it would change a row count.

**Measured and not taken:** hoisting the ratio-independent prologue out of the
concentration sweep, which looked like the largest remaining item and instruments
at **7.6%** of a beneficiated run — the three hoists above had already removed
what made it expensive. Measure the remainder *after* taking the cheap items.

⚠️ That 7.6% is a v1.14.2 figure and three later releases cut work around it
without re-measuring it. **Re-measured on v1.17.5 it is 2.3%** of the default
cell and 2.6% of raw, so the item is worth about 2% — still declined, now on a
current number, and a small illustration of the advice in the sentence above.

### What changed in v1.14.0

Another realism audit, and the result is more uncomfortable than v1.12.0's,
because three of the five findings were **already written down**. Every figure
below had been sitting in Stage 3's storage table since v1.9.0 under a note
reading "not modelled in Module 4" — and Stage 4 does not load that file. The
gap was documented, quoted as a known limitation for two releases, and never
closed. *Writing a gap down is not closing it.*

Measured on a 6,000-row stride sample of the 89,367-row on-disk catalog at
cislunar, both versions run against the same rows in the same process. **These
are sample figures, not full-catalog headlines** — the full-catalog cells
elsewhere in this file are v1.13.0 and are now stale.

| | v1.13.0 | **v1.14.0** | Δ |
|---|---|---|---|
| raw | 38.4050× | **38.7886×** | **+1.00%** |
| beneficiated | 25.7930× | **31.6556×** | **+22.73%** |

- **The pipeline sold water and never kept it.** Water is priced at every
  in-space destination, its liberation energy is charged and the array that
  bakes it is flown — and nothing kept it from subliming across a four-year
  cruise. The best cislunar missions are **~88% water by mass**, so the
  commodity carrying the entire result was the one with no containment. A
  sealed shaded hold at 0.05 kg/kg, incremental to the ore restraint, folded
  into the payload-scaling structure so the closed-form solver carries it with
  no change to its algebra.
- **The sun never set on the processing plant.** Processing power is a
  *continuous average* draw and the plant was sized straight off it, which is
  only right if the rig is never in shadow. It stands on a rotating body. Two
  terms: an array oversize of `[(1−f) + f/η]/(1−f)` = **2.11×**, which is a
  sizing factor no W/kg figure could ever have absorbed; and storage sized on
  the **body's own rotation period**, which finally makes `rotation_period_h` —
  carried by Stage 1 since v1.0.0 and read by nothing — a quantity the model
  uses. Together they cost **4.7×** at 1 AU and the median 10.2 h rotation, not
  the "roughly doubles" the storage table itself estimated.
- **The power source was chosen on mass, and it costs 625× more per watt.**
  This one was latent and this release is what made it dangerous. The
  radioisotope branch used to fire on *one row of 15,566*, so nobody noticed it
  was picking whichever plant was **lighter** while an RTG costs $500,000/W
  against $800. Adding the eclipse term moved the crossover from 3.46 AU to
  ~2.1 AU and put 31% of rows on the nuclear side — buying a median **$1.5B**
  plant, 14% of mission cost, on a criterion that cannot see dollars. Made a
  searched architecture axis resolved by the reported objective, it drops to
  **3.9%**. *An unreachable branch is not a verified branch.*
- **Market saturation could not see the programme it was written for.** Its own
  comment says it exists so "fly more missions" has a stopping point; it never
  read `nre_amortization_missions`, so a 100-mission programme sold 100
  payloads at the price one payload commands. Now charged on the programme's
  concurrent output, and the curve **turns**: 38.41× → 16.03× → 10.89× becomes
  38.79× → 16.47× → **20.32×** at N = 1/10/100. The optimum programme size is
  now interior, near N = 10.
- **Two ledger asymmetries.** The heat shield was the one recurring article
  with no learning curve — it is the most literally per-mission thing on the
  vehicle — and it was missing from the insured book value, the one item on the
  launch stack whose cost line sits outside `hardware_cost`. Both are inert at
  cislunar and at N = 1.

Also: `schema_check()` now checks Stage 3 **rows** as well as columns. The
operational-costs table is keyed by category, so a missing *figure* was
invisible to a column test — and four of this release's five findings arrive as
rows in it.

Verification: with both new flags off, the build reproduces HEAD across all 121
shared output columns; never-worse holds on the new power axis (max 1.000000,
zero exceptions) and for beneficiated ≤ raw; the mass-ledger identity holds
exactly; serial and parallel remain byte-identical. Runtime roughly doubles,
paid only on bodies where a radioisotope plant could be lighter.

### What changed in v1.12.0

A realism audit, and the result is uncomfortable: **the same defect keeps
recurring** — a term that exists on one side of the model and not the other.
Every item below moves the answer the same way, *worse*. Cislunar raw
31.7712× → **33.2342×** (+4.60%), beneficiated 22.4665× → **23.9169×**
(+6.46%), still the best case, same winner.

- **The DEVICE was never modelled, only the propellant — and this is the big
  one.** The clean statement of it is that **launch was modelled as an
  integrated vehicle with a payload it can actually lift, while in-space
  propulsion was modelled as a bare specific impulse.** One side had a
  capacity limit and the other did not. Stage 4 sized the electric stage on
  POWER alone, so buying enough kilowatts turned any row in the propellant
  table into a cargo tug. The result: **31.8% of raw winners were pulsed
  plasma thrusters and 24.3% were electrospray** — devices that have flown,
  and have flown producing *micronewtons* (EO-1's PPT: 860 µN; LISA
  Pathfinder's colloid heads: 5–30 µN each). The pipeline was asking them for
  ~7–10 N. Electrospray's own note in the table said scaling it to a cargo
  stage "means millions of emitters", and nothing read that sentence.

  The gate is **mass, not a threshold**: thrust is momentum flux, `T =
  m_prop·ve/t`, so Stage 3 now carries `thruster_kg_per_n` per technology and
  a device making µN/kg reports thousands of tonnes of thruster and dies in
  the rocket equation on its own. The physical divide is recorded as
  `thrust_scaling`: *continuous* devices (discharge or beam area you can
  enlarge) sit at 6–90 kg/N however big you build them; *replicated* devices
  (discrete emitters, needles, pulses) are stuck at 2,500–10,000 kg/N forever.
  Efficiency was also one shared 0.60 for every electric row — a PPT is really
  ~8% against a gridded ion thruster's 70%, so it needs ~9× the array. Both
  are per-technology now. **Zero replicated-scaling devices survive anywhere**,
  the evaluable catalog halves, and chemical propulsion comes back.

  > 🚨  **"Zero survive anywhere" was a property of the 15,566-row population,
  > not of the gate, and it is retired.** On the full 1.55 M-row catalog, FEEP
  > survives in seven of eight measured cells — 0 rows at `lunar_surface`, 13 at
  > `cislunar` raw, 5,479 at `earth_surface`. That is the gate working as
  > designed: `thruster_kg_per_n` is a mass penalty, not a cutoff, so the right
  > test is whether one ever **wins**. It never does, in any of the eight. But
  > the margin is not comfortable everywhere — at `mars_surface` the best FEEP
  > mission is the catalog's **fifth**-ranked body and at `earth_surface` its
  > **seventh**. PPT and electrospray, which won 31.8% and 24.3% of cislunar
  > rows before the gate, now survive nowhere at all.

- **Argon was a free resource, and the row said so itself.** It carried
  liquid-argon density — 1.395 kg/L, which exists only at its 87.3 K boiling
  point, and buys the lightest tank of any gas in the table at 2.1% of
  propellant mass — together with a boil-off of **zero**. Its own two comments
  read "liquid NBP (cryogenic storage)" and "stored supercritical at ambient
  temperature", three lines apart. Argon was winning ~25% of missions on that
  combination and the entire Mars result. Split into the two real articles:
  supercritical in a COPV at 0.30 kg/L (**22.9%** tankage), which is what has
  flown, and a `development`-tagged cryogenic row paying derived boil-off.
  22.9% is not a penalty, it is 1/M — pressure cancels out of the COPV mass
  fraction, so xenon 1.9% / krypton 12.5% / argon 22.9% is just their molar
  masses read backwards. Density derived two ways, boil-off derived from this
  table's own LOX figure. Measured effect at cislunar: argon falls from 25.0%
  of raw winners to 2.4% and from 27.3% of beneficiated winners to 0.0%, and
  1,059 bodies stop being feasible — while **neither headline ratio moves at
  all**, because the best missions were never flying argon. A single best-case
  cell is a poor regression test for a change that is wrong everywhere except
  at the top.
- **The cargo-water power plant was billed and never launched.** Liberation
  energy for water sold as cargo sized an array *after* the mass cascade had
  been built, so the cost model paid for it and the rocket equation never
  carried it. On a 400-body raw sample, `hardware_total_kg == 2,000 +
  power_system_kg + ep_system_kg` failed on **97 of 357 rows**, by up to
  408 kg. It now holds on every row. The worse half was the raw case: a raw
  mission to an icy body paid for an array it flew none of.
- **Propellant tankage had no cost line.** Flown since v1.11.0, charged its
  launch $/kg, manufactured for free. ~0.01% of mission cost, and kept exactly
  because it is small — this class is only found by checking every term.
- **Launch insurance under-booked the spacecraft.** Book value was rig +
  capsule, which was the whole vehicle back in v1.4.0. It never picked up the
  power plant, the electric stage, or tankage. A 300 kW electric stage is a
  nine-figure article and it was flying uninsured.
- **`max_accel_g` was exported and read by nobody**, though Stage 3 added it
  expressly to disqualify the kinetic launchers. Only maturity was excluding
  them; ungated, a 10,000 g slingshot at $6,250/kg wins on price and powders
  the mining rig.
- **The tanker charge was withdrawn** — the one item running the other way.
  Stage 3's note asked for it *"in the escape-direct scenario"*; v1.11.0
  implemented the arithmetic and dropped the scenario. Stage 4 reads
  `payload_leo_kg` and `usd_per_kg_to_leo` and nothing else, so no mission here
  is ever refuelled, and $1.08B was being billed for an unused capability. Now
  gated behind `escape_direct_launch`, which nothing sets.

**And one thing that turned out to be very nearly inert.** v1.11.0's RTG
option is correctly wired and fires on **1 row out of 15,566** (18916, at
3.86 AU). 864 catalog bodies sit beyond the 3.46 AU crossover, but they fail
in the mass cascade on a 10–12 km/s outbound Δv long before array mass
matters. The code is right; the claimed benefit never materialised. A term
being implemented is not the same as a term being reached.

**Verified four ways** on the rebuilt `master.py`, at cislunar: the full
catalog reproduces both cells; never-worse holds exactly (15,407 pairs, max
benef/raw 1.000000, 0 exceptions, 591 declined) — which mattered more than
usual here, since the thrust gate *removes* options and a strictly smaller
option set cannot make a correct search better; no `replicated`-scaling device
survives in either run, the direct check that the gate did what it claims
(**retired on the full catalog — see the note above; the check that survives is
whether one ever wins, and it never does**); and
serial vs 8-worker runs are byte-identical (raw 4,000 rows 43.2 s → 23.5 s,
beneficiated 2,000 rows 197.6 s → 54.0 s, sha256 MATCH on both). Full-catalog
wall clock is 86 s raw / 463 s beneficiated, essentially unchanged from
v1.11.0's 89 s / 462 s — the extra knapsack calls are offset by half the
catalog now failing early.

### What changed in v1.11.0

Same failure mode as v1.10.0, found one level further out: **the reference
tables were incomplete, and the omissions all ran the same way.** Everything
missing from the propellant table was either an option the search never got to
consider or a cost the model never got to charge — so the model was picking
the best of seven propellants while the output claimed it had picked the best
available.

- **Propellant tankage entered the rocket equation.** `density_kg_per_L` had
  been computed and exported since Stage 3 v1.2.0 and read by nothing. Tank
  mass scales with volume, so this subsidised low-density propellants — which
  are the same ones with the highest specific impulse.
- **Sixteen flown propellants were added**, including krypton (the most-flown
  electric propellant by unit count), iodine, and water electrothermal.
  Seventeen development and concept rows were added behind a maturity gate.
- **The RTG row was read for the first time** since it was written in v1.2.0.
  Solar and radioisotope power cross at 3.46 AU, and a lot of this catalog is
  beyond it.
- **Orbital refuelling was charged.** Starship's escape payload assumes tanker
  flights; twelve of them is $1.08B.
- **ISRU stopped being hydrolox-only.**

**Measured: the two effects pull opposite ways, and the split is the
evidence.** Raw improved at every destination (−0.18% to −1.94%) — that is the
wider search on its own, and a strictly larger option set cannot make a
correct search worse. Beneficiated split, +6.43% at `leo` against −6.89% at
`lunar_surface`, because beneficiation means more propellant and `k = 1/(1 −
t(R−1))` diverges with mass ratio. Cislunar, the best case, improved 22.9336×
→ **22.4665×**.

The surprise is *where* tankage acts. It is only ~0.7% of launch mass in the
winning missions, because the search routes around it — iodine wins nine of
ten cells on a 0.2% tank against xenon's 1.9%, and chemical propulsion goes
effectively extinct (hydrolox wins 7 rows of 32,442). The tank term's effect
is not a cost it adds; it is **which propellant it disqualifies**.

**Verified three ways** on the rebuilt `master.py`, at cislunar:

- **Reproduces the sweep** — 31.7712× raw and 22.4665× beneficiated from the
  built artefact in a separate process, matching the module-level run exactly.
- **Never-worse invariant holds** — 31,558 raw/beneficiated pairs, max
  `benef/raw` = 1.000000, zero exceptions, 655 bodies declining to concentrate
  at exactly 1.0. That is the expected signature and nothing else. It matters
  most for this release, because *widening* a search is the operation that
  exposed the v1.10.0 objective bug.
- **Serial and parallel are byte-identical** — sha256 match at 4,000 raw rows
  (1.94×) and 2,000 beneficiated rows (3.79×).

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
  beneficiation plus a searched programme — still comes in **~13× short**
  (**13.1443×**, full catalog, calc v1.16.0, measured 2026-08-11; **20.5895×**
  at a single mission). There is no "don't fly" option, so the ranking is
  really *which target loses least*.
  (This was `mars_surface` at ~25× until mineral_value v1.7.0 priced the local
  resources a planetary surface already has; Mars is now the *worst* of the
  four in-space destinations at 74.6748× raw.) Scale does not rescue it either
  — and as of v1.14.0 scale no longer even helps monotonically: market
  saturation now sees the programme's concurrent output, so the cost/revenue
  curve **turns**, with an interior optimum near N = 10. Measured on the full
  catalog 2026-08-10 (cislunar, raw): **26.7863× → 13.5836× → 18.3605×** at
  N = 1 / 10 / 100. So the most favourable programme in the model still comes
  in **~14× short**, and flying a hundred missions is worse than flying ten.
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
- ~~**Volatile cargo is never kept cold.**~~ **Closed in v1.14.0.** Water is
  now flown in a sealed shaded hold at 0.05 kg/kg, incremental to the ore
  restraint. It was not a rounding term — the best cislunar missions are ~88%
  water by mass, so the commodity carrying the result was the one flying free.
- ~~**The sun never sets.**~~ **Closed in v1.14.0.** The processing plant now
  installs 2.11× its continuous draw and carries storage sized on the body's
  own rotation period. Radioisotope plants and the EP array are exempt — one
  is flat with time, the other is in permanent sunlight.
  - ⚠️  **Still not modelled: the duty-cycle alternative.** A rig can mine
    slowly in daylight instead of carrying a battery, taking twice the stay
    rather than twice the plant. Where digging slowly is cheaper, the model is
    now pessimistic. A free-flying array off a small body would see almost no
    eclipse at all, and the pipeline cannot express that architecture either.
- **Boil-off cannot be bought down.** It is applied passively, so hydrolox
  pays the full 0.05%/day with no option to spend array mass and power on a
  zero-boil-off cryocooler. Conservative for hydrolox, but a gap rather than a
  decision.
- **Tank mass scales purely with volume.** The pressure term genuinely does;
  insulation and minimum gauge scale with area, so the model overstates the
  penalty on a very large tank and understates it on a small one. NASA's large
  NTP studies get an LH2 tank near 12-15% of propellant mass; this model says
  53% at the tonne scale its stages actually work at. The direction is chosen
  deliberately — the propellants that most want a generous tank model are the
  speculative ones.
- **Non-Earth launch origins are not modelled.** Stage 3 lists a lunar mass
  driver and a lunar space elevator, both roughly two orders of magnitude
  cheaper per kg than any rocket. Stage 4 departs from Earth and prices a
  discrete launch, so it cannot read either — their payload figures are annual
  throughput. They are markers for an architecture the pipeline does not have,
  not inputs to it.
- **Sails and tethers cannot be sized at all.** Anything propellantless has no
  mass ratio, so the rocket equation reports that it moves any payload for
  free. Doing it honestly needs a thrust-limited trajectory solver — the same
  thing missing from the EP stage — so they are excluded rather than allowed
  to report infinity.

## What the model charges for

Twenty models in total, added across seven releases. Each defaults ON; set
the flag to `False` to isolate its effect. The five below closed gaps in
v1.7.0 that all pushed the answer the same way — towards optimism; the five
after them arrived in v1.8.0 and v1.9.0, and one of those pushed back the
other way.

The next seven are v1.10.0 through v1.12.0 and are a different species: not
gaps in what the model charged for, but **masses it flew and never billed at
all**, or bills it presented for mass it never flew. v1.12.0 found three more
of them inside v1.11.0's own additions, which is why the count keeps moving —
and it also *withdrew* one (the tanker charge), so "seventeen" is not simply
the old fourteen plus three.

The last two are v1.14.0 and are a third species again: **terms whose figures
were already written down, cited and correct, in a Stage 3 table that Stage 4
does not load.** Volatile cargo containment and night-side power had both been
recorded as known limitations for two releases. Writing a gap down had been
mistaken for closing it.

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

**Propellant tankage** (`model_tank_mass`, v1.11.0). Stage 3 had computed
`density_kg_per_L` since v1.2.0 and nothing read it. A tank's mass scales with
the **volume** it encloses, not with the propellant mass inside it, so leaving
it out was a straight subsidy to whichever propellant had the lowest density —
which is the same propellant that has the highest specific impulse, so the
error compounded rather than cancelling. LH2 is 0.0708 kg/L against kerolox at
1.015: fourteen times the tank per kilogram burnt.

`tank_kg_per_L` is derived per storage class and anchored on flight articles
rather than asserted. As a fraction of the propellant it holds: iodine 0.2%
(solid at ambient pressure), xenon 1.9%, kerolox 2.5%, an APCP motor case 6.9%
against Star 48B's measured 6.4%, hydrolox 9.7% against Centaur III's measured
~9.7%, krypton 12.5% (a worse COPV at 18 MPa is the price of a cheaper
propellant), cold gas 46%, and bare LH2 53% — which is what a nuclear-thermal
stage has to earn its 900 s against.

The closed-form solver generalises with two scalars rather than going
iterative: `k = 1/(1 − t(R_ret − 1))` on the return leg, where the tank flies
home inside the cargo's post-burn mass, and `k_out` on the outbound leg, where
it is staged at the asteroid. Both are exactly 1 at `t = 0`. `t(R − 1) ≥ 1`
means the tank cannot close, and that is infeasible rather than expensive.

**Orbital refuelling** (`charge_tanker_flights`, v1.11.0 — **gated off in
v1.12.0**). Starship's escape payload (27 t) *exceeds* its GTO payload (21 t).
No propulsion system can do that — the escape figure is for a vehicle topped up
in orbit first. Stage 3's vehicle row has said so in prose since v1.4.0,
*including the fix* ("Module 4 should add ~$90M × N_tankers **to the
escape-direct scenario**"), and Stage 4 never did it.

v1.11.0 then did the arithmetic and dropped the scenario, charging twelve
flights — $1.08B on top of a $90M launch — on **every** mission. Stage 4 has no
escape-direct scenario: it reads `payload_leo_kg` and `usd_per_kg_to_leo` and
nothing else, so the vehicle is a LEO lifter and the stack departs on its own
outbound stage. Starship's 100 t to LEO needs no tankers. v1.12.0 gates the
charge behind `escape_direct_launch`, which nothing sets, and keeps the wiring
for the day this module gains direct injection.

**Argon storage** (v1.12.0, Stage 3). Not a flag — a reference-table fix, and
the one that moves numbers. See [What changed in
v1.12.0](#what-changed-in-v1120).

**Cargo-water power plant** (`model_water_liberation`, corrected v1.12.0). The
liberation energy for water sold as cargo had sized an array that the cost
model paid for and the rocket equation never carried. The flag is unchanged;
what changed is that the array is now flown.

**Launch acceleration** (`max_payload_accel_g`, v1.12.0). 15 g. Every real
launcher in Stage 3 is 6 g or less; SpinLaunch is 10,000 g, a light-gas gun
30,000, StarTram 30. Stage 3 added the column in v1.9.0 to disqualify them and
nothing read it, so only their `concept` status was keeping them out.

**Propellant tank fabrication** (v1.12.0). $6,000/kg, Centaur-derived. Tank
mass had been flown and launch-charged since v1.11.0 and never built.

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
(`source` / `tholen` / `albedo` / `albedo_assumed` / `unknown`).

This is not hypothetical, and it has now happened twice.

**NEOWISE, until catalog v1.1.0.** IRSA types its `asteroid_number` column by
what the result slice happens to contain: all-numbered comes back `int64`, and
one unnumbered row makes it `float64`. The fetcher stringified it, so the merge
key became `"3.0"` instead of `"3"` and matched nothing. Every NEOWISE row then
died at validation for having no orbital elements.

The bug worked at small row caps and failed at large ones, the fetcher printed
`OK  183,408 records fetched` on the runs where it contributed zero, and the only
trace in the output was seven `neowise_*` columns present and 100% empty. After
the fix, **132,691** bodies pick up NEOWISE IR albedo, beaming parameter and
diameter uncertainties. The population gain is small — JPL SBDB already ingests
NEOWISE diameters, so only ~27 bodies were missing outright — but no run before
v1.1.0 had the IR data it reported fetching.

**SsODNet, until catalog v1.0.9.** Downloaded in full
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

And note what `Source summary` does **not** tell you: it counts rows *fetched*,
which is exactly the number NEOWISE reported on the runs where it contributed
nothing. Since v1.1.0 the merge also prints how many of each supplement's keys
**matched the backbone**, and shouts when that is zero. The equivalent check on
a CSV you did not watch being built is one line — a `source_*` column at zero
whose fetcher reported success is the signature:

```bash
py -c "import pandas as pd; d=pd.read_csv('asteroid_pipeline/asteroid_catalog.csv',low_memory=False); print({c:int(d[c].notna().sum()) for c in d.columns if c.startswith('source_')})"
```

### Diameters, and the 9% problem

Stage 1 drops any body without a diameter, and that single rule set the size of
this catalog for its whole history. Of JPL's **1,554,321** asteroids only
**139,582 have a measured diameter** — 9.0%. Across every source the union is
**149,590**.

**1,553,817 have an absolute magnitude H**, and diameter follows from H and the
geometric albedo with no free parameters:

```
D_km = (1329 / sqrt(p_V)) * 10^(-H/5)          Fowler & Chillemi 1992
```

so the only estimated quantity is `p_V`. With `derive_diameter_from_h` on (the
default since v1.1.0) the catalog reaches **1,554,400 rows**. A measured
diameter is never overwritten, and `diameter_source` records which is which:

| `diameter_source` | rows | what it means |
|---|---|---|
| `measured` | 149,590 | a real measurement, from any source |
| `derived_h_orbit_albedo` | 1,298,885 | albedo from the belt's albedo/distance gradient |
| `derived_h_taxonomy_albedo` | 105,905 | albedo from the body's spectral class |
| `derived_h_measured_albedo` | 20 | had an albedo but no diameter |

Both albedo tables are **medians over the 138,437 bodies with a measured
albedo**, computed rather than taken from literature, with per-entry sample
sizes in the source. The gradient is strong enough to be worth binning for:
0.2885 at 1.3–2.0 AU against 0.0660 in the outer belt.

Three caveats, all of which run **optimistic**, and none of which should be
"fixed" by editing the tables:

- **Mass is the exposed quantity.** D scales as `p_V^-0.5` but mass as
  `p_V^-1.5`, and mass is what the ranking runs on. A factor-2 albedo error is
  a factor-2.8 mass error. Filter on `derived_diameter_is_estimate` before
  treating a derived row as comparable to a measured one.
- **The albedo sample is biased dark.** Those measurements are overwhelmingly
  NEOWISE, a thermal-IR survey; at fixed H a darker body is larger and easier
  to detect thermally. A median that is too low gives diameters that are too
  large.
- **Beyond 5.2 AU it is weakest.** The outer bin comes from 1,228 bodies
  dominated by dark Centaurs and Trojans, applied to genuinely icy TNOs. 5,656
  derived bodies exceed 100 km and the largest is 1,219 km — real TNOs whose
  sizes are overstated. That is 1.09% of the catalog, and they fail Stage 4 on
  Δv regardless.

Set `derive_diameter_from_h = False` for a measured-only catalog of ~149,600.

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
