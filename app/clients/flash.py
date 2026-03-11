"""Flash client — reality-writing engine API.

Handles timepoint generation (14-agent pipeline) and credit balance checks.
"""

import logging

import httpx

logger = logging.getLogger("mcp.clients.flash")


class FlashClient:
    """HTTP client for the Flash reality-writing engine."""

    def __init__(self, base_url: str, service_key: str):
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self._client = httpx.AsyncClient(timeout=90.0)  # generation can take 15-60s

    async def close(self):
        await self._client.aclose()

    def _headers(self, user_id: str | None = None) -> dict:
        h = {"X-Service-Key": self.service_key}
        if user_id:
            h["X-User-ID"] = user_id
        return h

    async def get_balance(self, user_id: str) -> dict:
        """Get credit balance for a user.

        Returns dict with at least 'balance' (int) and 'tier' (str).
        """
        url = f"{self.base_url}/api/v1/credits/balance"
        resp = await self._client.get(url, headers=self._headers(user_id))
        resp.raise_for_status()
        return resp.json()

    async def generate_sync(
        self,
        query: str,
        preset: str = "balanced",
        user_id: str | None = None,
    ) -> dict:
        """Generate a timepoint synchronously via Flash's 14-agent pipeline.

        This is a blocking call that can take 15-60 seconds.
        Returns the full TimepointResponse from Flash.
        """
        url = f"{self.base_url}/api/v1/timepoints/generate/sync"
        payload = {
            "query": query,
            "preset": preset,
        }
        resp = await self._client.post(
            url,
            json=payload,
            headers=self._headers(user_id),
        )
        resp.raise_for_status()
        return resp.json()
