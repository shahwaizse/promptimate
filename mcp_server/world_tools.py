"""MCP tools for text-to-world (mcp_server/world.py, Unity project unity/WorldLab): build a room from text or a spec,
relight it, list what's in it, and render Promptimate actors inside it. Registered by server.py."""
from __future__ import annotations

import json

BUILD_DOC = """Build a 3D room in Unity from a description or a world spec, and render it.

`description`: one line ("a cramped 1970s detective office at night, rain on the window, a desk lamp") is expanded
by keywords; for real control pass `spec` (a dict) instead: room {w, d, h}, style/era tags, openings (windows/doors
per wall), items with relations ("against the north wall", "at the desk", "on the desk"), clutter density,
materials, and lighting {time, weather, mood, practicals}. See demo/world/README.md for the format. Rooms: office,
living room, bedroom, cafe, workshop, subway platform. Assets are CC0 (Poly Haven, ambientCG, Kenney, Quaternius).
The layout solver keeps doors, windows and a walkway clear and drops items onto real surfaces; lighting is physical
(lumens, Kelvin, sun from time of day, exposure metered at the focus point). Returns world_id, stills, a 6 s camera
move MP4 (move=false skips it), validation (overlaps, floating items, exposure) and a contact sheet; look at it.
Use describe_world for actor staging and render_world_shot to put Promptimate characters in it. The first call
starts the WorldLab Unity server (about a minute; the first ever import takes ~10 minutes)."""

SHOT_DOC = """render_shot inside a world from build_world. `shot` is a render_shot spec without stage/lighting (the
world provides both): {actors: [{id, cast, motions: [...], at, yaw, sit: [{on: <world item id>, t: [t0, t1]}]}],
camera, aspect, seconds, name}. Generate the motions first; use describe_world for positions, and its seat entries
(hips, face_yaw, height) for generate_motion's `seat` option so the actor sits on the generated chair. Doors open
for walk-ins. Returns the MP4, validation and a contact sheet."""


def register(mcp, server_module=None):
    import anyio
    from mcp.server.fastmcp import Image

    import world

    def _with_sheet(res: dict) -> list:
        sheet = res.get("sheet") or res.get("contact_sheet")
        out = [json.dumps(res, indent=2, default=str)]
        if sheet:
            out.append(Image(path=sheet))
        return out

    @mcp.tool(description=BUILD_DOC)
    async def build_world(description: str | None = None, spec: dict | None = None, name: str | None = None,
                          move: bool = True) -> list:
        if not description and not spec:
            raise ValueError("give a description or a spec")
        res = await anyio.to_thread.run_sync(lambda: world.build_world(spec or description, name=name, move=move))
        return _with_sheet(res)

    @mcp.tool()
    async def light_world(world_id: str, lighting: str | dict, name: str | None = None) -> list:
        """Relight a built world, keeping the room and layout: `lighting` is text ("afternoon sun through the
        blinds", "storm at night") or a dict {time, weather, mood, practicals}. Returns a new world_id with stills,
        validation and a contact sheet."""
        res = await anyio.to_thread.run_sync(lambda: world.light_world(world_id, lighting, name=name))
        return _with_sheet(res)

    @mcp.tool()
    def describe_world(world_id: str) -> str:
        """What's in a world, for staging actors: room size, doors/windows (with a point just inside each door),
        the walkway, and every placed item with position and facing. Seats include the hips target, facing and
        height for generate_motion's `seat` option. +Z is north; coordinates in metres, room centred at the origin."""
        return json.dumps(world.describe(world_id), indent=2)

    @mcp.tool(description=SHOT_DOC)
    async def render_world_shot(world_id: str, shot: dict, force: bool = False) -> list:
        res = await anyio.to_thread.run_sync(lambda: world.render_world_shot(world_id, shot, force=force))
        return _with_sheet(res)
