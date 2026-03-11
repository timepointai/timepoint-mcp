"""Credit cost constants and balance pre-checks for write operations."""

import logging

logger = logging.getLogger("mcp.billing.credits")

# Credit costs per generation preset
COSTS = {
    "balanced": 5,
    "hd": 10,
    "hyper": 5,
}


async def check_balance(flash_client, user_id: str, cost: int) -> tuple[bool, int]:
    """Pre-check that a user has enough credits for an operation.

    Returns (has_enough, current_balance).
    """
    try:
        data = await flash_client.get_balance(user_id)
        balance = data.get("balance", 0)
        return balance >= cost, balance
    except Exception as e:
        logger.error("Failed to check balance for user %s: %s", user_id, e)
        # Fail open — let Flash handle the actual deduction and rejection
        return True, -1
