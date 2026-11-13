# 05: Spike plan (run on the GPU host)

The goal is to prove the riskiest parts before writing editor UI. Record numbers in `docs/spike-results.md`.

## Step 0: Environment
- Record the OS, GPU driver and Vulkan version (`vulkaninfo --summary`), and RAM.
- Make sure there is about 15 GB of free disk for models under `models/` (gitignored).

## Step 1: kimodo.cpp on Vulkan (AMD)
- Clone https://github.com/localai-org/kimodo.cpp and build with the Vulkan backend. Read its README,
  `docs/PROFILING.md` and `docs/QUANTIZATION.md` first.
- Download the SOMA motion GGUF (RP, latest available) and the text encoder: start with Q8_0 plus layer streaming,
  then try Q4_K_M.
- Generate a 5 s clip from a simple prompt ("a person walks forward and waves").
- **Measure** for each encoder config: peak VRAM, time to encode text, time to denoise, and total time.
- **Pass:** it runs on the 6600 XT without out-of-memory errors, and the motion looks right in whatever
  viewer or exporter kimodo.cpp ships.

## Step 2: Quality check (optional, recommended)
- If ROCm is workable (`HSA_OVERRIDE_GFX_VERSION=10.3.0`), run the official PyTorch Kimodo with
  `TEXT_ENCODER_DEVICE=cpu` on the same prompt and seed, and compare it to the kimodo.cpp output. Do the same for Q8
  against Q4_K_M.
- Find out whether kimodo.cpp accepts constraints yet (root path, keyframes). If not, note what's missing.

## Step 3: Unity Humanoid clip
- In a blank Unity 6 project, write an editor script that loads the output (NPZ or whatever kimodo.cpp writes), maps
  SOMA joints to Humanoid bones, and bakes a Humanoid `AnimationClip` via `HumanPoseHandler`.
- Use TexMotion's retargeting code (MIT) as reference: https://github.com/k0ta0uchi/TexMotion
- **Pass:** the clip plays correctly on a Mixamo character (feet planted, no flipped joints, correct facing).

## Step 4: Out-of-process worker
- Wrap kimodo.cpp in a long-lived worker process that keeps models loaded, and call it from the Unity editor over
  stdio or a named pipe.

## Step 5: MCP tool
- Expose `generate_motion(segments[], constraints?)` and `list_humanoids()` via a local MCP server. Drive it from
  Claude Code and generate a 2–3 segment sequence on a scene character.

When Steps 1–3 pass, the project is viable and the remaining work is product and UI. If Step 1 fails on Vulkan/AMD,
fall back to a Python sidecar using PyTorch + ROCm (Linux) or CPU, and reassess.
