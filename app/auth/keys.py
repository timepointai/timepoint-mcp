import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

import asyncpg


SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS mcp_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_hash TEXT NOT NULL UNIQUE,
    key_prefix TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    scopes TEXT[] DEFAULT '{read}',
    created_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    rate_limit INT DEFAULT 60
);

CREATE TABLE IF NOT EXISTS mcp_usage_logs (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT now(),
    user_id TEXT,
    api_key_id UUID,
    tool_name TEXT NOT NULL,
    credits_spent INT DEFAULT 0,
    latency_ms INT,
    status TEXT,
    error_message TEXT,
    client_info TEXT
);
"""

KEY_PREFIX = "tp_mcp_"


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _generate_key() -> str:
    return KEY_PREFIX + secrets.token_hex(32)


@dataclass
class KeyInfo:
    id: str
    key_prefix: str
    user_id: str
    name: str
    scopes: list[str]
    rate_limit: int
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None


class KeyStore:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def init_schema(self):
        async with self.pool.acquire() as conn:
            await conn.execute(SCHEMA_DDL)

    async def create_key(
        self,
        user_id: str,
        name: str,
        scopes: list[str] | None = None,
        rate_limit: int = 60,
    ) -> tuple[str, KeyInfo]:
        """Create a new API key. Returns (raw_key, key_info).
        The raw key is only returned once — store it securely."""
        raw_key = _generate_key()
        key_hash = _hash_key(raw_key)
        key_prefix = raw_key[:12]
        if scopes is None:
            scopes = ["read"]

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO mcp_api_keys (key_hash, key_prefix, user_id, name, scopes, rate_limit)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, created_at
                """,
                key_hash,
                key_prefix,
                user_id,
                name,
                scopes,
                rate_limit,
            )
        info = KeyInfo(
            id=str(row["id"]),
            key_prefix=key_prefix,
            user_id=user_id,
            name=name,
            scopes=scopes,
            rate_limit=rate_limit,
            created_at=row["created_at"],
            last_used_at=None,
            expires_at=None,
            revoked_at=None,
        )
        return raw_key, info

    async def validate_key(self, raw_key: str) -> KeyInfo | None:
        """Validate an API key. Returns KeyInfo if valid, None if not."""
        if not raw_key.startswith(KEY_PREFIX):
            return None
        key_hash = _hash_key(raw_key)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, key_prefix, user_id, name, scopes, rate_limit,
                       created_at, last_used_at, expires_at, revoked_at
                FROM mcp_api_keys
                WHERE key_hash = $1
                """,
                key_hash,
            )
            if row is None:
                return None
            if row["revoked_at"] is not None:
                return None
            if row["expires_at"] is not None and row["expires_at"] < datetime.now(timezone.utc):
                return None
            # Update last_used_at
            await conn.execute(
                "UPDATE mcp_api_keys SET last_used_at = now() WHERE id = $1",
                row["id"],
            )
        return KeyInfo(
            id=str(row["id"]),
            key_prefix=row["key_prefix"],
            user_id=row["user_id"],
            name=row["name"],
            scopes=list(row["scopes"]),
            rate_limit=row["rate_limit"],
            created_at=row["created_at"],
            last_used_at=row["last_used_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
        )

    async def list_keys(self, user_id: str) -> list[KeyInfo]:
        """List all non-revoked keys for a user."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, key_prefix, user_id, name, scopes, rate_limit,
                       created_at, last_used_at, expires_at, revoked_at
                FROM mcp_api_keys
                WHERE user_id = $1 AND revoked_at IS NULL
                ORDER BY created_at DESC
                """,
                user_id,
            )
        return [
            KeyInfo(
                id=str(r["id"]),
                key_prefix=r["key_prefix"],
                user_id=r["user_id"],
                name=r["name"],
                scopes=list(r["scopes"]),
                rate_limit=r["rate_limit"],
                created_at=r["created_at"],
                last_used_at=r["last_used_at"],
                expires_at=r["expires_at"],
                revoked_at=r["revoked_at"],
            )
            for r in rows
        ]

    async def revoke_key(self, key_id: str, user_id: str) -> bool:
        """Revoke a key. Returns True if found and revoked."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE mcp_api_keys SET revoked_at = now()
                WHERE id = $1::uuid AND user_id = $2 AND revoked_at IS NULL
                """,
                key_id,
                user_id,
            )
        return result == "UPDATE 1"

    async def log_usage(
        self,
        user_id: str | None,
        api_key_id: str | None,
        tool_name: str,
        credits_spent: int = 0,
        latency_ms: int = 0,
        status: str = "success",
        error_message: str | None = None,
    ):
        """Log a tool call for analytics."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO mcp_usage_logs
                    (user_id, api_key_id, tool_name, credits_spent, latency_ms, status, error_message)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7)
                """,
                user_id,
                api_key_id,
                tool_name,
                credits_spent,
                latency_ms,
                status,
                error_message,
            )
