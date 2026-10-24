"""
Redis-backed admission control and idempotent request claiming, shared by
every orchestrator replica.

Credits (concurrency cap on LLM-bound work)
-------------------------------------------
Each in-flight request holds a *leased* credit: an entry in a sorted set,
scored by its expiry time. Acquiring is one Lua script that drops expired
leases and adds a new one only if fewer than MAX_CONCURRENT_CALLS are held.
Releasing removes the entry.

The previous design kept a counter (DECR on acquire, INCR on release). If a
replica died between the two, the credit was gone for good, and re-running
init_budget() while requests were in flight pushed the counter above its
cap. With leases, a crashed holder's credit comes back when its lease
expires, and capacity is a constant, never a counter that can drift.

Claims (idempotency under Kafka's at-least-once delivery)
---------------------------------------------------------
A consumer-group rebalance can redeliver a message that another replica is
processing or has already finished. Each request_id has a claim key:

  "processing:<replica>"  with a lease TTL  — someone is working on it
  "done"                  with a long TTL   — finished; skip redeliveries

claim() returns "claimed", "busy" or "done". A failed attempt calls
release_claim() so a redelivery can retry it; a crashed attempt's claim
expires with its lease. This gives at-least-once delivery with idempotent
completion: a request is completed once even if it is delivered several
times. It is not "exactly-once execution": an attempt that crashes part
way through may have made LLM or agent calls before the retry.
"""
import os
import time
import uuid

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MAX_CONCURRENT_CALLS = int(os.getenv("MAX_CONCURRENT_CALLS", "5"))
# Must exceed the longest expected processing time (classification plus up to
# two agent calls with 60 s timeouts), or a slow request's credit can expire
# while it is still running. Matches the consumer's max_poll_interval_ms.
LEASE_SECONDS = float(os.getenv("CREDIT_LEASE_SECONDS", "300"))
DONE_TTL_SECONDS = int(os.getenv("DONE_TTL_SECONDS", "86400"))

CREDITS_KEY = "llm_credits"
CLAIM_PREFIX = "claim:"

_ACQUIRE = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZCARD', KEYS[1]) < tonumber(ARGV[2]) then
    redis.call('ZADD', KEYS[1], ARGV[3], ARGV[4])
    return 1
end
return 0
"""

_CLAIM = """
local v = redis.call('GET', KEYS[1])
if v == 'done' then return 'done' end
if v then return 'busy' end
redis.call('SET', KEYS[1], 'processing:' .. ARGV[1], 'PX', ARGV[2])
return 'claimed'
"""

_RELEASE_CLAIM = """
if redis.call('GET', KEYS[1]) == 'processing:' .. ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

_client = None
_scripts = {}


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def _script(name: str, body: str):
    if name not in _scripts:
        _scripts[name] = client().register_script(body)
    return _scripts[name]


# --- credits ---------------------------------------------------------------

def try_acquire_credit(holder: str, lease_seconds: float = LEASE_SECONDS) -> bool:
    now = time.time()
    return _script("acquire", _ACQUIRE)(
        keys=[CREDITS_KEY], args=[now, MAX_CONCURRENT_CALLS, now + lease_seconds, holder]
    ) == 1


def acquire_credit(holder: str | None = None, timeout_seconds: float = 10.0, lease_seconds: float = LEASE_SECONDS):
    """Poll for a credit. Returns the holder id on success (pass it to
    release_credit), or None on timeout."""
    holder = holder or uuid.uuid4().hex
    deadline = time.monotonic() + timeout_seconds
    while True:
        if try_acquire_credit(holder, lease_seconds):
            return holder
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.1)


def release_credit(holder: str) -> None:
    client().zrem(CREDITS_KEY, holder)


def credits_in_use() -> int:
    client().zremrangebyscore(CREDITS_KEY, "-inf", time.time())
    return client().zcard(CREDITS_KEY)


def current_budget() -> int:
    """Credits currently available."""
    return MAX_CONCURRENT_CALLS - credits_in_use()


def init_budget() -> None:
    """Clear all leases (e.g. after a full restart). Safe to call any time:
    capacity is MAX_CONCURRENT_CALLS, not a stored counter."""
    client().delete(CREDITS_KEY)


# --- claims ----------------------------------------------------------------

def claim(request_id: str, owner: str, lease_seconds: float = LEASE_SECONDS) -> str:
    return _script("claim", _CLAIM)(keys=[CLAIM_PREFIX + request_id], args=[owner, int(lease_seconds * 1000)])


def mark_done(request_id: str) -> None:
    client().set(CLAIM_PREFIX + request_id, "done", ex=DONE_TTL_SECONDS)


def release_claim(request_id: str, owner: str) -> bool:
    """Give up a claim after a failed attempt so a redelivery can retry.
    Only the owner's own claim is removed."""
    return _script("release_claim", _RELEASE_CLAIM)(keys=[CLAIM_PREFIX + request_id], args=[owner]) == 1


def wait_for_claim(request_id: str, owner: str, poll_seconds: float = 1.0,
                   lease_seconds: float = LEASE_SECONDS) -> str:
    """Claim, or wait while another replica's live claim is pending.
    Returns "claimed" or "done". Waiting (rather than skipping and
    committing) avoids losing the request if the other replica dies."""
    while True:
        state = claim(request_id, owner, lease_seconds)
        if state != "busy":
            return state
        time.sleep(poll_seconds)
