# Version history

Every release of this pipeline, newest first, plus the measurement tables that
each release superseded. It was split out of `README.md` in 2026-08 because the
version record had grown to roughly half that file and was burying the parts
you need to actually run the thing.

- **`README.md`**: what the pipeline is, how to run it, what the model does,
  and the **current** numbers.
- **this file**: what changed and when, and what the numbers used to be.
- **`CLAUDE.md`**: the working notes: the traps, the invariants, and the
  reasoning behind decisions that look wrong. It is the deepest record of the
  three and the one to read before editing.

Where the two overlap, `README.md` is the current answer and this file is the
history of how it got there.

## Current versions

| Stage | Module | Version | Last changed |
|---|---|---|---|
| 1 | `modules/catalog.py` | **1.1.1** | v1.1.1, `enrich_composition` by distinct taxonomy, 3.87× |
| 2 | `modules/mineral_value.py` | **1.7.1** | v1.7.1, three PGM ore minerals reclassified out of a silent default |
| 3 | `modules/transportation.py` | **1.12.1** | v1.12.1, `.astype(bool)` on the propellantless flag |
| 4 | `modules/calc.py` | **1.17.8** | v1.17.8, the loader checks its upstream stamps |
| - | `master.py` | **1.20.8** | a literal in `build_master.py`, in **two** places |

⚠️  **The authority is the `pipeline_version` field in each module's config
dataclass, never a table.** This one has rotted before: the README's copy read
calc 1.16.0 until 2026-08-21, four releases behind. Check the dataclass.

## How the version numbers work

Each module carries a `pipeline_version` that is stamped into every output CSV,
so the stamp is the only way to tell which code produced a given catalog.

**The rule is one-directional: changing any number a run produces means
bumping. Bumping does not mean a number changed.** Reading a version as
evidence that a result moved is the mistake the table below exists to prevent.

Twelve stamps so far have moved without moving a number:

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

⚠️  **Read the module, not just the number.** `1.7.1` and `1.17.1` are different
modules and unrelated releases; every row above is calc except the last.

⚠️  **Derive any count of these from the table, not from a sentence.** Eight
rows are performance stamps and four are not, and that split has rotted in
prose twice. A count is a number; re-derive it.

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

## Releases

Newest first. Each heading names every module whose `pipeline_version`
moved in that release.

| release | date | what it was |
|---|---|---|
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

**A cache grew without bound.** `_CALENDAR_CACHE` memoised a pair of programme
calendar multipliers on `(campaigns-per-ship, cadence, WACC)`. The first two of
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
`enrich_composition` resolved everything keyed on `spectral_type` once per row
, nine composition fields, two capitalisation passes, the PGM multiplier, twelve
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
answer**
, campaigns-per-ship comes out at the rig's trip life on all 168 rows. The proof
is what broke, not the answer: once a lever pushes back, a dimension whose
optimum is no longer guaranteed has to be searched rather than assumed. It does
bite when trips are longer, against the older Stage 3 table, where nothing
capped duty cycles and trips reached 20, 12 of 168 bodies choose to retire a rig
early rather than pay the calendar to use it up.

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

# Measurement history

What the numbers used to be, why they moved, and the rule this project keeps
relearning about predicting them. **Every table here names the release and the
catalog it belongs to. If one does not say, do not use it.**

The current answers are in the README:
[Results](README.md#current-results-the-complete-20-cell-matrix) for the model,
[Beneficiation](README.md#beneficiation) for the wall clock.

## Cost/revenue matrices

The headline number of each release, newest first. Lower is better and 1.0
would be breakeven; none of them reaches it.

🚨 **Every matrix in this section is superseded** by
[the 20-cell matrix](README.md#current-results-the-complete-20-cell-matrix),
which measures every destination × ore × programme-search setting on the full
1,555,667-row catalog on calc v1.17.7. **They are kept for their structure, not
their numbers**, which destination wins and why, what beneficiation does, which
effects the model is sensitive to. Two compounding reasons they cannot be
quoted:

- **catalog v1.1.0 took the population from 89,367 bodies to 1,554,400.** Every
  figure here is "the best mission over the bodies we had", so nothing survives
  a 17× population change, however sound the model was.
- **The model then changed repeatedly.** v1.14.0 alone added containment,
  eclipse power, a searched power source and saturation-vs-programme-size.

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
[the 20-cell matrix](README.md#current-results-the-complete-20-cell-matrix).
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
[the 20-cell matrix](README.md#current-results-the-complete-20-cell-matrix);
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

