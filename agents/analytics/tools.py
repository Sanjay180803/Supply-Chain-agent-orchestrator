import asyncio
import concurrent.futures
from fastmcp import Client

MCP_SERVER_URL = "http://localhost:8102/mcp"


def _run_async(coro):
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


def get_all_products() -> list[dict]:
    """Get all products — routed through MCP."""
    return _run_async(_call_tool("get_all_products", {}))


def get_all_suppliers() -> list[dict]:
    """Get all suppliers — routed through MCP."""
    return _run_async(_call_tool("get_all_suppliers", {}))