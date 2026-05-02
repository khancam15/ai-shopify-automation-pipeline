# AI Etsy Product Pipeline

An end-to-end AI-powered pipeline that researches a niche, builds a full brand identity, processes product mockups, uploads listings to Etsy via headless Chromium, and runs daily SEO and health monitoring — fully autonomous on a VPS with systemd.

---

## Pipeline Overview

| Phase | Script | What happens | Logs to DB |
|-------|--------|-------------|-----------|
| **0 — VPS Setup** | `setup_vps.sh` | One-time bootstrap: creates directories, installs venv, Playwright Chromium, and initialises the database | ✗ |
| **Foundation** | `scripts/db.py` | Initialises SQLite with 4 tables: `queue`, `listings`, `run_log`, `seo_review` | ✗ |
| **1 — Brand Build** | `scripts/etsy_brand_crew.py` | 6-agent CrewAI crew runs live market research (Serper), builds brand strategy, visual identity, SEO copy → `outputs/brand_guide.md` | ✗ |
| **2 — Launch Executor** | `scripts/etsy_launch_executor.py` | Reads brand guide, extracts 30-day checklist, writes weekly Claude prompts → `outputs/master.txt` | ✗ |
| **2 (alt) — Autonomous Engine** | `scripts/etsy_autonomous.py` | Richer prompt engine with completion checklists for Claude Chrome extension execution | ✗ |
| **3 — Queue Writer** | `scripts/queue_writer.py` | Adds products to the SQLite queue with title, tags, description, price, category — manual or batch JSON mode | ✗ |
| **4.1 — Image Processor** | `scripts/image_processor.py` | Resizes mockup images to 2000×2000 JPEG at quality 92 | ✓ |
| **4.2 — Listing Builder** | `scripts/listing_builder.py` | Reads queue row from SQLite, assembles `listing.json` payload | ✓ |
| **4.3 — Validator** | `scripts/pre_upload_validator.py` | Validates title ≤140 chars, exactly 13 tags, price range, ≥5 mockups — exits 0/1 for n8n routing | ✓ |
| **4.5 — File Organizer** | `scripts/file_organizer.py` | Stages files to `04_Assets/ReadyToUpload/`, archives after publish | ✓ |
| **5 — Etsy Uploader** | `scripts/etsy_uploader.py` | Playwright headless Chromium fills and submits listing to Etsy Seller Dashboard, captures listing URL | ✓ |
| **6 — SEO Analyzer** | `scripts/seo_analyzer.py` | Calls Etsy API for published tags, fetches top 5 competitor listings, writes gap report to SQLite | ✓ |
| **7 — Health Dashboard** | `scripts/health_dashboard.py` | Daily health report: published count, failure rate, stuck queue items — stdout captured by n8n | ✗ |

---

## Project Structure

```
ai-etsy-product-pipeline/
│
├── .env.example                # Credentials template — copy to .env, never commit .env
├── .gitignore
├── .pre-commit-config.yaml     # gitleaks secret scan on every commit
├── run.sh                       # VPS entry point for all phases
├── loop.sh                      # Autonomous loop — runs full cycles on interval
├── setup_vps.sh                 # One-time VPS bootstrap script
├── etsy-pipeline.service        # systemd unit for auto-restart on boot
├── requirements.txt
├── pyproject.toml
│
├── config/
│   └── .gitleaks.toml
│
├── prompts/
│   └── master.txt               # Tracked master launch prompt template
│
├── scripts/
│   ├── common.py                # Shared utilities (call_with_retry, load_state, etc.)
│   ├── db.py                    # SQLite schema + all DB helpers
│   ├── etsy_brand_crew.py       # Phase 1 — CrewAI brand builder
│   ├── etsy_launch_executor.py  # Phase 2 — Launch prompt executor
│   ├── etsy_autonomous.py       # Phase 2 alt — Autonomous prompt engine
│   ├── etsy_login.py            # One-time Etsy session setup via Playwright
│   ├── queue_writer.py          # Phase 3 bridge — add products to queue
│   ├── image_processor.py       # Phase 4.1 — Mockup resize to 2000×2000 JPEG
│   ├── listing_builder.py       # Phase 4.2 — Build listing.json from queue
│   ├── pre_upload_validator.py  # Phase 4.3 — Pre-upload validation
│   ├── file_organizer.py        # Phase 4.5 — Stage and archive files
│   ├── etsy_uploader.py         # Phase 5 — Playwright headless uploader
│   ├── seo_analyzer.py          # Phase 6 — Post-publish SEO gap analysis
│   └── health_dashboard.py      # Phase 7 — Daily health report
│
├── 01_Queue/                    # Incoming product queue (CSV or manual)
├── 02_Products/                 # Product source files and mockups
│   └── [ProductName]/
│       └── Mockups/             # Raw mockup images (PNG/JPG/WEBP)
├── 03_Canva_Exports/            # Canva design exports before processing
├── 04_Assets/
│   ├── ReadyToUpload/           # Staged files awaiting Playwright upload
│   │   └── [ProductName]/
│   │       ├── listing.json
│   │       └── *.jpg
│   └── Archived/                # Published listings moved here post-upload
│
├── outputs/                     # Runtime-generated files (git-ignored)
│   ├── brand_guide.md
│   ├── master.txt
│   ├── week_log.md
│   ├── executor_state.json
│   ├── feedback_report.md
│   ├── pipeline.db              # SQLite database
│   └── cron.log
│
└── logs/                        # Autonomous loop logs (git-ignored)
    ├── loop.log                 # all stdout/stderr from loop.sh
    ├── loop_errors.log          # failures only
    └── loop.pid                 # process ID for clean kill
```

---

## Requirements

- Python 3.12+
- [Anthropic API key](https://platform.claude.com/settings/keys) — brand building and prompt generation
- [Serper API key](https://serper.dev) — live market research in Phase 1
- [Etsy API key](https://www.etsy.com/developers) — SEO analysis in Phase 6
- Hostinger KVM 2 VPS (or any Ubuntu 24.04 LTS server)

---

## VPS Deployment (Hostinger KVM 2)

### 1. Clone and bootstrap (first time only)

```bash
cd /root
git clone https://github.com/khancam15/ai-etsy-product-pipeline.git
cd ai-etsy-product-pipeline
chmod +x setup_vps.sh && ./setup_vps.sh
```

This creates:
- All required directories (`01_Queue/`, `02_Products/`, `03_Canva_Exports/`, `04_Assets/`, `outputs/`, `logs/`)
- Python 3.12 virtual environment in `.venv`
- Playwright Chromium with system dependencies
- SQLite database at `outputs/pipeline.db`

### 2. Configure API keys

```bash
nano .env
```

Fill in:

```
ANTHROPIC_API_KEY=your_key_here
SERPER_API_KEY=your_key_here
ETSY_API_KEY=your_key_here
CREWAI_TRACING_ENABLED=false
```

### 3. Log into Etsy (one-time setup)

The uploader uses a persistent Playwright browser profile that saves your Etsy session. You need to log in once on a machine with a display:

**On your Mac (has display):**
```bash
python scripts/etsy_login.py
```

This opens a headed browser window. Log into Etsy, then press ENTER in the terminal to save the session.

**Copy to VPS:**
```bash
scp -r .playwright_profile/ root@YOUR_VPS_IP:/root/ai-etsy-product-pipeline/
```

After this, all headless uploads will stay logged in.

### 4. Install systemd service (auto-restart on boot)

The `etsy-pipeline.service` file ensures the loop keeps running even after VPS reboots:

```bash
cp etsy-pipeline.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable etsy-pipeline
systemctl start etsy-pipeline
```

Verify it's running:
```bash
systemctl status etsy-pipeline
tail -f logs/loop.log
```

---

## Autonomous Loop Workflow

The pipeline runs continuously on a timer (default: 1 hour between cycles). Each cycle:

1. **Phase 1** — Brand guide (skipped if <7 days old to save API credits)
2. **Phase 2** — Generate launch copy and add products to queue
3. **Pick next product** from queue with `pending` status
4. **Phase 4** — Process images, build listing, validate, stage
5. **Phase 5** — Upload to Etsy
6. **Phase 6** — SEO analysis (non-fatal if fails)
7. **Phase 7** — Health report

**Exit code handling:** Each phase must exit 0 before the next runs. Any failure halts that cycle and waits for the next scheduled cycle.

### Manual control

```bash
# Start the loop
systemctl start etsy-pipeline

# Watch it live
tail -f logs/loop.log

# Stop it
systemctl stop etsy-pipeline

# Restart with latest code
cd /root/ai-etsy-product-pipeline && git pull origin main
systemctl restart etsy-pipeline

# Check status
systemctl status etsy-pipeline
```

### Alternative: Run without systemd

```bash
# Test one cycle without sleeping
./loop.sh --once

# Run forever in background (survives SSH disconnect but not reboot)
nohup ./loop.sh >> logs/loop.log 2>&1 &

# Watch it
tail -f logs/loop.log

# Stop it
kill $(cat logs/loop.pid)
```

**Note:** `nohup` keeps the process alive through SSH disconnect but not through VPS reboots. Use systemd for production.

---

## Adding Products to the Queue

Products must be added to the SQLite queue before Phase 4 processes them. Use `queue_writer.py`:

### Interactive mode

```bash
python scripts/queue_writer.py
```

Prompts for: product_name, title, tags (comma-separated, exactly 13), description, price, category.

### Batch mode (JSON file)

```bash
cat > products.json <<'EOF'
[
  {
    "product_name": "UGC Creator Rate Card",
    "title": "UGC Creator Rate Card Template | Editable Canva | Freelance Pricing Sheet",
    "tags": ["ugc creator", "rate card template", "canva template", "freelance pricing", "pricing guide", "rate sheet", "editable template", "freelance designer", "business template", "coaching tool", "digital download", "freelance tool", "pricing template"],
    "description": "Ready-to-edit rate card template for UGC creators to showcase pricing...",
    "price": 7.99,
    "category": "Digital Downloads"
  }
]
EOF

python scripts/queue_writer.py --file products.json
```

### List queue

```bash
python scripts/queue_writer.py --list
```

---

## Manual Phase-by-Phase Execution

For debugging or custom workflows:

```bash
./run.sh db-init                     # initialise database (once)
./run.sh phase1                      # brand builder
./run.sh phase2                      # launch executor
./run.sh phase4 "ProductName"        # process images → build listing → validate → stage
./run.sh phase5 "ProductName"        # upload to Etsy
./run.sh phase6 "ProductName"        # SEO gap analysis
./run.sh phase7                      # health dashboard
./run.sh full "ProductName"          # phases 4 → 5 → 6 in one command
```

---

## Chrome Extension Integration

Use `etsy_autonomous.py` to generate structured 4-part prompts for the Claude Chrome extension:

```bash
./run.sh phase2-rich
```

Outputs to `outputs/master.txt` — each prompt includes:
1. Goal and context
2. Step-by-step browser actions
3. Safety constraints
4. Done checklist with proof items

Copy/paste each week's prompt into the Claude Chrome extension to execute the launch plan manually or via Claude Copilot.

---

## Local Development Setup

```bash
git clone https://github.com/khancam15/ai-etsy-product-pipeline.git
cd ai-etsy-product-pipeline

python3.12 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
pip install pre-commit
pre-commit install

cp .env.example .env
# fill in your API keys
```

Then run manually:
```bash
./run.sh phase1
./run.sh phase2
```

Or start the loop:
```bash
./loop.sh
```

---

## Database Schema

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `queue` | Products waiting to be processed | `id`, `product_name`, `status` (pending → designed → published/failed), `title`, `tags` (JSON), `description`, `price`, `category` |
| `listings` | Published Etsy listings (dedup index) | `product_name`, `title` (unique), `etsy_url`, `published_at` |
| `run_log` | Per-phase execution log | `product_name`, `phase`, `status` (success/failed), `message`, `run_at` |
| `seo_review` | Post-publish SEO gap reports | `product_name`, `listing_title`, `missing_tags` (JSON), `gap_count`, `reviewed_at` |

---

## Security

| Protection | How |
|-----------|-----|
| API keys never committed | `.env` is git-ignored; only `.env.example` is tracked |
| Secret scanning on every commit | `gitleaks` via pre-commit hook |
| Runtime outputs git-ignored | `outputs/*`, `logs/*`, `.playwright_profile/` all excluded from git |
| No hardcoded credentials | All secrets loaded via `python-dotenv` with absolute path |
| Playwright session isolated | Browser profile stored in `.playwright_profile/` (git-ignored) |
| Exit codes enforce safety | Each phase must exit 0 before proceeding — prevents cascading failures |

---

## Troubleshooting

### Loop not running after VPS reboot

Check systemd:
```bash
systemctl status etsy-pipeline
journalctl -u etsy-pipeline -n 50
```

If not running:
```bash
systemctl start etsy-pipeline
```

### Phase fails but loop keeps going

Check `logs/loop_errors.log`:
```bash
tail -f logs/loop_errors.log
```

Phases 6 and 7 (SEO and health) are non-fatal — listing already published.

### Etsy login expired

`.playwright_profile/` session expires over time. Re-run:
```bash
python scripts/etsy_login.py
scp -r .playwright_profile/ root@YOUR_VPS_IP:/root/ai-etsy-product-pipeline/
systemctl restart etsy-pipeline
```

### No pending products in queue

Add products manually:
```bash
python scripts/queue_writer.py
```

Or in batch:
```bash
python scripts/queue_writer.py --file products.json
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
