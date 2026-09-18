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
    the BEHAVIOUR      `validate`'s sanity bands, against the one defect they
                       are known to have had (check 5)

⚠️  `verify.py` DOES NOT COVER THIS.  Its own header says so: checks 1-5 cover
Stage 4 and check 6 covers Stage 2's judgement tables, and "if you change Stage
1, 2 or 3, this file is not your evidence".  That gap is exactly what this file
fills, and it is why it is a separate script rather than a seventh check.

✅  CHECK 5 CLOSES THE NAMED HALF OF THAT GAP.  `verify.py`'s header does not
merely say Stage 3 is uncovered, it names the item: transportation 1.12.1's
propellant-flag fix, which "had to be checked by running that function under
`-W error::FutureWarning` instead".  That was a one-off run by hand, and the
code it checks has since moved into `spacecost`, so nothing in either repo was
holding it.  It is a check now.  What is still uncovered is Stage 1's
derivation chain, which has no harness anywhere.

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

import contextlib
import csv
import dataclasses
import datetime as _dt
import hashlib
import io
import os
import sys
import tempfile
import warnings

# Local: the working-tree guard every harness here runs first.  It is a
# sibling file rather than a copied function because four harnesses need
# it and a second copy of a check is the defect this repo catalogues
# oftenest.
import tree_check

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

# ⚠️  A TABLE MISSING FROM THIS LIST IS A TABLE NOTHING COMPARES, and nothing
# says so: checks 3 and 4 walk it, so an omission makes a count quietly smaller
# rather than making anything red.  `environments.csv` arrived with the v1.15.0
# contract (spacecost v0.2.0) and is the first row added here since the split.
TABLES = ["launch_vehicles.csv", "propellants.csv", "delta_v_segments.csv",
          "operational_costs.csv", "storage_systems.csv", "environments.csv"]
SUMMARY = "transportation_summary.csv"


def _sha(path: str) -> str:
    """Hash of a file's RAW bytes, provenance columns included.

    The counterpart to `_content_sha`, and the difference between them is the
    whole of check 3 against check 4.  Check 3 compares two files this run
    built moments apart, so every column including `catalog_date` must agree
    and a raw hash is the strictest thing to compare.  Check 4 compares against
    a file COMMITTED on some other day, where the stamp is guaranteed to differ
    and says nothing, so it drops it first.  Using this one there is how that
    check spent a day reporting `*** CONTENT MOVED ***` at a clock.
    """
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
    """The adapter's CSVs, byte for byte, against the package's own.

    The count is DERIVED from `TABLES`, never spelled: it read "six" from the
    split until the v1.15.0 contract made it seven, which is this repo's
    standing failure mode arriving inside a checker.

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
    print("3. output      %s" % ("%d files byte-identical through both paths"
                                 % (len(TABLES) + 1)
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
        """One git command inside `root`, captured rather than printed.

        `-C root` rather than a `cwd` change: this runs inside a checkout that
        is NOT this repo, and leaving the process directory where it was means
        a caller added later cannot inherit a surprise.  Never raises on a
        non-zero exit; every caller reads `.returncode` itself, because "the
        tag is not here" is an ANSWER this check reports rather than an error.
        """
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
    """The reference tables against the CSVs spacecost commits there.

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
    ok, n, unheld = True, 0, []
    for name in TABLES:
        want = os.path.join(ref, name)
        if not os.path.exists(want):
            # ⚠️  NOT A SILENT CONTINUE.  A table the pinned tag does not commit
            # is a table this check does not cover, and the only symptom used to
            # be a smaller `n` -- the "count that is quietly smaller" shape this
            # repo has already been caught by once, in `verify_docs.py`'s file
            # enumeration.  It is legitimate (an older tag predates a table), so
            # it is reported rather than failed.
            unheld.append(name)
            continue
        n += 1
        # Content, not bytes: see `_content_sha`.  The docstring above has
        # always said this check pins CONTENT; now it does.
        same = _content_sha(os.path.join(built, name)) == _content_sha(want)
        ok = ok and same
        if not same:
            print("     %-30s *** DIFFERS from spacecost reference/ ***" % name)
    if unheld:
        print("     %d table(s) not committed under reference/ at this tag, so "
              "NOT compared: %s" % (len(unheld), ", ".join(unheld)))
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


# A name no real propellant can collide with. It is searched for in the report
# text rather than counted against a row total, so a table that grows a row
# cannot move the answer.
PROBE_NAME = "__verify_stage3_missing_flag_probe__"


def _probe_row(columns, flagless: bool) -> dict:
    """One synthetic propellant: implausible Isp, flag present or absent.

    Isp 5 s is below `validate`'s 40 s floor, so a row that REACHES the band is
    warned about and a row excluded from it is silent. That is the observable
    this check turns the flag question into: `has_mass_ratio` is a local inside
    `validate` and cannot be read from here, but whether the band still covers
    the row can be.
    """
    import numpy as np
    row = {c: np.nan for c in columns}
    row.update(name=PROBE_NAME, type="chemical", status="concept", trl=1,
               isp_vac_s=5.0, cost_usd_per_kg=1.0,
               density_kg_per_L=1.0, tank_kg_per_L=0.05)
    if not flagless:
        row["propellantless"] = False
    return row


def _validate_report(spacecost, launch, prop, dv, ops) -> str:
    """`validate`'s printed output, with FutureWarning promoted to an error.

    The promotion is half the check. transportation 1.12.1 rejected
    `.fillna(False).astype(bool)` because pandas raises `FutureWarning:
    Downcasting object dtype arrays on .fillna is deprecated` on an object
    column -- that is, the rejected fix would warn EXACTLY when it fired, on a
    row like this probe. An edit that reaches for it again passes a silent run
    and fails here.
    """
    buf = io.StringIO()
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        with contextlib.redirect_stdout(buf):
            spacecost.validate_tables(launch, prop, dv, ops)
    return buf.getvalue()


def _probe_still_discriminates(prop) -> bool:
    """True when the two spellings of `has_mass_ratio` disagree on the probe.

    THE PROBE HAS TO BE ABLE TO FAIL. It detects the 1.12.1 regression only
    while `~col.astype(bool)` and `col.ne(True)` actually differ on a missing
    flag: the first reads NaN as True and drops the row, the second reads it as
    "has a mass ratio" and keeps it. A pandas release that changed
    `astype(bool)` on a NaN would make the two agree, and this check would then
    pass forever while testing nothing -- the dead-diagnostic shape CLAUDE.md
    records under "A diagnostic can go CONSTANT, and a constant reads exactly
    like a clean result". So it is asserted rather than assumed.

    An old expression that RAISES still discriminates: a crash is not the
    silent drop this guards against.
    """
    try:
        old = bool((~prop["propellantless"].astype(bool)).iloc[-1])
    except Exception:                                      # noqa: BLE001
        return True
    new = bool(prop["propellantless"].ne(True).iloc[-1])
    return old != new


def check_validate_missing_flag(t) -> bool:
    """Stage 3's sanity bands still cover a propellant row that omits the flag.

    THE GAP THIS CLOSES. `verify.py`'s header says in as many words that
    "Stage 3's validate()" is not covered by it, and names this exact item:
    transportation 1.12.1's propellant-flag fix "lives in Stage 3's validate(),
    which Stage 4 never calls, and had to be checked by running that function
    under `-W error::FutureWarning` instead". That was done once, by hand,
    which is the written-from-memory-and-thrown-away shape both harnesses argue
    against, and the code it checks has since moved to another repository.

    THE DEFECT. `~propellant_df["propellantless"].astype(bool)` is correct only
    while every row states the flag, because pandas then infers dtype `bool`.
    Add one row that omits it, the column comes back `object` with a NaN in it,
    and `.astype(bool)` reads NaN as **True** -- so a propellant that forgot to
    say it has a mass ratio is silently classed as a SAIL and dropped from the
    Isp band and the price band at once. The checks would quietly stop covering
    the row most likely to be new and wrong, which is the "wrong behaviour is
    the quiet one" class exactly.

    Three assertions, and the third keeps the other two honest: the probe warns
    when the flag is present (so it is built correctly), it still warns when
    the flag is missing (the invariant), and the two spellings genuinely
    disagree on it (so the check can still fail).
    """
    import pandas as pd
    import spacecost
    from spacecost.prices import merge_propellant_prices

    # Priced, because that is the frame `validate` is actually called with:
    # `build` folds the fuel quotes in BEFORE validating, so `cost_usd_per_kg`
    # exists by then and the raw loader's frame raises KeyError. An empty live
    # frame is the `use_yfinance=False` path, so this needs no network.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        launch = spacecost.load_launch_vehicles()
        dv = spacecost.load_delta_v()
        ops = spacecost.load_operational_costs()
        prop = merge_propellant_prices(spacecost.load_propellants(),
                                       pd.DataFrame())
    spacecost.set_verbose(True)

    def named(df) -> int:
        """How many of `validate`'s report lines name the probe row."""
        report = _validate_report(spacecost, launch, df, dv, ops)
        return sum(PROBE_NAME in line for line in report.splitlines())

    def with_probe(flagless):
        """The reference table plus one probe row."""
        extra = pd.DataFrame([_probe_row(prop.columns, flagless)])
        return pd.concat([prop, extra], ignore_index=True)

    try:
        clean = named(prop)
        with_flag = named(with_probe(False))
        flagless_df = with_probe(True)
        no_flag = named(flagless_df)
        live = _probe_still_discriminates(flagless_df)
    except Exception as exc:                               # noqa: BLE001
        # Never a skip. This calls four public functions of a PINNED package;
        # if one has changed shape, that is the drift this file exists to
        # report, not a reason to pass quietly.
        print("5. validate    *** COULD NOT RUN *** (%s: %s)"
              % (type(exc).__name__, exc))
        return False

    ok = clean == 0 and with_flag == 1 and no_flag == 1 and live
    print("5. validate    a propellant row with NO propellantless flag is %s"
          % ("still covered by the sanity bands" if ok
             else "*** DROPPED FROM THE SANITY BANDS ***"))
    print("     probe named on %d line(s) clean / %d with the flag / %d without"
          % (clean, with_flag, no_flag))
    if not live:
        print("     *** THE PROBE NO LONGER DISCRIMINATES: astype(bool) and "
              "ne(True) agree on a missing flag on this pandas, so this check "
              "tests nothing. Re-derive it before trusting a pass.")
    if not ok and no_flag == 0:
        print("     the flagless row was read as PROPELLANTLESS, which IS the "
              "transportation 1.12.1 regression; see .ne(True) in "
              "spacecost/validate.py")
    return ok


def _installed_revision():
    """What revision pip actually installed, from the wheel's own metadata.

    `direct_url.json` is written by pip for anything installed from a URL
    (PEP 610) and records both the revision ASKED FOR and the commit it
    RESOLVED TO. Returns `(requested, commit)`, either of which may be None, or
    None entirely when the distribution was not installed from a direct URL --
    an editable checkout, a local path, or one day PyPI.
    """
    import json
    try:
        import importlib.metadata as md
        raw = md.distribution("spacecost").read_text("direct_url.json")
    except Exception:                                      # noqa: BLE001
        return None
    if not raw:
        return None
    try:
        info = json.loads(raw).get("vcs_info") or {}
    except ValueError:
        return None
    return info.get("requested_revision"), info.get("commit_id")


def check_installed_revision(t) -> bool:
    """The package being driven is the one `requirements.txt` pins.

    THE GAP THIS CLOSES, and it is the precondition for every check above.
    Checks 1 to 5 all describe whatever `import spacecost` happens to reach.
    Nothing asked whether that is the revision this repo pins, and the answer
    is not inferable from anything they compare: `__version__` moves only on a
    release, `DATA_VERSION` identifies the data CONTRACT rather than the
    commit, and `reference/` is compared against a SOURCE CHECKOUT rather than
    against the installed package. So `pip install -e ../spacecost` at a
    checkout two commits past the tag passes all five while the pipeline runs
    code this repo does not pin.

    🚨  THAT IS THE PARALLEL-REPO DIVERGENCE WITH A PACKAGE MANAGER IN FRONT OF
    IT. `1.0.6`, `1.1.4` and `1.3.6` each shipped as two different things the
    last time this project had two sources of one truth, and what made it
    expensive was that nothing checked.

    Three outcomes, kept apart the way `_reference_dir`'s are. Installed from
    the pinned tag is a pass and names the commit. Installed from a DIFFERENT
    revision is a failure. Installed from something with no VCS metadata at all
    -- editable, a local path, a future PyPI release -- is also a failure while
    `requirements.txt` pins a git ref, because a git-pinned requirement that
    produced a non-git install means something other than that pin put it
    there.
    """
    tag = _pinned_tag()
    rev = _installed_revision()

    if not tag:
        print("6. revision    *** the pinned ref could not be read from "
              "requirements.txt ***")
        return False

    if rev is None:
        print("6. revision    *** NOT INSTALLED FROM THE PINNED REF *** "
              "(no VCS metadata)")
        print("     requirements.txt pins %s, and the installed spacecost "
              "carries no" % tag)
        print("     direct_url.json, so it came from an editable checkout, a "
              "local path or")
        print("     a release. Whatever is being driven, it is not this pin.")
        # `py` is the Windows launcher and exists nowhere else, so naming it
        # unconditionally is wrong advice on the host most likely to need it.
        # Not shared with verify.py: that is one expression, not a manifest.
        launcher = "py" if os.name == "nt" else os.path.basename(sys.executable)
        print("     Reinstall:  %s -m pip install -r requirements.txt" % launcher)
        return False

    requested, commit = rev
    if requested != tag:
        print("6. revision    *** INSTALLED REVISION IS NOT THE PINNED ONE ***")
        print("     requirements.txt pins %s, pip installed %s (%s)"
              % (tag, requested, (commit or "unknown commit")[:12]))
        return False

    # The tag RESOLVING to a different commit than the one installed means the
    # tag itself has been moved, which a version string cannot show and which
    # no other check here can see.
    note = ""
    root = os.environ.get("SPACECOST_SOURCE") or os.path.normpath(
        os.path.join(REPO, os.pardir, "spacecost"))
    if commit and os.path.isdir(os.path.join(root, ".git")):
        state = _reference_matches_tag(root, tag)
        if isinstance(state, str):
            note = ", tag not resolvable here (%s)" % state
        else:
            import subprocess
            try:
                r = subprocess.run(
                    ("git", "-C", root, "rev-parse", tag + "^{commit}"),
                    capture_output=True, text=True, timeout=30)
                at_tag = r.stdout.strip() if r.returncode == 0 else ""
            except (OSError, subprocess.SubprocessError):
                at_tag = ""
            if at_tag and at_tag != commit:
                print("6. revision    *** THE TAG HAS MOVED ***")
                print("     installed %s, but %s now points at %s"
                      % (commit[:12], tag, at_tag[:12]))
                return False
            if at_tag:
                note = ", and %s still points there" % tag

    print("6. revision    installed from %s at %s%s"
          % (tag, (commit or "unknown")[:12], note))
    return True


def main() -> int:
    """Run every check and return the process exit code.

    Every check runs even after one fails.  The report is the point: a run that
    stopped at the first mismatch could not tell "the package moved a row" from
    "the adapter stopped passing the settings through", which is the one
    distinction this file exists to make.
    """
    print("=" * 70)
    print("  STAGE 3 VERIFICATION  -  economicspace adapter vs spacecost")
    print("=" * 70)
    # FIRST, and this file is the reason the check exists: on 2026-09-15 this
    # harness ran an OLDER COPY OF ITSELF off the Drive mount and printed four
    # checks instead of six, with `git status` clean and its bytes hashing equal
    # to HEAD afterwards.  See tree_check.py.
    tree_ok = tree_check.assert_tree()
    t, tmp = _load_adapter()
    import spacecost
    print("  spacecost %s, data contract %s" % (spacecost.__version__,
                                                spacecost.DATA_VERSION))
    print("  scratch   %s" % tmp)
    print("-" * 70)

    results = [
        tree_ok,
        check_config_surface(t),
        check_data_contract(t),
        check_output(t, tmp),
        check_against_committed_reference(t, tmp),
        check_validate_missing_flag(t),
        check_installed_revision(t),
    ]
    print("-" * 70)
    if all(results):
        print("  OK  STAGE 3 VERIFIED - the split has not drifted")
        return 0
    print("  *** NOT VERIFIED *** - see the failing check above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
