# Full-matrix measurement campaign - started 2026-09-09

7 destinations x {raw, beneficiated} x {search OFF (N=1), search ON} = 28 cells.

This is the SECOND full-matrix campaign.  The first ran 2026-08-23/24 on calc
`1.17.7` over five destinations and twenty cells; it is complete, and its
ledger, its frozen Stage 2 prices and its memory record are kept under
`archive-2026-08_calc-1.17.7/` with its cell archives under
`cells/archive-2026-08_calc-1.17.7/`.  Nothing in this campaign is comparable
with it cell for cell: the code, the market model, the insurance default and
the price epoch all moved in between.

Code under measurement (all stamps verified against `verify_docs.py` before start):
  catalog 1.2.0 | mineral_value 1.9.0 | transportation 1.14.0
  calc 1.21.2   | master 1.26.0

  WARNING: those are the stamps this campaign RAN ON, not the current ones.
  calc 1.22.0 landed on 2026-09-14, after the campaign finished, and moved four
  defaults: the surplus past a market ceiling sells at half price instead of
  being abandoned, and reliability, the learning curve and the cost of capital
  are off.  A cell here is reproducible only with sell_surplus_at_discount
  False, model_reliability True, model_learning_curve True and
  apply_wacc_compounding True.  A NEW campaign run today is a different
  measurement and should say so in its own header rather than being compared
  with these cells.
  master.py rebuilt from modules/, `git status` clean afterwards.
  platform_check.py: all 18 probes match the reference host, so cell hashes
  taken here are directly comparable with the ones in versions.md.

What is different from the 2026-08 campaign, and why every level moved:
  * two more destinations, `geo` and `mars_orbit`, never measured before
  * `market_model` defaults to `capacity_cap`; every 2026-08 cell is an
    `elasticity` figure
  * `charge_insurance` defaults False; every 2026-08 cell was charged it
  * Stage 3 re-run, so the tables carry the four `geo` and three `mars_orbit`
    delta-v segments that transportation 1.13.0/1.14.0 added.  The 2026-08
    tables have 26 segments and cannot price either new destination.

Inputs frozen for the whole campaign:
  Stage 1 asteroid_catalog.csv    2026-08-11  (1,555,667 rows)  NOT re-fetched:
    JPL adds bodies daily, so a rebuilt catalog is a different length and is
    comparable with nothing already measured.  It is deliberately one release
    behind (catalog 1.1.1 columns, module now 1.2.0), so `stamp_check()` says
    so on every run.  That is the deliberate-lag case its own note describes,
    not a failed write.
  Stage 3 transportation/*.csv    2026-09-09  (propellants 41, ops 44, dv 33)
    NO LONGER ON DISK IN THAT FORM.  On 2026-09-17 a direct `py
    modules/transportation.py` rebuilt them at the spacecost v0.2.0 contract:
    same rows, new stamp, and three live-priced propellant rows re-fetched
    (methalox -0.17%, kerolox +3.21%, HTP/RP-1 +4.22%).  The campaign's own
    values are recorded in versions.md under transportation v1.15.0, recovered
    from an archived cell rather than from a backup -- `outbound_prop_cost_usd
    / m_outbound_prop_kg` on the methalox rows of leo__benef__search-on IS the
    input price.  A cell of this campaign that chose a chemical propellant will
    not reproduce bit-exactly against the tables now on disk; the 11-15% of
    beneficiated rows at leo, geo, mars_orbit, mars_surface and earth_surface
    that fly methalox are the population that cares.  The three fetching
    modules refuse to overwrite unasked now.
  Stage 2 mineral_value           2026-09-09, all SEVEN destinations priced in
    one sitting, frozen into `stage2/`.  Never re-fetched during the campaign;
    `run_cell.py` copies the right one into place per cell.

  Backup of the pre-campaign inputs: `asteroid_pipeline/_inputs_backup_2026-09-09/`

## The live-price drift, measured rather than assumed

The 2026-08 campaign verified `live_price_usd_per_kg` IDENTICAL across all five
destinations.  This one cannot say that: COMEX futures were trading during the
seven fetches, and two of the five live-priced minerals ticked.

| mineral | spread across the seven | relative |
|---|---|---|
| gold | 142,199.5339 to 142,212.3910 | **9.0e-5** |
| copper | 14.8779 to 14.8790 | **7.4e-5** |
| platinum, palladium, silver | identical | 0 |

Accepted rather than fixed, deliberately.  It is the same order as the -0.004%
`leo` drift the committed record already carries and explicitly says not to
read as a regression, and three orders below the destination-to-destination
differences this matrix exists to measure.  Both alternatives are larger
methodological changes than the thing they fix: pricing off the reference table
alone abandons live prices entirely, and a price-pinning mechanism is new
config surface added mid-campaign.  The per-destination values are auditable in
`stage2/mineral_value_catalog.<dest>.csv`.

⚠️  A cross-destination claim resting on a difference finer than 1e-4 is not
supported by this campaign.  Nothing in the 2026-08 matrix came close to that.

## Layout

  `stage2/mineral_value_catalog.<dest>.csv`  the seven frozen price catalogs
  `run_cell.py <dest> <raw|benef> <off|on>`  one cell: copy Stage 2, run
      `--stages 4` only, time it, archive the output gzipped to `cells/`,
      append one row to `results.csv`
  `run_queue.py`   runs everything outstanding, resumable: it skips any cell
      already in `results.csv` with `rc == 0`.  Kill and restart freely.
  `analyse.py <dest>`  the 2x2 table plus the never-worse, mass-ledger and
      programme-structure invariants.  Do NOT run it while a cell is timing;
      in 2026-08 it inflated a wall clock by a few percent and put two spurious
      10.7-11.5 GB spikes in the memory record.
  `memwatch.py`    samples python RSS every 20 s into `memory.csv`.
  `population.py`  every per-cell POPULATION table the docs carry, from ONE
      pass over `cells/`: the rig's two bounds, the cadence, the propellant and
      vehicle shares, the market-ceiling diagnostic, the `replicated` ranks and
      the winners.  `--report` renders them from the JSON under `population/`;
      re-running a cell is not needed and not wanted.  It is the authority for
      those tables and supersedes `rig_bounds.py` and `extra_checks.py`, which
      are kept only because the 2026-08 archive's FINDINGS.md names them.
      Same caution as `analyse.py`: do not run it while a cell is timing.
      `--tag calc-1.22.0` reads cells archived under a suffix, i.e. a cell
      re-run at a later release; `analyse.py` takes the same as
      `--tag=calc-1.22.0`.  Both compose an EXACT filename rather than
      searching `cells/`, which is what keeps a re-measurement from being
      picked up as though it were one of the campaign's own cells, and the
      tag filter runs both ways so neither set can contaminate the other.
  `worked_calculation.py`  the worked derivation of ONE mission, section by
      section, every equation with its substitution under it.  The mission is
      the best case of whatever finished results are on disk, compared across
      the live Stage 4 catalog and every archived cell, so "which one" is a
      measurement rather than whichever file got passed in.  Every figure is
      re-derived from the equations and then checked column by column against
      that mission's own row; `--verify` runs the check and writes nothing,
      `--audit` adds the completeness audit below, `--pdf` renders with
      headless Chrome, `--cell` and `--designation` override the choice.  It is the only script here that imports `master`,
      and the only campaign output that is gitignored rather than committed,
      because it is generated from the run it describes.
  `verification_sheet.py`  a SECOND renderer over the same derivation, for a
      reader who wants to reproduce the answer on paper rather than read
      about it.  The narrative document explains the model; this one tags
      every input, cites the file, row and column it came from, names the
      tags each step consumes, and elides nothing.  It computes no model
      quantity of its own either: both renderers read one `build()`, so they
      cannot disagree.

      The citations are derived rather than listed.  CITATIONS.md's section 7
      says this repo does not duplicate sources, it says where they are, so
      the sheet reads them: the `notes` and `reference_year` of each
      `spacecost` row, the price-source columns of the Module 2 catalog, the
      provenance columns Stage 1 writes, and the config comment `ui_meta`
      already scrapes for the dashboard's help text.

      🚨  IT CARRIES A CHECK NOTHING ELSE IN THE REPO MAKES, AND THE CHECK
      FOUND FOUR DEFECTS ON ITS FIRST RUN.  `--check` parses every
      substitution on the page, evaluates it, and holds it to the value
      printed beside it.  That is a question about the PAGE rather than the
      model: a substitution can omit a term or round an operand past the
      point where it reproduces its own answer while every derived quantity
      is still exactly right, and the column-by-column comparison cannot see
      it.  Four lines did exactly that, three by truncating operands and one
      -- `budget - m_at` -- because the subtraction cancels five leading
      digits, so twelve significant figures in leaves seven out.  147 of 147
      match now; the two that are prose rather than arithmetic are named in
      the footer rather than passed over.  `--self-test` perturbs a printed
      value and confirms the check goes red, because a matcher nobody has
      seen fail is a matcher nobody has seen.

```
py campaign/verification_sheet.py --check    # evaluate every line, write nothing
py campaign/verification_sheet.py --pdf      # and render it
```

  `worked_calculation_doc.py`  the renderer that script writes through.  It
      decides what to say and in what order and computes no model quantity of
      its own; the prose branches on the derived shape, so a raw
      single-mission document and a beneficiated searched one are different
      documents rather than one with blanks in it.

      🚨  `SECTION_ORDER` IS THE ONE PLACE A SECTION'S NUMBER, TITLE AND
      ANCHOR LIVE, and it is worth knowing why it had to become one.  All
      three used to be typed into the `h(2, ...)` call inside the section,
      again into the contents list under a different wording, and again into
      every sentence elsewhere saying "see section 6"; three sections have
      early-return branches that repeated their own heading, so one section
      carried up to FOUR copies of its own identity with nothing holding them
      to each other.  Inserting a section renumbered the headings and left
      every cross-reference pointing one short, silently.  The number is the
      POSITION now, `sec()` writes the heading, `ref()` writes a
      cross-reference as a real link, and `document()` asserts that every
      section emitted its own anchor exactly once -- which is what catches a
      branch that forgot its heading, or kept a stale one and rendered under
      the wrong number.

  ✅  It covers every destination and every architecture the search can
  choose: seven destinations, both ore states, both programme settings,
  aerocapture and the heat shield, ISRU return propellant, chemical as well as
  electric propulsion, radioisotope power, cryogenic boil-off, all four market
  models and insurance.

  🚨  EVERY CONFIG DIAL WAS THEN AUDITED BY FLIPPING IT, because "which
  switches could make this document wrong" is a question to measure rather
  than reason about.  One 300-row cell per switch, each documented, and the
  dials sort into three groups that are worth telling apart:

    FOLLOWED   read off the ROW, so the live config cannot disagree: the
               destination, the market model, insurance, reliability, the
               learning curve, the cost of capital, the surplus flag, the
               programme search and its N, `model_tank_mass` (via
               `tank_mass_frac`), `model_eclipse_power` (via
               `array_oversize_factor`), `model_low_thrust_time` (via
               `ep_thrust_yr`), `model_launch_windows` (via
               `launch_window_wait_yr`) and, since 2026-09-18, the
               PROPELLANT PRICE (via `outbound_prop_cost_usd` over
               `m_outbound_prop_kg`).  That last one is not a dial at all,
               which is why it took longest to find: see below.
    REFUSED    named by the guard rather than approximated: an unknown
               destination, a power source that is neither solar nor RTG, the
               fallback delta-v pair, and `model_rig_service_life` off, which
               stops being a dial and becomes a different programme.
    CAUGHT     still read from the live config, every one with a compared
               column that fails loudly if it disagrees: `max_fleet_ships` and
               `programme_search_steps` (`programme_options_priced`),
               `concentration_search_steps` (`concentration_ratio`),
               `demand_elasticity` (`saturation_multiplier`),
               `surplus_price_fraction`, `model_rig_trip_limit`
               (`rig_terminal_value_usd`), and every physical scalar.

  ⚠️  `model_rig_trip_limit` is the ONE dial a row cannot settle, and the
  reason is worth knowing rather than looking for a column that would: wherever
  the calendar bound binds first, `trips_per_ship` comes out the same either
  way and `rig_trip_limit_binds` reads False in both.  The two readings differ
  only in the salvage credit.  Do not "fix" it by trying both and keeping
  whichever matches.

  A refusal or a red check is the correct outcome in every case above.  A
  document that quietly describes the wrong mission is the failure all of this
  exists to prevent.

  ✅  **AND WHICH MISSIONS IT HAS EVER BEEN RUN ON IS A MEASUREMENT NOW,
  NOT A RITUAL.** `--sweep` streams every Stage 4 output on disk once, keeps
  the cheapest mission of each distinct ARCHITECTURE, and derives a greedy
  cover of the axis values between them -- destination, ore state, programme
  size, return mode, propellant sourcing, power source, rendezvous apsis and
  electric against chemical. The axes are `row_shape`'s, so they are the ones
  the renderer branches on rather than a list somebody maintains.

```
py campaign/worked_calculation.py --sweep           # one mission per architecture
py campaign/worked_calculation.py --sweep --audit   # and audit every page it renders
```

  ✅  AND THE PAGE'S OWN BRANCHES ARE MEASURED WITH IT. Every document the
  sweep builds is rendered under a tracer, and the report names the renderer
  functions whose lines no swept mission reached. That is the coverage question
  one level in: `--audit` asks whether ONE page shows everything it computed,
  and this asks how much of the space of PAGES has ever been rendered at all.

  ⚠️  EVERY STAGE 4 OUTPUT IS CALLED `profitability_catalog.csv`, so a
  source is keyed by its PATH and labelled by its parent directory. Keying by
  name merged the live catalog with every `--source` cell into one entry and
  answered their rows out of the wrong file.

  ⚠️  A BRANCH NOTHING ON DISK CAN REACH IS STILL UNVERIFIED. Three of the
  renderer's sections belong to terms every archived cell has switched off --
  insurance, and the `unbounded` and `single_mission` market models -- so no
  sweep over `cells/` will ever render them. `--source` takes a Stage 4 output
  built with those terms ON, which is a 400-row cell written into a scratch
  directory in about a minute, and the sweep scans it ahead of everything else.

  🚨  `--max-sources` CAPS WHAT THE SWEEP DISCOVERED, NEVER WHAT YOU NAMED.
  It used to slice the whole list, and named sources come first -- so
  `--max-sources 1` with four `--source` arguments swept one of them and
  reported a clean cover of a space it had never opened. `--max-sources 0` is
  useful now: the named sources and nothing else, which skips the 1.1 GB live
  catalog and every archive, and is what makes the optional-term sweep cheap:

```
py campaign/worked_calculation.py --sweep --audit --max-sources 0 \
    --source <cell-with-insurance>/profitability_catalog.csv \
    --source <cell-with-unbounded>/profitability_catalog.csv
```

  ⚠️  BUILD THOSE CELLS WITH `output_dir` REPOINTED AND `input_dir` LEFT
  ALONE. `build_profitability_catalog` WRITES `<output_dir>/profitability_catalog.csv`
  as a side effect, so a builder that leaves that field alone replaces the live
  Stage 4 catalog with its 158-row sample; `input_dir` carries the ~868 MB of
  inputs and redirecting it makes every cell fail to LOAD instead. Reset every
  field a cell can differ on, in both directions, or the second cell inherits
  the first one's.

  🚨  EVERY CELL ON DISK WAS RUN AT `max_mining_fraction` 0.05 AND THE LIVE
  DEFAULT IS 1.0, so a sweep over archived cells wants
  `--max-mining-fraction 0.05`. Without it the derivation re-derives a haul up
  to twenty times the one the run took, the launch stack then fails against the
  vehicle, and the refusal used to blame the concentration ladder. It names the
  guard now and prints the arithmetic that points at the dial.

  🚨  AND THE OTHER DIRECTION IS THE QUIET ONE. A cap that is too LOOSE
  refuses; one that is too TIGHT still closes a mission, just a smaller one, and
  writes a confident document about it. Measured on a 158-row insurance cell
  swept at 0.05 against rows run at 1.0: 53 columns DIFFER with every MASS
  agreeing to 5.7e-05, which is a search landing elsewhere rather than
  arithmetic going wrong. `mining_cap_note` now names the dial whenever the
  row's own feed exceeds what this process is allowed to dig -- a one-sided test
  and airtight in that direction, because the run actually dug that much, so its
  cap permitted it.

  ⚠️  One `--max-mining-fraction` covers every source, so a sweep mixing
  archived cells with current ones cannot be right for both. That note is the
  compensation, not a fix.

  🚨  AND THE PAGE'S CLAIM ABOUT ITS OWN INDEPENDENCE WAS TYPED, AND
  FALSE. The Verification footer told every reader that what this derivation
  reads from the model is "reference data and table accessors". It also called
  the model's night-side derate, its synodic period and its delivered price --
  and two of those sit inside things the same sentence NAMES as written out
  here, the plant and the clock. The module docstring carried the same denial
  while `programme_ladder`'s own docstring, twelve hundred lines below,
  explained why borrowing the ladder's SHAPE is deliberate.

  Nothing could see it. Check 14 fails on any DIGIT reaching prose; a sentence
  about which functions a file calls carries none. So the derate and the
  synodic period are written out, the delivered price is compared rather than
  printed, and the claim is DERIVED: `BORROWED` is the register,
  `model_borrows` walks the file's own AST against it, and the footer prints
  what it finds. `verify_docs.py` check 16 fails on a borrow that is on no row
  AND on a row that matches no borrow -- both halves proved by planting one of
  each.

  ⚠️  WHAT IS LEFT IS DISCLOSED RATHER THAN DENIED. The ladder's rungs are
  read from the model on purpose: reproducing which programmes the search
  proposed would be a second opinion about what it offered rather than a check
  on what it concluded. Every value at every rung is priced here.

  🚨  A STAGE 3 TABLE ON DISK IS NOT THE TABLE THE RUN READ, AND THE
  PROPELLANT PRICE WAS THE LAST INPUT STILL TAKEN FROM IT. Three live-priced
  propellants were refetched on 2026-09-17, so every archived CHEMICAL mission
  stopped reproducing: on `earth_surface__raw__search-on`, 2005 TH50 came out
  **7 columns DIFFER** -- the two propellant lines by 1.660e-03 relative and
  five totals downstream of them by ~1.5e-08. The price was recoverable from
  the row all along, because a Stage 4 output carries both the cost and the
  mass, and their ratio is constant per propellant across a cell. It is read
  off the row now, the table still wins where the two agree so an unmoved cell
  stays bit-exact, and the run SAYS SO when it substitutes:

```
  propellant methalox  (LCH4 / LOX) priced off the ROW at 0.186202302606 $/kg;
             the Stage 3 table on disk now says 0.185893237684, so it has been
             refetched since this run
```

  ⚠️  THE OUTBOUND LEG, NEVER THE RETURN. Propellant made on site is billed
  at `isru_processing_usd_per_kg` and not at the propellant's price at all, so
  the return pair recovers the wrong number on exactly the missions ISRU exists
  for.

  🚨  `--designation` BYPASSED THE ONE FUNCTION THAT ATTACHES A ROW'S
  PROVENANCE. Three things are properties of the FILE and not of the row -- the
  evaluable population, its size, and whether the run had beneficiation on --
  and this path re-read the catalog with a bare `read_csv`, which attaches
  none. `run_setting` then fell through its file source to its LAST resort, the
  live config, whose `use_beneficiation` is True: a named row out of a RAW
  catalog was derived against the beneficiated purity bound, `5.28x` out on
  `best_phase_usd_per_kg`, and the page told the reader the best case beat a
  population of zero. `run_winner` picks the row either way now, so a caller
  cannot get one without the other -- and it drops a second read of a file the
  function had already loaded.

  🚨  ON ITS FIRST AUDITED RUN THE PAGE WAS CLEAN AT CISLUNAR AND AT NO
  OTHER DESTINATION. `leo` refused outright -- the derivation read an EMPTY
  delivery chain (`[]`, nothing above LEO) as a MISSING one (`None`,
  `earth_surface`, which avoids no launch) and returned 0 $/kg where Module 2
  returns 4,253. An RTG page hid the solar array it was chosen over, three
  output columns and three rates with it. A dense in-space hold rendered as
  "0.02 m3" because the volume was printed to two decimal places. And a
  chemical mission was reported incomplete for a power-processing rate no
  chemical page can show. All fixed; re-run the command rather than trusting
  this paragraph.

  ⚠️  IT HAS TO BE AFFORDABLE OR IT IS ANOTHER RITUAL. The first
  version scanned with `csv.reader`, parsing every field of every row to
  look at eight of them, and then re-streamed the whole source once per
  MISSION to fetch each row. It scans with pandas over the axis columns
  only and fetches the chosen rows in one pass per source; the rewrite was
  compared against the old one on a real archive, architecture by
  architecture, before it was trusted.

  ⚠️  A REFUSAL AND AN UNCOVERED AXIS VALUE ARE BOTH RESULTS. The guard in
  `context` declines shapes the cascade does not cover, by name, and finding
  out which those are is half of what the sweep is for; an axis value that
  exists on disk and went underived is reported rather than passed over. Both
  make the run exit 1.

  🚨  IT FOUND A DEFECT ON ITS FIRST RUN. `best_phase_usd_per_kg` came out
  61% low on an RTG, ISRU, chemical, raw mission, because the model writes that
  column from the RUN's `use_beneficiation` and the derivation read the ROW's
  own `beneficiation`. Those agree on every row except one that declined to
  concentrate inside a beneficiated run -- 15.8% of bodies, and never the
  winner, which is why a document about the best case could not see it. See
  `run_setting`, which carries the measurement: such a row is identical to the
  same body's raw row in 142 of 143 columns.

  ✅  COMPLETENESS IS MEASURED SEPARATELY, BY `--audit`, because a clean
  check says the page is CORRECT and says nothing about whether it is whole:
  a quantity that is never displayed is never compared either.  It renders
  the page, pulls every number out of it and asks two questions.  Of every
  column: does the page show it, at any unit the page is allowed to use?  Of
  every reference-table constant the derivation READ: the same.  The second
  question is the one a column audit cannot ask, because a rate is an input
  and no output column names it -- the rig's throughput, the three processing
  energies, the electric stage's per-newton and per-kilowatt figures, the
  alloy's element yields.  Between them they are what makes every displayed
  number reproducible from the page rather than taken on trust.

  ✅  THE LIST OF RATES IS RECORDED RATHER THAN TYPED.  A list of constants
  to look for would be a second copy of what the derivation reads; instead
  every reference-table read is logged as it happens, so a rate added to the
  cascade joins the audit with no edit here.

  🚨  AND THE THIRD QUESTION IS ABOUT THE PROSE, WHICH NEITHER OF THE OTHER
  TWO CAN SEE.  Every FIGURE on the page is derived and compared; the
  sentences around them are ordinary writing, and two of them asserted values
  nothing derived -- that Module 1's taxonomy fractions "sum to between 0.73
  and 0.96", and that solar and a radioisotope source "cross near 3.46 AU".
  Both were correct when written, neither was ever executed, and the first
  pair had already been WRONG at birth elsewhere in this repo.  A column audit
  cannot see either, because no column is missing: the page is complete and
  one of its sentences is simply untrue.

  Both derive now, off `taxonomy_fraction_span()` and `crossover_au()`, and
  what stops the third one is a register: any digit reaching `para` or `note`
  has to be on `TYPED_OK` with a reason it cannot rot, and a register row
  nothing matches is a finding too, because an allowlist nobody reads has
  stopped being a decision.  ⚠️  It reads the RENDERER'S SOURCE rather than
  the page, because a derived number and a typed one render identically --
  which is the whole difficulty -- and it covers prose rather than arithmetic,
  since a substitution exists to show `365.25 * 24 * 3600` and flagging that
  would be asking the page to stop being a derivation.

  ✅  SO IT RUNS IN `verify_docs.py` AS CHECK 14 AS WELL, in about a second
  and with no catalog, no `master` and no run.  A check that can only fire
  after a three-minute build against 868 MB of inputs is a check CI cannot
  have, and this is the one half of the audit that does not need any of it.

  🚨  AND THE AUDIT MEASURES ITSELF ON EVERY RUN, which is not decoration.
  Its first version tested only that a page number was consistent with a
  column at the precision it was printed to, and that is not sufficient: a
  bare `0` on the page is consistent with any cost in the model once the
  audit may look in millions and billions.  Moving every number by a third
  left 99 of 100 columns still matching, i.e. a check that could not fail.
  A match must now pin the value to within a percent or be exact, and the
  `matcher` line reports what the same perturbation does today -- one figure
  is the answer and the one below it is what the answer is worth.

Per cell: `profitability_catalog.csv` is archived gzipped to `cells/` and one
row is appended to `results.csv`.

⚠️  `CAMPAIGN_ROWS` caps rows for smoke-testing the ledger and archive plumbing
in a minute rather than in hours.  A capped run is NOT a campaign measurement;
delete its ledger row and its archive afterwards.

## A campaign must outlive the session that starts it, AND its console

🚨  **This killed the campaign twice, two days apart, and the second time the
obvious fix was already in place.**

| | exit code | what it was | what killed it |
|---|---|---|---|
| 2026-09-09 | `0x40010004` DBG_CONTROL_BREAK | a child of an agent background shell | session teardown took the whole process tree |
| 2026-09-11 | `0xC000013A` STATUS_CONTROL_C_EXIT | a scheduled task running `cmd /c ...` | a Ctrl+C aimed at an unrelated foreground command, four minutes in |

⚠️  **The second is the instructive one.**  Task Scheduler re-parented the queue
to the scheduler service, which is what "detached" is normally taken to mean,
and the kill still arrived.  **What propagates a console control event is the
CONSOLE, not the parent**, and the task's `cmd.exe` had attached to the shared
one.  Re-parenting a process does not move its console.

⚠️  **Both look exactly like a pipeline crash and neither is one.**  The cell
log carries no traceback, no `MemoryError` and no exit message -- Stage 4's
banner and then silence, where a real failure says something -- and `memwatch`
puts system RSS at 36-40 GB of 68.6 GB, so it was not memory.  The tells are a
literal `^C` written into the queue log, and an exit code that names a console
event rather than a fault.  Read the exit code before re-running anything: this
is *a broken checker looks exactly like a broken release*, one level out.

✅  **`_supervisor.py` is the fix, and it is about the console, not the
parent.**  It spawns the queue with `DETACHED_PROCESS` (no console exists for an
event to arrive on) plus `CREATE_NEW_PROCESS_GROUP` (out of the group a Ctrl+C
is broadcast to), then exits immediately -- holding the child would give the
scheduled task something to wait on, which is the console-owning process the
whole thing exists to avoid.  Stage 4 already writes to a per-cell file and the
queue writes to the handle the supervisor opens, so nothing needs a console.

The scheduled tasks invoke `python.exe _supervisor.py <target>` DIRECTLY.  There
is deliberately no `.bat` and no `cmd /c`: the wrapper was the console owner.

```
schtasks /run /tn economicspace_campaign      REM start or resume; idempotent
schtasks /run /tn economicspace_memwatch
schtasks /query /tn economicspace_campaign
```

✅  **Verified by reproducing the kill, not by reasoning about it.**  With the
supervisor in place, a foreground command was deliberately run past its timeout
so it was moved to the background -- the same transition that killed the
2026-09-11 start -- and `run_queue`, `run_pipeline` and `memwatch` were all
still alive afterwards.

Resuming needs no arguments and no state: `run_queue.py` skips every cell
already in the ledger with `rc == 0`, so re-running the task picks up exactly
where it stopped, and the failed row is what triggers the retry -- do not tidy
it away.  That property is why a two-day outage cost two days rather than the
campaign.

⚠️  **A watcher is not the campaign.**  Anything that merely reports progress
may die with a session; the thing that must not is the queue.  Never launch the
queue from a monitor, a notebook, an agent's background shell, or anything that
puts a `cmd` between it and the scheduler.

### The third interruption was the machine, and it is the one worth the trigger

🚨  **2026-09-11 16:33: the HOST went down**, mid-cell, and the campaign sat
idle five hours because nothing restarts it after a reboot.

⚠️  **The signature is different from the two console kills above, and that is
how you tell them apart without guessing.**  A console kill writes a literal
`^C` into the queue log, and `run_queue` survives long enough to print
`!! cell failed (rc=...)`.  This wrote neither: the queue log stops mid-cell,
`memory.csv` stops in the same minute, and every process is gone at once.  A
signature that includes the WATCHER dying is a machine event, not a process
event.  Confirmed in the event log rather than inferred:

```
Kernel-Power 41  the system has rebooted without cleanly shutting down first
6008             the previous system shutdown at 4:16:06 PM was unexpected
```

⚠️  That 16:16 is Windows' last-flushed liveness stamp, which LAGS the crash;
the logs put it at 16:33.  Do not read it as the time of death.  There is no
bugcheck and no dump, so it was a power loss or a hard hang, and nothing
attributes it to this workload: the 2026-08 campaign ran 26 h on this machine,
and `memwatch` had RSS at 36-40 GB of 68.6 GB.

✅  **Both tasks carry an `AtLogOn` trigger now**, with a two-minute delay, so a
reboot resumes the campaign on its own.

⚠️  **Register it user-scoped or it fails with Access denied.**
`New-ScheduledTaskTrigger -AtLogOn` with no `-User` means *any* user, which
needs elevation; `-User "$env:USERDOMAIN\$env:USERNAME"` does not.

🚨  **AND THE TRIGGER NEEDS A SINGLE-INSTANCE GUARD, WHICH THE SCHEDULER CANNOT
PROVIDE.**  It fires on an ordinary log off and on too, and a second queue would
race the first for one `profitability_catalog.csv` and one ledger: a corrupted
cell that still reports `rc 0`, which is defect class 5 wearing a scheduler's
clothes.  `MultipleInstances IgnoreNew` does **not** cover it, because the
supervisor exits as soon as it has spawned, so the TASK is never running when
the trigger fires again -- only the detached grandchild is.  `_supervisor.py`
therefore checks PROCESSES, not the scheduler.

⚠️  **Match the target as the script being RUN, not as a word on a command
line.**  The supervisor is invoked as `_supervisor.py run_queue.py`, so its own
cmdline contains the target, and `py` compounds it by spawning `python.exe`
with identical arguments -- so a naive substring test finds the launcher,
excluding self is not enough, and the guard refuses to start anything at all.
Measured, not predicted: the first version reported a different phantom pid on
each call.

### Pausing without losing the in-flight cell

A cell writes NOTHING until it finishes, so killing the queue mid-cell throws
that whole cell away -- up to 8 h of it.  `_pause.ps1` freezes the process tree
instead, which frees every core immediately and keeps the work:

```
powershell -File campaign\_pause.ps1            REM freeze
powershell -File campaign\_pause.ps1 -Resume    REM thaw and carry on
```

✅  **Suspending costs almost no memory, which is the opposite of what you would
expect.**  Windows trims a suspended process's working set, so pausing
`leo benef+search` 5.7 h in left the 16-process tree holding **0.4 GB** rather
than the ~25 GB it had resident.  CPU went to zero on all 15 measured
processes, verified by comparing `TotalProcessorTime` across a 10 s interval
rather than by watching a CPU graph.

⚠️  **Processes are found by command line, never by a remembered pid** -- a pid
does not survive the pause it is meant to outlive.

⚠️  **A reboot while suspended loses the in-flight cell**, exactly as killing it
would; the queue restarts that cell from the beginning.  Everything already in
`results.csv` with `rc == 0` is safe on disk either way.

⚠️  **The pause disarms the `AtLogOn` trigger and the resume re-arms it.**  A
paused campaign with a live reboot trigger would restart itself behind you at
the next logon, which is the whole failure the trigger exists to cause on
purpose.

### ⚠️  One wall clock in the ledger is not comparable: `leo__benef__search-on`

`results.csv` records **27,817 s** for that cell.  It is a true wall clock and a
misleading one: the campaign was suspended with `_pause.ps1` while the cell was
5.7 h in, and `run_cell.py` times with `time.time()` around the subprocess, so
the frozen period is inside the measurement.

**The pause was 74.7 min**, measured from the gap in `memory.csv` rather than
estimated -- `memwatch` is suspended by the same call, so its own sampling gap
IS the pause:

```
last sample before   2026-09-12 20:13:19
first sample after   2026-09-12 21:27:59
```

| | |
|---|---|
| recorded `wall_s` | 27,817 s |
| pause | ~4,482 s |
| **comparable compute** | **~23,335 s (6.48 h)** |
| ratio against the 2026-08 cell | **1.52x**, not the 1.82x the raw figure gives |

✅  **The ledger is deliberately NOT edited.**  `wall_s` means wall time and
that is what it holds; what the pause breaks is *comparability*, not the
measurement.  Correcting it in place would put a derived number into the file
that records observations, and would hide that the cell was interrupted at all.

🚨  **Use 23,335 s when quoting this cell beside any other**, and do not put
27,817 s in a runtime table.  Every other cell in this campaign ran
uninterrupted.

⚠️  **The general trap: a suspend-based pause silently corrupts any duration
measured across it.**  Anything timed with a wall clock, here and in
`run_queue.py`'s `elapsed` column, is inflated by the pause; CPU time and the
model's own outputs are untouched.  Prefer pausing BETWEEN cells when the
in-flight cell is cheap enough to lose.
