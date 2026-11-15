# -*- coding: utf-8 -*-
"""Read `sample_profile.py` stacks and say where Stage 4's search time goes.

    python rust/es_core/analyse_profile.py STACKS.txt [STACKS2.txt ...]

Only samples taken inside `evaluate_asteroid` count (loading CSVs and writing
the catalog are not the search).  Four views:

  sections   inside `_evaluate_combo_at_ratio`, by the `# ── ... ──` section
             headers of calc.py itself (read from the source, never typed
             here), attributed at the INNERMOST `_evaluate_combo_at_ratio`
             frame, so a recursive repair's time lands on its own section
  callers    what `evaluate_asteroid` spends outside that function
  inclusive  every function on the stack, counted once per sample
  self       the leaf frame (where Rust time shows as its calling line)

Percentages are of search samples.  A sample is ~1 ms; read anything under
~1% as noise.
"""
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CALC = os.path.join(os.path.dirname(os.path.dirname(HERE)), "modules", "calc.py")
EVAL = "_evaluate_combo_at_ratio"

src = open(CALC, encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(src, 1) if l.startswith("def %s(" % EVAL))
end = next(i for i, l in enumerate(src, 1) if i > start and l.startswith("def "))
headers = [(start, "(signature and set-up)")]
for i in range(start, end):
    l = src[i - 1]
    m = re.match(r"\s{4}# ── (.+?) ─", l)
    if m:
        headers.append((i, m.group(1).strip()))
    if l.startswith("    while passes < pass_limit:"):
        headers.append((i, "PYTHON SIZING LOOP (only when Rust hands back)"))
    if l.startswith("    if cascade is None or not cascade[\"viable\"]:"):
        headers.append((i, "(after the sizing loop)"))
    if l.startswith("    def _price_programme("):
        headers.append((i, "def _price_programme (nested; body is its own frame)"))
    if re.match(r"    (for|while) .*(programmes|fleet)", l):
        headers.append((i, "programme / fleet ladder: " + l.strip()[:60]))
headers.sort()


def section(line):
    name = headers[0][1]
    for ln, h in headers:
        if line >= ln:
            name = h
    return "%5d %s" % (next(ln for ln, h in headers if h == name), name)


def report(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    head = lines[0] if lines and lines[0].startswith("#") else ""
    stacks = [l.split(";") for l in lines if l and not l.startswith("#")]
    search = [s for s in stacks if any(":evaluate_asteroid:" in f for f in s)]
    n = len(search)
    print("=" * 78)
    print(os.path.basename(path), head)
    print("samples %d, inside evaluate_asteroid %d (%.1f%%)"
          % (len(stacks), n, 100 * n / max(1, len(stacks))))
    if not n:
        return
    sec = collections.Counter()
    callers = collections.Counter()
    incl = collections.Counter()
    leaf = collections.Counter()
    for s in search:
        evals = [i for i, f in enumerate(s) if f.split(":")[1] == EVAL]
        if evals:
            fr = s[evals[-1]]
            sec[section(int(fr.split(":")[2]))] += 1
        ea = max(i for i, f in enumerate(s) if ":evaluate_asteroid:" in f)
        below = s[ea + 1:]
        # the first frame under evaluate_asteroid that is not the hop through
        # evaluate_combo's lambda, so "who called into the expensive part"
        path = []
        for f in below[:3]:
            path.append(f.split(":")[1])
            if f.split(":")[1] == EVAL:
                break
        callers[" > ".join(path) if path else "(evaluate_asteroid itself)"] += 1
        for f in set(":".join(x.split(":")[:2]) for x in s):
            incl[f] += 1
        lf = s[-1].split(":")
        leaf["%s:%s" % (lf[0], lf[1])] += 1

    def show(title, c, k):
        print("-- %s" % title)
        for name, v in c.most_common(k):
            print("  %5.1f%%  %s" % (100 * v / n, name))

    show("sections of %s (innermost frame)" % EVAL, sec, 30)
    show("call paths under evaluate_asteroid", callers, 12)
    show("inclusive", incl, 30)
    show("self (leaf)", leaf, 20)


for p in sys.argv[1:]:
    report(p)
