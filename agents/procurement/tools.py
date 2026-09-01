import asyncio
import concurrent.futures
from fastmcp import Client

MCP_SERVER_URL = "http://localhost:8100/mcp"


def _run_async(coro):
    """Run an async coroutine from sync code, whether or not an event loop
    is already running. asyncio.run() fails inside an existing loop (e.g.
    when called from within the A2A executor's async execute()), so we
    detect that case and run the coroutine in a separate thread with its
    own event loop instead."""
    try:
        asyncio.get_running_loop()

        def run_in_new_loop():
            return asyncio.run(coro)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_in_new_loop)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


async def _call_tool(tool_name: str, arguments: dict):
    async with Client(MCP_SERVER_URL) as client:
        result = await client.call_tool(tool_name, arguments)
        return result.data


def find_product(product_name: str) -> dict | None:
    """Look up a product by fuzzy name match — routed through MCP."""
    result = _run_async(_call_tool("find_product", {"product_name": product_name}))
    if isinstance(result, dict) and "error" in result:
        return None
    return result


def find_suppliers_for_category(category: str) -> list[dict]:
    """Get suppliers capable of supplying a given product category — routed through MCP."""
    return _run_async(_call_tool("find_suppliers_for_category", {"category": category}))


def get_supplier_contracts(supplier_id: int) -> list[dict]:
    """Get a supplier's contract terms — routed through MCP."""
    return _run_async(_call_tool("get_supplier_contracts", {"supplier_id": supplier_id}))