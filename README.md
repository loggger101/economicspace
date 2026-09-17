# economicspace: Asteroid Mining Profitability Pipeline

End-to-end pipeline that estimates, for every asteroid it can pull data on, the
net profit of an **uncrewed autonomous mining and sample-return mission**.

It chains four stages: build an asteroid catalog from public astronomy
databases → price the minerals those asteroids contain → cost the
transportation → run the rocket-equation and cost cascade to produce a ranked
profitability table.

## Contents

What the pipeline is, how to run it, and the current numbers. The release
history is in [versions.md](versions.md); the editing traps are in
[CLAUDE.md](CLAUDE.md).

- [Start here](#start-here)
- [Layout](#layout)
- [Running it](#running-it)
- [Rebuilding master.py](#rebuilding-masterpy)
- [Verifying a change](#verifying-a-change)
- [Working copy](#working-copy)
- [Output](#output)
- [Programme scale](#programme-scale)
- [Where the material is sold](#where-the-material-is-sold)
- [The propulsion and storage catalog](#the-propulsion-and-storage-catalog)
- [Beneficiation](#beneficiation)
- [Results](#results)
- [Version history](#version-history)
- [Mission model](#mission-model)
- [What the model does not capture](#what-the-model-does-not-capture)
- [What the model charges for](#what-the-model-charges-for)
- [What the model deliberately does not charge for](#what-the-model-deliberately-does-not-charge-for)
- [Data sources](#data-sources)
- [History](#history)

## Start here

**Double-click `_START HERE.vbs`.** That is the whole answer on Windows: it
opens the dashboard in your browser with no terminal window, and the small
control panel it puts up is what you close when you are done.

| you are on | open this | what you get |
|---|---|---|
| **Windows, no terminal** | **`_START HERE.vbs`** (double-click) | the dashboard, and nothing else to think about |
| Windows, a terminal | `run.bat` | a menu over the dashboard, the headless runs, verification and the build |
| Linux or macOS | `./run.sh` | the same menu, POSIX |
| any host, scripted | `py run_pipeline.py --preset quick` | one headless run, no menu |

⚠️  **`master.py` is not the entry point**, though it is the biggest file here
and looks like one. It is generated, it is what the four launchers above drive,
and editing it is destroyed by the next build. If you opened it looking for the
start button, close it and double-click `_START HERE.vbs`.

The dashboard opens ready to re-run Stage 4 against the catalogs already on
disk, which is the loop you want almost every time; press **Quick sample** in
the sidebar for a run that finishes in minutes. The long version of all of this
is [Running it](#running-it), and the dashboard itself carries the same three
steps behind a **Start here** panel at the top of the page.

## Layout

```
_START HERE.vbs        Double-click this: opens the dashboard, no terminal
launch_ui.py           What it runs -- starts the server, owns the stop button
run.bat                Windows launcher: a terminal menu over everything below
run.sh                 Linux / macOS launcher: the same options, POSIX
run_pipeline.py        Headless CLI the launcher drives (presets + flags)
build_master.py        Build tool: assembles modules/ into master.py
verify.py              Release verification: the checks every change runs
verify_stage3.py       Stage 3 verification: this repo and spacecost agree
verify_stage1.py       Stage 1 verification: the derivation chain, no fetching
verify_docs.py         Docs verification: the docs still describe the code
tree_check.py          Does the disk hold what git says it holds? ~0.4 s
platform_check.py      Can THIS host reproduce the committed numbers? ~10 s
.github/workflows/     CI: the checks that need no catalog, run on every push
platform_reference.json  What it compares against, recorded on the ref host
requirements-lock.txt  The exact versions every committed number was measured on
Dockerfile             Container image for a second host. No CUDA layer, on purpose
SPARK_SETUP.md         Standing this up on a DGX Spark (aarch64 Linux)
master.py              GENERATED single-file pipeline - do not edit by hand
ui.py                  Streamlit front end (optional): configure, run, inspect
ui_meta.py             Config introspection + curation for ui.py
modules/
    catalog.py         Stage 1 - asteroid catalog
    mineral_value.py   Stage 2 - mineral prices + densities
    transportation.py  Stage 3 - ADAPTER over the spacecost package
    calc.py            Stage 4 - profitability calculation
campaign/              The 28-cell measurement campaign: results.csv, the
                       archived cells, FINDINGS.md, and the scripts that ran it
research/              Investigations that are not part of a run. starred-repos/
                       audits 17 external projects against this pipeline and
                       carries the probes that measured what they were worth
README.md              This file: what it is, how to run it, current numbers
versions.md            What changed in which release, what numbers used to be,
                       and the per-module changelogs
CITATIONS.md           Every source, dataset and borrowed line, and what each
                       obliges. Two of them require citation as a condition of use
CLAUDE.md              Working notes: the traps and invariants. Read before editing
```

**The split between these documents is deliberate**, because the recurring
failure in this repo is a stale sentence rather than a missing table. The table
is the list; its length is deliberately not spelled out beside it:

| file | holds | is the authority for |
|---|---|---|
| `README.md` | what the pipeline is, how to run it, what the model does, and the **current** numbers | the current answer |
| [`versions.md`](versions.md) | what changed in which release, what every number used to be, and the per-module changelogs | the measurement history |
| [`CITATIONS.md`](CITATIONS.md) | where every source, dataset and borrowed line came from, and what each obliges | references and attribution |
| [`CLAUDE.md`](CLAUDE.md) | the traps, the invariants, and the reasoning behind decisions that look wrong | how to edit it safely |
| the [`spacecost`](https://github.com/loggger101/spacecost) repo | Stage 3's reference tables, their citations, and their release history | every launch, propellant, delta-v, operational and storage row |

### Stage 3's tables live in another repository

**[`spacecost`](https://github.com/loggger101/spacecost)** holds every Stage 3
reference row: the 36 launch vehicles, the 41 propellants with their storage
classes and derived tankage, the Δv segments, the operational costs and the
storage systems, each with its inline citation. `modules/transportation.py` is
now a thin adapter that drives it, where two thirds of what it used to hold
was reference data.

They left because nothing in their schema knew what an asteroid was, and a
launch price is useful to anyone costing a mission. This pipeline is that
package's first consumer.

**Nothing about the model changed.** The six CSVs Stage 4 reads are byte
identical, `pipeline_version` is the same `1.14.0`, and all four Stage 4 cells
reproduce their committed hashes. Two checks say so and both are cheap:

```bash
py verify_stage3.py
```

⚠️  **A split is what caused this project's worst recorded incident**, when it
was briefly developed in two places and three version stamps each shipped as
two different things (see
[the parallel-repo divergence](versions.md#the-parallel-repo-divergence)). What
made that expensive was that nothing checked it, so this one is arranged so that
drift cannot be committed rather than merely being unlikely: the data is
single-sourced, the ten config dials are compared at import, and the output is
compared byte for byte. **The invariants, and what fails when each breaks, are
in [CLAUDE.md](CLAUDE.md#stage-3-lives-in-another-repository-now)**, which is
where the editing rules live.

**spacecost is pinned to a tagged release**, `v0.1.1`, in both
`requirements.txt` and `_MASTER_REQUIRED`. An untagged URL would let a fresh
install pick up a different table with nothing here moving.

`run.bat`, `run_pipeline.py`, `ui.py` and `ui_meta.py` sit at the root rather
than in `modules/` on purpose:
`build_master.py` concatenates everything in that directory into `master.py`
and asserts a specific header/footer shape on each file. All four are
consumers of the built `master.py`, not stages of it.

Each module is a standalone file: run it directly to build just that stage, or
import it for its functions without triggering a run. They share no Python
imports, stages hand off through CSVs on disk, not through each other's
namespaces (see [Stage dependencies](#stage-dependencies)).

| Stage | Module | Version | What it does |
|-------|--------|---------|--------------|
| 1 | `modules/catalog.py` | 1.2.0 | JPL SBDB + MP3C + SsODNet ssoBFT + NEOWISE; merge, dedupe, validate, enrich with per-spectral-type PGM factors |
| 2 | `modules/mineral_value.py` | 1.9.0 | Live yfinance futures, USGS/LME reference prices, in-pipeline mineralogy, destination pricing for every commodity, per-destination ISRU discounts |
| 3 | `modules/transportation.py` | 1.14.0 | Drives [**spacecost**](https://github.com/loggger101/spacecost): 36 launch vehicles (incl. non-rocket concepts), 41 propellants with storage class and tankage, Δv segments (incl. the delivery ladder above LEO), operational costs, storage systems |
| 4 | `modules/calc.py` | 1.22.0 | Per-asteroid Δv **and mission architecture**, and, by default since 1.17.0, **programme size, fleet size and schedule**, in-space delivery, beneficiation, rocket-equation mass cascade (incl. tankage) + cost cascade → net profit, ROI, $/kg-returned |

⚠️  That version column is checked against the modules' own `pipeline_version`
fields, and it has rotted before: it read catalog 1.1.0 / transportation 1.12.0
/ **calc 1.16.0** until 2026-08-21, when calc was four releases past it. The
authority is the dataclass field in each module, never this table.

**What each version changed is in [`versions.md`](versions.md)**, newest first.
⚠️  A version bump does **not** mean a number moved: performance, dead code
and a flipped default have all moved a stamp on their own. The rule is
one-directional, and the stamps that did it are listed in
[versions.md](versions.md#how-the-version-numbers-work). Count that table
rather than trusting a number here: this sentence has now carried a stale one
four times.

## Running it

### On Windows: double-click `_START HERE.vbs`

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

### On Linux or macOS, from a terminal: `run.sh`

The POSIX counterpart of `run.bat`, with the same options and the same
semantics, so `./run.sh quick leo` does what `run.bat quick leo` does:

```
./run.sh setup     create .venv and install the pinned requirements
./run.sh platform  can this host reproduce the committed numbers (~10 s)
./run.sh inputs    are the CSVs Stage 4 reads on disk (fetches nothing)
./run.sh build     rebuild master.py from modules/
./run.sh quick     400-row sample, all four stages
./run.sh rerun     Stage 4 only, against the catalogs already on disk
./run.sh standard  20,000-row sample, Stage 4 only
./run.sh full      THE PIPELINE DEFAULTS (3.2 h at cislunar, 6.1 h at earth_surface)
./run.sh verify    verify_stage3.py, then verify.py against the newest baseline
./run.sh campaign  the resumable measurement queue
./run.sh ui        the dashboard, in the foreground, reachable over the network
./run.sh help      run_pipeline.py --help
```

Three differences from `run.bat`, all of them about the host rather than the
model. `setup` exists because Linux has no equivalent of the Windows launcher
finding an interpreter for you. `platform` and `inputs` exist because a second
host is the case where the arithmetic and the input files are both worth
checking before spending a day, and neither question arises on the machine the
numbers were measured on. And `ui` runs Streamlit in the foreground on
`0.0.0.0` rather than handing off to `_START HERE.vbs`, because a headless box
has no desktop to put a control window on; it prints the addresses that will
resolve from another machine, and Ctrl-C is the stop button.

It inherits `run.bat`'s rule that **nothing prompts once an argument was
given**. `read` against a stdin that a scheduled job holds open but never
writes to hangs rather than exiting, so the destination prompt is guarded on
both "no argument" and "stdin is a terminal"; the test is
`./run.sh quick < /dev/null`, not a run from a console.

[`SPARK_SETUP.md`](SPARK_SETUP.md) is the long version: what was already
portable, what was not, the one thing that cannot be guaranteed on a second
host and has to be measured instead, and the ~868 MB of input CSVs that git
does not carry.

### On Windows, from a terminal: `run.bat`

`run.bat` is the whole pipeline behind a menu -- the same dashboard, plus the
headless runs, verification and the build. It finds Python, offers to install
anything missing, and dispatches. It takes an argument if you would rather skip
the menu:

```
run.bat ui         open the dashboard (hands off to _START HERE.vbs, then
                   closes this window -- no terminal stays up)
run.bat quick      400-row sample, all four stages
run.bat rerun      Stage 4 only, against the catalogs already on disk
run.bat standard   20,000-row sample, Stage 4 only
run.bat full       THE PIPELINE DEFAULTS (3.2 h at cislunar, 6.1 h at earth_surface)
run.bat verify     verify_stage3.py, then verify.py against the baseline
run.bat build      rebuild master.py from modules/
run.bat help       run_pipeline.py --help
```

It is a launcher and nothing else. Four of its options go through
`run_pipeline.py` and one through the dashboard, and from there through
`master.py`; `verify` calls `verify.py` and `build` calls `build_master.py`.
No model behaviour lives in it, and it adds no default the pipeline does not
already have, except that `quick` and `standard` cap rows and fly raw ore at
N = 1 rather than starting the multi-hour default cell on a double-click.

**Stages 1-3 re-fetch and overwrite, so they ask first.** Each replaces the
only copy of its CSV; there is no history and no undo, and every `verify.py`
baseline is built against those exact bytes. `run_pipeline.py` names what a
run would re-fetch and waits for a `yes`, unless the file does not exist yet
(nothing to lose) or you pass `--yes`. `run.bat` passes `--yes` on any
invocation carrying an argument, so a scripted or scheduled `run.bat quick`
still runs unattended; the menu asks.

⚠️  **The presets exist because the pipeline's own defaults are a long run.**
Since calc v1.17.0 a configure-nothing run is the full 1.55 M-row catalog,
beneficiated, with the programme search on, at `earth_surface`: **measured at
21,860 s (6.1 h)** in the 2026-09 28-cell campaign, against 9,878 s (2.7 h) for
the same cell at `cislunar`. ⚠️  Both are **calc 1.21.2** measurements and
neither has been re-taken since v1.22.0 gave the payload knapsack a second
price tier, so read them as a floor. ⚠️  This paragraph read 13,581 s / 5,692 s
until 2026-09-15 and said they had "not been re-taken since v1.21.0", which the
28-cell campaign above had already done: **a caveat naming the release that
would retire it does not expire on its own.** The configuration they describe
-- every row, beneficiated, search on -- is unchanged. That is the right default for the model and a hostile
one for a double-click, so `quick` and `standard` cap the rows and fly
run-of-mine ore at N = 1. The row cap is a **stride sample across the whole
belt**, not the innermost N bodies; see calc v1.13.0.

**`full` is the only preset that overrides nothing**, and every run says so
explicitly: each setting is printed marked `[default]`, or
`[default: <the value it replaced>]`, so a run is never ambiguous about which
question it answered.

```
  Destination  : cislunar             [default: earth_surface]
  Asteroids    : all (1.55 M)         [default]
  Stage 4 rows : 400 (stride sample)  [default: every row]
  Ore          : run-of-mine          [default: beneficiated (~4.7x slower)]
```

Those labels are read from the config dataclasses at runtime, not hardcoded, and
`run_pipeline.py` warns on stdout if `full` ever stops matching the declared
defaults, so flipping a default in a module cannot leave the label behind.

The launcher also sets the **delivery destination in one prompt**, which
`run_pipeline.py` writes through `MASTER_CONFIG` so Stage 2 and Stage 4 cannot
disagree.

### Headless, on any platform

`run_pipeline.py` is the launcher's engine and works on its own:

```bash
py run_pipeline.py --preset quick
py run_pipeline.py --destination cislunar --raw --no-search --rows 5000
py run_pipeline.py --stages 4 --destination cislunar --preset full --yes
py run_pipeline.py --market-model elasticity --stages 4 --destination cislunar
py run_pipeline.py --help
```

`--market-model` is applied **after** the preset, so
`--preset full --market-model single_mission` pins N = 1 whatever the preset
said about the programme search. `--market-model elasticity` restores the pre-v1.21.0 demand curve.

**calc v1.22.0 added four more model flags, for the same reason.** Each names a
default that release moved, each is applied after the preset, and together they
put a run back on v1.21.2's model:

```bash
py run_pipeline.py --stages 4 --destination cislunar --raw --no-search \
    --no-surplus-sales --reliability --learning-curve --cost-of-capital
```

That command reproduces the committed v1.21.2 sample cell exactly: **25.7233x
on 155 evaluable rows, 2017 KJ5**. Individually, `--no-surplus-sales` restores
the v1.21.0 hard wall (and `--surplus-fraction F` sets what the surplus fetches
otherwise, 0.0 to 1.0, refused outside it), `--reliability` puts the
`P(launch) x P(cruise) x P(mining)` discount back on revenue,
`--learning-curve` restores Wright's law on recurring hardware, and
`--cost-of-capital` restores WACC compounding **and with it the programme
calendar charge**, which is time-value and inert without a rate.

⚠️  **Reproducing the 28-cell matrix takes all four**, not a subset: they do
not act in the same proportion on every cell and one of them runs the other
way. See [calc v1.22.0](versions.md#calc-v1220).

⚠️  It does **not** reproduce pre-v1.21.0 figures exactly. calc v1.21.1 gave the
composition residual a market ceiling, and that defect was in the curve too, so
the curve moved with it: the raw cislunar cells by +2.36% and +5.82%, the
beneficiated ones not at all. For an exact reproduction use a build of the
release you are reproducing, which is what the `pipeline_version` stamp on every
CSV is for.

`--stages` takes digits, so `--stages 4` reuses the CSVs already on disk for
the other three, the normal working loop, and what saves the 224-second
catalog rebuild.

**Give `--stages 4` an explicit `--destination`.** Stage 2 decides what a
kilogram sells for and Stage 4 decides the architecture that puts it there, so
the two must agree, and both configs default to `earth_surface` while the
catalog on disk is whatever destination was last priced. A Stage-4-only run
that disagrees is refused before it starts, with the destination the catalog
actually holds named in the message, so this costs you one flag rather than a
wasted run.

### From source

Python 3.9+ (developed on 3.13, currently run on 3.14). Then:

```bash
pip install -r requirements.txt
```

On Windows, invoke the launcher `py` rather than `python`, a bare `python`
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

`master.py` is also designed to be pasted straight into a Colab or Jupyter cell,
it auto-installs its own dependencies and runs top-to-bottom.

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
tune the orchestrator, with a browser attached. What is worth knowing, in the
order you meet it:

- **A Start here panel** names the file that opens the page and the three
  steps, expanded on a machine that has never produced a profitability catalog
  and collapsed once it has.
- **The three presets are the launcher's**, imported from `run_pipeline.py`
  rather than restated, so the sidebar's **Quick sample** and `run.bat quick`
  are the same run by construction. Each button says what it sets, and a line
  underneath says what the dials currently add up to.
- **Every config field is introspected**, not hand-listed, so a field added to
  any of the four dataclasses appears automatically. The help text on each
  field is scraped from that field's own comment block in the module source.
  A curated ⭐ Common tab pins the dials that actually move results, and a
  **Find a setting** box searches names and help text across all four configs
  at once, replacing the tabs while it has anything in it.
- **Stages are individually selectable and reuse the CSVs on disk.** Re-running
  Stage 4 alone against a cached catalog is the normal working loop, and it
  saves the 224-second catalog rebuild a full run repeats. Pair it with
  `eval_row_cap`, at the v1.1.0 catalog size an uncapped Stage 4 is hours, and
  since calc v1.13.0 a capped one is a representative sample of the whole belt
  rather than the innermost N bodies. Skipping Stage 2
  after changing the destination is blocked rather than merely warned about,
  because a mineral catalog priced for one destination and a mission flown to
  another produces meaningless numbers that still look plausible.
- **Each run writes `ui_run_config.json`** beside the outputs: the full config
  snapshot, the stages run, and the diff from defaults. `pipeline_version`
  identifies the code that produced a CSV but not the configuration, and this
  repo's recurring failure is a number nobody can trace.
- **The drilldown draws the orbit**, top down and edge on, from the body's own
  elements read back out of the Stage 1 catalog, with the apsis the
  architecture search chose to meet it at marked. Earth and Mars are drawn as
  circles because that is what the Delta-v model assumes, and a truer ellipse
  would disagree with the numbers beside it. It also reports how well the orbit
  is KNOWN when the catalog says: the top of this ranking is enriched roughly
  threefold in bodies whose orbits are provisional, which
  [`research/starred-repos`](research/starred-repos/SPACE-MAP.md) measured and
  which no cost figure can show on its own.

The UI ranks by `total_cost_usd / gross_value_usd` rather than `profit_usd`,
for the reason given in [Reading `profitability_catalog.csv`](#reading-profitability_catalogcsv).
It reads and displays only; every number still comes from the pipeline.

### Stage dependencies

Stages 1, 2 and 3 are independent of each other and can be run in any order or
alone. **Stage 4 is not**; `modules/calc.py` reads the CSVs the other three
wrote, so it needs a populated `output_dir` before it will do anything. Run the
full `master.py` at least once, or run stages 1-3 individually first.

### What a first run costs

> ⚠️  **These figures changed by more than an order of magnitude in catalog
> v1.1.0.** Every row cap now defaults to unlimited, and the catalog went from
> 89,367 asteroids to **1,554,400**. A default end-to-end run is no longer a
> coffee break; budget an afternoon, and set the caps if you want the old
> behaviour back.

- **Stage 1** takes **224 s** at the unlimited default and writes a **0.88 GB**
  CSV (measured 2026-08-08, warm SsODNet cache, ~6 GB peak RAM). The JPL pull
  alone is 1,554,321 asteroids / 401 MB / 24 s. Set `jpl_limit = 50_000` to
  reproduce the pre-v1.1.0 couple-of-minutes, ~30-40 MB run.
- SsODNet's ssoBFT table is a **~500 MB parquet bulk download** on first run.
  It is cached and re-used for `cache_max_age_days` (7 by default). The cache
  lives in the system temp directory, deliberately *not* under `output_dir`, 
  on a Google Drive working copy that keeps half a gigabyte from re-syncing
  every run. Point `CATALOG_CONFIG.cache_dir` somewhere else if you want it
  co-located.
- **Stage 4 is the long pole by far**, because `eval_row_cap` defaults to `0`
  (evaluate everything), "everything" is 1.55 M rows, and both beneficiation
  and the programme search are on by default. The twenty-eight measured cells
  are tabulated under [Beneficiation](#beneficiation) and are not restated
  here: at cislunar the default cell is **2.7 h**, and the other six
  destinations span **0.73-2.95×** that, `lunar_surface` being the one that
  runs FASTER rather than slower. Set `eval_row_cap` for anything
  interactive: as of calc v1.13.0 a capped run is an evenly-spaced sample of
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
| `MASTER_CONFIG.delivery_destination` | `"earth_surface"` | **Read [Where the material is sold](#where-the-material-is-sold) before changing.** Sets every price *and* the mission architecture. One of `earth_surface`, `leo`, `geo`, `cislunar`, `lunar_surface`, `mars_orbit`, `mars_surface`. Writes Stage 2 and Stage 4 together, never set the two sub-configs separately |
| `.calc.use_beneficiation` | `True` | Return concentrate instead of run-of-mine ore. Charges the extra dig time, processing energy and solar-array mass. **Default since calc v1.17.0**; almost every historical table is `False`. See [Beneficiation](#beneficiation) |
| `.calc.beneficiation_recovery` | `0.90` | Fraction of the valuable phase reporting to concentrate |
| `.calc.max_concentration_ratio` | `50.0` | Safety cap on feed:concentrate. The purity bound normally binds first |
| `.calc.use_per_asteroid_dv` | `True` | Δv from each asteroid's own orbital elements. `False` gives every asteroid the same Δv |
| `.calc.mining_rate_kg_per_day_per_kg_rig` | `0.10` | Extraction throughput per kg of rig; caps payload and sets time at the asteroid |
| `.calc.max_mining_duration_yr` | `3.0` | Ceiling on time at the asteroid, binds how much you can return |
| `.calc.nre_recurring_overlap_fraction` | `0.30` | Development share already inside the per-kg recurring rate; `0.0` books both in full |
| `.catalog.jpl_limit` | `0` | Asteroids fetched from JPL; `0` = all 1,554,321. The only source of orbital elements, so it bounds the catalog |
| `.catalog.ssodnet_limit` / `neowise_limit` / `mp3c_limit` | `0` | Per-source caps, `0` = unlimited. One shared cap until v1.1.0, which made the catalog smaller than any single source |
| `.catalog.derive_diameter_from_h` | `True` | Size bodies with no measured diameter from H + an assumed albedo. `False` → ~149,600 rows instead of ~1,554,400 |
| `.catalog.min_derived_diameter_km` | `0.0` | Floor on *derived* diameters only. Trims the sub-km tail, where the albedo assumption hurts most |
| `.catalog.min_diameter_km` | `0.001` | Size floor. Raise to `1.0` to study km-class bodies only |
| `.catalog.require_spectral_type` | `False` | `True` drops untyped rows; fewer asteroids, but every one has a composition |
| `.catalog.use_jpl` / `use_mp3c` / `use_ssodnet` / `use_neowise` | all `True` | Per-source toggles. Turning off SsODNet skips the 500 MB download |
| `.calc.eval_row_cap` | `0` | Stage-4 evaluation cap; `0` evaluates every row. Was `5_000`, which discarded 99.7% of a v1.1.0 catalog |
| `.calc.eval_row_sampling` | `"stride"` | How a cap picks rows. `"stride"` samples the whole belt evenly; `"head"` is the pre-v1.13.0 innermost-N behaviour |
| `.calc.parallel_workers` | `0` | Stage-4 worker processes. `0` picks a count from the CPU count and the amount of work; `1` forces the single-core path. See [Parallel evaluation](#parallel-evaluation) |
| `.calc.max_mining_fraction` | `0.05` | Share of asteroid mass one mission may remove |
| `.calc.use_aerocapture_return` | `True` | Makes aerocapture *available*. Trades return Δv for a TPS mass penalty (15% of payload); Stage 4 prices both and flies whichever pays, per asteroid |
| `.calc.use_isru_return_propellant` | `True` | Makes ISRU *available* at bodies whose composition supplies the propellant, with the extra rock dug, timed and charged |
| `.calc.operational_propellants_only` | `True` | Restrict the search to propellants that have flown. `False` admits Stage 3's development and concept rows: nuclear thermal, VASIMR, fusion, Orion pulse |
| `.calc.model_tank_mass` | `True` | Put propellant tankage in the rocket equation. Tank mass scales with volume, so this is what stops low-density propellants flying their tanks for free |
| `.calc.allow_rtg_power` | `True` | Let the processing plant use radioisotope power where it is lighter than solar (past 3.46 AU), capped by `rtg_max_power_w` |
| `.calc.charge_tanker_flights` | `True` | Charge the orbital-refuelling flights a vehicle's escape payload assumes |
| `.calc.charge_insurance` | `False` | Charge Module 3's two insurance premiums: a $1.5M third-party liability flat and launch insurance at 10% of (launch + spacecraft book value). **Off since calc v1.20.0** because a premium is priced off an underwriter's book rather than off a mass; every table measured before it is a `True` run. See [What the model deliberately does not charge for](#what-the-model-deliberately-does-not-charge-for) |
| `.calc.optimise_architecture_per_asteroid` | `True` | Search return mode and propellant sourcing per target rather than fixing them catalog-wide |
| `.calc.selection_objective` | `"cost_revenue_ratio"` | What the per-asteroid search maximises. `"profit"` restores pre-v1.10.0 behaviour |
| `.calc.return_structure_frac_of_payload` | `0.15` | Return-vehicle structure as a fraction of the haul, on top of the 500 kg base |
| `.calc.nre_amortization_missions` | `1` | Programme size N. With the search on it is the FLOOR rather than the answer |
| `.calc.optimise_programme_scale` | `True` | Search programme size and fleet size per asteroid instead of setting N. **Default since calc v1.17.0.** It changes the question the run answers, so most historical tables are `False`, at N = 1. See [Programme scale](#programme-scale) |
| `.calc.market_model` | `"capacity_cap"` | What a delivered kilogram sells for and how much of it clears. `"capacity_cap"` holds price constant and clips quantity at Stage 2's `annual_market_kg`; `"single_mission"` pins N = 1; `"elasticity"` is the v1.14.0 demand curve (it reproduced v1.14.0 to v1.20.0 exactly until v1.21.1's residual-ceiling fix moved the two raw cells, and v1.21.2 moved it again by pooling the two silicate phases onto one ceiling); `"unbounded"` is a diagnostic. **Default since calc v1.21.0**, replacing the `model_market_saturation` flag. See [The market model](#what-the-model-charges-for) |
| `.calc.demand_elasticity` | `0.5` | The e in `(1 + Q/Q_market)^(-1/e)`. Read ONLY when `market_model` is `"elasticity"` |
| `.calc.sell_surplus_at_discount` | `True` | Sell what is past a market ceiling at a discount instead of abandoning it. **Default since calc v1.22.0**; `False` is v1.21.0's hard wall, which is what the 2026-09 campaign measured. Ceilings still bound the programme, because the marginal kilogram past one is worth strictly less than the one before it. See [The market model](#what-the-model-charges-for) |
| `.calc.surplus_price_fraction` | `0.5` | What a kilogram past a ceiling fetches, as a fraction of the full price. Read ONLY when `sell_surplus_at_discount` is `True`; `0.0` reproduces the wall |
| `.calc.max_fleet_ships` | `64` | Where the fleet ladder stops. Rows piling up against it mean their payloads have no finite market, not that bigger is better; the run says so |
| `.calc.programme_search_steps` | `8` | Rungs in the coarse fleet sweep, before one refinement pass. Same idiom as `concentration_search_steps` |
| `.calc.model_rig_trip_limit` | `True` | Cap rig life in duty CYCLES as well as calendar years. Inert at N = 1 |
| `.calc.model_programme_calendar` | `True` | Charge the calendar a programme actually spans: the NRE and rig are bought once and carried across every campaign. Inert at N = 1; also what makes the programme search two-dimensional |
| `.calc.contingency_fraction` | `0.20` | Flat contingency on the cost cascade |
| `.calc.apply_wacc_compounding` | `False` | Cost of capital: compound up-front costs over the mission, bucketed by when each is incurred, at Module 3's 10% WACC. **Off since calc v1.22.0** because a discount rate is a statement about whose money this is, which is outside a marginal-cost model; it also silences `model_programme_calendar`, whose multipliers are exactly 1.0 at a zero rate. See [What the model deliberately does not charge for](#what-the-model-deliberately-does-not-charge-for) |
| `.calc.model_reliability` | `False` | Multiply expected revenue by `P(launch) x P(cruise) x P(mining)` while charging every cost in full. **Off since calc v1.22.0**: two of those three are assumptions about a machine nobody has built, and multiplying the answer by them buries them in every headline. A default run now answers what it costs IF IT WORKS |
| `.calc.model_reliability_growth` | `True` | Let `p_mining` grow across a programme under the Duane model rather than sitting at the first-of-kind figure. Inert while `model_reliability` is off |
| `.calc.model_learning_curve` | `False` | Apply Wright's law to recurring hardware across a programme. **Off since calc v1.22.0**: it is a statement about a factory's learning, fitted to programmes that built dozens of articles, and this one prices the marginal physics. Exactly inert at N = 1 either way |
| `.calc.learning_curve_rate` | `0.85` | Wright's-law rate: each doubling of cumulative production cuts unit cost to this. Read ONLY when `model_learning_curve` is `True` |
| `.mineral.metals_api_key` | `"DEMO"` | Set a real metals.dev key to enable that source; `"DEMO"` silently skips |

⚠️  **`use_isru_return_propellant` and `use_aerocapture_return` mean
"available", not "mandatory".** Stage 4 prices every feasible combination per
asteroid and flies the one that pays, so these do not force an architecture on
the catalog. ISRU is additionally gated on physics: the propellant has to be
makeable from what the body is actually made of, and the rock it takes is dug,
timed and charged like any other feed.

"Makeable" is not only hydrolox. Electrolysing water into cryogenic hydrogen
and oxygen is the *hardest* thing you can do with asteroid water; a steam
rocket boils it and thrusts on the vapour at **1.00 kg of water per kg of
propellant** against hydrolox's 1.286, with no electrolyser, no liquefaction
and no cryogenic tank, and buys that at 190 s of specific impulse against 452.
Which trade wins varies by body, so it is resolved in the per-asteroid search.
Stage 3 states the feed ratio and the feed material on each propellant row.

🚨  **The dangerous corner is ISRU on *and* aerocapture off**, and what closes
it is `return_structure_frac_of_payload`. Without a payload-proportional term
in the cascade nothing scales with returned mass, the launch-mass constraint
goes slack, and a 30 km body "returns" 7.4e14 kg in a 500 kg capsule for a
fictional $7.8e17 profit. **Set that field to `0.0` and the corner reopens.**

Importing `master.py` is side-effect free, so you can drive it yourself:

```python
import master
results = master.run_full_pipeline()
```

### Parallel evaluation

Stage 4 evaluates each asteroid independently of every other one; the search
reads the reference tables and writes nothing, so since calc **v1.10.1** it
does that across a process pool instead of on one core.

**No number changes.** Serial and parallel output is byte-identical, and that
is one of the checks `verify.py` runs on every release. Chunks are consumed
in submission order specifically so that the row order, and therefore the
ordering of `profit_usd` ties under a non-stable sort, is unchanged.

Roughly 1.9× of the gain is single-threaded and applies even at
`parallel_workers = 1`: catalog rows are converted to plain dicts before the
inner search (pandas resolved ~7,400 index lookups per asteroid, ~38% of the
whole run), and the sizing loop's five Stage-3 constants are memoised rather
than looked up ~24 million times.

Leave `parallel_workers` at `0` unless you have a reason:

- **`1`** forces the serial path, for profiling, or when an outer harness is
  already running one process per destination and the cores are spoken for.
- **A specific count** is obeyed, clamped to the CPU count.

Auto mode will not start a worker that cannot repay its own startup, so short
interactive runs stay serial. That matters more than it sounds: startup is
~1.1 s per worker and **linear**, because each worker re-imports the 590 kB
`master.py` (Windows has no fork), and on a Google Drive working copy those
reads serialise. At 3,000 beneficiated rows, twelve workers is slower end to
end than six. The useful ceiling is the **physical** core count, hyperthreading
adds ~17% on this branch-heavy pure-Python workload, not 2×.

🚨  **If you drive the pipeline from your own script, import it by name.** A
spawned worker rebuilds the parent by importing `__main__`, and
`_spawn_environment` in `modules/calc.py` repoints that at the pipeline module
so a plain `Pool()` under Streamlit does not execute the whole app once per
worker. **The guard fails silently unless `master` is in `sys.modules` under
its own name**, which loading it by file path does not do, and then every
worker executes *your harness* as `__main__` instead:

```python
sys.path.insert(0, REPO)
import master as m
assert sys.modules.get("master") is m and m.__spec__ is not None
```

If your driver script re-runs itself once per worker, that is why; the full
account is in [CLAUDE.md](CLAUDE.md#entry-points).

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
master would quietly run the wrong function; syntax-checking cannot see it.
A clean build ends with `names : no unexpected shadowed definitions`. If it
instead lists a name, either add a `word_replace()` rename in `build_master.py`
or, if the duplication is deliberate and identical in every copy, add the name
to `_EXPECTED_DUPES`.

Commit the rebuilt `master.py` alongside the module change; it is tracked,
and `git status` after a build is the check that the two are in sync.

## Verifying a change

Almost every release of Stage 4 is argued from **bit-identity**: the claim is
not "the numbers look right", it is "these are the same floats, and here is the
hash". `verify.py` is those checks, committed:

```bash
py verify.py baseline --tag 1.17.7
```

Run that on a clean tree **before** editing. It builds four cells, raw and
beneficiated, each with the programme search off and on, and writes their CSVs
and hashes under `.verify/` (gitignored). Then make the change, rebuild, and:

```bash
py verify.py check --tag 1.17.7
```

which runs every check in this table. ⚠️  **Count the rows; the number is
deliberately not written here.** This sentence read "all six" above seven of
them from the day check 7 was added, which is the counts-in-prose failure the
whole [docs harness](#verifying-the-docs) exists to catch, sitting in the
section about verification.

| # | check | catches |
|---|---|---|
| 1 | bit-identity vs the baseline | any change to any number, column by column and by hash |
| 2 | pre-filter on vs off | the pruner and the solver drifting apart; they are two statements of one algebra |
| 3 | serial vs 8 workers | a worker seeing different reference data from its parent |
| 4 | mass ledger | a kilogram in the rocket equation with no price in the ledger |
| 5 | never-worse | a search optimising something other than what it reports |
| 6 | Stage 2 tables | a judgement-table edit that moved a number, or a commodity falling through a silent default |
| 7 | market ceilings | a capacity ceiling that pays rather than costs, and the three market columns swapping meanings: `saturation_multiplier`, `unsold_payload_kg` and v1.22.0's `surplus_payload_kg` |

`py verify.py invariants` runs 4, 5 and 6 only and needs no baseline, so it
works on any tree and is the fast way to check an upstream table edit;
`--cells` takes a subset.

🚨  **"On a clean tree, before editing" is enforced now, not merely asked
for.** It was a documented discipline with nothing behind it, and its failure
is silent in the worst way: baseline a tree that already carries the change and
check 1 compares the change against itself and prints **MATCH** on all four
cells, which is then what the release note argues from. `baseline` records the
commit it was taken on and whether `modules/`, `build_master.py` or `master.py`
differed from HEAD at the time; `check` reads that back and **refuses** a
baseline taken over a modified model path, the same way it refuses one that is
missing. Pass `--allow-dirty-baseline` when the edit really was unrelated,
which only the person who made it can know.

⚠️  Docs, harnesses and campaign scripts are deliberately **not** model paths:
they cannot move a number, and failing on them would be the cry-wolf shape this
repo records twice. ⚠️  And the dirtiness test is `git diff`, never
`git status`, because on a Google Drive working copy `status` reports files as
modified without reading them; see
[the Drive stat-cache trap](CLAUDE.md#google-drive-makes-the-tree-look-dirty-run-the-hooks).
A baseline written before this field existed reports `not recorded` and is
allowed through, since nothing can be inferred about a tree that is gone.

⚠️  A full `check` builds about twenty cells and takes **roughly half an hour**.
Most of that is check 2; turning the pre-filter off is exactly what v1.14.1 and
v1.17.4 exist to avoid, so an unpruned cell runs the entire search. Iterate with

```bash
py verify.py check --skip prune parallel
```

which is ~5 minutes and still catches any change to any number, then run the
full set once before committing. A verification you will not run is worse than
a slow one.

**Why it is committed rather than rewritten each time.** Before 2026-08-21
every release built these checks from scratch and threw them away, and a
harness bug came out of it nearly every time; several produced conclusions that
were written down before being caught, and calc v1.22.0 added one more to that
tally by publishing a runtime table it then had to retract. Each trap is
defended against at the line that would otherwise reproduce it, `verify.py`'s
header lists them, and the four hashes it prints reproduce the ones committed
for calc v1.17.4 and v1.17.6 exactly, which is what makes it a replacement for
those harnesses rather than another one to have to trust. **Add to that list
rather than starting another harness.**

⚠️  **Read that list before writing any comparison of your own**; see
[the harness table in CLAUDE.md](CLAUDE.md#the-verification-harness-is-committed-now).
The short version is that a broken checker looks exactly like a broken release,
which is why the report prints **both** a hash and a column diff: when the two
disagree, the hash is the one that is right, and the disagreement is itself the
signal that the comparator is at fault.

### Verifying the working tree

Every harness below runs this first and refuses on a finding, so you rarely
invoke it yourself; it is also standalone:

```bash
py tree_check.py
```

It hashes every tracked file through `git hash-object` and compares against the
index, using `git status` to tell an edit from something worse. A file you are
editing is skipped, which is why the count it prints is tracked files **minus**
the ones you have open.

The failure it exists for was observed on 2026-09-15: `verify_stage3.py` ran an
**older copy of itself** off the Google Drive mount, printed four checks instead
of six, and said `OK` -- with `git status` clean and its bytes hashing equal to
`HEAD` afterwards. A tracked file reading as **absent** is the same fault in its
other direction.

That `git status` is clean throughout is what makes the check possible rather
than pointless: git's stat cache trusts size and mtime and never re-reads
content, so git's opinion and the file's content are two independent readings,
and this failure is the case where they disagree. Reproduce it by changing one
byte of a tracked file without changing its length and restoring its mtime;
`git status --short` returns empty and the content hash moves.

It is a Drive File Stream fault, so on a plain clone it can only pass. That is
why CI runs it: as the control that the check still works.

### Verifying Stage 3

`verify.py` deliberately does not cover Stage 3, and since the tables moved to
`spacecost` there is a seam that needs its own check. `verify_stage3.py` is it,
it needs no baseline and no network, and it takes a few seconds:

```bash
py verify_stage3.py
```

It asserts six things: the ten config dials match the package's field for
field, the `pipeline_version` this repo stamps is the package's data-contract
version, the six CSVs are byte identical whether built through the adapter or
through the package directly, the five tables match the CSVs spacecost commits
under `reference/`, Stage 3's `validate()` still covers a propellant row that
omits its `propellantless` flag, and the spacecost that is actually INSTALLED
is the revision `requirements.txt` pins. The third would still pass if both
sides moved together, which is what the fourth is for; the fifth is the only
one that checks BEHAVIOUR rather than bytes; and the sixth is the precondition
for all of them.

🚨  **Check 6 is the precondition, and it was missing until 2026-09-15.** Every
other check here describes whatever `import spacecost` happens to reach, and
none of them can tell you whether that is the pinned revision: `__version__`
moves only on a release, `DATA_VERSION` identifies the data *contract* rather
than the commit, and `reference/` is compared against a source checkout rather
than against the installed package. So `pip install -e ../spacecost` at a
checkout past the tag passed all five while the pipeline ran code this repo
does not pin. It now reads pip's own `direct_url.json` (PEP 610), which records
both the revision asked for and the commit it resolved to, and fails on a
different revision, on an install with no VCS metadata at all, and on a tag
that has been **moved** since the install.

🚨  **Check 4 needs a spacecost SOURCE CHECKOUT, and until 2026-09-08 it had
never once run.** `reference/` sits at spacecost's repo root rather than inside
the package, so `pip install git+...` copies the package and leaves the
reference CSVs behind: on every ordinary install the check printed `SKIPPED`
and passed. The message read as an unusual-install caveat when what it meant
was that the *content* half of this seam had never been exercised. It now looks
for a checkout, in `SPACECOST_SOURCE` and then beside this repo, and says
plainly what it would take to run if it finds none.

⚠️  **And it proves the checkout's revision before trusting it.** A checkout at
some other commit is the parallel-repo divergence, not a convenience, so the
tag is read from `requirements.txt` and `reference/` is compared against it
with git. Matching means the check runs and names the tag; **differing is a
failure, not a skip**, because a `reference/` that has moved since the pinned
tag is precisely the drift this file exists to catch. Only `reference/` has to
match: the checkout beside this repo was two docs-only commits past `v0.1.1`
when this was written, and refusing over those would have made the check
unrunnable for nothing.

⚠️  It builds into a temporary directory and never touches
`asteroid_pipeline/`, for the reason the next paragraph gives.

⚠️  **`verify.py` covers Stage 4, and it never re-runs Stages 1-3.** That is
deliberate: a Stage 1 run fetches a different catalog (JPL adds bodies daily)
and a Stage 3 run re-fetches live metal and fuel prices, either of which moves
the inputs underneath the comparison and invalidates every baseline in the same
session. The consequence is that **a change to an upstream module can pass
every check here and still be wrong**: v1.12.1's propellant-flag fix lives in
Stage 3's `validate()`, which Stage 4 never calls, and had to be checked by
running that function under `-W error::FutureWarning` instead. If you change
Stage 1, 2 or 3, this file is not your evidence.

✅  **That named item is a check now**, `verify_stage3.py`'s fifth. It adds one
synthetic propellant with an implausible Isp and no `propellantless` flag and
asserts the sanity bands still warn about it, under `-W error::FutureWarning`
so that the `.fillna(False).astype(bool)` spelling v1.12.1 rejected fails here
rather than passing quietly. It also asserts the probe still
**discriminates**: the regression is only detectable while `~col.astype(bool)`
and `col.ne(True)` disagree about a missing flag, and a pandas release that
made them agree would leave the check passing forever while testing nothing.
⚠️  **Stage 1's derivation chain still has no harness anywhere.**

### What runs automatically

Everything above is a command somebody has to remember. Since 2026-09-15 the
subset that needs no catalog runs on every push and pull request, in
`.github/workflows/verify.yml`:

| step | why it can run there |
|---|---|
| `master.py` is in sync with `modules/` | rebuild, then `git diff --exit-code`. CLAUDE.md has always named this as the sync check and nothing automated it |
| `verify_docs.py` | reads the docs and the dataclasses; builds no stage |
| `verify_stage3.py` | builds into a temp dir, needs no network, and CI checks out `spacecost` at the pinned tag so its reference check RUNS rather than skipping |
| `platform_check.py` | **report only, never a gate** |

🚨  **`verify.py` is NOT in CI and cannot be.** `asteroid_pipeline/` is
gitignored in full, so a fresh clone has the code and none of the ~868 MB Stage
4 reads, and `.verify/` is gitignored too, so there is no baseline to compare
against either. Bit-identity stays a local pre-commit discipline. **CI going
green says the docs and the seams are intact; it says nothing whatever about a
number.**

⚠️  **platform_check.py is informational on purpose.** A GitHub runner is glibc
on x86-64 and the reference host is the Windows UCRT, so a libm probe
*differing* there is the expected answer rather than a finding, and CLAUDE.md's
rule is not to file the deltas as regressions. A gate that is red by
construction is the cry-wolf failure this repo already records twice. What it
is worth in CI is the answer to "how far does a Linux x86-64 runner diverge",
which SPARK_SETUP.md asks and nothing had recorded.

⚠️  **The pinned `spacecost` tag is read, never typed.** The workflow resolves
it by calling `verify_stage3._pinned_tag()`, which parses `requirements.txt`,
so a repin still lands in exactly the two places the split's release note names
and CI does not become a third.

### Verifying Stage 1

`verify.py` covers Stage 4 and `verify_stage3.py` the Stage 3 seam. Stage 1 was
the last stage with no harness at all, which mattered more than it sounds:
CLAUDE.md's [correctness invariants](CLAUDE.md#correctness-invariants-that-were-expensive-to-find)
are almost entirely a Stage 1 list, and every one of them was a rule written in
prose that nothing executed.

```bash
py verify_stage1.py
```

🚨  **It never fetches, and that is the design constraint rather than a
nicety.** Stage 1 pulls from JPL, which adds bodies daily, so re-running Stage 1
to test Stage 1 produces a catalog of a different length that is comparable with
nothing already measured, and Stage 1's output is the ~868 MB input every other
stage reads. So the checks split in two:

| # | check | what it executes |
|---|---|---|
| 1 | designations | the surface-form table in `_extract_canonical_designation`'s own docstring, plus the float64 id that cost NEOWISE four releases |
| 2 | taxonomy | every class has a residual; `Unknown` is the all-`None` sentinel; M-type has not been restored to a bare metal core |
| 3 | pgm | the enrichment fallback: exact type, then root letter, then chondritic |
| 4 | by_distinct | catalog 1.1.1's per-distinct-value optimisation still equals the per-row `.apply` it replaced, NaN keys included |
| 5 | lookup | regex metacharacters do not cross-match or raise, and an `int64` designation column still resolves |
| 6 | literature | Ceres, Vesta, Pallas, Psyche and Eros against their published values, and all five `measured` |
| 7 | rederive | every composition column recomputed from the taxonomy each row ended up with, over the whole catalog |
| 8 | provenance | the two `*_source` domains are closed, and the census reproduces |

Checks 1 to 5 need no catalog, no network and no baseline, so they run anywhere
including CI. Checks 6 to 8 read the catalog already on disk and say what would
make them run when it is absent.

✅  **Check 7 is Stage 1's analogue of a cell hash**: the committed catalog's
derived columns, recomputed row for row. It reproduces exactly across a
**version gap** (the file on disk is written by whichever catalog release last
ran, which is older than the module), and reproducing across one is a stronger
result than reproducing within one.

⚠️  **It compares only the columns that are a pure lookup on the final
taxonomy**, and the reason is worth knowing before you extend it. The catalog's
`spectral_type` is *post-fill*: `enrich_composition` fills a missing type from
Tholen, then from albedo, then from the albedo assumed when the diameter was
derived. Feeding the filled column back makes all three fallbacks dead code and
`spectral_type_source` then disagrees with the file everywhere it had been
filled, which is an artefact of the fixture rather than a defect. The fallback
chain is covered by check 8's census instead.

⚠️  **Check 8's counts are pinned to the catalog identity they came from**, not
asserted outright. They are properties of one build; re-running Stage 1 is a
legitimate act that necessarily moves every one of them, so a different build is
reported rather than failed.

### Verifying the docs

`verify.py` proves the model did not change. **`verify_docs.py` proves the docs
still describe it**, in about a second and with no baseline:

```bash
py verify_docs.py
```

| # | check | catches |
|---|---|---|
| 1 | defaults | a documented default that no longer matches its dataclass field |
| 2 | versions | the Stage/Version table or CLAUDE.md's `Current:` line drifting from `pipeline_version`, and the "moved without moving a number" tables drifting from the count spelled out beside them, in any doc that quotes it, including one holding no table of its own |
| 3 | row counts | "40 propellants" after a row was added |
| 4 | links | a markdown anchor that does not resolve |
| 5 | structure | unbalanced fences, ragged tables, heading-level jumps, duplicate h1/h2, in every markdown file in the repo |
| 6 | dashes | an em- or en-dash creeping back into prose a reader sees, or a line left opening with a bare comma by the pass that removed them: the docs, the root scripts, the campaign scripts, and comments in `modules/` |
| 7 | manifests | a list documented in one place drifting from the list defined in another: `requirements.txt` against `_MASTER_REQUIRED`, and the `run.bat` block above against run.bat's own dispatcher |
| 8 | help | a config dial the dashboard renders with no help text, because the UI scrapes its help from the field's own comment |
| 9 | runtime | the **whole twenty-eight-cell** wall-clock table above drifting from `calc.MEASURED_DEST_SECONDS`; also CLAUDE.md's copy of the cislunar row, `calc.MEASURED_CELL_SECONDS` (the cislunar cells at the current release, which every banner and `--help` string derives its cost ratios from) against the `campaign/logs/` JSON that measured it, and every "N h at &lt;destination&gt;" in `run.bat`, `run.sh` and this file, which are typed because shell cannot import `master` |
| 10 | transfer | a measurement dropped rather than moved during a reorganisation, `--before OLD.md NEW.md …` |
| 11 | docstrings | a module, class or function in the repo's own Python with no docstring |
| 12 | pairs | one measurement quoted in BOTH README and CLAUDE.md without a row on CLAUDE.md's register of known copies |

⚠️  **Every one of these fails if a file it is supposed to read is not on
disk.** That was not true until 2026-09-15: each check enumerated first-party
files from a static list and skipped any that was absent, so renaming
`verify_stage1.py` away dropped check 11 from 486 definitions to 469 and the
run still exited **0**. A missing file now fails on its own counter, reported
separately from the finding the check is actually about.

Check 6 is a ratchet rather than a style opinion: 1,342 em-dashes came out of
the docs and 1,120 out of the module comments, and without a check they drift
back one commit at a time. It reads `modules/*.py` through `tokenize` and `ast`
so it sees only comments and docstrings, because the `notes` and `composition`
strings are written into the CSVs and their text is data. Everything else, the
docs, the root scripts and the campaign scripts, is checked whole: none of them
holds a reference table, so none of their text is data.

⚠️  **`campaign/` was outside checks 5 and 6 until 2026-09**, through the whole
20-cell campaign, and its eight files happened to be clean when they were
brought in. That is the argument for the ratchet rather than a reprieve from it:
a file nothing checks is clean until it is not.

🚨  **Check 6 also catches what the conversion that removed those dashes left
behind.** An em-dash that had opened a *continuation* line became a bare
leading comma, so the sentence stopped parsing: `, it auto-installs its own
dependencies` was sitting in this file. Twenty of them, twelve in `modules/`
and eight in the docs, and the docs half was only found on a second pass
because the first sweep looked at Python and stopped there. A mechanical rewrite of prose
needs a check on what it *leaves*, not only on what it removes.

Check 11 is a ratchet on the same argument as check 6. The premise of this repo
is that a number without its reasoning attached gets "fixed" by the next person,
and that applies to code as much as to config: **87 definitions carried neither
a docstring nor a leading comment** when this was first measured, most of them
in `ui.py` and `launch_ui.py`, which are almost entirely made of Windows traps
that explain why the code looks the way it does. Nested functions count, because
several of the sharpest notes in the repo sit on a six-line closure.
`master.py` is exempt: it is generated, and its contents are the four modules,
checked here at source.

Checks 1, 3, 7 and 8 exist because they have already failed: `use_beneficiation`
and `optimise_programme_scale` were both documented as `False` for several
releases after calc v1.17.0 flipped them to `True`; the propellant table was
documented at 40 rows for six releases after v1.12.0 split argon into two;
`run.bat help` was accepted by the dispatcher and documented nowhere; and **39
of 105 config fields rendered in the dashboard as a bare number with no help**,
because a comment block explaining two fields sits above only the first one.

⚠️  **Check 7's second half is not cosmetic.** `requirements.txt` says in its
own first line that it mirrors `_MASTER_REQUIRED`, which `master.py`
pip-installs at import time; if the two drift, `pip install -r` builds a
different environment from the one a Colab paste sets up for itself.

✅  **Check 9 exists because a banner is the most-read copy of a number here
and was the least checked.** The beneficiation and programme-search cost ratios
were hand-copied into five files, and they went stale together: the superseded
v1.16.0 figures were still being *printed on every run* three releases after
the measurement that retired them. Those ratios now derive from one dict,
`calc.MEASURED_CELL_SECONDS`, so a re-measurement moves `--help`, both run
banners and the dashboard estimate at once; check 9 holds the table above to
`calc.MEASURED_DEST_SECONDS`, so the docs cannot drift from it either, and
holds `MEASURED_CELL_SECONDS` to the `campaign/logs/` JSON the run that
measured it wrote, so the constant itself is pinned to a measurement rather
than to somebody's typing.

✅  **Check 12 is the one hunt in this project that was prescribed in prose and
rebuilt from memory every time it ran.** CLAUDE.md describes it exactly, "
hunting sentences that share three or more distinctive numbers across two
files", and carries a table of what it found; the search itself was written
from that description, run, and thrown away, four separate times. That is the
shape `verify.py`'s header argues against, and it had the same consequence: the
run that finally committed it turned up a pair the table had missed since the
table was written, and it was **the project's four headline numbers**.

The register table is the **allowlist**, not the target. A pair is fine when it
is written down, because CLAUDE.md's job is the reasoning and this file's is
the answer, and the reasoning reads badly with the answer removed. What is not
fine is a pair nobody has recorded, because nobody will move both. So check 12
goes red on an *unregistered* pair only, and either remedy clears it: cut one
copy, or add the row. `versions.md` is deliberately outside it, because every
section there names the release it belongs to, so a superseded figure in it is
correct rather than stale.

⚠️  **It checks that a documented *configuration* matches the code; not that a
documented *measurement* is current.** A stale number passes everything in it.
That is what the release notes and `verify.py` are for. ⚠️  Check 12 is the
nearest thing to an exception and is not one: it can see that two files quote
one number, never that the number is still true.

⚠️  **It reads the docs and the module dataclasses, and runs nothing.** No
stage, no fetch, no baseline, which is why it costs a second and works on any
tree. It reaches all four modules, not just Stage 4: check 1 reads every
config dataclass, check 2 every `pipeline_version`, check 3 Module 3's
reference tables.

## Working copy

The working tree lives in Google Drive, but the git directory does **not**; 
`.git` here is a one-line pointer file rather than a directory:

```
gitdir: C:/Users/Owner/repos/economicspace.git
```

That keeps thousands of loose objects out of Drive sync. The cost is that the
external git directory stores the working tree's absolute path in its
`core.worktree` setting, so **renaming or moving this folder breaks git**: 
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
it*; a differing size is normally conclusive proof of a change. The tell is
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
                                          ~30-40 MB at jpl_limit = 50_000)
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

Output files are gitignored; they are regenerated by every run.

### Reading `profitability_catalog.csv`

One row per asteroid; the best mission found for it, across vehicle ×
propellant × return mode × propellant sourcing × rendezvous apsis ×
concentration ratio, sorted by `profit_usd` descending. Note that the *file*
is sorted by profit while the *search* that produced each row optimises
`selection_objective` (cost/revenue by default); those are different questions
and the sort order is the less useful of the two.

Two columns, **`pipeline_version` and `catalog_date`**, are provenance and must
be stripped before comparing two runs; `verify.py`'s `PROVENANCE` is the
authoritative list and the reason the verification blocks report a smaller
count than the file has. ⚠️  **The total is deliberately not written here.**
It read "141 columns" while the file had 144, having gone stale three releases
earlier, and no check in this repo can see it -- which is the
count-with-no-checker case CLAUDE.md says to delete rather than correct. Ask
the file: `len(pd.read_csv(path, nrows=1).columns)`.

The ones to look at first:

| Column | Meaning |
|--------|---------|
| `designation`, `name`, `spectral_type`, `comp_group` | Which asteroid, and what it's made of |
| `viable` | `profit_usd > 0`. The headline filter |
| `profit_M$`, `gross_M$`, `cost_M$` | Same numbers as the `_usd` columns, in millions, for reading |
| `roi` | `profit / total_cost` |
| `usd_per_kg_cost` | Mission cost per kg actually returned, the cleanest cross-asteroid comparison |
| `vehicle`, `propellant`, `isp_s` | The winning combination |
| `aerocapture_return`, `isru_return` | The architecture the search chose **for this asteroid**. Both used to be catalog-wide settings |
| `rendezvous_apsis` | `aphelion`, `perihelion` or `reference`, which apsis the transfer meets the target at, resolved against the destination |
| `isru_propellant_kg`, `isru_feed_kg` | Return propellant made on site, and the rock dug to make it. That feed comes off the throughput and mineable-mass budgets before any ore is loaded |
| `dv_out_m_s`, `dv_ret_m_s` | Per-asteroid Δv from its own orbital elements, including any low-thrust penalty |
| `dv_penalty_factor` | 1.0 for chemical, 1.5 for electric; electric can't fly impulsive burns |
| `max_payload_kg` | Material actually returned, after the mining-fraction, rocket-equation, volume and throughput caps |
| `mining_duration_yr` | Time at the asteroid to dig that payload; floors at `station_keeping_floor_yr` |
| `throughput_cap_kg`, `throughput_fits` | Most the rig could dig in `max_mining_duration_yr`, and whether that bound bit |
| `bulk_value_usd_per_kg` | Stage-2 prices × Stage-1 composition × PGM enrichment |
| `volume_fits` | `False` means the capsule volume cap bound the payload, not the mass budget |
| `m_launch_kg`, `m_outbound_prop_kg`, `m_return_prop_kg`, `m_at_asteroid_kg`, `tps_mass_kg` | The mass cascade |
| `m_dry_return_kg` | Return-vehicle dry mass actually flown, the 500 kg base plus `return_structure_frac_of_payload` of the haul. Compare it to `max_payload_kg`: a ratio far above ~7:1 means something has gone slack |
| `ep_system_kg`, `ep_power_w`, `ep_system_cost_usd` | The electric stage. Before v1.10.0 the first two existed and the third did not, which is exactly the bug |
| `*_cost_usd` (23 columns) | The cost cascade, line by line: launch, outbound and return propellant, hardware, mining rig, power system, EP stage, tankage, tanker flights, capsule, heat shield, ops, recovery, liability, licensing, launch insurance, NRE, autonomy NRE, contingency. Four of the 23 are the time-bucket aggregates in the next row, plus `total_cost_usd`. `liability_cost_usd` and `launch_insurance_cost_usd` are **0.0** unless `charge_insurance` is set; the columns stay so a charged run and an uncharged one have the same schema |
| `upfront_cost_usd`, `ongoing_cost_usd`, `end_of_mission_cost_usd`, `wacc_multiplier*` | Cost by time bucket, and the WACC factor applied to each. ⚠️  Every `wacc_multiplier*` is **1.0** unless `apply_wacc_compounding` is set, which is off by default since calc v1.22.0 |
| `saturation_multiplier`, `market_clearing_fraction`, `unsold_payload_kg`, `surplus_payload_kg` | What the market did to the load. The first is a PRICE multiplier and is 1.0 in every model but `elasticity`; the rest are quantity. `market_clearing_fraction` is the share of the assembled load's gross value that cleared, `surplus_payload_kg` is mass sold past a ceiling at `surplus_price_fraction`, and `unsold_payload_kg` is mass that earned nothing. The last two are exclusive: which one carries the mass is `sell_surplus_at_discount`, and `verify.py` check 7 asserts it |
| `p_success`, `p_mining`, `learning_curve_factor` | ⚠️  All **1.0** by default since calc v1.22.0. `model_reliability` and `model_learning_curve` are off, so these read as "no discount applied" rather than as a measurement |
| `programme_missions`, `fleet_ships`, `missions_per_ship`, `trips_per_ship`, `programme_span_yr`, `programme_calendar_multiplier` | The programme the search chose. N = fleet x campaigns-per-ship, and `trips_per_ship` is what the rig's two bounds allow. ⚠️  The calendar multiplier is 1.0 whenever the cost of capital is off, because it is time-value |
| `pipeline_version`, `catalog_date` | Which version of Stage 4 produced this row, and when |

Running `python modules/calc.py` directly (rather than `master.py`) also
prints a top-20 table, a breakdown by composition group, the winning
vehicle × propellant combinations, and a bar chart of where the money goes.
That last one is the fastest way to see which lever matters: launch-dominated
means try a cheaper vehicle, NRE-dominated means amortise across missions,
WACC-dominated means shorten the mission. ⚠️  The last of those cannot happen
under the calc v1.22.0 defaults, where the cost of capital is off and every
WACC multiplier is exactly 1.0.

Every mineral price column carries a `_usd_per_kg` suffix, prices are
normalised to USD/kg on the way in, everywhere, so the unit is never in
question downstream.

## Programme scale

`nre_amortization_missions` is programme size N, and since calc v1.15.0 it is
**searched rather than set**: `optimise_programme_scale` resolves fleet size
and campaigns-per-ship per asteroid, jointly with every other architecture
axis, and N follows as their product. It is **on by default** since v1.17.0.

That costs **2.0× to 3.1× runtime** rather than one full run per N, because
**N enters nothing in the mass cascade**; it appears in the cost model, the saturation
block and the reliability block, and in none of the rocket equation, the power
fixed point, the payload knapsack or the concentration sweep. The expensive
half of the mission is solved once per candidate and the whole ladder is priced
off the result.

**Scale is real, sublinear, and bounded.** Five models pull against each other,
and the last two are what stop it running away. 🚨  **Three of the five are OFF
or INERT under the calc v1.22.0 defaults**, which is marked per bullet, and
**both of the two that bound it are still live** -- so the conclusion survives
the flip, but the argument for it is now carried by fewer terms:

- **NRE amortises** across the programme, and the learning curve (Wright's law,
  0.85) falls on the per-mission articles. ⚠️  **The curve is OFF by default
  since v1.22.0** (`model_learning_curve`); the NRE amortisation is not and
  never was a flag. Turning the curve on is worth 34.3% on the searched
  cislunar sample cell and exactly nothing at N = 1.
- **Mining reliability grows** with programme size, Duane/AMSAA, 0.850 at
  N = 1 to 0.943 at N = 100, reported as the fleet average rather than the
  terminal value. ⚠️  **OFF by default since v1.22.0** (`model_reliability`),
  which takes the growth term with it.
- **The rig wears out**, on whichever of its two bounds binds first: a 15-year
  calendar life, or five duty cycles. Past that, mission N+1 buys a new rig.
  ✅  Live, and one of the two that bound the ladder.
- **The market saturates**, against the programme's **concurrent** output,
  which is what makes the optimum programme size **interior** rather than "as
  many as you can pay for". ✅  Live, and the other one. Since v1.22.0 the
  surplus past a ceiling sells at half price rather than being abandoned,
  which softens the bound without removing it: the marginal kilogram past a
  ceiling is still worth strictly less than the one before it.
- **The calendar is charged.** One rig digs one hole at a time, so campaigns on
  a ship are strictly sequential, and the lines bought once at t = 0; bus NRE,
  autonomy NRE, the rig, are carried across decades of programme span.
  ⚠️  **INERT since v1.22.0.** The flag is still True, but the charge is
  time-value and `apply_wacc_compounding` is off, so the multipliers are
  exactly 1.0. Measured: it was worth a median **1.457x** on the amortised
  lines of the searched cislunar sample cell, and the share of rows choosing
  **fewer campaigns than the rig can fly fell from 29.2% to 1.5%** with it
  inert -- this was the only term giving W a reason to be less than the rig's
  trip life.

Measured on the full catalog at cislunar, the search improves the raw cell
**15.3937× → 9.5435×** and the beneficiated cell **14.1071× → 6.6622×**, on a
median fleet of **3 ships** raw and 6 beneficiated, a median N of **12** and
**30**, and a median programme span of 11.4 years raw / 13.8 beneficiated.
Every destination is in [Results](#results).

⚠️  **The searched and unsearched columns answer different questions and are
not comparable.** One is the best single mission to a rock, the other the best
programme built around it. The improvement is a change of question, not a
saving, and it does not reach viability either: the best programme in the
model still loses about seven dollars for every one it earns.

⚠️  **Rows piling up against `max_fleet_ships` are a diagnostic, not a result.**
Those are bodies whose payloads cannot reach a ceiling that binds, so the
objective is monotone in N and the ladder's top rung is simply where the loop
stopped. That is **9.99% raw and 17.77% beneficiated** at cislunar and
**100.000% at `earth_surface`**, which is why that destination's searched cells
are not optima.

🚨  **Both of those rose sharply under `capacity_cap`**, from 0.37-0.40% at
cislunar, so this diagnostic counts a larger and slightly different population
than it did under `elasticity`: a body can now sit at the ceiling either
because no finite market bounds it **or** because its payload is too small to
reach one. `earth_surface` is unchanged at exactly 100%.

The historical curves against a *forced* programme size, and the two
corrections that reshaped them, are in
[The programme-scale curves](versions.md#the-programme-scale-curves).

## Where the material is sold

This is the single most consequential setting in the pipeline, so it gets its
own section.

Nothing mined has an intrinsic price; it is worth whatever it costs to put
an equivalent kilogram where the customer already is. The destination sets
both what the cargo sells for (Stage 2) and what the mission costs to fly
(Stage 4), and **both stages carry the field, so both must be set**:

```python
MASTER_CONFIG.delivery_destination = "cislunar"   # writes Stage 2 and Stage 4
```

Setting only one is the classic error; it prices the cargo at a depot while
still paying to land it in Utah. Stage 4's `destination_check()` refuses to
let that pass quietly.

### What a kilogram is worth

In-space prices are the launch cost avoided, **derived** rather than
tabulated: Falcon 9 reusable $/kg-to-LEO, carried further by walking a chain
of real stages backwards from the payload (`delivered_cost_usd_per_kg` over
`_DELIVERY_LEGS`). Staging is modelled leg-by-leg because it matters, a
single stage flying the whole 5,920 m/s to the lunar surface needs 10.96 kg
in LEO per kg landed against 4.99 kg for the tug-plus-lander pair that would
actually be flown.

| Destination | Launch cost avoided | kg in LEO per kg | Chain |
|-------------|--------------------|------------------|-------|
| `earth_surface` *(default)* | - | - | Terrestrial commodity prices |
| `leo` | $4,253/kg | 1.00 | Falcon 9 reusable $/kg-to-LEO |
| `geo` | $12,526/kg | 2.95 | LEO to GTO (2,455 m/s), then 1,836 m/s to circularise and remove 28.5 deg |
| `cislunar` | $10,810/kg | 2.54 | TLI + NRHO insertion (3,600 m/s), cryo tug |
| `lunar_surface` | $21,210/kg | 4.99 | TLI + LOI (4,050 m/s) tug, then 1,870 m/s lander |
| `mars_orbit` | $13,496/kg | 3.17 | TMI (3,600 m/s) + MOI (900 m/s) into the 1-sol staging orbit |
| `mars_surface` | $45,105/kg | 10.61 | TMI (3,600 m/s), aeroentry at 30% surviving mass, 800 m/s retroprop |

`geo` is a geostationary servicing depot, and it is the only destination in
this model with a **paying customer today**: roughly 550 active satellites,
and MEV-1 and MEV-2 have already docked with and station-kept commercial GEO
spacecraft. It is also the only one that pays a **plane change**. An asteroid
arrives near the ecliptic and GEO is equatorial, so 23.44 deg has to be bought
out on arrival; a launch from Canaveral parks at 28.5 deg and buys a slightly
bigger one. Those are two different numbers for the same manoeuvre, 1,730 and
1,836 m/s against 1,477 coplanar, and the model keeps them apart on purpose.

Its market is the narrow one. A depot refuels and services satellites, so the
volatiles hold most of their value and the structural metals lose most of
theirs: water is worth $9,818/kg there against cislunar's $10,607, while iron
is worth **$1,649/kg against cislunar's $7,337**. It is the first destination
whose utility overrides run downward on the metals rather than the volatiles,
and the argument is different in kind: the lunar and martian discounts are
about local **supply**, and this one is about local **demand**. Nobody launches
a kilogram of copper to geostationary orbit, so asteroid copper substitutes for
nothing there.

`mars_orbit` is the 250 x 33,793 km 1-sol elliptical staging orbit NASA
DRA 5.0 parks a Mars vehicle in; its period matches a sol to within a minute.
Capture there only has to **bind** the ellipse rather than circularise it, so
MOI is 900 m/s where a 200-km orbit costs 2,100 at the same arrival energy,
the same trade NRHO wins on at the Moon. It is the only Mars destination that
enters no atmosphere and lands nothing, so it pays neither the entry-survival
fraction below nor a lander, and it is the one in-space destination whose
**utility profile is the base one**: everything martian sits 4,100 m/s of
ascent away, so a depot there competes with Earth freight, not with the crust.

Mars' entry survival fraction is measured, not assumed: MSL landed 899 kg of
a 3,257 kg entry mass (27.6%) and Perseverance 1,025 of 3,440 (29.8%). The
lander dry-mass fraction of 0.20 is the Apollo LM descent stage (2,134 kg dry
on 8,200 kg of propellant).

⚠️ **The two surface figures are marginal-transport lower bounds.** They price
propellant and stages on a reusable Falcon 9 LEO price, with no first-of-kind
development, no programme overhead and no cadence limit. Real delivered cost
today is far higher; CLPS lunar landers run on the order of $1M/kg at ~100 kg
scale. Read them as "what it could cost at industrial scale", not "what it
costs now".

A kilogram sitting at a depot is worth **the better of its two fates**, and
the pipeline picks per commodity:

- **Used in space**: worth its terrestrial price **plus** the launch bill
  delivering it avoids, scaled by the in-space utility factor (base profile:
  water 1.00, structural metals 0.70, silicates 0.25, carbon 0.40, organics
  0.20), less the cost of refining it into a usable article on site. Note the
  *plus*: the launch cost is on top of the material, not instead of it.
- **Shipped down**: worth its terrestrial price **minus** the downleg:
  capsule + TPS + recovery + depot-departure burn, derived from the same
  Stage 3 rates Stage 4 charges for an Earth return. ~$25,400/kg from LEO,
  ~$27,300/kg from NRHO. Coming down is far cheaper than going up.

This is what puts an honest number on platinum at a depot. Its in-space
utility is 0.00, nobody in orbit wants platinum, but it is still platinum,
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

- **Cislunar is worse than LEO for anything shipped down**: it is further from
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

#### Utility is per destination, because the alternative to importing is not always launching

The freight table above says what Earth would pay to put a kilogram somewhere.
It does **not** say whether anyone there wants it, and that answer is not a
function of distance. It is a function of what the destination can dig up for
itself.

- **LEO and cislunar** are empty space. Nothing is available locally at any
  price, so the only substitute for asteroid material is the same material
  launched from Earth. These carry the base profile unchanged, and every other
  destination is defined as a deviation from them.
- **The lunar surface** sits on silicate regolith carrying 5-15 wt% FeO plus
  mare ilmenite, and on polar water ice. Water drops to 0.60 (the ice is in
  permanently shadowed craters at ~40 K with no sunlight to work by), iron and
  Fe-Ni to 0.45, silicates to 0.03. Carbon is *not* discounted; solar-wind
  implantation leaves it at ~100 ppm, which is not a resource.
- **The Martian surface** has metres-thick mid-latitude ground ice, 1-3 wt%
  hydrated regolith measured by Curiosity's SAM, a 95.3% CO₂ atmosphere and a
  globally oxidised crust. Water drops to 0.25, carbon to 0.02, silicates to
  0.02, iron to 0.40.
- **Nickel, cobalt and copper are undiscounted everywhere.** No concentrated
  ore of any of them is known on either body, and they are what motors,
  batteries and wiring are made of.

⚠️  **Prices still rise with distance**, and reading this table as though they
do not is the standard mistake: Mars freight is 10.6 kg-in-LEO per kg delivered
and that still dominates. They simply no longer rise as *fast* as the freight
does, and the volatiles that once carried the Mars result rise least, water at
Mars is 2.7× its LEO price now against 11× before. **Every override runs
downward**, deliberately; why that constraint exists, and why a PGM settlement
market was considered and rejected, are in
[CLAUDE.md](CLAUDE.md#model-assumptions-that-are-load-bearing).

**The import budget is split per commodity class.** One shared depot budget
meant a 20 t/yr Mars base absorbing 20 t of water *and* 20 t of platinum *and*
20 t of olivine. `_DEMAND_SHARE_BY_CLASS` partitions it, propellant 0.55,
structural 0.25, shielding 0.15, chemical 0.05, and `annual_market_kg` is
**routed**, so a commodity flown home saturates the terrestrial market rather
than a depot's import budget. Platinum at LEO was capped at the depot's
500 t/yr against the world's actual 180 t/yr.

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
widens as arrival energy falls: 5.6× at v_inf = 1 km/s, 2.7× at 5 km/s.

**Mars is a different journey, not a discounted Earth return.**
`_asteroid_to_mars_dv_km_s` runs the heliocentric transfer from the
asteroid's orbit to Mars' (1.524 AU), so the departure burn, arrival
v_infinity and capture are computed separately. That matters because plenty
of asteroids are genuinely more accessible from Mars than from Earth, and
approximating the leg would have hidden it entirely:

| Target | → Earth surface | → cislunar | → lunar surface | → Mars surface |
|--------|----------------|-----------|-----------------|----------------|
| Bennu-like (a = 1.13) | **0.75** | 1.96 | 4.56 | 5.14 |
| Mars-crosser (a = 1.46) | 0.78 | 2.33 | 4.93 | **3.28** |
| Main belt (a = 2.70) | 4.13 | 7.32 | 9.92 | **3.84** |

km/s of return Δv. A main-belt body is cheaper to deliver to Mars than to
Earth. The Moon is the awkward one, nearest in distance, but airless, so
every metre per second of arrival is propulsive.

Every output row carries `delivery_destination`, `delivery_arch` and
`value_basis`, so a CSV cannot be read without knowing which assumption
produced it.

## The propulsion and storage catalog

ℹ️  **These tables live in [`spacecost`](https://github.com/loggger101/spacecost)
now**, not in this repository; `modules/transportation.py` drives that package.
The row counts and the reasoning below are unchanged and still describe exactly
what Stage 4 reads, and `verify_docs.py` check 3 still holds every count here to
the tables themselves. See
[Stage 3's tables live in another repository](#stage-3s-tables-live-in-another-repository).

Stage 3 v1.9.0 rewrote the reference tables to hold the field rather than a
sample of it. The previous tables held what somebody had happened to list, and
the omissions were not random; everything missing was either an option the
search never got to consider or a cost the model never got to charge.

### Propellants: 41 rows

Each carries specific impulse, blended density, $/kg, boil-off rate, a
low-thrust Δv penalty, and (new in v1.9.0) a **storage class**, a derived
**tankage mass**, a maturity **status**, and whether the asteroid itself can
supply it.

| Status | Count | Rows |
|---|---|---|
| operational | 23 | kerolox, hydrolox, methalox, MMH/NTO, UDMH/NTO, Aerozine-50/NTO, hydrazine, green monoprop (ASCENT), HTP mono + bi, cold gas, solid APCP, xenon, krypton, argon, iodine, water electrothermal, water ion, hydrazine arcjet, electrospray, FEEP, PPT, solar sail |
| development | 8 | nuclear thermal, nuclear electric, solar-thermal H2, solar-thermal steam, VASIMR, MPD, metal/water (ALICE), cryogenic argon |
| concept | 9 | Li/F2/H2, CO/LOX, mass driver, Orion nuclear pulse, direct fusion drive, antimatter, magsail/e-sail, momentum tether, beamed laser-thermal |
| retired | 1 | mercury ion, banned under the Minamata Convention |

**Only the 23 operational rows are in the default search, and only 21 of those
can fly this mission profile.** Solid APCP is excluded because it cannot be
relit for a return burn years later; the solar sail because it is
propellantless and the rocket equation would report that it moves any payload
for free. Set `operational_propellants_only = False` to admit the rest, but
understand that a profit-maximising search will then fly every asteroid on
antimatter, which is why the gate exists.

Three of the additions matter more than the row count suggests:

- **Krypton** is, by unit count, the most-flown electric propellant in history,
  every Starlink v1.0 Hall thruster ran it, and it was absent. It is 30×
  cheaper than xenon at two-thirds the Isp, and it pays for that with a much
  worse tank (0.55 kg/L supercritical against xenon's 2.0, so 12.5% of its own
  mass in COPV against 1.9%).
- **Iodine** stores as a *solid* at ambient pressure, ρ 4.93 kg/L, so its
  reservoir is 0.2% of the propellant it holds, the best storage density of
  anything flying. ThrustMe flew it in 2020. It wins a large share of targets
  in the current model precisely because of that.
- **Water, electrothermally heated**, is the propellant the idea of a
  self-refuelling mining craft actually rests on: 1.00 kg of asteroid water
  per kg of propellant against hydrolox's 1.286, with no electrolyser and no
  cryogenic tank, at 190 s of Isp against 452. Honeybee's WINE demonstrated
  the full mine-boil-thrust loop in a vacuum chamber in 2018.

### Storage classes and tankage

Tank mass scales with the **volume** enclosed, not the propellant mass inside
it. `tank_kg_per_L` is derived per class, a flight-anchored multiple of
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
| solid motor | APCP (1.80 kg/L) | 6.9%, Star 48B measures 6.4% |
| deep cryogen, blended | hydrolox (0.361 kg/L) | 9.7%, Centaur III measures ~9.7% |
| supercritical gas, 18 MPa | krypton (0.55 kg/L) | 12.5% |
| supercritical gas, 30 MPa | cold gas N2 (0.25 kg/L) | 46% |
| deep cryogen, neat | LH2 for NTP (0.0708 kg/L) | 53% |

### Launch vehicles: 36 rows

17 operational and Earth-based (the default search), plus development vehicles
(Neutron, Terran R, Nova, Eclipse, Zhuque-3, Tianlong-3, Long March 9 and 10,
Starship), two retired, and eight **non-rocket** concepts.

On the non-rocket rows, read `max_accel_g` before the price. SpinLaunch is
~10,000 g and a light-gas gun ~30,000 g: that passes propellant, water and
steel billets and destroys every mining rig, optic, reaction wheel and radio
in the catalog. They do not have a cost problem, they have a payload problem,
and this pipeline cannot represent a split manifest.

The lunar mass driver and lunar space elevator are excluded structurally
rather than by maturity, Stage 4 departs from Earth, and their payload
columns are annual throughput, so reading them would be a unit error. The
**lunar elevator** is the one worth not dismissing: unlike Earth's it needs no
new material, because the Moon's shallow gravity well and the Earth-Moon L1
balance point put the required specific strength inside what Zylon and M5
already deliver (Pearson 1979; Eubanks & Radley 2016).

### Storage systems: 20 rows

A new `storage_systems.csv`, covering four domains that had previously been
represented by a single column:

- **propellant**: the tankage constants above, MLI, vapour-cooled shields,
  and zero-boil-off cryocoolers (80 W of input per W lifted at 20 K, ~5 kg/W)
- **cargo**: bulk ore restraint, volatile containment, sintering, dust seals
- **energy**: Li-ion, regenerative fuel cells, flywheels, RTGs, Kilopower-class
  fission, and the eclipse fraction that should be sizing all of them
- **depot**: cryogenic depot boil-off, tanker flights per departure, transfer
  losses, ISRU propellant depots

Stage 4 reads the tankage figures, the RTG rows and the tanker count. It does
**not** read the volatile-containment, eclipse or cryocooler rows; those are
documented gaps, and all three currently run in the optimistic direction. See
[What the model does not capture](#what-the-model-does-not-capture).

## Beneficiation

**On by default since calc v1.17.0** (`CALC_CONFIG.use_beneficiation`).
Terrestrial mines ship concentrate, not ore; switched off, the pipeline flies
home run-of-mine regolith at bulk grade while the rig's own throughput capacity,
66× the rocket-equation payload limit, sits idle. Switched on, the rig digs
surplus feed, rejects the gangue, and loads concentrate.

⚠️  **Almost every table dated before 2026-08-11 is the `False` case.** Set it
back to reproduce them.

### The load is optimised, not specified

A mission is not sent for a named mineral; it brings back **the most
valuable load it can assemble from what the target actually contains**. With
a fixed mass budget and divisible, per-kilogram-priced phases, that is a
fractional knapsack, so greedy selection by $/kg is provably optimal: fill
the hold with the best phase available, then the next, until full or the feed
runs out (`optimal_payload_mix` over `asteroid_phase_table`).

Both honest bounds fall out of it automatically; you cannot load more of a
phase than the processed feed contained, and once the hold is pure best-phase
there is nothing better to add. On an M-type at 50% metal / 45% silicate with
0.90 recovery:

| Feed | Delivered | Load |
|------|-----------|------|
| 1.0× | $5,135/kg | hold 90% full, in-situ ratios |
| 2.0× | $7,081/kg | 90% metal |
| 2.2× | $7,567/kg | 100% metal, saturated |
| 5.0× | $7,567/kg | no further gain |

### How hard to concentrate is an economic decision

Grade saturates; costs do not. Every extra kilogram of feed still costs dig
time (compounding through ops and WACC), processing energy, and the solar
array mass to supply it, and that array mass comes out of the payload
budget. So the optimum is usually *strictly inside* the range, and
`evaluate_combo` searches for it rather than assuming it.

The search always includes **not concentrating at all** as a baseline, which
is not the same as a ratio of 1.0, since that would still pay the separation
recovery loss and the array mass for no grade gain, so beneficiation is an
option rather than an obligation and can never make a mission worse.

How often it declines varies enormously by destination, and the ordering is the
ISRU discount doing its job: **0.6%** of bodies at `mars_surface`, 1.1% at
`earth_surface`, 3.9% at `lunar_surface`, 11.6% at `leo` and **15.8% at
`cislunar`**; a depot with no local resources is where concentrate is worth
least relative to bulk. Where it does concentrate, the chosen ratio is a
single-digit multiple and never the 50× cap, the best cislunar mission
concentrates 3.5× at N = 1 and 3.9× as a programme. Median improvement from
beneficiating runs from +39.5% at `cislunar` to **+77.7%** at `earth_surface`.

**"Can never make a mission worse" is checked, not assumed**, and it is one of
the checks in `verify.py`: join the raw and beneficiated catalogs on
`designation` and assert the beneficiated cost/revenue is never higher, row by
row. On the full catalog it holds across **all twenty-eight cells with zero
exceptions**, and the worst case is exactly 1.000000, which is beneficiation
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
| 1.8-2.5 AU | 11.4 | 41 kg |
| > 3.2 AU | 4.7 | 226 kg |

⚠️  **The search costs runtime: beneficiation is 5.24× the raw path.** Full
1,555,667-row catalog, six physical cores / 12 workers, calc v1.21.2, measured
2026-09-11/13, the complete wall clock for all twenty-eight cells:

| destination | raw, N = 1 | raw, searched | benef, N = 1 | **benef + searched** |
|---|---|---|---|---|
| `cislunar` | 947 s | 2,888 s | 4,967 s | **9,878 s** |
| `lunar_surface` | 633 s | 1,160 s | 3,021 s | 7,253 s |
| `geo` | 1,221 s | 2,558 s | 7,382 s | 19,902 s |
| `mars_orbit` | 2,065 s | 4,399 s | 13,135 s | 29,174 s |
| `leo` | 1,426 s | 2,583 s | 8,558 s | 23,335 s† |
| `mars_surface` | 1,799 s | 3,982 s | 12,113 s | 25,270 s |
| `earth_surface` | 1,747 s | 3,386 s | 11,000 s | 21,860 s |

The whole twenty-eight-cell matrix is **63.2 hours**. Tune with
`.calc.concentration_search_steps`, and cap `.calc.eval_row_cap` for anything
interactive.

† `campaign/results.csv` records 27,817 s for that cell, which is a true wall
clock and not a comparable one: the campaign was suspended 5.7 h into it and
`run_cell.py` times with a wall clock, so a 74.7 min pause is inside the
measurement. The ledger is deliberately not corrected; see
[the 28-cell campaign](versions.md#the-28-cell-campaign-2026-09).

⚠️  **Every timing older than calc v1.21.0 is LOW for the current build, and
every timing older than v1.17.7 is high.** The direction reversed: six
performance-only releases between v1.16.0 and v1.17.7 were worth **1.78× to
4.32×**, and then the capacity ceilings of v1.21.0 cost **1.29× to 2.31×** back,
landing hardest where a programme ladder exists. A wall-clock number in this
project tells you nothing without the release it was measured on. The
per-release figures are in [`versions.md`](versions.md).

**Most of that came from not solving dead candidates.** `prune_infeasible_combos`
(on by default, the Common tab's **Hopeless candidates**) refuses a candidate at
the two points where the answer is already decided rather than re-deriving it
once per power source and once per point of the concentration sweep: v1.14.1
refutes at pass 1 of the sizing loop, which prunes **75.9%** of candidates, and
v1.17.4 refutes at pass 2, the first pass that carries the electric stage, 
which kills a further **84-86%** of what pass 1 lets through. ⚠️  Both are
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

### Current results: the complete 28-cell matrix

Every destination × both settings of beneficiation × both settings of the
programme search, on the full 1,555,667-row catalog, 12 workers, **63.2 h of
compute, zero failed measurements**. `master.py` rebuilt from the modules with a
clean `git status`; `verify_docs.py`, `verify_stage3.py` and `platform_check.py`
all green before the start. Stage 2 priced for all seven destinations in one
sitting on 2026-09-09, Stage 3 refreshed the same day, Stage 1 frozen at the
2026-08-11 snapshot for the whole campaign.

Measured on calc `1.21.2` at **that release's defaults**: `market_model` is
`capacity_cap`, `charge_insurance` is False, `use_beneficiation` and
`optimise_programme_scale` are True.

🚨  **A CONFIGURE-NOTHING RUN NO LONGER ANSWERS THIS MATRIX.** Calc v1.22.0
moved four defaults, and this campaign is a v1.21.2 measurement: the surplus
past a market ceiling was abandoned rather than sold at half price, and
reliability, the learning curve and the cost of capital were all charged. **To
reproduce a cell below, set those four flags back**:

```python
CALC_CONFIG.sell_surplus_at_discount = False
CALC_CONFIG.model_reliability        = True
CALC_CONFIG.model_learning_curve     = True
CALC_CONFIG.apply_wacc_compounding   = True
```

⚠️  That is not a small correction to apply mentally: on a capped cislunar
sample the four together are worth **2.6x on raw ore and 2.1x on the default
cell**, they do not act in the same proportion on either, and one of them
(the learning curve) runs the OTHER way. The measured decomposition is in
[calc v1.22.0](versions.md#calc-v1220); **do not scale a cell below by a single
ratio.** Every number in this matrix is still a measurement of the model it
names, which is why it is kept rather than deleted, and it is the only
seven-destination measurement the project has.

✅  **THE WHOLE CISLUNAR 2x2 HAS BEEN RE-RUN AT THE CURRENT DEFAULTS.** A
configure-nothing run answers **3.1822x**, and the four cells are 2.09x to
3.11x better than the ones below. See
[the cislunar 2x2 at the v1.22.0 defaults](#the-cislunar-2x2-at-the-v1220-defaults).
The other six destinations have NOT been re-run.

Best cost/revenue, lower is better, 1.0 is breakeven:

| destination | raw, N = 1 | raw, searched | benef, N = 1 | **benef + searched** (default) |
|---|---|---|---|---|
| **`cislunar`** | **15.3937×** | **9.5435×** | **14.1071×** | **6.6622×** |
| `mars_orbit` | 16.8482× | 11.2682× | 13.3064× | 7.3681× |
| `geo` | 45.6819× | 19.2670× | 19.0459× | 9.6949× |
| `lunar_surface` | 33.9418× | 21.1384× | 21.5387× | 11.5920× |
| `mars_surface` | 23.9964× | 18.6352× | 16.9920× | 12.6892× |
| `leo` | 58.5181× | 24.2815× | 42.9440× | 13.6875× |
| `earth_surface` | 40,147.91× | 11,606.86׆ | 24,169.72× | 7,074.20׆ |

† **Not an optimum**, at `earth_surface` the capacity ceilings are far too large
to bind, so the fleet runs to `max_fleet_ships`. See below.

Evaluable rows, raw / beneficiated: 650,921 / 660,253 (`cislunar`), 821,078 /
956,090 (`mars_orbit`), 705,030 / 712,306 (`geo`), 586,054 / 606,304
(`lunar_surface`), 731,322 / 892,563 (`mars_surface`), 776,755 / 882,429
(`leo`), 784,242 / 912,846 (`earth_surface`). The programme search never changes
the evaluable set, at any destination.

**Cislunar is still the best case**, at 6.6622× on the default cell, but the
margin is now narrow: `mars_orbit` is 7.3681×, within 11%. Still **zero viable
missions anywhere**: the best cell in the entire model is a factor of 6.7 from
breakeven, and the project's headline is unchanged.

🚨  **THIS MATRIX IS NOT COMPARABLE CELL-FOR-CELL WITH THE 20-CELL ONE IT
REPLACES.** Four things moved at once: two new destinations, `market_model` from
`elasticity` to `capacity_cap`, `charge_insurance` from True to False, and a
fresh price epoch. The superseded matrix is in
[the 28-cell campaign](versions.md#the-28-cell-campaign-2026-09).

#### The cislunar 2x2 at the v1.22.0 defaults

**A configure-nothing run today answers 3.1822x.** All four cislunar cells were
re-measured on 2026-09-16 over every row of the 1,555,667-row catalog, 12
workers, 18,586 s in total. The matrix above is v1.21.2, and the other six
destinations have not been re-run.

| cell | v1.21.2 | **v1.22.0** | factor |
|---|---|---|---|
| raw, N = 1 | 15.3937x | **5.3483x** | 2.878x |
| raw, searched | 9.5435x | **3.9218x** | 2.433x |
| benef, N = 1 | 14.1071x | **4.5298x** | 3.114x |
| **benef + searched** (default) | 6.6622x | **3.1822x** | 2.094x |

The default cell's winner is the same body on a different propellant: 2021 CX5
(D), New Glenn, **iodine**, 62,283 kg at N = 18, against argon at 34,573 kg and
N = 35. All four v1.22.0 winners fly iodine.

**Still zero viable missions.** The best case in the model is a factor of 3.2
from breakeven rather than 6.7, and the project's headline is unchanged: a
default run returns no profitable mission, and that is the correct answer
rather than a regression.

✅  **Both evaluable counts reproduce exactly**, 650,921 raw and 660,253
beneficiated, on all four cells. That is the invariant worth reading: this
release put a second price tier inside the payload knapsack, and which rows are
evaluable falls out of the mass cascade, where no price may reach.

✅  **The never-worse invariants hold on the full population**, which this
release had only ever had on 155-row cells: four pairings, roughly 650,000
paired rows each, **zero exceptions**. Selling surplus at a discount raises
revenue toward the unbounded case and must never pass it; this is the
population-scale evidence that it does not.

⚠️  **The four flags are worth 2.09x to 3.11x depending on the cell, so
one ratio will not rescale the matrix above.** The release note projected 2.6x
on raw ore and 2.1x on the default cell from a capped sample; measured, the
default cell lands within 0.3% and the raw figure is 10.7% low.

⚠️  **Do not read the wall clocks as ratios against v1.21.2.** Three of the
four are FASTER than their campaign counterparts and one is slower, but the
campaign cells were measured across four days in separate sessions, and this
release's own finding is that a ratio taken across a session is a measurement
of the session.

✅  **They ARE what `MEASURED_CELL_SECONDS` holds as of 2026-09-16**, so the
banners, `--help` and the dashboard estimate now quote this release rather
than the campaign's. What that dict is for is the LEVEL of the cell somebody
is about to run; the seven-destination SPAN stays on the campaign table, where
every row shares one release. 🚨  **This paragraph said the dict "still holds
the v1.17.7 set" and that was wrong when it was written**: it held the 2026-09
campaign row, one release back, not the one before that.

✅  **The evaluable set did not move by a single row.** That is the invariant
worth reading: this release put a second price tier inside the payload
knapsack, and which rows are evaluable falls out of the mass cascade, where no
price may reach. 660,253 in both builds is the evidence it did not.

⚠️  **The four flags are worth 2.094x here, close to the 2.1x the release
note projected from a capped sample, and that is NOT permission to project.**
What held is a sample's estimate of a model ratio over identical rows, which is
the narrow kind of projection this project has seen hold before. Extrapolating
a stride sample's WALL CLOCK or cost ratio to a full catalog is the kind that
has failed four times.

⚠️  **Do not read the wall clock as a ratio against the 9,878 s the same
cell took on v1.21.2.** The two runs are five days apart in separate sessions,
and this release's own finding is that a ratio taken across a session is a
measurement of the session. What IS comparable across the two is the work each
did: this cell prices **7.4% fewer** programme options than its campaign
counterpart and still takes longer, which is a statement about the cost of a
rung rather than about the number of them.

The population detail, the rows that got worse and why, the structural moves
and the full invariant results are in
[the full-catalog cislunar 2x2 at these defaults](versions.md#the-full-catalog-cislunar-2x2-at-these-defaults-2026-09-16).

#### `mars_orbit` and `geo`: the two destinations nothing had ever measured

**`mars_orbit` is second-best at all four settings, and the most reachable
destination in the model.** 956,090 bodies can close a beneficiated mission
there against `cislunar`'s 660,253, 45% more. It takes the **base** utility
profile deliberately, because a depot in a 1-sol orbit competes with no local
mining: everything martian is 4,100 m/s of ascent away, more than the 3,600 m/s
of TMI that delivered the cargo. So it is the control that proves **the ISRU
discount carrying the `mars_surface` result is a property of being *on* Mars,
not of Mars.** Distance is an advantage here, not a penalty: a main-belt body is
cheaper to deliver to Mars than to Earth.

**`geo` is the worst in-space destination raw and the third best
beneficiated.** 45.6819× at N = 1 despite 705,030 evaluable bodies and a
delivered price of $12,526/kg, *above* cislunar's. The objective is not a
delivery-cost problem, it is the utility table: `geo` is the first destination
whose overrides run downward on **metals and rock** rather than volatiles, iron
0.15 against cislunar's 0.70, olivine and carbon 0.05. Nobody launches copper to
geostationary orbit. GEO is a volatiles destination and nothing else, so a mixed
payload is carrying cargo the market will not pay for, and concentrating is
worth more there (−58.3%) than anywhere else measured.

#### The destination ranking depends on the configuration

| | raw, N = 1 | beneficiated + searched |
|---|---|---|
| 1st | `cislunar` | `cislunar` |
| 2nd | `mars_orbit` | `mars_orbit` |
| 3rd | `mars_surface` | **`geo`** |
| 4th | `lunar_surface` | `lunar_surface` |
| 5th | **`geo`** | `mars_surface` |

`geo` is 5th as a single raw mission and 3rd as a beneficiated programme,
overtaking two destinations. **"Which destination is best" is only answerable
per configuration**, which is the same caution this project already carries
about propellant shares, reaching the destination ranking itself.

#### Two results that change standing claims

**A `replicated`-scaling thruster now wins two cells, not one.** 2014 YN (M) on
**FEEP** takes both raw `mars_surface` cells, where the previous campaign had it
winning only the searched one and sitting at rank 5, 1.06× off, at N = 1. The
thrust gate is a mass penalty rather than a threshold, and this mission pays
6.7 tonnes of thruster and wins anyway. ⚠️  It does not survive beneficiation:
both beneficiated cells go to conventional Hall thrusters on different bodies.
Zero FEEP winners at the other six destinations.

**`earth_surface`'s searched cells are still not optima.** Terrestrial markets
run 10¹² to 10¹⁵ kg/yr against a programme delivering ~10⁷ kg, so the capacity
ceilings never bind: the fleet median **and** maximum are both 64, N is 320, and
only 0.270% of rows decline a trip. The reported 11,606.86× and 7,074.20× are
the value at the ladder's top rung, and raising `max_fleet_ships` keeps
improving them. ✅  Consistent with `earth_surface` being the destination least
changed by this campaign: every cell moved −6.5%, where others moved −11% to
−69%, because the market model is inert there and the whole delta is the
insurance removal.

#### The winner moved far more than the population did

**Every cell figure above is a winner row**, and the population medians tell a
much duller story. Beneficiation's median improvement across the whole evaluable
population came within **0.1 to 2.3 percentage points** of the values the
2026-08 campaign committed, while the winner rows moved by 8 to 69%:

| destination | benef, winner row | benef, population median | 2026-08 median |
|---|---|---|---|
| `cislunar` | −8.4% | **+39.4%** | +39.5% |
| `lunar_surface` | −36.5% | **+66.1%** | +63.8% |
| `earth_surface` | −6.5% | **+77.7%** | +77.7% |

⚠️  The two middle columns use opposite conventions and are not each other's
negation: the median is `median(1 − r)` over the population, the committed
convention; the winner column is one row against its 2026-08 counterpart.

So `capacity_cap` and the insurance removal **reshaped the top of the
distribution and left the middle where it was.** A headline that moves 50% over
a median that moves 0.1 pp is a statement about one asteroid, not about the
model.

#### Invariants: clean on all twenty-eight cells

Never-worse holds on 28 pairings with zero exceptions; the mass ledger closes to
`0.000000000 kg` on every cell; `N = F × W` on every row of all fourteen
searched cells and `W > trips` never. **70 checks, 0 failures.**

**The structural change is that programmes now decline the rig's last trips.**
`W < trips` runs 20.86% of raw searched `cislunar` rows against the 2026-08
campaign's **0.319%**, and 35.99% at `mars_orbit`. Under a hard capacity ceiling
the extra campaign cannot be **sold**, where a demand curve would always have
sold it at a worse price. Fleet and programme sizes moved with it: cislunar's
fleet median went 2 to 6 and its N median 10 to 30.

Winners: **2021 CX5 (D) takes 8 of the 28 cells** and **2018 DT 6**, but neither
sweeps a destination the way 2021 CX5 swept two of them in 2026-08. Only
`earth_surface` has a single winner across all four cells (**2016 PN38**).
`mars_surface` and `mars_orbit` change winner on three of four axes.

#### Runtime

**A default cislunar run is ~2.7 h** on 12 workers, and the full wall clock for
all twenty-eight cells is in [Beneficiation](#beneficiation). ⚠️  Every timing
older than calc v1.21.0 is low for the current build: the capacity ceilings cost
1.29× to 2.31× depending on the cell, landing hardest where a programme ladder
exists.

## Version history

Every release note, and every measurement table these results superseded, is in
**[`versions.md`](versions.md)**: reorganised newest-first, with the module
versions each release carried. It used to live in this file and had grown to
roughly half of it.

It also carries the **[per-module changelogs](versions.md#module-changelogs)**,
one section per stage in numeric order, which is where the *schema* history
lives: which release added which config field and which output column, i.e. what
tells you whether an archived CSV can answer the question you are asking of it.
Those were 2,063 lines of comment above the four `pipeline_version` fields
until 2026-09-02.

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

Return-sample architecture, uncrewed throughout: no life support, no crew
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
  best case the model can reach, `cislunar` delivery plus beneficiation plus a
  searched programme, still comes in **~13× short** (**13.1443×**, full
  catalog, calc v1.17.7; **20.5895×** at a single mission). There is no "don't
  fly" option, so the ranking is really *which target loses least*.
  (This was `mars_surface` at ~25× until mineral_value v1.7.0 priced the local
  resources a planetary surface already has; Mars is now the *worst* of the
  four in-space destinations at 74.6748× raw.) **Scale does not rescue it**,
  and since v1.14.0 it does not even help monotonically, market saturation
  sees the programme's concurrent output, so the optimum programme size is
  interior. Searching it per body is worth about 40%, which is the difference
  between losing twenty dollars per dollar earned and losing thirteen.
- **Rank by `total_cost_usd / gross_value_usd`, not `profit_usd`.** Revenue is
  orders of magnitude below cost in most configurations, so `profit_usd`
  reduces to `-total_cost_usd` and `top_profitable()` becomes a pure cost
  ranking, a Δv table wearing a profit label. Until v1.10.0 the *search
  inside* Stage 4 had the same flaw for the same reason, and nothing had
  optimised the ratio this README ranks by. See `selection_key`.
- **Cheap launch does not rescue this.** Launch is ~2.3% of a mission. Zeroing
  it entirely improves the ratio by 2.3%.
- **In-space utility fractions are judgements.** `IN_SPACE_UTILITY` and its
  per-destination overrides decide how much of the launch-cost-avoided each
  commodity captures, and no market exists to calibrate them against. They are
  the softest numbers in the pipeline, and the per-destination discounts added
  in v1.7.0 are softer still; they are judgements about economies that do not
  exist. They are held to running *downward* for that reason.
- **Low-thrust trajectories are sized, not optimised.** Trip time and power
  are now modelled (see [What the model now charges for](#what-the-model-charges-for)),
  but the EP stage is sized to a fixed target thrusting time rather than having
  its trajectory jointly optimised against payload and arrival date.
- **The mining rate has no flight heritage.** No one has sustained-mined an
  asteroid, so `mining_rate_kg_per_day_per_kg_rig` is an engineering
  assumption. It is a single obvious dial rather than a hidden infinity, but
  it is still an assumption.
- **Δv is analytic, not trajectory-optimised, and it is OPTIMISTIC.** The
  patched-conic estimator meets the target at an apsis and takes the whole
  inclination change at departure, using `a`, `e` and `i` only. Measured
  against a Lambert porkchop with real 3-D geometry over 400 sampled bodies, it
  understates outbound Δv by a **median 1.30 km/s (11.9%), on 86% of bodies**;
  against the three real missions whose published figures it is validated on it
  is low by a consistent **0.40 to 0.46 km/s**. Every campaign this project
  has run inherits that bias, the 28-cell one included, and every ratio in them
  is correspondingly favourable.

  ⚠️  **The obvious fix makes it worse.** The estimator also *over*charges the
  plane change, by a median 4.87%, and the two errors partially cancel;
  correcting only the overcharge increases the total error in every inclination
  band. Neither term should move without the other. Both measurements, and the
  validated solver behind them, are in
  [`research/starred-repos/FINDINGS.md`](research/starred-repos/FINDINGS.md).
- **Launch windows are statistical, not ephemeris-based.** The synodic period
  gives an expected wait; the model does not compute actual departure dates,
  so it cannot tell you *which* window. As of catalog `1.2.0` the catalog does
  at least carry `element_epoch_jd`, so `mean_anomaly_deg` can be referred to a
  date; before that it could not, which made real phasing impossible rather
  than merely unimplemented.
- **Composition is uniform.** Each asteroid is its taxonomy class's mean
  composition all the way through: no core/mantle structure, no regolith
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
  hardware, kilns, condensers, cold traps, is not sized or costed.
- **The duty-cycle alternative to a battery is not priced.** Night-side power
  *is* charged, since v1.14.0, but a rig could mine slowly in daylight instead
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
  deliberately, the propellants that most want a generous tank model are the
  speculative ones.
- **Non-Earth launch origins are not modelled.** Stage 3 lists a lunar mass
  driver and a lunar space elevator, both roughly two orders of magnitude
  cheaper per kg than any rocket. Stage 4 departs from Earth and prices a
  discrete launch, so it cannot read either; their payload figures are annual
  throughput. They are markers for an architecture the pipeline does not have,
  not inputs to it.
- **Sails and tethers cannot be sized at all.** Anything propellantless has no
  mass ratio, so the rocket equation reports that it moves any payload for
  free. Doing it honestly needs a thrust-limited trajectory solver, the same
  thing missing from the EP stage, so they are excluded rather than allowed
  to report infinity.

## What the model charges for

Every model below defaults **ON** and each one moved every number when it
landed. They are corrections, not options; the flags exist to isolate an
effect, not to be left off. **When each one arrived is in
[`versions.md`](versions.md); what it charges for is here.**

⚠️  **The count is deliberately not spelled out.** It has rotted twice, once in
each direction, which is the exact failure the "when a number changes, grep the
prose too" rule in `CLAUDE.md` exists to catch. Count the list. One entry
(orbital refuelling) was later *withdrawn*, so the list is one longer than the
charges.

⚠️  **`use_beneficiation` and `optimise_programme_scale` are NOT on this list**,
and defaulting both ON does not put them on it. They are questions ("ship
concentrate or ore?", "how big a programme?"), not subsidies being withdrawn.
The test is not "is it on by default"; it is **"was the model getting something
for free before?"**

🚨  **THREE ITEMS LEFT THIS LIST IN CALC v1.22.0 AND ARE NOT RETRACTIONS.**
Mission reliability, the learning curve and the cost of capital all still pass
the membership test -- the model really was getting each of them free -- and
they are all **off by default now** for the reason
[insurance](#what-the-model-deliberately-does-not-charge-for) is: they price
something other than the physics and hardware of moving a kilogram. Their
sections below are kept in full, because what they charge for is still what
they charge for; each one now opens by saying it is off. **Set all four flags
True to reproduce anything measured before v1.22.0**, the 28-cell campaign
included.

### Gaps in what the model charged for

Time, rate, wear and the market: things that were happening to a real mission
and were not on any invoice.

**Low-thrust trip time** (`model_low_thrust_time`). Electric propulsion used to
pay a Δv penalty and nothing else; it flew its burns instantly on power it
never carried. A thruster's power fixes its thrust, so burning `m_prop` takes
`m_prop·(Isp·g0)² / (2·η·P)`: **high specific impulse buys propellant mass at a
quadratic cost in time-or-power.** The EP stage is sized to finish inside
`ep_target_thrust_yr` (3.0), and the array plus thruster/PPU mass that demands
goes into the same rocket equation as everything else. A typical electric
winner hauls ~4,900 kg of power system against a 2,000 kg mining rig.

✅  Validated against **Dawn**, the only mission to have flown this regime: at
its 2.2-3.0 AU operating distance the formula gives 5.0-9.3 years of thrusting
against ~5.9 actually flown. The 1/r² term does the work; evaluated at Dawn's
1 AU array rating the same sum gives 1.0 year and is nonsense. **If this check
ever passes that easily, the 1/r² term has been lost.**

**Launch windows** (`model_launch_windows`). Departure needs phasing and
alignments recur at the synodic period, so the expected wait after mining is
half a period. This punishes **NEAs hardest**, which is the opposite of the Δv
story: a body whose period nearly matches Earth's drifts in phase very slowly.

| Semi-major axis | Period | Synodic with Earth |
|---|---|---|
| 1.05 AU | 1.08 yr | **10.0 yr** |
| 1.13 AU | 1.20 yr | 6.0 yr |
| 2.70 AU | 4.44 yr | 1.3 yr |

⚠️  Accessibility in Δv and accessibility in *time* pull in opposite
directions, and only one of them was modelled before. **Do not assume a
low-Δv target is a fast one.**

**Bound-water liberation** (`model_water_liberation`). C/B/D-type "ice" is
water locked into phyllosilicates; it is baked out at ~700 K, not scooped.
Stage 3 charges **2,500 Wh/kg**, derived from heating the rock through
dehydroxylation plus the enthalpy of dehydration plus vaporisation, and
matching the 1-3 kWh/kg in the ISRU literature. It had been extracted free and
sold at full launch-cost-avoided.

**Learning curve** (`model_learning_curve`, **off** since calc v1.22.0;
`learning_curve_rate` 0.85). Wright's law on the per-mission articles,
capsule/lander and power system. The amortised mining rig is **excluded**,
because it is one shared unit rather than N built, and a curve on it
double-counts. Exactly 1.0 at `nre_amortization_missions = 1`, so a
single-mission run is untouched either way; 0.44 at N = 100.

⚠️  **It is off because it prices a factory, not a mission.** Wright's law is
fitted to programmes that built dozens to hundreds of articles; the ladder here
routinely proposes N in the tens, and crediting them with serial-production
learning assumes an industrial base the run never modelled. It also runs in the
generous direction, which is the direction this model refuses everywhere else.
Set `model_learning_curve` True to restore it.

**The market model** (`market_model`, `"capacity_cap"` since calc v1.21.0).
The only term in Stage 4 that pushes back on programme size: N improves five
levers at once (NRE/N, autonomy NRE/N, the learning curve, the rig's share and
reliability growth) and this is the sixth. Without something here,
`nre_amortization_missions` has no stopping point and the objective is monotone
in N, so the search reports where the ladder stopped rather than an optimum.

Four models, and the choice is what the run is claiming about prices:

| `market_model` | price behaviour | what bounds a programme |
|---|---|---|
| **`capacity_cap`** | constant at any volume | a hard kg/yr ceiling per commodity |
| `single_mission` | constant | N pinned at 1, no search, no ceiling |
| `elasticity` | `(1 + Q/Q_market)^(-1/ε)` | the demand curve |
| `unbounded` | constant | nothing; a **diagnostic**, and the run says so |

**`capacity_cap`** holds the price flat and clips the quantity instead.
Everything inside a commodity's ceiling sells at the full price Stage 2 quotes.
How much one delivery may sell is how long the destination has
been accumulating since the last one: `cap × cadence / F` in steady state, and
`cap × mission_duration` for the first delivery, which arrives at a market that
has been importing from Earth for the whole outbound-and-back trip. Averaged
over a programme of N that is
`cap × [duration + (N−1) × cadence/F] / N`, which is exactly `cap × duration`
at N = 1 and converges on the steady state as N grows.

The ceilings go **into the payload knapsack**, which is the part that makes the
model behave: a load that caps out on iron keeps walking down the price order
and spends the freed hold space on whatever is next, rather than flying the
excess unsold. Per-item upper bounds turn an unbounded fractional knapsack into
a bounded one, which greedy still solves exactly, so this is a constraint
*inside* the optimiser rather than a clamp on top of it.

**What happens past a ceiling is `sell_surplus_at_discount`, and since calc
v1.22.0 the answer is that it SELLS.** A destination that absorbs 100 t/yr of
water at the quoted price does not become unable to take the 101st tonne; it
takes it at a price that clears, which is the entire content of a supply curve
sloping down. The surplus is sold at `surplus_price_fraction` of full price,
**0.5** by default. Set the flag `False` for v1.21.0's hard wall, where the
surplus earns nothing and is reported as unsold; that is what the whole 2026-09
campaign was measured on.

⚠️  **This does NOT unbound the programme**, which is the objection to check
first, and the reason it does not is one sentence: the marginal kilogram past a
ceiling is worth strictly less than the one before it. A bigger fleet delivers
more often, so each delivery gets a shorter accumulation window and a larger
share of the load falls into the discounted tier, so another ship still adds
its full cost against a falling marginal revenue, and the objective still turns
over on its own. A wall is the `surplus_price_fraction = 0` end of the same
model, and `1.0` is the only setting that would genuinely remove the ceiling.

**In a concentrated load the discount changes what the ship carries, not just
what it is paid.** Each phase now appears in the knapsack twice, at full price
up to its ceiling and at the discounted price above it, and the greedy walk
interleaves them; a rich phase's half-price surplus can outrank a poor phase's
full-price allowance, and where it does, the optimal load carries it instead.
That is a different load from the one a wall chooses, not merely a differently
priced one. Raw ore cannot be reshaped at all, so there the surplus is simply
carried and sold at the discount.

Three output columns report it, kept apart because a price multiplier, a
discounted sale and a refused one are three different claims:
`market_clearing_fraction` is the share of the assembled load's gross value
that cleared, `surplus_payload_kg` is mass sold past a ceiling at the discount,
and `unsold_payload_kg` is mass that earned nothing. **The last two are
exclusive** and `verify.py` check 7 asserts it: under the v1.22.0 default the
mass lands in `surplus_payload_kg` and `unsold_payload_kg` is 0.0, and turning
the flag off swaps them over. ⚠️  The assertion carries a milligram floor,
because on the beneficiated path `unsold` is a difference of two sums that are
mathematically equal, and it can land one ULP off zero -- measured at
3.6e-12 kg against a 24-tonne payload.

⚠️  **The ceilings bind at the fleet sizes the model actually chooses.**
Cislunar's whole import budget is 100 t/yr and water's propellant share is
55 t/yr, against a median raw cadence of 1.384 yr and a median searched fleet
of **3**.

⚠️  That fleet median said **2** until 2026-09-14, which was the 2026-08
`elasticity` figure standing in a `capacity_cap` argument. The raw searched
cislunar median is 3 and the beneficiated one is 6; both are quoted elsewhere,
so the cell has to be named. Re-derived by `campaign/population.py`.

✅  **They were recalibrated in calc v1.21.1 and the LEVELS did not move**, on
the argument that they never were curve parameters: every row in
`IN_SPACE_ANNUAL_DEMAND_KG` is documented as an absorption budget, `geo` being
550 geostationary satellites at ~70 kg/yr of station-keeping propellant and
`mars_surface` being "a base that imports 20 t/yr". A kilogram delivered inside
a consumption budget genuinely displaces a launched kilogram, so it earns full
launch-cost-avoided; the curve, which had the price already quartered at exactly
the quantity the base needs, was the term using the number wrongly. What v1.21.1
did change is that the composition residual now has a ceiling at all. See
[calc v1.21.1](versions.md#calc-v1211) for the derivation, and for the
quarter-ceiling alternative measured and declined.

⚠️  **`earth_surface` is unbounded whichever model you pick.** Its ceilings are
terrestrial production, 10¹² to 10¹⁵ kg/yr, so nothing binds and the cell stays
monotone in N exactly as it was under `elasticity`. A downmass or recovery
ceiling would fix that and does not exist yet.

**`elasticity`** is the v1.14.0 term, unchanged and still available.
`P/P0 = (1 + Q/Q_market)^(−1/ε)` against Stage 2's `annual_market_kg`, with
ε = 0.5 (precious-metal demand is inelastic). Returning 180 t/yr of platinum
doubles world supply and quarters the price; delivering 6.6 t/yr of water to a
Mars base that can absorb 11 t/yr cuts the price to 0.39. Without it,
`nre_amortization_missions` had no stopping point: you could amortise
development across a fleet whose output would have destroyed the price
justifying it.

⚠️  **Both models read the same ceilings**, and differ only in what they do
when one is reached: `elasticity` bends the price, `capacity_cap` stops the
sale. World production is USGS; the in-space absorption ceilings (LEO 500 t/yr,
cislunar 100 t, lunar surface 50 t, Mars 20 t) are **judgement, not
measurement**, since no such market exists. They are destination *totals* split
across commodity classes rather than a figure each commodity gets to itself, so
the Mars water ceiling is 0.55 × 20 t = 11 t/yr, and the ceiling follows the
**value route**, so anything flown home is bounded by terrestrial production.

🚨  **"Rather than a figure each commodity gets to itself" is the rule, and
calc v1.21.2 is the release that made the code obey it.** A payload carries
five phases and two of them, `silicates` and the composition residual, sell
into one market: the residual is priced at the silicates quote precisely
because that is what it is. Every consumer looked its ceiling up per PHASE, so
each drew the full silicates allowance and a load could place twice the market.
It applied to **100% of bodies** at a **median 84% of the load**. The allowance
is pooled per market now, and drawn down as it is spent. See
[calc v1.21.2](versions.md#calc-v1212).

**Rig service life and terminal value** (`model_rig_service_life`). The rig was
amortised across `nre_amortization_missions` with no upper bound, so a
programme could spread one machine across 100 missions of two years each: 200
years of duty from something chewing rock. A 15-year life now *caps* the
amortisation, and the cap makes long-stay programmes markedly **more**
expensive, not less:

| Stay per mission | Missions one rig can serve | Charge vs. old flat ÷100 |
|---|---|---|
| 0.25 yr | 60 | 1.7× |
| 1.0 yr | 15 | 6.7× |
| 2.0 yr | 7 | **13.8×** |

Life remaining when the programme ends is credited at the salvage fraction
(0.50), but only when `nre_amortization_missions > 1`: a rig parked at an
asteroid nobody revisits is stranded, not an asset.

**Mission reliability** (`model_reliability`, **off** since calc v1.22.0).
Revenue was certain. With this on, expected revenue is
`p_launch(0.97) × exp(−T/MTBF)(30 yr) × p_mining(0.85)`, about 0.70 for a
five-year mission.

⚠️  **Off by default because two of those three numbers are assumptions, not
measurements.** Launch reliability is an observed rate over hundreds of
flights; the cruise term is an exponential on an assumed MTBF, and `p_mining`
is a judgement about a machine nobody has built. Multiplying the ANSWER by them
puts a ~30% discount into every headline ratio while leaving it exactly as
solid as the guess it came from. A default run now answers **what this costs if
it works**, which is the same framing that makes the two surface delivery
prices lower bounds; set `model_reliability` True for the risk-weighted
question. ⚠️  **Costs are still charged in full**, which is
both conservative and correct: you spend the money whether or not it works.
Insurance never entered this term, it replaced hardware on failure rather than
revenue, so calc v1.20.0 turning both premiums off changes nothing here.

`p_mining` is counted from the full flight record of regolith-contact
mechanisms, not from the failures alone:

| | Missions |
|---|---|
| **Succeeded** (10) | Apollo 15-17 drills/scoops; Luna 16/20/24; Stardust aerogel; Phoenix arm; Curiosity drill (feed mechanism failed 2016, recovered by feed-extended drilling); Hayabusa2 sampler + SCI impactor; OSIRIS-REx TAGSAM (121.6 g against a 60 g requirement); Perseverance corer; Chang'e 5 and 6 |
| **Partial** (1) | Hayabusa; projectile never fired, but contact dust was still collected and returned |
| **Failed** (2) | Philae's harpoon pyrotechnics; InSight's HP³ mole, which could not get purchase in Martian regolith |

That is **11/13 = 0.85** counting Hayabusa as the success it ultimately was, or
0.77 counting it as a loss. The canonical roster, with per-mission detail, is
the note in `modules/transportation.py`.

The honest caveat: none of these is *sustained* mining. They are one-shot
collections of grams to kilograms, not a rig moving 200 kg/day for years. 0.85
is the demonstrated **mechanism** rate; sustained-operation exposure is carried
by the spacecraft MTBF term rather than double-counted here.

**Reliability growth** (`model_reliability_growth`, inert while
`model_reliability` is off, which is the default since calc v1.22.0).
`p_mining` used to sit at
its first-of-kind value however many missions a programme flew, the one place
the model was *pessimistic*. Duane/AMSAA: failure probability falls as a power
law in cumulative production, `q(n) = q_first · n^(−α)` with α = 0.30, the
bottom of MIL-HDBK-189's *active* growth band, appropriate for hardware that
flies once every few years with no test fleet. Capped at a 0.95 mature ceiling.

| Programme size | `p_mining` (fleet average) |
|---|---|
| 1 | 0.850 |
| 10 | 0.902 |
| 100 | 0.943 |

⚠️  Reported as the **mean over missions 1..N, not the terminal value**. NRE and
the rig amortise across the whole programme, so per-mission expected revenue
has to use the programme average; quoting the last mission's reliability would
credit every mission with heritage only the last one has. Exactly 0.850 at
N = 1. ⚠️  Launch and cruise reliability deliberately do **not** grow: launch
vehicles are already mature, and MTBF is a duration exposure rather than a
heritage question. Do not "complete" the model by adding growth to them.

**Cryogenic boil-off** (`model_propellant_boiloff`). Return propellant sits in
the tank from launch until the departure burn, years rather than hours. Loading
per kg actually burned:

| Hold | hydrolox (0.05%/day) | methalox (0.012%) | storable (0%) |
|---|---|---|---|
| 1 yr | 1.20× | 1.04× | 1.00× |
| 5 yr | **2.49×** | 1.25× | 1.00× |
| 8 yr | 4.31× | 1.42× | 1.00× |

Folded into an effective return Δv, which leaves the closed-form cascade exact:
since `m_return_prop` scales with `(R−1)`, inflating that term by `k` is
`R_eff = 1 + (R−1)k`. ISRU return propellant is exempt; it is manufactured at
the asteroid on departure.

**In-space manufacturing** (Stage 2). Raw Fe-Ni is not a pressure vessel, and
the gap used to hide inside the 0.70 utility factor: the refinery was assumed
into existence and never costed. Now explicit, ~$230/kg for metals:

- **Energy** at **$6.08/kWh**, the capital cost of a kilowatt-hour in deep
  space ($800/W-EOL over a 15-year life), roughly 100× terrestrial industrial
  power, which is why in-space processing is not obviously free. Metals take
  5 kWh/kg; terrestrial electric-arc steelmaking is 4-5 kWh/kg and there is no
  carbothermic shortcut in vacuum.
- **Plant** at **$200/kg refined**: $300k/kg of deep-space hardware at
  100 kg/yr throughput per kg of plant over 15 years.

Deducted from the *used in space* route only; material shipped down is refined
on Earth. ⚠️  The plant's **mass** is deliberately not in any mission's rocket
equation: it belongs to the buyer at the depot, not to the miner.

### Mass flown and never billed, or billed and never flown

**The defect class to look for in this codebase first.** The mass cascade and
the cost cascade are written in different places, and nothing checks that every
kilogram in one has a price in the other. The one-line assertion that catches
the whole family is
`hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg`, and
one release introduced three fresh instances while fixing three older ones.

**The electric propulsion stage.** The EP array and thruster were sized, pushed
through the rocket equation, and never passed to the cost model, so a 309 kW,
14-tonne electric stage was free and electric propulsion won missions on
hardware nobody had to buy. Priced in two parts, because they cost wildly
different amounts per kilogram: the **array** off the existing $800/W-EOL
power-system row, the **thruster and PPU** off a Stage-3 row at **$1.5M/kW**,
anchored on a NEXT-C flight string (7 kW, ~47 kg, in the $10-15M class) with a
$0.5-3M/kW range because high-power Hall systems buy down from there. ⚠️
Flagged soft: this pipeline sizes some missions at 300 kW, six times the
largest article ever built.

**Return-vehicle structure** (`return_structure_frac_of_payload`, 0.15). The
return vehicle's dry mass was a flat 500 kg however much it carried, so the
cascade loaded 125 tonnes of ore into a half-tonne can: **250:1
payload-to-structure**, against 0.4:1 (Cygnus PCM) to 2:1 (Dragon) for real
cargo spacecraft. Nothing caught it because the only other bound on returned
mass was the launch vehicle's fairing *volume*, which dense ore never fills.
The 500 kg is now a floor and 15% of the payload is added for tankage, primary
structure and cargo restraint. The closed-form solver carries the term exactly:
writing `g = s(1+f) − 1`, it reduces to the old expression when `f = 0`.

**Propellant tankage** (`model_tank_mass`). `density_kg_per_L` had been
computed for four releases and read by nothing. A tank's mass scales with the
**volume** it encloses, not with the propellant mass inside it, so leaving it
out was a straight subsidy to whichever propellant had the lowest density,
which is the same propellant that has the highest specific impulse: the error
compounded rather than cancelling. LH2 is 0.0708 kg/L against kerolox at 1.015,
fourteen times the tank per kilogram burnt.

`tank_kg_per_L` is derived per storage class and anchored on flight articles
rather than asserted. As a fraction of the propellant it holds: **iodine 0.2%**
(solid at ambient pressure), xenon 1.9%, kerolox 2.5%, an APCP motor case 6.9%
against Star 48B's measured 6.4%, hydrolox 9.7% against Centaur III's measured
~9.7%, krypton 12.5%, cold gas 46%, and bare LH2 **53%**, which is what a
nuclear-thermal stage has to earn its 900 s against.

The closed-form solver generalises with two scalars rather than going
iterative: `k = 1/(1 − t(R_ret − 1))` on the return leg, where the tank flies
home inside the cargo's post-burn mass, and `k_out` on the outbound leg, where
it is staged at the asteroid. Both are exactly 1 at `t = 0`. 🚨  `t(R − 1) ≥ 1`
means **the tank cannot close**, and that is infeasible rather than expensive.

**Thruster scalability** (`thruster_kg_per_n`). The largest single correction
in the project, and the clearest statement of the defect class: **launch was
modelled as an integrated vehicle with a payload it can actually lift, while
in-space propulsion was modelled as a bare specific impulse.** One side had a
capacity limit and the other did not, so Stage 4 sized the electric stage on
power alone and buying enough kilowatts turned any row in the propellant table
into a cargo tug: 31.8% of cislunar winners were pulsed plasma thrusters and
24.3% electrospray, devices whose largest flown units make *micronewtons*,
being asked for ~7-10 N.

The gate is **mass, not a threshold**: thrust is momentum flux, `T = ṁ·ve`,
which owes nothing to efficiency, so Stage 3 carries kg/N per technology and a
device making µN/kg reports thousands of tonnes of thruster and dies in the
rocket equation on its own. The evaluable catalog halved and chemical
propulsion came back. ⚠️  Because it is a penalty rather than a cutoff, the
right test is not whether such devices *survive* but whether one ever **wins**,
and as of 2026-08-24 one does, at `mars_surface` with the programme search on.
That is the mechanism working, not leaking.

**Argon storage** (Stage 3). Not a flag but a reference-table fix, and the one
that moves numbers. The row carried liquid-argon density, which exists only at
87.3 K, *together with* a boil-off of zero: its own two comments read "liquid
NBP (cryogenic storage)" and "stored supercritical at ambient temperature",
three lines apart. Argon was winning ~25% of missions on that combination.
Split into the two articles that actually exist; see
[calc v1.12.0](versions.md#calc-v1120--transportation-v1100).

**Cargo-water power plant** (`model_water_liberation`). The liberation energy
for water sold as cargo had sized an array that the cost model paid for and the
rocket equation never carried. The flag is unchanged; what changed is that the
array is now flown.

**Launch acceleration** (`max_payload_accel_g`, 15 g). Every real launcher in
Stage 3 is 6 g or less; SpinLaunch is 10,000 g, a light-gas gun 30,000,
StarTram 30. The column existed to disqualify them and nothing read it, so only
their `concept` status was keeping them out.

**Propellant tank fabrication.** $6,000/kg, Centaur-derived (~1,880 kg of
structure, a ~$30M stage less ~$20M of RL10). Tank mass had been flown and
launch-charged for a release and never built. It is 0.004-0.6% of mission cost,
median 0.012%, and it is kept precisely because it is small: **these are only
ever found by checking every term rather than the big ones.**

**Orbital refuelling** (`charge_tanker_flights`, **gated off**). Starship's
escape payload (27 t) *exceeds* its GTO payload (21 t). No propulsion system
can do that; the escape figure is for a vehicle topped up in orbit first.
Charging for it was briefly implemented catalog-wide, at **$1.08B on top of a
$90M launch**, and that is the **withdrawn** entry: Stage 4 has no
escape-direct scenario, so the charge was real but billed against a scenario
this module does not have. Gated behind `escape_direct_launch`, which nothing
sets, rather than deleted, so the day this module gains direct injection the
charge becomes correct and the column is already wired.

### Figures that were written down and never wired in

Both of these had sat in a Stage 3 reference table, correctly derived and
correctly cited, behind a note saying they were not modelled in Stage 4, and
Stage 4 does not load that table. They were quoted as known limitations for two
releases and nothing moved. **Writing a gap down had been mistaken for closing
it. A reference table nobody reads is not a model.**

**Volatile cargo containment** (`model_volatile_containment`). The pipeline
priced water at every in-space destination, charged the energy to bake it out
of phyllosilicate and flew the array that does the baking, and charged
**nothing** to stop it subliming across a four-year cruise. Not a rounding
term: the best cislunar missions are **~88% water by mass**, so the commodity
carrying the entire result was the one flying free. A sealed shaded hold at
0.05 kg/kg, *incremental* to the 0.15 ore restraint; the hopper holds the
cargo, the seal and the shade keep the volatile fraction from leaving. Charged
on water only, since carbon and organics are refractory at these temperatures
and ride in the hopper like rock.

**Eclipse and night-side power** (`model_eclipse_power`). Processing power is a
*continuous average* draw and the plant was sized straight off it, which is
only right if the rig is never in shadow. It stands on a rotating body. Two
terms: an array oversize of `[(1−f) + f/η]/(1−f)` = **2.11×**, which is a
sizing factor no W/kg figure could ever have absorbed; and storage sized on the
**body's own rotation period**, which finally makes `rotation_period_h`,
carried by Stage 1 from the start and read by nothing, a quantity the model
uses, so a slow rotator is genuinely a worse place to mine. Together they cost
**4.7×** at 1 AU and the median 10.2 h rotation, not the "roughly doubles" the
storage table itself estimated.

### Bounds that only bite at programme scale

⚠️  **These two are the only entries on this list that are inert at N = 1**, so
no single-mission figure moves for either, which also means neither can be
checked by re-running a headline.

**The rig's duty cycles** (`model_rig_trip_limit`). `life` is "Mining rig
service life" = **15 YEARS**, a figure whose own Stage 3 notes describe
corrosion, thermal cycling and radiation dose. Dividing it by the stay gave a
mission count, and **nothing anywhere bounded duty cycles**, so at a short stay
one rig was good for twelve consecutive digs on the strength of a number that
only ever promised it would not have rusted meanwhile. A rig parked between
campaigns ages slowly; one cutting rock does not. Stage 3 adds a maximum of
**5 trips** and the min of the two bounds is taken, so long stays stay
calendar-limited and short ones are cycle-limited, which is the correct way
round and was the entire gap.

**Programme calendar time** (`model_programme_calendar`). One rig digs one hole
at a time, so campaigns on a ship are strictly sequential, and the cost model
compounded each mission's up-front costs over that *mission's* own duration and
stopped, which for a programme assumes every mission happens at once. The lines
carried free are the **amortised** ones, bus NRE, autonomy NRE and the rig,
because those alone are bought once at t = 0 and divided across missions that
sell years apart. A mission's own articles are unaffected: shift a whole cash
flow later and its cost/revenue ratio does not move.

⚠️  Salvage gets the **reciprocal** series, because it is collected at the
*end*; compounding a refund forward alongside the cost it is netted against
would pay a bonus for taking longer to collect it. Both multipliers are exactly
1.0 at one campaign per ship, which is what makes the term inert at N = 1.

🚨  **AND IT IS INERT AT EVERY N AS OF CALC v1.22.0, BECAUSE IT IS TIME-VALUE
AND THE COST OF CAPITAL IS NOW OFF.** Both multipliers are exactly 1.0 at
`wacc = 0` by construction, so this flag charges nothing until
`apply_wacc_compounding` is turned back on. It is left ON rather than flipped,
because the flag means "charge the calendar the programme spans" and that is
still what the model should do the moment there is a rate to charge it at; the
run banner says which of the two states it is in rather than leaving a reader
to derive it.

## What the model deliberately does not charge for

The list above is what the model was getting **free** and now pays for. This is
the shorter list of the opposite kind: costs that are real, that a real
programme pays, and that this pipeline does not price because they are not the
question it is asking.

**The test for this section is that the charge would be RIGHT and is still not
asked for.** That is what separates it from the withdrawn orbital-refuelling
charge, which is *wrong* for this module and gated rather than declined, and
from the corrections above, which the model was getting free.

🚨  **CALC v1.22.0 TRIPLED THE LENGTH OF THIS LIST, and that is the largest
single change to what a default run means since v1.17.0.** Mission reliability,
the learning curve and the cost of capital all pass the same test insurance
does: each is real, each is priced off something that is not a mass, a
Delta-v or a kilowatt, and each was being applied to the ANSWER rather than to
the physics. **Every one of them can be turned back on individually**, and the
four together reproduce v1.21.2.

**The cost of capital** (`apply_wacc_compounding`, default `False` since calc
v1.22.0). Up-front costs were compounded at Module 3's **10%** WACC over the
mission duration, bucketed so an end-of-mission line is not inflated by the
whole span. A discount rate is a statement about *whose money this is* -- an
agency's, a sovereign fund's, a venture portfolio's -- and the model does not
know and should not guess. It is not a rounding term either: an up-front line
compounded over a 5-to-12-year mission is worth roughly **twice** its face
value, which is the same 2.12-2.38x multiplier measured on the insurance
premium, applied to every up-front line in the cascade.

⚠️  **It takes the programme calendar charge with it.** `model_programme_calendar`
is time-value, and `programme_calendar_multipliers` returns exactly (1.0, 1.0)
at a zero rate, so that term is inert until the rate comes back. Duration still
binds through the dig, the launch windows, the rig's life and
`max_mission_duration_yr`, all of which are physical rather than financial.

**Mission reliability** (`model_reliability`, default `False` since calc
v1.22.0). See [its own section above](#gaps-in-what-the-model-charged-for) for
what it charges and where the 0.85 comes from. It is here because of what it
multiplies: `P` is a product of one measurement and two judgements, and
applying it to expected revenue puts both judgements into every headline ratio
while leaving the ratio exactly as reliable as they are. A default run answers
**what this costs if it works**; that is a lower bound in the same sense the two
surface delivery prices are.

**The learning curve** (`model_learning_curve`, default `False` since calc
v1.22.0). Wright's law at 85%. It prices a factory, and this pipeline does not
have one: the curve is fitted to programmes that built dozens to hundreds of
articles, and crediting a ten-mission programme with that learning assumes an
industrial base the run never modelled. Exactly inert at N = 1 either way, so
no single-mission figure in this project moves for it.

**Insurance** (`charge_insurance`, default `False` since calc v1.20.0). Module 3
prices two premiums, a **$1.5M** third-party liability flat and launch insurance
at **10%** of (launch + spacecraft book value), and until v1.20.0 every mission
was charged both. They are not wrong. They are out of scope: everything else in
the cascade is a mass, a Delta-v, a kilowatt or a flight-rate, and a premium is
priced off an underwriter's book. The two surface delivery prices are already
declared [marginal-transport lower bounds](#what-a-kilogram-is-worth) with no
NRE-style programme overhead in them, and a premium is exactly that kind of
overhead.

It was also, until calc v1.22.0, the model saying one thing twice:
`model_reliability` discounted expected revenue by
`p_launch x exp(-T/MTBF) x p_mining` while charging every cost in full, and a
premium is what a programme pays to turn that same risk into a certain payment.
⚠️  **That second argument is gone**, because reliability is off by default too
now, and the two terms are off together. It is left here because it was one of
v1.20.0's two reasons and the OTHER one -- a premium is priced off an
underwriter's book rather than off a mass -- is untouched and is sufficient on
its own. Turn reliability back on and the double count returns with it.

⚠️  **Turning it off is worth more than the invoice says**, because a
premium is an *upfront* line and so is multiplied by contingency and then
compounded at the upfront WACC multiplier: it is **2.4% to 4.3%** of total cost
and removing it improves the ratio by **5.5% to 9.6%**. The two are not
interchangeable; quote the improvement.

✅  **Launch insurance is essentially all of it.** The flat liability
premium lands at a median 0.03% to 0.05% of total cost. Full measurement, and
why the programme search makes insurance matter *more* rather than less, in
[calc v1.20.0](versions.md#calc-v1200).

⚠️  **Every measurement committed BEFORE 2026-09 was taken with both premiums
charged**, the 20-cell campaign included; set `charge_insurance` True to
reproduce one. ✅  The **28-cell campaign is the first that is not**, so no
insurance flag is needed to reproduce it.

🚨  **BUT IT IS NO LONGER TRUE THAT THE MATRIX IS WHAT A CONFIGURE-NOTHING RUN
ANSWERS**, which is what this paragraph said until calc v1.22.0 moved four more
defaults under it. Reproducing a cell of the 28-cell matrix now takes
`sell_surplus_at_discount` False, `model_reliability` True,
`model_learning_curve` True and `apply_wacc_compounding` True -- insurance is
simply the one flag it does NOT take. The sentence is corrected rather than
deleted because "the current matrix needs no flag to reproduce" is exactly the
kind of claim that is true for one release and quietly wrong for the next.

**What is not on this list, and why.** Crew costs are absent because every
mission here is uncrewed, not because they were declined; Module 3 replaced its
legacy `Crew` line with the autonomous-control NRE, which *is* charged. Orbital
refuelling is not here either: that charge is gated because it is **incorrect**
for this module rather than out of scope, and `escape_direct_launch` re-arms it
the day an escape-direct architecture exists. The test for this section is that
the charge would be **right** and is still not asked for.

## Data sources

- **NASA JPL Small-Body Database (SBDB)**: orbital + physical backbone
- **MP3C** (Observatoire de la Côte d'Azur), physical-properties compilation
- **SsODNet ssoBFT** (IMCCE): best-of-literature diameter, albedo, mass, density, rotation, taxonomy for ~1.2M bodies
- **NEOWISE Diameters & Albedos V2.0** (IRSA TAP), IR diameters + albedos for ~150k asteroids
- **yfinance**: live futures prices (metals; fuel-cost proxies)
- **USGS Mineral Commodity Summaries + LME**: reference prices for metals yfinance doesn't expose
- **metals.dev**: optional; set `MINERAL_CONFIG.metals_api_key` (defaults to `"DEMO"`, i.e. skipped)

🔔  **[`CITATIONS.md`](CITATIONS.md) is the authority for how to cite these**,
and two of them ask for citation as a **condition of use** rather than as a
courtesy: SsODNet (Berthier et al. 2023) and NEOWISE V2.0 (Mainzer et al. 2019,
doi:10.26033/18S3-2Z54). If a figure from this pipeline is published, those
travel with it. The list above says what each source supplies; it deliberately
does not restate the citations.

### Source outages change the population, not just the coverage

Sources fail soft by design, an unreachable host returns empty and the run
continues. What that hides is that **the number of asteroids evaluated, and
their taxonomy mix, can change by an order of magnitude between runs.**

Where a spectral type cannot be sourced, Stage 1 infers a coarse one from
geometric albedo and records that in `spectral_type_source`
(`source` / `tholen` / `albedo` / `albedo_assumed` / `unknown`).

This is not hypothetical: **two sources have been silently contributing
nothing, each for several releases.** SsODNet was downloaded in full (~500 MB)
and discarded at merge time on every run until catalog v1.0.9, which is why
measured taxonomy jumped from 1,854 bodies to **24,675** when it was fixed;
NEOWISE matched zero rows until catalog v1.1.0 because a float-typed
identifier stringified to `"3.0"` instead of `"3"`. Both printed a successful
fetch throughout. The mechanisms, and the three separate things that kept the
SsODNet one quiet, are in
[CLAUDE.md](CLAUDE.md#the-ssodnet-outage-that-wasnt-an-outage-fixed-in-v109);
what each was worth is in
[versions.md](versions.md#catalog-v110--calc-v1130).

⚠️  **Every figure committed before catalog v1.0.9 was measured on that
degraded catalog**, which is why the oldest of them quote "across 1,959
asteroids".

**So check `spectral_type_source` before comparing a run against a committed
number.** The run banner reporting a source as "Active" only means it was
*enabled*, not that it returned anything; read the `Source summary: {...}`
dict and the `Spectral type inferred from albedo for N entries` line instead.

And note what `Source summary` does **not** tell you: it counts rows *fetched*,
which is exactly the number NEOWISE reported on the runs where it contributed
nothing. Since v1.1.0 the merge also prints how many of each supplement's keys
**matched the backbone**, and shouts when that is zero. The equivalent check on
a CSV you did not watch being built is one line, a `source_*` column at zero
whose fetcher reported success is the signature:

```bash
py -c "import pandas as pd; d=pd.read_csv('asteroid_pipeline/asteroid_catalog.csv',low_memory=False); print({c:int(d[c].notna().sum()) for c in d.columns if c.startswith('source_')})"
```

### Diameters, and the 9% problem

Stage 1 drops any body without a diameter, and that single rule set the size of
this catalog for its whole history. Of JPL's **1,554,321** asteroids only
**139,582 have a measured diameter**: 9.0%. Across every source the union is
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
sizes in the source. The spectral-type table covers 28 classes with n >= 5
(S 0.2439 at n = 534, C 0.0540 at n = 195, V 0.3880 at n = 36); the orbital
gradient is strong enough to be worth binning for, 0.2885 at 1.3-2.0 AU
against 0.0660 in the outer belt.

⚠️  **The orbital table is what actually sizes the catalog, not the taxonomy
one.** A body with a taxonomy almost always has a diameter too, so the taxonomy
branch fires on 105,905 rows against the orbital gradient's 1,298,885.
⚠️  The derived albedo also sets the **composition**, deliberately: assuming
p_V = 0.066 for an outer-belt body *is* assuming it is carbonaceous, so the
assumed albedo is read as the last spectral-type fallback. Without that, 1.4 M
derived bodies would land on an `Unknown` composition with `None` fractions and
get no mass at all. Note the direction: **one assumption produces two outputs.**
Inferring the class first and reading an albedo back off it would launder one
guess into two apparently independent columns, and *that* would be circular.

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
  derived bodies exceed 100 km and the largest is 1,219 km; real TNOs whose
  sizes are overstated. That is 1.09% of the catalog, and they fail Stage 4 on
  Δv regardless.

Set `derive_diameter_from_h = False` for a measured-only catalog of ~149,600.

## History

Pre-git module copies, the original Colab notebook, and the parallel-repo
divergence that made `1.0.6` / `1.1.4` / `1.3.6` each mean two different things:
[Repository history](versions.md#repository-history).
