import pytest

from app.auth.rate_limit import RateLimiter
from app.tools.clockchain_write import register_clockchain_write_tools


class _MCPStub:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


class _KeyInfo:
    id = "k1"
    user_id = "u1"
    scopes = ["admin", "generate"]
    write_rate_limit = 10


class _KeyStore:
    async def validate_key(self, raw_key: str):
        return _KeyInfo()

    async def log_usage(self, **kwargs):
        return None


class _ClockchainClient:
    async def ingest_tdf(self, tdf_record: dict):
        return {"ok": True, "path": tdf_record.get("path")}


@pytest.mark.asyncio
async def test_index_tdf_defaults_schema_version_to_v02():
    mcp = _MCPStub()
    register_clockchain_write_tools(
        mcp=mcp,
        clockchain_client=_ClockchainClient(),
        flash_client=None,
        key_store=_KeyStore(),
        rate_limiter=RateLimiter(),
    )

    fn = mcp.tools["index_moment_from_tdf"]
    payload = {
        "path": "/1/jan/1/0000/test",
        "name": "Test",
        "year": 1,
        "month": 1,
        "day": 1,
    }
    out = await fn(payload, request=type("R", (), {"headers": {"X-API-Key": "tp_mcp_x"}})())

    assert out["indexed"] is True
    assert payload["schema_version"] == "0.2"
