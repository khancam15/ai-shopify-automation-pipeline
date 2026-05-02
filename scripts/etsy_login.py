"""
etsy_login.py — One-time Etsy session setup
─────────────────────────────────────────────
Opens a headed (visible) Chromium browser so you can log into Etsy manually.
The session is saved to .playwright_profile/ — all future headless runs
in etsy_uploader.py reuse this saved session without re-logging in.

Run this ONCE on your VPS (requires a GUI or X forwarding), or on your
local Mac before copying .playwright_profile/ to the VPS.

Usage:
    python scripts/etsy_login.py

After logging in:
    Press ENTER in this terminal to save the session and close the browser.

Copying session to VPS (if logged in on Mac):
    scp -r .playwright_profile/ root@YOUR_VPS_IP:/root/ai-etsy-product-pipeline/
"""

from __future__ import annotations

from pathlib import Path

_ROOT       = Path(__file__).resolve().parent.parent
PROFILE_DIR = _ROOT / ".playwright_profile"
ETSY_URL    = "https://www.etsy.com/signin"


def run_login() -> None:
    from playwright.sync_api import sync_playwright

    PROFILE_DIR.mkdir(exist_ok=True)

    print(f"\n  [etsy_login] Launching Chromium (headed)...")
    print(f"  [etsy_login] Profile will be saved to: {PROFILE_DIR}")
    print(f"  [etsy_login] Log into Etsy in the browser window that opens.")
    print(f"  [etsy_login] Then come back here and press ENTER to save and close.\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,         # headed — you must be able to see the browser
            args=["--no-sandbox"],
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(ETSY_URL, wait_until="domcontentloaded", timeout=30_000)

        input("  Press ENTER after logging in to save session and close browser...")

        browser.close()

    print(f"\n  [etsy_login] Session saved to: {PROFILE_DIR}")
    print(f"  [etsy_login] All future headless runs will use this session.")
    print()
    print(f"  To copy this session to your VPS run:")
    print(f"    scp -r .playwright_profile/ root@YOUR_VPS_IP:/root/ai-etsy-product-pipeline/")


if __name__ == "__main__":
    run_login()
