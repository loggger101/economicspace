# -*- coding: utf-8 -*-
"""Bit-for-bit comparison of two results, shared by the gate scripts.

`verify_rust.py`, `shadow_rust.py` and `bench_rust.py` each compare a Python
answer with a Rust one; this is the one rule they all use.  Two results are
the same when any downstream reader would see the same thing: same type,
same keys in the same order, floats and numpy scalars equal as bit patterns
(so NaN equals NaN and -0.0 differs from 0.0), recursively through dicts,
lists and tuples.  A type it has no rule for is never called equal unless
it is the same object or compares equal.
"""
import struct

import numpy as np


def bits(x):
    """A float's IEEE-754 bit pattern."""
    return struct.pack("<d", x)


def diffs(a, b, path="result", out=None):
    """Every path at which `a` and `b` differ (an empty list: identical)."""
    out = [] if out is None else out
    if type(a) is not type(b):
        out.append("%s type %s vs %s" % (path, type(a).__name__, type(b).__name__))
    elif isinstance(a, float):
        if bits(a) != bits(b):
            out.append("%s %s vs %s" % (path, bits(a).hex(), bits(b).hex()))
    elif isinstance(a, np.generic):
        if a.tobytes() != b.tobytes():
            out.append("%s np %r vs %r" % (path, a, b))
    elif isinstance(a, dict):
        if list(a) != list(b):
            out.append("%s keys differ" % path)
        else:
            for k in a:
                diffs(a[k], b[k], "%s.%s" % (path, k), out)
    elif isinstance(a, (list, tuple)):
        if len(a) != len(b):
            out.append("%s len %d vs %d" % (path, len(a), len(b)))
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                diffs(x, y, "%s[%d]" % (path, i), out)
    elif a is None or isinstance(a, (str, bool, int)):
        if a != b:
            out.append("%s %r vs %r" % (path, a, b))
    elif not (a is b or a == b):
        # anything else would need its own rule; refuse to call it equal
        out.append("%s unhandled %s" % (path, type(a).__name__))
    return out


def same(a, b):
    """True when `a` and `b` are identical bit for bit (see `diffs`)."""
    return not diffs(a, b)


def outcome(f, *a, **kw):
    """`("ok", result)`, or `("raised", type name, message)`: an exception is
    compared like a result, never swallowed."""
    try:
        return ("ok", f(*a, **kw))
    except Exception as exc:  # noqa: BLE001 - compared, not swallowed
        return ("raised", type(exc).__name__, str(exc))


if __name__ == "__main__":
    # self-check: the cases the rule exists for
    nan = float("nan")
    assert same(nan, nan) and not same(0.0, -0.0)
    assert not same(1, 1.0) and not same(True, 1)
    assert same({"a": (1.0, [nan])}, {"a": (1.0, [nan])})
    assert not same({"a": 1.0, "b": 2.0}, {"b": 2.0, "a": 1.0})
    assert not same((0.0,), (-0.0,)) and not same([1.0], [1.0, 2.0])
    assert same(np.float64(nan), np.float64(nan))
    assert not same(np.float64(0.0), np.float64(-0.0))
    assert outcome(int, "x")[0] == "raised" and outcome(int, "3") == ("ok", 3)
    print("bitsame self-check OK")
