# -*- coding: utf-8 -*-
"""Streamlit front end for the asteroid profitability pipeline.

    py -m pip install streamlit
    py -m streamlit run ui.py

Three things it does:

    Configure   every field of all four config dataclasses, introspected at
                runtime so a new field appears without editing this file, with
                the module's own explanatory comment attached as help text.
    Run         any subset of the four stages, reusing the CSVs already on disk
                for the stages you skip.  Stage 1 downloads ~500 MB and a full
                beneficiated Stage 4 takes ~20 minutes, so re-running Stage 4
                alone against a cached catalog is the normal working loop.
    Inspect     the profitability catalog ranked by cost/revenue, charted, and
                drilled into one asteroid at a time.

DELIBERATELY NOT IN `modules/`.  `build_master.py` concatenates that directory
into `master.py` and asserts a specific header/footer shape per module; this is
a consumer of the built `master.py`, not a part of it.

ON MUTATING CONFIG INSTANCES.  CLAUDE.md says to edit a field's default inside
the dataclass rather than mutating the instance, because mutation defeats having
one editable source of truth.  A UI is the exception the MasterConfig docstring
already carves out — it documents `MASTER_CONFIG.catalog.jpl_limit = 10_000` as
the supported way to drive the orchestrator.  What the UI must not do is let the
two `delivery_destination` copies drift apart, so it renders one control and
writes it through the `MASTER_CONFIG.delivery_destination` property, which sets
both.  Every run also drops a `ui_run_config.json` beside the outputs recording
exactly what produced them.
"""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

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


# ═════════════════════════════════════════════════════════════════════════════
# PIPELINE IMPORT
# ═════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="Importing master.py …")
def load_pipeline():
    """Import master.py once per Streamlit session.

    Importing is side-effect free by design — master.py guards its auto-run on
    `__name__ == "__main__"` — but it does print an installation banner and
    build the config singletons, so the output is swallowed here.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        import master  # noqa: PLC0415  (deliberately late + cached)
    return master, buf.getvalue()


try:
    master, _import_log = load_pipeline()
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


@st.cache_data(show_spinner=False)
def field_specs() -> Dict[str, List[FieldSpec]]:
    """Introspect the four configs once; the dataclasses do not change at runtime."""
    return {
        key: ui_meta.build_field_specs(CONFIG_OBJECTS[key], key)
        for key in CONFIG_OBJECTS
    }


SPECS = field_specs()
SPEC_INDEX: Dict[str, FieldSpec] = {
    f"{s.section_key}::{s.name}": s
    for specs in SPECS.values() for s in specs
}

DESTINATIONS = sorted(master.DELIVERY_DESTINATIONS.keys())


# ═════════════════════════════════════════════════════════════════════════════
# STAGE DEFINITIONS
# ═════════════════════════════════════════════════════════════════════════════

@dataclasses.dataclass(frozen=True)
class Stage:
    key: str
    number: int
    label: str
    blurb: str
    config_key: str

    def builder(self):
        return {
            "catalog":   master.build_asteroid_catalog,
            "mineral":   master.build_mineral_value_catalog,
            "transport": master.build_transportation_catalog,
            "calc":      master.build_profitability_catalog,
        }[self.key]

    def outputs(self) -> List[str]:
        """Files this stage writes, absolute, in the current output dir."""
        out = MASTER.output_dir
        if self.key == "catalog":
            return [os.path.join(out, MASTER.catalog.catalog_filename)]
        if self.key == "mineral":
            return [os.path.join(out, MASTER.mineral.catalog_filename)]
        if self.key == "transport":
            sub = os.path.join(out, MASTER.transport.subdir)
            return [
                os.path.join(sub, name) for name in (
                    "launch_vehicles.csv", "propellants.csv",
                    "delta_v_segments.csv", "operational_costs.csv",
                )
            ]
        return [os.path.join(out, MASTER.calc.output_filename)]


STAGES = [
    Stage("catalog",   1, "Asteroid catalog",
          "JPL SBDB + MP3C + SsODNet + NEOWISE. Downloads ~500 MB; slowest to "
          "re-run and the one you most want cached.", "catalog"),
    Stage("mineral",   2, "Mineral value",
          "Live prices + mineralogy, priced FOR THE CHOSEN DESTINATION. Must "
          "be re-run whenever the destination changes.", "mineral"),
    Stage("transport", 3, "Transportation",
          "Launch vehicles, propellants, Δv segments, ops costs. Reference "
          "tables — fast, and rarely needs re-running.", "transport"),
    Stage("calc",      4, "Profitability",
          "The headline output. ~20 min for a full beneficiated catalog, "
          "seconds with eval_row_cap set low.", "calc"),
]


def stage_cache_status(stage: Stage) -> Dict[str, Any]:
    """Whether this stage's outputs already exist, and how old they are."""
    paths = stage.outputs()
    present = [p for p in paths if os.path.exists(p)]
    if len(present) != len(paths):
        return {"cached": False, "missing": [p for p in paths if p not in present]}
    newest = max(os.path.getmtime(p) for p in present)
    size = sum(os.path.getsize(p) for p in present)
    return {
        "cached": True,
        "mtime": datetime.fromtimestamp(newest),
        "age_s": time.time() - newest,
        "size_mb": size / 1e6,
        "paths": paths,
    }


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
    text = spec.help or "No comment in the module source."
    return f"`{spec.name}`\n\n{text}"


def _seed(spec: FieldSpec) -> Any:
    """Ensure st.session_state[spec.key] holds a valid, correctly typed value.

    The widget key IS the storage key — Streamlit owns that slot and raises if
    anything writes to it after the widget exists, so the value is seeded before
    the widget is created and never assigned afterwards.  That also means each
    field may be rendered exactly ONCE per run (a duplicate key is an error),
    which is why a curated field appears as a live control on the Common tab and
    as a disabled mirror on its module tab.
    """
    key = spec.key
    live = getattr(CONFIG_OBJECTS[spec.section_key], spec.name, spec.default)

    if key not in st.session_state:
        st.session_state[key] = live

    value = st.session_state[key]

    # Coerce to the type the widget will demand, so a float field seeded with an
    # int (or a stale value outside new bounds) cannot blow up number_input.
    if spec.kind == "bool":
        st.session_state[key] = bool(value)
    elif spec.kind == "int" and spec.bounds:
        lo, hi, _ = spec.bounds
        st.session_state[key] = int(min(max(int(value or 0), lo), hi))
    elif spec.kind == "float" and spec.bounds:
        lo, hi, _ = spec.bounds
        st.session_state[key] = float(min(max(float(value or 0.0), lo), hi))
    elif spec.kind == "list":
        st.session_state[key] = list(value) if value else []
    elif spec.kind == "str" and value is None:
        st.session_state[key] = ""

    return st.session_state[key]


def render_field(spec: FieldSpec) -> None:
    """Render one config field as a live widget bound to st.session_state[spec.key]."""
    value = _seed(spec)
    label = spec.name.replace("_", " ")
    help_text = _help_for(spec)

    if spec.kind == "readonly":
        st.text_input(label, value=str(value), disabled=True,
                      key=f"ro::{spec.key}", help=help_text)
        return

    if spec.kind == "bool":
        st.checkbox(label, key=spec.key, help=help_text)
        return

    if spec.kind == "choice":
        options = spec.choices or ui_meta.CHOICES.get(spec.name) or []
        if not options:
            st.text_input(label, key=spec.key, help=help_text)
            return
        if value not in options:
            st.session_state[spec.key] = options[0]
        st.selectbox(label, options, key=spec.key, help=help_text)
        return

    if spec.kind == "list":
        options = _list_options(spec.name)
        # Anything already selected but absent from the discovered options (a
        # vehicle from a catalog not yet rebuilt, say) stays selectable.
        options = options + [c for c in value if c not in options]
        st.multiselect(label, options, key=spec.key,
                       help=help_text + "\n\nEmpty = no filter (all).")
        return

    if spec.kind in ("int", "float"):
        if not spec.bounds:
            st.number_input(label, key=spec.key, help=help_text)
            return
        lo, hi, step = spec.bounds
        if spec.kind == "int":
            st.number_input(label, min_value=int(lo), max_value=int(hi),
                            step=int(max(step, 1)), key=spec.key, help=help_text)
        else:
            st.number_input(label, min_value=float(lo), max_value=float(hi),
                            step=float(step), format="%.4f",
                            key=spec.key, help=help_text)
        return

    st.text_input(label, key=spec.key, help=help_text,
                  type="password" if spec.secret else "default")


def render_mirror(spec: FieldSpec, where: str = "⭐ Common") -> None:
    """Disabled read-only view of a field whose live control lives elsewhere.

    Keeps every field discoverable on its own module tab without instantiating
    a second widget for the same key.  Reads only — never `_seed()`: the live
    widget on the Common tab already owns this session key, and Streamlit
    forbids writing to a key after its widget exists.
    """
    value = st.session_state.get(
        spec.key, getattr(CONFIG_OBJECTS[spec.section_key], spec.name, spec.default)
    )
    shown = ", ".join(value) if isinstance(value, list) else str(value)
    st.text_input(spec.name.replace("_", " "), value=shown or "(all)",
                  disabled=True, key=f"mirror::{spec.key}",
                  help=f"{_help_for(spec)}\n\n**Set on the {where} tab.**")


@st.cache_data(show_spinner=False)
def _list_options_cached(name: str, sub_path: str, mtime: float) -> List[str]:
    try:
        df = pd.read_csv(sub_path)
    except Exception:
        return []
    for col in ("name", "vehicle", "propellant"):
        if col in df.columns:
            return sorted(df[col].dropna().astype(str).unique().tolist())
    return []


def _list_options(name: str) -> List[str]:
    """Legal values for candidate_vehicles / candidate_propellants, if built."""
    filename = {
        "candidate_vehicles": "launch_vehicles.csv",
        "candidate_propellants": "propellants.csv",
    }.get(name)
    if not filename:
        return []
    path = os.path.join(MASTER.output_dir, MASTER.transport.subdir, filename)
    if not os.path.exists(path):
        return []
    return _list_options_cached(name, path, os.path.getmtime(path))


def collect_config() -> Dict[str, Dict[str, Any]]:
    """Session values for every field, grouped by config section."""
    out: Dict[str, Dict[str, Any]] = {k: {} for k in CONFIG_OBJECTS}
    for section, specs in SPECS.items():
        for spec in specs:
            if spec.kind == "readonly" or spec.key not in st.session_state:
                continue
            value = st.session_state[spec.key]
            # An empty multiselect means "no filter", which the config spells
            # None, not [] — candidate_combos() reads None as "every vehicle".
            if spec.kind == "list" and not value:
                value = None
            out[section][spec.name] = value
    return out


def apply_config() -> List[str]:
    """Push session values onto the live config objects.  Returns a change log."""
    changes: List[str] = []
    for section, values in collect_config().items():
        target = CONFIG_OBJECTS[section]
        for name, new in values.items():
            old = getattr(target, name, None)
            if old != new:
                changes.append(f"{section}.{name}: {old!r} → {new!r}")
            setattr(target, name, new)

    # The destination is written LAST and through the master property, so it
    # cannot be left disagreeing between Stage 2 and Stage 4 by an ordinary
    # field write above.
    dest = st.session_state.get("destination", MASTER.delivery_destination)
    if MASTER.delivery_destination != dest:
        changes.append(f"delivery_destination: "
                       f"{MASTER.delivery_destination!r} → {dest!r}")
    MASTER.delivery_destination = dest

    # apply() re-pushes output_dir into every sub-config and re-asserts the
    # destination across Stages 2 and 4.
    MASTER.apply()
    return changes


def reset_config() -> None:
    """Restore the dataclass defaults and drop every session override.

    Runs at the TOP of a script run, before any widget exists — deleting a key
    that Streamlit has already bound to a live widget is exactly the write it
    forbids.  The sidebar button therefore sets a flag and reruns rather than
    resetting in place.
    """
    for section, specs in SPECS.items():
        cls = type(CONFIG_OBJECTS[section])
        defaults = {f.name: f.default for f in dataclasses.fields(cls)}
        for spec in specs:
            st.session_state.pop(spec.key, None)
            default = defaults.get(spec.name)
            if default is not dataclasses.MISSING:
                setattr(CONFIG_OBJECTS[section], spec.name, default)
    st.session_state.pop("destination", None)
    MASTER.apply()


# ═════════════════════════════════════════════════════════════════════════════
# RUN EXECUTION
# ═════════════════════════════════════════════════════════════════════════════

class _TailStream(io.TextIOBase):
    """stdout sink that keeps the whole log and mirrors the tail into the page.

    The pipeline's own progress prints are the only signal that a 20-minute
    Stage 4 is alive rather than hung, so they are streamed rather than shown
    after the fact.  Updates are throttled — Stage 1 emits thousands of lines
    and repainting on each one is slower than the pipeline.
    """

    def __init__(self, placeholder, tail_lines: int = 14, min_interval: float = 0.4):
        self._buf = io.StringIO()
        self._placeholder = placeholder
        self._tail_lines = tail_lines
        self._min_interval = min_interval
        self._last_paint = 0.0

    def write(self, s: str) -> int:
        self._buf.write(s)
        now = time.monotonic()
        if "\n" in s and (now - self._last_paint) >= self._min_interval:
            self._last_paint = now
            self._paint()
        return len(s)

    def _paint(self) -> None:
        lines = self._buf.getvalue().rstrip("\n").split("\n")
        try:
            self._placeholder.code("\n".join(lines[-self._tail_lines:]), language="text")
        except Exception:
            pass          # placeholder gone (rerun mid-write) — keep the pipeline alive

    def flush(self) -> None:
        pass

    def finish(self) -> str:
        self._paint()
        return self._buf.getvalue()


def write_run_manifest(selected: List[str], changes: List[str]) -> str:
    """Record what produced the CSVs in the output dir.

    The pipeline stamps `pipeline_version` into every CSV, which identifies the
    CODE but not the CONFIG.  Two runs of identical code at different
    destinations, or with beneficiation on and off, are indistinguishable from
    their outputs alone — and this project's documented failure mode is a
    number whose provenance nobody can reconstruct.
    """
    manifest = {
        "written_at": datetime.now().isoformat(timespec="seconds"),
        "stages_run": selected,
        "delivery_destination": MASTER.delivery_destination,
        "changes_from_defaults": changes,
        "versions": {
            "master": getattr(master, "__version__", "1.13.0"),
            "catalog": MASTER.catalog.pipeline_version,
            "mineral_value": MASTER.mineral.pipeline_version,
            "transportation": MASTER.transport.pipeline_version,
            "calc": MASTER.calc.pipeline_version,
        },
        "config": {
            section: {
                f.name: getattr(obj, f.name)
                for f in dataclasses.fields(obj)
            }
            for section, obj in CONFIG_OBJECTS.items()
        },
    }
    path = os.path.join(MASTER.output_dir, RUN_CONFIG_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)
    return path


def run_stages(selected_keys: List[str]) -> None:
    """Execute the chosen stages in order, streaming each one's log."""
    changes = apply_config()
    stages = [s for s in STAGES if s.key in selected_keys]

    results: Dict[str, Any] = {}
    logs: Dict[str, str] = {}
    st.session_state["run_error"] = None
    t_start = time.monotonic()

    for stage in stages:
        header = f"Stage {stage.number} — {stage.label}"
        with st.status(header, expanded=True) as status:
            placeholder = st.empty()
            stream = _TailStream(placeholder)
            t0 = time.monotonic()
            try:
                with contextlib.redirect_stdout(stream), \
                     contextlib.redirect_stderr(stream):
                    results[stage.key] = stage.builder()(
                        CONFIG_OBJECTS[stage.config_key]
                    )
            except Exception as exc:
                logs[stage.key] = stream.finish() + "\n" + traceback.format_exc()
                status.update(label=f"{header} — FAILED: {exc}", state="error")
                st.session_state["run_error"] = f"{header}: {exc}"
                st.session_state["run_logs"] = logs
                return
            logs[stage.key] = stream.finish()
            status.update(
                label=f"{header} — done in {time.monotonic() - t0:.1f}s",
                state="complete", expanded=False,
            )

    manifest_path = write_run_manifest(selected_keys, changes)

    st.session_state["run_logs"] = logs
    st.session_state["run_elapsed"] = time.monotonic() - t_start
    st.session_state["run_finished_at"] = datetime.now()
    st.session_state["run_manifest"] = manifest_path
    st.session_state["results_token"] = time.time()   # busts the results cache

    # The sidebar rendered its cache status BEFORE these stages wrote anything,
    # so it is now describing files that no longer exist in that state — most
    # visibly still warning about a destination mismatch this run just fixed.
    # Rerun so it re-reads the disk; the log is replayed from session_state.
    st.session_state["run_report_pending"] = True
    st.rerun()


# ═════════════════════════════════════════════════════════════════════════════
# RESULTS
# ═════════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner="Loading profitability catalog …")
def load_results(path: str, token: float) -> pd.DataFrame:
    """Read the profitability catalog and add the ranking column.

    `cost_revenue_ratio` is computed here rather than read, because Stage 4 does
    not write it.  CLAUDE.md is emphatic that this — not `profit_usd` — is the
    ranking to use: revenue sits orders of magnitude below cost in most
    configurations, so profit ≈ −cost and ranking by it degenerates into a Δv
    table wearing a profit label.
    """
    df = pd.read_csv(path, low_memory=False)
    gross = pd.to_numeric(df.get("gross_value_usd"), errors="coerce")
    cost = pd.to_numeric(df.get("total_cost_usd"), errors="coerce")
    df["cost_revenue_ratio"] = (cost / gross).where(gross > 0)
    return df


def results_path() -> str:
    return os.path.join(MASTER.output_dir, MASTER.calc.output_filename)


@st.cache_data(show_spinner=False)
def _taxonomy_provenance(path: str, mtime: float) -> Optional[Dict[str, int]]:
    try:
        col = pd.read_csv(path, usecols=["spectral_type_source"], low_memory=False)
    except Exception:
        return None
    return col["spectral_type_source"].fillna("unknown").astype(str) \
             .value_counts().to_dict()


def render_provenance() -> None:
    """How much of this catalog's taxonomy was MEASURED rather than guessed.

    The documented failure mode here is a source that fails soft: an outage does
    not shrink the catalog, it inflates it with taxonomy inferred from albedo, so
    two runs stop being comparable with nothing in the log saying so.  The
    SsODNet regression was invisible for exactly this reason.  Row counts cannot
    detect it — `spectral_type_source` can.
    """
    path = os.path.join(MASTER.output_dir, MASTER.catalog.catalog_filename)
    if not os.path.exists(path):
        return
    counts = _taxonomy_provenance(path, os.path.getmtime(path))
    if not counts:
        return

    total = sum(counts.values()) or 1
    guessed = counts.get("albedo", 0) + counts.get("unknown", 0)
    guessed_frac = guessed / total

    label = (f"Catalog provenance — {1 - guessed_frac:.0%} of taxonomy measured, "
             f"{guessed_frac:.0%} guessed")
    with st.expander(label, expanded=guessed_frac > 0.75):
        st.dataframe(
            pd.DataFrame(sorted(counts.items(), key=lambda kv: -kv[1]),
                         columns=["spectral_type_source", "asteroids"]),
            use_container_width=True, hide_index=True,
        )
        st.caption(
            "`source` / `tholen` are measured; `albedo` is inferred and "
            "`unknown` is neither. A data source that fails soft does not "
            "shrink the catalog — it inflates it with guessed taxonomy, which "
            "is why row counts cannot detect the problem and this can."
        )
        if guessed_frac > 0.75:
            st.warning(
                f"**{guessed_frac:.0%} of this catalog's taxonomy is guessed "
                "from albedo.** That is the signature of a small run or a "
                "source outage (SsODNet carries most of the measured "
                "taxonomy). Do not compare these numbers to a committed "
                "result — the population is not the same one.",
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

    # ── Headline ─────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Asteroids evaluated", f"{len(df):,}")
    c2.metric("Viable missions", f"{int(df['viable'].sum()):,}"
              if "viable" in df.columns else "—")
    if not ranked.empty:
        best = ranked.iloc[0]
        c3.metric("Best cost / revenue", f"{best['cost_revenue_ratio']:,.2f}×",
                  help="Lower is better. 1.0 is breakeven.")
        label = str(best.get("name") or best.get("designation") or "—")
        c4.metric("Best target", label,
                  help=f"{best.get('spectral_type', '?')}-type, "
                       f"{best.get('vehicle', '?')} / {best.get('propellant', '?')}")

    if "viable" in df.columns and int(df["viable"].sum()) == 0:
        st.info(
            "**Zero viable missions is the correct answer**, not a regression — "
            "a default run produces zero, and so does every other combination "
            "currently in the model. Rank by cost/revenue to see how close the "
            "best target gets.",
            icon="ℹ️",
        )

    tab_table, tab_charts, tab_drill = st.tabs(
        ["📊 Ranked table", "📈 Charts", "🔎 One asteroid"]
    )

    with tab_table:
        _render_table(ranked, df)
    with tab_charts:
        _render_charts(ranked)
    with tab_drill:
        _render_drilldown(ranked, df)


def _render_table(ranked: pd.DataFrame, df: pd.DataFrame) -> None:
    st.caption(
        "Ranked by **cost / revenue**, ascending — lower is better, 1.0 is "
        "breakeven. Not by `profit_usd`: revenue is far below cost in most "
        "configurations, so a profit ranking is a Δv table in disguise."
    )

    f1, f2, f3 = st.columns([2, 2, 1])
    types = sorted(df["spectral_type"].dropna().astype(str).unique()) \
        if "spectral_type" in df.columns else []
    picked_types = f1.multiselect("Spectral type", types, default=[])

    search = f2.text_input("Search designation / name", "",
                           placeholder="e.g. Bennu, 7753, Wilson")
    top_n = f3.number_input("Show top", min_value=5, max_value=5_000,
                            value=50, step=25)

    view = ranked
    if picked_types:
        view = view[view["spectral_type"].astype(str).isin(picked_types)]
    if search.strip():
        needle = search.strip().lower()
        # regex=False throughout: designations carry regex metacharacters, and
        # "(1) Ceres" against a regex engine is either a wrong match or a raise.
        hay = (view.get("designation", pd.Series(dtype=str)).astype(str).str.lower()
               .str.contains(needle, regex=False, na=False)
               | view.get("name", pd.Series(dtype=str)).astype(str).str.lower()
               .str.contains(needle, regex=False, na=False))
        view = view[hay]

    all_cols = [c for c in HEADLINE_COLUMNS if c in view.columns]
    extra = [c for c in view.columns if c not in all_cols]
    with st.expander(f"Columns  ({len(all_cols)} shown, {len(extra)} more available)"):
        chosen = st.multiselect("Displayed columns", all_cols + extra,
                                default=all_cols)
    cols = chosen or all_cols

    st.dataframe(
        view[cols].head(int(top_n)),
        use_container_width=True, hide_index=True,
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
    st.caption(f"{len(view):,} rows match, showing {min(int(top_n), len(view)):,}.")

    st.download_button(
        "⬇️  Download filtered rows as CSV",
        view[cols].to_csv(index=False).encode("utf-8"),
        file_name="profitability_filtered.csv",
        mime="text/csv",
    )


def _render_charts(ranked: pd.DataFrame) -> None:
    if ranked.empty:
        st.info("Nothing to chart.")
        return

    import altair as alt          # ships with streamlit; no new requirement

    n = st.slider("Chart the best N targets", 50, min(5_000, max(50, len(ranked))),
                  min(500, len(ranked)), step=50)
    view = ranked.head(n).copy()

    st.markdown("##### Cost/revenue against outbound Δv")
    st.caption(
        "Accessibility and value are only loosely coupled — the ranking "
        "responds to composition too, which is the whole reason Δv is "
        "per-asteroid. A vertical stripe here means Δv has collapsed to one "
        "value and `use_per_asteroid_dv` is off."
    )
    if {"dv_out_m_s", "cost_revenue_ratio"} <= set(view.columns):
        scatter = (
            alt.Chart(view)
            .mark_circle(size=45, opacity=0.55)
            .encode(
                x=alt.X("dv_out_m_s:Q", title="Δv outbound (m/s)",
                        scale=alt.Scale(zero=False)),
                y=alt.Y("cost_revenue_ratio:Q", title="cost / revenue (lower better)",
                        scale=alt.Scale(type="log")),
                color=alt.Color("spectral_type:N", title="type"),
                tooltip=[c for c in ("designation", "name", "spectral_type",
                                     "cost_revenue_ratio", "vehicle", "propellant",
                                     "max_payload_kg") if c in view.columns],
            )
            .interactive()
            .properties(height=380)
        )
        st.altair_chart(scatter, use_container_width=True)

    left, right = st.columns(2)

    with left:
        st.markdown("##### Best cost/revenue by spectral type")
        if "spectral_type" in view.columns:
            by_type = (
                view.groupby(view["spectral_type"].astype(str))
                .agg(best=("cost_revenue_ratio", "min"),
                     count=("cost_revenue_ratio", "size"))
                .reset_index()
                .rename(columns={"spectral_type": "type"})
                .sort_values("best")
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
        picks = []
        for col, label in (("vehicle", "Vehicle"), ("propellant", "Propellant"),
                           ("aerocapture_return", "Aerocapture"),
                           ("isru_return", "ISRU"),
                           ("rendezvous_apsis", "Rendezvous apsis")):
            if col in view.columns:
                counts = view[col].astype(str).value_counts()
                for value, count in counts.items():
                    picks.append({"axis": label, "choice": value, "n": int(count)})
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


def _render_drilldown(ranked: pd.DataFrame, df: pd.DataFrame) -> None:
    if ranked.empty:
        st.info("Nothing to drill into.")
        return

    labels = [
        f"{i + 1}.  {row.get('name') or row.get('designation')}  "
        f"({row.get('spectral_type', '?')})  —  {row['cost_revenue_ratio']:,.2f}×"
        for i, (_, row) in enumerate(ranked.head(300).iterrows())
    ]
    pick = st.selectbox("Target", range(len(labels)), format_func=lambda i: labels[i])
    row = ranked.iloc[pick]

    def val(key, default=None):
        v = row.get(key, default)
        return default if pd.isna(v) else v

    st.markdown(f"### {val('name') or val('designation')}")

    m = st.columns(5)
    m[0].metric("cost / revenue", f"{row['cost_revenue_ratio']:,.2f}×")
    m[1].metric("Payload", f"{val('max_payload_kg', 0):,.0f} kg")
    m[2].metric("Gross value", f"${val('gross_value_usd', 0):,.0f}")
    m[3].metric("Total cost", f"${val('total_cost_usd', 0):,.0f}")
    m[4].metric("Duration", f"{val('mission_duration_yr', 0):,.1f} yr")

    left, right = st.columns(2)

    with left:
        st.markdown("#### Chosen architecture")
        arch_rows = [
            ("Destination", val("delivery_destination")),
            ("Architecture", val("delivery_arch")),
            ("Vehicle", val("vehicle")),
            ("Propellant", f"{val('propellant')}  (Isp {val('isp_s', 0):,.0f} s)"),
            ("Return mode", "aerocapture" if val("aerocapture_return") else "propulsive"),
            ("Return propellant", "ISRU (hydrolox, made on site)"
             if val("isru_return") else "brought from Earth"),
            ("Rendezvous apsis", val("rendezvous_apsis")),
            ("Electric propulsion", "yes" if val("is_electric") else "no"),
            ("Beneficiation", f"{val('concentration_ratio', 0):,.2f}×"
             if val("beneficiation") else "declined"),
            ("Δv out / return", f"{val('dv_out_m_s', 0):,.0f} / "
                                f"{val('dv_ret_m_s', 0):,.0f} m/s"),
        ]
        st.dataframe(pd.DataFrame(arch_rows, columns=["", "value"]),
                     use_container_width=True, hide_index=True)

        st.markdown("#### Payload mix")
        mix = str(val("payload_mix", "") or "")
        if mix:
            mix_rows = []
            for part in mix.split(";"):
                part = part.strip()
                if not part:
                    continue
                phase, _, mass = part.rpartition(" ")
                mix_rows.append({"phase": phase, "mass": mass})
            st.dataframe(pd.DataFrame(mix_rows), use_container_width=True,
                         hide_index=True)
            st.caption(
                f"Dominant phase: **{val('payload_dominant_phase', '—')}** at "
                f"{float(val('payload_dominant_frac', 0)):.1%} of the hold. "
                "The mix is a fractional knapsack over the phases actually "
                "present, not a shopping list."
            )
        else:
            st.caption("Flown as bulk material — no beneficiation, so no mix.")

        st.markdown("#### Composition")
        comp = [(k.replace("comp_", "").replace("_", " "), val(k, 0.0))
                for k in ("comp_metal_fraction", "comp_silicate_fraction",
                          "comp_carbon_fraction", "comp_ice_fraction",
                          "comp_pgm_enrichment") if k in row.index]
        st.dataframe(pd.DataFrame(comp, columns=["fraction", "value"]),
                     use_container_width=True, hide_index=True)
        st.caption("Composition fractions sum to 0.76–0.96, not 1.0 — the "
                   "residual is valued at a bulk-silicate floor, not zero.")

    with right:
        st.markdown("#### Cost ledger")
        ledger = [(label, float(val(key, 0.0)))
                  for key, label in _COST_LEDGER if key in row.index]
        ledger = [(l, v) for l, v in ledger if abs(v) > 0]
        ledger_df = pd.DataFrame(ledger, columns=["line", "usd"])
        total = float(val("total_cost_usd", 0.0)) or 1.0
        ledger_df["share"] = ledger_df["usd"] / total
        st.dataframe(
            ledger_df.sort_values("usd", key=abs, ascending=False),
            use_container_width=True, hide_index=True,
            column_config={
                "usd": st.column_config.NumberColumn("USD", format="$%.4g"),
                "share": st.column_config.ProgressColumn(
                    "share of total", format="%.1f%%", min_value=0.0, max_value=1.0),
            },
        )

        st.markdown("#### Mass cascade")
        masses = [(label, float(val(key, 0.0)))
                  for key, label in _MASS_CASCADE if key in row.index]
        st.dataframe(
            pd.DataFrame(masses, columns=["component", "kg"]),
            use_container_width=True, hide_index=True,
            column_config={"kg": st.column_config.NumberColumn(format="%.1f")},
        )
        st.caption(
            "Every kilogram here should have a line in the ledger opposite. "
            "A mass that flies free is this codebase's signature bug — it is "
            "how the electric stage went unbilled until v1.10.0."
        )

        st.markdown("#### Model terms")
        terms = [(label, float(val(key, 0.0)))
                 for key, label in _MODEL_TERMS if key in row.index]
        st.dataframe(
            pd.DataFrame(terms, columns=["term", "value"]),
            use_container_width=True, hide_index=True,
            column_config={"value": st.column_config.NumberColumn(format="%.4g")},
        )

    with st.expander("Every column for this row"):
        st.dataframe(
            pd.DataFrame({"field": row.index, "value": row.astype(str).values}),
            use_container_width=True, hide_index=True, height=420,
        )


# ═════════════════════════════════════════════════════════════════════════════
# SIDEBAR — RUN CONTROL
# ═════════════════════════════════════════════════════════════════════════════

def render_sidebar() -> None:
    st.sidebar.title("🪐 Asteroid pipeline")

    dest_default = st.session_state.get("destination", MASTER.delivery_destination)
    st.sidebar.selectbox(
        "Delivery destination",
        DESTINATIONS,
        index=DESTINATIONS.index(dest_default) if dest_default in DESTINATIONS else 0,
        key="destination",
        help="Sets Stage 2 pricing AND Stage 4 architecture together. They are "
             "meaningless apart, so the UI writes both through "
             "MASTER_CONFIG.delivery_destination.",
    )
    destination = st.session_state["destination"]

    st.sidebar.divider()
    st.sidebar.subheader("Stages to run")

    stale_mineral = False
    cached_dest = cached_mineral_destination()
    selected: List[str] = []

    for stage in STAGES:
        status = stage_cache_status(stage)
        if status["cached"]:
            age = status["age_s"]
            when = (f"{age / 3600:.1f} h ago" if age > 3600
                    else f"{age / 60:.0f} min ago")
            note = f"cached · {status['size_mb']:.1f} MB · {when}"
            default = stage.key not in ("catalog",)
        else:
            note = "not built — must run"
            default = True

        # A cached mineral catalog priced for a different destination is not a
        # cache, it is a trap.  Force the re-run rather than let Stage 4 pair
        # cislunar prices with a Utah re-entry.
        if stage.key == "mineral" and status["cached"] and cached_dest \
                and cached_dest != destination:
            stale_mineral = True
            note = f"⚠️ cached for **{cached_dest}** — must re-run"
            default = True

        checked = st.sidebar.checkbox(
            f"**{stage.number}. {stage.label}**",
            value=st.session_state.get(f"stage::{stage.key}", default),
            key=f"stage::{stage.key}",
            help=stage.blurb,
            disabled=(stage.key == "mineral" and stale_mineral),
        )
        st.sidebar.caption(note)
        if checked or (stage.key == "mineral" and stale_mineral):
            selected.append(stage.key)

    if stale_mineral:
        st.sidebar.warning(
            f"Stage 2 is cached for **{cached_dest}** but you have selected "
            f"**{destination}**. Re-running it is forced — skipping would price "
            "the cargo at one destination and fly it to another.",
            icon="⚠️",
        )

    # Stage 4 reads what Stages 1-3 wrote, so a skipped upstream stage needs its
    # CSV already on disk.
    missing_inputs: List[str] = []
    if "calc" in selected:
        for upstream in STAGES[:3]:
            if upstream.key not in selected and not stage_cache_status(upstream)["cached"]:
                missing_inputs.append(f"Stage {upstream.number} ({upstream.label})")

    st.sidebar.divider()

    if missing_inputs:
        st.sidebar.error(
            "Stage 4 needs input that is neither selected nor cached: "
            + ", ".join(missing_inputs),
            icon="🚫",
        )

    run_disabled = (not selected) or bool(missing_inputs)
    if st.sidebar.button("▶️  Run pipeline", type="primary",
                         use_container_width=True, disabled=run_disabled):
        st.session_state["run_requested"] = list(selected)

    est = _runtime_estimate(selected)
    if selected:
        st.sidebar.caption(f"Rough estimate: **{est}**")

    st.sidebar.divider()
    st.sidebar.caption(f"Output dir\n\n`{MASTER.output_dir}`")
    if st.sidebar.button("↺  Reset config to defaults", use_container_width=True):
        # Deferred: reset_config() deletes widget-bound keys, which is only
        # legal before those widgets exist.  main() handles the flag on entry.
        st.session_state["reset_requested"] = True
        st.rerun()


def _runtime_estimate(selected: List[str]) -> str:
    """Very rough wall-clock estimate, from the timings recorded in CLAUDE.md."""
    if not selected:
        return "—"
    minutes = 0.0
    if "catalog" in selected:
        minutes += 6.0                                   # ~500 MB of downloads
    if "mineral" in selected:
        minutes += 1.0
    if "transport" in selected:
        minutes += 0.3
    if "calc" in selected:
        rows = st.session_state.get("cfg::calc::eval_row_cap",
                                    MASTER.calc.eval_row_cap) or 35_000
        benef = st.session_state.get("cfg::calc::use_beneficiation",
                                     MASTER.calc.use_beneficiation)
        per_row_s = 0.031 if benef else 0.004            # ~1,100 s vs ~140 s at 35k
        minutes += rows * per_row_s / 60.0
    if minutes < 1:
        return "under a minute"
    if minutes < 90:
        return f"~{minutes:.0f} min"
    return f"~{minutes / 60:.1f} h"


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

CURATED_KEYS = {
    f"{section}::{name}"
    for _, _, fields in ui_meta.CURATED_GROUPS
    for section, name in fields
}


def render_config_page() -> None:
    st.caption(
        "Every field of all four config dataclasses, introspected at runtime. "
        "Hover the ⓘ on any field for the module's own comment explaining it — "
        "those comments are the real documentation for this model, and they are "
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
                    if section == "__master__" and name == "delivery_destination":
                        st.text_input(
                            "delivery destination",
                            value=st.session_state.get(
                                "destination", MASTER.delivery_destination),
                            disabled=True, key="destination_mirror",
                            help="Set in the sidebar. Writes Stage 2 pricing "
                                 "and Stage 4 architecture together.",
                        )
                        continue
                    spec = SPEC_INDEX.get(f"{section}::{name}")
                    if spec is not None:
                        render_field(spec)
            st.divider()

    for tab, section in zip(tabs[1:], CONFIG_OBJECTS):
        with tab:
            paths = [s for s in SPECS[section] if s.is_path]
            dials = [s for s in SPECS[section] if not s.is_path]
            for group, specs in ui_meta.group_specs(dials):
                st.markdown(f"##### {group}")
                cols = st.columns(2)
                for i, spec in enumerate(specs):
                    with cols[i % 2]:
                        # Live control lives on the Common tab; a second widget
                        # sharing its key would be a duplicate-key error.
                        if f"{spec.section_key}::{spec.name}" in CURATED_KEYS:
                            render_mirror(spec)
                        else:
                            render_field(spec)
                st.divider()
            if paths:
                with st.expander("Paths and filenames"):
                    st.caption(
                        "`output_dir` is intentionally absent — "
                        "`MasterConfig.apply()` overwrites every sub-config's "
                        "copy from the master, so an edit here would be "
                        "silently discarded."
                    )
                    cols = st.columns(2)
                    for i, spec in enumerate(paths):
                        with cols[i % 2]:
                            render_field(spec)


def _render_run_report() -> None:
    """Replay the last run's outcome and log from session state."""
    error = st.session_state.get("run_error")
    if error:
        st.error(error)
    elif st.session_state.get("run_elapsed") is not None:
        finished = st.session_state.get("run_finished_at")
        when = finished.strftime("%H:%M:%S") if finished else "—"
        st.success(
            f"Last run finished at {when} in "
            f"{st.session_state['run_elapsed']:.1f}s. Config snapshot → "
            f"`{st.session_state.get('run_manifest', '—')}`"
        )
    with st.expander("Run log"):
        for key, log in st.session_state.get("run_logs", {}).items():
            st.markdown(f"**Stage {key}**")
            st.code(log or "(no output)", language="text")
    st.divider()


def main() -> None:
    # Before any widget exists — see reset_config().
    if st.session_state.pop("reset_requested", False):
        reset_config()

    render_sidebar()

    st.title("Asteroid mining profitability")
    st.caption(
        f"master 1.13.0 · catalog {MASTER.catalog.pipeline_version} · "
        f"mineral_value {MASTER.mineral.pipeline_version} · "
        f"transportation {MASTER.transport.pipeline_version} · "
        f"calc {MASTER.calc.pipeline_version}"
    )

    page = st.radio("Section", ["⚙️  Configure", "📊  Results"],
                    horizontal=True, label_visibility="collapsed")

    requested = st.session_state.pop("run_requested", None)
    if requested:
        st.subheader("Run")
        run_stages(requested)          # reruns on success; returns here on failure

    if st.session_state.get("run_error") or st.session_state.pop(
            "run_report_pending", False) or st.session_state.get("run_logs"):
        _render_run_report()

    if page.endswith("Configure"):
        render_config_page()
        return

    path = results_path()
    if not os.path.exists(path):
        st.info(
            "No profitability catalog yet. Pick your stages in the sidebar and "
            "run the pipeline.", icon="📭",
        )
        return

    token = st.session_state.get("results_token", os.path.getmtime(path))
    df = load_results(path, token)
    if df.empty:
        st.warning("The profitability catalog is empty — check the run log.")
        return

    manifest_path = os.path.join(MASTER.output_dir, RUN_CONFIG_FILENAME)
    if os.path.exists(manifest_path):
        with st.expander("What produced these numbers"):
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            st.write({
                "written_at": manifest.get("written_at"),
                "delivery_destination": manifest.get("delivery_destination"),
                "stages_run": manifest.get("stages_run"),
                "versions": manifest.get("versions"),
            })
            changes = manifest.get("changes_from_defaults") or []
            st.markdown("**Config changed from the loaded defaults:**")
            st.code("\n".join(changes) if changes else "(none)", language="text")

    render_provenance()
    render_results(df)


main()
