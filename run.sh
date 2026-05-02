#!/usr/bin/env bash
# run.sh — VPS entry point for the Etsy pipeline
# Usage:
#   ./run.sh phase1          — run brand builder crew (writes outputs/brand_guide.md)
#   ./run.sh phase2          — run launch executor   (writes outputs/master.txt)
#   ./run.sh phase2-rich     — run richer prompt engine
#   ./run.sh all             — run phase1 then phase2
#
# Cron example (runs phase2 daily at 6am server time):
#   0 6 * * * /path/to/project/run.sh phase2 >> /path/to/project/outputs/cron.log 2>&1

set -euo pipefail

# Resolve the project root regardless of CWD
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "[error] Virtual environment not found at .venv/"
    echo "        Run: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    echo "[error] .env file not found — copy .env.example and fill in your API keys"
    exit 1
fi

PHASE="${1:-}"

case "$PHASE" in
    phase1)
        echo "[run.sh] Starting Phase 1 — Brand Builder"
        "$PYTHON" scripts/etsy_brand_crew.py
        ;;
    phase2)
        echo "[run.sh] Starting Phase 2 — Launch Executor"
        "$PYTHON" scripts/etsy_launch_executor.py
        ;;
    phase2-rich)
        echo "[run.sh] Starting Phase 2 (rich) — Autonomous Executor"
        "$PYTHON" scripts/etsy_autonomous.py
        ;;
    all)
        echo "[run.sh] Running full pipeline: Phase 1 → Phase 2"
        "$PYTHON" scripts/etsy_brand_crew.py
        "$PYTHON" scripts/etsy_launch_executor.py
        ;;
    *)
        echo "Usage: $0 {phase1|phase2|phase2-rich|all}"
        exit 1
        ;;
esac
