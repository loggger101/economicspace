#!/bin/bash
# The whole Rust gate, sequential.  Every step prints a STEP line and a
# RESULT line; the SUMMARY lists each step's exit code against what it must
# be (want 1 = the step must FAIL: a plant or a guard that must refuse).
#
#   bash rust/es_core/gate/make_workdir.sh WORKDIR      # once
#   bash rust/es_core/gate/gate_all.sh WORKDIR > WORKDIR/gate_all.log 2>&1
#
# WORKDIR is outside OneDrive.  Env: SPACEVALUE (default: ../spacevalue next
# to this repo, on branch rust-cargo-prototype), DEST (default cislunar; the
# work dir's Stage 2 table must be priced for it).  About 75 minutes on the
# reference host.  Run nothing else that reads the catalog meanwhile.
#
# It REINSTALLS es_core and spacevalue_cargo_rs (good, planted, good again)
# into the current interpreter, and leaves the good builds installed.
set -u
W="${1:?usage: gate_all.sh WORKDIR}"
W="$(cd "$W" && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
SV="${SPACEVALUE:-$(cd "$REPO/../spacevalue" && pwd)}"
DEST="${DEST:-cislunar}"
OUT="$W/out"
B="$W/wheels"
export PATH="$HOME/.cargo/bin:$PATH"
PY="python -X utf8"
declare -a RES

rec() {  # name want got
  RES+=("$1|$2|$3")
  echo "RESULT $1 want=$2 got=$3"
}

inst_es() { python -m pip install -q --force-reinstall --no-deps "$B/$1"/es_core-*.whl < /dev/null; }
inst_sv() { python -m pip install -q --force-reinstall --no-deps "$B/$1"/spacevalue_cargo_rs-*.whl < /dev/null; }
SH="rust/es_core/shadow_rust.py"
BEN="--destination $DEST --beneficiated --search"
RAW="--destination $DEST --raw --search"

date; hostname
for f in "$OUT/asteroid_catalog.csv" "$W/cap_ben.pkl" "$W/cap_raw.pkl"; do
  [ -f "$f" ] || { echo "missing $f: run make_workdir.sh first"; exit 2; }
done
cd "$REPO"; python tree_check.py < /dev/null 2>&1 | tail -1
git log -1 --oneline; git status --short; (cd "$SV"; git branch --show-current; git log -1 --oneline; git status --short)

echo "== STEP build"
rm -rf "$B"; mkdir -p "$B"
cd "$REPO/rust/es_core"
export CARGO_TARGET_DIR="$HOME/.cargo-target/es_core"
python -m maturin build --release -o "$B/good" < /dev/null 2>&1 | tail -1
for f in planted_defect planted_loop_defect planted_ladder_defect planted_memo_defect planted_knapsack_defect; do
  python -m maturin build --release --features $f -o "$B/$f" < /dev/null 2>&1 | tail -1
done
cd "$SV/rust/cargo_py"
export CARGO_TARGET_DIR="$HOME/.cargo-target/spacevalue_cargo"
python -m maturin build --release -o "$B/svgood" < /dev/null 2>&1 | tail -1
python -m maturin build --release --features planted_knapsack_defect -o "$B/svplant" < /dev/null 2>&1 | tail -1
n=$(ls "$B"/*/*.whl | wc -l); [ "$n" = 8 ]; rec build_8_wheels 0 $?
cd "$REPO"
inst_es good; inst_sv svgood
python -c "import es_core, spacevalue_cargo_rs; print('installed good:', es_core.planted_defect(), spacevalue_cargo_rs.planted_defect())" < /dev/null

echo "== STEP cargo + pytest (spacevalue)"
(cd "$SV"; cargo test -q --manifest-path rust/cargo_core/Cargo.toml < /dev/null 2>&1 | tail -3; exit ${PIPESTATUS[0]}); rec cargo_test 0 $?
(cd "$SV"; SPACEVALUE_REQUIRE_RUST=1 python -m pytest -q -p no:cacheprovider tests/test_cargo_rust.py < /dev/null 2>&1 | tail -3; exit ${PIPESTATUS[0]}); rec sv_pytest 0 $?
python "$HERE/plants/sv_share.py" "$SV" < /dev/null 2>&1 | tail -1; rec plant_sv_test_share 0 ${PIPESTATUS[0]}
python "$HERE/plants/e2e_stale.py" < /dev/null 2>&1 | tail -1; rec plant_e2e_stale 0 ${PIPESTATUS[0]}

echo "== STEP es_core unit tests (keyword tables)"
(cd "$REPO/rust/es_core"; export CARGO_TARGET_DIR="$HOME/.cargo-target/es_core_test"; PATH="$PATH:$(python -c 'import sys,os;print(os.path.dirname(sys.executable))' < /dev/null)" cargo test --release -q --lib < /dev/null 2>&1 | tail -2; exit ${PIPESTATUS[0]}); rec es_core_tests 0 $?

echo "== STEP bitsame self-check"
python rust/es_core/bitsame.py < /dev/null 2>&1 | tail -1; rec bitsame_selfcheck 0 ${PIPESTATUS[0]}

echo "== STEP verify.py check 8 refuses under the Rust ladder (and only there)"
python "$HERE/plants/check8_guard.py" 1 < /dev/null 2>&1 | tail -1; rec check8_refuses_rust 0 ${PIPESTATUS[0]}
python "$HERE/plants/check8_guard.py" 0 < /dev/null 2>&1 | tail -1; rec check8_runs_python 0 ${PIPESTATUS[0]}

echo "== STEP verify_rust replay"
$PY rust/es_core/verify_rust.py --capture "$W/cap_ben.pkl" "$W/cap_raw.pkl" < /dev/null 2>&1 | tail -8; rec verify_rust 0 ${PIPESTATUS[0]}

echo "== STEP shadow benef/search 40"
$PY $SH "$OUT" 40 $BEN < /dev/null 2>&1 | tail -14; rec shadow_benef 0 ${PIPESTATUS[0]}
echo "== STEP shadow raw/search 60"
$PY $SH "$OUT" 60 $RAW < /dev/null 2>&1 | tail -14; rec shadow_raw 0 ${PIPESTATUS[0]}
echo "== STEP shadow rel+wacc+learning 12"
$PY $SH --set model_reliability=True --set apply_wacc_compounding=True --set model_learning_curve=True "$OUT" 12 $BEN < /dev/null 2>&1 | tail -14; rec shadow_dials 0 ${PIPESTATUS[0]}
echo "== STEP shadow refuses --set on a CLI-owned field"
$PY $SH --set use_beneficiation=False "$OUT" 5 $BEN < /dev/null 2>&1 | tail -1; rec shadow_set_refused 1 ${PIPESTATUS[0]}

echo "== STEP plant: cargo calls bypassing Rust (shim)"
PYTHONPATH="$HERE/plants/svshim" $PY $SH "$OUT" 20 $BEN < /dev/null 2>&1 | grep -E "^CARGO|^VERDICT"; rec plant_cargo_bypass 1 ${PIPESTATUS[0]}

echo "== STEP guard: missing spacevalue_cargo_rs"
python -m pip uninstall -y -q spacevalue_cargo_rs < /dev/null
ECONOMICSPACE_RUST=1 python -c "import sys; sys.path.insert(0,'.'); import modules.calc" < /dev/null 2>&1 | tail -1; rec guard_missing_sv 1 ${PIPESTATUS[0]}
inst_sv svgood

echo "== STEP plant: planted_defect (solver)"
inst_es planted_defect
ECONOMICSPACE_RUST=1 python -c "import sys; sys.path.insert(0,'.'); import modules.calc" < /dev/null 2>&1 | tail -1; rec guard_planted_es 1 ${PIPESTATUS[0]}
$PY rust/es_core/verify_rust.py --expect-defect --capture "$W/cap_ben.pkl" "$W/cap_raw.pkl" < /dev/null 2>&1 | tail -3; rec plant_solver_replay 0 ${PIPESTATUS[0]}
$PY $SH --expect-defect "$OUT" 40 $BEN < /dev/null 2>&1 | grep -E "^SHADOW|^OUTSIDE|^PLANT"; rec plant_solver_shadow 0 ${PIPESTATUS[0]}
for f in planted_loop_defect planted_ladder_defect planted_memo_defect planted_knapsack_defect; do
  echo "== STEP plant: $f"
  inst_es $f
  $PY $SH --expect-defect "$OUT" 40 $BEN < /dev/null 2>&1 | grep -E "^SHADOW|^OUTSIDE|^PLANT"; rec "plant_$f" 0 ${PIPESTATUS[0]}
done
inst_es good

echo "== STEP plant: spacevalue planted_knapsack_defect"
inst_sv svplant
ECONOMICSPACE_RUST=1 python -c "import sys; sys.path.insert(0,'.'); import modules.calc" < /dev/null 2>&1 | tail -1; rec guard_planted_sv 1 ${PIPESTATUS[0]}
$PY $SH "$OUT" 40 $BEN < /dev/null 2>&1 | grep -E "^SHADOW|^CARGO|^VERDICT"; rec plant_sv_shadow 1 ${PIPESTATUS[0]}
inst_sv svgood
python -c "import es_core, spacevalue_cargo_rs; print('reinstalled good:', es_core.planted_defect(), spacevalue_cargo_rs.planted_defect())" < /dev/null

echo "== STEP bench benef/search 20 (results compared)"
$PY rust/es_core/bench_rust.py "$OUT" 20 $BEN < /dev/null 2>&1 | tail -4; rec bench_benef 0 ${PIPESTATUS[0]}

echo "== STEP e2e 150 1 benef/search"
$PY rust/es_core/e2e_rust.py "$OUT" 150 1 $BEN < /dev/null 2>&1 | tail -6; rec e2e_150_1 0 ${PIPESTATUS[0]}
echo "== STEP e2e 150 4 benef/search (pool)"
$PY rust/es_core/e2e_rust.py "$OUT" 150 4 $BEN < /dev/null 2>&1 | tail -6; rec e2e_150_4 0 ${PIPESTATUS[0]}
echo "== STEP e2e 2000 1 raw/search"
$PY rust/es_core/e2e_rust.py "$OUT" 2000 1 $RAW < /dev/null 2>&1 | tail -6; rec e2e_2000_1 0 ${PIPESTATUS[0]}
rm -f "$OUT"/e2e_py_*.csv "$OUT"/e2e_rust_*.csv

echo "== SUMMARY"
bad=0
for r in "${RES[@]}"; do
  IFS='|' read -r n want got <<< "$r"
  if [ "$want" = 0 ] && [ "$got" = 0 ]; then v=OK
  elif [ "$want" = 1 ] && [ "$got" != 0 ]; then v=OK
  else v=BAD; bad=$((bad+1)); fi
  printf "%-36s want %s got %s  %s\n" "$n" "$want" "$got" "$v"
done
echo "steps ${#RES[@]}, bad $bad"
date
[ $bad = 0 ]
