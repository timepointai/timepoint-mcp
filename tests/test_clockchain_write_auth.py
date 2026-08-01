from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.auth.keys import KeyInfo
from app.auth.rate_limit import RateLimiter
from app.tools.clockchain_write import AuthError, _check_write_rate, _require_auth


def _set_key_header(monkeypatch, api_key=None):
    headers = {"x-api-key": api_key} if api_key else {}
    monkeypatch.setattr("app.auth.require.get_http_headers", lambda **kwargs: headers)


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
async def test_require_auth_missing_key_header(monkeypatch):
    _set_key_header(monkeypatch)
    with pytest.raises(AuthError):
        await _require_auth(_KeyStore(BASE_KEY_INFO), "generate")


@pytest.mark.asyncio
async def test_require_auth_invalid_key(monkeypatch):
    _set_key_header(monkeypatch, api_key="tp_mcp_bad")
    with pytest.raises(AuthError):
        await _require_auth(_KeyStore(None), "generate")


@pytest.mark.asyncio
async def test_require_auth_missing_scope(monkeypatch):
    read_only = replace(BASE_KEY_INFO, scopes=["read"])
    _set_key_header(monkeypatch, api_key="tp_mcp_good")
    with pytest.raises(AuthError):
        await _require_auth(_KeyStore(read_only), "generate")


@pytest.mark.asyncio
async def test_require_auth_success(monkeypatch):
    _set_key_header(monkeypatch, api_key="tp_mcp_good")
    info = await _require_auth(_KeyStore(BASE_KEY_INFO), "generate")
    assert info.user_id == "user-1"


def test_check_write_rate_limit_blocks_after_limit():
    limiter = RateLimiter()
    _check_write_rate(BASE_KEY_INFO, limiter)
    _check_write_rate(BASE_KEY_INFO, limiter)
    with pytest.raises(AuthError):
        _check_write_rate(BASE_KEY_INFO, limiter)
