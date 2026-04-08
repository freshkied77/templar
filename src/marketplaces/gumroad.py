"""
Gumroad marketplace integration.
API docs: https://app.gumroad.com/api
"""

import os
import httpx
from typing import Optional

from .base import BaseMarketplace, ListingStatus, SaleRecord


class GumroadMarketplace(BaseMarketplace):
    name = "gumroad"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GUMROAD_API_KEY")
        self.base_url = "https://api.gumroad.com/v1"

    def authenticate(self, credentials: dict) -> bool:
        if not self.api_key:
            self.api_key = credentials.get("api_key")
        resp = httpx.get(
            f"{self.base_url}/user",
            params={"access_token": self.api_key},
            timeout=10,
        )
        return resp.status_code == 200

    def list_product(self, product_data: dict) -> str:
        """Create a Gumroad product. Returns the product permalink."""
        formatted = self.format_for_marketplace(product_data)
        resp = httpx.post(
            f"{self.base_url}/products",
            params={"access_token": self.api_key},
            json={
                "name": formatted["title"],
                "description": formatted["description"],
                "price": int(formatted["price"] * 100),  # Gumroad uses cents
                "tags": formatted["tags"],
                "custom_preview": formatted["cover_image"],
                "is_description_limited": False,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            raise Exception(f"Gumroad API error: {resp.status_code} — {resp.text}")
        return resp.json().get("permalink", "")

    def delist_product(self, listing_id: str) -> bool:
        """Archive a Gumroad product."""
        resp = httpx.post(
            f"{self.base_url}/products/{listing_id}/archive",
            params={"access_token": self.api_key},
            timeout=10,
        )
        return resp.status_code == 200

    def get_listing_status(self, listing_id: str) -> ListingStatus:
        resp = httpx.get(
            f"{self.base_url}/products/{listing_id}",
            params={"access_token": self.api_key},
            timeout=10,
        )
        if resp.status_code != 200:
            return ListingStatus.UNKNOWN
        data = resp.json().get("product", {})
        if data.get("archived"):
            return ListingStatus.DELISTED
        return ListingStatus.ACTIVE

    def get_sales_data(self, timeframe: int = 7) -> list[SaleRecord]:
        from datetime import datetime, timedelta, timezone
        resp = httpx.get(
            f"{self.base_url}/sales",
            params={
                "access_token": self.api_key,
                "after": f"{(datetime.now(timezone.utc) - timedelta(days=timeframe)).strftime('%Y-%m-%d')}",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        sales = []
        for s in resp.json().get("sales", []):
            sales.append(SaleRecord(
                listing_id=s.get("product_permalink", ""),
                marketplace=self.name,
                quantity=s.get("quantity", 1),
                revenue=s.get("amount", 0) / 100,
                currency=s.get("currency", "USD"),
                timestamp=s.get("created_at", ""),
            ))
        return sales
