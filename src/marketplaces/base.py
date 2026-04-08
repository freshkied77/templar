"""
Base marketplace interface.
All marketplace integrations implement this contract.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class ListingStatus(Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    DELISTED = "delisted"
    SUSPENDED = "suspended"
    UNKNOWN = "unknown"


@dataclass
class SaleRecord:
    listing_id: str
    marketplace: str
    quantity: int
    revenue: float
    currency: str
    timestamp: str
    buyer_email: Optional[str] = None


@dataclass
class ListingResult:
    success: bool
    listing_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class BaseMarketplace(ABC):
    """Abstract interface all marketplace integrations must implement."""

    name: str = "base"

    @abstractmethod
    def authenticate(self, credentials: dict) -> bool:
        """Test and validate API credentials. Returns True if valid."""
        pass

    @abstractmethod
    def list_product(self, product_data: dict) -> str:
        """Create a new listing. Returns the marketplace listing_id."""
        pass

    @abstractmethod
    def delist_product(self, listing_id: str) -> bool:
        """Remove a listing. Returns True on success."""
        pass

    @abstractmethod
    def get_listing_status(self, listing_id: str) -> ListingStatus:
        """Check current status of a listing."""
        pass

    @abstractmethod
    def get_sales_data(self, timeframe: int = 7) -> list[SaleRecord]:
        """Fetch sales records for the specified timeframe (days)."""
        pass

    def update_listing(self, listing_id: str, product_data: dict) -> bool:
        """Optional: update an existing listing."""
        return False

    def format_for_marketplace(self, template: dict) -> dict:
        """Convert a Templar template dict into marketplace-specific product data."""
        return {
            "title": template.get("title", ""),
            "description": template.get("seo_description", ""),
            "price": template.get("price_suggested", 19),
            "category": template.get("category", ""),
            "tags": template.get("tags", []),
            "cover_image": template.get("cover_concept", ""),
        }
