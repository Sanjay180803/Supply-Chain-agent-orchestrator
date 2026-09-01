import time
import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

BUDGET_KEY = "llm_call_budget"
MAX_CONCURRENT_CALLS = 5  # tune this — simulates a rate/concurrency cap
DEDUP_PREFIX = "processed:"

# Atomic acquire: only decrement if budget > 0. Mirrors the SETNX-based
# exactly-once spend pattern — same class of bug (over-admission across
# replicas) applied to LLM-call concurrency instead of RPC credits.
ACQUIRE_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or "0")
if current > 0 then
    redis.call('DECR', KEYS[1])
    return 1
else
    return 0
end
"""

RELEASE_SCRIPT = """
redis.call('INCR', KEYS[1])
return 1
"""

acquire_lua = r.register_script(ACQUIRE_SCRIPT)
release_lua = r.register_script(RELEASE_SCRIPT)


def init_budget():
    """Reset the shared budget. Call once at startup (from one process only)."""
    r.set(BUDGET_KEY, MAX_CONCURRENT_CALLS)


def acquire_credit(timeout_seconds: float = 10.0) -> bool:
    """Block-poll for a credit. Returns False if timed out."""
    waited = 0.0
    interval = 0.1
    while waited < timeout_seconds:
        result = acquire_lua(keys=[BUDGET_KEY])
        if result == 1:
            return True
        time.sleep(interval)
        waited += interval
    return False


def release_credit():
    release_lua(keys=[BUDGET_KEY])


def current_budget() -> int:
    val = r.get(BUDGET_KEY)
    return int(val) if val else 0


def already_processing_or_done(request_id: str) -> bool:
    """
    Atomically claim a request_id using Redis SETNX semantics.
    Returns True if this is a duplicate delivery (already claimed elsewhere),
    False if this call just successfully claimed it and should proceed.

    This guards against Kafka's at-least-once delivery: if a consumer group
    rebalance causes the same message to be redelivered to another replica,
    only the first claimant actually processes it and touches the credit
    budget — preventing duplicate admission for a single logical request.
    """
    was_set = r.set(f"{DEDUP_PREFIX}{request_id}", "1", nx=True, ex=600)
    return not was_set