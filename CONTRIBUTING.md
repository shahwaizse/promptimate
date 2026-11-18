# Contributing

## Layout

| Path | What |
|---|---|
| `unity/com.promptimate.unity/` | The Unity package: the `.kimodo` importer, validator, Foot IK and grounding |
| `mcp_server/` | The MCP server `kimodo-motion` (don't rename it or its tools). `motiond.py` is the one GPU daemon every client shares. `local_config.py` holds the machine settings |
| `scripts/` | Setup, model download, engine packaging, `shorts.py` (the shorts factory command line) and `heavy_lock.py` |
| `bench/` | Motion benchmarks and A/B tooling (see `bench/README.md`), plus the shorts judging kit (`shorts_judge_*.py`) |
| `roblox/` | The Roblox bridge (the Luau player, Studio tools) and `roblox/headless/` (offscreen director, camera checks, renderer, our own procedural assets) |
| `demo/episodes/` | The shorts factory: stories, compiler, producer and writer prompt. See [its README](demo/episodes/README.md) |
| `demo/video*` | Launch-film projects (HyperFrames) edited by other people: leave them alone |
| `tests/` | Fast checks: `.venv\Scripts\python -m unittest discover tests` |

## Ground rules

- **Never commit:**
  - model weights (`models/`, `*.gguf`, `*.npz`);
  - third-party characters or assets (Mixamo, Kenney, Roblox catalog meshes and textures);
  - renders and audio;
  - `.venv`, `engine/` or `third_party/`;
  - Roblox place files;
  - `local.env`.
  The `.gitignore` covers them; check `git status` before committing.
- **Keep machine paths out of code.** Read them from `mcp_server/local_config.py` (environment or `local.env`) and add
  any new setting to `local.env.example`.
- **GPU work goes through `motiond`.** Don't start private model workers next to it (two copies overflow 8 GB). Wrap
  long renders and recordings in `scripts/heavy_lock.py`, because the machine is shared.
- **Licensing:** check `THIRD_PARTY_NOTICES.md` and ask the maintainer before adding a model, dataset or asset source. The SMPL-X Kimodo
  checkpoint is for local experiments only.
- **Claude integration stays a local MCP server** that the user connects to their own client. No logins inside the
  product.

## Changing things

- **Measure before claiming better.** For motion, use `bench/run_bench.py --tier smoke` and `bench/compare.py`. For
  shorts, run a blind A/B with `scripts/shorts.py judge-prep`/`judge-tally` against the online references, not
  against our previous episode. Differences under about 0.7 points are judge noise.
- After touching the Unity importer, run `.venv\Scripts\python mcp_server\unity_validate.py --self-test <clips>`.
- Before a pull request:
  - run `scripts\shorts.py test` and `scripts\shorts.py doctor`;
  - if you touched the shorts pipeline, produce one episode end to end (`scripts\shorts.py produce lie_shrink`) and
    look at the result.
