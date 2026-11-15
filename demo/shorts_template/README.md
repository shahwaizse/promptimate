# Shorts template

Turns `render_shot` shots plus voiceover timing into a HyperFrames project for a vertical short (or a 16:9
animatic). It assembles the shots on hard cuts with karaoke captions in the 9:16 safe band, a hook title on frame 0,
a music slot (a silent placeholder until you add a track), whooshes on cuts and an end card.

```powershell
.venv\Scripts\python.exe demo\shorts_template\build_short.py my_short.json          # build the project
.venv\Scripts\python.exe demo\shorts_template\build_short.py my_short.json --render # + hyperframes check/render
```

The spec format is in the docstring of `build_short.py`. Output goes to `build/<name>/` (gitignored): open it in the
HyperFrames desktop app or with `npx hyperframes preview` to keep editing.

## Example: "Wrong Turn" (`story/`)

Leo, a lost traveller, walks in from the left and looks around. Ava walks in from the right and points him back the
way he came. He thanks her and jogs off. It runs 8 shots, about 21 s, with two characters. It uses `continue_from`
chains (5 clips for Leo, 3 for Ava), walk-ins generated with root paths from the staging helper, and one shared story
clock so cuts stay continuous.

```powershell
.venv\Scripts\python.exe demo\shorts_template\story\gen_motions.py   # motions via server.generate_motion
.venv\Scripts\python.exe demo\shorts_template\story\make_short.py    # shots, TTS voiceover, build, render
```

The voiceover uses local Kokoro TTS (`npx hyperframes tts`). It needs `kokoro-onnx` and `soundfile` in a Python
that `HYPERFRAMES_PYTHON` points to; `make_short.py` uses `.cache/tts-venv` if it exists.

## Example 2: "Last Bus" (`last_bus/`)

A rainy night at a bus stop. Nora walks in, sits on the bench and checks her phone, then calls home. Walt, an older
man who never goes anywhere without his coffee, sits down next to her. A passer-by crosses behind with an umbrella.
It runs 9 shots, about 31 s (28.3 s of shots plus the end card), with three cast members from the shared cast file.
It shows props in hand, sitting on furniture and night lighting with rain.

```powershell
.venv\Scripts\python.exe demo\shorts_template\last_bus\gen_motions.py   # 13 motions via server.generate_motion
.venv\Scripts\python.exe demo\shorts_template\last_bus\make_short.py    # shots (render_many), TTS, build, render
```

Output: `build/last_bus/last_bus.mp4`, a frame strip `build/last_bus_frames.png`, and timings plus per-shot validation
in `build/last_bus_report.json`.

## What a shot can contain

**Cast.** `shots.list_cast()` has 21 CC0 characters: 5 Quaternius starters, 8 more Quaternius characters (young
women and men, an older grey-haired man in a suit, a woman in a dress, a redhead, a hooded adventurer) and 8 Kenney
characters (including two kids and a heavy-set man). `build` widens the body for heavier builds. A **cast file**
(`casts/town.json`) keeps the same people across episodes: each role (`nora`, `walt`, ...) names a catalogue
character, its height and build, and the props it always carries. Pass it as `cast_file` and use the role names as
`cast`.

**Props in hand.** These props are available: phone (its screen glows), cup, coffee, bag, briefcase, sword, book,
flashlight (casts a spot light), umbrella, stick and baton. Give them per actor:
`props: ["phone", {"prop": "coffee", "hand": "left", "t": [1, 4]}]`. Use `chain_t` for times on the actor's motion
chain. Omit `props` and they are inferred from the motion prompts ("holds a phone to their ear" gives a phone in the
right hand, timed to that segment). How the props behave:
- **Grip frame.** Each prop sits in a rig-independent grip frame (fingers, thumb side, palm normal), calibrated in the
  bind pose. The style per prop is power, cup (stays upright and tilts only at the mouth), flat (phone or book),
  hang (bag) or cane.
- **Fingers.** The finger pose comes from the importer's tables (grip, flat hold).
- **Phone and book.** The hand turns so the palm faces the face (looking at a phone) or the ear (a call).
- **Size.** Props scale with the character's oversized stylised hands.
- **Body contact.** A prop that would go into the holder's head, torso or thighs swings about the grip (up to 40°),
  then slides (up to 6 cm, 15 cm for bags).

Validation reports, per prop, its drift in the hand's frame (must stay under 1 cm), how far it goes into the body
beyond the hand itself (warning above 3 cm, failure above 8 cm) and the push and swing used.

**Sitting on furniture.** `generate_motion(..., seat={"t": [start, end], "height": 0.45, "x", "z", "heading_deg"})`
sits the clip on a seat of that height. Without it the model sits on the floor even for "sits on a chair". The
seated span pins a seated lower body, eased in and out, and leaves the upper body free. `meta.seat_check` reports how
well it held.

`shots.seat_option()`, `seat_hips()` and `chain_end()` compute the seat in the clip's frame from world staging.
`render_shot` then places furniture where the clip sits (bench, chair, sofa, lounge_chair, stool, ledge, crate; or
give `furniture: [{id, type, at, yaw, seat_height, stretch}]`). Unity measures the seat top by raycast and eases the
hips onto it, keeping the feet planted.

Root motion is rescaled to metres per character, because Humanoid retargeting otherwise shortens a 1.66 m
character's walk by about 6 %, so walk-ins and seats land where they were staged.

Validation reports per seated span:
- the motion's gap to the seat before the render-time correction and the contact after it
- the hips' distance to the seat line
- foot drift

Measured in "Last Bus":

| Measure | Result |
|---|---|
| Hips height vs target, from the motion | 1.9-3.7 cm |
| Seat contact error before the render-time correction | up to 5 cm |
| Seat contact error after the correction | 0 cm |
| Feet drift while seated | under 1 cm |
| Hips to seat line | 7-18 cm |

**Night lighting.** `lighting: {"preset": "night_street", "weather": "rain" | "fog" | "rain_fog", "rim": 1.1}`
(`render_shot(weather=..., rim=...)`):
- **Rain** is particle streaks, simulated deterministically per frame and starting 3 m from the lens, plus wet, glossy
  ground that picks up the lamp highlights.
- **Fog** thickens the haze.
- **Light cones** sit under street lamps.
- **Lamps.** `street_lamp` furniture brings a practical light.
- **Extra lights.** `practicals: [{pos, color, intensity, range, type}]` adds shop windows or signs.

**Faster renders.** `shots.render_many(specs)` queues a whole shot list on the warm Unity server and encodes,
contact-sheets and validates finished shots on a thread pool while the next one renders. Unity also encodes frames on
worker threads now.

| "Last Bus", 9 final 1080x1920 shots (28.3 s of footage) | Time |
|---|---|
| Shot by shot | 75 s |
| `render_many` | 53 s |
| Unity time per frame | ~52 ms (was ~100 ms) |

## Gallery and inspection

`gallery.py` renders every camera preset, every lighting preset, the night moods (clear, rain, fog, rain + fog),
every prop in a hand and the cast line-up into `build/gallery/`. It doubles as a regression check: it exits non-zero
if any render fails validation. `inspect_assets.py [cast|props|furniture]` renders close inspection sheets for tuning
the catalogues in `mcp_server/shots.py`.

## Assets and licences

All models are CC0. They are downloaded by `unity/DemoStudio/fetch_render_assets.py` from `render_assets.json`
(sources: Quaternius and Kenney via Poly Pizza and kenney.nl, plus CC0 props by smallbigsquare and CreativeTrio) into
`Assets/ThirdParty/`, which is gitignored. Nothing third-party is committed. The umbrella, walking stick and
flashlight are built in code.

## Known limits

- The model's hand roll is loose. Phone and book poses are corrected by turning the hand, but a gesture can still
  hold the prop at an odd angle.
- Grips are approximate. There are no two-handed props yet.
- The prop and seat checks model the body as capsules, accurate to about 2-3 cm on stylised rigs.
- Seated clips need the `seat` option. A seat higher than about 0.7 m leaves the feet free, as on a bar stool.
- Kimodo sometimes performs a gesture with the other hand ("looks at a phone in their right hand" done with the
  left). Give that clip's prop to the hand the model used.
