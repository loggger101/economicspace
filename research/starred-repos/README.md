# research/starred-repos

An audit of 17 starred repositories against this pipeline, and the code and
data worth taking from them.

🚨  **Nothing here is wired into the pipeline.** No module, config or CSV was
touched and no `pipeline_version` moved. Every script reads only, and none of
them runs Stage 1, 2 or 3, so none can invalidate a `.verify` baseline.

## What to read

| file | what it is |
|---|---|
| [`FINDINGS.md`](FINDINGS.md) | **start here.** Five findings, each a measurement on this repo's own catalog, with the recommendations at the end |
| [`SOURCES.md`](SOURCES.md) | per-repository inventory: licence, the specific files worth reading, and a verdict. Several stars are worth less here than they look |
| [`../../CITATIONS.md`](../../CITATIONS.md) | **the authority for every reference and attribution obligation in this repo**, including what was adapted from whom here |
| [`SPACE-MAP.md`](SPACE-MAP.md) | a focused re-audit of one repo the first pass got wrong. It found the orbit-quality gap |

## What to run

Every script takes the repo root as its working directory and needs only
numpy and pandas.

```bash
py research/starred-repos/probe_plane_change.py
py research/starred-repos/probe_taxonomy.py --repo . --cache research/starred-repos/sdsstax_ast.tab
py research/starred-repos/probe_lambert.py --n 400 --seed 1
```

| file | what it measures | runtime |
|---|---|---|
| `probe_plane_change.py` | where the plane change is paid (F1). Reproduces the five figures in `asteroid_transfer_dv_km_s`'s docstring first, which is what says it is measuring the shipped model | seconds |
| `probe_taxonomy.py` | taxonomy provenance and cross-survey disagreement (F2) | ~30 s |
| `probe_lambert.py` | the closed-form estimator against a real optimised transfer (F4) | ~10 min at n=400 |
| `orbital.py` | Kepler solver, elements to state vectors, and a validated Izzo Lambert solver. Imported by `probe_lambert.py`; not a probe itself | - |
| `patch_neowise_async.py` | a **patch candidate**, not live code: an async-TAP `fetch_neowise` that survives the 502 outage CLAUDE.md records. `py patch_neowise_async.py` runs a capped comparison against the live service | ~15 s |

## Data

`sdsstax_ast.tab`, 7.5 MB, is the SDSS-based Asteroid Taxonomy V1.1 asteroid
table from the PDS Small Bodies Node. It is **static**, so unlike the Stage 1
catalog it does not change under a re-fetch, which is what makes it safe to
commit. `probe_taxonomy.py` downloads it if absent. The citation, which is a
condition of use, is in [`../../CITATIONS.md`](../../CITATIONS.md).

## The one thing to take away

The two Δv findings point in **opposite directions** and partially cancel.
F1 says the model overcharges the plane change; F4 says it undercharges the
transfer geometry by more. Fixing either alone makes the model worse. If you
read only one thing here, read F4's reversal table.
