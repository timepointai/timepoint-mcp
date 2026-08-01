"""Regression tests: Clockchain read tools must require a valid API key.

Prior to this, search_moments/get_moment/browse_graph/etc. had no auth check
at all — any caller could hit mcp.timepointai.com with zero credentials.
These tests pin the "no key -> error, valid key -> passthrough" contract.

Also pins the header-access mechanism itself: fastmcp>=3 does not inject a
usable Starlette request into a plain `request=None` tool parameter, so
auth must read via fastmcp.server.dependencies.get_http_headers() instead.
"""

import pytest

from app.clients.clockchain import ClockchainClient
from app.tools.clockchain import register_clockchain_tools


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _RecordingHTTP:
    async def get(self, url, headers=None, params=None):
        return _Resp({"total_nodes": 1, "total_edges": 0})

    async def aclose(self):
        return None


def _client():
    c = ClockchainClient(
        flash_proxy_url="https://flash.timepointai.com",
        flash_service_key="flash-key",
        direct_url="https://clockchain.timepointai.com",
        direct_service_key="cc-key",
    )
    c._client = _RecordingHTTP()
    return c


class _FakeKeyStore:
    async def validate_key(self, api_key):
        if api_key != "valid-read-key":
            return None
        return type(
            "KeyInfo", (), {"id": "k1", "user_id": "test-user", "scopes": ["read"]}
        )()


class _FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _tools(key_store=None):
    mcp = _FakeMCP()
    register_clockchain_tools(mcp, _client(), key_store or _FakeKeyStore())
    return mcp.tools


def _set_key_header(monkeypatch, api_key=None):
    headers = {"x-api-key": api_key} if api_key else {}
    monkeypatch.setattr("app.auth.require.get_http_headers", lambda **kwargs: headers)


@pytest.mark.asyncio
async def test_graph_stats_rejects_missing_key(monkeypatch):
    _set_key_header(monkeypatch)
    result = await _tools()["graph_stats"]()
    assert "error" in result
    assert "API key" in result["error"]


@pytest.mark.asyncio
async def test_graph_stats_rejects_invalid_key(monkeypatch):
    _set_key_header(monkeypatch, api_key="bogus")
    result = await _tools()["graph_stats"]()
    assert "error" in result
    assert "Invalid" in result["error"]


@pytest.mark.asyncio
async def test_graph_stats_accepts_valid_key(monkeypatch):
    _set_key_header(monkeypatch, api_key="valid-read-key")
    result = await _tools()["graph_stats"]()
    assert "error" not in result
    assert result["total_moments"] == 1


@pytest.mark.asyncio
async def test_graph_stats_rejects_key_without_read_scope(monkeypatch):
    class _NoReadScopeStore:
        async def validate_key(self, api_key):
            return type(
                "KeyInfo", (), {"id": "k1", "user_id": "u", "scopes": ["generate"]}
            )()

    _set_key_header(monkeypatch, api_key="whatever")
    result = await _tools(key_store=_NoReadScopeStore())["graph_stats"]()
    assert "error" in result
    assert "scope" in result["error"]


@pytest.mark.asyncio
async def test_search_moments_rejects_missing_key(monkeypatch):
    _set_key_header(monkeypatch)
    result = await _tools()["search_moments"](query="Caesar")
    assert "error" in result
