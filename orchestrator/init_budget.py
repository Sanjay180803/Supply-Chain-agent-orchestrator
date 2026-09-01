from admission import init_budget, current_budget

if __name__ == "__main__":
    init_budget()
    print(f"Budget initialized: {current_budget()}")