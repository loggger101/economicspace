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
  `stage3/{launch_vehicles,propellants,operational_costs}.csv`  the spacecost
      0.3.x Module 3 tables this campaign flew, frozen on 2026-09-24 when the
      live ones moved to spacecost v0.4.0.  Read by `worked_calculation.py`
      for any row whose run ended before the live tables were written; three
      propellant prices in them are the 2026-09-17 refetch, and the outbound
      price is recovered from the row regardless.
  `run_cell.py <dest> <raw|benef> <off|on>`  one cell: install Stage 2,
      run `--stages 4`, time it, archive the output gzipped to `cells/`,
      append one row to `results.csv`.  For this campaign it copied the
      frozen `stage2/` table and refused one whose stamp was not the code's;
      since master v1.59.0 it installs the destination's table from the
      pinned price release, and stops the cell if that fails.
  `run_queue.py`   runs everything outstanding, resumable: it skips any cell
      already in `results.csv` with `rc == 0`.  Kill and restart freely.
  `quietqueue_pin.py`  the job runner is
      [quietqueue](https://github.com/loggger101/quietqueue), split out of
      `run_queue.py`, `_supervisor.py`, `memwatch.py` and `_pause.ps1`, which
      are shims now: each holds this campaign's values (`DESTS`, `CELLS`, the
      cell naming, `results.csv`, the logs, the task name) and hands them over.
      The pin is the one line in `requirements-campaign.txt`; this file holds
      the installed copy to it, and a mismatch is refused with the pip command,
      never installed.  Run it alone to see what is installed.
  `analyse.py <dest>`  the 2x2 table plus the never-worse, mass-ledger and
      programme-structure invariants.  Do NOT run it while a cell is timing;
      in 2026-08 it inflated a wall clock by a few percent and put two spurious
      10.7-11.5 GB spikes in the memory record.
  `memwatch.py`    samples python RSS every 20 s into `memory.csv`; `--once`
      writes one row and stops.
  `population.py`  every per-cell POPULATION table the docs carry, from ONE
      pass over `cells/`: the rig's two bounds, the cadence, the propellant and
      vehicle shares, the market-ceiling diagnostic, the `replicated` ranks and
      the winners.  `--report` renders them from the JSON under `population/`;
      re-running a cell is not needed and not wanted.  It is the authority for
      those tables and supersedes `rig_bounds.py` and `extra_checks.py`, which
      are kept only because the 2026-08 archive's FINDINGS.md names them;
      they read that campaign's cells, `cells/archive-2026-08_calc-1.17.7/`.
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
  `cargo_golden.py`  the seam into `spacevalue.cargo` (calc 1.33.0 on).
      `record DIR` hashes thirteen small cislunar cells, one per cargo branch
      `verify.py`'s four cells never reach (each market model, phases off,
      detailed phases off, refinery off, the surplus wall); `check DIR` holds a
      later tree to them, and `--plant NAME` proves the check can fail.
      `--fixtures FILE` also records the golden fixture spacevalue's
      `tests/test_cargo_golden.py` replays: re-record it only at a calc
      release that moves a number.  It builds cells through `verify.py`, so it
      reaches `master` the same way and writes only under `.verify/scratch/`
      and `DIR`.
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

      It carries three checks on the PAGE rather than the model, because a
      substitution can omit a term or round an operand past reproducing its
      own answer while every derived quantity is still right.  `--check`
      evaluates every substitution and holds it to the value printed beside
      it; it requires every input to name a file and a row, column or field;
      and it traces every number on the page to a tagged input, a step's
      value, an operand or a `claim()`ed table cell, at the precision it is
      printed to.  The five tables that are the document re-run at another
      setting (the fixed point's earlier passes, the concentration ladder,
      the programme ladders) are excused by name on the page and in the
      count.  `--self-test` perturbs a printed value and confirms the check
      goes red.

      Its last part, "Backing, row by row", gives every tagged row an entry:
      where it was read from, the published source it rests on (the
      sentences of its citation that name one, quoted), and how the page
      verifies it (which steps spend it, whether its substitution
      re-evaluates, which of the run's columns it equals).  An input nothing
      outside the repo stands behind (a setting, a judgement, an
      unreferenced constant, a value not measured for this body) is marked
      **(needs backing)**, as is a step that spends one; the flag is printed
      on the row too, and `--check` holds the two in step.  A source the
      installed spacecost release has withdrawn is refused even where the
      archived table the run read still cites it.

      It is set for A4 and prints in black: the page count follows the TABLE
      font, not the body font, `--font` takes that trade, nothing is
      truncated, screen furniture is hidden by the print rules
      (`print_furniture()`), and `monochrome()` refuses a non-neutral colour
      or a fill.  `--print-test` lays the page out as the printer does, so
      clipping is measured rather than assumed.

```
py campaign/verification_sheet.py --check       # every line, every origin, every number
py campaign/verification_sheet.py --pdf         # and render it
py campaign/verification_sheet.py --pdf --font 8.6   # larger type, more pages
py campaign/verification_sheet.py --print-test  # the page as the printer lays it out
```

  `worked_calculation_doc.py`  the renderer that script writes through.  It
      decides what to say and in what order and computes no model quantity of
      its own; the prose branches on the derived shape, so a raw
      single-mission document and a beneficiated searched one are different
      documents rather than one with blanks in it.

      `SECTION_ORDER` is the one place a section's number, title and anchor
      live: `sec()` writes the heading, `ref()` writes a cross-reference as a
      real link, and `document()` asserts every section emitted its own anchor
      exactly once.

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
  `--max-sources` caps what the sweep DISCOVERED, never what you named, so
  `--max-sources 0` sweeps only the named sources and skips the live catalog
  and every archive:

```
py campaign/worked_calculation.py --sweep --audit --max-sources 0 \
    --source <cell-with-insurance>/profitability_catalog.csv \
    --source <cell-with-unbounded>/profitability_catalog.csv
```

  ⚠️  BUILD THOSE CELLS WITH `output_dir` REPOINTED AND `input_dir` LEFT
  ALONE. `build_profitability_catalog` WRITES `<output_dir>/profitability_catalog.csv`
  as a side effect, so a builder that leaves that field alone replaces the live
  Stage 4 catalog with its 158-row sample; `input_dir` carries the gigabytes of
  inputs and redirecting it makes every cell fail to LOAD instead. Reset every
  field a cell can differ on, in both directions, or the second cell inherits
  the first one's.

  🚨  EVERY CELL ON DISK WAS RUN AT `max_mining_fraction` 0.05 AND THE LIVE
  DEFAULT IS 1.0, so a sweep over archived cells wants
  `--max-mining-fraction 0.05`. Without it the derivation re-derives a haul up
  to twenty times the one the run took, the launch stack then fails against the
  vehicle, and the refusal used to blame the concentration ladder. It names the
  guard now and prints the arithmetic that points at the dial.

  A cap that is too TIGHT still closes a mission, just a smaller one, so
  `mining_cap_note` names the dial whenever the row's own feed exceeds what
  this process may dig. One `--max-mining-fraction` covers every source, so a
  sweep mixing archived and current cells cannot be right for both.

  ⚠️  WHAT THE DERIVATION BORROWS FROM THE MODEL IS DERIVED, NOT TYPED.
  `BORROWED` is the register, `model_borrows` walks the file's own AST against
  it, and the footer prints what it finds; `verify_docs.py` check 16 fails on a
  borrow on no row and on a row matching no borrow. The programme ladder's
  rungs are borrowed on purpose: every value at every rung is priced here.

  ⚠️  THE PROPELLANT PRICE IS READ OFF THE ROW, from the OUTBOUND leg's cost
  over its mass, because three live-priced propellants were refetched on
  2026-09-17 and a Stage 3 table on disk is not the table an archived run
  read. The table still wins where the two agree, so an unmoved cell stays
  bit-exact, and the run says so when it substitutes. Never the return leg:
  propellant made on site is not billed at the propellant's price.

  ⚠️  A REFUSAL AND AN UNCOVERED AXIS VALUE ARE BOTH RESULTS. The guard in
  `context` declines shapes the cascade does not cover, by name, and finding
  out which those are is half of what the sweep is for; an axis value that
  exists on disk and went underived is reported rather than passed over. Both
  make the run exit 1.

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

  The prose has its own check: a digit reaching `para` or `note` must be on
  `TYPED_OK` with a reason it cannot rot, and a register row nothing matches is
  a finding too. It reads the renderer's source, not the page, so it runs as
  `verify_docs.py` check 14 with no catalog and no run. The audit reports on
  every run what perturbing every number by a third does to its own matcher, so
  a check that could not fail would show.

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
parent.**  It starts the queue with no console at all and exits at once; the
mechanism and its tests are quietqueue's `supervise`.  Stage 4 already writes to
a per-cell file and the queue writes to the queue log, so nothing needs a
console.

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
clothes.  `MultipleInstances IgnoreNew` does **not** cover it (the supervisor
exits as soon as it has spawned, so the task is never running when the trigger
fires again), so the guard checks PROCESSES.  How it tells the queue from its
own launcher -- the first version reported a different phantom pid on each call
and started nothing -- is quietqueue's `already_running`, tested there.

### Pausing without losing the in-flight cell

A cell writes NOTHING until it finishes, so killing the queue mid-cell throws
that whole cell away -- up to 8 h of it.  `_pause.ps1` freezes the process tree
instead, which frees every core immediately and keeps the work:

```
powershell -File campaign\_pause.ps1            REM freeze
powershell -File campaign\_pause.ps1 -Resume    REM thaw and carry on
```

The freezing is quietqueue's `pause.ps1`; this file passes it the campaign's
`-Match` patterns and `-TaskName`, which `Get-Help campaign\_pause.ps1 -Full`
lists.

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
purpose.  On a machine without that task (`economicspace_campaign`) the
pause and resume say so and leave the scheduler alone.

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
