# -*- coding: utf-8 -*-
"""Streamlit front end for the asteroid profitability pipeline.

    pip install -r requirements-ui.txt
    py -m streamlit run ui.py

Three things it does:

    Configure   every field of all four config dataclasses, introspected at
                runtime so a new field appears without editing this file, with
                the module's own explanatory comment attached as help text.
    Run         any subset of the four stages, reusing the CSVs already on disk
                for the stages you skip. Stage 1 downloads ~500 MB and a full
                Stage 4 runs 12 min to 1.6 h depending on two flags (see below),
                so re-running Stage 4 alone against a cached catalog is the
                normal working loop.
    Inspect     the profitability catalog ranked by cost/revenue, charted, and
                drilled into one asteroid at a time.

DELIBERATELY NOT IN `modules/`. `build_master.py` concatenates that directory
into `master.py` and asserts a specific header/footer shape per module; this is
a consumer of the built `master.py`, not a part of it.

ON THE THREE PRESETS. `run_pipeline.PRESETS` and `run_pipeline.apply_preset`
are imported rather than restated, so the "Quick sample" button here and
`run.bat quick` are the same run by construction. Importing that module is
side-effect free apart from its stdout reconfiguration; it does not import
master, and its own run is behind an `if __name__` guard.

ON MUTATING CONFIG INSTANCES. CLAUDE.md says to edit a field's default inside
the dataclass rather than mutating the instance, because mutation defeats having
one editable source of truth. A UI is the exception the MasterConfig docstring
already carves out: it documents `MASTER_CONFIG.catalog.jpl_limit = 10_000` as
the supported way to drive the orchestrator. What the UI must not do is let the
two `delivery_destination` copies drift apart, so it renders one control and
writes it through the `MASTER_CONFIG.delivery_destination` property, which sets
both. Every run also drops a `ui_run_config.json` beside the outputs recording
exactly what produced them.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import re
import time
import traceback
from collections import deque
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import streamlit as st

import run_pipeline
import ui_meta
from ui_meta import FieldSpec

st.set_page_config(
    page_title="Asteroid pipeline",
    page_icon="🪐",
    layout="wide",
    initial_sidebar_state="expanded",
)

RUN_CONFIG_FILENAME = "ui_run_config.json"
NA = "n/a"

# The two sections, named once. They used to be matched with
# `page.endswith("Configure")`, i.e. on the tail of a string carrying a leading
# emoji and two spaces, which is a comparison that breaks the moment anyone
# edits the label.
PAGE_CONFIGURE = "Configure"
PAGE_RESULTS = "Results"
PAGES = [PAGE_CONFIGURE, PAGE_RESULTS]


# ═════════════════════════════════════════════════════════════════════════════
# PIPELINE IMPORT
# ═════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="Importing master.py …")
def load_pipeline():
    """Import master.py once per Streamlit session.

    Importing is side-effect free by design, since master.py guards its auto-run
    on `__name__ == "__main__"`, but it does print an installation banner and
    build the config singletons, so that output is swallowed here.
    """
    with contextlib.redirect_stdout(io.StringIO()):
        import master  # noqa: PLC0415  (deliberately late and cached)
    return master


try:
    master = load_pipeline()
except Exception as exc:                                   # pragma: no cover
    st.error(f"Could not import `master.py`: {exc}")
    st.code(traceback.format_exc())
    st.stop()

MASTER = master.MASTER_CONFIG

CONFIG_OBJECTS: Dict[str, Any] = {
    "catalog":   MASTER.catalog,
    "mineral":   MASTER.mineral,
    "transport": MASTER.transport,
    "calc":      MASTER.calc,
}

DESTINATIONS = sorted(master.DELIVERY_DESTINATIONS.keys())

BUILDERS = {
    "catalog":   master.build_asteroid_catalog,
    "mineral":   master.build_mineral_value_catalog,
    "transport": master.build_transportation_catalog,
    "calc":      master.build_profitability_catalog,
}


@st.cache_data(show_spinner=False)
def field_specs() -> Dict[str, List[FieldSpec]]:
    """Introspect the four configs once; the dataclasses do not change at runtime."""
    return {key: ui_meta.build_field_specs(obj, key)
            for key, obj in CONFIG_OBJECTS.items()}


SPECS = field_specs()
SPEC_INDEX: Dict[str, FieldSpec] = {
    f"{s.section_key}::{s.name}": s
    for specs in SPECS.values() for s in specs
}


# ═════════════════════════════════════════════════════════════════════════════
# STAGES
# ═════════════════════════════════════════════════════════════════════════════

@dataclasses.dataclass(frozen=True)
class Stage:
    """One pipeline stage as the UI sees it: its config key, number and blurb.

    `key` is the name of the sub-config on `MASTER_CONFIG`, so it is also what
    `ui_meta` keys its field specs by; the four Stage objects are the only place
    the UI states the stage order, and everything else derives from them.
    """

    key: str
    number: int
    label: str
    blurb: str

    def outputs(self) -> List[str]:
        """Files this stage writes, absolute, in the current output dir."""
        out = MASTER.output_dir
        if self.key == "catalog":
            return [os.path.join(out, MASTER.catalog.catalog_filename)]
        if self.key == "mineral":
            return [os.path.join(out, MASTER.mineral.catalog_filename)]
        if self.key == "transport":
            sub = os.path.join(out, MASTER.transport.subdir)
            return [os.path.join(sub, name) for name in (
                "launch_vehicles.csv", "propellants.csv",
                "delta_v_segments.csv", "operational_costs.csv",
                "storage_systems.csv")]
        return [os.path.join(out, MASTER.calc.output_filename)]

    def cache_status(self) -> Optional[Tuple[float, float]]:
        """(age_seconds, size_mb) if every output exists, else None."""
        paths = self.outputs()
        if not all(os.path.exists(p) for p in paths):
            return None
        newest = max(os.path.getmtime(p) for p in paths)
        return time.time() - newest, sum(os.path.getsize(p) for p in paths) / 1e6


STAGES = [
    Stage("catalog",   1, "Asteroid catalog",
          "JPL SBDB + MP3C + SsODNet + NEOWISE. Downloads ~500 MB; slowest to "
          "re-run and the one you most want cached."),
    Stage("mineral",   2, "Mineral value",
          "Live prices + mineralogy, priced FOR THE CHOSEN DESTINATION. Must "
          "be re-run whenever the destination changes."),
    Stage("transport", 3, "Transportation",
          "Launch vehicles, propellants (with storage class and tankage), Δv "
          "segments, ops costs, storage systems. Reference tables: fast, and "
          "rarely needs re-running, but it MUST be re-run after a v1.9.0 "
          "upgrade, or Stage 4 reads a propellants.csv with no tankage "
          "columns and silently flies every tank for free."),
    Stage("calc",      4, "Profitability",
          "The headline output, and the only stage whose runtime you choose. "
          "Measured on the full 1.55 M-row catalog at cislunar, 12 workers, "
          "calc 1.17.7: 12 min raw at N = 1, 21 min with "
          "optimise_programme_scale, 57 min with use_beneficiation, and 1.6 h "
          "with both, and both of those flags DEFAULT ON as of calc v1.17.0, "
          "so budget for the 1.6 h unless you turn one off. Cislunar is the "
          "CHEAPEST destination: leo, mars_surface and earth_surface run "
          "2.1-2.7x longer per cell, so the default there is 3.4-4.3 h. "
          "Seconds with eval_row_cap set low."),
]


def cached_mineral_destination() -> Optional[str]:
    """Destination stamped into the mineral catalog already on disk.

    This is the guard that matters most for cached reuse: skipping Stage 2 after
    changing the destination pairs (say) cislunar prices with a Utah re-entry.
    Stage 4's own `destination_check()` catches it and shouts into the log, but
    by then you have paid for the run.
    """
    path = os.path.join(MASTER.output_dir, MASTER.mineral.catalog_filename)
    if not os.path.exists(path):
        return None
    try:
        head = pd.read_csv(path, nrows=1, usecols=["delivery_destination"])
    except Exception:
        return None
    if head.empty:
        return None
    return str(head["delivery_destination"].iloc[0]).strip().lower()


# ═════════════════════════════════════════════════════════════════════════════
# CONFIG WIDGETS
# ═════════════════════════════════════════════════════════════════════════════

def _help_for(spec: FieldSpec) -> str:
    """Tooltip for one config field: its name, then the module's own comment.

    The comment is scraped rather than paraphrased, on purpose. The premise of
    this repo is that a number without its reasoning attached gets "fixed" by
    the next person, so the dial shows the reasoning that is already next to the
    default in the source. A field with no comment says so, which is what
    `verify_docs.py` check 8 exists to prevent.
    """
    return f"`{spec.name}`\n\n{spec.help or 'No comment in the module source.'}"


def _seed(spec: FieldSpec) -> Any:
    """Ensure st.session_state[spec.key] holds a valid, correctly typed value.

    The widget key IS the storage key. Streamlit owns that slot and raises if
    anything writes to it after the widget exists, so the value is seeded before
    the widget is created and never assigned afterwards. That also means each
    field may be rendered exactly ONCE per run, because a duplicate key is an
    error, which is why a curated field appears as a live control on the Common
    tab and as a read-only mirror on its module tab.
    """
    key = spec.key
    if key not in st.session_state:
        st.session_state[key] = getattr(
            CONFIG_OBJECTS[spec.section_key], spec.name, spec.default)

    value = st.session_state[key]

    # Coerce to the type the widget will demand, so a float field seeded with an
    # int, or a stale value now outside its bounds, cannot blow up number_input.
    if spec.kind == "bool":
        st.session_state[key] = bool(value)
    elif spec.kind in ("int", "float") and spec.bounds:
        lo, hi, _ = spec.bounds
        cast = int if spec.kind == "int" else float
        st.session_state[key] = cast(min(max(cast(value or 0), lo), hi))
    elif spec.kind == "list":
        st.session_state[key] = list(value) if value else []
    elif spec.kind == "str" and value is None:
        st.session_state[key] = ""

    return st.session_state[key]


def render_field(spec: FieldSpec) -> None:
    """Render one config field as a live widget bound to st.session_state[spec.key]."""
    label = spec.name.replace("_", " ")
    help_text = _help_for(spec)

    if spec.kind == "readonly":
        # No _seed(): nothing reads these back, so claiming the session slot
        # would only risk colliding with a future live widget of the same name.
        current = getattr(CONFIG_OBJECTS[spec.section_key], spec.name, spec.default)
        st.text_input(label, value=str(current), disabled=True,
                      key=f"ro::{spec.key}", help=help_text)
        return

    value = _seed(spec)

    if spec.kind == "bool":
        st.checkbox(label, key=spec.key, help=help_text)

    elif spec.kind == "choice":
        options = spec.choices or []
        if not options:
            st.text_input(label, key=spec.key, help=help_text)
            return
        if value not in options:
            st.session_state[spec.key] = options[0]
        st.selectbox(label, options, key=spec.key, help=help_text)

    elif spec.kind == "list":
        # Anything already selected but absent from the discovered options (a
        # vehicle from a catalog not yet rebuilt, say) stays selectable.
        options = _list_options(spec.name)
        options = options + [c for c in value if c not in options]
        st.multiselect(label, options, key=spec.key,
                       help=help_text + "\n\nEmpty = no filter (all).")

    elif spec.kind in ("int", "float") and spec.bounds:
        lo, hi, step = spec.bounds
        cast = int if spec.kind == "int" else float
        st.number_input(
            label, min_value=cast(lo), max_value=cast(hi),
            step=cast(max(step, 1)) if spec.kind == "int" else float(step),
            format=None if spec.kind == "int" else "%.4f",
            key=spec.key, help=help_text)

    elif spec.kind in ("int", "float"):
        st.number_input(label, key=spec.key, help=help_text)

    else:
        st.text_input(label, key=spec.key, help=help_text,
                      type="password" if spec.secret else "default")


def render_mirror(spec: FieldSpec) -> None:
    """Read-only view of a curated field whose live control is on the Common tab.

    Keeps every field discoverable on its own module tab without instantiating a
    second widget for the same key. Reads only, never `_seed()`: the live widget
    already owns this session key, and Streamlit forbids writing to a key after
    its widget exists.
    """
    value = st.session_state.get(
        spec.key, getattr(CONFIG_OBJECTS[spec.section_key], spec.name, spec.default))
    shown = ", ".join(value) if isinstance(value, list) else str(value)
    st.text_input(spec.name.replace("_", " "), value=shown or "(all)",
                  disabled=True, key=f"mirror::{spec.key}",
                  help=f"{_help_for(spec)}\n\n**Set on the ⭐ Common tab.**")


@st.cache_data(show_spinner=False)
def _read_name_column(path: str, mtime: float) -> List[str]:
    """Sorted unique values of a reference CSV's name column, for a multiselect.

    `mtime` is not used in the body: it is part of the CACHE KEY, so editing the
    CSV on disk invalidates the cached list instead of serving a stale one for
    the life of the session. Returns [] on any failure, because a missing
    reference file should leave the picker empty rather than break the page.
    """
    try:
        df = pd.read_csv(path)
    except Exception:
        return []
    for col in ("name", "vehicle", "propellant"):
        if col in df.columns:
            return sorted(df[col].dropna().astype(str).unique().tolist())
    return []


def _list_options(name: str) -> List[str]:
    """Legal values for candidate_vehicles / candidate_propellants, if built."""
    filename = {"candidate_vehicles": "launch_vehicles.csv",
                "candidate_propellants": "propellants.csv"}.get(name)
    if not filename:
        return []
    path = os.path.join(MASTER.output_dir, MASTER.transport.subdir, filename)
    if not os.path.exists(path):
        return []
    return _read_name_column(path, os.path.getmtime(path))


def apply_config() -> List[str]:
    """Push session values onto the live config objects. Returns a change log."""
    changes: List[str] = []

    for section, specs in SPECS.items():
        target = CONFIG_OBJECTS[section]
        for spec in specs:
            if spec.kind == "readonly" or spec.key not in st.session_state:
                continue
            new = st.session_state[spec.key]
            # An empty multiselect means "no filter", which the config spells
            # None, not []: candidate_combos() reads None as "every vehicle".
            if spec.kind == "list" and not new:
                new = None
            old = getattr(target, spec.name, None)
            if old != new:
                changes.append(f"{section}.{spec.name}: {old!r} -> {new!r}")
            setattr(target, spec.name, new)

    # The destination is written LAST and through the master property, so it
    # cannot be left disagreeing between Stage 2 and Stage 4 by an ordinary
    # field write above.
    dest = st.session_state.get("destination", MASTER.delivery_destination)
    if MASTER.delivery_destination != dest:
        changes.append(
            f"delivery_destination: {MASTER.delivery_destination!r} -> {dest!r}")
    MASTER.delivery_destination = dest

    # apply() re-pushes output_dir into every sub-config and re-asserts the
    # destination across Stages 2 and 4.
    MASTER.apply()
    return changes


def effective(section: str, name: str) -> Any:
    """What a run started right now would use for one config field.

    Session state is the truth for anything the user has touched, because
    `apply_config()` does not push it onto the config objects until the run
    starts. Reading the config object alone made the sidebar summary contradict
    the Configure page the moment anyone edited a dial.
    """
    spec = SPEC_INDEX.get(f"{section}::{name}")
    if spec is not None and spec.key in st.session_state:
        return st.session_state[spec.key]
    return getattr(CONFIG_OBJECTS[section], name, None)


PRESET_LABELS = {
    "quick":    "Quick sample",
    "standard": "Standard",
    "full":     "Full run",
}


def preset_summary(name: str) -> str:
    """One line describing what a preset actually sets, read off run_pipeline.

    Built from the settings dict rather than from `blurb`, because the blurb is
    prose written for a `--help` epilog and this has to fit under a button.
    """
    s = run_pipeline.PRESETS[name]
    rows = "every row" if not s["rows"] else f"{s['rows']:,} rows"
    ore = "run-of-mine ore" if s["raw"] else "beneficiated"
    prog = "programme search" if s["search"] else "single mission"
    return f"{rows}, {ore}, {prog}"


def apply_run_preset(name: str) -> None:
    """Set the run-size dials to one of run_pipeline's three presets.

    Deliberately NOT called `apply_preset`: `run_pipeline.apply_preset` is the
    one that defines what a preset means, this one is the UI wrapper that also
    reconciles session state, and two functions of one name reading each other
    is how a reader ends up sure the mapping lives here.

    Runs at the TOP of a script run for the same reason `reset_config` does:
    it clears session keys, and a key Streamlit has already bound to a live
    widget is exactly the write it forbids. The sidebar button sets a flag and
    reruns.

    Which session keys to clear is DERIVED, by snapshotting every introspected
    field before and after and dropping the ones that moved, rather than by
    listing the four fields `run_pipeline.apply_preset` happens to write today.
    A fifth field added there would otherwise be written onto the config and
    then immediately overwritten from a stale session value, which is a silent
    wrong answer rather than an error.
    """
    settings = dict(run_pipeline.PRESETS[name])
    settings.pop("blurb", None)

    before = {spec.key: getattr(CONFIG_OBJECTS[spec.section_key], spec.name, None)
              for specs in SPECS.values() for spec in specs}
    run_pipeline.apply_preset(MASTER, settings)

    for specs in SPECS.values():
        for spec in specs:
            now = getattr(CONFIG_OBJECTS[spec.section_key], spec.name, None)
            if now != before[spec.key]:
                st.session_state.pop(spec.key, None)
    MASTER.apply()


def reset_config() -> None:
    """Restore the dataclass defaults and drop every session override.

    Runs at the TOP of a script run, before any widget exists, because deleting
    a key Streamlit has already bound to a live widget is exactly the write it
    forbids. The sidebar button therefore sets a flag and reruns rather than
    resetting in place.
    """
    for section, specs in SPECS.items():
        defaults = {f.name: f.default
                    for f in dataclasses.fields(type(CONFIG_OBJECTS[section]))}
        for spec in specs:
            st.session_state.pop(spec.key, None)
            default = defaults.get(spec.name, dataclasses.MISSING)
            if default is not dataclasses.MISSING:
                setattr(CONFIG_OBJECTS[section], spec.name, default)
    st.session_state.pop("destination", None)
    MASTER.apply()


# ═════════════════════════════════════════════════════════════════════════════
# RUN EXECUTION
# ═════════════════════════════════════════════════════════════════════════════

def _fmt_duration(seconds: float) -> str:
    """Compact human duration: 12s, 3m 19s, 1h 04m."""
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"
    return f"{int(seconds // 3600)}h {int(seconds % 3600) // 60:02d}m"


def _stage_minutes(key: str) -> float:
    """Prior for how long a stage takes, in minutes.

    Used for the sidebar estimate and for weighting the overall progress bar,
    so the two can never disagree about which stage dominates a run.

    Measured on this repo rather than guessed. The first version charged Stages
    2 and 3 a flat 1.0 and 0.3 minutes when they actually finish in about two
    seconds and half a second, which made the overall bar leap to ~85% while
    Stage 4 was still reporting 25%, and produced an overall ETA that
    contradicted the stage ETA directly beneath it.
    """
    if key == "mineral":
        return 0.04              # ~2 s: a handful of live price quotes
    if key == "transport":
        return 0.01              # ~0.5 s: pure reference tables, no network

    # Full size of the JPL asteroid table, measured 2026-08-08.  Needed as a
    # literal because `jpl_limit = 0` means "unlimited" as of catalog v1.1.0,
    # and `or 50_000` would have quietly estimated the largest possible run as
    # the smallest one; the estimate would have said three minutes for
    # something that takes an afternoon.
    _JPL_FULL_ROWS = 1_554_321

    if key == "catalog":
        limit = st.session_state.get("cfg::catalog::jpl_limit",
                                     MASTER.catalog.jpl_limit)
        limit = _JPL_FULL_ROWS if not limit else min(limit, _JPL_FULL_ROWS)
        ssodnet = st.session_state.get("cfg::catalog::use_ssodnet",
                                       MASTER.catalog.use_ssodnet)
        # JPL, NEOWISE and the merge scale with the row cap; SsODNet is a flat
        # ~500 MB parquet download that dwarfs all of them when enabled.
        # Slope re-fitted on the v1.1.0 unlimited run: 1,554,321 rows end to end
        # in 224 s with a warm SsODNet cache, i.e. ~2.4 min of scaling work plus
        # the parquet.  The old 1.5 min per 50k over-charged by ~48x at full
        # size, which mattered once "full size" became the default.
        return 0.15 + limit / _JPL_FULL_ROWS * 2.4 + (5.0 if ssodnet else 0.0)

    # Stage 4 is the long pole. `eval_row_cap` is an upper bound rather than a
    # count, so this overestimates when the catalog is smaller than the cap;
    # the stage bar self-corrects the moment the pipeline prints its first
    # "i / n evaluated" and the real n becomes known.
    #
    # 0 means "every row" here too, and against a v1.1.0 catalog that is ~1.55 M
    # rows rather than the 35,000 this used to assume.
    rows = st.session_state.get("cfg::calc::eval_row_cap",
                                MASTER.calc.eval_row_cap) or _JPL_FULL_ROWS
    benef = st.session_state.get("cfg::calc::use_beneficiation",
                                 MASTER.calc.use_beneficiation)
    # BOTH axes, because both default ON as of calc v1.17.0 and each costs
    # real time. Omitting the programme search once told the user 2.2 h for the
    # DEFAULT run against the 6.8 h then measured -- 3.1x low, and flatly
    # contradicted by this stage's own blurb four lines of sidebar away, which
    # already carried the right figure. A stale estimate beside a correct
    # sentence is the exact failure CLAUDE.md is written to catch. (Both
    # numbers are calc 1.16.0; on 1.17.7 the same cell is 1.6 h, which is what
    # the blurb and _SECONDS_PER_ROW now carry.)
    search = st.session_state.get("cfg::calc::optimise_programme_scale",
                                  MASTER.calc.optimise_programme_scale)

    # Seconds per row, read straight off the committed full-catalog 2x2 --
    # README.md, "Beneficiation", which carries the wall clock for all twenty
    # cells; calc 1.17.7, 12 workers, over master.MEASURED_CELL_ROWS (the
    # 1,555,667-row catalog those cells were measured on; 1,555,618 of them
    # carry positive mass, a 0.003% difference that does not matter to an
    # estimate the stage bar replaces within a minute):
    #
    #                 search OFF     search ON
    #     raw              733 s       1,253 s
    #     beneficiated   3,424 s       5,692 s
    #
    # The old pair of rates carried a beneficiated:raw ratio of 3.12x, taken
    # from a stride sample. versions.md retires that figure by name -- and
    # THE SAMPLING RULE is precisely about not doing this. These four are
    # measured full runs, so they need no ratio at all.
    #
    # Updated 2026-08-24 from the calc 1.16.0 figures (1,307 / 3,890 / 9,300 /
    # 24,587 s). The previous comment here said this "reads HIGH" because five
    # performance-only releases had landed with no full-catalog run on any of
    # them; the 20-cell campaign supplied one, and they were worth 1.78x to
    # 4.32x -- so the default estimate was reading 4.3x high, not slightly.
    # Read from master rather than restated here. These four numbers used to
    # be typed into five files at once and went stale together; calc.py's
    # MEASURED_CELL_SECONDS is the one place they live now.
    _CELL_ROWS = master.MEASURED_CELL_ROWS
    _SECONDS_PER_ROW = {k: v / _CELL_ROWS
                        for k, v in master.MEASURED_CELL_SECONDS.items()}
    # Measured at CISLUNAR, which is the CHEAPEST destination. leo, mars_surface
    # and earth_surface run 2.1-2.7x slower per cell (20-cell matrix); this does
    # not try to model that, because it is a prior, and the stage bar replaces
    # it with measured progress within the first minute. So it now reads LOW
    # away from cislunar rather than high everywhere -- the trade taken
    # deliberately, since the four cislunar cells are the ones measured on the
    # current code.
    return rows * _SECONDS_PER_ROW[(bool(benef), bool(search))] / 60.0


# Progress signals the pipeline already emits. These are PARSED rather than
# added, because the pipeline is a library the UI drives and not a UI backend.
# The one exception is calc.py's report interval, which went from 10% to 1% so
# that a bar drawn off it advances more than ten times in twenty minutes.
_COUNT_RE = re.compile(r"([\d,]+)\s*/\s*([\d,]+)\s+evaluated")
_TQDM_PCT_RE = re.compile(r"(\d{1,3})%\|")
# The ASCII banner characters come first: the pipeline's own output is pure
# ASCII, and `#` is what the old full-block rule became. The box-drawing
# characters are kept so an archived log from before that change still
# filters correctly.
_RULE_ONLY_RE = re.compile(r"^[\s=#█▔▁─═*·.+-]*$")


class _RunView:
    """The loading screen: one overall bar, plus a live panel per stage.

    Overall progress is weighted by `_stage_minutes`, so a run that includes
    Stage 1 does not show 25% complete the instant the catalog download starts.
    The weights are priors, and the caption says so; the per-stage bars are the
    ones carrying real measured progress.
    """

    def __init__(self, stages: Sequence[Stage]):
        """Weight each selected stage by its prior duration, then paint at 0%.

        The weights are floored at 0.05 minutes so a stage with no prior cannot
        contribute zero and make the overall bar jump past it.
        """
        self.stages = list(stages)
        self.weights = [max(_stage_minutes(s.key), 0.05) for s in self.stages]
        self.total_weight = sum(self.weights) or 1.0
        self.t_start = time.monotonic()
        self.done_weight = 0.0
        self.index = 0
        self._bar = st.progress(0.0)
        self.paint(0.0)

    def expected_seconds(self) -> float:
        """Prior duration of the stage currently running, in seconds."""
        return self.weights[self.index] * 60.0

    def paint(self, stage_fraction: float,
              stage_eta: Optional[float] = None) -> None:
        """Repaint the overall bar for the running stage's progress.

        The remaining time is COMPOSED (this stage's own estimate, plus the
        priors for stages not yet started) rather than extrapolated from the
        overall fraction. Extrapolating made the overall bar contradict the
        stage bar sitting directly beneath it, because a stage whose prior is
        wrong throws the overall fraction off and the error is then amplified
        by dividing by it. Composing means the headline number is only ever as
        wrong as the stage estimate it is built from.
        """
        stage_fraction = min(max(stage_fraction, 0.0), 1.0)
        frac = min(max((self.done_weight
                        + self.weights[self.index] * stage_fraction)
                       / self.total_weight, 0.0), 1.0)
        elapsed = time.monotonic() - self.t_start

        if stage_eta is None:
            stage_eta = self.expected_seconds() * (1.0 - stage_fraction)
        remaining = stage_eta + sum(self.weights[self.index + 1:]) * 60.0

        bits = [f"**{self.index + 1} of {len(self.stages)}**",
                self.stages[self.index].label,
                f"{_fmt_duration(elapsed)} elapsed",
                f"~{_fmt_duration(remaining)} left"]
        try:
            self._bar.progress(frac, text="  ·  ".join(bits))
        except Exception:
            pass

    def finish_stage(self) -> None:
        """Bank the finished stage's weight and repaint at 0% of the next one."""
        self.done_weight += self.weights[self.index]
        self.paint(0.0)


class ProgressScan:
    """Parses a pipeline stage's console stream into progress state.

    Deliberately free of Streamlit so it can be exercised against real captured
    output without a browser; `_StageMonitor` supplies the rendering.

    The pipeline prints an unindented emoji header when it enters a phase, and
    indented lines beneath it for detail. That indentation alone separates
    "what is happening now" from "what just happened", so the UI needs no table
    of phase names, which would rot the first time a module was reworded.

    Two numeric signals give a determinate bar: Stage 4's "i / n evaluated" and
    tqdm's percentage during the Stage 1 downloads.

    Carriage returns are handled the way a terminal would. tqdm redraws its bar
    with `\\r` and no newline, so only the text after the last `\\r` is real.
    Without that the log becomes one enormous line of superimposed redraws, and
    the pending buffer grows without bound across a 500 MB download.
    """

    def __init__(self, tail_lines: int = 6):
        """Empty scan state. `tail_lines` is how much of the log the UI shows.

        `full` keeps everything for the run log, `tail` is a bounded deque for
        the live view, and `_pending` holds a partial line between `feed` calls.
        """
        self.full: List[str] = []
        self.tail = deque(maxlen=tail_lines)
        self.live = ""               # in-flight tqdm redraw, not yet a log line
        self.phase = ""
        self.done = 0.0
        self.total = 0.0
        self._pending = ""

    def feed(self, text: str) -> None:
        """Absorb a chunk of the stage's stdout. May be a partial line.

        Carriage returns are resolved the way a terminal would: tqdm redraws its
        bar with `\r` and no newline, so only the text after the LAST `\r` is
        real. Without that the log becomes one enormous line of superimposed
        redraws and `_pending` grows without bound across a 500 MB download.
        """
        self._pending += text.replace("\r\n", "\n")
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._record(line.rsplit("\r", 1)[-1])
        if "\r" in self._pending:
            self.live = self._pending = self._pending.rsplit("\r", 1)[-1]
            self._scan(self.live)

    def close(self) -> None:
        """Flush a final line that arrived without a trailing newline."""
        if self._pending.strip():
            self._record(self._pending.rsplit("\r", 1)[-1])
        self._pending = ""

    @property
    def display_lines(self) -> List[str]:
        """The log tail, plus the in-flight tqdm redraw if one is mid-line."""
        return list(self.tail) + ([self.live] if self.live else [])

    @property
    def log(self) -> str:
        """Everything the stage printed, one line per redraw-resolved line."""
        return "\n".join(self.full)

    def _record(self, line: str) -> None:
        """Commit one completed line to the log and the tail, and scan it."""
        self.live = ""
        self.full.append(line)
        self.tail.append(line)
        self._scan(line)

    def _scan(self, line: str) -> None:
        """Update phase and progress counts from one line of output.

        Two numeric signals give a determinate bar, Stage 4's "i / n evaluated"
        and tqdm's percentage. Everything else is a PHASE header, recognised by
        being unindented and containing letters, which is why the UI needs no
        table of phase names to rot the first time a module is reworded.
        """
        line = line.rstrip()
        if not line:
            return

        if match := _COUNT_RE.search(line):
            self.done = float(match.group(1).replace(",", ""))
            self.total = float(match.group(2).replace(",", ""))
            return
        if match := _TQDM_PCT_RE.search(line):
            self.done, self.total = float(match.group(1)), 100.0
            return

        # Unindented and containing letters means a phase header; a new phase
        # invalidates the counts the previous one was reporting.
        if (line[:1] not in (" ", "\t")
                and not _RULE_ONLY_RE.match(line)
                and re.search(r"[A-Za-z]", line)):
            self.phase = line.strip()
            self.done = self.total = 0.0


class _StageMonitor(io.TextIOBase):
    """Renders one stage's ProgressScan into a live bar, caption and log tail.

    Repaints are throttled: Stage 1 emits thousands of lines and a tqdm bar
    redraws far faster than a browser can usefully follow, so painting on every
    write would make the UI the bottleneck rather than the pipeline.
    """

    def __init__(self, view: _RunView, min_interval: float = 0.25):
        """Claim a progress bar and a log slot for one stage.

        `min_interval` is the repaint throttle in seconds: Stage 1 emits
        thousands of lines and a tqdm bar redraws far faster than a browser can
        follow, so an unthrottled paint makes the UI the bottleneck.
        """
        self._view = view
        self._scan = ProgressScan()
        self._bar = st.progress(0.0)
        self._log = st.empty()
        self._t0 = time.monotonic()
        self._last_paint = 0.0
        self._min_interval = min_interval

    def write(self, s: str) -> int:
        """TextIOBase hook: the stage's stdout arrives here and is repainted."""
        self._scan.feed(s)
        self._paint()
        return len(s)

    def flush(self) -> None:
        """No-op: there is no buffer to flush, `write` paints as it goes."""
        pass

    def finish(self) -> str:
        """Close the scan, force one last repaint, and return the whole log."""
        self._scan.close()
        self._paint(force=True)
        return self._scan.log

    def _paint(self, force: bool = False) -> None:
        """Repaint the stage bar, throttled to `_min_interval` unless forced.

        Where there is no count to read it creeps against the stage prior rather
        than showing a stalled 0%, capped short of full so it never claims to be
        finished when it does not know.
        """
        now = time.monotonic()
        if not force and now - self._last_paint < self._min_interval:
            return
        self._last_paint = now

        scan = self._scan
        elapsed = now - self._t0
        measured = scan.total > 0
        if measured:
            frac = min(max(scan.done / scan.total, 0.0), 1.0)
        else:
            # No count to read. Creep against the prior rather than show a
            # stalled 0%, capped short of full so it never claims to be done.
            expected = self._view.expected_seconds()
            frac = min(0.95, elapsed / expected) if expected > 0 else 0.0

        # Only extrapolate once there is enough of a sample for the rate to
        # mean anything; below that the number swings wildly between repaints.
        eta = (elapsed * (1 - frac) / frac
               if measured and frac > 0.03 and elapsed > 3 else None)

        bits = [scan.phase or "working"]
        if measured:
            bits.append(f"{scan.done:,.0f} / {scan.total:,.0f}  ({frac:.0%})")
        bits.append(f"{_fmt_duration(elapsed)} elapsed")
        if eta is not None:
            bits.append(f"~{_fmt_duration(eta)} left")
        elif not measured:
            bits.append("estimated")

        try:
            self._bar.progress(frac, text="  ·  ".join(bits))
            self._log.code("\n".join(scan.display_lines) or "…", language="text")
            self._view.paint(frac, eta)
        except Exception:
            pass      # placeholder gone mid-write; never kill the pipeline for it


def write_run_manifest(selected: List[str], changes: List[str]) -> str:
    """Record what produced the CSVs in the output dir.

    The pipeline stamps `pipeline_version` into every CSV, which identifies the
    CODE but not the CONFIG. Two runs of identical code at different
    destinations, or with beneficiation on and off, are indistinguishable from
    their outputs alone, and this project's documented failure mode is a number
    whose provenance nobody can reconstruct.
    """
    manifest = {
        "written_at": datetime.now().isoformat(timespec="seconds"),
        "stages_run": selected,
        "delivery_destination": MASTER.delivery_destination,
        "changes_from_defaults": changes,
        "versions": {
            "catalog": MASTER.catalog.pipeline_version,
            "mineral_value": MASTER.mineral.pipeline_version,
            "transportation": MASTER.transport.pipeline_version,
            "calc": MASTER.calc.pipeline_version,
        },
        "config": {
            section: {f.name: getattr(obj, f.name)
                      for f in dataclasses.fields(obj)}
            for section, obj in CONFIG_OBJECTS.items()
        },
    }
    path = os.path.join(MASTER.output_dir, RUN_CONFIG_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    return path


def run_stages(selected_keys: Sequence[str]) -> None:
    """Execute the chosen stages in order, streaming each one's progress.

    Blocking by design. Streamlit runs the script in one thread, so the page is
    unresponsive until this returns; the loading screen exists to make that
    obvious and legible rather than to hide it. Running the pipeline on a
    worker thread would free the UI but needs every stage's prints marshalled
    back through a script-run context, which is a lot of machinery to avoid a
    wait the user deliberately asked for.
    """
    changes = apply_config()
    stages = [s for s in STAGES if s.key in selected_keys]
    logs: Dict[str, str] = {}
    st.session_state["run_error"] = None

    view = _RunView(stages)
    t_start = view.t_start

    for index, stage in enumerate(stages):
        view.index = index
        header = f"Stage {stage.number}: {stage.label}"
        with st.status(header, expanded=True) as status:
            monitor = _StageMonitor(view)
            t0 = time.monotonic()
            try:
                with contextlib.redirect_stdout(monitor), \
                     contextlib.redirect_stderr(monitor):
                    BUILDERS[stage.key](CONFIG_OBJECTS[stage.key])
            except Exception as exc:
                logs[stage.key] = monitor.finish() + "\n" + traceback.format_exc()
                status.update(label=f"{header} FAILED: {exc}", state="error")
                st.session_state["run_error"] = f"{header}: {exc}"
                st.session_state["run_logs"] = logs
                return
            logs[stage.key] = monitor.finish()
            status.update(
                label=f"{header} done in {_fmt_duration(time.monotonic() - t0)}",
                state="complete", expanded=False)
        view.finish_stage()

    st.session_state["run_logs"] = logs
    st.session_state["run_elapsed"] = time.monotonic() - t_start
    st.session_state["run_finished_at"] = datetime.now()
    st.session_state["run_manifest"] = write_run_manifest(
        list(selected_keys), changes)
    st.session_state["results_token"] = time.time()   # busts the results cache

    # Land on the answer. Someone who just pressed Run wants the output, and
    # leaving them on the Configure page meant a run finished with no visible
    # sign of it except a green line above the dials they had been editing.
    #
    # DEFERRED, like the reset and the presets, and for the same reason: the
    # section control is created in main() BEFORE this function is called, so
    # writing its key here is the write Streamlit forbids. main() reads the
    # flag at the top of the next run, before any widget exists.
    if "calc" in selected_keys:
        st.session_state["goto_results"] = True

    # The sidebar rendered its cache status BEFORE these stages wrote anything,
    # so it is now describing a state that no longer exists, most visibly still
    # warning about a destination mismatch this run just fixed. Rerun so it
    # re-reads the disk; the log is replayed from session state.
    st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# RESULTS
# ═════════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner="Loading profitability catalog …")
def load_results(path: str, token: float) -> pd.DataFrame:
    """Read the profitability catalog and add the ranking column.

    `cost_revenue_ratio` is computed here rather than read, because Stage 4 does
    not write it. CLAUDE.md is emphatic that this, and not `profit_usd`, is the
    ranking to use: revenue sits orders of magnitude below cost in most
    configurations, so profit is approximately -cost and ranking by it
    degenerates into a Δv table wearing a profit label.
    """
    df = pd.read_csv(path, low_memory=False)
    if {"gross_value_usd", "total_cost_usd"} <= set(df.columns):
        gross = pd.to_numeric(df["gross_value_usd"], errors="coerce")
        cost = pd.to_numeric(df["total_cost_usd"], errors="coerce")
        df["cost_revenue_ratio"] = (cost / gross).where(gross > 0)
    else:
        df["cost_revenue_ratio"] = float("nan")
    return df


@st.cache_data(show_spinner=False)
def _taxonomy_counts(path: str, mtime: float) -> Dict[str, int]:
    """`spectral_type_source` value counts from the catalog, for the provenance panel.

    Reads ONE column of a file that runs to 862 MB, which is what makes this
    cheap enough to do on every page render. `mtime` is a cache-key argument as
    in `_read_name_column`.
    """
    try:
        col = pd.read_csv(path, usecols=["spectral_type_source"], low_memory=False)
    except Exception:
        return {}
    return (col["spectral_type_source"].fillna("unknown").astype(str)
            .value_counts().to_dict())


def render_provenance() -> None:
    """How much of this catalog's taxonomy was MEASURED rather than guessed.

    The documented failure mode here is a source that fails soft: an outage does
    not shrink the catalog, it inflates it with taxonomy inferred from albedo, so
    two runs stop being comparable with nothing in the log saying so. The SsODNet
    regression was invisible for exactly this reason. Row counts cannot detect
    it; `spectral_type_source` can.
    """
    path = os.path.join(MASTER.output_dir, MASTER.catalog.catalog_filename)
    if not os.path.exists(path):
        return
    counts = _taxonomy_counts(path, os.path.getmtime(path))
    if not counts:
        return

    total = sum(counts.values()) or 1
    guessed = (counts.get("albedo", 0) + counts.get("unknown", 0)) / total
    alarming = guessed > 0.75

    with st.expander(f"Catalog provenance: {1 - guessed:.0%} of taxonomy "
                     f"measured, {guessed:.0%} guessed", expanded=alarming):
        st.dataframe(
            pd.DataFrame(sorted(counts.items(), key=lambda kv: -kv[1]),
                         columns=["spectral_type_source", "asteroids"]),
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "`source` and `tholen` are measured; `albedo` is inferred and "
            "`unknown` is neither. A data source that fails soft does not "
            "shrink the catalog, it inflates it with guessed taxonomy, which is "
            "why row counts cannot detect the problem and this can."
        )
        if alarming:
            st.warning(
                f"**{guessed:.0%} of this catalog's taxonomy is guessed from "
                "albedo.** That is the signature of a small run or a source "
                "outage, since SsODNet carries most of the measured taxonomy. "
                "Do not compare these numbers to a committed result: the "
                "population is not the same one.",
                icon="⚠️",
            )


HEADLINE_COLUMNS = [
    "designation", "name", "spectral_type", "cost_revenue_ratio",
    "concentration_ratio", "beneficiation", "vehicle", "propellant",
    "delivery_arch", "aerocapture_return", "isru_return", "rendezvous_apsis",
    "max_payload_kg", "gross_value_usd", "total_cost_usd", "profit_usd",
    "mission_duration_yr", "dv_out_m_s", "dv_ret_m_s", "diameter_km",
    "semi_major_axis_au", "is_neo", "viable",
    # Present only in a catalog built by Stage 1 v1.2.0 or later, and dropped
    # silently by `_render_table` when they are not. Listed here rather than
    # left to the "119 more available" expander because how well an orbit is
    # known is a property of the RANKING, not a detail of one row: the top of
    # this table is 3.1x enriched in bodies whose orbits are provisional.
    "orbit_condition_code", "observation_arc_days", "n_observations",
]


def render_results(df: pd.DataFrame) -> None:
    """The four headline metrics, then the table, charts and drilldown.

    ⚠️  `cost_revenue_ratio` is computed HERE, by `load_results`; it is not a
    column the pipeline writes. The objective Stage 4 actually ranks on is
    `total_cost_usd / gross_value_usd`, and a harness that went looking for a
    column by this name is entry 7 in `verify.py`'s table of harness bugs.
    """
    ranked = df.dropna(subset=["cost_revenue_ratio"]).sort_values("cost_revenue_ratio")
    n_viable = int(df["viable"].sum()) if "viable" in df.columns else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Asteroids evaluated", f"{len(df):,}")
    c2.metric("Viable missions", NA if n_viable is None else f"{n_viable:,}")
    if not ranked.empty:
        best = ranked.iloc[0]
        c3.metric("Best cost / revenue", f"{best['cost_revenue_ratio']:,.2f}×",
                  help="Lower is better. 1.0 is breakeven.")
        c4.metric("Best target",
                  str(best.get("name") or best.get("designation") or NA),
                  help=f"{best.get('spectral_type', '?')}-type, "
                       f"{best.get('vehicle', '?')} / {best.get('propellant', '?')}")

    if n_viable == 0:
        st.info(
            "**Zero viable missions is the correct answer**, not a regression. "
            "A default run produces zero, and so does every other combination "
            "currently in the model. Rank by cost/revenue to see how close the "
            "best target gets.",
            icon="ℹ️",
        )

    tab_table, tab_charts, tab_drill = st.tabs(
        ["📊 Ranked table", "📈 Charts", "🔎 One asteroid"])
    with tab_table:
        _render_table(ranked)
    with tab_charts:
        _render_charts(ranked)
    with tab_drill:
        _render_drilldown(ranked)


def _search_mask(view: pd.DataFrame, needle: str) -> pd.Series:
    """Case-insensitive substring match over designation and name.

    regex=False throughout: designations carry regex metacharacters, so
    "(1) Ceres" against a regex engine is either a wrong match or a raise. The
    mask is built on `view.index` so a missing column cannot misalign it.
    """
    mask = pd.Series(False, index=view.index)
    for col in ("designation", "name"):
        if col in view.columns:
            mask |= (view[col].astype(str).str.lower()
                     .str.contains(needle, regex=False, na=False))
    return mask


def _render_table(ranked: pd.DataFrame) -> None:
    """The ranked results table, with the spectral-type, search and top-N filters.

    Ranked ascending by cost/revenue rather than by `profit_usd`, and the
    caption says why: revenue sits far below cost in most configurations, so a
    profit ranking is a Delta-v table in disguise. The row search passes
    `regex=False`, the same trap the pipeline's own lookup helpers hit, because
    designations carry regex metacharacters.
    """
    st.caption(
        "Ranked by **cost / revenue**, ascending: lower is better, 1.0 is "
        "breakeven. Not by `profit_usd`, because revenue is far below cost in "
        "most configurations, so a profit ranking is a Δv table in disguise."
    )

    f1, f2, f3 = st.columns([2, 2, 1])
    types = (sorted(ranked["spectral_type"].dropna().astype(str).unique())
             if "spectral_type" in ranked.columns else [])
    picked = f1.multiselect("Spectral type", types, default=[])
    search = f2.text_input("Search designation / name", "",
                           placeholder="e.g. Bennu, 7753, Wilson")
    top_n = int(f3.number_input("Show top", min_value=5, max_value=5_000,
                                value=50, step=25))

    view = ranked
    if picked:
        view = view[view["spectral_type"].astype(str).isin(picked)]
    if search.strip():
        view = view[_search_mask(view, search.strip().lower())]

    headline = [c for c in HEADLINE_COLUMNS if c in view.columns]
    extra = [c for c in view.columns if c not in headline]
    with st.expander(f"Columns  ({len(headline)} shown, {len(extra)} more available)"):
        chosen = st.multiselect("Displayed columns", headline + extra,
                                default=headline)
    cols = chosen or headline

    st.dataframe(
        view[cols].head(top_n), use_container_width=True, hide_index=True,
        column_config={
            "cost_revenue_ratio": st.column_config.NumberColumn(
                "cost/rev", format="%.2f×",
                help="total_cost_usd / gross_value_usd. Lower is better."),
            "gross_value_usd": st.column_config.NumberColumn("gross $", format="$%.3g"),
            "total_cost_usd": st.column_config.NumberColumn("cost $", format="$%.3g"),
            "profit_usd": st.column_config.NumberColumn("profit $", format="$%.3g"),
            "max_payload_kg": st.column_config.NumberColumn("payload kg", format="%.0f"),
            "concentration_ratio": st.column_config.NumberColumn("conc", format="%.1f×"),
        },
    )
    st.caption(f"{len(view):,} rows match, showing {min(top_n, len(view)):,}.")
    st.download_button(
        "⬇️  Download filtered rows as CSV",
        view[cols].to_csv(index=False).encode("utf-8"),
        file_name="profitability_filtered.csv", mime="text/csv",
    )


def _render_charts(ranked: pd.DataFrame) -> None:
    """Altair charts over the ranked rows: the distribution and the trade-offs.

    Altair ships with Streamlit, so this adds no requirement. The row slider is
    clamped rather than trusted: a slider whose min exceeds its max, or whose
    value sits below its min, raises outright, and with fewer than 50 rows there
    is nothing to choose anyway.
    """
    if ranked.empty:
        st.info("Nothing to chart.")
        return

    import altair as alt          # ships with streamlit; no new requirement

    # A slider whose min exceeds its max, or whose value sits below its min,
    # raises. With fewer than 50 rows there is nothing to choose anyway.
    total = len(ranked)
    if total > 50:
        n = st.slider("Chart the best N targets", 50, min(5_000, total),
                      min(500, total), step=50)
    else:
        n = total
    view = ranked.head(n)

    st.markdown("##### Cost/revenue against outbound Δv")
    st.caption(
        "Accessibility and value are only loosely coupled: the ranking responds "
        "to composition too, which is the whole reason Δv is per-asteroid. A "
        "vertical stripe here means Δv has collapsed to one value and "
        "`use_per_asteroid_dv` is off."
    )
    if {"dv_out_m_s", "cost_revenue_ratio"} <= set(view.columns):
        st.altair_chart(
            alt.Chart(view).mark_circle(size=45, opacity=0.55).encode(
                x=alt.X("dv_out_m_s:Q", title="Δv outbound (m/s)",
                        scale=alt.Scale(zero=False)),
                y=alt.Y("cost_revenue_ratio:Q",
                        title="cost / revenue (lower better)",
                        scale=alt.Scale(type="log")),
                color=alt.Color("spectral_type:N", title="type"),
                tooltip=[c for c in ("designation", "name", "spectral_type",
                                     "cost_revenue_ratio", "vehicle",
                                     "propellant", "max_payload_kg")
                         if c in view.columns],
            ).interactive().properties(height=380),
            use_container_width=True,
        )

    left, right = st.columns(2)

    with left:
        st.markdown("##### Best cost/revenue by spectral type")
        if "spectral_type" in view.columns:
            by_type = (
                view.groupby(view["spectral_type"].astype(str))
                .agg(best=("cost_revenue_ratio", "min"),
                     count=("cost_revenue_ratio", "size"))
                .reset_index().rename(columns={"spectral_type": "type"})
            )
            # A DOT plot, not bars, and the reason is a bug this chart shipped
            # with: a bar is drawn from an implicit zero baseline, log(0) is
            # -inf, so `mark_bar` on a log scale renders an axis, a legend, five
            # labels and NO BARS. The spread here runs from ~18x to ~1e5, which
            # is exactly the range that needs a log axis, so the mark is what
            # gives way. Size carries the population behind each best, which a
            # bar could not show at all.
            st.altair_chart(
                alt.Chart(by_type).mark_circle(opacity=0.85).encode(
                    x=alt.X("best:Q", title="best cost/revenue (lower better)",
                            scale=alt.Scale(type="log")),
                    y=alt.Y("type:N", sort="x", title=None),
                    size=alt.Size("count:Q", title="targets"),
                    tooltip=["type", "best", "count"],
                ).properties(height=340),
                use_container_width=True,
            )
            st.caption(
                "One dot per spectral type at its best target. The dot is "
                "sized by how many targets of that type the run evaluated, so "
                "a large dot far right is a well-sampled type that simply does "
                "not pay, and a small dot on the left is one good body rather "
                "than a good class."
            )

    with right:
        st.markdown("##### What the architecture search chose")
        st.caption("If every row picks the same option, the search is costing "
                   "runtime and buying nothing.")
        picks = [
            {"axis": axis, "choice": str(choice), "n": int(count)}
            for col, axis in (("vehicle", "Vehicle"),
                              ("propellant", "Propellant"),
                              ("aerocapture_return", "Aerocapture"),
                              ("isru_return", "ISRU"),
                              ("rendezvous_apsis", "Rendezvous apsis"))
            if col in view.columns
            for choice, count in view[col].astype(str).value_counts().items()
        ]
        if picks:
            st.altair_chart(
                alt.Chart(pd.DataFrame(picks)).mark_bar().encode(
                    x=alt.X("n:Q", stack="normalize", title="share of targets"),
                    y=alt.Y("axis:N", title=None),
                    color=alt.Color("choice:N", title="choice"),
                    tooltip=["axis", "choice", "n"],
                ).properties(height=340),
                use_container_width=True,
            )


_COST_LEDGER = [
    ("launch_cost_usd", "Launch"),
    ("outbound_prop_cost_usd", "Outbound propellant"),
    ("return_prop_cost_usd", "Return propellant"),
    ("hardware_cost_usd", "Spacecraft hardware"),
    ("mining_rig_cost_usd", "Mining rig (amortised)"),
    ("capsule_cost_usd", "Return capsule"),
    ("power_system_cost_usd", "Power system"),
    ("ep_system_cost_usd", "Electric propulsion stage"),
    ("heat_shield_cost_usd", "Heat shield"),
    ("recovery_cost_usd", "Recovery"),
    ("ops_cost_usd", "Operations"),
    ("liability_cost_usd", "Liability"),
    ("licensing_cost_usd", "Licensing"),
    ("launch_insurance_cost_usd", "Launch insurance"),
    ("nre_cost_usd", "NRE"),
    ("autonomy_nre_cost_usd", "Autonomy NRE"),
    ("contingency_cost_usd", "Contingency"),
    ("rig_terminal_value_usd", "Rig terminal value (credit)"),
]

_MASS_CASCADE = [
    ("m_launch_kg", "Launch mass"),
    ("m_outbound_prop_kg", "Outbound propellant"),
    ("m_at_asteroid_kg", "Mass at asteroid"),
    ("hardware_total_kg", "Hardware total"),
    ("power_system_kg", "Power system"),
    ("ep_system_kg", "Electric propulsion system"),
    ("m_return_prop_kg", "Return propellant"),
    ("m_dry_return_kg", "Return vehicle dry"),
    ("tps_mass_kg", "Thermal protection"),
    ("max_payload_kg", "Payload delivered"),
]

_MODEL_TERMS = [
    ("saturation_multiplier", "Market saturation multiplier"),
    ("p_success", "Overall mission reliability"),
    ("p_mining", "Mining reliability (programme mean)"),
    ("learning_curve_factor", "Learning curve factor"),
    ("boiloff_factor", "Cryogenic boil-off factor"),
    ("wacc_multiplier", "WACC multiplier (weighted)"),
    ("missions_sharing_rig", "Missions sharing the rig"),
    ("synodic_period_yr", "Synodic period (yr)"),
    ("launch_window_wait_yr", "Launch-window wait (yr)"),
    ("water_liberated_kg", "Water liberated (kg)"),
    ("ep_power_w", "EP power (W)"),
    ("processing_power_w", "Processing power (W)"),
]


def _cell(row: pd.Series, key: str, default: Any = None) -> Any:
    """One value off a result row, with NaN normalised to `default`.

    Both halves matter: a column absent from an older catalog and a column
    present but null must read the same way, or the drilldown renders `nan` for
    a field the run simply never computed.
    """
    value = row.get(key, default)
    return default if pd.isna(value) else value


def _numeric_table(row: pd.Series, fields: Iterable[Tuple[str, str]],
                   columns: Tuple[str, str], fmt: str) -> None:
    """Two-column table of labelled numbers pulled off one result row."""
    data = [(label, float(_cell(row, key, 0.0)))
            for key, label in fields if key in row.index]
    st.dataframe(
        pd.DataFrame(data, columns=list(columns)),
        use_container_width=True, hide_index=True,
        column_config={columns[1]: st.column_config.NumberColumn(format=fmt)},
    )


ORBITAL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "research", "starred-repos", "orbital.py")

# The elements a picture of an orbit needs. Stage 4 carries only
# `semi_major_axis_au` through to the profitability catalog, so the rest are
# read back out of the Stage 1 catalog on demand.
_ELEMENT_COLUMNS = ["designation", "semi_major_axis_au", "eccentricity",
                    "inclination_deg", "longitude_asc_node_deg",
                    "arg_perihelion_deg"]

# HOW WELL THE ORBIT ABOVE IS KNOWN, which catalog v1.2.0 added and which no
# catalog built before it carries. Optional for exactly that reason: an 862 MB
# CSV written by an older Stage 1 has none of these columns, and naming a
# missing column in `usecols` is a ValueError rather than a NaN.
#
# It earns a panel of its own because of what research/starred-repos found:
# the top 30 of this ranking runs 43.3% at condition code 5 or worse against
# 13.9% of the population, a 3.1x enrichment at p = 8.3e-05, and the effect
# disappears further down the ranking. Selecting the extreme of a ranking
# derived from noisy elements preferentially selects the bodies whose fit
# errors flatter them, so a rank-1 result with U = 7 is a different kind of
# claim from a rank-1 result with U = 0.
_ORBIT_QUALITY_COLUMNS = ["orbit_condition_code", "observation_arc_days",
                          "n_observations"]


@st.cache_resource(show_spinner=False)
def orbital_module():
    """`research/starred-repos/orbital.py`, or None if it is not there.

    Imported by path rather than restated, because that file already carries a
    Kepler solver and an `elements_to_state` adapted from skyfield with the
    attribution recorded in CITATIONS.md. A second copy of the same rotation
    would be one more thing to keep in step, and the ATTRIBUTION would be on
    the copy nobody reads.

    `spec_from_file_location` is entry 5 in verify.py's table of harness bugs,
    but that entry is about a WORKER re-importing master; this is the parent
    process importing a numpy-only leaf module whose directory has a hyphen in
    it, which no plain import statement can name.
    """
    if not os.path.exists(ORBITAL_PATH):
        return None
    try:
        import importlib.util                       # noqa: PLC0415
        spec = importlib.util.spec_from_file_location("_ui_orbital", ORBITAL_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


@st.cache_data(show_spinner="Reading orbital elements ...")
def orbit_elements(path: str, mtime: float,
                   designations: Tuple[str, ...]) -> pd.DataFrame:
    """The elements for the given bodies, out of the Stage 1 catalog.

    Six columns of an 862 MB CSV is a ~7 s read, so it is filtered down to the
    bodies actually on screen and cached on the file's mtime. `mtime` is a
    cache key and is not read in the body, as in `_read_name_column`.
    """
    try:
        # The header first, because `usecols` raises on a column the file does
        # not have, and the orbit-quality trio only exists in a catalog built
        # by Stage 1 v1.2.0 or later.
        available = set(pd.read_csv(path, nrows=0).columns)
        wanted_cols = [c for c in _ELEMENT_COLUMNS + _ORBIT_QUALITY_COLUMNS
                       if c in available]
        if not set(_ELEMENT_COLUMNS) <= available:
            return pd.DataFrame(columns=_ELEMENT_COLUMNS)
        df = pd.read_csv(path, usecols=wanted_cols, low_memory=False)
    except Exception:
        return pd.DataFrame(columns=_ELEMENT_COLUMNS)
    wanted = df["designation"].astype(str).isin(set(designations))
    return df.loc[wanted].drop_duplicates("designation").reset_index(drop=True)


def _ellipse(orbital, a_au: float, e: float, i_deg: float,
             raan_deg: float, argp_deg: float, label: str) -> pd.DataFrame:
    """One closed orbit as 361 ecliptic points, in AU.

    `elements_to_state` is called with `a` in AU rather than km: the shape of
    the conic is `p / (1 + e cos nu)` and scales with `a`, so the position comes
    back in whatever unit went in. Only the VELOCITY it also returns would care
    about mu, and nothing here reads it.
    """
    import numpy as np                              # noqa: PLC0415
    nu = np.linspace(0.0, 2.0 * np.pi, 361)
    r, _v = orbital.elements_to_state(
        a_au, e, np.radians(i_deg), np.radians(raan_deg),
        np.radians(argp_deg), nu)
    return pd.DataFrame({"x": r[0], "y": r[1], "z": r[2],
                         "body": label, "step": range(len(nu))})


def _orbit_kind(body: str, target: str) -> str:
    """Which of the two roles a drawn orbit plays: target, or reference.

    Drives a dash pattern rather than only a colour, so which line is the
    subject survives a colour-blind reader, a light theme and a greyscale
    screenshot. Colour alone had Mars and the asteroid within one hue of each
    other at a two-pixel stroke.
    """
    return "target" if body == target else "reference"


def _render_orbit_quality(e_row: pd.Series) -> None:
    """How well this body's orbit is actually known, when the catalog says.

    Delta-v comes from a, e and i; the whole economic ranking comes from
    Delta-v. So a cost/revenue ratio quoted to six figures against a 32-day
    observation arc is a different claim from the same figure against a
    70-year one, and until Stage 1 v1.2.0 the catalog carried nothing that
    could tell the two apart.

    Says so plainly when the columns are absent rather than rendering nothing,
    because "this catalog cannot answer that" is the answer, and a silent gap
    reads as a clean bill of health.
    """
    if "orbit_condition_code" not in e_row.index:
        st.caption(
            "This catalog carries no orbit-quality columns, so how well the "
            "elements above are known is unknown. Stage 1 v1.2.0 added "
            "`orbit_condition_code`, `observation_arc_days` and "
            "`n_observations`; a catalog built before it, like the one on "
            "disk here, predates them."
        )
        return

    def _number(key):
        """One orbit-quality field as a float, or None if it is not one.

        Stage 1 coerces all three to numeric, so a non-numeric MPC code arrives
        as NaN and `pd.isna` is enough. Read defensively anyway: no catalog on
        this machine has these columns yet, so this branch has never run
        against real data, and a drilldown that raises is a worse answer than
        one that says it does not know.
        """
        value = e_row.get(key)
        try:
            return None if pd.isna(value) else float(value)
        except (TypeError, ValueError):
            return None

    code = _number("orbit_condition_code")
    arc = _number("observation_arc_days")
    obs = _number("n_observations")

    cols = st.columns(3)
    cols[0].metric("Orbit condition code U",
                   NA if code is None else str(int(code)),
                   help="MPC orbit uncertainty, 0 = well determined, "
                        "9 = barely constrained.")
    cols[1].metric("Observation arc",
                   NA if arc is None else f"{arc:,.0f} days")
    cols[2].metric("Observations", NA if obs is None else f"{obs:,.0f}")
    known = None if code is None else int(code)

    if known is not None and known >= 5:
        st.warning(
            f"**U = {known}: this orbit is provisional.** Delta-v comes from "
            "a, e and i, and the ranking comes from Delta-v, so a body this "
            "poorly determined can be flattered by its own fit errors. "
            "research/starred-repos measured the top 30 of this ranking at "
            "43.3% U >= 5 against 13.9% of the population, and the enrichment "
            "vanishes further down, which is the signature of a winner's "
            "curse rather than a bad catalog.",
            icon="⚠️",
        )


def _render_orbit(row: pd.Series) -> None:
    """Where this body actually is, drawn from its own elements.

    The one thing the tables cannot show: two targets with the same Delta-v can
    be a nearly circular body just outside Earth's orbit and a steeply inclined
    one crossing it, and which of those you are looking at is the whole story
    of the mission. Technique from typpo/spacekit (MIT), which solves Kepler
    per body to draw a million at once; here it is one body at a time, so numpy
    and Altair are enough and no WebGL is needed.

    Earth and Mars are drawn as CIRCLES because that is what the model assumes:
    `A_MARS_AU` is a semi-major axis used as a circular orbit radius in
    `_asteroid_to_mars_dv_km_s`, and the Earth legs work in canonical units
    where Earth's orbit is the unit circle. A truer ellipse for either would
    make the picture disagree with the numbers beside it.
    """
    orbital = orbital_module()
    if orbital is None:
        return

    designation = str(_cell(row, "designation", "") or "")
    if not designation:
        return

    catalog = os.path.join(MASTER.output_dir, MASTER.catalog.catalog_filename)
    if not os.path.exists(catalog):
        st.caption("The orbit diagram needs the Stage 1 catalog, which is not "
                   "on disk. Everything above comes from the Stage 4 output.")
        return

    elements = orbit_elements(catalog, os.path.getmtime(catalog), (designation,))
    if elements.empty:
        st.caption(f"`{designation}` is not in the Stage 1 catalog on disk, so "
                   "there are no elements to draw. That happens when the "
                   "profitability catalog came from a different run.")
        return

    import altair as alt                             # noqa: PLC0415
    e_row = elements.iloc[0]
    a_au = float(e_row["semi_major_axis_au"])
    ecc = float(e_row["eccentricity"])
    inc = float(e_row["inclination_deg"])

    orbits = pd.concat([
        _ellipse(orbital, 1.0, 0.0, 0.0, 0.0, 0.0, "Earth"),
        _ellipse(orbital, master.A_MARS_AU, 0.0, 0.0, 0.0, 0.0, "Mars"),
        _ellipse(orbital, a_au, ecc, inc,
                 float(e_row["longitude_asc_node_deg"]),
                 float(e_row["arg_perihelion_deg"]), designation),
    ], ignore_index=True)
    orbits["kind"] = [_orbit_kind(b, designation) for b in orbits["body"]]

    # Perihelion is nu = 0 and aphelion nu = pi, which are steps 0 and 180 of
    # the 361 sampled above. Marking the one the search CHOSE is the point:
    # `rendezvous_apsis` is a decision the model makes per body AND per
    # destination, and as a word in a table it is invisible.
    target = orbits[orbits["body"] == designation].reset_index(drop=True)
    apsis = str(_cell(row, "rendezvous_apsis", "") or "").lower()
    marks = pd.DataFrame([
        {"x": target.loc[0, "x"], "y": target.loc[0, "y"],
         "z": target.loc[0, "z"], "point": "perihelion"},
        {"x": target.loc[180, "x"], "y": target.loc[180, "y"],
         "z": target.loc[180, "z"], "point": "aphelion"},
    ])
    # A STRING rather than the boolean this started as: the legend renders the
    # encoded values verbatim, so a boolean column labelled the two apsides
    # "true" and "false" under a heading of "rendezvous", which is a caption
    # nobody can read without the source.
    marks["role"] = [("met here" if p == apsis else "other apsis")
                     for p in marks["point"]]

    span = float(max(orbits[["x", "y"]].abs().to_numpy().max(),
                     master.A_MARS_AU)) * 1.1
    domain = [-span, span]

    def _plane(horiz: str, vert: str, title: str):
        """One projection of the three orbits, with the sun and the apsides."""
        line = alt.Chart(orbits).mark_line(strokeWidth=2).encode(
            x=alt.X(f"{horiz}:Q", title=f"{horiz.upper()} (AU)",
                    scale=alt.Scale(domain=domain, nice=False)),
            y=alt.Y(f"{vert}:Q", title=f"{vert.upper()} (AU)",
                    scale=alt.Scale(domain=domain, nice=False)),
            order="step:Q",
            color=alt.Color("body:N", title=None,
                            sort=["Earth", "Mars", designation],
                            scale=alt.Scale(
                                domain=["Earth", "Mars", designation],
                                range=["#4c78a8", "#9d6b53", "#e45756"])),
            strokeDash=alt.StrokeDash(
                "kind:N", legend=None,
                scale=alt.Scale(domain=["reference", "target"],
                                range=[[4, 3], [1, 0]])),
            tooltip=["body:N"],
        )
        sun = alt.Chart(pd.DataFrame([{"x": 0.0, "y": 0.0, "z": 0.0}])).mark_point(
            shape="circle", size=90, filled=True, color="#f5b301").encode(
            x=f"{horiz}:Q", y=f"{vert}:Q")
        apsides = alt.Chart(marks).mark_point(
            shape="diamond", filled=True, size=110).encode(
            x=f"{horiz}:Q", y=f"{vert}:Q",
            color=alt.Color("role:N", title="apsis",
                            scale=alt.Scale(domain=["met here", "other apsis"],
                                            range=["#f2f2f2", "#8c8c8c"])),
            tooltip=["point:N", "role:N"])
        # `resolve_scale(color="independent")` is load-bearing, not tidying.
        # Layered charts share a scale per channel by default, so the apsis
        # layer's explicit colour domain swallowed the orbit layer's:
        # "Earth", "Mars" and the designation were all off-domain, drew with no
        # colour at all, and the chart rendered as a sun and two diamonds with
        # the orbits invisible and no error anywhere.
        return (line + sun + apsides).resolve_scale(
            color="independent").properties(width=330, height=330, title=title)

    st.markdown("#### Where it is")
    left_panel, right_panel = st.columns(2)
    # Explicit equal width and height on a SHARED domain, rather than
    # use_container_width: an orbit drawn on unequal axes is a picture of a
    # different orbit, and the edge-on panel is legible at all only because it
    # shares the top-down panel's scale.
    with left_panel:
        st.altair_chart(_plane("x", "y", "Looking down on the ecliptic"))
    with right_panel:
        st.altair_chart(_plane("x", "z", "Edge on: the inclination"))

    st.caption(
        f"**a** {a_au:,.3f} AU  |  **e** {ecc:,.4f}  |  **i** {inc:,.2f} deg  "
        f"|  perihelion {a_au * (1 - ecc):,.3f} AU  |  aphelion "
        f"{a_au * (1 + ecc):,.3f} AU. A flat line in the right-hand panel is a "
        "body in the ecliptic; a tall one is the plane change the Delta-v model "
        "is charging for. The pale diamond is the apsis the architecture "
        "search chose to meet it at, which CLAUDE.md is emphatic "
        "must stay a search and not a rule: at a = 0.6, e = 0.8 the old "
        "aphelion-if-above-1-AU rule cost 18.5 km/s outbound where perihelion "
        "needs 12.1."
    )
    _render_orbit_quality(e_row)

    st.caption(
        "Earth and Mars are circles at 1.000 and "
        f"{master.A_MARS_AU:,.3f} AU because that is what the Delta-v model "
        "assumes; a truer ellipse here would disagree with the numbers above. "
        "The node and the argument of perihelion are read from the Stage 1 "
        "catalog, which is the only place they survive."
    )


def _render_drilldown(ranked: pd.DataFrame) -> None:
    """One asteroid at a time: its mission, mass cascade, cost lines and payload.

    Capped at the top 300 rows, because the picker is a selectbox and the label
    for each entry is built eagerly; the full ranking is the table's job.
    """
    if ranked.empty:
        st.info("Nothing to drill into.")
        return

    top = ranked.head(300)
    labels = [
        f"{i + 1}.  {row.get('name') or row.get('designation')}  "
        f"({row.get('spectral_type', '?')})  ·  {row['cost_revenue_ratio']:,.2f}×"
        for i, (_, row) in enumerate(top.iterrows())
    ]
    pick = st.selectbox("Target", range(len(labels)), format_func=lambda i: labels[i])
    row = top.iloc[pick]

    st.markdown(f"### {_cell(row, 'name') or _cell(row, 'designation')}")

    m = st.columns(5)
    m[0].metric("cost / revenue", f"{row['cost_revenue_ratio']:,.2f}×")
    m[1].metric("Payload", f"{_cell(row, 'max_payload_kg', 0):,.0f} kg")
    m[2].metric("Gross value", f"${_cell(row, 'gross_value_usd', 0):,.0f}")
    m[3].metric("Total cost", f"${_cell(row, 'total_cost_usd', 0):,.0f}")
    m[4].metric("Duration", f"{_cell(row, 'mission_duration_yr', 0):,.1f} yr")

    left, right = st.columns(2)

    with left:
        st.markdown("#### Chosen architecture")
        st.dataframe(
            pd.DataFrame([
                ("Destination", _cell(row, "delivery_destination", NA)),
                ("Architecture", _cell(row, "delivery_arch", NA)),
                ("Vehicle", _cell(row, "vehicle", NA)),
                ("Propellant", f"{_cell(row, 'propellant', NA)}  "
                               f"(Isp {_cell(row, 'isp_s', 0):,.0f} s)"),
                ("Return mode", "aerocapture" if _cell(row, "aerocapture_return")
                                else "propulsive"),
                ("Return propellant", "ISRU (hydrolox, made on site)"
                 if _cell(row, "isru_return") else "brought from Earth"),
                ("Rendezvous apsis", _cell(row, "rendezvous_apsis", NA)),
                ("Electric propulsion", "yes" if _cell(row, "is_electric") else "no"),
                ("Beneficiation", f"{_cell(row, 'concentration_ratio', 0):,.2f}×"
                 if _cell(row, "beneficiation") else "declined"),
                ("Δv out / return", f"{_cell(row, 'dv_out_m_s', 0):,.0f} / "
                                    f"{_cell(row, 'dv_ret_m_s', 0):,.0f} m/s"),
            ], columns=["", "value"]),
            use_container_width=True, hide_index=True,
        )

        st.markdown("#### Payload mix")
        mix = str(_cell(row, "payload_mix", "") or "")
        if mix:
            rows = []
            for part in (p.strip() for p in mix.split(";")):
                if part:
                    phase, _, mass = part.rpartition(" ")
                    rows.append({"phase": phase, "mass": mass})
            st.dataframe(pd.DataFrame(rows), use_container_width=True,
                         hide_index=True)
            st.caption(
                f"Dominant phase: **{_cell(row, 'payload_dominant_phase', NA)}** "
                f"at {float(_cell(row, 'payload_dominant_frac', 0)):.1%} of the "
                "hold. The mix is a fractional knapsack over the phases actually "
                "present, not a shopping list."
            )
        else:
            st.caption("Flown as bulk material, so no beneficiation and no mix.")

        st.markdown("#### Composition")
        _numeric_table(
            row, [(k, k.replace("comp_", "").replace("_", " "))
                  for k in ("comp_metal_fraction", "comp_silicate_fraction",
                            "comp_carbon_fraction", "comp_ice_fraction",
                            "comp_pgm_enrichment")],
            ("fraction", "value"), "%.4g")
        st.caption("Composition fractions sum to 0.76 to 0.96, not 1.0. The "
                   "residual is valued at a bulk-silicate floor, not zero.")

    with right:
        st.markdown("#### Cost ledger")
        ledger = [(label, float(_cell(row, key, 0.0)))
                  for key, label in _COST_LEDGER if key in row.index]
        ledger_df = pd.DataFrame([lv for lv in ledger if abs(lv[1]) > 0],
                                 columns=["line", "usd"])
        total = float(_cell(row, "total_cost_usd", 0.0)) or 1.0
        ledger_df["share"] = ledger_df["usd"] / total
        st.dataframe(
            ledger_df.sort_values("usd", key=abs, ascending=False),
            use_container_width=True, hide_index=True,
            column_config={
                "usd": st.column_config.NumberColumn("USD", format="$%.4g"),
                "share": st.column_config.ProgressColumn(
                    "share of total", format="%.1f%%",
                    min_value=0.0, max_value=1.0),
            },
        )

        st.markdown("#### Mass cascade")
        _numeric_table(row, _MASS_CASCADE, ("component", "kg"), "%.1f")
        st.caption(
            "Every kilogram here should have a line in the ledger opposite. A "
            "mass that flies free is this codebase's signature bug: it is how "
            "the electric stage went unbilled until v1.10.0."
        )

        st.markdown("#### Model terms")
        _numeric_table(row, _MODEL_TERMS, ("term", "value"), "%.4g")

    st.divider()
    _render_orbit(row)

    with st.expander("Every column for this row"):
        st.dataframe(
            pd.DataFrame({"field": row.index, "value": row.astype(str).values}),
            use_container_width=True, hide_index=True, height=420,
        )


# ═════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═════════════════════════════════════════════════════════════════════════════

def _runtime_estimate(selected: Sequence[str]) -> str:
    """Rough wall-clock estimate, from the timings recorded in CLAUDE.md."""
    minutes = sum(_stage_minutes(k) for k in selected)
    if minutes < 1:
        return "under a minute"
    if minutes < 90:
        return f"~{minutes:.0f} min"
    return f"~{minutes / 60:.1f} h"


def render_sidebar() -> None:
    """Destination, stage selection, row caps, the runtime estimate and the run button.

    Two things here are deliberate and easy to undo by accident. The destination
    selectbox seeds from the CATALOG ON DISK rather than from the config
    default, because calc defaults to `earth_surface` while the catalog is
    almost always `cislunar`, and seeding from the config made a freshly-opened
    page disagree with its own data, mark Stage 2 stale, and turn the first
    click of "Run pipeline" into a live re-price nobody asked for. And a cached
    stage defaults to OFF unless it is Stage 4, because Stages 1-3 all FETCH,
    and each overwrites the only copy of its CSV.
    """
    st.sidebar.title("🪐 Asteroid pipeline")

    # Covers both "not seeded yet" and "seeded with something no longer legal",
    # either of which makes selectbox raise rather than fall back.
    #
    # SEEDED FROM THE CATALOG ON DISK, not from the config default, and that is
    # the difference between opening this page and destroying your inputs.
    # calc's default is `earth_surface` while the catalog here is almost always
    # `cislunar`, so seeding from the config made the freshly-opened page
    # disagree with its own data -- which marks Stage 2 stale, forces it back
    # on, and makes the very first click of "Run pipeline" re-fetch live metal
    # prices for a destination nobody chose. The old prices do not come back.
    #
    # This is NOT the silent adoption run_pipeline.py deliberately refuses: the
    # value lands in a selectbox the user is looking at, under a caption saying
    # it matches the data on disk. Headless, the right answer is to refuse and
    # say so; here, it is to show the truth and let them change it.
    cached_dest = cached_mineral_destination()
    if st.session_state.get("destination") not in DESTINATIONS:
        st.session_state["destination"] = (
            cached_dest if cached_dest in DESTINATIONS
            else MASTER.delivery_destination)
    st.sidebar.selectbox(
        "Delivery destination", DESTINATIONS, key="destination",
        help="Sets Stage 2 pricing AND Stage 4 architecture together. They are "
             "meaningless apart, so the UI writes both through "
             "MASTER_CONFIG.delivery_destination.",
    )
    destination = st.session_state["destination"]
    # Derived, never stored: a flag set at seeding time would still be claiming
    # "preselected" after the user had picked something else.
    if cached_dest and destination == cached_dest:
        st.sidebar.caption(
            "Matches the catalog already on disk, so Stage 2 does not need "
            "re-pricing. Changing it will force one."
        )

    st.sidebar.divider()
    st.sidebar.subheader("How big a run")
    st.sidebar.caption(
        "The same three presets `run.bat` and `run.sh` offer, imported from "
        "`run_pipeline.py` so they cannot drift apart. Each one writes the row "
        "caps and the two big flags; everything else is left alone, and you "
        "can still edit any dial afterwards on the Configure page."
    )
    # Stacked rather than in three columns: a sidebar is ~250 px wide, and
    # three columns truncated the labels to "Quick ...", "Stand...", "Full run",
    # which is a menu that hides which option you are choosing.
    for name in ("quick", "standard", "full"):
        if st.sidebar.button(PRESET_LABELS[name], key=f"preset::{name}",
                             use_container_width=True,
                             help=run_pipeline.PRESETS[name]["blurb"]):
            # Deferred for the same reason the reset is: apply_run_preset
            # clears widget-bound session keys, which is only legal before the
            # widgets for this run exist. main() handles the flag on entry.
            st.session_state["preset_requested"] = name
            st.rerun()
        st.sidebar.caption(preset_summary(name))
    # 0 means "no cap", so it is spelled as a phrase rather than run through
    # the same pluralisation as a count: the first version of this line read
    # "every evaluated rows".
    cap = effective("calc", "eval_row_cap") or 0
    if not cap:
        rows = "every row"
    else:
        rows = f"{cap:,} evaluated row" + ("" if cap == 1 else "s")
    st.sidebar.divider()
    st.sidebar.caption(
        f"**Currently set to {rows}**, "
        + ("beneficiated" if effective("calc", "use_beneficiation")
           else "run-of-mine ore") + ", "
        + ("programme search" if effective("calc", "optimise_programme_scale")
           else "single mission") + "."
    )

    st.sidebar.subheader("Stages to run")

    stale_mineral = bool(cached_dest and cached_dest != destination)
    selected: List[str] = []

    for stage in STAGES:
        status = stage.cache_status()
        if status:
            age_s, size_mb = status
            when = (f"{age_s / 3600:.1f} h ago" if age_s > 3600
                    else f"{age_s / 60:.0f} min ago")
            note = f"cached · {size_mb:.1f} MB · {when}"
            # Cached means REUSE, and only Stage 4 is exempt.
            #
            # Stages 1-3 fetch, so defaulting a cached one to "on" made the
            # first click of Run overwrite good data with today's download --
            # and this module's own docstring calls re-running Stage 4 against
            # a cached catalog "the normal working loop". The default now IS
            # that loop. Stage 4 fetches nothing and is the whole point of
            # pressing the button, so it stays on.
            default = stage.key == "calc"
        else:
            note = "not built, must run"
            default = True

        # A cached mineral catalog priced for a different destination is not a
        # cache, it is a trap. Force the re-run rather than let Stage 4 pair
        # cislunar prices with a Utah re-entry.
        forced = stage.key == "mineral" and stale_mineral
        if forced:
            note = f"⚠️ cached for **{cached_dest}**, must re-run"

        skey = f"stage::{stage.key}"
        if skey not in st.session_state:
            st.session_state[skey] = default
        if forced:
            # Legal because the widget for this run does not exist yet, and it
            # keeps the box from displaying unchecked while it is about to run.
            st.session_state[skey] = True

        if st.sidebar.checkbox(f"**{stage.number}. {stage.label}**", key=skey,
                               help=stage.blurb, disabled=forced):
            selected.append(stage.key)
        st.sidebar.caption(note)

    if stale_mineral:
        st.sidebar.warning(
            f"Stage 2 is cached for **{cached_dest}** but you have selected "
            f"**{destination}**. Re-running it is forced, because skipping "
            "would price the cargo at one destination and fly it to another. "
            "Note that it re-fetches **live** metal prices; see the caution "
            "below.",
            icon="⚠️",
        )

    # Stages 1-3 all FETCH, and each writes over the CSV already on disk. The
    # previous copy is the only copy: verify.py compares against baselines built
    # on those exact inputs, so refreshing them makes four cells stop
    # reproducing -- which looks precisely like a code regression and is not
    # one. That is a mistake somebody made here on 2026-08-23, by running
    # Stage 2 to look at a banner; CLAUDE.md carries the write-up. The CLI
    # spells this out in run_pipeline.py's refusal, and the front door should
    # not be the quieter of the two.
    _FETCHES = {
        "catalog":   "re-downloads the JPL catalog (~500 MB; JPL adds bodies "
                     "daily, so the population itself changes)",
        "mineral":   "re-fetches live metal prices",
        "transport": "re-fetches live commodity prices",
    }
    refetch = [st_ for st_ in STAGES[:3]
               if st_.key in selected and st_.cache_status()]
    if refetch:
        lines = "\n".join("- **Stage %d** %s"
                          % (st_.number, _FETCHES[st_.key])
                          for st_ in refetch)
        st.sidebar.warning(
            "This overwrites data already on disk:\n\n" + lines +
            "\n\nThe old values are **not recoverable**, and any verify.py "
            "baseline built on them will stop reproducing. Copy "
            "`asteroid_pipeline/*.csv` first if you may want to compare "
            "against them.",
            icon="🔄",
        )

    # Stage 4 reads what Stages 1-3 wrote, so a skipped upstream stage needs its
    # CSV already on disk.
    missing = [f"Stage {s.number} ({s.label})" for s in STAGES[:3]
               if "calc" in selected and s.key not in selected
               and not s.cache_status()]

    st.sidebar.divider()
    if missing:
        st.sidebar.error("Stage 4 needs input that is neither selected nor "
                         "cached: " + ", ".join(missing), icon="🚫")

    if st.sidebar.button("▶️  Run pipeline", type="primary",
                         use_container_width=True,
                         disabled=not selected or bool(missing)):
        st.session_state["run_requested"] = list(selected)
    if selected:
        st.sidebar.caption(f"Rough estimate: **{_runtime_estimate(selected)}**")

    st.sidebar.divider()
    st.sidebar.caption(f"Output dir\n\n`{MASTER.output_dir}`")
    if st.sidebar.button("↺  Reset config to defaults", use_container_width=True):
        # Deferred: reset_config() deletes widget-bound keys, which is only
        # legal before those widgets exist. main() handles the flag on entry.
        st.session_state["reset_requested"] = True
        st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# PAGES
# ═════════════════════════════════════════════════════════════════════════════

def render_search_results(needle: str) -> None:
    """Every config field whose name or help text matches, across all four configs.

    Replaces the tabs rather than sitting above them, and that is a correctness
    requirement rather than a layout preference: the widget key IS the storage
    key, so rendering one field here AND on its tab in the same run is a
    duplicate-key error. Search mode and browse mode are exclusive.
    """
    hits = [spec
            for section in CONFIG_OBJECTS
            for spec in SPECS[section]
            if needle in spec.name.lower() or needle in (spec.help or "").lower()]

    if not hits:
        st.info(f"No config field matches `{needle}`. The search covers field "
                "names and the module comment attached to each one.", icon="🔍")
        return

    st.caption(
        f"**{len(hits)}** field{'' if len(hits) == 1 else 's'} match "
        f"`{needle}`, from every config at once. Clear the box to go back to "
        "the tabs."
    )
    for section in CONFIG_OBJECTS:
        found = [s for s in hits if s.section_key == section]
        if not found:
            continue
        st.markdown(f"##### {ui_meta.SECTION_LABELS[section]}")
        cols = st.columns(2)
        for i, spec in enumerate(found):
            with cols[i % 2]:
                render_field(spec)
        st.divider()


def render_config_page() -> None:
    """The Common tab plus one tab per config, every field introspected at runtime.

    Nothing here lists the fields: `ui_meta.build_field_specs` walks the
    dataclasses, so a field added to `CalcConfig` tomorrow appears without
    anyone editing this file. The only editorial step is which fields are
    curated onto the Common tab.
    """
    st.caption(
        "Every field of all four config dataclasses, introspected at runtime. "
        "Hover the ⓘ on any field for the module's own comment explaining it. "
        "Those comments are the real documentation for this model, and they are "
        "there to stop someone 'fixing' a result that only looks wrong."
    )

    needle = st.text_input(
        "Find a setting", "", placeholder="e.g. beneficiation, rtg, wacc, tank",
        help="Matches the field name AND the module comment behind it, across "
             "all four configs at once. While this box has anything in it the "
             "tabs below are replaced by the matches, which is also what keeps "
             "a field from being rendered twice.",
    ).strip().lower()

    if needle:
        render_search_results(needle)
        return

    tabs = st.tabs(["⭐ Common"] + [ui_meta.SECTION_LABELS[k] for k in CONFIG_OBJECTS])

    with tabs[0]:
        for title, blurb, fields in ui_meta.CURATED_GROUPS:
            st.markdown(f"##### {title}")
            if blurb:
                st.caption(blurb)
            cols = st.columns(3)
            for i, (section, name) in enumerate(fields):
                with cols[i % 3]:
                    if section == "__master__":
                        st.text_input(
                            "delivery destination", disabled=True,
                            value=st.session_state.get(
                                "destination", MASTER.delivery_destination),
                            key="destination_mirror",
                            help="Set in the sidebar. Writes Stage 2 pricing "
                                 "and Stage 4 architecture together.")
                    elif spec := SPEC_INDEX.get(f"{section}::{name}"):
                        render_field(spec)
            st.divider()

    for tab, section in zip(tabs[1:], CONFIG_OBJECTS):
        with tab:
            dials = [s for s in SPECS[section] if not s.is_path]
            paths = [s for s in SPECS[section] if s.is_path]

            for group, specs in ui_meta.group_specs(dials):
                st.markdown(f"##### {group}")
                cols = st.columns(2)
                for i, spec in enumerate(specs):
                    with cols[i % 2]:
                        # A curated field's live control is on the Common tab; a
                        # second widget sharing its key would be a duplicate-key
                        # error, so this tab shows a read-only mirror instead.
                        (render_mirror if spec.curated else render_field)(spec)
                st.divider()

            if paths:
                with st.expander("Paths and filenames"):
                    st.caption(
                        "`output_dir` is intentionally absent, because "
                        "`MasterConfig.apply()` overwrites every sub-config's "
                        "copy from the master and an edit here would be "
                        "silently discarded."
                    )
                    cols = st.columns(2)
                    for i, spec in enumerate(paths):
                        with cols[i % 2]:
                            render_field(spec)


def render_results_page() -> None:
    """Load the profitability catalog from disk and render it, or say there is none.

    Reads the CSV rather than holding the last run's frame in memory, so the
    page is the same whether the run happened in this session or last week.
    """
    path = os.path.join(MASTER.output_dir, MASTER.calc.output_filename)
    if not os.path.exists(path):
        st.info("No profitability catalog yet. Pick your stages in the sidebar "
                "and run the pipeline.", icon="📭")
        return

    df = load_results(path, st.session_state.get("results_token",
                                                 os.path.getmtime(path)))
    if df.empty:
        st.warning("The profitability catalog is empty. Check the run log.")
        return

    manifest_path = os.path.join(MASTER.output_dir, RUN_CONFIG_FILENAME)
    if os.path.exists(manifest_path):
        with st.expander("What produced these numbers"):
            try:
                with open(manifest_path, encoding="utf-8") as fh:
                    manifest = json.load(fh)
            except (OSError, ValueError):
                manifest = {}
            st.write({k: manifest.get(k) for k in
                      ("written_at", "delivery_destination", "stages_run",
                       "versions")})
            changes = manifest.get("changes_from_defaults") or []
            st.markdown("**Config changed from the loaded defaults:**")
            st.code("\n".join(changes) if changes else "(none)", language="text")

    render_provenance()
    render_results(df)


def render_getting_started() -> None:
    """The three steps, and the name of the file that opens this page.

    Expanded on a machine that has never produced a profitability catalog and
    collapsed afterwards, so it is a first-run guide rather than a permanent
    banner. The entry-point sentence is here and not only in README.md because
    somebody looking at this page is exactly the person who no longer needs to
    read a README, and the question "what did I open, and how do I open it
    again" is the one a dashboard cannot answer from outside itself.
    """
    results_path = os.path.join(MASTER.output_dir, MASTER.calc.output_filename)
    first_run = not os.path.exists(results_path)

    with st.expander("Start here: how this page works", expanded=first_run):
        a, b = st.columns([3, 2])
        with a:
            st.markdown(
                "**1. Pick where the material is sold.** The destination in "
                "the sidebar sets both the price of a kilogram and the "
                "architecture that delivers it. Changing it forces Stage 2 to "
                "re-run, which re-fetches live metal prices.")
            st.markdown(
                "**2. Pick how big a run you want.** The three preset buttons "
                "are the ones the command line offers. **Quick sample** "
                "finishes in minutes and is the right first move; **Full "
                "run** is the model's own defaults and takes hours.")
            st.markdown(
                "**3. Press Run pipeline.** Stage 4 is ticked and Stages 1 to "
                "3 are not, because those three fetch live data and each "
                "overwrites the only copy of its CSV. Re-running Stage 4 "
                "against the catalogs already on disk is the normal loop.")
            st.markdown(
                "Results land on the **Results** tab and are read back from "
                "disk, so they survive closing this page.")
        with b:
            st.markdown("**Opening this dashboard again**")
            st.code("_START HERE.vbs", language="text")
            st.caption(
                "Double-click that file in the repository folder. It is the "
                "one entry point that needs no terminal. `run.bat` (Windows) "
                "and `./run.sh` (Linux and macOS) offer the same dashboard "
                "plus the headless runs, and this page itself is `ui.py`."
            )
            st.caption(
                f"Reading and writing `{MASTER.output_dir}`."
            )


def render_run_report() -> None:
    """Replay the last run's outcome and log from session state."""
    if error := st.session_state.get("run_error"):
        st.error(error)
    elif (elapsed := st.session_state.get("run_elapsed")) is not None:
        finished = st.session_state.get("run_finished_at")
        st.success(
            f"Last run finished at "
            f"{finished.strftime('%H:%M:%S') if finished else NA} in "
            f"{elapsed:.1f}s. Config snapshot → "
            f"`{st.session_state.get('run_manifest', NA)}`"
        )
    with st.expander("Run log"):
        for key, log in st.session_state.get("run_logs", {}).items():
            st.markdown(f"**Stage {key}**")
            st.code(log or "(no output)", language="text")
    st.divider()


def main() -> None:
    """Streamlit entry point: sidebar, then one of the two pages.

    The reset has to be handled FIRST, before any widget exists, because
    Streamlit owns the session-state slot behind each widget key and raises if
    you write to it after the widget has been created. See `reset_config()`.
    """
    # Before any widget exists. See reset_config() and apply_run_preset().
    if st.session_state.pop("reset_requested", False):
        reset_config()
    if preset := st.session_state.pop("preset_requested", None):
        apply_run_preset(preset)
    if st.session_state.pop("goto_results", False):
        st.session_state["page"] = PAGE_RESULTS

    render_sidebar()

    st.title("Asteroid mining profitability")
    st.caption(f"catalog {MASTER.catalog.pipeline_version} · "
               f"mineral_value {MASTER.mineral.pipeline_version} · "
               f"transportation {MASTER.transport.pipeline_version} · "
               f"calc {MASTER.calc.pipeline_version}")

    render_getting_started()

    # `segmented_control` when the installed Streamlit has it (1.40 and up),
    # because two radio dots read as a question and a segmented control reads
    # as a place you ARE. requirements-ui.txt only asks for >= 1.30, so the
    # radio stays as the fallback rather than becoming a version bump.
    #
    # Seeded rather than passed as `default=`, because a widget given both a
    # default AND a session-state value warns about it on every run, and this
    # key is written by the deferred jump at the top of this function.
    st.session_state.setdefault("page", PAGE_CONFIGURE)
    if hasattr(st, "segmented_control"):
        # It returns None when nothing is selected, so the seeded value is the
        # fallback rather than a crash on `page ==`.
        page = st.segmented_control(
            "Section", PAGES, key="page",
            label_visibility="collapsed") or PAGE_CONFIGURE
    else:
        page = st.radio("Section", PAGES, key="page",
                        horizontal=True, label_visibility="collapsed")

    if requested := st.session_state.pop("run_requested", None):
        st.subheader("Running the pipeline")
        st.caption(
            "The page stays put until this finishes, so leave the tab open. "
            "Percentages are measured where the pipeline reports a count and "
            "estimated from prior timings otherwise; the caption says which."
        )
        run_stages(requested)      # reruns on success; returns here on failure

    if st.session_state.get("run_logs"):
        render_run_report()

    if page == PAGE_RESULTS:
        render_results_page()
    else:
        render_config_page()


main()
