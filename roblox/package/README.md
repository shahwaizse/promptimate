# Promptimate for Roblox story shorts

Agent-made Roblox shorts ("In This Town" style) with generated character performances instead of the stock
animation IDs. The agent (Claude Code, Claude Desktop, or any MCP client) writes a shot list per character.
Promptimate generates it locally as one connected chain, places it in the place's coordinates, and pushes it
straight into the open Studio place. The tool returns a few hundred tokens and never the clip data.

## Pieces

| Where | What |
|---|---|
| `mcp_server/roblox_tools.py` | MCP tools `roblox_perform` and `roblox_install` (in the `kimodo-motion` server) |
| `mcp_server/roblox_record.py` | MCP tool `roblox_record`: camera checks, shot sheet, frame-by-frame 9:16 render |
| `mcp_server/roblox_studio.py` | Persistent session to Studio's built-in MCP server; ModuleScript upload with chunking |
| `roblox/PromptimatePlayer.lua` | Plays one clip on any R15 rig (Motor6D or AnimationConstraint), with foot locking. Low poses (lying, falls, crawling) are lifted so no box goes under the floor; opt out with `groundClamp = false` |
| `roblox/package/ShortDirector.lua` | Plays every character's chain from the cue sheet: `play()` realtime, `seek(t)` per frame, plus the staging probes |
| `roblox/package/PromptimateAutoplay.*.lua` | Pressing Play performs everything (client in Play mode, server in Run mode) |
| `roblox/package/PROMPT.md` | Section to paste into the popular free "In This Town" prompt |

In the place, everything lives in `ReplicatedStorage.Promptimate`: `PromptimatePlayer` and `ShortDirector`, `Clips/`
(one ModuleScript per clip, split into `<name>__1..n` chunks above the 200k-character source limit), and
`Performance` (the cue sheet: each character's rig path, then clips with start time, world origin and facing).
Folder attributes: `Autoplay` (default true), `StartDelay` (seconds), `PackageVersion`.

## Tools

- **`roblox_perform(actors, check=true, preview=true)`** takes `actors = [{name, start?, facing?, append?, beats: [...]}]`.
  Each beat is `{prompt | [prompts], seconds | [seconds], at?, to?, via?, arrive?, face?, sit?, sit_from?, peek?}`.
  Positions are in studs, in world X/Z.
  - `to` accepts `[x, z]`, an object or character name, or `Name:+X` (a side). It stops short of objects (about
    0.55 m) and of people (about 1.1 m, talking distance).
  - `sit` accepts an object (its seat surface: a `Seat`, a visible part named Seat*, or the highest low surface,
    such as bench slats) or a seat height in studs.
  - `face` is the end facing. It uses the engine's heading constraint on the last 8 frames, and the clip is
    re-checked and regenerated with a new seed (up to 3 tries) when it ends more than 30 degrees off. Path end
    (over 0.5 m) and seat fit get the same treatment.
  - Staging checks run on the real rig in the place, with everyone else posed at the same time:
    - wrong end facing
    - floating or sinking into the ground
    - the body passing through props (oriented-box test)
    - hovering above or sinking into the seat
    - two characters overlapping

  Built-in fixes for problems measured in the remake (`demo/roblox_short/README.md`, v2):
  - Stationary beats (idling, talking, arms crossed, hiding) are generated in place. A 34 s idle otherwise drifted
    12 studs.
  - A path comes to rest before a stationary next beat, so momentum doesn't carry into it.
  - Seats and marks are landed exactly with a bounded root warp. Cleanup otherwise gives back up to 0.9 m.
  - Seat spots are sized to each rig's width, and the tool says when a seat is too short for everyone on it.
  - Seats get an R15 lift of 0.12 m.
  - Characters approaching from behind a bench go round its end.
  - `peek` uses a 0.6 m sideways path with step-out wording (head 0.66 m out, 4/4 seeds past the cover edge).
  - A fall that says "onto their back" is retried until it ends lying down.

  Beats are cached by their spec, so re-calling after an edit regenerates only the edited beat and the ones after
  it. The result is compact JSON (clip names, start and duration, where each character ends, warnings) plus a plan
  image (top view of paths and end facings, and a beat timeline).
- **`roblox_record(shots, start, end, fps=24, quality=final|draft, check_only, sheet, audio, job)`** takes cues
  `{start, pos+look | track+offset+aim, fov, subjects, name}`. Camera checks run at the start, middle and end of
  each shot:
  - the camera inside or within 0.5 studs of a part or body
  - a subject's head and torso blocked
  - a subject out of frame or their head cut off

  With `sheet=true` it also returns one draft frame per shot. Rendering runs in the background (poll with
  `job`) and writes `.cache/roblox_perform/record/<name>/<name>_<quality>.mp4`.
- **`roblox_install(force)`** installs or updates the package (`roblox_perform` calls it automatically).

## Realtime fallback

Press Play. `PromptimateAutoplay` runs `ShortDirector.autoplay()`, which performs every chain in real time on the
client. Screen-record the Studio window (OBS, or Win+Alt+R). For vertical video, roll the camera 90 degrees and
rotate the recording, as the Ovra prompt does. The frame-by-frame recorder exists because Studio's viewport is
landscape and a screen recording drops frames when Studio is busy.

## Requirements

- Windows with Roblox Studio, and "Enable Studio as MCP server" turned on (Assistant > ... > Manage MCP Servers).
- The Promptimate engine on a local GPU. It's tested on an 8 GB AMD card over Vulkan; see the main README for
  setup. Generation takes about 10-20 s per beat once the models are warm.
- Python env from `setup.ps1`. The MCP server `mcp_server/server.py` is the `kimodo-motion` server.
