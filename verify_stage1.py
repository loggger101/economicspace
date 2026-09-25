# -*- coding: utf-8 -*-
"""Stage 1 verification: the catalog on disk is the pinned release, intact.

    py verify_stage1.py

WHAT STAGE 1 IS NOW.  It does not build the catalog; it installs one published
build of it, a `data-YYYY-MM-DD` release of the AsteroidCatalog repository
pinned by `CatalogConfig.catalog_release`.  The builder, and the traps its own
test suite executes (the designation regex, the float-typed merge key, the
distinct-value lookup), live in that repository and are verified there.  What
is left to verify HERE is the seam: that the pin names a real release written
against this pipeline's data contract, and that the bytes on disk are that
release's bytes.

🚨  IT NEVER WRITES THE CATALOG.  Checks 1, 2 and 5 read the release's two small
files (its manifest and `taxonomy.json`) over the network; everything else
reads what Stage 1 installed.  Installing is Stage 1's job.

THREE CLASSES OF CHECK.

    1        THE SEAM.  The pinned release exists, names itself, and is the
             data contract this pipeline is written against.  Run first,
             because every other check describes whatever release it names.
    2, 5     THE RELEASE'S TABLES.  The composition tables the catalog was
             built with, as the release ships them.  No catalog needed, so
             these run on CI too.
    3, 4, 8  AGAINST THE CATALOG ON DISK.  These skip, loudly and with a
             reason, when no release is installed -- which on CI is always,
             because `asteroid_pipeline/` is gitignored in full.

⚠️  The numbering is historical rather than an order.  2 and 8 keep the
numbers they had when this file verified the builder in place, so a release
note that names one still points at the same check.  The old 1, 3, 4, 5 and 9
tested the builder's internals and its installed revision; the builder's own
suite runs those now.

⚠️  CHECKS 6 AND 7 ARE RETIRED (master v1.36.0), AND THE REASON IS THE SAME.
6 held five bodies to literature values and 7 re-derived the composition
columns from `spectral_type` with a copy of the builder's lookup.  Both
re-tested the BUILD, which AsteroidCatalog now gates before it publishes
anything (`release.physical_problems`, `tools/audit_catalog.py`, and its test
suite), and check 3 already proves the bytes on disk are that published
build.  Both also went red on the first data-contract change, for correct
reasons: 1.4.0 pairs each mass with its own source's diameter, so the
literature diameters moved, and it types every body past 5.5 AU as D, so
composition stopped being a function of `spectral_type` alone.  A check that a
correct upstream release fails is a copy of the upstream's rules, not a guard.
The reference bodies are listed by `tools/audit_catalog.py` now.

⚠️  A CATALOG BUILT BEFORE STAGE 1 DOWNLOADED RELEASES HAS NO MANIFEST, and
check 3 fails on it by design: nothing says which build it is, so nothing can
say it is the pinned one.  Run Stage 1 to install the pin.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import sys

# Local: the working-tree guard every harness here runs first.  It is a
# sibling file rather than a copied function because four harnesses need
# it and a second copy of a check is the defect this repo catalogues
# oftenest.
import tree_check

REPO = os.path.dirname(os.path.abspath(__file__))

# Where Stage 1 installs: ASTEROID_PIPELINE_OUTPUT_DIR when it is set, as
# Stage 1 itself reads it, else ./asteroid_pipeline.  Read BEFORE load_stage1()
# points that variable at a temp dir.  Nothing here writes to it.
PIPELINE_DIR = (os.environ.get("ASTEROID_PIPELINE_OUTPUT_DIR")
                or os.path.join(REPO, "asteroid_pipeline"))


# The catalog every Stage 4 run reads.  Not regenerated here under any
# circumstance; see the module docstring.
CATALOG = os.path.join(PIPELINE_DIR, "asteroid_catalog.csv")

# The four fields whose sum is the composition invariant.  `Unknown` leaves
# every one of them None on purpose, which is the sentinel check 2 asserts.
FRACTIONS = ("metal_fraction", "silicate_fraction", "carbon_fraction",
             "ice_fraction")

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
    # The first release at data contract 1.4.0.  `derived_mass` and `orbit`
    # are that contract's two new labels.
    ("1.4.0", "2026-09-25"): {
        "rows": 1567469,
        "diameter_source": {
            "measured":                  149718,
            "derived_h_taxonomy_albedo": 105885,
            "derived_h_orbit_albedo":   1311819,
            "derived_h_measured_albedo":     31,
            "derived_mass":                  16,
        },
        "spectral_type_source": {
            "source":         171109,
            "albedo":          83405,
            "albedo_assumed": 1289645,
            "orbit":           23310,
        },
    },
    # The first published release, `data-2026-09-23`, as installed from GitHub.
    ("1.3.0", "2026-09-23"): {
        "rows": 1566618,
        "diameter_source": {
            "measured":                  149740,
            "derived_h_taxonomy_albedo": 105873,
            "derived_h_orbit_albedo":   1310985,
            "derived_h_measured_albedo":     20,
        },
        "spectral_type_source": {
            "source":         171108,
            "albedo":          84501,
            "albedo_assumed": 1310972,
            "unknown":            37,
        },
    },
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
    prints by design and this is not a run.  The installed files are then read
    from PIPELINE_DIR, under the names the module's config declares.
    """
    os.environ.setdefault("ASTEROID_PIPELINE_OUTPUT_DIR",
                          os.environ.get("TEMP") or "/tmp")
    sys.path.insert(0, os.path.join(REPO, "modules"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        import catalog
    return catalog


def installed(c, name_field: str) -> str:
    """The path Stage 1 installs one of its files to."""
    return os.path.join(PIPELINE_DIR, getattr(c.CONFIG, name_field))


def _sha256_bytes(data: bytes) -> str:
    """sha256 of bytes already in memory."""
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str) -> str:
    """sha256 of a file, read in 1 MB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# -----------------------------------------------------------------------------
# 1: THE SEAM.
# -----------------------------------------------------------------------------
def fetch_release(c):
    """The pinned release's manifest and taxonomy tables, or (None, None, why).

    Both are small.  The taxonomy is checked against the manifest's sha256
    before it is returned, so checks 2 and 5 describe the tables the release
    actually ships.
    """
    import requests

    cfg = c.CONFIG
    base = "%s/%s/" % (cfg.release_base_url.rstrip("/"), cfg.catalog_release)
    try:
        resp = requests.get(base + "manifest.json", timeout=60)
        if resp.status_code == 404:
            return None, None, "no release %r at %s" % (cfg.catalog_release, base)
        resp.raise_for_status()
        manifest = resp.json()
        tax = requests.get(base + "taxonomy.json", timeout=60)
        tax.raise_for_status()
    except Exception as exc:                               # noqa: BLE001
        return None, None, "could not reach the release: %s: %s" % (
            type(exc).__name__, exc)
    entry = (manifest.get("files") or {}).get("taxonomy.json")
    if not entry or _sha256_bytes(tax.content) != entry.get("sha256"):
        return manifest, None, "taxonomy.json does not match the manifest's sha256"
    return manifest, json.loads(tax.content.decode("utf-8")), None


def check_release(c, manifest, why) -> bool:
    """The pin names a real release, which names itself, at our data contract.

    🚨  THE PRECONDITION FOR EVERY OTHER CHECK.  A pin that names nothing, or
    a release written against a different contract, makes every check below
    describe the wrong thing -- and Stage 1 would refuse it anyway, but only
    at run time.  This says so in a second, and on CI.
    """
    cfg = c.CONFIG
    if manifest is None:
        print("1. release       *** %s ***" % why)
        return False
    bad = []
    if manifest.get("release_tag") != cfg.catalog_release:
        bad.append("the manifest served for %s names itself %r"
                   % (cfg.catalog_release, manifest.get("release_tag")))
    if manifest.get("pipeline_version") != cfg.pipeline_version:
        bad.append("release %s is data contract %s; this pipeline is written "
                   "against %s" % (cfg.catalog_release,
                                   manifest.get("pipeline_version"),
                                   cfg.pipeline_version))
    if why:
        bad.append(why)
    print("1. release       %s, built %s, contract %s, %s bodies, %d wrong"
          % (cfg.catalog_release, manifest.get("catalog_date"),
             manifest.get("pipeline_version"),
             "{:,}".format(manifest.get("rows", 0)), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


# -----------------------------------------------------------------------------
# 2 and 5: THE RELEASE'S TABLES.
# -----------------------------------------------------------------------------
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


def check_pgm_table(t) -> bool:
    """The PGM table is a set of positive multipliers, and the lookup falls back.

    The fallback is what keeps an unlisted sub-type ("Mq") inheriting its
    parent class rather than silently dropping to chondritic, and the default
    is 1.0 rather than 0.0 so an unknown body is priced as ordinary rather than
    as worthless.  Those are properties of the TABLE the release ships; the
    lookup rule itself is the builder's, and its own suite tests it.
    """
    bad = []
    for k, v in t.PGM_ENRICHMENT_BY_TYPE.items():
        if not (isinstance(v, (int, float)) and v > 0):
            bad.append("%s -> %r is not a positive multiplier" % (k, v))
    parent = t.PGM_ENRICHMENT_BY_TYPE.get("M")
    if parent is None:
        bad.append("no M row: the metal-rich class carries no enrichment")
    print("5. pgm           %d types, %d wrong"
          % (len(t.PGM_ENRICHMENT_BY_TYPE), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def tables(taxonomy: dict):
    """The release's tables under the names checks 2 and 5 read them by."""
    import types
    return types.SimpleNamespace(
        TAXONOMY_COMPOSITION=taxonomy["TAXONOMY_COMPOSITION"],
        PGM_ENRICHMENT_BY_TYPE=taxonomy["PGM_ENRICHMENT_BY_TYPE"],
    )


# -----------------------------------------------------------------------------
# 3, 4 and 8: AGAINST THE CATALOG ON DISK.
# -----------------------------------------------------------------------------
def check_bytes(c, manifest) -> bool:
    """What Stage 1 installed is the pinned release, byte for byte.

    The CSV is hashed whole, a few seconds for ~1.2 GB, because a manifest
    beside a catalog that has since been edited, truncated by a sync client or
    copied in from another host would otherwise vouch for bytes it never saw.
    """
    cfg = c.CONFIG
    if manifest is None:
        print("3. bytes         *** NO MANIFEST: nothing says which build the "
              "catalog on disk is ***")
        print("     It predates Stage 1 installing releases, or was copied in")
        print("     without %s.  Run Stage 1 to install %s."
              % (cfg.manifest_filename, cfg.catalog_release))
        return False
    bad = []
    if manifest.get("release_tag") != cfg.catalog_release:
        bad.append("installed release is %s; the pin is %s -- run Stage 1"
                   % (manifest.get("release_tag"), cfg.catalog_release))
    want = [(installed(c, "catalog_filename"), manifest["catalog_csv"])]
    tax_entry = (manifest.get("files") or {}).get("taxonomy.json")
    if tax_entry:
        want.append((installed(c, "taxonomy_filename"), tax_entry))
    for path, entry in want:
        name = os.path.basename(path)
        if not os.path.isfile(path):
            bad.append("%s is missing" % name)
        elif os.path.getsize(path) != entry["bytes"]:
            bad.append("%s is %d bytes, the manifest says %d"
                       % (name, os.path.getsize(path), entry["bytes"]))
        elif _sha256_file(path) != entry["sha256"]:
            bad.append("%s does not match the manifest's sha256" % name)
    print("3. bytes         %s, %d files hashed, %d wrong"
          % (manifest.get("release_tag"), len(want), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def check_stamps(df, manifest) -> bool:
    """The rows say what the manifest says: one build date, one contract.

    Stage 4's stamp check reads these columns, not the manifest, so they are
    what has to agree with it.
    """
    stamp, date = catalog_identity(df)
    bad = []
    if stamp != manifest.get("pipeline_version"):
        bad.append("pipeline_version %r; the manifest says %r"
                   % (stamp, manifest.get("pipeline_version")))
    if date != manifest.get("catalog_date"):
        bad.append("catalog_date %r; the manifest says %r"
                   % (date, manifest.get("catalog_date")))
    if len(df) != manifest.get("rows"):
        bad.append("%d rows; the manifest says %s" % (len(df), manifest.get("rows")))
    print("4. stamps        catalog %s / %s, %s rows, %d wrong"
          % (stamp, date, "{:,}".format(len(df)), len(bad)))
    for b in bad:
        print("     ! " + b)
    return not bad


def read_catalog():
    """The columns checks 4 and 8 need, or None when the catalog is absent.

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
    want = ["diameter_source", "spectral_type_source", "pipeline_version",
            "catalog_date"]
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


def check_provenance(df) -> bool:
    """The provenance columns' domains are closed, and the census still holds.

    WHY THIS ONE SURVIVED WHEN 6 AND 7 DID NOT.  Whether the build is right is
    AsteroidCatalog's question, gated before it publishes.  Whether THIS
    pipeline can read what the build wrote is ours: the worked calculation
    branches on `diameter_source` to decide which derivation to print, and the
    dashboard's provenance panel sorts `spectral_type_source` into measured
    and inferred.  A label neither knows is a body both would describe wrongly,
    and nothing else here would notice.  Data contract 1.4.0 added two:
    `derived_mass` and `orbit`.

    The counts are compared only against the catalog identity they were taken
    from; see `CENSUS`.  A different build is reported, not failed, because
    re-running Stage 1 is a legitimate act that necessarily moves every one of
    them.
    """
    domains = {
        "diameter_source": {"measured", "derived_h_measured_albedo",
                            "derived_h_taxonomy_albedo",
                            "derived_h_orbit_albedo", "derived_mass",
                            "none"},
        "spectral_type_source": {"source", "tholen", "albedo",
                                 "albedo_assumed", "orbit", "unknown"},
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
        # 🚨  The domain findings are printed HERE too.  This branch used to
        # announce "domains clean" whatever `bad` held and return the failure
        # silently, so a new label failed the run without saying why.
        print("8. provenance    domains %s; census NOT compared, this is "
              "catalog %s / %s"
              % ("clean" if not bad else "%d wrong" % len(bad), stamp, date))
        for b in bad:
            print("     ! " + b)
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

    Checks 1, 2 and 5 always run; they need the network, not the catalog.
    Checks 3, 4 and 8 need an installed catalog and say what would make
    them run when it is absent, which on CI is always, because
    `asteroid_pipeline/` is gitignored in full.
    """
    print("=" * 70)
    print("  STAGE 1 VERIFICATION  -  the pinned catalog release, installed")
    print("=" * 70)
    tree_ok = tree_check.assert_tree()
    c = load_stage1()
    print("  catalog_release %s, data contract %s"
          % (c.CONFIG.catalog_release, c.CONFIG.pipeline_version))
    print("-" * 70)

    manifest, taxonomy, why = fetch_release(c)
    results = [tree_ok, check_release(c, manifest, why)]
    if taxonomy is not None:
        remote = tables(taxonomy)
        results += [check_taxonomy(remote), check_pgm_table(remote)]
    else:
        print("2,5. tables      NOT RUN: the release's taxonomy.json could not "
              "be read (see 1)")
        results.append(False)

    if not os.path.isfile(CATALOG):
        print("3,4,8. catalog   SKIPPED, no catalog at")
        print("       %s" % CATALOG)
        print("     These read the catalog Stage 1 installs.  Install it with")
        print("       py run_pipeline.py --stages 1")
        print("     which downloads the pinned release and checks its sha256.")
    else:
        mpath = installed(c, "manifest_filename")
        local = None
        if os.path.isfile(mpath):
            with io.open(mpath, encoding="utf-8") as fh:
                local = json.load(fh)
        results.append(check_bytes(c, local))
        df, missing = read_catalog()
        if missing:
            print("     (catalog predates %d column(s): %s)"
                  % (len(missing), ", ".join(missing)))
        if local is not None:
            results.append(check_stamps(df, local))
        results.append(check_provenance(df))

    print("-" * 70)
    if all(results):
        print("  OK  STAGE 1 VERIFIED - %d checks" % len(results))
        return 0
    print("  *** NOT VERIFIED *** - see the failing check above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
