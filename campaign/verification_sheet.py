# -*- coding: utf-8 -*-
"""A pen-and-paper verification worksheet for one worked calculation.

WHAT IT IS FOR, and how it differs from the document beside it.
`worked_calculation.py` derives one mission and `worked_calculation_doc.py`
explains it: the prose says what each term means and why the model charges
for it.  This renders the same derivation as a WORKSHEET instead, for a
reader who wants to reproduce the answer on paper rather than read about it.
Three things change:

  1. every input is TAGGED and CITED, so a disagreement can be traced to a
     file, a row and a column rather than to "the reference tables";
  2. every step names the tags it consumes, so the dependency order is on the
     page and a reader can start anywhere and work outwards;
  3. nothing is elided.  The narrative document states a few intermediate
     sums without substituting them, because a sentence reads badly with nine
     terms in it; a worksheet has the opposite obligation.

A last part then asks every tag what stands BEHIND it, which is a different
question from where it was read: a published source quoted out of its
citation, or "(needs backing)" where the honest answer is nothing.  See
`part_backing`.

NOTHING HERE IS TYPED, for the reason the whole document exists.  This module
decides what to SAY; `worked_calculation.build` has already done the
arithmetic, and every figure below is read out of its dicts.  A worksheet
with a hand-copied number in it would be the defect this repo catalogues
first, committed in the one file whose entire purpose is to let somebody
check numbers.

THE CITATIONS ARE DERIVED TOO, which is the part worth knowing before
trusting them.  CITATIONS.md says where sources live rather than repeating
them: the `notes` and `reference_year` fields of each `spacecost` row, the
price-source columns of the Module 2 catalog, the provenance columns of the
Stage 1 catalog, and the config comment that `ui_meta` already scrapes for
the dashboard's help text.  This reads those, so a citation cannot go stale
against the row it describes.

TAGS ARE ASSIGNED, NOT TYPED, for the same reason section numbers are in the
renderer next door: a worksheet whose cross-references are hand-numbered is
one insertion away from pointing at the wrong line, silently.  A caller names
a step with a short KEY and cites other steps by key; the display tag is the
position, and `Worksheet.step` refuses a key it has not seen registered.

    py campaign/verification_sheet.py                     # the best case on disk
    py campaign/verification_sheet.py --pdf               # and print it
    py campaign/verification_sheet.py --catalog X.csv.gz  # a named source
    py campaign/verification_sheet.py --cell NAME         # an archived cell
"""
import argparse
import datetime
import math
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import worked_calculation as W
import worked_calculation_doc as D

# The full-precision formatter.  The narrative document's own docstring says
# why it exists and it is exactly the rule a worksheet lives by: a reader who
# retypes rounded intermediates does not get the printed result back.
P = D.prec


def exact(value):
    """The shortest decimal that reads back as the SAME double.

    For a subtraction that cancels there is no precision of rounded
    decimal that will do.  The cross-check residuals subtract two numbers
    equal to twelve digits, so seventeen significant figures still left
    the printed operands giving a different answer from the model's, in
    the fourth digit of the residual.  Python's repr is the shortest
    string that round-trips, so a reader retyping it gets the model's own
    float and therefore the model's own difference.
    """
    return repr(float(value))


# THE PARTS, IN THE ORDER THE MODEL EVALUATES THEM.  A part's number is its
# POSITION here and nothing else: the titles used to carry a typed number
# each and the prose a typed "see part 5", and the caps that sentence pointed
# at were in part 8.  One section's identity written down twice is the defect
# CLAUDE.md records for the narrative document next door; a cross-reference is
# `ref(key)` now, so inserting a part renumbers every mention of every part.
PART_KEYS = ("constants", "dials", "body", "prices", "transfer", "ratios",
             "plant", "fixed_point", "settled", "stack", "clock", "hold",
             "market", "searches", "reliability", "cost", "answer", "checks",
             "backing")


def part_no(key):
    """The number part `key` is printed under: its position in PART_KEYS."""
    return PART_KEYS.index(key)


def ref(key, word="part"):
    """A cross-reference to part `key`, as a link, marked as a label.

    A part number is a label, like a row number, so it is wrapped where the
    traceability check skips it: read as a number it would have to be traced
    to something the page derived, and only coincidence would trace it.
    """
    n = part_no(key)
    return '<span class="ord"><a href="#p%d">%s %d</a></span>' % (n, word, n)


def refs(first, last, joiner="to"):
    """A cross-reference to two parts: "parts 6 to 15", "parts 6 and 7"."""
    a, b = part_no(first), part_no(last)
    return ('<span class="ord"><a href="#p%d">parts %d</a> %s '
            '<a href="#p%d">%d</a></span>' % (a, a, joiner, b, b))


def ordinal(n):
    """A table row's position, marked so the traceability check skips it.

    A row number is a label.  Read as a number it has to be traced to
    something the page derived, and it is traced only by coincidence, while
    some step happens to produce the same small integer.
    """
    return '<span class="ord">%d</span>' % n


# ------------------------------------------------------------------ the sheet
class Worksheet(object):
    """The ordered register of inputs and steps a reader checks by hand.

    An INPUT is a number that comes from outside this derivation and carries
    a citation.  A STEP is a number the page produces, and it names the keys
    it was produced from.  Holding both in one object is what lets the render
    assert that every key a step cites is registered, and report every input
    no step spent, which are the two ways a worksheet quietly stops covering
    itself.
    """

    def __init__(self):
        """An empty sheet: no parts, no keys, nothing cited."""
        self.parts = []
        self.tag = {}
        self.value = {}
        self.used = set()
        self.claims = []
        self.n_input = 0
        self.n_step = 0
        # {quotation: pointer} the dial ledger has already printed; see
        # `said_once`.
        self.said = {}

    def part(self, key, title, blurb=""):
        """Open part `key`, numbered by its position in PART_KEYS."""
        n = part_no(key)
        self.parts.append({"key": key, "n": n,
                           "title": "%d. %s" % (n, title), "blurb": blurb,
                           "rows": []})

    def prose(self, text):
        """A line of explanation between steps, spanning the table."""
        self.parts[-1]["rows"].append(("prose", text))

    def block(self, html, rerun=""):
        """Raw HTML between steps: a table the step form cannot carry.

        `rerun` marks a table whose every row is THIS WHOLE DOCUMENT
        evaluated at a different setting -- the fixed point's earlier
        passes, the concentration ladder, the programme ladder.  Those
        numbers have a source and it is not a one-line substitution: it is
        parts 6 to 15 run again at that row's setting, which is a true
        answer and the only true one.  Saying so on the page, and marking
        it so the traceability check can count what it excused and why, is
        honest where inventing a substitution for them would not be.
        """
        if rerun:
            html = ('<div class="rerun"><p class="prose">' + rerun
                    + '</p>' + html + '<!--rerun-end--></div>')
        self.parts[-1]["rows"].append(("block", html))

    def _claim(self, key, kind):
        """Assign the display tag for `key`, refusing a key used twice."""
        if key in self.tag:
            raise AssertionError("key %r is registered twice" % key)
        if kind == "I":
            self.n_input += 1
            self.tag[key] = "I%d" % self.n_input
        else:
            self.n_step += 1
            self.tag[key] = "S%d" % self.n_step
        return self.tag[key]

    def cited(self, keys):
        """Display tags for `keys`, refusing any that is not registered.

        This is the assertion the whole tagging scheme is for: a step that
        cites a key nothing registered is a step whose inputs a reader cannot
        find, and it fails the render rather than printing a dead reference.
        """
        out = []
        for key in keys:
            if key not in self.tag:
                raise AssertionError("a step cites %r, which is not "
                                     "registered" % key)
            self.used.add(key)
            out.append(self.tag[key])
        return out

    def put(self, key, symbol, quantity, value, unit, source):
        """Register one INPUT and return its value, so a step can spend it.

        Returning the value is what stops a step spending a number that was
        never registered: the only way to get it onto the page is to cite it.
        """
        tag = self._claim(key, "I")
        self.value[key] = value
        self.parts[-1]["rows"].append(
            ("input", tag, symbol, quantity, value, unit, source))
        return value

    def step(self, key, symbol, quantity, formula, substitution, value,
             unit, uses, note=""):
        """Register one STEP: a number this page makes out of other keys."""
        tags = self.cited(uses)
        tag = self._claim(key, "S")
        self.value[key] = value
        self.parts[-1]["rows"].append(
            ("step", tag, symbol, quantity, formula, substitution, value,
             unit, tags, note))
        return value

    def claim(self, work, value, what="", uses=()):
        """Register a checkable arithmetic claim a BLOCK TABLE makes.

        A table row is a step that happens to be laid out in columns, and
        until this existed it was the one place the page produced a number
        without showing where it came from: the knapsack's supply, the
        alloy's per-element contribution, each rung's objective.  The
        working goes in a column of the table so the reader sees it, and
        the same (work, value) pair is registered here so the arithmetic
        check and the traceability check treat it exactly as they treat a
        step.  Returns the working, so a caller can put it straight in a
        cell.

        `uses` names the registered keys the working consumes, exactly as a
        step's does.  Without it an input spent only inside a table read as
        never spent: the market ceilings are each worked into an allowance
        in a table row, and all of them were reported in the footer as a
        missing step or a citation nobody needs.
        """
        self.cited(uses)
        self.claims.append((work, value, what))
        return D.esc(work)

    def unspent(self):
        """(inputs nothing cited, steps nothing cited), which differ in kind.

        An INPUT no step consumes is a finding, on the same argument this
        repo makes about an allowlist row that matches nothing: it is either
        a missing step or a citation nobody needs.  A STEP nothing consumes
        is usually a RESULT or a diagnostic, which is what the last line of
        a worksheet is for, so the two are reported apart rather than
        together.  Reporting them as one list buried the finding among the
        expected cases, which is the defect this docstring replaced.
        """
        loose = [k for k in self.tag if k not in self.used]
        return ([k for k in loose if self.tag[k].startswith("I")],
                [k for k in loose if self.tag[k].startswith("S")])


# ------------------------------------------------------------- provenance
# THE CITATIONS ARE READ, NOT LISTED.  CITATIONS.md's own section 7 says this
# repo does not duplicate sources, it says where they are: the `notes` field
# of each spacecost row, the price-source columns of the Module 2 catalog,
# and the provenance columns Stage 1 writes.  A hand-maintained list of
# citations here would be a second copy of all of it, and would go stale the
# first time a row was re-anchored.
def trim(text, limit=None):
    """One field of free text, HTML-safe, whitespace collapsed, ENTIRE.

    🚨  IT USED TO TRUNCATE AT 320 CHARACTERS AND THAT CUT THIRTY CITATIONS,
    which is the one thing a worksheet must not do: a reference note is where
    the numbers behind a number live -- "Reference $150k/kg = ~$4,700/oz;
    gold ran from $3,335 (May 2025) to $4,732 (May 2026)" is the whole
    provenance of the gold price, and it was ending in an ellipsis.  A
    citation that stops mid-sentence is not a shorter citation, it is a
    missing one, and the reader has no way to tell which.

    `limit` is kept so the call sites read the same and is deliberately
    ignored; the text wraps instead.  Wrapping costs vertical space, which
    the page has, where truncation costs information, which it does not.
    """
    text = " ".join(str(text).split())
    if text in ("", "nan", "None"):
        return ""
    # A comment's ⚠️ asks for the COLOUR glyph by name (VARIATION SELECTOR-16),
    # which prints yellow whatever the stylesheet says; selector 15 asks for
    # the same character in text, which prints in the ink around it.  A code
    # span written `like_this` is set as code rather than printing its marks.
    text = D.esc(text.replace(_VS_EMOJI, _VS_TEXT))
    return _BACKTICKS.sub(r"<code>\1</code>", text)


_VS_EMOJI, _VS_TEXT = "\ufe0f", "\ufe0e"
_BACKTICKS = re.compile(r"`([^`<>]+)`")


def join_clauses(bits):
    """Join citation fragments as sentences, without doubling a full stop.

    Each fragment is a clause the joiner ends; a quoted note already ends
    its own, and "... on departure.. reference year 2026" printed under
    every operational-costs row whose notes close with a stop.
    """
    out = bits[0] if bits else ""
    for bit in bits[1:]:
        ended = _TAGS.sub("", out).rstrip().endswith((".", "!", "?"))
        out += ("  " if ended else ".  ") + bit
    return out


def cited(html):
    """Mark a citation so the traceability check knows it is QUOTED text.

    A number inside a citation is the source, not a claim: "$1,400/oz" in
    the platinum note is what the exchange said, and asking the page to
    derive it would be asking it to derive the outside world.  The check
    strips these and audits what is left, which is the set of numbers the
    page itself asserts.
    """
    return '<span class="cite">%s</span>' % html


def stamp(row):
    """`catalog_date` and `pipeline_version` off any reference row."""
    get = getattr(row, "get", lambda _f: None)
    return ", ".join("%s %s" % (label, D.esc(get(field)))
                     for field, label in (("catalog_date", "built"),
                                          ("pipeline_version", "stage v"))
                     if present(get(field)))


def priced(C, element):
    """Whether Stage 2 gives `element` a finite price.  An element with none
    is worth nothing to the model (`_mineral_implied_value` skips it), so the
    page leaves it out of every yield sum the same way."""
    price = C["element_price"].get(element)
    return price is not None and math.isfinite(float(price))


def present(value):
    """A cell that holds something: not None and not a float NaN."""
    return not (value is None or (isinstance(value, float)
                                  and pd.isna(value)))


def cite_ops(C, category):
    """Cite one row of Module 3's operational-costs table.

    The `notes` field IS the citation: every row in that table carries the
    anchor its figure came from, which is what CITATIONS.md points at.  The
    `range_low` and `range_high` columns are carried too, because a cost
    model reader wants to know whether a figure is a measurement or the
    middle of a plausible band.
    """
    ops = C["ops"]
    hit = ops[ops["category"] == category]
    if not len(hit):
        # A citation to a row the table does not have is a page about a
        # table nobody can open, so it is a refusal, not a stand-in text.
        raise AssertionError("operational_costs.csv has no row named %r"
                             % category)
    row = hit.iloc[0]
    bits = ["<b>operational_costs.csv</b>, row <i>%s</i>" % D.esc(category)]
    unit = trim(row.get("unit"), 60)
    if unit:
        bits.append("in %s" % unit)
    band = []
    for field in ("range_low", "range_high"):
        value = row.get(field)
        if value is not None and not pd.isna(value):
            band.append(P(value, 6))
    if len(band) == 2:
        bits.append("plausible band %s to %s" % (band[0], band[1]))
    note = trim(row.get("notes"))
    if note:
        bits.append("<span class='src'>%s</span>" % note)
    year = row.get("reference_year")
    if year is not None and not pd.isna(year):
        bits.append("reference year %s" % D.esc(int(year)))
    return join_clauses(bits)


def cite_table_row(row, table, name, fields=()):
    """Cite one row of a Module 3 table by name, with its notes and status."""
    bits = ["<b>%s</b>, row <i>%s</i>" % (D.esc(table), D.esc(name))]
    for field in fields:
        # `raw` ON PURPOSE, AND THIS IS THE ONE PLACE IT IS RIGHT.  Reading
        # `notes` to print a citation is asking what the table says, not
        # spending the figure, and logging it would put a rate on the rate
        # audit's list that no line on the page pays.  `Recorded.raw`'s own
        # docstring is the rule this follows.
        value = getattr(row, "raw", getattr(row, "get", None))(field)
        text = trim(value, 90) if present(value) else ""
        if text:
            bits.append("%s %s" % (field, text))
    note = trim(row.raw("notes") if hasattr(row, "raw") else row.get("notes"))
    if note:
        bits.append("<span class='src'>%s</span>" % note)
    return join_clauses(bits)


def cite_mineral(C, name, label=None):
    """Cite one commodity row of the Module 2 catalog, price source included.

    Two dates matter and they are different questions: `ref_price_date` is
    when the reference quote was taken and `live_price_date` is when the
    fetcher last answered, and a commodity can carry one, both or neither.
    """
    minerals = C["minerals"]
    hit = minerals[minerals["name"] == name]
    if not len(hit):
        raise AssertionError("mineral_value_catalog.csv has no row named %r"
                             % name)
    row = hit.iloc[0]
    bits = ["<b>mineral_value_catalog.csv</b>, row <i>%s</i>"
            % D.esc(label or name)]
    basis = trim(row.get("price_basis"), 60)
    if basis:
        bits.append("basis %s" % basis)
    for field, what in (("ref_price_source", "reference quote"),
                        ("live_price_source", "live quote")):
        source = trim(row.get(field), 90)
        if not source:
            continue
        date = trim(row.get(field.replace("source", "date")), 20)
        bits.append("%s from %s%s"
                    % (what, source, " on %s" % date if date else ""))
    note = trim(row.get("notes"))
    if note:
        bits.append("<span class='src'>%s</span>" % note)
    return join_clauses(bits)


def cite_column(C, name, column, why=""):
    """Cite one column of a Module 2 row that is not its price.

    🚨  A ROW'S NOTES DESCRIBE THE MINERAL, NOT EVERY COLUMN IT CARRIES.
    The refining deduction, the refining energy and the absorption ceiling
    each used to be cited with `cite_mineral`, so kamacite's "most of an iron
    meteorite's metal" stood as the source of a $230/kg refining cost it
    says nothing about, under four inputs per phase -- and a note that did
    name a source would have been credited, in part 18, as backing a column
    it never mentions.  The column is the citation; `why` says how Stage 2
    wrote it.
    """
    if not len(C["minerals"][C["minerals"]["name"] == name]):
        raise AssertionError("mineral_value_catalog.csv has no row named %r"
                             % name)
    where = ("<b>mineral_value_catalog.csv</b>, row <i>%s</i>, column "
             "<i>%s</i>" % (D.esc(name), D.esc(column)))
    return ("%s.  <span class='src'>%s</span>" % (where, why) if why
            else where + ".")


# What `in_space_processing_usd_per_kg` IS, said by naming the function that
# writes it: a sum of two terms, neither of them the mineral's price.
REFINING_NOTE = ("Stage 2's refining deduction: the row's "
                 "<i>refining_kwh_per_kg</i> at the capital cost of energy "
                 "in space, plus an amortised plant "
                 "(<i>in_space_processing_cost_usd_per_kg</i> in "
                 "<b>modules/mineral_value.py</b>).")


def cite_body(C, column, what=""):
    """Cite one column of this body's Stage 1 catalog row.

    Stage 1 writes a provenance column beside most of what it derives, and
    those are the difference between a measurement and an inference: a
    diameter out of a thermal fit and one out of an assumed albedo are the
    same column and not the same claim.

    THE LABELS ARE IN THE BODY'S STAMP, NOT HERE.  The first version printed
    all five on every body input, so the diameter's provenance, the
    taxonomy's, the assumed albedo, whether the density was measured and the
    composition group appeared seven times over -- about half a page of
    repetition saying nothing new after the first.  A citation says what its
    column is (`what`: "NOT measured: ..."); `body_stamp` says, once, which
    labels Stage 1 gave the row.
    """
    body = C["body"]
    moved = C.get("body_from_row") or {}
    if column in moved:
        # The installed catalog postdates the run, so the value the run read
        # is the one its own row recorded; the installed one is shown beside
        # it, because the difference is what a reader would otherwise trip on.
        old = moved[column]
        return ("<b>profitability_catalog</b> &middot; row <i>%s</i> &middot; "
                "column <i>%s</i>, the value this run read.  "
                "<span class='src'>The catalog build it read is not "
                "installed; the installed one gives %s.</span>"
                % (D.esc(body.get("designation")), D.esc(column),
                   D.esc(old if isinstance(old, str) else P(old, 8))))
    bits = ["<b>asteroid_catalog.csv</b> &middot; row <i>%s</i> &middot; "
            "column <i>%s</i>"
            % (D.esc(body.get("designation")), D.esc(column))]
    if what:
        # A clause the joiner ends with a full stop opens a sentence.
        bits.append(what[:1].upper() + what[1:])
    # The provenance labels themselves are said once, glossed, in the body's
    # stamp at the head of its part (`body_stamp`): the taxonomy fields stood
    # under every phase nine times over, and the diameter's label under the
    # albedo directly below the stamp that had just said it.
    return join_clauses(bits)


# WHAT STAGE 1'S PROVENANCE LABELS MEAN, in AsteroidCatalog's own words
# (`asteroid_catalog/enrich.py` and `derive.py`).  "spectral_type_source
# source" printed as it is reads as a typing slip; it means the class was
# published.  A label not listed here prints bare, and `verify_stage1.py`
# check 8 is what catches a new one.
LABELS = {
    "spectral_type_source": {
        "source": "a published class, from JPL, SsODNet or MP3C",
        "tholen": "the Tholen class",
        "orbit": "D, from an orbit at Trojan distance or beyond",
        "albedo": "inferred from a measured albedo",
        "albedo_assumed": "inferred from the albedo assumed for the "
                          "diameter, the weakest class",
    },
    "diameter_source": {
        "measured": "measured",
        "derived_h_taxonomy_albedo": "from H and its taxonomy class's "
                                     "albedo",
        "derived_h_orbit_albedo": "from H and an albedo assumed from its "
                                  "orbit",
        "derived_h_measured_albedo": "from H and a measured albedo",
        "derived_h_fallback_albedo": "from H and a fallback albedo",
        "derived_mass": "from a measured mass at its class's density",
    },
}


def label_of(field, value):
    """`field` and its value, glossed where Stage 1 says what it means."""
    text = "<i>%s</i> <code>%s</code>" % (D.esc(field), D.esc(value))
    gloss = LABELS.get(field, {}).get(str(value))
    return text + (" (%s)" % D.esc(gloss) if gloss else "")


def body_stamp(C):
    """The row-level provenance every Stage 1 input on this page shares."""
    body = C["body"]
    bits = []
    if present(body.get("spectral_type")):
        bits.append("class %s%s" % (D.esc(body.get("spectral_type")),
                                    " in the %s" % D.esc(body.get("comp_group"))
                                    if present(body.get("comp_group"))
                                    else ""))
    bits += [label_of(field, body.get(field))
             for field in ("spectral_type_source", "diameter_source",
                           "density_measured") if present(body.get(field))]
    where = stamp(body)
    if where:
        bits.append(where)
    return "Stage 1 row: %s." % "; ".join(bits)


_FIELD_DOCS = {}
_FIELD_LINES = {}


def field_docs(module="calc"):
    """{field: {"help", "section"}} for one config, scraped once."""
    if not _FIELD_DOCS:
        import ui_meta
        for key, source in ui_meta.CONFIG_SOURCES.items():
            path, cls = source[0], source[1]
            # No fallback: a ledger whose definitions silently came back
            # empty would list every dial with no meaning beside it.
            _FIELD_DOCS[key] = ui_meta.scrape_field_docs(
                os.path.join(ROOT, path), cls)
            # The line each field is DEFINED on, so a citation can point a
            # reader at the whole comment rather than quoting all of it.
            # No fallback: a citation with no line to point at is a
            # ledger that cannot say where a dial is defined.
            import ast
            with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            node = next(n for n in ast.walk(tree)
                        if isinstance(n, ast.ClassDef) and n.name == cls)
            _FIELD_LINES[key] = (
                os.path.relpath(os.path.join(ROOT, path), ROOT)
                .replace(os.sep, "/"),
                {s.target.id: s.lineno for s in node.body
                 if isinstance(s, ast.AnnAssign)
                 and isinstance(s.target, ast.Name)})
    return _FIELD_DOCS.get(module, {})


def definition(help_text):
    """The first paragraph of a field's comment: what the dial IS.

    🚨  THE REST OF A FIELD'S COMMENT IS ITS HISTORY, AND ON THIS PAGE IT READ
    AS AN ANSWER ABOUT ANOTHER MISSION.  `max_mining_fraction`'s comment goes
    on to say what the dial did "on the cell winner (2017 KJ5)", and the
    citation printed all of it beside 2018 DT, in the column that is supposed
    to say how THIS mission was worked out.  The definition is the paragraph
    a reader needs to redo the arithmetic; the citation names the line the
    whole comment starts on, so nothing is withheld, only not restated.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n", help_text or "")
                  if p.strip()]
    return paragraphs[0] if paragraphs else ""


def field_line(field, module="calc"):
    """`modules/calc.py:251`, the line `field` is defined on, or ''."""
    field_docs(module)
    path, lines = _FIELD_LINES.get(module, ("", {}))
    return "%s:%d" % (path, lines[field]) if field in lines else ""


def cite_config(field, module="calc"):
    """Cite one config dial, with the comment `ui_meta` scrapes as its help.

    ONE DEFINITION WITH TWO READERS.  The dashboard already renders a field's
    comment block as its help text, and a dial's reasoning is exactly the
    citation a worksheet owes for it, so the same scrape answers both rather
    than this file carrying a second description of the same 105 fields.
    Only the definition is quoted; see `definition`.
    """
    doc = field_docs(module).get(field) or {}
    text = trim(definition(doc.get("help") or doc.get("label") or ""))
    line = field_line(field, module)
    if not line:
        raise AssertionError("no definition line found for the %s dial %r"
                             % (module, field))
    where = ("<b>%s</b> config, field <i>%s</i> (<b>%s</b>, where its whole "
             "comment is)" % (D.esc(module), D.esc(field), D.esc(line)))
    if not text:
        # A stock sentence in place of a definition is a placeholder, and
        # verify_docs check 8 already holds every dial to having help.
        raise AssertionError("the %s dial %r has no comment to cite"
                             % (module, field))
    return "%s.  <span class='src'>%s</span>" % (where, text)


def ops_row_read(*candidates):
    """Whichever of `candidates` the derivation actually read, or the first.

    THE ALTERNATIVE WAS A SECOND COPY OF THE MODEL'S CONDITION.  Three ops
    rows are chosen by the delivery architecture -- the lander against the
    capsule against the berthing adapter, the recovery campaign against the
    depot handover, the full licence against the launch-only one -- and
    writing that three-way test again here is exactly the duplication this
    repo catalogues first: the citation would then name the right row only
    for as long as nobody changed the condition.

    `Recorded` already logs every reference read during the derivation, so
    the row the model picked is on the record.  This reads the record.
    """
    read = set(field for table, field, _v in W.RATE_LOG
               if table == "Module 3 operations")
    return next((name for name in candidates if name in read),
                candidates[0])


def cite_here(name, what=""):
    """Cite a constant this derivation fixes in its own source, BY NAME.

    The name is the whole point, and the first version left it in prose: a
    citation reading "campaign/worked_calculation.py" and then a sentence is
    a file a reader can open and a value they then have to hunt for.  The
    origin check refuses that now, which is how these nine were found.
    """
    where = ("<b>campaign/worked_calculation.py</b> &middot; constant "
             "<i>%s</i>" % D.esc(name))
    return "%s.  <span class='src'>%s</span>" % (where, D.esc(what)) if what         else where


def phase_price_keys(S, C, only=None):
    """The registered price keys for the phases, in the table's own order.

    ONE DEFINITION WITH THREE READERS.  The bulk value, the purity bound and
    the hold's value are all sums over the same prices, and three hand-written
    citation lists would be three chances to name a different set.
    """
    keys, seen = [], set()
    for name, _frac, _price in C["phases"]:
        if only is not None and name not in only:
            continue
        base = "silicates" if name.startswith("other") else name
        # The alloy's blend is `P_alloy` on a four-fraction page only; with
        # phases (calc v1.24.0) nickel-iron is one dual-priced phase of several
        # and takes the same `P_<name>` as the rest.
        key = ("P_alloy" if base == "nickel-iron" and not C.get("phased")
               else "P_" + base.replace(" ", "_").replace("-", "_"))
        if key in S.tag and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def rerun_pass():
    """The fixed point's earlier passes: which parts each row re-runs."""
    return ("<b>Each row is %s run again at the hardware in its own first "
            "column.</b>  The last row is the one the mission is built on and "
            "is substituted in full below."
            % refs("fixed_point", "settled", "and"))


def rerun_sweep():
    """The concentration ladder: which parts each rung re-runs."""
    return ("<b>Each row is %s re-evaluated at that ratio</b>, so its source "
            "is this document run again, not a substitution.  The winning "
            "rung is the one substituted in full elsewhere; the objective is "
            "reproducible from the two columns beside it."
            % refs("fixed_point", "answer"))


def rerun_fleet():
    """The fleet ladder: which parts each rung re-runs."""
    return ("<b>Each row is %s re-evaluated at that fleet.</b>  The "
            "objective IS reproducible from the two columns beside it; the "
            "window and the clearing are that row's own run of %s."
            % (refs("market", "cost"), ref("market")))


def rerun_ladder():
    """The (F, W) grid: what each cell is."""
    return ("<b>Each cell is the cost and revenue cascade, %s, re-evaluated "
            "at that (F, W).</b>  The fleet table below carries the cost and "
            "revenue behind each objective." % refs("market", "cost"))


def payload_caps(out):
    """[(name, what it is, kg, key)] over the payload, and which bind.

    ONE DEFINITION WITH TWO READERS: the body's albedo note and the stack's
    caps table both say which ceiling set the payload, and they used to say
    it separately -- the note in a sentence typed once, "the mineable bound
    does not bind, and nor does the volume cap", printed under every body
    whichever cap bound.  The binder is the cap EQUAL to the payload flown,
    because the model takes the payload as their minimum; propellant made on
    site comes off the mineable and throughput budgets before any ore does.
    """
    C, M, B = out["C"], out["M"], out["B"]
    cas = M["cascade"]
    isru = M.get("isru_feed_loop", M["isru_feed"]) if C["isru"] else 0.0
    rocket = (min(cas["m_pay"], M["repair"]["refit"]["m_pay"])
              if M.get("repair") else cas["m_pay"])
    caps = [("rocket equation",
             ("the closed form under the settle-up's ceiling"
              if M.get("repair") else "bracket / denom, the closed form"),
             rocket, "m_fit" if M.get("repair") else "m_pay_cf"),
            ("mineable", "phi_min x m%s" % (", less the ISRU feed" if isru
                                            else ""),
             max(0.0, B["mineable"] - isru), "m_min"),
            ("volume", "a quarter of the fairing at the ore's bulk density",
             M["vol_cap"], "vol_cap")]
    if not C["beneficiated"]:
        caps.append(("throughput", "rate x t_dig,max, all the rig can move "
                     "in a stay%s" % (", less the ISRU feed" if isru else ""),
                     max(0.0, M["throughput"] - isru), "throughput"))
    # The payload IS the smallest of these, so one of them equals it to the
    # bit.  Naming the nearest instead would be the page guessing which
    # constraint sized the mission; it never had to on any swept mission,
    # ISRU ones included, and a page that cannot say is refused.
    binds = [name for name, _w, kg, _k in caps if kg == M["m_pay"]]
    if not binds:
        raise AssertionError("no cap equals the payload flown (%r)"
                             % M["m_pay"])
    return caps, binds


# ------------------------------------------------------------ 1. the body
def part_body(S, out):
    """Diameter, volume and mass, and the bound the body puts on one mission."""
    C, B = out["C"], out["B"]
    S.part("body", "The body",
           "Two of the three inputs to the mass are assumptions, not "
           "measurements; the citations say which.  " + cited(body_stamp(C)))
    # ⚠️  ONLY AN H-DERIVED DIAMETER HAS AN EQUATION TO SHOW.  A measured one,
    # and since data contract 1.4.0 one derived from a MEASURED MASS at the
    # class density (`diameter_source = "derived_mass"`), is a catalog input:
    # its row carries no assumed albedo, so the H chain would print NaN and a
    # derivation the body never went through.
    from_h = D.diameter_from_h(C["body"])
    if from_h:
        k = S.put("k_D", "k_D", "H-to-diameter constant", 1329.0, "km",
                  "<b>asteroid_catalog/derive.py</b> in AsteroidCatalog, "
                  "<i>_H_DIAMETER_CONSTANT</i>.  "
                  "<span class='src'>D_km = (1329 / sqrt(p_V)) * 10 ** (-H / 5), "
                  "Fowler and Chillemi 1992; the constant is 2 AU_km * "
                  "10 ** (-V_sun / 5) with the Sun's V = -26.762, and is the "
                  "same one JPL and the MPC use.</span>")
        H = S.put("H", "H", "absolute magnitude", C["H"], "mag",
                  cite_body(C, "absolute_magnitude_h"))
        pv = S.put("pV", "p_V", "geometric albedo", C["albedo"], "-",
                   cite_body(C, "albedo_assumed_for_diameter",
                             "measured albedo" if C["albedo_measured"]
                             else "NOT measured: the taxonomy default for this "
                                  "class, so the diameter is an inference"))
    else:
        S.put("D", "D", "diameter", B["d_km"], "km",
              cite_body(C, "diameter_km",
                        "not sized from H: %s"
                        % D.diameter_provenance(C["body"])))
    rho = S.put("rho", "rho", "bulk density", C["rho"], "g/cm3",
                cite_body(C, "density_gcm3",
                          "measured" if bool(C["body"].get("density_measured"))
                          else "NOT measured: the taxonomy estimate"))
    phi = S.put("phi", "phi_min", "mineable fraction of the body",
                C["cfg"].max_mining_fraction, "-",
                cite_config("max_mining_fraction")
                + ("  <span class='src'>Taken at 0.05 because this row was "
                   "written by calc %s, before 1.23.0 raised the default to "
                   "1.0.</span>" % D.esc(out["terms"]["stamp"])
                   if C.get("mining_old_default")
                   and C["cfg"].max_mining_fraction == 0.05 else ""))

    if from_h:
        root = pv ** 0.5
        S.step("sqrt_pV", "sqrt(p_V)", "root of the albedo",
               "sqrt(p_V)", "sqrt(%s)" % P(pv), root, "-", ["pV"])
        tenth = 10.0 ** (-H / 5.0)
        S.step("pogson", "10^(-H/5)", "the magnitude term",
               "10 ^ (-H / 5)", "10 ^ (-%s / 5)" % P(H), tenth, "-", ["H"])
        S.step("D", "D", "diameter", "k_D / sqrt(p_V) * 10 ^ (-H / 5)",
               "%s / %s * %s" % (P(k), P(root), P(tenth)), B["d_km"], "km",
               ["k_D", "sqrt_pV", "pogson"],
               "the row's own diameter_km, to the last bit")
    S.step("r", "r", "radius", "D / 2 * 1000",
           "%s / 2 * 1000" % P(B["d_km"]), B["r_m"], "m", ["D"])
    S.step("r3", "r^3", "radius cubed", "r * r * r",
           "%s ^ 3" % P(B["r_m"]), B["r3"], "m3", ["r"])
    S.step("V", "V", "volume of a sphere", "(4 / 3) * pi * r^3",
           "(4 / 3) * pi * %s" % P(B["r3"]), B["vol"], "m3", ["r3"])
    S.step("rho_si", "rho_SI", "density in SI", "rho * 1000",
           "%s * 1000" % P(rho), rho * 1000.0, "kg/m3", ["rho"],
           "g/cm3 to kg/m3")
    S.step("m", "m", "mass of the body", "rho_SI * V",
           "%s * %s" % (P(rho * 1000.0), P(B["vol"])), B["mass"], "kg",
           ["rho_si", "V"])
    S.step("m_min", "m_min", "what one mission may take", "phi_min * m",
           "%s * %s" % (P(phi), P(B["mass"])), B["mineable"], "kg",
           ["phi", "m"],
           "one of the four caps on the payload; see %s" % ref("stack"))
    if from_h:
        _caps, binds = payload_caps(out)
        if "mineable" in binds:
            reach = ("the mineable bound sets this payload, so an albedo "
                     "error moves the payload with the mass")
        elif "volume" in binds:
            reach = ("the volume cap sets this payload, and it scales with "
                     "the body's density but not with its albedo")
        else:
            reach = ("neither assumption reaches the answer here: the "
                     "payload is set by the %s, and the mass enters only "
                     "the mineable bound, which does not bind"
                     % " and the ".join(binds))
        S.step("albedo_lever", "dm/m", "what a factor-two albedo error does to "
               "the mass", "2 ^ 1.5, because D goes as 1 / sqrt(p_V) and m as "
               "D cubed, so m goes as p_V to the power of minus one and a half",
               "2 ^ 1.5", 2.0 ** 1.5, "x", ["pV", "m"], reach)


# -------------------------------------------- 2. what a kilogram is worth
# What a utility factor is, printed under the first phase's and pointed at by
# the rest.
UTILITY_NOTE = (
    "<span class='src'>How much of the launch cost avoided this commodity "
    "captures.  The utility factors are engineering judgements rather than "
    "measurements and are the softest assumption in the pipeline; "
    "CITATIONS.md says outright that there is nothing to cite, because they "
    "are a dial.  Every per-destination override runs DOWNWARD, against what "
    "the destination can dig up for itself.</span>")


def part_prices(S, out):
    """The launch cost avoided, the per-commodity price, and the phase table."""
    C = out["C"]
    # The blurb once said "No price here is a terrestrial quote" and had lost
    # the sentence that explained it, beside a row headed "terrestrial quote".
    S.part("prices", "What a kilogram is worth at the destination",
           "Delivered to the Earth's surface, a kilogram is worth its "
           "terrestrial quote and avoids no launch."
           if C.get("legs", ()) is None else
           "A kilogram used at the destination is worth its terrestrial "
           "quote plus a share of the launch it saves there, less refining "
           "it on site; one shipped home is worth its quote less the trip "
           "down.")
    hw_on = bool(C.get("stage_hardware"))
    c_leo = S.put("c_LEO", "c_LEO", "launch price to LEO",
                  C["leo_usd_per_kg"], "$/kg",
                  ("<b>spacecost/delivery.py</b>, <i>LEO_LAUNCH_USD_PER_KG</i>, "
                   "re-exported by <b>modules/mineral_value.py</b> as "
                   "<i>_LEO_USD_PER_KG</i>.  "
                   if hw_on else
                   "<b>campaign/worked_calculation.py</b>, "
                   "<i>_PRE_V040_LEO_USD_PER_KG</i>, spacecost 0.3.x's anchor, "
                   "which this row's Stage 2 table was priced at.  ")
                  + "<span class='src'>%s.  Chosen by the Stage 2 table's "
                    "own stamp, and held to every <i>used in space</i> price "
                    "that table carries.</span>"
                  % D.esc(C["pricing_label"]))
    if hw_on:
        rates = C["hw_rates"]
        # ⚠️  ONLY THE RATES THIS CHAIN SPENDS.  Every stage rate and the
        # entry-system rate used to be registered on every page, so a
        # cislunar page listed a lander's build rate and an EDL rate it can
        # never use as inputs "registered and never spent".  The condition is
        # the chain's own, the same one the legs below branch on.
        steps = C["chain"]["steps"]
        flown = set(leg["dry"] for leg in steps if leg["kind"] == "burn")
        for dry, rate in sorted(rates["stage"].items()):
            if dry not in flown:
                continue
            S.put("h_st%d" % round(dry * 100), "h_stage,%s" % P(dry),
                  "build cost of an expended stage at dry fraction %s"
                  % P(dry), rate, "$/kg of stage dry mass",
                  "<b>spacecost/delivery.py</b>, "
                  "<i>STAGE_HARDWARE_USD_PER_KG</i>, off the operational-cost "
                  "table: the tug rate is <i>Expendable upper stage recurring "
                  "cost</i>, the lander rate <i>Surface lander recurring "
                  "cost</i>.")
        if flown:
            S.put("h_prop", "h_prop", "the tug's propellant",
                  rates["propellant"], "$/kg",
                  "<b>spacecost/delivery.py</b>, "
                  "<i>TUG_PROPELLANT_USD_PER_KG</i>: the hydrolox row's "
                  "reference price.")
        if any(leg["kind"] != "burn" for leg in steps):
            S.put("h_edl", "h_edl", "the entry system an edl leg discards",
                  rates["entry"], "$/kg", "<b>spacecost/delivery.py</b>, "
                  "<i>ENTRY_SYSTEM_USD_PER_KG</i>: the TPS row, the nearest "
                  "priced article.")
    chain = C["chain"]
    prior = 1.0
    keys = ["c_LEO"]
    hw_keys = []
    for n, leg in enumerate(chain["steps"], 1):
        if leg["kind"] != "burn":
            S.step("leg%d" % n, "leg %d" % n, "surviving-mass fraction",
                   "1 / f_survive", "1 / %s" % P(leg["surviving"]),
                   leg["after"] / max(leg["before"], 1e-30), "kg/kg", keys[-1:])
            if hw_on:
                S.step("H%d" % n, "H_%d" % n, "leg %d entry system" % n,
                       "(m_after - m_before) h_edl",
                       "(%s - %s) * %s" % (P(leg["after"]), P(leg["before"]),
                                           P(C["hw_rates"]["entry"])),
                       leg["hw"], "$/kg", ["leg%d" % n, "h_edl"])
                hw_keys.append("H%d" % n)
            prior = leg["after"]
            keys.append("leg%d" % n)
            continue
        dv, isp, dry = leg["dv"], leg["isp"], leg["dry"]
        S.put("dv%d" % n, "dv_%d" % n, "leg %d delta-v" % n, dv, "m/s",
              "<b>spacecost/delivery.py</b>, <i>DELIVERY_CHAINS</i> for "
              "%s, re-exported as Module 2's <i>_DELIVERY_LEGS</i>.  "
              "<span class='src'>The chain is walked backwards from the "
              "payload, stage by stage: collapsing it into one burn throws "
              "away staging and overstates the destination.</span>"
              % D.esc(C["destination"]))
        S.put("isp%d" % n, "I_sp,%d" % n, "leg %d stage Isp" % n, isp, "s",
              "<b>spacecost/delivery.py</b>, <i>DELIVERY_CHAINS</i>.  "
              "The upper stage this leg is flown on.")
        S.put("dry%d" % n, "delta_%d" % n, "leg %d dry-mass fraction" % n,
              dry, "-", "<b>spacecost/delivery.py</b>, "
                        "<i>DELIVERY_CHAINS</i>.  Stage dry mass as a "
                        "fraction of its propellant load.")
        S.step("ve%d" % n, "v_e,%d" % n, "leg %d exhaust velocity" % n,
               "I_sp * g_0", "%s * %s" % (P(isp), P(W.G0)), leg["ve"], "m/s",
               ["isp%d" % n, "g0"])
        S.step("R%d" % n, "R_%d" % n, "leg %d mass ratio" % n,
               "exp(dv / v_e)", "exp(%s / %s)" % (P(dv), P(leg["ve"])),
               leg["R"], "-", ["dv%d" % n, "ve%d" % n])
        S.step("d%d" % n, "d_%d" % n, "leg %d stage dry mass" % n,
               "delta (R - 1) / (1 - delta R)",
               "%s * (%s - 1) / (1 - %s * %s)"
               % (P(dry), P(leg["R"]), P(dry), P(leg["R"])),
               leg["d"], "kg per kg of payload",
               ["dry%d" % n, "R%d" % n])
        S.step("m0_%d" % n, "m0_%d" % n, "leg %d start mass" % n,
               "R (1 + d)", "%s * (1 + %s)" % (P(leg["R"]), P(leg["d"])),
               leg["m0"], "kg per kg delivered", ["R%d" % n, "d%d" % n])
        if hw_on:
            rate = C["hw_rates"]["stage"][dry]
            S.step("H%d" % n, "H_%d" % n, "leg %d stage build cost" % n,
                   "m_before ((m0 / R - 1) h_stage + (m0 - m0 / R) h_prop)",
                   "%s * ((%s / %s - 1) * %s + (%s - 1 - (%s / %s - 1)) * %s)"
                   % (P(leg["before"]), P(leg["m0"]), P(leg["R"]), P(rate),
                      P(leg["m0"]), P(leg["m0"]), P(leg["R"]),
                      P(C["hw_rates"]["propellant"])),
                   leg["hw"], "$/kg",
                   ["m0_%d" % n, "R%d" % n, "h_st%d" % round(dry * 100),
                    "h_prop"])
            hw_keys.append("H%d" % n)
        prior = leg["after"]
        keys.append("m0_%d" % n)
    S.step("m_LEO", "m_LEO", "kilograms in LEO per kilogram delivered",
           "product of every leg" if chain["steps"] else
           "1: no leg is flown above LEO for this destination",
           " * ".join(P(s["m0"]) if s["kind"] == "burn"
                      else "(1 / %s)" % P(s["surviving"])
                      for s in chain["steps"]) or "1",
           chain["kg_in_leo"], "kg/kg", keys[1:] or ["c_LEO"])
    if C.get("legs", ()) is None:
        # `earth_surface`: Module 2 maps it to None, so nothing is launched
        # in its place and no launch cost is avoided.  `leo` maps to [] and
        # avoids the whole LEO price; the two are not the same question.
        p_l = S.step("P_L", "P_L", "launch cost a mined kilogram avoids",
                     "0: delivered to the Earth's surface, a kilogram avoids "
                     "no launch at all", "0", C["p_l"], "$/kg", ["c_LEO"],
                     "Module 2 maps this destination to no chain, not to an "
                     "empty one")
    elif hw_on and hw_keys:
        p_l = S.step("P_L", "P_L", "launch cost a mined kilogram avoids",
                     "c_LEO * m_LEO + sum of H",
                     "%s * %s + %s" % (
                         P(c_leo), P(chain["kg_in_leo"]),
                         " + ".join(P(s["hw"]) for s in chain["steps"])),
                     C["p_l"], "$/kg", ["c_LEO", "m_LEO"] + hw_keys,
                     "held to Module 2's own delivered_cost_usd_per_kg")
    else:
        p_l = S.step("P_L", "P_L", "launch cost a mined kilogram avoids",
                     "c_LEO * m_LEO",
                     "%s * %s" % (P(c_leo), P(chain["kg_in_leo"])),
                     C["p_l"], "$/kg", ["c_LEO", "m_LEO"],
                     "held to Module 2's own delivered_cost_usd_per_kg")

    S.prose("Used at the destination: <b>max(0, p + u P_L - c_ref)</b>, "
            "floored at zero by Stage 2.  Shipped home: <b>max(0, p - "
            "c_down)</b>.  Which one applies is Module 2's <i>value_route</i> "
            "column.")

    parts = C["price_parts"]
    refinery = bool(C.get("refinery"))
    # 🚨  THE PHASES AS THE BODY HAS THEM, NOT AS THEY ARE SOLD.  calc sells
    # the phases no process separates as one product (`_INSEPARABLE`), so the
    # hold's "nickel-iron" on a detailed-phase body is kamacite and taenite at
    # their fraction-weighted value.  This loop used to walk the SOLD list and
    # so registered nickel-iron's own Stage 2 row -- a row this body never
    # read -- and cited a "nickel-iron entry" in `comp_phases_detailed` that
    # does not exist.  The two prices happened to agree to the bit on 2018 DT,
    # which is the only reason nothing failed.  The members are priced here
    # and the merge is a step of its own below.
    merged = C.get("merged") or {}
    as_had = []
    for name, frac, price in C["phases"]:
        as_had.extend(merged.get(name, [(name, frac, price)]))
    seen, first_u = [], None
    for name, frac, price in as_had:
        base = "silicates" if name.startswith("other") else name
        pp = parts.get(base)
        if pp is None or base in seen:
            continue
        seen.append(base)
        short = base.replace(" ", "_").replace("-", "_")
        if base == "nickel-iron" and not C.get("phased"):
            continue
        # A phase that can be sold two ways registers its ROW price as the
        # as-it-is half, and the better of the two is its `P_` key below.
        dual = C.get("phased") and base in C.get("ways", {})
        pkey = ("Pa_%s" if dual else "P_%s") % short
        psym = ("P_%s,as-is" if dual else "P_%s") % base
        S.put("u_%s" % short, "u_%s" % base, "%s in-space utility" % base,
              pp["utility"], "-",
              "<b>mineral_value_catalog.csv</b>, row <i>%s</i>, column "
              "<i>in_space_utility</i>, written by "
              "<b>modules/mineral_value.py</b>'s "
              "<i>IN_SPACE_UTILITY_BY_DESTINATION</i> for %s.  %s"
              % (D.esc(base), D.esc(C["destination"]), UTILITY_NOTE
                 if first_u is None else
                 # Said in full once: it is the same five lines under
                 # every phase, a dozen times on an S-type.
                 "<span class='src'>The same judgement as %s's, above."
                 "</span>" % D.esc(first_u)))
        first_u = first_u or base
        # A mineral with NO terrestrial quote (the alloy, troilite,
        # schreibersite) is priced by Stage 2 at a terrestrial price of zero:
        # `apply_delivery_destination` reads a missing quote as None and
        # `in_space_price_usd_per_kg` as 0.0.  The page says so rather than
        # printing a NaN into a sum, which no reader can retype.
        quoted = math.isfinite(float(pp["terrestrial"]))
        terrestrial = float(pp["terrestrial"]) if quoted else 0.0
        S.put("t_%s" % short, "p_%s" % base, "%s terrestrial quote" % base,
              terrestrial, "$/kg", cite_mineral(C, base) if quoted else
              cite_mineral(C, base) + "  <span class='src'>No quote: Stage 2 "
              "prices a missing terrestrial price as zero.</span>")
        if pp["route"] == "used in space":
            S.put("c_%s" % short, "c_ref,%s" % base,
                  "%s on-site refining" % base, pp["refining"], "$/kg",
                  cite_column(C, base, "in_space_processing_usd_per_kg",
                              REFINING_NOTE))
        if pp["route"] == "used in space" and refinery:
            # calc v1.25.0: the refinery is flown, so the phase sells at the
            # price BEFORE the deduction: the net price plus what it took off.
            S.step("Pn_%s" % short, "P_%s,net" % base,
                   "%s price after the refining deduction" % base,
                   "max(0, p + u * P_L - c_ref)",
                   "max(0, %s + %s * %s - %s)"
                   % (P(terrestrial), P(pp["utility"]), P(C["p_l"]),
                      P(pp["refining"])),
                   pp["delivered"], "$/kg",
                   ["t_%s" % short, "u_%s" % short, "P_L", "c_%s" % short])
            S.step(pkey, psym, "%s price, refinery flown" % base,
                   "P_net + c_ref",
                   "%s + %s" % (P(pp["delivered"]), P(pp["refining"])),
                   pp["gross"], "$/kg", ["Pn_%s" % short, "c_%s" % short])
        elif pp["route"] == "used in space":
            S.step(pkey, psym, "%s delivered price" % base,
                   "max(0, p + u * P_L - c_ref)",
                   "max(0, %s + %s * %s - %s)"
                   % (P(terrestrial), P(pp["utility"]), P(C["p_l"]),
                      P(pp["refining"])),
                   pp["delivered"], "$/kg",
                   ["t_%s" % short, "u_%s" % short, "P_L", "c_%s" % short])
        else:
            S.put("dl_%s" % short, "c_down,%s" % base,
                  "%s downleg from the depot" % base,
                  pp["downleg"], "$/kg",
                  cite_column(C, base, "downleg_cost_usd_per_kg"))
            S.step(pkey, psym, "%s delivered price, flown home" % base,
                   "max(0, p - c_down)",
                   "max(0, %s - %s)"
                   % (P(terrestrial), P(pp["downleg"])),
                   pp["delivered"], "$/kg",
                   ["t_%s" % short, "dl_%s" % short])
            if refinery:
                # Shipped home it is refined on Earth: no deduction was taken,
                # so the price before it is the same number.
                S.step("Pn_%s" % short, "P_%s,net" % base,
                       "%s net price, refined on Earth" % base,
                       "P: shipped home, nothing is refined here",
                       P(pp["delivered"]), pp["delivered"], "$/kg", [pkey])

    # The element price table, once, for every element a yield-priced phase
    # reads.  Every one of these used to be a bare product inside a sum.
    # A table with a worked-out column prints its cells at the working's
    # precision: rounded to ten figures, `230.4205643` sat beside a working
    # that spent `230.420564301`, and a reader checking it saw two numbers.
    elements = []
    yields_by_mineral = []
    if C["yields"]:
        yields_by_mineral.append(("nickel-iron", C["yields"]))
    if C.get("phased"):
        yields_by_mineral += [(n, w["yields"])
                              for n, w in sorted(C.get("ways", {}).items())]
    for _mineral, ylds in yields_by_mineral:
        for element in ylds:
            if priced(C, element) and element not in elements:
                elements.append(element)
    net_of = {}
    if elements:
        S.prose("The elements a phase can be taken apart into, priced by the "
                "same two rules as the phases above%s.  A platinum-group "
                "element carries this body's enrichment, kappa, below."
                % ("; with the refinery flown the price that SELLS is the one "
                   "before the refining deduction and the NET one decides the "
                   "route" if refinery else ""))
        rows = []
        for element in elements:
            price = float(C["element_price"][element])
            pp = parts.get(element)
            if pp is None:
                rows.append([D.esc(element), "-", "-", "-", "-", "-",
                             "$" + P(price), "-", "-",
                             cited(cite_mineral(C, element))])
                net_of[element] = price
                continue
            p_t = (float(pp["terrestrial"])
                   if math.isfinite(float(pp["terrestrial"])) else 0.0)
            if pp["route"] == "used in space":
                net_work = S.claim("max(0, %s + %s * %s - %s)"
                                   % (P(p_t), P(pp["utility"]), P(C["p_l"]),
                                      P(pp["refining"])), pp["delivered"],
                                   "%s net price" % element)
                cost_col = "c_ref " + P(pp["refining"])
            else:
                net_work = S.claim("max(0, %s - %s)"
                                   % (P(p_t), P(pp["downleg"])),
                                   pp["delivered"], "%s price" % element)
                cost_col = "c_down " + P(pp["downleg"])
            if refinery and pp["route"] == "used in space":
                gross_work = S.claim("%s + %s" % (P(pp["delivered"]),
                                                  P(pp["refining"])), price,
                                     "%s gross price" % element)
            elif refinery:
                gross_work = "the same: refined on Earth"
            else:
                gross_work = "-"
            net_of[element] = pp["delivered"]
            rows.append([D.esc(element), D.esc(pp["route"]), P(p_t),
                         P(pp["utility"]), cost_col, net_work,
                         "$" + P(pp["delivered"]), gross_work,
                         ("$" + P(price)) if refinery else "-",
                         cited(cite_mineral(C, element))])
        S.block(D.table(["element", "route", "p $/kg", "u", "cost $/kg",
                         "net price worked out", "net $/kg",
                         "selling price worked out", "selling $/kg",
                         "source"], rows, "wide"))
        S.put("kappa", "kappa", "platinum-group enrichment", C["kappa"], "x",
              cite_body(C, "comp_pgm_enrichment",
                        "follows the taxonomy class"))

    def taken_apart(mineral, ylds):
        """The yield table for one mineral; returns (gross, net, rows)."""
        rows, gross, net = [], 0.0, 0.0
        g_terms, n_terms = [], []
        for element, fraction in ((e, f) for e, f in ylds.items()
                                  if priced(C, e)):
            price = C["element_price"][element]
            rare = element in C["rare_metals"]
            share = float(fraction) * (C["kappa"] if rare else 1.0)
            k_txt = (" * %s" % P(C["kappa"])) if rare else ""
            g = share * float(price)
            n = share * float(net_of.get(element, price))
            gross += g
            net += n
            g_terms.append("%s%s * %s" % (P(float(fraction)), k_txt,
                                          P(float(price))))
            n_terms.append("%s%s * %s" % (P(float(fraction)), k_txt,
                                          P(float(net_of.get(element, price)))))
            g_work = S.claim(g_terms[-1], g, "%s in %s" % (element, mineral))
            row = [D.esc(element), P(float(fraction)),
                   ("x " + P(C["kappa"])) if rare else "-",
                   "$" + P(float(price)), g_work, "$" + P(g)]
            if refinery:
                n_work = S.claim(n_terms[-1], n, "%s net in %s"
                                 % (element, mineral))
                row += ["$" + P(float(net_of.get(element, price))),
                        n_work, "$" + P(n)]
            rows.append(row)
        return gross, net, g_terms, n_terms, rows

    if C["yields"]:
        S.prose("Nickel-iron is an alloy, so its price is the "
                "yield-weighted sum of its elements, with this body's "
                "platinum-group enrichment on the rare metals.")
        gross, _net, g_terms, _n, rows = taken_apart("nickel-iron",
                                                     C["yields"])
        head = ["element", "yield (kg/kg)", "enrich", "price $/kg",
                "contribution worked out", "contribution $/kg"]
        if refinery:
            head += ["net $/kg", "net worked out", "net contribution"]
        S.block(D.table(head, rows, "wide"))
        S.step("P_alloy", "P_Fe-Ni", "nickel-iron blended price",
               "sum over elements of yield * enrichment * price",
               " + ".join(g_terms), C["alloy"], "$/kg", ["kappa", "P_L"],
               "the contribution column above, added term by term")

    if C.get("phased") and C.get("ways"):
        S.prose("A mineral with element yields is worth the better of two "
                "prices: its own row, used as it is, and the yield-weighted "
                "sum of its elements, taken apart.%s"
                % ("  With the refinery flown the better is decided on the "
                   "NET prices, after what each route's refining costs, and "
                   "the mineral then sells at the chosen route's price "
                   "before that deduction." if refinery else ""))
        for name, w in sorted(C["ways"].items()):
            short = name.replace(" ", "_").replace("-", "_")
            gross, net, g_terms, n_terms, rows = taken_apart(name, w["yields"])
            S.block(D.table(["element of %s" % D.esc(name), "yield (kg/kg)",
                             "enrich", "price $/kg", "contribution worked out",
                             "contribution $/kg"]
                            + (["net $/kg", "net worked out",
                                "net contribution"] if refinery else []),
                            rows, "wide"))
            inputs, candidates = [], []
            have_as_is = w["as_is"] is not None and ("Pa_%s" % short) in S.tag
            if have_as_is:
                inputs.append("Pa_%s" % short)
                candidates.append(w["as_is"])
            if gross > 0:
                S.step("Pr_%s" % short, "P_%s,apart" % name,
                       "%s taken apart" % name,
                       "sum over its elements of yield * enrichment * price",
                       " + ".join(g_terms), gross, "$/kg", ["kappa", "P_L"],
                       "the contribution column of the table above")
                inputs.append("Pr_%s" % short)
                candidates.append(gross)
            if not candidates:
                # Stage 2 gives every phase a price one way or the other; a
                # phase with neither is a table this page cannot describe.
                raise AssertionError("%s has no price as it is or taken "
                                     "apart" % name)
            if refinery and gross > 0:
                S.step("Prn_%s" % short, "P_%s,apart,net" % name,
                       "%s taken apart, net of refining" % name,
                       "sum over its elements of yield * enrichment * net "
                       "price", " + ".join(n_terms), net, "$/kg",
                       ["Pr_%s" % short],
                       "the net contribution column of the table above")
                as_net = w.get("as_is_net")
                if as_net is not None and ("Pn_%s" % short) in S.tag:
                    S.step("dP_%s" % short, "dP_%s" % name,
                           "which route %s is sold by" % name,
                           "P_apart,net - P_as-is,net",
                           "%s - %s" % (exact(net), exact(as_net)),
                           net - as_net,
                           "$/kg", ["Prn_%s" % short, "Pn_%s" % short],
                           "%s, so it is %s"
                           % ("positive" if net > as_net else
                              "not positive",
                              "taken apart" if w["chosen"] == "refined"
                              else "sold as it is"))
                    inputs = ["dP_%s" % short] + inputs
                value = w["refined"] if w["chosen"] == "refined" else w["as_is"]
                S.step("P_%s" % short, "P_%s" % name, "%s price" % name,
                       "the %s price, before the refining deduction"
                       % ("taken-apart" if w["chosen"] == "refined"
                          else "as-is"),
                       P(value), value, "$/kg", inputs)
                continue
            if len(candidates) == 1:
                S.step("P_%s" % short, "P_%s" % name, "%s price" % name,
                       "the %s price: it has no other"
                       % ("as-is" if have_as_is else "taken-apart"),
                       P(candidates[0]), candidates[0], "$/kg", inputs)
                continue
            S.step("P_%s" % short, "P_%s" % name, "%s price" % name,
                   "the better of as it is and taken apart",
                   "max(%s)" % ", ".join(P(v) for v in candidates),
                   max(candidates), "$/kg", inputs)

    for product, group in sorted(merged.items()):
        short = product.replace(" ", "_").replace("-", "_")
        keys = ["P_" + m.replace(" ", "_").replace("-", "_")
                for m, _f, _v in group]
        keys = [k for k in keys if k in S.tag]
        frac = sum(f for _m, f, _v in group)
        value = next(p for n, _f, p in C["phases"] if n == product)
        names = [D.esc(m) for m, _f, _v in group]
        S.prose("%s are one grain that no separation takes apart, so calc "
                "sells them as one product, <i>%s</i>, at their "
                "fraction-weighted value (<i>_INSEPARABLE</i> in "
                "<b>modules/calc.py</b>)."
                % (" and ".join([", ".join(names[:-1]), names[-1]]
                                if len(names) > 1 else names),
                   D.esc(product)))
        S.step("f_%s" % short, "f_%s" % product, "%s, as the hold carries it"
               % product, "sum of its members' fractions",
               " + ".join(P(f) for _m, f, _v in group), frac, "-", [],
               "each member's fraction is in the hold table below")
        S.step("P_%s" % short, "P_%s" % product, "%s price" % product,
               "sum of f * P over its members / f_%s" % product,
               "(%s) / %s" % (" + ".join("%s * %s" % (P(f), P(v))
                                         for _m, f, v in group), P(frac)),
               value, "$/kg", keys + ["f_%s" % short])

    # One sentence for both cases: no body in the catalog has phases that
    # sum to exactly one, so a second sentence for that case never rendered.
    S.prose("The hold is filled from this.  Whatever part of the body no "
            "phase names is carried at the silicate quote rather than "
            "discarded, as the <i>other</i> row when there is one, which is "
            "why this totals one.")
    rows = []
    for name, frac, price in C["phases"]:
        if name in merged:
            column = cite_body(C, C.get("phases_col") or "comp_phases",
                               "its %s entries, sold as one product: %s"
                               % (" and ".join(D.esc(m) for m, _f, _v
                                               in merged[name]),
                                  " + ".join(P(f) for _m, f, _v
                                             in merged[name])))
        elif name.startswith("other"):
            column = ("the residual: 1 - sum of the phases"
                      if C.get("phased") else
                      "the residual: 1 - sum of the four taxonomy fractions")
        elif C.get("phased"):
            column = cite_body(C, C.get("phases_col") or "comp_phases",
                               "its %s entry" % name)
        else:
            column = cite_body(C, "comp_%s_fraction"
                               % {"nickel-iron": "metal",
                                  "water": "ice"}.get(name, name))
        work = S.claim("%s * %s" % (P(frac), P(price)), frac * price,
                       "%s contribution" % name)
        rows.append([D.esc(name), P(frac), "$" + P(price), work,
                     "$" + P(frac * price), cited(column)])
    S.block(D.table(["phase", "mass fraction f_c", "$/kg P_c",
                     "contribution worked out", "contribution $/kg",
                     "where the fraction comes from"], rows, "wide"))
    S.step("bulk", "V_bulk", "value of a kilogram of run-of-mine ore",
           "sum over phases of f_c * P_c",
           " + ".join("%s * %s" % (P(f), P(p))
                      for _n, f, p in C["phases"]),
           C["bulk"], "$/kg", phase_price_keys(S, C))
    best = max(p for _n, _f, p in C["phases"])
    S.step("P_best", "P_best", "the purity bound",
           "max over phases of P_c",
           "max(%s)" % ", ".join(P(p) for _n, _f, p in C["phases"]),
           best, "$/kg", phase_price_keys(S, C),
           "concentrating rejects gangue, it does not transmute, so no "
           "amount of processing lifts the delivered value above this"
           + ("" if C["run_beneficiated"] else
              ".  This run did not concentrate, so the model's "
              "best_phase_usd_per_kg column carries V_bulk instead"))


# --------------------------------------------------------- the dial ledger
def repo_path(path):
    """A path as the page prints it: relative to the repository when inside it.

    The config holds absolute paths, which name the machine rather than the
    file and cannot wrap; relative, they say which file to open in a clone.
    """
    path = str(path)
    if os.path.isabs(path):
        rel = os.path.relpath(path, ROOT)
        if not rel.startswith(".."):
            return rel.replace(os.sep, "/")
    return path


def dial_value(value):
    """One dial's value as the ledger prints it, quoted rather than claimed."""
    if isinstance(value, bool):
        text = "True" if value else "False"
    elif isinstance(value, (int, float)):
        text = P(value, 12)
    else:
        text = str(value)
    return cited(D.esc(text))


def grouped(table):
    """`table` with each group heading (a row whose cells after the first are
    all empty) spanning the whole row instead of the first column."""
    def span(m):
        """One row, spanned if it is a group heading."""
        cells = re.findall(r"<td>(.*?)</td>", m.group(1), re.S)
        if len(cells) < 2 or not cells[0] or any(cells[1:]):
            return m.group(0)
        return '<tr class="grp"><td colspan="%d">%s</td></tr>' % (len(cells),
                                                                  cells[0])
    return re.sub(r"<tr>((?:<td>.*?</td>)+)</tr>", span, table, flags=re.S)


def part_dials(S, out):
    """Every calc dial, the value this page used, and how it knows.

    🚨  A WORKSHEET THAT SHOWS SEVENTEEN DIALS AND SPENDS EIGHTY-FOUR IS
    ASKING TO BE TRUSTED ABOUT SIXTY-SEVEN OF THEM.  Measured on 2026-10-08:
    the derivation read 84 calc fields and the sheet registered 17 as inputs,
    so `model_tank_mass`, `model_launch_windows`, `use_aerocapture_return`,
    `max_fleet_ships`, `surplus_price_fraction` and the rest shaped the answer
    without ever appearing.  A reader redoing it by hand could not know which
    terms were on.

    THE LIST IS THE DATACLASS, NOT A LIST OF FIELDS TYPED HERE, so a dial
    added to `CalcConfig` tomorrow joins this table with no edit.  The file
    dials are tabulated too, against the files this page actually read, and
    every path is shown relative to the repository: an absolute path is the
    one token the ledger cannot wrap, and it printed the user's home folder.
    The tag column is FOUND, by reading which inputs cite each field, so it
    cannot claim a dial is registered when it is not.
    """
    import dataclasses
    import ui_meta
    C = out["C"]
    cfg = C["cfg"]
    settled = W.dials_in_force(C)
    docs = field_docs("calc")
    S.part("dials", "The dials in force",
           "Every setting of Stage 4's config, the value this page was "
           "worked at, and how the page knows it.  A dial the row settles "
           "is read off the row, because the run that wrote it may have "
           "been configured differently from this process.  The tag column "
           "names the input each numeric dial is registered under where a "
           "step spends it.")
    tags = {}
    for part in S.parts:
        for row in part["rows"]:
            if row[0] != "input":
                continue
            for name in re.findall(r"field <i>([a-z0-9_]+)</i>", row[6] or ""):
                tags.setdefault(name, []).append(row[1])
    rows, section, paths = [], None, []
    for field in dataclasses.fields(cfg):
        name = field.name
        if name in ui_meta.PATH_FIELDS:
            paths.append(name)
            continue
        doc = docs.get(name) or {}
        sec = doc.get("section") or "Other"
        if sec != section:
            rows.append([cited("<b>%s</b>" % D.esc(sec)), "", "", "", ""])
            section = sec
        # Every config field is declared with a plain default; a factory
        # would need calling here, and is refused rather than shown blank.
        if field.default_factory is not dataclasses.MISSING:
            raise AssertionError("%s is declared with a default factory"
                                 % name)
        default = field.default
        if name in settled:
            value, how = settled[name]
        else:
            value = getattr(cfg, name)
            how = ("this process's config, at the dataclass default"
                   if value == default else
                   "this process's config, NOT the dataclass default (%s)"
                   % D.esc(default))
        line = field_line(name)
        if not line:
            raise AssertionError("no definition line found for %s" % name)
        text = trim(definition(doc.get("help") or ""))
        # Quoted here first, so an input that cites the field points back
        # rather than printing it again (`said_once`).
        S.said[" ".join(text.split())] = (
            "Quoted in full beside the dial in %s." % ref("dials"))
        rows.append(["<i>%s</i>" % D.esc(name), dial_value(value), cited(how),
                     '<span class="uses">%s</span>'
                     % (", ".join(tag_link(t, "r")
                                  for t in tags.get(name, [])) or "-"),
                     cited("%s <b>%s</b>" % (text, D.esc(line)))])
    # The FILE dials, tabulated against the files this page actually read.
    # They hold no number the arithmetic spends; what a reader needs from
    # them is which file each table came from, and the page chose those by
    # the row's provenance rather than through the config, so both are shown.
    files = C.get("files", {})
    # Said once in the heading: on every row it filled four lines of the
    # narrowest column eleven times over.
    rows.append([cited("<b>Files</b>: each value is this process's config; "
                       "the file a table was read from is chosen by the "
                       "row's provenance, as the header card says"),
                 "", "", "", ""])
    for name in paths:
        read = files.get(name)
        if read:
            what = ("this page read it as <code>%s</code>."
                    % D.esc(repo_path(read)))
        elif name == "delta_v_segments_file":
            what = ("this page reads no file through it: every Delta-v leg "
                    "is the model's own function of the body's orbit, worked "
                    "out in its own part.")
        else:
            raise AssertionError("no file recorded for the path dial %s"
                                 % name)
        rows.append(["<i>%s</i>" % D.esc(name),
                     dial_value(repo_path(getattr(cfg, name))),
                     cited("this process's config, as the heading says"),
                     '<span class="uses">-</span>',
                     cited("%s <b>%s</b>" % (what, D.esc(field_line(name)))
                           )])
    S.block(grouped(D.table(["dial", "value used", "how this page knows it",
                             "tag", "what it is (the field's own comment)"],
                            rows, "wide")))
    S.prose("Stages 2 and 3 reach this page only through the tables they "
            "wrote, and every row of those tables that a step spends is an "
            "input with its own citation.")


# ------------------------------------------------------- 0. the constants
def part_constants(S, out):
    """The physical constants every later part spends, registered once."""
    C = out["C"]
    S.part("constants", "Constants",
           "Registered here so no step below introduces an untagged "
           "number.")
    S.put("g0", "g_0", "standard gravity", W.G0, "m/s2",
          cite_here("G0", "The CODATA standard gravity, exact by "
                    "definition; the same constant spacecost exports as "
                    "G0_M_S2."))
    # The sources below were read off the documents on 2026-10-19 and agree
    # with the constants to the figures each publishes; CITATIONS.md section
    # 4 lists them.
    S.put("mu_E", "mu_E", "Earth gravitational parameter", W.MU_EARTH,
          "km3/s2", cite_here("MU_EARTH", "The IERS Conventions (2010), "
                              "IERS Technical Note 36, Table 1.1: GM = "
                              "3.986004418e14 m3/s2."))
    S.put("v_E", "v_E", "Earth mean orbital velocity", W.V_EARTH, "km/s",
          cite_here("V_EARTH", "The canonical unit the transfer is "
                    "worked in: speeds are carried as multiples of it and "
                    "converted once.  NASA's Earth Fact Sheet (NSSDCA) "
                    "gives a mean orbital velocity of 29.78 km/s."))
    S.put("r_LEO", "r_LEO", "parking-orbit radius", W.R_LEO, "km",
          cite_here("R_LEO", "6,378.14 km of Earth radius plus a "
                    "200 km parking orbit."))
    S.put("tau", "tau_fit", "cruise-time fit", W.TAU_CRUISE_FIT_YR_PER_M_S,
          "yr per m/s",
          cite_here("TAU_CRUISE_FIT_YR_PER_M_S", "A linear fit of "
                    "transfer time against delta-v, floored at half a "
                    "year."))
    if C["return_leg"] in ("ret_cislunar_prop", "ret_lunar_surface_prop"):
        S.put("R_M", "R_M", "lunar orbital radius", W.R_MOON, "km",
              cite_here("R_MOON", "The Moon's semi-major axis: NASA's Moon "
                        "Fact Sheet (NSSDCA) gives 0.3844 million km."))
        S.put("dv_NRHO", "dv_NRHO", "NRHO insertion increment", W.DV_NRHO,
              "km/s",
              cite_here("DV_NRHO", "Capture BINDS the orbit at low "
                        "perigee and takes the Oberth benefit there; this "
                        "is the increment that finishes the job at the "
                        "depot."))


def return_leg_steps(S, out, leg):
    """Register every burn of the return leg the row flew; return their keys.

    🚨  ONLY THE CISLUNAR CAPTURE WAS EVER WORKED OUT.  Every other arrival
    -- LEO, GEO, the Earth's surface, the Moon's, both Mars legs -- was a
    table of burns printed as bare numbers, so a page about any winner not at
    a cislunar depot asked to be trusted about its return.  Each leg is the
    derivation's own `_legs` / `_mars_legs` arithmetic, step for step, in the
    order `arrival` lists the burns, so the sum below is that leg's value.
    A leg this function does not know is a refusal, not a silent table.
    """
    C, DV = out["C"], out["DV"]
    name = C["return_leg"]
    keys = []
    vinf = leg["v_inf"]

    def const(key, symbol, what, value, unit, constant, why=""):
        """A constant `worked_calculation` fixes, registered by name."""
        if key not in S.tag:
            S.put(key, symbol, what, value, unit, cite_here(constant, why))
        return key

    def circularise(prefix, v_apo, v_apo_key):
        """`circularise_at_geo`: one burn for speed AND the GEO plane change."""
        circularise_prep(S)
        value = W.circularise_at_geo(v_apo)
        S.step(prefix, "dv_circ", "circularise at GEO, plane change "
               "included", "sqrt(v_a^2 + v_GEO^2 - 2 v_a v_GEO cos eps)",
               "sqrt(%s ^ 2 + %s ^ 2 - 2 * %s * %s * cos(%s deg))"
               % (exact(v_apo), exact(W.V_GEO), exact(v_apo), exact(W.V_GEO),
                  P(23.44)), value, "km/s", [v_apo_key, "v_GEO", "tilt"],
               "a law of cosines rather than a sum: one burn that changes "
               "speed and direction costs less than two")
        return prefix

    if name.startswith("ret_mars"):
        a_m = const("a_Mars", "a_Mars", "Mars' semi-major axis",
                    W.A_MARS_AU, "AU", "A_MARS_AU")
        r_t = DV["r_target"]
        a_tm = (r_t + W.A_MARS_AU) / 2.0
        S.step("a_tM", "a_tM", "the transfer ellipse to Mars",
               "(r_t + a_Mars) / 2", "(%s + %s) / 2" % (P(r_t),
                                                        P(W.A_MARS_AU)),
               a_tm, "AU", ["r_t", a_m],
               "a separate heliocentric transfer: none of the Earth "
               "arithmetic above applies to this half")
        vt2 = 2.0 / r_t - 1.0 / a_tm
        va2 = 2.0 / r_t - 1.0 / C["a_au"]
        vm2 = 2.0 / W.A_MARS_AU - 1.0 / a_tm
        S.step("vtA2", "v_t,ast^2", "transfer speed at the asteroid, squared",
               "2 / r_t - 1 / a_tM", "2 / %s - 1 / %s" % (exact(r_t),
                                                           exact(a_tm)),
               vt2, "x v_E^2", ["r_t", "a_tM"])
        S.step("va2", "v_ast^2", "the asteroid's speed there, squared",
               "2 / r_t - 1 / a", "2 / %s - 1 / %s" % (exact(r_t),
                                                        exact(C["a_au"])),
               va2, "x v_E^2", ["r_t", "a"])
        dep2 = vt2 + va2 - 2.0 * math.sqrt(vt2 * va2) * leg["cos_i"]
        S.step("depM", "dv_dep,M", "asteroid departure for Mars, plane "
               "change included",
               "sqrt(v_t^2 + v_ast^2 - 2 sqrt(v_t^2 v_ast^2) cos i) * v_E",
               "sqrt(%s + %s - 2 * sqrt(%s * %s) * %s) * %s"
               % (exact(vt2), exact(va2), exact(vt2), exact(va2),
                  exact(leg["cos_i"]), P(W.V_EARTH)),
               leg["mars_depart"], "km/s", ["vtA2", "va2", "cos_i", "v_E"])
        keys.append("depM")
        if name in ("ret_mars_surface_prop", "ret_mars_orbit_prop"):
            S.step("vtM2", "v_t,Mars^2", "transfer speed at Mars, squared",
                   "2 / a_Mars - 1 / a_tM",
                   "2 / %s - 1 / %s" % (exact(W.A_MARS_AU), exact(a_tm)), vm2,
                   "x v_E^2", ["a_Mars", "a_tM"])
            S.step("vinfM", "v_inf,M", "arrival excess at Mars",
                   "|sqrt(v_t,Mars^2) - sqrt(1 / a_Mars)| * v_E",
                   "|sqrt(%s) - sqrt(1 / %s)| * %s"
                   % (exact(vm2), P(W.A_MARS_AU), P(W.V_EARTH)),
                   leg["v_inf_mars"], "km/s", ["vtM2", "a_Mars", "v_E"])
            const("mu_M", "mu_M", "Mars gravitational parameter", W.MU_MARS,
                  "km3/s2", "MU_MARS")
        if name == "ret_mars_surface_prop":
            const("r_Mpark", "r_M,park", "low Mars orbit radius",
                  W.R_MARS_PARK, "km", "R_MARS_PARK", "3,396.2 km of Mars "
                  "radius plus a 200 km parking orbit.")
            v_c = math.sqrt(W.MU_MARS / W.R_MARS_PARK)
            S.step("vcM", "v_c,M", "circular speed in low Mars orbit",
                   "sqrt(mu_M / r_M,park)",
                   "sqrt(%s / %s)" % (P(W.MU_MARS), P(W.R_MARS_PARK)), v_c,
                   "km/s", ["mu_M", "r_Mpark"])
            S.step("capM", "dv_cap,M", "capture into low Mars orbit",
                   "sqrt((sqrt(2) v_c,M)^2 + v_inf,M^2) - v_c,M",
                   "sqrt((sqrt(2) * %s) ^ 2 + %s ^ 2) - %s"
                   % (exact(v_c), exact(leg["v_inf_mars"]), exact(v_c)),
                   leg["mars_capture"], "km/s", ["vcM", "vinfM"])
            keys.append("capM")
            keys.append(const("dv_desc", "dv_desc", "powered descent with "
                              "no atmospheric help",
                              W.DV_MARS_POWERED_DESCENT, "km/s",
                              "DV_MARS_POWERED_DESCENT"))
        elif name == "ret_mars_surface_aero":
            keys.append(const("dv_retro", "dv_retro", "terminal "
                              "retropropulsion after aeroentry",
                              W.DV_MARS_RETROPROP, "km/s",
                              "DV_MARS_RETROPROP", "The atmosphere absorbs "
                              "the capture and most of the descent."))
        elif name == "ret_mars_orbit_prop":
            const("r_1solp", "r_1sol,peri", "1-sol ellipse periapsis radius",
                  W.R_MARS_1SOL_PERI, "km", "R_MARS_1SOL_PERI",
                  "250 km altitude.")
            const("r_1sola", "r_1sol,apo", "1-sol ellipse apoapsis radius",
                  W.R_MARS_1SOL_APO, "km", "R_MARS_1SOL_APO",
                  "33,793 km altitude.")
            S.step("a_1sol", "a_1sol", "the 1-sol depot ellipse",
                   "(r_1sol,peri + r_1sol,apo) / 2",
                   "(%s + %s) / 2" % (P(W.R_MARS_1SOL_PERI),
                                      P(W.R_MARS_1SOL_APO)),
                   W.A_MARS_1SOL, "km", ["r_1solp", "r_1sola"])
            S.step("vesc1", "v_esc,1sol", "escape speed at its periapsis",
                   "sqrt(2 mu_M / r_1sol,peri)",
                   "sqrt(2 * %s / %s)" % (P(W.MU_MARS),
                                          P(W.R_MARS_1SOL_PERI)),
                   W.V_ESC_MARS_1SOL, "km/s", ["mu_M", "r_1solp"])
            S.step("vell1", "v_ell,1sol", "speed at periapsis on the ellipse",
                   "sqrt(mu_M (2 / r_1sol,peri - 1 / a_1sol))",
                   "sqrt(%s * (2 / %s - 1 / %s))"
                   % (P(W.MU_MARS), P(W.R_MARS_1SOL_PERI),
                      P(W.A_MARS_1SOL)),
                   W.V_ELL_MARS_1SOL, "km/s", ["mu_M", "r_1solp", "a_1sol"])
            S.step("cap1", "dv_cap,1sol", "capture into the 1-sol depot "
                   "ellipse", "sqrt(v_esc,1sol^2 + v_inf,M^2) - v_ell,1sol",
                   "sqrt(%s ^ 2 + %s ^ 2) - %s"
                   % (exact(W.V_ESC_MARS_1SOL), exact(leg["v_inf_mars"]),
                      exact(W.V_ELL_MARS_1SOL)),
                   leg["mars_capture_1sol"], "km/s",
                   ["vesc1", "vinfM", "vell1"],
                   "the burn only BINDS the orbit, deep at periapsis")
            keys.append("cap1")
        elif name == "ret_mars_orbit_aero":
            keys.append(const("dv_trim", "dv_trim", "periapsis raise after "
                              "aerocapture", W.DV_AEROBRAKE_TRIM, "km/s",
                              "DV_AEROBRAKE_TRIM", "Charged at the Earth "
                              "aerobrake trim."))
        else:
            raise AssertionError("no derivation for the return leg %r" % name)
        return keys

    keys.append("dv_match")
    if name in ("ret_cislunar_prop", "ret_lunar_surface_prop"):
        S.step("a_ell", "a_ell", "the bound capture ellipse",
               "(r_LEO + R_M) / 2",
               "(%s + %s) / 2" % (P(W.R_LEO), P(W.R_MOON)),
               leg["a_ell"], "km", ["r_LEO", "R_M"],
               "capture BINDS the orbit; it does not circularise")
        S.step("v_ell", "v_ell", "speed at perigee on that ellipse",
               "sqrt(mu_E (2 / r_LEO - 1 / a_ell))",
               "sqrt(%s * (2 / %s - 1 / %s))"
               % (P(W.MU_EARTH), P(W.R_LEO), P(leg["a_ell"])),
               leg["v_ell"], "km/s", ["mu_E", "r_LEO", "a_ell"])
        S.step("dv_cap", "dv_cap", "capture, then NRHO insertion",
               "max(0, v_hyp - v_ell) + dv_NRHO",
               "max(0, %s - %s) + %s" % (P(leg["v_hyp"]), P(leg["v_ell"]),
                                         P(W.DV_NRHO)),
               leg["cap"], "km/s", ["v_hyp", "v_ell", "dv_NRHO"])
        keys.append("dv_cap")
        if name == "ret_lunar_surface_prop":
            const_name = ("DV_NRHO_TO_LUNAR_SURFACE"
                          if C["dv_nrho_lunar"] == W.DV_NRHO_TO_LUNAR_SURFACE
                          else "_DV_NRHO_TO_LUNAR_SURFACE_BEFORE_1300")
            keys.append(const("dv_lunar", "dv_NRHO-surface", "NRHO to low "
                              "lunar orbit to the surface, all propulsive",
                              C["dv_nrho_lunar"], "km/s", const_name,
                              "The descent the run that wrote this row "
                              "flew, chosen by the row's calc stamp."))
    elif name in ("ret_leo_prop", "ret_earth_surface_prop"):
        S.step("capLEO", "dv_cap,LEO", "capture into LEO", "v_hyp - v_LEO",
               "%s - %s" % (P(leg["v_hyp"]), P(leg["v_leo"])),
               leg["leo_capture"], "km/s", ["v_hyp", "v_LEO"],
               "the departure burn run backwards: it kills the escape "
               "velocity as well as the excess")
        keys.append("capLEO")
        if name == "ret_earth_surface_prop":
            keys.append(const("dv_deorb", "dv_deorbit", "deorbit burn",
                              W.DV_LEO_DEORBIT, "km/s", "DV_LEO_DEORBIT",
                              "The capsule still has to come down."))
    elif name == "ret_leo_aero":
        keys.append(const("dv_trim", "dv_trim", "periapsis-raise trim after "
                          "aerobraking", W.DV_AEROBRAKE_TRIM, "km/s",
                          "DV_AEROBRAKE_TRIM"))
    elif name == "ret_geo_prop":
        S.step("v_escGEO", "v_esc,GEO", "escape speed at GEO",
               "sqrt(2) * v_GEO", "sqrt(2) * %s" % exact(W.V_GEO),
               W.V_ESC_GEO, "km/s", [circularise_prep(S)])
        v_dir = math.sqrt(W.V_ESC_GEO ** 2 + vinf ** 2)
        S.step("v_dirGEO", "v_a,direct", "arriving at GEO's radius on the "
               "hyperbola", "sqrt(v_esc,GEO^2 + v_inf^2)",
               "sqrt(%s ^ 2 + %s ^ 2)" % (exact(W.V_ESC_GEO), exact(vinf)),
               v_dir, "km/s", ["v_escGEO", "v_inf"])
        direct = circularise("dv_dirGEO", v_dir, "v_dirGEO")
        S.step("a_GTO", "a_GTO", "a GTO-shaped capture ellipse",
               "(r_LEO + R_GEO) / 2", "(%s + %s) / 2" % (P(W.R_LEO),
                                                         P(W.R_GEO)),
               W.A_GTO, "km", ["r_LEO", "R_GEO"])
        S.step("v_GTOp", "v_GTO,peri", "its perigee speed",
               "sqrt(mu_E (2 / r_LEO - 1 / a_GTO))",
               "sqrt(%s * (2 / %s - 1 / %s))" % (P(W.MU_EARTH), P(W.R_LEO),
                                                  P(W.A_GTO)),
               W.V_GTO_PERIGEE, "km/s", ["mu_E", "r_LEO", "a_GTO"])
        S.step("v_GTOa", "v_GTO,apo", "its apogee speed",
               "sqrt(mu_E (2 / R_GEO - 1 / a_GTO))",
               "sqrt(%s * (2 / %s - 1 / %s))" % (P(W.MU_EARTH), P(W.R_GEO),
                                                  P(W.A_GTO)),
               W.V_GTO_APOGEE, "km/s", ["mu_E", "R_GEO", "a_GTO"])
        apogee = circularise("dv_apoGEO", W.V_GTO_APOGEE, "v_GTOa")
        oberth = (leg["v_hyp"] - W.V_GTO_PERIGEE) + W.DV_GTO_APOGEE_TO_GEO
        S.step("dv_obGEO", "dv_Oberth", "capture at LEO perigee into GTO, "
               "then circularise", "(v_hyp - v_GTO,peri) + dv_apo",
               "(%s - %s) + %s" % (exact(leg["v_hyp"]),
                                   exact(W.V_GTO_PERIGEE),
                                   exact(W.DV_GTO_APOGEE_TO_GEO)),
               oberth, "km/s", ["v_hyp", "v_GTOp", apogee])
        S.step("capGEO", "dv_cap,GEO", "capture into GEO",
               "min(dv_direct, dv_Oberth)",
               "min(%s, %s)" % (exact(S.value[direct]), exact(oberth)),
               leg["geo_capture"], "km/s", [direct, "dv_obGEO"],
               "neither route always wins; this one took the %s"
               % ("direct one" if S.value[direct] < oberth else "Oberth one"))
        keys.append("capGEO")
    elif name == "ret_geo_aero":
        const("r_aero", "r_aero", "aerocapture periapsis radius",
              6378.14 + 100.0, "km", "A_GEO_AEROCAPTURE",
              "6,378.14 km of Earth radius plus a 100 km pass.")
        circularise_prep(S)
        a_ae = W.A_GEO_AEROCAPTURE
        S.step("a_aero", "a_aero", "the ellipse drag leaves, apogee at GEO",
               "(r_aero + R_GEO) / 2", "(%s + %s) / 2"
               % (P(6378.14 + 100.0), P(W.R_GEO)), a_ae, "km",
               ["r_aero", "R_GEO"])
        v_a = math.sqrt(W.MU_EARTH * (2.0 / W.R_GEO - 1.0 / a_ae))
        S.step("v_aeroA", "v_a", "its apogee speed",
               "sqrt(mu_E (2 / R_GEO - 1 / a_aero))",
               "sqrt(%s * (2 / %s - 1 / %s))" % (P(W.MU_EARTH), P(W.R_GEO),
                                                  P(a_ae)),
               v_a, "km/s", ["mu_E", "R_GEO", "a_aero"])
        keys.append(circularise("capGEOa", v_a, "v_aeroA"))
    elif name == "ret_gto_prop":
        if "R_GEO" not in S.tag:
            S.put("R_GEO", "R_GEO", "geostationary radius", W.R_GEO, "km",
                  cite_here("R_GEO"))
        S.step("a_GTO", "a_GTO", "the GTO depot ellipse",
               "(r_LEO + R_GEO) / 2", "(%s + %s) / 2" % (P(W.R_LEO),
                                                         P(W.R_GEO)),
               W.A_GTO, "km", ["r_LEO", "R_GEO"])
        S.step("v_GTOp", "v_GTO,peri", "its perigee speed",
               "sqrt(mu_E (2 / r_LEO - 1 / a_GTO))",
               "sqrt(%s * (2 / %s - 1 / %s))" % (P(W.MU_EARTH), P(W.R_LEO),
                                                  P(W.A_GTO)),
               W.V_GTO_PERIGEE, "km/s", ["mu_E", "r_LEO", "a_GTO"])
        S.step("capGTO", "dv_cap,GTO", "capture: bind the GTO ellipse at "
               "perigee", "max(0, v_hyp - v_GTO,peri)",
               "max(0, %s - %s)" % (exact(leg["v_hyp"]),
                                    exact(W.V_GTO_PERIGEE)),
               leg["gto_capture"], "km/s", ["v_hyp", "v_GTOp"],
               "the depot IS the ellipse, so no apogee burn follows, and "
               "it sits in the plane its customers are launched into, so "
               "no plane change is charged")
        keys.append("capGTO")
    elif name == "ret_gto_aero":
        keys.append(const("dv_trim", "dv_trim", "periapsis raise after "
                          "aerocapture onto the GTO ellipse",
                          W.DV_AEROBRAKE_TRIM, "km/s", "DV_AEROBRAKE_TRIM",
                          "Charged at the Earth aerobrake trim."))
    elif name == "ret_earth_surface_aero":
        pass
    else:
        raise AssertionError("no derivation for the return leg %r" % name)
    return keys


def circularise_prep(S):
    """Register what `circularise_at_geo` reads before a step cites it."""
    if "R_GEO" not in S.tag:
        S.put("R_GEO", "R_GEO", "geostationary radius", W.R_GEO, "km",
              cite_here("R_GEO"))
    if "tilt" not in S.tag:
        S.put("tilt", "eps", "the ecliptic's tilt to the equator", 23.44,
              "deg", cite_here("COS_ECLIPTIC_TILT", "GEO is equatorial and an "
                               "asteroid arrives near the ecliptic, so the "
                               "capture buys this plane change too"))
    if "v_GEO" not in S.tag:
        S.step("v_GEO", "v_GEO", "circular speed at GEO",
               "sqrt(mu_E / R_GEO)",
               "sqrt(%s / %s)" % (P(W.MU_EARTH), P(W.R_GEO)), W.V_GEO,
               "km/s", ["mu_E", "R_GEO"])
    return "v_GEO"


# ------------------------------------------------- 3. getting there and back
def part_transfer(S, out):
    """The patched conic: departure, apsis match, arrival, floors, penalty."""
    C, DV = out["C"], out["DV"]
    leg = DV["aph"] if DV["apsis"] == "aphelion" else DV["peri"]
    S.part("transfer", "Getting there and back",
           "A patched conic.  Distances in AU, speeds in multiples of "
           "Earth's orbital velocity until the last line of each block.")
    a = S.put("a", "a", "semi-major axis", C["a_au"], "AU",
              cite_body(C, "semi_major_axis_au"))
    e = S.put("e", "e", "eccentricity", C["e"], "-",
              cite_body(C, "eccentricity"))
    inc = S.put("inc", "i", "inclination", C["inc"], "deg",
                cite_body(C, "inclination_deg"))
    S.step("Q", "Q", "aphelion", "a (1 + e)",
           "%s * (1 + %s)" % (P(a), P(e)), DV["Q_au"], "AU", ["a", "e"])
    S.step("q", "q", "perihelion", "a (1 - e)",
           "%s * (1 - %s)" % (P(a), P(e)), DV["q_au"], "AU", ["a", "e"])
    S.step("r_t", "r_t", "the apsis this transfer meets the target at",
           "%s, which the search chose" % ("Q" if DV["apsis"] == "aphelion"
                                           else "q"),
           P(DV["r_target"]), DV["r_target"], "AU", ["Q", "q"],
           "priced both ways, not ruled: %s costs %s km/s round trip "
           "against %s, a factor of %s"
           % (D.esc(DV["apsis"]),
              P(DV["aph_round"] if DV["apsis"] == "aphelion"
                else DV["peri_round"]),
              P(DV["peri_round"] if DV["apsis"] == "aphelion"
                else DV["aph_round"]),
              P(max(DV["aph_round"], DV["peri_round"])
                / min(DV["aph_round"], DV["peri_round"]), 4)))
    S.claim("%s / %s" % (P(max(DV["aph_round"], DV["peri_round"])),
                         P(min(DV["aph_round"], DV["peri_round"]))),
            max(DV["aph_round"], DV["peri_round"])
            / min(DV["aph_round"], DV["peri_round"]), "the apsis factor")
    S.step("a_t", "a_t", "transfer-ellipse semi-major axis", "(1 + r_t) / 2",
           "(1 + %s) / 2" % P(DV["r_target"]), leg["a_t"], "AU", ["r_t"],
           "1 AU out to r_t")

    S.prose("Departure: the hyperbolic excess, and the burn that buys it.")
    S.step("v_t", "v_t", "speed on the transfer ellipse at Earth's orbit",
           "sqrt(2 - 1 / a_t)", "sqrt(2 - 1 / %s)" % P(leg["a_t"]),
           leg["v_t"], "x v_E", ["a_t"])
    S.step("cos_i", "cos i", "the plane change, taken in the same burn",
           "cos(i)", "cos(%s deg)" % P(inc), leg["cos_i"], "-", ["inc"])
    S.step("vinf2", "v_inf^2", "hyperbolic excess, squared",
           "v_t^2 + 1 - 2 v_t cos i",
           # repr operands: the subtraction cancels three or four digits,
           # so twelve significant figures in did not give the result back.
           "%s + 1 - 2 * %s * %s"
           % (exact(leg["v_t"] ** 2), exact(leg["v_t"]), exact(leg["cos_i"])),
           leg["v_inf_sq"], "x v_E^2", ["v_t", "cos_i"],
           "the law of cosines against Earth's own velocity")
    S.step("v_inf", "v_inf", "hyperbolic excess", "sqrt(v_inf^2) * v_E",
           "sqrt(%s) * %s" % (P(leg["v_inf_sq"]), P(W.V_EARTH)),
           leg["v_inf"], "km/s", ["vinf2", "v_E"])
    S.step("v_LEO", "v_LEO", "circular speed in the parking orbit",
           "sqrt(mu_E / r_LEO)",
           "sqrt(%s / %s)" % (P(W.MU_EARTH), P(W.R_LEO)),
           leg["v_leo"], "km/s", ["mu_E", "r_LEO"])
    S.step("v_esc", "v_esc", "escape speed from the parking orbit",
           "sqrt(2) * v_LEO", "sqrt(2) * %s" % P(leg["v_leo"]),
           leg["v_esc"], "km/s", ["v_LEO"])
    S.step("v_hyp", "v_hyp", "speed needed at perigee to leave on that "
                             "hyperbola", "sqrt(v_esc^2 + v_inf^2)",
           "sqrt(%s + %s)" % (P(leg["v_esc"] ** 2), P(leg["v_inf"] ** 2)),
           leg["v_hyp"], "km/s", ["v_esc", "v_inf"])
    S.step("dv_dep", "dv_dep", "the departure burn", "v_hyp - v_LEO",
           "%s - %s" % (P(leg["v_hyp"]), P(leg["v_leo"])),
           leg["depart"], "km/s", ["v_hyp", "v_LEO"])

    S.prose("Matching the target at the apsis.")
    S.step("v_ast", "v_ast", "the target, at r_t", "sqrt(2 / r_t - 1 / a)",
           "sqrt(2 / %s - 1 / %s)" % (exact(DV["r_target"]), exact(a)),
           leg["v_ast"], "x v_E", ["r_t", "a"])
    S.step("v_tr", "v_tr", "the spacecraft, at r_t",
           "sqrt(2 / r_t - 1 / a_t)",
           "sqrt(2 / %s - 1 / %s)" % (exact(DV["r_target"]),
                                      exact(leg["a_t"])),
           leg["v_tr"], "x v_E", ["r_t", "a_t"])
    S.step("dv_match", "dv_match", "the match burn",
           "|v_ast - v_tr| * v_E",
           "|%s - %s| * %s" % (exact(leg["v_ast"]), exact(leg["v_tr"]),
                               P(W.V_EARTH)),
           leg["match"], "km/s", ["v_ast", "v_tr", "v_E"],
           "the two speeds are given exactly: for a body whose orbit the "
           "transfer nearly matches, this subtraction CANCELS digits, and "
           "the rounded values above then miss the burn")
    S.step("dv_out_raw", "dv_out,raw", "outbound, before floor and penalty",
           "dv_dep + dv_match",
           "%s + %s" % (P(leg["depart"]), P(leg["match"])),
           DV["raw_out"] / 1000.0, "km/s", ["dv_dep", "dv_match"])

    S.prose("The return.  Only the arrival differs by destination; this "
            "mission flies <b>%s</b>, and every burn in it is worked out "
            "below." % D.esc(C["return_leg"]))
    keys = return_leg_steps(S, out, leg)
    S.step("dv_ret_raw", "dv_ret,raw", "return, before floor and penalty",
           "the burns of this leg, added",
           " + ".join(P(S.value[k]) for k in keys),
           DV["raw_ret"] / 1000.0, "km/s", keys)

    S.prose("The floors come BEFORE the penalty: a body cheap enough to "
            "reach pays floor x penalty, not its own value x penalty.")
    lam = S.put("lambda", "lambda_LT", "low-thrust delta-v penalty",
                C["dv_penalty"], "x",
                cite_table_row(C["pro"], "propellants.csv",
                               C["pro"].raw("name"),
                               ("dv_penalty_factor", "thrust_scaling")))
    # Literals in the model, not table rows: cited to the function that
    # applies them, which is where a reader would go to check them.
    S.put("floor_out", "floor_out", "outbound delta-v floor", DV["floor_out"],
          "m/s", "<b>modules/calc.py</b>, <i>asteroid_dv_options</i>: "
          "<span class='src'>the outbound leg is floored before anything "
          "else touches it, the same floor <i>derive_dv</i> applies "
          "here.</span>")
    S.put("floor_ret", "floor_ret", "return delta-v floor", DV["floor_ret"],
          "m/s", "<b>modules/calc.py</b>, <i>asteroid_dv_options</i>: "
          "<span class='src'>the return leg's floor, applied the same "
          "way.</span>")
    S.put("dv_ceil", "dv_max", "delta-v ceiling", DV["ceiling"], "m/s",
          cite_config("max_dv_outbound_m_s"))
    S.step("dv_out", "dv_out", "outbound delta-v, as flown",
           "min(max(dv_out,raw, floor_out), dv_max) * lambda_LT",
           "min(max(%s, %s), %s) * %s"
           % (P(DV["raw_out"]), P(DV["floor_out"]), P(DV["ceiling"]), P(lam)),
           DV["dv_out"], "m/s",
           ["dv_out_raw", "floor_out", "dv_ceil", "lambda"])
    S.step("dv_ret", "dv_ret", "return delta-v, as flown",
           "min(max(dv_ret,raw, floor_ret), dv_max) * lambda_LT",
           "min(max(%s, %s), %s) * %s"
           % (P(DV["raw_ret"]), P(DV["floor_ret"]), P(DV["ceiling"]), P(lam)),
           DV["dv_ret"], "m/s",
           ["dv_ret_raw", "floor_ret", "dv_ceil", "lambda"])


# ------------------------------------------- 4. the propellant and the tank
def part_ratios(S, out):
    """Exhaust velocity, the two mass ratios, the tank factors, the budget."""
    C, DV, M = out["C"], out["DV"], out["M"]
    R = M["R"]
    pro_name = str(C["pro"].raw("name"))
    S.part("ratios", "The propellant, the tank and the launch budget",
           "%s is built from these numbers and the vehicle's capacity."
           % ref("fixed_point", "Part"))
    isp = S.put("isp", "I_sp", "%s specific impulse" % pro_name, C["isp"], "s",
                cite_table_row(C["pro"], "propellants.csv", pro_name,
                               ("type", "status", "trl", "reference_year")))
    # The run's own value, read off the row; zero means the run did not
    # charge tankage (`model_tank_mass` off), and the citation then says so
    # rather than deriving a ratio the run never applied.
    if C["tank_frac"] > 0:
        tank_how = ("Module 3 derives it as <i>tank_kg_per_L</i> / "
                    "<i>density_kg_per_L</i> = %s / %s for the <i>%s</i> "
                    "storage class.  "
                    % (P(C["pro"].raw("tank_kg_per_L")),
                       P(C["pro"].raw("density_kg_per_L")),
                       D.esc(C["storage_class"])))
    else:
        tank_how = ("Zero: this run did not charge tankage "
                    "(<i>model_tank_mass</i> off), so every k below is 1.  ")
    S.put("tank_frac", "t", "tank mass per kg of propellant", C["tank_frac"],
          "kg/kg",
          "<b>profitability_catalog</b>, column <i>tank_mass_frac</i> on "
          "this row, which is the run's own value.  " + tank_how
          + cite_table_row(C["pro"], "propellants.csv", pro_name,
                           ("storage_class",)))
    cap = S.put("M_LEO", "M_LEO", "%s payload to LEO"
                % str(C["veh"].raw("name")), C["leo_cap"], "kg",
                cite_table_row(C["veh"], "launch_vehicles.csv",
                               C["veh"].raw("name"),
                               ("operator", "status", "reference_year")))
    S.step("ve", "v_e", "exhaust velocity", "I_sp * g_0",
           "%s * %s" % (P(isp), P(W.G0)), C["ve"], "m/s", ["isp", "g0"])
    S.step("R_out", "R_out", "outbound mass ratio", "exp(dv_out / v_e)",
           "exp(%s / %s)" % (P(DV["dv_out"]), P(C["ve"])),
           R["R_out"], "-", ["dv_out", "ve"])
    if M["boiloff_factor"] != 1.0:
        # This step's substitution read "as the model associates it" and
        # cited only dv_ret: a formula with no numbers in it, on the one
        # cryogenic line a reader could not otherwise check.
        S.put("boil_rate", "beta", "%s boil-off rate" % pro_name,
              C["boiloff_pct"], "% per day",
              cite_table_row(C["pro"], "propellants.csv", pro_name,
                             ("boiloff_pct_per_day", "storage_class")))
        S.step("t_out_hold", "t_out", "outbound transfer, the first half of "
               "the hold", "max(0.5, tau_fit * dv_out)",
               "max(0.5, %s * %s)" % (P(W.TAU_CRUISE_FIT_YR_PER_M_S),
                                      P(DV["dv_out"])),
               M["boiloff_outbound_yr"], "yr", ["tau", "dv_out"])
        # Worked from its two operands rather than printed: the previous
        # pass's dig plus the window wait, or on the first pass the floor
        # plus the wait.  Both are derived later on the page, so they are
        # registered here as quantities derived on this page, citing where.
        passes = M["passes"]
        wait = out["DV"]["window_wait"]
        prev = passes[-2]["dig"] if len(passes) >= 2 else None
        if prev is not None and prev + wait == M["boiloff_stay_yr"]:
            first, first_sym, first_what, first_src = (
                prev, "t_dig,prev", "the dig the previous pass sized",
                "the previous pass's row of the fixed point's table in %s"
                % ref("fixed_point"))
        elif (C["cfg"].station_keeping_floor_yr + wait
              == M["boiloff_stay_yr"]):
            first, first_sym, first_what, first_src = (
                C["cfg"].station_keeping_floor_yr, "t_floor",
                "the station-keeping floor, which is the first pass's stay",
                cite_config("station_keeping_floor_yr"))
        else:
            raise AssertionError("the stay estimate %r is neither the "
                                 "previous dig plus the wait nor the floor "
                                 "plus the wait" % M["boiloff_stay_yr"])
        S.put("stay_dig", first_sym, first_what, first, "yr",
              first_src if first_sym == "t_floor" else
              "<b>Derived on this page</b>: " + first_src)
        S.put("stay_wait", "t_wait", "the launch-window wait", wait, "yr",
              "<b>Derived on this page</b>: half the synodic period, worked "
              "out in %s" % ref("clock"))
        S.step("stay_hold", "t_stay,est", "the stay the converging pass "
               "assumed", "%s + t_wait" % first_sym,
               "%s + %s" % (P(first), P(wait)), M["boiloff_stay_yr"], "yr",
               ["stay_dig", "stay_wait"],
               "where the propellant is still sitting in its tank")
        S.step("hold_yr", "t_hold", "how long the return propellant sits "
               "in its tank", "t_out + t_stay,est",
               "%s + %s" % (P(M["boiloff_outbound_yr"]),
                            P(M["boiloff_stay_yr"])),
               M["boiloff_hold_yr"], "yr", ["t_out_hold", "stay_hold"])
        S.step("boil", "b", "boil-off inflation over the hold",
               "exp(beta / 100 * t_hold * 365.25)",
               "exp(%s / 100 * %s * 365.25)" % (P(C["boiloff_pct"]),
                                                P(M["boiloff_hold_yr"])),
               M["boiloff_factor"], "-", ["boil_rate", "hold_yr"])
        S.step("R_ret", "R_ret", "return mass ratio, boil-off included",
               "1 + (exp(dv_ret / v_e) - 1) * b",
               "1 + (exp(%s / %s) - 1) * %s"
               % (P(DV["dv_ret"]), P(C["ve"]), P(M["boiloff_factor"])),
               R["R_ret"], "-", ["dv_ret", "ve", "boil"])
    else:
        S.step("R_ret", "R_ret", "return mass ratio", "exp(dv_ret / v_e)",
               "exp(%s / %s)" % (P(DV["dv_ret"]), P(C["ve"])),
               R["R_ret"], "-", ["dv_ret", "ve"])
    S.step("k_out", "k_out", "the outbound tank, folded into the mass ratio",
           "1 / (1 - t (R_out - 1))",
           "1 / (1 - %s * (%s - 1))" % (P(R["t"]), P(R["R_out"])),
           R["k_out"], "-", ["tank_frac", "R_out"],
           "t (R - 1) >= 1 would mean the tank cannot close and the "
           "combination is infeasible rather than merely expensive")
    S.step("k_ret", "k_ret", "the return tank, folded in the same way",
           "1 / (1 - t (R_ret - 1))",
           "1 / (1 - %s * (%s - 1))" % (P(R["t"]), P(R["R_ret"])),
           R["k_ret"], "-", ["tank_frac", "R_ret"])
    S.step("budget", "budget", "what may arrive at the asteroid",
           "M_LEO / (k_out R_out)",
           "%s / (%s * %s)" % (P(cap), P(R["k_out"]), P(R["R_out"])),
           R["budget"], "kg", ["M_LEO", "k_out", "R_out"],
           "ore excluded: this is the stack before anything is loaded")


# ---------------------------------------------------- 5. the plant's rating
def part_plant_rating(S, out):
    """Specific power for a plant that stands in the body's shadow.

    Payload-independent, so it is settled before the fixed point rather than
    inside it: only the DRAW moves as the loop iterates, not the W/kg.
    """
    C = out["C"]
    S.part("plant", "What a watt of plant weighs",
           "None of this depends on the payload, so it is settled before "
           "the fixed point; only the draw moves as the loop iterates.")
    # 🚨  THE SOLAR CHAIN IS WORKED OUT ON AN RTG MISSION TOO.  The RTG
    # branch used to return before it, printing the radioisotope figure
    # beside the SOLAR derate as its value (5 against 1.457 on 2006 UE63),
    # and leaving `w_bare` unregistered for the cruise array, which flies
    # panels whatever powers the rig.  The solar figure is also what the
    # radioisotope plant was chosen against, so a reader needs it either way.
    rtg = C["power_source"] == "rtg"
    final = "w_solar" if rtg else "w_plant"
    final_sym = "w_solar" if rtg else "w_plant"
    final_what = ("what a solar plant would give here" if rtg
                  else "plant specific power")
    w1 = S.put("w_1AU", "w_1AU", "array specific power, rated at 1 AU",
               C["w_1au"], "W/kg", cite_ops(C, "Power system specific mass"))
    if 0.1 < C["a_au"] < 100.0:
        S.step("w_bare", "w_bare", "the same array, at this body's distance",
               "w_1AU / a^2", "%s / %s ^ 2" % (P(w1), P(C["a_au"])),
               C["w_bare"], "W/kg", ["w_1AU", "a"],
               "sunlight falls off as the square of the distance")
    else:
        S.step("w_bare", "w_bare", "the same array, at this body's distance",
               "w_1AU: outside 0.1 < a < 100 AU the model falls back to the "
               "1 AU rating", P(w1), C["w_bare"], "W/kg", ["w_1AU", "a"],
               "calc's solar_specific_power_w_per_kg, which refuses to "
               "price power off a distance it calls absurd")
    if C["oversize"] == 1.0:
        S.step(final, final_sym, final_what,
               "w_bare: the night-side term is off on this run",
               "%s" % P(C["w_bare"]), C["w_plant"], "W/kg", ["w_bare"])
        rtg_plant(S, C)
        return
    f = S.put("dark_frac", "f_dark", "fraction of the cycle in shadow",
              C["dark_frac"], "-",
              cite_ops(C, "Eclipse / night-side dark fraction"))
    eta = S.put("eta_store", "eta_store", "storage round-trip efficiency",
                C["storage_eff"], "-",
                cite_ops(C, "Energy storage round-trip efficiency"))
    e_store = S.put("e_store", "e_store", "storage usable specific energy",
                    C["storage_wh_per_kg"], "Wh/kg",
                    cite_ops(C, "Energy storage usable specific energy"))
    base = S.put("dark_base", "dark_0", "dark period the 1 AU rating "
                 "already carries", C["baseline_dark_h"], "h",
                 cite_ops(C, "Power-system row baseline dark period"))
    S.put("rot", "P_rot", "rotation period", C["rot_h"], "h",
          cite_body(C, "rotation_period_h",
                    "Measured." if C["rot_measured"]
                    else "NOT measured: the catalog median is used.")
          + ("  " + cite_config("default_rotation_period_h")
             if not C["rot_measured"] else ""))
    S.put("dark_max", "dark_max", "ceiling on the modelled night",
          C["max_dark_h"], "h", cite_config("max_dark_period_h"))
    S.step("dark_h", "dark_h", "the night, as modelled",
           "min(P_rot / 2, dark_max)",
           "min(%s / 2, %s)" % (P(C["rot_h"]), P(C["max_dark_h"])),
           C["dark_h"], "h", ["rot", "dark_max"],
           "half a rotation, capped: a slow rotator would otherwise buy a "
           "battery sized for a week of darkness")
    S.step("oversize", "oversize", "how much bigger the array has to be",
           "((1 - f) + f / eta) / (1 - f)",
           "((1 - %s) + %s / %s) / (1 - %s)" % (P(f), P(f), P(eta), P(f)),
           C["oversize"], "-", ["dark_frac", "eta_store"],
           "sunlit hours run the load AND recharge the store, lossily.  "
           "Written term by term: cancelling gives a different float")
    excess = max(0.0, C["dark_h"] - max(0.0, C["baseline_dark_h"]))
    S.step("excess_h", "excess_h", "storage this body needs beyond the rating",
           "max(0, dark_h - dark_0)",
           "max(0, %s - %s)" % (P(C["dark_h"]), P(C["baseline_dark_h"])),
           excess, "h", ["dark_h", "dark_base"],
           "an INCREMENT: charging the whole night would buy the rating's "
           "own battery twice")
    kg_per_w = C["oversize"] / C["w_bare"] + excess / C["storage_wh_per_kg"]
    S.step("kg_per_w", "kg/W", "plant mass per watt",
           "oversize / w_bare + excess_h / e_store",
           "%s / %s + %s / %s" % (P(C["oversize"]), P(C["w_bare"]),
                                  P(excess), P(C["storage_wh_per_kg"])),
           kg_per_w, "kg/W", ["oversize", "w_bare", "excess_h", "e_store"])
    S.step(final, final_sym, final_what, "1 / (kg/W)",
           "1 / %s" % P(kg_per_w), C["w_plant"], "W/kg", ["kg_per_w"],
           "the night side costs a factor of %s, which is the bare "
           "array's %s / %s"
           % (P(C["w_bare"] / C["w_plant"], 3), P(C["w_bare"]),
              P(C["w_plant"])))
    S.claim("%s / %s" % (P(C["w_bare"]), P(C["w_plant"])),
            C["w_bare"] / C["w_plant"], "the night-side factor")
    rtg_plant(S, C)


def rtg_plant(S, C):
    """On a radioisotope mission, the plant specific power the rig flies."""
    if C["power_source"] != "rtg":
        return
    S.put("w_rtg", "w_RTG", "radioisotope specific power",
          C["plant_w_per_kg"], "W/kg", cite_ops(C, "RTG specific power"))
    S.step("w_plant", "w_plant", "plant specific power",
           "w_RTG, flat: a radioisotope source does not care how far out it "
           "is, or whether the sun is up", P(C["plant_w_per_kg"]),
           C["plant_w_per_kg"], "W/kg", ["w_rtg", "w_solar"],
           "against the %s W/kg a solar plant would give here; the search "
           "chose the radioisotope one" % P(C["w_plant"]))


# ------------------------------------------------------ 6. the fixed point
def part_fixed_point(S, out):
    """The payload solve, which is circular and is iterated to a fixed point."""
    C, M, B = out["C"], out["M"], out["B"]
    cas, R = M["cascade"], M["R"]
    S.part("fixed_point", "The mass cascade, and the fixed point it is solved by",
           "Payload is solved for, not specified, and the solve is "
           "circular: payload sets feed, feed sets the draw, the draw sets "
           "the plant, and the plant comes out of the payload budget.")
    S.put("m_rig", "m_rig", "mining hardware mass",
          C["cfg"].mining_hardware_kg, "kg",
          cite_config("mining_hardware_kg"))
    S.put("d0", "d_0", "return-vehicle dry-mass floor",
          C["cfg"].return_vehicle_dry_kg, "kg",
          cite_config("return_vehicle_dry_kg"))
    S.put("f_str", "f_str", "ore restraint per kg of payload",
          C["cfg"].return_structure_frac_of_payload, "-",
          cite_config("return_structure_frac_of_payload"))
    S.put("c_seal", "c_seal", "volatile containment per kg of water",
          C["contain_per_kg"], "kg/kg",
          cite_ops(C, "Volatile cargo containment"))

    S.prose("Each pass solves the closed form at the PREVIOUS pass's "
            "hardware mass and containment fraction, then re-sizes both on "
            "the payload that came out.  The loop runs until they stop "
            "moving.  <b>Every column is one of the formulae worked out "
            "below, evaluated at that row's own hardware and f</b>: the "
            "payload by the closed form (coef, denom, bracket, m_pay), the "
            "EP stage by the three masses in " + ref("settled")
            + ", the plant by P / "
            "w_plant, the feed by its own min().")
    # Every cell at the precision the steps print, because the last row IS
    # those steps: at ten figures its hardware read 7,322.137193 beside a
    # step's 7,322.1371932, one number spelled two ways.
    rows = [[str(p["n"]), P(p["hw_in"]), P(p["f_used"]), P(p["m_pay"]),
             P(p["ep"]), P(p["plant"]), P(p["feed"]), P(p["dig"])]
            for p in M["passes"]]
    S.block(D.table(["pass", "hardware in (kg)", "structure frac",
                     "payload out (kg)", "EP stage (kg)", "plant (kg)",
                     "feed (kg)", "dig (yr)"], rows, "wide"),
            rerun=rerun_pass())
    S.prose("<b>The cascade is not re-solved once the loop converges.</b>  "
            "The payload carried forward is the last one solved INSIDE the "
            "loop, at the previous pass's hardware.  That is the model's "
            "own behaviour, and it is why the launch mass lands under the "
            "vehicle rather than on it; " + ref("stack")
            + " closes the difference.")
    if M.get("backoffs"):
        # calc v1.28.0, `damp_sizing_loop`: the passes whose stack did not
        # close, and the step the loop backed off to after each.
        S.prose("<b>The loop backed off.</b>  A pass after the first whose "
                "stack did not close moved the state back toward the one the "
                "last closing pass was solved at, by the step below, instead "
                "of refusing; the passes after it are solved at that blend, "
                "b + step (t - b) term by term, where b is the state a pass "
                "was solved at and t the sizing it computed.  A damped loop "
                "must settle, or the model refuses it.")
        S.block(D.table(["after pass", "hardware tried (kg)",
                         "why it did not close", "step now"],
                        [[str(b["n"]), P(b["hw_tried"]), b["why"],
                          P(b["step"])] for b in M["backoffs"]], "wide"),
                rerun=rerun_pass())

    # calc v1.28.0: the state the last pass was SOLVED at.  That is the
    # previous pass's sizing taken whole, unless the loop had to back off, in
    # which case it is a blend of two passes' sizing and the back-off table
    # below says which.
    last = M["passes"][-1]
    prev = M["passes"][-2] if len(M["passes"]) > 1 else None
    blended = last.get("step", 1.0) < 1.0
    with_ref = prev is not None and last.get("refinery_in", 0.0) > 0
    # calc v1.32.0: the ISRU plant, at the propellant and stay that pass ran at.
    with_iplant = prev is not None and last.get("isru_plant_in", 0.0) > 0
    S.step("hw_solved", "m_hw,solved", "the hardware the last solve ran at",
           "m_rig + plant + EP stage%s%s, %s"
           % (" + refinery" if with_ref else "",
              " + ISRU plant" if with_iplant else "",
              "%s of the way from the state the previous pass was solved "
              "at to the sizing it computed" % P(last["step"]) if blended
              else "at the PREVIOUS pass"),
           (" + ".join(P(v) for v in
                       [C["cfg"].mining_hardware_kg, last["plant_in"],
                        last["ep_in"]]
                       + ([last["refinery_in"]] if with_ref else [])
                       + ([last["isru_plant_in"]] if with_iplant else []))
            if prev is not None else P(last["hw_in"])),
           M["hw_solved"], "kg", ["m_rig"],
           "the last row's 'hardware in' column above, and NOT the "
           "hardware the mission actually flies; %s is built on that"
           % ref("stack"))
    S.step("f_solved", "f_solved", "the structure fraction it ran at",
           "f_str + c_frac, at the previous pass",
           "%s + %s" % (P(C["cfg"].return_structure_frac_of_payload),
                        P(M["f_solved"]
                          - C["cfg"].return_structure_frac_of_payload)),
           M["f_solved"], "-", ["f_str", "c_seal"])
    if C["tps_frac"] > 0:
        S.put("tps_frac", "tps_frac", "heat shield per kg of returned "
              "stack", C["tps_frac"], "-",
              cite_config("heat_shield_frac_of_payload"))
    else:
        S.put("tps_frac", "tps_frac", "heat shield per kg of returned "
              "stack", 0.0, "-",
              "<b>Derived on this page</b>: zero, because this mission "
              "returns propulsively and carries no heat shield; the "
              "<i>heat_shield_frac_of_payload</i> dial applies only to an "
              "aerocaptured return.")
    S.step("s_tps", "s_TPS", "the heat-shield multiplier on the whole "
           "returned stack", "1 + tps_frac",
           "1 + %s" % P(C["tps_frac"]), cas["s_tps"], "-", ["tps_frac"],
           "exactly 1.0 on a propulsive return, and then not one float of "
           "the cascade differs from the untps case" if C["tps_frac"] == 0
           else "the shield is hauled out and pushed back with everything "
           "it protects")
    S.step("coef", "coef", "the returning stack's multiplier",
           ("k_ret * s_TPS" if C["isru"] else "k_ret * s_TPS * R_ret"),
           ("%s * %s" % (P(R["k_ret"]), P(cas["s_tps"]))
            if C["isru"] else
            "%s * %s * %s" % (P(R["k_ret"]), P(cas["s_tps"]),
                              P(R["R_ret"]))),
           cas["coef"], "-", ["k_ret", "s_tps"] + ([] if C["isru"]
                                                   else ["R_ret"]),
           "carried propellant rides the outbound burn as dead mass: that "
           "is the one factor of R_ret separating the two forms")
    S.step("denom", "denom", "the denominator of the closed form",
           "coef (1 + f) - 1",
           "%s * (1 + %s) - 1" % (P(cas["coef"]), P(cas["struct_frac"])),
           cas["denom"], "-", ["coef", "f_solved"])
    S.step("bracket", "bracket", "the numerator of the closed form",
           "budget - m_hw - coef * d_0",
           "%s - %s - %s * %s" % (P(R["budget"]), P(cas["hardware_kg"]),
                                  P(cas["coef"]), P(cas["d0"])),
           cas["bracket"], "kg", ["budget", "hw_solved", "coef", "d0"])
    rep = M.get("repair")
    if not rep:
        S.step("m_pay_cf", "m_pay,cf", "the closed form's payload",
               "bracket / denom",
               "%s / %s" % (P(cas["bracket"]), P(cas["denom"])),
               cas["m_pay"], "kg", ["bracket", "denom"],
               "what the rocket equation can carry; %s holds it to the "
               "physical ceilings" % ref("settled"))
        return
    # calc v1.27.0, `repair_settled_overshoot`.  The first settle-up flew a
    # stack over the vehicle, so the payload was re-solved at the hardware
    # that stack settled on and the mission priced again under that ceiling.
    # The ceiling is the same closed form at that attempt's hardware and
    # structure fraction, so it is stepped here rather than asserted.
    fit = rep["refit"]
    S.step("m_pay_cf", "m_pay,cf", "the closed form's payload",
           "bracket / denom",
           "%s / %s" % (P(cas["bracket"]), P(cas["denom"])),
           cas["m_pay"], "kg", ["bracket", "denom"])
    S.put("m_launch_1", "m_launch,1", "the first settle-up's launch stack",
          rep["m_launch"], "kg",
          "<b>Derived on this page</b>: %s at the payload the "
          "first solve carried, %s kg, which put the stack over the "
          "vehicle's %s kg.  The run records how many times it re-solved as "
          "<b>profitability_catalog</b> &middot; column "
          "<i>settle_repairs</i>." % (refs("fixed_point", "stack"),
                                      P(rep["m_pay"]), P(C["leo_cap"])))
    S.put("hw_1", "m_hw,1", "the hardware that stack settled on",
          rep["hw"], "kg",
          "<b>Derived on this page</b>: the settled hardware of %s, for "
          "that first attempt." % ref("stack"))
    S.put("f_1", "f_1", "the structure fraction it settled on",
          rep["f_eff"], "-",
          "<b>Derived on this page</b>: the ore restraint plus seal of "
          "%s, for that first attempt." % ref("settled"))
    S.put("coef_1", "coef_1", "the returning stack's multiplier then",
          fit["coef"], "-",
          "<b>Derived on this page</b>: the first attempt's "
          "k_ret * s_TPS%s." % ("" if C["isru"] else " * R_ret"))
    S.step("bracket_cap", "bracket_cap", "the numerator at that hardware",
           "budget - m_hw,1 - coef_1 * d_0",
           "%s - %s - %s * %s" % (P(rep["budget"]), P(rep["hw"]),
                                  P(fit["coef"]), P(fit["d0"])),
           fit["bracket"], "kg", ["budget", "hw_1", "coef_1", "d0"])
    S.step("denom_cap", "denom_cap", "the denominator at that hardware",
           "coef_1 (1 + f_1) - 1",
           "%s * (1 + %s) - 1" % (P(fit["coef"]), P(rep["f_eff"])),
           fit["denom"], "-", ["coef_1", "f_1"])
    S.step("m_cap", "m_cap", "the payload that fits at that hardware",
           "bracket_cap / denom_cap",
           "%s / %s" % (P(fit["bracket"]), P(fit["denom"])),
           fit["m_pay"], "kg", ["bracket_cap", "denom_cap", "m_launch_1"],
           "the ceiling the mission is priced again under")
    S.step("m_fit", "m_pay,fit", "the payload the stack can carry",
           "min(m_pay,cf, m_cap)",
           "min(%s, %s)" % (P(cas["m_pay"]), P(fit["m_pay"])),
           min(cas["m_pay"], fit["m_pay"]), "kg", ["m_pay_cf", "m_cap"],
           "%s holds it to the physical ceilings" % ref("settled"))


# ------------------------------------------------- 7. the settled mission
def part_settled(S, out):
    """Feed, water, the seal, the power draw, the plant and the EP stage."""
    C, M, B = out["C"], out["M"], out["B"]
    cas = M["cascade"]
    S.part("settled", "The feed, the water and the power it takes",
           "Settled on the payload the last solve produced.")
    rate_rig = S.put("gamma", "gamma", "mining rate per kg of rig",
                     C["cfg"].mining_rate_kg_per_day_per_kg_rig,
                     "kg/day per kg of rig",
                     cite_config("mining_rate_kg_per_day_per_kg_rig"))
    t_max = S.put("t_max", "t_dig,max", "the longest dig the model allows",
                  C["cfg"].max_mining_duration_yr, "yr",
                  cite_config("max_mining_duration_yr"))
    S.step("rate", "rate", "rig throughput", "m_rig * gamma * 365.25",
           "%s * %s * 365.25" % (P(C["cfg"].mining_hardware_kg), P(rate_rig)),
           C["rate_kg_yr"], "kg/yr", ["m_rig", "gamma"])
    S.step("throughput", "throughput", "all the rig can move in one stay",
           "rate * t_dig,max",
           "%s * %s" % (P(C["rate_kg_yr"]), P(t_max)),
           M["throughput"], "kg", ["rate", "t_max"])
    S.put("V_fair", "V_fair", "fairing volume", C["fairing_m3"], "m3",
          (cite_table_row(C["veh"], "launch_vehicles.csv",
                          C["veh"].raw("name"))
           + ".  The row gives no fairing volume, so this is the model's "
             "default, <b>modules/calc.py</b>, "
             "<i>DEFAULT_FAIRING_VOLUME_M3</i>")
          if C.get("fairing_assumed") else
          cite_table_row(C["veh"], "launch_vehicles.csv",
                         C["veh"].raw("name"), ("fairing_volume_m3",)))
    S.step("vol_cap", "vol_cap", "what the hold can physically carry",
           "0.25 * V_fair * 1000 * rho",
           "0.25 * %s * 1000 * %s" % (P(C["fairing_m3"]), P(C["rho"])),
           M["vol_cap"], "kg", ["V_fair", "rho"],
           "a quarter of the fairing, at the ore's bulk density")
    # The payload FLOWN.  Part 6 ends on what the rocket equation can carry;
    # the model then takes the smallest of that and three physical ceilings
    # (`_evaluate_combo_at_ratio`'s settle-up: what the body allows, what the
    # hold holds and, on run-of-mine ore only, what the rig can dig in a
    # stay).  This step used to be missing, so a raw mission whose dig
    # clipped the payload printed "feed = m_pay" beside the closed form's
    # number and a feed a third smaller.  ISRU feed comes off the body and
    # the rig before any ore is loaded, which is why both carry it.
    cf_key = "m_fit" if M.get("repair") else "m_pay_cf"
    cf_sym = "m_pay,fit" if M.get("repair") else "m_pay,cf"
    cf_val = M["repair"]["refit"]["m_pay"] if M.get("repair") else cas["m_pay"]
    if M.get("repair"):
        cf_val = min(cas["m_pay"], cf_val)
    isru = bool(C["isru"])
    if C["beneficiated"] or (isru and C["isru_water_per_kg_prop"] > 0):
        S.put("eps_rec", "eps_rec", "separation recovery",
              C["recovery"], "-", cite_config("beneficiation_recovery"))
    water_in = C.get("phased")
    if (not C["beneficiated"]) or (isru and C["isru_water_per_kg_prop"] > 0):
        # The body's WATER fraction, which the raw hold and a water-fed ISRU
        # plant both read.  It was spent unregistered: "m_pay * f_ice" with
        # no f_ice anywhere on the page.
        S.put("f_water", "f_water", "the body's water fraction", C["ice_frac"],
              "-",
              cite_body(C, (C.get("phases_col") or "comp_phases")
                        if water_in else "comp_ice_fraction",
                        "its water entry, the water phase alone"
                        if water_in else "the ice fraction"))
    if isru:
        # 🚨  THIS WAS ONE INPUT, "Derived on this page", WITH NO STEP BEHIND
        # IT.  Propellant made on site is dug as rock, and how much rock a
        # kilogram of it takes is a Module 3 row and, for water, the body.
        material = str(C["pro"].raw("isru_feed_material") or "").strip()
        ratio = float(C["pro"].raw("isru_feed_kg_per_kg") or 0.0)
        S.put("k_isru", "k_ISRU", "%s per kg of propellant made on site"
              % ("water" if material == "water" else "rock"), ratio,
              "kg/kg",
              cite_table_row(C["pro"], "propellants.csv",
                             C["pro"].raw("name"),
                             ("isru_feed_material", "isru_feed_kg_per_kg")))
        if material == "water":
            S.step("k_feed", "k_feed", "rock dug per kg of propellant made",
                   "k_ISRU / (f_water * eps_rec)",
                   "%s / (%s * %s)" % (P(ratio), P(C["ice_frac"]),
                                       P(C["recovery"])),
                   C["isru_feed_per_kg_prop"], "kg/kg",
                   ["k_isru", "f_water", "eps_rec"],
                   "only the water is propellant, and only eps_rec of it "
                   "is recovered, so the rock is the water's multiple")
        else:
            S.step("k_feed", "k_feed", "rock dug per kg of propellant made",
                   "k_ISRU: the propellant IS bulk rock", P(ratio),
                   C["isru_feed_per_kg_prop"], "kg/kg", ["k_isru"])
        S.put("m_isru_loop", "m_rprop,loop", "propellant the converging "
              "pass made on site", M["isru_prop_loop"], "kg",
              "<b>Derived on this page</b>: the return propellant the last "
              "pass of the fixed point in %s sized, which is what the "
              "payload below was netted against." % ref("fixed_point"))
        S.step("f_isru", "f_ISRU,loop", "rock that pass dug for it",
               "m_rprop,loop * k_feed",
               "%s * %s" % (P(M["isru_prop_loop"]),
                            P(C["isru_feed_per_kg_prop"])),
               M["isru_feed_loop"], "kg", ["m_isru_loop", "k_feed"],
               "it comes off the body and the rig before any ore is loaded")
    loop_feed = M["isru_feed_loop"] if isru else 0.0
    sub_isru = ((lambda name: "%s - f_ISRU,loop" % name) if isru
                else (lambda n: n))
    num_isru = ((lambda v: "max(0, %s - %s)" % (P(v), P(loop_feed)))
                if isru else (lambda v: P(v)))
    terms = [cf_sym, sub_isru("m_min"), "vol_cap"]
    nums = [P(cf_val), num_isru(B["mineable"]), P(M["vol_cap"])]
    uses = [cf_key, "m_min", "vol_cap"]
    if not C["beneficiated"]:
        terms.append(sub_isru("throughput"))
        nums.append(num_isru(M["throughput"]))
        uses.append("throughput")
    if isru:
        uses.append("f_isru")
    _caps, binds = payload_caps(out)
    S.step("m_pay", "m_pay", "the payload flown",
           "min(%s)" % ", ".join(terms), "min(%s)" % ", ".join(nums),
           M["m_pay"], "kg", uses,
           "the model's max_payload_kg; here the %s sets it"
           % " and the ".join(binds)
           + ("" if C["beneficiated"] else
              ".  On run-of-mine ore the dig caps the payload itself, where "
              "concentrating lets it cap only the feed"))
    pay = M["m_pay"]

    if C["beneficiated"]:
        S.put("ratio", "r", "concentration ratio", out["ratio"], "-",
              "<b>Derived on this page</b>, by the sweep in "
              + ref("searches") + "; not a "
              "setting.  Grade saturates while the costs do not, so the "
              "optimum is interior and is found by pricing the rungs.  The "
              "run records it as <b>profitability_catalog</b> &middot; "
              "column <i>concentration_ratio</i>.")
        thr = max(0.0, M["throughput"] - loop_feed)
        mine = max(0.0, B["mineable"] - loop_feed)
        S.step("feed", "feed", "rock dug and processed",
               "max(min(m_pay * r, %s, %s), m_pay)"
               % (sub_isru("throughput"), sub_isru("m_min")),
               "max(min(%s * %s, %s, %s), %s)"
               % (P(pay), P(out["ratio"]), num_isru(M["throughput"]),
                  num_isru(B["mineable"]), P(pay)),
               M["feed"], "kg", ["m_pay", "ratio", "throughput", "m_min"]
               + (["f_isru"] if isru else []))
        # Which term set the feed, said by comparing them rather than
        # asserted: this note used to blame the throughput on every page.
        want = pay * out["ratio"]
        if M["feed"] == want:
            why = "the full ratio the sweep chose: nothing clipped the feed"
        # (No "floor" case: the payload is already capped by the same
        # throughput and mineable bounds, so the min() above never falls
        # below it, and a label for that was a branch no mission reached.)
        elif M["feed"] == thr:
            why = ("below the %s the sweep chose, because the rig's "
                   "throughput clips the feed first" % P(out["ratio"]))
        else:
            why = ("below the %s the sweep chose, because the body's "
                   "mineable mass clips the feed first" % P(out["ratio"]))
        S.step("ratio_got", "r_achieved", "the ratio the rig actually reaches",
               "feed / m_pay",
               "%s / %s" % (P(M["feed"]), P(pay)),
               M["ratio"], "-", ["feed", "m_pay"], why)
        water_note = ("the water the knapsack in %s loads; it is the "
                      "concentrate's own water, not the body's fraction"
                      % ref("hold"))
        S.step("water", "water", "water in the hold",
               "the water phase of the hold's mix" if M["water"] else
               "0: the hold's mix has no water phase", P(M["water"]),
               M["water"], "kg", ["m_pay", "eps_rec"], water_note)
    else:
        S.step("feed", "feed", "rock dug", "feed = m_pay on run-of-mine ore",
               P(pay), M["feed"], "kg", ["m_pay"],
               "not concentrating means the feed and the payload are the "
               "same rock")
        S.step("water", "water", "water in the hold", "m_pay * f_water",
               "%s * %s" % (P(pay), P(C["ice_frac"])),
               M["water"], "kg", ["m_pay", "f_water"])
    S.step("c_frac", "c_frac", "containment as a fraction of payload",
           "c_seal * min(1, water / m_pay)",
           "%s * min(1, %s / %s)"
           % (P(C["contain_per_kg"]), P(M["water"]), P(pay)),
           M["c_frac"], "-", ["c_seal", "water", "m_pay"])
    S.step("m_seal", "m_seal", "volatile containment mass", "c_frac * m_pay",
           "%s * %s" % (P(M["c_frac"]), P(pay)),
           M["m_containment"], "kg", ["c_frac", "m_pay"])
    S.step("f_eff", "f", "ore restraint plus the sealed hold",
           "f_str + c_frac",
           "%s + %s" % (P(C["cfg"].return_structure_frac_of_payload),
                        P(M["c_frac"])),
           M["f_eff"], "-", ["f_str", "c_frac"])
    if isru:
        S.prose("On an ISRU mission the return propellant is MADE from the "
                "rock, so the return half of the stack is sized here, before "
                "the dig it adds to; %s reuses these lines." % ref("stack"))
        return_stack_steps(S, out)
        S.step("f_isru_set", "f_ISRU", "rock dug for the propellant flown",
               "m_rprop * k_feed",
               "%s * %s" % (P(M["isru_prop"]), P(C["isru_feed_per_kg_prop"])),
               M["isru_feed"], "kg", ["m_rprop", "k_feed"],
               "re-settled on the stack actually flown")
    S.put("t_floor", "t_floor", "station-keeping floor on the stay",
          C["cfg"].station_keeping_floor_yr, "yr",
          cite_config("station_keeping_floor_yr"))
    S.step("t_dig", "t_dig", "the dig",
           "max((feed + f_ISRU) / rate, t_floor)" if isru
           else "max(feed / rate, t_floor)",
           "max(%s / %s, %s)"
           % (("(%s + %s)" % (P(M["feed"]), P(M["isru_feed"]))) if isru
              else P(M["feed"]), P(C["rate_kg_yr"]),
              P(C["cfg"].station_keeping_floor_yr)),
           M["dig_yr"], "yr", ["feed", "rate", "t_floor"]
           + (["f_isru_set"] if isru else []),
           "the FEED is dug, not the payload; that is what concentrating "
           "costs in time" if C["beneficiated"] else
           "the rock dug, at the rig's rate, never shorter than the floor")
    S.step("hrs", "hours", "the dig, in hours", "(t_dig * 365.25) * 24",
           "(%s * 365.25) * 24" % P(M["dig_yr"]),
           W.hours(M["dig_yr"]), "h", ["t_dig"],
           "y * 365.25 * 24 is NOT y * 8,766: the first rounds twice, and "
           "they differ in the last bit " + cited("on about 28% of this "
           "model's durations"))
    S.claim("365.25 * 24", 8766.0, "hours in a year, pre-multiplied")

    hrs = W.hours(M["dig_yr"])
    # The dig draw is charged only under the condition below, so a raw
    # mission that makes no propellant listed this as never spent.
    if C["beneficiated"] or C["isru"]:
        S.put("e_dig", "e_dig", "excavation energy", C["dig_wh"], "Wh/kg dug",
              cite_ops(C, "Drilling / excavation energy"))
    if C["beneficiated"]:
        S.put("e_ben", "e_ben", "beneficiation energy", C["benef_wh"],
              "Wh/kg of product",
              cite_ops(C, "Beneficiation / on-site processing energy"))
    # Only when there is water to liberate, which is the condition the draw
    # below spends it under; a dry body listed it as never spent.
    if M["liberated"] > 0:
        S.put("e_h2o", "e_H2O", "bound-water liberation energy",
              C["water_wh"], "Wh/kg of water",
              cite_ops(C, "Water liberation energy (bound water)"))
    d1 = 0.0
    if C["beneficiated"] or C["isru"]:
        d1 = (C["dig_wh"] * (M["feed"] + M["isru_feed"])
              + (C["benef_wh"] * M["m_pay"] if C["beneficiated"] else 0.0)
              ) / hrs
        S.step("P_dig", "P_dig", "excavation and processing draw",
               "(e_dig * feed + e_ben * m_pay) / hours"
               if C["beneficiated"] else "e_dig * feed / hours",
               ("(%s * %s + %s * %s) / %s"
                % (P(C["dig_wh"]), P(M["feed"] + M["isru_feed"]),
                   P(C["benef_wh"]), P(M["m_pay"]), P(hrs)))
               if C["beneficiated"] else
               "%s * %s / %s" % (P(C["dig_wh"]),
                                 P(M["feed"] + M["isru_feed"]), P(hrs)),
               d1, "W",
               ["e_dig", "feed", "hrs"] + (["e_ben", "m_pay"]
                                           if C["beneficiated"] else [])
               + (["f_isru_set"] if C["isru"] else []),
               "the feed here includes the rock dug for the propellant "
               "made on site" if C["isru"] else "")
    d2 = 0.0
    if M["liberated"] > 0:
        # What is baked out: the ISRU plant's water, and the cargo's own when
        # `model_water_liberation` is on.  It was printed as "water" whatever
        # it was made of.
        lib_terms, lib_nums, lib_uses = [], [], []
        if M.get("isru_water", 0.0) > 0:
            S.step("W_isru", "W_ISRU", "water baked out to make propellant",
                   "m_rprop * k_ISRU",
                   "%s * %s" % (P(M["isru_prop"]),
                                P(C["isru_water_per_kg_prop"])),
                   M["isru_water"], "kg", ["m_rprop", "k_isru"])
            lib_terms.append("W_ISRU")
            lib_nums.append(P(M["isru_water"]))
            lib_uses.append("W_isru")
        if abs(M["liberated"] - M.get("isru_water", 0.0)) > 0:
            lib_terms.append("water")
            lib_nums.append(P(M["water"]))
            lib_uses.append("water")
        S.step("W_lib", "W_lib", "water liberated",
               " + ".join(lib_terms), " + ".join(lib_nums),
               M["liberated"], "kg", lib_uses,
               "the cargo's water is baked out too: "
               "model_water_liberation is on" if "water" in lib_terms
               else "the cargo's own water is not baked out on this run")
        d2 = C["water_wh"] * M["liberated"] / hrs
        S.step("P_lib", "P_H2O", "bound-water liberation draw",
               "e_H2O * W_lib / hours",
               "%s * %s / %s" % (P(C["water_wh"]), P(M["liberated"]), P(hrs)),
               d2, "W", ["e_h2o", "W_lib", "hrs"])
    d3 = 0.0
    if M.get("refine_draw", 0.0) > 0:
        d3 = part_refinery(S, C, M, hrs)
    d4 = 0.0
    if M.get("isru_draw", 0.0) > 0:
        d4 = part_isru_plant(S, C, M, hrs)
    names = (["P_dig", "P_H2O"] + (["P_ref"] if d3 else [])
             + (["P_ISRU"] if d4 else []))
    nums = [d1, d2] + ([d3] if d3 else []) + ([d4] if d4 else [])
    S.step("draw", "P", "the continuous processing draw",
           " + ".join(names), " + ".join(P(v) for v in nums), M["draw"], "W",
           ([k for k in ("P_dig", "P_lib", "P_ref", "P_isru") if k in S.tag]
            or ["hrs"]))
    S.step("m_plant", "m_plant", "plant mass", "P / w_plant",
           "%s / %s" % (P(M["draw"]), P(C["plant_w_per_kg"])),
           M["plant"], "kg", ["draw", "w_plant"])

    if not C["electric"]:
        S.step("m_EP", "m_EP", "electric stage", "chemical: there is none",
               "0", 0.0, "kg", ["m_plant"])
    else:
        ep = M["ep"]
        S.prose("Sized on the converging pass's propellant load.  Array "
                "and power train scale with POWER; the thruster scales "
                "with THRUST, which owes nothing to efficiency.")
        S.put("t_burn_yr", "t_burn", "thrust time the stage is sized for",
              C["cfg"].ep_target_thrust_yr, "yr",
              cite_config("ep_target_thrust_yr"))
        S.put("eta_thr", "eta", "thruster efficiency", C["thruster_eff"], "-",
              cite_table_row(C["pro"], "propellants.csv",
                             C["pro"].raw("name"),
                             ("thruster_efficiency",)))
        S.put("sig_thr", "sigma_thr", "thruster specific mass",
              C["thruster_kg_per_n"], "kg/N",
              cite_table_row(C["pro"], "propellants.csv",
                             C["pro"].raw("name"),
                             ("thruster_kg_per_n", "thrust_scaling")))
        S.put("sig_ppu", "sigma_PPU", "power processing unit specific mass",
              C["ppu_kg_per_kw"], "kg/kW",
              cite_ops(C, "Power processing unit specific mass"))
        # The converging pass's closed form, carried on to its propellant.
        # This step printed the two loads and derived neither.
        R_ = M["R"]
        dry = cas["m_pay"] * (1.0 + cas["struct_frac"]) + cas["d0"]
        S.step("dry_cf", "dry_cf", "the returning stack the closed form "
               "solved", "m_pay,cf (1 + f_solved) + d_0",
               "%s * (1 + %s) + %s" % (P(cas["m_pay"]),
                                       P(cas["struct_frac"]), P(cas["d0"])),
               dry, "kg", ["m_pay_cf", "f_solved", "d0"])
        S.step("after_cf", "m_after,cf", "post-burn, at that pass",
               "k_ret * s_TPS * dry_cf",
               "%s * %s * %s" % (P(R_["k_ret"]), P(cas["s_tps"]), P(dry)),
               cas["m_after"], "kg", ["k_ret", "s_tps", "dry_cf"])
        S.step("rprop_cf", "m_rprop,cf", "return propellant, at that pass",
               "m_after,cf (R_ret - 1)",
               "%s * (%s - 1)" % (P(cas["m_after"]), P(R_["R_ret"])),
               cas["m_rprop"], "kg", ["after_cf", "R_ret"])
        S.step("at_cf", "m_at,cf", "at the asteroid, at that pass",
               "m_hw,solved + d_0 + f_solved m_pay,cf + tps_frac dry_cf "
               "+ t m_rprop,cf" + ("" if C["isru"] else " + m_rprop,cf"),
               "%s + %s + %s * %s + %s * %s + %s * %s%s"
               % (P(cas["hardware_kg"]), P(cas["d0"]),
                  P(cas["struct_frac"]), P(cas["m_pay"]), P(C["tps_frac"]),
                  P(dry), P(R_["t"]), P(cas["m_rprop"]),
                  "" if C["isru"] else " + " + P(cas["m_rprop"])),
               cas["m_at"], "kg",
               ["hw_solved", "d0", "f_solved", "m_pay_cf", "tps_frac",
                "dry_cf", "tank_frac", "rprop_cf"])
        S.step("oprop_cf", "m_oprop,cf", "outbound propellant, at that pass",
               "m_at,cf k_out (R_out - 1)",
               "%s * %s * (%s - 1)" % (P(cas["m_at"]), P(R_["k_out"]),
                                       P(R_["R_out"])),
               cas["m_oprop"], "kg", ["at_cf", "k_out", "R_out"])
        if C["isru"]:
            # calc's ISRU cascade hands the stage sizing a PLACEHOLDER: the
            # empty stack's outbound load and no return propellant.  The
            # page shows the load the model used, and says that it is not
            # the load flown.
            empty = cas["hardware_kg"] + R_["k_ret"] * cas["s_tps"] * cas["d0"]
            S.step("empty_cf", "m_empty", "the stack with no payload, as the "
                   "ISRU cascade states it", "m_hw,solved + k_ret * s_TPS * d_0",
                   "%s + %s * %s * %s" % (P(cas["hardware_kg"]),
                                          P(R_["k_ret"]), P(cas["s_tps"]),
                                          P(cas["d0"])),
                   empty, "kg", ["hw_solved", "k_ret", "s_tps", "d0"])
            S.step("m_prop_ep", "m_prop", "the load the stage is sized on",
                   "m_empty * k_out * R_out - m_empty",
                   "%s * %s * %s - %s" % (P(empty), P(R_["k_out"]),
                                          P(R_["R_out"]), P(empty)),
                   cas["m_prop_ep"], "kg", ["empty_cf", "k_out", "R_out"],
                   "NOT the load flown, which is m_oprop,cf + m_rprop,cf = "
                   + P(cas["m_prop"]) + " kg: calc's ISRU cascade returns "
                   "the empty stack's outbound propellant and no return "
                   "propellant as a placeholder, and its _ep_stage_kg sizes "
                   "the stage off that")
            S.claim("%s + %s" % (P(cas["m_oprop"]), P(cas["m_rprop"])),
                    cas["m_prop"], "the load flown at that pass",
                    ["oprop_cf", "rprop_cf"])
        else:
            S.step("m_prop_ep", "m_prop", "the load the stage is sized on",
                   "m_oprop,cf + m_rprop,cf",
                   "%s + %s" % (P(cas["m_oprop"]), P(cas["m_rprop"])),
                   cas["m_prop_ep"], "kg", ["oprop_cf", "rprop_cf"],
                   "the converging pass's propellant: the stage flown is the "
                   "one that pass sized")
        secs = C["cfg"].ep_target_thrust_yr * 365.25 * 24.0 * 3600.0
        S.step("t_burn_s", "t_burn (s)", "thrust time, in seconds",
               "t_burn * 365.25 * 24 * 3600",
               "%s * 365.25 * 24 * 3600" % P(C["cfg"].ep_target_thrust_yr),
               secs, "s", ["t_burn_yr"])
        S.step("P_ep", "P_EP", "electric power", "m_prop v_e^2 / (2 eta t)",
               "%s * %s / (2 * %s * %s)"
               % (P(cas["m_prop_ep"]), P(C["ve"] ** 2), P(C["thruster_eff"]),
                  P(secs)),
               ep["power"], "W",
               ["m_prop_ep", "ve", "eta_thr", "t_burn_s"])
        S.step("T_ep", "T", "thrust", "m_prop v_e / t",
               "%s * %s / %s" % (P(cas["m_prop_ep"]), P(C["ve"]), P(secs)),
               ep["thrust"], "N", ["m_prop_ep", "ve", "t_burn_s"])
        S.step("ep_array", "array", "the cruise array", "P_EP / w_bare",
               "%s / %s" % (P(ep["power"]), P(C["w_bare"])),
               ep["array"], "kg", ["P_ep", "w_bare"],
               "the BARE figure: a cruise array is in permanent sunlight, "
               "and it is the PROCESSING plant that stands in shadow")
        S.step("ep_ppu", "PPU", "power processing",
               "(P_EP / 1000) * sigma_PPU",
               "%s / 1000 * %s" % (P(ep["power"]), P(C["ppu_kg_per_kw"])),
               ep["ppu"], "kg", ["P_ep", "sig_ppu"])
        S.step("ep_thr", "thruster", "the thruster", "T * sigma_thr",
               "%s * %s" % (P(ep["thrust"]), P(C["thruster_kg_per_n"])),
               ep["thruster"], "kg", ["T_ep", "sig_thr"])
        S.step("m_EP", "m_EP", "electric stage", "array + PPU + thruster",
               "%s + %s + %s" % (P(ep["array"]), P(ep["ppu"]),
                                 P(ep["thruster"])),
               ep["mass"], "kg", ["ep_array", "ep_ppu", "ep_thr"])
    if M.get("isru_plant", 0.0) > 0:
        S.step("m_hw", "m_hw", "hardware, as flown",
               "m_rig + m_plant + m_EP + m_ref + m_iplant",
               "%s + %s + %s + %s + %s" % (P(C["cfg"].mining_hardware_kg),
                                           P(M["plant"]), P(M["ep"]["mass"]),
                                           P(M.get("refinery", 0.0)),
                                           P(M["isru_plant"])),
               M["hw"], "kg", ["m_rig", "m_plant", "m_EP", "m_iplant"]
               + (["m_ref"] if M.get("refinery", 0.0) > 0 else []))
    elif M.get("refinery", 0.0) > 0:
        S.step("m_hw", "m_hw", "hardware, as flown",
               "m_rig + m_plant + m_EP + m_ref",
               "%s + %s + %s + %s" % (P(C["cfg"].mining_hardware_kg),
                                      P(M["plant"]), P(M["ep"]["mass"]),
                                      P(M["refinery"])),
               M["hw"], "kg", ["m_rig", "m_plant", "m_EP", "m_ref"])
    else:
        S.step("m_hw", "m_hw", "hardware, as flown",
               "m_rig + m_plant + m_EP",
               "%s + %s + %s" % (P(C["cfg"].mining_hardware_kg),
                                 P(M["plant"]), P(M["ep"]["mass"])),
               M["hw"], "kg", ["m_rig", "m_plant", "m_EP"])


# ------------------------------------------------------- 8. the flown stack
def part_isru_plant(S, C, M, hrs):
    """calc v1.32.0: what making the propellant costs in watts and in plant.
    Returns the draw, which the caller adds to the processing total."""
    S.prose("Hydrolox made on site is split and both gases liquefied.  Module 3 "
            "states that as an energy per kilogram MADE, on top of liberating "
            "the water, and sizes the plant that does it from a throughput.")
    S.put("e_isru", "e_ISRU", "processing energy per kg of propellant made",
          C["isru_wh"], "Wh/kg",
          cite_table_row(C["pro"], "propellants.csv", C["pro"].raw("name"),
                         ("isru_processing_wh_per_kg",)))
    S.step("P_isru", "P_ISRU", "the propellant plant's draw",
           "e_ISRU * m_rprop / hours",
           "%s * %s / %s" % (P(C["isru_wh"]), P(M["isru_prop"]), P(hrs)),
           M["isru_draw"], "W", ["e_isru", "m_rprop", "hrs"])
    S.put("r_isru", "r_ISRU", "ISRU plant throughput", C["isru_plant_rate"],
          "kg/yr per kg of plant",
          cite_ops(C, "ISRU propellant plant throughput"))
    S.step("m_iplant", "m_iplant", "the ISRU plant",
           "m_rprop / (t_dig * r_ISRU)",
           "%s / (%s * %s)" % (P(M["isru_prop"]), P(M["dig_yr"]),
                               P(C["isru_plant_rate"])),
           M["isru_plant"], "kg", ["m_rprop", "r_isru"],
           "it rides with the rig and is costed as the rig is")
    return M["isru_draw"]


def part_refinery(S, C, M, hrs):
    """The flown refinery's energy, draw and plant (calc v1.25.0).  Returns
    the draw, which the caller adds to the processing total."""
    S.prose("The refinery is flown: each phase is refined by the route it "
            "is sold by, an element shipped home is refined on Earth, and "
            "every price above is the one before Stage 2's refining "
            "deduction.  Energies are Stage 2's <i>refining_kwh_per_kg</i>.")
    merged = C.get("merged") or {}

    def energy(name):
        """Register one phase's refining energy, by the route it is sold."""
        how = C["refine_how"].get(name, {})
        short = ("wh_" + name.replace(" ", "_").replace("-", "_")
                 .replace("(", "").replace(")", ""))
        value = C["refine_wh"].get(name, 0.0)
        row = "silicates" if name.startswith("other") else name
        if how.get("route") == "refined" and (how["terms"] or how["own_kwh"]):
            terms = []
            if how["own_kwh"]:
                terms.append("%s * 1000" % P(how["own_kwh"]))
            terms += ["%s * %s * 1000" % (P(f), P(k))
                      for _e, f, k in how["terms"]]
            # The energies are Stage 2 rows, named here because the step
            # cannot cite rows it never registered as inputs.
            S.step(short, "e_ref,%s" % name, "%s taken apart" % name,
                   "1000 (own kWh/kg + sum of yield * element kWh/kg)",
                   " + ".join(terms), value, "Wh/kg", [],
                   cited("<b>mineral_value_catalog.csv</b>, column "
                         "<i>refining_kwh_per_kg</i>: %s"
                         % "; ".join(["%s %s" % (D.esc(name),
                                                 P(how["own_kwh"]))]
                                     * bool(how["own_kwh"])
                                     + ["%s %s" % (D.esc(e), P(k))
                                        for e, _f, k in how["terms"]])
                         + ".  Only the elements refined HERE are charged; "
                         "one shipped home is refined on Earth"))
        elif value == 0.0:
            S.put(short, "e_ref,%s" % name, "%s refining energy" % name,
                  value, "Wh/kg",
                  cite_column(C, row, "value_route", "Zero: this phase is "
                              "shipped home and refined on Earth."))
        else:
            S.put(short, "e_ref,%s" % name, "%s refining energy" % name,
                  value, "Wh/kg",
                  cite_column(C, row, "refining_kwh_per_kg", "Times 1000, "
                              "refined as it is."))
        return short

    rows, keys = [], []
    for name, _frac, _price in C["phases"]:
        if name in merged:
            # Sold as one product, so refined at the members' fraction-
            # weighted energy: this cited nickel-iron's OWN row, which a
            # detailed-phase body never reads.
            members = merged[name]
            mkeys = [energy(m) for m, _f, _v in members]
            short = "wh_" + name.replace(" ", "_").replace("-", "_")
            frac = sum(f for _m, f, _v in members)
            S.step(short, "e_ref,%s" % name, "%s, as one product" % name,
                   "sum of f * e_ref over its members / f",
                   "(%s) / %s" % (" + ".join(
                       "%s * %s" % (P(f), P(C["refine_wh"].get(m, 0.0)))
                       for m, f, _v in members), P(frac)),
                   C["refine_wh"].get(name, 0.0), "Wh/kg", mkeys)
            keys.append(short)
            continue
        keys.append(energy(name))
    if C["beneficiated"]:
        mix = M["load"]["mix"]
        S.step("E_ref", "E_ref", "refining energy for this hold",
               "sum over the hold of kg * e_ref",
               " + ".join("%s * %s" % (P(kg), P(C["refine_wh"].get(n, 0.0)))
                          for n, kg in mix.items()),
               M["refine_wh"], "Wh", keys,
               # The kilograms are the knapsack's, which is laid out later:
               # it fills this same payload, so it is a table, not a step.
               "each phase's kilograms are what the hold's walk takes, in "
               "the TAKEN column of %s" % ref("hold"))
    else:
        S.step("e_raw", "e_raw", "refining energy per kg of ore",
               "sum over phases of f * e_ref",
               " + ".join("%s * %s" % (P(f), P(C["refine_wh"].get(n, 0.0)))
                          for n, f, _p in C["phases"]),
               C["refine_raw_wh"], "Wh/kg", keys)
        S.step("E_ref", "E_ref", "refining energy for this hold",
               "m_pay * e_raw", "%s * %s" % (P(M["m_pay"]),
                                             P(C["refine_raw_wh"])),
               M["refine_wh"], "Wh", ["e_raw", "m_pay"])
    S.step("P_ref", "P_ref", "the refinery's draw", "E_ref / hours",
           "%s / %s" % (P(M["refine_wh"]), P(hrs)), M["refine_draw"], "W",
           ["E_ref", "hrs"])
    S.put("r_plant", "r_plant", "refinery throughput", C["refinery_rate"],
          "kg/yr per kg of plant",
          cite_ops(C, "In-space processing plant throughput"))
    S.step("m_ref", "m_ref", "the refinery plant",
           "m_pay / (t_dig * r_plant)",
           "%s / (%s * %s)" % (P(M["m_pay"]), P(M["dig_yr"]),
                               P(C["refinery_rate"])),
           M["refinery"], "kg", ["m_pay", "r_plant"],
           "it rides with the rig and is costed as the rig is")
    return M["refine_draw"]


def return_stack_steps(S, out):
    """The return vehicle, its heat shield and the return propellant.

    None of these depends on the hardware, so an ISRU mission sizes them in
    the settled part, before the dig the propellant adds to, and the stack
    part reuses them; registering them twice would be a key used twice.
    """
    if "m_rprop" in S.tag:
        return
    C, M = out["C"], out["M"]
    R, cas = M["R"], M["cascade"]
    S.step("m_dry", "m_dry", "return vehicle dry", "d_0 + f * m_pay",
           "%s + %s * %s" % (P(cas["d0"]), P(M["f_eff"]), P(M["m_pay"])),
           M["m_dry"], "kg", ["d0", "f_eff", "m_pay"])
    S.step("m_tps", "m_TPS", "heat shield",
           "tps_frac * (m_pay + m_dry)",
           "%s * (%s + %s)" % (P(C["tps_frac"]), P(M["m_pay"]),
                               P(M["m_dry"])),
           M["m_tps"], "kg", ["tps_frac", "m_pay", "m_dry"],
           "zero on a propulsive return" if C["tps_frac"] == 0 else
           "sized on the stack it arrives behind")
    S.step("m_after", "m_after", "the returning stack, post-burn",
           "k_ret (1 + tps_frac) (m_pay (1 + f) + d_0)",
           "%s * (1 + %s) * (%s * (1 + %s) + %s)"
           % (P(R["k_ret"]), P(C["tps_frac"]), P(M["m_pay"]), P(M["f_eff"]),
              P(cas["d0"])),
           M["m_after"], "kg", ["k_ret", "tps_frac", "m_pay", "f_eff", "d0"])
    S.step("m_rprop", "m_rprop", "return propellant",
           "m_after (R_ret - 1)",
           "%s * (%s - 1)" % (P(M["m_after"]), P(R["R_ret"])),
           M["m_rprop"], "kg", ["m_after", "R_ret"],
           "made at the asteroid" if C["isru"] else "")


def part_stack(S, out):
    """The stack rebuilt on settled hardware, and what closes it."""
    C, M, B = out["C"], out["M"], out["B"]
    R, cas = M["R"], M["cascade"]
    S.part("stack", "The stack, from the payload outwards",
           "Built on the settled hardware and containment of %s, which "
           "are lighter than the ones the closed form solved at.  That "
           "difference is the whole launch margin." % ref("settled"))
    if "m_rprop" in S.tag:
        S.prose("The return vehicle, its heat shield and the return "
                "propellant were sized in %s, because this mission makes "
                "that propellant from the rock." % ref("settled"))
    return_stack_steps(S, out)
    S.step("m_tank_ret", "m_tank,ret", "return tankage", "t * m_rprop",
           "%s * %s" % (P(R["t"]), P(M["m_rprop"])),
           M["m_tank_ret"], "kg", ["tank_frac", "m_rprop"])
    S.step("m_at", "m_at", "mass at the asteroid, before the ore is loaded",
           ("m_hw + m_dry + m_TPS + m_tank,ret" if C["isru"]
            else "m_hw + m_dry + m_TPS + m_tank,ret + m_rprop"),
           ("%s + %s + %s + %s"
            % (P(M["hw"]), P(M["m_dry"]), P(M["m_tps"]), P(M["m_tank_ret"])))
           if C["isru"] else
           ("%s + %s + %s + %s + %s"
            % (P(M["hw"]), P(M["m_dry"]), P(M["m_tps"]), P(M["m_tank_ret"]),
               P(M["m_rprop"]))),
           M["m_at"], "kg",
           ["m_hw", "m_dry", "m_tps", "m_tank_ret"]
           + ([] if C["isru"] else ["m_rprop"]))
    S.step("m_oprop", "m_oprop", "outbound propellant",
           "m_at k_out (R_out - 1)",
           "%s * %s * (%s - 1)" % (P(M["m_at"]), P(R["k_out"]),
                                   P(R["R_out"])),
           M["m_oprop"], "kg", ["m_at", "k_out", "R_out"])
    S.step("m_tank_out", "m_tank,out", "outbound tankage", "t * m_oprop",
           "%s * %s" % (P(R["t"]), P(M["m_oprop"])),
           M["m_tank_out"], "kg", ["tank_frac", "m_oprop"])
    S.step("m_launch", "m_launch", "launch mass",
           "m_at + m_tank,out + m_oprop",
           "%s + %s + %s" % (P(M["m_at"]), P(M["m_tank_out"]),
                             P(M["m_oprop"])),
           M["m_launch"], "kg", ["m_at", "m_tank_out", "m_oprop"],
           "against a vehicle capacity of %s kg" % P(C["leo_cap"]))

    # calc v1.29.0: a stack the overshoot repair re-solved sits ON the
    # vehicle's capacity, and its "spare" is the rounding of that solve --
    # a few units in the last place either side of zero.  The identity
    # below holds only to that noise, so a page that asserted it would be
    # asserting a residue; this one says what the run actually did.
    spare_kg = C["leo_cap"] - M["m_launch"]
    if abs(spare_kg) <= 1e-9 * C["leo_cap"]:
        S.prose("It lands ON the vehicle's capacity, not under it: the "
                "overshoot repair solved the payload to that capacity, and "
                "what is left is the rounding of the solve, inside calc's "
                "launch_capacity_rtol.")
        S.step("spare", "M_LEO - m_launch", "spare capacity",
               "M_LEO - m_launch",
               "%s - %s" % (exact(C["leo_cap"]), exact(M["m_launch"])),
               spare_kg, "kg", ["M_LEO", "m_launch"],
               "the operands are given exactly, because the difference is "
               "the last bit of a solve that landed on the constraint")
    else:
        S.prose("Why it lands under the vehicle, exactly.")
        short = R["budget"] - M["m_at"]
        S.step("short", "budget - m_at", "how far under the budget the flown "
               "stack arrives", "budget - m_at",
               "%s - %s" % (exact(R["budget"]), exact(M["m_at"])), short, "kg",
               ["budget", "m_at"],
               "this subtraction CANCELS five digits, so the operands are "
               "given exactly; the rounded values in %s land about "
               "three digits short" % refs("ratios", "stack", "and"))
        S.step("spare", "M_LEO - m_launch", "spare capacity",
               "(budget - m_at) * k_out * R_out",
               "%s * %s * %s" % (P(short), P(R["k_out"]), P(R["R_out"])),
               spare_kg, "kg",
               ["short", "k_out", "R_out"],
               "the same number as M_LEO - m_launch, which is what closes the "
               "cascade against itself")

    caps, binds = payload_caps(out)
    S.prose("%s ceilings stand over the payload; the smallest is the payload "
            "flown, %s kg.%s"
            % (["No", "One", "Two", "Three", "Four", "Five"][len(caps)],
               P(M["m_pay"]),
               "  On concentrate the rig's throughput caps the FEED, not the "
               "payload, so it is not one of them here."
               if C["beneficiated"] else ""))
    rows = []
    for name, what, kg, key in caps:
        loop_feed = M.get("isru_feed_loop", 0.0) if C["isru"] else 0.0
        if name in ("mineable", "throughput") and loop_feed > 0:
            gross = B["mineable"] if name == "mineable" else M["throughput"]
            kg_text = S.claim("max(0, %s - %s)" % (P(gross), P(loop_feed)),
                              kg, "%s cap net of the ISRU feed" % name)
        else:
            kg_text = P(kg)
        rows.append([name, what,
                     kg_text + (" <b>binds</b>" if name in binds else ""),
                     '<span class="uses">%s</span>' % S.tag.get(key, "-")])
    S.block(D.table(["cap", "what it is", "kg", "worked out at"], rows))


# ------------------------------------------------------------ 9. the clock
def part_clock(S, out):
    """Periods, the wait for a window, the two duration clocks, the cadence."""
    C, M, DV = out["C"], out["M"], out["DV"]
    S.part("clock", "The clock",
           "Extraction is rate-limited, so the dig reaches the duration, "
           "the ops cost and the cadence.  The duration is the LONGER of "
           "two clocks.")
    S.step("T_ast", "T_ast", "orbital period of the body", "a ^ 1.5",
           "%s ^ 1.5" % P(C["a_au"]), DV["t_ast"], "yr", ["a"],
           "Kepler's third law in AU and years, where the constant is 1")
    S.put("a_dest", "a_dest", "the orbit %s is phased against"
          % C["destination"], DV["a_dest"], "AU",
          "<b>modules/calc.py</b>, <i>DELIVERY_ARCHITECTURES</i>, row "
          "<i>%s</i>, field <i>window_phasing_au</i>.  <span class='src'>A "
          "launch window recurs at the synodic period between the asteroid "
          "and the body the cargo is delivered to: everything in Earth's "
          "system rides Earth's orbit, and a Mars delivery waits on "
          "Earth-Mars alignment.</span>" % D.esc(C["destination"]))
    S.step("T_dest", "T_dest", "the orbit the destination is phased against",
           "a_dest ^ 1.5", "%s ^ 1.5" % P(DV["a_dest"]), DV["t_dest"], "yr",
           ["a_dest"])
    # The model caps the period at ten years (a co-orbital body's windows
    # never come round, and a real mission takes a worse transfer instead),
    # and answers one year for a geometry the term cannot speak about.  The
    # cap BINDS on every near-Earth body whose period is within ~10% of the
    # destination's, so a formula without it is wrong exactly there.
    if not (0.05 < C["a_au"] < 100.0) or DV["a_dest"] <= 0:
        S.step("synodic", "S_syn", "synodic period",
               "1: a = %s AU lies outside 0.05 < a < 100 AU, the geometry "
               "calc's synodic term covers, and it answers one year there"
               % P(C["a_au"]), "1", DV["synodic"], "yr", ["a"])
    else:
        S.step("synodic", "S_syn", "synodic period",
               "min(1 / |1 / T_ast - 1 / T_dest|, 10)",
               "min(1 / |1 / %s - 1 / %s|, 10)"
               % (exact(DV["t_ast"]), exact(DV["t_dest"])),
               DV["synodic"], "yr", ["T_ast", "T_dest"],
               "capped at ten years: a body whose period nearly matches "
               "the destination's would otherwise wait for ever")
    S.step("t_win", "t_win", "expected wait for a departure window",
           "S_syn / 2" if C["windows"] else "0: windows are not modelled",
           ("%s / 2" % P(DV["synodic"])) if C["windows"] else "0",
           DV["window_wait"], "yr", ["synodic"],
           "this punishes near-Earth bodies hardest: their periods are "
           "near Earth's, so the windows are years apart")
    S.step("stay", "t_stay", "time at the asteroid", "t_dig + t_win",
           "%s + %s" % (P(M["dig_yr"]), P(DV["window_wait"])),
           M["stay"], "yr", ["t_dig", "t_win"])
    S.step("t_out_yr", "t_out", "outbound transfer",
           "max(0.5, tau_fit * dv_out)",
           "max(0.5, %s * %s)" % (P(W.TAU_CRUISE_FIT_YR_PER_M_S),
                                  P(DV["dv_out"])),
           M["t_out"], "yr", ["tau", "dv_out"])
    S.step("t_back_yr", "t_back", "return transfer",
           "max(0.5, tau_fit * dv_ret)",
           "max(0.5, %s * %s)" % (P(W.TAU_CRUISE_FIT_YR_PER_M_S),
                                  P(DV["dv_ret"])),
           M["t_back"], "yr", ["tau", "dv_ret"])
    S.step("chem_fit", "chem", "transfer fit: out + stay + back",
           "t_out + t_stay + t_back",
           "%s + %s + %s" % (P(M["t_out"]), P(M["stay"]), P(M["t_back"])),
           M["chem_fit"], "yr", ["t_out_yr", "stay", "t_back_yr"])
    if M["electric_floor"] > 0:
        S.step("e_floor", "elec", "electric floor: thrust time + stay",
               "t_burn + t_stay",
               "%s + %s" % (P(M["ep"]["thrust_yr"]), P(M["stay"])),
               M["electric_floor"], "yr", ["t_burn_yr", "stay"],
               "the cruise fit is calibrated to CHEMICAL transfers; an "
               "electric stage is governed by burn time instead")
    S.step("T_miss", "T_miss", "mission duration",
           "max(1, chem, elec)",
           "max(1, %s, %s)" % (P(M["chem_fit"]), P(M["electric_floor"])),
           M["duration"], "yr",
           ["chem_fit"] + (["e_floor"] if M["electric_floor"] > 0 else []),
           # The 1 is the model's and is printed as such, but it never binds:
           # each leg of the transfer fit is at least half a year and the
           # stay is positive, so the fit always exceeds a year.  A third
           # label naming it was a branch no mission can reach.
           "the %s is the slower clock here; the 1 never binds, because "
           "each leg of the fit is at least half a year"
           % ("electric floor" if M["electric_floor"] > M["chem_fit"]
              else "transfer fit"))
    S.put("T_max", "T_max", "the longest mission the model flies",
          C["cfg"].max_mission_duration_yr, "yr",
          cite_config("max_mission_duration_yr"))
    S.step("T_margin", "T_max - T_miss", "how far inside that limit this "
           "mission is", "T_max - T_miss",
           "%s - %s" % (P(C["cfg"].max_mission_duration_yr),
                        P(M["duration"])),
           C["cfg"].max_mission_duration_yr - M["duration"], "yr",
           ["T_max", "T_miss"],
           "a candidate over the limit is refused, not charged")
    S.step("T_cad", "T_cad", "campaign cadence", "max(t_stay, S_syn)",
           "max(%s, %s)" % (P(M["stay"]), P(DV["synodic"])),
           M["cadence"], "yr", ["stay", "synodic"],
           "the dig paces this programme"
           if M["stay"] >= DV["synodic"] else "the window paces it")
    S.put("L_rig", "L_rig", "rig service life",
          C["val"]("Mining rig service life", used=False), "yr",
          cite_ops(C, "Mining rig service life"))
    S.put("W_max", "W_max", "rig maximum campaigns",
          C["val"]("Mining rig maximum trips", used=False), "-",
          cite_ops(C, "Mining rig maximum trips"))
    S.step("cal_cap", "calendar", "campaigns the calendar allows",
           "max(1, floor(L_rig / t_stay))",
           "max(1, floor(%s / %s))"
           % (P(C["val"]("Mining rig service life", used=False)),
              P(M["stay"])),
           M["calendar_cap"], "-", ["L_rig", "stay"])
    S.step("trips", "trips", "campaigns one rig serves",
           "min(calendar, W_max)",
           "min(%s, %s)" % (P(M["calendar_cap"]),
                            P(C["val"]("Mining rig maximum trips",
                                       used=False))),
           M["trips"], "-", ["cal_cap", "W_max"],
           "the rig is retired by %s"
           % ("the calendar" if M["calendar_cap"] <= C["val"](
               "Mining rig maximum trips", used=False)
              else "its duty cycles"))


# ------------------------------------------------------------ 10. the hold
def part_hold(S, out):
    """The fractional knapsack that decides what comes home."""
    C, M = out["C"], out["M"]
    S.part("hold", "The hold",
           "A fractional knapsack: with a fixed mass budget and divisible "
           "per-kilogram-priced phases, greedy by $/kg is provably "
           "optimal.")
    if C["beneficiated"]:
        S.prose("Supply is <b>feed x f_c x eps_rec</b>; the walk takes "
                "<b>min(supply, hold left)</b> in descending price "
                "order.")
        frac = dict((n, f) for n, f, _p in C["phases"])
        rows = []
        for n, w in enumerate(M["load"]["walk"], 1):
            supply = S.claim("%s * %s * %s"
                             % (P(M["feed"]), P(frac[w["phase"]]),
                                P(C["recovery"])), w["supply"],
                             "%s supply" % w["phase"])
            take = S.claim("min(%s, %s)" % (P(w["supply"]), P(w["hold"])),
                           w["take"], "%s taken" % w["phase"])
            rows.append([ordinal(n), D.esc(w["phase"]), "$" + P(w["price"]),
                         P(frac[w["phase"]]), supply, P(w["supply"]),
                         P(w["hold"]), take, P(w["take"]),
                         "hold full" if w["take"] <= 0
                         else ("hold ran out" if w["take"] < w["supply"]
                               else "all the feed had")])
        S.block(D.table(["#", "phase", "$/kg", "f_c", "supply worked out",
                         "supply (kg)", "hold left (kg)", "taken worked out",
                         "taken (kg)", "what stopped it"], rows, "wide"))
    else:
        S.prose("Run-of-mine ore is not sorted: the hold carries the body's "
                "own blend, phase by phase in its own proportions, "
                "normalised by the sum of the fractions.")
        fracs = [(n, f) for n, f, _p in C["phases"]]
        f_sum = sum(f for _n, f in fracs)
        rows = []
        for name, f in fracs:
            kg = M["load"]["mix"][name]
            work = S.claim("%s * %s / %s" % (P(M["m_pay"]), P(f), P(f_sum)),
                           kg, "%s in the raw hold" % name)
            rows.append([D.esc(name), P(f), work, P(kg)])
        S.block(D.table(["phase", "f_c", "kg worked out (m_pay f_c / sum f)",
                         "kg"], rows))
    S.step("hold_value", "V_hold", "what the load is worth, unbounded",
           "sum over phases of taken * P_c",
           " + ".join("%s * %s" % (P(v), P(dict(
               (n, p) for n, _f, p in C["phases"])[k]))
               for k, v in M["load"]["mix"].items()),
           M["load"]["value"], "$",
           ["m_pay", "feed"] + phase_price_keys(S, C, M["load"]["mix"]))
    S.step("hold_per_kg", "V_hold/kg", "blended value of the hold",
           "V_hold / m_pay",
           "%s / %s" % (P(M["load"]["value"]), P(M["m_pay"])),
           M["load"]["usd_per_kg"], "$/kg", ["hold_value", "m_pay"],
           "a factor of %s on the body's own blend, which is %s / %s"
           % (P(M["load"]["usd_per_kg"] / C["bulk"], 4),
              P(M["load"]["usd_per_kg"]), P(C["bulk"])))
    S.claim("%s / %s" % (P(M["load"]["usd_per_kg"]), P(C["bulk"])),
            M["load"]["usd_per_kg"] / C["bulk"], "the enrichment factor")
    S.step("ret_vol", "V_ret", "volume the cargo occupies",
           "m_pay / rho / 1000",
           "%s / %s / 1000" % (P(M["m_pay"]), P(C["rho"])),
           M["ret_vol"], "m3", ["m_pay", "rho"])


# ---------------------------------------------------------- 11. the market
def market_inputs(S, C, markets):
    """Register each market's absorption ceiling once; return their keys."""
    keys = {}
    first = getattr(S, "first_cap", None)
    for market in markets:
        cap = C["market_kg"].get(market)
        if cap is None:
            continue
        key = "cap_%s" % market.replace(" ", "_").replace("-", "_")
        if key not in S.tag:
            # The routing rule is said under the first ceiling only; it was
            # the same sentence under all nine, and again in part 18.
            S.put(key, "Cap_%s" % market, "%s absorption ceiling" % market,
                  cap, "kg/yr",
                  "<b>mineral_value_catalog.csv</b> &middot; row <i>%s</i> "
                  "&middot; column <i>annual_market_kg</i>, %s."
                  % (D.esc(market),
                     "which Module 2 ROUTES: a commodity sold at the depot "
                     "is bounded by that depot's import budget "
                     "(<i>IN_SPACE_ANNUAL_DEMAND_KG</i>) times its commodity "
                     "class's share of it (<i>_DEMAND_SHARE_BY_CLASS</i>, "
                     "both in <b>modules/mineral_value.py</b>), and one "
                     "flown home by world annual production"
                     if first is None else
                     "routed as the %s ceiling above is"
                     % D.esc(first)))
            first = S.first_cap = first or market
        keys[market] = key
    return keys


def part_market(S, out):
    """The sale, under whichever market model the row's run used.

    🚨  FOUR MODELS, AND THE PAGE USED TO KNOW ONE.  Its blurb said "prices
    are constant at any volume; what bounds a programme is what the
    destination can absorb", which is `capacity_cap` and nothing else, and
    its sale table indexed the knapsack's walk -- which a run-of-mine hold
    under `unbounded` does not have at all.  The model is the row's
    (`market_model`), and each one is written out the way the derivation
    prices it.
    """
    C, M, P_ = out["C"], out["M"], out["P"]
    rev = P_["rev"]
    n, f, w = P_["n"], P_["f"], P_["w"]
    mode = rev.get("mode", out["terms"]["market"])
    blurbs = {
        "capacity_cap": "Market model <b>capacity_cap</b>: prices are "
                        "constant at any volume, and what bounds a programme "
                        "is what the destination can absorb while it waits.  "
                        "A bigger fleet delivers more often, so each "
                        "delivery gets a shorter slice of the year.",
        "elasticity": "Market model <b>elasticity</b>: every kilogram sells, "
                      "and the price falls as the programme's delivery rate "
                      "fills the market, along a constant-elasticity demand "
                      "curve.",
        "unbounded": "Market model <b>unbounded</b>: no ceiling and no "
                     "curve, so the whole hold sells at its price.  The "
                     "model labels this a diagnostic, because it is the "
                     "free lunch the other models exist to refuse.",
        "single_mission": "Market model <b>single_mission</b>: the "
                          "programme is pinned at one mission and no market "
                          "bound is asked, so the whole hold sells at its "
                          "price."}
    S.part("market", "The market", blurbs.get(mode, "Market model <b>%s</b>."
                                              % D.esc(mode)))
    S.put("N", "N", "programme size", n, "missions",
          "<b>Derived on this page</b>, by the ladder in "
          + ref("searches") + "; the run "
          "records it as <b>profitability_catalog</b> &middot; column "
          "<i>programme_missions</i>.")
    S.put("F", "F", "fleet", f, "ships",
          "<b>Derived on this page</b>, by the ladder in "
          + ref("searches") + "; recorded "
          "as <b>profitability_catalog</b> &middot; column "
          "<i>fleet_ships</i>.")
    S.put("Wc", "W", "campaigns per ship", w, "-",
          "<b>Derived on this page</b>, by the ladder in "
          + ref("searches") + " and "
          "bounded by the rig's trips; recorded as "
          "<b>profitability_catalog</b> &middot; column "
          "<i>missions_per_ship</i>.")
    price = dict((name, p) for name, _f, p in C["phases"])
    mix = M["load"]["mix"]

    if mode in ("unbounded", "single_mission"):
        S.step("Rev", "Rev", "what one delivery sells",
               "V_hold: nothing bounds the sale", P(rev["capped"]["value"]),
               rev["capped"]["value"], "$", ["hold_value", "N", "F", "Wc"])
    elif mode == "elasticity":
        S.put("eps_d", "eps", "price elasticity of demand",
              C["cfg"].demand_elasticity, "-",
              cite_config("demand_elasticity"))
        keys = market_inputs(S, C, sorted(rev["pooled"]))
        residual = {
            "pooled": "The quantities are POOLED per market, because two "
                      "phases selling into one market depress it together",
            "copy": "Each phase is its own market here: this row's calc "
                    "(%s) gave the composition residual a COPY of the "
                    "silicates ceiling, and pooling the two came in 1.21.2"
                    % C["terms"]["stamp"],
            "none": "Each phase is its own market here, and the composition "
                    "residual has none at all: this row's calc (%s) bounded "
                    "only phases with a Stage 2 row of their own, and the "
                    "residual joined the silicates market in 1.21.1"
                    % C["terms"]["stamp"],
        }[C.get("residual_market", "pooled")]
        S.prose("%s; the rate is the fleet's, because F ships put F "
                "payloads on the market over one mission's duration.  P / P0 "
                "= (1 + Q / Qm) ^ (-1 / eps), and exactly 1 where the market "
                "shrugs." % residual)
        rows = []
        for market in sorted(rev["pooled"]):
            kg = rev["pooled"][market]
            cap = C["market_kg"].get(market, 0.0)
            mult = rev["multipliers"][market]
            rate = kg * f / M["duration"]
            rate_work = S.claim("%s * %s / %s" % (P(kg), P(f),
                                                  P(M["duration"])),
                                rate, "%s delivery rate" % market)
            if cap > 0 and rate > 0 and C["cfg"].demand_elasticity > 0 \
                    and rate / cap > 1e-9:
                mult_work = S.claim("(1 + %s / %s) ^ (-1 / %s)"
                                    % (P(rate), P(cap),
                                       P(C["cfg"].demand_elasticity)),
                                    mult, "%s multiplier" % market,
                                    [keys.get(market, "eps_d"), "eps_d"])
            else:
                mult_work = "1: the market does not feel it"
            rows.append([D.esc(market), P(kg), rate_work, P(rate),
                         P(cap) if cap else "-", mult_work,
                         P(mult, 12)])
        S.block(D.table(["market", "pooled kg", "rate worked out",
                         "Q (kg/yr)", "Qm (kg/yr)", "multiplier worked out",
                         "multiplier"], rows, "wide"))
        terms = []
        for phase, kg in mix.items():
            key = C["market_keys"].get(phase, phase)
            terms.append("%s * %s * %s" % (P(kg), P(price.get(phase, 0.0)),
                                           P(rev["multipliers"][key])))
        S.step("Rev", "Rev", "what one delivery sells",
               "sum over phases of kg * price * its market's multiplier",
               " + ".join(terms), rev["capped"]["value"], "$",
               ["hold_value", "eps_d", "F", "T_miss"])
    else:
        S.step("window", "omega", "how long one delivery's market "
               "accumulates", "(T_miss + (N - 1) * T_cad / F) / N",
               "(%s + (%s - 1) * %s / %s) / %s"
               % (P(M["duration"]), P(n), P(M["cadence"]), P(f), P(n)),
               rev["window"], "yr", ["T_miss", "N", "T_cad", "F"])
        keys = market_inputs(S, C, sorted(rev["allow"]))
        rows = []
        for market, allow in sorted(rev["allow"].items()):
            cap = C["market_kg"].get(market)
            work = S.claim("%s * %s" % (P(cap), P(rev["window"])), allow,
                           "%s allowance" % market,
                           [keys[market], "window"])
            rows.append([D.esc(market), P(cap), work, P(allow)])
        S.block(D.table(["market", "ceiling (kg/yr)", "allowance worked out",
                         "allowance (kg)"], rows))
        surplus_frac = rev["surplus_frac"]
        if surplus_frac > 0:
            S.put("surplus", "s", "price fraction past a ceiling",
                  surplus_frac, "-", cite_config("surplus_price_fraction"))
        walk = rev["capped"]["walk"]
        if not C["beneficiated"]:
            S.prose("A run-of-mine hold is the body's own proportions, so "
                    "nothing is chosen: each phase sells what fits inside its "
                    "market's allowance at full price, and what is over it "
                    "%s." % ("earns the surplus price" if surplus_frac > 0
                             else "earns nothing, because this run abandoned "
                                  "the surplus"))
            rows, terms = [], []
            # Two phases can sell into one market (the residual and the
            # silicates do), and the second is offered what the first left:
            # its allowance is a remainder, written out as one.
            drawn = {}
            for step in walk:
                full_value = step["full"] * step["price"]
                full_work = S.claim("%s * %s" % (P(step["full"]),
                                                 P(step["price"])),
                                    full_value,
                                    "%s at full price" % step["phase"])
                term = "%s * %s" % (P(step["full"]), P(step["price"]))
                over_work, over_value = "-", 0.0
                if step["over"] > 0 and surplus_frac > 0.0:
                    over_value = step["over"] * step["price"] * surplus_frac
                    over_work = S.claim(
                        "%s * %s * %s" % (P(step["over"]), P(step["price"]),
                                          P(surplus_frac)),
                        over_value, "%s surplus" % step["phase"])
                    term += " + %s * %s * %s" % (P(step["over"]),
                                                 P(step["price"]),
                                                 P(surplus_frac))
                terms.append(term)
                allowance = step["allowance"]
                key = C["market_keys"].get(step["phase"], step["phase"])
                allow_txt = ("-" if allowance is None
                             or allowance == float("inf")
                             else P(allowance))
                if key in drawn and allow_txt != "-":
                    prev_allow, prev_sold = drawn[key]
                    allow_txt = S.claim("%s - %s" % (P(prev_allow),
                                                     P(prev_sold)), allowance,
                                        "%s allowance left" % step["phase"])
                if allowance not in (None, float("inf")):
                    drawn[key] = (allowance, step["full"])
                # The mass past the ceiling is the hold less the allowance,
                # shown as such: on a run that abandoned the surplus it was a
                # bare number, the one cell of this table with no working.
                over_kg = P(step["over"])
                if step["over"] > 0 and allowance not in (None, float("inf")):
                    over_kg = S.claim("%s - %s" % (P(step["hold"]),
                                                   P(allowance)),
                                      step["over"],
                                      "%s past its ceiling" % step["phase"])
                # A phase that sold past its ceiling is worth two tiers, and
                # the cell says so: it was a bare sum, untraced, on 2014 YN.
                value_cell = "$" + P(full_value + over_value)
                if over_value > 0:
                    value_cell = "%s = %s" % (
                        S.claim("%s + %s" % (P(full_value), P(over_value)),
                                full_value + over_value,
                                "%s value" % step["phase"]), value_cell)
                rows.append([D.esc(step["phase"]), "$" + P(step["price"]),
                             P(step["hold"]), allow_txt,
                             P(step["full"]), full_work,
                             over_kg, over_work, value_cell])
            S.block(D.table(["phase", "$/kg", "in the hold (kg)",
                             "allowance (kg)", "sold at full (kg)",
                             "full value worked out", "over (kg)",
                             "surplus worked out", "value"], rows, "wide"))
            S.step("Rev", "Rev", "what one delivery sells",
                   "sum over phases of sold * price"
                   + (", plus over * price * s" if surplus_frac > 0 else ""),
                   " + ".join(terms), rev["capped"]["value"], "$",
                   ["window", "hold_value"]
                   + (["surplus"] if surplus_frac > 0 else []))
        else:
            S.prose("The load is RESHAPED, not clipped: the ceilings go into "
                    "the knapsack, so space a capped phase does not take "
                    "passes to the next phase down, and a bounded hold can "
                    "still fly full.%s"
                    % ("  Past a ceiling a phase sells at the surplus price, "
                       "as a second tier further down the price order."
                       if surplus_frac > 0 else ""))
            rows = []
            for i, step in enumerate(walk, 1):
                if step["full"]:
                    price_work = "the full price"
                else:
                    price_work = S.claim(
                        "%s * %s" % (P(step["price"] / surplus_frac),
                                     P(surplus_frac)), step["price"],
                        "%s surplus price" % step["phase"])
                value = S.claim("%s * %s" % (P(step["take"]),
                                             P(step["price"])),
                                step["take"] * step["price"],
                                "%s tier %d value" % (step["phase"], i))
                rows.append([ordinal(i), D.esc(step["phase"]),
                             "full" if step["full"] else "surplus",
                             price_work, "$" + P(step["price"]),
                             P(step["supply"]),
                             "-" if step["allowance"] is None
                             else P(step["allowance"]),
                             P(step["take"]), value,
                             "$" + P(step["take"] * step["price"])])
            S.block(D.table(["#", "phase", "tier", "price worked out", "$/kg",
                             "supply (kg)", "allowance (kg)", "sold (kg)",
                             "value worked out", "value"], rows, "wide"))
            S.step("Rev", "Rev", "what one delivery sells",
                   "sum over tiers of sold * price",
                   " + ".join("%s * %s" % (P(t["take"]), P(t["price"]))
                              for t in walk if t["take"] > 0),
                   rev["capped"]["value"], "$",
                   ["window", "hold_value"]
                   + (["surplus"] if surplus_frac > 0 else []))
    S.step("clearing", "clearing", "fraction of the unbounded hold that sold",
           "Rev / V_hold",
           "%s / %s" % (P(rev["capped"]["value"]), P(rev["gross_base"])),
           rev["clearing"] if mode != "elasticity"
           else rev["capped"]["value"] / rev["gross_base"],
           "-", ["Rev", "hold_value"],
           "every kilogram cleared, at a lower price: the model reports a "
           "clearing of 1 and the haircut in saturation_multiplier"
           if mode == "elasticity" else "")
    S.step("delivered", "V_del", "delivered value per kilogram flown",
           "Rev / m_pay",
           "%s / %s" % (P(rev["capped"]["value"]), P(M["m_pay"])),
           rev["delivered"], "$/kg", ["Rev", "m_pay"])


# --------------------------------------------------------- 12. the searches
def part_searches(S, out):
    """The two searches that chose the concentration ratio and the programme."""
    C, M, L = out["C"], out["M"], out["ladder"]
    sweep = out["sweep"]
    S.part("searches", "The two searches",
           "Neither the ratio nor the programme size is a setting; both "
           "are priced.  The ladders are printed so the winner can be "
           "checked as the argmin of the column beside it.")
    if C["beneficiated"]:
        best_name, best_frac, _best_price = max(C["phases"],
                                                key=lambda ph: ph[2])
        # The search is capped at `max_concentration_ratio`.  This step wrote
        # the uncapped formula until 2026-10-05, when the v1.40.0 mars_surface
        # winner became the first best case whose cap binds, and `--check`
        # caught "1 / (0.00477 * 0.9)" printed beside 50.
        S.put("r_cap", "r_cap", "concentration ratio ceiling",
              C["cfg"].max_concentration_ratio, "-",
              cite_config("max_concentration_ratio"))
        uncapped = 1.0 / (best_frac * C["recovery"])
        if uncapped > C["cfg"].max_concentration_ratio:
            S.claim("1 / (%s * %s)" % (P(best_frac), P(C["recovery"])),
                    uncapped, "the uncapped saturation ratio")
        S.step("r_max", "r_max", "saturation ratio, capped",
               "max(1, min(1 / (f_best * eps_rec), r_cap)), f_best being the "
               "fraction of the best-PRICED phase (%s) and not of the "
               "commonest" % best_name,
               "max(1, min(1 / (%s * %s), %s))"
               % (P(best_frac), P(C["recovery"]),
                  P(C["cfg"].max_concentration_ratio)),
               sweep["r_max"], "-", ["eps_rec", "r_cap"],
               "above the body's own ratio the hold is pure best-phase and "
               "grade stops improving, while the costs do not; %s"
               % ("the cap binds here, because 1 / (f_best eps_rec) is "
                  + P(uncapped) if uncapped > C["cfg"].max_concentration_ratio
                  else "the cap does not bind here"))
        S.put("r_steps", "steps", "rungs on the coarse ladder",
              C["cfg"].concentration_search_steps, "-",
              cite_config("concentration_search_steps"))
        S.step("r_step", "step", "the coarse ladder's geometric step",
               "r_max ^ (1 / (steps - 1))",
               "%s ^ (1 / (%s - 1))"
               % (P(sweep["r_max"]), P(C["cfg"].concentration_search_steps)),
               sweep["step"], "-", ["r_max", "r_steps"])
        S.prose("A different concentration ratio is a different feed, a "
                "different payload, a different plant and a different sale, "
                "so every rung below is a whole mission, and its last "
                "column is C_tot / E[Rev] computed exactly as %s computes "
                "it." % ref("answer"))
        rows = []
        for kind, ratio, won in sweep["rungs"]:
            mark = " <b>argmin</b>" if (kind, ratio) == (
                sweep["winner"][0], sweep["winner"][1]) else ""
            if won is None:
                # A rung where no mission closes: `concentration_sweep`
                # keeps it and the winner skips it, and indexing it here
                # crashed the sheet on the first body that had one.
                rows.append([kind, P(ratio), "-", "-", "-", "-", "-", "-",
                             "no mission closes at this ratio", "-"])
                continue
            best = won["ladder"]["best"]
            obj = S.claim("%s / %s" % (P(best["cost"]["total"]),
                                       P(best["expected"])), best["obj"],
                          "objective at ratio %s" % P(ratio))
            rows.append([kind, P(ratio), P(won["M"]["m_pay"]),
                         P(won["M"]["feed"]),
                         "$" + P(best["rev"]["delivered"]),
                         "(%d, %d)" % (best["f"], best["w"]),
                         P(best["cost"]["total"], 12),
                         P(best["expected"], 12), obj,
                         P(best["obj"]) + mark])
        S.block(D.table(["rung", "ratio", "payload (kg)", "feed (kg)",
                         "delivered $/kg", "best (F, W)", "total cost $",
                         "expected revenue $", "objective worked out",
                         "cost / revenue"], rows, "wide"),
                rerun=rerun_sweep())
    fleets = sorted(set(r["f"] for r in L["coarse"]))
    ws = sorted(set(r["w"] for r in L["coarse"]))
    if out["terms"]["searched"]:
        S.prose("A larger programme amortises the NRE over more missions; a "
                "larger fleet gets a smaller slice of the market.  The "
                "optimum is where those turn over.  The ladder's SHAPE is the "
                "model's own <i>programme_options</i>: a geometric ladder of "
                "fleets up to F_max, crossed with every W from 1 to the "
                "rig's trips.")
        S.put("F_max", "F_max", "largest fleet the ladder may try",
              C["cfg"].max_fleet_ships, "ships",
              cite_config("max_fleet_ships"))
        S.put("F_steps", "F_steps", "rungs on the fleet ladder",
              C["cfg"].programme_search_steps, "-",
              cite_config("programme_search_steps"))
        S.step("F_top", "F_top", "the largest fleet the coarse ladder priced",
               "max of the fleets the ladder proposed",
               "max(%s)" % ", ".join(str(x) for x in fleets),
               float(max(fleets)), "ships", ["F_max", "F_steps"],
               "%s against a cap of %s"
               % ("AT the cap: raising F_max could still improve this "
                  "answer" if max(fleets) >= C["cfg"].max_fleet_ships
                  else "under the cap", P(C["cfg"].max_fleet_ships)))
        S.step("W_top", "W_top", "the most campaigns per ship the ladder "
               "tried", "max of 1 .. trips",
               "max(%s)" % ", ".join(str(x) for x in ws), float(max(ws)),
               "-", ["trips"])
    else:
        S.prose("The programme search was OFF on this run "
                "(<i>optimise_programme_scale</i>, read off the row), so the "
                "ladder below has one rung: N is fixed.")
        S.put("N_fixed", "N_fixed", "the fixed programme size",
              out["terms"]["n_fixed"], "missions",
              cite_config("nre_amortization_missions")
              + "  Read off the row's <i>programme_missions</i>.")
        S.step("N_check", "N", "the programme flown", "N_fixed",
               P(out["terms"]["n_fixed"]), float(out["terms"]["n_fixed"]),
               "missions", ["N_fixed"])
    grid = dict(((r["f"], r["w"]), r["obj"]) for r in L["coarse"])
    rows = []
    for f in fleets:
        rows.append([str(f)] + [P(grid[(f, w)]) if (f, w) in grid else "-"
                                for w in ws])
    S.block(D.table(["fleet F"] + ["W = %d" % w for w in ws], rows, "wide"),
            rerun=rerun_ladder())
    if L["refine"]:
        S.prose("One refinement pass runs around the coarse winner at its "
                "own W, which is what makes the search non-exhaustive.")
        rows = []
        for r in L["refine"]:
            obj = S.claim("%s / %s" % (P(r["cost"]["total"]),
                                       P(r["expected"])), r["obj"],
                          "refined objective at N = %d" % r["n"])
            rows.append([P(r["n"]), str(r["f"]), str(r["w"]),
                         P(r["cost"]["total"], 12), P(r["expected"], 12),
                         obj, P(r["obj"])])
        S.block(D.table(["N", "ships", "campaigns/ship", "total cost $",
                         "expected revenue $", "objective worked out",
                         "cost / revenue"], rows, "wide"),
                rerun=rerun_fleet())
    S.prose("The table below holds W at the winner's own, so only the fleet "
            "moves.  Cost falls all the way down it; what stops it is the "
            "accumulation window.")
    rows = []
    at_w = sorted((r for r in L["coarse"] + L["refine"]
                   if r["w"] == out["P"]["w"]), key=lambda r: r["f"])
    for r in at_w:
        mark = " <b>argmin</b>" if r["f"] == out["P"]["f"] else ""
        obj = S.claim("%s / %s" % (P(r["cost"]["total"]), P(r["expected"])),
                      r["obj"], "objective at F = %d" % r["f"])
        rows.append([str(r["f"]), P(r["n"]),
                     P(r["rev"]["window"])
                     if math.isfinite(r["rev"]["window"]) else
                     "none: %s has no ceiling" % D.esc(r["rev"]["mode"]),
                     P(r["rev"]["clearing"]),
                     P(r["rev"]["surplus"] + r["rev"]["unsold"]),
                     P(r["cost"]["total"], 12), P(r["expected"], 12),
                     obj, P(r["obj"]) + mark])
    S.block(D.table(["fleet F", "N", "omega (yr)", "clearing",
                     "past the ceiling (kg)", "total cost $",
                     "expected revenue $", "objective worked out",
                     "cost / revenue"], rows, "wide"),
            rerun=rerun_fleet())


# ------------------------------------------------------- 13. the reliability
def part_reliability(S, out):
    """The discount the model applies when it is asked to."""
    C, P_, M_ = out["C"], out["P"], out["M"]
    rel = P_["rel"]
    S.part("reliability", "Reliability",
           "P = p_launch * exp(-T / MTBF) * p_mining, applied to revenue.")
    if rel["off"]:
        S.prose("<b>Not charged on this run</b> (<i>model_reliability</i>, "
                "read off the row's <i>p_success</i>): all three factors are "
                "exactly 1.0, so expected and gross revenue are the same "
                "number everywhere below.")
        S.step("P_succ", "P", "probability the mission delivers",
               "1: revenue is not discounted on this run", "1",
               rel["p_succ"], "-", ["Rev"])
    else:
        val = C["val"]
        S.put("p_launch", "p_launch", "launch vehicle reliability",
              rel["p_launch"], "-", cite_ops(C, "Launch vehicle reliability"))
        S.put("MTBF", "MTBF", "spacecraft mean time between failures",
              rel["mtbf"], "yr",
              cite_ops(C, "Spacecraft mean time between failures"))
        S.step("p_cruise", "p_cruise", "surviving the mission's duration",
               "exp(-T_miss / MTBF)",
               "exp(-%s / %s)" % (P(M_["duration"]), P(rel["mtbf"])),
               rel["p_cruise"], "-", ["T_miss", "MTBF"])
        q1 = 1.0 - val("Mining system first-of-kind success probability",
                       used=False)
        alpha = val("Mining reliability growth exponent", used=False)
        q_max = val("Mining system mature success probability", used=False)
        S.put("p_first", "p_1", "first-of-kind mining success",
              1.0 - q1, "-",
              cite_ops(C, "Mining system first-of-kind success probability"))
        S.put("alpha", "alpha", "mining reliability growth exponent",
              alpha, "-", cite_ops(C, "Mining reliability growth exponent"))
        S.put("p_mature", "p_max", "mature mining success", q_max, "-",
              cite_ops(C, "Mining system mature success probability"))
        rows = []
        for k, term in enumerate(rel["terms"], 1):
            work = S.claim("1 - max((1 - %s) * %d ^ -%s, 1 - %s)"
                           % (P(1.0 - q1), k, P(alpha), P(q_max)), term,
                           "mining success of mission %d" % k)
            rows.append([ordinal(k), work, P(term, 12)])
        S.block(D.table(["mission k", "success worked out", "p_k"], rows))
        S.step("p_mining", "p_mining", "mining success, averaged over the "
               "programme", "sum of p_k / N",
               "(%s) / %d" % (" + ".join(P(t) for t in rel["terms"]),
                              len(rel["terms"])),
               rel["p_mining"], "-", ["p_first", "alpha", "p_mature", "N"],
               "only mining learns; launch vehicles are mature and MTBF is "
               "an exposure, not a heritage question")
        S.step("P_succ", "P", "probability the mission delivers",
               "min(1, max(0, p_launch * p_cruise * p_mining))",
               "min(1, max(0, %s * %s * %s))"
               % (P(rel["p_launch"]), P(rel["p_cruise"]),
                  P(rel["p_mining"])),
               rel["p_succ"], "-", ["p_launch", "p_cruise", "p_mining"])
    S.step("E_Rev", "E[Rev]", "expected revenue", "P * Rev",
           "%s * %s" % (P(rel["p_succ"]), P(P_["rev"]["capped"]["value"])),
           P_["expected"], "$", ["P_succ", "Rev"])


# ------------------------------------------------------ 14. the cost cascade
def part_cost(S, out):
    """Every cost line, the three buckets, contingency and the total."""
    C, M, P_ = out["C"], out["M"], out["P"]
    K = P_["cost"]
    lines = K["lines"]
    S.part("cost", "The cost cascade",
           "Every line comes from a reference table, then is bucketed by "
           "WHEN it is spent, which is what decides how it compounds.")
    S.put("c_veh", "c_veh", "launch price", float(C["veh"].raw(
        "usd_per_kg_to_leo")), "$/kg to LEO",
        cite_table_row(C["veh"], "launch_vehicles.csv", C["veh"].raw("name"),
                       ("list_price_usd", "payload_leo_kg", "reference_year")))
    S.step("L_launch", "C_launch", "launch", "m_launch * c_veh",
           "%s * %s" % (P(M["m_launch"]), P(C["veh"].raw(
               "usd_per_kg_to_leo"))),
           lines["launch"], "$", ["m_launch", "c_veh"])
    S.put("c_prop", "c_prop", "propellant price", C["prop_usd_per_kg"],
          "$/kg",
          ("<b>profitability_catalog</b>, recovered from this row as "
           "outbound_prop_cost_usd / m_outbound_prop_kg, because the Stage 3 "
           "table on disk has moved since the run.  "
           if C["prop_moved"] is not None else "")
          + cite_table_row(C["pro"], "propellants.csv", C["pro"].raw("name"),
                           ("price_basis", "live_price_source",
                            "reference_year")))
    S.step("L_oprop", "C_oprop", "outbound propellant", "m_oprop * c_prop",
           "%s * %s" % (P(M["m_oprop"]), P(C["prop_usd_per_kg"])),
           lines["oprop"], "$", ["m_oprop", "c_prop"])
    if C["isru"]:
        # Three ways `isru_processing_terms` settles the rate, three origins:
        # the config field, the retired $50 it names as a constant, or the
        # row's own columns (whose reason already carries their `<i>` names).
        how = C["isru_opex_how"]
        if how.startswith("this process"):
            isru_cite = cite_config("isru_processing_usd_per_kg")
        elif how.startswith("calc's flat"):
            isru_cite = cite_here(
                "ISRU_OPEX_BEFORE_V132",
                "calc's default for isru_processing_usd_per_kg until 1.32.0 "
                "retired it.  The row was billed it: its "
                "return_prop_cost_usd over m_return_prop_kg agrees to 1e-9.")
        else:
            isru_cite = how
        S.put("c_isru", "c_ISRU", "flat processing cost of propellant made "
              "on site", C["isru_opex"], "$/kg", isru_cite)
    S.step("L_rprop", "C_rprop", "return propellant",
           "m_rprop * %s" % ("c_ISRU" if C["isru"] else "c_prop"),
           "%s * %s" % (P(M["m_rprop"]),
                        P(C["isru_opex"] if C["isru"]
                          else C["prop_usd_per_kg"])),
           lines["rprop"], "$", ["m_rprop", "c_isru" if C["isru"]
                                 else "c_prop"],
           "made at the asteroid over the dig, so it is an ONGOING line"
           if C["isru"] else "")
    S.put("c_rig", "c_rig", "mining rig recurring cost",
          C["val"]("Mining payload recurring cost", used=False), "$/kg",
          cite_ops(C, "Mining payload recurring cost"))
    if M.get("isru_plant", 0.0) > 0:
        S.step("C_rig_total", "C_rig", "one rig and the plants on it, built once",
               "(m_rig + m_ref + m_iplant) * c_rig",
               "(%s + %s + %s) * %s" % (P(C["cfg"].mining_hardware_kg),
                                        P(M.get("refinery", 0.0)),
                                        P(M["isru_plant"]),
                                        P(C["val"]("Mining payload recurring cost",
                                                   used=False))),
               K["rig_total"], "$", ["m_rig", "m_iplant", "c_rig"]
               + (["m_ref"] if M.get("refinery", 0.0) > 0 else []))
    elif M.get("refinery", 0.0) > 0:
        S.step("C_rig_total", "C_rig", "one rig and its refinery, built once",
               "(m_rig + m_ref) * c_rig",
               "(%s + %s) * %s" % (P(C["cfg"].mining_hardware_kg),
                                   P(M["refinery"]),
                                   P(C["val"]("Mining payload recurring cost",
                                              used=False))),
               K["rig_total"], "$", ["m_rig", "m_ref", "c_rig"])
    else:
        S.step("C_rig_total", "C_rig", "one rig, built once", "m_rig * c_rig",
               "%s * %s" % (P(C["cfg"].mining_hardware_kg),
                            P(C["val"]("Mining payload recurring cost",
                                       used=False))),
               K["rig_total"], "$", ["m_rig", "c_rig"])
    S.step("rig_used", "util", "how much of the rig's life this uses",
           "min(1, max(W t_stay / L_rig, W / trips))",
           "min(1, max(%s * %s / %s, %s / %s))"
           % (P(K["share"]), P(M["stay"]),
              P(C["val"]("Mining rig service life", used=False)),
              P(K["share"]), P(M["trips"])),
           K["used"], "-", ["Wc", "stay", "L_rig", "trips"])
    S.put("salvage", "salvage", "rig salvage fraction",
          C["val"]("Rig salvage fraction", used=False), "-",
          cite_ops(C, "Rig salvage fraction"))
    # A single mission salvages nothing: the model credits a terminal
    # value only when N > 1 (`cost` in worked_calculation, which mirrors
    # calc).  The formula without that condition printed a nine-figure
    # credit beside a page value of 0 on every N = 1 row.
    if P_["n"] > 1:
        S.step("rig_term", "terminal", "salvage credit on what is left",
               "C_rig (1 - util) * salvage, when N > 1",
               "%s * (1 - %s) * %s"
               % (P(K["rig_total"]), P(K["used"]),
                  P(C["val"]("Rig salvage fraction", used=False))),
               K["terminal"], "$", ["C_rig_total", "rig_used", "salvage", "N"])
    else:
        S.step("rig_term", "terminal", "salvage credit on what is left",
               "0 when N = 1: the rig's remaining life goes unsold", "0",
               K["terminal"], "$", ["N", "salvage"])
    S.step("L_rig_share", "C_rig/W", "this mission's share of the rig",
           "(C_rig - terminal) / W",
           "(%s - %s) / %s" % (P(K["rig_total"]), P(K["terminal"]),
                               P(K["share"])),
           lines["rig"], "$", ["C_rig_total", "rig_term", "Wc"])
    S.put("c_cap", "c_cap", "%s recurring cost" % C["arch_label"],
          C["capsule_per_kg"], "$/kg",
          cite_ops(C, ops_row_read("Berthing adapter recurring cost",
                                   "Return capsule recurring cost",
                                   "Surface lander recurring cost")))
    if out["terms"]["learning"]:
        rate = C["cfg"].learning_curve_rate
        S.put("lc_rate", "b_LC", "learning-curve rate", rate, "-",
              cite_config("learning_curve_rate"))
        n_m = P_["n"]
        expo = math.log(rate, 2)
        S.step("lc_exp", "beta_LC", "Wright's-law exponent", "log2(b_LC)",
               "log(%s, 2)" % P(rate), expo, "-", ["lc_rate"])
        # Every term written out, however many: an ellipsis is a Python
        # literal, so "1 ^ b + ... + 320 ^ b" PARSED, and the check rightly
        # called it wrong rather than abbreviated.
        #
        # 🚨  BUT NOT ON ONE LINE.  At N = 320 the substitution was a single
        # table row 1,484 px tall against a 996 px sheet, which no page break
        # can split, on every searched `earth_surface` page; the paper check
        # found it on its first sweep.  Past LC_GROUP terms the sum is laid
        # out in groups, each a checked claim that writes its own terms out,
        # and the step adds the groups' subtotals: every term is still on the
        # page and every line is still arithmetic.
        terms = ["%d ^ %s" % (k, exact(expo)) for k in range(1, n_m + 1)]
        if n_m <= LC_GROUP:
            sub = "(%s) / %d" % (" + ".join(terms), n_m)
        else:
            rows, subtotals = [], []
            for lo in range(0, n_m, LC_GROUP):
                group = terms[lo:lo + LC_GROUP]
                total = sum(k ** expo
                            for k in range(lo + 1, lo + len(group) + 1))
                rows.append([S.claim(" + ".join(group), total,
                                     "learning-curve terms",
                                     uses=["lc_exp"]),
                             P(total, 12)])
                subtotals.append(exact(total))
            S.prose("The mean below runs over every unit of the "
                    "programme, so its terms are added here in groups, each "
                    "written out in full, and the step adds the groups.")
            S.block(D.table(["how it is worked out", "subtotal"], rows,
                            "wide"))
            sub = "(%s) / %d" % (" + ".join(subtotals), n_m)
        S.step("lc", "LC", "learning-curve factor",
               "mean over k = 1..N of k ^ beta_LC", sub,
               K["lc"], "-", ["lc_exp", "N"],
               "Wright's law: each doubling of units costs b_LC of the last")
    else:
        S.put("lc", "LC", "learning-curve factor", K["lc"], "-",
              cite_config("model_learning_curve")
              + "  Not charged on this run (read off the row's "
              "<i>learning_curve_factor</i>), so it is exactly 1.0.")
    S.step("L_capsule", "C_cap", "the vehicle that meets the cargo",
           "m_dry * c_cap * LC",
           "%s * %s * %s" % (P(M["m_dry"]), P(C["capsule_per_kg"]), P(K["lc"])),
           lines["capsule"], "$", ["m_dry", "c_cap", "lc"],
           "billed on the return vehicle ACTUALLY FLOWN, whose dry mass "
           "grows with the haul, not on the base article")
    if lines["tps"] > 0:
        S.put("c_tps", "c_TPS", "heat shield", C["tps_per_kg"], "$/kg",
              cite_ops(C, "Heat shield / TPS for Earth return"))
        S.step("L_tps", "C_TPS", "heat shield", "m_TPS * c_TPS * LC",
               "%s * %s * %s" % (P(M["m_tps"]), P(C["tps_per_kg"]),
                                 P(K["lc"])),
               lines["tps"], "$", ["m_tps", "c_tps", "lc"])
    S.put("c_W", "c_W", "power plant", C["plant_usd_per_w"], "$/W",
          cite_ops(C, "RTG (radioisotope power)"
                   if C["power_source"] == "rtg"
                   else "Power system (solar + battery)"))
    S.step("L_plant", "C_plant", "power system", "P * c_W * LC",
           "%s * %s * %s" % (P(M["draw"]), P(C["plant_usd_per_w"]),
                             P(K["lc"])),
           lines["plant"], "$", ["draw", "c_W", "lc"],
           "priced on the DRAW rather than on the mass, which is how a "
           "radioisotope plant and a solar one are told apart")
    if M["ep"]["power"] > 0:
        S.put("c_kW", "c_kW", "electric drive",
              C["val"]("Electric propulsion system recurring cost",
                       used=False), "$/kW",
              cite_ops(C, "Electric propulsion system recurring cost"))
        S.step("L_ep", "C_EP", "electric stage",
               "(P_EP * c_W + P_EP / 1000 * c_kW) * LC",
               "(%s * %s + %s / 1000 * %s) * %s"
               % (P(M["ep"]["power"]), P(C["plant_usd_per_w"]),
                  P(M["ep"]["power"]),
                  P(C["val"]("Electric propulsion system recurring cost",
                             used=False)), P(K["lc"])),
               lines["ep"], "$", ["P_ep", "c_W", "c_kW", "lc"])
    S.put("c_tank", "c_tank", "propellant tank",
          C["val"]("Propellant tank recurring cost", used=False), "$/kg",
          cite_ops(C, "Propellant tank recurring cost"))
    S.step("L_tank", "C_tank", "tankage",
           "(m_tank,ret + m_tank,out) * c_tank * LC",
           "(%s + %s) * %s * %s"
           % (P(M["m_tank_ret"]), P(M["m_tank_out"]),
              P(C["val"]("Propellant tank recurring cost", used=False)),
              P(K["lc"])),
           lines["tank"], "$", ["m_tank_ret", "m_tank_out", "c_tank", "lc"])
    S.step("hardware", "C_hw", "hardware subtotal",
           "rig share + capsule + plant + EP + tank",
           "%s + %s + %s + %s + %s"
           % (P(lines["rig"]), P(lines["capsule"]), P(lines["plant"]),
              P(lines["ep"]), P(lines["tank"])),
           K["hardware"], "$",
           ["L_rig_share", "L_capsule", "L_plant", "L_tank"]
           + (["L_ep"] if M["ep"]["power"] > 0 else []),
           "term by term: the sum interleaves N-dependent and N-independent "
           "lines, so pre-adding a prefix re-associates it")
    S.put("c_ops", "c_ops", "mission operations",
          C["val"]("Mission operations", used=False), "$/yr",
          cite_ops(C, "Mission operations"))
    S.step("L_ops", "C_ops", "operations", "T_miss * c_ops",
           "%s * %s" % (P(M["duration"]),
                        P(C["val"]("Mission operations", used=False))),
           K["ops"], "$", ["T_miss", "c_ops"])
    S.put("nre_bus", "NRE_bus", "spacecraft development",
          C["val"]("Spacecraft development (NRE)", used=False), "$",
          cite_ops(C, "Spacecraft development (NRE)"))
    S.put("nre_overlap", "overlap", "recurring overlap deducted from NRE",
          C["cfg"].nre_recurring_overlap_fraction, "-",
          cite_config("nre_recurring_overlap_fraction"))
    S.step("L_nre", "C_NRE", "spacecraft NRE, per mission",
           "NRE_bus * (1 - overlap) / N",
           "%s * (1 - %s) / %s"
           % (P(C["val"]("Spacecraft development (NRE)", used=False)),
              P(C["cfg"].nre_recurring_overlap_fraction), P(P_["n"])),
           K["nre"], "$", ["nre_bus", "nre_overlap", "N"])
    S.put("nre_aut", "NRE_aut", "autonomous mining control",
          C["val"]("Autonomous mining control & AI (NRE)", used=False), "$",
          cite_ops(C, "Autonomous mining control & AI (NRE)"))
    S.step("L_aut", "C_aut", "autonomy NRE, per mission", "NRE_aut / N",
           "%s / %s" % (P(C["val"]("Autonomous mining control & AI (NRE)",
                                   used=False)), P(P_["n"])),
           K["autonomy"], "$", ["nre_aut", "N"])
    S.put("licensing", "C_lic", "launch licensing", K["licensing"], "$",
          cite_ops(C, ops_row_read("FAA Part 450 licensing (launch only)",
                                   "FAA Part 450 licensing compliance")))
    S.put("handover", "C_end", "end-of-mission handover", K["handover"], "$",
          cite_ops(C, ops_row_read("Depot berthing & handover operations",
                                   "Sample recovery operations")))

    ins_keys = []
    if out["terms"]["insurance"]:
        S.put("liability", "C_liab", "third-party liability insurance",
              K["liability"], "$",
              cite_ops(C, "Third-party liability insurance"))
        ins_rate = C["val"]("Launch insurance", used=False)
        S.put("ins_rate", "i_launch", "launch insurance premium",
              ins_rate, "% of what is launched",
              cite_ops(C, "Launch insurance"))
        book = (K["rig_total"] + lines["capsule"] + lines["plant"]
                + lines["ep"] + lines["tank"] + lines["tps"])
        S.step("book", "book", "the replacement cost of what is launched",
               "C_rig + C_cap + C_plant + C_EP + C_tank + C_TPS",
               "%s + %s + %s + %s + %s + %s"
               % (P(K["rig_total"]), P(lines["capsule"]), P(lines["plant"]),
                  P(lines["ep"]), P(lines["tank"]), P(lines["tps"])),
               book, "$", ["C_rig_total", "L_capsule", "L_plant", "L_tank"],
               "the rig at its FULL build cost: losing it on ascent destroys "
               "the whole unit however many missions were to share it")
        S.step("launch_ins", "C_ins", "launch insurance",
               "i_launch / 100 * (C_launch + book)",
               "%s / 100 * (%s + %s)" % (P(ins_rate), P(lines["launch"]),
                                         P(book)),
               K["launch_ins"], "$", ["ins_rate", "L_launch", "book"])
        ins_keys = ["liability", "launch_ins"]
    S.prose("Bucketed before any rate is applied.%s"
            % ("" if out["terms"]["insurance"] else
               "  The two insurance lines are zero: not charged on this run "
               "(<i>charge_insurance</i>, read off the row)."))
    S.step("upfront_lines", "upfront", "money spent at year zero",
           "launch + oprop + hardware + TPS + licensing + liability "
           "+ launch insurance + NRE + autonomy"
           + ("" if C["isru"] else " + rprop"),
           "%s + %s + %s + %s + %s + %s + %s + %s + %s%s"
           % (P(lines["launch"]), P(lines["oprop"]), P(K["hardware"]),
              P(lines["tps"]), P(K["licensing"]), P(K["liability"]),
              P(K["launch_ins"]), P(K["nre"]), P(K["autonomy"]),
              "" if C["isru"] else " + " + P(lines["rprop"])),
           K["upfront_lines"], "$",
           ["L_launch", "L_oprop", "hardware", "licensing", "L_nre", "L_aut"]
           + ins_keys + ([] if C["isru"] else ["L_rprop"])
           + (["L_tps"] if "L_tps" in S.tag else []))
    ongoing_lines = K["ops"] + (lines["rprop"] if C["isru"] else 0.0)
    # On an ISRU mission the made propellant is billed across the mission, so
    # the sum is shown with both terms; it printed the total alone, citing
    # only the operations line it had added something to.
    if C["isru"]:
        S.step("ongoing_lines", "ongoing", "money spent across the mission",
               "operations + rprop",
               "%s + %s" % (P(K["ops"]), P(lines["rprop"])), ongoing_lines,
               "$", ["L_ops", "L_rprop"])
    else:
        S.step("ongoing_lines", "ongoing", "money spent across the mission",
               "operations", P(ongoing_lines), ongoing_lines, "$",
               ["L_ops"])
    S.put("zeta", "zeta", "contingency reserve",
          C["cfg"].contingency_fraction, "-",
          cite_config("contingency_fraction"))
    S.step("upfront", "upfront*", "up front, after contingency",
           "upfront * (1 + zeta)",
           "%s * (1 + %s)" % (P(K["upfront_lines"]),
                              P(C["cfg"].contingency_fraction)),
           K["upfront"], "$", ["upfront_lines", "zeta"])
    S.step("ongoing", "ongoing*", "ongoing, after contingency",
           "ongoing * (1 + zeta)",
           "%s * (1 + %s)" % (P(ongoing_lines),
                              P(C["cfg"].contingency_fraction)),
           K["ongoing"], "$", ["ongoing_lines", "zeta"])
    S.step("end", "end*", "end of mission, after contingency",
           "handover * (1 + zeta)",
           "%s * (1 + %s)" % (P(K["handover"]),
                              P(C["cfg"].contingency_fraction)),
           K["end"], "$", ["handover", "zeta"])
    S.step("contingency", "reserve", "the contingency reserve itself",
           "zeta * (upfront + ongoing + end)",
           "%s * (%s + %s + %s)"
           % (P(C["cfg"].contingency_fraction), P(K["upfront_lines"]),
              P(ongoing_lines), P(K["handover"])),
           K["contingency"], "$", ["zeta", "upfront_lines", "ongoing_lines"])
    if out["terms"]["wacc"]:
        S.put("wacc", "r_c", "cost of capital", K["wacc"], "/yr",
              cite_ops(C, "Cost of capital (WACC)"))
    else:
        S.put("wacc", "r_c", "cost of capital", K["wacc"], "/yr",
              cite_config("apply_wacc_compounding")
              + "  Not charged on this run (read off the row's "
              "<i>wacc_multiplier_upfront</i>), so the rate is zero, both "
              "multipliers are exactly 1.0 and the programme calendar term "
              "is inert with it.")
    S.step("mult_up", "mult_up", "compounding on up-front money",
           "(1 + r_c) ^ T_miss",
           "(1 + %s) ^ %s" % (P(K["wacc"]), P(M["duration"])),
           K["mult_up"], "-", ["wacc", "T_miss"])
    S.step("mult_on", "mult_on", "compounding on ongoing money",
           "(1 + r_c) ^ (T_miss / 2)",
           "(1 + %s) ^ (%s / 2)" % (P(K["wacc"]), P(M["duration"])),
           K["mult_on"], "-", ["wacc", "T_miss"])
    if K["delta"] != 0.0:
        S.prose("W campaigns on one rig are sequential, so what is bought "
                "once and shared across them is carried for the whole "
                "programme, not one mission: the calendar charge.")
        y, share = K["y"], K["share"]
        S.step("cal_y", "y", "growth of money over one cadence",
               "(1 + r_c) ^ T_cad", "(1 + %s) ^ %s" % (P(K["wacc"]),
                                                      P(M["cadence"])),
               y, "-", ["wacc", "T_cad"])
        S.step("cal_cost", "cal_cost", "the carrying multiplier on shared "
               "spending", "(y ^ W - 1) / ((y - 1) W)",
               "(%s ^ %s - 1) / ((%s - 1) * %s)" % (P(y), P(share), P(y),
                                                    P(share)),
               K["cal_cost"], "-", ["cal_y", "Wc"])
        S.step("cal_credit", "cal_credit", "the same, on the salvage credit",
               "(1 - y ^ -W) / ((1 - 1 / y) W)",
               "(1 - %s ^ -%s) / ((1 - 1 / %s) * %s)" % (P(y), P(share),
                                                         P(y), P(share)),
               K["cal_credit"], "-", ["cal_y", "Wc"])
        S.step("prog_up", "C_shared", "what one mission's share of the "
               "programme buys up front", "C_NRE + C_aut + C_rig / W",
               "%s + %s + %s / %s" % (P(K["nre"]), P(K["autonomy"]),
                                      P(K["rig_total"]), P(share)),
               K["programme_upfront"], "$",
               ["L_nre", "L_aut", "C_rig_total", "Wc"])
        S.step("cal_delta", "delta", "programme calendar charge",
               "(C_shared (cal_cost - 1) - (terminal / W) (cal_credit - 1)) "
               "(1 + zeta) mult_up",
               "((%s * (%s - 1)) - (%s * (%s - 1))) * (1 + %s) * %s"
               % (P(K["programme_upfront"]), P(K["cal_cost"]),
                  P(K["rig_credit_share"]), P(K["cal_credit"]),
                  P(C["cfg"].contingency_fraction), P(K["mult_up"])),
               K["delta"], "$", ["prog_up", "cal_cost", "cal_credit",
                                 "rig_term", "zeta", "mult_up"])
    S.step("C_tot", "C_tot", "total cost of one mission of %d" % P_["n"],
           "upfront* mult_up + ongoing* mult_on + end*"
           + (" + delta" if K["delta"] != 0.0 else ""),
           "%s * %s + %s * %s + %s%s"
           % (P(K["upfront"]), P(K["mult_up"]), P(K["ongoing"]),
              P(K["mult_on"]), P(K["end"]),
              (" + " + P(K["delta"])) if K["delta"] != 0.0 else ""),
           K["total"], "$",
           ["upfront", "mult_up", "ongoing", "mult_on", "end"]
           + (["cal_delta"] if K["delta"] != 0.0 else []))


# ---------------------------------------------------------- 15. the answer
def part_answer(S, out):
    """The objective, and the two figures that are not it."""
    C, M, P_ = out["C"], out["M"], out["P"]
    K = P_["cost"]
    S.part("answer", "The answer",
           "The project ranks on cost over revenue.  Lower is better and "
           "1.0 is breakeven.")
    S.step("obj", "obj", "cost over revenue", "C_tot / E[Rev]",
           "%s / %s" % (P(K["total"]), P(P_["expected"])),
           P_["obj"], "x", ["C_tot", "E_Rev"],
           "what the campaign ranks on")
    S.step("profit", "profit", "profit", "E[Rev] - C_tot",
           "%s - %s" % (P(P_["expected"]), P(K["total"])),
           P_["expected"] - K["total"], "$", ["E_Rev", "C_tot"],
           "the catalog is SORTED by this and the project ranks on the "
           "ratio above, so the best case is not the file's first row")
    S.step("roi", "ROI", "return on cost", "profit / C_tot",
           "%s / %s" % (P(P_["expected"] - K["total"]), P(K["total"])),
           (P_["expected"] - K["total"]) / K["total"], "-",
           ["profit", "C_tot"])
    S.step("usd_kg", "$/kg", "cost per kilogram returned", "C_tot / m_pay",
           "%s / %s" % (P(K["total"]), P(M["m_pay"])),
           K["total"] / M["m_pay"], "$/kg", ["C_tot", "m_pay"],
           "against %s the load actually fetches"
           % ("$" + P(P_["rev"]["delivered"])))



# ------------------------------------------ the check that the page is right
# THE WHOLE CLAIM OF THIS DOCUMENT IS THAT A READER CAN RETYPE A LINE AND GET
# THE VALUE BESIDE IT.  Nothing else in this repo checks that.
# `worked_calculation.py`'s own comparison asks whether the DERIVATION agrees
# with the model, and it does; it cannot see a substitution string that omits
# a term, prints an operand at the wrong precision, or describes a different
# formula from the one that produced the number.  Those are defects of the
# PAGE rather than of the arithmetic, they look exactly like a correct page,
# and they are the only kind that matters to somebody with a calculator.
#
# So every substitution is parsed and evaluated, and the result is held to the
# value printed beside it.  A line that cannot be parsed is reported as
# UNCHECKED rather than passed over, because a checker that quietly covers
# half a page is this repo's most-catalogued failure.
_ALLOWED = {"exp": math.exp, "sqrt": math.sqrt, "log": math.log,
            "pi": math.pi, "cos": math.cos, "sin": math.sin,
            "radians": math.radians, "floor": math.floor,
            "min": min, "max": max, "abs": abs}

_WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_THOUSANDS = re.compile(r"(?<=\d),(?=\d\d\d)")
_BARS = re.compile(r"\|([^|]+)\|")
_DEG = re.compile(r"cos\(([^()]+) deg\)")


def evaluable(text):
    """`text` as a Python expression, or None if it is prose rather than sums.

    The substitutions are written for a person, so they carry three things
    Python will not take: thousands separators, `^` for exponentiation, and
    `|x|` for absolute value.  A degree argument is converted too, because
    the page states the plane change in degrees and the model takes radians.
    """
    expr = _THOUSANDS.sub("", text.strip())
    expr = _DEG.sub(r"cos(radians(\1))", expr)
    expr = _BARS.sub(r"abs(\1)", expr)
    expr = expr.replace("^", "**")
    if not expr or "=" in expr:
        return None
    for word in set(_WORD.findall(expr)):
        if word in _ALLOWED:
            continue
        # An `e` inside 1.4e-05 is part of the literal, not a name.
        if re.search(r"(?<![A-Za-z_0-9.])%s(?![A-Za-z_0-9])" % word, expr):
            return None
    return expr


def check_substitutions(sheet, tol=1e-9):
    """Evaluate every substitution on the sheet against the value beside it.

    Returns (checked, unchecked, bad).  `bad` is the list that matters: a row
    whose arithmetic does not produce its own printed result is a line a
    reader would fail to reproduce, which is the one defect this document
    cannot survive.
    """
    checked, unchecked, bad = 0, [], []
    rows = [(row[1], row[2], row[5], row[6])
            for part in sheet.parts for row in part["rows"]
            if row[0] == "step"]
    # A TABLE ROW IS A STEP LAID OUT IN COLUMNS and is checked as one.
    rows += [("table", what or "row", work, value)
             for work, value, what in sheet.claims]
    for tag, symbol, substitution, value in rows:
        how, got = reproduces(substitution, value, tol)
        if how == "prose":
            unchecked.append((tag, symbol, substitution))
            continue
        if how != "error":
            checked += 1
        if how != "ok":
            bad.append((tag, symbol, substitution, got, value))
    return checked, unchecked, bad


def origins(sheet):
    """(inputs with an origin, inputs without one).

    THE ONE PROMISE THE PAGE MAKES THAT NOTHING ELSE CHECKS.  Every input is
    supposed to say where it came from, and an input that arrives with an
    empty citation reads exactly like one that arrives with a good one:
    the cell is just blank, in a table of two hundred rows nobody scans.
    Condensing the sheet is precisely the edit that could drop one, so the
    promise is asserted rather than trusted.

    A bare file name is not an origin either.  A citation has to name the
    ROW or the FIELD the number sits in, or a reader cannot go and look, so
    an origin with no `row`, `column`, `field` or `<i>` in it is a finding.
    """
    good, bad = [], []
    for part in sheet.parts:
        for row in part["rows"]:
            if row[0] != "input":
                continue
            tag, symbol, source = row[1], row[2], row[6] or ""
            enough = ("<i>" in source
                      or "Derived on this page" in source)
            (good if source.strip() and enough else bad).append((tag, symbol))
    return good, bad


def report_origins(sheet, quiet=False):
    """Print the origin check, and return the number of inputs without one."""
    good, bad = origins(sheet)
    if not quiet:
        print("  origins    %d of %d inputs name a file and a row or field, "
              "%d do NOT" % (len(good), len(good) + len(bad), len(bad)))
        for tag, symbol in bad:
            print("     ! %-5s %s has no origin a reader could follow"
                  % (tag, symbol))
    return len(bad)


def report_substitutions(sheet, quiet=False):
    """Print the substitution check, and return the number of bad rows.

    PROVED BY BEING FED A WRONG ANSWER, which is this repo's standing rule for
    anything that prints a clean line: `--self-test` perturbs one printed
    value and the check goes red and names the tag.  A matcher nobody has
    seen fail is a matcher nobody has seen.
    """
    checked, unchecked, bad = check_substitutions(sheet)
    if not quiet:
        print("  arithmetic %d of %d substitutions evaluated and matched, "
              "%d not arithmetic, %d WRONG"
              % (checked - len(bad), checked, len(unchecked), len(bad)))
        for tag, symbol, sub, got, want in bad:
            print("     ! %-5s %-14s %s" % (tag, symbol, sub))
            print("            gives %r, page says %r" % (got, want))
        for tag, symbol, sub in unchecked:
            print("     - %-5s %-14s not arithmetic: %s"
                  % (tag, symbol, sub[:70]))
    return len(bad)


# ------------------------------------ every number, back to where it came from
# THE PROMISE THIS DOCUMENT MAKES IS THAT NOTHING ON IT IS UNSOURCED, and the
# two checks above each cover half of it: `origins` says every INPUT names a
# file and a row, `check_substitutions` says every STEP reproduces its own
# result.  Neither notices a number that is on the page without being either
# -- a table cell the renderer computed on the way past, a factor quoted in a
# note, a ratio in a caption.  Those are precisely the numbers a reader cannot
# follow, because there is nothing to follow them to.
#
# A number is TRACED when it is a correct rounding, at the precision it is
# printed to, of something the sheet registered: an input's value, a step's
# value, an operand inside a step's substitution, or a table claim and its
# operands.  Anything else is a finding.
_SCALES = (1.0, 1e6, 1e-6, 1e3, 1e-3, 1e2, 1e-2, 1e9, 1e-9)
# Citations are QUOTED source; the tag column and the cited-tag spans are
# the page's own cross-references.  "I10" and "S22" are labels that happen to
# contain digits, and reading them as numbers reported well over a hundred
# findings that were nothing but the sheet pointing at itself.  An `ord` span
# is the same kind of label: a table row's position, which counts rows rather
# than claiming anything about them.  The sale-tier table reached twelve tiers
# on the detailed phases, twelve is not a number any step makes, and the row
# label read as an untraced claim.
_CITE = re.compile(r'<(span|td)[^>]*class="[^"]*\b(?:cite|tag|uses|ord)\b[^"]*"'
                   r'[^>]*>.*?</\1>', re.S)
# A table whose rows are the whole cascade at another setting.  Excluded and
# COUNTED, never excluded quietly: the number it excused is printed beside
# the number it checked, so a register that quietly grew would be visible.
_RERUN = re.compile(r'<div class="rerun">.*?<!--rerun-end-->', re.S)


def sheet_numbers(sheet):
    """Every value and every operand the sheet registered, as floats."""
    out = []
    for part in sheet.parts:
        for row in part["rows"]:
            if row[0] == "input" and isinstance(row[4], (int, float)):
                out.append(float(row[4]))
            elif row[0] == "step":
                if isinstance(row[6], (int, float)):
                    out.append(float(row[6]))
                for field in (row[4], row[5]):
                    out.extend(v for v, _d in map(as_number,
                                                  NUMBER.findall(field))
                               if v is not None)
    for work, value, _what in sheet.claims:
        out.append(float(value))
        out.extend(v for v, _d in map(as_number, NUMBER.findall(work))
                   if v is not None)
    return out


NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")
VERSION = re.compile(r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])")


def as_number(token):
    """(value, decimals shown) for a rendered token, or (None, None)."""
    clean = token.replace(",", "")
    try:
        value = float(clean)
    except ValueError:
        return None, None
    if "e" in clean or "E" in clean:
        return value, None
    return value, len(clean.split(".")[1]) if "." in clean else 0


def is_traced(value, decimals, known):
    """Is `value` a correct rounding of something in `known`?

    The tolerance is the printing, not a fudge: a number shown to three
    decimals is traced by anything that rounds to it at three decimals, and
    a number shown whole has to match exactly.  The scale list is there
    because the page renders the same quantity in dollars and in millions.
    """
    for scale in _SCALES:
        target = value * scale
        for k in known:
            if decimals is None:
                # A token like 4.78e-12 is printed to three significant
                # figures, so it is traced by anything that ROUNDS to it at
                # three.  Holding it to 1e-6 relative asked a rendering to
                # be a measurement and reported the one number on the page
                # that is deliberately shown short.
                if k and abs(target - k) <= abs(k) * 5e-3:
                    return True
            elif abs(target - k) <= 0.5 * 10 ** (-decimals) * scale * 1.000001:
                return True
    return False


def untraced(sheet, html):
    """Numbers the page asserts with nothing behind them.

    Scoped to the numbered PARTS, and to what the page CLAIMS rather than
    what it quotes.  A number inside a citation is the source itself --
    "$1,400/oz" in the platinum note is what the exchange said -- so
    citations are stripped, and the header card and footer are document
    furniture rather than model output.
    """
    body = html
    head = body.find('<h2 id="p%d"' % part_no(PART_KEYS[0]))
    foot = body.find('<div class="foot">')
    if head > 0:
        body = body[head:foot if foot > head else len(body)]
    body = _CITE.sub(" ", body)
    reruns = len(_RERUN.findall(body))
    body = _RERUN.sub(" ", body)
    text = D.html.unescape(re.sub(r"<[^>]+>", " ", body))
    # ⚠️  A RELEASE STAMP IS A NAME, NOT A QUANTITY.  "calc 1.17.7" tokenised
    # as 1.17 and was traced only when some figure on the page happened to
    # round to it, so the same sentence passed on one 2026-08 row and failed
    # on the next.  Three dotted integers are a version and nothing else.
    text = VERSION.sub(" ", text)
    known = sheet_numbers(sheet)
    seen, bad = set(), []
    for token in NUMBER.findall(text):
        if token in seen:
            continue
        seen.add(token)
        value, decimals = as_number(token)
        if value is None or value == 0:
            continue
        if not is_traced(value, decimals, known):
            i = text.find(token)
            bad.append((token, " ".join(text[max(0, i - 60):i + 30].split())))
    return len(seen), bad, reruns


def ledger_on_page(html):
    """(tabulated {name: (value, how, definition)}, duplicates), READ OFF THE
    RENDERED PAGE rather than off the code that built it, so the check below
    cannot agree with the ledger by construction."""
    head = html.find('<h2 id="p%d"' % part_no("dials"))
    if head < 0:
        return {}, []
    tail = html.find("<h2 id=", head + 1)
    part = html[head:tail if tail > 0 else len(html)]
    tabulated, dupes = {}, []
    for row in re.findall(r"<tr>(.*?)</tr>", part, re.S):
        cells = re.findall(r"<td>(.*?)</td>", row, re.S)
        if len(cells) != 5 or not cells[0].startswith("<i>"):
            continue
        name = re.sub(r"<[^>]+>", "", cells[0]).strip()
        text = [D.html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                for c in cells]
        if name in tabulated:
            dupes.append(name)
        tabulated[name] = (text[1], text[2], text[4])
    return tabulated, dupes


def report_dials(html, quiet=False):
    """Every Stage 4 config field is on the page, with a value and a meaning.

    🚨  THE LEDGER WAS CHECKED ONLY BY LOOKING AT IT.  It is built by
    walking the dataclass, which is the right construction and not a proof:
    a `continue` added for some class of field, or a renderer that drops a
    row, would leave a page that reads complete and is not.  This reads the
    RENDERED ledger and holds it to `dataclasses.fields(CalcConfig)`: every
    field must be a row with a value, how the page knows it and its own
    comment's definition.  A row naming no field, or a field listed twice, is
    a finding too.  (File paths used to be named in a sentence rather than
    tabulated, and this read that sentence; they are rows now.)
    """
    import dataclasses
    import master
    fields = [f.name for f in dataclasses.fields(master.CALC_CONFIG)]
    tabulated, dupes = ledger_on_page(html)
    missing = [f for f in fields if f not in tabulated]
    blank = [f for f, (value, how, meaning) in tabulated.items()
             if not value or not how or not meaning]
    stray = [f for f in tabulated if f not in fields]
    bad = missing + blank + stray + dupes
    if not quiet:
        print("  dials      %d of %d Stage 4 config fields tabulated on the "
              "page, each with a value, how it is known and what it is; %d "
              "missing, %d blank, %d not a field, %d twice"
              % (len(fields) - len(missing), len(fields), len(missing),
                 len(blank), len(stray), len(dupes)))
        for name in bad:
            print("     ! %s" % name)
    return len(bad)


def dial_self_test(html):
    """Delete one ledger row from the page and confirm the check notices."""
    tabulated, _dupes = ledger_on_page(html)
    if not tabulated:
        print("  self-test  *** NO DIAL LEDGER TO PERTURB ***")
        return 1
    name = sorted(tabulated)[0]
    row = re.search(r"<tr><td><i>%s</i></td>.*?</tr>" % re.escape(name),
                    html, re.S)
    planted = html[:row.start()] + html[row.end():]
    if report_dials(planted, quiet=True):
        print("  self-test  deleting the %s row is caught: the dial check "
              "can fail" % name)
        return 0
    print("  self-test  *** DELETING THE %s ROW WENT UNNOTICED ***" % name)
    return 1


def page_tables(html):
    """Every <table> on the page as (headers, rows of cell text), NESTED
    TABLES KEPT APART: a worksheet block is a table inside the register's
    table, and a regex over the markup merges their columns."""
    from html.parser import HTMLParser

    class Parser(HTMLParser):
        """Collect each table's own header and data cells."""

        def __init__(self):
            """An empty stack of open tables, and none finished yet."""
            HTMLParser.__init__(self, convert_charrefs=True)
            self.stack, self.done = [], []

        def handle_starttag(self, tag, _attrs):
            """Open a table, a row or a cell on the innermost open table."""
            if tag == "table":
                self.stack.append({"heads": [], "rows": [], "cell": None,
                                   "row": None})
            elif self.stack and tag == "tr":
                self.stack[-1]["row"] = []
            elif self.stack and tag in ("td", "th"):
                self.stack[-1]["cell"] = [tag, ""]

        def handle_endtag(self, tag):
            """Close a cell, a row or a table, filing it where it belongs."""
            if not self.stack:
                return
            top = self.stack[-1]
            if tag in ("td", "th") and top["cell"]:
                kind, text = top["cell"]
                text = " ".join(text.split())
                (top["heads"] if kind == "th" else
                 top["row"] if top["row"] is not None else []).append(text)
                top["cell"] = None
            elif tag == "tr" and top["row"] is not None:
                if top["row"]:
                    top["rows"].append(top["row"])
                top["row"] = None
            elif tag == "table":
                self.done.append(self.stack.pop())

        def handle_data(self, data):
            """Text belongs to the innermost table's open cell, if any."""
            if self.stack and self.stack[-1]["cell"]:
                self.stack[-1]["cell"][1] += data

    parser = Parser()
    parser.feed(html)
    return [(t["heads"], t["rows"]) for t in parser.done]


PLACEHOLDER_TEXT = re.compile(
    r"\b(?:TODO|TBD|FIXME|XXX|lorem ipsum|nan|NaN|inf)\b"
    r"|no row named|chosen here rather than measured|\(empty: none")
BARE = re.compile(r"\$?-?[\d,]+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def placeholders(sheet, html):
    """Every line of the page that answers without showing how.

    Four kinds, each read off what the page actually carries:

      text     a stand-in phrase, or a value printed as nan or inf;
      empty    a step with no formula or no substitution;
      static   a step whose working is a bare number that is neither the
               value of a key it cites, nor a figure worked out in a table
               on this page, nor stated with its reason (a formula that
               opens "1: revenue is not discounted on this run");
      cell     a cell in a "worked out" column that is empty or a bare
               number, so the table states a figure and calls it working.
    """
    bad, counted = [], {"steps": 0, "cells": 0}
    text = D.html.unescape(re.sub(r"<[^>]+>", " ", html))
    seen = set()
    for m in PLACEHOLDER_TEXT.finditer(text):
        if m.group(0) in seen:
            continue
        seen.add(m.group(0))
        bad.append(("text", m.group(0), " ".join(
            text[max(0, m.start() - 50):m.end() + 30].split())))
    key_of = {tag: key for key, tag in sheet.tag.items()}
    for part in sheet.parts:
        for row in part["rows"]:
            if row[0] != "step":
                continue
            counted["steps"] += 1
            _k, tag, symbol, _q, formula, sub, value, _u, tags, _n = row
            if not str(formula).strip() or not str(sub).strip():
                bad.append(("empty", tag, symbol))
                continue
            if not BARE.fullmatch(str(sub).strip()):
                continue
            copies = any(
                isinstance(sheet.value.get(key_of.get(t)), (int, float))
                and float(sheet.value[key_of[t]]) == float(value)
                for t in tags)
            worked = any(isinstance(v, (int, float)) and float(v) == float(value)
                         for _w, v, _what in sheet.claims)
            lead = str(formula).split(":", 1)[0].strip()
            reasoned = (":" in str(formula) and BARE.fullmatch(lead)
                        and float(lead.replace(",", "").lstrip("$"))
                        == float(value))
            if not (copies or worked or reasoned):
                bad.append(("static", tag, "%s = %s" % (symbol, sub)))
    for heads, rows in page_tables(html):
        cols = [i for i, h in enumerate(heads) if "worked out" in h]
        for r in rows:
            for i in cols:
                if i >= len(r):
                    continue
                counted["cells"] += 1
                cell = r[i].strip()
                if not cell or BARE.fullmatch(cell):
                    bad.append(("cell", heads[i], " | ".join(r[:3])[:80]))
    return bad, counted


def report_placeholders(sheet, html, quiet=False):
    """Print the placeholder check, and return the number of findings."""
    bad, counted = placeholders(sheet, html)
    if not quiet:
        print("  static     %d step(s) and %d 'worked out' cell(s) read, and "
              "the page text: %d answer(s) stated without showing how "
              "(stand-in text, empty steps, uncited bare numbers, empty or "
              "bare cells)" % (counted["steps"], counted["cells"], len(bad)))
        for kind, what, where in bad:
            print("     ! %-6s %s  ... %s" % (kind, what, where))
    return len(bad)


def placeholder_self_test(sheet, html):
    """Plant one of each kind of placeholder and confirm each is caught."""
    import copy
    caught = []
    text = html.replace("</h2>", "</h2><p>TBD</p>", 1)
    caught.append(("stand-in text", report_placeholders(sheet, text, True)))
    planted = copy.deepcopy(sheet)
    for part in planted.parts:
        for n, row in enumerate(part["rows"]):
            if row[0] == "step" and not BARE.fullmatch(str(row[5]).strip()):
                value = float(row[6]) * 1.317 + 1.0
                part["rows"][n] = row[:5] + (P(value), value) + row[7:]
                break
        else:
            continue
        break
    caught.append(("an uncited bare number",
                   report_placeholders(planted, html, True)))
    blanked = html.replace(
        "</h2>", "</h2>" + D.table(["quantity", "how it is worked out",
                                    "value"], [["planted", "", "42"]]), 1)
    caught.append(("an empty worked-out cell",
                   report_placeholders(sheet, blanked, True)))
    missed = [what for what, found in caught if not found]
    if missed:
        print("  self-test  *** PLANTED %s WENT UNNOTICED ***"
              % ", ".join(missed).upper())
        return 1
    print("  self-test  planted stand-in text, an uncited bare number and an "
          "empty worked-out cell are each caught: the placeholder check can "
          "fail")
    return 0


def report_untraced(sheet, html, quiet=False):
    """Print the traceability check, and return the number of findings."""
    seen, bad, reruns = untraced(sheet, html)
    if not quiet:
        print("  traced     %d of %d numbers the page ASSERTS come from a "
              "tagged input, a step or a table claim, %d do NOT; %d table(s)"
              " are this document re-run at another setting and say so"
              % (seen - len(bad), seen, len(bad), reruns))
        for token, where in bad:
            print("     ! %-18s ... %s" % (token, where))
    return len(bad)

# ------------------------------------------------------- 16. the cross-checks
def part_checks(S, out):
    """Identities that must hold, for a reader to catch their own slips.

    None of these is a new measurement.  They are the places where two
    independently computed quantities have to agree, which is what lets
    somebody working down the page on paper find the line they fumbled
    rather than discovering at the end that the answer is out by 3%.
    """
    C, M, P_, B = out["C"], out["M"], out["P"], out["B"]
    K, R = P_["cost"], M["R"]
    S.part("checks", "Cross-checks",
           "Two routes to one number, which must agree.  If one disagrees "
           "on your paper the error is upstream, and the tags say where.")
    rows = []

    def ident(what, left_label, left, right_label, right, keys):
        """One identity: two routes to one number, and their difference.

        The tags are LOOKED UP from keys.  They were typed as symbol names
        ("S: m_hw, m_plant, m_EP"), which named no tag a reader could find
        and named the refinery on missions that flew none.
        """
        gap = S.claim("abs(%s - %s)" % (exact(left), exact(right)),
                      abs(left - right), "%s residual" % what)
        # A non-zero residual under the last bit of the largest number a
        # route subtracts is rounding, and says so: the launch margin is
        # two differences of masses near the vehicle's capacity, and its
        # bare 5.95e-13 read as a failure on a table titled "must agree".
        big = keys[0]
        rounding = (left != right and big in S.value
                    and abs(left - right) < math.ulp(abs(S.value[big])))
        rows.append([what, left_label, P(left, 12), right_label,
                     P(right, 12), gap, P(abs(left - right), 3)
                     + (", under one bit of %s" % D.esc(big)
                        if rounding else ""),
                     '<span class="uses">%s</span>'
                     % ", ".join(S.cited([k for k in keys if k in S.tag]))])

    ref_on = M.get("refinery", 0.0) > 0
    ident("the hardware ledger",
          "m_hw", M["hw"],
          "m_rig + m_plant + m_EP" + (" + m_ref" if ref_on else ""),
          (C["cfg"].mining_hardware_kg + M["plant"] + M["ep"]["mass"]
           + M.get("refinery", 0.0)),
          ["m_hw", "m_rig", "m_plant", "m_EP"] + (["m_ref"] if ref_on
                                                  else []))
    ident("the launch margin",
          "M_LEO - m_launch", C["leo_cap"] - M["m_launch"],
          "(budget - m_at) k_out R_out",
          (R["budget"] - M["m_at"]) * R["k_out"] * R["R_out"],
          ["M_LEO", "m_launch", "budget", "m_at", "k_out", "R_out"])
    ident("the hold is full",
          "sum of what the %s" % ("knapsack took" if C["beneficiated"]
                                  else "raw hold carries"),
          sum(M["load"]["mix"].values()),
          "m_pay", M["m_pay"], ["m_pay", "hold_value"])
    ident("the sale never exceeds the hold",
          "Rev", P_["rev"]["capped"]["value"],
          "clearing * V_hold",
          S.value["clearing"] * P_["rev"]["gross_base"],
          ["Rev", "clearing", "hold_value"])
    ident("the cost buckets add up",
          "C_tot", K["total"],
          "upfront* + ongoing* + end*"
          + (" + delta" if K["delta"] else ""),
          K["upfront"] * K["mult_up"] + K["ongoing"] * K["mult_on"]
          + K["end"] + K["delta"], ["C_tot", "upfront", "ongoing", "end"])
    ident("the contingency reserve",
          "reserve", K["contingency"],
          "zeta (upfront + ongoing + end)",
          C["cfg"].contingency_fraction
          * (K["upfront_lines"] + K["ops"]
             + (K["lines"]["rprop"] if C["isru"] else 0.0) + K["handover"]),
          ["contingency", "zeta"])
    ident("the programme is a rectangle",
          "N", float(P_["n"]), "F * W", float(P_["f"] * P_["w"]),
          ["N", "F", "Wc"])
    ident("the objective",
          "obj", P_["obj"], "C_tot / E[Rev]", K["total"] / P_["expected"],
          ["obj", "C_tot", "E_Rev"])
    S.block(D.table(["identity", "one route", "value", "the other route",
                     "value", "difference worked out", "difference", "tags"],
                    rows, "wide"))
    S.prose("Two structural bounds that are inequalities rather than "
            "identities: <b>W = %s must not exceed trips = %s</b>, because a "
            "rig cannot fly more campaigns than it survives; and "
            "<b>clearing = %s must not exceed 1</b>, because a ceiling can "
            "only ever cost a delivery revenue."
            % (P(P_["w"]), P(M["trips"]), P(P_["rev"]["clearing"])))


# ------------------------------------------------------- 17. the backing
# WHAT A ROW RESTS ON, ASKED OF EVERY ROW.  The origin check above holds every
# input to naming a file and a row, which says where a number was READ; it
# does not say whether anything outside this repository stands behind it.  A
# config dial, a constant typed into the derivation and a utility factor all
# pass the origin check, and none of them is a measurement.  This part asks
# the second question of every tag, and prints "(needs backing)" where the
# honest answer is nothing.
#
# A PUBLISHED SOURCE IS RECOGNISED, NOT ASSERTED.  A sentence of a row's notes
# counts as naming one when it carries a label ("Anchor:", "Source:"), an
# author ("et al", two names and a year), a link or DOI, or one of the
# agencies, publishers and price feeds below.  The sentences that matched are
# QUOTED on the page, so a false match is visible to the reader rather than
# hidden behind a tick.  A miss errs the safe way: the row is flagged.  A
# vehicle or station named as an ANALOGY is not on the list ("ISS-class
# hardware is rated 15-30 years" names no document), and a row's notes are
# quoted as the ROW's: a launch-vehicle row's price source is not a source
# for its payload, and the page says "the row's notes cite" for that reason.
#
# AUDITED AGAINST EVERY NOTES FIELD IT CAN READ (2026-10-19): the frozen
# Stage 2 and Stage 3 tables and every config comment.  That pass found
# sentences naming an agency in order to DENY a source ("NASA / SpaceX have
# not published a per-kg PICA-X cost"), which `_NO_SOURCE` now refuses, and
# real ones the first list missed: a guide or manual by title, "(SpaceNews
# 2024)", "per Reuters analyst consensus".
SOURCE_NAMES = (
    "NASA", "JPL", "ESA", "JAXA", "USGS", "LME", "LBMA", "World Bank",
    "Johnson Matthey", "CODATA", "IAU", "IERS", "NIST", "FAA", "CFR", "NICM",
    "SSCM", "SMCM", "Aerospace Corp", "Wikipedia", "Planetary Society",
    "Minor Planet Center", "MPC", "McDowell", "yfinance", "Yahoo Finance",
    "metals.dev", "Fastmarkets", "Argus", "Platts", "COMEX", "NYMEX", "CME",
    "SpaceX", "Blue Origin", "ULA", "Rocket Lab", "Arianespace",
    "Northrop Grumman", "DARPA", "GAO", "AIAA", "DLA", "Reuters",
    "SpaceNews", "Astronautix", "RocketCEA", "Gallagher", "Damodaran")
_MONTHS = ("Jan|Feb|Mar|Apr|May|Jun|June|Jul|July|Aug|Sep|Sept|Oct|Nov|Dec|"
           "Q[1-4]|NET|FY|early|late|mid")
_LABEL = re.compile(r"\b(?:Anchors?|Sources?|References?|Cited|Citation)\s*:")
_SOURCE_MARK = re.compile(
    _LABEL.pattern +
    r"|\bet al\b"
    r"|\b[A-Z][A-Za-z'-]+ (?:and|&) [A-Z][A-Za-z'-]+,? \(?(?:19|20)\d\d\b"
    # An attribution in parentheses, "(SpaceNews 2024)", and not a date.
    r"|\((?!(?:%s)\b)[A-Z][\w.&'/-]*(?: [A-Z][\w.&'/-]*)* (?:19|20)\d\d\)"
    # A document by its kind: a vendor's guide or manual, a datasheet.
    r"|\bUsers?'?s?'? (?:Guide|Manual)\b|\bPlanner'?s Guide\b"
    r"|\bdata ?sheets?\b|\bstatus reports?\b|\bStandard Prices\b"
    r"|\bdoi\s*:|https?://"
    r"|\b(?:%s)\b" % (_MONTHS, "|".join(re.escape(n) for n in SOURCE_NAMES)))
# A sentence that names a source only to say there is none, or that records
# what a row USED to cite.  Neither stands behind today's value.
_NO_SOURCE = re.compile(
    r"\b(?:no|not|never|none)\b[^.;:]{0,60}?\b(?:publish\w*|sources?|"
    r"cite\w*|mention\w*|commodity)\b"
    r"|\blists [^.;]{0,40}, not\b|\b(?:engineering|order-of-magnitude) "
    r"estimate\b|^\(?Until v?\d", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")
# What a period after which a sentence does NOT end looks like: an initial,
# a short abbreviation ("J. Eng.", "Fig.", "Rev.", "No."), "e.g." or "vs.".
# An initial stands alone: "NEXT-C." ends a sentence, and reading its C as
# an initial merged it into the next one (the self-test's planted row).
_ABBREV = re.compile(r"(?:(?<![\w-])[A-Z][a-z]{0,2}|\be\.g|\bi\.e|\bvs|\bcf|"
                     r"\bal|\bpp?)\.$")
_SRC_SPAN = re.compile(r"<span class='src'>(.*?)</span>", re.S)
_FIELD = re.compile(r"<b>(\w+)</b> config, field <i>([a-z0-9_]+)</i>")
_COLUMN = re.compile(r"column <i>([a-z0-9_]+)</i>")

# The surveys behind every Stage 1 column, as CITATIONS.md section 1 lists
# them.  A pointer to that file, not a second bibliography: the catalog does
# not say which survey supplied which column, so the page says what it can.
SURVEYS = ("the AsteroidCatalog release this run read, compiled from JPL "
           "SBDB, IMCCE SsODNet/ssoBFT (Berthier et al. 2023), NEOWISE "
           "Diameters and Albedos V2.0 (Mainzer et al. 2019) and MP3C; "
           "<b>CITATIONS.md</b> section 1")
COMPOSITION = ("the meteorite analogue AsteroidCatalog's mineralogy cites for "
               "this taxonomy class; <b>CITATIONS.md</b> section 1, "
               "<i>Mineral composition</i>")

# THE RELATIONS A STEP USES THAT A TEXTBOOK STATES.  Matched on the step's
# formula, so a return leg written with the same relation is cited the same
# way.  The references are CITATIONS.md section 4's; a step this does not
# match is the model's own arithmetic on its cited inputs, which the
# substitution and the run's row verify and no source could.
RELATIONS = (
    (re.compile(r"^exp\(dv"), "the rocket equation (Tsiolkovsky)",
     "Sutton and Biblarz, <i>Rocket Propulsion Elements</i>"),
    (re.compile(r"^I_sp \* g_0$"), "exhaust velocity from specific impulse",
     "Sutton and Biblarz, <i>Rocket Propulsion Elements</i>"),
    (re.compile(r"v_e\^2 / \(2 eta t\)"), "jet power of an electric thruster",
     "Sutton and Biblarz, <i>Rocket Propulsion Elements</i>"),
    (re.compile(r"^m_prop v_e / t$"), "thrust as mass flow times exhaust "
     "velocity", "Sutton and Biblarz, <i>Rocket Propulsion Elements</i>"),
    # `mu_\w+` and the `[^ ^]*` suffixes because a Mars leg writes the same
    # relation as `mu_M` and `v_inf,M`; an audit over one cell per
    # destination found those spellings matching nothing.
    (re.compile(r"sqrt\((?:mu_\w+ )?\(?2 (?:/|-) "), "the vis-viva equation",
     "Vallado, <i>Fundamentals of Astrodynamics and Applications</i>"),
    (re.compile(r"^sqrt\(mu_\w+ / [rR]"), "circular orbital speed",
     "Vallado, <i>Fundamentals of Astrodynamics and Applications</i>"),
    (re.compile(r"^sqrt\(2\) \* v_|^sqrt\(2 mu_\w+ / "), "escape speed",
     "Vallado, <i>Fundamentals of Astrodynamics and Applications</i>"),
    (re.compile(r"^sqrt\(v_esc[^ ^]*\^2 \+ v_inf[^ ^]*\^2\)"),
     "hyperbolic excess "
     "energy at perigee (vis-viva)",
     "Vallado, <i>Fundamentals of Astrodynamics and Applications</i>"),
    (re.compile(r"\+ 1 - 2 v_t cos i$|- 2 v_\w+ v_\w+ cos \w+\)$"
                r"|- 2 sqrt\(v_\w+\^2 v_\w+\^2\) cos \w+\)"),
     "a combined plane change by the "
     "law of cosines",
     "Vallado, <i>Fundamentals of Astrodynamics and Applications</i>"),
    (re.compile(r"^a(?:_dest)? \^ 1\.5$"), "Kepler's third law",
     "Vallado, <i>Fundamentals of Astrodynamics and Applications</i>"),
    (re.compile(r"1 / \|1 / T_ast - 1 / T_dest\|"), "the synodic period",
     "Vallado, <i>Fundamentals of Astrodynamics and Applications</i>"),
    (re.compile(r"^k_D / sqrt\(p_V\)"), "diameter from absolute magnitude "
     "and albedo", "Fowler and Chillemi 1992"),
)


# The table a citation names, and the path dial `C["files"]` records the
# file it was actually read from under.
TABLE_FILES = (("operational_costs.csv", "operational_costs_file"),
               ("propellants.csv", "propellants_file"),
               ("launch_vehicles.csv", "launch_vehicles_file"),
               ("mineral_value_catalog.csv", "mineral_catalog_file"),
               ("asteroid_catalog.csv", "asteroid_catalog_file"))


def plain(text):
    """HTML as the reader sees it: tags dropped, entities decoded."""
    return " ".join(D.html.unescape(re.sub(r"<[^>]+>", "", str(text)))
                    .split())


def sentences(text):
    """`text` split into sentences, not at an abbreviation's period."""
    out = []
    for piece in _SENTENCE.split(plain(text)):
        if out and _ABBREV.search(out[-1]):
            out[-1] += " " + piece
        else:
            out.append(piece)
    return out


# A SOURCE A LATER TABLE WITHDREW.  An archived run read a frozen spacecost
# table, and the page quotes that table faithfully -- including a citation
# the installed release has since retracted ("Until 1.17.1 this cited
# 'NASA Money-Mass-ematics 2023', a grades 7-8 classroom worksheet ... that
# never mentions beneficiation").  Quoting it as backing would be the page
# vouching for a source the project itself withdrew, so the installed
# tables' retractions are read, and a sentence naming one is refused.
_RETRACTED = []


def retracted():
    """Titles the installed spacecost tables say a row once cited wrongly."""
    if not _RETRACTED:
        import spacecost
        titles = set()
        for loader in ("load_operational_costs", "load_propellants",
                       "load_launch_vehicles", "load_storage"):
            for note in getattr(spacecost, loader)()["notes"].dropna():
                titles.update(re.findall(r"this (?:row )?cited '([^']+)'",
                                         str(note)))
        # A sentinel, so an install with no retractions is read once.
        _RETRACTED.append(tuple(sorted(titles)))
    return _RETRACTED[0]


def withdrawn(found):
    """(sentences still standing, the retracted titles that struck any)."""
    hit = [t for t in retracted() if any(t in s for s in found)]
    return [s for s in found if not any(t in s for t in hit)], hit


def named_sources(text):
    """The sentences of `text` that name a published source, verbatim."""
    # An explicit label outranks a denial in the same sentence: "Source:
    # Wikipedia, used as the LEO figure because no LEO figure is published"
    # names its source and denies a different one.
    return [s for s in sentences(text)
            if _LABEL.search(s)
            or (_SOURCE_MARK.search(s) and not _NO_SOURCE.search(s))]


def quoted(sentences):
    """Sentences as the page quotes them: escaped, each in its own quotes."""
    return " ".join("&ldquo;%s&rdquo;" % D.esc(s) for s in sentences)


def row_cites(sentences):
    """Sources quoted off a reference row's notes, labelled as the row's."""
    return "the row's notes cite %s" % quoted(sentences)


def input_backing(row):
    """(status, html) for one INPUT: 'source', 'derived' or 'needs'.

    Dispatched on the citation's own opening clause, which the `cite_*`
    helpers above write in a fixed form; a citation in a form this does
    not recognise falls through to the sentence test, and to the flag.
    """
    _k, _tag, _sym, quantity, _v, _u, source = row
    source = source or ""
    head = plain(source.split(".  ")[0])
    notes = " ".join(_SRC_SPAN.findall(source))
    if head.startswith("Derived on this page"):
        return "derived", "worked out on this page, as its citation says"
    # `cite_body` writes both forms with " &middot; row "; the run's own
    # `tank_mass_frac` also opens on profitability_catalog and is not a body
    # column, so the separator is what tells them apart.
    if (head.startswith(("asteroid_catalog.csv", "profitability_catalog"))
            and "&middot; row <i>" in source):
        column = (_COLUMN.findall(source) or [""])[0]
        if "NOT measured" in source:
            return "needs", ("not measured for this body: %s" % quoted(
                [s for s in sentences(source) if "NOT measured" in s]))
        return "source", COMPOSITION if column.startswith("comp_") else SURVEYS
    if head.startswith("mineral_value_catalog.csv"):
        if "<i>in_space_utility</i>" in source:
            return "needs", ("an engineering judgement: <b>CITATIONS.md</b> "
                             "section 7 records that there is nothing to "
                             "cite for a utility factor")
        if "terrestrial quote" in quantity:
            if "No quote" in source:
                return "needs", ("the row carries no price quote, and "
                                 "Stage 2 prices a missing terrestrial "
                                 "price as zero")
            # To the end of the clause, through a dot inside a name
            # ("metals.dev") but not the one that ends it.
            quotes = re.findall(r"(?:reference|live) quote from "
                                r"(?:[^.]|\.(?=\S))*", plain(source))
            if quotes:
                return "source", quoted(quotes)
        found = named_sources(notes)
        if found:
            return "source", row_cites(found)
        return "needs", ("the row's notes name no published source for "
                         "this column")
    match = _FIELD.search(source)
    if match and head.endswith(("where its whole comment is)",)):
        module, field = match.groups()
        doc = field_docs(module).get(field) or {}
        found = named_sources(doc.get("help") or "")
        if found:
            return "source", ("the field's comment: %s" % quoted(found))
        return "needs", ("a setting: its comment (<b>%s</b>) names no "
                         "published source" % D.esc(field_line(field,
                                                               module)))
    # A REFERENCE ROW IS DECIDED ON ITS NOTES ALONE.  Its citation also
    # carries the row's other fields, and one of them is `operator Blue
    # Origin`: scanning the whole citation credited a vehicle's maker as
    # the source of a figure its notes never sourced.
    if ".csv" in head:
        found, struck = withdrawn(named_sources(notes))
        gone = ", ".join("&ldquo;%s&rdquo;" % D.esc(t) for t in struck)
        if found:
            return "source", row_cites(found) + (
                ".  It also cites %s, which the installed spacecost release "
                "withdrew" % gone if struck else "")
        if struck:
            return "needs", ("the only source the row's notes give, %s, was "
                             "withdrawn by the installed spacecost release"
                             % gone)
        return "needs", "the row's notes name no published source"
    if notes and named_sources(notes):
        return "source", "its citation names %s" % quoted(
            named_sources(notes))
    found = named_sources(source)
    if found:
        return "source", "its citation names %s" % quoted(found)
    if "campaign/worked_calculation.py" in head:
        return "needs", "a constant fixed in the derivation's own source, "\
                        "with no reference given"
    if head.startswith(("modules/", "spacecost/", "asteroid_catalog/")):
        return "needs", "the model's own constant, with no reference given"
    return "needs", "the row's notes name no published source"


def relation(formula):
    """(name, reference) of the textbook relation a step uses, or None."""
    for pattern, name, where in RELATIONS:
        if pattern.search(str(formula)):
            return name, where
    return None


def reproduces(substitution, value, tol=1e-9):
    """('ok' | 'wrong' | 'error' | 'prose', what it evaluated to)."""
    expr = evaluable(substitution)
    if expr is None:
        return "prose", None
    try:
        got = eval(expr, {"__builtins__": {}}, dict(_ALLOWED))
    except Exception as exc:
        return "error", "%s" % exc
    scale = max(abs(float(value)), abs(float(got)), 1e-30)
    if abs(float(got) - float(value)) / scale > tol:
        return "wrong", got
    return "ok", got


def run_columns(out):
    """{value: [(column, how it compared)]} for the run's compared columns.

    Matched on the float, because a step does not know its column's name,
    and ONLY ON A DISTINCTIVE FLOAT.  The first version matched every value
    but 0 and 1, and an audit across one cell per destination found the
    small round numbers colliding: the fleet of 2 "equalled" ep_thrust_yr,
    a utility factor "equalled" containment_frac.  True as arithmetic and
    false as verification, so a value must carry four significant digits
    before the page says a column agrees with it; the integer rows that do
    have a column name it in their own citation.
    """
    c = out["check"]
    derived = W.comparable(out["C"], out["B"], out["DV"], out["M"],
                           out["P"], out["ladder"])
    bad = set(name for name, _o, _t, _r in c["bad"])
    found = {}
    for name in c["names"]:
        value = derived[name]
        if isinstance(value, bool) or not distinctive(value):
            continue
        theirs = float(out["archived"][name])
        how = ("DIFFERS" if name in bad else
               "bit-exact" if value == theirs else "within %g" % c["tol"])
        found.setdefault(float(value), []).append((name, how))
    return found


def distinctive(value):
    """Whether `value` carries at least four significant digits."""
    try:
        mantissa = repr(float(value)).lower().split("e")[0]
    except (TypeError, ValueError):
        return False
    return len(re.sub(r"\D", "", mantissa).strip("0")) >= 4


def tag_link(tag, where="b"):
    """A tag as a link to its row (`r`) or to its backing entry (`b`)."""
    return '<a href="#%s-%s">%s</a>' % (where, tag, tag)


def part_backing(S, out):
    """One entry per tagged row: where it came from, what stands behind it,
    and how this page verifies it.

    BUILT LAST, like the dial ledger, because it reads every row the other
    parts registered.  Every cell is quoted text or a label, so the
    traceability check skips this part: it states no number the page has
    not already stated and checked above.
    """
    C = out["C"]
    settled = W.dials_in_force(C)
    columns = run_columns(out)
    read = C.get("files", {})
    files = {table: repo_path(read[dial]) for table, dial in TABLE_FILES
             if read.get(dial)}
    rows = [r for part in S.parts for r in part["rows"]
            if r[0] in ("input", "step")]
    spent_by, uses = {}, {}
    for r in rows:
        if r[0] == "step":
            uses[r[1]] = list(r[8])
            for t in r[8]:
                spent_by.setdefault(t, []).append(r[1])
    key_of = dict((tag, key) for key, tag in S.tag.items())
    status = {}
    for r in rows:
        if r[0] == "input":
            status[r[1]] = input_backing(r)
    # A step needs backing where it SPENDS an input that does: naming the
    # inputs it spends directly keeps each entry to what that line consumes,
    # and the count upstream says how far the gap reaches without repeating
    # sixty tags under every cost line.
    flagged = set(t for t, (s, _h) in status.items() if s == "needs")

    def upstream(tag, seen):
        """Every input tag reachable from `tag` through the steps it spends."""
        for t in uses.get(tag, []):
            if t in seen:
                continue
            seen.add(t)
            upstream(t, seen)
        return seen

    S.part("backing", "Backing, row by row",
           "Every tagged row above, with the published source it rests on, "
           "quoted exactly where its citation names one, and how this page "
           "verifies it.  <b>(needs backing)</b> marks an input nothing "
           "outside this repository stands behind (a setting, a "
           "judgement, a constant given with no reference, a value not "
           "measured for this body) and a step that spends one, naming "
           "those it spends and then how many inputs upstream of it need "
           "backing in all.  A step whose relation is a textbook one names the "
           "book; the rest say <i>arithmetic</i>, the model's own on the "
           "rows the step spends.  <i>Re-evaluates</i> means the "
           "substitution, evaluated, gives the value printed, and "
           "<i>equals the run's</i> names the column of the run's own row "
           "that the value matches.  The same flag is printed beside the "
           "row itself, and each tag links between the two.")
    body = []
    for r in rows:
        tag = r[1]
        bits = []
        if r[0] == "input":
            state, why = status[tag]
            # The citation's opening clause, as text: cut at the joiner the
            # `cite_*` helpers use, it can end inside a span it opened.
            origin = D.esc(plain((r[6] or "").split(".  ")[0]))
            backed = ("<b class=\"nb\">(needs backing)</b> " + why
                      if state == "needs" else why)
            by = spent_by.get(tag)
            if by:
                bits.append("spent by %s"
                            % ", ".join(tag_link(t, "r") for t in by))
            else:
                bits.append("spent in a table on this page"
                            if key_of[tag] in S.used else "spent by no step")
            match = _FIELD.search(r[6] or "")
            if match and match.group(1) == "calc":
                field = match.group(2)
                bits.append("the run's own row settles it: %s"
                            % settled[field][1] if field in settled else
                            "read from this process's config")
            else:
                name = plain(origin).split(",")[0].split(" ")[0]
                if name in files:
                    bits.append("read from <b>%s</b>" % D.esc(files[name]))
        else:
            state = ("needs" if any(t in flagged for t in r[8])
                     else "steps")
            # Said in a word or two, because it is said 206 times: the
            # stock phrases were half of part 18's fifteen pages, and the
            # heading defines each of them once.
            origin = ("this page, from %s"
                      % ", ".join(tag_link(t, "r") for t in r[8])
                      if r[8] else "this page, from figures its note places")
            gaps = [t for t in r[8] if t in flagged]
            reach = len(upstream(tag, set()) & flagged)
            found = relation(r[4])
            backed = ("%s: %s" % found) if found else "arithmetic"
            if gaps:
                backed = ("<b class=\"nb\">(needs backing)</b> spends %s; %s"
                          % (", ".join(tag_link(t) for t in gaps), backed))
            if reach:
                backed += ("; %s upstream %s backing"
                           % (reach, "needs" if reach == 1 else "need"))
            how, got = reproduces(r[5], r[6]) if isinstance(
                r[6], (int, float)) else ("prose", None)
            bits.append({"ok": "re-evaluates",
                         "prose": "stated in words, not re-evaluated",
                         "wrong": "the substitution DOES NOT reproduce its "
                                  "value",
                         "error": "the substitution DOES NOT evaluate"}[how])
        value = r[4] if r[0] == "input" else r[6]
        if (isinstance(value, (int, float)) and not isinstance(value, bool)
                and distinctive(value)):
            for name, how in columns.get(float(value), []):
                bits.append("equals the run's <i>%s</i>, %s"
                            % (D.esc(name), how))
        status[tag] = (state, backed)
        body.append('<tr><td class="tag" id="b-%s">%s</td>'
                    '<td class="cite"><b>%s</b> %s</td>'
                    '<td class="cite">%s</td><td class="cite">%s</td>'
                    '<td class="cite">%s</td></tr>'
                    % (tag, tag_link(tag, "r"), D.esc(r[2]), D.esc(r[3]),
                       origin, backed, "; ".join(bits)))
    S.backing = dict((t, s) for t, (s, _h) in status.items())
    S.block('<div class="tw"><table class="wide backing"><thead><tr>'
            '<th>tag</th><th>quantity</th><th>read from</th>'
            '<th>the source it rests on</th><th>how this page verifies it'
            '</th></tr></thead><tbody>%s</tbody></table></div>'
            % "".join(body))


def report_backing(sheet, html, quiet=False):
    """Every tag has exactly one backing entry, and every flag is on its row.

    Read off the RENDERED page, both ways round: a tag with no entry is a
    row whose backing nobody stated, an entry for no tag is a ledger that
    drifted from the sheet, and a flagged entry whose row carries no flag is
    the page saying two different things about one number.
    """
    tags = set(sheet.tag.values())
    entries = re.findall(r'<td class="tag" id="b-([IS]\d+)">', html)
    inline = set(re.findall(r'<td class="tag" id="r-([IS]\d+)">'
                            r'(?:(?!</tr>).)*?class="nb"', html, re.S))
    flagged = set(t for t, s in getattr(sheet, "backing", {}).items()
                  if s == "needs")
    missing = sorted(tags - set(entries))
    stray = sorted(set(entries) - tags)
    twice = sorted(t for t in set(entries) if entries.count(t) > 1)
    unflagged = sorted(flagged - inline)
    wrongly = sorted(inline - flagged)
    n_in = sum(1 for t in tags if t.startswith("I"))
    need_in = sum(1 for t in flagged if t.startswith("I"))
    need_st = sum(1 for t in flagged if t.startswith("S"))
    derived = sum(1 for t, s in getattr(sheet, "backing", {}).items()
                  if s == "derived")
    if not quiet:
        print("  backing    %d of %d tags have one entry; inputs: %d named a "
              "source, %d derived here, %d NEED BACKING; steps: %d spend an "
              "input that needs backing; %d missing, %d stray, %d twice, %d "
              "flag(s) not on their row"
              % (len(tags) - len(missing), len(tags),
                 n_in - need_in - derived, derived, need_in, need_st,
                 len(missing), len(stray), len(twice),
                 len(unflagged) + len(wrongly)))
        for what, tags_ in (("no entry", missing), ("no such tag", stray),
                            ("entered twice", twice),
                            ("flag missing on its row", unflagged),
                            ("flagged on its row only", wrongly)):
            for t in tags_:
                print("     ! %-5s %s" % (t, what))
    return len(missing) + len(stray) + len(twice) + len(unflagged) \
        + len(wrongly)


def backing_self_test(sheet, html):
    """Delete one entry and one inline flag, and confirm each is caught."""
    failed = 0
    entry = re.search(r'<tr><td class="tag" id="b-[IS]\d+">.*?</tr>', html,
                      re.S)
    flag = re.search(r'<span class="nb">\(needs backing\)</span>', html)
    for what, planted in (
            ("deleting a backing entry",
             html[:entry.start()] + html[entry.end():] if entry else None),
            ("deleting an inline flag",
             html[:flag.start()] + html[flag.end():] if flag else None)):
        if planted is None:
            print("  self-test  *** NOTHING TO PERTURB for %s ***" % what)
            failed += 1
        elif report_backing(sheet, planted, quiet=True):
            print("  self-test  %s is caught: the backing check can fail"
                  % what)
        else:
            print("  self-test  *** %s WENT UNNOTICED ***" % what.upper())
            failed += 1
    # PLANTED CITATIONS, one per branch of `input_backing` that no mission on
    # disk reaches, plus the one fall-through an audit found: a vehicle row
    # whose notes source nothing must not be credited to its `operator`.
    def planted(source, quantity="a planted quantity"):
        """The status `input_backing` gives a made-up input."""
        return input_backing(("input", "I0", "x", quantity, 1.0, "-",
                              source))[0]
    title = (retracted() or ("",))[0]
    cases = [
        ("an operator field is not a source", "needs", planted(
            "<b>launch_vehicles.csv</b>, row <i>V</i>.  operator Blue "
            "Origin.  <span class='src'>Rounded from the band.</span>")),
        ("a source in the citation's own words", "source", planted(
            "<b>modules/calc.py</b>, <i>K</i>: per NASA SP-8007.")),
        ("a body value not measured", "needs", planted(
            "<b>asteroid_catalog.csv</b> &middot; row <i>B</i> &middot; "
            "column <i>density_gcm3</i>.  NOT measured: a class mean.")),
        ("a mineral with no quote", "needs", planted(
            "<b>mineral_value_catalog.csv</b>, row <i>m</i>.  <span "
            "class='src'>No quote: priced as zero.</span>",
            "m terrestrial quote")),
    ]
    if title:
        cases.append(("a live source beside a withdrawn one", "source",
                      planted("<b>operational_costs.csv</b>, row <i>R</i>. "
                              " <span class='src'>Anchor: NASA NEXT-C.  "
                              "Once from (%s 2023).</span>" % title)))
    for what, want, got in cases:
        if got == want:
            print("  self-test  %s: %s, as it should be" % (what, got))
        else:
            print("  self-test  *** %s: %s, NOT %s ***"
                  % (what.upper(), got, want))
            failed += 1
    caught = (not named_sources("A setting chosen to be round.")
              and named_sources("Anchor: NASA NEXT-C, flown.")
              and not named_sources("NASA has not published a figure."))
    print("  self-test  the source test %s a planted sentence with a "
          "source, one with none and one denying one"
          % ("tells apart" if caught else
                                   "*** CANNOT TELL APART ***"))
    return failed + (0 if caught else 1)

# ------------------------------------------------------------------- render
CSS = """
/* PRINT IS THE TARGET, NOT THE SCREEN.  The first version of this sheet came
   out at 49 pages, which is a document nobody prints and therefore nobody
   checks by hand -- the one use it was written for.  Everything below is set
   for paper: one line per step wherever a step fits on one, the origin
   flowing beside the value rather than stacked under it, and the page
   furniture cut to what a reader navigating on paper actually uses. */
/* BLACK AND WHITE, AND NEUTRAL GREY AT THAT.  This is printed, so every
   colour costs money: a page fill is ink over the whole sheet, and a grey
   that is not NEUTRAL -- the old --mute was #545b66, a blue -- is mixed
   from three cartridges on an inkjet rather than struck in black.  Two
   levels only, both with R = G = B, and nothing is distinguished by hue:
   an input row is marked by a rule down its edge, not by a fill. */
:root{--ink:#000;--mute:#555;--rule:#bbb;--bg:#fff;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:13px/1.35 "Iowan Old Style",Palatino,Georgia,serif;}
.wrap{max-width:62rem;margin:0 auto;padding:1.2rem .8rem 3rem;}
h1{font-size:1.5rem;line-height:1.15;margin:0 0 .1rem;}
h2{font-size:1rem;margin:1rem 0 .2rem;padding-bottom:.12rem;
   border-bottom:1.5px solid var(--ink);}
.sub{color:var(--mute);margin:0 0 .5rem;font-size:.86rem;}
p{margin:.25rem 0;}
.blurb{color:var(--mute);margin:.1rem 0 .3rem;font-size:.84rem;}
code,.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;}
table{border-collapse:collapse;width:100%%;font-size:.8rem;margin:.2rem 0 .5rem;}
th,td{text-align:left;vertical-align:top;padding:.1rem .3rem;
      border-bottom:.5px solid var(--rule);}
th{font-size:.68rem;text-transform:uppercase;letter-spacing:.03em;
   color:var(--mute);border-bottom:1px solid var(--ink);font-weight:600;}
.tw{overflow-x:auto;}
.sheet tr.in td:first-child{border-left:2px solid var(--ink);}
.tag{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.72rem;
     color:var(--ink);white-space:nowrap;font-weight:600;}
.sym{font-weight:600;overflow-wrap:break-word;}
/* INLINE, NOT STACKED.  The name under the symbol and the substitution under
   the formula were a line each on all 231 rows; run together with a
   separator they cost nothing and save about a third of the document. */
.qty{font-weight:400;color:var(--mute);}
.work{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.75rem;
      overflow-wrap:break-word;}
.sheet col.c1{width:2.7rem} .sheet col.c2{width:9.5rem}
.sheet col.c4{width:8.6rem}
.sheet th:last-child{text-align:right;}
.blk{margin:.15rem 0 .35rem;}
.sub2{color:var(--ink);}
.uses{color:var(--mute);font-size:.7rem;font-family:inherit;}
.val{font-family:ui-monospace,Menlo,Consolas,monospace;text-align:right;
     white-space:nowrap;font-weight:600;font-size:.76rem;}
.unit{color:var(--mute);font-weight:400;}
.src{color:var(--mute);font-style:italic;}
/* The flag a reader is meant to find on a skim: bold ink, no colour, so it
   survives the black-only print rules like everything else. */
.nb{font-weight:700;font-style:normal;color:var(--ink);white-space:nowrap;}
.org{font-family:inherit;font-size:.74rem;}
.note{color:var(--mute);font-size:.72rem;font-family:inherit;
      font-style:italic;}
.prose{color:var(--ink);font-size:.8rem;}
.card{border:.5px solid var(--ink);padding:.35rem .55rem;
      margin:.4rem 0 .5rem;}
.card table{margin:0;font-size:.76rem;}
.card td{border:0;padding:.03rem .5rem .03rem 0;}
.card td:first-child{white-space:nowrap;}
/* A group heading in a wide table spans the row: squeezed into the first
   column it printed `RETURN VEHICLE / SCALES WITH ITS / CARGO` down it. */
tr.grp td{padding-top:.3rem;}
/* A WIDE TABLE MUST BE ALLOWED TO BREAK ITS LONGEST WORD, BUT ONLY AT A
   JOINT.  The dial ledger carries field names and file paths with no space
   in them, and a table cannot be narrower than its widest unbreakable
   token: it ran to 941px against 741px of paper, so the browser shrank
   EVERY page to 79%% to fit it.  `overflow-wrap:anywhere` fixed the width
   and wrecked the words: it lets EVERY column shrink to one letter, so the
   browser handed the width to the longest description and printed
   `max_mini / ng_fractio / n` and `THROUG / HPUT` down a 50px column.  The
   joints are now in the markup (`typeset` puts a <wbr> after each `_` and
   `/` of a long token), and `break-word` is only the last resort for a
   token with none. */
.wide td{overflow-wrap:break-word;}
/* A short hyphenated word (a date, `E-chondrite`, `on-site`) stays on one
   line; `typeset` wraps it. */
.nw{white-space:nowrap;}
/* `D.h` attaches a self-link to every anchored heading.  It is useful on
   screen and is furniture on paper, so it fades in on hover and is removed
   outright from the print rules -- which the narrative document next door
   does and this stylesheet did not, so a pilcrow printed beside all
   seventeen headings. */
h2 a.anchor{color:var(--mute);text-decoration:none;opacity:0;
            margin-left:.3em;font-weight:400;}
h2:hover a.anchor{opacity:1;}
.toc{font-size:.76rem;color:var(--mute);margin:0 0 .5rem;}
.foot{margin-top:.8rem;padding-top:.3rem;border-top:1.5px solid var(--ink);
      color:var(--mute);font-size:.76rem;}
.foot p{margin:.2rem 0;}
.ok{font-weight:600;}
a{color:inherit;}
@media print{
  body{font-size:%(prose).1fpt;line-height:1.26;}
  .wrap{max-width:none;padding:0;}
  h1{font-size:13pt} h2{font-size:%(prose).1fpt;margin:.42rem 0 .12rem}
  table{font-size:%(t).1fpt} th{font-size:%(th).1fpt}
  th,td{padding:.4pt 2.2pt}
  .work{font-size:%(work).1fpt} .val{font-size:%(t).1fpt}
  .org{font-size:%(org).1fpt} .uses{font-size:%(uses).1fpt}
  .note{font-size:%(note).1fpt}
  h2 a.anchor{display:none;}
  h2{page-break-after:avoid;} tr{page-break-inside:avoid;}
  tr.grp{page-break-after:avoid;}
  .tw{overflow:visible;}
  a{color:inherit;text-decoration:none;}
}
@page{size:%(paper)s;margin:8mm 7mm;}
"""


# THE PAGE COUNT IS SET BY THE TABLE, NOT BY THE BODY TEXT.  Almost every
# line of this document is inside a table, so raising the BASE font leaves the
# count where it was and raising the TABLE font moves it.
#
# 🚨  THE CURVE THAT USED TO SIT HERE WAS TYPED, AND IT ROTTED TWICE.  It
# was re-measured once after the citations stopped being truncated, and then
# the dial ledger arrived, ran off the edge of the paper, and the browser
# shrank every page to fit: 23 pages at EVERY table size from 6.8 to 8.6pt,
# against a curve promising 14 to 19.  So the count is not stated here; every
# PDF run prints it, and `report_paper` fails a page that would be shrunk.
DEFAULT_PT = 7.2

# How many terms of the learning-curve mean one line of the page carries.
# Twenty keeps a group to a few lines of the narrow working column; the
# point is only that N terms never become ONE row taller than a sheet.
LC_GROUP = 20

# THE PAPER IS DECLARED, BECAUSE THE BROWSER'S DEFAULT WAS NOT THE ONE THIS
# FILE ASSUMED.  Every comment here measured against A4; every PDF this file
# has ever written was US Letter (MediaBox 612 x 792), which is wider and
# shorter.  `@page` now names the size and the measurement reads the same
# name, so the two cannot disagree again.  Letter stays the default because
# it is what every PDF so far has actually been.
PAPER_MM = {"letter": (215.9, 279.4), "A4": (210.0, 297.0)}
DEFAULT_PAPER = "letter"


def stylesheet(pt=DEFAULT_PT, paper=DEFAULT_PAPER):
    """The stylesheet, with the print sizes scaled off one table size."""
    return CSS % {"t": pt, "th": pt - 0.9, "work": pt - 0.2,
                  "org": pt - 0.3, "uses": pt - 0.6, "note": pt - 0.5,
                  "prose": pt + 1.4, "paper": paper}


def paper_px(paper=DEFAULT_PAPER):
    """The paper's printable box in CSS px, from the size and the @page margin.

    Derived rather than typed: the margins are read out of the stylesheet's
    own `@page` rule, so changing them moves the measurement with them.
    """
    vert, horiz = (float(x) for x in re.search(
        r"@page\{size:%\(paper\)s;margin:([\d.]+)mm ([\d.]+)mm;\}",
        CSS).groups())
    w_mm, h_mm = PAPER_MM[paper]
    return (round((w_mm - 2 * horiz) * 96 / 25.4),
            round((h_mm - 2 * vert) * 96 / 25.4))


# Where a word may break, said in the markup; see the `.wide td` rule.  A
# token longer than `_LONG` characters (a field name, a file path) may break
# after any `_`, `/` or `\` that leaves `_STUB` characters on each side (so
# never `max_mining_duration_ / yr`); a shorter one with a hyphen in it may
# not break at all.  Text only: tags, and everything inside <style>,
# <script> and <title>, pass through untouched.
_LONG = 20
_STUB = 5
_TAGS = re.compile(r"(<[^>]*>)")
_TOKEN = re.compile(r"[^\s<>]+")
_JOINT = re.compile(r"(?<=[_/\\])(?=[^_/\\])")
_RAW = ("style", "script", "title")


def _set_token(m):
    """One token of text, with its break points marked; see `typeset`."""
    t = m.group(0)
    if len(t) > _LONG:
        cuts = [j.start() for j in _JOINT.finditer(t)
                if _STUB <= j.start() <= len(t) - _STUB]
        return "<wbr>".join(t[a:b] for a, b in zip([0] + cuts, cuts + [None]))
    if "-" in t.strip("-"):
        return '<span class="nw">%s</span>' % t
    return t


def typeset(html):
    """The page as it is printed: `html` with its break points marked.

    APPLIED TO THE PAGE THAT IS WRITTEN AND MEASURED, NEVER TO THE ONE THE
    TEXT CHECKS READ.  Those strip tags to a space, so a <wbr> inside
    `mining_rate_kg_per_day` would hand them seven words; the characters a
    reader sees are the same either way.
    """
    out, raw = [], None
    for piece in _TAGS.split(html):
        if piece.startswith("<"):
            name = re.match(r"</?\s*([a-zA-Z]*)", piece).group(1).lower()
            if name in _RAW:
                raw = None if piece.startswith("</") else name
            out.append(piece)
        else:
            out.append(piece if raw else _TOKEN.sub(_set_token, piece))
    out = "".join(out)
    # It runs after the checks, so it proves it moved no visible character.
    if _TAGS.sub("", out) != _TAGS.sub("", html):
        raise AssertionError("typeset changed the text of the page")
    return out


def said_once(source, tag, said):
    """`source` with every long quotation already printed above replaced
    by a pointer to the row that printed it.

    🚨  SIX ROWS READ ONE REFERENCE ROW, AND ITS NOTES PRINTED SIX TIMES.
    Krypton's paragraph stood under its penalty, its Isp, its tank, its
    efficiency, its thruster mass and its price, and New Glenn's under its
    capacity, its fairing and its price: two pages of text said before.  A
    citation is per INPUT, which is right, and the notes are per ROW, so the
    first input to quote them keeps them and the rest point back.  The dial
    ledger quotes every field's definition first, so `said` arrives seeded
    with those (`part_dials`).

    Done here, at render, ON PURPOSE: part 18 reads each input's whole
    citation to find the source it names, and a pointer names none.  A short
    quotation is kept, because the pointer would be as long as the text.
    """
    def swap(m):
        """One quotation: kept the first time, a pointer every other time."""
        key = " ".join(m.group(1).split())
        if len(plain(key)) < SAID_ONCE_CHARS:
            return m.group(0)
        if key in said:
            return "<span class='src'>%s</span>" % said[key]
        said[key] = "Quoted in full at %s." % tag_link(tag, "r")
        return m.group(0)
    return _SRC_SPAN.sub(swap, source)


# Shorter than this and a quotation is kept where it stands: "The same
# judgement as kamacite's, above." is already the pointer.
SAID_ONCE_CHARS = 100


def render_row(row, backing=None, said=None):
    """One row of the sheet: an input, a step or a prose line.

    EVERYTHING THAT CAN SHARE A LINE DOES.  A step used to occupy four: the
    name under the symbol, the substitution under the formula, the cited tags
    under that, and the note under that.  None of the four needed its own
    line, and 231 rows times three wasted lines is most of a document nobody
    would print.  The separators carry the structure instead.

    `backing` is the backing part's {tag: status}: a row's tag links to its
    entry there, and a row that part flags carries the flag here too.
    `said` is what the page has quoted so far; see `said_once`.
    """
    kind = row[0]
    if kind == "prose":
        return '<tr><td class="prose" colspan="4">%s</td></tr>' % row[1]
    tag = row[1]
    cell = '<td class="tag" id="r-%s"><a href="#b-%s">%s</a></td>' % (
        tag, tag, tag)
    flag = (' <span class="nb">(needs backing)</span>'
            if (backing or {}).get(tag) == "needs" else "")
    if kind == "input":
        _k, tag, symbol, quantity, value, unit, source = row
        if said is not None:
            source = said_once(source, tag, said)
        return ('<tr class="in">%s'
                '<td class="sym">%s <span class="qty">%s</span>%s</td>'
                '<td class="org cite">%s</td>'
                '<td class="val">%s <span class="unit">%s</span></td></tr>'
                % (cell, D.esc(symbol), D.esc(quantity), flag, source,
                   P(value, 12) if isinstance(value, (int, float))
                   else D.esc(value), D.esc(unit)))
    (_k, tag, symbol, quantity, formula, substitution, value, unit, tags,
     note) = row
    return ('<tr>%s'
            '<td class="sym">%s <span class="qty">%s</span>%s</td>'
            '<td class="work">%s <span class="sub2">= %s</span>%s%s</td>'
            '<td class="val">%s <span class="unit">%s</span></td></tr>'
            % (cell, D.esc(symbol), D.esc(quantity), flag, D.esc(formula),
               D.esc(substitution),
               ' <span class="uses">[%s]</span>' % ", ".join(tags)
               if tags else "",
               ' <span class="note">%s</span>' % note if note else "",
               P(value, 12) if isinstance(value, (int, float))
               else D.esc(value), D.esc(unit)))


def header(out):
    """The subject card: which mission, at which release, out of what."""
    C, P_ = out["C"], out["P"]
    shape = D.shape_sentence(D.architecture(out))
    rows = [("body", "%s (%s)" % (D.esc(out["designation"]),
                                  D.esc(C["body"].get("spectral_type")))),
            ("destination", D.esc(C["destination"])),
            ("architecture", shape),
            ("programme", "N = %d, %d ship(s) x %d campaign(s)"
             % (P_["n"], P_["f"], P_["w"])),
            ("cost / revenue", "%s x" % P(P_["obj"])),
            ("best of", "%s evaluable bodies in this cell"
             % D.fmt(C["population"], 0)),
            ("source", D.esc(out["cell"])),
            ("calc version", D.esc(out["terms"]["stamp"])),
            ("market model", D.esc(out["terms"]["market"]))]
    # Which catalog and tables the run read, derived from the files the
    # derivation loaded; see `input_provenance`.
    rows += [(k, D.esc(v)) for k, v in C.get("provenance", [])]
    rows.append(("built", datetime.date.today().isoformat()))
    return ('<div class="card"><table>%s</table></div>'
            % "".join("<tr><td>%s</td><td><b>%s</b></td></tr>" % (k, v)
                      for k, v in rows))


def footer(out, sheet):
    """What the derivation was checked against, and what it borrowed."""
    c = out["check"]
    bits = ['<div class="foot">']
    checked, unchecked, bad = check_substitutions(sheet)
    bits.append(
        "<p>Every substitution on this page has been parsed and evaluated "
        "and held to the value printed beside it: <span class='ok'>%d of %d "
        "reproduce their own result</span>, %d differ, and %s.  That is a "
        "check on the PAGE rather than on the model, and it is the one the "
        "model's own comparison cannot make: a substitution can omit a "
        "term, or round an operand past the point where it reproduces the "
        "answer, while every derived quantity is still exactly right.</p>"
        % (checked - len(bad), checked, len(bad),
           "%d lines are prose rather than arithmetic (%s)"
           % (len(unchecked), ", ".join(D.esc(t) for t, _s, _x in unchecked))
           if unchecked else "no line is prose rather than arithmetic"))
    bits.append(
        "<p>Every figure above is derived by "
        "<code>campaign/worked_calculation.py</code> and then compared, "
        "column by column, against the row the pipeline actually produced: "
        "<span class='ok'>%d quantities, %d bit-exact, %d within %g, "
        "%d differing</span>, %s.  The worksheet adds no arithmetic of its "
        "own; it changes the order things are said in and cites where each "
        "input came from.</p>"
        % (c["n"], c["exact"], c["close"], c["tol"], len(c["bad"]),
           # Nothing is worst when nothing differs: the comparator names no
           # quantity, and the sentence used to end "on ."
           "worst relative difference %.3e on <code>%s</code>"
           % (c["worst"], D.esc(c["worst_name"])) if c["worst_name"]
           else "and not one of them differs in any bit"))
    if out["borrows"]:
        # `borrowed_shape` returns (name, why) pairs and the footer prints
        # what it finds, so a borrowing added tomorrow discloses itself
        # whether or not anybody remembers this sentence.
        bits.append("<p>What the derivation reads from the model rather than "
                    "writing out, disclosed by walking its own source: "
                    "%s.</p>"
                    % "; ".join("<code>%s</code> (%s)"
                                % (D.esc(name), D.esc(why))
                                for name, why in out["borrows"]))
    seen, loose, reruns = untraced(sheet, _PAGE.get("html", ""))
    if seen:
        bits.append(
            "<p>And every number the page ASSERTS is one of those: "
            "<span class='ok'>%d of %d</span> are a tagged input, a step's "
            "own value, an operand inside a substitution, or a table claim "
            "checked the same way%s.  %d %s this whole document "
            "re-evaluated at another setting (the fixed point's earlier "
            "passes, the concentration ladder, the programme ladder), and "
            "each says so above itself, because inventing a one-line "
            "substitution for a row that is a whole cascade would be a "
            "worse answer than naming what it is.</p>"
            % (seen - len(loose), seen,
               "" if not loose else
               ", and %d DO NOT: %s"
               % (len(loose), D.esc(", ".join(t for t, _w in loose))),
               reruns, "table is" if reruns == 1 else "tables are"))
    good, missing = origins(sheet)
    bits.append("<p>Every input is cited to the file and the row or field it "
                "came from, and that is asserted rather than claimed: "
                "<span class='ok'>%d of %d</span> name one%s.</p>"
                % (len(good), len(good) + len(missing),
                   "" if not missing else
                   ", and %d DO NOT: %s"
                   % (len(missing),
                      D.esc(", ".join(t for t, _s in missing)))))
    flags = getattr(sheet, "backing", {})
    need = sorted((t for t, s in flags.items() if s == "needs"),
                  key=lambda t: (t[0], int(t[1:])))
    # The list is the inputs, so it sits beside them: after the steps it read
    # as the steps' tags.
    bits.append("<p>%s rows marked <b>(needs backing)</b>: %d inputs nothing "
                "outside this repository stands behind (%s), and %d steps "
                "that spend one.  Each is listed with its reason in %s.</p>"
                % (len(need), sum(1 for t in need if t.startswith("I")),
                   ", ".join(t for t in need if t.startswith("I")) or "none",
                   sum(1 for t in need if t.startswith("S")),
                   ref("backing")))
    loose_in, loose_step = sheet.unspent()
    bits.append("<p>%d inputs and %d steps.  %s  %d steps are cited by "
                "nothing further, which is what a result or a diagnostic "
                "looks like on a worksheet.</p>"
                % (sheet.n_input, sheet.n_step,
                   "Every input is spent by a step."
                   if not loose_in else
                   "REGISTERED AND NEVER SPENT: %s.  An input no step uses "
                   "is a missing step or a citation nobody needs."
                   % D.esc(", ".join(sorted(sheet.tag[k]
                                            for k in loose_in))),
                   len(loose_step)))
    bits.append("<p>Generated %s from <code>%s</code>.  Re-run "
                "<code>py campaign/verification_sheet.py</code> and every "
                "figure moves with the model.</p>"
                % (datetime.date.today().isoformat(), D.esc(out["cell"])))
    bits.append("</div>")
    return "".join(bits)


def build_sheet(out):
    """Every part, in the order the model evaluates them, as one Worksheet."""
    sheet = Worksheet()
    builders = {"constants": part_constants, "body": part_body,
                "prices": part_prices, "transfer": part_transfer,
                "ratios": part_ratios, "plant": part_plant_rating,
                "fixed_point": part_fixed_point, "settled": part_settled,
                "stack": part_stack, "clock": part_clock, "hold": part_hold,
                "market": part_market, "searches": part_searches,
                "reliability": part_reliability, "cost": part_cost,
                "answer": part_answer, "checks": part_checks}
    # The dial ledger is BUILT LAST and printed second: it names, beside each
    # dial, the tag every other part registered it under, so it has to see
    # them all first.  Its position on the page is still its PART_KEYS slot.
    # The backing ledger is built after THAT, for the same reason: it has an
    # entry for every row every other part registered.
    for key in PART_KEYS:
        if key not in ("dials", "backing"):
            builders[key](sheet, out)
    part_dials(sheet, out)
    part_backing(sheet, out)
    sheet.parts.sort(key=lambda part: part["n"])
    assert [part["key"] for part in sheet.parts] == list(PART_KEYS), (
        "the parts built are not the parts PART_KEYS lists")
    return sheet


# THE FOOTER REPORTS ON THE PAGE IT IS PART OF, which is circular: the
# traceability check reads the rendered HTML, and the footer is in it.  The
# page is therefore rendered once without the footer, checked, and then
# rendered again with it -- and the second pass adds no number the first did
# not already carry, because the footer only ever counts.
_PAGE = {}


def document(out, sheet=None, pt=DEFAULT_PT, paper=DEFAULT_PAPER):
    """Assemble the whole worksheet as one HTML page."""
    sheet = build_sheet(out) if sheet is None else sheet
    body = [header(out)]
    contents = []
    said = dict(getattr(sheet, "said", {}))
    for part in sheet.parts:
        anchor = "p%d" % part["n"]
        # One entry per line-piece: wrapped freely, a part's number ended one
        # line and its title began the next.
        contents.append('<a class="nw" href="#%s">%s</a>'
                        % (anchor, part["title"]))
        # The part's number is a label, like a table row's: it read as an
        # untraced claim the day the page reached a twelfth part, having
        # been "traced" through eleven only by coinciding with small
        # integers some step happened to produce.
        body.append(D.h(2, re.sub(r"^(\d+)\.", r'<span class="ord">\1.</span>',
                                  D.esc(part["title"]), count=1), anchor))
        if part["blurb"]:
            body.append('<p class="blurb">%s</p>' % part["blurb"])
        # A BLOCK IS A TABLE OF ITS OWN, SO IT SITS BETWEEN THE STEP TABLES,
        # NOT INSIDE ONE.  Nested in a row, it lost the tag column's width,
        # wore the outer header over columns that did not line up with it on
        # every page it reached, and (rows being kept whole in print) was
        # pushed to a fresh page, leaving the last a third blank.  A run of
        # rows with no input or step in it is prose and is set as prose.
        runs = []
        for r in part["rows"]:
            if r[0] == "block":
                runs.append(r)
            elif runs and isinstance(runs[-1], list):
                runs[-1].append(r)
            else:
                runs.append([r])
        for run in runs:
            if isinstance(run, tuple):
                body.append('<div class="blk">%s</div>' % run[1])
                continue
            # Prose before the first tagged row and after the last is set
            # outside the table, so its header sits on top of a step.
            tagged = [i for i, r in enumerate(run) if r[0] != "prose"]
            lead, tail = ((tagged[0], tagged[-1] + 1) if tagged
                          else (len(run), len(run)))
            body.extend('<p class="prose">%s</p>' % r[1] for r in run[:lead])
            run, after = run[lead:tail], run[tail:]
            if run:
                body.append('<div class="tw"><table class="sheet">'
                            '<colgroup><col class="c1"><col class="c2">'
                            '<col class="c3"><col class="c4"></colgroup>'
                            '<thead><tr><th>tag</th><th>quantity</th>'
                            '<th>how it is worked out</th><th>value</th>'
                            '</tr></thead><tbody>')
                body.extend(render_row(r, getattr(sheet, "backing", None),
                                       said)
                            for r in run)
                body.append("</tbody></table></div>")
            body.extend('<p class="prose">%s</p>' % r[1] for r in after)
    # The parts, rendered once, are what the traceability check reads; the
    # footer is then written against that and appended.  See `_PAGE`.
    _PAGE["html"] = "".join(body[1:])
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Verification worksheet: %s</title><style>%s</style></head>"
        "<body><div class='wrap'><h1>Verification worksheet: %s</h1>"
        "<p class='sub'>Every number behind %s x, with its source, in the "
        "order the model works them out.</p>%s<p class='blurb'>%s</p>"
        "%s%s</div></body></html>"
        % (D.esc(out["designation"]), stylesheet(pt, paper),
           D.esc(out["designation"]),
           P(out["P"]["obj"]), header(out),
           " &middot; ".join(contents),
           "".join(body[1:]), footer(out, sheet)))


_HEX = re.compile("#([0-9a-fA-F]{3,8})")
# The stylesheet explains the trap by NAMING the colour it
# replaced, so the scan reads the rules and not the prose
# about them; a comment cannot reach a printer.
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_FILL = re.compile("background(?:-color)?[ ]*:[ ]*([^;}]+)")


def monochrome(css):
    """Colours in `css` that would cost more than black ink, as findings.

    THE PAGE IS PRINTED, SO EVERY COLOUR IS A COST.  A fill is ink over the
    whole area rather than over the glyphs, and a grey that is not NEUTRAL
    is mixed from three cartridges on an inkjet instead of struck in black:
    the old secondary text was #545b66, which is a blue.  So a hex has to
    satisfy R = G = B, and the only fill allowed is the page itself, which
    is white and therefore no ink at all.
    """
    css = _CSS_COMMENT.sub(" ", css)
    bad = []
    for hexcode in _HEX.findall(css):
        h = hexcode[:6] if len(hexcode) in (6, 8) else hexcode[:3]
        if len(h) == 3:
            rgb = [int(c * 2, 16) for c in h]
        else:
            rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        if len(set(rgb)) != 1:
            bad.append(("#" + hexcode, "not a neutral grey: R G B = %s"
                        % " ".join(str(v) for v in rgb)))
    for fill in _FILL.findall(css):
        fill = fill.strip()
        if fill not in ("var(--bg)", "#fff", "#ffffff", "white", "none",
                        "transparent"):
            bad.append((fill, "a fill is ink over the whole area"))
    return bad


_COLOUR_GLYPH = re.compile("[\ufe0f\U0001F000-\U0001FAFF]")


def colour_glyphs(html):
    """Characters the page would print as colour emoji, as findings.

    THE STYLESHEET IS NOT THE ONLY INK.  A field comment's ⚠️ carries
    VARIATION SELECTOR-16, which asks the browser for the colour glyph, and
    six of them printed yellow while `monochrome` passed, because it reads
    the CSS and the colour was in the text.  `trim` turns the selector into
    its text twin; this asks the page whether anything still requests a
    colour glyph, or is one (the supplementary emoji planes have no text
    form to ask for).
    """
    body = re.sub(r"(?is)<(style|script)\b.*?</\1>", " ", html)
    bad = []
    for match in _COLOUR_GLYPH.finditer(body):
        start = max(0, match.start() - 40)
        context = " ".join(_TAGS.sub(" ", body[start:match.start()]).split())
        bad.append(("U+%04X" % ord(match.group()),
                    "a colour glyph, after ...%s" % context[-30:].encode(
                        "ascii", "replace").decode()))
    return bad


FURNITURE = ("&#182;", "¶")


def print_furniture(css, html):
    """Screen furniture that would print, as findings.

    A SELF-LINK IS USEFUL ON SCREEN AND IS A SMUDGE ON PAPER.  `D.h` gives
    every anchored heading a pilcrow so the section can be linked to; the
    narrative document next door hides it in its print rules and this
    stylesheet did not, so a paragraph mark printed beside all seventeen
    headings and nobody noticed until it was on paper.

    The rule cannot be "hide everything decorative", because nothing in the
    markup says which elements those are.  What CAN be checked is the other
    direction: any element carrying one of a short list of furniture
    GLYPHS -- characters that are never data here -- has to be hidden by
    the print block.  The list is short and explicit on purpose; a glyph
    that is data somewhere else does not belong on it.
    """
    block = css[css.find("@media print{"):]
    bad = []
    for glyph in FURNITURE:
        for match in re.finditer(r'<(\w+)[^>]*class="([^"]+)"[^>]*>'
                                 + re.escape(glyph), html):
            tag, klass = match.group(1), match.group(2).split()[0]
            hidden = re.search(r"\.%s[^{]*\{[^}]*display\s*:\s*none"
                               % re.escape(klass), block)
            if not hidden:
                bad.append((klass, "<%s> carries %s and the print rules do "
                                   "not hide it" % (tag, glyph)))
    return bad


def report_furniture(css, html, quiet=False):
    """Print the furniture check, and return the number of findings."""
    bad = print_furniture(css, html)
    if not quiet:
        print("  furniture  %d screen-only element(s) that would print"
              % len(bad))
        for klass, why in bad:
            print("     ! .%-10s %s" % (klass, why))
    return len(bad)


def report_monochrome(html, quiet=False):
    """Print the ink check, and return the number of findings."""
    glyphs = colour_glyphs(html)
    bad = monochrome(CSS) + glyphs
    if not quiet:
        print("  ink        %d colour(s) in the stylesheet, %d that would "
              "cost more than black; %d colour glyph(s) in the text"
              % (len(set(_HEX.findall(_CSS_COMMENT.sub(" ", CSS)))),
                 len(bad) - len(glyphs), len(glyphs)))
        for what, why in bad:
            print("     ! %-12s %s" % (what, why))
    return len(bad)


def print_variant(html):
    """The same page with the PRINT rules applied unconditionally.

    WHAT GETS ONTO PAPER CANNOT BE MEASURED ON THE SCREEN STYLESHEET, and
    the two differ by about a third in every font size here.  Lifting the
    `@media print` block out of its query gives a page a browser will lay
    out exactly as the printer does, so the one question that matters --
    does anything run off the edge, is any single row taller than a sheet --
    can be asked with a viewport and four lines of JavaScript instead of
    guessed at.

    🚨  THAT QUESTION WAS ASKED ONCE, BY HAND, AND THEN NOT AGAIN.  Measured
    on 2026-09-19 at "A4's 741 x 1062 px": nothing overflowed.  The dial
    ledger arrived on 2026-10-08 and ran 200px off the edge, and nothing said
    so for five days, because the measurement was a sentence in this
    docstring rather than code -- and it was taken on A4 while every PDF was
    Letter.  `report_paper` asks it on every PDF run now, at the size
    `@page` declares.
    """
    i = html.index("@media print{")
    j = html.index(chr(125) + chr(10) + "@page", i)
    return html[:i] + html[i + len("@media print{"):j] + html[j + 1:]


# Run in the page once it has laid out: pin the body to the paper's printable
# width, then record what runs past that edge and which table row (one that
# holds no table of its own) is taller than a sheet.  The answer goes in the
# document TITLE, which the browser writes into the PDF's metadata, so it can
# be read back with nothing but a regex -- `--dump-dom` would be the obvious
# route and writes nothing to a redirected stdout on Windows.
_MEASURE_JS = """<script>addEventListener('load',function(){
var W=%(w)d,H=%(h)d,de=document.documentElement,b=document.body;
de.style.margin='0';b.style.margin='0';b.style.width=W+'px';
var x0=b.getBoundingClientRect().left,all=b.querySelectorAll('*'),over=[],
widest=W;
for(var i=0;i<all.length;i++){var r=all[i].getBoundingClientRect().right-x0;
 if(r>widest)widest=r;if(r>W+0.5)over.push(all[i]);}
var set=new Set(over),leaf=over.filter(function(e){
 for(var c=e.firstElementChild;c;c=c.nextElementSibling)if(set.has(c))
 return false;return true;});
var rows=[].filter.call(document.querySelectorAll('tr'),function(t){
 return !t.querySelector('table')&&t.getBoundingClientRect().height>H;});
function d(e,v){return [e.tagName.toLowerCase()+(e.className?'.'+
 String(e.className).split(' ')[0]:''),Math.round(v),
 (e.textContent||'').replace(/\\s+/g,' ').trim().slice(0,50)];}
document.title='MEASURE '+JSON.stringify({w:W,h:H,widest:Math.round(widest),
 over:leaf.length,tall:rows.length,
 overs:leaf.slice(0,6).map(function(e){
  return d(e,e.getBoundingClientRect().right-x0);}),
 talls:rows.slice(0,3).map(function(e){
  return d(e,e.getBoundingClientRect().height);})});});</script>"""


def _pdf_title(data):
    """The /Title of a PDF's info dictionary, decoded; None if it has none."""
    m = re.search(rb"/Title\s*(<[0-9A-Fa-f\s]*>|\((?:\\.|[^\\)])*\))", data)
    if not m:
        return None
    raw = m.group(1)
    if raw.startswith(b"<"):
        b = bytes.fromhex(re.sub(rb"\s", b"", raw[1:-1]).decode("ascii"))
        return (b[2:].decode("utf-16-be") if b[:2] == b"\xfe\xff"
                else b.decode("latin-1"))
    body = raw[1:-1]
    return re.sub(rb"\\(.)", rb"\1", body).decode("latin-1")


def paper_layout(html, paper=DEFAULT_PAPER):
    """Lay the PRINT variant out at the paper's width in a real browser.

    Returns the measurement as a dict, or None when no browser is installed.
    """
    import json
    import tempfile
    w, h = paper_px(paper)
    page = print_variant(typeset(html))
    cut = page.rfind("</body>")
    page = (page[:cut] + _MEASURE_JS % {"w": w, "h": h} + page[cut:]
            if cut >= 0 else page + _MEASURE_JS % {"w": w, "h": h})
    if not any(os.path.exists(p) for p in W.CHROME):
        return None
    scratch = tempfile.mkdtemp(prefix="vs_paper_")
    try:
        src = os.path.join(scratch, "measure.html")
        pdf = os.path.join(scratch, "measure.pdf")
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(page)
        if not W.render_pdf(src, pdf, extra=["--window-size=%d,%d"
                                             % (w + 400, h),
                                             "--hide-scrollbars"]):
            raise AssertionError("the browser wrote no measurement page")
        with open(pdf, "rb") as fh:
            title = _pdf_title(fh.read()) or ""
    finally:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)
    if not title.startswith("MEASURE "):
        raise AssertionError("the measurement page came back without its "
                             "measurement (title %r)" % title[:80])
    return json.loads(title[len("MEASURE "):])


def report_paper(html, paper=DEFAULT_PAPER, quiet=False):
    """Does the page fit the paper it declares?  Returns the findings.

    Two ways to fail: anything past the printable width, which makes the
    browser shrink EVERY page to fit and silently cancels the font setting;
    and a single table row taller than a sheet, which no page break can hold.
    """
    m = paper_layout(html, paper)
    if m is None:
        if not quiet:
            print("  paper      no Chrome or Edge installed: the print layout "
                  "is NOT measured")
        return 0
    bad = m["over"] + m["tall"]
    if not quiet:
        print("  paper      %s, %d x %d px printable: the widest element "
              "reaches %d px; %d run past the edge, %d row(s) taller than a "
              "sheet" % (paper, m["w"], m["h"], m["widest"], m["over"],
                         m["tall"]))
        for what, px, text in m["overs"]:
            print("     ! %-16s reaches %d px  %s" % (what, px, text))
        for what, px, text in m["talls"]:
            print("     ! %-16s %d px tall  %s" % (what, px, text))
    return bad


def paper_self_test(html, paper=DEFAULT_PAPER):
    """Plant a block wider than the paper and confirm the check notices."""
    w, _h = paper_px(paper)
    cut = html.rfind("</div></body>")
    planted = (html[:cut] + '<div style="width:%dpx">planted</div>' % (2 * w)
               + html[cut:])
    if paper_layout(planted, paper) is None:
        print("  self-test  *** no Chrome or Edge: the paper check's "
              "self-test did NOT run ***")
        return 0
    if report_paper(planted, paper, quiet=True):
        print("  self-test  a block twice the paper's width is caught: the "
              "paper check can fail")
        return 0
    print("  self-test  *** A BLOCK TWICE THE PAPER'S WIDTH WENT UNNOTICED ***")
    return 1


def sheet_lines():
    """Every line of this module's functions that COULD run.

    `worked_calculation.renderer_lines` asks the same question of the
    narrative renderer; this is it for the worksheet, read out of the
    compiled module so a blank or a comment is never counted as unrun.
    """
    import dis
    import io
    top = compile(io.open(__file__, encoding="utf-8").read(), __file__,
                  "exec")
    inner = ("<genexpr>", "<listcomp>", "<dictcomp>", "<setcomp>")
    seen, todo = set(), [c for c in top.co_consts
                         if hasattr(c, "co_code") and c.co_name not in inner]
    while todo:
        code = todo.pop()
        for _offset, line in dis.findlinestarts(code):
            if line:
                seen.add(line)
        todo += [c for c in code.co_consts if hasattr(c, "co_code")]
    return seen


def sweep(args):
    """Build the worksheet for one mission per architecture, and check each.

    🚨  A WORKSHEET CHECKED ON ITS BEST CASE HAS NEVER RUN ON THE REST.
    Every page this file had built was a cislunar M-type on a solar plant, a
    propulsive return and the capacity-cap market, so the GEO, Earth, lunar
    and Mars return legs, ISRU, boil-off, aerocapture, RTG plants and three
    of the four market models were code no reader had seen rendered -- the
    shape CLAUDE.md records twice for the narrative document next door.  The
    missions are FOUND by `worked_calculation`'s own sweep, so the two
    documents are held to the same cover of what is on disk, and every page
    is held to every check a single page is.

    The trace over this module says which lines no swept page ran: a branch
    that is in the file and has never rendered is a branch nobody has read.
    """
    found, about = W.sweep_candidates(args.max_sources, args.source)
    if not found:
        sys.exit("nothing to sweep: no Stage 4 catalog and no archived cell.")
    chosen, _uncovered, want = W.cover(dict(found), args.max_shapes)
    print("  found     %d architecture(s); building %d worksheet(s)\n"
          % (len(found), len(chosen)))
    bodies = W.catalog_bodies([des for _s, _o, _k, _n, des in chosen])
    per_source = {}
    for _sig, _obj, _kind, path, des in chosen:
        per_source.setdefault(path, []).append(des)
    rows = {}
    for path, wanted in per_source.items():
        meta = about[path]
        rows[path] = W.rows_for(meta["path"], wanted, population=meta["rows"])
    hit, failures, refused, built = set(), 0, 0, 0
    this = os.path.abspath(__file__)

    def tracer(frame, event, _arg):
        """Record every line of this module that runs, and keep tracing."""
        if (os.path.abspath(frame.f_code.co_filename) == this
                and event in ("call", "line")):
            hit.add(frame.f_lineno)
        return tracer

    # Named missions join the same traced run: a branch only one row on disk
    # takes is covered by naming that row, and the coverage report below is
    # then one report rather than several that have to be read together.
    jobs = [(about[path]["label"] + "  " + des, sig, kind, path, des, None)
            for sig, _obj, kind, path, des in chosen]
    for spec in args.also or []:
        bits = spec.split("|")
        jobs.append(("%s  %s" % (os.path.basename(os.path.dirname(bits[0]))
                                 + "/" + os.path.basename(bits[0]), bits[1]),
                     None, "also", bits[0], bits[1],
                     float(bits[2]) if len(bits) > 2 else None))
    import master
    for label, sig, kind, path, des, mining in jobs:
        before = master.CALC_CONFIG.max_mining_fraction
        if mining is not None:
            master.CALC_CONFIG.max_mining_fraction = mining
        try:
            if kind == "also":
                out = W.build(W.run_winner(path, des), label)
            else:
                told = W.ore_of(path) if kind == "cell" else None
                out = W.build(rows[path][des], label, body=bodies[des],
                              run_beneficiated=(told if told is not None
                                                else about[path]
                                                ["beneficiated"]))
        except SystemExit as exc:
            master.CALC_CONFIG.max_mining_fraction = before
            print("  %-52s REFUSED" % label)
            for line in str(exc).splitlines():
                print("      %s" % line.strip())
            refused += 1
            continue
        c = out["check"]
        if c["bad"]:
            master.CALC_CONFIG.max_mining_fraction = before
            print("  %-52s *** %d DIFFER: the derivation, not the page ***"
                  % (label, len(c["bad"])))
            failures += 1
            continue
        sys.settrace(tracer)
        try:
            sheet = build_sheet(out)
            html = document(out, sheet)
        except Exception as exc:
            sys.settrace(None)
            import traceback
            print("  %-52s *** THE SHEET RAISED ***" % label)
            traceback.print_exc()
            failures += 1
            continue
        finally:
            sys.settrace(None)
            master.CALC_CONFIG.max_mining_fraction = before
        built += 1
        # The checks are traced too: they run on every page, and a coverage
        # report that left them out listed them as code nobody had run.
        sys.settrace(tracer)
        try:
            bad = (report_substitutions(sheet, quiet=True)
                   + report_origins(sheet, quiet=True)
                   + report_untraced(sheet, html, quiet=True)
                   + report_dials(html, quiet=True)
                   + report_placeholders(sheet, html, quiet=True)
                   + report_monochrome(html, quiet=True)
                   + report_furniture(stylesheet(DEFAULT_PT), html,
                                      quiet=True)
                   + report_paper(html, quiet=True))
        finally:
            sys.settrace(None)
        loose_in, _loose_step = sheet.unspent()
        print("  %-52s %8.3fx  %d inputs, %d steps%s"
              % (label, out["P"]["obj"], sheet.n_input, sheet.n_step,
                 "" if not (bad or loose_in) else
                 "  *** %d page finding(s), %d unspent input(s) ***"
                 % (bad, len(loose_in))))
        print("      %s" % (W.describe_signature(sig) if sig
                             else "named with --also"))
        if bad or loose_in:
            failures += 1
            report_substitutions(sheet)
            report_origins(sheet)
            report_untraced(sheet, html)
            report_dials(html)
            report_placeholders(sheet, html)
            report_paper(html)
            if loose_in:
                print("     ! unspent: %s"
                      % ", ".join(sorted(sheet.tag[k] + " " + k
                                         for k in loose_in)))
    # The one price branch no table on disk reaches, drawn on a
    # counterfactual table and held to the same checks; see `branch_test`.
    sys.settrace(tracer)
    try:
        branch_bad = branch_test(W.run_winner(W.CATALOG, None),
                                 "branch test")
    finally:
        sys.settrace(None)
    failures += 1 if branch_bad else 0
    # Which of this module's lines no page ran, by function.
    import ast
    import io
    source = io.open(this, encoding="utf-8").read()
    owner = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for n in range(node.lineno, (node.end_lineno or node.lineno) + 1):
                owner[n] = node.name
    lines = source.split("\n")
    # A `raise` runs only when something is wrong, so a clean sweep cannot
    # reach one; those lines are failure paths wherever they sit.
    raises = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Raise):
            raises.update(range(node.lineno,
                                (node.end_lineno or node.lineno) + 1))
    skip = {"main", "sweep", "self_test", "sheet_lines", "print_variant",
            "tracer", "<module>"}
    missed = {}
    for line in sorted(sheet_lines() - hit):
        fn = owner.get(line, "<module>")
        if fn not in skip:
            missed.setdefault(fn, []).append(line)
    # A check's lines that print a finding run only when a page is WRONG,
    # so a clean sweep cannot reach them; `--self-test` and the planted-
    # defect proofs exercise those.  They are listed apart, so a branch of
    # the PAGE that never rendered cannot hide among them.
    checks = {"report_substitutions", "report_origins", "report_untraced",
              "report_dials", "ledger_on_page", "dial_self_test",
              "report_placeholders", "placeholders", "page_tables",
              "placeholder_self_test", "report_paper", "paper_layout",
              "paper_self_test", "_pdf_title", "paper_px",
              # `--every-winner` drives `--check` in child processes; it is
              # a runner, not a page, and a sweep never calls it.
              "every_winner", "every_winner_sources", "one",
              "Parser", "handle_starttag", "handle_endtag", "handle_data",
              "__init__",
              "report_monochrome", "colour_glyphs", "report_furniture",
              "check_substitutions",
              "untraced", "is_traced", "as_number", "evaluable", "monochrome",
              "print_furniture", "footer", "branch_test", "patched",
              "cited", "_claim", "report_backing", "backing_self_test",
              "step", "build_sheet", "return_leg_steps"}
    for title, group in (
            ("PAGE COVERAGE: lines of the page no swept page rendered",
             {fn: got for fn, got in
              ((fn, [n for n in got if n not in raises])
               for fn, got in missed.items() if fn not in checks) if got}),
            ("CHECK FAILURE PATHS: lines that run only when a check finds "
             "something, or that refuse a page",
             {fn: got for fn, got in
              ((fn, got if fn in checks else [n for n in got if n in raises])
               for fn, got in missed.items()) if got})):
        print("\n  %s" % title)
        for fn, got in sorted(group.items(), key=lambda kv: -len(kv[1])):
            print("    %-24s %3d line(s), first at %d: %s"
                  % (fn, len(got), got[0], lines[got[0] - 1].strip()[:60]))
            print("      lines %s" % ", ".join(str(n) for n in got))
        if not group:
            print("    (none)")
    print("\n  %d built, %d refused, %d failure(s)" % (built, refused,
                                                     failures))
    return 1 if failures else 0


def main(argv=None):
    """Pick the mission, derive it, and write the worksheet."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalog", default=None,
                    help="a Stage 4 output to document (.csv or .csv.gz)")
    ap.add_argument("--cell", default=None,
                    help="an archived campaign cell, by ledger name")
    ap.add_argument("--designation", default=None,
                    help="a named body instead of the cell's best case")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "verification_sheet"),
        help="output path, without an extension")
    ap.add_argument("--pdf", action="store_true",
                    help="also render the HTML with headless Chrome")
    ap.add_argument("--font", type=float, default=DEFAULT_PT, metavar="PT",
                    help="print size of the tables, which is what sets the "
                         "page count; a PDF run prints the count it got "
                         "(default: %(default)s)")
    ap.add_argument("--paper", choices=sorted(PAPER_MM),
                    default=DEFAULT_PAPER,
                    help="the paper the page is laid out and measured for "
                         "(default: %(default)s)")
    ap.add_argument("--print-test", action="store_true",
                    help="also write <out>.print.html, the same page with "
                         "the print rules always on, for measuring what "
                         "actually reaches the paper")
    ap.add_argument("--check", action="store_true",
                    help="run every check on the page and write nothing")
    ap.add_argument("--self-test", action="store_true",
                    help="prove each check can fail, by planting a defect "
                         "it exists to find")
    ap.add_argument("--every-winner", action="store_true",
                    dest="every_winner",
                    help="--check the winner of every Stage 4 output on disk "
                         "(the live catalog, every archived cell, and any "
                         "--source), each in its own process")
    ap.add_argument("--sweep", action="store_true",
                    help="build and check a worksheet for one mission per "
                         "architecture on disk; writes nothing")
    ap.add_argument("--max-sources", type=int, default=4, metavar="N",
                    dest="max_sources",
                    help="Stage 4 outputs a sweep scans (default: 4)")
    ap.add_argument("--max-shapes", type=int, default=10, metavar="N",
                    dest="max_shapes",
                    help="worksheets a sweep builds (default: 10)")
    ap.add_argument("--source", action="append", metavar="CSV",
                    help="another Stage 4 output for --sweep or "
                         "--every-winner to take first; repeatable")
    ap.add_argument("--workers", type=int, default=3, metavar="N",
                    help="processes --every-winner runs at once (default: "
                         "3; each holds a catalog in memory)")
    ap.add_argument("--also", action="append", metavar="CSV|DESIGNATION[|F]",
                    help="a named mission for --sweep to build as well, with "
                         "an optional depletion cap for that row alone; "
                         "repeatable")
    ap.add_argument("--max-mining-fraction", type=float, default=None,
                    metavar="F", dest="max_mining_fraction",
                    help="the depletion cap the RUN used, when it is not the "
                         "live default (archived 2026-09 cells used 0.05)")
    args = ap.parse_args(argv)

    if args.max_mining_fraction is not None:
        import master
        master.CALC_CONFIG.max_mining_fraction = args.max_mining_fraction
    if args.sweep:
        return sweep(args)
    if args.every_winner:
        return every_winner(args)

    told = None
    if args.cell:
        winner = W.archived_winner(args.cell, args.designation
                                   or next(r["winner"] for r in W.ledger_rows()
                                           if r["cell"] == args.cell))
        label = args.cell
        led = next((r for r in W.ledger_rows() if r["cell"] == args.cell), None)
        if led and led.get("ore"):
            told = led["ore"].strip().lower().startswith("benef")
    else:
        path = args.catalog or W.CATALOG
        winner = W.run_winner(path, args.designation or None)
        label = os.path.basename(path)
    out = W.build(winner, label, run_beneficiated=told)
    c = out["check"]
    print("  source    %s" % label)
    print("  best case %s at %.4fx  (calc %s)"
          % (out["designation"], out["P"]["obj"], out["terms"]["stamp"]))
    print("  derived   %d quantities: %d bit-exact, %d within %g, %d DIFFER"
          % (c["n"], c["exact"], c["close"], c["tol"], len(c["bad"])))
    if c["bad"]:
        for name, ours, theirs, rel in c["bad"]:
            print("     ! %-30s derived %r  row %r  rel %.3e"
                  % (name, ours, theirs, rel))
        print("\n*** THE DERIVATION AND THE MODEL DISAGREE ***")
        return 1
    sheet = build_sheet(out)
    html = document(out, sheet, args.font, args.paper)
    bad = (report_substitutions(sheet) + report_origins(sheet)
           + report_untraced(sheet, html) + report_dials(html)
           + report_placeholders(sheet, html)
           + report_backing(sheet, html)
           + report_monochrome(html)
           + report_furniture(stylesheet(args.font, args.paper), html))
    # The paper needs a browser, so it is measured on the runs that print.
    if args.pdf or args.print_test or args.self_test:
        bad += report_paper(html, args.paper)
    if args.self_test and (self_test(sheet) + dial_self_test(html)
                           + placeholder_self_test(sheet, html)
                           + backing_self_test(sheet, html)
                           + paper_self_test(html, args.paper)
                           + branch_test(winner, label)):
        return 1
    if bad:
        print("")
        print("*** THE PAGE DOES NOT HOLD UP: see the lines marked ! ***")
        return 1
    if args.check:
        print("  OK  every substitution reproduces the value beside it, "
              "every input names where it came from, every number on the "
              "page comes from one of them, every dial is tabulated, no "
              "answer is stated without its working, and it prints in black")
        return 0
    html = typeset(html)
    html_path = args.out + ".html"
    with open(html_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("  wrote     %s  (%d chars)" % (html_path, len(html)))
    if args.print_test:
        test_path = args.out + ".print.html"
        with open(test_path, "w", encoding="utf-8",
                  newline=chr(10)) as fh:
            fh.write(print_variant(html))
        print("  wrote     %s  (open at %d x %d px to measure the page)"
              % ((test_path,) + paper_px(args.paper)))
    if args.pdf and W.render_pdf(html_path, args.out + ".pdf"):
        print("  wrote     %s  (%d pages, %s)"
              % (args.out + ".pdf", W.pdf_pages(args.out + ".pdf"),
                 args.paper))
    return 0


def every_winner_sources(extra=None):
    """Every Stage 4 output on disk: named ones, the live catalog, the cells.

    Found rather than listed, so an archive added tomorrow is checked with no
    edit: the campaign's cells, every release-suffixed re-measurement beside
    them, and every archived campaign under `cells/archive-*`.
    """
    import glob
    found = list(extra or [])
    if os.path.exists(W.CATALOG):
        found.append(W.CATALOG)
    cells = os.path.join(ROOT, "campaign", "cells")
    found += sorted(glob.glob(os.path.join(cells, "*.csv.gz")))
    found += sorted(glob.glob(os.path.join(cells, "archive-*", "*.csv.gz")))
    for path in found:
        if not os.path.exists(path):
            sys.exit("no Stage 4 output at %s" % path)
    return found


def every_winner(args):
    """`--check` the best case of every Stage 4 output on disk.

    🚨  THIS WAS A SCRIPT IN A SCRATCH DIRECTORY, RUN BY HAND AND THROWN
    AWAY, and it is the check that found what no other could: three dials the
    derivation still read from this process, a fast path the model takes that
    the derivation did not, and a Stage 2 epoch rule that was right for Stage
    3 and wrong here.  None is an architecture, so `--sweep` cannot ask for
    them; only the winners of every run ever made reach them.  A check that
    finds defects every time it is run and is then discarded is the habit
    `verify.py`'s header is a list of the cost of.

    Each source runs in its own process, because a derivation adopts the
    row's configuration and a shared process would carry one run's dials
    into the next.  Exit 1 if any source is not clean.
    """
    import subprocess
    from concurrent.futures import ThreadPoolExecutor
    keys = ("best case", "derived", "arithmetic", "origins", "traced",
            "dials", "static", "OK  every", "!", "***", "Traceback",
            "Error")
    extra = (["--max-mining-fraction", str(args.max_mining_fraction)]
             if args.max_mining_fraction is not None else [])

    def one(path):
        """One source's --check, in its own process: (path, exit, lines)."""
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--check",
             "--catalog", path] + extra,
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        lines = [l.strip() for l in (proc.stdout + proc.stderr).splitlines()
                 if any(k in l for k in keys)]
        return path, proc.returncode, lines

    sources = every_winner_sources(args.source)
    print("  every winner: %d Stage 4 output(s) on disk\n" % len(sources))
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(one, sources))
    bad = 0
    for path, code, lines in results:
        print("  %s  exit %d" % (repo_path(path), code))
        for line in lines:
            print("      " + line[:200])
        bad += code != 0
    print("\n  %d source(s), %d not clean" % (len(results), bad))
    return 1 if bad else 0


def self_test(sheet):
    """Move one printed value and confirm the check goes red on it.

    A MATCHER THAT ACCEPTS EVERYTHING PRINTS THE SAME CLEAN LINE AS ONE THAT
    WORKS, and this repo has the entry to prove it: the completeness audit
    next door matched 99 of 100 columns after every one had been moved by
    31%.  So the check is measured rather than trusted, by feeding it an
    answer that is wrong on purpose.  Returns 1 if it failed to notice.
    """
    for part in sheet.parts:
        for n, row in enumerate(part["rows"]):
            if row[0] != "step" or evaluable(row[5]) is None:
                continue
            planted = list(row)
            planted[6] = float(row[6]) * 1.317 + 1.0
            part["rows"][n] = tuple(planted)
            _c, _u, bad = check_substitutions(sheet)
            part["rows"][n] = row
            if any(b[0] == row[1] for b in bad):
                print("  self-test  perturbing %s is caught: the check can "
                      "fail" % row[1])
                return 0
            print("  self-test  *** PERTURBING %s WENT UNNOTICED ***"
                  % row[1])
            return 1
    print("  self-test  *** NOTHING TO PERTURB ***")
    return 1


def branch_test(winner, label, quiet=False):
    """Render the one price branch no table on disk reaches, and check it.

    🚨  A PHASE SHIPPED HOME IS A BRANCH THE DATA NEVER TAKES.  Stage 2 routes
    a commodity home only when its terrestrial quote less the downleg (about
    $25,000/kg) beats what it is worth at the destination, which is true of
    the elements and of no phase a body in the catalog carries.  So the
    renderer's `max(0, p - c_down)` step had never been drawn by any sweep,
    and a branch never drawn is the unreachable-branch lesson waiting.

    So it is drawn on a COUNTERFACTUAL table, and the test says so: the
    page's cheapest phase that is used at the destination is routed home in
    the Stage 2 table held in memory, priced the way Stage 2 prices such a
    row, and the whole derivation re-run on `winner`.  Disagreeing with the
    row is expected, since the row's run never priced it that way.  What must
    hold is the PAGE: every substitution reproduces its value, every input
    names its source, every number traces, and the shipped-home step is
    actually on it.  Returns the number of findings.
    """
    real = W.reference_tables
    chosen = {}

    def patched(dest, archived=None):
        """The real tables, with one phase routed home."""
        tables = real(dest, archived)
        minerals = tables["minerals"].copy()
        if "value_route" not in minerals.columns:
            return tables
        names = set(chosen.get("phases", ()))
        pick = minerals[minerals["name"].isin(names)
                        & (minerals["value_route"] == "used in space")]
        if pick.empty:
            return tables
        if "yields_json" in pick.columns:
            bare = pick[pick["yields_json"].isna()
                        | (pick["yields_json"].astype(str).str.strip()
                           .isin(["", "{}", "nan"]))]
            pick = bare if not bare.empty else pick
        i = pick["price_usd_per_kg"].astype(float).idxmin()
        net = max(0.0, float(minerals.at[i, "terrestrial_price_usd_per_kg"])
                  - float(minerals.at[i, "downleg_cost_usd_per_kg"]))
        minerals.at[i, "value_route"] = "shipped to Earth"
        minerals.at[i, "price_usd_per_kg"] = net
        if "price_before_processing_usd_per_kg" in minerals.columns:
            minerals.at[i, "price_before_processing_usd_per_kg"] = net
        chosen["name"] = str(minerals.at[i, "name"])
        return dict(tables, minerals=minerals)

    base = W.build(winner, label)
    chosen["phases"] = [n for n, _f, _p in base["C"]["phases"]]
    W.reference_tables = patched
    try:
        out = W.build(winner, label + " (one phase shipped home)")
    finally:
        W.reference_tables = real
    if "name" not in chosen:
        print("  branch     *** NO PHASE TO ROUTE HOME ON THIS PAGE ***")
        return 1
    sheet = build_sheet(out)
    html = document(out, sheet, DEFAULT_PT)
    bad = (report_substitutions(sheet, quiet=True)
           + report_origins(sheet, quiet=True)
           + report_untraced(sheet, html, quiet=True))
    short = chosen["name"].replace(" ", "_").replace("-", "_")
    drawn = "dl_%s" % short in sheet.tag
    if not quiet:
        print("  branch     %s shipped home on a counterfactual table: the "
              "step is %s, and the page has %d finding(s)"
              % (chosen["name"], "drawn" if drawn else "*** NOT DRAWN ***",
                 bad))
    return bad + (0 if drawn else 1)


if __name__ == "__main__":
    sys.exit(main())
