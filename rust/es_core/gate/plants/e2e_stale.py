"""Plant for e2e_rust.run: Stage 4 exits 0 but writes nothing, with a stale
catalog already on disk.  run() must refuse (SystemExit), not hash the stale
file.  Exit 0 when caught."""
import os
import subprocess
import sys
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
import e2e_rust  # noqa: E402

d = tempfile.mkdtemp()
with open(os.path.join(d, "profitability_catalog.csv"), "w") as fh:
    fh.write("stale,from,an,earlier,run\n")
e2e_rust.subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "")
try:
    e2e_rust.run(d, "5", "1", [], True)
    print("MISSED: stale file hashed")
    sys.exit(1)
except SystemExit as e:
    print("CAUGHT:", e)
    sys.exit(0)
