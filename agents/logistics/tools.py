import asyncio
import concurrent.futures
from fastmcp import Client

MCP_SERVER_URL = "http://localhost:8101/mcp"


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


def find_carriers_for_region(region: str) -> list[dict]:
    """Get carriers for a region — routed through MCP."""
    return _run_async(_call_tool("find_carriers_for_region", {"region": region}))