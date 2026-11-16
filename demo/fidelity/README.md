# Fidelity: "Your Move"

A 2.39:1 short (42 s with cards). It shows what Promptimate's Unity route looks like when the renderer is set to
fidelity instead of speed: realistic humans, a photographic set and an offline HDRP **path tracer** with real motion
blur, depth of field and denoising, all on one RX 6600 XT.

**Story.** Late afternoon in an old living room. A father waits at the window. His daughter comes in with a suitcase
and sets it down. He turns, gestures to the chess table by the window, and they sit down across the board. He moves a
pawn: *your move.*

Every body motion is a Promptimate clip from `server.generate_motion` (14 clips, two `continue_from` chains, root paths,
seats). Faces are static, so the staging keeps them backlit, in profile, small in frame or turned away.

| Output | Path (gitignored) |
|---|---|
| Final film (master, CRF 14) | `demo/fidelity/build/your_move.mp4` |
| Web copy (CRF 21, 18 MB) | `demo/fidelity/build/your_move_web.mp4` |
| Frames (PNG, per shot) | `demo/fidelity/build/final/<shot>/fNNNN.png` |
| Stills | `demo/fidelity/build/stills/` |
| Before/after comparison | `demo/fidelity/build/compare_before_after.png` |

## How to rebuild

```powershell
.venv\Scripts\python.exe unity\FidelityStudio\fetch_assets.py      # Poly Haven + Rocketbox (no login), ~0.5 GB
.venv\Scripts\python.exe demo\fidelity\fetch_audio.py              # CC0 music + sound effects
.venv\Scripts\python.exe demo\fidelity\gen_motions.py              # 14 motions through the motiond daemon
.venv\Scripts\python.exe demo\fidelity\make_film.py --mode raster --res 960x408 --step 3   # fast blocking preview
.venv\Scripts\python.exe demo\fidelity\make_film.py --mode pt --spp 48 --res 1280x544 --stills 2.5,13.9,27.6
.venv\Scripts\python.exe demo\fidelity\make_film.py --mode pt --spp 80 --run final           # final frames
.venv\Scripts\python.exe demo\fidelity\assemble.py --run final     # grade, letterbox, cards, sound mix -> mp4
.venv\Scripts\python.exe demo\fidelity\compare.py --run final      # stills + before/after sheet
```

`make_film.py` holds `scripts/heavy_lock.py` for the whole render. It renders in chunks (`--chunk 55`, see below) and
relaunches Unity with `-resume`, which skips frames already on disk, after a chunk ends or after a crash.

## How it's made

### Project: `unity/FidelityStudio/` (HDRP 17.0.3, Unity 6000.0.34f1, DX12)

This is a new project, so the URP DemoStudio is untouched. It reuses the `com.promptimate.unity` package (the
`.kimodo` importer gives Humanoid clips with root motion, hand poses and IK curves). Settings and pipeline assets
are generated from code (`Setup.cs`): linear colour, DX12, and HDRP with ray tracing, path tracing, volumetrics and
SSS support.

| File | Role |
|---|---|
| `Film.cs` | Offline renderer: FilmSpec JSON in, PNG frames out. Ported actor playback from ShotStudio (segments on one story clock, metric root-motion travel, seats). Adds a physical camera with keyframes, rack focus and handheld noise, plus accumulation rendering and the render-time acting fixes below. |
| `Room.cs` | The set. The shell, window, pleated curtains and trim are code. Furniture comes from Poly Haven, and small props are dropped onto surfaces by raycast. |
| `Characters.cs` | Rocketbox avatars as HDRP characters: Humanoid rigs, HDRP Lit materials rebuilt from the avatars' textures, alpha-clipped hair and lashes, deterministic blinks through facial blendshapes. |
| `Lib.cs` | Materials (Poly Haven glTF → HDRP/Lit straight from the glTF JSON; glTFast's HDRP shader graphs render magenta here and are skipped by the path tracer), lights, HDRI, capture. |
| `Seating.cs` | ShotStudio's seat contact (hips onto the measured seat top, two-bone leg IK keeps the feet planted), also used for the arm IK. |
| `ImportRules.cs` | Normal/linear texture import, Rocketbox FBX as Humanoid. |
| `Probe.cs` | Capability probe (DX12, DXR, timings). |

**Path tracing with motion blur.** For each output frame, `Film.cs` calls `HDRenderPipeline.BeginRecording` /
`PrepareNewSubFrame` and renders `spp` sub-frames. Between sub-frames the actors and the camera advance across a
180° shutter, so the accumulated frame has true motion blur. Depth of field is the path tracer's own thin lens, from
the physical camera (focal length, f-stop, focus distance). Intel Open Image Denoise (`com.unity.rendering.denoising`,
runs on the CPU) cleans the last sub-frame. The path tracer runs at 1920×816, so no pixels are spent on letterbox
bars.

**Light.** One directional sun at 16° elevation (38 000 lux, 3500 K, 0.8° disc for soft shadows) comes in through
the window. The sky is the Poly Haven HDRI `ehingen_hillside` with its sun clamped out (`fetch_assets.py` writes a
`_nosun` copy), so it adds only sky fill and the window view, never a second sun. Bounce light, soft shadows, glossy
floor reflections, the oil lamp and the warm hallway practical all come out of the path tracer. The look: ACES,
fixed EV per shot, light bloom, vignette, a warm/cool split-tone and a touch of grain.

**Acting fixes at render time.** These are all measured, and the actors stay where the motions put them:
- **Seat contact (horizontal).** Humanoid root motion follows the centre of mass. That sits ~0.3 m in front of the
  pelvis when seated, so a clip that sits exactly on its seat in the motion data (6-7 cm) lands short of the chair in
  Unity. While the character sits down, the body is eased so the pelvis is over the back of the seat. The correction
  is removed before the next root-motion step, so it doesn't accumulate.
- **Seat contact (vertical).** ShotStudio's correction puts the hips onto the measured seat top.
- **Chess move.** Arm IK with a forward lean picks up `piece_pawn_white_04` and moves it two squares (e2-e4),
  palm-down. The fingertip pinch point is within 0-3 cm of the top of the piece during the carry. The table is 0.82 m
  wide and the chairs are tucked in, so the board is within arm's reach.
- **Suitcase.** It is held at the palm and hangs plumb. A "carry" pose straightens the arm, because Kimodo lifts the
  forearm whenever "carrying" is in the prompt. The case is set down at the end of the bend and stays on the floor.
- **Head level.** After Humanoid retargeting the Rocketbox rigs come out with the head pitched ~18° up, so "looks
  down at the table" read as looking at the ceiling. Neck and head are tipped back down.
- **Bone edits must be skinned.** `SkinnedMeshRenderer.forceMatrixRecalculationPerRender` is needed. Without it,
  every post-animation bone edit (IK, seats) is silently missing from batch-mode renders. DemoStudio already sets
  it.
- **Skin.** Plain HDRP Lit. The SSS skin diffusion profile rendered orange under the path tracer.

### Motions: `gen_motions.py`

Blocking is in `layout.json`, shared with the renderer. There are two chains, each with `continue_from`:
- **Father (7 clips).** Window idle (11.5 s), turn around, gesture, step-and-sit (with `seat`), three seated clips
  (the middle one reaches forward).
- **Daughter (7 clips).** Walk in on a root path, put the bag down, wait, walk to the chair on a root path, turn and
  sit (with `seat`), two seated clips. The first walk prompt was regenerated once, because the arm was held out
  sideways.

All 14 passed the automatic checks. Seat checks: hips within 1.6-4.3 cm of the target height, feet drift 0.1-3 cm.
Generation took 20 s to 17 min per clip: the machine was in low-RAM mode and motiond reloaded its text encoder.

### Picture and sound: `assemble.py`

- **Picture.** Per-shot H.264, letterboxed to 2.39:1 in 1920×1080, light grain, a fade in and out.
- **Cards.** Title card ("YOUR MOVE") and end card set with PIL.
- **Music.** Satie's Gymnopédie No. 1.
- **Sound effects.** Room tone, birds through the window, the clock, footsteps, the suitcase thud and the chess
  click. All are placed from `events.json`, the story times the motions produced. The mix is loudness-normalised to
  -18 LUFS.

## Assets and licences

Nothing third-party is committed. `unity/FidelityStudio/fetch_assets.py` + `fidelity_assets.json` and
`demo/fidelity/fetch_audio.py` + `audio_assets.json` download everything into gitignored folders.

**Characters: Microsoft Rocketbox avatar library, MIT licence**
(https://github.com/microsoft/Microsoft-Rocketbox, licence: https://github.com/microsoft/Microsoft-Rocketbox/blob/master/LICENSE).
- `Male_Adult_03` plays the father and `Female_Adult_09` plays the daughter. Both are the `_facial` FBX variants
  (with face blendshapes), with 2K colour, normal and specular textures.
- Downloaded file by file from raw.githubusercontent.com. The full repo is 4 GB.

**Set: Poly Haven, CC0** (https://polyhaven.com/license). Each asset page is `https://polyhaven.com/a/<id>`.
- **Models (glTF):** `chess_set` (4K), `round_wooden_table_01`, `dining_chair_02`, `ArmChair_01`, `Sofa_01`,
  `vintage_cabinet_01`, `book_encyclopedia_set_01`, `potted_plant_01`, `potted_plant_02`, `ceramic_vase_01`,
  `brass_vase_01`, `hanging_picture_frame_01`, `hanging_picture_frame_02`, `standing_picture_frame_01`,
  `mantel_clock_01`, `vintage_grandfather_clock_01`, `tea_set_01`, `side_table_01`, `vintage_suitcase`,
  `ornate_mirror_01`, `vintage_oil_lamp`.
- **Textures:** `rectangular_parquet` (floor), `plastered_wall_04` (walls, ceiling), `floral_jacquard` (rug),
  `dark_wood` (sill, door).
- **HDRI:** `ehingen_hillside` (4K .hdr; the film uses a derived sky-only 2K copy).

**Music and sound effects: Freesound, CC0.** The files are Freesound's public HQ previews, so no login is needed.

| Use | Title | Author | Page |
|---|---|---|---|
| Music | Satie - Gymnopédie n°1 | Sterio18 | https://freesound.org/people/Sterio18/sounds/472903 |
| Clock | antique clock tick.wav | keweldog | https://freesound.org/people/keweldog/sounds/223130 |
| Footsteps | Walking On A Wooden Floor | ralph.whitehead | https://freesound.org/people/ralph.whitehead/sounds/331447 |
| Suitcase | putting down suitcase.wav | unconsidered | https://freesound.org/people/unconsidered/sounds/144458 |
| Chess | Chess Pieces hitting wooden board.wav | XfiXy8 | https://freesound.org/people/XfiXy8/sounds/467282 |
| Birds | Sussex Woodland & Meadow Bird Sounds, Evening | Vonora | https://freesound.org/people/Vonora/sounds/269559 |
| Room tone | Room Tone Apartment Small Bachelor | leonelmail | https://freesound.org/people/leonelmail/sounds/329568 |

The composition (Satie, 1888) is in the public domain, and the recording is CC0 per its Freesound page. Licences were
read from the Openverse API, which mirrors Freesound's metadata. Check the pages before any commercial use.

**Other.**
- Title cards use Georgia and Segoe UI Light (Windows system fonts), rendered into images only.
- Unity HDRP and the denoising package ship with the editor.

Rocketbox and Poly Haven allow commercial use. As with every Promptimate output, the motion model's own licence
applies (see `docs/07-licensing-risks.md`).

## Render settings and times

| Setting | Value |
|---|---|
| Resolution | 1920×816 rendered (2.39:1), letterboxed into 1920×1080 |
| Frame rate, length | 24 fps; 835 frames = 34.8 s of story, 42.3 s with the title and end cards |
| Path tracer | 80 samples per frame, max depth 6, max intensity clamp 6, sky importance sampling |
| Motion blur | 180° shutter, accumulated across the 80 sub-frames (actors and camera move between them) |
| Depth of field | Physical camera, 36×24 mm sensor, 24-85 mm lenses at f/2-f/5.6, keyed focus with rack focus in the door shot |
| Denoiser | Intel Open Image Denoise (CPU), synchronous, AOVs on |
| Hardware | RX 6600 XT (8 GB, DXR on DX12), Ryzen 5 3600, 16 GB, shared with other agents all night |
| Time per frame | median 7.0 s, mean 6.8 s, max 10.9 s (from the per-chunk `report_*.json`) |
| Wall time, final | 2 h 04 min for 756 frames in 14 chunks of 55 (about 65 s of Unity start-up per chunk), plus 79 frames from an earlier run that hit the GPU memory leak |
| Previews | Raster blocking preview at 960×408 every 3rd frame: about 0.5 s/frame. Path-traced stills at 1280×544, 48 spp: about 2.5 s each |
| Encode | H.264 CRF 14 master (`your_move.mp4`, 125 MB) and CRF 21 web copy (`your_move_web.mp4`, 18 MB) |

The renderer has to restart in chunks: on this HDRP 17.0.3 / AMD driver combination, D3D12 non-local (shared)
memory grows every frame until the device hangs (`887a0007`) after about 80 frames. `--chunk 55` stays well under
that, and the final render had no crashes.

## What would push it further

- **Faces.** The biggest gap. Rocketbox's facial blendshapes are only used for blinks. Lip-sync, gaze and brow
  animation (FACS blendshapes are in the `_facial` FBX) would let the camera come close. Kimodo has no face channel.
- **Hands.** Finger poses come from the importer's tables, plus IK for the chess pinch. A grasp solver (finger
  contacts on the suitcase handle and the pawn) would sell close-ups; the pinch currently reads from a distance only.
- **Cloth and hair.** Jackets are skinned, not simulated, so a cloth pass or Alembic caches would help, and the
  hair cards are alpha-tested. Unity's Digital Human / Enemies hair system would be the next step.
- **Characters.** Rocketbox is circa-2015 game quality (about 10k triangles, 2K textures). MetaHuman-class or scanned
  CC0 humans would raise the ceiling, but none we found are free and loginless and Humanoid-ready.
- **Samples.** 80 spp + OIDN is clean at 1080p. 256 spp with the temporal OIDN mode would remove the last crawl in
  the darkest corners at about 3× the time. Volumetric fog in the path tracer (visible sun shafts) is supported by
  HDRP but we didn't have time to test it.
- **The memory leak.** Finding the per-frame non-local allocation (likely the ray-tracing acceleration structure for
  skinned meshes, or readback staging) would remove the chunk restarts (about 15 min per film).
- **Motion.** Kimodo lifts the forearm for "carrying" and keeps reaches small, so props currently rely on
  render-time IK. A prop-aware or hand-contact constraint in generation would remove those fixes.
