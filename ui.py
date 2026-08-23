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
                Stage 4 runs 22 min to 6.8 h depending on two flags (see below),
                so re-running Stage 4 alone against a cached catalog is the
                normal working loop.
    Inspect     the profitability catalog ranked by cost/revenue, charted, and
                drilled into one asteroid at a time.

DELIBERATELY NOT IN `modules/`. `build_master.py` concatenates that directory
into `master.py` and asserts a specific header/footer shape per module; this is
a consumer of the built `master.py`, not a part of it.

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
          "rarely needs re-running — but it MUST be re-run after a v1.9.0 "
          "upgrade, or Stage 4 reads a propellants.csv with no tankage "
          "columns and silently flies every tank for free."),
    Stage("calc",      4, "Profitability",
          "The headline output, and the only stage whose runtime you choose. "
          "Measured on the full 1.55 M-row catalog at cislunar, 12 workers: "
          "22 min raw at N = 1, 65 min with optimise_programme_scale, 2.6 h "
          "with use_beneficiation, and 6.8 h with both — and both of those "
          "flags DEFAULT ON as of calc v1.17.0, so budget for the 6.8 h unless "
          "you turn one off. Seconds with eval_row_cap set low."),
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
    # the smallest one — the estimate would have said three minutes for
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
    # BOTH axes, because both default ON as of calc v1.17.0 and each is worth
    # roughly 3x. Omitting the programme search told the user 2.2 h for the
    # DEFAULT run, against 6.8 h measured -- 3.1x low, and flatly contradicted
    # by this stage's own blurb four lines of sidebar away, which already says
    # "budget for the 6.8 h". A stale estimate beside a correct sentence is the
    # exact failure CLAUDE.md is written to catch.
    search = st.session_state.get("cfg::calc::optimise_programme_scale",
                                  MASTER.calc.optimise_programme_scale)

    # Seconds per row, read straight off the committed full-catalog 2x2 --
    # CLAUDE.md, "THE FULL CISLUNAR 2x2", calc 1.16.0, 12 workers, over the
    # 1,555,618 rows with positive mass:
    #
    #                 search OFF     search ON
    #     raw            1,307 s       3,890 s
    #     beneficiated   9,300 s      24,587 s
    #
    # The old pair of rates carried a beneficiated:raw ratio of 3.12x, taken
    # from a stride sample. CLAUDE.md retires that figure by name -- the real
    # full-catalog ratio is 7.1x -- and THE SAMPLING RULE is precisely about
    # not doing this. These four are measured full runs, so they need no
    # ratio at all.
    _CELL_ROWS = 1_555_618
    _SECONDS_PER_ROW = {
        (False, False):  1_307 / _CELL_ROWS,
        (False, True):   3_890 / _CELL_ROWS,
        (True,  False):  9_300 / _CELL_ROWS,
        (True,  True):  24_587 / _CELL_ROWS,
    }
    # Measured at CISLUNAR on calc 1.16.0. Five performance-only releases have
    # landed since and no full-catalog run has been made on any of them, so
    # this reads HIGH -- which is the right direction for an estimate. Other
    # destinations run 1.4-2x slower on raw (v1.14.0 matrix); this does not try
    # to model that, because it is a prior, and the stage bar replaces it with
    # measured progress within the first minute.
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
        self.full: List[str] = []
        self.tail = deque(maxlen=tail_lines)
        self.live = ""               # in-flight tqdm redraw, not yet a log line
        self.phase = ""
        self.done = 0.0
        self.total = 0.0
        self._pending = ""

    def feed(self, text: str) -> None:
        self._pending += text.replace("\r\n", "\n")
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._record(line.rsplit("\r", 1)[-1])
        if "\r" in self._pending:
            self.live = self._pending = self._pending.rsplit("\r", 1)[-1]
            self._scan(self.live)

    def close(self) -> None:
        if self._pending.strip():
            self._record(self._pending.rsplit("\r", 1)[-1])
        self._pending = ""

    @property
    def display_lines(self) -> List[str]:
        return list(self.tail) + ([self.live] if self.live else [])

    @property
    def log(self) -> str:
        return "\n".join(self.full)

    def _record(self, line: str) -> None:
        self.live = ""
        self.full.append(line)
        self.tail.append(line)
        self._scan(line)

    def _scan(self, line: str) -> None:
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
        self._view = view
        self._scan = ProgressScan()
        self._bar = st.progress(0.0)
        self._log = st.empty()
        self._t0 = time.monotonic()
        self._last_paint = 0.0
        self._min_interval = min_interval

    def write(self, s: str) -> int:
        self._scan.feed(s)
        self._paint()
        return len(s)

    def flush(self) -> None:
        pass

    def finish(self) -> str:
        self._scan.close()
        self._paint(force=True)
        return self._scan.log

    def _paint(self, force: bool = False) -> None:
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
]


def render_results(df: pd.DataFrame) -> None:
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
            st.altair_chart(
                alt.Chart(by_type).mark_bar().encode(
                    x=alt.X("best:Q", title="best cost/revenue",
                            scale=alt.Scale(type="log")),
                    y=alt.Y("type:N", sort="x", title=None),
                    tooltip=["type", "best", "count"],
                ).properties(height=340),
                use_container_width=True,
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


def _render_drilldown(ranked: pd.DataFrame) -> None:
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
            "Note that it re-fetches **live** metal prices — see the caution "
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

def render_config_page() -> None:
    st.caption(
        "Every field of all four config dataclasses, introspected at runtime. "
        "Hover the ⓘ on any field for the module's own comment explaining it. "
        "Those comments are the real documentation for this model, and they are "
        "there to stop someone 'fixing' a result that only looks wrong."
    )

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
    # Before any widget exists. See reset_config().
    if st.session_state.pop("reset_requested", False):
        reset_config()

    render_sidebar()

    st.title("Asteroid mining profitability")
    st.caption(f"catalog {MASTER.catalog.pipeline_version} · "
               f"mineral_value {MASTER.mineral.pipeline_version} · "
               f"transportation {MASTER.transport.pipeline_version} · "
               f"calc {MASTER.calc.pipeline_version}")

    page = st.radio("Section", ["⚙️  Configure", "📊  Results"],
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

    if page.endswith("Configure"):
        render_config_page()
    else:
        render_results_page()


main()
