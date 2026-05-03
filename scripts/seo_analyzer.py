"""
seo_analyzer.py — Phase 6
──────────────────────────
Post-publish SEO analysis + auto-apply.

Two stages per run:
  ANALYZE  — fetch this listing's current tags, search top-10 competitor
             listings for the primary keyword, count tag frequency, identify
             gaps, and write the report to the seo_review table.

  APPLY    — build an optimised 13-tag set (keep high-value existing tags,
             fill gaps with the highest-frequency competitor tags), PUT it
             to the live Etsy listing via the API, and log the change.

The apply stage runs automatically after analysis unless --analyze-only
is passed. This means every cycle the listing's tags improve toward the
best observed set in its niche.

Run:
    python scripts/seo_analyzer.py <product_name>
    python scripts/seo_analyzer.py <product_name> --analyze-only

Requires in .env:
    ETSY_API_KEY
    ETSY_ACCESS_TOKEN   (needs listings_w scope for the PUT)
    ETSY_SHOP_ID
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import requests
from dotenv import dotenv_values, load_dotenv
from api_retry import rget, rpost, rput

from db import insert_seo_review, get_conn, log_run

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
ENV_PATH = _ROOT / ".env"

ETSY_API_BASE = "https://openapi.etsy.com/v3/application"
TOKEN_URL     = "https://api.etsy.com/v3/public/oauth/token"

MAX_TAGS      = 13
TAG_MAX_LEN   = 20
# Keep at least this many of the original tags to preserve any organic traction
MIN_KEEP_ORIGINAL = 6


# ── Credentials ───────────────────────────────────────────────────────────────

def _load_creds() -> dict[str, str]:
    return dict(dotenv_values(ENV_PATH))


def _save_creds(updates: dict[str, str]) -> None:
    env = _load_creds()
    env.update(updates)
    ENV_PATH.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")


def _refresh_token(creds: dict) -> dict:
    """Refresh Etsy access token if needed. Returns updated creds dict."""
    resp = rpost(
        TOKEN_URL,
        data={
            "grant_type":    "refresh_token",
            "client_id":     creds["ETSY_API_KEY"],
            "refresh_token": creds["ETSY_REFRESH_TOKEN"],
        },
        timeout=30,
        _label="Etsy token refresh",
    )
    if not resp.ok:
        raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    creds["ETSY_ACCESS_TOKEN"]  = data["access_token"]
    creds["ETSY_REFRESH_TOKEN"] = data.get("refresh_token", creds["ETSY_REFRESH_TOKEN"])
    _save_creds({
        "ETSY_ACCESS_TOKEN":  creds["ETSY_ACCESS_TOKEN"],
        "ETSY_REFRESH_TOKEN": creds["ETSY_REFRESH_TOKEN"],
    })
    return creds


def _headers(creds: dict) -> dict[str, str]:
    return {
        "x-api-key":     creds["ETSY_API_KEY"],
        "Authorization": f"Bearer {creds['ETSY_ACCESS_TOKEN']}",
    }


# ── Listing lookup ─────────────────────────────────────────────────────────────

def _get_listing_id(product_name: str) -> str | None:
    """Extract listing ID from the etsy_url stored in the listings table."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT etsy_url FROM listings WHERE product_name = ? "
            "ORDER BY published_at DESC LIMIT 1",
            (product_name,),
        ).fetchone()
    if not row or not row["etsy_url"]:
        return None
    parts = row["etsy_url"].rstrip("/").split("/")
    for i, part in enumerate(parts):
        if part == "listing" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def _get_listing_data(creds: dict, listing_id: str) -> tuple[str, list[str]]:
    """Return (title, current_tags) for a published Etsy listing."""
    resp = rget(
        f"{ETSY_API_BASE}/listings/{listing_id}",
        headers=_headers(creds),
        timeout=15,
        _label="Etsy get listing",
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("title", ""), data.get("tags", [])


# ── Competitor research ───────────────────────────────────────────────────────

def _get_competitor_tag_counts(creds: dict, keyword: str, limit: int = 10) -> Counter:
    """
    Search Etsy for the top `limit` active listings matching the keyword.
    Count how many listings each tag appears in.

    Returns Counter({tag: frequency}) — higher frequency = more competitors use it.
    """
    resp = rget(
        f"{ETSY_API_BASE}/listings/active",
        headers=_headers(creds),
        params={"keywords": keyword, "limit": limit, "fields": "tags,title,listing_id"},
        timeout=15,
        _label="Etsy competitor search",
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    counts: Counter = Counter()
    for listing in results:
        for tag in listing.get("tags", []):
            counts[tag.lower()] += 1

    return counts


# ── Tag optimisation ──────────────────────────────────────────────────────────

def _primary_keyword(title: str) -> str:
    """
    Extract the most search-relevant phrase from a listing title.
    Uses the text before the first pipe (|) or em-dash (—), trimmed.
    Falls back to the first 4 words.
    """
    for sep in ["|", "—", "-"]:
        if sep in title:
            phrase = title.split(sep)[0].strip()
            if len(phrase) > 5:
                return phrase
    words = title.split()
    return " ".join(words[:4]) if len(words) >= 4 else title


def _build_optimised_tags(
    current_tags: list[str],
    competitor_counts: Counter,
) -> tuple[list[str], list[str], list[str]]:
    """
    Build the best possible 13-tag set by combining current tags with
    high-frequency competitor tags.

    Strategy:
      1. Score current tags: those that also appear in competitor data get
         a higher score → kept preferentially.
      2. Rank missing competitor tags by frequency (how many top listings use them).
      3. Fill 13 slots: start with highest-scoring current tags, pad with
         highest-frequency missing tags.
      4. All tags must be ≤ 20 chars (Etsy hard limit).

    Returns:
      (optimised_tags, added_tags, removed_tags)
    """
    current_lower = [t.lower() for t in current_tags]
    current_set   = set(current_lower)
    comp_set      = set(competitor_counts.keys())

    # Score existing tags: competitor overlap = 2 pts, just existing = 1 pt
    scored_existing = sorted(
        current_lower,
        key=lambda t: (competitor_counts.get(t, 0) * 2 + 1),
        reverse=True,
    )

    # Missing competitor tags ranked by frequency, within char limit
    missing_ranked = [
        tag for tag, _ in competitor_counts.most_common()
        if tag not in current_set and len(tag) <= TAG_MAX_LEN
    ]

    # Keep at least MIN_KEEP_ORIGINAL from the current set
    kept = scored_existing[:MIN_KEEP_ORIGINAL]
    remaining_slots = MAX_TAGS - len(kept)

    # Fill from current (lower priority) then missing
    extra_current = [t for t in scored_existing[MIN_KEEP_ORIGINAL:] if len(kept) + len([t]) <= MAX_TAGS]
    fill_from_current = extra_current[:max(0, remaining_slots - len(missing_ranked[:remaining_slots]))]
    fill_from_missing = missing_ranked[:remaining_slots - len(fill_from_current)]

    optimised = (kept + fill_from_current + fill_from_missing)[:MAX_TAGS]

    added   = [t for t in optimised if t not in current_set]
    removed = [t for t in current_lower if t not in set(optimised)]

    return optimised, added, removed


# ── Etsy listing update ────────────────────────────────────────────────────────

def _update_listing_tags(
    creds: dict,
    listing_id: str,
    tags: list[str],
) -> bool:
    """
    PUT the optimised tag list to the live Etsy listing.
    Returns True on success.
    """
    url  = f"{ETSY_API_BASE}/shops/{creds['ETSY_SHOP_ID']}/listings/{listing_id}"
    hdrs = {**_headers(creds), "Content-Type": "application/json"}

    resp = rput(url, headers=hdrs, json={"tags": tags}, timeout=30, _label="Etsy update tags")

    if resp.status_code == 401:
        creds = _refresh_token(creds)
        hdrs  = {**_headers(creds), "Content-Type": "application/json"}
        resp  = rput(url, headers=hdrs, json={"tags": tags}, timeout=30, _label="Etsy update tags retry")

    if not resp.ok:
        print(f"  [6] Tag update failed ({resp.status_code}): {resp.text[:200]}")
        return False

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def analyze(product_name: str, apply: bool = True) -> int:
    """
    Full Phase 6:
      1. Load listing ID and current tags from Etsy API
      2. Search top-10 competitors for the primary keyword
      3. Count tag frequency across competitors
      4. Identify gaps and build optimised 13-tag set
      5. Write gap report to seo_review table
      6. PUT optimised tags to the live listing (unless apply=False)

    Returns gap count (number of tags added/improved).
    """
    creds = _load_creds()

    for key in ("ETSY_API_KEY", "ETSY_ACCESS_TOKEN", "ETSY_SHOP_ID"):
        if not creds.get(key):
            raise RuntimeError(f"{key} not set in .env — run: python scripts/etsy_oauth.py")

    # 6.1 — Get listing ID
    listing_id = _get_listing_id(product_name)
    if not listing_id:
        raise ValueError(
            f"No published listing found for '{product_name}'. "
            f"Run Phase 5 first, or check the listings table."
        )
    print(f"  [6.1] Listing ID: {listing_id}")

    # 6.2 — Fetch current tags
    try:
        title, current_tags = _get_listing_data(creds, listing_id)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 401:
            creds = _refresh_token(creds)
            title, current_tags = _get_listing_data(creds, listing_id)
        else:
            raise
    keyword = _primary_keyword(title)
    print(f"  [6.2] Current tags ({len(current_tags)}): {current_tags}")
    print(f"  [6.2] Primary keyword: {keyword!r}")

    # 6.3 — Competitor research
    print(f"  [6.3] Searching top-10 competitors for: {keyword!r}")
    competitor_counts = _get_competitor_tag_counts(creds, keyword, limit=10)
    top_competitor_tags = [t for t, _ in competitor_counts.most_common(20)]
    print(f"  [6.3] Top competitor tags: {top_competitor_tags[:10]}")

    # 6.4 — Build optimised tag set
    optimised, added, removed = _build_optimised_tags(current_tags, competitor_counts)
    missing = [t for t in top_competitor_tags if t not in {x.lower() for x in current_tags}]

    print(f"  [6.4] Optimised tags ({len(optimised)}): {optimised}")
    if added:
        print(f"  [6.4] Adding  ({len(added)}): {added}")
    if removed:
        print(f"  [6.4] Removing({len(removed)}): {removed}")

    # 6.5 — Write gap report to SQLite
    insert_seo_review(
        product_name=product_name,
        listing_title=title,
        missing_tags=missing[:13],
        competitor_tags=top_competitor_tags[:20],
    )

    gap_count = len(added)

    # 6.6 — Apply optimised tags to live listing
    if apply and added:
        print(f"  [6.6] Applying {gap_count} tag improvement(s) to listing {listing_id}...")
        success = _update_listing_tags(creds, listing_id, optimised)
        if success:
            print(f"  [6.6] ✓ Listing tags updated on Etsy")
            log_run(
                product_name,
                "seo_analyzer",
                "success",
                f"Tags updated — added: {added}, removed: {removed}, gap_count: {gap_count}",
            )
        else:
            print(f"  [6.6] Tag update failed — listing is unchanged")
            log_run(
                product_name,
                "seo_analyzer",
                "failed",
                f"Tag update API call failed for listing {listing_id}",
            )
    elif not added:
        print(f"  [6.6] Tags already optimal — no update needed")
        log_run(product_name, "seo_analyzer", "success", "Tags already optimal, no update needed")
    else:
        print(f"  [6.6] Analyze-only mode — {gap_count} improvement(s) identified but not applied")
        log_run(
            product_name,
            "seo_analyzer",
            "success",
            f"Analyze-only: {gap_count} gaps identified — {missing[:5]}",
        )

    print(f"  [6] SEO gap count: {gap_count}")
    return gap_count


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print("Usage: python scripts/seo_analyzer.py <product_name> [--analyze-only]")
        sys.exit(1)

    product_name = args[0]
    apply_tags   = "--analyze-only" not in args

    try:
        gap_count = analyze(product_name, apply=apply_tags)
        sys.exit(0)
    except (ValueError, RuntimeError) as e:
        print(f"[error] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[error] Unexpected: {e}")
        sys.exit(1)
