import json
import uuid
from fastapi import FastAPI
import future
from pydantic import BaseModel
from kafka import KafkaProducer
import redis

app = FastAPI(title="Supply Chain Gateway")

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

REQUEST_TOPIC = "supply-chain-requests"


class GatewayRequest(BaseModel):
    request: str


@app.post("/submit")
def submit(req: GatewayRequest):
    request_id = str(uuid.uuid4())
    payload = {"request_id": request_id, "request": req.request}
    future = producer.send(REQUEST_TOPIC, payload)
    try:
        future.get(timeout=10)
    except Exception as e:
        return {"error": f"Failed to publish to Kafka: {e}"}
    producer.flush()
    r.set(f"status:{request_id}", "queued", ex=300)
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