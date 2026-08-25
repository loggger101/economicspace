# Notes for working in this repo

Context for anyone (human or agent) editing this pipeline. Three files, and
the split between them is deliberate:

| file | holds | is the authority for |
|---|---|---|
| [`README.md`](README.md) | what the pipeline is, how to run it, what the model does, and the **current** numbers | the current answer |
| [`versions.md`](versions.md) | what changed in which release, and what every number used to be | the measurement history |
| **this file** | what will bite you: the traps, the invariants, and the reasoning behind decisions that look wrong | how to edit it safely |

**It is meant to be grepped rather than read.** Six parts, in this order:

| part | what it is | read it when |
|---|---|---|
| **Build and versioning** | how `master.py` is assembled, and the `pipeline_version` rule | before any edit |
| **What the model currently says** | the 20-cell campaign, per destination, and the claims each cell retired | before re-measuring anything, or "fixing" a result that looks wrong |
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

## master.py is generated: never edit it

`master.py` is ~9,600 lines assembled from `modules/*.py` by `build_master.py`.
Edit the module, run `py build_master.py`, commit both. A change made
directly in `master.py` is destroyed by the next build.

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

## Bump `pipeline_version` when output changes

Each module carries a `pipeline_version` in its config dataclass, and it is
stamped into every output CSV. That stamp is the only way to tell which code
produced a given catalog, so changing any number a run produces means bumping
it. The version-history comment block above each `pipeline_version` field is
the real changelog for this project; it records the numerical impact of each
change, often hand-verified. Add to it, don't replace it.

This has already failed once: the project was briefly developed in two places
at once, and `1.0.6` / `1.1.4` / `1.3.6` each shipped as two different things.
See "The parallel-repo divergence" in `versions.md`; CSVs stamped with those
versions cannot be trusted and should be regenerated.

Current: catalog `1.1.1`, mineral_value `1.7.1`, transportation `1.12.1`,
calc `1.17.7`, master `1.20.8` (the master version is a literal in
`build_master.py`'s `MASTER_HEADER` and `MASTER_ORCHESTRATOR`, two places).

ℹ️  **TWELVE stamps so far do NOT mean the numbers moved.** The rule is
one-directional: *changing a number means bumping; bumping does not mean a
number changed*, and reading a version as evidence that a result moved is the
mistake this table exists to prevent.

⚠️  Every row is a **calc** stamp except the last, which is `mineral_value`, 
the first non-calc entry this table has carried. Read the module, not just the
number: `1.7.1` and `1.17.1` are different modules and unrelated releases.

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

**Every measured cell in this file stands unaltered across all twelve; do not
re-measure anything on account of any of them.** Each release's own section
carries its verification.

⚠️  **Derive the taxonomy from the table above, not from a count in prose.**
Eight rows are *performance* stamps; the rest are `1.17.0` (a default flip),
`1.17.3` (a cleanup), `1.17.7` (a memory bound) and `1.7.1` (a silent default
closed in another module), which is why
this file counts two sequences that run apart; see "What calc v1.17.0
changed". That paragraph is where the count last rotted: it was written at
`1.17.5` and still read "nine" and "seven" after `1.17.6` shipped, which is
exactly the *counts-spelled-out-in-prose* failure the "When a number changes,
grep the prose too" section names.

🚨  **`1.17.7` IS THE FIRST STAMP HERE THAT FIXES A DEFECT RATHER THAN A COST,
and it is a defect no cell in this file could have shown.** `_CALENDAR_CACHE`
was the one memo in the module keyed on a **per-candidate float**, so it grew
linearly with the catalog: ~45 entries per row, **~70 M entries and 11-18 GB**
projected on a full-catalog default cell against a documented run peak of
~6 GB. It landed in `1.17.4` and **no full-catalog run has been made since
`1.16.0`**, so nothing had ever exercised it at the scale that shows it. Now
bounded, which cannot change an output value by construction and is also
*faster* (180 → 91 ns a hit). See "What calc v1.17.7 changed".

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
~67-78 s on a full cislunar pass. See "What calc v1.17.4 changed".

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
being *rebuilt* per candidate rather than anything inside a rung. See "What calc v1.17.5
changed", whose own section also re-measures the one big item this file has
twice declined on a stale figure.

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
**reproduce exactly**. See "What calc v1.17.0 changed".

⚠️  **`1.15.0` AND `1.16.0` MOVE NUMBERS ONLY FOR PROGRAMMES, and almost every
measured cell in this file is a single mission.** Three items between them: 
`1.15.0`'s duty-cycle cap on rig life and its searched programme size,
`1.16.0`'s programme calendar charge, are all exactly inert at N = 1 (W = 1,
one campaign per ship). Verified rather than argued: on the 400-row raw
cislunar sample at N = 1, `1.16.0`'s term on and off is **141 of 141 columns
identical, sha256 MATCH**.

**Do not re-measure a single-mission cell on account of either release**, and
do not read any table below as covering an `optimise_programme_scale = True`
run unless it says so, only those under "Measured, FULL CATALOG" and "THE
FULL CISLUNAR 2×2" do. The N = 10 / N = 100 curve **does** move, and is now a
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
absolute. See "Measured, FULL CATALOG".

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
guidance. It sat under the `pipeline_version` heading above for several
releases, which is why a section about version stamps ran to nine hundred
lines.

Read it before re-measuring anything, and before "fixing" a result that looks
wrong: that is what it is for. `README.md` carries the same headline numbers
in a shorter form for anyone who is not about to edit the model; what is here
and not there is the per-destination detail, and the claims each cell retired.

### ✅ THE COMPLETE 20-CELL MATRIX IS MEASURED (CURRENT: 2026-08-23/24, calc `1.17.7`)

**Every destination × both settings of beneficiation × both settings of the
programme search**, on the full 1,555,667-row catalog, 12 workers, 26.1 h of
compute, zero failures. **These are the current numbers for the whole model.**

🚨  **The headline table itself lives in
[README.md](README.md#current-results-the-complete-20-cell-matrix) and is not
copied here**, for the reason this file gives everywhere else: name one
authority or you have two. What is below is the part a README should not
carry, the per-destination depth, the invariants, and the claims each cell
retired.

The two facts worth restating because everything downstream leans on them:
**`cislunar` is the best case on all four settings** (13.1443× against
`lunar_surface`'s 22.5790×, a factor of 1.72 on the default cell), and **the
programme search never changes the evaluable set** at any destination, as it
must not, since N enters nothing in the mass cascade.

⚠️  **Twelve of these twenty cells had never been measured at all**: every
non-cislunar beneficiated cell and every non-cislunar searched cell. The four
non-cislunar beneficiated figures in the v1.11.0 matrix were placeholders on
the OLD 89,367-row catalog and are now retired: `lunar_surface` reads
**35.8051×** against that table's 37.8133×, `leo` **48.2714×** against
51.2223×, `mars_surface` **55.3403×** against 51.9597×.

#### Reproduction against the committed record

| cell | measured | committed | Δ |
|---|---|---|---|
| `cislunar`, all four | 26.7863 / 15.4272 / 20.5895 / 13.1443 | identical | **exact** |
| `lunar_surface` raw N = 1 | 63.3505× | 63.3505× | **exact** |
| `mars_surface` raw N = 1 | 74.6748× | 74.6748× | **exact** |
| `leo` raw N = 1 | 71.1029× | 71.1055× | −0.004% |
| `earth_surface` raw N = 1 | 42,953.98× | 43,721.01× | **−1.75%** |

The cislunar reproduction is total: winner **2021 CX5 (D)** in all four,
New Glenn / xenon, New Glenn / iodine, iodine at **3.5186×**, argon at
**3.9249×**, payloads 93,312 / 68,432 / 62,283 / 34,573 kg, saturation 0.6873,
`p_mining` 0.850 / 0.8858 / 0.850 / 0.9024, RTG 5.44 / 6.66 / 10.83 / 12.66%,
and New Glenn overtaking Falcon Heavy in the default cell at 36.57 / 36.41%, 
every one the committed figure, across **seven version stamps** and a
**re-priced Stage 2 catalog**. The raw N = 1 row reproduces its v1.14.0
aerocapture (0.00 / 0.00 / 93.107 / 82.002 / 95.749%), RTG (5.439 / 3.957 /
8.240 / 6.506 / 8.461%) and ISRU (8.113 / 3.762 / 1.932 / 2.063 / 1.894%)
shares at every destination.

✅  **The drift ordering confirms a mechanism this file had only ever argued.**
`earth_surface` is priced straight off live terrestrial quotes while an
in-space kilogram is dominated by launch-cost-avoided, derived through the
rocket equation from **constants**. Across a 12-14 day price gap the cells move
in exactly that order, and they are ordered by **how small launch-cost-avoided
is, not by distance**:

```
cislunar 0%  =  lunar_surface 0%  =  mars_surface 0%  <  leo 0.004%  <<  earth_surface 1.75%
```

`leo` is the **cheapest** in-space destination to reach, so a terrestrial price
is the largest share of its value, and it is the only in-space cell that moves
at all. `mars_surface` is the furthest and does not move. **Do not read a small
`leo` drift as a regression**, and do not expect `earth_surface` to reproduce
across days: this file already says its raw cell moves a few tenths of a
percent overnight; 1.75% is a fortnight of metal prices.

#### Invariants: clean on all twenty cells

- **never-worse**: **20 pairings, zero exceptions**, every max ≤ 1.000000, 
  beneficiated ≤ raw and searched ≤ N = 1, at all five destinations
- **mass ledger**: `max |error| 0.000000000 kg` on all 20 cells
- **programme structure**: **N = F × W on every row** of all ten searched
  cells, and **W > `trips` never**

Bodies declining to concentrate vary enormously by destination, and the
ordering is the ISRU discount doing its job: `mars_surface` **4,276 (0.6%)**,
`earth_surface` 8,340 (1.1%), `lunar_surface` 22,781 (3.9%), `leo` 90,372
(11.6%), `cislunar` **102,765 (15.8%)**. Median improvement from beneficiation
runs +39.5% at `cislunar` to **+77.7%** at `earth_surface`.

### 🚨 `earth_surface`'s SEARCHED CELLS ARE NOT OPTIMA: saturation is inert there

`saturation_multiplier` across the searched cells:

| cell | min | median | max | fleet median | N median |
|---|---|---|---|---|---|
| `cislunar` raw | 0.358439 | 0.812837 | 0.999957 | 2 | 10 |
| `lunar_surface` raw | 0.536206 | 0.830467 | 0.999726 | 4 | 20 |
| `leo` raw | 0.704996 | 0.861486 | 1.000000 | 5 | 25 |
| `mars_surface` raw | 0.354904 | 0.750813 | 0.999996 | 2 | 10 |
| **`earth_surface` raw** | **1.000000** | **1.000000** | **1.000000** | **64** | **320** |
| **`earth_surface` benef** | **1.000000** | **1.000000** | **1.000000** | **64** | **320** |

At `earth_surface` the multiplier departs from 1.0 by a **median of 2.3e−11**
and at most **2.4e−7**, against `cislunar`'s 1.9e−1. Terrestrial markets run
10¹²: 10¹⁵ kg/yr, and fifteen commodities take the unlimited default, against
a programme delivering ~10⁷ kg, so the price never moves.

So every lever improves with N, **nothing pushes back**, the objective is
**monotone in N**, and **100.00% of rows**: 784,242 raw and 912,846
beneficiated; run to `max_fleet_ships` = 64, N = 320, 64 concurrent missions.
**`12,977.88×` and `7,869.88×` are the value at the ladder's TOP RUNG.** Raise
`max_fleet_ships` and they keep improving. This file already says rows at that
ceiling are "a diagnostic, not a result"; at `earth_surface` that is the entire
population, where `cislunar` runs 0.37-0.40% and `mars_surface` 0.15-0.47%.

🚨  **This is v1.14.0's own failure mode surviving at one destination.** That
release fixed "market saturation could not see the programme it was written
for … every lever pointed the same way and nothing pushed back" by making the
rate the programme's **concurrent** output. The fix is structurally present
here and **numerically inert**, because Q/Q_market is 1e−11.

It also re-scopes mineral_value `1.7.1`'s "measured and declined" note on
`nickel-iron` having no terrestrial market ceiling. That item was costed at
**7.7e−8 relative on a SINGLE MISSION's multiplier**: correct, and the wrong
scope. With the search on, a missing ceiling changes the **shape** of the
objective in N rather than its level, and a shape change has no size. ⚠️  The
other four destinations are unaffected; saturation bites hard at all of them.

### 🚨 RETIRED: a `replicated`-scaling device DOES win, at `mars_surface`

This file's standing claim is "**A `replicated` device never wins anywhere**; 
eight cells, zero wins", qualified by its own warning that "on half the cells
it holds by a few percent, not by a factor, and a modest change to thruster
mass or to the population could flip one."

**The programme search flips it.** `mars_surface`, raw, search ON:

```
rank 1   2014 YN     (M)  41.8068x   FEEP (indium field emission)   H3 (24L)       N = 5
rank 2   2015 BM510  (M)  47.4127x   methalox                       Falcon Heavy   N = 5
```

It wins by **13.4%**, carrying **6,667 kg of thruster for 96.7 kW**. At N = 1
the same destination still puts the best FEEP mission at **rank 5, 1.06× off**,
reproducing the committed figure exactly, so this is the **search**, not drift
and not the population.

Best `replicated` mission per cell, rank and margin, **zero survivors at
`lunar_surface` in all four cells**, as committed:

| destination | raw N = 1 | raw searched | benef N = 1 | benef searched |
|---|---|---|---|---|
| `cislunar` | 39 (1.29×) | 283 (1.69×) | 8,602 (2.17×) | 12,020 (2.12×) |
| `lunar_surface` | none | none | none | none |
| `leo` | 62 (1.32×) | 1,145 (1.47×) | 1,770 (1.62×) | 19,197 (2.15×) |
| `mars_surface` | 5 (1.06×) | **1, WINS** | 73 (1.11×) | 14 (1.06×) |
| `earth_surface` | 7 (1.09×) | 5 (1.07×) | 13 (1.20×) | 10 (1.16×) |

The `cislunar` and `earth_surface` N = 1 entries reproduce the committed ranks
and margins (39 / 1.29×, 8,602 / 2.17×, 7 / 1.10×).

✅  **The gate is not broken and must not be "fixed".** `thruster_kg_per_n` is
a mass penalty rather than a threshold, that was the whole design argument, 
and this mission pays 6.7 tonnes of thruster and wins anyway, which is the
mechanism working, not leaking. What is retired is the **claim**. The lesson is
the one v1.14.0 already wrote down for the RTG branch: *a margin of a few
percent is not a law*, and here one new search axis was enough to close it.

🚨  **SURVIVAL WAS NEVER THE TEST, AND THE COUNT IS THE REASON.** The
survivor count spans **400x across destinations on one model, one catalog and
one release**: zero at `lunar_surface` against 5,479 (0.699%) at
`earth_surface`, with `cislunar` at 13 raw (0.002%) and 327 beneficiated
(0.050%), and `leo` at 4,710 (0.607%). A claim built on a count is a statement
about the **population**, not about the gate, which is how "zero survive
anywhere" survived as a law for a release; it was measured on 15,566 rows.
**Test whether one WINS.**

Two facts about the survivors that do not change with the population:

- **Every survivor in every cell is FEEP**, 12,213 rows of it. Not one PPT and
  not one electrospray row survives anywhere, at any destination or programme
  size, where the pre-gate model had PPT winning **31.8%** of cislunar rows and
  electrospray **24.3%**. Only the lightest of the three `replicated`
  technologies (2,500 kg/N against 5,000 and 10,000) ever closes a mass budget.
- **They close by being enormous, not by being efficient.** Survivors carry
  **4.4 to 16.7 tonnes** of thruster (median 13.2 t raw) for ~5 N, and close
  only because their payloads are 70-128 t and can absorb it.

### Runtime, and the three quantities a sample cannot predict

**Wall clocks and cost ratios live in
[versions.md](versions.md#what-the-v117x-line-was-worth)**, which measured the
whole `1.17.x` line on the full catalog at once; the twenty-cell wall clock is
in [README.md](README.md#beneficiation). Neither is repeated here. The three
things that are *guidance* rather than record:

🚨  **A default cislunar run is now ~1.6 h, not 6.8 h**, and **every timing or
cost ratio in this project older than calc `1.17.7` is high by 1.78-4.32x.**
Five committed ratios moved as a consequence, including the two most quoted:
beneficiation costs **4.67x** rather than 7.1x, and the programme search
**1.71x** rather than 2.98x. ⚠️  Those are `cislunar` figures; `leo`,
`mars_surface` and `earth_surface` cost 2.1-2.7x more per cell.

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

### The rig's two bounds, and the cadence, at every destination

This file carries this table for `cislunar` only, where beneficiation swaps the
two bounds over. ✅  **Every committed `cislunar` figure reproduces exactly**: 
96.11 / 3.89 / 92.31 / 7.69% raw, 57.66 / 42.34 / 34.13 / 65.87% beneficiated,
98.04 / 95.77% raw searched and 75.08 / 37.59% beneficiated searched, cadence
medians 1.38 and 2.09 yr. Here are the other four.

**Which bound retires the rig** (cycle = `max_trips`, calendar = `life / stay`):

| destination | raw N=1 | raw ON | benef N=1 | benef ON |
|---|---|---|---|---|
| `cislunar` | 96.11 / 3.89 | 98.04 / 1.96 | 57.66 / 42.34 | 75.08 / 24.92 |
| `lunar_surface` | 96.09 / 3.91 | 96.36 / 3.64 | 75.24 / 24.76 | 93.51 / 6.49 |
| `leo` | 98.70 / 1.30 | 98.89 / 1.11 | 49.54 / 50.46 | 77.89 / 22.11 |
| **`mars_surface`** | **80.99 / 19.01** | **85.24 / 14.76** | **19.21 / 80.79** | **21.44 / 78.56** |
| `earth_surface` | 98.65 / 1.35 | 98.75 / 1.25 | 29.53 / 70.47 | 47.66 / 52.34 |

**What sets the pace** (window = synodic period, dig = mining rate), and the
median cadence:

| destination | raw N=1 | benef N=1 | cadence raw | cadence benef |
|---|---|---|---|---|
| `cislunar` | 92.31 / 7.69 | 34.13 / 65.87 | 1.384 yr | 2.090 yr |
| `lunar_surface` | 96.21 / 3.79 | 42.73 / 57.27 | 1.384 yr | 1.622 yr |
| `leo` | 88.67 / 11.33 | 25.37 / 74.63 | 1.369 yr | 2.564 yr |
| **`mars_surface`** | **99.95 / 0.05** | **63.18 / 36.82** | **3.798 yr** | **3.990 yr** |
| `earth_surface` | 86.48 / 13.52 | 17.03 / 82.97 | 1.369 yr | 3.324 yr |

🚨  **`mars_surface` INVERTS BOTH SPLITS, AND IT IS THE ONE DESTINATION WHERE
THE CALENDAR BOUND DOES MOST OF THE WORK.** Beneficiated, the calendar retires
**80.79%** of Mars rigs against `cislunar`'s 42.34% and `lunar_surface`'s
24.76%. The mechanism is in the cadence column: a Mars campaign repeats every
**3.8-4.0 years** against ~1.37 for everywhere else, because the Earth; Mars
synodic period is 2.14 yr and the transfer is a separate heliocentric leg. At
that cadence `life / stay` runs out long before five digs do.

⚠️  So this file's statement that "the cycle bound is what retires almost every
rig" is a **`cislunar` raw** claim twice over; it fails on beneficiated
`cislunar` (42% calendar), and it fails hardest at Mars, where the calendar
bound does **four fifths** of the work.

🚨  **And "a programme's pace is set by orbital mechanics, not by mining rate"
inverts at four destinations out of five.** v1.16.0 measured the window binding
on 165 of 168 rows of a 400-row raw cislunar sample and drew that conclusion.
On the full population it is true of **raw** everywhere: 86-99.97%, and
**false of beneficiated everywhere except Mars**: the dig sets the pace on
65.87% of `cislunar` rows, 74.63% of `leo`, and **82.97% of `earth_surface`**.
Beneficiation is exactly the thing that makes the stay long, so it moves the
binding constraint from the sky to the ground.

`mars_surface` is the exception that proves the mechanism: its window is so
long (**99.95%** binding on raw, still 63.18% beneficiated) that even
concentrating cannot make the dig the slower half.

**Programme span** follows the cadence, and the searched cells run long
everywhere: median 10.7 yr (`earth_surface`, `leo` raw) to **21.4 yr**
(`mars_surface` raw) and 13.3-18.7 yr beneficiated. A Mars programme in this
model is a **two-decade** commitment.

⚠️  **`W < trips` is only meaningful with the search ON.** At N = 1, W = 1 and
`trips` is 2-5, so the search-OFF cells report ~100% trivially. With the search
on it is 0.161% (`leo`), 0.177% (`lunar_surface`), 0.210-0.319% (`cislunar`),
0.234-0.268% (`earth_surface`) and **3.705-3.785% at `mars_surface`**: an
order of magnitude more, and the same cause: Mars's calendar charge over a
21-year span is what makes a ship decline the fifth campaign.

### Propellant and vehicle shares, all twenty cells

**Every share table elsewhere in this file is a single cell**, usually
`cislunar` raw at N = 1. These are all twenty, and the raw N = 1 column
reproduces the committed v1.14.0 shares at every destination.

**Propellant, % of evaluable rows:**

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

🚨  **IODINE COMES BACK, AND THE `1.11.0` CLAIM v1.14.0 RETIRED WAS HALF
RIGHT.** v1.11.0 said "iodine wins nine of the ten cells"; v1.14.0 retired that
by name when the eclipse term made **xenon** take 42-76% of every raw N = 1
cell. Both were measuring a **single-mission** population. Turn on both
defaults and iodine **overtakes xenon at `leo`** (42.74 against 42.14%) and
**wins `earth_surface` outright** (47.31 against 35.50%).

That is the mechanism the programme-scale curve already predicted; "iodine
takes over at scale", 25.19% → 49.64% between N = 1 and N = 100, now confirmed
on the real searched population rather than on three sampled points. **Every
propellant-share claim in this file is a statement about a configuration, not
about the model.**

⚠️  **Chemical propulsion is not merely alive, it is 11-15% of three
destinations.** `methalox` goes 1.6-1.8% raw to **11.11-15.23%** beneficiated
at `leo`, `mars_surface` and `earth_surface`. Beneficiation drives mass ratio
up, which is where the v1.11.0 tank term bites, and methalox stores at 0.83
kg/L against xenon's COPV, so it is the propellant that *gains* when the tank
starts to matter. Krypton moves the opposite way for the same reason
(12.5% tankage): 22.64% → 6.40% at `lunar_surface`, 15.37% → 1.52% at
`mars_surface`, and out of the table entirely at `leo`.

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

✅  **New Glenn's rise is the market-saturation mechanism, visible at every
destination at once.** It is a *smaller* vehicle than Falcon Heavy (45 t against
57 t), and it goes 1.67 → 36.57% at `cislunar`, 0.64 → 28.35% at
`lunar_surface`, 5.70 → 28.63% at `mars_surface`. Saturation punishes volume,
so at programme scale the model prefers **more, smaller missions**; the same
thing the winner's payload does (93,312 → 34,573 kg at `cislunar`). The
committed 2×2 recorded New Glenn overtaking Falcon Heavy at `cislunar` as a
first; it is now four destinations showing the same move.

⚠️  `mars_surface` remains the outlier the v1.14.0 matrix describes, least SLS
(10.72% against 21-32%) and most Vulcan, because a Mars delivery pays no Earth
capture, so its stacks are lighter and a mid-class vehicle closes missions that
need SLS anywhere else.

### Winners, and one that is new

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

**Aerocapture resolves per destination exactly as the physics requires**:
**0.00% at `cislunar` and `lunar_surface` in all four cells**; nobody asserts
it, the airless destinations ignore the flag and the search declines it, and
82-98% elsewhere, rising under beneficiation at every atmospheric destination.

**ISRU tracks hydrolox to within 0.03 pp at every destination**, which is the
consistency to expect rather than a coincidence, since hydrolox is the ISRU
route the search overwhelmingly takes: 8.1097 against 8.1106% at `cislunar`,
exact to four decimals at `lunar_surface`. ⚠️  **They are near-equal, not equal,
and the residual runs BOTH ways**: at `leo` and `earth_surface` hydrolox
slightly exceeds ISRU (1.9493 against 1.9292), so a few missions buy hydrolox
on Earth rather than make it, while at `mars_surface` ISRU exceeds hydrolox
(2.0606 against 2.0522), so a few make something else. Neither residual has
been traced to a propellant, and **the water-ion share is not the place to look
for it**: `cislunar` runs 15.58% water ion against 8.11% ISRU, so most
water-propelled missions are carrying their water up from Earth.

### Programme structure on the full population

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
anchors, document structure, the em-dash ratchet and, with `--before`, whether
a reorganisation dropped a measurement. Run it after touching any config field
or reference table.

⚠️  **It cannot see a stale measurement.** A number that is merely out of date
passes everything in it, which is why the rest of this section is still a
manual discipline.

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

🚨  **THERE ARE THREE FILES TO GREP NOW, NOT TWO.** The release history moved
out of the README into `versions.md` on 2026-08-24, so a measurement can go
stale in any of: this file (the working notes), `README.md` (the current
answer) and `versions.md` (what the numbers used to be). The split is what
makes that tractable; `versions.md` is *allowed* to hold superseded figures,
and every table in it names the release and catalog it belongs to, but it
means `grep -rn "<the old number>" *.md` is the check, not a two-file diff.

✅  **Audit a split at FACT level rather than by eye, and do it with
`verify_docs.py --before`.** Pull every distinctive numeric token out of the
old file (anything with a decimal point, a thousands separator, or four-plus
digits) and assert each still appears somewhere in the new ones; that is
check 7, and it exists because a line-level diff reported **302 differences**
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
> under "THE COMPLETE 20-CELL MATRIX" at the top of this file. **Every wall
> clock below is superseded**; they are kept because the *reasons* the timings
> moved are the point of the section.

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

The table below is calc `1.11.0` / six physical cores, on the **old ~31,000-row
catalog**, measured 2026-08-08. It is kept because the *ratios* between cells
are still the right way to reason about relative cost; the absolute seconds
are two orders of magnitude out of date:

| | raw | beneficiated | ratio |
|---|---|---|---|
| `cislunar` | 89 s | 462 s | 5.2× |
| `lunar_surface` | 84 s | 437 s | 5.2× |
| `mars_surface` | 158 s | 966 s | 6.1× |
| `leo` | 177 s | 948 s | 5.4× |
| `earth_surface` | 174 s | 1,017 s | 5.8× |

The whole ten-cell sweep is **about 70 minutes** including a Stage 2 re-run per
destination.

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
  bit-identical. See "What v1.10.1 changed".
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
documentation form of the defect this file spends thirty pages cataloguing.**
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
| "chemical propulsion is extinct in this model" | hydrolox holds 1.9-8.1% everywhere; methalox reaches **11-15%** of three destinations beneficiated |
| "iodine wins nine of the ten cells" | a **single-mission** claim; iodine overtakes xenon at `leo` and wins `earth_surface` once both defaults are on |
| "zero `replicated`-scaling devices survive" | they survive, and as of 2026-08-24 one **wins**, at `mars_surface` raw with the search on |
| "a `replicated` device never wins anywhere" | retired by the same measurement; the gate is a mass penalty, not a threshold |
| "the optimum N is *provably* a multiple of the rig's trip life" | only *usually*; programme calendar time pushes back inside a band |
| "the cycle bound retires almost every rig" | **`cislunar` raw** only; the calendar bound does 42% at `cislunar` beneficiated and **80.79%** at `mars_surface` |
| "a programme's pace is set by orbital mechanics, not mining rate" | true of raw everywhere, and **inverts under beneficiation** at every destination except Mars |
| "the RTG option is correctly wired and very nearly unreachable" | it became reachable the moment the eclipse term landed, and was then found to be choosing on **mass** while the two sources differ 625x in price |

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
[What the model charges for](README.md#what-the-model-charges-for) defaults ON
and each moved every number when it landed. They are corrections, not options;
the flags exist to isolate an effect, not to be left off. **That list lives in
README because it describes what the model currently does**, and it is not
repeated here.

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

### A change can be numerically negligible and still destroy the evidence

This project's releases are argued from **bit-identity**, so an
operation-reordering "cleanup" is a change to the proof rather than to the
number. Four have been measured and refused on exactly this ground:

| tempting change | what it was worth | why it is refused |
|---|---|---|
| sort the phase table at source | removes ~325,000 sorts | the saturation block accumulates over its natural order, so the table is **load-bearing on the last ULP**: 2.8e-16 on 3 of 60 rows |
| rearrange `bracket > 0` into a launch-capacity comparison | one fewer term | re-associates the arithmetic and moves the boundary in the last bit, changing whether a marginal row **survives the prune** |
| `pd.read_csv(engine="pyarrow")` | **4.8x** on the 862 MB read, identical dtypes | its float parser rounds differently in the last ULP: 13 of 46 columns differ, and `estimated_mass_kg` moves 1e-13 relative. **Mass is what the ranking runs on** |
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
| inlining `builtins.max` | **1.2-2.4x** per call on Python 3.13, not the 6x recorded on an older interpreter; 18.7 M calls buys ~0.4% of a run | **closed.** ⚠️  cProfile attributes 2.5 s to it, which is dispatch overhead on a C builtin and is what will tempt the next person |
| the ratio-independent prologue hoist | **2.3%** of the default cell, 2.6% raw, of which ~89% is recoverable | declined: ~2% for splitting a 570-line function with ~40 locals crossing the seam. ⚠️  The **7.6%** this file quoted for three releases was stale |
| `integrity_check`'s second factorize | **0.454 s**, ~0.03% of a full raw pass | declined; it optimises the harness, not the pipeline, and every clean fix widens a contract. ⚠️  cProfile says 0.85 s; that is instrumentation |
| `_infer_from_albedo` by distinct value | 0.182 s to 0.028 s, 0.020 s fully vectorised: **~0.15 s**, 0.07% of Stage 1 | declined; see defect class 3 |
| `viability_only` on `max_return_payload_kg` | 519 ns of a 2,105 ns call, but only 31% of calls in a raw cell | declined at **under 1%** average, against a new branch in the hottest function in the model |
| the rig block in `_mission_cost_tail` | 3.2% priced alone | **taken in `1.17.5`**, once priced with the neighbour that shares its key. **Price the block, not the line** |
| Parquet instead of CSV for the catalog | 19.7 s to **2.1 s** | real and free, and not taken: it changes Module 1's output contract and no measured cell would move detectably |
| `nickel-iron`'s missing market ceiling | **7.7e-8** relative on one mission, 7.7e-5 at N = 100 | declined; it would break bit-identity on a destination not re-measured since `1.14.0`. Take it in that pass if `earth_surface` is ever re-run |

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

**The card is 7.6x slower than the CPU at the arithmetic this model is made
of.** That is the TU102's 1:32 FP64 rate and a property of every consumer
GeForce, not a tuning problem. fp32 is 1.6x faster and unusable, because every
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

⚠️  A full `check` builds ~20 cells and takes **roughly half an hour**: most of
it check 2, since turning the pre-filter off is precisely what v1.14.1 and
v1.17.4 exist to avoid. Iterate with `--skip prune parallel` (~5 min, and it
still catches any change to any number), then run the full set once before
committing. **A verification you will not run is worse than a slow one.**

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
list rather than starting a twelfth harness.**

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

## Config discipline

Configs are dataclasses instantiated once at module scope. Edit the field
default *inside* the dataclass, not the instance afterwards, mutating
`CONFIG.foo` after construction defeats having one editable source of truth,
and every module says so in a comment.

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
- **Re-run Stage 3 after upgrading it.** Every Module 3 column Module 4 reads
  is read defensively, so a stale `propellants.csv` does not raise; it
  reverts tank mass to zero, drops the maturity gate, and un-excludes solids
  and sails, all silently. `schema_check()` in `calc.py` now names each
  missing column and the behaviour it reverts; do not weaken it into a
  generic "columns changed" warning, because the consequence is the useful
  part.

  ⚠️  **`schema_check()` checks COLUMNS, not VALUES, and that is a real hole.**
  It checks Module 3 **rows** as well since v1.14.0; the ops table is keyed by
  category, so a missing *figure* was invisible to a column test, and
  `_MODULE3_REQUIRED_OPS` now names each row Stage 4 needs alongside the model
  term its absence silently reverts. That closes the missing-row half. The
  wrong-**value** half is still open and is the one below.

  Editing a number in a Module 3 table, a density, a status, a boil-off rate
, leaves the schema identical, so nothing warns and Stage 4 quietly runs on
  the old figure. This cost a full measurement pass during v1.12.0: the argon
  rows were rewritten, Stage 3 was re-run, the CSV did not actually land, and
  two full-catalog runs plus a determinism sweep were measured against the
  table that was being replaced. Nothing anywhere said so.

  The cheap habit that catches it: **Stage 4's loader prints row counts for
  every Module 3 table it reads** (`Module 3 propellants  41 rows`). Read
  those against what Stage 3 said it wrote. A count that has not moved after
  you added a row is the whole diagnosis. When only values changed and no
  count moved, spot-check the field itself out of the CSV before trusting a
  number, one `read_csv` on the row you edited.

  The deeper lesson from that pass is in "What v1.12.0 changed": the headline
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

**Every number committed before v1.0.9 was measured on the degraded catalog**
, roughly 1,900 real-taxonomy bodies instead of ~24,700. The V-type count is
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

Windows, Python 3.13, invoked as `py` (a bare `python` hits the Microsoft Store
alias and fails). The working tree is on Google Drive with the git directory
outside it; see the README's "Working copy" section, especially if the folder
gets renamed again.

### Entry points

Four consumers of the built `master.py`, all at the repo root because
`build_master.py` concatenates `modules/` from four explicit paths and asserts
a header/footer shape per file, plus two files that launch one of them, and
one that reads the docs rather than the model:

| file | what it is |
|---|---|
| `run_pipeline.py` | headless CLI: `--preset`, `--stages`, `--destination`, row caps |
| `ui.py` | Streamlit dashboard |
| `verify.py` | the six release checks |
| `verify_docs.py` | the seven **docs** checks; imports the four configs, never runs the pipeline |
| `run.bat` | Windows launcher, a terminal menu over the three above, no model behaviour of its own |
| `Dashboard.vbs` | double-click entry point, starts the dashboard with no console, ever |
| `launch_ui.py` | what it starts: supervises `streamlit run ui.py` and owns the stop button |

The first three import master **by name** with the repo on `sys.path`, which is
the only form the worker pool tolerates; see `_spawn_environment`, and the
table of harness bugs under "The verification harness is committed now".
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

Three Windows-specific traps were hit building it, each of which looks fine
from a console and is broken everywhere else, the same shape as the `set /p`
rule below:

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
  `:ui` delegates to `Dashboard.vbs`, which also leaves one windowless-start
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
reads the four committed cells of THE FULL CISLUNAR 2×2 directly, so it needs
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
theirs, the version-history blocks are this project's real changelog, and so
does every DATA string, because the `notes` fields in `PROPELLANTS_REFERENCE`
and `STORAGE_REFERENCE` are written into `propellants.csv` and
`storage_systems.csv`, and rewriting them would change CSV bytes. The
transformation was AST-driven and touched only the source segments of
`print(...)` calls for exactly that reason.

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
