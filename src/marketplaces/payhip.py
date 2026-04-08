"""
Payhip marketplace integration.
API docs: https://payhip.com/docs
"""

import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional

from .base import BaseMarketplace, ListingStatus, SaleRecord


class PayhipMarketplace(BaseMarketplace):
    name = "payhip"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PAYHIP_API_KEY")
        self.base_url = "https://payhip.com/api/v1"

    def authenticate(self, credentials: dict) -> bool:
        if not self.api_key:
            self.api_key = credentials.get("api_key")
        resp = httpx.get(
            f"{self.base_url}/account",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        return resp.status_code == 200

    def list_product(self, product_data: dict) -> str:
        """Create a Payhip product. Returns the product link."""
        formatted = self.format_for_marketplace(product_data)
        resp = httpx.post(
            f"{self.base_url}/products",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "name": formatted["title"],
                "description": formatted["description"],
                "price": formatted["price"],
                "tags": formatted["tags"],
            },
            timeout=30,
        )
        if resp.status_code != 201:
            raise Exception(f"Payhip API error: {resp.status_code} — {resp.text}")
        data = resp.json()
        return data.get("data", {}).get("link", "")

    def delist_product(self, listing_id: str) -> bool:
        resp = httpx.delete(
            f"{self.base_url}/products/{listing_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        return resp.status_code in (200, 204)

    def get_listing_status(self, listing_id: str) -> ListingStatus:
        resp = httpx.get(
            f"{self.base_url}/products/{listing_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return ListingStatus.UNKNOWN
        data = resp.json().get("data", {})
        if data.get("is_deleted"):
            return ListingStatus.DELISTED
        return ListingStatus.ACTIVE

    def get_sales_data(self, timeframe: int = 7) -> list[SaleRecord]:
        resp = httpx.get(
            f"{self.base_url}/sales",
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={"after": (datetime.now(timezone.utc) - timedelta(days=timeframe)).strftime("%Y-%m-%d")},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        sales = []
        for s in resp.json().get("data", []):
            sales.append(SaleRecord(
                listing_id=s.get("product_link", ""),
                marketplace=self.name,
                quantity=s.get("quantity", 1),
                revenue=s.get("earnings", 0),
                currency="USD",
                timestamp=s.get("created_at", ""),
            ))
        return sales
