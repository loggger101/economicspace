# Provenance of the frozen Stage 2 tables

The CSVs beside this file are **history**: the hand-frozen mineral value
catalogs the cells before master v1.59.0 read (CLAUDE.md, "campaign/stage2/
and campaign/stage3/ are history"). Their bytes are never edited, so a cell
built on one still reproduces. Most of their columns carry no source of their
own: a row's `notes` describe the mineral, and its `ref_price_source` is the
catch-all "USGS/LME/mineralogy reference" on every row. Where General_Research
has since recorded what a column's value is, and what its sources do and do not
support, it is recorded **here**, column by column, beside spacevalue's current
treatment. This file mirrors `campaign/stage3/PROVENANCE.md`.

Every entry keeps the frozen value. None proposes a replacement. The rc-
numbers are revision candidates in
[General_Research](https://github.com/loggger101/General_Research); "current
spacevalue" means spacevalue main at 0.8.2 (data contract 1.22.1), which this
repository has not repinned to.

The sets this file covers are `mineral_value-1.12.0/` (cislunar) and the
top-level `mineral_value_catalog.mars_surface.csv` and
`mineral_value_catalog.mars_orbit.csv` (Stage 2 1.9.0). Where the same value
sits in the pinned price release a live cell reads
(`asteroid_pipeline/mineral_value/prices-2026-11-20/`, lunar_surface; its prices are
`prices-2026-11-12`'s), it
carries the same limits.

Since master v1.84.0 the verification worksheet prints the entry beside any
Stage 2 input whose row carries the value below, in a span that part 18 strips
before it looks for a source: a recorded limit is not backing, and the input's
NEED BACKING flag stands.

## Columns the same in every set

### refining_kwh_per_kg (per kg of raw feed)

All of these are engineering values per kg of raw feedstock, not measured
phase-specific refining intensities (rc-634).

- **kamacite, taenite, nickel-iron**, 5.0. An engineering allowance. The one
  comparator, hydrogen direct reduction at 3.48 kWh/kg of liquid steel (Vogl,
  Åhman & Nilsson 2018, J. Clean. Prod. 203, 736), has a different feed and
  product (current spacevalue rc-366).
- **cohenite**, 5.0. Nickel-iron's 5.0 transferred to a carbide with no carbon
  or product boundary (rc-452).
- **schreibersite**, 6.0. An unmeasured route assumption: Gull, Feng & Pasek
  (2022) corrode schreibersite in water and report no energy (rc-443).
- **olivine, enstatite, plagioclase, silicates**, 1.0. A low-energy scenario:
  microwave sintering of lunar simulants into construction material took
  19-27 kWh/kg (Liu et al. 2025, J. Eur. Ceram. Soc. 45, 117047), a different
  route and product, so a comparator only (rc-390).
- **carbon**, 2.0. An engineering scenario with no source (rc-437).

### in_space_processing_usd_per_kg (c_ref, per kg of raw feed)

Every row is the same formula: `refining_kwh_per_kg` at about $6.08/kWh (the
$800/W-EOL power-system cost spread over 15 years at full output) plus $200/kg
of plant ($300,000/kg of plant hardware over 100 kg/yr per kg of plant for 15
years). So 230.420564301 for the 5.0 kWh/kg metals, 236.504677162 for
schreibersite, 224.336451441 for troilite, 212.168225721 for carbon and
206.084112860 for the 1.0 kWh/kg silicates. Each component is a spacecost
estimate or scenario: the power row has no same-boundary source (rc-631), the
$300,000/kg is the unsupported generic mining-payload estimate (rc-517), and
the 100 kg/yr/kg throughput is an estimate in [20, 500] (rc-383). A model
deduction, not a published market quote (rc-642).

### density_gcm3

The generic row source maps no density to a reference; these are the phase
sources General_Research checked (rc-639, rc-640).

- **nickel-iron, kamacite**, 7.90. Kamacite's calculated density (Handbook of
  Mineralogy, D(calc.) 7.90, no measured value), used for the alloy; no IIIAB
  bulk-alloy basis is given. Remo (1993, Table 2, p. 169) puts selected
  iron-nickel meteorites at 7.29-7.88, a related bulk comparator (rc-639).
- **cohenite**, 7.40. Inside cohenite's measured 7.20-7.65 (Handbook of
  Mineralogy) (rc-639).
- **schreibersite**, 7.40. Inside its calculated 7.12-7.44 but above its
  measured 7.0-7.3 (Handbook of Mineralogy) (rc-639).
- **troilite**, 4.61. Agrawal, Carlozzi & Bryson (NASA NTRS 20170001623,
  Table 1, p. 20) list 4.61 for troilite, under a formula the extracted table
  reads as FeSi; the Handbook of Mineralogy gives FeS at 4.67-4.79 measured and
  4.85 calculated. Unreconciled with the phase (rc-640).
- **carbon**, 2.10. A graphite proxy, inside graphite's measured 2.09-2.23
  (Handbook of Mineralogy); nothing supports an amorphous or other form
  (rc-640).
- **plagioclase**, 2.69. A representative density with no Na/Ca composition
  defined: inside labradorite's measured 2.68-2.72 (Handbook of Mineralogy),
  against 2.62 for albite-composition feldspar (Agrawal et al., Table 1)
  (rc-640).

### terrestrial_price_usd_per_kg

- **kamacite, taenite, nickel-iron, cohenite, schreibersite, troilite**,
  blank. No direct quote: Stage 2 reads the missing quote as zero. A missing
  quote, not an observed zero market price (rc-643; current spacevalue rc-456,
  rc-589).
- **olivine, enstatite, silicates**, $0.05/kg. An engineering placeholder with
  no grade, product or quote year (rc-643; rc-455).
- **carbon**, $0.20/kg. A scenario with no grade or quote; USGS graphite and
  Platts N330 carbon black are other products (rc-643; rc-508).
- **plagioclase**, $0.10/kg. A rounded comparator to USGS Mineral Commodity
  Summaries 2026's $110/t for 2025 marketable feldspar (p. 82), not a quote for
  the phase (rc-643; rc-145).

## `mineral_value-1.12.0/` (cislunar)

- **in_space_utility**, all rows. Cislunar's
  `IN_SPACE_UTILITY_BY_DESTINATION` override is empty, so every factor is the
  base `IN_SPACE_UTILITY` profile's (0.70 for the Fe-Ni phases and
  schreibersite, 0.25 for the silicates, 0.40 carbon, 0.30 troilite):
  engineering judgements with no market to calibrate them. Since master
  v1.81.0 the worksheet names the base-map fallback (rc-638; rc-696).
- **annual_market_kg**, 5,000 kg/yr for carbon, 25,000 for the structural
  class (the Fe-Ni phases, cohenite, schreibersite, troilite) and 15,000 for
  the shielding class (olivine, enstatite, plagioclase, silicates). Cislunar's
  100,000 kg/yr import budget, a judgement, times the class's share
  (chemical 5%, structural 25%, shielding 15%), an allocation scenario. Kornuta
  et al. (2019) and LunA-10 (Northrop Grumman 2024) are demand forecasts that
  apportion nothing by class: context, not a source for the split, and not
  observed absorption (rc-636; rc-432).

## `mineral_value_catalog.mars_surface.csv` (Stage 2 1.9.0)

- **annual_market_kg**, 1,000 kg/yr for carbon, 5,000 for nickel-iron and
  troilite, 3,000 for the silicates. Mars surface's 20,000 kg/yr, a judgement
  (NASA forecasts no Mars-surface demand), times the same class shares, an
  allocation scenario. NASA's "10's of metric tons of commodities per year"
  for initial commercial use (Sanders & Kleinhenz 2024, NTRS 20240002713,
  p. 3) is order-of-magnitude context for an activity it marks not funded or
  approved, not a Mars-market forecast (rc-653).

## `mineral_value_catalog.mars_orbit.csv` (Stage 2 1.9.0)

- **annual_market_kg**, 3,000 kg/yr for carbon, 15,000 for nickel-iron and
  troilite, 9,000 for the silicates. Mars orbit's 60,000 kg/yr, a one-mission
  scenario, times the class shares, an allocation scenario. NASA's "100s
  metric tons per year for human Mars transportation" (Sanders & Kleinhenz
  2024, p. 3) is scale context for a notional activity, not a depot-market
  forecast or observed shares (rc-655).
