//! Opt-in Rust port of `modules/calc.py::max_return_payload_kg` (prototype).
//!
//! The contract is BIT-IDENTITY with the Python function, not "close enough":
//! the same floats, the same value types (the refusal cascade's `0` masses are
//! Python ints, not floats), the same dict key order, and the same exceptions.
//!
//! How that is kept honest:
//!   * Every float expression is written in the same order and association as
//!     the Python source, with no FMA and no fast-math (rustc contracts nothing
//!     unless asked; Cargo.toml asks for nothing).
//!   * `f64::exp` on x86_64-pc-windows-msvc calls the C runtime's `exp`, the
//!     same function CPython's `math.exp` calls.  `exp_matches_python` in
//!     `verify_rust.py` checks that bitwise rather than assuming it.
//!   * The fast path takes ONLY exact `float` arguments or exact `int`s within
//!     +/-2**53 (never numpy scalars, never bool), an exact `bool` for
//!     `isru_return`, all passed by the keyword names calc.py uses.  Anything else -- a positional call, an int, a numpy
//!     scalar, an unknown keyword, a denominator that is exactly zero -- is
//!     handed to the original Python function untouched, so every odd case
//!     behaves exactly as it always did, exceptions included.
//!   * A result containing any NaN is recomputed by Python
//!     (`Outcome::has_nan`): NaN sign and payload are not portable.

mod ladder;
mod sizing;

use pyo3::intern;
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyTuple};

/// The masses the Python solver returns.  `None` from `solve` means "fall
/// back to Python"; it is never a modelling answer.
pub(crate) enum Outcome {
    /// `_infeasible(r_out, r_ret)`: ints for the masses, as in Python.
    Infeasible { r_out: f64, r_ret: f64 },
    Isru {
        m_payload_max: f64,
        r_out: f64,
        r_ret: f64,
        base_launch: f64,
        m_outbound_prop: f64,
        m_at_asteroid: f64,
        m_tps: f64,
        k: f64,
        k_out: f64,
    },
    Full {
        m_payload_max: f64,
        r_out: f64,
        r_ret: f64,
        m_launch: f64,
        m_outbound_prop: f64,
        m_return_prop: f64,
        m_at_asteroid: f64,
        m_tps: f64,
        m_dry_return: f64,
        m_tank_return: f64,
        m_tank_outbound: f64,
        k: f64,
        k_out: f64,
    },
}

/// Python's two-argument `max(a, b)`: `a` unless `b > a`.
#[inline(always)]
pub(crate) fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}
/// Python's `min(a, b)`: `a` unless `b < a`.
#[inline(always)]
pub(crate) fn py_min(a: f64, b: f64) -> f64 {
    if b < a {
        b
    } else {
        a
    }
}

/// Python's `max(0.0, x)`: the first argument unless the second is strictly
/// greater.  NaN and -0.0 both come back as 0.0, as they do in CPython.
#[inline(always)]
fn py_max0(x: f64) -> f64 {
    if x > 0.0 {
        x
    } else {
        0.0
    }
}

/// `math.exp`: raises OverflowError when a FINITE argument overflows.
/// `None` is that raise.  `exp(inf)` is inf and does not raise, in both.
#[inline(always)]
pub(crate) fn py_exp(x: f64) -> Option<f64> {
    let e = x.exp();
    if e.is_infinite() && x.is_finite() {
        None
    } else {
        Some(e)
    }
}

/// Division as Python does it, except that a zero divisor (Python raises
/// ZeroDivisionError) returns `None` so the caller falls back to Python and
/// lets it raise.
#[inline(always)]
pub(crate) fn py_div(a: f64, b: f64) -> Option<f64> {
    if b == 0.0 {
        None
    } else {
        Some(a / b)
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn solve(
    g0: f64,
    leo_capacity_kg: f64,
    isp_s: f64,
    dv_out_m_s: f64,
    dv_ret_m_s: f64,
    hardware_kg: f64,
    dry_return_kg: f64,
    tps_frac: f64,
    isru_return: bool,
    structure_frac: f64,
    tank_frac: f64,
) -> Option<Outcome> {
    let refuse = Outcome::Infeasible { r_out: 0.0, r_ret: 0.0 };
    if !isp_s.is_finite() || isp_s <= 0.0 {
        return Some(refuse);
    }
    if !(dv_out_m_s.is_finite() && dv_ret_m_s.is_finite()) {
        return Some(refuse);
    }
    if dv_out_m_s < 0.0 || dv_ret_m_s < 0.0 {
        return Some(refuse);
    }
    if !leo_capacity_kg.is_finite() || leo_capacity_kg <= 0.0 {
        return Some(refuse);
    }

    // r_out = math.exp(dv_out_m_s / (isp_s * G0_M_S2)), then r_ret likewise;
    // either OverflowError -> _infeasible() with zeros.
    let r_out = match py_exp(py_div(dv_out_m_s, isp_s * g0)?) {
        Some(v) => v,
        None => return Some(refuse),
    };
    let r_ret = match py_exp(py_div(dv_ret_m_s, isp_s * g0)?) {
        Some(v) => v,
        None => return Some(refuse),
    };
    let s = 1.0 + tps_frac;
    let f = py_max0(structure_frac);
    let t = py_max0(tank_frac);
    // g = s * (1.0 + f) - 1.0 is computed in Python but never read.

    if t * (r_ret - 1.0) >= 1.0 || t * (r_out - 1.0) >= 1.0 {
        return Some(Outcome::Infeasible { r_out, r_ret });
    }
    let k = py_div(1.0, 1.0 - t * (r_ret - 1.0))?;
    let k_out = py_div(1.0, 1.0 - t * (r_out - 1.0))?;
    let launch_budget = py_div(leo_capacity_kg, k_out * r_out)?;

    if isru_return {
        let denom_isru = k * s * (1.0 + f) - 1.0;
        let base_launch = (hardware_kg + k * s * dry_return_kg) * k_out * r_out;
        if base_launch > leo_capacity_kg {
            return Some(Outcome::Infeasible { r_out, r_ret });
        }
        let m_payload_max = if denom_isru > 0.0 {
            let launch_max =
                py_div(launch_budget - hardware_kg - k * s * dry_return_kg, denom_isru)?;
            py_max0(launch_max)
        } else {
            f64::INFINITY
        };
        return Some(Outcome::Isru {
            m_payload_max,
            r_out,
            r_ret,
            base_launch,
            m_outbound_prop: base_launch - (hardware_kg + k * s * dry_return_kg),
            m_at_asteroid: hardware_kg + k * s * dry_return_kg,
            m_tps: tps_frac * dry_return_kg,
            k,
            k_out,
        });
    }

    let denom = k * s * r_ret * (1.0 + f) - 1.0;
    let bracket = launch_budget - hardware_kg - k * s * dry_return_kg * r_ret;
    if bracket <= 0.0 || denom <= 0.0 {
        return Some(Outcome::Infeasible { r_out, r_ret });
    }
    let m_payload_max = py_div(bracket, denom)?;
    if m_payload_max <= 0.0 {
        return Some(Outcome::Infeasible { r_out, r_ret });
    }

    let m_dry_return = dry_return_kg + f * m_payload_max;
    let m_tps = tps_frac * (m_payload_max + m_dry_return);
    let m_after_return = k * s * (m_payload_max * (1.0 + f) + dry_return_kg);
    let m_return_prop = m_after_return * (r_ret - 1.0);
    let m_tank_return = t * m_return_prop;
    let m_at_asteroid = hardware_kg + m_dry_return + m_tps + m_tank_return + m_return_prop;
    let m_outbound_prop = m_at_asteroid * k_out * (r_out - 1.0);
    #[cfg(not(feature = "planted_defect"))]
    let m_tank_outbound = t * m_outbound_prop;
    // A deliberate one-ulp error, built only by `verify_rust.py --plant` to
    // prove the differential check can see the smallest possible drift.
    #[cfg(feature = "planted_defect")]
    let m_tank_outbound = f64::from_bits((t * m_outbound_prop).to_bits() ^ 1);
    let m_launch = m_at_asteroid + m_tank_outbound + m_outbound_prop;

    Some(Outcome::Full {
        m_payload_max,
        r_out,
        r_ret,
        m_launch,
        m_outbound_prop,
        m_return_prop,
        m_at_asteroid,
        m_tps,
        m_dry_return,
        m_tank_return,
        m_tank_outbound,
        k,
        k_out,
    })
}

impl Outcome {
    /// Any NaN among the outputs.  NaN *payloads and signs* are not portable
    /// between CPython and Rust: LLVM treats float addition as commutative,
    /// and on x86 which NaN survives `a + b` depends on operand order, so
    /// the Rust result can carry +NaN where Python's carries -NaN.  Such
    /// calls go to Python, which keeps even NaN bits identical.
    pub(crate) fn has_nan(&self) -> bool {
        match *self {
            Outcome::Infeasible { r_out, r_ret } => r_out.is_nan() || r_ret.is_nan(),
            Outcome::Isru {
                m_payload_max, r_out, r_ret, base_launch, m_outbound_prop,
                m_at_asteroid, m_tps, k, k_out,
            } => [m_payload_max, r_out, r_ret, base_launch, m_outbound_prop,
                  m_at_asteroid, m_tps, k, k_out].iter().any(|v| v.is_nan()),
            Outcome::Full {
                m_payload_max, r_out, r_ret, m_launch, m_outbound_prop,
                m_return_prop, m_at_asteroid, m_tps, m_dry_return,
                m_tank_return, m_tank_outbound, k, k_out,
            } => [m_payload_max, r_out, r_ret, m_launch, m_outbound_prop,
                  m_return_prop, m_at_asteroid, m_tps, m_dry_return,
                  m_tank_return, m_tank_outbound, k, k_out]
                .iter().any(|v| v.is_nan()),
        }
    }
}

/// Build the dict with the same keys, in the same order, with the same value
/// types as the Python function.
pub(crate) fn to_dict<'py>(py: Python<'py>, o: Outcome) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    match o {
        Outcome::Infeasible { r_out, r_ret } => {
            d.set_item(intern!(py, "max_payload_kg"), 0.0f64)?;
            d.set_item(intern!(py, "viable"), false)?;
            d.set_item(intern!(py, "r_out"), r_out)?;
            d.set_item(intern!(py, "r_ret"), r_ret)?;
            for key in [
                intern!(py, "m_launch"),
                intern!(py, "m_outbound_prop"),
                intern!(py, "m_return_prop"),
                intern!(py, "m_at_asteroid"),
                intern!(py, "m_tps"),
                intern!(py, "m_dry_return"),
                intern!(py, "m_tank_return"),
                intern!(py, "m_tank_outbound"),
            ] {
                d.set_item(key, 0i64)?;
            }
        }
        Outcome::Isru {
            m_payload_max,
            r_out,
            r_ret,
            base_launch,
            m_outbound_prop,
            m_at_asteroid,
            m_tps,
            k,
            k_out,
        } => {
            d.set_item(intern!(py, "max_payload_kg"), m_payload_max)?;
            d.set_item(intern!(py, "viable"), true)?;
            d.set_item(intern!(py, "r_out"), r_out)?;
            d.set_item(intern!(py, "r_ret"), r_ret)?;
            d.set_item(intern!(py, "m_launch"), base_launch)?;
            d.set_item(intern!(py, "m_outbound_prop"), m_outbound_prop)?;
            d.set_item(intern!(py, "m_return_prop"), 0.0f64)?;
            d.set_item(intern!(py, "m_at_asteroid"), m_at_asteroid)?;
            d.set_item(intern!(py, "m_tps"), m_tps)?;
            d.set_item(intern!(py, "m_tank_return"), 0.0f64)?;
            d.set_item(intern!(py, "m_tank_outbound"), 0.0f64)?;
            d.set_item(intern!(py, "k_ret"), k)?;
            d.set_item(intern!(py, "k_out"), k_out)?;
        }
        Outcome::Full {
            m_payload_max,
            r_out,
            r_ret,
            m_launch,
            m_outbound_prop,
            m_return_prop,
            m_at_asteroid,
            m_tps,
            m_dry_return,
            m_tank_return,
            m_tank_outbound,
            k,
            k_out,
        } => {
            d.set_item(intern!(py, "max_payload_kg"), m_payload_max)?;
            d.set_item(intern!(py, "viable"), true)?;
            d.set_item(intern!(py, "r_out"), r_out)?;
            d.set_item(intern!(py, "r_ret"), r_ret)?;
            d.set_item(intern!(py, "m_launch"), m_launch)?;
            d.set_item(intern!(py, "m_outbound_prop"), m_outbound_prop)?;
            d.set_item(intern!(py, "m_return_prop"), m_return_prop)?;
            d.set_item(intern!(py, "m_at_asteroid"), m_at_asteroid)?;
            d.set_item(intern!(py, "m_tps"), m_tps)?;
            d.set_item(intern!(py, "m_dry_return"), m_dry_return)?;
            d.set_item(intern!(py, "m_tank_return"), m_tank_return)?;
            d.set_item(intern!(py, "m_tank_outbound"), m_tank_outbound)?;
            d.set_item(intern!(py, "k_ret"), k)?;
            d.set_item(intern!(py, "k_out"), k_out)?;
        }
    }
    Ok(d)
}

const N_ARGS: usize = 10;
const NAMES: [&str; N_ARGS] = [
    "leo_capacity_kg",
    "isp_s",
    "dv_out_m_s",
    "dv_ret_m_s",
    "hardware_kg",
    "dry_return_kg",
    "tps_frac",
    "isru_return",
    "structure_frac",
    "tank_frac",
];
const TPS: usize = 6;
const ISRU: usize = 7;

/// An exact Python `int` (not bool) with |n| <= 2**53, as the f64 it equals.
///
/// Every place the solver uses an argument, it meets a float operand (or goes
/// through `float()`), and CPython converts an int to float before mixed
/// arithmetic; below 2**53 that conversion is exact, so the f64 here is the
/// very operand Python computes with.  Above it, int-vs-float COMPARISONS are
/// exact in Python but not after conversion, so those calls go to Python.
pub(crate) fn exact_small_int(v: &Bound<'_, PyAny>) -> Option<f64> {
    const LIM: i64 = 1 << 53;
    let n: i64 = v.downcast_exact::<PyInt>().ok()?.extract().ok()?;
    if (-LIM..=LIM).contains(&n) {
        Some(n as f64)
    } else {
        None
    }
}

/// Read the keyword-only fast path.  `None` means "not a call the fast path
/// is sure it reproduces exactly"; the caller then defers to Python.
fn read_fast_args(
    args: &Bound<'_, PyTuple>,
    kwargs: Option<&Bound<'_, PyDict>>,
) -> Option<([f64; N_ARGS], bool)> {
    if !args.is_empty() {
        return None;
    }
    let kwargs = kwargs?;
    // Python defaults: tps_frac=0.0, isru_return=False, structure_frac=0.0,
    // tank_frac=0.0.  The six required ones have no default.
    let mut vals = [0.0f64; N_ARGS];
    let mut seen = [false; N_ARGS];
    let mut isru = false;
    for (k, v) in kwargs.iter() {
        let name: &str = k.downcast_exact::<pyo3::types::PyString>().ok()?.to_str().ok()?;
        let i = NAMES.iter().position(|n| *n == name)?;
        if i == ISRU {
            isru = v.downcast_exact::<PyBool>().ok()?.is_true();
        } else if let Ok(fl) = v.downcast_exact::<PyFloat>() {
            vals[i] = fl.value();
        } else if i == TPS {
            // The ISRU branch returns `tps_frac * dry_return_kg` as is: two
            // ints there make a Python int, which the f64 path cannot be.
            return None;
        } else {
            vals[i] = exact_small_int(&v)?;
        }
        seen[i] = true;
    }
    if !seen[..6].iter().all(|s| *s) {
        return None;
    }
    Some((vals, isru))
}

/// A callable that answers exactly like `fallback` (the Python solver), with
/// the common case computed in Rust.
#[pyclass(frozen)]
struct Solver {
    fallback: Py<PyAny>,
    g0: f64,
    fast: std::sync::atomic::AtomicU64,
    slow: std::sync::atomic::AtomicU64,
}

#[pymethods]
impl Solver {
    #[new]
    fn new(fallback: Py<PyAny>, g0: f64) -> Self {
        Solver {
            fallback,
            g0,
            fast: std::sync::atomic::AtomicU64::new(0),
            slow: std::sync::atomic::AtomicU64::new(0),
        }
    }

    #[pyo3(signature = (*args, **kwargs))]
    fn __call__<'py>(
        &self,
        py: Python<'py>,
        args: &Bound<'py, PyTuple>,
        kwargs: Option<&Bound<'py, PyDict>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        use std::sync::atomic::Ordering::Relaxed;
        if let Some((v, isru)) = read_fast_args(args, kwargs) {
            if let Some(o) = solve(
                self.g0, v[0], v[1], v[2], v[3], v[4], v[5], v[6], isru, v[8], v[9],
            ) {
                if !o.has_nan() {
                    self.fast.fetch_add(1, Relaxed);
                    return Ok(to_dict(py, o)?.into_any());
                }
            }
        }
        self.slow.fetch_add(1, Relaxed);
        self.fallback.bind(py).call(args, kwargs)
    }

    /// (fast-path calls, Python-fallback calls) since construction.
    fn counts(&self) -> (u64, u64) {
        use std::sync::atomic::Ordering::Relaxed;
        (self.fast.load(Relaxed), self.slow.load(Relaxed))
    }

    #[getter]
    fn __wrapped__(&self, py: Python<'_>) -> Py<PyAny> {
        self.fallback.clone_ref(py)
    }
}

/// `exp` exactly as the solver calls it, for `verify_rust.py`'s bitwise
/// comparison against `math.exp`.
#[pyfunction]
fn exp_many(xs: Vec<f64>) -> Vec<f64> {
    xs.into_iter().map(f64::exp).collect()
}

/// `ln` exactly as the sizing loop calls it (boil-off), for the same check
/// against `math.log`.
#[pyfunction]
fn log_many(xs: Vec<f64>) -> Vec<f64> {
    xs.into_iter().map(f64::ln).collect()
}

/// Whether this build carries a deliberate one-ulp defect (in the solver,
/// or in the sizing loop's damping blend).
#[pyfunction]
fn planted_defect() -> bool {
    cfg!(feature = "planted_defect") || cfg!(feature = "planted_loop_defect")
        || cfg!(feature = "planted_ladder_defect")
        || cfg!(feature = "planted_memo_defect")
        || cfg!(feature = "planted_knapsack_defect")
}

#[pymodule]
fn es_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Solver>()?;
    m.add_class::<sizing::SizingLoop>()?;
    m.add_class::<ladder::ProgrammeLadder>()?;
    m.add_function(wrap_pyfunction!(log_many, m)?)?;
    m.add_function(wrap_pyfunction!(exp_many, m)?)?;
    m.add_function(wrap_pyfunction!(planted_defect, m)?)?;
    Ok(())
}
