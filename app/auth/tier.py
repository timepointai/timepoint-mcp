"""Tier resolution helper.

Resolves subscription tier from Billing with short-lived in-memory caching.
"""

import time

from app.clients.billing import BillingClient


class TierResolver:
    def __init__(self, billing_client: BillingClient | None, ttl_seconds: int = 60):
        self.billing_client = billing_client
        self.ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[float, str]] = {}

    async def resolve_tier(self, user_id: str) -> str:
        """Return tier name: free/explorer/creator/studio.

        Falls back to free on any billing error/missing status.
        """
        now = time.monotonic()
        cached = self._cache.get(user_id)
        if cached and cached[0] > now:
            return cached[1]

        tier = "free"
        if self.billing_client is not None:
            try:
                status = await self.billing_client.get_status(user_id)
                sub_tier = (status.get("subscription_tier") or "free").lower()
                sub_status = (status.get("status") or "").lower()
                if sub_status == "active" and sub_tier in {"free", "explorer", "creator", "studio"}:
                    tier = sub_tier
            except Exception:
                tier = "free"

        self._cache[user_id] = (now + self.ttl_seconds, tier)
        return tier
