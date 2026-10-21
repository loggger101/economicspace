# -*- coding: utf-8 -*-
"""Run the campaign queue unattended, resumably.

Reads campaign/results.csv, skips every cell already recorded with rc == 0, and
runs the rest in order via run_cell.py.  Safe to kill and restart: at most the
in-flight cell is lost, because run_cell.py appends its ledger row the moment a
cell finishes.

    python campaign/run_queue.py            # run everything outstanding
    python campaign/run_queue.py --list     # show the queue and stop
    python campaign/run_queue.py --only cislunar lunar_surface

The runner is quietqueue's `run_queue` (see quietqueue_pin.py for the pin);
this file is the campaign: `DESTS`, `CELLS`, how a cell is named, the
`run_cell.py` command that runs one, and the ledger.  quietqueue is imported
only to run the queue, so `analyse.py` and `population.py`, which import
`DESTS` from here, need nothing installed.

The queue only READS the ledger; `run_cell.py` writes it.  So the ledger is a
parameter here and never a command-line flag: pointing the queue at a file
`run_cell.py` does not append to would make every cell look outstanding
forever.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMP = os.path.join(ROOT, "campaign")
LEDGER = os.path.join(CAMP, "results.csv")
RUN_CELL = os.path.join(CAMP, "run_cell.py")

# Best case first, then work outward; cheapest cell first within a destination.
# `geo` and `mars_orbit` are third and fourth rather than last because, when
# the 2026-09 campaign was queued, no cell had ever been run at either, and a
# campaign measured in days should learn its unknowns early.  That campaign
# measured them (MEASURED_DEST_SECONDS), so the order is kept for continuity,
# not need.  `gto` joins this list only once a cell is measured.
DESTS = ["cislunar", "lunar_surface", "geo", "mars_orbit",
         "leo", "mars_surface", "earth_surface"]
CELLS = [("raw", "off"), ("raw", "on"), ("benef", "off"), ("benef", "on")]

QUEUE = [(d, o, s) for d in DESTS for (o, s) in CELLS]


def cell_jobs(queue=None):
    """This campaign's queue as quietqueue `Job`s, one `run_cell.py` call per cell.

    The key is the cell name `run_cell.py` writes into the ledger's `cell`
    column, `<dest>__<ore>__search-<off|on>`; the two are built separately,
    so a change to one is a change to both.
    """
    from quietqueue import Job
    return [Job(f"{d}__{o}__search-{s}", d, (d, o, f"search-{s}"),
                [sys.executable, RUN_CELL, d, o, s])
            for d, o, s in (QUEUE if queue is None else queue)]


def main(argv=None):
    """This campaign's queue against this campaign's ledger, on the pinned quietqueue."""
    from quietqueue_pin import require
    qq = require()
    return qq.run_queue(cell_jobs(), LEDGER, key="cell", cwd=ROOT, argv=argv,
                        unit="cell", group_noun="destinations")


if __name__ == "__main__":
    sys.exit(main())
