# Notes for working in this repo

Context for anyone (human or agent) editing this pipeline. The split between
these files is deliberate, and the table is the list; **do not restate its
length in prose**, which is the failure this file catalogues three times over
and which caught this very paragraph on 2026-09-03:

| file | holds | is the authority for |
|---|---|---|
| [`README.md`](README.md) | what the pipeline is, how to run it, what the model does, and the **current** numbers | the current answer |
| [`versions.md`](versions.md) | what changed in which release, what every number used to be, and the per-module changelogs | the measurement history |
| [`CITATIONS.md`](CITATIONS.md) | where every source, dataset and borrowed line came from, and what each obliges | references and attribution |
| **this file** | what will bite you: the traps, the invariants, and the reasoning behind decisions that look wrong | how to edit it safely |
| the [`spacecost`](https://github.com/loggger101/spacecost) repo | Stage 3's reference tables, their citations, and their release history | every launch, propellant, delta-v, operational and storage row |

⚠️  **`CITATIONS.md` holds references, never values.** A number's source is
cited on the row that carries it, in `modules/*.py`; that row stays the
authority for the number. Two of the sources ask to be cited as a condition of
use, so it is not decorative.

**It is meant to be grepped rather than read.** Six parts, in this order:

| part | what it is | read it when |
|---|---|---|
| **Build and versioning** | how `master.py` is assembled, and the `pipeline_version` rule | before any edit |
| **What the model currently says** | the 28-cell campaign, per destination, and the claims each cell retired | before re-measuring anything, or "fixing" a result that looks wrong |
| **Keeping these files honest** | the one rule about stale prose, placed between the results and the assumptions because it is about both | after changing any number |
| **Load-bearing assumptions** | the things that silently corrupt the output if undone | before changing a model term |
| **Durable lessons** | the recurring defect classes, the traps, and the register of things already measured and declined | before "fixing" anything, and before optimising anything |
| **Working practice** | the verification harness, the invariants, data-source behaviour, Google Drive, the environment | when something is behaving strangely and it is not the model |

🚨  **This file used to carry a second copy of the release history, about five
thousand lines of it, beneath its own rule that two copies of one measurement
is a bug and that you must name one authority or you have two.** That copy is
gone and `versions.md` is the authority. What stayed here is the part that was
editing guidance rather than record: the defect classes, the traps, and the
things already measured and declined. **Add a release note to `versions.md`,
and add what it teaches to this file.**

## Contents

Six parts, and this file is meant to be grepped rather than read straight
through. Skim for the section that names what you are about to change.

- [master.py is generated: never edit it](#masterpy-is-generated-never-edit-it)
- [The build makes surgical assumptions about module structure](#the-build-makes-surgical-assumptions-about-module-structure)
- [Name collisions are handled by hand](#name-collisions-are-handled-by-hand)
- [Bump `pipeline_version` when output changes](#bump-pipeline_version-when-output-changes)
- [What the model currently says, and what that retired](#what-the-model-currently-says-and-what-that-retired)
- [When a number changes, grep the prose too](#when-a-number-changes-grep-the-prose-too)
- [Model assumptions that are load-bearing](#model-assumptions-that-are-load-bearing)
- [The older matrices, and the claims they retired](#the-older-matrices-and-the-claims-they-retired)
- [The corrections the model accumulated](#the-corrections-the-model-accumulated)
- [Durable lessons from the release history](#durable-lessons-from-the-release-history)
- [The verification harness is committed now](#the-verification-harness-is-committed-now)
- [Stage 3 lives in another repository now](#stage-3-lives-in-another-repository-now)
- [Config discipline](#config-discipline)
- [Correctness invariants that were expensive to find](#correctness-invariants-that-were-expensive-to-find)
- [Data sources fail softly by design](#data-sources-fail-softly-by-design)
- [Google Drive makes the tree look dirty: run the hooks](#google-drive-makes-the-tree-look-dirty-run-the-hooks)
- [Environment](#environment)

## master.py is generated: never edit it

`master.py` is assembled from `modules/*.py` by `build_master.py`, and it is
the largest file in the repo by an order of magnitude. Edit the module, run
`py build_master.py`, commit both. A change made directly in `master.py` is
destroyed by the next build.

⚠️  **A line count is not stated here on purpose.** This paragraph read
"~9,600 lines" while the file was 19,707, having gone stale by a factor of two
and out again as the modules grew and then lost their release notes. It is a
count spelled out in prose, which is the failure this file names three times
over; the build itself prints the real number on every run.

`git status` immediately after a build is the sync check: clean means
`master.py` matches the modules.

## The build makes surgical assumptions about module structure

`build_master.py` locates things by pattern, not by parsing. Every module must
keep:

- a leading `# -*- coding: utf-8 -*-` line followed immediately by the module
  docstring (the docstring strip anchors on it),
- an `# INSTALLATION` block ending with the literal `print("OK  All packages present")`,
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
are different functions over different frames, and module 4's silently won, 
while module 1's help text still told you to call it. Fixed in `91f2763`.

The post-build AST scan catches new collisions. Do not ignore its warning;
either add a rename or, if the duplication really is deliberate and identical
in every copy, add the name to `_EXPECTED_DUPES`.

🚨  **`word_replace` REWRITES COMMENTS AND STRING LITERALS TOO, NOT ONLY CODE**,
and since Stage 3 became an adapter over an external package that is no longer
a curiosity. It is `re.sub(r"\b" + name + r"\b", ...)` over the whole file
text, so every one of these is rewritten:

| what | how it broke |
|---|---|
| `from spacecost import validate as _v` | the **imported** name is still a bare word, so master.py asked the package for `validate_transport` and got `ImportError` |
| `"TRANSPORT CONFIG DRIFT: ..."` | a message that reads `TRANSPORT TRANSPORT_CONFIG DRIFT` in master.py |
| a comment explaining this very trap | both spellings came out identical, so the warning became nonsense |

⚠️  **Aliasing the local name is NOT enough**, which is the part that looks
like it should work. `from X import validate as _v` still spells `validate`.
The fix is on the other side: `spacecost` exports `validate_tables` as a
collision-proof second name, and the adapter imports that.

✅  **The general rule: never spell a rewritten word anywhere in a module that
reaches OUTSIDE itself.** For this module the rewritten words are the config
global and `validate`. Reach the package through `spacecost.` and **read the
built `master.py`** rather than the module, because they are not the same text
and only one of them runs.

⚠️  Note what caught this: `verify_docs.py` checks 8 and 9, which import master
and would have skipped silently in an older revision. Nothing in `verify.py`
looks at Stage 3, and the pipeline itself would only have failed at run time.

## Bump `pipeline_version` when output changes

Each module carries a `pipeline_version` in its config dataclass, and it is
stamped into every output CSV. That stamp is the only way to tell which code
produced a given catalog, so changing any number a run produces means bumping
it.

🚨  **THE CHANGELOG IS `versions.md`, AND AS OF 2026-09-02 IT IS THE ONLY
COPY.** It used to be a comment block above each `pipeline_version` field as
well, 2,063 lines of it across the four modules, recording the numerical
impact of each change, often hand-verified. That was a second copy of a
measurement record standing beneath this file's own rule that two copies is a
bug, and because `ui_meta` scrapes a field's comment block as its help text it
was also what the dashboard rendered when you opened the version stamp. It is
now [Module changelogs](versions.md#module-changelogs), one section per module,
in numeric order, which the comment blocks were not. **A release writes in two
places, and neither of them is the module:**

| where | what goes there |
|---|---|
| [`versions.md` > Releases](versions.md#releases) | what the release did, and the measurement that says so |
| [`versions.md` > Module changelogs](versions.md#module-changelogs) | the stamp, its pairing, and the config fields and output columns it adds |

⚠️  **The schema half is the part with no other home.** Which release added
`tank_cost_usd` and which added `cadence_window_bound` is what tells you
whether an archived CSV can answer the question you are asking of it, and no
release note above records it.

This has already failed once: the project was briefly developed in two places
at once, and `1.0.6` / `1.1.4` / `1.3.6` each shipped as two different things.
See "The parallel-repo divergence" in `versions.md`; CSVs stamped with those
versions cannot be trusted and should be regenerated.

Current: catalog `1.2.0`, mineral_value `1.9.0`, transportation `1.14.0`,
calc `1.22.0`, master `1.27.0` (the master version is a literal in
`build_master.py`'s `MASTER_HEADER` and `MASTER_ORCHESTRATOR`, two places).

ℹ️  **transportation `1.14.0` is now spacecost's data-contract version**, not a
number this repo owns. The tables moved out; the stamp did not move with them,
because the stamp identifies the data and the data is unchanged.

ℹ️  **TWENTY stamps so far do NOT mean the numbers moved.** The rule
is one-directional: *changing a number means bumping; bumping does not mean a
number changed*, and reading a version as evidence that a result moved is the
mistake this table exists to prevent.

⚠️  Most rows are **calc** stamps. The exceptions are `mineral_value 1.7.1`,
`mineral_value 1.8.0`, `mineral_value 1.9.0`, `transportation 1.13.0` and
`transportation 1.14.0`, so read the module and not just the number: `1.7.1`
and `1.17.1` are different modules and unrelated releases, and so are `1.14.0`
and `1.19.0`, which shipped together.

| stamp | why it moved | what a re-run gives |
|---|---|---|
| `1.10.1` | performance only | bit-identical, verified |
| `1.14.1` | performance only | bit-identical, verified |
| `1.14.2` | performance only | bit-identical, verified |
| `1.17.0` | **two defaults flipped** | bit-identical *only if configured explicitly* |
| `1.17.1` | performance only | bit-identical, verified |
| `1.17.2` | performance only | bit-identical, verified |
| `1.17.3` | **dead code removed** | bit-identical, verified |
| `1.17.4` | performance only | bit-identical, verified |
| `1.17.5` | performance only | bit-identical, verified |
| `1.17.6` | performance only | bit-identical, verified |
| `1.17.7` | **memory bound** | bit-identical, verified |
| mineral_value `1.7.1` | **silent default closed** | bit-identical, verified |
| `1.17.8` | **a new upstream check** | bit-identical, verified |
| `1.18.0` | **a sixth destination** | bit-identical, verified |
| mineral_value `1.8.0` | **a sixth destination** | bit-identical, verified |
| transportation `1.13.0` | **three reference rows** | bit-identical, verified |
| `1.19.0` | **a seventh destination** | bit-identical, verified |
| mineral_value `1.9.0` | **a seventh destination** | bit-identical, verified |
| transportation `1.14.0` | **four reference rows** | bit-identical, verified |
| `1.19.1` | **a check that cried wolf** | bit-identical, verified |

**Every measured cell in this file stands unaltered across all twenty; do not
re-measure anything on account of any of them.** Each release's own section
carries its verification.

⚠️  **Derive the taxonomy from the table above, not from a count in prose.**
Eight rows are *performance* stamps; the other twelve are `1.17.0` (a default
flip), `1.17.3` (a cleanup), `1.17.7` (a memory bound), `1.17.8` (a new
upstream check), `1.19.1` (that same check, fixed), `1.7.1` (a silent default
closed in another module), and two
trios that each add a delivery destination without touching any existing one:
`1.18.0` / `1.8.0` / `1.13.0` for `mars_orbit` and `1.19.0` / `1.9.0` /
`1.14.0` for `geo`. See
[calc v1.17.0](versions.md#calc-v1170) for the one of those that changes what a
configure-nothing run answers.

🚨  **THIS PARAGRAPH IS WHERE THE COUNT KEPT ROTTING, AND IT IS THE ONE PLACE
IN THIS FILE WHERE A SPELLED COUNT IS NOW CORRECT TO KEEP.** It was written at
`1.17.5` and still read "nine" and "seven" after `1.17.6` shipped; it then read
"eight and four" while `1.17.8` sat outside the table entirely, having said
"No number" in its own release section since 2026-08-27; and it read
"THIRTEEN" and "the only non-calc entry" until the `mars_orbit` trio landed
three stamps at once, two of them non-calc.

This file's general rule is `Name the list; do not state its length`, and
deleting the count here was tried on 2026-09-02 and **reverted the same hour**,
because `verify_docs.py` check 2 now counts both copies of this table, holds
them to each other, and holds every sentence beside them to the rows. The count
is spelled out *because* it is enforced. **That is the general lesson, not an
exception to it: a count nothing checks is a number waiting to rot, and the fix
is a checker or a deletion, never a correction.** Three corrections did not
stop this one. **Count the table.**

🚨  **`1.17.7` IS THE FIRST STAMP HERE THAT FIXES A DEFECT RATHER THAN A COST,
and it is a defect no cell in this file could have shown.** `_CALENDAR_CACHE`
(the name is historical; it is `_calendar_multipliers_cached` now) was the one
memo in the module keyed on a **per-candidate float**, so it grew
linearly with the catalog: ~45 entries per row, **~70 M entries and 11-18 GB**
projected on a full-catalog default cell against a documented run peak of
~6 GB. It landed in `1.17.4` and **no full-catalog run has been made since
`1.16.0`**, so nothing had ever exercised it at the scale that shows it. Now
bounded, which cannot change an output value by construction and is also
*faster* (180 → 91 ns a hit). See [calc v1.17.7](versions.md#calc-v1177--transportation-v1121).

✅  **The checks every release above argues from are now a committed file,
`verify.py`, instead of a harness rebuilt from memory each time.** CLAUDE.md
had recorded **eleven** harness bugs across six releases, three of which produced
conclusions that were written down before being caught. `verify.py` reproduces
the four cell hashes committed for `1.17.4` and `1.17.6` exactly, which is what
makes it a replacement for those harnesses rather than a twelfth one. See "The
verification harness is committed now".

⚠️  **`1.17.2` is the first performance release in this project that is INERT
on some cells and worth 1.45× on others**, and the split is not subtle: it
removes work that only exists when a programme LADDER exists, so both
search-OFF cells measure 0.99-1.02× and both search-ON cells 1.35-1.46×. Every
previous perf stamp moved every cell. Do not quote a single number for it.

⚠️  **`1.17.4` is uneven the OTHER way round, and quoting either release's
number for the other gets it backwards.** `1.17.2` helps only where a ladder
exists; `1.17.4` lands on the MASS cascade, so it is worth **2.04×**
beneficiated-without-search and only **1.26×** raw-with-search; the searched
cells dilute it because the cost ladder is a bigger share of what remains.
Measured 1.52 / 1.97 / 1.33 / **1.57×** across the four cells. It also takes a
fixed **~15 s off the LOAD** of every run at any row cap, which is a *larger*
share of a sample run than of a full one, and **3.44× off the per-row walk**
that every catalog row pays whether or not it turns out to be evaluable: 
~67-78 s on a full cislunar pass. See [calc v1.17.4](versions.md#calc-v1174--catalog-v111).

⚠️  **`1.17.5` is shaped like `1.17.2`, not like `1.17.4`, and it is the
SMALLEST perf stamp in the project: 1.06×, not 1.4-2×.** Every item in it
removes work that only exists when a programme LADDER exists, so both
search-OFF cells measure **1.00-1.01×** and both search-ON cells **1.06×**.
That flatness is the finding, not a disappointment: six perf releases have now
run through this search, and what is left in the ladder is per-option overhead
measured in tens of nanoseconds. **Do not quote a single number for it**, and
do not expect another 1.5× from this code path. ⚠️  `1.17.6` did not, and it is
the check on that sentence rather than a counter-example: it is worth 1.10× on
the default cell, and the ~3.6% of it that comes from the ladder is the ladder
being *rebuilt* per candidate rather than anything inside a rung. See
[calc v1.17.5](versions.md#calc-v1175).

🚨  **`1.17.6` IS THE FIRST PERF STAMP HERE THAT LANDS ON THE PER-ROW WALK
RATHER THAN ON THE SEARCH, so it is the first that is worth MORE on raw than on
the default cell, and the first whose ratio depends on the ROW CAP.** Measured
1.14-1.19× raw / 1.04-1.07× beneficiated / 1.16× raw-searched / 1.10-1.11× on
the default cell, at caps of 6,000 / 800 / 3,000 / 800 rows. At the
**150/400-row caps every previous release measured itself on it reads
1.03-1.10×**, because the fixed ~1.6 s (the catalog integrity walk plus the
pre-filter probe) is half of those cells and does not move. **Quote the cap
with the ratio**, and prefer the per-row figures: **1.15 / 1.05 / 1.18 /
1.12×**, which are what a full pass actually pays.

✅  **Its largest item is the third instance of v1.17.4's finding, and this
file now has that finding on both sides of the CSV boundary AND in between.**
`asteroid_bulk_value_usd_per_kg`, `asteroid_phase_table` and
`asteroid_best_phase_usd_per_kg` read five values off a row and nothing else,
all five derived by Module 1 from `spectral_type` alone: **~25 distinct
composition tuples across 1,555,667 rows**, and eleven in a 4,000-row stride.
They were walking `FRACTION_TO_MINERAL` three times per asteroid, with a
`pd.isna` on a scalar per entry, to re-derive one of a couple of dozen answers:
**56.5 µs/row, ~88 s of every full beneficiated pass and ~41 s of a raw one**,
paid by every catalog row whether or not it turns out to be evaluable. Memoised
on the composition they come to **3.74 µs** (12.3× / 11.2× / 21.6×). See "What
calc v1.17.6 changed".

ℹ️  **catalog `1.1.1` ships alongside it and is the same finding upstream.**
`enrich_composition` was resolving twelve `.apply()` passes over 1.55 M rows to
produce the ~800 answers 76 taxonomy classes can give: **9.09 s → 2.35 s**, all
12 derived columns identical. It changes no number and no CSV; the stamp moves
so a catalog still names the code that built it.

🚨  **calc `1.17.0` FLIPPED TWO DEFAULTS, so a default run no longer reproduces
almost any table in this file.** `use_beneficiation` and
`optimise_programme_scale` are both **True** now. No model term, coefficient,
table value or search axis moved; an explicitly configured run is
bit-identical to `1.16.0`, but the question a *configured-nothing* run asks
has changed, from "the best single mission to this rock" to "the best
programme built around it, flying concentrate". Set both False to get the old
answer; both OFF cells were re-measured on the full catalog on 2026-08-11 and
**reproduce exactly**. See [calc v1.17.0](versions.md#calc-v1170).

⚠️  **`1.15.0` AND `1.16.0` MOVE NUMBERS ONLY FOR PROGRAMMES, and almost every
measured cell in this file is a single mission.** Three items between them: 
`1.15.0`'s duty-cycle cap on rig life and its searched programme size,
`1.16.0`'s programme calendar charge, are all exactly inert at N = 1 (W = 1,
one campaign per ship). Verified rather than argued: on the 400-row raw
cislunar sample at N = 1, `1.16.0`'s term on and off is **141 of 141 columns
identical, sha256 MATCH**.

**Do not re-measure a single-mission cell on account of either release**, and
do not read any table as covering an `optimise_programme_scale = True` run
unless it says so; the searched columns of
[the 28-cell matrix](README.md#current-results-the-complete-28-cell-matrix) are
the ones that do. The N = 10 / N = 100 curve **does** move, and is now a
`1.14.0` measurement of a model superseded twice.

🚨  **"and the search is default OFF" was true until calc `1.17.0` and is now
wrong.** It is default **ON**, along with `use_beneficiation`. The sentence is
corrected rather than deleted because it is exactly the failure mode this file
exists to catch, a default named in prose, three releases from the code that
sets it.

✅  **That inertness is not an argument, it is a full-catalog measurement.** A
1,554,353-row cislunar raw run on `1.15.0` returns **26.7863× on 650,516
evaluable rows with 2021 CX5 winning on xenon and a New Glenn**: the committed
`1.14.0` cell, reproduced down to the payload in kilograms and the propellant
split. It also puts `1.14.1` + `1.14.2` at a measured **4.10×** on a full cell
(5,350 s → 1,306 s), inside their projected 3.4-4.6×.

🚨  **The programme search costs 1.51× runtime, not the 1.04-1.13× this file
first recorded** from a 2,500-row sample. Third sample-mispredicts-runtime
finding in this project, and the first to apply to a *ratio* rather than an
absolute. See [calc v1.15.0](versions.md#calc-v1150--transportation-v1120).

> 🚨  **That 1.51× is `1.15.0`'s ONE-dimensional ladder and does not carry to
> `1.16.0`, whose search is two-dimensional. Measured on the full catalog on
> 2026-08-11: 2.98× (1,307 s → 3,890 s).** `1.16.0`'s own section projects
> 1.10× from a 400-row sample. That is the **fourth** full-catalog runtime
> prediction this project has gotten wrong from a sample, and the **second**
> for a ratio rather than a wall clock. The mechanism is legible in the output
> and is not mysterious: `programme_options_priced` runs a median of **40**
> against the 1-D ladder's 8, because W is enumerated exhaustively inside every
> rung of the F ladder.

⚠️  Three of the five stamps in the `1.14.x` line are performance-only, which
is the sharpest illustration of why the table above is worth reading before
treating a version bump as evidence.

## What the model currently says, and what that retired

Everything from here to "When a number changes" is **measurement**, not
guidance.

Read it before re-measuring anything, and before "fixing" a result that looks
wrong: that is what it is for. **The headline numbers themselves are
[README.md's](README.md#current-results-the-complete-28-cell-matrix)**; what is
here and not there is the per-destination detail, the invariants, and the
claims each cell retired.

### ✅ THE COMPLETE 28-CELL MATRIX IS MEASURED (calc `1.21.2`, 2026-09-11/13)

🚨  **AND AS OF calc `1.22.0` IT IS NO LONGER WHAT A CONFIGURE-NOTHING RUN
ANSWERS.** Four defaults moved on 2026-09-14 and every cell below predates
them: the surplus past a market ceiling was **abandoned** rather than sold at
half price, and reliability, the learning curve and the cost of capital were
all **charged**. Set `sell_surplus_at_discount` False, `model_reliability`
True, `model_learning_curve` True and `apply_wacc_compounding` True to
reproduce anything in this section.

⚠️  **DO NOT SCALE THESE CELLS BY A SINGLE RATIO.** On the capped cislunar
sample cells the four together are worth 2.6x on raw ore and 2.1x on the
default cell, the cost of capital alone is 42-52% of it, and the learning
curve runs the OTHER way and is exactly inert at N = 1. The decomposition is in
[calc v1.22.0](versions.md#calc-v1220). What is below is a measurement of the
model it names, which is why it is kept: it is still the only seven-destination
measurement the project has.

🚨  **The headline matrix and the result highlights are in
[README.md](README.md#current-results-the-complete-28-cell-matrix), and are not
copied here**, for the reason this file gives everywhere else: name one
authority or you have two. What follows is the part a README should not carry:
per-destination depth, the invariants, and the claims each cell retired. The
campaign's own record, including what it cost and what it cannot support, is
[`campaign/FINDINGS.md`](campaign/FINDINGS.md).

**Seven destinations are measured now**, not five. `mars_orbit` and `geo` had
never had a cell run at either until this campaign, so every "at every
destination" sentence below means one of two things and you have to check which:
the **2026-09** campaign measured the objective, the evaluable set, the winner
and the invariants at all seven, and nothing else at any of them.

✅  **THAT GAP IS CLOSED AS OF 2026-09-14: EVERY SECTION BELOW IS NOW A 2026-09
`capacity_cap` MEASUREMENT.** The 2026-09 campaign extracted the winner row and
ran the invariants and nothing more, so the propellant shares, the vehicle
shares, the rig's two bounds, the cadence and the saturation diagnostics
remained 2026-08 `elasticity` figures with insurance charged for three days.
`campaign/population.py` re-derived all of them from the archived cells under
`campaign/cells/`, which carry every column needed: **one pass, about ten
minutes, and no stage re-run.** See
[the population re-derivation](versions.md#the-population-re-derivation-2026-09-14).

🚨  **RE-READING A CELL IS THE CHEAPEST MEASUREMENT IN THIS PROJECT AND IT WENT
UNTAKEN FOR THREE DAYS WHILE FIVE SECTIONS CARRIED A WARNING INSTEAD.** The
campaign cost 26 hours of compute and archived 11 GB precisely so that questions
like these would not need a re-run; the tables above sat stale because nobody
had written the reader, not because the data was missing. **When a section says
"not re-derived", check whether the inputs are already on disk before believing
the cost.**

⚠️  **Four of the five sections changed a documented CONCLUSION, not just a
level**, which is the argument against leaving such a gap open: `mars_surface`
stopped being the exception to the beneficiated inversion, `saturation_multiplier`
turned out to be identically 1.0 and therefore dead as a diagnostic, "ISRU tracks
hydrolox to within 0.03 pp" failed at three destinations, and iodine went from
winning two beneficiated cells to three.

Two facts everything below leans on: **`cislunar` is the best case on all four
settings**, though `mars_orbit` is now within 11% of it on the default cell,
and **the programme search never changes the evaluable set** at any of the seven
destinations, as it must not, since N enters nothing in the mass cascade.

🚨  **THE 28-CELL MATRIX IS NOT COMPARABLE CELL-FOR-CELL WITH THE 20-CELL ONE,
AND FOUR THINGS MOVED AT ONCE**, so no single delta can be attributed to any
one of them:

| what moved | from | to |
|---|---|---|
| destinations | five | **seven** |
| `market_model` | `elasticity` | **`capacity_cap`** |
| `charge_insurance` | True | **False** |
| price epoch | 2026-08-23 | **2026-09-09** |

The superseded matrix, the per-cell wall clocks and what the campaign cannot
support are in
[the 28-cell campaign](versions.md#the-28-cell-campaign-2026-09).

🚨  **AND THE THING TO INTERNALISE IS THAT THE WINNER MOVED AND THE POPULATION
DID NOT.** Winner rows moved 8-69% between the two campaigns; the beneficiation
population medians moved **0.1 to 2.3 percentage points**:

| destination | benef, winner row | benef population median, 2026-09 | the same, 2026-08 |
|---|---|---|---|
| `cislunar` | -8.4% | **+39.4%** | +39.5% |
| `lunar_surface` | -36.5% | **+66.1%** | +63.8% |
| `earth_surface` | -6.5% | **+77.7%** | +77.7% |

⚠️  The columns use opposite conventions and are not each other's negation; the
median is `median(1 - r)` over the evaluable population, which is the committed
convention, and the winner column is one row against its 2026-08 counterpart.

✅  **This is the sharpest instance in the project of the rule under
[A diagnostic describes the WINNER](#a-diagnostic-describes-the-winner-not-the-search-that-produced-it).**
`capacity_cap` and the insurance removal reshaped the TOP of the distribution
and left the middle where it was. **A headline that moves 50% over a median that
moves 0.1 pp is a statement about one asteroid**, and this file is full of
headline numbers. Quote a median before claiming the model changed.

#### What the two new destinations settled

⚠️  **They are not two more of the same thing, and that is why they were worth
adding together.** `mars_orbit` is the control on the ISRU discount: it takes
the base utility profile, so it isolates how much of the `mars_surface` result
is the crust rather than the distance. `geo` is the control on the other end,
the smallest in-space market in the model at 40 t/yr, where `earth_surface` is
the one whose market is so deep that saturation is numerically inert.

✅  **`mars_orbit` came second at all four settings and is the most reachable
destination in the model**, 956,090 evaluable bodies beneficiated against
`cislunar`'s 660,253. **So the ISRU discount that carries the `mars_surface`
result is a property of being ON Mars, not of Mars**, which is exactly what an
empty override dict was put there to test. Distance is an advantage here: a
main-belt body is cheaper to deliver to Mars than to Earth.

🚨  **`geo` IS WORST RAW AND THIRD BEST BENEFICIATED, SO THE DESTINATION
RANKING DEPENDS ON THE CONFIGURATION.** It is 5th of the in-space five as a
single raw mission and 3rd as a beneficiated programme. This file already says
every propellant-share claim is a statement about a configuration rather than
about the model; that caution now reaches **which destination is best**.

The mechanism is the utility table and not delivery cost: `geo` is priced at
$12,526/kg, *above* cislunar, and still loses at N = 1, because it is the first
destination whose overrides run downward on **metals and rock** rather than
volatiles. Concentrating is therefore worth more at `geo` (-58.3%) than
anywhere else measured, which extends rather than contradicts this file's
standing finding that `cislunar` is the WORST place to concentrate: the value
of beneficiation tracks how little the destination pays for what you would
otherwise ship.

🚨  **AND THE FIRST THING A `mars_orbit` CELL WOULD HAVE MEASURED WAS A DEFECT,
WHICH IS WHY IT IS WORTH RUNNING A DESTINATION EARLY.** `synodic_period_yr`'s
second argument was chosen by a conditional testing `== "mars_surface"`, written
in two places, so the destination added one release later took the `else` branch
and waited on Earth/Mars alignment that a 1-sol Mars depot does not fly to.
Wrong on **99.97%** of a 38,892-row stride sample. Fixed in calc `1.19.2`, which
reads the figure off `DELIVERY_ARCHITECTURES` instead.

⚠️  **The lesson is the one this file already states about branches, arriving
from the other side.** "An unreachable branch is not a verified branch" is about
a branch nothing fires; this is a branch that fires for **the wrong member of a
family**, and it is invisible for exactly the same reason: no cell of the
affected destination had been run. The general shape is **a conditional that
names one member of a set instead of asking the set a question**, and the
defence is the one taken here: put the answer in the table where a destination
already declares what it is, and assert the field is total.

#### Reproduction, and the one thing that did reproduce exactly

🚨  **THE 2026-09 CAMPAIGN CANNOT REPRODUCE THE 2026-08 CELLS AND WAS NEVER
GOING TO**, because all four of the things in the table above moved. What it
can be held to is narrower and was checked:

| what | result |
|---|---|
| evaluable rows, every destination measured in both campaigns | **identical**, all five |
| `earth_surface` evaluable, raw / benef | **784,242 / 912,846**, the committed figures |
| `leo`'s winners, all four cells | **identical**, 2018 DT at N = 1 becoming 2021 CX5 searched |
| a capped smoke cell against the committed `capacity_cap` sample | **25.7233x, 2017 KJ5, Falcon Heavy on iodine at 97,875 kg**, exact |

✅  **`leo` reproducing its structural signature is the strongest of these.**
This file records `leo` as the one destination where the best single mission and
the best programme are DIFFERENT BODIES. That held under a different market
model with insurance off, which is a stronger test than the measurement it
reproduces.

✅  **And the evaluable sets being identical across a market-model change is
the invariant it looks like.** Which rows are evaluable falls out of the mass
cascade, and neither N nor any price enters it. Had those counts moved, the
ceiling would have been reaching the SIZING path, which is the one thing the
`caps=None` guard exists to prevent.

⚠️  **`650,516` IS NOT A DISAGREEMENT WITH EITHER CAMPAIGN, AND THIS FILE USED
TO IMPLY IT WAS.** Both campaigns report **650,921** for cislunar raw,
identically. 650,516 belongs to a calc `1.15.0` run on a **1,554,353-row**
catalog snapshot rather than the 1,555,667-row one both campaigns used.
Different catalog, not different code. **A count quoted without its catalog is
not a measurement**, which is the same rule this file applies to wall clocks and
releases.

#### Invariants: clean on all twenty-eight cells

**70 checks, 0 failures**, from `campaign/analyse.py` over the archived cells:

- **never-worse**: **28 pairings, zero exceptions**, every max <= 1.000000,
  beneficiated <= raw and searched <= N = 1, at all seven destinations
- **mass ledger**: `max |error| 0.000000000 kg` on all 28 cells
- **programme structure**: **N = F x W on every row** of all fourteen searched
  cells, and **W > `trips` never**

🚨  **THE STRUCTURAL CHANGE IS THAT PROGRAMMES NOW DECLINE THE RIG'S LAST
TRIPS, BY TWO ORDERS OF MAGNITUDE.** `W < trips`, raw searched:

| destination | 2026-09 | 2026-08 |
|---|---|---|
| `mars_orbit` | **35.99%** | never measured |
| `mars_surface` | 32.73% | 3.71% |
| `cislunar` | 20.86% | **0.319%** |
| `lunar_surface` | 16.07% | 0.225% |
| `geo` | 12.97% | never measured |
| `leo` | 8.09% | 0.161% |
| `earth_surface` | 0.270% | 0.234% |

⚠️  **`geo`'s row was missing from this table until 2026-09-14**, which is the
seven-destinations-in-a-six-row-table failure this file warns about everywhere
else: the table beside it lists all seven, so the two disagreed about the size of
the campaign. Filled from `campaign/population/`, not re-run.

Under a hard ceiling the extra campaign cannot be **SOLD**, where under a demand
curve it could always be sold at a worse price. Fleet and programme sizes moved
with it: `cislunar` **beneficiated searched** went from a fleet median of 2 to 6
and an N median of 10 to 30. ⚠️  **Name the cell.** The RAW searched medians are
**3 and 12**, and this sentence sitting in a paragraph about raw searched rows
is what put "a median searched fleet of 2" into README's ceiling argument, where
it was both the wrong cell and the wrong campaign.

⚠️  **So this file's statement that "2,077 bodies decline to use up the rig" is
an `elasticity` claim**, and under `capacity_cap` it is ~146,000. It is the
same mechanism reported against a different market term, not a new one.

Bodies declining to concentrate, and the population medians, on the 2026-09
campaign:

| destination | declining | benef median | search median |
|---|---|---|---|
| `cislunar` | 108,985 (16.7%) | +39.4% | +48.3% |
| `leo` | 86,090 (11.1%) | +41.2% | +59.6% |
| `mars_orbit` | 60,908 (7.4%) | +33.0% | +41.4% |
| `geo` | 55,171 (7.8%) | +47.4% | +37.4% |
| `lunar_surface` | 22,972 (3.9%) | +66.1% | +51.3% |
| `earth_surface` | 8,500 (1.1%) | +77.7% | +67.2% |
| `mars_surface` | 4,219 (0.6%) | +73.6% | +47.0% |

⚠️  **The decline counts are close to the 2026-08 figures and the ordering is
unchanged**, which is the population result again: `lunar_surface` 22,972
against 22,781, `earth_surface` 8,500 against 8,340. The market model barely
touches which bodies refuse to concentrate.

### 🚨 `earth_surface`'s SEARCHED CELLS ARE NOT OPTIMA, UNDER EITHER MARKET MODEL

✅  **Re-confirmed on the 2026-09 campaign, and it is the same answer for a
DIFFERENT reason, which is the part worth having.** Under `elasticity` the
price never moved because terrestrial markets run 10¹²-10¹⁵ kg/yr; under
`capacity_cap` the ceilings are finite and still far too large for a programme
delivering ~10⁷ kg to reach. Measured: **100.000% of rows at
`max_fleet_ships`**, both searched cells, exactly as before, against
`cislunar`'s **9.99% raw and 17.77% beneficiated**.

🚨  **So `11,606.86x` and `7,074.20x` are the value at the ladder's TOP RUNG,
not optima.** Raise `max_fleet_ships` and they keep improving.

⚠️  **And the cislunar figure moved by a factor of 25**, from 0.37-0.40% under
`elasticity`, so this diagnostic now counts a larger and partly different
population: a row sits at the ceiling either because no finite market bounds it
**or** because its payload is too small to reach one. That is the warning under
[A wall does not blend](#a-wall-does-not-blend-so-a-diagnostic-can-change-meaning-under-you)
arriving on schedule, at a destination it was not written about.

🚨  **RE-DERIVED 2026-09-14, AND `saturation_multiplier` IS IDENTICALLY 1.0 ON
ALL TWENTY-EIGHT CELLS.** Min, median and max, every destination, every setting.
The column is not stale here; it is **inert**. `capacity_cap` does not bend a
price as a market fills, so the multiplier that expressed `elasticity`'s
haircut has nothing left to express and the whole table this section used to
carry has no information in it.

⚠️  **THE REASON CHANGED IN calc `1.22.0` AND THE CONCLUSION DID NOT, WHICH IS
WORTH READING CAREFULLY.** This paragraph used to say the multiplier is 1.0
because the ceiling "refuses the sale". It no longer refuses it: the surplus
past a ceiling SELLS, at `surplus_price_fraction` of full price. The multiplier
is still identically 1.0 -- `verify.py` check 7 asserts it on every cell -- but
now it is because the discount is applied **in the sale and in the knapsack**
rather than through the elasticity multiplier, not because no sale happens. A
diagnostic that stays constant across a model change for a DIFFERENT reason is
the subtlest version of this section's own lesson.

✅  **THE LIVE DIAGNOSTIC IS `market_clearing_fraction`**, which says what
fraction of an assembled load actually cleared, with `unsold_payload_kg`
alongside it. Searched cells:

🚨  **AND THE COMPANION COLUMN MOVED IN calc `1.22.0`: IT IS
`surplus_payload_kg` NOW, AND `unsold_payload_kg` READS 0.0.** Mass past a
ceiling is sold at a discount rather than abandoned, so it lands in the new
column and the old one goes quiet. The two are exclusive by construction and
check 7 asserts it. **The `unsold rows` column in the table below is therefore
a v1.21.2 measurement**, and a harness that kept counting `unsold_payload_kg`
across the flip would report zero everywhere and read as "nothing is ever lost
to a ceiling", which is false -- ceilings still bind on 18 to 96% of rows at
the six in-space destinations. That is this section's own lesson happening to
this section: **when you swap a model term, check whether the diagnostics that
watched it still VARY.**

| cell | rows at fleet cap | clearing min | clearing median | rows bound | unsold rows |
|---|---|---|---|---|---|
| `cislunar` raw | 65,037 (9.99%) | 0.578190 | 1.000000 | 30.07% | 195,723 |
| `cislunar` benef | 117,314 (17.77%) | 0.679429 | 1.000000 | 30.27% | 65,373 |
| `lunar_surface` raw | 64,397 (10.99%) | 0.491063 | **0.833930** | **70.18%** | 411,271 |
| `lunar_surface` benef | 37,532 (6.19%) | 0.637028 | 1.000000 | 38.80% | 25,803 |
| `geo` raw | 7,673 (1.09%) | 0.465097 | 0.965855 | **73.47%** | 518,014 |
| `geo` benef | 28,961 (4.07%) | 0.730985 | 1.000000 | 27.07% | 67,293 |
| `mars_orbit` raw | 22,962 (2.80%) | 0.560660 | 0.996629 | 54.48% | 447,323 |
| `mars_orbit` benef | 133,854 (14.00%) | 0.814357 | 1.000000 | 34.76% | 72,003 |
| `leo` raw | 33,826 (4.35%) | 0.888516 | 1.000000 | 23.33% | 181,238 |
| `leo` benef | 275,537 (31.22%) | 0.834402 | 1.000000 | 20.05% | 34,996 |
| `mars_surface` raw | 25,687 (3.51%) | 0.590189 | **0.848755** | **96.25%** | 703,876 |
| `mars_surface` benef | 132,801 (14.88%) | 0.763270 | 1.000000 | 18.12% | 6,977 |
| **`earth_surface` raw** | **784,242 (100.00%)** | **1.000000** | **1.000000** | **0.00%** | **0** |
| **`earth_surface` benef** | **912,846 (100.00%)** | **1.000000** | **1.000000** | **0.00%** | **0** |

🚨  **A CEILING BINDS ON 18 TO 96% OF ROWS AT THE SIX IN-SPACE DESTINATIONS,
AND ON EXACTLY ZERO AT `earth_surface`.** That is the cleanest statement the
project has of what `capacity_cap` does, and it is the same conclusion the
`elasticity` table reached by a different route: terrestrial markets run
10^12 to 10^15 kg/yr against a programme delivering ~10^7 kg, so nothing
bounds them at any fleet size the ladder can reach. Under a demand curve the
`earth_surface` multiplier departed from 1.0 by a median of 2.3e-11; under a
hard wall it does not depart at all, and **zero kilograms go unsold on
1,697,088 rows.**

⚠️  **THE `mars_surface` RAW CELL IS THE OPPOSITE POLE AND IT IS WORTH
KNOWING.** 96.25% of its rows are bound and 703,876 of them leave payload
unsold: a Mars base importing 20 t/yr is the shallowest market in the model
against the largest deliveries, so almost nothing clears whole. `lunar_surface`
raw (70.18%) and `geo` raw (73.47%) are the other two where the median row is
bound rather than clearing.

✅  **BENEFICIATION RELIEVES THE CEILING EVERYWHERE EXCEPT `cislunar`.** Bound
rows fall from 70.18% to 38.80% at `lunar_surface`, 96.25% to 18.12% at
`mars_surface`, 73.47% to 27.07% at `geo`, and unsold rows fall by one to two
orders of magnitude. Concentrating is exactly the way to sell the same value in
fewer kilograms, so it is the lever that gets a load under a wall. `cislunar` is
the exception at 30.07% to 30.27%, which is consistent with its standing
position as the worst place in the model to concentrate.

🚨  **AND THIS IS WHY THE DIAGNOSTIC HAD TO BE SWAPPED RATHER THAN
RE-MEASURED.** This file already warns, under
[A wall does not blend](#a-wall-does-not-blend-so-a-diagnostic-can-change-meaning-under-you),
that "a diagnostic inherits the shape of the term it was written against". That
note was about a row COUNT changing meaning. This is the harder version: the
column went **constant**, so a harness that kept reporting it would have printed
1.000000 forever and read as a clean result rather than a dead one. **When you
change a model term, check whether the diagnostics that watched it still VARY**,
not only whether their levels moved.

⚠️  **Rows at `max_fleet_ships` now range over two orders of magnitude**, from
`geo` raw at 1.09% to `earth_surface` at 100%, and `leo` beneficiated at 31.22%
is the highest of the in-space cells. The 2026-08 `elasticity` campaign put
`cislunar` at 0.37-0.40%; it is 9.99-17.77% now, the factor of 25 this file
already records, and the reason is the one given there: under a wall a row sits
at the ceiling either because no finite market bounds it **or** because its
payload is too small to reach one.

It also re-scopes mineral_value `1.7.1`'s "measured and declined" note on
`nickel-iron` having no terrestrial market ceiling. That item was costed at
**7.7e-8 relative on a SINGLE MISSION's multiplier**: correct, and the wrong
scope. With the search on, a missing ceiling changes the **shape** of the
objective in N rather than its level, and a shape change has no size. ⚠️  It is
now a `capacity_cap` question rather than an `elasticity` one, and the
`earth_surface` column above is the measurement of it: a commodity with no
ceiling is a commodity that never refuses a sale, which is exactly the 0.00%
bound and 0 unsold that destination reports.

### 🚨 RETIRED TWICE: a `replicated` device wins TWO cells now, at `mars_surface`

This file's standing claim is "**A `replicated` device never wins anywhere**; 
eight cells, zero wins", qualified by its own warning that "on half the cells
it holds by a few percent, not by a factor, and a modest change to thruster
mass or to the population could flip one."

✅  **THE 2026-09 CAMPAIGN WIDENED IT RATHER THAN FLIPPING IT BACK.**
**2014 YN on FEEP now wins BOTH raw `mars_surface` cells**, at N = 1 as well as
searched, where at N = 1 in 2026-08 the best FEEP mission sat at rank 5 and
1.06x off. So the claim retired below was retired for one cell and is now wrong
for two, and it took `capacity_cap` plus the insurance removal rather than a
change to the gate.

⚠️  **It does not survive beneficiation at either setting.** Both beneficiated
`mars_surface` cells go to conventional Hall thrusters on different bodies
entirely, krypton on 9992 and iodine on 2003 RS1. Concentrating changes the mass
budget enough that 6.7 tonnes of thruster stops paying, which is the gate
behaving as a mass penalty exactly as designed. **Zero FEEP winners at the other
six destinations**, on any setting.

✅  **RE-DERIVED 2026-09-14 ON ALL TWENTY-EIGHT CELLS** by
`campaign/population.py`, off the `thrust_scaling` column rather than by
matching propellant names, which is the authoritative gate and covers a
technology nobody thought to list. Best `replicated` mission per cell, rank and
margin against the cell's winner:

| destination | raw N = 1 | raw searched | benef N = 1 | benef searched |
|---|---|---|---|---|
| `cislunar` | 54 (1.43x) | 365 (1.95x) | 147 (1.52x) | 2,202 (1.92x) |
| `lunar_surface` | **none** | **none** | **none** | **none** |
| `geo` | 91 (1.70x) | 15,904 (4.75x) | 1,687 (1.83x) | 38,047 (2.77x) |
| `mars_orbit` | 28 (1.41x) | **15 (1.36x)** | 51,532 (2.29x) | 3,889 (1.60x) |
| `leo` | **8 (1.15x)** | 47 (1.28x) | 43 (1.26x) | 5,744 (2.09x) |
| **`mars_surface`** | **1, WINS** | **1, WINS** | **2 (1.00x)** | **2 (1.01x)** |
| `earth_surface` | 6 (1.07x) | 5 (1.08x) | 10 (1.11x) | 10 (1.16x) |

✅  **`lunar_surface` STILL HAS ZERO SURVIVORS IN ALL FOUR CELLS**, across a
market-model change, an insurance removal and a new price epoch. That is the
single most durable statement in this section and it reproduces exactly.

🚨  **`mars_surface` BENEFICIATED IS NOW A ROUNDING AWAY FROM FLIPPING TOO.**
Both beneficiated cells put the best FEEP mission at **rank 2, margin 1.00x and
1.01x**, where the 2026-08 campaign had them at rank 73 (1.11x) and rank 14
(1.06x). So the claim retired here is not merely retired at Mars, it is close to
being retired at all four Mars surface cells at once, and the thing standing
between is under one percent. This file's own lesson applies to its successor:
*a margin of a few percent is not a law.*

⚠️  **`mars_orbit` IS THE SECOND DESTINATION WHERE THE SEARCH HELPS A FEEP
MISSION RATHER THAN HURTING IT**, going rank 28 to rank 15 between N = 1 and
searched on raw ore. Everywhere else the programme search pushes FEEP *down* the
ranking, by a factor of 7 at `cislunar` and 175 at `geo`, because a ladder that
buys more, smaller missions cannot amortise 4 to 17 tonnes of thruster.

✅  **EVERY SURVIVOR IN EVERY CELL IS STILL FEEP.** Across all 28 cells and
every `replicated` row in them, the only technology that appears is **FEEP
(indium field emission)**: not one PPT and not one electrospray row survives
anywhere, at any destination, ore state or programme size. Only the lightest of
the three (2,500 kg/N against 5,000 and 10,000) ever closes a mass budget, and
that is now checked on seven destinations rather than five.

⚠️  **The survivor COUNT moved a long way and still proves nothing**, which is
the point of the next paragraph. Counts now run from **zero** at
`lunar_surface` to **6,220** at `earth_surface` raw searched, with `cislunar` at
76-515 and `leo` at 3,696-5,346. `geo` and `mars_orbit`, measured for the first
time, land at 723-976 and 134-270.

**The 2026-08 measurement that first retired the claim** is kept below because
it is the one that names the mechanism, and its architecture detail was not
re-extracted:

```
rank 1   2014 YN     (M)  41.8068x   FEEP (indium field emission)   H3 (24L)       N = 5
rank 2   2015 BM510  (M)  47.4127x   methalox                       Falcon Heavy   N = 5
```

It won by **13.4%**, carrying **6,667 kg of thruster for 96.7 kW**.

✅  **The gate is not broken and must not be "fixed".** `thruster_kg_per_n` is
a mass penalty rather than a threshold, that was the whole design argument,
and this mission pays 6.7 tonnes of thruster and wins anyway, which is the
mechanism working, not leaking. What is retired is the **claim**. The lesson is
the one v1.14.0 already wrote down for the RTG branch: *a margin of a few
percent is not a law*, and here one new search axis was enough to close it.

🚨  **SURVIVAL WAS NEVER THE TEST, AND THE COUNT IS THE REASON.** The
survivor count spans from **zero to 6,220 across destinations on one model, one
catalog and one release**. A claim built on a count is a statement about the
**population**, not about the gate, which is how "zero survive anywhere"
survived as a law for a release; it was measured on 15,566 rows.
**Test whether one WINS.**

Two facts about the survivors that do not change with the population:

- **Every survivor in every cell is FEEP.** Not one PPT and not one
  electrospray row survives anywhere, at any destination or programme size,
  where the pre-gate model had PPT winning **31.8%** of cislunar rows and
  electrospray **24.3%**. Only the lightest of the three `replicated`
  technologies (2,500 kg/N against 5,000 and 10,000) ever closes a mass budget.
  ✅  Re-checked on all 28 cells 2026-09-14, and it holds; the row count that
  used to be quoted here was a 2026-08 total over twenty cells and is deliberately
  gone, because **the claim is about which technology, never about how many
  rows**, which is the mistake the paragraph above it exists to name.
- **They close by being enormous, not by being efficient.** Survivors carry
  **4.4 to 16.7 tonnes** of thruster (median 13.2 t raw) for ~5 N, and close
  only because their payloads are 70-128 t and can absorb it.

### Runtime, and the three quantities a sample cannot predict

🚨  **THE 2026-09 CAMPAIGN RE-MEASURED EVERY WALL CLOCK AND THE DIRECTION
REVERSED.** A default cislunar run is **~2.7 h**, not 1.6 h: v1.21.0's capacity
ceilings are priced inside the payload knapsack and cost **1.29x to 2.31x**,
landing hardest where a programme LADDER exists, which is the opposite shape to
the v1.17.x line that had made everything faster. The twenty-eight-cell wall
clock is in [README.md](README.md#beneficiation) and the per-cell table is in
[the 28-cell campaign](versions.md#the-28-cell-campaign-2026-09).

⚠️  **So the sentence below is now wrong in BOTH directions depending on the
release you are reading**, which is exactly why it is left standing rather than
quietly edited: everything older than `1.17.7` is high by 1.78-4.32x, and
everything older than `1.21.0` is LOW by 1.29-2.31x. A wall clock in this
project is only ever true of the release it names.

**Wall clocks and cost ratios live in
[versions.md](versions.md#what-the-v117x-line-was-worth)**, which measured the
whole `1.17.x` line on the full catalog at once; the twenty-cell wall clock is
in [README.md](README.md#beneficiation). Neither is repeated here. The three
things that are *guidance* rather than record:

🚨  **A default cislunar run is now ~1.6 h, not 6.8 h**, and **every timing or
cost ratio in this project older than calc `1.17.7` is high by 1.78-4.32×.**
Five committed ratios moved as a consequence, including the two most quoted:
beneficiation costs **4.67×** rather than 7.1×, and the programme search
**1.71×** rather than 2.98×. ⚠️  Those are `cislunar` figures; `leo`,
`mars_surface` and `earth_surface` cost 2.1-2.7× more per cell.

⚠️  **The forbidden arithmetic was finally scored, and the prohibition held on
direction while being generous on magnitude.** Compounding the five releases'
stride-sample ratios lands within 3% on three cells and **20% low on the
default cell**, i.e. the only cell anybody runs and the one you were trying to
budget. Compounding understates; it is not permission to compound.

✅  **Memory is the third quantity under THE SAMPLING RULE**, after wall clocks
and ratios. Peak RSS tracks **output size**, not ladder traffic: 8.2 GB at
`lunar_surface` beneficiated up to **10.4 GB** at `leo` beneficiated N = 1, the
cell with the most evaluable rows, against 30.4 GB of system use. The rise
within a cell is the parent accumulating result rows. ⚠️  Two apparent peaks of
11.54 and 10.74 GB are **measurement contamination**, the two cells that
overlapped an analysis process; attributing your own harness to the thing you
are measuring is how a clean result becomes a false alarm.

### The rig's two bounds, and the cadence, at every destination (2026-09)

✅  **RE-DERIVED 2026-09-14 ON ALL TWENTY-EIGHT CELLS**, by
`campaign/population.py`, which reads the archived cells rather than re-running
anything. Every figure below is `capacity_cap` with insurance OFF, and is
directly comparable with the rest of the 28-cell campaign. ⚠️  **And with calc
`1.21.2`, not with a default run today**: `1.22.0` sells the surplus past a
ceiling at half price and turns reliability, the learning curve and the cost of
capital off. See the banner on the 28-cell section. The superseded
`elasticity` tables are in
[the 28-cell campaign](versions.md#the-28-cell-campaign-2026-09).

⚠️  **The denominator is not a choice here, and this file's own warning about
two right answers does not reach these tables.** An archived cell holds
evaluable rows ONLY, because `run_cell.py` archives what
`build_profitability_catalog` returns and that is already filtered: cislunar raw
searched is 650,921 rows and 650,921 evaluable. Every percentage below is over
the population every headline is quoted over.

**Which bound retires the rig** (cycle = `max_trips`, calendar = `life / stay`):

| destination | raw N=1 | raw ON | benef N=1 | benef ON |
|---|---|---|---|---|
| `cislunar` | 95.97 / 4.03 | 97.51 / 2.49 | 57.51 / 42.49 | 75.98 / 24.02 |
| `lunar_surface` | 95.92 / 4.08 | 96.36 / 3.64 | 70.62 / 29.38 | 90.97 / 9.03 |
| `geo` | 98.80 / 1.20 | 98.92 / 1.08 | 63.04 / 36.96 | 84.15 / 15.85 |
| **`mars_orbit`** | **60.63 / 39.37** | **62.76 / 37.24** | **21.87 / 78.13** | **25.84 / 74.16** |
| `leo` | 98.64 / 1.36 | 98.90 / 1.10 | 47.58 / 52.42 | 77.28 / 22.72 |
| **`mars_surface`** | **80.37 / 19.63** | **85.37 / 14.63** | **18.34 / 81.66** | **20.15 / 79.85** |
| `earth_surface` | 98.64 / 1.36 | 98.76 / 1.24 | 29.43 / 70.57 | 48.01 / 51.99 |

**What sets the pace** (window = synodic period, dig = mining rate), and the
median cadence:

| destination | raw N=1 | benef N=1 | cadence raw | cadence benef |
|---|---|---|---|---|
| `cislunar` | 91.98 / 8.02 | 34.34 / 65.66 | 1.384 yr | 2.100 yr |
| `lunar_surface` | 96.08 / 3.92 | 37.66 / 62.34 | 1.384 yr | 1.792 yr |
| `geo` | 98.07 / 1.93 | 16.98 / 83.02 | 1.375 yr | 2.277 yr |
| **`mars_orbit`** | **99.93 / 0.07** | 34.70 / 65.30 | **3.742 yr** | **4.497 yr** |
| `leo` | 86.80 / 13.20 | 23.46 / 76.54 | 1.369 yr | 2.860 yr |
| **`mars_surface`** | **99.93 / 0.07** | **46.24 / 53.76** | **3.798 yr** | **4.228 yr** |
| `earth_surface` | 86.45 / 13.55 | 16.96 / 83.04 | 1.368 yr | 3.326 yr |

🚨  **THE MARS EXCEPTION IS GONE, AND IT IS THE MOST REUSABLE THING IN THIS
RE-DERIVATION.** This file said, of the beneficiated inversion: *"`mars_surface`
is the exception that proves the mechanism: its window is so long (99.95%
binding on raw, still 63.18% beneficiated) that even concentrating cannot make
the dig the slower half."* Beneficiated `mars_surface` is now **46.24 / 53.76**,
so the dig IS the slower half, and **the inversion is universal: all seven
destinations are window-bound raw (86.45 to 99.93%) and dig-bound beneficiated
(53.76 to 83.04%)**. A claim whose whole rhetorical shape was "the one
exception" turned out to be a claim about a market term, and closing it took no
change to the launch-window model at all.

🚨  **`mars_orbit` IS THE SECOND CALENDAR-BOUND DESTINATION, AND IT INVERTS
WHERE NOTHING ELSE DOES: ON RAW ORE AT N = 1.** Its calendar bound retires
**39.37%** of rigs on the raw single-mission cell, against 1.20 to 4.08%
everywhere except `mars_surface`, which manages 19.63%. So a depot in Mars orbit
is *twice* as calendar-bound on raw ore as the surface below it, and both Mars
destinations run 74 to 82% calendar beneficiated. The cause is in the cadence
column and it is the same one: a Mars campaign repeats every **3.7 to 4.5
years** against ~1.37 for everywhere else, because the Earth/Mars synodic period
is 2.14 yr and the transfer is a separate heliocentric leg.

⚠️  **So "the cycle bound is what retires almost every rig" is now wrong three
ways, not two.** It fails on beneficiated `cislunar` (42.49% calendar), it fails
at `mars_surface` (81.66%), and it fails at `mars_orbit` (78.13%), which did not
exist as a destination when the claim was written. It survives only as a
statement about **raw** ore at the five non-Mars destinations.

**Programme structure**, searched cells only. `W < trips` is meaningless without
the search on, because at N = 1, W = 1 and `trips` is 2-5, so those cells report
~100% trivially:

| destination | W < trips raw | W < trips benef | fleet med raw/benef | N med raw/benef | span raw/benef |
|---|---|---|---|---|---|
| `cislunar` | 20.86% | 22.14% | 3 / 6 | 12 / 30 | 11.4 / 13.8 yr |
| `lunar_surface` | 16.07% | 18.23% | **26** / 6 | **130** / 25 | 12.3 / 13.2 yr |
| `geo` | 12.97% | 18.15% | 1 / 3 | 5 / 12 | 11.1 / 14.1 yr |
| `mars_orbit` | **35.99%** | 18.44% | 2 / 6 | 10 / 20 | **19.4** / 17.5 yr |
| `leo` | 8.09% | 9.22% | 12 / **34** | 60 / **130** | 10.7 / 14.2 yr |
| `mars_surface` | 32.73% | **23.59%** | 12 / 3 | 60 / 12 | **20.1** / 17.6 yr |
| `earth_surface` | 0.27% | 0.33% | **64 / 64** | **320 / 320** | 10.7 / 16.5 yr |

⚠️  **`W > trips` is zero on every row of all fourteen searched cells**, which
is an invariant rather than a measurement, and it holds.

⚠️  **A FLEET MEDIAN IS NOT A PROPERTY OF A DESTINATION, AND THE TWO
BENEFICIATION COLUMNS PROVE IT BY DISAGREEING ABOUT THE DIRECTION.**
Concentrating *raises* the chosen fleet at `leo` (12 to 34), `geo` (1 to 3) and
`cislunar` (3 to 6), and *lowers* it at `lunar_surface` (26 to 6) and
`mars_surface` (12 to 3). Quoting one of these as "the model's fleet size" is
the same error as quoting a propellant share without its configuration, and
`earth_surface` is the reminder of what a pinned column looks like: 64 and 320
are the ladder's top rung, not a choice.

⚠️  **This is where README's "a median searched fleet of 2" came from, and it
was a 2026-08 figure standing in a 2026-09 argument.** The raw cislunar searched
median is **3**; the 6 quoted in the campaign's own invariants block is the
BENEFICIATED cell. Both are right about different cells, which is exactly why
the cell has to be named. Corrected in README on 2026-09-14.

**Programme span** follows the cadence, and the searched cells run long
everywhere: median 10.7 yr (`earth_surface`, `leo` raw) to **20.1 yr**
(`mars_surface` raw), and 13.2-17.6 yr beneficiated. Both Mars destinations are
**two-decade** commitments on raw ore, and `mars_orbit` at 19.4 yr is within a
year of the surface.

### Propellant and vehicle shares, all twenty-eight cells (2026-09)

✅  **RE-DERIVED 2026-09-14 BY `campaign/population.py`**, off the archived
cells, so these are `capacity_cap` with insurance OFF and include the two
destinations that had never had a share table at all. ⚠️  **calc `1.21.2`, not
a default run today**; see the banner on the 28-cell section for the four flags
`1.22.0` moved. The superseded 2026-08
`elasticity` shares are in
[the 28-cell campaign](versions.md#the-28-cell-campaign-2026-09).

**Propellant, % of evaluable rows.** Columns are raw N=1 / raw ON / benef N=1 /
benef ON; anything under 0.20% in all four is dropped:

| | raw N=1 | raw ON | benef N=1 | benef ON |
|---|---|---|---|---|
| **`cislunar`** | | | | |
| xenon | 43.93 | 40.18 | 60.61 | **38.99** |
| iodine | 23.97 | 26.21 | 15.90 | **36.24** |
| water ion | 15.53 | 17.78 | 12.55 | 13.94 |
| hydrolox | 8.17 | 5.94 | 10.31 | 9.65 |
| krypton | 8.01 | 9.30 | 0.42 | 0.50 |
| **`lunar_surface`** | | | | |
| xenon | 42.89 | 37.64 | 52.30 | **34.05** |
| krypton | 22.59 | 26.31 | 3.28 | 10.31 |
| water ion | 20.57 | 20.86 | 19.48 | 19.80 |
| iodine | 9.73 | 11.16 | 22.57 | **33.23** |
| hydrolox | 3.87 | 3.59 | 2.08 | 2.23 |
| **`geo`** | | | | |
| xenon | 72.88 | 68.07 | 67.57 | **40.46** |
| iodine | 14.90 | 19.50 | 21.34 | **47.79** |
| water ion | 6.67 | 6.50 | 4.45 | 4.32 |
| hydrolox | 3.18 | 3.38 | 5.13 | 5.65 |
| krypton | 1.70 | 1.84 | 0.23 | 0.27 |
| **`mars_orbit`** | | | | |
| xenon | 83.73 | 76.20 | 77.02 | 46.71 |
| iodine | 12.63 | 19.73 | 8.09 | 37.81 |
| **methalox** | 1.76 | 1.78 | **14.55** | **14.48** |
| hydrolox | 1.07 | 1.09 | 0.17 | 0.26 |
| MMH/NTO | 0.32 | 0.32 | - | - |
| **`leo`** | | | | |
| xenon | 76.28 | 69.26 | 75.21 | **40.65** |
| iodine | 13.32 | 16.35 | 11.41 | **44.41** |
| krypton | 4.36 | 5.20 | 0.10 | 0.26 |
| **methalox** | 1.76 | 1.90 | **11.07** | **11.38** |
| hydrolox | 1.95 | 2.13 | 1.18 | 1.55 |
| argon | 0.94 | 3.63 | 0.01 | 0.13 |
| FEEP | 0.62 | 0.69 | 0.42 | 0.44 |
| **`mars_surface`** | | | | |
| xenon | 61.03 | 47.99 | 72.78 | 51.21 |
| iodine | 16.78 | 29.49 | 5.10 | 22.02 |
| krypton | 15.43 | 14.62 | 1.79 | 1.46 |
| **methalox** | 1.60 | 1.61 | **15.22** | **15.15** |
| argon | 1.70 | 2.81 | 2.77 | 5.98 |
| hydrolox | 2.05 | 2.06 | 0.68 | 0.78 |
| water ion | 0.83 | 0.84 | 1.52 | 3.26 |
| **`earth_surface`** | | | | |
| xenon | 74.77 | 71.13 | 63.71 | **34.43** |
| iodine | 13.34 | 16.30 | 20.35 | **48.33** |
| krypton | 5.48 | 5.69 | 0.95 | 1.36 |
| **methalox** | 1.73 | 1.77 | **12.26** | **12.46** |
| hydrolox | 1.92 | 2.02 | 0.20 | 0.37 |
| argon | 1.39 | 1.60 | 0.16 | 0.34 |
| FEEP | 0.71 | 0.79 | 0.50 | 0.44 |

🚨  **IODINE NOW WINS THREE BENEFICIATED SEARCHED CELLS OUTRIGHT, AND THE TWO IT
LOSES IT LOSES BY UNDER THREE POINTS.** It takes `earth_surface` (48.33 against
xenon's 34.43), `geo` (47.79 against 40.46) and `leo` (44.41 against 40.65), and
at `cislunar` (36.24 against 38.99) and `lunar_surface` (33.23 against 34.05) it
is within 2.75 and 0.82 points of the lead. In 2026-08 it took two cells. The
mechanism is the one the programme-scale curve predicted long before there was a
population to check it on: iodine takes over at scale.

⚠️  **Every propellant-share claim in this file remains a statement about a
configuration rather than about the model**, and this table is the proof: xenon
runs 43.93% of `cislunar` raw single missions and 38.99% of its beneficiated
programmes, and iodine goes 23.97% to 36.24% on the same rock population.

🚨  **THE CISLUNAR WINNER FLIES A PROPELLANT 0.12% OF ITS OWN POPULATION USES.**
The best beneficiated cislunar programme is 2021 CX5 on **argon**, at 6.6622x,
and argon is 0.12% of that cell's rows. This is
[a diagnostic describes the WINNER](#a-diagnostic-describes-the-winner-not-the-search-that-produced-it)
arriving in the share tables: a headline architecture can sit in the tail of
every distribution the same run reports, so **a share table is not a sanity
check on a winner and must never be read as one.**

⚠️  **Chemical propulsion holds 11-15% of FOUR destinations now, not three.**
`methalox` goes 1.6-1.8% raw to **11.07-15.22%** beneficiated at `mars_orbit`,
`mars_surface`, `leo` and `earth_surface`. `mars_orbit` is the new one, and it
arrives at the level the other three already sat at. The mechanism is unchanged:
beneficiation drives mass ratio up, which is where v1.11.0's tank term bites,
and methalox stores at 0.83 kg/L against xenon's COPV, so it is the propellant
that *gains* when the tank starts to matter. Krypton moves the opposite way for
the same reason (12.5% tankage): 22.59% to 3.28% at `lunar_surface`, 15.43% to
1.79% at `mars_surface`, 4.36% to 0.10% at `leo`.

🚨  **"ISRU TRACKS HYDROLOX TO WITHIN 0.03 pp AT EVERY DESTINATION" IS RETIRED,
AND IT WAS A FIVE-DESTINATION CLAIM MEASURED ON FIVE DESTINATIONS.** It still
holds at `cislunar` (0.0014 to 0.0068 pp), `lunar_surface` (0.0000 to 0.0015),
`geo` (0.0009 to 0.0250) and `mars_surface` (0.0003 to 0.0133). It fails at
three:

| destination | worst gap | which way |
|---|---|---|
| `earth_surface` benef ON | **+0.3668 pp** | hydrolox exceeds ISRU |
| `leo` benef ON | **+0.2885 pp** | hydrolox exceeds ISRU |
| `mars_orbit` raw N=1 | **-0.0630 pp** | ISRU exceeds hydrolox |

✅  **The residual still runs both ways, exactly as this file already said, but
the sharpest case is new and is a mechanism rather than a rounding.** At
`earth_surface` **beneficiated**, ISRU is 0.0005% and 0.0044% of rows while
hydrolox is 0.2012% and 0.3711%: ISRU essentially *vanishes* while hydrolox
does not, so nearly every hydrolox mission delivering concentrate to Earth
**buys its propellant on Earth rather than making it**. The near-equality was
never a law; it was hydrolox being the ISRU route the search usually takes, and
at one destination and one setting it stops taking it.

**Launch vehicle, % of evaluable rows.** Same column order; under 0.30% in all
four is dropped:

| | raw N=1 | raw ON | benef N=1 | benef ON |
|---|---|---|---|---|
| **`cislunar`** | | | | |
| Falcon Heavy | 65.47 | 58.09 | 66.39 | 40.02 |
| SLS Block 1B | 32.62 | 25.67 | 30.92 | 24.75 |
| **New Glenn** | 1.62 | 15.77 | 2.41 | **32.53** |
| **`lunar_surface`** | | | | |
| Falcon Heavy | 67.57 | 71.65 | 51.97 | 52.71 |
| SLS Block 1B | 31.45 | 26.02 | 38.07 | 24.10 |
| **New Glenn** | 0.57 | 1.93 | 7.70 | **17.01** |
| Vulcan VC6 | 0.19 | 0.19 | 0.86 | 2.80 |
| Long March 5 | 0.02 | 0.04 | 0.39 | 1.58 |
| **`geo`** | | | | |
| Falcon Heavy | 78.80 | **44.40** | 71.44 | 67.44 |
| SLS Block 1B | 18.02 | 16.22 | 22.68 | 19.47 |
| **New Glenn** | 2.96 | **39.06** | 4.97 | 10.66 |
| **`mars_orbit`** | | | | |
| Falcon Heavy | 77.94 | 77.25 | 59.76 | 53.37 |
| SLS Block 1B | 16.03 | 9.05 | 28.48 | 24.20 |
| **New Glenn** | 4.92 | 11.68 | 11.52 | **21.62** |
| Vulcan VC6 | 0.72 | 1.48 | 0.11 | 0.49 |
| **`leo`** | | | | |
| Falcon Heavy | 67.39 | 75.01 | 62.56 | 60.73 |
| SLS Block 1B | 23.54 | 14.67 | 28.74 | 20.04 |
| New Glenn | 8.75 | 9.97 | 8.18 | 15.28 |
| Vulcan VC6 | 0.24 | 0.19 | 0.41 | 2.85 |
| **`mars_surface`** | | | | |
| Falcon Heavy | 77.52 | 80.50 | 57.98 | 46.08 |
| SLS Block 1B | 14.63 | 9.96 | 23.75 | 23.27 |
| **New Glenn** | 5.12 | 5.72 | 16.96 | **27.57** |
| Vulcan VC6 | 1.77 | 2.76 | 0.44 | 1.57 |
| Ariane 6 | 0.41 | 0.51 | 0.21 | 0.36 |
| **`earth_surface`** | | | | |
| Falcon Heavy | 66.21 | 71.56 | 37.73 | 46.60 |
| SLS Block 1B | 23.62 | 18.14 | 20.71 | 18.98 |
| **New Glenn** | 9.85 | 10.07 | **29.92** | 25.80 |
| Ariane 6 | 0.01 | 0.03 | 2.72 | 1.59 |
| Vulcan VC6 | 0.25 | 0.10 | 2.66 | 1.93 |
| Falcon 9 | 0.00 | 0.04 | 2.03 | 1.37 |
| Long March 5 | 0.02 | 0.02 | 1.71 | 0.92 |
| H3 (24L) | 0.02 | 0.03 | 1.67 | 1.90 |

✅  **New Glenn's rise is the saturation mechanism, and it is now visible at all
seven destinations at once.** It is a *smaller* vehicle than Falcon Heavy (45 t
against 57 t), and it goes 1.62 to 32.53% at `cislunar`, 0.57 to 17.01% at
`lunar_surface`, 5.12 to 27.57% at `mars_surface`, 4.92 to 21.62% at
`mars_orbit`. A ceiling punishes volume, so at programme scale the model prefers
**more, smaller missions**, which is the same thing the winner's payload does.

🚨  **`geo` MOVES ON THE SEARCH AXIS INSTEAD, AND IT IS THE ONLY DESTINATION
THAT DOES.** New Glenn goes 2.96% to **39.06%** between raw N=1 and raw
SEARCHED, with Falcon Heavy falling 78.80% to 44.40%, while the beneficiation
axis barely moves it (4.97 to 10.66%). Everywhere else the flip is driven by
concentrating. `geo` is the model's smallest in-space market at 40 t/yr, so its
ceiling binds on programme size alone and does not need a denser payload to do
it. **Which axis a share moves on is itself a measurement**, and reading these
tables only down the beneficiation column would have missed this one entirely.

⚠️  **`earth_surface` beneficiated carries the most diverse fleet in the
campaign**, with eight vehicles above 0.3% including Ariane 6, Falcon 9, Long
March 5 and H3. Everywhere else three vehicles take 95%+. A market that never
saturates does not push the search toward any particular size, so the choice is
made on price alone and far more of the grid is competitive.

⚠️  `mars_surface` remains the outlier the 2026-08 matrix describes, with the
least SLS (14.63% against 16-32% elsewhere) and the most Vulcan, because a Mars
delivery pays no Earth capture, so its stacks are lighter and a mid-class
vehicle closes missions that need SLS anywhere else.

### Winners, and what 28 cells did to the claim

✅  **RE-DERIVED IN 2026-09, and the sweep is gone.** **2021 CX5 takes 8 of the
28 cells and 2018 DT 6**, but neither sweeps a destination the way 2021 CX5
swept two of them in 2026-08. Only `earth_surface` still has one winner across
all four cells (**2016 PN38**); `mars_surface` and `mars_orbit` change winner on
three of four axes.

| destination | raw N=1 | raw searched | benef N=1 | benef searched |
|---|---|---|---|---|
| `cislunar` | 2018 DT | 2014 WE121 | 2014 WE121 | 2021 CX5 |
| `mars_orbit` | 2018 DT | 2018 DT | 2015 BM510 | 2006 YF |
| `geo` | 2016 GS2 | 2021 CX5 | 2021 CX5 | 2021 CX5 |
| `lunar_surface` | 2018 DT | 2014 WE121 | 2018 DT | 2021 CX5 |
| `mars_surface` | 2014 YN | 2014 YN | 9992 | 2003 RS1 |
| `leo` | 2018 DT | 2021 CX5 | 2021 CX5 | 2021 CX5 |
| `earth_surface` | 2016 PN38 | 2016 PN38 | 2016 PN38 | 2016 PN38 |

⚠️  **"2021 CX5 takes 10 of the 20 cells" is retired as a claim about the
model**; it was a claim about `elasticity` with insurance charged. The body is
still the commonest winner, and it now wins only where the levers are doing the
most work.

✅  **`leo` reproduced its structural signature exactly**, the one destination
where the best single mission and the best programme are different bodies:
2018 DT at N = 1 becoming 2021 CX5 searched, in both campaigns.

⚠️  Everything below is the 2026-08 statement of this section, kept for the
per-destination detail that has not been re-derived.

#### The 2026-08 winners (superseded)

**2021 CX5 (D) takes 10 of the 20 cells**: all four at `cislunar`, all four at
`lunar_surface`, and two at `leo`. One body winning eight of eight across two
destinations, on all four settings, is a far stronger statement about that
target than any single ratio. **2016 PN38 (M)** takes all four `earth_surface`
cells.

`mars_surface` is the only destination whose winner moves on every axis: 8651
(M) at N = 1, **2014 YN (M)** on both searched settings, and **2001 UU92 (T)**
beneficiated at N = 1, which is the **first T-type winner anywhere in this
project's record**.

⚠️  **`leo` is where the best single mission and the best programme are
DIFFERENT BODIES**: 2018 DT (M) on xenon at N = 1 becomes **2021 CX5 (D) on
hydrolox** at N = 20. That is the argument for searching N *jointly* rather
than at a pivot; this file has always made it about architecture, and here it
changes the **target**.

**Aerocapture and ISRU, % of evaluable rows**, re-derived 2026-09-14 across all
seven destinations. Each cell is aerocapture / ISRU:

| destination | raw N=1 | raw ON | benef N=1 | benef ON |
|---|---|---|---|---|
| `cislunar` | **0.00** / 8.17 | **0.00** / 5.94 | **0.00** / 10.31 | **0.00** / 9.65 |
| `lunar_surface` | **0.00** / 3.87 | **0.00** / 3.59 | **0.00** / 2.08 | **0.00** / 2.23 |
| `geo` | 90.70 / 3.18 | 92.57 / 3.39 | **78.66** / 5.13 | 93.64 / 5.63 |
| **`mars_orbit`** | **40.71** / 1.14 | **37.69** / 1.14 | **50.54** / 0.18 | **49.95** / 0.27 |
| `leo` | 95.03 / 1.93 | 90.10 / 1.96 | 97.41 / 1.11 | 98.36 / 1.26 |
| `mars_surface` | 82.24 / 2.06 | 83.14 / 2.07 | 86.14 / 0.68 | 90.00 / 0.78 |
| `earth_surface` | 95.79 / 1.89 | 91.83 / 1.91 | 96.44 / **0.00** | 97.45 / **0.00** |

✅  **The airless half holds exactly: 0.00% at `cislunar` and `lunar_surface` in
all four cells.** Nobody asserts it, the airless destinations ignore the flag and
the search declines it, which is the physics resolving itself per destination
rather than a switch being set.

🚨  **"82-98% ELSEWHERE" IS RETIRED, AND `mars_orbit` IS WHY.** The real range is
**37.69 to 98.36%**, because a Mars-orbit depot declines aerocapture about half
the time: 37.69-50.54% against 78-98% at every other atmospheric destination. It
is the only destination in the model where the choice is close to even, and that
is the v1.10.0 design working. Aerocapture is priced per asteroid against the
propulsive return, and arriving at a **1-sol orbit** rather than a surface means
the Delta-v saved is small while the heat shield still has to be hauled out and
pushed back, so on a slow-arriving target it does not pay.

🚨  **"RISING UNDER BENEFICIATION AT EVERY ATMOSPHERIC DESTINATION" IS RETIRED
TOO, BY ONE CELL.** `geo` **falls** from 90.70% to 78.66% at N = 1, where the
other four rise. It recovers to 93.64% once the search is on, so the exception is
specific to the single-mission beneficiated cell, which is exactly the kind of
qualification a five-destination claim could not carry.

**ISRU still tracks hydrolox closely at four destinations and no longer at
three.** It holds at `cislunar` (0.0014 to 0.0068 pp), `lunar_surface` (0.0000
to 0.0015), `geo` (0.0009 to 0.0250) and `mars_surface` (0.0003 to 0.0133), and
fails at `earth_surface` (**+0.3668 pp**), `leo` (+0.2885) and `mars_orbit`
(-0.0630). The near-equality was never a law; it is hydrolox being the ISRU route
the search usually takes, and the residual runs both ways, as this file already
said.

🚨  **`earth_surface` BENEFICIATED MAKES NO PROPELLANT AT ALL: ISRU IS 0.0005%
AND 0.0044% OF ROWS**, against a hydrolox share of 0.2012% and 0.3711%. So
nearly every hydrolox mission delivering concentrate to Earth **buys its
propellant on Earth rather than making it**, which is the sharpest single
statement of the residual's mechanism the project has, and it only became
visible once the shares were kept in full rather than truncated to the
commonest few.

⚠️  **The water-ion share is still not where to look for the residual**:
`cislunar` runs 15.53% water ion against 8.17% ISRU, so most water-propelled
missions are carrying their water up from Earth.

### Programme structure on the full population (2026-08; see the 28-cell invariants above)

⚠️  **The 2026-09 figures are in the invariants block above and they moved a
long way**: `W < trips` went 0.319% to **20.86%** at cislunar raw searched, the
fleet median 2 to 6 and the N median 10 to 30. What is below is the 2026-08
`elasticity` population, kept because its *invariant* statements are the ones
the checks were built from.

The tables above are the current 20-cell campaign. The **cislunar 2x2** that
preceded it (calc `1.16.0`, 2026-08-11) was the first time both flags were
measured together on a full catalog, and all four of its model values reproduce
exactly in the campaign above; its cells, its winner and its superseded runtime
ratios are in
[the full cislunar 2x2](versions.md#the-full-cislunar-2x2-calc-v1160-2026-08-11).
What is kept here is the population detail that is an **invariant to re-check**
rather than a number to quote.

Every structural invariant `1.15.0` and `1.16.0` assert, on the full cislunar
population:

| | raw + search | benef + search |
|---|---|---|
| N = F × W on every row | ✅ | ✅ |
| W > `trips` ever | never | never |
| **W < `trips`** | **2,077 (0.319%)** | **1,389 (0.210%)** |
| fleet median / max | 2 / 64 | 2 / 64 |
| at `max_fleet_ships` | 2,383 (0.37%) | 2,610 (0.40%) |
| N median / max | 10 / 320 | 10 / 320 |
| calendar multiplier median / max | 1.3236 / 3.4551 | 1.4832 / 2.8409 |
| programme span median | 11.49 yr | 14.84 yr |
| programmes priced per mission | 40 | 40 |

🚨  **`W < trips` on 2,077 rows is what retires `1.16.0`'s own conclusion that
"the 2-D search is necessary but not yet load-bearing here".** That was read
off 168 sampled rows where W came out at the band top every time. On the real
population 2,077 bodies decline to use up the rig, because the calendar charge
outweighs what another campaign buys. **A sample is a good estimator of the
middle of this distribution and a bad one of its edge**: the medians held to
three decimals while the maxima did not (calendar multiplier 3.4551 against the
sample's 2.093, span 34.34 yr against 25.3).

Never-worse on the same population, all four pairings:

```
search ON vs OFF, raw           pairs 650,921 | max 1.000000 | worse 0 | median +42.4%
search ON vs OFF, beneficiated  pairs 660,253 | max 0.996770 | worse 0 | median +38.2%
beneficiated vs raw, search OFF pairs 650,921 | max 1.000000 | worse 0 | declined 102,765
beneficiated vs raw, search ON  pairs 650,921 | max 1.000000 | worse 0 | declined 102,427
```

The two declined counts are **15.79%** and **15.73%** of bodies refusing to
concentrate, against the committed 15.8%.

⚠️  **Two rows are unchanged on the RAW search axis and none on the
beneficiated one, which looks backwards and is not.** An unchanged row is a
body whose calendar cap is a single trip, so N = 1 is the only programme on its
ladder; beneficiation *lengthens* the stay, so it should produce more of them,
not fewer. It produces none because those two bodies are not in the
beneficiated evaluable set at all. **Do not read the 0 as a stronger result
than the 2.**

## When a number changes, grep the prose too

The recurring documentation failure here is not a missing table; it is a
stale sentence. A commit that measures something naturally rewrites the table
it measured, and leaves every summary paragraph that quoted the old figure
standing. An August 2026 audit found four releases' worth of rot in
committed-clean files: CLAUDE.md still called cislunar the best case at 51×
when Mars had been the best case at 34× for three commits; both files said
"nine" models in a section listing ten; the README asserted Mars "lands
within a factor of ~14" immediately above its own table reading 34×.

That matters more here than in most repos, because these files exist to stop
someone "fixing" a result that only looks wrong. A stale headline invites
exactly that.

✅  **The checkable part is mechanical now, and is committed as
`verify_docs.py`.** It takes about a second and needs no baseline; the checks
are listed in [README.md](README.md#verifying-the-docs), and they cover
documented defaults, `pipeline_version` stamps, reference-table row counts,
anchors, document structure, the em-dash ratchet, two cross-file manifests
(`requirements.txt` against `_MASTER_REQUIRED`, README's option list against
`run.bat`'s dispatcher) and, with `--before`, whether a reorganisation dropped
a measurement. Run it after touching any config field or reference table.

✅  **The counts in this table are checked mechanically now, as of 2026-09.**
They are the ones that are DERIVED rather than typed, which is why nobody
thinks of them as measurements. ⚠️  **The row count is deliberately not stated
here**: this paragraph opened "Three of these" above four rows until 2026-09,
which is this section's own failure mode occurring in the section that names
it.

| what | why it rots | where |
|---|---|---|
| the size of the two "moved without moving a number" tables, against the count spelled beside each | a release that says "No number" has to be added by hand, and `1.17.8` was not | check 2 |
| **21** usable propellants and **17** operational vehicles, the search GRID rather than a table length | a one-word edit to a row's `status` moves both, in README *and* in three `modules/calc.py` comments | check 3 |
| whether `campaign/` obeys the em-dash ratchet and the structure rules at all | it did not, for the whole 20-cell campaign | checks 5, 6 |
| whether every module, class and function carries a docstring | 87 carried neither that nor a leading comment, most of them in `ui.py` and `launch_ui.py` | check 11 |
| whether a measurement is quoted in BOTH this file and README off the register below | the register is maintained by hand, and it had missed the project's four headline numbers since it was written | check 12 |

⚠️  **It cannot see a stale measurement.** A number that is merely out of date
passes everything in it, which is why the rest of this section is still a
manual discipline. ⚠️  Check 12 is the nearest thing to an exception and is not
one: it can see that two current-claiming files quote one number, never that
the number is still true.

🚨  **AND IT CANNOT SEE THE COPIES THAT LIVE IN CODE.** The docs are not the
only place a measurement is quoted: **`--help` text, run banners, config
comments and harness comments all quote runtime ratios**, and none of it is a
dataclass default, so check 1 cannot reach it. The 2026-08-25 pass found the
superseded `1.16.0` ratios (beneficiation "~7x", the programme search "~3x")
still being **printed to the user on every run**, in five files at once:

| file | where |
|---|---|
| `run_pipeline.py` | `--help` for `--raw` and `--search`, and the `[default: ...]` run banner |
| `build_master.py` | the `MASTER CONFIG READY` banner, which is a `MASTER_ORCHESTRATOR` template, so it is in `master.py` too |
| `modules/calc.py` | the `use_beneficiation` and `optimise_programme_scale` config comments, and the release notes that were then still in the module |
| `verify.py` | the comment explaining why beneficiated cells run at a lower row cap |
| `README.md` | a quoted example of the run banner |

They are **4.67×** and **1.71×** on `1.17.7`. A banner is the *most* read copy
of a number in this project and was the least checked.

✅  **THAT CLASS IS CLOSED NOW: THE RATIOS ARE DERIVED, NOT TYPED.**
`modules/calc.py` holds `MEASURED_CELL_SECONDS`, the four measured cislunar
wall clocks, plus `beneficiation_cost_ratio()` and
`programme_search_cost_ratio()`. Every consumer computes from it:

| consumer | what it derives |
|---|---|
| `run_pipeline.py` | `--help` for `--raw` and `--search`, and both `[default: ...]` banner labels |
| `build_master.py` | the `MASTER CONFIG READY` banner, so `master.py` too |
| `modules/calc.py` | its own Stage 4 preview banner |
| `ui.py` | `_SECONDS_PER_ROW`, which was a second copy of the same four numbers, **and since 2026-09-14 the Stage 4 sidebar blurb as well** |

**Re-measure in one place and every printed ratio moves with it**, and because
the ratio is computed per configuration the banner says **5.24× at N = 1 and
3.42× with the search on**, which the single hand-typed figure could not.
✅  **Both moved on their own when `MEASURED_CELL_SECONDS` was re-measured for
the 28-cell campaign**, from 4.67× and 4.54×, and so did the `--search` help
text (1.71× to 3.05×). That is the mechanism working: nobody edited a banner.

🚨  **AND THE CLAIM ABOVE WAS FALSE WHEN IT WAS WRITTEN, IN THE ROW IT NAMES.**
`ui.py` derived `_SECONDS_PER_ROW` from the constant and **hand-typed the same
four wall clocks four hundred lines away**, in the Stage 4 sidebar blurb. When
the constant was re-measured for the 28-cell campaign the derived half moved
and the typed half did not, so the dashboard spent the next release telling
users to **budget 1.6 h for a cell that measures 2.7 h** -- and the blurb
attributed its figures to calc 1.17.7, which was honest and therefore made the
staleness invisible. Found 2026-09-14 by converting the blurb to derive; the
numbers changed under the edit, which is how a silent second copy announces
itself.

⚠️  **The lesson is narrower than "derive everything" and worth stating
exactly: a file that derives a number in one place is not a file that derives
it.** The audit that closed this class went looking for files that typed the
ratios and found five; it did not go looking for a SECOND copy inside a file
already on the fixed list, because that file was on the fixed list. **Grep for
the VALUE, not for the filename.** ⚠️  One typed copy is left on purpose, the
cislunar-to-dearest factor in `_DEST_FACTOR`, because it is a ratio of two
numbers that live in a markdown table rather than in code; it is labelled, and
it too had gone stale (2.1-2.7x against the 28-cell matrix's 2.2-3.0x).

⚠️  **`run_pipeline.py` deliberately asserts rather than falling back to a
literal** if master is somehow not loaded when the parser is built. A
hand-typed default there would be a sixth copy of a number this project has
already shipped stale once.

✅  **`verify_docs.py` check 9 pins the constant to the docs**, comparing
README's cislunar wall-clock row against `MEASURED_CELL_SECONDS` in both
directions, so prose cannot drift from the code either. What is left to do by
hand after a re-measurement is the *prose* elsewhere: this file and
`versions.md` quote ratios as text, and check 9 does not read them. ⚠️  The
2026-09 re-measurement caught exactly that -- README said 5.25× where the code
derives 5.24×, a rounding slip in prose that no check can see. Comments and console text are not output, so none of this moves a
`pipeline_version`; it does move `master.py`, which must be rebuilt and
committed with it.

🚨  **This paragraph used to open "Three of these are mechanical now" and then
describe four, against a file that had seven.** It is left corrected rather
than quietly rewritten because it is this section's own failure mode, a **count
spelled out in prose**, occurring in the section that names that failure mode.
That is the third time a count has rotted in this file. **Name the list; do not
state its length.**

So after changing any number, search for the superseded **claim**, not just
the digits: "best case", "still comes in", counts spelled out in prose and
headings, and the name of whichever destination used to win. Check that
summary paragraphs still agree with the tables below them in the same file.

⚠️  **AND CHECK THE OTHER FILE, BECAUSE THIS ONE RESTATES README HEADLINES
BEFORE ADDING DEPTH TO THEM.** The rule at the top of the 20-cell section says
the result highlights "are in README.md, and are not copied here". They partly
are, and the surviving pairs were found by hunting sentences that share three
or more distinctive numbers across two files:

| the shared measurement | in README under | here under |
|---|---|---|
| the winners: 2021 CX5 taking **8 of 28** cells and 2018 DT 6, 2016 PN38 sweeping `earth_surface` | [Current results](README.md#current-results-the-complete-28-cell-matrix) | "Winners, and what 28 cells did to the claim" |
| the lunar staging figures: 5,920 m/s, and 10.96 against 4.99 kg in LEO per kg landed | [What a kilogram is worth](README.md#what-a-kilogram-is-worth) | "Model assumptions that are load-bearing" (and again in `versions.md`, mineral_value `1.4.0`) |
| the `replicated` win: 13.4% clear, 6,667 kg of thruster for 96.7 kW | [Current results](README.md#current-results-the-complete-28-cell-matrix) | "RETIRED TWICE: a `replicated` device wins TWO cells now" |
| the Mars cadence, **3.7-4.5 yr** against ~1.37 everywhere else, now covering BOTH Mars destinations | [Current results](README.md#current-results-the-complete-28-cell-matrix) | "The rig's two bounds, and the cadence, at every destination (2026-09)" |
| everything older than `1.17.7` being high by 1.78-4.32x | [Current results](README.md#current-results-the-complete-28-cell-matrix) | "Runtime, and the three quantities a sample cannot predict" |
| the four cislunar wall clocks, 733 / 1,253 / 3,424 / 5,692 s | [Beneficiation](README.md#beneficiation) | "Runtime, and the three quantities a sample cannot predict" |
| why `mars_orbit` takes the BASE utility profile: the crust is 4,100 m/s of ascent away, against the 3,600 m/s of TMI that delivered the cargo | [What a kilogram is worth](README.md#what-a-kilogram-is-worth) | "Model assumptions that are load-bearing" |
| the base in-space utility profile itself: water 1.00, structural metals 0.70, silicates 0.25, carbon 0.40, and the Mars overrides against it | [What a kilogram is worth](README.md#what-a-kilogram-is-worth) | "Model assumptions that are load-bearing" |
| the insurance premiums: 2.4-4.3% of total cost against 5.5-9.6% of the answer, and liability alone at 0.03-0.05% | [What the model deliberately does not charge for](README.md#what-the-model-deliberately-does-not-charge-for) | "The corrections the model accumulated" |
| the median raw cislunar cadence, **1.384 yr**, used to argue the ceilings bind where the results actually sit | [What the model charges for](README.md#what-the-model-charges-for) | "The rig's two bounds, and the cadence, at every destination (2026-09)"; the cadence reproduces unchanged, the fleet median beside it did not |
| the in-space absorption ceilings: LEO **500 t/yr**, cislunar 100 t, `geo` 40 t/yr | [What the model charges for](README.md#what-the-model-charges-for) | "Model assumptions that are load-bearing" |
| 🚨  **the four cislunar cell objectives, now 15.3937 / 9.5435 / 14.1071 / 6.6622** -- the project's headline answer, and the pair this register missed for longest | [Current results](README.md#current-results-the-complete-28-cell-matrix), **and again** under [Programme scale](README.md#programme-scale) | the 28-cell matrix section |
| 🚨  **the winner-against-population table: 39.4 / 39.5 / -8.4, 66.1 / 63.8 / -36.5, 77.7 / -6.5** -- the 2026-09 campaign's most reusable finding, and deliberately in both files because README needs the result and this file needs the warning | [The winner moved far more than the population did](README.md#the-winner-moved-far-more-than-the-population-did) | the 28-cell matrix section |
| the 28-cell wall clocks, 947 / 2,888 / 4,967 / 9,878 s at cislunar | [Beneficiation](README.md#beneficiation) | pinned to `MEASURED_CELL_SECONDS` by check 9, not quoted here |

✅  **Re-run on 2026-09-07 for calc `1.21.0`, and it found TWO new pairs,
both created by that release's README section**: the cislunar cadence and the
ceiling table, added there to argue that the ceilings bind at the fleet sizes
the model actually chooses. Both are now rows above. Every other number the
release introduced -- **its own** four cell objectives, the clearing fractions,
the call counts -- landed in `versions.md` and at most one current-claiming
file, which is the split working rather than luck.

🚨  **RE-RUN AGAIN ON 2026-09-08, AND IT FOUND THE PAIR THE REGISTER HAD MISSED
SINCE THE REGISTER WAS WRITTEN: THE PROJECT'S FOUR HEADLINE NUMBERS.**
`26.7863 / 15.4272 / 20.5895 / 13.1443` sit in README's 20-cell matrix, again
in README's Programme scale section, and again in this file's reproduction
table -- **three copies across two files that both claim to be current**, under
a heading that opens by saying the headline matrix "is not copied here". Every
other pair in the table above was found by this same hunt; this one survived
every previous run of it.

⚠️  **The reason it survived is worth more than the row.** The hunt ranks its
hits and a reader skims for something unfamiliar; these four numbers are the
most familiar in the project, so the eye reads them as *the answer* rather than
as a duplicate. **A hunt for copies is defeated by the copy you have
memorised.** Read its output looking for what you recognise, not for what you
do not. The README-internal copy under
[Programme scale](README.md#programme-scale) is a fourth instance, kept
deliberately because the sentence there is an argument about what the search
buys and reads as nothing without the figures, but it is on the row now, so it
moves with the rest.

⚠️  **The hunt itself needs writing ASCII-safe.** The first attempt crashed
with `UnicodeEncodeError: 'charmap' codec can't encode character '\u2192'`
printing a CLAUDE.md line to a redirected stdout: the exact failure the
"console output is ASCII" section exists for, hit by the tool auditing the
documents rather than by the pipeline. Strip or replace non-ASCII before
printing a scraped line.

⚠️  **The last row was added on 2026-09-04 by the change that created it,
the row above it on 2026-09-03, and the six above that on 2026-09-02, each
time by re-running the hunt this table describes**, which is the tell that the
table is a snapshot and not a guarantee: it listed four pairs while nine
existed, the tenth arrived the same day with `mars_orbit`, and the eleventh,
the utility profile, had been sitting in both files the whole time and was
found only by running the hunt again over a destination change that had nothing
to do with it, and the twelfth was the project's four headline numbers, which
had been in both files since the campaign.

✅  **THE HUNT IS `verify_docs.py` CHECK 12 NOW, AND THIS TABLE IS ITS
ALLOWLIST.** You no longer re-run it by hand: a pair that is not on a row above
turns the docs check red, names both lines, and says the two ways to clear it.
That inverts what the table is for. It was a snapshot of what somebody last
looked for; it is now the list of copies the repo has *agreed to keep*, and
anything outside it is a finding.

⚠️  **Add the row when you deliberately keep a copy; do not add one to quiet a
red check you have not read.** The row is a promise to move both, and the whole
value of the register is that somebody decided each entry.

⚠️  **`versions.md` now carries far more of these pairs than this file does,
and that is FINE where this would not be.** The `geo` and `mars_orbit` prices,
plane changes and capture figures all appear in both README and `versions.md`.
That is the split working: `versions.md` is allowed superseded figures because
every section there names the release it belongs to, where this file and README
both claim to be current, which is what makes a pair between THEM a hazard. ⚠️  And note the last row is only half checked:
`verify_docs.py` check 9 pins README's copy of those four wall clocks to
`MEASURED_CELL_SECONDS`, and reads nothing here, so this file's copy can drift
from the code on its own.

**Each pair is a copy, so each pair drifts.** They are kept rather than cut
because this file's job is the reasoning and README's is the answer, and the
reasoning reads badly with the answer removed; but **move both, or neither**.
`grep -rn "<the old number>" --include='*.md' .` finds them, which is why the
rule two paragraphs up is a grep and not a diff. ⚠️  **Use that form rather
than `*.md`**, which expands to the root documents only and so misses
`campaign/`, whose `FINDINGS.md` carries the campaign's wall clock and catalog
size despite saying its findings were promoted out of it, and `research/`,
whose `starred-repos/` audit carries measured Delta-v and taxonomy figures.

🚨  **A MEASUREMENT CAN NOW GO STALE IN MORE PLACES THAN THE ROOT
DOCUMENTS.** The release history moved out of the README into `versions.md` on
2026-08-24, so a measurement can go stale in this file (the working notes),
`README.md` (the current answer) or `versions.md` (what the numbers used to
be), and since 2026-09-03 in `research/starred-repos/` as well. The split is what
makes that tractable; `versions.md` is *allowed* to hold superseded figures,
and every table in it names the release and catalog it belongs to, but it
means `grep -rn "<the old number>" --include='*.md' .` is the check, not a
two-file diff. ⚠️  **Run the find, do not trust a count here**; this sentence
has said "five files" and "three" and both went stale:

```bash
find . -name '*.md' -not -path './.git/*'
```

✅  **Audit a split at FACT level rather than by eye, and do it with
`verify_docs.py --before`.** Pull every distinctive numeric token out of the
old file (anything with a decimal point, a thousands separator, or four-plus
digits) and assert each still appears somewhere in the new ones; that is
check 10, and it exists because a line-level diff reported **302 differences**
on the first split and could not tell a dropped measurement from a reflowed
paragraph. It found **26 measurements dropped rather than moved**: the whole
v1.14.0 and v1.11.0 runtime tables, the `60.9284×` that is the only evidence
behind v1.15.0's "inert at N = 1", the 2,077-row full-catalog correction that
retires v1.16.0's "not yet load-bearing", and the saturation-multiplier column
that *is* the mechanism in v1.14.0's programme-scale curve.

```bash
py verify_docs.py --before OLD.md README.md CLAUDE.md versions.md
```

⚠️  **A reported loss is not automatically a bug, and the check cannot tell the
difference.** When this file's duplicate release history came out, ~210 tokens
went with it, and they were harness ephemera: serial-versus-parallel wall
clocks at a sampled row cap, profiler line dumps, nanosecond microbenchmarks
and per-release sample maxima; measurements of *a harness run*, not of the
model, whose durable form is the sentence "verified bit-identical, zero
exceptions" that `versions.md` carries per release. **Read every reported loss
and decide it deliberately.** The failure this check exists to catch is the one
nobody read.

⚠️  **It also surfaced a contradiction that had been sitting in the README.**
The v1.10.0 programme-scale curve explained its Falcon Heavy → New Glenn switch
as "a bigger vehicle starts paying". New Glenn lifts **45 t** to LEO against
Falcon Heavy's **57 t**, so the switch is to a *smaller* vehicle, and the
v1.14.0 curve a hundred lines below said exactly that, in the same file. The
correct reading is saturation punishing volume. **Two tables in one document
disagreeing about their own shared column is the failure this section is
about**, and it survived because nobody had read them next to each other.

## Model assumptions that are load-bearing

These were found by a realism audit and are easy to silently break again.

**`delivery_destination` must be set in TWO places, and they must agree.**
`MINERAL_CONFIG.delivery_destination` decides what a kilogram sells for;
`CALC_CONFIG.delivery_destination` decides the architecture that puts it
there. Disagreement prices the cargo at a depot while paying to land it in
Utah: Stage 4's `destination_check()` catches it and shouts, and in
`master.py` use `MASTER_CONFIG.delivery_destination`, which writes both.

⚠️  **It shouts on STDOUT, which is where a measurement harness is least likely
to be listening**, and `CALC_CONFIG.delivery_destination` defaults to
`earth_surface` while the on-disk Stage 2 catalog is usually the last
destination somebody ran, `cislunar`, for every measured cell in this file. So
importing `calc` and calling `build_profitability_catalog` straight off gives a
mismatched run, and a harness that pipes the output through `grep` for its own
result lines will filter the warning away and print a clean-looking number.

This was hit while measuring v1.15.0: two figures were recorded as "cislunar"
that were run against `earth_surface` prices, and the paired comparisons they
came from were still valid, both sides saw identical inputs, while the LEVELS
were not. **Set the destination explicitly in any harness**, and if you must
filter stdout, keep `MISMATCH` in the pattern.

✅  **`run_pipeline.py` is the one entry point that cannot hit this**, and it
is worth knowing which one that is rather than assuming the trap is closed.
Its `preflight()` reads the destination Module 2 stamped into the catalog on
disk and **refuses the run**, exit 2, before a stage starts, when Stage 4
would fly somewhere else and Stage 2 is not in `--stages`. That is a refusal,
not a warning, because there is no reading of a mismatched run worth the
minutes it costs. `ui.py`, `verify.py` and a hand-rolled harness are all still
on their own; `verify.py` sets the destination explicitly and asserts
`MISMATCH` is absent from stdout, which is the pattern to copy.

⚠️  It is also why the launcher can offer a destination menu at all.
`run.bat rerun leo` reuses the catalog on disk, which is normally priced for
`cislunar`; one keystroke from a meaningless run, and the refusal is what
makes it safe to put on a menu. **If you add another Stage-4-only entry point,
call `preflight()` from it.**

**And strip EVERY provenance column before hashing two runs.** There are two, 
`pipeline_version` and **`catalog_date`**, and only the first is obvious.
v1.17.3 dropped the version alone, got a MATCH on the raw cells and a DIFFER on
the beneficiated ones, and the whole difference was the date: midnight had
fallen partway through the run. That reads exactly like a defect confined to
the beneficiation path, and it is worth knowing in advance because a full
beneficiated cell is ~10 h, so **a full-catalog 2×2 cannot be run inside one
calendar date.** Any comparison of those cells will hit this.

**Every commodity is priced by destination, not just water** (Stage 2
v1.3.0). At an in-space destination a kilogram is worth its terrestrial price
**plus** `in_space_utility × launch-cost-avoided`, less the cost of refining
it on site. The *plus* is the point, v1.3.0 briefly replaced the terrestrial
price instead of adding to it, which quietly threw the material itself away.
Bulk iron goes from $0.50/kg to ~$2,747/kg in LEO. The in-space prices are
derived through the rocket equation in `delivered_cost_usd_per_kg()`, not
tabulated, but the utility factors are *engineering judgements*, and they
are the softest assumption in the whole pipeline. Treat them as a dial, not a
measurement.

**Utility is per destination, and the correction runs downward** (Stage 2
v1.7.0). One table used to serve every in-space destination, so olivine
captured the same fraction of its freight on the surface of Mars; a planet
made of olivine, as at a depot in empty space. The missing term is not
distance, it is **local competition: the alternative to importing is not
always launching from Earth**. LEO and cislunar have no local resources at any
price and keep the base profile as the calibration anchor;
`IN_SPACE_UTILITY_BY_DESTINATION` discounts the two surfaces against what they
can dig up (Mars water 1.00 → 0.25, carbon 0.40 → 0.02, silicates 0.25 → 0.02;
Moon water → 0.60, iron → 0.45). Ni/Co/Cu are undiscounted everywhere; no
concentrated ore of either body is known. Carbon is undiscounted on the Moon,
where solar-wind implantation leaves it at ~100 ppm.

🚨  **`mars_orbit` TAKES THE BASE PROFILE, AND THE EMPTY DICT IS THE POINT.**
It sits directly above `mars_surface`'s long override block and will read as an
oversight; copying those overrides up into it is the one edit that destroys the
destination's meaning. The overrides exist because a settlement STANDING ON a
crust digs up its own water, iron and rock. A depot in a 1-sol orbit competes
with nothing of the kind: everything martian is 3,400 km down a well costing
4,100 m/s of ascent, **more than the 3,600 m/s of TMI that brought the cargo
from Earth**, so the alternative to importing a kilogram there is launching it
from Earth, which is exactly what the base profile is calibrated on. The ISRU
discount that carries the `mars_surface` result is not a property of Mars; it
is a property of being ON Mars, and this destination is the control that says
so.

Two things not to "fix" here. **Every override runs downward**, deliberately:
raising a utility is precisely how this table becomes a way to manufacture
viability. And **prices still rise with distance**; Mars freight is 10.6
kg-in-LEO per kg delivered and that dominates; they just no longer rise as
fast as the freight does, and the volatiles that carried the Mars result rise
least. Water at Mars is 2.7× its LEO price now against 11× before.

A settlement catalyst market for the PGMs (utility 0.05 at the two surfaces)
was **considered and rejected**, and the reason generalises: this module
prices each commodity with one $/kg and one market depth, and
`in_space_price_usd_per_kg` routes on unit price alone. Gold at a lunar base
would route "used in space" at $76,060/kg into a 25 kg/yr catalyst market,
beating $30,061/kg into a 3,000,000 kg/yr terrestrial one, a
five-order-of-magnitude cliff in market depth that the router cannot see. The
real behaviour is a blend (sell the first few kg in space, fly the rest home)
and the pipeline cannot express a blend. That needs a quantity-aware route
choice, not a bigger table.

**The import budget is split per commodity** (Stage 2 v1.7.0).
`IN_SPACE_ANNUAL_DEMAND_KG` had called itself one shared budget since v1.5.0
while the code handed every commodity the whole thing, a 20 t/yr Mars base
absorbed 20 t of water *and* 20 t of platinum *and* 20 t of olivine.
`_DEMAND_SHARE_BY_CLASS` partitions it (propellant 0.55 / structural 0.25 /
shielding 0.15 / chemical 0.05, asserted to sum to 1.0), and shares are per
*class* because within a class the commodities substitute for each other; 
shielding mass does not care whether it arrives as olivine or pyroxene. Also,
`annual_market_kg` is now **routed**: the market that saturates is the one you
actually sell into, so a commodity flown home is bounded by terrestrial annual
production rather than a depot's import budget. Platinum at LEO was capped at
the depot's 500 t/yr against the world's real 180 t/yr. This is the one part
of v1.7.0 that runs upward, and it is a correction, not a concession.

**Cislunar is cheaper to reach than LEO, and worth more.** This is the one
result that reliably reads as a bug. Capturing into LEO has to kill the
entire arrival hyperbola (~3.6 km/s at v_inf = 3 km/s); capturing into an
NRHO depot only has to *bind* the orbit, and the burn takes the Oberth
benefit at low perigee (~0.94 km/s). See `_cislunar_capture_dv_km_s`. Do not
"fix" it.

**Mars is a separate heliocentric transfer, not a scaled Earth return.**
`_asteroid_to_mars_dv_km_s` terminates the transfer ellipse at 1.524 AU and
captures into Mars' well. Approximating it off the Earth legs would erase the
whole point: a main-belt body is cheaper to deliver to Mars (3.84 km/s) than
to Earth (4.13). Mars has an atmosphere so aerocapture is *available* and TPS
can be carried; the Moon does not, so `lunar_surface` ignores
`use_aerocapture_return` exactly as `cislunar` does. Since v1.10.0 "available"
is literal, where an atmosphere exists the model prices both the aerocaptured
and the propulsive return per asteroid and flies whichever pays. It is not a
foregone conclusion: on a slow-arriving target the Δv saved is small and the
heat shield is not worth hauling out and pushing back.

**Surface delivery costs are chained per stage, not lumped.** Module 2's
`_DELIVERY_LEGS` walks real stages backwards from the payload. Collapsing the
lunar chain into one 5,920 m/s burn would overstate the Moon by ~2x (10.96 vs
4.99 kg in LEO per kg landed) because it throws away staging. Mars' `edl` leg
carries a measured surviving-mass fraction (MSL 27.6%, Perseverance 29.8%),
not a Delta-v.

**The two surface prices are marginal-transport LOWER BOUNDS.** No NRE, no
programme overhead, no cadence limit, on a reusable Falcon 9 LEO price. Real
CLPS lunar delivery is ~$1M/kg today at ~100 kg scale against this model's
$21,210/kg. They answer "what could this cost at industrial scale", and the
whole Mars result rests on that framing.

**A commodity with no in-space market is not worth zero at a depot.** It is
worth its terrestrial price *minus* the downleg (`downleg_cost_usd_per_kg`: 
capsule + TPS + recovery + departure burn, ~$25,400/kg from LEO). Platinum at
a depot is ~$31,300/kg, not $0. Conversely, launch-cost-avoided is **additive**
to the terrestrial price, not a replacement for it. `value_route` records
which fate each commodity took.

**The payload mix is optimised, not specified.** `optimal_payload_mix` is a
fractional knapsack over `asteroid_phase_table`, fill the hold with the best
phase available, then the next. Greedy by $/kg is provably optimal here
because the phases are divisible and priced per kg. Both bounds (content and
purity) fall out of it; do not reintroduce them as separate clamps.

**So is the mission architecture, as of v1.10.0.** The search for one asteroid
now spans vehicle × propellant × return mode × propellant sourcing ×
rendezvous apsis × concentration ratio, and every axis is resolved for that
body. Aerocapture and ISRU used to be catalog-wide switches, which meant a
target whose best mission was propulsive got flown aerocaptured because some
other asteroid wanted it. If you add another architecture choice, add it to
this search rather than to `CalcConfig` as a global, and check the
never-worse invariant afterwards.

The check is a one-liner over two archived runs, and it had never actually been
run until 2026-08-07. Join the raw and beneficiated catalogs for a destination
on `designation` and assert `benef_ratio <= raw_ratio` row by row. Across all
five destinations, 165,843 asteroid × destination pairs, it holds with zero
exceptions, and the worst case is exactly 1.0000, which is beneficiation
declining and falling back on the `beneficiate=False` baseline. That is the
signature to expect: never worse, and equal wherever it declines. A max above
1.0 means the search is optimising something other than what gets reported.

⚠️  **Three definitions this file uses everywhere and had never written down,
each of which has now cost someone an hour.** `verify.py` is the executable
statement of all three; this is the prose one:

| quantity | it is | it is NOT |
|---|---|---|
| the objective ranked on | `total_cost_usd / gross_value_usd` | any column; **there is no `cost_revenue_ratio`** |
| `r`, in every never-worse table | the *lower* setting's ratio over the *higher*'s, e.g. `benef / raw` | the reciprocal |
| "median improvement +42.5%" | `median(1 − r)`, the fractional **reduction** in the ratio | `median(1/r − 1)`, which reads **74.0%** for the same result |

The last two describe one identical result and differ by a factor of 1.7, so a
harness that picks the wrong one reports a number that is not wrong so much as
*not the one on record*, and every committed figure here uses `median(1 − r)`.

⚠️  **A fourth, and it is a DENOMINATOR rather than a definition.** "Bodies
declining to concentrate" has two right answers: over the **joined** raw and
beneficiated pairs it is 15.8%, and over the beneficiated run's own
`concentration_ratio <= 1.0` column it is **15.61%**, because the bodies that
are evaluable beneficiated but not raw are in one denominator and not the
other. Both are correct. **Quote which one.**

**Which apsis the transfer meets the target at is a SEARCH, not a rule, and it
must not be simplified back into one.** The old estimator used
`r_target = aphelion if aphelion >= 1 AU else perihelion`, which is right for
most main-belt bodies and wrong for high-eccentricity ones: an aphelion
rendezvous is a slow transfer with a cheap match burn and an expensive
departure, a perihelion rendezvous the reverse, and which dominates depends on
`a` and `e` together. **For a = 0.6, e = 0.8 the rule cost 18.5 km/s outbound
where perihelion needs 12.1.** Both apsides are priced now and the winner is
resolved against the **destination**, so a body best met at aphelion for an
Earth return can be best met at perihelion for Mars. ✅  Bennu, Eros, Itokawa
and both reference cases still resolve to aphelion, so the published validation
figures are unaffected.

**How hard to concentrate is searched, not derived.** Grade saturates at
`saturation_ratio` = 1/(frac_best × recovery); costs keep climbing. So the
optimum is usually strictly interior and `evaluate_combo` sweeps for it. Two
mistakes already made here, both of which *looked* principled:
  1. Driving the ratio to the maximum, made cislunar missions 4× worse.
  2. Driving it to saturation on principle, still made cislunar ~12% worse.
The search also always evaluates **not concentrating at all** (via
`beneficiate=False`), which is not the same as ratio 1.0; that would still
pay the separation recovery loss and the array mass for no grade gain.
Without that baseline beneficiation cannot be declined, and stops being
weakly dominant.

Note this makes the beneficiation path several times slower than raw.
`concentration_search_steps` is the dial.

✅  **ONE CELL HAS NOW BEEN RE-RUN, AND THE PROJECTION HELD.** Measured
2026-08-11 on calc `1.15.0`, full 1,554,353-row catalog, cislunar, raw, 12
workers, programme search OFF:

| | calc `1.14.0` | **calc `1.15.0`** | speed-up |
|---|---|---|---|
| `cislunar` raw, full catalog | 5,350 s | **1,306 s** | **4.10×** |

**4.10× lands inside the projected 3.4-4.6× band**, which is the first time a
compounded sample-derived projection in this file has been checked against a
full run, and it is the *narrow* kind of projection (a ratio over identical
rows), not the wall-clock kind the note below warns about. Every other wall
clock in this section is still `1.14.0` and still high by roughly that factor.

🚨  **And the run reproduced the committed cell EXACTLY, across three
releases.** `26.7863×` on `650,516` evaluable rows with **2021 CX5** winning, all
three identical to the `1.14.0` figures at the top of this file. That is the
strongest form the "performance only" claim has ever been checked in: `1.14.1`
and `1.14.2` each asserted bit-identity on 150-2,500-row samples, and `1.15.0`
asserted inertness at N = 1 on 400 rows. **All three now hold on 1.55 million
bodies at once.** Do not re-measure the raw cislunar cell on account of any of
them.

⚠️  Do not multiply those two factors and quote the product as a runtime *in
general*; see THE SAMPLING RULE. The two speed-ups are ratios measured on
identical rows in one process, which is far better conditioned than a projected
wall clock, but the wall clock they imply is still a projection. It happened to
hold **for this cell**; that is one data point, and the beneficiated cell is
still unmeasured on anything past `1.14.0`. ✅  *(Measured 2026-08-24:
**3,424 s** on `1.17.7`.)*

⚠️  **The timings in this file have moved TEN times, for ten unrelated
reasons, and the fifth dwarfs the others.** Everything below is per
*catalog*, and catalog `1.1.0` made the catalog **17× bigger**: 89,367 rows
to 1,554,400. Cap `eval_row_cap` (which now *samples* rather than truncating; 
see calc `1.13.0`) for anything interactive.

> ✅  **ALL OF THEM ARE RE-MEASURED NOW (2026-08-23/24).** The twelfth move is
> the whole `1.17.x` line landing at once, measured on the full catalog for the
> first time: `cislunar` reads **733 / 1,253 / 3,424 / 5,692 s** for raw-N1 /
> raw-searched / benef-N1 / benef-searched, and all twenty cells are tabulated
> in [README.md](README.md#beneficiation). **Every wall clock below is
> superseded**; they are kept because the *reasons* the timings moved are the
> point of the section.

⚠️  **The eighth, ninth, tenth and eleventh moves are calc `1.17.1`,
`1.17.2`, `1.17.4` and `1.17.6`, and NONE of the wall clocks below have been
re-measured on any of them.** All four are performance-only. `1.17.6` measures
**1.15 / 1.05 / 1.18 / 1.12×** per row across raw / beneficiated / raw-searched
/ default, and it is the one whose quoted ratio *depends on the row cap*, so
read its own section before using any number from it.

`1.17.1` and `1.17.2` land hardest on
the cells that call the COST model most; a stride-sample A/B puts `1.17.1` at
1.04× (raw, search off) to **1.35×** (beneficiated + search, the `1.17.0`
default), and `1.17.2` at **0.99-1.02× with the search OFF** against **1.45×**
raw-searched and **1.37×** on the default cell. `1.17.4` lands on the MASS
cascade instead and comes out **1.40 / 2.04 / 1.26 / 1.50×** across raw /
beneficiated / raw-searched / default, plus a fixed **~15 s off the load**.
**Do not scale the numbers below by any of those ratios**; see THE SAMPLING
RULE below, which covers exactly this case. Every figure below is still the
`1.14.0`/`1.15.0`/`1.16.0` measurement it says it is, and those are the only
measured ones.

⚠️  **And do not compound them.** `1.17.1` × `1.17.2` on the default cell is
1.35 × 1.37 = 1.85×, which nobody has measured; the two were measured against
different HEADs on a host whose absolute times moved 30-45% between passes.
Compounding all three to 2.8× is worse still, and `1.17.4`'s and `1.17.6`'s
numbers are the two sets here measured with both builds in a single process, 
which removes the host-drift objection and does nothing at all about THE
SAMPLING RULE. ⚠️  `1.17.6` measured the same build twice that way and got
**1.14× and 1.19×** on the raw cell, so even the interleaved construction leaves
a few percent of drift; that is why its section records both passes.

> ✅  **SCORED 2026-08-24, and the warning was half right.** The full-catalog
> measurement exists now, so the forbidden product can be checked: compounding
> all five sample ratios gives **1.82 / 2.67 / 3.02 / 3.45×** against a measured
> **1.78 / 2.72 / 3.11 / 4.32×**. Three cells land inside **3%**; the default
> cell is **20% low**. The advice stands, compounding understates, and it
> understates worst on the one cell anybody runs, but the error is a fifth,
> not the order of magnitude the paragraph implies. See THE SAMPLING RULE.

⚠️  **`1.17.4`'s load saving does NOT scale with the row cap**, so it behaves
oppositely to most of this section: ~15 s is half the wall clock of a 400-row cell and 0.2% of a full
beneficiated one. A ratio quoted for it is meaningless without the row count.

**Measured on calc `1.14.0`, full catalog, 12 workers, 2026-08-09**; these are
the real numbers, and the sixth move is v1.14.0's power-source search axis:

| destination | raw | beneficiated |
|---|---|---|
| `cislunar` | **5,350 s** (89 min) | **38,072 s** (10.6 h) |
| `lunar_surface` | 5,118 s | not run |
| `leo` | 10,063 s | not run |
| `mars_surface` | 10,275 s | not run |
| `earth_surface` | 10,670 s | not run |

🚨  **The beneficiated estimate in this file was wrong by 4.8×, and the error
ran the OPPOSITE way to the one v1.1.0 warned about.** This file said "~2.2 h
beneficiated, estimated from the sample's 3.12× raw:beneficiated ratio". It is
**10.6 h**, because the real full-catalog ratio is **7.1× raw, not 3.12×**
(⚠️  **4.67× on `1.17.7`**; the perf releases landed unevenly). On
the 6,000-row v1.14.0 sample the ratio looked like **1.63×**: off by a factor
of four in the same direction.

Read that against the v1.1.0 note directly below, which records a sample
**over**estimating a run by 3.1×. So samples have now mispredicted full-catalog
runtime badly in *both* directions on this pipeline, for opposite reasons; 
fixed costs dominate a small run, and the expensive tail of the concentration
sweep is under-represented in a stride sample.

### THE SAMPLING RULE

> **A sample predicts full-catalog runtime here to no better than a factor of
> ~5.** It is *not* "samples overestimate"; the misses run both ways. Budget
> from a measured full run of the same cell, or do not budget at all.
>
> ⚠️  It covers **ratios between two settings**, not only absolute wall clocks;
> v1.15.0 established that half. Four mispredictions so far, two of them
> ratios: v1.13.0 raw (3.1× high), v1.13.0 beneficiated (4.8× low), v1.15.0's
> search cost (1.4× low), v1.16.0's search cost (2.7× low).
>
> ✅  The one kind of projection that HAS held is different in kind and worth
> keeping separate: extrapolating a **measured full-catalog speed-up on one
> cell** to another setting of that same cell. That is what put `1.15.0`'s
> beneficiated cell inside its projected band. Extrapolating *from a stride
> sample to the full catalog* is what has failed four times.

> ✅  **A FIFTH DATA POINT, 2026-08-24, and it is the first one that makes the
> rule look GENEROUS.** This file forbids compounding the per-release
> performance ratios ("do not compound them … nobody has measured that"). The
> 20-cell campaign measured the ground truth, so the forbidden arithmetic can
> finally be scored: compounding the stride-sample ratios of `1.17.1`,
> `1.17.2`, `1.17.4`, `1.17.5` and `1.17.6` against the measured `1.16.0` →
> `1.17.7` full-catalog speed-up:
>
> | cell | compounded from samples | measured | error |
> |---|---|---|---|
> | raw, search OFF | 1.82× | **1.78×** | +1.9% |
> | benef, search OFF | 2.67× | **2.72×** | −1.8% |
> | raw, search ON | 3.02× | **3.11×** | −2.9% |
> | **benef + search** (default) | 3.45× | **4.32×** | **−20.2%** |
>
> **Three cells inside 3%, and the default cell 20% low.** So the prohibition
> was right about the *direction*, compounding understates, and the magnitude
> is a fifth, not the factor of ~5 this rule is written around.
>
> ⚠️  **Do not read that as permission to compound.** It is one test, on one
> release line, of five ratios that all pointed the same way; and it missed
> worst on the **only cell anybody actually runs**. What it does establish is
> that the ~5× bound is a bound on the *worst* case and not a typical error, 
> and that the cell most likely to break a projection is the most expensive
> one, which is also the one you were trying to budget.

**This is the canonical statement; everywhere else in this file points here.**

The ten-cell sweep is therefore **~3.5 days**, not "most of a day": the raw row
alone is 41,476 s (11.5 h) and the four unmeasured beneficiated cells are ~70 h
on top of cislunar's 10.6.

> ✅  **MEASURED 2026-08-23/24, and it is not 3.5 days.** The full **twenty**-cell
> matrix, every destination × ore × search, i.e. twice the work this paragraph
> is estimating, took **26.1 h** on calc `1.17.7`. The ten cells this sentence
> describes are **13.5 h** of that. The projection was not wrong when written;
> five performance-only releases landed in between, worth 1.78-4.32×. **A
> runtime sentence in this file is only ever true of the release it names**, 
> which is this section's own point, arriving on schedule.

⚠️  **The per-destination table this paragraph used to restate is in
[versions.md](versions.md#calc-v1110--transportation-v190), and was a second copy of it.** What is
guidance rather than record, and so belongs here: the calc `1.11.0` numbers
were measured on the **old ~31,000-row catalog** and their absolute seconds are
two orders of magnitude out of date, but the **ratios between cells** are still
the right way to reason about relative cost. Beneficiation ran 5.2-6.1× raw
across all five destinations, and the ordering of the cells by cost has been
stable across every re-measurement since.

On calc `1.12.0`, cislunar measures **88 s raw / 502 s beneficiated** against
89 s / 462 s; raw unchanged, beneficiated up ~9%. That is `_cargo_water_kg`
calling the payload knapsack inside the fixed-point loop instead of once after
it, which is the price of sizing the array that bakes the cargo water. It was
measured before it was accepted (250-body sample: 19.8 s → 21.4 s, +8%). Only
cislunar has been re-timed; assume the rest of the table is ~10% low on
beneficiated, and the sweep **~75 minutes**.

The history, because each step is a different kind of change and conflating
them is how a stale timing gets quoted as evidence:

- `1.10.0` and earlier: ~140 s raw / ~2,120 s beneficiated. The ten-cell
  reproduction took about three and a half hours.
- `1.10.1`: ~33 s / ~137 s. A **pure performance release**: every number
  bit-identical. See [calc v1.10.1](versions.md#calc-v1101).
- `1.11.0`: the table above, roughly 5× slower than `1.10.1` again. Also not a
  performance regression in the code: the search is **4.6× wider** (357
  vehicle × propellant combinations per asteroid against 77) because the
  propellant table went from 7 usable rows to 21.

And before all of that they read ~1,100 s and 8×. That correction was
structural rather than a re-timing: v1.10.0 made the architecture search
per-asteroid, and it multiplies with the concentration sweep, because every
ratio is priced against every vehicle × propellant × return mode × ISRU choice
× apsis instead of against one nominal architecture.

So the beneficiated figure has now moved **three times, for three different
reasons**; up because the model got more expensive (v1.10.0), down because
the code got faster (v1.10.1), and up again because the option set got bigger
(v1.11.0). Only the first and third changed any output. A wall-clock number in
this repo tells you nothing on its own; always read which release it was
measured on.

**The beneficiation power plant feeds back into the rocket equation.**
Processing energy (Module 3: 200 Wh/kg dug, 500 Wh/kg concentrated) over the
stay time gives a power draw; Module 3's 60 W/kg-at-1-AU row scaled 1/r² by
the target's semi-major axis turns that into array mass; the array is
launched like everything else. Payload → feed → power → mass → payload is a
genuine circular dependency and `evaluate_combo` solves it by fixed-point
iteration. The 1/r² term is why a 3+ AU target needs a ~54× heavier plant
than a 1 AU one.

**But past 3.46 AU the plant should not be solar at all** (v1.11.0). Solar is
60 W/kg at 1 AU falling as 1/r²; an RTG is ~5 W/kg flat; sqrt(60/5) = 3.46 AU
is where they cross. Module 3 has priced RTGs since v1.2.0 and nothing read
the row until v1.11.0, so distant bodies were being punished for an
architecture choice no real outer-system mission makes. It is not a free win:
a radioisotope watt costs 625× a solar one ($500k against $800), so the model
buys the smallest one that does the job, and `rtg_max_power_w` caps it because
the binding constraint is **Pu-238 supply**, not money; DOE production is
~1.5 kg/yr, about one flagship RTG a year for the entire world. Do not extend
this to the EP array: that runs to hundreds of kilowatts, and pricing it off a
radioisotope row would quietly invent nuclear-electric propulsion.

**A propellant's tank is mass, and it scales with VOLUME** (v1.11.0). This is
the one to understand before touching the propellant table, because it is what
stops high-Isp low-density propellants running away with the answer. LH2 is
0.0708 kg/L against kerolox at 1.015, fourteen times the tank per kilogram
burnt, and before v1.11.0 hydrolox got its 452 s with no volumetric penalty
at all. `tank_kg_per_L` is derived per storage class from flight articles
(hydrolox lands at 9.7% of propellant mass against Centaur's measured ~9.7%),
and it enters the closed-form cascade through `k = 1/(1 − t(R_ret − 1))` and
`k_out`. `t(R − 1) ≥ 1` means the **tank cannot close** and the combination is
infeasible, not merely expensive, the same condition Module 2 hits on
`δ·R ≥ 1`.

**Δv must stay per-asteroid.** Before v1.4.0 every asteroid got the same Δv,
which made `max_payload_kg`, `total_cost_usd`, `mission_duration_yr`, `vehicle`
and `propellant` single-valued across an entire catalog; the ranking was
composition-only and accessibility had no effect. If you ever see those
columns collapse to one unique value again, `use_per_asteroid_dv` is off or
the orbital elements aren't reaching Stage 4.

**Electric propulsion needs its Δv penalty.** The rocket equation ignores
thrust; trajectories don't. Without `dv_penalty_factor`, a 3,000 s Isp
thruster wins the mass cascade on an impulsive budget it cannot fly.

**Extraction is rate-limited.** Payload is capped by what the rig can dig
inside `max_mining_duration_yr`, and the dig time feeds mission duration, ops
cost and WACC. Removing that cap makes the rig an infinitely fast vacuum.

**M-type is not a bare metal core.** No M-type has ever been measured near
iron-meteorite density: Psyche is ~3.8-3.9 g/cm³. Metal fractions are set
accordingly; don't restore the 0.80/5.30 values.

A default run produces zero viable missions. That is the correct answer, not
a regression. So does every other combination currently in the model.

## The older matrices, and the claims they retired

🚨  **`versions.md` is the authority for every superseded measurement, and it
is the only copy.** It holds the per-release notes, the cost/revenue matrices
each release retired, the runtime history and the programme-scale curves. This
file used to carry a second copy of all of it, roughly five thousand lines,
beneath its own warning that **two copies of one measurement is the
documentation form of the defect this file exists to catalogue.**
The second copy is gone; what stayed here is the part that is *editing
guidance* rather than record.

**So: before re-measuring anything, or "fixing" a result that looks wrong, read
[the measurement history](versions.md#measurement-history).** The rule that
makes it usable is that every table there names the release and the catalog it
belongs to, and if one does not say, it is not to be used.

⚠️  **The claims below are retired. Do not restore any of them from an older
revision of this file**, which is exactly how three of them came back once
already:

| retired claim | what is true now |
|---|---|
| "`mars_surface` is the best case" | **`cislunar` is**, on all four settings, by a factor of 1.72 on the default cell |
| "chemical propulsion is extinct in this model" | hydrolox holds 0.2-10.3% everywhere; methalox reaches **11-15% of FOUR destinations** beneficiated |
| "iodine wins nine of the ten cells" | a **single-mission** claim; on the 28-cell campaign iodine wins **three** beneficiated searched cells (`earth_surface`, `geo`, `leo`) |
| "zero `replicated`-scaling devices survive" | they survive, and as of 2026-08-24 one **wins**, at `mars_surface` raw with the search on |
| "a `replicated` device never wins anywhere" | retired by the same measurement; the gate is a mass penalty, not a threshold |
| "a `replicated` device wins exactly one cell" | it wins **two** as of 2026-09: both raw `mars_surface` cells, N = 1 included |
| "2021 CX5 takes 10 of the 20 cells" | an `elasticity` claim; on 28 cells it takes **8**, and sweeps no destination |
| "cislunar is the best case by a factor of 1.72" | still best, but `mars_orbit` is within **11%** on the default cell |
| "the campaign is five destinations and the model has seven" | **all seven are measured** as of 2026-09 |
| "`W < trips` on 2,077 rows" | an `elasticity` figure; under `capacity_cap` it is ~146,000 at cislunar |
| "the optimum N is *provably* a multiple of the rig's trip life" | only *usually*; programme calendar time pushes back inside a band |
| "the cycle bound retires almost every rig" | **`cislunar` raw** only; the calendar bound does 42% at `cislunar` beneficiated and **80.79%** at `mars_surface` |
| "a programme's pace is set by orbital mechanics, not mining rate" | true of raw everywhere, and **inverts under beneficiation at ALL SEVEN**, Mars included |
| "aerocapture runs 82-98% at every atmospheric destination" | **37.69-98.36%**; `mars_orbit` declines it about half the time, and the choice being close to even there is the per-asteroid pricing working |
| "aerocapture rises under beneficiation at every atmospheric destination" | `geo` **falls**, 90.70% to 78.66%, at N = 1 |
| "`mars_surface` is the exception that proves the mechanism" (the dig never sets its pace) | its beneficiated cells are **46.24 / 53.76**, so the dig does set the pace; there is no exception left |
| "ISRU tracks hydrolox to within 0.03 pp at every destination" | fails at `earth_surface` (**+0.3668 pp**), `leo` (+0.2885) and `mars_orbit` (-0.0630); it was a five-destination claim |
| "iodine overtakes xenon at `leo` and wins `earth_surface`" | it wins **three** beneficiated searched cells now, `geo` too, and is within 2.75 pp at `cislunar` |
| "chemical propulsion reaches 11-15% of three destinations" | **four**; `mars_orbit` joins at 14.48-14.55% |
| the `saturation_multiplier` min/median/max table | the column is **identically 1.0 on all 28 cells** under `capacity_cap`; the live diagnostic is `market_clearing_fraction` |
| "the cycle bound retires almost every rig", already narrowed once | wrong three ways now: beneficiated `cislunar` (42.49% calendar), `mars_surface` (81.66%) and `mars_orbit` (78.13%) |
| "the RTG option is correctly wired and very nearly unreachable" | it became reachable the moment the eclipse term landed, and was then found to be choosing on **mass** while the two sources differ 625× in price |

The last row is the one to internalise, because it generalises past its branch:
**an unreachable branch is not a verified branch.** "How often a branch fires"
is a statement about the population, not about whether the branch is right, and
the moment something else made it reachable a latent defect became 14% of
mission cost.

✅  **Placeholder rows are worth remembering as a class.** The four
non-cislunar beneficiated cells sat in the v1.11.0 matrix for three releases on
the old 89,367-row catalog. When they were finally measured, four came in
*better* and `mars_surface` came in **6.5% worse**. A placeholder from a
different population does not even have a reliable **sign**.

## The corrections the model accumulated

Every model listed under
[What the model charges for](README.md#what-the-model-charges-for) moved every
number when it landed. They are corrections, not options; the flags exist to
isolate an effect, not to be left off. **That list lives in README because it
describes what the model currently does**, and it is not repeated here.

⚠️  **"...and each defaults ON" was true until calc `1.22.0` and is not now.**
Three of the models in that section default OFF: mission reliability, the
learning curve and the cost of capital. Their prose stayed where it is, because
what each charges for is still what it charges for, and each section opens by
saying it is off. So the README section is no longer a list of things a default
run does, and the membership test below is the only thing that sorts the two
categories.

What belongs here is the **test for membership**, which is not "is it on by
default":

> **Was the model getting something for free before?**

⚠️  Neither `use_beneficiation` nor `optimise_programme_scale` is on the list,
and calc `1.17.0` defaulting both ON does not put them on it. They are
questions ("ship concentrate or ore?", "how big a programme?"), not subsidies
being withdrawn. Since `1.17.0` that test is the *only* thing separating the
two categories, because "it defaults OFF" used to carry half the argument.

⚠️  **One entry was withdrawn rather than added.** v1.11.0's orbital-refuelling
charge billed a real cost against a scenario this module does not have, which
makes it an error rather than a correction. Gated off, not deleted, so the day
this module gains a direct-injection architecture the charge becomes correct.

🚨  **CALC `1.22.0` PUT THREE MORE ENTRIES ON THE SECOND LIST AT ONCE, AND
THAT LIST IS NOW THE LONGER OF THE TWO WAYS A DEFAULT CAN MOVE.** The cost of
capital (`apply_wacc_compounding`), mission reliability (`model_reliability`)
and the learning curve (`model_learning_curve`) all fail the membership test in
the same direction insurance does: each is a real charge a real programme pays,
and each prices something that is not a mass, a Delta-v or a kilowatt. Read
their sections in [README](README.md#what-the-model-deliberately-does-not-charge-for);
what belongs here is the three things that will bite an editor:

⚠️  **`apply_wacc_compounding` SILENCES `model_programme_calendar`, which is
still True.** The calendar multipliers are exactly (1.0, 1.0) at `wacc <= 0` by
construction, so that whole term charges nothing now. The flag was left ON
rather than flipped because it still says the right thing about what to charge
the moment there is a rate; **the run banner reports which of the two states it
is in**, which is the only reason a reader is not left to derive it. Do not
"fix" the apparent inconsistency by flipping it.

⚠️  **`model_learning_curve` IS THE ONE WHOSE SIGN YOU WILL GUESS WRONG.**
Turning it off makes the default cell **34.3% WORSE**, because the curve was a
discount on recurring hardware. And it is **exactly 0.000% at N = 1**, so it
cannot be checked by re-running a single-mission headline -- the same shape as
the two programme-scale entries this file already warns about.

⚠️  **`model_reliability_growth` is still True and is inert**, because it
shapes P rather than creating it. Left that way so turning reliability back on
restores the whole v1.21.2 term rather than half of it.

🚨  **AND CALC `1.20.0` IS THE FIRST ENTRY THAT RUNS THE OTHER WAY: A CHARGE
THAT IS CORRECT AND WAS STILL REMOVED.** Insurance (`charge_insurance`, now
False) fails the membership test in the direction nothing had failed it before.
The model was not getting it free; it was paying for it, and the payment is
real. It is out of **scope**, which is a different objection from the tanker
charge's, and the two are worth telling apart because the remedy looks
identical:

| | the charge is | the flag means |
|---|---|---|
| `charge_tanker_flights` + `escape_direct_launch` | **wrong here** | re-arm it when the scenario exists |
| `charge_insurance` | **right, and not asked** | turn it on if you want the invoice rather than the physics |

The test that separates them: **would the charge be correct if you levied it
today?** The tanker charge would not; insurance would. So this one gets a
README section of its own,
[what the model deliberately does not charge for](README.md#what-the-model-deliberately-does-not-charge-for),
rather than a line on the corrections list, and it must not be added to that
list by a later reader tidying up.

⚠️  **Its magnitude does not read off its invoice, and this is the general
shape rather than a fact about insurance.** A premium is an **upfront** line,
so it carries contingency and the full upfront WACC multiplier: 2.4-4.3% of
total cost, and 5.5-9.6% of the answer, an effective 2.12-2.38x. **Any upfront
line in this cascade is worth roughly twice its face value**, and any
end-of-mission line is worth its face exactly (`mult_end` is 1.0). Costing one
by its share of `total_cost_usd` understates it by that factor.

🚨  **AND CALC `1.21.0` IS THE FIRST ENTRY THAT CHANGED SHAPE RATHER THAN
SIDES.** Market saturation passed the membership test and still does: without
something here the model sells any quantity at spot, which is the definition of
getting something for free. What moved is that it stopped being a **flag** and
became a four-valued **choice**, `market_model`, and three of the four values
are constant-price. So the correction survives, the boolean does not, and the
question "is this charge on?" no longer has a yes/no answer, it has a mode.

⚠️  **Do not read `capacity_cap` as the correction being switched off.** It
is a different statement of the same correction: `elasticity` bends the price
when a market fills, `capacity_cap` stops the sale. Both refuse the free lunch.
`unbounded` is the one value that genuinely withdraws it, which is why it is
labelled a diagnostic and why the run says so out loud.

⚠️  **Two entries are inert at N = 1**, the rig's duty cycles and programme
calendar time, because both bound programmes rather than missions. No
single-mission cell moves for either, so neither can be checked by re-running a
headline.

🚨  **Do not spell the count out in prose.** It has rotted twice, once in each
direction, and both times in a heading or a summary sentence rather than in a
measured cell. Count the list.

Two entries carry guidance that does not belong in README:

**`trips` is a property of the MISSION, not of the asteroid.** It is
`min(life / stay, max_trips)`, and the stay depends on how hard the candidate
concentrates, so two concentration ratios on one rock are two trip lives. **Do
not cache it per body.** Observed directly: one body reports trips of 3, 4 and
5 at different N.

**A search must optimise what it reports.** Until v1.10.0 every per-asteroid
search picked the candidate with the highest `profit_usd`, i.e. the cheapest
mission, while the project ranked the output by a ratio nothing had optimised.
`selection_key` is lexicographic now: maximise profit if any candidate is
actually profitable, otherwise minimise cost/revenue.

🚨  The diagnostic that finds this whole class of bug is worth keeping:
**widening a search must never make the reported answer worse.** It did, which
is how the bug was found; adding options let a cheaper, far less productive
mission win on profit while the reported ratio got worse. Any time a new option
degrades a result, the search is optimising something other than what is being
reported. It is `verify.py`'s check 5.

## Durable lessons from the release history

The releases themselves are in `versions.md`. What follows is what survived
them as guidance: the defect classes that keep recurring, the traps that have
each cost someone a day, and the register of items already measured and
declined so nobody re-derives them.

### The defect classes, in the order they keep recurring

**1. A mass in one cascade with no price in the other.** The mass cascade and
the cost cascade are written in different places and nothing checks that every
kilogram in one has a price in the other, or that every kilogram the cost model
pays for is actually flown. This is the class to look for **first**, and
v1.11.0 introduced three fresh instances while fixing three older ones. The
one-line assertion that catches the whole family:

```
hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg
```

⚠️  `mining_hardware_kg` is **not an output column**; the rig is the config
constant (2,000 kg). Written verbatim against the CSV this raises `KeyError`,
which it has done to two harnesses.

**2. A reference row that is internally contradictory**, holding two mutually
exclusive physical states and collecting the benefit of both. Argon carried a
cryogenic liquid's density *and* an ambient gas's zero boil-off, its own two
comments contradicting each other three lines apart. Neither number was crazy
alone. **Check that a row's fields describe a single physical article.**

**3. A quantity asked at a finer granularity than it has answers.** Now the
most common shape in this codebase by a wide margin: a column with few distinct
values and one Python call per row. Found on **both sides of the CSV boundary
and in between**, composition being derived per row when it is a function of
76 spectral types, and it recurs at every level: per-candidate constants that
vary only per body, per-option work that varies only per fleet.

⚠️  **The redundancy factor is not the saving; the per-call cost is.** The
largest surviving instance by row count is `_infer_from_albedo`, 1,300,139 rows
and 54 distinct values, and closing it is worth **0.15 s**, because the
function is two float comparisons. A 62,000-way redundancy over a 20 ns
function is worth nothing. **Do not re-find one on the row count alone.**

**4. A prescriptive comment nobody applied, or a gap documented and mistaken
for closed.** v1.14.0's two largest findings had sat in `STORAGE_REFERENCE`
with their citations behind a "not modelled in Module 4" note, and Module 4
does not load that table. The gap was quoted in *this file* as a known
limitation for two releases and nothing moved. **A reference table nobody reads
is not a model.** If you record a gap, record which consumer would have to
change, and check that it can even see the table.

⚠️  The subtler version is a note that **documents an intention as an
accomplishment**. `tank_frac` spent three releases derived in two places, ten
lines apart, beneath a note claiming there was now one derivation with two
readers. It survived a release whose whole argument was bit-identity, because
nothing a hash can see was wrong. **Check that a de-duplication claim names ONE
surviving definition before believing it.**

**5. The wrong behaviour is the quiet one.** A float-typed identifier
stringifies to `"3.0"`, which is not null and not right, and joins nothing;
`.astype(bool)` reads `NaN` and the string `"False"` as `True`; `str.contains`
without `regex=False` matches metacharacters. Each cost releases. The tell they
share: **the dtype is inferred from the data**, so the code works on a small
test slice and breaks at scale.

### A number is calibrated FOR a term, and swapping the term re-reads it

calc `1.21.1`, and the most reusable thing in it. `IN_SPACE_ANNUAL_DEMAND_KG`
did not change; what changed was understanding what its numbers had always
been, and that is worth having written down because the next person to
"recalibrate" them will start where this started.

**The arithmetic first.** With `eps = 0.5` the curve is `(1 + Q/Qm)^-2`, so
revenue is `Q x P0 x (1+Q/Qm)^-2`; with `x = Q/Qm` that is `x(1+x)^-2`, whose
derivative `(1+x)^-3 (1-x)` is zero at **x = 1**. So:

| | |
|---|---|
| the MOST a commodity can earn under the curve | `Qm x P0 / 4`, at exactly `Q = Qm` |
| what a hard wall at W earns | `W x P0` |
| the wall with the same maximum | **`W = Qm / 4`** |
| a wall at the SAME Qm, against the curve | **1.2x to 12x more generous** |

**Then the reading.** Every row of that table is anchored on a CONSUMPTION
rate: `geo` is 550 satellites x 70 kg/yr of station-keeping propellant,
`mars_surface` is "a base that imports 20 t/yr". Those are absorption budgets,
which is a wall concept. Feeding one into a curve as its scale parameter means
the price is already quartered at exactly the quantity the base actually needs,
which nobody decided; it fell out of the substitution. **The curve was the term
misusing the number, so `1.21.0`'s 1.2-12x is a correction, not an inflation,
and the levels stay.**

🚨  **THE TRAP IS THAT THE `Qm/4` VARIANT IS TEMPTING AND MEASURES WELL.** It
nearly reproduces the `elasticity` levels (27.29x against 26.57x raw searched)
AND it fixes the ladder, dropping the beneficiated fleet median from 7 to 2 and
rows at `max_fleet_ships` from 11 to 2. It is still wrong: it asserts a base
importing 20 t/yr pays full price for 5 t/yr, against the table's own anchor,
and it is **calibrating a bottom-up cost model to a desired output**. Continuity
with a term you are replacing is not a calibration criterion. ⚠️  And the
symptom it appears to fix is not a ceiling problem at all: those rows carry a
median payload of 632 kg against 16,650 kg and cannot reach ANY ceiling at a
fleet of 64. **Declined; do not re-take it on the strength of the fleet median.**

✅  **The general rule: when you swap a model term, re-derive what its
parameters MEAN, not just what they are worth.** The same float can be a
capacity in one term and a scale parameter in another, and nothing in the code
says which.

### Cutting the cost of a call is not the same as cutting the call

calc `1.21.0` introduced a defect class 3 instance and closed it in the same
release, which makes it the cleanest example of that class in this file.
`_market_mode()` validates a four-valued config string, and it was being asked
once per CANDIDATE from two places: **332 calls per evaluable row, ~216 M over
a catalog, ~47 s of a full beneficiated cell**, to re-derive one of four
answers that cannot change during a run.

The first fix was to make the function cheaper, an identity test against a
frozen set ahead of the normalising path. It bought 217 ns to 168, and the call
count was untouched. The actual fix was to resolve it once per asteroid in
`evaluate_asteroid` and thread it like `markets`: **332 calls per row to 2**.

Three things worth keeping:

- **Count the calls before optimising the callee.** A 1.3x on a call that
  should not be happening is a rounding error on the real number.
- ⚠️  **The estimate in this file was wrong by a factor of 9 in the cheap
  direction.** The note on defect class 3 says `_evaluate_combo_at_ratio` runs
  "~24 million times on a beneficiated catalog"; the counted figure for this
  call is ~216 M, because the ladder asks a second time per candidate. **Count
  it; do not multiply the number in this table by hand.**
- ✅  The threading is bit-identical, **all eight cell hashes**, four per market
  model. A parameter defaulting to `None` and derived on demand keeps the
  function usable standalone, which is what makes the change provable rather
  than merely plausible.

### A wall does not blend, so a diagnostic can change meaning under you

calc `1.21.0`'s finding, and it generalises past its own release. This file has
long read "every row at the ladder's top means `max_fleet_ships` is BINDING,
not bounding … a payload whose commodities have no `annual_market_kg` entry
gets an infinite market". That sentence was written against a smooth demand
curve, where **every** row took some haircut and the haircut grew with the
fleet. Under a hard ceiling the same diagnostic counts a second, different
population:

| rows at `max_fleet_ships` | under `elasticity` | under `capacity_cap` |
|---|---|---|
| what it means | their payloads have **no finite market** | that, **or** their payloads are **too small to reach one** |

Measured: 15 of 155 raw searched rows sit at the ceiling, all clearing exactly
1.0000, at a median payload of **632 kg against 16,650 kg** for the population
and cost/revenue ratios of **486x to 37,620x** against the winner's 18.6x. The
per-delivery allowance falls as 1/F while the payload per delivery does not, so
a 632 kg load needs a fleet of ~300 to bind and the ladder stops at 64.

✅  It costs nothing today, because those rows lose by three orders of
magnitude, and the winner **is** bound (clearing 0.8307) and answers by taking a
smaller fleet. The lesson is not about small payloads. It is that **a
diagnostic inherits the shape of the term it was written against**, and
swapping a continuous term for a discontinuous one silently re-populates it.
When you change a model term, re-read every warning that counts rows.

🚨  **AND IT HAPPENED AGAIN IN calc `1.22.0`, IN THE OPPOSITE DIRECTION.** The
ceiling went from a hard wall back to something partly continuous: the surplus
past it now sells at half price. `saturation_multiplier` is still identically
1.0, but for a different reason; `unsold_payload_kg` went to zero and the mass
it used to carry moved to a new column. **Twice in two releases, the same
diagnostics changed meaning without changing name.** Read this lesson as a
standing instruction rather than as an account of one release.

⚠️  **And the first hypothesis was wrong, which is the other half.** The
obvious culprit was `other (bulk silicate)`, calc's composition residual: it is
priced, it is on 100% of rows and it has no market ceiling. Mapping it to the
`silicates` ceiling it is already priced against leaves raw **bit-identical**
and moves beneficiated **1.9%**, with the bound count and fleet distribution
unchanged. Legible, plausible, and wrong; one 400-row A/B settled it. **Measure
the mechanism before writing it down**, which this file has now said three
times and paid for once more.

### A diagnostic describes the WINNER, not the search that produced it

calc `1.21.2`, and it is the sharpest instance of a class this file already has
two entries for. The raw cislunar cell moved **+4.23%** on **one row of 155**,
and that row reports `market_clearing_fraction = 1.0` in both builds, with
`unsold_payload_kg = 0.0`. Nothing was left unsold, and the answer still
changed.

The row is the cell's winner. What moved is its **architecture**: New Glenn on
xenon at 117,406 kg becomes Falcon Heavy on iodine at 97,875 kg. No ceiling
binds on the mission that won. The ceiling bound the missions that **lost**,
and tightening it changed which one survived.

🚨  **So counting rows with `clearing < 1.0` UNDERCOUNTS a ceiling's
influence**, and the raw cell is the clean demonstration: **0 rows bound, 1 row
changed.** Any column that reports a property of the selected candidate is
silent about the constraint's effect on the candidates it beat, and a search is
exactly a machine for discarding those.

⚠️  **The general form, and it is not about ceilings.** `p_mining`, the chosen
propellant, the payload, the aerocapture flag are all in this category: they
describe the survivor. A term that changes *which* candidate survives will move
the answer while every survivor-property column looks untouched, so
`N rows affected` computed from one of them is a lower bound and should be
labelled as one.

### A diagnostic can go CONSTANT, and a constant reads exactly like a clean result

The 2026-09-14 re-derivation, and it is the hardest version of a lesson this
file already has twice.
[A wall does not blend](#a-wall-does-not-blend-so-a-diagnostic-can-change-meaning-under-you)
says a diagnostic inherits the shape of the term it was written against, and it
was about a row COUNT quietly changing which population it counted. This is the
same mechanism one step further on.

`saturation_multiplier` is the column `elasticity` used to express its price
haircut, and this file carried a table of its min, median and max across the
searched cells as the evidence that saturation was biting. Under `capacity_cap`
it is **identically 1.0 on all twenty-eight cells**: a hard ceiling does not bend
a price, it refuses the sale, so the column has nothing left to say.

🚨  **NOTHING ABOUT THAT LOOKS WRONG FROM THE OUTSIDE.** A multiplier of
1.000000 is a legal, meaningful value; it is what an unbound row has always
reported. A harness that kept printing this column would have printed
`1.000000 / 1.000000 / 1.000000` forever, and the honest reading of that is "no
saturation anywhere", which is *false*: ceilings bind on 18 to 96% of rows at
the six in-space destinations. The information moved to
`market_clearing_fraction` and `unsold_payload_kg`, and nothing announced the
move.

✅  **The rule: when you swap a model term, check whether the diagnostics that
watched it still VARY, not only whether their levels moved.** A stale level is
visible the moment somebody compares two runs. A dead column is invisible
forever, because it agrees with itself perfectly.

⚠️  **The cheap test is one line and it belongs in any harness that reports a
distribution:** if `min == max` across a full population, the column is not a
measurement, and saying so out loud costs nothing. `population.py` asserts
nothing about this on purpose, because the finding was worth a sentence in the
docs rather than a check nobody would read; but a table of min/median/max that
comes back identical on 28 cells should stop a reader, and it did not stop three.

⚠️  **It also cost a real claim, which is how it was caught.** The same pass
retired "ISRU tracks hydrolox to within 0.03 pp at every destination", a
near-equality that held on the five destinations it was measured on and fails by
up to **0.3668 pp** at `earth_surface` beneficiated. Both failures are the same
shape: **a statement about a quantity that stopped being interesting was left
standing because nothing it was compared against had moved either.**

### The fleet search is coarse-then-refine, so tightening a constraint can improve a row

calc `1.21.2` again, and this one nearly got written up as a defect. Pooling
the silicate ceiling made **3 of 155** raw searched rows and **1 of 65**
beneficiated searched rows come out **BETTER**, by up to 3.27%. A tighter
constraint improving the answer is the signature of a real bug -- an allowance
leaking into the cost side, or a rung priced under one set of caps and reported
under another -- which is precisely what check 7 exists to catch.

✅  **It was chased instead of filed, and the revenue model is monotone.**
Measured: **20,000 randomised fixed-programme comparisons; pooled revenue lower
on 10,235, equal on 9,765, higher on ZERO.** For any FIXED programme a pooled
allowance can only ever cost you.

**The non-monotonicity is the ladder.** `_evaluate_combo_at_ratio` walks a
geometric F ladder crossed with W and then runs **one refinement pass around
the coarse winner's neighbourhood**. It is not exhaustive. Move the coarse
winner and the refinement explores a *different* neighbourhood, which can hold
a point the old walk never visited. The four rows carry that fingerprint
exactly: identical vehicle and propellant, `programme_options_priced` 44 -> 41,
and `fleet_ships` dropping 6 -> 4, 10 -> 8, 11 -> 8 onto a programme that is
both cheaper and marginally better-selling.

🚨  **THIS IS A CAVEAT ON CHECK 7's INVARIANT, AND IT PREDATES `1.21.2`.**
"Constraining must never improve the answer" is **exact for a fixed programme**
and only **approximately true for the searched best**, because the best is the
output of a non-exhaustive walk. So a check 7 violation is evidence about the
LADDER before it is evidence about the ceiling, and the way to tell them apart
is the fixed-programme comparison above -- which is cheap, needs no cell run,
and is the thing to reach for first.

⚠️  **Declined, deliberately.** Making the fleet search exhaustive would buy a
few tenths of a percent on a handful of rows for a real runtime cost, and the
honest place for that question is the branch-and-bound item under "The one big
structural item that is still open", which needs an admissible bound and has
the same shape. **Do not "fix" the ladder on the strength of four rows.**

### A ratio taken across a session is a measurement of the session

calc `1.22.0`, and it is THE SAMPLING RULE arriving from a direction that rule
does not cover. That rule is about a sample of ROWS failing to predict a full
catalog. This is a sample of TIME failing to predict itself.

The release's first runtime table read 1.41-2.01x, measured by running the old
build's four cells, then the new build's, in one sitting. The decomposition run
that followed re-ran the **identical** all-four-restored raw cell and measured
**68 s against the 42 s** the first pass had recorded for it, and the
all-four-new raw cell at **32 s against 49 s**. So the same work varied by 1.6x
on this host, in the direction of the session clock rather than of the build,
and the "1.4x" was of the same order as the noise it was made of.

✅  **The construction that does work is the one `1.17.4` and `1.17.6` used:
interleave both builds inside ONE process**, which is why those two releases'
numbers are the only per-release ratios in this project measured that way.
⚠️  And even that leaves a few percent: `1.17.6` measured the same build twice
interleaved and got 1.14x and 1.19x.

🚨  **THE DECISION THAT FOLLOWS IS TO PUBLISH NO RUNTIME TABLE, NOT TO PUBLISH
A HEDGED ONE.** A table with a caveat under it gets quoted without the caveat;
this file has a dozen entries proving that. What was actually measured is that
**this host cannot resolve a 1.4x ratio on a 155-row cell**, and that is what
the release note says.

### A change can be numerically negligible and still destroy the evidence

This project's releases are argued from **bit-identity**, so an
operation-reordering "cleanup" is a change to the proof rather than to the
number. Four have been measured and refused on exactly this ground:

| tempting change | what it was worth | why it is refused |
|---|---|---|
| sort the phase table at source | removes ~325,000 sorts | the saturation block accumulates over its natural order, so the table is **load-bearing on the last ULP**: 2.8e-16 on 3 of 60 rows |
| rearrange `bracket > 0` into a launch-capacity comparison | one fewer term | re-associates the arithmetic and moves the boundary in the last bit, changing whether a marginal row **survives the prune** |
| `pd.read_csv(engine="pyarrow")` | **4.8×** on the 862 MB read, identical dtypes | its float parser rounds differently in the last ULP: 13 of 46 columns differ, and `estimated_mass_kg` moves 1e-13 relative. **Mass is what the ranking runs on** |
| a faster CSV writer | ~84 s a full cell | every one changes the formatting, which is the contract |

✅  **The one shape that is free is a change that only EVICTS.** Bounding a memo
of a deterministic pure function forces recomputation of the identical float;
no operation is re-associated and nothing is approximated. That is why
`1.17.7`'s cache bound was safe to take where all four rows above were not.

⚠️  And note the corollary for **comparisons**: a comparator stricter than the
artefact it compares reports failures that do not exist. `read_csv`'s default
float parser is not correctly rounded, so `float_precision="round_trip"`
belongs in the *comparison* and **must never be added to Stage 4's loader**,
where it would move every number in the model. The model's inputs go through
the same slightly-inexact reader on every run, deterministically, and that is
part of why bit-identity holds at all.

### Measured and declined, so nobody re-derives them

Each of these looks like an obvious win, has been measured, and is **closed
rather than deferred** unless it says otherwise. ⚠️  Do not find one again and
assume it is bigger than it looks.

| item | measured | verdict |
|---|---|---|
| inlining `builtins.max` | **1.2-2.4×** per call on Python 3.13, not the 6× recorded on an older interpreter; 18.7 M calls buys ~0.4% of a run | **closed.** ⚠️  cProfile attributes 2.5 s to it, which is dispatch overhead on a C builtin and is what will tempt the next person |
| the ratio-independent prologue hoist | **2.3%** of the default cell, 2.6% raw, of which ~89% is recoverable | declined: ~2% for splitting a 570-line function with ~40 locals crossing the seam. ⚠️  The **7.6%** this file quoted for three releases was stale |
| `integrity_check`'s second factorize | **0.454 s**, ~0.03% of a full raw pass | declined; it optimises the harness, not the pipeline, and every clean fix widens a contract. ⚠️  cProfile says 0.85 s; that is instrumentation |
| `_infer_from_albedo` by distinct value | 0.182 s to 0.028 s, 0.020 s fully vectorised: **~0.15 s**, 0.07% of Stage 1 | declined; see defect class 3 |
| `viability_only` on `max_return_payload_kg` | 519 ns of a 2,105 ns call, but only 31% of calls in a raw cell | declined at **under 1%** average, against a new branch in the hottest function in the model |
| the rig block in `_mission_cost_tail` | 3.2% priced alone | **taken in `1.17.5`**, once priced with the neighbour that shares its key. **Price the block, not the line** |
| Parquet instead of CSV for the catalog | 19.7 s to **2.1 s** | real and free, and not taken: it changes Module 1's output contract and no measured cell would move detectably |
| **quarter ceilings** (`Qm/4`, the wall matching the curve's maximum revenue) | raw searched 18.57x to **27.29x**, beneficiated fleet median 7 to 2, rows at the fleet cap 11 to 2 | **declined.** It measures well and is wrong: it contradicts the table's own anchors and calibrates to a desired output. See the lesson above |
| `nickel-iron`'s missing market ceiling | **7.7e−8** relative on one mission, 7.7e−5 at N = 100 | declined; it would break bit-identity on a destination not re-measured since `1.14.0`. Take it in that pass if `earth_surface` is ever re-run |

⚠️  **Two of those figures went stale while being quoted forward, in opposite
directions**, which is the argument for re-measuring rather than inheriting.
The `max` figure was stale by an interpreter version; the prologue's by three
releases of work around it. **Measure the remainder after taking the cheap
items, not before**: the ranking changes, and this file has now recorded that
three times.

### Why the GPU is not the answer, measured rather than assumed

Raised as "the CPU is maxed but the GPU is idle", and tested rather than
reasoned about, on the reference machine's RTX 2080 Ti:

```
numpy  fp64 exp, 40M elements   0.222 s
cupy   fp64 exp, 40M elements   1.695 s     <- 7.6x SLOWER than the CPU
cupy   fp32 exp, 40M elements   0.137 s
host->device, 320 MB            0.055 s
```

**The card is 7.6× slower than the CPU at the arithmetic this model is made
of.** That is the TU102's 1:32 FP64 rate and a property of every consumer
GeForce, not a tuning problem. fp32 is 1.6× faster and unusable, because every
verification here is a bit-identity check. The workload is also the wrong
*shape*, branchy scalar Python with early exits, a fixed-point loop and a
knapsack with a `sorted()` in it, so a port is a rewrite. And the one piece
that **is** GPU-shaped, the pre-filter, is ~10 flops per candidate: ~14 GFLOP
for the entire catalog, under a second on either processor.

**RAM is not a constraint either**, at a ~6 GB peak against 64 GB installed,
with the one exception `1.17.7` closed; see "Where a cache is safe" below.

### The one big structural item that is still open

**Branch-and-bound on the objective**, i.e. pruning candidates that *can* close
but cannot beat the incumbent. It needs an **admissible** upper bound on
`selection_key`, which is lexicographic over profit and cost/revenue with
revenue coming out of the payload knapsack, so a bound that is provably never
optimistic is real work.

🚨  **Do not approximate it.** A bound that is occasionally too tight silently
drops winners, and it drops them **without changing the row count**, which is
the one failure mode none of `verify.py`'s six checks would catch.

⚠️  Neither `1.17.4`'s pre-filter nor `1.17.7`'s cache bound is a precedent for
it. The first prunes on **feasibility**, which is monotone in two masses and
provable in four lines; the second prunes a **cache**, where eviction is
value-neutral by construction. Neither is monotone in anything the objective
reads.

### Traps in the code that a reader will otherwise re-introduce

- **`_combo_can_close` and `max_return_payload_kg` are two statements of one
  algebra**, and the pre-filter side is written in three pieces. They are kept
  adjacent for that reason, and the defence is `prune_infeasible_combos = False`
  plus a column diff. **Change one, re-run that diff**; it is `verify.py`'s
  check 2.
- **The pre-filter's second stage must run at pass 1's `structure_frac`.**
  Containment grows that term, and it appears in `denom` rather than in
  `bracket`, where a larger value only helps. Testing `denom <= 0` instead looks
  sound and is wrong in the one direction no output diff can see.
- **`want_phase` must stay a short circuit inside the one walk**, not a
  water-only copy: the greedy walk is cheap and the bookkeeping is what costs,
  so a copy buys nothing and adds a drift hazard on a function that is
  load-bearing on the last ULP.
- **`totals_only` is an early return, not a second code path.** Keep
  `total_cost` final before it, or the ladder silently starts pricing on a
  different number from the one it reports.
- **The prologue tuple's order is load-bearing**, unpacked in one statement. A
  field inserted in one place and not the other shifts every value after it and
  changes no row count.
- **Three sums stay written out term by term** (`hardware_cost`,
  `spacecraft_book_value`, `upfront_lines`): they interleave N-dependent and
  N-independent terms, so pre-adding would re-associate.
- **A cached `None` needs a sentinel.** `None` is a legitimate answer for "this
  propellant can never be made from asteroid material", so `.get(key)` alone
  re-derives it on every call for exactly the rows where the answer is no. A
  cache that silently stops caching is the quiet-wrong-answer shape wearing
  performance clothing.
- **NaN and None must normalise to the same cache key**, and a bare NaN key
  never hits, because two NaNs are not equal. Anything that is not a real number
  or `None` should take the uncached path rather than invent a key.
- **`factorize`, not `unique` plus a dict.** `factorize` is total: NaN is a code
  like any other, so a missing value cannot fall through a lookup that
  `nan != nan` would break.
- **Give each row its own list** when expanding a column by distinct value. A
  62,000-way alias on a mutable object is a trap whether or not today's code
  springs it, and it costs 0.4 s.
- **`AsteroidContext`'s membership test is "does it vary with the candidate",
  not a field count.** If a quantity varies with the vehicle, propellant, return
  mode, power source or concentration ratio it must not live there.
  `synodic_period_yr` is carried separately from `window_wait_yr` because the
  wait is zero when `model_launch_windows` is off while the period is still an
  output column.
- **Non-electric candidates skip the stage-2 solver entirely**; with no electric
  stage the second pass *is* the first.
- **Memo on the config VALUES a function reads, not on `id(config)`**, so a
  config edited between runs is still answered correctly.
- **Do not memoise a warning path.** An unknown destination must still shout on
  every call; that loudness is the point of the warning.
- **The market ceilings must never reach the SIZING path.** `_cargo_water_kg`
  calls `optimal_payload_mix` from inside the fixed-point power solve, so a
  `caps=` argument arriving there would make the whole MASS cascade a function
  of fleet size, and that asymmetry is the only reason the programme ladder is
  affordable to search at all. Ceilings bound what a load may SELL, not what
  the rig digs or the hull carries. `caps` defaults to `None` precisely so the
  sizing call cannot acquire one by accident; if you add another caller, ask
  which side of that line it is on.
- **`optimal_payload_mix(caps=None)` must stay bit-identical to the unbounded
  walk.** The reason is no longer "so `elasticity` reproduces v1.20.0" -- it
  stopped doing that at `1.21.1` -- it is that **the SIZING path passes no
  caps**: `_cargo_water_kg` calls this from inside the fixed-point power solve,
  so if `caps=None` ever stopped being the old walk, every mass cascade in the
  model would move. The guard adds a branch and no arithmetic, deliberately;
  anything that reorders the `min` or folds the cap into it changes the rocket
  equation. ✅  `1.21.2` rewrote the inside of that branch and re-proved the
  outside of it: **16,000 randomised comparisons over five phases, on raw IEEE
  bit patterns, zero differences**, covering `want_phase` as well because the
  sizing path is what uses it. That is the check to repeat, not to argue.
- 🚨  **THE TIERED WALK ASSUMES A PHASE'S FULL-PRICE TIER IS REACHED FIRST**
  (v1.22.0). It identifies that tier as "the first time this phase appears in
  the walk", which is the same question as "the dearer of its two tiers" only
  while `surplus_price_fraction <= 1.0`. Above 1.0 the discounted tier sorts
  first, draws the market allowance, and the capped load comes out worth MORE
  than the uncapped one -- measured at 1.5 as 945,000 against an uncapped
  900,000, which inverts the invariant `verify.py` check 7 exists to enforce.
  Clamped in `optimal_payload_mix`, clamped again where `surplus_frac` is
  resolved, and REFUSED outright by `market_config_check`. **Do not "simplify"
  any of the three away**, and if you ever give the two tiers independent
  prices rather than one fraction, this assumption is the thing that breaks.
- ⚠️  **The tier ledger is written BEFORE the `take <= 0` skip**, deliberately.
  A full-price tier whose allowance is already spent takes nothing, and if it
  went unrecorded its own surplus tier would be read as the full-price one and
  clipped at the same exhausted allowance -- so the discount would silently
  never fire on exactly the phases it exists for.
- 🚨  **`caps` IS KEYED BY MARKET, NOT BY PHASE, AND THE WALK CONSUMES IT**
  (`1.21.2`). Two phases can sell into one market -- `silicates` and the
  composition residual do, on every body -- and a dict keyed by phase hands
  each of them the whole ceiling. Pass a dict you own; it is decremented as it
  is spent. Build the keys with `phase_market_key`, never with
  `_PHASE_MARKET_ALIAS` directly: that function prefers a phase's own Stage 2
  row and falls back to the alias, which is exactly what `phase_market_kg`
  does, and the two agreeing is what stops a future aliased phase pooling onto
  one key while drawing a different ceiling.

### Where a cache is safe, and where it is not

`1.17.7` bounded the one memo in the module keyed on a **per-candidate float**,
which had grown at ~45 entries per catalog row and projected to **11-18 GB** on
a full-catalog default cell against a documented ~6 GB run peak. Every other
memo is bounded by its key space: (N, rate) pairs, ~25 composition tuples, a
handful of ladder rungs, one destination string.

**The rule the two cases give you: `maxsize=None` is safe exactly when you can
name the ceiling. If you cannot, bound it.** A replay of the real key sequence
showed the hit rate flat at 83.9% from unbounded down to `maxsize=64`, because
all reuse is local to one candidate, and a bounded `lru_cache` is not
measurably slower than an unbounded one.

🚨  **It survived three releases because no full-catalog run was made in them.**
A 400-row verification cell shows 18,000 entries rather than 70 million. **A
stride sample does not predict a full run's MEMORY either**, which is the third
quantity THE SAMPLING RULE turns out to cover.

## The verification harness is committed now

`verify.py`, at the repo root. It is the six checks every release in
`versions.md` argues from, written down once. **What they are and how to run
them is in [README.md](README.md#verifying-a-change)**; what is here is why it
exists and how it fails.

```bash
py verify.py baseline --tag 1.17.7   # on a clean tree, BEFORE editing
py build_master.py
py verify.py check --tag 1.17.7
```

🚨  **A `check` with no baseline used to print `ALL CHECKS PASSED`.**
Check 1 skipped any cell absent from the baseline with a `continue` that never
touched `ok`, so a missing or partial baseline meant the most important of the
six compared *nothing* and the run still announced success. It now reports
`*** NOT VERIFIED ***`, names the cells, and exits 1. Two sibling cases went
the same way and are fixed with it: an empty cell in the mass ledger printed
`(no rows)` and passed, and a never-worse comparison whose join came back
empty was skipped silently; both of which are the regression, not the absence
of one. **A check that cannot run must never say it passed.**

⚠️  A full `check` takes **roughly half an hour**, most of it check 2, since
turning the pre-filter off is precisely what `1.14.1` and `1.17.4` exist to
avoid. **`--skip prune parallel` is the ~5 minute loop**; see
[README.md](README.md#verifying-a-change) for the flags. **A verification you
will not run is worse than a slow one.**

🚨  **THE REASON IT EXISTS IS IN THIS FILE, ONCE PER ROW OF THE TABLE BELOW.**
Every release before 2026-08-21 rebuilt these checks from memory and threw them
away, and the release notes record what that cost. **Three produced a wrong
conclusion that was written down or acted on before being caught, and three more
would have condemned a release that had changed nothing:**

| release | the harness bug | what it looked like |
|---|---|---|
| `1.15.0` | destination not set explicitly | two cells recorded as `cislunar` that ran against `earth_surface` prices |
| `1.15.0` | brute-force sweep truncated at N = 24 | a capped search read as a counter-example to the thing it was capping |
| `1.17.1` | parquet round trip renders `None` as `nan` | three identical object columns compared as different |
| `1.17.3` | only `pipeline_version` stripped | midnight falling mid-run read as a defect confined to the beneficiation path |
| `1.17.4` | `spec_from_file_location` instead of `import master` | `ImportError` in every worker; the harness re-ran itself once per core |
| `1.17.5` | `mining_hardware_kg` read as a column | `KeyError`; the rig is a config constant |
| `1.17.7` | `cost_revenue_ratio` | no such column; the objective is `total_cost_usd / gross_value_usd` |
| `1.17.7` | `median(1/r − 1)` | 74.0% where the committed convention reads 42.5% |
| `1.17.7` | two Series compared directly | **every float column DIFFER while the file hashed MATCH** |
| `1.17.7` | `read_csv` without `float_precision="round_trip"` | **the same symptom again, from a different cause** |
| `1.17.7` | `""` compared as different from `NaN` | **and again, from a third** |
| `1.21.0` | `market_model` not reset in `run_cell` | **a baseline labelled "the new default" that was entirely `elasticity`** |
| `1.22.0` | `dtype == object` on **pandas 3.0** | **five text columns DIFFER while the hashes MATCH** -- a text column now reads back as an Arrow-backed `StringDtype` |
| `1.22.0` | a build compared against one with an EXTRA column | every cell DIFFER, on a release that had changed nothing in them |

🚨  **THE FIRST `1.22.0` ENTRY IS THE SAME SYMPTOM FOR A FOURTH CAUSE, AND
IT IS THE ONE THE ENVIRONMENT CAN REINTRODUCE UNDER YOU.** The three `1.17.7`
rows are index alignment, a float parser and `""` against `NaN`; this is a
`dtype` test that was correct when it was written. `pandas` 3.0 infers a plain
text column as an Arrow-backed `str` where 2.x gives `object`, so
`col.dtype == object` silently became False for every text column and they all
fell through to the numeric comparison. **Test `dtype.kind in "OU"` or the
dtype's name, never `== object`**, and note the tell was the usual one: the
hash and the column diff disagreed, and the hash was right.

⚠️  **THE SECOND IS THIS RELEASE'S OWN AND IS NOT A DTYPE PROBLEM AT ALL.** A
release that ADDS an output column cannot be verified by hashing the whole
frame against the previous build, because the frame is a column wider by
construction and the hash is guaranteed to differ. The A/B reported
`*** DIFFER ***` on all four cells of a configuration later proved identical on
142 of 142 shared columns. **Hash the shared column set and NAME it**, and
treat "every cell differs at once" as the tell it has always been: a real
defect almost never does that.

🚨  **THE `1.21.0` ENTRY IS TRAP 1 ARRIVING A SECOND TIME, AND IT IS THE
ARGUMENT FOR TREATING `run_cell`'s RESET LIST AS A CONTRACT.** `run_cell` sets
four fields explicitly and takes the rest from `CELLS`. A field in neither is
whatever the previous cell left on the live config, so once a harness ran one
cell with `market_model="elasticity"`, every later plain `run_cell(m, name)` in
that process silently inherited it. Nothing raised and the hashes looked
plausible; what caught it was **two checks contradicting each other about one
population** -- 66 rows reported as bound by a ceiling beside a frame whose
minimum clearing fraction was 1.0000.

✅  **The general rule: when a release makes a config field something a cell can
DIFFER on, that field joins the explicit resets.** Before `1.21.0` there was
nothing to reset, because nothing varied it. Trap 1 was the same sentence about
`delivery_destination`, and the fix is the same one: set it explicitly, and read
the default off the dataclass rather than typing it.

⚠️  **And the tell generalises.** Neither check was wrong on its own terms;
they were wrong TOGETHER, and only an invariant that spans two of them could
see it. That is an argument for checks whose outputs overlap, which is also why
this harness prints a hash AND a column diff.

The last five are this release's own, hit while reconstructing the harness, 
five fresh bugs in one sitting, in a harness that had already been written
seven times. That is the argument, and it is empirical rather than
tidy-minded.

🚨  **THE LAST THREE ARE THE SHARPEST, THEY PRODUCE THE IDENTICAL SYMPTOM, AND
EACH HAD TO BE DIAGNOSED SEPARATELY; FIXING ONE MOVED THE COUNT AND NOTHING
ELSE.** In sequence, the same four cells reported:

```
75/139 identical | f3dbd86ee6d35fc0 | DIFFER dv_out_m_s, mission_duration_yr, …
137/139 identical | f3dbd86ee6d35fc0 | DIFFER payload_mix, payload_dominant_phase
139/139 identical | f3dbd86ee6d35fc0 | MATCH
```

**The hash never moved. All three readings were of the same four byte-identical
files**, against hashes committed for v1.17.4 and v1.17.6. The three causes:

1. **Index alignment.** `build_profitability_catalog` returns its rows
   **sorted by the objective**, so a live frame carries a scrambled index while
   the same frame re-read from CSV carries a fresh `RangeIndex`, and comparing
   two Series directly makes pandas align on the index **label**, not position.
2. **`read_csv`'s default float parser is not correctly rounded.** It is a fast
   reader, and it returns a float64 one ULP from the one written:
   `119898.18458829961` comes back as `119898.1845882996`. **Neither the
   default nor `float_precision="high"` round-trips; only `"round_trip"`
   does.** Same family as the pyarrow CSV engine v1.17.4 measured at 4.8× and
   rejected for moving `estimated_mass_kg` by 1e-13 relative: *a different
   float parser rounds differently in the last bit.*
3. **The empty string is not `NaN`, except that in a CSV it is.** An all-empty
   object column; `payload_mix` and `payload_dominant_phase` are empty on
   every row of a raw cell; writes as bare commas and reads back as
   **float64-of-NaN**, so a live `""` met a `nan`. A CSV cannot represent the
   difference, so the file's own hash cannot see it either; **a comparator
   stricter than the artefact it compares reports failures that do not exist.**

⚠️  **Point 2 says nothing about the pipeline, and must not be "fixed" there.**
`load_all_catalogs` reads with the default parser too, so the model's inputs go
through the same slightly-inexact reader on every run, which is
**deterministic**, and is therefore part of why bit-identity holds at all.
Setting `float_precision="round_trip"` in Stage 4's loader would move every
number in the model. It belongs in the *comparison*, not in the load.

Together these are v1.17.1's "a broken checker looks exactly like a broken
release" for the second and third time, and they are why this harness reports
**a hash AND a column diff** rather than either alone: **when the two disagree,
the hash is the one that is right**, and the disagreement is itself the signal
that the comparator is broken. A column diff alone would have condemned a
release that had changed nothing. A hash alone would not name the column when
something genuinely does move.

Every one of those is now defended against **at the line that would otherwise
reproduce it**, and `verify.py`'s header carries the list. ⚠️  **Add to that
list rather than starting another harness.**

✅  **It reproduces the four cell hashes committed for `1.17.4` and `1.17.6`
exactly**: `f3dbd86ee6d35fc0` / `3c809fb067c8d034` / `9bb6c8bb41852b66` /
`1d5823f859478c74`. That is what makes it a *replacement* for those harnesses
rather than another one to have to trust, and it is why `_comparable()`
deliberately does **not** sort columns: sorting would be tidier and would
silently make every hash it prints incomparable with the eight already in this
file.

⚠️  **It does not re-run Stages 1-3, deliberately.** A Stage 1 run fetches a
different catalog (JPL adds bodies daily) and a Stage 3 run re-fetches live
prices; either moves the inputs underneath the comparison. This is the same
reasoning catalog `1.1.1` used when it verified `enrich_composition` in-process
against the on-disk catalog rather than by re-running Stage 1.

⚠️  **The two never-worse comparisons run their own cells at a matched cap**
(400), because both join two runs on `designation`, and the four bit-identity
cells deliberately do *not* share a cap, since beneficiated is ~7× raw and runs
at 150. Joining a 400-row raw cell to a 150-row beneficiated one silently
compares 65 pairs and reports them as though they were the population. That
trap is one careless join away from being the twelfth entry in the table above.

### 🚨  RUNNING STAGE 2 OR STAGE 3 DESTROYS EVERY BASELINE YOU HOLD

The note directly above says `verify.py` will not re-run Stages 1-3 because
they move the inputs underneath a comparison. **That is not only a rule for the
harness. It is a rule for you**, and it was broken on 2026-08-23 by a single
throwaway command:

```
py run_pipeline.py --stages 2 ...       # just to look at the banner
```

Stage 2 re-fetched live metal prices, rewrote `mineral_value_catalog.csv`
(previously 2026-08-11), and **the committed `.verify` baseline stopped
reproducing**: `130/139` columns identical, with
`delivered_value_usd_per_kg`, `bulk_value_usd_per_kg`,
`best_phase_usd_per_kg` and `saturation_multiplier` all differing. The previous
prices are **not recoverable**; the on-disk Stage 2 catalog is the only copy
and it had been overwritten.

Three things worth keeping:

- **It looks exactly like a code regression.** Four cells failing bit-identity
  on nine value columns is the signature of a broken release, and the cause was
  an unrelated command run minutes earlier. This is the `catalog_date` lesson of
  `1.17.3` one level up: *the comparison broke, not the model.*
- **The mass and mission columns were untouched**: 130 of 139 identical, and
  every differing column downstream of price. That split is the diagnosis, and
  it is why a column-by-column diff earns its keep against a bare hash.
- **The fix is to re-isolate, not to argue.** Stash the change, baseline the
  **pre-change** build against the *same* refreshed catalog, restore, and
  re-check: `139/139` on all four cells. Comparing two builds against identical
  inputs is the only construction that answers the question once an input has
  moved.

**So: never run Stage 1, 2 or 3 to test an unrelated thing.** Use
`--stages 4`, which reads the CSVs already on disk. If you need to see a banner
or a config, run a stage that writes nothing, or read the code. And if you are
about to touch Stages 1-3 deliberately, copy `asteroid_pipeline/*.csv`
somewhere first, because nothing else will.

🚨  **IT HAPPENED AGAIN THE SAME DAY, WHILE AUDITING FOR BUGS, AND THAT IS
WHY THERE IS NOW A GUARD.** Testing `run_pipeline.py`'s *argument parsing*,
somebody ran `--stages 2,4` and `--stages 234 --destination leo` as throwaway
checks that the new comma/space separators parsed. They parsed, and then the
run went on to re-price the entire catalog for `leo`. The tell was not a
failing check but `verify.py` reporting a destination mismatch minutes later.

Two things make this worth recording rather than filing under carelessness:

- **The command looked like a parser test.** `--stages 2,4` reads as "does the
  comma work", and the answer arrives in the banner, three lines before the
  fetch. `preflight()` deliberately does NOT refuse it, because Stage 2 is in
  the list and is therefore "about to re-price anyway", correct reasoning
  about consistency, and no help at all against an unintended fetch.
- **Recovery worked, and that is luck rather than design.** Re-running
  `--stages 2 --destination cislunar` restored the pricing and all four cell
  hashes reproduced exactly, because yfinance serves a daily close and the
  mistake was caught the same day. An hour later on a different date and the
  baseline would have been gone.

✅  `run_pipeline.py` now asks before any of Stages 1-3 overwrites a file that
already exists (`overwrite_warning` / `confirm_overwrite`), naming what gets
re-fetched. ⚠️  It is **not** the same question as `confirm_long_run()`: that
one asks about spending hours, this one asks about spending something you
cannot get back, and a five-second Stage 2 is exactly the case the runtime
question would wave through. Skipped by `--yes`, which `run.bat` passes on
every *scripted* invocation; typing `run.bat quick` is not incidental, and
the file's own header promises that path can be scheduled.

### Console text is not output, and did not move a stamp

The 2026-08-23 ASCII conversion rewrote **243 `print(...)` calls** across the
four modules (103 / 42 / 50 / 48) and every banner `build_master.py` emits, and
**no `pipeline_version` was bumped**. That is deliberate and follows the rule as
stated: *changing any number a run produces means bumping.* No CSV byte
changes, so a catalog stamped `calc 1.17.7` means the same model whether it was
built before or after. The stamp identifies the code that produced a **catalog**,
and console text is not in one.

⚠️  Note this cuts against `1.17.3`, which bumped for dead-code removal, and
`mineral_value 1.7.1`, which bumped while bit-identical. Both were *choices*,
not obligations: the rule is one-directional. If you would rather every source
change carry a stamp, bump it; just do not read this decision as an oversight.

### A checker with a date in it passes on exactly one day

`verify_stage3.py` went red on 2026-09-08 reporting
`*** THE ADAPTER CHANGES THE DATA ***` and `*** CONTENT MOVED ***`, on all six
tables at once, having passed that same morning. Nothing in Stage 3 had been
touched for two releases. **The date had rolled over.**

Two independent instances of one mistake, in one file:

| check | what it compared | why it could only pass on 2026-09-07 |
|---|---|---|
| 3, output | adapter build vs package build | `PINNED_DATE = "2026-09-07"` was handed to the PACKAGE side only; the adapter stamps `date.today()` |
| 4, reference | adapter build vs spacecost's COMMITTED `reference/` CSVs | those carry the `catalog_date` they were generated on, and the comparison was raw bytes |

✅  Fixed by deriving `PINNED_DATE` from the clock, so both sides stamp the same
day by construction, and by giving check 4 a `_content_sha` that drops
`catalog_date` before hashing -- which is what its own docstring had always
claimed it did ("pins the CONTENT rather than the plumbing").
`pipeline_version` is deliberately NOT dropped: it moves only when somebody
moves it, so a difference there is a finding rather than a clock.

⚠️  **The comment above the literal said "the environment pins the clock
instead". Nothing pinned the clock; there was no such mechanism.** That is
defect class 4 -- a prescriptive comment nobody applied -- and it is why a
rotting literal looked deliberate. A reader checking whether the date was
handled would have read that sentence and stopped.

🚨  **And the messages were maximally alarming for a clock.** "THE ADAPTER
CHANGES THE DATA" and "CONTENT MOVED" are what you would print for a genuine
drift in the `spacecost` split, which is the one failure this file exists to
catch. *A broken checker looks exactly like a broken release*, for the third
time in this file, and the tell was the same as always: **everything failed at
once**, which is almost never what a real defect does.

⚠️  `verify.py` strips `catalog_date` before hashing and has done since
`1.17.3`; `verify_docs.py` and `verify_stage3.py` were written later and did
not inherit the lesson. **When you add a harness, read `PROVENANCE` in
`verify.py` first.**

### A skip is not a pass, in the DOCS harness too

`verify_docs.py` checks 8 and 9 import `master` and `ui_meta`, and both caught
every exception, printed `SKIPPED` and **returned pass**. The skip is there for
a machine without the third-party dependencies, which is legitimate; it also
swallowed a **`SyntaxError` in this repo's own source**.

Found on 2026-09-08 by causing it: a malformed string literal in `ui_meta.py`
made check 8 report `SKIPPED (SyntaxError...)` and pass, and the run only went
red because an unrelated version stamp happened to be wrong at the same moment.
With the stamps clean, `verify_docs.py` would have exited **OK** on a file that
does not parse.

✅  Fixed by splitting the cases: `SyntaxError` is a FAILURE, everything else
is still a skip. Verified by breaking a file on purpose and checking the exit
code went to 1.

⚠️  **This is the same defect CLAUDE.md already records `verify.py` having
had** -- a `check` with no baseline printing `ALL CHECKS PASSED` -- in the other
harness, found the same way, two releases apart. **A check that cannot run must
never say it passed**, and the sentence applies to every harness in this repo,
not to the one it was first written about.

### A skip that says so, and still hides that it is PERMANENT

🚨  **THE THIRD INSTANCE, AND THE ONLY ONE WHOSE SKIP WAS HONEST.**
`verify_stage3.py` check 4, the half that pins the reference tables' CONTENT
rather than the plumbing, printed `SKIPPED, spacecost installed without
reference/` and returned pass. Its own docstring said "a skip that says so is
not a pass", and it was telling the truth about what it saw. It was still
wrong, because **`reference/` sits at spacecost's REPO root, not inside the
package**, so `pip install git+...` leaves it behind *every time*. The skip was
not a caveat about an unusual install; it was the normal case, and **the check
had never run at all.**

✅  Fixed on 2026-09-08 by looking for a source checkout, in `SPACECOST_SOURCE`
and then beside this repo. It found one, ran for the first time, and all five
tables matched.

⚠️  **The revision has to be PROVEN, and that is the half that is easy to
skip.** The checkout beside this repo was **two commits past `v0.1.1`**, the
tag `requirements.txt` pins. Comparing against it blind would be the
parallel-repo divergence wearing a green check. So the tag is read from
`requirements.txt`, `reference/` is diffed against it with git, and the three
outcomes are kept distinct: **matching** runs the check and names the tag,
**absent** stays a skip that says what would make it run, and **differing is a
FAILURE**, because a `reference/` that has moved since the pinned tag is
exactly the drift this file exists to catch. Only `reference/` must match; the
two commits in question were docs and tests, and refusing over those would make
the check unrunnable for no gain.

✅  **The general rule, which the first two instances do not give you: a skip
is not a pass, AND a skip you have read is not a skip you have measured.** Both
earlier instances were skips that fired rarely and hid a defect when they did.
This one fired *always*, and the message was accurate every time. **Ask how
often a skip fires, not only whether it explains itself** -- a skip that fires
on 100% of runs is a check that does not exist, however well it is worded.

## Stage 3 lives in another repository now

`modules/transportation.py` is an adapter. Every reference row, all 141 of
them, is in [`spacecost`](https://github.com/loggger101/spacecost), pinned to
tag `v0.1.1` in `requirements.txt` and in `_MASTER_REQUIRED`.

🚨  **THIS PROJECT HAS ALREADY BEEN BURNED BY A SPLIT, AND THE LESSON WAS NOT
"DO NOT SPLIT".** It was developed in two places at once and `1.0.6` / `1.1.4` /
`1.3.6` each shipped as two different things; see
[the parallel-repo divergence](versions.md#the-parallel-repo-divergence). What
made that expensive is that **nothing checked it**. So this split is arranged
so that drift cannot be committed:

| | how it is held | what fails |
|---|---|---|
| the **data** | one copy, in spacecost; this repo holds none | nothing can drift |
| the **dials** | ten fields, mirrored, compared at import time | `_check_config_surface()` raises, so the import fails, not the run |
| the **output** | six CSVs, byte for byte, both paths | `verify_stage3.py`, which names the file and the side |

⚠️  **The dials are the mirrored surface, and they are mirrored on purpose.**
Two of the ten defaults are this project's rather than a library's:
`output_dir` points into `asteroid_pipeline/`, and `use_yfinance` is **True**
here and **False** in spacecost, because a pipeline stage is expected to fetch
and a library must not. That is why `TransportConfig` did not move, and why the
field-set assertion exists.

⚠️  **`ui_meta` scrapes `TransportConfig`'s comments for the dashboard's help
text**, which is the other reason it stayed. Move it and 10 dials lose their
help and `verify_docs.py` check 8 goes red. If you ever do move it, repoint
`CONFIG_SOURCES["transport"]` at spacecost's `config.py` in the same commit.

✅  **`pipeline_version` did NOT move, and that was a decision.** The stamp
identifies the DATA; the data did not change; spacecost's data-contract version
is the same `1.14.0`. Bumping it would have desynchronised every archived
catalog in order to announce a refactor. The **master** version moved instead,
`1.24.0` → `1.25.0`, which is where a structural change belongs.

⚠️  **`master.py` lost roughly a quarter of its lines** -- the build prints the
real number, and this file does not state one, for the reason given under
"master.py is generated" -- **and it is no longer self-contained in the "pure
PyPI" sense**: it pip-installs spacecost from a git URL at import. That is the trade the dependency buys. **Pin the tag.** An
untagged URL would let a fresh Colab paste install a different table with
nothing in this repo moving, which is the same failure the divergence was.

## Config discipline

Configs are dataclasses instantiated once at module scope. Edit the field
default *inside* the dataclass, not the instance afterwards, mutating
`CONFIG.foo` after construction defeats having one editable source of truth,
and every module says so in a comment.

🚨  **A FIELD'S COMMENT IS ITS UI HELP TEXT, AND THE ATTACHMENT RULE IS
POSITIONAL.** `ui_meta.scrape_field_docs` walks *upward* from a field to the
comment block directly above it, stopping at the first blank line or section
banner, and also reads a trailing comment on the field's own line. So a comment
block that explains **two** fields but sits above only the first leaves the
second with **no help at all in the dashboard**, and the reader sees a bare
number exactly where they are most likely to change one:

| the documented field | the silent one beside it |
|---|---|
| `market_model` (was `model_market_saturation`) | `demand_elasticity`, the ε the block defines |
| `allow_rtg_power` | `rtg_max_power_w`, the Pu-238 cap the block describes |
| `mining_hardware_kg` | `return_vehicle_dry_kg`, which the block also explains |
| `charge_tanker_flights` | `escape_direct_launch`, the flag that gates it |

**Thirty-nine of 105 fields were in that state**, and the fix is per field, not
one edit: give the second field its own block above (preceded by a blank line
so it does not merge upward) or a **single-line** trailing comment.

⚠️  **A trailing comment cannot be continued onto the next line.** A `#` line
below a field is a *block* comment belonging to whatever field comes next, so
a two-line trailing comment loses its own second half **and prepends it to the
neighbour**. That was introduced and caught while closing the gap above.

✅  **Every non-path field carries help now, and `verify_docs.py` check 8
keeps it that way**: it builds the real UI specs and fails on any field outside
`PATH_FIELDS` whose help is empty. Add a config field without a comment and the
docs check goes red before anyone opens the dashboard.

## Correctness invariants that were expensive to find

Undoing any of these silently corrupts the output:

- **Designation extraction** must not use a naive `^\d+` regex. For
  `"2024 BX1"` that yields `"2024"`, which cross-matches unrelated bodies.
  See `_extract_canonical_designation` in `catalog.py`.
- **Never build a merge key by stringifying a float column.** A numeric
  identifier that pandas has typed `float64` renders as `"3.0"`, which is not
  null, not obviously wrong, and joins nothing. Go through `Int64` first. This
  cost NEOWISE four releases of contributing zero rows, and note the shape,
  because it generalises past this one column: **the dtype depends on the
  data**, so a source that returns only numbered bodies in a small test slice
  is `int64` and works, and the same code silently breaks the moment one
  unnumbered row appears. Anything that tests clean at a small row cap and is
  only ever run at a large one is a candidate for this. See the v1.1.0 entry.
- **`str.contains` needs `regex=False`** in every lookup helper. Designations
  and mineral names carry regex metacharacters, so `"(1) Ceres"` matched
  `"1 Ceres"` and unbalanced brackets raised `re.PatternError`.
- **TPS mass belongs inside the rocket-equation cascade**, not just in the
  cost model. It is hauled outbound as dead mass and pushed back through the
  return burn. Omitting it overstates max payload by ~30%.
- **The return-capsule volume cap must bind**, not merely be reported. It is
  the only constraint keeping the mission physical when ISRU is on and
  aerocapture is off.
- **Composition fractions sum to 0.76-0.96**, not 1.0. The residual is valued
  at a bulk-silicate floor rather than zero.
- Do not globally suppress warnings in `catalog.py`, real `RuntimeWarning`s
  (divide-by-zero in the derived physical columns) need to stay visible.
- **Never use `.astype(bool)` on a flag that arrives through a CSV.** It reads
  the *string* `"False"` as `True` and `NaN` as `True`. It happens to be
  correct today only because every propellant row states `restartable` and
  `propellantless`, so pandas infers dtype `bool`; add one row that omits
  either and a solid motor silently rejoins the search, with no error
  anywhere. Use `_truthy(series, default=...)`, which parses the strings and
  makes you say what a *missing* value means instead of letting truthiness
  decide. Same shape as the `str.contains` / `regex=False` trap above: the
  wrong behaviour is the quiet one.

  ⚠️  **"through a CSV" was too narrow, and the second instance was in
  `transportation.py` for eight releases.** `validate()` selected both
  propellant sanity bands with `~propellant_df["propellantless"].astype(bool)`,
  on a frame built in-module from Python bools, so the *string* half of the
  trap could not fire, but the **NaN half could**, and it is the half that
  matters here: a row omitting the flag would be classed as a sail and dropped
  from the Isp band and the price band at once, i.e. the checks would stop
  covering exactly the row most likely to be new and wrong. Fixed in
  transportation `1.12.1` with `.ne(True)`, resolved once into
  `has_mass_ratio` rather than written out at both bands, deliberately not
  `.fillna(False).astype(bool)`, which raises a pandas `FutureWarning` on an
  object column, i.e. exactly when it would fire. **The rule is
  about the DTYPE being inferred from the data, not about where the data came
  from**: any `.astype(bool)` on a column that a future row could leave blank
  is the same bug.
- **Re-run Stage 3 after upgrading it**, where "upgrading it" now means moving
  the pinned `spacecost` tag. Every Module 3 column Module 4 reads
  is read defensively, so a stale `propellants.csv` does not raise; it
  reverts tank mass to zero, drops the maturity gate, and un-excludes solids
  and sails, all silently. `schema_check()` in `calc.py` now names each
  missing column and the behaviour it reverts; do not weaken it into a
  generic "columns changed" warning, because the consequence is the useful
  part.

  ⚠️  **`schema_check()` checks COLUMNS, not VALUES.** It checks Module 3
  **rows** as well since v1.14.0; the ops table is keyed by category, so a
  missing *figure* was invisible to a column test, and `_MODULE3_REQUIRED_OPS`
  now names each row Stage 4 needs alongside the model term its absence
  silently reverts. That closed the missing-row half.

  🚨  **A MODULE 3 TABLE IS NOW A `spacecost` EDIT, AND THAT IS FOUR STEPS, NOT
  ONE.** Change the row there, bump its `pipeline_version` if the number moves,
  cut a release and a tag, then repin the tag **here** in `requirements.txt`
  and `_MASTER_REQUIRED` and rebuild `master.py`. Skip the repin and this repo
  keeps installing the old tag, so the edit silently does not land -- the same
  failure the paragraph below describes, with a new way to reach it.
  `verify_stage3.py` catches it: it compares against the installed package.

  Editing a number in a Module 3 table, a density, a status, a boil-off rate,
  leaves the schema identical, so nothing warned and Stage 4 quietly ran on
  the old figure. This cost a full measurement pass during v1.12.0: the argon
  rows were rewritten, Stage 3 was re-run, the CSV did not actually land, and
  two full-catalog runs plus a determinism sweep were measured against the
  table that was being replaced. Nothing anywhere said so.

  ✅  **`stamp_check()` closes that half as of calc `1.17.8`.** Every stage has
  stamped its own `pipeline_version` into every CSV it writes all along, and
  nothing had ever read it back; the loader now compares that stamp against the
  module that WROTE it and shouts, naming each stale file and its stage. It
  needed no new column, and it makes the one-directional bump rule
  self-enforcing: follow it, and a write that silently fails to land is caught
  on the next run.

  🚨  **AND IT SPENT TWO RELEASES COMPARING EVERY CATALOG AGAINST MODULE 3,
  INCLUDING THE TWO MODULE 3 DID NOT WRITE.** `catalogs` holds `asteroids` and
  `minerals` as well as the four Stage 3 tables, so it fired on **every run**,
  named the wrong module, and closed with "Re-run Stage 3 (transportation)".
  That is the action the section titled "RUNNING STAGE 2 OR STAGE 3 DESTROYS
  EVERY BASELINE YOU HOLD" exists to prevent. **A check that cries wolf toward
  a destructive remedy is worse than no check**, and the generalisation is the
  one this file already makes about harnesses: *a broken checker looks exactly
  like a broken release*. Fixed in calc `1.19.1` with `_CATALOG_PROVENANCE`,
  which `load_all_catalogs` asserts against the dict it actually builds.

  ⚠️  **Three limits, all deliberate.** It is a *diagnostic, not an import*, so
  it is silent in a standalone `calc.py` run where the upstream configs do not
  exist, rather than inventing a complaint it cannot support. It cannot see
  **an edit that did not bump the version**; what it closes is the case where
  the discipline was followed and the CSV did not land. And **it cannot tell a
  deliberate lag from a failed write** -- catalog `1.1.1` and transportation
  `1.12.1` both changed no CSV byte and chose not to re-run their stage, so the
  check fires on them correctly and means nothing by it. That is why it now
  reports the fact and points at the release note instead of prescribing a
  fix.

  The cheap habit that catches it: **Stage 4's loader prints row counts for
  every Module 3 table it reads** (`Module 3 propellants  41 rows`). Read
  those against what Stage 3 said it wrote. A count that has not moved after
  you added a row is the whole diagnosis. When only values changed and no
  count moved, spot-check the field itself out of the CSV before trusting a
  number, one `read_csv` on the row you edited.

  The deeper lesson from that pass is in
  [calc v1.12.0](versions.md#calc-v1120--transportation-v1100): the headline
  cislunar ratios were **bit-identical** with the stale table and the correct
  one, because the best mission was not affected by the change. A best-case
  cell is a poor detector for anything wrong below the top; the
  propellant-share breakdown and the evaluable-row count are what caught it.

## Data sources fail softly by design

Unreachable or empty sources are tolerated and the run continues. MP3C is
regularly DNS-blocked from Colab. Do not "fix" an empty source by flipping its
toggle off; the toggle is for deliberately excluding a source, not for
routing around an outage.

`metals.dev` defaults to the key `"DEMO"`, which makes the fetcher skip
entirely. That is intentional; the demo endpoint is heavily rate-limited.

**But a soft failure silently changes the population you are measuring, and
that will invalidate a comparison without warning.** Missing spectral types
are backfilled by inferring a coarse type from albedo, so an outage does not
shrink the catalog; it *inflates* it with guessed taxonomy.

Check `spectral_type_source` (`source` / `tholen` / `albedo` / `albedo_assumed`
/ `unknown`) before comparing any run to a committed number. The startup
banner's "Active sources" line lists what was *enabled*, not what answered; 
read the `Source summary: {...}` dict instead.

⚠️  **`Source summary` reports what was FETCHED, not what was USED, and the gap
between those is where NEOWISE hid for four releases.** It printed 183,408 on
runs where the source contributed zero rows, because the failure was in the
merge key rather than the fetch. Since v1.1.0 `merge_sources` also reports how
many of each supplement's designations **matched the backbone**, and shouts
when that number is zero or when a source loses every row to keying. Read the
`Merged <source>: N supplement records (M matched the backbone, +K new
entries)` line, `M = 0` on a source that fetched rows is always a bug in that
fetcher, never an empty upstream table.

The corresponding check on the output CSV is one line, and it is worth running
against any catalog you did not watch being built:

```bash
py -c "import pandas as pd; d=pd.read_csv('asteroid_pipeline/asteroid_catalog.csv',low_memory=False); print({c:int(d[c].notna().sum()) for c in d.columns if c.startswith('source_')})"
```

A `source_*` column sitting at 0 while its fetcher reported success is the
signature.

⚠️  **Two upstream sources fetched ZERO rows on the run that produced the
committed cislunar 2x2, and it did not matter, but check before assuming that
of the next one.** IRSA (NEOWISE) returned `502 Proxy Error` all evening and
MP3C contributed nothing, so `Source summary` read
`{'JPL SBDB': 1555569, 'SsODNet': 1552868, 'NEOWISE': 0, 'MP3C': 0}`. The
catalog was unharmed, and **the provenance columns are what say so rather than
the row count**: measured diameters 149,590, taxonomy from a source 171,007,
taxonomy-albedo derivations 105,905, all three identical to the committed
v1.1.0 figures.

✅  **That outage also quantified what NEOWISE is worth here, which nobody had
measured.** `diameter_source = derived_h_measured_albedo` is **20 rows of
1,555,667**. A body with a measured albedo almost always has a measured
diameter too, both falling out of the same thermal-IR fit, so the `albedo`
column NEOWISE fills is nearly never the one `_albedo_for_derivation` reads.
The v1.1.0 note that NEOWISE recovers IR albedo "for 132,691 bodies that had
none" is about **columns**, and it reads as though those 132,691 rows were
sized off it. They are not; 20 are.

### The SsODNet outage that wasn't an outage (fixed in v1.0.9)

This one is worth reading in full, because nothing about it looked wrong.

ssoBFT renamed its identity columns; `sso_number`/`sso_name`/`sso_id` became
`number`/`name`/`id`. The column projection tolerated the loss, so
`fetch_ssodnet` cheerfully returned 50,000 rows with no `designation`, and
`merge_sources` dropped the entire source behind one ⚠️ line. A ~500 MB
download, and every literature diameter, density, rotation and taxonomy in it,
went in the bin on every run. The damage:

| | before | after |
|---|---|---|
| taxonomy measured | 1,854 | **24,675** |
| taxonomy guessed from albedo | 33,235 | **11,131** |
| density measured | 0 | **438** |
| V-type bodies | 3,988 | 2,614 |

**Every number committed before v1.0.9 was measured on the degraded catalog**,
roughly 1,900 real-taxonomy bodies instead of ~24,700. The V-type count is
the tell: V-types are rare, and 3,988 of them was an artefact of guessing
taxonomy from albedo.

Three separate things kept it quiet, and each is a trap worth not rebuilding:

- **The drift warning only fired when fewer than 5 of 24 columns matched.**
  Fourteen still matched, so losing every merge key read as healthy. A
  projection that tolerates missing columns must still *assert* the ones it
  cannot work without; that is what `_SSODNET_REQUIRED` is for now.
- **The row-cap sort key sat behind an `if in df.columns` guard**, so
  truncation silently stopped sorting and took an arbitrary 50,000 rows
  starting near asteroid 367488 instead of Ceres. A guard that turns a wrong
  answer into a quiet one is worse than no guard.
- **`pq.ParquetFile.schema` is the PHYSICAL parquet schema**, which names a
  nested list column by its inner path, so `spins.period.value` read as
  absent. Test membership against `schema_arrow`; that is what
  `read(columns=…)` accepts.

**Spot-check against literature rather than trusting row counts.** These five
are the standing check, and they reproduced exactly on the full 1,554,400-row
catalog after the v1.1.0 rebuild:

| body | diameter km | density g/cm³ | rotation h | type |
|---|---|---|---|---|
| Ceres | 939.400 | 2.162 | 9.074 | C |
| Vesta | 522.770 | 3.411 | 5.342 | V |
| Pallas | 513.000 | 2.911 | 7.813 | B |
| Psyche | 222.000 | 4.143 | 4.196 | X |
| Eros | - | - | 5.270 | S |

⚠️  All five must also report `diameter_source = measured`. That is the check
that H-derivation is not overwriting a measurement, and it is the half a
row-count comparison cannot see.

## Google Drive makes the tree look dirty: run the hooks

🚨  **FIRST, CHECK WHICH WORKING COPY YOU ARE IN.** This section describes a
checkout on a Drive File Stream mount whose `.git` is a **one-line pointer
file** at an external git directory. A plain clone somewhere else, with a real
`.git` directory, has neither the stat-cache bug nor any need for the hooks,
and the two are trivial to tell apart:

```bash
ls -d .git && cat .git 2>/dev/null   # "gitdir: ..." means the Drive setup
git rev-parse --show-toplevel
```

⚠️  **More than one working copy of this repo is the documented divergence
hazard, not a convenience.** The project was once developed in two places at
once and `1.0.6` / `1.1.4` / `1.3.6` each shipped as two different things; see
[the parallel-repo divergence](versions.md#the-parallel-repo-divergence). A
second checkout that is many merges behind will happily rebuild `master.py`
from *its* modules and produce a CSV stamped with a version that means
something else. **Before building or measuring anywhere, confirm the branch and
that it is up to date with the remote.**

Symptom: `git status` reports files as modified, `git diff` shows nothing,
and every blob hash matches. Then `git checkout` or `git merge --ff-only`
aborts with *"your local changes would be overwritten"*, so a merged PR
silently fails to land locally. This bit twice before it was diagnosed.

Cause: Drive File Stream reports a **placeholder size of 16384 bytes** when
git stats a file right after writing it during checkout. Git caches that in
the index stat:

```
git ls-files --debug master.py   ->  size: 16384
ls -l master.py                  ->  328335
```

Every later `status` sees the mismatch and reports modified *without reading
the file*; a differing size is normally conclusive proof of a change. That is
exactly why `diff` and `status` disagree, and why
`git update-index --refresh` refuses to fix it.

It is **not** a stat-metadata problem. `core.checkStat=minimal`,
`core.trustctime=false` and `core.fscache=false` were each tried and none of
them help; don't re-add them.

Fix: `.githooks/drive-restat.sh` re-stats entries whose content already
matches the index, wired to `post-checkout`, `post-merge` and `post-rewrite`.
A fresh clone must opt in once:

```bash
git config core.hooksPath .githooks
```

Run it by hand any time the tree looks wrong:

```bash
sh .githooks/drive-restat.sh
```

It only touches files whose hash already equals the index blob, so it cannot
stage, hide, or discard a real edit. If things are badly tangled, the
heavier reset is to delete the index and rebuild it, safe when the working
tree already matches HEAD, and it discards staging only:

```bash
rm -f "$(git rev-parse --git-dir)/index" && git reset
```

A checkout that moves *back* to a commit predating the hooks deletes them
mid-checkout, so they can't run, repair by hand afterwards.

## Environment

Windows, invoked as `py` (a bare `python` hits the Microsoft Store alias and
fails). The working tree is on Google Drive with the git directory outside it;
see the README's "Working copy" section, especially if the folder gets renamed
again.

🚨  **THE INTERPRETER VERSION IS NOT STATED HERE ANY MORE, AND THAT IS THE
FIX.** This paragraph has now been wrong in **three** directions inside a week.
It said 3.14 while 3.13 was installed; was corrected on 2026-09-03 with a 🚨
block insisting "3.14 HAS NEVER BEEN INSTALLED ON THIS MACHINE" and quoting
`py -0` as proof; that correction was itself false within the day, because a
3.14.6 install had appeared and `py` resolved to it; and by **2026-09-08** the
3.14 install was **gone again** and `py` was back to 3.13. Three corrections in
six days is the argument for deleting the number rather than fixing it a fourth
time. **Ask the machine:**

```bash
py -VV && py -0
py platform_check.py     # prints the running versions beside the reference host's
```

⚠️  **The libraries move with the interpreter, so do not type those either.**
`platform_reference.json` records them, `requirements-lock.txt` and the
`Dockerfile` pin them, and `platform_check.py` prints the running set beside
the reference set on every run. The one thing worth knowing without running it
is *why* pandas is the library that matters here: pandas **3.0** infers a plain
text column as an Arrow-backed `str` where 2.x gives `object`, and every dtype
trap this file catalogues lives on that object path.

✅  **The numeric probes are what govern hash comparability**, and they are
independent of all of the above: libm, the numpy kernels, the CRLF pin and the
float round trip. When those match, cell hashes computed here are directly
comparable with the ones in `versions.md`. The performance figures in "Measured
and declined" were taken on 3.13 and stand; nothing there needs re-measuring on
account of an interpreter.

🚨  **AND `platform_check.py` SPENT FIVE DAYS FAILING ON THE HOST ITS OWN
REFERENCE FILE NAMES.** `probe_pandas_dtypes` was added on 2026-09-03 to cover
the object path, and its `str_dtype` key was recorded on the transient 3.14 /
pandas 3.0 install as **`str`** while every other key in the file, and the
`host` block declaring **3.13.9 / numpy 2.2.6 / pandas 2.3.3**, had been
recorded on 3.13. So the reference was written across **two hosts**, and the
moment 3.14 went away the file contradicted itself: a machine matching the
declared reference host exactly reported

```
*** BROKEN: these are defects, not host properties ***
  pandas.str_dtype     reference str     got object
```

and exited 1. Fixed on 2026-09-08 by re-recording on one host, which moved
**exactly that one key** and left all sixteen others byte-identical, which is
what proves the diagnosis rather than merely suggesting it.

✅  **Two rules come out of it, and the second is the general one.** A
reference file must be recorded on ONE host in ONE `--record` run; a key
hand-added later is a key from somewhere else. And **a library version is not
a defect**: `pandas.*` now has its own bucket in `report()`, so a genuine
pandas 3.0 host is told its dtype CONTRACT differs, that no edit here changes
it, that it moves no float so a hash may still MATCH, and that what it moves is
behaviour. It used to be told it was broken. *A broken checker looks exactly
like a broken release*, for the fourth time in this file, and this time the
checker was accusing the reference host of being the wrong host.

⚠️  The general lesson is the one this file makes about counts, one level up: a
**version spelled out in prose** is a number waiting to rot. It rotted into a
false alarm, then into a false all-clear. It is the one fact here the machine
answers in a second, and three files (`requirements-lock.txt`, the `Dockerfile`,
`platform_reference.json`) already derive or pin it. This sentence no longer
types it.

### Another host: Linux, and what does not travel

The campaign is moving to a DGX Spark (GB10, aarch64, Ubuntu).
[`SPARK_SETUP.md`](SPARK_SETUP.md) is the long form; four things belong here
because they are traps rather than instructions.

🚨  **`lineterminator="\r\n"` IS PINNED IN THE FIVE CSV WRITERS AND IN
`verify.py`, AND IT MUST NOT BE "CLEANED UP".** `pandas.to_csv` defaults it to
`os.linesep`, and `cell_hash` is taken over exactly that text, so every hash in
`versions.md` is a hash of CRLF. Unpin it and a byte-perfect Linux run reports
DIFFER on all four cells with every float identical: trap #12, and the same
shape as the traps in `verify.py`'s header. It reads on Linux like a Windows
leftover, which is precisely why it is called out here. On Windows the pin is a
measured no-op (`5fc52123ed1ecc3a` either way; LF gives `9f6e314f49dc64ef`).

🚨  **THE INPUTS ARE NOT IN GIT, AND THAT IS WHAT STOPS A SECOND HOST
FIRST.** `asteroid_pipeline/` is gitignored in full, so a fresh clone has the
code, the frozen Stage 2 prices under `campaign/stage2/`, and none of the
~868 MB Stage 4 reads. `preflight()` refuses that run in a second rather than
dying inside the loader, and `run_pipeline.py --check-inputs` (`./run.sh
inputs`) answers it before a campaign is queued. **Copy them; do not regenerate
them.** Stage 1 re-fetches from JPL, which adds bodies daily, so a rebuilt
catalog is a different length and comparable with nothing already measured.

⚠️  **BIT-IDENTITY IS NOT PROMISED ACROSS HOSTS AND CANNOT BE MADE SO.**
`math.exp`, `math.log` and `math.cos` are the platform libm and numpy picks SIMD
kernels per architecture; none is required by IEEE 754 to be correctly rounded.
The rocket equation is `math.exp(dv / ve)` and `estimated_mass_kg` comes out of
`np.power(10.0, -H / 5.0)`, so this is not a corner. `platform_check.py` answers
it in ten seconds against `platform_reference.json` by hashing raw IEEE bit
patterns over the model's own argument ranges, with `math.sqrt` as a control
since IEEE *does* require correct rounding there. If it reports divergence,
re-baseline on that host and compare across hosts on values with a tolerance.
**Do not file the deltas as regressions.**

⚠️  **The queue is the five measured destinations, not seven.**
`campaign/run_queue.py`'s `DESTS` holds the twenty cells of the 2026-08
campaign, and adding `mars_orbit` or `geo` is not a one-line edit: there is no
frozen Stage 2 catalog for either, and making one means a live Stage 2 run at
today's prices, which is not the 2026-08-23 pricing the other twenty share.
That is a methodology decision, not a portability gap.

### Entry points

Everything that consumes the built `master.py` sits at the repo root, because
`build_master.py` concatenates `modules/` from four explicit paths and asserts
a header/footer shape per file, so a consumer inside `modules/` would be
concatenated into the thing it consumes. **Read the `runs` column, and do not
count the rows**; this paragraph said "four consumers ... plus two launchers"
above a seven-row table, and contradicted itself eleven lines later with "the
first three import master".

| file | runs the model? | what it is |
|---|---|---|
| `run_pipeline.py` | yes | headless CLI: `--preset`, `--stages`, `--destination`, row caps |
| `ui.py` | yes | Streamlit dashboard |
| `verify.py` | yes | the six release checks |
| `verify_stage3.py` | no | the Stage 3 seam: this repo's adapter against the `spacecost` package it drives. Builds into a temp dir, needs no baseline and no network |
| `verify_docs.py` | no | the **docs** checks; it imports master and the four configs for checks 8 and 9, but never builds a stage. Count them in its own docstring rather than quoting a number here |
| `run.bat` | no | Windows launcher: a terminal menu over `run_pipeline.py`, `verify.py`, `build_master.py` and the dashboard. No model behaviour of its own |
| `_START HERE.vbs` | no | double-click entry point, starts the dashboard with no console, ever |
| `launch_ui.py` | no | what it starts: supervises `streamlit run ui.py` and owns the stop button |

The three that run the model import master **by name** with the repo on
`sys.path`, which is the only form the worker pool tolerates; see
`_spawn_environment`, and the table of harness bugs under "The verification
harness is committed now".

🚨  **THE ENTRY POINT WAS `Dashboard.vbs` UNTIL 2026-09-04.** It is
`_START HERE.vbs`, renamed for the one reason a launcher has a name at all:
Windows Explorer hides extensions by default, so what a person opening this
folder sees is the words **START HERE**, and the question "which file do I
open" stops being one. Everything that named the old file was moved with it,
and `grep -rn "Dashboard.vbs" .` is the check.

⚠️  **BOTH ODDITIES IN THAT NAME ARE LOAD-BEARING. Do not tidy either away.**
The leading underscore pins it to the top of the listing and the space is what
makes it read as an instruction rather than an identifier.

🚨  **THE PREFIX IS `_` AND NOT `!` BECAUSE `run.bat` RUNS
`setlocal EnableDelayedExpansion`.** `!` is the conventional sort-to-top
character and it is the one that breaks this. **Measured, not predicted:** two
throwaway `.bat` files, each with `setlocal EnableDelayedExpansion` and the
name written as a LITERAL, against two `.vbs` files differing only in the
prefix.

```
probe_underscore.bat   ->  PASS, the vbs ran
probe_bang.bat         ->  GUARD-MISS, the vbs never ran
```

The `!` run never reached `start` at all: it failed at `if not exist "!PROBE
NAME.vbs"`, because cmd expands `!...!` inside a line under delayed expansion
and the name it then tested for was not the name on disk. So the failure mode
is **a launcher that cannot find itself, and a fallback path taken silently**,
caused by a character chosen for a file manager. `_` has no meaning to cmd,
PowerShell or sh. ⚠️  Note it is the LITERAL in the source that breaks; passing
the same name as an argument does not, which is why a probe has to be written
the way the real caller is written.

✅  **The sort order was measured, not assumed.** Explorer sorts with
`StrCmpLogicalW` from shlwapi, which is callable directly, so the candidates
were ranked against this repo's real root listing rather than against a guess
about ASCII:

```python
import ctypes, functools, os
cmp_w = ctypes.windll.shlwapi.StrCmpLogicalW
cmp_w.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
sorted(os.listdir("."), key=functools.cmp_to_key(cmp_w))
```

Unprefixed it ranked **17th of 22**. `_`, `!`, `@`, `~`, `#`, `+` and a leading
digit all rank **1st**; `-` does not move it at all, which is the result worth
knowing, because a hyphen is the other obvious choice and Explorer's logical
sort simply ignores it. ⚠️  Folders still sort above files by default, so the
launcher is first among FILES, not first in the window.

⚠️  **The space costs two things.** Any new caller must QUOTE it, and
`run.bat`'s hand-off is the form to copy:

```
start "" wscript.exe "_START HERE.vbs"
```

The empty `""` was already there as the window title, which is what stops
`start` reading the quoted path as one; without it a quoted first argument
becomes the title and nothing launches. And a markdown link to the file would
need `%20`, which `verify_docs.py` check 4 then cannot resolve on disk, so
README names it in backticks rather than linking it. **Neither is a reason to
rename it back**, but both are reasons to reach for the existing call rather
than write a new one. ⚠️  In prose, keep it in backticks for a third reason:
a bare leading `_` opens markdown emphasis.

✅  The rename was verified by running it, not by reading it: `wscript` on the
file brought up the control window, wrote `.launcher/running.json`, and
`/_stcore/health` on the port it recorded answered `200 ok`. The `start`
quoting was verified separately, on the throwaway `.bat` and `.vbs` pair
described above, because that line is where a quoting bug would live and it is
not exercised by double-clicking the file.

⚠️  **`campaign/` holds two more ways in, and they reach the model
differently.** `campaign/run_cell.py` shells out to `run_pipeline.py` as a
SUBPROCESS, one per cell, which is why it inherits `preflight()` and cannot
hit the destination trap; `analyse.py` and `population.py` read archived CSVs
and never build a stage. If you add a Stage-4-only entry point that does not
go through `run_pipeline.py`, call `preflight()` from it.

🚨  **`campaign/worked_calculation.py` IS THE ONE CAMPAIGN SCRIPT THAT
IMPORTS MASTER, and it answers the destination trap in a way `preflight()`
cannot.** It re-derives every figure behind one finished mission and checks the
derivation against that mission's own archived row, so the destination it must
agree with is the row's and not the config's. It therefore reads
`delivery_destination` off the ROW and replaces the config to match, which is
strictly stronger than refusing a mismatch: there is nothing to refuse, because
the run being documented already chose. ⚠️  **Do not "fix" it by adding
`preflight()`**; that would make it refuse exactly the archived cells it exists
to read. It builds no stage and fetches nothing, so it cannot destroy a
baseline.
`run.bat` is a launcher only; it adds no default the pipeline does not already
have, except that its `quick` / `standard` presets cap rows and fly raw ore at
N = 1 rather than starting the tens-of-hours default cell on a double-click.

⚠️  **`launch_ui.py` deliberately imports NOTHING from this project**: not
master, not ui, not `modules/`. It spawns `streamlit run ui.py` as a child and
watches a socket. It is the one process that must not fail, so putting a 1 MB
module and a multiprocessing pool inside the supervisor would be exactly
backwards, and it means nothing here is ever a worker's `__main__`, so
`_spawn_environment` never comes into it. Keep it that way.

`run_pipeline.py` carries two guards that exist because a launcher makes both
mistakes cheap, and neither is model behaviour:

- **`preflight()`** refuses a Stage-4 run whose inputs are missing, or whose
  destination disagrees with the prices on disk. See the destination section
  above; the missing-file half just turns a loader `FileNotFoundError`, which
  on a Module 3 file arrives *after* the 862 MB catalog load, into a message
  naming the stage to run.
- **`check_defaults_preset()`** re-derives the `full` preset's four values from
  `dataclasses.fields` and shouts if the preset stops matching. `full` is
  labelled "THE PIPELINE DEFAULTS", and calc `1.17.0` is precisely the release
  that would have made that label a lie. A count or a default spelled out in
  prose is the thing this file keeps catching; this one checks itself.

### The dashboard must not own a console, and that costs more than hiding one

`run.bat ui` used to run `streamlit run ui.py` in the foreground, so the
console window WAS the app: it had to stay open and in the way for as long as
the dashboard was up, and closing it was how you stopped the server. Hiding
that window is not enough on its own; a `pythonw` process with no console has
nothing to close and no output to read, so a failed start becomes a program
that silently does not appear and a successful one becomes a server nobody can
stop without Task Manager. `launch_ui.py` therefore puts up a small control
window to **replace** the console rather than merely suppress it.

The Windows-specific traps below were hit building it, each of which looks
fine from a console and is broken everywhere else, the same shape as the
`set /p` rule below. Count the list rather than trusting a number here; it read
"Three" above five of them until 2026-09:

- 🚨  **`SO_REUSEADDR` is INVERTED on Windows.** On Unix it means "reuse a
  port stuck in TIME_WAIT"; on Windows it means "bind even though someone else
  already holds it". Setting it made a free-port probe return True for the port
  Streamlit was serving *at that moment*, so a second launch would have started
  a duplicate server on an occupied port. `_port_is_free` does a bare `bind`;
  "is something listening" is `_port_answers`' question, and `_choose_port`
  asks it first.
- 🚨  **A process started with `start` inherits this console's stdout**, so
  `run.bat ui > log` or `run.bat ui | tee` blocked until the dashboard was
  closed, measured at 120 s+ against 0.46 s. `<nul >nul 2>&1` on the `start`
  line does NOT fix it. What does is going through Windows Script Host, whose
  `Run` does not pass the caller's handles to the process it creates, so
  `:ui` delegates to `_START HERE.vbs`, which also leaves one windowless-start
  implementation instead of two.
- ⚠️  **`Tk.after` is not thread-safe and raises once the main loop is gone.**
  Reporting progress from the boot thread with `root.after` produced
  `RuntimeError: main thread is not in main loop` whenever the window was
  closed during the seconds Streamlit takes to start, in a thread, under
  `pythonw`, where nothing would ever have shown it. The worker posts callables
  to a `queue.Queue` and the main thread drains it; the worker never touches a
  widget. Cancel the pending pump in `quit()` too: clearing the reschedule flag
  leaves the one already in flight to fire into a destroyed interpreter.
- 🚨  **Closing the window mid-spawn leaked a server nothing could stop.**
  `Popen` returns with the child already alive, so assigning it to `self.proc`
  afterwards left a window in which `quit()` found `None`, killed nothing, and
  the control window, the only thing that could have stopped the server, 
  went away. Reproduced, not theorised. **Two things were needed and one is
  not obvious:** a lock makes the hand-over atomic, AND `main()` must join the
  boot thread after `mainloop()` returns. The thread is a daemon, so without
  the join the interpreter exits and kills it wherever it stands; the lock
  would be protecting a window the process never lives long enough to reach.
- ⚠️  **A health check identifies Streamlit, not YOUR Streamlit.** Adopting
  any server that answers `/_stcore/health` on 8501 meant a double-click could
  open somebody else's project. `.launcher/running.json` records the port and
  pid we started; reuse requires the marker, a live pid AND a healthy port, so
  a crashed launcher, a recycled pid and a stranger's app each fail a different
  one of the three.

⚠️  **The dashboard's defaults must never re-fetch on their own.** Stages
1-3 all fetch, and each overwrites the only copy of its CSV, which is what
invalidates every `.verify` baseline, and it is a mistake somebody made here
on 2026-08-23. `ui.py` used to default every CACHED stage to on except Stage 1,
so the first click of "Run pipeline" re-priced Stage 2 and 3 against live
quotes. It now defaults a cached stage to **off** unless it is Stage 4, which
fetches nothing and is the point of the button; i.e. the default is the
"re-run Stage 4 against a cached catalog" loop that `ui.py`'s own docstring
already called the normal one. Ticking a fetching stage still works and now
says what it will destroy.

🚨  **The sidebar's runtime estimate ignored the programme search, which
defaults ON and costs ~3×.** `_stage_minutes` scaled Stage 4 by row count and
`use_beneficiation` only, on a beneficiated:raw ratio of **3.12×** taken from a
stride sample, the exact figure this file retires by name ("the real
full-catalog ratio is **7.1×** raw, not 3.12×"). So a default run was estimated
at **2.2 h against 6.8 h measured**, and was contradicted by Stage 4's own
blurb in the same sidebar, which already said "budget for the 6.8 h". It now
reads the four committed full-catalog cislunar cells directly, so it needs
no ratio at all.

✅  **Re-anchored 2026-08-24 on the calc `1.17.7` cells**: 733 / 1,253 / 3,424
/ 5,692 s. The previous note said the `1.16.0` figures read HIGH because five
performance-only releases had landed with no full-catalog run on any of them;
the 20-cell campaign supplied one, and they were worth 1.78×: 4.32×, so the
default estimate was reading **4.3× high, not slightly**. The sidebar prose
moved with it (6.8 h → 1.6 h), a number and the sentence beside it, changed
in the same commit, which is what this file's "grep the prose too" rule asks
for. ⚠️  It is a **cislunar** prior and cislunar is the CHEAPEST destination,
so it now reads LOW at `leo`, `mars_surface` and `earth_surface` (2.1-2.7×
slower per cell) rather than high everywhere. That trade is deliberate: those
four cells are the ones measured on the current code.

🚨  **And the destination selector seeds from the CATALOG ON DISK, not from
the config default.** `CALC_CONFIG.delivery_destination` is `earth_surface`
while the catalog is almost always `cislunar`, so a freshly-opened page
disagreed with its own data, marked Stage 2 stale, forced it back on and made
the first run a live re-price for a destination nobody chose. ⚠️  This is
**not** the silent adoption `run_pipeline.py`'s `preflight()` deliberately
refuses, and the distinction is the point: headless, the destination would be
adopted invisibly and the run would proceed, so refusing is right; in the UI it
lands in a selectbox the user is looking at, under a caption saying it matches
the data on disk. **A UI default that is visible is not the same as a CLI
default that is not.**

⚠️  **Nothing in `run.bat` may prompt once an argument was given**, and that
rule has now been broken twice in the same file. `set /p` against a stdin a
scheduled job holds open and never writes to does not read EOF; it **waits
there forever**, so the failure is a hang rather than an exit code, which is
the worse of the two. Both the destination prompt and the unrecognised-option
retry had to be moved behind `if defined ARG1`. If you add a menu entry, the
test is `run.bat <your-option>` from a non-interactive shell, not from a
console.

### Charts, presets and the dashboard's own defect classes

The 2026-09-04 UI pass found the repo's existing defect classes wearing a front
end, plus one environment trap that is not one of them. Count the items below
rather than trusting a number here: this paragraph said "four things ... and
one" over six of them before it had been read once, which is the failure this
file names oftener than any other, committed in the section documenting it.

🚨  **`mark_bar` ON A LOG SCALE DRAWS NOTHING, AND SAYS NOTHING.** A bar runs
from an implicit zero baseline, `log(0)` is negative infinity, so the "Best
cost/revenue by spectral type" chart rendered an axis, a legend, five type
labels and **no bars at all**, with no console error and no exception. The
spread it is plotting runs from about 18x to 1e5, which is exactly the range
that needs a log axis, so the MARK is what gives way: it is a dot plot now,
sized by how many targets of that type the run evaluated. **This is defect
class 5, "the wrong behaviour is the quiet one", in a chart**: the failure
looks like an empty result rather than a broken one, so it reads as "no
`replicated` device survived" rather than "this chart does not work".

🚨  **A LAYERED ALTAIR CHART SHARES ONE SCALE PER CHANNEL, and the explicit
domain wins.** The orbit diagram layers three orbits coloured by body over two
apsis markers coloured by role. The marker layer declares its own colour
domain, that domain swallowed the orbit layer's, "Earth" / "Mars" /
the designation were all off-domain, and **the orbits drew with no colour**,
leaving a picture of a sun and two diamonds. `resolve_scale(color="independent")`
is the fix and it is load-bearing rather than tidying. Same shape as the bar:
a chart that is wrong renders, it just renders less.

✅  **THE THREE PRESETS ARE IMPORTED, NOT RESTATED.** `run.bat quick` and the
dashboard's **Quick sample** now go through one `run_pipeline.apply_preset`,
because a second copy of "what quick means" is two definitions waiting to
disagree, which is the class this file names first and oftenest. The UI adds
one thing on top: which session keys to clear after applying a preset is
**derived**, by snapshotting every introspected field before and after and
dropping the ones that moved, rather than by listing the fields `apply_preset`
writes today. Listing them means a fifth field added there is written onto the
config and then immediately overwritten from a stale session value, which is a
silent wrong answer rather than an error.

⚠️  **A CONFIG SEARCH MUST REPLACE THE TABS, NOT SIT ABOVE THEM.** The widget
key IS the storage key, so a field rendered in the search results AND on its
own tab in the same run is a duplicate-key exception. Search mode and browse
mode are exclusive by construction, which is also why the curated fields
already render as read-only mirrors on their module tabs. Anything that adds a
second place a field can appear has to answer this.

⚠️  **`usecols` RAISES ON A COLUMN THE FILE DOES NOT HAVE**, which matters the
moment the UI reads anything Stage 1 added recently. `orbit_condition_code`,
`observation_arc_days` and `n_observations` arrived in catalog `1.2.0` and no
catalog built before it carries them, including the one on disk here, so the
element read takes the header first and intersects. The panel then SAYS the
catalog cannot answer the question rather than rendering nothing, because a
silent gap reads as a clean bill of health.

🚨  **AND `py` IS NOT NECESSARILY THE INTERPRETER THE DASHBOARD RUNS ON.** This
machine has at times carried two registered installations of the same Python
minor version: `py` resolved to one under `...\Programs\Python\`, while
`_START HERE.vbs` probes `pyw -3` and reached one under `...\Local\Python\`,
which is where `launch_ui.py` then installed Streamlit. So
`py -m streamlit run ui.py` fails with `ModuleNotFoundError` on a machine whose
dashboard works perfectly. **Ask the machine which one answered before
concluding a dependency is missing:**

```bash
py -0
py -c "import sys; print(sys.executable)"
py -c "import streamlit; print(streamlit.__version__)"
```

⚠️  **`.claude/launch.json` therefore spells the interpreter out, and that path
is a thing that rots.** It was still naming a `pythoncore-3.14-64` install
after that install was removed, under a user profile (`Loggg`) that has never
existed on this machine, so the Browser pane could not start the dashboard at
all. Repointed on 2026-09-08 at whatever `py -c "import sys;
print(sys.executable)"` answers, which is the command above. It is untracked
local tooling, so nothing in the repo's own harnesses can see it go stale; the
tell is the pane failing to launch, not a red check.

⚠️  It is the interpreter-version lesson one level along: this file refuses to
spell the version out because it rotted three times in six days, and the same
reasoning applies to which install `py` picks. `launch_ui.py` is right to use
`sys.executable` and `_console_python()` rather than shelling out to `py`; do
not "simplify" either into a bare interpreter name.

### The console output is ASCII, and must stay that way

🚨  **THE STAGE BANNERS USED TO BE EMOJI, AND WINDOWS PICKS cp1252 FOR A
REDIRECTED STDOUT.** So `py master.py > run.log`, or any pipe, died on the
first `print` with `UnicodeEncodeError: 'charmap' codec can't encode character
'\U0001f4b0'`, at master.py's own "PROFITABILITY PIPELINE" line, before one
row was evaluated. It never fired in a console, so it was invisible until the
moment somebody logged a long run, which is exactly when it cost most. Hit on
the first run of `run_pipeline.py`.

Fixed at source: **every `print(...)` in the four modules is pure ASCII**, and
so is everything `build_master.py` emits into `master.py`. Verified
mechanically rather than by eye, zero non-ASCII characters remain in any
print literal in the built `master.py`.

✅  **And the failing case was re-run rather than reasoned about.** A Stage 4
pass under `PYTHONUTF8=0 PYTHONIOENCODING=cp1252`, stdout redirected to a file,
with **no** reconfigure anywhere, i.e. exactly what used to die on the first
banner, now completes with **exit 0 and empty stderr**. That is the regression
test for this; re-run it after touching any print.

⚠️  **EMOJI WERE UNDER A FIFTH OF IT, AND FIXING ONLY THEM WOULD HAVE LEFT THE
CRASH IN PLACE.** Of **2,081** occurrences cp1252 cannot encode, just **372
(17.9%)** are emoji; the other **1,709** are box drawing, `─` alone appears
1,204 times, plus arrows, `Δ`, `≈`, `−` and `×`. The rule is therefore
**ASCII, not "no emoji"**: any non-ASCII character in a printed string is the
same bug, and `print("─" * 75)` crashes exactly as hard as a money bag.

⚠️  **Only PRINTED strings were converted.** Comments and docstrings keep
theirs, because they are the reasoning this repo exists to preserve, and so
does every DATA string, because the `notes` fields in `PROPELLANTS_REFERENCE`
and `STORAGE_REFERENCE` are written into `propellants.csv` and
`storage_systems.csv`, and rewriting them would change CSV bytes. The
transformation was AST-driven and touched only the source segments of
`print(...)` calls for exactly that reason.

🚨  **It also left TWENTY lines ungrammatical, and nobody read them for ten
days.** An em-dash that had opened a CONTINUATION line became a bare
comma at the start of the line, so `modules/calc.py` carried, among eleven
others, `#, and nothing in this module ever read it.` The pass was correct
about what it must not touch and had no check on what it left behind; a
converted comment is still prose a reader has to parse. Eight were re-joined in
place on 2026-09-02, comma moved onto the previous line and no word added or
reordered; the other four were inside the release notes that moved to
`versions.md` in the same pass and were fixed as prose there.

⚠️  **And then eight more turned up in the DOCS on the next pass the same
day**, including `, it auto-installs its own dependencies` in README, because
the first sweep grepped `modules/*.py` and stopped there. Fixing one half of a defect class and not
looking for the other half is how this one survived twice. ✅  It is
`verify_docs.py` check 6 now, beside the dash ratchet, because it is the same
pass's damage: **a mechanical rewrite of prose needs a check on what it LEAVES,
not only on what it removes.**

🚨  **`build_master.py`'s ANCHORS MATCH ON LINES THIS CHANGED, and one of them
broke on the first rebuild**; `BUILD FAILED: catalog: INSTALLATION block
survived`. Two rules, learned the hard way:

- The install-block anchor is now `print\("OK  All packages present"\)`. **Do
  not "improve" that marker to `[OK]`**; inside a regex `[OK]` is a CHARACTER
  CLASS matching `O` or `K`, so the anchor would silently stop matching the
  line it names. Every replacement used here is free of regex metacharacters
  for this reason.
- Both anchors still match the rule comments with `# ─+`, because those rules
  are **comments and are not printed**. Anchor and target must be changed
  together or not at all, the same "update `build_master.py` in the same
  commit" rule this file states above.

✅  **It moved no number, and that was proven rather than assumed.** The four
committed cell hashes reproduce exactly, and when a Stage 2 price refresh made
the release baseline stale mid-session, the change was re-isolated by baselining
the pre-change build against the *same* refreshed catalog: **139/139 columns
identical on all four cells.** Comparing two builds against identical inputs is
the only construction that answers this question.

`run.bat` still sets `PYTHONUTF8=1` and `chcp 65001`, and `run_pipeline.py`
still reconfigures stdout to UTF-8 with `errors="replace"` at import. That is
belt and braces, not the fix: it also covers tqdm, exception text and any data
value that reaches stdout.

✅  `PYTHONUTF8=1` **cannot move an output byte**, which is why it is safe to
set globally: the only bare `open()` in the four modules is binary
(`catalog.py`'s download), and every CSV is written by `to_csv`, which is UTF-8
regardless of locale. Checked before it was used, because a locale switch that
reached a CSV would break the bit-identity every release is argued from.
