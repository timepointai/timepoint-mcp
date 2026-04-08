"""Credit cost constants and balance pre-checks for write operations.

All credit operations are routed through the Gateway CreditAccount — the
single source of truth for user balances.
"""

import logging

logger = logging.getLogger("mcp.billing.credits")

# Credit costs per generation preset — kept in sync with Gateway CREDIT_COSTS.
COSTS = {
    "balanced": 5,
    "hd": 10,
    "hyper": 5,
    "gemini3": 5,
}

# Full cost map mirroring gateway.auth_core.credits.CREDIT_COSTS.
# Used for reference / future tool expansion.
CREDIT_COSTS = {
    # Flash generation
    "generate_balanced": 5,
    "generate_hd": 10,
    "generate_hyper": 5,
    "generate_gemini3": 5,
    # Chat & navigation
    "chat": 1,
    "temporal_jump": 2,
    # Conductor (base + per-tool)
    "conductor_base": 5,
    "conductor_generate": 5,
    "conductor_pro_sim": 15,
    "conductor_compare": 10,
    "conductor_campaign_sim": 15,
    "conductor_campaign_survey": 5,
    "conductor_compare_campaigns": 10,
    # Falcon
    "falcon_discover": 2,
    "falcon_pipeline": 10,
    "falcon_simulate": 5,
    "falcon_export": 1,
    # SkipMeetings
    "meeting_generation": 1,
    # Clockchain
    "clockchain_ingest": 1,
    "clockchain_index": 1,
    # Metering (Gateway proxy)
    "falcon_run": 10,
}


async def check_balance(gateway_client, user_id: str, cost: int) -> tuple[bool, int]:
    """Pre-check that a user has enough credits for an operation.

    Routes through Gateway /internal/credits/check — the single source of
    truth for credit balances.

    Returns (has_enough, current_balance).
    """
    try:
        data = await gateway_client.check_balance(user_id, cost)
        sufficient = data.get("sufficient", False)
        balance = data.get("balance", 0)
        return sufficient, balance
    except Exception as e:
        logger.error("Failed to check balance via Gateway for user %s: %s", user_id, e)
        # Fail open — let the spend call handle the actual rejection
        return True, -1


async def spend_credits(
    gateway_client,
    user_id: str,
    cost: int,
    transaction_type: str = "generation",
    description: str | None = None,
) -> tuple[bool, int | None]:
    """Deduct credits via Gateway /internal/credits/spend.

    Returns (success, balance_after). On failure returns (False, None).
    """
    try:
        data = await gateway_client.spend_credits(
            user_id=user_id,
            cost=cost,
            transaction_type=transaction_type,
            description=description,
        )
        if data.get("success"):
            return True, data.get("balance_after")
        logger.error(
            "Gateway spend_credits failed for user %s: %s",
            user_id,
            data.get("error", "unknown"),
        )
        return False, None
    except Exception as e:
        logger.error("Failed to spend credits via Gateway for user %s: %s", user_id, e)
        return False, None
