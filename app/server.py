"""Timepoint MCP Server — main entry point.

Provides AI agents with access to the Timepoint temporal knowledge platform
via the Model Context Protocol (MCP).
"""

import argparse
import contextlib
import hmac
import json
import logging
import sys

import asyncpg
import uvicorn
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from app.auth.keys import KeyStore
from app.auth.rate_limit import RateLimiter
from app.clients.clockchain import ClockchainClient
from app.clients.flash import FlashClient
from app.config import get_settings
from app.tools.clockchain import register_clockchain_tools
from app.tools.clockchain_write import register_clockchain_write_tools

logger = logging.getLogger("mcp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

VERSION = "0.1.0"

# --- Globals (initialized on startup) ---
db_pool: asyncpg.Pool | None = None
key_store: KeyStore | None = None
rate_limiter = RateLimiter()
clockchain_client: ClockchainClient | None = None
flash_client: FlashClient | None = None

# --- MCP server ---
mcp = FastMCP(
    "Timepoint",
    instructions=(
        "Timepoint gives you access to a temporal causal graph of historical events "
        "and an AI-powered reality-writing engine. Use the search, browse, and detail tools "
        "to explore history. Use generation tools (when available) to create rich historical "
        "timepoints with narratives, characters, dialog, and images."
    ),
)


# --- Health endpoint (plain HTTP, not MCP) ---
async def health(request: Request) -> JSONResponse:
    settings = get_settings()
    db_ok = db_pool is not None
    if db_ok:
        try:
            async with db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
        except Exception:
            db_ok = False

    return JSONResponse({
        "status": "ok" if db_ok else "degraded",
        "version": VERSION,
        "tools": len(mcp._tool_manager._tools) if hasattr(mcp, "_tool_manager") else 7,
        "transport": "streamable-http",
        "database": "connected" if db_ok else "disconnected",
        "clockchain": bool(settings.FLASH_URL or settings.CLOCKCHAIN_URL),
    })


async def root(request: Request) -> JSONResponse:
    """Landing page for visitors and unauthenticated agents."""
    accept = request.headers.get("accept", "")
    # If a browser, redirect to the main site
    if "text/html" in accept:
        return RedirectResponse("https://timepointai.com", status_code=302)
    # For agents/API callers, return instructions
    return JSONResponse({
        "service": "Timepoint MCP Server",
        "version": VERSION,
        "mcp_endpoint": "https://mcp.timepointai.com/mcp",
        "docs": "https://github.com/timepointai/timepoint-mcp",
        "get_api_key": {
            "instructions": "To get an MCP API key, visit timepointai.com or reach out on X @timepointai.",
            "website": "https://timepointai.com",
            "twitter": "https://x.com/timepointai",
        },
        "free_tools": [
            "search_moments", "get_moment", "browse_graph",
            "get_connections", "today_in_history", "random_moment", "graph_stats",
        ],
        "authenticated_tools": [
            "generate_moment (generate scope, 5-10 credits)",
            "publish_moment (generate scope, 0 credits)",
            "index_moment_from_tdf (admin scope, 0 credits)",
        ],
        "note": "Clockchain read tools work without authentication (rate-limited). Write tools require an API key with appropriate scopes and credits.",
    })


async def admin_create_key(request: Request) -> JSONResponse:
    """Create an MCP API key. Requires X-Admin-Key header (Flash admin key)."""
    settings = get_settings()
    admin_key = request.headers.get("X-Admin-Key", "")
    if not admin_key or not settings.FLASH_ADMIN_KEY:
        return JSONResponse({"error": "Missing X-Admin-Key header"}, status_code=401)
    if not hmac.compare_digest(admin_key, settings.FLASH_ADMIN_KEY):
        return JSONResponse({"error": "Invalid admin key"}, status_code=403)
    if not key_store:
        return JSONResponse({"error": "Database not available"}, status_code=503)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    user_id = body.get("user_id", "")
    name = body.get("name", "default")
    scopes = body.get("scopes", ["read", "generate"])
    write_rate_limit = body.get("write_rate_limit", 10)
    if not user_id:
        return JSONResponse({"error": "user_id is required"}, status_code=400)

    raw_key, info = await key_store.create_key(
        user_id=user_id,
        name=name,
        scopes=scopes,
        write_rate_limit=write_rate_limit,
    )
    return JSONResponse({
        "api_key": raw_key,
        "key_id": info.id,
        "key_prefix": info.key_prefix,
        "user_id": info.user_id,
        "name": info.name,
        "scopes": info.scopes,
        "warning": "Store this key securely — it will not be shown again.",
    }, status_code=201)


async def account_status(request: Request) -> JSONResponse:
    """Basic account status — returns key info if authenticated."""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key or not key_store:
        return JSONResponse({
            "authenticated": False,
            "tier": "anonymous",
            "get_api_key": "Visit https://timepointai.com or contact @timepointai on X to request an API key.",
        })
    info = await key_store.validate_key(api_key)
    if not info:
        return JSONResponse({"authenticated": False, "error": "Invalid API key"}, status_code=401)
    return JSONResponse({
        "authenticated": True,
        "user_id": info.user_id,
        "tier": "free",  # Phase 2: resolve from billing
        "scopes": info.scopes,
        "key_name": info.name,
    })


# --- Lifecycle ---
async def startup():
    global db_pool, key_store, clockchain_client, flash_client
    settings = get_settings()

    # Database
    if settings.DATABASE_URL:
        try:
            db_pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=2, max_size=10)
            key_store = KeyStore(db_pool)
            await key_store.init_schema()
            logger.info("Database connected, schema initialized")
        except Exception as e:
            logger.error("Database connection failed: %s", e)
            # Continue without DB — anonymous-only mode
    else:
        logger.warning("No DATABASE_URL — running in anonymous-only mode (no API keys)")

    # Clockchain client
    clockchain_client = ClockchainClient(
        flash_proxy_url=settings.FLASH_URL,
        flash_service_key=settings.FLASH_SERVICE_KEY,
        direct_url=settings.CLOCKCHAIN_URL,
        direct_service_key=settings.CLOCKCHAIN_SERVICE_KEY,
    )

    # Flash client (for generation)
    if settings.FLASH_URL and settings.FLASH_SERVICE_KEY:
        flash_client = FlashClient(
            base_url=settings.FLASH_URL,
            service_key=settings.FLASH_SERVICE_KEY,
        )
        logger.info("Flash client initialized")
    else:
        logger.warning("No Flash service key — generation tools will be unavailable")

    # Register tools
    register_clockchain_tools(mcp, clockchain_client)
    register_clockchain_write_tools(mcp, clockchain_client, flash_client, key_store, rate_limiter)
    logger.info("Timepoint MCP server started (v%s)", VERSION)


async def shutdown():
    global db_pool, clockchain_client, flash_client
    if flash_client:
        await flash_client.close()
    if clockchain_client:
        await clockchain_client.close()
    if db_pool:
        await db_pool.close()
    logger.info("Timepoint MCP server stopped")


# --- ASGI app ---
def create_http_app() -> Starlette:
    """Create the Starlette app that serves both MCP and plain HTTP endpoints."""

    @contextlib.asynccontextmanager
    async def lifespan(app):
        await startup()
        yield
        await shutdown()

    routes = [
        Route("/", root, methods=["GET"]),
        Route("/health", health, methods=["GET"]),
        Route("/admin/create-key", admin_create_key, methods=["POST"]),
        Route("/account/status", account_status, methods=["GET"]),
    ]

    app = Starlette(
        routes=routes,
        lifespan=lifespan,
    )

    # Mount MCP at /mcp
    mcp_app = mcp.http_app(path="/mcp")
    app.mount("/mcp", mcp_app)

    return app


# Module-level ASGI app for uvicorn
http_app = create_http_app()


def main():
    parser = argparse.ArgumentParser(description="Timepoint MCP Server")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    host = args.host or settings.MCP_HOST
    port = args.port or settings.MCP_PORT

    if args.transport == "stdio":
        # stdio mode for local development with Claude Desktop
        import asyncio
        asyncio.run(startup())
        mcp.run(transport="stdio")
    else:
        uvicorn.run(
            "app.server:http_app",
            host=host,
            port=port,
            log_level="info",
        )


if __name__ == "__main__":
    main()
