# -*- coding: utf-8 -*-
"""The cargo valuation's seam: coverage cells and the golden fixture.

Since calc 1.33.0 what a hold is worth is `spacevalue.cargo`, and spacevalue's
`tests/test_cargo_golden.py` replays calls recorded HERE, inside a Stage 4
run, for the last bit.  This file is the recorder, and the extra coverage
`verify.py` does not have.

verify.py's four cells run the default flags, and check 7 adds `unbounded`.
The cargo code also holds the elasticity multiplier, the single-mission
market, the four-fraction walk, the comp_phases fallback, the price-deduction
refinery and the surplus wall.  VARIANTS builds one small cell per such branch
through `verify.run_cell` (same scratch output dir, same resets, same hash).

    py campaign/cargo_golden.py record DIR [--fixtures FILE]   # before a change
    py campaign/cargo_golden.py check DIR [--plant NAME]       # after it

Run from the repository root: Stage 4 reads `asteroid_pipeline/` relative to
the working directory, and every cell is cislunar like verify.py's.

`--fixtures` wraps the functions calc calls across the seam (BOUNDARY) on
`modules.calc` and keeps a seeded sample of real calls: arguments before and
after (the knapsack spends its `caps`) and the result, every float as `repr`,
written with spacevalue's own codec so the two ends cannot disagree.  Re-record
only at a calc release that moves a number, and name the fixture's directory
for that calc.  `--plant NAME` multiplies one cargo function's float result by
(1 + 2**-50), in whichever module defines it, to prove a check can fail.
"""
import argparse
import gzip
import json
import os
import random
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import verify  # noqa: E402
from spacevalue import _cargo_codec  # noqa: E402

RAW, BENEF = 150, 40

# (label, verify.py cell, row cap, overrides).  Each names the branch it is for.
VARIANTS = [
    ("default/raw",                "raw",          RAW,   {}),
    ("default/benef+search",       "benef+search", BENEF, {}),
    ("elasticity/raw",             "raw",          RAW,   dict(market_model="elasticity")),
    ("elasticity/benef+search",    "benef+search", BENEF, dict(market_model="elasticity")),
    ("single_mission/raw+search",  "raw+search",   RAW,   dict(market_model="single_mission")),
    ("single_mission/benef",       "benef",        BENEF, dict(market_model="single_mission")),
    ("unbounded/benef+search",     "benef+search", BENEF, dict(market_model="unbounded")),
    ("phases_off/raw",             "raw",          RAW,   dict(model_mineral_phases=False)),
    ("phases_off/benef",           "benef",        BENEF, dict(model_mineral_phases=False)),
    ("detailed_off/benef",         "benef",        BENEF, dict(model_detailed_phases=False)),
    ("refinery_off/raw",           "raw",          RAW,   dict(model_refinery=False)),
    ("refinery_off/benef",         "benef",        BENEF, dict(model_refinery=False)),
    ("surplus_wall/benef+search",  "benef+search", BENEF, dict(sell_surplus_at_discount=False)),
]

# The cargo functions calc calls.  spacevalue's golden test holds this list to
# the callables of its consumer contract.
BOUNDARY = [
    "market_table", "_parse_phases", "_row_phases", "_row_water_fraction",
    "asteroid_refinery", "refinery_plant_kg", "_hold_refining",
    "asteroid_bulk_value_usd_per_kg", "phase_market_key", "phase_market_kg",
    "asteroid_phase_table", "saturation_price_multiplier",
    "_delivery_window_yr", "_capped_sale_value", "optimal_payload_mix",
    "asteroid_best_phase_usd_per_kg",
]
# Per cell and function: the first K_FIRST calls, then a K_RES reservoir.
K_FIRST, K_RES = 8, 24
SEED = 20261026


def cargo_module():
    """The module that defines the cargo code: calc before 1.33.0, else spacevalue."""
    calc = sys.modules["modules.calc"]
    if hasattr(calc, "_blend"):
        return calc
    import spacevalue.cargo
    return spacevalue.cargo


def _perturb(x):
    """`x` one part in 2**50 larger, for a float or a tuple ending in one."""
    if isinstance(x, float):
        return x * (1.0 + 2.0 ** -50)
    if isinstance(x, tuple) and x and isinstance(x[-1], float):
        return x[:-1] + (_perturb(x[-1]),)
    return x


def plant(name):
    """Replace cargo function `name` with one whose float result is perturbed.

    In both namespaces that can call it: the cargo module's own (its internal
    callers) and calc's, which binds the names it imports to the SAME objects
    and so would never see a patch made only in the cargo module.  A plant
    patched in one place once read MATCH on a cell it should have moved.
    """
    mod = cargo_module()
    orig = getattr(mod, name)

    def planted(*a, **k):
        """`name`, perturbed."""
        return _perturb(orig(*a, **k))
    where = [mod]
    calc = sys.modules["modules.calc"]
    if calc is not mod and getattr(calc, name, None) is orig:
        where.append(calc)
    for m in where:
        setattr(m, name, planted)
    print("PLANTED  %s.%s returns its float x (1 + 2**-50)" % (
        " and ".join(m.__name__ for m in where), name))


class Recorder(object):
    """Wraps BOUNDARY on modules.calc and keeps a seeded sample of its calls."""

    def __init__(self, calc):
        """A recorder for `calc`, empty until `install`."""
        self.calc = calc
        self.enc = _cargo_codec.Encoder()
        self.rng = random.Random(SEED)
        self.slots = {}
        self.count = {}
        self.failed = {}
        self.variant = None

    def install(self):
        """Wrap every BOUNDARY name in calc's namespace, where calc looks it up."""
        for name in BOUNDARY:
            setattr(self.calc, name, self._wrap(name, getattr(self.calc, name)))

    def _wrap(self, name, orig):
        """`orig`, recording a sample of its calls under `name`."""
        rec = self

        def wrapper(*a, **k):
            """Call through; encode the call only when it wins a slot."""
            key = (rec.variant, name)
            n = rec.count.get(key, 0)
            rec.count[key] = n + 1
            slot = None
            if n < K_FIRST:
                slot = ("first", n)
            else:
                j = rec.rng.randrange(n - K_FIRST + 1)
                if j < K_RES:
                    slot = ("res", j)
            if slot is None:
                return orig(*a, **k)
            try:
                before = (rec.enc.enc(list(a)), rec.enc.enc(dict(k)))
            except TypeError as err:
                rec.failed[name] = str(err)
                return orig(*a, **k)
            r = orig(*a, **k)
            try:
                entry = {"variant": rec.variant, "fn": name,
                         "args": before[0], "kwargs": before[1],
                         "result": rec.enc.enc(r),
                         "args_after": rec.enc.enc(list(a)),
                         "kwargs_after": rec.enc.enc(dict(k))}
            except TypeError as err:
                rec.failed[name] = str(err)
                return r
            rec.slots[(key, slot)] = entry
            return r
        wrapper.__wrapped__ = orig
        return wrapper

    def dump(self, path):
        """Write the fixture and say what it holds and what it missed."""
        calls = [self.slots[k] for k in sorted(
            self.slots, key=lambda s: (s[0][0], s[0][1], s[1][0], s[1][1]))]
        # `host`: the replay holds every call to the bit only here; another
        # C library's pow may round the elasticity multiplier one ulp away.
        body = {"format": 1, "host": sys.platform, "boundary": BOUNDARY, "calls": calls,
                "blobs": self.enc.blobs,
                "counts": {"%s|%s" % k: v for k, v in sorted(self.count.items())}}
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(body, f, separators=(",", ":"))
        print("FIXTURES  %d calls, %d blobs -> %s (%d bytes)" % (
            len(calls), len(self.enc.blobs), path, os.path.getsize(path)))
        for name, why in sorted(self.failed.items()):
            print("  UNENCODED %s: %s" % (name, why))
        seen = {c["fn"] for c in calls}
        for name in BOUNDARY:
            if name not in seen:
                print("  NEVER CALLED  %s" % name)


def _csv_name(label):
    """The file a cell's canonical CSV is kept in."""
    return label.replace("/", "__") + ".csv"


def main():
    """Build every VARIANT, then record or check its hash."""
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("mode", choices=["record", "check"])
    p.add_argument("dir", help="where the hashes and canonical CSVs live")
    p.add_argument("--fixtures", help="record the golden fixture to this .json.gz")
    p.add_argument("--plant", help="perturb this cargo function, to prove the check fails")
    p.add_argument("--only", nargs="+", help="a subset of the VARIANTS labels")
    a = p.parse_args()

    m = verify.load_master()
    calc = sys.modules["modules.calc"]
    print("calc %s, cargo code in %s" % (calc.CONFIG.pipeline_version,
                                         cargo_module().__name__))
    rec = None
    if a.fixtures:
        rec = Recorder(calc)
        rec.install()
    if a.plant:
        plant(a.plant)

    os.makedirs(a.dir, exist_ok=True)
    index_path = os.path.join(a.dir, "index.json")
    old = {}
    if a.mode == "check":
        with open(index_path, encoding="utf-8") as f:
            old = json.load(f)
    out, ok = {}, True
    for label, cell, cap, override in VARIANTS:
        if a.only and label not in a.only:
            continue
        if rec:
            rec.variant = label
        t0 = time.time()
        df = verify.run_cell(m, cell, eval_row_cap=cap, **override)
        h = verify.cell_hash(df)
        out[label] = {"rows": len(df), "hash": h, "cell": cell, "cap": cap,
                      "override": override}
        line = "  %-28s %4d rows | %s | %5.1fs" % (label, len(df), h, time.time() - t0)
        if a.mode == "record":
            with open(os.path.join(a.dir, _csv_name(label)), "w",
                      encoding="utf-8", newline="") as f:
                f.write(verify._csv(df))
        else:
            was = old[label]
            match = was["hash"] == h and was["rows"] == len(df)
            ok &= match
            if match:
                line += " | MATCH"
            else:
                base = verify._read_baseline(None, os.path.join(a.dir, _csv_name(label)))
                same, compared, differ = verify.column_diff(df, base)
                line += " | DIFFER %d/%d columns: %s" % (
                    compared - same, compared, ",".join(differ[:6]))
        print(line, flush=True)
    if a.mode == "record":
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    if rec:
        rec.dump(a.fixtures)
    if a.mode == "check":
        print("ALL MATCH" if ok else "MISMATCH")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
