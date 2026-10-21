# -*- coding: utf-8 -*-
"""Sample total python RSS every 20 s and record the peak per campaign cell.

Exists because 1.17.7 bounded _CALENDAR_CACHE against a PROJECTED 11-18 GB that
nobody had measured -- no full-catalog run had been made since 1.16.0.  This
turns that projection into a measurement, for free, across the whole campaign.
Appends to campaign/memory.csv; one row per sample.

    python campaign/memwatch.py          # sample until killed
    python campaign/memwatch.py --once   # write one row and stop

The sampler is quietqueue's `watch` (see quietqueue_pin.py for the pin); this
file is the campaign's: `memory.csv` and its column names, which every row
since 2026-08 carries, the logs a cell's name is read from, and the log names
that are not cells.  It counts every python process, ITSELF and any analysis
running alongside included: two 2026-08 peaks of 11.54 and 10.74 GB were that.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "campaign", "memory.csv")
LOG_DIR = os.path.join(ROOT, "campaign", "logs")
# The queue's and the harnesses' own logs start with `_`, and Stage 2's
# pricing logs with `stage2`: neither is a cell.
SKIP_PREFIXES = ("_", "stage2")
PROCESS_NAME = "python"
INTERVAL_S = 20
COLUMNS = ["ts", "cell", "n_python", "total_rss_gb", "max_proc_rss_gb", "sys_used_gb"]


def main(argv=None):
    """This campaign's watcher: `memory.csv`, the campaign logs, every 20 s."""
    from quietqueue_pin import require
    require()
    from quietqueue.memwatch import watch
    args = sys.argv[1:] if argv is None else list(argv)
    watch(OUT, LOG_DIR, SKIP_PREFIXES, PROCESS_NAME, INTERVAL_S,
          once="--once" in args, columns=COLUMNS)


if __name__ == "__main__":
    main()
