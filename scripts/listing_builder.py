"""
listing_builder.py  —  Phase 4.2
──────────────────────────────────
Reads a queue row from SQLite and formats all fields into a structured
JSON payload that Playwright and the validator consume downstream.

Run:
    python scripts/listing_builder.py <product_name>   — uses newest pending row
    python scripts/listing_builder.py <queue_id>       — uses exact row by ID

Output:
    04_Assets/ReadyToUpload/[ProductName]/listing.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from db import get_conn, DB_PATH, log_run

_ROOT       = Path(__file__).resolve().parent.parent
ASSETS_DIR  = _ROOT / "04_Assets" / "ReadyToUpload"


def build_listing_payload(queue_id: int) -> dict:
    """
    Reads the queue row and returns a validated payload dict.

    Execution steps:
      1. Fetch the queue row by ID — raises if not found
      2. Parse the tags JSON string back to a list
      3. Assemble the payload with all fields Playwright needs
      4. Write listing.json to 04_Assets/ReadyToUpload/[ProductName]/
      5. Return the payload dict for downstream use
    """
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM queue WHERE id = ?", (queue_id,)).fetchone()

    if row is None:
        raise ValueError(f"Queue item {queue_id} not found")

    tags: list[str] = json.loads(row["tags"])
    product_name: str = row["product_name"]

    payload = {
        "queue_id":     queue_id,
        "product_name": product_name,
        "title":        row["title"],
        "tags":         tags,
        "description":  row["description"],
        "price":        row["price"],
        "category":     row["category"],
    }

    out_dir = ASSETS_DIR / product_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "listing.json"
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  [4.2] Listing payload written: {out_file}")
    log_run(product_name, "listing_builder", "success", f"Payload written to {out_file}")
    return payload


def _resolve_queue_id(arg: str) -> int:
    """Accept either a numeric queue_id or a product_name string."""
    if arg.isdigit():
        return int(arg)
    # Look up the most recent pending row for this product name
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM queue WHERE product_name = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
            (arg,),
        ).fetchone()
    if row is None:
        raise ValueError(f"No pending queue item found for product: {arg}")
    return row["id"]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/listing_builder.py <product_name|queue_id>")
        sys.exit(1)

    try:
        qid = _resolve_queue_id(sys.argv[1])
        p = build_listing_payload(qid)
        print(f"\n  Done — payload for: {p['product_name']}")
    except ValueError as e:
        print(f"[error] {e}")
        sys.exit(1)
