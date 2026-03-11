from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.auth.keys import KeyInfo
from app.auth.rate_limit import RateLimiter
from app.tools.clockchain_write import AuthError, _check_write_rate, _require_auth


class _Req:
    def __init__(self, headers: dict[str, str]):
        self.headers = headers


class _KeyStore:
    def __init__(self, key_info: KeyInfo | None):
        self._key_info = key_info

    async def validate_key(self, raw_key: str):
        return self._key_info


BASE_KEY_INFO = KeyInfo(
    id="key-1",
    key_prefix="tp_mcp_abcd",
    user_id="user-1",
    name="test",
    scopes=["read", "generate"],
    rate_limit=60,
    write_rate_limit=2,
    created_at=datetime.now(timezone.utc),
    last_used_at=None,
    expires_at=None,
    revoked_at=None,
)


@pytest.mark.asyncio
async def test_require_auth_missing_key_header():
    with pytest.raises(AuthError):
        await _require_auth(_Req({}), _KeyStore(BASE_KEY_INFO), "generate")


@pytest.mark.asyncio
async def test_require_auth_invalid_key():
    with pytest.raises(AuthError):
        await _require_auth(_Req({"X-API-Key": "tp_mcp_bad"}), _KeyStore(None), "generate")


@pytest.mark.asyncio
async def test_require_auth_missing_scope():
    read_only = replace(BASE_KEY_INFO, scopes=["read"])
    with pytest.raises(AuthError):
        await _require_auth(_Req({"X-API-Key": "tp_mcp_good"}), _KeyStore(read_only), "generate")


@pytest.mark.asyncio
async def test_require_auth_success():
    info = await _require_auth(_Req({"X-API-Key": "tp_mcp_good"}), _KeyStore(BASE_KEY_INFO), "generate")
    assert info.user_id == "user-1"


def test_check_write_rate_limit_blocks_after_limit():
    limiter = RateLimiter()
    _check_write_rate(BASE_KEY_INFO, limiter)
    _check_write_rate(BASE_KEY_INFO, limiter)
    with pytest.raises(AuthError):
        _check_write_rate(BASE_KEY_INFO, limiter)
