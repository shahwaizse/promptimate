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


def static_for(ep) -> Path:
    """The world an episode plays in: our own procedural sets (STATIC = "own") or the exported Studio place."""
    own = CACHE / "own" / "scene_static.json"
    if getattr(ep, "STATIC", None) == "own" and own.exists():
        return own
    return CACHE / "scene" / "static.json"


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


def record_offline(ep, cues, name: str, fps: int = 30, end: float | None = None, out: Path | None = None, log=print,
                   ass: str | None = None, fonts: str | None = None, wav: str | None = None, workers: int = 3,
                   perf_actors: dict | None = None) -> dict:
    """The whole recording without Studio: Python director -> GPU-checked shot planning -> parallel render.
    perf_actors: roblox_perform's state (default: the last one saved)."""
    import director as DR
    import checks as CK
    import roblox_record as RR
    T = {}
    t = time.time()
    if perf_actors is None:
        perf_actors = json.loads((RR.STATE / "state.json").read_text())["actors"]
    perf = RR.Perf()
    t_end = end if end is not None else perf.end()
    sp = static_for(ep)
    ep_dir = CACHE / name
    ep_dir.mkdir(parents=True, exist_ok=True)
    static = json.loads(sp.read_text())
    (ep_dir / "static.json").write_bytes(sp.read_bytes())
    r = DR.build(ep, perf_actors, ep_dir, fps, t_end, static)
    (ep_dir / "hide.json").write_text(json.dumps(r["hidden_static"]))
    T["director"] = time.time() - t
    t = time.time()
    names = json.loads((ep_dir / "dynamic.json").read_text())["order"]
    RR.BACKEND = CK.Checks(ep_dir, names, ep_dir / "frames.npz", fps)
    try:
        pk = os.environ.get("PROMPTIMATE_SHOT_PICKS")
        import audit as AU
        if pk and Path(pk).exists() and (ep_dir / "shots.json").exists():
            # picks refer to the saved plan: reuse it exactly (a re-plan can shift shot boundaries)
            shots = [RR.CameraCue(**c) for c in json.loads((ep_dir / "shots.json").read_text())]
            notes, rep, after = [], {}, {}
        else:
            shots, notes = RR.plan_shots(sorted(cues, key=lambda c: c.start), perf, (1080, 1920), t_end, image_check=True)
            shots, an, rep, after = AU.repair(shots, perf, t_end, RR.BACKEND, log=log)
            notes = list(notes) + an
        rv = os.environ.get("PROMPTIMATE_SHOT_REVIEW")
        if rv and Path(rv).exists():          # a vision reviewer's marks on the last recording (shot_review.py)
            import shot_review as SRV_
            shots = SRV_.apply(shots, rv, perf, t_end, RR.BACKEND, log=log)
        pk = os.environ.get("PROMPTIMATE_SHOT_PICKS")
        if pk and Path(pk).exists():          # a vision reviewer's picks among rendered candidates (shot_pick.py)
            import shot_pick as SPK
            shots = SPK.apply(shots, pk, log=log)
        else:     # the plan the picks refer to (a picked recording keeps the plan its candidates came from)
            (ep_dir / "shots.json").write_text(json.dumps([c.model_dump() for c in shots], default=str))
        (ep_dir / "camera_audit.json").write_text(json.dumps({"before": rep, "after": after}, default=str, indent=1))
    finally:
        RR.BACKEND = None
    n = int(t_end * fps)
    cams = np.zeros((n, 7), "f4")
    for i in range(n):
        _k, _c, pos, look, fov = RR.camera(shots, perf, i / fps)
        cams[i] = [*pos, *look, fov]
    np.save(ep_dir / "cams.npy", cams)
    T["plan"] = time.time() - t
    log(f"offline plan: {len(shots)} shots, {T['plan']:.1f}s")
    t = time.time()
    out = out or (ep_dir / f"{name}.mp4")
    rr = RD.render_parallel(ep_dir, cams, out, fps, workers=workers, ass=ass, fonts=fonts, wav=wav)
    T["render"] = time.time() - t
    log(f"offline render: {rr}")
    return {"mp4": str(out), "timing": {k: round(v, 1) for k, v in T.items()}, "render": rr, "notes": notes}
