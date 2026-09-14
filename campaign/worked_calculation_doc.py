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
    """Dollars, which are always large enough here to want separators."""
    return "$" + fmt(value, places)


def musd(value):
    """Dollars in millions, for the cost tables where the cents are noise."""
    return "$" + fmt(float(value) / 1e6, 2) + "M"


def pct(value, places=2):
    """A fraction rendered as a percentage."""
    return fmt(float(value) * 100.0, places) + "%"


def sig(value, places=6):
    """A ratio or a multiplier, where the digits matter more than the size."""
    return fmt(value, places)


def esc(text):
    """HTML-escape any value, including the ones that are not strings."""
    return html.escape(str(text))


# ─────────────────────────────────────────────────────────────────── layout
def h(level, text, anchor=None):
    """A heading, optionally anchored so the contents list can reach it."""
    tag = "h%d" % level
    ident = ' id="%s"' % anchor if anchor else ""
    return "<%s%s>%s</%s>" % (tag, ident, text, tag)


def para(text):
    """A paragraph of prose."""
    return "<p>%s</p>" % text


def note(kind, text):
    """A called-out paragraph: `warn`, `ok` or `key`."""
    return '<p class="note %s">%s</p>' % (kind, text)


def table(headers, rows, cls=""):
    """A table from a header list and a list of cell lists."""
    out = ['<table%s>' % (' class="%s"' % cls if cls else "")]
    out.append("<thead><tr>%s</tr></thead>"
               % "".join("<th>%s</th>" % c for c in headers))
    out.append("<tbody>")
    for r in rows:
        out.append("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r))
    out.append("</tbody></table>")
    return "".join(out)


def eq(text):
    """A display equation, set apart from the prose."""
    return '<div class="eq">%s</div>' % text


def kv(pairs):
    """A two-column definition table for a block of named quantities."""
    return table(["quantity", "value"], [[k, v] for k, v in pairs], "kv")


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
        "electric": float(row["dv_penalty_factor"]) > 1.0,
        "vehicle": str(row["vehicle"]),
        "propellant": str(row["propellant"]),
        "searched": bool(out["terms"]["searched"]),
        "ep_kg": float(M["ep"]["mass"]),
    }


def shape_sentence(a):
    """One sentence naming the architecture the search chose.

    Assembled from the shape rather than written down, because which of these
    clauses is true is exactly what the search decides per body.
    """
    bits = ["a %s mission" % ("beneficiated" if a["beneficiated"] else "raw")]
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
                       ("the cost of capital", terms["wacc"])):
        (on if live else off).append(name)
    if terms["surplus_frac"] > 0:
        on.append("a surplus sale at %s of full price"
                  % pct(terms["surplus_frac"], 0))
    else:
        off.append("any sale past a market ceiling")
    parts = []
    if on:
        parts.append("This run charged " + english(on) + ".")
    if off:
        parts.append("It did not charge " + english(off) + ".")
    return " ".join(parts)


def english(items):
    """`a`, `a and b`, or `a, b and c`."""
    items = list(items)
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


# ───────────────────────────────────────────────────────────────── sections
def s_header(out):
    """Title block: what this document is about and how it was produced."""
    a = architecture(out)
    C, P = out["C"], out["P"]
    body = esc(out["designation"])
    rows = [
        ("body", "%s  (%s)" % (body, esc(out["archived"].get("spectral_type",
                                                             "type unknown")))),
        # The ROW's destination, not the live config's.  See the guard in
        # `context`: those two disagreed silently until 2026-09-14, and this
        # line is where the disagreement was visible.
        ("destination", esc(C["destination"])),
        ("source", esc(out["cell"])),
        ("cost / revenue", "<strong>%s x</strong>" % sig(P["obj"], 4)),
        ("programme", "N = %d, %d ship(s) x %d campaign(s)"
         % (P["n"], P["f"], P["w"])),
        ("calc version", esc(out["terms"]["stamp"])),
        ("built", datetime.date.today().isoformat()),
    ]
    return "".join([
        h(1, "Worked calculation: %s" % body),
        para("<strong>%s</strong>" % shape_sentence(a)),
        para(terms_sentence(out["terms"])),
        kv(rows),
        note("key",
             "Every figure below is derived from the reference tables and the "
             "body's own orbital elements, in the order the model evaluates "
             "them. None is copied from the run's output. The footer reports "
             "what happened when the two were compared column by column."),
    ])


def s_body(out):
    """Section 1: the rock."""
    B, C = out["B"], out["C"]
    pairs = [
        ("absolute magnitude H", fmt(C["H"], 3)),
        ("geometric albedo", fmt(C["albedo"], 4)),
        ("diameter", fmt(B["d_km"], 6, "km")),
        ("bulk density", fmt(C["rho"], 3, "g/cm3")),
        ("volume", fmt(B["vol"], 1, "m3")),
        ("mass", fmt(B["mass"], 0, "kg")),
        ("mineable at %s of mass" % pct(C["cfg"].max_mining_fraction, 0),
         fmt(B["mineable"], 0, "kg")),
    ]
    return "".join([
        h(2, "1. The body", "body"),
        para("Diameter comes from the catalog where a measurement exists and "
             "from H and albedo where it does not. Mass follows from the "
             "diameter and the bulk density, and only a fraction of it is "
             "ever available: one mission cannot strip-mine an asteroid."),
        eq("D = 1329 / sqrt(p_v) * 10^(-H/5) km &nbsp;&nbsp; "
           "m = rho * (4/3) * pi * r^3"),
        kv(pairs),
    ])


def s_composition(out):
    """Section 2: what it is made of and what that is worth."""
    C = out["C"]
    rows = []
    for name, frac, price in sorted(C["phases"], key=lambda p: -p[2]):
        rows.append([esc(name), pct(frac, 3), usd(price, 2),
                     usd(frac * price, 2)])
    total = sum(f for _n, f, _p in C["phases"])
    rows.append(["<strong>total</strong>", "<strong>%s</strong>" % pct(total, 3),
                 "", "<strong>%s</strong>" % usd(C["bulk"], 2)])
    best = max(p[2] for p in C["phases"])
    out_html = [
        h(2, "2. Composition, and what a kilogram is worth", "composition"),
        para("The taxonomy fractions are priced separately rather than "
             "blended, because a concentrating mission chooses between them. "
             "Module 1's fractions sum to between 0.76 and 0.96, and the "
             "remainder is carried as the bulk-silicate residual in the last "
             "row rather than discarded, which is why the table totals one."),
        table(["phase", "mass fraction", "$/kg", "contribution"], rows),
    ]
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


def s_transfer(out):
    """Section 3: the patched-conic transfer and the launch window."""
    DV, C = out["DV"], out["C"]
    a = architecture(out)
    chosen = DV["aph"] if a["apsis"] == "aphelion" else DV["peri"]
    other = DV["peri"] if a["apsis"] == "aphelion" else DV["aph"]
    chosen_r = DV["aph_round"] if a["apsis"] == "aphelion" else DV["peri_round"]
    other_r = DV["peri_round"] if a["apsis"] == "aphelion" else DV["aph_round"]
    rows = [
        ("semi-major axis", fmt(C["a_au"], 6, "AU")),
        ("eccentricity", fmt(C["e"], 6)),
        ("inclination", fmt(C["inc"], 4, "deg")),
        ("perihelion q", fmt(DV["q_au"], 6, "AU")),
        ("aphelion Q", fmt(DV["Q_au"], 6, "AU")),
        ("orbital period", fmt(DV["t_ast"], 4, "yr")),
        ("departure burn", fmt(chosen["depart"], 4, "km/s")),
        ("plane change term", fmt(chosen.get("cos_i", 0.0), 6)),
        ("rendezvous match burn", fmt(chosen["match"], 4, "km/s")),
        ("capture at the destination", fmt(chosen["cap"], 4, "km/s")),
        ("outbound dv", fmt(DV["dv_out"], 1, "m/s")),
        ("return dv", fmt(DV["dv_ret"], 1, "m/s")),
        ("synodic period", fmt(DV["synodic"], 4, "yr")),
        ("expected window wait", fmt(DV["window_wait"], 4, "yr")),
    ]
    html_out = [
        h(2, "3. Getting there and back", "transfer"),
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
             % (esc(a["apsis"]), fmt(chosen_r, 3), fmt(other_r, 3),
                "perihelion" if a["apsis"] == "aphelion" else "aphelion")),
        kv(rows),
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
        ("return propellant", fmt(M["m_rprop"], 1, "kg")),
        ("return tankage", fmt(M["m_tank_ret"], 1, "kg")),
        ("mass at the asteroid", fmt(M["m_at"], 1, "kg")),
        ("outbound propellant", fmt(M["m_oprop"], 1, "kg")),
        ("outbound tankage", fmt(M["m_tank_out"], 1, "kg")),
        ("<strong>launch mass</strong>",
         "<strong>%s</strong>" % fmt(M["m_launch"], 1, "kg")),
        ("vehicle capacity to LEO", fmt(C["leo_cap"], 1, "kg")),
    ]
    html_out = [
        h(2, "4. The mass cascade", "cascade"),
        para("Payload is solved for, not specified. It is bounded by the "
             "rocket equation against the vehicle's capacity to LEO, and the "
             "solve is a fixed point because the payload sets the feed, the "
             "feed sets the dig time and the power draw, the draw sets the "
             "array mass, and the array comes out of the payload budget."),
        eq("m_pay_max = (M_LEO / R_out - m_hw - m_dry * s * R_ret) "
           "/ (s * R_ret - 1)"),
        table(["pass", "hardware in (kg)", "structure frac", "payload (kg)",
               "EP (kg)", "plant (kg)", "feed (kg)", "dig (yr)"], pass_rows),
        para("The loop converges in %d passes. The closed form then solves the "
             "cascade at the settled hardware mass:" % len(M["passes"])),
        kv([("bracket", fmt(cas["bracket"], 3)),
            ("denominator", fmt(cas["denom"], 6)),
            ("mass ratio outbound", fmt(M["R"], 6))]),
        h(3, "The hardware ledger"),
        para("Every kilogram in the cascade has a price in the cost model and "
             "every kilogram the cost model pays for is flown. That identity "
             "is the first thing to check when anything here looks wrong."),
        kv(ledger),
        h(3, "The stack, from the payload outwards"),
        kv(masses),
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
    else:
        html_out.append(note(
            "key", "The stage is <strong>chemical</strong>: it flies "
            "impulsive burns, pays no dv penalty and carries no electric "
            "power system."))
    if M["vol_cap"] and M["ret_vol"] > 0:
        html_out.append(para(
            "The returned cargo occupies %s m3 against a %s m3 fairing "
            "allowance, so the %s bound the payload."
            % (fmt(M["ret_vol"], 2), fmt(C["fairing_m3"], 1),
               "volume cap" if M["ret_vol"] >= C["fairing_m3"] * 0.999
               else "mass budget rather than the volume cap")))
    return "".join(html_out)


def s_power(out):
    """Section 5: the processing plant, which only some missions need."""
    M, C = out["M"], out["C"]
    a = architecture(out)
    if M["plant"] <= 0:
        return "".join([
            h(2, "5. Power", "power"),
            note("ok",
                 "<strong>This mission flies no power system.</strong> The "
                 "plant exists to run separation and water liberation, and a "
                 "run-of-mine mission carrying no ice needs neither. The dig "
                 "still costs time, which is what bounds the payload; it just "
                 "does not cost watts."),
        ])
    pairs = [
        ("processing draw", fmt(M["draw"], 1, "W")),
        ("plant specific power", fmt(C["w_plant"], 3, "W/kg")),
        ("plant mass", fmt(M["plant"], 1, "kg")),
    ]
    html_out = [
        h(2, "5. Power", "power"),
        para("Processing energy over the stay gives a draw, the draw gives an "
             "array, and the array is launched like everything else. This is "
             "the feedback the fixed point above exists to solve."),
        kv(pairs),
    ]
    if a["power"] == "rtg":
        html_out.append(note(
            "key",
            "The plant is a <strong>radioisotope source</strong>, flat at "
            "about 5 W/kg wherever it is. Solar falls as 1/r2 and the two "
            "cross near 3.46 AU, so a distant body is better served by "
            "nuclear heat. It is not free: a radioisotope watt costs several "
            "hundred times a solar one, and the binding constraint is Pu-238 "
            "supply rather than money."))
    else:
        html_out.append(note(
            "key",
            "The plant is <strong>solar</strong>, rated at 1 AU and derated "
            "by 1/r2 to this body's distance, then oversized by %s for the "
            "night side: a rig on a rotating body is in shadow about half the "
            "time, and the sunlit hours have to run the load and recharge the "
            "store. The dark period used for storage is this body's own "
            "rotation, %s h."
            % (fmt(C["oversize"], 3), fmt(C["dark_h"], 2))))
    return "".join(html_out)


def s_clock(out):
    """Section 6: how long the mission takes, and how often it repeats."""
    M, DV = out["M"], out["DV"]
    pairs = [
        ("feed processed", fmt(M["feed"], 0, "kg")),
        ("dig time", fmt(M["dig_yr"], 4, "yr")),
        ("stay at the asteroid", fmt(M["stay"], 4, "yr")),
        ("outbound transfer", fmt(M["t_out"], 4, "yr")),
        ("return transfer", fmt(M["t_back"], 4, "yr")),
        ("window wait", fmt(DV["window_wait"], 4, "yr")),
        ("<strong>mission duration</strong>",
         "<strong>%s</strong>" % fmt(M["duration"], 4, "yr")),
        ("campaign cadence", fmt(M["cadence"], 4, "yr")),
        ("rig trips, calendar bound", fmt(M["calendar_cap"], 0)),
        ("<strong>trips this rig serves</strong>",
         "<strong>%d</strong>" % M["trips"]),
    ]
    bound = ("the calendar" if M["calendar_cap"] <= M["trips"]
             else "its duty cycles")
    return "".join([
        h(2, "6. The clock", "clock"),
        para("Extraction is rate-limited: the payload is capped by what the "
             "rig can dig inside the stay, and the dig time flows into "
             "operations cost, into the mission duration and into how often "
             "the campaign can repeat."),
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
    html_out = [h(2, "7. The hold", "hold")]
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
    html_out.append(kv([
        ("blended value", usd(load["usd_per_kg"], 2) + " /kg"),
        ("cargo water", fmt(M["water"], 1, "kg")),
        ("containment fraction", fmt(M["c_frac"], 5)),
    ]))
    return "".join(html_out)


def s_market(out):
    """Section 8: what the load actually sells for."""
    P, C = out["P"], out["C"]
    rev = P["rev"]
    frac = rev["surplus_frac"]
    rows = []
    for key, allowance in sorted(rev["allow"].items()):
        rows.append([esc(key), fmt(C["market_kg"].get(key, float("inf")), 0),
                     fmt(allowance, 1)])
    html_out = [
        h(2, "8. The market", "market"),
        para("Prices are constant at any volume and what bounds a programme "
             "is how much the destination can absorb while it waits. A bigger "
             "fleet delivers more often, so each delivery gets a shorter "
             "slice of the market's annual capacity."),
        eq("allowance = ceiling_kg_per_yr * "
           "[duration + (N - 1) * cadence / F] / N"),
        kv([("accumulation window", fmt(rev["window"], 4, "yr")),
            ("gross value, unbounded", musd(rev["gross_base"])),
            ("value after the ceilings", musd(rev["capped"]["value"])),
            ("market clearing fraction", sig(rev["clearing"], 6)),
            ("delivered value", usd(rev["delivered"], 2) + " /kg")]),
        table(["market", "ceiling (kg/yr)", "this delivery may sell (kg)"],
              rows),
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
    html_out = [h(2, "9. The searches", "searches")]
    if a["beneficiated"]:
        rows = []
        for kind, ratio, priced in sweep["rungs"]:
            if not priced:
                rows.append([kind, fmt(ratio, 4), "does not close", "", ""])
                continue
            best = priced["ladder"]["best"]
            rows.append([kind, fmt(ratio, 4), fmt(priced["M"]["m_pay"], 0),
                         fmt(priced["M"]["feed"], 0), sig(best["obj"], 4)])
        html_out.append(para(
            "How hard to concentrate is an economic decision, not a setting. "
            "Grade saturates once the hold is pure best-phase while the costs "
            "do not, so the value curve is concave and the optimum is usually "
            "strictly interior."))
        html_out.append(table(
            ["rung", "ratio", "payload (kg)", "feed (kg)", "cost / revenue"],
            rows))
        html_out.append(para(
            "The sweep runs to a saturation ratio of %s and the winner is "
            "%s to one." % (fmt(sweep["r_max"], 3), fmt(out["M"]["ratio"], 4))))
    else:
        html_out.append(para(
            "This mission does not concentrate, so there is no concentration "
            "sweep to show: the hold is the body's composition at whatever "
            "payload the cascade closes."))
    if a["searched"]:
        rows = []
        for p in sorted(ladder["coarse"] + ladder["refine"],
                        key=lambda x: x["obj"])[:12]:
            rows.append([p["n"], p["f"], p["w"], musd(p["cost"]["total"]),
                         musd(p["expected"]), sig(p["obj"], 4)])
        html_out.append(h(3, "The programme ladder"))
        html_out.append(para(
            "Programme size is searched jointly with everything else. A "
            "larger programme amortises the non-recurring costs over more "
            "missions; a larger fleet delivers more often and each delivery "
            "gets a smaller slice of the market. The optimum is where those "
            "two turn over, and it is interior."))
        html_out.append(table(
            ["N", "ships", "campaigns/ship", "cost", "expected revenue",
             "cost / revenue"], rows))
        html_out.append(para(
            "%d programmes were priced; the best is N = %d."
            % (len(ladder["coarse"]) + len(ladder["refine"]), out["P"]["n"])))
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
            h(2, "10. Reliability", "reliability"),
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
        h(2, "10. Reliability", "reliability"),
        para("Revenue is not certain: the launch can fail, the spacecraft can "
             "die in transit, and the mining chain has never been "
             "demonstrated. Expected revenue is multiplied by the product "
             "below while costs are charged in full, which is the "
             "conservative and correct treatment: the money is spent either "
             "way."),
        eq("P = p_launch * exp(-T / MTBF) * p_mining"),
        kv([("launch reliability", sig(rel["p_launch"], 4)),
            ("spacecraft MTBF", fmt(rel["mtbf"], 2, "yr")),
            ("cruise survival", sig(rel["p_cruise"], 6)),
            ("mining success, fleet average", sig(rel["p_mining"], 6)),
            ("<strong>P(success)</strong>",
             "<strong>%s</strong>" % sig(rel["p_succ"], 6))]),
    ])


def s_cost(out):
    """Section 11: the cost cascade, line by line."""
    P = out["P"]
    cst = P["cost"]
    lines = cst["lines"]
    order = [("launch", "launch"), ("outbound propellant", "oprop"),
             ("return propellant", "rprop"), ("mining rig share", "rig"),
             ("return capsule", "capsule"), ("power system", "plant"),
             ("electric stage", "ep"), ("tankage", "tank")]
    rows = [[name, musd(lines[key])] for name, key in order if key in lines]
    rows += [["operations", musd(cst["ops"])],
             ["spacecraft NRE / N", musd(cst["nre"])],
             ["autonomy NRE / N", musd(cst["autonomy"])],
             ["licensing", musd(cst["licensing"])],
             ["berthing and handover", musd(cst["handover"])]]
    if cst["terminal"]:
        rows.append(["rig terminal value",
                     "-" + musd(cst["rig_credit_share"])])
    buckets = [
        ("up-front, after contingency", musd(cst["upfront"])),
        ("ongoing, after contingency", musd(cst["ongoing"])),
        ("end of mission, after contingency", musd(cst["end"])),
        ("contingency at %s" % pct(cst["contingency"] / max(
            cst["upfront_lines"] + cst["ops"] + cst["handover"], 1e-9), 0),
         musd(cst["contingency"])),
    ]
    html_out = [
        h(2, "11. The cost cascade", "cost"),
        para("Every line comes from the reference tables; none is invented "
             "here. The lines are then bucketed by WHEN the money is spent, "
             "because that is what decides how it compounds."),
        table(["line", "cost"], rows),
        h(3, "By time bucket"),
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
    if cst["lc"] != 1.0:
        html_out.append(para(
            "Recurring hardware is discounted by a learning curve to a "
            "cumulative-average factor of %s across %d units."
            % (sig(cst["lc"], 6), P["n"])))
    html_out.append(kv([
        ("<strong>total cost</strong>",
         "<strong>%s</strong>" % musd(cst["total"]))]))
    return "".join(html_out)


def s_answer(out):
    """Section 12: the objective, and what it does and does not say."""
    P = out["P"]
    rev = P["rev"]
    return "".join([
        h(2, "12. The answer", "answer"),
        kv([("gross value of the load", musd(rev["capped"]["value"])),
            ("expected revenue", musd(P["expected"])),
            ("total cost", musd(P["cost"]["total"])),
            ("<strong>cost / revenue</strong>",
             "<strong>%s x</strong>" % sig(P["obj"], 6))]),
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
        para("The two are then compared column by column against the row the "
             "run actually produced, and %s: <strong>%d quantities, %d "
             "bit-exact, %d within 1e-12, %d differing</strong>, worst "
             "relative difference %s on <code>%s</code>."
             % (status, c["n"], c["exact"], c["close"], len(c["bad"]),
                "%.3e" % c["worst"], esc(c["worst_name"]))),
        para('<span class="small">Generated %s from source <code>%s</code>, '
             'calc %s.</span>'
             % (datetime.date.today().isoformat(), esc(out["cell"]),
                esc(out["terms"]["stamp"]))),
    ])


# ────────────────────────────────────────────────────────────────── the page
CSS = """
:root { color-scheme: light; }
body { font: 15px/1.55 Georgia, 'Times New Roman', serif; color: #1a1a1a;
       max-width: 52em; margin: 0 auto; padding: 3em 2em 6em; background: #fff; }
h1 { font-size: 2em; margin: 0 0 .2em; letter-spacing: -.01em; }
h2 { font-size: 1.3em; margin: 2.2em 0 .6em; padding-bottom: .25em;
     border-bottom: 2px solid #1a1a1a; }
h3 { font-size: 1.05em; margin: 1.6em 0 .4em; color: #333; }
p { margin: .7em 0; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; font-size: .93em;
        font-family: 'Segoe UI', Helvetica, Arial, sans-serif; }
th, td { text-align: left; padding: .38em .7em; border-bottom: 1px solid #ddd;
         vertical-align: top; }
th { background: #f4f4f2; font-weight: 600; border-bottom: 1.5px solid #bbb; }
td:not(:first-child) { text-align: right; font-variant-numeric: tabular-nums; }
table.kv td:first-child { width: 58%; }
tr:last-child td { border-bottom: none; }
.eq { font-family: 'Cascadia Mono', Consolas, monospace; background: #f7f7f5;
      border-left: 3px solid #999; padding: .7em 1em; margin: 1em 0;
      font-size: .9em; overflow-x: auto; }
.note { border-left: 4px solid #999; padding: .6em 1em; margin: 1.1em 0;
        background: #fafafa; }
.note.warn { border-color: #b4690e; background: #fdf6ec; }
.note.ok   { border-color: #2e7d32; background: #f1f8f1; }
.note.key  { border-color: #1565c0; background: #eff5fc; }
code { font-family: 'Cascadia Mono', Consolas, monospace; font-size: .92em; }
.small { color: #666; font-size: .85em; }
.toc { font-family: 'Segoe UI', Helvetica, Arial, sans-serif; font-size: .92em;
       background: #f7f7f5; padding: 1em 1.4em; margin: 1.5em 0; }
.toc ol { margin: .3em 0; padding-left: 1.4em; }
@media print {
  body { max-width: none; padding: 0; font-size: 10.5pt; }
  h2 { page-break-after: avoid; } table { page-break-inside: avoid; }
  .note { page-break-inside: avoid; }
}
"""

SECTIONS = [
    ("1. The body", "body", s_body),
    ("2. Composition", "composition", s_composition),
    ("3. Getting there and back", "transfer", s_transfer),
    ("4. The mass cascade", "cascade", s_cascade),
    ("5. Power", "power", s_power),
    ("6. The clock", "clock", s_clock),
    ("7. The hold", "hold", s_hold),
    ("8. The market", "market", s_market),
    ("9. The searches", "searches", s_searches),
    ("10. Reliability", "reliability", s_reliability),
    ("11. The cost cascade", "cost", s_cost),
    ("12. The answer", "answer", s_answer),
]


def contents():
    """The table of contents, built from the section list rather than typed."""
    items = "".join('<li><a href="#%s">%s</a></li>' % (anchor, title)
                    for title, anchor, _fn in SECTIONS)
    return ('<div class="toc"><strong>Contents</strong><ol>%s'
            '<li><a href="#verification">Verification</a></li></ol></div>'
            % items)


def document(out):
    """The whole document, as one HTML string.

    Section order follows the order the model evaluates things, which is also
    the order in which each quantity becomes derivable: nothing on the page
    depends on a number that appears later.
    """
    body = [s_header(out), contents()]
    for _title, _anchor, fn in SECTIONS:
        body.append(fn(out))
    body.append(s_footer(out))
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>Worked calculation: %s</title><style>%s</style></head><body>"
        "%s</body></html>\n" % (esc(out["designation"]), CSS, "".join(body))
    )
