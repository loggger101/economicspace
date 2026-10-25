# -*- coding: utf-8 -*-
"""The four stages of the asteroid profitability pipeline, as one package.

    catalog          Stage 1, the pinned catalog release
    mineral_value    Stage 2, commodity prices per destination
    transportation   Stage 3, the spacecost reference tables
    calc             Stage 4, the mission search and ranking

`master.py` at the repo root imports all four and is what the entry points
use.  Each module also runs on its own (`python modules/calc.py`).

This file imports none of them on purpose: a spawned Stage 4 worker imports
`modules.calc` and nothing else, and it runs this first.  So this holds only
what has to happen before any module prints.
"""

# -----------------------------------------------------------------------------
# CONSOLE ENCODING
# -----------------------------------------------------------------------------
# Windows consoles default to cp1252.  Every print in the four modules is
# ASCII, so this is for what the source does not control: tqdm's bars, a
# traceback quoting a non-ASCII path, data reaching stdout.  Before the first
# print().

import sys as _sys
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# -----------------------------------------------------------------------------
# SPAWNED-WORKER QUIET MODE
# -----------------------------------------------------------------------------
# Stage 4 evaluates asteroids across a process pool.  Windows has no fork, so
# every worker imports `modules.calc`, and with it this file, and would replay
# calc's banners -- 60 lines each, 700+ for a full pool, interleaved into the
# run log the UI parses.  Stage 4's parent sets ASTEROID_PIPELINE_WORKER before
# creating the pool; children inherit it.  Must run before calc's install
# block prints, which is why it is here: a package's __init__ runs before any
# of its modules.
#
# Flipped to "silenced" rather than cleared so that calc's own copy of this
# guard -- the modules each carry one, for when they are run standalone -- is a
# no-op after this one instead of leaking a second handle.
#
# stderr is deliberately left alone: a worker that dies should still say so.

import os as _os
if _os.environ.get("ASTEROID_PIPELINE_WORKER") == "1":
    _os.environ["ASTEROID_PIPELINE_WORKER"] = "silenced"
    _sys.stdout = open(_os.devnull, "w", encoding="utf-8")
