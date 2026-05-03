# AI Etsy Product Pipeline

A fully autonomous, API-driven pipeline that builds a brand, generates UGC creator template listings, creates Canva mockups and digital products, and publishes them to Etsy — all without a browser or manual steps. Runs continuously on a VPS via a three-mode loop (BUILD / DESIGN / MAINTAIN).

---

## How it works

```
Phase 1: CrewAI builds brand guide (every 7 days)
  └── Phase 2: Generates 10 product ideas + listing content → master.txt
        └── Phase 3: Canva MCP creates 6 mockup images per product
              └── Phase 3B: Canva MCP creates the actual digital template buyers download
                    └── Phase 4: Resize images → build listing → validate → stage
                          └── Phase 5: Publish listing + upload digital file to Etsy via REST API
                                └── Phase 6: SEO gap analysis → auto-apply best tags to live listing
                                      └── Phase 7: Health dashboard + daily email digest
```

**Your workflow:** Run OAuth once on your Mac → deploy to VPS → start the loop. Everything else is autonomous.

---

## Pipeline Phases

| Phase | Script | What happens |
|-------|--------|-------------|
| **Setup** | `scripts/db.py` | SQLite with 5 tables: `queue`, `listings`, `run_log`, `seo_review`, `sales` |
| **Pre-flight** | `scripts/preflight.py` | Validates all API credentials; auto-refreshes expired tokens; aborts loop if Etsy auth fails |
| **1 — Brand Builder** | `scripts/etsy_brand_crew.py` | 6-agent CrewAI crew runs live market research (Serper), builds brand strategy, visual identity, SEO keyword map → `outputs/brand_guide.md`. Refreshes every 7 days. |
| **2 — Launch Executor** | `scripts/etsy_launch_executor.py` | Reads brand guide, generates 10 Etsy listing ideas (titles, tags, descriptions) via Anthropic API → `outputs/master.txt`. Refreshes every 7 days. |
| **2 (rich)** | `scripts/etsy_autonomous.py` | Same as Phase 2 but with richer 4-part listing content and positioning |
| **3 — Image Generator** | `scripts/canva_image_generator.py` | Calls Anthropic API + Canva MCP — generates 6 mockup images per product (hero, features, preview, how-it-works, social proof, bundle). Exports via Canva Connect REST API. |
| **3B — Product Creator** | `scripts/canva_product_creator.py` | Calls Anthropic API + Canva MCP — creates the actual multi-page Canva template buyers download. Exports PDF + generates use-template link. Updates listing description automatically. |
| **4.1 — Image Processor** | `scripts/image_processor.py` | Resizes mockup images to 2000×2000 JPEG at quality 92 |
| **4.2 — Listing Builder** | `scripts/listing_builder.py` | Reads queue row from SQLite, assembles `listing.json` payload (includes template link + digital file path) |
| **4.3 — Validator** | `scripts/pre_upload_validator.py` | Validates title ≤140 chars, exactly 13 tags, price range, ≥5 mockups |
| **4.5 — File Organizer** | `scripts/file_organizer.py` | Stages files to `04_Assets/ReadyToUpload/`, archives after publish |
| **5 — Etsy Uploader** | `scripts/etsy_api_uploader.py` | Publishes listing to Etsy via REST API v3 — creates listing, uploads 6 images, uploads PDF digital file, marks as active |
| **6 — SEO Analyzer** | `scripts/seo_analyzer.py` | Fetches competitor tags, ranks by frequency, auto-applies optimised tag set to live listing (≥6 original tags kept). `--analyze-only` to skip the update. |
| **7 — Health Dashboard** | `scripts/health_dashboard.py` | Revenue summary, published count, failure rate, stuck queue items |
| **Sales Sync** | `scripts/sales_tracker.py` | Syncs Etsy transactions to SQLite. `--full` for all-time re-fetch. Runs daily. |
| **Email Digest** | `scripts/email_digest.py` | Sends daily HTML email with revenue summary, product pipeline status, and health stats |

---

## Autonomous Loop — Three Modes

`loop.sh` runs continuously and decides what to do each cycle based on your weekly publish budget and publish cooldown:

| Mode | Condition | What runs |
|------|-----------|-----------|
| **BUILD** | Under weekly limit + cooldown cleared | Phase 1 → 2 → 3 → 3B → 4 → 5 → 6 → 7 |
| **DESIGN** | Under weekly limit but cooldown still active | Phase 1 → 2 → 3 → 3B only (pre-designs next product) |
| **MAINTAIN** | Weekly publish limit reached | SEO refresh on all live listings → Phase 7 → sleep until Monday reset |

Configure in `.env`:
```
WEEKLY_PUBLISH_LIMIT=5        # max listings per Mon–Sun week (default 5)
PUBLISH_COOLDOWN_HOURS=24     # min hours between consecutive publishes (default 24)
```

---

## Project Structure

```
ai-etsy-product-pipeline/
│
├── .env.example                # Credentials template — copy to .env, never commit .env
├── .gitignore
├── .pre-commit-config.yaml     # gitleaks secret scan on every commit
├── run.sh                      # VPS entry point for all phases
├── loop.sh                     # Autonomous loop — three modes (BUILD/DESIGN/MAINTAIN)
├── setup_vps.sh                # One-time VPS bootstrap script
├── etsy-pipeline.service       # systemd unit for auto-restart on boot
├── requirements.txt
│
├── scripts/
│   ├── api_retry.py            # Exponential backoff for all API calls (429/5xx)
│   ├── canva_api.py            # Canva Connect REST API client (export, template link, folders)
│   ├── canva_image_generator.py# Phase 3 — Canva MCP mockup generator (6 images)
│   ├── canva_oauth.py          # One-time Canva OAuth2 PKCE setup (💻 HOST only)
│   ├── canva_product_creator.py# Phase 3B — Canva MCP digital product template creator
│   ├── common.py               # Shared utilities
│   ├── db.py                   # SQLite schema + all DB helpers
│   ├── email_digest.py         # Daily HTML email digest via Gmail SMTP
│   ├── etsy_api_uploader.py    # Phase 5 — Etsy REST API v3 listing publisher
│   ├── etsy_brand_crew.py      # Phase 1 — CrewAI brand builder
│   ├── etsy_launch_executor.py # Phase 2 — Listing content generator
│   ├── etsy_autonomous.py      # Phase 2 alt — Richer listing content engine
│   ├── etsy_oauth.py           # One-time Etsy OAuth2 PKCE setup (💻 HOST only)
│   ├── file_organizer.py       # Phase 4.5 — Stage and archive files
│   ├── health_dashboard.py     # Phase 7 — Daily health report + revenue summary
│   ├── image_processor.py      # Phase 4.1 — Mockup resize to 2000×2000 JPEG
│   ├── listing_builder.py      # Phase 4.2 — Build listing.json from queue
│   ├── meta_generator.py       # Parses master.txt → per-product meta.json
│   ├── pre_upload_validator.py # Phase 4.3 — Pre-upload validation
│   ├── preflight.py            # Credential check + token auto-refresh at loop startup
│   ├── queue_writer.py         # Manual queue entry (interactive or batch JSON)
│   ├── sales_tracker.py        # Etsy transactions sync → SQLite sales table
│   └── seo_analyzer.py         # Phase 6 — SEO gap analysis + auto-apply tags
│
├── 02_Products/                # Product source files and mockups
│   └── [ProductName]/
│       └── Mockups/
├── 04_Assets/
│   ├── ReadyToUpload/          # Staged files awaiting Etsy upload
│   └── Archived/               # Published listings moved here post-upload
│
├── outputs/                    # Runtime-generated files (git-ignored)
│   ├── brand_guide.md          # Phase 1 output
│   ├── master.txt              # Phase 2 output — product list + listing content
│   ├── executor_state.json
│   ├── week_log.md
│   └── pipeline.db             # SQLite database
│
└── logs/                       # Autonomous loop logs (git-ignored)
    ├── loop.log                # All stdout/stderr from loop.sh
    ├── loop_errors.log         # Failures only
    └── loop.pid                # Process ID for clean kill
```

---

## Requirements

- Python 3.12+
- [Anthropic API key](https://platform.claude.com/settings/keys) — Phases 1, 2, 3, 3B (Claude + Canva MCP)
- [Serper API key](https://serper.dev) — live market research in Phase 1
- [Etsy Developer account + API key](https://www.etsy.com/developers) — REST API for Phase 5 + SEO
- [Canva developer account + OAuth app](https://www.canva.com/developers/) — Canva Connect REST API
- Gmail account with [App Password](https://myaccount.google.com/apppasswords) — daily email digest
- Hostinger KVM 2 VPS (or any Ubuntu 24.04 LTS server)
- Canva MCP connected to Claude Code — required for Phase 3 and 3B

---

## Deployment

### 1. Clone and bootstrap

```bash
# 🖥️ VPS
cd /root
git clone https://github.com/khancam15/ai-etsy-product-pipeline.git
cd ai-etsy-product-pipeline
chmod +x setup_vps.sh && ./setup_vps.sh
```

### 2. Configure credentials

```bash
# 🖥️ VPS
nano .env
```

Minimum required keys:

```env
ANTHROPIC_API_KEY=sk-ant-...
SERPER_API_KEY=...

ETSY_API_KEY=...
ETSY_ACCESS_TOKEN=...         # filled by etsy_oauth.py
ETSY_REFRESH_TOKEN=...        # filled by etsy_oauth.py
ETSY_SHOP_ID=...              # filled by etsy_oauth.py

CANVA_CLIENT_ID=...
CANVA_CLIENT_SECRET=...
CANVA_ACCESS_TOKEN=...        # filled by canva_oauth.py
CANVA_REFRESH_TOKEN=...       # filled by canva_oauth.py

EMAIL_TO=your_email@gmail.com
EMAIL_FROM=your_gmail@gmail.com
EMAIL_SMTP_PASS=your_app_password

WEEKLY_PUBLISH_LIMIT=5
PUBLISH_COOLDOWN_HOURS=24
```

### 3. One-time OAuth setup — run on your Mac (needs a browser)

```bash
# 💻 HOST
python scripts/etsy_oauth.py    # opens browser → authorise → saves tokens to .env
python scripts/canva_oauth.py   # opens browser → authorise → saves tokens to .env
```

### 4. Initialise the database

```bash
# 🖥️ VPS
./run.sh db-init
```

### 5. Run pre-flight check

```bash
# 🖥️ VPS
./run.sh check
```

All lines should show ✓. If a token is expired, pre-flight auto-refreshes and saves it.

### 6. Install systemd service

```bash
# 🖥️ VPS
cp etsy-pipeline.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable etsy-pipeline
systemctl start etsy-pipeline
```

Verify:
```bash
# 🖥️ VPS
systemctl status etsy-pipeline
tail -f logs/loop.log
```

---

## One-off Commands

```bash
# 💻 HOST / 🖥️ VPS
./run.sh check                              # pre-flight credential check
./run.sh db-init                            # initialise SQLite database
./run.sh sales                              # sync latest Etsy transactions
./run.sh sales --full                       # re-fetch all-time transactions
./run.sh digest                             # send email digest now
./run.sh phase1                             # brand builder only
./run.sh phase2                             # listing content generator only
./run.sh phase3 "Product Name"              # generate 6 mockup images
./run.sh phase3b "Product Name"             # create digital product template
./run.sh phase4 "Product Name"              # process + stage one product
./run.sh phase5 "Product Name"              # publish one product to Etsy
./run.sh phase6 "Product Name"              # SEO analysis + auto-apply tags
./run.sh phase7                             # health dashboard
./run.sh full "Product Name"               # full pipeline: phase3 → 3b → 4 → 5 → 6
./loop.sh --once                            # run one loop cycle and exit (testing)

# 💻 HOST (OAuth — requires browser)
./run.sh etsy-auth                          # re-run Etsy OAuth
./run.sh canva-auth                         # re-run Canva OAuth
```

---

## Database Schema

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `queue` | Products waiting to be processed | `product_name`, `status` (pending/published/failed), `title`, `tags`, `description`, `price`, `template_link`, `digital_file` |
| `listings` | Published Etsy listings | `product_name`, `etsy_listing_id`, `etsy_url`, `published_at` |
| `run_log` | Per-phase execution log | `product_name`, `phase`, `status` (success/failed), `message`, `run_at` |
| `seo_review` | Post-publish SEO reviews | `product_name`, `original_tags`, `optimised_tags`, `tags_added`, `tags_removed`, `reviewed_at` |
| `sales` | Etsy transaction history | `transaction_id`, `product_name`, `amount` (net), `gross_amount`, `quantity`, `sale_date` |

---

## Security

| Protection | How |
|-----------|-----|
| API keys never committed | `.env` is git-ignored; only `.env.example` is tracked |
| Secret scanning on every commit | `gitleaks` via pre-commit hook |
| Runtime outputs git-ignored | `outputs/*`, `logs/*` all excluded |
| No hardcoded credentials | All secrets loaded via `python-dotenv` |
| Token auto-refresh | Etsy + Canva tokens refreshed automatically on 401 and saved back to `.env` |
| Exit codes enforce phase order | Each phase must exit 0 before the next runs |
| Retry logic on all API calls | Exponential backoff (2s/4s/8s) with Retry-After header support |

---

## Troubleshooting

### Loop not running after VPS reboot

```bash
# 🖥️ VPS
systemctl status etsy-pipeline
systemctl start etsy-pipeline
```

### Pre-flight fails on startup

```bash
# 🖥️ VPS
./run.sh check
```

If Etsy token is expired but refresh fails, re-run OAuth on your Mac:
```bash
# 💻 HOST
python scripts/etsy_oauth.py
```

### Phase fails mid-cycle

```bash
# 🖥️ VPS
tail -f logs/loop_errors.log
```

Phases 6 and 7 are non-fatal — the listing is already live if Phase 5 succeeded.

### No pending products in queue

Phase 3 hasn't run yet (designs not generated), or all products in `master.txt` have been published. Force a Phase 2 refresh:

```bash
# 🖥️ VPS
rm outputs/master.txt
./run.sh phase2
```

Or add a product manually:
```bash
# 🖥️ VPS
.venv/bin/python scripts/queue_writer.py
```

### Weekly publish limit reached

The loop automatically enters MAINTAIN mode (SEO refresh + health dashboard) and sleeps until Monday 00:00 UTC. To raise the limit:

```bash
# 🖥️ VPS
# Edit .env: WEEKLY_PUBLISH_LIMIT=10
```

### Out of API credits

Phase 1 is cached — brand guide refreshes only every 7 days. Phase 2 is also cached. To force a refresh:

```bash
# 🖥️ VPS
rm outputs/brand_guide.md   # force Phase 1
rm outputs/master.txt       # force Phase 2
```

---

## License

MIT
