//! Opt-in Rust port of the programme / fleet ladder inside
//! `modules/calc.py::_evaluate_combo_at_ratio` (prototype).
//!
//! The ladder prices every rung `full=False` and keeps the best key; Python
//! then re-prices the WINNER in full (`best_priced[0] is None`), so the only
//! thing this has to reproduce is the CHOICE: `(best_n, best_f, best_w,
//! priced_count)`.  Every number in the output row is still Python's.
//!
//! Choosing identically needs each rung's `total_cost` and `g` bit-exact,
//! because `_objective_key` tuples are compared with a strict `>`.  So:
//!   * `_mission_cost_tail(totals_only=True)` is ported line for line;
//!   * the memoised helpers are called back (`calendar`, `learning`,
//!     `mining_rel`, `refine`), each at most once per key per call;
//!   * a rung whose market answer is not trivial (elasticity, or a capacity
//!     ceiling that binds and is not pruned) is priced by calling Python's own
//!     `_price_programme(n, f, w, full=False)`, and Rust's `total_cost` is
//!     checked against the one it returns, bit for bit;
//!   * the capacity "does anything bind" test, the incumbent rung bound and
//!     the key comparison run here.
//! `cap_by_programme`'s memo semantics are kept: a rung priced twice skips the
//! bound the second time, exactly as Python's cached entry does.
//!
//! Anything uncertain returns FALLBACK and the Python ladder runs: a non-exact
//! type, a zero divisor, a NaN key (tuple comparison of NaN depends on object
//! identity in CPython), a self-check mismatch, a Python local that would be
//! unbound.

use crate::py_div;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::Mutex;

/// The ladder's helpers, remembered ACROSS calls (one `run` is one ladder).
///
/// `_learning_curve_cached(n, rate)`, `_calendar_multipliers_cached(m,
/// cadence, wacc)` and `_mining_reliability_cached(n, p_first, alpha,
/// p_mature, f)` are pure functions of their arguments (none reads the
/// config), so the float Python returned for a key IS the answer for that
/// key, and remembering it is bit-identical by construction.  Before this,
/// the memo lived for one `run`, and every ladder asked Python again for
/// every rung: about a tenth of beneficiated search, measured.
///
/// Keys hold the float arguments as BIT PATTERNS, which equals Python's
/// `lru_cache` key equality only for non-zero, non-NaN floats (0.0 == -0.0
/// and NaN != NaN in Python), so any other argument skips this memo and the
/// callback answers as before.  An int argument skips it too (`1 == 1.0`
/// shares a cache slot in Python).  Bounded: a full map is cleared, which only
/// evicts.
#[derive(Default)]
struct SharedMemo {
    lc: HashMap<(i64, u64), f64>,
    cal: HashMap<(i64, u64, u64), (f64, f64)>,
    pm: HashMap<(i64, i64, u64, u64, u64, u64), f64>,
    hits: u64,
}

const SHARED_MEMO_MAX: usize = 1 << 16;

/// The bits of `v` when it may key the shared memo, else None.
fn memo_bits(v: &Bound<'_, PyAny>) -> Option<u64> {
    let f = v.downcast_exact::<PyFloat>().ok()?.value();
    if f == 0.0 || f.is_nan() {
        return None;
    }
    Some(f.to_bits())
}

#[inline(always)]
fn planted_hit(v: f64) -> f64 {
    #[cfg(feature = "planted_memo_defect")]
    {
        return f64::from_bits(v.to_bits() ^ 1);
    }
    #[allow(unreachable_code)]
    v
}

pub const KIND_FALLBACK: u8 = 0;
pub const KIND_DONE: u8 = 2;

const PROLOGUE_LEN: usize = 43;

/// Python's two-argument `max(a, b)` / `min(a, b)`.
#[inline(always)]
fn py_max(a: f64, b: f64) -> f64 {
    if b > a { b } else { a }
}
#[inline(always)]
fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

fn exact_f(v: &Bound<'_, PyAny>) -> Option<f64> {
    v.downcast_exact::<PyFloat>().ok().map(|f| f.value())
}
fn exact_b(v: &Bound<'_, PyAny>) -> Option<bool> {
    v.downcast_exact::<PyBool>().ok().map(|b| b.is_true())
}
/// An exact Python int (not bool) that fits comfortably: counts here are
/// rungs, fleets and trips, never near 2**53.
fn exact_i(v: &Bound<'_, PyAny>) -> Option<i64> {
    let n: i64 = v.downcast_exact::<PyInt>().ok()?.extract().ok()?;
    if n.abs() < (1 << 40) { Some(n) } else { None }
}

/// The fields of `_mission_cost_prologue`'s tuple that the totals read.
struct Pro {
    launch_cost: f64,
    outbound_prop_cost: f64,
    return_prop_cost: f64,
    return_prop_is_ongoing: bool,
    mining_rig_cost_total: f64,
    rig_trips: Option<(i64, i64, Option<i64>)>,
    life_yr: f64,
    salvage: f64,
    capsule_base: f64,
    power_base: f64,
    ep_base: f64,
    ep_kw: f64,
    tank_base: f64,
    tank_mass: f64,
    tps_base: f64,
    tps_mass: f64,
    licensing_cost: f64,
    liability_cost: f64,
    launch_ins_pct: f64,
    nre_base: f64,
    autonomy_nre_total: f64,
    cont: f64,
    mult_upfront: f64,
    mult_ongoing: f64,
    mult_end: f64,
    ongoing_with_cont: f64,
    end_with_cont: f64,
    cadence: f64,
    stay_yr: f64,
    calendar_on: bool,
    rig_ages_waiting: bool,
    repeat_saved: Option<(f64, f64, f64)>,
}

fn read_pro(t: &Bound<'_, PyTuple>) -> PyResult<Option<Pro>> {
    if t.len() != PROLOGUE_LEN {
        return Err(PyTypeError::new_err(format!(
            "ProgrammeLadder: prologue has {} fields, es_core reads {}; rebuild es_core",
            t.len(), PROLOGUE_LEN)));
    }
    let g = |i: usize| t.get_item(i);
    macro_rules! f { ($i:expr) => { match exact_f(&g($i)?) { Some(v) => v, None => return Ok(None) } } }
    macro_rules! b { ($i:expr) => { match exact_b(&g($i)?) { Some(v) => v, None => return Ok(None) } } }
    let rt = g(7)?;
    let rig_trips = if rt.is_none() {
        None
    } else {
        let Ok(tt) = rt.downcast_exact::<PyTuple>() else { return Ok(None) };
        if tt.len() != 3 { return Ok(None); }
        let (Some(a), Some(b2)) = (exact_i(&tt.get_item(0)?), exact_i(&tt.get_item(1)?)) else { return Ok(None) };
        let c = tt.get_item(2)?;
        let cap = if c.is_none() { None } else { match exact_i(&c) { Some(v) => Some(v), None => return Ok(None) } };
        Some((a, b2, cap))
    };
    let rs = g(42)?;
    let repeat_saved = if rs.is_none() {
        None
    } else {
        let Ok(tt) = rs.downcast_exact::<PyTuple>() else { return Ok(None) };
        if tt.len() != 3 { return Ok(None); }
        match (exact_f(&tt.get_item(0)?), exact_f(&tt.get_item(1)?), exact_f(&tt.get_item(2)?)) {
            (Some(a), Some(b2), Some(c)) => Some((a, b2, c)),
            _ => return Ok(None),
        }
    };
    // Field order is `_mission_cost_prologue`'s return, which the tail unpacks.
    Ok(Some(Pro {
        launch_cost: f!(0),
        outbound_prop_cost: f!(3),
        return_prop_cost: f!(4),
        return_prop_is_ongoing: b!(5),
        mining_rig_cost_total: f!(6),
        rig_trips,
        life_yr: f!(8),
        salvage: f!(9),
        capsule_base: f!(11),
        power_base: f!(12),
        ep_base: f!(13),
        ep_kw: f!(14),
        tank_base: f!(15),
        tank_mass: f!(16),
        tps_base: f!(17),
        tps_mass: f!(18),
        licensing_cost: f!(21),
        liability_cost: f!(22),
        launch_ins_pct: f!(23),
        nre_base: f!(24),
        autonomy_nre_total: f!(25),
        cont: f!(26),
        mult_upfront: f!(28),
        mult_ongoing: f!(29),
        mult_end: f!(30),
        ongoing_with_cont: f!(33),
        end_with_cont: f!(35),
        cadence: f!(36),
        stay_yr: f!(37),
        calendar_on: b!(39),
        rig_ages_waiting: b!(41),
        repeat_saved,
    }))
}

/// Callbacks into calc.py's memoised helpers, each asked once per key here.
struct Cbs<'a, 'py> {
    calendar: &'a Bound<'py, PyAny>,
    learning: &'a Bound<'py, PyAny>,
    mining_rel: &'a Bound<'py, PyAny>,
    price: &'a Bound<'py, PyAny>,
    cal_memo: HashMap<i64, (f64, f64)>,
    lc_memo: HashMap<i64, f64>,
    pm_memo: HashMap<(i64, i64), f64>,
    /// The cross-call memo, when it could be taken, and this ladder's keys
    /// into it: (rate), (cadence, wacc), (p_first, alpha, p_mature).
    shared: Option<std::sync::MutexGuard<'a, SharedMemo>>,
    lc_key: Option<u64>,
    cal_key: Option<(u64, u64)>,
    pm_key: Option<(u64, u64, u64)>,
}

type Step<T> = PyResult<Option<T>>;

impl<'a, 'py> Cbs<'a, 'py> {
    fn calendar(&mut self, m: i64) -> Step<(f64, f64)> {
        if let Some(v) = self.cal_memo.get(&m) {
            return Ok(Some(*v));
        }
        let skey = self.cal_key.map(|(c, w)| (m, c, w));
        if let (Some(k), Some(sh)) = (skey, self.shared.as_mut()) {
            if let Some(&(a, b)) = sh.cal.get(&k) {
                sh.hits += 1;
                let v = (planted_hit(a), b);
                self.cal_memo.insert(m, v);
                return Ok(Some(v));
            }
        }
        let r = self.calendar.call1((m,))?;
        let Ok(t) = r.downcast_exact::<PyTuple>() else { return Ok(None) };
        if t.len() != 2 { return Ok(None); }
        let (Some(a), Some(b)) = (exact_f(&t.get_item(0)?), exact_f(&t.get_item(1)?)) else { return Ok(None) };
        self.cal_memo.insert(m, (a, b));
        if let (Some(k), Some(sh)) = (skey, self.shared.as_mut()) {
            if sh.cal.len() >= SHARED_MEMO_MAX { sh.cal.clear(); }
            sh.cal.insert(k, (a, b));
        }
        Ok(Some((a, b)))
    }
    fn learning(&mut self, n: i64) -> Step<f64> {
        if let Some(v) = self.lc_memo.get(&n) {
            return Ok(Some(*v));
        }
        let skey = self.lc_key.map(|r| (n, r));
        if let (Some(k), Some(sh)) = (skey, self.shared.as_mut()) {
            if let Some(&v) = sh.lc.get(&k) {
                sh.hits += 1;
                let v = planted_hit(v);
                self.lc_memo.insert(n, v);
                return Ok(Some(v));
            }
        }
        let Some(v) = exact_f(&self.learning.call1((n,))?) else { return Ok(None) };
        self.lc_memo.insert(n, v);
        if let (Some(k), Some(sh)) = (skey, self.shared.as_mut()) {
            if sh.lc.len() >= SHARED_MEMO_MAX { sh.lc.clear(); }
            sh.lc.insert(k, v);
        }
        Ok(Some(v))
    }
    fn mining_rel(&mut self, n: i64, f: i64) -> Step<f64> {
        if let Some(v) = self.pm_memo.get(&(n, f)) {
            return Ok(Some(*v));
        }
        let skey = self.pm_key.map(|(a, b, c)| (n, f, a, b, c, 0u64));
        if let (Some(k), Some(sh)) = (skey, self.shared.as_mut()) {
            if let Some(&v) = sh.pm.get(&k) {
                sh.hits += 1;
                let v = planted_hit(v);
                self.pm_memo.insert((n, f), v);
                return Ok(Some(v));
            }
        }
        let Some(v) = exact_f(&self.mining_rel.call1((n, f))?) else { return Ok(None) };
        self.pm_memo.insert((n, f), v);
        if let (Some(k), Some(sh)) = (skey, self.shared.as_mut()) {
            if sh.pm.len() >= SHARED_MEMO_MAX { sh.pm.clear(); }
            sh.pm.insert(k, v);
        }
        Ok(Some(v))
    }
    /// Python's `_price_programme(n, f, w, full=False)` -> (total_cost, g).
    fn price(&self, n: i64, f: i64, w: Option<i64>) -> Step<(f64, f64)> {
        let r = self.price.call1((n, f, w))?;
        let Ok(t) = r.downcast_exact::<PyTuple>() else { return Ok(None) };
        if t.len() < 3 || !t.get_item(0)?.is_none() { return Ok(None); }
        let (Some(tc), Some(g)) = (exact_f(&t.get_item(1)?), exact_f(&t.get_item(2)?)) else { return Ok(None) };
        Ok(Some((tc, g)))
    }
}

macro_rules! tryo {
    ($e:expr) => { match $e { Some(v) => v, None => return Ok(None) } };
}
macro_rules! tryc {
    ($e:expr) => { match $e? { Some(v) => v, None => return Ok(None) } };
}

fn rig_age(campaigns: i64, stay: f64, cadence: f64, ages_waiting: bool) -> f64 {
    if ages_waiting {
        stay + (campaigns - 1) as f64 * cadence
    } else {
        campaigns as f64 * stay
    }
}

/// `_mission_cost_tail(pro, n, per_ship, totals_only=True, fleet_ships=f)`.
fn tail_total(p: &Pro, n_in: i64, per_ship: Option<i64>, fleet: i64, cb: &mut Cbs) -> Step<f64> {
    let n = n_in.max(1);
    let mut rig_terminal_value = 0.0f64;
    let mut msr = n;
    let mut short_rigs: i64 = 0;
    let mut short_rig_value: Option<f64> = None;
    if let Some((trips, _cal_cap, trip_cap)) = p.rig_trips {
        msr = match per_ship {
            None => n.min(trips),
            Some(w) => w.min(trips).max(1),
        };
        if p.calendar_on {
            short_rigs = fleet * msr - n;
            if !(0 < short_rigs && short_rigs < fleet) {
                short_rigs = 0;
            }
        }
        if n > 1 {
            let mut life_used = tryo!(py_div(rig_age(msr, p.stay_yr, p.cadence, p.rig_ages_waiting), p.life_yr));
            let duty = if p.rig_ages_waiting { trip_cap } else { Some(trips) };
            if trip_cap.is_some() {
                let d = tryo!(duty);
                life_used = py_max(life_used, tryo!(py_div(msr as f64, d as f64)));
            }
            life_used = py_min(1.0, life_used);
            rig_terminal_value = p.mining_rig_cost_total * (1.0 - life_used) * p.salvage;
            if short_rigs != 0 {
                let mut su = tryo!(py_div(rig_age(msr - 1, p.stay_yr, p.cadence, p.rig_ages_waiting), p.life_yr));
                if trip_cap.is_some() {
                    let d = tryo!(duty);
                    su = py_max(su, tryo!(py_div((msr - 1) as f64, d as f64)));
                }
                su = py_min(1.0, su);
                short_rig_value = Some(p.mining_rig_cost_total * (1.0 - su) * p.salvage);
            }
        }
    }
    // the cache-miss branch (the cache only memoises it)
    let div = msr.max(1) as f64;
    let mut mining_rig_cost = (p.mining_rig_cost_total - rig_terminal_value) / div;
    let mut rig_gross_share = p.mining_rig_cost_total / div;
    let mut rig_credit_share = rig_terminal_value / div;
    let (mut cal_cost, mut cal_credit) = (1.0f64, 1.0f64);
    if p.calendar_on && msr > 1 {
        (cal_cost, cal_credit) = tryc!(cb.calendar(msr));
    }
    if short_rigs != 0 {
        // Python reads `short_rig_value`, unbound unless n > 1: never guess.
        let srv = tryo!(short_rig_value);
        let full_rigs = fleet - short_rigs;
        let credits_full = full_rigs as f64 * rig_terminal_value;
        let credits_short = short_rigs as f64 * srv;
        let credits = credits_full + credits_short;
        rig_gross_share = fleet as f64 * p.mining_rig_cost_total / n as f64;
        rig_credit_share = credits / n as f64;
        mining_rig_cost = rig_gross_share - rig_credit_share;
        let _rtv = credits / fleet as f64;
        if cal_cost != 1.0 || cal_credit != 1.0 {
            let (cost_full, credit_full) = (cal_cost, cal_credit);
            let (cost_short, credit_short) = tryc!(cb.calendar(msr - 1));
            cal_cost = ((full_rigs * msr) as f64 * cost_full
                        + (short_rigs * (msr - 1)) as f64 * cost_short)
                / n as f64;
            if credits > 0.0 {
                cal_credit = tryo!(py_div(
                    cal_cost * (tryo!(py_div(credits_full * credit_full, cost_full))
                                + tryo!(py_div(credits_short * credit_short, cost_short))),
                    credits));
            }
        }
    }
    let (mut launch_cost, mut outbound_prop_cost, mut tank_base) =
        (p.launch_cost, p.outbound_prop_cost, p.tank_base);
    if let Some((r0, r1, r2)) = p.repeat_saved {
        if n > 1 {
            let first_flights = fleet;   // fleet_ships is always passed by the ladder
            let repeat_share = 1.0 - first_flights as f64 / n as f64;
            launch_cost -= repeat_share * r0;
            outbound_prop_cost -= repeat_share * r1;
            tank_base -= repeat_share * r2;
        }
    }
    let lc = tryc!(cb.learning(n));
    let capsule_cost = p.capsule_base * lc;
    let power_system_cost = p.power_base * lc;
    let ep_system_cost = if p.ep_kw > 0.0 { p.ep_base * lc } else { 0.0 };
    let tank_cost = if p.tank_mass > 0.0 { tank_base * lc } else { 0.0 };
    let hardware_cost = mining_rig_cost + capsule_cost + power_system_cost
        + ep_system_cost + tank_cost;
    let heat_shield_cost = if p.tps_mass > 0.0 { p.tps_base * lc } else { 0.0 };
    let book = p.mining_rig_cost_total + capsule_cost + power_system_cost
        + ep_system_cost + tank_cost + heat_shield_cost;
    let launch_insurance_cost = p.launch_ins_pct * (launch_cost + book);
    let nre_cost = p.nre_base / n as f64;
    let autonomy_nre_cost = p.autonomy_nre_total / n as f64;
    let upfront_lines = launch_cost + outbound_prop_cost + hardware_cost + heat_shield_cost
        + p.licensing_cost + p.liability_cost + launch_insurance_cost
        + nre_cost + autonomy_nre_cost
        + (if p.return_prop_is_ongoing { 0.0 } else { p.return_prop_cost });
    let mut upfront_with_cont = upfront_lines * p.cont;
    let mut end_with_cont = p.end_with_cont;
    if p.mult_upfront != p.mult_end && rig_credit_share != 0.0 {
        upfront_with_cont += rig_credit_share * p.cont;
        end_with_cont -= rig_credit_share * p.cont;
    }
    let mut total_cost = upfront_with_cont * p.mult_upfront
        + p.ongoing_with_cont * p.mult_ongoing
        + end_with_cont * p.mult_end;
    if cal_cost != 1.0 || cal_credit != 1.0 {
        let programme_upfront = nre_cost + autonomy_nre_cost + rig_gross_share;
        total_cost += (programme_upfront * (cal_cost - 1.0) * p.mult_upfront
                       - rig_credit_share * (cal_credit - 1.0) * p.mult_end)
            * p.cont;
    }
    #[cfg(feature = "planted_ladder_defect")]
    {
        total_cost = f64::from_bits(total_cost.to_bits() ^ 1);
    }
    Ok(Some(total_cost))
}

/// `_objective_key(profit, gross, cost, config, on_profit)`.
#[inline(always)]
fn objective_key(profit: f64, gross: f64, cost: f64, on_profit: bool) -> (f64, f64) {
    if on_profit {
        return (0.0, profit);
    }
    if profit > 0.0 {
        return (1.0, profit);
    }
    if gross <= 0.0 {
        return (-1.0, -cost);
    }
    (0.0, -(cost / gross))
}
/// CPython tuple `>` / `<=` for NaN-free pairs: first unequal element decides.
#[inline(always)]
fn key_gt(a: (f64, f64), b: (f64, f64)) -> bool {
    if a.0 != b.0 { a.0 > b.0 } else { a.1 > b.1 }
}
#[inline(always)]
fn key_le(a: (f64, f64), b: (f64, f64)) -> bool {
    if a.0 != b.0 { a.0 <= b.0 } else { a.1 <= b.1 }
}
fn key_nan(a: (f64, f64)) -> bool {
    a.0.is_nan() || a.1.is_nan()
}

struct In {
    gross_base: f64,
    rung_gross_ub: f64,
    max_n: f64,
    mission_duration_yr: f64,
    cadence_yr: f64,
    p_launch: f64,
    p_cruise: f64,
    p_first: f64,
    model_reliability: bool,
    model_reliability_growth: bool,
    saturation_applies: bool,
    capacity_applies: bool,
    model_market_wave_clock: bool,
    rung_bound: bool,
    on_profit: bool,
    n_floor: i64,
    /// shadow only: every Rust-priced rung is priced by Python too and
    /// both total_cost and g must match bit for bit
    audit: bool,
    market_pool: Vec<(f64, f64)>,
    programmes: Vec<(i64, i64, Option<i64>)>,
}

enum Cap {
    /// "nothing binds": g is `gross_base`, pre-reliability
    Plain,
    /// Python priced it (and holds the entry in its own memo)
    Py,
}

struct Rung {
    total: f64,
    g: f64,
}

/// One rung, as `_price_programme(n, f, w, full=False, incumbent)`; `None`
/// is the rung bound's skip.  `Err`/`Ok(None)` at the outer level is fallback.
fn price_rung(
    x: &In, p: &Pro, n: i64, fleet: i64, w: Option<i64>, incumbent: Option<(f64, f64)>,
    cb: &mut Cbs, caps: &mut HashMap<(i64, i64), Cap>, stats: &mut [u64; 6],
) -> Step<Option<Rung>> {
    let total = tryc!(tail_total(p, n, w, fleet, cb));
    let mut ps = 1.0f64;
    if x.model_reliability {
        let pm = if x.model_reliability_growth { tryc!(cb.mining_rel(n, fleet)) } else { x.p_first };
        ps = py_max(0.0, py_min(1.0, x.p_launch * x.p_cruise * pm));
    }
    if x.saturation_applies {
        stats[2] += 1;
        let (tc, g) = tryc!(cb.price(n, fleet, w));
        if tc.to_bits() != total.to_bits() {
            stats[5] += 1;
            return Ok(None);
        }
        return Ok(Some(Some(Rung { total, g })));
    }
    let mut g = x.gross_base;
    if x.capacity_applies {
        match caps.get(&(n, fleet)) {
            Some(Cap::Plain) => {}
            Some(Cap::Py) => {
                let (tc, gp) = tryc!(cb.price(n, fleet, w));
                if tc.to_bits() != total.to_bits() {
                    stats[5] += 1;
                    return Ok(None);
                }
                return Ok(Some(Some(Rung { total, g: gp })));
            }
            None => {
                let window = if x.model_market_wave_clock {
                    let waves = match w {
                        Some(v) if v != 0 => v,
                        _ => (tryo!(py_div(n as f64, fleet as f64))).ceil() as i64,
                    };
                    tryo!(py_div(x.mission_duration_yr + (waves - 1) as f64 * x.cadence_yr, n as f64))
                } else {
                    // spacevalue.cargo._delivery_window_yr
                    let nn = n.max(1);
                    let ff = fleet.max(1);
                    let first = py_max(0.0, x.mission_duration_yr);
                    let steady = py_max(0.0, x.cadence_yr) / ff as f64;
                    (first + (nn - 1) as f64 * steady) / nn as f64
                };
                let binds = x.market_pool.iter().any(|&(kg, mkt)| kg > mkt * window);
                if !binds {
                    caps.insert((n, fleet), Cap::Plain);
                    stats[3] += 1;
                } else {
                    if let Some(inc) = incumbent {
                        let ub = x.rung_gross_ub * ps;
                        let k = objective_key(ub - total, ub, total, x.on_profit);
                        if key_nan(k) {
                            return Ok(None);
                        }
                        if key_le(k, inc) {
                            if x.audit {
                                // the skip rests on Rust's total_cost: check it
                                let (tc, _gp) = tryc!(cb.price(n, fleet, w));
                                if tc.to_bits() != total.to_bits() {
                                    stats[5] += 1;
                                    return Ok(None);
                                }
                            }
                            stats[4] += 1;
                            return Ok(Some(None));
                        }
                    }
                    stats[2] += 1;
                    let (tc, gp) = tryc!(cb.price(n, fleet, w));
                    if tc.to_bits() != total.to_bits() {
                        stats[5] += 1;
                        return Ok(None);
                    }
                    caps.insert((n, fleet), Cap::Py);
                    return Ok(Some(Some(Rung { total, g: gp })));
                }
            }
        }
    }
    if x.model_reliability {
        g *= ps;
    }
    if x.audit {
        let (tc, gp) = tryc!(cb.price(n, fleet, w));
        if tc.to_bits() != total.to_bits() || gp.to_bits() != g.to_bits() {
            stats[5] += 1;
            return Ok(None);
        }
    }
    Ok(Some(Some(Rung { total, g })))
}

/// The ladder: programmes[0], programmes[1:], then the refinement pass.
/// Returns (best_n, best_f, best_w, priced_count) or None for fallback.
fn run_ladder(
    x: &In, p: &Pro, cb: &mut Cbs, refine: &Bound<'_, PyAny>, stats: &mut [u64; 6],
) -> Step<(i64, i64, Option<i64>, i64)> {
    let mut caps: HashMap<(i64, i64), Cap> = HashMap::new();
    let (mut best_n, mut best_f, mut best_w) = x.programmes[0];
    let first = tryo!(tryc!(price_rung(x, p, best_n, best_f, best_w, None, cb, &mut caps, stats)));
    let mut best_key = objective_key(first.g - first.total, first.g, first.total, x.on_profit);
    if key_nan(best_key) {
        return Ok(None);
    }
    let mut priced: i64 = 1;
    let rung = |inc: (f64, f64)| if x.rung_bound { Some(inc) } else { None };
    for &(n, f, w) in &x.programmes[1..] {
        let cand = tryc!(price_rung(x, p, n, f, w, rung(best_key), cb, &mut caps, stats));
        priced += 1;
        let Some(c) = cand else { continue };
        let key = objective_key(c.g - c.total, c.g, c.total, x.on_profit);
        if key_nan(key) {
            return Ok(None);
        }
        if key_gt(key, best_key) {
            best_key = key;
            (best_n, best_f, best_w) = (n, f, w);
        }
    }
    // `if len(programmes) > 1:` -- always, here: calc.py only calls with >1.
    let fl = refine.call1((best_f,))?;
    let Ok(fl) = fl.downcast_exact::<PyList>() else { return Ok(None) };
    let mut fleets = Vec::with_capacity(fl.len());
    for it in fl.iter() {
        fleets.push(tryo!(exact_i(&it)));
    }
    for f in fleets {
        let Some(w) = best_w else { return Ok(None) };   // fleet * None raises in Python
        let n = f * w;
        if n < x.n_floor || (n as f64) > x.max_n {
            continue;
        }
        let cand = tryc!(price_rung(x, p, n, f, best_w, rung(best_key), cb, &mut caps, stats));
        priced += 1;
        let Some(c) = cand else { continue };
        let key = objective_key(c.g - c.total, c.g, c.total, x.on_profit);
        if key_nan(key) {
            return Ok(None);
        }
        if key_gt(key, best_key) {
            best_key = key;
            (best_n, best_f) = (n, f);
        }
    }
    Ok(Some((best_n, best_f, best_w, priced)))
}

#[pyclass(frozen)]
pub struct ProgrammeLadder {
    audit: bool,
    /// The cross-call helper memo; off only to measure what it is worth.
    use_memo: bool,
    fast: AtomicU64,
    slow: AtomicU64,
    memo: Mutex<SharedMemo>,
    // [fast ladders, fallbacks, python-priced rungs, plain rungs, bound skips, self-check misses]
    stats: [AtomicU64; 6],
}

#[pymethods]
impl ProgrammeLadder {
    #[new]
    #[pyo3(signature = (audit=false, memo=true))]
    fn new(audit: bool, memo: bool) -> Self {
        ProgrammeLadder {
            audit,
            use_memo: memo,
            fast: AtomicU64::new(0),
            slow: AtomicU64::new(0),
            memo: Mutex::new(SharedMemo::default()),
            stats: Default::default(),
        }
    }

    #[pyo3(signature = (**kwargs))]
    fn run<'py>(&self, py: Python<'py>, kwargs: Option<&Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyTuple>> {
        let kw = kwargs.ok_or_else(|| PyTypeError::new_err("ProgrammeLadder.run takes keywords"))?;
        const NAMES: [&str; 25] = [
            "prologue", "programmes", "gross_base", "rung_gross_ub", "max_n",
            "mission_duration_yr", "cadence_yr", "p_launch", "p_cruise", "p_first",
            "model_reliability", "model_reliability_growth", "saturation_applies",
            "capacity_applies", "model_market_wave_clock", "rung_bound", "on_profit",
            "n_floor", "market_pool", "calendar", "learning", "mining_rel", "price",
            "refine", "_unused",
        ];
        // Optional: the reliability constants `mining_rel` closes over, which
        // key the cross-call memo (absent: the per-call memo only).
        const OPTIONAL: [&str; 2] = ["rel_alpha", "p_mature"];
        let mut got: HashMap<String, Bound<'py, PyAny>> = HashMap::new();
        for (k, v) in kw.iter() {
            let name = k.downcast_exact::<PyString>()?.to_cow()?.into_owned();
            if !NAMES[..24].contains(&name.as_str()) && !OPTIONAL.contains(&name.as_str()) {
                return Err(PyTypeError::new_err(format!("ProgrammeLadder.run: unknown input {name:?}")));
            }
            got.insert(name, v);
        }
        let missing: Vec<&str> = NAMES[..24].iter().copied().filter(|n| !got.contains_key(*n)).collect();
        if !missing.is_empty() {
            return Err(PyTypeError::new_err(format!("ProgrammeLadder.run: missing inputs {missing:?}")));
        }
        let fallback = |s: &Self| {
            s.slow.fetch_add(1, Relaxed);
            s.stats[1].fetch_add(1, Relaxed);
            PyTuple::new(py, [KIND_FALLBACK])
        };
        macro_rules! f { ($n:expr) => { match exact_f(&got[$n]) { Some(v) => v, None => return fallback(self) } } }
        macro_rules! b { ($n:expr) => { match exact_b(&got[$n]) { Some(v) => v, None => return fallback(self) } } }
        let Ok(pt) = got["prologue"].downcast_exact::<PyTuple>() else { return fallback(self) };
        let Some(pro) = read_pro(pt)? else { return fallback(self) };
        let Ok(pl) = got["programmes"].downcast_exact::<PyList>() else { return fallback(self) };
        let mut programmes = Vec::with_capacity(pl.len());
        for it in pl.iter() {
            let Ok(t) = it.downcast_exact::<PyTuple>() else { return fallback(self) };
            if t.len() != 3 { return fallback(self); }
            let (Some(n), Some(fl)) = (exact_i(&t.get_item(0)?), exact_i(&t.get_item(1)?)) else { return fallback(self) };
            let wv = t.get_item(2)?;
            let w = if wv.is_none() { None } else { match exact_i(&wv) { Some(v) => Some(v), None => return fallback(self) } };
            programmes.push((n, fl, w));
        }
        if programmes.len() < 2 {
            return fallback(self);
        }
        let Ok(mp) = got["market_pool"].downcast_exact::<PyTuple>() else { return fallback(self) };
        let mut market_pool = Vec::with_capacity(mp.len());
        for it in mp.iter() {
            let Ok(t) = it.downcast_exact::<PyTuple>() else { return fallback(self) };
            if t.len() != 2 { return fallback(self); }
            let (Some(a), Some(c)) = (exact_f(&t.get_item(0)?), exact_f(&t.get_item(1)?)) else { return fallback(self) };
            market_pool.push((a, c));
        }
        let Some(n_floor) = exact_i(&got["n_floor"]) else { return fallback(self) };
        let x = In {
            gross_base: f!("gross_base"),
            rung_gross_ub: f!("rung_gross_ub"),
            max_n: f!("max_n"),
            mission_duration_yr: f!("mission_duration_yr"),
            cadence_yr: f!("cadence_yr"),
            p_launch: f!("p_launch"),
            p_cruise: f!("p_cruise"),
            p_first: f!("p_first"),
            model_reliability: b!("model_reliability"),
            model_reliability_growth: b!("model_reliability_growth"),
            saturation_applies: b!("saturation_applies"),
            capacity_applies: b!("capacity_applies"),
            model_market_wave_clock: b!("model_market_wave_clock"),
            rung_bound: b!("rung_bound"),
            on_profit: b!("on_profit"),
            n_floor,
            audit: self.audit,
            market_pool,
            programmes,
        };
        // The keys `calc.py`'s three lambdas pass besides the rung: prologue
        // fields 10 (lc rate), 36 (cadence) and 31 (wacc), and the reliability
        // constants.  Read as objects, so an int or a zero skips the memo.
        let lc_key = memo_bits(&pt.get_item(10)?);
        let cal_key = match (memo_bits(&pt.get_item(36)?), memo_bits(&pt.get_item(31)?)) {
            (Some(c), Some(w)) => Some((c, w)),
            _ => None,
        };
        let pm_key = match (memo_bits(&got["p_first"]),
                            got.get("rel_alpha").and_then(|v| memo_bits(v)),
                            got.get("p_mature").and_then(|v| memo_bits(v))) {
            (Some(a), Some(b), Some(c)) => Some((a, b, c)),
            _ => None,
        };
        let mut cb = Cbs {
            calendar: &got["calendar"],
            learning: &got["learning"],
            mining_rel: &got["mining_rel"],
            price: &got["price"],
            cal_memo: HashMap::new(),
            lc_memo: HashMap::new(),
            pm_memo: HashMap::new(),
            // try_lock: a re-entrant call (a callback reaching another ladder)
            // simply runs without the shared memo.
            shared: if self.use_memo { self.memo.try_lock().ok() } else { None },
            lc_key,
            cal_key,
            pm_key,
        };
        let mut stats = [0u64; 6];
        let res = run_ladder(&x, &pro, &mut cb, &got["refine"], &mut stats)?;
        for (i, v) in stats.iter().enumerate() {
            if i != 1 {
                self.stats[i].fetch_add(*v, Relaxed);
            }
        }
        let Some((bn, bf, bw, priced)) = res else { return fallback(self) };
        self.fast.fetch_add(1, Relaxed);
        self.stats[0].fetch_add(1, Relaxed);
        let bw_obj: Bound<'py, PyAny> = match bw {
            Some(v) => v.into_pyobject(py)?.into_any(),
            None => py.None().into_bound(py),
        };
        let inner = PyTuple::new(py, [
            bn.into_pyobject(py)?.into_any(), bf.into_pyobject(py)?.into_any(),
            bw_obj, priced.into_pyobject(py)?.into_any(),
        ])?;
        PyTuple::new(py, [KIND_DONE.into_pyobject(py)?.into_any(), inner.into_any()])
    }

    /// (ladders answered in Rust, ladders handed to Python).
    fn counts(&self) -> (u64, u64) {
        (self.fast.load(Relaxed), self.slow.load(Relaxed))
    }

    /// {fast, fallback, rungs_priced_by_python, rungs_plain, rungs_bound_skipped,
    ///  selfcheck_mismatch}
    fn stats(&self) -> HashMap<&'static str, u64> {
        let names = ["fast", "fallback", "rungs_priced_by_python", "rungs_plain",
                     "rungs_bound_skipped", "selfcheck_mismatch"];
        let mut m: HashMap<&'static str, u64> =
            names.iter().zip(self.stats.iter()).map(|(n, v)| (*n, v.load(Relaxed))).collect();
        m.insert("memo_hits", self.memo.lock().map(|g| g.hits).unwrap_or(0));
        m
    }
}
