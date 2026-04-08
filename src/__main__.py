"""
Templar — AI Digital Product System
Main entry point. Run the agent loop or dashboard.

Usage:
    python -m src              # Run agent (default interval)
    python -m src --fast       # Run with 60s interval for testing
    python -m src.dashboard    # Run dashboard only
    python -m src.marketplaces.etsy_auth  # Authorize Etsy OAuth
"""

import sys
import argparse
import logging
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.orchestrator import Orchestrator
from src.agent.memory import AgentMemory
from src.agent.tools import build_tool_registry
from src.generators.notion_template import NotionTemplateGenerator
from src.marketplaces.gumroad import GumroadMarketplace
from src.marketplaces.payhip import PayhipMarketplace
from src.marketplaces.lemonsqueezy import LemonSqueezyMarketplace
from src.marketplaces.etsy import EtsyMarketplace
from src.monitor.tracker import SalesTracker
from src.dashboard.app import app as dashboard_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Etsy is included. Run `python -m src.marketplaces.etsy_auth` first to authorize.


def run_agent(loop_interval: int = 300) -> None:
    """Initialize and run the autonomous agent."""
    memory = AgentMemory()
    tracker = SalesTracker(memory=memory)

    generators = {
        "notion_template": NotionTemplateGenerator(),
    }

    # Build marketplace dict — Etsy included if credentials are set
    marketplaces = {
        "gumroad": GumroadMarketplace(),
        "payhip": PayhipMarketplace(),
        "lemonsqueezy": LemonSqueezyMarketplace(),
    }

    # Add Etsy if credentials are available
    etsy = EtsyMarketplace()
    if etsy.access_token and etsy.shop_id:
        marketplaces["etsy"] = etsy
        logging.info("Etsy marketplace enabled (OAuth authorized)")
    else:
        logging.info("Etsy marketplace skipped — run `python -m src.marketplaces.etsy_auth` to enable")

    orchestrator = Orchestrator(memory=memory, loop_interval=loop_interval)
    orchestrator.run(generators=generators, marketplaces=marketplaces)


def run_dashboard() -> None:
    """Run the web dashboard only."""
    import uvicorn
    import os
    port = int(os.getenv("DASHBOARD_PORT", 5000))
    uvicorn.run(dashboard_app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Templar — Autonomous Digital Product System")
    parser.add_argument("--fast", action="store_true", help="Run agent with 60s loop interval")
    parser.add_argument("--dashboard", action="store_true", help="Run dashboard only")
    args = parser.parse_args()

    if args.dashboard:
        run_dashboard()
    else:
        interval = 60 if args.fast else 300
        run_agent(loop_interval=interval)
