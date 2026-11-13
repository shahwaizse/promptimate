# 02: Model: Kimodo and kimodo.cpp

## NVIDIA Kimodo
- Repo: https://github.com/nv-tlabs/kimodo. Code is Apache-2.0; checkpoints are licensed separately on HF.
- Released 2026-03-16. Latest models are v1.2 (2026-10-15). ~4.2k stars.
- A kinematic motion **diffusion** model that takes text plus sparse kinematic constraints and outputs 3D
  human or humanoid motion.
- Text encoding uses **LLM2Vec** on Llama-3-8B-Instruct (8B params).

### Checkpoints
| Model | Skeleton | Data | License |
|---|---|---|---|
| Kimodo-SOMA-RP-v1.2, -RP-ArdyRep-v1.2 | SOMA (77-joint `somaskel77`) | Bones Rigplay 1 (700 h, proprietary) | NVIDIA Open Model License |
| Kimodo-SOMA-RP-v1.1 / -SEED-v1.1 / v1 | SOMA | RP or BONES-SEED (288 h public) | NVIDIA Open Model License |
| Kimodo-G1-RP-v1 / -SEED-v1 | Unitree G1 robot | | NVIDIA Open Model License |
| Kimodo-SMPLX-RP-v1 | SMPL-X | | **NVIDIA R&D Model License (research only)** |

The README recommends the RP models. **Use SOMA RP** for this project.

### Constraints supported
- Full-body pose keyframes
- 2D root waypoints or paths on the ground plane
- End-effector (hands and feet) positions and rotations
- Multi-prompt sequences with transitions, and "constrained intervals" on the timeline

### Output (NPZ)
`posed_joints`, `global_rot_mats`, `local_rot_mats`, `foot_contacts`, `smooth_root_pos`, `root_positions`,
`global_root_heading`.

### VRAM (official PyTorch)
- About 17 GB fully on GPU, mostly for the text encoder.
- `TEXT_ENCODER_DEVICE=cpu` brings it to **under 3 GB**, at a modest speed cost.
- Tested on RTX 3090, 4090 and A100. No AMD mentioned.

## kimodo.cpp (what we'll actually use)
- Repo: https://github.com/localai-org/kimodo.cpp. Apache-2.0, ~1k stars, young project.
- GGML/GGUF port. Backends: **CPU and Vulkan** only (no CUDA, HIP or Metal listed).
- Text encoder GGUF: https://huggingface.co/LocalAI-io/Llama-3-Kimodo-GGML

| Variant | Size | Status |
|---|---|---|
| BF16 | 15.18 GB | reference |
| Q8_0 | 8.14 GB | recommended/default |
| Q6_K | 6.32 GB | experimental |
| Q5_K | 5.33 GB | experimental |
| Q4_K_M | 5.06 GB | preferred low-bit experiment |
| Q4_K | 4.39 GB | experimental |

  A shared `tokenizer.gguf` is used with every variant.
- Motion model GGUF, e.g. https://huggingface.co/LocalAI-io/Kimodo-SOMA-RP-v1.1-GGML: 0.3B params, F32, **1.13 GB**.
- The encoder **streams layers in chunks**: `KIMODO_TEXT_LAYER_CHUNK=1..32`, default 8 for the library and CLI.
- Missing features per the README (as of 2026-11): **general constraint input**, 77-joint SOMA expansion, skinned GLB
  export, and quantization of the motion denoiser. The constraint input gap matters because our Timeline features depend
  on it. Check its status, and plan to contribute upstream or fall back to the Python sidecar.
- Docs worth reading on the host: `docs/PROFILING.md` and `docs/QUANTIZATION.md` in the repo.
