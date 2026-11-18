#!/bin/bash
# Build the gate's work directory OUTSIDE OneDrive: a copy of Stage 1-3's
# outputs (Stage 4 writes its catalog there, so never point the gate at the
# live asteroid_pipeline/) and the two solver captures verify_rust replays.
#
#   bash rust/es_core/gate/make_workdir.sh WORKDIR
#
# Idempotent: an existing copy or capture is kept.  The captures take about
# 40 minutes together; they need es_core NOT required (capture.py runs the
# Python solver).  Run nothing else that reads the catalog meanwhile: two
# Stage 4 processes over the full catalog ran a 32 GB host out of memory.
set -u
W="${1:?usage: make_workdir.sh WORKDIR (outside OneDrive)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
case "$(cd "$(dirname "$W")" 2>/dev/null && pwd)/" in
  *OneDrive*) echo "refused: $W is inside OneDrive"; exit 2;;
esac
mkdir -p "$W/out"
SRC="$REPO/asteroid_pipeline"
if [ ! -f "$W/out/asteroid_catalog.csv" ]; then
  echo "copying Stage 1-3 outputs from $SRC"
  cp "$SRC"/asteroid_catalog.csv "$SRC"/catalog_manifest.json "$SRC"/catalog_taxonomy.json \
     "$SRC"/mineral_value_catalog.csv "$SRC"/mineral_value_manifest.json "$W/out/" || exit 1
  cp -r "$SRC/mineral_value" "$SRC/transportation" "$W/out/" || exit 1
fi
DEST="${DEST:-cislunar}"
python -c "import json,sys; d=json.load(open(sys.argv[1])).get('destination'); print('Stage 2 table priced for:', d); sys.exit(0 if d==sys.argv[2] else 3)" \
  "$W/out/mineral_value_manifest.json" "$DEST" < /dev/null || {
  echo "the gate will run --destination $DEST; install that destination's Stage 2"
  echo "table INTO THE WORK DIR (never the live asteroid_pipeline/), then rerun:"
  echo "  python run_pipeline.py --stages 2 --destination $DEST --output \"$W/out\" --yes"
  echo "(then check its mineral_value_manifest.json names $DEST)"
  exit 3; }
cd "$REPO"
CAP="rust/es_core/capture.py"
# capture DIR ROWS PKL FLAGS...: record, then refuse an empty capture.
# capture.py swallows run_pipeline's SystemExit, so a refused run (preflight's
# destination MISMATCH) used to write a capture of 0 calls and carry on.
capture() {
  local dir="$1" rows="$2" pkl="$3"; shift 3
  [ -f "$pkl" ] && return 0
  local line
  line=$(python -X utf8 "$CAP" "$REPO" "$dir" "$rows" "$pkl" "$@" < /dev/null 2>&1 | grep -E "^CAPTURED")
  echo "$line ($pkl)"
  case "$line" in
    "CAPTURED 0"|"") rm -f "$pkl"; echo "refused: empty capture $pkl"; exit 4;;
  esac
}
capture "$W/out" 150 "$W/cap_raw.pkl" --destination cislunar --raw --no-search
# mars_surface on purpose: the solver capture records solver inputs only, and
# this destination reaches the solver's surface legs.  Its prices are
# irrelevant to the capture, but preflight() refuses a destination the Stage 2
# table was not priced for, so the capture reads its own copy of the inputs
# with mars_surface's table installed from the pinned price release.
MARS="$W/out_mars"
if [ ! -f "$W/cap_ben.pkl" ]; then
  if [ ! -f "$MARS/asteroid_catalog.csv" ]; then
    mkdir -p "$MARS"
    cp "$W/out"/asteroid_catalog.csv "$W/out"/catalog_manifest.json \
       "$W/out"/catalog_taxonomy.json "$MARS/" || exit 1
    cp -r "$W/out/transportation" "$MARS/" || exit 1
  fi
  python -c "import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get('destination')=='mars_surface' else 3)" \
    "$MARS/mineral_value_manifest.json" < /dev/null 2>/dev/null || {
    echo "installing mars_surface's Stage 2 table into $MARS"
    python run_pipeline.py --stages 2 --destination mars_surface --output "$MARS" --yes \
      < /dev/null > "$W/stage2_mars.log" 2>&1
    python -c "import json,sys; d=json.load(open(sys.argv[1])).get('destination'); print('Stage 2 table priced for:', d); sys.exit(0 if d=='mars_surface' else 3)" \
      "$MARS/mineral_value_manifest.json" < /dev/null || { echo "mars_surface Stage 2 install failed: $W/stage2_mars.log"; exit 3; }
  }
  capture "$MARS" 60 "$W/cap_ben.pkl" --destination mars_surface --beneficiated --search
fi
ls -la "$W" "$W/out"
