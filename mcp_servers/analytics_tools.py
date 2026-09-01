from fastmcp import FastMCP
import requests

DATASET_SERVICE_URL = "http://localhost:8000"

mcp = FastMCP("analytics-tools")


@mcp.tool
def get_all_products() -> list[dict]:
    """Get all products in the supply chain dataset."""
    resp = requests.get(f"{DATASET_SERVICE_URL}/products")
    resp.raise_for_status()
    return resp.json()


@mcp.tool
def get_all_suppliers() -> list[dict]:
    """Get all suppliers in the supply chain dataset."""
    resp = requests.get(f"{DATASET_SERVICE_URL}/suppliers")
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8102)