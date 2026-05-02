"""
canva_watcher.py — Canva export watcher
─────────────────────────────────────────
Watches 03_Canva_Exports/ (synced from Dropbox or Google Drive via rclone)
for new product folders. When a folder has 5+ JPEG mockups and a meta.json
file, it automatically:

  1. Moves mockups to 02_Products/[ProductName]/Mockups/
  2. Adds the product to the SQLite queue using meta.json
  3. Logs the discovery to run_log

Run continuously (called by loop.sh every cycle):
    python scripts/canva_watcher.py

meta.json format (drop this file alongside your mockups in Dropbox/Drive):
    {
      "product_name": "UGC Rate Card Template",
      "title": "UGC Creator Rate Card Template | Editable Canva | Freelance Pricing",
      "tags": ["ugc creator", "rate card template", "canva template", ...],
      "description": "Ready-to-edit rate card for UGC creators...",
      "price": 7.99,
      "category": "Digital Downloads"
    }

Generate meta.json automatically by running:
    python scripts/meta_generator.py <product_name>
This reads master.txt to extract the matching title/tags/description.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from db import insert_queue_item, title_exists, log_run

_ROOT        = Path(__file__).resolve().parent.parent
INBOX_DIR    = _ROOT / "03_Canva_Exports"
PRODUCTS_DIR = _ROOT / "02_Products"

MIN_IMAGES   = 5
SETTLE_SECS  = 120   # wait 2 min after last file change before processing


def _is_settled(folder: Path) -> bool:
    """Return True if no file in the folder was modified in the last SETTLE_SECS."""
    now = time.time()
    for f in folder.iterdir():
        if now - f.stat().st_mtime < SETTLE_SECS:
            return False
    return True


def _process_folder(folder: Path) -> bool:
    """
    Process one inbox folder.
    Returns True if successfully queued, False if skipped.
    """
    meta_file = folder / "meta.json"
    images    = sorted(f for f in folder.glob("*.jpg"))
    images   += sorted(f for f in folder.glob("*.jpeg"))
    images   += sorted(f for f in folder.glob("*.png"))
    images   += sorted(f for f in folder.glob("*.webp"))

    if len(images) < MIN_IMAGES:
        print(f"  [watcher] {folder.name}: only {len(images)} images — need {MIN_IMAGES}, skipping")
        return False

    if not meta_file.exists():
        print(f"  [watcher] {folder.name}: no meta.json — skipping (run meta_generator.py first)")
        return False

    if not _is_settled(folder):
        print(f"  [watcher] {folder.name}: files still syncing — will check next cycle")
        return False

    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"  [watcher] {folder.name}: invalid meta.json — {e}")
        log_run(folder.name, "canva_watcher", "failed", f"Invalid meta.json: {e}")
        return False

    required = ["product_name", "title", "tags", "description", "price", "category"]
    missing  = [k for k in required if k not in meta]
    if missing:
        print(f"  [watcher] {folder.name}: meta.json missing fields: {missing}")
        log_run(folder.name, "canva_watcher", "failed", f"meta.json missing: {missing}")
        return False

    product_name = meta["product_name"]

    if title_exists(meta["title"]):
        print(f"  [watcher] {product_name}: title already in listings — skipping duplicate")
        shutil.rmtree(folder)
        return False

    # Move images to 02_Products/[ProductName]/Mockups/
    mockups_dir = PRODUCTS_DIR / product_name / "Mockups"
    mockups_dir.mkdir(parents=True, exist_ok=True)

    for src in images:
        dest = mockups_dir / src.name
        shutil.copy2(src, dest)
        print(f"  [watcher] Copied: {src.name} → {mockups_dir}")

    # Add to queue
    queue_id = insert_queue_item(
        product_name = product_name,
        title        = meta["title"],
        tags         = meta["tags"],
        description  = meta["description"],
        price        = float(meta["price"]),
        category     = meta.get("category", "Digital Downloads"),
    )

    print(f"  [watcher] Queued: {product_name} (queue ID: {queue_id})")
    log_run(product_name, "canva_watcher", "success",
            f"Queued ID={queue_id} with {len(images)} mockups")

    # Archive processed inbox folder
    done_dir = INBOX_DIR / "_processed" / product_name
    done_dir.parent.mkdir(exist_ok=True)
    shutil.move(str(folder), str(done_dir))
    print(f"  [watcher] Archived inbox folder → {done_dir}")

    return True


def watch_once() -> int:
    """
    Scan inbox once. Returns count of products queued this pass.
    Called by loop.sh every cycle.
    """
    INBOX_DIR.mkdir(exist_ok=True)

    folders = [
        f for f in INBOX_DIR.iterdir()
        if f.is_dir() and not f.name.startswith("_")
    ]

    if not folders:
        return 0

    queued = 0
    for folder in sorted(folders):
        if _process_folder(folder):
            queued += 1

    return queued


if __name__ == "__main__":
    count = watch_once()
    if count:
        print(f"\n  [watcher] {count} product(s) added to queue.")
    else:
        print("  [watcher] No new products found in inbox.")
