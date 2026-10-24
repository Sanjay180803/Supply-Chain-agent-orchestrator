import json
import os
import uuid

import redis
from fastapi import FastAPI
from pydantic import BaseModel

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = FastAPI(title="Supply Chain Gateway")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

_producer = None


def get_producer():
    global _producer
    if _producer is None:
        from kafka import KafkaProducer

        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
    return _producer

REQUEST_TOPIC = "supply-chain-requests"


class GatewayRequest(BaseModel):
    request: str


@app.post("/submit")
def submit(req: GatewayRequest):
    request_id = str(uuid.uuid4())
    payload = {"request_id": request_id, "request": req.request}
    # Record the status before publishing. Setting it afterwards raced with
    # fast workers: a worker could finish and write "done", and then this
    # line overwrote it with "queued", so the client polled until timeout.
    r.set(f"status:{request_id}", "queued", ex=300)
    try:
        get_producer().send(REQUEST_TOPIC, payload).get(timeout=10)
    except Exception as e:
        r.delete(f"status:{request_id}")
        return {"error": f"Failed to publish to Kafka: {e}"}
    return {"request_id": request_id, "status": "queued"}


@app.get("/result/{request_id}")
def get_result(request_id: str):
    status = r.get(f"status:{request_id}")
    if status is None:
        return {"error": "unknown request_id"}
    if status != "done":
        return {"status": status}
    result_raw = r.get(f"result:{request_id}")
    return {"status": "done", "result": json.loads(result_raw)}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)