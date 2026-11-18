"""Plant: route every 'Rust' call in spacevalue's tests/test_cargo_rust.py to
the Python.  Each fuzz test must FAIL on its fast-share check (it would
otherwise compare the Python with itself).  Exit 0 when all three are caught.

    python sv_share.py SPACEVALUE_CHECKOUT
"""
import os
import sys
import types

SV = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.join(SV, "tests"))
sys.path.insert(0, SV)
import test_cargo_rust as t  # noqa: E402
from spacevalue import cargo  # noqa: E402

real = t.rs
t.rs = types.SimpleNamespace(
    optimal_payload_mix=cargo.optimal_payload_mix,
    _hold_refining=cargo._hold_refining,
    _capped_sale_value=cargo._capped_sale_value,
    counts=real.counts)
caught = 0
for name in ("test_rust_mix_matches_python_on_hostile_inputs",
             "test_rust_hold_refining_matches_python",
             "test_rust_capped_sale_matches_python"):
    try:
        getattr(t, name)()
        print("MISSED", name)
    except AssertionError as e:
        caught += 1
        print("CAUGHT", name, e)
print("caught %d of 3" % caught)
sys.exit(0 if caught == 3 else 1)
