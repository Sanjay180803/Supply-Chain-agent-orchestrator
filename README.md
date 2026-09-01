# Multi-Agent Supply Chain Orchestrator

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

This project was built iteratively with real production-style debugging, not a clean happy-path build. Two findings worth calling out:

### 1. Kafka at-least-once delivery caused duplicate task processing

Under sustained load, Kafka consumer group rebalances (triggered when a slow LLM-bound `poll()` cycle missed a heartbeat) caused the same message to be redelivered to multiple orchestrator replicas. Since redelivery happened *after* successful processing but *before* offset commit, this created a duplicate-credit-consumption risk in the admission control layer — directly analogous to a distributed double-spend bug.

**Fix:** a Redis `SETNX`-based idempotency guard (`already_processing_or_done()`) claims each `request_id` atomically before processing begins. Only the first delivery of a given task actually executes; redelivered duplicates are detected and skipped. Verified via load testing: budget correctly returned to full capacity (5/5) after a run that included multiple observed rebalances, with zero credit leakage.

### 2. Admission control under concurrent load

A Redis-backed atomic credit system (mirroring an exactly-once distributed admission pattern) gates concurrent LLM calls across orchestrator replicas, preventing the request rate from exceeding a configured budget regardless of how many replicas are running. Verified via Locust and custom load tests: budget never went negative or above its ceiling across 15+ concurrent requests against a 5-credit budget, even through consumer rebalances and redeliveries.

## Load test results

Median end-to-end latency (full procurement + logistics coordination, including multi-round LLM negotiation): **~59s**, consistent across two independent test runs (n=4 and n=82 samples).

Per-agent latency (from the eval harness, n=72 total logged executions):

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

### 2. Seed the dataset
```bash
cd dataset_service
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
python init_budget.py
python worker.py   # run 2-3 times with different REPLICA_ID env vars
cd gateway && python -m uvicorn main:app --port 8005
```

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

## Project structure

```
dataset_service/       # FastAPI service serving synthetic supply-chain data
agents/
  procurement/          # negotiation agent (LangGraph + MCP + A2A)
  logistics/             # carrier selection agent
  compliance/            # policy validation agent
  analytics/             # aggregation agent
registry/                # agent discovery service
orchestrator/            # Kafka consumer + Redis admission control
mcp_servers/             # MCP tool servers per agent
infra/                   # Docker Compose (Kafka, Redis)
eval/                    # eval metrics + drift monitoring
load_tests/              # Locust load test
```

## What this project demonstrates

- Multi-agent coordination with distinct, non-trivial workflow shapes (negotiation, ranking, validation, aggregation)
- Standardized agent protocols (MCP for tool access, A2A for agent-to-agent communication) rather than ad-hoc HTTP calls
- Distributed systems correctness under real failure conditions (consumer rebalances, at-least-once delivery, concurrent admission control)
- Production discipline: load testing, structured evaluation, and drift monitoring — with honest treatment of each tool's limitations
