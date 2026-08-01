"""Shared API-key auth check for MCP tools (both read and write).

Extracted from app/tools/clockchain_write.py so app/tools/clockchain.py
(read tools) can require auth too without a read<->write module cycle.
"""

from app.auth.keys import KeyInfo, KeyStore


class AuthError(Exception):
    """Raised when authentication or authorization fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def require_auth(
    request,
    key_store: KeyStore | None,
    required_scope: str,
) -> KeyInfo:
    """Extract API key from request headers, validate, and check scope.

    Returns KeyInfo on success, raises AuthError on failure.
    """
    if key_store is None:
        raise AuthError("Authentication service unavailable. Try again later.")

    # FastMCP injects the Starlette request via context
    api_key = ""
    if hasattr(request, "headers"):
        api_key = request.headers.get("x-api-key", "") or request.headers.get("X-API-Key", "")

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
