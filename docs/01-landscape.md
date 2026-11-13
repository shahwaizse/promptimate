# 01: Landscape (as of 2026-11-14)

## What prompted this
A tweet from @smart_poly (2026-11-13, https://x.com/smart_poly/status/2121291142104748093) showed Unreal Engine
5.9 generating character animation from text with AI, locally on the GPU, with no subscription or cloud.

That plugin is **AnimGenOffline** (the name may change), which ships with UE 5.9 Preview 1. It is integrated into
Sequencer, where you guide the animation at a high level and AI generates the frames. The backend is **NVIDIA Kimodo**,
with weights downloaded from Hugging Face. It is probably Windows-only for now and runs fastest on RTX 30-series or
newer. Source: developer post at https://x.com/JohnnyB_222/status/2119878294749225179. There are no official Epic docs
for it yet.

## Unreal (for reference)
| Tool | Local | Notes |
|---|---|---|
| AnimGenOffline (UE 5.9, built-in) | Yes | Sequencer integration, Kimodo backend |
| [Text To Anim](https://texttoanim.altercode.dev/) ([Fab](https://www.fab.com/listings/a752158e-6e40-4221-8600-8ce4683e65a0)) | Yes | UE 5.6–5.8, Windows + NVIDIA RTX only. Uses kimodo.cpp GGUF in a hidden `UnrealEditor-Cmd` backend process over a private pipe. ~9.3 GB model download. Supports multi-prompt transitions, heading and floor-point direction per segment, loop detection, and IK Retargeter output to Manny, MetaHuman and Mixamo. **About 3–4 s per 5 s clip on an RTX 4080.** |
| [RIGIPO](https://www.fab.com/listings/5d79abf2-ac69-4372-be7d-644c0dd97da5) | Yes | Windows, NVIDIA, ~15 GB disk, UE 5.6–5.8 |

## Unity
| Tool | Local | Notes |
|---|---|---|
| Unity AI Animate (`com.unity.ai.generators`) | **No, cloud** | Text-to-motion and video-to-motion to Humanoid clips. Backend service with "quoting", i.e. it is paid. [README mirror](https://github.com/needle-mirror/com.unity.ai.generators/blob/master/Modules/Unity.AI.Animate/README.md) |
| [Avatar SDK Move](https://avatarsdk.com/move-unity-plugin/) | **No, cloud** | About $1 per 5 s clip, Unity 6+ |
| [PromptMotion](https://assetstore.unity.com/packages/tools/generative-ai/promptmotion-ai-animation-generator-library-137075) | Probably cloud | A review complains about the server being busy or unavailable |
| [TexMotion](https://github.com/k0ta0uchi/TexMotion) | Yes | MIT. Uses kimodo.cpp (`kimodo.dll` + ggml-vulkan) and outputs a Humanoid AnimationClip via `HumanPoseHandler`. **VRChat-focused** (requires VRCSDK). 0 stars, no releases. Also does video-to-pose (MediaPipe/WHAM). Useful as reference code. |

## The gap
There is no **general-purpose, polished, local** Unity tool that has:
- Timeline integration with constraint authoring (the equivalent of Sequencer in AnimGenOffline),
- AMD, NVIDIA and Intel support (all the UE plugins are NVIDIA-only),
- agent-directed multi-shot generation through MCP (none of these tools do this).

## Why the cloud tools charge separately
They run **motion diffusion models**, not LLMs. The only language model involved is the text encoder that embeds the
prompt. Their price pays for GPU time. An LLM like Claude can't directly generate good motion: keyframes written as
JSON come out stiff and physically wrong. That is why the design here makes Claude the *director*, not the animator.
