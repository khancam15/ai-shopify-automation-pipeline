"""
seo_analyzer.py  —  Phase 6
──────────────────────────────
Post-publish SEO analysis. Calls the Etsy API to retrieve the listing's
published tags, fetches the top 5 competitor listings for the primary
keyword, compares tags, and writes the gap report to the seo_review
SQLite table.

Run:
    python scripts/seo_analyzer.py <product_name>

Requires:
    ETSY_API_KEY in .env

Execution flow (per v3 Phase 6 spec):
  6.1  Call Etsy API to retrieve the published listing's tags and title
  6.2  Fetch top 5 search results for the listing's primary keyword
  6.3  Compare listing tags against competitor tags — identify gaps
  6.4  Write gap report to seo_review table (product, missing tags, timestamp)
  6.5  Print gap count for n8n notification node to include in alert
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

import requests

from db import insert_seo_review, get_conn, log_run

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

ETSY_API_KEY   = os.getenv("ETSY_API_KEY", "")
ETSY_API_BASE  = "https://openapi.etsy.com/v3/application"
ASSETS_DIR     = _ROOT / "04_Assets" / "ReadyToUpload"


def _etsy_headers() -> dict[str, str]:
    return {"x-api-key": ETSY_API_KEY}


def _get_listing_id(product_name: str) -> str | None:
    """Look up the Etsy listing URL from the listings table and extract the ID."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT etsy_url FROM listings WHERE product_name = ? ORDER BY published_at DESC LIMIT 1",
            (product_name,),
        ).fetchone()
    if not row or not row["etsy_url"]:
        return None
    # URL format: https://www.etsy.com/listing/123456789/...
    parts = row["etsy_url"].rstrip("/").split("/")
    for i, part in enumerate(parts):
        if part == "listing" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _get_published_tags(listing_id: str) -> tuple[str, list[str]]:
    """Return (title, tags) for a published Etsy listing via the API."""
    url = f"{ETSY_API_BASE}/listings/{listing_id}"
    resp = requests.get(url, headers=_etsy_headers(), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("title", ""), data.get("tags", [])


def _get_competitor_tags(keyword: str) -> list[str]:
    """
    Fetch the top 5 search results for a keyword and collect all their tags.
    Returns a deduplicated list of competitor tags.
    """
    url = f"{ETSY_API_BASE}/listings/active"
    params = {"keywords": keyword, "limit": 5, "fields": "tags,title"}
    resp = requests.get(url, headers=_etsy_headers(), params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    all_tags: set[str] = set()
    for listing in data.get("results", []):
        for tag in listing.get("tags", []):
            all_tags.add(tag.lower())

    return sorted(all_tags)


def analyze(product_name: str) -> int:
    """
    Runs the full Phase 6 SEO gap analysis.
    Returns the number of missing tags (gap count) for n8n notification.
    """
    listing_id = _get_listing_id(product_name)
    if not listing_id:
        raise ValueError(f"No published listing found for: {product_name}")

    # 6.1 — Get this listing's tags
    print(f"  [6.1] Fetching tags for listing ID: {listing_id}")
    title, our_tags = _get_published_tags(listing_id)
    our_tag_set = {t.lower() for t in our_tags}

    # Primary keyword = first non-stop word of title (simple heuristic)
    primary_keyword = title.split("|")[0].strip() if "|" in title else title.split()[0]

    # 6.2 — Competitor tags
    print(f"  [6.2] Searching competitor listings for: {primary_keyword!r}")
    competitor_tags = _get_competitor_tags(primary_keyword)

    # 6.3 — Gap analysis
    missing = [t for t in competitor_tags if t not in our_tag_set]
    print(f"  [6.3] Our tags:         {sorted(our_tag_set)}")
    print(f"  [6.3] Competitor tags:  {competitor_tags}")
    print(f"  [6.3] Missing tags:     {missing}")

    # 6.4 — Write to SQLite
    insert_seo_review(product_name, title, missing, competitor_tags)
    log_run(product_name, "seo_analyzer", "success", f"Gap count: {len(missing)}")

    # 6.5 — Print gap count for n8n
    print(f"  [6.5] SEO gap count: {len(missing)}")
    return len(missing)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/seo_analyzer.py <product_name>")
        sys.exit(1)

    if not ETSY_API_KEY:
        print("[error] ETSY_API_KEY not set in .env")
        sys.exit(1)

    try:
        gap_count = analyze(sys.argv[1])
        sys.exit(0)
    except Exception as e:
        print(f"[error] {e}")
        sys.exit(1)
