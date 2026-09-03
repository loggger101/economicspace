# Running this pipeline on the DGX Spark

Notes for moving the measurement campaign off the Windows reference host and
onto a DGX Spark (GB10, aarch64, Ubuntu-based DGX OS), optionally driven
through NVIDIA AI Workbench.

The short version: **the code runs there, three things that would have broken
it are fixed, and one thing cannot be guaranteed by anyone and has to be
measured instead.** `platform_check.py` measures it in about ten seconds, and
you should run it before spending a day on a campaign.

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
| no POSIX entry point | repo root | `run.bat` and `Dashboard.vbs` are the only launchers |

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
```

`setup` builds `.venv` and installs `requirements.txt` plus the UI extras. For
reproduction work install the pinned set instead, which is what every committed
number was measured on:

```bash
./.venv/bin/python -m pip install -r requirements-lock.txt
```

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

## Running the campaign

The queue is resumable. It skips every cell already recorded with `rc == 0`, so
killing it costs at most the in-flight cell.

```bash
./run.sh campaign --list          # show what is outstanding, run nothing
./run.sh campaign                 # run everything outstanding
./run.sh campaign --only cislunar leo
```

Before the first cell, copy the frozen Stage 2 catalogs across with the repo.
They are committed under `campaign/stage2/` and are **never re-fetched**;
`run_cell.py` copies the right one into place per cell. Re-running Stage 2 or
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

### Memory

Peak RSS across the twenty measured cells ran 8.2 GB to 10.4 GB, against a
128 GB unified pool on the Spark, so memory is not a constraint. Two apparent
peaks of 11.54 and 10.74 GB in the record are measurement contamination from an
analysis process that overlapped the run, not the pipeline.

If the Spark is running the campaign inside a container with a memory limit,
set it well above 16 GB. `campaign/memwatch.py` samples RSS if you want the
curve.

## One correction to CLAUDE.md

CLAUDE.md's Environment section says the reference host runs **Python 3.14
(3.14.6)** and that "3.13 is no longer installed at all". Both halves are
wrong, and the section was edited into that state on 2026-09-02 by the commit
`4e4bcfb`, whose message describes the change as fixing the interpreter
version.

On the reference host today:

```
py -0
 -V:3.13 *        Python 3.13 (64-bit)
 -V:Astral/CPython3.11.16 CPython 3.11.16 (64-bit)

py -3.14 -c "import sys"
No suitable Python runtime found
```

`py` resolves to **3.13.9**, and 3.14 is not installed. This matters here
specifically: provisioning the Spark to match the documented interpreter would
have meant matching a machine that does not exist, and interpreter version is
one of the few things that has already invalidated a measured figure in this
project. The `Dockerfile` and `requirements-lock.txt` pin 3.13.9, which is what
the numbers were actually measured on.
