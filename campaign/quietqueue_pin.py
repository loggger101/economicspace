# -*- coding: utf-8 -*-
"""The quietqueue the campaign runs on, held to the pin.

    python campaign/quietqueue_pin.py                  # say what is installed
    python campaign/quietqueue_pin.py --pause-script   # print pause.ps1's path

THE RUNNER IS quietqueue (github.com/loggger101/quietqueue), split out of
`run_queue.py`, `_supervisor.py`, `memwatch.py` and `_pause.ps1` with their
history on 2026-10-20. Those four files are shims now: each holds this
campaign's constants and hands them to quietqueue, after `require()`.

The pin is the one `quietqueue @ ...@vX.Y.Z` line in requirements-campaign.txt,
read rather than retyped. The version is read off the module that IMPORTS, as
launch_ui.py does for quietlaunch, and a mismatch is refused with the pip
command that fixes it.

UNLIKE launch_ui.py, THIS NEVER INSTALLS. The queue is usually started by a
scheduled task, detached, with nobody watching: a pip run there would change
the interpreter under a campaign measured in days, and fail where only a log
would see it. So it names the command and exits, and the supervisor writes the
refusal into the queue log, which is where a detached start's output goes.

ASCII only, like the rest of the pipeline's output.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = os.path.join(ROOT, "requirements-campaign.txt")

# A PEP 508 direct reference to a tag: `quietqueue @ git+https://...@v0.1.0`.
_PIN = re.compile(r"^\s*(quietqueue\s*@\s*git\+\S+@v(\d+\.\d+\.\d+))\s*$", re.M)


def pin():
    """(pip spec, version) from requirements-campaign.txt's quietqueue line, or None."""
    try:
        with open(REQUIREMENTS, encoding="utf-8") as fh:
            m = _PIN.search(fh.read())
    except OSError:
        return None
    return (m.group(1), m.group(2)) if m else None


def problem():
    """Why the installed quietqueue cannot run the campaign, or None if it can."""
    p = pin()
    if p is None:
        return ("requirements-campaign.txt has no `quietqueue @ ...@vX.Y.Z` "
                "line, so the pinned runner cannot be named.")
    spec, want = p
    fix = f'  {sys.executable} -m pip install --force-reinstall --no-deps "{spec}"'
    try:
        import quietqueue
    except ImportError:
        return f"quietqueue is not installed in {sys.executable}.\n{fix}"
    got = getattr(quietqueue, "__version__", None)
    if got != want:
        return (f"quietqueue {got} is installed ({os.path.dirname(quietqueue.__file__)});"
                f" requirements-campaign.txt pins {want}.\n{fix}")
    return None


def require(log=None):
    """The pinned quietqueue module; otherwise exit 1, saying why on stderr.

    `log`, when given, gets the same text appended: a detached start has no
    stderr anyone reads.
    """
    why = problem()
    if why is None:
        import quietqueue
        return quietqueue
    if log:
        try:
            with open(log, "a", encoding="utf-8", errors="replace") as fh:
                fh.write(f"      quietqueue_pin: {why}\n")
        except OSError:
            pass
    sys.exit(why)


def main(argv=None):
    """Report the installed quietqueue against the pin, or print pause.ps1's path."""
    args = sys.argv[1:] if argv is None else list(argv)
    qq = require()
    if "--pause-script" in args:
        print(qq.pause_script())
    else:
        print(f"quietqueue {qq.__version__} at {os.path.dirname(qq.__file__)}, as pinned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
