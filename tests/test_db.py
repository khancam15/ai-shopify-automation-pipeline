import json
import sqlite3
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import db


def _columns(db_path: Path, table_name: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def test_init_db_creates_seo_review_audit_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"

    db.init_db(db_path)

    assert {
        "original_tags",
        "optimised_tags",
        "added_tags",
        "removed_tags",
    }.issubset(_columns(db_path, "seo_review"))
    assert {"shopify_url", "shopify_product_id"}.issubset(_columns(db_path, "listings"))
    assert "shopify_url" in _columns(db_path, "run_log")


def test_insert_listing_migrates_legacy_table_and_stores_shopify_product_id(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-listings.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE listings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name    TEXT    NOT NULL,
                title           TEXT    NOT NULL UNIQUE,
                shopify_url     TEXT,
                published_at    TEXT    NOT NULL
            );
            """
        )

    db.insert_listing(
        "Test Product",
        "Test Title",
        "https://store.myshopify.com/products/test-product",
        shopify_product_id=12345,
        db_path=db_path,
    )

    assert "shopify_product_id" in _columns(db_path, "listings")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT shopify_product_id FROM listings").fetchone()

    assert row[0] == "12345"


def test_insert_seo_review_migrates_legacy_table_and_stores_audit_data(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE seo_review (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name    TEXT    NOT NULL,
                listing_title   TEXT    NOT NULL,
                missing_tags    TEXT    NOT NULL,
                competitor_tags TEXT    NOT NULL,
                gap_count       INTEGER NOT NULL,
                reviewed_at     TEXT    NOT NULL
            );
            """
        )

    db.insert_seo_review(
        product_name="Test Product",
        listing_title="Test Listing",
        original_tags=["old tag"],
        optimised_tags=["old tag", "new tag"],
        added_tags=["new tag"],
        removed_tags=[],
        missing_tags=["new tag"],
        competitor_tags=["new tag", "old tag"],
        db_path=db_path,
    )

    assert {
        "original_tags",
        "optimised_tags",
        "added_tags",
        "removed_tags",
    }.issubset(_columns(db_path, "seo_review"))

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM seo_review").fetchone()

    assert json.loads(row["original_tags"]) == ["old tag"]
    assert json.loads(row["optimised_tags"]) == ["old tag", "new tag"]
    assert json.loads(row["added_tags"]) == ["new tag"]
    assert json.loads(row["removed_tags"]) == []
    assert row["gap_count"] == 1


def test_insert_seo_review_uses_empty_added_tags_for_gap_count(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    db.init_db(db_path)

    db.insert_seo_review(
        product_name="Cleanup Product",
        listing_title="Cleanup Listing",
        original_tags=["tag", "tag"],
        optimised_tags=["tag"],
        added_tags=[],
        removed_tags=[],
        missing_tags=["unused competitor gap"],
        competitor_tags=["unused competitor gap"],
        db_path=db_path,
    )

    with sqlite3.connect(db_path) as conn:
        gap_count = conn.execute("SELECT gap_count FROM seo_review").fetchone()[0]

    assert gap_count == 0
