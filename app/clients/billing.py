"""Billing client — subscription tier/status lookup for MCP users."""

import logging

import httpx

logger = logging.getLogger("mcp.clients.billing")


class BillingClient:
    """HTTP client for internal billing endpoints."""

    def __init__(self, base_url: str, service_key: str):
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self._client = httpx.AsyncClient(timeout=20.0)

    async def close(self):
        await self._client.aclose()

    async def get_status(self, user_id: str) -> dict:
        """Get subscription status and tier for a user.

        Calls: GET /internal/billing/status
        Headers: X-Service-Key, X-User-Id
        """
        url = f"{self.base_url}/internal/billing/status"
        headers = {
            "X-Service-Key": self.service_key,
            "X-User-Id": user_id,
        }
        resp = await self._client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        logger.debug("billing status fetched for user_id=%s", user_id)
        return data
