import json
import time
import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

LOG_KEY = "eval_log"
MAX_LOG_ENTRIES = 5000  # cap so Redis doesn't grow unbounded


def log_execution(agent: str, success: bool, latency_ms: float, metric_value: float | None = None, error: str | None = None):
    """Append one execution record to the shared eval log.

    metric_value is agent-specific and used for drift detection:
    - procurement: final negotiated price
    - logistics: total shipping cost
    - compliance: 1.0 if approved else 0.0
    - analytics: not used (None) — analytics doesn't have a single drift-relevant number
    """
    entry = {
        "agent": agent,
        "timestamp": time.time(),
        "success": success,
        "latency_ms": latency_ms,
        "metric_value": metric_value,
        "error": error,
    }
    r.lpush(LOG_KEY, json.dumps(entry))
    r.ltrim(LOG_KEY, 0, MAX_LOG_ENTRIES - 1)


def get_all_logs() -> list[dict]:
    raw_entries = r.lrange(LOG_KEY, 0, -1)
    return [json.loads(e) for e in raw_entries]