# Agent handoff

You're on the **GPU host machine** (AMD RX 6600 XT, 8 GB VRAM, RDNA2, gfx1032, Windows). There is no CUDA, so use Vulkan.

## Current state (2026-11-14)
- The product is now called **Promptimate** (it was the "Text-to-Anim" working title). The MVP is built and works end
  to end. See `README.md` for the user-facing overview and `docs/spike-results.md` for measurements.
- Code map:
  - `unity/com.promptimate.unity/`: Unity package (`Promptimate.Editor` asmdef/namespace). Contains the `.kimodo`
    ScriptedImporter, `KimodoValidator`, and the headless entry point `Promptimate.Editor.BatchValidate.Run`.
  - `unity/PromptimateSandbox/`: default `UNITY_PROJECT`. Clips are dropped into `Assets/Promptimate/Generated/`
    (gitignored). `unity/TextToAnimSandbox/` is the gitignored pre-rename copy, kept only because it may be open locally.
  - `unity/DemoStudio/`: demo rendering scripts. Characters (Mixamo/Kenney) and clips are local only and never committed.
  - `mcp_server/`: FastMCP server, id **`kimodo-motion`**. Don't rename the id or the tools, because they appear in
    published videos and on the website. `unity_validate.py` runs the headless checks.
  - `setup.ps1`, `scripts/`: installer, model download, and engine packaging (`dist/` zip goes to GitHub Releases).
  - `demo/`: launch-film tooling. `demo/video*` are HyperFrames projects that other people edit, so leave them alone.
- Log markers `TTA_REPORT`, `TTA_SELFTEST`, `TTA_SUMMARY`, `TTA_CHAR*` and the env var `TTA_TEMP` keep their old prefix
  on purpose (tooling greps for them).
- After touching the importer, run `.venv\Scripts\python mcp_server\unity_validate.py --self-test <clips>`. All clips
  must pass, the `Correct` variant must pass, and the 4 broken variants must fail.

## Ground rules
- Keep everything on D: (C: is nearly full). Set `TEMP/TMP=D:\tmp`, `PIP_CACHE_DIR=D:\pip-cache` and
  `npm_config_cache=D:\npm-cache`.
- Keep model weights **out of git**. They are multi-GB downloads (Hugging Face) under separate licenses and live under
  `models/` (gitignored). The same applies to Mixamo/Kenney assets, renders, music, `.venv`, `third_party/` and `engine/`.
- Don't assume commercial use is allowed for any checkpoint. See `docs/07-licensing-risks.md` and `THIRD_PARTY_NOTICES.md`.
- Never use the SMPL-X Kimodo checkpoint for anything beyond local experiments, because it is research-only.
- Claude integration must go through a **local MCP server** that the user connects to their own Claude client.
  Never implement Claude subscription login or OAuth inside the plugin. See `docs/06-claude-integration.md`.
- Research docs (`docs/01..07`) are a snapshot. Re-check upstream kimodo.cpp (young and changing fast) before
  relying on flags or features. Positional constraints are still unsupported upstream.
