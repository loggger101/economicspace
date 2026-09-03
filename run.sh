#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  Linux / macOS launcher.  The POSIX counterpart of run.bat, same options and
#  same semantics, so `run.sh quick leo` does what `run.bat quick leo` does.
#
#  Two rules are inherited from run.bat deliberately, because both were learned
#  the hard way there:
#
#    1. NOTHING PROMPTS ONCE AN ARGUMENT WAS GIVEN.  run.bat's `set /p` against
#       a stdin that a scheduled job holds open but never writes to does not
#       read EOF, it waits forever, so the failure is a hang rather than an
#       exit code.  `read` here has the same shape, so the destination prompt
#       is guarded on BOTH "no argument was given" AND "stdin is a terminal".
#       The test is `./run.sh quick < /dev/null`, not a run from a console.
#
#    2. This adds no model default the pipeline does not already have.  The
#       presets cap rows and fly raw ore at N = 1 so that a double-click does
#       not start the tens-of-hours default cell; everything else is
#       run_pipeline.py's own.
#
#  The dashboard target is not a port of run.bat's: there is no Dashboard.vbs
#  and no windowless-start problem here, and a DGX Spark is usually headless,
#  so it runs streamlit in the foreground on 0.0.0.0 and prints the URL.
# ---------------------------------------------------------------------------
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# Parity with run.bat, and belt and braces rather than the fix.  The fix is
# that every print in the four modules is ASCII; this covers tqdm, exception
# text and any data value that reaches stdout under a POSIX locale that picked
# ASCII.  It cannot move an output byte: the only bare open() in the modules is
# binary, and every CSV is written by to_csv, which is UTF-8 regardless.
export PYTHONUTF8=1

# ---------------------------------------------------------------------------
#  Interpreter.  A local .venv wins if it exists, because that is what `setup`
#  builds and it is the only way to pin the versions the numbers were measured
#  on.  `python` is checked last: on some distributions it is Python 2, and on
#  Windows it is the Microsoft Store alias, which is why run.bat uses `py`.
# ---------------------------------------------------------------------------
if [ -x "$HERE/.venv/bin/python" ]; then
  PY="$HERE/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PY="$(command -v python)"
else
  echo "  No python3 on PATH.  Try:  sudo apt install python3 python3-venv" >&2
  exit 127
fi

DESTINATIONS="cislunar lunar_surface leo mars_surface earth_surface mars_orbit geo"

usage() {
  cat <<'EOF'

  ASTEROID PROFITABILITY PIPELINE

    ./run.sh setup    [--loose]    create .venv and install requirements
    ./run.sh platform              check this host can reproduce the numbers
    ./run.sh inputs                check the Stage 1-3 CSVs Stage 4 reads
    ./run.sh build                 rebuild master.py from modules/

    ./run.sh quick      [dest]     small capped run, all four stages
    ./run.sh rerun      [dest]     Stage 4 only, against the catalog on disk
    ./run.sh standard   [dest]     larger capped run, Stage 4 only
    ./run.sh full       [dest]     THE PIPELINE DEFAULTS, hours per cell

    ./run.sh verify                the release checks, ~5 min form
    ./run.sh campaign   [args]     the resumable measurement queue
    ./run.sh ui         [port]     the Streamlit dashboard, foreground
    ./run.sh help                  run_pipeline.py --help

  [dest] is one of:
EOF
  echo "    $DESTINATIONS"
  echo
  echo "  Omitted, it defaults to cislunar, which is the model's best case and"
  echo "  the destination the catalog on disk is normally priced for."
  echo
}

# ---------------------------------------------------------------------------
#  Destination.  Stage 2 decides what a kilogram sells for and Stage 4 decides
#  the architecture that puts it there, and they MUST agree; run_pipeline.py
#  writes both through MASTER_CONFIG from this one value.
# ---------------------------------------------------------------------------
pick_destination() {
  DEST="${1:-}"
  if [ -n "$DEST" ]; then
    case " $DESTINATIONS " in
      *" $DEST "*) return 0 ;;
      *) echo "  '$DEST' is not a destination.  One of: $DESTINATIONS" >&2
         exit 2 ;;
    esac
  fi
  # Rule 1: only ask when there is a human on the other end.
  if [ ! -t 0 ]; then DEST="cislunar"; return 0; fi
  echo
  echo "  Deliver to which destination?"
  local i=1
  for d in $DESTINATIONS; do echo "    $i) $d"; i=$((i + 1)); done
  echo
  printf "  Choose [1]: "
  read -r choice || choice=""
  i=1
  DEST="cislunar"
  for d in $DESTINATIONS; do
    [ "$choice" = "$i" ] && DEST="$d"
    i=$((i + 1))
  done
  echo "  -> $DEST"
}

# `--yes` skips the overwrite and long-run confirmations.  Passed only when
# this is NOT an interactive terminal, which is the same split run.bat makes:
# a scripted invocation must never block, a typed one should still be asked
# before it re-fetches something that cannot be got back.
YES=""
[ -t 0 ] || YES="--yes"

# ---------------------------------------------------------------------------
#  Setup.  The PINNED set is the default, because the reason to stand this up
#  on a second host is to reproduce a number, and numpy picks SIMD kernels per
#  RELEASE as well as per architecture: a minor upgrade is exactly the kind of
#  thing that moves a float in the last bit, and every release in versions.md
#  is argued from bit-identity.
#
#  It falls back to the loose set rather than failing, because a pinned wheel
#  that does not exist for aarch64 has to be BUILT, and that can fail for
#  reasons having nothing to do with this repo.  A working loose install is
#  worth more than a broken pinned one; what matters is that the difference is
#  said out loud rather than found later in a hash mismatch, and
#  "./run.sh platform" is what turns it into a measurement.
#
#  psutil is on the loose line and in the lock file but NOT in
#  requirements.txt, which asserts in its own first line that it mirrors
#  _MASTER_REQUIRED and is checked against it by verify_docs.py check 7.  Only
#  campaign/memwatch.py imports it, and the pipeline must not grow a dependency
#  for a tool it does not use.
# ---------------------------------------------------------------------------
cmd_setup() {
  echo "  Creating .venv with $PY"
  "$PY" -m venv .venv || {
    echo "  venv failed.  Try:  sudo apt install python3-venv" >&2; exit 1; }
  local vpy="$HERE/.venv/bin/python"
  "$vpy" -m pip install --upgrade pip || {
    echo "  pip could not update itself; continuing with the venv's own." >&2; }

  if [ "${1:-}" = "--loose" ]; then
    echo "  Installing the LOOSE set (--loose): the latest of everything."
    "$vpy" -m pip install -r requirements.txt -r requirements-ui.txt psutil || {
      echo "  install failed." >&2; exit 1; }
  else
    echo "  Installing the PINNED set: what every committed number was"
    echo "  measured on.  Pass --loose for the latest of everything instead."
    # --only-binary is what makes the fallback FAST rather than a 40-minute
    # source build of pyarrow that then fails anyway.  It is also the honest
    # reading of what the pinned set is for: a locally compiled extension is
    # not the artefact the numbers were measured against, so if the wheel is
    # not there, the pin has already failed and the loose set is the answer.
    if ! "$vpy" -m pip install --only-binary=:all: -r requirements-lock.txt; then
      echo
      echo "  The pinned install failed, most likely a wheel that does not" >&2
      echo "  exist for this architecture and could not be built.  Falling" >&2
      echo "  back to the loose set." >&2
      echo
      "$vpy" -m pip install -r requirements.txt -r requirements-ui.txt psutil || {
        echo "  the loose install failed too." >&2; exit 1; }
      echo
      echo "  NOTE: this environment is NOT the one the numbers were measured"
      echo "  on.  ./run.sh platform says whether it still reproduces them."
    fi
  fi
  echo
  echo "  Done.  Two checks before anything long, in this order:"
  echo "      ./run.sh platform      can this host reproduce the arithmetic"
  echo "      ./run.sh inputs        are the CSVs Stage 4 reads even here"
}

# ---------------------------------------------------------------------------
#  Inputs.  Delegated to run_pipeline.py rather than listed here, because that
#  is where preflight already holds the list, and a manifest written twice is
#  a manifest that drifts.  Nothing is fetched and no stage runs.
# ---------------------------------------------------------------------------
cmd_inputs() {
  exec "$PY" run_pipeline.py --stages 4 --check-inputs
}

cmd_campaign() {
  # The queue is resumable and skips every cell already recorded rc == 0, so
  # re-running it after a kill costs at most the in-flight cell.
  echo "  Workers: ${CAMPAIGN_WORKERS:-12} (set CAMPAIGN_WORKERS to change)"
  exec "$PY" campaign/run_queue.py "$@"
}

cmd_verify() {
  # verify.py defaults to `--tag head`, and there is usually no baseline-head,
  # which would silently turn the most important of the six checks into a hash
  # print.  Use the newest baseline actually on disk.
  local tag=""
  if [ -d .verify ]; then
    tag="$(ls -1dt .verify/baseline-* 2>/dev/null | head -1 || true)"
    tag="${tag##*/baseline-}"
  fi
  if [ -n "$tag" ]; then
    echo "  Comparing against baseline '$tag'."
    exec "$PY" verify.py check --tag "$tag" --skip prune parallel
  fi
  echo "  No baseline under .verify/ -- check 1 has nothing to compare"
  echo "  against, so it reports NOT VERIFIED and exits 1.  Make one on a"
  echo "  CLEAN tree BEFORE editing:   $PY verify.py baseline --tag mytag"
  exec "$PY" verify.py check --skip prune parallel
}

ACTION="${1:-}"
shift || true

case "$ACTION" in
  setup)     cmd_setup "$@" ;;
  platform)  exec "$PY" platform_check.py "$@" ;;
  inputs)    cmd_inputs ;;
  build)     exec "$PY" build_master.py ;;
  verify)    cmd_verify ;;
  campaign)  cmd_campaign "$@" ;;
  help|--help|-h)
             exec "$PY" run_pipeline.py --help ;;
  ui)
    # The same dashboard run.bat opens, and the same ui.py: it drives
    # the pipeline in-process, imports nothing platform-specific and
    # spawns no subprocess, so nothing here is a port.  What differs is
    # the WAY it is started.  run.bat hands off to Dashboard.vbs for a
    # windowless start and a control window in place of a console; a
    # Spark reached over ssh has no desktop to put either on, so this
    # runs the server in the foreground and Ctrl-C is the stop button.
    PORT="${1:-8501}"
    if ! "$PY" -c "import streamlit" 2>/dev/null; then
      echo "  streamlit is not installed in $PY." >&2
      echo "  Run:  ./run.sh setup     (or: $PY -m pip install streamlit)" >&2
      exit 1
    fi
    # 0.0.0.0 is a bind address, not an address to type.  Print the ones
    # that will actually resolve from the laptop: "open 0.0.0.0:8501" is
    # the commonest way this goes wrong on a headless box.
    echo
    echo "  Dashboard starting.  Ctrl-C stops it."
    for ip in $(hostname -I 2>/dev/null || true); do
      echo "      http://$ip:$PORT"
    done
    echo "      http://localhost:$PORT     (only from this machine)"
    echo
    echo "  If nothing loads from another machine the port is closed:"
    echo "      sudo ufw allow $PORT/tcp"
    echo "  or forward it over the ssh session you already have:"
    echo "      ssh -L $PORT:localhost:$PORT <user>@<this-host>"
    echo
    exec "$PY" -m streamlit run ui.py \
         --server.address 0.0.0.0 --server.port "$PORT" \
         --server.headless true
    ;;
  quick)
    pick_destination "${1:-}"
    exec "$PY" run_pipeline.py --preset quick --destination "$DEST" $YES
    ;;
  rerun)
    pick_destination "${1:-}"
    exec "$PY" run_pipeline.py --preset quick --stages 4 \
         --destination "$DEST" $YES
    ;;
  standard)
    pick_destination "${1:-}"
    exec "$PY" run_pipeline.py --preset standard --stages 4 \
         --destination "$DEST" $YES
    ;;
  full)
    pick_destination "${1:-}"
    echo
    echo "  THE PIPELINE DEFAULTS: every one of 1.55 million rows,"
    echo "  beneficiated, with the programme search on.  This preset overrides"
    echo "  nothing; it is what a configure-nothing run does.  Measured"
    echo "  2026-08-24 on the reference host: Stage 4 alone is 1.6 h at"
    echo "  cislunar and 3.8 h at earth_surface.  Ctrl-C is safe, each stage"
    echo "  writes its CSV before the next one starts."
    echo
    exec "$PY" run_pipeline.py --preset full --destination "$DEST" $YES
    ;;
  ""|menu)
    usage
    ;;
  *)
    echo "  '$ACTION' is not one of the options." >&2
    usage
    exit 2
    ;;
esac
