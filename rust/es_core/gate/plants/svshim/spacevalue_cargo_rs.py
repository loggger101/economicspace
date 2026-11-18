"""PLANT for the shadow's cargo gate: a stand-in for the extension whose
"Rust" cargo calls are spacevalue's own Python.  Rust mode then compares the
Python with itself; the shadow must refuse to call that a pass.  Used only by
putting this directory first on PYTHONPATH (gate_all.sh's plant_cargo_bypass)."""
from spacevalue.cargo import _capped_sale_value, _hold_refining, optimal_payload_mix  # noqa: F401


def counts():
    return (0, 0)


def planted_defect():
    return False
