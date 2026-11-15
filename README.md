# Promptimate

**Free, local text-to-animation for Unity.** Type a sentence such as *"a person walks forward and waves with their
right hand"* and get a standard Humanoid `AnimationClip` that plays on any humanoid rig, Mixamo characters included.
Generation runs entirely on your own GPU with NVIDIA's Kimodo motion model (through [kimodo.cpp](https://github.com/localai-org/kimodo.cpp)
on Vulkan), so there is no cloud, no credits and no subscription. A local MCP server lets Claude Code, or any other MCP
client, act as the director. It plans multi-shot sequences, generates each clip, checks the result and regenerates
bad takes.

**Status:** v0.2.0 preview.

## Requirements

- Windows 10/11 (x64)
- Unity 6 (6000.0 or newer)
- A GPU with a Vulkan driver (AMD, NVIDIA or Intel) and about **2 GB of free VRAM**. The motion model stays loaded
  between requests and unloads after 10 minutes idle; the text encoder runs on the CPU.
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
| `generate_motion(segments[{prompt, seconds}], name?, seed, steps=30, takes=3, clean=true, loop=false, in_place=false, root_path?, auto_stop=true, text_cfg?, transition_frames=5, unity_check="background")` | Generates a clip from one or more blended text segments. Makes 3 variations by default and keeps the cleanest, locks the feet to the ground, holds the character still where the text says it stops, and can make seamless loops, in-place clips or follow a root path. Returns stats, checks, a preview sheet (plus a takes sheet) and file paths. |
| `use_take(name, take)` | Switches a multi-take result to another variation. |
| `validate_in_unity(names?, self_test)` | Re-runs headless Unity validation. With `self_test` it also runs the negative controls. |
| `list_motions(limit)` | Lists earlier results. |
| `get_motion_preview(name)` | Returns the metadata (including the background Unity check) and preview image of an earlier result. |
| `worker_status(warm_up)` | Shows whether the GPU worker is loaded, or loads it now. |

See [`mcp_server/README.md`](mcp_server/README.md) for environment variables and details.

## Limitations

- **Body only.** There are no fingers and no facial animation. The SOMA model outputs a 30-joint body skeleton.
- **Constraints:** root paths, "stop here" holds and seamless loops are supported (through a small patch to
  kimodo.cpp, see `scripts/kimodo-promptimate.patch`). Hand and foot targets aren't exposed yet.
- **Prompt-following is imperfect.** Unusual actions can come out generic. Each call makes several variations and
  Claude regenerates when the checks or the preview show a problem.
- **Speed:** about **2.5 s per 5 s clip** once warm (30 diffusion steps), so a default 3-take call takes about 10 s,
  on a mid-range 8 GB GPU. The first request also loads the models, which takes up to a minute from an HDD.
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
