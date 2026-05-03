"""
canva_product_creator.py — Phase 3B
──────────────────────────────────────
Creates the actual digital product that buyers download from Etsy.

This is separate from Phase 3 (mockup images). Phase 3 makes the
listing look good; Phase 3B makes the thing people actually buy.

What it does:
  1. Reads product info from outputs/master.txt + meta.json
  2. Uses Anthropic API + Canva MCP to design a complete, professional
     template (media kit, rate card, pitch deck, etc.)
  3. Gets a "Use template" share link via Canva Connect API
     → buyers click this and get their own editable Canva copy
  4. Exports a PDF version via Canva Connect API
     → uploaded to Etsy as the digital download file
  5. Saves template_link + pdf_path to meta.json + a _product.json record
     → Phase 4 (listing_builder) embeds the link in the description
     → Phase 5 (etsy_api_uploader) attaches the PDF to the listing

Run:
    python scripts/canva_product_creator.py "Product Name" [--price 9.99]

Requires:
    ANTHROPIC_API_KEY in .env
    CANVA_MCP_TOKEN in .env       (for design creation via MCP)
    CANVA_ACCESS_TOKEN in .env    (for template link + PDF export via Connect API)

Output per product:
    02_Products/[ProductName]/Product/template.pdf
    outputs/[ProductName]_product.json
    03_Canva_Exports/[ProductName]/meta.json  ← updated with template_link
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

try:
    import requests
except ImportError:
    print("[3B] ERROR: requests not installed. Run: .venv/bin/pip install requests")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))
from db import log_run
from canva_api import CanvaClient, CanvaAPIError
from meta_generator import (
    _find_product_section,
    _list_products,
    MASTER_FILE,
    INBOX_DIR,
)

OUTPUTS_DIR  = _ROOT / "outputs"
PRODUCTS_DIR = _ROOT / "02_Products"
BRAND_GUIDE  = OUTPUTS_DIR / "brand_guide.md"

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CANVA_MCP_URL = "https://mcp.canva.com/mcp"
MODEL         = "claude-opus-4-5"


# ── Product archetypes → page structure ───────────────────────────────────────

def _detect_product_type(product_name: str, description: str) -> str:
    """Detect the product type from name/description for smarter page structure."""
    combined = (product_name + " " + description).lower()
    if any(k in combined for k in ["pitch deck", "presentation", "slide"]):
        return "pitch_deck"
    if any(k in combined for k in ["media kit", "press kit", "influencer kit"]):
        return "media_kit"
    if any(k in combined for k in ["rate card", "rate sheet", "pricing card"]):
        return "rate_card"
    if any(k in combined for k in ["portfolio", "lookbook", "showcase"]):
        return "portfolio"
    if any(k in combined for k in ["invoice", "contract", "proposal"]):
        return "business_doc"
    if any(k in combined for k in ["resume", "cv ", "curriculum"]):
        return "resume"
    if any(k in combined for k in ["social media", "content calendar", "post template"]):
        return "social_template"
    return "media_kit"  # default for creator niche


_PAGE_STRUCTURES: dict[str, list[str]] = {
    "media_kit": [
        "Cover — creator name, tagline, hero photo placeholder, niche labels",
        "About Me — bio, content niche, audience stats (followers, engagement rate)",
        "Content Categories — 3-4 content pillars with icons and short descriptions",
        "Audience Demographics — location, age range, platform breakdown",
        "Portfolio — 4-6 image placeholders for past brand collaborations",
        "Rates & Packages — tiered packages (Basic / Standard / Premium)",
        "Contact — email, social handles, booking CTA",
    ],
    "rate_card": [
        "Cover — creator name and 'Rate Card [Year]' header",
        "About — short bio, platform stats, niche summary",
        "Services — 3 service tiers with deliverables and prices",
        "Add-ons — optional extras (usage rights, exclusivity, rush)",
        "Process — how it works in 3 steps",
        "Terms — usage rights, revision policy, payment terms",
        "Contact — booking email, social handles",
    ],
    "pitch_deck": [
        "Cover — creator/brand name, bold headline, date",
        "The Opportunity — market context, audience size",
        "About Me / The Creator — stats, niche, past work logos",
        "Services — what you offer and why it works",
        "Case Studies — 2 brand deal examples with outcomes",
        "Packages & Pricing — tiered offerings",
        "Testimonials — 2-3 brand quotes",
        "Next Steps — CTA, contact info",
    ],
    "portfolio": [
        "Cover — name, portfolio title, niche",
        "Featured Work — 4 large image placeholders",
        "Project Breakdown — client, deliverables, results",
        "Stats & Reach — engagement, impressions, follower growth",
        "Collaborations — brand logos",
        "Services & Availability — current offerings",
        "Contact",
    ],
    "business_doc": [
        "Header — logo, document title, date, client/sender details",
        "Scope of Work — services, deliverables, timeline",
        "Pricing — itemised line items, totals",
        "Terms & Conditions — payment, revisions, ownership",
        "Signature block",
    ],
    "resume": [
        "Header — name, title, contact details",
        "Summary — professional bio",
        "Experience — work history with bullet points",
        "Skills — key competencies",
        "Education — qualifications",
        "Portfolio / Links — social handles, website",
    ],
    "social_template": [
        "Feed post templates (3 variations) — quote card, tips card, promotional",
        "Story templates (3 variations) — Q&A, countdown, announcement",
        "Carousel cover — branded multi-slide intro",
        "Highlight covers (6 icons) — reels, lifestyle, collabs, q&a, tips, shop",
    ],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_brand_context() -> str:
    if not BRAND_GUIDE.exists():
        return (
            "Brand: Benjaire LLC. "
            "Colors: cream #faf7f2 backgrounds, blush pink #c4a0a0 accents. "
            "Serif headlines, clean sans body, minimal editorial layout."
        )
    text   = BRAND_GUIDE.read_text(encoding="utf-8")
    lines  = []
    in_sec = False
    for line in text.split("\n"):
        lo = line.lower()
        if any(k in lo for k in ["color", "font", "palette", "typography", "visual", "aesthetic", "brand voice"]):
            in_sec = True
        if in_sec:
            lines.append(line)
        if in_sec and not line.strip() and len(lines) > 6:
            break
    return "\n".join(lines[:30]) or text[:600]


def _get_product_info(product_name: str, price: float) -> dict:
    """Read description from master.txt; fall back to meta.json."""
    description = ""
    title       = product_name

    if MASTER_FILE.exists():
        text    = MASTER_FILE.read_text(encoding="utf-8")
        section = _find_product_section(text, product_name)
        # Extract description
        dm = re.search(
            r"\*\*(?:Full )?Description\*\*[:\s]*([\s\S]{50,1500}?)(?=\n\*\*|\Z)",
            section,
        )
        if dm:
            description = dm.group(1).strip()
        # Extract title
        tm = re.search(r"\*\*Title\*\*[:\s]+(.{10,140})", section)
        if tm:
            title = tm.group(1).strip()

    meta_file = INBOX_DIR / product_name / "meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if not description:
            description = meta.get("description", "")
        if not title or title == product_name:
            title = meta.get("title", product_name)

    return {
        "product_name": product_name,
        "title":        title,
        "description":  description[:500],
        "price":        price,
    }


def _build_product_prompt(
    product_name: str,
    price: float,
    title: str,
    description: str,
    brand_ctx: str,
    product_type: str,
    pages: list[str],
) -> str:
    page_list = "\n".join(f"  Page {i+1}: {p}" for i, p in enumerate(pages))
    canva_type = "presentation" if product_type == "pitch_deck" else "document"

    return f"""You are creating a professional, fully editable Canva template — the actual digital product that buyers will download and use.

PRODUCT DETAILS:
  Name:        {product_name}
  Title:       {title}
  Price:       ${price}
  Description: {description}

BRAND VISUAL RULES:
{brand_ctx}
Core palette: cream #faf7f2 backgrounds, blush pink #c4a0a0 accents, dark readable text.
Style: serif headlines (Playfair Display or similar), clean sans body (Lato/Montserrat), generous white space, premium editorial feel.

DESIGN TYPE: {canva_type}

YOUR STEPS — execute in order:
1. Create a Canva folder named exactly: "{product_name} Template"
2. Create ONE {canva_type} design with ALL pages listed below
3. Move the design into the "{product_name} Template" folder
4. After completing, output EXACTLY:
   PRODUCT_DESIGN: https://www.canva.com/design/...

PAGE STRUCTURE (create all pages in order):
{page_list}

DESIGN RULES — apply to every page:
- Cream #faf7f2 background, blush pink #c4a0a0 accents, dark text
- Serif headlines, clean sans body, generous white space
- Use placeholder labels: [Your Name], [Insert Photo Here], [Add Your Bio], [Your Rate], [Client Logo] etc.
- Every text box and image frame must be clearly labelled so buyers know what to replace
- Include subtle brand color accents (borders, dividers, callout boxes) in blush pink
- Professional quality — this is a paid product, not a rough draft
- Keep layouts clean: no cluttered elements, strong visual hierarchy on every page

Create the complete {len(pages)}-page template now. Design all pages before outputting the PRODUCT_DESIGN line."""


# ── API call ──────────────────────────────────────────────────────────────────

def _call_api(prompt: str) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in .env")

    canva_token = os.getenv("CANVA_MCP_TOKEN", "")
    mcp_server: dict = {"type": "url", "url": CANVA_MCP_URL, "name": "canva"}
    if canva_token:
        mcp_server["authorization_token"] = canva_token

    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta":    "mcp-client-2025-04-04",
        },
        json={
            "model":       MODEL,
            "max_tokens":  8192,
            "messages":    [{"role": "user", "content": prompt}],
            "mcp_servers": [mcp_server],
        },
        timeout=600,
    )

    if resp.status_code == 401:
        body    = resp.json()
        auth_url = (body.get("error") or {}).get("auth_url") or body.get("auth_url")
        if auth_url:
            raise RuntimeError(
                f"\n  Canva requires authorisation. Visit:\n\n  {auth_url}\n\n"
                f"  Then add CANVA_MCP_TOKEN=Bearer <token> to .env and re-run.\n"
            )
        raise RuntimeError(f"API 401: {body}")

    resp.raise_for_status()
    return resp.json()


def _collect_text(response: dict) -> str:
    parts = []
    for block in response.get("content", []):
        btype = block.get("type", "")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "mcp_tool_result":
            for sub in block.get("content", []):
                if isinstance(sub, dict) and sub.get("type") == "text":
                    parts.append(sub["text"])
    return "\n".join(parts)


def _parse_design_url(text: str) -> str:
    """Extract PRODUCT_DESIGN: URL from response text."""
    m = re.search(r"PRODUCT_DESIGN:\s*(https://[^\s]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback: first canva.com/design/ URL
    m2 = re.search(r"https://www\.canva\.com/design/[^\s\"')>\]]+", text)
    return m2.group(0) if m2 else ""


# ── Post-processing ───────────────────────────────────────────────────────────

def _export_and_link(design_url: str, product_name: str) -> tuple[str, str]:
    """
    Given a Canva design URL:
      1. Get a "Use template" share link (for listing description)
      2. Export as PDF (for Etsy digital download file)

    Returns (template_link, pdf_path) — either may be empty string on failure.
    """
    template_link = ""
    pdf_path      = ""

    if not design_url:
        return template_link, pdf_path

    if not os.getenv("CANVA_ACCESS_TOKEN"):
        print("  [3B] CANVA_ACCESS_TOKEN not set — skipping Connect API steps")
        template_link = design_url  # use raw design URL as fallback
        return template_link, pdf_path

    try:
        client    = CanvaClient()
        design_id = CanvaClient.design_id_from_url(design_url)

        # 1. Template share link
        print(f"  [3B] Getting 'Use template' share link...")
        template_link = client.get_template_link(design_id)
        print(f"  [3B] Template link: {template_link[:70]}...")

        # 2. PDF export
        print(f"  [3B] Exporting PDF via Connect API...")
        pdf_urls = client.export_design(design_id, fmt="pdf")
        if pdf_urls:
            product_dir = PRODUCTS_DIR / product_name / "Product"
            product_dir.mkdir(parents=True, exist_ok=True)
            pdf_dest = product_dir / "template.pdf"

            r = requests.get(pdf_urls[0], timeout=120, allow_redirects=True)
            r.raise_for_status()
            pdf_dest.write_bytes(r.content)
            pdf_path = str(pdf_dest)
            size_kb  = len(r.content) // 1024
            print(f"  [3B] PDF saved: template.pdf ({size_kb} KB)")
        else:
            print(f"  [3B] PDF export returned no URLs — skipping")

    except CanvaAPIError as exc:
        print(f"  [3B] Canva API step failed: {exc}")
        template_link = template_link or design_url

    return template_link, pdf_path


_TEMPLATE_BLURB = """

──────────────────────────────────────
✦ HOW TO ACCESS YOUR TEMPLATE
──────────────────────────────────────
After purchase, click this link to get your free editable Canva copy:
{link}

No Canva account required to get started — Canva is free to use.
Edit on any device in minutes."""


def _update_meta(product_name: str, template_link: str, pdf_path: str) -> None:
    """
    Add template_link and product_pdf to meta.json so listing_builder
    can read the extras. Also updates the SQLite queue row description
    so the template link actually reaches the Etsy listing.
    """
    link_blurb = _TEMPLATE_BLURB.format(link=template_link) if template_link else ""

    # ── 1. Update meta.json ───────────────────────────────────────────────────
    meta_file = INBOX_DIR / product_name / "meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        if template_link:
            meta["template_link"] = template_link
        if pdf_path:
            meta["product_pdf"] = pdf_path
        if link_blurb and link_blurb not in meta.get("description", ""):
            meta["description"] = (meta.get("description", "") + link_blurb)[:4000]
        meta_file.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  [3B] meta.json updated with template_link")
    else:
        print(f"  [3B] meta.json not found — skipping meta update")

    # ── 2. Also patch the SQLite queue row description ────────────────────────
    # listing_builder.py reads description from the queue row, not meta.json,
    # so we must update the queue row here or the template link never reaches Etsy.
    if not template_link:
        return
    try:
        from datetime import datetime
        from db import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT id, description FROM queue "
                "WHERE product_name = ? AND status = 'pending' "
                "ORDER BY id DESC LIMIT 1",
                (product_name,),
            ).fetchone()
            if row and link_blurb not in (row["description"] or ""):
                new_desc = ((row["description"] or "") + link_blurb)[:4000]
                conn.execute(
                    "UPDATE queue SET description = ?, updated_at = ? WHERE id = ?",
                    (new_desc, datetime.utcnow().isoformat(), row["id"]),
                )
                print(f"  [3B] Queue row description updated with template link")
    except Exception as exc:
        print(f"  [3B] WARNING: Could not update queue description: {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────

def create_product(product_name: str, price: float | None = None) -> int:
    """
    Full Phase 3B:
      1. Detect product type → page structure
      2. Generate template in Canva via MCP
      3. Export PDF + get template link via Connect API
      4. Update meta.json
      5. Save _product.json record

    Returns 0 on success, 1 on failure.
    """
    print(f"\n  [3B] ── Product Creator ──────────────────────────────")
    print(f"  [3B] Product: {product_name}")

    # Resolve price
    if price is None:
        price = 9.99
        if MASTER_FILE.exists():
            text     = MASTER_FILE.read_text(encoding="utf-8")
            products = _list_products(text)
            for p in products:
                if p["name"].lower() == product_name.lower():
                    price = float(p["price"])
                    break
    print(f"  [3B] Price:   ${price}")

    # Load product info
    info        = _get_product_info(product_name, price)
    title       = info["title"]
    description = info["description"]

    # Detect product type + page structure
    ptype  = _detect_product_type(product_name, description)
    pages  = _PAGE_STRUCTURES.get(ptype, _PAGE_STRUCTURES["media_kit"])
    print(f"  [3B] Detected type: {ptype} ({len(pages)} pages)")

    brand_ctx = _load_brand_context()
    prompt    = _build_product_prompt(
        product_name, price, title, description, brand_ctx, ptype, pages
    )

    print(f"  [3B] Calling Anthropic API + Canva MCP ({MODEL})")
    print(f"  [3B] Generating {len(pages)}-page {ptype.replace('_', ' ')} template...")

    try:
        response = _call_api(prompt)
    except RuntimeError as exc:
        print(f"  [3B] ERROR: {exc}")
        log_run(product_name, "canva_product_creator", "failed", str(exc)[:400])
        return 1
    except Exception as exc:
        print(f"  [3B] Unexpected error: {exc}")
        log_run(product_name, "canva_product_creator", "failed", str(exc)[:400])
        return 1

    text       = _collect_text(response)
    design_url = _parse_design_url(text)

    if not design_url:
        debug_path = OUTPUTS_DIR / f"{product_name.replace(' ', '_')}_product_raw.json"
        debug_path.write_text(json.dumps(response, indent=2), encoding="utf-8")
        print(f"  [3B] ERROR: No design URL found. Raw response → {debug_path}")
        log_run(product_name, "canva_product_creator", "failed",
                f"No design URL — debug saved to {debug_path.name}")
        return 1

    print(f"\n  [3B] Template design created: {design_url}")

    # Export PDF + get template link
    template_link, pdf_path = _export_and_link(design_url, product_name)

    # Update meta.json
    _update_meta(product_name, template_link, pdf_path)

    # Save product record
    OUTPUTS_DIR.mkdir(exist_ok=True)
    record = {
        "product_name":  product_name,
        "price":         price,
        "product_type":  ptype,
        "pages":         len(pages),
        "generated_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "design_url":    design_url,
        "template_link": template_link,
        "product_pdf":   pdf_path,
    }
    safe     = product_name.replace(" ", "_")
    rec_path = OUTPUTS_DIR / f"{safe}_product.json"
    rec_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  [3B] Record saved → {rec_path}")

    status_parts = []
    if template_link:
        status_parts.append("template link ✓")
    if pdf_path:
        status_parts.append("PDF ✓")
    status = ", ".join(status_parts) or "design only"

    print(f"\n  [3B] ✓ Phase 3B complete: {ptype} template — {status}")

    log_run(product_name, "canva_product_creator", "success",
            f"type={ptype}, pages={len(pages)}, {status}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage: python scripts/canva_product_creator.py \"Product Name\" [--price 9.99]")
        sys.exit(1)

    _product = args[0]
    _price: float | None = None
    if "--price" in args:
        idx = args.index("--price")
        if idx + 1 < len(args):
            _price = float(args[idx + 1])

    sys.exit(create_product(_product, _price))
