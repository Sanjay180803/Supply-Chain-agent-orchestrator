import statistics
from collections import defaultdict
from logger import get_all_logs


def main():
    logs = get_all_logs()
    if not logs:
        print("No execution logs found yet. Run some agent tasks first.")
        return

    by_agent = defaultdict(list)
    for entry in logs:
        by_agent[entry["agent"]].append(entry)

    print(f"Total logged executions: {len(logs)}\n")

    for agent, entries in by_agent.items():
        total = len(entries)
        successes = [e for e in entries if e["success"]]
        failures = [e for e in entries if not e["success"]]
        success_rate = len(successes) / total * 100

        latencies = sorted(e["latency_ms"] for e in entries)
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0]

        print(f"=== {agent} ===")
        print(f"  Total executions: {total}")
        print(f"  Success rate: {success_rate:.1f}%  ({len(successes)}/{total})")
        print(f"  Latency p50: {p50:.0f}ms, p95: {p95:.0f}ms")

        if failures:
            print(f"  Failure reasons:")
            error_counts = defaultdict(int)
            for f in failures:
                error_counts[f.get("error", "unknown")[:80]] += 1
            for err, count in error_counts.items():
                print(f"    ({count}x) {err}")
        print()


if __name__ == "__main__":
    main()