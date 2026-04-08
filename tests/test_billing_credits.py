import pytest

from app.billing.credits import check_balance, spend_credits


class _GatewayClientOk:
    async def check_balance(self, user_id: str, cost: int):
        return {"sufficient": True, "balance": 9}

    async def spend_credits(self, user_id, cost, transaction_type="generation", description=None):
        return {"success": True, "transaction_id": "txn-1", "balance_after": 4}


class _GatewayClientInsufficient:
    async def check_balance(self, user_id: str, cost: int):
        return {"sufficient": False, "balance": 2}

    async def spend_credits(self, user_id, cost, transaction_type="generation", description=None):
        return {"success": False, "error": "Insufficient credits"}


class _GatewayClientErr:
    async def check_balance(self, user_id: str, cost: int):
        raise RuntimeError("boom")

    async def spend_credits(self, user_id, cost, transaction_type="generation", description=None):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_check_balance_has_enough_true():
    ok, balance = await check_balance(_GatewayClientOk(), "u1", 5)
    assert ok is True
    assert balance == 9


@pytest.mark.asyncio
async def test_check_balance_insufficient():
    ok, balance = await check_balance(_GatewayClientInsufficient(), "u1", 5)
    assert ok is False
    assert balance == 2


@pytest.mark.asyncio
async def test_check_balance_fail_open_on_error():
    ok, balance = await check_balance(_GatewayClientErr(), "u1", 5)
    assert ok is True
    assert balance == -1


@pytest.mark.asyncio
async def test_spend_credits_success():
    ok, balance_after = await spend_credits(_GatewayClientOk(), "u1", 5)
    assert ok is True
    assert balance_after == 4


@pytest.mark.asyncio
async def test_spend_credits_insufficient():
    ok, balance_after = await spend_credits(_GatewayClientInsufficient(), "u1", 5)
    assert ok is False
    assert balance_after is None


@pytest.mark.asyncio
async def test_spend_credits_fail_on_error():
    ok, balance_after = await spend_credits(_GatewayClientErr(), "u1", 5)
    assert ok is False
    assert balance_after is None
