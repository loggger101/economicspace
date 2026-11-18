"""verify.py check 8 under the Rust ladder: the same audit as Python mode.

Check 8 wraps calc's Python functions.  The Rust ladder prices a rung's cost
tail itself unless a market ceiling binds, so it hands those totals to
`calc._ES_LADDER_HOOK`.  This holds check 8's counts in Rust mode to Python
mode's EXACTLY (combos, solves, rungs, ladders, capped sales, and both planted
catches) on two small searched cells; a hook that misses a rung, or counts one
twice, moves `rungs`.  A count both modes get wrong together is check 8's own
business, proven by its planted floor.

    python check8_guard.py parity REF.json [--plant nohook|half] [--ladder-only]

REF.json caches the Python-mode counts (built when missing).  Exit 0 when the
Rust leg passes check 8 and every count matches; 1 otherwise.
  --plant nohook   the ladder never receives the hook (a build that ignores it)
  --plant half     the hook sees every other total (a build that drops some)
  --ladder-only    calc imported in Python mode with only `_ES_LADDER` swapped
                   for the installed es_core's, which is how a PLANTED es_core
                   (refused by calc's import guard) gets here
Both plants, and the `planted_hook_defect` build under --ladder-only, must
exit 1.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
# Small enough for a gate step, big enough that every count is in the
# thousands: raw rows are cheap, beneficiated ones are not.
CELLS = (("raw+search", 40), ("benef+search", 12))
# What must be equal across the modes; `rust_*` exist only in Rust mode.
SAME = ("combos", "prunable", "solves", "rungs", "key", "cost", "gross",
        "payload", "planted", "unbounded", "ladders", "sales", "ceiling",
        "planted_ceiling")


def counts(rust: str, plant: str) -> dict:
    """Run check 8 on CELLS in this process; {cell: stats}."""
    sys.path.insert(0, REPO)
    os.chdir(REPO)
    os.environ["ECONOMICSPACE_RUST"] = "1" if rust == "full" else "0"
    import verify  # noqa: E402
    m = verify.load_master()
    calc = sys.modules["modules.calc"]
    if rust == "ladder":
        import es_core
        calc._ES_LADDER = es_core.ProgrammeLadder()
    if plant:
        real = calc._ES_LADDER

        class Proxy:
            """The real ladder, with the hook dropped or thinned."""

            def run(self, **kw):
                hook = kw.pop("rung_hook", None)
                if plant == "half" and hook is not None:
                    kw["rung_hook"] = lambda totals: hook(totals[::2])
                return real.run(**kw)

            def __getattr__(self, name):
                return getattr(real, name)

        calc._ES_LADDER = Proxy()
    if rust != "none":
        assert calc._ES_LADDER is not None
    else:
        assert calc._ES_LADDER is None
    report = {}
    ok = True
    for name, cap in CELLS:
        ok &= verify.check_bound(m, [name], report, eval_row_cap=cap)
    report["_ok"] = int(ok)
    return report


def child(rust: str, plant: str = "") -> dict:
    """`counts` in a fresh interpreter (the mode is fixed at calc's import)."""
    env = dict(os.environ)
    env.pop("ECONOMICSPACE_RUST", None)
    cmd = [sys.executable, "-X", "utf8", os.path.abspath(__file__), "_child", rust, plant]
    out = subprocess.run(cmd, cwd=REPO, env=env, stdin=subprocess.DEVNULL,
                         capture_output=True, text=True)
    sys.stdout.write("".join(l + "\n" for l in out.stdout.splitlines()
                             if not l.startswith("JSON ")))
    line = [l for l in out.stdout.splitlines() if l.startswith("JSON ")]
    if out.returncode != 0 or not line:
        print(out.stderr[-3000:])
        raise SystemExit("check8_guard: the %s leg did not finish" % rust)
    return json.loads(line[-1][5:])


def main(argv) -> int:
    if argv[0] == "_child":
        print("JSON " + json.dumps(counts(argv[1], argv[2] if len(argv) > 2 else "")))
        return 0
    assert argv[0] == "parity", __doc__
    ref = argv[1]
    plant = argv[argv.index("--plant") + 1] if "--plant" in argv else ""
    rust = "ladder" if "--ladder-only" in argv else "full"
    if os.path.exists(ref):
        py = json.load(open(ref))
        print("python leg: cached", ref)
    else:
        print("python leg:")
        py = child("none")
        if py["_ok"]:
            json.dump(py, open(ref, "w"))
    print("rust leg (%s%s):" % (rust, ", plant " + plant if plant else ""))
    rs = child(rust, plant)
    good = bool(py["_ok"]) and bool(rs["_ok"])
    for name, _cap in CELLS:
        diff = [k for k in SAME if py[name][k] != rs[name][k]]
        good &= not diff and rs[name]["rust_rungs"] > 0
        print("PARITY %-13s rungs py %d rust %d (%d priced in Rust alone) | %s"
              % (name, py[name]["rungs"], rs[name]["rungs"], rs[name]["rust_rungs"],
                 "MATCH" if not diff else "DIFFER " + ",".join(
                     "%s %d/%d" % (k, py[name][k], rs[name][k]) for k in diff)))
    print("CHECK8 PARITY %s (python check 8 %s, rust check 8 %s)"
          % ("PASS" if good else "FAIL", "ok" if py["_ok"] else "FAILED",
             "ok" if rs["_ok"] else "FAILED"))
    return 0 if good else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
