import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from langchain_anthropic import ChatAnthropic

app = FastAPI(title="Orchestrator")
llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)

REGISTRY_URL = "http://localhost:8001"


class OrchestrateRequest(BaseModel):
    request: str


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
    resp = requests.get(f"{REGISTRY_URL}/discover", params={"capability": capability})
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail=f"No agent found for {capability}")
    return resp.json()[0]


def dispatch(agent: dict, raw_request: str) -> dict:
    resp = requests.post(f"{agent['url']}/invoke", json={"raw_request": raw_request}, timeout=60)
    resp.raise_for_status()
    return resp.json()


@app.post("/orchestrate")
def orchestrate(req: OrchestrateRequest):
    intents = classify_intent(req.request)
    results = {}
    for intent in intents:
        try:
            agent = discover_agent(intent)
            results[intent] = dispatch(agent, req.request)
        except Exception as e:
            results[intent] = {"error": str(e)}
    return {"intents": intents, "results": results}


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)