"""Clockchain write tools — generate, publish, and index moments.

These tools require authentication with appropriate scopes:
- generate_moment / publish_moment: requires "generate" scope
- index_moment_from_tdf: requires "admin" scope
"""

import logging
import time
from typing import Annotated

from pydantic import Field

from app.auth.keys import KeyInfo, KeyStore
from app.auth.rate_limit import RateLimiter
from app.billing.credits import COSTS, check_balance
from app.clients.clockchain import ClockchainClient
from app.clients.flash import FlashClient

logger = logging.getLogger("mcp.tools.clockchain_write")


class AuthError(Exception):
    """Raised when authentication or authorization fails."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def _require_auth(
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


def _check_write_rate(key_info: KeyInfo, rate_limiter: RateLimiter) -> None:
    """Check write rate limit for this key. Raises AuthError if exceeded."""
    rate_key = f"write:{key_info.id}"
    allowed, remaining = rate_limiter.check(rate_key, key_info.write_rate_limit)
    if not allowed:
        raise AuthError(
            f"Write rate limit exceeded ({key_info.write_rate_limit}/min). "
            "Wait a moment before trying again."
        )


def register_clockchain_write_tools(
    mcp,
    clockchain_client: ClockchainClient,
    flash_client: FlashClient | None,
    key_store: KeyStore | None,
    rate_limiter: RateLimiter,
):
    """Register clockchain write tools on the MCP server."""

    @mcp.tool()
    async def generate_moment(
        query: Annotated[str, Field(description="What historical event or moment to generate, e.g. 'Battle of Thermopylae' or 'First Moon Landing'")],
        preset: Annotated[str, Field(description="Generation quality preset: 'balanced' (5 credits), 'hd' (10 credits), or 'hyper' (5 credits)")] = "balanced",
        visibility: Annotated[str, Field(description="Visibility of the generated moment: 'private' (only you) or 'public'")] = "private",
        request=None,
    ) -> dict:
        """Generate a new historical moment using Timepoint's AI reality-writing engine.

        This runs a full 14-agent pipeline to create a rich timepoint with narrative,
        characters, dialog, images, and causal connections. The moment is then indexed
        into the clockchain graph.

        Costs 5-10 credits depending on preset. Requires an API key with 'generate' scope.

        The generated moment starts as private by default. Use publish_moment to make it public.
        """
        # Auth
        try:
            key_info = await _require_auth(request, key_store, "generate")
            _check_write_rate(key_info, rate_limiter)
        except AuthError as e:
            return {"error": e.message}

        # Check Flash client availability
        if flash_client is None:
            return {"error": "Generation service not configured. Contact the server administrator."}

        # Validate preset
        if preset not in COSTS:
            return {"error": f"Invalid preset '{preset}'. Choose from: {list(COSTS.keys())}"}

        if visibility not in ("private", "public"):
            return {"error": "Visibility must be 'private' or 'public'."}

        cost = COSTS[preset]

        # Pre-check balance
        has_enough, balance = await check_balance(flash_client, key_info.user_id, cost)
        if not has_enough:
            return {
                "error": f"Insufficient credits. Need {cost}, have {balance}.",
                "credits_required": cost,
                "credits_available": balance,
                "get_credits": "Visit https://timepointai.com to purchase credits.",
            }

        # Generate via Flash
        start = time.monotonic()
        try:
            result = await flash_client.generate_sync(
                query=query,
                preset=preset,
                user_id=key_info.user_id,
            )
        except Exception as e:
            logger.error("Flash generation failed for user %s: %s", key_info.user_id, e)
            if key_store:
                await key_store.log_usage(
                    user_id=key_info.user_id,
                    api_key_id=key_info.id,
                    tool_name="generate_moment",
                    credits_spent=0,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    status="error",
                    error_message=str(e),
                )
            return {"error": "Generation failed. The AI pipeline encountered an error. Please try again."}

        # Index into clockchain
        try:
            index_payload = {
                "timepoint": result,
                "source_type": "mcp_user",
                "visibility": visibility,
            }
            index_result = await clockchain_client.index_moment(index_payload, user_id=key_info.user_id)
        except Exception as e:
            logger.error("Clockchain indexing failed for user %s: %s", key_info.user_id, e)
            # Generation succeeded but indexing failed — still return the result
            index_result = {"error": f"Indexing failed: {e}. The moment was generated but may not appear in search yet."}

        latency_ms = int((time.monotonic() - start) * 1000)

        # Log usage
        if key_store:
            await key_store.log_usage(
                user_id=key_info.user_id,
                api_key_id=key_info.id,
                tool_name="generate_moment",
                credits_spent=cost,
                latency_ms=latency_ms,
                status="success",
            )

        # Build response
        path = result.get("path", index_result.get("path", ""))
        name = result.get("name", result.get("title", query))
        image_url = result.get("image_url", "")

        return {
            "path": path,
            "name": name,
            "image_url": image_url,
            "visibility": visibility,
            "credits_spent": cost,
            "generation_time_ms": latency_ms,
            "indexed": "error" not in index_result,
        }

    @mcp.tool()
    async def publish_moment(
        path: Annotated[str, Field(description="Canonical path of the moment to publish, e.g. '/1776/july/4/1200/usa/pennsylvania/philadelphia/signing-declaration-of-independence'")],
        request=None,
    ) -> dict:
        """Publish a private moment to make it publicly visible in the clockchain.

        Only works on moments you created (ownership check). Requires 'generate' scope.
        No credits are charged for publishing.
        """
        try:
            key_info = await _require_auth(request, key_store, "generate")
            _check_write_rate(key_info, rate_limiter)
        except AuthError as e:
            return {"error": e.message}

        start = time.monotonic()
        try:
            result = await clockchain_client.update_visibility(
                path=path,
                visibility="public",
                user_id=key_info.user_id,
            )
        except Exception as e:
            logger.error("Publish failed for path %s, user %s: %s", path, key_info.user_id, e)
            return {"error": f"Failed to publish moment: {e}"}

        if isinstance(result, dict) and "error" in result:
            return {"error": result.get("detail", "Failed to publish. You may not own this moment or the path is invalid.")}

        latency_ms = int((time.monotonic() - start) * 1000)
        if key_store:
            await key_store.log_usage(
                user_id=key_info.user_id,
                api_key_id=key_info.id,
                tool_name="publish_moment",
                credits_spent=0,
                latency_ms=latency_ms,
                status="success",
            )

        return {
            "path": path,
            "visibility": "public",
            "published": True,
        }

    @mcp.tool()
    async def index_moment_from_tdf(
        tdf_record: Annotated[dict, Field(description="A complete TDF (Timepoint Data Format) record to index directly into the clockchain")],
        request=None,
    ) -> dict:
        """Index a pre-formatted TDF record directly into the clockchain.

        This bypasses the Flash generation pipeline and is intended for automated
        pipelines and bulk imports. Requires 'admin' scope. No credits are charged.

        The TDF record must include at minimum: path, name, year, month, day.
        """
        try:
            key_info = await _require_auth(request, key_store, "admin")
            _check_write_rate(key_info, rate_limiter)
        except AuthError as e:
            return {"error": e.message}

        # Basic TDF validation
        required_fields = ["path", "name", "year", "month", "day"]
        missing = [f for f in required_fields if f not in tdf_record]
        if missing:
            return {"error": f"TDF record missing required fields: {missing}"}

        start = time.monotonic()
        try:
            result = await clockchain_client.ingest_tdf(tdf_record)
        except Exception as e:
            logger.error("TDF ingest failed for user %s: %s", key_info.user_id, e)
            return {"error": f"TDF ingestion failed: {e}"}

        if isinstance(result, dict) and "error" in result:
            return {"error": result.get("detail", "TDF ingestion failed.")}

        latency_ms = int((time.monotonic() - start) * 1000)
        if key_store:
            await key_store.log_usage(
                user_id=key_info.user_id,
                api_key_id=key_info.id,
                tool_name="index_moment_from_tdf",
                credits_spent=0,
                latency_ms=latency_ms,
                status="success",
            )

        return {
            "path": tdf_record.get("path", ""),
            "indexed": True,
            "result": result,
        }
