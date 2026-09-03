# -*- coding: utf-8 -*-
"""A second opinion on `spectral_type`, and what it does to composition.

Every value in this pipeline flows from `comp_metal_fraction`,
`comp_carbon_fraction`, `comp_ice_fraction` and `comp_pgm_enrichment`, and all
four are looked up from `spectral_type` through `TAXONOMY_COMPOSITION`.  So the
reliability of `spectral_type` IS the reliability of the answer, and nothing in
the pipeline measures it.

This probe fetches an independent taxonomy (the SDSS-based classification of
Carvano et al. 2010, PDS3 archive EAR_A_I0035_5_SDSSTAX_V1_1, 63,468 numbered
asteroids from u'g'r'i'z' photometry) and asks two questions:

  1. how often do the two surveys agree, at the letter and at `comp_group`
  2. when they disagree, how far do the value-bearing fractions move

The column specs come from juliensimon/space-datasets' `update-sdss-taxonomy.py`,
which read them off the archive's own .lbl files.

Note pds4_tools does NOT read this archive: it is PDS3, that library is PDS4.
A fixed-width read needs no dependency at all.

This script READS ONLY.  It parses `TAXONOMY_COMPOSITION` out of
modules/catalog.py as text rather than importing it, because importing that
module fires its INSTALLATION block.  It writes nothing to `asteroid_pipeline/`.

Usage:
    py research/starred-repos/probe_taxonomy.py
    py research/starred-repos/probe_taxonomy.py --repo . --cache sdsstax_ast.tab
"""

import argparse
import ast
import os
import re

import numpy as np
import pandas as pd

SDSS_URL = ("https://sbnarchive.psi.edu/pds3/non_mission/"
            "EAR_A_I0035_5_SDSSTAX_V1_1/data/sdsstax_ast_table.tab")

# PDS3 fixed-width layout of sdsstax_ast_table.tab: (name, start, width).
AST_COLSPECS = [
    ("ast_number", 0, 6), ("ast_name", 7, 17), ("prov_desig", 24, 11),
    ("classification", 35, 4), ("score_best", 39, 2), ("n_class", 43, 1),
]


def load_taxonomy_table(repo):
    """Parse TAXONOMY_COMPOSITION out of modules/catalog.py without importing it."""
    src = open(os.path.join(repo, "modules", "catalog.py"), encoding="utf-8").read()
    m = re.search(r"^TAXONOMY_COMPOSITION: Dict\[str, dict\] = (\{.*?^\})\s*$",
                  src, re.S | re.M)
    if not m:
        raise SystemExit("could not locate TAXONOMY_COMPOSITION in modules/catalog.py")
    return ast.literal_eval(m.group(1))


def entry_for(tax, spectral_type):
    """Resolve a spectral type to its TAXONOMY_COMPOSITION entry, longest root first.

    Mirrors the fallback in `enrich_composition`: exact match, then a two-letter
    root, then a one-letter root, then Unknown.
    """
    if spectral_type is None:
        return None
    t = str(spectral_type).strip()
    if t in tax:
        return tax[t]
    for n in (2, 1):
        if len(t) >= n and t[:n] in tax:
            return tax[t[:n]]
    return tax.get("Unknown")


def load_sdss(cache):
    """Download (once) and parse the SDSS asteroid classification table."""
    if not os.path.exists(cache):
        import urllib.request
        print(f"  downloading {SDSS_URL}")
        urllib.request.urlretrieve(SDSS_URL, cache)
    df = pd.read_fwf(
        cache,
        colspecs=[(c[1], c[1] + c[2]) for c in AST_COLSPECS],
        names=[c[0] for c in AST_COLSPECS],
        dtype=str,
    )
    df["ast_number"] = pd.to_numeric(df["ast_number"], errors="coerce")
    df["score_best"] = pd.to_numeric(df["score_best"], errors="coerce")
    df["classification"] = df["classification"].astype(str).str.strip()
    keep = (df["classification"].str.len() > 0) & ~df["classification"].isin(["-", "nan"])
    return df[keep]


def report_provenance(cat):
    """How much of the catalog, and of the NEOs, has a taxonomy from a real source."""
    print("\nTAXONOMY PROVENANCE")
    print(f"  all bodies : {len(cat):,}")
    for k, v in cat["spectral_type_source"].value_counts(dropna=False).items():
        print(f"    {str(k):16s} {v:10,}  ({v / len(cat) * 100:5.2f}%)")
    neo = cat[cat["is_neo"].astype(str).str.lower().isin(["true", "1", "y", "yes"])]
    if len(neo):
        src = neo["spectral_type_source"].eq("source").sum()
        num = pd.to_numeric(neo["designation"].astype(str).str.strip(),
                            errors="coerce").notna().sum()
        print(f"  NEOs       : {len(neo):,}")
        print(f"    from a real source : {src:,}  ({src / len(neo) * 100:.2f}%)")
        print(f"    numbered (so SDSS could ever reach them) : "
              f"{num:,}  ({num / len(neo) * 100:.1f}%)")


def main():
    """Compare the two taxonomies and price the disagreement."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".", help="repo root")
    ap.add_argument("--cache", default="sdsstax_ast.tab", help="local copy of the PDS table")
    args = ap.parse_args()

    tax = load_taxonomy_table(args.repo)
    print(f"TAXONOMY_COMPOSITION: {len(tax)} spectral types, "
          f"{len({v['group'] for v in tax.values()})} groups")

    sdss = load_sdss(args.cache)
    print(f"SDSS classifications: {len(sdss):,}")

    cat = pd.read_csv(
        os.path.join(args.repo, "asteroid_pipeline", "asteroid_catalog.csv"),
        usecols=["designation", "is_neo", "spectral_type", "spectral_type_source",
                 "comp_group", "comp_metal_fraction", "comp_carbon_fraction",
                 "comp_ice_fraction"],
        low_memory=False,
    )
    report_provenance(cat)

    # Numbered bodies carry a bare integer designation in this catalog.
    cat = cat.assign(catnum=pd.to_numeric(
        cat["designation"].astype(str).str.strip(), errors="coerce"))
    j = cat.merge(sdss, left_on="catnum", right_on="ast_number")
    j = j[j["spectral_type"].notna()].copy()
    print(f"\nAGREEMENT  (bodies with both an SsODNet type and an SDSS class: {len(j):,})")

    j["sdss_group"] = [(entry_for(tax, c) or {}).get("group") for c in j["classification"]]
    same_letter = (j["spectral_type"].astype(str).str[0].str.upper()
                   == j["classification"].astype(str).str[0].str.upper())
    same_group = j["comp_group"].astype(str) == j["sdss_group"].astype(str)
    hi = j["score_best"] >= 60

    print(f"  first letter agrees : {same_letter.sum():,} / {len(j):,}"
          f"  ({same_letter.mean() * 100:.1f}%)")
    print(f"  comp_group  agrees  : {same_group.sum():,} / {len(j):,}"
          f"  ({same_group.mean() * 100:.1f}%)")
    print(f"  comp_group agrees, SDSS score >= 60 (n={hi.sum():,})"
          f"  : {same_group[hi].mean() * 100:.1f}%")

    print("\n  largest comp_group disagreements (SsODNet -> SDSS):")
    worst = (j[~same_group].groupby(["comp_group", "sdss_group"])
             .size().sort_values(ascending=False).head(10))
    for (a, b), n in worst.items():
        print(f"    {a:12s} -> {b:12s} {n:6,}")

    print("\nWHAT IT DOES TO THE VALUE-BEARING FRACTIONS")
    for label, field in [("metal", "metal_fraction"),
                         ("carbon", "carbon_fraction"),
                         ("ice", "ice_fraction")]:
        cur = pd.to_numeric(j["comp_" + field], errors="coerce").astype("float64")
        alt = pd.to_numeric(
            pd.Series([(entry_for(tax, c) or {}).get(field) for c in j["classification"]],
                      index=j.index),
            errors="coerce").astype("float64")
        d = (alt - cur).abs()
        moved = d > 1e-9
        print(f"  {label:6s} changes on {moved.sum():6,} bodies "
              f"({moved.mean() * 100:5.1f}%)   median |delta| {d[moved].median():.3f}"
              f"   max {d.max():.3f}")


if __name__ == "__main__":
    main()
