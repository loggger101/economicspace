# The model

What a run does with a kilogram, from the asteroid to the buyer: the mission,
where the material is sold and what that makes it worth, the propulsion and
storage tables, beneficiation, programme scale, and what the model charges for,
declines to charge for and cannot capture. How to run it, the Tuning table and
the current numbers are in [README.md](README.md); why the load-bearing choices
must not be "fixed" is in
[CLAUDE.md](CLAUDE.md#the-model-load-bearing-assumptions-do-not-fix); when each
term arrived is in [versions.md](versions.md).

- [Mission model](#mission-model)
- [Where the material is sold](#where-the-material-is-sold)
- [The propulsion and storage catalog](#the-propulsion-and-storage-catalog)
- [Beneficiation](#beneficiation)
- [Programme scale](#programme-scale)
- [What the model charges for](#what-the-model-charges-for)
- [What the model deliberately does not charge for](#what-the-model-deliberately-does-not-charge-for)
- [What the model does not capture](#what-the-model-does-not-capture)

## Mission model

Return-sample architecture, uncrewed throughout: no life support, no crew
habitat, no human in the loop past LEO injection:

```
Earth launch → LEO → outbound burn → asteroid rendezvous
    → autonomous station-keeping + mining
    → return burn → Earth re-entry (sample-return capsule)
```

That is the `earth_surface` mission. Every other destination ends the return
at a depot or a surface instead, with its own capture, delivery vehicle and
arrival costs; see [What it costs to get there](#what-it-costs-to-get-there).

## Where the material is sold

This is the single most consequential setting in the pipeline, so it gets its
own section.

Nothing mined has an intrinsic price; it is worth whatever it costs to put
an equivalent kilogram where the customer already is. The destination sets
both what the cargo sells for (Stage 2) and what the mission costs to fly
(Stage 4), and **both stages carry the field, so both must be set**:

```python
MASTER_CONFIG.delivery_destination = "cislunar"   # writes Stage 2 and Stage 4
```

Setting only one is the classic error; it prices the cargo at a depot while
still paying to land it in Utah. Stage 4's `destination_check()` refuses to
let that pass quietly.

### What the rock is made of

**Since calc v1.24.0 a body is mined and sold as the minerals it is made of.**
Stage 1's catalog (data contract 1.7.0) divides each class's four coarse
fractions into phases, from the class's meteorite analogue: an S-type is
olivine, two pyroxenes, plagioclase and metal, plus the troilite and chromite
that sit in what the four fractions leave; a C-type is phyllosilicates,
magnetite, sulfide and carbonate with its water; an outer-belt D-type's ice is
water, carbon dioxide and ammonia. Stage 2 prices what each phase yields:
sulfur, phosphorus, chromium, titanium, CO2, ammonia, and the trace metals of
meteoritic iron (copper, germanium, gallium, molybdenum, tungsten, rhenium).

**A phase is worth the better of two prices**: its own row, the mineral used as
it is (olivine as shielding rock), and the value of its elements, the mineral
taken apart (troilite for its iron and sulfur). The knapsack loads each phase
separately, so a concentrating mission can now carry troilite or chromite
beside its metal.

Measured on `verify.py`'s four cislunar cells, the phases against the four
fractions on identical inputs. The switch off reproduces the previous model to
the bit on all four:

| cell | median body | best row |
|---|---|---|
| raw, N = 1 | **5.35% better** | 9.1000x to 8.9791x |
| raw, searched | **7.87% better** | 6.9929x to 6.6904x |
| beneficiated, N = 1 | **17.23% better** | 24.2785x to 21.8083x |
| default, beneficiated and searched | **11.29% better** | 16.3739x to 13.2109x |

On the default cell the winner's hold goes from metal, silicate and carbon to
**metal, troilite, chromite and carbon**, and a delivered kilogram is worth 23%
more. It is not a uniform lift: **D-types get worse**, because their carbon is
part soluble organics and their ice part CO2 and ammonia, each worth less than
the water it used to be counted as. At `earth_surface`, where rock is worth
cents, chromium makes chromite the best phase of an S-type.

**Since calc v1.25.0 the refinery is flown.** Stage 2 used to take refining
out of the price as a dollar estimate of a plant running for fifteen years;
now every phase is valued before that deduction, and the mission carries the
refinery: its energy, per phase and by the route each is sold by, joins the
processing draw that sizes the array, and its plant rides with the mining rig
and is costed as the rig is. A refinery that runs only for the stay costs far
more per kilogram than one running for fifteen years, so **the sign depends on
the stay**:

| cell | median body | best row |
|---|---|---|
| raw, N = 1 | **18.3% worse** | 8.9791x to 8.9723x |
| raw, searched | **24.6% worse** | 6.6904x to 6.5619x |
| beneficiated, N = 1 | **2.8% better** | 21.8083x to 20.6165x |
| default | **1.9% better** | 13.2109x to 12.6380x (a different winner) |

Raw ore over a short stay pays for a big array for a few months, worst at
2.2-2.8 AU where sunlight is thin; concentrate is dug for years, so its
refinery is cheap. Refining on the cruise home is not modelled.

**Since calc v1.26.0 the metal and the sulfide are the minerals they are.**
Stage 1's catalog (data contract 1.8.1) carries `comp_phases_detailed` beside
`comp_phases`: the metal as the **kamacite, taenite, tetrataenite and
cohenite** a class holds, the sulfide by species (**pyrrhotite, pentlandite,
niningerite, oldhamite, daubreelite**), and the **phosphates** (merrillite,
chlorapatite) and **CAI oxides** (perovskite, hibonite) that sat unnamed in
the residual. The class is what differs: an ordinary chondrite's metal is
Ni-rich, mostly taenite, where an iron meteorite's is mostly kamacite, and a
C-type's nickel is in pentlandite. A class whose metal has no meteorite source
keeps the alloy "nickel-iron" always meant.

Stage 2 prices the three alloys by **deriving** them from the nickel-iron row
(the lever rule gives each half's nickel, and each trace metal partitions
between them so the iron-meteorite mix gives the row back exactly), so an
S-type's metal carries more nickel and platinum per kilogram than an M-type's.
The alloys are intergrown in one metal grain and no process separates them,
so **Stage 4 sells them as one product**, `nickel-iron`, at their blended
value.

| where | median body, detailed against `comp_phases` |
|---|---|
| `cislunar`, all four `verify.py` cells | **unchanged** to 0.08%, same winners |
| `earth_surface`, raw N = 1 | **25.4% better** (C complex 38%, S complex 25%) |
| `earth_surface`, beneficiated N = 1 | **33.0% better** (C complex 56%, S complex 30%) |

In space a kilogram of structural metal sells at the launch cost it avoids,
whatever its nickel, so the minerals move a terrestrial ledger and barely
touch a depot's. `CALC_CONFIG.model_detailed_phases = False` is the earlier
model to the bit. See [versions.md](versions.md#master-v1400--catalog-v181--mineral_value-v1120--calc-v1260).

⚠️  The trace metals are worth **nothing** at an in-space destination: none
is wanted there, and flying a kilogram of gallium home costs more than it
fetches. They count at `earth_surface` only. The new reference prices are the
order of USGS's 2024 figures and are approximate. These are samples; see
[versions.md](versions.md#master-v1380--catalog-v170--mineral_value-v1110--calc-v1240)
for the full record.

### What a kilogram is worth

In-space prices are the launch cost avoided, **derived** rather than
tabulated: the cheapest LEO price a buyer can book today (Falcon Heavy
expendable, chosen by a rule spacecost asserts at import), carried further by
walking a chain of real stages backwards from the payload (`delivered_cost_usd_per_kg` over
`_DELIVERY_LEGS`, both re-exported here from `spacecost.delivery`, where every
leg's Δv is a lookup into the same table Stage 3 reads). Staging is modelled
leg-by-leg because it matters, a
single stage flying the whole 6,100 m/s to the lunar surface needs 12.81 kg
in LEO per kg landed against 5.28 kg for the tug-plus-lander pair that would
actually be flown.

| Destination | Launch cost avoided | kg in LEO per kg | Chain |
|-------------|--------------------|------------------|-------|
| `earth_surface` *(default)* | - | - | Terrestrial commodity prices |
| `leo` | $2,555/kg | 1.00 | Falcon Heavy (expendable) $/kg-to-LEO |
| `gto` | $5,168/kg ($414 of it stage hardware) | 1.86 | LEO to GTO (2,455 m/s), the perigee burn alone, no plane change |
| `geo` | $8,462/kg ($937 of it stage hardware) | 2.95 | LEO to GTO (2,455 m/s), then 1,836 m/s to circularise and remove 28.5 deg |
| `cislunar` | $7,236/kg ($742 of it stage hardware) | 2.54 | TLI + NRHO insertion (3,600 m/s), cryo tug |
| `lunar_surface` | $48,226/kg ($34,737 of it stage hardware) | 5.28 | TLI + LOI (4,050 m/s) tug, then 2,050 m/s lander |
| `mars_orbit` | $9,154/kg ($1,046 of it stage hardware) | 3.17 | TMI (3,600 m/s) + MOI (900 m/s) into the 1-sol staging orbit |
| `mars_surface` | $186,306/kg ($159,209 of it stage hardware) | 10.61 | TMI (3,600 m/s), aeroentry at 30% surviving mass, 800 m/s retroprop |

`gto` is a refuelling depot in a standard 28.5 deg transfer orbit, topping up
GEO-bound satellites before their apogee burn. Its chain is the first leg of
`geo`'s, so a kilogram there is never the dearer of the two, and it sits
under the cheapest direct launch to GTO, which spacecost tests. It serves
GEO's customers one burn earlier, so it takes `geo`'s utility profile by
reference rather than a second copy; what differs is the price and the
market, whose ceiling is anchored on the apogee propellant of a year's
launches to GTO rather than on station-keeping for the standing fleet.
Capture only binds the ellipse at perigee, as at cislunar, and no plane
change is charged, which is optimistic for a high-inclination arrival; see
`_gto_capture_dv_km_s`. It is wired in and has **not** been through a
campaign: no cell in the matrices below is a `gto` cell.

`geo` is a geostationary servicing depot, and it is the only destination in
this model with a **paying customer today**: roughly 610 active satellites,
and MEV-1 and MEV-2 have already docked with and station-kept commercial GEO
spacecraft. It is also the only one that pays a **plane change**. An asteroid
arrives near the ecliptic and GEO is equatorial, so 23.44 deg has to be bought
out on arrival; a launch from Canaveral parks at 28.5 deg and buys a slightly
bigger one. Those are two different numbers for the same manoeuvre, 1,730 and
1,836 m/s against 1,477 coplanar, and the model keeps them apart on purpose.

Its market is the narrow one. A depot refuels and services satellites, so the
volatiles hold most of their value and the structural metals lose most of
theirs: water is worth $9,818/kg there against cislunar's $10,607, while iron
is worth **$1,649/kg against cislunar's $7,337**. It is the first destination
whose utility overrides run downward on the metals rather than the volatiles,
and the argument is different in kind: the lunar and martian discounts are
about local **supply**, and this one is about local **demand**. Nobody launches
a kilogram of copper to geostationary orbit, so asteroid copper substitutes for
nothing there.

`mars_orbit` is the 250 x 33,793 km 1-sol elliptical staging orbit NASA
DRA 5.0 parks a Mars vehicle in; its period matches a sol to within a minute.
Capture there only has to **bind** the ellipse rather than circularise it, so
MOI is 900 m/s where a 200-km orbit costs 2,100 at the same arrival energy,
the same trade NRHO wins on at the Moon. It is the only Mars destination that
enters no atmosphere and lands nothing, so it pays neither the entry-survival
fraction below nor a lander, and it is the one in-space destination whose
**utility profile is the base one**: everything martian sits 4,100 m/s of
ascent away, so a depot there competes with Earth freight, not with the crust.

Mars' entry survival fraction is measured, not assumed: MSL landed 899 kg of
a 3,153 kg entry mass (28.5%) and Perseverance 1,026 of 3,369 (30.5%), on
JPL's best-estimated entry trajectories. The
lander dry-mass fraction of 0.20 is the Apollo LM descent stage (2,134 kg dry
on 8,200 kg of propellant).

⚠️ **The two surface figures are marginal-transport lower bounds.** They price
the propellant, the launch of every stage and, since spacecost `v0.4.0`, what
building the expended stages costs, on the cheapest LEO price a buyer can book,
with no first-of-kind development, no programme overhead and no cadence limit.
Real delivered cost today is far higher; CLPS lunar landers run on the order of
$1M/kg at ~100 kg scale. Read them as "what it could cost at industrial scale",
not "what it costs now".

The surface figures include building the stages a chain expends (since
spacecost `v0.4.0`): that is 72% of the lunar price and 85% of the Mars one,
against 11-12% at the orbital destinations, which is why both surfaces rose
while every orbit fell at that repin.

A kilogram sitting at a depot is worth **the better of its two fates**, and
the pipeline picks per commodity:

- **Used in space**: worth its terrestrial price **plus** the launch bill
  delivering it avoids, scaled by the in-space utility factor (base profile:
  water 1.00, structural metals 0.70, silicates 0.25, carbon 0.40, organics
  0.20), less the cost of refining it into a usable article on site. Note the
  *plus*: the launch cost is on top of the material, not instead of it.
- **Shipped down**: worth its terrestrial price **minus** the downleg:
  capsule + TPS + recovery + depot-departure burn, derived from the same
  Stage 3 rates Stage 4 charges for an Earth return. ~$25,400/kg from LEO,
  ~$27,300/kg from NRHO. Coming down is far cheaper than going up.

This is what puts an honest number on platinum at a depot. Its in-space
utility is 0.00, nobody in orbit wants platinum, but it is still platinum,
so it is priced by shipping it home rather than written off:

| Commodity | `earth_surface` | `leo` | `cislunar` | `lunar_surface` | `mars_surface` | Route |
|-----------|----------------|-------|------------|-----------------|----------------|-------|
| water | $0.001/kg | $2,352 | $7,033 | $28,733 | $46,374 | used in space |
| iron | $0.32/kg | $1,558 | $4,835 | $21,472 | $74,292 | used in space |
| nickel | $18.81/kg | $1,577 | $4,854 | $33,547 | $130,203 | used in space |
| platinum | $59,038/kg | $33,628 | $31,721 | $14,296 | $0 | shipped down |
| gold | $142,206/kg | $116,796 | $114,889 | $97,464 | $45,812 | shipped down |
| rhodium | $320,000/kg | $294,590 | $292,683 | $275,258 | $223,606 | shipped down |
| olivine | $0.05/kg | $433 | $1,603 | $1,241 | $3,520 | used in space |
| carbon | $0.20/kg | $810 | $2,683 | $19,079 | $3,514 | used in space |

The used-in-space rows are mineral_value 1.15.0 on spacecost `v0.9.0`; the
shipped-down rows were computed on `v0.4.0` from the 2026-09-09 terrestrial
quotes frozen under `campaign/stage2/`, and the LEO anchor does not reach them,
though the lunar ones carry `v0.9.0`'s ascent ($197/kg less downleg). Precious-metal rows carry a live spot quote, so they
move between runs; the rest are reference prices. Four things in that table
are worth reading twice:

- **Cislunar is worse than LEO for anything shipped down**: it is further from
  the customer, and the downleg is what sets the price. The downleg did not
  move in `v0.4.0`, which is why the three shipped-down rows only move with
  their quotes.
- **Platinum at Mars is exactly $0.** The $96,394/kg downleg from Mars exceeds
  every terrestrial price in the catalog, and there is no Martian buyer. That
  is the correct answer, not a bug.
- **Water at Mars captures a quarter of its freight, and at the Moon three
  fifths**: $46,374 of $186,306 against $28,733 of $48,226, because Mars has
  its own ground ice and the Moon's is in permanently shadowed craters.
- **Olivine is worth less on the Moon than at a cislunar depot** ($1,241 vs
  $1,603) even though the surface costs over six times as much to reach.
  Shipping rock to a body made of rock is not a business.

The `value_route` column records which fate was chosen for every row.

⚠️ The prices and the downleg are derived; the utility fractions are
**engineering judgements**. They are the softest assumption in the pipeline
and live in one table for exactly that reason.

#### Utility is per destination, because the alternative to importing is not always launching

The freight table above says what Earth would pay to put a kilogram somewhere.
It does **not** say whether anyone there wants it, and that answer is not a
function of distance. It is a function of what the destination can dig up for
itself.

- **LEO and cislunar** are empty space. Nothing is available locally at any
  price, so the only substitute for asteroid material is the same material
  launched from Earth. These carry the base profile unchanged, and every other
  destination is defined as a deviation from them.
- **The lunar surface** sits on silicate regolith carrying 5-15 wt% FeO plus
  mare ilmenite, and on polar water ice. Water drops to 0.60 (the ice is in
  permanently shadowed craters at ~40 K with no sunlight to work by), iron and
  Fe-Ni to 0.45, silicates to 0.03. Carbon is *not* discounted; solar-wind
  implantation leaves it at ~100 ppm, which is not a resource.
- **The Martian surface** has metres-thick mid-latitude ground ice, 1-3 wt%
  hydrated regolith measured by Curiosity's SAM, a 95.1% CO₂ atmosphere and a
  globally oxidised crust. Water drops to 0.25, carbon to 0.02, silicates to
  0.02, iron to 0.40.
- **Nickel, cobalt and copper are undiscounted everywhere.** No concentrated
  ore of any of them is known on either body, and they are what motors,
  batteries and wiring are made of.

⚠️  **Prices still rise with distance**, and reading this table as though they
do not is the standard mistake: Mars freight is 10.6 kg-in-LEO per kg delivered
and that still dominates. They simply no longer rise as *fast* as the freight
does, and the volatiles that once carried the Mars result rise least, water at
Mars is 2.7× its LEO price now against 11× before. **Every override runs
downward**, deliberately; why that constraint exists, and why a PGM settlement
market was considered and rejected, are in
[CLAUDE.md](CLAUDE.md#the-model-load-bearing-assumptions-do-not-fix).

**The import budget is split per commodity class.** One shared depot budget
meant a 20 t/yr Mars base absorbing 20 t of water *and* 20 t of platinum *and*
20 t of olivine. `_DEMAND_SHARE_BY_CLASS` partitions it, propellant 0.55,
structural 0.25, shielding 0.15, chemical 0.05, and `annual_market_kg` is
**routed**, so a commodity flown home saturates the terrestrial market rather
than a depot's import budget. Platinum at LEO was capped at the depot's
500 t/yr against the world's actual 180 t/yr.

### What it costs to get there

The destination is a different mission, not a different label:

| | `earth_surface` | `leo` | `cislunar` | `lunar_surface` | `mars_surface` |
|---|---|---|---|---|---|
| Delivery vehicle | re-entry capsule $150k/kg | berthing adapter $60k/kg | berthing adapter $60k/kg | lander $200k/kg | lander $200k/kg |
| Arrival ops | $15M recovery | $2M handover | $2M handover | $2M handover | $2M handover |
| Licensing | $2.5M launch + re-entry | $1.2M launch only | $1.2M launch only | $1.2M launch only | $1.2M launch only |
| Heat shield | yes | only if aerobraking | never | never (airless) | yes |

**Cislunar is cheaper to reach than LEO and worth more per kilogram.** This
reads as a bug and is not one: capturing into LEO must kill the entire
arrival hyperbola, while capturing into an NRHO depot only has to *bind* the
orbit, with the burn taking the Oberth benefit at low perigee. The advantage
widens as arrival energy falls: 5.6× at v_inf = 1 km/s, 2.7× at 5 km/s.

**Mars is a different journey, not a discounted Earth return.**
`_asteroid_to_mars_dv_km_s` runs the heliocentric transfer from the
asteroid's orbit to Mars' (1.524 AU), so the departure burn, arrival
v_infinity and capture are computed separately. That matters because plenty
of asteroids are genuinely more accessible from Mars than from Earth, and
approximating the leg would have hidden it entirely:

| Target | → Earth surface | → cislunar | → lunar surface | → Mars surface |
|--------|----------------|-----------|-----------------|----------------|
| Bennu-like (a = 1.13) | **0.75** | 1.96 | 4.56 | 5.14 |
| Mars-crosser (a = 1.46) | 0.78 | 2.33 | 4.93 | **3.28** |
| Main belt (a = 2.70) | 4.13 | 7.32 | 9.92 | **3.84** |

km/s of return Δv. A main-belt body is cheaper to deliver to Mars than to
Earth. The Moon is the awkward one, nearest in distance, but airless, so
every metre per second of arrival is propulsive.

Every output row carries `delivery_destination`, `delivery_arch` and
`value_basis`, so a CSV cannot be read without knowing which assumption
produced it.

## The propulsion and storage catalog

These tables live in [`spacecost`](https://github.com/loggger101/spacecost);
`modules/transportation.py` drives the package, and `verify_docs.py` check 3
holds every count below to the tables themselves.

### Propellants: 41 rows

Each carries specific impulse, blended density, $/kg, boil-off rate, a
low-thrust Δv penalty, a **storage class**, a derived
**tankage mass**, a maturity **status**, and whether the asteroid itself can
supply it.

| Status | Count | Rows |
|---|---|---|
| operational | 23 | kerolox, hydrolox, methalox, MMH/NTO, UDMH/NTO, Aerozine-50/NTO, hydrazine, green monoprop (ASCENT), HTP mono + bi, cold gas, solid APCP, xenon, krypton, argon, iodine, water electrothermal, water ion, hydrazine arcjet, electrospray, FEEP, PPT, solar sail |
| development | 8 | nuclear thermal, nuclear electric, solar-thermal H2, solar-thermal steam, VASIMR, MPD, metal/water (ALICE), cryogenic argon |
| concept | 9 | Li/F2/H2, CO/LOX, mass driver, Orion nuclear pulse, direct fusion drive, antimatter, magsail/e-sail, momentum tether, beamed laser-thermal |
| retired | 1 | mercury ion, banned under the Minamata Convention |

**Only the 23 operational rows are in the default search, and only 21 of those
can fly this mission profile.** Solid APCP is excluded because it cannot be
relit for a return burn years later; the solar sail because it is
propellantless and the rocket equation would report that it moves any payload
for free. Set `operational_propellants_only = False` to admit the rest, but
understand that a profit-maximising search will then fly every asteroid on
antimatter, which is why the gate exists.

Three of the additions matter more than the row count suggests:

- **Krypton** is, by unit count, the most-flown electric propellant in history,
  every Starlink v1.0 Hall thruster ran it, and it was absent. It is about
  13× cheaper than xenon at two-thirds the Isp ($794/kg since spacecost
  `v0.10.0`, the centre of a $300-$2,100 band; 33× at the unsourced $300
  before it), and it pays for that with a much
  worse tank (0.55 kg/L supercritical against xenon's 2.0, so 12.5% of its own
  mass in COPV against 1.9%).
- **Iodine** stores as a *solid* at ambient pressure, ρ 4.93 kg/L, so its
  reservoir is 0.2% of the propellant it holds, the best storage density of
  anything flying. ThrustMe flew it in 2020. It wins a large share of targets
  in the current model precisely because of that.
- **Water, electrothermally heated**, is the propellant the idea of a
  self-refuelling mining craft actually rests on: 1.00 kg of asteroid water
  per kg of propellant against hydrolox's 1.286, with no electrolyser and no
  cryogenic tank, at 190 s of Isp against 452. Honeybee's WINE demonstrated
  the full mine-boil-thrust loop in a vacuum chamber in 2018.

### Storage classes and tankage

Tank mass scales with the **volume** enclosed, not the propellant mass inside
it. `tank_kg_per_L` is derived per class, a flight-anchored multiple of
0.025 kg/L for the unpressurised classes, and `1.5·p/(PV/W)` off a 40 km COPV
performance factor for the pressurised ones.

The percentage column below is therefore a *consequence* of the named
propellant's density, not a property of the class: two propellants in the same
class pay different fractions if they store at different densities, which is
the whole point of putting volume in the model.

| Storage class | Named propellant | Tank as % of that propellant's mass |
|---|---|---|
| sublimating solid | iodine (4.93 kg/L) | 0.2% |
| supercritical gas, 10 MPa | xenon (2.0 kg/L) | 1.9% |
| storable liquid | MMH/NTO (1.16 kg/L) | 2.2% |
| benign liquid | water (1.0 kg/L) | 2.3% |
| mild cryogen | LOX (1.14 kg/L) | 2.5% |
| solid motor | APCP (1.80 kg/L) | 6.9%, Star 48B measures 6.2-6.5% (short and long nozzle; Northrop Grumman *Propulsion Products Catalog*, 2016) |
| deep cryogen, blended | hydrolox (0.361 kg/L) | 9.7%, Centaur III measures ~9.7% |
| supercritical gas, 18 MPa | krypton (0.55 kg/L) | 12.5% |
| supercritical gas, 30 MPa | cold gas N2 (0.25 kg/L) | 46% |
| deep cryogen, neat | LH2 for NTP (0.0708 kg/L) | 53% |

### Launch vehicles: 76 rows

48 operational and Earth-based (the default search), twelve in development
(Starship, New Glenn 9x4, Neutron, Terran R, Nova, Eclipse, Tianlong-3, Long
March 9 and 10, Soyuz-5, Epsilon S, Hyperbola-3), seven retired benchmarks, and
nine concepts: eight **non-rocket** ones plus SLS Block 1B, which never flew.
Since spacecost `v0.4.0` every row also says who can buy it (`availability`)
and carries a low/high band on its price and payload, with the headline at the
band's geometric centre.

⚠️  **Stage 4 flies every `operational` row**, and spacecost `v0.4.0`
took that from 17 to 48, most of the new ones Chinese and Russian vehicles a
Western buyer cannot book.

On the non-rocket rows, read `max_accel_g` before the price. SpinLaunch is
~10,000 g and a light-gas gun ~30,000 g: that passes propellant, water and
steel billets and destroys every mining rig, optic, reaction wheel and radio
in the catalog. They do not have a cost problem, they have a payload problem,
and this pipeline cannot represent a split manifest.

The lunar mass driver and lunar space elevator are excluded structurally
rather than by maturity, Stage 4 departs from Earth, and their payload
columns are annual throughput, so reading them would be a unit error. The
**lunar elevator** is the one worth not dismissing: unlike Earth's it needs no
new material, because the Moon's shallow gravity well and the Earth-Moon L1
balance point put the required specific strength inside what Zylon and M5
already deliver (Pearson 1979; Eubanks & Radley 2016).

### Storage systems: 20 rows

A new `storage_systems.csv`, covering four domains that had previously been
represented by a single column:

- **propellant**: the tankage constants above, MLI, vapour-cooled shields,
  and zero-boil-off cryocoolers (80 W of input per W lifted at 20 K, ~5 kg/W)
- **cargo**: bulk ore restraint, volatile containment, sintering, dust seals
- **energy**: Li-ion, regenerative fuel cells, flywheels, RTGs, Kilopower-class
  fission, and the eclipse fraction that should be sizing all of them
- **depot**: cryogenic depot boil-off, tanker flights per departure, transfer
  losses, ISRU propellant depots

Stage 4 reads the tankage figures, the RTG rows and the tanker count. It does
**not** read the volatile-containment, eclipse or cryocooler rows; those are
documented gaps, and all three currently run in the optimistic direction. See
[What the model does not capture](#what-the-model-does-not-capture).

## Beneficiation

**On by default since calc v1.17.0** (`CALC_CONFIG.use_beneficiation`).
Terrestrial mines ship concentrate, not ore; switched off, the pipeline flies
home run-of-mine regolith at bulk grade while the rig's own throughput capacity,
66× the rocket-equation payload limit, sits idle. Switched on, the rig digs
surplus feed, rejects the gangue, and loads concentrate.

⚠️  **Almost every table dated before 2026-08-11 is the `False` case.** Set it
back to reproduce them.

### The load is optimised, not specified

A mission is not sent for a named mineral; it brings back **the most
valuable load it can assemble from what the target actually contains**. With
a fixed mass budget and divisible, per-kilogram-priced phases, that is a
fractional knapsack, so greedy selection by $/kg is provably optimal: fill
the hold with the best phase available, then the next, until full or the feed
runs out (`optimal_payload_mix` over `asteroid_phase_table`).

Both honest bounds fall out of it automatically; you cannot load more of a
phase than the processed feed contained, and once the hold is pure best-phase
there is nothing better to add. On an M-type at 50% metal / 45% silicate with
0.90 recovery:

| Feed | Delivered | Load |
|------|-----------|------|
| 1.0× | $5,135/kg | hold 90% full, in-situ ratios |
| 2.0× | $7,081/kg | 90% metal |
| 2.2× | $7,567/kg | 100% metal, saturated |
| 5.0× | $7,567/kg | no further gain |

### How hard to concentrate is an economic decision

Grade saturates; costs do not. Every extra kilogram of feed still costs dig
time (compounding through ops and WACC), processing energy, and the solar
array mass to supply it, and that array mass comes out of the payload
budget. So the optimum is usually *strictly inside* the range, and
`evaluate_combo` searches for it rather than assuming it.

The search always includes **not concentrating at all** as a baseline, which
is not the same as a ratio of 1.0, since that would still pay the separation
recovery loss and the array mass for no grade gain, so beneficiation is an
option rather than an obligation and can never make a mission worse.

How often it declines varies enormously by destination, and the ordering is the
ISRU discount doing its job: **0.6%** of bodies at `mars_surface`, 1.1% at
`earth_surface`, 3.9% at `lunar_surface`, 11.6% at `leo` and **15.8% at
`cislunar`**; a depot with no local resources is where concentrate is worth
least relative to bulk. Where it does concentrate, the chosen ratio is a
single-digit multiple and never the 50× cap, the best cislunar mission
concentrates 3.5× at N = 1 and 3.9× as a programme. Median improvement from
beneficiating runs from +39.5% at `cislunar` to **+77.7%** at `earth_surface`.

**"Can never make a mission worse" is checked, not assumed**, and it is one of
the checks in `verify.py`: join the raw and beneficiated catalogs on
`designation` and assert the beneficiated cost/revenue is never higher, row by
row. On the full catalog it holds across **all twenty-eight cells with zero
exceptions**, and the worst case is exactly 1.000000, which is beneficiation
declining and falling back on the baseline. **That is the signature to expect:
never worse, and equal wherever it declines.** A maximum above 1.0 means the
search is optimising something other than what gets reported.

Costs charged, all of which the search trades against:

- **Time.** Dig time is charged on the *feed*, not the product.
- **Energy and mass.** Stage 3's 200 Wh/kg excavation and 500 Wh/kg
  beneficiation rates over the stay time give a power draw; Stage 3's
  60 W/kg-at-1-AU power-system row, scaled 1/r² by the target's semi-major
  axis, turns that into array mass; the array flies in the same rocket
  equation as everything else. Payload → feed → power → mass → payload is a
  real circular dependency, solved by fixed-point iteration.

That 1/r² term punishes distant targets hard, and the ratios between the rows
are the point rather than the absolute masses (cislunar delivery, measured on a
1,959-body pre-v1.0.9 run):

| Semi-major axis | W/kg at target | Mean array mass |
|-----------------|---------------|-----------------|
| < 1.2 AU | 51.5 | 4 kg |
| 1.8-2.5 AU | 11.4 | 41 kg |
| > 3.2 AU | 4.7 | 226 kg |

## Programme scale

`nre_amortization_missions` is programme size N, and since calc v1.15.0 it is
**searched rather than set**: `optimise_programme_scale` resolves fleet size
and campaigns-per-ship per asteroid, jointly with every other architecture
axis, and N follows as their product. It is **on by default** since v1.17.0.

That costs **2.0× to 3.1× runtime** rather than one full run per N, because
**N enters nothing in the mass cascade**; it appears in the cost model, the saturation
block and the reliability block, and in none of the rocket equation, the power
fixed point, the payload knapsack or the concentration sweep. The expensive
half of the mission is solved once per candidate and the whole ladder is priced
off the result.

**Scale is real, sublinear, and bounded.** Five models pull against each other,
and the last two are what stop it running away. Under the calc v1.22.0 defaults
three of the five are off or inert, which is marked per bullet; both of the two
that bound it are live:

- **NRE amortises** across the programme, and the learning curve (Wright's law,
  0.85) falls on the per-mission articles. ⚠️  **The curve is OFF by default
  since v1.22.0** (`model_learning_curve`); the NRE amortisation is not and
  never was a flag. Turning the curve on is worth 34.3% on the searched
  cislunar sample cell and exactly nothing at N = 1.
- **Mining reliability grows** with programme size, Duane/AMSAA, 0.850 at
  N = 1 to 0.943 at N = 100, reported as the fleet average rather than the
  terminal value. ⚠️  **OFF by default since v1.22.0** (`model_reliability`),
  which takes the growth term with it.
- **The rig wears out**, on whichever of its two bounds binds first: a 15-year
  calendar life, or five duty cycles. Past that, mission N+1 buys a new rig.
  ✅  Live, and one of the two that bound the ladder.
- **The market saturates**, against the programme's **concurrent** output,
  which is what makes the optimum programme size **interior** rather than "as
  many as you can pay for". ✅  Live, and the other one. Since v1.22.0 the
  surplus past a ceiling sells at half price rather than being abandoned,
  which softens the bound without removing it: the marginal kilogram past a
  ceiling is still worth strictly less than the one before it.
- **The calendar is charged.** One rig digs one hole at a time, so campaigns on
  a ship are strictly sequential, and the lines bought once at t = 0; bus NRE,
  autonomy NRE, the rig, are carried across decades of programme span.
  ⚠️  **INERT since v1.22.0.** The flag is still True, but the charge is
  time-value and `apply_wacc_compounding` is off, so the multipliers are
  exactly 1.0. Measured: it was worth a median **1.457x** on the amortised
  lines of the searched cislunar sample cell, and the share of rows choosing
  **fewer campaigns than the rig can fly fell from 29.2% to 1.5%** with it
  inert -- this was the only term giving W a reason to be less than the rig's
  trip life.

Measured on the full catalog at cislunar, the search improves the raw cell
**15.3937× → 9.5435×** and the beneficiated cell **14.1071× → 6.6622×**, on a
median fleet of **3 ships** raw and 6 beneficiated, a median N of **12** and
**30**, and a median programme span of 11.4 years raw / 13.8 beneficiated.
Every destination is in [Results](README.md#results).

⚠️  **The searched and unsearched columns answer different questions and are
not comparable.** One is the best single mission to a rock, the other the best
programme built around it. The improvement is a change of question, not a
saving, and it does not reach viability either: the best programme in the
model still loses about seven dollars for every one it earns.

⚠️  **Rows piling up against `max_fleet_ships` are a diagnostic, not a
result.** Their payloads cannot reach a ceiling that binds, so the objective is
monotone in N and the ladder's top rung is simply where the loop stopped. At
calc 1.21.2 that was **9.99% raw and 17.77% beneficiated** at cislunar and
**100.000% at `earth_surface`**, which is why that destination's searched cells
are not optima.

The historical curves against a *forced* programme size, and the two
corrections that reshaped them, are in
[The programme-scale curves](versions.md#the-programme-scale-curves).

## What the model charges for

Each model below was a correction when it landed, and its flag exists to
isolate an effect, not to be left off. **When each one arrived is in
[`versions.md`](versions.md); what it charges for is here.**

`use_beneficiation` and `optimise_programme_scale` are not on this list: they
are questions ("ship concentrate or ore?", "how big a programme?"), not
subsidies withdrawn. The test is **"was the model getting something for free
before?"** Mission reliability, the learning curve and the cost of capital pass
it, and are **off by default since calc v1.22.0** for the reason
[insurance](#what-the-model-deliberately-does-not-charge-for) is: they price
something other than the physics and hardware of moving a kilogram. Each says
so in its own entry. One entry, orbital refuelling, is *withdrawn* rather than
charged.

### Gaps in what the model charged for

Time, rate, wear and the market: things that were happening to a real mission
and were not on any invoice.

**Low-thrust trip time** (`model_low_thrust_time`). Electric propulsion used to
pay a Δv penalty and nothing else; it flew its burns instantly on power it
never carried. A thruster's power fixes its thrust, so burning `m_prop` takes
`m_prop·(Isp·g0)² / (2·η·P)`: **high specific impulse buys propellant mass at a
quadratic cost in time-or-power.** The EP stage is sized to finish inside
`ep_target_thrust_yr` (3.0), and the array plus thruster/PPU mass that demands
goes into the same rocket equation as everything else. A typical electric
winner hauls ~4,900 kg of power system against a 2,000 kg mining rig.

✅  Validated against **Dawn**, the only mission to have flown this regime: at
its 2.2-3.0 AU operating distance the formula gives 5.0-9.3 years of thrusting
against ~5.9 actually flown. The 1/r² term does the work; evaluated at Dawn's
1 AU array rating the same sum gives 1.0 year and is nonsense. **If this check
ever passes that easily, the 1/r² term has been lost.**

**Launch windows** (`model_launch_windows`). Departure needs phasing and
alignments recur at the synodic period, so the expected wait after mining is
half a period. This punishes **NEAs hardest**, which is the opposite of the Δv
story: a body whose period nearly matches Earth's drifts in phase very slowly.

| Semi-major axis | Period | Synodic with Earth |
|---|---|---|
| 1.05 AU | 1.08 yr | **10.0 yr** |
| 1.13 AU | 1.20 yr | 6.0 yr |
| 2.70 AU | 4.44 yr | 1.3 yr |

⚠️  Accessibility in Δv and accessibility in *time* pull in opposite
directions, and only one of them was modelled before. **Do not assume a
low-Δv target is a fast one.**

**Bound-water liberation** (`model_water_liberation`). C/B/D-type "ice" is
water locked into phyllosilicates; it is baked out at ~700 K, not scooped.
Stage 3 charges **2,500 Wh/kg**, derived from heating the rock through
dehydroxylation plus the enthalpy of dehydration plus vaporisation, and
matching the 1-3 kWh/kg in the ISRU literature. It had been extracted free and
sold at full launch-cost-avoided.

**Making ISRU propellant** (`model_isru_processing`, calc v1.32.0). Liberating
the water was the only processing an ISRU mission paid for in energy; splitting
it into hydrogen and oxygen and liquefying both was a flat, unsourced $50/kg
with no watt and no kilogram behind it. Stage 3 now states it per propellant
row: **hydrolox 15,200 Wh per kg made**, the low end of a 15.2-26.3 kWh/kg band
built from DOE's PEM electrolysis system figure (55 kWh/kg H2) and a NASA Glenn
20 K liquefier study (Johnson, AIAA ASCEND 2023), cross-checked by a whole lunar
water-to-hydrolox plant at 21.3 kWh/kg (Kleinhenz & Paz 2021). That goes through
the array. The plant that does it rides with the rig and is costed as the rig
is, at **7.28 kg of propellant a year per kg of plant**, which is that lunar
study's electrolysis-and-liquefaction half (tanks included, so an upper bound on
mass). Water burnt as it comes (resistojet, water ion, steam) states 0 and pays
nothing, and the flat $/kg is retired. ⚠️  **It moves almost nothing, and that
is a finding about the population, not about the term.** Hydrolox ISRU won 17%
of the calc 1.26.0 default cell only because electric missions were being
refused by the sizing-loop cliffs calc 1.27.0-1.29.0 removed; with those fixes
reverted on a sample the share returns, and this charge takes it to zero and
makes those rows a median 77% worse. See
[master v1.55.0](versions.md#master-v1550--calc-v1320--transportation-v1230).

**Learning curve** (`model_learning_curve`, **off** since calc v1.22.0;
`learning_curve_rate` 0.85). Wright's law on the per-mission articles,
capsule/lander and power system. The amortised mining rig is **excluded**,
because it is one shared unit rather than N built, and a curve on it
double-counts. Exactly 1.0 at `nre_amortization_missions = 1`, so a
single-mission run is untouched either way; 0.44 at N = 100.

⚠️  **It is off because it prices a factory, not a mission.** Wright's law is
fitted to programmes that built dozens to hundreds of articles; the ladder here
routinely proposes N in the tens, and crediting them with serial-production
learning assumes an industrial base the run never modelled. It also runs in the
generous direction, which is the direction this model refuses everywhere else.
Set `model_learning_curve` True to restore it.

**The market model** (`market_model`, `"capacity_cap"` since calc v1.21.0).
The only term in Stage 4 that pushes back on programme size: N improves five
levers at once (NRE/N, autonomy NRE/N, the learning curve, the rig's share and
reliability growth) and this is the sixth. Without something here,
`nre_amortization_missions` has no stopping point and the objective is monotone
in N, so the search reports where the ladder stopped rather than an optimum.

Four models, and the choice is what the run is claiming about prices:

| `market_model` | price behaviour | what bounds a programme |
|---|---|---|
| **`capacity_cap`** | constant at any volume | a hard kg/yr ceiling per commodity |
| `single_mission` | constant | N pinned at 1, no search, no ceiling |
| `elasticity` | `(1 + Q/Q_market)^(-1/ε)` | the demand curve |
| `unbounded` | constant | nothing; a **diagnostic**, and the run says so |

**`capacity_cap`** holds the price flat and clips the quantity instead.
Everything inside a commodity's ceiling sells at the full price Stage 2 quotes.
How much one delivery may sell is how long the destination has
been accumulating since the last one: `cap × cadence / F` in steady state, and
`cap × mission_duration` for the first delivery, which arrives at a market that
has been importing from Earth for the whole outbound-and-back trip. Averaged
over a programme of N that is
`cap × [duration + (N−1) × cadence/F] / N`, which is exactly `cap × duration`
at N = 1 and converges on the steady state as N grows.

The ceilings go **into the payload knapsack**, which is the part that makes the
model behave: a load that caps out on iron keeps walking down the price order
and spends the freed hold space on whatever is next, rather than flying the
excess unsold. Per-item upper bounds turn an unbounded fractional knapsack into
a bounded one, which greedy still solves exactly, so this is a constraint
*inside* the optimiser rather than a clamp on top of it.

**What happens past a ceiling is `sell_surplus_at_discount`, and since calc
v1.22.0 the answer is that it SELLS.** A destination that absorbs 100 t/yr of
water at the quoted price does not become unable to take the 101st tonne; it
takes it at a price that clears, which is the entire content of a supply curve
sloping down. The surplus is sold at `surplus_price_fraction` of full price,
**0.5** by default. Set the flag `False` for v1.21.0's hard wall, where the
surplus earns nothing and is reported as unsold; that is what the whole 2026-09
campaign was measured on.

⚠️  **This does NOT unbound the programme**, which is the objection to check
first, and the reason it does not is one sentence: the marginal kilogram past a
ceiling is worth strictly less than the one before it. A bigger fleet delivers
more often, so each delivery gets a shorter accumulation window and a larger
share of the load falls into the discounted tier, so another ship still adds
its full cost against a falling marginal revenue, and the objective still turns
over on its own. A wall is the `surplus_price_fraction = 0` end of the same
model, and `1.0` is the only setting that would genuinely remove the ceiling.

**In a concentrated load the discount changes what the ship carries, not just
what it is paid.** Each phase now appears in the knapsack twice, at full price
up to its ceiling and at the discounted price above it, and the greedy walk
interleaves them; a rich phase's half-price surplus can outrank a poor phase's
full-price allowance, and where it does, the optimal load carries it instead.
That is a different load from the one a wall chooses, not merely a differently
priced one. Raw ore cannot be reshaped at all, so there the surplus is simply
carried and sold at the discount.

Three output columns report it, kept apart because a price multiplier, a
discounted sale and a refused one are three different claims:
`market_clearing_fraction` is the share of the assembled load's gross value
that cleared, `surplus_payload_kg` is mass sold past a ceiling at the discount,
and `unsold_payload_kg` is mass that earned nothing. **The last two are
exclusive** and `verify.py` check 7 asserts it: under the v1.22.0 default the
mass lands in `surplus_payload_kg` and `unsold_payload_kg` is 0.0, and turning
the flag off swaps them over. ⚠️  The assertion carries a milligram floor,
because on the beneficiated path `unsold` is a difference of two sums that are
mathematically equal, and it can land one ULP off zero -- measured at
3.6e-12 kg against a 24-tonne payload.

⚠️  **The ceilings bind at the fleet sizes the model actually chooses.**
Cislunar's whole import budget is 100 t/yr and water's propellant share is
55 t/yr, against a median raw cadence of 1.384 yr and a median searched fleet
of **3**.

✅  **They were recalibrated in calc v1.21.1 and the LEVELS did not move**, on
the argument that they never were curve parameters: every row in
`IN_SPACE_ANNUAL_DEMAND_KG` is documented as an absorption budget, `geo` being
613 active geostationary satellites (McDowell's GCAT, Jan 2026; 550 until
mineral_value 1.13.0) at ~73 kg/yr of station-keeping propellant and
`mars_surface` being "a base that imports 20 t/yr". A kilogram delivered inside
a consumption budget genuinely displaces a launched kilogram, so it earns full
launch-cost-avoided; the curve, which had the price already quartered at exactly
the quantity the base needs, was the term using the number wrongly. What v1.21.1
did change is that the composition residual now has a ceiling at all. See
[calc v1.21.1](versions.md#calc-v1211) for the derivation, and for the
quarter-ceiling alternative measured and declined.

⚠️  **`earth_surface` is unbounded whichever model you pick.** Its ceilings are
terrestrial production, 10¹² to 10¹⁵ kg/yr, so nothing binds and the cell stays
monotone in N exactly as it was under `elasticity`. A downmass or recovery
ceiling would fix that and does not exist yet.

**`elasticity`** is the v1.14.0 term, unchanged and still available.
`P/P0 = (1 + Q/Q_market)^(−1/ε)` against Stage 2's `annual_market_kg`, with
ε = 0.5 (precious-metal demand is inelastic). Returning 180 t/yr of platinum
doubles world supply and quarters the price; delivering 6.6 t/yr of water to a
Mars base that can absorb 11 t/yr cuts the price to 0.39. Without it,
`nre_amortization_missions` had no stopping point: you could amortise
development across a fleet whose output would have destroyed the price
justifying it.

⚠️  **Both models read the same ceilings**, and differ only in what they do
when one is reached: `elasticity` bends the price, `capacity_cap` stops the
sale. World production is USGS; the in-space absorption ceilings (LEO 500 t/yr,
cislunar 100 t, lunar surface 50 t, Mars 20 t) are **judgement, not
measurement**, since no such market exists. They are destination *totals* split
across commodity classes rather than a figure each commodity gets to itself, so
the Mars water ceiling is 0.55 × 20 t = 11 t/yr, and the ceiling follows the
**value route**, so anything flown home is bounded by terrestrial production.

⚠️  **A ceiling belongs to a market, not to a phase.** `silicates` and the
composition residual sell into one market (the residual is priced at the
silicates quote because that is what it is), so they draw down one pooled
allowance, consumed as it is spent. Until calc v1.21.2 each looked its ceiling
up per phase and a load could place twice the market; see
[calc v1.21.2](versions.md#calc-v1212).

**Rig service life and terminal value** (`model_rig_service_life`). The rig was
amortised across `nre_amortization_missions` with no upper bound, so a
programme could spread one machine across 100 missions of two years each: 200
years of duty from something chewing rock. A 15-year life now *caps* the
amortisation, and the cap makes long-stay programmes markedly **more**
expensive, not less:

| Stay per mission | Missions one rig can serve | Charge vs. old flat ÷100 |
|---|---|---|
| 0.25 yr | 60 | 1.7× |
| 1.0 yr | 15 | 6.7× |
| 2.0 yr | 7 | **13.8×** |

Life remaining when the programme ends is credited at the salvage fraction
(0.50), but only when `nre_amortization_missions > 1`: a rig parked at an
asteroid nobody revisits is stranded, not an asset.

**Mission reliability** (`model_reliability`, **off** since calc v1.22.0).
Revenue was certain. With this on, expected revenue is
`p_launch(0.97) × exp(−T/MTBF)(30 yr) × p_mining(0.85)`, about 0.70 for a
five-year mission.

⚠️  **Off by default because two of those three numbers are assumptions, not
measurements.** Launch reliability is an observed rate over hundreds of
flights; the cruise term is an exponential on an assumed MTBF, and `p_mining`
is a judgement about a machine nobody has built. Multiplying the ANSWER by them
puts a ~30% discount into every headline ratio while leaving it exactly as
solid as the guess it came from. A default run now answers **what this costs if
it works**, which is the same framing that makes the two surface delivery
prices lower bounds; set `model_reliability` True for the risk-weighted
question. ⚠️  **Costs are still charged in full**, which is
both conservative and correct: you spend the money whether or not it works.
Insurance never entered this term, it replaced hardware on failure rather than
revenue, so calc v1.20.0 turning both premiums off changes nothing here.

`p_mining` is counted from the full flight record of regolith-contact
mechanisms, not from the failures alone:

| | Missions |
|---|---|
| **Succeeded** (10) | Apollo 15-17 drills/scoops; Luna 16/20/24; Stardust aerogel; Phoenix arm; Curiosity drill (feed mechanism failed 2016, recovered by feed-extended drilling); Hayabusa2 sampler + SCI impactor; OSIRIS-REx TAGSAM (121.6 g against a 60 g requirement); Perseverance corer; Chang'e 5 and 6 |
| **Partial** (1) | Hayabusa; projectile never fired, but contact dust was still collected and returned |
| **Failed** (2) | Philae's harpoon pyrotechnics; InSight's HP³ mole, which could not get purchase in Martian regolith |

That is **11/13 = 0.85** counting Hayabusa as the success it ultimately was, or
0.77 counting it as a loss. The canonical roster, with per-mission detail, is
the note in `modules/transportation.py`.

The honest caveat: none of these is *sustained* mining. They are one-shot
collections of grams to kilograms, not a rig moving 200 kg/day for years. 0.85
is the demonstrated **mechanism** rate; sustained-operation exposure is carried
by the spacecraft MTBF term rather than double-counted here.

**Reliability growth** (`model_reliability_growth`, inert while
`model_reliability` is off, which is the default since calc v1.22.0).
`p_mining` used to sit at
its first-of-kind value however many missions a programme flew, the one place
the model was *pessimistic*. Duane/AMSAA: failure probability falls as a power
law in cumulative production, `q(n) = q_first · n^(−α)` with α = 0.30, near
the bottom of the historical growth rates in MIL-HDBK-189C's Table II
(0.27-0.64 for one-shot systems, 0.23-0.53 for time-based ones), which suits
hardware that flies once every few years with no test fleet. Capped at a 0.95 mature ceiling.

| Programme size | `p_mining` (fleet average) |
|---|---|
| 1 | 0.850 |
| 10 | 0.902 |
| 100 | 0.943 |

⚠️  Reported as the **mean over missions 1..N, not the terminal value**. NRE and
the rig amortise across the whole programme, so per-mission expected revenue
has to use the programme average; quoting the last mission's reliability would
credit every mission with heritage only the last one has. Exactly 0.850 at
N = 1. ⚠️  Launch and cruise reliability deliberately do **not** grow: launch
vehicles are already mature, and MTBF is a duration exposure rather than a
heritage question. Do not "complete" the model by adding growth to them.

**Cryogenic boil-off** (`model_propellant_boiloff`). Return propellant sits in
the tank from launch until the departure burn, years rather than hours. Loading
per kg actually burned:

| Hold | hydrolox (0.05%/day) | methalox (0.012%) | storable (0%) |
|---|---|---|---|
| 1 yr | 1.20× | 1.04× | 1.00× |
| 5 yr | **2.49×** | 1.25× | 1.00× |
| 8 yr | 4.31× | 1.42× | 1.00× |

Folded into an effective return Δv, which leaves the closed-form cascade exact:
since `m_return_prop` scales with `(R−1)`, inflating that term by `k` is
`R_eff = 1 + (R−1)k`. ISRU return propellant is exempt; it is manufactured at
the asteroid on departure. ⚠️  **That exemption is optimistic and not yet
charged**: the propellant is made over the whole stay (a median 1.27 yr on the
ISRU rows measured for calc v1.32.0), so the first hydrogen made is held that
long and either boils or needs a 20 K cryocooler running the whole time. It is
inert today, because charged hydrolox ISRU wins no sampled row, and it is an
open item rather than a decision.

**In-space manufacturing** (Stage 2). Raw Fe-Ni is not a pressure vessel, and
the gap used to hide inside the 0.70 utility factor: the refinery was assumed
into existence and never costed. Now explicit, ~$230/kg for metals:

- **Energy** at **$6.08/kWh**, the capital cost of a kilowatt-hour in deep
  space ($800/W-EOL over a 15-year life), roughly 100× terrestrial industrial
  power, which is why in-space processing is not obviously free. Metals take
  5 kWh/kg; terrestrial electric-arc steelmaking is 4-5 kWh/kg and there is no
  carbothermic shortcut in vacuum.
- **Plant** at **$200/kg refined**: $300k/kg of deep-space hardware at
  100 kg/yr throughput per kg of plant over 15 years.

Deducted from the *used in space* route only; material shipped down is refined
on Earth. ⚠️  **This deduction is the `model_refinery = False` path.** By
default since calc v1.25.0 Stage 4 values every phase before it and flies the
refinery instead, its energy through the array and its plant with the rig;
see [What the rock is made of](#what-the-rock-is-made-of).

### Mass flown and never billed, or billed and never flown

**The defect class to look for in this codebase first.** The mass cascade and
the cost cascade are written in different places, and nothing checks that every
kilogram in one has a price in the other. The one-line assertion that catches
the whole family is
`hardware_total_kg == mining_hardware_kg + power_system_kg + ep_system_kg`, and
one release introduced three fresh instances while fixing three older ones.

**The electric propulsion stage.** The EP array and thruster were sized, pushed
through the rocket equation, and never passed to the cost model, so a 309 kW,
14-tonne electric stage was free and electric propulsion won missions on
hardware nobody had to buy. Priced in two parts, because they cost wildly
different amounts per kilogram: the **array** off the existing $800/W-EOL
power-system row, the **thruster and PPU** off a Stage-3 row at **$1.5M/kW**,
anchored on a NEXT-C flight string (7 kW, ~47 kg, in the $10-15M class) with a
$0.5-3M/kW range because high-power Hall systems buy down from there. ⚠️
Flagged soft: this pipeline sizes some missions at 300 kW, six times the
largest article ever built.

**Return-vehicle structure** (`return_structure_frac_of_payload`, 0.15). The
return vehicle's dry mass was a flat 500 kg however much it carried, so the
cascade loaded 125 tonnes of ore into a half-tonne can: **250:1
payload-to-structure**, against 0.4:1 (Cygnus PCM) to 2:1 (Dragon) for real
cargo spacecraft. Nothing caught it because the only other bound on returned
mass was the launch vehicle's fairing *volume*, which dense ore never fills.
The 500 kg is now a floor and 15% of the payload is added for tankage, primary
structure and cargo restraint. The closed-form solver carries the term exactly:
writing `g = s(1+f) − 1`, it reduces to the old expression when `f = 0`.

**Propellant tankage** (`model_tank_mass`). `density_kg_per_L` had been
computed for four releases and read by nothing. A tank's mass scales with the
**volume** it encloses, not with the propellant mass inside it, so leaving it
out was a straight subsidy to whichever propellant had the lowest density,
which is the same propellant that has the highest specific impulse: the error
compounded rather than cancelling. LH2 is 0.0708 kg/L against kerolox at 1.015,
fourteen times the tank per kilogram burnt.

`tank_kg_per_L` is derived per storage class and anchored on flight articles
rather than asserted. As a fraction of the propellant it holds: **iodine 0.2%**
(solid at ambient pressure), xenon 1.9%, kerolox 2.7%, an APCP motor case 6.9%
against Star 48B's measured 6.2-6.5%, hydrolox 9.7% against Centaur III's measured
~9.7%, krypton 12.5%, cold gas 46%, and bare LH2 **53%**, which is what a
nuclear-thermal stage has to earn its 900 s against.

The closed-form solver generalises with two scalars rather than going
iterative: `k = 1/(1 − t(R_ret − 1))` on the return leg, where the tank flies
home inside the cargo's post-burn mass, and `k_out` on the outbound leg, where
it is staged at the asteroid. Both are exactly 1 at `t = 0`. 🚨  `t(R − 1) ≥ 1`
means **the tank cannot close**, and that is infeasible rather than expensive.

**Thruster scalability** (`thruster_kg_per_n`). The largest single correction
in the project, and the clearest statement of the defect class: **launch was
modelled as an integrated vehicle with a payload it can actually lift, while
in-space propulsion was modelled as a bare specific impulse.** One side had a
capacity limit and the other did not, so Stage 4 sized the electric stage on
power alone and buying enough kilowatts turned any row in the propellant table
into a cargo tug: 31.8% of cislunar winners were pulsed plasma thrusters and
24.3% electrospray, devices whose largest flown units make *micronewtons*,
being asked for ~7-10 N.

The gate is **mass, not a threshold**: thrust is momentum flux, `T = ṁ·ve`,
which owes nothing to efficiency, so Stage 3 carries kg/N per technology and a
device making µN/kg reports thousands of tonnes of thruster and dies in the
rocket equation on its own. The evaluable catalog halved and chemical
propulsion came back. ⚠️  Because it is a penalty rather than a cutoff, the
right test is not whether such devices *survive* but whether one ever **wins**,
and in both the 2026-08 and 2026-09 campaigns one did, at `mars_surface`.
That is the mechanism working, not leaking.

**Argon storage** (Stage 3). Not a flag but a reference-table fix, and the one
that moves numbers. The row carried liquid-argon density, which exists only at
87.3 K, *together with* a boil-off of zero: its own two comments read "liquid
NBP (cryogenic storage)" and "stored supercritical at ambient temperature",
three lines apart. Argon was winning ~25% of missions on that combination.
Split into the two articles that actually exist; see
[calc v1.12.0](versions.md#calc-v1120--transportation-v1100).

**Cargo-water power plant** (`model_water_liberation`). The liberation energy
for water sold as cargo had sized an array that the cost model paid for and the
rocket equation never carried. The flag is unchanged; what changed is that the
array is now flown.

**Launch acceleration** (`max_payload_accel_g`, 15 g). Every real launcher in
Stage 3 is 6 g or less; SpinLaunch is 10,000 g, a light-gas gun 30,000,
StarTram 30. The column existed to disqualify them and nothing read it, so only
their `concept` status was keeping them out.

**Propellant tank fabrication.** $6,000/kg, Centaur-derived (~1,880 kg of
structure, a ~$30M stage less ~$20M of RL10). Tank mass had been flown and
launch-charged for a release and never built. It is 0.004-0.6% of mission cost,
median 0.012%, and it is kept precisely because it is small: **these are only
ever found by checking every term rather than the big ones.**

**Orbital refuelling** (`charge_tanker_flights`, **gated off**). Starship's
escape payload (27 t) *exceeds* its GTO payload (21 t). No propulsion system
can do that; the escape figure is for a vehicle topped up in orbit first.
Charging for it was briefly implemented catalog-wide, at **$1.08B on top of a
$90M launch**, and that is the **withdrawn** entry: Stage 4 has no
escape-direct scenario, so the charge was real but billed against a scenario
this module does not have. Gated behind `escape_direct_launch`, which nothing
sets, rather than deleted, so the day this module gains direct injection the
charge becomes correct and the column is already wired.

### Figures that were written down and never wired in

Both of these had sat in a Stage 3 reference table, correctly derived and
correctly cited, behind a note saying they were not modelled in Stage 4, and
Stage 4 does not load that table. They were quoted as known limitations for two
releases and nothing moved. **Writing a gap down had been mistaken for closing
it. A reference table nobody reads is not a model.**

**Volatile cargo containment** (`model_volatile_containment`). The pipeline
priced water at every in-space destination, charged the energy to bake it out
of phyllosilicate and flew the array that does the baking, and charged
**nothing** to stop it subliming across a four-year cruise. Not a rounding
term: the best cislunar missions are **~88% water by mass**, so the commodity
carrying the entire result was the one flying free. A sealed shaded hold at
0.05 kg/kg, *incremental* to the 0.15 ore restraint; the hopper holds the
cargo, the seal and the shade keep the volatile fraction from leaving. Charged
on water only, since carbon and organics are refractory at these temperatures
and ride in the hopper like rock.

**Eclipse and night-side power** (`model_eclipse_power`). Processing power is a
*continuous average* draw and the plant was sized straight off it, which is
only right if the rig is never in shadow. It stands on a rotating body. Two
terms: an array oversize of `[(1−f) + f/η]/(1−f)` = **2.11×**, which is a
sizing factor no W/kg figure could ever have absorbed; and storage sized on the
**body's own rotation period**, which finally makes `rotation_period_h`,
carried by Stage 1 from the start and read by nothing, a quantity the model
uses, so a slow rotator is genuinely a worse place to mine. Together they cost
**4.7×** at 1 AU and the median 10.2 h rotation, not the "roughly doubles" the
storage table itself estimated.

### Bounds that only bite at programme scale

⚠️  **These two are the only entries on this list that are inert at N = 1**, so
no single-mission figure moves for either, which also means neither can be
checked by re-running a headline.

**The rig's duty cycles** (`model_rig_trip_limit`). `life` is "Mining rig
service life" = **15 YEARS**, a figure whose own Stage 3 notes describe
corrosion, thermal cycling and radiation dose. Dividing it by the stay gave a
mission count, and **nothing anywhere bounded duty cycles**, so at a short stay
one rig was good for twelve consecutive digs on the strength of a number that
only ever promised it would not have rusted meanwhile. A rig parked between
campaigns ages slowly; one cutting rock does not. Stage 3 adds a maximum of
**5 trips** and the min of the two bounds is taken, so long stays stay
calendar-limited and short ones are cycle-limited, which is the correct way
round and was the entire gap.

**Programme calendar time** (`model_programme_calendar`). One rig digs one hole
at a time, so campaigns on a ship are strictly sequential, and the cost model
compounded each mission's up-front costs over that *mission's* own duration and
stopped, which for a programme assumes every mission happens at once. The lines
carried free are the **amortised** ones, bus NRE, autonomy NRE and the rig,
because those alone are bought once at t = 0 and divided across missions that
sell years apart. A mission's own articles are unaffected: shift a whole cash
flow later and its cost/revenue ratio does not move.

⚠️  Salvage gets the **reciprocal** series, because it is collected at the
*end*; compounding a refund forward alongside the cost it is netted against
would pay a bonus for taking longer to collect it. Both multipliers are exactly
1.0 at one campaign per ship, which is what makes the term inert at N = 1.

🚨  **AND IT IS INERT AT EVERY N AS OF CALC v1.22.0, BECAUSE IT IS TIME-VALUE
AND THE COST OF CAPITAL IS NOW OFF.** Both multipliers are exactly 1.0 at
`wacc = 0` by construction, so this flag charges nothing until
`apply_wacc_compounding` is turned back on. It is left ON rather than flipped,
because the flag means "charge the calendar the programme spans" and that is
still what the model should do the moment there is a rate to charge it at; the
run banner says which of the two states it is in rather than leaving a reader
to derive it.

## What the model deliberately does not charge for

The list above is what the model was getting **free** and now pays for. This is
the shorter list of the opposite kind: costs that are real, that a real
programme pays, and that this pipeline does not price because they are not the
question it is asking.

**The test for this section is that the charge would be RIGHT and is still not
asked for.** That is what separates it from the withdrawn orbital-refuelling
charge, which is *wrong* for this module and gated rather than declined, and
from the corrections above, which the model was getting free.

**The cost of capital** (`apply_wacc_compounding`, default `False` since calc
v1.22.0). Up-front costs were compounded at Module 3's **10%** WACC over the
mission duration, bucketed so an end-of-mission line is not inflated by the
whole span. A discount rate is a statement about *whose money this is* -- an
agency's, a sovereign fund's, a venture portfolio's -- and the model does not
know and should not guess. It is not a rounding term either: an up-front line
compounded over a 5-to-12-year mission is worth roughly **twice** its face
value, which is the same 2.12-2.38x multiplier measured on the insurance
premium, applied to every up-front line in the cascade.

⚠️  **It takes the programme calendar charge with it.** `model_programme_calendar`
is time-value, and `programme_calendar_multipliers` returns exactly (1.0, 1.0)
at a zero rate, so that term is inert until the rate comes back. Duration still
binds through the dig, the launch windows, the rig's life and
`max_mission_duration_yr`, all of which are physical rather than financial.

**Mission reliability** (`model_reliability`, default `False` since calc
v1.22.0). See [its own section above](#gaps-in-what-the-model-charged-for) for
what it charges and where the 0.85 comes from. It is here because of what it
multiplies: `P` is a product of one measurement and two judgements, and
applying it to expected revenue puts both judgements into every headline ratio
while leaving the ratio exactly as reliable as they are. A default run answers
**what this costs if it works**; that is a lower bound in the same sense the two
surface delivery prices are.

**The learning curve** (`model_learning_curve`, default `False` since calc
v1.22.0). Wright's law at 85%. It prices a factory, and this pipeline does not
have one: the curve is fitted to programmes that built dozens to hundreds of
articles, and crediting a ten-mission programme with that learning assumes an
industrial base the run never modelled. Exactly inert at N = 1 either way, so
no single-mission figure in this project moves for it.

**Insurance** (`charge_insurance`, default `False` since calc v1.20.0). Module 3
prices two premiums, a **$1.5M** third-party liability flat and launch insurance
at **10%** of (launch + spacecraft book value), and until v1.20.0 every mission
was charged both. They are not wrong. They are out of scope: everything else in
the cascade is a mass, a Delta-v, a kilowatt or a flight-rate, and a premium is
priced off an underwriter's book. The two surface delivery prices are already
declared [marginal-transport lower bounds](#what-a-kilogram-is-worth) with no
NRE-style programme overhead in them, and a premium is exactly that kind of
overhead.

With `model_reliability` on, a premium would also count twice the risk that
term already takes off revenue; both are off by default, and the out-of-scope
argument above is sufficient on its own.

⚠️  **Turning it off is worth more than the invoice says**, because a
premium is an *upfront* line and so is multiplied by contingency and then
compounded at the upfront WACC multiplier: it is **2.4% to 4.3%** of total cost
and removing it improves the ratio by **5.5% to 9.6%**. The two are not
interchangeable; quote the improvement.

✅  **Launch insurance is essentially all of it.** The flat liability
premium lands at a median 0.03% to 0.05% of total cost. Full measurement, and
why the programme search makes insurance matter *more* rather than less, in
[calc v1.20.0](versions.md#calc-v1200).

⚠️  **Every measurement committed before 2026-09 was taken with both premiums
charged**, the 20-cell campaign included; set `charge_insurance` True to
reproduce one. The 28-cell campaign is the first that was not.

**What is not on this list, and why.** Crew costs are absent because every
mission here is uncrewed, not because they were declined; Module 3 replaced its
legacy `Crew` line with the autonomous-control NRE, which *is* charged. Orbital
refuelling is not here either: that charge is gated because it is **incorrect**
for this module rather than out of scope, and `escape_direct_launch` re-arms it
the day an escape-direct architecture exists. The test for this section is that
the charge would be **right** and is still not asked for.

## What the model does not capture

Stated plainly so results aren't over-read:

- **Nothing is viable, in any configuration.** Zero asteroids turn a profit on
  a default run, and that is the honest answer rather than a bug. Fixed costs
  (development NRE, autonomy NRE, rig, capsule, contingency) run to
  billions, while the best bulk material is worth a few dollars per kg on
  Earth. The best case the model reaches today, `mars_surface` delivery plus
  beneficiation plus a searched programme, comes within 9% of breakeven (see
  [every destination at this release](README.md#every-destination-at-this-release-mars-surface-is-now-the-best-case)),
  and what put it there is the delivered price of a kilogram on Mars, not the
  asteroids. There is no "don't fly" option, so the ranking is really *which
  target loses least*. **Scale does not rescue it**: market saturation sees the
  programme's concurrent output, so the optimum programme size is interior.
- **Rank by `total_cost_usd / gross_value_usd`, not `profit_usd`.** Revenue is
  orders of magnitude below cost in most configurations, so `profit_usd`
  reduces to `-total_cost_usd` and `top_profitable()` becomes a pure cost
  ranking, a Δv table wearing a profit label. The search inside Stage 4
  optimises the same ratio (`selection_key`).
- **Cheap launch does not rescue this.** Launch is ~2.3% of a mission. Zeroing
  it entirely improves the ratio by 2.3%.
- **Launch prices are held at today's list for the whole programme.** A
  searched programme runs 10 to 20 years, and launch keeps getting cheaper:
  Terzi & Nicoli (2026) fit an experience curve of 21.2% per doubling of
  cumulative payload to orbit, and their conservative scenario puts the cost
  45% below today's by 2030 and 75% below by 2040. Every launch price here is
  the vehicle table's current figure, flat. **The direction of that error is
  not the obvious one**, because a kilogram in space is valued at the launch it
  avoids: a falling price cheapens every mission and every delivered price
  above LEO together, and [master v1.50.0](versions.md#master-v1500--mineral_value-v1140--transportation-v1200)
  measured that pair, the other way round, as worth ~0.5% on the cost side
  against 0.8-5.5% on the revenue side. A projected launch price would make
  the in-space answers WORSE and help only `earth_surface`.
- **In-space utility fractions are judgements.** `IN_SPACE_UTILITY` and its
  per-destination overrides decide how much of the launch-cost-avoided each
  commodity captures, and no market exists to calibrate them against. They are
  the softest numbers in the pipeline, and the per-destination discounts added
  in v1.7.0 are softer still; they are judgements about economies that do not
  exist. They are held to running *downward* for that reason.
- **Low-thrust trajectories are sized, not optimised.** Trip time and power
  are now modelled (see [What the model now charges for](#what-the-model-charges-for)),
  but the EP stage is sized to a fixed target thrusting time rather than having
  its trajectory jointly optimised against payload and arrival date.
- **The mining rate has no flight heritage.** No one has sustained-mined an
  asteroid, so `mining_rate_kg_per_day_per_kg_rig` is an engineering
  assumption. It is a single obvious dial rather than a hidden infinity, but
  it is still an assumption.
- **The drill's cool-down is not on the clock.** Metzger, Zacny & Morrison
  (2020) report that drilling heats regolith enough that it "takes hours or
  even days" to cool back, so a rig that waits between operations digs at a
  lower duty cycle than its rate implies. There is no term for it: the stay is
  the dig at the rated mass rate plus the launch window. Read it into the
  mining-rate dial above, which is where any such loss would land.
- **Δv is analytic, not trajectory-optimised, and it is OPTIMISTIC.** The
  patched-conic estimator meets the target at an apsis and takes the whole
  inclination change at departure, using `a`, `e` and `i` only. Measured
  against a Lambert porkchop with real 3-D geometry over 400 sampled bodies, it
  understates outbound Δv by a **median 1.30 km/s (11.9%), on 86% of bodies**;
  against the three real missions whose published figures it is validated on it
  is low by a consistent **0.40 to 0.46 km/s**. Every campaign this project
  has run inherits that bias, the 28-cell one included, and every ratio in them
  is correspondingly favourable.

  ⚠️  **The obvious fix makes it worse.** The estimator also *over*charges the
  plane change, by a median 4.87%, and the two errors partially cancel;
  correcting only the overcharge increases the total error in every inclination
  band. Neither term should move without the other. Both measurements, and the
  validated solver behind them, are in
  [starred-repos' `FINDINGS.md`](https://github.com/loggger101/starred-repos/blob/main/FINDINGS.md).
- **Launch windows are statistical, not ephemeris-based.** The synodic period
  gives an expected wait; the model does not compute actual departure dates,
  so it cannot tell you *which* window. As of catalog `1.2.0` the catalog does
  at least carry `element_epoch_jd`, so `mean_anomaly_deg` can be referred to a
  date; before that it could not, which made real phasing impossible rather
  than merely unimplemented.
- **Composition is uniform.** Each asteroid is its taxonomy class's mean
  composition all the way through: no core/mantle structure, no regolith
  versus bedrock, no ore grade. Beneficiation concentrates *against that mean*,
  so the purity bound is the class's best phase rather than a real assay.
- **Beneficiation has no flight heritage either.** Magnetic and electrostatic
  separation in microgravity, on a rotating body, with no water and no
  gravity-fed classification, has never been demonstrated. The 0.90 recovery
  is borrowed from terrestrial flotation circuits.
- **Concentrate density is approximated by bulk density** in the volume cap. A
  metal concentrate is denser than the parent body, so the volume constraint
  is conservative.
- **The refinery works only during the stay.** It is flown and costed (energy
  through the array, plant with the rig, since calc v1.25.0), but refining on
  the cruise home is not modelled, so a raw mission's refinery is dearer per kg
  than Stage 2's fifteen-year deduction it replaces.
- **Boil-off hold time is estimated, not integrated.** It uses the Δv-derived
  cruise plus the stay, not an actual thermal model over the real trajectory.
- **C-type "ice" is bound water** in phyllosilicates, not accessible ice. The
  energy to liberate it is now charged (2,500 Wh/kg), but the extraction
  hardware, kilns, condensers, cold traps, is not sized or costed.
- **The duty-cycle alternative to a battery is not priced.** Night-side power
  *is* charged, since v1.14.0, but a rig could mine slowly in daylight instead
  of carrying storage, taking twice the stay rather than twice the plant.
  Where digging slowly is cheaper the model is now pessimistic. A free-flying
  array station-keeping off a small body would see almost no eclipse at all,
  and the pipeline cannot express that architecture either.
- **Boil-off cannot be bought down.** It is applied passively, so hydrolox
  pays the full 0.05%/day with no option to spend array mass and power on a
  zero-boil-off cryocooler. Conservative for hydrolox, but a gap rather than a
  decision.
- **Tank mass scales purely with volume.** The pressure term genuinely does;
  insulation and minimum gauge scale with area, so the model overstates the
  penalty on a very large tank and understates it on a small one. NASA's large
  NTP studies get an LH2 tank near 12-15% of propellant mass; this model says
  53% at the tonne scale its stages actually work at. The direction is chosen
  deliberately, the propellants that most want a generous tank model are the
  speculative ones.
- **Non-Earth launch origins are not modelled.** Stage 3 lists a lunar mass
  driver and a lunar space elevator, both roughly two orders of magnitude
  cheaper per kg than any rocket. Stage 4 departs from Earth and prices a
  discrete launch, so it cannot read either; their payload figures are annual
  throughput. They are markers for an architecture the pipeline does not have,
  not inputs to it.
- **Sails and tethers cannot be sized at all.** Anything propellantless has no
  mass ratio, so the rocket equation reports that it moves any payload for
  free. Doing it honestly needs a thrust-limited trajectory solver, the same
  thing missing from the EP stage, so they are excluded rather than allowed
  to report infinity.
