# Notes for working in this repo

Context for anyone (human or agent) editing this pipeline. The README covers
what it does and how to run it; this file covers what will bite you.

## master.py is generated — never edit it

`master.py` is 6,300 lines assembled from `modules/*.py` by `build_master.py`.
Edit the module, run `python build_master.py`, commit both. A change made
directly in `master.py` is destroyed by the next build.

`git status` immediately after a build is the sync check: clean means
`master.py` matches the modules.

## The build makes surgical assumptions about module structure

`build_master.py` locates things by pattern, not by parsing. Every module must
keep:

- a leading `# -*- coding: utf-8 -*-` line followed immediately by the module
  docstring (the docstring strip anchors on it),
- an `# INSTALLATION` block ending with the literal `print("✅  All packages present")`,
- a `# RUN & PREVIEW` block at the bottom, wrapped in `if __name__ == "__main__":`,
- its config global named exactly `CONFIG`.

The build asserts all four before and after stripping and exits with
`BUILD FAILED: …` rather than emitting a wrong `master.py`. If you restructure
a module header, expect to update `build_master.py` in the same commit.

## Name collisions are handled by hand

Concatenating four standalone modules means duplicate top-level names, and
Python just lets the last definition win. `build_master.py` renames the known
ones via `word_replace()`:

| Module | Renames |
|--------|---------|
| catalog | `CONFIG`→`CATALOG_CONFIG`, `build_catalog`→`build_asteroid_catalog`, `lookup_asteroid`→`lookup_asteroid_catalog` |
| mineral_value | `CONFIG`→`MINERAL_CONFIG`, `merge_sources`→`merge_mineral_sources`, `validate`→`validate_minerals` |
| transportation | `CONFIG`→`TRANSPORT_CONFIG`, `validate`→`validate_transport` |
| calc | `CONFIG`→`CALC_CONFIG` |

`lookup_asteroid` is the cautionary tale: modules 1 and 4 both defined it, they
are different functions over different frames, and module 4's silently won —
while module 1's help text still told you to call it. Fixed in `91f2763`.

The post-build AST scan catches new collisions. Do not ignore its warning;
either add a rename or, if the duplication really is deliberate and identical
in every copy, add the name to `_EXPECTED_DUPES`.

## Bump `pipeline_version` when output changes

Each module carries a `pipeline_version` in its config dataclass, and it is
stamped into every output CSV. That stamp is the only way to tell which code
produced a given catalog, so changing any number a run produces means bumping
it. The version-history comment block above each `pipeline_version` field is
the real changelog for this project — it records the numerical impact of each
change, often hand-verified. Add to it, don't replace it.

This has already failed once: the project was briefly developed in two places
at once, and `1.0.6` / `1.1.4` / `1.3.6` each shipped as two different things.
See the README's "parallel-repo divergence" section — CSVs stamped with those
versions cannot be trusted and should be regenerated.

Current: catalog `1.0.7`, mineral_value `1.1.5`, transportation `1.2.5`,
calc `1.3.7`, master `1.4.4` (the master version is a literal in
`build_master.py`'s `MASTER_HEADER` and `MASTER_ORCHESTRATOR` — two places).

## Config discipline

Configs are dataclasses instantiated once at module scope. Edit the field
default *inside* the dataclass, not the instance afterwards — mutating
`CONFIG.foo` after construction defeats having one editable source of truth,
and every module says so in a comment.

## Correctness invariants that were expensive to find

Undoing any of these silently corrupts the output:

- **Designation extraction** must not use a naive `^\d+` regex. For
  `"2024 BX1"` that yields `"2024"`, which cross-matches unrelated bodies.
  See `_extract_canonical_designation` in `catalog.py`.
- **`str.contains` needs `regex=False`** in every lookup helper. Designations
  and mineral names carry regex metacharacters, so `"(1) Ceres"` matched
  `"1 Ceres"` and unbalanced brackets raised `re.PatternError`.
- **TPS mass belongs inside the rocket-equation cascade**, not just in the
  cost model. It is hauled outbound as dead mass and pushed back through the
  return burn. Omitting it overstates max payload by ~30%.
- **The return-capsule volume cap must bind**, not merely be reported. It is
  the only constraint keeping the mission physical when ISRU is on and
  aerocapture is off.
- **Composition fractions sum to 0.76–0.96**, not 1.0. The residual is valued
  at a bulk-silicate floor rather than zero.
- Do not globally suppress warnings in `catalog.py` — real `RuntimeWarning`s
  (divide-by-zero in the derived physical columns) need to stay visible.

## Data sources fail softly by design

Unreachable or empty sources are tolerated and the run continues. MP3C is
regularly DNS-blocked from Colab. Do not "fix" an empty source by flipping its
toggle off — the toggle is for deliberately excluding a source, not for
routing around an outage.

`metals.dev` defaults to the key `"DEMO"`, which makes the fetcher skip
entirely. That is intentional; the demo endpoint is heavily rate-limited.

## Environment

Windows, Python 3.13, invoked as `py` (a bare `python` hits the Microsoft Store
alias and fails). The working tree is on Google Drive with the git directory
outside it — see the README's "Working copy" section, especially if the folder
gets renamed again.
