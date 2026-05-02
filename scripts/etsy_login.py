"""
etsy_login.py — One-time Etsy session setup (run on Mac only)
──────────────────────────────────────────────────────────────
Opens a headed Chrome browser so you can log into Etsy manually.
The session is saved to .playwright_profile/ — etsy_uploader.py on the VPS
reuses this saved session headlessly without ever re-logging in.

This is the ONLY script that runs on your Mac. Everything else runs on the VPS.

Usage (💻 HOST — Mac terminal, not SSH):
    python scripts/etsy_login.py

After logging in:
    Press ENTER in this terminal to save the session and close the browser.

Copy the saved session to VPS (run on Mac):
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
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation", "--no-sandbox"],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        # Remove navigator.webdriver flag that Etsy's bot detection checks
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

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
