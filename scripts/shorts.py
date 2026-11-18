"""One entry point for the headless shorts factory.

    .venv\\Scripts\\python scripts\\shorts.py doctor              # what's installed, what's missing, how to fix it
    .venv\\Scripts\\python scripts\\shorts.py setup               # build every rebuildable asset (cache, fonts, media)
    .venv\\Scripts\\python scripts\\shorts.py voice               # install the tiny-voca narrator (CPU torch, ~1 GB)
    .venv\\Scripts\\python scripts\\shorts.py produce STORY [...]  # story -> finished vertical short (produce.py args)
    .venv\\Scripts\\python scripts\\shorts.py compile STORY        # story spec -> demo/episodes/eps/<slug>.py only
    .venv\\Scripts\\python scripts\\shorts.py catalog             # the writer's vocabulary (actions, props, sets, sfx)
    .venv\\Scripts\\python scripts\\shorts.py library             # pre-generate the shared motion library (GPU)
    .venv\\Scripts\\python scripts\\shorts.py test                # fast checks (no GPU)
    .venv\\Scripts\\python scripts\\shorts.py judge-prep OUT SEED name=video.mp4 ...
    .venv\\Scripts\\python scripts\\shorts.py judge-tally OUT

STORY is a slug in demo/episodes/stories/ (e.g. lie_shrink) or a path to a story .py file.
See demo/episodes/README.md for the whole pipeline.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / "mcp_server")]
import local_config as LC  # noqa: E402

PY = sys.executable
EP = REPO / "demo" / "episodes"
HL = REPO / "roblox" / "headless"
MEDIA = EP / "build" / "_media"
FONTS = {
    "Montserrat-Black.ttf": "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-Black.ttf",
    "Montserrat-ExtraBold.ttf": "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf",
}
TINY_VOCA_REPO = "https://github.com/n4ze3m/tiny-voca"
TINY_VOCA_COMMIT = "62e2adef158bc997042cc6234f541f1e0e4cd55d"     # the version the narration was tuned on
FACES = ["angry", "crying", "grin", "happy", "love", "neutral", "sad", "scared", "shocked", "sleeping", "smug", "tired",
         "wink"]


def _run(args: list, cwd: Path = REPO) -> int:
    print(">", " ".join(map(str, args)), flush=True)
    return subprocess.call([str(a) for a in args], cwd=str(cwd))


# --------------------------------------------------------------------------------------------------- doctor
def checks() -> list[tuple[str, bool, str]]:
    """(item, ok, how to fix)."""
    out = []

    def add(name, ok, fix):
        out.append((name, bool(ok), fix))

    add(f"python {sys.version.split()[0]} (3.10+)", sys.version_info >= (3, 10), "install Python 3.10+")
    for mod, pkg in (("numpy", "numpy"), ("PIL", "pillow"), ("mcp", "mcp[cli]"), ("moderngl", "moderngl"),
                     ("scipy", "scipy")):
        add(f"python package {pkg}", importlib.util.find_spec(mod) is not None,
            "pip install -r mcp_server\\requirements.txt -r requirements-shorts.txt")
    ff = LC.ffmpeg()
    have_ff = bool(shutil.which(ff) or Path(ff).exists())
    add(f"ffmpeg ({ff})", have_ff, "install ffmpeg (with libass) and put it on PATH or set PROMPTIMATE_FFMPEG in local.env")
    fp = LC.ffprobe()
    add(f"ffprobe ({fp})", shutil.which(fp) or Path(fp).exists(), "ships with ffmpeg; or set PROMPTIMATE_FFPROBE")
    if have_ff:
        add(f"H.264 encoder: {LC.h264_encoder()}", True, "")
    try:
        import moderngl
        ctx = moderngl.create_standalone_context(require=330)
        add(f"OpenGL 3.3 offscreen ({ctx.info.get('GL_RENDERER', '?')})", True, "")
        ctx.release()
    except Exception as e:  # noqa: BLE001
        add("OpenGL 3.3 offscreen context", False, f"update the GPU driver ({str(e)[:80]})")
    eng = [REPO / "engine", REPO / "third_party" / "kimodo.cpp" / "build" / "promptimate"]
    if os.environ.get("KIMODO_ENGINE_DIR"):
        eng.insert(0, Path(os.environ["KIMODO_ENGINE_DIR"]))
    add("kimodo engine", any(any(p.rglob("kmd-generate*")) for p in eng if p.exists()), "run .\\setup.ps1")
    add("motion models", (REPO / "models").exists() and any((REPO / "models").rglob("*.gguf")), "run .\\setup.ps1")
    C = LC.HEADLESS_CACHE
    add(f"headless cache: own sets ({C})", (C / "own" / "scene_static.json").exists() and (C / "own" / "sets" / "maps").exists(),
        "scripts\\shorts.py setup")
    add("headless cache: own props + looks", (C / "own" / "props.json").exists() and (C / "own" / "looks.json").exists(),
        "scripts\\shorts.py setup")
    add("headless cache: materials", (C / "mat").exists() and any((C / "mat").glob("*.png")), "scripts\\shorts.py setup")
    add("headless cache: face textures", all((C / "tex" / f"face_{f}.png").exists() for f in FACES),
        "scripts\\shorts.py setup")
    add("caption fonts (Montserrat)", all((MEDIA / "fonts" / f).exists() for f in FONTS), "scripts\\shorts.py setup")
    man = json.loads((EP / "media_manifest.json").read_text())
    have = sum((MEDIA / f"{k}_{q.replace(' ', '_')}_{v['pick']}.json").exists() for k in man for q, v in man[k].items())
    total = sum(len(v) for v in man.values())
    add(f"music + sfx cache ({have}/{total}; the rest downloads from Openverse on first use)", have > 0,
        "scripts\\shorts.py setup  (needs internet)")
    tv = LC.TINY_VOCA
    add(f"tiny-voca narrator ({tv})", (tv / "venv").exists() and (tv / "tiny-voca" / "weights" / "tiny-voca.pt").exists(),
        "install tiny-voca: see demo/episodes/README.md (Narrator)")
    pack = REPO / "assets" / "motion_library"
    add("motion library pack (assets/motion_library)", pack.exists() and any(pack.iterdir()),
        "git pull (it is tracked), or scripts\\shorts.py library to generate it locally")
    return out


def doctor() -> int:
    bad = 0
    for name, ok, fix in checks():
        print(f"  {'ok ' if ok else 'MISSING'}  {name}" + ("" if ok else f"\n           -> {fix}"))
        bad += not ok
    print("\nall set" if not bad else f"\n{bad} item(s) missing")
    return 1 if bad else 0


# ---------------------------------------------------------------------------------------------------- setup
def setup(skip_media: bool = False) -> int:
    print(f"headless cache: {LC.HEADLESS_CACHE}")
    # order matters: characters create the mesh index that the sets extend
    for script, args in (("materials.py", []), ("own_assets.py", []), ("own_sets.py", ["--no-render"])):
        if _run([PY, HL / script, *args]) != 0:
            print(f"setup: {script} failed")
            return 1
    faces = HL / "own_faces.py"
    if faces.exists():
        _run([PY, faces])
    elif not all((LC.HEADLESS_CACHE / "tex" / f"face_{f}.png").exists() for f in FACES):
        print("setup: no face textures (roblox/headless/own_faces.py missing)")
    (MEDIA / "fonts").mkdir(parents=True, exist_ok=True)
    for name, url in FONTS.items():
        p = MEDIA / "fonts" / name
        if not p.exists():
            print("font", name)
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "promptimate-setup"}), timeout=60) as f:
                p.write_bytes(f.read())
    if not skip_media:
        sys.path.insert(0, str(EP))
        os.chdir(EP)
        import produce as P
        man = json.loads((EP / "media_manifest.json").read_text())
        for kind, items in man.items():
            for q, v in items.items():
                try:
                    P.openverse(q, kind, MEDIA, pick=v["pick"], min_s=60 if kind == "music" else 0,
                                max_s=1e9 if kind == "music" else 8)
                except (SystemExit, OSError) as e:
                    print(f"  {kind} '{q}': {e}")
        os.chdir(REPO)
    return doctor()


# ---------------------------------------------------------------------------------------------------- voice
def voice() -> int:
    """tiny-voca (Apache-2.0 code and weights) in its own venv: torch CPU + the dizione phonemizer + weights."""
    root = LC.TINY_VOCA
    src = root / "tiny-voca"
    root.mkdir(parents=True, exist_ok=True)
    if not src.exists() and _run(["git", "clone", TINY_VOCA_REPO, src]) != 0:
        return 1
    _run(["git", "-C", src, "checkout", "-q", TINY_VOCA_COMMIT])
    vpy = root / "venv" / "Scripts" / "python.exe"
    if not vpy.exists() and _run([PY, "-m", "venv", root / "venv"]) != 0:
        return 1
    for st in ([vpy, "-m", "pip", "install", "torch", "--index-url", "https://download.pytorch.org/whl/cpu"],
               [vpy, "-m", "pip", "install", "-e", f"{src}[own]"]):
        if _run(st) != 0:
            return 1
    w = src / "weights"
    if not (w / "tiny-voca.pt").exists():
        from huggingface_hub import snapshot_download
        snapshot_download("n4ze3m/tiny-voca", local_dir=str(w))
    print(f"narrator installed in {root}")
    return 0


# ------------------------------------------------------------------------------------------------------ main
def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "doctor":
        return doctor()
    if cmd == "voice":
        return voice()
    if cmd == "setup":
        return setup(skip_media="--no-media" in rest)
    if cmd == "produce":
        if not rest:
            print("usage: shorts.py produce STORY [--offline] [...]")
            return 2
        if "--offline" not in rest and "--headless" not in rest and "--studio" not in rest:
            rest = rest + ["--offline"]                     # the headless pipeline is the default
        rest = [r for r in rest if r != "--studio"]
        return _run([PY, EP / "produce.py", *rest], cwd=EP)
    if cmd == "compile":
        return _run([PY, EP / "story_compile.py", _story(rest[0])], cwd=EP)
    if cmd == "catalog":
        return _run([PY, EP / "story_compile.py", "--catalog"], cwd=EP)
    if cmd == "library":
        return _run([PY, REPO / "scripts" / "build_motion_library.py", *rest])
    if cmd == "test":
        return _run([PY, "-m", "unittest", "discover", "-s", "tests", *rest])
    if cmd == "judge-prep":
        return _run([PY, REPO / "bench" / "shorts_judge_prep.py", *rest])
    if cmd == "judge-tally":
        return _run([PY, REPO / "bench" / "shorts_judge_tally.py", *rest])
    print(f"unknown command {cmd!r}\n{__doc__}")
    return 2


def _story(s: str) -> str:
    p = Path(s)
    if p.suffix == ".py" and p.exists():
        return str(p.resolve())
    return str(EP / "stories" / f"{s}.py")


if __name__ == "__main__":
    rc = main()
    sys.stdout.flush()
    os._exit(rc)
