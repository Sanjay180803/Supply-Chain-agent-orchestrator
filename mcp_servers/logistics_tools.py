from fastmcp import FastMCP
import requests

DATASET_SERVICE_URL = "http://localhost:8000"

mcp = FastMCP("logistics-tools")


@mcp.tool
def find_carriers_for_region(region: str) -> list[dict]:
    """Get available carriers serving a given region, with cost and transit time."""
    resp = requests.get(f"{DATASET_SERVICE_URL}/carriers", params={"region": region})
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8101)