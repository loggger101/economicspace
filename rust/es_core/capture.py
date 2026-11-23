"""Record every max_return_payload_kg call (args, kwargs, result) in a sample run.

usage: python rust/es_core/capture.py <repo> <out_dir> <rows> <pickle.pkl> [run_pipeline flags]

out_dir must already hold Stage 1-3 outputs; never the repo's asteroid_pipeline/.
"""
import collections
import pickle
import sys

repo, out_dir, rows, dump = sys.argv[1:5]
sys.path.insert(0, repo)
import os
os.chdir(repo)
# the PYTHON solver's calls are what verify_rust replays against es_core
os.environ["ECONOMICSPACE_RUST"] = "0"

import modules.calc as calc

_orig = calc.max_return_payload_kg
records = []
types = collections.Counter()


def recording(*args, **kwargs):
    res = _orig(*args, **kwargs)
    records.append((args, kwargs, dict(res)))
    types[tuple(type(a).__name__ for a in args)
          + tuple(sorted((k, type(v).__name__) for k, v in kwargs.items()))] += 1
    return res


calc.max_return_payload_kg = recording

import run_pipeline

extra = sys.argv[5:] or ["--destination", "cislunar", "--raw", "--no-search"]
sys.argv = ["run_pipeline.py", "--stages", "4", "--rows", rows,
            "--workers", "1", "--output", out_dir] + extra
try:
    run_pipeline.main()
except SystemExit:
    pass

with open(dump, "wb") as fh:
    pickle.dump(records, fh, protocol=5)
print("CAPTURED", len(records))
for sig, n in types.most_common():
    print(n, sig)
