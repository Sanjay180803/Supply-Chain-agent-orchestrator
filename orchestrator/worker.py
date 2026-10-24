import json
import os
import time
import requests

import admission
from admission import acquire_credit, mark_done, release_claim, release_credit, wait_for_claim

REPLICA_ID = os.getenv("REPLICA_ID", "orchestrator-0")
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8001")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
REQUEST_TOPIC = "supply-chain-requests"

_llm = None


def get_llm():
    global _llm
    if _llm is None:
        from langchain_anthropic import ChatAnthropic

        _llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    return _llm


def classify_intent(text: str) -> list[str]:
    prompt = f"""Classify this supply-chain request into one or more categories:
"procurement" (sourcing/buying products from suppliers)
"logistics" (shipping/carrier/transport)

Return ONLY a JSON list, e.g. ["procurement"] or ["procurement", "logistics"].

Request: {text}"""
    response = get_llm().invoke(prompt)
    content = response.content.strip().strip("`")
    if content.startswith("json"):
        content = content[4:]
    try:
        return json.loads(content.strip())
    except Exception:
        return ["procurement"]


def discover_agent(capability: str) -> dict:
    resp = requests.get(f"{REGISTRY_URL}/discover", params={"capability": capability}, timeout=5)
    resp.raise_for_status()
    return resp.json()[0]


def dispatch(agent: dict, raw_request: str) -> dict:
    resp = requests.post(f"{agent['url']}/invoke", json={"raw_request": raw_request}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def process_request(request_id: str, raw_request: str) -> str:
    """Process one delivery of a request. Returns "done" (completed now),
    "duplicate" (already completed by an earlier delivery) or
    "rejected" (no capacity). Raises if processing failed, after releasing
    the claim so a redelivery can retry."""
    r = admission.client()
    if wait_for_claim(request_id, REPLICA_ID) == "done":
        print(f"[{REPLICA_ID}] Skipping duplicate delivery of {request_id}")
        return "duplicate"

    print(f"[{REPLICA_ID}] Processing {request_id}")
    r.set(f"status:{request_id}", "processing", ex=300)

    holder = acquire_credit(f"{REPLICA_ID}:{request_id}", timeout_seconds=15.0)
    if holder is None:
        r.set(f"result:{request_id}", json.dumps({"error": "admission timeout — system at capacity"}), ex=300)
        r.set(f"status:{request_id}", "done", ex=300)
        mark_done(request_id)
        print(f"[{REPLICA_ID}] Admission timeout for {request_id}")
        return "rejected"

    try:
        intents = classify_intent(raw_request)
        results = {}
        for intent in intents:
            try:
                agent = discover_agent(intent)
                results[intent] = dispatch(agent, raw_request)
            except Exception as e:
                results[intent] = {"error": str(e)}

        final_result = {"intents": intents, "results": results, "handled_by": REPLICA_ID}
        r.set(f"result:{request_id}", json.dumps(final_result), ex=300)
        r.set(f"status:{request_id}", "done", ex=300)
        mark_done(request_id)
        print(f"[{REPLICA_ID}] Completed {request_id}")
        return "done"
    except Exception:
        # Without this, the claim would block every redelivery until it
        # expired and the request would never complete.
        release_claim(request_id, REPLICA_ID)
        r.set(f"status:{request_id}", "queued", ex=300)
        raise
    finally:
        release_credit(holder)


def run_consumer_loop():
    from kafka import KafkaConsumer
    from kafka.errors import CommitFailedError

    consumer = KafkaConsumer(
        REQUEST_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="orchestrator-group",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        session_timeout_ms=45000,
        heartbeat_interval_ms=3000,
        max_poll_interval_ms=300000,
    )
    print(f"[{REPLICA_ID}] Listening on {REQUEST_TOPIC}...")
    for message in consumer:
        payload = message.value
        process_request(payload["request_id"], payload["request"])
        try:
            consumer.commit()
        except CommitFailedError:
            print(f"[{REPLICA_ID}] Commit failed — was evicted from group, will rejoin")
            consumer.close()
            return


def main():
    from kafka.errors import KafkaError

    while True:
        try:
            run_consumer_loop()
        except KafkaError as e:
            print(f"[{REPLICA_ID}] Kafka error: {e}, restarting consumer in 3s...")
        except Exception as e:
            print(f"[{REPLICA_ID}] Unexpected error: {e}, restarting consumer in 3s...")
        time.sleep(3)


if __name__ == "__main__":
    main()