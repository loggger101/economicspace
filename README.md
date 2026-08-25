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
versions.md            Release history + the measurement tables it superseded
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

**What each version changed is in [`versions.md`](versions.md)**, newest first.
⚠️  A version bump does **not** mean a number moved — twelve stamps so far have
moved without one, for performance, dead code or a flipped default. The rule is
one-directional.

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

**Stages 1-3 re-fetch and overwrite, so they ask first.** Each replaces the
only copy of its CSV — there is no history and no undo, and every `verify.py`
baseline is built against those exact bytes. `run_pipeline.py` names what a
run would re-fetch and waits for a `yes`, unless the file does not exist yet
(nothing to lose) or you pass `--yes`. `run.bat` passes `--yes` on any
invocation carrying an argument, so a scripted or scheduled `run.bat quick`
still runs unattended; the menu asks.

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
- **Stage 4 is the long pole by far**, because `eval_row_cap` defaults to `0`
  (evaluate everything), "everything" is 1.55 M rows, and both beneficiation
  and the programme search are on by default. Measured at cislunar on six
  physical cores / 12 workers, calc v1.17.7: **733 s** raw at N = 1 and
  **5,692 s** (1.6 h) for the default cell. Other destinations cost 2.1–2.7×
  more. Set `eval_row_cap` for anything interactive — as of calc v1.13.0 a
  capped run is an evenly-spaced sample of the whole belt rather than the
  innermost N bodies, so it is actually representative.
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
| `.calc.use_beneficiation` | `True` | Return concentrate instead of run-of-mine ore. Charges the extra dig time, processing energy and solar-array mass. **Default since calc v1.17.0**; almost every historical table is `False`. See [Beneficiation](#beneficiation) |
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
| `.calc.optimise_programme_scale` | `True` | Search programme size and fleet size per asteroid instead of setting N. **Default since calc v1.17.0.** It changes the question the run answers, so most historical tables are `False`, at N = 1. See [Programme scale](#programme-scale) |
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

Stage 4 evaluates each asteroid independently of every other one — the search
reads the reference tables and writes nothing — so since calc **v1.10.1** it
does that across a process pool instead of on one core.

**No number changes.** Serial and parallel output is byte-identical, and that
is one of the six checks `verify.py` runs on every release. Chunks are consumed
in submission order specifically so that the row order, and therefore the
ordering of `profit_usd` ties under a non-stable sort, is unchanged.

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

which runs all six:

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

## Programme scale

`nre_amortization_missions` is programme size N, and since calc v1.15.0 it is
**searched rather than set**: `optimise_programme_scale` resolves fleet size
and campaigns-per-ship per asteroid, jointly with every other architecture
axis, and N follows as their product. It is **on by default** since v1.17.0.

That costs **1.71× runtime** rather than one full run per N, because **N enters
nothing in the mass cascade** — it appears in the cost model, the saturation
block and the reliability block, and in none of the rocket equation, the power
fixed point, the payload knapsack or the concentration sweep. The expensive
half of the mission is solved once per candidate and the whole ladder is priced
off the result.

**Scale is real, sublinear, and bounded.** Five models pull against each other,
and the last two are what stop it running away:

- **NRE amortises** across the programme, and the learning curve (Wright's law,
  0.85) falls on the per-mission articles.
- **Mining reliability grows** with programme size — Duane/AMSAA, 0.850 at
  N = 1 to 0.943 at N = 100, reported as the fleet average rather than the
  terminal value.
- **The rig wears out**, on whichever of its two bounds binds first: a 15-year
  calendar life, or five duty cycles. Past that, mission N+1 buys a new rig.
- **The market saturates**, against the programme's **concurrent** output —
  which is what makes the optimum programme size **interior** rather than "as
  many as you can pay for".
- **The calendar is charged.** One rig digs one hole at a time, so campaigns on
  a ship are strictly sequential, and the lines bought once at t = 0 — bus NRE,
  autonomy NRE, the rig — are carried across decades of programme span.

Measured on the full catalog at cislunar, the search improves the raw cell
**26.7863× → 15.4272×** and the beneficiated cell **20.5895× → 13.1443×**, on a
median fleet of **2 ships**, a median N of **10**, and a median programme span
of 11.5 years raw / 14.8 beneficiated. Every destination is in
[Results](#results).

⚠️  **The searched and unsearched columns answer different questions and are
not comparable.** One is the best single mission to a rock, the other the best
programme built around it. The improvement is a change of question, not a
saving — and it does not reach viability either: the best programme in the
model still loses about thirteen dollars for every one it earns.

⚠️  **Rows piling up against `max_fleet_ships` are a diagnostic, not a result.**
Those are bodies whose payloads have no finite market to saturate, so the
objective is monotone in N and the ladder's top rung is simply where the loop
stopped. That is 0.37–0.40% of rows at cislunar and **100% at
`earth_surface`**, which is why that destination's searched cells are not
optima.

The historical curves against a *forced* programme size — and the two
corrections that reshaped them — are in
[The programme-scale curves](versions.md#the-programme-scale-curves).

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

### Propellants — 41 rows

Each carries specific impulse, blended density, $/kg, boil-off rate, a
low-thrust Δv penalty, and (new in v1.9.0) a **storage class**, a derived
**tankage mass**, a maturity **status**, and whether the asteroid itself can
supply it.

| Status | Count | Rows |
|---|---|---|
| operational | 23 | kerolox, hydrolox, methalox, MMH/NTO, UDMH/NTO, Aerozine-50/NTO, hydrazine, green monoprop (ASCENT), HTP mono + bi, cold gas, solid APCP, xenon, krypton, argon, iodine, water electrothermal, water ion, hydrazine arcjet, electrospray, FEEP, PPT, solar sail |
| development | 8 | nuclear thermal, nuclear electric, solar-thermal H2, solar-thermal steam, VASIMR, MPD, metal/water (ALICE), cryogenic argon |
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

**On by default since calc v1.17.0** (`CALC_CONFIG.use_beneficiation`).
Terrestrial mines ship concentrate, not ore; switched off, the pipeline flies
home run-of-mine regolith at bulk grade while the rig's own throughput capacity
— 66× the rocket-equation payload limit — sits idle. Switched on, the rig digs
surplus feed, rejects the gangue, and loads concentrate.

⚠️  **Almost every table dated before 2026-08-11 is the `False` case.** Set it
back to reproduce them.

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

The search always includes **not concentrating at all** as a baseline — which
is not the same as a ratio of 1.0, since that would still pay the separation
recovery loss and the array mass for no grade gain — so beneficiation is an
option rather than an obligation and can never make a mission worse.

How often it declines varies enormously by destination, and the ordering is the
ISRU discount doing its job: **0.6%** of bodies at `mars_surface`, 1.1% at
`earth_surface`, 3.9% at `lunar_surface`, 11.6% at `leo` and **15.8% at
`cislunar`** — a depot with no local resources is where concentrate is worth
least relative to bulk. Where it does concentrate, the chosen ratio is a
single-digit multiple and never the 50× cap — the best cislunar mission
concentrates 3.5× at N = 1 and 3.9× as a programme. Median improvement from
beneficiating runs from +39.5% at `cislunar` to **+77.7%** at `earth_surface`.

**"Can never make a mission worse" is checked, not assumed**, and it is one of
the six checks in `verify.py`: join the raw and beneficiated catalogs on
`designation` and assert the beneficiated cost/revenue is never higher, row by
row. On the full catalog it holds across **all twenty cells with zero
exceptions**, and the worst case is exactly 1.000000 — which is beneficiation
declining and falling back on the baseline. **That is the signature to expect:
never worse, and equal wherever it declines.** A maximum above 1.0 means the
search is optimising something other than what gets reported.

Costs charged, all of which the search trades against:

- **Time.** Dig time is charged on the *feed*, not the product.
- **Energy and mass.** Stage 3's 200 Wh/kg excavation and 500 Wh/kg
  beneficiation rates over the stay time give a power draw; Stage 3's
  60 W/kg-at-1-AU power-system row, scaled 1/r² by the target's semi-major
  axis, turns that into array mass; the array flies in the same rocket
  equation as everything else. Payload → feed → power → mass → payload is a
  real circular dependency, solved by fixed-point iteration.

That 1/r² term punishes distant targets hard, and the ratios between the rows
are the point rather than the absolute masses (cislunar delivery, measured on a
1,959-body pre-v1.0.9 run):

| Semi-major axis | W/kg at target | Mean array mass |
|-----------------|---------------|-----------------|
| < 1.2 AU | 51.5 | 4 kg |
| 1.8–2.5 AU | 11.4 | 41 kg |
| > 3.2 AU | 4.7 | 226 kg |

⚠️  **The search costs runtime: beneficiation is 4.67× the raw path.** Full
1,555,667-row catalog, six physical cores / 12 workers, calc v1.17.7, measured
2026-08-23/24 — the complete wall clock for all twenty cells:

| destination | raw, N = 1 | raw, searched | benef, N = 1 | **benef + searched** |
|---|---|---|---|---|
| `cislunar` | 733 s | 1,253 s | 3,424 s | **5,692 s** |
| `lunar_surface` | 572 s | 867 s | 2,660 s | 4,508 s |
| `leo` | 1,175 s | 2,064 s | 8,834 s | 15,316 s |
| `mars_surface` | 1,191 s | 1,955 s | 7,128 s | 12,186 s |
| `earth_surface` | 1,154 s | 1,838 s | 7,714 s | 13,581 s |

The whole twenty-cell matrix is **26.1 hours**. Tune with
`.calc.concentration_search_steps`, and cap `.calc.eval_row_cap` for anything
interactive.

⚠️  **Every timing older than calc v1.17.7 is high, and by a lot.** Six
performance-only releases landed between v1.16.0 and v1.17.7 without changing a
single output value, worth **1.78× to 4.32×** depending on the cell — the
default cell went 24,587 s to 5,692 s. A wall-clock number in this project
tells you nothing without the release it was measured on. The per-release
figures are in [`versions.md`](versions.md).

**Most of that came from not solving dead candidates.** `prune_infeasible_combos`
(on by default, the Common tab's **Hopeless candidates**) refuses a candidate at
the two points where the answer is already decided rather than re-deriving it
once per power source and once per point of the concentration sweep: v1.14.1
refutes at pass 1 of the sizing loop, which prunes **75.9%** of candidates, and
v1.17.4 refutes at pass 2 — the first pass that carries the electric stage —
which kills a further **84–86%** of what pass 1 lets through. ⚠️  Both are
decisions rather than bounds: nothing is approximated, so no mission is lost.
⚠️  Turning the switch off restores the **pre-v1.14.1** search, not the v1.14.1
one, and an unpruned full cell is very slow.

🚨 **Do not budget any of this from a sample.** A stride sample has mispredicted
full-catalog runtime here by **3.1× high** and **4.8× low**, and a ratio between
two settings by **2.7×**, for opposite reasons: fixed costs dominate a small
run, while a stride sample under-represents the expensive tail of the
concentration sweep. Budget from a measured full run of the same cell, or do
not budget.

## Results

### Current results — the complete 20-cell matrix

Every destination × both settings of beneficiation × both settings of the
programme search, on the full 1,555,667-row catalog, 12 workers, 26.1 h of
compute, zero failures. `master.py` rebuilt from the modules with a clean
`git status`. Stage 2 priced once per destination on 2026-08-23 with live
prices verified identical across all five, so the destinations are comparable
by construction; Stages 1 and 3 were frozen for the whole campaign.

Best cost/revenue, lower is better, 1.0 is breakeven:

| destination | raw, N = 1 | raw, searched | benef, N = 1 | **benef + searched** (default) |
|---|---|---|---|---|
| **`cislunar`** | **26.7863×** | **15.4272×** | **20.5895×** | **13.1443×** |
| `lunar_surface` | 63.3505× | 38.9904× | 35.8051× | 22.5790× |
| `leo` | 71.1029× | 36.6889× | 48.2714× | 24.4678× |
| `mars_surface` | 74.6748× | 41.8068× | 55.3403× | 30.6818× |
| `earth_surface` | 42,953.98× | 12,977.88×† | 25,839.48× | 7,869.88×† |

† **Not an optimum** — at `earth_surface` market saturation is numerically
inert, so 100% of rows run to the fleet ceiling. See below.

Evaluable rows, raw / beneficiated: 650,921 / 660,253 (`cislunar`), 586,054 /
606,304 (`lunar_surface`), 776,755 / 882,429 (`leo`), 731,322 / 892,563
(`mars_surface`), 784,242 / 912,846 (`earth_surface`). The programme search
never changes the evaluable set, at any destination.

**Cislunar is still the best case, and by a wider margin than before** —
13.1443× against `lunar_surface`'s 22.5790×, a factor of 1.72 on the default
cell. The ordering cislunar < lunar_surface < leo < mars_surface <<
earth_surface reproduces the v1.14.0 raw ordering and now holds on all four
settings. Still **zero viable missions anywhere** — the best cell in the entire
model is a factor of 13 from breakeven, and the project's headline is unchanged.

**Twelve of these twenty cells had never been measured.** The four non-cislunar
beneficiated figures in the v1.11.0 matrix were placeholders on the old
89,367-row catalog and are retired: `lunar_surface` reads 35.8051× against that
table's 37.8133×, `leo` 48.2714× against 51.2223×, `mars_surface` 55.3403×
against 51.9597×.

**Reproduction.** All four cislunar cells and the `lunar_surface` and
`mars_surface` raw cells reproduce their committed values *exactly*, across
seven version stamps and a re-priced Stage 2 catalog. `leo` moves −0.004% and
`earth_surface` −1.75% — both live metal prices, not the model, and ordered
exactly as the pricing mechanism predicts: cells reproduce where
launch-cost-avoided dominates, and drift where a terrestrial price does.

**Invariants: clean on all twenty cells.** Never-worse holds on 20 pairings
with zero exceptions; the mass ledger closes to `0.000000000 kg` on every cell;
`N = F × W` on every row of all ten searched cells and `W > trips` never.

Winners: **2021 CX5 (D) takes 10 of the 20 cells** — all four at `cislunar`,
all four at `lunar_surface`, two at `leo`. **2016 PN38** (M) takes all four
`earth_surface` cells. `mars_surface` is the only destination whose winner
moves on every axis — 8651 (M), **2014 YN** (M), and **2001 UU92 (T)**, the
first T-type winner in this project's record.

#### Two results that change standing claims

**A `replicated`-scaling thruster does win, once.** At `mars_surface`, raw,
with the programme search on, 2014 YN (M) takes rank 1 on **FEEP** at 41.8068×,
13.4% clear of the runner-up, carrying 6,667 kg of thruster for 96.7 kW. Every
previous measurement had one of these devices surviving but never winning, at
best rank 5. The thrust gate is not broken — `thruster_kg_per_n` is a mass
penalty rather than a threshold, and this mission pays the mass and wins anyway
— but "never wins anywhere" is retired.

**`earth_surface`'s searched cells are not optima.** There the saturation
multiplier departs from 1.0 by a median of 2.3e−11, against cislunar's 1.9e−1:
terrestrial markets run 10¹²–10¹⁵ kg/yr against a programme delivering ~10⁷ kg,
so the price never moves. Every lever then improves with programme size,
nothing pushes back, and **100% of rows** run to `max_fleet_ships` = 64,
N = 320. The reported 12,977.88× and 7,869.88× are the value at the ladder's
top rung. The other four destinations are unaffected.

#### Three population results the single-cell tables could not show

**Iodine comes back at scale.** v1.11.0 claimed iodine won nine of ten cells;
v1.14.0 retired that when the eclipse term gave **xenon** 42–76% of every raw
N = 1 cell. Both were measuring single missions. Turn on both defaults and
iodine **overtakes xenon at `leo`** (42.74 vs 42.14%) and **wins
`earth_surface` outright** (47.31 vs 35.50%). Every propellant-share claim in
this project is a statement about a configuration, not about the model.

**Chemical propulsion reaches 11–15% of three destinations.** `methalox` goes
1.6–1.8% raw to 11.11–15.23% beneficiated at `leo`, `mars_surface` and
`earth_surface` — beneficiation drives mass ratio up, which is exactly where
the v1.11.0 tank term bites, and methalox is dense. Krypton moves the opposite
way for the same reason: 22.64% → 6.40% at `lunar_surface`.

**Mars inverts the rig's bounds.** This project's rig-bound figures are
cislunar's, where the *cycle* bound retires 96% of rigs raw. At `mars_surface`
beneficiated the **calendar** bound retires **80.79%**, because a Mars campaign
repeats every 3.8–4.0 years against ~1.37 elsewhere — the Earth–Mars synodic
period, on a separate heliocentric transfer. A Mars programme in this model has
a median span of **21 years**. Relatedly, "a programme's pace is set by orbital
mechanics, not mining rate" holds for raw everywhere (86–99.97%) and **inverts
under beneficiation** at every destination except Mars, where the dig sets the
pace on 66–83% of rows.

#### Runtime

**A default cislunar run is ~1.6 h**, and the full wall clock for all twenty
cells is in [Beneficiation](#beneficiation). ⚠️  Every timing older than calc
v1.17.7 is high by 1.78–4.32×, and so is every cost ratio derived from one —
see [what the v1.17.x line was worth](versions.md#what-the-v117x-line-was-worth).

## Version history

Every release note, and every measurement table these results superseded, is in
**[`versions.md`](versions.md)** — reorganised newest-first, with the module
versions each release carried. It used to live in this file and had grown to
roughly half of it.

The three that most often get quoted out of date:

- [calc v1.17.0](versions.md#calc-v1170) flipped **two defaults**, so a
  configure-nothing run no longer reproduces the N = 1 raw tables almost
  everything here was measured at.
- [catalog v1.1.0](versions.md#catalog-v110--calc-v1130) took the population
  from 89,367 asteroids to 1,554,400, which invalidates every figure older than
  it regardless of how sound the model was.
- [calc v1.14.0](versions.md#calc-v1140--transportation-v1110) made market
  saturation see programme size, which changed the **shape** of the
  programme-scale curve and not just its level.

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
  best case the model can reach — `cislunar` delivery plus beneficiation plus a
  searched programme — still comes in **~13× short** (**13.1443×**, full
  catalog, calc v1.17.7; **20.5895×** at a single mission). There is no "don't
  fly" option, so the ranking is really *which target loses least*.
  (This was `mars_surface` at ~25× until mineral_value v1.7.0 priced the local
  resources a planetary surface already has; Mars is now the *worst* of the
  four in-space destinations at 74.6748× raw.) **Scale does not rescue it**,
  and since v1.14.0 it does not even help monotonically — market saturation
  sees the programme's concurrent output, so the optimum programme size is
  interior. Searching it per body is worth about 40%, which is the difference
  between losing twenty dollars per dollar earned and losing thirteen.
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
- **The duty-cycle alternative to a battery is not priced.** Night-side power
  *is* charged, since v1.14.0 — but a rig could mine slowly in daylight instead
  of carrying storage, taking twice the stay rather than twice the plant.
  Where digging slowly is cheaper the model is now pessimistic. A free-flying
  array station-keeping off a small body would see almost no eclipse at all,
  and the pipeline cannot express that architecture either.
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

Every model below defaults **ON** and each one moved every number when it
landed. They are corrections, not options — the flags exist to isolate an
effect, not to be left off.

⚠️  **The count is deliberately not spelled out here.** It has rotted twice,
once in each direction, which is the exact failure the "when a number changes,
grep the prose too" rule in `CLAUDE.md` exists to catch. Count the list; do not
carry a number forward. One entry (orbital refuelling)
was later *withdrawn*, so the list is one longer than the charges.

They come in three species, and telling them apart is what makes the pattern
useful:

1. **Gaps in what the model charged for** — v1.7.0's five, all of which ran the
   same way, towards optimism; then v1.8.0 and v1.9.0's five, one of which
   (reliability growth) pushed back the other way.
2. **Masses flown and never billed, or bills presented for mass never flown** —
   v1.10.0 through v1.12.0. This is the defect class to look for in this
   codebase first: the mass cascade and the cost cascade are written in
   different places, and nothing checks that every kilogram in one has a price
   in the other. v1.12.0 found three fresh instances inside v1.11.0's own
   additions. The one-line assertion that catches the whole family is
   `hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg`.
3. **Terms whose figures were already written down, cited and correct, in a
   Stage 3 table Stage 4 does not load** — v1.14.0's two. Volatile cargo
   containment and night-side power had both been recorded as known limitations
   for two releases. *Writing a gap down had been mistaken for closing it.*

⚠️  **`use_beneficiation` and `optimise_programme_scale` are NOT on this list**,
and calc v1.17.0 defaulting both ON does not put them on it. They are questions
("ship concentrate or ore?", "how big a programme?"), not subsidies being
withdrawn. The test is not "is it on by default" — it is **"was the model
getting something for free before?"**

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

**Thruster scalability** (`thruster_kg_per_n`, v1.12.0). The largest single
correction in the project, and the clearest statement of the defect class:
**launch was modelled as an integrated vehicle with a payload it can actually
lift, while in-space propulsion was modelled as a bare specific impulse.** One
side had a capacity limit and the other did not, so Stage 4 sized the electric
stage on power alone and buying enough kilowatts turned any row in the
propellant table into a cargo tug — 31.8% of cislunar winners were pulsed
plasma thrusters and 24.3% electrospray, devices whose largest flown units make
*micronewtons*, being asked for ~7–10 N. The gate is **mass, not a threshold**:
thrust is momentum flux, so Stage 3 carries kg/N per technology and a device
making µN/kg reports thousands of tonnes of thruster and dies in the rocket
equation on its own. The evaluable catalog halved, and chemical propulsion came
back. ⚠️  Because it is a penalty rather than a cutoff, the right test is not
whether such devices *survive* but whether one ever **wins** — and as of
2026-08-24 one does, at `mars_surface` with the programme search on. That is
the mechanism working, not leaking.

**Argon storage** (v1.12.0, Stage 3). Not a flag — a reference-table fix, and
the one that moves numbers. The row carried liquid-argon density, which exists
only at 87.3 K, *together with* a boil-off of zero: its own two comments read
"liquid NBP (cryogenic storage)" and "stored supercritical at ambient
temperature", three lines apart. Argon was winning ~25% of missions on that
combination. Split into the two articles that actually exist. See
[calc v1.12.0](versions.md#calc-v1120--transportation-v1100).

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

### Added in v1.14.0, v1.15.0 and v1.16.0

**Volatile cargo containment** (`model_volatile_containment`, v1.14.0). The
pipeline priced water at every in-space destination, charged the energy to bake
it out of phyllosilicate and flew the array that does the baking — and charged
**nothing** to stop it subliming across a four-year cruise. Not a rounding
term: the best cislunar missions are **~88% water by mass**, so the commodity
carrying the entire result was the one flying free. A sealed shaded hold at
0.05 kg/kg, *incremental* to the 0.15 ore restraint — the hopper holds the
cargo, the seal and the shade keep the volatile fraction of it from leaving.
Charged on water only; carbon and organics are refractory at these temperatures
and ride in the hopper like rock.

**Eclipse and night-side power** (`model_eclipse_power`, v1.14.0). Processing
power is a *continuous average* draw and the plant was sized straight off it,
which is only right if the rig is never in shadow. It stands on a rotating
body. Two terms: an array oversize of `[(1−f) + f/η]/(1−f)` = **2.11×**, which
is a sizing factor no W/kg figure could ever have absorbed; and storage sized on
the **body's own rotation period**, which finally makes `rotation_period_h` —
carried by Stage 1 since v1.0.0 and read by nothing — a quantity the model
uses, so a slow rotator is genuinely a worse place to mine. Together they cost
**4.7×** at 1 AU and the median 10.2 h rotation, not the "roughly doubles" the
storage table itself estimated. ⚠️  A radioisotope plant is exempt because its
output is flat with time, and the EP array because it is in permanent sunlight
in cruise — it is the rig's plant that stands in the shadow, not the propulsion
train.

**The rig's duty cycles** (`model_rig_trip_limit`, v1.15.0). `life` is "Mining
rig service life" = **15 YEARS**, a figure whose own Stage 3 notes describe
corrosion, thermal cycling and radiation dose. Dividing it by the stay gave a
mission count, and **nothing anywhere bounded duty cycles** — so at a short stay
one rig was good for twelve consecutive digs on the strength of a number that
only ever promised it would not have rusted meanwhile. A rig parked between
campaigns ages slowly; one cutting rock does not. Stage 3 v1.12.0 adds a
maximum of **5 trips** and the min of the two bounds is taken, so long stays
stay calendar-limited and short ones are now cycle-limited. ⚠️  The 5 is a
documented judgement — nothing has ever mined an asteroid twice.

**Programme calendar time** (`model_programme_calendar`, v1.16.0). One rig digs
one hole at a time, so campaigns on a ship are strictly sequential — and the
cost model compounded each mission's up-front costs over that *mission's* own
duration and stopped, which for a programme assumes every mission happens at
once. The lines carried free are the **amortised** ones — bus NRE, autonomy
NRE, the rig — because those alone are bought once at t = 0 and divided across
missions that sell years apart. A mission's own articles are unaffected: shift
a whole cash flow later and its cost/revenue ratio does not move. ⚠️  Salvage
gets the **reciprocal** series, because it is collected at the *end*;
compounding a refund forward alongside the cost it is netted against would pay a
bonus for taking longer to collect it.

⚠️  **The last two are the only entries on this list that are inert at N = 1**,
so no single-mission figure moves for either — which also means neither can be
checked by re-running a headline.

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

Pre-git module copies, the original Colab notebook, and the parallel-repo
divergence that made `1.0.6` / `1.1.4` / `1.3.6` each mean two different things:
[Repository history](versions.md#repository-history).
