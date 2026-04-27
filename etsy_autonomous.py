"""
etsy_autonomous.py
──────────────────
Fully autonomous Phase 2 executor.
Reads the generated brand guide, extracts the 30-day checklist, and executes
each task autonomously using Claude computer use — no Claude in Chrome needed.

Run:
    python etsy_autonomous.py

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

load_dotenv()

console = Console()
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ── Claude 3.5 Sonnet is the correct model for computer use ──────────────────
MODEL      = "claude-3-5-sonnet-20241022"
BRAND_FILES = (Path("outputs/brand_guide.md"), Path("brand_guide.md"))
STATE_FILE = Path("outputs/executor_state.json")
LOG_FILE   = Path("outputs/week_log.md")
Path("outputs").mkdir(exist_ok=True)

# ── Correct computer use tool definitions ─────────────────────────────────────
TOOLS = [
    {
        "type": "computer_20241022",
        "name": "computer",
        "display_width_px": 1280,
        "display_height_px": 800,
        "display_number": 1,
    },
    {
        "type": "text_editor_20241022",
        "name": "str_replace_editor",
    },
    {
        "type": "bash_20241022",
        "name": "bash",
    },
]

BETA = ["computer-use-2024-10-22"]

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

# ── System prompt ─────────────────────────────────────────────────────────────
def build_system_prompt(guide: str, week: str) -> str:
    return f"""You are an autonomous Etsy store launch agent for "The Freelance Command Center".

You have full access to a web browser, a text editor, and a bash terminal.
Use these tools to complete the assigned task fully and verify success before finishing.

## Brand context
{guide[:3000]}

## Week
{week}

## Rules
- Navigate to the correct platform for each task (Canva, Etsy, Pinterest, Instagram).
- For Canva: go to canva.com, apply brand colors (#2C3E50 charcoal, #DAA520 gold, #F5F1E8 cream), use Poppins for headings.
- For Etsy: go to etsy.com/your/shops/me/tools — do NOT click publish or purchase without user approval.
- If you encounter a CAPTCHA, 2FA prompt, or login screen, stop and report it.
- Never enter payment details or passwords.
- After each task, briefly confirm what was done and what URL or file was produced.
"""

# ── Execute one task ──────────────────────────────────────────────────────────
def execute_task(task: str, guide: str, week: str) -> str:
    messages = [{"role": "user", "content": f"Complete this task now: {task}"}]
    system   = build_system_prompt(guide, week)
    output   = ""

    for _ in range(20):  # max 20 tool-use turns per task
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
            betas=BETA,
        )

        for block in response.content:
            if hasattr(block, "text") and block.text:
                output += block.text

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     f"[{block.name} executed with input: {str(block.input)[:300]}]",
                    })
            messages.append({"role": "user", "content": results})
        else:
            break

    return output.strip()

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
        console.print("  [dim]Claude executing...[/dim]")

        result = execute_task(item["task"], guide, label)

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
    else:
        checklist = extract_checklist(guide)
        state = {"started_at": datetime.now().isoformat(), "checklist": checklist}
        save_state(state)
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
        f"Tasks: {done}/{total}\nLog: outputs/week_log.md",
        style="green"
    ))

if __name__ == "__main__":
    main()
