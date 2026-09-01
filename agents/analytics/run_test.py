from graph import build_analytics_graph

def main():
    app = build_analytics_graph()
    test_request = "What's the average cost per category?"
    initial_state = {
        "raw_request": test_request,
        "parsed_request": None,
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