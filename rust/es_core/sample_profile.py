# -*- coding: utf-8 -*-
"""Sampling profile of a Stage 4 run: where the time goes, without cProfile's
per-call overhead (which inflated functions called millions of times and
misdirected the first port; see README).

    python rust/es_core/sample_profile.py [--rust] OUT_DIR ROWS STACKS.txt [run_pipeline flags...]

A background thread snapshots the main thread's stack every ~1 ms
(`sys._current_frames`) and writes one line per sample: the stack, outermost
first, as `file:function:line` frames joined by ';'.  `analyse_profile.py`
reads it.  Only the main thread runs the model (`--workers 1` is forced).

Caveat, stated rather than hidden: the sampler needs the GIL, which a Rust
call holds until it returns, so time inside Rust is charged to the Python
line that made the call.  Read Rust time by the calling line, never as zero.
"""
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
args = sys.argv[1:]
rust = args and args[0] == "--rust"
if rust:
    args = args[1:]
    os.environ["ECONOMICSPACE_RUST"] = "1"
else:
    os.environ.pop("ECONOMICSPACE_RUST", None)
out_dir, rows, dump, flags = args[0], args[1], args[2], args[3:]
sys.path.insert(0, REPO)
os.chdir(REPO)
# A finer switch interval lets the sampler in more often; it does not change
# what the model computes.
sys.setswitchinterval(0.0005)

main_id = threading.get_ident()
stop = threading.Event()
samples = []


def frame_stack(f):
    out = []
    while f is not None:
        c = f.f_code
        out.append("%s:%s:%d" % (os.path.basename(c.co_filename), c.co_name, f.f_lineno))
        f = f.f_back
    out.reverse()
    return ";".join(out)


def sampler():
    while not stop.is_set():
        time.sleep(0.001)
        f = sys._current_frames().get(main_id)
        if f is not None:
            samples.append((time.perf_counter(), frame_stack(f)))


import run_pipeline           # noqa: E402
sys.argv = ["run_pipeline.py", "--stages", "4", "--rows", rows,
            "--workers", "1", "--output", out_dir] + flags
th = threading.Thread(target=sampler, daemon=True)
t0 = time.perf_counter()
th.start()
try:
    run_pipeline.main()
except SystemExit:
    pass
stop.set()
th.join()
wall = time.perf_counter() - t0
with open(dump, "w", encoding="utf-8") as fh:
    fh.write("# wall %.3f s, %d samples, rust=%s\n" % (wall, len(samples), bool(rust)))
    for _t, s in samples:
        fh.write(s + "\n")
print("SAMPLED %d stacks over %.1f s (rust=%s) -> %s" % (len(samples), wall, bool(rust), dump))
