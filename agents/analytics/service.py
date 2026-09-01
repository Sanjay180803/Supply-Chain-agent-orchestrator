  
import threading
import time
import requests
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from graph import build_analytics_graph

app = FastAPI(title="Analytics Agent")
analytics_app = build_analytics_graph()

REGISTRY_URL = "http://localhost:8001"
SELF_URL = "http://localhost:8006"


class InvokeRequest(BaseModel):
    raw_request: str


@app.post("/invoke")
def invoke(req: InvokeRequest):
    initial_state = {
        "raw_request": req.raw_request,
        "parsed_request": None,
        "decision": None,
        "error": None,
    }
    result = analytics_app.invoke(initial_state)
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
            "name": "analytics-agent",
            "capability": "analytics",
            "url": SELF_URL,
        }, timeout=3)
    except requests.RequestException as e:
        print(f"Warning: could not register with registry: {e}")


@app.on_event("startup")
def startup_event():
    threading.Thread(target=register_with_registry, daemon=True).start()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8006)