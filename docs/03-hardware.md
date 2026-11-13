# 03: Hardware: fitting in 8 GB (RX 6600 XT)

The dev host is an **AMD RX 6600 XT, 8 GB, RDNA2 (gfx1032)**.

## VRAM budget
| Part | Size |
|---|---|
| Motion diffusion model (SOMA) | ~1.1 GB |
| Text encoder Q8_0 | 8.1 GB, doesn't fit alongside the motion model |
| Text encoder Q5_K / Q4_K_M | 5.3 / 5.1 GB, fits with headroom |
| Text encoder Q4_K | 4.4 GB |

The text encoder runs **once per prompt segment**, so it doesn't need to stay resident in VRAM.

## Ways to fit, in order of preference
1. **Layer streaming** of the Q8 encoder (`KIMODO_TEXT_LAYER_CHUNK`). Keeps full quality, but each prompt encodes slower.
2. **A lower quant** (Q4_K_M or Q5_K). Fits fully, but upstream marks it "experimental", so check the motion quality.
3. **Encoder on CPU.** The official PyTorch code supports `TEXT_ENCODER_DEVICE=cpu`. For kimodo.cpp, check whether
   a split CPU-encoder/Vulkan-denoiser setup is possible.

## Routes on AMD
- **kimodo.cpp + Vulkan (main route).** Vulkan runs on AMD, but upstream doesn't mention AMD and publishes no
  benchmarks. **Unverified, so it is the first thing the spike tests.**
- **Official PyTorch + ROCm (fallback/reference).** gfx1032 isn't officially supported by ROCm. It usually works on
  Linux with `HSA_OVERRIDE_GFX_VERSION=10.3.0`. Use it with the CPU text encoder (under 3 GB VRAM). This route is also
  the reference for checking kimodo.cpp output and for constraint features kimodo.cpp lacks.
- The existing UE plugins require NVIDIA RTX, so they are irrelevant on this card.

## System RAM
16 GB minimum, 32 GB recommended, especially when the encoder runs on the CPU (the Q8 encoder alone is 8 GB).

## Product implication
Detect VRAM at startup and pick automatically: full GPU (16 GB or more), layer streaming (8–12 GB), or quant/CPU encoder
(under 8 GB). Expose a "fast mode" (Q4/Q5). This would make it run on mid-range AMD and NVIDIA cards, which the Unreal
plugins don't support.
