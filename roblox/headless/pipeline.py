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

import local_config as LC  # noqa: E402
CACHE = LC.HEADLESS_CACHE


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


def clear_foreground(ep_dir: Path, shots, perf, cams, fps: int, t_end: float) -> int:
    """A film crew clears the foreground: during each shot, any character that isn't the shot's subject (or partner)
    and stands between the camera and the subject, or right against the lens, is hidden for that shot (the reverse
    angle never shows them missing). Judges: "extras' shoulders block subjects", "a yellow sleeve fills the frame"."""
    import roblox_record as RR
    fr = dict(np.load(ep_dir / "frames.npz"))
    dyn = json.loads((ep_dir / "dynamic.json").read_text())
    pose = fr["pose"]
    acts = dyn["actors"]
    real = {n: a.get("alias_of", n) for n, a in acts.items()}
    groups = {}
    for n, a in acts.items():
        groups.setdefault(real[n], []).extend(range(a["first"] - 1, a["last"]))
    torso = {}
    for n, a in acts.items():
        ti = next((i for i in range(a["first"] - 1, a["last"]) if dyn["parts"][i]["name"] == "Torso"), None)
        if ti is not None:
            torso.setdefault(real[n], []).append(ti)
    # episode props are cleared like extras (a potted plant or a rope post the writer placed in front of a face)
    for i, d in enumerate(dyn["parts"]):
        o = d.get("owner") or ""
        if o.startswith("prop:"):
            groups.setdefault(o, []).append(i)
            torso.setdefault(o, [i])
    hidden = 0
    n_frames = min(len(cams), len(pose))
    for k in range(n_frames):
        t = k / fps
        _i, c = RR._cue_at(shots, t)
        keep = {real.get(x, x) for x in ((c.subject, c.with_) if c.subject else ()) if x}
        if c.prop:
            keep.add("prop:" + c.prop)
        if c.subjects:
            keep |= {real.get(x, x) for x in c.subjects}
        pos, look, fov = cams[k, :3].astype(float), cams[k, 3:6].astype(float), float(cams[k, 6])
        fwd = look - pos
        fwd /= np.linalg.norm(fwd) + 1e-9
        right = np.cross(fwd, [0.0, 1.0, 0.0])
        right /= np.linalg.norm(right) + 1e-9
        up = np.cross(right, fwd)
        th = np.tan(np.radians(fov) / 2)
        subj_d = [float((pose[k, torso[x][0], :3] - pos) @ fwd) for x in keep if x in torso and pose[k, torso[x][0], 1] > -500]
        lim = min(subj_d) * 0.82 if subj_d else float(np.linalg.norm(look - pos)) * 0.6
        for n, tis in torso.items():
            if n in keep:
                continue
            tp = pose[k, tis[0], :3].astype(float)
            if tp[1] < -500:
                continue
            v = tp - pos
            d = float(v @ fwd)
            if d <= 0.3:
                continue
            u, w = float(v @ right) / (d * th * 9 / 16), float(v @ up) / (d * th)
            near_lens = d < 2.6 and abs(u) < 1.6 and abs(w) < 1.6
            if near_lens or (d < lim and abs(u) < 1.25 and abs(w) < 1.4):
                ii = groups.get(n, [])
                pose[k, ii, 1] -= 2000.0
                hidden += 1
    fr["pose"] = pose
    np.savez(ep_dir / "frames.npz", **fr)
    return hidden


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
    if os.environ.get("PROMPTIMATE_CLEAR_FG", "1") != "0":
        nh = clear_foreground(ep_dir, shots, perf, cams, fps, t_end)
        log(f"foreground cleared: {nh} actor-frames hidden")
    T["plan"] = time.time() - t
    log(f"offline plan: {len(shots)} shots, {T['plan']:.1f}s")
    t = time.time()
    out = out or (ep_dir / f"{name}.mp4")
    rr = RD.render_parallel(ep_dir, cams, out, fps, workers=workers, ass=ass, fonts=fonts, wav=wav)
    T["render"] = time.time() - t
    log(f"offline render: {rr}")
    return {"mp4": str(out), "timing": {k: round(v, 1) for k, v in T.items()}, "render": rr, "notes": notes}
