"""
Lemonsqueezy marketplace integration.
API docs: https://api.lemonsqueezy.com
"""

import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional

from .base import BaseMarketplace, ListingStatus, SaleRecord


class LemonSqueezyMarketplace(BaseMarketplace):
    name = "lemonsqueezy"

    def __init__(self, api_key: Optional[str] = None, store_id: Optional[str] = None):
        self.api_key = api_key or os.getenv("LEMONSQUEEZY_API_KEY")
        self.store_id = store_id or os.getenv("LEMONSQUEEZY_STORE_ID")
        self.base_url = "https://api.lemonsqueezy.com/v1"
        self.headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def authenticate(self, credentials: dict) -> bool:
        if not self.api_key:
            self.api_key = credentials.get("api_key")
        resp = httpx.get(
            f"{self.base_url}/stores",
            headers=self.headers,
            timeout=10,
        )
        return resp.status_code == 200

    def list_product(self, product_data: dict) -> str:
        """Create a Lemonsqueezy product and variants. Returns the variant ID."""
        formatted = self.format_for_marketplace(product_data)
        resp = httpx.post(
            f"{self.base_url}/products",
            headers=self.headers,
            json={
                "data": {
                    "type": "products",
                    "attributes": {
                        "name": formatted["title"],
                        "description": formatted["description"],
                        "store_id": int(self.store_id) if self.store_id else None,
                        "status": "published",
                    },
                    "relationships": {
                        "variants": {
                            "data": [{
                                "type": "variants",
                                "attributes": {
                                    "name": "Default",
                                    "price": int(formatted["price"]),
                                    "currency": "USD",
                                },
                            }],
                        },
                    },
                },
            },
            timeout=30,
        )
        if resp.status_code != 201:
            raise Exception(f"Lemonsqueezy API error: {resp.status_code} — {resp.text}")
        data = resp.json()
        variants = data.get("data", {}).get("relationships", {}).get("variants", {}).get("data", [])
        return str(variants[0].get("id", "")) if variants else ""

    def delist_product(self, listing_id: str) -> bool:
        """Archive a Lemonsqueezy product."""
        resp = httpx.patch(
            f"{self.base_url}/products/{listing_id}",
            headers=self.headers,
            json={"data": {"type": "products", "attributes": {"status": "draft"}}},
            timeout=10,
        )
        return resp.status_code == 200

    def get_listing_status(self, listing_id: str) -> ListingStatus:
        resp = httpx.get(
            f"{self.base_url}/products/{listing_id}",
            headers=self.headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return ListingStatus.UNKNOWN
        data = resp.json().get("data", {})
        if data.get("attributes", {}).get("status") == "draft":
            return ListingStatus.DELISTED
        return ListingStatus.ACTIVE

    def get_sales_data(self, timeframe: int = 7) -> list[SaleRecord]:
        resp = httpx.get(
            f"{self.base_url}/orders",
            headers=self.headers,
            params={
                "filter[created_at][gte]": (datetime.now(timezone.utc) - timedelta(days=timeframe)).strftime("%Y-%m-%d"),
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        sales = []
        for s in resp.json().get("data", []):
            attrs = s.get("attributes", {})
            sales.append(SaleRecord(
                listing_id=str(s.get("relationships", {}).get("variant", {}).get("data", {}).get("id", "")),
                marketplace=self.name,
                quantity=attrs.get("quantity", 1),
                revenue=attrs.get("total", 0) / 100,
                currency=attrs.get("currency", "USD"),
                timestamp=attrs.get("created_at", ""),
            ))
        return sales
