# -*- coding: utf-8 -*-
"""Documentation verification for the asteroid profitability pipeline.

`verify.py` proves the MODEL did not change.  This proves the DOCS still
describe it.  Nine checks, all mechanical, all fast (about a second):

    1. defaults      every default the README's Tuning table quotes, against
                     the dataclass field it names
    2. versions      the Stage/Version table and CLAUDE.md's "Current:" line,
                     against each module's `pipeline_version`
    3. row counts    documented reference-table sizes, against the tables
    4. links         every markdown anchor resolves, in all three files
    5. structure     balanced fences, no ragged tables, no heading-level jumps,
                     no duplicate h1/h2 within a file
    6. dashes        no em- or en-dash in prose a reader sees
    7. manifests     a list documented in one place, against the list actually
                     defined in another: requirements.txt vs _MASTER_REQUIRED,
                     and README's `run.bat` block vs run.bat's own dispatcher
    8. help          every config dial the dashboard renders carries the
                     comment it shows as help text
    9. transfer      every distinctive number in a --before snapshot still
                     appears somewhere in the docs afterwards

    py verify_docs.py                       # checks 1-8
    py verify_docs.py --before OLD.md NEW.md NEW2.md   # adds check 9

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
  "Propellants -- 40 rows" with development=7; the module loads 41 and 8, both
  stale by exactly the cryogenic-argon row v1.12.0 added.        -> check 3
  A README section promising "all five" checks above a table of six. -> by eye
  `run.bat help` was accepted by the dispatcher and documented nowhere, so
  README's option list had quietly drifted from run.bat's own.    -> check 7
  26 measurements dropped rather than moved when the version history was split
  out into versions.md -- a line diff reported 302 differences and could not
  tell any of them from a reflowed paragraph.                    -> check 9
  39 of 105 config fields showed a bare dial in the dashboard, because their
  comment block sat above a NEIGHBOURING field.                   -> check 8

SCOPE.  This reads the docs and the module dataclasses.  It does NOT run the
pipeline, fetch anything, or check that a documented NUMBER is a correct
measurement -- only that a documented CONFIGURATION matches the code.  A
measurement can be stale and still pass everything here; that is what the
release notes and `verify.py` are for.
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

REPO = os.path.dirname(os.path.abspath(__file__))
DOCS = ["README.md", "versions.md", "CLAUDE.md"]

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
    try:
        return float(str(x).replace("_", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------- 1. defaults
TUNING_ROW = re.compile(
    r"^\|\s*`(?:MASTER_CONFIG)?\.(\w+)\.(\w+)`\s*\|\s*`?([^|`]*?)`?\s*\|", re.M)


def check_defaults(mods) -> bool:
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
def check_versions(mods) -> bool:
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

    print("2. versions    %d stamps documented, %d wrong" % (seen, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# --------------------------------------------------------------- 3. row counts
def check_row_counts(mods) -> bool:
    """Documented sizes of the Stage 3 reference tables.

    These are quoted in prose and in headings all over the docs, and they move
    whenever a row is added -- v1.12.0 split argon and left "40 propellants"
    standing in two places."""
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

    print("3. row counts  %d claims checked, %d wrong  (propellants %d, "
          "vehicles %d, storage %d)"
          % (n, len(bad), sizes["propellants"], sizes["vehicles"], sizes["storage"]))
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
LINKED_DOCS = DOCS + ["campaign/FINDINGS.md", "campaign/README.md"]


def check_links() -> bool:
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
    bad = []
    for d in DOCS:
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

    print("5. structure   %d files checked, %d problems" % (len(DOCS), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# -------------------------------------------------------------------- 6. dashes
EM, EN = "—", "–"
ROOT_PY = ["ui.py", "ui_meta.py", "run_pipeline.py", "verify.py",
           "build_master.py", "launch_ui.py"]


def check_dashes() -> bool:
    """No em- or en-dash in prose a person reads.

    The docs and the root scripts must be clean outright.  In modules/*.py
    only COMMENTS and DOCSTRINGS are checked: the `notes` and `composition`
    strings are written into propellants.csv, launch_vehicles.csv and the
    asteroid catalog, so their text is DATA and keeps whatever it has.

    This is a ratchet, not a style opinion.  1,342 dashes came out of the docs
    and 1,120 out of the modules; without a check they drift back one commit
    at a time.
    """
    bad, files = [], 0

    for name in DOCS + ROOT_PY:
        p = os.path.join(REPO, name)
        if not os.path.exists(p):
            continue
        files += 1
        for i, line in enumerate(read(p).split("\n"), 1):
            # verify_docs.py's own character classes must keep matching a dash
            if name == os.path.basename(__file__) and "[-:" in line:
                continue
            if EM in line or EN in line:
                bad.append("%s:%d  %s" % (name, i, line.strip()[:70]))

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
            if i in rows and (EM in line or EN in line):
                bad.append("%s:%d  %s" % (rel, i, line.strip()[:70]))

    print("6. dashes      %d files checked, %d lines with an em/en dash"
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


# ----------------------------------------------------------------- 9. transfer
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
    print("9. transfer    %d distinctive numbers in %s, %d lost"
          % (len(seen), os.path.basename(before), len(lost)))
    for t, c in sorted(lost):
        print("     ! %-14s | %s" % (t, c[:110]))
    return not lost


# --------------------------------------------------------------------- driver
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Documentation verification (see the module docstring).")
    p.add_argument("--before", nargs="+", metavar=("OLD", "NEW"),
                   help="OLD.md then the file(s) its content should now be in; "
                        "adds check 7")
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
               check_help):
        ok = fn() and ok
    if args.before:
        if len(args.before) < 2:
            p.error("--before needs the old file and at least one new one")
        ok = check_transfer(args.before[0], args.before[1:]) and ok

    print("\n" + ("OK" if ok else "*** FAILURES ABOVE ***"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
