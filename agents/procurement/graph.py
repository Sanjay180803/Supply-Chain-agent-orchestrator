import json
from typing import TypedDict, List, Optional

 # swap for your provider of choice

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END

from schemas import ProcurementRequest, SupplierCandidate, ProcurementDecision, NegotiationRound
from tools import find_product, find_suppliers_for_category, get_supplier_contracts
llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)


class ProcurementState(TypedDict):
    raw_request: str
    parsed_request: Optional[ProcurementRequest]
    product: Optional[dict]
    candidates: List[SupplierCandidate]
    negotiation_rounds: List[NegotiationRound]
    decision: Optional[ProcurementDecision]
    error: Optional[str]


def parse_intent(state: ProcurementState) -> ProcurementState:
    prompt = f"""Extract a procurement request from this text. Return ONLY valid JSON matching this schema:
{{"product_name": str, "quantity": int, "max_unit_price": float or null, "max_lead_time_days": int or null}}

Text: {state['raw_request']}"""
    response = llm.invoke(prompt)
    try:
        data = json.loads(response.content.strip().strip("```json").strip("```"))
        state["parsed_request"] = ProcurementRequest(**data)
    except Exception as e:
        state["error"] = f"Failed to parse intent: {e}"
    return state


def discover_suppliers(state: ProcurementState) -> ProcurementState:
    if state.get("error"):
        return state

    req = state["parsed_request"]
    product = find_product(req.product_name)
    if not product:
        state["error"] = f"No product found matching '{req.product_name}'"
        return state
    state["product"] = product

    suppliers = find_suppliers_for_category(product["category"])
    candidates = []
    for supplier in suppliers:
        contracts = get_supplier_contracts(supplier["id"])
        for contract in contracts:
            if contract["product_id"] == product["id"]:
                candidates.append(SupplierCandidate(
                    supplier_id=supplier["id"],
                    supplier_name=supplier["name"],
                    price=contract["price"],
                    lead_time_days=contract["lead_time_days"],
                    trust_score=supplier["trust_score"],
                    terms=contract["terms"],
                ))
    if not candidates:
        state["error"] = "No suppliers found with a contract for this product"
        return state

    state["candidates"] = candidates
    return state


def rank_candidates(state: ProcurementState) -> ProcurementState:
    if state.get("error"):
        return state

    req = state["parsed_request"]
    for c in state["candidates"]:
        price_score = 1 / c.price if c.price > 0 else 0
        lead_time_score = 1 / (c.lead_time_days + 1)
        c.score = (price_score * 0.5) + (lead_time_score * 0.2) + (c.trust_score * 0.3)

    state["candidates"] = sorted(state["candidates"], key=lambda c: c.score, reverse=True)
    return state


def negotiate(state: ProcurementState) -> ProcurementState:
    if state.get("error"):
        return state

    top_candidate = state["candidates"][0]
    req = state["parsed_request"]
    rounds: List[NegotiationRound] = []

    current_price = top_candidate.price
    target_price = req.max_unit_price if req.max_unit_price else current_price * 0.9

    for round_num in range(1, 4):
        prompt = f"""You are negotiating a bulk purchase on behalf of a buyer.
Current supplier price: ${current_price:.2f}/unit. Quantity: {req.quantity}.
Buyer's target price: ${target_price:.2f}/unit.

As the SUPPLIER, respond with a counter price (a single number) that moves toward the target
but doesn't go below your cost margin (assume margin floor is 85% of current price).
Return ONLY the number."""
        response = llm.invoke(prompt)
        try:
            counter_price = float(response.content.strip().replace("$", ""))
        except ValueError:
            counter_price = current_price

        accepted = counter_price <= target_price * 1.05  # accept if within 5% of target
        rounds.append(NegotiationRound(
            round_number=round_num,
            proposed_price=current_price,
            counter_price=counter_price,
            accepted=accepted,
        ))

        current_price = counter_price
        if accepted:
            break

    state["negotiation_rounds"] = rounds
    top_candidate.price = current_price
    return state


def finalize_decision(state: ProcurementState) -> ProcurementState:
    if state.get("error"):
        return state

    top_candidate = state["candidates"][0]
    req = state["parsed_request"]

    rationale_prompt = f"""In 2-3 sentences, explain why {top_candidate.supplier_name} was chosen
for this procurement: price ${top_candidate.price:.2f}/unit, lead time {top_candidate.lead_time_days} days,
trust score {top_candidate.trust_score}, terms {top_candidate.terms}. Be concise and factual."""
    rationale_response = llm.invoke(rationale_prompt)

    state["decision"] = ProcurementDecision(
        product_name=req.product_name,
        quantity=req.quantity,
        chosen_supplier=top_candidate.supplier_name,
        final_price=top_candidate.price,
        lead_time_days=top_candidate.lead_time_days,
        terms=top_candidate.terms,
        rationale=rationale_response.content.strip(),
        negotiation_rounds=state["negotiation_rounds"],
    )
    return state


def build_procurement_graph():
    graph = StateGraph(ProcurementState)

    graph.add_node("parse_intent", parse_intent)
    graph.add_node("discover_suppliers", discover_suppliers)
    graph.add_node("rank_candidates", rank_candidates)
    graph.add_node("negotiate", negotiate)
    graph.add_node("finalize_decision", finalize_decision)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "discover_suppliers")
    graph.add_edge("discover_suppliers", "rank_candidates")
    graph.add_edge("rank_candidates", "negotiate")
    graph.add_edge("negotiate", "finalize_decision")
    graph.add_edge("finalize_decision", END)

    return graph.compile()