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

    def _read_base(self) -> str:
        """Base URL for read tools (search/browse/today/random/neighbors/get_moment/stats).

        These hit Clockchain's own ``/api/v1/*`` endpoints directly via
        ``CLOCKCHAIN_URL``. There is NO ``/api/v1/clockchain/*`` read proxy on
        Flash — that path 404s — so the legacy proxy is only a last-resort
        fallback when CLOCKCHAIN_URL is unconfigured.
        """
        return self._direct_base()

    def _read_headers(self, user_id: str | None = None) -> dict:
        """Headers for direct Clockchain reads.

        Sends ``X-Service-Key`` (CLOCKCHAIN_SERVICE_KEY) so service-key-gated
        endpoints (browse/today/random/neighbors) authenticate. Falls back to
        the Flash outbound key when reads are routed through the proxy base
        (CLOCKCHAIN_URL unset).
        """
        if self.direct_url:
            h = dict(self._direct_headers())
        else:
            h = dict(self._proxy_headers())
        if user_id:
            h["X-User-ID"] = user_id
        return h

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
        """Search moments directly against Clockchain's public /api/v1/search.

        The Clockchain search endpoint caps limit at 50 (``le=50``); clamp here so
        a larger MCP-side request doesn't 422 the upstream call.
        """
        url = f"{self._read_base()}/search"
        capped = min(max(limit, 1), 50)
        data = await self._get(url, self._read_headers(user_id), params={"q": query, "limit": capped})
        if isinstance(data, list):
            return data[:limit]
        if isinstance(data, dict) and "error" in data:
            return data
        return data.get("items", data.get("results", []))[:limit]

    async def get_moment(self, path: str, format: str = "default") -> dict:
        """Get moment detail from Clockchain /api/v1/moments/{path}."""
        clean_path = path.strip("/")
        url = f"{self._read_base()}/moments/{clean_path}"
        params = {"format": format} if format != "default" else None
        return await self._get(url, self._read_headers(), params)

    async def browse(self, path: str = "") -> dict:
        """Browse graph hierarchy via Clockchain /api/v1/browse. Requires service key."""
        clean_path = path.strip("/")
        if clean_path:
            url = f"{self._read_base()}/browse/{clean_path}"
        else:
            url = f"{self._read_base()}/browse"
        return await self._get(url, self._read_headers())

    async def neighbors(self, path: str) -> dict:
        """Get graph neighbors via Clockchain /api/v1/graph/neighbors. Requires service key."""
        clean_path = path.strip("/")
        url = f"{self._read_base()}/graph/neighbors/{clean_path}"
        return await self._get(url, self._read_headers())

    async def traverse(
        self,
        path: str,
        direction: str = "both",
        depth: int = 2,
        edge_types: str | None = None,
        limit: int = 50,
        min_weight: float = 0.0,
    ) -> dict:
        """Multi-hop BFS subgraph via Clockchain /api/v1/graph/traverse. Requires service key.

        Clamps depth to 1..4 and limit to 1..200 client-side so oversized MCP
        requests don't 422 the upstream call (upstream caps are depth 4 /
        limit 500; we keep MCP payloads smaller).
        """
        clean_path = path.strip("/")
        url = f"{self._read_base()}/graph/traverse/{clean_path}"
        params = {
            "direction": direction,
            "depth": min(max(depth, 1), 4),
            "limit": min(max(limit, 1), 200),
        }
        if edge_types:
            params["edge_types"] = edge_types
        if min_weight:
            params["min_weight"] = min_weight
        return await self._get(url, self._read_headers(), params)

    async def path(
        self,
        from_path: str,
        to_path: str,
        max_hops: int = 6,
        edge_types: str | None = None,
    ) -> dict:
        """Shortest connection path via Clockchain /api/v1/graph/path. Requires service key.

        Clamps max_hops to 1..10 client-side (upstream cap is 10).
        """
        url = f"{self._read_base()}/graph/path"
        params = {
            "from": from_path.strip("/"),
            "to": to_path.strip("/"),
            "max_hops": min(max(max_hops, 1), 10),
        }
        if edge_types:
            params["edge_types"] = edge_types
        return await self._get(url, self._read_headers(), params)

    async def today(self) -> dict:
        """Today in history via Clockchain /api/v1/today. Requires service key."""
        url = f"{self._read_base()}/today"
        return await self._get(url, self._read_headers())

    async def random(self) -> dict:
        """Random public moment via Clockchain /api/v1/random. Requires service key."""
        url = f"{self._read_base()}/random"
        return await self._get(url, self._read_headers())

    async def stats(self) -> dict:
        """Graph stats via Clockchain /api/v1/stats. Public endpoint."""
        url = f"{self._read_base()}/stats"
        return await self._get(url, self._read_headers())

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
