"""Smoke test 2: generation with automatic Python + headless-Unity validation, plus validate_in_unity self-test."""
import asyncio, json, time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
PY = r"D:\unity-text-to-anim\.venv\Scripts\python.exe"
SERVER = r"D:\unity-text-to-anim\mcp_server\server.py"
async def main():
    async with stdio_client(StdioServerParameters(command=PY, args=[SERVER])) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("tools:", [t.name for t in (await s.list_tools()).tools])
            for segs in ([{"prompt": "a person raises both arms out to the sides, then turns to the left", "seconds": 5}],
                         [{"prompt": "a person walks forward", "seconds": 3}, {"prompt": "a person turns around and walks back", "seconds": 4}]):
                t = time.time()
                res = await s.call_tool("generate_motion", {"segments": segs, "seed": 7}, read_timeout_seconds=None)
                m = json.loads(res.content[0].text)
                print(f"--- {time.time()-t:.1f}s gen={m['generation']['seconds']}s cold={m['generation']['cold_start']}")
                print("checks:", json.dumps(m["checks"]))
                print("unity:", json.dumps(m["unity_validation"]))
                print("preview:", m["files"]["preview"])
            res = await s.call_tool("validate_in_unity", {"self_test": True}, read_timeout_seconds=None)
            print("--- validate_in_unity self_test:\n", res.content[0].text[:3000])
asyncio.run(main())
