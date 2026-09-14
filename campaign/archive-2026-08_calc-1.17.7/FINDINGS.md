# Campaign findings - 2026-08-23/24 - COMPLETE

The 20-cell full-matrix campaign finished on 2026-08-24. **Its findings have
been promoted into the three main documents and are not repeated here**, for
the reason CLAUDE.md gives everywhere else: name one authority, or you have
two. This file is now the campaign's own record, not a copy of the results.

Code under measurement: catalog `1.1.1` | mineral_value `1.7.1` |
transportation `1.12.1` | calc `1.17.7` | master `1.20.8`. `master.py` rebuilt
from `modules/`, `git status` clean afterwards. Catalog 1,555,667 rows
(2026-08-11 snapshot). Stage 2 priced once per destination on 2026-08-23, live
prices verified identical across all five. Stages 1 and 3 frozen throughout, so
every cell is comparable. 12 workers, 26.1 h of compute, zero failures.

## Where the findings went

| finding | now lives in |
|---|---|
| the 20-cell cost/revenue matrix | [README.md, Results](../README.md#current-results-the-complete-20-cell-matrix) |
| per-destination propellant, vehicle, rig-bound and cadence tables | [CLAUDE.md, What the model currently says](../CLAUDE.md#what-the-model-currently-says-and-what-that-retired) |
| the `1.17.x` runtime and cost-ratio measurements | [versions.md, What the v1.17.x line was worth](../versions.md#what-the-v117x-line-was-worth) |
| the wall clock for all twenty cells | [README.md, Beneficiation](../README.md#beneficiation) |
| claims the campaign retired | [CLAUDE.md, The older matrices](../CLAUDE.md#the-older-matrices-and-the-claims-they-retired) |

## What the campaign established, in one line each

1. **The committed cislunar 2x2 reproduces EXACTLY on calc 1.17.7**, every
   headline, share and invariant, against a re-priced Stage 2 catalog and a
   snapshot 1,267 bodies larger than some committed cells.
2. **Twelve of the twenty cells had never been measured**: every non-cislunar
   beneficiated cell and every non-cislunar searched cell.
3. **The first full-catalog runtime on the `1.17.x` line**, which moved five
   committed cost ratios; the whole 2x2 is 3.52x faster than on `1.16.0`.
4. **`1.17.7`'s memory bound holds**, measured rather than projected, and peak
   RSS tracks output size rather than ladder traffic.
5. **RETIRED: a `replicated`-scaling device DOES win**, at `mars_surface` raw
   with the programme search on.
6. **RETIRED: `earth_surface`'s searched cells are not optima**, because market
   saturation is numerically inert there and 100% of rows run to the fleet
   ceiling.
7. **Iodine returns at scale**, New Glenn rises at every destination, and
   `mars_surface` inverts both of the rig's bounds.
8. **THE SAMPLING RULE was scored for the first time** against the arithmetic
   it forbids: compounding per-release sample ratios lands within 3% on three
   cells and 20% low on the default cell.

## The raw record

Prose is not the record; these are.

```
campaign/results.csv       one row per cell: ratio, winner, evaluable, wall clock
campaign/cells/            the archived profitability_catalog.csv per cell, gzipped
campaign/logs/             per-cell driver logs, the queue log, memwatch, extra checks
campaign/memory.csv        RSS sampled every 20 s across the whole campaign
campaign/stage2/           the per-destination Stage 2 catalogs the cells were priced from
```

The scripts that produced them (`run_queue.py`, `run_cell.py`, `analyse.py`,
`extra_checks.py`, `rig_bounds.py`, `memwatch.py`) are alongside.
`campaign/README.md` carries the layout and the frozen inputs; the resume
procedure is `run_queue.py`'s own docstring, which is the thing that implements
it: it skips every cell already in `results.csv` with `rc == 0`, so the queue is
safe to kill and restart and loses at most the in-flight cell.

⚠️  **Do not re-run Stage 1, 2 or 3 to re-check anything here.** Stage 2
re-fetches live prices and Stage 1 re-fetches a catalog JPL adds to daily;
either invalidates every cell in `results.csv` and every `.verify` baseline.
The frozen inputs are backed up at
`asteroid_pipeline/_inputs_backup_2026-08-23/`.
