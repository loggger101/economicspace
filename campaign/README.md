# Full-matrix measurement campaign - started 2026-09-09

7 destinations x {raw, beneficiated} x {search OFF (N=1), search ON} = 28 cells.

This is the SECOND full-matrix campaign.  The first ran 2026-08-23/24 on calc
`1.17.7` over five destinations and twenty cells; it is complete, and its
ledger, its frozen Stage 2 prices and its memory record are kept under
`archive-2026-08_calc-1.17.7/` with its cell archives under
`cells/archive-2026-08_calc-1.17.7/`.  Nothing in this campaign is comparable
with it cell for cell: the code, the market model, the insurance default and
the price epoch all moved in between.

Code under measurement (all stamps verified against `verify_docs.py` before start):
  catalog 1.2.0 | mineral_value 1.9.0 | transportation 1.14.0
  calc 1.21.2   | master 1.26.0
  master.py rebuilt from modules/, `git status` clean afterwards.
  platform_check.py: all 18 probes match the reference host, so cell hashes
  taken here are directly comparable with the ones in versions.md.

What is different from the 2026-08 campaign, and why every level moved:
  * two more destinations, `geo` and `mars_orbit`, never measured before
  * `market_model` defaults to `capacity_cap`; every 2026-08 cell is an
    `elasticity` figure
  * `charge_insurance` defaults False; every 2026-08 cell was charged it
  * Stage 3 re-run, so the tables carry the four `geo` and three `mars_orbit`
    delta-v segments that transportation 1.13.0/1.14.0 added.  The 2026-08
    tables have 26 segments and cannot price either new destination.

Inputs frozen for the whole campaign:
  Stage 1 asteroid_catalog.csv    2026-08-11  (1,555,667 rows)  NOT re-fetched:
    JPL adds bodies daily, so a rebuilt catalog is a different length and is
    comparable with nothing already measured.  It is deliberately one release
    behind (catalog 1.1.1 columns, module now 1.2.0), so `stamp_check()` says
    so on every run.  That is the deliberate-lag case its own note describes,
    not a failed write.
  Stage 3 transportation/*.csv    2026-09-09  (propellants 41, ops 44, dv 33)
  Stage 2 mineral_value           2026-09-09, all SEVEN destinations priced in
    one sitting, frozen into `stage2/`.  Never re-fetched during the campaign;
    `run_cell.py` copies the right one into place per cell.

  Backup of the pre-campaign inputs: `asteroid_pipeline/_inputs_backup_2026-09-09/`

## The live-price drift, measured rather than assumed

The 2026-08 campaign verified `live_price_usd_per_kg` IDENTICAL across all five
destinations.  This one cannot say that: COMEX futures were trading during the
seven fetches, and two of the five live-priced minerals ticked.

| mineral | spread across the seven | relative |
|---|---|---|
| gold | 142,199.5339 to 142,212.3910 | **9.0e-5** |
| copper | 14.8779 to 14.8790 | **7.4e-5** |
| platinum, palladium, silver | identical | 0 |

Accepted rather than fixed, deliberately.  It is the same order as the -0.004%
`leo` drift the committed record already carries and explicitly says not to
read as a regression, and three orders below the destination-to-destination
differences this matrix exists to measure.  Both alternatives are larger
methodological changes than the thing they fix: pricing off the reference table
alone abandons live prices entirely, and a price-pinning mechanism is new
config surface added mid-campaign.  The per-destination values are auditable in
`stage2/mineral_value_catalog.<dest>.csv`.

⚠️  A cross-destination claim resting on a difference finer than 1e-4 is not
supported by this campaign.  Nothing in the 2026-08 matrix came close to that.

## Layout

  `stage2/mineral_value_catalog.<dest>.csv`  the seven frozen price catalogs
  `run_cell.py <dest> <raw|benef> <off|on>`  one cell: copy Stage 2, run
      `--stages 4` only, time it, archive the output gzipped to `cells/`,
      append one row to `results.csv`
  `run_queue.py`   runs everything outstanding, resumable: it skips any cell
      already in `results.csv` with `rc == 0`.  Kill and restart freely.
  `analyse.py <dest>`  the 2x2 table plus the never-worse, mass-ledger and
      programme-structure invariants.  Do NOT run it while a cell is timing;
      in 2026-08 it inflated a wall clock by a few percent and put two spurious
      10.7-11.5 GB spikes in the memory record.
  `memwatch.py`    samples python RSS every 20 s into `memory.csv`.

Per cell: `profitability_catalog.csv` is archived gzipped to `cells/` and one
row is appended to `results.csv`.

⚠️  `CAMPAIGN_ROWS` caps rows for smoke-testing the ledger and archive plumbing
in a minute rather than in hours.  A capped run is NOT a campaign measurement;
delete its ledger row and its archive afterwards.
