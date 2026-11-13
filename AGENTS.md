# Agent handoff

You're picking this up on the **GPU host machine**. The research was done on a different machine that has no GPU.

## Context
- The goal is a Unity editor plugin for local text-to-animation. See `README.md`.
- Research is in `docs/`. Treat it as a snapshot from 2026-11-14. Re-check the upstream repos (kimodo.cpp in
  particular is young and changing fast) before relying on specifics such as flags, file names and supported features.
- Target dev GPU: **AMD RX 6600 XT, 8 GB VRAM** (RDNA2, gfx1032). There is no CUDA, so use Vulkan.

## What to do first
Follow `docs/05-spike-plan.md` in order. Steps 0–2 are the riskiest (does kimodo.cpp run on Vulkan/AMD, how fast is
it, and can it fit in 8 GB). Record measured results in `docs/spike-results.md` before writing any Unity code.

## Ground rules
- Keep model weights **out of git**. They are multi-GB downloads (Hugging Face) under separate licenses. Put them under
  `models/` (gitignored).
- Don't assume commercial use is allowed for any checkpoint. See `docs/07-licensing-risks.md`.
- Never use the SMPL-X Kimodo checkpoint for anything beyond local experiments, because it is research-only.
- Claude integration must go through a **local MCP server** that the user connects to their own Claude client.
  Never implement Claude subscription login or OAuth inside the plugin. See `docs/06-claude-integration.md`.
