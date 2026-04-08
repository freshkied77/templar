"""
Main agent orchestrator.
Runs the continuous autonomous loop: generate → list → monitor → learn → self-correct.
"""

import time
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .memory import AgentMemory
from .tools import ToolRegistry, build_tool_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("templar.agent")

# Threshold: minimum active listings before we stop generating and start optimizing
MIN_CATALOG_SIZE = 5
# Days old a top performer must be before we generate a new one in that category
TOP_PERFORMER_COOLDOWN_DAYS = 14
# Days with zero sales before we delist a listing
DELIST_AFTER_DAYS = 30
# Never generate if best category conversion exceeds this (market saturated signal)
SATURATION_THRESHOLD = 0.10  # 10% conversion = very saturated, vary price instead

MARKETPLACES_TO_USE = ["gumroad", "payhip", "lemonsqueezy"]

NOTION_CATEGORIES = [
    "Habit Tracker",
    "Project Management",
    "Finance Tracker",
    "Content Calendar",
    "Inventory Management",
    "Travel Planner",
    "Student Dashboard",
    "Fitness Tracker",
    "Business Planner",
    "Reading List",
    "Goal Tracker",
    "Client CRM",
    "Social Media Manager",
    "Recipe Book",
    "Weekly Planner",
    "Blog Editorial",
    "Product Launch",
    "Freelance Tracker",
    "Study Schedule",
    "Wellness Journal",
]


class Orchestrator:
    """
    The autonomous agent loop. Each cycle:

    1. Fetch sales data from all marketplaces
    2. Self-correct: delist dead listings, update category weights
    3. Decide: generate new? A/B test existing? or wait?
    4. Generate (AI description + AI template structure)
    5. List on configured marketplaces
    6. Flag exceptions requiring human attention
    7. Sleep and repeat
    """

    def __init__(
        self,
        memory: Optional[AgentMemory] = None,
        loop_interval: int = 300,  # 5 minutes
    ):
        self.memory = memory or AgentMemory()
        self.loop_interval = loop_interval
        self.tools: Optional[ToolRegistry] = None
        self._running = False

    def _init_tools(self, generators: dict, marketplaces: dict) -> None:
        self.tools = build_tool_registry(self.memory, generators, marketplaces)

    def _should_generate(self) -> tuple[bool, str]:
        """
        Decide whether to generate a new template this cycle.
        Returns (should_generate, reason).
        """
        stats = self.memory.get_total_stats()
        active = stats.get("active_listings", 0)
        weights = self.memory.get_category_weights()
        top_cats = self.memory.get_top_categories(limit=1)

        # Rule 1: If catalog is very small, always generate
        if active < MIN_CATALOG_SIZE:
            if top_cats:
                return True, f"Catalog below minimum size ({active}/{MIN_CATALOG_SIZE})"
            # No data yet — pick first category
            return True, f"Initial catalog build ({active} listings)"

        # Rule 2: Check for dead listings — delist first, don't add more
        dead = self.memory.get_listings_with_no_sales(days_old=DELIST_AFTER_DAYS)
        if dead:
            return False, f"Has {len(dead)} stale listings — delisting first"

        # Rule 3: Check if best performer is stale (opportunity to explore)
        if top_cats:
            best_cat = top_cats[0]
            best_data = weights.get(best_cat, {})
            # If best category has very high conversion, don't spam it — vary instead
            if best_data.get("conversion_rate", 0) > SATURATION_THRESHOLD:
                return True, f"Top category '{best_cat}' saturated — trying new categories"

        # Rule 4: Exploit vs explore — 70% stay on top categories, 30% explore new
        if top_cats and random.random() < 0.7:
            return True, f"Exploiting top category '{top_cats[0]}'"
        return True, "Explore cycle — trying new category"

    def _get_next_category(self) -> str:
        """Pick next category using learned performance weights with explore."""
        weights = self.memory.get_category_weights()
        top_cats = self.memory.get_top_categories(limit=3)

        if not top_cats:
            # Cold start — pick a category we have least data on
            listed = set(w.keys() for w in weights.values())
            for cat in NOTION_CATEGORIES:
                if cat not in weights:
                    return cat
            return random.choice(NOTION_CATEGORIES)

        # 70% exploit top-3, 30% explore uncovered or low-weight categories
        if random.random() < 0.7:
            return random.choice(top_cats)

        # Explore: pick from categories with fewest listings
        uncovered = [c for c in NOTION_CATEGORIES if c not in weights or weights[c]["total_listings"] < 2]
        if not uncovered:
            uncovered = [c for c in NOTION_CATEGORIES if c not in top_cats]
        return random.choice(uncovered) if uncovered else random.choice(top_cats)

    def _generate_description_ai(self, category: str, template_title: str) -> str:
        """Use AI to generate a conversion-optimized sales description."""
        if not self.tools:
            return None
        # Try AI generation via a dedicated tool
        try:
            prompt = f"""You are an expert copywriter for digital Notion templates.
Write a compelling sales description for a Notion template with:
- Category: {category}
- Title: {template_title}

The description should:
1. Open with the #1 problem this template solves (one punchy sentence)
2. List 3 specific benefits (not features) in short bullet points
3. End with a call to action

Keep it under 200 words. Conversational, confident tone. No fluff.
Return ONLY the description text, no markdown formatting."""
            # Delegate to the AI generator with a description-specific prompt
            result = self.tools.call("generate_template", category=category, description=prompt)
            if result.success and result.data:
                # The template generator returns a full template; extract or use tagline
                return result.data.get("seo_description") or result.data.get("tagline", "")
        except Exception:
            pass
        return None

    def _generate_description(self, category: str) -> str:
        """Generate description — AI if available, else structured fallback."""
        # Try AI first
        ai_desc = self._generate_description_ai(category, f"Premium {category} Template")
        if ai_desc:
            return ai_desc

        # Structured fallback with category-specific copy
        prompts = {
            "Habit Tracker": "A beautifully designed Notion habit tracker with daily streaks, weekly reviews, and visual progress charts for building lasting habits. Stop relying on willpower — build systems.",
            "Project Management": "A comprehensive Notion project tracker with Kanban boards, Gantt views, task dependencies, and team collaboration. Everything you need, nothing you don't.",
            "Finance Tracker": "Track income, expenses, savings goals, and net worth in one place. 5 minutes a week to know exactly where your money goes. No bank syncing required.",
            "Content Calendar": "Plan, schedule, and track your content across every platform. Built for creators who want consistency without the chaos. 30 days of content, planned in under an hour.",
            "Inventory Management": "Never run out of stock again. Track inventory levels, reorder points, and supplier info. Perfect for e-commerce sellers and product-based businesses.",
            "Travel Planner": "Plan trips like a pro. Itinerary, packing list, budget tracker, and accommodation details — all in one place. Your next adventure starts here.",
            "Student Dashboard": "Track assignments, GPA, study time, and goals in one dashboard. Designed specifically for university students who want to stay on top of everything without the stress.",
            "Fitness Tracker": "Log workouts, track progress, and see your strength gains over time. Includes workout templates, meal logging, and progress photos. No gym subscription required.",
            "Business Planner": "The command center for your business. Track goals, clients, finances, and tasks in one place. Built for founders and side-hustlers who mean business.",
            "Reading List": "Stop losing book recommendations. Track what you're reading, what you've read, and what you want to read next. Includes notes, ratings, and quotes.",
            "Goal Tracker": "Set big goals, break them into monthly sprints, track weekly progress. The system that turns ambitions into achievements. No fluff, just results.",
            "Client CRM": "Manage your clients from first contact to final payment. Track leads, appointments, invoices, and deliverables. Perfect for freelancers and consultants.",
            "Social Media Manager": "Plan, schedule, and analyze your social media from one dashboard. Track engagement, plan content, and never miss a posting day again.",
            "Recipe Book": "Your personal chef's notebook. Store recipes, create meal plans, and auto-generate shopping lists. Cook more, stress less.",
            "Weekly Planner": "Master your week before it starts. Plan priorities, block time, and track habits — all on one page. 15 minutes Sunday changes the whole week.",
            "Blog Editorial": "Take your blog from idea to published post. Editorial calendar, outline builder, and SEO checklist — everything WordPress bloggers need.",
            "Product Launch": "The launch checklist that actually works. Pre-launch, launch day, and post-launch tracking. Because a great product deserves a great launch.",
            "Freelance Tracker": "Track clients, projects, hours, and invoices in one place. Know exactly what to invoice, when, and how much you're really earning.",
            "Study Schedule": "Study smarter, not harder. Weekly schedule, exam countdown, and topic review tracker. Designed for students who want top grades with less stress.",
            "Wellness Journal": "Your daily wellness check-in. Mood, sleep, water, movement, and gratitude — 5 minutes a day to feel measurably better.",
        }
        return prompts.get(
            category,
            f"A premium Notion {category} template designed to save you hours every week. Structured for immediate use, fully customizable to your workflow.",
        )

    def _delist_dead_listings(self) -> int:
        """Autonomously delist listings with zero sales after threshold days. Returns count."""
        if not self.tools:
            return 0
        dead = self.memory.get_listings_with_no_sales(days_old=DELIST_AFTER_DAYS)
        delisted = 0
        for listing in dead:
            result = self.tools.call(
                "delist_product",
                listing_id=listing["listing_id"],
                marketplace_name=listing["marketplace"],
            )
            if result.success:
                self.memory.remove_listing(listing["listing_id"], listing["marketplace"])
                log.info(f"Autodelisted: {listing['title']} on {listing['marketplace']}")
                delisted += 1
            else:
                self.memory.log_exception(
                    title=f"Failed to autodelist {listing['title']}",
                    description=result.error or "Unknown error",
                    severity="low",
                )
        return delisted

    def run_cycle(self, generators: dict, marketplaces: dict) -> dict:
        """Run one full agent cycle. Returns cycle summary."""
        self._init_tools(generators, marketplaces)
        summary = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "actions": [],
            "errors": [],
            "decisions": [],
        }

        # Step 0: Self-correction — delist dead listings first
        delisted = self._delist_dead_listings()
        if delisted > 0:
            summary["decisions"].append(f"Autodelisted {delisted} stale listings")

        # Step 1: Check for exceptions requiring human attention
        exceptions = self.tools.call("get_open_exceptions")
        if exceptions.success and exceptions.data:
            for exc in exceptions.data:
                log.warning(f"Open exception: {exc['title']} — {exc['description']}")

        # Step 2: Fetch and record sales data
        log.info("Fetching sales data from marketplaces...")
        sales_result = self.tools.call("get_sales_data", marketplace_name=None, timeframe=7)
        if sales_result.success:
            summary["actions"].append({"action": "fetch_sales", "data": sales_result.data})
        else:
            summary["errors"].append({"action": "fetch_sales", "error": sales_result.error})

        # Step 3: Decide whether to generate
        should_gen, reason = self._should_generate()
        summary["decisions"].append(f"generate_decision: {reason}")
        log.info(f"Generate decision: {should_gen} — {reason}")

        if not should_gen:
            stats = self.tools.call("get_stats")
            if stats.success:
                summary["stats"] = stats.data
            return summary

        # Step 4: Pick category and generate description
        category = self._get_next_category()
        description = self._generate_description(category)
        log.info(f"Generating template: {category}")

        gen_result = self.tools.call("generate_template", category=category, description=description)
        if not gen_result.success:
            log.error(f"Template generation failed: {gen_result.error}")
            summary["errors"].append({"action": "generate_template", "error": gen_result.error})
            return summary

        template = gen_result.data
        self.memory.record_decision(category=category, action="generate", outcome="success")
        summary["actions"].append({
            "action": "generate_template",
            "category": category,
            "title": template.get("title"),
            "price": template.get("price_suggested"),
        })

        # Step 5: List on marketplaces
        log.info(f"Listing on: {MARKETPLACES_TO_USE}")
        list_result = self.tools.call(
            "list_product",
            template=template,
            marketplaces_to_use=MARKETPLACES_TO_USE,
        )

        listed_on = []
        for mp, result in list_result.data.items():
            if "error" in result:
                log.error(f"Failed to list on {mp}: {result['error']}")
                summary["errors"].append({"action": f"list_on_{mp}", "error": result["error"]})
            else:
                log.info(f"Listed on {mp}: {result.get('listing_id', 'unknown')}")
                listed_on.append(mp)
                self.memory.record_decision(
                    category=category,
                    action=f"list_on_{mp}",
                    outcome="success",
                    revenue=0,
                    sales_count=0,
                )

        summary["actions"].append({"action": "list_product", "listed_on": listed_on})

        # Step 6: Get updated stats
        stats = self.tools.call("get_stats")
        if stats.success:
            summary["stats"] = stats.data
            log.info(f"Stats: {stats.data}")

        return summary

    def run(self, generators: dict, marketplaces: dict) -> None:
        """Run the agent loop continuously."""
        self._running = True
        log.info(f"Templar agent started. Loop interval: {self.loop_interval}s")
        log.info(f"Marketplaces: {MARKETPLACES_TO_USE}")

        while self._running:
            try:
                self.run_cycle(generators, marketplaces)
            except Exception as e:
                log.exception(f"Agent cycle failed: {e}")
                self.tools.call(
                    "flag_exception",
                    title="Agent cycle crashed",
                    description=str(e),
                    severity="high",
                )

            if self._running:
                time.sleep(self.loop_interval)

    def stop(self) -> None:
        self._running = False
        log.info("Agent stopped.")
