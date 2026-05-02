# AI Etsy Product Pipeline

An end-to-end AI-powered pipeline that researches a niche, builds a full brand identity, processes product mockups, uploads listings to Etsy via headless Chromium, and runs daily SEO and health monitoring — fully autonomous on a VPS.

---

## Pipeline Overview

| Phase | Script | What happens |
|-------|--------|-------------|
| **0 — VPS Setup** | `setup_vps.sh` | One-time bootstrap: creates directories, installs venv, Playwright Chromium, and initialises the database |
| **Foundation** | `scripts/db.py` | Initialises SQLite with 4 tables: `queue`, `listings`, `run_log`, `seo_review` |
| **1 — Brand Build** | `scripts/etsy_brand_crew.py` | 6-agent CrewAI crew runs live market research (Serper), builds brand strategy, visual identity, SEO copy → `outputs/brand_guide.md` |
| **2 — Launch Executor** | `scripts/etsy_launch_executor.py` | Reads brand guide, extracts 30-day checklist, writes weekly Claude prompts → `outputs/master.txt` |
| **2 (alt) — Autonomous Engine** | `scripts/etsy_autonomous.py` | Richer prompt engine with completion checklists for Claude Chrome extension execution |
| **4.1 — Image Processor** | `scripts/image_processor.py` | Resizes mockup images to 2000×2000 JPEG at quality 92 |
| **4.2 — Listing Builder** | `scripts/listing_builder.py` | Reads queue row from SQLite, assembles `listing.json` payload |
| **4.3 — Validator** | `scripts/pre_upload_validator.py` | Validates title ≤140 chars, exactly 13 tags, price range, ≥5 mockups — exits 0/1 for n8n routing |
| **4.5 — File Organizer** | `scripts/file_organizer.py` | Stages files to `04_Assets/ReadyToUpload/`, archives after publish |
| **5 — Etsy Uploader** | `scripts/etsy_uploader.py` | Playwright headless Chromium fills and submits listing to Etsy Seller Dashboard, captures listing URL |
| **6 — SEO Analyzer** | `scripts/seo_analyzer.py` | Calls Etsy API for published tags, fetches top 5 competitor listings, writes gap report to SQLite |
| **7 — Health Dashboard** | `scripts/health_dashboard.py` | Daily health report: published count, failure rate, stuck queue items — stdout captured by n8n |

---

## Project Structure

```
ai-etsy-product-pipeline/
│
├── .env.example              # Credentials template — copy to .env, never commit .env
├── .gitignore
├── .pre-commit-config.yaml   # gitleaks secret scan on every commit
├── run.sh                    # VPS entry point for all phases
├── loop.sh                   # Autonomous loop — runs full cycles on interval
├── setup_vps.sh              # One-time VPS bootstrap script
├── requirements.txt
├── pyproject.toml
│
├── config/
│   └── .gitleaks.toml
│
├── prompts/
│   └── master.txt            # Tracked master launch prompt template
│
├── scripts/
│   ├── db.py                   # SQLite schema + all DB helpers
│   ├── etsy_brand_crew.py      # Phase 1 — CrewAI brand builder
│   ├── etsy_launch_executor.py # Phase 2 — Launch prompt executor
│   ├── etsy_autonomous.py      # Phase 2 alt — Autonomous prompt engine
│   ├── image_processor.py      # Phase 4.1 — Mockup resize to 2000×2000 JPEG
│   ├── listing_builder.py      # Phase 4.2 — Build listing.json from queue
│   ├── pre_upload_validator.py # Phase 4.3 — Pre-upload validation
│   ├── file_organizer.py       # Phase 4.5 — Stage and archive files
│   ├── etsy_uploader.py        # Phase 5 — Playwright headless uploader
│   ├── seo_analyzer.py         # Phase 6 — Post-publish SEO gap analysis
│   └── health_dashboard.py     # Phase 7 — Daily health report
│
├── 01_Queue/                 # Incoming product queue (CSV or manual)
├── 02_Products/              # Product source files and mockups
│   └── [ProductName]/
│       └── Mockups/          # Raw mockup images (PNG/JPG/WEBP)
├── 03_Canva_Exports/         # Canva design exports before processing
├── 04_Assets/
│   ├── ReadyToUpload/        # Staged files awaiting Playwright upload
│   │   └── [ProductName]/
│   │       ├── listing.json
│   │       └── *.jpg
│   └── Archived/             # Published listings moved here post-upload
│
└── outputs/                  # Runtime-generated files (git-ignored)
    ├── brand_guide.md
    ├── master.txt
    ├── week_log.md
    ├── executor_state.json
    └── cron.log

└── logs/                     # Autonomous loop logs (git-ignored)
    ├── loop.log              # all stdout/stderr
    ├── loop_errors.log       # failures only
    └── loop.pid              # process ID for clean kill
```

---

## Requirements

- Python 3.12+
- [Anthropic API key](https://platform.claude.com/settings/keys)
- [Serper API key](https://serper.dev) — live market research in Phase 1
- [Etsy API key](https://www.etsy.com/developers) — SEO analysis in Phase 6

---

## VPS Deployment (Hostinger KVM 2)

### First-time setup

```bash
git clone https://github.com/khancam15/ai-etsy-product-pipeline.git
cd ai-etsy-product-pipeline
chmod +x setup_vps.sh && ./setup_vps.sh
```

Then fill in your API keys:

```bash
nano .env
```

```
ANTHROPIC_API_KEY=your_key_here
SERPER_API_KEY=your_key_here
ETSY_API_KEY=your_key_here
CREWAI_TRACING_ENABLED=false
```

### Log into Etsy (one-time)

The uploader uses a persistent Playwright browser profile that saves your Etsy session. You need to log in once before running Phase 5:

```bash
python scripts/etsy_login.py
```

This opens a headed browser, lets you log into Etsy, and saves the session to `.playwright_profile/`. After this, all headless uploads will stay logged in.

---

Create `/etc/systemd/system/etsy-pipeline.service`:

```ini
[Unit]
Description=Etsy Pipeline Autonomous Loop
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai-etsy-product-pipeline
ExecStart=/root/ai-etsy-product-pipeline/loop.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
systemctl daemon-reload
systemctl enable etsy-pipeline
systemctl start etsy-pipeline
systemctl status etsy-pipeline
```

---

### Pulling updates to VPS

```bash
cd /root/ai-etsy-product-pipeline
git pull origin main
systemctl restart etsy-pipeline
```

---

## Quick Start

### Option A: Autonomous Loop (Recommended)

Run the full pipeline continuously on a schedule (default: every 1 hour):

```bash
# Run forever in background
nohup ./loop.sh >> logs/loop.log 2>&1 &

# Or test one cycle without sleeping
./loop.sh --once

# Watch it live
tail -f logs/loop.log

# Stop it cleanly
kill $(cat logs/loop.pid)
```

**How it works:**
- Every cycle: Phase 1 (brand, skipped if <7 days old) → Phase 2 (copy) → Phase 4–7 (process, upload, SEO)
- Checks exit code of each phase before proceeding — any failure halts that cycle
- Phase 6 (SEO) and 7 (health) are non-fatal — listing already published
- Logs everything to `logs/loop.log`, errors to `logs/loop_errors.log`
- Sleep interval: 3600s (default) or override with `SLEEP=7200 ./loop.sh`

### Option B: Manual Phase-by-Phase

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

Copy/paste each week's prompt into the extension to execute the launch plan manually or via Copilot.

---

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

---

## Database Schema

| Table | Purpose |
|-------|---------|
| `queue` | Products waiting to be processed — status: `pending → designed → published / failed` |
| `listings` | Published Etsy listings with URL and timestamp |
| `run_log` | Per-phase execution log with status, message, and timing |
| `seo_review` | Post-publish SEO gap reports: missing tags vs competitors |

---

## Security

| Protection | How |
|-----------|-----|
| API keys never committed | `.env` is git-ignored; only `.env.example` is tracked |
| Secret scanning on every commit | `gitleaks` via pre-commit hook |
| Runtime outputs git-ignored | `outputs/*` excluded except `.gitkeep` |
| No hardcoded credentials | All secrets loaded via `python-dotenv` with absolute path |
| Playwright session isolated | Browser profile stored in `.playwright_profile/` (git-ignored) |

---

## License

MIT
