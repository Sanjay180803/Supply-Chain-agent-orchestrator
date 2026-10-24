import concurrent.futures
import time

from conftest import requires_redis

pytestmark = requires_redis


def test_never_more_than_max_concurrent_credits(adm):
    def grab(i):
        return adm.try_acquire_credit(f"h{i}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as ex:
        granted = sum(ex.map(grab, range(60)))
    assert granted == adm.MAX_CONCURRENT_CALLS
    assert adm.current_budget() == 0


def test_release_returns_capacity(adm):
    holders = [adm.acquire_credit(timeout_seconds=0) for _ in range(adm.MAX_CONCURRENT_CALLS)]
    assert all(holders)
    assert adm.acquire_credit(timeout_seconds=0) is None
    adm.release_credit(holders[0])
    assert adm.acquire_credit(timeout_seconds=0) is not None


def test_crashed_holder_credit_comes_back_after_lease(adm):
    """A replica that dies never calls release_credit. With the old counter
    the credit was lost forever; with leases it expires."""
    for i in range(adm.MAX_CONCURRENT_CALLS):
        assert adm.try_acquire_credit(f"dead{i}", lease_seconds=0.2)
    assert adm.acquire_credit(timeout_seconds=0) is None
    time.sleep(0.3)
    assert adm.current_budget() == adm.MAX_CONCURRENT_CALLS


def test_init_budget_cannot_push_capacity_above_max(adm):
    held = [adm.acquire_credit(timeout_seconds=0) for _ in range(3)]
    adm.init_budget()  # e.g. someone restarts init_budget.py mid-run
    for h in held:
        adm.release_credit(h)
    granted = sum(adm.try_acquire_credit(f"n{i}") for i in range(20))
    assert granted == adm.MAX_CONCURRENT_CALLS


def test_claim_states(adm):
    assert adm.claim("r1", "A") == "claimed"
    assert adm.claim("r1", "B") == "busy"
    adm.mark_done("r1")
    assert adm.claim("r1", "B") == "done"


def test_only_owner_can_release_claim(adm):
    adm.claim("r2", "A")
    assert adm.release_claim("r2", "B") is False
    assert adm.release_claim("r2", "A") is True
    assert adm.claim("r2", "B") == "claimed"


def test_expired_claim_can_be_reclaimed(adm):
    adm.claim("r3", "A", lease_seconds=0.2)
    time.sleep(0.3)
    assert adm.claim("r3", "B") == "claimed"


def test_concurrent_claims_have_one_winner(adm):
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        states = list(ex.map(lambda i: adm.claim("r4", f"o{i}"), range(20)))
    assert states.count("claimed") == 1
    assert states.count("busy") == 19
