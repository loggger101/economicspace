# Campaign findings (accumulating) - 2026-08-23

Code: catalog `1.1.1` | mineral_value `1.7.1` | transportation `1.12.1` |
calc `1.17.7` | master `1.20.8`. `master.py` rebuilt, `git status` clean.
Catalog: 1,555,667 rows (2026-08-11 snapshot). Stage 2 priced once per
destination on 2026-08-23, live prices verified identical across all five.
12 workers throughout.

## 1. The committed cislunar 2x2 reproduces EXACTLY on calc 1.17.7

Every headline, every share and every invariant, against a re-priced Stage 2
catalog and a catalog snapshot 1,267 bodies larger than some committed cells.

| | search OFF | search ON |
|---|---|---|
| raw | 26.7863x | 15.4272x |
| beneficiated | 20.5895x | 13.1443x |

Reproduced to the committed digit: evaluable 650,921 / 660,253; winner
2021 CX5 (D) in all four; New Glenn/xenon, New Glenn/iodine, iodine at
3.5186x, argon at 3.9249x; payloads 93,312 / 68,432 / 62,283 / 34,573 kg;
saturation 0.6873; p_mining 0.850 / 0.8858 / 0.850 / 0.9024; RTG
5.44 / 6.66 / 10.83 / 12.66%; aerocapture 0.00% in all four; New Glenn
overtaking Falcon Heavy in the default cell at 36.57 / 36.41%.

Invariants, all exact against the committed 2x2:
- never-worse, 4 of 4 pairings, zero exceptions; declined 102,765 / 102,427;
  max 0.996770 on the beneficiated search axis; 2 unchanged raw rows and 0
  beneficiated; medians +42.4% / +38.2% / +39.5% / +34.2%
- mass ledger max |error| 0.000000000 kg on all four cells
- N = F x W on every row; W > trips never; W < trips 2,077 (0.319%) raw and
  1,389 (0.210%) beneficiated; fleet median 2 max 64; N median 10

## 2. NEW - the first full-catalog runtime on the 1.17.x line

No full-catalog run had been made since `1.16.0`, so the five performance-only
releases had only ever been measured on 150-400 row cells. THE SAMPLING RULE
says a sample predicts full-catalog runtime here to no better than ~5x.

| cell | `1.16.0` | `1.17.7` | speed-up |
|---|---|---|---|
| raw, search OFF | 1,307 s | 733 s | 1.78x |
| raw, search ON | 3,890 s | 1,253 s | 3.11x |
| benef, search OFF | 9,300 s | 3,424 s | 2.72x |
| **benef, search ON** (the default) | **24,587 s** | **5,692 s** | **4.32x** |
| whole 2x2 | 39,084 s | 11,101 s | **3.52x** |

The gain is largest exactly where the default configuration sits, which is what
`1.17.1`, `1.17.2` and `1.17.5` were aimed at (the programme ladder) plus
`1.17.4` and `1.17.6` (the mass cascade and the per-row walk).

### Three committed COST RATIOS move as a consequence

These are ratios between two settings, which THE SAMPLING RULE explicitly
covers, and they are now full-catalog measurements:

| ratio | committed (`1.16.0`) | measured (`1.17.7`) |
|---|---|---|
| programme search, raw | 2.98x | **1.71x** |
| programme search, beneficiated | 2.64x | **1.66x** |
| beneficiation, search OFF | 7.1x | **4.67x** |
| beneficiation, search ON | 6.3x | **4.54x** |
| 2x2 corner to corner | 18.8x | **7.77x** |

## 3. NEW - 1.17.7's memory bound, measured rather than projected

`1.17.7` bounded `_CALENDAR_CACHE` against a PROJECTED 11-18 GB on a
full-catalog default cell, on top of a documented ~6 GB run peak - a projection
nobody could exercise, because no full-catalog run had been made since
`1.16.0` and a 400-row cell shows 18,000 cache entries rather than 70 million.

Measured on the default cell (beneficiated + searched, the one that actually
builds the ladder): total python RSS 4.36 GB at 13 min, rising to 8.6 GB at
92 min, peak 9.04 GB across the campaign; system 26.2 GB of 68.6 GB. The rise
is result accumulation in the parent (660,253 rows x 141 columns), not cache
growth - it tracks output size, not ladder traffic.

**The bound holds at full scale.** THE SAMPLING RULE now has a third quantity
confirmed under it: a stride sample does not predict a full run's memory, and
this is what the measurement looks like when the bound is in place.

## 4. lunar_surface 2x2 - THREE OF FOUR CELLS NEVER MEASURED BEFORE

| | search OFF | search ON |
|---|---|---|
| raw | 63.3505x (reproduces `1.14.0`) | **38.9904x** NEW |
| beneficiated | **35.8051x** NEW | **22.5790x** NEW |

Evaluable 586,054 raw / 606,304 beneficiated. Winner is **2021 CX5 (D) in all
four cells** - the same body that wins all four cislunar cells.

- raw/OFF reproduces the committed `1.14.0` 63.3505x exactly, with the same
  winner, iodine and Falcon Heavy, and propellant shares matching to the
  decimal (Xe 42.26 / Kr 22.64 / water 20.67 / I 10.29 / hydrolox 3.76 against
  the committed 42.3 / 22.6 / 20.7 / 10.3 / 3.8). Evaluable is 586,054 against
  the committed 585,710 - the +1,267 bodies JPL added between snapshots. **The
  ratio does not move**, which is the stronger statement.
- The stale `1.11.0` beneficiated placeholder for this destination was
  37.8133x on the OLD 89,367-row catalog. The real value is **35.8051x**.
- Aerocapture 0.00% in all four, as an airless destination requires.

### Beneficiation is worth far more at the Moon than at cislunar

| | cislunar | lunar_surface |
|---|---|---|
| median improvement, search OFF | +39.5% | **+63.8%** |
| median improvement, search ON | +34.2% | **+66.5%** |
| bodies declining to concentrate | 102,765 (15.8%) | **22,781 (3.9%)** |

Four times fewer bodies decline. Worth not "fixing": lunar water utility is
0.60 against cislunar's 1.00 (`IN_SPACE_UTILITY_BY_DESTINATION`), so the Moon
pays less for volatiles - and concentrating is exactly how a mission escapes
being carried by volatiles.

### Programme structure differs from cislunar

Fleet median **4** and N median **20** on lunar raw+search, against cislunar's
2 and 10. W < trips on 1,317 (0.225%) raw and 1,074 (0.177%) beneficiated.
N = F x W on every row and W > trips never, in both searched cells.

Krypton collapses 22.64% -> 6.40% under beneficiation, the same tank-mass
mechanism v1.11.0 documents and the 2x2 records at cislunar.

Runtimes: 572 / 867 / 2,660 / 4,508 s (total 2.39 h).

## 5. THE COMPLETE 20-CELL MATRIX (2026-08-23/24, calc 1.17.7)

Full 1,555,667-row catalog, 12 workers, 26.1 h of compute, zero failures.
Stage 2 priced once per destination on 2026-08-23 with live prices verified
identical across all five, so the destinations are comparable by construction.

Best cost/revenue, lower is better, 1.0 = breakeven:

| destination | raw N=1 | raw searched | benef N=1 | **benef searched** |
|---|---|---|---|---|
| **cislunar** | 26.7863x | 15.4272x | 20.5895x | **13.1443x** |
| lunar_surface | 63.3505x | 38.9904x | 35.8051x | 22.5790x |
| leo | 71.1029x | 36.6889x | 48.2714x | 24.4678x |
| mars_surface | 74.6748x | 41.8068x | 55.3403x | 30.6818x |
| earth_surface | 42,953.98x | 12,977.88x | 25,839.48x | 7,869.88x |

Evaluable rows: 650,921/660,253 | 586,054/606,304 | 776,755/882,429 |
731,322/892,563 | 784,242/912,846 (raw/beneficiated; the search does not
change the evaluable set).

**cislunar is still the best case, by a factor of 1.72 on the default cell** -
13.1443x against lunar_surface's 22.5790x. The destination ordering is
cislunar < lunar_surface < leo < mars_surface << earth_surface, which
reproduces the v1.14.0 raw ordering exactly and now holds on all four settings.

### Reproduction against the committed record

| cell | measured | committed | delta |
|---|---|---|---|
| cislunar, all four | 26.7863 / 15.4272 / 20.5895 / 13.1443 | identical | exact |
| lunar_surface raw N=1 | 63.3505x | 63.3505x | exact |
| mars_surface raw N=1 | 74.6748x | 74.6748x | exact |
| leo raw N=1 | 71.1029x | 71.1055x | -0.004% |
| earth_surface raw N=1 | 42,953.98x | 43,721.01x | **-1.75%** |

Also reproduced exactly on the raw N=1 row: aerocapture 0.00 / 0.00 / 93.107 /
82.002 / 95.749% against the committed 0.00 / 0.00 / 93.1 / 82.0 / 95.8;
RTG 5.439 / 3.957 / 8.240 / 6.506 / 8.461% against 5.44 / 3.96 / 8.24 / 6.50 /
8.46; ISRU 8.113 / 3.762 / 1.932 / 2.063 / 1.894% against 8.11 / 3.76 / 1.93 /
2.06 / 1.89.

### The drift ordering confirms a mechanism that was only ever argued

CLAUDE.md holds that `earth_surface` is priced straight off live terrestrial
quotes while an in-space kilogram is dominated by launch-cost-avoided, derived
through the rocket equation from CONSTANTS - so the control drifts and the rest
do not. Measured across a 12-14 day price gap, the ordering is exactly that,
and it is ordered by **how small launch-cost-avoided is**, not by distance:

  cislunar 0% = lunar_surface 0% = mars_surface 0% < leo 0.004% << earth_surface 1.75%

LEO is the CHEAPEST in-space destination to reach, so terrestrial price is the
largest share of its value among the four, and it is the only in-space cell
that moves at all. Mars is the furthest and does not move.

### Invariants: clean on all 20 cells

- **never-worse**: 20 pairings, **zero exceptions**, every max <= 1.000000
- **mass ledger**: max |error| 0.000000000 kg on all 20 cells
- **programme structure**: N = F x W on every row of all 10 searched cells;
  W > trips never

## 6. RETIRED - a `replicated`-scaling device DOES win, at mars_surface

CLAUDE.md's standing claim is "**A `replicated` device never wins anywhere** -
eight cells, zero wins", qualified by the warning that "on half the cells it
holds by a few percent, not by a factor, and a modest change to thruster mass
or to the population could flip one."

**The programme search flips it.** At `mars_surface`, raw, search ON:

```
rank 1  2014 YN     (M)  41.8068x  FEEP (indium field emission)  H3 (24L)   N=5
rank 2  2015 BM510  (M)  47.4127x  methalox                      Falcon Heavy
```

It wins by **13.4%**, carrying 6,667 kg of thruster for 96.7 kW. At N = 1 the
same destination still puts the best FEEP mission at **rank 5, 1.06x off** -
reproducing the committed figure exactly - so this is the search, not drift.

Best `replicated` mission per cell, rank and margin (0 survivors at
lunar_surface in all four cells, as committed):

| destination | raw N=1 | raw searched | benef N=1 | benef searched |
|---|---|---|---|---|
| cislunar | 39 (1.29x) | 283 (1.69x) | 8,602 (2.17x) | 12,020 (2.12x) |
| lunar_surface | none | none | none | none |
| leo | 62 (1.32x) | 1,145 (1.47x) | 1,770 (1.62x) | 19,197 (2.15x) |
| mars_surface | 5 (1.06x) | **1 (WINS)** | 73 (1.11x) | 14 (1.06x) |
| earth_surface | 7 (1.09x) | 5 (1.07x) | 13 (1.20x) | 10 (1.16x) |

The cislunar and earth_surface N=1 entries reproduce the committed ranks and
margins (39/1.29x, 8,602/2.17x, 7/1.10x). **The gate is not broken** -
`thruster_kg_per_n` is a mass penalty, not a threshold, and this mission pays
6.7 t of thruster and still wins. What is retired is the CLAIM, and the lesson
is the one that release note itself anticipated: a margin of a few percent is
not a law, and a new search axis was enough to close it.

## 7. NEW - market saturation is INERT at earth_surface, so its searched cells are not optima

`saturation_multiplier` across the searched cells:

| cell | min | median | max | fleet median | N median |
|---|---|---|---|---|---|
| cislunar raw | 0.358439 | 0.812837 | 0.999957 | 2 | 10 |
| lunar_surface raw | 0.536206 | 0.830467 | 0.999726 | 4 | 20 |
| leo raw | 0.704996 | 0.861486 | 1.000000 | 5 | 25 |
| mars_surface raw | 0.354904 | 0.750813 | 0.999996 | 2 | 10 |
| **earth_surface raw** | **1.000000** | **1.000000** | **1.000000** | **64** | **320** |
| **earth_surface benef** | **1.000000** | **1.000000** | **1.000000** | **64** | **320** |

At `earth_surface` the multiplier departs from 1.0 by a **median of 2.3e-11**
and at most **2.4e-7**, against cislunar's 1.9e-1. Terrestrial markets are
10^12-10^15 kg/yr (and 15 commodities take the unlimited default), against a
programme delivering ~10^7 kg - so the price never moves.

Consequently every lever improves with N, nothing pushes back, the objective is
**monotone in N**, and **100.00% of rows** - 784,242 raw and 912,846
beneficiated - run to `max_fleet_ships` = 64, N = 320, 64 concurrent missions.

**So 12,977.88x and 7,869.88x are the value at the ladder's TOP RUNG, not
optima.** Raise `max_fleet_ships` and they keep improving. CLAUDE.md already
says rows at that ceiling are "a diagnostic, not a result"; at earth_surface
that is the entire population, where cislunar runs 0.37-0.40%.

**This is v1.14.0's own failure mode surviving at one destination.** That
release fixed "market saturation could not see the programme it was written
for ... every lever pointed the same way and nothing pushed back" by making the
rate the programme's CONCURRENT output. The fix is structurally present here
and numerically inert, because Q/Q_market is 1e-11. It connects to
mineral_value `1.7.1`'s "measured and declined" note on `nickel-iron` having no
terrestrial market ceiling: that item was costed at 7.7e-8 relative **on a
single mission's multiplier**, which is correct and the wrong scope - with the
search on, the missing ceiling changes the SHAPE of the objective in N rather
than its level.

The other four destinations are unaffected: saturation bites hard at all of
them, and their fleet medians are 1-5.

## 8. Runtimes and shares

Wall clock per cell (s), 12 workers:

| destination | raw N=1 | raw search | benef N=1 | benef search |
|---|---|---|---|---|
| cislunar | 733 | 1,253 | 3,424 | 5,692 |
| lunar_surface | 572 | 867 | 2,660 | 4,508 |
| leo | 1,175 | 2,064 | 8,834 | 15,316 |
| mars_surface | 1,191 | 1,955 | 7,128 | 12,186 |
| earth_surface | 1,154 | 1,838 | 7,714 | 13,581 |

WARNING: `lunar_surface raw N=1` (572 s) and `leo raw N=1` (1,175 s) overlapped
an analysis process and are a few percent high. Every other figure is clean.

Winners: **2021 CX5 (D) takes 10 of the 20 cells** - all four at cislunar, all
four at lunar_surface, and two at leo. `2016 PN38` (M) takes all four
earth_surface cells. `mars_surface` is the only destination whose winner moves
on every axis: 8651 (M), 2014 YN (M), and **2001 UU92 (T)** beneficiated at
N=1 - the first T-type winner anywhere in this project's record.

Aerocapture resolves per destination exactly as the physics requires: **0.00%
at cislunar and lunar_surface in all four cells** (airless), 82-98% elsewhere,
rising under beneficiation at every atmospheric destination.

**The winner's vehicle is not the population's**, again: every winner flies a
New Glenn, Falcon Heavy, H3 or Long March while Falcon Heavy and SLS carry most
of every population.
