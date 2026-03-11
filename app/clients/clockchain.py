import logging

import httpx

logger = logging.getLogger("mcp.clients.clockchain")


class ClockchainClient:
    """HTTP client for the Clockchain temporal graph API."""

    def __init__(
        self,
        flash_proxy_url: str,
        flash_service_key: str,
        direct_url: str = "",
        direct_service_key: str = "",
    ):
        self.flash_proxy_url = flash_proxy_url.rstrip("/")
        self.flash_service_key = flash_service_key
        self.direct_url = direct_url.rstrip("/") if direct_url else ""
        self.direct_service_key = direct_service_key
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._client.aclose()

    def _proxy_headers(self, user_id: str | None = None) -> dict:
        h = {"X-Service-Key": self.flash_service_key}
        if user_id:
            h["X-User-ID"] = user_id
        return h

    def _direct_headers(self) -> dict:
        if self.direct_service_key:
            return {"X-Service-Key": self.direct_service_key}
        return {}

    def _proxy_base(self) -> str:
        return f"{self.flash_proxy_url}/api/v1/clockchain"

    def _direct_base(self) -> str:
        return f"{self.direct_url}/api/v1" if self.direct_url else self._proxy_base()

    async def _get(self, url: str, headers: dict, params: dict | None = None) -> dict | list:
        resp = await self._client.get(url, headers=headers, params=params)
        if resp.status_code == 404:
            return {"error": "not_found", "detail": "Resource not found"}
        resp.raise_for_status()
        return resp.json()

    async def _post(self, url: str, headers: dict, json: dict | None = None) -> dict:
        resp = await self._client.post(url, headers=headers, json=json)
        if resp.status_code == 404:
            return {"error": "not_found", "detail": "Resource not found"}
        resp.raise_for_status()
        return resp.json()

    async def _patch(self, url: str, headers: dict, json: dict | None = None) -> dict:
        resp = await self._client.patch(url, headers=headers, json=json)
        if resp.status_code == 404:
            return {"error": "not_found", "detail": "Resource not found"}
        resp.raise_for_status()
        return resp.json()

    async def search(self, query: str, limit: int = 20, user_id: str | None = None) -> list:
        """Search moments. Uses Flash proxy (requires service key for search endpoint)."""
        url = f"{self._proxy_base()}/search"
        data = await self._get(url, self._proxy_headers(user_id), params={"q": query})
        if isinstance(data, list):
            return data[:limit]
        return data.get("items", data.get("results", []))[:limit]

    async def get_moment(self, path: str, format: str = "default") -> dict:
        """Get moment detail. Uses public endpoint when available."""
        clean_path = path.strip("/")
        base = self._direct_base()
        url = f"{base}/moments/{clean_path}"
        params = {"format": format} if format != "default" else None
        headers = self._direct_headers()
        # Try direct first (public), fall back to proxy
        try:
            return await self._get(url, headers, params)
        except httpx.HTTPStatusError:
            if self.direct_url:
                url = f"{self._proxy_base()}/moments/{clean_path}"
                return await self._get(url, self._proxy_headers(), params)
            raise

    async def browse(self, path: str = "") -> dict:
        """Browse graph hierarchy. Requires service key."""
        clean_path = path.strip("/")
        if clean_path:
            url = f"{self._proxy_base()}/browse/{clean_path}"
        else:
            url = f"{self._proxy_base()}/browse"
        return await self._get(url, self._proxy_headers())

    async def neighbors(self, path: str) -> dict:
        """Get graph neighbors. Requires service key."""
        clean_path = path.strip("/")
        url = f"{self._proxy_base()}/graph/neighbors/{clean_path}"
        return await self._get(url, self._proxy_headers())

    async def today(self) -> dict:
        """Today in history. Requires service key."""
        url = f"{self._proxy_base()}/today"
        return await self._get(url, self._proxy_headers())

    async def random(self) -> dict:
        """Random public moment. Requires service key."""
        url = f"{self._proxy_base()}/random"
        return await self._get(url, self._proxy_headers())

    async def stats(self) -> dict:
        """Graph stats. Public endpoint."""
        base = self._direct_base()
        url = f"{base}/stats"
        return await self._get(url, self._direct_headers())

    async def index_moment(self, payload: dict, user_id: str) -> dict:
        """Index a new moment into the clockchain.

        Posts to /api/v1/index with created_by set to user_id.
        """
        url = f"{self._proxy_base()}/index"
        payload["created_by"] = user_id
        return await self._post(url, self._proxy_headers(user_id), json=payload)

    async def update_visibility(self, path: str, visibility: str, user_id: str) -> dict:
        """Update the visibility of a moment (e.g. private -> public).

        Requires ownership — clockchain verifies created_by matches user_id.
        """
        clean_path = path.strip("/")
        url = f"{self._proxy_base()}/moments/{clean_path}/visibility"
        payload = {"visibility": visibility, "user_id": user_id}
        return await self._patch(url, self._proxy_headers(user_id), json=payload)

    async def ingest_tdf(self, tdf_record: dict) -> dict:
        """Ingest a TDF record directly into the clockchain."""
        url = f"{self._proxy_base()}/ingest/tdf"
        return await self._post(url, self._proxy_headers(), json=tdf_record)
