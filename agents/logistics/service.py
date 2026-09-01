import threading
import time
import requests
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from graph import build_logistics_graph

app = FastAPI(title="Logistics Agent")
logistics_app = build_logistics_graph()

REGISTRY_URL = "http://localhost:8001"
SELF_URL = "http://localhost:8003"


class InvokeRequest(BaseModel):
    raw_request: str


@app.post("/invoke")
def invoke(req: InvokeRequest):
    initial_state = {
        "raw_request": req.raw_request,
        "parsed_request": None,
        "candidates": [],
        "decision": None,
        "error": None,
    }
    result = logistics_app.invoke(initial_state)
    if result.get("error"):
        return {"error": result["error"]}
    return {"decision": result["decision"].model_dump()}


@app.get("/health")
def health():
    return {"status": "ok"}


def register_with_registry():
    time.sleep(1)
    try:
        requests.post(f"{REGISTRY_URL}/register", json={
            "name": "logistics-agent",
            "capability": "logistics",
            "url": SELF_URL,
        }, timeout=3)
    except requests.RequestException as e:
        print(f"Warning: could not register with registry: {e}")


@app.on_event("startup")
def startup_event():
    threading.Thread(target=register_with_registry, daemon=True).start()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)