"""
Exception detection and alerting.
Flags anomalies, listing failures, and system errors.
"""

import logging
from datetime import datetime
from typing import Optional

from ..agent.memory import AgentMemory

log = logging.getLogger("templar.exceptions")


class ExceptionDetector:
    """Detects and logs exceptions from marketplace operations and system state."""

    def __init__(self, memory: Optional[AgentMemory] = None):
        self.memory = memory or AgentMemory()
        self.last_check: Optional[datetime] = None

    def detect_listing_failure(self, marketplace: str, template_title: str, error: str) -> None:
        """Flag when a listing fails to post."""
        self.memory.log_exception(
            title=f"Listing failed on {marketplace}",
            description=f"Template: {template_title}. Error: {error}",
            severity="high",
        )
        log.error(f"Listing failure on {marketplace}: {error}")

    def detect_sales_anomaly(self, marketplace: str, listing_id: str, expected: int, actual: int) -> None:
        """Flag when sales deviate significantly from expectation."""
        if actual > expected * 3:  # 3x spike
            self.memory.log_exception(
                title=f"Sales spike on {marketplace}",
                description=f"Listing {listing_id}: expected ~{expected}, got {actual}. Check for fraud or API error.",
                severity="medium",
            )
        elif actual == 0 and expected > 0:  # Unexpected drop
            self.memory.log_exception(
                title=f"Sales drop on {marketplace}",
                description=f"Listing {listing_id}: expected {expected}, got 0. May indicate listing suspension.",
                severity="medium",
            )

    def detect_marketplace_auth_failure(self, marketplace: str) -> None:
        """Flag when marketplace authentication fails."""
        self.memory.log_exception(
            title=f"Marketplace auth failure: {marketplace}",
            description=f"API authentication failed for {marketplace}. Check API keys.",
            severity="high",
        )

    def detect_api_outage(self, marketplace: str, consecutive_failures: int) -> None:
        """Flag when a marketplace API appears to be down."""
        self.memory.log_exception(
            title=f"Possible API outage: {marketplace}",
            description=f"{consecutive_failures} consecutive API failures. System may need manual intervention.",
            severity="high",
        )

    def detect_rejected_listing(self, marketplace: str, reason: str) -> None:
        """Flag when a listing is rejected by marketplace moderation."""
        self.memory.log_exception(
            title=f"Listing rejected: {marketplace}",
            description=f"Moderation rejection reason: {reason}",
            severity="medium",
        )

    def get_open_exceptions(self) -> list:
        return self.memory.get_open_exceptions()

    def resolve(self, exception_id: int) -> None:
        self.memory.resolve_exception(exception_id)
        log.info(f"Exception {exception_id} marked as resolved")
