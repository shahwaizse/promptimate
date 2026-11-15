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
