# -*- coding: utf-8 -*-
"""Stage 3 verification: the adapter and the package it drives still agree.

    py verify_stage3.py

WHY THIS FILE EXISTS.  Stage 3's reference tables moved out of this repo into
`spacecost`, an independent package, and `modules/transportation.py` is now the
adapter that drives it.  That is a split, and this project has run that
experiment before: it was briefly developed in two places at once and `1.0.6`,
`1.1.4` and `1.3.6` each shipped as two different things.  See "the
parallel-repo divergence" in versions.md.

What made that incident expensive was not the split, it was that **nothing
checked it**.  So the split is arranged to make drift impossible to commit
rather than merely unlikely:

    the DATA           single-sourced.  There is one copy of every reference
                       row, in spacecost, and this repo holds none
    the DIALS          mirrored, ten fields, and asserted at import time by
                       `_check_config_surface()` in the adapter, which raises
                       rather than warns
    the OUTPUT         checked here, byte for byte

⚠️  `verify.py` DOES NOT COVER THIS.  Its own header says so: checks 1-5 cover
Stage 4 and check 6 covers Stage 2's judgement tables, and "if you change Stage
1, 2 or 3, this file is not your evidence".  That gap is exactly what this file
fills, and it is why it is a separate script rather than a seventh check.

⚠️  IT NEVER TOUCHES THE REAL PIPELINE DIRECTORY.  Everything is built into a
temporary directory.  Running Stage 3 against `asteroid_pipeline/` would
re-fetch live fuel prices and overwrite the only copy of the catalogs every
`.verify` baseline was measured against -- the mistake CLAUDE.md documents
under "RUNNING STAGE 2 OR STAGE 3 DESTROYS EVERY BASELINE YOU HOLD".  This
script also passes `use_yfinance=False` so it needs no network and is
deterministic, and pins `catalog_date` so midnight cannot read as a defect.

WHAT A FAILURE MEANS.  Not "spacecost is broken".  Either the package moved a
row and this repo has not caught up, or the adapter is no longer passing the
settings through faithfully.  The report says which.
"""

import dataclasses
import hashlib
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.abspath(__file__))

# The stamp both sides are pinned to. `catalog_date` is a PROVENANCE column,
# not a model value, and comparing two builds without pinning it is how a
# release once read as a defect confined to the beneficiation path when the
# whole difference was that midnight had fallen mid-run.
PINNED_DATE = "2026-09-07"

TABLES = ["launch_vehicles.csv", "propellants.csv", "delta_v_segments.csv",
          "operational_costs.csv", "storage_systems.csv"]
SUMMARY = "transportation_summary.csv"


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _load_adapter():
    """Import Stage 3 the way the pipeline does, but pointed at scratch.

    The env var is set BEFORE the import because the module resolves its
    default output directory at import time. Without that, importing it would
    create `asteroid_pipeline/transportation/` as a side effect.
    """
    tmp = tempfile.mkdtemp(prefix="verify_stage3_")
    os.environ["ASTEROID_PIPELINE_OUTPUT_DIR"] = tmp
    sys.path.insert(0, os.path.join(REPO, "modules"))
    import transportation as t
    if "verify_stage3_" not in t.CONFIG.output_dir:
        raise SystemExit(
            "REFUSING TO RUN: Stage 3 resolved its output to\n"
            "    %s\n"
            "which is not the temporary directory this script created. Running "
            "it there would re-fetch live prices and overwrite the catalogs "
            "every .verify baseline was measured against." % t.CONFIG.output_dir)
    return t, tmp


def check_config_surface(t) -> bool:
    """The ten dials this repo owns still match the ones the package accepts."""
    import spacecost
    mine = {f.name for f in dataclasses.fields(t.TransportConfig)}
    theirs = {f.name for f in dataclasses.fields(spacecost.SpacecostConfig)}
    ok = mine == theirs
    print("1. config      %d dials, %s" % (
        len(mine), "identical on both sides" if ok else "*** DRIFTED ***"))
    if not ok:
        print("     only in economicspace : %s" % sorted(mine - theirs))
        print("     only in spacecost     : %s" % sorted(theirs - mine))
    return ok


def check_data_contract(t) -> bool:
    """The stamp this repo writes is the package's data-contract version.

    They are the same number on purpose: the stamp identifies the DATA, and the
    data is the package's. If they diverge, a catalog would be stamped with a
    version that does not describe the tables inside it.
    """
    import spacecost
    ok = t.CONFIG.pipeline_version == spacecost.DATA_VERSION
    print("2. contract    stamp %s, spacecost data contract %s  %s" % (
        t.CONFIG.pipeline_version, spacecost.DATA_VERSION,
        "" if ok else "*** MISMATCH ***"))
    return ok


def check_output(t, tmp) -> bool:
    """The adapter's six CSVs, byte for byte, against the package's own.

    Both are built here rather than one being read off disk, because the point
    is that the ADAPTER adds nothing and loses nothing on the way through.
    """
    import spacecost

    via_adapter = os.path.join(tmp, "adapter")
    cfg = t.TransportConfig(output_dir=via_adapter, use_yfinance=False)
    # The adapter has no catalog_date argument -- it is Stage 3's public
    # signature and gains nothing from one -- so the environment pins the
    # clock instead, and the package side is pinned to the same value.
    _quiet_build(lambda: t.build_transportation_catalog(cfg))
    a_dir = os.path.join(via_adapter, cfg.subdir)

    via_package = os.path.join(tmp, "package")
    scfg = spacecost.SpacecostConfig(output_dir=via_package, use_yfinance=False)
    _quiet_build(lambda: spacecost.build_catalog(scfg, catalog_date=PINNED_DATE))
    p_dir = scfg.table_dir()

    ok = True
    for name in TABLES + [SUMMARY]:
        a, b = _sha(os.path.join(a_dir, name)), _sha(os.path.join(p_dir, name))
        same = a == b
        ok = ok and same
        print("     %-30s %s  %s" % (name, a[:16],
                                     "match" if same else "*** DIFFER ***"))
    print("3. output      %s" % ("six files byte-identical through both paths"
                                 if ok else "*** THE ADAPTER CHANGES THE DATA ***"))
    return ok


def check_against_committed_reference(t, tmp) -> bool:
    """The five tables against the CSVs spacecost commits under `reference/`.

    This is the half that pins the CONTENT rather than the plumbing: check 3
    would still pass if both sides moved together. Skipped, with a message,
    when spacecost is installed from a wheel that carries no `reference/`
    directory -- a skip that says so is not a pass.
    """
    import spacecost
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(spacecost.__file__)))
    ref = os.path.join(pkg_root, "reference")
    if not os.path.isdir(ref):
        print("4. reference   SKIPPED, spacecost installed without reference/ "
              "(%s)" % pkg_root)
        return True

    built = os.path.join(tmp, "adapter", "transportation")
    ok = True
    for name in TABLES:
        want = os.path.join(ref, name)
        if not os.path.exists(want):
            continue
        same = _sha(os.path.join(built, name)) == _sha(want)
        ok = ok and same
        if not same:
            print("     %-30s *** DIFFERS from spacecost reference/ ***" % name)
    print("4. reference   %s" % ("five tables match spacecost's committed CSVs"
                                 if ok else "*** CONTENT MOVED ***"))
    return ok


def _quiet_build(fn):
    """Run a build with its progress output discarded."""
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        return fn()


def main() -> int:
    print("=" * 70)
    print("  STAGE 3 VERIFICATION  -  economicspace adapter vs spacecost")
    print("=" * 70)
    t, tmp = _load_adapter()
    import spacecost
    print("  spacecost %s, data contract %s" % (spacecost.__version__,
                                                spacecost.DATA_VERSION))
    print("  scratch   %s" % tmp)
    print("-" * 70)

    results = [
        check_config_surface(t),
        check_data_contract(t),
        check_output(t, tmp),
        check_against_committed_reference(t, tmp),
    ]
    print("-" * 70)
    if all(results):
        print("  OK  STAGE 3 VERIFIED - the split has not drifted")
        return 0
    print("  *** NOT VERIFIED *** - see the failing check above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
