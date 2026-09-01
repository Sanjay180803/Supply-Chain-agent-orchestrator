import json
from typing import TypedDict, Optional
from collections import defaultdict

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END

from schemas import AnalyticsRequest, AnalyticsDecision
from tools import get_all_products, get_all_suppliers

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)


class AnalyticsState(TypedDict):
    raw_request: str
    parsed_request: Optional[AnalyticsRequest]
    decision: Optional[AnalyticsDecision]
    error: Optional[str]


def parse_intent(state: AnalyticsState) -> AnalyticsState:
    prompt = f"""Extract an analytics query from this text. Return ONLY valid JSON matching this schema:
{{"metric": "avg_cost_per_category" | "supplier_count_by_country" | "top_suppliers_by_trust", "filter_category": str or null, "filter_country": str or null}}

Text: {state['raw_request']}"""
    response = llm.invoke(prompt)
    content = response.content.strip().strip("`")
    if content.startswith("json"):
        content = content[4:]
    try:
        data = json.loads(content.strip())
        state["parsed_request"] = AnalyticsRequest(**data)
    except Exception as e:
        state["error"] = f"Failed to parse intent: {e}"
    return state


def compute_metric(state: AnalyticsState) -> AnalyticsState:
    if state.get("error"):
        return state
    req = state["parsed_request"]

    if req.metric == "avg_cost_per_category":
        products = get_all_products()
        totals = defaultdict(list)
        for p in products:
            totals[p["category"]].append(p["unit_cost"])
        result = {cat: round(sum(costs) / len(costs), 2) for cat, costs in totals.items()}
        summary = f"Computed average unit cost across {len(totals)} categories."

    elif req.metric == "supplier_count_by_country":
        suppliers = get_all_suppliers()
        counts = defaultdict(int)
        for s in suppliers:
            counts[s["country"]] += 1
        result = dict(counts)
        summary = f"Counted suppliers across {len(counts)} countries."

    elif req.metric == "top_suppliers_by_trust":
        suppliers = get_all_suppliers()
        top = sorted(suppliers, key=lambda s: s["trust_score"], reverse=True)[:5]
        result = {s["name"]: s["trust_score"] for s in top}
        summary = "Identified top 5 suppliers by trust score."

    else:
        state["error"] = f"Unknown metric: {req.metric}"
        return state

    state["decision"] = AnalyticsDecision(metric=req.metric, result=result, summary=summary)
    return state


def build_analytics_graph():
    graph = StateGraph(AnalyticsState)
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("compute_metric", compute_metric)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "compute_metric")
    graph.add_edge("compute_metric", END)

    return graph.compile()