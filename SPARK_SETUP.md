# Running this pipeline on the DGX Spark

Notes for moving the measurement campaign off the Windows reference host and
onto a DGX Spark (GB10, aarch64, Ubuntu-based DGX OS), optionally driven
through NVIDIA AI Workbench.

The short version: **the code runs there, everything that would have broken it
is fixed, one thing cannot be guaranteed by anyone and has to be measured
instead, and one thing is not broken at all but will still stop you on the
first day.** Count the table below rather than trusting a number in this
sentence; it said "three things" above four rows until 2026-09-03, which is the
counts-in-prose failure CLAUDE.md catalogues.

Three commands, in this order, and none of them takes longer than a minute:

```bash
./run.sh setup       # build the environment
./run.sh platform    # does this host's arithmetic match the reference host
./run.sh inputs      # are the CSVs Stage 4 reads even on the disk
```

The second is the thing that cannot be guaranteed, and it answers in about ten
seconds instead of twenty-six hours. The third is the thing that is not broken:
`asteroid_pipeline/` is gitignored, so a fresh clone has the code and none of
the ~868 MB the model reads. See
[the inputs git does not carry](#the-inputs-git-does-not-carry).

## What was already portable

Worth stating, because it is most of the surface and none of it needed
touching:

| thing | why it already works |
|---|---|
| paths | every one goes through `os.path.join`; no literal separators anywhere |
| the worker pool | asks for `mp.get_context("spawn")` explicitly rather than inheriting the platform default, so Linux behaves exactly as Windows does |
| encoding | every `print` in the four modules is pure ASCII, and every file open names its encoding |
| line endings in the repo | `.gitattributes` pins `*.py` to LF, so a Linux checkout is byte-identical to the Windows one |
| the Python floor | only the walrus operator is newer than 3.8, so nothing here needs a recent interpreter |
| dependencies | pandas, numpy, pyarrow, yfinance, tqdm and streamlit all ship manylinux aarch64 wheels |
| `launch_ui.py` | already branches on `os.name` and already degrades when tkinter is absent, which is what a headless box has |

## What was broken, and is now fixed

| what | where | what would have happened |
|---|---|---|
| the interpreter was hardcoded as `py` | `campaign/run_cell.py`, `campaign/run_queue.py` | the campaign runner would not start at all; `py` is the Windows launcher |
| output directories assumed to exist | `campaign/run_cell.py` | `campaign/cells/` is gitignored, so a fresh clone dies on the archive step AFTER paying for the whole cell |
| the CSV line terminator followed the platform | the four writers, and `verify.py` | see below; the dangerous one |
| no POSIX entry point | repo root | `run.bat` and `_START HERE.vbs` are the only launchers |
| printed instructions said `py` | `run_pipeline.py`, `verify.py`, `modules/catalog.py` | the message telling you which stage to run next named the Windows launcher, on the host that most needs the advice |

### The line terminator, which is the dangerous one

`pandas.to_csv` defaults `lineterminator` to `os.linesep`. Every cell hash in
`versions.md` was computed on Windows, over CRLF text. The same build on Linux
writes LF, so **a byte-perfect run would have reported DIFFER on every cell**,
with every float identical and nothing wrong with the model.

That is this project's most expensive recurring failure arriving in a new
costume. `verify.py`'s header already carries eleven harness bugs, three of
which produced a wrong conclusion that was written down before being caught,
and three of the last five are the same symptom from three different causes.
A broken comparator looks exactly like a broken release.

It is pinned to CRLF now rather than LF, because CRLF is what the committed
hashes are OF. On Windows the pin is a provable no-op:

```
default sha : 5fc52123ed1ecc3a
pinned  sha : 5fc52123ed1ecc3a   <- identical
LF      sha : 9f6e314f49dc64ef   <- what Linux would have produced
```

## The one thing that cannot be guaranteed

`math.exp`, `math.log` and `math.cos` are the platform's C library, and numpy
picks SIMD kernels per architecture. **None of them is required by IEEE 754 to
be correctly rounded**, so glibc on aarch64 and the Windows UCRT on x86-64 are
allowed to disagree in the last bit, and sometimes do.

This is not a corner of the model. The rocket equation is `math.exp(dv / ve)`,
and `estimated_mass_kg`, which is what the entire ranking runs on, comes out of
`np.power(10.0, -H / 5.0)`. A one ULP difference there is the same class of
thing as the pyarrow CSV engine that was measured at 4.8x and rejected for
moving that column by 1e-13 relative.

No edit fixes this. What you can do is find out in ten seconds instead of
twenty-six hours:

```bash
python platform_check.py
```

It hashes the raw IEEE bit patterns of every transcendental the model calls,
over the model's own argument ranges, and compares them against
`platform_reference.json`, recorded on the reference host. `math.sqrt` is
included as a control, because IEEE 754 *does* require correct rounding for
sqrt, so a mismatch there means something far more basic is wrong.

### If the probe says the arithmetic matches

Cell hashes produced on the Spark are directly comparable with the ones in
`versions.md`. Nothing further to think about.

### If the probe reports libm divergence

The Spark's results are still correct. They are just not bit-comparable with
the Windows record, so:

- **Re-baseline on the Spark** (`python verify.py baseline --tag spark`) and
  every comparison *within* that host stays exact, which is what `verify.py`
  is actually for.
- **Compare across hosts on values with a tolerance**, not on hashes. The
  headline objective is `total_cost_usd / gross_value_usd`; agreement to ~12
  significant figures is what a last-bit libm difference looks like, and
  anything worse than that is a real difference worth chasing.
- **Do not re-measure the committed cells on the Spark and file the deltas as
  regressions.** That is the mistake this file exists to prevent.

## Setup

Three paths. They are listed in the order I would actually use them.

### Bare virtualenv, recommended

Simplest, fastest, and the closest thing to the reference host. Nothing in this
pipeline benefits from a container.

```bash
git clone <your-remote> economicspace
cd economicspace
./run.sh setup
./run.sh platform
./run.sh inputs
```

`setup` builds `.venv` and installs **`requirements-lock.txt`**, which is what
every committed number was measured on. That is the default rather than the
loose list because the reason to stand this up on a second host is to reproduce
a number, and numpy picks its SIMD kernels per release as well as per
architecture.

If a pinned wheel does not exist for aarch64, `setup` says so and falls back to
the loose set rather than failing. It asks pip for `--only-binary`, so a
missing wheel fails in seconds instead of spending forty minutes compiling
pyarrow from source and then failing; and a locally built extension would not
be the artefact the numbers were measured against anyway, so at that point the
pin has already failed. A working loose install
is worth more than a broken pinned one; what matters is that you are told, and
`./run.sh platform` is what turns "different versions" into a measurement.
`./run.sh setup --loose` asks for the loose set deliberately.

The three commands answer three separate questions, and they are cheap in that
order: can this host build the environment, does its arithmetic agree with the
reference host, and are the files Stage 4 reads even on the disk.

**The venv is not optional on Ubuntu 24.04**, which is the one thing here that
is a distribution property rather than a preference. `master.py` pip-installs
anything in `_MASTER_REQUIRED` that is missing, at import, and it does so with
`check_call`, so a failure is an exception before the first stage. Recent
Debian and Ubuntu mark the system interpreter externally managed (PEP 668) and
refuse exactly that install. Inside `.venv` the question does not arise, and
`run.sh` prefers `.venv/bin/python` over anything on PATH for this reason.

### Docker

Use this if you want the environment pinned harder than pip can pin it, or if
Workbench is going to drive a container anyway.

```bash
docker build -t asteroid-pipeline .
docker run --rm -it --shm-size=2g \
    -v "$PWD/asteroid_pipeline:/work/asteroid_pipeline" \
    -v "$PWD/campaign:/work/campaign" \
    asteroid-pipeline ./run.sh platform
```

`--shm-size` is not decoration. Docker defaults `/dev/shm` to 64 MB, and the
`spawn` context's synchronisation primitives are POSIX semaphores that live
there. The probe's spawn check is what tells you whether this host got it
right, which is why it is a separate check rather than folded into the libm
ones.

### NVIDIA AI Workbench

Workbench is a container manager with a project UI on top. It will run this
fine, and it is worth being clear about what it does and does not add:

| it does | it does not |
|---|---|
| pin and rebuild the environment reproducibly | make anything faster; this workload is CPU-only fp64 |
| give you a JupyterLab and a browser terminal on the Spark | help with the GPU, which is measured as the wrong tool here |
| manage the remote connection from this machine | change any number the pipeline produces |

The safe way to set it up, rather than hand-writing a project spec:

1. In Workbench, **create a new project** on the Spark context, choosing a
   Python base environment. Let Workbench generate `.project/spec.yaml` itself;
   that file's schema is tied to the Workbench version and a hand-written one
   is a good way to get a project it refuses to open.
2. Add this repository as the project's git remote, or clone it into the
   project directory.
3. Point the environment at `requirements-lock.txt`, or set the project's
   custom container to this repo's `Dockerfile`.
4. In the project's settings, **raise shared memory** above the default. This
   is the same `/dev/shm` issue as the Docker path.
5. Open a terminal in the project and run `python platform_check.py`.

There is no CUDA layer in the `Dockerfile`, deliberately. The GPU question was
measured rather than assumed: on the reference machine's card, fp64 `exp` over
40 M elements ran **7.6x slower** on the GPU than on the CPU, because consumer
and workstation parts run fp64 at a small fraction of fp32, and GB10 is the
same shape of part. fp32 is 1.6x faster and unusable, because every
verification here is a bit-identity check. The workload is also the wrong
shape: branchy scalar Python with early exits, a fixed-point loop, and a
knapsack with a `sorted()` in it.

## The inputs git does not carry

**This is the one that will stop you, and it stops you before anything else
does.** The whole of `asteroid_pipeline/` is gitignored, because everything in
it is regenerated per run, so a fresh clone has the code, the frozen Stage 2
prices under `campaign/stage2/`, and **none of the roughly 868 MB that Stage 4
actually reads**:

| file | stage that writes it | size |
|---|---|---|
| `asteroid_catalog.csv` | 1 | 823 MB |
| `mineral_value_catalog.csv` | 2 | 12 KB |
| `transportation/launch_vehicles.csv` | 3 | 14 KB |
| `transportation/propellants.csv` | 3 | 27 KB |
| `transportation/delta_v_segments.csv` | 3 | 6 KB |
| `transportation/operational_costs.csv` | 3 | 28 KB |

Ask before you queue anything:

```bash
./run.sh inputs
```

It prints each file with its size or `[MISSING]`, exits 2 if any is absent, and
runs no stage and fetches nothing. The list is `preflight`'s own, not a second
copy of it.

Copy them from the host that built them:

```bash
rsync -avP <reference-host>:<repo>/asteroid_pipeline/ ~/economicspace/asteroid_pipeline/
```

**Regenerating them instead is not the same thing, and the difference is
silent.** Stage 1 re-fetches from JPL, which adds bodies daily, so the catalog
comes back a different length; Stage 2 and Stage 3 re-fetch live prices. The
run that follows is perfectly valid and is comparable with nothing already
measured, which is the whole point of moving the campaign rather than starting
a new one. `run_pipeline.py` refuses a Stage 4 run whose inputs are missing
rather than dying inside the loader an hour later, so the failure is cheap; it
is only expensive if you answer it by re-running Stage 1.

## Running the campaign

The queue is resumable. It skips every cell already recorded with `rc == 0`, so
killing it costs at most the in-flight cell.

```bash
./run.sh campaign --list          # show what is outstanding, run nothing
./run.sh campaign                 # run everything outstanding
./run.sh campaign --only cislunar leo
```

The queue is the **twenty** cells of the 2026-08 campaign: five destinations
times raw/beneficiated times search off/on. `mars_orbit` and `geo` are in the
model and are **not in the queue**, and adding them is not a one-line edit to
`DESTS`: there is no frozen Stage 2 catalog for either under `campaign/stage2/`,
and making one means a live Stage 2 run at today's metal prices, which is not
the 2026-08-23 pricing the other twenty share. Those eight cells are a decision
about methodology, not a portability gap, so they are left out of this file
deliberately.

The Stage 2 catalogs the queue does use travel with the repo: they are
committed under `campaign/stage2/`, are **never re-fetched**, and `run_cell.py`
copies the right one into place per cell. The rest of what a cell reads does
not travel with the repo at all; see [the inputs git does not carry](#the-inputs-git-does-not-carry). Re-running Stage 2 or
Stage 3 to "check something" overwrites the only copy of its CSV and
permanently invalidates every baseline you hold. That has happened twice on the
reference host, both times from a throwaway command.

### Worker count

The campaign was measured at 12 workers, which is the reference host's core
count, so 12 is what the wall clocks in `campaign/results.csv` mean and it
stays the default. GB10 has 20 cores, 10 Cortex-X925 plus 10 Cortex-A725:

```bash
CAMPAIGN_WORKERS=20 ./run.sh campaign
```

**Worker count cannot move a result.** `verify.py` check 3 holds serial and
parallel to the same hash, and chunks are consumed with `imap`, which yields in
submission order. What it moves is the wall clock, so a ledger row measured at
a different width is a valid cell with a time that is not comparable to the
committed ones.

Do not read across from the reference host's timings either way. The cores are
a different microarchitecture at a different clock, and this project's own
sampling rule is that runtime does not extrapolate: four full-catalog
predictions have been wrong from a sample, in both directions, by up to a
factor of five. Measure one cheap cell on the Spark and scale from that.

### Disk

Budget **~10 GB** for a full twenty-cell run, which is more than the inputs and
is the part that is easy to miss:

| | size |
|---|---|
| the inputs Stage 4 reads | 868 MB |
| `profitability_catalog.csv`, rewritten per cell | 350-500 MB |
| `campaign/cells/`, one gzipped archive per cell | 8.1 GB for twenty |

`campaign/cells/` is gitignored and regenerable, so it is the thing to delete
if the disk gets tight; the measurements taken from those archives live in
`campaign/results.csv` and `campaign/FINDINGS.md`, which are committed. Running
out part way through is survivable rather than costly, because the queue skips
every cell already recorded `rc == 0` and loses at most the in-flight one.

### Memory

Peak RSS across the twenty measured cells ran 8.2 GB to 10.4 GB, against a
128 GB unified pool on the Spark, so memory is not a constraint. Two apparent
peaks of 11.54 and 10.74 GB in the record are measurement contamination from an
analysis process that overlapped the run, not the pipeline.

If the Spark is running the campaign inside a container with a memory limit,
set it well above 16 GB. `campaign/memwatch.py` samples RSS if you want the
curve.

## The dashboard, over ssh

The Streamlit dashboard is the same one Windows gets. `ui.py` drives the
pipeline **in-process**, imports nothing platform-specific and spawns no
subprocess, so there is no port of it and no second version to keep in step.

```bash
./run.sh ui             # port 8501
./run.sh ui 9000        # or any other port
```

What differs is the way the server is started, and only because a Spark
reached over ssh has no desktop:

| | Windows | Spark |
|---|---|---|
| started by | `run.bat ui`, which hands off to `_START HERE.vbs` | `./run.sh ui`, in the foreground |
| window | a small Tk control window, no console | none; the terminal you started it in |
| stopped by | the control window's button | Ctrl-C |
| reached at | `localhost:8501`, opened for you | this host's LAN address, printed at start |

`launch_ui.py` is what supplies the Windows half, and it is not used here: it
needs a display for the control window, and a headless box has none. Nothing
in it is on the path a run takes.

`0.0.0.0` is a bind address and not an address to type, which is the commonest
way this goes wrong. `./run.sh ui` prints the addresses that will actually
resolve from your laptop, and if none of them loads, the port is closed:

```bash
sudo ufw allow 8501/tcp
```

The alternative, which needs no firewall change at all and is what I would use
over a home network, is to forward the port down the ssh session you already
have and then open `localhost:8501` on the laptop:

```bash
ssh -L 8501:localhost:8501 <user>@<spark>
```

### Surviving the ssh session

Both the dashboard and a campaign run in the foreground, and closing the ssh
session sends them a hangup. That is the one convenience the Windows launcher
has that a terminal does not: `_START HERE.vbs` starts a detached process with
its own control window, and there is nothing to detach from here. Use `tmux`,
which is the same answer for both and is the reason not to build a second
launcher:

```bash
tmux new -s spark          # start, or: tmux attach -t spark
./run.sh campaign          # or ./run.sh ui
```

Ctrl-B then D detaches and leaves it running; `tmux attach -t spark` picks it
back up from anywhere, including after a reboot of the laptop. A twenty-cell
campaign is a day of work and the queue is resumable, so a dropped connection
costs at most the in-flight cell either way, but watching it is easier than
re-reading a log.

**The dashboard defaults every cached stage to off except Stage 4**, which
fetches nothing. That is deliberate and it matters more here than at home: a
tick in the wrong box re-prices Stage 2 against live quotes and overwrites the
only copy of the catalog you just spent an hour copying over.

## The interpreter, which CLAUDE.md had wrong

**Fixed in CLAUDE.md on 2026-09-03; this section is the record of why it
mattered here rather than a live correction.** From 2026-09-02 its Environment
section said the reference host runs **Python 3.14 (3.14.6)** and that "3.13 is
no longer installed at all". Both halves were wrong:

```
py -0
 -V:3.13 *        Python 3.13 (64-bit)
 -V:Astral/CPython3.11.16 CPython 3.11.16 (64-bit)

py -3.14 -c "import sys"
No suitable Python runtime found
```

It is worth keeping because it is the failure this whole exercise is about,
one layer up. Provisioning a second host to match the documented interpreter
would have meant matching a machine that does not exist, and interpreter
version is one of the few things that has already invalidated a measured figure
in this project (the `builtins.max` row of CLAUDE.md's "Measured and declined"
was re-measured from ~6x to 1.2-2.4x for exactly that reason). The wrong number
had also grown an alarm beneath it telling the reader that every performance
figure in the file predated the running interpreter. That is now retracted.

The `Dockerfile` and `requirements-lock.txt` pin **3.13.9**, which is what the
numbers were actually measured on, and `platform_check.py` prints the running
version beside the reference host's on every run. Three copies that derive it,
against one sentence that typed it.
