# Spike results (GPU host, 2026-11-14)

> **Renamed (2026-11-14):** the product is now **Promptimate**. Paths below are as measured at the time: `unity/com.local.text-to-anim` is now `unity/com.promptimate.unity` (namespace `Promptimate.Editor`), `unity/TextToAnimSandbox` is now `unity/PromptimateSandbox`, and the drop folder `Assets/TextToAnim/Generated` is now `Assets/Promptimate/Generated`. Headless batch mode does work now (see `mcp_server/unity_validate.py`).

## Step 0: Environment
| | |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| GPU | AMD Radeon RX 6600 XT, 8 GB (RDNA2), AMD proprietary driver 2.0.353, Vulkan 1.4.315. ggml reports `fp16: 1, int dot: 1, matrix cores: none` |
| RAM | 16 GB |
| Disk | **C: SSD, 9 GB free; must not be used.** D: 1 TB **7200 rpm HDD** (Seagate ST1000DM003). Everything (repo, models, Vulkan SDK, HF/pip caches, temp files) lives on D:. |
| Toolchain | VS 2022 Build Tools (MSVC, already on C:), CMake, Ninja, Vulkan SDK 1.4.363.1 at `D:\VulkanSDK` (its installer needs admin), Python 3.12 venv at `D:\unity-text-to-anim\.venv` |
| Unity | 6000.0.34f1 and 6000.5.10f1 in `D:\Unity\Editors`. Batch mode fails on licensing, so test in the editor. |

D: redirects used: `HF_HOME=D:\hf-cache`, `PIP_CACHE_DIR=D:\pip-cache`, `TEMP/TMP=D:\tmp`.

## Step 1: kimodo.cpp on Vulkan/AMD: **PASS**
- kimodo.cpp at `75ed52d` (2026-10-29), ggml pinned submodule `8c63e70`. Built with Ninja + MSVC Release and
  `KIMODO_ENABLE_VULKAN=ON` with no source changes. The recursive submodule clone of ggml hung, so shallow-fetch the
  pinned commit instead.
- Weights: `kimodo-soma-rp-v1.1-f32.gguf` (1.13 GB), `Llama-3-Kimodo-Q4_K_M.gguf` (5.06 GB), `Llama-3-Kimodo-Q8_0.gguf`, `tokenizer.gguf`.
- Upstream drift vs the research docs: the SOMA model outputs its **30-joint control skeleton** (no 77-joint expansion).
  There is still **no general constraint input**. `kmd-generate --server` is a ready-made long-lived stdin/stdout worker.

### Timings: prompt "a person walks forward and waves", 150 frames (5 s), seed 42
| Config | Text upload/load | Text encode | Motion weight upload | Diffusion | Notes |
|---|---|---|---|---|---|
| Q4_K_M, chunk 8 (streamed), cold disk, 50 steps | ~45 s (HDD-bound, ~140 MB/s) | 47.8 s total incl. upload | 7.0 s | 29.8 s (≈580 ms/step) | one-shot CLI, wall 86 s |
| Q4_K_M, chunk 32 (resident), warm OS cache, 50 steps | (load) | **0.89 s** | 7.0 s | 29.2 s | one-shot CLI, wall 74 s |
| Q4_K_M resident, MCP worker, 30 steps | 35.7 s resident load (once) | 2.5 s first, then fast | 7.1 s (once) | ≈17 s | **MCP end to end: 63 s cold, 20.7 s warm (5 s clip), 20.1 s warm (6 s, two segments)** |

- **Diffusion dominates** at ≈580 ms/step for a 150-frame clip: body transformer ≈520 ms and root transformer
  ≈48 ms per step. Upstream measures ≈45 ms/step on an RTX 5070 Ti, so this card is about 12× slower. It has no matrix
  cores and the motion denoiser is F32. This is the first thing to optimise (fewer steps, F16 denoiser, shader tuning).
- **Cold load is disk-bound** (HDD). The worker keeps the models resident, so this is paid once per session.
- VRAM: Windows' adapter counter showed only about 1.1–1.5 GB of dedicated delta. Per-process counters during worker
  load show a large *shared* (system-memory) allocation. **TODO:** confirm whether part of the encoder sits in shared
  memory. Nothing ran out of memory.

## Step 2: Quality
- Visual check by stick-figure contact sheet (`mcp_server/motion.py:render_preview`). The walk-and-wave prompt gives
  a clean stride cycle with the right arm raised and waving at 2.8–3.5 s, covering about 8.7 m in 5 s.
- The PyTorch/ROCm reference comparison was not done (Windows host; ROCm route skipped for the MVP).
- Multi-prompt works: "walks forward" then "stops and jumps up and down" gives a clear crouch and jump (hips reach 1.31 m)
  with a blended transition, but the root keeps drifting forward through the "stop", so prompt adherence is imperfect.
- Same prompt and seed give byte-identical output (deterministic).
- Constraints: still unsupported in kimodo.cpp, so the MVP is text plus multi-prompt segments only.

## MVP built
- `mcp_server/`: a FastMCP (mcp 1.x) stdio server with `generate_motion(segments[], seed, steps, transition_frames)`,
  `list_motions`, `get_motion_preview` and `worker_status`. It keeps one resident `kmd-generate --server` worker and
  returns stats and a preview PNG (so Claude can judge the result), plus GLB/BVH exports. It also drops a `.kimodo` file
  into the Unity project.
- `unity/com.local.text-to-anim`: a `ScriptedImporter` for `.kimodo` that builds a SOMA rest rig and a Humanoid
  Avatar, samples `HumanPoseHandler`, and outputs a Humanoid `AnimationClip` (muscles plus RootT/RootQ).
- `unity/TextToAnimSandbox`: a minimal Unity 6 project that references the package.
- Gotcha: on Windows, subprocesses started from an MCP stdio server must use `stdin=DEVNULL` or they hang.

## Step 3: Unity Humanoid clip: **PASS** (user-confirmed once, now verified automatically)
- User check in Unity 6000.0.34f1: imports without errors, faces and walks forward, feet planted, no flipped joints.
- **Automated validation** (`KimodoValidator.cs`) runs on every import and headless via
  `mcp_server/unity_validate.py` (separate `unity/ValidationProject`, about 10 s warm, 60 s cold). It runs three rigs:
  - A = source converted to Unity, checked against **independent Python FK positions** (`refPos` in the `.kimodo` file;
    the position handedness flip is unambiguous). Error is 0.01 mm.
  - B = baked clip replayed on the SOMA avatar. Hips-relative error is 0.2 mm mean and 4 mm max.
  - C = synthetic humanoid with different proportions and random bone axes (like Mixamo). Bone directions are within
    0.5–0.9° on average and facing within 1°.
  - Semantic checks: starts facing +Z, doesn't move opposite to its facing (unless the prompt says backward), toes
    point forward, left/right not mirrored, feet grounded and not below the floor.
- **Negative controls** (`validate_in_unity(self_test=true)` / `unity_validate.py --self-test`): unmirrored
  conversion, unconverted quaternions, 180° yaw and flipped root Z must all FAIL, and the correct conversion must PASS.
  All 5 behave as expected. Lesson learned: without the FK reference, unconverted quaternions passed, because walking is
  mostly rotation about the lateral axis.
- MCP gotchas: the stdio launcher gives a minimal environment, and Unity's Package Manager crashes without
  `PROGRAMDATA`/`ALLUSERSPROFILE`, so `unity_validate.py` fills them in. A machine-wide lock file stops several MCP
  server instances (one per Claude session) from generating on the 8 GB GPU at once. The worker unloads after 10 min idle.
