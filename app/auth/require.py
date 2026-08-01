"""Shared API-key auth check for MCP tools (both read and write).

Extracted from app/tools/clockchain_write.py so app/tools/clockchain.py
(read tools) can require auth too without a read<->write module cycle.

Header access uses fastmcp.server.dependencies.get_http_headers(), which
reads the current request from a contextvar FastMCP's ASGI layer sets per
call. The older pattern of accepting a `request=None` tool parameter and
reading `request.headers` does NOT work on fastmcp>=3 (Streamable HTTP
does not inject a real Starlette Request into tool kwargs that way) — it
silently always returns "" and every call looked like it had no key at
all, regardless of what the caller actually sent. Discovered while adding
auth to the read tools; also fixed in clockchain_write.py for the same
reason.
"""

from fastmcp.server.dependencies import get_http_headers

from app.auth.keys import KeyInfo, KeyStore


class AuthError(Exception):
    """Raised when authentication or authorization fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def require_auth(
    key_store: KeyStore | None,
    required_scope: str,
) -> KeyInfo:
    """Extract API key from the current request's headers, validate, and check scope.

    Returns KeyInfo on success, raises AuthError on failure.
    """
    if key_store is None:
        raise AuthError("Authentication service unavailable. Try again later.")

    headers = get_http_headers(include=["x-api-key"])
    api_key = headers.get("x-api-key", "")

    if not api_key:
        raise AuthError(
            "This tool requires an API key. Set the X-API-Key header. "
            "Get a key at https://timepointai.com or contact @timepointai on X."
        )

    info = await key_store.validate_key(api_key)
    if info is None:
        raise AuthError("Invalid or expired API key.")

    if required_scope not in info.scopes:
        raise AuthError(
            f"Your API key lacks the '{required_scope}' scope. "
            f"Current scopes: {info.scopes}. Contact support to upgrade."
        )

    return info
