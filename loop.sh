#!/usr/bin/env bash
# loop.sh — Autonomous pipeline loop for VPS
#
# Runs one full product cycle per iteration, then sleeps before the next.
# Each phase must exit 0 before the next phase starts — any failure halts
# the current cycle, logs the error, and waits for the next scheduled run.
#
# Usage:
#   ./loop.sh                    — run forever (default 3600s sleep between cycles)
#   ./loop.sh --once             — run exactly one cycle then exit
#   SLEEP=7200 ./loop.sh         — override sleep interval
#
# Logs:
#   logs/loop.log                — all stdout/stderr from every cycle
#   logs/loop_errors.log         — failures only (easier to scan)
#
# Stop the loop:
#   kill $(cat logs/loop.pid)
#   — or — Ctrl+C if running in foreground

set -uo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="$SCRIPT_DIR/.venv/bin/python"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/loop.log"
ERR_FILE="$LOG_DIR/loop_errors.log"
PID_FILE="$LOG_DIR/loop.pid"
SLEEP="${SLEEP:-3600}"
RUN_ONCE="${1:-}"

# ── Guards ────────────────────────────────────────────────────────────────────
mkdir -p "$LOG_DIR"

if [[ ! -x "$PYTHON" ]]; then
    echo "[loop] ERROR: .venv not found. Run: ./setup_vps.sh" >&2
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    echo "[loop] ERROR: .env not found. Copy .env.example and fill in API keys." >&2
    exit 1
fi

echo $$ > "$PID_FILE"

# ── Helpers ───────────────────────────────────────────────────────────────────
_ts()  { date -u '+%Y-%m-%d %H:%M:%S UTC'; }

_log() {
    local msg="[loop] $(_ts) $*"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

_err() {
    local msg="[loop][ERROR] $(_ts) $*"
    echo "$msg" >&2
    echo "$msg" >> "$LOG_FILE"
    echo "$msg" >> "$ERR_FILE"
}

_sleep_or_exit() {
    if [[ "$RUN_ONCE" == "--once" ]]; then
        _log "Run-once mode — exiting."
        exit 0
    fi
    _log "Sleeping ${SLEEP}s until next cycle..."
    sleep "$SLEEP"
}

_run_phase() {
    local label="$1"
    shift
    _log "Starting $label: $*"
    if "$@" >> "$LOG_FILE" 2>&1; then
        _log "$label completed OK"
        return 0
    else
        local code=$?
        _err "$label FAILED (exit $code)"
        return $code
    fi
}

# ── Trap clean exit ───────────────────────────────────────────────────────────
_cleanup() {
    _log "Loop stopped (signal received)."
    rm -f "$PID_FILE"
}
trap _cleanup INT TERM EXIT

# ── Main loop ─────────────────────────────────────────────────────────────────
_log "========================================"
_log "Autonomous loop starting. PID=$$"
_log "Sleep interval: ${SLEEP}s between cycles"
_log "Logs: $LOG_FILE"
_log "========================================"

CYCLE=0

while true; do
    CYCLE=$((CYCLE + 1))
    _log "──────── CYCLE $CYCLE START ────────"

    # ── Phase 1: Brand Builder ────────────────────────────────────────────────
    # Only regenerates brand_guide.md if it's older than 7 days, to avoid
    # burning Serper + Anthropic credits on every hourly cycle.
    BRAND_GUIDE="$SCRIPT_DIR/outputs/brand_guide.md"
    BRAND_AGE_LIMIT=$((7 * 24 * 3600))

    RUN_PHASE1=true
    if [[ -f "$BRAND_GUIDE" ]]; then
        BRAND_MOD=$(date -r "$BRAND_GUIDE" +%s 2>/dev/null || stat -c %Y "$BRAND_GUIDE" 2>/dev/null || echo 0)
        NOW=$(date +%s)
        AGE=$(( NOW - BRAND_MOD ))
        if [[ $AGE -lt $BRAND_AGE_LIMIT ]]; then
            _log "Phase 1 skipped — brand_guide.md is $((AGE / 3600))h old (refreshes after 168h)"
            RUN_PHASE1=false
        fi
    fi

    if [[ "$RUN_PHASE1" == true ]]; then
        _run_phase "Phase 1 (brand builder)" "$PYTHON" scripts/etsy_brand_crew.py \
            || { _log "Cycle $CYCLE aborted at phase 1."; _sleep_or_exit; continue; }
    fi

    # ── Phase 2: Launch Executor ──────────────────────────────────────────────
    _run_phase "Phase 2 (launch executor)" "$PYTHON" scripts/etsy_launch_executor.py \
        || { _log "Cycle $CYCLE aborted at phase 2."; _sleep_or_exit; continue; }

    # ── Pick next queued product ──────────────────────────────────────────────
    PRODUCT=$("$PYTHON" - 2>>"$LOG_FILE" <<'PYEOF'
import sys
sys.path.insert(0, 'scripts')
from db import get_queue_items
rows = get_queue_items('pending')
print(rows[0]['product_name'] if rows else '')
PYEOF
)

    if [[ -z "$PRODUCT" ]]; then
        _log "No pending products in queue — nothing to upload this cycle."
        _sleep_or_exit
        continue
    fi

    _log "Next product: $PRODUCT"

    # ── Phase 4: Process + Stage ──────────────────────────────────────────────
    _run_phase "Phase 4.1 (image processor)"      "$PYTHON" scripts/image_processor.py     "$PRODUCT" \
        || { _log "Cycle $CYCLE aborted at phase 4.1."; _sleep_or_exit; continue; }

    _run_phase "Phase 4.2 (listing builder)"      "$PYTHON" scripts/listing_builder.py     "$PRODUCT" \
        || { _log "Cycle $CYCLE aborted at phase 4.2."; _sleep_or_exit; continue; }

    _run_phase "Phase 4.3 (validator)"            "$PYTHON" scripts/pre_upload_validator.py "$PRODUCT" \
        || { _log "Cycle $CYCLE aborted at phase 4.3 — listing failed validation."; _sleep_or_exit; continue; }

    _run_phase "Phase 4.5 (file organizer)"       "$PYTHON" scripts/file_organizer.py      "$PRODUCT" \
        || { _log "Cycle $CYCLE aborted at phase 4.5."; _sleep_or_exit; continue; }

    # ── Phase 5: Upload to Etsy ───────────────────────────────────────────────
    _run_phase "Phase 5 (etsy uploader)"          "$PYTHON" scripts/etsy_uploader.py       "$PRODUCT" \
        || { _log "Cycle $CYCLE aborted at phase 5."; _sleep_or_exit; continue; }

    # ── Phase 6: SEO Analysis (non-fatal) ────────────────────────────────────
    # Listing is already published at this point so a failure here is safe to skip.
    _run_phase "Phase 6 (seo analyzer)"           "$PYTHON" scripts/seo_analyzer.py        "$PRODUCT" \
        || _err "Phase 6 failed — listing is live, SEO report skipped."

    # ── Phase 7: Health Dashboard (non-fatal) ────────────────────────────────
    _run_phase "Phase 7 (health dashboard)"       "$PYTHON" scripts/health_dashboard.py \
        || _err "Phase 7 failed — non-fatal."

    _log "──────── CYCLE $CYCLE COMPLETE — product: $PRODUCT ────────"

    _sleep_or_exit
done
