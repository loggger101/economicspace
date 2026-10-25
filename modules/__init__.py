# -*- coding: utf-8 -*-
"""The four stages of the asteroid profitability pipeline, as one package.

    catalog          Stage 1, the pinned catalog release
    mineral_value    Stage 2, commodity prices per destination
    transportation   Stage 3, the spacecost reference tables
    calc             Stage 4, the mission search and ranking
    _runtime         what each of them does before its own code runs

`master.py` at the repo root imports all four and is what the entry points
use.  Each module also runs on its own (`python modules/calc.py`).

This file imports none of them on purpose: a spawned Stage 4 worker imports
`modules.calc` and nothing else.  The console encoding and the worker's quiet
mode happen in `_runtime`, which every module imports before it prints.
"""
