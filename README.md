# economicspace: Asteroid Mining Profitability Pipeline

End-to-end pipeline that estimates, for every asteroid it can pull data on, the
net profit of an **uncrewed autonomous mining and sample-return mission**.

It chains four stages: build an asteroid catalog from public astronomy
databases → price the minerals those asteroids contain → cost the
transportation → run the rocket-equation and cost cascade to produce a ranked
profitability table.

## Contents

What the pipeline is, how to run and verify it, and the current numbers. What
the model does with a kilogram, and what it charges for, declines and cannot
capture, is in [MODEL.md](MODEL.md); the release history is in
[versions.md](versions.md); the editing traps are in [CLAUDE.md](CLAUDE.md).

- [Start here](#start-here)
- [Layout](#layout)
- [Running it](#running-it)
- [Verifying a change](#verifying-a-change)
- [Working copy](#working-copy)
- [Output](#output)
- [Results](#results)
- [Version history](#version-history)
- [Data sources](#data-sources)
- [History](#history)
- [License](#license)

## Start here

**Double-click `_START HERE.vbs`.** That is the whole answer on Windows: it
opens the dashboard in your browser with no terminal window, and the small
control panel it puts up is what you close when you are done.

| you are on | open this | what you get |
|---|---|---|
| **Windows, no terminal** | **`_START HERE.vbs`** (double-click) | the dashboard, and nothing else to think about |
| Windows, a terminal | `run.bat` | a menu over the dashboard, the headless runs and verification |
| Linux or macOS | `./run.sh` | the same menu, POSIX |
| any host, scripted | `py run_pipeline.py --preset quick` | one headless run, no menu |

⚠️  **`master.py` is not the entry point**, though its name makes it look like
one. It is the import surface the four launchers above drive: it imports the
four stage modules and runs nothing when imported. If you opened it looking for
the start button, close it and double-click `_START HERE.vbs`.

The dashboard opens ready to re-run Stage 4 against the catalogs already on
disk, which is the loop you want almost every time; press **Quick sample** in
the sidebar for a run that finishes in minutes. The long version of all of this
is [Running it](#running-it), and the dashboard itself carries the same three
steps behind a **Start here** panel at the top of the page.

## Layout

```
_START HERE.vbs        Double-click this: opens the dashboard, no terminal
launch_ui.py           What it runs -- hands ui.py to quietlaunch, which owns the stop button
run.bat                Windows launcher: a terminal menu over everything below
run.sh                 Linux / macOS launcher: the same options, POSIX
run_pipeline.py        Headless CLI the launcher drives (presets + flags)
verify.py              Release verification: the checks every change runs
verify_stage1.py       Stage 1 verification: the pinned catalog release, installed
verify_docs.py         Docs verification: the docs still describe the code
tree_check.py          Does the disk hold what git says it holds? ~0.4 s
platform_check.py      Can THIS host reproduce the committed numbers? ~10 s
requirements-verify.txt  The pinned samebytes those two (and verify.py's run
                       comparison, and four docs checks) are shims over;
                       installed on first use
.github/workflows/     CI: the checks that need no catalog, run on every push
platform_reference.json  What it compares against, recorded on the ref host
requirements-lock.txt  The exact versions every committed number was measured on
Dockerfile             Container image for a second host. No CUDA layer, on purpose
SPARK_SETUP.md         Standing this up on a DGX Spark (aarch64 Linux)
master.py              Import surface: the four modules, their configs, the orchestrator
ui.py                  Streamlit front end (optional): configure, run, inspect
ui_meta.py             Config introspection + curation for ui.py
orbital.py             Elements to state vectors, numpy only; ui.py's orbit
                       diagram draws with it
modules/               A package: master.py imports it
    __init__.py        Imports no stage, so a Stage 4 worker loads calc alone
    _runtime.py        What every stage does first: console encoding, worker
                       quiet mode, output directory, installs, overwrite guard
    _release.py        Download and checksum a published release (Stages 1, 2)
    catalog.py         Stage 1 - asteroid catalog
    mineral_value.py   Stage 2 - installs a published spacevalue price release
    transportation.py  Stage 3 - ADAPTER over the spacecost package
    calc.py            Stage 4 - profitability calculation
campaign/              The 28-cell measurement campaign: results.csv, the
                       archived cells, FINDINGS.md, and the scripts that ran it
                       (its job runner is quietqueue, pinned in
                       requirements-campaign.txt)
README.md              This file: what it is, how to run it, current numbers
MODEL.md               What the model does, charges for, declines and cannot capture
versions.md            What changed in which release, what numbers used to be,
                       and the per-module changelogs
CITATIONS.md           Every source, dataset and borrowed line, and what each
                       obliges. Two of them require citation as a condition of use
CLAUDE.md              Working notes: the traps and invariants. Read before editing
LESSONS.md             The long form behind each CLAUDE.md rule, frozen 2026-10-17
```

Each document is the authority for one thing:

| file | holds | is the authority for |
|---|---|---|
| `README.md` | what the pipeline is, how to run and verify it, and the **current** numbers | the current answer |
| [`MODEL.md`](MODEL.md) | what the model does with a kilogram: the mission, the prices, the propulsion tables, beneficiation, programme scale, and what it charges for, declines and cannot capture | what a run means |
| [`versions.md`](versions.md) | what changed in which release, what every number used to be, and the per-module changelogs | the measurement history |
| [`CITATIONS.md`](CITATIONS.md) | where every source, dataset and borrowed line came from, and what each obliges | references and attribution |
| [`CLAUDE.md`](CLAUDE.md) | the traps, the invariants, and the decisions that look wrong, one rule at a time | how to edit it safely |
| [`LESSONS.md`](LESSONS.md) | how each of those rules was learned, word for word as of 2026-10-17, and maintained as current about nothing | why a rule exists |
| the [`spacecost`](https://github.com/loggger101/spacecost) repo | Stage 3's reference tables, their citations, their release history, the recorded fuel quotes, and the delivery chains Stage 2's prices are built on | every launch, propellant, delta-v, operational and storage row, and what a kilogram costs to deliver or return |
| the [`spacevalue`](https://github.com/loggger101/spacevalue) repo | Stage 2's pricing: the mineral reference table, the destinations, in-space utility and demand, the recorded metal quotes, and the published price releases | what a kilogram of each commodity is worth at each destination, and why |
| the [`General_Research`](https://github.com/loggger101/General_Research) repo | the peer-reviewed and tiered-authoritative sources behind the model's weakest-sourced cells, with one extracted-data CSV per source | what backs a number, and how strongly |

### Stage 3's tables live in another repository

**[`spacecost`](https://github.com/loggger101/spacecost)** holds every Stage 3
reference row: the 76 launch vehicles, the 41 propellants with their storage
classes and derived tankage, the Δv segments, the operational costs and the
storage systems, each with its inline citation. `modules/transportation.py` is
now a thin adapter that drives it, where two thirds of what it used to hold
was reference data.

**It holds the delivery chains too, as of its `v0.3.0`, and those are what
Stage 2's prices are built on.** `delivered_cost_usd_per_kg` and
`downleg_cost_usd_per_kg` live in `spacecost.delivery`, which the Stage 2
package reads at import, so a name dropped there fails Stage 2 first and the
traceback will not mention Stage 3.

**Stage 3 prices fuel from a recorded quote snapshot**, `fuel-2026-10-17`
(`TransportConfig.quote_snapshot`), so re-running it rebuilds the same tables,
byte for byte and offline. It fetched live fuel prices until master v1.59.0,
which is why `campaign/stage3/spacecost-<ver>/` holds hand-frozen copies; they
stay as the record of the cells that read them.

🚨  **A repin can move values, and the data on disk adopts one
deliberately.** `pipeline_version` is spacecost's data contract, inherited with
its config, so a repin moves the Stage 3 stamp whether or not a value moved.
When values move, Stage 3 is re-run at the new pin. What each repin moved is
in its release note in [versions.md](versions.md); the first to move values
was [master v1.35.0](versions.md#master-v1350--mineral_value-v1100--transportation-v1160).

⚠️  **The seam is arranged so drift cannot be committed**, because a split is
what caused this project's worst recorded incident
([the parallel-repo divergence](versions.md#the-parallel-repo-divergence)):
the data and the config are single-sourced (Stage 3's config is spacecost's
`SpacecostConfig` with two defaults overridden), and the package that imports
is held to the pinned tag at import. The invariants are in
[CLAUDE.md](CLAUDE.md#stages-1-2-and-3-live-in-other-repositories).

**spacecost is pinned to a tagged release**, `v0.14.0`, in all five places
that type it: as a URL in `requirements.txt`, and in `PIP_SPEC` in
`modules/_runtime.py` (what Stage 3 installs from at import); and in prose
here, in [CLAUDE.md](CLAUDE.md) and in [CITATIONS.md](CITATIONS.md).

### Stage 1 downloads the catalog; it does not build it

`modules/catalog.py` builds nothing. The four survey fetchers, the cross-match,
the diameter derivation, the validator and the Bus-DeMeo composition table are
in [`asteroid_catalog`](https://github.com/loggger101/AsteroidCatalog), and that
repository **publishes** its builds: each `data-YYYY-MM-DD`
[release](https://github.com/loggger101/AsteroidCatalog/releases) is one
frozen catalog, gated before it is published (every source must have
contributed, the stamps must be current, and it must not have shrunk) and
checksummed.

Stage 1 installs **one pinned release**. The pinned catalog release is `data-2026-10-21b` (data contract 1.10.0),
set by `CatalogConfig.catalog_release` in `modules/catalog.py`. Stage 1
downloads the release's manifest, refuses it unless it is this pipeline's data
contract (`CatalogConfig.pipeline_version`), downloads the gzipped catalog and
the composition tables, checks every byte against the manifest's sha256s, and
only then replaces what is on disk. With the pinned release already installed
it downloads nothing.

**Why.** A build cannot be repeated: JPL adds bodies daily, so the catalog a
build returns today is a different length from last week's and comparable with
nothing already measured. While Stage 1 built its own, re-running it replaced
the 862 MB input every committed number was measured on, with no way back. A
pinned release is the same bytes on every host, so a fresh clone gets the
catalog the numbers were measured on, and re-running Stage 1 is harmless.

**Moving to a newer catalog is a deliberate repin**: change `catalog_release`,
run Stage 1, and record it in [versions.md](versions.md). It moves every number
downstream, exactly as a rebuild did. Publishing a new catalog is done in the
AsteroidCatalog repository (Actions > publish catalog > Run workflow).

```bash
py verify_stage1.py
```

### Stage 2 installs published prices; it does not price

`modules/mineral_value.py` prices nothing. The reference table, the eight
destinations, the in-space utility factors and demand ceilings, and the
recorded metal quotes are in [`spacevalue`](https://github.com/loggger101/spacevalue),
split out of this module with its history at master v1.59.0, and that
repository **publishes** price releases: each `prices-YYYY-MM-DD`
[release](https://github.com/loggger101/spacevalue/releases) is every
destination's table built from one recorded quote snapshot, gated before it is
published and checksummed.

Stage 2 installs **one pinned release**. The pinned price release is `prices-2026-10-07`,
set by `MineralValueConfig.price_release` in `modules/mineral_value.py`.
Every current measurement was taken on tables priced from its five COMEX and
NYMEX closes, so pinning it moved no number. Stage 2 downloads the
release's manifest, refuses it unless it is this pipeline's data contract
(`MineralValueConfig.pipeline_version`), downloads all eight tables, checks
every byte against the manifest, caches them under
`asteroid_pipeline/mineral_value/<tag>/`, and installs the one for
`delivery_destination`. With the release cached it downloads nothing, so a
destination change needs no network.

**Why.** A live price cannot be fetched twice. While Stage 2 fetched its own,
re-running it replaced the only copy of the prices every baseline and archived
cell was measured on, and `campaign/stage2/` filled with hand-frozen copies,
which stay as the record of the campaigns that read them.

**Changing a price is a release, then a repin.** A new snapshot, a utility
factor or a reference price is a spacevalue change and a new `prices-*`
release; this repository then moves `price_release` and records it in
[versions.md](versions.md). It moves every number downstream.

**spacevalue is pinned to a tagged release**, `v0.2.0`, in all five places
that type it: as a URL in `requirements.txt`, and in `PIP_SPEC` in
`modules/_runtime.py` (what Stages 2 and 4 install at import: Stage 2 for the
names it re-exports, Stage 4 for `spacevalue.cargo`, the cargo valuation that
moved there at calc 1.33.0); and in prose here, in [CLAUDE.md](CLAUDE.md) and in
[CITATIONS.md](CITATIONS.md).

`run.bat`, `run_pipeline.py`, `ui.py` and `ui_meta.py` sit at the root rather
than in `modules/` on purpose: that package holds the four stages and nothing
else, and all four are consumers of `master.py`, not stages of it.

Each module is a standalone file: run it directly to build just that stage, or
import it for its functions without triggering a run. They share no Python
imports, stages hand off through CSVs on disk, not through each other's
namespaces (see [Stage dependencies](#stage-dependencies)).

| Stage | Module | Version | What it does |
|-------|--------|---------|--------------|
| 1 | `modules/catalog.py` | 1.10.0 | Installs the pinned, published [`asteroid_catalog`](https://github.com/loggger101/AsteroidCatalog) release: JPL SBDB + MP3C + SsODNet ssoBFT + NEOWISE, every body re-keyed onto JPL's designation, merged, validated, enriched with per-spectral-type composition and, since 1.7.0, the mineral phases it is made of (since 1.8.0 with the alloy and the sulfides resolved). Downloads rather than builds since master v1.34.0; the version is the catalog's data contract |
| 2 | `modules/mineral_value.py` | 1.17.0 | Installs the pinned, published [`spacevalue`](https://github.com/loggger101/spacevalue) price release: for the destination, every commodity priced from recorded COMEX and NYMEX closes and dated USGS/LME/LBMA reference prices, with in-space utility, demand ceilings and per-destination discounts. Downloads rather than prices since master v1.59.0; the version is spacevalue's data contract |
| 3 | `modules/transportation.py` | 1.23.6 | Drives [**spacecost**](https://github.com/loggger101/spacecost): launch vehicles (incl. non-rocket concepts), propellants with storage class and tankage, Δv segments (incl. the delivery ladder above LEO), operational costs, storage systems, and since v1.15.0 the `environments` table Stage 4 does not yet read. The row counts are under [The propulsion and storage catalog](MODEL.md#the-propulsion-and-storage-catalog) |
| 4 | `modules/calc.py` | 1.33.0 | Per-asteroid Δv **and mission architecture**, and, by default since 1.17.0, **programme size, fleet size and schedule**, in-space delivery, beneficiation, rocket-equation mass cascade (incl. tankage) + cost cascade → net profit, ROI, $/kg-returned |

The version column is held to each module's `pipeline_version` by
`verify_docs.py` check 2, and the dataclass field is the authority. **What
each version changed is in [`versions.md`](versions.md)**, newest first. A
bump does **not** mean a number moved; the stamps that moved alone are tabled
under [how the version numbers work](versions.md#how-the-version-numbers-work).

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
build from pinned inputs and give the same files on every run, but each writes
over what is on disk, and a destination change or a repin replaces what a
baseline was measured on. So a cached stage starts unticked and the
destination selector is preselected to whatever the catalog on disk is already
priced for. Tick a stage and it tells you what that will overwrite. This is the loop you want almost every
time: the catalogs are expensive to rebuild and Stage 4 is the stage whose
answer you are actually changing.

Why a `.vbs` and not a `.bat`: cmd creates its window before the first line of
a batch file runs, and a shortcut set to "Minimized" still puts one on the
taskbar. Windows Script Host is the only launcher that can start a process with
no window at all. It decides nothing itself -- which port, whether a
dashboard is already up, what to do when Streamlit is missing, all of that
lives in [quietlaunch](https://github.com/loggger101/quietlaunch), where it
is tested. `launch_ui.py` installs the version `requirements-ui.txt` pins
(on first use, or when the pin moves) and tells it which app to run.

### On Linux or macOS, from a terminal: `run.sh`

The POSIX counterpart of `run.bat`, with the same options and the same
semantics, so `./run.sh quick leo` does what `run.bat quick leo` does:

```
./run.sh setup     create .venv and install the pinned requirements
./run.sh platform  can this host reproduce the committed numbers (~10 s)
./run.sh inputs    are the CSVs Stage 4 reads on disk (fetches nothing)
./run.sh quick     400-row sample, all four stages
./run.sh rerun     Stage 4 only, against the catalogs already on disk
./run.sh standard  20,000-row sample, Stage 4 only
./run.sh full      THE PIPELINE DEFAULTS (3.2 h at cislunar, 6.1 h at earth_surface)
./run.sh verify    verify_stage1.py, then verify.py against the newest baseline
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
host and has to be measured instead, and the gigabytes of input CSVs that git
does not carry.

### On Windows, from a terminal: `run.bat`

`run.bat` is the whole pipeline behind a menu -- the same dashboard, plus the
headless runs and verification. It finds Python, offers to install
anything missing, and dispatches. It takes an argument if you would rather skip
the menu:

```
run.bat ui         open the dashboard (hands off to _START HERE.vbs, then
                   closes this window -- no terminal stays up)
run.bat quick      400-row sample, all four stages
run.bat rerun      Stage 4 only, against the catalogs already on disk
run.bat standard   20,000-row sample, Stage 4 only
run.bat full       THE PIPELINE DEFAULTS (3.2 h at cislunar, 6.1 h at earth_surface)
run.bat verify     verify_stage1.py, then verify.py against the baseline
run.bat help       run_pipeline.py --help
```

It is a launcher and nothing else. Four of its options go through
`run_pipeline.py` and one through the dashboard, and from there through
`master.py`; `verify` calls `verify.py`.
No model behaviour lives in it, and it adds no default the pipeline does not
already have, except that `quick` and `standard` cap rows and fly raw ore at
N = 1 rather than starting the multi-hour default cell on a double-click.

**Stages 1-3 overwrite, so they ask first.** Each replaces its CSV on disk,
and every `verify.py` baseline is built against those exact bytes. The pinned
inputs make a re-run give the same bytes back, but a different destination or
a repin does not. `run_pipeline.py` names what a run would overwrite and waits
for a `yes`, unless the file does not exist yet (nothing to lose) or you pass
`--yes`. `run.bat` passes `--yes` on any
invocation carrying an argument, so a scripted or scheduled `run.bat quick`
still runs unattended; the menu asks.

⚠️  **The presets exist because the pipeline's own defaults are a long run**:
a configure-nothing run is the full catalog, beneficiated, with the programme
search on, at `earth_surface` (the wall clocks are tabled under
[What a first run costs](#what-a-first-run-costs)). That is the right default for the model and
a hostile one for a double-click, so `quick` and `standard` cap the rows and
fly run-of-mine ore at N = 1. The row cap is a **stride sample across the
whole belt**, not the innermost N bodies.

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

**calc v1.22.0's four default flips each have a flag**, applied after the
preset. Together they put a run back on v1.21.2's model, and this reproduces
the committed v1.21.2 sample cell exactly, **25.7233x on 155 evaluable rows,
2017 KJ5**:

```bash
py run_pipeline.py --stages 4 --destination cislunar --raw --no-search \
    --no-surplus-sales --reliability --learning-curve --cost-of-capital
```

`--no-surplus-sales` restores the hard wall at a market ceiling
(`--surplus-fraction F` sets what the surplus fetches otherwise, 0.0 to 1.0,
refused outside it), `--reliability` the `P(launch) x P(cruise) x P(mining)`
discount on revenue, `--learning-curve` Wright's law on recurring hardware, and
`--cost-of-capital` WACC compounding and with it the programme calendar
charge, which is time-value and inert without a rate. Reproducing the 28-cell
matrix takes all four. Figures from before v1.21.0 do not reproduce exactly on
any flags: use a build of that release, which is what the `pipeline_version`
stamp on every CSV is for.

`--stages` takes digits, so `--stages 4` reuses the CSVs already on disk for
the other three: the normal working loop, and the one that cannot overwrite a
fetched input.

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

Run all four stages in order:

```bash
python master.py
```

Or run a single stage:

```bash
python modules/transportation.py
```

Each module installs whatever it is missing from its own `_REQUIRED_PKGS` when
it is imported (through `modules/_runtime.py`), so either form works on a fresh
interpreter.

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
  Stage 4 alone against a cached catalog is the normal working loop. Pair it
  with `eval_row_cap`: an uncapped Stage 4 is hours, and a capped one is a
  stride sample of the whole belt. Skipping Stage 2 after changing the
  destination is blocked rather than merely warned about, because a mineral
  catalog priced for one destination and a mission flown to another produces
  meaningless numbers that still look plausible.
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
  [starred-repos](https://github.com/loggger101/starred-repos/blob/main/SPACE-MAP.md) measured and
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

> ⚠️  **The catalog is ~1.57 M asteroids**, and a default end-to-end run is
> not a coffee break; budget an afternoon, and cap Stage 4's rows for anything
> interactive.

- **Stage 1** downloads the pinned catalog release once: a **~320 MB** gzip
  that decompresses to a **~2.4 GB** CSV (the `data-2026-10-21b` release:
  1,575,889 bodies, 102 columns; the `comp_phases` column added at 1.7.0 is
  ~320 MB of it and `comp_phases_detailed`, added at 1.8.0, ~430 MB),
  checksummed before it replaces anything. Installing it on
  2026-10-21 took **1 min 11 s** end to end.
  A re-run at the same pin downloads nothing and takes ~30 s, the checksum and
  the CSV read.
- **Stage 4 is the long pole by far**, because `eval_row_cap` defaults to `0`
  (evaluate everything), "everything" is 1.55 M rows, and both beneficiation
  and the programme search are on by default. The twenty-eight measured cells
  are tabulated below: at cislunar the default cell is **2.7 h**, and the other six
  destinations span **0.73-2.95×** that, `lunar_surface` being the one that
  runs FASTER rather than slower. Set `eval_row_cap` for anything
  interactive: as of calc v1.13.0 a capped run is an evenly-spaced sample of
  the whole belt rather than the innermost N bodies, so it is actually
  representative.

  ⚠️  **Those wall clocks, and the run banners derived from them, predate
  spacecost `v0.4.0`'s 48-vehicle grid** (1,008 vehicle x propellant
  combinations per asteroid against 357). Measured whole on it, the default
  cislunar cell took **16,862 s on `v0.4.0`** (2026-09-24) and **12,062 s on
  master v1.40.0** (2026-09-30), so budget a default cislunar run at
  **3.5-5 h**. See
  [the v1.40.0 default cell](versions.md#the-full-catalog-default-cell-at-this-release-2026-09-30),
  and never budget from a slice of one run
  ([the sampling rule](CLAUDE.md#reading-a-result-without-fooling-yourself)).
- **The catalog's size is not a dial here any more.** Which bodies exist, which
  surveys contributed and whether diameters are derived from H are decided
  when a catalog release is built, in the AsteroidCatalog repository. To study
  a subset -- measured diameters only, km-class bodies -- filter the catalog
  (`derived_diameter_is_estimate`, `diameter_km`) rather than rebuilding it.

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

⚠️  **A wall clock is true only of the release and catalog it names.**
Performance-only releases between v1.16.0 and v1.17.7 were worth **1.78x to
4.32x**, and v1.21.0's capacity ceilings cost **1.29x to 2.31x** back; the
per-release figures are in [`versions.md`](versions.md#runtime-history).
`prune_infeasible_combos` (on by default, the Common tab's **Hopeless
candidates**) refuses a candidate whose answer is already decided and
approximates nothing; turning it off restores the pre-v1.14.1 search, and an
unpruned full cell is very slow.

🚨 **Do not budget any of this from a sample.** A stride sample has mispredicted
full-catalog runtime here by **3.1x high** and **4.8x low**, and a ratio between
two settings by **2.7x**, for opposite reasons: fixed costs dominate a small
run, while a stride sample under-represents the expensive tail of the
concentration sweep. Budget from a measured full run of the same cell, or do
not budget.

### Output location

Defaults to `./asteroid_pipeline` under the working directory. Override with
an environment variable, set before any module is imported:

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
| `MASTER_CONFIG.delivery_destination` | `"earth_surface"` | **Read [Where the material is sold](MODEL.md#where-the-material-is-sold) before changing.** Sets every price *and* the mission architecture. One of `earth_surface`, `leo`, `gto`, `geo`, `cislunar`, `lunar_surface`, `mars_orbit`, `mars_surface`. Writes Stage 2 and Stage 4 together, never set the two sub-configs separately |
| `.calc.use_beneficiation` | `True` | Return concentrate instead of run-of-mine ore. Charges the extra dig time, processing energy and solar-array mass. **Default since calc v1.17.0**; almost every historical table is `False`. See [Beneficiation](MODEL.md#beneficiation) |
| `.calc.beneficiation_recovery` | `0.90` | Fraction of the valuable phase reporting to concentrate |
| `.calc.max_concentration_ratio` | `50.0` | Safety cap on feed:concentrate. The purity bound normally binds first |
| `.calc.use_per_asteroid_dv` | `True` | Δv from each asteroid's own orbital elements. `False` gives every asteroid the same Δv |
| `.calc.mining_rate_kg_per_day_per_kg_rig` | `0.10` | Extraction throughput per kg of rig; caps payload and sets time at the asteroid |
| `.calc.max_mining_duration_yr` | `3.0` | Ceiling on time at the asteroid, binds how much you can return |
| `.calc.nre_recurring_overlap_fraction` | `0.30` | Development share already inside the per-kg recurring rate; `0.0` books both in full |
| `.catalog.catalog_release` | `"data-2026-10-21b"` | Which published catalog build Stage 1 installs. Changing it replaces the catalog every stage reads and moves every result; record a repin in versions.md. See [Stage 1 downloads the catalog](#stage-1-downloads-the-catalog-it-does-not-build-it) |
| `.calc.eval_row_cap` | `0` | Stage-4 evaluation cap; `0` evaluates every row. |
| `.calc.eval_row_sampling` | `"stride"` | How a cap picks rows. `"stride"` samples the whole belt evenly; `"head"` is the pre-v1.13.0 innermost-N behaviour |
| `.calc.parallel_workers` | `0` | Stage-4 worker processes. `0` picks a count from the CPU count and the amount of work; `1` forces the single-core path. See [Parallel evaluation](#parallel-evaluation) |
| `.calc.max_mining_fraction` | `1.0` | Share of asteroid mass one mission may remove. `1.0` puts the whole body on the table and leaves the dig rate, the capsule volume and the rocket equation to bound the haul |
| `.calc.use_aerocapture_return` | `True` | Makes aerocapture *available*. Trades return Δv for a TPS mass penalty (15% of payload); Stage 4 prices both and flies whichever pays, per asteroid |
| `.calc.use_isru_return_propellant` | `True` | Makes ISRU *available* at bodies whose composition supplies the propellant, with the extra rock dug, timed and charged |
| `.calc.model_isru_processing` | `True` | Charge the energy and the plant that turn the feed into propellant: Stage 3's `isru_processing_wh_per_kg` (hydrolox 15,200 Wh/kg, electrolysis and liquefaction) goes through the array, and the plant (Stage 3's "ISRU propellant plant throughput") rides with the rig at the rig's rate. **Default since calc v1.32.0**; `False` is the earlier model to the bit. See [What the model charges for](MODEL.md#what-the-model-charges-for) |
| `.calc.isru_processing_usd_per_kg` | `0.0` | A flat $/kg on propellant made on site. **Retired at calc v1.32.0**: it was an unsourced `50.0` that `model_isru_processing` now charges as energy and plant, and it was billed on water ISRU, which processes nothing. `50.0` with `model_isru_processing = False` reproduces v1.31.0 |
| `.calc.operational_propellants_only` | `True` | Restrict the search to propellants that have flown. `False` admits Stage 3's development and concept rows: nuclear thermal, VASIMR, fusion, Orion pulse |
| `.calc.model_tank_mass` | `True` | Put propellant tankage in the rocket equation. Tank mass scales with volume, so this is what stops low-density propellants flying their tanks for free |
| `.calc.allow_rtg_power` | `True` | Let the processing plant use radioisotope power where it is lighter than solar (past 3.46 AU), capped by `rtg_max_power_w` |
| `.calc.charge_tanker_flights` | `True` | Charge the orbital-refuelling flights a vehicle's escape payload assumes |
| `.calc.model_mineral_phases` | `True` | Sell a body as the MINERALS it is made of (Stage 1's `comp_phases`) rather than as four coarse fractions: each phase at the better of its own price and the value of its elements. **Default since calc v1.24.0**; `False` is the earlier model to the bit. See [What the rock is made of](MODEL.md#what-the-rock-is-made-of) |
| `.calc.model_refinery` | `True` | Fly the refinery (its energy through the array, its plant with the rig) and value every phase before Stage 2's refining deduction, instead of taking an estimated plant out of the price. **Default since calc v1.25.0**; `False` is the earlier model to the bit. See [What the rock is made of](MODEL.md#what-the-rock-is-made-of) |
| `.calc.model_detailed_phases` | `True` | Read Stage 1's `comp_phases_detailed` rather than `comp_phases`: the metal as the kamacite, taenite, tetrataenite and cohenite a class holds, the sulfide by species (pyrrhotite, pentlandite, niningerite, oldhamite, daubreelite), and the phosphates and CAI oxides named. **Default since calc v1.26.0**; `False` is the earlier model to the bit. See [What the rock is made of](MODEL.md#what-the-rock-is-made-of) |
| `.calc.charge_insurance` | `False` | Charge Module 3's two insurance premiums: a $1.5M third-party liability flat and launch insurance at 10% of (launch + spacecraft book value). **Off since calc v1.20.0** because a premium is priced off an underwriter's book rather than off a mass; every table measured before it is a `True` run. See [What the model deliberately does not charge for](MODEL.md#what-the-model-deliberately-does-not-charge-for) |
| `.calc.optimise_architecture_per_asteroid` | `True` | Search return mode and propellant sourcing per target rather than fixing them catalog-wide |
| `.calc.selection_objective` | `"cost_revenue_ratio"` | What the per-asteroid search maximises. `"profit"` restores pre-v1.10.0 behaviour |
| `.calc.return_structure_frac_of_payload` | `0.15` | Return-vehicle structure as a fraction of the haul, on top of the 500 kg base |
| `.calc.nre_amortization_missions` | `1` | Programme size N. With the search on it is the FLOOR rather than the answer |
| `.calc.optimise_programme_scale` | `True` | Search programme size and fleet size per asteroid instead of setting N. **Default since calc v1.17.0.** It changes the question the run answers, so most historical tables are `False`, at N = 1. See [Programme scale](MODEL.md#programme-scale) |
| `.calc.market_model` | `"capacity_cap"` | What a delivered kilogram sells for and how much of it clears. `"capacity_cap"` holds price constant and clips quantity at Stage 2's `annual_market_kg`; `"single_mission"` pins N = 1; `"elasticity"` is the v1.14.0 demand curve; `"unbounded"` is a diagnostic. **Default since calc v1.21.0**, replacing the `model_market_saturation` flag. See [The market model](MODEL.md#what-the-model-charges-for) |
| `.calc.demand_elasticity` | `0.5` | The e in `(1 + Q/Q_market)^(-1/e)`. Read ONLY when `market_model` is `"elasticity"` |
| `.calc.sell_surplus_at_discount` | `True` | Sell what is past a market ceiling at a discount instead of abandoning it. **Default since calc v1.22.0**; `False` is v1.21.0's hard wall, which is what the 2026-09 campaign measured. Ceilings still bound the programme, because the marginal kilogram past one is worth strictly less than the one before it. See [The market model](MODEL.md#what-the-model-charges-for) |
| `.calc.surplus_price_fraction` | `0.5` | What a kilogram past a ceiling fetches, as a fraction of the full price. Read ONLY when `sell_surplus_at_discount` is `True`; `0.0` reproduces the wall |
| `.calc.max_fleet_ships` | `64` | Where the fleet ladder stops. Rows piling up against it mean their payloads have no finite market, not that bigger is better; the run says so |
| `.calc.programme_search_steps` | `8` | Rungs in the coarse fleet sweep, before one refinement pass. Same idiom as `concentration_search_steps` |
| `.calc.model_rig_trip_limit` | `True` | Cap rig life in duty CYCLES as well as calendar years. Inert at N = 1 |
| `.calc.model_programme_calendar` | `True` | Charge the calendar a programme actually spans: the NRE and rig are bought once and carried across every campaign. Inert at N = 1; also what makes the programme search two-dimensional |
| `.calc.contingency_fraction` | `0.20` | Flat contingency on the cost cascade |
| `.calc.apply_wacc_compounding` | `False` | Cost of capital: compound up-front costs over the mission, bucketed by when each is incurred, at Module 3's 10% WACC. **Off since calc v1.22.0** because a discount rate is a statement about whose money this is, which is outside a marginal-cost model; it also silences `model_programme_calendar`, whose multipliers are exactly 1.0 at a zero rate. See [What the model deliberately does not charge for](MODEL.md#what-the-model-deliberately-does-not-charge-for) |
| `.calc.model_reliability` | `False` | Multiply expected revenue by `P(launch) x P(cruise) x P(mining)` while charging every cost in full. **Off since calc v1.22.0**: two of those three are assumptions about a machine nobody has built, and multiplying the answer by them buries them in every headline. A default run now answers what it costs IF IT WORKS |
| `.calc.model_reliability_growth` | `True` | Let `p_mining` grow across a programme under the Duane model rather than sitting at the first-of-kind figure. Inert while `model_reliability` is off |
| `.calc.model_learning_curve` | `False` | Apply Wright's law to recurring hardware across a programme. **Off since calc v1.22.0**: it is a statement about a factory's learning, fitted to programmes that built dozens of articles, and this one prices the marginal physics. Exactly inert at N = 1 either way |
| `.calc.learning_curve_rate` | `0.85` | Wright's-law rate: each doubling of cumulative production cuts unit cost to this. Read ONLY when `model_learning_curve` is `True` |
| `.mineral.price_release` | `"prices-2026-10-07"` | The spacevalue price release Stage 2 installs. A repin moves every price |
| `.transport.quote_snapshot` | `"fuel-2026-10-17"` | The recorded fuel quotes Stage 3 prices from. A repin moves the propellant prices |

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

Since calc v1.32.0 it also states what turning the feed into propellant
costs, and hydrolox pays it: **15.2 kWh per kg** to split the water and
liquefy both gases, on top of the 3.2 kWh/kg of liberating it, and a plant
the size of **one kilogram per 7.28 kg of propellant a year**. Charged, it
wins no sampled row at any destination. The ISRU that wins is water burnt as
it comes. See [What the model charges for](MODEL.md#what-the-model-charges-for).

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

Leave `parallel_workers` at `0` unless you have a reason:

- **`1`** forces the serial path, for profiling, or when an outer harness is
  already running one process per destination and the cores are spoken for.
- **A specific count** is obeyed, clamped to the CPU count.

Auto mode will not start a worker that cannot repay its own startup, so short
interactive runs stay serial. That matters more than it sounds: startup is
**linear** in the worker count, because each worker re-imports `modules.calc`
(Windows has no fork), and on a Google Drive working copy those reads
serialise. The useful ceiling is the **physical** core count, hyperthreading
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
account is in [LESSONS.md](LESSONS.md#entry-points).

## Verifying a change

Almost every release of Stage 4 is argued from **bit-identity**: the claim is
not "the numbers look right", it is "these are the same floats, and here is the
hash". `verify.py` is those checks, committed:

```bash
py verify.py baseline --tag 1.17.7
```

Run that on a clean tree **before** editing. It builds four cells, raw and
beneficiated, each with the programme search off and on, and writes their CSVs
and hashes under `.verify/` (gitignored). Then make the change and:

```bash
py verify.py check --tag 1.17.7
```

which runs every check in this table:

| # | check | catches |
|---|---|---|
| 1 | bit-identity vs the baseline | any change to any number, column by column and by hash |
| 2 | pre-filter on vs off | the pruner and the solver drifting apart; they are two statements of one algebra |
| 3 | serial vs 8 workers | a worker seeing different reference data from its parent |
| 4 | mass ledger | a kilogram in the rocket equation with no price in the ledger |
| 5 | never-worse | a search optimising something other than what it reports |
| 6 | Stage 2 tables | a judgement-table edit that moved a number, or a commodity falling through a silent default |
| 7 | market ceilings | a capacity ceiling that pays rather than costs, and the three market columns swapping meanings: `saturation_multiplier`, `unsold_payload_kg` and v1.22.0's `surplus_payload_kg` |

`py verify.py invariants` runs 4 to 7 and needs no baseline, so it works on any
tree and is the fast way to check an upstream table edit; `--cells` takes a
subset.

🚨  **`check` refuses a baseline taken over a modified model path.** Baseline a
tree that already carries the change and check 1 compares the change against
itself and prints **MATCH** on every cell. `baseline` records its commit and
whether `modules/` or `master.py` differed from HEAD, by
`git diff` and never `git status` (which reports phantom changes on a synced
folder). Pass `--allow-dirty-baseline` only when the edit really was
unrelated. Docs, harnesses and campaign scripts are not model paths. Cells are
built into `.verify/scratch/`, so the live `profitability_catalog.csv` is never
overwritten.

⚠️  A full `check` builds about twenty cells and takes **roughly half an hour**.
Most of that is check 2; turning the pre-filter off is exactly what v1.14.1 and
v1.17.4 exist to avoid, so an unpruned cell runs the entire search. Iterate with

```bash
py verify.py check --skip prune parallel
```

which is ~5 minutes and still catches any change to any number, then run the
full set once before committing. A verification you will not run is worse than
a slow one.

**Add to `verify.py` rather than starting another harness**, and read its
header's list of past harness bugs before writing any comparison of your own:
a broken checker looks exactly like a broken release, which is why the report
prints **both** a hash and a column diff. When the two disagree, the hash is
right and the comparator is at fault.

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

It exists because a synced folder once served an **older copy** of a harness,
which ran, printed fewer checks than it has and said `OK`, with `git status`
clean throughout: git's stat cache trusts size and mtime and never re-reads
content, so the two can disagree while status says nothing. On a plain clone it
can only pass, which is why CI runs it, as the control that it still works.

The check itself, the host probes behind `platform_check.py`, `verify.py`'s
run comparison and `verify_docs.py` checks 4, 5, 6 and 11 live in
[samebytes](https://github.com/loggger101/samebytes),
split out of this repo with their history; the two files here are shims bound
to this repository. The pin is the one line in `requirements-verify.txt`, and
`modules/_runtime.py` installs that tag on first use and refuses an editable
or shadowing copy, exactly as it does spacecost.

### Verifying Stage 3

spacecost's own CI holds its tables to the CSVs it commits, its `validate()`
to its bands and its built wheel to the names this repo imports
(`tests/test_consumer_contract.py`). Here, `modules/_runtime.py` refuses any
spacecost but the pinned tag at import: another tag or revision is reinstalled
in place, and an editable checkout, a shadowing copy or an install with no git
record is refused with the command to fix it.

⚠️  **`verify.py` covers Stage 4, and it never re-runs Stages 1-3.** That is
deliberate: a run at a moved pin installs a different catalog, a different
price release or different fuel quotes, any of which moves the inputs
underneath the comparison and invalidates every baseline in the same
session. The consequence is that **a change to an upstream module can pass
every check here and still be wrong**: v1.12.1's propellant-flag fix lives in
Stage 3's `validate()`, which Stage 4 never calls, and had to be checked by
running that function under `-W error::FutureWarning` instead. If you change
Stage 1, 2 or 3, this file is not your evidence.

spacecost's suite covers that case now, a synthetic propellant row with no
`propellantless` flag under `-W error::FutureWarning`, and Stage 1's builder is
tested in AsteroidCatalog: each where the code is.

### What runs automatically

Everything above is a command somebody has to remember. Since 2026-09-15 the
subset that needs no catalog runs on every push and pull request, in
`.github/workflows/verify.yml`:

| step | why it can run there |
|---|---|
| `import master` | imports the four modules and builds the configs, which also holds the installed spacecost to the pinned tag; Stage 1's taxonomy tables are empty without a catalog, which nothing at import reads |
| `verify_docs.py` | reads the docs and the dataclasses; builds no stage |
| `samebytes hooks check` | the `.githooks/` copies are samebytes' packaged hooks, LF and executable |
| `platform_check.py` | **report only, never a gate** |

🚨  **`verify.py` is NOT in CI and cannot be.** `asteroid_pipeline/` is
gitignored in full, so a fresh clone has the code and none of the gigabytes
Stage 4 reads, and `.verify/` is gitignored too, so there is no baseline to compare
against either. Bit-identity stays a local pre-commit discipline. **CI going
green says the docs and the seams are intact; it says nothing whatever about a
number.**

⚠️  **platform_check.py is informational on purpose.** A GitHub runner is glibc
on x86-64 and the reference host is the Windows UCRT, so a differing libm probe
there is the expected answer, not a finding.

### Verifying Stage 1

Stage 1 builds nothing, so what is left to verify here is the seam: that the
pin names a real release at this pipeline's data contract, and that the catalog
on disk is that release, byte for byte. The builder's own traps -- the
designation regex, the float-typed merge key, the distinct-value lookup -- are
executed by the AsteroidCatalog repository's test suite, where the code is.

```bash
py verify_stage1.py
```

It never writes the catalog; installing is Stage 1's job.

| # | check | what it executes |
|---|---|---|
| 1 | release | the pinned release exists, names itself, and is the data contract `CatalogConfig.pipeline_version` says |
| 3 | bytes | the installed catalog and composition tables match the installed manifest's sha256s, and the manifest is the pinned release |
| 4 | stamps | the rows' `pipeline_version`, `catalog_date` and count match the manifest |
| 8 | provenance | the two `*_source` domains are the labels this pipeline's readers know, and the census reproduces |

Check 1 reads only the release's manifest over the network, so it runs on
CI. Checks 3, 4 and 8 read the catalog Stage 1
installed, and say what would make them run when it is absent. A catalog built
before Stage 1 downloaded releases carries no manifest and fails check 3:
nothing says which build it is. The number 8 is the one that check had when
this file verified the builder in place.

⚠️  **Checks 6 and 7 are retired (master v1.36.0).** Both re-tested the build,
which AsteroidCatalog gates before publishing, and check 3 already proves the
bytes on disk are that build. Check 8 stays because it is a question about this
pipeline: the worked calculation and the dashboard both branch on the two
`*_source` labels. Its counts are pinned to the catalog identity they came
from, so a repin is reported rather than failed.

⚠️  **Checks 2 and 5 are retired too (2026-10-25).** They held the release's
composition and PGM tables to their invariants; AsteroidCatalog's
`tests/test_traps.py` holds every one of them, and its release test holds the
shipped `taxonomy.json` to those tables.

### Verifying the docs

`verify.py` proves the model did not change. **`verify_docs.py` proves the docs
still describe it**, in about a second and with no baseline:

```bash
py verify_docs.py
```

| # | check | catches |
|---|---|---|
| 1 | defaults | a documented default that no longer matches its dataclass field |
| 2 | versions | the Stage/Version table or CLAUDE.md's `Current:` line drifting from `pipeline_version`, and versions.md's "moved without moving a number" table drifting from any count of it spelled out in prose |
| 3 | row counts | "40 propellants" after a row was added |
| 4 | links | a markdown link to a file that is not there, or an anchor that does not resolve |
| 5 | structure | unbalanced fences, ragged tables, heading-level jumps, duplicate h1/h2, in every markdown file in the repo |
| 6 | dashes | an em- or en-dash in prose a reader sees, or a line left opening with a bare comma: the docs, the root scripts, the campaign scripts, and comments in `modules/` |
| 7 | manifests | a list documented in one place drifting from the list defined in another: `requirements.txt` against the modules' `_REQUIRED_PKGS`, CLAUDE.md's alias table against `master.py`, the pinned catalog release and spacecost tag against every document that names them, and the `run.bat` and `run.sh` blocks above against their dispatchers |
| 8 | help | a config dial the dashboard renders with no help text, because the UI scrapes its help from the field's own comment |
| 9 | runtime | the twenty-eight-cell wall-clock table under [What a first run costs](#what-a-first-run-costs) drifting from `calc.MEASURED_DEST_SECONDS`; `calc.MEASURED_CELL_SECONDS` against the `campaign/logs/` JSON that measured it; every "N h at &lt;destination&gt;" in `run.bat`, `run.sh` and this file |
| 10 | transfer | a measurement dropped rather than moved during a reorganisation, `--before OLD.md NEW.md ...` |
| 11 | docstrings | a module, class or function in the repo's own Python with no docstring |
| 12 | pairs | one measurement quoted in CLAUDE.md, which quotes none, and in README or MODEL.md |
| 13 | scope | a document disagreeing with `verify.py` about which checks it runs: its docstring list, the check table above, and the sentences that say what `invariants` or `--skip prune parallel` covers |
| 14 | prose | a number typed into a sentence the worked calculation renders, unless it is on the `TYPED_OK` register in `campaign/worked_calculation.py` |
| 15 | guards | a FETCHING stage module that would overwrite its own outputs when run directly: each must gate its build on `_runtime.confirm_overwrite` and exit on a refusal |
| 16 | borrows | the worked calculation touching something in `master` that is on no row of its `BORROWED` register, or a row that matches no call |
| 17 | dest table | the destination table under [What a kilogram is worth](MODEL.md#what-a-kilogram-is-worth) drifting from `master.DELIVERY_DESTINATIONS`, and the launcher menus and calc's `DELIVERY_ARCHITECTURES` offering a different set of destinations |
| 18 | shim | a `master.<name>` the repo's own Python reads that `master.py` cannot resolve, or that two modules define differently |

Every check fails if a file it is supposed to read is not on disk, on a counter
of its own. Checks 6 and 11 are ratchets: check 6 reads `modules/*.py` through
`tokenize` and `ast`, so it sees only comments and docstrings (the `notes` and
`composition` strings are written into the CSVs, so their text is data), and
reads every other file whole. Check 12 reads README, MODEL.md and CLAUDE.md only, and
CLAUDE.md quotes no measurement, so a pair it finds is cut from CLAUDE.md;
`versions.md` and `LESSONS.md` are outside it because every section there
names the release or date it belongs to. Why each check exists is in its
docstring.

⚠️  **It checks that a documented *configuration* matches the code, never that
a documented *measurement* is current.** A stale number passes everything in
it. It reads the docs and the module dataclasses and runs nothing, which is why
it costs a second and works on any tree.

## Working copy

The repository is a normal clone inside a OneDrive-synced folder that a second
machine edits too. A sync client and git both believe they own the files, and
three things follow; the editing rules for each are in
[CLAUDE.md](CLAUDE.md#environment):

- **Phantom-modified files.** The sync client churns stat data, so `git status`
  can report a file modified that `git diff` shows unchanged, and
  `git checkout` or `git merge --ff-only` then abort on changes that do not
  exist. `.githooks/drive-restat.sh` re-stats entries whose content matches the
  index, from `post-checkout`, `post-merge` and `post-rewrite`; a fresh clone
  opts in once (below). Never `git stash`.
- **Conflict copies.** A file edited on both machines comes back as
  `<name>-DESKTOP-PJS73RO.<ext>`. Diff it against history, keep the newer side,
  delete the copy, and never commit one.
- **Evicted `.git/` files.** If git fails with `mmap failed`, OneDrive has made
  part of `.git/` online-only. It is not corruption and it clears once the
  files are back; delete nothing in `.git/`.

```bash
git config core.hooksPath .githooks
```

The hooks are samebytes' copies; `python -m samebytes hooks check .` says
whether they still match the pinned release, and CI runs it.

`.gitattributes` pins `*.py`, `*.md` and the other text sources to LF, because
Git for Windows sets `core.autocrlf=true` in its system config by default and a
rewrite to CRLF would put every line of every source into one diff.

## Output

```
<output_dir>/
    asteroid_catalog.csv               ← Stage 1 (the pinned release)
    rejected_entries.csv               ← Stage 1 (the build's validation rejects)
    catalog_manifest.json              ← Stage 1 (which release is installed)
    catalog_taxonomy.json              ← Stage 1 (the build's composition tables)
    mineral_value_catalog.csv          ← Stage 2 (the destination's table)
    mineral_value_manifest.json        ← Stage 2 (which release and destination)
    mineral_value/<tag>/               ← Stage 2 (the pinned release, all eight)
    transportation/
        launch_vehicles.csv            ← Stage 3
        propellants.csv                ← Stage 3
        delta_v_segments.csv           ← Stage 3
        operational_costs.csv          ← Stage 3
        storage_systems.csv            ← Stage 3
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
authoritative list. The column total is deliberately not written here. Ask the
file: `len(pd.read_csv(path, nrows=1).columns)`.

The ones to look at first:

| Column | Meaning |
|--------|---------|
| `designation`, `name`, `spectral_type`, `comp_group` | Which asteroid, and what it's made of |
| `viable` | `profit_usd > 0`. The headline filter |
| `profit_M$`, `gross_M$`, `cost_M$` | Same numbers as the `_usd` columns, in millions, for reading |
| `roi` | `profit / total_cost` |
| `usd_per_kg_cost` | Mission cost per kg actually returned, the cleanest cross-asteroid comparison |
| `vehicle`, `propellant`, `isp_s` | The winning combination |
| `aerocapture_return`, `isru_return` | The architecture the search chose **for this asteroid** |
| `rendezvous_apsis` | `aphelion`, `perihelion` or `reference`, which apsis the transfer meets the target at, resolved against the destination |
| `isru_propellant_kg`, `isru_feed_kg` | Return propellant made on site, and the rock dug to make it. That feed comes off the throughput and mineable-mass budgets before any ore is loaded |
| `isru_plant_kg`, `isru_processing_power_w` | The plant that makes that propellant, and its draw (calc v1.32.0). The plant is in `hardware_total_kg` and the rig's cost; the draw is in `processing_power_w`. Both 0.0 unless the propellant has to be processed, which is hydrolox |
| `dv_out_m_s`, `dv_ret_m_s` | Per-asteroid Δv from its own orbital elements, including any low-thrust penalty |
| `dv_penalty_factor` | 1.0 for chemical, 1.5 for electric; electric can't fly impulsive burns |
| `max_payload_kg` | Material actually returned, after the mining-fraction, rocket-equation, volume and throughput caps |
| `mining_duration_yr` | Time at the asteroid to dig that payload; floors at `station_keeping_floor_yr` |
| `throughput_cap_kg`, `throughput_fits` | Most the rig could dig in `max_mining_duration_yr`, and whether that bound bit |
| `bulk_value_usd_per_kg` | Stage-2 prices × Stage-1 composition × PGM enrichment |
| `volume_fits` | `False` means the capsule volume cap bound the payload, not the mass budget |
| `m_launch_kg`, `m_outbound_prop_kg`, `m_return_prop_kg`, `m_at_asteroid_kg`, `tps_mass_kg` | The mass cascade |
| `m_dry_return_kg` | Return-vehicle dry mass actually flown, the 500 kg base plus `return_structure_frac_of_payload` of the haul. Compare it to `max_payload_kg`: a ratio far above ~7:1 means something has gone slack |
| `ep_system_kg`, `ep_power_w`, `ep_system_cost_usd` | The electric stage: its mass, its power and its price |
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

## Results

### What a configure-nothing run answers today

**4.8379x, and still zero viable missions.** The default cell (`cislunar`,
concentrate, programme search on) was run over every row of
`data-2026-09-29c` on master v1.40.0 (calc 1.26.0, spacecost `v0.5.0`,
mineral_value 1.12.0) on 2026-09-30, 12 workers, 12,062 s of Stage 4:

| | |
|---|---|
| best case | **2018 DT (M), 4.8379x**: New Glenn on krypton Hall thrusters, one ship flying 3 campaigns of 103,701 kg, concentrated 2.11x |
| next | 2021 CX5 (D) 4.9899x, 2010 CE55 (X) 5.0547x, 2015 DS (X) 5.0585x, 2005 QP87 (X) 5.0936x |
| evaluable bodies | 604,422 of 1,568,878 |
| median body | 20.9073x |

🚨  **THE BEST CASE IMPROVED AND THE MEDIAN BODY GOT WORSE**, against the
last full default cell (5.1275x on spacecost `v0.4.0`, 2026-09-24): the winner
by 5.6%, the median of 603,366 paired bodies by **19.3% the other way**. Taken
apart on a sample, the worsening is almost entirely the **catalog**: its 1.5.0
correction cut S-complex metal to 0.06 and V to 0.01, which costs the median
body a third, and the mineral phases and the refinery give back about an
eighth. 2018 DT's own composition did not change; its hold is worth 29% more
a kilogram sold as minerals. The decomposition, the population and the
invariants are in
[the v1.40.0 default cell](versions.md#the-full-catalog-default-cell-at-this-release-2026-09-30).

#### Every destination at this release: Mars surface is now the best case

The six other destinations' default cells were run on the same inputs on
2026-10-01/03, so the seven together are the current answer to "where is it
best to deliver". `gto`, added at master v1.54.0, has no cell here and has
never been run on the full catalog, so it is not ranked:

| destination | cost / revenue | winner | median body |
|---|---|---|---|
| **`mars_surface`** | **1.0914x** | 2015 DS (X), Falcon Heavy (expendable) on iodine, aerocaptured, 2 missions | **2.0246x** |
| `lunar_surface` | 2.9353x‡ | 2005 QP87 (X), Falcon Heavy (expendable) on iodine | 8.2537x |
| `mars_orbit` | 4.5908x | 350751 (B), New Glenn on iodine | 13.9410x |
| `cislunar` | 4.8379x | 2018 DT (M), above | 20.9073x |
| `geo` | 6.8572x | 2016 GS2 (D), New Glenn on iodine | 92.9549x |
| `leo` | 17.0106x | 2005 QP87 (X), Falcon Heavy (expendable) on iodine | 60.4780x |
| `earth_surface` | 6,154.06x† | 2018 DT (M), Falcon Heavy (expendable) on iodine | 24,301.21x |

† At `max_fleet_ships` on every row, so the ladder's top rung, not an optimum.

‡ Re-run over the full catalog at master v1.43.0 (calc 1.27.0, mineral_value
1.12.2) on 2026-10-06. 2018 DT's 2.9068x at v1.40.0 rested on schreibersite
being priced at the base utility on the Moon, which made it the dearest phase
in the hold; with that corrected 2018 DT scores 2.9996x. See
[the full cell](versions.md#the-full-lunar_surface-cell-at-this-release).

#### What has moved since, on samples

No full cell has been re-run since. Each release below was measured on a sample
holding each cell's top bodies, and its release note has the detail.

| release | what changed | what it did to the table above |
|---|---|---|
| [master v1.43.0](versions.md#master-v1430--calc-v1270) (calc 1.27.0) | a settled stack a fraction of a percent over its vehicle is re-solved with less payload instead of refused | about two bodies in five got a better mission; no best case moved. The `lunar_surface` row is this release's full cell |
| [master v1.46.0](versions.md#master-v1460--mineral_value-v1130--transportation-v1180) (mineral_value 1.13.0) | nickel, iron, iridium, ruthenium and four more reference prices re-pinned to their sources | `earth_surface` only: **2018 DT 6,154.06x to 5,374.37x**; the other winners move under 2% |
| [master v1.47.0](versions.md#master-v1470--calc-v1280) (calc 1.28.0) | the sizing loop backs off toward the last state that closed instead of refusing at pass 2 | evaluable bodies go from 36-56% of the catalog to about 89%; no body worse, every winner the same float. Compare paired bodies, not the medians of two evaluable sets |
| [master v1.50.0](versions.md#master-v1500--mineral_value-v1140--transportation-v1200) (spacecost 0.8.0) | the LEO anchor rises to $2,555/kg | each in-space winner improves by 0.55% (`mars_surface`, 1.09136x to 1.08536x) to 5.04% (`leo`); `earth_surface` is 0.32% worse. A dearer launch reads as better mining, because a kilogram in space is worth the launch it avoids |
| [master v1.51.0](versions.md#master-v1510--calc-v1290) (calc 1.29.0) | the overshoot repair stops refusing its own exact fit | 8 to 328 bodies per destination improve by a median 1-18%; the `lunar_surface` winner becomes **2014 YN, 2.86091x**; every other winner is the same float |
| [master v1.52.0](versions.md#master-v1520--calc-v1300--mineral_value-v1150--transportation-v1210) (spacecost 0.9.0) | lunar descent re-pinned to Apollo's 2,050 m/s | `lunar_surface` only: **2014 YN 2.86091x to 2.61433x** |
| [master v1.53.0](versions.md#master-v1530--transportation-v1220) (spacecost 0.10.0) | krypton priced at $794/kg, where it was an unsourced $300 | the `cislunar` winner, 2018 DT, moves to iodine at **4.61562x**; every other winner is the same float |
| [master v1.55.0](versions.md#master-v1550--calc-v1320--transportation-v1230) (calc 1.32.0) | ISRU hydrolox pays for its electrolysis and liquefaction | charged, hydrolox ISRU wins no sampled row; see [What the model charges for](MODEL.md#what-the-model-charges-for) |
| [master v1.56.0](versions.md#master-v1560--catalog-v1100) (catalog 1.10.0) | the catalog repins to `data-2026-10-21b`: PGM factors computed for the S complex, Q, K and L, and Tagish Lake's carbon for D, Z, T and P | on a 3,922-body sample, `earth_surface` S bodies better by a median 18-21% and the default best becomes 2018 RT1; the `lunar_surface` raw best becomes 2024 SE4; in space hundredths of a percent |

⚠️  **Seven cells, one setting.** The raw and N = 1 cells have not been run on
these inputs at any destination.

#### Older full matrices

The last full matrices measured older models on older inputs, and are kept in
the history:

- **The 28-cell matrix** (calc 1.21.2, 2026-09-11/13): every destination the
  model then had, at both ore states and both programme settings, on the full
  catalog, 63.2 h of compute. It is the only measurement of the raw and N = 1
  cells at every destination. Reproducing a cell takes the four calc v1.22.0
  flags above, `model_mineral_phases`, `model_refinery` and
  `model_detailed_phases` off, and the inputs frozen under `campaign/stage2/`
  and `campaign/stage3/`. See [`campaign/FINDINGS.md`](campaign/FINDINGS.md)
  and [the 2026-09 campaign](versions.md#the-2026-09-campaign-population-detail).
- **The cislunar 2x2 at the v1.22.0 defaults** (2026-09-16), where a
  configure-nothing run answered 3.1822x:
  [the full-catalog cislunar 2x2](versions.md#the-full-catalog-cislunar-2x2-at-these-defaults-2026-09-16).

Neither found a viable mission, and neither does anything since.

## Version history

Every release note, every superseded measurement and the
[per-module changelogs](versions.md#module-changelogs) are in
**[`versions.md`](versions.md)**, newest first. The changelogs are the *schema*
history: which release added which config field and output column, which is
what says whether an archived CSV can answer the question you are asking of it.

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

## Data sources

- **The asteroid catalog**, a published [AsteroidCatalog](https://github.com/loggger101/AsteroidCatalog) release merging NASA JPL SBDB, IMCCE SsODNet ssoBFT, NEOWISE Diameters & Albedos V2.0 and MP3C
- **Commodity prices**, a published [spacevalue](https://github.com/loggger101/spacevalue) price release: COMEX and NYMEX closes recorded from Yahoo Finance, and USGS, LME, LBMA, World Bank and Johnson Matthey reference prices, each dated; its CITATIONS.md lists them
- **Fuel-cost proxies**, a recorded [spacecost](https://github.com/loggger101/spacecost) quote snapshot of the NYMEX heating-oil and Henry Hub natural-gas closes

🔔  **[`CITATIONS.md`](CITATIONS.md) is the authority for how to cite these**,
and two of them ask for citation as a **condition of use** rather than as a
courtesy: SsODNet (Berthier et al. 2023) and NEOWISE V2.0 (Mainzer et al. 2019,
doi:10.26033/18S3-2Z54). If a figure from this pipeline is published, those
travel with it. The list above says what each source supplies; it deliberately
does not restate the citations.

### What the catalog's provenance columns say

The catalog is a published [AsteroidCatalog](https://github.com/loggger101/AsteroidCatalog)
release, and every row says where its numbers came from. Two columns matter
most here, because the model's mass, and so its ranking, rests on them:

| column | values | read it as |
|---|---|---|
| `diameter_source` | `measured`, `derived_mass`, `derived_h_measured_albedo`, `derived_h_taxonomy_albedo`, `derived_h_orbit_albedo` | only `measured` is a size somebody observed; `derived_mass` is sized from a measured mass at the class density (data contract 1.4.0); the three `derived_h_*` are sized from H and an albedo |
| `spectral_type_source` | `source`, `tholen`, `albedo`, `albedo_assumed`, `orbit`, `unknown` | only `source` and `tholen` rest on a spectrum; `orbit` types an untyped body from the Trojans outward as D (data contract 1.4.0) |

In `data-2026-10-21b`, **149,718** of 1,575,889 bodies have a measured diameter
and 171,109 a taxonomy from a source; the rest are inferred. ⚠️  **Mass is the
exposed quantity**: D scales as `p_V^-0.5` and mass as `p_V^-1.5`, so a
factor-2 albedo error is a factor-2.8 mass error. Filter on
`derived_diameter_is_estimate` before treating a derived row as comparable to
a measured one.

How the albedo tables are built, what 1.4.0 corrected in them, and every
source's quirks are the catalog's to document: see the AsteroidCatalog README
and CHANGELOG. How two sources once contributed nothing for releases while
Stage 1 built the catalog here, and the catalog-size history, are in
[versions.md > Stage 1 when it built the catalog](versions.md#stage-1-when-it-built-the-catalog).

## History

Pre-git module copies, the original Colab notebook, and the parallel-repo
divergence that made `1.0.6` / `1.1.4` / `1.3.6` each mean two different things:
[Repository history](versions.md#repository-history).

## License

MIT, see [`LICENSE`](LICENSE). That covers the code. It does not cover the
upstream data the pipeline fetches at run time or the third-party code adapted
into it, and [`CITATIONS.md`](CITATIONS.md) is the license position for both.
Two sources require citation as a condition of use, not as a courtesy, and
those citations travel with any published figure derived from this pipeline.
The adapted routine in `orbital.py` is MIT,
Copyright (c) 2013-2018 Brandon Rhodes.
