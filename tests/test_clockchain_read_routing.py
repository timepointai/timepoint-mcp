"""Regression tests for Clockchain read-tool routing.

Bug (jun 2026): search/browse/today/random/neighbors were routed through a
non-existent Flash proxy path ``{FLASH_URL}/api/v1/clockchain/*`` which 404s,
so every discovery tool returned empty/not-found even though graph_stats
(which went direct to CLOCKCHAIN_URL) reported ~19.7k nodes. These tests pin
the read methods to Clockchain's own ``/api/v1/*`` endpoints with the service
key attached.
"""

import pytest

from app.clients.clockchain import ClockchainClient


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

    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def get(self, url, headers=None, params=None):
        self.calls.append({"url": url, "headers": headers or {}, "params": params or {}})
        return _Resp(self._payload)

    async def aclose(self):
        return None


def _client(payload):
    c = ClockchainClient(
        flash_proxy_url="https://flash.timepointai.com",
        flash_service_key="flash-key",
        direct_url="https://clockchain.timepointai.com",
        direct_service_key="cc-key",
    )
    http = _RecordingHTTP(payload)
    c._client = http
    return c, http


@pytest.mark.asyncio
async def test_search_hits_clockchain_direct_with_service_key():
    c, http = _client([{"path": "/x", "name": "March on Rome"}])
    results = await c.search("rome", limit=20)
    call = http.calls[-1]
    assert call["url"] == "https://clockchain.timepointai.com/api/v1/search"
    assert "/clockchain/" not in call["url"]
    assert call["headers"]["X-Service-Key"] == "cc-key"
    assert call["params"]["q"] == "rome"
    assert results and results[0]["name"] == "March on Rome"


@pytest.mark.asyncio
async def test_search_clamps_limit_to_upstream_max_50():
    c, http = _client([])
    await c.search("rome", limit=100)
    assert http.calls[-1]["params"]["limit"] == 50


@pytest.mark.asyncio
async def test_browse_root_hits_direct_browse():
    c, http = _client({"prefix": "/", "items": []})
    await c.browse("")
    call = http.calls[-1]
    assert call["url"] == "https://clockchain.timepointai.com/api/v1/browse"
    assert call["headers"]["X-Service-Key"] == "cc-key"


@pytest.mark.asyncio
async def test_browse_path_hits_direct_browse_path():
    c, http = _client({"prefix": "/1776", "items": []})
    await c.browse("/1776/")
    assert http.calls[-1]["url"] == "https://clockchain.timepointai.com/api/v1/browse/1776"


@pytest.mark.asyncio
async def test_today_and_random_hit_direct_with_key():
    c, http = _client({"events": []})
    await c.today()
    assert http.calls[-1]["url"] == "https://clockchain.timepointai.com/api/v1/today"
    assert http.calls[-1]["headers"]["X-Service-Key"] == "cc-key"

    c2, http2 = _client({"path": "/x"})
    await c2.random()
    assert http2.calls[-1]["url"] == "https://clockchain.timepointai.com/api/v1/random"
    assert http2.calls[-1]["headers"]["X-Service-Key"] == "cc-key"


@pytest.mark.asyncio
async def test_neighbors_hits_direct_graph_neighbors():
    c, http = _client({"neighbors": []})
    await c.neighbors("/1776/july/4")
    assert (
        http.calls[-1]["url"]
        == "https://clockchain.timepointai.com/api/v1/graph/neighbors/1776/july/4"
    )


@pytest.mark.asyncio
async def test_stats_hits_direct_stats():
    c, http = _client({"total_nodes": 19791})
    await c.stats()
    assert http.calls[-1]["url"] == "https://clockchain.timepointai.com/api/v1/stats"


@pytest.mark.asyncio
async def test_reads_fall_back_to_flash_proxy_when_clockchain_url_unset():
    # When CLOCKCHAIN_URL is empty, reads degrade to the legacy proxy base.
    c = ClockchainClient(
        flash_proxy_url="https://flash.timepointai.com",
        flash_service_key="flash-key",
        direct_url="",
        direct_service_key="",
    )
    http = _RecordingHTTP([])
    c._client = http
    await c.search("rome")
    assert http.calls[-1]["url"] == "https://flash.timepointai.com/api/v1/clockchain/search"
    assert http.calls[-1]["headers"]["X-Service-Key"] == "flash-key"
