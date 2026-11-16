# Roblox "In This Town" comparison short (2026-11-16)

One 32.6 s story, "In this town, you can't sit down", made three ways in Roblox Studio with the same town, cast,
19-shot camera script, narration, captions and music. Only the character animation differs:

- **A, stock:** what agent-made shorts use today. Stock R15 animations (idle, walk, run, jump, fall, sit, wave,
  point, cheer), MoveTo-style motion at Roblox speeds, and default-Animate-script walk/run blending. It also gets
  the tricks an agent would script: a Seat, turning the body to "look around", sliding sideways to "peek", tipping
  over for a fall, and wave/point for "talking".
- **B, Promptimate:** 16 generated clips, one `continue_from` chain per character, with `root_path` blocking and the
  new `seat` option for the bench. Played with `PromptimatePlayer:Seek`.
- **C, Roblox Prompt-to-Animation:** A, plus 9 `generate_animation` clips for the beats stock can't do. That took
  11 calls, 2 of which failed server-side with "Malformed Output". Seat and ground heights were calibrated per clip.

## Run it

```powershell
.venv\Scripts\python.exe roblox\short\town.py            # build the set in the open place
.venv\Scripts\python.exe roblox\short\gen_b.py           # B motions (GPU daemon)
.venv\Scripts\python.exe roblox\short\gen_c.py           # C motions (publishes assets to the Roblox account!)
.venv\Scripts\python.exe roblox\short\calibrate.py       # bench from B's seated pose; A/C seat and ground offsets
.venv\Scripts\python.exe roblox\short\render.py A --encode   # also B, C (about 28 min each)
.venv\Scripts\python.exe demo\roblox_short\make_short.py     # VO, music, captions, 3 vertical MP4s, side-by-side, sheets
```

**Rendering.** Each frame is posed deterministically: Python computes it (`perf.py`) and `ShortDirector.lua`
applies it. The vertical 9:16 frame is then stitched from 3 pitched `screen_capture`s, related by exact
rotation homographies (`stitch.py`). This is needed because Studio's viewport is landscape and capture resets
camera roll.

## Results (blind, frames only; judges saw X/Y/Z)

| | beats read (/22), judge 1 / judge 2 | story | naturalness | continuity | rank |
|---|---|---|---|---|---|
| A stock | 14 / 8 | 6 / 5 | 5 / 4 | 5 / 5 | 2nd / 2nd |
| **B Promptimate** | **20 / 18** | **8 / 7** | **7 / 6** | **7 / 6** | **1st / 1st** |
| C Roblox P2A | 12 / 8 | 5 / 4 | 4 / 4 | 5 / 4 | 3rd / 3rd |

Raw scores are in `.cache/roblox_short/judge_scores.json`; the packets are in `build/judge/`.

## v2: the same story made only with the new tools (2026-11-16)

`perform_short.py` remakes the story (37 s, with a new ending: both characters sit side by side on a second
bench under a second NO SITTING sign). It drives the `kimodo-motion` MCP server over stdio, exactly as a creator's
Claude would: one shot list per character, read the warnings, edit, call again, then camera cues, then record.
Every call and every token sent or returned is logged in `.cache/roblox_short/v2/calls.json`; `report` summarises
them. `creator_setup.luau` is the creator's own step (cast from HumanoidDescriptions, benches), the same with or
without Promptimate.

```powershell
.venv\Scripts\python.exe demo\roblox_short\perform_short.py setup        # cast + set (Studio MCP, creator's step)
.venv\Scripts\python.exe demo\roblox_short\perform_short.py perform 4    # Timmy + Officer (share a bench), then Mrs. Lee
.venv\Scripts\python.exe demo\roblox_short\perform_short.py cameras 2    # camera checks + shot sheet
.venv\Scripts\python.exe demo\roblox_short\perform_short.py record       # 9:16 render (heavy lock), polls for the MP4
.venv\Scripts\python.exe demo\roblox_short\perform_short.py report       # calls and tokens vs the hand-built pipeline
.venv\Scripts\python.exe demo\roblox_short\hard_beats.py all|peek2       # peek / fall measurements over 4 seeds
.venv\Scripts\python.exe demo\roblox_short\two_sitters.py                # side-by-side sitting on the real rigs
```

**Cost to the agent** for one clean pass with the final tool and shot lists:

| step | calls | returned |
|---|---|---|
| Timmy + Officer performance (18 beats) | 1 | ~350 text tokens + one 393-token plan image |
| Mrs. Lee performance (3 beats) | 1 | ~95 text + 393 image |
| camera checks + 19-shot sheet | 1 | 10-140 text + 1,037 image |
| render (start, then about 3 polls, then the finished MP4 with a contact sheet) | about 5 | under 500 text + one ~1,000-token contact sheet |

The hand-built pipeline (generate_motion plus Studio MCP, from the demo's own artefacts):
- 27 generate_motion calls returning about 94k tokens.
- 1.44 M characters (about 400k tokens) of clip data that the model would have to write into `execute_luau`, two
  modules of it over the 200k source limit.
- About 3,130 Studio calls for the frame-by-frame render, each screen capture returning an image (about 3.6 M tokens).

The full development session (`calls.json`: three creator-style fix rounds plus reruns after tool fixes) came to 46
calls, about 7.7k returned text tokens and 22k image tokens.

**Staging checks that fired on real issues** (each was confirmed in Studio frames and fixed by editing the beat or
the set):
- Mrs. Lee drifted 12 studs backward through her shop door during a 34 s idle: "passes through Door/DoorGlass",
  "floats". The tool now keeps stationary beats in place.
- "Officer passes through LampPole": Bench2 had been placed over a street lamp.
- "Timmy passes through TrashCan / CrateDBand": waypoints too close.
- Mrs. Lee's mark was inside the shop doorway.
- "Bench2 is too short for everyone on it": two blocky R15 bodies need about 8 studs. The fix was a longer bench.
- The run ended at full speed, so the next crouch slid 4 m into the crates: "passes through CrateC", plus a crossed
  path in the plan image. Fixed in the tool: a path now comes to rest when the next beat is stationary.
- Cameras:
  - "peek close: camera is inside Body" (a building)
  - "Timmy hidden behind CrateB" on the run
  - "Officer hidden behind LampPole"
  - "Timmy is out of frame"
  - plus framing the sheet showed (shots aimed at an old seat spot, too tight)
- The shot sheet also caught what no check did: both characters sitting facing the backrest. The fix was backrest
  detection in the tool.

**Hard beats** (`hard_beats.json`, 4 seeds each, from a crouched hide):

| peek variant | head out toward the side | past a cover edge 0.3 m out | back in cover |
|---|---|---|---|
| demo wording ("leans to the left and peeks out"), no path | 0.29 m | 1/4 | 0/4 |
| "crouches and leans to the right to peek out", no path | 0.30 m | 1/4 | 0/4 |
| same + 0.42 m hips path | 0.23 m | 0/4 | 0/4 |
| "crouches, steps to the right and leans out to look, then steps back", no path | 0.05 m | 0/4 | 3/4 |
| same + 0.42 m path | 0.37 m | 3/4 | 3/4 |
| **same + 0.6 m path (now the `peek` default)** | **0.66 m** | **4/4 (1.1 s visible)** | **3/4** |

- **Falls.** All wordings (the demo's too) land flat on the back in 4/4 seeds within 0.6-0.9 s. The weak spot was
  the R15 rig: boxy heads and arms sank up to 1 stud into the floor on impact. `PromptimatePlayer` now lifts low
  poses so no body part goes under the clip's floor (standing poses are untouched), which removed every
  "sinks into the ground" warning in the short. `roblox_perform` also retries a fall that says "onto their back"
  but doesn't end lying down.
- **Side by side on one bench** (`two_sitters.json`, at 35.8 s):

  | | intersecting part pairs (of 225) | hips apart | seat contact |
  |---|---|---|---|
  | first version | 33 | 1.5 studs | -0.30 / -0.36 studs |
  | now | 0 | 4.0 studs | -0.16 / -0.09 studs |

  The changes: seat spots sized to each rig's measured width (torso plus arms), an R15 seat lift of 0.12 m, and
  "too short for everyone" reported instead of overlapping.

Other quality fixes found along the way:
- Seats and marks reached after a walk came out up to 0.9 m short, because cleanup removes the foot sliding the
  generator used. A bounded root warp now lands them.
- `to: "X"` with `via` now measures the stop distance from the last waypoint.
- Characters coming from behind a bench go round its end.
- The seat-front ray and the collision test ignore only the sitting surface, not the backrest.
- Collisions need 0.15 studs of penetration, so leaning against something isn't flagged.
