# Provenance of the frozen Stage 3 tables

The CSVs beside this file are **history**: the hand-frozen spacecost tables the
cells before master v1.59.0 read (CLAUDE.md, "campaign/stage2/ and
campaign/stage3/ are history"). Their bytes are never edited, so a cell built
on one still reproduces. What a frozen row's `notes` say is what spacecost said
when it was frozen; where General_Research has since found that a note
overstates its source, or that a value is a scenario, it is recorded **here**,
row by row, beside the current spacecost treatment.

Every entry keeps the frozen value and range. None proposes a replacement. The
rc- numbers are revision candidates in
[General_Research](https://github.com/loggger101/General_Research); "current
spacecost" means spacecost main at 0.18.4 (data contract 1.27.4) when the
entries were written; since master v1.86.0 this repository is pinned to
v0.19.0 (contract 1.28.0), which keeps each treatment named here.

## Rows the same in every frozen set

The rows below carry the same values in the top-level tables and in every
`spacecost-0.4.0/` to `spacecost-0.14.0/` set, except where an entry says
otherwise. Since master v1.80.0 the worksheet quotes the current spacecost row
beside each one it reads.

### propellants.csv

- **hydrolox (LH2 / LOX)**, $1.60/kg (stored 1.5999999999999999). The note's
  "LH2 base price $3-6/kg (NASA contracts)" names no contract, and the step to
  "~$10/kg" with handling overhead, and the blend to $1.60 with LOX, are not
  shown. Current spacecost calls the $10/kg component a scenario and gives
  Space Insider's ~$6.1/kg and DLA's FY2025 standard as comparators (rc-576,
  rc-626).
- **Krypton (Hall)**, $300/kg in the top-level table and 0.4.0 to 0.9.0 (0.10.0
  and 0.14.0 store $794/kg). An archived bulk-price reference with no published
  source. Current spacecost's $794/kg is the geometric centre of $300/kg bulk
  krypton (INL/RPT-23-75203, sec. 1: about $1/L, ~$267/kg) and SETS Space's
  $2,100/kg flight-grade lower quote, two procurement scopes; neither rebases
  the archived $300 (rc-630).
- **FEEP (indium field emission)**, $250/kg. No price source is recorded. It
  matches USGS MCS 2026's 2022 U.S. warehouse average for 99.99% refined
  indium (pp. 99-100; $370/kg 2025e), a comparator, not a FEEP-grade quote;
  under review as rc-651.

- **Xenon (Hall / ion)**, 54.0 kg/N. The frozen comment's 12.7 kg / 236 mN is
  NEXT PM1 (12.7 kg, 13.5 kg with harnesses; NASA/TM-2011-216973, pp. 37-38),
  a predecessor proxy, not NEXT-C: NEXT-C is about 14 kg at 235 mN (NTRS
  20205005689, pp. 4-5), ~60 kg/N. Neither states a system-mass boundary
  (rc-656).
- **Argon (Hall / ion)**, 1,500 s, 0.40, 40.0 kg/N. Generic mission-model
  scenarios: SpaceX's Starlink report gives only relative figures (2.4x the
  thrust and 1.5x the Isp of the first generation, Progress Report 2023, p.
  48), and NASA S3VI names argon with no values (rc-657).
- **Water (gridded ion / ECR)**, 900 s, 0.35, 80.0 kg/N. Scenarios. The frozen
  note's Pale Blue flight was a water resistojet (2023); Pale Blue's first
  successful in-orbit water ion operation is in its 2025 release. The ESA and
  JAXA ECR systems it names are not identified. Nakagawa et al. (Acta
  Astronautica 157, 2019) measure at most 665 +/- 59 s on a miniature CubeSat
  ECR thruster, neutraliser neglected (rc-659).
- **Water (electrothermal / resistojet)**, 10.0 kg/N, 0.75, continuous
  scaling. Model assumptions with no matched device. Mirtich (NASA TM-83489,
  p. 4) gives a historical power-dependent resistojet mass that includes the
  PPU and thermal rejection, a comparator only (rc-660).
- **VASIMR (argon, variable Isp)**, 4,000 s, 0.50, 53.0 kg/N. A mission-model
  scenario: VX-200's measured argon point at 200 kW is 4,900 +/- 300 s, 72
  +/- 9% and 5.8 +/- 0.4 N (Squire et al., IEPC-2011-154, p. 1). The ~300 kg
  behind 53 kg/N has no recorded source or mass boundary. The frozen note's
  "100 hours at 80 kW" is VX-200SS's endurance record, 88 continuous hours
  (Chang Diaz et al., IEPC-2022-525, pp. 1 and 9), a different benchmark from
  VX-200's performance (rc-661).

### launch_vehicles.csv (`spacecost-0.4.0/` to `spacecost-0.14.0/`)

- **Ariane 6 (A64)**, $115M to $132M, an estimate. The note's "€115M (2018
  est.)" is a target in 2014 economic conditions, not a 2018 estimate
  (Assemblée nationale, Rapport d'information no. 1438, 2018, printed p. 36),
  converted at $1.15/€ without escalation; the $115M low end has no range
  method. The 0.4.0 and 0.5.0 notes credit the ESA Ariane 6 overview, which
  states payloads only. The same report's press-reported $130M transition
  price (p. 62) and Euronews (Jul 2024) are comparators (rc-700).

### operational_costs.csv

- **Eclipse / night-side dark fraction**, 0.50 [0.35, 0.55]. Scenario
  geometry. Stubbs & Wang (2012, sec. 5.1, p. 275) is a Vesta tropical
  comparator for a roughly half-time dark period, not an asteroid-wide
  fraction, and no source gives the range (rc-627; the top-level 1.15.0 row,
  rc-811).
- **Energy storage round-trip efficiency**, 0.90 [0.80, 0.95]. Schmitz et al.
  (2023, Table 3) is a Li-ion efficiency comparator, at its own system boundary
  (rc-627).
- **Power-system row baseline dark period**, 0.58 h [0, 1.2]. The 0.58 h is
  the ISS eclipse (Kascak et al., NASA/TM-2001-211138, p. 1), a comparator,
  not a sourced deep-space baseline (rc-627).
- **Energy storage usable specific energy**, 104 Wh/kg: as in 0.4.0 below
  (rc-729).
- **Propellant tank recurring cost**, $6,000/kg of tank dry mass [$3,000,
  $25,000], in the top-level table and the 0.4.0 to 0.10.0 sets (0.14.0's
  differently worded row is below, rc-730). An engineering estimate: the
  note's ~$5,300/kg comes from an unreferenced ~$30M Centaur III stage less
  an assumed ~$20M RL10, over ~1,880 kg of structure, and neither anchor nor
  the tank-only allocation has a source. Whole-stage comparators, such as
  NASA OIG's $29M second-ICPS hardware purchase (IG-20-012, p. 23), are not
  tank costs (rc-825; current spacecost rc-421).

## `spacecost-0.4.0/operational_costs.csv`

- **Mining payload recurring cost**, $300,000/kg [$100,000, $1,000,000]. The
  frozen note credits SSCM/NICM; no checked cost-estimating relationship or
  recurring unit cost matches mining hardware, so SSCM/NICM are unverified
  former anchors and the value and range are scenario inputs (rc-727).
- **Electric propulsion system recurring cost**, $1,500,000/kW [$500,000,
  $3,000,000]. No published NASA record prices a NEXT-C string as a recurring
  unit; the $18.41M NEXT-C award and the Gateway PPE contract are bundled
  development and system contracts, not per-string $/kW quotes. Point and
  range are scenarios (rc-728).
- **Energy storage usable specific energy**, 104 Wh/kg [70, 160], i.e. 130
  Wh/kg x 0.80 depth of discharge. The 130 is an analogy to protected D-RATS
  spacesuit-simulator packs, measured at 124-133 Wh/kg (mean 129.6; Bennett &
  Baldwin, NASA/TM-2010-216906, Table 5), not spacecraft batteries; NASA's
  140 Wh/kg usable Li-ion figure at 80% DoD is a separate comparator (rc-729).

## `spacecost-0.5.0/`

Since master v1.80.0 the verification worksheet also quotes, beside any row it
reads from a frozen set, the installed spacecost release's row of the same name
(`since_frozen` in `campaign/verification_sheet.py`), for scope only: part 18
does not credit a frozen value with a source its own row never named.

- **propellants.csv, Krypton (Hall)**, 2,000 s, 0.45 and 35 kg/N. A generic
  mission-model selection, not demonstrated krypton Hall performance: NASA
  S3VI's small-spacecraft Kr Hall devices list 900-1,575 s, manufacturer
  reported; NASA-457M's 0.50 is a discharge efficiency, not the 0.45 total;
  S3VI's small-device mass and thrust are not the cargo-scale 35 kg/N. Both
  are comparators, not replacements (rc-584, rc-625).
- **operational_costs.csv, Rig salvage fraction**, 0.5 [0.0, 0.8] of remaining
  book value. A scenario: NASA CR-3349's 5-10% of capital and 60-90% of
  on-orbit cost use other denominators, and Mas 2007 is condition-priced resale
  in a liquid terrestrial market, not an asteroid rig residual (rc-624).
- **operational_costs.csv, Depot berthing & handover operations**, $2M
  [0.5M, 8M] per delivery. A scenario: no commercial depot or institutional
  component price exists; NASA CRS figures are whole-mission comparators about
  100x the estimate; ISS berthing is an analogy, not a derivation (rc-629).
- **operational_costs.csv, Power system (solar + battery)**, $800/W EOL [500,
  1,500]. An estimate: the JPL comparator (Surampudi et al.) covers solar-array
  cost only, in older dollars, not the PV-battery train (rc-631).
- **operational_costs.csv, Volatile cargo containment**, 0.05 [0.03, 0.12] kg
  per kg of water. The frozen note's "which is what the citation covers" names
  no citation. An engineering estimate for an incremental passive sealed hold
  beyond ore restraint: no published source gives the mass fraction or
  multi-year stability; Jones 2017's tank data and NASA's cryogenic
  zero-boil-off work are scope comparators only (rc-645).
- **operational_costs.csv, mining reliability rows**: spacecraft MTBF 30 [15,
  60] years, an unfitted scenario on an assumed constant hazard; first-of-kind
  success 0.85 [0.70, 0.95], a selected 11-of-13 outcome tally, not a
  sustained-mining reliability; mature success 0.95 [0.85, 0.99], an
  uncalibrated scenario, with satellite-deployment and one-actuator records as
  comparators only (rc-646).
- **operational_costs.csv, Beneficiation / on-site processing energy**, 500
  [100, 2,000] Wh/kg of refined product. Its frozen citation, a classroom
  worksheet, is a source General_Research rejected. DOE's 2007 Mining Industry
  Energy Bandwidth Study, Exhibit 24, supports only a terrestrial 19.3 Wh/kg of
  mined material, on a feed basis; the frozen centre and range are an
  assumption (rc-684).

## `operational_costs.csv` (top level, spacecost 1.15.0)

- **Launch vehicle reliability**, row 52, 0.97 [0.90, 0.99]. A
  fleet-representative scenario with no fitted cohort or estimator, and a
  scenario envelope rather than a confidence interval. Cross & Vesely's
  first-flight analysis and SpaceX's single-family aggregate are comparators,
  not a derivation (rc-652).

## `spacecost-0.10.0/`

- **launch_vehicles.csv, Long March 8A**, 3,500 kg to GTO. No variant-matched
  primary source: the figure is a secondary catalogue's (Next Spaceflight);
  CASC gives the CZ-8A no GTO figure, and the 2.8 t a CNSA-hosted report gives
  is the base CZ-8's. A scenario proxy (rc-704; current spacecost rc-703).
- **propellants.csv, HTP (98% peroxide monoprop)** $5.00/kg [5.00, 7.155],
  and the derived **HTP / RP-1** $4.6875/kg. Unverified historical estimates:
  the HTP input is unsourced, and its current-source review is rc-319. Epic
  Aerospace's $65/kg listing is not a substitute until its date, order size
  and shipping basis are matched (rc-705).

## `spacecost-0.14.0/` (pipeline 1.23.6)

### launch_vehicles.csv

- **Long March 8A**, 3,500 kg to GTO: as in 0.10.0 above, a scenario proxy
  with no variant-matched source (rc-707). Its price, $52.9M [$40M, $70M], is
  a scenario band: no source or calculation gives it, and the eXTP
  launch-service budget (RMB 245.2M) names no variant and is a budget, not a
  price (rc-711; current spacecost rc-503).
- **Long March 5**, $133M [$110M, $160M]. Only the ~$160M high end has a
  source (Wikipedia); the $110M low end has none, no priced comparator is
  named, and FAA AST's 2018 fact sheet gives the price as "Undisclosed". A
  scenario band of unstated vehicle-cost or launch-service scope (rc-708;
  current spacecost rc-592).
- **Long March 4C**, $38.7M [$30M, $50M]. Rests on a Long March 4B $50M (2006)
  comparator by analogy; the comparator's source, the 4B-to-4C step and the
  dollar-year conversion are not documented, so the band is a scenario
  (rc-709; current spacecost rc-505).
- **Long March 2C**, $29.6M [$25M, $35M]. An analogy to the Long March 2D's
  $30M, itself under review (rc-315): a scenario band. Batch or bundled 2D
  service fees are not a substitute (rc-710; current spacecost rc-476).
- **Long March 12**, $63.2M [$50M, $80M]. No source or comparable price
  boundary; the Guangzhou Daily report of a quote below RMB 20,000/kg states
  no orbit, utilisation, date or scope. A scenario, under current review
  rc-318 (rc-712).
- **Vega C**, $45.1M [$37M, $55M]. The "€48M (2022)" traces to ESA's 2022
  contract disclosures: €48.62M for the Sentinel-1C launch-service contract,
  beside a separate €232M Vega-C launch-services line. One institutional
  contract, not a list price; the $37M low end, the $45.1M centre and the 2026
  conversion have no source, so the band is a scenario (rc-721; current
  spacecost rc-720).
- **Long March 2D**, 3,500 kg to LEO. The payload is FAA AST's 2018
  Compendium fact sheet figure, 3,500 kg to 200 km LEO; the note's Wikipedia
  attribution covers only the $30M price (rc-723; current spacecost rc-719).
- **Proton-M**, $65M. FAA AST's 2018 Proton M fact sheet, an "Estimated Price
  per Launch", which GAO-17-609 (Table 4, p. 30) repeats from FAA data and
  calls a public-information estimate that a customer's price departs from
  (p. 21): a dated agency estimate in nominal dollars, not a 2026 price,
  whatever `price_basis` and `reference_year` say (rc-725; current spacecost
  rc-724).

### operational_costs.csv

- **Expendable upper stage recurring cost**, $4,800/kg [$1,750, $13,400], and
  **Propellant tank recurring cost**, $6,000/kg [$3,000, $25,000]. Estimates:
  the Falcon 9 and Centaur III anchors are unmatched, and the tank-only
  allocation (Centaur III less an assumed RL10) is unsupported. Whole-stage and
  tank-only scopes are distinct. GAO's $52.0M (1990) Centaur and NASA OIG's
  $29M second-ICPS purchase are historical whole-stage comparators, not
  current Centaur III production prices or a tank allocation. The source-scope
  review is rc-421 (rc-730).
- **Return capsule recurring cost**, $150,000/kg [$50,000, $400,000]. No
  like-for-like capsule unit cost is published: an engineering scenario, not a
  sourced or derived rate. Stardust's 46 kg capsule and mission totals do not
  allocate capsule cost (rc-731; current spacecost rc-497).
- **Mining payload recurring cost**, $300,000/kg [$100,000, $1,000,000]. No
  registered mining-hardware CER or recurring unit cost matches it; a scenario,
  and generic spacecraft or instrument CERs do not apply without a shown fit
  (rc-732).
- **Surface lander recurring cost**, $200,000/kg [$100,000, $500,000]. The
  CLPS comparator, NASA OIG task-order values over Nova-C dry mass, is a
  full-service ratio, not a lander hardware unit cost or CER; its review is
  rc-300 (rc-733).
- **FAA Part 450 licensing compliance**, $2,500,000/programme [$1,000,000,
  $5,000,000]. An estimate no document prices. The FAA PRA notice's 2,903
  initial-application paperwork hours are a workload floor, not a cost rate,
  and exclude safety-case engineering; CRS R48582 is not a cost basis, and the
  per-launch user fee stays outside this row (rc-734).
- **Depot berthing & handover operations**, $2M [0.5M, 8M]. ISS visiting-vehicle
  berthing is an analogy, not a component-level price calculation, and NASA
  OIG's CRS figures are full-mission ceilings, not handover prices: a scenario
  (rc-735).
- **Power system (solar + battery)**, $800/W EOL [500, 1,500]. An estimate with
  no same-boundary source. Surampudi et al. (JPL D-24454) is a historical
  solar-array-only comparator without batteries, not a price for the
  PV-battery train (rc-738).

### propellants.csv

- **HTP (98% peroxide monoprop)** and **HTP / RP-1**: as in 0.10.0 above,
  unverified historical estimates under rc-319 (rc-706).
- **MPD (lithium magnetoplasmadynamic)**, 4,000 s, 40 kg/N, 0.40. No source is
  recorded for the three values or the test device. Polk et al. (IEPC-2024-841,
  pp. 2, 6) summarise Princeton's facility capability and measured MAI lithium
  MPD results, but name no RIAME test and do not support the 40 kg/N, so the
  inherited values are scenario inputs (rc-775).

## `launch_vehicles.csv` (top level)

- **Vega C**, $37M. The note's "Source: Avio / ESA — ~€34M" names no
  document, date, EUR/USD or inflation method, or whether it is a vehicle cost
  or a launch-service price: an unsourced historical estimate. ESA's later
  €48.62M Sentinel-1C contract is a different, mission-specific amount and does
  not replace it (rc-722).
