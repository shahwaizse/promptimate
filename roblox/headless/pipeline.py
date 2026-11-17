"""Headless recording of an episode: Studio only stages and poses (no rendering), the GPU renders offscreen.

    silent_mp4 = record(camera_cues, name, fps=30, end=None, out=Path)

Steps and rough costs (receipts, 107 s): shot planning (Studio camera checks) ~?s, static world export ~8 s (cached
across episodes), pose dump ~6 s, render ~25 s."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "mcp_server"))
import export as X  # noqa: E402
import hlrender as RD  # noqa: E402

CACHE = Path(os.environ.get("PROMPTIMATE_HEADLESS_CACHE", r"D:\tmp\headless"))


def record(cues, name: str, fps: int = 30, end: float | None = None, out: Path | None = None, log=print,
           fresh_static: bool = False, ass: str | None = None, fonts: str | None = None, wav: str | None = None,
           workers: int = 3) -> dict:
    import roblox_record as RR
    T = {}
    t = time.time()
    perf = RR.Perf()
    t_end = end if end is not None else perf.end()
    RR._ensure_running()
    shots, notes = RR.plan_shots(sorted(cues, key=lambda c: c.start), perf, (1080, 1920), t_end, image_check=False)
    n = int(t_end * fps)
    cams = np.zeros((n, 7), "f4")
    for i in range(n):
        _k, _c, pos, look, fov = RR.camera(shots, perf, i / fps)
        cams[i] = [*pos, *look, fov]
    T["plan"] = time.time() - t
    log(f"headless plan: {len(shots)} shots, {T['plan']:.1f}s")
    scene = CACHE / "scene"
    ep_dir = CACHE / name
    t = time.time()
    if fresh_static or not (scene / "static.json").exists():
        X.export_static(scene)
    T["static"] = time.time() - t
    t = time.time()
    X.export_dynamic(ep_dir, fps, 0.0, (n - 1) / fps)
    T["poses"] = time.time() - t
    for f in ("static.json",):
        (ep_dir / f).write_bytes((scene / f).read_bytes())
    np.save(ep_dir / "cams.npy", cams)
    t = time.time()
    out = out or (ep_dir / f"{name}.mp4")
    r = RD.render_parallel(ep_dir, cams, out, fps, workers=workers, ass=ass, fonts=fonts, wav=wav)
    T["render"] = time.time() - t
    log(f"headless render: {r}")
    return {"mp4": str(out), "timing": {k: round(v, 1) for k, v in T.items()}, "render": r, "notes": notes}
