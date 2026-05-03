# AI Etsy Product Pipeline

An end-to-end AI-powered pipeline that researches a niche, builds a full brand identity, generates Etsy listing content, auto-generates competitive product mockups via the Canva MCP, and uploads listings to Etsy — fully autonomous on a VPS. Your only recurring task is reviewing and approving AI-generated designs.

---

## How it works

```
Claude reads your brand guide → generates 6 competitive mockup designs via Canva MCP
  └── You review designs in Canva → approve and export to Google Drive
        └── rclone syncs to VPS every 5 minutes
              └── Canva watcher detects new product → queues it automatically
                    └── Pipeline processes images → builds listing → uploads to Etsy
                          └── SEO analysis runs → daily email digest sent to you
```

That's your entire workflow. Everything else runs while you sleep.

---

## Mockup Image Strategy

Every product gets 6 AI-generated images built around Etsy conversion data. Each image has a specific job:

| # | Image | Purpose | Why it works |
|---|-------|---------|--------------|
| 1 | **Before / After split** | Hero — stop the scroll | Highest CTR format used by 30% of top Etsy sellers |
| 2 | **Features + price anchor** | Sell the value | Shows outcome-tied features + "Designer cost $200+ · Your price $9.99" |
| 3 | **Filled-in template preview** | Prove the quality | Buyers see exactly what they're getting before they buy |
| 4 | **How it works** | Remove friction | Time-specific steps: "Download → Customize → Pitch. Ready in 30 minutes." |
| 5 | **Testimonial + trust badges** | Social proof | Specific outcome quote + "Beginner Friendly" + niche badges |
| 6 | **Bundle value stack** | Close the sale | "$188 total value → $9.99" price anchoring drives impulse purchase |

Claude generates 4 design variations per image using your brand kit, picks the richest layout for each, saves all 6 to a named Canva folder, and exports them ready for Google Drive.

---

## Pipeline Overview

| Phase | Script | What happens |
|-------|--------|-------------|
| **Setup** | `scripts/db.py` | SQLite with 4 tables: `queue`, `listings`, `run_log`, `seo_review` |
| **1 — Brand Builder** | `scripts/etsy_brand_crew.py` | 6-agent CrewAI crew runs live market research (Serper), builds brand strategy, visual identity, SEO keyword map → `outputs/brand_guide.md`. Refreshes every 7 days. |
| **2 — Launch Executor** | `scripts/etsy_launch_executor.py` | Reads brand guide, generates Etsy listing content (titles, tags, descriptions) via Anthropic API → `outputs/master.txt` |
| **2 (rich) — Autonomous Engine** | `scripts/etsy_autonomous.py` | Same as Phase 2 but generates richer 4-part listing content with positioning, features, and CTA |
| **Canva MCP** | Claude Code + Canva API | Reads brand guide → generates 6 competitive mockup images per product (Before/After hero, features, preview, how-it-works, social proof, bundle value stack) → saves to named Canva folder → exports as JPGs |
| **Canva Watcher** | `scripts/canva_watcher.py` | Monitors `03_Canva_Exports/` (synced from Google Drive). When a folder has 5+ images + `meta.json`, moves mockups to `02_Products/` and adds product to queue automatically |
| **Meta Generator** | `scripts/meta_generator.py` | Parses `outputs/master.txt` to extract listing content for one product and writes `meta.json` to the product's Google Drive folder |
| **4.1 — Image Processor** | `scripts/image_processor.py` | Resizes mockup images to 2000×2000 JPEG at quality 92 |
| **4.2 — Listing Builder** | `scripts/listing_builder.py` | Reads queue row from SQLite, assembles `listing.json` payload |
| **4.3 — Validator** | `scripts/pre_upload_validator.py` | Validates title ≤140 chars, exactly 13 tags, price range, ≥5 mockups |
| **4.5 — File Organizer** | `scripts/file_organizer.py` | Stages files to `04_Assets/ReadyToUpload/`, archives after publish |
| **5 — Etsy Uploader** | `scripts/etsy_uploader.py` | Playwright headless Chromium fills and submits listing to Etsy Seller Dashboard using saved session |
| **6 — SEO Analyzer** | `scripts/seo_analyzer.py` | Calls Etsy API for published tags, fetches competitor listings, writes gap report to SQLite |
| **7 — Health Dashboard** | `scripts/health_dashboard.py` | Published count, failure rate, stuck queue items |
| **Email Digest** | `scripts/email_digest.py` | Sends daily HTML email with product list, brand brief, and pipeline health stats |
| **Etsy Login** | `scripts/etsy_login.py` | One-time Mac-only setup — opens headed Chrome for manual Etsy login, saves session to `.playwright_profile/` |

---

## Project Structure

```
ai-etsy-product-pipeline/
│
├── .env.example                # Credentials template — copy to .env, never commit .env
├── .gitignore
├── .pre-commit-config.yaml     # gitleaks secret scan on every commit
├── run.sh                      # VPS entry point for all phases
├── loop.sh                     # Autonomous loop — runs full cycles on interval
├── setup_vps.sh                # One-time VPS bootstrap script
├── setup_rclone.sh             # Google Drive → VPS sync setup (rclone)
├── etsy-pipeline.service       # systemd unit for auto-restart on boot
├── requirements.txt
│
├── prompts/
│   └── master.txt              # Header template for outputs/master.txt
│
├── scripts/
│   ├── common.py               # Shared utilities (call_with_retry, load_state, etc.)
│   ├── db.py                   # SQLite schema + all DB helpers
│   ├── etsy_brand_crew.py      # Phase 1 — CrewAI brand builder
│   ├── etsy_launch_executor.py # Phase 2 — Listing content generator
│   ├── etsy_autonomous.py      # Phase 2 alt — Richer listing content engine
│   ├── etsy_login.py           # One-time Etsy session setup (Mac only)
│   ├── canva_watcher.py        # Auto-detects synced Google Drive folders → queues products
│   ├── meta_generator.py       # Extracts per-product meta.json from master.txt
│   ├── queue_writer.py         # Manual queue entry (interactive or batch JSON)
│   ├── image_processor.py      # Phase 4.1 — Mockup resize to 2000×2000 JPEG
│   ├── listing_builder.py      # Phase 4.2 — Build listing.json from queue
│   ├── pre_upload_validator.py # Phase 4.3 — Pre-upload validation
│   ├── file_organizer.py       # Phase 4.5 — Stage and archive files
│   ├── etsy_uploader.py        # Phase 5 — Playwright headless uploader
│   ├── seo_analyzer.py         # Phase 6 — Post-publish SEO gap analysis
│   ├── health_dashboard.py     # Phase 7 — Daily health report
│   └── email_digest.py         # Daily HTML email digest via Gmail SMTP
│
├── 02_Products/                # Product source files and mockups
│   └── [ProductName]/
│       └── Mockups/            # Raw mockup images (PNG/JPG/WEBP)
├── 03_Canva_Exports/           # Synced from Google Drive via rclone
│   └── [ProductName]/
│       ├── *.jpg               # 5 Canva mockup exports
│       └── meta.json           # Generated by meta_generator.py
├── 04_Assets/
│   ├── ReadyToUpload/          # Staged files awaiting Playwright upload
│   └── Archived/               # Published listings moved here post-upload
│
├── outputs/                    # Runtime-generated files (git-ignored)
│   ├── brand_guide.md
│   ├── master.txt
│   ├── week_log.md
│   ├── executor_state.json
│   ├── feedback_report.md
│   └── pipeline.db             # SQLite database
│
└── logs/                       # Autonomous loop logs (git-ignored)
    ├── loop.log                # All stdout/stderr from loop.sh
    ├── loop_errors.log         # Failures only
    ├── rclone.log              # Google Drive sync log
    └── loop.pid                # Process ID for clean kill
```

---

## Requirements

- Python 3.12+
- [Anthropic API key](https://platform.claude.com/settings/keys) — brand building and listing content generation
- [Serper API key](https://serper.dev) — live market research in Phase 1
- [Etsy API key](https://www.etsy.com/developers) — SEO analysis in Phase 6
- Gmail account with [App Password](https://myaccount.google.com/apppasswords) — daily email digest
- Hostinger KVM 2 VPS (or any Ubuntu 24.04 LTS server)
- Google Drive or Dropbox — mockup delivery to VPS
- [Canva account](https://canva.com) + Canva MCP connected to Claude Code — AI mockup generation

---

## VPS Deployment

### 1. Clone and bootstrap

```bash
cd /root
git clone https://github.com/khancam15/ai-etsy-product-pipeline.git
cd ai-etsy-product-pipeline
chmod +x setup_vps.sh && ./setup_vps.sh
```

### 2. Configure credentials

```bash
nano .env
```

```
ANTHROPIC_API_KEY=your_key_here
SERPER_API_KEY=your_key_here
ETSY_API_KEY=your_key_here
CREWAI_TRACING_ENABLED=false

EMAIL_TO=your_email@gmail.com
EMAIL_FROM=your_gmail@gmail.com
EMAIL_SMTP_PASS=your_gmail_app_password
```

### 3. Initialise the database

```bash
./run.sh db-init
```

### 4. Set up Google Drive sync (rclone)

Authorise rclone on your Mac first (requires a browser):

```bash
# On your Mac
rclone authorize "drive"
# Copy the token that appears
```

Then configure on the VPS:

```bash
./setup_rclone.sh install
./setup_rclone.sh config    # paste the token when prompted
./setup_rclone.sh sync      # test sync
./setup_rclone.sh cron      # install 5-minute auto-sync
```

### 5. Log into Etsy — one-time Mac setup

The uploader uses a persistent Playwright browser profile. Log in once on your Mac, then copy the session to the VPS.

```bash
# On your Mac (💻 HOST)
python scripts/etsy_login.py
# Log into Etsy in the browser that opens, then press ENTER

# Copy session to VPS
scp -r .playwright_profile/ root@YOUR_VPS_IP:/root/ai-etsy-product-pipeline/
```

### 6. Install systemd service

```bash
cp etsy-pipeline.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable etsy-pipeline
systemctl start etsy-pipeline
```

Verify:
```bash
systemctl status etsy-pipeline
tail -f logs/loop.log
```

---

## Autonomous Loop

Each cycle runs automatically every hour:

1. **Email digest** — sends once per calendar day
2. **Canva watcher** — scans `03_Canva_Exports/` for new synced products
3. **Phase 1** — brand guide (skipped if less than 7 days old)
4. **Phase 2** — generate listing content → `outputs/master.txt`
5. **Pick next queued product** — `pending` status from SQLite
6. **Phase 4** — resize images → build listing → validate → stage
7. **Phase 5** — upload to Etsy via headless Chromium
8. **Phase 6** — SEO gap analysis (non-fatal)
9. **Phase 7** — health dashboard

Exit code handling: each phase must exit 0 before the next runs. A failure halts that cycle and waits for the next scheduled run.

### Manual control

```bash
systemctl start etsy-pipeline        # start
systemctl stop etsy-pipeline         # stop
systemctl restart etsy-pipeline      # restart
tail -f logs/loop.log                # watch live
tail -f logs/loop_errors.log         # failures only
```

### One-off commands

```bash
./loop.sh --once                     # run one cycle and exit (testing)
./run.sh phase1                      # brand builder only
./run.sh phase2                      # listing generator only
./run.sh phase4 "ProductName"        # process + stage one product
./run.sh phase5 "ProductName"        # upload one product to Etsy
./run.sh full "ProductName"          # phases 4 → 5 → 6 for one product
./run.sh digest                      # send email digest now
./run.sh watch                       # run canva watcher once
```

---

## Your Ongoing Workflow

After initial setup, your only recurring task is a 3-step review loop:

### Step 1 — Ask Claude to generate mockups

Open Claude Code and say:
> "Generate mockups for [Product Name]"

Claude will:
- Read your `outputs/brand_guide.md` for brand colors, fonts, and positioning
- Generate 4 design variations for each of the 6 image slots via Canva MCP
- Auto-pick the richest layout for each slot based on thumbnail complexity
- Save all 6 to a named folder in your Canva account

### Step 2 — Review and export from Canva

- Open the folder link Claude gives you
- Tweak any text or colors in Canva if needed (fully editable)
- Download all 6 as JPGs

### Step 3 — Drop into Google Drive

Drop the 6 JPGs into your Google Drive folder named exactly after the product.

The pipeline does the rest automatically:
- rclone syncs to VPS within 5 minutes
- Canva watcher detects the folder and queues the product
- Images are resized, listing is built and validated, then uploaded to Etsy
- SEO analysis runs post-publish
- Daily email digest keeps you updated

---

### Generating meta.json for a product

After Phase 2 runs, generate listing metadata before dropping your images:

```bash
./run.sh meta "Product Name" --price 9.99
```

This writes `03_Canva_Exports/[ProductName]/meta.json` on the VPS so the watcher has everything it needs the moment your images land.

To see all products Phase 2 generated:

```bash
.venv/bin/python scripts/meta_generator.py --list
```

### Canva MCP — image generation reference

Each product gets 6 images built from Etsy conversion data:

```
Image 1 — Before/After hero     (highest CTR format — 30% of top sellers)
Image 2 — Features + price anchor  ("Designer cost $200+ vs your $9.99")
Image 3 — Filled-in preview     (buyers see exactly what they're buying)
Image 4 — How it works          ("Ready in 30 minutes" — removes friction)
Image 5 — Testimonial + badges  (specific outcome + Beginner Friendly badge)
Image 6 — Bundle value stack    ($188 total value → your price anchoring)
```

Requires: Claude Code with Canva MCP connected and a Canva brand kit configured.

---

## Database Schema

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `queue` | Products waiting to be processed | `id`, `product_name`, `status` (pending → published/failed), `title`, `tags` (JSON), `description`, `price`, `category` |
| `listings` | Published Etsy listings | `product_name`, `title` (unique), `etsy_url`, `published_at` |
| `run_log` | Per-phase execution log | `product_name`, `phase`, `status` (success/failed), `message`, `run_at` |
| `seo_review` | Post-publish SEO gap reports | `product_name`, `listing_title`, `missing_tags` (JSON), `gap_count`, `reviewed_at` |

---

## Security

| Protection | How |
|-----------|-----|
| API keys never committed | `.env` is git-ignored; only `.env.example` is tracked |
| Secret scanning on every commit | `gitleaks` via pre-commit hook |
| Runtime outputs git-ignored | `outputs/*`, `logs/*`, `.playwright_profile/` all excluded |
| No hardcoded credentials | All secrets loaded via `python-dotenv` |
| Playwright session isolated | Browser profile stored in `.playwright_profile/` (git-ignored) |
| Exit codes enforce order | Each phase must exit 0 before proceeding |

---

## Troubleshooting

### Loop not running after VPS reboot

```bash
systemctl status etsy-pipeline
systemctl start etsy-pipeline
```

### Phase fails mid-cycle

```bash
tail -f logs/loop_errors.log
```

Phases 6 and 7 are non-fatal — listing is already published if Phase 5 succeeded.

### Etsy login session expired

```bash
# On your Mac (💻 HOST)
python scripts/etsy_login.py
scp -r .playwright_profile/ root@YOUR_VPS_IP:/root/ai-etsy-product-pipeline/
systemctl restart etsy-pipeline
```

### No pending products in queue

Either drop images into Google Drive (automated path) or add manually:

```bash
.venv/bin/python scripts/queue_writer.py
```

### Google Drive not syncing

```bash
rclone sync "etsy-pipeline:YourFolderName" 03_Canva_Exports/ --log-level=INFO
crontab -l    # verify cron is installed
```

### Out of API credits

Phase 1 is cached — brand guide refreshes only every 7 days. To force refresh:

```bash
rm outputs/brand_guide.md
./run.sh phase1
```

---

## License

MIT
