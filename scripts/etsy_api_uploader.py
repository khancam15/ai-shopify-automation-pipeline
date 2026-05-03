"""
etsy_api_uploader.py  —  Phase 5 (API-based, replaces Playwright)
────────────────────────────────────────────────────────────────────
Creates a live Etsy listing via the Open API v3 REST endpoints,
uploads mockup images, and attaches the digital download file.

Run:
    python scripts/etsy_api_uploader.py <product_name>

Prerequisites (one-time, 💻 HOST):
    python scripts/etsy_oauth.py

Credentials read from .env:
    ETSY_API_KEY, ETSY_ACCESS_TOKEN, ETSY_REFRESH_TOKEN, ETSY_SHOP_ID

Execution flow:
  5.1  Load listing.json from 04_Assets/ReadyToUpload/[ProductName]/
  5.2  Refresh access token if needed
  5.3  POST /v3/application/shops/{shop_id}/listings → get listing_id
  5.4  POST mockup JPEGs to listings/{listing_id}/images (up to 10)
  5.4.5 POST PDF to listings/{listing_id}/files (digital download)
  5.5  Log success to SQLite run_log + insert into listings table
  5.6  Update queue row to "published"
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values, load_dotenv
from api_retry import retry_request, rget, rpost, rput

from db import insert_listing, log_run, update_queue_status

_ROOT       = Path(__file__).resolve().parent.parent
ENV_PATH    = _ROOT / ".env"

load_dotenv(ENV_PATH)

ASSETS_DIR  = _ROOT / "04_Assets" / "ReadyToUpload"
API_BASE    = "https://openapi.etsy.com/v3/application"
TOKEN_URL   = "https://api.etsy.com/v3/public/oauth/token"

# Etsy taxonomy ID for "Digital Prints" (general digital download category).
# Full list: https://developer.etsy.com/documentation/reference/#operation/getTaxonomyNodes
DEFAULT_TAXONOMY_ID = 2078  # Art & Collectibles > Prints > Digital Prints


def _load_env() -> dict[str, str]:
    return dict(dotenv_values(ENV_PATH))


def _save_env(updates: dict[str, str]) -> None:
    env = _load_env()
    env.update(updates)
    ENV_PATH.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")


def _refresh_token(api_key: str, refresh_token: str) -> tuple[str, str]:
    """Exchange refresh token for a new access token. Returns (access, refresh)."""
    resp = rpost(
        TOKEN_URL,
        data={
            "grant_type":    "refresh_token",
            "client_id":     api_key,
            "refresh_token": refresh_token,
        },
        timeout=30,
        _label="Etsy token refresh",
    )
    if not resp.ok:
        raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    new_access  = data["access_token"]
    new_refresh = data.get("refresh_token", refresh_token)
    _save_env({"ETSY_ACCESS_TOKEN": new_access, "ETSY_REFRESH_TOKEN": new_refresh})
    print("  [5.2] Access token refreshed and saved.")
    return new_access, new_refresh


def _headers(api_key: str, access_token: str) -> dict[str, str]:
    return {
        "x-api-key":     api_key,
        "Authorization": f"Bearer {access_token}",
    }


def _create_listing(
    api_key: str,
    access_token: str,
    shop_id: str,
    payload: dict,
) -> int:
    """POST the listing to Etsy. Returns the new listing_id."""
    tags = payload.get("tags", [])[:13]  # Etsy max 13 tags

    body = {
        "quantity":         999,
        "title":            payload["title"][:140],
        "description":      payload["description"],
        "price":            float(payload["price"]),
        "who_made":         "i_did",
        "when_made":        "made_to_order",
        "taxonomy_id":      DEFAULT_TAXONOMY_ID,
        "tags":             tags,
        "is_digital":       True,
        "type":             "download",
        "is_customizable":  False,
        "is_personalizable": False,
    }

    resp = rpost(
        f"{API_BASE}/shops/{shop_id}/listings",
        headers={**_headers(api_key, access_token), "Content-Type": "application/json"},
        json=body,
        timeout=30,
        _label="Etsy create listing",
    )
    if not resp.ok:
        raise RuntimeError(f"Create listing failed ({resp.status_code}): {resp.text}")

    listing_id = resp.json()["listing_id"]
    print(f"  [5.3] Listing created: {listing_id}")
    return listing_id


def _upload_images(
    api_key: str,
    access_token: str,
    shop_id: str,
    listing_id: int,
    image_paths: list[Path],
) -> None:
    """Upload each JPEG mockup. Etsy allows up to 10 images."""
    url  = f"{API_BASE}/shops/{shop_id}/listings/{listing_id}/images"
    hdrs = _headers(api_key, access_token)

    for rank, img_path in enumerate(image_paths[:10], start=1):
        with open(img_path, "rb") as fh:
            resp = retry_request(
                "POST",
                url,
                headers=hdrs,
                files={"image": (img_path.name, fh, "image/jpeg")},
                data={"rank": rank, "overwrite": "true"},
                timeout=60,
                _label=f"Etsy image upload {rank}",
            )
        if resp.ok:
            print(f"  [5.4] Uploaded image {rank}/{len(image_paths)}: {img_path.name}")
        else:
            print(f"  [5.4] Warning — image upload failed for {img_path.name}: {resp.text}")
        time.sleep(0.5)  # stay under Etsy rate limits


def _upload_digital_file(
    api_key: str,
    access_token: str,
    shop_id: str,
    listing_id: int,
    file_path: str,
) -> None:
    """
    Upload the product PDF as the Etsy digital download file.
    Buyers download this file after purchase.

    Non-fatal — if upload fails, the listing is still live (just without
    the attached file; seller can upload manually).
    """
    pdf = Path(file_path)
    if not pdf.exists():
        print(f"  [5.4.5] Digital file not found: {pdf} — skipping")
        return

    url  = f"{API_BASE}/shops/{shop_id}/listings/{listing_id}/files"
    hdrs = _headers(api_key, access_token)

    try:
        with open(pdf, "rb") as fh:
            resp = retry_request(
                "POST",
                url,
                headers=hdrs,
                files={"file": (pdf.name, fh, "application/pdf")},
                data={"name": pdf.name, "rank": 1},
                timeout=120,
                _label="Etsy digital file upload",
            )
        if resp.ok:
            size_kb = pdf.stat().st_size // 1024
            print(f"  [5.4.5] Digital file uploaded: {pdf.name} ({size_kb} KB)")
        else:
            print(f"  [5.4.5] Warning — digital file upload failed ({resp.status_code}): {resp.text[:200]}")
    except Exception as exc:
        print(f"  [5.4.5] Warning — digital file upload error: {exc}")


def upload_listing(product_name: str) -> str | None:
    """
    Full Phase 5 upload via Etsy API.
    Returns the listing URL on success, None on failure.
    """
    env = _load_env()

    api_key       = env.get("ETSY_API_KEY", "")
    access_token  = env.get("ETSY_ACCESS_TOKEN", "")
    refresh_token = env.get("ETSY_REFRESH_TOKEN", "")
    shop_id       = env.get("ETSY_SHOP_ID", "")

    if not api_key or not shop_id:
        raise RuntimeError(
            "ETSY_API_KEY and ETSY_SHOP_ID are required. "
            "Run: python scripts/etsy_oauth.py"
        )

    # Load listing payload
    payload_file = ASSETS_DIR / product_name / "listing.json"
    if not payload_file.exists():
        raise FileNotFoundError(f"listing.json not found — run listing_builder.py first")

    payload = json.loads(payload_file.read_text(encoding="utf-8"))

    # Collect mockup images
    image_paths = sorted((ASSETS_DIR / product_name).glob("*.jpg"))
    if not image_paths:
        raise FileNotFoundError(f"No JPEG mockups found in {ASSETS_DIR / product_name}")

    # Refresh token if we have a refresh token (proactive, avoids mid-upload expiry)
    if refresh_token:
        try:
            access_token, refresh_token = _refresh_token(api_key, refresh_token)
        except RuntimeError as e:
            print(f"  [5.2] Token refresh warning: {e} — trying existing token.")

    # Create the listing
    try:
        listing_id = _create_listing(api_key, access_token, shop_id, payload)
    except RuntimeError as e:
        raise RuntimeError(f"Phase 5 listing creation failed: {e}") from e

    # Upload mockup images
    _upload_images(api_key, access_token, shop_id, listing_id, image_paths)

    # Upload digital download file (PDF template — non-fatal if missing)
    digital_file = payload.get("digital_file", "")
    if digital_file:
        _upload_digital_file(api_key, access_token, shop_id, listing_id, digital_file)
    else:
        print(f"  [5.4.5] No digital file in payload — upload manually if needed")

    listing_url = f"https://www.etsy.com/listing/{listing_id}"
    print(f"  [5.5] Listing live: {listing_url}")

    log_run(product_name, "etsy_api_uploader", "success", "Listing published via API", etsy_url=listing_url)
    insert_listing(product_name, payload["title"], listing_url)
    update_queue_status(payload["queue_id"], "published")

    # Archive staged files so 04_Assets/ReadyToUpload doesn't grow indefinitely
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from file_organizer import archive
        archive(product_name)
    except Exception as exc:
        print(f"  [5.6] Archive warning (non-fatal): {exc}")

    return listing_url


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/etsy_api_uploader.py <product_name>")
        sys.exit(1)

    try:
        result = upload_listing(sys.argv[1])
        sys.exit(0 if result else 1)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"[error] {e}")
        sys.exit(1)
