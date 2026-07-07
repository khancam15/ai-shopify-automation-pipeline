#!/usr/bin/env bash
# test_infrastructure.sh — Verify new infrastructure is working
#
# Run this script after installing the improvements to verify everything works.
#
# Usage:
#   ./test_infrastructure.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=============================================="
echo "Testing New Infrastructure"
echo "=============================================="
echo

# ── 1. Check Python version ───────────────────────────────────────────────────

echo "[1/8] Checking Python version..."
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "❌ Virtual environment not found at .venv/"
    echo "   Run: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

PY_VERSION=$("$PYTHON" --version 2>&1 | awk '{print $2}')
echo "✅ Python $PY_VERSION found"
echo

# ── 2. Test configuration ─────────────────────────────────────────────────────

echo "[2/8] Testing configuration module..."
if "$PYTHON" scripts/config.py >/dev/null 2>&1; then
    echo "✅ Configuration valid"
else
    echo "⚠️  Configuration has warnings (non-fatal)"
    "$PYTHON" scripts/config.py || true
fi
echo

# ── 3. Test logger ────────────────────────────────────────────────────────────

echo "[3/8] Testing logger module..."
"$PYTHON" scripts/logger.py >/dev/null 2>&1
if [[ -f logs/pipeline.log ]]; then
    echo "✅ Logger working (check logs/pipeline.log)"
else
    echo "⚠️  Logger test completed but no log file created"
fi
echo

# ── 4. Test validation ────────────────────────────────────────────────────────

echo "[4/8] Testing validation module..."
"$PYTHON" scripts/validation.py >/dev/null 2>&1
echo "✅ Validation module working"
echo

# ── 5. Test API retry (circuit breaker) ───────────────────────────────────────

echo "[5/8] Testing API retry module..."
"$PYTHON" -c "from scripts.api_retry import retry_request, _check_circuit; print('✅ API retry module loaded')"
echo

# ── 6. Test health check ──────────────────────────────────────────────────────

echo "[6/8] Running health check (quick mode)..."
if "$PYTHON" scripts/health_check.py --quick; then
    echo "✅ Health check completed"
else
    echo "⚠️  Health check reported issues (review details above)"
fi
echo

# ── 7. Check for security issues ──────────────────────────────────────────────

echo "[7/8] Checking .env security..."
if [[ -f .env ]]; then
    if git check-ignore .env >/dev/null 2>&1; then
        echo "✅ .env is in .gitignore"
    else
        echo "❌ WARNING: .env is NOT in .gitignore!"
        echo "   Add it immediately: echo '.env' >> .gitignore"
    fi
else
    echo "⚠️  .env file not found (expected for new setup)"
fi
echo

# ── 8. Run quick tests ────────────────────────────────────────────────────────

echo "[8/8] Running existing tests..."
if [[ -d tests ]]; then
    "$PYTHON" -m pytest tests/ -q 2>&1 | head -20 || echo "⚠️  Some tests failed (check output above)"
    echo "✅ Test suite ran"
else
    echo "⚠️  No tests directory found"
fi
echo

# ── Summary ───────────────────────────────────────────────────────────────────

echo "=============================================="
echo "Infrastructure Test Complete"
echo "=============================================="
echo
echo "Next steps:"
echo "  1. Review logs/pipeline.log for structured logging"
echo "  2. Run full health check: python scripts/health_check.py"
echo "  3. Check configuration: python scripts/config.py"
echo "  4. Install dev tools: pip install -r requirements-dev.txt"
echo "  5. Run full test suite: pytest --cov=scripts"
echo
echo "Documentation: docs/IMPLEMENTATION.md"
echo

exit 0
