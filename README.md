# Multi-Agent Supply Chain Orchestrator

![Tests](https://github.com/Sanjay180803/Supply-Chain-agent-orchestrator/actions/workflows/tests.yml/badge.svg)

A distributed, multi-agent supply chain platform built to explore production-grade patterns in agentic AI systems: multi-agent coordination, protocol standardization (MCP, A2A), distributed systems correctness under concurrent load, and evaluation/drift monitoring.

Four specialized LangGraph agents — **procurement**, **logistics**, **compliance**, and **analytics** — coordinate through a Kafka-queued orchestrator with Redis-backed admission control, communicate via the Model Context Protocol (MCP) and Agent2Agent (A2A) protocol, and are continuously monitored via an eval/drift pipeline.

## Architecture

```
                    ┌─────────────┐
                    │   Gateway   │  (submits requests, polls results)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │    Kafka    │  (3-partition queue)
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
  Orchestrator-1     Orchestrator-2     Orchestrator-3   (Kafka consumer group)
        │                  │                  │
        └──────────┬───────┴──────────┬───────┘
                    ▼                  ▼
              ┌──────────┐      ┌──────────┐
              │  Redis   │      │ Registry │  (agent discovery)
              │ (admission│      └────┬─────┘
              │  control) │           │
              └──────────┘   ┌────────┼────────┬────────┐
                              ▼        ▼        ▼        ▼
                        Procurement Logistics Compliance Analytics
                          (A2A)      (A2A)     (A2A)     (A2A)
                              │        │
                              ▼        ▼
                         MCP Tools  MCP Tools
                              │        │
                              └───┬────┘
                                  ▼
                          Dataset Service
                        (products, suppliers,
                         inventory, carriers)
```

Each agent is a standalone LangGraph workflow with a distinct shape:
- **Procurement** — multi-round LLM-driven negotiation between buyer and supplier
- **Logistics** — carrier ranking and selection based on cost/speed tradeoffs
- **Compliance** — rule-based policy validation (trust score, payment terms, price thresholds)
- **Analytics** — aggregation queries over the dataset (avg cost, top suppliers, supplier counts)

## Tech stack

| Layer | Technology |
|---|---|
| Agent orchestration | LangGraph, LangChain |
| LLM | Claude (Sonnet 4.6) via `langchain-anthropic` |
| Tool protocol | MCP (Model Context Protocol) via `fastmcp` |
| Agent-to-agent protocol | A2A (Agent2Agent) via `a2a-sdk` 1.1.2 |
| Message queue | Apache Kafka |
| Admission control / caching | Redis (atomic Lua scripts) |
| API layer | FastAPI |
| Load testing | Locust |
| Drift detection | PSI, KS-test (`scipy`, `numpy`) |
| Infra | Docker Compose |

## Key engineering findings

### 1. Kafka at-least-once delivery caused duplicate task processing

Under sustained load, consumer-group rebalances (triggered when a slow, LLM-bound processing cycle missed a heartbeat) redelivered messages to other orchestrator replicas after they had been processed but before the offset was committed. Without a guard, the same request would run twice and consume two credits.

**Fix:** each `request_id` has a Redis claim: `processing:<replica>` with a lease, or `done`. A redelivered message whose request is `done` is skipped; one whose request is still being processed waits for that claim to finish or expire. A failed attempt releases its claim so the redelivery retries it; a crashed attempt's claim expires.

The resulting guarantee is **at-least-once delivery with idempotent completion**: each request completes once even when delivered several times. It is not exactly-once execution: an attempt that crashes part way may already have made LLM or agent calls before the retry.

### 2. Admission control across replicas

LLM-bound work is capped at `MAX_CONCURRENT_CALLS` (default 5) across all replicas. Each in-flight request holds a **leased credit** in a Redis sorted set; acquiring is a single Lua script that drops expired leases and grants a credit only below the cap. A replica that dies without releasing loses nothing permanently: its credit returns when the lease expires (default 300 s, matching `max_poll_interval_ms`).

An earlier version used a counter (`DECR`/`INCR`), which lost credits for good when a replica died mid-request, and could exceed the cap if the budget was re-initialized while requests were in flight.

**Verified by tests** (`tests/`, run in CI against Redis): 60 concurrent acquisitions against 5 credits grant exactly 5; a dead holder's credit returns after its lease; three concurrent deliveries of one request run the work once; a failed attempt is retried and completes.

## Load test results

These numbers come from runs against the Anthropic API; the raw logs are not committed. Re-run `orchestrator/load_test.py` and `eval/run_eval_metrics.py` to reproduce them.

Median end-to-end latency for one workload — a single request that needs procurement (multi-round LLM negotiation) and logistics: **~59 s** (two runs, n = 4 and n = 82).

Per-agent latency from the eval harness (n = 72 logged executions in total). Each agent does a different amount of LLM work, so these are not comparable to each other:

| Agent | p50 latency | p95 latency | Success rate |
|---|---|---|---|
| Compliance | 1.8s | 4.8s | 100% |
| Analytics | 4.0s | 5.4s | 100% |
| Logistics | 10.3s | 16.6s | 100% |
| Procurement | 44.0s | 49.2s | 100% |

Latency scales with LLM call count per workflow — procurement's multi-round negotiation is the most expensive; compliance's single-pass rule check is the cheapest.

## Eval & drift monitoring

Every agent execution is logged (success/failure, latency, and an agent-specific drift metric) to a shared Redis log. `eval/run_eval_metrics.py` reports success rates and latency percentiles per agent; `eval/drift_monitor.py` runs PSI and KS-test comparisons between baseline and recent execution windows.

**Note on PSI at small sample sizes:** PSI's histogram-bucketing approach becomes unstable below ~10 samples per window and can report inflated drift scores that don't reflect real severity. The eval harness surfaces this limitation rather than hiding it — PSI alerts should be corroborated with the KS-test p-value before acting on them in a production setting.

## Protocols

**MCP (Model Context Protocol):** Procurement, logistics, and analytics expose their data-access tools (supplier lookup, carrier lookup, dataset aggregation) as real MCP servers via `fastmcp`, rather than direct HTTP calls. Compliance intentionally does not use MCP — its logic is pure in-memory policy validation with no external data dependency, a deliberate scope decision rather than a gap.

**A2A (Agent2Agent):** All four agents publish a real Agent Card at `/.well-known/agent-card.json` and communicate via the actual A2A JSON-RPC task lifecycle (`submitted` → `working` → `completed`/`failed`), built against `a2a-sdk` 1.1.2's protobuf-based API.

## Running locally

### Prerequisites
- Python 3.11+
- Docker Desktop
- An Anthropic API key with available credit

### 1. Start infrastructure
```bash
cd infra
docker-compose up -d
```

### 2. Seed and serve the dataset
From the repository root (the dataset service is `main.py`, `models.py`, `generate_data.py`):
```bash
pip install -r requirements.txt
python generate_data.py
python -m uvicorn main:app --port 8000
```

### 3. Start the registry
```bash
cd registry
python -m uvicorn main:app --port 8001
```

### 4. Start MCP tool servers
```bash
cd mcp_servers
pip install fastmcp requests
python procurement_tools.py    # port 8100
python logistics_tools.py      # port 8101
python analytics_tools.py      # port 8102
```

### 5. Start each agent's A2A server
Set `ANTHROPIC_API_KEY` in each terminal.
```bash
cd agents/procurement && python a2a_server.py   # port 8202
cd agents/logistics   && python a2a_server.py   # port 8203
cd agents/compliance  && python a2a_server.py   # port 8204
cd agents/analytics   && python a2a_server.py   # port 8205
```

### 6. Start the Kafka-based orchestration layer (optional, for distributed dispatch)
```bash
cd orchestrator
pip install -r requirements.txt
python create_topic.py --partitions 3        # one partition per replica
REPLICA_ID=orchestrator-1 python worker.py   # repeat in 3 terminals with different IDs
```
In another terminal, from the repository root:
```bash
cd gateway && python -m uvicorn main:app --port 8005
```
Hosts are configurable with `REDIS_URL`, `KAFKA_BOOTSTRAP` and `REGISTRY_URL`.

### 7. Send a request via A2A
```bash
cd orchestrator
python a2a_client.py
```

### 8. Run eval + drift analysis
```bash
cd eval
pip install numpy scipy redis
python run_eval_metrics.py
python drift_monitor.py
```

## Tests

```bash
pip install redis requests pytest fastapi httpx pydantic
REDIS_URL=redis://localhost:6379/15 pytest tests -v
```

Admission, claim, worker and gateway tests run against a real Redis with intent classification and agent calls stubbed, so they need no API key and make no paid calls. CI runs them on every pull request.

## Project structure

```
main.py, models.py,
generate_data.py      # dataset service: FastAPI over synthetic supply-chain data
agents/
  procurement/          # negotiation agent (LangGraph + MCP + A2A)
  logistics/             # carrier selection agent
  compliance/            # policy validation agent
  analytics/             # aggregation agent
registry/                # agent discovery service
orchestrator/            # Kafka consumer, Redis admission control, topic setup
gateway/                 # submit/poll API in front of Kafka
tests/                   # admission, idempotency, worker and gateway tests
mcp_servers/             # MCP tool servers per agent
infra/                   # Docker Compose (Kafka, Redis)
eval/                    # eval metrics + drift monitoring
load_tests/              # Locust load test
```

## What this project demonstrates

- Multi-agent coordination with distinct, non-trivial workflow shapes (negotiation, ranking, validation, aggregation)
- Standardized agent protocols (MCP for tool access, A2A for agent-to-agent communication) rather than ad-hoc HTTP calls
- Distributed systems correctness under failure (consumer rebalances, at-least-once delivery with idempotent completion, leased admission credits), covered by tests
- Production discipline: load testing, structured evaluation, and drift monitoring — with honest treatment of each tool's limitations
