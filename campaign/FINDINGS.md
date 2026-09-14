# Campaign findings - 2026-09-11/13 - COMPLETE

The **28-cell** full-matrix campaign finished on 2026-09-13: seven destinations
x {raw, beneficiated} x {programme search off, on}, every cell on the full
1,555,667-row catalog. **28 of 28 cells, 47.14 h of queue time, zero failed
measurements**, 20 GB of archived catalogs under `cells/`.

Code under measurement: catalog `1.2.0` | mineral_value `1.9.0` |
transportation `1.14.0` | calc `1.21.2` | master `1.26.0`. `master.py` rebuilt
from `modules/`, `git status` clean afterwards, `verify_docs.py` and
`verify_stage3.py` green before the start, `platform_check.py` 18/18 probes
matching the reference host. 12 workers throughout.

🚨  **Nothing here is comparable cell-for-cell with the 2026-08 campaign**, kept
under `archive-2026-08_calc-1.17.7/`. Four things moved between them: two new
destinations, `market_model` defaulting to `capacity_cap` instead of
`elasticity`, `charge_insurance` defaulting False, and a fresh Stage 2 / Stage 3
price epoch.

## The matrix

Cost / revenue, lower is better, 1.0 = breakeven.

| destination | raw N=1 | raw + search | beneficiated | **benef + search** |
|---|---|---|---|---|
| **cislunar** | 15.3937x | 9.5435x | 14.1071x | **6.6622x** |
| mars_orbit | 16.8482x | 11.2682x | 13.3064x | **7.3681x** |
| geo | 45.6819x | 19.2670x | 19.0459x | 9.6949x |
| lunar_surface | 33.9418x | 21.1384x | 21.5387x | 11.5920x |
| mars_surface | 23.9964x | 18.6352x | 16.9920x | 12.6892x |
| leo | 58.5181x | 24.2815x | 42.9440x | 13.6875x |
| earth_surface | 40,147.9077x | 11,606.8561x | 24,169.7195x | 7,074.1975x |

No cell is profitable, at any destination, on any setting. That remains the
correct answer rather than a regression.

## What is new, and what it retires

### `mars_orbit` is the second-best destination in the model

Second at **all four** settings, within 10% of `cislunar`, and with **956,090
evaluable bodies** against cislunar's 660,253 -- 45% more asteroids can close a
beneficiated mission to a Mars-orbit depot than to a cislunar one.

✅  **This is the control working exactly as designed.** `mars_orbit` takes the
BASE utility profile -- its override dict is deliberately empty -- because a
depot in a 1-sol orbit competes with no local mining: everything martian is
4,100 m/s of ascent away, more than the 3,600 m/s of TMI that delivered the
cargo. **The ISRU discount that carries the `mars_surface` result is not a
property of Mars, it is a property of being ON Mars**, and this destination is
what proves it. Add that a main-belt body is cheaper to deliver to Mars than to
Earth, and distance is an advantage here rather than a penalty.

### `geo` is the worst in-space destination, and the most reachable of the cheap ones

45.6819x raw at N=1, the worst of the six in-space cells, while carrying
705,030 evaluable bodies -- more than `cislunar` or `lunar_surface`. The
objective is not a delivery-cost problem: `geo` is priced at $12,526/kg, ABOVE
cislunar. It is the utility table. `geo` is the first destination whose
overrides run downward on **metals and rock** rather than volatiles (iron 0.15
against cislunar's 0.70, olivine and carbon 0.05), because nobody launches
copper to geostationary orbit. GEO is a volatiles destination and nothing else,
so a mixed payload is carrying cargo the market will not pay for.

### The destination RANKING depends on the configuration

| | raw, N=1 | beneficiated + searched |
|---|---|---|
| 1st | cislunar | cislunar |
| 2nd | mars_orbit | mars_orbit |
| 3rd | mars_surface | **geo** |
| 4th | lunar_surface | lunar_surface |
| 5th | **geo** | mars_surface |

`geo` is 5th as a single raw mission and 3rd as a beneficiated programme,
overtaking two destinations. **"Which destination is best" is only answerable
per configuration**, which is a stronger form of the caution CLAUDE.md already
carries about propellant shares.

### A `replicated`-scaling FEEP device now wins TWO cells, not one

CLAUDE.md retired its "a `replicated` device never wins anywhere" law on one
cell -- `mars_surface` raw searched -- and warned the margin was thin enough
that a modest change could flip it. It flipped the other way: **2014 YN on FEEP
(indium field emission) now wins both raw `mars_surface` cells**, where in
2026-08 the best FEEP mission at N=1 sat at rank 5, 1.06x off.

⚠️  It does not survive beneficiation. Both beneficiated cells go to
conventional Hall thrusters on different bodies (krypton on 9992, iodine on
2003 RS1). Concentrating the ore changes the mass budget enough that 6.7 tonnes
of thruster stops paying, which is consistent with the gate being a mass
penalty rather than a threshold. Zero FEEP winners in the other 22 cells.

### The two levers are not interchangeable, and the split is per destination

Winner-row improvement from each lever alone, against raw N=1:

| destination | beneficiation | search | utility profile |
|---|---|---|---|
| cislunar | -8.4% | -38.0% | base |
| mars_orbit | -21.0% | -33.1% | base |
| lunar_surface | -36.5% | -37.7% | discounted |
| leo | -26.6% | **-58.5%** | base |
| **geo** | **-58.3%** | -57.8% | metals/rock near-worthless |

At `geo` the two levers are interchangeable to within 1%; at `leo` the search is
worth more than twice beneficiation. Beneficiation's value tracks how little the
destination pays for what you would otherwise ship.

## 🚨  The winner moved far more than the population did

**Every per-cell number reported during this campaign is a WINNER-ROW figure**,
and the population medians tell a different and much duller story:

| destination | benef, winner row | benef, population median | 2026-08 committed median |
|---|---|---|---|
| cislunar | -8.4% | **+39.4%** | +39.5% |
| lunar_surface | -36.5% | **+66.1%** | +63.8% |
| earth_surface | -6.5% | **+77.7%** | +77.7% |

⚠️  The two middle columns use opposite conventions and are not each other's
negation: the median is `median(1 - r)`, the committed convention, over the
whole evaluable population; the winner column is one row's change against its
2026-08 counterpart.

⚠️  **The population medians are nearly UNCHANGED from 2026-08**, while the
winner rows moved by 8-69%. So `capacity_cap` and the insurance removal
reshaped the TOP of the distribution and left the middle where it was. That is
the sharpest instance in this project of CLAUDE.md's rule that *a diagnostic
describes the winner, not the search that produced it*: a headline that moves
50% over a median that moves 0.1 pp is a statement about one row.

Population medians and decline counts, this campaign:

| destination | bodies declining to concentrate | benef median | search median |
|---|---|---|---|
| cislunar | 108,985 (16.7%) | +39.4% | +48.3% |
| leo | 86,090 (11.1%) | +41.2% | +59.6% |
| geo | 55,171 (7.8%) | +47.4% | +37.4% |
| mars_orbit | 60,908 (7.4%) | +33.0% | +41.4% |
| lunar_surface | 22,972 (3.9%) | +66.1% | +51.3% |
| earth_surface | 8,500 (1.1%) | +77.7% | +67.2% |
| mars_surface | 4,219 (0.6%) | +73.6% | +47.0% |

## Invariants: clean on all 28 cells

**70 OK verdicts, zero failures**, from `analyse.py` over the archived cells.

- **never-worse**: 28 pairings, every max <= 1.000000, worse 0, at all seven
  destinations on both axes
- **mass ledger**: `max |error| 0.000000000 kg` on all 28 cells
- **programme structure**: `N = F x W` on every row of all 14 searched cells,
  and `W > trips` never

### The structural change: programmes now decline the rig's last trips

| destination | `W < trips`, raw searched | 2026-08 |
|---|---|---|
| mars_orbit | **35.99%** | never measured |
| mars_surface | 32.73% | 3.71% |
| cislunar | 20.86% | **0.319%** |
| lunar_surface | 16.07% | 0.225% |
| leo | 8.09% | 0.161% |
| earth_surface | 0.270% | 0.234% |

Two orders of magnitude more programmes retire a ship with trip life unspent.
Under a hard ceiling the extra campaign cannot be SOLD, where under a demand
curve it could always be sold at a worse price. Fleet and programme sizes moved
with it: cislunar's fleet median 2 -> 6, N median 10 -> 30.

### `earth_surface` still runs to the ladder's top rung

Fleet median **and** max both 64, N median 320, `W < trips` on 0.270% of rows.

🚨  **`11,606.8561x` and `7,074.1975x` are therefore NOT optima**; they are the
value at `max_fleet_ships`, and raising that cap keeps improving them.
CLAUDE.md's warning survives the market-model change: terrestrial ceilings are
finite under `capacity_cap` and still far too large to bind, against a
programme delivering ~10^7 kg into markets running 10^12-10^15 kg/yr.

✅  Consistent with `earth_surface` being the destination LEAST changed by this
campaign: every cell moved -6.5%, where others moved -11% to -69%. Saturation is
numerically inert there, so the market-model switch does nothing and the whole
delta is the insurance removal -- inside the 5.5-9.6% band CLAUDE.md predicts
for it.

## Two questions this campaign closed

**`market_clearing_fraction` and `unsold_payload_kg` are not inconsistent.**
`geo` raw N=1 reports 0.9807 clearing beside 8,019 kg unsold of a 61,835 kg
payload -- 1.9% against 13%. They measure different things, deliberately split
in calc v1.21.0 so neither column carries two meanings: clearing is the share of
the load's **gross VALUE** that cleared, unsold is **MASS**. Low value in high
mass is exactly the GEO story.

**The `650,516` evaluable count in CLAUDE.md is not a discrepancy with either
campaign.** Both the 2026-08 and 2026-09 campaigns report **650,921** for
cislunar raw, identically. 650,516 belongs to a calc `1.15.0` run on a
**1,554,353-row** catalog snapshot, against the 1,555,667-row one both campaigns
used. Different catalog, not different code.

## What is NOT in this campaign

- **Insurance is off** in every cell (`charge_insurance` default False).
- **`elasticity` is not measured** anywhere here; every cell is `capacity_cap`.
- **Live prices drifted 9.0e-5 (gold) and 7.4e-5 (copper)** across the seven
  Stage 2 fetches, so **no cross-destination claim finer than 1e-4 is
  supported**. Nothing in this matrix comes within three orders of that.
- **Per-destination propellant, vehicle, rig-bound and cadence tables are not
  re-derived here.** The archived cells under `cells/` carry every column needed
  for them; only the winner row and the invariants were extracted.
- 🚨  **`leo__benef__search-on`'s ledger `wall_s` of 27,817 s includes a 74.7 min
  suspension** and must never go into a runtime table; the comparable figure is
  **~23,335 s**. See the pause section in `README.md`.

## Where these findings went

✅  **Promoted into the three main documents on 2026-09-13, so this file is the
campaign's own record and not a second copy of the results.** That is the split
this project runs on: name one authority, or you have two.

| finding | now lives in |
|---|---|
| the 28-cell cost/revenue matrix, the two new destinations, the ranking, the FEEP win | [README.md, Results](../README.md#current-results-the-complete-28-cell-matrix) |
| the 28-cell wall clocks | [README.md, Beneficiation](../README.md#beneficiation), pinned to `MEASURED_CELL_SECONDS` by `verify_docs.py` check 9 |
| the superseded 20-cell matrix, the per-cell wall clocks, the price-epoch evidence | [versions.md](../versions.md#the-28-cell-campaign-2026-09) |
| the invariants, the retired claims, what was NOT re-derived | [CLAUDE.md](../CLAUDE.md#the-complete-28-cell-matrix-is-measured-current-2026-09-1113-calc-1212) |

✅  **WHAT WAS NOT PROMOTED HAS NOW BEEN DERIVED: CLOSED 2026-09-14.** The
per-destination propellant, vehicle, rig-bound, cadence and saturation tables in
CLAUDE.md were still 2026-08 `elasticity` measurements with insurance charged,
because this campaign extracted the winner row and ran the invariants and
nothing else. `population.py` read the archived cells under `cells/` and
derived all of them in **one pass, about ten minutes, with no stage re-run**.
Per-cell JSON is under `population/`; the tables are in
[CLAUDE.md](../CLAUDE.md#the-rigs-two-bounds-and-the-cadence-at-every-destination-2026-09)
and the superseded 2026-08 ones in
[versions.md](../versions.md#the-population-re-derivation-2026-09-14).

🚨  **It changed four documented CONCLUSIONS, not four levels**, which is the
argument against ever leaving that kind of gap open: `mars_surface` stopped
being the exception to the beneficiated dig/window inversion, `saturation_multiplier`
turned out to be **identically 1.0 on all 28 cells** and therefore dead as a
diagnostic, "ISRU tracks hydrolox to within 0.03 pp" failed at three
destinations, and iodine went from winning two beneficiated cells to three.

✅  **The derivation reproduces all 28 objectives in the matrix above exactly**,
plus every winner body, the `W < trips` values and the fleet-cap percentages,
which is what makes it a measurement rather than another harness to have to
trust.

⚠️  **The cheapest open item in the project stayed open for three days anyway.**
The campaign cost 47 h of queue time and archived 20 GB precisely so questions
like these would not need a re-run. The data was never missing; the reader was.
**When a section says "not re-derived", check whether the inputs are already on
disk before believing the cost.**
