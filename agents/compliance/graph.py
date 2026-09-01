import json
from typing import TypedDict, Optional

from langchain_anthropic import ChatAnthropic
from langgraph.graph import StateGraph, END

from schemas import ComplianceRequest, ComplianceViolation, ComplianceDecision
from tools import check_trust_score, check_terms, check_price, MIN_TRUST_SCORE, APPROVED_TERMS

llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)


class ComplianceState(TypedDict):
    raw_request: str
    parsed_request: Optional[ComplianceRequest]
    violations: list
    decision: Optional[ComplianceDecision]
    error: Optional[str]


def parse_intent(state: ComplianceState) -> ComplianceState:
    prompt = f"""Extract compliance-check details from this text. Return ONLY valid JSON matching this schema:
{{"supplier_name": str, "trust_score": float, "terms": str, "unit_price": float, "max_approved_price": float or null}}

Text: {state['raw_request']}"""
    response = llm.invoke(prompt)
    content = response.content.strip().strip("`")
    if content.startswith("json"):
        content = content[4:]
    try:
        data = json.loads(content.strip())
        state["parsed_request"] = ComplianceRequest(**data)
    except Exception as e:
        state["error"] = f"Failed to parse intent: {e}"
    return state


def run_checks(state: ComplianceState) -> ComplianceState:
    if state.get("error"):
        return state
    req = state["parsed_request"]
    violations = []

    if not check_trust_score(req.trust_score):
        violations.append(ComplianceViolation(
            rule="minimum_trust_score",
            detail=f"Supplier trust score {req.trust_score} is below minimum {MIN_TRUST_SCORE}",
        ))

    if not check_terms(req.terms):
        violations.append(ComplianceViolation(
            rule="approved_payment_terms",
            detail=f"Terms '{req.terms}' not in approved list: {sorted(APPROVED_TERMS)}",
        ))

    if not check_price(req.unit_price, req.max_approved_price):
        violations.append(ComplianceViolation(
            rule="max_approved_price",
            detail=f"Unit price {req.unit_price} exceeds approved max {req.max_approved_price}",
        ))

    state["violations"] = violations
    return state


def finalize_decision(state: ComplianceState) -> ComplianceState:
    if state.get("error"):
        return state
    req = state["parsed_request"]
    violations = state["violations"]
    approved = len(violations) == 0

    if approved:
        rationale = f"Supplier {req.supplier_name} passed all compliance checks: trust score, payment terms, and price are within approved thresholds."
    else:
        rationale = f"Supplier {req.supplier_name} failed {len(violations)} compliance check(s): " + "; ".join(v.rule for v in violations)

    state["decision"] = ComplianceDecision(
        supplier_name=req.supplier_name,
        approved=approved,
        violations=violations,
        rationale=rationale,
    )
    return state


def build_compliance_graph():
    graph = StateGraph(ComplianceState)
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("run_checks", run_checks)
    graph.add_node("finalize_decision", finalize_decision)

    graph.set_entry_point("parse_intent")
    graph.add_edge("parse_intent", "run_checks")
    graph.add_edge("run_checks", "finalize_decision")
    graph.add_edge("finalize_decision", END)

    return graph.compile()