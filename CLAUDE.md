# Notes for working in this repo

Context for anyone (human or agent) editing this pipeline. The README covers
what it does and how to run it; this file covers what will bite you.

## master.py is generated — never edit it

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

Current: catalog `1.1.0`, mineral_value `1.7.0`, transportation `1.12.0`,
calc `1.16.0`, master `1.19.0` (the master version is a literal in
`build_master.py`'s `MASTER_HEADER` and `MASTER_ORCHESTRATOR` — two places).

⚠️  **calc `1.16.0` charges programme calendar time, and like `1.15.0` it moves
numbers only for programmes.** It is exactly inert at W = 1 — one campaign per
ship — which is every N = 1 run, which is every measured cell in this file
except the N = 10 / N = 100 curve. Verified rather than argued: at N = 1 the
400-row raw cislunar sample is **141 of 141 columns identical, sha256 MATCH**
with the term on and off. Do not re-measure a single-mission cell on account of
it. The N = 10 / N = 100 curve **does** move and is now a `1.14.0` measurement
of a model that has been superseded twice.

⚠️  **calc `1.15.0` moves numbers only for programmes, not for single missions,
and every measured cell in this file is a single mission.** Its two items — a
duty-cycle cap on rig life, and a searched programme size — are both inert at
N = 1, and the search is default OFF. Do not re-measure anything on account of
it; do not read any table below as covering an `optimise_programme_scale = True`
run, because only the one under "Measured — FULL CATALOG" does.

✅  **That inertness is not an argument, it is a full-catalog measurement.** A
1,554,353-row cislunar raw run on `1.15.0` returns **26.7863× on 650,516
evaluable rows with 2021 CX5 winning on xenon and a New Glenn** — the committed
`1.14.0` cell, reproduced down to the payload in kilograms and the propellant
split. It also puts `1.14.1` + `1.14.2` at a measured **4.10×** on a full cell
(5,350 s → 1,306 s), inside their projected 3.4–4.6×.

🚨  **The programme search costs 1.51× runtime, not the 1.04–1.13× this file
first recorded** from a 2,500-row sample. Third sample-mispredicts-runtime
finding in this project, and the first to apply to a *ratio* rather than an
absolute. See "Measured — FULL CATALOG".

calc `1.14.1` and `1.14.2` are the **second and third** stamps that do not mean
the numbers moved — same contract as `1.10.1`, and verified the same way. See
"What calc v1.14.1 changed" and "What calc v1.14.2 changed". Every measured cell
in this file was produced by `1.14.0` and stands unaltered; do not re-measure
anything on account of either.

Three of the five stamps in the `1.14.x` line are therefore performance-only,
which is worth noticing before reading a version number as evidence that a
result changed. The rule is one-directional: changing a number means bumping.

calc `1.10.1` was the first stamp that did **not** mean the numbers moved. It
was a pure performance release, verified bit-identical, and it was bumped
anyway so that a CSV still names the code that produced it — the rule above is
"changing a number means bumping", not "bumping means a number changed".

> ✅  **calc `1.14.0` / transportation `1.11.0` HAVE NOW BEEN MEASURED ON THE
> FULL CATALOG — six of the ten cells.** Measured 2026-08-09, on the
> 1,554,400-row catalog `1.1.0` (1,554,353 with positive mass), master
> `1.17.0`, `master.py` rebuilt from the modules with `git status` clean, 12
> workers. **These are the current numbers. Everything further down this file
> is older than they are.**
>
> | destination | raw `1.14.0` | evaluable | winner | wall clock |
> |---|---|---|---|---|
> | **`cislunar`** | **26.7863×** | 650,516 | 2021 CX5 (D), Xe, New Glenn | 5,350 s |
> | `lunar_surface` | 63.3505× | 585,710 | 2021 CX5 (D), iodine, Falcon Heavy | 5,118 s |
> | `leo` | 71.1055× | 776,266 | 2018 DT (M), Xe, Falcon Heavy | 10,063 s |
> | `mars_surface` | 74.6748× | 730,858 | 8651 (M), iodine, New Glenn | 10,275 s |
> | `earth_surface` | 43,721.0072× | 783,742 | 2016 PN38 (M), Xe, Falcon Heavy | 10,670 s |
>
> **Beneficiated, `cislunar` only: 20.5895×**, 659,847 evaluable, 38,072 s —
> 2021 CX5 again, on iodine, concentrating **3.519×**.
>
> **`cislunar` is still the best case at 20.5895×**, and not narrowly: it is
> 2.4× clear of the next destination on raw. That is now measured on the real
> population rather than inferred from a 15,566-row one.
>
> ⚠️  **Only `cislunar` has a like-for-like anchor, and it is the ONLY cell
> here that is a model delta.** Its raw cell moves 25.7035× → **26.7863×
> (+4.21%)** against `1.13.0` on the same catalog, which is the expected
> direction — v1.14.0 removes subsidies. The other four destinations had
> **never been run on the 1.55 M catalog at all**; their standing figures were
> `1.11.0` on ~31,000 evaluable rows. So those four rows are **first
> measurements, not deltas**, and no percentage change against anything above
> them is meaningful.
>
> ⚠️  **The four non-cislunar BENEFICIATED cells remain unmeasured on this
> catalog** — they are ~10 h (`lunar_surface`) to ~20 h (the rest) each and
> were not run. Do not fill them in from the `1.11.0` matrix below; that matrix
> is a different population *and* three releases of model behind.
>
> **8651 (M) is still the Mars raw winner**, exactly as on `1.10.x` and
> `1.11.0`, through a 17× population increase and three releases of model
> change. Winner identity surviving that is a stronger check on the Mars
> heliocentric leg than any ratio in this file.
>
> **The destination ordering has shifted.** `1.11.0` raw ran cislunar < mars <
> leo < lunar; it now runs **cislunar < lunar < leo < mars**. `lunar_surface`
> improved most in relative terms and Mars worst — consistent with v1.14.0
> landing hardest on volatile-rich missions, which is what the Mars result used
> to be carried by.
>
> ⚠️  **The programme-scale curve INVERTS, and that is still the headline
> result of this release rather than the ratios.** Market saturation could not
> see `nre_amortization_missions` at all, so "fly more missions" had no
> stopping point — the thing the term was written to prevent. On a **6,000-row
> stride sample of the OLD 89,367-row catalog**:
>
> | N | `1.13.0` | **`1.14.0`** |
> |---|---|---|
> | 1 | 38.4050× | 38.7886× |
> | 10 | 16.0296× | **16.4745×** |
> | 100 | **10.8935×** | **20.3246×** |
>
> The optimum programme size is **interior**, around N = 10. Every other
> programme-scale figure in this file was measured on a model in which more
> missions were free money.
>
> ✅  **Rebuilt on the full catalog 2026-08-10, raw, and the turn reproduces:**
> **26.7863× → 13.5836× → 18.3605×** at N = 1 / 10 / 100. At N = 10 one rig
> serves all ten missions back to back so `concurrent_missions` is still **1**
> and the saturation multiplier *improves*; at N = 100 the rig cap (12 at this
> stay length) forces **9 concurrent rigs** and the multiplier collapses to
> 0.5423. See "Mining reliability GROWS with programme size" for the full table
> — including that the winning vehicle gets *smaller* with scale, which the old
> model could not express. The beneficiated curve remains unmeasured.
>

> ℹ️  *Superseded by the v1.14.0 full-catalog block above, which re-measures
> this release's one cell and adds five more. Kept because the population
> argument below it is the reason those numbers are what they are — the
> `1.13.0` cislunar raw cell is now 26.7863× rather than 25.7035×.*
>
> 🚨🚨  **catalog `1.1.0` / calc `1.13.0` CHANGED THE POPULATION, SO EVERY CELL
> IN EVERY TABLE BELOW IS STALE.** The catalog goes from 89,367 asteroids to
> **1,554,400**. This is not a model change — not one term, coefficient or
> search axis moved — but nothing in this file survives it, because every
> figure here is "the best mission over the bodies we had", and we now have
> 17× more bodies.
>
> **Do not compare any run against a number below.** They were measured on a
> catalog that was a small, systematically inner-belt-biased subset of this
> one. Read "What catalog v1.1.0 / calc v1.13.0 changed" for what is measured
> so far and what is not.
>
> Measured at cislunar, **full catalog, raw** (2026-08-08, 2,539 s,
> 668,004 evaluable of 1,554,351):
>
> | | `1.12.0` | **`1.13.0`** | Δ |
> |---|---|---|---|
> | `cislunar` raw | 33.2342× | **25.7035×** | **−22.66%** |
> | `cislunar` beneficiated | 23.9169× | *not measured* | — |
>
> **The improvement is NOT an artefact of the H-derived diameters.** The best
> body on a **measured** diameter is 2016 GS2 at **27.0173×**, still −18.7%
> against `1.12.0`. Both it and the third-place 678927 were excluded by the old
> row cap rather than by the diameter requirement. **Removing the cap is what
> moved the headline; the derivation mostly deepens the population below it.**
>
> 🚨  **And the old catalog contained ZERO unnumbered asteroids** — all 89,367
> rows were numbered, 1 to 199,994. That is worse than a truncation and it was
> never noticed: JPL returns rows in SPK-ID order and numbered bodies come
> first, so **no provisional-designation body could enter the catalog at any
> cap below the full table**, whatever the cap was set to. The new catalog has
> **658,490** of them, plus 695,916 numbered bodies past the old ceiling.
> Recently-discovered NEAs are overwhelmingly unnumbered, and NEAs are what
> this model likes — 2021 CX5, 2016 GS2 and 2002 AT4 are all in that class.
> Every result this project has ever published was blind to it.
>
> The winner is **2021 CX5**, a D-type NEA at a = 1.63 AU and 82 m across, on
> xenon and a New Glenn. 7753 (B) and 4660 Nereus are both displaced. The top
> ten are all C/D/B/X-types between 1.34 and 1.87 AU and eight of them are
> under 500 m — small dark accessible NEAs, which is exactly the population a
> number-ordered row cap truncates.
>
> **26 bodies now beat the old best case of 33.2342×.**

> ℹ️  *Superseded — measured on the OLD 89,367-row catalog (15,407 / 15,566
> evaluable). Kept for the argon and thrust-gate findings, which are about
> mechanism rather than level. Note in particular that its "`cislunar` is
> still the best case" claim has since been re-checked against the real
> population and **holds**, at 20.5895×.*
>
> 🚨  **v1.12.0 MOVED EVERY NUMBER AND ONLY `cislunar` HAS BEEN RE-MEASURED.**
> Measured 2026-08-08 on transportation `1.10.0` + calc `1.12.0`, full
> catalog, against the same on-disk Stage 2 catalog the `1.11.0` cislunar
> cells were measured on:
>
> | | `1.11.0` | **`1.12.0`** | Δ |
> |---|---|---|---|
> | `cislunar` raw | 31.7712× | **33.2342×** | **+4.60%** |
> | `cislunar` beneficiated | 22.4665× | **23.9169×** | **+6.46%** |
>
> **`cislunar` is still the best case, now at 23.9169×**, and the winner is
> unchanged — 7753 (B), concentrating 5.311× against 4.955×. Both cells got
> *worse*, which is the expected direction: every item in v1.12.0 is a term
> that existed on one side of the model and not the other. See "What v1.12.0
> changed".
>
> ⚠️  **Evaluable rows roughly HALVED**, 31,186 → 15,407 raw and 31,510 →
> 15,566 beneficiated. That is the thrust-scalability gate: about half the
> catalog was only closing its mass budget on a micronewton thruster flown as
> a cargo tug. A population change that large invalidates any per-row
> comparison against an earlier run, not just the headline.
>
> ⚠️  **"Chemical propulsion is extinct in this model" is RETIRED.** It was an
> artefact of the same gap — hydrolox now wins 5.5% of rows at cislunar and
> methalox another 0.1%. Do not restore that claim from an older revision of
> this file.
>
> ⚠️  **The other EIGHT cells of the matrix below are `1.11.0` figures and are
> now stale.** They were not re-run: each needs its own Stage 2 pass and the
> full sweep is ~70 minutes. Do not quote them as current, and do not compare
> a fresh run at `leo` / `lunar_surface` / `mars_surface` / `earth_surface`
> against them — the two changes that move numbers (argon storage, the
> cargo-water array) are properties of the *mission*, so they move every
> destination, and `earth_surface` is **not** a control for either.
>
> ⚠️  **Every propellant-share figure in this file predates the argon split**
> and is stale for the same reason — argon's storage class changed, so "iodine
> 52% / argon 36%" and "Mars is the one destination that wins on argon" are
> both claims about a propellant that no longer exists in that form.
>
> Superseded: the 2026-08-07 reproduction's ten cells (they remain correct for
> calc `1.10.0`/`1.10.1` and are kept below for comparison), and the
> programme-scale curve 22.93× → 9.85× → 7.28×, which was measured at the old
> N=1 anchor of 22.93× and has **not** been rebuilt on `1.11.0` or `1.12.0`.
>
> Still stale and not fixable by re-running: the historical progression
> 2.2× → 14× → 39× → 34× → 25×, and any figure in the version-history comment
> blocks. That series is per-release, so rebuilding it means running old code.
>
> ⚠️  **`mars_surface` is not the best case — `cislunar` is.** That reverses
> `1a5e0c8` and it is still the single most important stale claim to watch
> for, because it is asserted in prose all over both files.

## When a number changes, grep the prose too

The recurring documentation failure here is not a missing table — it is a
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

So after changing any number, search for the superseded **claim**, not just
the digits: "best case", "still comes in", counts spelled out in prose and
headings, and the name of whichever destination used to win. Check that
summary paragraphs still agree with the tables below them in the same file.

## Model assumptions that are load-bearing

These were found by a realism audit and are easy to silently break again.

**`delivery_destination` must be set in TWO places, and they must agree.**
`MINERAL_CONFIG.delivery_destination` decides what a kilogram sells for;
`CALC_CONFIG.delivery_destination` decides the architecture that puts it
there. Disagreement prices the cargo at a depot while paying to land it in
Utah — Stage 4's `destination_check()` catches it and shouts, and in
`master.py` use `MASTER_CONFIG.delivery_destination`, which writes both.

⚠️  **It shouts on STDOUT, which is where a measurement harness is least likely
to be listening**, and `CALC_CONFIG.delivery_destination` defaults to
`earth_surface` while the on-disk Stage 2 catalog is usually the last
destination somebody ran — `cislunar`, for every measured cell in this file. So
importing `calc` and calling `build_profitability_catalog` straight off gives a
mismatched run, and a harness that pipes the output through `grep` for its own
result lines will filter the warning away and print a clean-looking number.

This was hit while measuring v1.15.0: two figures were recorded as "cislunar"
that were run against `earth_surface` prices, and the paired comparisons they
came from were still valid — both sides saw identical inputs — while the LEVELS
were not. **Set the destination explicitly in any harness**, and if you must
filter stdout, keep `MISMATCH` in the pattern.

**Every commodity is priced by destination, not just water** (Stage 2
v1.3.0). At an in-space destination a kilogram is worth its terrestrial price
**plus** `in_space_utility × launch-cost-avoided`, less the cost of refining
it on site. The *plus* is the point — v1.3.0 briefly replaced the terrestrial
price instead of adding to it, which quietly threw the material itself away.
Bulk iron goes from $0.50/kg to ~$2,747/kg in LEO. The in-space prices are
derived through the rocket equation in `delivered_cost_usd_per_kg()`, not
tabulated — but the utility factors are *engineering judgements*, and they
are the softest assumption in the whole pipeline. Treat them as a dial, not a
measurement.

**Utility is per destination, and the correction runs downward** (Stage 2
v1.7.0). One table used to serve every in-space destination, so olivine
captured the same fraction of its freight on the surface of Mars — a planet
made of olivine — as at a depot in empty space. The missing term is not
distance, it is **local competition: the alternative to importing is not
always launching from Earth**. LEO and cislunar have no local resources at any
price and keep the base profile as the calibration anchor;
`IN_SPACE_UTILITY_BY_DESTINATION` discounts the two surfaces against what they
can dig up (Mars water 1.00 → 0.25, carbon 0.40 → 0.02, silicates 0.25 → 0.02;
Moon water → 0.60, iron → 0.45). Ni/Co/Cu are undiscounted everywhere — no
concentrated ore of either body is known. Carbon is undiscounted on the Moon,
where solar-wind implantation leaves it at ~100 ppm.

Two things not to "fix" here. **Every override runs downward**, deliberately:
raising a utility is precisely how this table becomes a way to manufacture
viability. And **prices still rise with distance** — Mars freight is 10.6
kg-in-LEO per kg delivered and that dominates — they just no longer rise as
fast as the freight does, and the volatiles that carried the Mars result rise
least. Water at Mars is 2.7× its LEO price now against 11× before.

A settlement catalyst market for the PGMs (utility 0.05 at the two surfaces)
was **considered and rejected**, and the reason generalises: this module
prices each commodity with one $/kg and one market depth, and
`in_space_price_usd_per_kg` routes on unit price alone. Gold at a lunar base
would route "used in space" at $76,060/kg into a 25 kg/yr catalyst market,
beating $30,061/kg into a 3,000,000 kg/yr terrestrial one — a
five-order-of-magnitude cliff in market depth that the router cannot see. The
real behaviour is a blend (sell the first few kg in space, fly the rest home)
and the pipeline cannot express a blend. That needs a quantity-aware route
choice, not a bigger table.

**The import budget is split per commodity** (Stage 2 v1.7.0).
`IN_SPACE_ANNUAL_DEMAND_KG` had called itself one shared budget since v1.5.0
while the code handed every commodity the whole thing — a 20 t/yr Mars base
absorbed 20 t of water *and* 20 t of platinum *and* 20 t of olivine.
`_DEMAND_SHARE_BY_CLASS` partitions it (propellant 0.55 / structural 0.25 /
shielding 0.15 / chemical 0.05, asserted to sum to 1.0), and shares are per
*class* because within a class the commodities substitute for each other —
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
is literal — where an atmosphere exists the model prices both the aerocaptured
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
worth its terrestrial price *minus* the downleg (`downleg_cost_usd_per_kg` —
capsule + TPS + recovery + departure burn, ~$25,400/kg from LEO). Platinum at
a depot is ~$31,300/kg, not $0. Conversely, launch-cost-avoided is **additive**
to the terrestrial price, not a replacement for it. `value_route` records
which fate each commodity took.

**The payload mix is optimised, not specified.** `optimal_payload_mix` is a
fractional knapsack over `asteroid_phase_table` — fill the hold with the best
phase available, then the next. Greedy by $/kg is provably optimal here
because the phases are divisible and priced per kg. Both bounds (content and
purity) fall out of it; do not reintroduce them as separate clamps.

**So is the mission architecture, as of v1.10.0.** The search for one asteroid
now spans vehicle × propellant × return mode × propellant sourcing ×
rendezvous apsis × concentration ratio, and every axis is resolved for that
body. Aerocapture and ISRU used to be catalog-wide switches, which meant a
target whose best mission was propulsive got flown aerocaptured because some
other asteroid wanted it. If you add another architecture choice, add it to
this search rather than to `CalcConfig` as a global — and check the
never-worse invariant afterwards.

The check is a one-liner over two archived runs, and it had never actually been
run until 2026-08-07. Join the raw and beneficiated catalogs for a destination
on `designation` and assert `benef_ratio <= raw_ratio` row by row. Across all
five destinations — 165,843 asteroid × destination pairs — it holds with zero
exceptions, and the worst case is exactly 1.0000, which is beneficiation
declining and falling back on the `beneficiate=False` baseline. That is the
signature to expect: never worse, and equal wherever it declines. A max above
1.0 means the search is optimising something other than what gets reported.

**How hard to concentrate is searched, not derived.** Grade saturates at
`saturation_ratio` = 1/(frac_best × recovery); costs keep climbing. So the
optimum is usually strictly interior and `evaluate_combo` sweeps for it. Two
mistakes already made here, both of which *looked* principled:
  1. Driving the ratio to the maximum — made cislunar missions 4× worse.
  2. Driving it to saturation on principle — still made cislunar ~12% worse.
The search also always evaluates **not concentrating at all** (via
`beneficiate=False`), which is not the same as ratio 1.0 — that would still
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

**4.10× lands inside the projected 3.4–4.6× band**, which is the first time a
compounded sample-derived projection in this file has been checked against a
full run — and it is the *narrow* kind of projection (a ratio over identical
rows), not the wall-clock kind the note below warns about. Every other wall
clock in this section is still `1.14.0` and still high by roughly that factor.

🚨  **And the run reproduced the committed cell EXACTLY, across three
releases.** `26.7863×` on `650,516` evaluable rows with **2021 CX5** winning, all
three identical to the `1.14.0` figures at the top of this file. That is the
strongest form the "performance only" claim has ever been checked in: `1.14.1`
and `1.14.2` each asserted bit-identity on 150–2,500-row samples, and `1.15.0`
asserted inertness at N = 1 on 400 rows. **All three now hold on 1.55 million
bodies at once.** Do not re-measure the raw cislunar cell on account of any of
them.

⚠️  Do not multiply those two factors and quote the product as a runtime *in
general*. Both were measured on stride samples, and this file's own rule is that
a sample predicts full-catalog runtime here to no better than a factor of ~5 —
the two speed-ups are ratios measured on identical rows in one process, which is
a much better-conditioned quantity than a projected wall clock, but the wall
clock they imply is still a projection. It happened to hold **for this cell**;
that is one data point, and the beneficiated cell is still unmeasured on
anything past `1.14.0`.

⚠️  **The timings in this file have moved seven times, for seven unrelated
reasons, and the fifth dwarfs the others.** Everything below is per
*catalog*, and catalog `1.1.0` made the catalog **17× bigger** — 89,367 rows
to 1,554,400. Cap `eval_row_cap` (which now *samples* rather than truncating —
see calc `1.13.0`) for anything interactive.

**Measured on calc `1.14.0`, full catalog, 12 workers, 2026-08-09** — these are
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
**10.6 h**, because the real full-catalog ratio is **7.1× raw, not 3.12×**. On
the 6,000-row v1.14.0 sample the ratio looked like **1.63×** — off by a factor
of four in the same direction.

Read that against the v1.1.0 note directly below, which records a sample
**over**estimating a run by 3.1×. So samples have now mispredicted full-catalog
runtime badly in *both* directions on this pipeline, for opposite reasons —
fixed costs dominate a small run, and the expensive tail of the concentration
sweep is under-represented in a stride sample. **The rule is not "samples
overestimate"; it is that a sample predicts full-catalog runtime here to no
better than a factor of ~5.** Budget from a measured full run of the same cell
or do not budget at all.

The ten-cell sweep is therefore **~3.5 days**, not "most of a day": the raw row
alone is 41,476 s (11.5 h) and the four unmeasured beneficiated cells are ~70 h
on top of cislunar's 10.6.

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
89 s / 462 s — raw unchanged, beneficiated up ~9%. That is `_cargo_water_kg`
calling the payload knapsack inside the fixed-point loop instead of once after
it, which is the price of sizing the array that bakes the cargo water. It was
measured before it was accepted (250-body sample: 19.8 s → 21.4 s, +8%). Only
cislunar has been re-timed; assume the rest of the table is ~10% low on
beneficiated, and the sweep **~75 minutes**.

The history, because each step is a different kind of change and conflating
them is how a stale timing gets quoted as evidence:

- `1.10.0` and earlier: ~140 s raw / ~2,120 s beneficiated. The ten-cell
  reproduction took about three and a half hours.
- `1.10.1`: ~33 s / ~137 s. A **pure performance release** — every number
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
reasons** — up because the model got more expensive (v1.10.0), down because
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
the binding constraint is **Pu-238 supply**, not money — DOE production is
~1.5 kg/yr, about one flagship RTG a year for the entire world. Do not extend
this to the EP array: that runs to hundreds of kilowatts, and pricing it off a
radioisotope row would quietly invent nuclear-electric propulsion.

**A propellant's tank is mass, and it scales with VOLUME** (v1.11.0). This is
the one to understand before touching the propellant table, because it is what
stops high-Isp low-density propellants running away with the answer. LH2 is
0.0708 kg/L against kerolox at 1.015 — fourteen times the tank per kilogram
burnt — and before v1.11.0 hydrolox got its 452 s with no volumetric penalty
at all. `tank_kg_per_L` is derived per storage class from flight articles
(hydrolox lands at 9.7% of propellant mass against Centaur's measured ~9.7%),
and it enters the closed-form cascade through `k = 1/(1 − t(R_ret − 1))` and
`k_out`. `t(R − 1) ≥ 1` means the **tank cannot close** and the combination is
infeasible, not merely expensive — the same condition Module 2 hits on
`δ·R ≥ 1`.

**Δv must stay per-asteroid.** Before v1.4.0 every asteroid got the same Δv,
which made `max_payload_kg`, `total_cost_usd`, `mission_duration_yr`, `vehicle`
and `propellant` single-valued across an entire catalog — the ranking was
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
iron-meteorite density — Psyche is ~3.8–3.9 g/cm³. Metal fractions are set
accordingly; don't restore the 0.80/5.30 values.

A default run produces zero viable missions. That is the correct answer, not
a regression. So does every other combination currently in the model.

### The v1.14.0 full-catalog matrix (CURRENT — measured 2026-08-09)

Best cost/revenue (lower is better, 1.0 is breakeven). Full 1,554,400-row
catalog `1.1.0`, mineral_value `1.7.0` re-run per destination, transportation
`1.11.0`, calc `1.14.0`, master `1.17.0`. Built artefact: `master.py` rebuilt
from `modules/*.py` with `git status` clean afterwards.

| destination | raw | evaluable | beneficiated | evaluable |
|---|---|---|---|---|
| **`cislunar`** | **26.7863×** | 650,516 | **20.5895×** | 659,847 |
| `lunar_surface` | 63.3505× | 585,710 | *not measured* | — |
| `leo` | 71.1055× | 776,266 | *not measured* | — |
| `mars_surface` | 74.6748× | 730,858 | *not measured* | — |
| `earth_surface` | 43,721.0072× | 783,742 | *not measured* | — |

**`cislunar` is still the best case, at 20.5895×**, by a factor of 2.4 on raw.

Winners, raw: **2021 CX5** (D, 82 m, a = 1.626 AU) at both `cislunar` and
`lunar_surface`; **2018 DT** (M) at `leo`; **8651** (M) at `mars_surface`;
**2016 PN38** (M) at `earth_surface`. Beneficiated at `cislunar` it is 2021 CX5
again, concentrating **3.519×** on iodine and a New Glenn against xenon raw.

Four things in that table worth not "fixing":

**Only the `cislunar` raw cell is a delta.** 25.7035× → 26.7863× (**+4.21%**)
against `1.13.0` on the same catalog and the same Stage 2 pass, so that one
number isolates the v1.14.0 model change and runs the direction every item in
the release pushes. The other four raw cells had never been run on this
catalog; they are first measurements against nothing.

**The `cislunar` beneficiated cell is also a first.** `1.13.0` left it
explicitly *not measured*, so **20.5895× is not a −14% move from 23.9169×** —
that figure was measured on 15,566 rows against this one's 659,847. There is no
beneficiated full-catalog predecessor to compare it to.

**Mars keeps 8651 (M) as its raw winner**, the same body as `1.10.x` and
`1.11.0`. A winner identity surviving a 17× population increase *and* three
releases of model change is a much stronger statement about the separate
heliocentric transfer than any ratio here.

**The ordering changed: cislunar < lunar < leo < mars**, where `1.11.0` raw ran
cislunar < mars < leo < lunar. Mars moved from best-of-the-rest to worst, which
is the same mechanism as v1.7.0's ISRU discount showing up again — v1.14.0's
containment charge lands on the volatile-rich missions Mars was carried by.

Propellant shares, raw, per destination — **every share figure in this file
predating this table is stale**, and the spread across destinations is the
point:

| destination | xenon | iodine | water ion | krypton | hydrolox |
|---|---|---|---|---|---|
| `cislunar` | 42.6% | 25.2% | 15.6% | 8.0% | 8.1% |
| `lunar_surface` | 42.3% | 10.3% | 20.7% | 22.6% | 3.8% |
| `mars_surface` | 57.8% | 19.9% | — | 15.4% | 2.1% |
| `leo` | 76.0% | 13.6% | — | 4.4% | 1.9% |
| `earth_surface` | 74.7% | 13.5% | — | 5.5% | 1.9% |

`cislunar` beneficiated: xenon 59.2% / iodine 17.1% / water ion 12.5% /
hydrolox 10.3% / krypton 0.5%.

**Xenon has taken over from iodine**, which reverses the v1.11.0 headline that
"iodine wins nine of the ten cells". That claim belonged to a model without the
eclipse term; sizing the plant for the night side reprices every electric
mission and the ranking among them moved with it. Chemical propulsion is *not*
extinct — hydrolox holds 1.9–8.1% everywhere.

**Aerocapture resolves per destination exactly as the physics requires**:
95.8% of `earth_surface` rows, 93.1% of `leo`, 82.0% of `mars_surface`, and
**0.00% at `cislunar` and `lunar_surface`**. Nobody asserted that; the airless
destinations ignore the flag and the search declines it on its own.

Launch vehicles, raw, per destination — measured on the same runs and never
recorded until 2026-08-11:

| destination | Falcon Heavy | SLS Block 1B | New Glenn | Vulcan VC6 | rest |
|---|---|---|---|---|---|
| `cislunar` | 66.43% | 31.59% | 1.68% | 0.13% | 0.17% |
| `lunar_surface` | 67.98% | 30.95% | 0.64% | 0.19% | 0.23% |
| `leo` | 69.56% | 21.33% | 8.80% | 0.24% | 0.07% |
| `earth_surface` | 66.47% | 23.34% | 9.86% | 0.25% | 0.07% |
| `mars_surface` | 79.94% | 10.72% | 5.70% | 2.61% | 1.03% |
| `cislunar` benef | 64.87% | 30.20% | 4.28% | 0.33% | 0.33% |

**Two vehicles carry 88–98% of every cell**, and the spread that does exist is
Mars': it takes the least SLS (10.7% against 21–32%) and the most Vulcan and
Ariane. That is the separate heliocentric transfer showing up in the vehicle
column — a Mars delivery pays no Earth capture, so its stacks are lighter and a
mid-class vehicle closes missions that need SLS anywhere else.

⚠️  **The winner's vehicle is not the population's.** Every raw winner in the
matrix above flies a New Glenn or a Falcon Heavy while New Glenn takes 0.6–9.9%
of rows. Do not read a share table as a statement about the best mission, or a
winner as a statement about the fleet.

**ISRU return propellant, share of rows**: `cislunar` 8.11%, `lunar_surface`
3.76%, `mars_surface` 2.06%, `leo` 1.93%, `earth_surface` 1.89%, and `cislunar`
beneficiated 10.33%. Each tracks its cell's **hydrolox** share to within
**0.03 pp** — 8.1097 against 8.1106 at `cislunar`, exact to four decimals at
`lunar_surface` — which is the consistency to expect rather than a coincidence,
since hydrolox is the ISRU route the search overwhelmingly takes.

⚠️  They are near-equal, not equal, and the residual runs **both** ways: at
`leo` and `earth_surface` hydrolox slightly *exceeds* ISRU (1.9493 vs 1.9292),
so a few missions buy hydrolox on Earth rather than make it, while at
`mars_surface` ISRU exceeds hydrolox (2.0606 vs 2.0522), so a few make
something else. Neither residual has been traced to a propellant, and the
water-ion share is not the place to look for it — `cislunar` runs 15.58% water
ion against 8.11% ISRU, so most water-propelled missions are carrying their
water up from Earth.

**Power source, RTG share**: `lunar_surface` 3.96%, `cislunar` 5.44%,
`mars_surface` 6.50%, `leo` 8.24%, `earth_surface` 8.46%, and `cislunar`
beneficiated **10.83%**.

⚠️  That retires "**RTG share falls 31% → 3.9%**" as a full-catalog figure. 3.9%
was measured on a 6,000-row sample of the *old* catalog. On the real population
the raw cells run **1.01× (`lunar_surface`) to 2.17× (`earth_surface`)** of
that, and `cislunar` beneficiated is **2.78×** it. Note the spread: the sample
happened to land almost exactly right for one destination and understate
another by more than double, which is the same "a sample is not the population"
lesson as the runtime estimate. The v1.14.0 conclusion — that searching beats
choosing on mass — is unaffected and if anything strengthened, since the branch
is reached more often than anyone had measured.

### Verification (2026-08-09, full catalog)

**1. Never-worse holds, and holds exactly**, on the `cislunar` pair — the only
destination with both settings measured:

```
pairs 650,516 | max benef/raw 1.000000 | exceptions 0 | declined (== 1.0) 102,703
```

That is the documented signature and nothing else: never worse, and equal
wherever beneficiation declines. 15.8% of bodies decline to concentrate.

ℹ️  That 15.8% is over the **650,516 joined pairs**. The beneficiated run's own
`concentration_ratio <= 1.0` column reports **15.61%**, over its **659,847**
rows — the 9,331 bodies that are evaluable beneficiated but not raw are in one
denominator and not the other. Both are right; quote which one.

**2. The mass-ledger identity holds exactly**, on every row of all six cells:

```
hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg
max |error| 0.000000000 kg   (650,516 + 659,847 + 585,710 + 730,858 + 776,266 + 783,742 rows)
```

**3. Serial and parallel are byte-identical** (cislunar raw, 2,500-row stride):

| | serial | 8 workers | speed-up | sha256 |
|---|---|---|---|---|
| raw, 2,500 rows | 77 s | 53 s | 1.45× | MATCH |

**4. 🚨  "Zero `replicated`-scaling devices survive" IS NO LONGER TRUE, and the
claim was a population artefact rather than a property of the gate.** At
`cislunar`, **13 raw and 327 beneficiated rows** survive on FEEP, where v1.12.0
measured zero across 15,407 / 15,566 rows.

This is **not** a leak. `thruster_kg_per_n` is a mass penalty in the rocket
equation, not an exclusion threshold — that was the whole design argument for
it, so that nobody has to name a cutoff. The survivors are carrying **4.4 to
16.7 tonnes of thruster** (median 13.2 t raw) for ~5 N, and they close only
because their payloads are 70–128 t and can absorb it. **None is remotely
competitive**: the best of them is 34.6× raw against the catalog best of
26.7863×.

So the check to run is not "do any survive" but **"does one ever win"**, and
the answer is no. Restating it as a count is what made a 15,566-row result
sound like a physical law. Same lesson this file already records for the RTG
branch: *how often a branch fires is a statement about the population, not
about whether the branch is right.*

✅  **THAT CHECK IS NOW ANSWERED AT EVERY DESTINATION** (2026-08-11), read off
the archived full-catalog CSVs rather than re-run. **A `replicated` device never
wins anywhere** — eight cells, zero wins:

| cell | survivors | share | best replicated | its rank | vs the cell's best |
|---|---|---|---|---|---|
| `lunar_surface` raw | **0** | — | — | — | — |
| `cislunar` raw | 13 | 0.002% | 34.6263× | 39 | 1.29× worse |
| `cislunar` benef | 327 | 0.050% | 44.6634× | 8,602 | 2.17× |
| `cislunar` raw, N = 10 | 378 | 0.058% | 28.0197× | 5,741 | 2.06× |
| `cislunar` raw, N = 100 | 471 | 0.072% | 46.0062× | 19,233 | 2.51× |
| `mars_surface` raw | 835 | 0.114% | **78.9916×** | **5** | **1.06×** |
| `leo` raw | 4,710 | 0.607% | 93.6443× | 62 | 1.32× |
| `earth_surface` raw | 5,479 | 0.699% | 47,861.1154× | **7** | 1.10× |

⚠️  **The honest statement is "never wins", NOT "never comes near", and the
cislunar cell is the one that makes it look comfortable.** At `mars_surface` a
FEEP mission is the **fifth-best body in the catalog**, 5.8% off the winner; at
`earth_surface` it is **seventh**, 9.5% off. Quoting cislunar's rank 39 and
1.29× as the margin overstates how much room the gate has. It holds at every
destination — but on half the cells it holds by a few percent, not by a factor,
and a modest change to thruster mass or to the population could flip one.

⚠️  **The survivor count spans 400× across destinations** — 0 at
`lunar_surface` against 5,479 at `earth_surface` — on one model, one catalog and
one release. That is the population argument far more sharply than a
15,566-row result could ever have made it, and it is exactly why the count is
not the test.

**Every survivor in every cell is FEEP**, 12,213 rows of it. Not one PPT and not
one electrospray row survives anywhere, at any destination or programme size —
where v1.12.0's pre-gate run had PPT winning **31.8%** of cislunar rows and
electrospray **24.3%**. Both are now absent from the model's output entirely;
only the lightest of the three `replicated` technologies (2,500 kg/N against
5,000 and 10,000) ever closes a mass budget at all.

### The v1.12.0 cislunar cells (superseded — measured on 15,407 / 15,566 rows)

| | `1.11.0` | **`1.12.0`** | Δ |
|---|---|---|---|
| `cislunar` raw | 31.7712× | **33.2342×** | **+4.60%** |
| `cislunar` beneficiated | 22.4665× | **23.9169×** | **+6.46%** |

Full catalog, **15,407 evaluable raw / 15,566 beneficiated** (against ~31,000
on `1.11.0` — see below), measured 2026-08-08 on transportation `1.10.0` +
calc `1.12.0` against the same on-disk Stage 2 catalog. Winner unchanged at
7753 (B), now concentrating **5.311×** against 4.955×; the raw winner is still
4660 Nereus, on iodine and a Falcon Heavy rather than electrospray and a New
Glenn. **`cislunar` is still the best case.**

Both cells got worse, and every item in the release pushes that way — see
"What v1.12.0 changed".

⚠️  **The evaluable population halved, and that is the headline result of this
release rather than the ratios.** ~15,700 bodies were closing their mass
budget only because the model would sell them a micronewton thruster as a
cargo tug. They are not marginal missions that got more expensive; they are
missions that were never physical. Any per-row comparison against a `1.11.0`
catalog is comparing different populations.

⚠️  **The argon correction moved neither headline cell and still changed the
answer for a quarter of the catalog.** Both ratios above are bit-identical to
a run made against the pre-argon tables — the best missions at cislunar were
never flying argon — while argon's share of chosen propellants collapsed from
25.0% to 2.4% raw and from 27.3% to 0.0% beneficiated, and 1,059 bodies became
infeasible outright. This is worth internalising before trusting any single
cell as a regression test: **the best case is a terrible detector for a change
that is wrong everywhere except at the top.** The propellant-share table and
the evaluable-row count caught it; the headline did not.

⚠️  **The other four destinations have NOT been re-measured on `1.12.0`.** The
table below is `1.11.0` and is kept because its *structure* is still the right
way to read the model, not because its numbers are current.

### The v1.11.0 matrix (fully superseded on raw; the beneficiated column is the last figure any non-cislunar cell has)

⚠️  **Read this table for its structure, not its levels.** Every cell is the
OLD 89,367-row catalog at 30,458–32,442 evaluable rows. The **raw column is
fully superseded** by the v1.14.0 full-catalog matrix near the top of this file.
The **beneficiated column is retained only because it is still the last figure
any non-cislunar destination has** — those four cells have never been run on the
1.55 M catalog. Treat them as an order-of-magnitude placeholder, not a
measurement of the current model: they are three releases and a 17× population
behind, and the one cell that *has* been re-measured (cislunar, 22.4665× here)
now reads **20.5895×**.

Best cost/revenue (lower is better, 1.0 is breakeven), measured 2026-08-08 on
transportation `1.9.0` + calc `1.11.0`, full catalog, 30,458–32,442 evaluable
rows per destination. The prior column is the 2026-08-07 reproduction on calc
`1.10.0`/`1.10.1`, so the delta is the mission-model change: tank mass, the
tanker bill, the RTG option, and a propellant search 4.6× wider.

| destination | raw `1.10.x` | raw `1.11.0` | Δ | benef `1.10.x` | benef `1.11.0` | Δ |
|---|---|---|---|---|---|---|
| `earth_surface` | 45,893.7× | 45,236.50× | −1.43% | 25,038.5× | 26,256.72× | **+4.87%** |
| `leo` | 72.4520× | 71.0459× | −1.94% | 48.1286× | 51.2223× | **+6.43%** |
| `cislunar` | 31.8269× | 31.7712× | −0.18% | **22.9336×** | **22.4665×** | **−2.04%** |
| `lunar_surface` | 75.8315× | 75.5110× | −0.42% | 40.6132× | 37.8133× | **−6.89%** |
| `mars_surface` | 70.4063× | 70.4346× | +0.04% | 51.8161× | 51.9597× | +0.28% |

**`cislunar` was still the best case at `1.11.0`, at 22.4665×**, and it was one
of the cells that improved. It is still the best case on `1.12.0` — at
**23.9169×**, per that release's own verification table.

⚠️  This sentence read "still the best case on `1.12.0`, at 22.7353×" until
2026-08-09. **That number was never measured anywhere.** It appears in no
table, in neither file, and it contradicts the v1.12.0 verification block three
sections above it, which records 23.9169×. It was almost certainly carried over
from an intermediate run and then quoted forward. Exactly the failure mode
"When a number changes, grep the prose too" exists to catch — a summary
sentence surviving the table it was summarising.

Winners, `1.11.0` beneficiated: 4660 Nereus (Xe, 2.469×) at `earth_surface`,
5620 (D, 4.444×) at `leo`, 7753 (B, 4.955×) at `cislunar`, 7753 (B, 4.816×) at
`lunar_surface`, 6178 (P, 7.071×) at `mars_surface`. **Four of the five
reproduce their `1.10.x` identity and concentration ratio** — only `leo` moved,
from 4015 Wilson-Harrington (B, 5.5×). Every raw winner is 4660 Nereus except
Mars, which keeps 8651 (M) exactly as before.

Four things in that table are worth not "fixing":

**Raw improved everywhere and beneficiated did not.** Raw moves −0.2% to −1.9%;
beneficiated splits, +6.4% at `leo` and −6.9% at `lunar_surface`. Those are two
different mechanisms pulling against each other. The **wider search** can only
help — 21 operational propellants against 7, and a strictly larger option set
cannot make a correctly-implemented search worse (that is the never-worse
diagnostic, and it is why the raw row is a check on this release rather than a
result). **Tank mass** can only hurt, and it hurts in proportion to mass ratio,
because `k = 1/(1 − t(R−1))` diverges as `t(R−1) → 1`. Beneficiation means more
feed, more power, a longer stay and more propellant, so it is where the tank
term bites; raw is where the wider search shows through cleanly.

**Iodine wins almost everywhere, and that is the tank term talking.** Nine of
the ten cells are won on iodine, which stores as a solid at ambient pressure at
4.93 kg/L and therefore pays **0.2%** of its own mass in tankage against
xenon's 1.9%. Chemical propulsion is essentially extinct in this model. Note
what this means: the tank term is only ~0.7% of launch mass in the *winning*
missions, because the search routes around it. Its effect is not a cost it
adds, it is **which propellant it disqualifies**.

> 🚨  **BOTH halves of that paragraph are RETIRED as of the 2026-08-09
> full-catalog measurement.** Iodine does not win nine of ten cells — **xenon
> does**, taking 42–76% of raw rows at every destination while iodine holds
> 10–25%. And chemical propulsion is not extinct: hydrolox holds **1.9–8.1%**
> everywhere. Only the *mechanism* survives — the tank term still works by
> disqualifying rather than taxing. What changed the ranking among the
> survivors is v1.14.0's eclipse term, which reprices every electric mission.
> See "The v1.14.0 full-catalog matrix (CURRENT)".

> ⚠️  The propellant SHARES that used to be quoted here — "iodine takes 52% of
> winners and argon 36%" across `earth_surface` — are stale as of `1.12.0`,
> because argon's storage class changed and its tank fraction went 2.1% →
> 22.9%. The mechanism above is unaffected and is in fact the point: argon was
> taking a third of the winners on a tank exemption it should never have had.
> On `1.12.0` at cislunar the split is iodine 58.6% / PPT 29.0% /
> electrospray 11.0% / xenon 1.0% beneficiated, and PPT 31.8% / iodine 26.8% /
> electrospray 24.3% / xenon 8.9% / krypton 4.9% raw. **Argon goes from 27.3%
> of beneficiated winners to 0.0%, and 25.0% of raw winners to 2.4%.**

**Mars barely moved (+0.04% raw, +0.28% beneficiated), and it was the only
destination that did not adopt iodine** — it won on argon at both settings.
That is a compositional/architectural result, not noise: the Mars leg is a
separate heliocentric transfer, and its winner identity (8651 M raw, 6178 P
beneficiated) reproduces `1.10.x` exactly.

> ⚠️  **That Mars result is the single cell most likely to have moved on
> `1.12.0`, and it has not been re-measured.** Mars was winning on argon at
> both settings, and argon is exactly what v1.12.0 corrected. Assume the Mars
> figures and the argon claim are both wrong until someone re-runs them.

**`earth_surface` moved 1.4-4.9%, and that is NOT drift.** It is not a control
for this release — see the note below the older table.

### The v1.7.0 pricing matrix (superseded, retained for the delta it measured)

Measured on catalog `1.0.9` / calc `1.10.0`, full catalog, 35,807 asteroids
fetched and ~29,600–35,000 evaluable per destination. Both columns were run in
ONE process on identical code, so the delta is attributable to the Stage 2
change alone. **These are still the correct figures for that code**; the
`1.7.0` column is the "prior" column of the `1.11.0` table above.

**Beneficiated:**

| destination | mineral_value `1.6.0` | **`1.7.0`** | change | `1.7.0` winner |
|---|---|---|---|---|
| `earth_surface` (default) | 25,110× | 25,038.5×† | −0.3%† | 4660 Nereus, Xe, 2.5× |
| `leo` | 47.17× | 48.13× | +2.0% | 4015 Wilson-Harrington, B, 5.5× |
| `cislunar` | 19.02× | **22.93×** | +20.6% | 7753, B, 5.4× |
| `lunar_surface` | 21.42× | 40.61× | +89.6% | 7753, B, 4.8× |
| `mars_surface` | **11.86×** | 51.82× | **+336.7%** | 6178, P, 7.1× |

**Raw:**

| destination | mineral_value `1.6.0` | **`1.7.0`** | change |
|---|---|---|---|
| `earth_surface` | 46,049.9× | 46,071.3× | +0.05% |
| `leo` | 65.97× | 72.45× | +9.8% |
| `cislunar` | 21.71× | **31.83×** | +46.6% |
| `lunar_surface` | 25.54× | 75.83× | +196.9% |
| `mars_surface` | **16.59×** | 70.41× | +324.4% |

† The one cell not from the paired run. It was measured on 2026-08-07, in a
separate process, when the whole matrix was reproduced (below). Its −0.3% is
therefore quote drift, not the pricing change — which, `earth_surface` being the
control, cannot touch it at all.

⚠️  **`earth_surface` is the control — for a Stage 2 change.** The v1.7.0
pricing change cannot touch it, because in-space pricing does not apply there,
so its raw +0.05% is the run-to-run noise floor from live price quotes moving
between the two loops. Do not "fix" a small earth_surface drift; do worry if it
ever gets large.

⚠️  **It is NOT a control for a Stage 3 or Stage 4 change**, and v1.11.0 is
both. Tank mass, orbital refuelling and a 4.6×-wider propellant search are
properties of the *mission*, not of where the cargo is sold, so they move
earth_surface exactly as they move everything else. If you are checking a
release of that kind, there is no control cell in this matrix — compare
against the previous run of the same code path instead.

**That ~0.05% is the WITHIN-process floor, and it is the wrong yardstick for two
runs on different days.** Across the 2026-08-07 reproduction the two
`earth_surface` cells moved −0.39% (raw) and −0.28% (beneficiated) while every
in-space cell reproduced to the hundredth. Same code, same catalog contents,
about eighteen hours of metal prices in between (`12b3d9f` was committed
2026-08-06 23:36). So the number to compare against depends on what you are
doing: ~0.05% between two loops in one process, but a few tenths of a percent
across a day, and both cells happening to fall is luck rather than a pattern.
Seeing 0.4% on a re-run tomorrow is not a regression.

That the in-space cells did *not* drift with it is the mechanism worth keeping:
`earth_surface` is priced straight off live terrestrial quotes, while an
in-space kilogram is dominated by launch-cost-avoided, which is derived through
the rocket equation from constants. The control moves and the rest does not.

### The matrix was reproduced end to end on 2026-08-07

All ten cells were re-measured through the Streamlit UI, one destination at a
time, from a catalog re-downloaded from scratch that morning. This is the first
time the tables have been checked against a *separate* run rather than against
the process that produced them.

| destination | raw measured | table | beneficiated measured | table |
|---|---|---|---|---|
| `earth_surface` | 45,893.7× | 46,071.3× | 25,038.5× | _(was pending)_ |
| `leo` | 72.4520× | 72.45× | 48.1286× | 48.13× |
| `cislunar` | 31.8269× | 31.83× | **22.9336×** | **22.93×** |
| `lunar_surface` | 75.8315× | 75.83× | 40.6132× | 40.61× |
| `mars_surface` | 70.4063× | 70.41× | 51.8161× | 51.82× |

Every in-space cell reproduced to the hundredth, and so did every winner
identity and concentration ratio the beneficiated table names — 4015
Wilson-Harrington (B, 5.5×) at LEO, 7753 (B, 5.4×) at cislunar, 7753 (B, 4.8×)
at the lunar surface, 6178 (P, 7.1×) at Mars. The `earth_surface` beneficiated
winner landed on 4660 Nereus (Xe, 2.5×), which is what the table had already
predicted for the cell it could not fill.

Two things this does and does not establish. It **does** show the pipeline is
deterministic given its inputs, which was not previously demonstrated — the
architecture search, the concentration sweep and the fixed-point power solve all
had to land identically. It does **not** revalidate the model; reproducing a
number says nothing about whether the number is right.

The catalog also came back identical where it matters: 35,807 rows, 24,675
measured taxonomies against 11,131 guessed from albedo, 2,614 V-types. Those are
the v1.0.9 reference figures exactly, so SsODNet answered and the population is
the documented one rather than a silently inflated substitute. Evaluable rows
ran 29,634–35,048 per destination, inside the range quoted above.

Four things in those tables are worth not "fixing":

**`cislunar` is now the best case, not `mars_surface`.** That reverses
`1a5e0c8`, which is where Mars took the lead and where the gap had been tracked
ever since. Mars was the best case *because* Stage 2 paid it full
launch-cost-avoided for water and carbon at a destination with metres-thick
mid-latitude ground ice and a 95.3% CO2 atmosphere. Price the local competition
and Mars goes from best of the four in-space destinations to worst. Cislunar
wins because an NRHO depot is the one destination with genuinely no local
anything, so it takes no ISRU discount at all — its whole +20.6% is the routed
market cap.

**The Mars winner changes identity three times**, which is the tell that this
is a compositional effect rather than a scaling one: 35678 (D) raw baseline →
4015 Wilson-Harrington (B) beneficiated baseline → 8651 (M) raw v1.7.0 → 6178
(P) beneficiated v1.7.0. Discount the volatiles and the optimiser walks away
from hydrated bodies. The Moon moves the opposite way — its winner goes
*toward* a B-type — because lunar water only falls to 0.60 while Mars water
falls to 0.25.

**LEO barely moves under beneficiation** (+2.0%) despite moving +9.8% raw, and
its winner and concentration ratio do not change at all. Concentrating to 5.5×
shifts the payload mix away from the commodity whose ceiling moved. A
destination that absorbs a change under beneficiation is not evidence the run
failed.

> That paragraph is about the **v1.7.0 pricing** change and stays true of it.
> Do not carry it forward as a general property of LEO: under **v1.11.0** LEO
> is the destination that moves MOST under beneficiation (+6.43%) and its
> winner does change, from 4015 Wilson-Harrington (B, 5.5×) to 5620 (D,
> 4.44×). Different change, different sensitivity — which is the point of
> recording which release a claim belongs to.

**Beneficiation now helps everywhere, including cislunar.** Under calc
`1.10.0`, cislunar goes 21.71× raw → 19.02× beneficiated at `1.6.0` pricing and
31.83× → 22.93× at `1.7.0`, concentrating 2.5× and 5.4× respectively. Still
true on `1.11.0`: 31.7712× raw → 22.4665× beneficiated at 4.955×.

⚠️  That **retires the `fa263ad` result**, which held that cislunar was the one
destination where the optimiser declined to concentrate the best body (39.79×
either way, unchanged to the hundredth). It no longer reproduces, and it was
retired by **calc `1.10.0`, not by this change** — the `1.6.0` pricing column
above already concentrates. v1.10.0 replaced the selection objective, and
"declines to concentrate" was an artefact of optimising `profit_usd` while
reporting a ratio. So the old warning has inverted: do not repeat "the
optimiser declines to concentrate at cislunar" either. What survives is the
weaker and still-true statement that the decision belongs to the
(target × destination) pair, not to the target.

✅  **The programme-scale curve was rebuilt on 2026-08-07** at cislunar,
beneficiated: 22.93× at N=1 → 9.85× at N=10 → 7.28× at N=100, replacing the
Mars figures 25.2× → 6.9× → 5.3×. See "Mining reliability GROWS with programme
size" below for the full table and for the two things in it that are not
constants.

⚠️  **That curve is calc `1.10.0` and has NOT been rebuilt on `1.11.0`.** Its
N = 1 anchor is 22.93× and that cell now measures 22.4665×, so the levels are
about 2% optimistic. The *shape* is unaffected and does not need re-running to
be trusted: `p_mining` is a function of N alone, and the rig cap is
`life / stay`, so neither depends on anything v1.11.0 touched. Rebuilding the
levels is three full beneficiated cislunar runs, ~25 minutes.

⚠️  **Still not re-measured, and not fixable by re-running:** the historical
progression 2.2× → 14× → 39× → 34× → 25×. It is a per-release series, so
rebuilding it means re-running old code, not just re-running the current
model.

Closing the remaining gap is not a tuning exercise. Rig terminal value and
in-space manufacturing were the named candidates and both shipped in v1.8.0
(`e860259`); the architecture search and the corrected selection objective
shipped in v1.10.0. What remains is joint trajectory/payload optimisation --
the EP stage is still sized to a fixed `ep_target_thrust_yr` rather than
having its trajectory optimised against payload and arrival date -- and
programme scale. Do not manufacture viability by editing `IN_SPACE_UTILITY`,
its per-destination overrides, or the in-space demand ceilings -- all three are
judgement tables and all three are load-bearing. v1.7.0 held its overrides to
running DOWNWARD for exactly this reason: a table that can be moved either way
to taste stops being a model.

The rig itself is the next obvious per-asteroid decision that is still a
global: `mining_hardware_kg` is 2,000 kg for a 500-metre NEA and for Ceres
alike, and it sets both the throughput cap and a big block of dead mass. It
was left alone in v1.10.0 because sizing it per target changes the meaning of
`max_payload_by_throughput_kg` everywhere it is read.

v1.11.0 closed three more, none of them by tuning: propellant tankage,
orbital refuelling, and the RTG option. Two of those three did not survive
v1.12.0's audit intact — the refuelling charge was billed against the wrong
scenario and is now gated off, and the RTG branch turns out to be reachable by
2 rows of 31,510. Only tankage did what it claimed. That is worth remembering
when reading any release note in this file, including this one: **a term
being implemented is not the same as a term being reached.**

What v1.11.0 **also** established is that the reference tables themselves were
a source of error, not just the code reading them — sixteen flown propellants
were missing, and the model was choosing the best of seven options while the
report claimed it had chosen the best available. v1.12.0 found the sharper
version of the same lesson: a table row can be wrong not by omission but by
**internal contradiction**, holding two incompatible physical states at once
and collecting the benefit of both. See argon.

✅  **Two of the three storage gaps are closed as of v1.14.0** — **volatile
cargo containment** and **eclipse / night-side power**. See "What v1.14.0
changed". The remaining one is **boil-off cannot be bought down** with a
cryocooler, and it is the one that runs *pessimistic*, so it is a gap rather
than a subsidy.

⚠️  Read how those two were closed before writing another "known limitation"
into this file. Every figure was already in `STORAGE_REFERENCE`, with its
citation, behind a "⚠️  Not modelled in Module 4" note — and Module 4 does not
load `storage_systems.csv`. The gap was documented in Module 3, quoted in this
file for two releases, and **writing it down was mistaken for closing it**.
A reference table nobody reads is not a model. If you record a gap, record
which consumer would have to change and check that it can even see the table.

✅  **Thrust scalability is gated as of v1.12.0**, and closing it was the
single largest correction in this release. It is written up under "What
v1.12.0 changed"; the short version is that Module 4 sized an electric stage
by POWER alone, so buying enough kilowatts turned any row in the propellant
table into a cargo tug. A third of winning missions at cislunar were on pulsed
plasma thrusters and a quarter on electrospray — devices that have flown, and
have flown producing MICRONEWTONS.

The gate is mass, not a threshold: Module 3 now carries `thruster_kg_per_n`
per technology and Module 4 derives the thrust its mission needs, so a device
that makes µN per kilogram reports thousands of tonnes of thruster and dies in
the rocket equation on its own. Same shape as propellant tankage.

## The twenty-two things the model stopped giving away

Each defaults ON and each moved every number. They are corrections, not
options; the flags exist to isolate effects, not to be left off.

One arrived in v1.16.0 and is under "What calc v1.16.0 changed": **programme
calendar time**, where a programme took decades and was charged for none of
them — the NRE and the rig are bought once at t = 0 and amortised across
campaigns one rig can only fly one after another, and every one of those shares
was compounded over a single mission duration.

One arrived in v1.15.0 and is under "What calc v1.15.0 changed": **the rig's
duty cycles**, where `missions_sharing_rig` divided a fifteen-**year** calendar
life by the stay and treated the quotient as the machine's whole life, so one
rig was good for twelve consecutive digs on a number that only ever promised it
would not corrode.

⚠️  **Those two are the only items on this list that are inert at N = 1.** Both
bound programmes rather than missions, which is why no single-mission cell in
this file moves for either — and why neither can be checked by re-running a
headline. The rest of the list moves every number in the model.

⚠️  **`optimise_programme_scale` is NOT on this list and must not be added to
it.** It is a search axis, not a correction: it defaults OFF, and turning it on
changes the question the run answers rather than fixing something the model was
getting free. The distinction is the whole reason this section exists.

Two arrived in v1.10.0 and are documented under "What v1.10.0 changed" rather
than repeated here: the **electric propulsion stage**, which was flown as mass
and never billed, and the **return vehicle's structure**, which did not grow
with its cargo.

One more arrived in v1.11.0 and is under "What v1.11.0 changed": **propellant
tankage**, which is mass in the rocket equation that scales with volume rather
than with the propellant inside it. (v1.11.0's **orbital refuelling** charge
was the fourteenth item and it has been *withdrawn* — see "What v1.12.0
changed". It was billing a real cost against a scenario this module does not
have, which makes it an error rather than a correction, and it is now gated
off.)

Four arrived in v1.12.0 and are under "What v1.12.0 changed": **thruster
scalability**, the biggest of them, where the in-space stage was sized on
power alone so a micronewton device could be bought as a cargo tug; **argon's
storage**, which took a cryogenic liquid's density and an ambient gas's zero
boil-off at the same time; the **cargo-water power plant**, which was billed
and never launched; and **propellant tank fabrication**, which was launched
and never billed.

Two arrived in v1.14.0 and are under "What v1.14.0 changed": **volatile cargo
containment**, where water was sold at a depot with nothing charged to keep it
from subliming on the way, and **eclipse / night-side power**, where the
processing plant was sized on a continuous draw as though the sun never set on
a rig standing on a rotating body. Both figures had been sitting in
`STORAGE_REFERENCE` since Module 3 v1.9.0 behind a note saying they were not
modelled.

Notice the shape almost all of them share. The mass cascade and the cost
cascade are written in different places, and nothing checks that every
kilogram in one has a price in the other — or that every kilogram the cost
model pays for is actually being flown. That is the bug class to look for in
this codebase first, and v1.11.0 introduced three fresh instances of it while
fixing three older ones. The one-line assertion that catches the whole family:

```
hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg
```

Argon is the exception and it has its own shape, worth learning separately: a
reference row that was internally inconsistent, holding two mutually exclusive
storage states at once. Neither number was crazy on its own. **Check that a
row's fields describe a single physical article** — the giveaway there was two
comments contradicting each other three lines apart.

**Low-thrust trip time.** `T = 2*eta*P/(Isp*g0)`, so burning m_prop takes
`m_prop*(Isp*g0)^2/(2*eta*P)` -- high Isp buys propellant mass at a QUADRATIC
cost in time-or-power. The EP stage is sized to finish inside
`ep_target_thrust_yr` and its array (1/r^2) plus thruster/PPU mass enters the
rocket equation -- and, since v1.10.0, the cost model too. Electric fell from
12% of winning combos to 2%. Validated
against Dawn: 5.0-9.3 yr predicted at its 2.2-3.0 AU operating distance vs
~5.9 yr flown. Evaluate at Dawn's 1 AU array rating instead and you get 1.0
yr -- if this check ever "passes" that easily, the 1/r^2 term has been lost.

**Launch windows.** Expected wait is half a synodic period. This punishes
NEAs HARDEST -- their periods sit near Earth's so phase drifts slowly, giving
a 10-year synodic period at a = 1.05 AU against 1.3 years for a main-belt
body. Delta-v accessibility and time accessibility are anticorrelated; do not
assume a low-Delta-v target is a fast one.

**Bound-water liberation.** C/B/D "ice" is water in phyllosilicates, baked out
at ~700 K. 2,500 Wh/kg. It was being extracted free and sold at full
launch-cost-avoided.

**Learning curve.** Wright's law 85% on the per-mission articles only. The
amortised mining rig is EXCLUDED -- it is one shared unit, not N built, so a
curve on it double-counts. Exactly 1.0 at nre_amortization_missions = 1, which
is what keeps a single-mission run unaffected.

**Market saturation.** `P/P0 = (1 + Q/Q_market)^(-1/eps)`, eps = 0.5. Without
it `nre_amortization_missions` had no stopping point: you could amortise
development across a fleet whose output would have destroyed the price that
justified it. The in-space absorption ceilings are judgement, not
measurement. Since Stage 2 v1.7.0 the destination ceiling is a total split
across commodity classes rather than a figure each commodity gets to itself,
and it follows the value route — see "The import budget is split per
commodity" above.

**Rig service life caps amortisation** (v1.8.0, cycles v1.15.0). A 15-year rig
cannot serve 100 missions of 2 years each. `missions_sharing_rig` is capped at
`life / stay`, and at long stays this makes the rig 13.8x MORE expensive per
mission than the old flat division, not less. Terminal value is credited only
when nre_amortization_missions > 1 -- a rig nobody returns to is stranded, not
an asset, which is what keeps a single-mission run unchanged.

⚠️  **`life / stay` alone was never the bound, and at SHORT stays it was barely
a bound at all.** `life` is fifteen *years* and describes corrosion, thermal
cycling and radiation dose; nothing bounded duty cycles, so a 1.25 yr stay made
one rig good for twelve consecutive digs. v1.15.0 adds Module 3's "Mining rig
maximum trips" (5) and takes the **min** of the two, so long stays stay
calendar-limited and short ones are cycle-limited. `rig_trips_per_ship` is the
single derivation; `rig_trip_limit_binds` reports which bound fired, per row,
because the two swap over at a stay of `life / trips` (3 yr at 15 and 5) and
neither is "the" cap. Terminal value now runs off whichever bound is binding —
paying salvage on remaining calendar years while the machine is mechanically
finished would refund a worn-out rig.

⚠️  **`trips` is a property of the MISSION, not of the asteroid.** The stay
depends on how hard the candidate concentrates, so two concentration ratios on
one rock are two trip lives. Do not cache it per body.

**Mission reliability multiplies REVENUE ONLY** (v1.8.0). Costs are charged in
full because you spend the money either way. Launch insurance replaces
hardware, not revenue, so it is not a double count -- do not "fix" that.

p_mining = 0.85 is counted from the FULL regolith-contact flight record --
10 successes, 1 partial (Hayabusa returned its sample despite the sampler
failing), 2 failures (Philae's harpoons, InSight's mole) = 11/13. The ten
are counted by PROGRAMME where a programme flew one design repeatedly and by
MISSION otherwise: Apollo 15-17 (1), Luna 16/20/24 (1), Stardust, Phoenix,
Curiosity, Hayabusa2, OSIRIS-REx, Perseverance, Chang'e 5, Chang'e 6. Count
them all as separate missions and you get a different denominator -- the
canonical roster with per-mission detail is the "Mining system first-of-kind
success probability" note in `transportation.py`, not this summary. v1.7.0 used 0.75, counted from the three failures alone with
none of the successes; that was selection bias and below even the pessimistic
0.77 reading. If you revisit this number, count both columns.

Sustained-operation risk is deliberately NOT folded into p_mining -- none of
those missions was sustained mining, and the exposure is already carried by
the spacecraft MTBF term. Adding it here double-counts.
**Mining reliability GROWS with programme size** (v1.9.0). Duane/AMSAA,
q(n) = q_first * n^(-0.30), capped at 0.95. Reported as the MEAN over
missions 1..N, not the terminal value -- NRE and the rig amortise across the
whole programme, so per-mission expected revenue must use the programme
average. Quoting the last mission's reliability would credit every mission
with heritage only the last one has. Exactly 0.85 at N=1.

Launch and cruise reliability deliberately do NOT grow: launch vehicles are
already mature, and MTBF is a duration exposure, not a heritage question. Do
not "complete" the model by adding growth to them.

Note how reliability growth and the rig service-life cap pull against each
other. Rebuilt 2026-08-07 at **cislunar**, beneficiated, on calc `1.10.0` +
mineral_value `1.7.0` -- cislunar rather than Mars because cislunar is now the
best case, and the curve belongs at whichever destination that is:

| N | best cost/revenue | p_mining | P(success) | missions sharing one rig | winning vehicle |
|---|---|---|---|---|---|
| 1 | 22.93x | 0.850 | 0.646 | 1 | Falcon Heavy |
| 10 | **9.85x** | 0.902 | 0.708 | 4 (capped) | New Glenn |
| 100 | **7.28x** | 0.943 | 0.739 | 4 (capped) | New Glenn |

✅  **REBUILT ON THE FULL CATALOG 2026-08-10** — cislunar, **raw**, all
1,554,400 rows, calc `1.14.0`. N = 1 is the measured headline cell; N = 10 and
N = 100 are 5,236 s and 5,489 s runs against the same catalog and Stage 2 pass:

| N | best cost/revenue | p_mining | saturation multiplier | concurrent missions | rig serves | winner | vehicle / propellant | payload |
|---|---|---|---|---|---|---|---|---|
| 1 | 26.7863x | 0.850 | 0.6873 | 1 | 1 | 2021 CX5 (D) | New Glenn / xenon | 93,312 kg |
| 10 | **13.5836x** | 0.902 | 0.7785 | 1 | 10 | 2002 AT4 (D) | New Glenn / krypton | 42,597 kg |
| 100 | 18.3605x | 0.943 | 0.5423 | **9** | 12 | 2021 CX5 (D) | H3 (24L) / iodine | 19,495 kg |

**The curve turns, and the optimum is interior** — −49.3% at N = 10, then back
up to −31.5% at N = 100. That is the v1.14.0 sample result reproduced on the
real population rather than inferred from 6,000 rows.

The mechanism is legible in the columns, and this is the part to understand
before touching `model_market_saturation`:

- **At N = 10 nothing is concurrent.** One rig serves all ten missions back to
  back (`missions_sharing_rig` = 10, `concurrent_missions` = **1**), so the
  market never sees two payloads at once and the saturation multiplier
  *improves*, 0.6873 → 0.7785. NRE per mission falls 10x and `p_mining` grows
  0.850 → 0.902. Every lever points the same way, which is why the old model
  looked right here.
- **At N = 100 the rig cap binds and saturation bites.** One rig serves 12
  missions at this stay length, so a hundred-mission programme needs
  ceil(100/12) = **9 rigs flying at once**, and the multiplier collapses to
  0.5423. That is what turns the curve, and it is exactly the term v1.14.0
  added.

Two things here that are NOT constants and were quoted as such above:

**The rig cap is 12, not 4.** It is `life / stay`, and this winner's mission is
4.2-4.4 yr rather than the older profile's. Do not carry "4 (capped)" forward.

> 🚨  **RETIRED BY calc `1.15.0`, and the reason is that 12 was never a life at
> all.** `life / stay` divides a **CALENDAR** figure — "Mining rig service
> life", 15 *years*, whose own Module 3 notes describe corrosion, thermal
> cycling and radiation dose — by the stay, and the result was treated as the
> rig's whole life. Nothing anywhere bounded **duty cycles**. So one rig was
> good for twelve consecutive digs on the strength of a number that only ever
> promised it would not have rusted meanwhile.
>
> Module 3 `1.12.0` adds "Mining rig maximum trips" (**5**, range 2-12) and
> `rig_trips_per_ship` takes the min of the two, so a long-stay mission stays
> calendar-limited and a short-stay one is now cycle-limited — which is the
> correct way round and was the entire gap. ⚠️  The 5 is a **judgement** and the
> row says so at length: nothing has ever mined an asteroid twice, so it is
> bracketed between terrestrial mining plant (overhaul at ~2-3 yr of continuous
> duty, in a workshop that does not exist at an asteroid) and the flight record
> for regolith-contact mechanisms (single-campaign by design, or failed inside
> one).
>
> **Every N = 1 figure in this file is untouched**, because at N = 1
> `missions_sharing_rig` is `min(1, trips)` either way. Measured: with the cap
> on and off at N = 1, the best cislunar raw cell is **60.9284× both ways** on
> the same 400-row sample. The cap changes the answer only for programmes, which
> is the whole point of it. `model_rig_trip_limit = False` restores `1.14.2`.

**The winning vehicle gets SMALLER with scale**, reversing the old curve's
Falcon Heavy → New Glenn. Payload falls 93,312 → 42,597 → 19,495 kg and the
vehicle goes New Glenn → New Glenn → **H3 (24L)**. Saturation punishes volume,
so at programme scale the model prefers more, smaller missions. The old curve
could not express this at all, because saturation could not see N.

✅  **And the WHOLE POPULATION moves the same way, not just the winner** —
recorded 2026-08-11 off the same three runs, never previously read out:

| | N = 1 | N = 10 | N = 100 |
|---|---|---|---|
| Falcon Heavy (57 t) | 66.43% | 69.76% | 58.99% |
| SLS Block 1B (105 t) | 31.59% | 25.66% | 25.06% |
| New Glenn (45 t) | 1.68% | 3.58% | **13.91%** |
| H3 24L (16.5 t) | 0.07% | 0.32% | **1.25%** |
| *capacity-weighted mean* | *71.8 t* | *68.5 t* | *66.6 t* |

New Glenn is **smaller** than Falcon Heavy in this table (45 t against 57 t), so
its 8× rise and SLS's fall are the same effect as the winner's, and the
capacity-weighted mean falls monotonically. The winner moves much further than
the fleet does — 93.3 t of vehicle to 16.5 t against the mean's −7.4% — which is
what you would expect from a term that bites hardest on the largest payloads.

**Propellant follows, and iodine takes over at scale:**

| | N = 1 | N = 10 | N = 100 |
|---|---|---|---|
| xenon | 42.65% | 39.90% | **15.46%** |
| iodine | 25.19% | 26.10% | **49.64%** |
| water ion | 15.58% | 18.71% | 19.39% |
| krypton | 8.01% | 9.45% | 9.53% |
| hydrolox | 8.11% | 5.00% | 4.89% |

Xenon loses two thirds of its share and iodine roughly doubles. Note this is the
*reverse* of what the eclipse term did in v1.14.0, which is what took xenon from
iodine in the first place — so the xenon/iodine ranking is not a property of the
model, it is a property of the model **at N = 1**, and every propellant-share
table in this file is a single-mission table. RTG share drifts 5.44% → 6.11% →
6.34%.

⚠️  **Three points, so "near N = 10" is the lowest of the points sampled, not a
located optimum.** The minimum lies somewhere between 1 and 100 and nothing
here pins it more tightly.

> ✅  **calc `1.15.0` locates it instead of sampling it**, and the reason three
> points was always the wrong tool is structural rather than a matter of
> budget: **the optimum N is provably an exact multiple of the rig's trip
> life**, so 1 / 10 / 100 were sampling a grid whose points mostly *cannot* be
> optimal. Within a fleet band the saturation multiplier is constant while every
> other lever improves with N, so the best N in a band is its top, N = F × trips.
>
> 🚨  **"Provably" is RETIRED by calc `1.16.0`.** The proof rested on "every
> lever improves with N and none pushes back", and programme calendar time is a
> lever that pushes back — it grows like `y^W` while NRE/N falls like `1/N`. So
> the optimum N need not be a multiple of the trip life, campaigns-per-ship is
> searched (exhaustively, not laddered), and the claim above is now only a
> *usually*. Measured: on the 400-row raw cislunar sample it still comes out at
> the band top on all 168 rows, so the answer survives even though the argument
> does not — but against a Module 3 table without the trip cap, 12 of 168 rows
> break it. **Do not restore "provably" from this or any earlier revision.**
>
> `optimise_programme_scale` searches the FLEET and lets N follow, jointly with
> every other architecture axis, at **1.51× runtime measured on the full
> catalog** — against one full run per N — because
> N enters nothing in the mass cascade. On a 2,500-row raw cislunar sample it
> moves the best cell **42.0081× → 21.7341×**, with fleets of 1-8 ships (N = 5
> to 40) and a median of 8 ladder rungs priced per mission.
>
> ⚠️  That is a **sample**, not this table's full-catalog population, and the
> table above is not superseded by it — it is a different measurement. What the
> table's three points cannot tell you is where the minimum is, and that is now
> answerable without re-running anything.
>
> ⚠️  And **`trips` is not a constant across this table's rows either.** It is
> `min(life / stay, max_trips)` and the stay depends on how hard the mission
> concentrates, so it varies per candidate, not just per body. See "What calc
> v1.15.0 changed".

⚠️  **This is the RAW curve.** The beneficiated curve above is not superseded by
it — it is unmeasured. Two beneficiated cislunar runs are ~21 h.

⚠️  Calc `1.10.0`. The N = 1 cell is 22.4665x on `1.11.0` and **20.5895x** on
`1.14.0` full catalog (measured 2026-08-09), so the cost/revenue column is
~10% optimistic throughout; the other four columns are unaffected by either
release. **And the SHAPE is wrong, not just the level** -- see the v1.14.0
correction below.

The winner is 7753 (B) at every N. The 10->100 step buys little because one rig
only serves 4 missions at this stay length, so mission 5 buys a new rig. "Fly
more missions" is real but sublinear, and bounded by market saturation at the
far end.

> 🚨  **"bounded by market saturation at the far end" WAS NOT TRUE, and every
> curve in this section was measured without it.** Market saturation never read
> `nre_amortization_missions` — the name appears in exactly four places in
> `calc.py` and none of them was the saturation block — so a 100-mission
> programme divided its NRE by 100, grew its reliability, and sold 100 payloads
> at the price ONE payload commands. Every lever pointed the same way and
> nothing pushed back, which is precisely what the term's own config comment
> says it exists to prevent.
>
> Fixed in v1.14.0: the rate is the programme's **concurrent** output,
> `ceil(N / missions_sharing_rig)`, derived from the rig service-life cap this
> module already computes. Exactly 1 at N = 1, so no single-mission figure
> moves — which is every headline figure on record.
>
> On a 6,000-row raw cislunar sample the curve stops being monotone and
> **turns**: 38.41× → 16.03× → 10.89× becomes 38.79× → 16.47× → **20.32×**.
> The optimum programme size is interior, near N = 10. **Treat the whole table
> above as measured on a model where more missions were free money**, and
> rebuild it before quoting any of it.

Two things changed against the old Mars curve (25.2x -> 6.9x -> 5.3x) beyond
the anchor moving. The rig cap is **4 here, not 7** -- it is `life / stay`, so
it is a property of the destination's mission profile, not a constant to quote
across destinations. And the winning **vehicle switches** from Falcon Heavy to
New Glenn at N >= 10: once NRE is spread across a programme, the per-mission
launch bill stops dominating and a bigger vehicle starts paying. `p_mining`
reproduced 0.850 / 0.902 / 0.943 exactly, as it must -- Duane/AMSAA growth is a
function of N alone and knows nothing about where the cargo goes.

**Cryogenic boil-off** (v1.8.0). Return propellant is held for years, so
hydrolox loads 2.5x what it burns on a 5-year mission. Folded into an
effective return Delta-v -- since m_return_prop scales with (R-1), inflating
that term by k is exactly R_eff = 1 + (R-1)k, which leaves the closed-form
cascade valid. ISRU is exempt. Without it hydrolox won missions it could not
have stored propellant for.

**In-space manufacturing is costed, not assumed** (v1.8.0, Module 2). ~$230/kg
for metals: energy at $6.08/kWh (the capital cost of a Watt in deep space,
~100x terrestrial) plus $200/kg of amortised refinery. It used to hide inside
the 0.70 utility factor. The plant's MASS is deliberately not in any mission's
rocket equation -- it belongs to the buyer at the depot, not to the miner.

Rank by `total_cost_usd / gross_value_usd`, not by `profit_usd`. Revenue is
orders of magnitude below cost in most configurations, which makes
`profit_usd ≈ -total_cost_usd`, so `top_profitable()` degenerates into a
pure cost ranking — a Δv table wearing a profit label. The ratio is the only
ranking that responds to both sides.

**And until v1.10.0 the code did not take its own advice.** Every per-asteroid
search — concentration ratio, vehicle, propellant — picked the candidate with
the highest `profit_usd`, i.e. the cheapest mission, and then the project
ranked the output by a ratio nothing had optimised. `selection_key` now makes
the objective lexicographic: maximise profit if any candidate is actually
profitable, otherwise minimise cost/revenue. `selection_objective = "profit"`
restores the old behaviour.

The diagnostic that finds this class of bug is worth remembering: **widening a
search must never make the reported answer worse.** It did — adding options
let a cheaper, far less productive mission win on profit while the reported
ratio got worse. Any time a new option degrades a result, the search is
optimising something other than what is being reported.

## What v1.10.0 changed

Four things, and two of them were asymmetries where a mass entered the rocket
equation but never entered the ledger. That is the failure mode to watch for
in this codebase: the mass cascade and the cost cascade are written in
different places and nothing checks that every kilogram in one has a price in
the other.

**The electric propulsion stage was free.** v1.7.0 sized the EP array and
thruster (`ep_system_kg`, `ep_power_w`), pushed them through the rocket
equation, and never passed them to `mission_cost_usd`. A 309 kW, 14-tonne
electric stage cost nothing, so electric propulsion won missions on hardware
nobody had to buy. Now priced in two parts, because they cost wildly different
amounts per kilogram: the array off the existing $800/W power-system row, the
thruster and PPU off Module 3's new `Electric propulsion system recurring
cost` at $1.5M/kW (NEXT-C anchored). This was invisible while the objective
preferred cheap missions and appeared the moment it stopped.

**The return vehicle did not grow with its cargo.** `return_vehicle_dry_kg`
was a flat 500 kg however much it carried, so the cascade happily loaded 125
tonnes of ore into a half-tonne can — 250:1 payload-to-structure, against 0.4:1
to 2:1 for real cargo spacecraft. The only other check was the launch
vehicle's fairing *volume*, which dense ore never fills.
`return_structure_frac_of_payload` (0.15) now scales it, and the closed-form
solver carries the term exactly: with `g = s·(1+f) − 1`, the payload formula
reduces to the old one when `f = 0`. Side effect worth knowing: this is also
what stops ISRU + propulsive return reporting an unbounded payload.

**Two architecture choices became per-asteroid.** `use_aerocapture_return` and
`use_isru_return_propellant` were catalog-wide switches even though the right
answer to both varies target by target, for the same reasons the vehicle and
propellant already did. Both now mean "available", not "mandatory", and the
profit search picks. Turning the search off (`optimise_architecture_per_asteroid
= False`) prices only the config's nominal architecture.

**ISRU stopped being magic.** The old switch deleted return propellant from
the cascade for every asteroid at a flat $50/kg. It never asked what the body
was made of — an M-type with zero ice made propellant out of nothing — never
asked what the propellant was, so it synthesised *xenon and argon* at a rubble
pile, and never charged the feed, the dig time or the bake-out energy, which is
the entire cost of ISRU. Now: at bodies with a non-zero ice fraction, hydrolox
at the stoichiometric 1.286 kg of water per kg of propellant (electrolysis
yields 8 kg O₂ per kg H₂; a 6:1 O/F stage needs 9/(1+6) kg of water per kg
burnt). The rock it takes comes off the rig's throughput and the body's
mineable mass *before* any ore is loaded. Default flipped to True, because
gated and costed it is an option a real programme would evaluate.

⚠️  **"Hydrolox only" was superseded by v1.11.0** and the tuple it was
hardcoded as is gone. Electrolysing water into cryogenic hydrogen and oxygen
is the hardest thing you can do with asteroid water, not the only one — a
steam rocket boils it at 1.00 kg of water per kg of propellant and buys that
at 190 s of Isp. The feed ratio and the feed material now come off the
propellant row. See "What v1.11.0 changed".

Also: the rendezvous apsis is searched rather than assumed (see below), and the
all-propulsive Earth-surface return finally pays the 100 m/s deorbit burn its
docstring had been claiming for four versions — it was numerically identical to
`ret_leo_prop`.

**Δv: which apsis you meet the target at is a search, not a rule.** The
estimator used `r_target = aphelion if aphelion ≥ 1 AU else perihelion`. That
is right for most main-belt bodies and wrong for high-eccentricity ones: an
aphelion rendezvous is a slow transfer with a cheap match burn and an expensive
departure, a perihelion rendezvous the reverse, and which dominates depends on
a and e together. For a = 0.6, e = 0.8 the rule cost 18.5 km/s outbound where
perihelion needs 12.1. Both apsides are priced now, and the winner is resolved
against the **destination** — a Mars delivery pays no Earth capture, so a body
best met at aphelion for an Earth return can be best met at perihelion for
Mars. The published validation figures are unaffected: Bennu, Eros, Itokawa and
both reference cases all still resolve to aphelion.

## What v1.10.1 changed

**Nothing you can measure.** It is a performance release and every number it
produces is bit-identical to `1.10.0`. That was checked two ways rather than
argued: serial and parallel runs over the same rows produce CSVs with the same
sha256 — cislunar beneficiated at 1,200 and 6,000 rows, earth_surface raw at
4,000 rows on ten workers, and mars_surface beneficiated at 2,500 rows on
eight, which also exercises the separate heliocentric transfer — and a
full-catalog run through `master.py` reproduced the committed cislunar cells
exactly: **22.9336×** beneficiated with the same winner and concentration ratio
(7753, B, 5.405×) and **31.8269×** raw.

Cislunar is the destination that was reproduced end to end because it is the
one the on-disk Stage 2 catalog is priced for. Checking another destination's
*value* means re-running Stage 2 first — pointing Stage 4 at a mineral catalog
priced elsewhere is exactly the mismatch `destination_check()` exists to catch,
and it does catch it. The other two destinations above were checked for
serial/parallel agreement, which does not depend on the prices being right.

A full beneficiated destination went from ~2,120 s to **137 s**, and raw from
~140 s to **33 s**.

**The main loop runs on every core.** Asteroids are independent — the search
reads the reference tables and writes nothing — so it had always been
embarrassingly parallel, and had always run on exactly one of twelve threads.
`parallel_workers` (0 = auto) now spreads it over a process pool.

Three things about that are worth not undoing:

- **Chunks are consumed in submission order** (`imap`, not `imap_unordered`).
  The order matters because the caller sorts on `profit_usd` with pandas'
  default quicksort, which is **not stable** — reordering arrivals would
  permute tied rows and make two runs of identical code produce different
  CSVs. The whole point of the release is that they don't.
- **Workers must not re-execute the wrong main module.** Windows has no fork,
  so a worker rebuilds the parent by importing `__main__` — and under
  Streamlit `__main__` is a synthetic module whose `__file__` points at
  `ui.py`, so the obvious `Pool()` runs the entire Streamlit app once per
  worker. That was reproduced, not theorised. `_spawn_environment` repoints
  `__main__.__spec__` at the pipeline module for the pool's lifetime.

  ⚠️  **The guard needs the pipeline module to be in `sys.modules` under its
  own `__name__`, and says nothing when it is not.** Write a measurement
  harness the obvious way — `spec_from_file_location("master", abs_path)` then
  `exec_module` — and master never lands in `sys.modules`, `own` resolves to
  `None`, `pin` is `False`, and every worker executes *your harness* as
  `__main__` instead. A sweep script re-runs its own sweep once per worker.
  Put the repo on `sys.path` and `import master` by name, then assert it:
  `assert sys.modules.get("master") is m and m.__spec__ is not None`.
- **More workers is not always faster.** Startup is ~1.1 s per worker and
  linear (each reads the 590 kB `master.py` twice, and on a Drive File Stream
  working copy those reads serialise). At 3,000 beneficiated rows twelve
  workers is *slower* end to end than six. `_resolve_worker_count` will not
  start a worker that cannot repay itself, which is why a small interactive
  run stays serial.

The ceiling is the six **physical** cores: hyperthreading adds ~17% on this
branch-heavy pure-Python workload, not 2×. Measured scaling net of startup is
1.95× / 3.43× / 4.48× / 4.89× / 5.24× at 2 / 4 / 6 / 8 / 12 workers.

**And ~1.9× of the gain is single-threaded**, which is the part that also helps
anyone running one process per destination:

- **Catalog rows are dicts in the hot path.** Every consumer reads a row with
  `.get(key)` or `[key]` and nothing else, but pandas resolves each of those
  through the index machinery at ~5 µs, and the search does ~7,400 per
  asteroid. That was ~38% of the entire run spent re-deriving positions in an
  index that never changes. `Series.to_dict()` unboxes numpy scalars to Python
  ones, which is value-preserving — `np.float64` *is* a C double — so the
  arithmetic downstream is unchanged. 1.73×.
- **The five ops-table constants the sizing loop needs are memoised.** They
  were looked up per (asteroid × vehicle × propellant × architecture × ratio):
  ~24 million lookups of five numbers that never move. 1.09×. (Six as of
  v1.11.0 — the RTG specific-power row joined them.)

If you add to the search, the thing to re-run before trusting a parallel
number is the serial/parallel sha256 diff — not the full reproduction, which
is a much slower way to catch the same class of mistake.

## What v1.11.0 changed

The reference tables held what somebody had happened to list, not what
exists. That sounds like a completeness nicety and it is not, because the
omissions were not random — **they all ran the same way**. Everything missing
from the propellant table was either a real option the search never got to
consider, or a real cost the model never got to charge.

Module 3 goes `1.8.2 → 1.9.0` (data and schema), Module 4 `1.10.1 → 1.11.0`
(the code that reads them), master `1.13.1 → 1.14.0`.

### Propellants: 7 rows → 40 (41 as of v1.12.0, which split argon)

Sixteen of the additions **have flown** and were simply absent — solid APCP,
UDMH/NTO, Aerozine-50, green monopropellant, HTP as monoprop and as
bipropellant, cold gas, krypton, iodine, water electrothermal and water ion,
hydrazine arcjet, electrospray, FEEP, PPT, and mercury ion. Krypton is the one
that should be embarrassing: by unit count it is the most-flown electric
propellant in history, because every Starlink v1.0 Hall thruster ran it.

Seven more are development hardware (nuclear thermal, nuclear electric,
solar-thermal, solar steam, VASIMR, MPD, metal/water) and nine are concepts
(Li/F2/H2, CO/LOX, mass driver, Orion pulse, direct fusion drive, antimatter,
magsail, tether, beamed laser-thermal). Those seventeen are **gated out of the
default search** by `operational_propellants_only`, which mirrors
`operational_vehicles_only` exactly. Ungated, a profit-maximising search flies
every asteroid on antimatter, so do not "fix" the gate.

Two further filters look like maturity gates and are not — they are about
whether a propellant can fly *this mission profile*, and they bind however
flight-proven it is:

- **`restartable`.** An asteroid return fires its second burn years after the
  first. A solid motor cannot be relit or throttled, so APCP is excluded
  permanently at TRL 9. It stays in the table because "we did not consider
  solids" and "solids cannot fly this profile" are different statements and
  only one of them is true.
- **`propellantless`.** A sail has no mass ratio, so the rocket equation
  reports that it moves any payload for free. Real sails run ~0.1 mm/s² of
  characteristic acceleration, falling as 1/r². Excluded rather than allowed
  to report infinity. Sizing one honestly needs a thrust-limited trajectory
  solver, which is the same gap that keeps the EP stage pinned to a fixed
  `ep_target_thrust_yr`.

### Tank mass is in the rocket equation

`density_kg_per_L` had been computed and exported since Module 3 v1.2.0 and
**read by nothing**. Tank mass scales with the volume it encloses, not with
the propellant mass inside it, so leaving it out was a straight subsidy to
whichever propellant had the lowest density — which is the same propellant
that has the highest Isp. The error compounded instead of cancelling.

`tank_kg_per_L` is derived per storage class and anchored on flight articles,
not asserted. As a fraction of the propellant it holds:

| propellant | tank / propellant mass | anchor |
|---|---|---|
| iodine (solid, ambient) | 0.2% | ThrustMe reservoir |
| xenon (COPV, 10 MPa) | 1.9% | Dawn |
| kerolox | 2.5% | F9 stage 2 |
| APCP motor case | 6.9% | Star 48B measures 6.4% |
| hydrolox | 9.7% | Centaur III measures ~9.7% |
| krypton (COPV, 18 MPa) | 12.5% | — |
| cold gas (COPV, 30 MPa) | 46% | — |
| bare LH2 (NTP, solar-thermal) | 53% | — |

The closed-form cascade generalises with two scalars rather than going
iterative: `k = 1/(1 − t(R_ret − 1))` on the return leg, where the tank flies
home inside the cargo's post-burn mass, and `k_out` likewise on the outbound
leg, where the tank is staged at the asteroid. Both are exactly 1 at `t = 0`,
so `model_tank_mass = False` reproduces v1.10.1. `t(R − 1) ≥ 1` is **"the tank
cannot close"** — the same condition Module 2 hits on `δ·R ≥ 1` — and it is
infeasible, not merely expensive.

Two things worth not undoing. The **two tanks are treated differently** because
they are used differently, and collapsing them would be wrong in both
directions. And the recomputation at the *capped* payload reads `k_ret` and
`k_out` back out of the solver rather than re-deriving them: two copies of this
algebra drifting apart is exactly how a mass ends up in one cascade and not the
other.

⚠️  The tank model is **SOFT and deliberately pessimistic**. Real tank mass is
a pressure term (∝ V, exact) plus insulation and minimum-gauge terms (∝ area,
so ∝ V^⅔). Collapsing both into ∝ V overstates the penalty on a very large
tank and understates it on a small one. NASA's large-NTP studies get an LH2
tank near 12-15% of propellant mass at ~38 t of hydrogen; this model says 53%
because its stages hold tonnes, not tens of tonnes. The direction is chosen:
the propellants that most want a generous tank model are the speculative ones.

### Three things the model was denying itself

- **The RTG row is finally read.** Module 3 priced radioisotope power in
  v1.2.0, with a note saying it is for past ~3 AU, and no code ever looked at
  it — so every main-belt body flew a photovoltaic array starved by 1/r², and
  distance was being punished for an architecture choice no real mission would
  make. Solar is 60 W/kg at 1 AU falling as 1/r²; an RTG is ~5 W/kg
  everywhere; they cross at **sqrt(60/5) = 3.46 AU**. Capped by
  `rtg_max_power_w` because the binding constraint is Pu-238 supply — DOE
  makes ~1.5 kg/yr, about one flagship RTG a year for the world — not money,
  and charged at its own $500k/W rather than the $800/W solar rate. **Not**
  applied to the EP array: that runs to hundreds of kilowatts, and pricing it
  as a radioisotope source would quietly invent nuclear-electric propulsion.
- **ISRU is no longer hydrolox-only.** v1.10.0 hardcoded `("hydrolox",)`,
  which was right about the chemistry it knew and wrong about the question.
  Electrolysing water into cryogenic hydrogen and oxygen is the *hardest*
  thing you can do with asteroid water, not the only thing: a steam rocket
  boils it and thrusts on the vapour at **1.00 kg of water per kg of
  propellant against hydrolox's 1.286**, with no electrolyser, no liquefaction
  and no cryogenic tank — and buys that at 190 s of Isp against 452. Which one
  wins varies by body, so it belongs in the per-asteroid search. The feed ratio
  and the feed *material* now come off the propellant row, and the
  water-liberation energy follows the propellant instead of a constant.
- **Orbital refuelling is charged.** Starship's escape payload (27 t) *exceeds*
  its GTO payload (21 t), which is impossible under any propulsion system
  unless the escape figure is for a vehicle topped up after reaching orbit.
  Module 3's own notes field has said so since v1.4.0 — including the fix,
  "Module 4 should add ~$90M × N_tankers" — and Module 4 never did. Twelve
  tanker flights at list price is **$1.08B on top of a $90M launch**.

### Launch vehicles: 12 rows → 36

Six operational (LVM3, Ariane 62, Long March 7, Vega C, PSLV-XL, Alpha), two
retired (Delta IV Heavy, and H-IIA — which launched Hayabusa2, the closest
flight heritage in the table to what this pipeline models), eight in
development, and eight **non-rocket** concepts: SpinLaunch, a light-gas gun,
StarTram, Skylon, Sea Dragon, a lunar mass driver, and the lunar and Earth
space elevators.

Read `max_accel_g` before the price column on those last ones. The kinetic
launchers do not have a cost problem — they are 10,000-30,000 g. That passes
propellant, water and steel billets, and destroys every mining rig, optic,
reaction wheel and radio in the catalog. A launcher that can lift only
consumables changes a mining programme's economics without lifting any of its
hardware, and this pipeline cannot express a split manifest.

The lunar-origin rows are excluded **structurally, not by status**: this module
departs from Earth, and their payload columns are annual throughput rather than
per-launch mass, so reading them would be a unit error, not just optimism. Of
everything in that section the **lunar space elevator** is the one not to
dismiss — unlike Earth's it needs no new material, because the Moon's shallow
well and the Earth-Moon L1 balance point put the required specific strength
inside what Zylon and M5 already deliver (Pearson 1979; Eubanks & Radley 2016).

### New table: storage systems

`STORAGE_REFERENCE`, 20 systems across four domains — propellant tankage and
cryocooling, cargo containment, onboard energy storage, in-space depots —
exported as `storage_systems.csv`. Storage had previously been one column.

Three gaps it documents that are **not** modelled, all of which run in the
optimistic direction on the current answer:

- **Volatile cargo containment.** The pipeline sells water at every in-space
  destination and has never once charged anything to keep it from subliming
  through a four-year cruise. Water is a large part of why the volatile-rich B
  and C types win.
- **Eclipse and night-side power.** `processing_power_w()` computes a
  continuous average draw and sizes the array off it, which assumes the sun
  never sets. A rig on a body with a 2-20 h rotation is dark about half the
  time and either carries the storage or mines at half duty cycle.
- **Zero-boil-off cooling.** Boil-off is applied passively, so hydrolox is
  charged the full 0.05%/day with no option to spend array mass and power to
  buy it down. That is conservative for hydrolox, and it is a gap rather than a
  decision.

### The search got 4.6× wider

357 (vehicle × propellant) combinations per asteroid against 77, from 21
operational propellants and 17 operational Earth-origin vehicles. Runtime
scales with it, so the v1.10.1 timings above no longer hold — see the timing
note in that section for what they were measured on.

### Measured effect

The full matrix is under "The v1.11.0 matrix (current)" above. The headline:
**`cislunar` remains the best case and improved slightly, 22.9336× →
22.4665×.** Raw improved at every destination (−0.18% to −1.94%); beneficiated
split, +6.43% at `leo` against −6.89% at `lunar_surface`.

That split is the useful diagnostic and it is worth understanding before
touching any of this:

- A **wider search cannot make the answer worse** — that is the never-worse
  invariant, and the raw row is where it shows uncontaminated, because raw
  does not amplify the tank term.
- **Tank mass hurts in proportion to mass ratio**, since `k = 1/(1 − t(R−1))`
  diverges as `t(R−1) → 1`. Beneficiation means more feed, more power, a
  longer stay and more propellant, so beneficiated is where it lands.

**The tank term's real effect is not the cost it adds — it is the propellants
it disqualifies.** In the winning missions tankage is only ~0.7% of launch
mass, because the search routes around it: iodine takes nine of the ten cells,
storing as a solid at ambient pressure at 4.93 kg/L for 0.2% of its own mass
against xenon's 1.9%. Across a full `earth_surface` run iodine wins 52% of
rows and argon 36%, while hydrolox wins 7 of 32,442 and methalox 30. Chemical
propulsion is effectively extinct in this model, and it was not extinct before
because iodine and krypton were not in the table to beat it.

> 🚨  **All four of those share figures are RETIRED.** Argon's 36% went first
> (v1.12.0 corrected its storage class). As of the 2026-08-09 full-catalog run
> the `earth_surface` split is **xenon 74.7% / iodine 13.5% / krypton 5.5% /
> hydrolox 1.9% / methalox 1.7%** — iodine does not take nine of ten cells,
> **xenon does**, and chemical propulsion is not extinct. The *mechanism* in
> this paragraph is the part that survives and is why it is kept: the tank term
> works by disqualifying rather than taxing. What reordered the survivors was
> v1.14.0's eclipse term repricing every electric mission.

Four of the five beneficiated winners reproduce their `1.10.x` identity AND
concentration ratio. That is worth noticing: a change that moved every number
left the *targets* almost entirely alone, which is what you would expect from
a change to how missions are priced rather than to which rocks are worth
visiting.

### Verification (2026-08-08)

Three checks, all on the rebuilt `master.py` at cislunar. Run these after any
change to the search; they are much cheaper than a full reproduction and catch
a different class of mistake each.

**1. The matrix reproduces on the built artefact.** The sweep ran against the
modules; the numbers below came from `master.py` after `build_master.py`, in a
separate process:

| | measured | sweep | |
|---|---|---|---|
| cislunar raw | 31.7712× | 31.7712× | MATCH |
| cislunar beneficiated | 22.4665× | 22.4665× | MATCH |

**2. Never-worse holds, and holds exactly.** Join raw and beneficiated on
`designation` and assert `benef_ratio <= raw_ratio` row by row:

```
pairs 31,558 | max benef/raw 1.000000 | exceptions 0 | declined (== 1.0) 655
```

That is the signature to expect and nothing else: **never worse, and equal
wherever it declines** — 655 bodies where beneficiation was evaluated and
rejected in favour of the `beneficiate=False` baseline. A max above 1.0 means
the search is optimising something other than what gets reported. This
mattered more than usual for v1.11.0, because widening a search is exactly the
operation that exposed the v1.10.0 objective bug.

**3. Serial and parallel are byte-identical.**

| | serial | 8 workers | speed-up | sha256 |
|---|---|---|---|---|
| raw, 4,000 rows | 56 s | 29 s | 1.94× | MATCH |
| beneficiated, 2,000 rows | 235 s | 62 s | 3.79× | MATCH |

Determinism survives the wider search. This is the check CLAUDE.md already
told you to run before trusting a parallel number after adding to the search,
and it is the one that would catch a worker seeing different reference data
from the parent.

## What v1.12.0 changed

A realism audit of the model's physical assumptions, prompted by v1.11.0's own
additions. Six findings, and **most of them are the same defect**: a term that
exists on one side of the model and not the other. That is the bug class this
file already tells you to look for first.

All of them move the answer the **same way: worse**. Cislunar raw 31.7712× →
33.2342× (+4.60%), beneficiated 22.4665× → 23.9169× (+6.46%). Cislunar is
still the best case and its winner is unchanged.

**The ratios are not the headline. The population is.** Evaluable rows halved,
~31,000 → ~15,500, because half the catalog was closing its mass budget on a
micronewton thruster the model was happy to sell as a cargo tug. Those are not
missions that got more expensive; they were never physical.

Transportation goes `1.9.0 → 1.10.0` (the tables), calc `1.11.0 → 1.12.0` (the
code that reads them), master `1.14.0 → 1.15.0`.

### The device was never modelled, only the propellant

The largest correction in this release, and the one that halved the evaluable
catalog. It is also the cleanest example of the asymmetry this whole project
keeps rediscovering, so it is worth stating in its general form first:

> **LAUNCH was modelled as an integrated vehicle with a payload it can
> actually lift. IN-SPACE propulsion was modelled as a bare specific impulse.**
> One side had a capacity limit and the other did not.

`PROPELLANTS_REFERENCE` has always been half a propellant table and half a
propulsion-system table — `isp_vac_s`, `restartable` and `dv_penalty_factor`
are all properties of the *device*, not the chemical. What it never carried
was anything about whether the device can be **built at the size this pipeline
flies**. So `_evaluate_combo_at_ratio` sized the electric stage on power:

```
P = m_prop·ve² / (2·η·t)      →  array mass, PPU mass, done
```

Buy enough kilowatts and any row became a cargo tug. The result, on a full
`1.11.0` cislunar run:

| propellant | raw winners | benef winners | largest unit ever flown |
|---|---|---|---|
| PPT (PTFE pulsed plasma) | **31.8%** | **29.0%** | EO-1, **860 µN** |
| Electrospray (ionic liquid) | **24.3%** | 11.0% | ST7-DRS, **5-30 µN** each |
| FEEP (indium) | <0.1% | <0.1% | IFM Nano, **0.35 mN** |

The pipeline was asking those devices for **~7-10 N**. Electrospray's own
notes field in this table said scaling it to a cargo stage "means millions of
emitters", and nothing read that sentence — the same
prescriptive-comment-nobody-applied trap as the Starship tanker note.

**The fix is mass, not a threshold**, which matters because a threshold would
have been a judgement call and this is not one. Thrust is momentum flux:

```
T = ṁ·ve = m_prop·(Isp·g0)/t          # owes NOTHING to efficiency
```

`ep_thrust_required_n()` computes it, Module 3's `_THRUSTER_SYSTEMS` supplies
`thruster_kg_per_n` per technology, and the product goes into the rocket
equation. A device that makes micronewtons per kilogram reports thousands of
tonnes of thruster and fails to close. Nobody names a cutoff, exactly as with
propellant tankage and `t(R−1) ≥ 1`.

The physical divide the table now records as `thrust_scaling`:

- **`continuous`** — thrust comes from a discharge or beam whose area you can
  enlarge. Scaling up means a BIGGER device, so kg/N stays roughly flat with
  size: 6 kg/N (hydrazine arcjet, MR-509) to 90 (NSTAR), everything mature
  landing in that band.
- **`replicated`** — thrust comes from discrete emitters, needles or pulses.
  Scaling up means MORE devices, so kg/N is fixed by the single unit and never
  improves: 2,500 (FEEP), 5,000 (PPT), 10,000 (electrospray).

**Efficiency was also one shared constant**, 0.60 for every electric row, and
it is nearly as decisive. A PPT converts ~8% of its input into jet power
against a gridded ion thruster's 70%, so it needs ~9× the array — and the
array is mass too. Now per-technology and measurably varying in output: 0.70
on 10,809 rows, 0.45 on 1,997, 0.35 on 1,878.

The old lumped `8 kg/kW` "thruster + PPU" row is what allowed this, because a
per-kW figure cannot express a per-newton constraint. It is split: the PPU
scales with power (4.7 kg/kW, NEXT-C's 34.5 kg at 7.4 kW) and the thruster
head scales with thrust. Together they reproduce NEXT-C to within 1% —
4.7×7.4 + 54×0.236 = 47.5 kg against 47.2 measured.

Four things worth not undoing:

**The thruster term is small for everything that survives.** Median 2.7% of EP
system mass, max 16%. As with tankage, its effect is not a cost it adds — it
is **which device it disqualifies**. Zero `replicated` rows survive anywhere in
either full run.

> 🚨  **That last sentence is retired as of 2026-08-09.** On the full 1.55 M
> catalog, 13 raw / 327 beneficiated rows *do* survive on FEEP — carrying
> 4.4–16.7 t of thruster, closing only because their payloads are 70–128 t, and
> **none of them competitive** (best 34.6× against 26.7863×). Survival was
> never the right test, because `thruster_kg_per_n` is a mass penalty rather
> than a threshold. **Test whether one wins.**
>
> That test is answered at all five destinations as of 2026-08-11 — **never, in
> eight cells** — and the margin is much tighter than cislunar suggests: rank 5
> at `mars_surface` and rank 7 at `earth_surface`, 5.8% and 9.5% off the
> winner. Survivors run 0 to 5,479 rows depending only on the destination, and
> every one of them is FEEP. See the v1.14.0 verification block near the top.

**Chemical propulsion is no longer extinct.** Hydrolox takes 5.5% of cislunar
rows and methalox 0.1%. The old "chemical is extinct in this model" line was
never a physical result; it was micronewton thrusters winning races they could
not enter.

**The guard in `_apply_thruster_data` raises rather than defaulting**, and it
tests `dv_penalty_factor > 1` — the same test Module 4 uses for `is_electric`.
Keying it off `type == "electric"` would have silently missed
`nuclear_electric`, direct fusion drive and antimatter. It caught all three
while this was being written.

**Iodine is the judgement call and it is load-bearing.** Its only flight unit
is ThrustMe's 1.1 mN cubesat thruster, which works out near 1,100 kg/N — but
that is an artefact of a 1U device, not a property of iodine, which runs in
Hall and gridded bodies that are the same hardware xenon uses. Entered at
60 kg/N against xenon Hall's 30, penalised for the heated feed and corrosion
tolerance it really needs. `status` cannot express "flown, but three orders of
magnitude below the scale we are modelling", and that is a gap in the schema
rather than in this number.

### Argon was a free resource, and the row said so itself

This is the one that moves the numbers, and it is worth reading in full
because nothing about it required any physics to spot — the row contradicted
itself in its own comments, three lines apart:

```python
"density_kg_per_L":    1.395,   # liquid NBP (cryogenic storage)
"boiloff_pct_per_day": 0.0,     # Stored supercritical at ambient temperature
```

1.395 kg/L is liquid argon, which exists only at 87.3 K. At 87.3 K it boils.
The row took the cryogenic liquid's **density** — hence the lightest tank of
any gas in the table, 2.1% of propellant mass — and the ambient gas's
**zero boil-off**, and paid for neither.

Measured at cislunar, argon was chosen for **25.0% of raw winners and 27.3% of
beneficiated winners**; correctly bottled it takes 2.4% and 0.0%, and 1,059
bodies stop being feasible at all. It also carried the entire Mars result at
both settings, which has not been re-run.

Split into the two articles that actually exist, and let the per-asteroid
search decide, which is this codebase's usual answer to "which one?":

| | storage | ρ (kg/L) | tank / propellant | boil-off | status |
|---|---|---|---|---|---|
| `Argon (Hall / ion)` | COPV, 18 MPa, ambient | 0.30 | **22.9%** | 0 | operational |
| `Argon (Hall / ion, cryogenic)` | liquid, 87.3 K, MLI | 1.395 | 2.1% | 0.024%/day | development |

The supercritical row is the one tagged operational because it is what has
**flown**. Every noble-gas EP system ever launched — xenon on Dawn,
BepiColombo and SMART-1, krypton on Starlink v1, argon on Starlink V2 — stores
its propellant supercritical in a COPV. No spacecraft has ever carried a
cryogen for an electric thruster. Tagging the liquid row `development` is the
same call the table already makes for VASIMR, and it is what stops the default
search flying an article nobody has built — which is exactly what the old row
did by accident.

Three things here not to "fix":

**22.9% is not a punishment, it is 1/M.** Tank fraction for a COPV is
`1.5·Z·R·T / (M·(PV/W))` — pressure cancels, because the bottle gets heavier
in proportion to what it holds. So xenon 1.9% / krypton 12.5% / argon 22.9% is
just M = 131.3 / 83.8 / 39.9 read backwards. Argon at 30 MPa pays 22.3%
against 22.9% at 18 MPa; the answer barely moves, and that robustness is the
tell that it is physics rather than a tuned constant.

**The density is derived twice, not asserted.** Peng-Robinson at 293.15 K /
18 MPa gives Z = 0.919, ρ = 0.321 kg/L; a generalised-compressibility reading
at Tr = 1.945, Pr = 3.70 gives Z ≈ 0.99, ρ = 0.298. 0.30 is between them. PR
reproduces the table's existing xenon row (1.86 against 2.00) but overstates
krypton, which is why two methods were used rather than one.

**The boil-off is derived from this table's own LOX figure.** Kerolox is
0.015%/day and its comment says only the LOX half boils, weighted by the mix
ratio; at O/F 2.30 that makes LOX alone 0.0215%/day. Scaling to argon at the
same tank and MLI is two ratios — heat leak ∝ ΔT, (300−87.3)/(300−90.2) =
1.014, and energy to boil ∝ ρ·h_fg, (1.141×213.1)/(1.395×161.1) = 1.082 —
giving 0.024%/day. Argon boils slightly **faster** than oxygen: 3 K colder,
and 8% less latent heat per litre.

### The cargo-water array was priced and never flown

The mirror image of the free EP stage. v1.7.0 charges liberation energy for
water sold as cargo, ~2,500 Wh/kg, and that energy sizes a power plant. The
term was added to `processing_power_watts` **after** `actual_cascade` had
already been built, so the array was billed in the ledger and never entered
the rocket equation. The comment there said "that extra power needs extra
array, **which the cascade already flew**". It had not.

The diagnostic is a one-liner and it is worth keeping:

```
hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg
```

On a fixed 400-body raw cislunar sample that failed on **97 of 357 rows**, by
up to 408 kg; beneficiated, 59 of 227 rows by up to 757 kg. It now holds on
every row of both full-catalog runs, exactly.

The worse half was the **raw** case: the sizing loop skipped the liberation
term entirely unless beneficiating or making propellant, so a raw mission to
an icy body paid for an array it flew none of. Fixed by moving the term inside
the fixed point, ungating it, and factoring the water estimate into
`_cargo_water_kg` so the loop and the post-loop settle-up cannot use different
expressions — which is what they were doing.

The settle-up now also runs **before** the cascade is rebuilt rather than
after, and `_downstream_of_hardware` is evaluated twice: once to learn how much
ISRU propellant the mission makes (which sets dig time, which sets the plant,
which is itself hardware), and again with the settled plant mass. The launch
stack is re-checked against the vehicle afterwards, because the closed-form
payload guarantee only holds at the hardware mass it was solved for.

This is the term that moves the **median** far more than the best case: 243.2 →
307.5 on the raw sample, +26.4%, because it lands on volatile-rich bodies and
the best cislunar mission is not one.

### Three smaller asymmetries

**Propellant tankage had no cost line.** Flown through the rocket equation
since v1.11.0, charged its launch $/kg because it sits inside `m_launch`, and
manufactured for free. New Module 3 row at $6,000/kg, Centaur-derived
(~1,880 kg of structure, ~$30M stage less ~$20M of RL10). It is 0.004–0.6% of
mission cost, median 0.012%, and it is kept precisely because it is small:
these are only ever found by checking every term rather than the big ones.

**Launch insurance under-booked the spacecraft.** Book value was rig +
capsule, which *was* the whole vehicle in v1.4.0. It never picked up the
v1.5.0 power plant, the electric stage v1.10.0 finally priced at $1.5M/kW, or
v1.11.0 tankage. A 300 kW electric stage is a nine-figure article and it was
flying uninsured. The rig enters at full build cost, not its amortised share —
losing it on ascent destroys the whole unit however many missions meant to
share it.

**`max_accel_g` was exported and read by nobody.** Module 3 added it in v1.9.0
expressly to disqualify the kinetic launchers and said so in the column's own
documentation. Only *maturity* was excluding them, which works today because
SpinLaunch and the light-gas gun are tagged `concept` — turn
`operational_vehicles_only` off and a 10,000 g slingshot at $6,250/kg enters
the search and wins on price, because nothing knew it would powder the rig.
`max_payload_accel_g` = 15 g: every real launcher in the table is 6 g or less,
SpinLaunch is 10,000, a light-gas gun 30,000, StarTram 30.

### And one that ran the other way

**The tanker charge was keyed to the wrong scenario.** Module 3's Starship
note asked for `$90M × N_tankers` **"in the escape-direct scenario"**; v1.11.0
implemented the arithmetic and dropped the scenario, levying it on every
mission.

This module has no escape-direct scenario. Grep it: Stage 4 reads
`payload_leo_kg` and `usd_per_kg_to_leo` and nothing else — the vehicle is a
LEO lifter, and the stack departs on its own outbound stage, which the rocket
equation sizes. Starship's 100 t to LEO needs no tankers; refuelling is what
buys the *escape* figure, which is never read. So the charge was $1.08B for a
capability the mission does not use.

Gated behind `escape_direct_launch`, which nothing sets, rather than deleted —
the day this module gains a direct-injection architecture the charge becomes
correct and the column is already wired. It is currently inert either way,
because Starship is the only vehicle with a non-zero tanker count and it is
`development`.

Note the shape: this is the *same* failure as the prescriptive-comment class
described above, but committed while fixing one. The note said what to do and
where to do it; v1.11.0 read the first half.

### The RTG option is correctly wired and very nearly unreachable

Worth recording because it looks like a feature and behaves like a rounding
error. v1.11.0 added radioisotope power so distant bodies would stop being
punished by a 1/r²-starved array. The crossover is 3.46 AU and 864 catalog
bodies (2.41%) sit beyond it, 856 with positive mass.

**It fires on exactly one row** of 15,566 — 18916, at 3.857 AU, drawing 4.4 W
into an 0.87 kg plant. Every other row is `solar`. The distant population is
not eliminated by array mass or by the 25-year duration cap (those bodies come
out at 4–5 years); it fails in the mass cascade on a 10–12 km/s outbound Δv
that an electric stage's 1.5× penalty turns into 15–18. The array was never the
binding constraint.

(It fired on *zero* rows before the thrust gate; the gate changed which
missions close, and one distant body came through. That is the correct
behaviour and it is also a good illustration of how little of the catalog this
branch touches.)

That is not an argument for removing it — the code is right, and it will
matter the moment the Δv model or the vehicle set changes. It is an argument
against quoting "the RTG option" as something that improved these numbers.

> 🚨  **RETIRED BY v1.14.0, and the reason is worth more than the section.**
> "The code is right, and it will matter the moment the Δv model changes" was
> half correct and the wrong half was the first half. Adding the eclipse term
> made photovoltaics roughly half as good per kilogram, which moved the
> crossover from 3.46 AU to about **2.1 AU** and put **31% of rows** on the
> nuclear side — and at that point the branch turned out to have been choosing
> on **mass alone** the whole time, while the two sources differ by **625× in
> price per watt**. It was buying a median **$1.5B** radioisotope plant, 14% of
> mission cost, on a criterion that cannot see dollars.
>
> Making it a searched axis resolved against `selection_key` drops it from
> **31% to 3.9%** of rows. So 607 of the 693 bodies that "wanted" nuclear did
> not want it at all; they wanted the lighter plant and would have been
> bankrupted by it.
>
> The general lesson, and it is the one this file already states in
> "**a search must optimise what you report**": *an unreachable branch is not a
> verified branch.* "Correctly wired and very nearly unreachable" was a
> statement about how often it fired, and it was being read as a statement
> about whether it was right. The moment something else made it reachable, a
> latent defect became 14% of mission cost. **Check the objective of every
> choice the model makes, not just the ones that currently fire.**

### Verification (2026-08-08)

Same three checks as v1.11.0, on the rebuilt `master.py` at cislunar.

**1. Full-catalog cislunar, both settings:**

| | `1.11.0` | `1.12.0` | Δ | winner | evaluable |
|---|---|---|---|---|---|
| raw | 31.7712× | **33.2342×** | +4.60% | 4660 Nereus, iodine | **15,407** |
| beneficiated | 22.4665× | **23.9169×** | +6.46% | 7753 (B), 5.311× | **15,566** |

**2. Never-worse holds, and holds exactly:**

```
pairs 15,407 | max benef/raw 1.000000 | exceptions 0 | declined (== 1.0) 591
```

This one mattered more than usual. The thrust gate REMOVES options, and a
strictly smaller option set cannot make a correctly-implemented search better
— the mirror of the never-worse argument that v1.11.0's wider search relied
on. Both cells moved the right way and the invariant still holds exactly.

**3. Serial and parallel are byte-identical:**

| | serial | 8 workers | speed-up | sha256 |
|---|---|---|---|---|
| raw, 4,000 rows | 43.2 s | 23.5 s | 1.84× | MATCH |
| beneficiated, 2,000 rows | 197.6 s | 54.0 s | 3.66× | MATCH |

**4. No `replicated`-scaling device survives anywhere**, in either full run —
the direct check that the gate did what it claims. Thruster mass is a median
2.7% of EP system mass among survivors (max 16%), which is the tankage
signature again: the term disqualifies rather than taxes.

> 🚨  **RETIRED 2026-08-09 — that was a property of a 15,000-row population,
> not of the gate.** On the full 1.55 M catalog at cislunar, **13 raw and 327
> beneficiated rows** survive on FEEP, carrying 4.4–16.7 t of thruster for
> ~5 N. They close because their payloads are 70–128 t, and **none is
> competitive** — best 34.6× against the catalog best of 26.7863×. The gate is
> a mass penalty rather than a threshold, exactly as designed, so survival was
> never the thing to test. **Test whether one WINS.** Do not restore "zero
> survive anywhere" from this or any earlier revision.
>
> ✅  As of 2026-08-11 that test is run at every destination and a `replicated`
> device wins **none of eight cells** — but at `mars_surface` the best one is
> the catalog's **fifth**-ranked body and at `earth_surface` its **seventh**, so
> do not restore "none is remotely competitive" as a general claim either. It is
> true at cislunar and nowhere else.

Full-catalog wall clock at cislunar: **86 s raw / 463 s beneficiated**, against
89 s / 462 s on `1.11.0` — unchanged, because the extra knapsack calls are
offset by half the catalog now failing early. The beneficiated figure is up ~18% because
`_cargo_water_kg` calls the payload knapsack inside the fixed-point loop rather
than once after it. That was measured before it was accepted: on the 250-body
beneficiated sample the whole run went 19.8 s → 21.4 s, +8%.

## What catalog v1.1.0 / calc v1.13.0 changed

**Nothing in the model. Everything in the population.** Not one term,
coefficient, table value or search axis moved; a run over the same rows
produces the same numbers. The catalog went from **89,367 asteroids to
1,554,400**, and that is enough on its own to invalidate every figure in this
file.

Read this section as the counterweight to the rest of the document. Every
other release here made the answer *worse* by removing something the model was
getting for free. This one makes it **better**, and for a reason that is not a
concession: the model was always searching for the best rock in a bag that
held 5.7% of the rocks.

catalog goes `1.0.9 → 1.1.0`, calc `1.12.0 → 1.13.0`, master `1.15.0 → 1.16.0`.

### The bag was small for three unrelated reasons

**1. NEOWISE was contributing literally nothing, silently, and only at scale.**

IRSA returns `asteroid_number` as `float64` whenever the result slice contains
any unnumbered body. `.astype("string")` then builds `"3.0"`, and
`_extract_canonical_designation` matches neither `^(\d+)\s*$` nor
`^(\d+)\s+[A-Z][a-z]` against `"3.0"`, so it passes the value through
unchanged. The merge key could never equal JPL's `"3"`. Every NEOWISE row
arrived at validation as a body nothing else had heard of and was dropped for
having no semi-major axis.

Three things about the shape of this bug are worth internalising, because they
are the reason it survived four releases:

- **It works at small caps.** A slice with no unnumbered bodies is `int64` and
  renders `"3"`. So every quick test passed and the production run failed.
- **The fetcher still printed its success line**, `✅ 183,408 records fetched
  from NEOWISE V2.0`, on the run where it contributed zero.
- **The only trace in the output was an absence** — all seven `neowise_*`
  columns present in `asteroid_catalog.csv` and 100% empty. A column full of
  NaN does not look like a bug, it looks like missing data.

This is the `.astype(bool)` / `regex=False` trap again in a new costume, and
CLAUDE.md already states the general rule: **the wrong behaviour is the quiet
one.** The specific new instance: *a float-typed identifier stringifies to a
key that is not null and not right.*

Fixed in three places, deliberately redundant:
`fetch_neowise` formats through `Int64`; `_extract_canonical_designation`
strips a trailing `.0` from any source; and `merge_sources` now **fails loud**
when a source arrives with rows and either survives keying with none or matches
zero backbone designations. That third one is the general defence — it would
have caught this on the first run.

⚠️  The population gain from this fix alone is **small**: JPL SBDB already
ingests NEOWISE diameters, so it recovers only ~27 bodies JPL lacked. What it
recovers is *data*, not rows — IR albedo, beaming parameter and diameter
uncertainties for **132,691** bodies that had none.

**2. One row cap was shared by four sources, which made the catalog smaller
than any single source.**

`jpl_limit` capped every fetcher. Each takes its lowest-numbered N bodies, so
four sources capped at the same N return substantially the *same* N bodies;
the merge collapses them and the union is ~N rather than 4N. Raising the cap
to reach further into one source dragged every other source along with it.
This is what the request that prompted this release described as "a lot of
them are duplicates which are removed" — the duplicates were real and the
dedup was correct; the mistake was upstream, in asking four sources the same
question.

Now one cap per source (`jpl_limit`, `ssodnet_limit`, `neowise_limit`,
`mp3c_limit`) and **0 means unlimited**, which is the default. Measured
2026-08-08: JPL serves all 1,554,321 asteroids for 401 MB in 24 s.

**3. Only 9% of asteroids have a measured diameter, and validation drops the
rest.**

This is the real ceiling and it always was. Of JPL's 1,554,321 asteroids,
**139,582 have a measured diameter** — and `validate_and_filter` drops any body
without one. The union across every source is **149,590**.

**1,553,817 have an absolute magnitude H**, and diameter follows from H and
albedo with no free parameters:

```
D_km = (1329 / sqrt(p_V)) * 10**(-H/5)         Fowler & Chillemi 1992
```

so the only estimated quantity is `p_V`. `derive_missing_diameters()` fills
it, gated behind `derive_diameter_from_h` (default on), and a measured
diameter is never overwritten.

### The albedo tables are derived, and they are the soft part

Both are medians over the **138,437** bodies that have a measured albedo,
computed 2026-08-08 rather than taken from literature, with per-row sample
sizes in the source. `ALBEDO_BY_SPECTRAL_TYPE` covers 28 classes (n ≥ 5;
S 0.2439 at n=534, C 0.0540 at n=195, V 0.3880 at n=36).
`ALBEDO_BY_SEMI_MAJOR_AXIS_AU` is the belt's albedo gradient — 0.2885 at
1.3-2.0 AU falling to 0.0660 in the outer belt.

Four things not to "fix" here:

**The orbit table is what actually sizes the catalog, not the taxonomy table.**
A body with a taxonomy almost always has a diameter too, so the taxonomy branch
fires on 105,905 rows against the orbital gradient's **1,298,885**.

**The sample is biased, and the bias runs optimistic.** Those albedos are
overwhelmingly NEOWISE, a thermal-infrared survey. At fixed H a darker body is
larger, and a larger warmer body is easier to detect thermally, so the measured
sample over-represents dark bodies relative to the 1.4 M never measured. A
median that is too low gives a diameter that is too large. Quantifying it needs
a debiased size-frequency model, which this pipeline does not have. **Do not
correct it by raising the table** — that is the move CLAUDE.md rejects for
`IN_SPACE_UTILITY`, and for the same reason.

**Mass is the exposed quantity, not diameter.** D scales as `p_V^-0.5` and mass
as `p_V^-1.5`. A factor-2 albedo error is a factor-2.8 mass error, and mass is
what the ranking runs on. `diameter_source` and
`derived_diameter_is_estimate` exist so this is filterable; filter on them
before treating a derived row as comparable to a measured one.

**The derived albedo also sets the composition, deliberately.** Assuming
p_V = 0.066 for an outer-belt body *is* assuming it is carbonaceous, so
`enrich_composition` reads the assumed albedo as its last spectral-type
fallback (`spectral_type_source = "albedo_assumed"`). Without that, all 1.4 M
derived bodies land on `TAXONOMY_COMPOSITION["Unknown"]`, whose fractions are
`None`, so they get no density, no mass, and Stage 4 skips them — 1.4 M rows
with a diameter and nothing to do with it. Note the direction: **one
assumption produces two outputs.** Inferring the class first and reading an
albedo back off it would launder one guess into two apparently independent
columns, and that *would* be circular.

⚠️  **Beyond 5.2 AU the derived diameters are the weakest in the catalog.** The
outer bin's 0.069 comes from 1,228 measured bodies dominated by dark Centaurs
and Trojans, and it is applied to genuinely icy TNOs that run brighter. 5,656
derived bodies come out above 100 km and the largest is 1,219 km, which is
bigger than Ceres — those are real TNOs (2014 UZ224, 2012 VP113, 2018 VG18)
whose sizes are overstated. It affects **1.09%** of the catalog and they fail
Stage 4 on Δv anyway, so it is documented rather than fixed.

### Stage 4: the cap defaulted to throwing away 99.7% of the run

`eval_row_cap` defaulted to **5,000**. Against a 1.55 M-row catalog that is
0.3%, discarded behind one line of stdout. Every published figure in this file
was measured with the cap explicitly set to 0 through the UI, so defaulting it
to 0 makes the code agree with documented practice rather than changing what a
documented run does.

**And a capped run was never a sample.** The catalog reaches Stage 4 sorted by
semi-major axis, so `.head(n)` returned the *innermost* n bodies — at 5,000
rows of this catalog, everything inside roughly 2.1 AU: no outer belt, no
Hildas, no Trojans, and an S-complex-skewed spectral mix. Every "quick check
before the full run" was made on a population that does not resemble the full
run. `eval_row_sampling = "stride"` takes evenly-spaced rows across the whole
catalog; `"head"` restores the old behaviour exactly. Stride is `np.linspace`
over positions — no RNG, no seed to record — so v1.10.1's determinism holds.

⚠️  This changes the numbers any **capped** run produces. It does not change an
uncapped one, which is every figure on record.

### Measured effect

Catalog, full, measured 2026-08-08 (224 s end to end, ~6 GB peak, 0.88 GB CSV,
warm SsODNet cache):

| | v1.0.9 @ `jpl_limit=200_000` | **v1.1.0 unlimited** |
|---|---|---|
| catalog rows | 89,367 | **1,554,400** |
| measured diameters | 89,367 | 149,590 |
| H-derived diameters | — | 1,404,810 |
| NEOWISE rows merged | **0** | **132,691** |
| taxonomy from a source | 52,881 | 171,007 |
| NEAs (a < 1.3 AU) | ~1,000 | **10,897** |
| rows with positive mass | 89,333 | 1,554,351 |
| numbered bodies | 89,367 (max 199,994) | 895,910 |
| **unnumbered bodies** | **0** | **658,490** |

That last row is the one to notice, and it is a *third* silent failure
alongside NEOWISE and the shared cap. JPL returns rows in SPK-ID order and
numbered bodies come first, so at any cap below the full table a provisional
designation could never appear — the cap was not truncating the tail of the
population, it was **excluding an entire class of it**. Recently-discovered
NEAs are overwhelmingly unnumbered, and NEAs are the bodies this model finds
best. Nobody had to make a mistake for this to happen; `limit=N` on an ordered
API is simply not a sample.

Stage 4 at cislunar, **full catalog, raw**, measured 2026-08-08 — 2,539 s,
668,004 evaluable of 1,554,351 (43.0%), 1.06 GB output:

| | `1.12.0` | **`1.13.0`** | Δ | evaluable |
|---|---|---|---|---|
| raw | 33.2342× | **25.7035×** | **−22.66%** | 15,407 → **668,004** |
| beneficiated | 23.9169× | *not measured* | — | — |

**The best case is 2021 CX5**, a D-type NEA at a = 1.63 AU, 82 m across, on
xenon and a New Glenn. The top ten are all C/D/B/X-types between 1.34 and
1.87 AU, eight of them under 500 m, and **26 bodies beat the old best case**.

⚠️  **The gain is the cap, not the derivation, and the split matters.** The
best body on a **measured** diameter is 2016 GS2 at **27.0173×** — still
−18.7% against `1.12.0`. So H-derivation is worth only ~1.3× of ratio at the
very top; almost all of the improvement comes from **fetching bodies the row
cap was hiding**. 2016 GS2 is unnumbered and 678927 (third place, also
measured) has an IAU number past the 200,000 the previous run fetched. Neither
was ever excluded for lacking a diameter.

That is the right way to read this release: **derivation deepens the
population, the cap removal is what found better rocks.** Quote 25.7035× as
the model's answer and 27.0173× as the measurement-only answer, and never
present the first without the second.

**Chemical propulsion is emphatically not extinct, and xenon has taken over.**
Full raw shares: xenon 41.7%, iodine 24.4%, **hydrolox 16.0%**, water ion
9.2%, krypton 8.2%, methalox 0.2%, argon 0.2%. Against `1.12.0` raw that is a
different table entirely — iodine has more than halved and hydrolox has
roughly tripled. No `replicated`-scaling device appears anywhere, which is the
v1.12.0 thrust gate still doing its job on a 43×-larger population. Vehicles:
Falcon Heavy 66.6%, SLS Block 1B 31.9%, New Glenn 1.3%.

> ⚠️  **Two updates from 2026-08-09, on the same catalog at v1.14.0.** The
> shares move again — xenon 42.6% / iodine 25.2% / water ion 15.6% / hydrolox
> **8.1%** / krypton 8.0% — so hydrolox roughly *halves* back and water ion
> takes its place. Both are the eclipse and containment terms landing on
> volatile-rich bodies. **And "no `replicated`-scaling device appears
> anywhere" is now false**: 13 raw / 327 beneficiated rows survive on FEEP, all
> of them uncompetitive. See the v1.14.0 verification block for why that is the
> gate working rather than failing.

⚠️  **Still not measured, and each needs its own run:** the four non-cislunar
destinations **beneficiated**, and the programme-scale curve. ✅  Everything
else in this list was measured on 2026-08-09 — cislunar beneficiated, all four
other destinations raw, and every winner identity in the current matrix.

⚠️  **Do not budget from a sample — this release proved that wrong.** Scaling
the 20,000-row stride sample predicted 2.2 h for the full raw run; it took
**42 minutes**, a 3.1× overestimate, because fixed costs (worker startup, the
0.88 GB catalog load) dominate a small run and parallel efficiency is far
better on a large one. The measured raw figure is **2,539 s**; beneficiated is
*estimated* at ~2.2 h from the sample's 3.12× raw:beneficiated ratio, and that
estimate carries the same warning.

> 🚨  **The beneficiated estimate above was wrong by 4.8×, in the OPPOSITE
> direction, and that is the lesson rather than either number.** Measured
> 2026-08-09 on v1.14.0: full cislunar beneficiated is **10.6 h**, not ~2.2 h.
> The true full-catalog ratio is **7.1× raw**, against the 3.12× assumed here
> and the **1.63×** that v1.14.0's own 6,000-row sample showed.
>
> So on this pipeline a sample has now mispredicted full-catalog runtime by
> 3.1× *high* and 4.8× *low*, for opposite reasons: fixed costs dominate a
> small run, while a stride sample under-represents the expensive tail of the
> concentration sweep. **The rule is not "samples overestimate" — it is that a
> sample predicts full-catalog runtime here to no better than a factor of ~5.**
> Budget from a measured full run of the same cell, or do not budget.

### Verification (2026-08-08)

**1. Literature spot-check on the full 1,554,400-row catalog** — the same five
bodies CLAUDE.md names for the v1.0.9 SsODNet fix, all exact:
Ceres 939.400 km / 2.162 / 9.074 h / C, Vesta 522.770 / 3.411 / 5.342 h / V,
Pallas 513.000 / 2.911 / 7.813 h / B, Psyche 222.000 / 4.143 / 4.196 h / X,
Eros 5.270 h / S. All five report `diameter_source = measured`, which is the
check that derivation is not overwriting measurements.

**2. Never-worse holds, and holds exactly** (20,000-row stride sample):

```
pairs 8,612 | max benef/raw 1.000000 | exceptions 0 | declined (== 1.0) 429
```

**3. Serial and parallel are byte-identical**, which is the check that the new
stride selection did not introduce order-dependence:

| | serial | 8 workers | speed-up | sha256 |
|---|---|---|---|---|
| raw, 4,000 rows | 67.0 s | 48.1 s | 1.39× | MATCH |
| beneficiated, 1,500 rows | 139.0 s | 62.0 s | 2.24× | MATCH |

The speed-ups are below v1.12.0's 1.84× / 3.66× because these caps are smaller
and per-worker startup is fixed; the sha256 is the part that matters here.

## What calc v1.14.0 / transportation v1.11.0 changed

A realism audit of the whole model — every metric and every calculation, not
one subsystem. Five findings, and the first three share a shape this project
has not seen before and should not see again:

> **The data was already there, correctly derived and correctly cited, and
> writing the gap down had been mistaken for closing it.**

Every figure below has sat in Module 3's `STORAGE_REFERENCE` since its v1.9.0,
under a note reading "⚠️  Not modelled in Module 4". Module 4 loads
`operational_costs.csv` and does **not** load `storage_systems.csv`. So the
table was documentation, the gap was quoted in *this file* as a known
limitation for two releases, and nothing ever moved. That is the
prescriptive-comment failure with a twist: not a comment nobody applied, but a
**whole reference table nobody could read**.

All five findings move the answer the same way: worse.

transportation goes `1.10.0 → 1.11.0` (four new ops rows, no propellant,
vehicle or Δv figure moved), calc `1.13.0 → 1.14.0`, master `1.16.0 → 1.17.0`.

### The pipeline sold water and never kept it

The largest of the three, and the one that is not a rounding term. The model
prices water at every in-space destination, charges the energy to bake it out
of phyllosilicate (v1.7.0) and the array that does the baking (v1.12.0) — and
charges **nothing at all** to stop it subliming across a four-year cruise.

Exposed ice in vacuum at 1 AU sits far above its sublimation threshold and is
simply gone. Shaded, sealed and blanketed it is stable for decades. The charge
is a sealed shaded hold: no power, no cryocooler, but real mass.

Check the size of what was flying free before deciding this is minor — the best
cislunar missions are **~88% water by mass**:

```
water 38,415 kg; carbon 3,548 kg; nickel-iron 1,537 kg     (of a 43,500 kg hold)
```

**The commodity carrying the entire result was the one commodity with no
containment.** Module 3's row is 0.05 kg/kg and it is **incremental** to the
0.15 ore restraint Module 4 already flies as
`return_structure_frac_of_payload` — the hopper holds the cargo, the seal and
the shade keep the volatile fraction of it from leaving. That reading is what
makes the storage row's own "heavier than an ore hopper" true at a value below
0.15. Charged on **water only**; carbon and organics are refractory at these
temperatures and ride in the hopper like rock.

It folds into `structure_frac`, which means the closed-form solver carries it
with **no change to its algebra** — it is already the `f` in `(1 + f)`. It is
settled at the payload actually flown rather than the loop's estimate, and it
joins the fixed point rather than being estimated outside it, because
estimating a feedback term outside the loop is exactly the v1.12.0
cargo-water-array bug.

### The sun never set on the processing plant

`processing_power_w()` returns a **continuous average draw** — energy over the
time available — and the plant was sized straight off it. That is only right if
the rig is never in shadow. It stands on a rotating body.

Two terms, and it matters that they are separate:

- **Array oversize.** To deliver P continuously through a dark fraction f, the
  sunlit hours must run the load *and* recharge the store:
  `[(1−f) + f/η_rt]/(1−f)` = **2.11×** at f = 0.50, η_rt = 0.90. This is a
  **sizing factor, not a specific mass**, which is why no W/kg row could ever
  have absorbed it however its notes were worded.
- **Storage**, sized on the **body's own rotation period**. This finally makes
  `rotation_period_h` — carried by Module 1 since v1.0.0 and read by nothing —
  a quantity the model uses, and it means a slow rotator is genuinely a worse
  place to mine.

Both collapse **exactly** into one effective W/kg, because both are
proportional to the draw:

```
m_plant = P·oversize/w_solar + P·Δh/e_storage = P·(oversize/w_solar + Δh/e_storage)
```

so `eclipse_effective_w_per_kg` returns a specific power the rest of the module
uses precisely where it used the bare figure — which keeps the plant's sizing,
its 1/r² behaviour and its comparison against a radioisotope source in one
currency.

Four things not to "fix" here:

**The storage term is charged as an INCREMENT, and the deduction is not a
nicety.** "Power system specific mass" is 60 W/kg system-level against ROSA's
~150 W/kg at the wing, and part of that 2.5× is a battery. Module 3's new
"Power-system row baseline dark period" names how much (0.58 h — a LEO eclipse)
and only the excess is new mass. Without it the battery is charged twice, and
at 0.0056 kg/W against the row's own 0.0167 kg/W that is **a third of the
plant**.

**That row was internally contradictory, and the argon audit did not catch
it** because it was looking at propellants. "Power system specific mass"
claimed to cover "power through eclipse **and** through the night side of a
rotating body" — and no single specific mass can be right for both, since an
asteroid with a 10 h rotation is dark for 5 h, roughly 9× the LEO figure. Same
failure as argon: **a reference row asserting two incompatible physical states
at once.** The claim is removed from its notes and replaced by a row that says
which of the two the 60 W/kg figure actually is.

**The penalty is much bigger than the storage row's own estimate.** That row
says eclipse "roughly DOUBLES the power system"; derived, it is **4.7×** at 1
AU and the median 10.2 h rotation, because the battery for a 5-hour night is
heavier than the array oversize (0.044 kg/W against 0.035). The 2× is the array
term alone. Do not restore "roughly doubles".

**The exemptions are physical, not conservative.** A radioisotope plant has
flat output and never sees a night. The **EP array** is in interplanetary
cruise in permanent sunlight and keeps the bare 1/r² figure — it is the rig's
plant that stands in the shadow, not the propulsion train.

⚠️  **The soft part, and it runs the other way.** Module 3's row also names the
alternative architecture: a rig can **mine at half duty cycle** instead of
carrying storage, taking twice the stay rather than twice the plant. This model
sizes the storage and does not price the duty-cycle option, so where digging
slowly is cheaper the answer here is pessimistic. And a free-flying array
station-keeping off a small body would see almost no eclipse at all — an
architecture this pipeline cannot express. `dark_fraction` is a cited 0.50 with
a 0.35–0.55 range; it is the softest number in this release.

⚠️  Also soft: 104 Wh/kg is 130 Wh/kg system-level Li-ion at 80% depth of
discharge, and 80% DoD over the ~2,000 charge cycles a 10 h rotation implies
across a 2.3-year dig is aggressive for cycle life. A regenerative fuel cell
(400 Wh/kg, TRL 5) would cut the term ~4× and is not taken, because nothing has
flown one. Those two roughly offset.

### The power source was chosen on mass, and it costs 625× more per watt

This one was **latent, and this release is what made it dangerous** — which is
the most useful thing in the audit.

CLAUDE.md carried a section headed "The RTG option is correctly wired and very
nearly unreachable", recording that the branch fired on **one row of 15,566**.
It ended: "the code is right, and it will matter the moment the Δv model or the
vehicle set changes."

The code was not right. `power_source_for_target` picked whichever of
photovoltaic and radioisotope was **lighter**, and an RTG costs **$500,000 per
watt against $800** — 625×. Nothing asked whether the lighter plant paid. That
was invisible while the branch fired on one row.

Adding the eclipse term makes photovoltaics roughly half as good per kilogram,
which moves the crossover from **3.46 AU to about 2.1 AU** and puts **31% of
rows** on the nuclear side. At which point the model was buying a median
**$1.5 billion** radioisotope plant — **14% of mission cost**, max 23% — on a
criterion that cannot see dollars.

So it becomes a searched architecture axis, exactly as this file requires of
any new one, resolved by `selection_key` like everything else. RTG share falls
**31% → 3.9%**: 607 of the 693 bodies that "wanted" nuclear did not want it at
all. The Pu-238 ceiling is now enforced as **infeasibility** rather than as a
preference, which is what it physically is — DOE production is ~1.5 kg/yr,
about one flagship RTG a year for the world.

⚠️  **Both of those percentages are 6,000-row SAMPLE figures on the OLD
catalog.** On the full 1.55 M catalog (2026-08-09) the searched axis lands on a
radioisotope plant for **3.96% (`lunar_surface`) to 8.46% (`earth_surface`)** of
raw rows, and **10.83%** of beneficiated `cislunar` rows — 1.01× to 2.17× the
sample's 3.9% on raw, and 2.78× beneficiated. The *conclusion* is untouched and
if anything stronger: the branch is reached more often than anyone had
measured, so searching it against price rather than mass matters more, not
less. Quote the range above, not 3.9%.

`power_source_for_target` keeps its name and its docstring and changes job: it
generates the candidate rather than making the decision, and it is what prunes
inner-system bodies from paying for a second search pass.

**The lesson, and it generalises past this branch: an unreachable branch is not
a verified branch.** "Correctly wired and very nearly unreachable" was a
statement about how often it fired and it was being read as a statement about
whether it was right. Check the objective of every choice the model makes, not
only the ones that currently fire.

### Market saturation could not see the programme it was written for

`model_market_saturation`'s own config comment:

> "Prices were static at the point of sale, so a mission could return any
> quantity of platinum at spot and the 'fly more missions' lever had no
> stopping point."

It never achieved that. `nre_amortization_missions` appears in exactly four
places in `calc.py` — rig amortisation, NRE division, the learning curve and
reliability growth — and **none of them was the saturation block**. So a
100-mission programme divided its NRE by 100, grew its reliability under
Duane/AMSAA, and sold 100 payloads into the market at the price **one** payload
commands. Every lever pointed the same way and nothing pushed back.

The rate that matters is how much is on the market **at once**, and the model
already computes it: one rig serves `missions_sharing_rig` missions back to
back, so a programme of N needs `ceil(N / that)` rigs and that many missions
are in flight concurrently. Derived from the model's own rig service-life
arithmetic rather than asserted, and **exactly 1 at N = 1** — so no
single-mission figure moves, which is every headline figure on record.

The curve stops being monotone and turns (6,000-row raw cislunar sample):

| N | `1.13.0` | **`1.14.0`** | concurrent | saturation multiplier |
|---|---|---|---|---|
| 1 | 38.4050× | 38.7886× | 1 | 0.7451 |
| 10 | 16.0296× | **16.4745×** | 1 | 0.7773 |
| 100 | **10.8935×** | **20.3246×** | 10 | **0.4279** |

**The optimum programme size is now interior, near N = 10.** That is a result
the model could not previously express, and it is the headline of this release
rather than the ratios.

### Two ledger asymmetries, in the family this file already names

**TPS had no learning curve.** The capsule, the power system, the electric
stage and the tankage all carry `lc`; an ablative heat shield is the most
literally per-mission article on the vehicle — consumed on entry, rebuilt every
flight — and it was the one recurring article that did not, for no reason
anybody wrote down.

**TPS was missing from the insured book value.** v1.12.0 swept that list
against the mass cascade and picked up the plant, the electric stage and the
tankage. TPS is billed from a different variable and was missed — it is the one
item on the launch stack whose cost line sits outside `hardware_cost`. On an
Earth-return mission it is 15% of payload at $50,000/kg.

Both are inert at cislunar (no atmosphere, so `tps_frac = 0`) and at N = 1,
which is why neither moves the measured cells below and why both need
re-measuring at `earth_surface`, `leo` and `mars_surface`.

### And one hole in the safety net, half closed

`schema_check()` tested Module 3 **columns**. The ops table is keyed by
category, so every figure in it is a **row**, and a missing row was invisible —
`_ops_value` defaults it, silently and flatteringly. Four of this release's
five findings arrive as ops rows, so shipping them behind a check that cannot
see them would have been the same mistake again.

`_MODULE3_REQUIRED_OPS` names each row Stage 4 needs and the model term its
absence reverts. The wrong-**value** half of the hole CLAUDE.md describes is
still open.

### Measured effect

⚠️  **Everything here is a 6,000-row stride SAMPLE of the OLD 89,367-row
on-disk catalog**, not the 1.55 M-row catalog the `1.13.0` headline was
measured on. Both versions were run against the same rows in the same process,
so the delta is the model change and nothing else — but **do not quote these as
full-catalog figures**. A full raw cislunar pass is ~42 minutes and has not
been re-run.

| | `1.13.0` | **`1.14.0`** | Δ | evaluable |
|---|---|---|---|---|
| raw | 38.4050× | **38.7886×** | **+1.00%** | 2,256 → 2,215 |
| beneficiated | 25.7930× | **31.6556×** | **+22.73%** | 2,278 → 2,232 |

**Beneficiated moves 23× as far as raw, and that is the tank-mass signature
from v1.11.0 in a new place.** Concentrating means more feed, more power, a
bigger plant — and the eclipse term multiplies the plant. The winner's plant
goes **308 → 915 kg** (×3.0), its propellant switches from iodine to xenon, and
it concentrates **less**: 5.062× → 4.030×, because grade now costs more array.
Raw is where the containment term shows through comparatively cleanly.

The winner is 136564 (C) in all four cells.

### Verification (2026-08-08)

**1. The gated-off build reproduces HEAD EXACTLY.** With
`model_eclipse_power = False` and `model_volatile_containment = False`, against
`master.py` at HEAD, 3,000-row raw cislunar, 1,128 rows each:

```
121 shared columns compared | 120 identical | 1 differs: pipeline_version
```

That is the check that matters most for a release of this kind, and it is
stronger than a sha256 diff would have been — the CSV gains nine columns, so
byte-identity was never available. Every gate reproduces the release it belongs
to, so a stale Module 3 catalog degrades to `1.13.0` rather than to something
that never shipped.

**2. Never-worse holds on the NEW axis.** Adding the power-source search cannot
make any row's reported objective worse, because solar is always in the
candidate set:

```
pairs 1,081 | max searched/solar-only 1.000000 | exceptions 0 | improved 23 | bodies added 24
```

**3. Never-worse holds, beneficiated ≤ raw:**

```
pairs 1,105 | max benef/raw 1.000000 | exceptions 0 | declined (== 1.0) 171
```

**4. The mass-ledger identity holds exactly**, on every row of both settings:

```
hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg
max |error| 0.000000000 kg
```

**5. Serial and parallel are byte-identical** (2,500-row raw):

| | serial | 8 workers | speed-up | sha256 |
|---|---|---|---|---|
| raw, 2,500 rows | 47.3 s | 25.5 s | 1.85× | MATCH |

**6. The ops-row staleness check fires.** Removing three rows from
`operational_costs.csv` names all three and the term each one reverts; the
current table is clean.

**Runtime roughly doubles**: 51 s → 107 s raw and 93 s → 174 s beneficiated on
the 6,000-row sample. That is the power-source axis, and it is paid only on
bodies where a radioisotope plant could be lighter — inner-system targets are
pruned before the second pass. Budget a full raw cislunar pass at ~1.5 h rather
than 42 min.

### Still not measured

✅  **Mostly closed on 2026-08-09** — see "The v1.14.0 full-catalog matrix
(CURRENT)" near the top of this file. Six of the ten cells are now measured on
the full 1,554,400-row catalog: the complete **raw** row at all five
destinations, plus **`cislunar` beneficiated**. `cislunar` **is** still the best
case, at 20.5895×.

What genuinely remains:

- **The four non-cislunar BENEFICIATED cells.** `lunar_surface` is ~10 h and
  the other three ~20 h each on this hardware; they were not run. `leo` and
  `mars_surface` are where the two TPS fixes could first show a non-zero
  effect, since both are inert at `cislunar` (no atmosphere → `tps_frac = 0`)
  and at N = 1.
- **The programme-scale curve on the full catalog.** The sample shows it turns;
  where it turns is not established. This is the cheapest thing left — two raw
  cislunar runs at N = 10 and N = 100, ~3 h.

  ⚠️  **Superseded as a method by calc `1.15.0`, though not as a measurement.**
  Re-running at N = 10 and N = 100 samples a grid whose points mostly cannot be
  optimal — the optimum N is *usually* a whole multiple of the rig's trip life,
  so N = 10 and N = 100 are the right answer only by coincidence.
  `optimise_programme_scale` locates it per body inside ONE run, at 1.51×
  runtime (measured, full catalog on `1.15.0`) rather than 2×. What genuinely
  remains here is a **full-catalog run with the search on**, which is one raw
  cislunar pass and has not been done — and it should now be done on `1.16.0`,
  whose search is two-dimensional and has only been timed on a 400-row sample.
  ⚠️  "Always a whole multiple" was `1.15.0`'s wording and calc `1.16.0` demoted
  it to "usually" — programme calendar time pushes back inside a band. The N =
  10 / N = 100 curve is also a `1.14.0` measurement and **does** move under
  `1.16.0`, unlike every N = 1 cell in this file.
- **The historical progression 2.2× → 14× → 39× → 34× → 25×.** Still not
  fixable by re-running: it is a per-release series, so rebuilding it means
  running old code.

## What calc v1.14.1 changed

**Nothing you can measure.** It is a performance release, same contract as
`1.10.1`: every number it produces is identical to `1.14.0`, and the stamp moves
only so that a CSV still names the code that produced it. **Do not re-measure
any table in this file on account of it.**

The finding is one sentence: **the search was spending ~90% of itself proving
missions infeasible, the hard way.** Profiled at cislunar on the real catalog:

| | calls to `_evaluate_combo_at_ratio` | reached the cost model | |
|---|---|---|---|
| raw, 200 rows | 134,538 | 8,292 | **6.2%** |
| beneficiated, 60 rows | 266,584 | 19,445 | **7.3%** |

The other ~93% paid the function's full ~20 µs prologue — eclipse geometry,
synodic period, ISRU chemistry, tankage, electric-stage sizing — to reach
`max_return_payload_kg`, which then refused them on about a dozen flops.

### Pass 1 of the fixed point is its most optimistic pass, and it is closed form

That is the whole argument, and it is what makes this exact rather than a
heuristic. The sizing loop enters its first iteration at

```
hardware_kg    = config.mining_hardware_kg      # plant and EP stage are both 0
structure_frac = return_structure_frac_of_payload   # containment not yet added
stay_est_yr    = station_keeping_floor_yr + window_wait_yr   # the minimum
```

and every later pass can only **add** hardware and **lengthen** the hold. More
hardware shrinks the launch bracket; a longer hold raises the boil-off factor,
which raises `R_ret`, which shrinks it again. So `if not cascade["viable"]:
return None` on pass 1 is a decision no later pass can overturn, and
`_combo_can_close` evaluates that condition directly.

**And it is blind to two axes the loop was re-running it for.** Pass 1 cannot
see `power_mode` — the plant it would size does not exist yet — and it cannot
see the concentration ratio, because no feed has been dug. So the identical
refutation was being recomputed once per power source *and* once per point of
the concentration sweep. That is why a dead candidate costs **305 µs
beneficiated against 32 µs raw**: the sweep re-proved it dead nine times over.
The test therefore sits **above** both loops, not inside them.

### And the per-body constants were re-derived per candidate

The second finding, and it is the v1.10.1 lesson again in a place that release
did not look. Six quantities are functions of (asteroid × config) and of
nothing else — the dark period, the eclipse-corrected specific power, the 1/r²
solar figure, the synodic period, the mineable mass, the throughput cap — and
every one of them was being computed inside `_evaluate_combo_at_ratio`, i.e.
**38,643 times apiece for 200 asteroids**, re-answering the same question about
the same rock.

`AsteroidContext` computes them once per body and `evaluate_asteroid` threads it
down. The arithmetic is untouched; the **repetition** was the cost, which is
exactly the argument v1.10.1 made for memoising the ops constants and for
unboxing catalog rows to dicts. Worth ~0.2× on raw on top of the pre-filter.

⚠️  `synodic_period_yr` is carried on the context **separately from the wait it
usually implies**, because `window_wait_yr` is zero when `model_launch_windows`
is off while the synodic period is still reported. Deriving one from the other
would silently zero an output column on that setting.

### Measured

Working tree against `git HEAD`, same rows, same process structure, serial:

| | HEAD `1.14.0` | tree `1.14.1` | speed-up | output |
|---|---|---|---|---|
| raw, 400 rows | 7.86 s | **4.07 s** | **1.93×** | 124/124 columns identical, sha256 MATCH |
| beneficiated, 150 rows | 28.07 s | **16.73 s** | **1.68×** | 124/124 columns identical, sha256 MATCH |

On a 200-row stride probe of the **full** 1.55 M catalog the pre-filter keeps
**24.1%** of candidates — 59,040 of 77,826 pruned per asteroid-batch. That is a
larger prune rate than the 30% the 150-row sample showed, so the sample
understated it; treat 24.1% as the population figure.

⚠️  **The speed-up is 1.7–1.9×, NOT the ~4× the prune rate suggests**, and the
gap is the point. The 24% that survive are the expensive ones — they run the
full cascade, the cost model and the whole concentration sweep. Pruning three
quarters of the candidates removes well under half the work. Do not quote the
prune rate as if it were a speed-up.

Extrapolated to the measured full-catalog cells (**projection, not a
measurement** — and this file's own rule is that a sample predicts full-catalog
runtime here to no better than a factor of ~5): cislunar raw 5,350 s → ~2,800 s,
cislunar beneficiated 38,072 s → ~6.3 h. **Nobody has run either.**

### Verification (2026-08-10)

**1. Pruned and unpruned builds agree exactly.** `prune_infeasible_combos =
False` restores the `1.14.0` search, and both settings were run over the same
rows in the same process:

```
raw, 400 rows          252 viable both ways | 124/124 columns identical | sha256 MATCH
beneficiated, 150 rows 148 viable both ways | 124/124 columns identical | sha256 MATCH
```

Both were also diffed against `git HEAD` itself, which is the stronger check
and the one that covers the `AsteroidContext` refactor as well as the pruner —
a hoist that dropped a term would not show up in a prune-on/prune-off diff,
because both sides would have dropped it.

**2. Not one mission was lost, and the profiler says so directly.** Calls to
`mission_cost_usd` — the function only a candidate that survives the cascade
ever reaches — are **8,292 before the change and 8,292 after**, while calls to
`_evaluate_combo_at_ratio` fall 134,538 → 38,443. That is a cleaner statement
of soundness than the row counts, because it counts *survivors* rather than
*winners*: a pruner could drop a viable-but-losing candidate without moving any
headline, and this would catch it.

**3. Soundness was checked pairwise before the change was wired in**, on 68,136
(candidate × Δv × ISRU) tuples across both settings: every tuple the pre-filter
killed was also solved in full, and **zero of them produced a result**.

**4. Serial and parallel are byte-identical** — the check this file requires
after any change to the search, and it matters more than usual here because
v1.14.1 attaches derived state to the propellant rows that get pickled to
workers:

| | serial | 8 workers | sha256 |
|---|---|---|---|
| raw, 2,500-row stride | 57.3 s | 53.9 s | MATCH |
| beneficiated, 1,200-row stride | 116.2 s | 66.7 s | MATCH |

⚠️  The raw wall clocks are dominated by the 19.7 s CSV catalog load, which both
paths pay; do not read a parallel speed-up out of that row.

**Both hashes also match the runs made before the `AsteroidContext` hoist** —
`4cdf16ae…` raw over 1,052 output rows and `948d6538…` beneficiated over 502 —
which is a second, wider check on the hoist than the 400/150-row HEAD diffs,
and on a stride sample of the real catalog rather than of a cached subset.

### Two things not to "fix"

**`_combo_can_close` and `max_return_payload_kg` are two statements of the same
algebra**, which is exactly the duplication this file warns about under the mass
ledger ("two copies of this algebra drifting apart is how a mass ends up in one
cascade and not the other"). They are kept adjacent in the source for that
reason. The defence is `prune_infeasible_combos = False` plus a column-by-column
diff: if they ever disagree, the pruned build drops rows the unpruned one keeps
and the diff says so on the first run. **Change one, re-run that diff.**

⚠️  As of v1.14.2 the pre-filter side is written in **three** pieces:
`_combo_close_terms` (everything independent of the vehicle), `_closes_with`
(the one comparison that is not), and `_combo_can_close` — which is now defined
as exactly their composition and exists so there is still one readable statement
of the whole test, and so `_prefilter_probe` does not become a fourth copy. The
search calls the split pair; everything else calls the composed one. That diff
is therefore *more* important than it was, not less, and it was re-run for
v1.14.2 on both settings.

**`AsteroidContext`'s membership test is "does it vary with the candidate",
not a field count.** If a quantity varies only with the body it belongs on the
context; if it varies with the vehicle, propellant, return mode, power source or
concentration ratio it must not, because the context is built once and every
candidate reads the same copy. `synodic_period_yr` is carried on it *separately*
from `window_wait_yr` for a related reason: the wait is zero when
`model_launch_windows` is off, and the synodic period is still an output column.

**The pre-filter is deliberately one-sided and deliberately loose.** True means
"solve it properly", not "this is a mission" — the throughput cap, the duration
limit, the volume cap and the post-settle launch recheck all still apply, and
about a quarter of the survivors die on one of them. Tightening it to catch
those would mean duplicating four more downstream conditions, i.e. four more
copies of the same drift hazard, for a fraction of the remaining time. Cheap
and sound beats tight and clever here.

### Why the GPU is not the answer, measured rather than assumed

This came up as "the CPU is maxed but the GPU is idle". It was tested rather
than reasoned about, on the reference machine's RTX 2080 Ti:

```
numpy  fp64 exp, 40M elements   0.222 s
cupy   fp64 exp, 40M elements   1.695 s     <- 7.6x SLOWER than the CPU
cupy   fp32 exp, 40M elements   0.137 s
host->device, 320 MB            0.055 s
```

**The card is 7.6× slower than the CPU at the arithmetic this model is made
of.** That is the TU102's 1:32 FP64 rate, and it is a property of every
consumer GeForce, not a tuning problem. fp32 is 1.6× faster than the CPU — and
unusable, because every verification this project relies on is a bit-identity
check: sha256 CSV diffs, `max |error| 0.000000000 kg`, "120 of 121 columns
identical". Single precision would break all of them for a 1.6× that the PCIe
round trip mostly eats.

The workload is also the wrong *shape* — branchy scalar Python with early exits,
a fixed-point loop, a knapsack with a `sorted()` in it — so the port is a
rewrite, not an annotation. And the piece that IS GPU-shaped, this pre-filter,
is ~10 flops per candidate: ~14 GFLOP for the entire 1.55 M-row catalog, which
is under a second on **either** processor and irrelevant against a 5,350 s run.

**RAM is not a constraint either.** The run peaks around 6 GB against 64 GB
installed. The only honest RAM/IO win found was the catalog load — `read_csv`
on the 883 MB catalog is **19.7 s** against **2.1 s** for the same frame as
Parquet — which is real, free, and worth ~0.4% of a full destination run. It is
noted here rather than implemented because it changes Module 1's output
contract, and no measured cell in this file would move by a detectable amount.

### What is left on the table

- **Branch-and-bound on the objective**, i.e. pruning candidates that *can*
  close but cannot beat the incumbent. That would attack the remaining 24%,
  which is where the time now is. It needs an **admissible** upper bound on
  `selection_key`, and `selection_key` is lexicographic over profit and
  cost/revenue with revenue coming out of the payload knapsack — so a bound
  that is provably never optimistic is real work. **Do not approximate it.** A
  bound that is occasionally too tight silently drops winners, and it would
  drop them without changing the row count, which is the one failure mode none
  of the checks above would catch.

⚠️  Four of the other items this section listed were taken in **v1.14.2** and
none of them was branch-and-bound. Read that section before assuming the
remaining time is where this one says it is.

## What calc v1.14.2 changed

**Nothing you can measure.** Third performance-only stamp, same contract as
`1.10.1` and `1.14.1`: every number identical, the stamp moves only so a CSV
still names the code that produced it. **Do not re-measure any table in this
file on account of it.**

Measured against `git HEAD`, same rows, one process, serial:

| | HEAD `1.14.1` | tree `1.14.2` | speed-up | output |
|---|---|---|---|---|
| raw, 400 rows | 2.70 s | **1.13 s** | **2.39×** | 124/124 columns identical, sha256 MATCH |
| beneficiated, 150 rows | 9.19 s | **4.51 s** | **2.04×** | 124/124 columns identical, sha256 MATCH |

That is a larger step than `1.14.1`'s own 1.93× / 1.68×, and **none of it came
from the algorithm**. The search does exactly the same work in the same order;
it had been paying to do it through the wrong machinery.

### The model's arithmetic was going through numpy, one scalar at a time

The single largest item ever found in this module, and it had been sitting in
the two most-called functions since they were written.

`max_return_payload_kg` and `_combo_can_close` called `np.isfinite` and `np.exp`
on **Python floats**. Measured on the reference machine:

| | per call |
|---|---|
| `np.isfinite(x)` | **698 ns** |
| `math.isfinite(x)` | **32 ns** |
| `float(np.exp(x))` | **694 ns** |
| `math.exp(x)` | **47 ns** |

15–22×, and it is not a numpy defect: a ufunc call on a scalar builds a 0-d
array, resolves a dtype loop and boxes the result, which is the right price for
an operation designed to be amortised over a million elements and the wrong one
for a single float. `max_return_payload_kg` makes **seven** of them per
invocation and is called 496,000 times per 150 beneficiated asteroids — about
half that function, and roughly a quarter of the whole search.

**`math.exp` was checked bitwise against `np.exp`**, not assumed equal: 400,000
samples spanning this model's (Δv, Isp) range, zero mismatches. The two differ
only in how they *overflow* — numpy returns `inf` and warns, `math` raises — so
the `isfinite` guard becomes a `try/except OverflowError`. That is the form
`_combo_can_close` has always used, so the two statements of this algebra now
agree on their error handling as well as their arithmetic.

⚠️  **This generalises past these two functions.** Anywhere in this codebase
that a numpy name is applied to a scalar, it is costing ~20× for nothing. The
tell is `np.` inside a function called per candidate rather than per catalog.

### Three hoists, one of which is a trap

**The knapsack re-sorted the same phase list ~2,100 times per asteroid.**
`optimal_payload_mix` did `sorted(phases, key=lambda p: -p[2])` on every call —
325,000 sorts plus 1.4 M key-lambda calls per 150 beneficiated rows, all
re-deriving one order for one rock. Memoised per list in `_PHASE_ORDER_CACHE`,
the same single-slot identity-keyed shape as `_OPS_CACHE`.

> 🚨  **Do NOT "fix" this by sorting the phase table at source.** That was tried
> first and it **changes the output**: `saturation_multiplier`,
> `gross_value_usd`, `profit_usd`, `roi` and `delivered_value_usd_per_kg` all
> move. The market-saturation block builds `sold` from `phases` and accumulates
> `adj_value` by iterating that dict, and floating-point addition is not
> associative — so **the phase table's natural order is load-bearing on the last
> ULP** and nothing in the code said so.
>
> Measured: max relative change **2.8e-16** on 3 of 60 rows, and no vehicle,
> propellant, concentration ratio or power source moved. Numerically that is
> nothing. It is still fatal, because **every verification this project relies
> on is a bit-identity check** — the sha256 CSV diffs, `max |error|
> 0.000000000 kg`, "124 of 124 columns identical". A sort at source reads like a
> free cleanup and silently costs you the ability to prove a release changed
> nothing.
>
> The general lesson, which is new to this file: *a change can be numerically
> negligible and still destroy the evidence.* This repo's releases are argued
> from bit-identity, so an operation-reordering "cleanup" is a change to the
> proof, not just to the number.

**Six per-propellant constants and one per-vehicle were re-parsed per surviving
candidate.** `thruster_efficiency`, `thruster_kg_per_n`, `tank_frac`, `isp`,
`boiloff`, `dv_penalty` and the vehicle's fairing volume — each through
`pd.isna`, which is another pandas dispatch on a Python scalar, so this alone
was ~980,000 `pd.isna` calls per 150 rows. Derived once per run in
`candidate_combos` and attached to the row dict, exactly as
`_PREFILTER_CONSTS_KEY` is and for the same reason: the dict is what crosses the
multiprocessing boundary, so a worker receives the derived values instead of
rebuilding them.

This is the v1.14.1 finding one level further in, and it closed a live drift
hazard on the way: **`tank_frac` was being derived twice from the same two
columns**, once in `_prefilter_propellant_consts` and once in
`_evaluate_combo_at_ratio`. One derivation now, two readers.

**The pre-filter is monotone in launch capacity.** `_combo_can_close` reads the
vehicle in exactly one place — the final comparison — and a bigger rocket can
never turn a candidate that closes into one that does not. The combo grid is
vehicle-major, so seventeen vehicles were each re-deriving one propellant's
exponentials, boil-off inflation and tankage closure to differ only on the last
line. Split into `_combo_close_terms` (no vehicle) and `_closes_with` (vehicle),
memoised per (propellant × Δv × ISRU).

⚠️  **The COEFFICIENTS are hoisted, not the launch capacity they imply**, and
that is not a stylistic choice. `bracket > 0` rearranges algebraically to
`leo > (hw + k·s·d0·R_ret)·k_out·R_out` — but not in floating point. The
rearrangement re-associates the arithmetic and moves the boundary in the last
bit, which for a candidate sitting on it changes whether the row survives the
prune. Same lesson as the phase sort, in a place where it would have changed a
row count rather than a decimal.

### Measured and deliberately NOT taken

**Hoisting the ratio-independent prologue out of the concentration sweep.**
`_evaluate_combo_at_ratio` re-runs its whole prologue for each of the ~8 solves
`evaluate_combo` makes per candidate, and none of it depends on `target_ratio`.
That looked like the biggest remaining item and it is not: instrumented, the
prologue is **7.6%** of a beneficiated run, so ~6.7% is recoverable — too little
to justify splitting a 570-line function with ~40 locals crossing the seam.

The reason it shrank is the three hoists above: the `pd.isna` parsing *was* the
prologue's cost. **Measure the remainder after taking the cheap items, not
before** — the ranking changes.

**Inlining `max(0.0, x)`.** `builtins.max` is 4.5 M calls and ~7.9% of a
beneficiated profile, and `x if x > 0.0 else 0.0` is ~6× cheaper per call. Left
alone: it is spread over dozens of sites in the mass cascade, where readability
is doing real work, for a single-digit gain.

### Verification (2026-08-10)

**1. NEW vs HEAD, column by column and by hash**, at both the search level and
through `build_profitability_catalog`:

```
raw, 400 rows           124/124 columns identical | sha256 MATCH
beneficiated, 150 rows  124/124 columns identical | sha256 MATCH
raw, 2,500-row stride   1,052 rows | 129 columns | sha256 MATCH less version stamp
```

That last row is the stronger one: it is the full output CSV, and the **only**
byte that differs between `1.14.1` and `1.14.2` is the `pipeline_version` column.

**2. Pruned and unpruned builds still agree exactly**, which is the check
v1.14.1 requires after touching `_combo_can_close` — and this release touched it:

```
raw, 400 rows           124/124 columns identical | sha256 MATCH
beneficiated, 150 rows  124/124 columns identical | sha256 MATCH
```

**3. The mass-ledger identity holds exactly**, both settings, `max |error|
0.000000000 kg`.

**4. Never-worse holds, and holds exactly:**

```
pairs 162 | max benef/raw 1.000000 | exceptions 0 | declined (== 1.0) 31
```

**5. Serial and parallel are byte-identical** — required after any change to the
search, and doubly so here because `candidate_combos` now attaches a second
derived tuple to the rows that get pickled to workers:

| | serial | 8 workers | sha256 |
|---|---|---|---|
| raw, 2,500-row stride | 43.6 s | 48.5 s | MATCH |
| beneficiated, 1,200-row stride | 70.8 s | 53.6 s | MATCH |

Row counts (1,052 raw / 502 beneficiated) reproduce v1.14.1's exactly, so the
population is the same one those hashes were taken over.

⚠️  The raw wall clocks are dominated by the 19.7 s CSV catalog load, which both
paths pay; do not read a parallel speed-up out of that row. It is now most of
that row — which is the one place the Parquet note below has started to matter.

## What calc v1.15.0 / transportation v1.12.0 changed

Two findings. The first is a correction and runs the usual direction (worse);
the second is a new search axis and can only run the other way. Paired with
Module 3 `1.12.0`, master `1.17.2 → 1.18.0`.

⚠️  **NOTHING MEASURED IN THIS FILE MOVES.** Every committed cell is N = 1, and
both items are inert there: the trip cap only binds when a rig serves more than
one mission, and the programme search is **default OFF**. That was a deliberate
choice and it is the one to understand before flipping it — see below.

### The rig wore out on a calendar, and the calendar was never the bound

`missions_sharing_rig` was `min(N, life_yr // stay_yr)`, and `life_yr` is
**"Mining rig service life" = 15 YEARS**, whose own Module 3 notes describe a
calendar mechanism: corrosion, thermal cycling, radiation dose. Dividing it by
the stay produced a mission count, and that count was treated as the whole life
of the machine.

**Nothing anywhere bounded duty cycles.** At the ~1.25 yr stay the winning
cislunar mission actually flies, one rig was good for **twelve consecutive
mining campaigns** on the strength of a number that only ever promised it would
not have rusted meanwhile. A rig parked between campaigns ages slowly. One
cutting rock does not.

Module 3 `1.12.0` adds **"Mining rig maximum trips" = 5** (range 2-12) and
`rig_trips_per_ship` takes the **min** of the two bounds, so a long-stay mission
stays calendar-limited and a short-stay one is now cycle-limited — which is the
correct way round and was the entire gap. `rig_trip_limit_binds` reports which
bound retired the rig, per row; on a 400-row raw cislunar sample the cycle bound
binds on **97.0%** of rows against a median calendar cap of 15.

⚠️  **The 5 is a JUDGEMENT and the ops row says so at length.** Nothing has ever
mined an asteroid twice, so it is bracketed between two analogues that disagree
in the useful direction: terrestrial mobile mining plant reaches major overhaul
near 15,000-25,000 operating hours (~2 campaigns at this model's stay) and
survives 2-3 rebuilds — *in a workshop that does not exist at an asteroid* —
while every regolith-contact mechanism ever flown was single-campaign by design
or failed inside one (TAGSAM fired once; Philae's harpoons did not fire;
InSight's mole never buried itself; Curiosity's drill lost its feed mechanism).
**5 is already the optimistic reading of both.**

One consequence worth not "fixing": **terminal value is now credited against
whichever bound is binding.** Paying salvage on remaining calendar years while
the rig is mechanically finished would refund a worn-out machine — the same
shape of subsidy this file keeps cataloguing — so `life_used_frac` is the max of
the calendar and cycle fractions. Gated with the cap itself, so
`model_rig_trip_limit = False` is the `1.14.2` expression exactly.

### Programme size was an input to a model that knows what it costs

v1.14.0 made market saturation see `nre_amortization_missions` and thereby made
the programme-scale curve **turn** — the optimum N became interior. Nothing then
searched for it. N stayed a config field, and the curve was mapped by re-running
the whole pipeline at N = 1, 10, 100, which this file's own tables already flag
as "three points, so near N = 10 is the lowest of the points sampled, not a
located optimum."

`optimise_programme_scale` searches it jointly with every other architecture
axis, resolved by `selection_key` like all of them. Two structural facts make
that cost **1.51× runtime rather than 8-12×** — measured on the full catalog,
and see the correction below, because the sample said 1.13×:

**1. N ENTERS NOTHING IN THE MASS CASCADE.** It appears in `mission_cost_usd`,
the saturation block and the reliability block, and in none of the rocket
equation, the fixed-point power solve, the payload knapsack or the concentration
sweep. So the expensive half of the mission is solved **once** per candidate and
the whole ladder is priced off the same cascade. Re-running the pipeline at
another N re-solves all of it to change three numbers.

**2. THE OPTIMUM N IS ALWAYS AN EXACT MULTIPLE OF `trips_per_ship`.** Within one
fleet band — every N with the same `ceil(N / trips)` — the concurrent output and
therefore the saturation multiplier are **constant**, while NRE/N falls,
autonomy NRE/N falls, the learning curve falls, the rig's per-mission share
falls or holds, and `p_mining` rises. Every lever improves and none pushes back,
so the best N in a band is its **top**, N = F × trips. The search is therefore
over the **FLEET**, and N follows.

That also answers the question directly: **the number of ships is the decision
variable and programme size is its consequence.**

Two further consequences worth keeping:

- **N = 1 is never skipped in effect.** It sits in band 1, whose top is
  N = trips, and by the argument above N = trips dominates it. So a searched run
  can never report worse than the N = 1 run every committed figure was measured
  at — the never-worse invariant holds **by construction** here, not by
  measurement. Measured anyway: 1,052 pairs, zero exceptions.
- **N = F × trips is the only N the cost model is exactly right at.**
  `mining_rig_cost` charges every mission the same share of a fully-used rig, so
  a programme of 13 with trips = 12 books its second rig — used once — as though
  it were worn out. At a whole multiple there is no part-worn rig to mis-book.

⚠️  **DEFAULT OFF, and this is the one axis in the module that is not a
correction.** Every measured cell on record is N = 1. Turning this on does not
make those numbers wrong — it changes the **question**, from "the best single
mission to this rock" to "the best programme built around it". Two answers to
two different questions; a default flip would retire every committed figure at
once with no way to reproduce them.

### Measured — FULL CATALOG (2026-08-11)

✅  Both cells run on the **full 1,554,353-row catalog** at cislunar, raw, 12
workers, in ONE process against the same Stage 2 pass, through the built
`master.py`. **650,516 evaluable rows** in both.

| | search off (N = 1) | **search on** | Δ |
|---|---|---|---|
| best cost/revenue | **26.7863×** | **14.1730×** | **−47.1%** |
| winner | 2021 CX5 (D) | 2021 CX5 (D) | same body |
| vehicle / propellant | New Glenn / **xenon** | New Glenn / **iodine** | — |
| N | 1 | **5** | — |
| fleet | 1 | **1** | — |
| payload | 93,312 kg | 68,432 kg | −26.7% |
| saturation multiplier | 0.6873 | 0.7253 | — |
| `p_mining` | 0.850 | 0.8858 | — |
| wall clock | **1,306 s** | **1,978 s** | **1.51×** |

🚨  **RUN 1 REPRODUCES THE COMMITTED v1.14.0 CELL EXACTLY, ACROSS THREE
RELEASES.** Not just the ratio — `26.7863×`, `650,516` evaluable rows, **2021
CX5 (D)** on **xenon** and a **New Glenn**, payload **93,312 kg**, saturation
**0.6873**, `p_mining` **0.850**, RTG share **5.44%**, aerocapture **0.00%**, and
the propellant split **xenon 42.65 / iodine 25.19 / water ion 15.58 / hydrolox
8.11 / krypton 8.01%** against the committed 42.6 / 25.2 / 15.6 / 8.1 / 8.0.

`1.14.1` and `1.14.2` each argued bit-identity from 150–2,500-row samples, and
`1.15.0` argued inertness at N = 1 from 400 rows. **All three now hold on 1.55
million bodies simultaneously.** This is the first time a "performance only"
claim in this project has been checked at full scale.

🚨  **THE RUNTIME CLAIM WAS WRONG, AND IT IS THE SAME LESSON A THIRD TIME.**
This release originally recorded **1.04–1.13×** from a 2,500-row stride sample.
Measured on the full catalog it is **1.51×** — the sample understated the cost of
the search by ~1.4×, in the *same direction* as v1.13.0's beneficiated estimate
and the opposite direction to its raw one.

That is now **three** full-catalog runtime predictions this pipeline has gotten
wrong from stride samples, in both directions, and this file already states the
rule: *a sample predicts full-catalog runtime here to no better than a factor of
~5.* It applies to a **ratio between two settings**, not only to an absolute
wall clock, which is the part this release adds. The reason is population: the
ladder is priced per *surviving* candidate, and the full catalog's survivors are
not the sample's.

**Every other number in this release came out where the sample said** — the
never-worse invariant, the band structure, the fleet distribution's shape. Only
the runtime moved.

**Never-worse holds exactly on the whole population:**

```
pairs 650,516 | max searched/unsearched 1.000000 | worse 0
improved 650,515 | unchanged 1 | median improvement 45.3%
```

The single unchanged row is the expected signature, not a miss: a body whose
stay is long enough that its calendar cap is 1 trip, so N = 1 is the only
programme on its ladder.

**Fleet sizes chosen**, of 650,516 bodies: 1 ship 304,164 (46.8%), 2 ships
122,905, 3 ships 55,464, then a long tail to the ceiling. Median **2**, max
**64**. N follows exactly — **N = F × trips on every single row**, and N is a
whole multiple of `trips_per_ship` on every single row. Median **8** ladder rungs
priced per mission, max 12.

⚠️  **2,393 rows (0.37%) sit AT `max_fleet_ships` = 64**, and the run says so on
stdout. Those are bodies whose payloads have no finite market to saturate, so
the objective is monotone in N and the ladder's top rung is where the loop
stopped — not an optimum. Read them as a diagnostic, not a result.

**The winner keeps its identity and changes its propellant**: 2021 CX5 both
ways, on a New Glenn both ways, but **xenon at N = 1 and iodine at N = 5**, with
payload falling 93,312 → 68,432 kg. That is the argument for searching N jointly
rather than at a pivot — the best architecture is a function of programme size,
so picking the architecture first and sizing the programme afterwards would pick
the wrong one.

**Propellant shares move with the search**, and in a direction consistent with
saturation punishing volume: water ion 15.58% → 18.39% and krypton 8.01% →
9.29%, while hydrolox falls 8.11% → 5.33% and xenon 42.65% → 40.27%. Vehicles
shift toward Falcon Heavy, 66.4% → 71.0%, against SLS Block 1B 31.6% → 25.7%.

**The trip cap binds on 96.1% of rows** (98.1% with the search on) against a
median calendar cap of **15** and a median trip life of **5** — so on the real
population the cycle bound is what retires almost every rig, and the calendar
bound it replaced was doing almost nothing.

**RTG share** 5.44% → 6.66%; **aerocapture 0.00%** both ways, as cislunar must.

**The mass-ledger identity holds** on all 650,516 rows of both cells to
**7.3e-12 kg**, which is 0.000000000 kg at the precision this file quotes it and
is float noise from the *check's* own re-association — it computes
`h − a − b − c` where the model computes `h = a + b + c`. Worth naming rather
than rounding away: it is the same non-associativity that makes the phase-table
order load-bearing.

### Verification (2026-08-11)

**1. The gated build reproduces HEAD EXACTLY**, both settings. With
`model_rig_trip_limit = False` and `optimise_programme_scale = False`, against
`git HEAD` in the same process on the same rows:

```
raw, 400 rows           129/129 shared columns identical | sha256 a59f871595b228d6 MATCH
beneficiated, 150 rows  129/129 shared columns identical | sha256 ef93b7287dbb49fa MATCH
```

The CSV gains six columns, so byte-identity of the whole file was never
available — the hash is over the shared columns, which is the same construction
v1.14.0 used for the same reason.

**2. 🚨  THE BAND ARGUMENT WAS BRUTE-FORCED, NOT ASSERTED**, because it is the
load-bearing claim of the whole release. Every integer N from 1 to N_max was
evaluated exhaustively per body and compared against the ladder:

| | bodies | N swept | optimum not a multiple of trips | ladder worse than brute force |
|---|---|---|---|---|
| raw | 20 | 1-60 | **0** | **0** |
| beneficiated | 12 | 1-40 | 1 | **1** |
| beneficiated | 32 | 1-24 | 4 → **1 real** | **1** |

Raw is exact everywhere, and the ratios match to four decimals on all 20.

⚠️  **Three of that last row's four "exceptions" are the harness, not the
model**, and the shape is worth recording because it is the standing trap in
this file wearing a new hat. All three report a brute-force optimum of exactly
**N = 24** — the top of the swept range — while the ladder went *past* the sweep
and returned a **better** answer (2018 NB76: brute 250.6962× at N = 24 against
the ladder's 247.7041× at N = 35). The check counted "not a multiple of trips"
without asking whether the brute force had simply run out of room, so a
truncated sweep read as a counter-example to the thing it was truncating. **A
capped search is not a sample of an uncapped one** — the same lesson this file
already records for `eval_row_cap` and for `jpl_limit`, found again in a
verification harness rather than in the pipeline.

⚠️  **The one beneficiated exception is real, and it is NOT the band argument.**
On 2014 JT2 the brute force finds N = 4 at **30.2597×** while the ladder reports
N = 3 at **30.5535×** — 0.97% worse. The trace says why: at N = 4 the winner is a
*different concentration ratio* (3.216 rather than 5.518), which is a different
mission with a shorter stay and therefore a **trip life of 4 rather than 3** —
and N = 4 is a band top for *that* candidate. The ladder handles that correctly.
What it never did was **price that ratio at all**, because `evaluate_combo`
sweeps the ratio coarsely and refines around the winner, and the winner now
depends on N.

Raising `concentration_search_steps` from 7 to 25 makes the ladder return
**30.2597× on ratio 3.216 exactly** — which is what identifies the grid, rather
than the fleet argument, as the cause.

It is documented rather than patched. Refining around the best two ratios is a
heuristic stacked on a heuristic for a sub-1% effect that the existing dial
already closes, and `concentration_search_steps` is the dial this project
already points at for this trade. **It bites only where beneficiation is on AND
the optimum stay sits near a `life / stay` step**, which is why raw is clean.

**One genuine miss in 52 bodies brute-forced, at 0.97%.** 2014 JT2 is the same
body in both beneficiated runs; no other body in either sweep, at either N
range, produced one.

**3. `trips_per_ship` is NOT a property of the body** and the table above is how
that was found. It is `min(life / stay, max_trips)` and the stay depends on how
hard the candidate concentrates, so two ratios on one rock are two mission
profiles with two trip lives and two ladders. Observed directly: 2014 JT2 reports
trips of 3, 4 and 5 at different N, and across the raw sample bodies report 2, 4
and 5. Do not cache a trip life per asteroid.

**4. Never-worse holds, and holds exactly**, with the search on:

```
pairs 120 | max benef/raw 1.000000 | exceptions 0 | declined (== 1.0) 21
```

**5. The mass-ledger identity holds exactly**, both settings, with the search on:

```
hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg
max |error| 0.000000000 kg   (120 raw + 123 beneficiated rows)
```

**6. Serial and parallel are byte-identical** with the search on — required
after any change to the search, and the check that would catch a worker seeing a
different ladder from the parent (v1.15.0 attaches nothing new to the pickled
rows, but the two reliability memos are per-process and would show here if the
ladder were order-dependent):

```
raw, 1,200-row stride   serial 65.3 s | 8 workers 75.6 s | 495 rows | sha256 MATCH
```

⚠️  Eight workers are SLOWER than serial on that row, which is v1.10.1's
"more workers is not always faster" note showing up rather than anything new:
495 output rows is a small run, worker startup is ~1.1 s each and the 883 MB
catalog load is paid by both. Do not read a parallel regression out of it — the
sha256 is what this row is for.

**7. At N = 1 the trip cap changes nothing**, which is what protects every
committed figure. On the same 400-row raw sample, `model_rig_trip_limit` on and
off both give **60.9284×** — while the median trip life moves 15 → 5 and the
cycle bound binds on 97.0% of rows. The cap changes the answer only for
programmes, which is the point of it.

**8. The ops-row staleness check fires.** "Mining rig maximum trips" is named in
`_MODULE3_REQUIRED_OPS` with the behaviour its absence reverts, because a
missing row silently restores the calendar-only cap. Module 3's ops table goes
43 → **44 rows**; read that count out of Stage 4's loader line, which is the
habit this file already prescribes.

### What this release does NOT close

✅  **CLOSED IN v1.16.0 — see "What calc v1.16.0 changed".** The gap read:

> **Programme calendar time is still free.** The fleet is only ever the
> *minimum* that can fly N missions, `ceil(N / trips)`, because nothing charges
> for the decades a serialised programme spends waiting: WACC compounds over
> `mission_duration_yr`, per mission, and there is no programme-level discount.
> So a 5-ship, 25-mission programme is priced as though its five sequential
> campaigns per ship happened at once. That makes fleet size a **one-sided**
> decision — more ships only ever adds saturation, never buys schedule — and it
> is the reason F never exceeds the minimum.

Two things about closing it that the note above did not anticipate. The trade it
predicted is real and measured — the median fleet grows from **1 ship to 2**.
But the charge also lands *inside* a fleet band, which **retires the band
argument this release was built on**, so the search had to become
two-dimensional rather than gaining a term. And the cadence turned out not to be
the mission duration at all: see below.

✅  **The cislunar RAW cells are now measured on the full catalog**, both
settings — see "Measured — FULL CATALOG" above. What remains:

**The beneficiated cell has not been run on this release, at any destination.**
`cislunar` beneficiated was 38,072 s on `1.14.0`; at the 4.10× this release
measured on raw it projects to ~2.6 h, and **that is a projection, from the same
class of estimate this file has now gotten wrong three times.** Budget from a
measured run or do not budget.

**Nothing has been re-measured at the other four destinations.** The trip cap is
a property of the mission profile, so it moves every destination once N > 1, and
the four non-cislunar raw cells in the v1.14.0 matrix are N = 1 — so they stand
as measured, and say nothing about what a *programme* to those destinations
looks like. `leo` and `mars_surface` are the interesting ones: they are where the
two v1.14.0 TPS fixes first become non-zero, and both are inert at `cislunar`.

**The programme-scale curve is superseded as a method but not as a table.** The
N = 1 / 10 / 100 curve above was measured on `1.14.0` and its N = 1 anchor
(26.7863×) reproduces here exactly, so the table stands. What the search adds is
that it locates the optimum per body instead of sampling three points — and on
the real population the answer is a **median of 2 ships and N = 10**, not the
single N = 10 that curve happened to sample.

## What calc v1.16.0 changed

One correction, and it forced a structural change to the search that was not
part of the plan. calc `1.15.0 → 1.16.0`, master `1.18.0 → 1.19.0`. **No Module
3 row moved and no other module changed**, so no Stage 1/2/3 re-run is needed —
but see the warning about which Module 3 catalog you are pointing at, below.

⚠️  **INERT AT N = 1, and therefore on every measured cell in this file except
the N = 10 / N = 100 curve.** Verified, not asserted: 141 of 141 columns
identical and sha256 MATCH with the term on and off. Do not re-measure a
single-mission cell.

### A programme took decades and was charged for none of them

`mission_cost_usd` compounds each mission's up-front costs by `(1 + W)^T` over
that mission's own duration and stops. For one mission that is exactly right.
For a programme it quietly assumes **every mission in the programme happens at
the same time**, and they cannot: one rig digs one hole at a time, so W
campaigns on a ship are strictly sequential.

The lines that were being carried for free are the **amortised** ones — the bus
NRE, the autonomy NRE, and the rig — because they are the only ones bought
*once, at t = 0* and then divided across missions that sell years apart. A
mission's own articles are not affected, and the reason is worth keeping,
because it is what makes the correction small enough to state exactly:

> Shift one mission's whole cash flow later and **its cost/revenue ratio does
> not move** — its costs and its revenue shift together. Only a line paid at
> t = 0 for a mission that sells at t = w × cadence is stretched.

So the charge is one closed-form scalar on three cost lines:

```
cost   = mean of y^w   over w = 0 … W−1        y = (1 + wacc)^cadence
       = (y^W − 1) / ((y − 1) · W)
```

**Terminal value gets the reciprocal series, and that is not a nicety.** Salvage
is collected once, at the *end* of the programme, so relative to a campaign that
sold earlier it arrives late and is worth **less**:
`credit = (1 − y^-W) / ((1 − 1/y) · W)`, which is ≤ 1 and falls with W. Netting
the credit against the purchase first and applying one multiplier to the pair
would have paid a bonus for taking longer to collect a refund — the exact shape
of subsidy this file spends thirty pages cataloguing, arriving inside the term
written to remove one.

Both multipliers are **exactly 1.0 at W = 1**, which is what makes the release
inert on the committed figures, and the charge is applied as a *delta* on top of
the untouched v1.15.0 expression rather than as a rebuilt sum — so no term is
re-associated and the released arithmetic is bit-identical rather than
numerically-equal. Same discipline as the v1.14.2 phase-sort rejection.

### The cadence is the DIG — or the WINDOW, and usually the window

The obvious cadence is `mission_duration_yr`, and it is wrong twice over.

**Too long:** the rig stays at the asteroid. Campaign w+1 starts as soon as
campaign w's feed is out of the ground, while campaign w's capsule is still
flying home. So the cadence is the **stay**, not the round trip.

**Too short:** you can only dispatch the next capsule when a window opens, and
this module has known how rarely that is since v1.5.0. If the rig digs faster
than Earth and the target line up, the rig **idles** and the synodic period sets
the pace. `campaign_cadence_yr` takes the max of the two.

🚨  **The window binds on 165 of 168 rows** in the 400-row raw cislunar sample —
so on this population a programme's pace is set by orbital mechanics, not by
mining rate, and the stay is almost never the constraint. That inverts the
intuition the term was built on.

It also lands hardest on exactly the bodies this model likes. A synodic period
diverges as a → 1 AU, so a NEA at 1.05 AU can only be revisited every ~14 years
however fast its rig works. This file has recorded since v1.5.0 that "Δv
accessibility and time accessibility are anticorrelated"; a single mission pays
that wait **once**, and a programme of W campaigns pays it **W − 1 more times**.
Programme scale is where that anticorrelation finally costs something.

### It retires the band argument, and the search becomes 2-D

This is the part that was not planned for. v1.15.0's whole case for a
one-dimensional ladder was:

> within one fleet band, the saturation multiplier is constant while NRE/N
> falls, the learning curve falls, the rig's share falls and `p_mining` rises —
> **every lever improves and none pushes back** — so the best N in a band is its
> top, N = F × trips.

Programme calendar time **is** a lever that pushes back inside a band, and it is
not a small one: it grows like `y^W` while NRE/N falls like `1/N`. An exponential
against a hyperbola has an interior optimum, so campaigns-per-ship is now a real
decision and the top of the band is frequently not it.

The search is therefore over **(F, W)** with N = F × W:

- **F stays a ladder** — geometric, refined, capped by `max_fleet_ships` — because
  it runs to 64 and cannot be enumerated.
- **W is ENUMERATED EXHAUSTIVELY**, 1 … trips. No ladder, no refinement, no
  unimodality assumption, because `trips` is `min(life / stay, max_trips)` and
  `max_trips` is **5**: the whole dimension is typically five integers. A
  dimension small enough to enumerate should be enumerated rather than argued
  about — and v1.15.0's own verification found its single real miss in exactly
  the gap a heuristic leaves.

⚠️  **That "typically five" depends on a current Module 3 catalog**, and this is
where it bit during measurement. Against the *archived* 43-row
`operational_costs.csv` from the v1.14.0 campaign, "Mining rig maximum trips" is
absent, `rig_trips_per_ship` silently reverts to calendar-only, and `trips` runs
to **20** — quadrupling the enumeration and changing every programme figure.
`schema_check()` caught it, by name, on stdout. **Read the loader's
`Module 3 operational costs  44 rows` line before trusting any number here**;
43 means the trip cap is not in the run.

Two consequences worth keeping:

**N = 1 is now literally in the search set** (F = 1, W = 1) rather than being
*dominated* by N = trips through the band argument. The never-worse invariant
against every committed figure therefore holds by inspection rather than by
proof — which is a strictly better place to be, given that the proof it replaces
has just been retired.

**Non-rectangular programmes stop being mis-booked.** `missions_sharing_rig` was
`min(N, trips)`, which for 7 missions over 2 ships claims 5 campaigns on a rig
that only ever flies 4. It is `min(trips, ceil(N / F))` now, derived from the
fleet like everything else.

### Measured — 400-row raw cislunar stride sample

⚠️  **A SAMPLE, on the current 44-row Module 3 catalog.** This file's own rule is
that a sample predicts a full-catalog *runtime* here to no better than a factor
of ~5, and v1.15.0 established that the rule applies to *ratios between two
settings* too. Nothing below is a full-catalog measurement.

| | search off (N = 1) | search on |
|---|---|---|
| calendar off (`1.15.0`) | **60.9283×** | **31.0693×** |
| calendar on (`1.16.0`) | **60.9283×** | **33.7977×** |
| | *identical, 141/141 cols* | **+8.78% worse** |

**Every row gets worse and none gets better**, which is the direction a
correction must run: median penalty **5.26%**, max **19.72%**, **zero** rows
improved. Median calendar multiplier on the amortised lines **1.323**, max
**2.093**, against a median programme span of **11.5 years**.

**The fleet grows, which is exactly the two-sidedness the gap note predicted**:
median F goes **1 → 2**, and median N **5 → 10**, once a ship can buy schedule
instead of only adding saturation.

🚨  **But W = trips on all 168 rows, so on THIS sample the band argument would
still have given the right answer.** That is worth stating plainly rather than
buried, because it is the one place this release could be over-sold:

- The band argument was a **proof** — "every lever improves and none pushes
  back". Programme calendar time is a lever that pushes back, so **the proof is
  invalid**, and a dimension whose optimum is no longer guaranteed has to be
  searched rather than assumed.
- On this sample the improving levers still win at every body, so the search
  returns the band top anyway. **The 2-D search is necessary but not yet
  load-bearing here.**
- ⚠️  Whether it bites depends on `trips`, and therefore on **v1.15.0's cap**.
  Re-run against the *stale* 43-row Module 3 table — where the trip cap is
  absent and trips reaches 20 — and `y^W` has room to work: **12 of 168 rows
  then choose W < trips**, the median multiplier is 2.918 and the median span
  25.3 years. So the two corrections interact, and capping trips at 5 is most of
  what keeps the calendar charge from overturning the band top.

Runtime on the sample: **37.6 s → 41.5 s**, and the programmes priced per
mission go **8 → 40** (median). That wall clock is ~20 s of catalog load both
paths pay, so the search itself costs considerably more than the 1.1× ratio
suggests. **Do not budget a full run from it** — this file has now mispredicted
full-catalog runtime from a sample three times, including once for a ratio.

### Verification (2026-08-11)

**1. The gated build reproduces HEAD EXACTLY.** `model_programme_calendar =
False`, against `git HEAD` in the same process on the same rows:

```
raw, 400 rows   135/136 shared columns identical | the 1 that differs is pipeline_version
                135/135 less the version stamp   | sha256 842f4026ae9a9f46 MATCH
```

The CSV gains five columns, so byte-identity of the whole file was never
available — the hash is over the shared columns, the same construction v1.14.0
and v1.15.0 used for the same reason.

**2. The term is exactly inert at N = 1**, which is what protects every
committed figure in this file:

```
raw, 400 rows, calendar ON vs OFF   141/141 columns identical | sha256 MATCH
```

Note this is a *stronger* check than item 1 and the one to re-run first if this
release is ever suspected: it compares the new code against itself with only the
gate moved, so it isolates the term from the refactor around it.

**3. Never-worse holds, and now by construction.** Searched against N = 1, both
with the calendar charged:

```
pairs 168 | max searched/N=1 0.909928 | worse 0 | improved 168 | median improvement 50.9%
```

Every row improves because (1, 1) is in the search set, so the search cannot
report worse than the programme every committed figure was measured at.

**4. 🚨  THE 2-D SEARCH WAS BRUTE-FORCED, because the argument it replaced was.**
v1.15.0 brute-forced the band argument since that argument was load-bearing for
its ladder; this release retires the argument, so the search that replaced it
had to be checked in its own right. Every (F, W) on a 20 × 8 grid was pinned and
priced exhaustively — 160 full evaluations against one catalog load — and
compared per body against what the search reported:

```
bodies compared 49 | grid F 1..20 x W 1..8 (W clamped to trips)
searched WORSE than brute force : 5 | max searched/brute 1.000274  (0.027%)
W chosen == brute-force W       : 49 of 49
F chosen == brute-force F       : 42 of 49   (every miss is |dF| = 1)
```

**The new dimension is exact on every body.** All five misses have the right W
and the wrong F by exactly one ship, so the residual is **not** the 2-D
extension — it is the **inherited F ladder's spacing**, unchanged from v1.15.0,
and it costs **0.027%**. Compare v1.15.0's own brute force, which found one real
miss at **0.97%** from the concentration grid: this is a factor of 35 smaller and
in a different mechanism.

⚠️  Two rows come out *better* than the brute force. That is the grid running out
of room at F > 20, not a defect — the same "a capped search is not a sample of an
uncapped one" trap this file records for `eval_row_cap`, `jpl_limit` and
v1.15.0's own truncated sweep. The harness reports it as its own line rather than
counting it as an exception.

**5. The mass-ledger identity holds exactly**, every setting, `max |error|
0.000000000 kg` — as it must, since N enters nothing in the mass cascade.

**6. Serial and parallel are byte-identical WITH THE SEARCH ON** — required
after any change to the search, and the check that would catch a worker seeing a
different ladder from the parent:

```
raw, 1,200-row stride, calendar ON, search ON
serial 58.6 s | 8 workers 58.5 s | 495 rows | sha256 221b4d4bf4441ed8 MATCH
```

⚠️  The two wall clocks being equal is the catalog load dominating a small run,
not a parallel regression — v1.10.1's "more workers is not always faster" note.
The sha256 is what this row is for.

**7. Beneficiated reproduces too**, both checks, on a 150-row sample:

```
gated off vs HEAD       135/135 shared columns less the version stamp | sha256 63326e750efeee87 MATCH
calendar ON vs OFF, N=1 141/141 columns identical                     | sha256 MATCH
```

### What this release does NOT close

**Every ship is identical and every campaign is the same length.** The programme
is a rectangle, F × W, priced off one cascade. A real programme would fly a
first mission, learn, and size the second differently — and this model's own
learning curve and reliability growth say so. Rectangles are what make the
search affordable; they are not what a programme looks like.

**The fleet is still built at t = 0.** F ships are bought up front and each
flies W campaigns. Staggering acquisition — buy the second ship out of the
first's revenue — is the obvious next refinement and it would cut the charge
this release adds, so **the direction of the remaining error is optimistic for
small fleets and pessimistic for large ones.**

**Nothing is measured on the full catalog.** Every figure above is a 400-row
stride sample. The cislunar raw cell with the search on is one ~2,000 s run on
`1.15.0` and has not been repeated here.

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
- **Never build a merge key by stringifying a float column.** A numeric
  identifier that pandas has typed `float64` renders as `"3.0"`, which is not
  null, not obviously wrong, and joins nothing. Go through `Int64` first. This
  cost NEOWISE four releases of contributing zero rows — and note the shape,
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
- **Composition fractions sum to 0.76–0.96**, not 1.0. The residual is valued
  at a bulk-silicate floor rather than zero.
- Do not globally suppress warnings in `catalog.py` — real `RuntimeWarning`s
  (divide-by-zero in the derived physical columns) need to stay visible.
- **Never use `.astype(bool)` on a flag that arrives through a CSV.** It reads
  the *string* `"False"` as `True` and `NaN` as `True`. It happens to be
  correct today only because every propellant row states `restartable` and
  `propellantless`, so pandas infers dtype `bool` — add one row that omits
  either and a solid motor silently rejoins the search, with no error
  anywhere. Use `_truthy(series, default=...)`, which parses the strings and
  makes you say what a *missing* value means instead of letting truthiness
  decide. Same shape as the `str.contains` / `regex=False` trap above: the
  wrong behaviour is the quiet one.
- **Re-run Stage 3 after upgrading it.** Every Module 3 column Module 4 reads
  is read defensively, so a stale `propellants.csv` does not raise — it
  reverts tank mass to zero, drops the maturity gate, and un-excludes solids
  and sails, all silently. `schema_check()` in `calc.py` now names each
  missing column and the behaviour it reverts; do not weaken it into a
  generic "columns changed" warning, because the consequence is the useful
  part.

  ⚠️  **`schema_check()` checks COLUMNS, not VALUES, and that is a real hole.**
  It checks Module 3 **rows** as well since v1.14.0 — the ops table is keyed by
  category, so a missing *figure* was invisible to a column test, and
  `_MODULE3_REQUIRED_OPS` now names each row Stage 4 needs alongside the model
  term its absence silently reverts. That closes the missing-row half. The
  wrong-**value** half is still open and is the one below.

  Editing a number in a Module 3 table — a density, a status, a boil-off rate
  — leaves the schema identical, so nothing warns and Stage 4 quietly runs on
  the old figure. This cost a full measurement pass during v1.12.0: the argon
  rows were rewritten, Stage 3 was re-run, the CSV did not actually land, and
  two full-catalog runs plus a determinism sweep were measured against the
  table that was being replaced. Nothing anywhere said so.

  The cheap habit that catches it: **Stage 4's loader prints row counts for
  every Module 3 table it reads** (`📥 Module 3 propellants  41 rows`). Read
  those against what Stage 3 said it wrote. A count that has not moved after
  you added a row is the whole diagnosis. When only values changed and no
  count moved, spot-check the field itself out of the CSV before trusting a
  number — one `read_csv` on the row you edited.

  The deeper lesson from that pass is in "What v1.12.0 changed": the headline
  cislunar ratios were **bit-identical** with the stale table and the correct
  one, because the best mission was not affected by the change. A best-case
  cell is a poor detector for anything wrong below the top; the
  propellant-share breakdown and the evaluable-row count are what caught it.

## Data sources fail softly by design

Unreachable or empty sources are tolerated and the run continues. MP3C is
regularly DNS-blocked from Colab. Do not "fix" an empty source by flipping its
toggle off — the toggle is for deliberately excluding a source, not for
routing around an outage.

`metals.dev` defaults to the key `"DEMO"`, which makes the fetcher skip
entirely. That is intentional; the demo endpoint is heavily rate-limited.

**But a soft failure silently changes the population you are measuring, and
that will invalidate a comparison without warning.** Missing spectral types
are backfilled by inferring a coarse type from albedo, so an outage does not
shrink the catalog — it *inflates* it with guessed taxonomy.

Check `spectral_type_source` (`source` / `tholen` / `albedo` / `albedo_assumed`
/ `unknown`) before comparing any run to a committed number. The startup
banner's "Active sources" line lists what was *enabled*, not what answered —
read the `Source summary: {...}` dict instead.

⚠️  **`Source summary` reports what was FETCHED, not what was USED, and the gap
between those is where NEOWISE hid for four releases.** It printed 183,408 on
runs where the source contributed zero rows, because the failure was in the
merge key rather than the fetch. Since v1.1.0 `merge_sources` also reports how
many of each supplement's designations **matched the backbone**, and shouts
when that number is zero or when a source loses every row to keying. Read the
`Merged <source>: N supplement records (M matched the backbone, +K new
entries)` line — `M = 0` on a source that fetched rows is always a bug in that
fetcher, never an empty upstream table.

The corresponding check on the output CSV is one line, and it is worth running
against any catalog you did not watch being built:

```bash
py -c "import pandas as pd; d=pd.read_csv('asteroid_pipeline/asteroid_catalog.csv',low_memory=False); print({c:int(d[c].notna().sum()) for c in d.columns if c.startswith('source_')})"
```

A `source_*` column sitting at 0 while its fetcher reported success is the
signature.

### The SsODNet outage that wasn't an outage (fixed in v1.0.9)

This one is worth reading in full, because nothing about it looked wrong.

ssoBFT renamed its identity columns — `sso_number`/`sso_name`/`sso_id` became
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
— roughly 1,900 real-taxonomy bodies instead of ~24,700. The V-type count is
the tell: V-types are rare, and 3,988 of them was an artefact of guessing
taxonomy from albedo.

Three separate things kept it quiet, and each is a trap worth not rebuilding:

- **The drift warning only fired when fewer than 5 of 24 columns matched.**
  Fourteen still matched, so losing every merge key read as healthy. A
  projection that tolerates missing columns must still *assert* the ones it
  cannot work without — that is what `_SSODNET_REQUIRED` is for now.
- **The row-cap sort key sat behind an `if in df.columns` guard**, so
  truncation silently stopped sorting and took an arbitrary 50,000 rows
  starting near asteroid 367488 instead of Ceres. A guard that turns a wrong
  answer into a quiet one is worse than no guard.
- **`pq.ParquetFile.schema` is the PHYSICAL parquet schema**, which names a
  nested list column by its inner path, so `spins.period.value` read as
  absent. Test membership against `schema_arrow` — that is what
  `read(columns=…)` accepts.

After fixing, spot-check against literature rather than trusting row counts:
Ceres 939.4 km / 2.162 g/cm³ / 9.074 h / C, Vesta 522.8 / 3.411 / 5.342 h / V,
Pallas B, Psyche X, Eros 5.27 h / S.

## Google Drive makes the tree look dirty — run the hooks

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
the file* — a differing size is normally conclusive proof of a change. That is
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
heavier reset is to delete the index and rebuild it — safe when the working
tree already matches HEAD, and it discards staging only:

```bash
rm -f "$(git rev-parse --git-dir)/index" && git reset
```

A checkout that moves *back* to a commit predating the hooks deletes them
mid-checkout, so they can't run — repair by hand afterwards.

## Environment

Windows, Python 3.13, invoked as `py` (a bare `python` hits the Microsoft Store
alias and fails). The working tree is on Google Drive with the git directory
outside it — see the README's "Working copy" section, especially if the folder
gets renamed again.
