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
[ -f "$W/cap_raw.pkl" ] || python -X utf8 "$CAP" "$REPO" "$W/out" 150 "$W/cap_raw.pkl" \
  --destination cislunar --raw --no-search < /dev/null 2>&1 | grep -E "^CAPTURED"
# mars_surface on purpose: the solver capture records solver inputs only, and
# this destination reaches the solver's surface legs (prices are irrelevant).
[ -f "$W/cap_ben.pkl" ] || python -X utf8 "$CAP" "$REPO" "$W/out" 60 "$W/cap_ben.pkl" \
  --destination mars_surface --beneficiated --search < /dev/null 2>&1 | grep -E "^CAPTURED"
ls -la "$W" "$W/out"
