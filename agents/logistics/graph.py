import json
from typing import TypedDict, List, Optional

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END

from schemas import LogisticsRequest, CarrierOption, LogisticsDecision
from tools import find_carriers_for_region

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)


class LogisticsState(TypedDict):
    raw_request: str
    parsed_request: Optional[LogisticsRequest]
    candidates: List[CarrierOption]
    decision: Optional[LogisticsDecision]
    error: Optional[str]


def parse_intent(state: LogisticsState) -> LogisticsState:
    prompt = f"""Extract a logistics/shipping request from this text. Return ONLY valid JSON matching this schema:
{{"origin_region": str or null, "destination_region": str, "weight_kg": float, "max_transit_days": float or null}}

Valid regions: North America, Europe, APAC, LATAM, MEA

If the origin region is not stated or implied in the text, return null for origin_region — do not guess or default to any region.

Text: {state['raw_request']}"""
    response = llm.invoke(prompt)
    content = response.content.strip().strip("`")
    if content.startswith("json"):
        content = content[4:]
    try:
        data = json.loads(content.strip())
        state["parsed_request"] = LogisticsRequest(**data)
    except Exception as e:
        state["error"] = f"Failed to parse intent: {e}"
    return state


def discover_carriers(state: LogisticsState) -> LogisticsState:
    if state.get("error"):
        return state
    req = state["parsed_request"]

    # Carriers are looked up by destination region regardless of whether
    # origin is known — origin isn't used for filtering in this dataset,
    # only for record-keeping in the final decision.
    carriers = find_carriers_for_region(req.destination_region)
    if not carriers:
        state["error"] = f"No carriers found for region '{req.destination_region}'"
        return state

    candidates = []
    for c in carriers:
        candidates.append(CarrierOption(
            carrier_id=c["id"],
            carrier_name=c["name"],
            region=c["region"],
            cost_per_kg=c["cost_per_kg"],
            avg_transit_days=c["avg_transit_days"],
            total_cost=round(c["cost_per_kg"] * req.weight_kg, 2),
        ))
    state["candidates"] = candidates
    return state


def rank_carriers(state: LogisticsState) -> LogisticsState:
    if state.get("error"):
        return state
    req = state["parsed_request"]
    for c in state["candidates"]:
        cost_score = 1 / c.total_cost if c.total_cost > 0 else 0
        speed_score = 1 / (c.avg_transit_days + 1)
        penalty = 1.0
        if req.max_transit_days and c.avg_transit_days > req.max_transit_days:
            penalty = 0.3
        c.score = (cost_score * 0.5 + speed_score * 0.5) * penalty

    state["candidates"] = sorted(state["candidates"], key=lambda c: c.score, reverse=True)
    return state


def finalize_decision(state: LogisticsState) -> LogisticsState:
    if state.get("error"):
        return state
    req = state["parsed_request"]
    top = state["candidates"][0]

    rationale_prompt = f"""In 2-3 sentences, explain why {top.carrier_name} was chosen for this shipment:
total cost ${top.total_cost:.2f}, estimated transit {top.avg_transit_days} days.
State the reasoning confidently and factually — do not mention data limitations,
missing context, or ask for more information."""
    rationale_response = llm.invoke(rationale_prompt)

    state["decision"] = LogisticsDecision(
        origin_region=req.origin_region,  # may be None — that's fine now
        destination_region=req.destination_region,
        weight_kg=req.weight_kg,
        chosen_carrier=top.carrier_name,
        total_cost=top.total_cost,
        estimated_transit_days=top.avg_transit_days,
        rationale=rationale_response.content.strip(),
    )
    return state


def build_logistics_graph():
    graph = StateGraph(LogisticsState)
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("discover_carriers", discover_carriers)
    graph.add_node("rank_carriers", rank_carriers)
    graph.add_node("finalize_decision", finalize_decision)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "discover_carriers")
    graph.add_edge("discover_carriers", "rank_carriers")
    graph.add_edge("rank_carriers", "finalize_decision")
    graph.add_edge("finalize_decision", END)

    return graph.compile()