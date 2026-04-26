# Walkthrough — Etsy Digital Product Pipeline

A step-by-step guide to running the full pipeline from a blank slate to an active Etsy store launch.

---

## Overview

The pipeline has two phases:

```
Phase 1: etsy_brand_crew.py
  └── 5 AI agents do market research → strategy → visuals → copy → launch plan
  └── Writes outputs/brand_guide.md

Phase 2: etsy_launch_executor.py  (or etsy_autonomous.py)
  └── Reads brand_guide.md
  └── Extracts 30-day task checklist (4 weeks)
  └── Executes tasks week-by-week via Claude
```

---

## Prerequisites

Before you start, you need:

- [ ] Python 3.11+ installed (`python3 --version`)
- [ ] An Anthropic API key → [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys)
- [ ] A Serper API key → [serper.dev](https://serper.dev) (free tier: 2,500 searches/month)
- [ ] A virtual environment set up (see below)

---

## Step 1 — Clone and Install

```bash
git clone https://github.com/khancam15/etsy-digital-product-pipeline.git
cd etsy-digital-product-pipeline

python3 -m venv venv
source venv/bin/activate

pip install anthropic crewai crewai-tools python-dotenv rich pre-commit
```

---

## Step 2 — Configure Credentials

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
SERPER_API_KEY=your_serper_key_here
```

**Never commit `.env`.** It is already git-ignored. Run `git check-ignore -v .env` to verify.

---

## Step 3 — Enable Secret Scanning

This installs a pre-commit hook that blocks accidental key leaks on every `git commit`:

```bash
pre-commit install
```

To test it manually:

```bash
pre-commit run --all-files
# Expected: Detect hardcoded secrets...Passed
```

---

## Step 4 — Customize Your Niche

Open `etsy_brand_crew.py` and change line 24:

```python
NICHE = "Notion productivity templates for freelancers"   # <-- change this
```

Replace with your niche, e.g.:
- `"Canva social media templates for coaches"`
- `"Printable budget planners for families"`
- `"Digital sticker packs for bullet journaling"`

---

## Step 5 — Run Phase 1: Brand Builder

```bash
python etsy_brand_crew.py
```

What happens:
1. **Market Analyst** searches Etsy for top stores, buyer sentiment, top keywords, and visual trends
2. **Brand Strategist** defines niche, persona, store name, and positioning
3. **Visual Director** recommends colors, fonts, logo concept, and mockup styles
4. **Copy Strategist** writes tagline, tone guide, title formula, SEO tags, and review request
5. **Launch Planner** compiles everything into `outputs/brand_guide.md` + 30-day checklist

**Expected runtime:** 3–8 minutes  
**Output:** `outputs/brand_guide.md`

---

## Step 6 — Run Phase 2: Launch Executor

### Option A — Prompt-assisted (recommended for beginners)

```bash
python etsy_launch_executor.py
```

For each task in the 30-day checklist, the script prints a ready-to-paste prompt like:

```
--- PASTE INTO CLAUDE IN CHROME ---
You are the Week 1 launch agent for The Freelance Command Center...
[full instructions]
---
```

**What you do:**
1. Open Chrome → go to [claude.ai](https://claude.ai) with the Chrome extension enabled
2. Paste the prompt
3. Claude navigates your Etsy/Canva dashboard and completes the task

Progress is saved to `outputs/executor_state.json` after each task — if the run is interrupted, restart the script and it will resume from where it left off.

### Option B — Fully Autonomous (advanced)

```bash
# Requires Docker
docker run \
  -e ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) \
  -v $HOME/.anthropic:/home/user/.anthropic \
  -p 5900:5900 -p 8501:8501 -p 6080:6080 -p 8080:8080 \
  ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest

# In a separate terminal:
python etsy_autonomous.py
```

Claude will control the browser autonomously. It will **pause and ask for confirmation** before:
- Clicking Publish on any Etsy listing
- Clicking any Purchase button
- Encountering a CAPTCHA or 2FA prompt

---

## Week-by-Week Task Overview

| Week | Focus | Key actions |
|------|-------|------------|
| **Week 1** | Storefront setup | Banner, logo, About section, policies, first 3 listings |
| **Week 2** | Listing expansion | Reach 10 listings, A/B test two title formulas |
| **Week 3** | External traffic | Pinterest boards, Instagram grid, first TikTok/Reel |
| **Week 4** | Optimization | Review Etsy Stats, refine tags, respond to all messages |

---

## Outputs Reference

| File | Contents | Git-tracked? |
|------|---------|:---:|
| `outputs/brand_guide.md` | Full brand + launch plan | No |
| `outputs/week_log.md` | Task-by-task execution log | No |
| `outputs/executor_state.json` | Resumable run state | No |
| `outputs/feedback_report.md` | Week 4 tag performance analysis | No |
| `brand_guide.md` (root) | Copy of brand guide for quick access | Yes |

---

## Troubleshooting

**`brand_guide.md not found`**  
→ Run Phase 1 (`etsy_brand_crew.py`) first.

**`ANTHROPIC_API_KEY` error**  
→ Check your `.env` file exists and the key is valid at [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys).

**Task stuck / no output**  
→ Delete `outputs/executor_state.json` and restart to begin from Week 1 again.

**CAPTCHA or login prompt in autonomous mode**  
→ Claude will stop and report it. Log into Etsy/Canva manually, then re-run.

**`pre-commit` blocks a commit**  
→ A secret pattern was detected. Remove the value, use `os.environ["KEY_NAME"]` instead, and re-commit.

---

## Security Checklist

Before pushing to GitHub, verify:

- [ ] `git check-ignore -v .env` returns `.gitignore:2:.env`
- [ ] `pre-commit run --all-files` passes
- [ ] No raw API keys in any `.py` file (`grep -r 'sk-ant-api' *.py` returns nothing)
- [ ] `git ls-files` does not include `outputs/`, `.env`, or `history_list.txt`
