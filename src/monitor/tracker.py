"""
Sales and listing tracker.
Periodically syncs with marketplace APIs and maintains local state.
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..agent.memory import AgentMemory

log = logging.getLogger("templar.monitor")


class SalesTracker:
    """Tracks sales across all marketplaces and updates memory with performance data."""

    def __init__(self, memory: Optional[AgentMemory] = None):
        self.memory = memory or AgentMemory()

    def sync_all_sales(self, marketplaces: dict, timeframe: int = 7) -> dict:
        """Fetch sales from all marketplaces and update category weights."""
        results = {}
        category_sales = {}

        for name, mp in marketplaces.items():
            try:
                sales = mp.get_sales_data(timeframe=timeframe)
                results[name] = {"fetched": len(sales), "sales": sales}
                for sale in sales:
                    category = self.memory._get_listing_category(sale.listing_id, name) or "unknown"
                    category_sales.setdefault(category, []).append(sale.quantity)
                    self.memory.record_sales(sale.listing_id, name, sale.quantity)
                log.info(f"{name}: fetched {len(sales)} sales")
            except Exception as e:
                log.error(f"Failed to fetch sales from {name}: {e}")
                results[name] = {"error": str(e)}

        self._update_category_weights(category_sales)
        return results

    def _update_category_weights(self, category_sales: dict) -> None:
        """Update category performance weights based on sales data."""
        import sqlite3
        conn = sqlite3.connect(self.memory.db_path)
        for category, sales in category_sales.items():
            if not sales:
                continue
            total_sales = sum(sales)
            row = conn.execute(
                "SELECT total_listings, total_revenue FROM category_weights WHERE category = ?",
                (category,),
            ).fetchone()
            listings = row["total_listings"] if row else 1
            revenue = row["total_revenue"] if row else 0.0
            conversion = total_sales / listings if listings > 0 else 0.0
            avg_price = revenue / total_sales if total_sales > 0 else 19.0
            self.memory.update_category_weight(
                category,
                total_listings=listings,
                total_sales=total_sales,
                total_revenue=revenue,
                conversion_rate=conversion,
                avg_price=avg_price,
            )
        conn.close()

    def get_performance_summary(self) -> dict:
        """Return performance summary across all categories and marketplaces."""
        stats = self.memory.get_total_stats()
        listings = self.memory.get_all_listings()
        exceptions = self.memory.get_open_exceptions()

        # Sales + revenue by marketplace
        sales_by_mp = {}
        revenue_by_mp = {}
        for listing in listings:
            mp = listing["marketplace"]
            if mp not in sales_by_mp:
                sales_by_mp[mp] = 0
                revenue_by_mp[mp] = 0.0
            sales_by_mp[mp] += listing["sales_count"]
            revenue_by_mp[mp] += listing["revenue"] or 0

        # Sales + revenue by category
        sales_by_cat = {}
        revenue_by_cat = {}
        for listing in listings:
            cat = listing["category"]
            if cat not in sales_by_cat:
                sales_by_cat[cat] = 0
                revenue_by_cat[cat] = 0.0
            sales_by_cat[cat] += listing["sales_count"]
            revenue_by_cat[cat] += listing["revenue"] or 0

        # Listings by status
        active = [l for l in listings if l["status"] == "active"]
        delisted = [l for l in listings if l["status"] == "delisted"]

        return {
            "stats": stats,
            "listings": listings,
            "active_listings": active,
            "exceptions": exceptions,
            "sales_by_marketplace": sales_by_mp,
            "revenue_by_marketplace": revenue_by_mp,
            "sales_by_category": sales_by_cat,
            "revenue_by_category": revenue_by_cat,
            "total_listings_count": len(listings),
            "active_count": len(active),
            "delisted_count": len(delisted),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
