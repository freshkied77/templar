"""
Notion Template Generator.
Uses AI to generate complete, saleable Notion templates.
"""

import json
import os
from typing import Optional

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


SYSTEM_PROMPT = """You are a world-class Notion template designer. You create premium, visually appealing, and highly functional Notion templates that people will actually use and pay for.

For every template you produce, you MUST include:
1. A compelling title and tagline
2. A complete page structure with database views and properties
3. Sample data with realistic entries
4. A cover image concept description
5. SEO-optimized description

Output ONLY valid JSON. No markdown, no explanation."""


class NotionTemplateGenerator:
    """Generates Notion template structures using AI or rule-based fallback."""

    def __init__(self, api_key: Optional[str] = None, provider: str = "anthropic"):
        self.provider = provider.lower()
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")

        if self.provider == "anthropic" and ANTHROPIC_AVAILABLE and self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider == "openai" and OPENAI_AVAILABLE and self.api_key:
            self.client = openai.OpenAI(api_key=self.api_key)
        else:
            self.client = None

    def _generate_with_ai(self, user_prompt: str) -> dict:
        if not self.client:
            return None

        if self.provider == "anthropic":
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            text = response.content[0].text
        else:
            response = self.client.chat.completions.create(
                model="gpt-4o",
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = response.choices[0].message.content

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        return json.loads(text)

    def generate(self, category: str, description: str = None) -> dict:
        if self.client:
            user_prompt = f"""Generate a premium Notion template for: {category}.

Return valid JSON with these exact fields:
- category, title, tagline, price_suggested (number $9-$29)
- cover_concept, structure (views, properties, blocks)
- sample_data (3 realistic entries)
- seo_description (under 160 chars)
- tags (5 search tags)

Category: {category}
{description or 'Create based on category alone.'}"""
            try:
                return self._generate_with_ai(user_prompt)
            except Exception:
                return self._rule_based_template(category)
        return self._rule_based_template(category)

    def _rule_based_template(self, category: str) -> dict:
        templates = {
            "habit tracker": self._habit_tracker_template,
            "project management": self._project_management_template,
            "finance tracker": self._finance_tracker_template,
            "content calendar": self._content_calendar_template,
            "student dashboard": self._student_dashboard_template,
            "goal tracker": self._goal_tracker_template,
        }
        for key, fn in templates.items():
            if key in category.lower():
                return fn()
        return self._generic_template(category)

    def _habit_tracker_template(self) -> dict:
        return {
            "category": "Habit Tracker",
            "title": "The Atomic Habits Tracker — Build Systems Not Goals",
            "tagline": "The only habit tracker you'll actually use. Tracks streaks, weekly reviews, and visual progress without the overwhelm.",
            "price_suggested": 19,
            "cover_concept": "Dark aesthetic with neon accent lines showing a rising streak graph",
            "structure": {
                "type": "database",
                "views": ["Calendar", "Gallery", "Table"],
                "properties": [
                    {"name": "Habit", "type": "title"},
                    {"name": "Streak", "type": "number"},
                    {"name": "Best Streak", "type": "number"},
                    {"name": "Weekly Goal", "type": "select", "options": ["1-3", "4-5", "6-7"]},
                    {"name": "Category", "type": "select", "options": ["Health", "Productivity", "Learning", "Mindset"]},
                    {"name": "Status", "type": "select", "options": ["Active", "Paused", "Archived"]},
                    {"name": "Started", "type": "date"},
                ],
                "blocks": [
                    {"type": "callout", "emoji": "🎯", "text": "This template is designed to make habit tracking effortless. Just log your habit every day. The stats do the rest."},
                    {"type": "heading_1", "text": "How to Use This Template"},
                    {"type": "bulleted_list", "items": [
                        "Create a new row for each habit you want to track",
                        "Update the Streak property every day you complete your habit",
                        "Use the Calendar view to see your consistency at a glance",
                    ]},
                ],
            },
            "sample_data": [
                {"Habit": "Morning Pages (3 pages longhand)", "Streak": 14, "Best Streak": 21, "Weekly Goal": "4-5", "Category": "Mindset", "Status": "Active"},
                {"Habit": "Read 20 pages", "Streak": 7, "Best Streak": 30, "Weekly Goal": "6-7", "Category": "Learning", "Status": "Active"},
            ],
            "seo_description": "Stop relying on willpower. This Notion habit tracker uses streak science and visual feedback to make building habits almost effortless.",
            "tags": ["habit tracker", "productivity", "streaks", "self-improvement", "Notion template"],
        }

    def _project_management_template(self) -> dict:
        return {
            "category": "Project Management",
            "title": "The Minimal PM — Project Management Without the Bloat",
            "tagline": "A Notion PM system that has everything you need and nothing you don't. Kanban, timeline, priorities, all in one page.",
            "price_suggested": 24,
            "cover_concept": "Clean white with bold typography and a minimal Kanban board visualization",
            "structure": {
                "type": "database",
                "views": ["Kanban", "Timeline", "Table"],
                "properties": [
                    {"name": "Task", "type": "title"},
                    {"name": "Status", "type": "select", "options": ["Backlog", "In Progress", "Review", "Done", "Blocked"]},
                    {"name": "Priority", "type": "select", "options": ["Critical", "High", "Medium", "Low"]},
                    {"name": "Due Date", "type": "date"},
                    {"name": "Assignee", "type": "person"},
                    {"name": "Estimate (hrs)", "type": "number"},
                ],
                "blocks": [
                    {"type": "callout", "emoji": "⚡", "text": "Welcome to your new PM system. Add tasks, assign priorities, and watch your project unfold in the Timeline view."},
                ],
            },
            "sample_data": [
                {"Task": "Finalize landing page copy", "Status": "Review", "Priority": "High", "Estimate (hrs)": 3},
                {"Task": "Set up payment integration", "Status": "In Progress", "Priority": "Critical", "Estimate (hrs)": 8},
            ],
            "seo_description": "The last project management template you'll need. Notion-based, fully customizable, designed for solo founders and small teams.",
            "tags": ["project management", "Notion template", "kanban", "productivity", "task tracker"],
        }

    def _finance_tracker_template(self) -> dict:
        return {
            "category": "Finance Tracker",
            "title": "Clarity — The Notion Finance Dashboard That Actually Works",
            "tagline": "Track income, expenses, savings goals, and net worth in one place. No bank syncing required — just 5 minutes a week.",
            "price_suggested": 19,
            "cover_concept": "Dark finance app aesthetic with green and red accent colors showing growth charts",
            "structure": {
                "type": "database",
                "views": ["Table", "Gallery", "Calendar"],
                "properties": [
                    {"name": "Transaction", "type": "title"},
                    {"name": "Amount", "type": "number", "format": "dollar"},
                    {"name": "Type", "type": "select", "options": ["Income", "Expense", "Transfer"]},
                    {"name": "Category", "type": "select", "options": ["Food", "Transport", "Housing", "Entertainment", "Savings", "Business", "Other"]},
                    {"name": "Date", "type": "date"},
                    {"name": "Recurring", "type": "checkbox"},
                ],
                "blocks": [
                    {"type": "callout", "emoji": "💰", "text": "Add every transaction. Income or expense. 5 minutes a week is all it takes."},
                ],
            },
            "sample_data": [
                {"Transaction": "Client payment — Website project", "Amount": 2500, "Type": "Income", "Category": "Business"},
                {"Transaction": "Hosting — Annual", "Amount": -180, "Type": "Expense", "Category": "Business", "Recurring": True},
            ],
            "seo_description": "Finally, a finance tracker that doesn't require a finance degree. Built in Notion for freelancers and side-hustlers.",
            "tags": ["finance tracker", "budget", "freelance", "money management", "Notion template"],
        }

    def _content_calendar_template(self) -> dict:
        return {
            "category": "Content Calendar",
            "title": "The Content Engine — 30-Day Social Media Calendar System",
            "tagline": "Plan, schedule, and track your content across every platform. Built for creators who want consistency without the chaos.",
            "price_suggested": 22,
            "cover_concept": "Vibrant gradient cover with social media icons arranged in a calendar grid",
            "structure": {
                "type": "database",
                "views": ["Calendar", "Table", "Board"],
                "properties": [
                    {"name": "Content Piece", "type": "title"},
                    {"name": "Platform", "type": "select", "options": ["Instagram", "Twitter/X", "LinkedIn", "TikTok", "Blog", "YouTube"]},
                    {"name": "Status", "type": "select", "options": ["Idea", "Drafting", "Scheduled", "Published"]},
                    {"name": "Publish Date", "type": "date"},
                    {"name": "Caption/Description", "type": "text"},
                    {"name": "Hashtags", "type": "text"},
                ],
                "blocks": [
                    {"type": "callout", "emoji": "📅", "text": "The content calendar that ends your posting anxiety. Pick a day, create the content, mark it published. Repeat."},
                ],
            },
            "sample_data": [
                {"Content Piece": "Behind-the-scenes reel — designing the new template", "Platform": "Instagram", "Status": "Scheduled", "Publish Date": "2026-04-05"},
                {"Content Piece": "Thread: 5 lessons from my first 100 sales", "Platform": "Twitter/X", "Status": "Idea", "Publish Date": "2026-04-07"},
            ],
            "seo_description": "The Notion content calendar used by 1,000+ creators to maintain consistent posting across all platforms.",
            "tags": ["content calendar", "social media", "marketing", "content creation", "Notion template"],
        }

    def _student_dashboard_template(self) -> dict:
        return {
            "category": "Student Dashboard",
            "title": "The Dean's List Dashboard — Academic Success Without the Stress",
            "tagline": "Track assignments, GPA, study time, and goals in one dashboard designed specifically for university students.",
            "price_suggested": 17,
            "cover_concept": "Clean academic aesthetic with a four-quadrant layout showing courses, tasks, GPA, and goals",
            "structure": {
                "type": "database",
                "views": ["Table", "Calendar", "Gallery"],
                "properties": [
                    {"name": "Assignment", "type": "title"},
                    {"name": "Course", "type": "select"},
                    {"name": "Due Date", "type": "date"},
                    {"name": "Weight (%)", "type": "number"},
                    {"name": "Grade", "type": "select", "options": ["A", "B", "C", "D", "F", "Pending"]},
                    {"name": "Status", "type": "select", "options": ["Not Started", "In Progress", "Submitted"]},
                ],
                "blocks": [
                    {"type": "callout", "emoji": "🎓", "text": "Welcome to your academic command center. Add your courses first, then add assignments as they come in."},
                ],
            },
            "sample_data": [
                {"Assignment": "Research paper — Modern History", "Course": "HIST 201", "Due Date": "2026-04-15", "Weight (%)": 25, "Status": "In Progress"},
                {"Assignment": "Problem set 5", "Course": "MATH 301", "Due Date": "2026-04-08", "Weight (%)": 10, "Status": "Not Started"},
            ],
            "seo_description": "The Notion student dashboard that actually keeps you on top of assignments, exams, and your GPA.",
            "tags": ["student dashboard", "university", "academic", "Notion template", "study tracker"],
        }

    def _goal_tracker_template(self) -> dict:
        return {
            "category": "Goal Tracker",
            "title": "Goal Crusher — The Notion Goal System That Works",
            "tagline": "Set goals, break them into monthly sprints, track weekly progress, and celebrate wins. No fluff, just results.",
            "price_suggested": 15,
            "cover_concept": "Bold typography with a mountain peak illustration and achievement badges",
            "structure": {
                "type": "database",
                "views": ["Table", "Gallery", "Board"],
                "properties": [
                    {"name": "Goal", "type": "title"},
                    {"name": "Category", "type": "select", "options": ["Career", "Finance", "Health", "Learning", "Relationships", "Creative"]},
                    {"name": "Why It Matters", "type": "text"},
                    {"name": "Target Date", "type": "date"},
                    {"name": "Progress", "type": "number", "format": "percent"},
                    {"name": "Sprint", "type": "select", "options": ["Q1 2026", "Q2 2026", "Q3 2026", "Q4 2026"]},
                    {"name": "Status", "type": "select", "options": ["Active", "Completed", "Abandoned"]},
                ],
                "blocks": [
                    {"type": "callout", "emoji": "🏆", "text": "Every big goal was once a decision. This template turns your decisions into a system."},
                ],
            },
            "sample_data": [
                {"Goal": "Earn $10k from digital products", "Category": "Finance", "Progress": 35, "Sprint": "Q2 2026", "Status": "Active"},
                {"Goal": "Run a half marathon", "Category": "Health", "Progress": 60, "Sprint": "Q2 2026", "Status": "Active"},
            ],
            "seo_description": "Stop setting goals and forgetting them. This Notion goal tracker uses quarterly sprints to break big goals into weekly actions.",
            "tags": ["goal tracker", "productivity", "Notion template", "personal development", "OKR"],
        }

    def _generic_template(self, category: str) -> dict:
        return {
            "category": category,
            "title": f"The Ultimate {category} Notion Template",
            "tagline": f"A premium, beautifully designed {category} template that saves you hours and keeps you organized.",
            "price_suggested": 19,
            "cover_concept": "Modern minimal design with bold title and category-relevant imagery",
            "structure": {
                "type": "database",
                "views": ["Table", "Gallery"],
                "properties": [
                    {"name": "Item", "type": "title"},
                    {"name": "Status", "type": "select", "options": ["Active", "Completed", "Archived"]},
                    {"name": "Priority", "type": "select", "options": ["High", "Medium", "Low"]},
                ],
                "blocks": [
                    {"type": "callout", "emoji": "✨", "text": f"Your new {category} template. Add your items, customize the views, and get to work."},
                ],
            },
            "sample_data": [
                {"Item": "Sample item 1", "Status": "Active", "Priority": "High"},
                {"Item": "Sample item 2", "Status": "Active", "Priority": "Medium"},
            ],
            "seo_description": f"A premium Notion {category} template designed for productivity and organization.",
            "tags": [category.lower(), "Notion template", "productivity", "organization"],
        }
