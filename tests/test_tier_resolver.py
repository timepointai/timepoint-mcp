import pytest

from app.auth.tier import TierResolver


class _BillingClient:
    def __init__(self, payload: dict, should_raise: bool = False):
        self.payload = payload
        self.should_raise = should_raise
        self.calls = 0

    async def get_status(self, user_id: str):
        self.calls += 1
        if self.should_raise:
            raise RuntimeError("billing down")
        return self.payload


@pytest.mark.asyncio
async def test_tier_resolver_active_subscription():
    billing = _BillingClient({"subscription_tier": "creator", "status": "active"})
    resolver = TierResolver(billing, ttl_seconds=60)
    tier = await resolver.resolve_tier("u1")
    assert tier == "creator"


@pytest.mark.asyncio
async def test_tier_resolver_non_active_falls_back_to_free():
    billing = _BillingClient({"subscription_tier": "creator", "status": "past_due"})
    resolver = TierResolver(billing, ttl_seconds=60)
    tier = await resolver.resolve_tier("u1")
    assert tier == "free"


@pytest.mark.asyncio
async def test_tier_resolver_caches():
    billing = _BillingClient({"subscription_tier": "explorer", "status": "active"})
    resolver = TierResolver(billing, ttl_seconds=60)
    t1 = await resolver.resolve_tier("u1")
    t2 = await resolver.resolve_tier("u1")
    assert t1 == "explorer" and t2 == "explorer"
    assert billing.calls == 1


@pytest.mark.asyncio
async def test_tier_resolver_error_falls_back_free():
    billing = _BillingClient({}, should_raise=True)
    resolver = TierResolver(billing, ttl_seconds=60)
    tier = await resolver.resolve_tier("u1")
    assert tier == "free"
