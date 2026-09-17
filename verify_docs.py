# -*- coding: utf-8 -*-
"""Documentation verification for the asteroid profitability pipeline.

`verify.py` proves the MODEL did not change.  This proves the DOCS still
describe it.  The checks below are all mechanical and all fast (about a
second).  Their number is deliberately not written out here -- it read "Ten"
against eleven of them for as long as check 11 had existed, which is the
counts-in-prose failure this file was written to catch:

    1. defaults      every default the README's Tuning table quotes, against
                     the dataclass field it names
    2. versions      the Stage/Version table and CLAUDE.md's "Current:" line,
                     against each module's `pipeline_version`; and every count
                     spelled out in prose beside a "moved without moving a
                     number" table, in any doc that quotes one, against the
                     rows of the table itself
    3. row counts    documented reference-table sizes, against the tables
    4. links         every markdown anchor resolves, in all three files
    5. structure     balanced fences, no ragged tables, no heading-level jumps,
                     no duplicate h1/h2, in every markdown file in the repo
    6. dashes        no em- or en-dash in prose a reader sees, and no line left
                     opening with a bare comma by the pass that removed them;
                     the docs, the root scripts and the campaign scripts
    7. manifests     a list documented in one place, against the list actually
                     defined in another: requirements.txt vs _MASTER_REQUIRED,
                     and README's `run.bat` block vs run.bat's own dispatcher
    8. help          every config dial the dashboard renders carries the
                     comment it shows as help text
    9. runtime       README's cislunar wall clock, against the
                     MEASURED_CELL_SECONDS every banner now derives from
   10. transfer      every distinctive number in a --before snapshot still
                     appears somewhere in the docs afterwards
   11. docstrings    every module, class and function in the repo's own Python
                     carries one
   12. pairs         no measurement is quoted in BOTH README and CLAUDE.md
                     without a row on CLAUDE.md's register of known copies
   13. scope         which checks `verify.py` runs, against every sentence in
                     either file that says -- its own docstring list, README's
                     table, and the four claims about what a subcommand covers

    py verify_docs.py                       # every check except 10
    py verify_docs.py --before OLD.md NEW.md NEW2.md   # adds check 10

WHY THIS FILE EXISTS
--------------------
The recurring failure in this repo is not a missing table, it is a stale
sentence -- CLAUDE.md's "When a number changes, grep the prose too" records an
audit that found four releases' worth of rot in committed-clean files.  Every
one of the checks below was written by hand during one such audit and would
otherwise have been thrown away, which is the same mistake `verify.py` exists
to stop.  What they caught, on the run that prompted writing them down:

  README documented `use_beneficiation` and `optimise_programme_scale` as
  False.  Both have been True since calc 1.17.0, so the two most consequential
  settings in the pipeline were documented backwards.            -> check 1
  calc 1.17.8 said "No number" in its own release section and was missing from
  BOTH tables of stamps that moved without moving a number, so the count beside
  each read "twelve" against thirteen rows -- the third time that particular
  count has rotted.  It then rotted a FOURTH time, in README, which quotes the
  count and holds no table, and so was outside this check until 2026-09-02.
                                                                 -> check 2
  "Propellants -- 40 rows" with development=7; the module loads 41 and 8, both
  stale by exactly the cryogenic-argon row v1.12.0 added.        -> check 3
  A README section promising "all five" checks above a table of six. -> by eye
  `run.bat help` was accepted by the dispatcher and documented nowhere, so
  README's option list had quietly drifted from run.bat's own.    -> check 7
  26 measurements dropped rather than moved when the version history was split
  out into versions.md -- a line diff reported 302 differences and could not
  tell any of them from a reflowed paragraph.                   -> check 10
  The superseded 1.16.0 runtime ratios were still being PRINTED on every
  run, in five files at once, three releases after the measurement that
  retired them.                                                 -> check 9
  39 of 105 config fields showed a bare dial in the dashboard, because their
  comment block sat above a NEIGHBOURING field.                   -> check 8
  87 definitions carried neither a docstring nor a comment, most of them in
  ui.py and launch_ui.py, where the Windows traps that justify the code are
  the whole reason it looks the way it does.                     -> check 11
  The cross-document pair hunt was PRESCRIBED IN PROSE and rebuilt from that
  description four separate times, which is the "written from memory and
  thrown away" shape this file's own argument is about.  Committing it found a
  pair the hand-maintained register had missed since the register was written,
  and it was the project's four headline cislunar numbers.       -> check 12

SCOPE.  This reads the docs and the module dataclasses.  It does NOT run the
pipeline, fetch anything, or check that a documented NUMBER is a correct
measurement -- only that a documented CONFIGURATION matches the code.  A
measurement can be stale and still pass everything here; that is what the
release notes and `verify.py` are for.

WHICH FILES.  Checks 4, 5 and 6 cover `campaign/` as well as the three
authorities, since 2026-09.  Six campaign scripts and two campaign markdown
files spent a whole measurement campaign outside every check in here, which is
the state the dash ratchet exists to prevent: a file nothing checks is clean
until it is not.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tokenize
from typing import Dict, List, Optional, Tuple

# Local: the working-tree guard every harness here runs first.  It is a
# sibling file rather than a copied function because four harnesses need
# it and a second copy of a check is the defect this repo catalogues
# oftenest.
import tree_check



def _force_utf8_stdout() -> None:
    """Make stdout survive a non-ASCII character on a cp1252 console.

    Every `print` in this repo's own modules is pure ASCII, and check 6 is the
    ratchet that keeps them that way.  This file is the one that prints text it
    did NOT write: check 10 echoes the source line each lost number came from,
    and those lines are comments and docstrings, where the arrows, sigmas and
    warning glyphs are still allowed.  Windows picks cp1252 for a redirected
    stdout, so `--before` on a module source died with UnicodeEncodeError
    part-way through its own report, the same failure `run_pipeline.py`'s
    identical guard exists for.  `errors="replace"` is the load-bearing half.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass          # already detached, or not a text stream


_force_utf8_stdout()

REPO = os.path.dirname(os.path.abspath(__file__))
DOCS = ["README.md", "versions.md", "CLAUDE.md"]

# Markdown that is not one of the three authorities but is still prose a reader
# is sent to.  The campaign pair spent a whole measurement campaign outside
# every check here, which is exactly how the docs drifted before any of these
# existed: a file nothing checks is a file that is clean until it is not.
CAMPAIGN_DOCS = ["campaign/FINDINGS.md", "campaign/README.md",
                 # Not a campaign doc, but the same argument: it is prose a
                 # reader is sent to, it quotes measured figures (the GPU
                 # result, the memory peaks, the CRLF hashes), and a file
                 # nothing checks is a file that is clean until it is not.
                 "SPARK_SETUP.md",
                 # The citation authority.  It carries two attribution
                 # obligations that are conditions of use rather than
                 # courtesies, so it is prose that must not rot quietly.
                 "CITATIONS.md",
                 # The starred-repo audit.  Same argument again: it quotes
                 # measured figures (the plane-change split, the Lambert gap,
                 # the taxonomy disagreement, the orbit-quality enrichment)
                 # and README and versions.md both link into it.
                 "research/starred-repos/README.md",
                 "research/starred-repos/FINDINGS.md",
                 "research/starred-repos/SOURCES.md",
                 "research/starred-repos/SPACE-MAP.md",
                 # The second pass over the same seventeen.  Same argument
                 # again, and one more: it carries the NHATS and
                 # Shoemaker-Helin rank agreements, which are the only
                 # external check on the delta-v model that this repo did not
                 # build itself.
                 "research/starred-repos/SECOND-PASS.md"]

# The campaign scripts.  Prose a reader sees, checked whole like the root
# scripts rather than comments-only like modules/: they hold no reference table,
# so nothing in them is written into a CSV and none of their text is data.
CAMPAIGN_PY = ["campaign/analyse.py", "campaign/extra_checks.py",
               "campaign/memwatch.py", "campaign/population.py",
               "campaign/rig_bounds.py",
               "campaign/run_cell.py", "campaign/run_queue.py"]

MODULES = {
    "catalog":   "modules/catalog.py",
    "mineral":   "modules/mineral_value.py",
    "transport": "modules/transportation.py",
    "calc":      "modules/calc.py",
}

# A "distinctive" number: has a decimal point, a thousands separator, or four
# or more digits.  Bare years are excluded -- they are dates, not measurements.
TOKEN = re.compile(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+|\b\d{4,}\b")
YEAR = re.compile(r"20\d\d")


def read(path: str) -> str:
    """Whole file as text, always UTF-8.

    Explicit rather than relying on the locale: on Windows the default is
    cp1252, and every doc and module here carries arrows, Greek and warning
    glyphs in its prose, so a locale read would raise on the first one.
    """
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def absent(names) -> List[str]:
    """First-party paths this repo NAMES that are not on disk.

    🚨  A SKIP IS NOT A PASS, AND THIS FILE HAD SEVEN OF THEM.  Every list in
    here -- `DOCS`, `ROOT_PY`, `FIRST_PARTY_PY`, `MODULES`, `CURRENT_DOCS` --
    names files the repo OWNS, so a name with no file behind it is a finding,
    never a reason to read one file fewer and still print OK.

    ⚠️  PROVED RATHER THAN ARGUED, 2026-09-15.  Renaming `verify_stage1.py`
    away took check 11 from 486 definitions to 469 and check 6 from 35 files to
    34, and the run still exited **0**.  A whole first-party harness could
    leave this repo and every docs check would call the result clean.

    🚨  AND IT IS REACHABLE WITHOUT DELETING ANYTHING.  The working copy is on
    a Drive File Stream mount, where a file that has not materialised can read
    as absent -- the same mount whose placeholder sizes already have a section
    in CLAUDE.md.  Both stage harnesses were invisible to the first run of this
    session and visible to the next, with no commit in between: check 6 read
    **33** files and then 35.  That is this check's own failure mode arriving
    through the filesystem rather than through a deletion.

    This is the same defect `verify.py` had (a `check` with no baseline
    printing ALL CHECKS PASSED), `verify_docs.py` checks 8 and 9 had (a
    `SyntaxError` swallowed as a skip) and `verify_stage3.py` check 4 had (a
    skip that fired on 100% of runs).  Fourth instance, same sentence.
    """
    return [n for n in names if not os.path.exists(os.path.join(REPO, n))]


def load_modules() -> Dict[str, object]:
    """Import each stage for its CONFIG.  Their import banners go to /dev/null;
    they print on import by design and this is not a run."""
    out = {}
    for alias, rel in MODULES.items():
        spec = importlib.util.spec_from_file_location("_vd_" + alias,
                                                      os.path.join(REPO, rel))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_vd_" + alias] = mod
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            spec.loader.exec_module(mod)
        out[alias] = mod
    return out


def _num(x) -> Optional[float]:
    """`x` as a float if it reads as one, else None.

    Strips `_` and `,` so a documented `1,555,667` or a source-side `1_555_667`
    compares equal to the int on the dataclass; check 1 uses it to accept a
    difference of NOTATION while still failing on a difference of value.
    """
    try:
        return float(str(x).replace("_", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------- 1. defaults
TUNING_ROW = re.compile(
    r"^\|\s*`(?:MASTER_CONFIG)?\.(\w+)\.(\w+)`\s*\|\s*`?([^|`]*?)`?\s*\|", re.M)


def check_defaults(mods) -> bool:
    """Every default README's Tuning table quotes, against the field it names.

    Reads the table rather than a hand-kept list, so a row added there is
    checked from the moment it is written. A row naming a field that does not
    exist is a failure too, not a skip: that is a rename the docs did not
    follow. This is the check that caught `use_beneficiation` and
    `optimise_programme_scale` being documented as False for several releases
    after calc v1.17.0 flipped them.
    """
    txt = read(os.path.join(REPO, "README.md"))
    bad: List[str] = []
    n = 0
    for m in TUNING_ROW.finditer(txt):
        alias, field, documented = m.group(1), m.group(2), m.group(3).strip()
        if alias not in mods:
            continue
        cfg = mods[alias].CONFIG
        name = ".%s.%s" % (alias, field)
        if not hasattr(cfg, field):
            bad.append("%-44s documented, but no such field" % name)
            continue
        n += 1
        doc, act = documented.strip('"').strip("'"), str(getattr(cfg, field))
        if doc == act:
            continue
        if _num(doc) is not None and _num(doc) == _num(act):
            continue
        # "all `True`" covers a row that documents several toggles at once
        if doc.lower().startswith("all ") and doc.lower().endswith(str(act).lower()):
            continue
        bad.append("%-44s README says %-14s actual %s" % (name, doc, act))

    print("1. defaults    %d documented, %d wrong" % (n, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# ----------------------------------------------------------------- 2. versions

# The stamp tables in versions.md and CLAUDE.md share this header exactly.
_STAMP_HEADER = "| stamp | why it moved | what a re-run gives |"

_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve "
          "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
          ).split()


def _spelled(token: str) -> Optional[int]:
    """`"thirteen"` or `"13"` as an int, else None."""
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return _WORDS.index(token) if token in _WORDS else None


def _stamp_table(text: str) -> Optional[List[str]]:
    """Body rows of the no-number stamp table, or None if it is not there."""
    lines = text.split("\n")
    try:
        i = next(k for k, l in enumerate(lines) if l.strip() == _STAMP_HEADER)
    except StopIteration:
        return None
    rows = []
    for l in lines[i + 1:]:
        if not l.startswith("|"):
            break
        if "---" not in l:
            rows.append(l)
    return rows


def _stamp_prose(doc: str, total: int, perf: int,
                 seen: int, bad: List[str]):
    """Hold every count spelled out beside a stamp table to the table itself.

    Split out of `check_versions` so it can run against a file that quotes the
    count but carries no table -- README did exactly that, and went stale for a
    fourth time because nothing looked at it.
    """
    text = read(os.path.join(REPO, doc))
    for pat, want, label in (
            (r"([A-Za-z]+) stamps so far", total, "total"),
            (r"stands unaltered across all ([a-z]+)", total, "total"),
            (r"([A-Za-z]+) rows are \*?\*?performance", perf, "performance"),
            (r"performance stamps and ([a-z]+) are not", total - perf, "other"),
            (r"the other ([a-z]+) are `", total - perf, "other")):
        for m in re.finditer(pat, text):
            seen += 1
            if _spelled(m.group(1).lower()) != want:
                bad.append("%s says %r %s stamps, the table has %d"
                           % (doc, m.group(1), label, want))
    return seen, bad


def check_versions(mods) -> bool:
    """Documented stamps against the dataclasses, and the stamp tables against
    the counts spelled beside them.

    Two halves. The first reads README's Stage/Version table and CLAUDE.md's
    `Current:` line; that one has rotted before, reading calc 1.16.0 while the
    module was four releases past it. The second counts the rows of the
    "moved without moving a number" table in each doc and holds the prose to
    them, because that count has now rotted three times.
    """
    actual = {a: mods[a].CONFIG.pipeline_version for a in mods}
    bad: List[str] = []

    # README's stage table:  | 4 | `modules/calc.py` | 1.17.7 | ... |
    readme = read(os.path.join(REPO, "README.md"))
    seen = 0
    for alias, rel in MODULES.items():
        pat = re.compile(r"\|\s*`%s`\s*\|\s*([0-9]+\.[0-9]+\.[0-9]+)\s*\|"
                         % re.escape(rel))
        m = pat.search(readme)
        if not m:
            bad.append("README stage table has no row for %s" % rel)
            continue
        seen += 1
        if m.group(1) != actual[alias]:
            bad.append("README stage table: %-28s says %-8s actual %s"
                       % (rel, m.group(1), actual[alias]))

    # CLAUDE.md:  Current: catalog `1.1.1`, mineral_value `1.7.1`, ...
    claude = read(os.path.join(REPO, "CLAUDE.md"))
    mc = re.search(r"Current:\s*(.{0,200})", claude, re.S)
    NAMES = {"catalog": "catalog", "mineral": "mineral_value",
             "transport": "transportation", "calc": "calc"}
    if mc:
        blob = mc.group(1)
        for alias, label in NAMES.items():
            m = re.search(r"%s\s*`([0-9]+\.[0-9]+\.[0-9]+)`" % re.escape(label), blob)
            if m:
                seen += 1
                if m.group(1) != actual[alias]:
                    bad.append("CLAUDE.md Current: %-16s says %-8s actual %s"
                               % (label, m.group(1), actual[alias]))

    # versions.md's own "Current versions" table:
    #     | 3 | `modules/transportation.py` | **1.14.0** | ... |
    # This one was NOT checked until 2026-09-07, and it had rotted: it read
    # catalog 1.1.1 while the module was at 1.2.0, stale since the 1.2.0
    # release, in the document that calls itself the authority for the
    # measurement history.  Both other copies of the same table were checked,
    # which is what let this one sit wrong -- the check covered the places
    # somebody had already been burned by and not the third.
    versions = read(os.path.join(REPO, "versions.md"))
    for alias, rel in MODULES.items():
        pat = re.compile(r"\|\s*`%s`\s*\|\s*\**([0-9]+\.[0-9]+\.[0-9]+)\**\s*\|"
                         % re.escape(rel))
        m = pat.search(versions)
        if not m:
            bad.append("versions.md Current-versions table has no row for %s" % rel)
            continue
        seen += 1
        if m.group(1) != actual[alias]:
            bad.append("versions.md Current versions: %-28s says %-8s actual %s"
                       % (rel, m.group(1), actual[alias]))

    # The master version is a literal in build_master.py, in two places, and
    # versions.md quotes it in the same table.  It is not a dataclass field, so
    # check 1 cannot reach it either.
    bm = read(os.path.join(REPO, "build_master.py"))
    lits = set(re.findall(r"MASTER ASTEROID PROFITABILITY PIPELINE - v"
                          r"([0-9]+\.[0-9]+\.[0-9]+)", bm))
    lits |= set(re.findall(r"Master Asteroid Profitability Pipeline "
                           r"\(([0-9]+\.[0-9]+\.[0-9]+)\)", bm))
    if len(lits) > 1:
        bad.append("build_master.py master version disagrees with itself: %s"
                   % sorted(lits))
    elif lits:
        want = lits.pop()
        mm = re.search(r"\|\s*`master\.py`\s*\|\s*\**([0-9]+\.[0-9]+\.[0-9]+)\**\s*\|",
                       versions)
        if mm:
            seen += 1
            if mm.group(1) != want:
                bad.append("versions.md master.py says %-8s build_master.py has %s"
                           % (mm.group(1), want))

    # ---- the "moved without moving a number" tables, and the prose on them --
    # Both files carry this table and both spell its size out in words beside
    # it, and that count has now rotted THREE times: "nine"/"seven" after
    # 1.17.6 shipped, then "twelve"/"four" while 1.17.8 sat outside the table
    # having said "No number" in its own release section for a week.  The
    # paragraph warning against counts in prose is itself where they rot, so
    # this counts the rows instead.
    #
    # README carries the same sentence and NO table, which is exactly how it
    # went stale a fourth time: it read "twelve stamps so far" until 2026-09-02
    # while both tables held thirteen rows, and this check never looked at it.
    # A file with no table of its own is scored against the canonical one.
    canonical = None
    for doc in ("versions.md", "CLAUDE.md"):
        rows = _stamp_table(read(os.path.join(REPO, doc)))
        if rows is None:
            bad.append("%s: no `| stamp | why it moved |` table found" % doc)
            continue
        total = len(rows)
        perf = sum("performance only" in r for r in rows)
        if canonical is None:
            canonical = (total, perf)
        elif canonical != (total, perf):
            bad.append("%s's stamp table has %d rows (%d perf); the first "
                       "table had %d (%d perf)"
                       % (doc, total, perf, canonical[0], canonical[1]))
        seen, bad = _stamp_prose(doc, total, perf, seen, bad)

    if canonical is not None:
        # Docs that quote the count but hold no table of their own.
        for doc in ("README.md",):
            seen, bad = _stamp_prose(doc, canonical[0], canonical[1], seen, bad)

    print("2. versions    %d stamps documented, %d wrong" % (seen, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# --------------------------------------------------------------- 3. row counts
def check_row_counts(mods) -> bool:
    """Documented sizes of the Stage 3 reference tables.

    Two kinds.  The TABLE sizes are quoted in prose and in headings all over the
    docs and move whenever a row is added; v1.12.0 split argon and left
    "40 propellants" standing in two places.  The DERIVED counts are what
    survives the maturity and mission-profile filters, they are quoted in
    `modules/calc.py`'s comments as well as in README, and they move whenever a
    row's `status` changes, which is a one-word edit nobody thinks of as a
    measurement."""
    t = mods["transport"]
    sizes = {
        "propellants": len(t.PROPELLANTS_REFERENCE),
        "vehicles":    len(t.LAUNCH_VEHICLES_REFERENCE),
        "storage":     len(t.STORAGE_REFERENCE),
    }
    # (regex, which size it claims) -- each must match the table it describes
    CLAIMS: List[Tuple[str, str]] = [
        (r"###\s*Propellants\s*[-:—–]\s*(\d+)\s*rows", "propellants"),
        (r"###\s*Launch vehicles\s*[-:—–]\s*(\d+)\s*rows", "vehicles"),
        (r"###\s*Storage systems\s*[-:—–]\s*(\d+)\s*rows", "storage"),
        (r"(\d+)\s*launch vehicles \(incl\. non-rocket concepts\)", "vehicles"),
        (r"(\d+)\s*propellants with storage class", "propellants"),
    ]
    readme = read(os.path.join(REPO, "README.md"))
    bad, n = [], 0
    for pat, key in CLAIMS:
        for m in re.finditer(pat, readme):
            n += 1
            if int(m.group(1)) != sizes[key]:
                bad.append("README claims %s %s, module has %d"
                           % (m.group(1), key, sizes[key]))

    # status breakdowns:  | operational | 23 | ... |
    counts: Dict[str, int] = {}
    for row in t.PROPELLANTS_REFERENCE:
        s = str(row.get("status", "?"))
        counts[s] = counts.get(s, 0) + 1
    for status, want in counts.items():
        m = re.search(r"^\|\s*%s\s*\|\s*(\d+)\s*\|" % re.escape(status),
                      readme, re.M)
        if m:
            n += 1
            if int(m.group(1)) != want:
                bad.append("README propellant status '%s' says %s, module has %d"
                           % (status, m.group(1), want))

    # ---- DERIVED counts: the size of the SEARCH GRID, not of a table -------
    # The row counts above are lengths.  These are what survives the filters,
    # and they are quoted in `modules/calc.py`'s own comments as well as in
    # README, which is the copy CLAUDE.md warns check 1 cannot reach: "it
    # cannot see the copies that live in code."  They move whenever a row's
    # `status` changes, which is a one-word edit nobody thinks of as a
    # measurement.
    #
    # Matched as a digit OR as the English word, because three of the calc
    # comments spell it "seventeen" -- and a count spelled out in prose is
    # exactly what this repo keeps finding stale.
    def _truthy(row, key, default):
        """A reference-table flag as a bool, with an explicit default if absent.

        Says what a MISSING value means instead of letting truthiness decide,
        which is the trap `.astype(bool)` springs on a nullable column: it reads
        NaN as True, so a propellant row omitting `restartable` would count as
        usable and one omitting `propellantless` would be classed as a sail.
        """
        v = row.get(key, None)
        if v is None or (isinstance(v, float) and v != v):
            return default
        return bool(v)

    ops_props = [r for r in t.PROPELLANTS_REFERENCE
                 if str(r.get("status")) == "operational"]
    derived = {
        "operational propellants": len(ops_props),
        # what can actually fly the profile: a solid cannot be relit for a
        # return burn years later, and a sail reports an unbounded payload
        "usable propellants": len([r for r in ops_props
                                   if _truthy(r, "restartable", True)
                                   and not _truthy(r, "propellantless", False)]),
        "operational vehicles": len([r for r in t.LAUNCH_VEHICLES_REFERENCE
                                     if str(r.get("status")) == "operational"]),
    }
    WORDS = {n: w for n, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"
        .split())}
    NUM = r"(\d+|[a-z]+)"
    DERIVED_CLAIMS = [
        ("README.md", r"Only the %s operational rows are in the default search"
                      % NUM, "operational propellants"),
        ("README.md", r"default search, and only %s of those" % NUM,
         "usable propellants"),
        ("modules/calc.py", r"%s propellants' worth of answers" % NUM,
         "usable propellants"),
        ("modules/calc.py", r"%s numbers that are fixed for" % NUM,
         "operational vehicles"),
        ("modules/calc.py", r"%s evaluations per propellant row" % NUM,
         "operational vehicles"),
        ("modules/calc.py", r"%s vehicles now share one" % NUM,
         "operational vehicles"),
    ]
    for gone in absent([r for r, _, _ in DERIVED_CLAIMS]):
        bad.append("%s carries a derived count and is not on disk" % gone)
    for rel, pat, key in DERIVED_CLAIMS:
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            continue
        want = derived[key]
        found = re.findall(pat, read(path))
        if not found:
            bad.append("%s: no claim matching %r (expected %s = %d)"
                       % (rel, pat, key, want))
            continue
        for got in found:
            n += 1
            if got != str(want) and got != WORDS.get(want):
                bad.append("%s claims %r %s, the tables give %d"
                           % (rel, got, key, want))

    print("3. row counts  %d claims checked, %d wrong  (propellants %d, "
          "vehicles %d, storage %d; %d usable propellants, %d operational "
          "vehicles)"
          % (n, len(bad), sizes["propellants"], sizes["vehicles"],
             sizes["storage"], derived["usable propellants"],
             derived["operational vehicles"]))
    for b in bad:
        print("     ! " + b)
    return not bad


# -------------------------------------------------------------------- 4. links
def slugs(path: str) -> set:
    """GitHub's heading -> anchor rule, including its -1 suffix for repeats."""
    out, seen = set(), {}
    for line in read(path).split("\n"):
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if not m:
            continue
        # NB: underscore is a WORD character and GitHub KEEPS it in an anchor.
        # Stripping it here reported `#reading-profitability_catalogcsv` as
        # broken when it is correct -- and a broken checker looks exactly like
        # a broken release, which this repo has already paid for twice.
        h = re.sub(r"[`*~]|\[|\]|\(|\)", "", m.group(2))
        s = re.sub(r"[^\w\s\-]", "", h, flags=re.UNICODE).strip().lower()
        s = s.replace(" ", "-")
        k = seen.get(s, 0)
        seen[s] = k + 1
        out.add(s if k == 0 else "%s-%d" % (s, k))
    return out


LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")

# Link-checked as well as DOCS.  These live in a subdirectory and point back up
# at the root docs, which is why targets resolve relative to the LINKING FILE
# rather than to REPO -- keying anchors by the path as written works only while
# every doc sits at the root, and campaign/ does not.
LINKED_DOCS = DOCS + CAMPAIGN_DOCS


def check_links() -> bool:
    """Every intra-repo markdown anchor resolves, in all five linked docs.

    Targets resolve relative to the LINKING FILE, not to the repo root, because
    `campaign/` does not sit at the root and keying anchors by the path as
    written works only while every doc does. External links are skipped; this
    checks what the repo controls.
    """
    missing_linked = ["%s is on the linked-document list and is not on disk"
                      % g for g in absent(LINKED_DOCS)]
    files = [d for d in LINKED_DOCS if os.path.exists(os.path.join(REPO, d))]
    anchors = {os.path.normpath(os.path.join(REPO, d)):
               slugs(os.path.join(REPO, d)) for d in files}
    bad, n = list(missing_linked), 0
    for d in files:
        src = os.path.normpath(os.path.join(REPO, d))
        base = os.path.dirname(src)
        for m in LINK.finditer(read(src)):
            target = m.group(2)
            if target.startswith(("http", "mailto", "#!")):
                continue
            fpart, _, apart = target.partition("#")
            dest = os.path.normpath(os.path.join(base, fpart)) if fpart else src
            if fpart and dest not in anchors:
                if not os.path.exists(dest):
                    bad.append("%s -> %s  (no such file)" % (d, target))
                continue
            if apart:
                n += 1
                if apart not in anchors[dest]:
                    bad.append("%s -> %s  (no such anchor)" % (d, target))
    print("4. links       %d anchors checked, %d broken" % (n, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# ---------------------------------------------------------------- 5. structure
def check_structure() -> bool:
    """Balanced fences, no ragged tables, no heading jumps, no duplicate h1/h2.

    Over every markdown file in the repo, not only the three authorities: a
    ragged table renders as literal pipes wherever it lives, and `campaign/`
    was outside this until 2026-09.

    A repeated h3 is normal here and is NOT flagged; nineteen release sections
    each carry their own "### Verification (date)". Ambiguous LINK targets are
    check 4's job, and it resolves GitHub's `-1` suffixes.
    """
    bad = ["%s is a tracked document and is not on disk" % g
           for g in absent(DOCS + CAMPAIGN_DOCS)]
    for d in DOCS + CAMPAIGN_DOCS:
        p = os.path.join(REPO, d)
        if not os.path.exists(p):
            continue
        lines = read(p).split("\n")

        fences = [i for i, l in enumerate(lines, 1) if l.strip().startswith("```")]
        if len(fences) % 2:
            bad.append("%s: unbalanced code fences (last at line %d)"
                       % (d, fences[-1]))

        infence, block, start, prev, heads = False, [], 0, 0, {}
        for i, l in enumerate(lines, 1):
            if l.strip().startswith("```"):
                infence = not infence
                continue
            if infence:
                continue
            s = l.strip()
            if s.startswith("|"):
                if not block:
                    start = i
                block.append(s)
            else:
                if len(block) >= 2 and len({b.count("|") for b in block}) > 1:
                    bad.append("%s: ragged table at line %d" % (d, start))
                block = []
            m = re.match(r"^(#{1,6})\s+\S", l)
            if m:
                lvl = len(m.group(1))
                if prev and lvl > prev + 1:
                    bad.append("%s: heading jumps h%d -> h%d at line %d"
                               % (d, prev, lvl, i))
                prev = lvl
                # Only h1/h2.  A repeated h3 is normal and correct here --
                # nineteen release sections each carry their own
                # "### Verification (date)" and "### What this release does
                # NOT close", and flagging those made the check useless noise.
                # Ambiguous LINK targets are check 4's job, and it resolves
                # GitHub's -1 suffixes.
                if lvl <= 2:
                    heads[l.strip()] = heads.get(l.strip(), 0) + 1
        for h, c in heads.items():
            if c > 1:
                bad.append("%s: duplicate heading %r (%dx)" % (d, h[:60], c))

    print("5. structure   %d files checked, %d problems"
          % (len(DOCS) + len(CAMPAIGN_DOCS), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# -------------------------------------------------------------------- 6. dashes
EM, EN = "—", "–"
ROOT_PY = ["ui.py", "ui_meta.py", "run_pipeline.py", "verify.py",
           "build_master.py", "launch_ui.py", "platform_check.py",
           # verify_stage3.py was outside BOTH ratchets until 2026-09-15, which
           # is the "a file nothing checks is clean until it is not" state this
           # check exists to prevent, in the one harness that guards the
           # spacecost split.  It was clean on dashes and carried three
           # definitions with no docstring, `main` among them.
           "verify_stage3.py", "verify_stage1.py", "tree_check.py",
           # Not Python, but prose a reader sees, and it was outside the
           # ratchet long enough to collect two em-dashes.  The hook's header
           # is the only account of the Drive stat-cache bug there is.
           # run.sh is here for the same reason and one more: it is the only
           # account of which run.bat traps do and do not carry to POSIX.
           ".githooks/drive-restat.sh", "_START HERE.vbs",
           "run.sh"] + CAMPAIGN_PY


# A line that begins with a bare comma is what the 2026-08-23 ASCII pass left
# where an em-dash had OPENED a continuation line.  The sentence stops parsing
# in English and nothing noticed for ten days: twelve in modules/*.py, then
# eight more in the docs found a week later, because the first sweep only
# looked at Python.  Anchored on start-of-line so a comma inside a sentence is
# untouched, and it is checked in the same place as the dashes because it is
# the same pass's damage.
ORPHAN_COMMA = re.compile(r"^\s*(?:#\s*)?,\s+\S")


def check_dashes() -> bool:
    """No em- or en-dash in prose a person reads, and no orphaned comma.

    The docs, the root scripts and the campaign scripts must be clean outright.
    In modules/*.py only COMMENTS and DOCSTRINGS are checked: the `notes` and
    `composition` strings are written into propellants.csv,
    launch_vehicles.csv and the asteroid catalog, so their text is DATA and
    keeps whatever it has.

    This is a ratchet, not a style opinion.  1,342 dashes came out of the docs
    and 1,120 out of the modules; without a check they drift back one commit
    at a time.  The orphan comma is the same conversion's leftover, and it is
    checked here for that reason.
    """
    gone = absent(DOCS + CAMPAIGN_DOCS + ROOT_PY + list(MODULES.values()))
    bad = []
    files = 0

    for name in DOCS + CAMPAIGN_DOCS + ROOT_PY:
        p = os.path.join(REPO, name)
        if not os.path.exists(p):
            continue
        files += 1
        for i, line in enumerate(read(p).split("\n"), 1):
            # verify_docs.py's own character classes must keep matching a dash
            if name == os.path.basename(__file__) and "[-:" in line:
                continue
            if EM in line or EN in line:
                bad.append("%s:%d  em/en dash  %s" % (name, i, line.strip()[:60]))
            elif ORPHAN_COMMA.match(line):
                bad.append("%s:%d  line opens with a bare comma  %s"
                           % (name, i, line.strip()[:60]))

    for rel in MODULES.values():
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            continue
        files += 1
        src = read(p)
        rows = set()
        try:
            fh = io.StringIO(src)
            for tok in tokenize.generate_tokens(fh.readline):
                if tok.type == tokenize.COMMENT:
                    rows.add(tok.start[0])
            for node in ast.walk(ast.parse(src)):
                body = getattr(node, "body", None)
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef)) and body:
                    f = body[0]
                    if (isinstance(f, ast.Expr)
                            and isinstance(f.value, ast.Constant)
                            and isinstance(f.value.value, str)):
                        rows.update(range(f.lineno, f.end_lineno + 1))
        except (SyntaxError, tokenize.TokenError) as exc:
            bad.append("%s: could not parse (%s)" % (rel, exc))
            continue
        for i, line in enumerate(src.split("\n"), 1):
            if i not in rows:
                continue
            if EM in line or EN in line:
                bad.append("%s:%d  em/en dash  %s" % (rel, i, line.strip()[:60]))
            elif ORPHAN_COMMA.match(line):
                bad.append("%s:%d  comment opens with a bare comma  %s"
                           % (rel, i, line.strip()[:60]))

    print("6. dashes      %d files checked, %d bad lines "
          "(em/en dash, or a line opening with a bare comma)%s"
          % (files, len(bad),
             ", %d NOT ON DISK" % len(gone) if gone else ""))
    for g in gone:
        print("     ! %s is on the dash ratchet and is not on disk" % g)
    for b in bad[:20]:
        print("     ! " + b)
    if len(bad) > 20:
        print("     ! ... and %d more" % (len(bad) - 20))
    return not bad and not gone


# ---------------------------------------------------------------- 7. manifests
def check_manifests() -> bool:
    """A list documented in one place, against the list defined in another.

    Neither of these is a dataclass default, so check 1 cannot reach them, and
    both have already drifted.  `run.bat help` shipped accepted-but-undocumented
    for several releases; requirements.txt asserts in its own first line that it
    mirrors `_MASTER_REQUIRED`, and nothing was checking that.  The second is
    not cosmetic: a miss means `pip install -r` builds a different environment
    from the one the Colab paste auto-installs.
    """
    bad, n = [], 0

    # requirements.txt <-> _MASTER_REQUIRED (build_master.py writes it into
    # master.py, which pip-installs it at import time).
    req_p = os.path.join(REPO, "requirements.txt")
    bm_p = os.path.join(REPO, "build_master.py")
    if os.path.exists(req_p) and os.path.exists(bm_p):
        req = [ln.strip() for ln in read(req_p).split("\n")
               if ln.strip() and not ln.strip().startswith("#")]
        # A requirement line reduces to its DISTRIBUTION NAME, which is what
        # `_MASTER_REQUIRED` lists.  Three forms appear here:
        #     numpy                     a bare name
        #     numpy>=1.24               a version specifier
        #     spacecost @ git+https://  a PEP 508 direct reference
        # The last arrived when Stage 3's tables moved out to `spacecost`, which
        # is not on PyPI and so installs from a tagged git ref.  Splitting on the
        # specifier characters alone left the whole URL in the name and reported
        # a mismatch that was not one: the checker failing to understand the
        # manifest format it is checking.
        req = [r.split("@", 1)[0].strip() for r in req]
        req = [re.split(r"[<>=!~;\[]", r)[0].strip() for r in req]
        m = re.search(r"_MASTER_REQUIRED\s*=\s*\[(.*?)\]", read(bm_p), re.S)
        if m is None:
            bad.append("build_master.py: no _MASTER_REQUIRED list found")
        else:
            master = re.findall(r'"([^"]+)"', m.group(1))
            n += 1
            if sorted(req) != sorted(master):
                bad.append("requirements.txt %s != _MASTER_REQUIRED %s"
                           % (sorted(req), sorted(master)))

    # README's `run.bat` block <-> the words run.bat's dispatcher accepts.
    bat_p = os.path.join(REPO, "run.bat")
    readme_p = os.path.join(REPO, "README.md")
    if os.path.exists(bat_p) and os.path.exists(readme_p):
        bat = io.open(bat_p, encoding="utf-8", errors="replace").read()
        # `if /i "%CHOICE%"=="ui"   goto ui` -- the word forms only; the digits
        # are menu shortcuts and q/quit is not a run option.  Anchored on
        # %CHOICE% rather than on `==` alone, because run.bat compares other
        # variables too and the loose form reported the install prompt's "n"
        # as an undocumented option.
        accepted = {w.lower() for w in
                    re.findall(r'"%CHOICE%"\s*==\s*"([A-Za-z]+)"', bat)}
        accepted -= {"q", "quit"}
        documented = set(re.findall(r"^run\.bat\s+([a-z]+)", read(readme_p), re.M))
        n += 1
        for miss in sorted(accepted - documented):
            bad.append("run.bat accepts '%s', README does not document it" % miss)
        for extra in sorted(documented - accepted):
            bad.append("README documents 'run.bat %s', dispatcher rejects it"
                       % extra)

    # The PINNED REF, which the name comparison above deliberately throws
    # away. `spacecost` is not on PyPI, so it installs from a tagged git URL,
    # and that URL is typed in TWO places: `requirements.txt`, which
    # `pip install -r` reads, and `_MASTER_PIP_SPEC` in build_master.py, which
    # is written into master.py and auto-installs at import for the Colab
    # paste. Nothing compared them until 2026-09-15.
    #
    # 🚨  A ONE-LINE REPIN OF EITHER ALONE IS THE PARALLEL-REPO DIVERGENCE.
    # The two paths would install different revisions of the reference tables,
    # both would report a `spacecost` that imports cleanly, and every stamp in
    # this repo would still read `transportation 1.14.0`, because that stamp
    # identifies the DATA CONTRACT and not the commit. `1.0.6`, `1.1.4` and
    # `1.3.6` each shipped as two different things the last time this project
    # ran two sources of one truth; see versions.md.
    if os.path.exists(req_p) and os.path.exists(bm_p):
        req_ref = re.search(r"^spacecost\s*@\s*(\S+)", read(req_p), re.M)
        spec_ref = re.search(r'"spacecost"\s*:\s*"([^"]+)"', read(bm_p))
        n += 1
        if req_ref is None or spec_ref is None:
            # Not a skip. Both are supposed to be there, and one of them going
            # missing is the drift rather than a reason to pass quietly.
            bad.append("the pinned spacecost ref could not be read from %s"
                       % ("requirements.txt" if req_ref is None
                          else "build_master.py's _MASTER_PIP_SPEC"))
        elif req_ref.group(1) != spec_ref.group(1):
            bad.append("pinned spacecost ref differs: requirements.txt has %s, "
                       "_MASTER_PIP_SPEC has %s -- `pip install -r` and a Colab "
                       "paste would install different Stage 3 tables"
                       % (req_ref.group(1), spec_ref.group(1)))

    # README's `./run.sh` block <-> the words run.sh's dispatcher accepts.
    # Same check as the one above and for the same reason: `run.bat help`
    # shipped accepted-but-undocumented for several releases, and run.sh is the
    # newer of the two launchers, so its list is the one still moving.  The
    # dispatcher is a `case` over $ACTION; a label may carry alternatives
    # (`help|--help|-h`), and only the bare word forms are options a reader
    # would type.  `menu` is the empty-argument fallthrough, not an option.
    sh_p = os.path.join(REPO, "run.sh")
    if os.path.exists(sh_p) and os.path.exists(readme_p):
        sh = read(sh_p)
        block = sh.partition('case "$ACTION" in')[2]
        accepted = set()
        for label in re.findall(r"^\s{0,4}([A-Za-z|\-\"]+)\)", block, re.M):
            accepted |= {w for w in label.split("|") if w.isalpha()}
        accepted -= {"menu"}
        documented = set(re.findall(r"^\./run\.sh\s+([a-z]+)",
                                    read(readme_p), re.M))
        n += 1
        for miss in sorted(accepted - documented):
            bad.append("run.sh accepts '%s', README does not document it" % miss)
        for extra in sorted(documented - accepted):
            bad.append("README documents './run.sh %s', dispatcher rejects it"
                       % extra)

    print("7. manifests   %d manifests checked, %d mismatched" % (n, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# --------------------------------------------------------------------- 8. help
def check_help() -> bool:
    """Every config field the dashboard shows as a dial must carry help text.

    The UI scrapes its help straight out of the module sources, so a field's
    comment IS its documentation.  The attachment rule is positional: a block
    explains the field directly below it, and a comment block covering TWO
    fields leaves the second one blank in the dashboard.  Thirty-nine of 105
    fields were in that state, including `demand_elasticity`, `rtg_max_power_w`
    and `contingency_fraction` -- bare numbers, at exactly the dials a reader is
    most likely to change.  Fields listed in `ui_meta.PATH_FIELDS` are paths and
    filenames and are exempt by design.
    """
    try:
        sys.path.insert(0, REPO)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            import master as _m
            import ui_meta as _um
    except SyntaxError as exc:
        # A SyntaxError is in THIS REPO'S OWN SOURCE, so it is a failure and
        # never a skip.  The skip below exists for a machine without the
        # third-party dependencies; it must not also swallow a broken file.
        #
        # Found the hard way on 2026-09-08: a malformed string literal in
        # ui_meta.py made this check report SKIPPED and return PASS, and the
        # run only went red because an unrelated version stamp was also wrong.
        # That is the defect CLAUDE.md already records verify.py having had --
        # "a check that cannot run must never say it passed" -- in the other
        # harness.
        print("%s FAILED (%s in this repo's own source: %s)"
              % ("8. help       ", type(exc).__name__, exc))
        return False
    except Exception as exc:                       # noqa: BLE001
        print("8. help        SKIPPED (%s: %s)" % (type(exc).__name__, exc))
        return True

    pairs = [("catalog", _m.CATALOG_CONFIG), ("mineral", _m.MINERAL_CONFIG),
             ("transport", _m.TRANSPORT_CONFIG), ("calc", _m.CALC_CONFIG)]
    bad, n = [], 0
    for key, cfg in pairs:
        for spec in _um.build_field_specs(cfg, key):
            if spec.name in _um.PATH_FIELDS:
                continue
            n += 1
            if not (getattr(spec, "help", "") or "").strip():
                bad.append("%s.%s has no comment, so the UI shows a bare dial"
                           % (key, spec.name))

    print("8. help        %d dials checked, %d with no help" % (n, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# ------------------------------------------------------------------ 9. runtime
# One row per destination of README's 28-cell wall-clock table.  `[^|]*` after
# each figure is what lets `leo`'s dagger and the bold markers through; the
# pattern was tested against all three documents and matches the seven rows of
# the current table and nothing else, superseded tables included, because those
# carry two columns or no `s` suffix.
DEST_ROW = re.compile(
    r"^\|\s*`([a-z_]+)`\s*\|"
    r"\s*\*{0,2}([\d,]+)\s*s\*{0,2}[^|]*\|"
    r"\s*\*{0,2}([\d,]+)\s*s\*{0,2}[^|]*\|"
    r"\s*\*{0,2}([\d,]+)\s*s\*{0,2}[^|]*\|"
    r"\s*\*{0,2}([\d,]+)\s*s\*{0,2}[^|]*\|", re.M)

# CLAUDE.md's copy lives in the cross-document pairs register, which is by
# definition the list of copies the repo has agreed to keep CURRENT, so it is
# the one line in that file safe to pin.  Anchored on the row's own text rather
# than on a bare four-number pattern, deliberately: CLAUDE.md quotes the
# superseded 1.17.7 figures (733 / 1,253 / 3,424 / 5,692) in the same file on
# purpose, and a check that flagged those would be crying wolf at the history
# this project keeps on purpose.
CLAUDE_REGISTER = re.compile(r"^\|.*28-cell wall clocks.*\|$", re.M)

# `run.bat` and `run.sh` quote the default cell in HOURS before starting a
# multi-hour run, and shell cannot import `master` to derive it.  So it is
# typed, and therefore checked: every "N h at <destination>" in either launcher
# must round-trip through MEASURED_DEST_SECONDS.  Both read 1.6 h at cislunar
# and 3.8 h at earth_surface until 2026-09-15 -- calc 1.17.7 figures under a
# 1.21.2 base, in the one string a user reads before committing an afternoon.
LAUNCHER_HOURS = re.compile(r"([\d.]+) h at ([a-z_]+)")


# The campaign harness writes one JSON per cell it finishes: a per-cell
# `*.status.json` and, for a queue, a `*.progress.json` holding a `done` list of
# the same records.  Both carry `wall_s` and `calc_version`, both are committed,
# and between them they are the only machine-readable record of what a cell
# actually took.  That makes them the right thing to pin a typed constant to.
CELL_LOGS = os.path.join(REPO, "campaign", "logs")


def _measured_cells_on_disk(destination, calc_version):
    """`{(benef, search): wall_s}` for one destination at one release.

    Reads every campaign log rather than a named file, because a cell can have
    been measured by `run_cell.py` (its own status file) or inside a queue (one
    progress file holding several), and which one a given cell went through is
    not something a check should have to know.
    """
    found = {}
    if not os.path.isdir(CELL_LOGS):
        return found
    for fn in sorted(os.listdir(CELL_LOGS)):
        if not fn.endswith(".json"):
            continue
        try:
            with io.open(os.path.join(CELL_LOGS, fn), encoding="utf-8") as fh:
                blob = json.load(fh)
        except (ValueError, OSError):
            continue
        records = blob.get("done") if isinstance(blob.get("done"), list) else [blob]
        for rec in records:
            if not isinstance(rec, dict) or rec.get("rc") not in (0, "0"):
                continue
            if rec.get("destination") and rec["destination"] != destination:
                continue
            if not rec.get("destination") and not str(
                    rec.get("cell", "")).startswith(destination + "__"):
                continue
            if str(rec.get("calc_version")) != calc_version:
                continue
            if rec.get("wall_s") is None:
                continue
            key = (rec.get("ore") == "benef", rec.get("search") == "on")
            found[key] = float(rec["wall_s"])
    return found


def _check_cell_seconds(_m, cells, bad):
    """`MEASURED_CELL_SECONDS` against the campaign logs it was measured from.

    ⚠️  A MISSING LOG IS A FAILURE, NOT A SKIP.  This repo has now found six
    checks that could not run and said they passed anyway, and the constant
    this one guards is printed to a user on every run.  If the release stamped
    on the constant has no finished cislunar cells behind it on disk, the right
    answer is that nobody can tell where those four numbers came from.
    """
    stamp = getattr(_m, "MEASURED_CELL_CALC", None)
    if stamp is None:
        bad.append("master has MEASURED_CELL_SECONDS but no "
                   "MEASURED_CELL_CALC saying which release measured it")
        return 0
    logged = _measured_cells_on_disk("cislunar", stamp)
    if not logged:
        bad.append("MEASURED_CELL_SECONDS is stamped calc %s and "
                   "campaign/logs has no finished cislunar cell at that "
                   "release to check it against" % stamp)
        return 0
    n = 0
    labels = {(False, False): "raw N=1", (False, True): "raw searched",
              (True, False): "benef N=1", (True, True): "benef+searched"}
    for key, lab in sorted(labels.items()):
        if key not in logged:
            bad.append("MEASURED_CELL_SECONDS has %s and campaign/logs has no "
                       "cislunar %s at calc %s" % (lab, lab, stamp))
            continue
        n += 1
        # The logs carry tenths; the constant is whole seconds by convention.
        if abs(cells[key] - logged[key]) > 1.0:
            bad.append("MEASURED_CELL_SECONDS %-15s says %d s, "
                       "campaign/logs says %.1f s"
                       % (lab, cells[key], logged[key]))
    return n


def check_runtime() -> bool:
    """README's whole 28-cell wall-clock table, against `MEASURED_DEST_SECONDS`.

    Every user-facing quote of the beneficiation and programme-search cost
    ratios DERIVES from that dict, so the banners cannot go stale on their own.
    What can still drift is the docs: README tabulates the same twenty-eight
    numbers in prose, and prose is what this repo gets wrong.  Pinning the two
    together means a re-measurement has exactly one place to start and one check
    that says whether it finished.

    ⚠️  THIS CHECKED ONE ROW OF SEVEN UNTIL 2026-09-15, and the six it did not
    read are where the rot was: `lunar_surface` runs the default cell FASTER
    than cislunar, and five files said "cislunar is the cheapest destination"
    anyway, because the only row anybody had pinned was cislunar's own.  A
    check that reads one row of a table is a check on that row, not on the
    table.

    Since 2026-09-16 it covers a second dict as well.  `MEASURED_CELL_SECONDS`
    is no longer the cislunar row of this one -- it is the same cell one
    release later, which is what a banner should quote -- so the identity that
    used to be asserted here is gone and `_check_cell_seconds` pins those four
    to the campaign logs instead.
    """
    try:
        sys.path.insert(0, REPO)
        with contextlib.redirect_stdout(io.StringIO()):
            import master as _m
    except SyntaxError as exc:
        # See check 8: this repo's own source failing to parse is a failure.
        print("9. runtime     FAILED (%s in this repo's own source: %s)"
              % (type(exc).__name__, exc))
        return False
    except Exception as exc:                       # noqa: BLE001
        print("9. runtime     SKIPPED (%s: %s)" % (type(exc).__name__, exc))
        return True

    dests = getattr(_m, "MEASURED_DEST_SECONDS", None)
    cells = getattr(_m, "MEASURED_CELL_SECONDS", None)
    if not dests or not cells:
        print("9. runtime     SKIPPED (no MEASURED_DEST_SECONDS in master)")
        return True

    bad: List[str] = []
    n = 0
    labels = ["raw N=1", "raw searched", "benef N=1", "benef+searched"]

    # -- MEASURED_CELL_SECONDS against the logs it was measured from ----------
    # 🚨  THIS USED TO ASSERT THAT THE TWO DICTS AGREED ON CISLUNAR, and that
    # assertion was retired on 2026-09-16 rather than broken: they are two
    # measurements of one cell at two releases now, so agreement would be the
    # defect.  What replaces it has to be stronger, or unpicking the derivation
    # would have cost a check.  It is: the four seconds are compared against
    # `campaign/logs/*.json`, the artifacts the run itself wrote, so the
    # constant is pinned to a measurement rather than to a second copy of one.
    n += _check_cell_seconds(_m, cells, bad)

    # -- README's table, every row --------------------------------------------
    readme = read(os.path.join(REPO, "README.md"))
    rows = {m.group(1): m.groups()[1:] for m in DEST_ROW.finditer(readme)}
    missing = set(dests) - set(rows)
    if missing:
        bad.append("README's wall-clock table has no row for %s"
                   % ", ".join(sorted(missing)))
    for dest, got in sorted(rows.items()):
        if dest not in dests:
            bad.append("README's wall-clock table has a row for %r, which is "
                       "not in MEASURED_DEST_SECONDS" % dest)
            continue
        for got_s, exp, lab in zip(got, dests[dest], labels):
            n += 1
            if int(got_s.replace(",", "")) != exp:
                bad.append("README %-14s %-15s says %s s, "
                           "MEASURED_DEST_SECONDS says %d s"
                           % (dest, lab, got_s, exp))

    # -- CLAUDE.md's register row ---------------------------------------------
    claude = read(os.path.join(REPO, "CLAUDE.md"))
    reg = CLAUDE_REGISTER.search(claude)
    if reg is None:
        bad.append("CLAUDE.md's pairs register has no 28-cell wall-clock row")
    else:
        got = re.findall(r"[\d,]+(?=\s*(?:/|s\b))", reg.group(0))
        if len(got) != 4:
            bad.append("CLAUDE.md's wall-clock register row does not quote "
                       "four figures: %s" % reg.group(0).strip()[:70])
        else:
            for got_s, exp, lab in zip(got, dests["cislunar"], labels):
                n += 1
                if int(got_s.replace(",", "")) != exp:
                    bad.append("CLAUDE.md register %-15s says %s s, "
                               "MEASURED_DEST_SECONDS says %d s"
                               % (lab, got_s, exp))

    # -- the launchers and README's copy of their menus ---------------------
    # README tabulates both launchers' option lists, hours included, so the
    # same figure is typed in three files.  All three are held here rather than
    # two, because the README copy is the one a reader meets first.
    for fn in ("run.bat", "run.sh", "README.md"):
        path = os.path.join(REPO, fn)
        if not os.path.exists(path):
            bad.append("%s quotes a launcher runtime and is not on disk" % fn)
            continue
        for got_s, dest in LAUNCHER_HOURS.findall(read(path)):
            if dest not in dests:
                bad.append("%s quotes a runtime for %r, which is not a "
                           "destination" % (fn, dest))
                continue
            n += 1
            # `expected_cell_seconds`, not the campaign table: cislunar has
            # been re-measured since and a menu quoting hours should quote the
            # newest figure the destination has.  It is a LEVEL per row and
            # never a ratio between rows, which is the one thing that accessor
            # refuses to be used for.
            want = round(_m.expected_cell_seconds(dest, True, True) / 3600.0, 1)
            if abs(float(got_s) - want) > 0.05:
                bad.append("%s says %s h at %s, expected_cell_seconds says "
                           "%.1f h" % (fn, got_s, dest, want))

    print("9. runtime     %d cells checked, %d mismatched" % (n, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# ---------------------------------------------------------------- 11. docstrings
# Every .py this repo owns.  master.py is excluded because it is GENERATED: its
# contents are the four modules, which are checked here at source, and
# build_master.py strips their module docstrings by design.
FIRST_PARTY_PY = (["build_master.py", "run_pipeline.py", "ui.py", "ui_meta.py",
                   "verify.py", "verify_stage3.py", "verify_stage1.py",
                   "tree_check.py",
                   "launch_ui.py", "platform_check.py",
                   os.path.basename(__file__)]
                  + list(MODULES.values()) + CAMPAIGN_PY)


def check_docstrings() -> bool:
    """Every module, class and function in the repo's own Python has a docstring.

    A ratchet, on the same argument as check 6.  This repo's premise is that a
    number without its reasoning attached gets "fixed" by the next person, and
    that applies to code as much as to config: 87 definitions carried neither a
    docstring nor a leading comment when this was first measured, most of them
    in `ui.py` and `launch_ui.py`, which are almost entirely made of Windows
    traps that explain why the code looks the way it does.

    NESTED functions count.  Several of the sharpest notes in here are on a
    six-line closure -- `_as_designation` is the NEOWISE float-key bug, and
    `_truthy` is the `.astype(bool)` trap -- and exempting them by size would
    exempt exactly the ones worth reading.
    """
    gone = absent(FIRST_PARTY_PY)
    bad = []
    n = 0
    for rel in FIRST_PARTY_PY:
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            continue
        try:
            tree = ast.parse(read(path))
        except SyntaxError as exc:
            bad.append("%s: could not parse (%s)" % (rel, exc))
            continue
        n += 1
        if not ast.get_docstring(tree):
            bad.append("%s has no module docstring" % rel)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef)):
                continue
            n += 1
            if not ast.get_docstring(node):
                bad.append("%s:%d  %s has no docstring"
                           % (rel, node.lineno, node.name))

    print("11. docstrings %d definitions checked, %d without one%s"
          % (n, len(bad),
             ", %d FILES NOT ON DISK" % len(gone) if gone else ""))
    for g in gone:
        print("     ! %s is first-party Python and is not on disk" % g)
    for b in bad[:20]:
        print("     ! " + b)
    if len(bad) > 20:
        print("     ! ... and %d more" % (len(bad) - 20))
    return not bad and not gone




# ------------------------------------------------------------------- 12. pairs
# The two documents that both claim to be CURRENT.  `versions.md` is excluded
# on purpose and is not an oversight: every section there names the release and
# the catalog it belongs to, so a superseded figure in it is correct rather than
# stale.  What makes a copy hazardous is two files that both assert TODAY.
CURRENT_DOCS = ("README.md", "CLAUDE.md")

# The register's own table header, verbatim.  Its rows are the allowlist, so
# they must not also be counted as one side of a pair; a register entry quotes
# the numbers it registers by design.
REGISTER_HEADER = "| the shared measurement | in README under | here under |"

# A dotted version (`1.21.0`, `v1.17.7`) is an identifier, not a measurement,
# and `[calc v1.12.0](versions.md#calc-v1120--transportation-v1100)` produced
# three "shared numbers" out of one anchor.  Both are stripped before
# tokenising rather than filtered after, because the anchor's digits are not
# separable from a real figure once they are tokens.
_SEMVER = re.compile(r"v?\d+\.\d+\.\d+")
_LINK_TARGET = re.compile(r"\]\([^)]*\)")
_NUMBER = re.compile(r"\d[\d,]*\.\d+|\d[\d,]{3,}")
_YEAR = re.compile(r"(?:19|20)\d\d")


def _figures(line: str) -> set:
    """The distinctive numbers on one line: decimals and thousands, no noise.

    Distinctive means a number specific enough that two files carrying three of
    them are quoting one measurement rather than coinciding.  Small integers
    are excluded for that reason -- a line with `2`, `5` and `64` on it shares
    those with half the repo.
    """
    line = _LINK_TARGET.sub("]()", line)
    line = _SEMVER.sub(" ", line)
    return {m.group(0) for m in _NUMBER.finditer(line)
            if not _YEAR.fullmatch(m.group(0))}


def check_pairs() -> bool:
    """No measurement is quoted in BOTH current-claiming docs off the register.

    CLAUDE.md prescribes this hunt in prose ("hunting sentences that share
    three or more distinctive numbers across two files") and carries a table of
    the pairs it found.  Until 2026-09-08 the hunt itself was rebuilt from that
    description each time somebody ran it, which is the same "written from
    memory and thrown away" shape that `verify.py`'s header argues against, and
    it had the same result: the run that finally committed it found a pair the
    register had missed since the register was written, and it was the
    project's four headline numbers.

    The register table is the ALLOWLIST rather than the target.  A pair is
    fine when it is written down, because this file's job is the reasoning and
    README's is the answer and the reasoning reads badly with the answer
    removed; what is not fine is a pair nobody knows about, because nobody will
    move both.  So this fails on an UNREGISTERED pair only, and the fix is
    either to cut one copy or to add the row.
    """
    missing_current = ["%s claims to be current and is not on disk" % g
                       for g in absent(CURRENT_DOCS)]
    reg_tokens, lines = set(), {}
    for doc in CURRENT_DOCS:
        path = os.path.join(REPO, doc)
        if not os.path.exists(path):
            continue
        rows, in_register = [], False
        for i, raw in enumerate(read(path).splitlines(), 1):
            if raw.strip() == REGISTER_HEADER:
                in_register = True
                continue
            if in_register:
                # The table ends at the first line that is not one of its rows.
                if raw.startswith("|"):
                    reg_tokens |= _figures(raw)
                    continue
                in_register = False
            rows.append((i, raw, _figures(raw)))
        lines[doc] = rows

    a, b = CURRENT_DOCS
    unregistered, n_pairs = [], 0
    seen = set()
    for ia, la, fa in lines.get(a, ()):
        if len(fa) < 3:
            continue
        for ib, lb, fb in lines.get(b, ()):
            shared = fa & fb
            if len(shared) < 3:
                continue
            n_pairs += 1
            missing = shared - reg_tokens
            if not missing:
                continue
            key = tuple(sorted(shared))
            if key in seen:
                continue
            seen.add(key)
            unregistered.append((sorted(missing), a, ia, la, b, ib, lb))

    for gone in missing_current:
        print("     ! " + gone)
    print("12. pairs      %d cross-doc number pairs, %d not on the register"
          % (n_pairs, len(unregistered)))
    for missing, fa, ia, la, fb, ib, lb in unregistered:
        print("     ! %s and %s quote %s and it is not on the register"
              % (fa, fb, ", ".join(missing)))
        print("         %s:%d  %s" % (fa, ia, la.strip()[:110]))
        print("         %s:%d  %s" % (fb, ib, lb.strip()[:110]))
    if unregistered:
        print("       Cut one copy, or add a row to CLAUDE.md's register table")
        print("       under \"AND CHECK THE OTHER FILE\".")
    return not unregistered and not missing_current


# ---------------------------------------------------------------- 10. transfer
def check_transfer(before: str, after: List[str]) -> bool:
    """Every distinctive number in `before` must survive somewhere in `after`.

    This is the check for a reorganisation.  A line-level diff cannot do it:
    when the docs were split into versions.md a line diff reported 302
    differences and could not tell 26 dropped measurements from a reflow."""
    old = read(before)
    hay = "\n".join(read(p) for p in after)
    seen: Dict[str, str] = {}
    for m in TOKEN.finditer(old):
        tok = m.group(0)
        if tok in seen or YEAR.fullmatch(tok):
            continue
        a = old.rfind("\n", 0, m.start()) + 1
        b = old.find("\n", m.end())
        seen[tok] = old[a:b if b > 0 else None].strip()
    lost = [(t, c) for t, c in seen.items() if t not in hay]
    print("10. transfer   %d distinctive numbers in %s, %d lost"
          % (len(seen), os.path.basename(before), len(lost)))
    for t, c in sorted(lost):
        print("     ! %-14s | %s" % (t, c[:110]))
    return not lost


# --------------------------------------------------------------------- driver
# --------------------------------------------------------- 13. harness scope
# Every section `verify.py` PRINTS, as `print("\n<N>. <NAME>")`.  That is the
# ground truth for "which checks are there", because it is what a run emits and
# what every document tells a reader to count.
VERIFY_SECTION = re.compile(r'print\(\s*"\\n(\d+)\.\s')

# A numbered line of the module docstring's own list of checks.
VERIFY_LIST_ITEM = re.compile(r"^ {4}(\d+)\.\s+\S", re.M)

# README's table of what each check catches: "| 4 | mass ledger | ... |".
#
# ⚠️  ANCHORED ON ITS SECTION, BECAUSE README CARRIES TWO SUCH TABLES.  The
# other one is `verify_docs.py`'s own checks, under the same "| # | check |"
# heading a few hundred lines away, and a pattern loose enough to read one
# reads both -- which on the first run of this check reported that verify.py
# ran twelve checks.  Two tables of the same shape in one document is exactly
# what this repo's register discipline is about.
README_VERIFY_SECTION = "## Verifying a change"
README_CHECK_HEADER = "| # | check | catches |"
README_CHECK_ROW = re.compile(r"^\| (\d+) \|", re.M)

# Every sentence that claims WHICH checks a subcommand runs.  All four forms
# this repo has actually used, in both files: a comment on the usage line, the
# BUDGET paragraph, and README's prose.  A claim written in a fifth form is not
# checked, which is why the message says to write it like one of these.
SCOPE_CLAIM = (
    re.compile(r"verify\.py invariants\s+# ([\d, to]+?) only; needs no baseline"),
    re.compile(r"`py verify\.py invariants` runs ([\d, to and]+?) and needs no"),
    re.compile(r"--skip prune parallel  # ~5 min: ([\d, to and]+)$", re.M),
    re.compile(r"turns off 2 and 3 and leaves ([\d, to and]+?) running"),
)


def _numbers(text):
    """The check numbers a phrase like "1 and 4 to 7" names, expanded."""
    out, parts = set(), re.split(r",| and ", text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        span = re.match(r"^(\d+)\s*(?:to|-)\s*(\d+)$", part)
        if span:
            out.update(range(int(span.group(1)), int(span.group(2)) + 1))
        elif part.isdigit():
            out.add(int(part))
    return out


def _function_body(src, name):
    """One top-level function's source, by slicing between `def` lines."""
    start = src.index("def %s(" % name)
    rest = src.find("\ndef ", start)
    return src[start:rest if rest != -1 else len(src)]


def check_harness_scope() -> bool:
    """Which checks `verify.py` runs, against every document that says.

    🚨  THIS EXISTS BECAUSE THE COUNT ROTTED IN THE FILE NAMED AS ITS OWN
    AUTHORITY.  CLAUDE.md and README both tell a reader to count the checks in
    `verify.py`'s header rather than quote a number; on 2026-09-16 that header
    was wrong in three places at once and README in a fourth, all of them
    omitting check 7, which had landed a release earlier.  `cmd_check`'s own
    docstring records the same rot being found and fixed ONCE before -- in the
    docstring, not in the header ten lines above it, which is this repo's
    standing failure of fixing one half of a defect class.

    ⚠️  A count nothing checks is a number waiting to rot, and CLAUDE.md's rule
    is that the fix is a checker or a deletion, never a correction.  Deleting
    was not available here: a reader has to be told which subcommand runs what
    before choosing one, and "count them" is the advice that failed.  So this
    derives the answer from the code and holds all four claims to it.

    Ground truth is what a run PRINTS, not what any list says, because the
    numbering a reader sees on screen is the thing the documents are describing.
    """
    bad: List[str] = []
    vp = os.path.join(REPO, "verify.py")
    if absent(("verify.py",)):
        print("13. scope      1 NOT ON DISK (verify.py)")
        return False
    src = read(vp)

    runs = {}
    for fn in ("cmd_check", "cmd_invariants"):
        try:
            runs[fn] = {int(n) for n in VERIFY_SECTION.findall(_function_body(src, fn))}
        except ValueError:
            bad.append("verify.py has no %s to read its sections from" % fn)
            runs[fn] = set()
    # Check 1 is printed as part of the baseline comparison rather than as a
    # numbered banner, so it is added from the command that owns it instead of
    # being inferred.  Asserting it is present keeps that from going stale too.
    if runs.get("cmd_check") and 1 not in runs["cmd_check"]:
        runs["cmd_check"].add(1)
    every = runs.get("cmd_check", set())
    n = 0

    # -- the module docstring's own numbered list --------------------------
    listed = {int(x) for x in VERIFY_LIST_ITEM.findall(src.split('"""')[1])}
    n += 1
    if listed != every:
        bad.append("verify.py's docstring lists checks %s and it runs %s"
                   % (sorted(listed), sorted(every)))

    # -- README's table of what each check catches -------------------------
    readme = read(os.path.join(REPO, "README.md"))
    start = readme.find(README_VERIFY_SECTION)
    if start == -1:
        bad.append("README has no %r section to find the check table in"
                   % README_VERIFY_SECTION)
        section = ""
    else:
        # To the next heading of ANY level, not the next `##`: "Verifying a
        # change" has five `###` subsections under it and the last of them
        # carries verify_docs.py's own check table, in the same shape.
        nxt = re.search(r"^#{2,6} ", readme[start + 1:], re.M)
        section = (readme[start:start + 1 + nxt.start()] if nxt
                   else readme[start:])
    # From the table's own header to the first line that is not a row, rather
    # than by matching row TEXT: check 6 is "Stage 2 tables" and a pattern
    # keyed on a lower-case name silently dropped it, so the check quietly
    # measured six of seven -- which is the defect this check exists for,
    # committed inside the check itself on its first run.
    head = section.find(README_CHECK_HEADER)
    rows = ""
    if head == -1:
        bad.append("README's %r section has no %r table"
                   % (README_VERIFY_SECTION, README_CHECK_HEADER))
    else:
        for line in section[head:].split("\n")[2:]:
            if not line.startswith("|"):
                break
            rows += line + "\n"
    tabled = {int(x) for x in README_CHECK_ROW.findall(rows)}
    n += 1
    if tabled != every:
        bad.append("README's check table under %r covers %s and verify.py "
                   "runs %s" % (README_VERIFY_SECTION, sorted(tabled),
                                sorted(every)))

    # -- every claim about what a subcommand runs --------------------------
    # `invariants` is whatever cmd_invariants prints; the `--skip` loop is
    # everything cmd_check prints minus the two checks the flag turns off.
    want = {"invariants": runs.get("cmd_invariants", set()),
            "skip": every - {2, 3}}
    found = 0
    for text, where in ((src, "verify.py"), (readme, "README.md")):
        for pattern in SCOPE_CLAIM:
            for claim in pattern.findall(text):
                found += 1
                n += 1
                got = _numbers(claim)
                # Which claim this is: the two `--skip` forms name 2 and 3, the
                # two `invariants` forms do not.
                key = "skip" if "skip" in pattern.pattern or "turns off" in pattern.pattern \
                    else "invariants"
                if got != want[key]:
                    bad.append("%s says %r runs %s, the code runs %s"
                               % (where, claim.strip(), sorted(got),
                                  sorted(want[key])))
    if found < 4:
        # Not a skip.  These sentences are the thing this check exists for, and
        # a reworded one that no pattern matches is silently unchecked -- which
        # is how the rot got in.
        bad.append("only %d of the 4 known scope sentences matched; one has "
                   "been reworded, so rewrite it in the existing form or add "
                   "the form to SCOPE_CLAIM" % found)

    print("13. scope      %d claims checked against verify.py's %d checks, "
          "%d wrong" % (n, len(every), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def main(argv: Optional[List[str]] = None) -> int:
    """Run every check except 10, plus 10 if `--before` names a snapshot.

    Returns the process exit code: 0 if everything passed, 1 otherwise.

    Every check runs even after one fails, because the point of a docs sweep is
    the whole list: stopping at the first mismatch would hide the other nine.
    """
    p = argparse.ArgumentParser(
        description="Documentation verification (see the module docstring).")
    p.add_argument("--before", nargs="+", metavar=("OLD", "NEW"),
                   help="OLD.md then the file(s) its content should now be in; "
                        "adds check 10")
    args = p.parse_args(argv)

    # The tree check runs FIRST and gates everything under it: every check
    # below reads files off this disk, so if the disk is not serving what git
    # holds, their verdicts are about bytes nobody committed.  It also reads
    # every tracked file, which is the materialisation the Drive mount needs
    # anyway, so running it here makes the checks below safer as well as
    # checked.  See tree_check.py.
    ok = tree_check.assert_tree()
    mods = load_modules()
    for fn in (lambda: check_defaults(mods),
               lambda: check_versions(mods),
               lambda: check_row_counts(mods),
               check_links,
               check_structure,
               check_dashes,
               check_manifests,
               check_help,
               check_runtime,
               check_docstrings,
               check_pairs,
               check_harness_scope):
        ok = fn() and ok
    if args.before:
        if len(args.before) < 2:
            p.error("--before needs the old file and at least one new one")
        ok = check_transfer(args.before[0], args.before[1:]) and ok

    print("\n" + ("OK" if ok else "*** FAILURES ABOVE ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
