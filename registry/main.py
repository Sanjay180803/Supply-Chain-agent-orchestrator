from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List
import requests

app = FastAPI(title="Agent Registry")


class AgentRegistration(BaseModel):
    name: str
    capability: str   # e.g. "procurement", "logistics"
    url: str          # base url of the agent service


class AgentInfo(AgentRegistration):
    healthy: bool = True


REGISTRY: Dict[str, AgentInfo] = {}


@app.post("/register")
def register_agent(agent: AgentRegistration):
    REGISTRY[agent.name] = AgentInfo(**agent.dict())
    return {"status": "registered", "name": agent.name}


@app.get("/discover")
def discover(capability: str) -> List[AgentInfo]:
    matches = [a for a in REGISTRY.values() if a.capability == capability]
    healthy_matches = []
    for m in matches:
        try:
            resp = requests.get(f"{m.url}/health", timeout=2)
            m.healthy = resp.status_code == 200
        except requests.RequestException:
            m.healthy = False
        if m.healthy:
            healthy_matches.append(m)
    if not healthy_matches:
        raise HTTPException(status_code=404, detail=f"No healthy agents for capability '{capability}'")
    return healthy_matches


@app.get("/agents")
def list_agents():
    return list(REGISTRY.values())


@app.get("/")
def root():
    return {"status": "ok", "service": "registry"}