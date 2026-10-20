# -*- coding: utf-8 -*-
"""Start the dashboard with no terminal window, and give it something to close.

    pyw -3 launch_ui.py          (what `_START HERE.vbs` runs)
    py  -3 launch_ui.py          (same thing, with a console to watch)

THE LAUNCHER IS quietlaunch (github.com/loggger101/quietlaunch), split out of
this file with its history on 2026-10-20. It puts up the control window that
replaces the console, picks a port, reuses the dashboard it started earlier,
installs Streamlit on first use, and stops the server and its children when the
window closes. The Windows traps that shaped it are documented and tested
there. What stays here is what is this project's: which app, what the window
says, and making sure the PINNED quietlaunch is the one that runs.

The pin is the `quietlaunch @ ...@vX.Y.Z` line in requirements-ui.txt, read
rather than retyped. A missing or stale install is fixed in place with
`pip install --force-reinstall --no-deps`, on the same rules
modules/transportation.py applies to spacecost: the version is read off the
module that IMPORTS, and an editable install is somebody's checkout, refused
rather than overwritten.

NOT A SECOND ENTRY POINT TO THE MODEL. Neither this nor quietlaunch imports
master, ui, or anything under modules/: quietlaunch spawns `streamlit run ui.py`
as a child and watches a socket. That is deliberate: this process is the one
thing that must not fail, and importing the pipeline here would put a 1 MB
module and a multiprocessing pool inside the supervisor. It also sidesteps
`_spawn_environment` entirely, since nothing here is ever a worker's
`__main__`. Standard library only until quietlaunch is in hand, for the same
reason.

ASCII ONLY, like the rest of the pipeline's output.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS = os.path.join(HERE, "requirements-ui.txt")
LOG_DIR = os.path.join(HERE, ".launcher")
TITLE = "Asteroid Pipeline"

# CREATE_NO_WINDOW, so the pip child cannot open the console this file exists
# to remove.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _message_box(text):
    """The only way to report a failure before any window exists."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, text, TITLE, 0x10)
            return
        except Exception:
            pass
    try:
        sys.stderr.write(TITLE + "\n\n" + text + "\n")
    except Exception:
        pass


def _console_python():
    """The console interpreter beside a `pythonw`, for the pip child.

    quietlaunch has the same function; this copy exists because it runs BEFORE
    quietlaunch can be imported. Under `pyw`, sys.executable is pythonw.exe,
    whose stdout is None, so pip run through it has nowhere to write.
    """
    exe = sys.executable or ""
    if os.path.basename(exe).lower().startswith("pythonw"):
        cand = os.path.join(os.path.dirname(exe),
                            os.path.basename(exe).replace("pythonw", "python", 1))
        if os.path.isfile(cand):
            return cand
    return exe


def _pin():
    """(pip spec, version) from requirements-ui.txt's quietlaunch line, or None."""
    try:
        with open(REQUIREMENTS, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*quietlaunch\s*@\s*(\S+@v(\d+\.\d+\.\d+))\s*$",
                             line)
                if m:
                    return "quietlaunch @ " + m.group(1), m.group(2)
    except OSError:
        pass
    return None


def _imported_version():
    """quietlaunch's version as it IMPORTS, or None when it does not."""
    try:
        import quietlaunch
    except ImportError:
        return None
    return getattr(quietlaunch, "__version__", None)


def _editable():
    """True when pip installed quietlaunch editable, i.e. it is a checkout."""
    try:
        import importlib.metadata as md
        text = md.distribution("quietlaunch").read_text("direct_url.json")
    except Exception:
        return False
    return bool(json.loads(text or "{}").get("dir_info", {}).get("editable"))


def _tail(path, lines=10):
    """Last lines of a log, for a message box that is the only report."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "\n".join(f.read().splitlines()[-lines:]).strip()
    except OSError:
        return ""


def _ensure_quietlaunch():
    """Make the pinned quietlaunch the one that imports. True when it is.

    `--no-deps` because quietlaunch has none, and because a plain reinstall of a
    git pin is how numpy and pandas once moved off the measured host. Streamlit
    is NOT installed here: quietlaunch installs it from requirements-ui.txt,
    behind its window, where the minute it takes is visible.
    """
    pin = _pin()
    if pin is None:
        _message_box("requirements-ui.txt has no `quietlaunch @ ...@vX.Y.Z` "
                     "line, so there is no pinned launcher to run.\n\n"
                     "Looked in: %s" % REQUIREMENTS)
        return False
    spec, want = pin
    have = _imported_version()
    if have == want:
        return True
    cmd = [_console_python(), "-m", "pip", "install", "--force-reinstall",
           "--no-deps", spec]
    if have is not None and _editable():
        _message_box("quietlaunch %s is an editable install, and "
                     "requirements-ui.txt pins %s.\n\nCheck out v%s there, or "
                     "replace it with:\n%s" % (have, want, want, " ".join(cmd)))
        return False
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "install.log")
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        rc = subprocess.run(cmd, cwd=HERE, stdout=log,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            creationflags=_NO_WINDOW).returncode
    if rc != 0:
        _message_box("Could not install quietlaunch %s.\n\n%s"
                     % (want, _tail(log_path) or "See " + log_path))
        return False
    for name in [n for n in sys.modules
                 if n == "quietlaunch" or n.startswith("quietlaunch.")]:
        del sys.modules[name]
    importlib.invalidate_caches()
    have = _imported_version()
    if have != want:
        _message_box("quietlaunch still imports as %s after installing %s; "
                     "another copy shadows it on sys.path." % (have, want))
        return False
    return True


def main():
    """Install the pinned launcher if needed, then hand the dashboard to it."""
    if not _ensure_quietlaunch():
        return 1
    import quietlaunch
    return quietlaunch.launch(quietlaunch.LaunchConfig(
        app=os.path.join(HERE, "ui.py"),
        title=TITLE,
        heading="Asteroid mining profitability pipeline",
        subtitle="Dashboard",
        # Cold start imports master.py, which is ~1 MB and pulls pandas, numpy
        # and yfinance behind it; on a synced-folder working copy that read is
        # slow and serialises.
        boot_hint="First run loads the pipeline, which takes a minute.",
        boot_timeout_s=300.0,
        requirements=REQUIREMENTS,
    ))


if __name__ == "__main__":
    sys.exit(main())
