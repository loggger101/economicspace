# -*- coding: utf-8 -*-
"""Start the campaign queue with NO CONSOLE, then exit immediately.

    python.exe campaign/_supervisor.py [run_queue.py | memwatch.py]

The scheduled tasks run this file, directly, with no `.bat` and no `cmd /c`:
the wrapper is a console owner, and a console is how the 2026-09-09 and
2026-09-11 kills arrived.  The supervisor itself is quietqueue's `supervise`
(see quietqueue_pin.py for the pin), which documents and tests the traps:
DETACHED_PROCESS, exiting at once, and a single-instance guard that looks at
processes rather than at the scheduler, so the AtLogOn trigger can fire on
every logon.  What stays here is this campaign's: the target under
`campaign/`, the queue log, the repo root to run in, and this file's own name,
which the guard must skip because its command line names the target.

Exits 0 whether it started the target or found it running; exits 1, with the
reason in the queue log, when the installed quietqueue is not the pinned one.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMP = os.path.join(ROOT, "campaign")
LOG = os.path.join(CAMP, "logs", "_queue.log")
DEFAULT_TARGET = "run_queue.py"
# What every invocation of this supervisor has on its command line.
SELF_NAME = "_supervisor"


def main(argv=None):
    """Supervise `campaign/<argv[0]>`, `run_queue.py` when none is given."""
    from quietqueue_pin import require
    qq = require(log=LOG)
    args = sys.argv[1:] if argv is None else list(argv)
    qq.supervise(os.path.join(CAMP, args[0] if args else DEFAULT_TARGET), LOG,
                 cwd=ROOT, self_names=(SELF_NAME,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
