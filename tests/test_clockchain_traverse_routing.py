"""Routing tests for the temporal-navigator reads: traverse() and path().

Same fake-http injection pattern as test_clockchain_read_routing.py — pins
the new multi-hop methods to Clockchain's /api/v1/graph/traverse and
/api/v1/graph/path endpoints with the direct service key, and covers the
client-side clamps (depth<=4, limit<=200, max_hops<=10), 404 unwrapping,
and the tool-level {error, suggestion} shapes.
"""

import pytest

from app.clients.clockchain import ClockchainClient
from app.tools.clockchain import register_clockchain_tools


@pytest.fixture(autouse=True)
def _authenticated_request(monkeypatch):
    """Every tool call in this file goes through require_auth(); stub the
    header source so routing tests don't need to exercise real auth."""
    monkeypatch.setattr(
        "app.auth.require.get_http_headers",
        lambda **kwargs: {"x-api-key": "test-read-key"},
    )


class _FakeKeyStore:
    """Always validates the fixed test key with the "read" scope."""

    async def validate_key(self, api_key):
        if api_key != "test-read-key":
            return None
        return type(
            "KeyInfo", (), {"id": "k1", "user_id": "test-user", "scopes": ["read", "generate"]}
        )()


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _RecordingHTTP:
    """Captures the last GET (url, headers, params) and returns a canned payload."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self._status_code = status_code
        self.calls = []

    async def get(self, url, headers=None, params=None):
        self.calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        return _Resp(self._payload, self._status_code)

    async def aclose(self):
        return None


def _client(payload, status_code=200):
    c = ClockchainClient(
        flash_proxy_url="https://flash.timepointai.com",
        flash_service_key="flash-key",
        direct_url="https://clockchain.timepointai.com",
        direct_service_key="cc-key",
    )
    http = _RecordingHTTP(payload, status_code)
    c._client = http
    return c, http


class _FakeMCP:
    """Captures functions registered via @mcp.tool() so tests can call them."""

    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _tools(payload, status_code=200):
    c, http = _client(payload, status_code)
    mcp = _FakeMCP()
    register_clockchain_tools(mcp, c, _FakeKeyStore())
    return mcp.tools, http


# --- ClockchainClient.traverse ---


@pytest.mark.asyncio
async def test_traverse_hits_direct_graph_traverse_with_service_key():
    c, http = _client({"anchor": "/1776/july/4", "nodes": [], "edges": []})
    await c.traverse("/1776/july/4/")
    call = http.calls[-1]
    assert call["url"] == "https://clockchain.timepointai.com/api/v1/graph/traverse/1776/july/4"
    assert call["headers"]["X-Service-Key"] == "cc-key"
    assert call["params"]["direction"] == "both"
    assert call["params"]["depth"] == 2
    assert call["params"]["limit"] == 50
    assert "edge_types" not in call["params"]


@pytest.mark.asyncio
async def test_traverse_passes_direction_edge_types_and_min_weight():
    c, http = _client({"nodes": []})
    await c.traverse(
        "/1914/june/28", direction="past", depth=3,
        edge_types="causes,caused_by", limit=80, min_weight=0.5,
    )
    p = http.calls[-1]["params"]
    assert p["direction"] == "past"
    assert p["depth"] == 3
    assert p["edge_types"] == "causes,caused_by"
    assert p["limit"] == 80
    assert p["min_weight"] == 0.5


@pytest.mark.asyncio
async def test_traverse_clamps_depth_and_limit():
    c, http = _client({"nodes": []})
    await c.traverse("/x", depth=9, limit=1000)
    p = http.calls[-1]["params"]
    assert p["depth"] == 4
    assert p["limit"] == 200

    await c.traverse("/x", depth=0, limit=0)
    p = http.calls[-1]["params"]
    assert p["depth"] == 1
    assert p["limit"] == 1


@pytest.mark.asyncio
async def test_traverse_unwraps_404_to_error_dict():
    c, _ = _client({"detail": "not found"}, status_code=404)
    result = await c.traverse("/nope")
    assert result == {"error": "not_found", "detail": "Resource not found"}


# --- ClockchainClient.path ---


@pytest.mark.asyncio
async def test_path_hits_direct_graph_path_with_service_key():
    c, http = _client({"found": True, "hops": 2, "nodes": [], "edges": []})
    await c.path("/1914/june/28", "/1919/june/28")
    call = http.calls[-1]
    assert call["url"] == "https://clockchain.timepointai.com/api/v1/graph/path"
    assert call["headers"]["X-Service-Key"] == "cc-key"
    assert call["params"]["from"] == "1914/june/28"
    assert call["params"]["to"] == "1919/june/28"
    assert call["params"]["max_hops"] == 6


@pytest.mark.asyncio
async def test_path_clamps_max_hops():
    c, http = _client({"found": False})
    await c.path("/a", "/b", max_hops=99)
    assert http.calls[-1]["params"]["max_hops"] == 10

    await c.path("/a", "/b", max_hops=0)
    assert http.calls[-1]["params"]["max_hops"] == 1


@pytest.mark.asyncio
async def test_path_unwraps_404_to_error_dict():
    c, _ = _client({"detail": "not found"}, status_code=404)
    result = await c.path("/a", "/b")
    assert result == {"error": "not_found", "detail": "Resource not found"}


# --- traverse_moments tool ---


@pytest.mark.asyncio
async def test_traverse_moments_tool_returns_upstream_payload():
    payload = {
        "anchor": "/1776/july/4", "direction": "both", "depth": 2,
        "nodes": [{"id": "/1776/july/4", "hop": 0}], "edges": [],
        "node_count": 1, "edge_count": 0, "truncated": False,
    }
    tools, http = _tools(payload)
    result = await tools["traverse_moments"]("/1776/july/4")
    assert result == payload
    assert http.calls[-1]["url"].endswith("/api/v1/graph/traverse/1776/july/4")


@pytest.mark.asyncio
async def test_traverse_moments_tool_404_gives_error_suggestion_shape():
    tools, _ = _tools({}, status_code=404)
    result = await tools["traverse_moments"]("/nope")
    assert set(result) == {"error", "suggestion"}
    assert "/nope" in result["suggestion"]


@pytest.mark.asyncio
async def test_traverse_moments_tool_rejects_bad_direction_without_calling_upstream():
    tools, http = _tools({})
    result = await tools["traverse_moments"]("/x", direction="sideways")
    assert set(result) == {"error", "suggestion"}
    assert http.calls == []


@pytest.mark.asyncio
async def test_traverse_moments_tool_rejects_bad_edge_types_without_calling_upstream():
    tools, http = _tools({})
    result = await tools["traverse_moments"]("/x", edge_types="causes,wormholes")
    assert set(result) == {"error", "suggestion"}
    assert "wormholes" in result["error"]
    assert http.calls == []


@pytest.mark.asyncio
async def test_traverse_moments_tool_never_raises_on_http_failure():
    class _ExplodingHTTP:
        calls = []

        async def get(self, url, headers=None, params=None):
            raise RuntimeError("boom")

        async def aclose(self):
            return None

    c, _ = _client({})
    c._client = _ExplodingHTTP()
    mcp = _FakeMCP()
    register_clockchain_tools(mcp, c, _FakeKeyStore())
    result = await mcp.tools["traverse_moments"]("/x")
    assert set(result) == {"error", "suggestion"}


# --- find_path tool ---


@pytest.mark.asyncio
async def test_find_path_tool_returns_upstream_payload():
    payload = {
        "found": True, "from": "/a", "to": "/b", "hops": 1,
        "nodes": [{"id": "/a", "hop": 0}, {"id": "/b", "hop": 1}],
        "edges": [{"source": "/a", "target": "/b", "type": "causes"}],
    }
    tools, http = _tools(payload)
    result = await tools["find_path"]("/a", "/b")
    assert result == payload
    assert http.calls[-1]["url"].endswith("/api/v1/graph/path")


@pytest.mark.asyncio
async def test_find_path_tool_passes_found_false_through_unchanged():
    payload = {"found": False, "from": "/a", "to": "/b", "hops": 0, "nodes": [], "edges": []}
    tools, _ = _tools(payload)
    result = await tools["find_path"]("/a", "/b", max_hops=3)
    assert result == payload


@pytest.mark.asyncio
async def test_find_path_tool_404_gives_error_suggestion_shape():
    tools, _ = _tools({}, status_code=404)
    result = await tools["find_path"]("/a", "/b")
    assert set(result) == {"error", "suggestion"}
    assert "/a" in result["suggestion"] and "/b" in result["suggestion"]


@pytest.mark.asyncio
async def test_find_path_tool_never_raises_on_http_failure():
    class _ExplodingHTTP:
        async def get(self, url, headers=None, params=None):
            raise RuntimeError("boom")

        async def aclose(self):
            return None

    c, _ = _client({})
    c._client = _ExplodingHTTP()
    mcp = _FakeMCP()
    register_clockchain_tools(mcp, c, _FakeKeyStore())
    result = await mcp.tools["find_path"]("/a", "/b")
    assert set(result) == {"error", "suggestion"}
