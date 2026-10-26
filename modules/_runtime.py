# -*- coding: utf-8 -*-
"""What every stage module needs before its own code runs, held once.

    console encoding     UTF-8 on stdout and stderr, before anything prints
    worker quiet mode    a spawned Stage 4 worker's stdout goes to devnull
    DEFAULT_OUTPUT_DIR   where every stage reads and writes unless told not to
    install()            pip-installs what a module is missing, and holds a
                         git-pinned package to its tag
    confirm_overwrite()  what a fetching stage asks before it overwrites the
                         only copy of its inputs

The first three happen when this file is imported, which each module does
before anything else.  install() is CALLED, never run at import: calc imports
this file too, and so does every spawned Stage 4 worker, and neither may touch
spacecost.

A module imports it as `modules._runtime` in package mode and as `_runtime`
when it runs as a script (`python modules/calc.py` puts `modules/` on
sys.path).  Standard library only, since it runs before anything is installed.
"""

import importlib
import importlib.metadata as metadata
import json
import os
import subprocess
import sys

# -----------------------------------------------------------------------------
# CONSOLE ENCODING
# -----------------------------------------------------------------------------
# Windows consoles default to cp1252.  Every print in the four modules is
# ASCII, so this is for what the source does not control: tqdm's bars, a
# traceback quoting a non-ASCII path, data reaching stdout.  Before the first
# print().

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# -----------------------------------------------------------------------------
# SPAWNED-WORKER QUIET MODE
# -----------------------------------------------------------------------------
# Stage 4 evaluates asteroids across a process pool.  Windows has no fork, so
# every worker imports `modules.calc`, and with it this file, and would replay
# calc's banners -- 60 lines each, 700+ for a full pool, interleaved into the
# run log the UI parses.  Stage 4's parent sets ASTEROID_PIPELINE_WORKER before
# creating the pool; children inherit it.  Must run before calc's install
# block prints, which is why it is here: calc imports this file first.
#
# Flipped to "silenced" rather than cleared, so that a second copy of this
# file in one process (imported once as `modules._runtime` and once as
# `_runtime`) is a no-op instead of leaking a second handle.
#
# stderr is deliberately left alone: a worker that dies should still say so.

if os.environ.get("ASTEROID_PIPELINE_WORKER") == "1":
    os.environ["ASTEROID_PIPELINE_WORKER"] = "silenced"
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

# -----------------------------------------------------------------------------
# DEFAULT OUTPUT LOCATION
# -----------------------------------------------------------------------------
# ./asteroid_pipeline under the working directory, or wherever
# ASTEROID_PIPELINE_OUTPUT_DIR says.  Read once, when this file is first
# imported: a caller pointing the stages elsewhere sets the variable before
# importing any of them.

DEFAULT_OUTPUT_DIR = (os.environ.get("ASTEROID_PIPELINE_OUTPUT_DIR")
                      or os.path.join(os.getcwd(), "asteroid_pipeline"))

# -----------------------------------------------------------------------------
# INSTALLATION
# -----------------------------------------------------------------------------
# spacecost is not on PyPI, so it installs from a TAGGED git ref, and a bare
# name in an install list would resolve to nothing.  This maps import name to
# pip argument for every such package.  IF SPACECOST IS EVER PUBLISHED, replace
# the URL with a pinned version ("spacecost==0.1.0").  The tag is typed in
# several places in this repo; verify_docs check 7 finds and holds them all.
PIP_SPEC = {
    "spacecost": "git+https://github.com/loggger101/spacecost@v0.13.0",
}

# samebytes, the toolkit behind tree_check.py, platform_check.py and verify.py's
# run comparison, is the opposite arrangement on purpose: typed ONCE, as the
# one `samebytes @ git+...@vX.Y.Z` line in requirements-verify.txt, and read
# from there.  Only the harnesses install it (`install(["samebytes"])`), never
# a stage module, so it is no part of requirements.txt or of check 7's typed
# copies; check 7 holds it to that one line instead.  No file, or no single
# such line, means it is not pinned here, and the harness says so.
_VERIFY_REQUIREMENTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "requirements-verify.txt")


def _read_pin(path, pkg):
    """The `git+...@vX.Y.Z` spec on `pkg`'s one requirement line in `path`, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    found = []
    for line in lines:
        name, sep, spec = line.partition("@")
        spec = spec.strip()
        if (sep and name.strip() == pkg and spec.startswith("git+")
                and spec.rsplit("@", 1)[-1].startswith("v")):
            found.append(spec)
    return found[0] if len(found) == 1 else None


_SAMEBYTES_SPEC = _read_pin(_VERIFY_REQUIREMENTS, "samebytes")
if _SAMEBYTES_SPEC:
    PIP_SPEC["samebytes"] = _SAMEBYTES_SPEC


def _pinned_pkg_version(name):
    """The version of `name` as it imports, falling back to pip's metadata."""
    found = getattr(__import__(name), "__version__", None)
    if found is None:
        try:
            found = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return found


def _pinned_pkg_origin(name, tag):
    """Why the `name` that imports is not what pip installed from `tag`, or None.

    pip's own record of the install (PEP 610 `direct_url.json`) says which
    revision was ASKED FOR; it describes the INSTALLED copy, so the copy that
    actually imports is held to it too, or a checkout earlier on sys.path at
    the right version would pass on the installed copy's record.  The answer
    is "editable" (somebody's checkout), "shadowed" (another copy imports),
    "untracked" (no VCS record: a local path, a wheel, one day PyPI),
    "revision" (installed from another ref), or None.
    """
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return "untracked"
    info = json.loads(dist.read_text("direct_url.json") or "{}")
    if info.get("dir_info", {}).get("editable"):
        return "editable"
    root = os.path.normcase(os.path.realpath(str(dist.locate_file(""))))
    here = os.path.normcase(os.path.realpath(__import__(name).__file__))
    try:
        if os.path.commonpath([root, here]) != root:
            return "shadowed"
    except ValueError:                  # another drive
        return "shadowed"
    vcs = info.get("vcs_info")
    if not vcs:
        return "untracked"
    if vcs.get("requested_revision") != tag:
        return "revision"
    return None


def install(required):
    """pip-install whichever of `required` (import names) will not import.

    Each module passes its own `_REQUIRED_PKGS`, which verify_docs check 7
    holds to requirements.txt.  A package in PIP_SPEC is also held to its tag,
    but only for a module that lists it.
    """
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(PIP_SPEC.get(pkg, pkg))

    # A PINNED package that imports at the WRONG TAG is as broken as a missing
    # one, and fails later and less legibly: an interpreter holding spacecost
    # 0.1.1 dies inside Stage 2 with "module 'spacecost' has no attribute
    # 'LEO_LAUNCH_USD_PER_KG'", which names neither the package nor the pin.
    # So a git-pinned package is held to its tag here: the version off the
    # module that IMPORTS, and the revision off pip's record of the install
    # (`_pinned_pkg_origin`), since `__version__` moves only on a release and a
    # checkout two commits past the tag reports the tag's version.  An install
    # from another tag or revision is replaced IN PLACE with --no-deps, because
    # a plain reinstall once dragged numpy and pandas off the measured host
    # (CLAUDE.md, "--no-deps when repinning spacecost").  Anything pip did not
    # install from a git ref -- an editable checkout, a shadowing copy, a local
    # path -- is refused rather than overwritten, at any version: test an
    # unreleased spacecost by tagging it.  The probe above has already imported
    # the stale copy, so it is evicted from sys.modules before anything below
    # imports it for real.
    for pkg, spec in PIP_SPEC.items():
        if pkg not in required or spec in missing:
            continue
        tag = spec.rsplit("@", 1)[-1]
        want = tag.lstrip("v")
        have = _pinned_pkg_version(pkg)
        why = _pinned_pkg_origin(pkg, tag)
        if have == want and why is None:
            continue
        fix = [sys.executable, "-m", "pip", "install", "--force-reinstall",
               "--no-deps", spec]
        if why == "editable":
            raise RuntimeError(
                f"{pkg} {have} is an editable install, and this file pins "
                f"{tag}.  Replace it with:  " + " ".join(fix))
        if why == "shadowed":
            raise RuntimeError(
                f"{pkg} imports from {__import__(pkg).__file__}, not from the "
                f"copy pip installed, and this file pins {tag}.  Take that "
                f"copy off sys.path.")
        if why == "untracked":
            raise RuntimeError(
                f"{pkg} {have} carries no record of being installed from a git "
                f"ref, and this file pins {tag}.  Replace it with:  "
                + " ".join(fix))
        print(f"PKG  {pkg} {have} is installed and this file pins {tag}; "
              f"reinstalling with --no-deps ...")
        try:
            subprocess.check_call(fix[:4] + ["-q"] + fix[4:])
        except (OSError, subprocess.CalledProcessError) as err:
            raise RuntimeError(
                f"{pkg} {have} is installed, this file pins {want}, and the "
                f"reinstall failed.  Run:  " + " ".join(fix)) from err
        for name in [n for n in sys.modules
                     if n == pkg or n.startswith(pkg + ".")]:
            del sys.modules[name]
        importlib.invalidate_caches()
        have = _pinned_pkg_version(pkg)
        if have != want or _pinned_pkg_origin(pkg, tag) is not None:
            raise RuntimeError(
                f"{pkg} still imports as {have} after reinstalling {tag}; "
                f"another copy shadows it on sys.path.")
        print(f"OK  {pkg} {want} installed")

    if missing:
        print(f"PKG  Installing: {missing} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q"] + missing
        )
        print("OK  Install complete")
    else:
        print("OK  All packages present")


# -----------------------------------------------------------------------------
# OVERWRITE GUARD
# -----------------------------------------------------------------------------
# A FETCHING stage writes over the only copy of its inputs, and there is no
# undo: every `.verify` baseline and every committed measurement was taken
# against the files this run is about to replace.  `run_pipeline.py` has
# asked before doing that since 2026-08-23; running a stage module directly
# went nowhere near that guard, which is the hole somebody fell into on
# 2026-09-17 while smoke-testing an import, re-fetching three live propellant
# prices over the campaign's frozen tables.  Stages 1-3 each call this from
# their `__main__` block before building; verify_docs check 15 holds that.

def confirm_overwrite(paths, what):
    """True when it is safe to overwrite `paths`; ask the user if it is not.

    Refuses on EOF rather than hanging, because stdin here may be a
    scheduled task's dead handle -- the `set /p` trap in `run.bat`, which
    waits forever instead of failing.  `--yes` skips the question, which is
    what a scripted caller passes.
    """
    existing = [p for p in paths if os.path.exists(p)]
    if not existing or "--yes" in sys.argv:
        return True
    print("")
    print("  " + "=" * 71)
    print("  THIS RE-FETCHES LIVE DATA AND OVERWRITES WHAT IS ON DISK")
    print("  " + "=" * 71)
    print("  %s" % what)
    for p in existing[:8]:
        print("    %s" % p)
    if len(existing) > 8:
        print("    ... and %d more" % (len(existing) - 8))
    print("")
    print("  The values on disk are the only copy.  Any verify.py baseline")
    print("  or archived measurement taken against them stops reproducing,")
    print("  and that looks exactly like a code regression.")
    print("")
    try:
        return input("  Type 'yes' to overwrite: ").strip().lower() == "yes"
    except (EOFError, KeyboardInterrupt):
        print("")
        print("  No console to confirm on (stdin is not a terminal).")
        print("  Pass --yes if overwriting them is what you meant.")
        return False
