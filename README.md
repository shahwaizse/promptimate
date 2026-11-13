# Unity Text-to-Anim (working title)

Local, free, GPU-powered **text-to-animation for Unity**. It is the Unity counterpart of Unreal Engine 5.9's
experimental *AnimGenOffline* plugin.

- Generates humanoid `AnimationClip`s from text prompts, plus optional constraints (keyframe poses, root paths,
  hand/foot targets).
- Runs fully on the user's machine via [kimodo.cpp](https://github.com/localai-org/kimodo.cpp), a GGML port of
  NVIDIA Kimodo. It uses Vulkan, so it works on AMD, NVIDIA and Intel cards, with no Python, cloud or subscription.
- Exposes its tools over a local **MCP server**, so a user's own Claude Code or Claude Desktop can direct
  multi-shot sequences that fit the scene. Claude plans the shots and Kimodo generates the motion.

**Status:** research done (Nov 2026). Nothing is built yet. The next step is the spike in
[`docs/05-spike-plan.md`](docs/05-spike-plan.md), run on the GPU host (RX 6600 XT, 8 GB).

## Docs

| File | Contents |
|---|---|
| [`docs/01-landscape.md`](docs/01-landscape.md) | What prompted this, existing UE and Unity tools, where the gap is |
| [`docs/02-model.md`](docs/02-model.md) | Kimodo and kimodo.cpp: models, sizes, constraints, outputs |
| [`docs/03-hardware.md`](docs/03-hardware.md) | VRAM budget, fitting on 8 GB, AMD/Vulkan notes |
| [`docs/04-architecture.md`](docs/04-architecture.md) | Proposed plugin architecture |
| [`docs/06-claude-integration.md`](docs/06-claude-integration.md) | Why not "use a Claude sub" directly, and the MCP design |
| [`docs/07-licensing-risks.md`](docs/07-licensing-risks.md) | Model licenses, distribution, open questions |
| [`docs/05-spike-plan.md`](docs/05-spike-plan.md) | **Start here:** the first concrete tasks |
| [`AGENTS.md`](AGENTS.md) | Handoff notes for the agent picking this up |
