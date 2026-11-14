# Third-party notices

Promptimate's own code (the Unity package, the MCP server and the scripts in this repository) is MIT-licensed; see
[`LICENSE`](LICENSE). It builds on the third-party work listed below. Each component keeps its own license.

## Included in this repository

### kimodo.cpp (Apache License 2.0)
- Project: https://github.com/localai-org/kimodo.cpp (GGML port of NVIDIA Kimodo, from the LocalAI project)
- `mcp_server/vendor/export_bvh.py` and `mcp_server/vendor/export_glb.py` are vendored from kimodo.cpp `scripts/`
  (commit `75ed52d`). The SOMA 30-joint skeleton constants in `mcp_server/motion.py` are copied from
  `scripts/export_glb.py`, and `scripts/download_models.py` mirrors kimodo.cpp's `scripts/download_gguf_weights.py`.
- The full license text is in [`mcp_server/vendor/LICENSE-kimodo.cpp.txt`](mcp_server/vendor/LICENSE-kimodo.cpp.txt).
- kimodo.cpp NOTICE: "kimodo.cpp. This project uses ggml, Copyright the ggml authors (https://github.com/ggml-org/ggml)."

## Included in the prebuilt engine (`kimodo-engine-win64-vulkan.zip`, GitHub Releases)

The release asset is an unmodified Windows x64 Release build of kimodo.cpp with the ggml Vulkan backend
(`kmd-generate.exe`, `ggml*.dll`). It ships with its license files:

| Component | License | File in the zip |
|---|---|---|
| kimodo.cpp | Apache License 2.0 | `LICENSE-kimodo.cpp.txt`, `NOTICE-kimodo.cpp.txt` |
| ggml (https://github.com/ggml-org/ggml), Copyright (c) 2023-2026 The ggml authors | MIT | `LICENSE-ggml.txt` |

The build also needs the Microsoft Visual C++ 2015-2022 runtime and a Vulkan GPU driver. Both are installed
separately and are not redistributed.

## NOT included: model weights (downloaded by you during setup)

No model weights are in this repository or in any release. `setup.ps1` (via `scripts/download_models.py`) downloads
them from Hugging Face (`LocalAI-io/Kimodo-SOMA-RP-v1.1-GGML`, `LocalAI-io/Llama-3-Kimodo-GGML`) only after you accept
their licenses. By downloading them you agree to:

| Model | Role | License |
|---|---|---|
| NVIDIA Kimodo SOMA (RP v1.1), GGUF conversion | Motion diffusion model | [NVIDIA Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/) |
| LLM2Vec text encoder based on Meta Llama 3 (`Llama-3-Kimodo`), GGUF conversion, plus tokenizer | Text encoder | [Meta Llama 3 Community License](https://www.llama.com/llama3/license/) |

**Built with Meta Llama 3.** Your use of the Llama 3-based text encoder is subject to the Meta Llama 3 Community
License and Acceptable Use Policy. Promptimate does not use, download or support the research-only SMPL-X Kimodo
checkpoint.

Check each license yourself before using generated animation commercially.

## Python dependencies (installed by pip, not redistributed)

`mcp_server/requirements.txt` installs these from PyPI into a local `.venv`:

| Package | License |
|---|---|
| mcp (Model Context Protocol Python SDK) | MIT |
| numpy | BSD-3-Clause |
| matplotlib | Matplotlib License (PSF-based, BSD-compatible) |
| pillow | MIT-CMU (HPND) |
| huggingface_hub | Apache-2.0 |

Their transitive dependencies (pydantic, httpx, starlette, uvicorn and others; see
`mcp_server/requirements.lock.txt`) are under their own permissive licenses.

## NOT included: demo characters, renders and music

The launch videos and screenshots use Kenney character models (CC0) and Adobe Mixamo characters. None of these
characters, rendered frames, videos or music are distributed in this repository. The `unity/DemoStudio` project
contains only the editor scripts used to render the demos; bring your own characters.

## Trademarks

NVIDIA and Kimodo are trademarks of NVIDIA Corporation. Unity is a trademark of Unity Technologies. Claude is a
trademark of Anthropic. Llama and Meta are trademarks of Meta Platforms. Mixamo and Adobe are trademarks of Adobe.
Promptimate is not affiliated with, endorsed by or sponsored by any of them.
