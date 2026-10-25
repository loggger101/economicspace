# CLAUDE.md: working in this repo

The rules that will bite you, the invariants, and the decisions that look wrong
and are not. Each rule is one or two lines; the account of how it was learned
is in [LESSONS.md](LESSONS.md) under a heading of the same name (frozen
2026-10-17, read on demand, never loaded by default).

| file | is the authority for |
|---|---|
| [`README.md`](README.md) | what the pipeline is, how to run and verify it, and the **current** numbers |
| [`MODEL.md`](MODEL.md) | what the model does, charges for, declines and cannot capture |
| [`versions.md`](versions.md) | every release, every superseded number, the per-module changelogs |
| [`CITATIONS.md`](CITATIONS.md) | where each source came from and what it obliges (references, never values: a value's source is cited on the row that carries it in `modules/*.py`) |
| **this file** | how to edit safely |
| [`LESSONS.md`](LESSONS.md) | the long form behind each rule here, as of 2026-10-17 |
| [`spacecost`](https://github.com/loggger101/spacecost) | Stage 3's reference tables and the delivery-price chains |
| [`quietlaunch`](https://github.com/loggger101/quietlaunch) | the windowless dashboard launcher `launch_ui.py` hands over to, and its Windows traps |
| [`quietqueue`](https://github.com/loggger101/quietqueue) | the campaign job runner the four `campaign/` shims hand over to (queue, no-console supervisor, memory watcher, pause), and its traps; pinned in `requirements-campaign.txt`, checked by `campaign/quietqueue_pin.py`, never auto-installed |
| [`AsteroidCatalog`](https://github.com/loggger101/AsteroidCatalog) | builds and publishes the Stage 1 catalog |
| [`starred-repos`](https://github.com/loggger101/starred-repos) | the audit of 17 external repos and its probes; `orbital.py` was taken from it |

**Keeping this file small is a rule, not a preference.** It quotes no
measurement README or MODEL.md carries (`verify_docs.py` check 12 fails on a
line sharing three distinctive figures with one of them; a lone number gets past it),
types no count it cannot check, and carries no release history. A release
adds its notes to `versions.md` and, if it teaches something, one line here.

## Before you touch anything

- **Never run Stage 1, 2 or 3 to test something else.** Stages 2 and 3
  re-fetch live prices and overwrite the only copy of their CSVs, which breaks
  every `.verify` baseline and every archived-cell derivation. Use
  `--stages 4`. If you must run one, copy `asteroid_pipeline/*.csv` first.
- **Take a baseline on a clean tree before editing model code:**
  `py verify.py baseline --tag <current>`, then edit,
  `py verify.py check --tag <current>`. Never edit `master.py` or `modules/`
  while a `verify.py` run is going: its workers import them as they start.
- **The tree lives in a synced folder** (OneDrive). Every harness runs
  `tree_check.py` first; read `git show --stat` after every commit, and treat a
  `*-DESKTOP-*` file as the newer side of a sync conflict until diffed. See
  [Environment](#environment).
- **Interpreter:** `py` or `python`; ask the machine (`py -0`,
  `py platform_check.py`) and never type a version into a doc. If `py` says
  "Unable to create process", its registration is stale: use `python`.
- **Run `py verify_docs.py`** (about a second, no inputs) after touching any
  doc, config field, reference table or printed number.

## Build

Nothing is built. `modules/` is a package and `master.py` is a hand-written
shim (master v1.57.0 retired `build_master.py` and the generated file): it
imports the four modules, binds the aliases below, holds `MasterConfig` and
`run_full_pipeline`, and forwards every other `master.<name>` to the module
that defines it. Edit a module and commit it; there is no second file.

| module | master's name for it |
|---|---|
| catalog | `CONFIG`->`CATALOG_CONFIG`, `build_catalog`->`build_asteroid_catalog` |
| mineral_value | `CONFIG`->`MINERAL_CONFIG`, `validate`->`validate_minerals` |
| transportation | `CONFIG`->`TRANSPORT_CONFIG`, `validate`->`validate_transport` |
| calc | `CONFIG`->`CALC_CONFIG` |

- A name two modules bind to different objects is **refused**, not resolved
  (`master.CONFIG` raises). Read it from the module, or add an alias here;
  `_IDENTICAL_COPIES` is only for equal copies that are not one object.
  `verify_docs.py` check 18 resolves every `master.<name>` the repo reads.
- The forwarding serves reads from outside. Code inside `master.py` sees only
  what it imports by name.
- `modules/__init__.py` silences spawned workers before any module prints and
  imports no module, because a Stage 4 worker imports `modules.calc` alone.
- Each module still runs on its own (`python modules/calc.py`) and still
  installs its own `_REQUIRED_PKGS` at import; check 7 holds their union to
  `requirements.txt`.

## Versions and release notes

Current: catalog `1.10.0`, mineral_value `1.16.0`, transportation `1.23.0`,
calc `1.32.0`, master `1.57.0` (checked by `verify_docs.py` check 2; the master
version is `MASTER_VERSION` in `master.py`).

- Each module's `pipeline_version` is stamped into every CSV it writes.
  **Changing any number a run produces means bumping it. Bumping does not mean
  a number moved**: versions.md's "moved without moving a number" table lists
  the stamps that did not.
- A release writes in two places, both in `versions.md`: **Releases** (what it
  did and the measurement that says so) and **Module changelogs** (the stamp,
  its pairing, and the config fields and output columns it adds; that schema
  half is what says whether an archived CSV can answer a question). Never a
  changelog in module comments: `ui_meta` scrapes a field's comment block as
  its dashboard help.
- transportation's stamp **is** spacecost's data contract (`DATA_VERSION`);
  `verify_stage3.py` check 2 holds them equal, so a repin can move it.
- Comments, docstrings and console text are not output: no stamp.
- CSVs stamped `1.0.6` / `1.1.4` / `1.3.6` are untrustworthy (two parallel
  repos shipped different code under each). Before building or measuring,
  confirm the branch is up to date with the remote.

## Defaults that moved: reproducing an older number

A configure-nothing run today is not what any 2026-09 table measured. Each
flag below is bit-identical to the release before it when set to the old
value, and no combination reproduces a 2026-09 cell on today's **inputs**
(catalog, Stage 2 prices and spacecost tables all moved too; the frozen sets
are under `campaign/stage2/` and `campaign/stage3/`).

| release | field | now | old |
|---|---|---|---|
| calc 1.17.0 | `use_beneficiation`, `optimise_programme_scale` | True | False |
| calc 1.20.0 | `charge_insurance` | False | True |
| calc 1.21.0 | `market_model` | `capacity_cap` | `elasticity` |
| calc 1.22.0 | `sell_surplus_at_discount` | True | False |
| calc 1.22.0 | `model_reliability`, `model_learning_curve`, `apply_wacc_compounding` | False | True |
| calc 1.23.0 | `max_mining_fraction` | 1.0 | 0.05 |
| calc 1.24.0 / 1.25.0 / 1.26.0 | `model_mineral_phases`, `model_refinery`, `model_detailed_phases` | True | False |
| calc 1.27.0 / 1.28.0 | `repair_settled_overshoot`, `damp_sizing_loop` | True | False |
| calc 1.29.0 | `launch_capacity_rtol` | 1e-9 | 0.0 |
| calc 1.32.0 | `model_isru_processing` / `isru_processing_usd_per_kg` | True / 0.0 | False / 50.0 |

Traps in that table:
- `apply_wacc_compounding` off makes `model_programme_calendar` (still True)
  charge nothing; it is left True deliberately and the run banner says which
  state it is in.
- Turning `model_learning_curve` off makes a programme **worse** (it is a
  discount), and it is exactly inert at N = 1, so a single-mission headline
  cannot check it. The same is true of the duty-cycle and calendar terms.
- `model_reliability_growth` is True and inert; it only shapes reliability.
- `max_mining_fraction` is invisible on beneficiated cislunar cells; a
  reproduction that checks only those passes without it.
- Insurance is off for **scope** (correct and not asked), the tanker charge
  (`charge_tanker_flights` with `escape_direct_launch`) is gated off because it
  is **wrong** here. Never add either to MODEL.md's corrections list.
- An upfront cost line is worth about twice its face (contingency and the
  upfront WACC multiplier); an end-of-mission line its face.

## The model: load-bearing assumptions (do not "fix")

- **`delivery_destination` must agree in Stage 2 and Stage 4**
  (`MINERAL_CONFIG` prices the cargo, `CALC_CONFIG` flies it; in `master.py`
  set `MASTER_CONFIG.delivery_destination`). `CALC_CONFIG` defaults to
  `earth_surface` while the catalog on disk is usually `cislunar`, and
  `destination_check()` only prints `MISMATCH` to stdout. `run_pipeline.py`'s
  `preflight()` refuses a mismatch; any other Stage-4 entry point must call it
  or set the destination explicitly and keep `MISMATCH` in its output filter.
  Anything that reads a Stage 2 table to interpret a result must first ask
  which destination it was priced for: its prices **and** its routed ceilings
  are per destination, and the wrong one raises nothing.
- **Every commodity is priced per destination**: terrestrial price **plus**
  `in_space_utility x launch-cost-avoided`, less on-site refining. Utility
  factors are judgement, the softest input in the model; treat them as a dial.
- **Utility overrides only run downward** (local competition: a base that can
  dig its own water does not pay to import it). `leo`, `cislunar` and
  `mars_orbit` take the base profile; `mars_orbit`'s empty dict is the point (the
  crust is 4,100 m/s of ascent away). `gto` takes `geo`'s profile **by
  reference**; do not copy it into a literal. Utility families
  (`_UTILITY_FAMILIES`) are asserted at import at every destination.
- **The import budget is split per commodity class** (`_DEMAND_SHARE_BY_CLASS`,
  sums to 1) and `annual_market_kg` is **routed**: a commodity flown home is
  bounded by world production, one sold at a depot by its import budget. Every
  in-space destination must have a demand row (asserted); a missing row used
  to mean an unbounded market.
- **Cislunar is cheaper to reach than LEO** (an NRHO capture only binds the
  orbit, at low perigee: `_cislunar_capture_dv_km_s`). **Mars is its own
  heliocentric transfer**, not a scaled Earth return. Airless destinations
  ignore `use_aerocapture_return`; elsewhere aerocapture and propulsive capture
  are both priced per asteroid.
- **Surface delivery is chained per stage** (`_DELIVERY_LEGS`, from spacecost);
  never lump it into one burn. Surface prices are marginal-transport lower
  bounds that include building the expended stages; surfaces rising while
  orbits fell under spacecost v0.4.0 is correct.
- **spacecost's `TUG_ISP_S` is 465 s while the hydrolox row says 452**, and the
  GEO deorbit burn is 1,490 m/s against a row of 1,488: both are asserted at
  import rather than derived, because deriving them moves published prices.
  That is a release with a re-measurement, never a tidy-up.
- **A commodity with no in-space market is worth its terrestrial price minus the
  downleg**, not zero, at a depot. `value_route` records which fate it took.
- **The payload mix is a fractional knapsack** (`optimal_payload_mix`), greedy
  by $/kg, provably optimal; content and purity bounds fall out of it. A
  mineral's value is the better of its own price and its yields
  (`_phase_value`), in the phase walk only; never move the four-fraction walk
  onto it.
- **Inseparable phases sell as one product** (`_INSEPARABLE`: kamacite and
  taenite). Before splitting a phase, ask whether any process separates the
  parts. A refinement moves a number only where a **source** moves it.
- **The mission architecture is searched per asteroid** (vehicle, propellant,
  return mode, ISRU, rendezvous apsis, concentration ratio, power source).
  Add a new choice to the search, never as a catalog-wide `CalcConfig` global,
  then check never-worse. The apsis is searched (a rule cost 18.5 km/s where
  perihelion needs 12.1); the concentration ratio is searched and the search
  always includes **not concentrating** (`beneficiate=False`, which is not
  ratio 1.0).
- **Never-worse**: beneficiated <= raw and searched <= N = 1, row by row, max
  exactly 1.0 where it declines. A widened search making the reported answer
  worse means it optimises something other than what it reports
  (`verify.py` check 5). `selection_key` is lexicographic: profit if any
  candidate is profitable, else cost/revenue.
- **The plant feeds back into the rocket equation** (payload -> feed -> power
  -> mass -> payload), solved by fixed-point iteration in `evaluate_combo`.
  Solar falls 1/r^2; past 3.46 AU an RTG can win, capped by Pu-238 supply
  (`rtg_max_power_w`). Never price the EP array off the RTG row.
- **Tank mass scales with volume** (`tank_kg_per_L` per storage class);
  `t(R - 1) >= 1` means the tank cannot close and the candidate is infeasible.
- **Delta-v is per asteroid.** If `max_payload_kg`, `vehicle` or `propellant`
  collapse to one value across a catalog, `use_per_asteroid_dv` is off or the
  elements are not reaching Stage 4. EP needs `dv_penalty_factor`.
- **Extraction is rate-limited** by `max_mining_duration_yr`; the haul is
  derived from whichever cap binds and is **not searched**, so a binding cap
  sizes the mission (sweep it and look for the plateau).
- **`trips` is a property of the mission, not the body** (it depends on the
  stay, which depends on the ratio): never cache it per body.
- **M-types are not bare metal cores** (Psyche ~3.8-3.9 g/cm^3); do not
  restore 0.80/5.30.
- **Composition fractions sum to strictly under 1** in every real class; the
  residual is valued at a bulk-silicate floor. Check the property, never type
  the interval (it has been wrong at birth and stale since).
- **A raw refinery is dearer per kg than Stage 2's deduction** (its plant works
  a 0.25-year stay, not a fifteen-year life), so the refinery helps
  concentrating missions and hurts raw ones. Not a defect.
- **ISRU water is the water phase**, not the ice fraction
  (`_row_water_fraction`); CO2 and ammonia are not hydrolox. calc sizes an ISRU
  mission's electric stage on a placeholder load; the derivation mirrors it, and
  changing that is a model release.
- **A default run produces zero viable missions.** That is the answer, not a
  regression.

## Reading a result without fooling yourself

| quantity | it is | it is NOT |
|---|---|---|
| the objective | `total_cost_usd / gross_value_usd` | a column (there is no `cost_revenue_ratio`) |
| a cell's winner | the row minimising it | `df.iloc[0]` (the frame is sorted by `profit_usd`) |
| `r` in never-worse | lower setting over higher, e.g. benef / raw | the reciprocal |
| "median improvement" | `median(1 - r)` | `median(1/r - 1)` (1.7x larger) |

- **Quote a population median before claiming the model changed.** Winners
  move far more than populations, and an unchanged winner is not an unchanged
  cell (one release moved 1.14% of rows with the winner the same float).
- **Ask what a sample could have detected.** A clean 65-row sample cannot see a
  1% population shift; a hash says `MATCH` without saying how many rows backed
  it.
- **THE SAMPLING RULE: a sample predicts full-catalog runtime, a ratio between
  two settings, or memory to no better than a factor of ~5, in either
  direction.** Budget from a measured full run of the same cell. Never compound
  per-release ratios; a contiguous slice is worse than a stride sample; timing
  two builds in separate sessions measures the session (interleave them in one
  process). A wall clock, ratio or count is true only of the release and
  catalog it names. Runtime constants live in `MEASURED_CELL_SECONDS` (the
  cislunar cells at the current release: levels for banners) and
  `MEASURED_DEST_SECONDS` (seven destinations at one release: the only source
  for a cross-destination ratio). Their cislunar rows differ **on purpose**; do
  not "fix" one to match the other. Every printed ratio derives from them.
- **A diagnostic inherits the shape of the term it watched.** When a term
  changes, check the diagnostics still **vary**: `saturation_multiplier` is
  identically 1.0 under `capacity_cap`, `unsold_payload_kg` reads 0 since calc
  1.22.0 (the mass is in `surplus_payload_kg`). A column built by subtraction
  needs a floor (milligram), not `> 0`.
- **Survivor-property columns undercount a constraint**: a ceiling can change
  the winner while no winning row is bound.
- **Tightening a constraint can improve a searched row** because the fleet
  ladder is coarse-then-refine, not exhaustive. Settle it with a
  fixed-programme comparison (revenue is monotone there) before calling a
  defect; do not make the ladder exhaustive on a few rows' evidence.
- **`earth_surface` searched cells sit at `max_fleet_ships` on every row**: they
  are the ladder's top rung, not optima.
- **A count is not a test of a gate.** "Zero survive" is a population fact;
  test whether one wins. An unreachable branch is not a verified branch.
- **A share measured under a defect is the defect's share.** Re-measure the
  population at the current release before sizing a change by it.
- **When every mass in a cascade is off by the same fraction**, look for what
  set the payload, not the biggest term downstream. Masses agreeing to 1e-5
  under fifty differing columns means the search landed elsewhere (usually a
  dial read from the live config), not broken arithmetic.
- **When a candidate disappears, name the guard that refused it** (trace which
  `return None` fired under `sys.settrace`) before naming the term that moved
  it. Adding mass or Delta-v never makes a mission fit.

## Verification

| tool | what | notes |
|---|---|---|
| `verify.py baseline / check / invariants` | the release checks; list in its own header | full `check` ~30 min; `--skip prune parallel` ~5 min |
| `verify_docs.py` | the docs checks; list in its docstring | ~1 s; `--before OLD.md README.md MODEL.md CLAUDE.md versions.md LESSONS.md` audits a reorganisation for dropped numbers |
| `verify_stage1.py` | pinned catalog release vs data contract, and the bytes on disk | never writes the catalog |
| `verify_stage3.py` | this repo's adapter vs the installed spacecost | temp dir, no baseline |
| `tree_check.py` | disk content vs git index | run first by every harness |
| `platform_check.py` | libm/numpy/pandas against `platform_reference.json` | a library version is not a defect |
| `campaign/worked_calculation.py`, `campaign/verification_sheet.py` | derive one mission from the equations and hold it to its row | see below |

Comparing two runs (`verify.py` already does all of this; copy it rather than
writing a new harness, and read its header list of past harness bugs first):
- Print a hash **and** a column diff. When they disagree the hash is right and
  the comparator is broken; "every cell differs at once" is the tell.
- Strip **both** provenance columns, `pipeline_version` and `catalog_date`
  (midnight falls mid-run on long cells).
- In comparisons only, `read_csv(float_precision="round_trip")`. **Never** in
  Stage 4's loader, where it would move every number.
- Compare by position (frames come back sorted by the objective), treat `""`
  and NaN as equal, test text columns with `dtype.kind in "OU"` (pandas 3 reads
  them as `str`, not `object`).
- When a release adds a column, hash the **shared** column set and name it.
- Set `delivery_destination` explicitly; `mining_hardware_kg` is a config
  constant, not a column; join never-worse pairs at a **matched** row cap.
- A config field that cells can differ on joins `run_cell`'s explicit resets,
  or every later cell inherits the previous one's value.
- `verify.py` builds cells into `.verify/scratch/` (`output_dir`);
  `input_dir` is untouched. `build_profitability_catalog` writes its CSV as a
  side effect, so any harness that calls it must redirect `output_dir` or it
  replaces the live catalog.

What counts as evidence:
- **Releases are argued from bit-identity.** A refactor that reorders float
  operations changes the proof even when it changes nothing visible; these
  were measured and refused for that reason: sorting the phase table at
  source, rearranging `bracket > 0`, `pd.read_csv(engine="pyarrow")`, a faster
  CSV writer. A change that only **evicts** (bounding a pure-function memo) is
  free. `y * 365.25 * 24.0` is not `y * 8766.0`; keep the model's association.
- **A check that cannot run never says it passed**, and a skip that fires on
  every run is a check that does not exist. Ask how often it fires.
- **Feed a new check a wrong answer before trusting its clean line.** Plant the
  failing case; for a register, also plant a value-neutral literal, the one
  case older guards cannot see.
- **Registers are checked in both directions**: an entry nothing matches is a
  permission still being granted (`TYPED_OK`, check 14; `BORROWED`, check 16;
  `NOT_SHOWN`; spacecost's `TYPED`).
- **A check is only a check on what it reads.** Ask what the largest thing is
  that it could be mistaken for covering, and read whole tables, not one row.
- Never put `date.today()` on one side of a comparison and a literal on the
  other.
- Validate every anchor of a patch before editing, then edit, then write.

## Things that destroy work and say nothing

- **Stages 1-3**: see the first rule. `run_pipeline.py` asks before
  overwriting; the three fetching modules guard their own standalone runs
  (`_confirm_overwrite`, held mirrored by check 15). Typing a stage list to
  test the parser still runs the stages.
- **`campaign/run_cell.py` on a measured cell overwrites its archive**
  (`campaign/cells/<cell>.csv.gz`, gitignored, one copy). Archive a
  re-measurement with a `__calc-<ver>` suffix. Readers build exact names, so a
  suffixed archive is invisible to them: `worked_calculation.py` lists those it
  did not compare and reaches one with `--catalog <path>.csv.gz`. Never make it
  glob `campaign/cells/`.
- **Freeze the live inputs before the re-run that replaces them**
  (`campaign/stage2/mineral_value-<ver>/`, `campaign/stage3/spacecost-<ver>/`).
  A table that recorded its quotes can be rebuilt (`live_price_*` replayed as
  the live frame, network untouched); change rows by replaying, not
  re-fetching.
- **`run_cell.py` refuses** a frozen Stage 2 catalog whose stamp differs from
  the Stage 2 code.
- **A synced-folder revert** silently undoes uncommitted edits and
  `tree_check.py` stays green (content equals the index). Commit early; audit
  landed work against `origin/main`, not the working tree.

## Worked calculation and verification sheet

`campaign/worked_calculation.py` re-derives every figure of one archived
mission from the equations and compares 88+ quantities with its row.
`campaign/verification_sheet.py` renders the same derivation as a
pen-and-paper worksheet and `--check` re-evaluates every printed substitution.

- **The row decides the run, never this process.** Destination, ore state,
  market tier, depletion cap, prices, Stage 2 epoch and Stage 3 tables are read
  off the row or the file it came from (`run_setting`, `dials_in_force`,
  `run_could_read`, `transport_tables_for`); the live config is the last
  resort. Do not add `preflight()`: it would refuse the archives this exists
  to read. Every path that picks a row goes through `run_winner`, which
  attaches the file's provenance; a shortcut returning a bare row silently
  falls back to the live config.
- A run cannot read a file written after it ended: `run_could_read` compares
  dates. When the model reads a dial on the **config** and the derivation on
  the **row**, they agree at the top and diverge in the tail.
- Propellant price is recovered from the row's **outbound** cost / mass, snapped
  to the table's float where they agree. The Stage 2 pricing model is chosen by
  the table's stamp and checked against its `used in space` prices.
- `--audit` checks completeness: every non-zero column and every rate the
  derivation read (recorded, not listed) must appear on the page, pinned
  within 1% of the page's printed precision; numbers inside text cells match
  as printed. The perturbation figure it prints is what that answer is worth.
- `--sweep` derives one mission per architecture (axes from `row_shape`,
  including market, plant, capture and optional terms), traces renderer
  coverage, and reports what is not on disk. `--source` adds a cell built with
  a term on; `--max-sources 0` sweeps only named sources. State that belongs to
  one document (`RATE_LOG`) resets per document.
- A sentence asserting a value or a property of the file is a claim nothing
  executes: digits in prose go on `TYPED_OK` (check 14), model calls on
  `BORROWED` (check 16). Sections are numbered from one ordered list; each
  must emit its anchor exactly once.
- Reproduce the fixed point's stopping test term for term: the loop keeps its
  last pass, so the exit condition decides which mission you get.
- The sheet: a token's tolerance is the precision it was printed at; a
  subtraction that cancels prints operands as `repr(float)`; computed table
  cells go through `claim()`. Check a page against a row where the clamps
  **bind** (synodic cap, salvage at N = 1, the payload's four ceilings), never
  only the best case. Its part 1 ledgers every `CalcConfig` field. PDFs are
  measured at the print stylesheet's width (`report_paper`); if the page count
  does not move with `--font`, the browser is shrinking an overflow. Never edit
  the file while a sweep runs.

## Code traps a reader will re-introduce

- `_combo_can_close` and `max_return_payload_kg` are one algebra in two
  places; change one, re-run the pruned-vs-unpruned diff (`verify.py` check 2).
  The pre-filter's second stage runs at pass 1's `structure_frac`; with
  `damp_sizing_loop` on it sizes the EP stage off the **floor** (full-vehicle
  outbound load plus the empty return vehicle, less 1%), except under ISRU.
- A pre-filter proven against the loop is not proven against the problem: the
  prune and the loop can be wrong together and check 2 cannot see it.
- A damped loop must converge; an undamped one may fly its last pass. At step
  1.0 it assigns, never blends. A strict `>` on a quantity solved to sit on the
  constraint needs `launch_capacity_rtol`.
- Adding candidates to a coarse-then-refine search can make rows worse: refine
  around the best unrepaired rung too.
- `want_phase` is a short circuit inside the one walk; `totals_only` is an
  early return with `total_cost` final before it; the prologue tuple's order is
  load-bearing; `hardware_cost`, `spacecraft_book_value` and `upfront_lines`
  stay summed term by term.
- A cached `None` needs a sentinel; NaN and None normalise to one key; use
  `factorize`, not `unique` plus a dict; give each expanded row its own list;
  memo on config **values**, never `id(config)`; never memoise a warning path.
- `maxsize=None` is safe only when you can name the key space's ceiling;
  otherwise bound it.
- `AsteroidContext` holds only what does not vary with the candidate.
  Non-electric candidates skip the stage-2 solver.
- **Market ceilings never reach the sizing path**: `_cargo_water_kg` calls
  `optimal_payload_mix` inside the power solve with `caps=None`, which must stay
  bit-identical to the unbounded walk. `caps` is keyed by **market**
  (`phase_market_key`) and consumed as spent; pass a dict you own. The tiered
  walk assumes the full-price tier comes first, so `surplus_price_fraction` is
  clamped twice and refused above 1.0 by `market_config_check`; the tier ledger
  is written before the `take <= 0` skip.
- `DELIVERY_ARCHITECTURES` answers per-destination questions
  (`window_phasing_au`, asserted total). Never write a conditional that names
  one destination; ask the table.
- `destination_check`, `stamp_check` and `schema_check` are diagnostics: they
  name the stale file and the behaviour it reverts. Do not weaken them into
  generic warnings. Read Stage 4's loader row counts after a Stage 3 change.

## Correctness invariants

- Never build a merge key by stringifying a float column (`"3.0"` joins
  nothing); go through `Int64`. Read `designation` with `dtype={"designation":
  str}`; `.astype(str)` afterwards gives `"69260.0"`. Bugs whose dtype is
  inferred from the data pass on small slices and fail at scale.
- `str.contains(..., regex=False)` in every lookup.
- Never `.astype(bool)` on a column a row could leave blank (it reads `"False"`
  and NaN as True); use `_truthy(series, default=...)` or `.ne(True)`.
- TPS mass is inside the rocket-equation cascade; the return-capsule volume cap
  binds; propellant made on site is never billed at the propellant table's
  price (it pays processing energy and a plant on the rig since calc 1.32.0).
- `hardware_total_kg == mining_hardware_kg (config) + power_system_kg +
  ep_system_kg + refinery_kg + isru_plant_kg` (`verify.py` check 4). A mass
  with no price, or a price with no mass, is defect class 1: look there first.
- A reference row must describe one physical article (argon once had a
  liquid's density and a gas's zero boil-off).
- A floor applied before an add-back is not a floor on the sum.

## Adding a destination

`gto` (master v1.54.0) is the worked example; its release note in versions.md
lists every file it touched.

1. spacecost: `DELIVERY_CHAINS`, `DOWNLEG_DEPARTURE_DV_M_S`, the `TYPED`
   register for any typed burn, tests; release and repin.
2. calc: a `DELIVERY_ARCHITECTURES` row (with `window_phasing_au`), its return
   legs in the per-asteroid Delta-v table, capture Delta-v.
3. mineral_value: `_DESTINATION_NOTES`, a decided `IN_SPACE_UTILITY_BY_DESTINATION`
   row (an omission silently means the base profile), and an
   `IN_SPACE_ANNUAL_DEMAND_KG` row (asserted for in-space destinations).
4. `campaign/worked_calculation.py`, `verification_sheet.py` and
   `worked_calculation_doc.py`: the return legs and their labels.
5. `run.bat` and `run.sh` menus, and MODEL.md's destination table; check 17
   holds all three. The entry points and dashboard derive from
   `DELIVERY_DESTINATIONS`.
6. Not until a cell is measured: `MEASURED_DEST_SECONDS`, campaign `DESTS`.

## Stage 1 and Stage 3 live in other repositories

- **Stage 1 downloads a published catalog**; AsteroidCatalog builds and gates
  it. The pinned catalog release is `data-2026-10-21b`
  (`CatalogConfig.catalog_release`). Same pin, same bytes; nothing installs
  until every asset matches its sha256, manifest written last, staging in a
  fresh `mkdtemp`. `pipeline_version` there is the data contract, checked not
  stamped; moving it is a schema decision.
- **A catalog repin is a model change for the population**: baseline, repin,
  re-run a cell, report a paired median (catalog 1.5.0 moved the median body a
  third while the winner improved). New provenance label values need the two
  readers that branch on them updated (`verify_stage1.py` check 8 catches
  unknown ones).
- **Stage 3 is an adapter over spacecost, pinned to tag `v0.12.0`**, and
  Stage 2 imports `spacecost.delivery` too, so a dropped name fails a pricing
  stage first. The pin is typed in six places: `requirements.txt`,
  `_PIP_SPEC` in `modules/transportation.py` and `modules/mineral_value.py`,
  and prose in README, CITATIONS.md and this sentence. Check 7 holds them
  together.
- **A spacecost table change is four steps**: edit there, bump its version if
  a number moves, tag a release, repin here. Repin with
  `pip install --force-reinstall --no-deps` (without `--no-deps` pip upgrades
  numpy and pandas), then `py platform_check.py`. The install blocks reinstall
  a stale git-pinned package at import.
- `TransportConfig` stays here, mirrored field for field
  (`_check_config_surface()` raises); its comments are the dashboard help.
- **A regex repin rewrites history**: a version string in prose is a pin or a
  date; decide per string and read the diff.
- When a seam changes shape, sweep **both** repos for guards of the old shape;
  a private name consumed across repos needs a tested contract in the repo
  that could delete it (spacecost's `tests/test_consumer_contract.py` names
  what Stage 2 and Stage 3 reach).

## Config and docs discipline

- Configs are dataclasses instantiated once; edit the field default, never the
  instance. A field's help text is the comment block directly above it
  (stopping at a blank line) or a one-line trailing comment; a trailing comment
  cannot continue onto the next line. Check 8 fails on a non-path field with no
  help.
- **When a number changes, grep for the superseded claim**, not only the
  digits: `grep -rn "<old>" --include='*.md' .` and the same over code
  comments, `--help` text and banners. A file that derives a number in one
  place may still type it in another; grep for the value.
- **Name a list; do not state its length** unless a check enforces the count.
  The fix for a rotting number is a checker or a deletion, never a correction.
- **A reason can go stale while its fact stays true**: when the architecture
  changes, grep for the comments justifying a workaround against it.
- **A comment saying two copies must agree is a request for a checker.**
  Derive what agrees, type what does not, and assert the gap.
- **When a quantity is divided, grep every reader of the whole** and ask which
  part it meant (the ice fraction stopped being all water at calc 1.24.0).
- **A mechanical pass over every instance assumes they are one kind of thing.**
  Find the member that is not, and diff the **output** (console text included),
  not only the values.
- **A flipped default reaches every reader that infers a run from the config**,
  not only the producers; chase it into the worked calculation and the
  harnesses.
- Data sources fail softly; read the per-ticker `FAIL`/`WARN` lines before
  quoting a level, since a yfinance outage prices off reference rows and
  reports success. `metals.dev` with key `DEMO` is skipped on purpose.
- **Printed strings are ASCII** (Windows cp1252 stdout crashes on anything
  else, box drawing included). Comments, docstrings and data strings keep their
  characters. `run.bat` and `run_pipeline.py` also force UTF-8, which cannot
  move a CSV byte.

## Environment

- Windows, repos under `C:\Users\<user>\OneDrive\Documents\GitHub\`, shared
  with a second machine through OneDrive. `*-DESKTOP-PJS73RO.*` and other
  `-DESKTOP-` files are sync-conflict copies: diff them (usually the newer
  side) and delete them; never commit one. `git add -A` will commit a revert and
  a conflict copy together, so read `git show --stat`.
- `git status` can show phantom-modified files; confirm with `git diff`.
  `.githooks/drive-restat.sh` re-stats entries whose content matches the index
  (opt in with `git config core.hooksPath .githooks`). Never `git stash`. An
  unmappable `.git/index` during a sync clears on its own; do not delete it.
- Another host (Linux): `lineterminator="\r\n"` is pinned in every CSV writer
  and in `verify.py` because every committed hash is a hash of CRLF; never
  "clean it up". `asteroid_pipeline/` is gitignored, so copy it rather than
  regenerate (`run_pipeline.py --check-inputs`). Bit-identity across hosts is
  not promised; `platform_check.py` says whether hashes are comparable.

Entry points (the three that run the model import `master` by name with the
repo on `sys.path`, which the worker pool needs):

| file | runs the model | what |
|---|---|---|
| `run_pipeline.py` | yes | headless CLI; `preflight()`, `check_defaults_preset()`, overwrite prompts |
| `ui.py` | yes | Streamlit dashboard |
| `verify.py` | yes | release checks |
| `run.bat`, `run.sh` | no | launcher menus over the above; nothing may prompt once an argument is given (`set /p` hangs a scheduled job) |
| `_START HERE.vbs` | no | double-click entry; starts the dashboard with no console |
| `launch_ui.py` | no | installs the pinned quietlaunch and hands it `ui.py`; imports nothing from this project, keep it that way |
| `campaign/run_cell.py` | via subprocess | one campaign cell through `run_pipeline.py` |

Launcher and dashboard traps:
- `_START HERE.vbs`: the `_` sorts it first and is safe; `!` breaks `run.bat`
  under delayed expansion. Quote the space (`start "" wscript.exe "_START
  HERE.vbs"`).
- `launch_ui.py` is a shim. Its pin is the one `quietlaunch @ ...@vX.Y.Z`
  line in `requirements-ui.txt` (read, not retyped); the port, Tk-thread,
  hand-over and server-reuse traps live and are tested in quietlaunch. Here:
  WSH `Run` rather than `start`, so a redirected `run.bat ui` does not block.
- `ui.py`: cached fetching stages default off; the destination selector seeds
  from the catalog on disk; presets come from `run_pipeline.apply_preset`;
  search mode replaces the tabs (a widget key is its storage key); `usecols`
  intersects the header first. Altair: no `mark_bar` on a log scale (draws
  nothing), and a layered chart needs `resolve_scale(color="independent")`.
- The dashboard may run on a different interpreter from `py`
  (`.claude/launch.json` spells one out and rots); check `sys.executable`
  before concluding a package is missing.

## Measured and declined

Count the calls before optimising the callee, price the per-call cost rather
than the redundancy factor, and re-measure the remainder after taking the
cheap items; the ranking changes. Each of these looks like a win and is closed:

| item | verdict |
|---|---|
| inlining `builtins.max`, `integrity_check`'s second factorize, a `viability_only` path in `max_return_payload_kg`, the prologue hoist | each under ~2% of a run |
| Parquet instead of CSV | real (19.7 s to 2.1 s) and not taken: it changes Module 1's output contract |
| quarter ceilings (`Qm/4`) | declined: calibrating a cost model to a desired output. A capacity and a curve's scale parameter are different meanings of one float |
| `nickel-iron`'s missing market ceiling | declined until `earth_surface` is re-run |
| ISRU methalox (Sabatier, carbon route) | declined: bound by the rig cap; carbon gasification has no source |
| a GPU port | the RTX 2080 Ti is 7.6x slower than the CPU at fp64 `exp`; fp32 breaks bit-identity |
| an exhaustive fleet ladder | declined; see branch-and-bound |

The one structural item still open is **branch-and-bound on the objective**. It
needs a provably admissible bound on `selection_key`. Never approximate it: a
bound that is occasionally too tight drops winners without changing the row
count, which no check here would see.
