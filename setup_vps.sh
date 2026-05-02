#!/usr/bin/env bash
# setup_vps.sh — Phase 0: one-time VPS environment bootstrap
#
# Run once after cloning the repo to a new server:
#   chmod +x setup_vps.sh && ./setup_vps.sh
#
# What it does:
#   1. Creates all required pipeline directories
#   2. Creates .env from .env.example if not present
#   3. Creates Python virtual environment
#   4. Installs pip dependencies
#   5. Installs Playwright Chromium with system deps
#   6. Initialises the SQLite database
#   7. Sets executable bits on run.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "  AI Etsy Pipeline — VPS Setup"
echo "========================================"
echo ""

# 1 — Directory structure
echo "[1/7] Creating pipeline directories..."
mkdir -p \
    01_Queue \
    02_Products \
    03_Canva_Exports \
    "04_Assets/ReadyToUpload" \
    "04_Assets/Archived" \
    outputs
echo "      Done."

# 2 — .env
echo "[2/7] Checking .env..."
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    if [[ -f "$SCRIPT_DIR/.env.example" ]]; then
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        echo "      Created .env from .env.example — fill in your API keys before running the pipeline."
    else
        echo "      WARNING: no .env.example found. Create .env manually with:"
        echo "        ANTHROPIC_API_KEY=..."
        echo "        SERPER_API_KEY=..."
        echo "        ETSY_API_KEY=..."
    fi
else
    echo "      .env already exists — skipping."
fi

# 3 — Virtual environment
echo "[3/7] Setting up Python virtual environment..."
if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
    python3.12 -m venv "$SCRIPT_DIR/.venv"
    echo "      Created .venv with python3.12"
else
    echo "      .venv already exists — skipping creation."
fi

PYTHON="$SCRIPT_DIR/.venv/bin/python"
PIP="$SCRIPT_DIR/.venv/bin/pip"

# 4 — pip dependencies
echo "[4/7] Installing pip dependencies..."
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet -r requirements.txt
echo "      Done."

# 5 — Playwright Chromium
echo "[5/7] Installing Playwright Chromium (with system deps)..."
"$PYTHON" -m playwright install chromium --with-deps
echo "      Done."

# 6 — Database
echo "[6/7] Initialising SQLite database..."
"$PYTHON" scripts/db.py
echo "      Done."

# 7 — Executable bits
echo "[7/7] Setting executable permissions..."
chmod +x "$SCRIPT_DIR/run.sh"
chmod +x "$SCRIPT_DIR/setup_vps.sh"
echo "      Done."

echo ""
echo "========================================"
echo "  Setup complete."
echo ""
echo "  Next steps:"
echo "  1. Edit .env and fill in all API keys"
echo "  2. Log into Etsy in the Playwright profile:"
echo "       ./run.sh phase5-login  (see docs)"
echo "  3. Run the brand builder:"
echo "       ./run.sh phase1"
echo "  4. Run the launch executor:"
echo "       ./run.sh phase2"
echo "========================================"
