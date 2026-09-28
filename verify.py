# -*- coding: utf-8 -*-
"""Release verification harness for the asteroid profitability pipeline.

Run this before and after any change to Stage 4.  It is the checks every
release in versions.md argues from, written down once instead of rebuilt from
memory each time:

    1. bit-identity    four cells, column by column and by hash, vs a baseline
    2. prune on/off    the pre-filter agrees with the unpruned search
    3. serial/parallel a worker sees what its parent sees
    4. mass ledger     hardware_total_kg == rig + plant + ep, exactly
    5. never-worse     beneficiated <= raw, and searched <= N = 1
    6. stage 2 tables  the judgement tables still produce the numbers on disk
    7. market ceilings a capacity ceiling may only ever cost you, never pay

Typical use.  The ORDER matters: the baseline must be captured before the first
edit, exactly as every release note in versions.md says it was.

    py verify.py baseline           # on a clean tree, BEFORE editing
    ...make the change...
    py build_master.py
    py verify.py check              # bit-identity + every invariant

Other entry points:

    py verify.py check --skip prune parallel  # ~5 min: 1 and 4 to 7
    py verify.py check --cells raw benef      # a subset
    py verify.py invariants                   # 4 to 7 only; needs no baseline
    py verify.py baseline --tag 1.17.6        # keep several around

SCOPE.  Checks 1-5 and 7 cover STAGE 4; check 6 covers STAGE 2's judgement
TABLES.
Nothing here ever re-runs Stages 1-3 -- deliberately, because a Stage 2 or 3
run re-fetches live prices and a Stage 1 run at a moved pin installs a
different catalog, either of which moves the inputs underneath the comparison.  Check
6 works around that by recomputing the pure table functions against the values
already stored in the on-disk Stage 2 catalog, which needs no network.

Both of those now have harnesses of their own, and this file is still not
their evidence.  Stage 3's validate() is `verify_stage3.py` check 5;
transportation 1.12.1's propellant-flag fix lives there, and had been checked
once by hand under `-W error::FutureWarning`.  Stage 1 is `verify_stage1.py`,
which checks the pinned catalog release against this pipeline's data contract
and the catalog on disk against that release's bytes; the build itself is
verified in AsteroidCatalog before it is published.  If you change Stage 1 or
Stage 3, run those.

BUDGET.  A full `check` builds ~20 cells and takes roughly HALF AN HOUR on the
reference machine.  Most of that is check 2, because turning the pre-filter off
is what v1.14.1 and v1.17.4 exist to avoid -- an unpruned cell runs the whole
search.  Iterate with `--skip prune parallel` (~5 min, and it still catches any
change to any number: it turns off 2 and 3 and leaves 1 and 4 to 7 running),
then run the full set once before committing.  A
verification you will not run is worse than a slow one.

WHY THIS FILE EXISTS
--------------------
Every release so far wrote these checks from scratch and threw them away, and
CLAUDE.md records what that cost: a harness bug nearly every time, several of
which produced conclusions that were written down before being caught.  COUNT
THE LIST; the number is deliberately not written here, because it was written
here as "eleven" and went stale the next time one was added, which is the
counts-in-prose failure this repo catalogues everywhere else.

  v1.15.0   two cells recorded as "cislunar" that ran against earth_surface
            prices, because CALC_CONFIG defaults to earth_surface while the
            on-disk Stage 2 catalog is whatever destination was last built
  v1.15.0   a brute-force sweep truncated at N = 24 read as a counter-example
            to the very thing it was truncating
  v1.17.1   a parquet round trip rendered None as nan, so three identical
            object columns compared as different -- "a broken checker looks
            exactly like a broken release"
  v1.17.3   only pipeline_version stripped before hashing, so midnight falling
            mid-run made catalog_date differ, and that read as a defect
            confined to the beneficiation path
  v1.17.4   ImportError: No module named master -- a harness that loads the
            pipeline through spec_from_file_location never puts it in
            sys.modules, so _spawn_environment cannot pin it and every worker
            tries to rebuild the parent from a module it cannot import
  v1.17.5   KeyError on mining_hardware_kg -- the rig is a CONFIG CONSTANT and
            not an output column, so the mass-ledger identity as CLAUDE.md
            states it does not run verbatim against the CSV
  1.17.7    cost_revenue_ratio -- there is no such column; the objective is
            total_cost_usd / gross_value_usd
  1.17.7    median improvement quoted as median(1/r - 1) = 74.0%, where
            CLAUDE.md's committed convention is median(1 - r) = 42.5%
  1.17.7    column_diff compared two Series directly, so pandas aligned them on
            the index LABEL -- and build_profitability_catalog returns rows
            SORTED by the objective, so a live frame's index is scrambled while
            the same frame re-read from CSV has a fresh RangeIndex.  Every float
            column read as differing while the file hashed identical.  Found by
            this file on the first run it was written for, and the reason both
            a hash AND a column diff are reported: when they disagree, the hash
            is the one that is right.
  1.17.7    pd.read_csv without float_precision="round_trip".  The default C
            parser is a FAST float reader that is not correctly rounded, so a
            baseline read back came out one ULP off what was written --
            119898.18458829961 -> 119898.1845882996.  Same symptom as the row
            above (64 of 139 columns DIFFER against four byte-identical
            hashes) and a completely different cause, so it had to be
            diagnosed twice.  Neither the default nor "high" round-trips.
  1.17.7    the empty string compared as different from NaN.  An all-empty
            object column (payload_mix, payload_dominant_phase on a raw cell)
            writes as bare commas and reads back as float64-of-NaN, so a live
            "" met a nan.  A CSV cannot represent that difference, so the hash
            cannot see it either -- and a comparator stricter than the artefact
            it compares reports failures that do not exist.

  1.21.0    a baseline labelled "the new default" that was entirely
            `elasticity`.  `run_cell` resets four config fields explicitly and
            takes the rest from CELLS, and `market_model` is in neither -- so a
            harness that ran one cell with market_model="elasticity" left the
            live config there, and every later run_cell(m, name) in the same
            process inherited it silently.  This is trap 1 exactly, one field
            along: a config field nothing resets is whatever the last run left.
            The tell was internal contradiction, not an error -- check 7
            reporting 66 rows bound by a ceiling beside a frame whose MINIMUM
            clearing fraction was 1.0000, which cannot both be true of one
            population.  Fixed by resetting `market_model` from the DATACLASS
            default beside the other four.

  1.22.0    `col.dtype == object` on pandas 3.0.  A plain text column now reads
            back as an Arrow-backed StringDtype, so that test is False and
            every text column fell through to the numeric comparison: five
            reported as DIFFER (thrust_scaling, isru_feed_material, name,
            payload_mix, payload_dominant_phase) beside MATCHING hashes.  A
            fourth cause of the same symptom, and the first the ENVIRONMENT
            introduced rather than the author.  Test dtype.kind in "OU", or the
            dtype's name, never == object.
  1.22.0    a build compared against one carrying an EXTRA output column.  A
            release that ADDS a column cannot be verified by hashing the whole
            frame against the previous build: the frame is a column wider by
            construction, so the hash is guaranteed to differ and says nothing.
            All four cells reported DIFFER on a configuration later proved
            identical on 142 of 142 SHARED columns.  Hash the shared set and
            NAME it.
  1.22.0    a runtime ratio measured across a session rather than interleaved.
            The old build's cells were timed first and the new build's after,
            and the same all-flags-restored cell later re-measured 68 s against
            the 42 s that pass had recorded -- 1.6x drift on identical work, in
            the direction of the session clock.  The 1.4-2.0x "slowdown" it
            produced was published and retracted.  Interleave both builds in
            ONE process, as v1.17.4 and v1.17.6 did, or publish nothing.

Traps 9, 10, 11 and the pandas-3 dtype trap are four DIFFERENT causes of one
identical symptom: columns reported as DIFFER beside a byte-identical hash.
Each had to be found separately, because fixing one moved the count and nothing
else.  That is the argument for the whole file.

Each is defended against below, at the line that would otherwise reproduce it.
⚠️  AND THE RESET LIST IS PART OF THE CONTRACT, NOT HOUSEKEEPING.  Trap 12
was a config field that had no reset because nothing had ever varied it.  When
a release makes a config field something a cell can differ on, it belongs in
`run_cell`'s explicit resets, or the next harness inherits it.

Add to that list rather than starting a twelfth harness.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import io
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Local: the working-tree guard every harness here runs first.  It is a
# sibling file rather than a copied function because four harnesses need
# it and a second copy of a check is the defect this repo catalogues
# oftenest.
import tree_check

REPO = os.path.dirname(os.path.abspath(__file__))


# -----------------------------------------------------------------------------
# LOADING THE PIPELINE
# -----------------------------------------------------------------------------

# The launcher to name in a printed instruction.  `py` is the Windows launcher
# and does not exist anywhere else, so a hint that says it is wrong advice on
# the host that most needs the hint.  Not shared between files on purpose: the
# four modules must stay standalone for the Colab paste, and this is one
# expression, not a manifest.
_PY = "py" if os.name == "nt" else os.path.basename(sys.executable)

def load_master():
    """Import the built master.py in the one way the worker pool tolerates.

    MUST be `import master` by name with the repo on sys.path.  Loading it
    through spec_from_file_location("master", path) + exec_module works
    perfectly in serial and then fails in the pool: the module never lands in
    sys.modules under its own __name__, so _spawn_environment's `own` resolves
    to None, `pin` is False, and every worker executes THIS FILE as __main__
    instead -- that is, re-runs the whole verification once per worker.  The
    assert is what turns that into a failure rather than a mystery.
    """
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        import master as m
    assert sys.modules.get("master") is m and m.__spec__ is not None, (
        "master must be imported BY NAME with the repo on sys.path -- see "
        "_spawn_environment in calc.py"
    )
    return m


# -----------------------------------------------------------------------------
# CELLS
# -----------------------------------------------------------------------------
# The four cells every release in versions.md is verified on, at the caps it uses.
# Beneficiated cells run at 150 rows because they are ~4.7x raw (the ratio is
# master.MEASURED_CELL_SECONDS'; this comment is the only place verify.py
# restates it); raw at 400.
CELLS: Dict[str, Dict[str, Any]] = {
    "raw":          dict(use_beneficiation=False, optimise_programme_scale=False,
                         eval_row_cap=400),
    "raw+search":   dict(use_beneficiation=False, optimise_programme_scale=True,
                         eval_row_cap=400),
    "benef":        dict(use_beneficiation=True,  optimise_programme_scale=False,
                         eval_row_cap=150),
    "benef+search": dict(use_beneficiation=True,  optimise_programme_scale=True,
                         eval_row_cap=150),
}

# BOTH of these come out before hashing, and the second is the one that has
# already cost a release.  pipeline_version is obvious.  catalog_date is stamped
# from the wall clock, so a run that straddles midnight disagrees with itself --
# and a full beneficiated cell is ~10 h, so a full-catalog 2x2 CANNOT be run
# inside one calendar date.  Any comparison of those cells hits this.
PROVENANCE = ("pipeline_version", "catalog_date")

DESTINATION = "cislunar"      # what the on-disk Stage 2 catalog is priced for

# Where a harness-built cell is allowed to land.  See `run_cell`: the model
# WRITES its catalog as a side effect, and the live one is somebody's
# finished run rather than scratch space.
_SCRATCH = os.path.join(REPO, ".verify", "scratch")

# Config fields `run_cell` puts back to their declared default before every
# cell.  `CELLS` names four fields; anything a caller varies through
# `**override` and this list does not name is inherited by the NEXT cell in the
# same process.  See the trap note in `run_cell`.
RESET_FIELDS = (
    "market_model",              # v1.21.0
    "model_reliability",         # v1.22.0
    "model_learning_curve",      # v1.22.0
    "apply_wacc_compounding",    # v1.22.0
    "sell_surplus_at_discount",  # v1.22.0
    "surplus_price_fraction",    # v1.22.0
)


def _declared_default(config, field: str):
    """The dataclass DEFAULT for `field`, not whatever the instance now holds.

    `run_cell` mutates the live config, so "put it back" has to mean "back to
    what the class declares", and reading the instance would just return the
    value the previous cell left there.
    """
    for f in dataclasses.fields(type(config)):
        if f.name == field:
            return f.default
    raise AttributeError("no config field named %r" % field)


def run_cell(m, name: str, *, workers: int = 1, **override):
    """Build one profitability cell and return the frame.

    delivery_destination is set EXPLICITLY.  CALC_CONFIG defaults to
    earth_surface while the on-disk Stage 2 catalog is whatever destination was
    last built, so importing calc and calling straight off gives a mismatched
    run that prices the cargo at one place and pays to deliver it to another.
    destination_check() shouts on STDOUT -- exactly where a harness that filters
    output is least likely to be listening -- so the shout is asserted on rather
    than hoped for.
    """
    spec = dict(CELLS[name])
    spec.update(override)

    C = m.CALC_CONFIG
    # 🚨  AND THE CELL IS WRITTEN SOMEWHERE THE PIPELINE DOES NOT KEEP ITS
    # ANSWER.  `build_profitability_catalog` does not only RETURN a frame, it
    # writes `<output_dir>/profitability_catalog.csv` as a side effect -- so a
    # harness that leaves `output_dir` alone replaces the live Stage 4 catalog
    # with whatever capped cell it just built, every time it runs one.  This
    # file builds about twenty of them per `check`.
    #
    # What that costs is not the file, which regenerates, but the RUN behind
    # it: the catalog on disk after a campaign is a full-catalog cell that took
    # hours, and `campaign/worked_calculation.py` with no `--catalog`, the
    # dashboard, and `preflight()`'s destination test all read exactly that
    # file.  Overwriting it with a 400-row stride sample leaves every one of
    # them answering about the sample, and nothing says so.
    #
    # ⚠️  `input_dir` is a SEPARATE field and is deliberately not touched:
    # Stage 4 reads its ~868 MB of inputs through that one, and redirecting it
    # would make every cell here fail to load rather than fail to save.  This
    # is the narrowest possible redirection -- one field, one side effect.
    C.output_dir = _SCRATCH
    os.makedirs(_SCRATCH, exist_ok=True)
    C.delivery_destination    = DESTINATION
    C.eval_row_sampling       = "stride"
    C.parallel_workers        = workers
    C.prune_infeasible_combos = True
    # TRAP #13, and it is #1 in this file's header one field along.  `CELLS`
    # does not name `market_model`, so before calc v1.21.0 there was nothing to
    # reset and every field a cell cared about was in the spec.  There is now:
    # a harness that runs one cell with `market_model="elasticity"` and the
    # next with the plain default leaves the SECOND run in elasticity too,
    # because nothing here puts it back.  That is not hypothetical -- it
    # produced a `.verify` baseline labelled "the new default" that was
    # entirely elasticity, and the tell was a check reporting 66 bound rows
    # beside a frame whose minimum clearing was 1.0000.
    #
    # Read off the dataclass rather than typed, so the reset cannot drift from
    # the default the way a literal would; `--market-model` in run_pipeline.py
    # resolves its own default the same way and for the same reason.
    #
    # v1.22.0 adds four more for the same reason, and the rule is the one that
    # entry states: a field joins this list the moment a cell can DIFFER on
    # it.  All four are things a harness now A/Bs -- the release that flipped
    # them was itself verified by running each cell with them restored -- so
    # leaving them out would leak exactly the way `market_model` did.
    for _field in RESET_FIELDS:
        setattr(C, _field, _declared_default(C, _field))
    for k, v in spec.items():
        setattr(C, k, v)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        df = m.build_profitability_catalog(C)
    if "MISMATCH" in buf.getvalue():
        raise AssertionError(
            f"destination mismatch in cell {name!r}: the Stage 2 catalog on "
            f"disk is not priced for {DESTINATION}"
        )
    return df


# -----------------------------------------------------------------------------
# COMPARING TWO RUNS
# -----------------------------------------------------------------------------
def _comparable(df):
    """The frame with every provenance column removed.

    Column ORDER is left alone deliberately.  Sorting them would be tidier and
    would silently make every hash this file prints incomparable with the eight
    already committed in versions.md -- which is the whole point of printing one.
    """
    return df[[c for c in df.columns if c not in PROVENANCE]]


def _csv(df) -> str:
    """The canonical text a cell hashes to.

    The baseline stored on disk IS these bytes, so a hash comparison is a byte
    comparison of the file and needs no parsing at all -- which is why the hash
    is the authority here and the column diff is the diagnostic.

    to_csv writes floats at repr precision, so nothing is lost on the way OUT.
    Reading them back is the lossy direction: see _read_baseline.

    lineterminator is PINNED, and leaving it off is trap #12.  pandas defaults
    it to `os.linesep`, so this function returns CRLF text on Windows and LF
    text on Linux -- and the hash is taken over exactly this string.  Every
    cell hash in versions.md was computed on Windows, over CRLF, so the same
    build on Linux reproduces every float and still reports DIFFER on all four
    cells.  That is the eleven-entry table in this header happening a twelfth
    time: a broken comparator that looks exactly like a broken release.  CRLF
    is pinned rather than LF because CRLF is what the committed hashes are OF.
    """
    return _comparable(df).to_csv(index=False, lineterminator="\r\n")


def cell_hash(df) -> str:
    """First 16 hex digits of the sha256 of the cell's comparable CSV.

    Sixteen because that is the width every release note in versions.md quotes,
    and this harness reproduces the four hashes committed for v1.17.4 and
    v1.17.6 exactly. It goes through `_csv` / `_comparable`, which strips BOTH
    provenance columns and deliberately does NOT sort the remaining ones:
    sorting would be tidier and would silently make every hash printed here
    incomparable with the ones already on record.
    """
    return hashlib.sha256(_csv(df).encode("utf-8")).hexdigest()[:16]


def column_diff(a, b) -> Tuple[int, int, List[str]]:
    """(identical, compared, differing) over the shared non-provenance columns.

    Compared POSITIONALLY, via .to_numpy(), and that is not a detail.
    build_profitability_catalog returns its rows SORTED by the objective, so a
    live frame carries a scrambled index while the same frame re-read from CSV
    carries a fresh RangeIndex.  Comparing the two Series directly makes pandas
    align on the index LABEL, so nearly every float column reports as differing
    while the file hashes identical -- which is the ninth entry in this file's
    header, found by this very function on the run it was written for.  The
    hash said MATCH and the column diff said DIFFER, and the hash was right.

    Nulls are normalised to one spelling before comparing.  A parquet round trip
    renders a None in an object column back as nan, so a naive per-column
    astype(str) reports thrust_scaling, isru_feed_material and name as differing
    when they are identical -- v1.17.1 lost time to exactly that.
    """
    shared = [c for c in a.columns if c in b.columns and c not in PROVENANCE]
    differing = []
    for c in shared:
        x, y = a[c], b[c]
        if len(x) != len(y):
            differing.append(c)
            continue
        if x.dtype.kind == "f" and y.dtype.kind == "f":
            xv, yv = x.to_numpy(), y.to_numpy()
            same = bool(((xv == yv) | (_isnan(xv) & _isnan(yv))).all())
        else:
            same = _blanks(x) == _blanks(y)
        if not same:
            differing.append(c)
    return len(shared) - len(differing), len(shared), differing


def _blanks(s) -> list:
    """A column as a list with every spelling of "nothing here" collapsed to None.

    None, NaN and the EMPTY STRING all become None, and that last one is trap
    #11.  An all-empty object column written by to_csv is a run of bare commas,
    and read_csv types that column as float64-of-NaN -- so a live `""` comes
    back as `nan` and a naive comparison calls them different.  They are not:
    a CSV cannot represent the difference, so the file's own hash cannot see it
    either, and a comparator stricter than the artefact it compares reports
    failures that do not exist.  `payload_mix` and `payload_dominant_phase` are
    empty on every row of a raw cell and were the last two columns to fall.
    """
    return [None if (v is None or v != v or v == "") else v
            for v in s.to_numpy().tolist()]


def _isnan(v):
    """numpy's isnan, imported lazily so the module imports without pandas.

    Only ever called on a value already known to be a float, which is why there
    is no type guard: `math.isnan` would do as well here and numpy is already
    loaded by the time any comparison runs.
    """
    import numpy as np
    return np.isnan(v)


def _read_baseline(pd, path):
    """Read a baseline cell back WITHOUT losing the last bit of every float.

    float_precision="round_trip" is mandatory, and leaving it off is trap #10 in
    the header.  pandas' default C parser is a fast float reader that is NOT
    correctly rounded, so it returns a float64 one ULP away from the one that
    was written -- `119898.18458829961` comes back as `119898.1845882996`.
    Neither "high" nor the default round-trips; only "round_trip" does.

    That produced the same symptom as trap #9 and had to be diagnosed
    separately: 64 of 139 columns reported as DIFFER while all four cells
    hashed byte-identical to the baseline.  Same family as the pyarrow CSV
    engine v1.17.4 measured and rejected -- a different float parser rounding
    differently in the last ULP -- and the same lesson: a comparison is only as
    exact as the slackest step in it.

    NOTE this says nothing about the pipeline itself.  load_all_catalogs reads
    with the default parser too, so the model's inputs go through the same
    slightly-inexact reader on every run -- which is deterministic, and is
    therefore why bit-identity holds at all.  Do not "fix" that: changing
    float_precision there would move every number in the model.
    """
    return pd.read_csv(path, low_memory=False, float_precision="round_trip")


# -----------------------------------------------------------------------------
# THE FIVE CHECKS
# -----------------------------------------------------------------------------
def check_mass_ledger(m, frames: Dict[str, Any]) -> bool:
    """hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg.

    The rig is a CONFIG CONSTANT, not an output column.  The identity as
    CLAUDE.md states it raises KeyError if run verbatim against the CSV, which
    is what happened on v1.17.5's first attempt.
    """
    rig = m.CALC_CONFIG.mining_hardware_kg
    ok = True
    for name, df in frames.items():
        if df.empty:
            # Not "nothing to check" -- these cells evaluate 150-400 rows at
            # cislunar, so an empty one IS the regression. Passing quietly here
            # would hide it behind a check that looks like it ran.
            print(f"  {name:13s} NO ROWS -- the cell produced nothing  FAIL")
            ok = False
            continue
        err = float((df["hardware_total_kg"] - rig
                     - df["power_system_kg"] - df["ep_system_kg"]).abs().max())
        good = err < 1e-6
        ok &= good
        print(f"  {name:13s} max |error| {err:.9f} kg  {'OK' if good else 'FAIL'}")
    return ok


def _ratio(df):
    """The objective this project ranks on.

    There is no cost_revenue_ratio column.  Rank by
    total_cost_usd / gross_value_usd: ranking by profit_usd degenerates into a
    pure cost ranking, which is a delta-v table wearing a profit label.
    """
    return df["total_cost_usd"] / df["gross_value_usd"]


# Both never-worse comparisons join two cells on `designation`, so the two
# sides must be sampled at the SAME cap or the join is a subset of the smaller
# one and the counts mean nothing.  The bit-identity cells above deliberately
# do not share a cap (beneficiated is ~4.7x raw, so it runs at 150), which is why
# this check runs its own.  400 is the cap the committed figures use.
NEVER_WORSE_CAP = 400


def check_never_worse(m) -> bool:
    """Both invariants: beneficiated <= raw, and searched <= N = 1.

    "median improvement" is median(1 - searched/unsearched) -- the fractional
    REDUCTION in the ratio.  median(1/r - 1) is a different number for the same
    result (42.5% against 74.0%) and is not the convention the committed
    figures use.
    """
    cap = dict(eval_row_cap=NEVER_WORSE_CAP)
    side = {name: run_cell(m, name, **cap)
            for name in ("raw", "benef", "raw+search", "benef+search")}

    ok = True
    pairs = (("benef",        "raw",   "benef <= raw"),
             ("raw+search",   "raw",   "search <= N=1"),
             ("benef+search", "benef", "search <= N=1 (benef)"))
    for lo, hi, label in pairs:
        a, b = side[hi], side[lo]
        if a.empty or b.empty:
            which = "hi" if a.empty else "lo"
            print(f"  {label:22s} SKIPPED -- the {which} cell is empty  FAIL")
            ok = False
            continue
        j = (a[["designation"]].assign(r_hi=_ratio(a))
             .merge(b[["designation"]].assign(r_lo=_ratio(b)), on="designation"))
        if j.empty:
            print(f"  {label:22s} SKIPPED -- the two cells share no "
                  f"designation  FAIL")
            ok = False
            continue
        r = j["r_lo"] / j["r_hi"]
        worse = int((r > 1 + 1e-12).sum())
        ok &= worse == 0
        print(f"  {label:22s} pairs {len(j):5d} | max {r.max():.6f} | "
              f"worse {worse} | declined {int((r == 1.0).sum()):4d} | "
              f"median +{(1 - r).median() * 100:.1f}%")
    return ok


def check_market_cap(m) -> bool:
    """calc v1.21.0's invariants: a ceiling may only ever cost you (check 7).

    Two claims, and the first is the one worth having.

    ── CONSTRAINING MUST NEVER IMPROVE THE ANSWER ──────────────────────────
    `capacity_cap` clips each commodity at an allowance; `unbounded` is the
    same run with every allowance infinite.  For any FIXED programme the capped
    gross value is <= the uncapped one and the cost is identical, so the capped
    best-over-rungs can never beat the uncapped best-over-rungs.  The objective
    is cost/revenue, so capped >= unbounded, row by row.

    That is the mirror of check 5's argument and it catches the same class of
    bug.  Check 5 says widening a search must not make the reported answer
    worse; this says narrowing one must not make it better.  A violation means
    the ceilings are being applied to something other than what gets reported
    -- an allowance leaking into the cost side, or a rung priced under one set
    of caps and reported under another.

    ── AND THE COLUMNS MUST MEAN WHAT THEY SAY ────────────────────────────
    `saturation_multiplier` is a PRICE multiplier and must be exactly 1.0 in
    every model but `elasticity`; `market_clearing_fraction` is a share and
    must land in [0, 1] to within a tolerance the comment below earns;
    `unsold_payload_kg` and v1.22.0's `surplus_payload_kg` cannot be negative
    or exceed the payload, and must never both carry real mass on one row.
    Cheap, and it is what stops these columns quietly swapping meanings the way
    one overloaded column would have.
    """
    cap = dict(eval_row_cap=NEVER_WORSE_CAP)
    ok = True

    for name in ("raw+search", "benef+search"):
        capped = run_cell(m, name, market_model="capacity_cap", **cap)
        free   = run_cell(m, name, market_model="unbounded", **cap)
        if capped.empty or free.empty:
            print(f"  {name:14s} SKIPPED -- a cell came back empty  FAIL")
            ok = False
            continue
        j = (free[["designation"]].assign(r_free=_ratio(free))
             .merge(capped[["designation"]].assign(r_cap=_ratio(capped)),
                    on="designation"))
        if j.empty:
            print(f"  {name:14s} SKIPPED -- no shared designation  FAIL")
            ok = False
            continue
        # r_cap must be >= r_free: the ceiling can only ever cost you.
        r = j["r_free"] / j["r_cap"]
        better = int((r > 1 + 1e-9).sum())
        ok &= better == 0
        bound = int((capped["market_clearing_fraction"] < 1.0).sum())
        print(f"  {name:14s} pairs {len(j):5d} | max {r.max():.9f} | "
              f"cap beat unbounded on {better} | ceiling bound {bound} rows")

    for name in ("raw", "benef+search"):
        d = run_cell(m, name, market_model="capacity_cap", **cap)
        if d.empty:
            continue
        sat  = d["saturation_multiplier"]
        clr  = d["market_clearing_fraction"]
        uns  = d["unsold_payload_kg"]
        sur  = d["surplus_payload_kg"]
        # The clearing bound carries a TOLERANCE, and the first run of this
        # check is why.  It reported four rows "outside (0, 1]" whose value was
        # 1.0000000000000002: bodies where a ceiling binds by a hair, so the
        # reshape branch runs, the bounded knapsack re-walks to the same load,
        # and `cvalue / gross_base` lands one ULP over 1.0 because the walk
        # took a different route to the same answer.  Nothing in the model
        # moved.  That is trap #2 from this file's own header -- a comparator
        # stricter than the artefact it compares reports failures that do not
        # exist -- and it is the reason check 5 tests `r > 1 + 1e-12` rather
        # than `r > 1`.
        #
        # Zero IS admissible: a programme large enough that no commodity can be
        # placed sells nothing, which is the ceiling working rather than
        # failing.  It has not been observed at cislunar and would show as an
        # infinite cost/revenue ratio if it were.
        #
        # v1.22.0's two mass columns are EXCLUSIVE by construction: a kilogram
        # past a ceiling is either abandoned or discounted, never both, and
        # which one it is falls out of `sell_surplus_at_discount` for the whole
        # run.  Asserting it here is what stops the pair quietly collapsing
        # back into one overloaded column, which is the failure the two of them
        # exist to prevent.
        #
        # ⚠️  AND IT CARRIES A TOLERANCE, FOR THE SAME REASON THE CLEARING
        # BOUND ABOVE DOES.  On the beneficiated path `unsold` is a DIFFERENCE
        # OF TWO SUMS, the uncapped load's mass less the capped load's, and
        # with the surplus tier on those two are mathematically equal: the
        # allowance splits one phase's take across two tiers, and
        # `(x - a) + a` is not always `x` in floating point.  The first run of
        # this check found exactly that, on 2 of 158 rows, at
        # **3.638e-12 kg against a 24-tonne payload -- 1.5e-16 relative**, one
        # ULP.  A milligram floor is six orders of magnitude above the residue
        # and far below any mass this model can mean, and the alternative was
        # an epsilon inside the cost cascade, which this project does not do to
        # silence a checker.
        both = int(((uns > 1e-6) & (sur > 1e-6)).sum())
        bad  = {
            "saturation_multiplier != 1.0": int((sat != 1.0).sum()),
            "clearing outside [0, 1]":      int(((clr < 0) | (clr > 1 + 1e-9)).sum()),
            "unsold negative":              int((uns < 0).sum()),
            "unsold > payload":             int((uns > d["max_payload_kg"] + 1e-6).sum()),
            "surplus negative":             int((sur < 0).sum()),
            "surplus > payload":            int((sur > d["max_payload_kg"] + 1e-6).sum()),
            "unsold and surplus together":  both,
        }
        for label, n in bad.items():
            if n:
                print(f"  {name:14s} {label}: {n} rows  FAIL")
        ok &= not any(bad.values())
        print(f"  {name:14s} columns OK on {len(d)} rows")

    return ok


def check_stage2(m) -> bool:
    """Stage 2's judgement tables still produce the numbers on disk.

    Added after the second release running turned up an item the five Stage 4
    checks structurally could not see (transportation 1.12.1's propellant flag,
    then mineral_value 1.7.1's commodity classes).  Documenting that gap twice
    was the wrong answer; this closes it for the table half.

    Two things, and neither needs the network:

      RECOMPUTE.  Every row of the on-disk Stage 2 catalog, through the live
        `annual_market_kg` and `in_space_utility`, against the values stored in
        it.  This is the Stage 2 analogue of a four-cell hash: it is what says a
        judgement-table edit was inert, and it is the check to re-run after
        touching one.

      COVERAGE.  Which commodities fall through a silent default.  A name with
        no `_COMMODITY_CLASS` entry silently takes 15% of a destination's whole
        import budget; a name with no ANNUAL_WORLD_PRODUCTION_KG entry silently
        takes an UNLIMITED terrestrial market and can never saturate.  The
        first is now an import-time assert in the module, so it should always
        report zero; the second is reported because `nickel-iron` is a known,
        measured, deliberately-unfixed instance -- see CLAUDE.md.  A count that
        GROWS is the signal, not the count itself.
    """
    import pandas as pd

    path = os.path.join(m.MINERAL_CONFIG.output_dir,
                        m.MINERAL_CONFIG.catalog_filename)
    if not os.path.exists(path):
        print(f"  (no Stage 2 catalog at {path} -- skipped)")
        return True

    d = pd.read_csv(path, float_precision="round_trip")
    dest = str(d["delivery_destination"].iloc[0])
    bad = []
    for _, r in d.iterrows():
        name = str(r["name"])
        route = str(r["value_route"]) if pd.notna(r.get("value_route")) else None
        if float(r["annual_market_kg"]) != m.annual_market_kg(name, dest, route):
            bad.append((name, "annual_market_kg"))
        if "in_space_utility" in d.columns and \
                float(r["in_space_utility"]) != m.in_space_utility(name, dest):
            bad.append((name, "in_space_utility"))
    ok = not bad
    print(f"  recompute      {len(d):3d} rows at {dest:14s} "
          f"{'ALL IDENTICAL' if ok else str(len(bad)) + ' DIFFER: ' + str(bad[:4])}")

    names = {str(r["name"]) for r in m.MINERAL_REFERENCE}
    no_class = sorted(names - set(m._COMMODITY_CLASS))
    no_cap = sorted(n for n in names
                    if n not in m.ANNUAL_WORLD_PRODUCTION_KG)
    ok &= not no_class
    print(f"  unclassified   {len(no_class)} "
          f"{'(would silently take 15% of a depot) ' + str(no_class) if no_class else ''}")
    print(f"  uncapped       {len(no_cap)} take the unlimited terrestrial "
          f"default ({m._UNLIMITED_MARKET_KG:.0e} kg/yr)")

    # v1.21.2.  EVERY PHASE calc can put in a hold must resolve to a ceiling.
    # This is the defect v1.21.1 fixed, generalised so the next one cannot
    # happen: `asteroid_phase_table` appends the composition residual under a
    # name Stage 2 has no row for, `markets.get` missed, and it took the
    # infinite default -- priced, unbounded, and on 100% of bodies.  A phase
    # with no market is not a rounding error; under `capacity_cap` it is the
    # whole of a monotone-in-N objective.
    #
    # ⚠️  Tests the PHASE names, not the mineral names.  The block above checks
    # Stage 2's own rows, and the residual is not one of them -- which is
    # exactly how it slipped through for a release.
    markets = m.market_table(d)
    phase_names = set(m.FRACTION_TO_MINERAL.values()) | {m._RESIDUAL_PHASE}
    unbounded = sorted(p for p in phase_names
                       if m.phase_market_kg(markets, p) == float("inf"))
    ok &= not unbounded
    print(f"  phase ceilings {len(phase_names) - len(unbounded)}/{len(phase_names)} "
          f"payload phases resolve to a market"
          + (f"  *** UNBOUNDED: {unbounded} ***" if unbounded else ""))

    # And every phase's market KEY must name a real market, or the pooling in
    # `_capped_sale_value` and the knapsack caps would pool onto a key nothing
    # bounds.  Cheap, and it is the half an alias table can get wrong.
    stray = sorted(k for k in {m.phase_market_key(markets, p) for p in phase_names}
                   if markets is not None and k not in markets)
    ok &= not stray
    if stray:
        print(f"  phase ceilings *** alias points at no market: {stray} ***")
    return ok


def check_prune(m, names: List[str],
                already: Optional[Dict[str, Any]] = None) -> bool:
    """The pre-filter must agree with the unpruned search, column for column.

    Required after ANY change to _combo_can_close, _combo_close_terms,
    _closes_with, _closes_carrying_its_own_stage or anything they read.  Those
    are two statements of the same algebra, kept adjacent on purpose; this is
    the diff that says so when they drift apart.

    `already` lets check 1 hand over the prune-ON cells it has just built --
    they are the same run with the same config, so rebuilding them would be
    four more catalog loads for four identical frames.  The prune-OFF side is
    always built here, and it is the slow half anyway: turning the pre-filter
    off is what v1.14.1 and v1.17.4 exist to avoid.
    """
    already = already or {}
    ok = True
    for name in names:
        on = already.get(name)
        if on is None:
            on = run_cell(m, name)
        off = run_cell(m, name, prune_infeasible_combos=False)
        m.CALC_CONFIG.prune_infeasible_combos = True
        same, total, diff = column_diff(_comparable(on), _comparable(off))
        h1, h2 = cell_hash(on), cell_hash(off)
        good = (h1 == h2) and not diff
        ok &= good
        print(f"  {name:13s} {same}/{total} identical | {h1} vs {h2} | "
              f"{'MATCH' if good else 'DIFFER ' + ','.join(diff[:4])}")
    return ok


def check_parallel(m, names: List[str], workers: int = 8) -> bool:
    """Serial and parallel must be byte-identical.

    Required after any change to the search, and the check that catches a worker
    seeing different reference data from its parent -- module-level memos are
    PER PROCESS, and several are attached to the propellant and vehicle dicts
    that get pickled across the boundary.

    More workers is not always faster.  On a small cap the 862 MB catalog load
    and ~1.1 s per-worker startup dominate, and 8 workers regularly comes out
    SLOWER than serial.  The hash is what this check is for; the wall clock is
    not a result.
    """
    ok = True
    for name in names:
        t0 = time.perf_counter(); a = run_cell(m, name, workers=1)
        ta = time.perf_counter() - t0
        t0 = time.perf_counter(); b = run_cell(m, name, workers=workers)
        tb = time.perf_counter() - t0
        h1, h2 = cell_hash(a), cell_hash(b)
        good = h1 == h2
        ok &= good
        print(f"  {name:13s} serial {ta:6.1f}s | {workers}w {tb:6.1f}s | "
              f"{len(a):4d} rows | {h1} {'MATCH' if good else 'DIFFER'}")
    return ok


# -----------------------------------------------------------------------------
# BASELINE
# -----------------------------------------------------------------------------
# The paths whose content decides what a cell comes out as.  A baseline
# captured while any of these was modified may already contain the change it
# is supposed to predate, which is how check 1 comes to verify a change against
# itself and report MATCH.  Docs, harnesses and campaign scripts are NOT here:
# they cannot move a number, and failing on them would be the cry-wolf shape
# this repo records twice.
MODEL_PATHS = ("modules", "build_master.py", "master.py")


def _git(*args: str):
    """One git command in this repo, captured; None if git cannot answer.

    Never raises.  A tree with no git at all is a legitimate place to run this
    harness -- a Colab paste, an unpacked archive -- and the answer there is
    "no provenance", which the caller records honestly rather than failing on.
    """
    import subprocess
    try:
        r = subprocess.run(("git", "-C", REPO) + args, capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def _dirty_model_paths() -> Optional[List[str]]:
    """Files under MODEL_PATHS that differ from HEAD; None if git cannot say.

    🚨  `git diff`, NEVER `git status`, and on this working copy that is not a
    style preference.  CLAUDE.md's "Google Drive makes the tree look dirty"
    section documents Drive File Stream reporting a placeholder size of 16384
    bytes when git stats a file just after checkout: `status` then calls it
    modified WITHOUT READING IT, while `diff` compares content and shows
    nothing.  A provenance check built on `status` would therefore condemn
    every baseline taken on the reference machine, which is the one machine
    that takes them.
    """
    out = _git("diff", "--name-only", "HEAD", "--", *MODEL_PATHS)
    if out is None:
        return None
    return [line for line in out.splitlines() if line.strip()]


def _provenance() -> Dict[str, Any]:
    """What tree this baseline was taken on, recorded at capture time.

    `cmd_baseline` cannot fail and says so, but it can WRITE DOWN enough for
    `cmd_check` to fail later, which is the only point at which the question
    matters.  Nothing is derived at check time: a baseline is compared against
    the tree it was taken on, not the tree reading it.
    """
    dirty = _dirty_model_paths()
    return {
        "sha": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        # None means git could not answer, and [] means it answered "clean".
        # They are different facts and are kept apart on purpose: reading a
        # missing answer as a clean one is how an unverifiable baseline would
        # come to look like a good one.
        "dirty_model": dirty,
    }


def report_provenance(index: Dict[str, Any], allow_dirty: bool) -> bool:
    """Print where a baseline came from; False when it cannot support check 1.

    THE FAILURE THIS CATCHES.  `cmd_baseline`'s own docstring says to run it on
    a clean tree BEFORE the first edit, because "a baseline captured afterwards
    verifies a change against itself".  That was a documented discipline with
    nothing behind it, and its failure is silent in the worst way: check 1
    prints MATCH on all four cells and the release note then argues from a
    hash that compared the change to itself.

    Three outcomes, kept distinct for the reason `verify_stage3.py` keeps its
    three apart.  A baseline written before this field existed has no
    provenance and is reported as such rather than assumed good; a clean one is
    named; a baseline taken over a modified model path FAILS, and `--allow-
    dirty-baseline` is the escape for the case where the edit was unrelated.
    """
    meta = index.get("_meta", {})
    if "provenance" not in meta:
        print("  provenance   not recorded (baseline predates this field)")
        return True
    prov = meta["provenance"] or {}
    sha, branch = prov.get("sha"), prov.get("branch")
    where = "%s (%s)" % (sha[:12], branch) if sha else "unknown commit"
    dirty = prov.get("dirty_model")
    if dirty is None:
        print("  provenance   %s, tree state unknown (git could not answer)"
              % where)
        return True
    if not dirty:
        print("  provenance   %s, model paths clean" % where)
        return True
    print("  provenance   %s, and %d MODEL PATH(S) WERE MODIFIED when it was "
          "taken:" % (where, len(dirty)))
    for f in dirty[:8]:
        print("                 %s" % f)
    if len(dirty) > 8:
        print("                 ... and %d more" % (len(dirty) - 8))
    if allow_dirty:
        print("  provenance   --allow-dirty-baseline given; continuing")
        return True
    print("  *** THIS BASELINE MAY ALREADY CONTAIN THE CHANGE IT PREDATES.")
    print("      Check 1 would be comparing the change against itself, and it")
    print("      would print MATCH. Re-take it on a clean tree:")
    print("          %s verify.py baseline --tag <tag>" % _PY)
    print("      or pass --allow-dirty-baseline if the edit above is unrelated.")
    return False


def baseline_dir(tag: str) -> str:
    """Directory holding one tagged baseline, under .verify/.

    Tagged rather than single, so several can sit side by side: a release is
    checked against the tag it branched from, and `run.bat verify` picks the
    newest on disk rather than defaulting to one that may not exist.
    """
    return os.path.join(REPO, ".verify", f"baseline-{tag}")


def _cell_file(d: str, name: str) -> str:
    """Path of one baselined cell inside a baseline directory.

    `+` becomes `_` because two of the four cell names carry one
    (`raw+search`, `benef+search`) and it is not a portable filename character.
    """
    return os.path.join(d, name.replace("+", "_") + ".csv")


def cmd_baseline(args) -> int:
    """Build each cell and write it, plus an index.json of hashes, under .verify.

    RUN THIS ON A CLEAN TREE, BEFORE THE FIRST EDIT. It is not a check and
    cannot fail; the whole value of the file it writes is that it records what
    the code did before you touched it, so a baseline captured afterwards
    verifies a change against itself. `index.json` also stamps the destination
    and the calc version, which is what lets `check` print
    "calc 1.17.7 -> 1.17.8" rather than comparing two unnamed runs.
    """
    m = load_master()
    d = baseline_dir(args.tag)
    os.makedirs(d, exist_ok=True)
    index: Dict[str, Any] = {}
    print(f"\nBaseline -> {d}\n")
    for name in args.cells:
        t0 = time.perf_counter()
        df = run_cell(m, name)
        text = _csv(df)
        with open(_cell_file(d, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        index[name] = {"sha16": h, "rows": int(len(df)),
                       "cap": CELLS[name]["eval_row_cap"]}
        print(f"  {name:13s} {len(df):4d} rows | {h} | "
              f"{time.perf_counter() - t0:5.1f}s")
    index["_meta"] = {"destination": DESTINATION,
                      "calc_version": m.CALC_CONFIG.pipeline_version,
                      # Recorded HERE rather than derived at check time: the
                      # question is what tree this was taken on, and by the
                      # time anything reads it that tree is gone.
                      "provenance": _provenance()}
    with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
    print(f"\nWrote {len(args.cells)} cells at calc "
          f"{index['_meta']['calc_version']}")
    # Said at capture as well as at check.  A baseline taken over a modified
    # model path is recoverable in the ten seconds after it is written and
    # expensive an hour later, when four cells have already printed MATCH.
    report_provenance(index, allow_dirty=True)
    return 0


def cmd_check(args) -> int:
    """Every check against a baseline, most-important first.

    The count is deliberately not spelled out: this docstring said SIX from
    the day check 7 landed, while `cmd_invariants` ten lines below said "4 to
    7" correctly, so one file disagreed with itself about its own size. Read
    the numbered sections the run prints.

    Check 1 is the one with a prerequisite, and its failure mode is the reason
    this function tracks `unchecked` rather than just `ok`: a cell absent from
    the baseline used to `continue` without touching `ok`, so a run against a
    missing or partial baseline printed hashes, compared NOTHING, and finished
    with ALL CHECKS PASSED. It now returns 1 and names the cells. **A check
    that cannot run must never say it passed.**

    Checks 2 and 3 are the slow half and are what `--skip prune parallel`
    turns off for the ~5 minute loop; 4 to 7 need no baseline and are also
    available on their own as `invariants`.

    The working-tree guard in `main()` runs before any of them and is not
    numbered, because it is a precondition rather than a check on the model:
    it asks whether this disk is serving what git holds. See tree_check.py.
    """
    import pandas as pd

    m = load_master()
    d = baseline_dir(args.tag)
    index: Dict[str, Any] = {}
    if os.path.isfile(os.path.join(d, "index.json")):
        with open(os.path.join(d, "index.json"), encoding="utf-8") as f:
            index = json.load(f)
    else:
        print(f"\n(no baseline at {d} -- check 1 will only report hashes)")

    ok = True
    # Cells check 1 could not compare. Tracked, because "not in baseline" used
    # to `continue` without touching `ok` -- so a check run against a missing
    # or partial baseline printed hashes, compared nothing, and finished with
    # ALL CHECKS PASSED. A verification that cannot run must never report that
    # it passed; that is worse than not running it at all.
    unchecked: List[str] = []
    frames: Dict[str, Any] = {}

    was = index.get("_meta", {}).get("calc_version", "?")
    print(f"\n1. BIT-IDENTITY vs baseline "
          f"(calc {was} -> {m.CALC_CONFIG.pipeline_version})")
    # Tracked separately from `ok` and reported beside `unchecked` below,
    # because it is the same kind of finding: not "a number moved" but "check 1
    # could not answer the question it appears to have answered".
    trustworthy = True
    if index:
        trustworthy = report_provenance(index, args.allow_dirty_baseline)
    for name in args.cells:
        df = run_cell(m, name)
        frames[name] = df
        h = cell_hash(df)
        if name not in index:
            print(f"  {name:13s} {len(df):4d} rows | {h} | NOT COMPARED "
                  f"(absent from baseline)")
            unchecked.append(name)
            continue
        old = _read_baseline(pd, _cell_file(d, name))
        same, total, diff = column_diff(_comparable(df), old)
        good = (h == index[name]["sha16"]) and not diff
        ok &= good
        print(f"  {name:13s} {same}/{total} identical | {h} | "
              f"{'MATCH' if good else 'DIFFER ' + ','.join(diff[:4])}")

    print("\n2. PRUNE ON vs OFF")
    if "prune" in args.skip:
        print("  (skipped)")
    else:
        ok &= check_prune(m, args.cells, already=frames)

    print("\n3. SERIAL vs PARALLEL")
    if "parallel" in args.skip:
        print("  (skipped)")
    else:
        searched = [c for c in args.cells if "search" in c]
        ok &= check_parallel(m, searched or args.cells[:1])

    print("\n4. MASS LEDGER")
    ok &= check_mass_ledger(m, frames)

    print("\n5. NEVER-WORSE")
    ok &= check_never_worse(m)

    print("\n6. STAGE 2 TABLES")
    ok &= check_stage2(m)

    # v1.21.2: check 7 used to run ONLY from `verify.py invariants`, so the
    # command every release is argued from -- this one -- never ran the market
    # ceiling invariant at all.  Nothing hid it; it was simply not in the list,
    # and the one release note that quotes a check 7 result got it by running
    # the other subcommand by hand.  Same shape as this repo's other
    # never-ran-at-all checks: the output looked complete because the numbering
    # stopped where the list did.
    print("\n7. MARKET CEILINGS")
    ok &= check_market_cap(m)

    if unchecked:
        print("\n*** NOT VERIFIED: check 1 compared nothing for %s."
              % ", ".join(unchecked))
        print("    Build a baseline on a CLEAN tree BEFORE editing:")
        print("        %s verify.py baseline --tag %s" % (_PY, args.tag))
        return 1
    if not trustworthy:
        print("\n*** NOT VERIFIED: the baseline was taken over a modified "
              "model path, so check 1 cannot mean what it says. See above.")
        return 1
    print("\n" + ("ALL CHECKS PASSED" if ok else "*** FAILURES ABOVE ***"))
    return 0 if ok else 1


def cmd_invariants(args) -> int:
    """Checks 4 to 7 only -- no baseline needed, so this runs on any tree."""
    m = load_master()
    frames = {name: run_cell(m, name) for name in args.cells}
    print("\n4. MASS LEDGER")
    ok = check_mass_ledger(m, frames)
    print("\n5. NEVER-WORSE")
    ok &= check_never_worse(m)
    print("\n6. STAGE 2 TABLES")
    ok &= check_stage2(m)
    print("\n7. MARKET CEILINGS (calc v1.21.0)")
    ok &= check_market_cap(m)
    print("\n" + ("OK" if ok else "*** FAILURES ABOVE ***"))
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    """Dispatch `baseline` / `check` / `invariants`; returns the exit code.

    `--cells` and `--skip` exist for the edit loop rather than for a release:
    a release runs everything, and a verification you will not run is worse
    than a slow one.
    """
    p = argparse.ArgumentParser(
        description="Release verification harness (see the module docstring).")
    p.add_argument("command", choices=("baseline", "check", "invariants"))
    p.add_argument("--tag", default="head",
                   help="baseline name under .verify/ (default: head)")
    p.add_argument("--cells", nargs="+", default=list(CELLS),
                   choices=list(CELLS), metavar="CELL",
                   help="subset of: " + ", ".join(CELLS))
    p.add_argument("--skip", nargs="*", default=[], choices=("prune", "parallel"),
                   help="checks to skip while iterating")
    # The escape, and it is deliberately not a `--skip` value: those turn off a
    # check that would otherwise run, where this asserts something about the
    # baseline that the harness cannot see for itself -- that the model paths
    # modified when it was taken are unrelated to the change being verified.
    # Only the person who made the edit knows that, so it has to be said out
    # loud rather than defaulted.
    p.add_argument("--allow-dirty-baseline", action="store_true",
                   help="proceed even though the baseline was captured over a "
                        "modified modules/ or build_master.py (say so only if "
                        "that edit is unrelated to what you are verifying)")
    args = p.parse_args(argv)

    # Before any of the three, and it gates ALL of them including `baseline`:
    # a baseline captured off a tree that is not serving what git holds is a
    # poisoned reference that every later `check` is measured against, which is
    # the most expensive version of this failure rather than the cheapest.
    # It costs about half a second for the whole tree.  See tree_check.py.
    if not tree_check.assert_tree():
        print("")
        print("*** NOT VERIFIED *** - the working tree is not what "
              "git holds")
        return 1

    return {"baseline": cmd_baseline,
            "check": cmd_check,
            "invariants": cmd_invariants}[args.command](args)


if __name__ == "__main__":
    # The guard is load-bearing: check 3 starts a process pool, and on Windows a
    # worker rebuilds the parent by importing __main__.
    raise SystemExit(main())
