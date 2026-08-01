"""Routing tests for the Explore subgraph read: subgraph() and explore_graph.

Same fake-http injection pattern as test_clockchain_read_routing.py — pins
the new method to Clockchain's /api/v1/graph/subgraph/{path} endpoint with
the direct service key, and covers the client-side clamps (depth 1..3,
cap 1..200), leading-slash stripping, 404 unwrapping, and the tool-level
web_url deep link + {error, suggestion} shapes.
"""

import functools

import pytest

from app.clients.clockchain import ClockchainClient
from app.tools.clockchain import register_clockchain_tools


class _FakeRequest:
    """Minimal stand-in for the Starlette request FastMCP injects — carries
    a fixed test API key so routing tests don't need to exercise real auth."""

    def __init__(self, api_key="test-read-key"):
        self.headers = {"X-API-Key": api_key}


class _FakeKeyStore:
    """Always validates _FakeRequest's fixed key with the "read" scope."""

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
        self.calls.append(
            {"url": url, "headers": headers or {}, "params": params or {}}
        )
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
    """Captures functions registered via @mcp.tool() so tests can call them.

    Wraps each tool with a pre-authenticated fake request so existing
    positional call sites keep working now that every read tool requires
    auth.
    """

    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = functools.partial(fn, request=_FakeRequest())
            return fn

        return decorator


def _tools(payload, status_code=200):
    c, http = _client(payload, status_code)
    mcp = _FakeMCP()
    register_clockchain_tools(mcp, c, _FakeKeyStore())
    return mcp.tools, http


_SUBGRAPH_PAYLOAD = {
    "nodes": [{"id": "/1776/july/4", "hop": 0}],
    "edges": [],
    "meta": {
        "root": "/1776/july/4",
        "depth": 1,
        "cap": 100,
        "truncated": False,
        "counts": {"nodes": 1, "edges": 0},
    },
}


# --- ClockchainClient.subgraph ---


@pytest.mark.asyncio
async def test_subgraph_hits_direct_graph_subgraph_with_service_key():
    c, http = _client(_SUBGRAPH_PAYLOAD)
    await c.subgraph("/1776/july/4/")
    call = http.calls[-1]
    assert (
        call["url"]
        == "https://clockchain.timepointai.com/api/v1/graph/subgraph/1776/july/4"
    )
    assert "/clockchain/" not in call["url"]
    assert call["headers"]["X-Service-Key"] == "cc-key"
    assert call["params"]["depth"] == 1
    assert call["params"]["cap"] == 200


@pytest.mark.asyncio
async def test_subgraph_strips_leading_slash_from_path():
    c, http = _client(_SUBGRAPH_PAYLOAD)
    await c.subgraph("/1914/june/28")
    assert http.calls[-1]["url"].endswith("/api/v1/graph/subgraph/1914/june/28")
    assert "//1914" not in http.calls[-1]["url"].replace("https://", "")


@pytest.mark.asyncio
async def test_subgraph_clamps_depth_and_cap():
    c, http = _client(_SUBGRAPH_PAYLOAD)
    await c.subgraph("/x", depth=9, cap=999)
    p = http.calls[-1]["params"]
    assert p["depth"] == 3
    assert p["cap"] == 200

    await c.subgraph("/x", depth=0, cap=0)
    p = http.calls[-1]["params"]
    assert p["depth"] == 1
    assert p["cap"] == 1


@pytest.mark.asyncio
async def test_subgraph_passes_depth_and_cap_through_in_range():
    c, http = _client(_SUBGRAPH_PAYLOAD)
    await c.subgraph("/x", depth=2, cap=50)
    p = http.calls[-1]["params"]
    assert p["depth"] == 2
    assert p["cap"] == 50


@pytest.mark.asyncio
async def test_subgraph_unwraps_404_to_error_dict():
    c, _ = _client({"detail": "not found"}, status_code=404)
    result = await c.subgraph("/nope")
    assert result == {"error": "not_found", "detail": "Resource not found"}


# --- explore_graph tool ---


@pytest.mark.asyncio
async def test_explore_graph_tool_returns_payload_with_web_url():
    tools, http = _tools(dict(_SUBGRAPH_PAYLOAD))
    result = await tools["explore_graph"]("/1776/july/4", depth=2)
    assert result["nodes"] == _SUBGRAPH_PAYLOAD["nodes"]
    assert result["meta"] == _SUBGRAPH_PAYLOAD["meta"]
    assert (
        result["web_url"] == "https://app.timepointai.com/explore/1776/july/4?depth=2"
    )
    assert http.calls[-1]["url"].endswith("/api/v1/graph/subgraph/1776/july/4")


@pytest.mark.asyncio
async def test_explore_graph_tool_web_url_reflects_clamped_depth():
    tools, http = _tools(dict(_SUBGRAPH_PAYLOAD))
    result = await tools["explore_graph"]("/x", depth=9, cap=999)
    assert http.calls[-1]["params"]["depth"] == 3
    assert http.calls[-1]["params"]["cap"] == 200
    assert result["web_url"].endswith("/explore/x?depth=3")


@pytest.mark.asyncio
async def test_explore_graph_tool_404_gives_error_suggestion_shape():
    tools, _ = _tools({}, status_code=404)
    result = await tools["explore_graph"]("/nope")
    assert set(result) == {"error", "suggestion"}
    assert result["error"] == "Moment not found."
    assert "/nope" in result["suggestion"]
    assert "web_url" not in result


@pytest.mark.asyncio
async def test_explore_graph_tool_never_raises_on_http_failure():
    class _ExplodingHTTP:
        async def get(self, url, headers=None, params=None):
            raise RuntimeError("boom")

        async def aclose(self):
            return None

    c, _ = _client({})
    c._client = _ExplodingHTTP()
    mcp = _FakeMCP()
    register_clockchain_tools(mcp, c, _FakeKeyStore())
    result = await mcp.tools["explore_graph"]("/x")
    assert set(result) == {"error", "suggestion"}
