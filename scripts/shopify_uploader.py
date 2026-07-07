"""
shopify_uploader.py  —  Phase 5
────────────────────────────────────────────────────────────────────
Creates a live Shopify product listing via the Admin REST API,
uploads mockup images (base64-encoded), and embeds the Canva
template link in the product description.

Run:
    python scripts/shopify_uploader.py <product_name>

Prerequisites (one-time, 💻 HOST):
    python scripts/shopify_setup.py

Credentials read from .env:
    SHOPIFY_STORE_DOMAIN  — e.g. your-store.myshopify.com
    SHOPIFY_ACCESS_TOKEN  — Admin API access token (shpat_...)
    SHOPIFY_API_VERSION   — optional, defaults to 2024-01

Execution flow:
  5.1  Load listing.json from 04_Assets/ReadyToUpload/[ProductName]/
  5.2  Convert plain-text description to HTML
  5.3  POST /products.json with variants, tags, and body_html → get product_id
  5.4  Images already embedded via base64 in the create call
  5.5  Log success to SQLite run_log + insert into listings table
  5.6  Update queue row to "published"
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values, load_dotenv
from api_retry import retry_request

from db import insert_listing, log_run, update_queue_status

_ROOT    = Path(__file__).resolve().parent.parent
ENV_PATH = _ROOT / ".env"
load_dotenv(ENV_PATH)

ASSETS_DIR  = _ROOT / "04_Assets" / "ReadyToUpload"
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2024-01")


def _load_env() -> dict[str, str]:
    return {k: v for k, v in dotenv_values(ENV_PATH).items() if v is not None}


def _normalize_domain(domain: str) -> str:
    return domain.strip().removeprefix("https://").removeprefix("http://").rstrip("/")


def _api_base(domain: str) -> str:
    domain = _normalize_domain(domain)
    return f"https://{domain}/admin/api/{API_VERSION}"


def _headers(access_token: str) -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }


# ── Description → HTML ────────────────────────────────────────────────────────

def _to_html(text: str) -> str:
    """Convert plain-text product description to basic HTML for Shopify body_html."""
    lines = text.split("\n")
    html_parts: list[str] = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("")
            continue

        if stripped.startswith(("- ", "• ", "* ")):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            html_parts.append(f"  <li>{stripped[2:].strip()}</li>")
        elif stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
            if not in_list:
                html_parts.append("<ol>")
                in_list = True
            content = stripped.split(".", 1)[1].strip() if "." in stripped else stripped
            html_parts.append(f"  <li>{content}</li>")
        elif stripped.startswith("**") and stripped.endswith("**"):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<strong>{stripped.strip('*')}</strong>")
        elif stripped.startswith("#"):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            heading = stripped.lstrip("#").strip()
            html_parts.append(f"<h3>{heading}</h3>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p>{stripped}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(p for p in html_parts if p != "")


# ── Image encoding ────────────────────────────────────────────────────────────

def _encode_image(path: Path) -> str:
    """Return base64-encoded JPEG content for Shopify image attachment."""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


# ── Product creation ──────────────────────────────────────────────────────────

def _create_product(
    domain: str,
    access_token: str,
    payload: dict,
    image_paths: list[Path],
) -> dict:
    """
    POST a new Shopify product. Returns the created product dict.
    Images are sent as base64 attachments in the same request.
    """
    tags_raw = payload.get("tags", [])
    tags_str = ", ".join(str(t) for t in tags_raw)

    description_text = payload.get("description", "")
    template_link    = payload.get("template_link", "")
    if template_link:
        description_text += (
            "\n\n──────────────────────────────────────\n"
            "✦ HOW TO ACCESS YOUR TEMPLATE\n"
            "──────────────────────────────────────\n"
            f"After purchase, click this link to get your free editable Canva copy:\n{template_link}\n\n"
            "No Canva account required to get started — Canva is free to use.\n"
            "Edit on any device in minutes."
        )

    body_html = _to_html(description_text)

    images = [
        {"attachment": _encode_image(p), "filename": p.name, "position": i + 1}
        for i, p in enumerate(image_paths[:10])
    ]

    product_body = {
        "product": {
            "title":        payload["title"][:255],
            "body_html":    body_html,
            "vendor":       os.getenv("SHOPIFY_VENDOR", "Benjaire LLC"),
            "product_type": payload.get("category", "Digital Template"),
            "tags":         tags_str,
            "status":       "active",
            "variants": [{
                "price":                str(float(payload["price"])),
                "requires_shipping":    False,
                "inventory_management": None,
                "inventory_policy":     "continue",
                "fulfillment_service":  "manual",
            }],
            "images": images,
        }
    }

    resp = retry_request(
        "POST",
        f"{_api_base(domain)}/products.json",
        headers=_headers(access_token),
        json=product_body,
        timeout=120,
        _label="Shopify create product",
    )

    if not resp.ok:
        raise RuntimeError(
            f"Product creation failed ({resp.status_code}): {resp.text[:400]}"
        )

    return resp.json()["product"]


# ── Main ──────────────────────────────────────────────────────────────────────

def upload_listing(product_name: str) -> str | None:
    """
    Full Phase 5 upload via Shopify Admin API.
    Returns the product URL on success, None on failure.
    """
    env = _load_env()

    domain       = _normalize_domain(env.get("SHOPIFY_STORE_DOMAIN", ""))
    access_token = env.get("SHOPIFY_ACCESS_TOKEN", "")

    if not domain or not access_token:
        raise RuntimeError(
            "SHOPIFY_STORE_DOMAIN and SHOPIFY_ACCESS_TOKEN are required. "
            "Run: python scripts/shopify_setup.py"
        )

    payload_file = ASSETS_DIR / product_name / "listing.json"
    if not payload_file.exists():
        raise FileNotFoundError(
            f"listing.json not found — run listing_builder.py first"
        )

    payload = json.loads(payload_file.read_text(encoding="utf-8"))

    # Collect mockup images (ReadyToUpload dir or Mockups dir)
    mockups_dir  = _ROOT / "02_Products" / product_name / "Mockups"
    image_paths  = sorted(mockups_dir.glob("*.jpg")) if mockups_dir.exists() else []
    if not image_paths:
        image_paths = sorted((ASSETS_DIR / product_name).glob("*.jpg"))
    if not image_paths:
        raise FileNotFoundError(
            f"No JPEG mockups found for {product_name}"
        )

    print(f"  [5.1] Loaded listing.json for: {product_name}")
    print(f"  [5.1] Images: {len(image_paths)} mockups")

    product = _create_product(domain, access_token, payload, image_paths)
    product_id     = product["id"]
    product_handle = product.get("handle", "")
    product_url    = f"https://{domain}/products/{product_handle}"

    print(f"  [5.3] Product created: ID {product_id}")
    print(f"  [5.5] Listing live: {product_url}")

    log_run(
        product_name,
        "shopify_uploader",
        "success",
        f"Product published via Admin API — ID {product_id}",
        shopify_url=product_url,
    )
    insert_listing(product_name, payload["title"], product_url, shopify_product_id=product_id)
    update_queue_status(payload["queue_id"], "published")

    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).parent))
        from file_organizer import archive
        archive(product_name)
    except Exception as exc:
        print(f"  [5.6] Archive warning (non-fatal): {exc}")

    return product_url


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/shopify_uploader.py <product_name>")
        sys.exit(1)

    try:
        result = upload_listing(sys.argv[1])
        sys.exit(0 if result else 1)
    except (FileNotFoundError, RuntimeError) as e:
        print(f"[error] {e}")
        sys.exit(1)
