"""
etsy_brand_crew.py
──────────────────
Run from the project root:
    python scripts/etsy_brand_crew.py

Requires:
    pip install crewai crewai-tools
    ANTHROPIC_API_KEY and SERPER_API_KEY in your .env

The crew performs a full 6-agent Etsy brand build driven by live
market research. A final brand_guide.md is written to ./outputs/.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai_tools import SerperDevTool

load_dotenv()


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise SystemExit(f"[error] {key} is not set. Add it to your .env file.")
    return value


_require_env("ANTHROPIC_API_KEY")
_require_env("SERPER_API_KEY")

# ─── CONFIG ──────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

MODEL = "claude-haiku-4-5-20251001"   # fastest / most cost-efficient for agentic loops

# ─── TOOLS ───────────────────────────────────────────────────────────────────

search     = SerperDevTool(n_results=8)


# ─── AGENTS ──────────────────────────────────────────────────────────────────

niche_scout = Agent(
    role="Etsy Niche Scout",
    goal=(
        "Identify the single highest-opportunity Etsy niche for a new digital "
        "product store by analyzing market size, competition level, buyer intent, "
        "and profit potential. Deliver one specific, actionable niche statement."
    ),
    backstory=(
        "You have evaluated thousands of Etsy categories and know exactly which "
        "niches are oversaturated, which are emerging, and which have durable "
        "demand. You combine search trend data with review volume proxies to "
        "surface niches where a new seller can realistically reach $1k/month "
        "within 90 days selling digital products."
    ),
    tools=[search],
    llm=MODEL,
    verbose=True,
    allow_delegation=False,
)

market_analyst = Agent(
    role="Etsy Market Research Analyst",
    goal=(
        "Gather and synthesize live data on top-selling Etsy stores in the niche, "
        "dominant visual styles, price points, buyer language in reviews, "
        "keyword volume, and whitespace opportunities."
    ),
    backstory=(
        "You are a specialist in consumer market intelligence for digital product "
        "businesses. You think in patterns: what is selling, who is buying, what "
        "language converts, and where competitors are leaving gaps."
    ),
    tools=[search],
    llm=MODEL,
    verbose=True,
    allow_delegation=False,
)

brand_strategist = Agent(
    role="Brand Strategist",
    goal=(
        "Use the market research to define a differentiated store foundation: "
        "a precise niche, a compelling store name, target buyer persona, "
        "a one-sentence positioning statement, and three brand tone adjectives."
    ),
    backstory=(
        "You build brands that cut through noise. You translate research signals "
        "into a coherent identity that attracts a specific buyer and repels everyone else. "
        "You believe a brand with sharp edges outperforms a brand trying to appeal to all."
    ),
    tools=[search],
    llm=MODEL,
    verbose=True,
    allow_delegation=False,
)

visual_director = Agent(
    role="Visual Identity Director",
    goal=(
        "Recommend a complete visual identity system: a 2–3 color primary palette "
        "with hex codes and usage rules, 1–2 neutral hex codes, a display font and "
        "body font pairing with rationale, logo concept direction (wordmark, icon, or combo), "
        "and a single-line aesthetic descriptor."
    ),
    backstory=(
        "You have directed brand identities for dozens of e-commerce businesses. "
        "You know that color is emotional, typography is personality, and logo "
        "recognition at 500×500 pixels is a non-negotiable constraint on Etsy. "
        "You base every visual decision on what the market research says buyers respond to."
    ),
    tools=[search],
    llm=MODEL,
    verbose=True,
    allow_delegation=False,
)

copy_strategist = Agent(
    role="Brand Copywriter and SEO Strategist",
    goal=(
        "Produce the full brand voice system: tagline, tone guide, a product title "
        "formula, a listing description template, 13 Etsy SEO tags, and a "
        "review request message. All copy must reflect the brand tone adjectives "
        "and be optimized for Etsy search."
    ),
    backstory=(
        "You write copy that converts browsers into buyers. You understand Etsy's "
        "algorithm rewards keyword-first titles and relevant long-tail tags. "
        "You write the way the target buyer thinks, not the way the seller thinks."
    ),
    tools=[search],
    llm=MODEL,
    verbose=True,
    allow_delegation=False,
)

launch_planner = Agent(
    role="Launch Asset Planner",
    goal=(
        "Compile all upstream deliverables into a single structured brand_guide.md, "
        "then append a 30-day launch checklist covering storefront setup, listing "
        "rollout, and external traffic (Pinterest, Instagram, TikTok) with specific "
        "action items and recommended tools."
    ),
    backstory=(
        "You are the operator who turns strategy into execution. You have launched "
        "over fifty Etsy digital product stores. You know what separates a store "
        "that makes its first sale in week one from one that sits dormant for months."
    ),
    tools=[],
    llm=MODEL,
    verbose=True,
    allow_delegation=False,
)

# ─── TASKS ───────────────────────────────────────────────────────────────────

task_niche = Task(
    description="""
    Search Etsy and current trend data to identify the single best niche for a
    new digital product store launching today.

    Evaluate niches across these dimensions:
    1. Demand signal — search volume, number of active listings, review velocity
       on top sellers (reviews/month as a revenue proxy).
    2. Competition gap — are the top 10 results dominated by a few large stores,
       or is there room for a new entrant?
    3. Digital product fit — can this niche be served with downloadable files
       (templates, printables, planners, guides, presets, etc.)?
    4. Buyer willingness to pay — average price point $5–$35, strong impulse-buy
       characteristics.
    5. Durability — not a passing trend; will still sell in 12 months.

    Return ONE chosen niche as a single specific sentence
    (e.g. "Notion productivity templates for freelancers" or
    "Printable budget planners for newly married couples").
    Label it clearly: CHOSEN NICHE: <niche statement>
    """,
    expected_output=(
        "A short report showing evaluation of 3–5 candidate niches across the five "
        "dimensions, followed by a clearly labelled CHOSEN NICHE statement."
    ),
    agent=niche_scout,
)

task_research = Task(
    description="""
    The niche to research has been chosen by the Niche Scout in the previous task.
    Use that CHOSEN NICHE as the subject of all research below.

    Conduct live market research on Etsy for that niche.

    Search for:
    1. Top 5 best-selling stores in this niche — note their store names, estimated
       monthly revenue (use any public data or review count proxies), visual style
       description, and price points.
    2. The most common buyer complaints and praises in reviews (what buyers love
       and what they wish was different).
    3. Top 10 search keywords buyers use to find these products on Etsy.
    4. At least 2 underserved sub-niches or positioning gaps competitors are missing.
    5. Dominant color palettes and aesthetic styles in the top stores' thumbnails.

    Format output as structured sections with headers.
    """,
    expected_output=(
        "A structured market research report with five sections: "
        "Competitor Overview, Buyer Sentiment, Top Keywords, "
        "Positioning Gaps, and Visual Landscape."
    ),
    agent=market_analyst,
    context=[task_niche],
)

task_strategy = Task(
    description="""
    Using the market research report and the CHOSEN NICHE from the Niche Scout,
    define the store foundation for a new Etsy digital product store in that niche.

    Deliver:
    1. Refined niche statement (one sentence, ultra-specific)
    2. Target buyer persona (name them, describe their job, problem, and goal)
    3. Three store name options with reasoning (check Etsy availability mentally)
    4. Recommended store name with justification
    5. One-sentence brand positioning statement (who, what, outcome)
    6. Three brand tone adjectives with one-line definitions each

    Base every decision explicitly on the research findings.
    """,
    expected_output=(
        "A brand foundation document with six sections: "
        "Niche, Persona, Name Options, Recommended Name, "
        "Positioning Statement, and Tone Adjectives."
    ),
    agent=brand_strategist,
    context=[task_niche, task_research],
)

task_visual = Task(
    description=f"""
    Design the complete visual identity system for the Etsy store defined
    in the brand strategy document.

    Deliver:
    1. Primary color palette: 2–3 colors with hex codes, names, and one-line
       usage rule per color (e.g. "Use for CTAs and logo mark").
    2. Neutral palette: 1–2 hex codes for backgrounds and body text.
    3. Font pairing: display font (for headings and store name) + body font
       (for descriptions). Source from Google Fonts. Explain why each fits
       the brand tone adjectives.
    4. Logo concept direction: describe the concept (wordmark / icon / combo),
       what the icon represents symbolically, and how it reads at 500×500px.
    5. One aesthetic descriptor sentence (e.g. "Clean editorial with warm amber
       accents — professional but approachable").
    6. Three Canva or Adobe Express template style recommendations for listing mockups.

    Root every decision in the market research visual landscape findings.
    """,
    expected_output=(
        "A visual identity specification with six sections: "
        "Color Palette, Neutrals, Font Pairing, Logo Direction, "
        "Aesthetic Descriptor, and Mockup Style Recommendations."
    ),
    agent=visual_director,
    context=[task_research, task_strategy],
)

task_copy = Task(
    description=f"""
    Write the complete brand voice and SEO system for the Etsy store.

    Deliver:
    1. Tagline: one punchy sentence (10 words max) that captures positioning.
    2. Tone guide: a 3-bullet do/don't for each tone adjective (9 bullets total).
    3. Product title formula: a fill-in-the-blank template using keyword-first
       structure Etsy rewards (e.g. "[Primary Keyword] | [Benefit] — [Format]").
    4. Listing description template: a 5-section structure with placeholder copy
       showing exactly what goes in each section and why.
    5. 13 Etsy SEO tags: drawn directly from the top keywords and buyer language
       in the research, one tag per line.
    6. Review request message: 3–4 sentences, warm tone, non-pushy, sent after
       successful download delivery.

    Every word should sound like the brand's tone adjectives, not generic Etsy copy.
    """,
    expected_output=(
        "A brand copy and SEO document with six sections: "
        "Tagline, Tone Guide, Title Formula, Description Template, "
        "SEO Tags, and Review Request Message."
    ),
    agent=copy_strategist,
    context=[task_research, task_strategy],
)

task_launch = Task(
    description=f"""
    Compile all previous deliverables — market research, brand strategy,
    visual identity, and copy system — into a single complete brand guide.

    Then append a 30-day launch checklist with specific action items grouped
    by week:
    - Week 1: Storefront setup (banner, logo, about, policies, first 3 listings)
    - Week 2: Listing expansion (reach 10 listings, A/B test two title formulas)
    - Week 3: External traffic (Pinterest boards, Instagram grid, first TikTok/Reel)
    - Week 4: Optimization (review analytics, refine tags, respond to all messages)

    For each week, include 5–7 specific actions and name at least one free tool
    to use (Canva, Pinterest Trends, Etsy Rank, etc.).

    Write the entire brand guide to outputs/brand_guide.md

    The file must use clean Markdown with headers, subheaders, and bullet points.
    Include a cover section at the top: Store Name, Positioning Statement,
    Aesthetic Descriptor, and Tagline.
    """,
    expected_output=(
        "A complete brand_guide.md written to outputs/brand_guide.md containing: "
        "Cover Section, Market Research Summary, Brand Foundation, Visual Identity, "
        "Copy System, and 30-Day Launch Checklist."
    ),
    agent=launch_planner,
    context=[task_research, task_strategy, task_visual, task_copy],
    output_file="outputs/brand_guide.md",
)

# ─── CREW ────────────────────────────────────────────────────────────────────

brand_crew = Crew(
    agents=[
        niche_scout,
        market_analyst,
        brand_strategist,
        visual_director,
        copy_strategist,
        launch_planner,
    ],
    tasks=[
        task_niche,
        task_research,
        task_strategy,
        task_visual,
        task_copy,
        task_launch,
    ],
    process=Process.sequential,   # each task feeds context into the next
    verbose=True,
)

# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{'─'*60}")
    print(f"  Etsy Brand Builder Crew")
    print(f"  Niche: AI-selected by Niche Scout agent")
    print(f"{'─'*60}\n")

    result = brand_crew.kickoff()

    print(f"\n{'─'*60}")
    print("  Brand guide written to: outputs/brand_guide.md")
    print(f"{'─'*60}\n")
    print(result)
