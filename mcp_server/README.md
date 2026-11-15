# Promptimate MCP server (`kimodo-motion`)

Local text-to-motion for a Claude client. Claude plans the shots and Kimodo (kimodo.cpp, Vulkan) generates the motion.

## Setup
Run `.\setup.ps1` from the repo root. It installs the prebuilt engine into `engine/`, creates `.venv`, and downloads
the weights into `models/` (`models/kimodo-soma-rp-v1.1-f32.gguf`, `Llama-3-Kimodo-Q4_K_M.gguf` or `-Q8_0`,
`tokenizer.gguf`). A local source build of kimodo.cpp with `scripts/kimodo-promptimate.patch` applied, in
`third_party/kimodo.cpp/build/promptimate`, is also picked up (see `scripts/package_engine.py` for the build steps), or
point `KIMODO_ENGINE_DIR` at any folder that contains `kmd-generate.exe`.

## Connect
- **Claude Code:** `claude mcp add kimodo-motion -e UNITY_PROJECT=C:\path\to\YourUnityProject -- <repo>\.venv\Scripts\python.exe <repo>\mcp_server\server.py`,
  or copy `.mcp.json.example` to `.mcp.json`, fill in the paths, start `claude` in the repo and approve the server.
- **Claude Desktop:** add the same `command`/`args`/`env` block to `claude_desktop_config.json`.

## Tools
| Tool | What it does |
|---|---|
| `generate_motion(segments[{prompt, seconds}], seed, steps=30, takes=3, clean=true, loop=false, in_place=false, root_path?, auto_stop=true, text_cfg?, transition_frames=5, name?, unity_check="background")` | Generates the motion and returns stats, checks, a preview sheet and (for several takes) a takes sheet. Writes raw `.f32` (plus the engine's `foot_contacts.f32`) to `output/<name>/take<k>/` and the cleaned result to `output/<name>/`, GLB and BVH in the background, and drops `<name>.kimodo` into `$UNITY_PROJECT/Assets/Promptimate/Generated/`. |
| `use_take(name, take)` | Switch a multi-take result to another take |
| `validate_in_unity(names?, self_test)` | Headless Unity bake and verify (also runs in the background after each generation unless `unity_check="off"`) |
| `list_motions`, `get_motion_preview(name)` | Browse earlier results |
| `worker_status(warm_up)` | Load the GPU worker ahead of time (about 1 min cold) |

## Automatic verification
Every `generate_motion` result includes:
- `checks`: instant Python checks (facing, feet, toes, travel vs facing).
- `unity_validation`: a headless Unity bake, about 10 s, run in the background (read it with `get_motion_preview`). It compares the clip against reference positions from the
  Python forward kinematics, round-trips it on the SOMA avatar, retargets it onto a differently proportioned rig, and
  checks facing, left/right and feet.

After touching the importer, run `.venv\Scripts\python mcp_server\unity_validate.py --self-test`. The deliberately
broken conversions (negative controls) must fail and the correct one must pass.

Env: `KIMODO_TEXT_QUANT` (`q4_k_m` default, `q8_0`), `UNITY_PROJECT`, `UNITY_EXE`, `KIMODO_IDLE_UNLOAD_S` (600),
`TTA_TEMP` (default `<repo>/.cache/tmp`), `KIMODO_ENGINE_DIR`, and any kimodo env var (`KIMODO_TEXT_LAYER_CHUNK`, ...).
Defaults can also be set with `KIMODO_STEPS` (30), `KIMODO_TEXT_CFG` (2.0) and `KIMODO_TAKES` (3).
Timing on an RX 6600 XT: about 2.5 s per 5 s clip at 30 steps once warm; a default 3-take call takes about 10 s.

## Generation pipeline
1. Each take: one engine pass. If the text says the character stops (a later segment with "stops", "stands still",
   "in place", or "X then stops") or `loop=true`, a second pass with the same seed adds constraints: the hips are held
   where the first pass reached, and/or the last frame is pinned to the first frame's pose.
2. The take with the best automatic score (check failures, glitches, foot skating, floating, jerk) is chosen.
3. Post-processing (`postprocess.py`): foot contacts (heuristic + the engine's predicted contacts) are locked with
   two-bone leg IK, the floor offset is removed, loops get a seamless seam, `in_place` removes travel.
4. Outputs, the preview sheet (`render.py`), then GLB/BVH export and headless Unity validation in the background.

Benchmark and quality metrics: see `bench/README.md` (`run_bench.py` for engine/config scans, `server_eval.py` for
the full server pipeline).
