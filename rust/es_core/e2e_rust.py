# -*- coding: utf-8 -*-
"""End-to-end: does ECONOMICSPACE_RUST=1 change a single byte of Stage 4?

    python rust/es_core/e2e_rust.py OUT_DIR ROWS WORKERS [run_pipeline flags...]

OUT_DIR must already hold Stage 1-3 outputs (it is written to: never point it
at the repo's own asteroid_pipeline/).  Runs Stage 4 three times, Python,
Rust, Python, interleaved in one session so the timings compare like with
like (the sampling rule in CLAUDE.md), and requires all three
profitability_catalog.csv files to be byte-identical.  The two Python runs
also prove the comparison is meaningful: a nondeterministic output would
fail here before it could hide a Rust difference.

Exit 0 only if the bytes match.  Prints wall-clock per run.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


def run(out_dir, rows, workers, flags, rust):
    env = dict(os.environ)
    env.pop("ECONOMICSPACE_RUST", None)
    if rust:
        env["ECONOMICSPACE_RUST"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, "-X", "utf8", os.path.join(REPO, "run_pipeline.py"),
           "--stages", "4", "--rows", rows, "--workers", workers,
           "--output", out_dir] + flags
    src = os.path.join(out_dir, "profitability_catalog.csv")
    # Stage 4 can exit 0 without writing (no viable evaluation, an empty
    # frame), which would leave the previous run's file to be hashed as this
    # one's: remove it first, and require that this run wrote a new one.
    if os.path.exists(src):
        os.remove(src)
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8")
    dt = time.perf_counter() - t0
    if p.returncode != 0:
        print(p.stdout[-3000:], p.stderr[-3000:])
        raise SystemExit("run failed (rust=%s)" % rust)
    if not os.path.exists(src) or os.path.getsize(src) == 0:
        print(p.stdout[-3000:], p.stderr[-3000:])
        raise SystemExit("run exited 0 but wrote no %s (rust=%s)" % (src, rust))
    dst = os.path.join(out_dir, "e2e_%s_%d.csv" % ("rust" if rust else "py", int(t0)))
    shutil.copyfile(src, dst)
    with open(dst, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    return dt, digest, dst


def main():
    out_dir, rows, workers = sys.argv[1:4]
    flags = sys.argv[4:]
    results = []
    for rust in (False, True, False):
        dt, h, path = run(out_dir, rows, workers, flags, rust)
        results.append((rust, dt, h))
        print("  %-6s %8.1f s  sha256 %s  (%s)"
              % ("rust" if rust else "python", dt, h[:16], os.path.basename(path)))
    hashes = {h for _, _, h in results}
    py_t = [dt for r, dt, _ in results if not r]
    rs_t = [dt for r, dt, _ in results if r]
    print("  python mean %.1f s, rust %.1f s, speed-up %.2fx (whole Stage 4 run)"
          % (sum(py_t) / len(py_t), rs_t[0], (sum(py_t) / len(py_t)) / rs_t[0]))
    if len(hashes) == 1:
        print("E2E PASS: all three catalogs byte-identical")
        return 0
    print("E2E FAIL: catalogs differ")
    return 1


if __name__ == "__main__":
    sys.exit(main())
