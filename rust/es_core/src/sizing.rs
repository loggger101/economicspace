//! Opt-in Rust port of the coupled sizing loop inside
//! `modules/calc.py::_evaluate_combo_at_ratio` (prototype).
//!
//! Same contract as the solver port: bit-identity with the Python loop, or a
//! FALLBACK that makes calc.py run its own, untouched loop instead.  The loop
//! is the `while passes < pass_limit:` block; everything before it (the
//! inputs) and after it (the settle-up, pricing, programmes) stays Python.
//!
//! How it hands back:
//!   (KIND_FALLBACK,)              run the Python loop; nothing was decided
//!   (KIND_REFUSE,)                the loop's `return None`
//!   (KIND_DONE, state)            the loop ended (converged, or out of passes);
//!                                 calc.py assigns `state` and skips its loop
//!   (KIND_REFIT_FEED, state, a)   `return _refit_to_feed_budget(*a)`
//!   (KIND_REFIT_PLANT, state, a)  `return _refit_to_plant_ceiling(*a)`
//! The refits recurse into `_evaluate_combo_at_ratio`, so Python makes them,
//! after assigning `state` (the closures read `return_dry_kg`,
//! `structure_frac_eff` and `damped_here`).
//!
//! FALLBACK, never a guess, whenever Python would do something this cannot
//! reproduce bit for bit: an argument that is not an exact float (or, where
//! the value only ever meets a float operand, an exact int within 2**53), a
//! division by zero (Python raises), `math.exp` overflowing (raises),
//! `math.log` of a non-positive number (raises), a callback returning
//! anything but the exact types the Python code would carry, and any NaN in
//! the state handed back (NaN sign is not portable; see lib.rs).
//!
//! The knapsack (`_hold_refining`, and `_cargo_water_kg`'s concentrating
//! branch) is called back into Python, unless `cargo=(refinery, phases,
//! recovery)` is given and reads exactly: then spacevalue's own Rust crate
//! (`spacevalue_cargo_core`) answers it here, with no crossing.  Inputs it
//! cannot read exactly leave the callbacks in charge; both are correct.

use crate::{exact_small_int, py_div, py_exp, py_max, py_min, solve, to_dict, Outcome};
use spacevalue_cargo_core as svc;
use pyo3::exceptions::PyTypeError;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyList, PyString, PyTuple};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};

pub const KIND_FALLBACK: u8 = 0;
pub const KIND_REFUSE: u8 = 1;
pub const KIND_DONE: u8 = 2;
pub const KIND_REFIT_FEED: u8 = 3;
pub const KIND_REFIT_PLANT: u8 = 4;

/// v1.28.0 constants, asserted equal to calc's at construction.
const DAMP_MIN_STEP: f64 = 1.0 / 1024.0;
const DAMP_EXTRA_PASSES: u32 = 36;

// Float inputs, by the name calc.py passes them under (`name=name`).
const F_NAMES: [&str; 48] = [
    "leo_cap", "isp_s_val", "dv_out_m_s", "dv_ret_stored", "dv_ret_eff",
    "tps_frac", "tank_frac", "structure_frac", "structure_frac_eff",
    "mineable_kg", "throughput_cap_kg", "window_wait_yr", "stay_est_yr",
    "outbound_yr", "boiloff_pct", "boiloff_factor", "eff_used", "ep_w_per_kg",
    "ppu_kg_per_kw", "thruster_kg_per_n", "ep_target_thrust_yr",
    "isru_feed_per_kg_prop", "isru_water_per_kg_prop", "isru_process_wh_per_kg",
    "isru_plant_rate", "refinery_rate", "target_ratio", "dig_wh", "benef_wh",
    "containment_per_kg", "water_wh", "plant_w_per_kg", "rtg_max_power_w",
    "mining_hardware_kg", "return_vehicle_dry_kg", "station_keeping_floor_yr",
    "mine_rate_kg_per_day", "ice_frac",
    // the loop's state, as calc.py initialised it
    "power_system_kg", "ep_system_kg", "refinery_kg", "isru_feed_kg",
    "isru_prop_kg", "containment_frac", "ep_power_watts", "ep_thrust_yr",
    "ep_thrust_n", "processing_power_watts",
];
// Names whose value only ever meets a float operand (or goes through a
// comparison that is exact for |n| <= 2**53), so an exact int is converted.
// Everything else must be an exact float: it can be carried into the state
// unchanged, and an int there would be a different Python type.
#[cfg_attr(not(test), allow(dead_code))] // the authority `slot` is generated from; held to it by slot_tests
const F_INT_OK: [&str; 19] = [
    "leo_cap", "isp_s_val", "tank_frac", "boiloff_pct", "eff_used",
    "ep_w_per_kg", "ppu_kg_per_kw", "thruster_kg_per_n", "isru_plant_rate",
    "refinery_rate", "target_ratio", "dig_wh", "benef_wh", "containment_per_kg",
    "water_wh", "plant_w_per_kg", "rtg_max_power_w", "mining_hardware_kg",
    "return_vehicle_dry_kg",
];
const B_NAMES: [&str; 16] = [
    "models_boiloff", "is_electric", "isru", "beneficiate", "power_is_rtg",
    "damp", "relax", "carry_ep_home", "model_isru_feed_budget",
    "size_ep_on_flown_load", "model_raw_excavation_power",
    "model_water_liberation", "model_volatile_containment",
    "refit_rtg_ceiling", "has_refinery", "has_phases",
];
// Non-float inputs.
const O_PAYLOAD_CAP: &str = "payload_cap_kg";
const O_HOLD_REFINING: &str = "hold_refining";
const O_CARGO_WATER: &str = "cargo_water";
const O_CARGO: &str = "cargo";

/// Where a keyword goes: one `match` (generated from F_NAMES, F_INT_OK and
/// B_NAMES, which stay the authority; `slot_matches_tables` holds the two
/// together) instead of a linear search of each table for every keyword.
#[derive(Clone, Copy, PartialEq, Debug)]
enum Slot {
    /// (index into F_NAMES, an exact int is accepted)
    F(usize, bool),
    /// index into B_NAMES
    B(usize),
    Cap,
    Hold,
    Water,
    Cargo,
}

fn slot(name: &str) -> Option<Slot> {
    Some(match name {
        "leo_cap" => Slot::F(0, true),
        "isp_s_val" => Slot::F(1, true),
        "dv_out_m_s" => Slot::F(2, false),
        "dv_ret_stored" => Slot::F(3, false),
        "dv_ret_eff" => Slot::F(4, false),
        "tps_frac" => Slot::F(5, false),
        "tank_frac" => Slot::F(6, true),
        "structure_frac" => Slot::F(7, false),
        "structure_frac_eff" => Slot::F(8, false),
        "mineable_kg" => Slot::F(9, false),
        "throughput_cap_kg" => Slot::F(10, false),
        "window_wait_yr" => Slot::F(11, false),
        "stay_est_yr" => Slot::F(12, false),
        "outbound_yr" => Slot::F(13, false),
        "boiloff_pct" => Slot::F(14, true),
        "boiloff_factor" => Slot::F(15, false),
        "eff_used" => Slot::F(16, true),
        "ep_w_per_kg" => Slot::F(17, true),
        "ppu_kg_per_kw" => Slot::F(18, true),
        "thruster_kg_per_n" => Slot::F(19, true),
        "ep_target_thrust_yr" => Slot::F(20, false),
        "isru_feed_per_kg_prop" => Slot::F(21, false),
        "isru_water_per_kg_prop" => Slot::F(22, false),
        "isru_process_wh_per_kg" => Slot::F(23, false),
        "isru_plant_rate" => Slot::F(24, true),
        "refinery_rate" => Slot::F(25, true),
        "target_ratio" => Slot::F(26, true),
        "dig_wh" => Slot::F(27, true),
        "benef_wh" => Slot::F(28, true),
        "containment_per_kg" => Slot::F(29, true),
        "water_wh" => Slot::F(30, true),
        "plant_w_per_kg" => Slot::F(31, true),
        "rtg_max_power_w" => Slot::F(32, true),
        "mining_hardware_kg" => Slot::F(33, true),
        "return_vehicle_dry_kg" => Slot::F(34, true),
        "station_keeping_floor_yr" => Slot::F(35, false),
        "mine_rate_kg_per_day" => Slot::F(36, false),
        "ice_frac" => Slot::F(37, false),
        "power_system_kg" => Slot::F(38, false),
        "ep_system_kg" => Slot::F(39, false),
        "refinery_kg" => Slot::F(40, false),
        "isru_feed_kg" => Slot::F(41, false),
        "isru_prop_kg" => Slot::F(42, false),
        "containment_frac" => Slot::F(43, false),
        "ep_power_watts" => Slot::F(44, false),
        "ep_thrust_yr" => Slot::F(45, false),
        "ep_thrust_n" => Slot::F(46, false),
        "processing_power_watts" => Slot::F(47, false),
        "models_boiloff" => Slot::B(0),
        "is_electric" => Slot::B(1),
        "isru" => Slot::B(2),
        "beneficiate" => Slot::B(3),
        "power_is_rtg" => Slot::B(4),
        "damp" => Slot::B(5),
        "relax" => Slot::B(6),
        "carry_ep_home" => Slot::B(7),
        "model_isru_feed_budget" => Slot::B(8),
        "size_ep_on_flown_load" => Slot::B(9),
        "model_raw_excavation_power" => Slot::B(10),
        "model_water_liberation" => Slot::B(11),
        "model_volatile_containment" => Slot::B(12),
        "refit_rtg_ceiling" => Slot::B(13),
        "has_refinery" => Slot::B(14),
        "has_phases" => Slot::B(15),
        O_PAYLOAD_CAP => Slot::Cap,
        O_HOLD_REFINING => Slot::Hold,
        O_CARGO_WATER => Slot::Water,
        O_CARGO => Slot::Cargo,
        _ => return None,
    })
}

/// The knapsack's inputs, read once per `run`: `(refinery, phases, recovery)`
/// exactly as calc's two callbacks close over them.
struct Native {
    phases: Vec<(String, f64, f64)>,
    refinery: Option<(Vec<(String, f64)>, f64)>,
    recovery: f64,
}

fn read_native(v: &Bound<'_, PyAny>) -> Option<Native> {
    if v.is_none() {
        return None;
    }
    let t = v.downcast_exact::<PyTuple>().ok()?;
    if t.len() != 3 {
        return None;
    }
    let r = t.get_item(0).ok()?;
    let refinery = if r.is_none() {
        None
    } else {
        let rt = r.downcast_exact::<PyTuple>().ok()?;
        if rt.len() != 2 {
            return None;
        }
        let d = rt.get_item(0).ok()?;
        let d = d.downcast_exact::<PyDict>().ok()?;
        let mut m = Vec::with_capacity(d.len());
        for (k, val) in d.iter() {
            let k = k.downcast_exact::<PyString>().ok()?.to_str().ok()?.to_owned();
            m.push((k, val.downcast_exact::<PyFloat>().ok()?.value()));
        }
        Some((m, rt.get_item(1).ok()?.downcast_exact::<PyFloat>().ok()?.value()))
    };
    let p = t.get_item(1).ok()?;
    let mut phases = Vec::new();
    if !p.is_none() {
        let l = p.downcast_exact::<PyList>().ok()?;
        for it in l.iter() {
            let pt = it.downcast_exact::<PyTuple>().ok()?;
            if pt.len() != 3 {
                return None;
            }
            let name = pt.get_item(0).ok()?.downcast_exact::<PyString>().ok()?.to_str().ok()?.to_owned();
            let frac = pt.get_item(1).ok()?.downcast_exact::<PyFloat>().ok()?.value();
            let price = pt.get_item(2).ok()?.downcast_exact::<PyFloat>().ok()?.value();
            if price.is_nan() {
                return None; // the price sort needs a strict weak order
            }
            phases.push((name, frac, price));
        }
    }
    let recovery = t.get_item(2).ok()?.downcast_exact::<PyFloat>().ok()?.value();
    Some(Native { phases, refinery, recovery })
}

/// The ordered phase table (`_PHASE_ORDER_CACHE`'s list), built once a run.
struct NativeView<'a> {
    n: &'a Native,
    ordered: Vec<svc::Phase<'a>>,
}

impl<'a> NativeView<'a> {
    fn new(n: &'a Native) -> Self {
        let ph: Vec<svc::Phase<'a>> = n.phases.iter()
            .map(|(name, f, p)| svc::Phase { name: name.as_str(), frac: *f, price: *p }).collect();
        NativeView { n, ordered: svc::by_price(&ph) }
    }
    /// `_hold_refining(refinery, phases, p, f, beneficiate, recovery)`.
    fn hold(&self, p: f64, f: f64, beneficiate: bool) -> Step<(f64, Option<f64>)> {
        let r = match &self.n.refinery {
            None => svc::hold_refining(None, &self.ordered, p, f, beneficiate, self.n.recovery),
            Some((m, raw)) => {
                let per = |name: &str| -> f64 {
                    m.iter().find(|(k, _)| k == name).map(|(_, v)| *v).unwrap_or(0.0)
                };
                svc::hold_refining(Some((&per, *raw)), &self.ordered, p, f, beneficiate, self.n.recovery)
            }
        };
        Ok(r.filter(|(wh, w)| !wh.is_nan() && !w.is_some_and(|v| v.is_nan())))
    }
    /// `float(optimal_payload_mix(p, f, phases, recovery, want_phase="water"))`.
    fn water(&self, p: f64, f: f64) -> Step<f64> {
        match svc::optimal_payload_mix::<svc::CapsVec>(p, f, &self.ordered, self.n.recovery,
                                                         Some("water"), None, 0.0) {
            svc::MixOut::Want(v) if !v.is_nan() => Ok(Some(v)),
            _ => Ok(None),
        }
    }
}

/// What `run` hands back as `state`, in this order.  calc.py unpacks by the
/// same tuple and asserts it at import.
pub const STATE_NAMES: [&str; 23] = [
    "power_system_kg", "ep_system_kg", "refinery_kg", "isru_feed_kg",
    "isru_prop_kg", "stay_est_yr", "containment_frac", "structure_frac_eff",
    "ep_power_watts", "ep_thrust_n", "ep_thrust_yr", "processing_power_watts",
    "boiloff_factor", "dv_ret_eff", "converged", "damped_here",
    "carried_ep_kg", "return_dry_kg", "hardware_est_kg", "cascade",
    "trial_payload", "r_ret", "hold_water",
];

macro_rules! idx {
    ($name:expr) => {{
        const I: usize = {
            let mut i = 0;
            loop {
                if konst_eq(F_NAMES[i], $name) {
                    break i;
                }
                i += 1;
            }
        };
        I
    }};
}

const fn konst_eq(a: &str, b: &str) -> bool {
    let (a, b) = (a.as_bytes(), b.as_bytes());
    if a.len() != b.len() {
        return false;
    }
    let mut i = 0;
    while i < a.len() {
        if a[i] != b[i] {
            return false;
        }
        i += 1;
    }
    true
}

fn b_idx(name: &str) -> usize {
    B_NAMES.iter().position(|n| *n == name).unwrap()
}

/// Python's `min(a, b, c)`: left to right, first minimal wins.
#[inline(always)]
fn py_min3(a: f64, b: f64, c: f64) -> f64 {
    py_min(py_min(a, b), c)
}

/// `math.log`: ValueError (here None) for x <= 0, NaN in -> NaN out.
#[inline(always)]
fn py_log(x: f64) -> Option<f64> {
    if x <= 0.0 {
        None
    } else {
        Some(x.ln())
    }
}

/// `spacevalue.cargo.refinery_plant_kg`.
#[inline(always)]
fn refinery_plant_kg(hold_kg: f64, stay_yr: f64, rate: f64) -> Option<f64> {
    if hold_kg <= 0.0 || stay_yr <= 0.0 || rate <= 0.0 {
        return Some(0.0);
    }
    py_div(hold_kg, stay_yr * rate)
}

struct Cascade {
    o: Outcome,
}

impl Cascade {
    fn viable(&self) -> bool {
        !matches!(self.o, Outcome::Infeasible { .. })
    }
    fn max_payload(&self) -> f64 {
        match self.o {
            Outcome::Infeasible { .. } => 0.0,
            Outcome::Isru { m_payload_max, .. } | Outcome::Full { m_payload_max, .. } => {
                m_payload_max
            }
        }
    }
    fn r_out(&self) -> f64 {
        match self.o {
            Outcome::Infeasible { r_out, .. }
            | Outcome::Isru { r_out, .. }
            | Outcome::Full { r_out, .. } => r_out,
        }
    }
    fn r_ret(&self) -> f64 {
        match self.o {
            Outcome::Infeasible { r_ret, .. }
            | Outcome::Isru { r_ret, .. }
            | Outcome::Full { r_ret, .. } => r_ret,
        }
    }
    /// `float(cascade.get("k_ret", 1.0))`
    fn k_ret(&self) -> f64 {
        match self.o {
            Outcome::Infeasible { .. } => 1.0,
            Outcome::Isru { k, .. } | Outcome::Full { k, .. } => k,
        }
    }
    fn k_out(&self) -> f64 {
        match self.o {
            Outcome::Infeasible { .. } => 1.0,
            Outcome::Isru { k_out, .. } | Outcome::Full { k_out, .. } => k_out,
        }
    }
    /// `float(cascade.get("m_outbound_prop", 0.0))`, `... "m_return_prop" ...`;
    /// the refusal cascade's are int 0, which float() makes 0.0.
    fn props(&self) -> (f64, f64) {
        match self.o {
            Outcome::Infeasible { .. } => (0.0, 0.0),
            Outcome::Isru { m_outbound_prop, .. } => (m_outbound_prop, 0.0),
            Outcome::Full { m_outbound_prop, m_return_prop, .. } => {
                (m_outbound_prop, m_return_prop)
            }
        }
    }
}

struct In {
    f: [f64; F_NAMES.len()],
    b: [bool; B_NAMES.len()],
    payload_cap: Option<f64>,
}

/// The loop's live state; `Option` where Python's local may be unassigned.
struct State {
    power_system_kg: f64,
    ep_system_kg: f64,
    refinery_kg: f64,
    isru_feed_kg: f64,
    isru_prop_kg: f64,
    stay_est_yr: f64,
    containment_frac: f64,
    structure_frac_eff: f64,
    ep_power_watts: f64,
    ep_thrust_n: f64,
    ep_thrust_yr: f64,
    processing_power_watts: f64,
    boiloff_factor: f64,
    dv_ret_eff: f64,
    converged: bool,
    damped_here: u32,
    carried_ep_kg: f64,
    return_dry_kg: f64,
    hardware_est_kg: f64,
    cascade: Option<Cascade>,
    trial_payload: Option<f64>,
    r_ret: Option<f64>,
    hold_water: Option<Option<f64>>,
    // knapsack evaluations (hold or cargo water) this run answered in Rust,
    // and those it called back into Python for; bookkeeping only
    knap_native: u64,
    knap_callback: u64,
}

impl State {
    fn has_nan(&self) -> bool {
        let fs = [
            self.power_system_kg, self.ep_system_kg, self.refinery_kg,
            self.isru_feed_kg, self.isru_prop_kg, self.stay_est_yr,
            self.containment_frac, self.structure_frac_eff, self.ep_power_watts,
            self.ep_thrust_n, self.ep_thrust_yr, self.processing_power_watts,
            self.boiloff_factor, self.dv_ret_eff, self.carried_ep_kg,
            self.return_dry_kg, self.hardware_est_kg,
            self.trial_payload.unwrap_or(0.0), self.r_ret.unwrap_or(0.0),
            self.hold_water.flatten().unwrap_or(0.0),
        ];
        fs.iter().any(|v| v.is_nan())
            || self.cascade.as_ref().map(|c| c.o.has_nan()).unwrap_or(false)
    }
}

enum Exit {
    Fallback,
    Refuse,
    Done,
    RefitFeed(f64, f64, f64),
    RefitPlant(f64, f64, f64),
}

/// What a callback-or-Rust step can produce: a value, or "give up and let
/// Python run the loop" (`Ok(None)`), or a real exception (`Err`).
type Step<T> = PyResult<Option<T>>;

macro_rules! tryf {
    ($e:expr) => {
        match $e {
            Some(v) => v,
            None => return Ok(Exit::Fallback),
        }
    };
}
macro_rules! tryc {
    ($e:expr) => {
        match $e? {
            Some(v) => v,
            None => return Ok(Exit::Fallback),
        }
    };
}

/// `_ep_stage_kg`, from the two propellant loads it reads off a cascade.
/// Returns (ep_system_kg, ep_power_w, ep_thrust_n, ep_thrust_yr).
fn ep_stage(g0: f64, m_out: f64, m_ret: f64, x: &In) -> Option<(f64, f64, f64, f64)> {
    let isp = x.f[idx!("isp_s_val")];
    let eff = x.f[idx!("eff_used")];
    let t_yr = x.f[idx!("ep_target_thrust_yr")];
    let ep_w_per_kg = x.f[idx!("ep_w_per_kg")];
    let m = m_out + m_ret;
    // ep_power_required_w
    let ep_power_w = if t_yr <= 0.0 || m <= 0.0 {
        0.0
    } else {
        let ve = isp * g0;
        let seconds = t_yr * 365.25 * 24.0 * 3600.0;
        py_div(m * ve * ve, 2.0 * eff * seconds)?
    };
    // ep_thrust_required_n
    let ep_thrust_n = if t_yr <= 0.0 || m <= 0.0 || isp <= 0.0 {
        0.0
    } else {
        let seconds = t_yr * 365.25 * 24.0 * 3600.0;
        py_div(m * (isp * g0), seconds)?
    };
    let ep_thrust_yr = if m > 0.0 { t_yr } else { 0.0 };
    let array_kg = if ep_w_per_kg > 0.0 { py_div(ep_power_w, ep_w_per_kg)? } else { 0.0 };
    let ppu_kg = ep_power_w / 1000.0 * x.f[idx!("ppu_kg_per_kw")];
    let thruster_kg = ep_thrust_n * x.f[idx!("thruster_kg_per_n")];
    Some((array_kg + ppu_kg + thruster_kg, ep_power_w, ep_thrust_n, ep_thrust_yr))
}

/// `_flown_propellant_kg` -> (m_outbound_prop, m_return_prop).
#[allow(clippy::too_many_arguments)]
fn flown_prop(
    payload_kg: f64, hardware_kg: f64, return_dry_kg: f64, structure_frac: f64,
    tps_frac: f64, tank_frac: f64, c: &Cascade, isru: bool,
) -> (f64, f64) {
    let k_ret = c.k_ret();
    let k_out = c.k_out();
    let after = k_ret * (1.0 + tps_frac) * (payload_kg * (1.0 + structure_frac) + return_dry_kg);
    let return_prop = after * (c.r_ret() - 1.0);
    let dry = return_dry_kg + structure_frac * payload_kg;
    let out_load = hardware_kg + dry + tps_frac * (payload_kg + dry)
        + tank_frac * return_prop + (if isru { 0.0 } else { return_prop });
    (out_load * k_out * (c.r_out() - 1.0), return_prop)
}

fn blend(base: &[f64; 7], target: &[f64; 7], step: f64) -> [f64; 7] {
    let mut out = [0.0; 7];
    for i in 0..7 {
        out[i] = base[i] + step * (target[i] - base[i]);
    }
    #[cfg(feature = "planted_loop_defect")]
    {
        out[0] = f64::from_bits(out[0].to_bits() ^ 1);
    }
    out
}

fn call_cargo_water(cb: &Bound<'_, PyAny>, p: f64, f: f64) -> Step<f64> {
    let r = cb.call1((p, f))?;
    Ok(r.downcast_exact::<PyFloat>().ok().map(|v| v.value()))
}

fn call_hold_refining(cb: &Bound<'_, PyAny>, p: f64, f: f64) -> Step<(f64, Option<f64>)> {
    let r = cb.call1((p, f))?;
    let Ok(t) = r.downcast_exact::<PyTuple>() else { return Ok(None) };
    if t.len() != 2 {
        return Ok(None);
    }
    let Ok(wh) = t.get_item(0)?.downcast_exact::<PyFloat>().map(|v| v.value()) else {
        return Ok(None);
    };
    let w = t.get_item(1)?;
    if w.is_none() {
        return Ok(Some((wh, None)));
    }
    match w.downcast_exact::<PyFloat>() {
        Ok(v) => Ok(Some((wh, Some(v.value())))),
        Err(_) => Ok(None),
    }
}

/// The loop, statement for statement.  Comments name the Python line it is.
fn run_loop(
    g0: f64, x: &In, st: &mut State,
    hold_cb: &Bound<'_, PyAny>, water_cb: &Bound<'_, PyAny>,
    native: Option<&NativeView<'_>>,
) -> PyResult<Exit> {
    let f = |n: usize| x.f[n];
    let bv = |n: &str| x.b[b_idx(n)];
    let isp = f(idx!("isp_s_val"));
    let tps = f(idx!("tps_frac"));
    let tank = f(idx!("tank_frac"));
    let sf = f(idx!("structure_frac"));
    let mineable = f(idx!("mineable_kg"));
    let thr_cap = f(idx!("throughput_cap_kg"));
    let window = f(idx!("window_wait_yr"));
    let target_ratio = f(idx!("target_ratio"));
    let floor_yr = f(idx!("station_keeping_floor_yr"));
    let mine_rate = f(idx!("mine_rate_kg_per_day"));
    let (isru, beneficiate, is_electric) = (bv("isru"), bv("beneficiate"), bv("is_electric"));
    let (damp, relax) = (bv("damp"), bv("relax"));
    let isru_plant_rate = f(idx!("isru_plant_rate"));
    let containment_per_kg = f(idx!("containment_per_kg"));

    let mut step = 1.0f64;
    let mut base: Option<[f64; 7]> = None;
    let mut target: Option<[f64; 7]> = None;
    let mut passes: u32 = 0;
    let mut pass_limit: u32 = 12;
    while passes < pass_limit {
        passes += 1;
        if bv("models_boiloff") {
            let hold_yr = f(idx!("outbound_yr")) + st.stay_est_yr;
            let bf = tryf!(py_exp(f(idx!("boiloff_pct")) / 100.0 * hold_yr * 365.25));
            let r_ret_raw = tryf!(py_exp(tryf!(py_div(f(idx!("dv_ret_stored")), isp * g0))));
            let r_ret_eff = 1.0 + (r_ret_raw - 1.0) * bf;
            st.boiloff_factor = bf;
            st.dv_ret_eff = isp * g0 * tryf!(py_log(r_ret_eff));
        }

        let plant_kg = if isru_plant_rate > 0.0 {
            tryf!(refinery_plant_kg(st.isru_prop_kg, st.stay_est_yr - window, isru_plant_rate))
        } else {
            0.0
        };
        st.hardware_est_kg = f(idx!("mining_hardware_kg")) + st.power_system_kg
            + st.ep_system_kg + st.refinery_kg + plant_kg;
        st.carried_ep_kg = if bv("carry_ep_home") { st.ep_system_kg } else { 0.0 };
        st.return_dry_kg = f(idx!("return_vehicle_dry_kg")) + st.carried_ep_kg;
        let o = tryf!(solve(
            g0, f(idx!("leo_cap")), isp, f(idx!("dv_out_m_s")), st.dv_ret_eff,
            st.hardware_est_kg - st.carried_ep_kg, st.return_dry_kg, tps, isru,
            st.structure_frac_eff, tank,
        ));
        st.cascade = Some(Cascade { o });
        let c = st.cascade.as_ref().unwrap();
        if !c.viable() {
            let Some(b0) = base else { return Ok(Exit::Refuse) };
            if !damp {
                return Ok(Exit::Refuse);
            }
            step *= 0.5;
            st.damped_here += 1;
            if step < DAMP_MIN_STEP {
                return Ok(Exit::Refuse);
            }
            if st.damped_here == 1 {
                pass_limit += DAMP_EXTRA_PASSES;
            }
            let t0 = tryf!(target);
            let v = blend(&b0, &t0, step);
            (st.power_system_kg, st.ep_system_kg, st.refinery_kg, st.isru_feed_kg,
             st.isru_prop_kg, st.stay_est_yr, st.containment_frac) =
                (v[0], v[1], v[2], v[3], v[4], v[5], v[6]);
            st.structure_frac_eff = sf + st.containment_frac;
            continue;
        }

        let mut new_ep_kg = 0.0;
        if is_electric {
            let (mo, mr) = c.props();
            let r = tryf!(ep_stage(g0, mo, mr, x));
            new_ep_kg = r.0;
            (st.ep_power_watts, st.ep_thrust_n, st.ep_thrust_yr) = (r.1, r.2, r.3);
        }

        let mut trial_payload = py_min3(c.max_payload(), mineable,
                                        py_max(0.0, thr_cap - st.isru_feed_kg));
        if let Some(cap) = x.payload_cap {
            if trial_payload > cap {
                trial_payload = cap;
            }
        }
        st.trial_payload = Some(trial_payload);
        if trial_payload <= 0.0 {
            return Ok(Exit::Refuse);
        }
        let mut new_isru_feed = 0.0;
        let mut new_isru_prop = 0.0;
        if isru {
            let r_ret = c.r_ret();
            st.r_ret = Some(r_ret);
            new_isru_prop = (trial_payload + st.return_dry_kg
                             + st.structure_frac_eff * trial_payload)
                * (1.0 + tps) * (r_ret - 1.0);
            if bv("model_isru_feed_budget") {
                new_isru_prop *= c.k_ret();
            }
            new_isru_feed = new_isru_prop * f(idx!("isru_feed_per_kg_prop"));
            if new_isru_feed >= thr_cap || new_isru_feed >= mineable {
                if bv("model_isru_feed_budget") {
                    return Ok(Exit::RefitFeed(
                        trial_payload, new_isru_feed,
                        if beneficiate { target_ratio } else { 1.0 }));
                }
                return Ok(Exit::Refuse);
            }
        }

        if is_electric && bv("size_ep_on_flown_load") {
            let (mo, mr) = flown_prop(
                trial_payload, st.hardware_est_kg - st.carried_ep_kg, st.return_dry_kg,
                st.structure_frac_eff, tps, tank, c, isru);
            let r = tryf!(ep_stage(g0, mo, mr, x));
            new_ep_kg = r.0;
            (st.ep_power_watts, st.ep_thrust_n, st.ep_thrust_yr) = (r.1, r.2, r.3);
        }

        let trial_feed = if beneficiate {
            py_min3(trial_payload * target_ratio,
                    py_max(0.0, thr_cap - new_isru_feed),
                    py_max(0.0, mineable - new_isru_feed))
        } else {
            trial_payload
        };
        // mining_duration_yr, then max(..., floor)
        let md = if mine_rate <= 0.0 {
            floor_yr
        } else {
            let dig_yr = tryf!(py_div(trial_feed + new_isru_feed, mine_rate * 365.25));
            py_max(floor_yr, dig_yr)
        };
        let trial_dur = py_max(md, floor_yr);

        let mut ppw = 0.0;
        if beneficiate || isru || bv("model_raw_excavation_power") {
            // processing_power_w
            let feed = trial_feed + new_isru_feed;
            let conc = if beneficiate { trial_payload } else { 0.0 };
            ppw = if trial_dur <= 0.0 {
                0.0
            } else {
                let e = f(idx!("dig_wh")) * py_max(feed, 0.0)
                    + f(idx!("benef_wh")) * py_max(conc, 0.0);
                tryf!(py_div(e, trial_dur * 365.25 * 24.0))
            };
        }
        let need_cargo_water = bv("model_water_liberation")
            || (bv("model_volatile_containment") && containment_per_kg > 0.0);
        let (trial_refine_wh, hold_water) = if bv("has_refinery") {
            match native {
                Some(nv) => {
                    st.knap_native += 1;
                    tryc!(nv.hold(trial_payload, trial_feed, beneficiate))
                }
                None => {
                    st.knap_callback += 1;
                    tryc!(call_hold_refining(hold_cb, trial_payload, trial_feed))
                }
            }
        } else {
            (0.0, None)   // `_hold_refining(None, ...)` is (0.0, None)
        };
        st.hold_water = Some(hold_water);
        let trial_cargo_water = if need_cargo_water {
            match hold_water {
                Some(w) => w,
                None => {
                    // _cargo_water_kg
                    if trial_payload <= 0.0 {
                        0.0
                    } else if beneficiate {
                        if !bv("has_phases") {
                            0.0
                        } else {
                            match native {
                                Some(nv) => {
                                    st.knap_native += 1;
                                    tryc!(nv.water(trial_payload, trial_feed))
                                }
                                None => {
                                    st.knap_callback += 1;
                                    tryc!(call_cargo_water(water_cb, trial_payload, trial_feed))
                                }
                            }
                        }
                    } else {
                        trial_payload * f(idx!("ice_frac"))
                    }
                }
            }
        } else {
            0.0
        };
        let mut new_containment_frac = 0.0;
        if bv("model_volatile_containment") && trial_payload > 0.0 {
            new_containment_frac = containment_per_kg
                * py_min(1.0, tryf!(py_div(trial_cargo_water, trial_payload)));
        }
        if trial_dur > 0.0 && bv("model_water_liberation") {
            let mut trial_water = if isru {
                new_isru_prop * f(idx!("isru_water_per_kg_prop"))
            } else {
                0.0
            };
            trial_water += trial_cargo_water;
            if trial_water > 0.0 {
                ppw += tryf!(py_div(f(idx!("water_wh")) * trial_water,
                                    trial_dur * 365.25 * 24.0));
            }
        }
        let mut new_refinery_kg = 0.0;
        if trial_refine_wh > 0.0 && trial_dur > 0.0 {
            ppw += tryf!(py_div(trial_refine_wh, trial_dur * 365.25 * 24.0));
            new_refinery_kg = tryf!(refinery_plant_kg(trial_payload, trial_dur,
                                                      f(idx!("refinery_rate"))));
        }
        let iproc = f(idx!("isru_process_wh_per_kg"));
        if iproc > 0.0 && trial_dur > 0.0 {
            ppw += tryf!(py_div(iproc * new_isru_prop, trial_dur * 365.25 * 24.0));
        }
        st.processing_power_watts = ppw;

        let new_power_kg;
        if ppw > 0.0 {
            if bv("power_is_rtg") && ppw > f(idx!("rtg_max_power_w")) {
                if bv("refit_rtg_ceiling") {
                    return Ok(Exit::RefitPlant(trial_payload, ppw, trial_dur));
                }
                return Ok(Exit::Refuse);
            }
            let pw = f(idx!("plant_w_per_kg"));
            new_power_kg = if pw > 0.0 { tryf!(py_div(ppw, pw)) } else { 0.0 };
        } else {
            new_power_kg = 0.0;
        }

        let new_stay_yr = trial_dur + window;
        let close = |n: f64, o: f64| (n - o).abs() <= 0.01 * py_max(n, 1.0);
        st.converged = close(new_power_kg, st.power_system_kg)
            && close(new_ep_kg, st.ep_system_kg)
            && close(new_isru_feed, st.isru_feed_kg)
            && close(new_stay_yr, st.stay_est_yr)
            && close(new_refinery_kg, st.refinery_kg)
            && (new_containment_frac - st.containment_frac).abs() <= 1e-4;
        let cur = [st.power_system_kg, st.ep_system_kg, st.refinery_kg, st.isru_feed_kg,
                   st.isru_prop_kg, st.stay_est_yr, st.containment_frac];
        let new = [new_power_kg, new_ep_kg, new_refinery_kg, new_isru_feed,
                   new_isru_prop, new_stay_yr, new_containment_frac];
        if damp || relax {
            base = Some(cur);
            target = Some(new);
        }
        let v = if st.converged || step == 1.0 {
            new
        } else {
            // Python would call _damp_blend(None, ...) and raise; unreachable
            // in practice (step < 1 only once damp or relax set base), but
            // never guessed at.
            let (Some(b0), Some(t0)) = (base, target) else { return Ok(Exit::Fallback) };
            blend(&b0, &t0, step)
        };
        (st.power_system_kg, st.ep_system_kg, st.refinery_kg, st.isru_feed_kg,
         st.isru_prop_kg, st.stay_est_yr, st.containment_frac) =
            (v[0], v[1], v[2], v[3], v[4], v[5], v[6]);
        st.structure_frac_eff = sf + st.containment_frac;
        if st.converged {
            break;
        }
        if relax && st.damped_here == 0 {
            step = 0.5;
            st.damped_here += 1;
            pass_limit += DAMP_EXTRA_PASSES;
        }
    }
    Ok(Exit::Done)
}

#[pyclass(frozen)]
pub struct SizingLoop {
    g0: f64,
    unset: Py<PyAny>,
    fast: AtomicU64,
    slow: AtomicU64,
    knap_native: AtomicU64,
    knap_callback: AtomicU64,
}

type Inputs<'py> = (In, Bound<'py, PyAny>, Bound<'py, PyAny>, Option<Native>);

fn read_inputs<'py>(kw: &Bound<'py, PyDict>) -> PyResult<Option<Inputs<'py>>> {
    let mut x = In { f: [0.0; F_NAMES.len()], b: [false; B_NAMES.len()], payload_cap: None };
    let mut seen_f = [false; F_NAMES.len()];
    let mut seen_b = [false; B_NAMES.len()];
    let mut seen_cap = false;
    let mut hold = None;
    let mut water = None;
    let mut native = None;
    let mut ok = true;
    for (k, v) in kw.iter() {
        let name = k.downcast_exact::<PyString>()?.to_cow()?;
        let name: &str = &name;
        match slot(name) {
            Some(Slot::F(i, int_ok)) => {
                seen_f[i] = true;
                if let Ok(fl) = v.downcast_exact::<PyFloat>() {
                    x.f[i] = fl.value();
                } else if int_ok {
                    match exact_small_int(&v) {
                        Some(val) => x.f[i] = val,
                        None => ok = false,
                    }
                } else {
                    ok = false;
                }
            }
            Some(Slot::B(i)) => {
                seen_b[i] = true;
                match v.downcast_exact::<PyBool>() {
                    Ok(bb) => x.b[i] = bb.is_true(),
                    Err(_) => ok = false,
                }
            }
            Some(Slot::Cap) => {
                seen_cap = true;
                if !v.is_none() {
                    match v.downcast_exact::<PyFloat>() {
                        Ok(fl) => x.payload_cap = Some(fl.value()),
                        Err(_) => ok = false,
                    }
                }
            }
            Some(Slot::Hold) => hold = Some(v),
            Some(Slot::Water) => water = Some(v),
            // Optional; unreadable means the callbacks answer, not a fallback.
            Some(Slot::Cargo) => native = read_native(&v),
            // A misspelt or stale name is a programming error, not data.
            None => return Err(PyTypeError::new_err(format!("SizingLoop.run: unknown input {name:?}"))),
        }
    }
    let missing: Vec<&str> = F_NAMES.iter().zip(seen_f).filter(|(_, s)| !s).map(|(n, _)| *n)
        .chain(B_NAMES.iter().zip(seen_b).filter(|(_, s)| !s).map(|(n, _)| *n))
        .chain((!seen_cap).then_some(O_PAYLOAD_CAP))
        .chain(hold.is_none().then_some(O_HOLD_REFINING))
        .chain(water.is_none().then_some(O_CARGO_WATER))
        .collect();
    if !missing.is_empty() {
        return Err(PyTypeError::new_err(format!("SizingLoop.run: missing inputs {missing:?}")));
    }
    if !ok {
        return Ok(None);
    }
    Ok(Some((x, hold.unwrap(), water.unwrap(), native)))
}

#[pymethods]
impl SizingLoop {
    #[new]
    fn new(g0: f64, unset: Py<PyAny>, damp_min_step: f64, damp_extra_passes: u32) -> PyResult<Self> {
        if damp_min_step.to_bits() != DAMP_MIN_STEP.to_bits()
            || damp_extra_passes != DAMP_EXTRA_PASSES
        {
            return Err(PyTypeError::new_err(
                "SizingLoop: calc's _DAMP_MIN_STEP / _DAMP_EXTRA_PASSES differ from es_core's"));
        }
        Ok(SizingLoop { g0, unset, fast: AtomicU64::new(0), slow: AtomicU64::new(0),
                        knap_native: AtomicU64::new(0), knap_callback: AtomicU64::new(0) })
    }

    /// Names of the state tuple, in order.
    #[classattr]
    #[allow(non_snake_case)]
    fn STATE_NAMES() -> Vec<&'static str> {
        STATE_NAMES.to_vec()
    }
    #[classattr]
    #[allow(non_snake_case)]
    fn INPUT_NAMES() -> Vec<&'static str> {
        F_NAMES.iter().chain(B_NAMES.iter()).copied()
            .chain([O_PAYLOAD_CAP, O_HOLD_REFINING, O_CARGO_WATER, O_CARGO]).collect()
    }

    #[pyo3(signature = (**kwargs))]
    fn run<'py>(&self, py: Python<'py>, kwargs: Option<&Bound<'py, PyDict>>) -> PyResult<Bound<'py, PyTuple>> {
        let kw = kwargs.ok_or_else(|| PyTypeError::new_err("SizingLoop.run takes keywords"))?;
        let fallback = |s: &Self| {
            s.slow.fetch_add(1, Relaxed);
            PyTuple::new(py, [KIND_FALLBACK])
        };
        let Some((x, hold_cb, water_cb, native)) = read_inputs(kw)? else { return fallback(self) };
        let view = native.as_ref().map(NativeView::new);
        let mut st = State {
            power_system_kg: x.f[idx!("power_system_kg")],
            ep_system_kg: x.f[idx!("ep_system_kg")],
            refinery_kg: x.f[idx!("refinery_kg")],
            isru_feed_kg: x.f[idx!("isru_feed_kg")],
            isru_prop_kg: x.f[idx!("isru_prop_kg")],
            stay_est_yr: x.f[idx!("stay_est_yr")],
            containment_frac: x.f[idx!("containment_frac")],
            structure_frac_eff: x.f[idx!("structure_frac_eff")],
            ep_power_watts: x.f[idx!("ep_power_watts")],
            ep_thrust_n: x.f[idx!("ep_thrust_n")],
            ep_thrust_yr: x.f[idx!("ep_thrust_yr")],
            processing_power_watts: x.f[idx!("processing_power_watts")],
            boiloff_factor: x.f[idx!("boiloff_factor")],
            dv_ret_eff: x.f[idx!("dv_ret_eff")],
            converged: false,
            damped_here: 0,
            carried_ep_kg: 0.0,
            return_dry_kg: 0.0,
            hardware_est_kg: 0.0,
            cascade: None,
            trial_payload: None,
            r_ret: None,
            hold_water: None,
            knap_native: 0,
            knap_callback: 0,
        };
        let exit = run_loop(self.g0, &x, &mut st, &hold_cb, &water_cb, view.as_ref())?;
        // knapsack evaluations are counted only for runs Rust answers, so a
        // run that falls back (and is redone in Python) counts for neither
        let knap = (st.knap_native, st.knap_callback);
        let count_knap = |s: &Self| {
            s.knap_native.fetch_add(knap.0, Relaxed);
            s.knap_callback.fetch_add(knap.1, Relaxed);
        };
        let (kind, args) = match exit {
            Exit::Fallback => return fallback(self),
            Exit::Refuse => {
                self.fast.fetch_add(1, Relaxed);
                count_knap(self);
                return PyTuple::new(py, [KIND_REFUSE]);
            }
            Exit::Done => (KIND_DONE, None),
            Exit::RefitFeed(a, b, c) => (KIND_REFIT_FEED, Some((a, b, c))),
            Exit::RefitPlant(a, b, c) => (KIND_REFIT_PLANT, Some((a, b, c))),
        };
        if st.has_nan() || args.map(|(a, b, c)| a.is_nan() || b.is_nan() || c.is_nan()).unwrap_or(false) {
            return fallback(self);
        }
        let unset = self.unset.bind(py);
        let opt = |v: Option<f64>| -> PyResult<Bound<'py, PyAny>> {
            Ok(match v {
                Some(f) => PyFloat::new(py, f).into_any(),
                None => unset.clone(),
            })
        };
        let cascade = match st.cascade {
            Some(c) => to_dict(py, c.o)?.into_any(),
            None => unset.clone(),
        };
        let hold_water = match st.hold_water {
            None => unset.clone(),
            Some(None) => py.None().into_bound(py),
            Some(Some(w)) => PyFloat::new(py, w).into_any(),
        };
        let fl = |v: f64| PyFloat::new(py, v).into_any();
        let state = PyTuple::new(py, [
            fl(st.power_system_kg), fl(st.ep_system_kg), fl(st.refinery_kg),
            fl(st.isru_feed_kg), fl(st.isru_prop_kg), fl(st.stay_est_yr),
            fl(st.containment_frac), fl(st.structure_frac_eff), fl(st.ep_power_watts),
            fl(st.ep_thrust_n), fl(st.ep_thrust_yr), fl(st.processing_power_watts),
            fl(st.boiloff_factor), fl(st.dv_ret_eff),
            PyBool::new(py, st.converged).to_owned().into_any(),
            st.damped_here.into_pyobject(py)?.into_any(),
            fl(st.carried_ep_kg), fl(st.return_dry_kg), fl(st.hardware_est_kg),
            cascade, opt(st.trial_payload)?, opt(st.r_ret)?, hold_water,
        ])?;
        self.fast.fetch_add(1, Relaxed);
        count_knap(self);
        match args {
            None => PyTuple::new(py, [kind.into_pyobject(py)?.into_any(), state.into_any()]),
            Some((a, b, c)) => PyTuple::new(py, [
                kind.into_pyobject(py)?.into_any(), state.into_any(),
                PyTuple::new(py, [a, b, c])?.into_any(),
            ]),
        }
    }

    /// (loops answered in Rust, loops handed back to Python) since construction.
    fn counts(&self) -> (u64, u64) {
        (self.fast.load(Relaxed), self.slow.load(Relaxed))
    }

    /// (knapsack evaluations answered in Rust, evaluations that called back
    /// into Python), over the runs Rust answered, since construction.
    fn knapsack_counts(&self) -> (u64, u64) {
        (self.knap_native.load(Relaxed), self.knap_callback.load(Relaxed))
    }
}

#[cfg(test)]
mod slot_tests {
    use super::*;

    /// The generated match and the tables it was generated from agree on
    /// every name, both ways.
    #[test]
    fn slot_matches_tables() {
        for (i, n) in F_NAMES.iter().enumerate() {
            assert_eq!(slot(n), Some(Slot::F(i, F_INT_OK.contains(n))), "{n}");
        }
        for (i, n) in B_NAMES.iter().enumerate() {
            assert_eq!(slot(n), Some(Slot::B(i)), "{n}");
        }
        assert_eq!(slot(O_PAYLOAD_CAP), Some(Slot::Cap));
        assert_eq!(slot(O_HOLD_REFINING), Some(Slot::Hold));
        assert_eq!(slot(O_CARGO_WATER), Some(Slot::Water));
        assert_eq!(slot(O_CARGO), Some(Slot::Cargo));
        assert_eq!(slot("no_such_input"), None);
    }
}
