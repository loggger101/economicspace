# -*- coding: utf-8 -*-
"""catalog, Module 1 of the Asteroid Profitability Pipeline.

THE BUILDER IS NOT IN THIS FILE ANY MORE.  It lives in `asteroid_catalog`, an
independent package, and this module is the adapter that drives it:

    https://github.com/loggger101/AsteroidCatalog

Why it left.  This module was 3,338 lines of survey fetchers, cross-matching,
validation and derivation, and nothing in its schema knew what a mine was.  A
merged asteroid catalog with honest provenance is useful to anyone doing
population statistics, survey planning or target selection, so the builder
became a package other projects can cite, and this pipeline became its first
consumer.  Second split of this kind, after Stage 3 to `spacecost`.

WHAT THIS FILE STILL OWNS, and why each did not move:

    CatalogConfig       the dials, because two of the defaults are this
                        project's rather than a library's: `output_dir` points
                        into `asteroid_pipeline/`, and a stage is expected to
                        create it.  `ui_meta` also scrapes each field's comment
                        block as the dashboard's help text for that dial, so
                        the comments here are UI copy and not just commentary
    the output location where Stage 2 and Stage 4 will look for the CSV
    the RUN & PREVIEW   the standalone-module behaviour every stage here has,
                        including the overwrite guard

NOTHING WAS RE-TYPED ON THE WAY OUT, and that is what makes the move provable.
The package was built by slicing source line ranges, 2,953 of this module's
3,338 lines.

STAGE 1 CANNOT BE RE-RUN TO VERIFY THAT, which is the difference from the
Stage 3 split.  `spacecost` could assert its CSVs byte-identical through both
paths; JPL adds bodies daily, so a rebuilt catalog here is a different length
and comparable with nothing already measured, and the file it would overwrite
is the 862 MB input every other stage reads.  So the extraction was checked
in-process instead, against the catalog already on disk -- the same reasoning
catalog 1.1.1 used when it verified `enrich_composition` without re-running the
stage.  25 checks, 107,521 values, 0 differing: every reference table leaf by
leaf at raw IEEE bit patterns with key order included, every pure function over
a stride sample of the real 1,555,667-row catalog, and all 24 function bodies
held to this module's own source text.

    to re-check that claim:   py verify_stage1.py

`pipeline_version` IS NOT A NUMBER THIS MODULE OWNS ANY MORE.  It is the
package's DATA CONTRACT, mirrored here, and the check below asserts the two are
equal -- so it moves when the package's moves and at no other time.

Active sources (all four are the package's now, fetched at run time):
    - NASA JPL SBDB                     orbital backbone: elements, H,
                                        designations, orbit quality
    - IMCCE SsODNet ssoBFT              best-of-literature diameter, albedo,
                                        mass, density, rotation, taxonomy
    - NEOWISE Diameters & Albedos V2.0  thermal-IR diameters and albedos
    - MP3C (Observatoire Cote d'Azur)   physical-properties compilation

Pipeline flow:
    Fetch  ->  Merge  ->  Derive diameters  ->  Validate  ->  Enrich  ->  Export
"""

# ──────────────────────────────────────────────────────────────────────────────
# INSTALLATION
# ──────────────────────────────────────────────────────────────────────────────
# Windows consoles default to cp1252, which cannot encode every character this
# file's progress output can carry -- force UTF-8 before anything prints.
import sys as _sys
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

import subprocess, sys

# `asteroid_catalog` is not on PyPI yet, so it installs from git.  The mapping
# is import-name -> pip argument, because for this one package those differ and
# a bare name in the install list would resolve to nothing.
# IF IT IS EVER PUBLISHED: replace the URL with a pinned version
# ("asteroid-catalog==0.1.0") and delete `_PIP_SPEC`; the rest of the block is
# already shaped for it.  Keep `requirements.txt` in step -- verify_docs
# check 7 holds every typed copy of this pin to the others.
_REQUIRED_PKGS = ["requests", "pandas", "numpy", "tqdm", "pyarrow",
                  "asteroid_catalog"]
_PIP_SPEC = {
    "asteroid_catalog":
        "git+https://github.com/loggger101/AsteroidCatalog@v0.1.1",
}
_missing = []
for _pkg in _REQUIRED_PKGS:
    try:
        __import__(_pkg)
    except ImportError:
        _missing.append(_PIP_SPEC.get(_pkg, _pkg))

if _missing:
    print(f"PKG  Installing: {_missing} ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q"] + _missing
    )
    print("OK  Install complete")
else:
    print("OK  All packages present")


# ──────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
import dataclasses
import json
import os
import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

import asteroid_catalog

# NEVER SPELL A NAME THE BUILD REWRITES.  `build_master.py` concatenates the
# four stage modules into `master.py` and resolves collisions with
# `word_replace`, a whole-word regex over the ENTIRE file text -- comments and
# string literals included, not only code.  For THIS module it rewrites three
# words: `CONFIG`, `build_catalog` and `lookup_asteroid`.
#
# ALIASING THE LOCAL NAME IS NOT ENOUGH, and that is the trap.  In
# `from asteroid_catalog import X as _y` the imported name X is still a bare
# word, so it is rewritten too and the import then fails against a package with
# no such attribute.  That exact mistake cost the Stage 3 split a release.
#
# The package exports collision-proof second names for the two functions that
# collide, and those are what is imported.  Everywhere else in this file, reach
# the package through `asteroid_catalog.` -- and read the built master.py
# rather than assuming, because this file and its concatenated copy are not the
# same text.
from asteroid_catalog import build_catalog_table as _pkg_build_catalog
from asteroid_catalog import lookup_body as _pkg_lookup_body

# The launcher to name in a printed instruction.  `py` is the Windows launcher
# and exists nowhere else, so a hint that says it is wrong advice on the host
# that most needs the hint.
_PY = "py" if os.name == "nt" else os.path.basename(sys.executable)

# Silence the chronic noise the data libraries emit during a typical run, but
# DON'T globally suppress everything, real RuntimeWarnings (e.g. divide-by-zero
# in our mass calculation) should still surface so we can spot bugs.
for _cat in (DeprecationWarning, FutureWarning, UserWarning):
    warnings.filterwarnings("ignore", category=_cat)

pd.set_option("display.max_columns", None)

# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT OUTPUT LOCATION
# ─────────────────────────────────────────────────────────────────────────────
# Colab keeps its scratch space at /content.  Anywhere else (local Windows,
# Linux, CI) that path is meaningless -- on Windows it silently resolves to
# C:\content -- so fall back to an ./asteroid_pipeline dir under the CWD.

def _default_output_dir() -> str:
    """Colab-aware default output directory."""
    env = os.environ.get("ASTEROID_PIPELINE_OUTPUT_DIR")
    if env:
        return env
    # Colab detection.  os.path.isdir("/content") alone is not enough: on
    # Windows a leading "/" is drive-relative, so it tests C:\content -- a
    # directory an earlier run of the pre-fix code may itself have created,
    # which would route output straight back to the path this function
    # exists to avoid.  Require a POSIX platform as well.
    if os.name == "posix" and os.path.isdir("/content"):
        return "/content/asteroid_pipeline"
    return os.path.join(os.getcwd(), "asteroid_pipeline")


_DEFAULT_OUTPUT_DIR = _default_output_dir()



# ═════════════════════════════════════════════════════════════════════════════
# ║                                                                           ║
# ║   ★  USER SETTINGS, EDIT THESE TO TUNE THE PIPELINE  ★                  ║
# ║                                                                           ║
# ║   Every knob the casual user is expected to touch lives in this single    ║
# ║   dataclass.  Each field has a brief note describing what it controls,    ║
# ║   the default value, and (where relevant) the range / common values.      ║
# ║                                                                           ║
# ║   Nothing below this block needs editing for normal use.                  ║
# ║                                                                           ║
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class CatalogConfig:
    """User-editable pipeline configuration.  See per-field comments below."""

    # ─── SOURCE TOGGLES ───────────────────────────────────────────────────────
    # Set any of these to False to skip that source.  An unreachable or empty
    # source is silently tolerated by the pipeline; you don't need to flip the
    # toggle just because a host is down.
    use_jpl:      bool = True   # NASA JPL Small-Body Database     (orbital + physical)
    use_mp3c:     bool = True   # MP3C @ Observatoire Côte d'Azur   (physical compilation)
    use_ssodnet:  bool = True   # SsODNet ssoBFT (IMCCE)            (mass, density, taxonomy, …)
    use_neowise:  bool = True   # NEOWISE V2.0 via IRSA TAP         (IR diameters + albedos)
    # To add a new catalog: write a fetch_<name>(config) function and add a
    # matching `use_<name>: bool = True` line here.

    # ─── FETCH LIMITS & NETWORK ──────────────────────────────────────────────
    # ONE CAP PER SOURCE, and 0 means "no cap, take the whole table".
    #
    # Until v1.1.0 `jpl_limit` was reused as the row cap for every source, which
    # quietly made the catalog SMALLER than any single source.  Each fetcher
    # takes its first N rows ordered by asteroid number, so four sources capped
    # at the same N return substantially the SAME N bodies; the merge then
    # collapses them and the union is ~N rather than 4N.  Raising the shared cap
    # to reach further down one source dragged every other source along with it.
    #
    # Measured 2026-08-08 against the live APIs, which is what the defaults are
    # sized from:
    #     JPL SBDB      1,554,321 asteroids   (139,582 with a measured diameter)
    #     SsODNet        ~1,200,000 rows      (~500 MB parquet, cached)
    #     NEOWISE V2.0     183,412 rows       (143,318 unique bodies w/ diameter)
    #     MP3C           varies; frequently unreachable
    #
    # 0 (unlimited) is the default because JPL is the only source of orbital
    # elements, so a body it does not return cannot be evaluated no matter what
    # the other sources know about it.  The full JPL pull is ~435 MB / ~80 s on
    # a warm connection; NEOWISE unlimited is ~19 MB / ~30 s.  Set a cap if you
    # want a fast interactive run: 50_000 reproduces the pre-v1.1.0 behaviour.
    jpl_limit:       int = 0   # 0 = all 1.55 M asteroids (orbital elements)
    ssodnet_limit:   int = 0   # 0 = whole cached ssoBFT table
    neowise_limit:   int = 0   # 0 = all 183 k NEOWISE rows

    # Ask IRSA for the NEOWISE table as an asynchronous (IVOA UWS) job rather
    # than a single synchronous request.  A sync query holds one connection
    # open for the server-side query AND the ~19 MB transfer, so a proxy
    # timeout anywhere in that window discards the whole result with nothing to
    # retry; that is the 502 that made NEOWISE contribute 0 rows to the run
    # behind the committed cislunar 2x2.  Async runs the job server-side and
    # leaves the result at a stable, re-fetchable URL.  Falls back to the
    # synchronous path on any failure, so turning this off only removes a way
    # to succeed.  Same ADQL and same rows either way, verified byte-identical.
    neowise_use_async: bool = True

    # How long to poll an async NEOWISE job before giving up and falling back.
    # The full table completes in well under a minute; this is a ceiling for a
    # service under load, not an expected wait.
    neowise_async_max_wait_s: int = 900
    mp3c_limit:      int = 0   # 0 = whatever MP3C will serve
    request_timeout: int = 300 # seconds per HTTP request before giving up (5 min)

    # ─── QUALITY GATES  (enforced in validate_and_filter) ────────────────────
    # `min_diameter_km` drops anything below this size.  Default 0.001 km =
    # 1 metre (essentially "keep everything that has a positive diameter").
    # Bump to e.g. 1.0 to focus on >=1-km bodies.
    min_diameter_km: float = 0.001

    # If True, asteroids with no spectral classification (Bus / Tholen) are
    # rejected.  Useful for compositional studies; False keeps more rows.
    require_spectral_type: bool = False

    # ─── DERIVED DIAMETERS  (v1.1.0) ─────────────────────────────────────────
    # validate_and_filter drops any body without a diameter, and only 139,582
    # of JPL's 1,554,321 asteroids have one measured.  1,553,812 have an
    # absolute magnitude H and a valid orbit, and diameter follows from H and
    # the geometric albedo exactly:
    #
    #     D_km = (1329 / sqrt(p_V)) * 10**(-H/5)          (Fowler & Chillemi 1992)
    #
    # so the ONLY thing being estimated is p_V.  With this on, the evaluable
    # population goes from ~139 k to ~1.55 M, an 11x larger catalog whose extra
    # rows carry a diameter uncertain by roughly the square root of the albedo
    # error, and a MASS uncertain by that cubed.  Every such row is tagged
    # `diameter_source = "derived_h_*"`; a measured diameter always wins, and
    # `derived_diameter_is_estimate` gives downstream code a single boolean to
    # filter on.  Turn this off for a measured-only catalog.
    derive_diameter_from_h: bool = True

    # Floor on DERIVED diameters only (km).  Measured diameters are governed by
    # `min_diameter_km` above and are never subject to this.  0.0 keeps every
    # derived body; raise it to trim the sub-kilometre tail, which is most of
    # the 1.4 M and is where the albedo assumption hurts most.
    min_derived_diameter_km: float = 0.0

    # ─── OUTPUT  (where the CSVs land) ───────────────────────────────────────
    # `output_dir` is created at startup if it doesn't exist.  On Colab the
    # default '/content/...' lives in the session sandbox, change to a Drive
    # path like '/content/drive/MyDrive/asteroids' to persist between runs.
    output_dir:        str = _DEFAULT_OUTPUT_DIR
    catalog_filename:  str = "asteroid_catalog.csv"
    rejected_filename: str = "rejected_entries.csv"

    # ─── BULK-DOWNLOAD CACHE  (SsODNet parquet & similar) ────────────────────
    # SsODNet's ssoBFT is ~500 MB.  We cache it once per `cache_max_age_days`
    # and re-use it between runs.  Bump max_age down to force a fresh pull.
    #
    # `cache_dir` controls WHERE the cache lives:
    #   • Empty string (default) → system tmp directory (good for Drive users:
    #                              the ~500 MB parquet does NOT round-trip
    #                              through Drive sync on every run).
    #   • Any absolute path      → that exact directory.
    # If you want the cache co-located with the catalog CSV instead, set this
    # to e.g. f"{output_dir}/_cache".
    cache_dir:           str   = ""

    # How long the ssoBFT parquet cache is reused before it is re-downloaded.
    # That download is ~500 MB, so raise this for repeated offline runs.
    cache_max_age_days:  float = 7.0

    # ─── PREVIEW & SUMMARY DISPLAY  (cosmetic, affects stdout only) ──────────
    preview_rows:           int = 10   # rows shown in CATALOG PREVIEW table
    top_n_spectral_types:   int = 20   # types listed in spectral-distribution bars

    # ─── PIPELINE VERSION  (bump when changing the schema) ───────────────────
    # Stamped into every output CSV, and the only way to tell which code
    # produced a given catalog.  BUMP IT when a change moves any number a run
    # produces.  The rule is ONE-DIRECTIONAL: changing a number means bumping,
    # and a bump does NOT mean a number changed, which is why nothing may read
    # a version as evidence that a result moved.
    # THE CHANGELOG IS versions.md, NOT THIS COMMENT.  It used to be 155 lines
    # of release notes sitting right here, a second copy of a record versions.md
    # already held, which is the documentation form of the defect this project
    # keeps cataloguing; it was also what the dashboard rendered as this field's
    # help text, because ui_meta scrapes a field's comment block.  Moved out on
    # 2026-09-02.  Two places to write, neither of them here:
    #     versions.md > Releases            what the release did, and what it
    #                                       measured to say so
    #     versions.md > Module changelogs   this module's own stamp-by-stamp
    #                                       record: Stage 1 changelog
    pipeline_version: str = "1.2.0"


# Instantiate and create the output dir.  Edit CONFIG values above this line
# (inside the dataclass); DO NOT mutate CONFIG fields here, that defeats the
# purpose of having a single editable source of truth.
CONFIG = CatalogConfig()
os.makedirs(CONFIG.output_dir, exist_ok=True)

def _check_catalog_config_surface() -> None:
    """Fail loudly if this module's dials and the package's have diverged.

    NOT NAMED `_check_config_surface`, WHICH IS WHAT THE STAGE 3 ADAPTER
    CALLS ITS EQUIVALENT.  `build_master.py` concatenates the four stage
    modules into one namespace and the last definition of a shared name
    wins, so two adapters with one name is a collision -- its AST scan
    says so on every build.  The two are not interchangeable copies
    (different dataclasses, different packages), so `_EXPECTED_DUPES` is
    the wrong answer and a distinct name is the right one.
    """
    mine   = {f.name for f in dataclasses.fields(CatalogConfig)}
    theirs = {f.name for f in dataclasses.fields(asteroid_catalog.CatalogConfig)}
    if mine != theirs:
        raise SystemExit(
            "STAGE 1 SETTINGS DRIFT: modules/catalog.py and asteroid_catalog "
            "no longer describe the same settings.\n"
            f"    only here             : {sorted(mine - theirs)}\n"
            f"    only asteroid_catalog : {sorted(theirs - mine)}\n"
            "Add the field to whichever side lacks it, or this run is "
            "configured by one and executed by the other."
        )


def _check_data_contract() -> None:
    """The stamp written into every row is the package's, mirrored here.

    A catalog stamped `1.2.0` has to mean one derivation chain.  If this
    module and the package disagree about the number, every CSV this stage
    writes is labelled with a version that describes different code.
    """
    if CONFIG.pipeline_version != asteroid_catalog.DATA_VERSION:
        raise SystemExit(
            "STAGE 1 CONTRACT DRIFT: this module stamps "
            f"{CONFIG.pipeline_version!r} and asteroid_catalog "
            f"{asteroid_catalog.DATA_VERSION!r}.\n"
            "The stamp is the PACKAGE's; mirror it here, or repin the package."
        )


_check_catalog_config_surface()
_check_data_contract()


def _as_package_config(config: "CatalogConfig"):
    """This module's dials as the package's, field for field.

    Built from `dataclasses.fields` rather than by listing names, so a field
    added on both sides carries over with no edit here.  `_check_catalog_config_surface`
    above is what makes that safe.
    """
    return asteroid_catalog.CatalogConfig(**{
        f.name: getattr(config, f.name) for f in dataclasses.fields(config)
    })


# ──────────────────────────────────────────────────────────────────────────────
# THE BUILDER, RE-EXPORTED
# ──────────────────────────────────────────────────────────────────────────────
# The same objects, not copies.  They are re-exported rather than reached
# through `asteroid_catalog.` because several things read them as attributes of
# THIS module: `verify_stage1.py`, the Colab paste, and every doc that tells a
# reader to call `catalog.enrich_composition`.  Re-exporting keeps every such
# caller working unchanged.
TAXONOMY_COMPOSITION         = asteroid_catalog.TAXONOMY_COMPOSITION
PGM_ENRICHMENT_BY_TYPE       = asteroid_catalog.PGM_ENRICHMENT_BY_TYPE
pgm_enrichment_for_type      = asteroid_catalog.pgm_enrichment_for_type

ALBEDO_FALLBACK              = asteroid_catalog.ALBEDO_FALLBACK
ALBEDO_BY_SPECTRAL_TYPE      = asteroid_catalog.ALBEDO_BY_SPECTRAL_TYPE
ALBEDO_BY_SEMI_MAJOR_AXIS_AU = asteroid_catalog.ALBEDO_BY_SEMI_MAJOR_AXIS_AU

# The fetchers.  Each returns an empty frame rather than raising when its
# source is unreachable, which is the soft-failure contract Stage 1 has always
# had; read the per-source MATCH counts, not the fetch counts.
fetch_jpl_sbdb               = asteroid_catalog.fetch_jpl_sbdb
fetch_ssodnet                = asteroid_catalog.fetch_ssodnet
fetch_neowise                = asteroid_catalog.fetch_neowise
fetch_mp3c                   = asteroid_catalog.fetch_mp3c

# The chain.
merge_sources                = asteroid_catalog.merge_sources
deduplicate_catalog          = asteroid_catalog.deduplicate_catalog
derive_missing_diameters     = asteroid_catalog.derive_missing_diameters
validate_and_filter          = asteroid_catalog.validate_and_filter
enrich_composition           = asteroid_catalog.enrich_composition

# Query utilities, and the two internals `verify_stage1.py` drives directly.
filter_by_region             = asteroid_catalog.filter_by_region
filter_by_spectral_group     = asteroid_catalog.filter_by_spectral_group
_extract_canonical_designation = asteroid_catalog._extract_canonical_designation
_by_distinct                 = asteroid_catalog.taxonomy._by_distinct
_resolve_cache_dir           = asteroid_catalog.config._resolve_cache_dir


def lookup_asteroid(catalog: pd.DataFrame, query: str) -> pd.DataFrame:
    """Find a body by designation, number or name.

    The package spells this `lookup_body` as well, and the second name is why
    this one can keep its own: see the import block above.  Module 4 defines a
    `lookup_asteroid` of its own over a different frame, so the build renames
    this one to `lookup_asteroid_catalog` in master.py.
    """
    return _pkg_lookup_body(catalog, query)


def build_catalog(config: CatalogConfig = CONFIG) -> pd.DataFrame:
    """Fetch every source, merge, derive, validate, enrich, and export.

    Delegates to `asteroid_catalog.build_catalog`, which is the same code this
    file used to contain, sliced rather than re-typed.

    VERBOSE IS TURNED ON HERE, AND THAT IS WHAT KEEPS STAGE 1's CONSOLE OUTPUT
    UNCHANGED BY THE SPLIT.  The package is silent by default because a library
    imported to read one taxonomy row has no business printing; a pipeline
    stage that is also the program does.  Ten messages print either way --
    those report a defect rather than a condition, and a diagnostic that has
    gone quiet reads exactly like a clean result.
    """
    asteroid_catalog.set_verbose(True)
    return _pkg_build_catalog(_as_package_config(config))


# Eagerly create the default cache dir so first-run prints reflect the real path
os.makedirs(_resolve_cache_dir(CONFIG), exist_ok=True)

print(f"OK  Configuration loaded - output dir: {CONFIG.output_dir}")
print(f"    Active sources  : "
      f"{', '.join(s for s, on in (('JPL', CONFIG.use_jpl), ('MP3C', CONFIG.use_mp3c), ('SsODNet', CONFIG.use_ssodnet), ('NEOWISE', CONFIG.use_neowise)) if on)}")
def _fmt_limit(n: int) -> str:
    """Render a row cap for the banner; 0 is unlimited, not zero rows."""
    return "unlimited" if not n else f"{n:,}"


print(f"    Fetch limits    : "
      f"JPL {_fmt_limit(CONFIG.jpl_limit)}  |  "
      f"SsODNet {_fmt_limit(CONFIG.ssodnet_limit)}  |  "
      f"NEOWISE {_fmt_limit(CONFIG.neowise_limit)}  |  "
      f"MP3C {_fmt_limit(CONFIG.mp3c_limit)}")
print(f"    Min diameter    : {CONFIG.min_diameter_km} km")
print(f"    Strict taxonomy : {CONFIG.require_spectral_type}")
print(f"    H-derived diam. : "
      f"{'on - bodies with no measured diameter are sized from H + albedo' if CONFIG.derive_diameter_from_h else 'off - measured diameters only'}")

print(f"OK  Taxonomy lookup ready - {len(TAXONOMY_COMPOSITION)} spectral types defined")
print(f"OK  PGM enrichment table ready - "
      f"{len(PGM_ENRICHMENT_BY_TYPE)} non-baseline spectral types "
      f"(M / Xe = 2.0x, V = 0.2x, A / R / O = 0.5x, others 1.0x)")


print("\nOK  Helper utilities available:")
print("    lookup_asteroid(catalog, 'Ceres')")
print("    filter_by_region(catalog, 2.0, 3.3)   # main-belt slice")
print("    filter_by_spectral_group(catalog, 'X-complex')  # metallic")


# ─────────────────────────────────────────────────────────────────────────────
# RUN & PREVIEW
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # All tunable values live in the USER SETTINGS block at the top of this file; 
    # edit CONFIG fields there, then re-run.


    # ── OVERWRITE GUARD ──────────────────────────────────────────────────────
    # A FETCHING stage writes over the only copy of its inputs, and there is no
    # undo: every `.verify` baseline and every committed measurement was taken
    # against the files this run is about to replace.  `run_pipeline.py` has
    # asked before doing that since 2026-08-23; running THIS FILE went nowhere
    # near that guard, which is the hole somebody fell into on 2026-09-17 while
    # smoke-testing an import, re-fetching three live propellant prices over the
    # campaign's frozen tables.
    #
    # ⚠️  Mirrored, not shared: a stage module is standalone by construction and
    # cannot import a helper.  `verify_docs.py` check 15 holds the three copies
    # to each other, so edit one and the docs harness names the other two.
    def _confirm_overwrite(paths, what):
        """True when it is safe to overwrite `paths`; ask the user if it is not.

        Refuses on EOF rather than hanging, because stdin here may be a
        scheduled task's dead handle -- the `set /p` trap in `run.bat`, which
        waits forever instead of failing.  `--yes` skips the question, which is
        what a scripted caller passes.
        """
        existing = [p for p in paths if os.path.exists(p)]
        if not existing or "--yes" in sys.argv:
            return True
        print("")
        print("  " + "=" * 71)
        print("  THIS RE-FETCHES LIVE DATA AND OVERWRITES WHAT IS ON DISK")
        print("  " + "=" * 71)
        print("  %s" % what)
        for p in existing[:8]:
            print("    %s" % p)
        if len(existing) > 8:
            print("    ... and %d more" % (len(existing) - 8))
        print("")
        print("  The values on disk are the only copy.  Any verify.py baseline")
        print("  or archived measurement taken against them stops reproducing,")
        print("  and that looks exactly like a code regression.")
        print("")
        try:
            return input("  Type 'yes' to overwrite: ").strip().lower() == "yes"
        except (EOFError, KeyboardInterrupt):
            print("")
            print("  No console to confirm on (stdin is not a terminal).")
            print("  Pass --yes if overwriting them is what you meant.")
            return False

    if not _confirm_overwrite(
            [os.path.join(CONFIG.output_dir, CONFIG.catalog_filename),
                    os.path.join(CONFIG.output_dir, CONFIG.rejected_filename)],
            "Stage 1 re-fetches the asteroid catalog from JPL and its supplements."):
        print("  Cancelled; nothing was fetched and nothing was written.")
        sys.exit(1)

    catalog = build_catalog(CONFIG)

    if not catalog.empty:

        # ── Column preview ─────────────────────────────────────────────────────────
        PREVIEW_COLS = [
            "designation", "name", "spectral_type", "comp_group",
            "diameter_km", "density_gcm3", "density_measured",
            "albedo", "semi_major_axis_au", "eccentricity", "inclination_deg",
            "comp_composition", "estimated_mass_kg",
        ]
        show = [c for c in PREVIEW_COLS if c in catalog.columns]

        print(f"\n{'='*65}")
        print(f"    CATALOG PREVIEW  -  first {CONFIG.preview_rows} entries")
        print(f"{'='*65}")
        print(catalog[show].head(CONFIG.preview_rows).to_string(index=False))

        # ── Spectral distribution ─────────────────────────────────────────────────
        print(f"\n{'='*65}")
        print("    SPECTRAL TYPE DISTRIBUTION")
        print(f"{'='*65}")
        if "spectral_type" in catalog.columns:
            dist = catalog["spectral_type"].value_counts()
            bar_scale = max(dist.values) / 40 if len(dist) else 1
            top_n = CONFIG.top_n_spectral_types
            for spec, n in dist.head(top_n).items():
                bar = "█" * max(1, int(n / bar_scale))
                print(f"  {str(spec):8s} {bar:<42s} {n:>6,}")
            if len(dist) > top_n:
                print(f"  ... and {len(dist)-top_n} more types")

        # ── Size histogram ────────────────────────────────────────────────────────
        print(f"\n{'='*65}")
        print("    SIZE DISTRIBUTION")
        print(f"{'='*65}")
        if "diameter_km" in catalog.columns:
            d = pd.to_numeric(catalog["diameter_km"], errors="coerce")
            bins   = [(0, 0.1), (0.1, 1), (1, 10), (10, 100), (100, 500), (500, 1e9)]
            labels = ["<0.1 km", "0.1-1 km", "1-10 km", "10-100 km", "100-500 km", ">500 km"]
            for (lo, hi), label in zip(bins, labels):
                n = int(((d >= lo) & (d < hi)).sum())
                bar = "█" * min(int(n / max(1, len(catalog)) * 50), 50)
                print(f"  {label:12s} {bar:<52s} {n:,}")

        # ── Orbital regions ───────────────────────────────────────────────────────
        print(f"\n{'='*65}")
        print("    ORBITAL REGION DISTRIBUTION")
        print(f"{'='*65}")
        if "semi_major_axis_au" in catalog.columns:
            a = pd.to_numeric(catalog["semi_major_axis_au"], errors="coerce")
            regions = [
                (0.0,  1.0,  "Near-Sun / Aten class"),
                (1.0,  1.7,  "NEA / Apollo / Amor"),
                (1.7,  2.5,  "Inner Main Belt"),
                (2.5,  3.3,  "Middle Main Belt"),
                (3.3,  4.0,  "Outer Main Belt"),
                (4.0,  5.4,  "Jupiter Trojans region"),
                (5.4, 30.1,  "Outer solar system"),
                (30.1, 1e9,  "Trans-Neptunian / KBO"),
            ]
            for lo, hi, name in regions:
                n = int(((a >= lo) & (a < hi)).sum())
                if n > 0:
                    print(f"  {name:30s} {n:>8,}  ({n/len(catalog)*100:4.1f}%)")

        # ── Composition group summary ─────────────────────────────────────────────
        print(f"\n{'='*65}")
        print("    COMPOSITION GROUP BREAKDOWN")
        print(f"{'='*65}")
        if "comp_group" in catalog.columns:
            grp = catalog["comp_group"].value_counts()
            for g, n in grp.items():
                print(f"  {str(g):20s} {n:>8,}  ({n/len(catalog)*100:4.1f}%)")

        # ── Data completeness report ──────────────────────────────────────────────
        print(f"\n{'='*65}")
        print("    DATA COMPLETENESS")
        print(f"{'='*65}")
        key_cols = [
            "designation", "name", "spectral_type", "diameter_km",
            "albedo", "density_gcm3", "density_measured",
            "semi_major_axis_au", "eccentricity", "inclination_deg",
            "comp_composition", "estimated_mass_kg",
        ]
        for col in key_cols:
            if col in catalog.columns:
                pct = catalog[col].notna().mean() * 100
                bar = "█" * int(pct / 2)
                print(f"  {col:30s} {bar:<50s} {pct:5.1f}%")
