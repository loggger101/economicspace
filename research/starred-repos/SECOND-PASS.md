# Second pass over the same 17 repositories

[`FINDINGS.md`](FINDINGS.md) and [`SOURCES.md`](SOURCES.md) are the first pass.
This is a re-read of the same seventeen with a different question: not "what is
this repository for" but "what is in it that the first pass did not open".

The star list was re-checked against the GitHub API before starting. It is
still exactly the seventeen `SOURCES.md` names, so nothing here is a new
repository; everything is something that was already starred and not seen.

**Four findings. Two of them are measurements on this repo's own catalog and
one of those retires an assumption `FINDINGS.md` F4 rests on.** The other two
are capability findings: things that are now possible and were not.

| finding | what it is | status |
|---|---|---|
| [F6](#f6-two-independent-delta-v-oracles-exist-and-neither-was-used) | NHATS and Shoemaker-Helin, two external delta-v oracles, measured | **measured**, [`probe_nhats.py`](probe_nhats.py) |
| [F7](#f7-brahe-is-not-thin-any-more-and-it-closes-space-mapmds-open-item) | brahe ships a native SPICE reader and a Horizons SPK client, MIT | verified live |
| [F8](#f8-space-datasets-was-read-at-2-per-cent) | space-datasets was read at 4 scripts out of about 200 | inventory |
| [F9](#f9-astroquery-carries-an-orbit-covariance-client) | astroquery has a NEODyS client returning full orbit covariance | verified live |

🚨  **Nothing here is wired into the pipeline.** One probe was added. No
module, config or CSV was touched and no `pipeline_version` moved. Every fetch
below is a read of a public API; none of them runs Stage 1, 2 or 3, so none can
invalidate a `.verify` baseline.

---

## F6. Two independent delta-v oracles exist, and neither was used

F4's whole argument rests on a Lambert oracle **built in this repository** and
validated against three published missions. It is a good instrument and it is
ours, which is the one thing that cannot be said for it. Two oracles built by
other people were sitting in the starred set and were not opened.

### The two instruments

**NHATS**, `ssd-api.jpl.nasa.gov/nhats.api`, reached through
`juliensimon/space-datasets`' `scripts/update-nhats.py`. It is JPL's own
numerically optimised **round-trip** delta-v for every NEA it can find a viable
crewed trajectory for: 7,033 bodies, one HTTP call, no kernels, no solver.
Real ephemerides, multi-revolution transfers, the lot.

**Shoemaker-Helin**, the standard published closed-form NEO delta-v
approximation, carried as Asterank's `dv` column over about 600,000 bodies.
Asterank is also the direct prior art for this entire project: somebody else's
economic ranking of the same population.

⚠️  **Asterank's economics are not usable and its delta-v is.** `price`,
`profit` and `saved` come back as 1e-42 and 0.0 through the public endpoint,
which is not a rounding problem. Take the `dv` column and leave the rest.

### What they say

`py research/starred-repos/probe_nhats.py --asterank`, on the 1,555,667-row
catalog on disk:

```
NHATS  : 7,033 NEAs from JPL
joined : 7,006  (99.6% of NHATS)

  perihelion rendezvous wins    : 1,639  (23.4%)
  shipped one-way        median :   4.657 km/s
  NHATS round-trip (JPL) median :   9.367 km/s
  ratio one-way / round-trip    : median 0.5194  p90 0.7075  max 1.0788
  ONE-WAY EXCEEDS ROUND TRIP    : 14 / 7,006  (0.20%)

  rank agreement with JPL (Spearman) : 0.5976
    U <= 2   n =    960   0.6135
    U <= 4   n =  1,435   0.6590
    U >= 5   n =  5,571   0.5852

SHOEMAKER-HELIN  (n = 1,000 joined)
  shipped one-way  median :   8.423 km/s
  Shoemaker-Helin  median :   8.140 km/s
  gap S-H minus shipped   : median -0.272  mean -0.921
  shipped BELOW S-H       : 420 / 1,000  (42.0%)
  rank agreement (Spearman) : 0.9494
```

**The shipped estimator agrees with the other closed form at 0.949 and with
JPL at 0.598.** That is the finding, and it is the shape F4 predicted from a
different direction: the disagreement is not between this pipeline and the
literature, it is between **closed-form patched conics as a family** and real
optimised trajectories. F4 built one Lambert oracle and got the same answer;
JPL's 7,033-body answer is now the second witness, and it is not ours.

⚠️  **It does NOT confirm F4's magnitude, and must not be quoted as though it
did.** F4 measures a one-way gap of about +1.30 km/s. NHATS is round-trip,
crewed, and constrained (stay at least 8 days, total under 450 days, entry
speed capped), so its number is an upper bound on a differently-shaped
quantity. What transfers is the **rank** disagreement and its sign, not the
kilometres per second.

### The one hard inconsistency

**14 bodies where the shipped ONE-WAY leg costs more than JPL's whole ROUND
TRIP.** NHATS excludes the Earth arrival capture, so its total is the LEO
departure plus the outbound match plus the return departure, and the shipped
`dv_out` is the first two of those three. One-way above round-trip is therefore
structurally impossible rather than merely surprising.

They are a coherent set: median `a` 1.005 au, `e` 0.110, `i` 1.43 deg, largest
excess 0.297 km/s. Earth co-orbital bodies, where the patched conic degenerates
because the transfer ellipse is barely an ellipse. 0.20% of the accessible
population, and the error is small, but it is the only place in the delta-v
model where an external check says the answer is not merely imprecise but the
wrong side of a bound.

### It corroborates SPACE-MAP.md with a different instrument

**79.5% of the NHATS accessible population carries an orbit condition code of
5 or worse**, against 13.9% of the catalog. The economically attractive NEO
population is enriched about 5.7x in badly-determined orbits, measured on
JPL's own accessibility list rather than on this pipeline's ranking.

[SPACE-MAP.md](SPACE-MAP.md) found the same thing by looking at the top of the
profitability ranking and worrying about a winner's curse. This says the
enrichment is a property of the **accessible population**, not only of the
selection: low delta-v NEAs are small, faint and recently discovered, so they
have short arcs. That is a stronger and less flattering statement than the
selection effect, because no ranking change removes it.

✅  And the rank agreement moves the right way with orbit quality: 0.659 at
U <= 4 against 0.585 at U >= 5. Part of the disagreement with JPL is the
orbits, not the model.

### 🚨 The first reading of this was wrong, and the reason is worth keeping

The first run of this probe priced **aphelion only**, copying
[`probe_plane_change.py`](probe_plane_change.py), which does the same and is
correct to do so because it is comparing placements of a plane change and holds
the apsis fixed on both sides.

It reported **43 violations and a rank agreement of 0.4006**, and the violators
looked like a beautiful finding: every one an interior NEO with `a` under 1 au.

They were an artefact. `asteroid_transfer_dv_km_s` prices both apsides and the
architecture search takes the winner, and **perihelion wins on 23.4% of the
NEO population**, which is exactly the interior bodies. Pricing both apsides
drops the violations to 14 and lifts the agreement to 0.5976.

⚠️  Both numbers reproduced the docstring's five reference bodies to four
decimals, because **all five of those resolve to aphelion**. The reference
check passed on a probe that was measuring the wrong model. That is this
repo's own rule arriving with a new example: *reproducing the validated figures
is necessary and not sufficient*, and a broken checker looks exactly like a
broken release.

---

## F7. brahe is not thin any more, and it closes SPACE-MAP.md's open item

`SOURCES.md` files `duncaneddy/brahe` under "thin for this project": *"good
library, wrong domain: Earth-orbit operations, ground stations, EOP, TLEs,
space weather. Nothing heliocentric."*

That was true. It is not true now, and the difference is exactly the thing
[SPACE-MAP.md](SPACE-MAP.md) section 4 says is missing.

| what it now ships | why it matters here |
|---|---|
| `src/spice/` : a native DAF, SPK and binary PCK reader in Rust, no CSPICE | SPACE-MAP.md says reading kernels "needs `spiceypy`", which is what made the oracle validation a heavy lift |
| **SPK type 21** | the segment type Horizons emits **for small bodies**. Its own comment says so, and its test fixture is a Ceres type-21 segment |
| `src/spice/validation.rs` | the reader is validated against ANISE as an independent oracle, at matched ephemeris time |
| `datasets.horizons` : `HorizonsClient.get_spk()` | generates and caches a **targeted SPK for any small body** through the Horizons API |
| `datasets.sbdb` : `SBDBClient.lookup()` | resolves a designation to the NAIF or SPK id that request needs |

🚨  **The Horizons client is the part that changes the economics.**
SPACE-MAP.md prices this work in kernel downloads: 646 MB for 16 bodies, 15.2
GB for 373. Horizons will generate an SPK for **an arbitrary body on demand**,
cached, at a few hundred kilobytes. So the two-body error in F4's oracle can be
bounded on the bodies F4 actually sampled, rather than on whichever 373 bodies
JPL chose to pre-integrate.

✅  **It installs on this host.** `brahe` 1.7.0 on PyPI ships a
`cp314-cp314-win_amd64` wheel, and `platform_check.py` reports this machine at
Python 3.14.6. No Rust toolchain and no CSPICE build.

⚠️  **Offline validation harness only, never a pipeline dependency**, for the
reason SPACE-MAP.md already gives and one more: it is a compiled extension, and
this project's bit-identity argument does not want a second libm in the room.
It belongs beside `verify.py`, not in `_MASTER_REQUIRED`.

⚠️  **This is the "measured and declined" list's own lesson inverted.** That
list exists so nobody re-derives an item that was already priced. A *verdict*
is not a measurement and does not keep: brahe's verdict was correct when
written and had rotted by the time it was read, because the repository moved.
**Re-read a rejected star before trusting the rejection**, which is the whole
premise of this second pass.

---

## F8. space-datasets was read at 2 per cent

`SOURCES.md` calls this "the highest information-per-byte star in the set" and
then names **four** files. The repository carries about **200** dataset
scripts, and the four named are the four that were relevant to the questions
being asked that day.

Everything below is a live, keyless, cited source of exactly the kind this
pipeline's softest numbers are asserted without.

| script | what it fetches | which soft assumption it touches |
|---|---|---|
| `update-nhats.py` | JPL NHATS accessibility, 7,033 NEAs | **F6 above.** The one that turned out to matter |
| `update-asterank.py` | Asterank, about 600k bodies with Shoemaker-Helin delta-v and a full economic ranking | F6, and the only direct prior art this project has |
| `update-nesvorny-families.py` | Nesvorny HCM families V2.0, about 170k asteroids in 274 collisional families | **F2.** Family membership is composition evidence: fragments of one parent body share a parent. It is the hierarchical structure a PyMC prior would want, and F2 currently proposes a flat categorical |
| `update-bus-demeo.py` | Bus-DeMeo taxonomy, 371 asteroids plus principal-component scores | F2. The *reference* taxonomy that defines the classes `TAXONOMY_COMPOSITION` keys on |
| `update-lcdb.py` | the asteroid lightcurve database: rotation periods, family codes, taxonomy | rotation bears on whether a rubble pile can be anchored to and dug at all, which the model assumes |
| `update-launch-cost.py` | 63 launch vehicles, cost per kg to LEO, 2024 USD, **cited per row** | **the most load-bearing external number in the project.** In-space value is dominated by launch-cost-avoided |
| `update-lunar-geochemistry.py` | Astromat and EarthChem lunar sample geochemistry | `IN_SPACE_UTILITY_BY_DESTINATION`'s lunar overrides, which CLAUDE.md calls engineering judgements and the softest assumption in the pipeline |
| `update-meteorites.py` | Wikidata meteorite classes and masses | ground truth for the metal and carbon fractions in `TAXONOMY_COMPOSITION` |
| `update-ssodnet.py` | a second implementation of the SsODNet fetch | worth diffing against `fetch_ssodnet`, which lost an entire source for four releases to a column rename |

✅  Both HuggingFace mirrors used above are live and were checked:
`nhats-accessible-asteroids` (updated 2026-09-03) and
`asterank-asteroid-mining`. The Bus-DeMeo tables were fetched directly from
the PDS Small Bodies Node and are 371 rows each.

⚠️  **`update-launch-cost.py` disagrees with this model's own vehicle table and
that disagreement is worth an hour.** It puts Falcon Heavy at 63,800 kg
expendable and 50,000 kg reusable; CLAUDE.md quotes 57 t. New Glenn agrees at
45,000 kg. The pipeline's numbers may well be the better ones, and a cited
independent table is the cheapest way to find out which rows were never
checked.

ℹ️  **This also half-rehabilitates `pds4_tools`.** `SOURCES.md` says it is
"useful only if a PDS4 small-body archive is ever wanted". Bus-DeMeo is a PDS4
small-body archive and is wanted. It still does not need the library, because
the archive serves flat `.tab` tables next to the XML labels, which is the same
answer the SDSS table gave. The verdict survives; the reasoning behind it does
not.

---

## F9. astroquery carries an orbit-covariance client

`SOURCES.md` names four astroquery modules. There are about sixty, and one of
the ones not named answers a question SPACE-MAP.md leaves explicitly open.

`astroquery/solarsystem/neodys/core.py` wraps **NEODyS**, which returns, per
NEO, the equinoctial and Keplerian state vectors, the RMS, the eigenvalues, and
the **full 6x6 covariance matrix**. Verified live against `2000 SG344`, which
is one of the fourteen bodies F6 flags.

SPACE-MAP.md's finding is that the ranking could not see orbit quality, and its
closing paragraph is a deliberate non-decision:

> A U cutoff, an arc-length floor and a confidence-weighted ranking are all
> defensible and they answer different questions. Choosing one changes what the
> model says, so it is a modelling decision.

`condition_code` is a coarse integer from 0 to 9, so all three of those options
are ways of thresholding a scalar. A covariance is different in kind: push it
through the delta-v estimator and you get a **distribution over
`cost_revenue_ratio` for that body**, which is an error bar rather than a
filter, and it needs no cutoff to be chosen.

⚠️  **One HTTP call per object**, like `jplsbdb` and unlike the bulk SBDB
fetch, so it cannot run over 1.55 M rows and does not need to. The scope that
matters is the top of the ranking, which is 30 to 200 bodies and is precisely
where SPACE-MAP.md measured the 3.1x enrichment.

ℹ️  Two other unnamed astroquery modules are worth knowing exist: `mpc` (a
fifth catalog source) and `imcce` (Miriade and SkyBoT, from the institution
that runs SsODNet, which is already one of the four sources).

---

## Revised verdicts

Only the rows that moved. Everything else in
[`SOURCES.md`](SOURCES.md) stands as written.

| repository | was | now |
|---|---|---|
| **duncaneddy/brahe** | tier 3, "wrong domain, nothing heliocentric" | **tier 1.** MIT SPICE reader with SPK type 21, plus a Horizons SPK client. Closes SPACE-MAP.md section 4 |
| **juliensimon/space-datasets** | tier 1, four files named | **tier 1, and read at 2%.** NHATS alone produced F6 |
| **astropy/astroquery** | tier 1, four modules named | **tier 1, plus NEODyS.** Full orbit covariance, which `condition_code` cannot express |
| **Small-Bodies-Node/pds4_tools** | tier 2, "only if a PDS4 archive is ever wanted" | verdict unchanged, reasoning retired. Bus-DeMeo is that archive and still does not need the library |

Re-checked and unchanged, so nobody re-opens them: **Celestia** really does
ship no asteroid catalogs, only `.cel` demo scripts and locale copies of them,
the content lives in a separate repository. **OpenSCvx** still has no orbital
transfer example; the examples are robot arms, aircraft and abstract control.
**pygmo2**, **pyomo**, **z3**, **pymc**, **polars** and **mesa** carry nothing
domain-specific that the first pass missed; each was grepped for it. **nyx**
ships kernels and gravity models under `data/`, but they are NASA products
better fetched from NAIF than from an AGPL repository. **spacekit** and
**CamPyRoS** are as described.

---

## What I would do, in order

1. **Take F6's fourteen violations seriously and nothing else about F6 as a
   number.** They are a real inconsistency in the delta-v model at Earth
   co-orbital geometry, they are cheap to reproduce, and unlike F1 and F4 they
   do not require a decision about re-measuring the campaign. The rank
   disagreement with JPL is a corroboration of F4's direction and is not a
   second estimate of its size.
2. **Run the pipeline's own vehicle table against `update-launch-cost.py`.**
   An afternoon, no model change, and it checks the number the entire in-space
   valuation rests on against a cited independent compilation.
3. **Add NEODyS covariance to the top of the ranking** (F9). It converts
   SPACE-MAP.md's open modelling decision into an error bar and needs no cutoff
   to be argued for.
4. **Pull the Nesvorny families** (F8) before building anything with PyMC. F2
   proposes a flat categorical prior over `spectral_type`; family membership is
   the hierarchy that prior actually has, and it is 170,000 bodies of it.
5. **Bound F4's oracle with brahe** (F7), now that it costs a pip install and
   a few hundred kilobytes per body instead of 15.2 GB and a CSPICE build.
   Until it is bounded, F4's +1.30 km/s carries an unmeasured two-body error.
6. Everything else in F8's table is real and none of it is urgent.

⚠️  **Items 1 to 4 move no number a run produces.** Item 5 does not either; it
puts an error bar on one. Nothing in this pass is a release.

## Licence position

Every source used or recommended above is permissive or is public data.
**brahe** is MIT, **astroquery** is BSD-3, **space-datasets** is MIT for its
pipeline code with each dataset licensed at its own source. **NHATS**, **SBDB**
and **Horizons** are NASA JPL public APIs; **NEODyS** is University of Pisa;
**Bus-DeMeo** and **Nesvorny** are NASA PDS. **Asterank** is MIT.

Nothing was copied from any of the four copyleft repositories, and nothing in
this pass came near them. The full position is in
[`../../CITATIONS.md`](../../CITATIONS.md), which is the authority.
