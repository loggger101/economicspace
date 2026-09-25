# -*- coding: utf-8 -*-
"""The document `worked_calculation.py` derives the numbers for.

Every figure on the page comes out of the derivation dicts.  Nothing here
computes a model quantity and nothing here is typed: this module decides what
to SAY and in what order, and the arithmetic has already happened.  That split
is the reason the document cannot go stale against the model the way a
hand-written one did within nine hours of being finished.

⚠️  THE PROSE BRANCHES, because the document is about whichever mission the
run actually picked.  A sentence that asserts an architecture -- "the return is
propulsive", "the plant is solar" -- is wrong the moment the best case is a
different shape, and the whole point of the rewrite this module belongs to is
that the best case is not knowable in advance.  So every such sentence is
selected from the derived shape, and the terms in force are stated rather than
assumed.

⚠️  Numbers are formatted here and ONLY here.  `fmt` and its friends are the
single place a unit or a precision is decided, so a figure cannot appear with
four decimals in one table and two in the next.
"""
import datetime
import html
import math


# ─────────────────────────────────────────────────────────────── formatting
def fmt(value, places=2, unit=""):
    """A float with thousands separators, a fixed precision and a unit."""
    if value is None:
        return "n/a"
    try:
        text = "{:,.{p}f}".format(float(value), p=places)
    except (TypeError, ValueError):
        return html.escape(str(value))
    return text + (" " + unit if unit else "")


def usd(value, places=0):
    """Dollars, at `places` decimals or enough to keep a small rate legible.

    🚨  "ALWAYS LARGE ENOUGH TO WANT SEPARATORS" WAS FALSE OF EVERY
    RATE ON THE PAGE, AND `places=0` THEN PRINTED THEM AS `$0`.  Methalox is
    $0.186/kg, so a chemical mission's cost table read "6,491.7 kg x $0/kg" --
    a basis that tells the reader the propellant is free and that no audit can
    match against the line beside it.  `places` is a MINIMUM now: a value under
    a dollar gets whatever it needs for three significant figures, and nothing
    at or above a dollar renders differently from before.
    """
    try:
        size = abs(float(value))
    except (TypeError, ValueError):
        return "$" + fmt(value, places)
    if 0.0 < size < 1.0:
        places = max(places, 2 - int(math.floor(math.log10(size))))
    return "$" + fmt(value, places)


def musd(value):
    """Dollars in millions, at enough precision to identify the line.

    🚨  TWO DECIMALS IN MILLIONS IS TWO SIGNIFICANT FIGURES ON A $780k LINE.
    Three cost lines on the default cell were rendering as `$0.78M`, `$0.66M`
    and `$0.33M`, which a reader cannot check against anything and a column
    audit correctly reported as absent from the page.  The cents are still
    noise on a billion-dollar line, so the precision follows the SIZE rather
    than the unit.
    """
    try:
        millions = float(value) / 1e6
    except (TypeError, ValueError):
        return fmt(value)
    # 🚨  AND THE TIERS STOPPED AT FOUR DECIMALS, WHICH IS ONE
    # SIGNIFICANT FIGURE ON A $778 LINE.  A return-propellant line of $778.22
    # rendered `$0.0008M` and the column audit reported it absent, correctly:
    # the page was not showing it, it was showing a rounding of it.  Below
    # $0.1M the millions are the wrong UNIT rather than the wrong precision, so
    # the line falls back to plain dollars.  The table's header says "cost" and
    # claims no unit, which is what makes that safe.
    if abs(float(value)) < 100_000.0:
        return usd(value, 2)
    size = abs(millions)
    return "$" + fmt(millions, 2 if size >= 10.0 else 3 if size >= 1.0 else 4) + "M"


def pct(value, places=2):
    """A fraction rendered as a percentage."""
    return fmt(float(value) * 100.0, places) + "%"


def sig(value, places=6):
    """A ratio or a multiplier, where the digits matter more than the size."""
    return fmt(value, places)


def prec(value, digits=12, unit=""):
    """A number at `digits` significant figures, with thousands separators.

    🚨  THE TABLES ROUND AND THE SUBSTITUTIONS MUST NOT.  A `deriv` block
    claims that the numbers on its left produce the number on its right, and a
    reader who retypes rounded intermediates does not get the printed result
    back -- which turns the one part of the page that can be checked by hand
    into the one part that fails when it is.  `fmt` is for reading; this is for
    arithmetic, and the two are deliberately different functions.
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        return esc(value)
    if value != value or value in (float("inf"), float("-inf")):
        return esc("%g" % value)
    if value == 0.0:
        return "0" + (" " + unit if unit else "")
    exponent = int(math.floor(math.log10(abs(value))))
    # Outside this band a fixed-point rendering is unreadable rather than
    # precise: a yield of 1.5e-06 does not want thirteen leading zeros.
    if exponent > digits + 3 or exponent < -4:
        return ("%.*e" % (digits - 1, value)) + (" " + unit if unit else "")
    text = "{:,.{p}f}".format(value, p=max(0, min(15, digits - 1 - exponent)))
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text + (" " + unit if unit else "")


def esc(text):
    """HTML-escape any value, including the ones that are not strings."""
    return html.escape(str(text))


# ─────────────────────────────────────────────────────────────────── layout
def h(level, text, anchor=None):
    """A heading, optionally anchored so the contents list can reach it.

    An anchored heading also carries a self-link, which is hidden until the
    heading is hovered and hidden again in print.  A sixty-page derivation
    whose sections cannot be linked to is a document nobody quotes from.
    """
    tag = "h%d" % level
    if not anchor:
        return "<%s>%s</%s>" % (tag, text, tag)
    return ('<%s id="%s">%s<a class="anchor" href="#%s" '
            'aria-label="link to this section">&#182;</a></%s>'
            % (tag, anchor, text, anchor, tag))


def para(text):
    """A paragraph of prose."""
    return "<p>%s</p>" % text


def note(kind, text):
    """A called-out paragraph: `warn`, `ok` or `key`."""
    return '<p class="note %s">%s</p>' % (kind, text)


def table(headers, rows, cls=""):
    """A table from a header list and a list of cell lists.

    ⚠️  WRAPPED, BECAUSE A TABLE CANNOT SHRINK BELOW ITS OWN CONTENT.  The
    nomenclature table measures about 414px at its narrowest and a phone is
    375px, so an unwrapped one does not overflow itself -- it widens the
    BODY, and every paragraph on the page then sits in a column the reader
    has to scroll sideways to finish.  The wrapper takes the overflow
    instead, and print turns it off again because paper has no scrollbar.
    """
    out = ['<div class="tw"><table%s>' % (' class="%s"' % cls if cls else "")]
    out.append("<thead><tr>%s</tr></thead>"
               % "".join("<th>%s</th>" % c for c in headers))
    out.append("<tbody>")
    for r in rows:
        out.append("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r))
    out.append("</tbody></table></div>")
    return "".join(out)


def eq(text):
    """A display equation, set apart from the prose."""
    return '<div class="eq">%s</div>' % text


def kv(pairs):
    """A two-column definition table for a block of named quantities."""
    return table(["quantity", "value"], [[k, v] for k, v in pairs], "kv")


def deriv(rows):
    """A substitution block: symbol, expression and an optional note per row.

    This is the form the whole document turns on.  A table of answers states
    that the model produced them; a substitution states what was multiplied by
    what, so a reader with a calculator can disagree.  Rows are
    `(symbol, expression)` or `(symbol, expression, note)`, and a bare string
    is a comment spanning the block.  A continuation line passes an empty
    symbol, which is what aligns a chain of `=` under its own left-hand side.
    """
    body = []
    for row in rows:
        if isinstance(row, str):
            body.append('<tr><td class="dsym"></td>'
                        '<td class="dnote" colspan="2">%s</td></tr>' % row)
            continue
        symbol, expression = row[0], row[1]
        body.append('<tr><td class="dsym">%s</td><td class="dexp">%s</td>'
                    '<td class="dnote">%s</td></tr>'
                    % (symbol, expression, row[2] if len(row) > 2 else ""))
    return '<div class="deriv"><table>%s</table></div>' % "".join(body)


def outputs(pairs):
    """What a section produces, boxed at its head so the page can be skimmed.

    The sections run in the order the model evaluates things, so a reader
    following one quantity through the cascade would otherwise have to read
    every section whole to find where it was settled.
    """
    return ('<div class="out"><table>%s</table></div>'
            % "".join('<tr><td class="dsym">%s</td><td class="dexp">%s</td>'
                      '<td class="dnote">%s</td></tr>'
                      % (k, v, row[2] if len(row) > 2 else "")
                      for row in pairs for k, v in [(row[0], row[1])]))


# ──────────────────────────────────────────────────────── the section list
# 🚨  ONE PLACE A SECTION'S NUMBER, TITLE AND ANCHOR LIVE.  Every one of them
# used to be typed into the `h(2, ...)` call inside the section, AGAIN into
# the contents list at the bottom of this file under a different wording, and
# AGAIN into every sentence elsewhere that says "see section 6" -- and three
# sections have early-return branches that repeated their own heading a second
# and a third time, so one section carried up to four copies of its own
# identity with nothing holding them to each other.  Inserting a section
# renumbered the headings and left every cross-reference in the prose pointing
# one section short, silently, which is this repo's standing failure mode
# wearing a table of contents.
#
# The number is the POSITION, so it cannot disagree with the order; `sec()`
# writes the heading, `ref()` writes a cross-reference, and `contents()` reads
# the same list.  `document()` asserts that every section emitted its own
# anchor exactly once, which is what stops a section quietly rendering under
# somebody else's heading.
SECTION_ORDER = [
    ("nomenclature", "Nomenclature and input values"),
    ("body",         "The body"),
    ("composition",  "Composition, and what a kilogram is worth"),
    ("transfer",     "Getting there and back"),
    ("cascade",      "The mass cascade"),
    ("power",        "Power"),
    ("clock",        "The clock"),
    ("hold",         "The hold"),
    ("market",       "The market"),
    ("searches",     "The searches"),
    ("reliability",  "Reliability"),
    ("cost",         "The cost cascade"),
    ("answer",       "The answer"),
]
SECTION_NO = dict((anchor, n) for n, (anchor, _t) in enumerate(SECTION_ORDER))
SECTION_TITLE = dict(SECTION_ORDER)


def sec(anchor):
    """The numbered, anchored heading for a section, from the list above."""
    return h(2, "%d. %s" % (SECTION_NO[anchor], SECTION_TITLE[anchor]), anchor)


def ref(anchor, word="section"):
    """A cross-reference to a section, as a link carrying its real number.

    ⚠️  IT IS A LINK RATHER THAN A PHRASE, which is the half a typed "section
    6" could never be: the number is right because it is the position, and the
    reader can reach it because the anchor is the same string the heading was
    written from.
    """
    return '<a href="#%s">%s %d</a>' % (anchor, word, SECTION_NO[anchor])


# ───────────────────────────────────────────────────────────── the sentences
def architecture(out):
    """The mission's shape, as a dict of booleans and names the prose reads."""
    C, M, row = out["C"], out["M"], out["archived"]
    return {
        "beneficiated": bool(C["beneficiated"]),
        "aero": bool(row["aerocapture_return"]),
        "isru": bool(row["isru_return"]),
        "power": str(row["power_source"]),
        "apsis": str(row["rendezvous_apsis"]),
        # Two questions, not one: the penalty is a property of the propellant
        # and is always charged, while the STAGE exists only if the model was
        # asked to size one.  See the shape guard in `context`.
        "electric": bool(C["electric"]),
        "penalised": float(row["dv_penalty_factor"]) > 1.0,
        "vehicle": str(row["vehicle"]),
        "propellant": str(row["propellant"]),
        "searched": bool(out["terms"]["searched"]),
        "ep_kg": float(M["ep"]["mass"]),
        "dest": str(C["destination"]),
        "lander": bool(C["arch"].get("needs_lander")),
        "to_earth": bool(C["arch"]["returns_to_earth"]),
        "boiloff": float(M["boiloff_factor"]) > 1.0,
        "tps_kg": float(M["m_tps"]),
    }


def shape_sentence(a):
    """One sentence naming the architecture the search chose.

    Assembled from the shape rather than written down, because which of these
    clauses is true is exactly what the search decides per body.
    """
    bits = ["a %s mission to %s" % ("beneficiated" if a["beneficiated"]
                                    else "raw", esc(a["dest"]))]
    bits.append("flown on a %s" % esc(a["vehicle"]))
    bits.append("burning %s" % esc(a["propellant"]))
    bits.append("returning %s"
                % ("by aerocapture" if a["aero"] else "propulsively"))
    bits.append("making its return propellant on site" if a["isru"]
                else "carrying its return propellant from Earth")
    bits.append("powered by %s"
                % ("a radioisotope source" if a["power"] == "rtg"
                   else "a solar array"))
    bits.append("meeting the target at %s" % esc(a["apsis"]))
    return ", ".join(bits) + "."


def terms_sentence(terms):
    """What the run charged for, and what it did not."""
    on, off = [], []
    for name, live in (("mission reliability", terms["reliability"]),
                       ("the learning curve", terms["learning"]),
                       ("the cost of capital", terms["wacc"]),
                       ("insurance premiums", terms["insurance"])):
        (on if live else off).append(name)
    if terms["surplus_frac"] > 0:
        on.append("a surplus sale at %s of full price"
                  % pct(terms["surplus_frac"], 0))
    elif terms["market"] == "capacity_cap":
        off.append("any sale past a market ceiling")
    parts = []
    if on:
        parts.append("This run charged " + english(on) + ".")
    if off:
        parts.append("It did not charge " + english(off) + ".")
    return " ".join(parts)


# The model's leg keys are identifiers, and an identifier in a sentence is a
# reader's problem rather than a precision.  The key is still shown, in code
# font beside the phrase, because it is what to grep for in `_legs`.
LEG_LABEL = {
    "ret_cislunar_prop": "a propulsive capture into a cislunar NRHO depot",
    "ret_lunar_surface_prop": "a cislunar capture and then a propulsive "
                              "descent to the lunar surface",
    "ret_leo_prop": "a propulsive capture into LEO",
    "ret_leo_aero": "aerocapture and aerobraking into LEO",
    "ret_geo_prop": "a propulsive capture into GEO",
    "ret_geo_aero": "aerocapture into a GEO-apogee ellipse",
    "ret_earth_surface_aero": "direct entry at Earth",
    "ret_earth_surface_prop": "a propulsive capture into LEO and a deorbit burn",
    "ret_mars_surface_aero": "aeroentry and retropropulsion to the Mars surface",
    "ret_mars_surface_prop": "a propulsive capture and powered descent at Mars",
    "ret_mars_orbit_prop": "a propulsive capture into a 1-sol Mars orbit",
    "ret_mars_orbit_aero": "aerocapture into a 1-sol Mars orbit",
}


def crossover_au(C):
    """Where a solar array and a radioisotope source deliver the same W/kg.

    Solar is rated at 1 AU and falls as 1/r2; an RTG is flat.  So
    `w_1au / r^2 = w_rtg` at `r = sqrt(w_1au / w_rtg)`, and the page can show
    the square root rather than assert its answer.  It asserted "3.46 AU" for
    four releases, three of them after the rates it is made of were already
    being printed a paragraph above it.
    """
    return math.sqrt(C["w_1au"] / C["rtg_w_per_kg"])


def english(items):
    """`a`, `a and b`, or `a, b and c`."""
    items = list(items)
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


# ───────────────────────────────────────────────────────────────── sections
# The `diameter_source` labels whose diameter is a CATALOG INPUT rather than
# the output of the H-and-albedo relation.  `derived_mass` arrived with data
# contract 1.4.0: a measured mass at the class density, which puts no assumed
# albedo on the row, so the H chain has nothing to substitute.
_DIAMETER_NOT_FROM_H = {
    "measured": "a measured diameter",
    "derived_mass": "derived by Stage 1 from the body's MEASURED mass at its "
                    "class density",
}


def diameter_from_h(body):
    """Was this body's diameter sized from H and an albedo?

    ONE DEFINITION, TWO RENDERERS.  This page and `verification_sheet.py`
    both branch on it, and a label the two read differently is a body the two
    documents describe differently.
    """
    return str(body.get("diameter_source") or "unknown") \
        not in _DIAMETER_NOT_FROM_H


def diameter_provenance(body):
    """A reader's phrase for where a diameter NOT sized from H came from."""
    return _DIAMETER_NOT_FROM_H.get(str(body.get("diameter_source") or ""),
                                    "sized from H and an albedo")


def group_restates_type(comp_group, spectral_type):
    """True when the taxonomy GROUP adds nothing to the spectral LETTER.

    `D-type` beside a `D` is one fact written twice, and the header drops the
    group when that is all it is.  `X-complex` beside an `M` is two facts and
    is kept.

    🚨  THE COMPLETENESS AUDIT CALLS THIS TOO, AND THAT IS THE WHOLE REASON IT
    IS A FUNCTION.  `comp_group` is an output column, so `--audit` asks the
    page to show it; on a body where the header suppresses it the audit is
    right that the string is absent and wrong that anything is missing.  The
    alternative was an exemption for the column, which would have stopped it
    being checked on exactly the bodies where it carries information -- the
    header's rule and the audit's rule have to be ONE rule, or the next edit
    to either silently pulls them apart.
    """
    if not comp_group:
        return True
    return (str(comp_group).lower().replace("-type", "")
            == str(spectral_type or "").lower())


def named_as(out):
    """The body's name, when the catalog holds one the designation does not.

    ⚠️  THE SAME RULE AS `group_restates_type`, AND FOR THE SAME
    REASON: this is a condition the page and the audit have to share, or the
    next edit to either pulls them apart.  A provisional designation appears in
    `name` as its own text on most rows, and printing "2021 CX5 2021 CX5"
    reads as two facts where there is one.
    """
    name = str(out["archived"].get("name") or "").strip()
    if not name or name in str(out["designation"]):
        return ""
    return " " + esc(name)


def s_header(out):
    """Title block: what this document is about and how it was produced."""
    a = architecture(out)
    C, P = out["C"], out["P"]
    body = esc(out["designation"])
    rows = [
        # ⚠️  THE GROUP ONLY WHEN IT SAYS SOMETHING THE LETTER DOES NOT.  On
        # most bodies `comp_group` is the spectral type with "-type" after it,
        # and printing "D, D-type" reads as two facts where there is one.
        # ⚠️  A NAMED BODY IS NAMED.  `name` is an output column
        # and most rows carry a provisional designation in it, which repeats
        # the heading; a numbered asteroid carries a real name that the page
        # dropped, and `--audit` reported it missing at `mars_surface` on the
        # first run that documented one.  Shown when it says something the
        # designation does not, which is the `comp_group` rule again.
        ("body", "%s%s  (%s%s)"
         % (body, named_as(out),
            esc(out["archived"].get("spectral_type", "type unknown")),
            "" if group_restates_type(
                C.get("comp_group"),
                out["archived"].get("spectral_type", ""))
            else ", " + esc(C["comp_group"]))),
        # The ROW's destination, not the live config's.  See the guard in
        # `context`: those two disagreed silently until 2026-09-14, and this
        # line is where the disagreement was visible.
        # The architecture's OWN label, which the row carries and the page used
        # to paraphrase from the return leg.  A depot, a surface base and a
        # re-entry capsule are three different missions and this is the one
        # place the model says which in words.
        ("destination", esc(C["destination"])),
        ("source", esc(out["cell"])),
        ("cost / revenue", "<strong>%s x</strong>" % sig(P["obj"], 4)),
        ("programme", "N = %d, %d ship(s) x %d campaign(s)"
         % (P["n"], P["f"], P["w"])),
        ("market model", esc(out["terms"]["market"])),
        ("calc version", esc(out["terms"]["stamp"])),
        ("built", datetime.date.today().isoformat()),
    ]
    if C.get("arch_label"):
        rows.insert(2, ("delivery architecture", esc(C["arch_label"])))
    if C.get("population"):
        rows.insert(2, ("best of", "%s evaluable bodies in this cell"
                        % fmt(C["population"], 0)))
    # 🚨  THE STRIP IS DERIVED LIKE EVERYTHING ELSE.  It is the one part of
    # the page a reader sees without scrolling, which makes it the worst
    # possible place for a figure somebody typed -- so every tile reads the
    # same dicts the sections below it derive from, and the objective tile is
    # literally `P["obj"]`, the number section 12 ends on.
    M, cost = out["M"], P["cost"]
    figures = [
        ("cost / revenue", sig(P["obj"], 4), "x", True),
        ("payload returned", fmt(M["m_pay"], 0), "kg", False),
        # ⚠️  N = 1 IS THE COMMON CASE AND "1 missions" READS AS A BUG.
        # Every other tile carries a unit that does not inflect; this one
        # does, and a single-mission cell is exactly the cell somebody looks
        # at first.
        ("programme", "%d" % P["n"],
         "mission" if P["n"] == 1 else "missions", False),
        ("expected revenue", musd(P["expected"]), "", False),
        ("total cost", musd(cost["total"]), "", False),
    ]
    strip = ('<div class="figs">%s</div>'
             % "".join('<div class="fig%s"><span class="k">%s</span>'
                       '<span class="v">%s%s</span></div>'
                       % (" lead" if lead else "", esc(key), value,
                          ('<span class="u"> %s</span>' % esc(unit))
                          if unit else "")
                       for key, value, unit, lead in figures))
    return "".join([
        '<header class="masthead"><div>',
        '<p class="eyebrow">Worked calculation &#183; %s &#183; calc %s</p>'
        % (esc(C["destination"]), esc(out["terms"]["stamp"])),
        h(1, body),
        '<p class="standfirst"><strong>%s</strong></p>' % shape_sentence(a),
        '<p class="terms">%s</p>' % terms_sentence(out["terms"]),
        strip,
        '</div></header>',
        kv(rows),
        note("key",
             "Every figure below is derived from the reference tables and the "
             "body's own orbital elements, in the order the model evaluates "
             "them. None is copied from the run's output. The footer reports "
             "what happened when the two were compared column by column."),
    ])


# 🚨  THE THREE CLASSES ARE THE POINT OF THE NOMENCLATURE TABLE, AND THEY
# ARE NOT DEGREES OF CONFIDENCE.  A measured orbital element and a chosen bulk
# density are both "inputs", and a reader who cannot tell them apart cannot
# tell which half of the answer is astronomy and which half is a judgement
# somebody made.  D is narrower still: two entries in the whole table are not
# given at all, they are the output of the searches in section 9, and printing
# them beside the givens without saying so would be the one genuinely
# misleading thing a table like this can do.
CLASSES = [
    ("K", "known", "measured, quoted, or defined outside this model"),
    ("A", "assumed", "chosen here; a dial rather than a measurement"),
    ("D", "decided", "the output of a search on this page"),
]


def symbols(rows):
    """The nomenclature table: symbol, quantity, value, unit and class."""
    return table(["symbol", "quantity", "value", "unit", "cls"], rows, "sym")


def s_nomenclature(out):
    """Section 0: every input, with its value, its unit and where it came from.

    ⚠️  NOTHING HERE IS TYPED AND NOTHING HERE IS DERIVED.  Every value is read
    off the context the derivation built, so the table cannot drift from the
    arithmetic below it; every LABEL and every class letter is prose, which is
    the half a renderer is allowed to own.  A row that had to compute something
    to fill itself in would be a second opinion about a number the rest of the
    document already derives.
    """
    C, M, B = out["C"], out["M"], out["B"]
    cfg, val, a = C["cfg"], C["val"], architecture(out)
    P, ph, terms = out["P"], C["physics"], out["terms"]
    measured = not diameter_from_h(B)

    body_rows = [
        ["H", "absolute magnitude", prec(C["H"], 6), "mag", "K"],
    ]
    # A diameter derived from a measured mass carries no albedo at all, and a
    # row printing "None" as a given is worse than no row.
    if not measured or C.get("albedo_measured") is not None:
        body_rows.append(
            ["p_V", "geometric albedo (measured)" if measured
             else "geometric albedo (taxonomy default)",
             prec(C["albedo_measured"] if measured else C["albedo"], 6), "-",
             "K" if measured else "A"])
    body_rows += [
        ["rho", "bulk density", prec(C["rho"], 6), "g/cm3", "A"],
        ["a", "semi-major axis", prec(C["a_au"], 12), "AU", "K"],
        ["e", "eccentricity", prec(C["e"], 12), "-", "K"],
        ["i", "inclination", prec(C["inc"], 8), "deg", "K"],
    ]
    if measured:
        body_rows.append(["D", "diameter (%s)"
                          % ("measured" if B.get("diameter_source") == "measured"
                             else "from the measured mass"),
                          prec(B["d_km"], 8), "km", "K"])
    body_rows += [
        ["f_c", "composition fractions (%s)"
         % ", ".join(esc(n) for n, _f, _p in C["phases"]),
         ", ".join(prec(f, 4) for _n, f, _p in C["phases"]), "-", "A"],
        ["kappa", "platinum-group enrichment", prec(C["kappa"], 4), "x", "A"],
        ["phi_min", "mineable fraction of the body",
         prec(cfg.max_mining_fraction, 4), "-", "A"],
        ["P_rot", "rotation period", prec(C["rot_h"], 6), "h", "A"],
    ]

    physics_rows = [
        ["g_0", "standard gravity", prec(ph["g0"], 8), "m/s2", "K"],
        ["mu_E", "Earth gravitational parameter", prec(ph["mu_earth"], 12),
         "km3/s2", "K"],
        ["v_E", "Earth orbital velocity", prec(ph["v_earth"], 6), "km/s", "K"],
        ["r_LEO", "parking-orbit radius", prec(ph["r_leo"], 8), "km", "A"],
        ["R_M", "lunar orbital radius", prec(ph["r_moon"], 8), "km", "K"],
        ["dv_NRHO", "NRHO insertion increment", prec(ph["dv_nrho"], 4),
         "km/s", "K"],
        ["tau_fit", "cruise-time fit", prec(ph["tau_fit"], 4), "yr/(m/s)",
         "A"],
    ]
    if a["penalised"]:
        physics_rows.append(["lambda_LT", "low-thrust delta-v penalty",
                             prec(C["dv_penalty"], 4), "x", "A"])

    vehicle_rows = [
        ["M_LEO", "%s payload to LEO" % esc(str(C["veh"]["name"])),
         prec(C["leo_cap"], 8), "kg", "K"],
        ["V_fair", "fairing volume (the model's default: the vehicle's row "
         "gives none)" if C.get("fairing_assumed") else "fairing volume",
         prec(C["fairing_m3"], 6), "m3",
         "A" if C.get("fairing_assumed") else "K"],
        ["c_veh", "launch price",
         prec(float(C["veh"]["usd_per_kg_to_leo"]), 8), "$/kg to LEO", "K"],
        ["I_sp", "%s specific impulse" % esc(str(C["pro"]["name"])),
         prec(C["isp"], 6), "s", "K"],
        ["rho_p", "propellant density",
         prec(float(C["pro"]["density_kg_per_L"]), 6), "kg/L", "K"],
        # ⚠️  WHICH STORAGE CLASS IS WHAT PRODUCES THE TANK FIGURE, and the
        # tank term is the one that decides methalox against krypton at
        # programme scale.  The page printed the derived kg/L and never said
        # which kind of vessel it came from.
        ["-", "storage class", esc(C["storage_class"]), "-", "K"],
        ["sigma_tank", "tank mass per litre",
         prec(float(C["pro"]["tank_kg_per_L"]), 10), "kg/L", "K"],
        # ⚠️  THE PRICE THE RUN PAID.  The nomenclature table is where a
        # reader looks up the symbol the cost lines multiply by, so it has to
        # be the same number those lines used -- not the Stage 3 table as it
        # stands today.  See `run_propellant_price`.
        ["c_prop", "propellant price",
         prec(C["prop_usd_per_kg"], 6), "$/kg", "K"],
    ]
    if a["electric"]:
        vehicle_rows += [
            ["eta", "thruster efficiency", prec(C["thruster_eff"], 4), "-",
             "K"],
            # 🚨  THE GATE, NOT A LABEL.  `thrust_scaling` is what decides
            # whether a thruster specific mass is a conventional article's or
            # a replicated device's, and a replicated one is a mass penalty
            # measured in tonnes.  The page carried the kg/N with no way to
            # tell which kind of thruster it belonged to.
            ["-", "thrust scaling", esc(C["thrust_scaling"]), "-", "K"],
            ["sigma_thr", "thruster specific mass",
             prec(C["thruster_kg_per_n"], 6), "kg/N", "K"],
            ["sigma_PPU", "power processing unit specific mass",
             prec(C["ppu_kg_per_kw"], 6), "kg/kW", "K"],
            ["t_burn", "thrust time the stage is sized for",
             prec(cfg.ep_target_thrust_yr, 4), "yr", "A"],
        ]
    vehicle_rows += [
        ["m_rig", "mining hardware mass", prec(cfg.mining_hardware_kg, 8),
         "kg", "A"],
        ["d_0", "return-vehicle dry mass floor",
         prec(cfg.return_vehicle_dry_kg, 6), "kg", "A"],
        ["f_str", "ore restraint per kg of payload",
         prec(cfg.return_structure_frac_of_payload, 4), "-", "A"],
        ["c_seal", "volatile containment per kg of water",
         prec(C["contain_per_kg"], 4), "-", "A"],
    ]
    if a["aero"]:
        vehicle_rows.append(["f_TPS", "heat shield per kg of arriving stack",
                             prec(C["tps_frac"], 4), "-", "A"])

    value_rows = [
        ["gamma", "mining rate per kg of rig",
         prec(cfg.mining_rate_kg_per_day_per_kg_rig, 4), "kg/day/kg", "A"],
        ["e_dig", "excavation energy", prec(C["dig_wh"], 6), "Wh/kg", "A"],
        ["e_ben", "beneficiation energy", prec(C["benef_wh"], 6), "Wh/kg",
         "A"],
        ["e_H2O", "bound-water liberation energy", prec(C["water_wh"], 6),
         "Wh/kg", "A"],
        ["w_1AU", "%s"
         % ("radioisotope specific power" if a["power"] == "rtg"
            else "array specific power, rated at 1 AU"),
         prec(C["plant_w_per_kg"] if a["power"] == "rtg" else C["w_1au"], 6),
         "W/kg", "K"],
        ["eps_rec", "separation recovery", prec(C["recovery"], 4), "-", "A"],
    ]
    if a["beneficiated"]:
        # ⚠️  THE SEARCHED RATIO, NOT THE ACHIEVED ONE.  `r` is the dial section
        # 9.1 turns; what the rig manages against it is `feed / payload` and
        # can be smaller, because the throughput ceiling clips the feed.  They
        # are different quantities and section 7 reports the other.
        value_rows.append(["r", "concentration ratio (searched, %s)"
                           % ref("searches"),
                           prec(out["ratio"], 10), "-", "D"])
    value_rows += [
        ["c_LEO", "launch price to LEO (%s)" % esc(C["pricing_label"]),
         prec(C["leo_usd_per_kg"], 8), "$/kg", "K"],
        ["u_c", "in-space utility, by commodity",
         ", ".join("%s %s" % (esc(n), prec(C["price_parts"][n]["utility"], 3))
                   for n, _f, _p in C["phases"]
                   if n in C["price_parts"]) or "-", "-", "A"],
        ["Cap_m", "absorption ceiling, by market",
         ", ".join("%s %s" % (esc(k), prec(v, 6))
                   for k, v in sorted(C["market_kg"].items())
                   if k in set(C["market_keys"].values())), "kg/yr", "A"],
    ]

    money_rows = [
        ["L_rig", "rig service life", prec(val("Mining rig service life"), 4),
         "yr", "A"],
        ["W_max", "rig maximum campaigns",
         prec(val("Mining rig maximum trips"), 4), "-", "A"],
        ["N, F, W", "units, fleet, campaigns per ship%s"
         % ((" (searched, %s)" % ref("searches")) if a["searched"]
            else " (pinned)"),
         "%d, %d, %d" % (P["n"], P["f"], P["w"]), "-",
         "D" if a["searched"] else "A"],
        ["c_rig", "mining rig recurring cost",
         prec(val("Mining payload recurring cost"), 8), "$/kg", "A"],
        ["c_cap", "%s recurring cost"
         % ("surface lander" if a["lander"] else "re-entry capsule"
            if a["to_earth"] else "berthing adapter"),
         prec(C["capsule_per_kg"], 8), "$/kg", "A"],
        ["c_W", "power plant", prec(C["plant_usd_per_w"], 8), "$/W", "A"],
        ["c_kW", "electric drive",
         prec(val("Electric propulsion system recurring cost"), 8), "$/kW",
         "A"],
        ["c_tank", "propellant tank",
         prec(val("Propellant tank recurring cost"), 8), "$/kg", "A"],
        ["c_ops", "mission operations", prec(val("Mission operations"), 10),
         "$/yr", "A"],
        ["NRE_bus", "spacecraft development, less %s overlap"
         % pct(cfg.nre_recurring_overlap_fraction, 0),
         prec(val("Spacecraft development (NRE)"), 10), "$", "A"],
        ["NRE_aut", "autonomous mining control",
         prec(val("Autonomous mining control & AI (NRE)"), 10), "$", "A"],
        ["zeta", "contingency reserve", prec(cfg.contingency_fraction, 4),
         "-", "A"],
        ["beta", "learning curve (Wright)",
         prec(cfg.learning_curve_rate, 4) if terms["learning"]
         else "not charged", "-", "A"],
        ["r_c", "cost of capital",
         prec(val("Cost of capital (WACC)"), 4) if terms["wacc"]
         else "not charged", "/yr", "A"],
    ]
    if terms["reliability"]:
        money_rows += [
            ["p_L", "launch success",
             prec(val("Launch vehicle reliability"), 4), "-", "K"],
            ["MTBF", "spacecraft mean time between failures",
             prec(val("Spacecraft mean time between failures"), 4), "yr",
             "A"],
            ["q_1, alpha, q_max",
             "mining first-of-kind failure, growth exponent, ceiling",
             "%s, %s, %s"
             % (prec(1.0 - val("Mining system first-of-kind success "
                               "probability"), 4),
                prec(val("Mining reliability growth exponent"), 4),
                prec(val("Mining system mature success probability"), 4)),
             "-", "A"],
        ]
    else:
        money_rows.append(["p_L, MTBF, q", "mission reliability",
                           "not charged", "-", "A"])
    money_rows.append(
        ["-", "launch insurance, third-party liability",
         "%s%% + %s $" % (prec(val("Launch insurance"), 4),
                          prec(val("Third-party liability insurance"), 8))
         if terms["insurance"] else "not charged", "-", "A"])

    legend = " &nbsp;&nbsp; ".join(
        "<strong>%s</strong> %s, %s" % (code, word, gloss)
        for code, word, gloss in CLASSES)
    return "".join([
        sec("nomenclature"),
        para("Everything below is an input. Every other number in this "
             "document is derived from these, on a page that shows the "
             "substitution, so a reader who disagrees with the answer can "
             "find out which line the disagreement starts in."),
        h(3, "The body"),
        symbols(body_rows),
        h(3, "Physics and orbital mechanics"),
        symbols(physics_rows),
        h(3, "Vehicle, propulsion and the rig"),
        symbols(vehicle_rows),
        h(3, "Processing, and what a kilogram is worth"),
        symbols(value_rows),
        h(3, "Programme, reliability and money"),
        symbols(money_rows),
        para('<span class="small">%s</span>' % legend),
    ])


def s_body(out):
    """Section 1: the rock.

    ⚠️  WHICH DIAMETER THIS BODY HAS DECIDES WHICH EQUATION BELONGS ON THE
    PAGE, AND IT ALSO DECIDES WHICH ALBEDO COLUMN IS POPULATED.  Stage 1 fills
    `diameter_km` on every row, deriving it from H and albedo where no
    measurement exists, so the model always reads a diameter and the
    provenance lives in `diameter_source` instead.  Where that says
    `measured`, `albedo_assumed_for_diameter` is NaN -- and the page used to
    print "nan" beside an H-and-albedo equation the body never went through.
    """
    B, C = out["B"], out["C"]
    source = str(B.get("diameter_source") or "unknown")
    from_h = diameter_from_h(B)
    # The assumed albedo is the one the derivation would have used; the
    # measured one is the only one a measured body has.  Neither is invented
    # here: both are catalog columns, and exactly one of them is populated.
    albedo = C["albedo"] if from_h else C.get("albedo_measured")
    pairs = [
        ("absolute magnitude H", fmt(C["H"], 3)),
        ("geometric albedo%s" % ("" if from_h else
                                 " (measured)" if albedo is not None
                                 else " (none on this row)"),
         fmt(albedo, 4)),
        ("diameter", fmt(B["d_km"], 6, "km")),
        ("diameter provenance", esc(source)),
        ("bulk density", fmt(C["rho"], 3, "g/cm3")),
    ]
    lead = ("This body has no measured diameter, so Stage 1 sized it from its "
            "absolute magnitude and an albedo, and that is the figure below."
            if from_h else
            "This body's diameter is %s, so no sizing from H is done and "
            "none is shown: the catalog figure is used as it stands."
            % diameter_provenance(B))
    steps = []
    if from_h:
        # 1329 / sqrt(p_V) is the standard photometric diameter relation, and
        # the two factors are shown separately because they pull in opposite
        # directions: a DARK body at a given brightness is a LARGE one, which
        # is most of why a taxonomy default for the albedo is load-bearing.
        steps += [
            ("D", "= 1329 / sqrt(p_V) * 10^(-H/5)", "km"),
            ("", "= 1329 / sqrt(%s) * 10^(-%s/5)"
             % (prec(albedo, 6), prec(C["H"], 6))),
            ("", "= 1329 / %s * %s"
             % (prec(math.sqrt(albedo), 12),
                prec(10.0 ** (-C["H"] / 5.0), 12))),
            ("", "= %s km" % prec(B["d_km"], 15)),
        ]
    steps += [
        ("r", "= D / 2 * 1000 = %s m" % prec(B["r_m"], 12)),
        ("r^3", "= %s m3" % prec(B["r3"], 12)),
        ("V", "= (4/3) * pi * r^3 = %s m3" % prec(B["vol"], 12)),
        ("m", "= rho * V = %s * %s"
         % (prec(C["rho"] * 1000.0, 6), prec(B["vol"], 12)), "kg/m3 x m3"),
        ("", "= %s kg" % prec(B["mass"], 15)),
        ("m_min", "= phi_min * m = %s * %s"
         % (prec(C["cfg"].max_mining_fraction, 4), prec(B["mass"], 15))),
        ("", "= %s kg" % prec(B["mineable"], 15),
         # phi_min is a dial, so this gloss derives from it rather than
         # asserting the depletion limit the default no longer imposes.
         ("the whole body is on the table, so this bound is the body itself"
          if C["cfg"].max_mining_fraction >= 1.0 else
          "one mission may not strip more than %s of the body"
          % pct(C["cfg"].max_mining_fraction, 0))),
    ]
    # 🚨  WHAT THE MASS RESTS ON, which is the question a mass with no
    # sensitivity beside it invites and does not answer.  Both inputs to the
    # H-and-albedo route are assumptions, and the exponents are not 1: D goes
    # as p_V^(-1/2) and m as D^3, so the albedo enters CUBED-over-two.  Saying
    # so costs three lines and is the difference between a reader trusting the
    # figure and a reader knowing how much to trust it.
    sensitivity = []
    if from_h:
        sensitivity = [
            ("D", "~ p_V^(-1/2)   and   m ~ D^3   =>   m ~ p_V^(-3/2)"),
            ("dm/m", "= -1.5 * dp_V/p_V",
             "a factor-2 albedo error moves the mass by 2^1.5 = %s"
             % prec(2.0 ** 1.5, 4)),
            ("m", "~ rho", "linear in the assumed density"),
        ]
    dug = out["M"]["feed"] + out["M"]["isru_feed"]
    return "".join([
        sec("body"),
        outputs([("m", prec(B["mass"], 12, "kg"), "mass of the body"),
                 ("m_min", prec(B["mineable"], 12, "kg"),
                  "what one mission may take")]),
        para(lead + " Mass follows from the diameter and the bulk density."
             + (" All of it is available to one mission, so what the rig "
                "actually takes is set by the dig rate, the capsule volume "
                "and the rocket equation rather than by the body."
                if C["cfg"].max_mining_fraction >= 1.0 else
                " Only a fraction of it is ever available: one mission may "
                "not strip-mine the asteroid.")),
        deriv(steps),
        kv(pairs),
        para("The rig moves %s kg of rock on this mission (%s), which "
             "is %s of what the body would allow, so the rock is not what "
             "bounds this target."
             % (fmt(dug, 0), ref("clock"), pct(dug / B["mineable"], 4))
             if B["mineable"] > 0 else ""),
        h(3, "What the mass rests on") if sensitivity else "",
        deriv(sensitivity) if sensitivity else "",
        para("Both inputs to that chain are assumptions rather than "
             "measurements. Neither reaches the answer here: the mass sets "
             "only the mineable bound, which does not bind, and the density "
             "reaches the return-capsule volume cap, which does not bind "
             "either (%s)." % ref("cascade")) if sensitivity else "",
    ])


def s_composition(out):
    """Section 2: what it is made of and what that is worth."""
    C = out["C"]
    span = C["frac_span"]
    rows = []
    for name, frac, price in sorted(C["phases"], key=lambda p: -p[2]):
        rows.append([esc(name), pct(frac, 3), usd(price, 2),
                     usd(frac * price, 2)])
    total = sum(f for _n, f, _p in C["phases"])
    rows.append(["<strong>total</strong>", "<strong>%s</strong>" % pct(total, 3),
                 "", "<strong>%s</strong>" % usd(C["bulk"], 2)])
    best = max(p[2] for p in C["phases"])
    out_html = [
        sec("composition"),
        para("The taxonomy fractions are priced separately rather than "
             "blended, because a concentrating mission chooses between them. "
             "Across the %d classes Module 1 gives fractions for they sum to "
             "between %s (%s) and %s (%s), never to one, and the remainder is "
             "carried as the bulk-silicate residual in the last row rather "
             "than discarded, which is why the table totals one."
             % (span["classes"], fmt(span["low"], 2),
                english([esc(n) for n in span["at_low"]]),
                fmt(span["high"], 2),
                english([esc(n) for n in span["at_high"]]))),
        table(["phase", "mass fraction", "$/kg", "contribution"], rows),
    ]
    # 🚨  WHERE THOSE PRICES COME FROM, because every one of them is a
    # DELIVERED price at this destination rather than a terrestrial quote, and
    # the page had been printing them with no way to reproduce any of them.
    # At an in-space destination a kilogram is worth its terrestrial price PLUS
    # the launch cost it avoids -- the plus is the point; replacing the
    # terrestrial price instead is a defect Stage 2 shipped once and it quietly
    # threw the material itself away.  The utility factors behind the "avoided"
    # half are engineering judgements and are the softest assumption in the
    # whole pipeline, which is the strongest reason to show the chain rather
    # than the answer.
    # 🚨  AN EMPTY CHAIN IS NOT A MISSING ONE.  `earth_surface`
    # has no chain at all (None) and avoids no launch; `leo` has an EMPTY one
    # ([]) because nothing flies above LEO, and it avoids the launch to LEO in
    # full.  `if C["legs"]` read those as the same thing, so a `leo` page
    # dropped the section explaining the largest term in every price it
    # printed.  Same defect as the derivation's, in the file next door.
    if C["legs"] is not None:
        out_html.append(h(3, "Why a kilogram is worth that much HERE"))
        out_html.append(para(
            "None of the prices above is a terrestrial quote. At an in-space "
            "destination a kilogram is worth what it fetches on Earth "
            "<strong>plus</strong> the launch cost it saves, and that saving "
            "is the cost of putting a kilogram there from Earth instead. "
            + ("The chain is walked backwards from the payload, stage by "
               "stage, because collapsing it into one burn throws away "
               "staging and overstates the destination."
               if C["legs"] else
               "Here the chain is empty, and that is the answer rather than "
               "the absence of one: this destination IS low Earth orbit, so "
               "nothing has to be flown above the launch vehicle and a "
               "kilogram mined out here avoids the whole LEO launch price.")))
        # 🚨  THE CHAIN, NOT THE ANSWER.  `p_L` is the largest term in every
        # delivered price in the table above, so a page that printed it as one
        # figure would be asking to be trusted about the number the rest of the
        # document leans on hardest.  Each leg is a stage, and a stage's dry
        # mass is not a rounding: the `d` term is what makes the second leg of
        # a two-leg chain cost more than the first.
        chain = C["chain"]
        steps = []
        for i, step in enumerate(chain["steps"], 1):
            if step["kind"] == "edl":
                steps += [
                    ("leg %d" % i, "entry, descent and landing"),
                    ("m", "= %s / %s = %s kg"
                     % (prec(step["before"], 12), prec(step["surviving"], 4),
                        prec(step["after"], 12)),
                     "%s of the arriving mass survives"
                     % pct(step["surviving"], 1)),
                ]
                if C.get("stage_hardware"):
                    steps.append(
                        ("H_%d" % i, "= (%s - %s) * %s = %s $/kg"
                         % (prec(step["after"], 12), prec(step["before"], 12),
                            prec(C["hw_rates"]["entry"], 8),
                            prec(step["hw"], 12)),
                         "the entry system this leg discards, at the TPS "
                         "rate"))
                continue
            steps += [
                ("leg %d" % i, "%s m/s on an Isp %s s stage, %s dry"
                 % (prec(step["dv"], 6), prec(step["isp"], 6),
                    pct(step["dry"], 0))),
                ("R", "= exp(dv / (I_sp g_0)) = exp(%s / %s) = %s"
                 % (prec(step["dv"], 6), prec(step["ve"], 12),
                    prec(step["R"], 12))),
                ("d", "= delta (R - 1) / (1 - delta R) = %s"
                 % prec(step["d"], 12), "stage dry mass per kg of payload"),
                ("m0", "= R (1 + d) = %s * %s = %s"
                 % (prec(step["R"], 12), prec(1.0 + step["d"], 12),
                    prec(step["m0"], 12)), "kg at the start of the leg"),
            ]
            if C.get("stage_hardware"):
                steps.append(
                    ("H_%d" % i, "= %s * (%s * %s + %s * %s) = %s $/kg"
                     % (prec(step["before"], 12), prec(step["stage_dry"], 12),
                        prec(C["hw_rates"]["stage"][step["dry"]], 8),
                        prec(step["propellant"], 12),
                        prec(C["hw_rates"]["propellant"], 8),
                        prec(step["hw"], 12)),
                     "building the stage this leg expends, and its "
                     "propellant: stage dry mass is m0 / R - 1"))
        steps += [
            ("m_LEO", "= %s kg in LEO per kg delivered"
             % prec(chain["kg_in_leo"], 12)),
        ]
        if C.get("stage_hardware"):
            steps += [
                ("P_L", "= c_LEO * m_LEO + sum H = %s * %s + %s"
                 % (prec(C["leo_usd_per_kg"], 8),
                    prec(chain["kg_in_leo"], 12),
                    prec(chain["hardware_usd_per_kg"], 12))),
            ]
        else:
            steps += [
                ("P_L", "= c_LEO * m_LEO = %s * %s"
                 % (prec(C["leo_usd_per_kg"], 8),
                    prec(chain["kg_in_leo"], 12))),
            ]
        steps += [
            ("", "= %s $/kg" % prec(chain["usd_per_kg"], 12),
             "the launch cost a kilogram mined out there avoids"),
        ]
        out_html.append(deriv(steps))
        # Every delivered price in the phase table, with the three terms that
        # produced it.  Stage 2 writes all three as columns, and the page had
        # been printing only their result -- which is also the only place the
        # "plus, not instead of" rule is visible: a terrestrial quote is ADDED
        # to the launch cost avoided, and replacing it instead is a defect
        # Stage 2 shipped once and quietly threw the material away.
        parts = C["price_parts"]
        price_rows = []
        for name, _frac, price in sorted(C["phases"], key=lambda p: -p[2]):
            part = parts.get(name)
            if part is None or name == "nickel-iron":
                continue
            if part["route"].startswith("used"):
                # 🚨  THE DERIVED P_L, NOT MODULE 2's.  This line printed
                # `C["p_l"]` -- the pipeline's own answer -- three paragraphs
                # below the chain that derives the same quantity here, so one
                # page carried two statements of its largest price term and
                # showed the borrowed one.  They agree because `build` asserts
                # it, which is a check and not a licence to print the other
                # side of it.  See `model_borrows`.
                shown = ("%s + %s * %s - %s"
                         % (prec(part["terrestrial"], 8),
                            prec(part["utility"], 4),
                            prec(chain["usd_per_kg"], 12),
                            prec(part["refining"], 10)))
            else:
                shown = ("max(0, %s - %s)"
                         % (prec(part["terrestrial"], 8),
                            prec(part["downleg"], 12)))
            price_rows.append([esc(name), esc(part["route"]), shown,
                               usd(price, 6)])
        if price_rows:
            out_html.append(h(3, "Every price in the table above, term by "
                              "term"))
            out_html.append(para(
                "A commodity <strong>used</strong> at the destination is "
                "worth its terrestrial quote <strong>plus</strong> its "
                "utility share of the launch cost avoided, less what refining "
                "it on site costs. One <strong>shipped home</strong> is worth "
                "its terrestrial quote less the downleg, floored at zero. "
                "Which of the two happened is a Stage 2 column, not a "
                "judgement made here."))
            out_html.append(eq("P_c = p_terrestrial + u_c * P_L - c_refine "
                               "&nbsp;&nbsp; (used in space)"))
            out_html.append(table(
                ["phase", "route", "substitution", "$/kg"], price_rows))
        # ⚠️  THE LOWER-BOUND CAVEAT BELONGS TO THE TWO SURFACES, NOT TO
        # EVERY DESTINATION, and attaching it to a depot would be borrowing a
        # warning that is not about this mission.  What IS true everywhere is
        # the utility factors, so that half is unconditional.
        surface = C["arch"].get("needs_lander")
        out_html.append(note(
            "warn",
            ("This is a <strong>marginal-transport lower bound</strong>: no "
             "programme overhead, no development cost, and an industrial "
             "launch cadence that does not exist yet. Real lunar delivery "
             "today runs orders of magnitude above it. " if surface else "")
            + "The utility factors that decide how much of this saving each "
              "commodity captures are engineering judgements rather than "
              "measurements, and they are the softest assumption in the "
              "pipeline. Treat them as a dial."))
    else:
        out_html.append(h(3, "Why a kilogram is worth that much HERE"))
        out_html.append(para(
            "The cargo comes home, so there is no launch cost avoided and no "
            "delivery ladder: a kilogram is worth its terrestrial price, less "
            "what it costs to bring it down through the atmosphere. That "
            "downleg is why the cheaper platinum-group metals can arrive worth "
            "nothing at all."))
    if C["yields"]:
        # 🚨  EVERY OTHER PRICE IN THIS TABLE IS A ROW LOOKUP.  `nickel-iron`
        # is an ALLOY, so its price is the yield-weighted sum of the elements
        # in it, with this body's own platinum-group enrichment applied to the
        # rare metals -- which is why two bodies with identical metal fractions
        # need not carry the same value of metal.
        yield_rows = []
        for element, frac in sorted(C["yields"].items(),
                                    key=lambda kv2: -float(kv2[1])):
            price = C["element_price"].get(element)
            if price is None:
                continue
            rare = element in C["rare_metals"]
            share = float(frac) * (C["kappa"] if rare else 1.0)
            yield_rows.append([esc(element), fmt(float(frac) * 1e6, 1),
                               ("x " + fmt(C["kappa"], 2)) if rare else "-",
                               usd(float(price), 2),
                               usd(share * float(price), 2)])
        yield_rows.append(["<strong>nickel-iron, blended</strong>", "", "", "",
                           "<strong>%s</strong>" % usd(C["alloy"], 2)])
        out_html.append(h(3, "What the metal is worth, element by element"))
        out_html.append(para(
            "Every other price above is a row in the mineral catalog. "
            "<strong>Nickel-iron is not.</strong> It is an alloy, so its price "
            "is the yield-weighted sum of its elements, with this body's "
            "platinum-group enrichment of %s applied to the rare metals. That "
            "enrichment follows the taxonomy, which is why two bodies with the "
            "same metal fraction need not carry metal of the same value."
            % fmt(C["kappa"], 2)))
        out_html.append(table(["element", "yield (ppm of alloy)", "enrichment",
                               "$/kg", "contribution $/kg"], yield_rows))
        # 🚨  A ZERO HERE IS A RESULT, NOT A MISSING NUMBER, and it is worth
        # saying so on the page: a reader who takes it for a data error will
        # go looking for a bug that is not there.  An element with no in-space
        # market is worth its terrestrial price MINUS the cost of flying it
        # down, and for the cheaper platinum-group metals that difference is
        # negative, so the delivered price floors at zero.  The same downleg
        # leaves rhodium and iridium worth six figures.
        dead = [n for n, p2 in C["element_price"].items()
                if n in C["yields"] and float(p2 or 0.0) <= 0.0]
        if dead:
            out_html.append(note(
                "warn",
                "%s %s at <strong>exactly zero</strong> here, and that is a "
                "result rather than a gap in the data: an element with no "
                "in-space market is worth its terrestrial price less the cost "
                "of flying it down, and for the cheaper platinum-group metals "
                "that difference is negative, so the delivered price floors "
                "at zero. The same downleg leaves rhodium and iridium worth "
                "six figures a kilogram."
                % (english([esc(n) for n in sorted(dead)]).capitalize(),
                   "prices" if len(dead) == 1 else "price")))
    if C["beneficiated"]:
        out_html.append(para(
            "The best phase present is worth %s per kilogram, and that is the "
            "<strong>purity bound</strong>: concentrating rejects gangue, it "
            "does not transmute, so no amount of processing can lift the "
            "delivered value above it." % usd(best, 2)))
    else:
        out_html.append(para(
            "This mission does not concentrate, so the hold is the body's own "
            "composition and the bulk figure of %s per kilogram is what it "
            "delivers. The purity bound does not apply: there is nothing to "
            "bind." % usd(C["bulk"], 2)))
    return "".join(out_html)


def capture_block(C, DV, chosen):
    """The arrival burn written out, where this geometry can write it out.

    ⚠️  TWO LEG FAMILIES, AND THE REST GET THE BURN TABLE ALONE.  Capturing
    into a depot only has to BIND an ellipse, and the burn takes the Oberth
    benefit deep at perigee; capturing into LEO has to kill the escape velocity
    as well as the excess, which is the departure burn run backwards.  Those
    two are one expression each and are worth showing.  A GEO arrival prices
    two competing geometries and a Mars one is a separate heliocentric
    transfer, so for those the burn table above is the honest statement and an
    invented substitution would not be.
    """
    ph = C["physics"]
    leg = C["return_leg"]
    if leg in ("ret_cislunar_prop", "ret_lunar_surface_prop"):
        rows = [
            ("a_ell", "= (r_LEO + R_M) / 2 = (%s + %s) / 2 = %s km"
             % (prec(ph["r_leo"], 8), prec(ph["r_moon"], 8),
                prec(chosen["a_ell"], 12)),
             "capture BINDS the orbit; it does not circularise"),
            ("v_ell", "= sqrt(mu_E (2/r_LEO - 1/a_ell)) = sqrt(%s * %s)"
             % (prec(ph["mu_earth"], 12),
                prec(2.0 / ph["r_leo"] - 1.0 / chosen["a_ell"], 12))),
            ("", "= %s km/s" % prec(chosen["v_ell"], 12)),
            ("dv_cap", "= (v_hyp - v_ell) + dv_NRHO = (%s - %s) + %s"
             % (prec(chosen["v_hyp"], 12), prec(chosen["v_ell"], 12),
                prec(ph["dv_nrho"], 4))),
            ("", "= %s km/s" % prec(chosen["cap"], 12)),
        ]
        if leg == "ret_lunar_surface_prop":
            rows.append(("dv_land",
                         "= %s km/s"
                         % prec(ph["dv_nrho_to_lunar_surface"], 6),
                         "NRHO to low lunar orbit to the ground, all "
                         "propulsive: there is no air"))
    elif leg in ("ret_leo_prop", "ret_earth_surface_prop"):
        rows = [
            ("dv_cap", "= v_hyp - v_LEO = %s - %s = %s km/s"
             % (prec(chosen["v_hyp"], 12), prec(chosen["v_leo"], 12),
                prec(chosen["leo_capture"], 12)),
             "the deepest Earth arrival: it kills the escape velocity too"),
        ]
        if leg == "ret_earth_surface_prop":
            rows.append(("dv_deorbit", "= %s km/s"
                         % prec(ph["dv_leo_deorbit"], 4),
                         "the capsule still has to come down"))
    else:
        return ""
    return deriv(rows)


def s_transfer(out):
    """Section 3: the patched-conic transfer and the launch window."""
    DV, C = out["DV"], out["C"]
    a = architecture(out)
    # Only the CHOSEN apsis's legs are needed; the other one contributes just
    # its round-trip total, for the sentence that says why it lost.
    chosen = DV["aph"] if a["apsis"] == "aphelion" else DV["peri"]
    chosen_r = DV["aph_round"] if a["apsis"] == "aphelion" else DV["peri_round"]
    other_r = DV["peri_round"] if a["apsis"] == "aphelion" else DV["aph_round"]
    # ⚠️  ONLY WHAT THE SUBSTITUTIONS ABOVE DO NOT ALREADY SHOW.  Every
    # orbital element, both apsides, both burns and both legs are now derived
    # line by line, so repeating them here would be a rounded second copy of a
    # number the reader has just watched being made.
    rows = [
        ("orbital period", fmt(DV["t_ast"], 4, "yr")),
        ("synodic period", fmt(DV["synodic"], 4, "yr")),
        ("expected window wait", fmt(DV["window_wait"], 4, "yr")),
    ]
    ph = C["physics"]
    # 🚨  CANONICAL UNITS THROUGHOUT 2.1 TO 2.4: r_Earth = 1, v_Earth = 1.
    # The heliocentric half of this transfer is dimensionless and only the last
    # line of each block multiplies by v_E to reach km/s, which is exactly how
    # `_legs` is written.  Restoring units line by line would make every
    # intermediate a different number from the one the model holds.
    geometry = [
        ("Q", "= a (1 + e) = %s * (1 + %s) = %s AU"
         % (prec(C["a_au"], 12), prec(C["e"], 12), prec(DV["Q_au"], 12)),
         "aphelion"),
        ("q", "= a (1 - e) = %s AU" % prec(DV["q_au"], 12), "perihelion"),
        ("r_t", "= %s AU" % prec(DV["r_target"], 12),
         "the apsis this transfer meets the target at"),
        ("a_t", "= (1 + r_t) / 2 = %s AU" % prec(chosen["a_t"], 12),
         "transfer ellipse, 1 AU to r_t"),
    ]
    departure = [
        ("v_t", "= sqrt(2 - 1/a_t) = sqrt(2 - %s)"
         % prec(1.0 / chosen["a_t"], 12)),
        ("", "= %s" % prec(chosen["v_t"], 12),
         "speed on the transfer ellipse at Earth's orbit"),
        ("cos i", "= cos(%s deg) = %s"
         % (prec(C["inc"], 8), prec(chosen["cos_i"], 12)),
         "the plane change, taken in the same burn"),
        ("v_inf^2", "= v_t^2 + 1 - 2 v_t cos i", "law of cosines against "
         "Earth's own velocity"),
        ("", "= %s + 1 - %s = %s"
         % (prec(chosen["v_t"] ** 2, 12),
            prec(2.0 * chosen["v_t"] * chosen["cos_i"], 12),
            prec(chosen["v_inf_sq"], 12))),
        ("v_inf", "= sqrt(%s) * v_E = %s * %s"
         % (prec(chosen["v_inf_sq"], 12), prec(chosen["v_inf_canon"], 12),
            prec(ph["v_earth"], 6))),
        ("", "= %s km/s" % prec(chosen["v_inf"], 12)),
        ("v_LEO", "= sqrt(mu_E / r_LEO) = sqrt(%s / %s) = %s km/s"
         % (prec(ph["mu_earth"], 12), prec(ph["r_leo"], 8),
            prec(chosen["v_leo"], 12))),
        ("v_esc", "= sqrt(2) v_LEO = %s km/s" % prec(chosen["v_esc"], 12)),
        ("v_hyp", "= sqrt(v_esc^2 + v_inf^2) = sqrt(%s + %s)"
         % (prec(chosen["v_esc"] ** 2, 12), prec(chosen["v_inf"] ** 2, 12))),
        ("", "= %s km/s" % prec(chosen["v_hyp"], 12)),
        ("dv_dep", "= v_hyp - v_LEO = %s - %s = %s km/s"
         % (prec(chosen["v_hyp"], 12), prec(chosen["v_leo"], 12),
            prec(chosen["depart"], 12)),
         "the departure burn, from the parking orbit"),
    ]
    match = [
        ("v_ast", "= sqrt(2/r_t - 1/a) = sqrt(%s - %s) = %s"
         % (prec(2.0 / DV["r_target"], 12), prec(1.0 / C["a_au"], 12),
            prec(chosen["v_ast"], 12)), "the target, at r_t"),
        ("v_tr", "= sqrt(2/r_t - 1/a_t) = sqrt(%s - %s) = %s"
         % (prec(2.0 / DV["r_target"], 12), prec(1.0 / chosen["a_t"], 12),
            prec(chosen["v_tr"], 12)), "the spacecraft, at r_t"),
        ("dv_match", "= |v_ast - v_tr| * v_E = %s * %s"
         % (prec(abs(chosen["v_ast"] - chosen["v_tr"]), 12),
            prec(ph["v_earth"], 6))),
        ("", "= %s km/s" % prec(chosen["match"], 12)),
        ("dv_out", "= dv_dep + dv_match = %s km/s"
         % prec(chosen["out"], 12), "before the floor and the penalty"),
    ]
    html_out = [
        sec("transfer"),
        outputs([("dv_out", prec(DV["dv_out"], 12, "m/s"),
                  "outbound, floored and penalised"),
                 ("dv_ret", prec(DV["dv_ret"], 12, "m/s"),
                  "return, floored and penalised")]),
        para("The transfer is a patched conic: an ellipse from Earth's orbit "
             "to the apsis the search chose, a burn to match the target's "
             "velocity there, and a capture at the destination."),
        note("key",
             "<strong>Which apsis the transfer meets the target at is a "
             "search, not a rule.</strong> An aphelion rendezvous is a slow "
             "transfer with a cheap match burn and an expensive departure; a "
             "perihelion rendezvous is the reverse, and which wins depends on "
             "a and e together. Here %s costs %s km/s round trip against %s "
             "for %s, so the search took it."
             % (esc(a["apsis"]), prec(chosen_r, 8), prec(other_r, 8),
                "perihelion" if a["apsis"] == "aphelion" else "aphelion")
             + " That is a factor of %s, and it is priced per asteroid AND "
               "per destination, because the outbound leg is the same either "
               "way and the return is not."
               % prec(other_r / chosen_r if chosen_r else 0.0, 4)),
        h(3, "The transfer geometry"),
        deriv(geometry),
        h(3, "Departure: the hyperbolic excess, and the burn that buys it"),
        deriv(departure),
        h(3, "Matching the target at the apsis"),
        deriv(match),
        kv(rows),
        h(3, "The return, burn by burn"),
        # 🚨  WHAT HAPPENS ON ARRIVAL IS THE WHOLE DIFFERENCE BETWEEN
        # DESTINATIONS, and it used to be one row here reading the cislunar
        # capture whatever the row had flown.  The breakdown comes out of the
        # leg set beside the physics that produced it; assembling it here would
        # be a second opinion about the arithmetic.
        para("The outbound half is the same wherever the cargo is going. What "
             "differs is entirely the arrival, and it differs by more than "
             "intuition suggests. This mission flies %s (<code>%s</code>)."
             % (LEG_LABEL.get(C["return_leg"], "the leg below"),
                esc(C["return_leg"]))),
        table(["burn", "km/s"],
              [[esc(label), fmt(value, 4)]
               for label, value in chosen["arrival"][C["return_leg"]]]
              + [["<strong>total, before the floor and the penalty</strong>",
                  "<strong>%s</strong>" % fmt(chosen[C["return_leg"]], 4)]]),
        capture_block(C, DV, chosen),
        deriv([
            ("dv_out", "= min(max(%s, %s), %s) * %s = %s m/s"
             % (prec(DV["raw_out"], 10), prec(DV["floor_out"], 6),
                prec(DV["ceiling"], 8), prec(DV["penalty"], 4),
                prec(DV["dv_out"], 12)),
             "floored%s" % (", then penalised" if DV["penalty"] != 1.0
                            else "")),
            ("dv_ret", "= min(max(%s, %s), %s) * %s = %s m/s"
             % (prec(DV["raw_ret"], 10), prec(DV["floor_ret"], 6),
                prec(DV["ceiling"], 8), prec(DV["penalty"], 4),
                prec(DV["dv_ret"], 12))),
        ]),
        note("key",
             "<strong>The floors come before the low-thrust penalty.</strong> "
             "The model floors the raw legs at %s m/s outbound and %s m/s on "
             "the return and only then multiplies by the electric penalty, so "
             "a body cheap enough to arrive at pays the floor times the "
             "penalty rather than its own value times the penalty. Here the "
             "outbound leg %s and the return leg %s."
             % (fmt(DV["floor_out"], 0), fmt(DV["floor_ret"], 0),
                "is floored" if DV["raw_out"] < DV["floor_out"]
                else "clears its floor",
                "is floored" if DV["raw_ret"] < DV["floor_ret"]
                else "clears its floor")),
    ]
    if a["aero"]:
        html_out.append(note(
            "ok", "The return is <strong>aerocaptured</strong>: the "
            "destination has an atmosphere, so the arrival hyperbola is bled "
            "off against it rather than burned off, at the cost of a heat "
            "shield that is hauled out and pushed back."))
    else:
        html_out.append(note(
            "ok", "The return is <strong>propulsive</strong>. Either the "
            "destination has no atmosphere to brake against, or the search "
            "priced the heat shield and declined it."))
    if C["cfg"].model_launch_windows:
        html_out.append(para(
            "Departure needs the target and the destination phased, and those "
            "alignments recur at the synodic period, so the expected wait "
            "after mining completes is half of one: %s. Counterintuitively "
            "this punishes near-Earth bodies hardest, because their periods "
            "are near Earth's and the windows are therefore years apart."
            % fmt(DV["window_wait"], 3, "yr")))
    return "".join(html_out)


def s_cascade(out):
    """Section 4: the mass cascade and the fixed point that closes it."""
    M, C = out["M"], out["C"]
    a = architecture(out)
    cas = M["cascade"]
    pass_rows = [[p["n"], fmt(p["hw_in"], 1), fmt(p["f_used"], 5),
                  fmt(p["m_pay"], 1), fmt(p["ep"], 1), fmt(p["plant"], 1),
                  fmt(p["feed"], 0), fmt(p["dig"], 4)]
                 for p in M["passes"]]
    ledger = [
        ("mining rig", fmt(C["cfg"].mining_hardware_kg, 1, "kg")),
        ("power system", fmt(M["plant"], 1, "kg")),
        ("electric stage", fmt(M["ep"]["mass"], 1, "kg")),
        ("<strong>hardware total</strong>",
         "<strong>%s</strong>" % fmt(M["hw"], 1, "kg")),
    ]
    masses = [
        ("payload returned", fmt(M["m_pay"], 1, "kg")),
        ("return vehicle dry", fmt(M["m_dry"], 1, "kg")),
        ("volatile containment", fmt(M["m_containment"], 1, "kg")),
        ("heat shield", fmt(M["m_tps"], 1, "kg")),
        ("return propellant%s" % (" (made on site)" if a["isru"] else ""),
         fmt(M["m_rprop"], 1, "kg")),
        ("return tankage", fmt(M["m_tank_ret"], 1, "kg")),
        ("mass at the asteroid", fmt(M["m_at"], 1, "kg")),
        ("outbound propellant", fmt(M["m_oprop"], 1, "kg")),
        ("outbound tankage", fmt(M["m_tank_out"], 1, "kg")),
        ("<strong>launch mass</strong>",
         "<strong>%s</strong>" % fmt(M["m_launch"], 1, "kg")),
        ("vehicle capacity to LEO", fmt(C["leo_cap"], 1, "kg")),
    ]
    R, DV = M["R"], out["DV"]
    ve_note = ("effective, inflated %s for boil-off" % sig(M["boiloff_factor"], 6)
               if M["boiloff_factor"] != 1.0 else "")
    constants = [
        ("t", "= sigma_tank / rho_p = %s / %s = %s"
         % (prec(float(C["pro"]["tank_kg_per_L"]), 10),
            prec(float(C["pro"]["density_kg_per_L"]), 6), prec(R["t"], 15)),
         "tank mass per kg of propellant"),
        ("v_e", "= I_sp g_0 = %s * %s = %s m/s"
         % (prec(C["isp"], 6), prec(C["physics"]["g0"], 8), prec(C["ve"], 12))),
        ("R_out", "= exp(dv_out / v_e) = exp(%s / %s) = %s"
         % (prec(DV["dv_out"], 12), prec(C["ve"], 12), prec(R["R_out"], 15))),
        ("R_ret", "= exp(dv_ret / v_e) = exp(%s / %s) = %s"
         % (prec(M["dv_ret_eff"], 12), prec(C["ve"], 12), prec(R["R_ret"], 15)),
         ve_note),
        ("k_out", "= 1 / (1 - t (R_out - 1)) = 1 / (1 - %s * %s) = %s"
         % (prec(R["t"], 12), prec(R["R_out"] - 1.0, 12),
            prec(R["k_out"], 15)), "the tank, folded into the mass ratio"),
        ("k_ret", "= 1 / (1 - t (R_ret - 1)) = 1 / (1 - %s * %s) = %s"
         % (prec(R["t"], 12), prec(R["R_ret"] - 1.0, 12),
            prec(R["k_ret"], 15))),
        ("budget", "= M_LEO / (k_out R_out) = %s / %s = %s kg"
         % (prec(C["leo_cap"], 8), prec(R["k_out"] * R["R_out"], 12),
            prec(R["budget"], 15)),
         "what may arrive at the asteroid, ore excluded"),
    ]
    # 🚨  `coef` IS THE WHOLE DIFFERENCE BETWEEN THE TWO FORMS, AND IT IS
    # ONE FACTOR OF R_ret.  Carrying the return propellant up from Earth pushes
    # it through the outbound burn as dead mass; making it at the asteroid
    # means it never rides the outbound leg at all.  Printing the wrong one
    # would be a worked calculation of a mission this is not.
    closed_form = [
        ("coef", "= k_ret * s_TPS%s = %s"
         % ("" if a["isru"] else " * R_ret", prec(cas["coef"], 15)),
         "the returning stack's multiplier%s"
         % ("; the propellant is made on site, so no R_ret" if a["isru"]
            else "")),
        ("f", "= f_str + c_seal_frac = %s + %s = %s"
         % (prec(C["cfg"].return_structure_frac_of_payload, 4),
            prec(cas["struct_frac"]
                 - C["cfg"].return_structure_frac_of_payload, 12),
            prec(cas["struct_frac"], 15)),
         "ore restraint plus the sealed hold, at THIS pass's water"),
        ("denom", "= coef (1 + f) - 1 = %s * %s - 1 = %s"
         % (prec(cas["coef"], 12), prec(1.0 + cas["struct_frac"], 12),
            prec(cas["denom"], 15))),
        ("m_hw", "= %s kg" % prec(M["hw_solved"], 15),
         "the hardware the solve was run AT, i.e. the previous pass's"),
        ("bracket", "= budget - m_hw - coef * d_0 = %s - %s - %s"
         % (prec(R["budget"], 12), prec(M["hw_solved"], 12),
            prec(cas["coef"] * cas["d0"], 12))),
        ("", "= %s kg" % prec(cas["bracket"], 15)),
        ("m_pay", "= bracket / denom = %s / %s"
         % (prec(cas["bracket"], 15), prec(cas["denom"], 15))),
        ("", "= %s kg" % prec(cas["m_pay"], 15), "the closed form's payload"),
    ]
    caps_rows = [
        ["mineable", "%s of the body" % pct(C["cfg"].max_mining_fraction, 0),
         fmt(out["B"]["mineable"], 0)],
        ["throughput", "%s kg/yr over %s yr, on the feed"
         % (fmt(C["rate_kg_yr"], 0), fmt(C["cfg"].max_mining_duration_yr, 1)),
         fmt(M["throughput"], 0)],
        ["volume", "%s of the fairing at %s kg/L"
         % (pct(0.25, 0), fmt(C["rho"], 2)), fmt(M["vol_cap"], 0)],
        ["rocket equation", "the closed form above", fmt(cas["m_pay"], 0)],
    ]
    binds = min(caps_rows, key=lambda r: float(r[2].replace(",", "")))
    for r in caps_rows:
        if r is binds:
            r[0] = "<strong>%s</strong>" % r[0]
            r[2] = "<strong>%s &nbsp;&lt;-- binds</strong>" % r[2]
    feed_terms = []
    if a["beneficiated"]:
        feed_terms += [
            ("feed", "= min(m_pay * r, throughput, mineable)"),
            ("", "= min(%s * %s, %s, %s)"
             % (prec(M["m_pay"], 12), prec(out["ratio"], 12),
                prec(M["throughput"], 12), prec(out["B"]["mineable"], 12))),
            ("", "= %s kg" % prec(M["feed"], 15)),
            ("r", "= feed / m_pay = %s" % prec(M["ratio"], 15),
             "achieved, against the %s the sweep chose"
             % prec(out["ratio"], 10)),
        ]
    feed_terms += [
        ("water", "= %s kg" % prec(M["water"], 15),
         "%s of the hold; see %s" % (pct(
             M["water"] / M["m_pay"] if M["m_pay"] else 0.0, 4), ref("hold"))),
        ("c_frac", "= c_seal * min(1, water / m_pay) = %s * %s = %s"
         % (prec(C["contain_per_kg"], 4),
            prec(min(1.0, M["water"] / M["m_pay"]) if M["m_pay"] else 0.0, 12),
            prec(M["c_frac"], 15))),
        ("m_seal", "= c_frac * m_pay = %s kg" % prec(M["m_containment"], 15)),
    ]
    # 🚨  THE ONE IDENTITY ON THE PAGE THAT CHECKS THE CASCADE AGAINST
    # ITSELF, AND IT IS THE `m_at` ONE RATHER THAN THE HARDWARE ONE.  Every
    # launch mass in this model is `m_at * k_out * R_out` -- the outbound
    # propellant and its tank are both proportional to what leaves LEO -- so
    # the vehicle's spare capacity is exactly the shortfall against `budget`
    # pushed back out through the same factor.  That holds whatever caused the
    # shortfall.
    #
    # ⚠️  THE HARDWARE DIFFERENCE ALONE DOES NOT CLOSE IT, and writing that
    # down and printing it was a mistake made here first: the loop settles the
    # containment fraction as well as the hardware, so `f` moves between the
    # solve and the flown stack too, and on this body the hardware term alone
    # over-explains the margin by a factor of four. Two terms move, so the
    # identity has to be stated on the quantity they both feed.
    slack = C["leo_cap"] - M["m_launch"]
    closure = [
        ("m_dry", "= d_0 + f m_pay = %s + %s * %s = %s kg"
         % (prec(C["cfg"].return_vehicle_dry_kg, 6), prec(M["f_eff"], 12),
            prec(M["m_pay"], 12), prec(M["m_dry"], 12))),
        ("m_after", "= k_ret (1 + f_TPS) (m_pay (1 + f) + d_0) = %s kg"
         % prec(M["m_after"], 12), "the returning stack, post-burn"),
        ("m_rprop", "= m_after (R_ret - 1) = %s * %s = %s kg"
         % (prec(M["m_after"], 12), prec(R["R_ret"] - 1.0, 12),
            prec(M["m_rprop"], 12))),
        ("m_tank_ret", "= t * m_rprop = %s kg" % prec(M["m_tank_ret"], 12)),
        ("m_at", "= m_hw + m_dry + m_TPS + m_tank_ret%s = %s kg"
         % ("" if a["isru"] else " + m_rprop", prec(M["m_at"], 12)),
         "at the asteroid, before the ore is loaded"),
        ("m_oprop", "= m_at k_out (R_out - 1) = %s kg"
         % prec(M["m_oprop"], 12)),
        ("m_tank_out", "= t * m_oprop = %s kg" % prec(M["m_tank_out"], 12)),
        ("m_launch", "= m_at + m_tank_out + m_oprop = %s kg"
         % prec(M["m_launch"], 15),
         "against M_LEO = %s kg" % prec(C["leo_cap"], 8)),
        ("budget - m_at", "= %s - %s = %s kg"
         % (prec(R["budget"], 12), prec(M["m_at"], 12),
            prec(R["budget"] - M["m_at"], 12)),
         "the solve aimed at `budget`; the flown stack lands under it"),
        ("", "x k_out R_out = %s * %s = %s kg"
         % (prec(R["budget"] - M["m_at"], 12),
            prec(R["k_out"] * R["R_out"], 12),
            prec((R["budget"] - M["m_at"]) * R["k_out"] * R["R_out"], 12))),
        ("M_LEO - m_launch", "= %s - %s = %s kg"
         % (prec(C["leo_cap"], 8), prec(M["m_launch"], 12), prec(slack, 12)),
         "the same number, which is what closes the cascade"),
        ("m_hw", "solved %s, settled %s, a difference of %s kg"
         % (prec(M["hw_solved"], 12), prec(M["hw"], 12),
            prec(M["hw_solved"] - M["hw"], 12)),
         "one of the two terms that moved"),
        ("f", "solved %s, settled %s"
         % (prec(cas["struct_frac"], 12), prec(M["f_eff"], 12)),
         "the other; the seal is settled on the flown payload"),
    ]
    html_out = [
        sec("cascade"),
        outputs([("m_pay", prec(M["m_pay"], 12, "kg"), "returned payload"),
                 ("m_feed", prec(M["feed"], 12, "kg"), "dug and processed"),
                 ("m_launch", prec(M["m_launch"], 12, "kg"),
                  "against a vehicle capacity of %s kg"
                  % prec(C["leo_cap"], 8))]),
        para("Payload is solved for, not specified. It is bounded by the "
             "rocket equation against the vehicle's capacity to LEO, and the "
             "solve is a fixed point because the payload sets the feed, the "
             "feed sets the dig time and the power draw, the draw sets the "
             "array mass, and the array comes out of the payload budget."),
        # 🚨  TWO FORMS, AND THE DIFFERENCE IS ONE FACTOR OF R_ret.  Carrying
        # the return propellant up from Earth means it is pushed through the
        # outbound burn as dead mass; making it at the asteroid means it never
        # rides the outbound leg at all.  Showing the wrong one would be a
        # worked calculation of a mission this is not.
        eq("coef = k_ret * s_TPS%s &nbsp;&nbsp;&nbsp; "
           "m_pay = (M_LEO / (k_out R_out) - m_hw - coef * d0) "
           "/ (coef (1 + f) - 1)"
           % ("" if a["isru"] else " * R_ret")),
        table(["pass", "hardware in (kg)", "structure frac", "payload (kg)",
               "EP (kg)", "plant (kg)", "feed (kg)", "dig (yr)"], pass_rows),
        note("key",
             "<strong>The cascade is not re-solved once the loop "
             "converges.</strong> The payload carried forward is the last one "
             "solved INSIDE the loop, at the PREVIOUS pass's hardware, and "
             "that is the model's own behaviour rather than an approximation "
             "made here. It is also why the launch mass comes out a little "
             "under the vehicle instead of exactly on it, which the last "
             "block in this section accounts for to the kilogram."),
        h(3, "The propellant constants"),
        deriv(constants),
        h(3, "That last pass, term by term"),
        deriv(closed_form),
        h(3, "The feed, the water in the hold and the seal"),
        deriv(feed_terms),
        h(3, "The hardware ledger"),
        para("Every kilogram in the cascade has a price in the cost model and "
             "every kilogram the cost model pays for is flown. That identity "
             "is the first thing to check when anything here looks wrong."),
        kv(ledger),
        h(3, "The stack, from the payload outwards"),
        kv(masses),
        h(3, "The stack rebuilt on the settled hardware, and what closes it"),
        deriv(closure),
        note("key",
             "The vehicle finishes with <strong>%s kg</strong> of spare "
             "capacity, and that is not slack: the closed form solved for a "
             "stack arriving at the asteroid at exactly the budget, and the "
             "stack actually flown is built on settled hardware and a settled "
             "containment fraction, both of which came out a little lighter. "
             "The shortfall against the budget, multiplied back out through "
             "the same k_out R_out every launch mass carries, is the spare "
             "capacity exactly."
             % fmt(slack, 3)),
        h(3, "Which cap binds"),
        para("Four ceilings stand over the payload and only the smallest of "
             "them is the answer. Naming which one binds is the difference "
             "between a result about this body and a result about the rig."),
        table(["cap", "what it is", "kg"], caps_rows),
    ]
    if a["electric"]:
        ep = M["ep"]
        html_out.append(note(
            "key",
            "The stage is <strong>electric</strong>, so it pays a dv penalty "
            "of %s for being unable to fly impulsive burns, and it carries "
            "its own power: %s kW of array, %s kg of thruster and %s kg of "
            "PPU for %s N of thrust."
            % (fmt(C["dv_penalty"], 2), fmt(ep["power"] / 1000.0, 1),
               fmt(ep["thruster"], 1), fmt(ep["ppu"], 1),
               fmt(ep["thrust"], 3))))
        # ⚠️  THREE MASSES ON TWO DIFFERENT QUANTITIES, and none of them can be
        # checked from the page without these rates.  Array and PPU scale with
        # POWER; the thruster scales with THRUST, which owes nothing to
        # efficiency.  The array figure is also NOT the plant's: an EP array is
        # in permanent sunlight and takes the bare 1/r2 specific power, while
        # the plant standing on the body takes the night-side derating.
        html_out.append(kv([
            ("exhaust velocity (Isp %s s x g0)" % fmt(C["isp"], 1),
             fmt(C["ve"], 1, "m/s")),
            ("thrust time the stage is sized for",
             fmt(C["cfg"].ep_target_thrust_yr, 2, "yr")),
            ("thruster efficiency", pct(C["thruster_eff"], 1)),
            ("thruster specific mass", fmt(C["thruster_kg_per_n"], 1, "kg/N")),
            ("PPU specific mass", fmt(C["ppu_kg_per_kw"], 2, "kg/kW")),
            ("EP array specific power, permanent sunlight",
             fmt(C["w_bare"], 3, "W/kg")),
        ]))
        # ⚠️  SIZED ON THE PASS'S PROPELLANT LOAD, NOT THE SETTLED ONE.
        # The model never re-sizes the stage after the loop converges, so it
        # is built for a propellant mass a few kilograms above the one the
        # flown stack actually burns.  Substituting the settled figure here
        # would produce a stage the run did not fly and a mass ledger that
        # does not add up.
        seconds = C["cfg"].ep_target_thrust_yr * 365.25 * 24.0 * 3600.0
        html_out.append(deriv([
            ("t_burn", "= %s yr * 365.25 * 24 * 3600 = %s s"
             % (prec(C["cfg"].ep_target_thrust_yr, 4), prec(seconds, 12))),
            ("m_prop", "= %s kg" % prec(cas["m_prop"], 12),
             "the converging pass's load, which is what the stage is sized "
             "on"),
            ("P", "= m_prop v_e^2 / (2 eta t_burn)"),
            ("", "= %s * %s / (2 * %s * %s)"
             % (prec(cas["m_prop"], 12), prec(C["ve"] ** 2, 12),
                prec(C["thruster_eff"], 4), prec(seconds, 12))),
            ("", "= %s W" % prec(ep["power"], 12)),
            ("T", "= m_prop v_e / t_burn = %s N" % prec(ep["thrust"], 12)),
            ("array", "= P / w_bare = %s / %s = %s kg"
             % (prec(ep["power"], 12), prec(C["w_bare"], 12),
                prec(ep["array"], 12)),
             "the bare 1/r^2 figure: an EP array never stands in a shadow"),
            ("PPU", "= (P / 1000) sigma_PPU = %s * %s = %s kg"
             % (prec(ep["power"] / 1000.0, 12), prec(C["ppu_kg_per_kw"], 6),
                prec(ep["ppu"], 12))),
            ("thruster", "= T sigma_thr = %s * %s = %s kg"
             % (prec(ep["thrust"], 12), prec(C["thruster_kg_per_n"], 6),
                prec(ep["thruster"], 12)),
             "on THRUST, which owes nothing to efficiency"),
            ("m_EP", "= %s kg" % prec(ep["mass"], 12)),
        ]))
    elif a["penalised"]:
        # ⚠️  NOT "chemical".  The propellant is electric and the legs are
        # penalised for it; what is switched off is the sizing of a stage to
        # fly them, which is `model_low_thrust_time`.  Calling this chemical
        # would contradict the delta-v table three sections up.
        html_out.append(note(
            "warn",
            "This run does <strong>not size an electric stage</strong>, "
            "although the propellant is one: the legs still carry the %s "
            "low-thrust penalty shown above, and no array, PPU or thruster is "
            "flown or paid for, and the duration has no thrust-time floor. "
            "That is <code>model_low_thrust_time</code> off, and it is a "
            "diagnostic rather than a mission."
            % fmt(C["dv_penalty"], 2)))
    else:
        html_out.append(note(
            "key", "The stage is <strong>chemical</strong>: it flies "
            "impulsive burns, pays no dv penalty and carries no electric "
            "power system."))
    if a["isru"]:
        html_out.append(note(
            "key",
            "The return propellant is <strong>made at the asteroid</strong>, "
            "so it never rides the outbound leg: %s kg of it appears in the "
            "returning stack and none of it in the launch mass. What does NOT "
            "drop out is the empty return <strong>tank</strong> -- you can "
            "make propellant out there, not a pressure vessel -- so %s kg of "
            "tankage is still launched from Earth. The saving is paid for in "
            "rock: %s kg of extra feed the same rig has to dig before any "
            "ore. The propellant needs %s, and this rock is %s, so the rig "
            "digs %s kg of it for every kilogram made -- which is the cost a "
            "flat dollar-per-kilogram charge left out."
            % (fmt(M["m_rprop"], 1), fmt(M["m_tank_ret"], 1),
               fmt(M["isru_feed"], 0),
               # ⚠️  TWO RATIOS, AND THE TABLE'S IS THE FIRST.
               # A water-fed propellant reads kg of WATER per kg made straight
               # off Module 3; what the rig has to dig for it is that over the
               # body's ice fraction, which is a different number and the one
               # the mass cascade uses.  Printing only the second left the
               # Module 3 rate unreproducible from the page.
               ("%s kg of water per kg, at %s ice"
                % (prec(C["isru_water_per_kg_prop"], 6),
                   pct(C["ice_frac"], 2)))
               if C["isru_water_per_kg_prop"] > 0 else
               "%s kg of regolith per kg" % prec(C["isru_feed_per_kg_prop"], 6),
               "water ice" if C["isru_water_per_kg_prop"] > 0 else "regolith",
               prec(C["isru_feed_per_kg_prop"], 6))))
    if a["aero"]:
        html_out.append(note(
            "key",
            "The heat shield is <strong>%s kg</strong>, and it is dead mass "
            "twice over: hauled out from Earth and then pushed back through "
            "the return burn, even though it ablates on entry. It is sized on "
            "the payload AND the dry return vehicle, because that is what it "
            "arrives behind." % fmt(M["m_tps"], 1)))
    if a["boiloff"]:
        html_out.append(note(
            "warn",
            "This propellant <strong>boils off</strong>. It sits in the tank "
            "from launch until the return burn, and over that hold the "
            "quantity needed is inflated by a factor of %s. The model folds "
            "that into an effective return delta-v rather than bolting a term "
            "onto the cascade, because the return propellant scales with "
            "(R - 1) and inflating that term is exactly the same arithmetic."
            % fmt(M["boiloff_factor"], 4)))
    if M["vol_cap"] and M["ret_vol"] > 0:
        # ⚠️  THE ALLOWANCE IS A QUARTER OF THE FAIRING, NOT THE FAIRING.  The
        # model returns cargo in 25% of the fairing volume, so quoting the
        # whole of it overstates the headroom fourfold AND puts the binding
        # test four times too high: a payload sitting exactly on the volume
        # cap was reported as bounded by the mass budget, which is the one
        # sentence this paragraph exists to get right.  The cap is a mass in
        # the cascade, so the test is against the mass it produced.
        # ⚠️  SIGNIFICANT FIGURES, NOT DECIMAL PLACES.  Two
        # decimals renders a 0.0151 m3 hold as "0.02", which is the same
        # defect as the cost lines that printed to two significant figures --
        # a number on the page that cannot be checked against the column it
        # came from.  A dense concentrate at an in-space destination is a small
        # volume, so this is the normal case rather than a corner.
        html_out.append(para(
            "The returned cargo occupies %s m3 against a %s m3 allowance, a "
            "quarter of the %s m3 fairing, so the %s bound the payload."
            % (prec(M["ret_vol"], 4), fmt(0.25 * C["fairing_m3"], 1),
               fmt(C["fairing_m3"], 1),
               "volume cap" if M["m_pay"] >= M["vol_cap"] * 0.999999
               else "mass budget rather than the volume cap")))
    return "".join(html_out)


def solar_plant_terms(C, name="w_plant"):
    """The array's specific power on this body, term by term.

    🚨  ONE DERIVATION, THREE CALLERS, AND AN RTG PAGE IS ONE OF
    THEM.  `solar_w_per_kg_bare`, `array_oversize_factor` and `dark_period_h`
    are properties of the BODY and the model writes them on every row,
    radioisotope missions included.  A page that flew nuclear heat showed none
    of them -- so it hid the alternative its own choice was made against, and
    hid the two storage rates behind it, which `--sweep --audit` found at `geo`
    on the first run that ever rendered such a page.

    `name` is the label of the last row: an array that IS the plant, or one
    that would have been.  Everything above it is the same arithmetic either
    way, which is why this is a function rather than a third copy.
    """
    excess = max(0.0, C["dark_h"] - max(0.0, C["baseline_dark_h"]))
    kg_per_w = 1.0 / C["w_plant"] if C["w_plant"] else 0.0
    return [
        ("w_bare", "= w_1AU / a^2 = %s / %s^2 = %s W/kg"
         % (prec(C["w_1au"], 6), prec(C["a_au"], 12), prec(C["w_bare"], 12)),
         "sunlight falls off as the square of the distance"),
        ("oversize", "= ((1 - f) + f / eta) / (1 - f)"),
        ("", "= ((1 - %s) + %s / %s) / (1 - %s) = %s"
         % (prec(C["dark_frac"], 4), prec(C["dark_frac"], 4),
            prec(C["storage_eff"], 4), prec(C["dark_frac"], 4),
            prec(C["oversize"], 12)),
         "the sunlit hours run the load AND recharge the store"),
        ("dark_h", "= min(P_rot / 2, %s) = min(%s, %s) = %s h"
         % (prec(C["max_dark_h"], 6), prec(C["rot_h"] / 2.0, 8),
            prec(C["max_dark_h"], 6), prec(C["dark_h"], 8)),
         "the night, %s"
         % ("CLAMPED: this body turns too slowly to size a store for"
            if C.get("dark_clamped") else
            "half a rotation, under the ceiling" if C.get("rot_measured") else
            "half a rotation; none is measured, so the catalog median is "
            "used")),
        ("excess_h", "= max(0, dark_h - baseline) = max(0, %s - %s) = %s h"
         % (prec(C["dark_h"], 6), prec(C["baseline_dark_h"], 6),
            prec(excess, 12)),
         "only the storage ABOVE what the 1 AU rating already buys is new "
         "mass"),
        ("kg/W", "= oversize / w_bare + excess_h / e_storage"),
        ("", "= %s / %s + %s / %s = %s"
         % (prec(C["oversize"], 12), prec(C["w_bare"], 12),
            prec(excess, 12), prec(C["storage_wh_per_kg"], 6),
            prec(kg_per_w, 12))),
        (name, "= 1 / (kg/W) = %s W/kg" % prec(C["w_plant"], 12),
         "against a bare %s: the night side costs a factor of %s"
         % (prec(C["w_bare"], 6),
            prec(C["w_bare"] / C["w_plant"] if C["w_plant"] else 0.0, 4))),
    ]


def s_power(out):
    """Section 5: the processing plant, which only some missions need."""
    M, C = out["M"], out["C"]
    a = architecture(out)
    if M["plant"] <= 0:
        # 🚨  A ZERO PLANT IS NOT A MISSING SECTION.  The model computes
        # `power_w_per_kg_at_target` and `dark_period_h` on every row whether
        # or not a plant is flown, because both are properties of the BODY
        # rather than of the mission, and this branch used to drop them: a
        # column audit reported two quantities the pipeline computed and the
        # page did not show, on exactly the mission shape that needs no plant.
        # They are also the figures that say what concentrating WOULD have
        # cost, which is the only reason a reader of a raw mission cares.
        rate = [
            ("P", "= 0 W", "nothing to excavate above the ore, nothing to "
                           "separate and no ice to bake out"),
        ]
        if a["power"] == "rtg":
            # 🚨  THE ALTERNATIVE IS PART OF THE ANSWER.  A
            # radioisotope source was chosen over an array on this body, and
            # the array's numbers are output columns the model fills in
            # anyway; a page that omits them asks the reader to take the
            # choice on trust.  See `solar_plant_terms`.
            rate += solar_plant_terms(C, name="w_solar")
        else:
            rate += solar_plant_terms(C)
        rate.append(
            ("w_plant",
             "= %s W/kg" % prec(C["plant_w_per_kg"], 12)
             if a["power"] == "rtg" else
             "= 1 / (kg/W) = %s W/kg" % prec(C["plant_w_per_kg"], 12),
             "flat: a radioisotope source takes neither penalty"
             if a["power"] == "rtg" else
             "what a plant on this body would cost per watt, had one been "
             "needed"))
        return "".join([
            sec("power"),
            note("ok",
                 "<strong>This mission flies no power system.</strong> The "
                 "plant exists to run separation and water liberation, and a "
                 "run-of-mine mission carrying no ice needs neither. The dig "
                 "still costs time, which is what bounds the payload; it just "
                 "does not cost watts."),
            deriv(rate),
            # ⚠️  THE COUNTERFACTUAL NEEDS ITS PRICE TOO.  The
            # branch exists to say what a plant on this body WOULD have cost,
            # and it gave the watts per kilogram and not the dollars per watt
            # -- which is the half a reader would have to look up.  Found by
            # the rate audit on a mission that flies no plant at all.
            kv([("plant specific power",
                 fmt(C["plant_w_per_kg"], 3, "W/kg")),
                ("plant price, had one been flown",
                 usd(C["plant_usd_per_w"], 2) + " /W")]),
            para("Everything under the draw is a property of the body "
                 "rather than of the mission, and the model reports it on "
                 "every row. It is what a concentrating mission to the same "
                 "target would have paid for its watts, and it is derived "
                 "here rather than asserted so that the comparison can be "
                 "checked as easily as the mission that was flown."),
        ])
    # ⚠️  A DRAW WITH NO RATES BEHIND IT CANNOT BE CHECKED.  Excavation is
    # charged per kilogram MOVED, beneficiation per kilogram of product OUT,
    # and liberation per kilogram of water baked out of the rock; the three go
    # over the dig time to give watts.  All three are Module 3 rows that the
    # page consumed silently.
    pairs = [
        ("excavation energy", fmt(C["dig_wh"], 1, "Wh/kg dug")),
        ("beneficiation energy", fmt(C["benef_wh"], 1, "Wh/kg of product")),
        ("water liberation energy", fmt(C["water_wh"], 1, "Wh/kg of water")),
        ("water liberated", fmt(M["liberated"], 1, "kg")),
        ("<strong>processing draw</strong>",
         "<strong>%s</strong>" % fmt(M["draw"], 1, "W")),
        ("plant specific power", fmt(C["plant_w_per_kg"], 3, "W/kg")),
        ("<strong>plant mass</strong>",
         "<strong>%s</strong>" % fmt(M["plant"], 1, "kg")),
    ]
    # 🚨  `y * 365.25 * 24.0` IS NOT `y * 8766.0`.  Float multiplication does
    # not associate, and the model writes the first, so the hours here are
    # formed the same way.  A pre-multiplied constant rounds once where this
    # rounds twice, they disagree in the last bit on about a quarter of the
    # durations this model produces, and that is enough to move a draw, an
    # array mass and every cost downstream of it off bit-exact.
    hrs = (M["dig_yr"] * 365.25) * 24.0
    dug = M["feed"] + M["isru_feed"]
    draw_terms, total = [], []
    if a["beneficiated"] or a["isru"]:
        draw_terms.append(
            ("P_dig+ben", "= (e_dig * %s + e_ben * %s) / %s"
             % (prec(dug, 12), prec(M["m_pay"], 12) if a["beneficiated"]
                else "0", prec(hrs, 12))))
        total.append((C["dig_wh"] * dug
                      + (C["benef_wh"] * M["m_pay"] if a["beneficiated"]
                         else 0.0)) / hrs)
        draw_terms.append(("", "= (%s * %s + %s * %s) / %s = %s W"
                           % (prec(C["dig_wh"], 6), prec(dug, 12),
                              prec(C["benef_wh"] if a["beneficiated"] else 0.0,
                                   6),
                              prec(M["m_pay"] if a["beneficiated"] else 0.0,
                                   12),
                              prec(hrs, 12), prec(total[-1], 12))))
    if M["liberated"] > 0:
        total.append(C["water_wh"] * M["liberated"] / hrs)
        draw_terms.append(
            ("P_H2O", "= e_H2O * %s / %s = %s * %s / %s = %s W"
             % (prec(M["liberated"], 12), prec(hrs, 12),
                prec(C["water_wh"], 6), prec(M["liberated"], 12),
                prec(hrs, 12), prec(total[-1], 12))))
    draw_terms += [
        ("hours", "= (t_dig * 365.25) * 24 = (%s * 365.25) * 24 = %s h"
         % (prec(M["dig_yr"], 12), prec(hrs, 12)),
         "associated exactly as the model associates it"),
        ("P", "= %s W" % prec(M["draw"], 15), "the continuous processing draw"),
    ]
    plant_terms = []
    if a["power"] == "rtg":
        plant_terms = [
            ("w_plant", "= %s W/kg" % prec(C["plant_w_per_kg"], 12),
             "flat: a radioisotope source takes neither the 1/r^2 nor the "
             "night-side penalty"),
        ]
        # The array it was chosen over, same arithmetic, on the same body.
        plant_terms += solar_plant_terms(C, name="w_solar")
    else:
        plant_terms = solar_plant_terms(C)
    plant_terms.append(
        ("m_plant", "= P / w_plant = %s / %s = %s kg"
         % (prec(M["draw"], 12), prec(C["plant_w_per_kg"], 12),
            prec(M["plant"], 15))))
    html_out = [
        sec("power"),
        outputs([("P", prec(M["draw"], 12, "W"), "processing draw"),
                 ("m_plant", prec(M["plant"], 12, "kg"), "plant mass")]),
        para("Processing energy over the stay gives a draw, the draw gives an "
             "array, and the array is launched like everything else. This is "
             "the feedback the fixed point above exists to solve."),
        h(3, "The draw"),
        deriv(draw_terms),
        h(3, "The plant that supplies it"),
        deriv(plant_terms),
        kv(pairs),
    ]
    if a["power"] == "rtg":
        html_out.append(note(
            "key",
            "The plant is a <strong>radioisotope source</strong>, flat at "
            "%s W/kg wherever it is, against a solar array's %s W/kg at 1 AU. "
            "Solar falls as 1/r2 and a radioisotope source does not, so the "
            "two cross at sqrt(%s / %s) = <strong>%s AU</strong> and a body "
            "further out than that is better served by nuclear heat. It is "
            "not free: this plant is priced at %s per watt, and the binding "
            "constraint is not money but Pu-238 supply -- DOE produces about "
            "1.5 kg a year, roughly one flagship RTG for the entire world, "
            "which is why a draw over the ceiling makes a mission infeasible "
            "rather than expensive."
            % (fmt(C["rtg_w_per_kg"], 2), fmt(C["w_1au"], 2),
               fmt(C["w_1au"], 2), fmt(C["rtg_w_per_kg"], 2),
               fmt(crossover_au(C), 2), usd(C["plant_usd_per_w"]))))
    else:
        html_out.append(note(
            "key",
            "The plant is <strong>solar</strong>, rated at 1 AU and derated "
            "by 1/r2 to this body's distance, then oversized by %s for the "
            "night side: a rig on a rotating body is in shadow about half the "
            "time, and the sunlit hours have to run the load and recharge the "
            "store. The dark period used for storage is this body's own "
            "rotation, %s h. Solar was the cheaper source here because this "
            "body sits inside the crossover: %s W/kg at 1 AU against a "
            "radioisotope source's flat %s W/kg puts the two level at %s AU, "
            "and this body orbits at %s AU."
            % (fmt(C["oversize"], 3), fmt(C["dark_h"], 2),
               fmt(C["w_1au"], 2), fmt(C["rtg_w_per_kg"], 2),
               fmt(crossover_au(C), 2), fmt(C["a_au"], 3))))
    return "".join(html_out)


def s_clock(out):
    """Section 6: how long the mission takes, and how often it repeats."""
    M, DV, C = out["M"], out["DV"], out["C"]
    pairs = [("feed processed", fmt(M["feed"], 0, "kg"))]
    if M["isru_feed"] > 0:
        # ⚠️  WITHOUT THIS ROW THE TABLE DOES NOT ADD UP.  The dig time is on
        # every kilogram the rig moves, and under ISRU that is the ore plus the
        # rock the propellant is made from, which can be half as much again.
        pairs += [("regolith dug for return propellant",
                   fmt(M["isru_feed"], 0, "kg")),
                  ("<strong>total rock moved</strong>",
                   "<strong>%s</strong>" % fmt(M["feed"] + M["isru_feed"],
                                               0, "kg"))]
    pairs += [
        # Without the rate the dig time is an assertion.  It is the rig's mass
        # times its throughput per kilogram of rig, which is why a bigger rig
        # is a faster one and why the rig mass appears in two cascades.
        ("rig throughput", fmt(C["rate_kg_yr"], 0, "kg/yr")),
        ("dig time", fmt(M["dig_yr"], 4, "yr")),
        ("stay at the asteroid", fmt(M["stay"], 4, "yr")),
        ("outbound transfer", fmt(M["t_out"], 4, "yr")),
        ("return transfer", fmt(M["t_back"], 4, "yr")),
        ("window wait", fmt(DV["window_wait"], 4, "yr")),
        # Both candidate durations, because the answer is the larger of them
        # and a page that shows only the winner cannot be checked against
        # itself: out + stay + back does not add up to the duration whenever
        # the electric floor is what binds, which on an EP mission is usual.
        ("transfer fit: out + stay + back", fmt(M["chem_fit"], 4, "yr")),
    ]
    if M["electric_floor"] > 0:
        pairs.append(("electric floor: thrust time + stay",
                      fmt(M["electric_floor"], 4, "yr")))
    pairs += [
        ("<strong>mission duration</strong>",
         "<strong>%s</strong>" % fmt(M["duration"], 4, "yr")),
        ("campaign cadence", fmt(M["cadence"], 4, "yr")),
        ("rig trips, calendar bound", fmt(M["calendar_cap"], 0)),
        ("<strong>trips this rig serves</strong>",
         "<strong>%d</strong>" % M["trips"]),
    ]
    bound = ("the calendar" if M["calendar_cap"] <= M["trips"]
             else "its duty cycles")
    cfg, P_, a = C["cfg"], out["P"], architecture(out)
    t_dest = DV["a_dest"] ** 1.5
    dug = M["feed"] + M["isru_feed"]
    periods = [
        ("T_ast", "= a^1.5 = %s^1.5 = %s yr"
         % (prec(C["a_au"], 12), prec(DV["t_ast"], 12))),
        ("T_dest", "= %s^1.5 = %s yr" % (prec(DV["a_dest"], 12),
                                         prec(t_dest, 12)),
         "the orbit the destination is phased against"),
        ("S", "= 1 / |1/T_ast - 1/T_dest| = 1 / |%s - %s|"
         % (prec(1.0 / DV["t_ast"], 12), prec(1.0 / t_dest, 12))),
        ("", "= %s yr" % prec(DV["synodic"], 12), "the synodic period"),
        ("t_win", "= S / 2 = %s yr" % prec(DV["window_wait"], 12),
         "the expected wait once the feed is out of the ground"
         if C["cfg"].model_launch_windows
         else "launch windows are not modelled on this run"),
    ]
    clock = [
        ("rate", "= m_rig * gamma * 365.25 = %s * %s * 365.25 = %s kg/yr"
         % (prec(cfg.mining_hardware_kg, 8),
            prec(cfg.mining_rate_kg_per_day_per_kg_rig, 4),
            prec(C["rate_kg_yr"], 12))),
        ("t_dig", "= rock moved / rate = %s / %s = %s yr"
         % (prec(dug, 12), prec(C["rate_kg_yr"], 12), prec(M["dig_yr"], 12)),
         "the FEED is dug, not the payload; that is what concentrating costs"),
        ("t_stay", "= t_dig + t_win = %s + %s = %s yr"
         % (prec(M["dig_yr"], 12), prec(DV["window_wait"], 12),
            prec(M["stay"], 12))),
        ("t_out", "= max(0.5, tau_fit * dv_out) = max(0.5, %s * %s) = %s yr"
         % (prec(C["physics"]["tau_fit"], 4), prec(DV["dv_out"], 12),
            prec(M["t_out"], 12))),
        ("t_back", "= max(0.5, tau_fit * dv_ret) = %s yr"
         % prec(M["t_back"], 12)),
        ("transfer fit", "= t_out + t_stay + t_back = %s yr"
         % prec(M["chem_fit"], 12)),
    ]
    if M["electric_floor"] > 0:
        clock.append(("electric floor", "= t_burn + t_stay = %s + %s = %s yr"
                      % (prec(cfg.ep_target_thrust_yr, 4),
                         prec(M["stay"], 12), prec(M["electric_floor"], 12))))
    clock += [
        ("T_miss", "= max(1, %s) = %s yr"
         % (", ".join(prec(v, 12) for v in
                      ([M["chem_fit"], M["electric_floor"]]
                       if M["electric_floor"] > 0 else [M["chem_fit"]])),
            prec(M["duration"], 12)),
         "whichever clock is slower is the mission"),
        ("T_cad", "= max(t_stay, S) = max(%s, %s) = %s yr"
         % (prec(M["stay"], 12), prec(DV["synodic"], 12),
            prec(M["cadence"], 12)),
         "the %s paces this programme"
         % ("dig" if M["stay"] >= DV["synodic"] else "launch window")),
        ("calendar bound", "= floor(L_rig / t_stay) = floor(%s / %s) = %d"
         % (prec(C["val"]("Mining rig service life"), 4),
            prec(M["stay"], 12), M["calendar_cap"])),
        ("trips", "= min(calendar, W_max) = %d" % M["trips"]
         if C["rig_trip_limit"] else "= %d" % M["trips"],
         "campaigns one rig can serve"),
        ("span", "= T_miss + (W - 1) T_cad = %s + %d * %s = %s yr"
         % (prec(M["duration"], 12), max(0, P_["w"] - 1),
            prec(M["cadence"], 12),
            prec(M["duration"] + max(0, P_["w"] - 1) * M["cadence"], 12)),
         "the whole programme, on one rig"),
    ]
    return "".join([
        sec("clock"),
        outputs([("T_miss", prec(M["duration"], 12, "yr"), "mission duration"),
                 ("T_cad", prec(M["cadence"], 12, "yr"), "campaign cadence"),
                 ("trips", "%d" % M["trips"], "campaigns one rig serves")]),
        para("Extraction is rate-limited: the payload is capped by what the "
             "rig can dig inside the stay, and the dig time flows into "
             "operations cost, into the mission duration and into how often "
             "the campaign can repeat."
             + (" The duration is the longer of two clocks: the transfers "
                "plus the stay, and the thrust time an electric stage needs "
                "plus the stay."
                if M["electric_floor"] > 0 else
                " No electric stage is sized on this run, so there is no "
                "thrust-time floor: the duration is the transfers plus the "
                "stay.")),
        h(3, "Orbital and synodic periods"),
        deriv(periods),
        h(3, "The dig, the stay and the two clocks"),
        deriv(clock),
        kv(pairs),
        para("The rig is retired by <strong>%s</strong>. It wears out on duty "
             "cycles as well as on a calendar, and the model takes whichever "
             "of the two binds first: a service life divided by the stay is a "
             "figure about not corroding, and a machine cutting rock does not "
             "age that way." % bound),
    ])


def s_hold(out):
    """Section 7: what actually goes in the hold."""
    M, C = out["M"], out["C"]
    a = architecture(out)
    load = M["load"]
    rows = []
    price = {n: p for n, _f, p in C["phases"]}
    for name, kg in sorted(load["mix"].items(), key=lambda kv2: -kv2[1]):
        rows.append([esc(name), fmt(kg, 1), pct(kg / load["loaded"], 2),
                     usd(price.get(name, 0.0), 2),
                     musd(kg * price.get(name, 0.0))])
    rows.append(["<strong>total</strong>",
                 "<strong>%s</strong>" % fmt(load["loaded"], 1), "", "",
                 "<strong>%s</strong>" % musd(load["value"])])
    html_out = [sec("hold")]
    if a["beneficiated"]:
        html_out.append(para(
            "The mission is not sent for a named mineral; it is sent to bring "
            "back the best load it can assemble from what the body contains. "
            "With a fixed mass budget and divisible, per-kilogram-priced "
            "phases that is a fractional knapsack, and greedy selection by "
            "$/kg is provably optimal: fill the hold with the most valuable "
            "phase available, then the next."))
        html_out.append(para(
            "The rig processes %s kg of feed to fill a %s kg hold, a "
            "concentration ratio of %s to one, at a separation recovery of %s."
            % (fmt(M["feed"], 0), fmt(M["m_pay"], 0), fmt(M["ratio"], 3),
               pct(C["recovery"], 0))))
    else:
        html_out.append(para(
            "This mission flies run-of-mine ore, so nothing is chosen: it "
            "digs what it flies and flies what it digs, and the hold is the "
            "body's own composition scaled to the payload."))
    html_out.append(table(
        ["phase", "kg", "share of hold", "$/kg", "value"], rows))
    # 🚨  THE WALK, NOT ONLY ITS ANSWER.  Both bounds this model claims fall
    # OUT of the greedy walk rather than being imposed on it, and neither is
    # visible without the supply column beside the take: you cannot load more
    # of a phase than the processed feed contained (the content bound), and
    # once the hold is full there is nothing left to add (the purity bound).
    # A table of takes alone shows a result and hides the mechanism.
    if a["beneficiated"] and load.get("walk"):
        walk_rows = []
        for i, step in enumerate(load["walk"], 1):
            reason = ("hold full" if step["stopped"]
                      else "all the feed had" if step["take"] >= step["available"]
                      - 1e-9 and step["take"] > 0
                      else "hold ran out" if step["take"] > 0 else "-")
            walk_rows.append([
                "%d" % i, esc(step["phase"]), usd(step["price"], 2),
                fmt(step["supply"], 1),
                fmt(step["hold"], 1) if not step["stopped"] else "0.0",
                fmt(step["take"], 1), esc(reason)])
        html_out.append(h(3, "The walk itself, in price order"))
        html_out.append(para(
            "Each phase can supply <code>feed * f_c * eps_rec</code> and no "
            "more. The walk takes the cheapest of that supply and the hold "
            "still empty, in descending price order, and stops when the hold "
            "is full."))
        html_out.append(eq("supply = feed * f_c * eps_rec &nbsp;&nbsp; "
                           "take = min(supply, hold remaining)"))
        html_out.append(table(
            ["#", "phase", "$/kg", "supply (kg)", "hold left (kg)",
             "taken (kg)", "what stopped it"], walk_rows))
    # ⚠️  THE COMPARISON AGAINST THE BLEND ONLY MEANS SOMETHING IF THE HOLD
    # WAS CHOSEN.  A run-of-mine hold IS the blend, so the factor is exactly
    # one by construction and printing it reads as a result rather than as an
    # identity.
    html_out.append(deriv([
        ("value", "= sum(take * price) = %s" % usd(load["value"], 6)),
        ("$/kg", "= value / hold = %s / %s = %s"
         % (prec(load["value"], 12), prec(load["loaded"], 12),
            prec(load["usd_per_kg"], 12)),
         ("against %s for the body's own blend, a factor of %s"
          % (usd(C["bulk"], 2),
             prec(load["usd_per_kg"] / C["bulk"] if C["bulk"] else 0.0, 4))
          if a["beneficiated"] else
          "which is the body's own blend: nothing was chosen")),
    ]))
    html_out.append(kv([
        ("blended value", usd(load["usd_per_kg"], 2) + " /kg"),
        ("cargo water", fmt(M["water"], 1, "kg")),
        # The sealed, shaded hold is charged on the VOLATILE fraction of the
        # cargo, so it is payload-proportional exactly like the ore restraint
        # it sits on top of, which is what lets it fold into f and leave the
        # closed-form solver's algebra untouched.
        ("containment rate", fmt(C["contain_per_kg"], 4, "kg per kg of water")),
        ("containment fraction of payload", fmt(M["c_frac"], 5)),
        ("containment mass", fmt(M["m_containment"], 1, "kg")),
    ]))
    return "".join(html_out)


MARKET_PROSE = {
    "capacity_cap":
        "Prices are constant at any volume and what bounds a programme is how "
        "much the destination can absorb while it waits. A bigger fleet "
        "delivers more often, so each delivery gets a shorter slice of the "
        "market's annual capacity.",
    "elasticity":
        "Prices BEND as a market fills rather than holding and refusing the "
        "sale. Demand for precious metals is inelastic, so at the elasticity "
        "this model uses, doubling world supply quarters the price, which is "
        "why returning a tonne of platinum was never the business a "
        "spot-price spreadsheet makes it look. Everything clears; it clears "
        "for less.",
    "unbounded":
        "<strong>Nothing bounds the sale on this run.</strong> Any quantity "
        "clears at the catalog price, which is a diagnostic rather than a "
        "market: it is the free lunch every other model here exists to "
        "refuse, and the programme search has no reason to stop growing.",
    "single_mission":
        "Prices are constant and the programme is pinned at one mission, so "
        "there is no quantity for a market to notice and nothing to bound.",
}


def s_market(out):
    """Section 8: what the load actually sells for.

    🚨  FOUR MODELS, AND THEY ARE NOT DEGREES OF ONE THING.  A demand curve
    moves the PRICE and sells everything; a capacity ceiling holds the price
    and clips the QUANTITY; the other two bound nothing at all.  The
    diagnostics cross over with them, which is the part that misleads: under
    `elasticity` the haircut is in `saturation_multiplier` and the clearing
    fraction is 1.0, and under `capacity_cap` it is exactly the other way
    round.  A section that showed one table whatever the mode would read as a
    clean result rather than a wrong one.
    """
    P, C = out["P"], out["C"]
    rev = P["rev"]
    mode = rev.get("mode", "capacity_cap")
    frac = rev["surplus_frac"]
    if mode in ("unbounded", "single_mission"):
        return "".join([
            sec("market"),
            note("warn" if mode == "unbounded" else "ok",
                 MARKET_PROSE[mode]),
            kv([("gross value of the load", musd(rev["gross_base"])),
                ("delivered value", usd(rev["delivered"], 2) + " /kg")]),
        ])
    if mode == "elasticity":
        rows = [[esc(key), fmt(kg, 1),
                 fmt(C["market_kg"].get(key, float("inf")), 0),
                 sig(rev["multipliers"].get(key, 1.0), 6)]
                for key, kg in sorted(rev["pooled"].items())]
        return "".join([
            sec("market"),
            para(MARKET_PROSE[mode]),
            eq("P / P0 = (1 + Q / Qm) ^ (-1 / eps)"),
            note("key",
                 "<strong>The rate that moves a price is the MARKET's, not "
                 "one phase's share of it.</strong> Two phases selling into "
                 "one market depress it together, so the quantities are "
                 "pooled per market and each phase is then discounted at its "
                 "market's multiplier. Asking the curve per phase asks it "
                 "twice about half the quantity each time, which is a "
                 "strictly smaller haircut than the truth. And the quantity "
                 "is the PROGRAMME's: what is on the market at once is the "
                 "fleet, because one rig serves its campaigns back to back "
                 "while %s in flight concurrently."
                 % ("a single rig puts one payload" if P["f"] == 1 else
                    "%d rigs put %d payloads" % (P["f"], P["f"]))),
            table(["market", "this programme delivers (kg)",
                   "annual market (kg)", "price multiplier"], rows),
            kv([("gross value at spot", musd(rev["gross_base"])),
                ("value after the curve", musd(rev["capped"]["value"])),
                ("saturation multiplier", sig(rev["sat"], 6)),
                ("delivered value", usd(rev["delivered"], 2) + " /kg")]),
        ])
    M, a = out["M"], architecture(out)
    n, fleet = P["n"], P["f"]
    rows = []
    for key, allowance in sorted(rev["allow"].items()):
        ceiling = C["market_kg"].get(key, float("inf"))
        rows.append([esc(key), fmt(ceiling, 0),
                     "%s * %s" % (prec(ceiling, 8), prec(rev["window"], 12)),
                     fmt(allowance, 1)])
    # 🚨  THE WINDOW IS WHAT TURNS THE PROGRAMME LADDER OVER, and it is one
    # line of arithmetic that the page had been printing only the answer to.
    # The FIRST delivery waits the whole mission; every later one waits a
    # cadence divided by the fleet, because ships are interleaved.  So the
    # average slice of the market a delivery gets falls roughly as 1/F once
    # the mission term is amortised, while cost scales with F.
    window = [
        ("omega", "= (T_miss + (N - 1) * T_cad / F) / N"),
        ("T_cad / F", "= %s / %d = %s yr"
         % (prec(M["cadence"], 12), fleet, prec(M["cadence"] / fleet, 12)),
         "one fleet-interleaved cadence"),
        ("", "= (%s + %d * %s) / %d"
         % (prec(M["duration"], 12), n - 1,
            prec(M["cadence"] / fleet, 12), n)),
        ("", "= %s yr" % prec(rev["window"], 15),
         "how long one delivery's worth of market accumulates"),
    ]
    sale, total = [], 0.0
    walk = rev["capped"].get("walk") or []
    if a["beneficiated"]:
        sale_rows = []
        for i, step in enumerate(walk, 1):
            if step["take"] <= 0 and step["stopped"]:
                continue
            sale_rows.append([
                "%d" % i, esc(step["phase"]),
                "full" if step["full"] else "surplus",
                usd(step["price"], 2), fmt(step["supply"], 1),
                fmt(step["allowance"], 1) if step["allowance"] is not None
                else "-", fmt(step["take"], 1),
                musd(step["take"] * step["price"])])
        sale = sale_rows
    else:
        sale_rows = []
        for i, step in enumerate(walk, 1):
            sale_rows.append([
                "%d" % i, esc(step["phase"]),
                "bound" if step["bound"] else "clears",
                usd(step["price"], 2), fmt(step["hold"], 1),
                fmt(step["allowance"], 1), fmt(step["full"], 1),
                fmt(step["over"], 1)])
        sale = sale_rows
    html_out = [
        sec("market"),
        outputs([("Rev", musd(rev["capped"]["value"]), "what one delivery sells"),
                 ("clearing", prec(rev["clearing"], 12),
                  "of the unbounded hold's value")]),
        para(MARKET_PROSE["capacity_cap"]),
        eq("allowance = ceiling_kg_per_yr * "
           "[duration + (N - 1) * cadence / F] / N"),
        h(3, "The accumulation window behind one delivery"),
        deriv(window),
        h(3, "What each market will take from this delivery"),
        table(["market", "ceiling (kg/yr)", "ceiling x omega",
               "allowance (kg)"], rows),
        h(3, "The sale, tier by tier" if a["beneficiated"]
          else "The sale, phase by phase"),
        para("A concentrated load is <strong>reshaped</strong> rather than "
             "clipped: the ceilings go into the knapsack, so space a capped "
             "phase does not get stays available to the next phase down the "
             "price order. That is why a bounded hold can still fly full."
             if a["beneficiated"] else
             "Run-of-mine ore cannot be reshaped: the hold is the body's own "
             "composition, so a ceiling clips the sale rather than steering "
             "the load."),
        table(["#", "phase", "tier", "$/kg", "supply (kg)", "allowance (kg)",
               "sold (kg)", "value"]
              if a["beneficiated"] else
              ["#", "phase", "", "$/kg", "in hold (kg)", "allowance (kg)",
               "at full price (kg)", "past the ceiling (kg)"], sale),
        deriv([
            ("Rev", "= sum(sold * price) = %s" % usd(rev["capped"]["value"], 6)),
            ("gross", "= %s" % usd(rev["gross_base"], 6),
             "the same hold with no ceiling over it"),
            ("clearing", "= Rev / gross = %s / %s = %s"
             % (prec(rev["capped"]["value"], 12),
                prec(rev["gross_base"], 12), prec(rev["clearing"], 15))),
            ("delivered", "= Rev / m_pay = %s / %s = %s $/kg"
             % (prec(rev["capped"]["value"], 12), prec(M["m_pay"], 12),
                prec(rev["delivered"], 12))),
        ]),
        kv([("accumulation window", fmt(rev["window"], 4, "yr")),
            ("gross value, unbounded", musd(rev["gross_base"])),
            ("value after the ceilings", musd(rev["capped"]["value"])),
            ("market clearing fraction", sig(rev["clearing"], 6)),
            ("delivered value", usd(rev["delivered"], 2) + " /kg")]),
    ]
    if frac > 0:
        html_out.append(note(
            "ok",
            "Material past a ceiling <strong>sells at %s of full "
            "price</strong> rather than being abandoned: %s kg of this load "
            "did. The ceiling still bounds the programme, because the "
            "marginal kilogram past it is worth strictly less than the one "
            "before it." % (pct(frac, 0), fmt(rev["surplus"], 1))))
    else:
        html_out.append(note(
            "warn",
            "Material past a ceiling <strong>earns nothing</strong> on this "
            "run: %s kg of this load went unsold. That is the hard wall, "
            "which is what calc 1.21.0 shipped and what every cell of the "
            "2026-09 campaign was measured on." % fmt(rev["unsold"], 1)))
    return "".join(html_out)


def s_searches(out):
    """Section 9: the two searches that chose the mission."""
    sweep, ladder = out["sweep"], out["ladder"]
    a = architecture(out)
    html_out = [sec("searches")]
    C = out["C"]
    if a["beneficiated"]:
        rows = []
        for kind, ratio, priced in sweep["rungs"]:
            if not priced:
                rows.append([kind, fmt(ratio, 4), "does not close", "", "", "",
                             ""])
                continue
            best = priced["ladder"]["best"]
            mark = (" &nbsp;&lt;-- argmin"
                    if priced is sweep["winner"][2] else "")
            rows.append([kind, fmt(ratio, 4), fmt(priced["M"]["m_pay"], 0),
                         fmt(priced["M"]["feed"], 0),
                         usd(best["rev"]["delivered"], 2),
                         "(%d, %d)" % (best["f"], best["w"]),
                         sig(best["obj"], 6) + mark])
        best_frac = max(C["phases"], key=lambda p: p[2])[1]
        html_out.append(para(
            "How hard to concentrate is an economic decision, not a setting. "
            "Grade saturates once the hold is pure best-phase while the costs "
            "do not, so the value curve is concave and the optimum is usually "
            "strictly interior."))
        # 🚨  THE SATURATION RATIO IS A PROPERTY OF THE BODY, NOT A DIAL.
        # Once the hold is pure best-phase there is nothing better to put in
        # it, so grade stops improving while dig time, processing energy and
        # the ops clock keep climbing.  Naming it is what makes an interior
        # optimum legible as a result rather than as a search that stopped.
        html_out.append(deriv([
            ("r_max", "= 1 / (f_best * eps_rec) = 1 / (%s * %s) = %s"
             % (prec(best_frac, 6), prec(C["recovery"], 4),
                prec(sweep["r_max"], 12)),
             "above this the hold is pure %s and grade stops improving"
             % esc(max(C["phases"], key=lambda p: p[2])[0])),
            ("step", "= r_max^(1/%d) = %s"
             % (max(1, int(C["cfg"].concentration_search_steps) - 1),
                prec(sweep["step"], 12)),
             "the coarse ladder is geometric, then refined at +/- half a step"),
        ]))
        html_out.append(table(
            ["rung", "ratio", "payload (kg)", "feed (kg)", "delivered $/kg",
             "best (F, W)", "cost / revenue"], rows))
        html_out.append(para(
            "The sweep runs to a saturation ratio of %s. The winner is the "
            "rung at %s, and the rig achieves %s to one against it, because "
            "the throughput ceiling clips the feed before the ratio does."
            % (fmt(sweep["r_max"], 3), fmt(out["ratio"], 4),
               fmt(out["M"]["ratio"], 4))
            if out["M"]["ratio"] < out["ratio"] - 1e-9 else
            "The sweep runs to a saturation ratio of %s and the winner is "
            "%s to one." % (fmt(sweep["r_max"], 3), fmt(out["M"]["ratio"], 4))))
    else:
        html_out.append(para(
            "This mission does not concentrate, so there is no concentration "
            "sweep to show: the hold is the body's composition at whatever "
            "payload the cascade closes."))
    if a["searched"]:
        best = out["P"]
        # 🚨  THE LADDER IS TWO-DIMENSIONAL AND A SORTED LIST HIDES THAT.  F
        # is a geometric ladder and W is enumerated exhaustively, so the
        # programmes priced form a grid; printing the best twelve in objective
        # order shows which programme won and conceals the SHAPE of the
        # surface, which is the whole argument for searching the two jointly.
        # A grid shows the turnover in both directions at once.
        grid = {}
        for p in ladder["coarse"]:
            grid[(p["f"], p["w"])] = p
        fleets = sorted({f for f, _w in grid})
        campaigns = sorted({w for _f, w in grid})
        head = ["fleet F"] + ["W = %d" % w for w in campaigns]
        grid_rows = []
        for f in fleets:
            row = ["<strong>%d</strong>" % f]
            for w in campaigns:
                p = grid.get((f, w))
                if p is None:
                    row.append("-")
                elif p["f"] == best["f"] and p["w"] == best["w"]:
                    row.append("<strong>%s</strong>" % sig(p["obj"], 4))
                else:
                    row.append(sig(p["obj"], 4))
            grid_rows.append(row)
        html_out.append(h(3, "The programme ladder"))
        html_out.append(para(
            "Programme size is searched jointly with everything else. A "
            "larger programme amortises the non-recurring costs over more "
            "missions; a larger fleet delivers more often and each delivery "
            "gets a smaller slice of the market. The optimum is where those "
            "two turn over, and it is interior."))
        html_out.append(eq("N = F * W &nbsp;&nbsp; W &lt;= trips = %d"
                           % out["M"]["trips"]))
        html_out.append(table(head, grid_rows))
        html_out.append(para(
            "Every cell is a cost/revenue ratio, and the coarse ladder is "
            "%d programmes. The best of them is F = %d, W = %d."
            % (len(ladder["coarse"]), min(grid, key=lambda k: grid[k]["obj"])[0],
               min(grid, key=lambda k: grid[k]["obj"])[1])))
        if ladder["refine"]:
            ref = [[p["n"], p["f"], p["w"], musd(p["cost"]["total"]),
                    musd(p["expected"]),
                    sig(p["obj"], 6)
                    + (" &nbsp;&lt;-- argmin" if p["obj"] == best["obj"]
                       else "")]
                   for p in sorted(ladder["refine"], key=lambda x: x["f"])]
            html_out.append(h(3, "The refinement pass"))
            html_out.append(para(
                "One pass runs around the coarse winner at its own W, which "
                "is what makes the search non-exhaustive: it explores the "
                "neighbourhood of the rung that won and no other."))
            html_out.append(table(
                ["N", "ships", "campaigns/ship", "cost", "expected revenue",
                 "cost / revenue"], ref))
        # ⚠️  WHY IT TURNS OVER, which no ratio on its own can say.  The
        # window falls as 1/F once the mission term is amortised, so each
        # delivery's allowance shrinks with the fleet while cost scales with
        # it.  The ladder stops where the ceilings first begin to bite.
        turn = [p for p in sorted(ladder["coarse"] + ladder["refine"],
                                  key=lambda x: x["f"]) if p["w"] == best["w"]]
        if len(turn) > 2:
            turn_rows = []
            for p in turn:
                rv = p["rev"]
                turn_rows.append([
                    p["f"], p["n"], fmt(rv["window"], 6),
                    sig(rv["clearing"], 6),
                    fmt(rv.get("surplus", 0.0) or rv.get("unsold", 0.0), 0),
                    musd(p["cost"]["total"]),
                    sig(p["obj"], 6)
                    + (" &nbsp;&lt;-- argmin" if p["obj"] == best["obj"]
                       else "")])
            html_out.append(h(3, "Why the ladder turns over"))
            html_out.append(para(
                "Every row below is at W = %d, the winner's own campaigns per "
                "ship, so only the fleet moves. Cost falls all the way: a "
                "bigger programme always amortises the non-recurring lines "
                "better. What stops it is the window."
                % best["w"]))
            html_out.append(table(
                ["fleet F", "N", "omega (yr)", "clearing",
                 "past the ceiling (kg)", "cost", "cost / revenue"],
                turn_rows))
        html_out.append(para(
            "%d programmes were priced in all. The ladder is geometric in the "
            "fleet and exhaustive in campaigns-per-ship, then refined once "
            "around the coarse winner, so it is not an exhaustive search."
            % (len(ladder["coarse"]) + len(ladder["refine"]))))
    else:
        html_out.append(h(3, "The programme"))
        html_out.append(para(
            "The programme search was off for this run, so the mission is "
            "priced at N = %d and the fleet is whatever that needs. Turning "
            "the search on asks a different question: not the best single "
            "mission to this body, but the best programme built around it."
            % out["P"]["n"]))
    return "".join(html_out)


def s_reliability(out):
    """Section 10: the probability the mission works, when it is charged."""
    rel = out["P"]["rel"]
    if rel.get("off"):
        return "".join([
            sec("reliability"),
            eq("P = p_launch * exp(-T / MTBF) * p_mining"),
            para("That is the discount the model applies when it is asked "
                 "to. On this run all three factors are exactly 1.0, so "
                 "expected revenue and gross revenue are the same number "
                 "everywhere below."),
            note("ok",
                 "<strong>Revenue is not discounted for risk on this "
                 "run.</strong> The answer below is what the mission costs if "
                 "it works. Two of the three factors in that discount are "
                 "judgements about hardware nobody has flown, and applying "
                 "them to the answer buries them in the headline; the run "
                 "therefore states the physics and leaves the risk weighting "
                 "to whoever needs it."),
        ])
    return "".join([
        sec("reliability"),
        para("Revenue is not certain: the launch can fail, the spacecraft can "
             "die in transit, and the mining chain has never been "
             "demonstrated. Expected revenue is multiplied by the product "
             "below while costs are charged in full, which is the "
             "conservative and correct treatment: the money is spent either "
             "way."),
        eq("P = p_launch * exp(-T / MTBF) * p_mining"),
        # ⚠️  ONLY THE MINING TERM LEARNS, and the page had shown its
        # fleet average without the curve behind it.  A launch vehicle is
        # already mature and MTBF is a duration exposure rather than a
        # heritage question, so a programme buys down exactly one of the
        # three, and by how much is the thing worth seeing.
        deriv([
            ("p_cruise", "= exp(-T_miss / MTBF) = exp(-%s / %s) = %s"
             % (prec(out["M"]["duration"], 12), prec(rel["mtbf"], 6),
                prec(rel["p_cruise"], 15))),
            ("p_mine(n)", "= 1 - max(q_1 n^-alpha, 1 - q_max)",
             "the nth unit built"),
            ("", " &nbsp; ".join(
                "n=%d: %s" % (i, prec(v, 8)) for i, v in
                [(1, rel["terms"][0]),
                 (max(1, len(rel["terms"]) // 2),
                  rel["terms"][max(0, len(rel["terms"]) // 2 - 1)]),
                 (len(rel["terms"]), rel["terms"][-1])])),
            ("p_mining", "= (1/N) sum over n = 1..%d = %s"
             % (len(rel["terms"]), prec(rel["p_mining"], 15))),
            ("P", "= %s * %s * %s = %s"
             % (prec(rel["p_launch"], 6), prec(rel["p_cruise"], 12),
                prec(rel["p_mining"], 12), prec(rel["p_succ"], 15))),
        ]),
        kv([("launch reliability", sig(rel["p_launch"], 4)),
            ("spacecraft MTBF", fmt(rel["mtbf"], 2, "yr")),
            ("cruise survival", sig(rel["p_cruise"], 6)),
            ("mining success, fleet average", sig(rel["p_mining"], 6)),
            ("<strong>P(success)</strong>",
             "<strong>%s</strong>" % sig(rel["p_succ"], 6))]),
        note("key",
             "<strong>Costs are charged in full either way.</strong> The "
             "money is spent whether or not the mission works, so the "
             "discount belongs on revenue alone, which is the conservative "
             "and the correct treatment."),
    ])


def s_cost(out):
    """Section 11: the cost cascade, line by line.

    🚨  THREE OF THESE LINES ARE CHOSEN BY THE DESTINATION AND NOT BY THE
    MISSION, so they are LABELLED by it too.  The vehicle that meets the cargo
    is a lander at a surface base, a guided re-entry capsule if it comes home
    and a passive berthing adapter at a depot, and those differ by more than
    threefold per kilogram.  An Earth return also pays a recovery campaign and
    the full launch-and-re-entry licence where an in-space delivery pays depot
    handover and the launch-only one.  A page that called every one of them
    "return capsule" would hide the largest single difference between two
    destinations behind a constant label.
    """
    P, a = out["P"], architecture(out)
    cst = P["cost"]
    lines = cst["lines"]
    vehicle_line = ("surface lander" if a["lander"]
                    else "re-entry capsule" if a["to_earth"]
                    else "berthing adapter")
    order = [("launch", "launch"), ("outbound propellant", "oprop"),
             ("return propellant, made on site" if a["isru"]
              else "return propellant", "rprop"),
             ("mining rig share", "rig"), (vehicle_line, "capsule"),
             ("power system", "plant"), ("electric stage", "ep"),
             ("tankage", "tank"), ("heat shield", "tps")]
    # 🚨  A LINE WITH NO BASIS BESIDE IT CANNOT BE CHECKED, AND EVERY LINE
    # HERE HAS ONE.  Each is a mass or a draw or a duration times a rate out
    # of Module 3, and the page had been printing only the product -- which
    # made the largest single line in most missions, the vehicle that meets
    # the cargo, look like a constant rather than something that grows with
    # the haul.
    M, C = out["M"], out["C"]
    lc = cst["lc"]
    lc_note = " x lc" if lc != 1.0 else ""
    basis = {
        "launch": "%s kg x %s"
                  % (fmt(M["m_launch"], 1),
                     usd(float(C["veh"]["usd_per_kg_to_leo"]), 0) + "/kg"),
        # ⚠️  THE PRICE THE RUN PAID, WHICH IS THE ONE THE LINE BESIDE
        # IT WAS COSTED AT.  These read `C["pro"]["cost_usd_per_kg"]` -- the
        # Stage 3 table as it stands TODAY -- while the cost came from the
        # price recovered off the row, so a page whose propellant table had
        # been refetched showed a basis that does not multiply out to its own
        # line.  See `run_propellant_price`.
        "oprop": "%s kg x %s"
                 % (fmt(M["m_oprop"], 1),
                    usd(C["prop_usd_per_kg"], 0) + "/kg"),
        "rprop": "%s kg x %s"
                 % (fmt(M["m_rprop"], 1),
                    usd(C["cfg"].isru_processing_usd_per_kg if a["isru"]
                        else C["prop_usd_per_kg"], 0) + "/kg"),
        "rig": "%s over %d campaign(s)"
               % (musd(cst["rig_total"] - cst["terminal"]), cst["share"]),
        "capsule": "%s kg x %s%s"
                   % (fmt(M["m_dry"], 1), usd(C["capsule_per_kg"], 0) + "/kg",
                      lc_note),
        "plant": "%s W x %s%s"
                 % (fmt(M["draw"], 1), usd(C["plant_usd_per_w"], 0) + "/W",
                    lc_note),
        # ⚠️  BUILT ONLY WHEN THERE IS A STAGE TO PRICE.  `C["val"]`
        # RECORDS the rate it hands out, and the audit then expects the page to
        # show it -- so composing this string for a chemical mission, whose
        # zero-cost row is then dropped from the table, reported the page
        # incomplete for two rates no chemical page can print.  Reading a rate
        # is what makes it a rate; see `val`.
        "ep": ("%s W x %s/W + %s kW x %s/kW%s"
               % (fmt(M["ep"]["power"], 1),
                  usd(C["val"]("Power system (solar + battery)"), 0),
                  fmt(M["ep"]["power"] / 1000.0, 2),
                  usd(C["val"]("Electric propulsion system recurring cost"), 0),
                  lc_note)) if M["ep"]["power"] > 0 else "",
        "tank": "%s kg x %s%s"
                % (fmt(M["m_tank_ret"] + M["m_tank_out"], 1),
                   usd(C["val"]("Propellant tank recurring cost"), 0) + "/kg",
                   lc_note),
        "tps": "%s kg x %s%s"
               % (fmt(M["m_tps"], 1), usd(C["tps_per_kg"], 0) + "/kg", lc_note),
    }
    rows = [[name, esc(basis.get(key, "")), musd(lines[key])]
            for name, key in order if key in lines and lines[key]]
    # ⚠️  THE SUBTOTAL, NOT JUST THE LINES.  `hardware_cost_usd` is the figure
    # the mass ledger is checked against -- every kilogram in the cascade has a
    # price in it and every kilogram it pays for is flown -- and the page
    # printed its five components without ever printing the sum a reader would
    # need to run that check.
    rows += [["<strong>hardware subtotal</strong>",
              "rig + %s + plant + stage + tank"
              % ("lander" if a["lander"] else "capsule" if a["to_earth"]
                 else "adapter"),
              "<strong>%s</strong>" % musd(cst["hardware"])],
             ["operations", "%s yr x %s/yr"
              % (fmt(M["duration"], 4),
                 usd(C["val"]("Mission operations"), 0)), musd(cst["ops"])],
             ["spacecraft NRE / N", "%s x (1 - %s) / %d"
              % (usd(C["val"]("Spacecraft development (NRE)"), 0),
                 fmt(C["cfg"].nre_recurring_overlap_fraction, 2), P["n"]),
              musd(cst["nre"])],
             ["autonomy NRE / N", "%s / %d"
              % (usd(C["val"]("Autonomous mining control & AI (NRE)"), 0),
                 P["n"]), musd(cst["autonomy"])]]
    if cst["liability"] or cst["launch_ins"]:
        # 🚨  A PREMIUM IS AN UPFRONT LINE, so it carries contingency and the
        # full up-front compounding and is worth about twice its face value in
        # the answer.  Costing it by its share of the total understates it by
        # that factor, which is why it is listed rather than folded in.
        rows += [["third-party liability", "flat, per mission",
                  musd(cst["liability"])],
                 ["launch insurance", "%s%% of launch + book value"
                  % fmt(C["val"]("Launch insurance"), 2),
                  musd(cst["launch_ins"])]]
    rows += [
             ["licensing: %s" % ("launch and re-entry" if a["to_earth"]
                                 else "launch only"), "flat, per mission",
              musd(cst["licensing"])],
             ["recovery campaign" if a["to_earth"] else "berthing and handover",
              "flat, at end of mission", musd(cst["handover"])]]
    if cst["terminal"]:
        rows.append(["rig terminal value",
                     "%s unused x %s salvage, over %d"
                     % (pct(1.0 - cst["used"], 1),
                        pct(C["val"]("Rig salvage fraction"), 0), cst["share"]),
                     "-" + musd(cst["rig_credit_share"])])
    buckets = [
        ("up-front, after contingency", musd(cst["upfront"])),
        ("ongoing, after contingency", musd(cst["ongoing"])),
        ("end of mission, after contingency", musd(cst["end"])),
        ("contingency at %s" % pct(cst["contingency"] / max(
            cst["upfront_lines"] + cst["ops"] + cst["handover"], 1e-9), 0),
         musd(cst["contingency"])),
    ]
    rig_terms = [
        ("C_rig", "= m_rig * c_rig = %s * %s = %s"
         % (prec(C["cfg"].mining_hardware_kg, 8),
            prec(C["val"]("Mining payload recurring cost"), 8),
            usd(cst["rig_total"], 2)),
         "one rig, built once"),
        ("util", "= %s" % prec(cst["used"], 12),
         "how much of the rig's life this programme uses"),
        ("terminal", "= C_rig (1 - util) * salvage = %s"
         % usd(cst["terminal"], 2),
         "credited back at the end" if cst["terminal"]
         else "the rig is used up exactly"),
        ("rig share", "= (C_rig - terminal) / W = (%s - %s) / %d = %s"
         % (prec(cst["rig_total"], 12), prec(cst["terminal"], 12),
            cst["share"], usd(cst["lines"]["rig"], 2))),
    ]
    if lc != 1.0:
        rig_terms.insert(0, ("lc", "= (1/N) sum(k^log2(beta)), k = 1..%d = %s"
                             % (P["n"], prec(lc, 15)),
                             "Wright's law, cumulative average: every "
                             "recurring article is built at %s of unit one"
                             % pct(lc, 1)))
    cont = C["cfg"].contingency_fraction
    bucket_terms = [
        ("upfront", "= launch + propellant + hardware + licensing + NRE"),
        ("", "= %s, x (1 + %s) = %s"
         % (usd(cst["upfront_lines"], 2), prec(cont, 4),
            usd(cst["upfront"], 2))),
        ("ongoing", "= ops%s = %s, x (1 + %s) = %s"
         % (" + on-site propellant" if a["isru"] else "",
            usd(cst["ongoing"] / (1.0 + cont), 2), prec(cont, 4),
            usd(cst["ongoing"], 2))),
        ("end", "= %s, x (1 + %s) = %s"
         % (usd(cst["handover"], 2), prec(cont, 4), usd(cst["end"], 2))),
        ("contingency", "= %s" % usd(cst["contingency"], 2),
         "charged across all three"),
    ]
    html_out = [
        sec("cost"),
        outputs([("C_tot", musd(cst["total"]), "total cost of one mission "
                  "of %d" % P["n"])]),
        para("Every line comes from the reference tables; none is invented "
             "here. The lines are then bucketed by WHEN the money is spent, "
             "because that is what decides how it compounds."),
        table(["line", "basis", "cost"], rows),
        h(3, "The rig, which is bought once and flies every campaign"),
        deriv(rig_terms),
        h(3, "By time bucket"),
        para("What decides how a line compounds is WHEN it is spent, so the "
             "lines are bucketed before any rate is applied: up front at year "
             "zero, ongoing across the mission, or at the end. The "
             "contingency reserve is charged on all three."),
        deriv(bucket_terms),
        kv(buckets),
    ]
    if cst["wacc"] > 0:
        html_out.append(para(
            "Up-front money is compounded forward to the point of sale at a "
            "cost of capital of %s over %s years, a factor of %s; ongoing "
            "money is compounded over half the duration, and end-of-mission "
            "money not at all."
            % (pct(cst["wacc"], 1), fmt(out["M"]["duration"], 2),
               sig(cst["mult_up"], 4))))
        if cst["cal_cost"] != 1.0:
            html_out.append(note(
                "key",
                "The programme spans %s years, and the lines bought once at "
                "the start are carried across all of it: the bus NRE, the "
                "autonomy NRE and the rig compound by a further %s. The rig's "
                "salvage credit runs the other way, by %s, because it is "
                "collected at the end."
                % (fmt(cst["span"], 2), sig(cst["cal_cost"], 4),
                   sig(cst["cal_credit"], 4))))
    else:
        html_out.append(note(
            "ok",
            "<strong>No cost of capital is charged on this run</strong>, so "
            "every bucket is taken at face value and the programme calendar "
            "charge is inert with it: that term is time-value, and there is "
            "no rate for it to work on."))
    if a["isru"]:
        html_out.append(note(
            "ok",
            "The return propellant is billed at the ISRU processing rate "
            "rather than at a launch-price-per-kilogram, and it is an "
            "<strong>ongoing</strong> line rather than an up-front one: it is "
            "manufactured at the asteroid over the mining duration, not "
            "bought on Earth at year zero. That is worth more than the rate "
            "itself when a cost of capital is charged, because an ongoing "
            "line compounds over half the mission and an up-front one over "
            "all of it."))
    if cst["lc"] != 1.0:
        html_out.append(para(
            "Recurring hardware is discounted by a learning curve to a "
            "cumulative-average factor of %s across %d units."
            % (sig(cst["lc"], 6), P["n"])))
    total_terms = []
    if cst["wacc"] > 0:
        total_terms += [
            ("mult_up", "= (1 + r_c)^T_miss = %s^%s = %s"
             % (prec(1.0 + cst["wacc"], 6), prec(M["duration"], 12),
                prec(cst["mult_up"], 15))),
            ("mult_on", "= (1 + r_c)^(T_miss/2) = %s"
             % prec(cst["mult_on"], 15),
             "ongoing money is spent across the mission, so half of it"),
            ("mult_end", "= 1", "paid at the end, not carried"),
        ]
        if cst["cal_cost"] != 1.0:
            total_terms += [
                ("y", "= (1 + r_c)^T_cad = %s" % prec(cst["y"], 15)),
                ("cal", "= (y^W - 1) / ((y - 1) W) = %s"
                 % prec(cst["cal_cost"], 15),
                 "W campaigns are sequential, so articles bought at t = 0 are "
                 "carried across the whole %s yr span" % fmt(cst["span"], 2)),
                ("dC", "= (%s * (cal - 1)%s) * (1 + zeta) * mult_up = %s"
                 % (usd(cst["programme_upfront"], 2),
                    "" if not cst["terminal"] else " less the salvage credit",
                    usd(cst["delta"], 2))),
            ]
    total_terms += [
        ("C_tot", "= upfront * mult_up + ongoing * mult_on + end%s"
         % (" + dC" if cst["delta"] else "")),
        ("", "= %s * %s = %s"
         % (usd(cst["upfront"], 2), prec(cst["mult_up"], 12),
            usd(cst["upfront"] * cst["mult_up"], 2))),
        ("", "+ %s * %s = %s"
         % (usd(cst["ongoing"], 2), prec(cst["mult_on"], 12),
            usd(cst["ongoing"] * cst["mult_on"], 2))),
        ("", "+ %s * 1 = %s" % (usd(cst["end"], 2), usd(cst["end"], 2))),
    ]
    if cst["delta"]:
        total_terms.append(("", "+ %s" % usd(cst["delta"], 2),
                            "the programme calendar charge"))
    total_terms.append(("", "= %s" % usd(cst["total"], 4)))
    html_out.append(h(3, "Compounding forward to the point of sale"))
    html_out.append(deriv(total_terms))
    html_out.append(kv([
        ("<strong>total cost</strong>",
         "<strong>%s</strong>" % musd(cst["total"]))]))
    return "".join(html_out)


def s_answer(out):
    """Section 12: the objective, and what it does and does not say."""
    P = out["P"]
    rev, cst, M = P["rev"], P["cost"], out["M"]
    profit = P["expected"] - cst["total"]
    face = cst["upfront"] + cst["ongoing"] + cst["end"]
    # ⚠️  FOUR READINGS OF TWO NUMBERS.  The objective is a ratio and a
    # ratio is hard to feel; profit, cost per kilogram and the effective
    # compounding multiplier are the same two numbers said three other ways,
    # and none of them is a new measurement.  They are here because a reader
    # who cannot place 3x on any scale can place a dollar per kilogram.
    restated = [
        ("obj", "= C_tot / E[Rev] = %s / %s = %s"
         % (prec(cst["total"], 12), prec(P["expected"], 12),
            prec(P["obj"], 12)), "what the campaign ranks on"),
        ("profit", "= E[Rev] - C_tot = %s" % usd(profit, 2)),
        ("ROI", "= profit / C_tot = %s"
         % prec(profit / cst["total"] if cst["total"] else 0.0, 8)),
        ("$/kg", "= C_tot / m_pay = %s / %s = %s"
         % (prec(cst["total"], 12), prec(M["m_pay"], 12),
            prec(cst["total"] / M["m_pay"] if M["m_pay"] else 0.0, 12)),
         "against %s/kg the load actually fetches"
         % usd(rev["delivered"], 2)),
    ]
    if cst["wacc"] > 0 and face > 0:
        restated.append(
            ("mult_eff", "= C_tot / (buckets at face) = %s / %s = %s"
             % (prec(cst["total"], 12), prec(face, 12),
                prec(cst["total"] / face, 12)),
             "what the cost of capital and the calendar charge cost in total"))
    return "".join([
        sec("answer"),
        outputs([("obj", "%s x" % sig(P["obj"], 6), "cost over revenue; "
                  "lower is better and 1.0 is breakeven")]),
        deriv(restated),
        kv([("gross value of the load", musd(rev["capped"]["value"])),
            ("expected revenue", musd(P["expected"])),
            ("total cost", musd(P["cost"]["total"])),
            ("profit", musd(P["expected"] - P["cost"]["total"])),
            ("cost per kilogram returned",
             usd(P["cost"]["total"] / out["M"]["m_pay"], 2) + " /kg"),
            ("<strong>cost / revenue</strong>",
             "<strong>%s x</strong>" % sig(P["obj"], 6))]),
        # ⚠️  THE FILE IS SORTED ON PROFIT AND THE PROJECT RANKS ON THE RATIO,
        # which are different questions and pick different rows.  Showing both
        # is what stops a reader treating the first row of a catalog as its
        # best case.
        note("warn" if P["expected"] < P["cost"]["total"] else "ok",
             "Profit and the ratio are <strong>different questions</strong>: "
             "the output catalog is sorted by profit, and this project ranks "
             "on cost over revenue. The best case is the lowest ratio, which "
             "is not in general the first row of the file."),
        para("Lower is better and 1.0 is breakeven. This is the best case in "
             "the run that produced it, which is a statement about one body "
             "and one architecture rather than about asteroid mining."),
        note("warn",
             "The two surface delivery prices this model rests on are "
             "marginal-transport lower bounds: no programme overhead, no "
             "development cost beyond the NRE lines above, and an industrial "
             "launch cadence that does not exist yet. The number above is "
             "what the physics and the hardware cost, not what a programme "
             "would be quoted."),
    ])


def s_footer(out):
    """The verification footer, which is measured on every build."""
    c = out["check"]
    status = ("every derived quantity agrees with the model"
              if not c["bad"] else
              "<strong>%d quantities DISAGREE</strong>" % len(c["bad"]))
    return "".join([
        h(2, "Verification", "verification"),
        para("This document is generated by an independent derivation: the "
             "transfer, the tankage, the mass cascade and its fixed point, "
             "the electric stage, the plant, the knapsack, the clock, the "
             "ceilings and the whole cost cascade are written out from the "
             "equations here, not called out of the pipeline. What it reads "
             "from the model is reference data and table accessors."),
        # 🚨  THE SENTENCE ABOVE USED TO END THE PARAGRAPH, AND IT WAS
        # FALSE.  The derivation called the model's own night-side derate, its
        # synodic period and its delivered price, two of which sit inside
        # things that sentence NAMES -- the plant and the clock.  The first
        # two are written out here now and the third is compared rather than
        # printed, so the claim is true of every borrow that is left; what
        # remains is the search's SHAPE, which is deliberate and is therefore
        # DISCLOSED rather than denied.  The list is scanned off the
        # derivation's AST, so it cannot go stale the way the sentence did.
        # ⚠️  NO COUNT.  This sentence opened "One thing is borrowed"
        # above a derived list of three names -- a number in prose disagreeing
        # with the list beside it, in the paragraph written to stop exactly
        # that.  Name the list; do not state its length.
        para("What is borrowed on purpose, and is not derived here, is "
             "<strong>which</strong> programmes the search proposed. "
             "Reproducing the ladder's shape by hand would be a second "
             "opinion about what the search offered rather than a check on "
             "what it concluded, so the rungs are read from the model and "
             "every value at every rung is priced here. In full: %s."
             % ("; ".join("<code>%s</code> (%s)" % (esc(name), esc(why))
                          for name, why in out["borrows"])))
        if out.get("borrows") else
        para("Nothing at all is borrowed from the model beyond reference "
             "data: every decision on this page as well as every figure is "
             "made here."),
        para("The two are then compared column by column against the row the "
             "run actually produced, and %s: <strong>%d quantities, %d "
             "bit-exact, %d within %s, %d differing</strong>, worst "
             "relative difference %s on <code>%s</code>."
             % (status, c["n"], c["exact"], c["close"], "%g" % c["tol"],
                len(c["bad"]), "%.3e" % c["worst"], esc(c["worst_name"]))),
        # A count on its own cannot be read: 71 against 72 is the difference
        # between an archived cell and a current one, and saying so is the
        # whole reason the check returns the names.
        para("A further %d derived quantit%s no column in this row and could "
             "not be compared: %s. An archived cell predates the columns a "
             "later release added, which is why this is reported rather than "
             "refused." % (len(c["skipped"]),
                           "y has" if len(c["skipped"]) == 1 else "ies have",
                           ", ".join("<code>%s</code>" % esc(n)
                                     for n in c["skipped"])))
        if c.get("skipped") else "",
        para("The quantities compared, in the order the check walks them: "
             '<span class="small"><code>%s</code></span>.'
             % esc(", ".join(c["names"]))) if c.get("names") else "",
        '<p class="colophon small">Generated %s by '
        '<code>campaign/worked_calculation.py</code> from source '
        '<code>%s</code>, calc %s. Re-run it and every figure above moves '
        'with the model.</p>'
        % (datetime.date.today().isoformat(), esc(out["cell"]),
           esc(out["terms"]["stamp"])),
    ])


# ────────────────────────────────────────────────────────────────── the page
CSS = """
/* Every colour is a token, and every token is redefined once for dark mode.
   🚨  PRINT IS PINNED LIGHT.  The PDF is rendered by headless Chrome, which
   honours `prefers-color-scheme` from the HOST, so a dark-themed machine was
   one media query away from printing white-on-black over sixty pages.  The
   print block restates the light values rather than trusting the cascade. */
:root {
  color-scheme: light dark;
  --ink:        #16181d;   /* body text */
  --ink-soft:   #5b6270;   /* captions, notes, secondary cells */
  --ink-faint:  #8a90a0;   /* rules that should not be read as content */
  --paper:      #ffffff;
  --paper-sunk: #f6f7f9;   /* equations, substitutions, the contents rail */
  --line:       #e3e6ec;
  --line-firm:  #c3c8d2;
  --rule:       #16181d;   /* the heavy rule under a section heading */
  --accent:     #1f5fa8;   /* outputs, links, the key note */
  --accent-bg:  #eef4fb;
  --warn:       #9a5b08;
  --warn-bg:    #fdf5e9;
  --ok:         #2a6b31;
  --ok-bg:      #f0f7f0;
  --serif: Georgia, 'Iowan Old Style', 'Times New Roman', serif;
  --sans:  'Segoe UI', -apple-system, 'Helvetica Neue', Arial, sans-serif;
  --mono:  'Cascadia Mono', 'JetBrains Mono', Consolas, 'Liberation Mono',
           monospace;
  --measure: 46rem;        /* the text column */
  --rail: 15rem;           /* the contents rail beside it */
}
@media (prefers-color-scheme: dark) {
  :root {
    --ink: #e4e7ee; --ink-soft: #a2a9b8; --ink-faint: #6d7486;
    --paper: #14161a; --paper-sunk: #1c1f26;
    --line: #2b2f38; --line-firm: #3c424e; --rule: #8b93a4;
    --accent: #7fb2f0; --accent-bg: #172431;
    --warn: #d99b3c; --warn-bg: #2a2014;
    --ok: #86c98d; --ok-bg: #15251a;
  }
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  font: 16px/1.62 var(--serif);
  color: var(--ink); background: var(--paper);
  margin: 0; padding: 0 1.25rem;
  /* The rail and the column, side by side, centred as a pair.  Below the
     breakpoint the rail becomes an ordinary block at the top of the flow, so
     the same markup reads on a phone and prints as a contents page. */
  display: grid;
  grid-template-columns: 1fr minmax(0, var(--measure)) 1fr;
  column-gap: 2.5rem;
}
body > * { grid-column: 2; }

/* the title block */
.masthead { grid-column: 1 / -1; padding: 3.25rem 0 0;
            border-bottom: 1px solid var(--line); margin-bottom: 2.25rem; }
.masthead > div { max-width: calc(var(--measure) + var(--rail) + 2.5rem);
                  margin: 0 auto; padding-bottom: 2rem; }
.eyebrow { font: 600 .72rem/1.4 var(--sans); letter-spacing: .14em;
           text-transform: uppercase; color: var(--ink-soft);
           margin: 0 0 .5rem; }
h1 { font: 700 2.55rem/1.1 var(--serif); margin: 0 0 .65rem;
     letter-spacing: -.02em; }
.standfirst { font: 1.06rem/1.5 var(--serif); color: var(--ink);
              margin: 0 0 .5rem; max-width: 42rem; }
.standfirst strong { font-weight: 600; }
.terms { font: .9rem/1.5 var(--sans); color: var(--ink-soft);
         margin: 0; max-width: 42rem; }

/* The key figures, derived like everything else and set apart so the page
   answers its own question before the reader has scrolled once. */
.figs { display: grid; gap: .7rem; margin: 1.75rem 0 0;
        grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr)); }
.fig { border: 1px solid var(--line); border-radius: 6px;
       padding: .7rem .85rem; background: var(--paper-sunk); }
.fig .k { font: 600 .67rem/1.3 var(--sans); letter-spacing: .09em;
          text-transform: uppercase; color: var(--ink-soft);
          display: block; margin-bottom: .3rem; }
.fig .v { font: 600 1.3rem/1.15 var(--sans); font-variant-numeric: tabular-nums;
          letter-spacing: -.01em; display: block; }
.fig .u { font-size: .66em; font-weight: 400; color: var(--ink-soft); }
.fig.lead { border-color: var(--accent); background: var(--accent-bg); }
.fig.lead .v { color: var(--accent); }

/* the contents rail */
.toc { font: .88rem/1.45 var(--sans); background: var(--paper-sunk);
       border: 1px solid var(--line); border-radius: 6px;
       padding: 1rem 1.1rem; margin: 0 0 2.5rem; }
.toch { font: 600 .7rem/1 var(--sans); letter-spacing: .12em;
        text-transform: uppercase; color: var(--ink-soft);
        margin: 0 0 .7rem; padding: 0; border: none; }
.toc ol { margin: 0; padding: 0; list-style: none; }
.toc li { margin: 0; }
.toc a { display: flex; gap: .55rem; padding: .22rem 0;
         color: var(--ink); text-decoration: none; }
.toc a:hover { color: var(--accent); }
.tocn { color: var(--ink-faint); font-variant-numeric: tabular-nums;
        min-width: 1.1rem; text-align: right; }
.toc a.here { color: var(--accent); font-weight: 600; }
.toc a.here .tocn { color: var(--accent); }

@media (min-width: 62rem) {
  body { grid-template-columns:
           1fr var(--rail) minmax(0, var(--measure)) 1fr; }
  body > * { grid-column: 3; }
  .masthead { grid-column: 1 / -1; }
  .toc { grid-column: 2; grid-row: 2 / 500;
         position: sticky; top: 1.5rem; align-self: start;
         max-height: calc(100vh - 3rem); overflow-y: auto;
         background: none; border: none; padding: 0; margin: 0; }
}

/* headings */
h2 { font: 600 1.45rem/1.25 var(--serif); margin: 3rem 0 .9rem;
     padding-bottom: .3rem; border-bottom: 2px solid var(--rule);
     letter-spacing: -.01em; scroll-margin-top: 1.5rem; }
h3 { font: 600 1.01rem/1.35 var(--sans); margin: 2rem 0 .5rem;
     color: var(--ink); letter-spacing: -.005em; scroll-margin-top: 1.5rem; }
h2 a.anchor, h3 a.anchor { color: var(--ink-faint); text-decoration: none;
     opacity: 0; padding-left: .4rem; font-weight: 400; }
h2:hover a.anchor, h3:hover a.anchor { opacity: 1; }
p { margin: .85rem 0; }
a { color: var(--accent); }

/* tables */
.tw { overflow-x: auto; margin: 1.1rem 0; }
table { border-collapse: collapse; width: 100%; margin: 0;
        font: .89rem/1.45 var(--sans); }
th, td { text-align: left; padding: .4rem .7rem;
         border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-weight: 600; font-size: .77rem; letter-spacing: .05em;
     text-transform: uppercase; color: var(--ink-soft);
     border-bottom: 1px solid var(--line-firm); }
td:not(:first-child) { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover { background: var(--paper-sunk); }
table.kv td:first-child { width: 58%; }
table.sym td:not(:first-child) { text-align: left; }
table.sym td:first-child, table.sym td:nth-child(3), table.sym td:nth-child(4),
table.sym td:last-child { font-family: var(--mono); font-size: .93em; }
table.sym td:last-child { text-align: center; color: var(--ink-soft); }

/* equations and substitutions */
.eq { font: .86rem/1.5 var(--mono); background: var(--paper-sunk);
      border-left: 3px solid var(--line-firm); border-radius: 0 4px 4px 0;
      padding: .75rem 1rem; margin: 1.1rem 0; overflow-x: auto; }
.deriv { background: var(--paper-sunk); border-left: 3px solid var(--line-firm);
         border-radius: 0 4px 4px 0; padding: .55rem .35rem;
         margin: 1.1rem 0; overflow-x: auto; }
.deriv table, .out table { width: 100%; margin: 0;
        font: .82rem/1.5 var(--mono); }
.deriv td, .out td { border: none; padding: .1rem .6rem;
        vertical-align: baseline; white-space: nowrap; }
.deriv tbody tr:hover, .out tbody tr:hover { background: none; }
.deriv td:not(:first-child), .out td:not(:first-child) { text-align: left; }
.deriv .dsym, .out .dsym { width: 1%; color: var(--ink-soft); }
.deriv .dexp, .out .dexp { width: 1%; }
.deriv .dnote, .out .dnote { color: var(--ink-soft); white-space: normal;
        font-family: var(--sans); font-size: .95em; }
/* What a section PRODUCES, boxed at its head so the page can be skimmed. */
.out { background: var(--accent-bg); border-left: 4px solid var(--accent);
       border-radius: 0 4px 4px 0; padding: .55rem .35rem;
       margin: 1.1rem 0 1.5rem; }
.out .dsym { font-weight: 700; color: var(--accent); }

/* called-out paragraphs */
.note { border-left: 4px solid var(--line-firm); border-radius: 0 4px 4px 0;
        padding: .7rem 1rem; margin: 1.2rem 0; background: var(--paper-sunk);
        font-size: .96rem; }
.note.warn { border-color: var(--warn); background: var(--warn-bg); }
.note.ok   { border-color: var(--ok);   background: var(--ok-bg); }
.note.key  { border-color: var(--accent); background: var(--accent-bg); }
code { font-family: var(--mono); font-size: .9em; }
.small { color: var(--ink-soft); font-size: .85em; }
.colophon { border-top: 1px solid var(--line); margin-top: 3rem;
            padding: 1.25rem 0 4rem; }

/* print and PDF */
@media print {
  /* The light palette, restated: see the note at the top of this sheet. */
  :root {
    color-scheme: light;
    --ink: #16181d; --ink-soft: #555b66; --ink-faint: #8a90a0;
    --paper: #ffffff; --paper-sunk: #f4f5f7;
    --line: #dcdfe5; --line-firm: #b9bec8; --rule: #16181d;
    --accent: #14508f; --accent-bg: #eef3f9;
    --warn: #8a5207; --warn-bg: #fbf4e8;
    --ok: #235c29; --ok-bg: #eff5ef;
  }
  @page { margin: 16mm 14mm; }
  body { display: block; font-size: 10.2pt; line-height: 1.5; padding: 0; }
  .masthead { padding: 0; margin-bottom: 1.2rem; }
  .masthead > div { max-width: none; padding-bottom: 1rem; }
  h1 { font-size: 22pt; }
  /* The rail is a contents PAGE in print, and the sticky positioning that
     makes it a rail on screen would otherwise pin it to every page. */
  .toc { position: static; max-height: none; break-after: page;
         background: none; border: none; padding: 0; }
  .figs { grid-template-columns: repeat(auto-fit, minmax(0, 1fr));
          gap: .5rem; }
  .fig { break-inside: avoid; }
  h2 { break-after: avoid; font-size: 14pt; margin-top: 1.6rem; }
  h3 { break-after: avoid; }
  .tw { overflow-x: visible; margin: .9rem 0; }
  table, .note, .deriv, .out, .eq, .tw { break-inside: avoid; }
  tbody tr:hover { background: none; }
  h2 a.anchor, h3 a.anchor { display: none; }
  /* A substitution must not be clipped at the page edge, and print has no
     horizontal scroll to fall back on.  The longest line in this document is
     about 95 characters, which at this size clears an A4 text column. */
  .deriv table, .out table { font-size: 7.4pt; }
  .deriv td, .out td { padding: .06rem .45rem; }
  a { color: inherit; text-decoration: none; }
}
"""

# Which function renders which section.  The NUMBER and the TITLE are not
# here: `SECTION_ORDER` at the top of this file owns those, and this dict owns
# only the binding, so the two cannot disagree about either.  The assertion
# below is what holds them together.
SECTION_FN = {
    "nomenclature": s_nomenclature,
    "body":         s_body,
    "composition":  s_composition,
    "transfer":     s_transfer,
    "cascade":      s_cascade,
    "power":        s_power,
    "clock":        s_clock,
    "hold":         s_hold,
    "market":       s_market,
    "searches":     s_searches,
    "reliability":  s_reliability,
    "cost":         s_cost,
    "answer":       s_answer,
}
assert set(SECTION_FN) == set(SECTION_NO), (
    "SECTION_ORDER and SECTION_FN disagree about which sections exist: %s"
    % sorted(set(SECTION_FN) ^ set(SECTION_NO)))


def contents():
    """The contents list, numbered from the section list rather than typed."""
    items = "".join('<li><a href="#%s"><span class="tocn">%d</span>%s</a></li>'
                    % (anchor, SECTION_NO[anchor], esc(title))
                    for anchor, title in SECTION_ORDER)
    return ('<nav class="toc" aria-label="Contents"><h2 class="toch">'
            'Contents</h2><ol>%s'
            '<li><a href="#verification"><span class="tocn">&#183;</span>'
            'Verification</a></li></ol></nav>' % items)


# The only script on the page, and it is presentational: it marks which
# section the reader is in so a thirteen-section rail is navigable.  Nothing
# here computes, formats or moves a number, which is the line this document
# cannot cross -- a figure that arrived after the page was written could not
# be compared against the model or seen by the completeness audit, and the
# audit strips <script> before it reads anything.
#
# ⚠️  IT MUST DEGRADE TO NOTHING.  With JavaScript off, or in a PDF, the rail
# is a plain list of links and every section is still reachable; the only
# thing lost is the highlight.  That is why the `here` class is added here
# rather than baked into the markup.
SPY = """<script>
(function () {
  var links = {}, order = [];
  Array.prototype.forEach.call(
    document.querySelectorAll('.toc a[href^="#"]'), function (a) {
      var id = a.getAttribute('href').slice(1);
      if (document.getElementById(id)) { links[id] = a; order.push(id); }
    });
  if (!order.length) { return; }
  var current = null, queued = false;
  function mark() {
    queued = false;
    var found = order[0];
    for (var i = 0; i < order.length; i++) {
      if (document.getElementById(order[i]).getBoundingClientRect().top
          <= 140) { found = order[i]; }
    }
    if (found === current) { return; }
    if (current) { links[current].classList.remove('here'); }
    links[found].classList.add('here');
    current = found;
  }
  function schedule() {
    if (!queued) { queued = true; requestAnimationFrame(mark); }
  }
  addEventListener('scroll', schedule, { passive: true });
  addEventListener('resize', schedule, { passive: true });
  mark();
})();
</script>"""


def document(out):
    """The whole document, as one HTML string.

    Section order follows the order the model evaluates things, which is also
    the order in which each quantity becomes derivable: nothing on the page
    depends on a number that appears later.
    """
    body = [s_header(out), contents()]
    for anchor, _title in SECTION_ORDER:
        html_out = SECTION_FN[anchor](out)
        # 🚨  A SECTION MUST EMIT ITS OWN HEADING, EXACTLY ONCE.  Three of
        # these have early-return branches, and before the heading came out of
        # `sec()` each branch carried its own typed copy; a branch that forgot
        # one rendered under the heading above it and a branch that kept a
        # stale one rendered under the wrong number.  Both read as a
        # perfectly ordinary page.
        count = html_out.count('id="%s"' % anchor)
        assert count == 1, (
            "section %r emitted its anchor %d times, not once" % (anchor, count))
        body.append(html_out)
    body.append(s_footer(out))
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="generator" content="campaign/worked_calculation.py">'
        '<meta name="description" content="%s">'
        '<title>Worked calculation: %s</title><style>%s</style></head><body>'
        '%s%s</body></html>\n'
        % (esc(shape_sentence(architecture(out))), esc(out["designation"]),
           CSS, "".join(body), SPY)
    )
