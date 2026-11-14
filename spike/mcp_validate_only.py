import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
    p = StdioServerParameters(command=r"D:\unity-text-to-anim\.venv\Scripts\python.exe", args=[r"D:\unity-text-to-anim\mcp_server\server.py"])
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("validate_in_unity", {"self_test": True}, read_timeout_seconds=None)
            print(res.content[0].text)
asyncio.run(main())
