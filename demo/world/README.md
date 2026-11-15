# Text-to-world (prototype)

Promptimate turns text into motion. This prototype extends it to **places**: a sentence ("a cramped 1970s detective
office at night, rain on the window, a desk lamp, cigarette smoke") becomes a furnished, lit Unity room built from
real CC0 assets. Promptimate characters can then act in it, and the same room can be relit from text (day, night,
storm).

```
text ──expand()/Claude──▶ world spec (JSON) ──resolve()──▶ layout + lights + cameras ──WorldLab (Unity URP)──▶ stills, camera move, report
                                                  ▲                                                          │
                              tagged CC0 library + real mesh sizes (measure())          validate(): bounds, drops, cameras, exposure
```

| Piece | Where |
|---|---|
| Python side (spec, solver, light physics, render client, validation, character shots) | `mcp_server/world.py` |
| Unity project (URP 17, Unity 6000.0.34) | `unity/WorldLab/` (`Assets/Editor/WorldLab/*`; `Assets/Editor/ShotStudio/*` is a copy of DemoStudio's shot renderer, patched to accept `stage: "world:<json>"`) |
| Asset library manifest and fetcher | `unity/WorldLab/world_assets.json`, `unity/WorldLab/fetch_world_assets.py` |
| Demo driver, expanded specs, renders | `demo/world/run_demo.py`, `demo/world/specs/`, `demo/world/build/` (gitignored) |

## Run it

```powershell
.venv\Scripts\python unity\WorldLab\fetch_world_assets.py      # ~150 CC0 files, ~100 s, no login
.venv\Scripts\python -c "import sys; sys.path.insert(0,'mcp_server'); import world; world.measure()"   # real sizes + HDRI radiance (first import of the project: ~10 min)
.venv\Scripts\python demo\world\run_demo.py --shot <motion name>
```

Every Unity session runs under `scripts/heavy_lock.py` (`world.session()`), and the editor closes afterwards.

## MCP-style API (`mcp_server/world.py`, not wired into `server.py` yet)

| Function | Returns |
|---|---|
| `expand(text, seed)` | a world spec from one sentence (keyword stand-in for Claude writing the spec) |
| `build_world(spec_or_text, name?, render=True, move=True)` | `world_id`, `stills` (wide/detail/reverse PNG), `mp4` (6 s camera move), `sheet`, `validation`, `lighting` (EV, white balance, lux), `unplaced`, `notes`, timings |
| `light_world(world_id, lighting)` | the same room and layout relit; `lighting` is a dict (`{"time": "night", "weather": "storm", "mood": "tense"}`) or text (`"storm at dusk"`) |
| `describe(world_id)` | room, doors (with an inside approach point), every item with position/yaw/size, and for seats the hips target |
| `seat_target(world_id, item_id)` | hips (x, z), facing, seat height and a `render_shot` furniture entry for that exact chair, to plug into `generate_motion(seat=...)` |
| `render_world_shot(world_id, shot)` | `render_shot` in the generated room: same shot spec (actors, camera, props, `sit: [{on: <world item>, t: [..]}]`), the world supplies stage and light, and the seats become measured shot furniture. Returns mp4, contact sheet and the usual shot validation |
| `measure(lineup=True)` | Unity measures every model's real size after its scale rule and each HDRI's radiance; writes `.cache/world/asset_sizes.json` and front-view lineups for checking model orientation |

Suggested tool wiring: `build_world(spec) -> {world_id, preview}` is `build_world`; `light_world(scene, mood)` is
`light_world`; `render_shot(..., world=<id>)` is `render_world_shot`.

## Spec format (what Claude writes)

```jsonc
{
  "name": "office", "seed": 1,
  "style": ["noir", "1970s", "vintage", "office"],            // drives asset + material + HDRI choice by tags
  "room": {"size": [4.5, 3.8], "height": 2.9,
           "floor": {"tags": ["noir", "1970s"]},              // or a material id ("herringbone_parquet")
           "walls": "dark_paneled_wood", "ceiling": "ceiling_plaster",
           "trench": {"wall": "north", "width": 3.4, "depth": 1.25},   // optional: subway track bed (rails, sleepers, edge strip, tunnel mouths)
           "columns": {"count": 4, "offset": 2.2}},
  "openings": [
    {"type": "window", "wall": "north", "at": 0.5, "width": 1.5, "height": 1.5, "sill": 0.85, "blinds": true, "rainy": true, "curtains": false},
    {"type": "door", "wall": "south", "at": 0.2, "width": 0.92, "height": 2.1, "open": 0}       // also "arch"
  ],
  "items": [
    {"id": "desk", "cat": "desk", "against": "north", "user_faces": "room", "at": 0.5},
    {"id": "desk_chair", "cat": "chair", "at_desk": "desk", "prefer": "armchair_victorian"},
    {"id": "visitor_chair", "cat": "chair", "in_front_of": "desk", "facing": "desk", "count": 2},
    {"id": "desk_lamp", "cat": "lamp_desk", "on": "desk", "side": "left", "light": {"on": true}},
    {"id": "phone", "cat": "phone", "on": "desk", "side": "right"},
    {"id": "cabinet", "cat": "cabinet", "against": "west", "at": 0.7},
    {"id": "coat_rack", "cat": "coat_rack", "corner": "sw"},
    {"id": "fan", "cat": "ceiling_fan", "ceiling": true, "above": "desk"},
    {"id": "frame", "cat": "frame", "on_wall": "west", "above": "cabinet"},
    {"id": "rug", "cat": "rug", "under": ["sofa", "coffee_table"]},
    {"id": "lights", "cat": "lamp_ceiling", "grid": [6, 2]}
  ],
  "clutter": 0.7,                                             // surface, floor and wall decor density 0..1
  "lighting": {"time": "night",                               // dawn sunrise morning noon afternoon golden_hour dusk evening night, or an hour (21.5)
               "weather": "rain",                             // clear partly_cloudy overcast rain storm snow fog
               "mood": "noir",                                // neutral noir cozy cheerful eerie gloomy clinical romantic tense
               "window_light": "street",                      // auto | sky | street | moon | none
               "practicals": {"desk_lamp": {"lumens": 450, "kelvin": 2700}, "all": null},
               "extra": [{"source": "neon_red", "pos": [1, 2, 1.8]}],
               "haze": 0.5, "exposure": 0, "white_balance": null, "hdri": null},
  "effects": [{"type": "smoke", "source": "ashtray"}, {"type": "steam", "source": "mug"}],
  "camera": {"focus": "desk", "move": "push_in", "fov": 52, "seconds": 6}
}
```

Relations: `against` (wall or `any`, with `at` = fraction along the wall, `gap`), `corner` (`ne/nw/se/sw`), `at` [x, z],
`at_frac` [fx, fz], `center`, `at_desk` (the knee side of a desk, tucked under), `in_front_of` (a desk's visitor
side, otherwise the item's front; `count` spreads them), `beside` (`side` left/right relative to the item's front),
`around` (chairs round a table), `near` (`dist`), `opposite`, `facing` (item, `door`, `window`, `center`), `on`
(surface; `side` left/right/center from the user's side of a desk), `on_wall` (`above`, `height`, `at`), `ceiling`
(`above`, `grid`), `under` (rugs), `count`, `prefer` (a library id). Room axes: metres, +X east, +Z north, the
default camera audience is on the south side (same convention as `render_shot`).

## How it works

**Assets.** `world_assets.json` tags 115 models, 33 materials and 14 HDRIs with a category, placement (floor, wall,
surface, ceiling, seat), size, style and era tags, seat and top heights, a front correction, and built-in practical
lights (lumens, Kelvin, bulb offset, spot or point). `measure()` replaces the guessed sizes with what Unity actually
loads. That pass caught a Poly Haven model authored in centimetres (10× too big), three models facing sideways, and a
"phone" that was really a 6 cm smartphone (replaced by a procedural 1970s desk phone). Missing props are procedural:
ashtray with a glowing cigarette, rugs with borders, deterministic abstract paintings, signs, and blinds as real slats.

**Layout.** Greedy over candidate positions generated from each relation, with hard constraints:
- inside the walkable floor (a subway trench removes a strip);
- no overlaps, except a chair tucked under its own desk;
- door swing zones stay clear;
- tall pieces don't stand in front of windows;
- clearance in front of desks, sofas and shelves;
- wall items clear of openings and of tall furniture.

Soft scores cover relation error and spacing. A walkway check (grid BFS from the door, 0.2 m body radius) must reach
the room centre and every access point (seat fronts, the end of a desk whose user faces the room). When a choice
would wall something off, the next candidate is tried. Repair: when a piece doesn't fit at all (a 2 m desk in a
cramped office), smaller assets of the same category are tried. Then come surface clutter (style-matched, unique,
only on surfaces below 1.3 m), floor clutter along walls, wall decor, rugs under seating groups, and ceiling fixtures.
Unity snaps every model by its real mesh bounds: floor items to y = 0, wall items flush to their wall, surface items
by ray cast onto the parent's actual top, ceiling items under the ceiling.

**Light from text (physically based, then exposed like a camera):**
- Time of day gives sun elevation, direct sun (lux) and sky illuminance with their colour temperatures (noon sun
  100 000 lx at 5600 K, golden hour 14 000 lx at 3000 K, night sky 0.3 lx). Weather scales them (overcast removes
  direct sun, storm drops the sky to 20 %).
- The sun is aimed through the main window. At night the window gets a sodium street lamp (2000 K spot, about 22 lx
  at the glass for noir) and moonlight (0.35 lx, 4100 K).
- Practicals use real lumens and Kelvin (a 60 W bulb is 800 lm at 2700 K, a candle 12 lm at 1850 K, a fluorescent
  tube 2600 lm at 4300 K). Candela comes from the cone for spots.
- Indirect light uses a split-flux estimate: (window flux + lamp flux) × mean albedo / (room surface × (1 − albedo)),
  plus a bounce light where the sun patch lands.
- A **light meter at the focus point** sets EV100, offset by the mood's EV bias. Every light is converted to Unity
  intensity relative to that exposure (1.0 = a white surface at middle exposure).
- The camera white is the illuminance-weighted colour temperature at the meter plus the mood's shift. Every light
  colour is von Kries-adapted to it, which is why moonlight comes out blue and tungsten amber under a 4200 K noir
  white, without hand-picked colours.
- The HDRI (window view + reflections) is picked by time/weather/environment tags. Its exposure is matched to the
  computed sky luminance using the radiance Unity measured around its horizon.
- Mood also sets contrast, saturation, bloom, vignette, grain and shadow/highlight tints. Abandoned or eerie rooms get
  dead and flickering tubes.

**Atmosphere.** Cigarette smoke and steam (particles with noise), fake volumetric shafts (the window extruded along the
light direction, additive), dust motes in the beam, rain or snow outside the window, a rain normal map scrolling on
the glass, double-strike lightning flashes (directional light + sky exposure), flickering practicals, a box-projected
reflection probe and SSAO. All of it is simulated deterministically per frame.

**Cameras.** A wide establishing shot from the far side of the room facing the focus (line-of-sight and furniture
checks), a detail shot, and a reverse. The move (dolly or push-in) has its endpoints validated. Walls between the camera and the
room become shadow-only (a film-set cutaway that keeps the room light-tight).

**Validation** (automatic, every build): real mesh bounds overlapping, items floating or sunk, surface drops that
missed, anything poking out of the room or through the ceiling, cameras inside furniture, walkway reachability,
unplaced items, and image statistics per still (mean, p05/p95, clipped and black share: too dark, washed out or blown
out).

## Assets and licences

Everything is **CC0 1.0** and downloadable without a login. Nothing is committed; `fetch_world_assets.py` writes a
`LICENSES.md` with the source page of every file next to the downloads.

| Source | What | Licence |
|---|---|---|
| [Poly Haven](https://polyhaven.com) (API `api.polyhaven.com`) | ~105 scanned models (glTF, 1k textures), 27 PBR materials (diffuse, GL normal, roughness), 14 HDRIs (2k .hdr) | CC0 |
| [ambientCG](https://ambientcg.com) | 6 materials (wallpapers, tiles, carpet, fabric) | CC0 |
| [Kenney](https://kenney.nl) Furniture Kit | fallback models (desk, bed, coat rack, floor lamp, boxes) | CC0 |
| Quaternius / Poly Pizza | the character cast (same as `render_shot`) | CC0 |
| Procedural (Promptimate) | ashtray, desk phone, rugs, paintings, signs, blinds, curtains, doors, room shell | — |

## Results (2026-11-16, RX 6600 XT, `run_demo.py`)

Renders: `demo/world/build/` (`overview.jpg` is a 3x3 sheet; each world folder has `wide/detail/reverse.png`, a 6 s
1080p camera move `.mp4`, `report.json`, `result.json`). Expanded specs: `demo/world/specs/`.

| World (one-line prompt) | Items | EV100 / WB | Unity render | Validation |
|---|---|---|---|---|
| office: "cramped 1970s detective office at night, rain on the window, desk lamp, cigarette smoke, venetian blinds" | 18 | 6.0 / 4200 K | 19 s | ok (wide still flagged dark: noir) |
| office relit "afternoon, clear" (practicals off) | same layout | 9.3 / 7500 K | 6 s | ok (sun patch through the blinds: 26 % clipped in the detail still) |
| office relit "storm at dusk, tense" | same layout | 6.1 / 2700 K | 6 s | ok (lightning in the move) |
| living: "cozy Scandinavian living room on a winter morning, snow, fireplace, candles" | 23 | 9.0 / 6600 K | 13 s | ok |
| subway: "abandoned subway platform at night" | 31 | 5.4 / 3800 K | 12 s | ok |
| workshop: "dusty abandoned workshop at golden hour" | 16 | 8.2 / 3600 K | 7 s | ok |
| character: man_suit walks in through the door, round the desk, sits in the generated desk chair, picks up the phone (10.1 s) | | | 14 s | render_shot checks passed (warnings: feet slide 56 cm while seated, phone grazes torso) |

The layout solve takes 0.05–0.6 s per room. A build is about 10–20 s in a warm editor plus about 14 s of ffmpeg.
The whole demo (7 builds and the shot) took about 6 minutes in one Unity session, not counting the wait for the
shared heavy lock. One-time costs: asset fetch 99 s; first project import and measure about 10 min. The motion took
about 64 s of GPU time (681 s wall: motiond was shared).

What the automatic checks caught during development:
- the measure function routed to the wrong renderer;
- a model authored in centimetres;
- side-facing models;
- a rug outside the room and a camera inside the fireplace;
- an inverted exposure bias that blew out every scene;
- a white balance that turned a golden-hour room blue.

## Limits (honest)

- **Lighting is real-time URP, not GI.** Indirect light is an estimate plus a bounce light, Unity's ambient has no
  occlusion (SSAO helps), and volumetrics are faked with additive geometry. Adaptive Probe Volumes or a lightmap bake
  would be the next step. An HDRP project (another agent's fidelity work) would give physical light units and
  volumetric fog.
- **Rectangular rooms only** (plus trench and columns). No L-shapes, stairs, multi-room layouts or exteriors.
- **Library size.** About 115 models: good coverage for offices, living rooms, workshops and stations; thin for
  kitchens, bathrooms, shops and anything period-specific. Missing categories fall back to Kenney low-poly or
  procedural pieces, and the style mix shows.
- **The expander is keywords**, not language understanding. Claude writing the spec directly is the intended path.
- **Model metadata is partly hand-set** (seat/top heights, bulb offsets, fronts): `measure()` checks sizes, and the
  front-view lineups make fronts easy to check, but bulb offsets are still manual.
- **Characters:** seats re-use `render_shot`'s seat logic. Routing a walk around furniture is planned by hand
  (`describe()` gives positions); a path planner over the solver's walkway grid is the obvious next step.
- **No local ML component yet.** A texture/painting/window-panorama generator (stable-diffusion.cpp on Vulkan) was
  skipped for time; the procedural paintings and HDRIs fill that role.
