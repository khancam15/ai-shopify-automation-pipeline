#!/usr/bin/env bash
# setup_rclone.sh — Configure rclone cloud sync for Canva exports
#
# Syncs your Dropbox or Google Drive folder to 03_Canva_Exports/ on the VPS.
# Run this ONCE on the VPS after cloning the repo.
#
# Usage:
#   ./setup_rclone.sh install     — install rclone
#   ./setup_rclone.sh config      — configure cloud provider (opens browser on Mac)
#   ./setup_rclone.sh sync        — manual one-off sync now
#   ./setup_rclone.sh cron        — install auto-sync cron (every 5 minutes)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INBOX_DIR="$SCRIPT_DIR/03_Canva_Exports"
RCLONE_REMOTE="${RCLONE_REMOTE:-etsy-pipeline}"   # name you give rclone remote
RCLONE_PATH="${RCLONE_PATH:-etsy-pipeline}"        # folder name in Dropbox/Drive

CMD="${1:-}"

_install() {
    echo "[rclone] Installing rclone..."
    curl -fsSL https://rclone.org/install.sh | bash
    echo "[rclone] Installed: $(rclone version | head -1)"
}

_config() {
    echo ""
    echo "════════════════════════════════════════════"
    echo "  rclone remote setup"
    echo "════════════════════════════════════════════"
    echo ""
    echo "  This opens an interactive setup. When asked for a name,"
    echo "  type: etsy-pipeline"
    echo ""
    echo "  Choose your provider:"
    echo "    - Dropbox → type: dropbox"
    echo "    - Google Drive → type: drive"
    echo ""
    echo "  For the OAuth step on a headless VPS:"
    echo "    1. On your Mac run: rclone authorize dropbox (or drive)"
    echo "    2. Log in in the browser that opens"
    echo "    3. Copy the token and paste it here"
    echo ""
    rclone config
}

_sync() {
    mkdir -p "$INBOX_DIR"
    echo "[rclone] Syncing ${RCLONE_REMOTE}:${RCLONE_PATH} → ${INBOX_DIR}"
    rclone sync "${RCLONE_REMOTE}:${RCLONE_PATH}" "$INBOX_DIR" \
        --transfers=4 \
        --checkers=8 \
        --contimeout=60s \
        --timeout=300s \
        --retries=3 \
        --log-level=INFO
    echo "[rclone] Sync complete."
}

_install_cron() {
    CRON_CMD="*/5 * * * * rclone sync ${RCLONE_REMOTE}:${RCLONE_PATH} ${INBOX_DIR} --log-file=${SCRIPT_DIR}/logs/rclone.log 2>&1"
    ( crontab -l 2>/dev/null | grep -v "rclone sync"; echo "$CRON_CMD" ) | crontab -
    echo "[rclone] Cron installed — syncing every 5 minutes."
    echo "         Logs: logs/rclone.log"
}

case "$CMD" in
    install) _install ;;
    config)  _config  ;;
    sync)    _sync    ;;
    cron)    _install_cron ;;
    *)
        echo "Usage: $0 {install|config|sync|cron}"
        echo ""
        echo "  Quick start on VPS:"
        echo "    ./setup_rclone.sh install"
        echo "    ./setup_rclone.sh config"
        echo "    ./setup_rclone.sh cron"
        exit 1
        ;;
esac
