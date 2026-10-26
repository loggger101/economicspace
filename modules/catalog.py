# -*- coding: utf-8 -*-
"""catalog, Module 1 of the Asteroid Profitability Pipeline.

STAGE 1 DOES NOT BUILD THE CATALOG ANY MORE.  IT DOWNLOADS ONE.  The catalog
is built by `asteroid_catalog`, an independent repository, and published there
as a GitHub Release -- one frozen build per `data-YYYY-MM-DD` tag:

    https://github.com/loggger101/AsteroidCatalog/releases

This module pins ONE of those tags (`catalog_release` below), downloads it,
checks every byte against the release's manifest, and writes it where Stage 2
and Stage 4 have always looked for it.

WHY.  A build cannot be repeated: JPL adds bodies daily, so the catalog a
build returns today is a different length from last week's, and comparable
with nothing already measured.  While this stage built its own, re-running it
was the most destructive thing a user could do here -- it replaced the 862 MB
input every committed number was measured on, with no way back.  A pinned
release is the same bytes every time, on every host: re-running Stage 1 is now
a no-op when the pin has not moved, and a fresh clone gets the catalog the
committed numbers were measured on instead of today's.

MOVING TO A NEWER CATALOG IS A DELIBERATE, ONE-LINE REPIN of
`catalog_release`, and it moves every number downstream exactly as a rebuild
did.  Record it in versions.md like any other input change.

WHAT THIS FILE STILL OWNS:

    CatalogConfig       the pin, the data contract this pipeline expects, and
                        where the files land.  `ui_meta` scrapes each field's
                        comment block as the dashboard's help text, so the
                        comments here are UI copy and not just commentary
    TAXONOMY_COMPOSITION / PGM_ENRICHMENT_BY_TYPE / PHASE_GROUP
                        read from the release's `taxonomy.json`: the tables
                        the catalog was BUILT with, not whatever a locally
                        installed package happens to hold.  PHASE_GROUP
                        (data contract 1.7.0) names every mineral phase the
                        `comp_phases` column may carry, and from 1.8.0 the
                        `comp_phases_detailed` one
    the RUN & PREVIEW   the standalone-module behaviour every stage here has,
                        including the overwrite guard

`pipeline_version` IS THE CATALOG'S DATA CONTRACT, and this module checks it
rather than stamping it: the release's manifest must carry the same value, or
the download is refused before anything on disk is touched.

    to check the catalog on disk:   py verify_stage1.py

Release assets used here:
    manifest.json               tag, build date, data contract, sha256s
    asteroid_catalog.csv.gz     the catalog, decompressed to catalog_filename
    rejected_entries.csv        validation rejects
    taxonomy.json               the composition tables the build used

Pipeline flow:
    Manifest  ->  check pin + contract  ->  Download  ->  Verify sha256  ->
    Decompress  ->  Verify sha256  ->  Install
"""

# ──────────────────────────────────────────────────────────────────────────────
# INSTALLATION
# ──────────────────────────────────────────────────────────────────────────────
try:
    from . import _release, _runtime
except ImportError:                 # run as a script: modules/ is on sys.path
    import _release
    import _runtime

# No `asteroid_catalog` here: this stage downloads the package's published
# output and never imports the package itself.
_REQUIRED_PKGS = ["requests", "pandas", "numpy", "tqdm"]
_runtime.install(_REQUIRED_PKGS)


# ──────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────────
import gzip
import json
import os
import shutil
import sys
import tempfile
import warnings
from dataclasses import dataclass
from typing import Optional

import pandas as pd

# Silence the chronic noise the data libraries emit during a typical run, but
# DON'T globally suppress everything, real RuntimeWarnings (e.g. divide-by-zero
# in our mass calculation) should still surface so we can spot bugs.
for _cat in (DeprecationWarning, FutureWarning, UserWarning):
    warnings.filterwarnings("ignore", category=_cat)

pd.set_option("display.max_columns", None)

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

    # ─── THE PINNED CATALOG ──────────────────────────────────────────────────
    # Which published build of the asteroid catalog this pipeline runs on: a
    # `data-YYYY-MM-DD` release tag of the AsteroidCatalog repository.  Every
    # host that runs Stage 1 at this pin gets the same bytes, checked against
    # the release's sha256s.  Changing it replaces the catalog every stage
    # reads, and moves every number downstream: record a repin in versions.md.
    # The published tags are listed at
    # https://github.com/loggger101/AsteroidCatalog/releases
    catalog_release: str = "data-2026-10-21b"

    # Where release assets are downloaded from; the tag and the asset name are
    # appended.  Plumbing: change it only to point at a mirror.
    release_base_url: str = ("https://github.com/loggger101/AsteroidCatalog"
                             "/releases/download")

    # Seconds to wait on any one HTTP request before giving up.  The catalog
    # asset is a few hundred MB, but this bounds a stall, not the transfer.
    request_timeout: int = 300

    # ─── OUTPUT  (where the CSVs land) ───────────────────────────────────────
    # `output_dir` is created at startup if it doesn't exist.  It defaults to
    # ./asteroid_pipeline under the working directory, or to
    # ASTEROID_PIPELINE_OUTPUT_DIR when that is set.
    output_dir:       str = _runtime.DEFAULT_OUTPUT_DIR
    catalog_filename:  str = "asteroid_catalog.csv"
    rejected_filename: str = "rejected_entries.csv"
    manifest_filename: str = "catalog_manifest.json"
    taxonomy_filename: str = "catalog_taxonomy.json"

    # ─── PREVIEW & SUMMARY DISPLAY  (cosmetic, affects stdout only) ──────────
    preview_rows:           int = 10   # rows shown in CATALOG PREVIEW table
    top_n_spectral_types:   int = 20   # types listed in spectral-distribution bars

    # ─── DATA CONTRACT ───────────────────────────────────────────────────────
    # The catalog schema this pipeline is written against: the
    # `pipeline_version` asteroid_catalog stamps into every row.  Stage 1
    # refuses a release whose manifest says otherwise, before anything on disk
    # is touched, and Stage 4's stamp check compares the catalog on disk with
    # it.  It moves only when a repin crosses a data-contract change, and then
    # only after the stages that read the catalog have been checked against the
    # new schema.  The record of what each contract changed is AsteroidCatalog's
    # CHANGELOG.md; this pipeline's is versions.md > Stage 1 changelog.
    pipeline_version: str = "1.10.0"


# Instantiate and create the output dir.  Edit CONFIG values above this line
# (inside the dataclass); DO NOT mutate CONFIG fields here, that defeats the
# purpose of having a single editable source of truth.
CONFIG = CatalogConfig()
os.makedirs(CONFIG.output_dir, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# THE RELEASE
# ──────────────────────────────────────────────────────────────────────────────
# The asset names are the release's, fixed by asteroid_catalog's `release.py`.
_ASSET_MANIFEST = "manifest.json"
_ASSET_CATALOG = "asteroid_catalog.csv.gz"
_ASSET_REJECTED = "rejected_entries.csv"
_ASSET_TAXONOMY = "taxonomy.json"


# The download, the hash and the size check are modules/_release.py's, shared
# with Stage 2.  What stays here is what is Stage 1's own: the assets, the
# contract and the words, which name this stage's pin and releases page.
_catalog_sha256 = _release.sha256
_check_asset = _release.check


def _asset_url(config: "CatalogConfig", asset: str) -> str:
    """Where one asset of the pinned release is served."""
    return _release.asset_url(config.release_base_url, config.catalog_release,
                              asset)


def _download_asset(config: "CatalogConfig", asset: str, dest: str) -> None:
    """Stream one release asset to `dest`, with a byte progress bar."""
    url = _asset_url(config, asset)
    _release.download(
        url, dest, config.request_timeout,
        "FAIL  %s has no asset %s.\n"
        "      %s\n"
        "      Check `catalog_release` against the published tags at\n"
        "      https://github.com/loggger101/AsteroidCatalog/releases"
        % (config.catalog_release, asset, url), asset)


def _fetch_manifest(config: "CatalogConfig") -> dict:
    """The pinned release's manifest, checked against the pin and the contract."""
    manifest = _release.fetch_json(
        _asset_url(config, _ASSET_MANIFEST), config.request_timeout,
        "FAIL  no catalog release %r.\n"
        "      Check `catalog_release` against the published tags at\n"
        "      https://github.com/loggger101/AsteroidCatalog/releases"
        % config.catalog_release)
    if manifest.get("release_tag") != config.catalog_release:
        raise SystemExit("FAIL  the manifest served for %r names itself %r."
                         % (config.catalog_release, manifest.get("release_tag")))
    if manifest.get("pipeline_version") != config.pipeline_version:
        raise SystemExit(
            "FAIL  STAGE 1 CONTRACT MISMATCH: release %s is data contract %s,\n"
            "      and this pipeline is written against %s.  Nothing was\n"
            "      downloaded.  Pin a release at %s, or move\n"
            "      CatalogConfig.pipeline_version once Stages 2-4 have been\n"
            "      checked against the new schema."
            % (config.catalog_release, manifest.get("pipeline_version"),
               config.pipeline_version, config.pipeline_version))
    return manifest


def installed_manifest(config: "CatalogConfig" = CONFIG) -> Optional[dict]:
    """The manifest of the release on disk, or None when there is none.

    An UNREADABLE manifest is None too: it vouches for nothing, so Stage 1
    reinstalls, which is safe because a pinned release is the same bytes on
    every host.  It used to raise, and this runs at import, so one truncated
    manifest made `import master` fail -- including the run that would have
    repaired it.
    """
    path = os.path.join(config.output_dir, config.manifest_filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def release_on_disk(config: "CatalogConfig" = CONFIG) -> bool:
    """Is the pinned release what is installed, byte for byte?

    Reads the whole catalog to hash it (a few seconds), because a manifest
    beside a CSV that has since been edited or half-copied would otherwise
    vouch for bytes it never saw.
    """
    manifest = installed_manifest(config)
    catalog_path = os.path.join(config.output_dir, config.catalog_filename)
    if (manifest is None or manifest.get("release_tag") != config.catalog_release
            or not os.path.isfile(catalog_path)):
        return False
    entry = manifest["catalog_csv"]
    return (os.path.getsize(catalog_path) == entry["bytes"]
            and _catalog_sha256(catalog_path) == entry["sha256"])


def _load_taxonomy(config: "CatalogConfig"):
    """The composition tables the installed catalog was built with.

    Empty when no release is installed yet.  Nothing in Stages 2-4 reads these
    tables -- they read the `comp_*` columns the build already wrote -- so an
    empty table is only visible to the tools that inspect it.
    """
    path = os.path.join(config.output_dir, config.taxonomy_filename)
    if not os.path.isfile(path):
        return {}, {}, {}
    with open(path, encoding="utf-8") as fh:
        tables = json.load(fh)
    # PHASE_GROUP is absent before data contract 1.7.0: an empty vocabulary,
    # which is what a catalog with no `comp_phases` column has.
    return (tables["TAXONOMY_COMPOSITION"], tables["PGM_ENRICHMENT_BY_TYPE"],
            tables.get("PHASE_GROUP", {}))


# Updated IN PLACE after a download, so a caller holding a reference to any of
# the three dicts sees the tables of the release that was just installed.
TAXONOMY_COMPOSITION, PGM_ENRICHMENT_BY_TYPE, PHASE_GROUP = _load_taxonomy(CONFIG)


def read_catalog(config: "CatalogConfig" = CONFIG) -> pd.DataFrame:
    """The installed catalog, read the way every reader must.

    `designation` MUST be read as a string: a numbered asteroid's designation
    looks like an integer, so a slice in which every row happens to be numbered
    infers int64 and every string comparison against it matches nothing.
    """
    return pd.read_csv(os.path.join(config.output_dir, config.catalog_filename),
                       low_memory=False, dtype={"designation": str})


def build_catalog(config: CatalogConfig = CONFIG) -> pd.DataFrame:
    """Install the pinned catalog release, verified, and return it.

    Nothing on disk changes until every downloaded byte has matched the
    manifest: files are fetched into a staging directory, checked, and only
    then moved over the installed copies.  When the pinned release is already
    installed, nothing is downloaded at all.
    """
    os.makedirs(config.output_dir, exist_ok=True)
    catalog_path = os.path.join(config.output_dir, config.catalog_filename)

    print("=" * 65)
    print("    STAGE 1 - ASTEROID CATALOG  (release %s)" % config.catalog_release)
    print("=" * 65)

    if release_on_disk(config):
        print("  OK  %s is already installed, and its sha256 matches."
              % config.catalog_release)
    else:
        manifest = _fetch_manifest(config)
        print("  Release   : %s, built %s, data contract %s"
              % (manifest["release_tag"], manifest["catalog_date"],
                 manifest["pipeline_version"]))
        print("  Bodies    : {:,}".format(manifest["rows"]))

        # A FRESH staging directory per install, never a fixed name.  A fixed
        # `.catalog_download` was cleared with rmtree(ignore_errors=True) and
        # then created, and on the Drive mount an EMPTY leftover can refuse
        # deletion (WinError 5): the error was swallowed and `makedirs` died,
        # so one interrupted install blocked every later one.  A unique name
        # cannot collide, and the `finally` below still removes it.
        stage = tempfile.mkdtemp(prefix=".catalog_download-", dir=config.output_dir)
        try:
            files = manifest["files"]
            for asset in (_ASSET_CATALOG, _ASSET_TAXONOMY, _ASSET_REJECTED):
                if asset not in files:
                    if asset == _ASSET_REJECTED:
                        continue          # a build with no rejects ships none
                    raise SystemExit("FAIL  the manifest lists no %s." % asset)
                _download_asset(config, asset, os.path.join(stage, asset))
                _check_asset(os.path.join(stage, asset), files[asset], asset)

            print("  Decompressing ...")
            csv_stage = os.path.join(stage, config.catalog_filename)
            with gzip.open(os.path.join(stage, _ASSET_CATALOG), "rb") as fin, \
                    open(csv_stage, "wb") as fout:
                shutil.copyfileobj(fin, fout, 1 << 20)
            _check_asset(csv_stage, manifest["catalog_csv"], config.catalog_filename)

            # Every byte checked.  Install: the catalog last but one, and the
            # manifest LAST, so an interrupted install never leaves a manifest
            # vouching for files that are not there.
            moves = [(os.path.join(stage, _ASSET_TAXONOMY),
                      os.path.join(config.output_dir, config.taxonomy_filename))]
            if _ASSET_REJECTED in files:
                moves.append((os.path.join(stage, _ASSET_REJECTED),
                              os.path.join(config.output_dir,
                                           config.rejected_filename)))
            moves.append((csv_stage, catalog_path))
            manifest_path = os.path.join(config.output_dir,
                                         config.manifest_filename)
            if os.path.exists(manifest_path):
                os.remove(manifest_path)
            # A release that ships no rejects file must not leave the previous
            # release's beside it, looking like this one's.
            rejected_path = os.path.join(config.output_dir,
                                         config.rejected_filename)
            if _ASSET_REJECTED not in files and os.path.exists(rejected_path):
                os.remove(rejected_path)
            for src, dst in moves:
                os.replace(src, dst)
            # Written in the staging directory and MOVED into place, so an
            # interrupted write can never leave a half-written manifest.
            manifest_stage = os.path.join(stage, config.manifest_filename)
            with open(manifest_stage, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(manifest, fh, indent=2)
                fh.write("\n")
            os.replace(manifest_stage, manifest_path)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        print("  OK  installed %s -> %s" % (config.catalog_release, catalog_path))

    taxonomy, pgm, phases = _load_taxonomy(config)
    TAXONOMY_COMPOSITION.clear()
    TAXONOMY_COMPOSITION.update(taxonomy)
    PGM_ENRICHMENT_BY_TYPE.clear()
    PGM_ENRICHMENT_BY_TYPE.update(pgm)
    PHASE_GROUP.clear()
    PHASE_GROUP.update(phases)

    catalog = read_catalog(config)
    print("  OK  %s rows x %d columns" % ("{:,}".format(len(catalog)),
                                         len(catalog.columns)))
    return catalog


_catalog_on_disk = installed_manifest(CONFIG)
print(f"OK  Configuration loaded - output dir: {CONFIG.output_dir}")
print(f"    Catalog release : {CONFIG.catalog_release} "
      f"(data contract {CONFIG.pipeline_version})")
print("    On disk         : "
      + ("nothing installed yet" if _catalog_on_disk is None else
         "%s, built %s" % (_catalog_on_disk.get("release_tag"),
                           _catalog_on_disk.get("catalog_date"))))
if _catalog_on_disk is not None and _catalog_on_disk.get("release_tag") != CONFIG.catalog_release:
    print("    WARN  the catalog on disk is not the pinned release; "
          "run Stage 1 to install it.")


# ─────────────────────────────────────────────────────────────────────────────
# RUN & PREVIEW
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # All tunable values live in the USER SETTINGS block at the top of this file; 
    # edit CONFIG fields there, then re-run.


    # Nothing is at risk when the pinned release is already installed: Stage 1
    # then downloads nothing, so the guard is handed no paths and passes.
    _at_risk = ([] if release_on_disk(CONFIG) else
                [os.path.join(CONFIG.output_dir, CONFIG.catalog_filename),
                 os.path.join(CONFIG.output_dir, CONFIG.rejected_filename)])
    if not _runtime.confirm_overwrite(
            _at_risk,
            "Stage 1 installs catalog release %s over the catalog on disk."
            % CONFIG.catalog_release):
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
