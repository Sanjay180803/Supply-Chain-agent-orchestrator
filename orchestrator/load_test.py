import threading
import time
import requests
import redis

GATEWAY_URL = "http://localhost:8005"
NUM_REQUESTS = 15  # more than the budget of 5, to force contention

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

results = []
lock = threading.Lock()

TEST_REQUEST = "Source 500 units of Conference electronics unit and ship to Europe, 200 kg"


def submit_and_track(idx):
    start = time.time()
    resp = requests.post(f"{GATEWAY_URL}/submit", json={"request": TEST_REQUEST}, timeout=10)
    request_id = resp.json()["request_id"]

    # Poll for completion
    status = "queued"
    while status not in ("done",):
        time.sleep(0.5)
        r_resp = requests.get(f"{GATEWAY_URL}/result/{request_id}", timeout=10)
        data = r_resp.json()
        status = data.get("status", "unknown")
        if time.time() - start > 240:
            status = "timeout"
            break

    elapsed = time.time() - start
    handled_by = data.get("result", {}).get("handled_by", "N/A") if status == "done" else "N/A"

    with lock:
        results.append({
            "idx": idx,
            "request_id": request_id,
            "status": status,
            "elapsed": round(elapsed, 2),
            "handled_by": handled_by,
        })
        print(f"[{idx}] {request_id[:8]}... status={status} elapsed={elapsed:.1f}s handled_by={handled_by}")


def monitor_budget(stop_event, min_seen: list, max_seen: list):
    """Runs in parallel, samples the Redis budget continuously to catch any violation."""
    while not stop_event.is_set():
        val = r.get("llm_call_budget")
        val = int(val) if val else 0
        if val < min_seen[0]:
            min_seen[0] = val
        if val > max_seen[0]:
            max_seen[0] = val
        time.sleep(0.05)


def main():
    print(f"Firing {NUM_REQUESTS} concurrent requests against a budget of 5...")
    print(f"Initial budget: {r.get('llm_call_budget')}\n")

    stop_event = threading.Event()
    min_seen = [999]
    max_seen = [-999]
    monitor_thread = threading.Thread(target=monitor_budget, args=(stop_event, min_seen, max_seen))
    monitor_thread.start()

    threads = []
    for i in range(NUM_REQUESTS):
        t = threading.Thread(target=submit_and_track, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    stop_event.set()
    monitor_thread.join()

    print("\n=== RESULTS ===")
    done = [r_ for r_ in results if r_["status"] == "done"]
    errors = [r_ for r_ in results if r_["status"] not in ("done",)]
    print(f"Completed: {len(done)}/{NUM_REQUESTS}")
    print(f"Failed/timeout: {len(errors)}")

    print(f"\n=== ADMISSION CONTROL CORRECTNESS ===")
    print(f"Budget min observed: {min_seen[0]}  (should be >= 0 — negative = over-admission bug)")
    print(f"Budget max observed: {max_seen[0]}  (should be <= 5 — over max = release bug)")
    print(f"Final budget: {r.get('llm_call_budget')}  (should return to 5 once all requests drain)")

    print(f"\n=== LOAD DISTRIBUTION ACROSS REPLICAS ===")
    from collections import Counter
    handler_counts = Counter(r_["handled_by"] for r_ in results if r_["status"] == "done")
    for handler, count in handler_counts.items():
        print(f"  {handler}: {count} requests")


if __name__ == "__main__":
    main()