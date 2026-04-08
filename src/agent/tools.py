"""
Tools available to the agent.
Each tool is a callable the agent can invoke as part of its reasoning.
"""

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("templar.tools")


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str = None
    tool_name: str = ""


class ToolRegistry:
    """Registry of available agent tools."""

    def __init__(self):
        self._tools: dict[str, callable] = {}

    def register(self, name: str, func: callable) -> None:
        self._tools[name] = func

    def call(self, name: str, **kwargs) -> ToolResult:
        if name not in self._tools:
            return ToolResult(success=False, error=f"Unknown tool: {name}", tool_name=name)
        try:
            result = self._tools[name](**kwargs)
            return ToolResult(success=True, data=result, tool_name=name)
        except Exception as e:
            return ToolResult(success=False, error=str(e), tool_name=name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())


def build_tool_registry(memory, generators, marketplaces) -> ToolRegistry:
    registry = ToolRegistry()

    def generate_template(category: str, description: str) -> dict:
        """Generate a Notion template from category and description."""
        generator = generators.get("notion_template")
        if not generator:
            raise ValueError("Notion template generator not available")
        template = generator.generate(category=category, description=description)
        return template

    def list_product(template: dict, marketplaces_to_use: list[str]) -> dict:
        """List a product on specified marketplaces. Returns {marketplace: listing_id}."""
        from ..generators.template_renderer import build_template_package
        results = {}
        # Build the deliverable package before listing
        try:
            package_path = build_template_package(template)
            template["_package_path"] = package_path
        except Exception as e:
            log.warning(f"Failed to build template package: {e}")
            package_path = None

        for mp_name in marketplaces_to_use:
            marketplace = marketplaces.get(mp_name)
            if not marketplace:
                results[mp_name] = {"error": f"Unknown marketplace: {mp_name}"}
                continue
            try:
                listing_id = marketplace.list_product(template)
                memory.add_listing(
                    listing_id=listing_id,
                    marketplace=mp_name,
                    category=template.get("category", "unknown"),
                    title=template.get("title", "untitled"),
                    price=template.get("price_suggested", 19),
                    url=getattr(marketplace, "base_url", None),
                )
                results[mp_name] = {"listing_id": listing_id, "package": package_path}
            except Exception as e:
                memory.log_exception(
                    title=f"Listing failed on {mp_name}",
                    description=str(e),
                    severity="high",
                )
                results[mp_name] = {"error": str(e)}
        return results

    def delist_product(listing_id: str, marketplace_name: str) -> bool:
        """Remove a product from a marketplace."""
        marketplace = marketplaces.get(marketplace_name)
        if not marketplace:
            return False
        success = marketplace.delist_product(listing_id)
        if success:
            memory.remove_listing(listing_id, marketplace_name)
        return success

    def get_sales_data(marketplace_name: str = None, timeframe: int = 7) -> list:
        """Get sales data from marketplaces. If marketplace_name is None, check all."""
        results = {}
        targets = (
            [marketplaces.get(marketplace_name)]
            if marketplace_name
            else marketplaces.values()
        )
        for mp in targets:
            if not mp:
                continue
            try:
                sales = mp.get_sales_data(timeframe=timeframe)
                results[mp.name] = sales
                for sale in sales:
                    memory.record_sales(
                        sale.listing_id,
                        mp.name,
                        sale.quantity,
                        sale.revenue,
                        sale.timestamp,
                    )
            except Exception as e:
                memory.log_exception(
                    title=f"Sales fetch failed on {mp.name}",
                    description=str(e),
                    severity="medium",
                )
        return results

    def get_listing_status(listing_id: str, marketplace_name: str) -> dict:
        """Check the status of a listing on a marketplace."""
        marketplace = marketplaces.get(marketplace_name)
        if not marketplace:
            return {"error": f"Unknown marketplace: {marketplace_name}"}
        return marketplace.get_listing_status(listing_id)

    def flag_exception(title: str, description: str, severity: str = "medium") -> int:
        """Log an exception that requires operator attention."""
        return memory.log_exception(title=title, description=description, severity=severity)

    def get_open_exceptions() -> list:
        """Return all unresolved exceptions."""
        return memory.get_open_exceptions()

    def resolve_exception(exception_id: int) -> None:
        """Mark an exception as resolved."""
        memory.resolve_exception(exception_id)

    def get_stats() -> dict:
        """Return aggregated stats."""
        return memory.get_total_stats()

    # Register all tools
    registry.register("generate_template", generate_template)
    registry.register("list_product", list_product)
    registry.register("delist_product", delist_product)
    registry.register("get_sales_data", get_sales_data)
    registry.register("get_listing_status", get_listing_status)
    registry.register("flag_exception", flag_exception)
    registry.register("get_open_exceptions", get_open_exceptions)
    registry.register("resolve_exception", resolve_exception)
    registry.register("get_stats", get_stats)

    return registry
