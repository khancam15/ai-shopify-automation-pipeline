#!/usr/bin/env bash
# run.sh — VPS entry point for the Etsy pipeline
#
# Usage:
#   ./run.sh db-init               — initialise SQLite database (run once on new VPS)
#   ./run.sh phase1                — Brand Builder crew (writes outputs/brand_guide.md)
#   ./run.sh phase2                — Launch Executor   (writes outputs/master.txt)
#   ./run.sh phase2-rich           — Autonomous Executor (richer prompt engine)
#   ./run.sh phase4 <product>      — Process images → build listing → validate → stage
#   ./run.sh phase5 <product>      — Upload staged listing to Etsy (Playwright)
#   ./run.sh phase6 <product>      — Post-publish SEO gap analysis
#   ./run.sh phase7                — Daily health dashboard (stdout for n8n)
#   ./run.sh all                   — Full pipeline: phase1 → phase2
#   ./run.sh full <product>        — Phases 4 → 5 → 6 for one product
#
# Cron examples:
#   0 6 * * * /path/to/project/run.sh phase2 >> /path/to/project/outputs/cron.log 2>&1
#   0 8 * * * /path/to/project/run.sh phase7 >> /path/to/project/outputs/cron.log 2>&1

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
PRODUCT="${2:-}"

# Phase 4–6 and full require a product name argument
_require_product() {
    if [[ -z "$PRODUCT" ]]; then
        echo "[error] Phase $PHASE requires a product name: ./run.sh $PHASE <product_name>"
        exit 1
    fi
}

case "$PHASE" in
    db-init)
        echo "[run.sh] Initialising database"
        "$PYTHON" scripts/db.py
        ;;
    digest)
        echo "[run.sh] Sending email digest now"
        "$PYTHON" scripts/email_digest.py
        ;;
    watch)
        echo "[run.sh] Checking Canva exports inbox"
        "$PYTHON" scripts/canva_watcher.py
        ;;
    meta)
        _require_product
        echo "[run.sh] Generating meta.json for: $PRODUCT"
        "$PYTHON" scripts/meta_generator.py "$PRODUCT" ${3:+--price "$3"}
        ;;
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
    phase4)
        _require_product
        echo "[run.sh] Phase 4 — Process images, build listing, validate, stage: $PRODUCT"
        "$PYTHON" scripts/image_processor.py "$PRODUCT"
        "$PYTHON" scripts/listing_builder.py "$PRODUCT"
        "$PYTHON" scripts/pre_upload_validator.py "$PRODUCT"
        "$PYTHON" scripts/file_organizer.py "$PRODUCT"
        ;;
    phase5)
        _require_product
        echo "[run.sh] Phase 5 — Upload to Etsy: $PRODUCT"
        "$PYTHON" scripts/etsy_uploader.py "$PRODUCT"
        ;;
    phase6)
        _require_product
        echo "[run.sh] Phase 6 — SEO analysis: $PRODUCT"
        "$PYTHON" scripts/seo_analyzer.py "$PRODUCT"
        ;;
    phase7)
        echo "[run.sh] Phase 7 — Health dashboard"
        "$PYTHON" scripts/health_dashboard.py
        ;;
    all)
        echo "[run.sh] Running full pipeline: Phase 1 → Phase 2"
        "$PYTHON" scripts/etsy_brand_crew.py
        "$PYTHON" scripts/etsy_launch_executor.py
        ;;
    full)
        _require_product
        echo "[run.sh] Full product pipeline: Phase 4 → 5 → 6 for: $PRODUCT"
        "$PYTHON" scripts/image_processor.py "$PRODUCT"
        "$PYTHON" scripts/listing_builder.py "$PRODUCT"
        "$PYTHON" scripts/pre_upload_validator.py "$PRODUCT"
        "$PYTHON" scripts/file_organizer.py "$PRODUCT"
        "$PYTHON" scripts/etsy_uploader.py "$PRODUCT"
        "$PYTHON" scripts/seo_analyzer.py "$PRODUCT"
        ;;
    *)
        echo "Usage: $0 {db-init|phase1|phase2|phase2-rich|phase4|phase5|phase6|phase7|all|full} [product_name]"
        exit 1
        ;;
esac
