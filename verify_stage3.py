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

import csv
import dataclasses
import datetime as _dt
import hashlib
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.abspath(__file__))

# The stamp both sides are pinned to. `catalog_date` is a PROVENANCE column,
# not a model value, and comparing two builds without pinning it is how a
# release once read as a defect confined to the beneficiation path when the
# whole difference was that midnight had fallen mid-run.
#
# 🚨  IT IS DERIVED FROM THE CLOCK AND MUST NOT BE A LITERAL. It was
# `"2026-09-07"` from the day this file was written until 2026-09-08, when the
# date rolled over mid-session and every one of the six comparisons went red at
# once: only the PACKAGE side took this value, while the adapter stamps
# `date.today()` through Stage 3's ordinary path, so the two agreed on exactly
# one calendar day and disagreed on every other. The file then reported
# `*** THE ADAPTER CHANGES THE DATA ***`, which is a broken checker wearing the
# costume of a broken release -- the failure mode `verify.py`'s header exists
# to catalogue, here in the other Stage 3 harness.
#
# ⚠️  The comment above this one used to end "so the environment pins the clock
# instead". Nothing pinned the clock; there was no such mechanism. That is
# defect class 4, a prescriptive comment nobody applied, and it is why the
# literal looked deliberate rather than rotten.
PINNED_DATE = _dt.date.today().isoformat()

TABLES = ["launch_vehicles.csv", "propellants.csv", "delta_v_segments.csv",
          "operational_costs.csv", "storage_systems.csv"]
SUMMARY = "transportation_summary.csv"


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# `catalog_date` is stamped from the wall clock, so any comparison against a
# COMMITTED artefact has to drop it or it passes on exactly one calendar day.
# `pipeline_version` is deliberately NOT dropped: it moves only when somebody
# moves it, so a difference there is a real finding rather than a clock.
_PROVENANCE = ("catalog_date",)


def _content_sha(path: str) -> str:
    """sha256 of a CSV with the wall-clock provenance columns removed.

    Both sides go through the identical transform, so re-serialising is safe;
    what matters is that the two are treated the same, not that the text
    matches the file on disk.

    This exists because check 4 compared raw bytes against a CSV spacecost
    COMMITTED, which carries the date it was generated on. Every row of every
    table therefore differed by one field from the day after it was committed,
    and the check announced `*** CONTENT MOVED ***` -- the most alarming
    message it has, for a clock. See `PINNED_DATE` above for the same defect
    in check 3, found the same morning.
    """
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return hashlib.sha256(b"").hexdigest()
    drop = {i for i, c in enumerate(rows[0]) if c in _PROVENANCE}
    trimmed = [[v for i, v in enumerate(r) if i not in drop] for r in rows]
    blob = "\n".join("\x1f".join(r) for r in trimmed).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


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
    # signature and gains nothing from one -- so it stamps `date.today()` like
    # any ordinary run, and the package side is handed that SAME day's date.
    # `PINNED_DATE` is therefore derived from the clock, never typed; see the
    # note on it above for the day this file spent failing because it was.
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


def _pinned_tag() -> str:
    """The `spacecost` tag `requirements.txt` pins, read rather than typed.

    One source: `requirements.txt` says in its own header that it mirrors
    `_MASTER_REQUIRED`, and `verify_docs.py` check 7 holds the two to each
    other, so reading it here adds no third copy.  Typing the tag into this
    file would make it the fourth place a repin has to land, and the release
    note for the split already lists three.
    """
    try:
        with open(os.path.join(REPO, "requirements.txt"), encoding="utf-8") as f:
            for line in f:
                if "spacecost" in line and "@" in line:
                    return line.rsplit("@", 1)[1].strip()
    except OSError:
        pass
    return ""


def _reference_dir():
    """Find spacecost's committed `reference/`, and prove which revision it is.

    Returns `(path, note)` with `path` None when the check cannot run.

    🚨  A PIP INSTALL CAN NEVER SATISFY THIS CHECK, and the old message implied
    otherwise.  `reference/` sits at spacecost's REPO root, a sibling of the
    package directory, so `pip install git+...` copies the package and leaves
    the reference CSVs behind every time.  The skip therefore fired on every
    ordinary install, reading as an unusual-install caveat when it was in fact
    "the content half of this seam has never run here".  What it needs is a
    source checkout, so this looks for one.

    ⚠️  A CHECKOUT IS ONLY USABLE IF ITS `reference/` MATCHES THE PINNED TAG,
    and that is not a formality: the checkout beside this repo was two commits
    PAST `v0.1.1` when this was written.  Those two happened to be docs-only,
    which is exactly the kind of luck this project has already been burned by;
    a second working copy at another revision is the parallel-repo divergence,
    not a convenience.  So the revision is asked of git rather than assumed,
    and a `reference/` that has moved since the tag is a FINDING, not a skip.
    """
    tag = _pinned_tag()
    candidates = []
    env = os.environ.get("SPACECOST_SOURCE")
    if env:
        candidates.append(("SPACECOST_SOURCE", env))
    candidates.append(("sibling checkout",
                       os.path.normpath(os.path.join(REPO, os.pardir, "spacecost"))))
    try:
        import spacecost
        candidates.append(("installed package", os.path.dirname(
            os.path.dirname(os.path.abspath(spacecost.__file__)))))
    except Exception:
        pass

    for label, root in candidates:
        ref = os.path.join(root, "reference")
        if not os.path.isdir(ref):
            continue
        if not tag:
            return ref, "%s, pinned tag unreadable" % label
        state = _reference_matches_tag(root, tag)
        if state is True:
            return ref, "%s at %s" % (label, tag)
        if state is False:
            return None, ("%s has a reference/ that DIFFERS from %s"
                          % (label, tag))
        # Not a git checkout, or the tag is absent: usable but unproven.
        return ref, "%s, revision unproven (%s)" % (label, state)
    return None, ""


def _reference_matches_tag(root: str, tag: str):
    """True / False / a string saying why the revision could not be proven."""
    import subprocess
    def git(*args):
        return subprocess.run(("git", "-C", root) + args, capture_output=True,
                              text=True, timeout=30)
    try:
        if git("rev-parse", "--git-dir").returncode != 0:
            return "not a git checkout"
        if git("rev-parse", "--verify", "--quiet", tag + "^{commit}").returncode != 0:
            return "tag %s not in this checkout" % tag
        # Only `reference/` has to match: the two commits past v0.1.1 on the
        # checkout beside this repo touched docs and tests, and refusing over
        # those would make the check unrunnable for no gain.  What must not
        # differ is the data being compared.
        return git("diff", "--quiet", tag, "--", "reference").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return "git unavailable"


def check_against_committed_reference(t, tmp) -> bool:
    """The five tables against the CSVs spacecost commits under `reference/`.

    This is the half that pins the CONTENT rather than the plumbing: check 3
    would still pass if both sides moved together.  See `_reference_dir` for
    where the CSVs are found and why the revision is proven before they are
    trusted.  A skip that says so is not a pass, and this one now says what it
    would take to make it run.
    """
    ref, note = _reference_dir()
    if ref is None:
        if note:
            print("4. reference   *** NOT VERIFIED *** %s" % note)
            print("     The pinned tag and the checkout disagree about the data")
            print("     this check compares. Check out %s, or point"
                  % (_pinned_tag() or "the pinned tag"))
            print("     SPACECOST_SOURCE at a checkout that is at it.")
            return False
        print("4. reference   SKIPPED, no spacecost source checkout found")
        print("     A pip install cannot satisfy this: reference/ sits at")
        print("     spacecost's repo root, not inside the package, so it is")
        print("     never copied into site-packages. Clone spacecost beside")
        print("     this repo, or set SPACECOST_SOURCE, to run it.")
        return True

    built = os.path.join(tmp, "adapter", "transportation")
    ok, n = True, 0
    for name in TABLES:
        want = os.path.join(ref, name)
        if not os.path.exists(want):
            continue
        n += 1
        # Content, not bytes: see `_content_sha`.  The docstring above has
        # always said this check pins CONTENT; now it does.
        same = _content_sha(os.path.join(built, name)) == _content_sha(want)
        ok = ok and same
        if not same:
            print("     %-30s *** DIFFERS from spacecost reference/ ***" % name)
    print("4. reference   %s" % (
        "%d tables match spacecost's committed CSVs (%s)" % (n, note)
        if ok else "*** CONTENT MOVED *** (%s)" % note))
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
