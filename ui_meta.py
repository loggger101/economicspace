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
    # Only consulted when eval_row_cap > 0.  "stride" samples the whole
    # catalog; "head" takes the innermost N bodies, which is what a cap did
    # before calc v1.13.0 and is kept so an old run can be reproduced.
    "eval_row_sampling": ["stride", "head"],
    "candidate_vehicles": None,            # from transportation/launch_vehicles.csv
    "candidate_propellants": None,         # from transportation/propellants.csv
}

# Explicit numeric bounds where the default heuristic would get them wrong, or
# where a bad value wastes a 20-minute run. (min, max, step).
BOUNDS: Dict[str, Tuple[float, float, float]] = {
    # 0 = unlimited on all four source caps, so the minimum must be 0 rather
    # than 100 — a slider that cannot reach 0 cannot express "take the whole
    # table", which is the v1.1.0 default.  Upper bounds are each source's real
    # size measured 2026-08-08: JPL 1,554,321 asteroids, SsODNet ~1.2 M rows,
    # NEOWISE 183,412, MP3C ~1.2 M.
    "jpl_limit":                         (0, 2_000_000, 10_000),
    "ssodnet_limit":                     (0, 2_000_000, 10_000),
    "neowise_limit":                     (0, 200_000, 1_000),
    "mp3c_limit":                        (0, 2_000_000, 10_000),
    "min_derived_diameter_km":           (0.0, 100.0, 0.001),
    # Must reach the full 1.55 M catalog, otherwise the slider itself becomes a
    # cap the user cannot see past.
    "eval_row_cap":                      (0, 2_000_000, 500),
    # 0 = auto.  The upper bound is deliberately generous rather than
    # os.cpu_count(): calc clamps to the real CPU count anyway, and pinning the
    # slider to this machine would bake a host detail into a config the UI
    # writes to ui_run_config.json and users copy between machines.
    "parallel_workers":                  (0, 64, 1),
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
    "rtg_max_power_w":                   (0.0, 1_000_000.0, 500.0),
    "nre_amortization_missions":         (1, 1_000, 1),
    "max_fleet_ships":                   (1, 500, 1),
    "programme_search_steps":            (2, 40, 1),
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
# architecture search, and then "the twenty things the model stopped giving
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
        "What this run costs you in wall-clock time. Every cap here means "
        "UNLIMITED at 0. catalog v1.1.0 removed the shared row cap and can now "
        "hand Stage 4 ~1.55 million asteroids instead of ~89 thousand, so these "
        "are no longer minor dials: a full beneficiated destination goes from "
        "minutes to hours. Cap the rows to sanity-check a config change first — "
        "and note that calc v1.13.0 makes a capped run an evenly-spaced sample "
        "of the whole belt rather than the innermost N bodies.",
        [
            ("catalog", "jpl_limit"),
            ("catalog", "ssodnet_limit"),
            ("catalog", "neowise_limit"),
            ("catalog", "mp3c_limit"),
            ("calc", "eval_row_cap"),
            ("calc", "eval_row_sampling"),
            ("calc", "concentration_search_steps"),
            ("calc", "parallel_workers"),
        ],
    ),
    (
        "Catalog population",
        "How many asteroids exist at all. Only 139,582 of JPL's 1,554,321 "
        "asteroids have a MEASURED diameter, and Stage 1 drops any body "
        "without one. Deriving diameter from absolute magnitude H lifts the "
        "catalog to ~1.55 million, at the cost of an assumed albedo on every "
        "derived row — and mass scales as albedo^-1.5, so those rows are much "
        "softer than their diameters look. Every one is tagged in "
        "`diameter_source`.",
        [
            ("catalog", "derive_diameter_from_h"),
            ("catalog", "min_derived_diameter_km"),
            ("catalog", "min_diameter_km"),
            ("catalog", "require_spectral_type"),
        ],
    ),
    (
        "The big levers",
        "The five settings that change what question the run is answering. "
        "`optimise_programme_scale` is the newest and the sharpest: OFF, a run "
        "answers \"the best single mission to this rock at N missions\"; ON, it "
        "answers \"the best programme built around it\", sizing the fleet, the "
        "schedule and N together. Every committed figure in CLAUDE.md and the "
        "README was measured OFF at N = 1, so turning it on does not make them "
        "wrong — it changes the question. It is affordable because programme "
        "size touches nothing in the mass cascade: the rocket equation, the "
        "power fixed point and the concentration sweep are solved once per "
        "candidate and every programme is priced off the result. (The 1.51x "
        "runtime measured on the full catalog is a v1.15.0 figure, for a search "
        "that was one-dimensional; v1.16.0's is two-dimensional and has not been "
        "measured on the full catalog.)",
        [
            ("calc", "use_beneficiation"),
            ("calc", "nre_amortization_missions"),
            ("calc", "optimise_programme_scale"),
            ("calc", "selection_objective"),
            ("calc", "optimise_architecture_per_asteroid"),
        ],
    ),
    (
        "Programme scale and fleet size",
        "The dials behind `optimise_programme_scale` in the group above. One rig "
        "serves `min(service life / stay, maximum trips)` missions back to back, "
        "so a programme of N needs ceil(N / that) rigs and that many payloads "
        "hit the market at once. Since v1.16.0 that is no longer the only thing "
        "pushing back on scale: `model_programme_calendar` charges the calendar "
        "the programme actually spans, and a programme that flies more campaigns "
        "per ship carries its NRE and its rig for longer before they sell "
        "anything. So the search is two-dimensional — a ladder over the FLEET, "
        "and every campaigns-per-ship value enumerated exhaustively, because "
        "there are at most a handful of them. "
        "`max_fleet_ships` bounds the ladder — if rows pile up against it the "
        "run says so, and it means those payloads have no finite market rather "
        "than that bigger is better. `model_rig_trip_limit` and "
        "`model_programme_calendar` are corrections rather than options — a rig "
        "wears out on duty cycles as well as on a calendar, and a programme "
        "takes years — and they sit here because between them they set the trip "
        "life and the schedule this whole search is built on. Both are inert at "
        "N = 1.",
        [
            ("calc", "max_fleet_ships"),
            ("calc", "programme_search_steps"),
            ("calc", "model_rig_trip_limit"),
            ("calc", "model_programme_calendar"),
        ],
    ),
    (
        "Architecture availability",
        "Since v1.10.0 these mean *available*, not *mandatory*. The "
        "per-asteroid search decides whether to use them. "
        "`operational_propellants_only` is the gate on Stage 3's 40-row "
        "propellant table: leave it ON unless you specifically want the run to "
        "consider hardware that has never flown.",
        [
            ("calc", "use_aerocapture_return"),
            ("calc", "use_isru_return_propellant"),
            ("calc", "use_per_asteroid_dv"),
            ("calc", "operational_vehicles_only"),
            ("calc", "operational_propellants_only"),
            ("calc", "allow_rtg_power"),
        ],
    ),
    (
        "Hopeless candidates (v1.14.1)",
        "⚠️  Leave this ON. Roughly **76% of the (vehicle × propellant × return "
        "mode × propellant sourcing) candidates the search generates cannot "
        "close their mass budget at all** — they are not bad missions, they are "
        "not missions. Before v1.14.1 each one paid the full sizing prologue to "
        "be told so, once per power source and once per point of the "
        "concentration sweep: up to eighteen times for the same dead candidate. "
        "Skipping them makes the search 1.5–1.7× faster and changes NO output, "
        "because the test is the sizing loop's own first iteration in closed "
        "form, and that iteration is the most optimistic one it will ever take. "
        "Turn it OFF only to reproduce the v1.14.0 search, or to check the "
        "pruner on a population nobody has tried — if an output ever moves, "
        "that is a bug in the pre-filter, not a result. The run log prints how "
        "much it is actually removing; a rate near 0% or near 100% is worth "
        "investigating either way.",
        [
            ("calc", "prune_infeasible_combos"),
        ],
    ),
    (
        "The sixteen corrections",
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
            ("calc", "model_tank_mass"),
            ("calc", "model_eclipse_power"),
            ("calc", "model_volatile_containment"),
            ("calc", "charge_tanker_flights"),
            ("calc", "apply_wacc_compounding"),
            ("calc", "learning_curve_rate"),
            ("calc", "return_structure_frac_of_payload"),
        ],
    ),
    (
        "Night-side power (v1.14.0)",
        "A rig anchored to a rotating body is in shadow about half the time, so "
        "the processing plant needs an oversized array AND a battery sized on "
        "the body's own rotation period. `default_rotation_period_h` is used "
        "only where the catalog has no measured period — about two thirds of "
        "rows — and `max_dark_period_h` clamps the slow rotators, where a "
        "chemical battery stops being the right answer at all.",
        [
            ("calc", "default_rotation_period_h"),
            ("calc", "max_dark_period_h"),
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
