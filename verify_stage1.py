# -*- coding: utf-8 -*-
"""Stage 1 verification: the derivation chain still derives what it derived.

    py verify_stage1.py

WHY THIS FILE EXISTS.  `verify.py`'s header says in as many words that Stage 1
is not covered by it: "What is still NOT covered: Stage 3's validate(), and
Stage 1's derivation chain.  A change there can pass everything here and still
be wrong."  Stage 3's half became `verify_stage3.py` check 5.  This is the
other half, and until 2026-09-15 it was the only stage with no harness at all.

The gap mattered more than it looks.  CLAUDE.md's "Correctness invariants that
were expensive to find" is almost entirely a Stage 1 list -- the designation
regex, the float-typed merge key that cost NEOWISE four releases, the
`str.contains` metacharacters, the `.astype(bool)` trap, the composition
residual -- and every one of them was a rule written in prose that nothing
executed.  A prose invariant is a comment nobody applied, which is this
project's defect class 4.

🚨  IT NEVER FETCHES, AND THAT IS THE WHOLE DESIGN CONSTRAINT.  Stage 1 pulls
from JPL, which adds bodies daily, so RE-RUNNING Stage 1 to test Stage 1 would
produce a catalog of a different length that is comparable with nothing already
measured -- and CLAUDE.md's "RUNNING STAGE 2 OR STAGE 3 DESTROYS EVERY BASELINE
YOU HOLD" applies here with an extra edge, because Stage 1's output is the
862 MB input every other stage reads.  So every check below either runs a PURE
function against a synthetic frame, or reads the catalog already on disk.
Nothing here opens a socket.  This is the same reasoning catalog 1.1.1 used
when it verified `enrich_composition` in-process rather than by re-running the
stage.

TWO CLASSES OF CHECK, AND THE SPLIT IS DELIBERATE.

    1 to 5   PURE.  No catalog, no network, no baseline.  These are the
             documented traps, executed.  They run anywhere, including CI,
             where the catalog is gitignored and absent by construction.
    6 to 8   AGAINST THE CATALOG ON DISK.  These skip, loudly and with a
             reason, when it is not there.

⚠️  That split is what stops this becoming a harness that never runs.  A check
that skips on 100% of runs is a check that does not exist -- `verify_stage3.py`
check 4 spent its whole life in that state -- so the half that carries the
regression value is the half that needs no data.

⚠️  THE CATALOG ON DISK IS USUALLY OLDER THAN THIS MODULE, AND THAT IS NOT A
DEFECT.  It is stamped with the catalog `pipeline_version` that built it, and
Stage 1 is the stage nobody re-runs, so a gap is the normal case: at the time
of writing the file says 1.1.0 and the module says 1.2.0.  Check 7 reports the
gap and still compares, because the composition columns are a pure lookup on
the final taxonomy and must reproduce across releases that did not touch the
table.  Reproducing ACROSS a version gap is a stronger result than reproducing
within one, so it is printed rather than skipped.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))

# The catalog every Stage 4 run reads.  Not regenerated here under any
# circumstance; see the module docstring.
CATALOG = os.path.join(REPO, "asteroid_pipeline", "asteroid_catalog.csv")

# The four fields whose sum is the composition invariant.  `Unknown` leaves
# every one of them None on purpose, which is the sentinel check 2 asserts.
FRACTIONS = ("metal_fraction", "silicate_fraction", "carbon_fraction",
             "ice_fraction")

# The composition columns that are a PURE LOOKUP on the final `spectral_type`,
# mapped to the table field each comes from.  `spectral_type_source` is
# deliberately NOT here: see check 7.
DERIVED_FROM_TAXONOMY = {
    "comp_group":             "group",
    "comp_density_est_gcm3":  "density_est_gcm3",
    "comp_metal_fraction":    "metal_fraction",
    "comp_silicate_fraction": "silicate_fraction",
    "comp_carbon_fraction":   "carbon_fraction",
    "comp_ice_fraction":      "ice_fraction",
}

# The standing literature spot-check, from CLAUDE.md's "Spot-check against
# literature rather than trusting row counts".  Values are quoted there to
# three decimals, so they are compared at three decimals: a comparator
# stricter than the artefact it compares reports failures that do not exist.
#
# ⚠️  CLAUDE.md prints "-" for Eros's diameter and density.  That means those
# two were not quoted in the table, NOT that the body lacks them; it carries
# 16.84 km and 2.342581 g/cm3, and it is `measured` like the other four.
LITERATURE = {
    "1":   ("Ceres",  939.400, 2.162, 9.074, "C"),
    "4":   ("Vesta",  522.770, 3.411, 5.342, "V"),
    "2":   ("Pallas", 513.000, 2.911, 7.813, "B"),
    "16":  ("Psyche", 222.000, 4.143, 4.196, "X"),
    "433": ("Eros",    16.840, 2.343, 5.270, "S"),
}

# The provenance census, pinned to the catalog IDENTITY that produced it.
#
# 🚨  PINNED BY IDENTITY RATHER THAN ASSERTED OUTRIGHT, and that is the
# difference between a check and a nuisance.  These counts are properties of
# one build of one catalog; Stage 1 is allowed to be re-run, and the day it is,
# every number here changes legitimately.  A check that went red on a correct
# action would be the cry-wolf shape CLAUDE.md records twice.  So the census is
# compared only when the file says it is that build, and merely REPORTED
# otherwise.
#
# 149,590 and 105,905 are the figures CLAUDE.md quotes; note they come from
# `diameter_source` while its third figure, 171,007, comes from
# `spectral_type_source`.  Reading all three off one column is the obvious
# misreading and it is why they are written out per column here.
CENSUS = {
    ("1.1.0", "2026-08-11"): {
        "rows": 1555667,
        "diameter_source": {
            "measured":                  149590,
            "derived_h_taxonomy_albedo": 105905,
            "derived_h_orbit_albedo":   1300152,
            # The v1.1.0 note that NEOWISE recovers IR albedo "for 132,691
            # bodies that had none" is about COLUMNS.  Twenty rows are sized
            # off it, which is what this row is here to keep true.
            "derived_h_measured_albedo":     20,
        },
        "spectral_type_source": {
            "source":         171007,
            "albedo":          84508,
            "albedo_assumed": 1300139,
            "unknown":            13,
        },
    },
}


def load_stage1():
    """Import Stage 1 without letting it create an output directory.

    The module resolves its default output dir at IMPORT time, so the env var
    has to be set first or importing it would make `asteroid_pipeline/` as a
    side effect of a read-only check.  Its import banner goes to /dev/null: it
    prints by design and this is not a run.
    """
    os.environ.setdefault("ASTEROID_PIPELINE_OUTPUT_DIR",
                          os.environ.get("TEMP") or "/tmp")
    sys.path.insert(0, os.path.join(REPO, "modules"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        import catalog
    return catalog


# -----------------------------------------------------------------------------
# 1 to 5: PURE.  No catalog, no network.
# -----------------------------------------------------------------------------
def check_designations(c) -> bool:
    """`_extract_canonical_designation` still matches its own spec table.

    THE TRAP.  A naive `^\\d+` yields "2024" for "2024 BX1", which is not null,
    not obviously wrong, and cross-matches an unrelated numbered body.  The
    function's docstring carries the surface-form table verbatim, so the spec
    is executable and this check is that docstring, run.

    The empty and "None" cases matter as much as the interesting ones: they
    must land on a missing value rather than on the STRING "None", which would
    join to nothing and look like a source that returned no rows.
    """
    import pandas as pd

    cases = [("1", "1"), ("00001", "1"), ("1 Ceres", "1"), ("433 Eros", "433"),
             ("(1) Ceres", "1"), ("2024 BX1", "2024 BX1"),
             ("1999 KW4", "1999 KW4"), ("Ceres", "Ceres"),
             ("", None), ("None", None)]
    got = c._extract_canonical_designation(pd.Series([a for a, _ in cases]))
    bad = []
    for (raw, want), g in zip(cases, list(got)):
        g = None if pd.isna(g) else g
        if g != want:
            bad.append("%r -> %r, want %r" % (raw, g, want))

    # The float-typed identifier, which is the same trap one column along: a
    # numeric id pandas has typed float64 renders as "3.0", which is not null,
    # not obviously wrong, and joins nothing.  It cost NEOWISE four releases of
    # contributing zero rows.
    f = c._extract_canonical_designation(pd.Series([1.0, 433.0, 69260.0],
                                                   dtype="float64"))
    for g in list(f):
        if isinstance(g, str) and g.endswith(".0"):
            bad.append("float64 id rendered as %r (the NEOWISE merge-key trap)"
                       % g)

    print("1. designations  %d surface forms + the float64 id, %d wrong"
          % (len(cases) + 3, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def check_taxonomy(c) -> bool:
    """The composition table's own invariants, which nothing had executed.

    🚨  CLAUDE.md SAID 0.76-0.96 AND THE TABLE HAS ALWAYS SAID 0.73-0.96.
    `Cgh` sums to 0.73 and `Cg`, `G` and `Ch` to 0.74-0.75, in every revision
    of `modules/catalog.py` that has ever existed.  `C` itself is exactly 0.76,
    which is where the number came from: somebody read the C row and
    generalised it to the complex.  Three documents quoted it forward.  The
    range is therefore NOT what is asserted here.

    What is load-bearing is the property the range was standing in for: every
    real class sums to strictly less than 1, so there IS a residual, and calc
    values it at a bulk-silicate floor rather than zero.  Asserting the
    PROPERTY rather than the interval is also what stops this check going red
    the day somebody re-measures a taxonomy row, which is a legitimate act.

    `Unknown` is the deliberate exception: all four fractions are None, so the
    residual is the whole body and everything is bulk silicate, which is the
    honest answer for a body whose taxonomy nothing knows.
    """
    bad = []
    sums = {}
    for name, entry in c.TAXONOMY_COMPOSITION.items():
        s = sum(float(entry.get(f) or 0.0) for f in FRACTIONS)
        sums[name] = s
        if name == "Unknown":
            if any(entry.get(f) is not None for f in FRACTIONS):
                bad.append("Unknown must leave every fraction None (sentinel)")
            continue
        if not (0.0 < s < 1.0):
            bad.append("%s sums to %.4f, outside (0, 1): the residual is what "
                       "calc floors at bulk silicate" % (name, s))
        for f in FRACTIONS:
            v = entry.get(f)
            if v is not None and not (0.0 <= float(v) <= 1.0):
                bad.append("%s.%s = %r is not a fraction" % (name, f, v))

    # M-type is not a bare metal core.  No M-type has ever been measured near
    # iron-meteorite density; Psyche is ~3.8-3.9 g/cm3, and the 0.80 / 5.30
    # pair is the value this table must never be "restored" to.
    m = c.TAXONOMY_COMPOSITION.get("M", {})
    if float(m.get("metal_fraction") or 0) >= 0.80:
        bad.append("M metal_fraction is back at %s; see CLAUDE.md, M-type is "
                   "not a bare metal core" % m.get("metal_fraction"))
    if float(m.get("density_est_gcm3") or 0) >= 5.0:
        bad.append("M density_est_gcm3 is back at %s; Psyche is ~3.8-3.9"
                   % m.get("density_est_gcm3"))

    real = [v for k, v in sums.items() if k != "Unknown"]
    print("2. taxonomy      %d classes, sums %.4f to %.4f, %d wrong"
          % (len(sums), min(real), max(real), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def check_pgm(c) -> bool:
    """`pgm_enrichment_for_type` falls back by first character, then to 1.0.

    The fallback is what keeps an unlisted sub-type ("Mq") inheriting its
    parent class rather than silently dropping to chondritic, and the default
    is 1.0 rather than 0.0 so an unknown body is priced as ordinary rather than
    as worthless.
    """
    bad = []
    parent = c.PGM_ENRICHMENT_BY_TYPE.get("M")
    cases = [("M", parent), ("Mq", parent), ("Zz", 1.0), (None, 1.0),
             ("", 1.0)]
    for t, want in cases:
        got = c.pgm_enrichment_for_type(t)
        if got != want:
            bad.append("%r -> %r, want %r" % (t, got, want))
    print("3. pgm           %d types, %d wrong" % (len(cases), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def check_by_distinct(c) -> bool:
    """`_by_distinct` still equals the per-row `.apply` it replaced.

    catalog 1.1.1 replaced twelve `.apply()` passes over 1.55 M rows with a
    lookup over the ~76 distinct taxonomy classes, worth 9.09 s to 2.35 s, and
    argued correctness from "all 12 derived columns identical" on one run.
    That was a measurement of one catalog, not a property, and nothing has
    re-checked it since.

    ⚠️  THE NaN CASES ARE THE POINT.  Two NaNs are not equal, so a
    distinct-value optimisation is exactly where a missing value falls through
    a lookup that `nan != nan` would break, and this repo has the
    `factorize`-not-`unique` rule written down for that reason.  The fixture
    therefore carries None, a bare float NaN and a repeat.
    """
    import pandas as pd

    # 🚨  THE LOOKUP MUST BE TOTAL, OR THIS CHECK CANNOT FAIL.  Written as
    # `TAXONOMY_COMPOSITION.get(t, {}).get("group")` it returns None for an
    # unknown key, so a `_by_distinct` that DROPS NaN keys and one that handles
    # them agree on NaN -- both give a missing value -- and the very path this
    # check exists for goes invisible.  Caught by reintroducing the defect and
    # watching the check stay green.  The real derivation falls back to the
    # `Unknown` entry, so the fixture does too, and a dropped NaN key then
    # shows up as a missing value where a real one is owed.
    def fn(t):
        """The taxonomy group, falling back to Unknown as the real chain does."""
        return (c.TAXONOMY_COMPOSITION.get(t)
                or c.TAXONOMY_COMPOSITION["Unknown"]).get("group")
    fixtures = [
        ["C", "M", None, "V", "Cgh", float("nan"), "M"],
        [None, None],
        ["Zz", "Zz", "C"],
        [],
    ]
    bad = []
    for i, data in enumerate(fixtures):
        s = pd.Series(data, dtype="object")
        fast = list(c._by_distinct(s, fn).fillna("<NA>"))
        slow = list(s.apply(fn).fillna("<NA>")) if len(s) else []
        if fast != slow:
            bad.append("fixture %d: %r != %r" % (i, fast, slow))
    print("4. by_distinct   %d fixtures, %d differing from a per-row apply"
          % (len(fixtures), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def check_lookup(c) -> bool:
    """`lookup_asteroid` survives regex metacharacters and an int64 column.

    TWO TRAPS IN ONE FUNCTION.  Designations and names carry regex
    metacharacters, so `str.contains` without `regex=False` made "(1) Ceres"
    match "1 Ceres" and raised `re.PatternError` on an unbalanced bracket.  And
    a numbered asteroid's designation looks like an integer, so a frame built
    from a slice where every row happens to be numbered comes back `int64` and
    a string comparison matches nothing -- "expected one row, found 0" about a
    body that is right there in the file.

    Both are the dtype-inferred-from-the-data shape: they work on the test
    slice and fail on the one that matters.
    """
    import pandas as pd

    def quiet(frame, query):
        """lookup_asteroid with its own report suppressed.

        It prints 'No entries found matching ...' on a miss, which is right
        for somebody at a prompt and is noise inside a check whose EXPECTED
        result on one probe is a miss.
        """
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            return c.lookup_asteroid(frame, query)

    bad = []
    meta = pd.DataFrame({"designation": ["1", "2024 BX1"],
                         "name": ["(1) Ceres", "z"]})
    try:
        n = len(quiet(meta, "(1) Ceres"))
        if n != 1:
            bad.append("'(1) Ceres' matched %d rows, want 1" % n)
    except Exception as exc:                               # noqa: BLE001
        bad.append("'(1) Ceres' raised %s: %s" % (type(exc).__name__, exc))
    try:
        # Must NOT cross-match: "1 Ceres" is a different surface form and the
        # bracketed one is not a regex that matches it.
        n = len(quiet(meta, "1 Ceres"))
        if n != 0:
            bad.append("'1 Ceres' cross-matched %d rows, want 0" % n)
    except Exception as exc:                               # noqa: BLE001
        bad.append("'1 Ceres' raised %s: %s" % (type(exc).__name__, exc))

    ints = pd.DataFrame({"designation": pd.Series([1, 433, 69260],
                                                  dtype="int64"),
                         "name": ["Ceres", "Eros", "x"]})
    try:
        n = len(quiet(ints, "433"))
        if n != 1:
            bad.append("int64 designation column: '433' matched %d rows, "
                       "want 1" % n)
    except Exception as exc:                               # noqa: BLE001
        bad.append("int64 designation column raised %s: %s"
                   % (type(exc).__name__, exc))

    print("5. lookup        3 probes, %d wrong" % len(bad))
    for b in bad:
        print("     ! " + b)
    return not bad


# -----------------------------------------------------------------------------
# 6 to 8: AGAINST THE CATALOG ON DISK.
# -----------------------------------------------------------------------------
def read_catalog():
    """The columns checks 6 to 8 need, or None when the catalog is absent.

    ⚠️  `usecols` RAISES on a column the file does not have, which matters the
    moment this reads anything a recent Stage 1 added: no catalog built before
    catalog 1.2.0 carries `orbit_condition_code`, and the same will be true of
    the next column somebody adds.  So the header is taken first and the
    request intersected with it, and what could not be read is REPORTED rather
    than silently dropped, because a silent gap reads as a clean bill of
    health.

    `float_precision="round_trip"` because the default CSV float parser is fast
    rather than correctly rounded; it is the fourth entry in `verify.py`'s
    table of harness bugs, and it belongs in a COMPARISON like this one and
    never in Stage 4's loader.
    """
    import pandas as pd

    if not os.path.isfile(CATALOG):
        return None, []
    want = (["designation", "name", "diameter_km", "density_gcm3",
             "rotation_period_h", "spectral_type", "diameter_source",
             "spectral_type_source", "pipeline_version", "catalog_date"]
            + list(DERIVED_FROM_TAXONOMY) + ["comp_pgm_enrichment"])
    header = pd.read_csv(CATALOG, nrows=0).columns
    have = [col for col in want if col in header]
    missing = [col for col in want if col not in header]
    df = pd.read_csv(CATALOG, usecols=have, dtype={"designation": str},
                     low_memory=False, float_precision="round_trip")
    return df, missing


def catalog_identity(df):
    """The (pipeline_version, catalog_date) this catalog was built as."""
    def one(col):
        """The single stamp value a provenance column should carry."""
        if col not in df.columns:
            return None
        vals = df[col].dropna().unique()
        return str(vals[0]) if len(vals) == 1 else None
    return one("pipeline_version"), one("catalog_date")


def check_literature(c, df) -> bool:
    """The five standing bodies still reproduce their literature values.

    This is the check that says the merge and the derivation chain did not
    quietly degrade, and it is the one a row count cannot make: the SsODNet
    outage that was not an outage returned 50,000 rows with no designation, and
    the tell was that V-types went to 3,988 because taxonomy was being guessed
    from albedo.

    ⚠️  `diameter_source == "measured"` on all five is the half a value
    comparison cannot see: it is what says H-derivation is not overwriting a
    measurement.
    """
    import pandas as pd

    bad = []
    for des, (nm, dia, dens, rot, typ) in LITERATURE.items():
        row = df[df["designation"] == des]
        if row.empty:
            bad.append("%s (%s) is not in the catalog" % (nm, des))
            continue
        row = row.iloc[0]
        for col, want, dp in (("diameter_km", dia, 3),
                              ("density_gcm3", dens, 3),
                              ("rotation_period_h", rot, 3)):
            if col not in df.columns:
                continue
            got = row[col]
            if pd.isna(got) or round(float(got), dp) != round(want, dp):
                bad.append("%s %s = %r, want %s to %d dp"
                           % (nm, col, got, want, dp))
        if "spectral_type" in df.columns and str(row["spectral_type"]) != typ:
            bad.append("%s spectral_type = %r, want %r"
                       % (nm, row["spectral_type"], typ))
        if ("diameter_source" in df.columns
                and str(row["diameter_source"]) != "measured"):
            bad.append("%s diameter_source = %r, want 'measured': "
                       "H-derivation is overwriting a measurement"
                       % (nm, row["diameter_source"]))
    print("6. literature    %d bodies, %d wrong" % (len(LITERATURE), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def check_rederive(c, df) -> bool:
    """The composition columns re-derive from the taxonomy each row ended up
    with, exactly.

    THIS IS STAGE 1's ANALOGUE OF A CELL HASH, and it is the strongest thing
    this file does: the committed catalog's derived columns, recomputed by
    today's table, row for row.

    ⚠️  ONLY THE PURE-LOOKUP COLUMNS, AND THE REASON IS SUBTLE.  The catalog's
    `spectral_type` is POST-FILL: `enrich_composition` fills a missing type
    from Tholen, then from albedo, then from the albedo assumed when the
    diameter was derived.  Feeding the filled column back would make all three
    fallbacks dead code, and `spectral_type_source` would come back "source"
    on every row and disagree with the file everywhere it had been filled --
    a failure that is an artefact of the fixture rather than a defect.  So the
    fallback chain is out of scope here and is covered by check 8's census
    instead, and what is compared is the part that IS a function of the final
    type.

    ✅  It reproduces across a version gap, which is a stronger result than
    reproducing within one: the file is written by whichever catalog release
    last ran, and the composition table has not moved under it.
    """
    import numpy as np
    import pandas as pd

    tax = c.TAXONOMY_COMPOSITION

    def look(t, field):
        """The table entry for a type, by exact match then root letter."""
        entry = tax.get(t) or tax.get(str(t)[:1]) or tax["Unknown"]
        return entry.get(field)

    bad, checked = [], 0
    pairs = list(DERIVED_FROM_TAXONOMY.items()) + [("comp_pgm_enrichment", None)]
    for col, field in pairs:
        if col not in df.columns or "spectral_type" not in df.columns:
            continue
        checked += 1
        if field is None:
            want = c._by_distinct(df["spectral_type"], c.pgm_enrichment_for_type)
        else:
            want = c._by_distinct(df["spectral_type"],
                                  lambda t, _f=field: look(t, _f))
        got = df[col]
        if got.dtype.kind in "fc":
            # Both-NaN counts as agreement; a float column cannot be compared
            # with != without turning every missing value into a difference.
            agree = (got.isna() & want.isna()) | np.isclose(
                got.fillna(-9.0), pd.to_numeric(want, errors="coerce").fillna(-9.0))
        else:
            agree = got.fillna("<NA>").astype(str) == want.fillna("<NA>").astype(str)
        n = int((~agree).sum())
        if n:
            bad.append("%s differs on %d of %d rows" % (col, n, len(df)))
    print("7. rederive      %d composition columns over %d rows, %d differing"
          % (checked, len(df), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def check_provenance(c, df) -> bool:
    """The provenance columns' domains are closed, and the census still holds.

    A soft failure does not shrink the catalog, it INFLATES it with guessed
    taxonomy, so the row count says nothing and the provenance columns say
    everything.  An unexpected label is the tell that a fetcher or a fallback
    has started writing something nobody reads.

    The counts are compared only against the catalog identity they were taken
    from; see `CENSUS`.  A different build is reported, not failed, because
    re-running Stage 1 is a legitimate act that necessarily moves every one of
    them.
    """
    domains = {
        "diameter_source": {"measured", "derived_h_measured_albedo",
                            "derived_h_taxonomy_albedo",
                            "derived_h_orbit_albedo", "none"},
        "spectral_type_source": {"source", "tholen", "albedo",
                                 "albedo_assumed", "unknown"},
    }
    bad = []
    for col, allowed in domains.items():
        if col not in df.columns:
            continue
        seen = set(df[col].dropna().astype(str).unique())
        for extra in sorted(seen - allowed):
            bad.append("%s carries %r, which is outside its documented domain"
                       % (col, extra))

    stamp, date = catalog_identity(df)
    expect = CENSUS.get((stamp, date))
    if expect is None:
        print("8. provenance    domains clean; census NOT compared, this is "
              "catalog %s / %s" % (stamp, date))
        for col in domains:
            if col in df.columns:
                counts = df[col].value_counts(dropna=False)
                print("     %s: %s" % (col, ", ".join(
                    "%s %d" % (k, v) for k, v in counts.items())))
        return not bad

    if len(df) != expect["rows"]:
        bad.append("row count %d, the census for %s / %s says %d"
                   % (len(df), stamp, date, expect["rows"]))
    for col, wanted in expect.items():
        if col == "rows" or col not in df.columns:
            continue
        counts = df[col].value_counts(dropna=False).to_dict()
        for label, n in wanted.items():
            got = int(counts.get(label, 0))
            if got != n:
                bad.append("%s[%s] = %d, census says %d" % (col, label, got, n))
    print("8. provenance    domains closed and the census reproduces "
          "(catalog %s / %s), %d wrong" % (stamp, date, len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def main() -> int:
    """Run every check and return the process exit code.

    Checks 1 to 5 always run.  Checks 6 to 8 need the catalog and say what
    would make them run when it is absent, which on CI is always, because
    `asteroid_pipeline/` is gitignored in full.
    """
    print("=" * 70)
    print("  STAGE 1 VERIFICATION  -  the derivation chain, without fetching")
    print("=" * 70)
    c = load_stage1()
    print("  catalog module pipeline_version %s" % c.CONFIG.pipeline_version)
    print("-" * 70)

    results = [check_designations(c), check_taxonomy(c), check_pgm(c),
               check_by_distinct(c), check_lookup(c)]

    df, missing = read_catalog()
    if df is None:
        print("6-8. catalog     SKIPPED, no catalog at")
        print("       %s" % CATALOG)
        print("     These three read the catalog already on disk. They do NOT")
        print("     build one: Stage 1 fetches from JPL, which adds bodies")
        print("     daily, so a rebuilt catalog is a different length and is")
        print("     comparable with nothing already measured. Copy the file in")
        print("     rather than regenerating it.")
    else:
        if missing:
            print("     (catalog predates %d column(s): %s)"
                  % (len(missing), ", ".join(missing)))
        results += [check_literature(c, df), check_rederive(c, df),
                    check_provenance(c, df)]

    print("-" * 70)
    if all(results):
        print("  OK  STAGE 1 VERIFIED - %d checks" % len(results))
        return 0
    print("  *** NOT VERIFIED *** - see the failing check above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
