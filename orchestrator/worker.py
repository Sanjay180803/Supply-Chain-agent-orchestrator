import json
import os
import time
import requests
from kafka import KafkaConsumer
from kafka.errors import CommitFailedError, KafkaError
import redis
from langchain_anthropic import ChatAnthropic

from admission import acquire_credit, release_credit, init_budget, already_processing_or_done

REPLICA_ID = os.getenv("REPLICA_ID", "orchestrator-0")
REGISTRY_URL = "http://localhost:8001"
REQUEST_TOPIC = "supply-chain-requests"

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
r = redis.Redis(host="localhost", port=6379, decode_responses=True)


def classify_intent(text: str) -> list[str]:
    prompt = f"""Classify this supply-chain request into one or more categories:
"procurement" (sourcing/buying products from suppliers)
"logistics" (shipping/carrier/transport)

Return ONLY a JSON list, e.g. ["procurement"] or ["procurement", "logistics"].

Request: {text}"""
    response = llm.invoke(prompt)
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


def process_request(request_id: str, raw_request: str):
    if already_processing_or_done(request_id):
        print(f"[{REPLICA_ID}] Skipping duplicate delivery of {request_id}")
        return

    print(f"[{REPLICA_ID}] Processing {request_id}")
    r.set(f"status:{request_id}", "processing", ex=300)

    if not acquire_credit(timeout_seconds=15.0):
        r.set(f"status:{request_id}", "done", ex=300)
        r.set(f"result:{request_id}", json.dumps({"error": "admission timeout — system at capacity"}), ex=300)
        print(f"[{REPLICA_ID}] Admission timeout for {request_id}")
        return

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
        print(f"[{REPLICA_ID}] Completed {request_id}")
    finally:
        release_credit()


def run_consumer_loop():
    consumer = KafkaConsumer(
        REQUEST_TOPIC,
        bootstrap_servers="localhost:9092",
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