"""
db.py — SQLite schema and helpers
───────────────────────────────────
Single source of truth for all database operations.
Four tables per v3 spec:
  queue       — product work queue (pending → designed → published/failed)
  listings    — deduplication index of published titles
  run_log     — timestamped execution record per product
  seo_review  — post-publish tag gap analysis results
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _ROOT / "outputs" / "pipeline.db"


@contextmanager
def get_conn(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path = DB_PATH) -> None:
    """Create all four tables if they don't exist. Safe to call on every startup."""
    db_path.parent.mkdir(exist_ok=True)
    with get_conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS queue (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name    TEXT    NOT NULL,
                title           TEXT    NOT NULL,
                tags            TEXT    NOT NULL,  -- JSON array
                description     TEXT    NOT NULL,
                price           REAL    NOT NULL,
                category        TEXT    NOT NULL,
                status          TEXT    NOT NULL DEFAULT 'pending',
                created_at      TEXT    NOT NULL,
                updated_at      TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS listings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name    TEXT    NOT NULL,
                title           TEXT    NOT NULL UNIQUE,
                etsy_url        TEXT,
                published_at    TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS run_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name    TEXT    NOT NULL,
                phase           TEXT    NOT NULL,
                status          TEXT    NOT NULL,  -- success / failed / skipped
                message         TEXT,
                etsy_url        TEXT,
                run_at          TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seo_review (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name    TEXT    NOT NULL,
                listing_title   TEXT    NOT NULL,
                missing_tags    TEXT    NOT NULL,  -- JSON array
                competitor_tags TEXT    NOT NULL,  -- JSON array
                gap_count       INTEGER NOT NULL,
                reviewed_at     TEXT    NOT NULL
            );
        """)


# ── Queue helpers ─────────────────────────────────────────────────────────────

def insert_queue_item(
    product_name: str,
    title: str,
    tags: list[str],
    description: str,
    price: float,
    category: str,
    db_path: Path = DB_PATH,
) -> int:
    import json
    now = datetime.utcnow().isoformat()
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO queue
               (product_name, title, tags, description, price, category, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (product_name, title, json.dumps(tags), description, price, category, now, now),
        )
        return cur.lastrowid


def get_queue_items(status: str, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    with get_conn(db_path) as conn:
        return conn.execute(
            "SELECT * FROM queue WHERE status = ? ORDER BY created_at ASC", (status,)
        ).fetchall()


def update_queue_status(item_id: int, status: str, db_path: Path = DB_PATH) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE queue SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, item_id),
        )


# ── Listings (dedupe) helpers ─────────────────────────────────────────────────

def title_exists(title: str, db_path: Path = DB_PATH) -> bool:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM listings WHERE title = ?", (title,)
        ).fetchone()
        return row is not None


def insert_listing(
    product_name: str,
    title: str,
    etsy_url: str | None,
    db_path: Path = DB_PATH,
) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO listings (product_name, title, etsy_url, published_at) VALUES (?, ?, ?, ?)",
            (product_name, title, etsy_url, now),
        )


# ── Run log helpers ───────────────────────────────────────────────────────────

def log_run(
    product_name: str,
    phase: str,
    status: str,
    message: str = "",
    etsy_url: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO run_log (product_name, phase, status, message, etsy_url, run_at) VALUES (?, ?, ?, ?, ?, ?)",
            (product_name, phase, status, message, etsy_url, now),
        )


# ── SEO review helpers ────────────────────────────────────────────────────────

def insert_seo_review(
    product_name: str,
    listing_title: str,
    missing_tags: list[str],
    competitor_tags: list[str],
    db_path: Path = DB_PATH,
) -> None:
    import json
    now = datetime.utcnow().isoformat()
    with get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO seo_review
               (product_name, listing_title, missing_tags, competitor_tags, gap_count, reviewed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                product_name,
                listing_title,
                json.dumps(missing_tags),
                json.dumps(competitor_tags),
                len(missing_tags),
                now,
            ),
        )


if __name__ == "__main__":
    init_db()
    print(f"Database initialised at: {DB_PATH}")
