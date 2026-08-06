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

Current: catalog `1.0.9`, mineral_value `1.6.0`, transportation `1.8.2`,
calc `1.10.0`, master `1.12.0` (the master version is a literal in
`build_master.py`'s `MASTER_HEADER` and `MASTER_ORCHESTRATOR` — two places).

> ⚠️  **Every committed result number below predates calc `1.10.0` and is
> superseded.** That release changed what the per-asteroid search optimises,
> costed the electric propulsion stage for the first time, and made the return
> vehicle scale with its cargo. All three move every row. The tables are kept
> because the *shape* of the results still holds and because the deltas are the
> point — but treat the digits as stale until someone re-runs all five
> destinations on the v1.0.9 catalog. See "What v1.10.0 changed" below.

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
v1.3.0). At an in-space destination the terrestrial price is *replaced* by
`in_space_utility × launch-cost-avoided`. Two consequences that look wrong
but are not: bulk iron jumps from $0.50/kg to ~$2,977/kg in LEO, and
platinum drops to **zero**, because there is no orbital market for it. The
in-space prices are derived through the rocket equation in
`delivered_cost_usd_per_kg()`, not tabulated — but `IN_SPACE_UTILITY` is a
table of *engineering judgements*, and it is the softest assumption in the
whole pipeline. Treat it as a dial, not a measurement.

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

Note this makes the beneficiation path ~8× slower — on the v1.0.9 catalog
(35,778 asteroids) a destination costs ~140 s raw against ~1,100 s
beneficiated, so re-measuring all five destinations is a couple of hours, not
a coffee break. `concentration_search_steps` is the dial.

**The beneficiation power plant feeds back into the rocket equation.**
Processing energy (Module 3: 200 Wh/kg dug, 500 Wh/kg concentrated) over the
stay time gives a power draw; Module 3's 60 W/kg-at-1-AU row scaled 1/r² by
the target's semi-major axis turns that into array mass; the array is
launched like everything else. Payload → feed → power → mass → payload is a
genuine circular dependency and `evaluate_combo` solves it by fixed-point
iteration. The 1/r² term is why a 3+ AU target needs a ~54× heavier plant
than a 1 AU one.

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

Best cost/revenue, beneficiated, across all 35,778 evaluable asteroids at
catalog `1.0.9` / calc `1.9.1` (lower is better, 1.0 is breakeven). The
pre-1.0.9 column is kept because the *change* is the point — it is entirely a
population effect, not a modelling one:

| destination | pre-1.0.9 | **current** | winner |
|---|---|---|---|
| `earth_surface` (default) | 191,359× | 156,725× | 17188 (1999 WC2), M |
| `leo` | 290× | 290.4× | 434 Hungaria, Xe |
| `lunar_surface` | 74× | 53.5× | 4660 Nereus, Xe |
| `cislunar` | 143× | 39.8× | 4660 Nereus, Xe |
| `mars_surface` | 34× | **25.2×** | 4015 Wilson-Harrington, B |

Two things in that table are worth not "fixing":

**Cislunar and lunar surface swapped.** The Moon used to beat cislunar (74×
vs 143×) and no longer does (53.5× vs 39.8×). Nothing about either
architecture changed — cislunar gained 3.6× from the larger population and
the Moon only 1.4×, because the restored catalog contains accessible NEAs
(the winner is 4660 Nereus for both) that suit the cheaper cislunar capture.
The ordering is a property of which asteroids you know about, not just of Δv.

**LEO barely moved** (290× → 290.4×) while everything else moved a lot. Its
winner, 434 Hungaria, was already inside the old ~1,850-body subset, so 13×
more targets found nothing better. A destination that does not respond to a
population change is not evidence the run failed.

`mars_surface` remains the best case the model can reach. That changed in
`1a5e0c8` when the lunar and Mars destinations landed, and the gap has been
tracked on Mars ever since.

**`mars_surface` is the best case the model can currently reach**, not
cislunar — that changed in `1a5e0c8` when the lunar and Mars destinations
landed, and the gap has been tracked on Mars ever since. Flying more missions
is the strongest remaining lever. Mars, beneficiated, on the restored catalog:
**25.2× at N=1 → 6.9× at N=10 → 5.3× at N=100** (was 34.2 → ~10 → ~8). See the
reliability-growth and rig-service-life entries below, which pull against each
other — that is why the 10→100 step buys so little.

**Beneficiation behaves differently at Mars than it did at cislunar, and the
old cislunar intuition does not carry over.** At cislunar (`fa263ad`) the
optimiser *declined* to concentrate on the single best body, so beneficiation
halved the median and left the best case untouched. Measured across every
destination on one catalog (v1.0.9, 35,778 evaluated), best cost/revenue:

| destination | raw | beneficiated | best target concentrated? |
|---|---|---|---|
| `earth_surface` | 236,629× | 156,725× | yes, 2.2× |
| `leo` | 445.9× | 290.4× | yes, 2.5× |
| `cislunar` | 39.79× | **39.79×** | **no — declines** |
| `lunar_surface` | 126.6× | 53.5× | yes, 2.5× |
| `mars_surface` | 54.2× | **25.2×** | yes, 4.2× |

**Cislunar is the one destination where the optimiser declines to concentrate
the best body** — 39.79× to the hundredth either way. That is the `fa263ad`
result, and it still reproduces on a catalog 19× larger. Everywhere else
beneficiation moves the best case hard, and usually changes which asteroid
wins. So do not repeat "beneficiation does not move the best target" as a
general fact: it is a cislunar result, not a property of beneficiation.

The reason is compositional, and 4660 Nereus makes it visible — the *same*
asteroid wins both cislunar and lunar surface, and the optimiser declines to
concentrate it at cislunar while concentrating it 2.5× for the lunar surface.
The decision belongs to the (target × destination) pair, not to the target.

The median halves roughly everywhere regardless, cislunar included
(4,053× → 2,161×, −47%).

Closing the last 25× is not a tuning exercise. Rig terminal value and
in-space manufacturing were the named candidates and both shipped in v1.8.0
(`e860259`), so what remains is joint trajectory/payload optimisation, and
programme scale. Do not manufacture viability by editing `IN_SPACE_UTILITY`
or the in-space demand ceilings -- both are judgement tables and both are
load-bearing.

## The twelve things the model stopped giving away

Each defaults ON and each moved every number. They are corrections, not
options; the flags exist to isolate effects, not to be left off.

The last two arrived in v1.10.0 and are documented under "What v1.10.0
changed" rather than repeated here: the **electric propulsion stage**, which
was flown as mass and never billed, and the **return vehicle's structure**,
which did not grow with its cargo.

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
measurement.

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
other. Mars beneficiated, catalog v1.0.9: N=1 25.2x, N=10 6.9x, N=100 5.3x.
The 10->100 step buys little because one rig only serves 7 missions at that
stay length, so mission 8 buys a new rig. "Fly more missions" is real but
sublinear, and bounded by market saturation at the far end.

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
the entire cost of ISRU. Now: hydrolox only, at bodies with a non-zero ice
fraction, at the stoichiometric 1.286 kg of water per kg of propellant
(electrolysis yields 8 kg O₂ per kg H₂; a 6:1 O/F stage needs 9/(1+6) kg of
water per kg burnt). The rock it takes comes off the rig's throughput and the
body's mineable mass *before* any ore is loaded. Default flipped to True,
because gated and costed it is an option a real programme would evaluate.

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
