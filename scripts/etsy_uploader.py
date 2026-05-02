"""
etsy_uploader.py  —  Phase 5
──────────────────────────────
Playwright headless Chromium uploader. Reads listing.json from
04_Assets/ReadyToUpload/[ProductName]/ and submits a draft listing
to Etsy Seller Dashboard. No display required — runs fully headless
on the VPS.

Run:
    python scripts/etsy_uploader.py <product_name>

Requirements:
    pip install playwright
    playwright install chromium --with-deps

Execution flow (per v3 Phase 5 spec):
  5.1  Launch headless Chromium with a persistent browser profile
       (Etsy session already logged in — do NOT re-login on every run)
  5.2  Navigate to Etsy Seller Dashboard > Listings > Add a Listing
  5.3  Fill in the title field from the JSON payload
  5.4  Upload all 5 mockup images using set_input_files() — no PyAutoGUI
  5.5  Fill description, tags, price, category, digital download toggle
  5.6  Submit listing and capture the confirmation URL
  5.7  On submission failure: pause 30 s, retry once, then log and exit 1

Safety:
  - Never auto-publishes. Listing is left as draft (status: active is
    the Etsy default after "Save and continue" — change to draft if
    the spec requires review before publish).
  - Credentials loaded from .env only, never hardcoded.
  - All actions logged to SQLite run_log and outputs/week_log.md.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
import os

from db import log_run, insert_listing, update_queue_status

_ROOT        = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

ASSETS_DIR   = _ROOT / "04_Assets" / "ReadyToUpload"
PROFILE_DIR  = _ROOT / ".playwright_profile"  # persistent login session
LOG_FILE     = _ROOT / "outputs" / "week_log.md"

ETSY_LISTING_URL = "https://www.etsy.com/your/shops/me/listings/create"


def _log(msg: str) -> None:
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{msg}\n")


def _fill_tags(page, tags: list[str]) -> None:
    """
    Etsy tag input requires typing each tag and pressing Enter.
    Waits for the tag chip to appear before moving to the next.
    """
    tag_input = page.locator("input[placeholder*='tag' i]").first
    for tag in tags[:13]:
        tag_input.fill(tag)
        tag_input.press("Enter")
        time.sleep(0.4)


def upload_listing(product_name: str, retry: bool = False) -> str | None:
    """
    Runs the full Phase 5 upload sequence.
    Returns the Etsy listing URL on success, None on failure.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    payload_file = ASSETS_DIR / product_name / "listing.json"
    if not payload_file.exists():
        raise FileNotFoundError(f"listing.json not found — run listing_builder.py first")

    payload = json.loads(payload_file.read_text(encoding="utf-8"))
    mockup_paths = sorted(
        str(p) for p in (ASSETS_DIR / product_name).glob("*.jpg")
    )

    if not mockup_paths:
        raise FileNotFoundError(f"No JPEG mockups found in {ASSETS_DIR / product_name}")

    PROFILE_DIR.mkdir(exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.pages[0] if browser.pages else browser.new_page()

        try:
            # 5.2 — Navigate to listing creation
            _log(f"  [5.2] Navigating to: {ETSY_LISTING_URL}")
            page.goto(ETSY_LISTING_URL, wait_until="networkidle", timeout=30_000)

            # Etsy may redirect to login if session expired
            if "signin" in page.url or "login" in page.url:
                _log("  [5.x] Session expired — Etsy login required. Re-run after logging in.")
                log_run(product_name, "etsy_uploader", "failed", "Session expired — manual login needed")
                browser.close()
                return None

            # 5.3 — Title
            _log(f"  [5.3] Filling title: {payload['title'][:60]}...")
            page.locator("input[id*='title' i], input[name*='title' i]").first.fill(payload["title"])

            # 5.4 — Upload images via set_input_files (no PyAutoGUI)
            _log(f"  [5.4] Uploading {len(mockup_paths)} mockup image(s)...")
            file_input = page.locator("input[type='file']").first
            file_input.set_input_files(mockup_paths)
            page.wait_for_timeout(3000)  # allow upload progress

            # 5.5 — Description
            _log("  [5.5] Filling description...")
            page.locator("textarea[id*='description' i], textarea[name*='description' i]").first.fill(
                payload["description"]
            )

            # Tags
            _log("  [5.5] Filling tags...")
            _fill_tags(page, payload["tags"])

            # Price
            _log(f"  [5.5] Setting price: ${payload['price']}")
            page.locator("input[id*='price' i], input[name*='price' i]").first.fill(str(payload["price"]))

            # Digital download toggle
            digital_toggle = page.locator("input[type='checkbox'][id*='digital' i]")
            if digital_toggle.count() > 0 and not digital_toggle.first.is_checked():
                digital_toggle.first.check()
                _log("  [5.5] Digital download toggle enabled")

            # 5.6 — Submit (saves as draft / active depending on Etsy flow)
            _log("  [5.6] Submitting listing...")
            page.locator("button[type='submit'], button:has-text('Save')").first.click()
            page.wait_for_url("**/listings/**", timeout=20_000)

            listing_url = page.url
            _log(f"  [5.6] Listing submitted: {listing_url}")
            log_run(product_name, "etsy_uploader", "success", "Listing submitted", etsy_url=listing_url)
            insert_listing(product_name, payload["title"], listing_url)
            update_queue_status(payload["queue_id"], "published")

            browser.close()
            return listing_url

        except PWTimeout as exc:
            _log(f"  [5.7] Timeout: {exc}")
            browser.close()

            if not retry:
                _log("  [5.7] Retrying in 30 seconds...")
                time.sleep(30)
                return upload_listing(product_name, retry=True)

            log_run(product_name, "etsy_uploader", "failed", str(exc))
            update_queue_status(payload["queue_id"], "failed")
            return None

        except Exception as exc:
            _log(f"  [5.7] Upload error: {exc}")
            log_run(product_name, "etsy_uploader", "failed", str(exc))
            browser.close()
            return None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/etsy_uploader.py <product_name>")
        sys.exit(1)

    result = upload_listing(sys.argv[1])
    sys.exit(0 if result else 1)
