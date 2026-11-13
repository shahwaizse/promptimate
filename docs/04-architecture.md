# 04: Proposed architecture

```
Unity Editor (C#)                          Worker process (native)
┌────────────────────────────┐   pipe /    ┌────────────────────────────┐
│ Editor window / Timeline   │   stdio     │ kimodo.cpp (ggml-vulkan)   │
│ Constraint authoring       │ ──────────▶ │ text encoder + denoiser    │
│ Retarget → Humanoid clip   │ ◀────────── │ returns joint rots + root  │
│ MCP server (localhost)     │             └────────────────────────────┘
└────────────────────────────┘
        ▲
        │ MCP
  User's own Claude Code / Claude Desktop
```

## Components
1. **Native worker.** Build kimodo.cpp as a CLI or shared library for Win, Linux and macOS (Vulkan; MoltenVK on Mac,
   untested). Run it **out of process** so crashes or VRAM out-of-memory errors don't kill the editor. Text To Anim does
   the same with a hidden backend process and a private pipe. Keep the models loaded between requests.
2. **Model manager.** Downloads from HF on first run, checks SHA-256, shows the license-acceptance screen, picks the
   quant or streaming mode by VRAM (see 03-hardware.md), and stores models outside the Unity project.
3. **Retargeting.** Map SOMA 77-joint data to Unity Humanoid bones, then use `HumanPoseHandler` to get muscle curves
   and root curves, and produce a Humanoid `AnimationClip`. This plays on any Mecanim humanoid (Mixamo, VRM, Synty…).
   TexMotion (MIT) does exactly this and is a good reference.
4. **Editor window.** Prompt, duration, seed, loop / in-place / root-motion options, preview on a selected character,
   and save to `.anim`.
5. **Timeline track (differentiator).** Clips with text segments; pose keyframes captured from a posed character in
   the scene; a root path drawn as a spline; hand and foot targets taken from scene transforms. All of these become
   Kimodo constraints, and the result is baked into the track.
6. **Post-processing.** Foot-lock using the `foot_contacts` output, loop detection and blending, FBX export (via the
   Unity FBX Exporter package).
7. **MCP server.** See 06-claude-integration.md.

## Package layout (proposal)
`com.<org>.text-to-anim`: `Editor/` (UI, Timeline, MCP), `Runtime/` (minimal; clips are plain assets),
`Native~/` (worker binaries per platform). Editor-only at first; runtime generation is out of scope for v1.
