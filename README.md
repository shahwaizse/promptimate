# Promptimate

**Free, local text-to-animation for Unity.** Type a sentence such as *"a person walks forward and waves with their
right hand"* and get a standard Humanoid `AnimationClip` that plays on any humanoid rig, Mixamo characters included.
Generation runs entirely on your own GPU with NVIDIA's Kimodo motion model (through [kimodo.cpp](https://github.com/localai-org/kimodo.cpp)
on Vulkan), so there is no cloud, no credits and no subscription. A local MCP server lets Claude Code, or any other MCP
client, act as the director. It plans multi-shot sequences, generates each clip, checks the result and regenerates
bad takes.

**Status:** v0.1.0 preview. It works end to end on the developer's machine, but it has only been tested on one
AMD GPU under Windows. Expect rough edges.

## Requirements

- Windows 10/11 (x64)
- Unity 6 (6000.0 or newer)
- A GPU with a Vulkan driver and about **8 GB VRAM** (AMD, NVIDIA or Intel in principle; only AMD has been tested).
  The models stay loaded between requests (about 6 GB) and unload after 10 minutes idle.
- 16 GB system RAM
- Python 3.10+ (used for the MCP server)
- About 7 GB of free disk space for the models
- Optional: [Claude Code](https://claude.com/claude-code) or another MCP client

## Quick start

```powershell
git clone https://github.com/shahwaizse/promptimate.git
cd promptimate
.\setup.ps1
```

`setup.ps1` checks your GPU and Vulkan runtime, installs the prebuilt kimodo.cpp engine from GitHub Releases into
`engine/`, creates a Python `.venv`, asks you to accept the model licenses, downloads the models (about 6 GB, from
Hugging Face) into `models/`, and prints the next steps. Everything stays inside the clone folder.

1. **Add the Unity package.** In Unity 6, open *Window > Package Manager > + > Add package from disk...* and select
   `unity/com.promptimate.unity/package.json`.
2. **Connect Claude Code** (use the paths that `setup.ps1` printed):
   ```powershell
   claude mcp add kimodo-motion -e KIMODO_TEXT_QUANT=q4_k_m -e UNITY_PROJECT="C:\path\to\YourUnityProject" -- "C:\path\to\promptimate\.venv\Scripts\python.exe" "C:\path\to\promptimate\mcp_server\server.py"
   ```
   For Claude Desktop or another client, add an MCP server with the same command, args and env. There is a template
   in [`.mcp.json.example`](.mcp.json.example). Promptimate never signs in to Claude: it's a local server your own
   client connects to.
3. **Ask for motion,** for example *"make three clips for a guard: patrol walk, hears a noise and looks around, spots a
   friend and waves"*. The clips appear in `Assets/Promptimate/Generated/` and import as Humanoid animation clips. GLB and BVH copies
   are also written to `output/`.

## MCP tools

The server id is `kimodo-motion`.

| Tool | What it does |
|---|---|
| `generate_motion(segments[{prompt, seconds}], name?, seed, steps=30, transition_frames=5, unity_check=true)` | Generates a clip from one or more blended text segments. Returns stats, a preview image, file paths and the check results. |
| `validate_in_unity(names?, self_test)` | Re-runs headless Unity validation. With `self_test` it also runs the negative controls. |
| `list_motions(limit)` | Lists earlier results. |
| `get_motion_preview(name)` | Returns the metadata and preview image of an earlier result. |
| `worker_status(warm_up)` | Shows whether the GPU worker is loaded, or loads it now. |

See [`mcp_server/README.md`](mcp_server/README.md) for environment variables and details.

## Limitations

- **Body only.** There are no fingers and no facial animation. The SOMA model outputs a 30-joint body skeleton.
- **No positional constraints yet.** You can't specify keyframe poses, root paths or hand and foot targets, because
  kimodo.cpp doesn't expose them. Input is text plus multi-segment prompts.
- **Prompt-following is imperfect.** For example, "stops" may keep drifting forward. Regenerate with another seed or
  reword the prompt. Claude does this automatically when the checks or the preview show a problem.
- **Speed:** about **20 s per 5 s clip** once warm (30 diffusion steps), measured on an AMD RX 6600 XT (8 GB). The first
  request also loads the models, which takes 1 to 2 minutes from an HDD.
- **Only tested on AMD / Windows.** NVIDIA and Intel should work through Vulkan but haven't been tested.
- The model licenses are separate from this code. Check them before you use output commercially (see below).

## Credits

- **NVIDIA Kimodo**: the SOMA text-to-motion diffusion model.
- **[kimodo.cpp](https://github.com/localai-org/kimodo.cpp)** from the LocalAI project: the GGML/Vulkan port that
  makes local generation possible, plus the GGUF conversions on Hugging Face.
- **Meta Llama 3**: the LLM2Vec text encoder is built with Meta Llama 3.
- **[ggml](https://github.com/ggml-org/ggml)**: the tensor library and Vulkan backend.

## License

Promptimate's code is released under the [MIT License](LICENSE). Third-party components and the model licenses are
listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). The models aren't included. You download them during
setup under the NVIDIA Open Model License (Kimodo SOMA) and the Meta Llama 3 Community License (text encoder).
