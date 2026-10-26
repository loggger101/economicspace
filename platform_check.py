# -*- coding: utf-8 -*-
"""Is THIS host able to reproduce the committed numbers?  Answer in ~10 seconds.

A shim over `samebytes.parity`, bound to this repository's reference
(`platform_reference.json`) and to its own commands in the printed advice.
The probes moved to samebytes (github.com/loggger101/samebytes) with this
file's history on 2026-10-25; what each probe measures and why its argument
range is the model's own is that module's docstring.

What does NOT travel between hosts is BIT-IDENTITY, the whole currency of this
project: `math.exp` and numpy's kernels are not required to be correctly
rounded, so two hosts can disagree in the last bit with nothing wrong.  This
says whether this host's cell hashes are comparable with the committed ones.

    python platform_check.py --record     # on the reference host, once
    python platform_check.py              # on the new host: compare and report

Exit codes: 0 all probes match, 1 a probe differs, 2 the reference is missing.
Everything runs under the `__main__` guard: the spawn probe starts a pool,
and a spawned worker re-imports this file.
"""
import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCE = os.path.join(HERE, "platform_reference.json")

# The launcher to name in a printed instruction.  `py` is the Windows launcher
# and does not exist anywhere else.
_PY = "py" if os.name == "nt" else os.path.basename(sys.executable)

# This repository's phrases in samebytes' advice; see `samebytes.parity.HINTS`.
HINTS = {
    "rebaseline": "%s verify.py baseline" % _PY,
    "record": "%s platform_check.py --record" % _PY,
    "record_missing": "python platform_check.py --record",
    "traps_doc": "CLAUDE.md",
    "hashes_doc": "versions.md",
}


def main(argv=None):
    """Install the pinned samebytes if needed, then record or check this host."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    from modules import _runtime
    if "samebytes" not in _runtime.PIP_SPEC:
        raise SystemExit("platform_check: requirements-verify.txt has no single "
                         "`samebytes @ git+...@vX.Y.Z` line, so the pinned "
                         "samebytes cannot be named")
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        _runtime.install(["samebytes"])
    if said.getvalue().replace("OK  All packages present\n", ""):
        print(said.getvalue(), end="")
    from samebytes import parity
    return parity.main(argv, reference=REFERENCE, hints=HINTS)


if __name__ == "__main__":
    sys.exit(main())
