# -*- coding: utf-8 -*-
"""mineral_value, Module 2 of the Asteroid Profitability Pipeline.

STAGE 2 DOES NOT PRICE ANYTHING ANY MORE.  IT INSTALLS PUBLISHED PRICES.  The
pricing is `spacevalue`, an independent package split out of this module at
its data contract 1.16.0, with its history:

    https://github.com/loggger101/spacevalue

spacevalue publishes one frozen set of tables per `prices-YYYY-MM-DD` release:
every destination's mineral-value table, built from one recorded quote
snapshot, and a manifest of their sha256s.  This module pins ONE of those tags
(`price_release` below), downloads it, checks every byte against the manifest,
and installs the table for `delivery_destination` where Stage 4 has always
read it.

WHY.  A live price cannot be fetched twice.  While this stage fetched its own,
re-running it replaced the only copy of the prices every `.verify` baseline
and every archived cell was measured on, so the rule was "never re-run
Stage 2", and campaign/stage2/ filled up with hand-frozen copies.  A pinned
release is the same bytes on every host and every day: re-running Stage 2 is
safe, and switching destination needs no network once a release is cached.

MOVING TO NEWER PRICES IS A DELIBERATE, ONE-LINE REPIN of `price_release`, and
it moves every number downstream.  Record it in versions.md.  A change to the
pricing itself (a utility factor, a demand ceiling, a reference price) is a
spacevalue release, then a prices release, then a repin here.

WHAT THIS FILE STILL OWNS:

    MineralValueConfig  the pin, the data contract this pipeline expects, the
                        destination, and where the files land.  `ui_meta`
                        scrapes each field's comment block as dashboard help
    the re-exports      spacevalue's names that something here reads as
                        `master.<name>`: the destination list (the entry
                        points, the dashboard, verify_docs), the judgement
                        tables verify.py check 6 recomputes the installed
                        table through, and the delivery names the worked
                        calculation borrows
    the RUN & PREVIEW   the standalone-module behaviour every stage has

`pipeline_version` IS SPACEVALUE'S DATA CONTRACT, and this module checks it
rather than stamping it: the release's manifest must carry the same value, or
the download is refused before anything on disk is touched.

Release assets used here:
    manifest.json                        tag, contract, quotes, sha256s
    mineral_value_catalog.<dest>.csv     one per destination

Pipeline flow:
    Manifest  ->  check pin + contract  ->  Download  ->  Verify sha256  ->
    Cache  ->  Install the destination's table  ->  Verify sha256
"""

# ─────────────────────────────────────────────────────────────────────────────
# INSTALLATION
# ─────────────────────────────────────────────────────────────────────────────
try:
    from . import _release, _runtime
except ImportError:                 # run as a script: modules/ is on sys.path
    import _release
    import _runtime

# spacevalue for the names this module re-exports; the prices themselves come
# from the release.  spacecost arrives with it and is pinned separately.
_REQUIRED_PKGS = ["requests", "pandas", "tqdm", "spacevalue"]
_runtime.install(_REQUIRED_PKGS)


# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from typing import Optional

import pandas as pd

import spacevalue
from spacevalue import catalog as _sv


# ═════════════════════════════════════════════════════════════════════════════
# ║                                                                           ║
# ║   ★  USER SETTINGS, EDIT THESE TO TUNE THE PIPELINE  ★                  ║
# ║                                                                           ║
# ═════════════════════════════════════════════════════════════════════════════
@dataclass
class MineralValueConfig:
    """Stage 2's settings: which published prices, and for which destination."""

    # ─── THE PINNED PRICES ───────────────────────────────────────────────────
    # Which published price release this pipeline runs on: a
    # `prices-YYYY-MM-DD` tag of the spacevalue repository, built from the
    # quotes recorded that day.  Every host that runs Stage 2 at this pin gets
    # the same bytes, checked against the release's sha256s.  Changing it
    # moves every price, and so every number downstream: record a repin in
    # versions.md.  The published tags are listed at
    # https://github.com/loggger101/spacevalue/releases
    price_release: str = "prices-2026-10-07"

    # Where release assets are downloaded from; the tag and the asset name are
    # appended.  Plumbing: change it only to point at a mirror.
    release_base_url: str = ("https://github.com/loggger101/spacevalue"
                             "/releases/download")

    # Seconds to wait on any one HTTP request before giving up.
    request_timeout: int = 60

    # ─── DELIVERY DESTINATION  (drives EVERY price; read this) ──────────────
    # Where the mined material is SOLD, and so which of the release's tables
    # is installed.  It selects the market, and the market decides both what a
    # kilogram is worth and which asteroids win: at earth_surface a commodity
    # is worth its terrestrial price, and anywhere in space the better of the
    # launch cost it saves there and its Earth price less the trip home.  The
    # destinations, their derived prices and the judgement behind them are
    # spacevalue's README and MODEL.md's destination table.
    #
    # ⚠️  Module 4's CALC_CONFIG carries a delivery_destination of its own,
    # and it must MATCH this one; it selects the mission architecture that
    # delivers the cargo here.  In master.py set
    # MASTER_CONFIG.delivery_destination, which sets both.
    delivery_destination: str = "earth_surface"

    # ─── OUTPUT ──────────────────────────────────────────────────────────────
    # The installed table is `<output_dir>/<catalog_filename>`, where Stage 4
    # reads it.  Every table of the pinned release is cached in
    # `<output_dir>/<subdir>/<price_release>/`, so a destination change
    # installs from there without the network.
    output_dir:        str = _runtime.DEFAULT_OUTPUT_DIR
    catalog_filename:  str = "mineral_value_catalog.csv"
    manifest_filename: str = "mineral_value_manifest.json"
    subdir:            str = "mineral_value"

    # ─── DATA CONTRACT ───────────────────────────────────────────────────────
    # The table schema and pricing this pipeline is written against: the
    # `pipeline_version` spacevalue stamps into every row.  Stage 2 refuses a
    # release whose manifest says otherwise, before anything on disk is
    # touched, and Stage 4's stamp check compares the installed table with
    # it.  The record of what each contract changed is spacevalue's
    # CHANGELOG.md; this pipeline's is versions.md > Stage 2 changelog.
    pipeline_version: str = "1.17.0"

    # ─── DISPLAY ─────────────────────────────────────────────────────────────
    preview_rows:      int = 20   # rows per table in the end-of-run preview


CONFIG = MineralValueConfig()
os.makedirs(CONFIG.output_dir, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# SPACEVALUE'S NAMES THAT THIS PIPELINE READS
# ─────────────────────────────────────────────────────────────────────────────
# The same objects, not copies, and only what something here reads, each by
# `master.<name>`:
#
#   DELIVERY_DESTINATIONS    the destination list: run_pipeline.py's
#                            --destination choices, the dashboard's selector,
#                            verify_docs check 17
#   the judgement tables     verify.py check 6 recomputes every row of the
#                            installed table through them, which is what says
#                            the release on disk is what the pinned package
#                            computes
#   the delivery names       campaign/worked_calculation.py re-derives a
#                            delivered price from them (its BORROWED register)
#
# spacevalue's tests/test_consumer_contract.py names every one, so dropping
# one there is a breaking change it has to declare.
DELIVERY_DESTINATIONS      = spacevalue.DELIVERY_DESTINATIONS
MINERAL_REFERENCE          = spacevalue.MINERAL_REFERENCE
ANNUAL_WORLD_PRODUCTION_KG = spacevalue.ANNUAL_WORLD_PRODUCTION_KG
annual_market_kg           = spacevalue.annual_market_kg
in_space_utility           = spacevalue.in_space_utility
_COMMODITY_CLASS           = _sv._COMMODITY_CLASS
_UNLIMITED_MARKET_KG       = _sv._UNLIMITED_MARKET_KG
_DELIVERY_LEGS             = _sv._DELIVERY_LEGS
_LEO_USD_PER_KG            = _sv._LEO_USD_PER_KG
delivered_cost_usd_per_kg  = _sv.delivered_cost_usd_per_kg

# Sanity checks over a table; prints and never drops a row.  Module 3 defines
# a `validate` too, so master.py binds this one as `validate_minerals`.
validate = spacevalue.validate


# ─────────────────────────────────────────────────────────────────────────────
# THE RELEASE
# ─────────────────────────────────────────────────────────────────────────────
_ASSET_MANIFEST = spacevalue.ASSET_MANIFEST


def _cache_dir(config: "MineralValueConfig") -> str:
    """Where every table of the pinned release is kept once checked."""
    return os.path.join(config.output_dir, config.subdir, config.price_release)


def _asset_url(config: "MineralValueConfig", asset: str) -> str:
    """Where one asset of the pinned release is served."""
    return _release.asset_url(config.release_base_url, config.price_release,
                              asset)


def _not_found(what: str) -> str:
    """The refusal for a release or asset that is not there, naming the pin."""
    return ("FAIL  %s.\n"
            "      Check `price_release` against the published tags at\n"
            "      https://github.com/loggger101/spacevalue/releases" % what)


def _read_manifest(path: str) -> Optional[dict]:
    """A manifest on disk, or None when it is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) else None


def _check_contract(config: "MineralValueConfig", manifest: dict) -> None:
    """Refuse a manifest that is not the pin, or not this pipeline's contract."""
    if manifest.get("release_tag") != config.price_release:
        raise SystemExit("FAIL  the manifest served for %r names itself %r."
                         % (config.price_release, manifest.get("release_tag")))
    if manifest.get("pipeline_version") != config.pipeline_version:
        raise SystemExit(
            "FAIL  STAGE 2 CONTRACT MISMATCH: release %s is data contract %s,\n"
            "      and this pipeline is written against %s.  Nothing was\n"
            "      downloaded.  Pin a release at %s, or move\n"
            "      MineralValueConfig.pipeline_version once Stage 4 has been\n"
            "      checked against the new contract."
            % (config.price_release, manifest.get("pipeline_version"),
               config.pipeline_version, config.pipeline_version))


def cached_release(config: "MineralValueConfig" = CONFIG) -> Optional[dict]:
    """The pinned release's manifest when every table of it is cached intact.

    Reads and hashes every cached table (they are small), because a manifest
    beside a table that has since been edited would vouch for bytes it never
    saw.  None means Stage 2 has to download.
    """
    cache = _cache_dir(config)
    manifest = _read_manifest(os.path.join(cache, _ASSET_MANIFEST))
    if manifest is None or manifest.get("release_tag") != config.price_release:
        return None
    for fname, entry in manifest.get("files", {}).items():
        path = os.path.join(cache, fname)
        if (not os.path.isfile(path) or os.path.getsize(path) != entry["bytes"]
                or _release.sha256(path) != entry["sha256"]):
            return None
    return manifest


def _download_release(config: "MineralValueConfig") -> dict:
    """Fetch and check every table of the pinned release into the cache.

    Into a fresh staging directory first, and moved into place only when every
    byte has matched, the manifest last, so an interrupted download never
    leaves a manifest vouching for tables that are not there.
    """
    manifest = _release.fetch_json(
        _asset_url(config, _ASSET_MANIFEST), config.request_timeout,
        _not_found("no price release %r" % config.price_release))
    _check_contract(config, manifest)
    print("  Release   : %s, quotes %s recorded %s, data contract %s"
          % (manifest["release_tag"], manifest.get("quote_snapshot"),
             manifest.get("catalog_date"), manifest["pipeline_version"]))

    cache = _cache_dir(config)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    stage = tempfile.mkdtemp(prefix=".prices_download-",
                             dir=os.path.dirname(cache))
    try:
        for fname, entry in sorted(manifest["files"].items()):
            url = _asset_url(config, fname)
            _release.download(
                url, os.path.join(stage, fname), config.request_timeout,
                _not_found("%s has no asset %s\n      %s"
                           % (config.price_release, fname, url)), fname)
            _release.check(os.path.join(stage, fname), entry, fname)
        with open(os.path.join(stage, _ASSET_MANIFEST), "w", encoding="utf-8",
                  newline="\n") as fh:
            json.dump(manifest, fh, indent=2)
            fh.write("\n")
        # FILES ARE REPLACED, NOT THE DIRECTORY.  Removing the cache directory
        # to swap a fresh one in fails on the synced folder (WinError 5, the
        # trap Stage 1's staging comment records), and it did, on a planted
        # one-byte edit.  The manifest goes first and comes back last, so the
        # cache never holds a manifest vouching for tables it does not have.
        os.makedirs(cache, exist_ok=True)
        manifest_path = os.path.join(cache, _ASSET_MANIFEST)
        if os.path.exists(manifest_path):
            os.remove(manifest_path)
        for fname in manifest["files"]:
            os.replace(os.path.join(stage, fname), os.path.join(cache, fname))
        os.replace(os.path.join(stage, _ASSET_MANIFEST), manifest_path)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return manifest


def install_destination(destination: str, target: str,
                        config: "MineralValueConfig" = CONFIG) -> dict:
    """Copy one destination's cached table to `target`, checked, and say what.

    Returns the release's manifest entry for the table.  Written beside the
    target and moved over it only once its sha256 is the manifest's, so a
    failed copy never leaves half a table where Stage 4 reads.
    """
    manifest = cached_release(config) or _download_release(config)
    fname = spacevalue.table_filename(destination)
    entry = manifest["files"].get(fname)
    if entry is None:
        raise SystemExit(
            "FAIL  release %s has no table for destination %r; it carries %s."
            % (config.price_release, destination,
               ", ".join(sorted(manifest.get("destinations", [])))))
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    tmp = target + ".installing"
    shutil.copyfile(os.path.join(_cache_dir(config), fname), tmp)
    _release.check(tmp, entry, fname)
    os.replace(tmp, target)
    return dict(entry, release_tag=manifest["release_tag"],
                quote_snapshot=manifest.get("quote_snapshot"),
                catalog_date=manifest.get("catalog_date"),
                pipeline_version=manifest["pipeline_version"])


def installed_table(config: "MineralValueConfig" = CONFIG) -> Optional[dict]:
    """What is installed at `catalog_filename`, per the record Stage 2 wrote."""
    return _read_manifest(os.path.join(config.output_dir,
                                       config.manifest_filename))


def build_mineral_value_catalog(
    config: MineralValueConfig = CONFIG,
) -> pd.DataFrame:
    """Install the pinned release's table for the destination, and return it.

    Nothing is priced here.  When the release is already cached and intact,
    nothing is downloaded either.
    """
    print("=" * 65)
    print("    STAGE 2 - MINERAL VALUE  (release %s)" % config.price_release)
    print("=" * 65)
    if config.delivery_destination not in DELIVERY_DESTINATIONS:
        raise SystemExit(
            "FAIL  unknown delivery_destination %r; spacevalue %s prices %s."
            % (config.delivery_destination, spacevalue.__version__,
               ", ".join(DELIVERY_DESTINATIONS)))

    if cached_release(config) is not None:
        print("  OK  %s is cached, and every table's sha256 matches."
              % config.price_release)
    target = os.path.join(config.output_dir, config.catalog_filename)
    record = install_destination(config.delivery_destination, target, config)
    record["destination"] = config.delivery_destination
    record_path = os.path.join(config.output_dir, config.manifest_filename)
    with open(record_path + ".tmp", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")
    os.replace(record_path + ".tmp", record_path)

    catalog = pd.read_csv(target)
    print("  OK  installed %s for %s -> %s"
          % (config.price_release, config.delivery_destination, target))
    print("  OK  %d rows, data contract %s, quotes %s recorded %s"
          % (len(catalog), record["pipeline_version"],
             record["quote_snapshot"], record["catalog_date"]))
    return catalog


print(f"OK  Stage 2 ready - spacevalue {spacevalue.__version__}, "
      f"data contract {spacevalue.DATA_VERSION}, release {CONFIG.price_release}")
print(f"    Delivery dest  : {CONFIG.delivery_destination}  "
      f"(sets EVERY price; one of {len(DELIVERY_DESTINATIONS)} destinations)")


# ─────────────────────────────────────────────────────────────────────────────
# RUN & PREVIEW
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # Re-running is safe now: the release is the same bytes every time.  What
    # is at risk is a table for ANOTHER destination, or another release, that
    # a baseline or a cell was measured against.
    _target = os.path.join(CONFIG.output_dir, CONFIG.catalog_filename)
    _on_disk = installed_table(CONFIG) or {}
    _at_risk = ([] if (_on_disk.get("release_tag") == CONFIG.price_release
                       and _on_disk.get("destination") == CONFIG.delivery_destination)
                else [_target])
    if not _runtime.confirm_overwrite(
            _at_risk,
            "Stage 2 installs price release %s (%s) over the table on disk."
            % (CONFIG.price_release, CONFIG.delivery_destination)):
        print("  Cancelled; nothing was fetched and nothing was written.")
        sys.exit(1)

    catalog = build_mineral_value_catalog(CONFIG)

    cols = [c for c in ("name", "kind", "price_usd_per_kg", "price_basis",
                        "value_route", "live_price_source") if c in catalog.columns]
    print(f"\n{'='*75}")
    print(f"    MINERAL VALUE CATALOG - first {CONFIG.preview_rows} entries")
    print(f"{'='*75}")
    print(catalog[cols].head(CONFIG.preview_rows).to_string(index=False))
