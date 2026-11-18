"""Machine-specific settings in one place: tool paths, cache folders and the video encoder.

Every value comes from an environment variable, which can also be set in `local.env` at the repo root (gitignored;
copy `local.env.example`). Real environment variables win over `local.env`. Defaults keep everything inside the clone
(`.cache/`) and find tools on PATH, so a fresh machine needs no edits beyond installing ffmpeg.
"""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _main_checkout() -> Path | None:
    """In a git worktree, the main checkout (where the gitignored local.env lives)."""
    g = REPO / ".git"
    if g.is_file():                                   # worktree: ".git" is a file "gitdir: <main>/.git/worktrees/<n>"
        try:
            d = Path(g.read_text().split("gitdir:", 1)[1].strip())
            return d.parents[2] if d.parent.name == "worktrees" else None
        except (OSError, IndexError):
            return None
    return None


def _load_local_env() -> None:
    p = REPO / "local.env"
    if not p.exists():
        main = _main_checkout()
        p = main / "local.env" if main else p
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_local_env()


def _path(var: str, default: Path) -> Path:
    v = os.environ.get(var)
    return Path(v) if v else default


# Working data of the headless shorts pipeline (scenes, own sets/props, mesh index, sign textures). Rebuildable.
HEADLESS_CACHE = _path("PROMPTIMATE_HEADLESS_CACHE", REPO / ".cache" / "headless")
os.environ.setdefault("PROMPTIMATE_HEADLESS_CACHE", str(HEADLESS_CACHE))
OWN = HEADLESS_CACHE / "own"
# tiny-voca TTS (Apache-2.0): a folder with its own venv and weights (see docs in demo/episodes/README.md)
TINY_VOCA = _path("PROMPTIMATE_TINY_VOCA", REPO / ".cache" / "tiny-voca")
# scratch space for episode builds (judge kits, debug sheets)
SCRATCH = _path("PROMPTIMATE_SCRATCH", REPO / ".cache" / "scratch")


def _tool(var: str, name: str) -> str:
    v = os.environ.get(var)
    if v:
        return v
    found = shutil.which(name)
    if found:
        return found
    ff = os.environ.get("PROMPTIMATE_FFMPEG")          # ffprobe usually sits next to ffmpeg
    if ff and name != "ffmpeg":
        cand = Path(ff).with_name(name + Path(ff).suffix)
        if cand.exists():
            return str(cand)
    return name                                        # let the subprocess call fail with a clear "not found"


def ffmpeg() -> str:
    return _tool("PROMPTIMATE_FFMPEG", "ffmpeg")


def ffprobe() -> str:
    return _tool("PROMPTIMATE_FFPROBE", "ffprobe")


@functools.lru_cache(maxsize=1)
def h264_encoder() -> str:
    """The fastest H.264 encoder this ffmpeg can actually open: AMD AMF, NVIDIA NVENC, Intel QSV, else libx264.
    PROMPTIMATE_VENC forces one."""
    forced = os.environ.get("PROMPTIMATE_VENC", "auto")
    if forced in ("x264", "libx264"):
        return "libx264"
    if forced != "auto":
        return forced
    for enc in ("h264_amf", "h264_nvenc", "h264_qsv"):
        try:
            r = subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                "color=s=256x256:d=0.1", "-frames:v", "1", "-c:v", enc, "-f", "null", "-"],
                               capture_output=True, timeout=20)
            if r.returncode == 0:
                return enc
        except (OSError, subprocess.SubprocessError):
            break
    return "libx264"


def h264_args(quality: int = 21) -> list[str]:
    """Fast near-transparent H.264 settings for the chosen encoder (lower `quality` = better)."""
    enc = h264_encoder()
    if enc == "h264_amf":
        return ["-c:v", enc, "-quality", "speed", "-rc", "cqp", "-qp_i", str(quality - 1), "-qp_p", str(quality + 1),
                "-pix_fmt", "yuv420p"]
    if enc == "h264_nvenc":
        return ["-c:v", enc, "-preset", "p4", "-rc", "constqp", "-qp", str(quality), "-pix_fmt", "yuv420p"]
    if enc == "h264_qsv":
        return ["-c:v", enc, "-global_quality", str(quality), "-pix_fmt", "nv12"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(quality - 2), "-pix_fmt", "yuv420p"]
