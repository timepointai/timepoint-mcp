"""Gateway client — credit balance checks and spending via API Gateway.

Routes all credit operations through the Gateway CreditAccount (single source
of truth) instead of Flash's legacy credit ledger.
"""

import logging

import httpx

logger = logging.getLogger("mcp.clients.gateway")


class GatewayClient:
    """HTTP client for the Gateway internal credits API."""

    def __init__(self, base_url: str, service_key: str):
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self._client = httpx.AsyncClient(timeout=20.0)

    async def close(self):
        await self._client.aclose()

    def _headers(self) -> dict:
        return {"X-Service-Key": self.service_key}

    async def check_balance(self, user_id: str, cost: int) -> dict:
        """Check if user has sufficient credits.

        GET /internal/credits/check?user_id=...&cost=...
        Returns dict with 'sufficient' (bool) and 'balance' (int).
        """
        url = f"{self.base_url}/internal/credits/check"
        resp = await self._client.get(
            url,
            params={"user_id": user_id, "cost": cost},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def spend_credits(
        self,
        user_id: str,
        cost: int,
        transaction_type: str = "generation",
        description: str | None = None,
    ) -> dict:
        """Spend credits for a user.

        POST /internal/credits/spend
        Returns dict with 'success', 'transaction_id', 'balance_after', 'error'.
        """
        url = f"{self.base_url}/internal/credits/spend"
        payload = {
            "user_id": user_id,
            "cost": cost,
            "transaction_type": transaction_type,
        }
        if description:
            payload["description"] = description
        resp = await self._client.post(
            url,
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()
