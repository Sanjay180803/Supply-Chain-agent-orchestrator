import asyncio
from fastmcp import Client

async def main():
    async with Client("http://localhost:8100/mcp") as client:
        tools = await client.list_tools()
        print("Available tools:", [t.name for t in tools])

        result = await client.call_tool("find_product", {"product_name": "Conference"})
        print("find_product result:", result)

if __name__ == "__main__":
    asyncio.run(main())