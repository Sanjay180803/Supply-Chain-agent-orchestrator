from fastmcp import FastMCP
import requests

DATASET_SERVICE_URL = "http://localhost:8000"

mcp = FastMCP("procurement-tools")


@mcp.tool
def find_product(product_name: str) -> dict:
    """Look up a product by fuzzy name match against the supply chain dataset."""
    resp = requests.get(f"{DATASET_SERVICE_URL}/products")
    resp.raise_for_status()
    products = resp.json()
    product_name_lower = product_name.lower()
    for p in products:
        if product_name_lower in p["name"].lower():
            return p
    return {"error": f"No product found matching '{product_name}'"}


@mcp.tool
def find_suppliers_for_category(category: str) -> list[dict]:
    """Get suppliers capable of supplying a given product category."""
    resp = requests.get(f"{DATASET_SERVICE_URL}/suppliers", params={"capability": category})
    resp.raise_for_status()
    return resp.json()


@mcp.tool
def get_supplier_contracts(supplier_id: int) -> list[dict]:
    """Get a supplier's contract terms (price, lead time, terms) for all products they cover."""
    resp = requests.get(f"{DATASET_SERVICE_URL}/suppliers/{supplier_id}/contracts")
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    # Streamable HTTP transport so it runs as a standalone service like your other agents
    mcp.run(transport="http", host="0.0.0.0", port=8100)