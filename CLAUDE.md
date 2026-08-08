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

Current: catalog `1.0.9`, mineral_value `1.7.0`, transportation `1.9.0`,
calc `1.11.0`, master `1.14.0` (the master version is a literal in
`build_master.py`'s `MASTER_HEADER` and `MASTER_ORCHESTRATOR` — two places).

calc `1.10.1` was the one stamp that did **not** mean the numbers moved. It
was a pure performance release, verified bit-identical, and it was bumped
anyway so that a CSV still names the code that produced it — the rule above is
"changing a number means bumping", not "bumping means a number changed".

> ⚠️  **The five-destination tables below were re-measured on
> transportation `1.9.0` + calc `1.11.0` on 2026-08-08.** All ten cells, one
> destination at a time, Stage 2 re-run for each. The catalog was NOT
> re-downloaded — Stage 1 is untouched by this release, and re-fetching would
> only add live-quote drift to a comparison that is about the mission model.
>
> **`cislunar` remains the best case at 22.4665×**, and it is one of the cells
> that got *better*. The direction is mixed by destination and that is the
> interesting part — see "The v1.11.0 matrix" below.
>
> Superseded: the 2026-08-07 reproduction's ten cells (they remain correct for
> calc `1.10.0`/`1.10.1` and are kept below for comparison), and the
> programme-scale curve 22.93× → 9.85× → 7.28×, which was measured at the old
> N=1 anchor of 22.93× and has **not** been rebuilt on `1.11.0`.
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

⚠️  **The timings in this file have moved three times, twice for reasons that
had nothing to do with each other.** Current, on calc `1.11.0` / six physical
cores, full catalog, measured 2026-08-08:

| | raw | beneficiated | ratio |
|---|---|---|---|
| `cislunar` | 89 s | 462 s | 5.2× |
| `lunar_surface` | 84 s | 437 s | 5.2× |
| `mars_surface` | 158 s | 966 s | 6.1× |
| `leo` | 177 s | 948 s | 5.4× |
| `earth_surface` | 174 s | 1,017 s | 5.8× |

The whole ten-cell sweep is **about 70 minutes** including a Stage 2 re-run per
destination.

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

### The v1.11.0 matrix (current)

Best cost/revenue (lower is better, 1.0 is breakeven), measured 2026-08-08 on
transportation `1.9.0` + calc `1.11.0`, full catalog, 30,458–32,442 evaluable
rows per destination. The prior column is the 2026-08-07 reproduction on calc
`1.10.0`/`1.10.1`, so the delta is the mission-model change: tank mass, the
tanker bill, the RTG option, and a propellant search 4.6× wider.

| destination | raw `1.10.x` | **raw `1.11.0`** | Δ | benef `1.10.x` | **benef `1.11.0`** | Δ |
|---|---|---|---|---|---|---|
| `earth_surface` | 45,893.7× | 45,236.50× | −1.43% | 25,038.5× | 26,256.72× | **+4.87%** |
| `leo` | 72.4520× | 71.0459× | −1.94% | 48.1286× | 51.2223× | **+6.43%** |
| `cislunar` | 31.8269× | 31.7712× | −0.18% | **22.9336×** | **22.4665×** | **−2.04%** |
| `lunar_surface` | 75.8315× | 75.5110× | −0.42% | 40.6132× | 37.8133× | **−6.89%** |
| `mars_surface` | 70.4063× | 70.4346× | +0.04% | 51.8161× | 51.9597× | +0.28% |

**`cislunar` is still the best case, at 22.4665×**, and it is one of the cells
that improved.

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
xenon's 1.9%. Across a full `earth_surface` run iodine takes 52% of winners and
argon 36%; hydrolox wins 7 rows out of 32,442 and methalox 30. Chemical
propulsion is essentially extinct in this model. Note what this means: the tank
term is only ~0.7% of launch mass in the *winning* missions, because the search
routes around it. Its effect is not a cost it adds, it is **which propellant it
disqualifies**.

**Mars barely moved (+0.04% raw, +0.28% beneficiated), and it is the only
destination that did not adopt iodine** — it wins on argon at both settings.
That is a compositional/architectural result, not noise: the Mars leg is a
separate heliocentric transfer, and its winner identity (8651 M raw, 6178 P
beneficiated) reproduces `1.10.x` exactly.

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
orbital refuelling, and the RTG option. What that release **also** established
is that the reference tables themselves were a source of error, not just the
code reading them — sixteen flown propellants were missing, and the model was
therefore choosing the best of seven options while the report claimed it had
chosen the best available. Three storage gaps remain open and all three run
optimistic: **volatile cargo is never kept cold**, **the sun never sets** on
the processing plant, and **boil-off cannot be bought down** with a
cryocooler. They are listed with their citations in `STORAGE_REFERENCE` — the
data is there, the consumer is not.

## The fourteen things the model stopped giving away

Each defaults ON and each moved every number. They are corrections, not
options; the flags exist to isolate effects, not to be left off.

Two arrived in v1.10.0 and are documented under "What v1.10.0 changed" rather
than repeated here: the **electric propulsion stage**, which was flown as mass
and never billed, and the **return vehicle's structure**, which did not grow
with its cargo.

Two more arrived in v1.11.0 and are under "What v1.11.0 changed": **propellant
tankage**, which is mass in the rocket equation that scales with volume rather
than with the propellant inside it, and **orbital refuelling**, where a
vehicle quoting a refuelled escape payload was not being charged for the
tanker flights that payload assumes.

Notice the shape all four share. The mass cascade and the cost cascade are
written in different places, and nothing checks that every kilogram in one has
a price in the other — or that every kilogram the cost model pays for is
actually being flown. That is the bug class to look for in this codebase
first.

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

**Rig service life caps amortisation** (v1.8.0). A 15-year rig cannot serve
100 missions of 2 years each. `missions_sharing_rig` is capped at
`life / stay`, and at long stays this makes the rig 13.8x MORE expensive per
mission than the old flat division, not less. Terminal value is credited only
when nre_amortization_missions > 1 -- a rig nobody returns to is stranded, not
an asset, which is what keeps a single-mission run unchanged.

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

⚠️  Calc `1.10.0`. The N = 1 cell is 22.4665x on `1.11.0`, so the cost/revenue
column is ~2% optimistic throughout; the other four columns are unaffected by
that release.

The winner is 7753 (B) at every N. The 10->100 step buys little because one rig
only serves 4 missions at this stay length, so mission 5 buys a new rig. "Fly
more missions" is real but sublinear, and bounded by market saturation at the
far end.

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

### Propellants: 7 rows → 40

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

Check `spectral_type_source` (`source` / `tholen` / `albedo` / `unknown`)
before comparing any run to a committed number. The startup banner's "Active
sources" line lists what was *enabled*, not what answered — read the
`Source summary: {...}` dict instead.

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
