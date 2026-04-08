"""
Etsy marketplace integration.
API docs: https://developers.etsy.com/documentation

OAuth: After running `python -m src.marketplaces.etsy_auth` once,
the access token and secret are stored in your .env file.
The adapter uses these directly — no OAuth library needed.

Etsy API quirks:
- All listing creation starts as "draft" and requires manual review
- Listings go through content moderation before going live
- Max 13 tags per listing
- taxonomy_id 1529 = Digital Items > Templates > Notion
"""

import os
import httpx
from datetime import datetime, timedelta, timezone
from typing import Optional

from .base import BaseMarketplace, ListingStatus, SaleRecord

# ── OAuth signing ───────────────────────────────────────────────────────────────

from .etsy_oauth import build_signed_params

ETSY_BASE_URL = "https://api.etsy.com/v3"
HEADERS_BASE = {"Content-Type": "application/json", "Accept": "application/json"}


class EtsyMarketplace(BaseMarketplace):
    name = "etsy"

    def __init__(
        self,
        consumer_key: Optional[str] = None,
        consumer_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        access_secret: Optional[str] = None,
        shop_id: Optional[str] = None,
    ):
        self.api_key = consumer_key or os.getenv("ETSY_CONSUMER_KEY")
        self.consumer_secret = consumer_secret or os.getenv("ETSY_CONSUMER_SECRET")
        self.access_token = access_token or os.getenv("ETSY_ACCESS_TOKEN")
        self.access_secret = access_secret or os.getenv("ETSY_ACCESS_SECRET")
        self.shop_id = shop_id or os.getenv("ETSY_SHOP_ID")
        self.base_url = ETSY_BASE_URL

    def _auth_headers(self, method: str, path: str, extra_params: dict = None) -> dict:
        """Build authorization headers with OAuth 1.0a HMAC-SHA1 signature."""
        url = f"{self.base_url}{path}"
        params = build_signed_params(
            method=method,
            url=url,
            consumer_key=self.api_key,
            consumer_secret=self.consumer_secret,
            oauth_token=self.access_token,
            oauth_secret=self.access_secret,
            extra_params=extra_params or {},
        )
        headers = dict(HEADERS_BASE)
        headers["x-api-key"] = self.api_key
        headers["Authorization"] = "Bearer " + self.access_token  # Bearer works alongside OAuth
        return headers

    def authenticate(self, credentials: dict = None) -> bool:
        """Verify the stored access token by fetching user info."""
        if not self.access_token or not self.api_key:
            return False
        try:
            headers = self._auth_headers("GET", "/application/user")
            resp = httpx.get(
                f"{self.base_url}/application/user",
                headers=headers,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def list_product(self, product_data: dict) -> str:
        """Create an Etsy listing (as draft). Requires manual publish after moderation."""
        formatted = self.format_for_marketplace(product_data)
        headers = self._auth_headers("POST", f"/applications/shops/{self.shop_id}/listings")

        payload = {
            "quantity": 999,
            "title": formatted["title"][:140],  # Etsy title max 140 chars
            "description": formatted["description"],
            "price": {"amount": int(formatted["price"] * 100), "divisor": 100, "currency_code": "USD"},
            "tags": formatted["tags"][:13],  # Etsy max 13 tags
            "taxonomy_id": 1529,  # Digital > Templates > Notion
            "listing_state": "draft",  # Always draft — goes through moderation
            "is_customizable": True,
        }

        resp = httpx.post(
            f"{self.base_url}/applications/shops/{self.shop_id}/listings",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            raise Exception(f"Etsy API error: {resp.status_code} — {resp.text}")
        return str(resp.json().get("listing_id", ""))

    def delist_product(self, listing_id: str) -> bool:
        """Deactivate an Etsy listing."""
        headers = self._auth_headers("PUT", f"/applications/shops/{self.shop_id}/listings/{listing_id}")
        resp = httpx.put(
            f"{self.base_url}/applications/shops/{self.shop_id}/listings/{listing_id}",
            headers=headers,
            json={"state": "inactive"},
            timeout=10,
        )
        return resp.status_code == 200

    def publish_listing(self, listing_id: str) -> bool:
        """
        Attempt to publish a draft listing.
        Note: Etsy may require manual review before publishing.
        This will raise an exception if moderation rejects the content.
        """
        headers = self._auth_headers("PUT", f"/applications/shops/{self.shop_id}/listings/{listing_id}")
        resp = httpx.put(
            f"{self.base_url}/applications/shops/{self.shop_id}/listings/{listing_id}",
            headers=headers,
            json={"state": "active"},
            timeout=10,
        )
        if resp.status_code == 200:
            return True
        # Moderation rejection or other error
        raise Exception(f"Etsy publish failed: {resp.status_code} — {resp.text}")

    def get_listing_status(self, listing_id: str) -> ListingStatus:
        """Check Etsy listing state."""
        headers = self._auth_headers("GET", f"/applications/shops/{self.shop_id}/listings/{listing_id}")
        resp = httpx.get(
            f"{self.base_url}/applications/shops/{self.shop_id}/listings/{listing_id}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return ListingStatus.UNKNOWN
        state = resp.json().get("state", "")
        return {
            "active": ListingStatus.ACTIVE,
            "draft": ListingStatus.DRAFT,
            "inactive": ListingStatus.DELISTED,
            "archived": ListingStatus.DELISTED,
            "sold_out": ListingStatus.DELISTED,
        }.get(state, ListingStatus.UNKNOWN)

    def get_sales_data(self, timeframe: int = 7) -> list[SaleRecord]:
        """Fetch orders from Etsy API (requires OAuth signature)."""
        after = (datetime.now(timezone.utc) - timedelta(days=timeframe)).strftime("%Y-%m-%d")
        headers = self._auth_headers("GET", f"/applications/shops/{self.shop_id}/orders")
        resp = httpx.get(
            f"{self.base_url}/applications/shops/{self.shop_id}/orders",
            headers=headers,
            params={"created_after": after, "was_shipped": False},
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        sales = []
        for s in resp.json().get("results", []):
            for item in s.get("line_items", []):
                sales.append(SaleRecord(
                    listing_id=str(item.get("listing_id", "")),
                    marketplace=self.name,
                    quantity=item.get("quantity", 1),
                    revenue=float(item.get("price", {}).get("amount", 0)) / 100,
                    currency=item.get("price", {}).get("currency", "USD"),
                    timestamp=s.get("created_timestamp", ""),
                    buyer_email=s.get("buyer_email", ""),
                ))
        return sales

    def get_moderation_status(self, listing_id: str) -> dict:
        """Check if a draft listing has been reviewed by Etsy moderation."""
        headers = self._auth_headers("GET", f"/applications/shops/{self.shop_id}/listings/{listing_id}/moderation")
        resp = httpx.get(
            f"{self.base_url}/applications/shops/{self.shop_id}/listings/{listing_id}/moderation",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"status": "unknown"}
