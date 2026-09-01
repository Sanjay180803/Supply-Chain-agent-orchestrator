from graph import build_procurement_graph

def main():
    app = build_procurement_graph()

    test_request = "I need to source 500 units of Conference electronics unit with a target price under $60 per unit"

    initial_state = {
        "raw_request": test_request,
        "parsed_request": None,
        "product": None,
        "candidates": [],
        "negotiation_rounds": [],
        "decision": None,
        "error": None,
    }

    result = app.invoke(initial_state)

    if result.get("error"):
        print("ERROR:", result["error"])
        return

    decision = result["decision"]
    print("\n=== PROCUREMENT DECISION ===")
    print(f"Product: {decision.product_name} x{decision.quantity}")
    print(f"Supplier: {decision.chosen_supplier}")
    print(f"Final price: ${decision.final_price:.2f}/unit")
    print(f"Lead time: {decision.lead_time_days} days")
    print(f"Terms: {decision.terms}")
    print(f"\nRationale: {decision.rationale}")
    print(f"\nNegotiation rounds: {len(decision.negotiation_rounds)}")
    for r in decision.negotiation_rounds:
        print(f"  Round {r.round_number}: proposed ${r.proposed_price:.2f} -> counter ${r.counter_price:.2f} "
              f"({'accepted' if r.accepted else 'continuing'})")


if __name__ == "__main__":
    main()