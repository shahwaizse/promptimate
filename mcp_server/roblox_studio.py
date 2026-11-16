"""Roblox Studio access for the Promptimate MCP tools: one persistent session to Studio's built-in MCP server
(roblox/tools/studio_mcp.py), run on its own event-loop thread so synchronous tool code can call it.

    st = studio()                      # shared, opened on first use (Studio must have a place open with
    st.luau("return 1")                # 'Enable Studio as MCP server' on)
    st.upload({"Name": src, ...}, folder="Clips")   # ModuleScripts into ReplicatedStorage.Promptimate[/folder],
                                                    # long sources chunked under the 200k character limit
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "roblox" / "tools"))

MODULE_LIMIT = 199_000      # ModuleScript.Source cap is 200,000 characters
CHUNK = 150_000             # chunk size for long clip data
CALL_BUDGET = 420_000       # characters of Luau per execute_luau call when batching small modules


def long_str(s: str) -> str:
    """Luau long-bracket literal that can't be closed by the content."""
    eq = "=" * 3
    while f"]{eq}]" in s:
        eq += "="
    return f"[{eq}[{s}]{eq}]"


def chunk_module(name: str, body: str, folder_path: str) -> dict[str, str]:
    """ModuleScript sources for a data string: one module returning it, or (if too long) chunk modules
    '<name>__1..n' plus a main module that concatenates them. folder_path: Luau expression of the folder."""
    src = f"return {long_str(body)}\n"
    if len(src) <= MODULE_LIMIT:
        return {name: src}
    parts = [body[i:i + CHUNK] for i in range(0, len(body), CHUNK)]
    mods = {f"{name}__{k + 1}": f"return {long_str(p)}\n" for k, p in enumerate(parts)}
    mods[name] = (f"local F = {folder_path}\nreturn "
                  + " .. ".join(f"require(F[{json.dumps(f'{name}__{k + 1}')}])" for k in range(len(parts))) + "\n")
    return mods


class Studio:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="roblox-studio")
        self._thread.start()
        self._sess = None
        self._lock = threading.RLock()
        self.calls = 0

    def _run(self, coro, timeout: float = 300):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _ensure(self):
        if self._sess is None:
            from studio_mcp import StudioSession
            s = StudioSession()
            self._run(s.__aenter__(), 90)
            self._run(asyncio.sleep(2), 10)   # Studio finishes registering the proxy
            self._sess = s
        return self._sess

    def reset(self):
        with self._lock:
            if self._sess is not None:
                try:
                    self._run(self._sess.__aexit__(None, None, None), 20)
                except Exception:
                    pass
            self._sess = None

    def call(self, tool: str, args: dict | None = None, timeout: float = 300) -> dict:
        with self._lock:
            for attempt in range(2):
                try:
                    s = self._ensure()
                    self.calls += 1
                    return self._run(s.call(tool, args), timeout)
                except (RuntimeError, OSError, asyncio.TimeoutError, ConnectionError) as e:
                    if attempt:
                        raise RuntimeError(f"Roblox Studio MCP call failed: {e}") from e
                    self.reset()
        raise AssertionError

    def luau(self, code: str, timeout: float = 300) -> str:
        """Run Luau in the open place; returns the text result, raises on a Luau error."""
        for attempt in range(4):
            r = self.call("execute_luau", {"code": code, "datamodel_type": "Edit"}, timeout)
            text = next((c for c in r["content"] if isinstance(c, str)), "")
            if r["isError"] and "not reachable" in text and attempt < 3:
                time.sleep(3 * (attempt + 1))   # Studio busy (e.g. mid-save / switching data models): retry
                continue
            if r["isError"]:
                raise RuntimeError(f"Luau error: {text[:2000]}")
            return text
        return text

    def luau_json(self, code: str, timeout: float = 300):
        return json.loads(self.luau(code, timeout))

    def upload(self, mods: dict[str, str], folder: str = "") -> int:
        """Create/replace ModuleScripts in ReplicatedStorage.Promptimate (or its subfolder `folder`); several small
        modules go in one call. Returns the number of execute_luau calls used."""
        head = ('local RS = game:GetService("ReplicatedStorage")\n'
                'local root = RS:FindFirstChild("Promptimate") or Instance.new("Folder")\n'
                'root.Name = "Promptimate"; root.Parent = RS\nlocal F = root\n')
        if folder:
            head += (f'F = root:FindFirstChild({json.dumps(folder)}) or Instance.new("Folder")\n'
                     f'F.Name = {json.dumps(folder)}; F.Parent = root\n')
        head += ('local function put(n, s) local m = F:FindFirstChild(n) or Instance.new("ModuleScript");'
                 ' m.Name = n; m.Source = s; m.Parent = F end\n')
        calls, batch, size = 0, [], 0
        items = list(mods.items())

        def flush():
            nonlocal calls, batch, size
            if batch:
                self.luau(head + "\n".join(batch) + f"\nreturn {len(batch)}")
                calls += 1
            batch, size = [], 0

        for name, src in items:
            line = f"put({json.dumps(name)}, {long_str(src)})"
            if size + len(line) > CALL_BUDGET:
                flush()
            batch.append(line)
            size += len(line)
        flush()
        return calls


_STUDIO: Studio | None = None


def studio() -> Studio:
    global _STUDIO
    if _STUDIO is None:
        _STUDIO = Studio()
    return _STUDIO
