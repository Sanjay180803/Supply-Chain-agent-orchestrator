import numpy as np
from scipy import stats
from collections import defaultdict
from logger import get_all_logs


def calculate_psi(baseline: list[float], recent: list[float], buckets: int = 10) -> float:
    """Population Stability Index — measures how much a distribution has
    shifted between two samples. PSI < 0.1: no significant shift.
    0.1-0.25: moderate shift. > 0.25: significant shift, worth investigating."""
    if len(baseline) < 2 or len(recent) < 2:
        return 0.0

    breakpoints = np.percentile(baseline, np.linspace(0, 100, buckets + 1))
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf

    baseline_counts, _ = np.histogram(baseline, bins=breakpoints)
    recent_counts, _ = np.histogram(recent, bins=breakpoints)

    baseline_pct = baseline_counts / len(baseline) + 1e-6
    recent_pct = recent_counts / len(recent) + 1e-6

    psi = np.sum((recent_pct - baseline_pct) * np.log(recent_pct / baseline_pct))
    return float(psi)


def main():
    logs = get_all_logs()
    if not logs:
        print("No execution logs found yet. Run some agent tasks first.")
        return

    # Sort chronologically (Redis LPUSH means logs are newest-first, so reverse)
    logs = sorted(logs, key=lambda e: e["timestamp"])

    by_agent = defaultdict(list)
    for entry in logs:
        if entry.get("metric_value") is not None:
            by_agent[entry["agent"]].append(entry["metric_value"])

    for agent, values in by_agent.items():
        if len(values) < 10:
            print(f"=== {agent} ===")
            print(f"  Only {len(values)} samples with metric_value — need at least 10 for meaningful drift detection.\n")
            continue

        midpoint = len(values) // 2
        baseline = values[:midpoint]
        recent = values[midpoint:]

        psi = calculate_psi(baseline, recent)
        ks_stat, ks_pvalue = stats.ks_2samp(baseline, recent)

        print(f"=== {agent} (metric: {'price' if agent in ('procurement',) else 'cost' if agent == 'logistics' else 'approval rate'}) ===")
        print(f"  Baseline: n={len(baseline)}, mean={np.mean(baseline):.2f}, std={np.std(baseline):.2f}")
        print(f"  Recent:   n={len(recent)}, mean={np.mean(recent):.2f}, std={np.std(recent):.2f}")
        print(f"  PSI: {psi:.4f}  ({'no drift' if psi < 0.1 else 'moderate drift' if psi < 0.25 else 'SIGNIFICANT DRIFT'})")
        print(f"  KS test: statistic={ks_stat:.4f}, p-value={ks_pvalue:.4f}  ({'no significant difference' if ks_pvalue > 0.05 else 'DISTRIBUTIONS DIFFER SIGNIFICANTLY'})")
        print()


if __name__ == "__main__":
    main()