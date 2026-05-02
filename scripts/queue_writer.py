"""
queue_writer.py — Phase 3 bridge
──────────────────────────────────
Adds a product to the SQLite queue so Phase 4 can pick it up.
Called manually once you have mockup images exported from Canva to:
  02_Products/[ProductName]/Mockups/

Two modes:
  1. Interactive (no args) — prompts for each field
  2. JSON file (--file)    — reads from a structured JSON file

Run:
    python scripts/queue_writer.py
    python scripts/queue_writer.py --file path/to/product.json
    python scripts/queue_writer.py --list

JSON file format:
    {
      "product_name": "UGC Creator Rate Card Template",
      "title": "UGC Creator Rate Card Template | Editable Canva | Freelance Pricing Sheet",
      "tags": ["ugc creator", "rate card template", "canva template", ...],
      "description": "Ready-to-edit rate card for UGC creators...",
      "price": 7.99,
      "category": "Digital Downloads"
    }
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from db import insert_queue_item, get_queue_items, title_exists, DB_PATH

_ROOT = Path(__file__).resolve().parent.parent


def _prompt(label: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    val = input(f"  {label}{hint}: ").strip()
    return val if val else default


def _add_from_dict(data: dict) -> int:
    required = ["product_name", "title", "tags", "description", "price", "category"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    if title_exists(data["title"]):
        print(f"  [queue_writer] Title already in listings table — skipping duplicate.")
        return -1

    tags = data["tags"]
    if isinstance(tags, str):
        tags = json.loads(tags)

    qid = insert_queue_item(
        product_name=data["product_name"],
        title=data["title"],
        tags=tags,
        description=data["description"],
        price=float(data["price"]),
        category=data["category"],
    )
    print(f"  [queue_writer] Added to queue: ID={qid} | {data['product_name']}")
    return qid


def add_interactive() -> int:
    print("\n  Add product to queue")
    print("  " + "-" * 40)
    product_name = _prompt("Product name (folder name in 02_Products/)")
    title        = _prompt("Etsy listing title (max 140 chars)")
    tags_raw     = _prompt("Tags (comma-separated, exactly 13)")
    description  = _prompt("Description")
    price        = _prompt("Price (e.g. 7.99)", "7.99")
    category     = _prompt("Category", "Digital Downloads")

    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    return _add_from_dict({
        "product_name": product_name,
        "title":        title,
        "tags":         tags,
        "description":  description,
        "price":        float(price),
        "category":     category,
    })


def list_queue() -> None:
    pending = get_queue_items("pending")
    designed = get_queue_items("designed")
    if not pending and not designed:
        print("  Queue is empty.")
        return
    for row in pending + designed:
        print(f"  ID={row['id']} [{row['status']}] {row['product_name']} | {row['title'][:60]}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--list" in args:
        list_queue()
        sys.exit(0)

    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 >= len(args):
            print("Usage: python scripts/queue_writer.py --file <path>")
            sys.exit(1)
        path = Path(args[idx + 1])
        if not path.exists():
            print(f"[error] File not found: {path}")
            sys.exit(1)
        data = json.loads(path.read_text(encoding="utf-8"))
        # Support a list of products in one file
        if isinstance(data, list):
            for item in data:
                _add_from_dict(item)
        else:
            _add_from_dict(data)
        sys.exit(0)

    # Default: interactive mode
    try:
        add_interactive()
    except (KeyboardInterrupt, EOFError):
        print("\n  Cancelled.")
        sys.exit(0)
