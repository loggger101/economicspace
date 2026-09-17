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
  `worked_calculation_doc.py`  the renderer that script writes through.  It
      decides what to say and in what order and computes no model quantity of
      its own; the prose branches on the derived shape, so a raw
      single-mission document and a beneficiated searched one are different
      documents rather than one with blanks in it.

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
               `ep_thrust_yr`) and `model_launch_windows` (via
               `launch_window_wait_yr`).
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
