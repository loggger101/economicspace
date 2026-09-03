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
import os
import re
import sys
import tokenize
from typing import Dict, List, Optional, Tuple



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
                 "SPARK_SETUP.md"]

# The campaign scripts.  Prose a reader sees, checked whole like the root
# scripts rather than comments-only like modules/: they hold no reference table,
# so nothing in them is written into a CSV and none of their text is data.
CAMPAIGN_PY = ["campaign/analyse.py", "campaign/extra_checks.py",
               "campaign/memwatch.py", "campaign/rig_bounds.py",
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
    files = [d for d in LINKED_DOCS if os.path.exists(os.path.join(REPO, d))]
    anchors = {os.path.normpath(os.path.join(REPO, d)):
               slugs(os.path.join(REPO, d)) for d in files}
    bad, n = [], 0
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
    bad = []
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
           # Not Python, but prose a reader sees, and it was outside the
           # ratchet long enough to collect two em-dashes.  The hook's header
           # is the only account of the Drive stat-cache bug there is.
           # run.sh is here for the same reason and one more: it is the only
           # account of which run.bat traps do and do not carry to POSIX.
           ".githooks/drive-restat.sh", "Dashboard.vbs",
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
    bad, files = [], 0

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
          "(em/en dash, or a line opening with a bare comma)"
          % (files, len(bad)))
    for b in bad[:20]:
        print("     ! " + b)
    if len(bad) > 20:
        print("     ! ... and %d more" % (len(bad) - 20))
    return not bad


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
        req = [re.split(r"[<>=!~]", r)[0].strip() for r in req]
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
CISLUNAR_ROW = re.compile(
    r"^\|\s*`cislunar`\s*\|\s*\*{0,2}([\d,]+)\s*s\*{0,2}\s*"
    r"\|\s*\*{0,2}([\d,]+)\s*s\*{0,2}\s*"
    r"\|\s*\*{0,2}([\d,]+)\s*s\*{0,2}\s*"
    r"\|\s*\*{0,2}([\d,]+)\s*s\*{0,2}\s*\|", re.M)


def check_runtime() -> bool:
    """README's cislunar wall clock, against `calc.MEASURED_CELL_SECONDS`.

    Every user-facing quote of the beneficiation and programme-search cost
    ratios now DERIVES from that dict, so the banners cannot go stale on their
    own.  What can still drift is the docs: README tabulates the same four
    numbers in prose, and prose is what this repo gets wrong.  Pinning the two
    together means a re-measurement has exactly one place to start and one
    check that says whether it finished.
    """
    try:
        sys.path.insert(0, REPO)
        with contextlib.redirect_stdout(io.StringIO()):
            import master as _m
    except Exception as exc:                       # noqa: BLE001
        print("9. runtime     SKIPPED (%s: %s)" % (type(exc).__name__, exc))
        return True

    cells = getattr(_m, "MEASURED_CELL_SECONDS", None)
    if not cells:
        print("9. runtime     SKIPPED (no MEASURED_CELL_SECONDS in master)")
        return True

    m = CISLUNAR_ROW.search(read(os.path.join(REPO, "README.md")))
    bad, n = [], 0
    if m is None:
        bad.append("README has no `cislunar` wall-clock row to check")
    else:
        # column order in README: raw N=1, raw searched, benef N=1, benef+search
        want = [cells[(False, False)], cells[(False, True)],
                cells[(True, False)], cells[(True, True)]]
        labels = ["raw N=1", "raw searched", "benef N=1", "benef+searched"]
        for got_s, exp, lab in zip(m.groups(), want, labels):
            n += 1
            got = int(got_s.replace(",", ""))
            if got != exp:
                bad.append("README cislunar %-15s says %s s, "
                           "MEASURED_CELL_SECONDS says %d s" % (lab, got_s, exp))

    print("9. runtime     %d cells checked, %d mismatched" % (n, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# ---------------------------------------------------------------- 11. docstrings
# Every .py this repo owns.  master.py is excluded because it is GENERATED: its
# contents are the four modules, which are checked here at source, and
# build_master.py strips their module docstrings by design.
FIRST_PARTY_PY = (["build_master.py", "run_pipeline.py", "ui.py", "ui_meta.py",
                   "verify.py", "launch_ui.py", "platform_check.py",
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
    bad, n = [], 0
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

    print("11. docstrings %d definitions checked, %d without one" % (n, len(bad)))
    for b in bad[:20]:
        print("     ! " + b)
    if len(bad) > 20:
        print("     ! ... and %d more" % (len(bad) - 20))
    return not bad


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

    mods = load_modules()
    ok = True
    for fn in (lambda: check_defaults(mods),
               lambda: check_versions(mods),
               lambda: check_row_counts(mods),
               check_links,
               check_structure,
               check_dashes,
               check_manifests,
               check_help,
               check_runtime,
               check_docstrings):
        ok = fn() and ok
    if args.before:
        if len(args.before) < 2:
            p.error("--before needs the old file and at least one new one")
        ok = check_transfer(args.before[0], args.before[1:]) and ok

    print("\n" + ("OK" if ok else "*** FAILURES ABOVE ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
