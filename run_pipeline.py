# -*- coding: utf-8 -*-
"""Headless command-line front end for the asteroid profitability pipeline.

    py run_pipeline.py --preset quick
    py run_pipeline.py --destination cislunar --raw --no-search --rows 5000
    py run_pipeline.py --stages 4 --preset full

This is what `run.bat` drives, and it is a thin wrapper: every knob it exposes
is a field on one of the four config dataclasses, set through MASTER_CONFIG
before the stage builders are called.  It adds no model behaviour of its own.

DELIBERATELY NOT IN `modules/`.  `build_master.py` concatenates that directory
into `master.py` from four explicit paths and asserts a header/footer shape per
module; this is a consumer of the built `master.py`, exactly as `ui.py` and
`verify.py` are.

THREE THINGS IT HAS TO GET RIGHT, all of them traps this repo has already hit:

  1. `import master` BY NAME with the repo on sys.path.  Loading it through
     spec_from_file_location + exec_module works in serial and then fails in
     the worker pool -- master never lands in sys.modules under its own
     __name__, `_spawn_environment`'s `own` resolves to None, and every worker
     executes THIS FILE as __main__ instead.  calc v1.17.4's harness hit
     exactly that and re-ran itself once per core.
  2. `if __name__ == "__main__":` around everything.  Windows has no fork, so
     a spawned worker re-imports the main module; without the guard it re-runs
     the pipeline once per core.
  3. `delivery_destination` written through the MASTER_CONFIG property, never
     onto a sub-config.  Stage 2 decides what a kilogram sells for and Stage 4
     decides the architecture that puts it there; setting them apart prices the
     cargo at a depot while paying to land it in Utah.

ON THE PRESETS.  The pipeline's own defaults are the full 1.55 M-row catalog,
beneficiated, with the programme search on, at earth_surface -- measured at
13,581 s (3.8 h) in the 2026-08-24 campaign; see README.md's Results.
That is the right default for the model and a hostile default for someone who
has just double-clicked something, so `--preset` names three runs by what they
cost, and `--preset full` is the one that reproduces the pipeline's own
defaults exactly.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import io
import os
import sys
import time
from datetime import datetime, timedelta

REPO = os.path.dirname(os.path.abspath(__file__))


def _force_utf8_stdout() -> None:
    """Survive a redirected stdout on Windows, whatever reaches it.

    Windows picks cp1252 for a redirected stdout, so `py run_pipeline.py >
    run.log` -- or any pipe -- used to die on the first print with
    UnicodeEncodeError, at master.py's own "PROFITABILITY PIPELINE" banner,
    before a single row was evaluated.

    THAT IS FIXED AT SOURCE NOW: every print in modules/*.py is pure ASCII, so
    the banners cannot trip this.  What is left is everything the source does
    not control -- tqdm's progress bars, a traceback quoting a non-ASCII path,
    and DATA reaching stdout (an asteroid designation, a propellant `notes`
    field).  Those are why this stays.

    `errors="replace"` is the load-bearing half: a glyph nothing can encode
    must never take down a run that is hours in.  It runs at import, i.e.
    BEFORE master.py is imported and starts printing.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass          # already detached, or not a text stream


_force_utf8_stdout()

# Runtime notes on each preset.  The timings are order-of-magnitude, read off
# the measured cells in README.md's Results; the row cap is what makes them
# differ.
PRESETS = {
    "quick": dict(
        rows=400, raw=True, search=False, asteroids=20_000,
        blurb="400-row stride sample, run-of-mine ore, single mission "
              "(minutes once the catalog is cached)",
    ),
    "standard": dict(
        rows=20_000, raw=True, search=False, asteroids=0,
        blurb="20,000-row stride sample of the full catalog, run-of-mine ore, "
              "single mission (tens of minutes)",
    ),
    "full": dict(
        rows=0, raw=False, search=True, asteroids=0,
        blurb="THE PIPELINE DEFAULTS -- every row, beneficiated, programme "
              "search on (1.6 h at cislunar to 3.8 h at earth_surface, "
              "measured 2026-08-24)",
    ),
}

# `full` is the one preset that overrides nothing: its four values are the
# dataclass defaults verbatim, which is what makes it the slow one. Asserted
# at startup against the dataclasses rather than trusted, so that a default
# flipped in a module cannot leave this claim standing while it stops being
# true -- the failure mode CLAUDE.md calls a stale claim in prose.
#
# It is NOT the default preset -- that is `quick`, on the --preset flag. This
# names the preset that IS the pipeline's own defaults, which is a different
# thing, and running the two names together is how someone reads "the default"
# off a banner and means the other one.
PIPELINE_DEFAULTS_PRESET = "full"

STAGE_NAMES = {
    1: "catalog (downloads ~500 MB on a cold run)",
    2: "mineral value",
    3: "transportation costs",
    4: "profitability (the long one)",
}


def load_master():
    """Import the built master.py in the one way the worker pool tolerates.

    See trap 1 in the module docstring.  The assert is what turns a silent
    fan-out of this script into a failure that names itself.
    """
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        import master as m
    assert sys.modules.get("master") is m and m.__spec__ is not None, (
        "master must be imported BY NAME with the repo on sys.path -- see "
        "_spawn_environment in calc.py"
    )
    return m


def human(seconds: float) -> str:
    return str(timedelta(seconds=int(seconds)))


def nonneg_int(text):
    """An int >= 0, for the three caps where 0 already means "no cap".

    Argparse's plain `type=int` accepts a negative, and a negative row cap is
    not rejected downstream -- it is MISREAD. `eval_row_cap = -5` is truthy and
    `len(df) > -5` is true, so Stage 4 enters the capping branch and then either
    raises deep inside numpy (`stride`, the default) or, with
    `eval_row_sampling = "head"`, quietly evaluates every row but the last five.
    Asking for a five-row smoke test and getting an hours-long full run is the
    quiet-wrong-answer shape this repo keeps finding; refuse it at the flag.
    """
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not a whole number" % text)
    if value < 0:
        raise argparse.ArgumentTypeError(
            "%r is negative; use 0 for no cap" % text)
    return value


def parse_stages(text, parser):
    """Digits 1-4, comma- or space-separated. Anything else is a typo.

    Previously any character outside 1-4 was silently dropped, so `--stages 45`
    ran Stage 4 alone and said nothing about the 5 -- the user asked for
    something this program does not have and got a plausible-looking run
    instead of an error.
    """
    cleaned = text.replace(",", " ").split()
    seen, unknown = set(), []
    for chunk in cleaned:
        for ch in chunk:
            if ch in "1234":
                seen.add(int(ch))
            else:
                unknown.append(ch)
    if unknown:
        parser.error(
            "--stages %r contains %s, which is not a stage. Use the digits "
            "1-4, e.g. 4 or 234." % (text, ", ".join(repr(c) for c in
                                                     sorted(set(unknown)))))
    if not seen:
        parser.error("--stages %r names no stage in 1-4" % text)
    return sorted(seen)


def _loaded_master():
    """The already-imported master module.

    `build_parser` runs after `load_master()`, so this is a dict lookup rather
    than an import.  It asserts instead of falling back to a literal on
    purpose: a hand-typed default here would be a SIXTH copy of a number this
    project has already shipped stale once, and a missing import is a
    programming error worth hearing about, not worth papering over with a
    figure that cannot be re-measured."""
    m = sys.modules.get("master")
    assert m is not None, (
        "build_parser() ran before load_master(); the --help text quotes "
        "master.MEASURED_CELL_SECONDS and has nowhere to read it from"
    )
    return m


def _benef_ratio() -> float:
    return _loaded_master().beneficiation_cost_ratio(False)


def _search_ratio() -> float:
    return _loaded_master().programme_search_cost_ratio(False)


def build_parser(destinations) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_pipeline",
        description="Run the asteroid mining profitability pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="presets:\n" + "\n".join(
            "  %-9s %s" % (k, v["blurb"]) for k, v in PRESETS.items()
        ),
    )
    p.add_argument("--preset", choices=sorted(PRESETS), default="quick",
                   help="starting point for every other flag (default: quick)")
    p.add_argument("--stages", default="1234",
                   help="which stages to run, as digits, e.g. 4 or 234 "
                        "(default: 1234). Skipped stages reuse the CSVs "
                        "already in the output directory.")
    p.add_argument("--destination", choices=sorted(destinations),
                   help="where the mined material is sold. Sets Stage 2 and "
                        "Stage 4 together, which must always agree.")
    p.add_argument("--rows", type=nonneg_int,
                   help="Stage 4 row cap, 0 = every row (stride-sampled "
                        "across the whole catalog, not the first N)")
    p.add_argument("--asteroids", type=nonneg_int,
                   help="Stage 1 fetch cap per source, 0 = all 1.55 M")
    p.add_argument("--workers", type=nonneg_int,
                   help="worker processes for Stage 4, 0 = auto")
    p.add_argument("--output",
                   help="output directory (default: ./asteroid_pipeline)")

    ore = p.add_mutually_exclusive_group()
    ore.add_argument("--raw", dest="raw", action="store_true",
                     help="fly run-of-mine ore (~%.1fx faster than concentrate)"
                          % _benef_ratio())
    ore.add_argument("--beneficiated", dest="raw", action="store_false",
                     help="concentrate the ore before flying it")
    p.set_defaults(raw=None)

    prog = p.add_mutually_exclusive_group()
    prog.add_argument("--search", dest="search", action="store_true",
                      help="search programme scale: fleet x campaigns "
                           "(~%.1fx slower)" % _search_ratio())
    prog.add_argument("--no-search", dest="search", action="store_false",
                      help="price one mission per asteroid (N = 1)")
    p.set_defaults(search=None)

    p.add_argument("--yes", "-y", action="store_true",
                   help="skip the confirmation prompt on a long run")
    return p


def resolve(args) -> dict:
    """Preset first, then any explicit flag laid on top of it."""
    settings = dict(PRESETS[args.preset])
    settings.pop("blurb")
    for key in ("rows", "asteroids", "raw", "search"):
        if getattr(args, key) is not None:
            settings[key] = getattr(args, key)
    return settings


def declared_default(config_obj, field_name):
    """The value the dataclass DECLARES for a field, not the value set on it.

    Read from `dataclasses.fields` rather than hardcoded, so that flipping a
    default in a module -- which is exactly what calc v1.17.0 did to
    `use_beneficiation` and `optimise_programme_scale` -- shows up here on the
    next run instead of rotting into a wrong label. This file's own copy of the
    defaults would be one more count-spelled-out-in-prose waiting to go stale.
    """
    for f in dataclasses.fields(type(config_obj)):
        if f.name == field_name:
            if f.default is not dataclasses.MISSING:
                return f.default
            if f.default_factory is not dataclasses.MISSING:   # type: ignore
                return f.default_factory()                     # type: ignore
    return None


def check_defaults_preset(cfg) -> None:
    """Verify `full` still IS the defaults instead of merely saying so.

    Shouts on stdout rather than raising: a labelling drift should not block a
    run, but it must not be silent either. Same shape as Stage 4's
    `destination_check()`, and written because this repo's recurring failure is
    a claim that outlived the thing it described.
    """
    expected = {
        "rows":      declared_default(cfg.calc,    "eval_row_cap"),
        "asteroids": declared_default(cfg.catalog, "jpl_limit"),
        "raw":   not declared_default(cfg.calc,    "use_beneficiation"),
        "search":    declared_default(cfg.calc,    "optimise_programme_scale"),
    }
    actual = {k: v for k, v in PRESETS[PIPELINE_DEFAULTS_PRESET].items()
              if k != "blurb"}
    if actual == expected:
        return
    print()
    print("  WARNING: preset %r is labelled 'THE PIPELINE DEFAULTS' and no "
          "longer matches them." % PIPELINE_DEFAULTS_PRESET)
    for k in sorted(expected):
        if actual.get(k) != expected[k]:
            print("     %-10s preset says %r, dataclass default is %r"
                  % (k, actual.get(k), expected[k]))
    print("     A default was flipped in a module. Update PRESETS in "
          "run_pipeline.py.")


def preflight(cfg, stages, destination_given: bool) -> list:
    """Refuse a run whose inputs cannot support it, BEFORE it starts.

    Two failures, both of which otherwise surface only as a line on stdout.
    CLAUDE.md's warning about `destination_check()` is exactly this: it shouts
    "on STDOUT, which is where a measurement harness is least likely to be
    listening", and a run that has already started is a run somebody will read
    the numbers off.

      1. A stage is skipped and its output is not on disk. Stage 4 otherwise
         dies inside the loader on a bare file-not-found -- and if the missing
         file is one of Module 3's, it dies AFTER the 862 MB catalog load.

      2. Stage 4 flies to one destination while the Stage 2 catalog on disk
         priced the cargo for another. The run completes, every profit number
         in it is meaningless, and nothing in the output CSV says so.

    (2) is the one this launcher made cheap to hit: `run.bat rerun leo` reuses
    the catalog on disk, which is normally priced for cislunar. Hence a hard
    refusal rather than a warning -- there is no reading of that run worth the
    minutes it costs.

    It also fires when NO --destination is given, because both configs default
    to `earth_surface` while the catalog on disk is whatever was last run.
    That is not over-eagerness: it is the exact case CLAUDE.md describes as
    "importing calc and calling build_profitability_catalog straight off gives
    a mismatched run".  So `--stages 4` wants an explicit --destination, and
    the message says which one.  Adopting the stamped value automatically was
    considered and rejected -- it would make the destination depend on
    whatever somebody ran last, which is how two v1.15.0 figures came to be
    recorded as cislunar after running against earth_surface prices.

    Returns the lines of a printable error, or [] if the run can proceed.
    """
    need = []
    if 4 in stages:
        if 1 not in stages:
            need.append((cfg.calc.asteroid_catalog_file,
                         os.path.join(cfg.calc.input_dir,
                                      cfg.calc.asteroid_catalog_file), 1))
        if 2 not in stages:
            need.append((cfg.calc.mineral_catalog_file,
                         os.path.join(cfg.calc.input_dir,
                                      cfg.calc.mineral_catalog_file), 2))
        if 3 not in stages:
            tdir = os.path.join(cfg.calc.input_dir,
                                cfg.calc.transportation_subdir)
            for fname in (cfg.calc.launch_vehicles_file,
                          cfg.calc.propellants_file,
                          cfg.calc.delta_v_segments_file,
                          cfg.calc.operational_costs_file):
                need.append((fname, os.path.join(tdir, fname), 3))

    missing = [(f, path, st) for f, path, st in need if not os.path.isfile(path)]
    if missing:
        stages_needed = sorted({st for _, _, st in missing})
        lines = ["Stage 4 needs files that are not on disk, and the stage",
                 "that writes them is not in --stages:", ""]
        lines += ["    %-28s (Stage %d)" % (f, st) for f, _, st in missing]
        lines += ["",
                  "Run those stages first:",
                  "",
                  "      py run_pipeline.py --stages %s"
                  % "".join(str(s) for s in stages_needed + [4])]
        return lines

    # -- (2) the destination the on-disk prices were built for ---------------
    if 4 not in stages or 2 in stages:
        return []                       # Stage 2 is about to re-price anyway

    path = os.path.join(cfg.calc.input_dir, cfg.calc.mineral_catalog_file)
    stamped = _stamped_destination(path)
    if stamped is None:
        return []                       # pre-v1.3.0 catalog; Stage 4 warns
    mine = str(cfg.delivery_destination).strip().lower()
    if stamped == mine:
        return []

    why = ([] if destination_given else [
        "No --destination was given, so this run took the config default,",
        "which is `%s` and is almost certainly not what you meant." % mine,
        "",
    ])
    return [
        "DESTINATION MISMATCH -- refusing to run.",
        "",
        "    the catalog on disk prices the cargo for : %s" % stamped,
        "    this run would fly it to                 : %s" % mine,
        "",
    ] + why + [
        "Stage 2 decides what a kilogram sells for and Stage 4 decides the",
        "architecture that puts it there. Disagreeing prices the cargo at a",
        "depot while paying to land it in Utah, and every profit number in",
        "the run is meaningless.",
        "",
        "Either use the destination the catalog is already priced for --",
        "",
        "      --destination %s" % stamped,
        "",
        "-- or re-price it, which means running Stage 2:",
        "",
        "      --stages %s --destination %s"
        % ("".join(str(x) for x in sorted(set(stages) | {2})), mine),
        "",
        "WARNING: Stage 2 re-fetches LIVE metal prices and overwrites the",
        "catalog on disk. The old prices are not recoverable, and every",
        ".verify baseline stops reproducing. Copy asteroid_pipeline/*.csv",
        "first if you may want to compare against them.",
    ]


def _stamped_destination(path):
    """The destination Module 2 priced for, read from its CSV's first row.

    One column of one row, so the whole 31-row file is not worth loading, and
    this must not import pandas at module scope -- master.py has not been
    imported yet when the parser is built.  Returns None when the column is
    absent (a pre-v1.3.0 catalog), which Stage 4's own check reports.
    """
    import csv
    try:
        with io.open(path, encoding="utf-8", newline="") as f:
            row = next(csv.DictReader(f), None)
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    if not row or "delivery_destination" not in row:
        return None
    value = (row["delivery_destination"] or "").strip().lower()
    return value or None


def print_banner(args, settings, cfg, stages) -> None:
    """Print every setting, each marked as the default or as a change from it.

    The marking is the point. Since calc v1.17.0 a configure-nothing run is the
    full catalog, beneficiated, with the programme search on -- so "the
    defaults" and "what most tables on record were measured at" are no
    longer the same thing, and a run that does not say which it is invites the
    two being confused.
    """
    rows      = settings["rows"]
    asteroids = settings["asteroids"]

    d_rows   = declared_default(cfg.calc,    "eval_row_cap")
    d_ast    = declared_default(cfg.catalog, "jpl_limit")
    d_benef  = declared_default(cfg.calc,    "use_beneficiation")
    d_search = declared_default(cfg.calc,    "optimise_programme_scale")
    d_dest   = declared_default(cfg.mineral, "delivery_destination")

    def fmt_rows(n):      return "every row" if not n else "{:,} (stride sample)".format(n)
    def fmt_ast(n):       return "all (1.55 M)" if not n else "{:,} per source".format(n)
    # Ratios come from master.MEASURED_CELL_SECONDS, never typed here: these
    # two labels printed the superseded 1.16.0 figures for three releases.
    _m = sys.modules["master"]
    def fmt_ore(raw):
        if raw:
            return "run-of-mine"
        return "beneficiated (~%.1fx slower)" % _m.beneficiation_cost_ratio(
            settings["search"])
    def fmt_prog(s):
        if not s:
            return "single mission (N = 1)"
        return "fleet x campaigns searched (~%.1fx slower)" % (
            _m.programme_search_cost_ratio(not settings["raw"]))

    def mark(current, default, fmt):
        """[default] if it matches the dataclass, else what the default was."""
        if current == default:
            return "[default]"
        return "[default: %s]" % fmt(default)

    lines = [
        ("Destination",  cfg.delivery_destination,
         mark(cfg.delivery_destination, d_dest, str)),
        ("Asteroids",    fmt_ast(asteroids),
         mark(asteroids, d_ast, fmt_ast)),
        ("Stage 4 rows", fmt_rows(rows),
         mark(rows, d_rows, fmt_rows)),
        ("Ore",          fmt_ore(settings["raw"]),
         mark(not settings["raw"], d_benef, lambda b: fmt_ore(not b))),
        ("Programme",    fmt_prog(settings["search"]),
         mark(settings["search"], d_search, fmt_prog)),
    ]

    print()
    print("=" * 78)
    print("  ASTEROID PROFITABILITY PIPELINE")
    print("=" * 78)
    print("  Preset       : %s -- %s" % (args.preset, PRESETS[args.preset]["blurb"]))
    print("  Stages       : %s" % ", ".join("%d %s" % (s, STAGE_NAMES[s])
                                            for s in stages))
    for label, value, note in lines:
        print("  %-12s : %-40s %s" % (label, value, note))
    print("  Output       : %s" % cfg.output_dir)
    print("-" * 78)
    if all(note == "[default]" for _, _, note in lines):
        print("  Every setting above is the pipeline default.")
    else:
        print("  [default] marks a pipeline default; the rest are this run's")
        print("  overrides, with the default they replaced shown alongside.")
    print("=" * 78)


# Stage -> (what it re-fetches, the file it overwrites). Stage 4 is absent
# because it fetches nothing: it reads the CSVs the others wrote.
_FETCHING_STAGES = {
    1: ("the JPL catalog and its supplements (~500 MB; JPL adds bodies daily, "
        "so the population itself changes)", "asteroid_catalog_file"),
    2: ("live metal prices", "mineral_catalog_file"),
    3: ("live commodity prices", None),
}


def overwrite_warning(cfg, stages) -> list:
    """Lines naming every fetch that would replace data already on disk.

    WHY THIS EXISTS, twice over. Stages 1-3 do not compute, they FETCH, and
    each writes over the only copy of its CSV -- there is no history and no
    undo. Every `.verify` baseline is built against those exact inputs, so
    refreshing one makes four cells stop reproducing, which looks exactly like
    a code regression and is not one.

    It has now happened here twice. On 2026-08-23 somebody ran `--stages 2`
    to look at a banner. Later the same day somebody testing THIS FILE's
    argument parsing ran `--stages 2,4` and `--stages 234` as throwaway
    checks -- the flags parsed correctly and the run went on to re-price the
    whole catalog for `leo`. Both times the command looked harmless and the
    cost was invisible until a comparison failed hours later.

    So the guard is about what a stage DOES, not about how long it takes:
    `confirm_long_run` asks about spending hours, and this asks about spending
    something you cannot get back.
    """
    at_risk = []
    for stage in sorted(stages):
        if stage not in _FETCHING_STAGES:
            continue
        what, attr = _FETCHING_STAGES[stage]
        path = None
        if attr:
            path = os.path.join(cfg.calc.input_dir, getattr(cfg.calc, attr))
            if not os.path.isfile(path):
                continue                    # nothing to lose; it must run
        elif not os.path.isdir(os.path.join(cfg.calc.input_dir,
                                            cfg.calc.transportation_subdir)):
            continue
        at_risk.append((stage, what))
    if not at_risk:
        return []
    lines = ["This run RE-FETCHES live data and overwrites what is on disk:", ""]
    lines += ["    Stage %d  %s" % (stage, what) for stage, what in at_risk]
    lines += [
        "",
        "The current values are the only copy. Any verify.py baseline built",
        "on them stops reproducing, and that reads exactly like a code",
        "regression. Copy asteroid_pipeline/*.csv first if you may want to",
        "compare against them.",
    ]
    return lines


def confirm_overwrite(cfg, stages) -> bool:
    for line in overwrite_warning(cfg, stages):
        print(("  " + line) if line else "")
    try:
        return input("\n  Type 'yes' to overwrite: ").strip().lower() == "yes"
    except KeyboardInterrupt:
        return False
    except EOFError:
        # Same rule as confirm_long_run: refuse, and say why, rather than
        # hanging on a stdin nobody is holding.
        print()
        print("  No console to confirm on (stdin is not a terminal).")
        print("  Pass --yes if overwriting them is what you meant.")
        return False


def confirm_long_run() -> bool:
    print()
    print("  WARNING: an uncapped Stage 4 over the full catalog runs for")
    print("  hours, and beneficiated with the programme search on has never")
    print("  been measured end to end -- budget days, not hours.")
    print("  Ctrl-C is safe: each stage writes its CSV before the next starts.")
    try:
        return input("\n  Type 'run' to continue: ").strip().lower() == "run"
    except KeyboardInterrupt:
        return False
    except EOFError:
        # No console to answer on -- a scheduled job, or stdin redirected.
        # Refusing is the right default for a run measured in days, but it has
        # to say WHY: a bare "Cancelled." and a non-zero exit reads as a run
        # that failed. Same trap as the destination prompt in run.bat, which
        # made a successful `run.bat quick` report 255.
        print()
        print("  No console to confirm on (stdin is not a terminal).")
        print("  Pass --yes to run this unattended.")
        return False


def main() -> int:
    print("Importing the pipeline ...", flush=True)
    master = load_master()

    parser = build_parser(master.DELIVERY_DESTINATIONS)
    args = parser.parse_args()
    settings = resolve(args)

    stages = parse_stages(args.stages, parser)

    cfg = master.MASTER_CONFIG
    if args.output:
        cfg.output_dir = os.path.abspath(args.output)
    # apply() pushes output_dir into all four sub-configs and creates the tree.
    # It also re-asserts the destination across Stage 2 and Stage 4, so it runs
    # BEFORE the destination is set here, not after.
    cfg.apply()

    if args.destination:
        cfg.delivery_destination = args.destination      # writes BOTH copies
    cfg.catalog.jpl_limit = settings["asteroids"]
    cfg.calc.eval_row_cap = settings["rows"]
    cfg.calc.use_beneficiation = not settings["raw"]
    cfg.calc.optimise_programme_scale = settings["search"]
    if args.workers is not None:
        cfg.calc.parallel_workers = args.workers

    check_defaults_preset(cfg)
    print_banner(args, settings, cfg, stages)

    problem = preflight(cfg, stages, bool(args.destination))
    if problem:
        print()
        for line in problem:
            print(("  " + line) if line else "")
        print()
        return 2

    if not args.yes and overwrite_warning(cfg, stages):
        if not confirm_overwrite(cfg, stages):
            print("  Cancelled. Nothing was overwritten.")
            return 1

    rows = settings["rows"]
    if 4 in stages and (not rows or rows > 50_000) and not args.yes:
        if not confirm_long_run():
            print("  Cancelled.")
            return 1

    builders = {
        1: ("catalog",   master.build_asteroid_catalog,       cfg.catalog),
        2: ("mineral",   master.build_mineral_value_catalog,  cfg.mineral),
        3: ("transport", master.build_transportation_catalog, cfg.transport),
        4: ("calc",      master.build_profitability_catalog,  cfg.calc),
    }

    t0 = time.time()
    results = {}
    for stage in stages:
        name, build, conf = builders[stage]
        print()
        print("-" * 72)
        print("  STAGE %d -- %s" % (stage, STAGE_NAMES[stage]))
        print("  started %s" % datetime.now().strftime("%H:%M:%S"))
        print("-" * 72, flush=True)
        t_stage = time.time()
        results[name] = build(conf)
        print("\n  Stage %d done in %s" % (stage, human(time.time() - t_stage)),
              flush=True)

    print()
    print("=" * 72)
    print("  COMPLETE in %s" % human(time.time() - t0))
    # Deliberately NOT a row/viable count. Stage 4 prints its own summary
    # immediately above this, and the two counted different things -- master
    # counts asteroids evaluated, this frame holds only the rows that produced
    # a result, so "20 evaluated" sat directly above "7 evaluated". One
    # authoritative count beats two that disagree.
    profit = results.get("calc")
    if profit is not None and not profit.empty:
        if not int(profit["viable"].sum()):
            print("  Zero viable missions is the model's correct answer for")
            print("  every setting currently in it, not a failure.")
    print("  Output written to: %s" % cfg.output_dir)
    print("=" * 72)
    return 0


if __name__ == "__main__":        # trap 2 -- required on Windows (spawn)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted. Whatever finished is on disk.")
        sys.exit(130)
