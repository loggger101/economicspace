# -*- coding: utf-8 -*-
"""Config introspection and curation for the pipeline UI.

Deliberately NOT in `modules/`: `build_master.py` concatenates every module in
that directory into `master.py` and asserts a specific header/footer shape on
each one. The UI is a *consumer* of `master.py`, not a part of it, so it lives
at the repo root alongside `build_master.py`.

Two jobs:

1.  **Introspect.** Walk the four config dataclasses and emit a widget spec per
    field, so a field added to `CalcConfig` tomorrow shows up in the UI without
    anyone remembering to list it here.

2.  **Curate.** Decide what belongs on the front page, what is a path rather
    than a dial, and which fields have a fixed set of legal values.

The help text shown in the UI is scraped straight out of the module sources.
Those comment blocks are the real documentation for this model. The repo's
whole premise is that a number without its reasoning attached gets "fixed" by
the next person, so the UI surfaces them rather than paraphrasing.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import re
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))

# Which module source backs each config, for comment scraping. The class names
# are the *module* names, not the renamed master.py globals: build_master.py
# renames the CONFIG instances, not the classes.
CONFIG_SOURCES: Dict[str, Tuple[str, str]] = {
    "catalog":   (os.path.join(_HERE, "modules", "catalog.py"),        "CatalogConfig"),
    "mineral":   (os.path.join(_HERE, "modules", "mineral_value.py"),  "MineralValueConfig"),
    "transport": (os.path.join(_HERE, "modules", "transportation.py"), "TransportConfig"),
    "calc":      (os.path.join(_HERE, "modules", "calc.py"),           "CalcConfig"),
}

SECTION_LABELS: Dict[str, str] = {
    "catalog":   "Stage 1 · Catalog",
    "mineral":   "Stage 2 · Mineral value",
    "transport": "Stage 3 · Transportation",
    "calc":      "Stage 4 · Profitability",
}


# ─────────────────────────────────────────────────────────────────────────────
# FIELDS THE UI TREATS SPECIALLY
# ─────────────────────────────────────────────────────────────────────────────

# Paths and filenames. Real settings, but plumbing rather than model
# assumptions, so they get their own collapsed section instead of sitting among
# the dials. `output_dir` is excluded from even that: MasterConfig.apply()
# overwrites every sub-config's copy from the master, so editing one here would
# be silently discarded.
PATH_FIELDS = {
    "input_dir", "output_dir", "cache_dir", "subdir", "transportation_subdir",
    "catalog_filename", "rejected_filename", "output_filename",
    "asteroid_catalog_file", "mineral_catalog_file",
    "launch_vehicles_file", "propellants_file",
    "delta_v_segments_file", "operational_costs_file",
    "metals_api_url",
}

# Shown read-only. `pipeline_version` is the stamp that tells you which code
# produced a CSV. CLAUDE.md is explicit that it must be bumped in the source
# when output changes, so letting the UI edit it would defeat the entire point.
READONLY_FIELDS = {"pipeline_version", "PRICE_UNIT"}

# Never rendered as an ordinary widget anywhere.
#
# `delivery_destination` exists on BOTH the mineral and calc configs and the two
# must agree: Stage 2 decides what a kilogram sells for, Stage 4 decides the
# architecture that puts it there. Rendering two independent widgets is exactly
# the mismatch `destination_check()` exists to catch, so the UI renders one
# control and writes it through `MASTER_CONFIG.delivery_destination`, which sets
# both.
SUPPRESSED_FIELDS = {"delivery_destination"}

# Secrets get a password-style input.
SECRET_FIELDS = {"metals_api_key"}

# Fixed value sets. `None` means "resolve at runtime from the loaded module".
CHOICES: Dict[str, Optional[List[str]]] = {
    "delivery_destination": None,          # from master.DELIVERY_DESTINATIONS
    "selection_objective": ["cost_revenue_ratio", "profit"],
    "candidate_vehicles": None,            # from transportation/launch_vehicles.csv
    "candidate_propellants": None,         # from transportation/propellants.csv
}

# Explicit numeric bounds where the default heuristic would get them wrong, or
# where a bad value wastes a 20-minute run. (min, max, step).
BOUNDS: Dict[str, Tuple[float, float, float]] = {
    "jpl_limit":                         (100, 200_000, 1_000),
    "eval_row_cap":                      (0, 200_000, 500),
    "request_timeout":                   (10, 900, 10),
    "min_diameter_km":                   (0.0, 100.0, 0.001),
    "preview_rows":                      (1, 200, 1),
    "top_n_preview":                     (1, 200, 1),
    "top_n_spectral_types":              (1, 100, 1),
    "cache_max_age_days":                (0.0, 365.0, 1.0),

    "mining_hardware_kg":                (0.0, 100_000.0, 100.0),
    "return_vehicle_dry_kg":             (0.0, 50_000.0, 50.0),
    "return_structure_frac_of_payload":  (0.0, 3.0, 0.01),
    "max_mining_fraction":               (0.0, 1.0, 0.01),
    "mining_rate_kg_per_day_per_kg_rig": (0.0, 10.0, 0.01),
    "max_mining_duration_yr":            (0.0, 50.0, 0.25),
    "station_keeping_floor_yr":          (0.0, 10.0, 0.05),

    "beneficiation_recovery":            (0.0, 1.0, 0.01),
    "max_concentration_ratio":           (1.0, 1_000.0, 1.0),
    "concentration_search_steps":        (2, 40, 1),

    "ep_target_thrust_yr":               (0.1, 30.0, 0.25),
    "max_mission_duration_yr":           (1.0, 100.0, 1.0),
    "learning_curve_rate":               (0.5, 1.0, 0.01),
    "demand_elasticity":                 (0.05, 5.0, 0.05),

    "max_dv_outbound_m_s":               (1_000.0, 60_000.0, 500.0),
    "default_dv_outbound_m_s":           (0.0, 30_000.0, 100.0),
    "default_dv_return_m_s":             (0.0, 30_000.0, 100.0),
    "aerocapture_dv_savings_m_s":        (0.0, 15_000.0, 100.0),
    "heat_shield_frac_of_payload":       (0.0, 2.0, 0.01),

    "isru_processing_usd_per_kg":        (0.0, 100_000.0, 10.0),
    "nre_amortization_missions":         (1, 1_000, 1),
    "nre_recurring_overlap_fraction":    (0.0, 1.0, 0.05),
    "contingency_fraction":              (0.0, 2.0, 0.05),
}

# ─────────────────────────────────────────────────────────────────────────────
# THE CURATED FRONT PAGE
# ─────────────────────────────────────────────────────────────────────────────
# Ordered groups of (config_key, field_name). Everything here is a shortcut to
# the dials that actually move results, not a separate set of settings. Each of
# these renders as the live control on the Common tab and as a read-only mirror
# on its module tab.
#
# The grouping follows CLAUDE.md: the destination, the run-size dials, the
# architecture search, and then "the twelve things the model stopped giving
# away", which are corrections rather than options.

CURATED_GROUPS: List[Tuple[str, str, List[Tuple[str, str]]]] = [
    (
        "Destination",
        "Where the material is sold. Sets Stage 2 pricing and Stage 4 "
        "architecture together; they are meaningless apart.",
        [("__master__", "delivery_destination")],
    ),
    (
        "Run size",
        "What this run costs you in wall-clock time. A full beneficiated "
        "catalog is roughly 20 minutes per destination, so capping the rows is "
        "how you sanity-check a config change first.",
        [
            ("catalog", "jpl_limit"),
            ("calc", "eval_row_cap"),
            ("calc", "concentration_search_steps"),
        ],
    ),
    (
        "The big levers",
        "The four settings that change what question the run is answering.",
        [
            ("calc", "use_beneficiation"),
            ("calc", "nre_amortization_missions"),
            ("calc", "selection_objective"),
            ("calc", "optimise_architecture_per_asteroid"),
        ],
    ),
    (
        "Architecture availability",
        "Since v1.10.0 these mean *available*, not *mandatory*. The "
        "per-asteroid search decides whether to use them.",
        [
            ("calc", "use_aerocapture_return"),
            ("calc", "use_isru_return_propellant"),
            ("calc", "use_per_asteroid_dv"),
        ],
    ),
    (
        "The twelve corrections",
        "⚠️  These default ON and each one moved every number. They are "
        "corrections, not options: the flags exist to isolate an effect, not "
        "to be left off. Switching them off makes the model more profitable "
        "and less true.",
        [
            ("calc", "model_low_thrust_time"),
            ("calc", "model_launch_windows"),
            ("calc", "model_water_liberation"),
            ("calc", "model_market_saturation"),
            ("calc", "model_rig_service_life"),
            ("calc", "model_reliability"),
            ("calc", "model_reliability_growth"),
            ("calc", "model_propellant_boiloff"),
            ("calc", "apply_wacc_compounding"),
            ("calc", "learning_curve_rate"),
            ("calc", "return_structure_frac_of_payload"),
        ],
    ),
    (
        "Data sources",
        "A source that fails soft does not shrink the catalog, it inflates it "
        "with albedo-guessed taxonomy. Check the provenance panel on the "
        "results page before comparing to a committed number.",
        [
            ("catalog", "use_jpl"),
            ("catalog", "use_mp3c"),
            ("catalog", "use_ssodnet"),
            ("catalog", "use_neowise"),
            ("mineral", "use_yfinance"),
            ("mineral", "use_metals_api"),
        ],
    ),
]

CURATED_KEYS = {
    f"{section}::{name}"
    for _, _, fields in CURATED_GROUPS
    for section, name in fields
}


# ─────────────────────────────────────────────────────────────────────────────
# COMMENT SCRAPING
# ─────────────────────────────────────────────────────────────────────────────

# Matches `# ─── MINING THROUGHPUT  (v1.4.0) ────────────────────` and friends.
# The modules use box-drawing rules of a few different characters.
#
# The class is built through re.escape because a literal "-" sitting between
# two other characters is a RANGE, not a hyphen: the same family of mistake as
# the `str.contains(..., regex=False)` fixes in the pipeline itself.
_RULE_CHARS = "".join(re.escape(c) for c in "─═━=_·•-")
_BANNER_RE = re.compile(
    rf"^#\s*[{_RULE_CHARS}]{{2,}}\s*(?P<title>.*?)\s*[{_RULE_CHARS}]{{2,}}\s*$"
)
_BARE_RULE_RE = re.compile(rf"^#\s*[{_RULE_CHARS}]{{4,}}\s*$")


def _banner_title(line: str) -> Optional[str]:
    """Section title if `line` is a section banner, else None.

    A banner must have an actual title. The version-history blocks above each
    `pipeline_version` are markdown-ish tables whose separator rows otherwise
    match the banner shape and produce a group literally named
    `------  ----------------`.
    """
    match = _BANNER_RE.match(line.strip())
    if not match:
        return None
    title = match.group("title").strip()
    # Reject a "title" made of nothing but more rule characters.
    if not title or not re.search(r"[0-9A-Za-zΔ]", title):
        return None
    return title


def _clean_comment(line: str) -> str:
    body = line.lstrip()[1:]
    return body[1:] if body.startswith(" ") else body


def scrape_field_docs(path: str, class_name: str) -> Dict[str, Dict[str, str]]:
    """field name -> {"help", "section"} scraped from a module source.

    Walks backwards from each field definition collecting the comment block
    directly above it, stopping at the first blank line or section banner. The
    banner title, if there is one, becomes the field's group heading: the
    modules already organise their configs into labelled sections and there is
    no reason for the UI to invent its own taxonomy.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return {}

    lines = src.split("\n")
    cls = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.ClassDef) and n.name == class_name),
        None,
    )
    if cls is None:
        return {}

    docs: Dict[str, Dict[str, str]] = {}
    for stmt in cls.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue

        block: List[str] = []
        section = ""

        i = stmt.lineno - 2          # 0-indexed line directly above the field
        while i >= 0 and lines[i].strip() and lines[i].lstrip().startswith("#"):
            section = _banner_title(lines[i]) or ""
            if section or _BARE_RULE_RE.match(lines[i].strip()):
                break
            block.append(_clean_comment(lines[i]))
            i -= 1

        # If the field had no comment of its own, keep scanning up for the
        # section banner it lives under so it still gets grouped.
        while not section and i >= 0:
            line = lines[i].strip()
            if line.startswith("class ") or line.startswith("@dataclass"):
                break
            section = _banner_title(line) or ""
            i -= 1

        docs[stmt.target.id] = {
            "help": "\n".join(reversed(block)).strip(),
            "section": section or "Other",
        }

    return docs


# ─────────────────────────────────────────────────────────────────────────────
# WIDGET SPECS
# ─────────────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class FieldSpec:
    """Everything ui.py needs to render one config field."""
    section_key: str                 # "calc"
    name: str                        # "use_beneficiation"
    kind: str                        # bool | int | float | str | choice | list | readonly
    default: Any
    help: str = ""
    group: str = "Other"
    choices: Optional[List[str]] = None
    bounds: Optional[Tuple[float, float, float]] = None
    secret: bool = False
    is_path: bool = False

    @property
    def key(self) -> str:
        """Stable session-state key, which is also the Streamlit widget key."""
        return f"cfg::{self.section_key}::{self.name}"

    @property
    def curated(self) -> bool:
        return f"{self.section_key}::{self.name}" in CURATED_KEYS


def _kind_for(name: str, field: dataclasses.Field, default: Any) -> str:
    ann = str(field.type)

    if name in READONLY_FIELDS:
        return "readonly"
    if name in CHOICES:
        return "list" if "List" in ann else "choice"
    if isinstance(default, bool):          # before int, because bool IS an int
        return "bool"

    # The ANNOTATION wins over the default's runtime type. Several float fields
    # are written with an int literal (`mining_hardware_kg: float = 2_000`), and
    # typing off the value alone would hand them an integer stepper and write an
    # int back into a float field.
    if "float" in ann:
        return "float"
    if "int" in ann:
        return "int"
    if isinstance(default, float):
        return "float"
    if isinstance(default, int):
        return "int"
    return "str"


def _infer_bounds(name: str, default: Any,
                  kind: str) -> Optional[Tuple[float, float, float]]:
    if name in BOUNDS:
        return BOUNDS[name]
    if default is None or kind not in ("int", "float"):
        return None
    if kind == "int":
        return (0, max(1_000, abs(int(default)) * 100), 1)

    default = float(default)
    # A field whose name says "fraction" and whose default sits in [0, 1] is a
    # fraction; anything else gets a permissive non-negative range.
    if ("frac" in name or name.endswith("_rate")) and 0.0 <= default <= 1.0:
        return (0.0, 1.0, 0.01)
    span = max(1.0, abs(default) * 100.0)
    step = 10.0 ** (len(str(int(abs(default)))) - 2) if abs(default) >= 100 else 0.01
    return (0.0, span, max(step, 0.01))


def build_field_specs(config_obj: Any, section_key: str) -> List[FieldSpec]:
    """Introspect one config dataclass into an ordered list of FieldSpecs."""
    docs = scrape_field_docs(*CONFIG_SOURCES[section_key])

    specs: List[FieldSpec] = []
    for field in dataclasses.fields(config_obj):
        name = field.name
        if name in SUPPRESSED_FIELDS:
            continue

        default = getattr(config_obj, name, field.default)
        doc = docs.get(name, {})
        kind = _kind_for(name, field, default)

        specs.append(FieldSpec(
            section_key=section_key,
            name=name,
            kind=kind,
            default=default,
            help=doc.get("help", ""),
            group=doc.get("section", "Other"),
            choices=CHOICES.get(name),
            bounds=_infer_bounds(name, default, kind),
            secret=name in SECRET_FIELDS,
            is_path=name in PATH_FIELDS,
        ))

    return specs


def group_specs(specs: List[FieldSpec]) -> List[Tuple[str, List[FieldSpec]]]:
    """Bucket specs by their scraped section banner, preserving source order."""
    buckets: Dict[str, List[FieldSpec]] = {}
    for spec in specs:
        buckets.setdefault(spec.group, []).append(spec)
    return list(buckets.items())          # dicts preserve insertion order
