import pytest

from app.billing.credits import check_balance


class _FlashClientOk:
    async def get_balance(self, user_id: str):
        return {"balance": 9}


class _FlashClientErr:
    async def get_balance(self, user_id: str):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_check_balance_has_enough_true():
    ok, balance = await check_balance(_FlashClientOk(), "u1", 5)
    assert ok is True
    assert balance == 9


@pytest.mark.asyncio
async def test_check_balance_fail_open_on_error():
    ok, balance = await check_balance(_FlashClientErr(), "u1", 5)
    assert ok is True
    assert balance == -1
