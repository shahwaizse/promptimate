r"""Client for Roblox Studio's built-in MCP server (Studio > Assistant > ... > Manage MCP Servers > "Enable Studio as
MCP server"). StudioMCP.exe hosts a local endpoint that Studio connects to, so a session must stay open for a few
seconds until Studio registers; then Studio's own tools (execute_luau, generate_animation, screen_capture, ...) work.

CLI:
    .venv\Scripts\python roblox\tools\studio_mcp.py list                 # tool names
    .venv\Scripts\python roblox\tools\studio_mcp.py call <tool> '<json>'  # studio_id is filled in automatically
    .venv\Scripts\python roblox\tools\studio_mcp.py luau <file.luau|-> [Edit|Server|Client]

Python:
    async with StudioSession() as s:
        out = await s.call("execute_luau", {"code": "return 1+1"})
"""
from __future__ import annotations

import asyncio
import contextlib
import glob
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _params() -> StdioServerParameters:
    bat = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Roblox", "mcp.bat")
    if os.path.exists(bat):  # written by Studio when the MCP server is enabled (official launch path)
        return StdioServerParameters(command="cmd.exe", args=["/c", bat], env=dict(os.environ))
    roots = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Roblox", "Versions"), r"D:\Roblox\Versions"]
    found = sorted((p for r in roots for p in glob.glob(os.path.join(r, "*", "StudioMCP.exe"))),
                   key=os.path.getmtime, reverse=True)
    if not found:
        raise SystemExit("StudioMCP.exe not found; is Roblox Studio installed?")
    return StdioServerParameters(command=found[0], args=[], env=dict(os.environ))


class StudioSession:
    """Open session to StudioMCP; waits until a Studio instance with an open place has registered."""

    def __init__(self, wait_s: float = 45.0, prefer: str = ""):
        self.wait_s, self.prefer = wait_s, prefer
        self.studio_id: str | None = None

    async def __aenter__(self):
        self._stack = contextlib.AsyncExitStack()
        r, w = await self._stack.enter_async_context(stdio_client(_params()))
        self._sess = await self._stack.enter_async_context(ClientSession(r, w))
        await self._sess.initialize()
        deadline = asyncio.get_event_loop().time() + self.wait_s
        while True:
            res = await self._sess.call_tool("list_roblox_studios", {})
            studios = json.loads(res.content[0].text).get("studios", []) if res.content else []
            if studios:
                pick = next((s for s in studios if self.prefer and self.prefer in json.dumps(s)), studios[0])
                self.studio_id = pick.get("id")
                self.studios = studios
                break
            if asyncio.get_event_loop().time() > deadline:
                raise RuntimeError("no Roblox Studio instance registered with the MCP server (is a place open and "
                                   "'Enable Studio as MCP server' on?)")
            await asyncio.sleep(2)
        return self

    async def __aexit__(self, *exc):
        with contextlib.suppress(Exception):
            await self._stack.aclose()

    async def tools(self) -> list:
        return (await self._sess.list_tools()).tools

    async def call(self, tool: str, args: dict | None = None) -> dict:
        args = dict(args or {})
        args.setdefault("studio_id", self.studio_id)
        res = await self._sess.call_tool(tool, args)
        return {"isError": res.isError,
                "content": [getattr(c, "text", None) or {"type": c.type, "data": getattr(c, "data", None)}
                            for c in res.content]}

    async def luau(self, code: str, datamodel: str = "Edit") -> dict:
        return await self.call("execute_luau", {"code": code, "datamodel_type": datamodel})


async def _main(argv: list[str]):
    async with StudioSession() as s:
        if argv[0] == "list":
            print("studios:", json.dumps(s.studios))
            for t in await s.tools():
                print(f"- {t.name}: {(t.description or '').strip().splitlines()[0][:200]}")
        elif argv[0] == "call":
            print(json.dumps(await s.call(argv[1], json.loads(argv[2]) if len(argv) > 2 else {}), indent=2)[:20000])
        elif argv[0] == "luau":
            code = sys.stdin.read() if argv[1] == "-" else open(argv[1], encoding="utf-8").read()
            print(json.dumps(await s.luau(code, argv[2] if len(argv) > 2 else "Edit"), indent=2)[:20000])


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
