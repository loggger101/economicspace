# Container image for running the pipeline on the DGX Spark (aarch64 Ubuntu).
#
# Also the base image to point NVIDIA AI Workbench at, if the project is driven
# from there; see SPARK_SETUP.md for why Workbench is optional here and what it
# does and does not buy on this workload.
#
# THERE IS NO CUDA IN THIS IMAGE, DELIBERATELY.  The GPU question was measured
# rather than assumed and the answer is in CLAUDE.md: on the reference machine's
# card, fp64 `exp` over 40 M elements ran 7.6x SLOWER on the GPU than on the
# CPU, because consumer and workstation Blackwell/Turing parts run fp64 at a
# small fraction of fp32.  GB10 is the same shape of part.  fp32 is 1.6x faster
# and unusable, because every verification in this project is a bit-identity
# check.  The workload is also the wrong shape: branchy scalar Python with early
# exits, a fixed-point loop and a knapsack with a `sorted()` in it.  Adding a
# CUDA layer here would add gigabytes and mislead the next reader into thinking
# something in this repo uses it.
#
#     docker build -t asteroid-pipeline .
#     docker run --rm -it \
#         --shm-size=2g \
#         -v "$PWD/asteroid_pipeline:/work/asteroid_pipeline" \
#         -v "$PWD/campaign:/work/campaign" \
#         asteroid-pipeline ./run.sh platform
#
# `--shm-size` is not decoration.  Docker defaults /dev/shm to 64 MB, and the
# worker pool asks for the `spawn` context, whose synchronisation primitives are
# POSIX semaphores living there.  `platform_check.py`'s spawn probe is what
# tells you whether this host got it right, and it is the reason that probe
# exists as a separate check rather than being folded into the libm ones.

# python:3.13 is multi-arch and resolves to linux/arm64 on the Spark.  The minor
# version is pinned to the reference host's 3.13.9: CLAUDE.md's Environment
# section claims 3.14.6, and that claim is wrong -- `py -0` on the reference
# machine lists only 3.13 and an unrelated 3.11, and 3.14 is not installed at
# all.  Matching the DOCUMENTED interpreter would have meant matching a machine
# that does not exist.
FROM python:3.13.9-slim-bookworm

# tini so Ctrl-C reaches the worker pool rather than orphaning it: a campaign
# cell is hours long and killing it is a normal thing to do.  The queue is
# resumable and loses at most the in-flight cell, but only if the children
# actually die.
RUN apt-get update \
 && apt-get install --no-install-recommends -y tini ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /work

# Requirements copied on their own first so a source edit does not invalidate
# the pip layer; the install is the slow half on aarch64, where a wheel that is
# missing has to be built rather than downloaded.
COPY requirements-lock.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir -r requirements-lock.txt

COPY . .

# The campaign runner writes here and gitignores campaign/cells, so a fresh
# clone has no directory to write into.  run_cell.py creates them too; this is
# belt and braces for the case where the volume is mounted empty.
RUN mkdir -p campaign/logs campaign/cells asteroid_pipeline

# 20 cores on GB10 (10 Cortex-X925 + 10 Cortex-A725).  Worker count cannot move
# a result -- verify.py check 3 holds serial and parallel to the same hash -- so
# this is a wall-clock dial only, and a ledger row measured at a width other
# than the campaign's 12 is a valid cell with a time that is not comparable.
ENV CAMPAIGN_WORKERS=20 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["./run.sh"]
