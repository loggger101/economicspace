# Version history

Every release of this pipeline, newest first, plus the measurement tables that
each release superseded. It was split out of `README.md` in 2026-08 because the
version record had grown to roughly half that file and was burying the parts
you need to actually run the thing.

- **`README.md`**: what the pipeline is, how to run it, what the model does,
  and the **current** numbers.
- **this file**: what changed and when, what the numbers used to be, and the
  per-module changelogs.
- **`CLAUDE.md`**: the working notes: the traps, the invariants, and the
  reasoning behind decisions that look wrong. It is the deepest record of the
  three and the one to read before editing.

Where the two overlap, `README.md` is the current answer and this file is the
history of how it got there.

## Contents

Newest first. Every table names the release and the catalog it belongs to;
one that does not say is not to be used.

- [Current versions](#current-versions)
- [How the version numbers work](#how-the-version-numbers-work)
- [What "no number" claims rest on](#what-no-number-claims-rest-on)
- [Releases](#releases)
- [master v1.34.0: Stage 1 installs a published catalog](#master-v1340-stage-1-installs-a-published-catalog)
- [master v1.33.0 / catalog v1.3.0](#master-v1330--catalog-v130)
- [master v1.32.0](#master-v1320)
- [master v1.31.0](#master-v1310)
- [master v1.30.0](#master-v1300)
- [transportation v1.15.0 / master v1.29.0](#transportation-v1150--master-v1290)
- [calc v1.23.0](#calc-v1230)
- [calc v1.22.0](#calc-v1220)
- [calc v1.21.2](#calc-v1212)
- [calc v1.21.1](#calc-v1211)
- [calc v1.21.0](#calc-v1210)
- [master v1.25.0 - Stage 3 moved to the `spacecost` package](#master-v1250---stage-3-moved-to-the-spacecost-package)
- [calc v1.20.0](#calc-v1200)
- [catalog v1.2.0](#catalog-v120)
- [calc v1.19.2](#calc-v1192)
- [calc v1.19.1](#calc-v1191)
- [calc v1.19.0 / mineral_value v1.9.0 / transportation v1.14.0](#calc-v1190--mineral_value-v190--transportation-v1140)
- [calc v1.18.0 / mineral_value v1.8.0 / transportation v1.13.0](#calc-v1180--mineral_value-v180--transportation-v1130)
- [calc v1.17.8](#calc-v1178)
- [mineral_value v1.7.1](#mineral_value-v171)
- [calc v1.17.7 / transportation v1.12.1](#calc-v1177--transportation-v1121)
- [calc v1.17.6](#calc-v1176)
- [calc v1.17.5](#calc-v1175)
- [calc v1.17.4 / catalog v1.1.1](#calc-v1174--catalog-v111)
- [calc v1.17.3](#calc-v1173)
- [calc v1.17.2](#calc-v1172)
- [calc v1.17.1](#calc-v1171)
- [calc v1.17.0](#calc-v1170)
- [calc v1.16.0](#calc-v1160)
- [calc v1.15.0 / transportation v1.12.0](#calc-v1150--transportation-v1120)
- [calc v1.14.2](#calc-v1142)
- [calc v1.14.1](#calc-v1141)
- [calc v1.14.0 / transportation v1.11.0](#calc-v1140--transportation-v1110)
- [catalog v1.1.0 / calc v1.13.0](#catalog-v110--calc-v1130)
- [calc v1.12.0 / transportation v1.10.0](#calc-v1120--transportation-v1100)
- [calc v1.11.0 / transportation v1.9.0](#calc-v1110--transportation-v190)
- [calc v1.10.1](#calc-v1101)
- [calc v1.10.0](#calc-v1100)
- [Earlier releases](#earlier-releases)
- [Stage 1 changelog: `modules/catalog.py`](#stage-1-changelog-modulescatalogpy)
- [Stage 2 changelog: `modules/mineral_value.py`](#stage-2-changelog-modulesmineral_valuepy)
- [Stage 3 changelog: `modules/transportation.py`](#stage-3-changelog-modulestransportationpy)
- [Stage 4 changelog: `modules/calc.py`](#stage-4-changelog-modulescalcpy)
- [Cost/revenue matrices](#costrevenue-matrices)
- [The 28-cell campaign, 2026-09](#the-28-cell-campaign-2026-09)
- [The population re-derivation, 2026-09-14](#the-population-re-derivation-2026-09-14)
- [The destination runtime table, 2026-09-15](#the-destination-runtime-table-2026-09-15)
- [The docs harness stopped passing on files it never read, 2026-09-15](#the-docs-harness-stopped-passing-on-files-it-never-read-2026-09-15)
- [The stale working tree became checkable, 2026-09-15](#the-stale-working-tree-became-checkable-2026-09-15)
- [What the v1.17.x line was worth](#what-the-v117x-line-was-worth)
- [The sampling rule](#the-sampling-rule)
- [Runtime history](#runtime-history)
- [The programme-scale curves](#the-programme-scale-curves)
- [The parallel-repo divergence](#the-parallel-repo-divergence)

## Current versions

| Stage | Module | Version | Last changed |
|---|---|---|---|
| 1 | `modules/catalog.py` | **1.3.0** | v1.3.0, bodies joined across sources and every source validated against its service. The stamp is [`asteroid_catalog`](https://github.com/loggger101/AsteroidCatalog)'s data contract; since master v1.34.0 Stage 1 installs a published release of that catalog and checks the contract rather than stamping it |
| 2 | `modules/mineral_value.py` | **1.9.0** | v1.9.0, `geo` priced: a seventh delivery destination |
| 3 | `modules/transportation.py` | **1.15.0** | v1.15.0, the `environments` table: the stamp follows [`spacecost`](https://github.com/loggger101/spacecost)'s data contract, which owns it since master v1.25.0 |
| 4 | `modules/calc.py` | **1.23.0** | v1.23.0, the 5% depletion cap comes off: a mission may take the whole body |
| - | `master.py` | **1.34.0** | a literal in `build_master.py`, in **two** places |

⚠️  **The authority is the `pipeline_version` field in each module's config
dataclass, never a table.** This one has rotted before: the README's copy read
calc 1.16.0 until 2026-08-21, four releases behind. Check the dataclass.

## How the version numbers work

Each module carries a `pipeline_version` that is stamped into every output CSV,
so the stamp is the only way to tell which code produced a given catalog.

**The rule is one-directional: changing any number a run produces means
bumping. Bumping does not mean a number changed.** Reading a version as
evidence that a result moved is the mistake the table below exists to prevent.

Twenty-one stamps so far have moved without moving a number:

| stamp | why it moved | what a re-run gives |
|---|---|---|
| calc `1.10.1` | performance only | bit-identical, verified |
| calc `1.14.1` | performance only | bit-identical, verified |
| calc `1.14.2` | performance only | bit-identical, verified |
| calc `1.17.0` | **two defaults flipped** | bit-identical *only if configured explicitly* |
| calc `1.17.1` | performance only | bit-identical, verified |
| calc `1.17.2` | performance only | bit-identical, verified |
| calc `1.17.3` | **dead code removed** | bit-identical, verified |
| calc `1.17.4` | performance only | bit-identical, verified |
| calc `1.17.5` | performance only | bit-identical, verified |
| calc `1.17.6` | performance only | bit-identical, verified |
| calc `1.17.7` | **memory bound** | bit-identical, verified |
| mineral_value `1.7.1` | **silent default closed** | bit-identical, verified |
| calc `1.17.8` | **a new upstream check** | bit-identical, verified |
| calc `1.18.0` | **a sixth destination** | bit-identical, verified |
| mineral_value `1.8.0` | **a sixth destination** | bit-identical, verified |
| transportation `1.13.0` | **three reference rows** | bit-identical, verified |
| calc `1.19.0` | **a seventh destination** | bit-identical, verified |
| mineral_value `1.9.0` | **a seventh destination** | bit-identical, verified |
| transportation `1.14.0` | **four reference rows** | bit-identical, verified |
| transportation `1.15.0` | **a sixth reference table** | bit-identical, verified |
| calc `1.19.1` | **a check that cried wolf** | bit-identical, verified |

⚠️  **Read the module, not just the number.** `1.7.1` and `1.17.1` are different
modules and unrelated releases, and so are `1.13.0` and `1.18.0`, which shipped
together. Every row above is calc except `mineral_value 1.7.1`,
`mineral_value 1.8.0`, `mineral_value 1.9.0`, `transportation 1.13.0`,
`transportation 1.14.0` and `transportation 1.15.0`.

⚠️  **Derive any count of these from the table, not from a sentence.** Eight
rows are performance stamps and thirteen are not, and that split rotted in prose
three times before `verify_docs.py` check 2 started holding both copies of this
table to each other and both sentences to the tables. It is spelled out here
*because* it is checked; a count nothing checks is a number waiting to rot.

**Console text is not output.** The 2026-08-23 pass that rewrote all 243
`print()` calls to pure ASCII bumped nothing, because no CSV byte changed. That
cuts against `1.17.3` (bumped for dead code) and `mineral_value 1.7.1` (bumped
while bit-identical); both were choices the rule permits, not obligations.

## What "no number" claims rest on

Almost every release below is argued from **bit-identity**: not "the numbers
look right" but "these are the same floats, and here is the hash." The six
checks are committed as `verify.py`; see
[Verifying a change](README.md#verifying-a-change).

⚠️  Before 2026-08-21 every release rebuilt those checks from memory and threw
them away, and eleven harness bugs came out of it; three of which produced
conclusions that were written down before being caught. Where a release note
below quotes a hash, it was produced by a harness that no longer exists; the
four cell hashes `verify.py` prints reproduce the ones committed for v1.17.4
and v1.17.6 exactly, which is what makes it a replacement for those rather than
a twelfth one to have to trust.

## master v1.34.0: Stage 1 installs a published catalog

**Stage 1 stops building the catalog and installs a pinned, published build of
it.** The AsteroidCatalog repository now publishes each build as a GitHub
Release (`data-YYYY-MM-DD`: the gzipped CSV, a Parquet copy, the rejection log,
the composition tables and a manifest of sha256s), gated before publishing:
every source must have contributed above a floor, the stamps must be single and
current, and the catalog must not have shrunk against the previous release.
The pinned catalog release is `data-2026-09-23`.

**Why.** A build cannot be repeated -- JPL adds bodies daily -- so re-running
Stage 1 replaced the one input every committed number was measured on, with no
way back, and two hosts that each ran Stage 1 were on different catalogs. A
pinned release is the same bytes everywhere. Stage 1 is now idempotent: at an
installed pin it downloads nothing.

### What changes here

- `modules/catalog.py` downloads the manifest, refuses a release that is not
  this pipeline's data contract, downloads and sha256-checks the catalog
  (gzipped and decompressed) and `taxonomy.json` in a staging directory, and
  only then replaces what is on disk, writing `catalog_manifest.json` last.
- **The `asteroid_catalog` package is no longer installed**: gone from
  `requirements.txt`, `_MASTER_REQUIRED` / `_MASTER_PIP_SPEC`, and the module's
  own install block, and with it the config mirror and the two import-time
  drift checks (`STAGE 1 SETTINGS DRIFT`, `STAGE 1 CONTRACT DRIFT`). Nothing in
  this repo can break at import when the package changes any more.
- `TAXONOMY_COMPOSITION` and `PGM_ENRICHMENT_BY_TYPE` are read from the
  installed release's tables, the ones its catalog was built with.
- `run_pipeline.py` loses `--asteroids` and the presets' `asteroids` value (the
  `quick` preset's 20,000-row catalog is gone: Stage 1 always installs the
  whole release, and Stage 4's `--rows` is what makes a run quick). Its banner
  names the catalog release; its overwrite question skips Stage 1 when the pin
  is already installed.
- The dashboard: a "Catalog" group with the one dial, the build dials gone from
  "Run size", "Catalog population" and "Data sources", and Stage 1's time prior
  a flat 1.5 min.
- `verify_stage1.py` is rewritten around the seam; see
  [README](README.md#verifying-stage-1). `verify_docs.py` check 7 now holds the
  release pin to every document that names it, and no longer looks for a
  package pin.
- `build_master.py` no longer renames `lookup_asteroid` for Module 1, which no
  longer defines one.

### What it was tested against

The `data-2026-09-23` catalog was built and packaged locally with the new
gates (all passed: 1,566,617 bodies; JPL 1,566,617, SsODNet 1,563,644, MP3C
1,335,046, NEOWISE 143,015; 149,740 measured diameters), served from a local
mirror, and installed by the new Stage 1 into a scratch directory: 40 s cold,
31 s at an installed pin. A tampered asset and a wrong data contract were both
refused with nothing installed. `verify_stage1` passed 9 of 9 against it, check
7 re-deriving all seven composition columns over every row with 0 differing,
and the Parquet asset matched the CSV on all 95 columns.

### What did not change

- **No Stage 2, 3 or 4 code, and no number measured on the catalog on disk.**
  This release changes where the catalog comes from, not what any stage does
  with it.
- **The catalog on disk, until Stage 1 is next run.** The 2026-08-11 catalog
  (contract 1.1.0) has no manifest, is not a published release, and fails
  `verify_stage1` check 3 by design. Installing `data-2026-09-23` over it
  replaces the input the committed tables were measured on, exactly as a
  rebuild would have: keep a copy first to reproduce any of them.
- catalog `1.3.0`, mineral_value `1.9.0`, transportation `1.15.0`, calc `1.23.0`.

## master v1.33.0 / catalog v1.3.0

**asteroid_catalog v0.1.3 -> v0.2.0, which moves the catalog contract to
1.3.0.** The package's
[`CHANGELOG.md`](https://github.com/loggger101/AsteroidCatalog/blob/main/CHANGELOG.md)
is the authority for what changed in Stage 1 and the measurements behind it;
this note records what it means here.

Every source was pulled in full on 2026-09-22/23 and joined back to JPL by
hand. Each defect it found had passed every build:

| defect | measured |
|---|---|
| MP3C never contributed: every URL the fetcher tried answered 404, the service having moved to `dachs.oca.eu` | 0 rows on every build; 1,335,502 bodies now |
| NEOWISE bodies joined nothing when filed under another designation, or NEOWISE's own `"1996 GQ0"` | 10,627 of 143,318 bodies (7.4%) |
| SsODNet rows under a secondary designation survived as duplicates | 182 in the 2026-08-11 build |
| duplicates culled rather than combined; a sigma could sit beside another source's value | 27,864 NEOWISE bodies with repeat fits |
| `orbital_period_yr` was in DAYS, from both JPL and SsODNet | Ceres read 1679.85 |
| `name` held provisional designations | 1,537,189 unnamed bodies |
| source placeholders read as data: MP3C H = 0 and 99.99, NEOWISE's assumed fit values and -0.999 | 26 bodies sized at 5,000-5,600 km |

**Same-day A/B on the full sources** (package tests, not this repo's harness):
all 1,566,600 bodies the old code accepted are kept, plus 16; rejected for no
orbit 10,632 -> 210; **not one measured diameter changed value**.

### What changes here

- The pin, in all six places, and `_check_data_contract` now expects `1.3.0`.
- `CatalogConfig` gains `use_mpc_identifications`, copied verbatim from the
  package (its comment is the dashboard's help text), and it is listed in the
  dashboard's "Data sources" group.
- **After the next Stage 1 build**, a Stage 4 result's `name` is empty for an
  unnamed body rather than its provisional designation; `designation` is its
  identity, as before.

### What did not change

- **The catalog on disk.** Stage 1 was not re-run; it is still stamped
  `1.1.0`, so `stamp_check()` keeps reporting it as stale, which is the
  deliberate-lag case it cannot tell from a failed write.
- **No Stage 2, 3 or 4 number.** All four Stage 4 cells reproduce the `1.23.0`
  baseline, 143/143 columns identical, and `verify_stage1` (10 checks, check 7
  re-deriving the composition columns over the catalog on disk through the new
  package), `verify_stage3`, `verify_docs` and `platform_check` all pass.
- mineral_value `1.9.0`, transportation `1.15.0`, calc `1.23.0`.

## master v1.32.0

**asteroid_catalog v0.1.1 -> v0.1.3, and the redundancies the split left.
No module stamp moved, and no number moved.** The catalog contract stays at
**1.2.0**.

A redundancy audit the day after the split asked two questions of every
top-level name the pre-split module bound: is it still reachable, and is it
now defined more than once. **63 names carried, 0 dropped.** Two were defined
twice, and they are the same defect from opposite ends:

| | dead in | live in |
|---|---|---|
| `_PY` | the **adapter** | the package, for `fetch_ssodnet`'s pyarrow hint |
| `_fmt_limit` | the **package** | the adapter, for its startup banner |

A split moves a helper's USERS without moving the helper, or the other way
round, and what is left behind still imports, still parses, and is called by
nothing. The adapter dropped its `_PY` and reaches the package's `_fmt_limit`
rather than keeping a copy.

⚠️  **The sweep that found them had to be run on both sides, and its corpus was
the hard part.** The first attempt found `_fmt_limit` and MISSED `_PY`, because
it asked whether the name appears anywhere in the repo and four other modules
define a `_PY` of their own. A name-based corpus check is defeated by a common
name.

🚨  **Closing the second one opened a new trap, and it is the reusable half.**
`_fmt_limit` is now a private name consumed across a repository boundary:
underscore-prefixed, absent from `__all__`, called by nothing in its own repo,
so a dead-code sweep run there flags it -- and one did, the same hour.
Deleting it breaks this repo's first Stage 1 banner. The package carries
`PRIVATE_CONSUMER_SURFACE` now, a tested contract naming each private name and
the reason it is reached, proved by deleting one and watching the suite name
it. Same arrangement `spacecost` uses for the private names Stage 2 reaches.

✅  **A third redundancy was inside the package rather than across the
seam**, and it is the shape this project has a rule for: `requirements.txt`
there listed the same five dependencies `pyproject.toml` declares, by hand,
with nothing holding the two to each other -- under its own comment saying
*"pyproject.toml is the authority"*. A comment that says two copies must agree
is a request for a checker. Nothing referenced the file and it was never
packaged, so it is gone rather than checked (`v0.1.3`).

⚠️  **And the repin itself nearly falsified three sentences.** A blind
`` `v0.1.1` `` substitution over the three prose files hit **six** mentions
where only **three** are the live pin; the others were accounts of things that
happened, two about spacecost's own `v0.1.1`. `verify_docs.py` check 7 warns
about exactly this in its own comment and cannot catch it, because a falsified
history sentence is not a pin and nothing compares it. Reading the diff line
by line is what caught it.

### What did not change

- **No number.** All four Stage 4 cells reproduce the `1.23.0` baseline.
- **Stage 1's console output**, byte for byte against the pre-split module --
  which is how the `_fmt_limit` re-export was confirmed to be equivalent.
- The catalog stamp, 1.2.0.

## master v1.31.0

**Stage 1's builder moves to
[`asteroid_catalog`](https://github.com/loggger101/AsteroidCatalog), pinned to
tag `v0.1.1`. No module stamp moved, and no number moved.** `modules/catalog.py`
is an adapter, 628 lines against 3,338, and `master.py` is 2,753 lines smaller.
The catalog contract stays at **1.2.0**, because it is the PACKAGE's data
contract now, mirrored here and asserted equal at import.

Second split of this kind, after Stage 3 to `spacecost` at master v1.25.0, and
the same argument: nothing in the schema of four survey fetchers, a
cross-match and a Bus-DeMeo composition table knows what a mine is. A merged
catalog with honest provenance is useful to anyone doing population
statistics, survey planning or target selection.

### This one could not be verified the way Stage 3's was

🚨  **AND THE DIFFERENCE IS THE REUSABLE PART.** `spacecost` proved itself by
building its CSVs through both paths and asserting them byte-identical.
**Stage 1 cannot be re-run at all.** JPL adds bodies daily, so a rebuilt
catalog is a different length and comparable with nothing already measured,
and the file it would overwrite is the 862 MB input every other stage reads.
There is no "run it both ways" available.

So the extraction was proved **in process**, which is the reasoning catalog
`1.1.1` used when it verified `enrich_composition` against the catalog on disk
rather than by re-running the stage:

| what | how it was compared | result |
|---|---|---|
| the reference tables | leaf by leaf, at full `repr` **and** raw IEEE bit pattern, dict **key order** included | identical |
| every pure function | both ways over a stride sample of the real 1,555,667-row catalog, cell by cell on bit patterns | identical |
| all 24 function bodies | as **source text**, against the module's own line ranges | identical |
| the config surface | field set, and every default but the documented adaptations | identical |

**25 checks, 107,521 values, 0 differing.** The probe was then fed a wrong
answer, one PGM factor moved 2.0 to 2.5, and went red on both the table and
the function that reads it, which is what makes the clean run worth quoting.
It is kept as `tools/extraction_probe.py` in the package and needs the
pre-split module out of this repo's history to run.

✅  **AND `verify_stage1.py` CHECK 7 IS THE STRONGER RESULT, because it is not
a sample.** It re-derives seven composition columns over all **1,555,667
rows** through the adapter and reports **0 differing**, along with the
literature spot-check and the full provenance census. The probe says the code
is the same code; check 7 says the whole catalog comes out the same.

### Nothing was re-typed, and that is what makes any of it mean something

The package was built by slicing source line ranges, **2,953 of the module's
3,338 lines**, and so was the adapter: the config dataclass and the
`RUN & PREVIEW` block are the original text.

⚠️  **The dataclass had to stay here AND had to stay verbatim.**
`ui_meta.scrape_field_docs` reads a field's comment block as the dashboard's
help text for that dial, so those comments are UI copy. Re-wording one
silently re-words the dashboard, which no test would have caught.

### The one real defect in the move, and how it surfaced

🚨  **A BLANKET `print` -> `say` PASS SILENCED THE ZERO-MATCH ALERT.** All 114
prints became the package's opt-in output, which is right for a library and
wrong for ten of them: the alert that fires when a supplement fetched rows and
matched NONE of the backbone is the one diagnostic that catches a fetcher
contributing nothing while its own fetch summary reads 183,408 -- the failure
that cost NEOWISE four releases. Silenced, it reads exactly like a clean
result.

✅  Ten messages are `warn()` now and print regardless of verbosity. **A defect
in the code, or a fatal abort, is loud; an external condition the design
tolerates -- MP3C unreachable, a retried TAP timeout -- is progress output.** A
blanket answer is wrong in both directions: all-loud makes the common case
noisy enough that nobody reads either.

⚠️  **What found it was comparing the adapter's startup banner with the
pre-split module's, byte for byte.** Two lines were missing, and chasing them
turned up something else: they were module-level prints that **could never
fire in a library**, because verbosity is always set after import. They were
stage banner text, so they live in the adapter now. That is package `v0.1.1`,
and the reason to run a banner comparison rather than assume one.

### What the split had to be taught about this repo

⚠️  **Two collision-proof names, and they are load-bearing.** The adapter
imports `build_catalog_table` and `lookup_body`, never `build_catalog`,
`lookup_asteroid` or `CONFIG`: `word_replace` rewrites all three on the way
into `master.py`, and aliasing the LOCAL name does not help because the
IMPORTED name is still a bare word. Same trap that cost the Stage 3 split a
release. The package's `tests/test_consumer_contract.py` runs this repo's real
regex against every name the adapter imports, and asserts the naive names
really would be rewritten, so the guard cannot go vacuous.

⚠️  **`_check_config_surface` collided with the Stage 3 adapter's**, and the
build's AST scan said so. Renamed to `_check_catalog_config_surface` rather
than added to `_EXPECTED_DUPES`: the two are not interchangeable copies, they
check different dataclasses against different packages.

🚨  **`verify_docs.py` CHECK 7 COVERED NEITHER PIN, AND IT IS THE CHECK
WRITTEN TO PREVENT EXACTLY THIS.** Every pattern in it spelled `spacecost`, so
the six places that type the new pin would have had nothing comparing them.
That is this repo's "a check that reads one row of a table is a check on that
row", committed a third time, inside the check written against it. The package
is a parameter there now, so a third split joins by adding one row, and a
prose claim is attributed to a package by proximity because prose carries no
URL.

⚠️  **It also could not compare `asteroid-catalog` with `asteroid_catalog`.** A
DISTRIBUTION name and an IMPORT name are not the same string; for every
package here until now they coincided, so the comparison was a bare string
match. It normalises per PEP 503 now, and deliberately does **not** carry a
general alias table: a package whose import name genuinely differs from its
distribution name should still fail there, because then the two lists really
do need separate entries.

✅  **`verify_stage1.py` gains check 9, the seam.** Is the installed package
the revision `requirements.txt` pins? Checks 1 to 8 all describe whatever
`import asteroid_catalog` reached, and none of them can tell you which
revision that was -- `__version__` moves only on a release and the data
contract identifies the schema rather than the commit. `pip install -e` at a
checkout ten commits past the tag passes all eight. That is the parallel-repo
divergence with a package manager in front of it.

### What did not change

- **No number.** Stage 4's four cell hashes reproduce against the `1.23.0`
  baseline; Stage 1 writes no CSV in this release and the catalog on disk was
  never touched.
- **The catalog stamp**, 1.2.0. It identifies the DATA; the data did not move.
- **Stage 1's console output**, byte for byte, which is what the adapter
  turning verbosity on buys.
- **Stage 3.** `verify_stage3.py` passes unchanged, all six checks.

## master v1.30.0

**spacecost v0.2.0 -> v0.3.0. No module stamp moved, and no number moved.**
The data contract stays at **1.15.0**, because the package gained a module and
not a table: `build_catalog()` writes the same seven CSVs byte for byte, so
`verify_stage3.py` check 3 passes unchanged and **Stage 3 did not have to be
re-run**, which is the whole reason this shape was chosen. A restamp would
have obliged a re-run, and a Stage 3 re-run re-fetches live prices.

### What moved, and why it should never have been here

`modules/mineral_value.py`'s delivery-leg chain and its downleg, together
about 190 lines, are `spacecost.delivery` now. The block opened by stating
what it was:

> Constants below are cross-referenced to Module 3. They are duplicated
> rather than imported because Module 2 runs BEFORE Module 3 in the pipeline
> order (and in the concatenated master.py), so the tables are not in scope.
> **If you change one of these, change it in Module 3 too.**

Thirteen numbers retyped by hand under a manual-sync instruction: nine Δv, a
launch price, and three downleg cost lines.

| what | where it came from | how it was held |
|---|---|---|
| 9 chain Δv | `DELTA_V_REFERENCE` | retyped |
| `_LEO_USD_PER_KG` 4,253 | `LAUNCH_VEHICLES_REFERENCE`, Falcon 9 reusable | retyped |
| capsule, TPS, recovery | `OPERATIONAL_COSTS_REFERENCE` | retyped |

🚨  **THE JUSTIFICATION EXPIRED AT THE STAGE 3 SPLIT AND STOOD FOR TWO MORE
RELEASES.** Concatenation order was the entire argument, and a pip-installed
package has no position in a pipeline: `master.py` installs spacecost in its
header, before any stage's code runs. The reason was true when written, went
false when master v1.25.0 made Stage 3 a package, and nothing re-read it.
**A comment explaining why two copies exist is not a reason they still have
to**, and the tell is that it was addressed to a reader rather than to a
checker.

### Derived where the table agrees, typed where it does not

Every chain Δv is a `DELTA_V_REFERENCE` lookup now. The six downleg departure
burns are **not**, and that is the decision worth recording:

| destination | value | the row | agrees |
|---|---|---|---|
| `leo` | 120 | *(no row: a LEO deorbit burn is not tabulated)* | - |
| `geo` | 1,490 | `GEO -> Earth (deorbit to entry)` 1,488 | **NO, by 2 m/s** |
| `cislunar` | 450 | `TLI -> NRHO insertion` 450 | yes |
| `lunar_surface` | 2,720 | 1,870 ascent + ~850 TEI, which has no row | partial |
| `mars_orbit` | 900 | `1-sol Mars orbit -> Earth (TEI)` 900 | yes |
| `mars_surface` | 6,200 | 4,100 + 2,100 | yes, as a sum |

Deriving all six uniformly is the tidy-looking change and it would have moved
**two published prices** -- what a kilogram of platinum is worth at GEO and in
LEO -- inside a release whose entire claim is that it moves none. They stay as
literals with the mismatch tabulated beside them. ⚠️  **Reconciling those two
is a real question and a separate release.**

### What says no number moved

Not an argument: a probe. Every value the two blocks can produce was captured
from the pre-move code at full `repr` **and as its raw IEEE bit pattern**, and
re-captured after: **271 leaf values, zero differences**, covering the seven
delivered prices, the seven downlegs, `DELIVERY_DESTINATIONS` (its `basis` and
`notes` strings included, and its key ORDER), `delivered_cost_usd_per_kg` at
three launch prices, and a 48-point sweep of the stage-mass-ratio kernel
including the two edges where the tank cannot close.

⚠️  **`math.exp`, not `np.exp`, and the package now carries both.**
`rocket.py` is the vectorised entry point and `delivery.py` is the scalar one;
they are not interchangeable here, because the two libraries are free to round
the last bit differently and this repo argues its releases from bit-identity.
`spacecost/delivery.py` says so where the exponential is.

⚠️  **`None` and `[]` still mean different things**, and the move preserved
it: `earth_surface` has no chain and avoids no launch, `leo` has an EMPTY
chain and avoids the whole LEO price. `spacecost`'s test suite now pins that
distinction, which is the first time it has been checked anywhere.

### The derivation audit: what is derived, what is stated, and the gap

The first pass derived the nine chain Delta-v and left everything else typed.
A literal-by-literal audit of the moved module then found three things.

✅  **Four of the six downleg burns ARE rows, so they are lookups now.**
`cislunar` off `TLI -> NRHO insertion`, `mars_orbit` off `1-sol Mars orbit ->
Earth (TEI)`, `mars_surface` off the ascent-plus-TEI pair, and
`lunar_surface`'s 1,870 m/s ascent off the descent row it is symmetric with.
Typing all six because two could not be derived was **a blanket exception**,
and a blanket exception is how a register stops being a decision.

🚨  **`TUG_ISP_S` IS 465 s AND THE PACKAGE'S OWN HYDROLOX ROW SAYS 452.** This
is the one number in the chain that looks derivable and is not, and it had
been quietly inconsistent since Stage 2 v1.2.0. 465 is the top of the
450-465 s band a cryogenic UPPER STAGE is quoted over, which is the right
figure for a tug; 452 is the RS-25 / RL-10 datasheet figure the propellant
table carries. Both are defensible and they are not the same number.

⚠️  **DERIVING IT IS A MODEL CHANGE AND THE MAGNITUDE IS NOT SMALL:**

| destination | at 465 s | at the table's 452 s | change |
|---|---|---|---|
| `leo` | $4,253 | $4,253 | +0.00% |
| `cislunar` | $10,809.93 | $11,130.38 | **+2.96%** |
| `geo` | $12,526.34 | $12,938.14 | **+3.29%** |
| `mars_orbit` | $13,495.71 | $13,985.91 | **+3.63%** |
| `mars_surface` | $45,105.39 | $46,751.40 | **+3.65%** |
| `lunar_surface` | $21,209.96 | $22,315.54 | **+5.21%** |

Every in-space price in the model is one of those, so this is a release with a
re-measurement behind it, not a tidy-up. **Left at 465 and the discrepancy is
ASSERTED at import** against the table's 452, so the row cannot move under the
comment describing it. Same treatment for the GEO deorbit burn, 1,490 m/s
against a row of 1,488.

✅  **THE GENERAL RULE THIS SETTLES: DERIVE WHAT AGREES, TYPE WHAT DOES NOT,
AND ASSERT THE DIFFERENCE.** A discrepancy that is documented is a sentence;
a discrepancy that is asserted cannot go stale, because the thing it compares
against raises when it moves. This file is full of the first kind.

### A derivation claim decays one literal at a time, and no output test sees it

`tests/test_delivery.py` reads the module's SOURCE and requires every numeric
literal to be either algebra (`0` and `1`) or a row on a `TYPED` register
naming the table that cannot supply it.

🚨  **NO TEST OF THE OUTPUTS COULD DO THIS.** A hardcoded 3,600 and a
looked-up 3,600 produce identical numbers and identical hashes, right up until
the row moves and only one of them follows. The bit-exactness probe that
guards this whole change would have passed a module with every lookup
converted back to a literal.

⚠️  **Both halves are findings**, the third register in this project under that
rule after `TYPED_OK` and `BORROWED`: a literal with no row is a value that
stopped being derived, and a row with no literal is a permission still being
granted for a number that has gone. Proved by planting one of each -- and by
planting a literal that changes **no value at all**, which is the case the
import assertions cannot reach and therefore the only one that tests the
register itself.

### README's destination table was the third copy, and `verify_docs` check 17 reads it

Seven rows of typed markdown restating the derivation: the price, the
kg-in-LEO ratio and every Delta-v in the chain column. Nothing read any of it.
Check 17 holds all 23 claims to `master.DELIVERY_DESTINATIONS`, including that
a Delta-v quoted in a row's prose is a burn in **that** destination's chain.
Proved able to fail on a stale price, a rotted ratio, a wrong Delta-v and a
dropped destination.

⚠️  It is check 9's lesson on a second table -- *a check that reads one row of
a table is a check on that row* -- and the reason it was worth writing is the
same one: this repo has already had the "cheapest destination" claim stand in
five files while the ledger disproving it sat in the repo.

### The pin is typed in SEVEN places, and two of them were a release stale

🚨  **CORRECTED AT THE v0.3.2 REPIN.** This section said FIVE, and five is the
number of copies that carry the tag as a **URL**. Three more carry it as
PROSE -- README's own sentence, CLAUDE.md's Stage 3 heading paragraph and
CITATIONS.md's licence note -- and only README's was read. Both of the others
sat at `v0.3.0` through the `v0.3.1` repin with nothing looking at them.

⚠️  **The reason the URL half was safe and the prose half was not is the whole
lesson.** Check 7 FINDS the URL by scanning every first-party file for it, so
a new code copy joins by existing, and that property paid the day
`modules/mineral_value.py` gained its own `_PIP_SPEC`. Prose carries no URL,
so each claim has to be NAMED -- and naming one is a check that reads one row
of a table. The same sentence this repo wrote for check 9, committed inside
the check written to prevent it.

✅  Check 7 reads all three now, on the two phrasings that assert what the pin
IS (`pinned to tag` and `pinned to a tagged release**,`), and **a file whose
claim it cannot find is a finding rather than a silent pass** -- so a rewording
cannot quietly take a copy back out of scope. It went from 4 manifests to 7,
and was proved by staling a prose copy, staling a URL copy, and rewording a
claim out of the pattern's reach.

### The pin is typed in SEVEN places now

`modules/mineral_value.py` has its own `_PIP_SPEC`, because a standalone
`py modules/mineral_value.py` has to be able to install what it imports.
`verify_docs.py` check 7 picked it up with no edit, which is that check's own
design working: it scans every first-party file for the URL rather than
reading a list of files, precisely so a fifth copy joins the comparison by
existing. **That is the first time that property has actually been exercised.**

⚠️  **Stage 2 is the first stage to reach the package now.** A name dropped
from spacecost fails a PRICING stage that runs before the Stage 3 adapter
does, and the traceback will not mention Stage 3. The four names are on
spacecost's `tests/test_consumer_contract.py`, in their own group, saying so.

### What did not change

- every module `pipeline_version`; only `master.py` moved, 1.29.0 -> 1.30.0
- `build_catalog()`'s seven CSVs, byte for byte (`verify_stage3.py` check 3)
- the data contract, 1.15.0 both sides (check 2)
- every Stage 2 price, bit-exact (the 271-value probe above)
- `campaign/worked_calculation.py`'s three borrowings, which still resolve
  against `master` because the names are re-exported rather than deleted

## transportation v1.15.0 / master v1.29.0

**spacecost v0.1.1 -> v0.2.0, and the data contract 1.14.0 -> 1.15.0.** The
stamp is not a number this repo owns any more; it is the package's data
contract, mirrored here, and `verify_stage3.py` check 2 asserts the two are
equal. It moved because the package gained a table.

`environments`, 23 destinations of solar flux, dark period and one-way light
time. Those are the multipliers three `operational_costs` rows are already
silent functions of, since 60 W/kg is a figure AT 1 AU. **Stage 4 derives its
own 1/r^2 array scaling and does not read the table**, so it moves no number
here; it is re-exported and written like the other five because a consumer that
can see five tables of six is a consumer that will one day re-derive the sixth.

**No pre-existing VALUE moved.** The five inherited tables are byte-identical
to the 1.14.0 build once the two provenance columns are stripped, which is
`verify_stage3.py` check 3 over seven files and check 4 against the CSVs
spacecost commits at the pinned tag. What moved on them is the stamp, and it is
a column on every one.

**Verified against the model**: all four calc v1.23.0 cells reproduce their
committed hashes exactly -- `a3333bc04f08e6f9` / `1640c4fe82e521d4` /
`a90b6bdd12db585e` / `af407f7e2376bb7c`, 143 of 143 columns each. The Stage 3
seam is green on all six checks, the docs harness on all fifteen, Stage 1 on
all nine.

### A repin does not require a restamp, and the disk was restamped anyway

**The rule first, because it is the part that generalises: re-run Stage 3 when
a ROW changes, not when a stamp does.** Stage 4 reads no column this contract
moved, so leaving the CSVs at 1.14.0 would have cost one `stamp_check()` line
and nothing else -- the deliberate-lag case that check's own note describes --
where re-running means re-fetching live fuel prices over the only copy of the
tables every committed measurement was taken against.

**That is not the state on disk.** The accident recorded below had already
rebuilt them at the new contract before the decision was made, so
`asteroid_pipeline/transportation/` carries seven files stamped **1.15.0** and
dated 2026-09-17: the same 36 vehicles, 41 propellants, 33 delta-v segments, 44
operational rows and 20 storage systems, the new 23-row `environments` table,
and three live-priced propellant rows that moved with the fetch. It is recorded
rather than restored, because a byte restoration of a file that no longer
exists cannot be verified against anything -- and the values that matter are in
the table below, read back out of an archived cell.

### A guard on one door is not a guard on the room

`run_pipeline.py` has asked before Stages 1-3 overwrite a CSV since
2026-08-23, and CLAUDE.md's "RUNNING STAGE 2 OR STAGE 3 DESTROYS EVERY BASELINE
YOU HOLD" is written as though that guard were the only way in. It is not.
`py modules/transportation.py` runs the stage with no guard anywhere in the
path, and on 2026-09-17 that is exactly what happened here, while
smoke-testing an import that had just been repinned.

It re-fetched three live propellant prices over the campaign's frozen tables:

| propellant | frozen 2026-09-09 | re-fetched 2026-09-17 | moved |
|---|---|---|---|
| methalox (LCH4 / LOX) | 0.186202302606 | 0.185893 | **-0.17%** |
| kerolox (RP-1 / LOX) | 0.580466991536 | 0.599073 | **+3.21%** |
| HTP / RP-1 | 1.455541072067 | 1.516942 | **+4.22%** |

**The frozen values were recoverable only because an archived cell had been
priced with them.** `leo__benef__search-on` carries `outbound_prop_cost_usd`
and `m_outbound_prop_kg` on 100,392 methalox rows, and their ratio is constant
to 1.7e-16 across all of them: the input price, read back out of an output.
The three figures above are that ratio, on the rows of that cell whose
propellant is each fuel. **A live catalog with no archive behind it is not
recoverable at all.**

What it cost, measured rather than assumed: **nothing that is committed.** All
four v1.23.0 cells reproduce, because no winner in any of them flies a
live-priced propellant -- they are 72 xenon, 39 iodine, 22 water ion, 14
krypton and 8 hydrolox on the raw cell, every one reference-priced. What is
lost is exact input-identity with the 2026-09 campaign for rows that DO choose
one, which is 11 to 15% of the beneficiated cells at four destinations.

✅  **The three fetching modules now guard their own standalone run.**
`_confirm_overwrite` names the files, refuses on EOF rather than hanging on a
scheduled task's dead stdin, and takes `--yes` for a scripted caller. Proved by
re-running the command that caused the damage: the file's hash is unchanged and
nothing was fetched. Proved the other way too -- a second run into a scratch
directory with `--yes` writes all seven files.

The guard is MIRRORED rather than shared, because a stage module is standalone
by construction and cannot import a helper, so `verify_docs.py` check 15 holds
the three copies to each other and to the call.

🚨  **And its first draft could not fail.** It tested that
`_confirm_overwrite` was MENTIONED after the build, which neutering the call to
`if False and _confirm_overwrite(...)` satisfies perfectly. Found by planting
exactly that. It matches the GATE now: the refusal, a `sys.exit` between it and
the build, and its position ahead of the build. A check nobody has seen fail is
a check nobody has seen.

### The pin was typed in four places and two of them were checked

`verify_docs.py` check 7 compared `requirements.txt` against
`_MASTER_PIP_SPEC`, which is the pair that had burned somebody. The other two
are `_PIP_SPEC` in `modules/transportation.py` -- **what a standalone module run
installs from, so the module could have gone on fetching the old tables past a
repin** -- and README's sentence naming the tag.

It scans every first-party file for the URL form now, so a fifth copy joins the
comparison with no edit here. Only the URL form counts: a bare `v0.1.1` in prose
is usually history, and both documents tell the story of a checkout that sat two
commits past it. Proved by repinning one copy alone: it goes red and names the
file.


## Releases

Newest first. Each heading names every module whose `pipeline_version`
moved in that release.

| release | date | what it was |
|---|---|---|
| [master v1.30.0](#master-v1300) | 2026-09-21 | **spacecost v0.3.0**: Stage 2's delivery chains move to the package, and the sentence explaining why they were duplicated had expired at the split |
| [transportation v1.15.0 / master v1.29.0](#transportation-v1150--master-v1290) | 2026-09-17 | **spacecost v0.2.0**: a sixth reference table, and the guard a stage module run directly never had |
| [calc v1.23.0](#calc-v1230) | 2026-09-17 | **the depletion cap comes off**: `max_mining_fraction` 0.05 -> 1.0, and a constraint that bound on 2% of bodies was sizing the mission on them |
| [calc v1.22.0](#calc-v1220) | 2026-09-14 | **four defaults moved**: the surplus past a ceiling sells at half price, and reliability, the learning curve and the cost of capital come off |
| [calc v1.21.2](#calc-v1212) | 2026-09-08 | **one market, two allowances**: the composition residual and the `silicates` phase each drew the full silicates ceiling, on 100% of bodies |
| [calc v1.21.1](#calc-v1211) | 2026-09-08 | **the ceilings recalibrated: the levels do not move, and the composition residual gets the ceiling it was already priced against** |
| [calc v1.21.0](#calc-v1210) | 2026-09-07 | **prices are constant and quantity is what binds**: the market term becomes a four-valued `market_model`, and the ceilings go into the payload knapsack |
| [calc v1.20.0](#calc-v1200) | 2026-09-04 | **both insurance premiums are off**: a transfer priced off an underwriter's book, in a model that prices masses |
| [catalog v1.2.0](#catalog-v120) | 2026-09-03 | **NEOWISE dedup decided by row order on 27,802 bodies**; the ranking could not see orbit quality; `ma` had no epoch; async TAP |
| [calc v1.19.2](#calc-v1192) | 2026-09-03 | **`mars_orbit` waited for the wrong planet** |
| [calc v1.19.1](#calc-v1191) | 2026-09-02 | a version check had been comparing every catalog against Module 3 |
| [calc v1.19.0 / mineral_value v1.9.0 / transportation v1.14.0](#calc-v1190--mineral_value-v190--transportation-v1140) | 2026-09-02 | **a seventh destination: a geostationary servicing depot** |
| [calc v1.18.0 / mineral_value v1.8.0 / transportation v1.13.0](#calc-v1180--mineral_value-v180--transportation-v1130) | 2026-09-02 | **a sixth destination: a Mars-orbit depot** |
| [calc v1.17.8](#calc-v1178) | 2026-08-27 | the loader now checks the Stage 3 stamp, not just its columns |
| [mineral_value v1.7.1](#mineral_value-v171) | 2026-08-21 | three PGM ore minerals were falling through a silent default |
| [calc v1.17.7 / transportation v1.12.1](#calc-v1177--transportation-v1121) | 2026-08-21 | a cache grew without bound; `.astype(bool)` on a nullable flag |
| [calc v1.17.6](#calc-v1176) | 2026-08-21 | composition derived per row instead of per taxonomy |
| [calc v1.17.5](#calc-v1175) | 2026-08-20 | one cache entry carries the whole campaigns-per-ship block |
| [calc v1.17.4 / catalog v1.1.1](#calc-v1174--catalog-v111) | 2026-08-20 | the catalog load, and 74.3% of the search dying on pass 2 |
| [calc v1.17.3](#calc-v1173) | 2026-08-12 | dead code, and a de-duplication note that was not true |
| [calc v1.17.2](#calc-v1172) | 2026-08-12 | the cost cascade's N-independent half, hoisted out of the ladder |
| [calc v1.17.1](#calc-v1171) | 2026-08-12 | the default flip multiplied every cost-model per-call cost by forty |
| [calc v1.17.0](#calc-v1170) | 2026-08-11 | **two defaults flipped**: beneficiation and the programme search |
| [calc v1.16.0](#calc-v1160) | 2026-08-11 | **a programme took decades and was charged for none of them** |
| [calc v1.15.0 / transportation v1.12.0](#calc-v1150--transportation-v1120) | 2026-08-11 | **the rig wore out on a calendar; programme size became searched** |
| [calc v1.14.2](#calc-v1142) | 2026-08-10 | the model's arithmetic was going through numpy, one scalar at a time |
| [calc v1.14.1](#calc-v1141) | 2026-08-10 | ~90% of the search was proving missions infeasible the expensive way |
| [calc v1.14.0 / transportation v1.11.0](#calc-v1140--transportation-v1110) | 2026-08-08 | **containment, eclipse power, the RTG objective, saturation vs N** |
| [catalog v1.1.0 / calc v1.13.0](#catalog-v110--calc-v1130) | 2026-08-08 | **89,367 asteroids became 1,554,400**: the population, not the model |
| [calc v1.12.0 / transportation v1.10.0](#calc-v1120--transportation-v1100) | 2026-08-08 | **the thruster was never modelled, only the propellant** |
| [calc v1.11.0 / transportation v1.9.0](#calc-v1110--transportation-v190) | 2026-08-08 | **tankage, the RTG row, and 16 flown propellants that were missing** |
| [calc v1.10.1](#calc-v1101) | 2026-08-07 | the first performance-only stamp, the process pool |
| [calc v1.10.0](#calc-v1100) | 2026-08-07 | **the EP stage and the return structure flew free; the search optimised the wrong thing** |
| [Earlier releases](#earlier-releases) | - | v1.9.0 and earlier, summarised |

⚠️  **A release section says what the release DID. It does not list the config
fields and output columns the release added**; that is the schema history, and
it lives in [Module changelogs](#module-changelogs) below, one section per
module in numeric order.

## calc v1.23.0

🚨  **A MISSION MAY NOW TAKE THE WHOLE BODY.** `max_mining_fraction`
goes **0.05 -> 1.0**. The 5% was a stated conservatism -- *"single mission can
never strip-mine the whole asteroid ... 5% is conservative for a first mission
to a hundreds-of-kilometre body"* -- and it was never derived from anything.
Requested directly: the haul should be bounded by what the mission can actually
do, not by a round number.

⚠️  **The three real bounds are unchanged and they are the ones that
bind.** What the rig can dig in the time
(`mining_rate_kg_per_day_per_kg_rig` x `max_mining_duration_yr` = 219,200 kg at
the defaults), the return capsule's volume cap, and the rocket equation. The
depletion cap sat on top of those, and past about 8% of a typical body it is
not the binding one at all.

### What it was worth

The 400/150-row stride cells at cislunar, both settings run in ONE process,
same build, only the field differing:

| cell | phi = 0.05 | **phi = 1.0** | change | rows moved | worse |
|---|---|---|---|---|---|
| `raw` | 9.7517x | **10.2503x** | +5.11% | 3 of 155 | 2 |
| `raw+search` | 7.4656x | **7.4656x** | none | 2 of 155 | 1 |
| `benef` | 7.1104x | **7.1104x** | **bit-identical** | 0 of 65 | 0 |
| `benef+search` | 4.3224x | **4.3224x** | **bit-identical** | 0 of 65 | 0 |

Cell hashes, `phi = 0.05` then `phi = 1.0`:

```
raw           f6c52720c5b886eb -> a3333bc04f08e6f9
raw+search    39172396cc26cbc7 -> 1640c4fe82e521d4
benef         a90b6bdd12db585e -> a90b6bdd12db585e     MATCH
benef+search  af407f7e2376bb7c -> af407f7e2376bb7c     MATCH
```

✅  **BOTH BENEFICIATED CELLS ARE BIT-IDENTICAL**, which is the cleanest
statement of how little this bound was doing: concentrating raises the FEED the
rig digs, so if the cap were anywhere near binding it would bind hardest there.
It binds on no beneficiated row in the sample at all. The winner is unchanged
in all four cells.

🚨  **AND THE RAW HEADLINE GOT 5.11% WORSE, WHICH IS THE FINDING
RATHER THAN A COST.** Relaxing a constraint cannot make a fixed mission worse;
it made the reported answer worse because **the haul is DERIVED from whichever
constraint binds rather than searched**. Payload is not a search axis. Swept on
2017 KJ5, the raw cell's winner, holding everything else fixed:

| `max_mining_fraction` | haul | best ratio | architecture |
|---|---|---|---|
| 0.01 | 23,481 kg | 27.3943x | H3 (24L) / iodine |
| 0.02 | 46,962 kg | 16.1025x | Falcon Heavy / water ion |
| **0.05** | **117,406 kg** | **9.7517x** | **New Glenn / xenon** |
| 0.08 | 97,875 kg | 10.2503x | Falcon Heavy / iodine |
| 0.10 | 97,875 kg | 10.2503x | Falcon Heavy / iodine |
| 0.20 | 97,875 kg | 10.2503x | Falcon Heavy / iodine |
| 0.50 | 97,875 kg | 10.2503x | Falcon Heavy / iodine |
| **1.00** | **97,875 kg** | **10.2503x** | Falcon Heavy / iodine |

**The plateau from 0.08 up is the cap ceasing to bind.** Everything below it is
the cap choosing the mission's size, and 0.05 happened to land on a haul that
prices better than the one the mass budget picks unclamped. The old default was
improving the headline by forcing a smaller mission, on a body where nothing
physical asked for one.

⚠️  **So 9.7517x was a better number and a worse measurement**, and
it is the figure [calc v1.22.0](#calc-v1220) reports as its raw cell. That
section is unchanged and stays correct for the release it names.

✅  **The programme search absorbs it entirely**: `raw+search` reports the
identical 7.4656x on a differing hash, because a ladder that chooses a fleet
can answer a bigger per-mission haul by flying fewer of them. A model change
visible at N = 1 and invisible under the search is worth knowing about before
quoting either cell as the effect.

### Invariants

`py verify.py check --skip prune parallel --tag 1.23.0`, cislunar, at this
release's defaults:

- **mass ledger**: `max |error| 0.000000000 kg` on all four cells
- **never-worse**: 3 pairings, `worse 0` on every one, max <= 1.000000
- **market ceilings**: `cap beat unbounded on 0`, both searched cells
- **Stage 2 tables**: 31 rows recomputed at cislunar, all identical

⚠️  **Check 1 reports `NOT VERIFIED` on purpose**: the baseline was
taken on a tree carrying this change, so it would be comparing the change with
itself. The evidence for what moved is the one-process A/B above, which is the
construction this project requires for a ratio anyway.

### What did not change

No model term, no coefficient, no reference-table row, and no output column.
`mineable_kg` is still computed, still carried on `AsteroidContext`, still
subtracted from by the ISRU feed, and still bounds the haul -- on a body small
enough for the whole of it to be less than what the rig could dig, which is the
case the bound is now reserved for. Set `max_mining_fraction` below 1.0 to
restore a depletion limit; a 1.22.0 catalog is reproduced exactly by setting it
to 0.05.

### The full-catalog default cell at this release (2026-09-18)

The release above is argued from 400/150-row stride cells. This is the
configure-nothing cell over every row of the 1,555,667-row catalog: `cislunar`,
beneficiated, programme search on, 12 workers, `--preset full`, **12,000.5 s**.
Stages 1-3 were not run, and the live Stage 2 catalog was verified
byte-identical to `campaign/stage2/mineral_value_catalog.cislunar.csv` before
launch, so the 2026-09-09 price epoch is the 28-cell campaign's.

| | v1.22.0 | **v1.23.0 (this run)** |
|---|---|---|
| cost / revenue | 3.1822x | **3.1822x** |
| winner | 2021 CX5 (D) | 2021 CX5 (D) |
| vehicle / propellant | New Glenn / iodine | New Glenn / iodine |
| payload | 62,283 kg | 62,283 kg |
| programme | N = 18, 6 ships x 3 campaigns | N = 18, 6 ships x 3 campaigns |
| evaluable rows | 660,253 | **660,253** |
| wall clock | 11,676 s | 12,000 s |

#### The winner is bit-identical and the population is not

The objective is `3.182208152479452` in both builds, the payload
`62282.753868077045` and the concentration ratio `3.518630541998643`: the same
floats, not the same rounding. Paired row by row on `designation`, **7,513 rows
(1.14%) move**, 3,336 change propellant and 4,740 change vehicle.

🚨  **THAT IS THIS PROJECT'S STANDING CAMPAIGN FINDING RUNNING BACKWARDS.**
The 2026-09 campaign's most reusable result is that winner rows moved 8-69%
while the population medians moved 0.1 to 2.3 pp. Here the winner does not move
at all and the population does. **A headline that reproduces exactly is not
evidence that the model did not change.**

#### Two things moved between the cells, so they are attributed rather than guessed

The propellant price is recoverable from a Stage 4 row as
`outbound_prop_cost_usd / m_outbound_prop_kg`. Exactly three moved, and they are
the three refetched on 2026-09-17 by the guard that did not exist:

| propellant | v1.22.0 | v1.23.0 | moved |
|---|---|---|---|
| HTP / RP-1 | 1.455541 | 1.516942 | **+4.218%** |
| kerolox | 0.580467 | 0.599073 | **+3.205%** |
| methalox | 0.186202 | 0.185893 | **-0.166%** |

Every other propellant price is identical to the last bit. A price move can only
reach a row whose chosen propellant is one of those three in one build or the
other, which makes the split exact:

| | rows |
|---|---|
| objective moved | 7,513 |
| reachable by a price move | 1,436 |
| **NOT reachable, so the dial** | **6,077** |

The dial-only rows are **5,830 better and 247 worse**, worst regression
**+391.27** on the objective, which is `max_mining_fraction` no longer sizing a
mission that nothing physical asked to be small.

⚠️  **The methalox share halving is the DIAL, not the price**, and the
direction is what says so: methalox got **cheaper** and lost share, 0.1989% to
0.0830%, with 866 rows leaving it for iodine (529) and xenon (127). A bigger
haul is a different mass ratio, and methalox wins on tankage at high mass ratio.

#### The 65-row sample could not have seen this

The release note above reports both beneficiated cislunar cells **bit-identical**
under this dial, `0 of 65 rows` moved. On the full catalog the same cell moves
6,077 rows on the dial alone.

✅  **That is not a contradiction and the arithmetic is the point**: 1.14% of 65
rows is under one row, so a clean sample was the expected outcome either way.
What was wrong is the reading. **"Bit-identical on 65 rows" is a statement about
the sample**, and it was carried forward as a statement about the cell. THE
SAMPLING RULE already covers wall clocks, cost ratios and memory; this is the
fourth quantity, a **population share**, and it is the one that looks safest
because a hash either matches or it does not.

#### Invariants, on all 660,253 rows

- **mass ledger**: `max |error| 0.000000000 kg`
- **programme structure**: `N = F x W` on every row, and `W > trips` never
- `W < trips` on **23,151 rows (3.51%)**
- **`saturation_multiplier` identically 1.0**, min and max, which is correct and
  inert under `capacity_cap`
- `unsold_payload_kg` and `surplus_payload_kg` are exclusive: **0 rows carry
  both**, 0 unsold and 31,576 with a genuine surplus
- clearing min **0.839715**, median 1.000000, **6.42%** of rows bound
- **113,222 rows (17.15%)** at `max_fleet_ships`

⚠️  **A bare `unsold_payload_kg > 0` reports 1,882 unsold rows against a true
0.** The beneficiated path forms that column by subtracting two associations of
one quantity, so an unshrunk hold leaves a ULP. The milligram floor is the same
one `verify.py` check 7 takes.

⚠️  **The never-worse pairings are NOT reported, because they cannot be run.**
Both join two runs on `designation`, and the v1.23.0 square has only this
corner; the other three cells are v1.22.0 or older. Joining across releases
compares two models rather than two settings.

#### `MEASURED_CELL_SECONDS` deliberately does not move

It is the four cislunar cells at `MEASURED_CELL_CALC`, and only one of the four
exists at v1.23.0. Moving one row would make the dict a mixed-release object and
`verify_docs.py` check 9 would go red, having no v1.23.0 logs behind the other
three. The wall clock is 2.8% off v1.22.0's anyway, which is inside the session
drift this release's own runtime note says the host cannot resolve.

#### The archive, and the worked calculation

Archived as `cislunar__benef__search-on__calc-1.23.0.csv.gz`, calc-suffixed so
that `population.py`, `analyse.py` and `worked_calculation.py` cannot mistake it
for the campaign's own cell, all three building exact filenames rather than
globbing.

`py campaign/worked_calculation.py --audit --catalog <that archive>` derives
**88 quantities: 87 bit-exact, 1 within 1e-12** (`diameter_km`, 6.795e-16
relative), **0 DIFFER**, with 121 of 121 non-zero columns shown, **35 of 35**
reference constants shown, 2 of 106 values still matched after every one is
moved 31.7%, and no typed number in a sentence.

✅  **It is the first archive that needs no `--max-mining-fraction` override**,
because the run and the live default are both 1.0. Every older archive was
written at 0.05 and re-derives as a different, smaller mission without the flag.

## calc v1.22.0

**Four defaults moved. The surplus past a market ceiling sells at half price
instead of being abandoned, and reliability, the learning curve and the cost of
capital come off.**

Three of the four are the same decision, and it is the one v1.20.0 made about
insurance: a charge that is **real** and is nonetheless not what this pipeline
asks. The fourth is a model change, and it makes the ceiling a price rather
than a wall.

### The membership test, and which side each of these is on

[README's corrections list](README.md#what-the-model-charges-for) turns on one
question, **"was the model getting something for free?"**, and everything on it
defaults ON. v1.20.0 added a second list for the opposite case, and insurance
was its only entry. It has three more:

| | the charge is | why the default moved |
|---|---|---|
| `apply_wacc_compounding` | **right, and not asked** | a discount rate says whose money this is; the model does not know |
| `model_reliability` | **right, and not asked** | it multiplies the ANSWER by two judgements and one measurement |
| `model_learning_curve` | **right, and not asked** | it prices a factory this programme does not have |
| `charge_tanker_flights` | **wrong here** | v1.11.0's entry, gated rather than declined; unchanged |

⚠️  **None of this says the risk is not real or the money is not spent.** It
says a default run answers *what it costs to move a kilogram if it works*,
which is the framing that already makes the two surface delivery prices
[marginal-transport lower bounds](README.md#what-a-kilogram-is-worth). Every
one of the four flags turns back on individually.

⚠️  **`apply_wacc_compounding` takes `model_programme_calendar` with it.** The
calendar charge is time-value, and `programme_calendar_multipliers` returns
exactly (1.0, 1.0) at a zero rate by construction -- the guard is
`if w == 1 or wacc <= 0.0 or cadence_yr <= 0.0` -- so that term is inert until
a rate comes back. The flag is left ON rather than flipped, because it still
says the right thing about what the model should charge the moment there is
something to charge; the run banner reports which of the two states it is in
rather than leaving a reader to derive it.

🚨  **AND THAT IS THE RELEASE'S LARGEST STRUCTURAL CONSEQUENCE, AS OPPOSED TO
ITS LARGEST NUMERICAL ONE.** Measured on the searched beneficiated sample cell:

| | with the rate on | with it off |
|---|---|---|
| `programme_calendar_multiplier` | 1.160 to 1.834, **median 1.457** | **1.0 on 65/65 rows** |
| `wacc_multiplier` | 1.593 to 3.459, median 1.935 | 1.0 on 65/65 |
| **`W < trips`** | **29.23%** of rows | **1.54%** |
| fleet median / N median | 6 / 30 | 4 / 20 |

So v1.16.0's whole contribution -- giving campaigns-per-ship a reason to be
less than the rig's trip life, and thereby making the programme search
two-dimensional -- is inert on 98.5% of rows. **The search still PRICES ~40
programmes per candidate**, so the runtime for that dimension is still being
paid for an axis that almost never changes the answer.

✅  **It is not v1.14.0's failure mode returning, and the check is specific.**
Three bounds are untouched: the capacity ceilings still bound the fleet F, the
rig's duty-cycle life still caps W, and `max_fleet_ships` still stops the
ladder, so N = F x W is bounded on both factors. The residual 1.54% is the
ceiling still declining a trip occasionally, which is the tell that the
objective is NEARLY monotone in W rather than monotone.

### The ceiling stops being a wall

v1.21.0 made `capacity_cap` a quantity wall: everything inside a commodity's
ceiling sold at the quoted price and everything past it earned **nothing**,
reported as `unsold_payload_kg`. That is the right shape for a market that
refuses the sale outright, and it is too strong for most of the ones in
`IN_SPACE_ANNUAL_DEMAND_KG`. A destination that absorbs 100 t/yr of water at
the quoted price does not become unable to take the 101st tonne; it takes it at
a price that clears, which is the whole content of a supply curve sloping down.

`sell_surplus_at_discount` (True) sells it at `surplus_price_fraction` (0.5).
**0.5 is a deliberately round number with no market study behind it**, which is
why it is a dial rather than a buried constant; 0.0 reproduces the wall exactly
and 1.0 would remove the ceiling altogether.

🚨  **THE PROGRAMME IS STILL BOUNDED, AND THAT IS THE OBJECTION TO CHECK
FIRST.** The ladder turns over because the marginal kilogram past a ceiling is
worth strictly less than the one before it: a bigger fleet delivers more often,
each delivery gets a shorter accumulation window, a larger share of every load
falls into the discounted tier, and another ship adds its whole cost against a
falling marginal revenue. A wall is the `surplus_price_fraction = 0` end of
this model rather than a different one.

### In a concentrated load it changes what the ship carries

This is the half that is not a re-pricing. A beneficiated load chooses its
contents, so the discount puts every phase into the knapsack **twice**: once at
full price up to its market allowance, once at the discounted price above it.
The merged list is sorted by unit price like any other fractional knapsack, so
a rich phase's half-price surplus can outrank a poor phase's full-price
allowance, and where it does, the optimal load carries it instead.

✅  **Greedy is still exact.** A two-step price schedule is two ITEMS, not a
clamp: each has a constant unit value and is divisible, which is the only
condition greedy needs. Checked against an integer DP that shares no code with
the walk -- 150 random instances, every split of every phase between its two
tiers enumerated -- plus 400 instances proving `caps=None` reproduces an
independently written greedy bit for bit, 400 proving `surplus_price_fraction`
0.0 reproduces an independently written bounded greedy bit for bit, and 300
proving the value is monotone in the fraction and equal to the UNCAPPED load at
1.0. ⚠️  Those last two compare against a REFERENCE implementation, not against
the v1.21.2 code; what proves bit-identity with the code is the acceptance test
below, which exercises both paths on real cells.

⚠️  **It cannot be done as a second pass over the leftovers**, which is the
implementation that suggests itself. That fills the hold full-price-first and
tops up with surplus afterwards, which is a different and strictly worse load,
and it is the "clamp bolted onto the outside of an optimiser" shape
`optimal_payload_mix` already warns against.

⚠️  **One walk, not two.** The tiered sequence is built ahead of the loop and
the loop is unchanged for every other caller: the tier ledger is `None` on any
call that is not tiered, so the default path pays one `is None` test per phase
and no arithmetic. Tiers are off whenever `want_phase` is set, because that
short circuit returns the first take of the named phase and would miss the
surplus; it is not a live combination, since `want_phase` belongs to the SIZING
path and the sizing path must never pass `caps` at all.

### The acceptance test: restoring the four flags reproduces v1.21.2

🚨  **THIS IS THE LOAD-BEARING VERIFICATION AND IT WAS RUN FIRST.** Without it
no delta below is interpretable: a plumbing change that moved something on its
own would be indistinguishable from a default that moved it. The four cells at
`verify.py`'s caps, on the new build with all four flags set back:

| cell | shared columns | hash | |
|---|---|---|---|
| raw | **142 / 142** | `69db5aed0bd5063b` | MATCH |
| raw + search | **142 / 142** | `8b5fef9af02b8da8` | MATCH |
| benef | **142 / 142** | `bc7bc81c3a57cd1f` | MATCH |
| benef + search | **142 / 142** | `ae17596e31a8c156` | MATCH |

⚠️  **Over the SHARED columns, deliberately, so these four hashes are not
comparable with the ones in older sections of this file.** The new build
carries a column the old one does not, `surplus_payload_kg`, so a hash of the
whole frame is guaranteed to differ and says nothing at all about the model. A
comparison reporting DIFFER on that basis is a broken comparator, which is this
project's most-repeated failure, so the column set is named rather than assumed.

⚠️  **And the first run of that comparator WAS broken, the other way round.**
It reported 137-139 of 142 columns identical while the hashes MATCHED, on
`thrust_scaling`, `isru_feed_material`, `name`, `payload_mix` and
`payload_dominant_phase`. The cause: it tested `dtype == object`, and on
**pandas 3.0** a text column reads back as an Arrow-backed `StringDtype`, so
every text column fell through to the numeric path. The hash was right, as it
has been every previous time the two disagreed.

### What it moved

Cislunar, `verify.py`'s caps (400 raw / 150 beneficiated rows, 155 and 65
evaluable), `capacity_cap`, against the same cells on v1.21.2:

| cell | v1.21.2 | **v1.22.0** | change | winner |
|---|---|---|---|---|
| raw, N = 1 | 25.7233x | **9.7517x** | **-62.1%** | 2017 KJ5, unchanged |
| raw, searched | 19.7213x | **7.4656x** | **-62.1%** | 2017 KJ5, unchanged |
| benef, N = 1 | 20.5353x | **7.1104x** | **-65.4%** | 2010 FG81, unchanged |
| **benef + searched** | 8.9005x | **4.3224x** | **-51.4%** | 2010 FG81, unchanged |

🚨  **THE WINNER COLUMN WAS WRONG IN ALL FOUR ROWS UNTIL 2026-09-14, AND IT WAS
WRONG THE SAME WAY EACH TIME: IT NAMED `df.iloc[0]`.** The output frame is
SORTED BY `profit_usd` and the project ranks on `total_cost_usd /
gross_value_usd`, so the first row of the file is the cheapest-to-fly mission
and not the objective winner. It reported `2025 SV5 -> 701967`, `2017 VC38`,
`2014 WC23` and `735549 -> 2014 WC23`, which are exactly the profit-sorted
first rows of the eight archived cells. Re-extracted from
`.verify/baseline-1.21.2/` and `.verify/baseline-1.22.0/` with
`run_cell.py`'s own filter (`_obj > 0`, `nsmallest(1, "_obj")`): the ratios
were right and every designation was not.

✅  **The correction changes what the table SAYS, not only what it prints: the
winner does not move in any of the four cells.** The four defaults are worth
51-65% of the objective and re-rank nothing at the top, which is
[the winner moved and the population did not](CLAUDE.md#what-the-model-currently-says-and-what-that-retired)
arriving inverted -- the level moved and the winner did not. A table whose
winner column was read off the wrong row could not have said so.

⚠️  **`campaign/run_cell.py` is not affected and neither is any campaign
table.** It has always used `ok.nsmallest(1, "_obj").iloc[0]`; this was a
hand-extraction written for one release note, which is precisely the kind of
one-off reader this file keeps catching. `20.5354x` above was a rounding slip
in the same table for the same cell v1.21.2's own note records as `20.5353x`;
the archived value is `20.535349`.

⚠️  **These are 155- and 65-row sample cells and are NOT the headline matrix.**
They are the four cells `verify.py` runs, which is why every release in this
file is argued on them. The full-catalog 28-cell matrix in README is a v1.21.2
measurement and stays one until somebody pays the 63 hours to re-run it.

### The two mass columns, on real rows

`unsold_payload_kg` goes to **zero on every cell** and `surplus_payload_kg`
picks the mass up, which is the exclusivity `verify.py` check 7 now asserts:

| cell | unsold rows, v1.21.2 | surplus rows, v1.22.0 | clearing min |
|---|---|---|---|
| raw, N = 1 | 0 | 1 (max 7,890 kg) | 1.0000 -> 0.9741 |
| raw, searched | **57** | **31** (max 30,275 kg) | 0.9235 -> 0.8806 |
| benef, N = 1 | 0 | 0 | 1.0000 -> 1.0000 |
| benef + searched | 3 | 1 (max 252 kg) | 0.9698 -> 0.9493 |

🚨  **57 ROWS PAST A CEILING BECOMES 31, AND THE CLEARING FRACTION GETS WORSE
RATHER THAN BETTER.** Both look backwards and both are the ladder answering.
Fewer rows end up past a ceiling because the fleet search picks a different
programme for many of them; and the rows that do sit past one accept a LOWER
clearing fraction, because a discounted kilogram is worth half and the
programme that maximises the objective is now willing to sell more of them.
**A clearing fraction is a property of the programme the search chose, not a
measure of how hard the ceiling is biting** -- which is
[a diagnostic describes the WINNER](CLAUDE.md#a-diagnostic-describes-the-winner-not-the-search-that-produced-it)
arriving in the column that lesson was first written about.

### Which flag did what

One flag at a time, all on the NEW build so the code is held fixed and only the
config moves, from the all-four-restored baseline that is proven bit-identical
to v1.21.2 above:

| | raw, N = 1 | benef + searched |
|---|---|---|
| v1.21.2 (all four restored) | 25.7233x | 8.9005x |
| cost of capital OFF | 14.8654x (**-42.2%**) | 4.2974x (**-51.7%**) |
| reliability OFF | 17.4914x (**-32.0%**) | 6.4340x (**-27.7%**) |
| learning curve OFF | 25.7233x (**+0.0%**) | 11.9493x (**+34.3%**) |
| surplus sells at half | 25.3377x (-1.5%) | 8.7454x (-1.7%) |
| **v1.22.0 (all four)** | **9.7517x (-62.1%)** | **4.3224x (-51.4%)** |

🚨  **THE COST OF CAPITAL IS THE LARGEST SINGLE TERM IN THE RELEASE, AND IT IS
LARGER THAN THE MODEL CHANGE BY A FACTOR OF THIRTY.** Removing a 10% discount
rate is worth 42-52%; selling the surplus at half price instead of abandoning
it is worth 1.5-1.7%. That ordering is worth internalising before reading any
of this release's headline numbers as a statement about markets: **three
quarters of the move is financial framing, not economics of the ceiling.**

🚨  **THE LEARNING CURVE RUNS THE OTHER WAY, AND IS EXACTLY INERT AT N = 1.**
Turning it off makes the searched cell **34.3% WORSE**, because the curve was a
discount on recurring hardware, and it moves the N = 1 cell by **0.000%**,
which is the claim its own config comment makes -- the cumulative average at
one unit is the first-unit cost by definition. So a flag that is free at N = 1
is the third-largest term once a programme is being searched, and it is the
only one of the four that a reader would guess the sign of wrongly.

⚠️  **The four do not compose, and this is the fifth time this project has
scored the forbidden arithmetic.** Summing the four single-flag deltas on the
default cell gives -46.8% against a measured **-51.4%**, so compounding
understates by about a tenth -- the same direction, and about a quarter of the
magnitude, that the v1.17.x line's compounding error had. **Quote the measured
combination, not a product of the parts.**

### Runtime: NOT measured, and the reason is worth more than the number

ℹ️  **One full-catalog cell has been run since, on 2026-09-16, and it is a wall clock rather than a ratio**; see
[the full-catalog cislunar 2x2 at these defaults](#the-full-catalog-cislunar-2x2-at-these-defaults-2026-09-16).
Nothing below is superseded by it: the objection is to the RATIO, and one cell measured
five days after another in a separate session cannot supply one.

🚨  **A FIRST PASS PUT THE NEW DEFAULTS AT 1.41-2.01x THE RUNTIME OF v1.21.2,
AND THAT TABLE WAS WRONG.** The decomposition above re-ran the identical
all-four-restored raw cell later in the same session and measured **68 s
against the 42 s** the first pass had recorded for it, and the all-four-NEW raw
cell at **32 s against 49 s**. So the same configuration varied by 1.6x on this
host while the "measurement" it fed varied by 1.4x, in the same direction as
the session clock rather than with the build.

**What was actually measured is that this host cannot resolve a 1.4x runtime
ratio on a 155-row cell**, which is the honest finding and the reason no
runtime table is published here. There is a real cost in the release -- the
tiered walk builds and sorts a 2N item list per bound rung, where the wall
walked N items in the cached order -- and it has not been isolated from the
noise. ⚠️  Anyone re-measuring it should interleave the two builds inside ONE
process the way calc v1.17.4 and v1.17.6 did, and should expect the tiered path
to cost nothing at all on rungs where no ceiling binds, which is most of them.

⚠️  `MEASURED_CELL_SECONDS` is **unchanged** and still holds the v1.17.7
full-catalog figures, so every banner deriving a cost ratio from it is quoting
a v1.17.7 measurement of a model two releases old. Re-measuring that is a
26-hour job and nobody has done it for this release. THE SAMPLING RULE covers
ratios as well as wall clocks, and now covers one more thing: **a ratio taken
across a session is a measurement of the session.**

### The cells, for the next release to compare against

`py verify.py baseline --tag 1.22.0`, cislunar, at this release's defaults.
These are `verify.py`'s own canonical hashes -- the whole frame less
`pipeline_version` and `catalog_date`, CRLF-pinned -- and unlike the four in
the acceptance test above they ARE the form every other hash in this file
takes:

| cell | rows | hash |
|---|---|---|
| raw | 155 | `f6c52720c5b886eb` |
| raw + search | 155 | `39172396cc26cbc7` |
| benef | 65 | `a90b6bdd12db585e` |
| benef + search | 65 | `af407f7e2376bb7c` |

⚠️  **They are not comparable with any hash committed before this release**,
and not because a number moved: the frame carries `surplus_payload_kg` now, so
it is a column wider. That is the whole content of the warning above, in the
one place a future reader is most likely to reach for a hash and diff it.

### Invariants

`py verify.py check --tag 1.22.0`, the FULL set rather than the five-minute
loop, **ALL CHECKS PASSED**. Two of the seven are worth naming, because this is
the kind of release that could have broken them:

- **check 2, pre-filter on vs off**: 143/143 identical, hashes matching, all
  four cells. The pruner and the solver are two statements of one algebra, and
  a REVENUE change has no business moving a FEASIBILITY test -- ceilings bound
  what a load may sell, not what the rig digs or the hull carries. This is the
  evidence that they did not.
- **check 3, serial vs 8 workers**: hashes match on both searched cells. It
  matters here because the tiered walk adds per-call MUTABLE state (the tier
  ledger, and the tier list itself), and mutable state is the shape that
  diverges across processes.

⚠️  It was run AFTER the release was committed rather than before, which is the
wrong way round: this file's own instructions say to iterate with
`--skip prune parallel` and run the full set once before committing. Nothing
came of it, and that is luck rather than method.

The rest, which `py verify.py invariants` also reports on its own:

- **mass ledger** `0.000000000 kg` on all four cells
- **never-worse** zero exceptions on all three pairings: `benef <= raw` 155
  pairs, max 1.000000, 10 declined, median **+52.0%**; both search pairings
  max 0.869940, median +39.8%
- **Stage 2 tables** identical, 31 rows recomputed at cislunar; **5/5 payload
  phases resolve to a market**
- **check 7, the one this release could have broken**: a ceiling still only
  ever COSTS you. `cap beat unbounded on 0` rows in both searched cells, max
  ratio **1.000000000**, with the ceiling binding on 31 raw and 13
  beneficiated rows. Selling the surplus at a discount raises revenue toward
  the unbounded case and must never pass it, and it does not.
- **the knapsack** proved separately, off the pipeline: 150 random instances
  against an integer DP that enumerates every split of every phase between its
  two tiers and shares no code with the walk; 400 proving `caps=None` and 400
  proving `surplus_price_fraction = 0.0` each reproduce an independently
  written greedy bit for bit; 300 proving the value is monotone in the fraction
  and equals the UNCAPPED load at 1.0
- **the out-of-range guard**: `surplus_price_fraction` above 1.0 would make the
  ceiling PAY rather than cost, because the discounted tier would sort ahead of
  the full-price one and draw the allowance. Measured at 1.5: a load worth
  900,000 uncapped priced at 945,000 capped. Refused at run level and clamped
  in the resolver

🚨  **AND CHECK 7's NEW EXCLUSIVITY TEST FAILED ON ITS FIRST RUN, ON 2 OF 158
ROWS, AND THE MODEL WAS RIGHT.** The claim is that `unsold_payload_kg` and
`surplus_payload_kg` are never both positive. Measured, those two rows carry
**3.638e-12 kg of "unsold" against a 24-tonne payload: 1.5e-16 relative, one
ULP.** On the beneficiated path `unsold` is a DIFFERENCE OF TWO SUMS -- the
uncapped load's mass less the capped load's -- and with the surplus tier on
those two are mathematically equal, because the allowance splits one phase's
take across two tiers and `(x - a) + a` is not always `x`.

✅  **Fixed in the CHECK, with a milligram floor, not in the cascade.** That is
the precedent check 7 already set for its clearing bound, which tolerates
`1.0000000000000002` for the same reason; **a comparator stricter than the
artefact it compares reports failures that do not exist**, and an epsilon
inside the cost cascade to silence a checker is not something this project
does. The floor is six orders of magnitude above the residue and far below any
mass the model can mean.

### The full-catalog cislunar 2x2 at these defaults (2026-09-16)

The subsection above says no runtime table is published for this release and
that `MEASURED_CELL_SECONDS` still holds v1.17.7 figures. This is the cell that
closes the first half of that gap and deliberately does not close the second.

**All four cislunar cells, every row of the 1,555,667-row catalog, 12 workers,
calc `1.22.0` at its own defaults, 18,586 s in total.** Stages 1-3 were not
run; the live Stage 2 catalog was verified byte-identical to
`campaign/stage2/mineral_value_catalog.cislunar.csv` before launch, so the
2026-09-09 price epoch is the one the 28-cell campaign used.

⚠️  **The four are ONE construction, deliberately.** Every cell was run as
`--preset full` with the two axes laid on top, because `resolve()` applies the
preset first and explicit flags after it. `campaign/run_cell.py` would have used
the default preset plus overrides, which leaves `jpl_limit` differing between
cells; Stage 4 never reads it, so it cannot move a number, but it would make
the 2x2 four constructions rather than one, and comparability across the square
is the whole reason for running it.

| cell | best | evaluable | wall |
|---|---|---|---|
| raw, N = 1 | **5.3483x** | 650,921 | 735 s |
| raw, searched | **3.9218x** | 650,921 | 1,439 s |
| beneficiated, N = 1 | **4.5298x** | 660,253 | 4,737 s |
| **beneficiated + searched** (default) | **3.1822x** | 660,253 | 11,676 s |

The default cell is the one measured first and described in detail below; the
other three landed on the same day.

| | v1.21.2 (the campaign) | **v1.22.0 (this run)** |
|---|---|---|
| cost / revenue | 6.6622x | **3.1822x** |
| winner | 2021 CX5 (D) | 2021 CX5 (D) |
| vehicle / propellant | New Glenn / argon | New Glenn / **iodine** |
| payload | 34,573 kg | **62,283 kg** |
| programme | N = 35 | **N = 18**, 6 ships x 3 campaigns |
| evaluable rows | 660,253 | **660,253** |
| wall clock | 9,878 s | **11,676 s** |

⚠️  **The archive is `cislunar__benef__search-on__calc-1.22.0.csv.gz`,
NOT the campaign's own name.** `campaign/run_cell.py` would have written
`cislunar__benef__search-on.csv.gz`, which is the v1.21.2 artifact that
`population.py`, `analyse.py` and `worked_calculation.py` all read, is 377 MB,
is gitignored and has no backup. A calc-suffixed name is invisible to both
readers because each builds an exact filename rather than globbing, which is
what makes a second measurement of one cell safe to keep on disk at all.

#### The evaluable set did not move, and that is the invariant

**660,253 rows in both builds**, identical. Which rows are evaluable falls out
of the mass cascade, and no price, flag or N enters it. This release put a
second price tier inside the payload knapsack, so the one thing it could have
broken is the `caps=None` guard that keeps ceilings out of the SIZING path; an
evaluable count that moved by a single row would have been that. It did not.

#### The capped-sample decomposition scored, and it was right

The release note above puts the four flags at **2.1x on the default cell**,
measured on a capped cislunar sample. On the full catalog the winner moves
6.6622x to 3.1822x, a factor of **2.094x**.

✅  **That is a data point ON THE SAMPLING RULE rather than against it, and
the distinction is the one the rule already draws.** What has failed four times
is extrapolating a stride sample's WALL CLOCK or cost RATIO to a full catalog.
What held here is a sample's estimate of a MODEL ratio over identical rows,
which is the narrow kind, the same kind that put calc v1.15.0's beneficiated
cell inside its projected band. **Do not read it as permission to project a
runtime from a sample.**

#### 251 rows got worse, and they are all at the ladder's top rung

The four flips are not uniformly an improvement. Paired row by row against the
archived v1.21.2 cell, **660,002 rows improve, 251 (0.04%) regress**, worst
**1.2606x**, and the population median improvement is **57.54%** on the
committed `median(1 - r)` convention.

🚨  **Every one of the 251 sits at N = 320 in BOTH builds, and NONE of them
was ceiling-bound**, against 30.27% of the population in v1.21.2. N = 320 is
`max_fleet_ships` 64 times a five-trip rig, i.e. the ladder's top rung. So the
gain that carries this release, selling the surplus, is worth exactly zero to
them, while withdrawing the learning curve takes away the largest Wright's-law
discount on the ladder. They are the rows where one flip bites and the other
three cannot.

⚠️  It costs nothing: their cost/revenue ratios run **678x to 1,418x**,
three orders of magnitude off the winner, which is the same population this
file already describes as sitting at the ladder's top because no finite market
bounds them. **It is still worth knowing that a release argued as a 2x
improvement makes a named set of rows worse**, and that the set is identifiable
from one column.

#### What moved structurally

| | v1.21.2 | v1.22.0 |
|---|---|---|
| rows a ceiling binds | 30.27% | **6.53%** |
| minimum clearing fraction | 0.679429 | 0.839715 |
| `W < trips` | 22.14% | **3.51%** |
| `W > trips` | 0 | 0 |
| fleet median | 6 | 4 |
| N median | 30 | 20 |
| programme span median | 13.82 yr | 15.18 yr |
| concentration ratio median | 7.4074 | 7.4074 |

🚨  **PROGRAMMES TAKE THE RIG'S LAST TRIPS BACK.** calc v1.21.0's signature
population finding was that programmes decline the rig's final campaigns once a
hard wall refuses the sale, and at this cell it ran 22.14%. Selling that
campaign's load at half price is enough to make it worth flying again:
**3.51%**. The mechanism is not new and the direction is the whole point: a
wall that refuses a sale and a wall that discounts it are different walls.

⚠️  **The propellant and vehicle shares move with it, and one reverses a
documented lead.** Xenon goes 38.99% to **55.30%** of rows and iodine 36.24% to
**20.70%**, so iodine's near-lead at cislunar is not merely lost but inverted,
by 34.6 points. New Glenn falls 32.53% to **16.05%** and Falcon Heavy rises
40.02% to **54.08%**. Both follow the same cause: iodine's advantage and New
Glenn's are effects of programme SCALE and of a ceiling that punishes volume,
and N fell from 30 to 20 while the ceiling stopped refusing anything.

#### The exclusivity test, on 660,253 rows instead of 158

The invariants section above records check 7's new exclusivity test failing on
**2 of 158 rows** at 3.638e-12 kg, and being fixed with a milligram floor. The
full population is the stronger statement of the same thing:

| at check 7's threshold, 660,253 rows | |
|---|---|
| `unsold` and `surplus` both above 1e-6 kg | **0** |
| `unsold` above 1e-6 kg anywhere | **0** |
| `saturation_multiplier` not equal to 1.0 | **0** |
| clearing outside [0, 1] | **0** |
| either column negative, or over the payload | **0** |

⚠️  **A bare positive test instead of the floor reports 1,769
violations**, at a maximum of **1.455e-11 kg against payloads in the tens of
tonnes, 1.8e-16 relative.** That is one ULP and it is the same residue, three
orders of magnitude more often because there are four thousand times as many
rows. The floor is not a convenience; without it this cell reports a
four-figure failure count for a model that is exactly right.

#### The winner is bound by a ceiling and sells no surplus at all

`market_clearing_fraction` 0.983516, `surplus_payload_kg` **0.0**,
`unsold_payload_kg` 0.0. Those look inconsistent and are not, and the generated
document derives the reason: gross value **$582.66M unbounded against $573.05M
after the ceilings**, with 0.0 kg discounted.

The tiered walk records surplus only when a phase's DISCOUNTED tier is actually
drawn. A ceiling can clip the dearest phase's full-price tier, the hold then
refills with cheaper material at full price, and the walk never reaches the
discounted tier before the hold is full. Value falls below 1.0; no mass is sold
at a discount. **10,757 rows are bound with zero surplus, 25.0% of all bound
rows**, so this is a quarter of the bound population rather than a quirk of one
body. Across the cell the discounted tier does fire: **32,349 rows (4.90%)
carry surplus, 23.0 kt of it.**

✅  **This is the reason the two columns exist rather than one.** A single
"mass over the ceiling" column would read 0.0 here and be taken to mean no
ceiling bound the winner, which is false.

#### Runtime: a number, and not a ratio

**11,676.4 s (3.24 h)**, 12 workers, against the 9,878 s this cell measured on
v1.21.2 on 2026-09-11.

🚨  **DO NOT QUOTE 1.18x.** The two runs are five days apart in separate
sessions, and the subsection above is this release's own finding that **a ratio
taken across a session is a measurement of the session**: the same host moved
1.6x on an identical configuration while the release's first runtime table was
reading 1.4x off it. The wall clock is a fact about this run. The ratio is not
a measurement, and isolating the tiered walk's real cost still needs the
interleaved construction calc v1.17.4 and v1.17.6 used.

⚠️  `MEASURED_CELL_SECONDS` was therefore **left unchanged by the run that
measured this cell**, and deliberately: it holds four cells measured as a set,
and replacing one of them with a figure from a different release would make
the dict internally incomparable, which is exactly what it was rebuilt to
prevent.

✅  **THAT OBJECTION DISSOLVED THE MOMENT THE OTHER THREE LANDED, AND THE DICT
MOVED ON 2026-09-16**; see
[the runtime constant follows the release now](#the-runtime-constant-follows-the-release-now-2026-09-16).
The reason to wait was never that one release is better than another, it was
that a dict half at one release and half at the next is a set nobody can take
a ratio inside. Four cells at one release is a set again.

#### The whole square against v1.21.2

Every cell reproduces its campaign counterpart's evaluable count exactly, and
no cell's winner is worse:

| cell | v1.21.2 | v1.22.0 | factor | median improvement | rows worse |
|---|---|---|---|---|---|
| raw, N = 1 | 15.3937x | 5.3483x | **2.878x** | +61.24% | **0** |
| raw, searched | 9.5435x | 3.9218x | **2.433x** | +54.61% | 168 |
| benef, N = 1 | 14.1071x | 4.5298x | **3.114x** | +66.38% | **0** |
| benef, searched | 6.6622x | 3.1822x | **2.094x** | +57.54% | 251 |

🚨  **THE REGRESSIONS ARE CONFINED TO THE SEARCHED CELLS, AND THAT PROVES
THE MECHANISM RATHER THAN MERELY AGREEING WITH IT.** The single-cell note above
argued from the 251 rows' position on the ladder that the cause is the learning
curve's withdrawal. The learning curve is **exactly inert at N = 1**, so if
that reading is right the N = 1 cells must carry ZERO regressions. They do:
**0 of 650,921 and 0 of 660,253**, against 168 and 251 in the searched cells.
A hypothesis about a programme-scale term, checked on the cells where no
programme exists, is a much stronger test than the ladder position it was
formed from.

⚠️  **The capped-sample projection was good on the default cell and
noticeably worse on raw ore.** The release note projects **2.6x on raw and 2.1x
on the default cell**. Measured: **2.878x** and **2.094x**, so the default
cell lands within 0.3% and the raw figure is **10.7% low**. The raw number is
the one a reader reaches for when rescaling an older raw cell, which is the
worse of the two to be wrong about.

✅  **Both N = 1 cells share a maximum r of 0.5863**, i.e. even the
least-improved row of either improves by 41.4%, and the bound is identical
across ore states. At N = 1 three of the four flips are pure removals of a
charge and the fourth is inert, so the floor on how little they can help is a
property of the cost cascade rather than of the ore.

#### Invariants on the full population

`campaign/analyse.py`'s own `never_worse`, `mass_ledger` and
`programme_invariants`, called on these four frames rather than restated:

| pairing | pairs | max r | worse | declined | median |
|---|---|---|---|---|---|
| benef <= raw, search OFF | 650,921 | 1.000000 | **0** | 56,707 | +51.6% |
| benef <= raw, search ON | 650,921 | 1.000000 | **0** | 80,528 | +47.7% |
| search ON <= OFF, raw | 650,921 | 1.000000 | **0** | 4 | +39.3% |
| search ON <= OFF, benef | 660,253 | 0.997496 | **0** | 0 | +39.0% |

🚨  **THIS IS THE CHECK THIS RELEASE MOST NEEDED AND HAD ONLY EVER HAD ON
155 ROWS.** Selling the surplus at a discount RAISES revenue toward the
unbounded case, and the whole argument of check 7 is that it must never pass
it. Four pairings, **zero exceptions on roughly 650,000 paired rows each**, is
the population-scale statement of that, and it is what the 2x2 buys beyond four
more headline numbers.

- **mass ledger**: `max |error| 0.000000000 kg` on all four cells
- **programme structure**: `N = F x W` on every row of both searched cells, and
  `W > trips` never
- **market columns** at check 7's thresholds: clean on all four cells, and
  `unsold_payload_kg` above a milligram is **0 rows in the whole square**

#### A ceiling is nearly inert without the search

| cell | rows a ceiling binds | rows selling surplus |
|---|---|---|
| raw, N = 1 | 0.32% | 2,110 |
| raw, searched | **15.68%** | 102,079 |
| benef, N = 1 | 0.02% | 114 |
| benef, searched | 6.53% | 32,349 |

✅  **A capacity ceiling is an ANNUAL allowance, so a single delivery barely
reaches one**: 0.02% of beneficiated rows at N = 1 against 6.53% searched, and
0.32% against 15.68% on raw ore. The market model is very nearly inert on a
single-mission run, which is worth knowing before attributing anything in an
N = 1 cell to it.

⚠️  **And beneficiation RELIEVES the ceiling on the searched cells**,
15.68% to 6.53%, because concentrating is exactly the way to sell the same
value in fewer kilograms. That is the same direction the 28-cell campaign
reports at every destination except `cislunar`, which under a hard wall was the
exception; under a discounted surplus it is not.

#### Programme structure, and the rig's last trips

| | v1.21.2 | v1.22.0 |
|---|---|---|
| `W < trips`, raw searched | 20.86% | **8.131%** |
| `W < trips`, benef searched | 22.14% | **3.509%** |
| fleet median, raw / benef | 3 / 6 | **2 / 4** |
| N median, raw / benef | 12 / 30 | **10 / 20** |

🚨  **THE RIG'S LAST TRIPS COME BACK ON BOTH SEARCHED CELLS, AND THE THREE
POINTS NOW MAKE A SEQUENCE.** On the 2026-08 `elasticity` campaign `W < trips`
ran **0.319%** at cislunar raw searched; calc v1.21.0's hard wall took it to
**20.86%**; selling that campaign's load at half price brings it back to
**8.131%**. A demand curve always permitted the sale at a worse price, a wall
refused it outright, and a discount is between the two -- so the diagnostic
lands between the two, which is the behaviour a reader should expect and is
better evidence than either endpoint alone.

#### What this does NOT settle

⚠️  **One destination of seven.** The other six are untouched, so the
28-cell matrix stands as the only seven-destination measurement and every claim
it carries is still a v1.21.2 claim. The two destinations whose ORDERING
against cislunar is close, `mars_orbit` at 11% on the default cell, cannot be
re-ranked from this square.

⚠️  **`MEASURED_CELL_SECONDS` was still unchanged here, and the argument for
leaving it was about the DICT rather than about the numbers.** A complete
cislunar 2x2 at v1.22.0 looks like exactly what that dict holds. But it was the
cislunar ROW of `MEASURED_DEST_SECONDS`, whose other six rows are v1.21.2, and
`dest_cost_span()` computes a span ACROSS destinations; a single row from
another release would make that span a measurement of a release difference
wearing a destination's name. Re-measure all seven or none.

🚨  **THAT ARGUMENT WAS RIGHT AND ITS PREMISE WAS OPTIONAL, WHICH IS THE PART
WORTH KEEPING.** The two dicts were one object, so every use inherited the
constraint of the strictest use. Splitting them satisfies both readers at once
and neither has to compromise: see
[the runtime constant follows the release now](#the-runtime-constant-follows-the-release-now-2026-09-16).
**When a shared definition forces a choice between two correct requirements,
check whether it is one measurement or two before conceding to either.**

✅  **The worked calculation was regenerated against this row** and
reproduces it: **88 derived quantities, 87 bit-exact, 1 within 1e-12, 0
differing**, worst 6.795e-16 relative on `diameter_km`. It reads all four of
this release's flags off the row rather than the live config, which is the
reader-side fix this release's own notes describe, exercised here for the first
time on a full-catalog winner.

### The population at these defaults, re-derived (2026-09-16)

The 2x2 above reported the winner, the invariants and a handful of structural
moves. This is the rest: every per-cell table the docs carry, re-derived at
cislunar from the four archived cells by `campaign/population.py --tag
calc-1.22.0`. **One read, no re-run** -- which is the lesson CLAUDE.md already
teaches about re-reading a cell, taken on the day rather than three days later.

⚠️  **It reaches ONE destination of seven.** Every table in CLAUDE.md that
these rows appear in stays a `1.21.2` seven-destination measurement, and a
cislunar column measured at a later release is not a scale factor for the six
beside it.

#### What the tooling needed, and what it deliberately still refuses

`population.py` and `analyse.py` both compose an exact cell filename, which is
what makes a calc-suffixed archive invisible to them and therefore safe to keep
on disk. Reading one needed an option, and the option is a `--tag` SUFFIX
rather than a glob, so the property survives: a tag still builds one name per
cell, and a tag with no archive behind it yields nothing rather than falling
back to the campaign's cell and answering a question nobody asked.

#### The programme calendar charge is inert on 650,000 rows

`calendar_mult_median` **1.3190 to 1.0000** on the raw searched cell and
**1.4026 to 1.0000** on the beneficiated one.

✅  **That is a documented PREDICTION confirmed on a full population rather
than a new finding.** `apply_wacc_compounding` is off since v1.22.0, and
`model_programme_calendar` is left True with a note saying its multipliers are
exactly 1.0 at a zero rate, so the term still says the right thing the moment
there is a rate. It had never been checked on more than the winner. It is now,
on every searched row of both cells, and **the median is exactly 1.0**.

#### The calendar bound takes the majority of beneficiated rigs

Which bound retires the rig, cycle / calendar, cislunar:

| cell | v1.21.2 | v1.22.0 |
|---|---|---|
| raw, N = 1 | 95.97 / 4.03 | 95.69 / 4.31 |
| raw, searched | 97.51 / 2.49 | 98.17 / 1.83 |
| **beneficiated, N = 1** | 57.51 / 42.49 | **47.84 / 52.16** |
| beneficiated, searched | 75.98 / 24.02 | **58.45 / 41.55** |

🚨  **THE BENEFICIATED N = 1 CELL CROSSES 50%**, so at these defaults the
CALENDAR retires the majority of cislunar rigs on that cell where the cycle
bound did before. CLAUDE.md records "the cycle bound retires almost every rig"
as already wrong three ways; this is a fourth, at the project's best-case
destination, and it takes no change to the rig model -- the cadence lengthens
(2.100 to **2.617 yr** beneficiated at N = 1) and a longer stay is what spends
a service life.

#### The beneficiated inversion gets stronger

What sets the pace, window / dig: beneficiated N = 1 goes **34.34 / 65.66** to
**26.16 / 73.84**, so the dig sets the pace on three rows in four. Raw is
unmoved at 91.70 / 8.30. The inversion CLAUDE.md records as universal across
all seven destinations is not merely intact here, it is wider.

#### Programmes take the rig's last trips back, on the raw cell too

| | v1.21.2 | v1.22.0 |
|---|---|---|
| `W < trips`, raw searched | 20.86% | **8.13%** |
| `W < trips`, beneficiated searched | 22.14% | **3.51%** |
| fleet median, raw / benef searched | 3 / 6 | **2 / 4** |
| N median, raw / benef searched | 12 / 30 | **10 / 20** |
| programme span median, benef searched | 13.82 yr | **15.18 yr** |

The beneficiated figure was already in the section above; the raw one is new
and moves the same way for the same reason. **Smaller programmes, run longer.**

#### Every ceiling diagnostic loosens, and one column retires by construction

| | v1.21.2 | v1.22.0 |
|---|---|---|
| rows a ceiling binds, raw searched | 30.07% | **15.68%** |
| rows a ceiling binds, benef searched | 30.27% | **6.53%** |
| minimum clearing, raw searched | 0.578190 | **0.772791** |
| minimum clearing, benef searched | 0.679429 | **0.839715** |
| unsold rows, all four cells | 1,458 / 195,723 / 273 / 64,759 | **0 / 0 / 0 / 0** |

⚠️  **Those four zeros are the honest count and a bare `> 0` test reports
1,891 on the beneficiated searched cell.** See below; the column is residue,
not mass.

#### FEEP climbs a long way and still does not win

Best `replicated`-scaling mission per cell, rank and margin against the winner:

| cell | v1.21.2 | v1.22.0 |
|---|---|---|
| raw, N = 1 | 54 (1.43x) | **11 (1.36x)** |
| raw, searched | 365 (1.95x) | **18 (1.40x)** |
| beneficiated, N = 1 | 147 (1.52x) | **33 (1.37x)** |
| beneficiated, searched | 2,202 (1.92x) | **321 (1.53x)** |

**Zero wins at cislunar on any setting**, and every survivor is still FEEP, so
the standing claim holds. What moves is how close it comes: **2014 UV210 takes
three of the four cells** where v1.21.2 had four different bodies, and the
worst margin narrows from 1.92x to 1.53x.

🚨  **AND ONE MAGNITUDE IN CLAUDE.md IS RELEASE-SPECIFIC.** It records that the
programme search pushes FEEP down the ranking "by a factor of 7 at `cislunar`".
At these defaults it is 11 to 18, a factor of **1.6**. The DIRECTION survives;
the factor was a `1.21.2` number and reads as a property of the model.

⚠️  **The survivor COUNT moves both ways and still proves nothing**: 93 to 104
raw at N = 1, and 76 to **10** raw searched. CLAUDE.md's rule that survival was
never the test is the reason this is a footnote rather than a finding.

#### Far fewer bodies decline to concentrate

`campaign/analyse.py --tag=calc-1.22.0 cislunar` runs the committed invariants
over the same four cells, and every one holds: **never-worse on all four
pairings with zero exceptions**, the mass ledger at `max |error| 0.000000000
kg` on 2.6 million rows, and `N = F x W` on every row of both searched cells
with `W > trips` never. Its `W < trips` figures are **8.131% and 3.509%**,
which reproduce `population.py`'s to three decimals from a separate read --
two tools over one population, which is the overlap this repo builds checks
for.

🚨  **WHAT IS NEW IS THE DECLINE COUNT, AND IT NEARLY HALVES.** Bodies refusing
to concentrate, i.e. falling back on the `beneficiate=False` baseline:

| | v1.21.2 | v1.22.0 |
|---|---|---|
| search OFF | 102,765 (15.79%) | **56,707 (8.71%)** |
| search ON | 102,427 (15.74%) | **80,528 (12.37%)** |

⚠️  **CLAUDE.md records the decline counts as the thing the market model barely
touches** -- "22,972 against 22,781" at `lunar_surface` across the whole
`elasticity` to `capacity_cap` change. Four flags at once move it by a factor
of nearly two at cislunar, so that stability was a property of the market term
rather than of the population.

⚠️  **It is also the one place the two axes disagree.** At v1.21.2 the two
settings were within 0.05 pp of each other; here they are 8.71% against
12.37%, so the programme search now makes a body MORE likely to decline to
concentrate. That is consistent with the rest of this section -- the chosen
programmes are smaller and the ceilings bind on a quarter as many rows -- but
it is a population claim nobody has checked at another destination.

#### Two invariants reproduce exactly

✅  **Aerocapture is 0.00% on all four cells.** Cislunar is airless, nobody
asserts it, and the search declines it.

✅  **ISRU still tracks hydrolox, and more tightly than before**: the gap is
**+0.000461 / +0.000461 / -0.000151 / +0.000606 pp** across the four cells,
against 0.0014 to 0.0068 pp at v1.21.2. The residual still runs both ways.

#### The unsold column was counted with a bare positive test

🚨  **`campaign/population.py` COUNTED `unsold_payload_kg > 0` AND THE
BENEFICIATED PATH LEAVES FLOAT RESIDUE THERE.** calc forms that column as
`sum(payload_mix.values())` minus the knapsack's `loaded_kg`, where `loaded_kg`
is an accumulated `payload_kg - remaining`: two associations of one quantity,
so a hold the ceilings did not shrink comes out as **1.455e-11 kg** rather than
zero.

Six committed figures in CLAUDE.md's ceiling table were high as a result, and
`verify.py` check 7 had already met this residue and taken a milligram floor
for it -- so this is the repo's standing failure of fixing one half of a defect
class:

| beneficiated searched cell | was | is |
|---|---|---|
| `mars_surface` | 6,977 | **6,136** (-12.1%) |
| `leo` | 34,996 | **33,642** (-3.9%) |
| `mars_orbit` | 72,003 | **69,432** (-3.6%) |
| `geo` | 67,293 | **66,605** (-1.0%) |
| `lunar_surface` | 25,803 | **25,546** (-1.0%) |
| `cislunar` | 65,373 | **64,759** (-0.9%) |

✅  **The raw column was always right**, because the raw path accumulates
`unsold` directly rather than subtracting two sums. Re-deriving all 28 cells
with the floor moved `unsold_rows` and **nothing else**: 9 values across 28
JSON files, every other statistic bit-identical, which is what says the fix is
confined to what it should touch.

#### The same bare test was a real defect in the document generator

🚨  **`campaign/worked_calculation.py` INFERRED "THIS RUN HARD-WALLED" FROM
`unsold_payload_kg > 0.0`**, which is the one line deciding whether a whole
derivation prices the surplus as abandoned or sold at a discount.

The tempting reading is that residue is harmless because a row with residue
sold no surplus. **Measured, it is the opposite: 1,769 of the 1,891 residue
rows carry a genuine surplus above a milligram**, and all 1,891 are
ceiling-bound. So those rows were read exactly backwards, and this is the
flipped-default failure that file already documents arriving from the other
side.

⚠️  **The check at the end catches it, which is an argument for the compared
column set rather than for leaving it.** Proved on `2021 VW5`, one of the
1,769: before the fix the derivation reports that it disagrees with the model;
after it, **88 quantities, 86 bit-exact, 2 within 1e-12, 0 DIFFER**.

✅  **And the residue column itself is bit-exact now, by matching the model's
association rather than by tolerating a difference.** The derivation subtracted
two quantities it had both computed as `payload - remaining`, which cancels to
exactly 0.0; calc subtracts a `sum()` from an accumulator. Taking the sum on
the free side is the `y * 365.25 * 24.0` lesson again: one rounding is not more
accurate than two, it is a different number, and the one that matters is the
model's. ⚠️  Note what a relative comparator does with the difference -- 0.0
against 1.455e-11 is a relative error of **1.0**, a 100% disagreement over one
ULP -- which is why this had to be fixed at the arithmetic rather than with a
tolerance.

### The runtime constant follows the release now (2026-09-16)

The section above measured all four cislunar cells at v1.22.0 and deliberately
left `MEASURED_CELL_SECONDS` alone, for a reason that was about the dict rather
than the numbers: it WAS the cislunar row of `MEASURED_DEST_SECONDS`, so moving
it would have put one release's row inside a seven-row table that
`dest_cost_span()` takes ratios across. This is the change that removes the
premise instead of conceding to it.

🚨  **THE BANNER WAS TELLING USERS THAT CONCENTRATING COSTS 3.4x WHILE THE
RELEASE THEY WERE RUNNING MEASURES 8.1x.** That is the exact failure the whole
constant exists to prevent, and it had been reintroduced not by typing a number
but by deriving one from the wrong measurement:

| what the banner prints | calc 1.21.2 (what it said) | calc 1.22.0 (measured) |
|---|---|---|
| beneficiation, with the search on | 3.42x | **8.11x** |
| programme search, on raw ore | 3.05x | **1.96x** |
| both on, against the raw N = 1 cell | 10.43x | **15.89x** |

⚠️  **The cross-release reading of that table is not one measurement, and
neither column is a clean ratio either** -- the campaign cells span 2026-09-11/13
and these 2026-09-16, both across sessions, which is the thing this release's
own notes say cannot be resolved on this host. What is claimed is narrower: the
right column is the best available estimate of the cell somebody is about to
run, measured at the release that will run it.

#### What was split, and what each half is now for

| | holds | is the authority for |
|---|---|---|
| `MEASURED_DEST_SECONDS` | the 2026-09 campaign, seven destinations, calc 1.21.2 | the SPAN across destinations, and README's 28-cell table |
| `MEASURED_CELL_SECONDS` | the four cislunar cells at `MEASURED_CELL_CALC` | the LEVEL of a cell somebody is about to run: both banners, `--help`, the dashboard estimate |

**They are two measurements of one cell, not two copies of one measurement**,
so each keeps its own authority and neither is edited to agree with the other.
`dest_cost_span()` is untouched and still reads the campaign table alone, so
no ratio in this project crosses a release; `expected_cell_seconds()` is the
new accessor for the other question, best-available per destination, and its
docstring refuses to be used for a ratio.

✅  **`measured_cell_provenance()` makes the staleness say so.** When
`MEASURED_CELL_CALC` is behind the running `pipeline_version` every banner and
both `--help` strings grow " (measured at calc X)", and the string is empty on
the common path. This file's rule everywhere else is that a wall clock is only
ever true of the release it names; a banner quoting one without naming a
release was relying on somebody having re-measured.

#### The half of the shape change that does not need a clock

The beneficiated searched cell got **dearer** while three of the four got
cheaper, and a cross-session wall clock cannot establish that on its own.
`programme_options_priced` can: it is a deterministic output, so it compares
across releases the way a wall clock does not.

| searched cell | v1.21.2 | v1.22.0 | |
|---|---|---|---|
| raw, options priced | 26,854,749 | 26,757,376 | -0.4% |
| **beneficiated, options priced** | 27,992,344 | **25,927,278** | **-7.4%** |

Row counts are identical in both (650,921 and 660,253) and so is the median
concentration ratio (1.0000 and 7.4074), so this is the same population doing
the same sweep. **The beneficiated searched cell prices 7.4% FEWER programme
options and still takes longer**, which puts the cost in the price of a rung
rather than in the number of them, and the second market tier v1.22.0 put
inside the payload knapsack is walked per rung.

⚠️  **This is not a runtime table and must not be quoted as one.** It is an
argument about WHERE a cost is, made from counts, because the clock cannot make
it. Isolating the tiered walk's cost still needs the interleaved construction
calc v1.17.4 and v1.17.6 used.

#### The check that replaced the identity

Check 9 used to assert that `MEASURED_CELL_SECONDS` was the cislunar row of
`MEASURED_DEST_SECONDS`. Unpicking the derivation retires that assertion, and
retiring a check to make a change pass is how a guard is lost, so it is
replaced by a stronger one: the four seconds are compared against
`campaign/logs/*.json`, the per-cell status and queue-progress files the run
itself wrote, which are committed and carry `wall_s` and `calc_version`.

**The constant is pinned to the measurement now rather than to a second copy of
one**, which is a thing the identity could never do: two typed dicts agreeing
with each other says nothing about whether either was measured.

⚠️  **A missing log is a FAILURE, not a skip**, because this repo has now found
six checks that could not run and said they passed. Both failure modes were
proved by causing them: a wall clock edited by 676 s names the cell and the
log, and a `MEASURED_CELL_CALC` bumped to a release with no cells behind it
reports that nobody can say where the four numbers came from.

⚠️  **The launcher hours moved with it, cislunar only.** `run.bat`, `run.sh`
and README quote "N h at &lt;destination&gt;" and are typed because shell cannot
import `master`; cislunar goes **2.7 h to 3.2 h** and the other six are
unchanged, because a menu should quote the newest figure each destination has.
Check 9 pins all of them through `expected_cell_seconds`, which is a LEVEL per
row and never a ratio between rows.

#### Two stale figures the same pass found

🚨  **README said `MEASURED_CELL_SECONDS` "is unchanged and still holds the
v1.17.7 set", twice, and it was wrong when it was written.** The dict held the
2026-09 campaign row, one release back, not the one before that. Both copies
went in with the 2x2 and neither was ever true.

⚠️  **`use_beneficiation`'s config comment quoted 4.67x, which is the DASHBOARD
HELP TEXT for that dial**, under a sentence saying both figures come from the
dict. They did not: 4.67x is calc 1.17.7 and the dict derived 3.42x. So the
dashboard told a reader 4.67x, the banner beside it said 3.42x, and the release
running measures 8.11x. Both are de-typed now, and `run_pipeline.py`'s ore
formatter lost a third copy in the same pass. **Deriving one figure in a file
does not make the file derive that figure** -- this project's own lesson, found
again in a file whose comment says numbers must never be typed in it.

## calc v1.21.2

**One market, two allowances. The composition residual and the `silicates`
phase each drew the full silicates ceiling, on 100% of bodies.**

### What v1.21.1 fixed, and the half it left open

v1.21.1 found that `asteroid_phase_table`'s composition residual was priced at
the `silicates` quote and bounded by nothing, and mapped it onto the
`silicates` market with `_PHASE_MARKET_ALIAS`. That was right, and the comment
it shipped with says exactly what was intended:

> Priced as silicates, bounded as silicates, in one place.

It was bounded as silicates in **two** places. Every consumer asked
`phase_market_kg` per PHASE, so `silicates` got the full allowance and
`other (bulk silicate)` got the full allowance again. The alias made the two
share a ceiling in the sense of reading the same number off the table, and not
at all in the sense of spending it once.

### Why it is not a corner

| | |
|---|---|
| bodies carrying BOTH phases | **3,999 of 4,000** sampled (100.0%) |
| the two as a share of the load | **median 0.840**, min 0.440, max 0.940 |
| the cislunar `silicates` ceiling | **15,000 kg/yr**, among the tightest in the table |

So the doubled allowance applied to the dominant mass fraction of essentially
every asteroid, against one of the ceilings most likely to bind. The
demonstration, on a synthetic load at that ceiling over a 3-year window:

```
BENEFICIATED knapsack, silicates ceiling 15,000 kg/yr, window 3 yr
  before   mix {water: 40,500, silicates: 45,000, other (bulk silicate): 34,500}
  after    mix {water: 40,500, silicates: 45,000}
```

79,500 kg of silicate-family material sold into a 45,000 kg market.

### What changed

`phase_market_key()` is new and is the market IDENTITY of a phase, where
`phase_market_kg()` is its size. Both resolve the alias the same way -- a
phase's own Stage 2 row wins, the alias is the fallback -- so the two cannot
disagree about which market a phase is in. Every consumer pools on the key:

| consumer | before | after |
|---|---|---|
| `_capped_sale_value` (raw) | allowance per phase | one allowance per market, drawn down |
| the knapsack `caps` (beneficiated) | keyed by phase | keyed by market, consumed in place |
| the `binds` fast path | tested per phase | tested on the pooled quantity |
| `elasticity` | curve asked per phase | curve asked on the market's total throughput |

⚠️  **`elasticity` moves too, and it has to.** Asking the curve per phase asked
it twice about half the quantity each time, and the curve is convex, so two
half-loads take a smaller haircut than one whole one. Two phases selling into
one market depress it together.

⚠️  **`sale_terms` is a 4-tuple now**, `(kg, price, ceiling, market_key)`. It
has four consumers and all four were updated; the type annotation moved with
it so the next reader is told.

### What did NOT change, and it is the load-bearing one

✅  **`optimal_payload_mix(caps=None)` is bit-identical**, and so is the
`want_phase` short circuit. Both matter more than the headline: `_cargo_water_kg`
calls this from inside the fixed-point power solve, so if `caps=None` ever
stopped being the old walk, **every mass cascade in the model would move**.
Verified rather than argued -- **16,000 randomised comparisons over five
phases, zero differences**, on raw IEEE bit patterns rather than on `==`.

Every new line sits inside `if caps is not None:`. **Stage 2 is not touched and
not re-run**; no `annual_market_kg`, no schema change, no new reference row.

### What it moved

Every cell that moves gets **worse**, which is the only direction a removed
revenue overstatement can go.

| cell | v1.21.1 | v1.21.2 | | rows that moved |
|---|---|---|---|---|
| raw | 24.6804x | **25.7233x** | +4.23% | **1 of 155** |
| raw + search | 18.5707x | **19.7213x** | +6.20% | 94 of 155 |
| beneficiated | 20.5353x | 20.5353x | **hash unchanged** | 0 of 65 |
| beneficiated + search | 8.6861x | **8.9005x** | +2.47% | 9 of 65 |

New baseline: `eac188f956a9fa36` / `99bf5e6e3fd3a012` / `109ce36a07ac6975` /
`c681bc9f32684ea0`. The beneficiated hash is v1.21.1's, unchanged.

✅  **The beneficiated N = 1 cell being bit-identical is the corroboration, not
a let-off.** The knapsack walks in descending price order and the silicate pair
is the cheapest thing in the hold, so at N = 1 the window is long enough that
the pair never reaches its ceiling and pooling one allowance with another
changes nothing. That is the same cell, for the same reason, that v1.21.1's
release note gives for its own fix landing on the raw cells and "not at all on
the beneficiated ones". The defect and its correction agree about where they
live.

🚨  **THE RAW CELL MOVED ON ONE ROW OF 155, AND THAT ROW REPORTS
`market_clearing_fraction = 1.0` IN BOTH BUILDS.** It is the winner, 2017 KJ5,
and what changed is its ARCHITECTURE: New Glenn on xenon at 117,406 kg becomes
Falcon Heavy on iodine at 97,875 kg. No ceiling binds on the mission that won;
the ceiling bound the missions that LOST, and the tighter allowance changed
which one survived.

⚠️  **So `market_clearing_fraction` describes the WINNER, not the search.** A
row can be changed by a ceiling and still report that nothing was left unsold,
because the column is a property of the surviving candidate and the constraint
acted on the ones it beat. Counting rows with `clearing < 1.0` therefore
undercounts the ceiling's influence, and the raw cell is the clean case: **0
rows bound, 1 row changed.** This is the same shape as v1.21.0's warning that a
diagnostic inherits the shape of the term it was written against, arriving from
the other side.

### Three rows got BETTER, and that is the search, not the ceiling

`raw + search` improved on 3 rows of 155 and `benef + search` on 1 of 65, by up
to 3.27%. A tighter constraint improving the answer is the signature of a real
defect, so it was chased rather than filed.

✅  **The revenue model is monotone. Measured: 20,000 randomised fixed-programme
comparisons, pooled revenue LOWER on 10,235, EQUAL on 9,765, HIGHER on ZERO.**
For any fixed programme, pooling can only ever cost you.

**The fleet search is coarse-then-refine, not exhaustive.** A geometric ladder
over F crossed with W, then one refinement pass around the coarse winner's
neighbourhood. Tightening the ceiling moves the coarse winner, so the
refinement explores a DIFFERENT neighbourhood, and it can contain a point the
old walk never visited. The three rows show exactly that fingerprint: identical
vehicle and propellant, `programme_options_priced` 44 -> 41, and `fleet_ships`
falling 6 -> 4, 10 -> 8, 11 -> 8 onto a programme that is cheaper AND sells
marginally more.

🚨  **This is a caveat on check 7's stated invariant and it is not new in this
release.** "Constraining must never improve the answer" is exact for a FIXED
programme and only approximately true for the SEARCHED best, because the best
is the outcome of a non-exhaustive walk. A violation there is evidence about
the ladder, not necessarily about the ceiling, and the way to tell them apart
is the fixed-programme comparison above. Recorded rather than fixed: making the
fleet search exhaustive is a real cost for a few tenths of a percent, and the
branch-and-bound item in CLAUDE.md is the place that question belongs.

### Invariants

- **mass ledger** `0.000000000 kg` on all four cells
- **never-worse** zero exceptions on all three pairings; `benef <= raw` declined
  25 -> 24, median improvement +39.8%
- **Stage 2 tables** identical, 31 rows recomputed at cislunar
- **`caps=None` and `want_phase`** bit-identical, 16,000 randomised comparisons
  on raw IEEE bit patterns
- ceiling bound on `raw + search` 66 -> 57 rows and `benef + search` 17 -> 16;
  it falls because the ladder now turns over BEFORE the binding region rather
  than being driven into it

### It retires a standing claim about N = 1

CLAUDE.md has said since v1.21.0 that "at N = 1 `capacity_cap`,
`single_mission` and constant prices are the same run", on the reasoning that
no single cislunar mission fills a ceiling over a 3-6 year window. That was
true while the two silicate phases drew an allowance each. Pooling them makes
one candidate bind at N = 1. Measured against `unbounded`, which is constant
prices with every ceiling infinite:

| cell | vs `unbounded` | best | |
|---|---|---|---|
| raw, `capacity_cap` | **differs on 1 of 155 rows** | 24.6804x -> **25.7233x** | retired |
| raw, `single_mission` | 0 of 155 | 24.6804x | holds |
| beneficiated, `capacity_cap` | 0 of 65 | 20.5353x | holds |
| beneficiated, `single_mission` | 0 of 65 | 20.5353x | holds |

`single_mission` is safe by construction -- it pins N = 1 and applies no
ceiling -- so what is retired is the `capacity_cap` half, at raw only.
`market_clearing_fraction` reads 1.0 on every row of all four, the differing
one included.

### Two checks that were not running

🚨  **`verify.py check` never ran check 7.** It was wired into
`verify.py invariants` only, so the command every release is argued from ran
checks 1 to 6 and stopped, and the output looked complete because the numbering
stopped where the list did. The one release note that quotes a check 7 result
got it by running the other subcommand by hand. Now in both.

✅  **check 6 gained phase-ceiling coverage.** Every phase
`asteroid_phase_table` can put in a hold must resolve to a finite market, and
every alias must point at a market that exists. That is v1.21.1's defect
generalised so the next one cannot happen: the residual was priced, unbounded,
and on 100% of bodies, and the block above it checks Stage 2's own rows, which
the residual is not one of.

## calc v1.21.1

**The capacity ceilings recalibrated from curve parameter to hard wall. The
levels do not move, and the reason they do not is the finding.**

### The two meanings of Qm, and which one the table holds

`P/P0 = (1 + Q/Qm)^(-1/e)` with `e = 0.5` is `(1 + Q/Qm)^-2`, so revenue is
`Q x P0 x (1 + Q/Qm)^-2`. Writing `x = Q/Qm`, that is `x(1+x)^-2`, whose
derivative `(1+x)^-3 (1-x)` is zero at **x = 1**. So under the curve:

| x = Q/Qm | price multiplier | curve revenue | wall revenue | wall / curve |
|---|---|---|---|---|
| 0.10 | 0.8264 | 0.0826 | 0.1000 | 1.21x |
| 0.50 | 0.4444 | 0.2222 | 0.5000 | 2.25x |
| **1.00** | 0.2500 | **0.2500** | 1.0000 | **4.00x** |
| 2.00 | 0.1111 | 0.2222 | 1.0000 | 4.50x |
| 10.00 | 0.0083 | 0.0826 | 1.0000 | 12.10x |

**The most a commodity can ever earn under the curve is `Qm x P0 / 4`**, at
exactly `Q = Qm`. A hard wall at W earns `W x P0`. Equal maxima therefore put
the equivalent wall at **W = Qm/4**, and a wall at the same Qm is 1.2x to 12x
more generous depending on how saturated the commodity is. That is the size of
what v1.21.0 changed, and it had not been quantified.

### Why the levels are nonetheless right, and were never curve parameters

Every row of `IN_SPACE_ANNUAL_DEMAND_KG` is documented as a consumption budget,
not as the scale of a demand curve:

| row | what the source comment anchors it on |
|---|---|
| `geo` 40 t/yr | ~550 active geostationary satellites at ~70 kg/yr of station-keeping propellant |
| `mars_orbit` 60 t/yr | ~128 t per 2.14-yr synodic period, one crewed mission's in-space propellant |
| `mars_surface` 20 t/yr | "a base that imports 20 t/yr" |
| `leo` 500 t/yr | half a Starship-class Mars-departure propellant load, per year |

A kilogram delivered inside a consumption budget **displaces a kilogram
launched from Earth**, so it earns the full launch-cost-avoided the price model
already computes; beyond the budget there is no demand at all. That is a hard
wall exactly, and these are hard-wall numbers.

🚨  **So the curve was the term using the number wrongly, and v1.21.0's 1.2x to
12x is a CORRECTION rather than an inflation.** Under the curve, supplying a
depot with precisely the water it consumes paid a quarter of the price, which
is not a claim anybody made on purpose; it is what falls out of feeding an
absorption budget into a scale parameter. ⚠️  v1.21.0's own release note called
these "the knee of a smooth curve". That was wrong and is corrected here and in
README.

### Measured and declined: quarter ceilings

The equal-maximum-revenue wall, `W = Qm/4`, measured on the same cells:

| variant | raw + search | benef + search | fleet median | at `max_fleet_ships` |
|---|---|---|---|---|
| as shipped | 18.5707x | 8.5221x | 7 | 11 / 65 |
| **all in-space ceilings / 4** | 27.2932x | 10.9931x | **2** | **2 / 65** |

⚠️  **It is tempting, and that is the argument against it.** Quartering the
ceilings very nearly reproduces the `elasticity` levels (27.29x against 26.57x
raw searched) and it fixes the ladder: the fleet median falls 7 to 2 and rows at
`max_fleet_ships` fall 11 to 2. But it buys that by asserting a base which
imports 20 t/yr only pays full price for 5 t/yr, which contradicts the table's
own anchors, and it is **calibrating a bottom-up cost model to a desired
output** -- continuity with a term this release supersedes is not a calibration
criterion. **Declined.**

✅  And the ladder symptom it "fixes" is not a ceiling problem. v1.21.0 measured
those rows: a median payload of **632 kg against 16,650 kg** for the population,
too small to reach ANY ceiling at a fleet of 64. Quartering makes them reachable
by making the ceilings wrong.

### What did change: one phase had no ceiling at all

⚠️  **RIGHT, AND HALF DONE. See [calc v1.21.2](#calc-v1212).** The alias below
gave the residual the `silicates` ceiling, and every consumer then read that
ceiling per PHASE, so `silicates` and the residual drew the full allowance
each. The comment this release shipped -- "priced as silicates, bounded as
silicates, in one place" -- states the intent exactly; the code gave each of
them its own place. The hashes and deltas in this section are correct for this
release and superseded by the next.

`asteroid_phase_table` appends the composition residual, priced at the
`silicates` quote because that is what it is, and Stage 2's catalog has no row
for it, so `markets.get(name)` missed and it took the infinite default.
**Priced as silicates, bounded by nothing.** Defect class 1 in market form: a
quantity with a price in one half of the model and no counterpart in the other.

`_PHASE_MARKET_ALIAS` maps it to `silicates` and `phase_market_kg()` is the one
place a phase name becomes a ceiling, so the alias cannot be honoured at one
call site and forgotten at another. A mapping rather than a new Stage 2 row on
purpose: the residual is this module's name for "the rest of the rock", not a
commodity anybody trades, and inventing a reference row for it would put a
fiction in the data.

**Stage 2 is not touched and not re-run.**

### What it moved

Under `capacity_cap`, **three of the four cells are bit-identical** -- same
hashes as v1.21.0 -- and only the beneficiated searched cell moves:

| cell | v1.21.0 | v1.21.1 | |
|---|---|---|---|
| raw | 24.6804x | 24.6804x | hash unchanged |
| raw + search | 18.5707x | 18.5707x | hash unchanged |
| beneficiated | 20.5353x | 20.5353x | hash unchanged |
| beneficiated + search | 8.5221x | **8.6861x** | +1.92% |

New baseline: `11ec818051269759` / `6738be0a0bcaeca3` / `109ce36a07ac6975` /
`d3a405d7b281289d`.

🚨  **AND IT MOVES `elasticity`, WHICH COSTS THAT MODE ITS v1.20.0 GUARANTEE.**
The defect was in the curve too -- an unbounded phase is unbounded under either
model -- so fixing it correctly moves both. The curve is hit on the RAW cells,
where the cargo is the body's own composition and the residual is a large mass
fraction, and not at all on the beneficiated ones, where the knapsack loads the
cheapest phase last:

| cell | v1.20.0 | now | |
|---|---|---|---|
| raw | 48.4982x | 49.6422x | **+2.36%** |
| raw + search | 26.5704x | 28.1162x | **+5.82%** |
| beneficiated | 25.7366x | 25.7366x | unchanged |
| beneficiated + search | 14.8549x | 14.8549x | unchanged |

⚠️  **`elasticity` is therefore the v1.14.0 CURVE, not a bug-for-bug replay of
v1.20.0**, and every statement of that guarantee has been corrected: the config
comment, `optimal_payload_mix`'s docstring, the market block's comment, README's
tuning table and the dashboard's help text. To reproduce a pre-v1.21.1 figure
exactly you need a pre-v1.21.1 build, which is what the stamp is for.

### Invariants

Mass ledger `0.000000000 kg` on all four cells; never-worse zero exceptions on
all three pairings; Stage 2 tables identical; check 7 clean, with the ceiling
binding 66 of 155 raw searched rows and 53 of 158 beneficiated.

## calc v1.21.0

**Prices are constant at any volume, and what bounds a programme is quantity.**
The market term stops being a boolean and becomes `market_model`, a four-valued
selector, defaulting to `capacity_cap`.

| `market_model` | price behaviour | what bounds a programme |
|---|---|---|
| **`capacity_cap`** | constant | a hard kg/yr ceiling per commodity |
| `single_mission` | constant | N pinned at 1, no search, no ceiling |
| `elasticity` | `(1 + Q/Q_market)^(-1/e)` | the v1.14.0 demand curve |
| `unbounded` | constant | nothing; a diagnostic, and the run says so |

The ceilings are Stage 2's `annual_market_kg`, **unchanged and not re-run**.
What changed is what happens when one is reached: `elasticity` bent the price
for the whole sale, `capacity_cap` sells everything inside the ceiling at full
price and nothing past it.

### The window, and why the first delivery is different

How much one delivery may sell is how long the destination has been
accumulating since the last one. In steady state F ships repeating every
`cadence_yr` put a delivery on the market every `cadence / F` years, which is
the same constraint as a rate test seen from the other side:

```
kg <= cap x cadence / F     <=>     kg x F / cadence <= cap
```

The first delivery arrives at a market that has been importing from Earth for
the whole outbound-and-back trip, so its window is `mission_duration_yr`. Over
a programme of N the accumulated total is `duration + (N-1) x cadence / F`, and
`_delivery_window_yr` returns the per-delivery average of that: exactly
`duration` at N = 1, converging on `cadence / F` as N grows.

Averaged rather than branched, deliberately. A step between delivery one and
delivery two hands N = 1 a structural advantage no economics produced, and the
ladder would then collapse onto N = 1 for a reason that is a rule rather than a
result.

**The steady-state clock is `campaign_cadence_yr`, not `mission_duration_yr`,
and that is a change from v1.14.0.** A rig starts its next campaign as soon as
the feed is out of the ground; the duration exceeds the cadence on essentially
every body, so the old denominator understated sustained throughput. Under a
smooth curve that is a bias buried in an exponent. Under a wall it moves the
feasible fleet directly.

### The ceilings go into the knapsack

`optimal_payload_mix` takes per-phase upper bounds now, which is what makes a
capped load behave: one that caps out on iron keeps walking down the price
order and spends the freed hold space on whatever is next, instead of flying
the excess unsold. Per-item quantity limits turn an unbounded fractional
knapsack into a **bounded** one, and greedy solves that exactly too, so this is
a constraint inside the optimiser rather than a clamp on top of it.

Raw ore cannot be reshaped, so there the excess simply does not sell
(`_capped_sale_value`). The cap therefore acts through two different mechanisms
across the matrix: mix reshaping in the beneficiated cells, revenue clipping in
the raw ones. That asymmetry is not a defect, it is what raw means.

⚠️  **THE SIZING PATH MUST NEVER SEE THE CEILINGS.** `_cargo_water_kg` calls
the knapsack from inside the fixed-point power solve, so a cap reaching it
would make the whole MASS cascade a function of fleet size, and that asymmetry
is the only reason the programme ladder is affordable to search. Ceilings bound
what a load may SELL, not what the rig digs or the hull carries: the ship is
designed once and the fleet is sized around it. That runs conservative, since
the plant is sized for a richer mix than a capped delivery carries, and it
keeps the ledger internally consistent, because the array flown is still
exactly the array charged.

### Two output columns, not one overloaded one

| column | means | 1.0 unless |
|---|---|---|
| `saturation_multiplier` | a PRICE multiplier | `market_model = "elasticity"` |
| `market_clearing_fraction` | share of the load's gross value that cleared | `capacity_cap` and something bound |
| `unsold_payload_kg` | payload capacity that earned nothing | as above |

A price multiplier and a quantity clip are different claims, and a column that
means one thing in one market model and another in the next is the ambiguity
this project keeps paying for.

### The acceptance test: `elasticity` reproduces v1.20.0

⚠️  **True of this release and superseded by the next.** calc `1.21.1` gave the
composition residual the ceiling it was already priced against, a defect that
was in the curve as well, and the two raw cells moved. See
[calc v1.21.1](#calc-v1211).

The refactor's whole risk is leaking into the old path, so that is what was
checked first, using `verify.py`'s own comparator rather than a fresh one:

| cell | hash | v1.20.0 baseline |
|---|---|---|
| raw | `7f7cc1eed2628150` | MATCH |
| raw+search | `8969c36dd236efaf` | MATCH |
| benef | `84445d43812af21c` | MATCH |
| benef+search | `72e888e3d83d7de8` | MATCH |

⚠️  Compared on the **v1.20.0 column set**. This release adds two columns, so
the frame cannot hash to a v1.20.0 baseline by construction; the two new
columns are dropped and every column that existed at v1.20.0 is identical.

New default cell hashes, for the next release to compare against:
`11ec818051269759` / `6738be0a0bcaeca3` / `109ce36a07ac6975` /
`e78b585fb222831e`.

🚨  **AN EARLIER SET OF FOUR WAS WRONG, AND THE WAY IT WAS WRONG IS THE
TWELFTH ENTRY IN `verify.py`'S TRAP LIST.** `run_cell` resets four config
fields explicitly and takes everything else from `CELLS`; `market_model` was in
neither, so a harness that ran the acceptance cells with
`market_model="elasticity"` left the live config there, and the baseline it
then took "at the new default" was **entirely elasticity**. It is trap 1 one
field along, the same shape as v1.15.0's two cells recorded as `cislunar` that
ran against `earth_surface` prices.

⚠️  **Nothing raised, and the hashes looked plausible.** What caught it was an
internal contradiction between two checks on one population: check 7 reported
**66 rows bound by a ceiling** beside a frame whose **minimum** clearing
fraction was **1.0000**, which cannot both be true. Fixed by resetting
`market_model` from the dataclass default beside the other four, so the trap is
closed for every future harness rather than for this one.

✅  The measured cells above are unaffected: they came from a
`verify.py baseline` in a clean process, which never set the field, and from a
run that passed all four models explicitly.

### All four models on one cell, which is the argument for the whole release

`raw+search`, 400-row cislunar stride sample, everything else identical:

| `market_model` | best cost/revenue | fleet median / max | rows at `max_fleet_ships` | rows a ceiling bound |
|---|---|---|---|---|
| `single_mission` | 24.6804x | 1 / 1 | 0 / 155 | n/a |
| `elasticity` | 26.5704x | 2 / 64 | 1 / 155 | n/a |
| **`capacity_cap`** | **18.5707x** | **3 / 64** | **15 / 155** | **66 / 155** |
| `unbounded` | 7.4600x | **64 / 64** | **155 / 155** | 0 / 155 |

⚠️  **The `elasticity` row is a v1.21.0 figure and moved at v1.21.1**, to
28.1162x, when the composition residual gained the ceiling it was already
priced against. The other three rows are unchanged. See
[calc v1.21.1](#calc-v1211).

🚨  **`unbounded` puts every row at the ladder's top and reports 7.46x**, which
is the whole reason this release could not simply be "turn the market term
off". Constant prices with nothing bounding quantity is not a cheaper answer,
it is **not an answer**: 155 of 155 rows report where the loop stopped. That
row is what the capacity ceiling exists to prevent, and it is left in the
selector, loudly labelled, so the failure mode is reachable on purpose rather
than by accident.

`capacity_cap` sits where it should, between the single mission and the
fantasy. It is better than `single_mission` because a programme genuinely does
amortise, and far worse than `unbounded` because the amortisation stops paying
once the market fills.

⚠️  `single_mission` at 24.6804x is **exactly** the `capacity_cap` raw N = 1
figure, to four decimals, which is the arithmetic confirming what the N = 1
section above claims: no single cislunar mission fills a ceiling, so the two
models are the same run there.

⚠️  **They are EXPECTED to separate at `geo` and that has not been measured.**
Its 40 t/yr import budget is the smallest in the table, so a single delivery
plausibly fills it, but no `geo` cell has ever been run and there is no frozen
Stage 2 catalog for one; making it means a live Stage 2 run at today's prices,
which is a methodology decision rather than a spare afternoon. Treat the
difference between the two models away from cislunar as unmeasured.

### The release introduced a defect class 3 and then closed it

`_market_mode()` validates a config string, and the first cut of this release
called it from `_evaluate_combo_at_ratio` and again from
`_programme_ladder_cached`. Both are per CANDIDATE. Counted rather than
estimated, on a 150-row beneficiated searched cell:

| | calls | per evaluable row |
|---|---|---|
| as first written | 21,574 | **332** |
| after the hoist | 151 | **2** |

332 calls per row is ~216 M over a full catalog, at ~217 ns each: **~47 s of a
full beneficiated cell** to re-derive one of four answers. That is defect
class 3 exactly, *a quantity asked at a finer granularity than it has answers*,
and this release wrote it rather than inherited it.

Fixed the way `markets` already was: resolved once per asteroid in
`evaluate_asteroid` and threaded down, with the parameter defaulting to None so
a standalone caller still works. **All eight cell hashes reproduce**, four under
`elasticity` against v1.20.0 and four under `capacity_cap` against the baseline
taken before the hoist, so it is a performance change and nothing else.

⚠️  The lesson this file already states applies to the fast path that was tried
first: an identity test against a frozen set took 217 ns to 168, a 1.3x on a
call that should not have been happening at all. **Cutting the cost of a call
is not the same as cutting the call**, and the profile said 47 s either way
until the count was taken. Count the calls before optimising the callee.

### Is a feasibility gate on the ladder needed?  Measured: no

The design discussion called for rungs that exceed a ceiling to be refused
outright, with the reshaping knapsack as the main event and a feasibility gate
on the ladder as a backstop. The gate is **not implemented**, and this is the
measurement that says it need not be.

Clearing fraction of the rungs the search actually CHOSE:

| cell | min | 5th percentile | median |
|---|---|---|---|
| raw + search | 0.8307 | 0.9635 | 1.0000 |
| beneficiated + search | 0.8858 | 0.9851 | 1.0000 |

The search does pick rungs where a ceiling binds, and it never picks one that
throws much away: the worst chosen rung still places 83% of its load, and 95%
of rows place more than 96%. That is the objective doing the work a gate would
have done, because a rung that cannot sell its cargo has low revenue and loses
on cost/revenue without anyone forbidding it.

⚠️  **The two answers were in tension and the later one won.** A pure
feasibility gate says "this rung is not offered"; it cannot say "cap the iron
and fill the freed space with platinum", which is what the mixture-optimisation
requirement asks for. Clipping with reshaping is the only formulation that does
both, and it subsumes the gate: a fully-clipped rung is priced at the revenue
it can actually earn instead of being removed, which is strictly more
information.

✅  What DOES hold literally is the price claim. `saturation_multiplier` is
exactly 1.0 on every row in every mode but `elasticity`, asserted by check 7.
No price moves; only quantity is bounded.

### verify.py check 7, and the bug it found in itself first

`check_market_cap` asserts the thing this release actually claims, and it is
the mirror of check 5's argument. Check 5 says widening a search must not make
the reported answer worse; this says **narrowing one must not make it better**.
For any fixed programme the capped gross value is at most the uncapped one and
the cost is identical, so `capacity_cap` can never beat `unbounded` row by row.
A violation would mean an allowance leaking into the cost side, or a rung
priced under one set of caps and reported under another.

| | pairs | max | cap beat unbounded | ceiling bound |
|---|---|---|---|---|
| raw + search | 155 | 1.000000000 | **0** | 66 rows |
| beneficiated + search | 158 | 1.000000000 | **0** | 53 rows |

⚠️  **Its first run reported four failures that were not failures**, and they
are worth recording because they are trap #2 from `verify.py`'s own header
arriving in a new check. Four beneficiated rows had a
`market_clearing_fraction` of **1.0000000000000002**: bodies where a ceiling
binds by a hair, so the reshape branch runs, the bounded knapsack re-walks to
the same load, and the ratio lands one ULP over 1.0 because the walk took a
different route to the same answer. Nothing in the model moved. **A comparator
stricter than the artefact it compares reports failures that do not exist**,
which is why check 5 has always tested `r > 1 + 1e-12` rather than `r > 1`, and
the new check now carries the same tolerance.

The other invariants pass unchanged under the new default:

| check | result |
|---|---|
| 4, mass ledger | max absolute error `0.000000000 kg` on all four cells |
| 5, never-worse | 0 exceptions on all three pairings; searched vs N = 1 improves a median **+50.7%** raw, **+53.7%** beneficiated |
| 6, Stage 2 tables | 31 rows recomputed at cislunar, all identical |

⚠️  Those never-worse medians are **larger** than the `elasticity` era's
+42.4%, which is the search having more room to move once the price stops
sagging with every extra ship.

### What it did to the numbers

⚠️  **400/150-row cislunar stride samples, not a full catalog.** Under THE
SAMPLING RULE these are the right shape for a ratio between two settings on
identical rows and are **not** a prediction of a full-catalog cell.

| cell | `elasticity` | `capacity_cap` | change |
|---|---|---|---|
| raw | 48.4982x | **24.6804x** | -49.1% |
| raw + search | 26.5704x | **18.5707x** | -30.1% |
| beneficiated | 25.7366x | **20.5353x** | -20.2% |
| beneficiated + search | 14.8549x | **8.5221x** | -42.6% |

Every cell improves, which is the expected direction and not a result: the
price haircut that used to apply to every sale is gone, and what replaces it
binds on some rows and not others. The winner changed propellant where the
ceilings bit hardest: **iodine to xenon** at raw N = 1, and **krypton to
iodine** beneficiated. It held at iodine in both searched cells, though the raw
searched cell changed BODY, 2017 MC1 to 2017 KJ5.

⚠️  This sentence said "three of the four cells" until an audit on 2026-09-08
counted it, above a parenthesis naming two. A count spelled out in prose beside
the list it is counting is the failure this project names oftenest, and it
survived here because the parenthesis looked like an example rather than the
whole set. **Name the list.**

**Neither N = 1 cell binds on any row, at cislunar.** At N = 1 the window is
the whole mission duration, ~3 to 6 years, and no single cislunar mission fills
a 55 t/yr water or 25 t/yr metals ceiling over that. So at this destination
`capacity_cap` and `single_mission` are the same run, and every N = 1 cislunar
figure this project has published is a constant-price figure already.

⚠️  **That is a cislunar result and does not generalise.** The allowance scales
with the destination's import budget, which runs from `geo`'s 40 t/yr to
`leo`'s 500 t/yr, so whether a single mission binds is a per-destination
question and only cislunar has been asked.

### Where the ceiling binds, and where it cannot reach

It binds on **66 of 155** raw searched rows and **17 of 65** beneficiated
searched rows, and it binds at the top of the ranking, which is what matters:
the raw searched winner clears **0.8307** of its gross value and answers by
taking a **smaller** fleet than it did under `elasticity` (F = 2, N = 10
becomes F = 1, N = 5). The ladder turns over exactly as intended there.

⚠️  **But more rows sit at `max_fleet_ships`, not fewer**, which is the
opposite of what was predicted:

| cell | | `elasticity` | `capacity_cap` |
|---|---|---|---|
| raw + search | fleet median / max | 2 / 64 | **3 / 64** |
| | rows at `max_fleet_ships` | 1 / 155 | **15 / 155** |
| beneficiated + search | fleet median / max | 2 / 26 | **7 / 64** |
| | rows at `max_fleet_ships` | 0 / 65 | **11 / 65** |

**Those rows are the ones a ceiling cannot reach, and they are the worst rows
in the run.** All 15 raw ones clear at exactly 1.0000 and carry a median
payload of **632 kg against 16,650 kg for the population**, at cost/revenue
ratios of **486x to 37,620x** against the winner's 18.6x. A delivery that small
never fills a per-commodity ceiling: the allowance falls as 1/F while the
payload per delivery is constant, so a 632 kg load needs a fleet of roughly 300
to bind, and the ladder stops at 64.

Under `elasticity` even a tiny payload took a small haircut that grew with F,
so it drifted off the ceiling. **A wall does not blend.** A row whose every
commodity sits inside its allowance feels nothing at all, and is monotone in N
again. That is the documented `earth_surface` degeneracy arriving on the
bottom of the cislunar ranking rather than on the top of it.

✅  It costs nothing today, because those rows lose by three orders of
magnitude. It is written down because the diagnostic changes meaning: **"rows
at `max_fleet_ships`" no longer reads as "their payloads have no finite
market"**, it reads as "their payloads are too small to reach one". Both are
the ladder running out rather than turning over; only the second is harmless.

### Measured and declined: a ceiling for the composition residual

The first hypothesis for the above was `other (bulk silicate)`, calc's
composition residual. Composition fractions sum to 0.73-0.96 and the remainder
is priced at a bulk-silicate floor, but the residual is not a Stage 2 commodity
so `market_table` has no entry for it and it takes the infinite default. It is
priced, it is on 100% of rows, and it has no ceiling.

Measured rather than assumed, by mapping it to the `silicates` ceiling it is
already priced against:

| cell | as shipped | residual mapped to `silicates` |
|---|---|---|
| raw + search | 18.5707x, 66/155 bound, 15 at cap | **18.5707x, 66/155, 15** |
| beneficiated + search | 8.5221x, 17/65 bound, 11 at cap | **8.6861x, 17/65, 11** |

**Raw is bit-identical and beneficiated moves 1.9%**, with the bound count and
the fleet distribution unchanged in both. So the residual is not what lets a
programme scale, and the hypothesis was wrong. Declined for now on that
evidence; it remains the correct mapping on the merits, and it is a one-line
change whenever the ceilings are next recalibrated.

⚠️  The measurement is the point here rather than the verdict. The mechanism
was legible, plausible and wrong, and one 400-row A/B was enough to say so.

## master v1.25.0 - Stage 3 moved to the `spacecost` package

**No number moved, and that is the claim this release has to make rather than
assume.** Stage 3's reference tables left this repository for
[`spacecost`](https://github.com/loggger101/spacecost), an independent MIT
package pinned here at tag `v0.1.1`. `modules/transportation.py` went from
5,054 lines to 368 and is now the adapter that drives it.

Two thirds of that module was annotated reference data -- 36 launch vehicles,
41 propellants, 33 delta-v segments, 44 operational costs, 20 storage systems,
141 cited rows in total -- and nothing in its schema knew what an asteroid was.
The extraction sliced source line ranges rather than re-typing anything, so
every citation crossed over byte for byte.

### What did not move

| | |
|---|---|
| `pipeline_version` | **1.14.0**, unchanged, and deliberately so |
| the six Stage 3 CSVs | byte identical, all six, verified both ways |
| all four Stage 4 cells | 139/139 columns identical, hashes MATCH against the committed `1.20.0` baseline |
| every measurement in this file | unaffected; nothing here needs re-measuring |

The stamp identifies the DATA, the data did not change, and spacecost's own
data-contract version is the same `1.14.0` this module last shipped. Bumping it
would have desynchronised every archived catalog in order to announce a
refactor. The **master** version carries the structural change instead:
`1.24.0` -> `1.25.0`.

### Verification

```
verify_stage3.py   config 10 dials identical | contract 1.14.0 = 1.14.0
                   six CSVs byte-identical through adapter and package
                   five tables match spacecost's committed reference/
verify.py check --tag 1.20.0 --skip prune parallel
                   raw           139/139 identical | 7f7cc1eed2628150 | MATCH
                   raw+search    139/139 identical | 8969c36dd236efaf | MATCH
                   benef         139/139 identical | 84445d43812af21c | MATCH
                   benef+search  139/139 identical | 72e888e3d83d7de8 | MATCH
                   mass ledger 0.000000000 kg on all four | never-worse clean
verify_docs.py     all 11 checks
```

The Stage 3 comparison was also run against a build of the **pre-adapter**
module captured before any edit: all six files identical, `f12f099e36635025`
and the other five hashes reproducing exactly.

### The split is checked, because the last one was not

This project was once developed in two places at once and `1.0.6` / `1.1.4` /
`1.3.6` each shipped as two different things; see
[the parallel-repo divergence](#the-parallel-repo-divergence). What made that
expensive was not the split, it was that nothing checked it. So:

- the **data** is single-sourced, one copy, in spacecost
- the **dials** are mirrored, ten fields, and compared at import by
  `_check_config_surface()`, which raises rather than warns
- the **output** is compared byte for byte by `verify_stage3.py`

`use_yfinance` differs on purpose -- **True** here, **False** in spacecost --
because a pipeline stage is expected to fetch and a library must not. It is one
of the two defaults that kept `TransportConfig` in this repo.

### One defect, found by a docs check

`build_master.py` resolves name collisions with a whole-word regex over the
entire module text, **comments and string literals included**. The adapter's
`from spacecost import validate as _v` had the imported name rewritten to
`validate_transport`, so `master.py` asked the package for an attribute it does
not have. Two string literals were mangled the same way.

⚠️  Aliasing the local name does not help: the imported name is still a bare
word. The fix is on the package side -- spacecost exports `validate_tables` as
a collision-proof second name. **Nothing in `verify.py` looks at Stage 3**, and
the pipeline would only have failed at run time; `verify_docs.py` checks 8 and
9 caught it because they import master.

### Also in this release

`verify_docs.py` check 7 could not parse a PEP 508 direct reference
(`spacecost @ git+https://...`) and reported a mismatch that was not one: the
checker not understanding the manifest format it checks. It now strips the
`@ url` form before comparing.

`master.py` is **13,954 lines, down from 18,577**, and pip-installs spacecost
from a pinned git tag at import. ⚠️  Keep the tag pinned; an untagged URL would
let a fresh Colab paste install a different table with nothing here moving.

## calc v1.20.0

**Both insurance premiums are off**, behind a new `charge_insurance` flag that
defaults **False**. Module 3 prices two of them and the cost cascade charged
both on every mission:

| Module 3 row | basis | value |
|---|---|---|
| Third-party liability insurance | flat, per mission | $1,500,000 |
| Launch insurance | percent of (launch + spacecraft book value) | 10% |

Neither is wrong, and that is what makes this different from every other cost
flag in the module. `charge_tanker_flights` is gated because the charge is
**incorrect** here; it bills a scenario this module does not have. These two
are correct, real, and **out of scope**: this pipeline prices the marginal
physics and hardware of moving a kilogram, on the same framing that makes the
two surface delivery prices
[marginal-transport lower bounds](README.md#what-a-kilogram-is-worth) with no
NRE-style programme overhead in them. A premium is priced off an underwriter's
book. It is not a mass, a Delta-v or a kilowatt, and nothing else in the
cascade is priced that way.

It is also a second statement of a risk the model already carries explicitly.
`model_reliability` multiplies expected revenue by
`p_launch x exp(-T/MTBF) x p_mining` and charges every cost in full; a premium
is what a programme pays to convert that risk into a certain payment, so
pricing both is pricing one uncertainty in two currencies.

⚠️  **This does not disturb the reliability term, in either direction.** That
block's own note has said since v1.8.0 that insurance "replaces hardware on
failure, not revenue, so there is no double count". That was true, so there is
no double count to remove now, and `charge_insurance` reaches none of
`p_launch`, `p_cruise` or `p_mining`. The two comments that made the argument
are corrected in place rather than deleted.

### What the two premiums were worth

Measured on a cislunar stride sample, Stage 4 only, on the four cells and caps
`verify.py` uses, each run twice against an identical catalog in one process,
so every ratio below is over identical rows:

| cell | rows | best cost/revenue, charged | off | median improvement | premium, % of total cost |
|---|---|---|---|---|---|
| raw | 155 | 52.0009 | **48.4982** | **5.85%** | 2.752% |
| raw + search | 155 | 30.0398 | **26.5704** | **9.57%** | 4.342% |
| beneficiated | 65 | 27.4143 | **25.7366** | **5.49%** | 2.409% |
| beneficiated + search | 65 | 16.5339 | **14.8549** | **9.33%** | 3.923% |

`median improvement` is `median(1 - r)` with `r = off / charged`, the
convention every never-worse figure in this project uses; the reciprocal
reading is 1.7x larger and is not the one on record.

🚨  **THE IMPROVEMENT IS TWICE THE PREMIUM'S SHARE OF COST, AND THAT IS THE PART TO
UNDERSTAND BEFORE READING ANY OF IT.** A premium is an **upfront** line, so it
is multiplied by contingency (1.20) and then compounded over the whole mission
at the upfront WACC multiplier before it reaches `total_cost`. Removing $1 of
it removes $2.12 to $2.38 of the answer:

| cell | premium share | median improvement | effective multiplier |
|---|---|---|---|
| raw | 2.752% | 5.847% | **2.124** |
| raw + search | 4.342% | 9.571% | **2.204** |
| beneficiated | 2.409% | 5.489% | **2.279** |
| beneficiated + search | 3.923% | 9.329% | **2.378** |

The share column is the line as Module 3 prices it. **Quote the improvement and
not the share**, unless you mean the invoice rather than the answer.

✅  **"Insurance" here is one term with a rounding error attached.**
Third-party liability is a flat $1.5M and lands at a median **0.027% to
0.045%** of total cost; launch insurance is 2.383% to 4.322% of it. Everything
above is the 10% of the launch stack, and the flat premium would not have been
worth a release on its own.

🚨  **The programme search makes insurance MATTER MORE, not less**, 4.342% against
2.752% raw, and it is the only cost line in the module that behaves that way.
Both NREs amortise across N and the rig is shared across a fleet; a premium is
underwritten **per launch** and per spacecraft, so it does not amortise at all.
As a programme grows, insurance grows into the space the amortised lines
vacate.

### Verification

**With the flag ON, calc 1.20.0 is bit-identical to 1.19.1**, which is the
claim every default flip in this project has to make. All four cells against
the `baseline-1.19.1` on disk:

| cell | columns | hash | |
|---|---|---|---|
| raw | 139/139 | `4184f13cf57a6df7` | MATCH |
| raw + search | 139/139 | `66d88054984b014a` | MATCH |
| beneficiated | 139/139 | `b88b5dac5d2fe43d` | MATCH |
| beneficiated + search | 139/139 | `2a4f610ec97bf6f2` | MATCH |

The new default's own hashes, for the next release to compare against:
`7f7cc1eed2628150` / `8969c36dd236efaf` / `84445d43812af21c` /
`72e888e3d83d7de8`.

**`verify.py check --tag 1.20.0` passes all six on the new default**, the
full pass rather than the five-minute loop: the pre-filter on against off is
139/139 columns and MATCH on all four cells, serial against 8 workers is MATCH
on both searched cells, the mass ledger is `0.000000000 kg` on all four,
never-worse has zero exceptions on all three pairings, and Stage 2 recomputes
identical on 31 rows.

Three properties hold in all four cells and are worth re-checking if anything
here is touched:

- **The evaluable set does not move.** 155 / 155 / 65 / 65 rows charged and
  off, the same designations both ways. Feasibility is a question about two
  masses; a premium enters no mass cascade, so it cannot make a mission close
  or fail to close.
- **Never-worse, and it is provable rather than lucky.** Every option's cost
  falls weakly and no revenue moves, so every option's ratio falls and so does
  the argmax over them. Measured anyway: **0 worse** in all four cells, worst
  `r` 0.9534 / 0.9317 / 0.9492 / 0.9258.
- **The winner does not change.** 2017 KJ5 raw, 2017 MC1 raw-searched, 2010
  FG81 in both beneficiated cells, on both settings. The premium is close to
  proportional to the launch stack, so it rescales the ranking far more than it
  reorders it.

⚠️  **The column count is unchanged: 141 both ways.** `liability_cost_usd`
and `launch_insurance_cost_usd` stay in the CSV at 0.0, so no consumer schema
moves, the dashboard's cost breakdown still resolves, and a charged run is one
column away from an uncharged one rather than a different file format.

### What this retires

🚨  **EVERY MEASUREMENT COMMITTED IN THIS PROJECT IS A `charge_insurance = True`
MEASUREMENT**, including the whole 20-cell campaign of 2026-08-23/24 and every
table in [Measurement history](#measurement-history). None of them is wrong and
none of them is reproducible by a configure-nothing run any more; set
`charge_insurance` True to reproduce one. This is calc v1.17.0's situation
exactly, a default that changes the question a default run asks, and the same
rule applies: **do not read any table as covering a `charge_insurance = False`
run unless it says so.**

⚠️  **Do not scale a committed cell by any ratio above.** These are
stride-sample cells at caps of 400 and 150, and the four *levels* in the table
(52.0009 and the rest) are sample bests rather than the full-catalog cells.
What a sample estimates well here is the ratio between two settings over
identical rows, which is the better-conditioned half of THE SAMPLING RULE; the
levels are the half that has been wrong four times.

## catalog v1.2.0

Four items. Two were the intended ones and change no number. The third was
found while verifying the second, **does** change a number, and is the reason
this is a minor bump rather than a patch: NEOWISE's `ORDER BY` was not total,
so which of a body's duplicate rows survived deduplication was decided by
nothing at all. The fourth came from an audit of another project and adds the
orbit-quality fields the ranking never had.

🚨  **THE THIRD ITEM IS THE ONE TO READ.** It was not on any plan. It surfaced
because switching transports produced two frames with the same content hash and
different row order, and the only reason that was noticed is that the change
was verified by comparing the two paths instead of by reasoning that they must
agree.

### `ORDER BY asteroid_number` is not total, and dedup is order-sensitive

`deduplicate_catalog` sorts by completeness with `kind="stable"` and keeps the
first row. A **stable** sort preserves input order among equal keys, so for two
rows of equal completeness the winner is whichever arrived first.

NEOWISE returns **183,408 rows for 143,318 bodies**. Measured on the live
table:

| | count |
|---|---|
| bodies with more than one NEOWISE row | 27,864 |
| of those, top completeness is **tied** | 27,819 |
| of those, `diameter_km` actually differs | **27,802** |

Relative spread of those diameters: **median 11.6%, p90 27.4%, max 86.3%.**

⚠️  **Diameter cubes into `estimated_mass_kg`, which is what the whole ranking
runs on.** A median 11.6% diameter spread is a **39% mass** spread, and the
worst body spans 3.832 km to 27.99 km, a factor of 380 in mass.

The ordering was left to the server, and the server does not do it the same way
twice: a sync and an async pull of the **identical** ADQL returned the same
183,408 rows with the same content hash in a **different order**. So the
diameter of ~28,000 bodies has never been reproducible, and no committed run
can be said to have picked them deliberately.

The fix orders on enough columns to be total. Both transports then produce
byte-identical frames (`5e4872ba51d9b70d`), and repeated async pulls are stable.

✅  **It deliberately does NOT try to pick the physically best measurement.**
`fit_code` and `stacked_flag` are the NEOWISE fields that express fit quality,
and preferring them is a **modelling** decision with a defensible answer that
somebody should choose on the physics. This release only makes the choice
*defined*. Reproducibility first; correctness of the criterion is a separate
question, and still open.

⚠️  **This does move numbers, on the next Stage 1 run.** Diameters for up to
27,802 bodies may change relative to the catalog on disk, and mass, value and
ranking move with them. Nothing changes until Stage 1 is re-run; the existing
catalog is untouched.

### The ranking had no idea which orbital elements were any good

SBDB exposes **79 queryable fields** (`?info=field` lists them). This pipeline
requested **23**, and among the 56 it did not was `condition_code`, the MPC
orbit-uncertainty parameter U: 0 for a well-determined orbit, 9 for one barely
constrained.

⚠️  **Δv is computed from `a`, `e` and `i`, and the entire economic ranking is
computed from Δv.** So an orbit fitted to a four-day arc with 18 observations
produces a cost/revenue ratio quoted to six figures, and nothing in the
pipeline could tell it apart from a body observed for 70 years.

Measured against the profitability catalog on disk, joined to SBDB:

| set | n | U >= 5 | vs population | binomial p |
|---|---|---|---|---|
| **top 30 by cost/revenue** | 30 | **43.3%** | **3.1x** | **8.3e-05** |
| top 50 | 50 | 30.0% | 2.2x | 2.5e-03 |
| all matched rows | 157 | 18.5% | 1.3x | 0.065 |
| SBDB population (1,562,105 bodies) | - | 13.9% | 1.0x | - |

🚨  **The enrichment is concentrated at the very top and vanishes down the
ranking**, which is the signature of a winner's curse rather than of a bad
population. Quartiles of the same 157 rows: Q1 **35.9%** at U >= 5, then 5.1%,
15.4%, 17.5%. Ranking on a quantity derived from noisy elements preferentially
selects the bodies whose fit errors happen to flatter them, and the extreme of
the ranking is exactly where that bias is strongest.

The best-ranked bodies with barely-determined orbits:

| designation | ratio | U | arc (days) | observations |
|---|---|---|---|---|
| **2017 MC1** (rank 1) | 18.26 | **7** | 32 | 28 |
| 2015 BN515 (rank 2) | 21.27 | **8** | 12 | 17 |
| 2024 SS4 | 32.67 | **7** | **5** | 33 |
| 2024 XY11 | 36.59 | **8** | **4** | 24 |
| 2015 KJ292 | 37.52 | **9** | **4** | 18 |

✅  **This release FETCHES the information and applies none of it.** Filtering
or down-weighting on orbit quality changes what the model answers, and choosing
the rule is a modelling decision with several defensible answers (a hard U
cutoff, an arc-length floor, a confidence-weighted ranking). Making the data
available is the part that is unambiguously right; **the top of the ranking
should not be read as a target list until one of those is chosen.**

⚠️  Six related fields came with it, all 100% populated: `data_arc`,
`n_obs_used`, `rms`, `moid` (Earth MOID, a standard accessibility proxy this
model derives nothing from), `class` and `soln_date`. Fields with negligible
coverage were checked and **deliberately not added**: `H_sigma` 0.00%, `G`
0.10%, `BV` 0.85%, `UB` 0.81%, `IR` 0.00%, `GM` 0.01%, `extent` 0.02%.

ℹ️  Found by auditing `julie-dujardin/space-map` (AGPL-3.0, read not copied),
whose SBDB mirror queries the `?info=field` discovery endpoint instead of
hardcoding a field list. A pipeline that discovers the schema would have
surfaced both this and the missing `epoch` on its own.

### The two intended items

Neither changes a number this pipeline computes. The first is a **latent**
defect: a field that has been fetched since `1.0.3` and was never usable. The
second is robustness on a source that has already failed once in the record.

### `ma` was fetched without `epoch`, so it was unusable rather than unused

`_JPL_FIELDS` requested `ma`, commented in the module as "mean anomaly at
epoch (deg)", and never requested `epoch`. A mean anomaly fixes no date without
the epoch it is referred to, so `mean_anomaly_deg` has been present in every
catalog this project has written and has never been capable of answering the
question it exists to answer.

⚠️  **It was invisible because nothing downstream reads it.** Module 4 prices
transfers from `a`, `e` and `i` only; `longitude_asc_node_deg`,
`arg_perihelion_deg`, `mean_anomaly_deg`, `mean_motion_deg_day` and
`orbital_period_yr` have **zero references** outside Module 1. So a column that
was silently useless sat beside four that were merely unused, and no check
could tell them apart. That is the same shape as "an unreachable branch is not
a verified branch": an unread column is not a validated column.

The fix is one entry in `_JPL_FIELDS`, one in `_JPL_RENAME`, one in
`_JPL_NUMERIC` (SBDB returns the epoch as a **string**, so it must be coerced
or it lands in the CSV as text), and one in `_SAFE_FIELDS`.

🚨  **`_SAFE_FIELDS` mattered more than it looks.** That fallback already
carried `ma`, so omitting `epoch` from it would have reproduced the exact
defect on precisely the runs where the primary field list had already failed,
i.e. the runs least likely to be examined closely.

⚠️  **The epoch must stay PER ROW.** Most bodies share one, but not all: a
2,000-row NEO sample returned 1,999 at JD 2461200.5 and one at JD 2455562.5,
**5,638 days apart**. A hardcoded constant would be silently wrong for exactly
the minority most likely to be interesting.

**No number moves.** Nothing reads the column; it is added so the next Stage 1
run captures it rather than requiring a second full refetch the day anyone
wants a dated launch window. The stamp moves because the output gains a column,
which is the schema half of the bump rule.

### NEOWISE now asks IRSA for an async job

`fetch_neowise` posted its ADQL to `/TAP/sync` and streamed the body. A
synchronous TAP query holds **one** connection open for the server-side query
**and** the whole ~19 MB transfer, so a proxy timeout anywhere in that window
discards the entire result, with no retry surface and no partial success.

That is not hypothetical here. The run behind the committed cislunar 2x2 saw
IRSA return `502 Proxy Error` all evening and `Source summary` read
`'NEOWISE': 0`.

The IVOA UWS pattern splits it into three phases: submit, run server-side with
nothing held open, then fetch the result from a **stable URL** that can be
re-fetched. A poll that fails is explicitly not fatal, because the job is still
running on the server, which is the entire point.

Measured against the live service on 2026-09-03, same ADQL both ways:

| path | result |
|---|---|
| `/TAP/sync` | HTTP 200, 584 bytes, 3.9 s |
| `/TAP/async` | submit 303, COMPLETED after 5 polls, 584 bytes, 5.7 s |

**Byte-identical.** Async costs a few seconds of polling on a small query and
buys the retry surface on a large one.

✅  **It can only add a way to succeed.** On any async failure `body` stays
`None` and the original synchronous block runs unchanged, so the worst case is
the behaviour this function had before. All of the existing body validation
(VOTable envelope, HTML error page, empty body, unexpected header) is untouched
and runs on whichever path produced the bytes.

New config fields: `neowise_use_async` (default `True`),
`neowise_async_max_wait_s` (default 900).

### What this release does NOT contain

⚠️  A measured Δv change was **considered and refused**, and the reasoning is
worth keeping because the measurement looked good in isolation. Module 4 takes
the entire inclination change at Earth departure; splitting it optimally saves
a median 4.87% of `dv_out` on a 38,892-row stride sample, and the split
contains the shipped rule as an endpoint so it is never-worse by construction.

Against a **Lambert oracle** with real 3-D geometry it makes the model worse in
every inclination band, because the shipped estimator carries a second, larger
error of the opposite sign:

| band | shipped error | after the split | |
|---|---|---|---|
| i < 5 deg | -1.139 | -1.288 | worse |
| 5-15 deg | -1.601 | -2.312 | worse |
| i > 15 deg | -0.533 | -2.656 | worse |

Negative means the model understates the cost. The two errors partially cancel,
the cancellation is accidental and inclination-dependent, and **removing only
the overcharge exposes the undercharge in full.** See
`research/starred-repos/FINDINGS.md` F1 and F4 for both measurements and the
validated solver they were taken with.

ℹ️  The standing consequence, which no release fixes: **the pipeline's outbound
Δv is optimistic by roughly 0.4 to 1.3 km/s**, and the whole 20-cell campaign
inherits that. It is a model limitation, not a regression, and it is recorded
here rather than fixed because fixing it correctly means both terms moving
together and a full re-measurement.

## calc v1.19.2

🚨  **`mars_orbit` PHASED ITS LAUNCH WINDOWS AGAINST EARTH**, and had done so
since v1.18.0 shipped it. One conditional, written in two places:

```python
a_dest_au = (A_MARS_AU
             if str(config.delivery_destination).strip().lower() == "mars_surface"
             else 1.0)
```

`synodic_period_yr(a_asteroid, a_dest)` returns the years between successive
departure windows, and its second argument is the heliocentric orbit the cargo
is delivered to. A depot in a 1-sol Mars orbit is reached by the **same
heliocentric transfer** as the surface 3,400 km beneath it: the same
`_asteroid_to_mars_dv_km_s`, the same transfer ellipse terminating at 1.524 AU,
the same arrival `v_infinity`. It therefore waits on the same Earth/Mars
alignment. The test named one of the model's two Mars destinations and silently
got the other one wrong.

### What it was worth

Measured on the catalog's 1,555,667 semi-major axes, on a 38,892-row stride
sample of them:

| phased against | median synodic period | mean | at the 10-yr cap |
|---|---|---|---|
| Earth, 1.000 AU, what `mars_orbit` got | 1.2976 yr | 1.3473 | 0.17% |
| **Mars, 1.524 AU**, what it should get | **3.3033 yr** | 3.4988 | 0.71% |

**The two answers differ on 99.97% of rows, and the old one is too SHORT on
99.46% of them**, by a median of 2.0079 yr and by as much as 8.2397.

✅  **The committed `mars_surface` cadence is what makes the old value visibly
wrong rather than merely different.** CLAUDE.md records a Mars campaign
repeating every **3.798 yr raw** against ~1.37 everywhere else, and names the
cause: the Earth/Mars synodic period, and a transfer that is a separate
heliocentric leg. `mars_orbit` was being handed the ~1.37 that belongs to a
destination in Earth's orbit, for a mission that flies to Mars.

The term is not decorative. `synodic_yr` feeds `window_wait_yr`
(`0.5 x synodic`), and `campaign_cadence_yr` is `max(stay, synodic)`, so it
sets how often a rig can fly, how long return propellant sits boiling off, the
programme span, and **which of the rig's two bounds retires it**. Mars is the
one destination where the calendar bound does most of the work, precisely
because the cadence is long; `mars_orbit` was being scored as though it were
not.

### The fix is a table entry, not a better conditional

`DELIVERY_ARCHITECTURES` is where a destination already declares its physical
mission, so it now declares this too:

```python
"window_phasing_au": A_MARS_AU,     # mars_orbit, mars_surface
"window_phasing_au": 1.0,           # everything riding Earth's orbit
```

and `window_phasing_au(destination)` reads it back. Everything in Earth's
system, `leo`, `geo`, `cislunar`, `lunar_surface` and `earth_surface`, phases
against 1 AU because they all ride Earth's orbit around the Sun.

⚠️  **The field is asserted at import, not defaulted.** A `.get(..., 1.0)`
would have been a silent default of the wrong value for any future destination
off Earth's orbit, which is this defect exactly. The next destination is asked
the question beside the table it is being added to, rather than in two
conditionals 4,000 lines away that name a destination it is not. That is the
same reasoning `mineral_value` v1.7.1 applied to its own silent default.

### Verification

**Six of the seven destinations are bit-identical by construction**, since
`window_phasing_au` returns exactly the `1.0` or `A_MARS_AU` the conditional
returned for them; the resolved value was checked for all seven.
`verify.py check --tag 1.17.7` passes: all four cislunar cells **139/139
columns identical**, hashes MATCH, mass ledger `0.000000000 kg`, never-worse
clean.

**`mars_orbit` changes, and that is the point.** No `mars_orbit` cell has ever
been run, so no committed measurement moves; every prediction made for it in
[calc v1.18.0](#calc-v1180--mineral_value-v180--transportation-v1130) that
touches cadence, span or the rig bounds should be read against Mars phasing
now.

## calc v1.19.1

**No number moved.** Console output only: no CSV byte changes, and the four
cislunar cells are bit-identical.

**`stamp_check` had been crying wolf on every run since v1.17.8 shipped it two
releases earlier, and the action it recommended was the destructive one.**

The check compares the `pipeline_version` stamped in an upstream CSV against
the module that wrote it, so a write that silently failed to land is caught on
the next run. That is what it was for. What it actually did was compare **every
frame in `catalogs`** against `TRANSPORT_CONFIG`, and that dict holds
`asteroids` (written by Module 1) and `minerals` (Module 2) alongside the four
Stage 3 tables. A Module 1 version can never equal a Module 3 version, so:

```
     WARN  Module 3 catalog was written by a DIFFERENT transportation build
          * asteroids.csv stamped 1.1.0
          * minerals.csv stamped 1.7.1
        -> Re-run Stage 3 (transportation) before trusting any number below
```

Three things wrong, and the third is the one that matters:

1. **The wrong comparand** for two of the six files.
2. **The wrong remedy named.** Re-running Stage 3 cannot change what Module 1
   stamped into the asteroid catalog.
3. 🚨  **The remedy is the single most destructive action in this repo.**
   CLAUDE.md carries a section titled "RUNNING STAGE 2 OR STAGE 3 DESTROYS
   EVERY BASELINE YOU HOLD", written after somebody did exactly that on
   2026-08-23 and could not get the prices back. So a check written to enforce
   the version discipline was, on every single run, advising the reader toward
   an irreversible refetch, for two files it was misreading.

**A check that cries wolf toward a destructive remedy is worse than no check**,
and this is the same family as the harness bugs in
[what "no number" claims rest on](#what-no-number-claims-rest-on): a broken
checker looks exactly like a broken release.

### What it does now

`_CATALOG_PROVENANCE` maps each catalog key to the stage that writes it and the
config global carrying that module's version, and `load_all_catalogs`
**asserts** the map names exactly the catalogs it builds. The assert is in the
loader rather than in the check, because the loader is where the two can drift:
that dict is the definition and the map is the description, and a catalog added
without a map entry would otherwise be silently unchecked forever. A key with
no entry is now reported rather than skipped.

The wording changed as much as the logic. It names the right stage per file, and
it reports rather than instructs:

```
     WARN  6 upstream CSV(s) were written by a different build of the module
           that owns them:
          * asteroids.csv stamped 1.1.0 - Stage 1 in this process is 1.1.1
          * minerals.csv stamped 1.7.1 - Stage 2 in this process is 1.9.0
          * propellants.csv stamped 1.12.1 - Stage 3 in this process is 1.14.0
        -> This may be DELIBERATE. Several releases changed no CSV byte and
           chose not to re-run their stage; read the release note first.
        -> If you do re-run Stage 1, 2 or 3, it REFETCHES and overwrites the
           only copy of its CSV, and every verify.py baseline stops
           reproducing. Copy asteroid_pipeline/*.csv first.
```

⚠️  **It still fires on the current tree, and that is now correct.** catalog
v1.1.1 and transportation v1.12.1 both changed no CSV byte and deliberately did
not re-run their stage, and v1.13.0 / v1.14.0 added reference rows on the same
call. **The check cannot tell a deliberate lag from a write that failed to
land**, because both look like "the file predates the module", so it states the
fact and says where the answer is instead of prescribing a fix it cannot
justify. That limit is now in the docstring rather than discovered by the
reader.

The two documented limits are unchanged: it is a **diagnostic, not an import**,
so a standalone `calc.py` run where the upstream configs do not exist skips
each comparison silently rather than inventing one; and it still cannot see an
edit that did not bump a version.

**Verified**: `verify.py check --tag 1.17.7` passes, all four cislunar cells
139/139 identical, hashes MATCH.

⚠️  **Noticed and deliberately not taken**, so nobody finds it and assumes it
is a bug: v1.19.0 added `_V_LEO_KM_S` and `_V_ESC_LEO_KM_S` at module scope for
the GEO capture, and `_leo_departure_dv_km_s` and `_cislunar_capture_dv_km_s`
still derive the same two values inline, so there are now three copies of
`sqrt(mu / R_LEO)`. They **cannot drift**, being one expression over one
constant rather than the two-place derivations CLAUDE.md's defect class 4 is
about, and consolidating them is bit-safe because hoisting an identical
expression re-associates nothing. It is left alone because it is a performance
change to the hottest function in the model, worth two `sqrt` per call, and
this repo's rule is that those go in their own measured release rather than
inside one arguing bit-identity.

## calc v1.19.0 / mineral_value v1.9.0 / transportation v1.14.0

**No number moved, and nothing has been measured yet.** A seventh
`delivery_destination`, `geo`, and no value at any of the six that existed.
**No `geo` cell has been run.**

**It is the only destination in this model with a paying customer today.**
Roughly 550 active geostationary satellites, and MEV-1 and MEV-2 have docked
with and station-kept commercial GEO spacecraft for real money. Every other
destination in the table is an architecture study.

### Two plane changes, and they must not be reconciled

GEO is the first destination that pays for **inclination**, and the model
carries two different figures for what is nominally the same apogee burn:

| the burn | plane change | Δv |
|---|---|---|
| coplanar, for reference | 0 deg | 1,477 m/s |
| a kilogram **arriving** from an asteroid | 23.44 deg, ecliptic to equator | **1,730 m/s** |
| a kilogram **launched** from Earth | 28.5 deg, a Canaveral parking orbit | **1,836 m/s** |

Module 2 prices the launched kilogram, because launch cost avoided is what
in-space material is worth; Module 4 prices the arriving one. **Making them
agree would put a launch site's latitude into an interplanetary trajectory.**
Both are combined by the law of cosines rather than added, which is the other
thing intuition gets wrong here: a burn that changes speed and direction at
once costs less than doing both separately.

### Capture is a search, because neither route always wins

`_cislunar_capture_dv_km_s` has one answer. `_geo_capture_dv_km_s` prices two
and takes the cheaper:

| v_inf | direct capture at GEO | Oberth at perigee, then circularise |
|---|---|---|
| 1 km/s | **2.046** | 2.545 |
| 3 km/s | **2.749** | 2.901 |
| 5 km/s | 3.997 | **3.582** |

**The crossover is at v_inf = 3.585 km/s**, and the reason is the apogee burn.
A cislunar depot is captured into by *binding* an ellipse, 450 m/s. GEO has to
be *circularised* into, which is four times that and does not fall with
arrival speed, so the Oberth benefit has less to work with. Cislunar remains
the cheapest destination to reach from an asteroid: 0.96 km/s against GEO's
2.05 at best.

⚠️  **Aerocapture here is not an aerobrake trim.** At LEO drag does the whole
job and the propulsive residue is 100 m/s; at GEO drag can only lower the
apogee, and circularising there is still **1.737 km/s** of real burn, flat in
v_infinity. Copying `DV_AEROBRAKE_TRIM_KM_S` across would understate a GEO
arrival by 17x.

### The market is the narrow one, and the argument is new

`geo` is priced at **$12,526.34/kg**, between cislunar and mars_orbit. What
separates it is the utility table, and it is **the first destination whose
overrides run downward on the metals and the rock rather than on the
volatiles**:

| | at `geo` | at `cislunar` |
|---|---|---|
| water | 0.80, **$10,021/kg** | 1.00, $10,810/kg |
| iron | 0.15, **$1,879/kg** | 0.70, $7,567/kg |
| olivine | 0.05 | 0.25 |
| carbon | 0.05 | 0.40 |

✅  **That is a different ARGUMENT from the lunar and martian blocks, not a
different number.** Those are about local **supply**: a settlement standing on
a crust digs up its own water and iron, so imported material competes with
local mining. Nothing is mined at GEO and nothing ever will be. These
discounts are about local **demand**, which is the other half of what the
table means. Utility is "how good a substitute 1 kg of this is for a
**launched** kg here", and nobody launches a kilogram of copper to
geostationary orbit: there is no factory 36,000 km up, no crew, and no
construction site. So GEO is a volatiles destination and nothing else.

Ni / Co / Cu are discounted here where the two surfaces deliberately leave
them alone, and that is the same distinction: those overrides are about there
being no local **ore**, this one is about there being no local **factory**.

**Demand is 40,000 kg/yr**, the only row of that table anchored on hardware
that exists: ~550 satellites at roughly 70 kg/yr of station-keeping
propellant. That makes it the smallest in-space market in the model and the
one most likely to saturate, **which is the point of having it**.
`earth_surface` is the destination where saturation is numerically inert and
100% of rows run to the fleet ceiling, and nothing anchored the other end.

### Verification, and one thing not measured

Across a 270-point grid of orbital elements, a 0.6-5.2 AU x e 0.0-0.95 x
i 0-80 deg, **6,930 pre-existing leg values compare bit-for-bit against
v1.17.8 with zero mismatches**, with `geo` and `mars_orbit` contributing four
new keys and nothing else. The six existing destinations reprice to the cent.

✅  **`verify.py check --tag 1.17.7` passes with both destinations in
place**: all four cislunar cells **139/139 columns identical** and hashes
MATCH (`4184f13cf57a6df7` / `66d88054984b014a` / `b88b5dac5d2fe43d` /
`2a4f610ec97bf6f2`), mass ledger `0.000000000 kg` on all four, never-worse
clean at the committed medians (+39.5% beneficiated, +42.5% searched), and
Stage 2's 31 rows recompute identically at cislunar. That is the end-to-end
form of the grid check above: adding a destination moved nothing.

⚠️  **The per-row cost of the new legs is NOT established, and the honest
answer is that the A/B did not resolve on this host.** `_transfer_legs_for_apsis`
computes every destination's legs unconditionally, as it always has, so a
cislunar run now derives a GEO capture it will never read. In isolation
`_geo_capture_dv_km_s` measures a stable **1.29 us per call** and runs twice
per row, which bounds the addition at roughly **3-4 us/row, ~5 s on a full
1.55 M-row pass**, against a 733 s raw cell. But the end-to-end A/B swung
between 1.22x and 2.35x across fifteen alternating passes, and **the unchanged
build alone varied 2x between passes inside one process**, so no ratio from it
is worth committing. THE SAMPLING RULE's cousin: a benchmark whose control
moves 2x is not measuring the treatment.

Making the legs conditional on the destination is the obvious fix if it turns
out to matter, and it is deliberately **not** taken here: it changes control
flow in the hottest function in the model, and belongs in its own measured
release rather than inside one whose whole claim is that it moves no number.

## calc v1.18.0 / mineral_value v1.8.0 / transportation v1.13.0

**No number moved, and nothing has been measured yet.** This release adds a
sixth `delivery_destination`, `mars_orbit`, and changes no value at any of the
five that existed. **No `mars_orbit` cell has been run**; the figures below are
derivations and table entries, not results, and the 20-cell campaign is
untouched.

**A depot in Mars orbit is the same heliocentric transfer as `mars_surface`,
stopped one leg early**, which is why it costs three tables and two return legs
rather than a new transfer model. `_asteroid_to_mars_dv_km_s` already computed
the arrival at Mars; what is new is a capture into a **1-sol elliptical
staging orbit** (250 x 33,793 km, NASA DRA 5.0) instead of a circularisation
into a 200-km one, and no descent after it.

The orbit is chosen on the argument NRHO is chosen on in cislunar space:
capture only has to **bind** the ellipse, and the burn happens deep at
periapsis where Oberth pays. Its period is 24.60 h against a sol's 24.62.

| at a Hohmann arrival, v_inf 2.65 km/s | Δv |
|---|---|
| capture into the 1-sol orbit | **0.90 km/s** |
| circularise into a 200-km orbit | 2.10 km/s |

That 2.10 reproduces Module 3's independently-sourced "Low Mars orbit → Earth
(TEI)" figure of 2,100 m/s from the geometry, which is the cross-check that the
0.90 is right too.

**What separates the two Mars destinations is four things, and only the first
is Δv:**

| | `mars_orbit` | `mars_surface` |
|---|---|---|
| launch cost avoided | **$13,496/kg** | $45,105/kg |
| kg in LEO per kg delivered | **3.17** | 10.61 |
| entry-survival fraction | none, nothing enters | 0.30 (MSL / Perseverance) |
| return vehicle | berthing adapter, $60k/kg | lander, $200k/kg |
| downleg to Earth | 900 m/s, **$30,150/kg** | 6,200 m/s, $96,394/kg |
| utility profile | **the base one** | the ISRU-discounted one |

✅  **The last row is the point of the destination.** The `mars_surface`
overrides exist because a settlement standing on a crust digs up its own water,
iron and rock, so asteroid material competes with local mining. A depot in a
1-sol orbit competes with nothing of the kind: everything martian is 3,400 km
down a well that costs 4,100 m/s of ascent to climb, which is **more than the
3,600 m/s of TMI that brought the cargo from Earth**. So the alternative to
importing a kilogram there is launching that kilogram from Earth, which is the
exact condition `IN_SPACE_UTILITY`'s base profile is calibrated on, and
`IN_SPACE_UTILITY_BY_DESTINATION["mars_orbit"]` is deliberately `{}`.

⚠️  **The empty dict will read as an oversight next to the block below it, and
copying `mars_surface`'s overrides up into it would destroy the destination's
meaning.** The ISRU discount that carries the `mars_surface` result is not a
property of Mars; it is a property of being **on** Mars, and this destination
is the control that says so.

The downleg row is the second consequence. A commodity with no in-space market
is valued by flying it home, and from the surface that route costs more per
kilogram than any price in the catalog, so the PGMs are worth **zero** at a
Mars base. From orbit the same kilogram routes home for $30,150 and they are
worth something again.

**Verified bit-identical where it has to be.** `_asteroid_to_mars_dv_km_s`
gained two keys and no arithmetic was re-associated; across a 270-point grid of
orbital elements spanning a 0.6-5.2 AU, e 0.0-0.95, i 0-80 deg, **6,930
pre-existing leg values compare bit-for-bit against v1.17.8 with zero
mismatches**, and the only difference is the two added keys. Stage 2's five
existing destinations reprice to the cent.

✅  **`verify.py check --tag 1.17.7` passes**, all four cislunar cells 139/139
identical with hashes MATCH; the full result is recorded under
[the `geo` release](#calc-v1190--mineral_value-v190--transportation-v1140),
which was verified with both destinations in place.

⚠️  **Two re-runs are owed before this destination can be measured, and both
destroy baselines.** Stage 3 must be re-run for the three new Δv rows to reach
`delta_v_segments.csv`; Stage 2 must be re-run at `--destination mars_orbit` to
price a catalog for it. Both re-fetch. Copy `asteroid_pipeline/*.csv` first; see
CLAUDE.md, "Running Stage 2 or Stage 3 destroys every baseline you hold".

⚠️  **Neither is urgent, because nothing downstream reads the Δv table.**
Module 4 derives every Δv it uses from orbital elements; `DELTA_V_REFERENCE` is
the citation home and the cross-check, which is why the three new rows are
there. `mars_orbit` is fully usable against the Stage 3 CSVs as they stand.

❗  **Found while checking that claim: `stamp_check` has been crying wolf since
calc v1.17.8 shipped, and the action it recommends is the destructive one.** It
compares `TRANSPORT_CONFIG.pipeline_version` against **every** frame in
`catalogs`, including `asteroids` (1.1.0) and `minerals` (1.7.1), neither of
which can ever equal a transportation version, and then prints "Re-run Stage 3
(transportation)". A check written to enforce the version discipline therefore
recommends, on every run, the one action CLAUDE.md documents as destroying every
baseline you hold. It fired before this release and is not caused by it. Not
fixed here: a version-stamp check is not a delivery destination, and mixing them
would put a behaviour change inside a release whose whole claim is that it moves
no number.

## calc v1.17.8

**No number.** Four cells 139/139 columns bit-identical against the committed
v1.17.7 baseline, all four hashes MATCH. The stamp moves so a catalog still
names the code that built it.

Closes the **value half** of the upstream-staleness hole `CLAUDE.md` has listed
as open since v1.14.0. `schema_check()` asks whether the Module 3 columns and
rows this version reads are PRESENT; it passes cleanly on a catalog whose
**values** are a release out of date, because editing a density, a status or a
boil-off rate leaves the schema identical.

🚨 **That is not a hypothetical, and it has already cost a full measurement
pass.** During v1.12.0 the argon rows were rewritten, Stage 3 was re-run, the
CSV did not actually land, and two full-catalog runs plus a determinism sweep
were measured against the table that was being replaced. Nothing anywhere said
so. The documented mitigation was to read Stage 4's row counts against what
Stage 3 reported writing, by eye, on every run: the kind of habit that works
until the day it matters.

`stamp_check()` compares the transportation `pipeline_version` **stamped in
each Stage 3 CSV** against the Module 3 in this process. It needed no new
column, because Stage 3 has stamped its output all along and nothing had ever
read it back. What it really does is turn *"changing any number a run produces
means bumping"* from a rule someone has to remember into one the loader
enforces on the way past.

⚠️ **It is a diagnostic, not an import.** `TRANSPORT_CONFIG` exists only when
both modules share a process, which is `master.py`, the normal path. A
standalone `calc.py` run cannot know what Module 3 currently says, and it stays
silent rather than inventing a complaint it cannot support: the modules hand
off through CSVs on disk and must not grow an import edge for a warning.

⚠️ **It cannot see an edit that did not bump the version.** The rule is
one-directional, so a value changed without a bump still passes. What this
closes is the case where the discipline was followed and the write silently did
not land, which is exactly the v1.12.0 failure.

## mineral_value v1.7.1

**No number.** All 31 rows of the Stage 2 catalog recompute identically, and the
four Stage 4 cells are bit-identical. The stamp moves so a catalog still names
the code that built it.

The first audit pass Stage 2 has ever had, and it found one thing. A commodity's
share of a depot's import budget is looked up as
`_COMMODITY_CLASS.get(name, "shielding")`, and three rows had no entry, 
**sperrylite (PtAs₂), laurite (RuS₂) and native-pgm**. They were taking the
shielding share, **15% of a destination's entire import budget**, where the
eight PGM *elements* all take the trace slice at **0.05%**. That is 75,000 kg/yr
at LEO against 250, a factor of 300, for the ore minerals of exactly those
metals.

It is inert today, and that is why it survived: their in-space utility is 0.0 at
every destination, so the price router always ships them to Earth and the class
is never read. But the settlement catalyst market that would make it reachable
is recorded in `CLAUDE.md` as *considered and rejected*, not impossible, so
this is the same shape as the RTG branch: **an unreachable branch is not a
verified branch.** Reclassified to trace, with an assert that now fails at
import if any commodity is unclassified.

Measured and deliberately not fixed: **`nickel-iron` has no terrestrial market
ceiling**, so at `earth_surface` it never saturates, and it is one of only four
phases Stage 4 sells. Correcting it to world pig-iron production moves the
saturation multiplier by 7.7×10⁻⁸ at one mission's output and 7.7×10⁻⁵ at
programme scale: nothing, but enough to break bit-identity on a destination that
had not been re-measured since calc v1.14.0.

⚠️  **Two days later it was, and that re-scopes the item rather than closing
it.** The 2026-08-24 campaign measured all four `earth_surface` cells, and it
also found that market saturation is **numerically inert** there, the
multiplier departs from 1.0 by a median of 2.3e−11, so 100% of rows run to the
fleet ceiling. Costing a missing ceiling against a *single mission's* multiplier
was therefore the wrong scope: with the search on, a missing ceiling changes the
**shape** of the objective in N rather than its level, and a shape change has no
size. Still not fixed, and if `earth_surface` is ever re-measured for another
reason, take it in that pass.

Stage 1 was audited in the same pass and needed no changes. Its taxonomy table
covers the real population to **99.997%**, of 75 distinct spectral types across
1.55 M rows, only `Z` (36 rows) and `U` (4) resolve to neither an exact entry
nor the root-letter fallback. **53 rows in total (0.0034%)** end with no
`comp_metal_fraction` and are skipped by Stage 4, and the cascade fails safe by
excluding them rather than mispricing them: an unresolved type lands on
`TAXONOMY_COMPOSITION["Unknown"]`, whose fractions are `None`.

## calc v1.17.7 / transportation v1.12.1

**No number, and for once that is not the point.** Every stamp before this one
went after cost, or a default, or dead code. This one fixes a **defect**, and
one that no cell in this repo could have shown, because the run that shows it
has not been made since v1.16.0.

**A cache grew without bound.** `_CALENDAR_CACHE`, the hand-rolled dict this
release replaced with `_calendar_multipliers_cached`, memoised a pair of
programme calendar multipliers on `(campaigns-per-ship, cadence, WACC)`. The first two of
those are small; the third, `cadence`, is `max(stay, synodic period)`, a fresh
float for **every candidate mission**. So unlike every other memo in the module,
which reaches a ceiling and sits there, this one grew **linearly with the
catalog**: ~45 entries per catalog row, or 3,983 / 17,729 / 36,071 entries at
caps of 100 / 400 / 800 rows. On a full-catalog default cell that projects to
**~70 million entries and 11-18 GB**, against a documented run peak of ~6 GB.

**The retention was buying 0.1 pp.** Replaying the real 223,538-call sequence
through bounded LRUs, all reuse turns out to be local to one candidate mission, 
v1.17.5's per-candidate rig cache already absorbs the cross-option traffic:

```
unbounded     hit rate 83.9%   retained 36,071 entries
maxsize 1024  hit rate 83.9%   retained  1,024 entries
maxsize   64  hit rate 83.8%   retained     64 entries
```

Now `functools.lru_cache(maxsize=1024)`, confirmed flat at 1,024 entries at
every cap with the hit rate unchanged. **This cannot change an output value by
construction rather than by rounding**; it is a memo of a pure function, so
evicting an entry only forces recomputation of the identical float. That makes
it the one shape of optimisation this project can take for free, unlike the
arithmetic reorderings it has repeatedly declined. It is also *faster*:
`lru_cache` hashes in C, 180 → 91 ns per hit, and bounding costs nothing against
`maxsize=None`.

**Two smaller items.** `_load_csv` now reads with `low_memory=False`: not for
memory, but because the default reader infers dtypes from *chunks*, so the dtype
depends on how values fall across them, and it emitted a `DtypeWarning` on every
single load (a warning that always fires is one nobody reads). Measured neutral
first: 0 of 46 columns change dtype or value. And in Stage 3, the two propellant
sanity bands selected rows with `.astype(bool)` on a flag that reads `NaN` as
**True**, so a future propellant row omitting it would be silently classed as a
sail and dropped from both checks, the trap this repo already documents, in the
one place it had not been fixed. It is now `.ne(True)`, which is total across
both dtypes; the obvious `.fillna(False).astype(bool)` was written first and
rejected, because pandas raises a deprecation warning on the object path, that
is, exactly when the fix would fire.

Verified with the newly committed `verify.py` rather than a harness rebuilt from
memory; see [Verifying a change](README.md#verifying-a-change), and note that writing
that file turned up **five** fresh harness bugs of its own, three of them
producing the identical "columns DIFFER against a byte-identical hash" symptom
from three unrelated causes.

## calc v1.17.6

**No number.** A performance release on the same contract as v1.10.1, v1.14.1,
v1.14.2, v1.17.1, v1.17.2, v1.17.4 and v1.17.5; the stamp moves so a CSV still
names the code that produced it, and every measured cell stands as measured.

Three releases in a row went at the **programme ladder**. This one goes at the
**per-row walk**: the work every one of 1,555,618 catalog rows pays whether or
not it turns out to be evaluable, which makes it the first performance stamp
here worth more on the *raw* cell than on the default one.

**Composition is a per-taxonomy fact, and it was being derived per row.** The
three functions that price an asteroid's material: the bulk blend, the phase
table and the purity ceiling; read five values off the row and nothing else,
and all five come from Module 1's taxonomy: 76 spectral types collapse to about
**25 distinct composition tuples across 1.55 million rows**. They were walking
the mineral table three times per asteroid, with a `pandas.isna` on a scalar per
entry, to re-derive one of a couple of dozen answers. Memoised on the
composition: **14.84 → 1.21 µs**, **13.97 → 1.25 µs** and **27.66 → 1.28 µs**
per row, or ~88 s off every full beneficiated pass. This is the same finding
v1.17.4 made on *both sides* of the CSV boundary, now found in the place between
them: **a column with few distinct values and one Python call per row.**

**Six smaller items, all the same sentence.** The refusal helper inside the
rocket-equation solver was a nested `def`, rebuilt on all ~500,000 calls of the
hottest function in the model (~5% of it). The programme ladder itself is a
function of the rig's trip life and the config, and was being rebuilt per
candidate (~3.6% of the default cell). The vehicle's LEO capacity was derived in
three separate places, once per candidate, for seventeen numbers fixed for the
run. The Δv options, the per-propellant constants, and five reliability table
rows were each asked for at a finer granularity than they have answers.

| cell | HEAD | **v1.17.6** | speed-up | per-row |
|---|---|---|---|---|
| raw, 6,000 rows | 18.61 / 19.15 s | **16.28 / 16.14 s** | **1.14-1.19×** | **1.15×** |
| beneficiated, 800 rows | 13.49 / 13.73 s | **12.96 / 12.81 s** | **1.04-1.07×** | **1.05×** |
| raw + search, 3,000 rows | 16.71 / 16.58 s | **14.42 / 14.33 s** | **1.16×** | **1.18×** |
| beneficiated + search (default), 800 rows | 22.81 / 22.55 s | **20.51 / 20.45 s** | **1.10-1.11×** | **1.12×** |

Interleaved A/B, both builds in one process, cells alternated, best of 3, run
twice.

🚨 **This is the first release here whose ratio depends on the row cap, and
the caps above are deliberately large.** At the 150/400-row caps every previous
release measured itself on, the same build honestly reads **1.03-1.10×**; a
capped run pays a fixed ~1.6 s of catalog integrity check and pre-filter probe
that does not move and does not scale. **Quote the cap with the ratio.**

Verified the way every release here is: four cells 139/139 columns bit-identical
against HEAD with sha256 MATCH (less both provenance columns), and the four
hashes are the ones v1.17.4 committed, so they now reproduce across two
releases; pre-filter on vs off identical on all four; serial vs 8 workers
byte-identical on the two searched cells, matching v1.17.4's committed hashes;
mass ledger exact at 0.000000000 kg; both never-worse invariants holding with
zero exceptions, the searched-vs-unsearched median landing on +42.5% against the
committed full-catalog +42.4%.

## calc v1.17.5

**No number.** A performance release on the same contract as v1.10.1, v1.14.1,
v1.14.2, v1.17.1, v1.17.2 and v1.17.4; the stamp moves so a CSV still names
the code that produced it, and every measured cell in this project stands as
measured.

Third release in a row aimed at the **programme ladder**, which is where
v1.17.0's default flip put the work: it prices a median of ~42 programme
options for every candidate mission, so anything re-derived per option is
re-derived forty times to change three numbers.

**One cache entry now carries the whole W-dependent block.** The rig cost
shares and the programme-calendar multipliers are a function of how many
campaigns one rig flies, of W, and of a prologue that is fixed for the
candidate. They are not a function of N. With W running `1 … trips` and
`trips` capped at 5, ~42 options were asking for at most ten distinct answers.

🚨 **CLAUDE.md had already measured this item and declined it at 3.2%.** What
moved it over the bar was not a re-measurement but the *neighbour*: the
calendar multipliers sixty lines below share the same key, and v1.17.4 had just
memoised them separately. Folding both into one entry makes the second lookup
disappear rather than survive. **Price the block, not the line.**

**Three smaller items, all of them repetition rather than arithmetic.** The two
O(N) memos (`learning_curve_factor`, `mining_success_probability`) were building
their dictionary keys in Python: two conversions and a tuple allocation before
the lookup started, at 455,094 calls apiece, and now hash in C via
`functools.lru_cache`: 159 → 92 ns and 249 → 131 ns. `_objective_key` ran
`str(x).strip().lower()` on all 457,776 calls to re-derive one boolean from a
config field fixed for the run. And `isru_feed_kg_per_kg_propellant` re-answered
a per-*propellant* question once per candidate: four rows in five fall through
to a legacy name test, a string normalisation plus a substring scan, to
conclude "no".

| cell | HEAD | **v1.17.5** | speed-up |
|---|---|---|---|
| raw, search off | 1.186 s | **1.175 s** | **1.01×** |
| beneficiated, search off | 2.260 s | **2.256 s** | **1.00×** |
| raw, search on | 2.262 s | **2.127 s** | **1.06×** |
| beneficiated + search (the default) | 4.283 s | **4.029 s** | **1.06×** |

Interleaved A/B, both builds in one process, cells alternated, best of 4.

🚨 **This is the smallest performance stamp in the project, and the flatness is
the finding.** Every item removes work that only exists when a ladder exists,
so both search-OFF cells are inert and should be. Six perf releases have now
run through this search; what is left in the ladder is per-option overhead
measured in tens of nanoseconds. **Do not expect another 1.5× from this path.**
(v1.17.6 did not get one from it; its 3.6% ladder item is the ladder being
*rebuilt* per candidate, not anything inside a rung.)

Verified the way every release here is: four cells 135/135 columns
bit-identical against HEAD with sha256 MATCH (less both provenance columns, 
`pipeline_version` *and* `catalog_date`); pre-filter on vs off identical on all
four; serial vs 8 workers byte-identical; mass ledger exact at 0.000000000 kg;
both never-worse invariants holding with zero exceptions.

**Also: one dead constant removed** (`AU_KM`, unreferenced across all four
modules, `ui.py`, `ui_meta.py` and `build_master.py`), and a fresh mechanical
scan of every top-level definition, dataclass field and import found nothing
else, v1.17.3's conclusion holding one release later.

## calc v1.17.4 / catalog v1.1.1

**No number.** A performance release on the same contract as v1.10.1, v1.14.1,
v1.14.2, v1.17.1 and v1.17.2; the stamp moves so a CSV still names the code
that produced it, and every measured cell in this project stands as measured.

Two findings, in the two places five previous performance releases never
looked: the **catalog load**, and **pass 2** of the sizing loop.

**Nobody had profiled the load.** `comp_minerals` is a list-column that pandas
reads back as a string, and Stage 4 was `ast.literal_eval`-ing it once per row.
Composition is assigned from the spectral taxonomy, so that column takes **25
distinct values across all 1,555,667 rows**: 1.55 million parses to produce
twenty-five answers, costing more than the 862 MB CSV read in front of it.
`integrity_check` then walked the same 1.55 M lists to build a set of fourteen
names. Both now go by distinct value: **13.0×** on the parse, **3.2×** on the
walk, and the parsed column verified identical element for element.

**The pre-filter refuted at pass 1 and never asked about pass 2.** v1.14.1's
filter is sound and its argument is that pass 1 is the loop's most optimistic
pass. Measured on the real population, of 219,054 candidate solves **162,816
(74.3%) die on pass 2**: the first pass that flies the electric stage pass 1
has just sized, which on an electric mission is tonnes. That stage is the same
at every concentration ratio and every power source, so the identical
refutation was being re-derived 8 to 16 times. Asking once per (vehicle ×
propellant × Δv × ISRU) cuts candidate solves **219,054 → 32,342** and cascade
solves **500,860 → 183,677**.

🚨 **It is a decision, not a bound.** Viability is monotone decreasing in
`hardware_kg` and in `r_ret`, and both only grow from pass 1 to pass 2; the
plant is ≥ 0, and the hold is floored at `station_keeping_floor_yr`. Nothing is
approximated, which is what separates this from the branch-and-bound on the
objective that CLAUDE.md still warns against.

| cell | HEAD | **v1.17.4** | speed-up |
|---|---|---|---|
| raw, search off | 1.854 s | **1.223 s** | **1.52×** |
| beneficiated, search off | 4.901 s | **2.486 s** | **1.97×** |
| raw, search on | 3.160 s | **2.369 s** | **1.33×** |
| beneficiated + search (the default) | 6.533 s | **4.157 s** | **1.57×** |
| *load + integrity check* | *30.38 s* | ***15.36 s*** | ***1.98×*** |
| *row → dict walk, per row* | *61.0 µs* | ***17.7 µs*** | ***3.44×*** |

Interleaved A/B, both builds in one process, cells alternated, best of 3.

**Every row was converted through a pandas Series it did not need.** Both the
serial loop and the workers walked the catalog with `iterrows()`, and
`_row_to_dict` threw the Series away: 61 µs a row against **17.7 µs** for
`to_dict("records")` over a 256-row block. That is ~50 µs on every catalog row
whether or not it is evaluable, so ~67-78 s a pass, about **5-6% of the raw cislunar
cell**. Value- and type-preserving, checked cell by cell over 20,000 rows.

**And the same finding upstream, shipped as catalog v1.1.1.**
`enrich_composition` resolved everything keyed on `spectral_type` once per row,
nine composition fields, two capitalisation passes, the PGM multiplier, twelve
`.apply()` passes making ~19 M Python calls to produce the ~800 answers that 76
taxonomy classes can give. **9.09 s → 2.35 s**, all 12 derived columns
identical. It is the *same column* Stage 4 fixes at the other end of the CSV
boundary, which is the useful part: the pattern to look for is **a column with
few distinct values and one Python call per row**, and this pipeline had it on
both sides of its own output file.

🚨 **Two fast options were measured and rejected.** `pd.read_csv(engine=
"pyarrow")` takes the 862 MB read from 17.9 s to **3.7 s** with identical
dtypes, and rounds floats differently in the last ULP, moving
`estimated_mass_kg` by a relative 1e-13. Physically nothing, and fatal: mass is
what the ranking runs on and every release here is argued from bit-identity.
And `builtins.max` is **not** worth inlining; the "~6× cheaper" figure this
project has quoted since v1.14.2 is stale, because Python 3.13 specialises
two-argument `max`; re-measured it is 1.2-2.4×, so the whole item is ~0.6%.

⚠️ **The shape is the opposite of v1.17.2's.** That release is inert with the
search off and worth 1.45× with it on, because it removes ladder work; this one
lands on the mass cascade, so it is worth most where there is *no* ladder. And
the load saving does not scale with the row cap at all; it is half the wall
clock of a 400-row cell and 0.2% of a full beneficiated one. **A single ratio
for this release is meaningless without the row count.**

Verified: four cells 139/139 columns bit-identical with sha256 MATCH; prune on
vs off and stage 2 active vs neutralised both identical on all four; serial vs
8 workers byte-identical with the search on; mass ledger exact; both
never-worse invariants hold. And pairwise, **every one of 20,533 tuples the
new stage killed was then solved in full at every power mode and every ratio,
and none produced a mission.** That last check is the one that matters: a
filter that is too tight drops a candidate without changing any row count, so
no output diff could see it.

## calc v1.17.3

**No number, and nothing was meant to get faster either**: a cleanup stamp.
Two dead functions removed, two live duplications collapsed to one definition
each. calc `1.17.2 → 1.17.3`, master `1.20.2 → 1.20.3`.

**Two functions had no caller.** `low_thrust_burn_time_yr` and
`asteroid_dv_m_s`, neither referenced in four releases across all four modules,
`ui.py`, `ui_meta.py` and `build_master.py`. ⚠️  The first one's section comment
carries the **Dawn validation** and was kept, re-anchored on
`ep_power_required_w`, the same relation solved for power rather than time.
Do not delete the comment because the function under it went.

🚨 **`tank_frac` was still derived twice, and a note said it was not.** v1.14.2
recorded "one derivation now, two readers" and had in fact *moved* the second
copy: two functions each divided `tank_kg_per_L` by `density_kg_per_L`, ten
lines apart, the second under a comment saying it matched the first "exactly".
One `_tank_frac_per_kg` now. The shape is worth more than the fix, **a note
that documented an intention as an accomplishment**, which survived a release
whose entire argument was bit-identity, because nothing a hash can see was
wrong. *Check that a de-duplication claim names ONE surviving definition before
believing it.*

The phase walk existed three times; two of them now share `_phase_prices`.
⚠️  The third, `asteroid_bulk_value_usd_per_kg`, is deliberately **not** folded
in: it admits a fraction of exactly 0.0 where the other two skip it. Unifying
it would be numerically negligible and would still cost the bit-identity every
release here is argued from.

🚨 **This release found the `catalog_date` trap.** An earlier pass of the four
cells matched on 140 columns with only `pipeline_version` dropped; a later pass
reported the two *beneficiated* cells as differing, and the whole difference was
`catalog_date`; **midnight had fallen between the raw cells and the
beneficiated ones.** That reads exactly like a defect confined to the
beneficiation path. A CSV diff must strip **every** provenance column, and there
are two. A full beneficiated cell is hours, so a full-catalog 2×2 cannot be run
inside one calendar date and any comparison of those cells will hit this.

A mechanical scan found no unused imports, no unused config fields, no
unreachable statements and no duplicate top-level definitions in any of the
four modules. The remaining duplication in this codebase is semantic, not
structural.

## calc v1.17.2

**No number.** A performance release, second in a row aimed at the programme
ladder, which is where v1.17.0's default flip put the work. calc
`1.17.1 → 1.17.2`, master `1.20.1 → 1.20.2`.

🚨 **The headline is the shape of the table, not its best number.** This is the
first performance release in the project that is *inert* on some cells and
worth 1.45× on others:

| cell | HEAD | **v1.17.2** | speed-up |
|---|---|---|---|
| raw, search off | 1.928 s | 1.944 s | **0.99×** |
| beneficiated, search off | 5.052 s | 5.064 s | **1.00×** |
| raw, search on | 5.222 s | **3.597 s** | **1.45×** |
| beneficiated + search (the default) | 12.686 s | **9.250 s** | **1.37×** |

Both items remove work that only exists when a **ladder** exists, so a run with
the programme search off gains nothing and should not be expected to. Every
earlier perf stamp moved every cell. **Do not quote one number for this one.**

**`mission_cost_usd` was solving the same problem forty times.** The ladder
varies programme size and campaigns-per-ship and nothing else, yet the whole
cost cascade ran per option: ~10 `max()` calls, ~6 dict lookups, ~15 `float()`
conversions and a 22-tuple unpack, forty times over, to change three numbers.
Split into an N-independent prologue and an N-dependent tail.

🚨 **v1.17.1 named this change and refused it, on a claim that was wrong.** "It
re-associates the final sums" is true of a naive split and false of the
arithmetic as written: every N-dependent line factors as
`<N-independent base> * lc`, and Python already evaluates `a * b * lc` as
`(a * b) * lc`, so hoisting `a * b` into a name is the same two operations in
the same order. The three sums that genuinely interleave N-dependent and
N-independent terms are restated verbatim in the tail. **The tell was that a
mechanism had been asserted in prose with no line of arithmetic quoted next to
it.**

**The saturation sum is a function of fleet size and was priced per option.**
The ladder crosses fleet with campaigns-per-ship, so ~40 options run over ~8
distinct fleets and four passes in five re-derived a sum already made. Memoised
on the integer fleet, bit-identical by construction, since the same fleet
re-runs the same accumulation over the same list in the same order. That
matters more here than almost anywhere else: this is the sum v1.14.2 found to
be load-bearing on the last ULP.

⚠️  **Two things not to "fix".** The three interleaved sums must stay written
out term by term; pre-adding their N-independent members would re-associate
the addition, which is numerically negligible and fatal. And the prologue's
tuple order is load-bearing, unpacked in one statement at the top of the tail;
a field inserted in one place and not the other shifts every value after it,
and that would not change a row count.

## calc v1.17.1

**No number.** A performance release. calc `1.17.0 → 1.17.1`, master
`1.20.0 → 1.20.1`.

The finding is one sentence, and it is v1.17.0's own doing: **turning the
programme search on by default multiplied every per-call cost in the COST
cascade by forty.** Every previous performance release went after the mass
cascade, because until v1.17.0 `mission_cost_usd` ran once per surviving
candidate. It now runs once per programme option, and the ladder prices a
median of 40 of them.

Measured at cislunar on a 150-row beneficiated sample with the search on:
**8,057,499 calls to `_ops_value`**: 11.7% of the profile, looking up
**twenty-two numbers that never move**. That is v1.10.1's finding (the five
ops-table constants the sizing loop needs, looked up once per asteroid ×
vehicle × propellant × architecture × ratio) in the other half of the model,
six releases later.

What was taken: the 22 Stage 3 rows the cost cascade reads, memoised on the
frame's identity and unpacked in one statement; a `want_phase` short circuit in
the payload knapsack, whose dominant caller reads exactly one key and was
building the whole mix dict to discard it; the body's ice fraction hoisted onto
`AsteroidContext`; a `totals_only` early return, since the ladder compares
options on `total_cost` and reads the other ~39 keys only for the winner; the
rig trip life passed in rather than re-derived; and `delivery_architecture`
memoised, ⚠️  with the *warning* path deliberately not memoised, because that
loudness is the whole point of the warning.

| cell | HEAD | **v1.17.1** | speed-up |
|---|---|---|---|
| raw, search off | 1.704 s | 1.631 s | **1.04×** |
| beneficiated, search off | 5.950 s | **4.623 s** | **1.29×** |
| raw, search on | 5.989 s | **4.792 s** | **1.25×** |
| beneficiated + search (the default) | 14.504 s | **10.765 s** | **1.35×** |

The gradient across that table is the release in one picture: the cells that
gained least are the ones that call the cost model least.

🚨 **This release is where the interleaved A/B construction came from.** The
host swings ~20% run to run, so measuring two builds in separate processes
minutes apart is not a measurement; the first attempt reported the default
cell as **0.88×, a slowdown**, purely from drift. Every performance release
after this one imports both builds into one process and alternates the cells
A,B,A,B…, best of N.

⚠️  **A broken checker looks exactly like a broken release.** A parquet round
trip renders a `None` in an object column back as `nan`, so a naive per-column
`astype(str)` comparison reported three identical columns as differing.
Normalise the null representation, or trust the CSV hash, which is what caught
it here.

⚠️  **`totals_only` is an early return, not a second code path.** If a term is
ever added to `total_cost` *after* the diagnostics, the ladder silently starts
pricing on a different number from the one it reports. Keep `total_cost` final
before it, and note that failure would not change a row count, so only the
bit-identity diff would catch it.

## calc v1.17.0

**Two defaults, and nothing else.** No model term, coefficient, table value or
search axis moved, and an explicitly configured run is bit-identical to
v1.16.0. calc `1.16.0 → 1.17.0`, master `1.19.0 → 1.20.0`.

```
use_beneficiation         False -> True
optimise_programme_scale  False -> True
```

It is bumped anyway, because a *default* run's numbers change and the rule is
that changing any number a run produces means bumping.

**Why the flip is defensible now and was not before.** The standing argument
for keeping the programme search off was that a default flip "would silently
retire every committed figure at once **with no way to reproduce them**", and
the second half was the load-bearing part. It stopped being true once both
settings were measured side by side on the full catalog: the search-OFF cells
are recorded and reproduce exactly (26.7863× raw, 20.5895× beneficiated), so
the N = 1 answer is a recorded number rather than a lost one.

⚠️  **The two flags are not defensible on the same grounds**, and it is worth
keeping that straight:

- **`use_beneficiation` is weakly dominant by construction.** The search always
  also prices *not concentrating*, which is not the same as a ratio of 1.0, it
  declines the recovery loss and the array mass too, so turning it on strictly
  widens the option set and cannot make any row worse. Verified on 650,921
  pairs: max benef/raw **1.000000**, zero exceptions.
- **`optimise_programme_scale` is not dominant in that sense at all**: it
  changes the *question*, from "the best single mission to this rock" to "the
  best programme built around it". What makes it safe is narrower: v1.16.0 put
  (fleet, campaigns) = (1, 1) **in the search set**, so never-worse against
  N = 1 holds by inspection. Verified: zero worse, median improvement 42.4%.

⚠️  **Neither belongs on the list of things the model stopped giving away.**
They are questions, not subsidies being withdrawn. Since this release "it
defaults OFF" no longer carries half that argument, so the only test left is
**"was the model getting something for free before?"**, and for these two it
was not.

**What it costs.** Beneficiation and the programme search are close to
multiplicative, so a default run was roughly twenty times the raw
single-mission run almost every table was measured at. ⚠️  Those ratios have
since moved a long way; see [v1.17.7](#calc-v1177--transportation-v1121) and
the runtime table in the README. Both `master.py`'s and `calc.py`'s startup
summaries now print these two settings, because a multi-hour default run with
no explanation on stdout is how someone concludes the pipeline has hung.

⚠️  **Almost every table in this project is N = 1 raw, and a default run no
longer reproduces any of them.** That is a *labelling* problem, not a stale
number problem; the figures are right for the question they answer. The
one-line reproduction recipe for anything dated before 2026-08-11:

```python
CALC_CONFIG.use_beneficiation = False          # raw cells
CALC_CONFIG.optimise_programme_scale = False   # N = 1 cells
```

🚨 **`delivery_destination` did NOT move.** It still defaults to
`earth_surface` on both Stage 2 and Stage 4, so a genuinely configure-nothing
run is beneficiated + searched at `earth_surface`, which is the one cell in
the model that must not be read as an optimum, because market saturation is
numerically inert there.

## calc v1.16.0

**A programme took decades and was charged for none of them.** One correction,
inert at N = 1, verified as 141 of 141 columns identical, sha256 MATCH, with
the term on and off, so every measured cell in this project stands.

Stage 4 compounds a mission's up-front costs by `(1+W)^T` over that mission's
own duration. For one mission that is right. For a programme it assumes every
mission happens at once, and they cannot: one rig digs one hole at a time, so W
campaigns on a ship are strictly sequential. The lines that were being carried
free are the **amortised** ones, the bus NRE, the autonomy NRE and the rig, 
because those alone are bought once, at t = 0, and divided across missions that
sell years apart. A mission's own articles are unaffected: shift a whole cash
flow later and its cost/revenue ratio does not move.

The charge is a closed-form mean over the programme, exactly 1.0 at one campaign
per ship. **Salvage gets the reciprocal series**, because it is collected at the
*end*, compounding a refund forward alongside the cost it is netted against
would pay a bonus for taking longer to collect it.

**The cadence is the dig, or the launch window, whichever is slower**, and on
a 400-row raw cislunar sample **the window binds on 165 of 168 rows**. The rig
stays at the asteroid, so campaign w+1 starts as soon as w's feed is out of the
ground; but a capsule can only be dispatched when Earth and the target line up,
and a synodic period diverges as *a* → 1 AU. A NEA at 1.05 AU can only be
revisited every ~14 years however fast its rig works. A single mission pays that
wait once; a programme of W pays it W−1 more times.

🚨 **"A programme's pace is set by orbital mechanics, not mining rate" was drawn
from those 165 rows, and it INVERTS on the full population.** Measured at all
five destinations on 2026-08-24: it holds for **raw** everywhere (86-99.97%) and
is **false of beneficiated everywhere except Mars**: the dig sets the pace on
65.87% of `cislunar` rows, 74.63% of `leo` and **82.97% of `earth_surface`**,
because beneficiation is exactly the thing that makes the stay long. Mars is the
exception that proves the mechanism: its window is so long (99.95% binding raw,
still 63.18% beneficiated) that even concentrating cannot make the dig the
slower half. The claim was not wrong about the population it was measured on; it
was stated as though the population were the model.

**It retires the band argument and makes the programme search two-dimensional.**
v1.15.0 could ladder fleet size alone because within a band every lever improved
with N and none pushed back. Calendar time is the lever that pushes back, so
campaigns-per-ship became a real decision: fleet stays a ladder, campaigns-per-
ship is **enumerated exhaustively** (it is at most five integers). Measured on
the sample: the searched cell **31.0693× → 33.7977×**, median penalty 5.3%, no
row improved, median fleet **1 → 2 ships**, median N **5 → 10**.

✅  **Settled on the full catalog, 2026-08-11: campaigns-per-ship comes out
BELOW the rig's trip life on 2,077 of 650,921 rows (0.319%)** raw, and 1,389
(0.210%) beneficiated. So the dimension this release added is doing real work on
the real population: 2,077 bodies decline to use up the rig, because the
calendar charge outweighs what another campaign buys. It simply had no room to
show on 400 bodies, which is why this release could only record it as
"necessary but not yet load-bearing".

⚠️  **On its own sample the band argument would still have given the right
answer**, campaigns-per-ship comes out at the rig's trip life on all 168 rows.
The proof is what broke, not the answer: once a lever pushes back, a dimension
whose optimum is no longer guaranteed has to be searched rather than assumed.
It does bite when trips are longer: against the older Stage 3 table, where
nothing capped duty cycles and trips reached 20, 12 of 168 bodies choose to
retire a rig early rather than pay the calendar to use it up.

Brute-forced rather than argued: every (fleet × campaigns-per-ship) on a 20 × 8
grid, priced exhaustively, per body. **Campaigns-per-ship is exact on 49 of 49
bodies**; the search is worse than brute force on 5, by at most **0.027%**, and
every one of those is the inherited fleet ladder landing one ship off.

⚠️  **Read the loader's `Module 3 operational costs  44 rows` line before
trusting any programme figure.** Against the archived 43-row table from the
v1.14.0 campaign the trip cap is silently absent, campaigns-per-ship runs to 20
instead of 5, and every programme number changes. `schema_check()` names it on
stdout; this bit during measurement.

## calc v1.15.0 / transportation v1.12.0

**Programme size stopped being an input.** Two items, both inert at N = 1, so
every measured cell in this project stands. ✅  Measured rather than asserted:
on a 400-row raw cislunar sample the best cell is **60.9284× with the trip cap
on and off alike**, while the median trip life moves 15 → 5 and the cycle bound
binds on 97.0% of rows. The cap changes the answer only for programmes, which is
the point of it.

**The rig wore out on a calendar, and the calendar was never the bound.**
`missions_sharing_rig` was `min(N, life / stay)`, and `life` is "Mining rig
service life" = **15 YEARS**: a figure whose own Stage 3 notes describe
corrosion, thermal cycling and radiation dose. Dividing it by the stay gave a
mission count, and nothing anywhere bounded **duty cycles**, so at the ~1.25 yr
stay the winning cislunar mission flies, one rig was good for **twelve
consecutive digs** on the strength of a number that only ever promised it would
not have rusted meanwhile. A rig parked between campaigns ages slowly; one
cutting rock does not.

Stage 3 v1.12.0 adds **"Mining rig maximum trips" = 5** (range 2-12) and the min
of the two bounds is taken, so long stays stay calendar-limited and short ones
are now cycle-limited. ⚠️ The 5 is a **judgement**; nothing has ever mined an
asteroid twice, bracketed between terrestrial mining plant (overhaul at ~2-3 yr
of continuous duty, in a workshop that does not exist at an asteroid) and the
flight record for regolith-contact mechanisms (single-campaign by design, or
failed inside one: TAGSAM, Philae, InSight's mole, Curiosity's drill). It also
stops terminal value refunding a mechanically-finished rig for its unused
calendar years.

**Programme size and fleet size became a searched axis.** v1.14.0 made market
saturation see N and thereby made the scale curve *turn*; nothing then searched
for the turn, and the curve was mapped by re-running the whole pipeline at
N = 1, 10, 100. Two structural facts make searching it cost **1.51× runtime,
not 12×** (measured on the full catalog; a 2,500-row sample said 1.13×):

1. **N enters nothing in the mass cascade.** It appears in the cost model,
   the saturation block and the reliability block, and in none of the rocket
   equation, the power fixed point, the payload knapsack or the concentration
   sweep. The expensive half is solved once and the whole ladder priced off it.
2. **The optimum N is always an exact multiple of the rig's trip life.** Within
   one fleet band the concurrent output, and so the saturation multiplier, is
   constant while NRE/N, the learning curve, the rig share and `p_mining` all
   improve, so the band's best is its top, N = F × trips. **So the search is over
   the FLEET and N follows**, and every N that cannot be optimal is skipped
   without being priced.

> 🚨  **Point 2 is retired by v1.16.0, "always" is now "usually".** The proof
> was "every lever improves and none pushes back", and programme calendar time
> pushes back. Campaigns-per-ship is searched now, exhaustively, and the search
> is two-dimensional. Point 1 is untouched and is what still makes it cheap.

That is also the answer to the question in plain terms: **the number of ships is
the decision variable and programme size is its consequence.**

On a 2,500-row raw cislunar sample it moves the best cell **42.0081× →
21.7341×**, choosing fleets of 1-8 ships (N = 5-40) and pricing a median of 8
ladder rungs per mission. ⚠️  That is a sample; the full-catalog figures are in
the table below.

Brute-forced rather than asserted, because it is the load-bearing claim: every
integer N from 1 to 60 was evaluated exhaustively for 20 raw bodies and 1 to 24
for 32 beneficiated ones. Raw is exact everywhere: 0 exceptions, ratios matching
to four decimals. Beneficiated has **one genuine miss in 52 bodies, at 0.97%**,
and it is not the band argument: it is the concentration sweep's greedy
refinement, which now depends on N, failing to price a ratio that would have won
at a different programme size. Raising `concentration_search_steps` from 7 to 25
makes the ladder return the brute-force optimum exactly, which is what identifies
the grid rather than the fleet argument as the cause.

### Measured on the full catalog (2026-08-11)

Both cells, all **1,554,353 rows** at cislunar raw, one process, 12 workers,
**650,516 evaluable** in each:

| | search off (N = 1) | search on |
|---|---|---|
| best cost/revenue | **26.7863×** | **14.1730×** (−47.1%) |
| winner | 2021 CX5 (D), New Glenn, **xenon** | 2021 CX5 (D), New Glenn, **iodine** |
| N / fleet | 1 / 1 | **5 / 1** |
| wall clock | 1,306 s | 1,978 s (**1.51×**) |

Never-worse holds on the whole population: **650,516 pairs, 0 worse, 650,515
improved, median improvement 45.3%.** `N = F × trips` on every single row. Fleet
sizes: 46.8% of bodies want one ship, median 2, and 0.37% pile up against
`max_fleet_ships` (bodies whose payloads have no finite market; the run flags
them).

🚨 **Run 1 reproduces the committed v1.14.0 cell exactly**: ratio, evaluable
rows, winner, vehicle, propellant, payload to the kilogram, saturation
multiplier, `p_mining`, RTG share, and the whole propellant split. v1.14.1 and
v1.14.2 argued bit-identity from ≤2,500-row samples and v1.15.0 argued inertness
from 400; **all three now hold on 1.55 million bodies at once.** The run also
measures those two performance releases at **4.10×** on a full cell, inside the
projected 3.4-4.6×.

🚨 **And one claim did not survive.** This release originally recorded
**1.04-1.13×** runtime for the search, from a 2,500-row sample. On the full
catalog it is **1.51×**; the sample understated it by ~1.4×. That is the third
time a stride sample has mispredicted full-catalog runtime here, in both
directions, and it extends the standing rule from absolute wall clocks to
*ratios between two settings*. Every other number in the release came out where
the sample said; only the runtime moved.

⚠️ **Default ON as of calc v1.17.0** (it was OFF at this release), and it is
still the one axis in Stage 4 that is not a correction: it changes the question
from "the best single mission to this rock" to "the best programme built around
it". Almost every figure on record is the former, at N = 1; set
`optimise_programme_scale = False` to reproduce them.

## calc v1.14.2

**No number.** The third performance-only stamp, same contract as v1.10.1 and
v1.14.1. Every measured cell in this project stands as measured on v1.14.0.

| | v1.14.1 | **v1.14.2** | speed-up | output |
|---|---|---|---|---|
| raw, 400 rows | 2.70 s | **1.13 s** | **2.39×** | 124/124 columns identical, sha256 MATCH |
| beneficiated, 150 rows | 9.19 s | **4.51 s** | **2.04×** | 124/124 columns identical, sha256 MATCH |

A bigger step than v1.14.1's, and **none of it came from the algorithm**; the
search does the same work in the same order. It had been doing it through the
wrong machinery.

**The model's arithmetic was going through numpy, one scalar at a time.** The
two most-called functions in the module applied `np.isfinite` and `np.exp` to
plain Python floats. On the reference machine `np.isfinite` costs **698 ns**
against `math.isfinite`'s **32 ns**, and `float(np.exp(x))` **694 ns** against
`math.exp`'s **47 ns**: 15-22×, because a ufunc call on a scalar builds a 0-d
array, resolves a dtype loop and boxes the result. That is the right price
amortised over a million elements and the wrong one for a single float. The
solver makes seven of them per call and is called half a million times per 150
beneficiated asteroids. `math.exp` was checked **bitwise** against `np.exp` over
400,000 samples spanning the model's Δv/Isp range before the swap: zero
mismatches.

**Three hoists.** The payload knapsack re-sorted the same phase list ~2,100
times per asteroid; six per-propellant constants and one per-vehicle were
re-parsed for every surviving candidate, each through `pd.isna` (another pandas
dispatch on a scalar: ~980,000 calls per 150 rows); and the infeasibility
pre-filter turns out to be **monotone in launch capacity**, so seventeen vehicles
were each re-deriving one propellant's exponentials, boil-off and tankage
closure only to differ on the final comparison.

🚨 **One of those hoists is a trap, and it is the most transferable thing in this
release.** Sorting the phase table at source, the obvious way to hoist the
knapsack's sort, *changes the output*. The market-saturation block accumulates
value by iterating a dict built from that table, and floating-point addition is
not associative, so the table's natural order is load-bearing on the last ULP.
The measured effect is **2.8e-16** on 3 of 60 rows with no winner moving:
numerically nothing, and still fatal, because every claim this project makes
about a release is argued from bit-identity. *A change can be numerically
negligible and still destroy the evidence.* The same reasoning is why the
pre-filter hoist carries the coefficients of its final comparison rather than the
launch capacity they algebraically imply; that rearrangement would move the
prune boundary in the last bit, and there it would change a row count.

**Measured and not taken:** hoisting the ratio-independent prologue out of the
concentration sweep, which looked like the largest remaining item and instruments
at **7.6%** of a beneficiated run; the three hoists above had already removed
what made it expensive. Measure the remainder *after* taking the cheap items.

⚠️ That 7.6% is a v1.14.2 figure and three later releases cut work around it
without re-measuring it. **Re-measured on v1.17.5 it is 2.3%** of the default
cell and 2.6% of raw, so the item is worth about 2%, still declined, now on a
current number, and a small illustration of the advice in the sentence above.

## calc v1.14.1

**No number.** A performance release on the same contract as v1.10.1: the stamp
moves so a CSV still names the code that produced it, and every measured cell in
this project stands as measured on v1.14.0.

The search was spending ~90% of itself proving missions infeasible the
expensive way. Of 134,538 candidate solves for 200 raw asteroids at cislunar,
**8,292 reached the cost model: 6.2%**; beneficiated it is 7.3%. The rest paid
a ~20 µs prologue (eclipse geometry, synodic period, ISRU chemistry, tankage,
electric-stage sizing) to reach a solver that rejected them on a dozen flops.

Those flops now come first. The trick is that the sizing loop's **first**
iteration runs at zero plant mass, zero containment and the shortest possible
hold, so it is the most optimistic pass the loop will ever take, and it is
closed form. If it does not close, nothing downstream does. It is also blind to
the power source (no plant yet) and to the concentration ratio (no feed yet),
which is why the identical refutation was being recomputed up to eighteen times
for one dead candidate.

The second half of the release is the same lesson in a different place: the dark
period, the eclipse-corrected specific power, the 1/r² solar figure, the synodic
period, the mineable mass and the throughput cap are functions of the **body**
alone, and all six were being recomputed for every candidate: 38,643 times
apiece for 200 asteroids. `AsteroidContext` computes them once per asteroid.

| | v1.14.0 | **v1.14.1** | speed-up | output |
|---|---|---|---|---|
| raw, 400 rows | 7.86 s | **4.07 s** | **1.93×** | 124/124 columns identical, sha256 MATCH |
| beneficiated, 150 rows | 28.07 s | **16.73 s** | **1.68×** | 124/124 columns identical, sha256 MATCH |

On the full catalog it prunes **75.9%** of candidates. ⚠️ **That is not a 4×.**
The quarter that survive are the expensive ones, full cascade, cost model,
whole concentration sweep, so three quarters of the candidates are well under
half of the work. Do not quote the prune rate as a speed-up.

Soundness was checked three ways rather than argued: 68,136 (candidate × Δv ×
ISRU) tuples were pruned *and* solved in full, and none of the pruned ones
produced a result; calls to `mission_cost_usd` are **8,292 before and 8,292
after** while total solves fall 134,538 → 38,443; and serial vs 8 workers is
byte-identical. `.calc.prune_infeasible_combos = False` restores the v1.14.0
search exactly, and is the diff to run if an output ever moves.

> ✅ **This is stage 1 of two as of v1.17.4**, which asked the question this
> release did not: what happens at pass **2**. Pass 2 is the first pass that
> flies the electric stage pass 1 has just sized, and **74.3% of everything
> that survives stage 1 dies there**: identically at every concentration ratio
> and every power source, because that stage is sized off a cascade blind to
> both. Same flag, same restore, same diff. See [calc v1.17.4](#calc-v1174--catalog-v111).

**The GPU was tested and rejected**, on an RTX 2080 Ti: fp64 `exp` over 40M
elements is **1.695 s on the card against 0.222 s on the CPU**: 7.6× slower,
which is the consumer 1:32 FP64 rate. fp32 is faster and unusable, because every
check this project relies on is a bit-identity check. RAM is not a constraint
either: the run peaks near 6 GB of 64 GB.

## calc v1.14.0 / transportation v1.11.0

Another realism audit, and the result is more uncomfortable than v1.12.0's,
because three of the five findings were **already written down**. Every figure
below had been sitting in Stage 3's storage table since v1.9.0 under a note
reading "not modelled in Module 4", and Stage 4 does not load that file. The
gap was documented, quoted as a known limitation for two releases, and never
closed. *Writing a gap down is not closing it.*

Measured on a 6,000-row stride sample of the 89,367-row on-disk catalog at
cislunar, both versions run against the same rows in the same process. **These
are sample figures, not full-catalog headlines**: the full-catalog cells
elsewhere in this project are v1.13.0 and are now stale.

| | v1.13.0 | **v1.14.0** | Δ |
|---|---|---|---|
| raw | 38.4050× | **38.7886×** | **+1.00%** |
| beneficiated | 25.7930× | **31.6556×** | **+22.73%** |

- **The pipeline sold water and never kept it.** Water is priced at every
  in-space destination, its liberation energy is charged and the array that
  bakes it is flown, and nothing kept it from subliming across a four-year
  cruise. The best cislunar missions are **~88% water by mass**, water
  38,415 kg against carbon 3,548 kg and nickel-iron 1,537 kg of a 43,500 kg
  hold, so the commodity carrying the entire result was the one with no
  containment. ⚠️  Charged on **water only**: carbon and organics are
  refractory at these temperatures and ride in the hopper like rock. A
  sealed shaded hold at 0.05 kg/kg, incremental to the ore restraint, folded
  into the payload-scaling structure so the closed-form solver carries it with
  no change to its algebra.
- **The sun never set on the processing plant.** Processing power is a
  *continuous average* draw and the plant was sized straight off it, which is
  only right if the rig is never in shadow. It stands on a rotating body. Two
  terms: an array oversize of `[(1−f) + f/η]/(1−f)` = **2.11×**, which is a
  sizing factor no W/kg figure could ever have absorbed; and storage sized on
  the **body's own rotation period**, which finally makes `rotation_period_h`, 
  carried by Stage 1 since v1.0.0 and read by nothing, a quantity the model
  uses. Together they cost **4.7×** at 1 AU and the median 10.2 h rotation, not
  the "roughly doubles" the storage table itself estimated. ⚠️  **The storage
  term is charged as an INCREMENT and the deduction is not a nicety**: the
  60 W/kg row is system-level and part of its 2.5× gap to ROSA's ~150 W/kg at
  the wing is a battery, so Stage 3 names the baseline dark period it already
  covers (0.58 h, a LEO eclipse) and only the excess is new mass. Without that
  the battery is charged twice, and at 0.0056 kg/W against the row's own
  0.0167 kg/W that is **a third of the plant**. ⚠️  **The battery is the bigger
  half, which is why "roughly doubles" was so far out**: at the median 10.2 h
  rotation the storage for a 5-hour night is 0.044 kg/W against the array
  oversize's 0.035, so the 2× the storage table estimated is the array term
  alone. ⚠️  The 104 Wh/kg it is sized
  at is 130 Wh/kg system-level Li-ion at 80% depth of discharge, which is
  aggressive for the ~2,000 cycles a 10 h rotation implies across a 2.3-year
  dig; a regenerative fuel cell would cut the term ~4× and is not taken because
  nothing has flown one. Those two roughly offset.
- **The power source was chosen on mass, and it costs 625× more per watt.**
  This one was latent and this release is what made it dangerous. The
  radioisotope branch used to fire on *one row of 15,566*, so nobody noticed it
  was picking whichever plant was **lighter** while an RTG costs $500,000/W
  against $800. Adding the eclipse term moved the crossover from 3.46 AU to
  ~2.1 AU and put 31% of rows on the nuclear side, buying a median **$1.5B**
  plant, 14% of mission cost, on a criterion that cannot see dollars. Made a
  searched architecture axis resolved by the reported objective, it drops to
  **3.9%**. *An unreachable branch is not a verified branch.*
- **Market saturation could not see the programme it was written for.** Its own
  comment says it exists so "fly more missions" has a stopping point; it never
  read `nre_amortization_missions`, so a 100-mission programme sold 100
  payloads at the price one payload commands. Now charged on the programme's
  concurrent output, and the curve **turns**: 38.41× → 16.03× → 10.89× becomes
  38.79× → 16.47× → **20.32×** at N = 1/10/100. The optimum programme size is
  now interior, near N = 10.
- **Two ledger asymmetries.** The heat shield was the one recurring article
  with no learning curve; it is the most literally per-mission thing on the
  vehicle, and it was missing from the insured book value, the one item on the
  launch stack whose cost line sits outside `hardware_cost`. Both are inert at
  cislunar and at N = 1.

Also: `schema_check()` now checks Stage 3 **rows** as well as columns. The
operational-costs table is keyed by category, so a missing *figure* was
invisible to a column test, and four of this release's five findings arrive as
rows in it.

Verification: with both new flags off, the build reproduces HEAD across all 121
shared output columns; never-worse holds on the new power axis (max 1.000000,
zero exceptions) and for beneficiated ≤ raw; the mass-ledger identity holds
exactly; serial and parallel remain byte-identical. Runtime roughly doubles,
paid only on bodies where a radioisotope plant could be lighter.

## catalog v1.1.0 / calc v1.13.0

**Nothing in the model. Everything in the population.** Not one term,
coefficient, table value or search axis moved; a run over the same rows
produces the same numbers. The catalog went from **89,367 asteroids to
1,554,400**, and that is enough on its own to invalidate every earlier figure,
because every figure here is "the best mission over the bodies we had".
catalog `1.0.9 → 1.1.0`, calc `1.12.0 → 1.13.0`, master `1.15.0 → 1.16.0`.

Read this as the counterweight to every other release below. All the others
make the answer *worse* by removing something the model was getting free. This
one makes it **better**, and not as a concession: the model had always been
searching for the best rock in a bag holding 5.7% of the rocks.

**The bag was small for three unrelated reasons.**

1. **NEOWISE was contributing literally nothing, silently, and only at scale.**
   IRSA types `asteroid_number` by what the result slice happens to contain, so
   one unnumbered row makes the column `float64`; stringifying it built `"3.0"`
   where the backbone had `"3"`, and every NEOWISE row then died at validation
   for having no orbital elements. It **worked at small caps**, the fetcher
   printed its success line on the runs where it contributed zero, and the only
   trace in the output was seven `neowise_*` columns present and 100% empty.
   ⚠️  The row gain is small (~27 bodies JPL lacked); what it recovers is
   *data*: IR albedo, beaming parameter and diameter uncertainties for
   **132,691** bodies that had none. `merge_sources` now fails loud when a
   source arrives with rows and matches zero backbone designations.
2. **One row cap was shared by four sources**, which made the catalog smaller
   than any single source: each fetcher takes its lowest-numbered N bodies, so
   four sources capped at N return substantially the *same* N bodies and the
   union is ~N rather than 4N. One cap per source now, `0` = unlimited.
3. **Only 9% of asteroids have a measured diameter**, and validation drops the
   rest. That is the real ceiling; see
   [Diameters, and the 9% problem](README.md#diameters-and-the-9-problem).

🚨 **A row cap was never a sample, and that is a third silent failure.** JPL
returns rows in SPK-ID order and numbered bodies come first, so at any cap below
the full table a **provisional designation could never appear**; the old
catalog held **zero unnumbered asteroids**, all 89,367 rows numbered 1 to
199,994, against the new one's **658,490**. Recently-discovered NEAs are
overwhelmingly unnumbered, and NEAs are the bodies this model finds best.
Nobody had to make a mistake for this: `limit=N` on an ordered API is simply
not a sample.

**Stage 4's cap defaulted to throwing away 99.7% of the run.** `eval_row_cap`
was **5,000** against a 1.55 M-row catalog, discarded behind one line of
stdout, and because the catalog reaches Stage 4 sorted by semi-major axis,
`.head(n)` returned the *innermost* n bodies: at 5,000 rows, everything inside
roughly 2.1 AU, with no outer belt, no Hildas, no Trojans and an S-skewed
spectral mix. Every "quick check before the full run" was made on a population
that does not resemble the full run. The default is now `0`, and
`eval_row_sampling = "stride"` takes evenly-spaced rows across the whole
catalog (`"head"` restores the old behaviour). ⚠️  This changes what a *capped*
run produces; it does not change an uncapped one, which is every figure on
record.

**Measured at cislunar, full catalog, raw:** `33.2342× → 25.7035×`
(**−22.66%**), on 668,004 evaluable rows of 1,554,351, in 2,539 s. The best
case is **2021 CX5**, a D-type NEA at 1.63 AU, 82 m across, and 26 bodies beat
the old best case.

🚨 **The gain is the CAP, not the derivation, and the split matters.** The best
body on a *measured* diameter is 2016 GS2 at **27.0173×**, still −18.7%
against v1.12.0. So H-derivation is worth only ~1.3× of ratio at the very top;
almost all of the improvement comes from fetching bodies the row cap was
hiding. 2016 GS2 is unnumbered and the third-place body has an IAU number past
the 200,000 the previous run fetched. **Neither was ever excluded for lacking a
diameter.** Quote 25.7035× as the model's answer and 27.0173× as the
measurement-only answer, and never present the first without the second.

⚠️  **Do not budget from a sample: this release proved that wrong.** Scaling a
20,000-row stride sample predicted 2.2 h for the full raw run; it took **42
minutes**, a 3.1× overestimate, because fixed costs dominate a small run. The
beneficiated figure was then *estimated* at ~2.2 h from the sample's ratio and
turned out to be **10.6 h**: 4.8× the other way. Those two misses are what
established [the sampling rule](#the-sampling-rule).

## calc v1.12.0 / transportation v1.10.0

A realism audit, and the result is uncomfortable: **the same defect keeps
recurring**; a term that exists on one side of the model and not the other.
Every item below moves the answer the same way, *worse*. Cislunar raw
31.7712× → **33.2342×** (+4.60%), beneficiated 22.4665× → **23.9169×**
(+6.46%), still the best case, same winner.

- **The DEVICE was never modelled, only the propellant, and this is the big
  one.** The clean statement of it is that **launch was modelled as an
  integrated vehicle with a payload it can actually lift, while in-space
  propulsion was modelled as a bare specific impulse.** One side had a
  capacity limit and the other did not. Stage 4 sized the electric stage on
  POWER alone, so buying enough kilowatts turned any row in the propellant
  table into a cargo tug. The result: **31.8% of raw winners were pulsed
  plasma thrusters and 24.3% were electrospray**: devices that have flown,
  and have flown producing *micronewtons* (EO-1's PPT: 860 µN; LISA
  Pathfinder's colloid heads: 5-30 µN each). The pipeline was asking them for
  ~7-10 N. Electrospray's own note in the table said scaling it to a cargo
  stage "means millions of emitters", and nothing read that sentence.

  The gate is **mass, not a threshold**: thrust is momentum flux, `T =
  m_prop·ve/t`, so Stage 3 now carries `thruster_kg_per_n` per technology and
  a device making µN/kg reports thousands of tonnes of thruster and dies in
  the rocket equation on its own. The physical divide is recorded as
  `thrust_scaling`: *continuous* devices (discharge or beam area you can
  enlarge) sit at 6-90 kg/N however big you build them; *replicated* devices
  (discrete emitters, needles, pulses) are stuck at 2,500-10,000 kg/N forever.
  Efficiency was also one shared 0.60 for every electric row; a PPT is really
  ~8% against a gridded ion thruster's 70%, so it needs ~9× the array. Both
  are per-technology now, and measurably so in the output: **0.70 on 10,809
  rows, 0.45 on 1,997, 0.35 on 1,878**. **Zero replicated-scaling devices
  survive anywhere**, the evaluable catalog halves, and chemical propulsion
  comes back.

  The old lumped **8 kg/kW** "thruster + PPU" row is what allowed all of this,
  because a per-kW figure cannot express a per-newton constraint. It is split:
  the PPU scales with power (4.7 kg/kW, from NEXT-C's 34.5 kg at 7.4 kW) and
  the thruster head with thrust (54 kg/N). Together they reproduce NEXT-C to
  within 1%: `4.7 × 7.4 + 54 × 0.236 = 47.5 kg` against **47.2 kg measured**.
  ⚠️  **Iodine is the judgement call and it is load-bearing.** Its only flight
  unit is a 1.1 mN cubesat thruster, which works out near 1,100 kg/N, but that
  is an artefact of a 1U device rather than a property of iodine, which runs in
  the same Hall and gridded bodies xenon uses. Entered at **60 kg/N** against
  xenon Hall's 30, penalised for the heated feed and corrosion tolerance it
  really needs. `status` cannot express "flown, but three orders of magnitude
  below the scale being modelled", and that is a gap in the schema rather than
  in this number.

  > 🚨  **"Zero survive anywhere" was a property of the 15,566-row population,
  > not of the gate, and it is retired.** On the full 1.55 M-row catalog, FEEP
  > survives in seven of eight measured cells: 0 rows at `lunar_surface`, 13 at
  > `cislunar` raw, 5,479 at `earth_surface`. That is the gate working as
  > designed: `thruster_kg_per_n` is a mass penalty, not a cutoff, so the right
  > test is whether one ever **wins**. It never does, in any of the eight. But
  > the margin is not comfortable everywhere, at `mars_surface` the best FEEP
  > mission is the catalog's **fifth**-ranked body and at `earth_surface` its
  > **seventh**. PPT and electrospray, which won 31.8% and 24.3% of cislunar
  > rows before the gate, now survive nowhere at all.

- **Argon was a free resource, and the row said so itself.** It carried
  liquid-argon density: 1.395 kg/L, which exists only at its 87.3 K boiling
  point, and buys the lightest tank of any gas in the table at 2.1% of
  propellant mass, together with a boil-off of **zero**. Its own two comments
  read "liquid NBP (cryogenic storage)" and "stored supercritical at ambient
  temperature", three lines apart. Argon was winning ~25% of missions on that
  combination and the entire Mars result. Split into the two real articles:
  supercritical in a COPV at 0.30 kg/L (**22.9%** tankage), which is what has
  flown, and a `development`-tagged cryogenic row paying derived boil-off.
  22.9% is not a penalty, it is 1/M, pressure cancels out of the COPV mass
  fraction, so xenon 1.9% / krypton 12.5% / argon 22.9% is just
  M = 131.3 / 83.8 / 39.9 read backwards. ✅  Argon at 30 MPa pays **22.3%**
  against 22.9% at 18 MPa, and that robustness is the tell that it is physics
  rather than a tuned constant. **Density is derived twice rather than
  asserted**:
  Peng-Robinson at 293.15 K / 18 MPa gives Z = 0.919 and 0.321 kg/L, a
  generalised-compressibility reading at Tr = 1.945 / Pr = 3.70 gives Z ~ 0.99
  and 0.298 kg/L, and 0.30 sits between them; two methods rather than one
  because PR reproduces this table's xenon row but overstates krypton.
  **Boil-off is derived from the table's own LOX figure**: kerolox is
  0.015%/day and only the LOX half boils, which at O/F 2.30 makes LOX alone
  0.0215%/day, scaled to argon by heat leak (300 − 87.3)/(300 − 90.2) = 1.014
  and energy to boil (1.141 x 213.1)/(1.395 x 161.1) = 1.082, giving
  **0.024%/day**; argon boils slightly *faster* than oxygen, being 3 K colder
  with 8% less latent heat per litre. Measured effect at cislunar: argon falls from 25.0%
  of raw winners to 2.4% and from 27.3% of beneficiated winners to 0.0%, and
  1,059 bodies stop being feasible, while **neither headline ratio moves at
  all**, because the best missions were never flying argon. A single best-case
  cell is a poor regression test for a change that is wrong everywhere except
  at the top.
- **The cargo-water power plant was billed and never launched.** Liberation
  energy for water sold as cargo sized an array *after* the mass cascade had
  been built, so the cost model paid for it and the rocket equation never
  carried it. On a 400-body raw sample, `hardware_total_kg == 2,000 +
  power_system_kg + ep_system_kg` failed on **97 of 357 rows**, by up to
  408 kg. It now holds on every row. The worse half was the raw case: a raw
  mission to an icy body paid for an array it flew none of.
- **Propellant tankage had no cost line.** Flown since v1.11.0, charged its
  launch $/kg, manufactured for free. ~0.01% of mission cost, and kept exactly
  because it is small; this class is only found by checking every term.
- **Launch insurance under-booked the spacecraft.** Book value was rig +
  capsule, which was the whole vehicle back in v1.4.0. It never picked up the
  power plant, the electric stage, or tankage. A 300 kW electric stage is a
  nine-figure article and it was flying uninsured.
- **`max_accel_g` was exported and read by nobody**, though Stage 3 added it
  expressly to disqualify the kinetic launchers. Only maturity was excluding
  them; ungated, a 10,000 g slingshot at $6,250/kg wins on price and powders
  the mining rig.
- **The tanker charge was withdrawn**: the one item running the other way.
  Stage 3's note asked for it *"in the escape-direct scenario"*; v1.11.0
  implemented the arithmetic and dropped the scenario. Stage 4 reads
  `payload_leo_kg` and `usd_per_kg_to_leo` and nothing else, so no mission here
  is ever refuelled, and $1.08B was being billed for an unused capability. Now
  gated behind `escape_direct_launch`, which nothing sets.

**And one thing that turned out to be very nearly inert.** v1.11.0's RTG
option is correctly wired and fires on **1 row out of 15,566** (18916, at
3.86 AU). 864 catalog bodies sit beyond the 3.46 AU crossover, but they fail
in the mass cascade on a 10-12 km/s outbound Δv long before array mass
matters. The code is right; the claimed benefit never materialised. A term
being implemented is not the same as a term being reached.

**Verified four ways** on the rebuilt `master.py`, at cislunar: the full
catalog reproduces both cells; never-worse holds exactly (15,407 pairs, max
benef/raw 1.000000, 0 exceptions, 591 declined), which mattered more than
usual here, since the thrust gate *removes* options and a strictly smaller
option set cannot make a correct search better; no `replicated`-scaling device
survives in either run, the direct check that the gate did what it claims
(**retired twice over: see the note above; survival was a property of a
15,566-row population, and "never wins anywhere" fell on 2026-08-24 when a FEEP
mission took rank 1 at `mars_surface` raw with the programme search on, 13.4%
clear of the runner-up. The gate is a mass penalty rather than a threshold, so
paying 6.7 tonnes of thruster and winning anyway is the mechanism working, not
leaking**); and
serial vs 8-worker runs are byte-identical (raw 4,000 rows 43.2 s → 23.5 s,
beneficiated 2,000 rows 197.6 s → 54.0 s, sha256 MATCH on both). Full-catalog
wall clock is 86 s raw / 463 s beneficiated, essentially unchanged from
v1.11.0's 89 s / 462 s; the extra knapsack calls are offset by half the
catalog now failing early.

## calc v1.11.0 / transportation v1.9.0

Same failure mode as v1.10.0, found one level further out: **the reference
tables were incomplete, and the omissions all ran the same way.** Everything
missing from the propellant table was either an option the search never got to
consider or a cost the model never got to charge, so the model was picking
the best of seven propellants while the output claimed it had picked the best
available.

- **Propellant tankage entered the rocket equation.** `density_kg_per_L` had
  been computed and exported since Stage 3 v1.2.0 and read by nothing. Tank
  mass scales with volume, so this subsidised low-density propellants, which
  are the same ones with the highest specific impulse.
- **Sixteen flown propellants were added**, including krypton (the most-flown
  electric propellant by unit count), iodine, and water electrothermal.
  Seventeen development and concept rows were added behind a maturity gate.
- **The RTG row was read for the first time** since it was written in v1.2.0.
  Solar and radioisotope power cross at 3.46 AU, and a lot of this catalog is
  beyond it.
- **Orbital refuelling was charged.** Starship's escape payload assumes tanker
  flights; twelve of them is $1.08B.
- **ISRU stopped being hydrolox-only.**

**Measured: the two effects pull opposite ways, and the split is the
evidence.** Raw improved at every destination (−0.18% to −1.94%); that is the
wider search on its own, and a strictly larger option set cannot make a
correct search worse. Beneficiated split, +6.43% at `leo` against −6.89% at
`lunar_surface`, because beneficiation means more propellant and `k = 1/(1 −
t(R−1))` diverges with mass ratio. Cislunar, the best case, improved 22.9336×
→ **22.4665×**.

The surprise is *where* tankage acts. It is only ~0.7% of launch mass in the
winning missions, because the search routes around it; iodine wins nine of
ten cells on a 0.2% tank against xenon's 1.9%, and chemical propulsion goes
effectively extinct (hydrolox wins 7 rows of 32,442). The tank term's effect
is not a cost it adds; it is **which propellant it disqualifies**.

🚨 **Both halves of that last sentence are RETIRED; only the mechanism
survives.** v1.14.0's eclipse term reprices every electric mission, and on the
full catalog **xenon** takes 42-76% of every raw cell against iodine's 10-25%,
while chemical propulsion is not extinct; hydrolox holds 1.9-8.1% everywhere
and methalox reaches 11-15% of three destinations under beneficiation.
⚠️  Iodine then comes *back* at programme scale, overtaking xenon at `leo` and
winning `earth_surface` outright, so every propellant-share claim in this
project is a statement about a **configuration** rather than about the model.
What survives unaltered is that the tank term works by **disqualifying** rather
than by taxing.

**Verified three ways** on the rebuilt `master.py`, at cislunar:

- **Reproduces the sweep**: 31.7712× raw and 22.4665× beneficiated from the
  built artefact in a separate process, matching the module-level run exactly.
- **Never-worse invariant holds**: 31,558 raw/beneficiated pairs, max
  `benef/raw` = 1.000000, zero exceptions, 655 bodies declining to concentrate
  at exactly 1.0. That is the expected signature and nothing else. It matters
  most for this release, because *widening* a search is the operation that
  exposed the v1.10.0 objective bug.
- **Serial and parallel are byte-identical**: sha256 match at 4,000 raw rows
  (1.94×) and 2,000 beneficiated rows (3.79×).

## calc v1.10.1

**No number**: the first performance-only stamp, and the one that set the
contract every later one follows. Every output is bit-identical to v1.10.0,
checked two ways: sha256-diffing serial against parallel CSVs over the same
rows at three destinations, and reproducing the then-committed cislunar cells
from the full catalog (22.9336× beneficiated with the same winner and
concentration ratio, 31.8269× raw).

A full beneficiated destination went from ~2,120 s to **137 s**, and raw from
~140 s to **33 s**.

**The main loop runs on every core.** Asteroids are independent; the search
reads the reference tables and writes nothing, so it had always been
embarrassingly parallel and had always run on one thread of twelve.

**And ~1.9× of the gain is single-threaded**, which is the part that also helps
anyone running one process per destination: catalog rows are converted to plain
dicts before the inner search (pandas was resolving ~7,400 index lookups per
asteroid, ~38% of the entire run), and the sizing loop's five Stage 3 constants
are memoised rather than looked up ~24 million times.

Three things about the parallel path that must not be undone, chunks consumed
in submission order, the `__main__` repointing that stops a worker re-executing
the Streamlit app, and the refusal to start a worker that cannot repay its own
startup, are documented where they matter, under
[Parallel evaluation](README.md#parallel-evaluation).

⚠️  **The timings above belong to this release and the old 89,367-row catalog.**
v1.11.0 made the search 4.6× wider, catalog v1.1.0 made the catalog 17× bigger,
and v1.14.0 added a power-source axis. None of that is a regression.

## calc v1.10.0

Two of these are the same bug in two places: **a mass entered the rocket
equation and never entered the ledger.** That is the failure mode to watch for
here, because the mass cascade and the cost cascade live in different
functions and nothing checks that every kilogram in one has a price in the
other.

- **The electric propulsion stage was free.** v1.7.0 sized the EP array and
  thruster, pushed them through the rocket equation, and never passed them to
  the cost model. A 309 kW, 14-tonne electric stage cost nothing. Now priced:
  the array off the existing $800/W row, the thruster and PPU off a new
  $1.5M/kW Stage-3 row anchored on NEXT-C.
- **The return vehicle did not grow with its cargo.** A flat 500 kg however
  much it carried, so the cascade loaded 125 tonnes of ore into a half-tonne
  can: 250:1 payload-to-structure, against 0.4:1 to 2:1 for real cargo
  spacecraft. `return_structure_frac_of_payload` fixes it, and the closed-form
  payload solver carries the term exactly.
- **The search optimised the wrong thing.** Every per-asteroid search picked
  the highest `profit_usd`. Since revenue here sits orders of magnitude below
  cost, that is `≈ −total_cost_usd`, so it quietly meant "pick the cheapest
  mission", while the project ranked the output by a cost/revenue ratio
  nothing had optimised. The tell was unmissable once looked for: adding
  options could make a target's reported ratio *worse*. `selection_key` now
  maximises profit when anything is profitable and minimises cost/revenue
  otherwise.
- **Aerocapture and ISRU became per-asteroid choices**, and ISRU became
  physical: hydrolox at bodies with water, at 1.286 kg of water per kg of
  propellant, with the extra rock dug, timed and charged. The old switch
  synthesised *xenon* at a rubble pile. (Hydrolox was the *only* route
  v1.10.0 allowed; v1.11.0 added the water-fed thermal and electric options
  at 1.00 kg per kg; see the ISRU note under [Tuning](README.md#tuning).)
- **The rendezvous apsis is searched, not assumed**, and resolved against the
  destination, a body best met at aphelion for an Earth return can be best
  met at perihelion for Mars. Published validation figures are unaffected.

The first two both flattered electric propulsion and large hauls, so v1.10.0
was expected to move the headline number *up* before the architecture search
pulled it back down. **Measured: the architecture search dominates.** Mars
beneficiated went 25.2× on v1.9.1 to 11.86× on v1.10.0 at unchanged v1.6.0
pricing, better, not worse, despite two new charges. Resolving aerocapture,
ISRU, apsis and propellant per asteroid is worth more than the EP stage and
the return structure cost.

If a change suddenly improves these by an order of magnitude, suspect it has
switched one of the twenty models off rather than found something. See
[What the model charges for](README.md#what-the-model-charges-for).

## Earlier releases

These predate the per-release notes above and are summarised rather than
written out. What each one started charging for is described in full under
[What the model charges for](README.md#what-the-model-charges-for), which is
organised by model rather than by release.

**mineral_value v1.7.0; destination pricing, and the release that moved Mars
from best to worst.** One utility table had served every in-space destination,
so olivine captured the same fraction of its freight on the surface of Mars; a
planet made of olivine, as at a depot in empty space. The missing term is not
distance, it is **local competition: the alternative to importing is not always
launching from Earth.** Per-destination discounts, all running *downward*; the
import budget split per commodity class instead of every commodity getting the
whole thing; and `annual_market_kg` **routed**, so a commodity flown home is
bounded by terrestrial production rather than a depot's import budget. Measured
effect: [the v1.7.0 pricing matrix](#the-v170-pricing-matrix). Mechanism:
[Where the material is sold](README.md#where-the-material-is-sold).

**catalog v1.0.9; SsODNet had been downloaded and discarded on every run.**
ssoBFT renamed its identity columns, the column projection tolerated the loss,
and a ~500 MB download went in the bin at merge time behind one warning line.
Measured taxonomy went from **1,854 to 24,675** bodies and albedo-guessed
taxonomy from 33,235 to 11,131, density measured from 0 to **438**, and V-types
*fell* from 3,988 to 2,614; that last one is the giveaway, because V-types are
genuinely rare and 3,988 of them was an artefact of guessing taxonomy from
albedo. ⚠️  **Every figure committed before v1.0.9 was measured on that
degraded catalog.** Full account, including the three separate things that kept
it quiet:
[the SsODNet outage that wasn't an outage](CLAUDE.md#the-ssodnet-outage-that-wasnt-an-outage-fixed-in-v109).

**calc v1.9.0, reliability growth.** Duane/AMSAA, `q(n) = q_first · n^(−0.30)`,
capped at 0.95 and reported as the mean over missions 1..N rather than the
terminal value. The one place the model had been *pessimistic*. Exactly 0.850 at
N = 1. `p_mining` was also recalibrated 0.75 → **0.85** on the full
regolith-contact flight record; the old figure was counted from the three
failures with none of the successes, which was selection bias and below even the
pessimistic reading.

**calc v1.8.0, four charges.** Rig service life (a 15-year life *caps*
amortisation, which makes long-stay programmes up to 13.8× more expensive per
mission, not less), mission reliability on revenue only, cryogenic boil-off
folded into an effective return Δv, and in-space manufacturing costed instead of
hidden inside a utility factor.

**calc v1.7.0; five charges**, all of which had been running the same way,
towards optimism: low-thrust trip time, launch windows, bound-water liberation,
the learning curve, and market saturation.

**Net effect of those two releases on a default `earth_surface` run**, which is
the only place this early progression was ever tabulated:

| | v1.6.0 | v1.7.0 | v1.8.0 |
|---|---|---|---|
| electric share of winning combos | 12% | 2% | varies by destination |
| median mission duration | 3.49 yr | 4.12 yr | 4.1 yr |
| expected revenue multiplier | 1.00 | 1.00 | **0.67** (reliability) |
| rows with no feasible mission | 0 | 47 | 85 |

⚠️  Measured on the pre-v1.0.9 catalog, so the row counts are not comparable
with anything current; the *direction* of each column is the point.

**Earlier still.** Pre-v1.7.0 module copies were overwritten in place before any
of this was under version control; see
[Repository history](#repository-history) for how to recover them.

# Module changelogs

Every `pipeline_version` each module has carried, oldest first, one section per
module.

**This is the per-module view; [Releases](#releases) above is the cross-module
one.** Where a stamp has its own section there it is linked rather than
restated, because two copies of one measurement is the defect this project
keeps finding.

Three things live here and nowhere else, which is why the section exists at all
rather than folding into Releases:

- **The schema history.** Which release added which config field and which
  output column. A catalog stamped `calc 1.12.0` carries `tank_cost_usd` and no
  `cadence_window_bound`, and this is the only record of that; it is what tells
  you whether an archived CSV can answer the question you are asking of it.
- **The early releases.** calc 1.3.0 to 1.9.1, catalog 1.0.3 to 1.0.9,
  mineral_value 1.1.0 to 1.7.0 and transportation 1.2.0 to 1.8.2 all predate
  the per-release notes above. [Earlier releases](#earlier-releases) summarises
  them by theme; this is the stamp-by-stamp record.
- **The pairing map.** Almost every release moves two modules at once, and the
  pairing is what says whether a Stage 3 CSV on disk is old enough to matter to
  a Stage 4 run.

🚨  **This was 2,063 lines of comment above the four `pipeline_version` fields
until 2026-09-02**: calc 1,328, transportation 313, mineral_value 267, catalog
155. It was a second copy of the release record, which is the documentation
form of the defect CLAUDE.md exists to catalogue, and because the dashboard
scrapes a field's comment block as its help text, it was also what `ui.py`
rendered when you opened the version stamp: **88,148 characters of tooltip on
calc alone**, against 1,019 for the pointer that replaced it.

**Add a release note to [Releases](#releases) and its schema line here. Do not
start a third copy in the module.**

⚠️  **Stamps are in NUMERIC order here. They were not in the comment blocks
this came from**, where calc ran 1.3.6 before 1.3.5 and 1.17.4 before 1.17.3,
each entry having been appended wherever the writer's cursor happened to be.
Reading those in file order gave the wrong history, which is its own argument
for the move.

## Stage 1 changelog: `modules/catalog.py`

**`1.0.3`  initial release**, with NEOWISE and SsODNet integration.

**`1.0.4`  per-type PGM enrichment.** New `PGM_ENRICHMENT_BY_TYPE` table and
`comp_pgm_enrichment` column: a per-spectral-type multiplier on the rare-metal
(Pt, Pd, Ru, Ir, Os, Rh, Au) portion of the metal-fraction value. Differentiated
core fragments (M / Xe) take 2.0×, basaltic crust (V) 0.2×, mantle fragments
(A / R / O) 0.5×. Consumed by calc v1.3.4.

New output column: `comp_pgm_enrichment`.

**`1.0.5`  Asterank removed** (asterank.com/api). Dropped `fetch_asterank()`
and the `_ASTERANK_*` constants, the `use_asterank` toggle, the source's entry
in `build_catalog`'s sources dict, and its six output columns
(`provisional_des`, `delta_v_kms`, `estimated_value_usd`,
`estimated_profit_usd`, `accessibility_score`, `source_asterank`). calc v1.3.5
and later do not read them. Active sources reduced to JPL SBDB, SsODNet,
NEOWISE and MP3C.

**`1.0.6`  `lookup_asteroid()` passes `regex=False`.** Designations and names
carry regex metacharacters and pandas' `str.contains` defaults to `regex=True`,
so the substring match the docstring promised was really a pattern match:
`lookup_asteroid(cat, "(1) Ceres")` silently matched `"1 Ceres"`, and any
unbalanced bracket raised `re.PatternError`. No other behaviour change.

**`1.0.7`  renumbering, no behaviour change.** This project was briefly
developed in two places at once and both shipped different code as `1.0.6`, so
that stamp is ambiguous; the reconciled module is `1.0.7` because it matches
neither parent. Treat any CSV stamped `1.0.6` as undated and re-run it. See
[the parallel-repo divergence](#the-parallel-repo-divergence).

**`1.0.8`  the X-complex metal fractions were pre-Psyche.** M-type carried 0.80
metal at 5.30 g/cm³, the "exposed iron core" picture. No M-type has ever been
measured near that density: 16 Psyche is ~3.8-3.9 g/cm³ (Elkins-Tanton 2020,
Siltala and Granvik 2021) against 7.8 for an iron meteorite, and metal content
is now put at ~30-60%.

| type | metal | density g/cm³ |
|---|---|---|
| M | 0.80 → 0.50 | 5.30 → 3.90 |
| Xe | 0.75 → 0.45 | 5.00 → 3.80 |
| Xk | 0.50 → 0.25 | 3.80 → 3.60 |
| X | 0.40 → 0.30 | 3.50 → 3.30 |
| E | 0.30 → 0.10 | 3.50 → 3.20 |

Xk and E were independently inconsistent: both are described as
enstatite-dominant, and aubrites are near metal-free. Fraction sums per type are
unchanged, so calc v1.3.3's residual silicate floor behaves exactly as before.
Lowers M-type bulk value and raises nothing.

**`1.0.9`  SsODNet was being fetched and then thrown away.** The full account,
including the three separate things that kept it quiet, is
[the SsODNet outage that wasn't an outage](CLAUDE.md#the-ssodnet-outage-that-wasnt-an-outage-fixed-in-v109);
the summary is in [Earlier releases](#earlier-releases). ssoBFT renamed its
identity columns (`sso_number` / `sso_name` / `sso_id` became `number` / `name`
/ `id`), and these had drifted with them:

| old name | new name |
|---|---|
| `perihelion` | `periapsis_distance` |
| `aphelion` | `apoapsis_distance` |
| `perihelion_argument` | `periapsis_argument` |
| `absolute_magnitude.value` | `absolute_magnitude.H.value` |
| `spins.<1..3>.period.value` | `spins.period.value`, now a LIST |

Measured on one run with the sources otherwise identical (JPL 50k, NEOWISE 50k,
MP3C unreachable), catalog entries went **35,098 → 35,807** and measured
taxonomy **1,854 → 24,675** (source plus tholen; it was 1,358 + 496). Verified
against literature afterwards: Ceres 939.4 km / 2.162 g/cm³ / 9.074 h / C,
Vesta **522.8** / 3.411 / 5.342 h / V, Pallas B, Psyche X, Eros 5.27 h / S.
**Any CSV stamped `1.0.8` or earlier was built on the degraded catalog.**

**`1.1.0`  POPULATION RELEASE.** Full write-up:
[catalog v1.1.0 / calc v1.13.0](#catalog-v110--calc-v1130). Three things, all of
which change how many asteroids exist downstream: the NEOWISE float-typed merge
key, one row cap per source instead of one shared `jpl_limit`, and diameter
derived from H where none was measured. Measured 2026-08-08 against the live
APIs:

| | bodies |
|---|---|
| JPL asteroids available | 1,554,321 |
| ...with a MEASURED diameter | 139,582 |
| ...with H and a valid orbit | **1,553,812** |
| catalog at `jpl_limit=200,000` (v1.0.9) | 89,367 |
| catalog, measured diameters only (v1.1.0, gate off) | ~**139,600** |
| catalog, H-derived enabled (v1.1.0, default) | ~**1,553,800** |

The NEOWISE fix recovers only 27 bodies JPL lacks, because JPL SBDB already
ingests NEOWISE diameters, but it restores IR albedo, beaming parameter and
diameter uncertainties for ~**132,700** bodies that had none. ⚠️  Read that
against what the 2026-08 IRSA outage later measured NEOWISE to be worth: those
132,700 rows are *columns*, and only 20 bodies in 1,555,667 are actually SIZED
off the albedo it fills. See
[Data sources fail softly by design](CLAUDE.md#data-sources-fail-softly-by-design).

New config: one fetch limit per source, `derive_diameter_from_h`,
`min_derived_diameter_km`.

New output columns: `diameter_source`, `derived_diameter_is_estimate`.

⚠️  **Any CSV stamped `1.0.9` or earlier was built on at most 89,367 bodies**
and is not comparable row for row with a `1.1.0` run.

**`1.1.1`  performance only, every column identical.** Full write-up:
[calc v1.17.4 / catalog v1.1.1](#calc-v1174--catalog-v111). `enrich_composition`
resolved everything keyed on `spectral_type` once per ROW, twelve `.apply()`
passes making ~19 million Python calls to produce the ~800 answers 76 taxonomy
classes can give: **9.09 s to 2.35 s, 3.87×**, on a 224 s Stage 1. Verified by
running both builds on the same frame in one process, all 12 derived columns
identical.

No config or column change; the stamp moves so a catalog still names the code
that built it.

**`1.2.0`  a total NEOWISE sort order, the element epoch, and async TAP.**
Full write-up: [catalog v1.2.0](#catalog-v120). NEOWISE's `ORDER BY` named only
`asteroid_number`, which is not total over a table with 183,408 rows for
143,318 bodies, so `deduplicate_catalog`'s stable sort resolved 27,802 bodies
by arrival order alone; `ma` had been fetched since `1.0.3` without `epoch`,
which made `mean_anomaly_deg` unusable rather than merely unused; and
`fetch_neowise` moved from synchronous TAP to an IVOA UWS async job with the
synchronous path kept as the fallback.

New output columns: `element_epoch_jd` (osculating element epoch, JD TDB, from
SBDB's `epoch`), plus seven orbit-quality and accessibility fields, all 100%
populated: `orbit_condition_code` (MPC uncertainty U, 0-9),
`observation_arc_days`, `n_observations`, `orbit_fit_rms_arcsec`,
`earth_moid_au`, `orbit_class` and `orbit_solution_date`. All added to
`_JPL_FIELDS`, `_JPL_RENAME` and `_SAFE_FIELDS`; the five numeric ones also to
`_JPL_NUMERIC`, while `orbit_class` and `orbit_solution_date` are deliberately
excluded from it, being a category code and a date.

New config fields: `neowise_use_async` (bool, default `True`),
`neowise_async_max_wait_s` (int, default 900).

⚠️  **A catalog stamped `1.1.1` or earlier has no `element_epoch_jd`**, so its
`mean_anomaly_deg` cannot be referred to a date and no dated launch window can
be computed from it. Every other column is unchanged and remains comparable.

⚠️  **This is the first Stage 1 stamp whose CSV has not been regenerated.** The
catalog on disk is still `1.1.1`, so `stamp_check()` will report it as stale on
every Stage 4 run until Stage 1 is next run. That is the deliberate-lag case
the check explicitly cannot distinguish from a failed write; it is correct to
fire and means nothing by it here.

**`1.3.0`  bodies joined across sources, and every source validated against
its service.** Full write-up:
[master v1.33.0 / catalog v1.3.0](#master-v1330--catalog-v130), and the
package's `CHANGELOG.md` (`asteroid_catalog` `v0.2.0`).

New config field: `use_mpc_identifications` (bool, default `True`).

New output columns: `provisional_designation`, `absolute_magnitude_h_sigma`,
`albedo_sigma`, `estimated_mass_sigma_kg`, `neowise_n_fits`, `family`,
`proper_semi_major_axis_au`, `proper_eccentricity`, `proper_inclination_deg`,
`n_sources`, `sources`, and for each of diameter, albedo, H (`h_`), mass and
rotation period: `<stem>_provider`, `<stem>_n_sources`, `<stem>_spread`,
`<stem>_sources_agree`.

⚠️  **Three columns change meaning, not just value**, so a `1.2.0` CSV and a
`1.3.0` CSV do not compare on them: `orbital_period_yr` is years (it was days);
`name` is an IAU name or empty (it held provisional designations); a sigma
column now always belongs to the source its value came from.
`neowise_beaming_param` and `albedo_ir` are empty where NEOWISE assumed rather
than fitted them.

**`1.3.0` unchanged, installed rather than built (master v1.34.0).** No output
column moves: Stage 1 installs a published `asteroid_catalog` release and the
stamp is the release's. Full write-up:
[master v1.34.0](#master-v1340-stage-1-installs-a-published-catalog).

Config fields removed (they are build settings, chosen when a release is
built): `use_jpl`, `use_mp3c`, `use_ssodnet`, `use_neowise`, `jpl_limit`,
`ssodnet_limit`, `neowise_limit`, `mp3c_limit`, `neowise_use_async`,
`neowise_async_max_wait_s`, `use_mpc_identifications`, `min_diameter_km`,
`require_spectral_type`, `derive_diameter_from_h`, `min_derived_diameter_km`,
`cache_dir`, `cache_max_age_days`.

New config fields: `catalog_release` (str, the pin), `release_base_url` (str),
`manifest_filename` (str, `catalog_manifest.json`), `taxonomy_filename` (str,
`catalog_taxonomy.json`).

## Stage 2 changelog: `modules/mineral_value.py`

**`1.1.0`  initial release.**

**`1.1.1`  cross-file audit cleanup (May 2026).** Removed unused imports
(`field` from dataclasses, `Dict` from typing) and refreshed the
`_REF_PRICE_DATE` stamp 2026-01-15 to 2026-05-29.

**`1.1.2`  calibration pass**, fixing low-value bugs found in Stage 4 output.

- Iron **$0.12 → $0.50/kg**. The old number was the iron-ore benchmark; mining
  produces refined Fe metal from nickel-iron alloy, so the correct sale price is
  steel scrap ($0.25-0.50/kg).
- Gold $85k → **$150k/kg** (~$4,700/oz, May 2026 against a January-stamped
  value); platinum $31.5k → **$45k/kg** (~$**1,400**/oz, Heraeus 2026 forecast
  mid); palladium $32k → **$48k/kg** (~$**1,495**/oz, LBMA May 2026); rhodium
  $150k → **$320k/kg** (~$**9,950**/oz, LBMA May 2026).
- Water $2,500 → **$4,250/kg**, matching transportation v1.2.4's reusable
  Falcon 9 $4,253/kg-to-LEO instead of the legacy Falcon 9 launch cost.
- `nickel-iron` yields: added ruthenium (3 ppm) and osmium (2 ppm), previously
  missing despite being in the element catalog; iridium 2 → 4 ppm, rhodium
  2 → 1.5 ppm, rebalanced for the ~37 ppm total PGM the siderite literature
  gives.

Numerical impact, hand-verified: nickel-iron implied value **$3.26 → $4.60/kg**
(+41%), M-type bulk **$2.61 → $3.69/kg** (+41%), C-type **$375 → $638/kg**
(+70%, water-driven), B-type **$500 → $850/kg** (+70%).

**`1.1.3`  rare-mineral phase entries** (option 3 from the low-value audit):
`sperrylite` (PtAs2, **56.6%** Pt, ~$25k/kg implied), `laurite` (RuS2,
**61.2%** Ru, ~$10k/kg), `awaruite` (Ni3Fe, 75.9% Ni plus 5× PGM enrichment,
~$25k/kg) and `native-pgm` (~$55k/kg). These are NOT referenced by default in
Stage 1's `TAXONOMY_COMPOSITION`, which uses bulk `nickel-iron` as the metal
carrier; they are available targets for per-asteroid composition overrides or
future spectral-identification work, and Stage 4's integrity check reports them
as informational "extra" rows. ⚠️  Three of them then spent eight releases
inheriting a silent market-size default; see `1.7.1`.

**`1.1.4`  `lookup_mineral()` passes `regex=False`**, the same trap as catalog
v1.0.6 at the other end of the pipeline: `"nickel-iron (alloy)"` was read as a
pattern rather than the literal substring the docstring promises, and an
unbalanced bracket raised `re.PatternError`.

**`1.1.5`  renumbering, no behaviour change.** Both parents of the parallel-repo
split shipped different code as `1.1.4`; the reconciled module is `1.1.5`
because it matches neither. See
[the parallel-repo divergence](#the-parallel-repo-divergence).

**`1.2.0`  water is priced by DELIVERY DESTINATION.** Water was hardcoded at
$4,250/kg, explicitly "the cost-to-LEO of launching an equivalent water mass",
i.e. the value of water sitting in orbit, while Stage 4's mission model flew the
cargo back down and landed it in a re-entry capsule. Water on Earth's surface is
worth bulk-industrial rates.

The error was not marginal. Water was 99.9-100.0% of the bulk value of every
water-bearing type, so the entire profitability ranking was a proxy for
`ice_fraction`:

| type | bulk $/kg | from water | share |
|---|---|---|---|
| D | 1,062.63 | 1,062.50 | 100.0% |
| B | 850.13 | 850.00 | 100.0% |
| C | 637.63 | 637.50 | 100.0% |
| M | 5.90 | 0.00 | 0.0% |

New `WATER_VALUE_BY_DESTINATION` table and a `delivery_destination` config field
(`earth_surface` / `leo` / `cislunar`), defaulting to `earth_surface`, which is
what the Stage 4 architecture actually delivered, so C-type bulk value drops
637.63 to 0.13 $/kg and the ranking inverts to metal-rich types. Set `leo` to
recover the old numbers, but only alongside a mission model that actually stops
at LEO.

New config: `delivery_destination`.

New output columns: `value_basis`, `delivery_destination`.

**`1.3.0`  IN-SPACE DELIVERY: destination pricing generalised from water to
every commodity.** Paired with transportation v1.4.0 and calc v1.5.0. v1.2.0
repriced water and left every other commodity at terrestrial spot, which is the
same inconsistency v1.2.0 existed to fix, just moved: iron delivered to LEO was
valued at scrap-steel rates while the water beside it in the same capsule was
valued at launch cost avoided.

- `WATER_VALUE_BY_DESTINATION` becomes `DELIVERY_DESTINATIONS`, and the in-space
  prices are now DERIVED rather than tabulated. The old cislunar figure was
  "~3× the LEO figure" by assertion; it is now $4,253/kg-to-LEO carried a
  further 3,600 m/s by an Isp 465 s stage of dry-mass fraction 0.10, through the
  rocket equation in `delivered_cost_usd_per_kg()`. That lands at
  **$10,809/kg: 15% below the old hand-waved $12,750**, and traceable.
- **A kilogram at a depot is worth the better of two fates**, chosen per
  commodity. USED IN SPACE is the terrestrial price PLUS
  `in_space_utility × launch cost avoided`; note the PLUS. SHIPPED DOWN is the
  terrestrial price MINUS `downleg_cost_usd_per_kg` (capsule, TPS, recovery and
  the depot-departure burn): ~$25,400/kg from LEO, ~$27,300/kg from NRHO. Coming
  down is far cheaper than going up. This is what puts an honest number on
  platinum at a depot: nobody in orbit wants it, but it is still platinum.
- New `IN_SPACE_UTILITY` table: how good a substitute each commodity is for the
  launched article. Water 1.00, structural metals 0.70, silicates 0.25, carbon
  0.40, organics 0.20, and 0.00 for the precious metals, which routes them down
  the ship-to-Earth branch rather than zeroing them. **These are judgements, not
  measurements**, and they live in one table for that reason.
- New `apply_delivery_destination()` step, run after `merge_sources` so it
  overrides live quotes as well as reference ones.

Price impact at LEO and cislunar (`earth_surface` unchanged):

| commodity | terrestrial | LEO | cislunar | route |
|---|---|---|---|---|
| nickel-iron | $4.73 | $2,978 | $7,567 | used in space |
| water | $0.001 | $4,253 | $10,810 | used in space |
| platinum | $56,695 | $31,285 | $29,378 | shipped down |
| gold | $138,882 | $113,472 | $111,565 | shipped down |

New output columns: `terrestrial_price_usd_per_kg`, `in_space_utility`,
`downleg_cost_usd_per_kg`, `value_route`.

**`1.4.0`  SURFACE DESTINATIONS: `lunar_surface` and `mars_surface`.** Paired
with transportation v1.5.0 and calc v1.6.0. Prices for the three existing
destinations are unchanged.

- `delivered_cost_usd_per_kg` now walks a CHAIN OF LEGS (`_DELIVERY_LEGS`)
  backwards from the payload instead of taking one lumped Δv. Staging is worth
  roughly 2× on a lunar landing: a single stage flying the whole 5,920 m/s needs
  10.96 kg in LEO per kg landed against 4.99 kg for the TLI/LOI-tug and lander
  pair that would actually be flown.
- New `edl` leg type for atmospheric arrival, carrying a surviving-mass fraction
  rather than a Δv. Mars uses 0.30, measured from MSL (3,257 kg entry to 899 kg
  rover, 27.6%) and Perseverance (3,440 to 1,025, 29.8%).
- New `_LANDER_DRY_MASS_FRAC` 0.20. The Apollo LM descent stage flew 2,134 kg
  dry on 8,200 kg of propellant; a lander is structurally much heavier than a
  cryo tug for the same propellant load.

| destination | kg in LEO per kg delivered | delivered cost | downleg |
|---|---|---|---|
| `leo` | 1.00 | $4,253/kg | $25,410/kg |
| `cislunar` | 2.54 | $10,810/kg | $27,317/kg |
| `lunar_surface` | 4.99 | $21,210/kg | $44,939/kg |
| `mars_surface` | 10.61 | $45,105/kg | $96,394/kg |

The Mars downleg exceeds the terrestrial price of platinum, so platinum
delivered to a Mars base is worth exactly nothing, which is the correct answer
rather than a bug. ⚠️  **Both surface figures are marginal-transport LOWER
BOUNDS**: no NRE, no programme overhead, no cadence limit. CLPS lunar landers
really cost ~$1M/kg today at ~100 kg scale.

**`1.5.0`  market-size data for calc v1.7.0's saturation model.** Prices were
static at the point of sale: a mission could return any quantity of platinum and
sell every kilogram at spot, which left the "fly more missions" lever with no
stopping point.

- `ANNUAL_WORLD_PRODUCTION_KG`, USGS primary production. The targets asteroid
  mining always names are the small ones: osmium ~1 t/yr, iridium 7.5 t, rhodium
  23 t, platinum 180 t.
- `IN_SPACE_ANNUAL_DEMAND_KG`, what a theoretical base can absorb per year, all
  commodities competing for one import budget: LEO 500 t, cislunar 100 t, lunar
  surface 50 t, Mars 20 t. ⚠️  **Judgement, not measurement**; no such market
  exists.

New output column: `annual_market_kg`, destination-aware.

**`1.6.0`  in-space manufacturing is costed instead of assumed.** The gap
between "kilogram of Fe-Ni at a depot" and "kilogram of usable structure" used
to hide inside the 0.70 utility factor, so the refinery was assumed into
existence and never paid for. Now explicit and derived from Stage 3 rates:
energy at kWh/kg times $6.08/kWh (the capital cost of a kilowatt hour in deep
space, $800/W-EOL over a 15-year life, about 100× terrestrial industrial power),
plus $300k/kg of plant hardware at 100 kg/yr throughput per kg over 15 years,
i.e. $200 per kg refined.

Metals take 5 kWh/kg (electric-arc and direct-reduction steelmaking are
4-5 kWh/kg terrestrially and there is no carbothermic shortcut in vacuum),
silicates 1, carbon 2, water 0.5. Deducted from the "used in space" route only;
material shipped down is refined on Earth. The utility factor now means only
what it says: how good a substitute the finished article is for a launched one.

New output column: `in_space_processing_usd_per_kg`.

**`1.7.0`  utility is per destination, and the import budget is per commodity.**
Summary and the measured pricing matrix:
[Earlier releases](#earlier-releases) and
[the v1.7.0 pricing matrix](#the-v170-pricing-matrix). Mechanism:
[Where the material is sold](README.md#where-the-material-is-sold).

- `IN_SPACE_UTILITY_BY_DESTINATION` overrides the base table per destination.
  LEO and cislunar keep the base profile unchanged, because nothing is available
  locally there at any price, so they are the calibration anchor. The two
  surfaces are discounted against what they can dig up: water 1.00 to 0.60 Moon
  (PSR ice, ~40 K, no sunlight) and to 0.25 Mars (metres-thick ground ice,
  1-3 wt% hydrated regolith per SAM); iron and FeNi 0.70 to 0.45 Moon
  (5-15 wt% FeO plus ilmenite) and to 0.40 Mars (oxidised crust, loose
  meteoritic iron at Meridiani); silicates 0.25 to 0.03 Moon and 0.02 Mars,
  because it is the ground; carbon 0.40 to 0.02 Mars (95.3% CO2 atmosphere) and
  NOT discounted on the Moon, where carbon is ~100 ppm of solar-wind
  implantation; Ni/Co/Cu undiscounted everywhere, no concentrated ore of either
  body being known. **Every override runs DOWNWARD**, deliberately: raising a
  utility is precisely how this table becomes a way to manufacture viability.
- `_DEMAND_SHARE_BY_CLASS` splits the destination import budget that
  `IN_SPACE_ANNUAL_DEMAND_KG` had described as shared since v1.5.0 and never
  actually divided; every commodity used to get the whole budget to itself.
  Propellant 0.55 / structural 0.25 / shielding 0.15 / chemical 0.05, plus a
  **0.0005** trace slice that binds only if anyone ever gives the PGMs in-space
  utility. So Mars absorbs 11 t/yr of water where it used to absorb 20 t/yr of
  every commodity independently. Measured raw on the full catalog, this alone
  costs LEO 9.8% and cislunar **46.6%**, at destinations with no utility
  override at all; cislunar takes the bigger hit off the smaller budget.
- `annual_market_kg` is now ROUTED: the market that saturates is the one you
  sell into, so a commodity flown down is bounded by terrestrial annual
  production rather than by a depot's import budget. It runs in both directions;
  platinum at LEO tightens (the depot's 500 t/yr becomes the world's real
  180 t/yr) while gold loosens (500 t/yr becomes 3,000 t/yr).

Prices still RISE with distance, Mars freight being 10.6 kg-in-LEO per kg
delivered and that dominating; they just no longer rise as fast as the freight
does, and the volatiles that carried the Mars result rise least. Water at Mars
is 2.7× its LEO price now against 11× before.

Price impact at `mars_surface`:

| commodity | before | after |
|---|---|---|
| water | $44,902 | $11,073 |
| iron | $31,344 | $17,812 |
| olivine | $11,070 | $696 |
| carbon | $17,831 | $691 |
| nickel | $31,360 | unchanged, undiscounted |
| platinum | $0 | unchanged, downleg still exceeds spot |

**`1.7.1`  three commodities were falling through a silent default.** Full
write-up: [mineral_value v1.7.1](#mineral_value-v171). `sperrylite`, `laurite`
and `native-pgm` had no `_COMMODITY_CLASS` entry, so `annual_market_kg` handed
them the `.get(..., "shielding")` default: 0.15 of a destination's entire import
budget instead of the trace slice the eight PGM elements get, a factor of 300,
for the ore minerals of exactly those metals. Reclassified to `trace`, and an
`assert` after `MINERAL_REFERENCE` now fails at import if any commodity has no
class.

No exported value changes; all 31 rows of the on-disk catalog recompute
identically. The stamp moves so a catalog still names the code that built it.

**`1.8.0`  a sixth delivery destination: `mars_orbit`.** Full write-up:
[calc v1.18.0 / mineral_value v1.8.0 / transportation v1.13.0](#calc-v1180--mineral_value-v180--transportation-v1130).
A 1-sol elliptical Mars depot (250 x 33,793 km, NASA DRA 5.0), priced at
**$13,495.71/kg** on a 3.17 kg-in-LEO-per-kg stack.

Five table entries, no new config field and no new column:

| table | entry |
|---|---|
| `_DELIVERY_LEGS` | `[("burn", 3_600, tug), ("burn", 900, tug)]`, TMI + MOI, and no `edl` leg |
| `_DESTINATION_NOTES` | the derivation, and why binding beats circularising |
| `_DOWNLEG_DEPARTURE_DV_M_S` | **900 m/s**, against the surface's 6,200 |
| `IN_SPACE_ANNUAL_DEMAND_KG` | **60,000 kg/yr** |
| `IN_SPACE_UTILITY_BY_DESTINATION` | **`{}`**, the base profile, deliberately |

`delivery_destination` gains a sixth accepted value, so `DELIVERY_DESTINATIONS`
grows a key and both `--destination` and the dashboard picker offer it; each
derives its option list from that dict, so neither needed editing.

The demand figure is the one row of that table that does not fall off with
distance: 60 t/yr is larger than the 20 t/yr surface base it serves, because a
depot is transport infrastructure rather than a settlement, and what it holds is
the propellant for descent, ascent and the trans-Earth stage. That is ~128 t per
2.14-year synodic period, roughly one DRA 5.0 crewed mission's in-space
propellant, and still under cislunar's 100 t/yr.

The five existing destinations reprice to the cent, and no exported value moves.

**`1.9.0`  a seventh delivery destination: `geo`.** Full write-up:
[calc v1.19.0 / mineral_value v1.9.0 / transportation v1.14.0](#calc-v1190--mineral_value-v190--transportation-v1140).
A geostationary servicing depot at **$12,526.34/kg**, on a two-stage chain
(LEO to GTO, then an apogee burn that circularises and removes 28.5 deg at
once) worth 5.3% over flying it single-stage.

`IN_SPACE_UTILITY_BY_DESTINATION` gains its **first override block that runs
downward on the metals**: iron / nickel / cobalt / copper / nickel-iron /
awaruite to 0.15, the silicates to 0.05, carbon and organics to 0.05, and water
held at 0.80. Ni / Co / Cu are discounted here where the two surfaces leave
them undiscounted, and the reason is in the release note: those blocks are
about no local ORE, this one is about no local FACTORY.
`IN_SPACE_ANNUAL_DEMAND_KG` gains **40,000 kg/yr**, the smallest in-space
market in the table and the only one anchored on hardware that exists.
`_DOWNLEG_DEPARTURE_DV_M_S` gains **1,490 m/s**, twelve times the LEO figure.

The six existing destinations reprice to the cent, and no exported value moves.

## Stage 3 changelog: `modules/transportation.py`

🚨  **THIS RECORD MOVED WITH THE TABLES IT DESCRIBES, AND
[`spacecost`](https://github.com/loggger101/spacecost) IS THE ONLY COPY.** It
was 251 lines here and a verbatim second copy there, which is the documentation
form of the defect this project catalogues first and oftenest: *two copies of
one measurement is a bug, and you must name one authority or you have two.*
Deleted on 2026-09-07 by the same reasoning that deleted the 2,063 lines of
module-comment changelog on 2026-09-02.

**Read it at
[spacecost/CHANGELOG.md](https://github.com/loggger101/spacecost/blob/main/CHANGELOG.md#data-contract-history)**,
under "Data contract history". All 21 stamps, `1.2.0` through `1.14.0`,
unaltered.

⚠️  **NOTHING WAS DROPPED, AND THAT WAS CHECKED RATHER THAN ASSUMED**, with
`verify_docs.py --before`, which is the tool this project built for exactly
this move: it pulls every distinctive numeric token out of the old text and
asserts each still appears in the new. It exists because a line-level diff
reported 302 differences on the first such split and could not tell a dropped
measurement from a reflowed paragraph.

⚠️  **What you probably came here for is the SCHEMA half**, and it is the half
with no other home: which release added which output column is what tells you
whether an archived CSV can answer the question you are asking of it. That is
in spacecost's copy too, per stamp. A catalog on disk stamped
`transportation 1.9.0` was written by the tables that package now versions as
data contract `1.9.0`; the numbering is continuous across the move, because the
stamp identifies the DATA and the data did not change.

**Where a new entry goes now.** A table row changes in spacecost, so it is a
spacecost release, recorded in that repo's `CHANGELOG.md`. This repo follows by
moving the pinned tag in `requirements.txt` and `_MASTER_REQUIRED`, and that
move is a `master` release recorded above.
## Stage 4 changelog: `modules/calc.py`

**`1.3.0`  initial profitability calculator.**

**`1.3.1`  uncrewed autonomous-mission model**, paired with transportation
v1.2.4. Adds an `autonomy_nre_cost` line item to `mission_cost_usd`, sourced
from Stage 3's new `Autonomous mining control & AI (NRE)` row, which replaces
the legacy crew row; the docstring and cascade comments now state explicitly
that there is no crew cost, no life support and no human in the loop past LEO.

**`1.3.2`  deep accuracy audit**, five fixes, all numerically verified.

- **TPS mass now lives IN the rocket-equation cascade**, having been costed but
  not pushed. Reduces max payload by ~32% on a typical NEA. New closed form:
  `m_p_max = (M_LEO/R_out - m_hw - s·m_dry·R_ret) / (s·R_ret - 1)`, where
  `s = 1 + tps_frac`.
- Launch-insurance basis fixed: a percentage of (launch plus spacecraft book
  value), where it had wrongly been a percentage of (launch plus future
  revenue).
- Capsule recurring cost added, `dry_return × $/kg-recurring`; the 500 kg
  capsule previously had no manufacturing cost at all.
- Mining rig and capsule costs split: the rig amortises across
  `nre_amortization_missions` because it stays at the asteroid, and the capsule
  is per mission, fly-and-die.
- WACC compounding time-bucketed: upfront `× (1+W)^T`, ongoing `× (1+W)^(T/2)`,
  end `× 1.0`, where all three had been compounded to the end.

**`1.3.3`  silent under-counting in `asteroid_bulk_value_usd_per_kg`.** Stage
1's four composition fractions sum to 0.73-0.96 depending on taxonomy class, and
the residual (4-27%) was silently zero-valued; it is now treated as a bulk
silicate floor at ~$0.05/kg, which adds 0.2-1.2% to gross value. Pairs with
mineral_value v1.1.2's price and yield calibration: refined-iron Fe $0.50/kg,
where it had been iron-ore **$0.12**; Au $150k, Pt $45k, Pd $48k, Rh $320k;
water **$4,250**/kg from the Falcon 9 reusable launch cost avoided; plus Ru and
Os added to, and Ir bumped in, the nickel-iron PGM yields.

Combined hand-verified effect on Stage 4 output:

| asteroid bulk USD/kg | old | new |
|---|---|---|
| M-type | $**2.61** | $**3.69** (+41%) |
| S/Q-type | $0.6 | $0.85 (+39%) |
| C-type | $375 | $638 (+70%, water-driven) |
| B-type | $500 | $850 (+70%, water-driven) |

For a single Falcon Heavy plus methalox aerocapture mission returning 9.9 t,
C-type gross value rises $3.7M to $6.3M.

**`1.3.4`  per-asteroid PGM enrichment**, paired with catalog v1.0.4 and
mineral_value v1.1.3. Adds `RARE_METAL_ELEMENTS = {Pt, Pd, Rh, Ir, Os, Ru, Au}`;
`_mineral_implied_value()` takes a `pgm_enrichment` multiplier that scales the
rare-metal yields only and leaves base metals (Fe, Ni, Co) untouched; and
`asteroid_bulk_value_usd_per_kg()` pulls `comp_pgm_enrichment` from each row and
applies it to the nickel-iron lookup only. The default 1.0× (chondritic)
preserves v1.3.3 behaviour for catalogs from a Stage 1 older than v1.0.4.

Hand-verified per-type effect:

| type | enrichment | nickel-iron $/kg | asteroid bulk $/kg |
|---|---|---|---|
| M, Xe | 2.0× | $4.60 → $**7.10** | $**3.69** → $**5.69** (+54%) |
| X, E | 1.5× | $4.60 → $**5.85** | roughly +30% |
| A, R | 0.5× | $4.60 → $3.35 | roughly -9% to -20% |
| V | 0.2× | $4.60 → $**2.60** | $0.28 → $0.18 (-36%) |
| others | 1.0× | unchanged | unchanged |

For a **9,865** kg M-type return, gross value goes $36k to $56k (+54%). C-type
and B-type water-rich asteroids are unaffected, having no metal phase.

**`1.3.5`  Asterank-dependent code removed**, paired with catalog v1.0.5.
`asteroid_dv_m_s` no longer reads `asteroid_row["delta_v_kms"]`, so all missions
use `config.default_dv_outbound_m_s` and its return counterpart, and the output
dict no longer emits `asterank_value_usd`, `asterank_profit_usd` or
`asterank_accessibility`. No behavioural change for catalogs without Asterank
columns, which is now every catalog: v1.3.4 already fell back to defaults when
the field was absent. ⚠️  This is the release that left every asteroid on an
identical Δv, which v1.4.0 had to fix.

**`1.3.6`  correctness and performance**, with no change to any number a
default-config run produces, verified bitwise across all 53 numeric output
columns on a 500-asteroid catalog.

- **Return payload is now bounded by return-capsule VOLUME**, not just by mining
  fraction. With `use_isru_return_propellant=True` AND
  `use_aerocapture_return=False`, `tps_frac` collapses to 0 and nothing in the
  rocket equation scales with payload, so the launch-mass constraint went slack:
  a 30 km body "returned" 7.4e14 kg in a 500 kg capsule for a $7.8e17 profit
  that topped the rankings. The volume check already existed and already flagged
  it (`volume_fits=False`) and was never applied. Applied, that case yields
  **144,000** kg and -$2.67e9. Both sane toggle combinations are unchanged to
  the bit.
- `lookup_asteroid()` passes `regex=False`, the same trap as catalog v1.0.6.
- Ops-cost and mineral-price lookups memoised, and the candidate
  vehicle × propellant grid hoisted out of the per-asteroid loop, since it
  depends only on config. Stage 4 went from 8 to 469 asteroids/s; a 5,000-row
  run is ~11 s, having been ~10.6 min.

**`1.3.7`  renumbering, no behaviour change.** Both parents of the
parallel-repo split shipped different code as `1.3.6`; the reconciled module is
`1.3.7` because it matches neither. See
[the parallel-repo divergence](#the-parallel-repo-divergence).

**`1.4.0`  realism audit. Every number this module produces changes.**

- **PER-ASTEROID Δv.** v1.3.5 removed the Asterank per-target override and never
  replaced it, so every asteroid received an identical Δv. Measured on a 150-row
  run, `max_payload_kg`, `total_cost_usd`, `m_launch_kg`, `mission_duration_yr`,
  `vehicle` and `propellant` each had exactly ONE unique value catalog-wide and
  only `bulk_value_usd_per_kg` varied: the profitability ranking was a
  spectral-type ranking, and a main-belt body was costed the same as a
  co-orbital NEA. New patched-conic estimator (`asteroid_transfer_dv_km_s`) from
  a / e / i, validated to within ~10% of Stage 3's table and of published Bennu,
  Eros and Itokawa figures. Aerocapture saving is now per-asteroid rather than a
  flat 4,000 m/s.
- **MINING THROUGHPUT.** Extraction was instantaneous and unbounded, duration
  coming only from Δv plus a flat 0.5 yr whether the mission returned 33 kg or
  50 tonnes. Payload is now capped by what the rig can dig inside
  `max_mining_duration_yr`, and the dig time flows into mission duration, ops
  cost and WACC.
- **LOW-THRUST Δv PENALTY**, applying transportation v1.3.0's
  `dv_penalty_factor`, so electric propulsion no longer wins the mass cascade on
  an impulsive budget it cannot fly.
- **COST DE-DUPLICATION.** The return capsule is priced off Stage 3's capsule
  rate ($150k/kg) instead of the mining-payload rate ($300k/kg), and
  `nre_recurring_overlap_fraction` removes the development share already
  embedded in the per-kg recurring brackets. Set that field to 0.0 to restore
  the old double-booking.

New config: `use_per_asteroid_dv`, `mining_rate_kg_per_day_per_kg_rig`,
`nre_recurring_overlap_fraction`.

New output columns: `dv_penalty_factor`, `mining_duration_yr`,
`throughput_cap_kg`, `throughput_fits`.

**`1.5.0`  IN-SPACE DELIVERY ARCHITECTURE**, paired with mineral_value v1.3.0
and transportation v1.4.0. `delivery_destination` was a Stage 2 price label that
Stage 4 ignored: whatever it said, this module flew a re-entry capsule to
Earth's surface and costed a full recovery campaign, so setting it to `cislunar`
priced the cargo at a depot while paying to land it in Utah, the exact
inconsistency the field was added to prevent. It is now an architecture selector
Stage 4 honours, and the two modules are checked against each other at load time
by `destination_check`.

- **RETURN Δv IS NOW PER-DESTINATION**, derived per asteroid from the arrival
  v_infinity rather than assumed. `asteroid_transfer_dv_km_s` returns a dict of
  legs instead of a 3-tuple, and new `_cislunar_capture_dv_km_s` captures at low
  perigee into an ellipse reaching lunar distance, taking the Oberth benefit,
  then inserts into NRHO at apogee. At v_inf = 3 km/s the three architectures
  cost `dv_match + 0` (earth_surface, direct entry), `dv_match + 0.96`
  (cislunar) and `dv_match + 3.59` km/s (leo, propulsive capture). **LEO is the
  most expensive destination to reach AND worth less per kg than cislunar**, the
  two effects compound, and the ranking now shows it.
- **COST LINES SWAP BY ARCHITECTURE.** An in-space delivery carries a $60k/kg
  berthing adapter instead of a $150k/kg re-entry capsule, $2M of depot handover
  instead of a $15M Earth recovery campaign, and the $1.2M launch-only Part 450
  licence instead of the $2.5M launch-plus-re-entry one.
- **TPS IS ARCHITECTURE-GATED** (`uses_tps`). A cislunar delivery never enters an
  atmosphere, so `use_aerocapture_return` is ignored there and no heat-shield
  mass enters the cascade. LEO honours it as aerocapture plus multi-pass
  aerobraking.

`earth_surface` runs are UNCHANGED to the bit; the architecture table reproduces
the old code path exactly for that destination.

**BENEFICIATION** arrives in the same release (`use_beneficiation`, default
False at the time, and off preserves v1.4.0 output bit for bit). The pipeline
flew home run-of-mine regolith at bulk grade while the rig's own throughput cap
sat 66× above the rocket-equation payload limit and never bound, so all that
processing capacity was modelled as idle. Terrestrial mines ship concentrate,
not ore. With it on: the throughput cap bounds the FEED rather than the payload;
the load is OPTIMISED rather than specified, by a fractional knapsack over
`asteroid_phase_table` where greedy selection by $/kg is provably optimal, so
both honest bounds (content and purity) fall out of it; TIME is charged on the
feed, so a 50:1 ratio costs 50× the dig time; and ENERGY and MASS are charged
and fed back, the array entering the same rocket equation as the rig, with the
circular dependency solved by fixed-point iteration.

Worked example, M-type at 50% metal / 45% silicate, recovery 0.90:

| feed | delivered $/kg | hold |
|---|---|---|
| 1.0× | $5,135 | 90% full, in-situ ratios |
| 2.0× | $7,081 | 90% metal |
| 2.2× | $7,567 | 100% metal, saturated |
| 5.0× | $7,567 | no further gain |

The saturation ratio is `1/(frac_best × recovery)`, which is what sets
`target_ratio`.

New config: `use_beneficiation`, `beneficiation_recovery`,
`max_concentration_ratio`. `delivery_destination` is not new, but it changes
meaning here, from a Stage 2 price label Stage 4 ignored into the architecture
selector Stage 4 honours.

New output columns: `delivery_destination`, `delivery_arch`, `returns_to_earth`,
`flies_tps`, `beneficiation`, `feed_processed_kg`, `concentration_ratio`,
`delivered_value_usd_per_kg`, `best_phase_usd_per_kg`, `purity_bound_binds`,
`payload_mix`, `payload_dominant_phase`, `payload_dominant_frac`,
`processing_power_w`, `power_system_kg`, `power_w_per_kg_at_target`,
`hardware_total_kg`, `power_system_cost_usd`.

**`1.6.0`  SURFACE DESTINATIONS: `lunar_surface` and `mars_surface`**, paired
with mineral_value v1.4.0 and transportation v1.5.0. The three existing
destinations are unchanged and an `earth_surface` run is still bit-identical to
v1.4.0.

- Lunar surface is cislunar capture plus 2.6 km/s of NRHO to LLO to surface,
  entirely propulsive. No TPS: there is no atmosphere, so
  `use_aerocapture_return` is ignored exactly as for cislunar.
- **MARS IS A DIFFERENT JOURNEY, not a discounted Earth return.** New
  `_asteroid_to_mars_dv_km_s` runs the same patched-conic treatment but
  terminates the heliocentric transfer at Mars' orbit (1.524 AU) rather than
  Earth's, so the departure burn, the arrival v_infinity and the capture into
  Mars' well are computed separately. Modelling it as "Earth return minus
  something" would have hidden the interesting part: plenty of NEAs have aphelia
  near Mars and are genuinely more accessible from a Mars base than from Earth.
  Aerocapture IS available at Mars and is worth several km/s, so `mars_surface`
  carries TPS where `lunar_surface` cannot.
- Surface deliveries carry a $200k/kg lander, Stage 3's new row, rather than a
  $60k/kg berthing adapter or a $150k/kg re-entry capsule; a lander flies itself
  down.

New Δv legs on `asteroid_transfer_dv_km_s`: `ret_lunar_surface_prop`,
`ret_mars_surface_aero`, `ret_mars_surface_prop`, `v_inf_mars`,
`dv_depart_for_mars`.

**`1.7.0`  MODELLING COMPLETENESS: five things the pipeline got for free.**
Unlike v1.5.0 and v1.6.0 these are CORRECTIONS rather than new options: they
default ON and every number moves. Paired with mineral_value v1.5.0 and
transportation v1.6.0.

- **LOW-THRUST TRIP TIME.** Electric propulsion paid a Δv penalty but flew its
  burns instantly on power it never carried. A thruster's power fixes its
  thrust, `T = 2·eta·P/(Isp·g0)`, so burning `m_prop` takes
  `m_prop(Isp·g0)²/(2·eta·P)`: high Isp buys propellant mass at a QUADRATIC cost
  in time-or-power. The EP stage is now sized to finish inside
  `ep_target_thrust_yr`, its array (1/r²) and thruster/PPU mass enter the rocket
  equation, and the thrusting time enters mission duration. Validated against
  Dawn: 5.0-9.3 yr predicted at its 2.2-3.0 AU operating distance against ~5.9
  yr actually flown. This was load-bearing: v1.6.0's headline Mars result was a
  **1,500** s Hall thruster that would have needed 48 kW and a 4-tonne array at
  2.26 AU.
- **LAUNCH WINDOWS.** Departure needs phasing and alignments recur at the
  synodic period, so the expected wait after mining is half a period. It
  punishes NEAs hardest: a body at a = 1.05 AU has a 10-year synodic period with
  Earth against 1.3 years for a main-belt object. Δv accessibility and TIME
  accessibility pull in opposite directions and only one was modelled.
- **BOUND-WATER LIBERATION.** C/B/D "ice" is water in phyllosilicates, baked out
  at ~700 K rather than scooped: 2,500 Wh per kg of water. It was being
  extracted free and sold at full launch-cost-avoided.
- **LEARNING CURVE.** Wright's law at 85% on the per-mission articles (capsule
  or lander, power system). The amortised mining rig is excluded, being one
  shared unit rather than N built. Exactly 1.0 at
  `nre_amortization_missions = 1`, so a single-mission run is untouched.
- **MARKET SATURATION.** `P/P0 = (1 + Q/Q_market)^(-1/eps)` against Stage 2's
  `annual_market_kg`. Returning 180 t/yr of platinum doubles world supply and
  quarters the price; delivering 6.6 t/yr of water to a 20 t/yr Mars base cuts
  it to **0.57**. Without this the "fly more missions" lever had no stopping
  point.

New config: `model_low_thrust_time`, `ep_target_thrust_yr`,
`max_mission_duration_yr`, `model_launch_windows`, `model_water_liberation`,
`learning_curve_rate`, `model_market_saturation`, `demand_elasticity`.

New output columns: `is_electric`, `ep_power_w`, `ep_system_kg`, `ep_thrust_yr`,
`synodic_period_yr`, `launch_window_wait_yr`, `water_liberated_kg`,
`saturation_multiplier`, `learning_curve_factor`.

**`1.8.0`  MODELLING COMPLETENESS, PART 2: four more corrections, all default
ON.** Paired with mineral_value v1.6.0 and transportation v1.7.0.

- **RIG SERVICE LIFE AND TERMINAL VALUE.** The rig was amortised across
  `nre_amortization_missions` with no upper bound, so a programme could spread
  one machine across 100 missions of two years each: 200 years of duty from
  something chewing rock. A 15-year life now CAPS the amortisation, and the cap
  makes long-stay programmes markedly MORE expensive rather than less; at a
  2-year stay one rig serves 7 missions, not 100, so the per-mission charge is
  13.8× what the old flat division gave. Life left when the programme ends is
  credited at the salvage fraction (0.50), but only when
  `nre_amortization_missions > 1`: a rig parked at an asteroid nobody revisits
  is stranded rather than an asset, so a single-mission run is unchanged.
- **MISSION RELIABILITY.** Revenue was certain. Expected revenue is now
  `p_launch(0.97) × exp(-T/MTBF)(30 yr) × p_mining(0.75)`, about 0.62 for a
  5-year mission. COSTS are charged in full, which is the correct treatment, and
  launch insurance replaces hardware rather than revenue, so there is no double
  count. `p_mining` is the honest one: nobody has ever sustained-mined an
  asteroid, and regolith-contact mechanisms are where deep-space missions fail.
- **CRYOGENIC BOIL-OFF.** Return propellant sits in the tank from launch to the
  departure burn, i.e. years. Hydrolox loses 0.05%/day even actively cooled, so
  a 5-year hold means loading ~2.5× what the rocket equation burns. Folded into
  an effective return Δv, which leaves the closed-form cascade exact: since
  `m_return_prop` scales with `(R-1)`, inflating that term by k is
  `R_eff = 1 + (R-1)k`. ISRU is exempt. Without this, hydrolox won long missions
  it could not physically store propellant for.
- **IN-SPACE MANUFACTURING** is costed in mineral_value v1.6.0 rather than
  hidden inside the 0.70 utility factor: ~$230/kg for metals, energy at
  $6.08/kWh plus $200/kg of amortised refinery.

New config: `model_rig_service_life`, `model_reliability`,
`model_propellant_boiloff`.

New output columns: `p_success`, `boiloff_factor`, `dv_ret_effective_m_s`,
`rig_terminal_value_usd`, `missions_sharing_rig`.

**`1.9.0`  RELIABILITY GROWTH**, the one place the model had been pessimistic
rather than optimistic. `p_mining` was pinned at its first-of-kind 0.75 however
many missions a programme flew, and a fleet that has flown ten rigs has found
and fixed failure modes the first one discovered the hard way.

Duane / AMSAA: `q(n) = q_first · n^(-alpha)`, alpha = 0.30 from MIL-HDBK-189's
active-growth band, capped at a 0.95 mature ceiling because growth is
asymptotic; no heritage makes a machine grinding rock in vacuum certain to work.
Reported as the MEAN over missions 1..N rather than the terminal value, because
that is what the rest of the cost model needs: NRE and the rig are amortised
across the whole programme, so per-mission expected revenue must use the
programme average, and quoting the last mission's reliability would credit every
mission with heritage only the last one has.

| N | `p_mining` |
|---|---|
| 1 | 0.750, unchanged, so single-mission runs are bit-identical to v1.8.0 |
| 10 | **0.838** |
| 100 | **0.912** |

Launch and cruise reliability deliberately do not grow: launch vehicles are
already mature, and MTBF is a duration exposure rather than a heritage question.

New config: `model_reliability_growth`.

New output column: `p_mining`.

**`1.9.1`  first-of-kind mining success recalibrated 0.75 to 0.85.** The old
figure was counted from failures alone (OSIRIS-REx's jammed flap, Hayabusa's
dead projectile, Philae's harpoons) with none of the successes, which is
selection bias. The full regolith-contact flight record is 10 clean successes
(Apollo, Luna 16/20/24, Stardust, Phoenix, Curiosity, Hayabusa2, OSIRIS-REx,
Perseverance, Chang'e 5 and 6), one partial (Hayabusa returned its sample
despite the sampler failing) and two failures (Philae's harpoons, InSight's
mole): 11/13 = 0.85, or 0.77 if Hayabusa is counted as a loss. 0.85 is taken
because Hayabusa did return its sample. Sustained-operation risk is NOT
double-counted here; none of those missions was sustained mining, and the
exposure is already carried by the spacecraft MTBF term.

Effect: P(success) on a 5-year mission rises 0.62 to 0.70, and every
cost/revenue ratio improves ~13%.

**`1.10.0`  PER-ASTEROID ARCHITECTURE SEARCH**, plus three physical corrections
it exposed. Full write-up: [calc v1.10.0](#calc-v1100). Return mode is chosen
rather than set; rendezvous apsis is searched rather than ruled; ISRU becomes
physical and per-asteroid; boil-off uses the real hold time; and the
earth-surface propulsive return pays its deorbit burn (+100 m/s).

New config: `optimise_architecture_per_asteroid`.

New output columns: `aerocapture_return`, `isru_return`, `isru_propellant_kg`,
`isru_feed_kg`, `rendezvous_apsis`.

**`1.10.1`  performance only, no number in this module's output changes.** Full
write-up: [calc v1.10.1](#calc-v1101). The main loop becomes parallel, catalog
rows become dicts in the hot path (1.73×), and the five ops-table constants the
sizing loop needs are memoised (a further 1.09×). Net ~1.9× per core, ~7×
wall-clock on 12 threads.

New config: `parallel_workers`.

**`1.11.0`  STORAGE, AND A MUCH WIDER CATALOG.** Full write-up:
[calc v1.11.0 / transportation v1.9.0](#calc-v1110--transportation-v190).
Propellant tankage enters the rocket equation; the maturity gate applies to
propellants; the RTG row is finally read; orbital refuelling is charged (an item
later gated off as a charge against a scenario this module does not have); ISRU
is no longer hydrolox-only; and lunar-origin launch systems are excluded
structurally rather than by status, since their payload columns are annual
throughput and reading them would be a unit error rather than merely optimism.

New config: `model_tank_mass`, `operational_propellants_only`,
`allow_rtg_power`, `rtg_max_power_w`. The first and third each restore the
previous release exactly when set False, which is the diff to run if a number
here ever looks wrong.

New output columns: `tank_mass_frac`, `m_tank_return_kg`, `m_tank_outbound_kg`,
`propellant_storage_class`, `power_source`, `tanker_flights`, `tanker_cost_usd`,
`isru_feed_material`.

**`1.12.0`  a realism audit; every item moves the answer the same way, WORSE.**
Full write-up:
[calc v1.12.0 / transportation v1.10.0](#calc-v1120--transportation-v1100). Full
catalog at cislunar, raw 31.7712× to 33.2342× (+4.60%) and beneficiated
22.4665× to 23.9169× (+6.46%); cislunar is still the best case and its winner is
unchanged (7753 B, now concentrating **5.311**×).

⚠️  **The ratios are not the headline.** Evaluable rows HALVED, ~31,000 to
~15,500, because half the catalog was closing its mass budget on a micronewton
thruster sized as a cargo tug. Those missions were never physical, and any
per-row comparison against a v1.11.0 catalog compares different populations.

New config: `escape_direct_launch`, `max_payload_accel_g`.

New output column: `tank_cost_usd`.

**`1.13.0`  POPULATION RELEASE.** Full write-up:
[catalog v1.1.0 / calc v1.13.0](#catalog-v110--calc-v1130). No change to the
mission model at all: not one term, coefficient or search axis moved, and a run
over the same rows produces the same numbers. What changed is how many rows
arrive and which ones a cap keeps. `eval_row_cap` defaults to 0 (evaluate
everything) instead of 5,000, and a capped run now SAMPLES rather than
truncating, because the catalog arrives sorted by semi-major axis and `.head(n)`
returned the innermost n bodies. Stride is deterministic (`np.linspace` over
positions, no RNG), so v1.10.1's serial/parallel byte-identity survives.

⚠️  **This changes the numbers any CAPPED run produces.** It does not change an
uncapped one, which is every figure on record.

New config: `eval_row_sampling`.

**`1.14.0`  realism audit; containment, eclipse power, the RTG objective and
saturation against N.** Full write-up:
[calc v1.14.0 / transportation v1.11.0](#calc-v1140--transportation-v1110). Five
findings, of which the first three share a shape: a term written down as missing
and then quoted as a known limitation until being written down was mistaken for
being fixed. Also: `schema_check` now checks Stage 3 ROWS as well as columns,
the ops table being row-keyed, so a missing figure was invisible to a column
test.

New config: `model_eclipse_power`, `default_rotation_period_h`,
`max_dark_period_h`, `model_volatile_containment`.

New output columns: `solar_w_per_kg_bare`, `array_oversize_factor`,
`dark_period_h`, `dark_period_clamped`, `rotation_period_h`, `cargo_water_kg`,
`containment_frac`, `m_containment_kg`, `concurrent_missions`.

**`1.14.1`  performance only, no number changes.** Full write-up:
[calc v1.14.1](#calc-v1141). The search spent ~85-94% of itself proving missions
infeasible: profiled at cislunar, of 134,538 calls to `_evaluate_combo_at_ratio`
for 200 raw asteroids only 8,292 reached the cost model, 6.2%, and beneficiated
only **19,445** of **266,584**, 7.3%. The fixed point's first iteration is its
most optimistic one and is closed form, so `_combo_can_close` evaluates that
condition up front; and it is independent of two axes the loop was re-running it
for, since pass 1 can see neither `power_mode` nor the concentration ratio.
Measured at cislunar, **70.6%** of raw (combo × dv × ISRU) tuples pruned and
69.5% of beneficiated ones, with ZERO of them producing a result when solved in
full. Per-body constants that were re-derived per candidate move onto
`AsteroidContext`.

New config: `prune_infeasible_combos` (default True; off restores the v1.14.0
search exactly, and is the diff to run if an output ever moves).

New stdout line: the pruned-candidate count, so a population where the
pre-filter stops firing is visible rather than silent.

**`1.14.2`  performance only, every number identical to `1.14.1`.** Full
write-up: [calc v1.14.2](#calc-v1142). Scalar arithmetic was going through
numpy, seven ufunc dispatches per call to a function invoked **496,000** times
per 150 beneficiated asteroids; the knapsack re-sorted the same phase list
~2,100 times per asteroid; six per-propellant constants and one per-vehicle were
re-parsed per surviving candidate; and the pre-filter turns out to be monotone
in launch capacity, so seventeen vehicles were re-deriving one propellant's
exponentials. Raw 2.70 s to 1.13 s (2.39×), beneficiated 9.19 s to 4.51 s
(2.04×), 124 columns identical and sha256 matching in both.

**`1.15.0`  programme scale becomes a searched axis, and the rig wears out on
something other than a calendar.** Full write-up:
[calc v1.15.0 / transportation v1.12.0](#calc-v1150--transportation-v1120).
Paired with transportation v1.12.0. Measured on the full 1,554,353-row catalog
at cislunar, raw, both cells in one process: search OFF 26.7863× in 1,306 s
(2021 CX5, New Glenn, xenon, N=1), search ON 14.1730× in 1,978 s (2021 CX5, New
Glenn, iodine, N=5). **2,393** rows (0.37%) sit AT `max_fleet_ships` and are
flagged on stdout; those are bodies with no finite market, where the objective
is monotone and the ladder's top rung is where the loop stopped rather than an
optimum.

New config: `model_rig_trip_limit`, `optimise_programme_scale`,
`max_fleet_ships`, `programme_search_steps`.

New output columns: `programme_missions`, `fleet_ships`, `trips_per_ship`,
`rig_trips_calendar_cap`, `rig_trip_limit_binds`, `programme_options_priced`.

**`1.16.0`  PROGRAMME CALENDAR TIME.** Full write-up:
[calc v1.16.0](#calc-v1160). A programme took years and was charged for none of
them, and that was the last item this module's own config comment named as an
open gap. The amortised lines were carried for free; cadence is the dig or the
window, whichever is slower; the band argument is retired and the search is 2-D;
and `missions_sharing_rig` is derived from the fleet.

⚠️  **Inert at W = 1, hence at N = 1**, hence on every committed cell except the
N = 10 / N = 100 curve.

New config: `model_programme_calendar` (default True; False restores v1.15.0
exactly, in all four respects).

New output columns: `missions_per_ship`, `campaign_cadence_yr`,
`cadence_window_bound`, `programme_span_yr`, `programme_calendar_multiplier`.

**`1.17.0`  DEFAULTS: beneficiation ON, programme search ON.** Full write-up:
[calc v1.17.0](#calc-v1170). No model term, coefficient, table value or search
axis moved; an explicitly configured run is bit-identical to v1.16.0. What moves
is what you get when you configure NOTHING, which is the whole point of the
bump.

⚠️  **A default run no longer reproduces the older tables**, because almost all
of them are N = 1 raw. Both flags restore them, and both OFF cells were
re-measured on the full catalog on 2026-08-11 and reproduce exactly.

No new config field and no new column; two defaults flipped.

**`1.17.1`  performance only, every number identical.** Full write-up:
[calc v1.17.1](#calc-v1171). The first stamp aimed at the COST cascade rather
than the mass cascade, because v1.17.0 made `optimise_programme_scale` a default
and the ladder prices a median of 40 options per candidate, so every per-call
cost in `mission_cost_usd` is multiplied by forty. `_ops_cost_constants` memoises
the 22 Stage 3 rows the cost cascade reads, `_ops_value` having run **8.06**
million times on a 150-row beneficiated-plus-search sample; `optimal_payload_mix`
gains a `want_phase` short circuit, because `_cargo_water_kg` is **97.3%** of
that function's callers and reads ONE key of the mix;
`AsteroidContext.cargo_ice_frac` stops being re-derived per candidate;
`mission_cost_usd` gains `totals_only=True`; `rig_trips` is passed in; and
`delivery_architecture` is memoised on its raw argument, **458,337** calls to
normalise one string, with the warning path deliberately not memoised so an
unknown destination still shouts every time.

**`1.17.2`  performance only, every number identical.** Full write-up:
[calc v1.17.2](#calc-v1172). `mission_cost_usd` splits into
`_mission_cost_prologue` and `_mission_cost_tail`; the market-saturation sum is
memoised per FLEET; and `max(1, missions_sharing_rig)` is computed once instead
of three times.

🚨  **v1.17.1's "what this release does NOT close" named the split and REFUSED
it**, on the grounds that it re-associates the final sums. The premise is right
and the conclusion does not follow, and the distinction is the whole release;
see `_mission_cost_prologue`'s docstring.

**`1.17.3`  dead code and duplication removed, every number identical.** Full
write-up: [calc v1.17.3](#calc-v1173). `low_thrust_burn_time_yr` and
`asteroid_dv_m_s` deleted, both without a caller; `_tank_frac_per_kg` reduced to
one derivation with two readers, which v1.14.2 had CLAIMED to do and had in fact
only moved the second copy; `_phase_prices` / `_pgm_enrichment` folded from three
walks of `FRACTION_TO_MINERAL` into one generator, with
`asteroid_bulk_value_usd_per_kg` deliberately not folded in; and five dead slots
of the `ctx.ops` unpack `_`-prefixed rather than removed, the tuple's ORDER being
the contract with `_ops_sizing_constants`.

⚠️  **Its section comment carries the DAWN VALIDATION** (5.0-9.3 yr predicted at
2.2-3.0 AU against ~5.9 yr flown, and 1.0 yr if the 1/r² term is lost), which is
load-bearing and was KEPT, re-anchored on `ep_power_required_w`. Do not delete
that comment on the grounds that the function it sat above is gone.

**`1.17.4`  performance only, every number identical.** Full write-up:
[calc v1.17.4 / catalog v1.1.1](#calc-v1174--catalog-v111). The load was never
profiled and was the biggest single item in the run; the pre-filter gains a
second stage, the big one; `_calendar_multipliers_cached` answers what
`programme_calendar_multipliers` was asked **369,166** times for at most `trips`
distinct answers; `_iter_row_dicts` replaces `iterrows()`; and
`_ep_device_consts` / `_ep_stage_kg` are extracted so the new filter sizes the
stage off ONE definition rather than a second copy.

**`1.17.5`  performance only, every number bit-identical to `1.17.4`.** Full
write-up: [calc v1.17.5](#calc-v1175). The rig shares and calendar multipliers
share one cache entry; the two O(N) memos move to `functools.lru_cache`, which
hashes in C; `_objective_key`'s string normalisation is memoised in
`_selects_on_profit`; `isru_feed_kg_per_kg_propellant` splits into
`_isru_propellant_consts`, four rows in five having fallen through to a legacy
name test to conclude "no", **48,600** of **62,018** calls on a 150-row sample;
and `AU_KM` is removed as dead.

**`1.17.6`  performance only, every number bit-identical to `1.17.5`.** Full
write-up: [calc v1.17.6](#calc-v1176). The first perf release here that lands on
the per-row walk rather than on the search. Composition is a per-taxonomy fact;
`_infeasible` stops being a nested def rebuilt on all 500,860 calls of the
hottest function in the mass cascade; the programme LADDER is a function of
`trips` and the config, and `programme_options` plus `fleet_refinement` were
rebuilt per surviving candidate, **10,741** times per 150-row sample, for one of
a handful of answers; one per-propellant cache entry replaces four lookups; and
five reliability ops rows and the ranking objective resolve once.

**`1.17.7`  MEMORY, not speed.** Full write-up:
[calc v1.17.7 / transportation v1.12.1](#calc-v1177--transportation-v1121). The
first stamp here that fixes a defect nothing would have noticed until a
full-catalog run ran out of RAM. `_CALENDAR_CACHE`, now
`_calendar_multipliers_cached`, was the ONE memo in this module keyed on a
per-candidate float, so it grew LINEARLY with the catalog at
~45 entries per row, projecting to ~70 M entries and 11-18 GB against a
documented run peak of ~6 GB. Now `lru_cache(maxsize=1024)`, which is also
FASTER, because `lru_cache` hashes in C rather than building a key tuple in
Python: **180.1** to **91.0** ns a hit, and a bounded `lru_cache` is not
measurably slower than an unbounded one (**93.4** ns), so bounding it is not a
trade against speed.

Second item, unrelated: `_load_csv` reads with `low_memory=False`, taken only
because it was MEASURED neutral on the real 1,555,667-row catalog, 0 of 46
dtypes and 0 values changed.

**`1.17.8`  the loader checks its upstream stamp, not just its columns.** Full
write-up: [calc v1.17.8](#calc-v1178). `schema_check` asks whether the Stage 3
columns and rows this version reads are PRESENT, and passes cleanly on a catalog
whose VALUES are a release out of date, because editing a density or a boil-off
rate leaves the schema identical. New `stamp_check` compares the transportation
`pipeline_version` stamped in each Stage 3 CSV against the Stage 3 in this
process, which needed no new column because Stage 3 has stamped its CSVs all
along.

⚠️  **A diagnostic, not an import**: `TRANSPORT_CONFIG` exists only when both
modules share a process, so a standalone `calc.py` run stays silent rather than
inventing a complaint it cannot support.

No config or column change; the stamp moves so a catalog still names the code
that built it.

**`1.18.0`  the `mars_orbit` delivery architecture.** Full write-up:
[calc v1.18.0 / mineral_value v1.8.0 / transportation v1.13.0](#calc-v1180--mineral_value-v180--transportation-v1130).
`delivery_destination` accepts a sixth value. No new config field and no new
output column; every column a `mars_orbit` run writes already exists.

- `DELIVERY_ARCHITECTURES` gains `mars_orbit`: `aero_allowed` **True**
  (aerocapture into the ellipse, which Odyssey and MRO flew for real at Mars),
  and **no `needs_lander`**, so the return vehicle is billed as a $60k/kg
  berthing adapter rather than the $200k/kg lander `mars_surface` pays for.
- `_asteroid_to_mars_dv_km_s` gains two keys, `ret_mars_orbit_prop`
  (departure + a 1-sol capture) and `ret_mars_orbit_aero` (departure + the
  aerobrake trim). Nothing existing is re-associated.
- Four module constants describe the depot orbit: `R_MARS_1SOL_PERIAPSIS_KM`,
  `R_MARS_1SOL_APOAPSIS_KM`, and the two velocities precomputed from them.
  They are constants of the DEPOT, not of the arriving candidate, so they are
  resolved once at module scope; that function runs twice per catalog row, and
  per-call re-derivation of a per-destination constant is defect class 3.

The aero leg is charged at `DV_AEROBRAKE_TRIM_KM_S` (100 m/s), which is
**conservative** at Mars: the real periapsis raise out of the atmosphere, taken
at a 37,189 km apoapsis, is ~12 m/s. An existing sourced constant was preferred
to a new invented one for a term this far inside the departure burn.

**Bit-identity, measured rather than argued.** Across a 270-point grid of
orbital elements, a 0.6-5.2 AU x e 0.0-0.95 x i 0-80 deg, **6,930 pre-existing
leg values compare bit-for-bit against v1.17.8, zero mismatches**, with the two
new keys the only difference. No `mars_orbit` cell has been run.

**`1.19.0`  the `geo` delivery architecture.** Full write-up:
[calc v1.19.0 / mineral_value v1.9.0 / transportation v1.14.0](#calc-v1190--mineral_value-v190--transportation-v1140).
`delivery_destination` accepts a seventh value. No new config field and no new
output column.

- `DELIVERY_ARCHITECTURES` gains `geo`: a depot, so a berthing adapter and no
  lander, and `aero_allowed` **True**, which is what separates it from
  `cislunar` directly below it in that table.
- `_geo_capture_dv_km_s` is new and is a **search, not a formula**: it prices a
  direct capture at the GEO radius against an Oberth capture at perigee plus a
  circularisation, and takes the cheaper. Neither always wins; the crossover is
  v_inf = 3.585 km/s.
- `_circularise_at_geo_km_s` combines the speed change and the plane change by
  the law of cosines. Adding them would overstate every GEO arrival.
- `_transfer_legs_for_apsis` gains `ret_geo_prop` and `ret_geo_aero`. The aero
  leg is **flat in v_infinity** at `DV_GEO_AEROCAPTURE_ARRIVAL_KM_S` = 1.737
  km/s, because drag removes whatever arrival energy there was and what is left
  is a circularisation.
- Nine module constants describe the orbit and the transfer ellipse, all
  resolved at import: they are constants of the ORBIT, and this function runs
  twice per catalog row on every destination.

Bit-identity re-verified on the same 270-point grid: **6,930 pre-existing leg
values, zero mismatches**. No `geo` cell has been run.

**`1.19.1`  `stamp_check` compared every catalog against Module 3.** Full
write-up: [calc v1.19.1](#calc-v1191). Console output only; no column, no
field, no CSV byte.

- `_CATALOG_PROVENANCE` is new: catalog key to (stage, config global name).
  The config is resolved through `globals()` rather than referenced, because a
  standalone `calc.py` has none of the upstream configs.
- `load_all_catalogs` gained an **assert** that the map names exactly the
  catalogs it builds. It lives in the loader, not the check, because the loader
  is where the definition and the description can drift apart.
- `stamp_check` compares each file against the module that wrote it, names the
  right stage in the message, reports a key with no provenance entry instead of
  skipping it, and no longer instructs the reader to re-run a stage.

**`1.19.2`  `mars_orbit` phased its launch windows against Earth.** Full
write-up: [calc v1.19.2](#calc-v1192). No config field and no output column;
`synodic_period_yr`, `window_wait_yr`, `campaign_cadence_yr` and everything
downstream of them **change at `mars_orbit` only**, and are bit-identical at
the other six destinations.

- `DELIVERY_ARCHITECTURES` gains a required `window_phasing_au` on every entry:
  `A_MARS_AU` for `mars_orbit` and `mars_surface`, `1.0` for the five that ride
  Earth's orbit. Asserted at import rather than defaulted, so a destination
  added without it fails on the way in.
- `window_phasing_au(destination)` is new and reads that field back. It
  replaces a `== "mars_surface"` conditional that existed in two places, one
  the real computation in `AsteroidContext` and one the pre-filter's diagnostic
  probe, which had to agree and were free not to.

**`1.20.0`  both insurance premiums are off.** Full write-up:
[calc v1.20.0](#calc-v1200). One new config field and no new output column;
`liability_cost_usd` and `launch_insurance_cost_usd` are **0.0** on a default
run, and every cost, ratio and rank downstream of them moves at every
destination.

- `charge_insurance` is new in `CalcConfig` and defaults **False**. It is the
  only cost flag in the module that is off because the charge is out of SCOPE
  rather than incorrect; `charge_tanker_flights` is the other shape, gated
  because this module has no scenario the charge belongs to.
- `_mission_cost_prologue` zeroes `liability_cost` and `launch_ins_raw`
  immediately after the `_ops_cost_constants` unpack, not at their two use
  sites, so the three sums `_mission_cost_tail` must keep written out term for
  term are untouched. Adding 0.0 to a finite float is exact, which is why
  `charge_insurance = True` is bit-identical to 1.19.1 rather than merely equal
  to it.
- The Stage 4 preview banner gains an `Insurance` line, beside `Programme` and
  `Calendar`.
- **Module 3 is not touched and its two rows are still read.** No Stage 3
  re-run, no CSV schema change, and nothing in `_MODULE3_REQUIRED_OPS` moves.

**`1.21.0`  constant prices, and a capacity ceiling that binds quantity.** Full
write-up: [calc v1.21.0](#calc-v1210). One config field REPLACED rather than
added, and **two new output columns**; a default run's ratios, fleet sizes and
payload mixes all move, at every destination except `earth_surface`.

- `model_market_saturation` (bool) is **gone**, replaced by `market_model`
  (str), defaulting `"capacity_cap"`. The four legal values are exported as
  `MARKET_MODELS` so the dashboard's dropdown resolves from the module rather
  than from a second list; `_market_mode()` validates and **raises** on an
  unrecognised value rather than defaulting to one.
  `market_model = "elasticity"` is the old `True`, and reproduced every figure
  measured from v1.14.0 to v1.20.0 -- until calc `1.21.1` fixed a defect that
  was in the curve as well; see [calc v1.21.1](#calc-v1211).
- `demand_elasticity` is unchanged and is now read **only** in `"elasticity"`
  mode.
- New output columns: `market_clearing_fraction`, `unsold_payload_kg` and
  `market_model`. The first two sit beside `saturation_multiplier` rather than
  replacing it, because a PRICE multiplier and a QUANTITY clip are different
  claims; `saturation_multiplier` stays 1.0 in every mode but `"elasticity"`.
  **An archived CSV without these three columns is a pre-1.21.0 run**, which is
  the fastest way to tell one.
- **`market_model` is stamped into every row**, for the reason
  `delivery_destination` and `pipeline_version` are: it identifies the run. The
  same code now gives four answers 20% to 49% apart, so a version stamp alone
  no longer says what produced a catalog. It is NOT provenance and
  `verify.py` does not strip it before hashing: `catalog_date` and
  `pipeline_version` are stripped because they move without the model moving,
  and this moves only when the model does.
- `capacity_allowance_kg()` and `_delivery_window_yr()` are new. The window is
  `[duration + (N-1) x cadence/F] / N`, so `cap x mission_duration` at N = 1
  and `cap x cadence/F` in the limit.
- `optimal_payload_mix()` takes an optional `caps` mapping: per-phase upper
  bounds, which make it a BOUNDED fractional knapsack, still solved exactly by
  the same greedy walk. `caps=None` is bit-identical to the pre-1.21.0 walk.
- `_capped_sale_value()` is new and handles the raw cargo, which cannot be
  reshaped.
- `programme_options()` returns `[(1, 1, 1)]` in `"single_mission"` mode, and
  `_programme_ladder_cached`'s memo key gains the market model because of it.
- The monotone-ladder warning now fires on `market_model = "unbounded"` as well
  as on `model_rig_service_life = False`. Those are the two ways to leave the
  objective monotone in N and only one of them was guarded.
- `market_mode` is resolved once per asteroid in `evaluate_asteroid` and
  threaded like `markets`, rather than derived per candidate. See below; it is
  a performance fix for a cost this release introduced, and it is bit-identical
  (all eight cell hashes, both market models).
- **Stage 2 is not touched.** No `annual_market_kg` change, no schema change,
  no re-run: the ceilings the cap reads are the ones already in the catalog.

**`1.21.1`  the ceilings recalibrated; the levels do not move.** Full
write-up: [calc v1.21.1](#calc-v1211). No config field and no output column;
one cell of four moves under `capacity_cap` and the two raw cells move under
`elasticity`.

- `_RESIDUAL_PHASE` and `_PHASE_MARKET_ALIAS` are new, mapping
  `"other (bulk silicate)"` to the `silicates` market it is already priced
  against. `phase_market_kg()` is the single lookup both the sale terms and the
  knapsack caps now go through.
- **No change to `IN_SPACE_ANNUAL_DEMAND_KG`, `_DEMAND_SHARE_BY_CLASS` or
  `ANNUAL_WORLD_PRODUCTION_KG`**, and no Stage 2 re-run. The recalibration
  concluded the levels were already hard-wall numbers; see the release note.
- ⚠️  `market_model = "elasticity"` no longer reproduces v1.20.0 exactly. The
  defect was in the curve as well.

**`1.21.2`  one market was being sold twice.** Full write-up:
[calc v1.21.2](#calc-v1212). No config field and no output column; three of
the four cells move and the beneficiated N = 1 hash does not.

**`1.22.0`  four defaults moved; the ceiling stopped being a wall.** Full
write-up: [calc v1.22.0](#calc-v1220). Three config fields are new, four
defaults change, and one output column is added.

- **New config: `sell_surplus_at_discount`** (True) and
  **`surplus_price_fraction`** (0.5). Under `market_model = "capacity_cap"`,
  mass past a commodity's ceiling now sells at that fraction of full price
  instead of earning nothing. Read by nothing else; the other three market
  models have no ceiling to be past.
- **New config: `model_learning_curve`** (False), gating the existing
  `learning_curve_rate`, which keeps its 0.85 and is now read only when the
  flag is on. The flag is resolved to a RATE in the cost prologue rather than
  carried as a second field, so the prologue tuple's shape and ORDER are
  unchanged -- see the warning on that tuple in `CLAUDE.md`.
- **Defaults changed**: `model_reliability` True -> **False**,
  `apply_wacc_compounding` True -> **False**, and the two new flags above.
  `model_reliability_growth` stays True and is inert while reliability is off;
  `model_programme_calendar` stays True and is inert at a zero WACC.
- **New output column: `surplus_payload_kg`**, mass sold past a ceiling at the
  discount. It is a SECOND column rather than a reinterpretation of
  `unsold_payload_kg`, which keeps its meaning of mass that earned nothing; the
  two are exclusive on any one run and `verify.py` check 7 asserts it. A
  catalog stamped `calc 1.21.x` has no such column, which is how you tell it is
  a hard-wall cell.
- **Internal**: `_capped_sale_value` returns a 3-tuple,
  `(value, unsold_kg, surplus_kg)`, up from 2. `optimal_payload_mix` takes
  `surplus_price_frac` and returns `surplus_kg` in its result dict.
  `_price_programme`'s tuple gains `surplus_kg` at index 10, APPENDED, because
  `_objective_key` reads indices 1 and 2 off it positionally.
- **`verify.py`**: `RESET_FIELDS` is new and `run_cell` puts all five back from
  the dataclass before every cell. Four of the five are this release's, and the
  rule is v1.21.0's: a field joins that list the moment a cell can differ on it.

**`1.23.0`  the depletion cap comes off.** Full write-up:
[calc v1.23.0](#calc-v1230). No config field is added and no output column; one
default changes.

- **Default changed**: `max_mining_fraction` 0.05 -> **1.0**. A mission may
  remove the whole body, and the haul is bounded by the dig rate, the capsule
  volume and the rocket equation instead.
- **No schema change.** `mineable_kg` is still on `AsteroidContext` and
  `max_mining_fraction` is still a config field with the same name, range and
  meaning, so a catalog stamped `calc 1.22.0` and one stamped `1.23.0` carry
  identical columns. **The stamp is the only thing that distinguishes them**,
  which makes this the release where reading the stamp matters most.
- ⚠️  **Both beneficiated cells are bit-identical to 1.22.0**, so a
  hash alone does not tell those two releases apart on either of them. The raw
  cells differ.
- **`campaign/run_cell.py`**: the ledger records `surplus_kg`. `population.py`
  is deliberately NOT updated, because its `usecols` raising on an older
  archive is the behaviour that file wants.
- **`run_pipeline.py`**: four new flags, `--surplus-sales` /
  `--no-surplus-sales` with `--surplus-fraction F`, `--reliability`,
  `--learning-curve` and `--cost-of-capital`, each with a `--no-` partner.
  Same precedent as v1.21.0's `--market-model`: **a field a cell can differ on
  needs a way to say so from the command line**, or the headless path cannot
  express a run the docs instruct the reader to make -- and `campaign/`
  reaches Stage 4 only by shelling out to this file, so without them no future
  campaign could reproduce a 2026-09 cell. Defaults in `--help` are read off
  the dataclass; `--surplus-fraction` is validated by `unit_float` at the flag
  as well as by `market_config_check` in the model. Verified end to end: the
  four together return the raw cislunar sample cell to **25.7233x, 2017 KJ5**.
- **`market_config_check(config)`** is new in `calc.py` and is called from
  `build_profitability_catalog` beside `destination_check`. It refuses a
  `surplus_price_fraction` outside [0, 1].

- `phase_market_key()` is new: the market IDENTITY of a phase, where
  `phase_market_kg()` is its size. It takes `markets` so it resolves the alias
  the same way that function does -- a phase's own Stage 2 row wins, the alias
  is the fallback -- and the two agreeing by construction is the point.
- **`sale_terms` is a 4-tuple**, `(kg, price, ceiling, market_key)`, up from 3.
  Four consumers, all updated. This is the one schema-shaped change in the
  release and it is internal: no CSV column moved.
- `optimal_payload_mix` takes `cap_keys`, and **`caps` is now keyed by market
  and consumed in place** rather than keyed by phase and read. `caps=None`
  and `want_phase` are unchanged and were re-proved bit-identical.
- **No change to `IN_SPACE_ANNUAL_DEMAND_KG`, `_PHASE_MARKET_ALIAS`'s content,
  or any Stage 2 table**, and no Stage 2 re-run. The ceilings are the same
  numbers; what changed is that one of them is now spent once.
- `verify.py` check 6 gained phase-ceiling coverage, and **check 7 was added to
  `verify.py check`**, which had never run it.

# Measurement history

What the numbers used to be, why they moved, and the rule this project keeps
relearning about predicting them. **Every table here names the release and the
catalog it belongs to. If one does not say, do not use it.**

The current answers are in the README:
[Results](README.md#current-results-the-complete-28-cell-matrix) for the model,
[Beneficiation](README.md#beneficiation) for the wall clock.

## Cost/revenue matrices

### The 28-cell campaign, 2026-09

Seven destinations × {raw, beneficiated} × {programme search off, on}, every
cell on the full 1,555,667-row catalog. **28 of 28 cells, 63.2 h of compute,
zero failed measurements.** calc `1.21.2` / mineral_value `1.9.0` /
transportation `1.14.0` / catalog `1.2.0` / master `1.26.0`, 12 workers.

Measured at the **current defaults**: `market_model` `capacity_cap`,
`charge_insurance` False, `use_beneficiation` and `optimise_programme_scale`
True. The current matrix is
[README's](README.md#current-results-the-complete-28-cell-matrix); what is here
is the matrix it replaced and what the difference was worth.

Wall clock per cell, seconds, at 12 workers:

| destination | raw N=1 | raw searched | benef N=1 | benef searched | total |
|---|---|---|---|---|---|
| `cislunar` | 947 | 2,888 | 4,967 | 9,878 | 5.19 h |
| `lunar_surface` | 633 | 1,160 | 3,021 | 7,253 | 3.35 h |
| `geo` | 1,221 | 2,558 | 7,382 | 19,902 | 8.63 h |
| `mars_orbit` | 2,065 | 4,399 | 13,135 | 29,174 | 13.55 h |
| `leo` | 1,426 | 2,583 | 8,558 | 23,335† | 9.97 h |
| `mars_surface` | 1,799 | 3,982 | 12,113 | 25,270 | 11.99 h |
| `earth_surface` | 1,747 | 3,386 | 11,000 | 21,860 | 10.55 h |

† 🚨  **The ledger records 27,817 s for that cell and it must not be quoted.**
The campaign was suspended 5.7 h into it and `run_cell.py` times with a wall
clock, so the frozen 74.7 min is inside the measurement. The pause was measured
from the gap in `memory.csv` rather than estimated, `memwatch` being suspended
by the same call. **`campaign/results.csv` is deliberately not corrected**:
`wall_s` means wall time and that is what it holds, and editing it would put a
derived number in the file that records observations while hiding that the cell
was interrupted. ⚠️  The general trap: a suspend-based pause silently inflates
anything timed across it. Model outputs and CPU time are untouched.

#### The superseded 20-cell matrix, calc v1.17.7 (2026-08-23/24)

Five destinations, 26.1 h of compute, measured with `market_model` at
`elasticity` and **insurance charged**:

| destination | raw, N = 1 | raw, searched | benef, N = 1 | benef + searched |
|---|---|---|---|---|
| `cislunar` | 26.7863× | 15.4272× | 20.5895× | 13.1443× |
| `lunar_surface` | 63.3505× | 38.9904× | 35.8051× | 22.5790× |
| `leo` | 71.1029× | 36.6889× | 48.2714× | 24.4678× |
| `mars_surface` | 74.6748× | 41.8068× | 55.3403× | 30.6818× |
| `earth_surface` | 42,953.98× | 12,977.88× | 25,839.48× | 7,869.88× |

🚨  **Nothing in it is comparable cell-for-cell with the 28-cell matrix**, and
the campaign's own record is under `campaign/archive-2026-08_calc-1.17.7/`.
**Four things moved between them at once**, so no single delta can be
attributed:

| what moved | from | to |
|---|---|---|
| destinations | five | **seven** (`mars_orbit`, `geo` added) |
| `market_model` | `elasticity` | **`capacity_cap`** |
| `charge_insurance` | True | **False** |
| price epoch | 2026-08-23 | **2026-09-09** |

#### What the winner rows did, and what the population did

🚨  **The two disagree, and that is the most reusable finding of the
campaign.** Winner rows moved 8-69%; the beneficiation population medians moved
**0.1 to 2.3 percentage points**:

| destination | benef, winner row | benef population median, 2026-09 | the same, 2026-08 |
|---|---|---|---|
| `cislunar` | −8.4% | **+39.4%** | +39.5% |
| `lunar_surface` | −36.5% | **+66.1%** | +63.8% |
| `earth_surface` | −6.5% | **+77.7%** | +77.7% |

⚠️  The columns use opposite conventions and are not each other's negation:
the median is `median(1 − r)` over the evaluable population, the committed
convention; the winner column is one row against its 2026-08 counterpart.

`capacity_cap` and the insurance removal **reshaped the top of the distribution
and left the middle where it was**. This is the sharpest instance in the project
of *a diagnostic describes the winner, not the search that produced it*: a
headline moving 50% over a median moving 0.1 pp is a statement about one row.

#### The structural change: `W < trips`

| destination | raw searched, 2026-09 | 2026-08 |
|---|---|---|
| `mars_orbit` | **35.99%** | never measured |
| `mars_surface` | 32.73% | 3.71% |
| `cislunar` | 20.86% | **0.319%** |
| `lunar_surface` | 16.07% | 0.225% |
| `leo` | 8.09% | 0.161% |
| `earth_surface` | 0.270% | 0.234% |

Two orders of magnitude more programmes retire a ship with trip life unspent.
Under a hard ceiling the extra campaign cannot be **sold**, where a demand curve
would always have sold it at a worse price. `cislunar`'s fleet median went 2 to
6 and its N median 10 to 30.

#### Invariants, and what the campaign closed

**70 checks, 0 failures**, from `campaign/analyse.py` over the archived cells:
never-worse on all 28 pairings, mass ledger exact to `0.000000000 kg` on every
cell, `N = F × W` on every row of all fourteen searched cells, `W > trips`
never.

✅  **Two long-standing questions closed, neither needing a re-run:**

- `market_clearing_fraction` and `unsold_payload_kg` are not inconsistent.
  `geo` raw N=1 reads 0.9807 clearing beside 8,019 kg unsold of a 61,835 kg
  payload, 1.9% against 13%, because clearing is a share of **gross value** and
  unsold is **mass**. Split deliberately in v1.21.0 so neither column carries
  two meanings; low value in high mass is exactly the GEO story.
- The **650,516** evaluable count quoted for cislunar raw is not a disagreement
  with either campaign. Both report **650,921**, identically. 650,516 belongs to
  a calc v1.15.0 run on a **1,554,353-row** catalog snapshot rather than the
  1,555,667-row one both campaigns used. Different catalog, not different code.

#### How much a price epoch is worth, measured

✅  **The 2026-08 campaign quantified this and the figure is the precedent for
reading the one below.** Re-running its cells 12-14 days after the committed
values, the cells moved in exactly the order the pricing mechanism predicts, and
they are ordered by **how small launch-cost-avoided is, not by distance**:

```
cislunar 0%  =  lunar_surface 0%  =  mars_surface 0%  <  leo 0.004%  <<  earth_surface 1.75%
```

`leo` is the **cheapest** in-space destination to reach, so a terrestrial price
is the largest share of its value and it is the only in-space cell that moves at
all; `mars_surface` is the furthest and does not move. `earth_surface` is priced
straight off live terrestrial quotes, so a fortnight of metal prices is worth
**1.75%** there. ⚠️  **Do not read a small `leo` drift as a regression**, and do
not expect `earth_surface` to reproduce across days.

⚠️  **What the campaign does not support.** Live prices drifted across the seven
Stage 2 fetches, gold by **9.0e-5** and copper by **7.4e-5** relative, with
platinum, palladium and silver identical, because COMEX was trading during the
sitting. That is **three orders below** the 1.75% a fortnight buys at
`earth_surface`, and four below nothing at all in-space. **No cross-destination claim finer than 1e-4 rests on this campaign**;
nothing in the matrix comes within three orders of that. The 2026-08 campaign
could claim identical prices across its five destinations and this one cannot.


The headline number of each release, newest first. Lower is better and 1.0
would be breakeven; none of them reaches it.

🚨 **Every matrix in this section is superseded** by
[the 28-cell matrix](README.md#current-results-the-complete-28-cell-matrix),
which measures every destination × ore × programme-search setting on the full
1,555,667-row catalog on calc v1.21.2. **They are kept for their structure, not
their numbers**, which destination wins and why, what beneficiation does, which
effects the model is sensitive to. Two compounding reasons they cannot be
quoted:

- **catalog v1.1.0 took the population from 89,367 bodies to 1,554,400.** Every
  figure here is "the best mission over the bodies we had", so nothing survives
  a 17× population change, however sound the model was.
- **The model then changed repeatedly.** v1.14.0 alone added containment,
  eclipse power, a searched power source and saturation-vs-programme-size.

### The population re-derivation, 2026-09-14

The 28-cell campaign above extracted the winner row and ran the invariants and
nothing more. Five sections of CLAUDE.md therefore kept carrying **2026-08
`elasticity` figures with insurance charged**, each under a heading saying so:
the propellant shares, the vehicle shares, the rig's two bounds, the cadence and
the saturation diagnostics.

`campaign/population.py` closed that gap without re-running a stage. It reads
each archived cell once with `usecols`, at about 17 s a cell, and derives every
per-cell population table at once. **28 cells, ~10 minutes, no fetch, no
re-run.** The per-cell JSON is committed under `campaign/population/`.

**It reproduces every committed 2026-09 figure it touches**, which is what makes
it a measurement rather than a new harness to have to trust: the four cislunar
objectives (15.3937 / 9.5435 / 14.1071 / 6.6622), all 28 winner bodies, all six
`W < trips` values, the fleet-cap percentages (9.99% raw and 17.77%
beneficiated at cislunar, 100.000% at `earth_surface`) and the `earth_surface`
evaluable counts (784,242 / 912,846).

⚠️  **An archived cell holds evaluable rows ONLY.** `run_cell.py` archives what
`build_profitability_catalog` returns, which is already filtered: cislunar raw
searched is 650,921 rows and 650,921 evaluable. So the denominator question that
CLAUDE.md warns about for "bodies declining to concentrate" does not arise for
any of these tables.

#### What it changed, and it was four conclusions rather than four levels

| claim | status |
|---|---|
| `mars_surface` is the exception to the beneficiated dig/window inversion | **retired**; its beneficiated cells are 46.24 / 53.76, and the inversion is universal across all seven |
| `saturation_multiplier` min/median/max as the saturation diagnostic | **dead**; identically 1.0 on all 28 cells under `capacity_cap` |
| ISRU tracks hydrolox to within 0.03 pp at every destination | **retired**; fails at `earth_surface` (+0.3668 pp), `leo` (+0.2885), `mars_orbit` (-0.0630) |
| iodine wins two beneficiated searched cells | **widened to three**; `geo` joins `leo` and `earth_surface` |
| chemical propulsion reaches 11-15% of three destinations | **four**; `mars_orbit` joins at 14.48-14.55% |
| the cycle bound retires almost every rig | **wrong three ways**; `mars_orbit` is 78.13% calendar beneficiated and 39.37% raw |

🚨  **`mars_orbit` IS THE SECOND CALENDAR-BOUND DESTINATION AND IT INVERTS ON
RAW ORE**, where `mars_surface` needs beneficiation to get there: 39.37% of raw
single-mission rigs are retired by the calendar against 1.20-4.08% at the four
non-Mars destinations. Its cadence is 3.742 yr raw and 4.497 yr beneficiated.

#### The superseded 2026-08 `elasticity` tables

Kept here because this file is where superseded measurements live, and every
table in it names the campaign it belongs to. These are **five** destinations,
`elasticity`, insurance charged, calc `1.17.7`, 2026-08-23/24.

**Which bound retires the rig** (cycle / calendar):

| destination | raw N=1 | raw ON | benef N=1 | benef ON |
|---|---|---|---|---|
| `cislunar` | 96.11 / 3.89 | 98.04 / 1.96 | 57.66 / 42.34 | 75.08 / 24.92 |
| `lunar_surface` | 96.09 / 3.91 | 96.36 / 3.64 | 75.24 / 24.76 | 93.51 / 6.49 |
| `leo` | 98.70 / 1.30 | 98.89 / 1.11 | 49.54 / 50.46 | 77.89 / 22.11 |
| `mars_surface` | 80.99 / 19.01 | 85.24 / 14.76 | 19.21 / 80.79 | 21.44 / 78.56 |
| `earth_surface` | 98.65 / 1.35 | 98.75 / 1.25 | 29.53 / 70.47 | 47.66 / 52.34 |

**What sets the pace** (window / dig), and the median cadence:

| destination | raw N=1 | benef N=1 | cadence raw | cadence benef |
|---|---|---|---|---|
| `cislunar` | 92.31 / 7.69 | 34.13 / 65.87 | 1.384 yr | 2.090 yr |
| `lunar_surface` | 96.21 / 3.79 | 42.73 / 57.27 | 1.384 yr | 1.622 yr |
| `leo` | 88.67 / 11.33 | 25.37 / 74.63 | 1.369 yr | 2.564 yr |
| `mars_surface` | 99.95 / 0.05 | 63.18 / 36.82 | 3.798 yr | 3.990 yr |
| `earth_surface` | 86.48 / 13.52 | 17.03 / 82.97 | 1.369 yr | 3.324 yr |

**`saturation_multiplier` across the searched cells**, the table that is now
inert:

| cell | min | median | max | fleet median | N median |
|---|---|---|---|---|---|
| `cislunar` raw | 0.358439 | 0.812837 | 0.999957 | 2 | 10 |
| `lunar_surface` raw | 0.536206 | 0.830467 | 0.999726 | 4 | 20 |
| `leo` raw | 0.704996 | 0.861486 | 1.000000 | 5 | 25 |
| `mars_surface` raw | 0.354904 | 0.750813 | 0.999996 | 2 | 10 |
| `earth_surface` raw | 1.000000 | 1.000000 | 1.000000 | 64 | 320 |
| `earth_surface` benef | 1.000000 | 1.000000 | 1.000000 | 64 | 320 |

At `earth_surface` the multiplier departed from 1.0 by a median of 2.3e-11 and
at most 2.4e-7, against `cislunar`'s 1.9e-1.

**Programme structure and survivor counts**, the remaining 2026-08 figures that
CLAUDE.md carried until 2026-09-14:

* **`W < trips`, searched cells**: 0.161% (`leo`), 0.177% (`lunar_surface`),
  0.210-0.319% (`cislunar`), 0.234-0.268% (`earth_surface`) and
  **3.705-3.785% at `mars_surface`**. Under `capacity_cap` these are 8.09% to
  35.99%, two orders of magnitude higher, because the extra campaign cannot be
  SOLD where a demand curve would always have sold it at a worse price.
* **`replicated` survivor counts**: zero at `lunar_surface`, 13 raw (0.002%)
  and 327 beneficiated (0.050%) at `cislunar`, 4,710 (0.607%) at `leo` and
  5,479 (0.699%) at `earth_surface`, **12,213 rows across the twenty cells**,
  every one of them FEEP.
* **`cislunar` window-bound share with the search ON**: 95.77% raw and 37.59%
  beneficiated, against 98.04 / 75.08% for the cycle bound on the same cells.

⚠️  The survivor counts are kept for the record and prove nothing about the
gate. CLAUDE.md's "SURVIVAL WAS NEVER THE TEST" is the paragraph that says why:
the count is a statement about the population, and the test is whether one WINS.

**Aerocapture and ISRU, 2026-08**: aerocapture resolved to 0.00% at `cislunar`
and `lunar_surface` in all four cells and **82-98% elsewhere**, rising under
beneficiation at every atmospheric destination. ISRU tracked hydrolox to within
0.03 pp at all five, the pairs being **8.1097 against 8.1106%** at `cislunar`,
exact to four decimals at `lunar_surface`, **1.9493 against 1.9292** at `leo`
and `earth_surface` (hydrolox exceeding ISRU) and **2.0606 against 2.0522** at
`mars_surface` (ISRU exceeding hydrolox).

⚠️  Both of those are retired on seven destinations: aerocapture runs
**37.69-98.36%** because `mars_orbit` declines it about half the time and `geo`
FALLS under beneficiation at N = 1, and the ISRU near-equality fails at
`earth_surface`, `leo` and `mars_orbit`. The current figures are in
[CLAUDE.md](CLAUDE.md#winners-and-what-28-cells-did-to-the-claim).

**Best `replicated` mission per cell**, rank and margin:

| destination | raw N = 1 | raw searched | benef N = 1 | benef searched |
|---|---|---|---|---|
| `cislunar` | 39 (1.29x) | 283 (1.69x) | 8,602 (2.17x) | 12,020 (2.12x) |
| `lunar_surface` | none | none | none | none |
| `leo` | 62 (1.32x) | 1,145 (1.47x) | 1,770 (1.62x) | 19,197 (2.15x) |
| `mars_surface` | 5 (1.06x) | 1, WINS | 73 (1.11x) | 14 (1.06x) |
| `earth_surface` | 7 (1.09x) | 5 (1.07x) | 13 (1.20x) | 10 (1.16x) |

**Propellant, % of evaluable rows.** Two destinations per row-block, left and
right. This is the table CLAUDE.md carried until 2026-09-14; the current one is
in [CLAUDE.md](CLAUDE.md#propellant-and-vehicle-shares-all-twenty-eight-cells-2026-09).

| | raw N=1 | raw ON | benef N=1 | benef ON | | raw N=1 | raw ON | benef N=1 | benef ON |
|---|---|---|---|---|---|---|---|---|---|
| **`cislunar`** | | | | | **`mars_surface`** | | | | |
| xenon | 42.64 | 40.44 | 59.24 | 48.94 | xenon | 57.81 | 49.09 | 59.92 | 47.87 |
| iodine | 25.19 | 26.00 | 17.08 | 26.48 | iodine | 19.94 | 28.51 | 14.71 | 23.23 |
| water ion | 15.58 | 18.44 | 12.54 | 13.80 | krypton | 15.37 | 14.65 | 1.52 | 1.11 |
| hydrolox | 8.11 | 5.29 | 10.34 | 9.80 | methalox | 1.60 | 1.61 | **15.23** | **15.23** |
| krypton | 8.01 | 9.29 | 0.47 | 0.38 | argon | 1.81 | 2.67 | 5.60 | 6.96 |
| **`lunar_surface`** | | | | | **`leo`** | | | | |
| xenon | 42.26 | 37.93 | 47.32 | 37.26 | xenon | 76.04 | 71.36 | 74.85 | **42.14** |
| krypton | 22.64 | 26.31 | 6.40 | 8.51 | iodine | 13.56 | 16.19 | 11.61 | **42.74** |
| water ion | 20.67 | 20.87 | 19.44 | 19.76 | methalox | 1.77 | 1.86 | **11.11** | **11.45** |
| iodine | 10.29 | 10.89 | 24.42 | 31.86 | krypton | 4.36 | 4.83 | - | - |
| hydrolox | 3.76 | 3.57 | 2.12 | 2.26 | hydrolox | 1.95 | 2.06 | 1.20 | 1.58 |
| **`earth_surface`** | | | | | | | | | |
| xenon | 74.67 | 71.57 | 64.03 | **35.50** | | | | | |
| iodine | 13.46 | 16.07 | 20.09 | **47.31** | | | | | |
| methalox | 1.73 | 1.76 | **12.26** | **12.43** | | | | | |
| krypton | 5.46 | 5.70 | 0.90 | 1.51 | | | | | |
| hydrolox | 1.92 | 2.01 | - | - | | | | | |

**Launch vehicle, % of evaluable rows:**

| destination | | raw N=1 | raw ON | benef N=1 | benef ON |
|---|---|---|---|---|---|
| `cislunar` | Falcon Heavy | 66.42 | 71.48 | 64.86 | 36.41 |
| | SLS Block 1B | 31.60 | 25.67 | 30.20 | 25.65 |
| | **New Glenn** | 1.67 | 2.45 | 4.28 | **36.57** |
| `lunar_surface` | Falcon Heavy | 67.98 | 72.53 | 53.73 | 39.19 |
| | SLS Block 1B | 30.96 | 26.03 | 33.10 | 24.24 |
| | **New Glenn** | 0.64 | 1.00 | 10.27 | **28.35** |
| `leo` | Falcon Heavy | 69.55 | 73.98 | 62.81 | 58.76 |
| | SLS Block 1B | 21.33 | 16.39 | 26.71 | 20.05 |
| | New Glenn | 8.80 | 9.28 | 8.57 | 16.81 |
| `mars_surface` | Falcon Heavy | 79.94 | 80.23 | 43.44 | 40.98 |
| | SLS Block 1B | 10.72 | 9.96 | 23.31 | 23.09 |
| | **New Glenn** | 5.70 | 5.52 | 27.68 | **28.63** |
| `earth_surface` | Falcon Heavy | 66.47 | 71.37 | 37.60 | 46.48 |
| | SLS Block 1B | 23.35 | 18.34 | 20.62 | 19.00 |
| | **New Glenn** | 9.86 | 10.07 | 29.88 | 25.55 |

The 2026-08 headline was that iodine overtook xenon at `leo` (42.74 against
42.14%) and won `earth_surface` outright (47.31 against 35.50%), with `methalox`
at 11.11-15.23% of `leo`, `mars_surface` and `earth_surface`, and New Glenn
rising from 1.67% to 36.57% of `cislunar` between raw N=1 and beneficiated
searched.

⚠️  **These two tables are kept VERBATIM rather than summarised, and that was a
deliberate decision under check 10.** Summarising them dropped 109 distinctive
numbers, which the transfer check reported; they are full-catalog population
measurements of five destinations under a market model the project no longer
runs, and nothing else in the repo records them. That is the opposite of the
~210 tokens the release-history split dropped, which were harness ephemera.
**Read every reported loss and decide it deliberately.**

### The destination runtime table, 2026-09-15

No `pipeline_version` moved. Nothing a run writes changed: `MEASURED_CELL_SECONDS`
holds the same four integers it held before, and the only reason it is worth a
section is that **the claim built on top of it was false.**

The 28-cell campaign above measured every destination's wall clock and nobody
sorted the column. `modules/calc.py`, `ui.py`, `run_pipeline.py`, `run.bat`,
`run.sh`, README and CLAUDE.md all said **"cislunar is the CHEAPEST
destination"**;
the campaign's own ledger says otherwise, and had done since the cells landed:

| destination | raw N=1 | raw searched | benef N=1 | default cell | default vs cislunar |
|---|---|---|---|---|---|
| `lunar_surface` | 633 s | 1,160 s | 3,021 s | 7,253 s | **0.73x** |
| `cislunar` | 947 s | 2,888 s | 4,967 s | 9,878 s | 1.00x |
| `geo` | 1,221 s | 2,558 s | 7,382 s | 19,902 s | 2.02x |
| `earth_surface` | 1,747 s | 3,386 s | 11,000 s | 21,860 s | 2.21x |
| `leo` | 1,426 s | 2,583 s | 8,558 s | 23,335 s | 2.36x |
| `mars_surface` | 1,799 s | 3,982 s | 12,113 s | 25,270 s | 2.56x |
| `mars_orbit` | 2,065 s | 4,399 s | 13,135 s | 29,174 s | **2.95x** |

**`lunar_surface` is cheaper on all four cells**, 0.40x to 0.73x, and on the raw
searched cell `geo` (0.89x) and `leo` (0.89x) are cheaper too. Cislunar is the
second-cheapest destination to run, not the cheapest.

🚨  **AND IT WAS NEVER THE CHEAPEST.** The 20-cell campaign's own ledger,
`campaign/archive-2026-08_calc-1.17.7/results.csv`, has `lunar_surface` at
**0.78 / 0.69 / 0.78 / 0.79x** cislunar on calc `1.17.7` in 2026-08. So no new
data arrived and nothing changed under the claim; the column had never been
sorted, in either campaign.

⚠️  **Derived from `campaign/results.csv` with `rc == 0`, which matters.** The
ledger carries **29 rows for 28 cells**: the first `cislunar__benef__search-on`
attempt exited `rc = 1073807364` (`0x40010004`, a Windows Ctrl-C) at 8,011.7 s
and was re-run to completion at 9,877.9 s. Averaging the two, which is what an
unfiltered `pivot_table` does, gives **8,944.8 s** and quietly disagrees with
README by 9%. Filter on the return code before reading that file.

⚠️  **`leo`'s default cell is the one judgement call.** The ledger's 27,817 s
includes a 74.7 min suspension a wall clock cannot see; `campaign/results.csv`
is deliberately left uncorrected and **23,335 s** is the comparable figure.
Summing the corrected table reproduces README's **63.2 h** exactly, which is
what says the correction was applied once and not twice.

**What changed in the code.** `MEASURED_DEST_SECONDS` in `modules/calc.py` now
holds all twenty-eight cells, and `MEASURED_CELL_SECONDS` is **derived** from
its `cislunar` row rather than restated, so the two cannot disagree; the derived
dict reproduces the previous four literals exactly, which is why no banner, no
`--help` string and no output byte moves. `dest_cost_span()` computes the span.

✅  **`_DEST_FACTOR` in `ui.py` is gone, and it was the last hand-typed ratio in
the project.** It read `(2.2, 3.0)` -- `earth_surface` and `mars_orbit` against
cislunar -- presented as the range "the others run longer". The real span is
**0.73x to 2.95x** and straddles one. Its own comment had said "if that table is
ever machine-read, derive it"; it is, so it does.

⚠️  **The user-visible half is what this cost.** The dashboard's Stage 4 blurb
told you to budget 2.2-3.0x for a non-cislunar destination, so a
`lunar_surface` campaign was over-budgeted by a factor of three.

✅  **`verify_docs.py` check 9 now reads the table rather than one row of it**:
all seven README rows, CLAUDE.md's pairs-register row, and the identity between
the two dicts -- **32 cells against 4**. Proved to fail in three directions
before being trusted: a changed dict value, a changed README figure, and a
deleted README row. That is the finding underneath the finding, and it is in
CLAUDE.md as
[the cheapest-destination claim](CLAUDE.md#the-cheapest-destination-claim-survived-because-one-row-of-seven-was-pinned):
**a check that reads one row of a table is a check on that row.**

### The docs harness stopped passing on files it never read, 2026-09-15

No `pipeline_version` moved; `verify_docs.py` builds no stage.

Every check in that file enumerates first-party paths from a static list and
each loop opened `if not os.path.exists(path): continue`. **Seven sites, across
checks 3, 4, 5, 6, 11 and 12**, plus four paired guards in check 7.

Measured rather than argued -- rename `verify_stage1.py` away and run it:

| | present | absent |
|---|---|---|
| check 6 | 35 files checked | **34** |
| check 11 | 486 definitions | **469** |
| exit code | 0 | **0** |

A first-party harness could leave the repo and every docs check would call the
result clean. Nothing printed a skip message, because nothing knew it had been
asked to read a file: the list names a path and the disk says nothing back.

🚨  **Reachable on this working copy WITHOUT deleting anything.** The tree is on
a Drive File Stream mount where an unmaterialised file can read as absent, and
that is how it was found: the first `verify_docs.py` run of the day read **33**
files and the next read **35**, no commit in between, the two invisible files
being `verify_stage1.py` and `verify_stage3.py`. The same session also caught
the mount serving a **stale** `verify_stage3.py` -- four checks on its first run
and six on every later one, on bytes that hash equal to HEAD.

✅  **Closed by `absent()`**, one helper the enumerating checks call. A named
first-party path with no file behind it is a finding and fails the run, on its
own counter: checks 6 and 11 print `N NOT ON DISK` rather than folding it into
"bad lines" or "without one", because a missing file is not a dash error and a
count that quietly shrinks is the most readable-looking failure there is.

Verified in both directions before being trusted: two files hidden gives exit
**1** naming both, restored gives exit **0** and `0 bad lines`.

⚠️  **Check 7 had already met this class and fixed the inner half.** Its own
comment reads *"Not a skip. Both are supposed to be there, and one of them going
missing is the drift rather than a reason to pass quietly"* -- inside an
`if os.path.exists(a) and os.path.exists(b)` that went on skipping silently.
Somebody had the right thought one line too deep.

**Fourth instance of the same sentence in this repo**, after `verify.py`'s
baseline-less `ALL CHECKS PASSED`, `verify_docs.py`'s `SyntaxError`-as-skip, and
`verify_stage3.py` check 4's skip that fired on 100% of runs. This is the first
with no skip message at all. See
[a skip with no message at all](CLAUDE.md#a-skip-with-no-message-at-all-the-file-that-is-simply-not-there).

### The stale working tree became checkable, 2026-09-15

No `pipeline_version` moved; `tree_check.py` builds no stage and fetches nothing.

The day before, this repo recorded a failure and called it unresolved: the Drive
File Stream mount served `verify_stage3.py`'s **first run of the day** an older
copy of itself, which printed **four** checks instead of six and exited `OK`,
with `git status` clean and the file's bytes hashing equal to `HEAD` afterwards.
The sibling fault, same session, is a tracked file reading as **absent**: two
harnesses were invisible to one `verify_docs.py` run and visible to the next.
The note said the habit was the only defence.

**That was wrong, and the reason is the finding.** `git status` is clean
throughout because git's stat cache trusts SIZE and MTIME and never re-reads
content -- the same cache whose other direction is the phantom-dirty tree
`.githooks/drive-restat.sh` repairs. So git's opinion and the file's CONTENT are
two INDEPENDENT readings of one tree, and the failure is exactly where they
disagree:

| content vs index | git status says | reading |
|---|---|---|
| equal | clean | fine |
| differs | modified | somebody edited it; not this |
| differs | **clean** | **nobody edited it and it changed anyway** |
| missing | **clean** | **a tracked file is not there** |

**Reproduced before it was trusted.** Change one byte of a tracked file without
changing its length, restore its mtime, and `git status --short` returns EMPTY
while the content hash moves:

```
git status --short : ''
index blob         : cbc38e60eac6
working-tree hash  : c2651c97a14e
```

⚠️  **Hash through `git hash-object`, never `sha256` of the raw bytes**, which is
what the three commands CLAUDE.md used to recommend did. `.gitattributes` pins
`*.py` to LF and `*.bat` to CRLF and the index stores the normalised form, so
raw bytes disagree with the index for every CRLF file by construction. Measured:
`run.bat` matches its index blob through `hash-object` and does **not** through
`--no-filters`, which is what proves the filter is load-bearing.

✅  **It reads the whole tree rather than a curated list**, which is the previous
day's lesson applied at once: a hand-maintained file list is *a check that reads
one row of a table* wearing different clothes. **147 tracked files, three git
invocations, 0.43 s.**

✅  **And reading is also the cure**, so the check subsumes the manual
prophylactic CLAUDE.md used to prescribe: materialisation is what a read does
anyway, so running it first either catches the stale bytes or forces the mount to
produce the current ones before the harness reads them itself.

**Every harness calls it first and refuses on a finding** -- `verify.py` (all
three subcommands, `baseline` included, because a baseline captured off a stale
tree is a poisoned reference every later `check` is measured against),
`verify_docs.py`, `verify_stage1.py`, `verify_stage3.py` -- and CI runs it
standalone as the control case, where a plain clone can only pass.

**Verified in both directions before it was wired in**, which is the whole point
of the section it is filed under:

| case | result |
|---|---|
| baseline, nothing touched | 147 verified, 0 findings |
| stale read (same size, same mtime) | **1 finding**, names the file and both hashes |
| a normal edit git can see | 0 findings, **no false alarm** |
| a staged edit | 0 findings, **no false alarm** |
| stale file, each of the four harnesses | **exit 1**, all four, each naming the file |

`verify.py check` refuses in seconds rather than after its usual run, because the
gate is before the work rather than after it.

🚨  **THE ONE GAP, AND IT IS NOT CLOSED.** A harness's OWN source is compiled by
Python before any of its code runs, so a stale import is already loaded by the
time the check executes. It is caught **in practice** because the mount served
stale bytes for a whole PROCESS rather than for a single read, so the later
re-read still sees them; it is **not caught in principle**, because a
materialisation landing between the import and the call would hide it. Every file
a harness reads after that point is fully covered. The green line is not proof
that the harness printing it is current.

### Full catalog, calc v1.14.0 (2026-08-09)

The 1,554,400-row catalog v1.1.0 (1,554,353 with positive mass), Stage 2 re-run
per destination, transportation v1.11.0, calc v1.14.0, master v1.17.0, on
`master.py` rebuilt from the modules with a clean `git status`. 12 workers.

| destination | raw | evaluable | beneficiated (v1.17.7) | evaluable |
|---|---|---|---|---|
| **`cislunar`** | **26.7863×** | 650,516 | **20.5895×** | 659,847 |
| `lunar_surface` | 63.3505× | 585,710 | 35.8051× | 606,304 |
| `leo` | 71.1055× | 776,266 | 48.2714× | 882,429 |
| `mars_surface` | 74.6748× | 730,858 | 55.3403× | 892,563 |
| `earth_surface` | 43,721.0072× | 783,742 | 25,839.48× | 912,846 |

⚠️  The beneficiated column read *not measured* until 2026-08-24 and is filled
in from the 20-cell matrix above, so it is **calc v1.17.7 on a 1,555,667-row
catalog** while the raw column is v1.14.0 on 1,554,400 rows. The two columns
are not a like-for-like pair; quote the 20-cell matrix instead.

**Cislunar is still the best case, at 20.5895×**: 2.4× clear of the next
destination on raw. Still **zero viable missions** anywhere.

Winners, raw: **2021 CX5** (D, 82 m, a = 1.626 AU) at both `cislunar` and
`lunar_surface`, **2018 DT** (M) at `leo`, **8651** (M) at `mars_surface`,
**2016 PN38** (M) at `earth_surface`. Beneficiated at cislunar it is 2021 CX5
again, concentrating 3.519× on iodine where raw flies xenon.

⚠️  **Only the cislunar raw cell is a delta.** 25.7035× → **26.7863×
(+4.21%)** against v1.13.0 on the same catalog, the expected direction, since
every item in v1.14.0 removes something the model was getting free. The other
four raw cells had **never been run on this catalog**, so they are first
measurements, not changes. And cislunar beneficiated had never been run either:
20.5895× is **not** a move from 23.9169×, which was measured on 15,566 rows
against this cell's 659,847.

⚠️  **The four non-cislunar beneficiated cells were unmeasured at this
release**: estimated at 10 to 20 hours each on six cores, and not run. ✅  They
were measured on 2026-08-24 on calc v1.17.7, where they took **2.0-2.5 h each**
rather than the 10-20 estimated, and the numbers are in
[the 28-cell matrix](README.md#current-results-the-complete-28-cell-matrix).
Until then the v1.11.0 table below was the last figure they had, three releases
and a 17× population behind, which is why it must be read for structure and
never as a number.

**8651 (M) is still the Mars raw winner**, the same body as v1.10.x and
v1.11.0. Surviving a 17× population increase *and* three releases of model
change is a stronger statement about the separate Mars heliocentric transfer
than any ratio here.

**The destination ordering has shifted**: cislunar < lunar < leo < mars, where
v1.11.0 raw ran cislunar < mars < leo < lunar. Mars went from best-of-the-rest
to worst, which is v1.14.0's containment charge landing on exactly the
volatile-rich missions the Mars result used to be carried by.

**Xenon has taken over from iodine.** Raw shares by destination:

| destination | xenon | iodine | water ion | krypton | hydrolox |
|---|---|---|---|---|---|
| `cislunar` | 42.6% | 25.2% | 15.6% | 8.0% | 8.1% |
| `lunar_surface` | 42.3% | 10.3% | 20.7% | 22.6% | 3.8% |
| `mars_surface` | 57.8% | 19.9% | - | 15.4% | 2.1% |
| `leo` | 76.0% | 13.6% | - | 4.4% | 1.9% |
| `earth_surface` | 74.7% | 13.5% | - | 5.5% | 1.9% |

That retires v1.11.0's "iodine wins nine of the ten cells". Chemical propulsion
is **not** extinct; hydrolox holds 1.9-8.1% everywhere.

**Aerocapture resolves per destination on its own**: 95.8% of `earth_surface`
rows, 93.1% of `leo`, 82.0% of `mars_surface`, and **0.00% at `cislunar` and
`lunar_surface`**, which is the airless-destination behaviour falling out of
the search rather than being asserted.

**RTG share** runs 3.96% (`lunar_surface`) to 8.46% (`earth_surface`) raw, and
10.83% at cislunar beneficiated. v1.14.0 measured 3.9% on a 6,000-row sample, 
which turns out to be almost exactly right for one destination and less than
half the true figure for another, so quote the range rather than the sample.

Verification, all passing: never-worse holds exactly on the cislunar pair
(650,516 pairs, max benef/raw 1.000000, zero exceptions, 102,703 declined); the
mass-ledger identity `hardware_total_kg == mining + power + ep` holds to
**0.000000000 kg** on every row of all six cells; serial and parallel output is
byte-identical (sha256 MATCH).

⚠️  **Everything from here down is also a smaller catalog**, not just an
older model: 89,367 bodies against this table's 1,554,400. Why that alone
invalidates them, and why the gain was the row cap rather than the H-derived
diameters, is under
[catalog v1.1.0 / calc v1.13.0](#catalog-v110--calc-v1130).

### The v1.7.0 pricing matrix

Cost/revenue ratio (lower is better; 1.0 would be breakeven), catalog v1.0.9 /
calc v1.10.0 / mineral_value v1.7.0, full catalog: 35,807 asteroids fetched,
~29,600-35,000 evaluable per destination. The v1.6.0 column is the previous
Stage 2 pricing, run in the **same process on identical code**, so the
difference is the pricing change and nothing else:

| | raw v1.6.0 → **v1.7.0** | beneficiated v1.6.0 → **v1.7.0** | best target (v1.7.0, beneficiated) |
|---|---|---|---|
| `earth_surface` | 46,049.9× → 46,071.3× | 25,110× → 25,038.5×† | 4660 Nereus, Xe, 2.5× |
| `leo` | 65.97× → 72.45× | 47.17× → 48.13× | 4015 Wilson-Harrington, B, 5.5× |
| `cislunar` | 21.71× → 31.83× | 19.02× → **22.93×** | 7753, B, 5.4× |
| `lunar_surface` | 25.54× → 75.83× | 21.42× → 40.61× | 7753, B, 4.8× |
| `mars_surface` | 16.59× → 70.41× | **11.86×** → 51.82× | 6178, P, 7.1× |

† Measured 2026-08-07 in a separate process, not in the paired run, so its
−0.3% is quote drift rather than the pricing change.

`earth_surface` is the **control**, in-space pricing does not apply there, so
its +0.05% raw movement is the run-to-run noise floor from live quotes shifting
between loops within one process. Over longer gaps it is larger: see the
reproduction below, where the control moved ~0.4% in under a day and nothing
else moved at all.

Still **zero viable missions** anywhere.

### Cislunar only, calc v1.12.0 (2026-08-08)

Stage 3 v1.10.0 + Stage 4 v1.12.0, full catalog, against the same on-disk
Stage 2 catalog the v1.11.0 cislunar cells used.

| | v1.11.0 | **v1.12.0** | Δ | winner | evaluable |
|---|---|---|---|---|---|
| `cislunar` raw | 31.7712× | **33.2342×** | **+4.60%** | 4660 Nereus, iodine | **15,407** |
| `cislunar` beneficiated | 22.4665× | **23.9169×** | **+6.46%** | 7753, B, 5.31× | **15,566** |

**Cislunar is still the best case, now at 23.9169×**, and its winner is
unchanged. Both cells got *worse*, which is the whole shape of the release:
every item in it is a term that existed on one side of the model and not the
other. See [calc v1.12.0](#calc-v1120--transportation-v1100).

⚠️  **The ratios are not the headline; the population is.** Evaluable rows
roughly halved, ~31,000 → ~15,500, because about half the catalog was closing
its mass budget only on a micronewton thruster the model was happy to sell as
a cargo tug. Those are not missions that got more expensive; they were never
physical. Any per-row comparison against a v1.11.0 catalog compares different
populations.

⚠️  **"Chemical propulsion is extinct in this model" is retired.** Hydrolox now
wins 5.5% of cislunar rows and methalox 0.1%. It was never a physical result.

> ⚠️  **The other four destinations have NOT been re-run on v1.12.0.** The
> v1.11.0 table immediately below is stale for them. Both of the changes that
> move numbers, argon's storage class and the cargo-water power plant, are
> properties of the *mission*, so they move every destination, and
> `earth_surface` is not a control for either. `mars_surface` is the cell most
> likely to have moved a lot: it was the one destination winning on argon.

### Full matrix, calc v1.11.0 (2026-08-08)

Stage 3 v1.9.0 + Stage 4 v1.11.0. Ten cells, one destination at a time, Stage 2
re-run for each; the asteroid catalog was reused, since Stage 1 is untouched by
this release and re-fetching would only add quote drift to a comparison about
the mission model.

| destination | raw v1.10.x | **raw v1.11.0** | benef v1.10.x | **benef v1.11.0** | v1.11.0 winner (benef) |
|---|---|---|---|---|---|
| `earth_surface` | 45,893.7× | 45,236.50× | 25,038.5× | 26,256.72× | 4660 Nereus, Xe, 2.47× |
| `leo` | 72.4520× | 71.0459× | 48.1286× | 51.2223× | 5620, D, 4.44× |
| `cislunar` | 31.8269× | 31.7712× | **22.9336×** | **22.4665×** | 7753, B, 4.96× |
| `lunar_surface` | 75.8315× | 75.5110× | 40.6132× | 37.8133× | 7753, B, 4.82× |
| `mars_surface` | 70.4063× | 70.4346× | 51.8161× | 51.9597× | 6178, P, 7.07× |

**Cislunar was still the best case at v1.11.0, at 22.4665×, and it improved.**
Four of the five beneficiated winners keep their v1.10.x identity *and*
concentration ratio; only `leo` moved, from 4015 Wilson-Harrington (B, 5.5×).
On v1.12.0 cislunar is **23.9169×** and still the best case; on v1.14.0 it is
**20.5895×** and still the best case.

⚠️  That sentence read "on v1.12.0 cislunar is 22.7353×" until 2026-08-09.
**That number was never measured**; it appears in no table in either file and
contradicts v1.12.0's own verification block, which records 23.9169×. Corrected
rather than carried forward.

Two mechanisms pull against each other here and the split between the raw and
beneficiated columns is the evidence for both:

- **The wider search can only help.** 21 operational propellants against 7, and
  a strictly larger option set cannot make a correctly-implemented search
  worse. Raw moves −0.18% to −1.94% at every destination, which is that effect
  on its own.
- **Tank mass can only hurt, in proportion to mass ratio**, since
  `k = 1/(1 − t(R−1))` diverges as `t(R−1) → 1`. Beneficiation means more feed,
  more power, a longer stay and more propellant, so beneficiated is where it
  bites: +6.4% at `leo`, and still net −6.9% at `lunar_surface` where the
  search gain wins.

**Iodine takes nine of the ten cells**, which is the tank term talking rather
than a coincidence: it stores as a solid at ambient pressure at 4.93 kg/L and
pays 0.2% of its own mass in tankage against xenon's 1.9%. Chemical propulsion
is effectively extinct in this model.

Note what that implies. Tankage is only ~0.7% of launch mass in the *winning*
missions, because the search routes around it. Its effect is not a cost it
adds; it is **which propellant it disqualifies**.

Mars was the exception on both counts: it moves +0.04% / +0.28% and was the
only destination that did not adopt iodine, winning on argon at both settings.

> ⚠️  **The propellant shares here are stale as of v1.12.0**: the figures used
> to read "iodine 52% of winners and argon 36%" across `earth_surface`. Argon's
> storage class changed in v1.12.0 and its tank fraction went 2.1% → 22.9%,
> because the old row was carrying liquid-argon density *and* zero boil-off at
> the same time. The mechanism above survives and is in fact sharpened by it:
> argon had been taking a quarter to a third of the winners on a tank exemption
> it should never have had. On v1.12.0 at cislunar the split is iodine 58.6% /
> PPT 29.0% / electrospray 11.0% beneficiated, and PPT 31.8% / iodine 26.8% /
> electrospray 24.3% raw; **argon falls from 27.3% to 0.0% and from 25.0% to
> 2.4%.** The Mars claim in the paragraph above should be assumed wrong until
> Mars is re-run: Mars was the destination winning on argon.

### Reproduced end to end, calc v1.10.x (2026-08-07)

All ten cells were re-measured through the UI from a catalog re-downloaded that
morning, the first check of these tables against a separate run rather than
against the process that produced them. ⚠️  **On the pre-v1.1.0 89,367-row
catalog**, so the levels here are not comparable with anything measured after
catalog v1.1.0 took the population to 1,554,400; what the table establishes is
reproducibility, not magnitude.

| destination | raw | beneficiated |
|---|---|---|
| `earth_surface` | 45,893.7× (table: 46,071.3×) | 25,038.5× (was pending) |
| `leo` | 72.4520× (72.45×) | 48.1286× (48.13×) |
| `cislunar` | 31.8269× (31.83×) | **22.9336×** (22.93×) |
| `lunar_surface` | 75.8315× (75.83×) | 40.6132× (40.61×) |
| `mars_surface` | 70.4063× (70.41×) | 51.8161× (51.82×) |

Every in-space cell came back to the hundredth, as did every winner and
concentration ratio, and the `earth_surface` beneficiated cell landed on 4660
Nereus at 2.5×, exactly the target the table had predicted for the cell it could
not fill. The catalog also rebuilt to its reference shape: 35,807 rows, 24,675
measured taxonomies against 11,131 albedo-guessed, 2,614 V-types.

The two `earth_surface` cells were the only ones to move (−0.39% raw, −0.28%
beneficiated), which is the control doing its job: it is priced off live
terrestrial quotes, while an in-space kilogram is dominated by a
launch-cost-avoided term derived from constants.

This establishes that the pipeline is deterministic given its inputs, the
architecture search, the concentration sweep and the fixed-point power solve all
had to land identically for it to hold. It does not revalidate the model.
Reproducing a number says nothing about whether the number is right.

### Mars is no longer the best case: cislunar is

This reverses `1a5e0c8`, where Mars took the lead. Mars was best *because*
Stage 2 credited it full launch-cost-avoided for water and carbon at a
destination with metres-thick mid-latitude ground ice and a 95.3% CO₂
atmosphere. Once v1.7.0 prices that local competition, Mars goes from best of
the four in-space destinations to **worst** (+337%), and cislunar wins at
22.93×, because an NRHO depot is the one destination with no local resources
at all, so it takes no ISRU discount. Its +20.6% is entirely the routed market
cap.

The Mars winner changes identity three times as the discount bites: 35678 (D)
→ 4015 Wilson-Harrington (B) → 8651 (M) → 6178 (P), which is the tell that
this is compositional, not a rescaling. Discount the volatiles and the
optimiser walks away from hydrated bodies. The Moon moves the *opposite* way,
its winner shifting toward a B-type, because lunar water only falls to 0.60
against Mars's 0.25.

**LEO barely moves under beneficiation** (+2.0%) despite +9.8% raw, with an
unchanged winner and concentration ratio: concentrating to 5.5× shifts the
payload mix off the commodity whose ceiling moved.

### Beneficiation now helps everywhere, cislunar included

⚠️ This **retires the `fa263ad` finding** that cislunar was the one destination
where the optimiser declined to concentrate the best body (39.79× either way).
It no longer reproduces; cislunar goes 21.71× → 19.02× at v1.6.0 pricing and
31.83× → 22.93× at v1.7.0, concentrating 2.5× and 5.4×.

It was retired by **calc v1.10.0, not by the pricing change**: the v1.6.0
column above already concentrates. v1.10.0 replaced the selection objective,
and "declines to concentrate" turns out to have been an artefact of optimising
`profit_usd` while reporting a ratio. So the old warning has inverted: don't
repeat "the optimiser declines to concentrate at cislunar" either. What
survives is the weaker, still-true claim that the decision belongs to the
(target × destination) pair rather than to the target.

### The release progression

⚠️ **This is a per-release series and has not been
re-measured**; rebuilding it means re-running old code, not re-running the
current model, which is why the 2026-08-07 sweep did not touch it. It is kept
because the *discipline* it records is the point: every step was a correction,
and the last two moved the number down. Read it as a shape, not as current
figures; this column tracks Mars, which is no longer the best case, and the
best case now anchors at 22.93× at cislunar.

| Release | Mars | What it started charging for |
|---|---|---|
| v1.6.0 | 2.2× | - |
| v1.7.0 | 14× | low-thrust trip time, launch windows, bound-water energy, learning curve, market saturation |
| v1.8.0 | 39× | rig service life, mission reliability, cryogenic boil-off, in-space manufacturing |
| v1.9.1 | 34× | reliability growth, and `p_mining` recalibrated 0.75 → 0.85 on the full flight record |
| catalog v1.0.9 | **25×** | nothing new; restored SsODNet, which had been downloaded and then discarded on every run, taking measured taxonomy from ~1,850 to ~24,675 bodies |
| v1.10.0 | **11.86×** | the electric propulsion stage and the return vehicle's structure, both flown as mass, neither billed, plus a per-asteroid architecture search and a fixed selection objective |

The whole column is at **v1.6.0 pricing**, which is what makes it a series about
the calc model rather than about Stage 2. Do not read the last row against the
51.82× in the tables above: that is the same code at v1.7.0 pricing, and the
difference between the two is the local-resource discount, not a release.

## What the v1.17.x line was worth

Six releases landed between calc v1.16.0 and v1.17.7, v1.17.1, v1.17.2,
v1.17.4, v1.17.5, v1.17.6, plus v1.17.3's cleanup; none of which changed an
output value, and **no full-catalog run had been made on any of them.** They
had only ever been measured on the 150-400-row cells each release argues itself
from, which is exactly what [the sampling rule](#the-sampling-rule) says
not to extrapolate from.
Measured at `cislunar` on the full **1,555,667-row** catalog, 12 workers, both
builds against the same catalog and the same Stage 2 pass, 2026-08-24.

🚨  **The `v1.17.7` column is the ONE PLACE these four numbers live.** They are
`MEASURED_CELL_SECONDS` in `modules/calc.py`, and every printed cost ratio in
the project derives from it: `run_pipeline.py`'s `--help` and run banner,
`build_master.py`'s `MASTER CONFIG READY` banner (so `master.py` too), calc's
own Stage 4 preview, and `ui.py`'s runtime estimate. They were five hand-copied
literals until 2026-08-25 and had gone stale together. **Re-measure here, edit
the dict, and every banner moves with it**; `verify_docs.py` check 9 holds
[README's wall-clock table](README.md#beneficiation) to the same values.

| cell | v1.16.0 | **v1.17.7** | speed-up |
|---|---|---|---|
| raw, search OFF | 1,307 s | **733 s** | 1.78× |
| raw, search ON | 3,890 s | **1,253 s** | 3.11× |
| benef, search OFF | 9,300 s | **3,424 s** | 2.72× |
| **benef, search ON** (the default) | **24,587 s** | **5,692 s** | **4.32×** |
| whole 2×2 | 39,084 s | **11,101 s** | **3.52×** |

The gain is largest exactly where the default configuration sits, which is what
v1.17.1, v1.17.2 and v1.17.5 aimed at (the programme ladder) on top of v1.17.4
and v1.17.6 (the mass cascade and the per-row walk).

🚨 **Five committed cost ratios move as a consequence**, and they are ratios
between two settings rather than wall clocks:

| ratio | committed (v1.16.0) | **measured (v1.17.7)** |
|---|---|---|
| programme search, raw | 2.98× | **1.71×** |
| programme search, beneficiated | 2.64× | **1.66×** |
| beneficiation, search OFF | 7.1× | **4.67×** |
| beneficiation, search ON | 6.3× | **4.54×** |
| 2×2 corner to corner | 18.8× | **7.77×** |

✅ **It also scored the arithmetic this project forbids.** Compounding the five
performance releases' stride-sample ratios gives 1.82 / 2.67 / 3.02 / 3.45×
against the measured 1.78 / 2.72 / 3.11 / **4.32×**: **three cells inside 3%,
and the default cell 20% low.** So the prohibition was right about the
*direction* (compounding understates), and the magnitude is a fifth rather than
the factor of ~5 [the sampling rule](#the-sampling-rule) is written around.

⚠️  **Do not read that as permission to compound.** It is one test, on one
release line, of five ratios that all pointed the same way, and it missed
worst on the **only cell anybody actually runs**, which is also the one you
were trying to budget.

✅ **Memory was measured too, and it is the third quantity under the sampling
rule.** v1.17.7 bounded a cache against a *projected* 11-18 GB that nobody
could exercise. Sampled every 20 s across the campaign the bound holds, and
peak RSS tracks **output size** rather than ladder traffic: 8.2 GB at
`lunar_surface` beneficiated, 8.4-9.0 GB across the four cislunar cells, and
**10.4 GB** at `leo` beneficiated N = 1, the cell with the most evaluable rows.
Peak system use 30.4 GB of 68.6 GB.

⚠️  **Two apparent peaks of 11.54 and 10.74 GB are measurement contamination,
not the pipeline**; they are exactly the two cells that overlapped an analysis
process loading four 650 k-row frames. Recorded rather than quietly dropped,
because attributing your own harness to the thing you are measuring is how a
clean result becomes a false alarm.

### The full cislunar 2x2, calc v1.16.0 (2026-08-11)

The first time both settings of beneficiation **and** both settings of the
programme search were measured on a full catalog at one destination, at
`cislunar`, on a 1,555,667-row catalog (1,555,618 with positive mass), 12
workers, one Stage 1/2/3 pass.

These superseded the cislunar row of the **v1.14.0 destination matrix above**,
which they also reproduce. ✅  **All four MODEL values then reproduced exactly
again on calc v1.17.7** and now live in
[the 28-cell matrix](README.md#current-results-the-complete-28-cell-matrix);
only the runtimes here are superseded.

| | search OFF (N = 1) | search ON |
|---|---|---|
| **raw** | **26.7863×** | **15.4273×** |
| **beneficiated** | **20.5895×** | **13.1443×** |

Evaluable 650,921 raw / 660,253 beneficiated. ⚠️  Its **runtimes are
superseded**: on calc v1.17.7 the same four cells take 733 / 1,253 / 3,424 /
5,692 s, so beneficiation is **4.67×** and the programme search **1.71×**, and
the 2×2 spans **7.77×** corner to corner rather than 18.8×. All four MODEL
values reproduce exactly.

**13.1443× is the best cislunar figure this model has produced**, and it is what
calc v1.17.0's two flipped defaults return **at cislunar**. It is still a factor
of 13 from breakeven, so the project's headline is unchanged: **a default run
produces zero viable missions, and that is the correct answer.**

⚠️  It is **not** "the default run", `delivery_destination` still defaults to
`earth_surface`, so a configure-nothing v1.17.0 run is beneficiated + searched
at `earth_surface`. Only the two flags moved. That cell **is** measured now, at
**7,869.88×**, and it is the one cell that must not be read as an optimum,
because saturation is inert there and every row runs to the fleet ceiling.

⚠️  The two columns are **not comparable**; one is the best single mission to a
rock, the other the best programme built around it (here: 10 missions, 2 ships,
17 years). The improvement is a change of question, not a saving.

The same body, **2021 CX5** (D-type, 82 m, a = 1.626 AU), wins all four cells on
a New Glenn, while its propellant goes xenon → iodine → iodine → **argon** and
its payload falls **93,312 → 34,573 kg**, which is market saturation preferring
more, smaller missions at programme scale.

**Both search-OFF cells reproduce their committed v1.14.0 values exactly**, four
releases later and on a catalog that has grown by 1,267 bodies: same winner
(2021 CX5, D-type), same vehicle, same propellant, same payload in kilograms,
same concentration ratio, same propellant shares. That is a stronger check than
the byte-identity diffs v1.14.1/v1.14.2/v1.15.0 argued from, because those
compared identical rows and this compares a different population.

As of **calc v1.17.0 the bottom-right cell is what the default FLAGS produce**
(at this destination: the default destination is still `earth_surface`); the
top-left is what almost every other table on record is. Set
`use_beneficiation = False` and `optimise_programme_scale = False` to reproduce
them.

## The sampling rule

Five of the misses recorded in this file are the same mistake, so it gets
stated once. `CLAUDE.md` carries the canonical version; this is what the
history below is evidence for.

> **A stride sample predicts a full-catalog measurement here to no better than
> a factor of ~5.** It is *not* "samples overestimate"; the misses run both
> ways. Budget from a measured full run of the same cell, or do not budget.

It covers three quantities, and it grew to cover each of them the hard way:

| quantity | added by | the miss |
|---|---|---|
| **wall clock** | catalog v1.1.0 | a 20,000-row sample predicted 2.2 h for a run that took 42 min: **3.1× high** |
| | calc v1.14.0 | ~2.2 h predicted for a cell that took 10.6 h: **4.8× low** |
| **a ratio between two settings** | calc v1.15.0 | the programme search costed at 1.04-1.13×, measured **1.51×** |
| | calc v1.16.0 | costed at 1.10×, measured **2.98×** |
| **memory** | calc v1.17.7 | a cache showing 18,000 entries at 400 rows projects to **~70 million** on a full one |

⚠️  **The two mechanisms pull in opposite directions**, which is why the misses
have no reliable sign: fixed costs (worker startup, the catalog load) dominate a
small run and make it look slow per row, while a stride sample
*under*-represents the expensive tail of the concentration sweep and makes a
beneficiated cell look cheap.

✅  **One kind of projection HAS held, and it is different in kind.**
Extrapolating a *measured full-catalog speed-up on one cell* to another setting
of that same cell put calc v1.15.0's beneficiated cell inside its projected
3.4-4.6× band, and v1.16.0's calendar charge landed at +8.85% against a sample's
+8.78%. What has failed five times is extrapolating **from a stride sample to
the full catalog**. On this pipeline a sample predicts a *model ratio* far
better than it predicts a *resource*.

## Runtime history

Current wall clocks are in [Beneficiation](README.md#beneficiation); what
follows is what they used to be. **The reasons they moved are the point of this
section**: a wall-clock number in this repo tells you nothing on its own, and
they have now moved for twelve unrelated reasons, only some of which were the
code getting faster.

### Wall clock, full catalog, calc v1.14.0 (2026-08-09)

Six physical cores / 12 workers, the 1,554,400-row catalog:

| destination | raw | beneficiated |
|---|---|---|
| `cislunar` | **5,350 s** (89 min) | **38,072 s** (10.6 h) |
| `lunar_surface` | 5,118 s | *not run* |
| `leo` | 10,063 s | *not run* |
| `mars_surface` | 10,275 s | *not run* |
| `earth_surface` | 10,670 s | *not run* |

The raw row alone was 11.5 h and the ten-cell sweep was projected at **~3.5
days**. ✅  On calc v1.17.7 the full **twenty**-cell matrix, twice that work, 
took **26.1 hours**, and the ten cells this projection describes are 13.5 h of
it. The projection was not wrong when written; six performance-only releases
landed in between. **A runtime sentence in this repo is only ever true of the
release it names.**

🚨 **The beneficiated estimate here was wrong by 4.8×, and it ran the OPPOSITE
way to the previous miss.** The figure on record before this run was "~2.2 h
beneficiated, estimated from a sample's 3.12× raw:beneficiated ratio". It is
**10.6 h**, because the real full-catalog ratio was **7.1×**, not 3.12×, and on
the 6,000-row v1.14.0 sample it looked like **1.63×**, off by a factor of four
in the same direction. Read that against catalog v1.1.0, which recorded a sample
**over**estimating a run by 3.1×. Samples have now mispredicted full-catalog
runtime on this pipeline badly in *both* directions, for opposite reasons: fixed
costs dominate a small run, and the expensive tail of the concentration sweep is
under-represented in a stride sample.

### Wall clock, old catalog, calc v1.11.0 (2026-08-08)

Six physical cores, the 89,367-row catalog. Kept only because the **ratios
between destinations** are still roughly how to reason about relative cost; the
absolute seconds are two orders of magnitude out of date.

| | raw | beneficiated | ratio |
|---|---|---|---|
| `cislunar` | 89 s | 462 s | 5.2× |
| `lunar_surface` | 84 s | 437 s | 5.2× |
| `mars_surface` | 158 s | 966 s | 6.1× |
| `leo` | 177 s | 948 s | 5.4× |
| `earth_surface` | 174 s | 1,017 s | 5.8× |

The whole ten-cell sweep was about **70 minutes** including a Stage 2 re-run per
destination. On calc v1.12.0 cislunar measured **88 s raw / 502 s
beneficiated**; raw unchanged, beneficiated up ~9%, which is `_cargo_water_kg`
calling the payload knapsack inside the fixed-point loop instead of once after
it. That was measured before it was accepted (250-body sample: 19.8 s → 21.4 s,
+8%).

### Why they moved, in order

Conflating these is how a stale timing gets quoted as evidence. Each step is a
different *kind* of change and only some of them touched an output:

- **calc v1.10.0 and earlier**: ~140 s raw / ~2,120 s beneficiated, single
  core. The 2026-08-07 ten-cell reproduction took about three and a half hours.
- **calc v1.10.1**: ~33 s / ~137 s. A **pure performance release**; every
  number bit-identical.
- **calc v1.11.0**: the table above, roughly 5× slower than v1.10.1 again, and
  **not** a performance regression: the search is **4.6× wider** (357 vehicle ×
  propellant combinations per asteroid against 77) because the propellant table
  went from 7 usable rows to 21.
- **catalog v1.1.0**: the catalog went **17× bigger**, 89,367 rows to
  1,554,400. Everything above is per *catalog*.
- **calc v1.14.0**: roughly doubles, on the power-source search axis.
- **calc v1.14.1 through v1.17.7**: six performance-only releases worth a
  measured 1.78-4.32× on the full catalog. See
  [what the v1.17.x line was worth](#what-the-v117x-line-was-worth).

⚠️  **The beneficiated figure in particular has moved three times for three
different reasons, and only two touched a result.** It read **1,100 s** at a
ratio of 8× before anyone measured it again; two independent runs on 2026-08-07
gave **2,122 s and 2,124 s**, so that step was the model getting genuinely more
expensive rather than the measurement being noisy; v1.10.0 had made the
architecture search per-asteroid, and the two searches *multiply*, because every
concentration ratio is now priced against every vehicle × propellant × return
mode × ISRU choice × apsis rather than against one nominal architecture. Then
v1.10.1 took it to 137 s by using the other eleven threads and by not looking
every catalog row up through a pandas index a few thousand times per asteroid.
So: up because the model got more expensive, down because the code got faster,
and up again because the option set got bigger. **Always read which release a
wall clock was measured on.**

### The old beneficiation decline figures

Superseded by the full-catalog per-destination figures in
[Beneficiation](README.md#beneficiation), and kept because they are the
measurement the never-worse invariant was first checked against.

Measured 2026-08-07 on the old catalog at cislunar: beneficiation **declines on
1.365%** of targets, with a **median concentration ratio of 7.41×** and a
**maximum of 22.2×** against a cap of 50, so the optimum is strictly interior
and nowhere near the cap. The never-worse check joined the raw and beneficiated
catalogs on `designation` across all five destinations, **165,843 pairs**, with
the beneficiated cost/revenue never higher and a worst case of exactly 1.0000.

⚠️  The decline rate is the figure that moved most: 1.365% on the old catalog
against **15.8% at cislunar** on the full one. It is a property of the
population, not of the model.

## The programme-scale curves

Three separate attempts to answer "does flying more missions help?", each
superseded by the next. The current answer is that the question is resolved
**per body inside one run**: `optimise_programme_scale` searches fleet size
and campaigns-per-ship jointly with every other architecture axis, so a curve
against a *forced* programme size is no longer how the model is read. See
[Programme scale](README.md#programme-scale).

### Calc v1.10.0, cislunar, beneficiated (2026-08-07)

| Programme | `p_mining` | `P(success)` | Missions sharing one rig | Best cost/revenue | Winning vehicle |
|---|---|---|---|---|---|
| 1 mission | 0.850 | 0.646 | 1 | 22.93× | Falcon Heavy |
| 10 missions | 0.902 | 0.708 | 4 (capped) | 9.85× | New Glenn |
| 100 missions | 0.943 | 0.739 | 4 (capped) | **7.28×** | New Glenn |

⚠️  **The winning vehicle switches from Falcon Heavy to New Glenn at N ≥ 10,
and the reason on record for that was wrong.** The README used to explain it as
"once NRE is spread across a programme, the per-mission launch bill stops
dominating and **a bigger vehicle starts paying**", but New Glenn lifts
**45 t** to LEO against Falcon Heavy's **57 t**, so the switch is to a *smaller*
vehicle, and the sentence was contradicted by a table a hundred lines below it
in the same file. The correct reading is the one v1.14.0's curve makes
explicitly: **market saturation punishes volume, so at programme scale the model
prefers more, smaller missions.** The same effect, visible two releases before
anything could express it.

🚨 **The SHAPE of this table is wrong, not just its levels.** It was measured on
a model in which market saturation could not see `nre_amortization_missions` at
all, so a 100-mission programme divided its NRE by 100, grew its reliability,
and sold 100 payloads at the price **one** payload commands. Every lever pointed
the same way and nothing pushed back, which is precisely what that term was
written to prevent. Fixed in v1.14.0.

⚠️  Its levels are ~10% optimistic too: the N = 1 anchor of 22.93× measured
22.4665× on v1.11.0 and **20.5895×** on v1.14.0. `p_mining` and the rig cap are
the two columns that do carry over; the first is a function of N alone, the
second a property of the mission profile.

### Calc v1.14.0, cislunar, 6,000-row sample (2026-08-08)

The sample that first showed the curve **turning**, measured with market
saturation blind to programme size and then able to see it, on the same rows in
the same process:

| N | v1.13.0 | **v1.14.0** | concurrent missions | saturation multiplier |
|---|---|---|---|---|
| 1 | 38.4050× | 38.7886× | 1 | 0.7451 |
| 10 | 16.0296× | **16.4745×** | 1 | 0.7773 |
| 100 | **10.8935×** | **20.3246×** | 10 | **0.4279** |

The saturation multiplier column is the mechanism in one number: it *improves*
from N = 1 to N = 10, because one rig serves all ten missions back to back and
the market never sees two payloads at once, then collapses at N = 100, where
the rig cap forces ten concurrent rigs. **"Fly more missions" is not an
unbounded lever and never should have looked like one.** ⚠️  A sample, on the
old catalog; the full-catalog version is below.

### Calc v1.14.0, cislunar, raw, full catalog (2026-08-10)

All 1,554,400 rows. N = 1 is the measured headline cell; N = 10 and N = 100 are
separate full runs against the same catalog and Stage 2 pass.

| N | best cost/revenue | `p_mining` | saturation multiplier | concurrent missions | rig serves | winner | vehicle / propellant | payload |
|---|---|---|---|---|---|---|---|---|
| 1 | 26.7863× | 0.850 | 0.6873 | 1 | 1 | 2021 CX5 (D) | New Glenn / xenon | 93,312 kg |
| 10 | **13.5836×** | 0.902 | 0.7785 | 1 | 10 | 2002 AT4 (D) | New Glenn / krypton | 42,597 kg |
| 100 | 18.3605× | 0.943 | 0.5423 | **9** | 12 | 2021 CX5 (D) | H3 (24L) / iodine | 19,495 kg |

**The curve turns, and the optimum is interior**, −49.3% at N = 10, then back
up to −31.5% at N = 100. Scale still helps overall; it just stops helping
monotonically. Why, reading the columns:

- **At N = 10 nothing is concurrent.** One rig serves all ten missions back to
  back, so the market never sees two payloads at once and the saturation
  multiplier actually *improves* (0.6873 → 0.7785). NRE per mission falls 10×,
  `p_mining` grows. Every lever points the same way, which is why the
  pre-v1.14.0 model looked plausible here.
- **At N = 100 the rig cap binds.** One rig serves 12 missions at this stay
  length, so a hundred-mission programme needs ⌈100/12⌉ = **9 rigs flying at
  once** and the multiplier collapses to 0.5423. That is the turn.

**The winning vehicle gets *smaller* with scale**: New Glenn → New Glenn →
H3 (24L), payload falling 93,312 → 42,597 → 19,495 kg. Saturation punishes
volume, so at programme scale the model prefers more, smaller missions. The old
model could not express that at all. The whole population moves the same way:
New Glenn's share goes 1.68% → 3.58% → **13.91%** while SLS falls 31.59% →
25.06%, and the capacity-weighted mean vehicle falls monotonically 71.8 → 66.6 t.

**Propellant follows, and iodine takes over at scale**: xenon 42.65% → 39.90% →
**15.46%** against iodine 25.19% → 26.10% → **49.64%**. ⚠️  That is the *reverse*
of what v1.14.0's eclipse term did, which is what took xenon from iodine in the
first place, so the xenon/iodine ranking is not a property of the model, it is
a property of the model **at N = 1**. The searched full-catalog population later
confirmed it: iodine overtakes xenon at `leo` and wins `earth_surface` outright.

⚠️  **Two things not to read as constants.** The rig cap is 12 here, not the 4 of
the older curve; it is `life / stay`, and this winner flies 4.2-4.4 yr. And
**three points means "near N = 10" is the lowest of the points sampled, not a
located optimum.**

🚨 **The rig cap was retired outright by v1.15.0**, and the reason is that 12 was
never a life at all: `life / stay` divides a **calendar** figure: 15 years, of
corrosion, thermal cycling and radiation dose, by the stay, and nothing
anywhere bounded **duty cycles**. Stage 3 v1.12.0 adds a maximum-trips figure
and the min of the two is taken.

⚠️  **This is the RAW curve**, and the beneficiated one above is not superseded
by it; it is simply unmeasured at pinned N = 10 / 100. That gap is still open:
the 2026-08-24 campaign measured the beneficiated *searched* cell at all five
destinations, which locates the optimum per body, but did not produce a curve
against a forced programme size. It is two runs and they are now cheap.

# Repository history

Earlier version-suffixed copies of every module (`Master(1.4.0).py`,
`CalcPipeline(1.3.0).py`, the original Colab notebook, and the rest) were
removed once the code moved into git, version history lives in commits now.
They remain retrievable from the import commit `84ae606`:

```bash
git show --name-only 84ae606                              # what was imported
git show '84ae606:CalcPipeline(1.3.0).py' > restored.py   # restore one
```

`Profitability Pipeline(1.0.2).ipynb` is worth knowing about specifically: it
is the original Colab notebook, and it is not a duplicate of any `.py` here.
It is the only surviving copy of Module 1 v1.0.3, Module 2 v1.1.0, Module 3
v1.2.0 and Module 4 v1.3.2, which were overwritten in place before any of
this was under version control.

```bash
git show '84ae606:Profitability Pipeline(1.0.2).ipynb' > notebook.ipynb
```

## The parallel-repo divergence

This project was briefly developed in two places at once, and both copies
shipped different code under the *same* `pipeline_version`: `1.0.6`, `1.1.4`
and `1.3.6` each meant two different things depending on which copy you read.
That is precisely the failure `pipeline_version` exists to prevent, since it
is stamped into every output CSV.

The two were reconciled in `5ecafa1`, and the merged modules were renumbered
(catalog `1.0.7`, mineral_value `1.1.5`, calc `1.3.7`, master `1.4.4`) because
they match neither parent. Any CSV produced before that merge carries an
ambiguous version stamp; treat `1.0.6` / `1.1.4` / `1.3.6` output as
undated and re-run rather than trusting the number.

