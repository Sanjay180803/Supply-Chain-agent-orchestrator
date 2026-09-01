from graph import build_compliance_graph

def main():
    app = build_compliance_graph()
    test_request = "Check compliance for supplier Shady Corp with trust score 0.3, terms cash-on-delivery, unit price 500, max approved price 300"
    initial_state = {
        "raw_request": test_request,
        "parsed_request": None,
        "violations": [],
        "decision": None,
        "error": None,
    }
    result = app.invoke(initial_state)
    if result.get("error"):
        print("ERROR:", result["error"])
        return
    print(result["decision"].model_dump())

if __name__ == "__main__":
    main()