"""verify.py check 8 must refuse under the Rust ladder, and must not refuse
without it.

    python check8_guard.py 1    # Rust mode: exit 0 when check_bound refuses
    python check8_guard.py 0    # Python mode: exit 0 when the ladder is off
"""
import os
import sys
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "..", ".."))
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ["ECONOMICSPACE_RUST"] = sys.argv[1]
import modules.calc as calc  # noqa: E402
import verify  # noqa: E402

if sys.argv[1] == "1":
    assert calc._ES_LADDER is not None
    r = verify.check_bound(None, [])
    print("rust mode: check_bound returned", r)
    sys.exit(0 if r is False else 1)
assert calc._ES_LADDER is None
print("python mode: _ES_LADDER is None, guard does not fire")
