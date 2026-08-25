# Full-matrix measurement campaign - started 2026-08-23

5 destinations x {raw, beneficiated} x {search OFF (N=1), search ON} = 20 cells.

Code under measurement (all stamps verified against CLAUDE.md before start):
  catalog 1.1.1 | mineral_value 1.7.1 | transportation 1.12.1
  calc 1.17.7   | master 1.20.8
  master.py rebuilt from modules/, `git status` clean afterwards.

Inputs frozen for the whole campaign:
  Stage 1 asteroid_catalog.csv    2026-08-11  (1,555,667 rows)
  Stage 3 transportation/*.csv    2026-08-23  (propellants 41 rows, ops 44 rows)
  Stage 2 re-run PER DESTINATION only (prices are per-destination); Stage 1 and
  Stage 3 are NEVER re-run during the campaign, so every cell is comparable.

Backup of the starting inputs: asteroid_pipeline/_inputs_backup_2026-08-23/

Per cell: profitability_catalog.csv is archived (gzipped) to campaign/cells/
and one row is appended to campaign/results.csv.
