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
        self.n_input = 0
        self.n_step = 0

    def part(self, title, blurb=""):
        """Open a new part of the worksheet."""
        self.parts.append({"title": title, "blurb": blurb, "rows": []})

    def prose(self, text):
        """A line of explanation between steps, spanning the table."""
        self.parts[-1]["rows"].append(("prose", text))

    def block(self, html):
        """Raw HTML between steps: a table the step form cannot carry."""
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
def trim(text, limit=320):
    """One field of free text, HTML-safe and cut to a readable length."""
    if text is None:
        return ""
    text = " ".join(str(text).split())
    if text in ("", "nan", "None"):
        return ""
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + " ..."
    return D.esc(text)


def spacecost_pin():
    """The spacecost tag this repo installs Stage 3's tables from.

    Read out of `requirements.txt` rather than typed, because the pin is in
    four places already and CLAUDE.md records what a fifth copy costs.
    """
    path = os.path.join(ROOT, "requirements.txt")
    if not os.path.exists(path):
        return ""
    for line in open(path, encoding="utf-8"):
        if "spacecost" in line and "@" in line:
            return line.strip().rsplit("@", 1)[-1].split("#")[0].strip()
    return ""


def stamp(row):
    """`catalog_date` and `pipeline_version` off any reference row."""
    bits = []
    for field, label in (("catalog_date", "built"),
                         ("pipeline_version", "stage v")):
        value = row.get(field) if hasattr(row, "get") else None
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        bits.append("%s %s" % (label, D.esc(value)))
    return ", ".join(bits)


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
        return "operational_costs.csv (no row named %s)" % D.esc(category)
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
    return ".  ".join(bits)


def cite_table_row(row, table, name, fields=()):
    """Cite one row of a Module 3 table by name, with its notes and status."""
    bits = ["<b>%s</b>, row <i>%s</i>" % (D.esc(table), D.esc(name))]
    for field in fields:
        # `raw` ON PURPOSE, AND THIS IS THE ONE PLACE IT IS RIGHT.  Reading
        # `notes` to print a citation is asking what the table says, not
        # spending the figure, and logging it would put a rate on the rate
        # audit's list that no line on the page pays.  `Recorded.raw`'s own
        # docstring is the rule this follows.
        value = (row.raw(field) if hasattr(row, "raw")
                 else (row.get(field) if hasattr(row, "get") else None))
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        text = trim(value, 90)
        if text:
            bits.append("%s %s" % (field, text))
    note = trim(row.raw("notes") if hasattr(row, "raw") else row.get("notes"))
    if note:
        bits.append("<span class='src'>%s</span>" % note)
    return ".  ".join(bits)


def cite_mineral(C, name, label=None):
    """Cite one commodity row of the Module 2 catalog, price source included.

    Two dates matter and they are different questions: `ref_price_date` is
    when the reference quote was taken and `live_price_date` is when the
    fetcher last answered, and a commodity can carry one, both or neither.
    """
    minerals = C["minerals"]
    hit = minerals[minerals["name"] == name]
    if not len(hit):
        return "mineral_value_catalog.csv (no row named %s)" % D.esc(name)
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
    return ".  ".join(bits)


def cite_body(C, column, what=""):
    """Cite one column of this body's Stage 1 catalog row.

    Stage 1 writes a provenance column beside most of what it derives, and
    those are the difference between a measurement and an inference: a
    diameter out of a thermal fit and one out of an assumed albedo are the
    same column and not the same claim.
    """
    body = C["body"]
    bits = ["<b>asteroid_catalog.csv</b>, row <i>%s</i>, column <i>%s</i>"
            % (D.esc(body.get("designation")), D.esc(column))]
    if what:
        bits.append(what)
    for field, label in (("diameter_source", "diameter provenance"),
                         ("spectral_type_source", "taxonomy provenance"),
                         ("albedo_assumed_for_diameter", "albedo assumed"),
                         ("density_measured", "density measured"),
                         ("comp_group", "composition group")):
        value = body.get(field)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        bits.append("%s: %s" % (label, D.esc(value)))
    where = stamp(body)
    if where:
        bits.append(where)
    return ".  ".join(bits)


_FIELD_DOCS = {}


def cite_config(field, module="calc"):
    """Cite one config dial, with the comment `ui_meta` scrapes as its help.

    ONE DEFINITION WITH TWO READERS.  The dashboard already renders a field's
    comment block as its help text, and a dial's reasoning is exactly the
    citation a worksheet owes for it, so the same scrape answers both rather
    than this file carrying a second description of the same 105 fields.
    """
    if not _FIELD_DOCS:
        import ui_meta
        for key, source in ui_meta.CONFIG_SOURCES.items():
            path, cls = source[0], source[1]
            try:
                _FIELD_DOCS[key] = ui_meta.scrape_field_docs(
                    os.path.join(ROOT, path), cls)
            except Exception:
                _FIELD_DOCS[key] = {}
    doc = _FIELD_DOCS.get(module, {}).get(field) or {}
    text = trim(doc.get("help") or doc.get("label") or "")
    where = "<b>%s</b> config, field <i>%s</i>" % (D.esc(module), D.esc(field))
    if text:
        return "%s.  <span class='src'>%s</span>" % (where, text)
    return where + ".  A dial: chosen here rather than measured."


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
    for name in candidates:
        if name in read:
            return name
    return candidates[0]


def cite_here(what):
    """Cite a constant this derivation fixes in its own source."""
    return "<b>campaign/worked_calculation.py</b>.  %s" % D.esc(what)


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
        key = ("P_alloy" if base == "nickel-iron"
               else "P_" + base.replace(" ", "_").replace("-", "_"))
        if key in S.tag and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


# ------------------------------------------------------------ 1. the body
def part_body(S, out):
    """Diameter, volume and mass, and the bound the body puts on one mission."""
    C, B = out["C"], out["B"]
    S.part("1. The body",
           "Everything downstream is sized against this rock.  Two of the "
           "three numbers behind its mass are assumptions rather than "
           "measurements, and the citations below say which.")
    k = S.put("k_D", "k_D", "H-to-diameter constant", 1329.0, "km",
              "<b>modules/catalog.py</b>, <i>_H_DIAMETER_CONSTANT</i>.  "
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
    rho = S.put("rho", "rho", "bulk density", C["rho"], "g/cm3",
                cite_body(C, "density_gcm3",
                          "measured" if bool(C["body"].get("density_measured"))
                          else "NOT measured: the taxonomy estimate"))
    phi = S.put("phi", "phi_min", "mineable fraction of the body",
                C["cfg"].max_mining_fraction, "-",
                cite_config("max_mining_fraction"))

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
           "one of the four caps on the payload; see part 5")
    S.prose("D scales as p_V to the power -1/2 and m as D cubed, so m scales "
            "as p_V to the power -3/2: a factor-two albedo error moves the "
            "mass by 2 ** 1.5 = 2.828.  Neither assumption reaches the "
            "answer on this body, because the mineable bound does not bind.")


# -------------------------------------------- 2. what a kilogram is worth
def part_prices(S, out):
    """The launch cost avoided, the per-commodity price, and the phase table."""
    C = out["C"]
    S.part("2. What a kilogram is worth at the destination",
           "No price here is a terrestrial quote.  At an in-space "
           "destination a kilogram is worth what it fetches on Earth PLUS "
           "the launch cost it saves, less what refining it on site costs.")
    c_leo = S.put("c_LEO", "c_LEO", "reusable launch price to LEO",
                  C["leo_usd_per_kg"], "$/kg",
                  "<b>modules/mineral_value.py</b>, <i>_LEO_USD_PER_KG</i>.  "
                  "<span class='src'>Falcon 9 reusable $/kg to LEO, from "
                  "Module 3's launch-vehicle table ($74M / 17.4 t).  It is "
                  "the cheapest operational figure in that table, so every "
                  "in-space price derived from it is a LOWER bound on the "
                  "launch cost avoided.</span>")
    chain = C["chain"]
    prior = 1.0
    keys = ["c_LEO"]
    for n, leg in enumerate(chain["steps"], 1):
        if leg["kind"] != "burn":
            S.step("leg%d" % n, "leg %d" % n, "surviving-mass fraction",
                   "1 / f_survive", "1 / %s" % P(leg.get("frac", 1.0)),
                   leg["after"] / max(leg["before"], 1e-30), "kg/kg", keys[-1:])
            prior = leg["after"]
            keys.append("leg%d" % n)
            continue
        dv, isp, dry = leg["dv"], leg["isp"], leg["dry"]
        S.put("dv%d" % n, "dv_%d" % n, "leg %d delta-v" % n, dv, "m/s",
              "<b>modules/mineral_value.py</b>, <i>_DELIVERY_LEGS</i> for "
              "%s.  <span class='src'>The chain is walked backwards from the "
              "payload, stage by stage: collapsing it into one burn throws "
              "away staging and overstates the destination.</span>"
              % D.esc(C["destination"]))
        S.put("isp%d" % n, "I_sp,%d" % n, "leg %d stage Isp" % n, isp, "s",
              "<b>modules/mineral_value.py</b>, <i>_DELIVERY_LEGS</i>.  "
              "The upper stage this leg is flown on.")
        S.put("dry%d" % n, "delta_%d" % n, "leg %d dry-mass fraction" % n,
              dry, "-", "<b>modules/mineral_value.py</b>, "
                        "<i>_DELIVERY_LEGS</i>.  Stage dry mass as a "
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
        prior = leg["after"]
        keys.append("m0_%d" % n)
    S.step("m_LEO", "m_LEO", "kilograms in LEO per kilogram delivered",
           "product of every leg",
           " * ".join(P(s["m0"]) for s in chain["steps"] if s["kind"] == "burn")
           or "1 (no chain: the destination is the launch site)",
           chain["kg_in_leo"], "kg/kg", keys[1:] or ["c_LEO"])
    p_l = S.step("P_L", "P_L", "launch cost a mined kilogram avoids",
                 "c_LEO * m_LEO",
                 "%s * %s" % (P(c_leo), P(chain["kg_in_leo"])),
                 C["p_l"], "$/kg", ["c_LEO", "m_LEO"],
                 "held to Module 2's own delivered_cost_usd_per_kg")

    S.prose("A commodity USED at the destination is worth its terrestrial "
            "quote plus its utility share of that saving, less on-site "
            "refining.  One SHIPPED HOME is worth its terrestrial quote less "
            "the downleg, floored at zero.  Which of the two happened is a "
            "Module 2 column, not a judgement made here.")

    parts, seen = C["price_parts"], []
    for name, frac, price in C["phases"]:
        base = "silicates" if name.startswith("other") else name
        pp = parts.get(base)
        if pp is None or base in seen:
            continue
        seen.append(base)
        short = base.replace(" ", "_").replace("-", "_")
        if base == "nickel-iron":
            continue
        S.put("u_%s" % short, "u_%s" % base, "%s in-space utility" % base,
              pp["utility"], "-",
              "<b>mineral_value_catalog.csv</b>, row <i>%s</i>, column "
              "<i>in_space_utility</i>, written by "
              "<b>modules/mineral_value.py</b>'s "
              "<i>IN_SPACE_UTILITY_BY_DESTINATION</i> for %s.  "
              "<span class='src'>How much of the launch cost avoided this "
              "commodity captures.  The utility factors are engineering "
              "judgements rather than measurements and are the softest "
              "assumption in the pipeline; CITATIONS.md says outright that "
              "there is nothing to cite, because they are a dial.  Every "
              "per-destination override runs DOWNWARD, against what the "
              "destination can dig up for itself.</span>"
              % (D.esc(base), D.esc(C["destination"])))
        S.put("t_%s" % short, "p_%s" % base, "%s terrestrial quote" % base,
              pp["terrestrial"], "$/kg", cite_mineral(C, base))
        S.put("c_%s" % short, "c_ref,%s" % base, "%s on-site refining" % base,
              pp["refining"], "$/kg", cite_mineral(C, base))
        if pp["route"] == "used in space":
            S.step("P_%s" % short, "P_%s" % base, "%s delivered price" % base,
                   "p + u * P_L - c_ref",
                   "%s + %s * %s - %s"
                   % (P(pp["terrestrial"]), P(pp["utility"]), P(C["p_l"]),
                      P(pp["refining"])),
                   pp["delivered"], "$/kg",
                   ["t_%s" % short, "u_%s" % short, "P_L", "c_%s" % short])
        else:
            S.put("dl_%s" % short, "c_down", "downleg from the depot",
                  pp["downleg"], "$/kg", cite_mineral(C, base))
            S.step("P_%s" % short, "P_%s" % base, "%s delivered price" % base,
                   "max(0, p - c_down)",
                   "max(0, %s - %s)"
                   % (P(pp["terrestrial"]), P(pp["downleg"])),
                   pp["delivered"], "$/kg",
                   ["t_%s" % short, "dl_%s" % short])

    if C["yields"]:
        S.prose("Nickel-iron is the one phase whose price is not a row "
                "lookup.  It is an alloy, so it is the yield-weighted sum of "
                "its elements, with this body's platinum-group enrichment "
                "applied to the rare metals.")
        S.put("kappa", "kappa", "platinum-group enrichment", C["kappa"], "x",
              cite_body(C, "comp_pgm_enrichment",
                        "follows the taxonomy class"))
        rows, total = [], 0.0
        for element, fraction in C["yields"].items():
            if element not in C["element_price"]:
                continue
            share = float(fraction)
            rare = element in C["rare_metals"]
            if rare:
                share *= C["kappa"]
            price = float(C["element_price"][element])
            total += share * price
            rows.append([D.esc(element), P(float(fraction) * 1e6, 8),
                         ("x " + P(C["kappa"])) if rare else "-",
                         "$" + P(price, 10), "$" + P(share * price, 10),
                         cite_mineral(C, element)])
        S.block(D.table(["element", "yield (ppm of alloy)", "enrichment",
                         "$/kg delivered", "contribution $/kg", "source"],
                        rows, "wide"))
        S.step("P_alloy", "P_Fe-Ni", "nickel-iron blended price",
               "sum over elements of yield * enrichment * price",
               "the column above, added",
               C["alloy"], "$/kg", ["kappa", "P_L"])

    S.prose("The phase table is what the hold is filled from.  Module 1's "
            "taxonomy fractions never sum to one; the remainder is carried "
            "as undifferentiated rock at the silicate quote rather than "
            "discarded, which is why the table below totals one.")
    rows = []
    for name, frac, price in C["phases"]:
        short = ("nickel_iron" if name == "nickel-iron"
                 else ("silicates" if name.startswith("other")
                       else name.replace(" ", "_").replace("-", "_")))
        column = ("the residual, 1 - sum of the four fractions"
                  if name.startswith("other")
                  else cite_body(C, "comp_%s_fraction"
                                 % {"nickel-iron": "metal",
                                    "water": "ice"}.get(name, name)))
        rows.append([D.esc(name), D.pct(frac, 3), "$" + P(price, 10),
                     "$" + P(frac * price, 10), column])
    S.block(D.table(["phase", "mass fraction", "$/kg", "contribution $/kg",
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
           "amount of processing lifts the delivered value above this")


# ------------------------------------------------------- 0. the constants
def part_constants(S, out):
    """The physical constants every later part spends, registered once."""
    C = out["C"]
    S.part("0. Constants",
           "Fixed quantities, registered here so that no step below "
           "introduces a number without a tag.  A reader checking one line "
           "in isolation can find every operand in it.")
    S.put("g0", "g_0", "standard gravity", W.G0, "m/s2",
          cite_here("G0, the CODATA standard gravity; the same constant "
                    "spacecost exports as G0_M_S2."))
    S.put("mu_E", "mu_E", "Earth gravitational parameter", W.MU_EARTH,
          "km3/s2", cite_here("MU_EARTH."))
    S.put("v_E", "v_E", "Earth mean orbital velocity", W.V_EARTH, "km/s",
          cite_here("V_EARTH.  The canonical unit the transfer is worked "
                    "in: speeds are carried as multiples of it and "
                    "converted once."))
    S.put("r_LEO", "r_LEO", "parking-orbit radius", W.R_LEO, "km",
          cite_here("R_LEO = 6,378.14 km of Earth radius plus a 200 km "
                    "parking orbit."))
    S.put("tau", "tau_fit", "cruise-time fit", W.TAU_CRUISE_FIT_YR_PER_M_S,
          "yr per m/s",
          cite_here("TAU_CRUISE_FIT_YR_PER_M_S.  A linear fit of transfer "
                    "time against delta-v, floored at half a year."))
    if C["destination"] == "cislunar":
        S.put("R_M", "R_M", "lunar orbital radius", W.R_MOON, "km",
              cite_here("R_MOON."))
        S.put("dv_NRHO", "dv_NRHO", "NRHO insertion increment", W.DV_NRHO,
              "km/s",
              cite_here("DV_NRHO.  Capture BINDS the orbit at low perigee "
                        "and takes the Oberth benefit there; this is the "
                        "increment that finishes the job at the depot."))


# ------------------------------------------------- 3. getting there and back
def part_transfer(S, out):
    """The patched conic: departure, apsis match, arrival, floors, penalty."""
    C, DV = out["C"], out["DV"]
    leg = DV["aph"] if DV["apsis"] == "aphelion" else DV["peri"]
    S.part("3. Getting there and back",
           "A patched conic: an ellipse from Earth's orbit out to the apsis "
           "the search chose, a burn to match the target's velocity there, "
           "and a capture at the destination.  Distances are in AU and "
           "speeds in multiples of Earth's own orbital velocity until the "
           "last line of each block.")
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
           "the searched apsis: %s" % D.esc(DV["apsis"]),
           "%s costs %s km/s round trip against %s for the other"
           % (D.esc(DV["apsis"]),
              P(DV["aph_round"] if DV["apsis"] == "aphelion"
                else DV["peri_round"], 8),
              P(DV["peri_round"] if DV["apsis"] == "aphelion"
                else DV["aph_round"], 8)),
           DV["r_target"], "AU", ["Q", "q"])
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
           "%s + 1 - 2 * %s * %s"
           % (P(leg["v_t"] ** 2), P(leg["v_t"]), P(leg["cos_i"])),
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
           "sqrt(2 / %s - 1 / %s)" % (P(DV["r_target"]), P(a)),
           leg["v_ast"], "x v_E", ["r_t", "a"])
    S.step("v_tr", "v_tr", "the spacecraft, at r_t",
           "sqrt(2 / r_t - 1 / a_t)",
           "sqrt(2 / %s - 1 / %s)" % (P(DV["r_target"]), P(leg["a_t"])),
           leg["v_tr"], "x v_E", ["r_t", "a_t"])
    S.step("dv_match", "dv_match", "the match burn",
           "|v_ast - v_tr| * v_E",
           "|%s - %s| * %s" % (P(leg["v_ast"]), P(leg["v_tr"]),
                               P(W.V_EARTH)),
           leg["match"], "km/s", ["v_ast", "v_tr", "v_E"])
    S.step("dv_out_raw", "dv_out,raw", "outbound, before floor and penalty",
           "dv_dep + dv_match",
           "%s + %s" % (P(leg["depart"]), P(leg["match"])),
           DV["raw_out"] / 1000.0, "km/s", ["dv_dep", "dv_match"])

    S.prose("The return, burn by burn.  The outbound half is the same "
            "wherever the cargo is going; what differs is entirely the "
            "arrival.  This mission flies <b>%s</b>."
            % D.esc(C["return_leg"]))
    rows = [[D.esc(what), P(value, 8)]
            for what, value in leg["arrival"][C["return_leg"]]]
    S.block(D.table(["burn", "km/s"], rows))
    if C["return_leg"] == "ret_cislunar_prop":
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
               "(v_hyp - v_ell) + dv_NRHO",
               "(%s - %s) + %s" % (P(leg["v_hyp"]), P(leg["v_ell"]),
                                   P(W.DV_NRHO)),
               leg["cap"], "km/s", ["v_hyp", "v_ell", "dv_NRHO"])
    S.step("dv_ret_raw", "dv_ret,raw", "return, before floor and penalty",
           "the burns above, added",
           " + ".join(P(v) for _w, v in leg["arrival"][C["return_leg"]]),
           DV["raw_ret"] / 1000.0, "km/s",
           ["dv_cap"] if C["return_leg"] == "ret_cislunar_prop"
           else ["dv_match"])

    S.prose("The floors come BEFORE the low-thrust penalty.  A body cheap "
            "enough to arrive at pays the floor times the penalty rather "
            "than its own value times the penalty, and a page that showed "
            "only the product could not say which.")
    lam = S.put("lambda", "lambda_LT", "low-thrust delta-v penalty",
                C["dv_penalty"], "x",
                cite_table_row(C["pro"], "propellants.csv",
                               C["pro"].raw("name"),
                               ("dv_penalty_factor", "thrust_scaling")))
    S.put("floor_out", "floor_out", "outbound delta-v floor", DV["floor_out"],
          "m/s", cite_here("the outbound floor in `derive_dv`, mirroring "
                           "the model's own."))
    S.put("floor_ret", "floor_ret", "return delta-v floor", DV["floor_ret"],
          "m/s", cite_here("the return floor in `derive_dv`."))
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
    S.part("4. The propellant, the tank and the launch budget",
           "Two mass ratios and two tank factors.  Everything in part 6 is "
           "built out of these four numbers and the vehicle's capacity.")
    isp = S.put("isp", "I_sp", "%s specific impulse" % pro_name, C["isp"], "s",
                cite_table_row(C["pro"], "propellants.csv", pro_name,
                               ("type", "status", "trl", "reference_year")))
    S.put("tank_frac", "t", "tank mass per kg of propellant", C["tank_frac"],
          "kg/kg",
          "<b>profitability_catalog</b>, column <i>tank_mass_frac</i> on "
          "this row, which is the run's own value.  Module 3 derives it as "
          "<i>tank_kg_per_L</i> / <i>density_kg_per_L</i> = %s / %s for the "
          "<i>%s</i> storage class.  "
          % (P(C["pro"].raw("tank_kg_per_L")),
             P(C["pro"].raw("density_kg_per_L")), D.esc(C["storage_class"]))
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
        S.step("boil", "b", "boil-off inflation over the hold",
               "exp(rate/100 * hold_yr * 365.25)", "as the model associates it",
               M["boiloff_factor"], "-", ["dv_ret"])
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
    S.part("5. What a watt of plant weighs",
           "Established before the fixed point because none of it depends "
           "on the payload.  Only the draw moves as the loop iterates.")
    if C["power_source"] == "rtg":
        S.put("w_rtg", "w_RTG", "radioisotope specific power",
              C["rtg_w_per_kg"], "W/kg", cite_ops(C, "RTG specific power"))
        S.step("w_plant", "w_plant", "plant specific power",
               "flat: a radioisotope source does not care how far out it is",
               "%s" % P(C["rtg_w_per_kg"]), C["w_plant"], "W/kg", ["w_rtg"])
        return
    w1 = S.put("w_1AU", "w_1AU", "array specific power, rated at 1 AU",
               C["w_1au"], "W/kg", cite_ops(C, "Power system specific mass"))
    S.step("w_bare", "w_bare", "the same array, at this body's distance",
           "w_1AU / a^2", "%s / %s ^ 2" % (P(w1), P(C["a_au"])),
           C["w_bare"], "W/kg", ["w_1AU", "a"],
           "sunlight falls off as the square of the distance")
    if C["oversize"] == 1.0:
        S.step("w_plant", "w_plant", "plant specific power",
               "w_bare: the night-side term is off on this run",
               "%s" % P(C["w_bare"]), C["w_plant"], "W/kg", ["w_bare"])
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
                    "measured" if C["rot_measured"]
                    else "NOT measured: the catalog median is used")
          + ("  " + cite_config("default_rotation_period_h")
             if not C["rot_measured"] else ""))
    S.put("dark_max", "dark_max", "ceiling on the modelled night",
          C["max_dark_h"], "h", cite_config("max_dark_period_h"))
    S.step("dark_h", "dark_h", "the night, as modelled",
           "min(P_rot / 2, dark_max)",
           "min(%s / 2, %s)" % (P(C["rot_h"]), P(C["max_dark_h"])),
           C["dark_h"], "h", ["rot", "dark_max"],
           "a night is half a rotation, up to a ceiling: a slow rotator "
           "would otherwise buy a battery sized for a week of darkness")
    S.step("oversize", "oversize", "how much bigger the array has to be",
           "((1 - f) + f / eta) / (1 - f)",
           "((1 - %s) + %s / %s) / (1 - %s)" % (P(f), P(f), P(eta), P(f)),
           C["oversize"], "-", ["dark_frac", "eta_store"],
           "the sunlit hours run the load AND recharge the store, and the "
           "recharge is lossy.  Written term for term: cancelling it gives "
           "a different float")
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
    S.step("w_plant", "w_plant", "plant specific power", "1 / (kg/W)",
           "1 / %s" % P(kg_per_w), C["w_plant"], "W/kg", ["kg_per_w"],
           "against a bare %s W/kg: the night side costs a factor of %s"
           % (P(C["w_bare"], 6), P(C["w_bare"] / C["w_plant"], 3)))


# ------------------------------------------------------ 6. the fixed point
def part_fixed_point(S, out):
    """The payload solve, which is circular and is iterated to a fixed point."""
    C, M, B = out["C"], out["M"], out["B"]
    cas, R = M["cascade"], M["R"]
    S.part("6. The mass cascade, and the fixed point it is solved by",
           "Payload is solved for, not specified.  It is bounded by the "
           "rocket equation against the vehicle's capacity, and the solve "
           "is circular: the payload sets the feed, the feed sets the dig "
           "time and the power draw, the draw sets the plant mass, and the "
           "plant comes out of the payload budget.")
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
            "the payload that came out.  The loop is run until they stop "
            "moving.")
    rows = [[str(p["n"]), P(p["hw_in"], 10), P(p["f_used"], 10),
             P(p["m_pay"], 10), P(p["ep"], 8), P(p["plant"], 8),
             P(p["feed"], 8), P(p["dig"], 6)] for p in M["passes"]]
    S.block(D.table(["pass", "hardware in (kg)", "structure frac",
                     "payload out (kg)", "EP stage (kg)", "plant (kg)",
                     "feed (kg)", "dig (yr)"], rows, "wide"))
    S.prose("<b>The cascade is not re-solved once the loop converges.</b>  "
            "The payload carried forward is the last one solved INSIDE the "
            "loop, at the previous pass's hardware, and that is the model's "
            "own behaviour rather than an approximation made here.  It is "
            "also why the launch mass lands a little under the vehicle "
            "instead of exactly on it, which part 9 closes to the kilogram.")

    prev = M["passes"][-2] if len(M["passes"]) > 1 else None
    S.step("hw_solved", "m_hw,solved", "the hardware the last solve ran at",
           "m_rig + plant + EP stage, at the PREVIOUS pass",
           ("%s + %s + %s" % (P(C["cfg"].mining_hardware_kg),
                              P(prev["plant"]), P(prev["ep"]))
            if prev is not None else P(M["passes"][-1]["hw_in"])),
           M["hw_solved"], "kg", ["m_rig"],
           "the last row's 'hardware in' column above, and NOT the "
           "hardware the mission actually flies; part 8 is built on that")
    S.step("f_solved", "f_solved", "the structure fraction it ran at",
           "f_str + c_frac, at the previous pass",
           "%s + %s" % (P(C["cfg"].return_structure_frac_of_payload),
                        P(M["f_solved"]
                          - C["cfg"].return_structure_frac_of_payload)),
           M["f_solved"], "-", ["f_str", "c_seal"])
    S.step("s_tps", "s_TPS", "the heat-shield multiplier on the whole "
           "returned stack", "1 + tps_frac",
           "1 + %s" % P(C["tps_frac"]), cas["s_tps"], "-", ["budget"],
           "exactly 1.0 on a propulsive return, and then not one float of "
           "the cascade differs from the untps case")
    S.step("coef", "coef", "the returning stack's multiplier",
           ("k_ret * s_TPS" if C["isru"] else "k_ret * s_TPS * R_ret"),
           ("%s * %s" % (P(R["k_ret"]), P(cas["s_tps"]))
            if C["isru"] else
            "%s * %s * %s" % (P(R["k_ret"]), P(cas["s_tps"]),
                              P(R["R_ret"]))),
           cas["coef"], "-", ["k_ret", "s_tps"] + ([] if C["isru"]
                                                   else ["R_ret"]),
           "carrying the return propellant up from Earth pushes it through "
           "the outbound burn as dead mass, which is the one factor of "
           "R_ret that separates the two forms")
    S.step("denom", "denom", "the denominator of the closed form",
           "coef (1 + f) - 1",
           "%s * (1 + %s) - 1" % (P(cas["coef"]), P(cas["struct_frac"])),
           cas["denom"], "-", ["coef", "f_solved"])
    S.step("bracket", "bracket", "the numerator of the closed form",
           "budget - m_hw - coef * d_0",
           "%s - %s - %s * %s" % (P(R["budget"]), P(cas["hardware_kg"]),
                                  P(cas["coef"]), P(cas["d0"])),
           cas["bracket"], "kg", ["budget", "hw_solved", "coef", "d0"])
    S.step("m_pay", "m_pay", "returned payload", "bracket / denom",
           "%s / %s" % (P(cas["bracket"]), P(cas["denom"])),
           cas["m_pay"], "kg", ["bracket", "denom"],
           "the model's max_payload_kg")


# ------------------------------------------------- 7. the settled mission
def part_settled(S, out):
    """Feed, water, the seal, the power draw, the plant and the EP stage."""
    C, M, B = out["C"], out["M"], out["B"]
    cas = M["cascade"]
    S.part("7. The feed, the water and the power it takes",
           "Settled on the payload the last solve produced.  These are the "
           "quantities the loop re-sized between passes, and they are what "
           "the hardware and the clock are built from.")
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
          cite_table_row(C["veh"], "launch_vehicles.csv",
                         C["veh"].raw("name"), ("fairing_volume_m3",)))
    S.step("vol_cap", "vol_cap", "what the hold can physically carry",
           "0.25 * V_fair * 1000 * rho",
           "0.25 * %s * 1000 * %s" % (P(C["fairing_m3"]), P(C["rho"])),
           M["vol_cap"], "kg", ["V_fair", "rho"],
           "a quarter of the fairing, at the ore's bulk density")

    if C["beneficiated"]:
        S.put("ratio", "r", "concentration ratio", out["ratio"], "-",
              "Decided by the sweep in part 12, not assumed.  It is an "
              "economic choice: grade saturates while the costs do not.")
        S.step("feed", "feed", "rock dug and processed",
               "max(min(m_pay * r, throughput, mineable), m_pay)",
               "max(min(%s * %s, %s, %s), %s)"
               % (P(cas["m_pay"]), P(out["ratio"]), P(M["throughput"]),
                  P(B["mineable"]), P(cas["m_pay"])),
               M["feed"], "kg", ["m_pay", "ratio", "throughput", "m_min"])
        S.step("ratio_got", "r_achieved", "the ratio the rig actually reaches",
               "feed / m_pay",
               "%s / %s" % (P(M["feed"]), P(cas["m_pay"])),
               M["ratio"], "-", ["feed", "m_pay"],
               "below the %s the sweep chose, because the throughput "
               "ceiling clips the feed before the ratio does"
               % P(out["ratio"], 8))
    else:
        S.step("feed", "feed", "rock dug", "feed = m_pay on run-of-mine ore",
               P(cas["m_pay"]), M["feed"], "kg", ["m_pay"],
               "not concentrating means the feed and the payload are the "
               "same rock")
    S.put("eps_rec", "eps_rec", "separation recovery",
          C["recovery"], "-", cite_config("beneficiation_recovery"))
    S.step("water", "water", "water in the hold",
           ("what the knapsack in part 10 loaded"
            if C["beneficiated"] else "m_pay * f_ice"),
           (P(M["water"]) if C["beneficiated"]
            else "%s * %s" % (P(cas["m_pay"]), P(C["ice_frac"]))),
           M["water"], "kg", ["m_pay", "eps_rec"])
    S.step("c_frac", "c_frac", "containment as a fraction of payload",
           "c_seal * min(1, water / m_pay)",
           "%s * min(1, %s / %s)"
           % (P(C["contain_per_kg"]), P(M["water"]), P(cas["m_pay"])),
           M["c_frac"], "-", ["c_seal", "water", "m_pay"])
    S.step("m_seal", "m_seal", "volatile containment mass", "c_frac * m_pay",
           "%s * %s" % (P(M["c_frac"]), P(cas["m_pay"])),
           M["m_containment"], "kg", ["c_frac", "m_pay"])
    S.step("f_eff", "f", "ore restraint plus the sealed hold",
           "f_str + c_frac",
           "%s + %s" % (P(C["cfg"].return_structure_frac_of_payload),
                        P(M["c_frac"])),
           M["f_eff"], "-", ["f_str", "c_frac"])
    S.put("t_floor", "t_floor", "station-keeping floor on the stay",
          C["cfg"].station_keeping_floor_yr, "yr",
          cite_config("station_keeping_floor_yr"))
    S.step("t_dig", "t_dig", "the dig", "max(feed / rate, t_floor)",
           "max(%s / %s, %s)"
           % (P(M["feed"] + M["isru_feed"]), P(C["rate_kg_yr"]),
              P(C["cfg"].station_keeping_floor_yr)),
           M["dig_yr"], "yr", ["feed", "rate", "t_floor"],
           "the FEED is dug, not the payload; that is what concentrating "
           "costs in time")
    S.step("hrs", "hours", "the dig, in hours", "(t_dig * 365.25) * 24",
           "(%s * 365.25) * 24" % P(M["dig_yr"]),
           W.hours(M["dig_yr"]), "h", ["t_dig"],
           "associated exactly as the model associates it: y * 365.25 * 24 "
           "is not y * 8766, and the difference reaches the last bit")

    hrs = W.hours(M["dig_yr"])
    S.put("e_dig", "e_dig", "excavation energy", C["dig_wh"], "Wh/kg dug",
          cite_ops(C, "Drilling / excavation energy"))
    if C["beneficiated"]:
        S.put("e_ben", "e_ben", "beneficiation energy", C["benef_wh"],
              "Wh/kg of product",
              cite_ops(C, "Beneficiation / on-site processing energy"))
    S.put("e_h2o", "e_H2O", "bound-water liberation energy", C["water_wh"],
          "Wh/kg of water",
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
                                           if C["beneficiated"] else []))
    d2 = 0.0
    if M["liberated"] > 0:
        d2 = C["water_wh"] * M["liberated"] / hrs
        S.step("P_lib", "P_H2O", "bound-water liberation draw",
               "e_H2O * water / hours",
               "%s * %s / %s" % (P(C["water_wh"]), P(M["liberated"]), P(hrs)),
               d2, "W", ["e_h2o", "water", "hrs"])
    S.step("draw", "P", "the continuous processing draw",
           "P_dig + P_H2O",
           "%s + %s" % (P(d1), P(d2)), M["draw"], "W",
           ([k for k in ("P_dig", "P_lib") if k in S.tag] or ["hrs"]))
    S.step("m_plant", "m_plant", "plant mass", "P / w_plant",
           "%s / %s" % (P(M["draw"]), P(C["w_plant"])),
           M["plant"], "kg", ["draw", "w_plant"])

    if not C["electric"]:
        S.step("m_EP", "m_EP", "electric stage", "chemical: there is none",
               "0", 0.0, "kg", ["m_plant"])
    else:
        ep = M["ep"]
        S.prose("The electric stage is sized on the propellant the "
                "converging pass loaded, and on two different quantities: "
                "the array and the power train scale with POWER, the "
                "thruster scales with THRUST, and thrust owes nothing to "
                "efficiency.")
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
        S.step("m_prop_ep", "m_prop", "the load the stage is sized on",
               "outbound + return propellant, at the converging pass",
               "%s + %s" % (P(cas["m_oprop"]), P(cas["m_rprop"])),
               cas["m_prop"], "kg", ["budget", "coef"])
        secs = C["cfg"].ep_target_thrust_yr * 365.25 * 24.0 * 3600.0
        S.step("t_burn_s", "t_burn (s)", "thrust time, in seconds",
               "t_burn * 365.25 * 24 * 3600",
               "%s * 365.25 * 24 * 3600" % P(C["cfg"].ep_target_thrust_yr),
               secs, "s", ["t_burn_yr"])
        S.step("P_ep", "P_EP", "electric power", "m_prop v_e^2 / (2 eta t)",
               "%s * %s / (2 * %s * %s)"
               % (P(cas["m_prop"]), P(C["ve"] ** 2), P(C["thruster_eff"]),
                  P(secs)),
               ep["power"], "W",
               ["m_prop_ep", "ve", "eta_thr", "t_burn_s"])
        S.step("T_ep", "T", "thrust", "m_prop v_e / t",
               "%s * %s / %s" % (P(cas["m_prop"]), P(C["ve"]), P(secs)),
               ep["thrust"], "N", ["m_prop_ep", "ve", "t_burn_s"])
        S.step("ep_array", "array", "the cruise array", "P_EP / w_bare",
               "%s / %s" % (P(ep["power"]), P(C["w_bare"])),
               ep["array"], "kg", ["P_ep", "w_bare"],
               "the BARE figure, not the eclipse-derated one: a cruise "
               "array is in permanent sunlight, and it is the PROCESSING "
               "plant that stands in the body's shadow")
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
    S.step("m_hw", "m_hw", "hardware, as flown",
           "m_rig + m_plant + m_EP",
           "%s + %s + %s" % (P(C["cfg"].mining_hardware_kg), P(M["plant"]),
                             P(M["ep"]["mass"])),
           M["hw"], "kg", ["m_rig", "m_plant", "m_EP"])


# ------------------------------------------------------- 8. the flown stack
def part_stack(S, out):
    """The stack rebuilt on settled hardware, and what closes it."""
    C, M, B = out["C"], out["M"], out["B"]
    R, cas = M["R"], M["cascade"]
    S.part("8. The stack, from the payload outwards",
           "Built on the hardware and the containment fraction that settled "
           "in part 7, which are a little lighter than the ones the closed "
           "form solved at.  That difference is the whole of the launch "
           "margin, and the last two lines close it to the kilogram.")
    S.step("m_dry", "m_dry", "return vehicle dry", "d_0 + f * m_pay",
           "%s + %s * %s" % (P(cas["d0"]), P(M["f_eff"]), P(M["m_pay"])),
           M["m_dry"], "kg", ["d0", "f_eff", "m_pay"])
    S.step("m_tps", "m_TPS", "heat shield",
           "tps_frac * (m_pay + m_dry)",
           "%s * (%s + %s)" % (P(C["tps_frac"]), P(M["m_pay"]),
                               P(M["m_dry"])),
           M["m_tps"], "kg", ["m_pay", "m_dry"],
           "zero on a propulsive return" if C["tps_frac"] == 0 else "")
    S.step("m_after", "m_after", "the returning stack, post-burn",
           "k_ret (1 + tps_frac) (m_pay (1 + f) + d_0)",
           "%s * (1 + %s) * (%s * (1 + %s) + %s)"
           % (P(R["k_ret"]), P(C["tps_frac"]), P(M["m_pay"]), P(M["f_eff"]),
              P(cas["d0"])),
           M["m_after"], "kg", ["k_ret", "m_pay", "f_eff", "d0"])
    S.step("m_rprop", "m_rprop", "return propellant",
           "m_after (R_ret - 1)",
           "%s * (%s - 1)" % (P(M["m_after"]), P(R["R_ret"])),
           M["m_rprop"], "kg", ["m_after", "R_ret"])
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

    S.prose("Why it lands under the vehicle rather than on it, exactly.")
    short = R["budget"] - M["m_at"]
    S.step("short", "budget - m_at", "how far under the budget the flown "
           "stack arrives", "budget - m_at",
           "%s - %s" % (P(R["budget"], 17), P(M["m_at"], 17)), short, "kg",
           ["budget", "m_at"],
           "the only subtraction on the page that CANCELS: five leading "
           "digits go, so both operands are given to full double precision "
           "and a reader working from the rounded values in part 4 and "
           "part 8 will land about three digits short of this")
    S.step("spare", "M_LEO - m_launch", "spare capacity",
           "(budget - m_at) * k_out * R_out",
           "%s * %s * %s" % (P(short), P(R["k_out"]), P(R["R_out"])),
           C["leo_cap"] - M["m_launch"], "kg",
           ["short", "k_out", "R_out"],
           "the same number as M_LEO - m_launch, which is what closes the "
           "cascade against itself")

    S.prose("Four ceilings stand over the payload and only the smallest is "
            "the answer.  Naming which one binds is the difference between "
            "a result about this body and a result about the rig.")
    caps = [("mineable", "%s of the body" % D.pct(C["cfg"].max_mining_fraction),
             B["mineable"]),
            ("throughput", "%s kg/yr over %s yr" % (P(C["rate_kg_yr"], 8),
                                                    P(M["dig_yr"], 4)),
             M["throughput"]),
            ("volume", "a quarter of the fairing at %s kg/L" % P(C["rho"]),
             M["vol_cap"]),
            ("rocket equation", "the closed form in part 6", M["m_pay"])]
    low = min(v for _n, _w, v in caps)
    S.block(D.table(["cap", "what it is", "kg"],
                    [[n, w, P(v, 10) + (" <b>binds</b>" if v == low else "")]
                     for n, w, v in caps]))


# ------------------------------------------------------------ 9. the clock
def part_clock(S, out):
    """Periods, the wait for a window, the two duration clocks, the cadence."""
    C, M, DV = out["C"], out["M"], out["DV"]
    S.part("9. The clock",
           "Extraction is rate-limited, so the dig time flows into the "
           "mission duration, into operations cost and into how often the "
           "campaign can repeat.  The duration is the LONGER of two clocks.")
    S.step("T_ast", "T_ast", "orbital period of the body", "a ^ 1.5",
           "%s ^ 1.5" % P(C["a_au"]), DV["t_ast"], "yr", ["a"],
           "Kepler's third law in AU and years, where the constant is 1")
    S.step("T_dest", "T_dest", "the orbit the destination is phased against",
           "a_dest ^ 1.5", "%s ^ 1.5" % P(DV["a_dest"]), DV["t_dest"], "yr",
           ["a"])
    S.step("synodic", "S_syn", "synodic period",
           "1 / |1 / T_ast - 1 / T_dest|",
           "1 / |1 / %s - 1 / %s|" % (P(DV["t_ast"]), P(DV["t_dest"])),
           DV["synodic"], "yr", ["T_ast", "T_dest"])
    S.step("t_win", "t_win", "expected wait for a departure window",
           "S_syn / 2" if C["windows"] else "0: windows are not modelled",
           ("%s / 2" % P(DV["synodic"])) if C["windows"] else "0",
           DV["window_wait"], "yr", ["synodic"],
           "counterintuitively this punishes near-Earth bodies hardest, "
           "because their periods are near Earth's and the windows are "
           "therefore years apart")
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
               "the delta-v-linear cruise fit is calibrated to CHEMICAL "
               "transfers; an electric stage thrusts for most of the trip, "
               "so its duration is governed by burn time instead")
    S.step("T_miss", "T_miss", "mission duration",
           "max(1, chem, elec)",
           "max(1, %s, %s)" % (P(M["chem_fit"]), P(M["electric_floor"])),
           M["duration"], "yr",
           ["chem_fit"] + (["e_floor"] if M["electric_floor"] > 0 else []),
           "whichever clock is slower is the mission")
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
    S.part("10. The hold",
           "The mission is not sent for a named mineral; it is sent to "
           "bring back the best load it can assemble.  With a fixed mass "
           "budget and divisible, per-kilogram-priced phases that is a "
           "fractional knapsack, and greedy selection by $/kg is provably "
           "optimal: fill the hold with the most valuable phase available, "
           "then the next.")
    if C["beneficiated"]:
        S.prose("Each phase can supply <b>feed * f_c * eps_rec</b> and no "
                "more.  The walk takes the lesser of that supply and the "
                "hold still empty, in descending price order.")
        rows = []
        for n, w in enumerate(M["load"]["walk"], 1):
            rows.append([str(n), D.esc(w["phase"]), "$" + P(w["price"], 10),
                         P(w["supply"], 10), P(w["hold"], 10),
                         P(w["take"], 10),
                         "hold full" if w["take"] <= 0
                         else ("hold ran out" if w["take"] < w["supply"]
                               else "all the feed had")])
        S.block(D.table(["#", "phase", "$/kg", "supply (kg)",
                         "hold left (kg)", "taken (kg)", "what stopped it"],
                        rows, "wide"))
    else:
        S.prose("Run-of-mine ore is not sorted: the hold carries the body's "
                "own blend, phase by phase in its own proportions.")
        rows = [[D.esc(k), P(v, 10)] for k, v in M["load"]["mix"].items()]
        S.block(D.table(["phase", "kg"], rows))
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
           "against %s for the body's own blend, a factor of %s"
           % (P(C["bulk"], 8), P(M["load"]["usd_per_kg"] / C["bulk"], 4)))
    S.step("ret_vol", "V_ret", "volume the cargo occupies",
           "m_pay / rho / 1000",
           "%s / %s / 1000" % (P(M["m_pay"]), P(C["rho"])),
           M["ret_vol"], "m3", ["m_pay", "rho"])


# ---------------------------------------------------------- 11. the market
def part_market(S, out):
    """The accumulation window, the ceilings, and the sale tier by tier."""
    C, M, P_ = out["C"], out["M"], out["P"]
    rev = P_["rev"]
    n, f, w = P_["n"], P_["f"], P_["w"]
    S.part("11. The market",
           "Prices are constant at any volume; what bounds a programme is "
           "how much the destination can absorb while it waits.  A bigger "
           "fleet delivers more often, so each delivery gets a shorter "
           "slice of the market's annual capacity.")
    S.put("N", "N", "programme size", n, "missions",
          "Decided by the ladder in part 12, not assumed.")
    S.put("F", "F", "fleet", f, "ships", "Decided by the ladder in part 12.")
    S.put("Wc", "W", "campaigns per ship", w, "-",
          "Decided by the ladder in part 12, bounded by trips.")
    S.step("window", "omega", "how long one delivery's market accumulates",
           "(T_miss + (N - 1) * T_cad / F) / N",
           "(%s + (%s - 1) * %s / %s) / %s"
           % (P(M["duration"]), P(n), P(M["cadence"]), P(f), P(n)),
           rev["window"], "yr", ["T_miss", "N", "T_cad", "F"])
    rows = []
    for market, allow in sorted(rev["allow"].items()):
        cap = C["market_kg"].get(market)
        rows.append([D.esc(market), P(cap, 10),
                     "%s * %s" % (P(cap, 10), P(rev["window"])),
                     P(allow, 10), cite_mineral(C, market)])
    S.block(D.table(["market", "ceiling (kg/yr)", "x omega", "allowance (kg)",
                     "source of the ceiling"], rows, "wide"))
    S.prose("A concentrated load is RESHAPED rather than clipped: the "
            "ceilings go into the knapsack, so space a capped phase does "
            "not get stays available to the next phase down the price "
            "order.  That is why a bounded hold can still fly full.")
    rows = []
    for i, step in enumerate(rev["capped"]["walk"], 1):
        rows.append([str(i), D.esc(step["phase"]),
                     "full" if step["full"] else "surplus",
                     "$" + P(step["price"], 10), P(step["supply"], 10),
                     "-" if step["allowance"] is None
                     else P(step["allowance"], 10),
                     P(step["take"], 10),
                     "$" + P(step["take"] * step["price"], 10)])
    S.block(D.table(["#", "phase", "tier", "$/kg", "supply (kg)",
                     "allowance (kg)", "sold (kg)", "value"], rows, "wide"))
    S.step("Rev", "Rev", "what one delivery sells",
           "sum over tiers of sold * price",
           " + ".join("%s * %s" % (P(t["take"]), P(t["price"]))
                      for t in rev["capped"]["walk"] if t["take"] > 0),
           rev["capped"]["value"], "$", ["window", "hold_value"])
    S.step("clearing", "clearing", "fraction of the unbounded hold that sold",
           "Rev / V_hold",
           "%s / %s" % (P(rev["capped"]["value"]), P(rev["gross_base"])),
           rev["clearing"], "-", ["Rev", "hold_value"])
    S.step("delivered", "V_del", "delivered value per kilogram flown",
           "Rev / m_pay",
           "%s / %s" % (P(rev["capped"]["value"]), P(M["m_pay"])),
           rev["delivered"], "$/kg", ["Rev", "m_pay"])


# --------------------------------------------------------- 12. the searches
def part_searches(S, out):
    """The two searches that chose the concentration ratio and the programme."""
    C, M, L = out["C"], out["M"], out["ladder"]
    sweep = out["sweep"]
    S.part("12. The two searches",
           "Neither the concentration ratio nor the programme size is a "
           "setting.  Both are chosen by pricing the alternatives, and both "
           "ladders are printed here so a reader can check that the winner "
           "is the argmin of the column beside it.")
    if C["beneficiated"]:
        best_name, best_frac, _best_price = max(C["phases"],
                                                key=lambda ph: ph[2])
        S.step("r_max", "r_max", "saturation ratio",
               "1 / (f_best * eps_rec), f_best being the fraction of the "
               "best-PRICED phase (%s) and not of the commonest" % best_name,
               "1 / (%s * %s)" % (P(best_frac), P(C["recovery"])),
               sweep["r_max"], "-", ["eps_rec"],
               "above this the hold is pure best-phase and grade stops "
               "improving, while the costs do not")
        S.step("r_step", "step", "the coarse ladder's geometric step",
               "r_max ^ (1 / (steps - 1))",
               "%s ^ (1 / %s)"
               % (P(sweep["r_max"]), P(C["cfg"].concentration_search_steps - 1)),
               sweep["step"], "-", ["r_max"])
        rows = []
        for kind, ratio, won in sweep["rungs"]:
            mark = " <b>argmin</b>" if (kind, ratio) == (
                sweep["winner"][0], sweep["winner"][1]) else ""
            rows.append([kind, P(ratio, 8), P(won["M"]["m_pay"], 8),
                         P(won["M"]["feed"], 8),
                         "$" + P(won["ladder"]["best"]["rev"]["delivered"], 8),
                         "(%d, %d)" % (won["ladder"]["best"]["f"],
                                       won["ladder"]["best"]["w"]),
                         P(won["ladder"]["best"]["obj"], 8) + mark])
        S.block(D.table(["rung", "ratio", "payload (kg)", "feed (kg)",
                         "delivered $/kg", "best (F, W)", "cost / revenue"],
                        rows, "wide"))
    S.prose("Programme size is searched jointly with everything else.  A "
            "larger programme amortises the non-recurring costs over more "
            "missions; a larger fleet delivers more often and each delivery "
            "gets a smaller slice of the market.  The optimum is where "
            "those two turn over, and it is interior.")
    fleets = sorted(set(r["f"] for r in L["coarse"]))
    ws = sorted(set(r["w"] for r in L["coarse"]))
    grid = dict(((r["f"], r["w"]), r["obj"]) for r in L["coarse"])
    rows = []
    for f in fleets:
        rows.append([str(f)] + [P(grid[(f, w)], 7) if (f, w) in grid else "-"
                                for w in ws])
    S.block(D.table(["fleet F"] + ["W = %d" % w for w in ws], rows, "wide"))
    S.prose("One refinement pass then runs around the coarse winner at its "
            "own W, which is what makes the search non-exhaustive: it "
            "explores the neighbourhood of the rung that won and no other.")
    if L["refine"]:
        rows = [[P(r["n"], 6), str(r["f"]), str(r["w"]),
                 D.musd(r["cost"]["total"]), D.musd(r["expected"]),
                 P(r["obj"], 7)] for r in L["refine"]]
        S.block(D.table(["N", "ships", "campaigns/ship", "cost",
                         "expected revenue", "cost / revenue"], rows, "wide"))
    S.prose("Every row below is at the winner's own W, so only the fleet "
            "moves.  Cost falls all the way: a bigger programme always "
            "amortises the non-recurring lines better.  What stops it is "
            "the accumulation window.")
    rows = []
    at_w = sorted((r for r in L["coarse"] + L["refine"]
                   if r["w"] == out["P"]["w"]), key=lambda r: r["f"])
    for r in at_w:
        mark = " <b>argmin</b>" if r["f"] == out["P"]["f"] else ""
        rows.append([str(r["f"]), P(r["n"], 6), P(r["rev"]["window"], 7),
                     P(r["rev"]["clearing"], 7),
                     P(r["rev"]["surplus"] + r["rev"]["unsold"], 6),
                     D.musd(r["cost"]["total"]), P(r["obj"], 7) + mark])
    S.block(D.table(["fleet F", "N", "omega (yr)", "clearing",
                     "past the ceiling (kg)", "cost", "cost / revenue"],
                    rows, "wide"))


# ------------------------------------------------------- 13. the reliability
def part_reliability(S, out):
    """The discount the model applies when it is asked to."""
    C, P_ = out["C"], out["P"]
    rel = P_["rel"]
    S.part("13. Reliability",
           "P = p_launch * exp(-T / MTBF) * p_mining, applied to revenue.")
    if rel["off"]:
        S.prose("<b>Revenue is not discounted for risk on this run.</b>  All "
                "three factors are exactly 1.0, so expected revenue and "
                "gross revenue are the same number everywhere below.  Two "
                "of the three are judgements about hardware nobody has "
                "flown, and folding them into the headline buries them.")
    S.step("P_succ", "P", "probability the mission delivers",
           "p_launch * exp(-T_miss / MTBF) * p_mining",
           "%s * %s * %s" % (P(rel["p_launch"]), P(rel["p_cruise"]),
                             P(rel["p_mining"])),
           rel["p_succ"], "-", ["T_miss", "Rev"])
    S.step("E_Rev", "E[Rev]", "expected revenue", "P * Rev",
           "%s * %s" % (P(rel["p_succ"]), P(P_["rev"]["capped"]["value"])),
           P_["expected"], "$", ["P_succ", "Rev"])


# ------------------------------------------------------ 14. the cost cascade
def part_cost(S, out):
    """Every cost line, the three buckets, contingency and the total."""
    C, M, P_ = out["C"], out["M"], out["P"]
    K = P_["cost"]
    lines = K["lines"]
    S.part("14. The cost cascade",
           "Every line comes from a reference table; none is invented.  The "
           "lines are then bucketed by WHEN the money is spent, because "
           "that is what decides how it compounds.")
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
    S.step("L_rprop", "C_rprop", "return propellant",
           "m_rprop * %s" % ("c_ISRU" if C["isru"] else "c_prop"),
           "%s * %s" % (P(M["m_rprop"]),
                        P(C["cfg"].isru_processing_usd_per_kg if C["isru"]
                          else C["prop_usd_per_kg"])),
           lines["rprop"], "$", ["m_rprop", "c_prop"])
    S.put("c_rig", "c_rig", "mining rig recurring cost",
          C["val"]("Mining payload recurring cost", used=False), "$/kg",
          cite_ops(C, "Mining payload recurring cost"))
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
    S.step("rig_term", "terminal", "salvage credit on what is left",
           "C_rig (1 - util) * salvage",
           "%s * (1 - %s) * %s"
           % (P(K["rig_total"]), P(K["used"]),
              P(C["val"]("Rig salvage fraction", used=False))),
           K["terminal"], "$", ["C_rig_total", "rig_used", "salvage"])
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
    S.put("lc", "LC", "learning-curve factor", K["lc"], "-",
          cite_config("model_learning_curve")
          + ("  Not charged on this run, so it is exactly 1.0."
             if K["lc"] == 1.0 else ""))
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
          cite_ops(C, "Power system (solar + battery)"))
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
           "written out term by term: the sum interleaves N-dependent and "
           "N-independent lines, so pre-adding any prefix re-associates it")
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

    S.prose("What decides how a line compounds is WHEN it is spent, so the "
            "lines are bucketed before any rate is applied.")
    S.step("upfront_lines", "upfront", "money spent at year zero",
           "launch + oprop + hardware + TPS + licensing + insurance + NRE "
           "+ autonomy" + ("" if C["isru"] else " + rprop"),
           "%s + %s + %s + %s + %s + %s + %s + %s%s"
           % (P(lines["launch"]), P(lines["oprop"]), P(K["hardware"]),
              P(lines["tps"]), P(K["licensing"]), P(K["liability"]),
              P(K["nre"]), P(K["autonomy"]),
              "" if C["isru"] else " + " + P(lines["rprop"])),
           K["upfront_lines"], "$",
           ["L_launch", "L_oprop", "hardware", "licensing", "L_nre", "L_aut"]
           + ([] if C["isru"] else ["L_rprop"]))
    ongoing_lines = K["ops"] + (lines["rprop"] if C["isru"] else 0.0)
    S.step("ongoing_lines", "ongoing", "money spent across the mission",
           "operations" + (" + rprop" if C["isru"] else ""),
           P(ongoing_lines), ongoing_lines, "$", ["L_ops"])
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
    S.put("wacc", "r_c", "cost of capital", K["wacc"], "/yr",
          cite_config("apply_wacc_compounding")
          + ("  Not charged on this run, so both multipliers are exactly "
             "1.0 and the programme calendar term is inert with it."
             if K["wacc"] == 0.0 else ""))
    S.step("mult_up", "mult_up", "compounding on up-front money",
           "(1 + r_c) ^ T_miss",
           "(1 + %s) ^ %s" % (P(K["wacc"]), P(M["duration"])),
           K["mult_up"], "-", ["wacc", "T_miss"])
    S.step("mult_on", "mult_on", "compounding on ongoing money",
           "(1 + r_c) ^ (T_miss / 2)",
           "(1 + %s) ^ (%s / 2)" % (P(K["wacc"]), P(M["duration"])),
           K["mult_on"], "-", ["wacc", "T_miss"])
    if K["delta"] != 0.0:
        S.step("cal_delta", "delta", "programme calendar charge",
               "(programme upfront (cal_cost - 1) - (terminal/W)"
               " (cal_credit - 1)) (1 + zeta) mult_up",
               "((%s * (%s - 1)) - (%s * (%s - 1))) * (1 + %s) * %s"
               % (P(K["programme_upfront"]), P(K["cal_cost"]),
                  P(K["rig_credit_share"]), P(K["cal_credit"]),
                  P(C["cfg"].contingency_fraction), P(K["mult_up"])),
               K["delta"], "$", ["upfront", "mult_up"])
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
    S.part("15. The answer",
           "The project ranks on cost over revenue.  Lower is better and "
           "1.0 is breakeven.")
    S.step("obj", "obj", "cost over revenue", "C_tot / E[Rev]",
           "%s / %s" % (P(K["total"]), P(P_["expected"])),
           P_["obj"], "x", ["C_tot", "E_Rev"],
           "what the campaign ranks on")
    S.step("profit", "profit", "profit", "E[Rev] - C_tot",
           "%s - %s" % (P(P_["expected"]), P(K["total"])),
           P_["expected"] - K["total"], "$", ["E_Rev", "C_tot"],
           "the output catalog is SORTED by this, and the project ranks on "
           "the ratio above; they are different questions and the best "
           "case is in general not the first row of the file")
    S.step("roi", "ROI", "return on cost", "profit / C_tot",
           "%s / %s" % (P(P_["expected"] - K["total"]), P(K["total"])),
           (P_["expected"] - K["total"]) / K["total"], "-",
           ["profit", "C_tot"])
    S.step("usd_kg", "$/kg", "cost per kilogram returned", "C_tot / m_pay",
           "%s / %s" % (P(K["total"]), P(M["m_pay"])),
           K["total"] / M["m_pay"], "$/kg", ["C_tot", "m_pay"],
           "against %s the load actually fetches"
           % ("$" + P(P_["rev"]["delivered"], 8)))



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
    for part in sheet.parts:
        for row in part["rows"]:
            if row[0] != "step":
                continue
            tag, symbol, substitution, value = row[1], row[2], row[5], row[6]
            expr = evaluable(substitution)
            if expr is None:
                unchecked.append((tag, symbol, substitution))
                continue
            try:
                got = eval(expr, {"__builtins__": {}}, dict(_ALLOWED))
            except Exception as exc:
                bad.append((tag, symbol, substitution, "%s" % exc, value))
                continue
            checked += 1
            scale = max(abs(float(value)), abs(float(got)), 1e-30)
            if abs(float(got) - float(value)) / scale > tol:
                bad.append((tag, symbol, substitution, got, value))
    return checked, unchecked, bad


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
    S.part("16. Cross-checks",
           "Each row is two numbers that were computed by different routes "
           "and must agree.  If one of them disagrees on your paper, the "
           "error is upstream of it and the tags say where to look.")
    rows = []

    def ident(what, left_label, left, right_label, right, tags):
        """One identity: two routes to one number, and their difference."""
        rows.append([what, left_label, P(left, 12), right_label,
                     P(right, 12), P(abs(left - right), 3), tags])

    ident("the hardware ledger",
          "m_hw", M["hw"],
          "m_rig + m_plant + m_EP",
          C["cfg"].mining_hardware_kg + M["plant"] + M["ep"]["mass"],
          "S: m_hw, m_plant, m_EP")
    ident("the launch margin",
          "M_LEO - m_launch", C["leo_cap"] - M["m_launch"],
          "(budget - m_at) k_out R_out",
          (R["budget"] - M["m_at"]) * R["k_out"] * R["R_out"],
          "S: m_launch, m_at, budget")
    ident("the hold is full",
          "sum of what the knapsack took", sum(M["load"]["mix"].values()),
          "m_pay", M["m_pay"], "S: m_pay")
    ident("the sale never exceeds the hold",
          "Rev", P_["rev"]["capped"]["value"],
          "clearing * V_hold",
          P_["rev"]["clearing"] * P_["rev"]["gross_base"],
          "S: Rev, clearing, hold_value")
    ident("the cost buckets add up",
          "C_tot", K["total"],
          "upfront* + ongoing* + end*"
          + (" + delta" if K["delta"] else ""),
          K["upfront"] * K["mult_up"] + K["ongoing"] * K["mult_on"]
          + K["end"] + K["delta"], "S: C_tot")
    ident("the contingency reserve",
          "reserve", K["contingency"],
          "zeta (upfront + ongoing + end)",
          C["cfg"].contingency_fraction
          * (K["upfront_lines"] + K["ops"]
             + (K["lines"]["rprop"] if C["isru"] else 0.0) + K["handover"]),
          "S: contingency")
    ident("the programme is a rectangle",
          "N", float(P_["n"]), "F * W", float(P_["f"] * P_["w"]),
          "I: N, F, W")
    ident("the objective",
          "obj", P_["obj"], "C_tot / E[Rev]", K["total"] / P_["expected"],
          "S: obj")
    S.block(D.table(["identity", "one route", "value", "the other route",
                     "value", "difference", "tags"], rows, "wide"))
    S.prose("Two structural bounds that are inequalities rather than "
            "identities: <b>W = %s must not exceed trips = %s</b>, because a "
            "rig cannot fly more campaigns than it survives; and "
            "<b>clearing = %s must not exceed 1</b>, because a ceiling can "
            "only ever cost a delivery revenue."
            % (P(P_["w"]), P(M["trips"]), P(P_["rev"]["clearing"], 8)))


# ------------------------------------------------------------------- render
CSS = """
:root{--ink:#16181d;--mute:#5d6470;--rule:#d8dce3;--bg:#fff;
      --tint:#f5f7fa;--key:#0b5cad;--warn:#8a4b00;--ok:#0a6b3d;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:14px/1.55 "Iowan Old Style",Palatino,Georgia,serif;}
.wrap{max-width:60rem;margin:0 auto;padding:2.2rem 1.1rem 5rem;}
h1{font-size:1.9rem;line-height:1.2;margin:0 0 .2rem;}
h2{font-size:1.18rem;margin:2.6rem 0 .5rem;padding-bottom:.28rem;
   border-bottom:2px solid var(--ink);}
.sub{color:var(--mute);margin:0 0 1.4rem;font-size:.95rem;}
p{margin:.55rem 0;}
.blurb{color:var(--mute);margin:.2rem 0 1rem;}
code,.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;}
table{border-collapse:collapse;width:100%;font-size:.84rem;margin:.5rem 0 1rem;}
th,td{text-align:left;vertical-align:top;padding:.3rem .45rem;
      border-bottom:1px solid var(--rule);}
th{font-size:.74rem;text-transform:uppercase;letter-spacing:.04em;
   color:var(--mute);border-bottom:1px solid var(--ink);font-weight:600;}
.tw{overflow-x:auto;}
.sheet td{border-bottom:1px solid var(--rule);}
.sheet tr.in td{background:var(--tint);}
.tag{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.76rem;
     color:var(--key);white-space:nowrap;font-weight:600;width:3.1rem;}
.sym{white-space:nowrap;font-weight:600;}
.qty{display:block;font-weight:400;color:var(--mute);font-size:.78rem;}
.work{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.78rem;
      overflow-wrap:anywhere;}
/* The citation column is the widest thing on the page and must not be
   allowed to push the VALUE off the edge: a worksheet whose answers have
   scrolled out of view is a worksheet nobody can check. */
.sheet col.c1{width:3.4rem} .sheet col.c2{width:11rem}
.sheet col.c4{width:9.5rem}
.sub2{display:block;color:var(--ink);margin-top:.15rem;
      word-break:break-word;}
.uses{display:block;color:var(--mute);font-size:.72rem;margin-top:.15rem;
      font-family:inherit;}
.val{font-family:ui-monospace,Menlo,Consolas,monospace;text-align:right;
     white-space:nowrap;font-weight:600;}
.unit{color:var(--mute);font-weight:400;}
.src{color:var(--mute);font-style:italic;}
.note{display:block;color:var(--warn);font-size:.76rem;margin-top:.2rem;}
.prose{color:var(--ink);}
.card{border:1px solid var(--rule);background:var(--tint);
      padding:.8rem 1rem;margin:1rem 0 1.6rem;}
.card table{margin:0;font-size:.82rem;}
.card td{border:0;padding:.14rem .5rem .14rem 0;}
.big{font-size:1.5rem;font-weight:700;}
.foot{margin-top:2.5rem;padding-top:.8rem;border-top:2px solid var(--ink);
      color:var(--mute);font-size:.84rem;}
.ok{color:var(--ok);font-weight:600;}
@media print{
  body{font-size:10.5pt;} .wrap{max-width:none;padding:0;}
  h2{page-break-after:avoid;} tr{page-break-inside:avoid;}
  .tw{overflow:visible;}
}
@page{margin:14mm 12mm;}
"""


def render_row(row):
    """One row of the sheet: an input, a step, a prose line or a block."""
    kind = row[0]
    if kind == "prose":
        return ('<tr><td class="tag"></td><td class="prose" colspan="3">%s'
                '</td></tr>' % row[1])
    if kind == "block":
        return ('<tr><td class="tag"></td><td colspan="3">%s</td></tr>'
                % row[1])
    if kind == "input":
        _k, tag, symbol, quantity, value, unit, source = row
        return ('<tr class="in"><td class="tag">%s</td>'
                '<td class="sym">%s<span class="qty">%s</span></td>'
                '<td class="work"><span class="uses">%s</span></td>'
                '<td class="val">%s <span class="unit">%s</span></td></tr>'
                % (tag, D.esc(symbol), D.esc(quantity), source,
                   P(value, 12) if isinstance(value, (int, float))
                   else D.esc(value), D.esc(unit)))
    (_k, tag, symbol, quantity, formula, substitution, value, unit, tags,
     note) = row
    return ('<tr><td class="tag">%s</td>'
            '<td class="sym">%s<span class="qty">%s</span></td>'
            '<td class="work">%s<span class="sub2">= %s</span>%s%s</td>'
            '<td class="val">%s <span class="unit">%s</span></td></tr>'
            % (tag, D.esc(symbol), D.esc(quantity), D.esc(formula),
               D.esc(substitution),
               '<span class="uses">from %s</span>' % ", ".join(tags)
               if tags else "",
               '<span class="note">%s</span>' % note if note else "",
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
            ("cost / revenue", "%s x" % P(P_["obj"], 6)),
            ("best of", "%s evaluable bodies in this cell"
             % D.fmt(C["population"], 0)),
            ("source", D.esc(out["cell"])),
            ("calc version", D.esc(out["terms"]["stamp"])),
            ("market model", D.esc(out["terms"]["market"])),
            ("Stage 3 tables", "spacecost %s" % D.esc(spacecost_pin())),
            ("built", datetime.date.today().isoformat())]
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
        "reproduce their own result</span>, %d differ, and %d lines are "
        "prose rather than arithmetic (%s).  That is a check on the PAGE "
        "rather than on the model, and it is the one the model's own "
        "comparison cannot make: a substitution can omit a term, or round "
        "an operand past the point where it reproduces the answer, while "
        "every derived quantity is still exactly right.</p>"
        % (checked - len(bad), checked, len(bad), len(unchecked),
           ", ".join(D.esc(t) for t, _s, _x in unchecked) or "none"))
    bits.append(
        "<p>Every figure above is derived by "
        "<code>campaign/worked_calculation.py</code> and then compared, "
        "column by column, against the row the pipeline actually produced: "
        "<span class='ok'>%d quantities, %d bit-exact, %d within %g, "
        "%d differing</span>, worst relative difference %.3e on "
        "<code>%s</code>.  The worksheet adds no arithmetic of its own; it "
        "changes the order things are said in and cites where each input "
        "came from.</p>"
        % (c["n"], c["exact"], c["close"], c["tol"], len(c["bad"]),
           c["worst"], D.esc(c["worst_name"])))
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
    for build_part in (part_constants, part_body, part_prices, part_transfer,
                       part_ratios, part_plant_rating, part_fixed_point,
                       part_settled, part_stack, part_clock, part_hold,
                       part_market, part_searches, part_reliability,
                       part_cost, part_answer, part_checks):
        build_part(sheet, out)
    return sheet


def document(out, sheet=None):
    """Assemble the whole worksheet as one HTML page."""
    sheet = build_sheet(out) if sheet is None else sheet
    body = [header(out)]
    contents = []
    for n, part in enumerate(sheet.parts, 1):
        anchor = "p%d" % n
        contents.append('<a href="#%s">%s</a>' % (anchor, part["title"]))
        body.append(D.h(2, D.esc(part["title"]), anchor))
        if part["blurb"]:
            body.append('<p class="blurb">%s</p>' % part["blurb"])
        body.append('<div class="tw"><table class="sheet">'
                    '<colgroup><col class="c1"><col class="c2">'
                    '<col class="c3"><col class="c4"></colgroup>'
                    '<thead><tr><th>tag</th><th>quantity</th>'
                    '<th>how it is worked out</th><th>value</th></tr></thead>'
                    '<tbody>')
        body.extend(render_row(r) for r in part["rows"])
        body.append("</tbody></table></div>")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Verification worksheet: %s</title><style>%s</style></head>"
        "<body><div class='wrap'><h1>Verification worksheet: %s</h1>"
        "<p class='sub'>Every number behind %s x, with its source, in the "
        "order the model works them out.</p>%s<p class='blurb'>%s</p>"
        "%s%s</div></body></html>"
        % (D.esc(out["designation"]), CSS, D.esc(out["designation"]),
           P(out["P"]["obj"], 6), header(out),
           " &middot; ".join(contents),
           "".join(body[1:]), footer(out, sheet)))


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
    ap.add_argument("--check", action="store_true",
                    help="evaluate every substitution and write nothing")
    ap.add_argument("--self-test", action="store_true",
                    help="prove the substitution check can fail, by "
                         "perturbing one printed value")
    args = ap.parse_args(argv)

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
    bad = report_substitutions(sheet)
    if args.self_test and self_test(sheet):
        return 1
    if bad:
        print("")
        print("*** A SUBSTITUTION DOES NOT PRODUCE ITS OWN RESULT ***")
        return 1
    if args.check:
        print("  OK  every substitution reproduces the value beside it")
        return 0
    html = document(out, sheet)
    html_path = args.out + ".html"
    with open(html_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    print("  wrote     %s  (%d chars)" % (html_path, len(html)))
    if args.pdf and W.render_pdf(html_path, args.out + ".pdf"):
        print("  wrote     %s" % (args.out + ".pdf"))
    return 0


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


if __name__ == "__main__":
    sys.exit(main())
