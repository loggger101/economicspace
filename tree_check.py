# -*- coding: utf-8 -*-
"""Does the working tree contain the bytes git says it contains?

A shim over `samebytes.tree`, bound to this repository.  The check moved to
samebytes (github.com/loggger101/samebytes) with this file's history on
2026-10-25; the account of the failure it catches (a synced folder serving
stale or absent bytes while `git status` stays clean) and of why a content
hash through `git hash-object` is the only way to see it is that module's
docstring.

    python tree_check.py      exit 0 verified, 1 a finding, 2 skipped

Every harness here imports this and calls `assert_tree()` before it reads
anything.  The pin is the one `samebytes @ ...@vX.Y.Z` line in
requirements-verify.txt; `modules/_runtime.install()` reads it, installs that
tag when samebytes is missing or at another, and refuses an editable or
shadowing copy.
"""
import contextlib
import io
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
from modules import _runtime  # noqa: E402

if "samebytes" not in _runtime.PIP_SPEC:
    raise SystemExit("tree_check: requirements-verify.txt has no single "
                     "`samebytes @ git+...@vX.Y.Z` line, so the pinned "
                     "samebytes cannot be named")

# install() says "OK  All packages present" when there is nothing to do; every
# harness imports this file, so only what it says otherwise is passed on.
_said = io.StringIO()
with contextlib.redirect_stdout(_said):
    _runtime.install(["samebytes"])
if _said.getvalue().replace("OK  All packages present\n", ""):
    print(_said.getvalue(), end="")

from samebytes import tree as _tree  # noqa: E402


def verify_tree():
    """(findings, files verified, skip reason) for this repository."""
    return _tree.verify_tree(REPO)


def assert_tree(label=""):
    """Print this repository's one-line verdict; False only on a real finding."""
    return _tree.assert_tree(REPO, label)


if __name__ == "__main__":
    raise SystemExit(_tree.main(REPO))
