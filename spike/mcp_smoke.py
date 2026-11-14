"""End-to-end smoke test: spawn the MCP server over stdio and call its tools like Claude would."""
import asyncio, json, sys, time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PY = r"D:\unity-text-to-anim\.venv\Scripts\python.exe"
SERVER = r"D:\unity-text-to-anim\mcp_server\server.py"

async def main():
    async with stdio_client(StdioServerParameters(command=PY, args=[SERVER])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("tools:", [t.name for t in (await s.list_tools()).tools])
            for label, segs in [
                ("cold", [{"prompt": "a person walks forward and waves with their right hand", "seconds": 5}]),
                ("warm", [{"prompt": "a person walks forward and waves with their right hand", "seconds": 5}]),
                ("multi", [{"prompt": "a person walks forward", "seconds": 3},
                           {"prompt": "a person stops and jumps up and down", "seconds": 3}]),
            ]:
                t = time.time()
                res = await s.call_tool("generate_motion", {"segments": segs, "seed": 42, "steps": 30}, read_timeout_seconds=None)
                txt = [c.text for c in res.content if c.type == "text"]
                imgs = [c for c in res.content if c.type == "image"]
                print(f"--- {label}: {time.time()-t:.1f}s error={res.isError} images={len(imgs)}")
                print(txt[0][:1500] if txt else res)
asyncio.run(main())
