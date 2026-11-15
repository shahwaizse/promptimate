# Shorts template

Turns `render_shot` shots plus voiceover timing into a HyperFrames project for a vertical short (or a 16:9
animatic). It assembles the shots on hard cuts with karaoke captions in the 9:16 safe band, a hook title on frame 0,
a music slot (a silent placeholder until you add a track), whooshes on cuts and an end card.

```powershell
.venv\Scripts\python.exe demo\shorts_template\build_short.py my_short.json          # build the project
.venv\Scripts\python.exe demo\shorts_template\build_short.py my_short.json --render # + hyperframes check/render
```

The spec format is in the docstring of `build_short.py`. Output goes to `build/<name>/` (gitignored): open it in the
HyperFrames desktop app or with `npx hyperframes preview` to keep editing.

## Example: "Wrong Turn" (`story/`)

Leo, a lost traveller, walks in from the left and looks around. Ava walks in from the right and points him back the
way he came. He thanks her and jogs off. It runs 8 shots, about 21 s, with two characters. It uses `continue_from`
chains (5 clips for Leo, 3 for Ava), walk-ins generated with root paths from the staging helper, and one shared story
clock so cuts stay continuous.

```powershell
.venv\Scripts\python.exe demo\shorts_template\story\gen_motions.py   # motions via server.generate_motion
.venv\Scripts\python.exe demo\shorts_template\story\make_short.py    # shots, TTS voiceover, build, render
```

The voiceover uses local Kokoro TTS (`npx hyperframes tts`). It needs `kokoro-onnx` and `soundfile` in a Python
that `HYPERFRAMES_PYTHON` points to; `make_short.py` uses `.cache/tts-venv` if it exists.

`gallery.py` renders every camera preset and every lighting preset on one scene into `build/gallery/`. It doubles as
a regression check: it exits non-zero if any render fails validation.
