# -*- coding: utf-8 -*-
"""Installing a published release: download, check every byte, then install.

Two stages here install someone else's published output rather than building
their own.  Stage 1 installs an AsteroidCatalog `data-*` release, Stage 2 a
spacevalue `prices-*` release, and both follow one rule: nothing on disk
changes until every downloaded byte has matched the release's manifest.  The
pieces of that rule both of them use live here, once.

What each stage keeps for itself is what differs: which assets it needs, the
contract it checks the manifest against, and the words it fails with, which
name its own config field and its own releases page.
"""

import hashlib
import os

import requests


def sha256(path: str) -> str:
    """sha256 of a file, read in 1 MB chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def asset_url(base_url: str, tag: str, asset: str) -> str:
    """Where one asset of a release is served."""
    return "%s/%s/%s" % (base_url.rstrip("/"), tag, asset)


def download(url: str, dest: str, timeout: int, not_found: str,
             label: str) -> None:
    """Stream `url` to `dest`, with a byte progress bar labelled `label`.

    A 404 exits with `not_found`, which names the pin to check: a release that
    lacks an asset is the caller's pin being wrong far more often than the
    release being broken.
    """
    from tqdm.auto import tqdm

    with requests.get(url, stream=True, timeout=timeout) as resp:
        if resp.status_code == 404:
            raise SystemExit(not_found)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length") or 0) or None
        with open(dest, "wb") as fh, tqdm(
                total=total, desc="     %s" % label, unit="B",
                unit_scale=True, unit_divisor=1024, mininterval=0.3) as bar:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)
                    bar.update(len(chunk))


def check(path: str, entry: dict, what: str) -> None:
    """Refuse a file whose size or sha256 is not the manifest's."""
    size = os.path.getsize(path)
    if size != entry["bytes"]:
        raise SystemExit("FAIL  %s is %d bytes; the manifest says %d.  "
                         "Nothing was installed." % (what, size, entry["bytes"]))
    digest = sha256(path)
    if digest != entry["sha256"]:
        raise SystemExit("FAIL  %s has sha256 %s; the manifest says %s.  "
                         "Nothing was installed." % (what, digest, entry["sha256"]))


def fetch_json(url: str, timeout: int, not_found: str) -> dict:
    """A release's manifest, or exit with `not_found` when there is none."""
    resp = requests.get(url, timeout=timeout)
    if resp.status_code == 404:
        raise SystemExit(not_found)
    resp.raise_for_status()
    return resp.json()
