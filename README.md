# AI Shopify Automation Pipeline

Autonomous pipeline for building digital products, generating Canva mockups and downloadable templates, publishing products to Shopify, syncing sales, and running post-publish SEO maintenance.

## Workflow

```text
Phase 1   Brand strategy          -> outputs/brand_guide.md
Phase 2   Product listing plan     -> outputs/master.txt
Phase 3   Canva mockup images      -> 02_Products/<product>/Mockups/
Phase 3B  Canva product/template   -> 03_Canva_Exports/<product>/meta.json
Phase 4   Process, build, validate -> 04_Assets/ReadyToUpload/<product>/
Phase 5   Publish to Shopify       -> Shopify Admin API
Phase 6   SEO refresh              -> Shopify tags + SEO metafields
Phase 7   Health dashboard         -> stdout/email-ready report
```

## Main Commands

```bash
./run.sh db-init
./run.sh shopify-auth
./run.sh canva-auth
./run.sh phase1
./run.sh phase2
./run.sh phase3 "Product Name"
./run.sh phase3b "Product Name"
./run.sh phase4 "Product Name"
./run.sh phase5 "Product Name"
./run.sh phase6 "Product Name"
./run.sh phase7
./run.sh sales
./run.sh full "Product Name"
```

For the autonomous VPS loop:

```bash
./loop.sh
./loop.sh --once
```

## Setup

1. Create a virtualenv and install dependencies.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

2. Copy the environment template.

```bash
cp .env.example .env
```

3. Fill in:

```text
ANTHROPIC_API_KEY
SERPER_API_KEY
SHOPIFY_STORE_DOMAIN
SHOPIFY_ACCESS_TOKEN
CANVA_CLIENT_ID
CANVA_CLIENT_SECRET
CANVA_ACCESS_TOKEN
CANVA_REFRESH_TOKEN
```

4. Verify Shopify credentials.

```bash
python scripts/shopify_setup.py
```

5. Initialize SQLite.

```bash
python scripts/db.py
```

## Shopify Requirements

Create a custom Shopify app with Admin API access. Required scopes:

```text
write_products
read_products
read_orders
write_orders
read_inventory
```

The uploader creates an active Shopify product, embeds mockup images, stores the product URL and product ID locally, and marks the queue row as published.

## Database

SQLite lives at `outputs/pipeline.db`.

Core tables:

```text
queue       pending/designed/published product work
listings    published Shopify products, including shopify_url and shopify_product_id
run_log     phase status history
seo_review  before/after SEO tag audit trail
sales       Shopify order line-item revenue
```

## Services

Install the Shopify systemd unit on the VPS:

```bash
cp shopify-pipeline.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable shopify-pipeline
systemctl start shopify-pipeline
systemctl status shopify-pipeline
```

## Verification

```bash
.venv/bin/pytest -q
.venv/bin/python -m compileall -q scripts tests
```
