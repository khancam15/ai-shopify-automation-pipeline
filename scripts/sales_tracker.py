"""
sales_tracker.py — Daily sales & revenue sync
───────────────────────────────────────────────
Pulls transaction data from the Etsy Open API v3, maps each sale to a
product name via the listings table, and stores everything in the
SQLite `sales` table.

Run:
    python scripts/sales_tracker.py          — sync new transactions only
    python scripts/sales_tracker.py --full   — re-fetch all transactions (slow)

Called by loop.sh once per day alongside the email digest.

Etsy API used:
    GET /v3/application/shops/{shop_id}/transactions
    Fields: transaction_id, listing_id, title, price, quantity,
            seller_fees, create_timestamp

Requires in .env:
    ETSY_API_KEY, ETSY_ACCESS_TOKEN, ETSY_REFRESH_TOKEN, ETSY_SHOP_ID
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values, load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
ENV_PATH = _ROOT / ".env"

sys.path.insert(0, str(Path(__file__).parent))
from db import (
    get_conn,
    get_latest_sale_date,
    get_sales_summary,
    init_db,
    log_run,
    upsert_sale,
)
from api_retry import rget, rpost

ETSY_API_BASE = "https://openapi.etsy.com/v3/application"
TOKEN_URL     = "https://api.etsy.com/v3/public/oauth/token"
PAGE_SIZE     = 100


# ── Credentials ───────────────────────────────────────────────────────────────

def _load_creds() -> dict[str, str]:
    return dict(dotenv_values(ENV_PATH))


def _save_creds(updates: dict[str, str]) -> None:
    env = _load_creds()
    env.update(updates)
    ENV_PATH.write_text("".join(f"{k}={v}\n" for k, v in env.items()), encoding="utf-8")


def _refresh_token(creds: dict) -> dict:
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


def _hdrs(creds: dict) -> dict[str, str]:
    return {
        "x-api-key":     creds["ETSY_API_KEY"],
        "Authorization": f"Bearer {creds['ETSY_ACCESS_TOKEN']}",
    }


# ── Listing ID → product name cache ───────────────────────────────────────────

def _build_listing_map() -> dict[str, str]:
    """
    Build a map of etsy listing_id → product_name from the listings table.
    Extracted from stored etsy_url e.g. https://www.etsy.com/listing/123456/...
    """
    mapping: dict[str, str] = {}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT product_name, etsy_url FROM listings WHERE etsy_url IS NOT NULL"
        ).fetchall()
    for row in rows:
        url = row["etsy_url"] or ""
        parts = url.rstrip("/").split("/")
        for i, part in enumerate(parts):
            if part == "listing" and i + 1 < len(parts):
                mapping[parts[i + 1]] = row["product_name"]
                break
    return mapping


# ── Transaction parsing ───────────────────────────────────────────────────────

def _parse_amount(price_obj: dict | None) -> float:
    """Convert Etsy price object {"amount": 799, "divisor": 100} → 7.99."""
    if not price_obj:
        return 0.0
    try:
        return round(price_obj["amount"] / price_obj["divisor"], 2)
    except (KeyError, ZeroDivisionError, TypeError):
        return 0.0


def _parse_transaction(tx: dict, listing_map: dict[str, str]) -> dict | None:
    """
    Convert a raw Etsy transaction dict into a normalised sale dict.
    Returns None if the transaction is missing essential fields.
    """
    tx_id = str(tx.get("transaction_id", ""))
    if not tx_id:
        return None

    listing_id = str(tx.get("listing_id", ""))
    title      = tx.get("title") or tx.get("listing", {}).get("title", "")
    quantity   = int(tx.get("quantity", 1))

    gross_amount = _parse_amount(tx.get("price"))
    total_gross  = round(gross_amount * quantity, 2)

    # Seller fees (Etsy transaction fee + payment processing)
    seller_fees  = _parse_amount(tx.get("seller_fees"))
    net_amount   = round(total_gross - abs(seller_fees), 2)

    # Timestamp — Etsy returns Unix epoch integers
    ts = tx.get("create_timestamp") or tx.get("created_timestamp") or 0
    try:
        sale_date = datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        sale_date = datetime.utcnow().isoformat()

    product_name = listing_map.get(listing_id, "")

    return {
        "transaction_id": tx_id,
        "listing_id":     listing_id,
        "product_name":   product_name,
        "title":          title[:200],
        "gross_amount":   total_gross,
        "amount":         net_amount,
        "quantity":       quantity,
        "currency":       (tx.get("price") or {}).get("currency_code", "USD"),
        "sale_date":      sale_date,
    }


# ── Fetch transactions ────────────────────────────────────────────────────────

def _fetch_transactions(
    creds: dict,
    min_created: int | None = None,
    offset: int = 0,
) -> list[dict]:
    """
    Fetch one page of transactions from the Etsy API.
    min_created: Unix timestamp — only fetch sales after this time.
    """
    params: dict = {"limit": PAGE_SIZE, "offset": offset}
    if min_created:
        params["min_created"] = min_created

    resp = rget(
        f"{ETSY_API_BASE}/shops/{creds['ETSY_SHOP_ID']}/transactions",
        headers=_hdrs(creds),
        params=params,
        timeout=30,
        _label="Etsy transactions",
    )

    if resp.status_code == 401:
        creds = _refresh_token(creds)
        resp = rget(
            f"{ETSY_API_BASE}/shops/{creds['ETSY_SHOP_ID']}/transactions",
            headers=_hdrs(creds),
            params=params,
            timeout=30,
            _label="Etsy transactions (retry after refresh)",
        )

    resp.raise_for_status()
    return resp.json().get("results", [])


# ── Main sync ─────────────────────────────────────────────────────────────────

def sync_sales(full: bool = False) -> dict:
    """
    Sync Etsy transactions to the local sales table.

    Args:
        full: If True, re-fetch all transactions (ignores last sync date).

    Returns:
        Summary dict with new_sales, total_revenue_7d, etc.
    """
    init_db()  # ensure sales table exists

    creds = _load_creds()
    for key in ("ETSY_API_KEY", "ETSY_ACCESS_TOKEN", "ETSY_SHOP_ID"):
        if not creds.get(key):
            raise RuntimeError(f"{key} not set in .env — run: python scripts/etsy_oauth.py")

    listing_map = _build_listing_map()
    print(f"  [sales] Listing map: {len(listing_map)} products")

    # Determine how far back to fetch
    min_created: int | None = None
    if not full:
        last_date = get_latest_sale_date()
        if last_date:
            try:
                dt = datetime.fromisoformat(last_date.replace("Z", "+00:00"))
                min_created = int(dt.timestamp())
                print(f"  [sales] Incremental sync from: {last_date[:10]}")
            except (ValueError, AttributeError):
                pass
    if full or min_created is None:
        print(f"  [sales] Full sync — fetching all transactions")

    new_count = 0
    offset    = 0

    while True:
        txs = _fetch_transactions(creds, min_created=min_created, offset=offset)
        if not txs:
            break

        for tx in txs:
            sale = _parse_transaction(tx, listing_map)
            if not sale:
                continue
            inserted = upsert_sale(**sale)
            if inserted:
                new_count += 1

        if len(txs) < PAGE_SIZE:
            break  # last page
        offset += PAGE_SIZE

    summary = get_sales_summary(days=7)
    summary["new_transactions"] = new_count

    print(f"  [sales] ✓ Synced {new_count} new transaction(s)")
    print(f"  [sales] Last 7 days: {summary['order_count']} orders | "
          f"${summary['total_revenue']:.2f} net | "
          f"${summary['gross_revenue']:.2f} gross")
    if summary["best_product"]:
        print(f"  [sales] Best product: {summary['best_product']} "
              f"(${summary['best_product_revenue']:.2f})")
    print(f"  [sales] All-time revenue: ${summary['all_time_revenue']:.2f}")

    log_run(
        "pipeline",
        "sales_tracker",
        "success",
        f"new={new_count}, 7d_revenue=${summary['total_revenue']:.2f}, "
        f"7d_orders={summary['order_count']}",
    )
    return summary


if __name__ == "__main__":
    full_sync = "--full" in sys.argv
    try:
        result = sync_sales(full=full_sync)
        sys.exit(0)
    except RuntimeError as e:
        print(f"[error] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[error] Unexpected: {e}")
        sys.exit(1)
