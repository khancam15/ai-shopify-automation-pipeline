"""
etsy_autonomous.py
──────────────────
Phase 2 executor for claude-3-5-sonnet · computer use.
Reads the generated brand guide, extracts the 30-day checklist, and generates
ready-to-paste prompts for each launch task.

Run:
    python scripts/etsy_autonomous.py

Requirements:
    pip install anthropic python-dotenv rich
    ANTHROPIC_API_KEY in your .env file
"""

import os
import json
import time
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import anthropic
from rich.console import Console
from rich.panel import Panel
from rich import print as rprint

load_dotenv()

console = Console()
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MODEL      = "claude-3-5-sonnet-20241022"
BRAND_FILES = (Path("outputs/brand_guide.md"), Path("brand_guide.md"))
STATE_FILE = Path("outputs/executor_state.json")
LOG_FILE   = Path("outputs/week_log.md")
MASTER_TEMPLATE_FILE = Path("prompts_example/master.txt")
MASTER_PROMPT_FILE = Path("outputs/master.txt")
Path("outputs").mkdir(exist_ok=True)

# ── Load brand guide ──────────────────────────────────────────────────────────
def load_brand_guide() -> str:
    for brand_file in BRAND_FILES:
        if brand_file.exists():
            return brand_file.read_text(encoding="utf-8")

    preferred_file = BRAND_FILES[0]
    fallback_file = BRAND_FILES[1]
    if not preferred_file.exists():
        raise FileNotFoundError(
            f"Brand guide not found at {preferred_file.resolve()} or {fallback_file.resolve()}\n"
            "Run etsy_brand_crew.py first."
        )

# ── Extract checklist ─────────────────────────────────────────────────────────
def extract_checklist(guide: str) -> dict:
    patterns = {
        "week_1": r"### Week 1.*?(?=### Week 2|$)",
        "week_2": r"### Week 2.*?(?=### Week 3|$)",
        "week_3": r"### Week 3.*?(?=### Week 4|$)",
        "week_4": r"### Week 4.*?(?=$)",
    }
    checklist = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, guide, re.DOTALL | re.IGNORECASE)
        if not match:
            checklist[key] = []
            continue
        block = match.group(0)
        items = re.findall(r"\d+\.\s+(.+?)(?=\n\d+\.|\n\n|$)", block, re.DOTALL)
        tool_match = re.search(r"\*Free Tool:\s*(.+?)\*", block)
        tool = tool_match.group(1).strip() if tool_match else None
        checklist[key] = [
            {"task": item.strip().replace("**", ""), "tool": tool, "status": "pending"}
            for item in items
        ]
    total = sum(len(v) for v in checklist.values())
    console.print(f"[dim]Extracted {total} tasks from the generated brand guide[/dim]")
    return checklist

# ── State management ──────────────────────────────────────────────────────────
def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def load_state() -> dict | None:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def initialize_master_prompt_file() -> None:
    """Create or reset outputs/master.txt from prompts_example/master.txt when available."""
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

# ── Prompt generation for Claude Chrome extension ────────────────────────────
def build_extension_prompt(task: str, guide: str, week: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        system=(
            "You are an Etsy launch execution planner. "
            "Generate one high-quality prompt the user can paste into the Claude Chrome extension. "
            "The prompt must include objective, exact steps, constraints, and a completion checklist."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Week: {week}\n"
                    f"Task: {task}\n\n"
                    "Brand guide context:\n"
                    f"{guide[:3200]}\n\n"
                    "Output format:\n"
                    "1) Goal\n"
                    "2) Step-by-step browser actions\n"
                    "3) Safety constraints (no publish/purchase without confirmation)\n"
                    "4) Done checklist with proof items"
                ),
            }
        ],
    )
    return response.content[0].text.strip()

# ── Run one week ──────────────────────────────────────────────────────────────
LABELS = {
    "week_1": "Week 1 — Storefront Setup",
    "week_2": "Week 2 — Listing Expansion",
    "week_3": "Week 3 — External Traffic",
    "week_4": "Week 4 — Optimization",
}

def run_week(key: str, tasks: list, guide: str, state: dict) -> list:
    label = LABELS[key]
    console.print(Panel(f"[bold]{label}[/bold]", style="cyan"))

    for i, item in enumerate(tasks):
        if item["status"] == "completed":
            console.print(f"  [dim]↳ Skipping: {item['task'][:60]}[/dim]")
            continue

        console.print(f"\n  [bold cyan]Task {i+1}/{len(tasks)}:[/bold cyan] {item['task'][:70]}")
        console.print("  [dim]Generating Claude Chrome extension prompt...[/dim]")

        result = build_extension_prompt(item["task"], guide, label)
        rprint(f"\n[bold yellow]--- PASTE INTO CLAUDE CHROME EXTENSION ---[/bold yellow]\n{result}\n")
        append_master_prompt(label, i + 1, item["task"], result)

        item["status"]       = "completed"
        item["result"]       = result[:400]
        item["completed_at"] = datetime.now().isoformat()

        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n## {label} · Task {i+1}\n**Task:** {item['task']}\n**Result:** {result[:300]}\n---\n")

        state["checklist"][key] = tasks
        save_state(state)
        console.print(f"  [green]✓ Task {i+1} complete[/green]")
        time.sleep(2)

    return tasks

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    console.print(Panel(
        "[bold]The Freelance Command Center — Autonomous Executor[/bold]\n"
        "[dim]claude-3-5-sonnet · computer use · outputs/brand_guide.md[/dim]",
        style="cyan"
    ))

    guide = load_brand_guide()

    state = load_state()
    if state:
        console.print("[yellow]Resuming from saved state.[/yellow]")
        if not MASTER_PROMPT_FILE.exists():
            initialize_master_prompt_file()
    else:
        checklist = extract_checklist(guide)
        state = {"started_at": datetime.now().isoformat(), "checklist": checklist}
        save_state(state)
        initialize_master_prompt_file()
        console.print("[green]New execution started.[/green]")

    for key in ["week_1", "week_2", "week_3", "week_4"]:
        tasks = state["checklist"].get(key, [])
        if not tasks:
            console.print(f"[dim]No tasks for {key}[/dim]")
            continue
        if all(t["status"] == "completed" for t in tasks):
            console.print(f"[dim]{LABELS[key]} already complete[/dim]")
            continue
        state["checklist"][key] = run_week(key, tasks, guide, state)
        console.print(f"\n[green]✓ {LABELS[key]} complete[/green]\n")
        time.sleep(3)

    done  = sum(1 for v in state["checklist"].values() for t in v if t["status"] == "completed")
    total = sum(len(v) for v in state["checklist"].values())
    console.print(Panel(
        f"[bold green]Launch complete[/bold green]\n\n"
        f"Tasks: {done}/{total}\n"
        f"Log: outputs/week_log.md\n"
        f"Master prompts: outputs/master.txt",
        style="green"
    ))

if __name__ == "__main__":
    main()
