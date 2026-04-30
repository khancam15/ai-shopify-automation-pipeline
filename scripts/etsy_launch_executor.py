"""
etsy_launch_executor.py
────────────────────────
Phase 2 of the Etsy Brand Builder pipeline.

Reads the generated brand guide from Phase 1, extracts the 30-day
checklist, and dispatches four weekly Claude executor agents that run
through prompt generation for the Claude Chrome extension.

Each generated prompt includes:
  - The full brand guide context
  - Its week-specific task list
    - Clear execution constraints for a Claude in Chrome browser session

Week 4 includes a feedback loop prompt: Claude reads Etsy Stats, scores tag
performance, and recommends the next optimization cycle.

Requirements:
    pip install anthropic python-dotenv rich

Run:
    python scripts/etsy_launch_executor.py

Run this from the project root after scripts/etsy_brand_crew.py generates outputs/brand_guide.md
"""

import os
import re
import json
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

load_dotenv()


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise SystemExit(f"[error] {key} is not set. Add it to your .env file.")
    return value


console = Console()
client = anthropic.Anthropic(api_key=_require_env("ANTHROPIC_API_KEY"))

MODEL          = "claude-haiku-4-5-20251001"  # prompt-generation model (fast, cost-efficient)
BRAND_GUIDES   = (Path("outputs/brand_guide.md"), Path("brand_guide.md"))
STATE_FILE     = Path("outputs/executor_state.json")
OUTPUTS_DIR    = Path("outputs")
MASTER_TEMPLATE_FILE = Path("prompts/master.txt")
MASTER_PROMPT_FILE = OUTPUTS_DIR / "master.txt"
OUTPUTS_DIR.mkdir(exist_ok=True)


# ─── STEP 1 — LOAD BRAND GUIDE ───────────────────────────────────────────────

def load_brand_guide() -> str:
    """Read the generated brand guide from disk. Raise clearly if missing."""
    for brand_guide in BRAND_GUIDES:
        if brand_guide.exists():
            return brand_guide.read_text(encoding="utf-8")

    preferred_file = BRAND_GUIDES[0]
    fallback_file = BRAND_GUIDES[1]
    raise FileNotFoundError(
        f"Brand guide not found at {preferred_file.resolve()} or {fallback_file.resolve()}\n"
        "Run etsy_brand_crew.py first to generate it."
    )


# ─── STEP 2 — EXTRACT 30-DAY CHECKLIST ───────────────────────────────────────

def extract_checklist(brand_guide: str) -> dict[str, list[dict]]:
    """
    Parse the four weekly sections from the generated brand guide.
    Returns a dict: {"week_1": [...], "week_2": [...], ...}
    Each item: {"task": str, "tool": str | None, "status": "pending"}
    """
    week_patterns = {
        "week_1": r"Week 1.*?(?=Week 2|$)",
        "week_2": r"Week 2.*?(?=Week 3|$)",
        "week_3": r"Week 3.*?(?=Week 4|$)",
        "week_4": r"Week 4.*?(?=$)",
    }

    checklist: dict[str, list[dict]] = {}

    for week_key, pattern in week_patterns.items():
        section = re.search(pattern, brand_guide, re.DOTALL | re.IGNORECASE)
        if not section:
            checklist[week_key] = []
            continue

        block = section.group(0)

        # Extract numbered items
        items = re.findall(r"\d+\.\s+(.+?)(?=\n\d+\.|\n\n|$)", block, re.DOTALL)
        tool_match = re.search(r"\*Free Tool:\s*(.+?)\*", block)
        tool = tool_match.group(1).strip() if tool_match else None

        checklist[week_key] = [
            {
                "task":   item.strip().replace("**", "").replace("\n", " "),
                "tool":   tool,
                "status": "pending",
            }
            for item in items
        ]

    total = sum(len(v) for v in checklist.values())
    console.print(f"[dim]Extracted {total} tasks across 4 weeks from the generated brand guide[/dim]")
    return checklist


# ─── STEP 3 — STATE PERSISTENCE ───────────────────────────────────────────────

def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_state() -> dict | None:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def initialize_master_prompt_file() -> None:
    """Create or reset outputs/master.txt from prompts/master.txt when available."""
    if MASTER_TEMPLATE_FILE.exists():
        template = MASTER_TEMPLATE_FILE.read_text(encoding="utf-8").rstrip()
        MASTER_PROMPT_FILE.write_text(f"{template}\n\n", encoding="utf-8")
        return

    MASTER_PROMPT_FILE.write_text(
        "# Master Claude Chrome Extension Prompts\n\n"
        "Use this file to execute each weekly launch task in Claude Chrome extension.\n"
        f"Generated: {datetime.now().isoformat()}\n\n",
        encoding="utf-8",
    )


def append_master_prompt(week_label: str, task_number: int, task_text: str, prompt: str) -> None:
    entry = (
        f"## {week_label} · Task {task_number}\n"
        f"Task: {task_text}\n\n"
        f"{prompt}\n\n"
        "---\n\n"
    )
    with open(MASTER_PROMPT_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


# ─── STEP 4 — SINGLE-TASK EXECUTOR ───────────────────────────────────────────

def build_system_prompt(brand_guide: str, week_label: str) -> str:
    return f"""You are an autonomous Etsy store launch agent for the brand "Freelance Flow".

You have full access to a web browser, a text editor, and a bash terminal.
Your job is to complete the assigned task completely and verify success before finishing.

## Brand context (from the generated brand guide)

{brand_guide}

## Operating rules
- You are executing Week: {week_label}
- Use Claude in Chrome to navigate to the correct platform for each task.
- For Canva tasks: go to canva.com, select the relevant template, apply brand colors
  (#B2E0D4 mint, #FFBFA0 peach, #406E8E slate, #F6F5F0 cream, #333333 charcoal),
  use Poppins for headings and Roboto for body text.
- For Etsy tasks: go to etsy.com/your/shops/me/tools and log in if prompted.
  Wait for explicit user confirmation before clicking any purchase or publish button.
- For Pinterest/Instagram tasks: open the platform and create content using brand copy
  extracted directly from the brand guide above.
- After completing each task, briefly confirm what was done and what URL or file was produced.
- If you encounter a CAPTCHA or 2FA prompt, pause and inform the user.
- Never enter payment details, passwords, or personal credentials. Ask the user.
- Log every completed action to: outputs/week_log.md

## Task format
You will receive one task at a time. Complete it fully before returning.
"""


def execute_task(
    task_text: str,
    brand_guide: str,
    week_label: str,
    week_key: str,
) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=f"""You are an Etsy launch assistant for The Freelance Command Center.
Brand guide context:
{brand_guide[:2000]}
Generate a clear step-by-step prompt the user pastes into Claude in Chrome to complete this task.""",
        messages=[{"role": "user", "content": f"Generate a Claude in Chrome prompt for: {task_text}"}],
    )
    result = response.content[0].text
    print(f"\n--- PASTE INTO CLAUDE IN CHROME ---\n{result}\n---\n")
    return result



# ─── STEP 5 — WEEKLY AGENT RUNNERS ────────────────────────────────────────────

WEEK_LABELS = {
    "week_1": "Week 1 — Storefront Setup",
    "week_2": "Week 2 — Listing Expansion",
    "week_3": "Week 3 — External Traffic",
    "week_4": "Week 4 — Optimization",
}


def run_weekly_agent(
    week_key: str,
    tasks: list[dict],
    brand_guide: str,
    state: dict,
) -> list[dict]:
    """
    Run all tasks for a given week sequentially.
    Updates and saves state after each task.
    Returns updated task list.
    """
    label = WEEK_LABELS[week_key]
    console.print(Panel(f"[bold]{label}[/bold]", style="cyan"))

    log_path = OUTPUTS_DIR / "week_log.md"

    for i, item in enumerate(tasks):
        if item["status"] == "completed":
            console.print(f"  [dim]↳ Skipping (already completed): {item['task'][:60]}[/dim]")
            continue

        task_number = i + 1
        console.print(f"\n  [bold cyan]Task {task_number}/{len(tasks)}:[/bold cyan] {item['task'][:70]}")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            progress.add_task(description="Claude executing...", total=None)

            result = execute_task(
                task_text=f"Complete this task now: {item['task']}",
                brand_guide=brand_guide,
                week_label=label,
                week_key=week_key,
            )

        append_master_prompt(
            week_label=label,
            task_number=task_number,
            task_text=item["task"],
            prompt=result,
        )

        # Mark complete and log
        item["status"]    = "completed"
        item["result"]    = result[:500]
        item["completed_at"] = datetime.now().isoformat()

        log_entry = (
            f"\n## {label} · Task {task_number}\n"
            f"**Task:** {item['task']}\n"
            f"**Completed:** {item['completed_at']}\n"
            f"**Result:** {result[:300]}\n"
            f"---\n"
        )
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)

        state["checklist"][week_key] = tasks
        save_state(state)

        console.print(f"  [green]✓[/green] Task {task_number} complete")
        time.sleep(2)  # brief pause between tasks

    return tasks


# ─── STEP 6 — WEEK 4 FEEDBACK LOOP ────────────────────────────────────────────

FEEDBACK_PROMPT = """
You are the Week 4 optimization agent for Freelance Flow on Etsy.

Using the browser, navigate to your Etsy Stats dashboard at:
  https://www.etsy.com/your/shops/me/stats

Do the following:
1. Find the "Search terms" section showing which keywords brought visitors.
2. Find the "Listings" section showing click-through rate per listing.
3. Identify the 3 lowest-performing tags (fewest clicks or impressions).
4. Identify the 3 best-performing tags (most clicks).
5. Suggest 3 replacement tags for the underperformers, sourced from the
   buyer language and keyword list in the brand guide.

Return a JSON object in this exact format:
{
  "underperforming_tags": ["tag1", "tag2", "tag3"],
  "top_performing_tags":  ["tag1", "tag2", "tag3"],
  "replacement_tags":     ["tag1", "tag2", "tag3"],
  "recommendation":       "One sentence summary of what to change and why."
}
"""


def run_feedback_loop(brand_guide: str, state: dict) -> dict:
    """
    Week 4 feedback agent: reads Etsy Stats and returns tag performance data.
    Patches state with optimization recommendations.
    """
    console.print(Panel("[bold amber]Week 4 — Feedback loop running[/bold amber]", style="yellow"))

    result = execute_task(
        task_text=FEEDBACK_PROMPT,
        brand_guide=brand_guide,
        week_label="Week 4 — Optimization",
        week_key="week_4",
    )

    # Parse the JSON block from Claude's response
    json_match = re.search(r"\{[\s\S]+\}", result)
    feedback_data: dict = {}

    if json_match:
        try:
            feedback_data = json.loads(json_match.group(0))
            console.print("[green]✓ Etsy Stats parsed successfully[/green]")
            rprint(feedback_data)
        except json.JSONDecodeError:
            console.print("[yellow]⚠ Could not parse JSON — raw result saved[/yellow]")
            feedback_data = {"raw_result": result}
    else:
        feedback_data = {"raw_result": result}

    state["feedback"] = {
        "generated_at": datetime.now().isoformat(),
        "data":         feedback_data,
    }
    save_state(state)

    # Write feedback report
    report_path = OUTPUTS_DIR / "feedback_report.md"
    report_path.write_text(
        f"# Etsy Stats Feedback Report\n\n"
        f"Generated: {state['feedback']['generated_at']}\n\n"
        f"## Tag Performance\n\n"
        f"```json\n{json.dumps(feedback_data, indent=2)}\n```\n\n"
        f"## Next Action\n\n"
        f"{feedback_data.get('recommendation', 'See raw result above.')}\n",
        encoding="utf-8",
    )
    console.print(f"[dim]Feedback report written to: {report_path}[/dim]")
    return feedback_data


# ─── STEP 7 — MAIN ORCHESTRATOR ───────────────────────────────────────────────

def main() -> None:
    console.print(Panel(
        "[bold]Freelance Flow — Phase 2 Autonomous Executor[/bold]\n"
        "[dim]Claude in Chrome · Anthropic API · outputs/brand_guide.md[/dim]",
        style="cyan",
    ))

    # Load brand guide
    console.print("\n[dim]Loading generated brand guide...[/dim]")
    brand_guide = load_brand_guide()

    # Resume from saved state or start fresh
    state = load_state()
    if state:
        console.print("[yellow]Resuming from saved state.[/yellow]")
        if not MASTER_PROMPT_FILE.exists():
            initialize_master_prompt_file()
    else:
        checklist = extract_checklist(brand_guide)
        state = {
            "started_at": datetime.now().isoformat(),
            "checklist":  checklist,
            "feedback":   None,
        }
        save_state(state)
        initialize_master_prompt_file()
        console.print("[green]New execution started.[/green]")

    checklist = state["checklist"]

    # ── Execute each weekly agent in sequence ──────────────────────────────
    for week_key in ["week_1", "week_2", "week_3", "week_4"]:
        tasks = checklist.get(week_key, [])
        if not tasks:
            console.print(f"[dim]No tasks found for {week_key} — skipping[/dim]")
            continue

        pending = [t for t in tasks if t["status"] != "completed"]
        if not pending:
            console.print(f"[dim]{WEEK_LABELS[week_key]} — all tasks already complete, skipping[/dim]")
            continue

        checklist[week_key] = run_weekly_agent(
            week_key=week_key,
            tasks=tasks,
            brand_guide=brand_guide,
            state=state,
        )

        # Week 4 also runs the feedback loop after regular tasks complete
        if week_key == "week_4":
            run_feedback_loop(brand_guide=brand_guide, state=state)

        console.print(f"\n[green]✓ {WEEK_LABELS[week_key]} complete[/green]\n")
        time.sleep(3)

    # ── Final summary ──────────────────────────────────────────────────────
    total     = sum(len(v) for v in checklist.values())
    completed = sum(1 for v in checklist.values() for t in v if t["status"] == "completed")

    console.print(Panel(
        f"[bold green]Launch complete[/bold green]\n\n"
        f"Tasks completed: {completed}/{total}\n"
        f"Week log:        outputs/week_log.md\n"
        f"Master prompts:  outputs/master.txt\n"
        f"Feedback report: outputs/feedback_report.md\n"
        f"State file:      outputs/executor_state.json",
        style="green",
    ))


if __name__ == "__main__":
    main()
