# Promptimate MCP server (`kimodo-motion`)

Local text-to-motion for a Claude client. Claude plans the shots and Kimodo (kimodo.cpp, Vulkan) generates the motion.

## Setup
Run `.\setup.ps1` from the repo root. It installs the prebuilt engine into `engine/`, creates `.venv`, and downloads
the weights into `models/` (`models/kimodo-soma-rp-v1.1-f32.gguf`, `Llama-3-Kimodo-Q4_K_M.gguf` or `-Q8_0`,
`tokenizer.gguf`). A local source build of kimodo.cpp in `third_party/kimodo.cpp/build/release` is also picked up, or
point `KIMODO_ENGINE_DIR` at any folder that contains `kmd-generate.exe`.

## Connect
- **Claude Code:** `claude mcp add kimodo-motion -e UNITY_PROJECT=C:\path\to\YourUnityProject -- <repo>\.venv\Scripts\python.exe <repo>\mcp_server\server.py`,
  or copy `.mcp.json.example` to `.mcp.json`, fill in the paths, start `claude` in the repo and approve the server.
- **Claude Desktop:** add the same `command`/`args`/`env` block to `claude_desktop_config.json`.

## Tools
| Tool | What it does |
|---|---|
| `generate_motion(segments[{prompt, seconds}], seed, steps=30, transition_frames=5, name?)` | Generates the motion and returns stats plus a preview image. Writes GLB, BVH and raw `.f32` to `output/<name>/`, and drops `<name>.kimodo` into `$UNITY_PROJECT/Assets/Promptimate/Generated/`. |
| `validate_in_unity(names?, self_test)` | Headless Unity bake and verify (runs automatically after each generation unless `unity_check=false`) |
| `list_motions`, `get_motion_preview(name)` | Browse earlier results |
| `worker_status(warm_up)` | Load the GPU worker ahead of time (about 1 min cold) |

## Automatic verification
Every `generate_motion` result includes:
- `checks`: instant Python checks (facing, feet, toes, travel vs facing).
- `unity_validation`: a headless Unity bake, about 10 s. It compares the clip against reference positions from the
  Python forward kinematics, round-trips it on the SOMA avatar, retargets it onto a differently proportioned rig, and
  checks facing, left/right and feet.

After touching the importer, run `.venv\Scripts\python mcp_server\unity_validate.py --self-test`. The deliberately
broken conversions (negative controls) must fail and the correct one must pass.

Env: `KIMODO_TEXT_QUANT` (`q4_k_m` default, `q8_0`), `UNITY_PROJECT`, `UNITY_EXE`, `KIMODO_IDLE_UNLOAD_S` (600),
`TTA_TEMP` (default `<repo>/.cache/tmp`), `KIMODO_ENGINE_DIR`, and any kimodo env var (`KIMODO_TEXT_LAYER_CHUNK`, ...).
Timing on an RX 6600 XT: about 20 s per 5 s clip at 30 steps once warm.
