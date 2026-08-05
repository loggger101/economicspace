# Asteroid Profitability Pipeline

Estimates whether returning mined material from a given asteroid pays for the
mission that fetched it. Four modules feed a rocket-equation mass cascade and a
cost cascade, producing a per-asteroid profit ranking.

Mission profile throughout: **uncrewed autonomous mining** — no crew costs, no
life-support overhead, no human in the loop past LEO.

## Layout

| File | Role |
|---|---|
| `profitability_pipeline(1.0.6).py` | **Module 1** — asteroid catalog: JPL SBDB + MP3C + SsODNet + NEOWISE, spectral taxonomy → composition fractions |
| `MineralValue(1.1.4).py` | **Module 2** — mineral and element pricing: yfinance live + USGS/LME reference + mineralogy yields |
| `TransportationData(1.2.4).py` | **Module 3** — launch vehicles, propellants, Δv segments, operational costs |
| `CalcPipeline(1.3.6).py` | **Module 4** — rocket-equation cascade + cost cascade + ranking |
| `.combine_master.py` | Build tool — assembles the four modules into one runnable file |
| `Master(1.4.3).py` | **Generated.** Do not edit — edit a module and rebuild |
| `Profitability Pipeline.ipynb` | Original Colab working notebook (see *History* below) |

Modules run standalone or via the Master. The Master is what you paste into
Colab: it is self-contained, installs its own dependencies, and the orchestrator
at the bottom runs all four stages top to bottom.

## Running it

```bash
python "Master(1.4.3).py"
```

Outputs land under `MASTER_CONFIG.output_dir` (default
`/content/asteroid_pipeline`, which is the Colab path):

```
asteroid_catalog.csv          Stage 1  (~30-40 MB at 50k rows)
rejected_entries.csv          Stage 1  (validation rejects)
mineral_value_catalog.csv     Stage 2
transportation/*.csv          Stage 3
profitability_catalog.csv     Stage 4  — the headline output
```

To import the Master for its functions without running the pipeline, set
`MASTER_AUTORUN = False` before importing.

### Main tuning knobs

All on `MASTER_CONFIG`, set before `run_full_pipeline()` fires:

| Knob | Effect |
|---|---|
| `catalog.jpl_limit` | asteroid catalog size |
| `calc.eval_row_cap` | cap Stage 4 evaluations (default 5,000; `0` = all) |
| `calc.nre_amortization_missions` | spread $588M bus NRE + $200M autonomy NRE across a fleet |
| `calc.use_isru_return_propellant` | manufacture return propellant at the asteroid |
| `calc.use_aerocapture_return` | heat-shield return instead of propulsive |
| `calc.max_mining_fraction` | share of asteroid mass a single mission may take |

At `nre_amortization_missions = 1` essentially nothing is profitable — the
first mission carries the entire development cost. Raising it is the main lever.

## Rebuilding the Master

Edit a **module**, never `Master(*).py` — the Master is machine-assembled and
any hand edit is lost on the next build.

1. Bump the module's `pipeline_version` field.
2. Save it under the matching new filename.
3. Update the version constants at the top of `.combine_master.py`.
4. `python .combine_master.py`

The build strips each module's docstring, auto-install block and auto-run
block, renames colliding globals (`CONFIG` → `CATALOG_CONFIG` etc.) and
functions, then concatenates. Afterwards it parses what it wrote and reports
any top-level name defined twice — a silent shadowing bug otherwise, since
Python just lets the last definition win.

Each strip is anchored to a literal the four modules share (the `# INSTALLATION`
banner, the `# RUN & PREVIEW` banner, the `# -*- coding -*-` line). Rename or
move one in a module and that strip would quietly match nothing, folding the
text it should have cut into the Master — at worst a module's auto-run block
firing partway down the file, re-running that stage on import. The build now
stops and names the module and the strip that missed, so bump the anchors and
the strip together.

### Filenames must match `pipeline_version`

Every output CSV carries a `pipeline_version` column, so a filename that
disagrees with the version inside it makes that provenance column lie.

This drifted badly before the repo existed: every save went to the *previous*
version's filename, leaving six files misnumbered and four pairs byte-identical.
Four module revisions were overwritten in place and survive only inside the
Colab notebook. To check:

```bash
grep -H "pipeline_version: str" *.py
```

## History

The repo starts with the pre-cleanup state, so nothing is lost. Superseded
versions live in history rather than the working tree:

```bash
git log --oneline
git show d368dce:"profitability_pipeline(1.0.5).py" > restored.py
git show d368dce --stat
```

`Profitability Pipeline.ipynb` is kept deliberately. It was extensionless (so
nothing could open it) and is not a duplicate of any `.py`: it is the only
surviving copy of Module 1 v1.0.3, Module 2 v1.1.0, Module 3 v1.2.0 and
Module 4 v1.3.2.

## Note on Google Drive — the repo lives outside it

The working files are in a synced Drive folder, but the git repository is not.
`.git` here is a one-line pointer file, not a directory:

```
gitdir: C:/Users/Owner/repos/profitability-pipeline.git
```

Git commands work normally from this folder — nothing to remember day to day.

This is deliberate. Drive seeds a `desktop.ini` into every folder it syncs, and
within seconds of `git init` it had written 41 of them inside `.git`, including
`refs/heads/` and `refs/tags/`, which git reads as refs (`warning: ignoring
broken ref refs/tags/desktop.ini`). Worse, a sync landing mid-write on a loose
object can corrupt the repository. Moving the git directory to local disk stops
Drive touching git internals at all.

Consequences worth knowing:

- **History is on this machine only.** Drive backs up your working files, not
  the repo. Push to a remote if you want history backed up too.
- **On another machine the pointer path won't resolve.** Re-point it by editing
  the `.git` file, or clone from a remote instead.
- Moving the repo: edit the path in `.git`, and update `core.worktree` in
  `C:/Users/Owner/repos/profitability-pipeline.git/config`.
