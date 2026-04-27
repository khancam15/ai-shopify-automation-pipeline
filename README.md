# Etsy Digital Product Pipeline

An end-to-end AI-powered pipeline that researches a niche, builds a full brand identity, and autonomously executes a 30-day Etsy store launch — driven by Claude AI, CrewAI, and Python automation.

---

## What It Does

| Phase | Script | What happens |
|-------|--------|-------------|
| **1 — Brand Build** | `scripts/etsy_brand_crew.py` | A 5-agent CrewAI crew runs live market research (via Serper), defines brand strategy, visual identity, SEO copy, and writes a complete `outputs/brand_guide.md` |
| **2 — Launch Execution** | `scripts/etsy_launch_executor.py` | Reads `outputs/brand_guide.md`, extracts the 30-day checklist, and dispatches per-week Claude agents that generate step-by-step "Claude in Chrome" prompts for each task |
| **2 (alt) — Autonomous** | `scripts/etsy_autonomous.py` | Same as above but uses Claude computer-use beta to execute tasks fully autonomously via browser control |

---

## Project Structure

```
etsybot/
├── .config/
│   └── .gitleaks.toml        # Hidden gitleaks configuration
├── .env.example              # Credential template (copy to .env)
├── .gitignore                # Protects secrets, outputs, venv, history
├── .pre-commit-config.yaml   # gitleaks secret scanning on every commit
├── README.md                 # Project overview and usage
├── scripts/
│   ├── etsy_brand_crew.py    # Phase 1 — CrewAI brand builder (5 agents)
│   ├── etsy_launch_executor.py # Phase 2 — Weekly executor with Claude prompts
│   └── etsy_autonomous.py    # Phase 2 (alt) — Autonomous computer-use executor
└── outputs/
    ├── brand_guide.md        # Generated brand guide (git-ignored)
    ├── week_log.md           # Execution log per task (git-ignored)
    ├── feedback_report.md    # Week 4 tag performance analysis (git-ignored)
    └── executor_state.json   # Resumable run state (git-ignored)
```

---

## Niche & Brand (default config)

> **Niche:** Notion productivity templates for freelancers  
> **Store:** The Freelance Command Center  
> **Positioning:** Unified Notion templates helping independent freelancers track income, manage clients, and prepare taxes.

To run on a different niche, change the `NICHE` constant at the top of `scripts/etsy_brand_crew.py`.

---

## Requirements

- Python 3.11+
- An [Anthropic API key](https://platform.claude.com/settings/keys)
- A [Serper API key](https://serper.dev) (for live market research in Phase 1)

```bash
pip install anthropic crewai crewai-tools python-dotenv rich pre-commit
```

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/khancam15/etsy-digital-product-pipeline.git
cd etsy-digital-product-pipeline

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install anthropic crewai crewai-tools python-dotenv rich pre-commit

# 4. Configure credentials
cp .env.example .env
# Edit .env and fill in your ANTHROPIC_API_KEY and SERPER_API_KEY

# 5. Enable secret scanning (blocks accidental key commits)
pre-commit install
```

---

## Usage

### Phase 1 — Generate Brand Guide

```bash
python scripts/etsy_brand_crew.py
```

Runs live research and writes `outputs/brand_guide.md`. Takes ~3–8 minutes depending on API speed.

### Phase 2 — Execute Launch (prompt-assisted)

```bash
python scripts/etsy_launch_executor.py
```

Reads `outputs/brand_guide.md` and prints a "Claude in Chrome" prompt for each task. Paste each prompt into Claude in Chrome to execute in your browser.

### Phase 2 (alt) — Execute Launch (fully autonomous)

```bash
python scripts/etsy_autonomous.py
```

Uses Claude computer-use beta to drive the browser autonomously. Requires the [Anthropic computer-use Docker image](https://github.com/anthropics/anthropic-quickstarts).

> **Safety note:** The autonomous executor will never click Publish or Purchase without explicit user confirmation.

---

## Security

| Protection | How |
|-----------|-----|
| API keys never committed | `.env` and `.env.*` are git-ignored |
| Secret scanning | `gitleaks` runs on every `git commit` via pre-commit hook |
| Generated outputs git-ignored | `outputs/`, `executor_state.json`, `history_list.txt` never tracked |
| Env template provided | `.env.example` shows required keys with placeholder values |

---

## License

MIT
