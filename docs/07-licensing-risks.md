# 07: Licensing and risks

## Model licenses (verify the license text before any release)
- **Kimodo code**: Apache-2.0. **kimodo.cpp**: Apache-2.0.
- **SOMA and G1 checkpoints**: NVIDIA Open Model License. Sources *disagree* on whether commercial use is allowed
  (one says research and commercial, another says R&D). **Open question: read the actual license text and the HF model
  cards.**
- **SMPL-X checkpoint**: NVIDIA R&D Model License, research only. Do not use it.
- **Text encoder**: built on Meta Llama 3, so the Meta Llama 3 Community License applies (includes attribution and
  acceptable-use terms).
- Text To Anim (UE) has users accept both the NVIDIA and Meta licenses before downloading. Copy that flow.
- Training data: the Bones Rigplay 1 dataset is proprietary but described as "commercially-friendly" by NVIDIA. Check
  what that means for generated output.
- TexMotion is MIT, so its retargeting code can be reused with attribution.

## Distribution
- 9+ GB of weights can't ship in an Asset Store or UPM package. Download on first run from HF.
- Check whether Asset Store policies allow downloading third-party AI models (with their licenses) after install.

## Product risks
- **Unity** could ship a local mode for AI Animate.
- **TexMotion**, or another project, could generalize beyond VRChat.
- **kimodo.cpp maturity**: Vulkan/AMD stability is unverified, constraint input is not implemented yet, and the
  project is young.
- **Quality on low VRAM**: Q4/Q5 encoders are "experimental".
- **Anthropic policy** on third-party subscription use is changing. The MCP design avoids the issue, but recheck it.
