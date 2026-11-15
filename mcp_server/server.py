"""Promptimate MCP server (id: kimodo-motion): local text-to-motion with kimodo.cpp (Vulkan) for a Claude client.

Run:  .venv\\Scripts\\python.exe mcp_server\\server.py
Claude acts as the director (it plans segments); Kimodo generates the motion.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from mcp.server.fastmcp import FastMCP, Image  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import constraints as C  # noqa: E402
import hands  # noqa: E402
import intent  # noqa: E402
import metrics  # noqa: E402
import motion  # noqa: E402
import postprocess  # noqa: E402
import render  # noqa: E402
import selection  # noqa: E402
import unity_validate  # noqa: E402
from kimodo_worker import KimodoWorker, Segment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
DEFAULT_STEPS = int(os.environ.get("KIMODO_STEPS", "30"))
DEFAULT_TEXT_CFG = float(os.environ.get("KIMODO_TEXT_CFG", "2.0"))
DEFAULT_TAKES = int(os.environ.get("KIMODO_TAKES", "3"))

PROMPT_GUIDE = (
    "Prompt style (matches the captions Kimodo was trained on): one person, present tense, plain physical "
    "description of the body, starting with 'a person ...'. Name the body part and side ('waves with their right "
    "hand'), the direction ('walks forward', 'turns left', 'steps backward') and the manner ('slowly', 'energetically', "
    "'like a zombie'). Describe what the body does, not story, objects or scenery: 'a person sits down on the floor' "
    "works, 'a man sits on a chair in a cafe' does not. One or two actions per segment; for a sequence use several "
    "segments (2-10 s each) and they are blended. Moods work as manner ('a person walks sadly with their head down')."
)

mcp = FastMCP("kimodo-motion", instructions=(
    "Local text-to-motion (NVIDIA Kimodo SOMA via kimodo.cpp on the user's GPU). " + PROMPT_GUIDE + " "
    "Control beyond text: root_path pins where the character's hips go (metres; +Z = the direction the character "
    "starts facing, +X = the character's left), e.g. walk 3 m forward then stop = [{t:0,x:0,z:0},{t:3,x:0,z:3},"
    "{t:5,x:0,z:3}]; loop=true makes a seamless cycle (walks, runs, idles); in_place=true removes travel. "
    "takes=N generates N variations in one call and auto-picks the cleanest; look at the takes sheet and call "
    "use_take if another one matches the prompt better. Always look at the returned preview (front/side views, "
    "top-down path, height and foot-contact timeline) and judge whether the motion matches the request; regenerate "
    "with another seed or a reworded prompt if not. 'checks' are fast automatic sanity checks; if they fail, "
    "regenerate. Clips are cleaned automatically (feet locked to the ground, no floor penetration). "
    "Clips that must fit together: start_pose/end_pose='idle' starts/ends the clip in the same neutral standing pose "
    "every time. Use it on both ends for a set of game clips an Animator switches between (wave, attack, emote, "
    "start/stop walking all returning to one shared idle). continue_from=<earlier motion name> starts the clip in "
    "that clip's last pose and keeps its momentum, for a shot list or combo played back to back (walk in -> stop -> "
    "talk -> leave). Leave both off for one-off clips, and don't combine them with loop. Every clip still starts at "
    "the origin facing +Z; Apply Root Motion carries position and turning across chained clips. "
    "Speed: a few seconds per clip once warm. The models start loading in the background when this server starts "
    "(about 1 min from a slow disk), so the first call may wait for that."
))
# All instances (one per Claude session) share one warm engine through motiond; MOTIOND=0 runs a private engine.
if os.environ.get("MOTIOND", "1") == "0":
    worker = KimodoWorker()
else:
    from motiond import RemoteWorker
    worker = RemoteWorker()
# Unity project that receives .kimodo files (imported as Humanoid clips by com.promptimate.unity).
UNITY_PROJECT = Path(os.environ.get("UNITY_PROJECT", ROOT / "unity" / "PromptimateSandbox"))
_bg_lock = threading.Lock()


def _preload() -> None:  # matplotlib's first import costs seconds from an HDD; pay it while the user types
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot  # noqa: F401
    except Exception:
        pass


threading.Thread(target=_preload, daemon=True).start()


class MotionSegment(BaseModel):
    prompt: str = Field(description="Motion description, e.g. 'a person jogs forward then stops'")
    seconds: float = Field(default=5.0, ge=0.5, le=10.0, description="Segment duration in seconds (30 fps)")


class Waypoint(BaseModel):
    t: float = Field(description="Time in seconds from the clip start")
    x: float = Field(description="Metres, + = the character's initial left")
    z: float = Field(description="Metres, + = the character's initial facing direction")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "motion"


def _score(m: dict, chk: dict) -> float:
    """Lower is better: automatic check failures dominate, then glitches, foot skating, floating and jerk."""
    return (10.0 * len(chk["failures"]) + 2.0 * m.get("pop_frames", 0) + 0.15 * m.get("skate_speed_cms", 0)
            + 5.0 * m.get("float_ratio", 0) + 0.004 * m.get("jerk_p95", 0) + 0.5 * m.get("penetration_max_cm", 0))


_STATIONARY = re.compile(r"\b(stops?|stopping|stands? still|standing still|in place|on the spot|stationary|"
                         r"without moving)\b", re.I)
_THEN_STOP = re.compile(r"\bthen (stops?|stands? still|comes to a stop)\b", re.I)
_LOCOMOTION = re.compile(r"\b(walks?|walking|jogs?|jogging|runs?|running|steps?|moves?|crawls?|skips?|"
                         r"sprints?|marches?|strolls?|turns? around|forward|backward|sideways)\b", re.I)


def _auto_holds(segs) -> list[tuple[int, int]]:
    """Frame ranges where the text says the character is stationary, so the hips get held still:
    a later segment that says it stops / stays in place (from 0.5 s in), the end part of 'X then stops' (last 40 %),
    and later segments without locomotion words that follow a stationary one."""
    holds, start, still = [], 0, False
    for i, s in enumerate(segs):
        end = start + s.frames
        p = s.prompt
        if _THEN_STOP.search(p):
            holds.append((start + int(0.6 * s.frames), end - 1))
            still = True
        elif i and _STATIONARY.search(p) and not _LOCOMOTION.search(_STATIONARY.sub("", p)):
            holds.append((start + 15, end - 1))  # a clip that starts stationary doesn't drift; no hold needed
            still = True
        elif still and not _LOCOMOTION.search(p):
            holds.append((start, end - 1))
        else:
            still = False
        start = end
    merged: list[tuple[int, int]] = []
    for a, b in holds:  # merge adjacent ranges
        if merged and a <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def _bg(fn, *args) -> None:
    def run():
        try:
            fn(*args)
        except Exception as e:  # background work must never take the server down
            print(f"background task failed: {type(e).__name__}: {e}", file=sys.stderr)
    threading.Thread(target=run, daemon=True).start()


def _update_meta(out_dir: Path, **fields) -> None:
    with _bg_lock:
        p = out_dir / "meta.json"
        meta = json.loads(p.read_text())
        meta.update(fields)
        p.write_text(json.dumps(meta, indent=2))


def _export_bg(out_dir: Path) -> None:
    files = motion.export(out_dir)
    _update_meta(out_dir, exports=files)


def _unity_bg(out_dir: Path, asset: Path) -> None:
    _update_meta(out_dir, unity_validation={"pending": True})
    try:
        res = _unity_summary(unity_validate.validate([asset]))
    except Exception as e:
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    _update_meta(out_dir, unity_validation=res)


def _finish(out_dir: Path, name: str, prompt_text: str, root, rot, *, loop: bool, in_place: bool,
            segs=None) -> dict:
    """Write final raw files + .kimodo for the chosen take; returns file paths."""
    postprocess.save(out_dir, root, rot)
    motion.write_skeleton_json(out_dir)
    extra = {"loop": loop, "inPlace": in_place}
    if segs:
        # finger poses inferred from the text (point, fist, wave, clap, grip), timed to the gesture; rigs without
        # finger bones ignore them. Segment frames are rescaled if the clip was retimed.
        scale = len(root) / max(1, sum(s.frames for s in segs))
        hs = [(s.prompt, max(1, round(s.frames * scale))) for s in segs]
        extra["handPoses"] = hands.hand_poses(hs, pos=motion.fk(root, rot), frames=len(root))
    if (UNITY_PROJECT / "Assets").is_dir():
        target = UNITY_PROJECT / "Assets" / "Promptimate" / "Generated" / f"{name}.kimodo"
        files = {"unity_asset": str(motion.write_kimodo_file(out_dir, target, prompt_text, extra))}
    else:
        files = {"kimodo": str(motion.write_kimodo_file(out_dir, out_dir / f"{name}.kimodo", prompt_text, extra))}
    files.update({"glb": str(out_dir / "animation.glb"), "bvh": str(out_dir / "animation.bvh"),
                  "raw_dir": str(out_dir), "preview": str(out_dir / "preview.png")})
    return files


POSES = {"free", "idle"}
CONTINUE_OVERLAP = 5  # continue_from: the previous clip's last 5 frames condition the start (pose + velocity)


def _hold_frames(continue_from: str | None) -> int:
    """Frames snapped exactly at the start: a short still hold for a canonical pose; a continuation snaps only
    frame 0 so the motion carries on instead of pausing."""
    return 1 if continue_from else C.POSE_WINDOW


def _continue_context(continue_from: str, n: int) -> np.ndarray:
    """Feature rows of the previous clip's last n frames, re-based so the first of them is at the origin facing +Z
    (the model always starts its clip there; pinning frame 0 anywhere else fights it)."""
    root, rot = motion.load(OUTPUT / continue_from)
    n = min(n, len(root))
    x, z, h = C.frame_placement(root, rot, len(root) - n)
    r, q = C.rebase(root[-n:], rot[-n:], x, z, h)
    feat = C.features(r, q)
    return np.concatenate([np.repeat(feat[:1], n - len(feat), axis=0), feat]) if len(feat) < n else feat


def _trim_lead_in(d: Path, n: int) -> None:
    """Drop the first n frames of a take's engine output (the continue_from lead-in)."""
    root, rot = motion.load(d)
    postprocess.save(d, root[n:], rot[n:])
    cf = d / "foot_contacts.f32"
    if cf.exists():
        c = np.fromfile(cf, dtype="<f4").reshape(len(root), -1)
        np.ascontiguousarray(c[n:]).tofile(cf)


def _start_target(start_pose: str, continue_from: str | None):
    """Start pose (root, rot) in the new clip's canonical space (origin, facing +Z), and for continue_from the
    previous clip's end placement (x, z, heading) in that clip's own space."""
    if continue_from:
        d = OUTPUT / continue_from
        if not (d / "meta.json").exists() or not (d / "root_positions.f32").exists():
            raise ValueError(f"unknown motion {continue_from!r} for continue_from; call list_motions")
        root, rot = motion.load(d)  # the final (post-processed) clip, as it plays in Unity
        x, z, h = C.frame_placement(root, rot, len(root) - 1)
        return C.rebase(root[-1], rot[-1], x, z, h), (x, z, h)
    if start_pose != "free":
        return C.load_pose(start_pose), None
    return None, None


def _apply_pins(root, rot, start_pose, end_pose, continue_from, *, in_place=False):
    """After post-processing: make the pinned start/end frames exactly the target pose (foot locking and grounding
    move legs and hips a little), and work out where a continued clip sits in its chain.
    Returns (root, rot, pins_info, chain)."""
    pins, chain = {}, None
    target, prev_end = _start_target(start_pose, continue_from)
    # Each pin is placed where the clip's own feet are (fit_placement), so snapping reshapes the body without
    # sliding planted feet; a pinned start is then moved rigidly so it begins exactly at the origin facing +Z.
    if target is not None:
        if in_place:
            root, rot, info = C.snap_pose(root, rot, target, "start", hold=_hold_frames(continue_from))
        else:
            x, z, h = C.fit_placement(root, rot, 0, target)
            root, rot, info = C.snap_pose(root, rot, C.transform(*target, x, z, h), "start",
                                          hold=_hold_frames(continue_from), xz=True)
            root, rot = C.rebase(root, rot, x, z, h)
        pins["start"] = {"pose": "continue" if continue_from else start_pose, "frames": info["frames"],
                         "distance_before_snap": info["before"], "distance_after": info["after"]}
    if end_pose != "free":
        target = C.load_pose(end_pose)
        if in_place:
            x, z, h = C.frame_placement(root, rot, len(root) - 1)
        else:
            x, z, h = C.fit_placement(root, rot, len(root) - 1, target)
        root, rot, info = C.snap_pose(root, rot, C.transform(*target, x, z, h), "end", xz=not in_place)
        pins["end"] = {"pose": end_pose, "frames": info["frames"], "distance_before_snap": info["before"],
                       "distance_after": info["after"]}
    if continue_from:
        x, z, h = prev_end
        try:
            pw = json.loads((OUTPUT / continue_from / "meta.json").read_text()).get("chain", {}).get("world_start")
        except Exception:
            pw = None
        pw = pw or {"x": 0.0, "z": 0.0, "heading_deg": 0.0}
        a = np.radians(pw["heading_deg"])
        wx = pw["x"] + np.cos(a) * x + np.sin(a) * z  # same rotation convention as constraints.transform
        wz = pw["z"] - np.sin(a) * x + np.cos(a) * z
        chain = {"previous": continue_from,
                 "start_in_previous": {"x": round(x, 4), "z": round(z, 4), "heading_deg": round(np.degrees(h), 2)},
                 "world_start": {"x": round(float(wx), 4), "z": round(float(wz), 4),
                                 "heading_deg": round(pw["heading_deg"] + float(np.degrees(h)), 2)},
                 "note": "re-based to start at the origin facing +Z; with Apply Root Motion (or Timeline 'match "
                         "offsets') it carries on from the previous clip. world_start = where it begins in the "
                         "first clip's space."}
    return root, rot, pins, chain


@mcp.tool()
def generate_motion(segments: list[MotionSegment], name: str | None = None, seed: int = 0,
                    steps: int = DEFAULT_STEPS, transition_frames: int = 10, text_cfg: float | None = None,
                    takes: int = DEFAULT_TAKES, clean: bool = True, loop: bool = False, in_place: bool = False,
                    root_path: list[Waypoint] | None = None, auto_stop: bool = True,
                    start_pose: str = "free", end_pose: str = "free", continue_from: str | None = None,
                    speed: float = 1.0, unity_check: str = "background") -> list:
    """Generate a humanoid motion clip from one or more text segments (played in order, blended).

    Returns stats, automatic checks, output paths (.kimodo dropped into the Unity project, imported as a Humanoid
    AnimationClip; GLB/BVH written in the background) and a preview image.
    steps: diffusion steps (10-100). seed: change it for a different take. text_cfg: how strongly to follow the
    text (default ~2; higher = more literal but can get stiff). takes: generate N variations (seeds seed..seed+N-1)
    and keep the cleanest. clean: lock feet to the ground and remove floor penetration. loop: seamless cycle.
    in_place: remove horizontal travel. root_path: waypoints pinning the hips' ground position over time.
    auto_stop: when a segment says the character stops / stands still / stays in place, actually hold the hips
    there (a second constrained pass; the model alone often keeps drifting).
    start_pose / end_pose: "free" (default; the model picks) or "idle" (the same neutral standing pose every time,
    held for a few frames). Use "idle" on both ends for game clips that an Animator blends between (idle -> wave ->
    idle, starts and stops). end_pose="idle" costs a second pass per take.
    continue_from: name of an earlier motion; this clip starts exactly in its last pose (seamless chaining for a
    shot list or a combo). Each clip still starts at the origin facing +Z; meta "chain" says where it sits in the
    first clip's space. Can't be combined with start_pose="idle" or loop.
    speed: playback speed of the result (0.5-2.0). The model tops out around 3 m/s, so for a sprint use the run
    prompt with speed 1.3-1.5; for slow motion use 0.5-0.8. The clip keeps the requested duration.
    unity_check: "background" (default; result lands in meta.json, see get_motion_preview), "sync" or "off".
    """
    if not segments:
        raise ValueError("need at least one segment")
    steps = max(1, min(int(steps), 200))
    takes = max(1, min(int(takes), 6))
    speed = float(speed)
    if not 0.5 <= speed <= 2.0:
        raise ValueError("speed must be between 0.5 and 2.0")
    if speed != 1.0 and (loop or continue_from or root_path):
        raise ValueError("speed can't be combined with loop, continue_from or root_path yet")
    # wording the model follows measurably better (intent.rewrite); the user's prompt is kept in the meta
    given = [s.prompt.strip() for s in segments]
    segs = [Segment(intent.rewrite(p), max(2, min(300, round(s.seconds * speed * motion.FPS))))
            for p, s in zip(given, segments)]
    if len(segs) > 1 and any(s.frames <= transition_frames for s in segs[1:]):
        raise ValueError("every segment after the first must be longer than transition_frames")
    frames = sum(s.frames for s in segs)
    name = _slug(name or segs[0].prompt) + time.strftime("_%Y%m%d_%H%M%S")
    prompt_text = " | ".join(s.prompt for s in segs)
    cfg = DEFAULT_TEXT_CFG if text_cfg is None else float(text_cfg)
    start_pose, end_pose = (start_pose or "free").lower(), (end_pose or "free").lower()
    for v in (start_pose, end_pose):
        if v not in POSES:
            raise ValueError(f"start_pose/end_pose must be one of {sorted(POSES)}, got {v!r}")
    if continue_from and start_pose != "free":
        raise ValueError("continue_from already sets the start pose; leave start_pose='free'")
    if loop and (continue_from or start_pose != "free" or end_pose != "free"):
        raise ValueError("loop=true already makes the clip end in its start pose; it can't also use "
                         "start_pose/end_pose/continue_from")
    start_target, _ = _start_target(start_pose, continue_from)
    out_dir = OUTPUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    # continue_from: the engine also generates `pre` lead-in frames pinned to the previous clip's last frames (so
    # the new motion picks up its velocity, not just its pose); they're cut off again after generation.
    pre = CONTINUE_OVERLAP - 1 if continue_from else 0
    if segs[0].frames + pre > 300:  # stay within the engine's 10 s segment limit
        segs[0] = Segment(segs[0].prompt, 300 - pre)
        frames = sum(s.frames for s in segs)
    gen_segs = [Segment(s.prompt, s.frames + (pre if i == 0 else 0)) for i, s in enumerate(segs)]
    gframes = frames + pre
    cons = None
    if root_path:
        cons = C.Constraints(gframes).root_path([(w.t + pre / motion.FPS, w.x, w.z) for w in root_path])
    if start_target is not None:
        cons = cons if cons is not None else C.Constraints(gframes)
        if continue_from:
            for t, row in enumerate(_continue_context(continue_from, pre + 1)):
                cons.pose(t, row)
        else:
            feat = C.pose_features(*start_target)
            for t in range(min(C.POSE_WINDOW, gframes)):
                cons.pose(t, feat)
    boundaries = list(np.cumsum([s.frames for s in segs])[:-1]) if len(segs) > 1 else None

    holds = _auto_holds(gen_segs) if auto_stop and not root_path and not in_place else []

    t0 = time.time()
    results = []
    for k in range(takes):
        d = out_dir / f"take{k}"
        cfile = cons.save(d / "constraints.bin") if cons is not None else None
        info = worker.generate(gen_segs, d, steps=steps, seed=seed + k, transition=transition_frames,
                               text_cfg=cfg, constraints=cfile)
        if loop or holds or end_pose != "free":
            # pass 2, same seed: hold the hips still where the text says the character stops (at the spot the
            # free pass reached), pin the last frame to the first frame's pose (offset by the travel) for loops,
            # and/or pin the end pose.
            r0, q0 = motion.load(d)
            c2 = cons.copy() if cons is not None else C.Constraints(gframes)
            for h0, h1 in holds:
                c2.hold_still(h0, h1, float(r0[h0, 0]), float(r0[h0, 2]))
            if loop:
                feat = C.features(r0, q0)
                end = feat[0].copy()
                end[[0, 2]] += (r0[-1] - r0[0])[[0, 2]]
                c2.pose(0, feat[0]).pose(gframes - 1, end)
            if end_pose != "free":
                # the end pose turned to the heading pass 1 ended with, held still where pass 1 stopped
                ex, ez, eh = C.frame_placement(r0, q0, gframes - 1)
                if c2.mask[gframes - 1, 0]:  # an auto-stop hold or root_path already says where it ends
                    ex, ez = float(c2.observed[gframes - 1, 0]), float(c2.observed[gframes - 1, 2])
                feat = C.pose_features(*C.transform(*C.load_pose(end_pose), ex, ez, eh))
                for t in range(max(0, gframes - C.POSE_WINDOW), gframes):
                    held = (float(c2.observed[t, 0]), float(c2.observed[t, 2])) if c2.mask[t, 0] else (ex, ez)
                    c2.pose(t, feat, root_xz=False)
                    c2.root_xz(t, *held)
            info2 = worker.generate(gen_segs, d, steps=steps, seed=seed + k, transition=transition_frames,
                                    text_cfg=cfg, constraints=c2.save(d / "constraints_pass2.bin"))
            info["seconds"] = round(info["seconds"] + info2["seconds"], 2)
            info["passes"] = 2
            if holds:
                info["auto_holds_s"] = [[round((a - pre) / motion.FPS, 2), round((b - pre) / motion.FPS, 2)]
                                        for a, b in holds]
        if pre:
            _trim_lead_in(d, pre)
            info["frames"] = info.get("frames", gframes) - pre
            info["lead_in_frames"] = pre
        root, rot = motion.load(d)
        pos = motion.fk(root, rot)
        chk = motion.checks(pos, prompt_text)
        m = metrics.compute(pos=pos, boundaries=boundaries)
        results.append({"take": k, "seed": seed + k, "dir": d, "info": info, "checks": chk, "metrics": m,
                        "pos": pos})
    # pick the take that does what the prompt asks (prompt-derived checks, late starts, too-still takes) with real
    # defects as tie-breakers; see selection.py
    selection.score_takes(results, [(s.prompt, s.frames) for s in segs], prompt_text)
    for r in results:
        r.pop("pos", None)
    best = min(results, key=lambda r: r["score"])
    gen_seconds = round(time.time() - t0, 2)

    meta = _assemble(out_dir, name, segs, prompt_text, best, results, seed=seed, steps=steps, cfg=cfg,
                     transition_frames=transition_frames, clean=clean, loop=loop, in_place=in_place,
                     root_path=[w.model_dump() for w in root_path] if root_path else None, unity_check=unity_check,
                     start_pose=start_pose, end_pose=end_pose, continue_from=continue_from, speed=speed)
    meta["generation"]["total_gen_seconds"] = gen_seconds
    if any(g != s.prompt for g, s in zip(given, segs)):
        meta["prompts_as_given"] = given
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    images = [Image(path=str(out_dir / "preview.png"))]
    if takes > 1:
        sheet = render.render_takes_sheet([motion.fk(*motion.load(r["dir"])) for r in results],
                                          out_dir / "takes.png",
                                          [f"take {r['take']} (seed {r['seed']}) score {r['score']}" +
                                           (" <- chosen" if r is best else "") for r in results])
        images.append(Image(path=str(sheet)))
    return [json.dumps(meta, indent=2), *images]


def _assemble(out_dir: Path, name: str, segs, prompt_text: str, best: dict, results: list, *, seed, steps, cfg,
              transition_frames, clean, loop, in_place, root_path, unity_check, start_pose="free", end_pose="free",
              continue_from=None, speed=1.0) -> dict:
    """Post-process the chosen take, write all outputs, start background export/validation, return meta."""
    d = best["dir"]
    root, rot = motion.load(d)
    contacts = postprocess.load_contacts(d)
    pp = {}
    if speed != 1.0:
        root, rot = postprocess.retime(root, rot, speed)
        contacts = None  # engine contacts are per generated frame; the heuristic re-detects on the retimed clip
        pp["speed"] = speed
    if loop:
        root, rot, li = postprocess.make_loop(root, rot, window=(0, len(root) - 1) if len(root) > 2 else None,
                                              foot_lock=clean, contacts=contacts)
        pp["loop"] = {k: li[k] for k in ("frames", "seconds", "seam_before", "seam_after", "loop_offset_xz_m")
                      if k in li}
    elif clean:
        root, rot, ci = postprocess.clean(root, rot, contacts=contacts,
                                          segment_boundaries=[round(b / speed) for b in np.cumsum([s.frames for s in segs])[:-1]])
        pp["clean"] = {k: ci[k] for k in ("ground_offset_m", "before", "after") if k in ci}
    if in_place:
        root, rot = postprocess.make_in_place(root, rot)[:2]
    root, rot, pins, chain = _apply_pins(root, rot, start_pose, end_pose, continue_from, in_place=in_place)
    if pins:
        pp["pose_pins"] = pins
    files = _finish(out_dir, name, prompt_text, root, rot, loop=loop, in_place=in_place, segs=segs)
    pos = motion.fk(root, rot)
    render.render_judge_sheet(pos, out_dir / "preview.png", prompt_text)
    st = motion.stats(pos)
    chk = motion.checks(pos, prompt_text, in_place=in_place)
    final_metrics = {k: v for k, v in metrics.compute(pos=pos).items()
                     if k in ("skate_speed_cms", "penetration_max_cm", "float_ratio", "jerk_p95", "pop_frames",
                              "root_end_speed_ms", "root_travel_m", "heading_change_deg")}
    meta = {"name": name, "segments": [s.__dict__ for s in segs], "seed": best["seed"], "steps": steps,
            "text_cfg": cfg, "transition_frames": transition_frames, "options": {
                "clean": clean, "loop": loop, "in_place": in_place, "root_path": root_path, "speed": speed,
                "start_pose": start_pose, "end_pose": end_pose, "continue_from": continue_from},
            "generation": best["info"], "stats": st, "checks": chk, "metrics": final_metrics, "postprocess": pp,
            "files": files}
    if chain:
        meta["chain"] = chain
    if len(results) > 1:
        meta["takes"] = [{"take": r["take"], "seed": r["seed"], "score": r["score"], "why": r.get("score_parts"),
                          "checks_passed": r["checks"]["passed"], "dir": str(r["dir"])} for r in results]
        meta["chosen_take"] = best["take"]
    asset = Path(files.get("unity_asset") or files["kimodo"])
    unity = None
    if unity_check == "sync":
        try:
            unity = _unity_summary(unity_validate.validate([asset]))
        except Exception as e:  # validation problems must not lose the generated motion
            unity = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    elif unity_check == "background":
        unity = {"pending": True, "note": "running in the background; see get_motion_preview"}
    meta["unity_validation"] = unity
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    _bg(_export_bg, out_dir)
    if unity_check == "background":
        _bg(_unity_bg, out_dir, asset)
    return meta


def _unity_summary(res: dict) -> dict:
    out = {"ok": res["exit_code"] == 0 and res["clips"] > 0, "seconds": res["seconds"],
           "compile_errors": res["compile_errors"], "self_test": res.get("self_test") or None}
    out["clips"] = [{"asset": Path(r["asset"]).stem, "passed": r["passed"], "failures": r["failures"],
                     "ref_pos_err_m": round(r.get("refPosErrMaxM", -1), 4),
                     "other_rig_bone_dir_err_deg": round(r.get("boneDirErrMeanDeg", -1), 1)}
                    for r in res["reports"]]
    if not res["reports"]:
        out["error"] = f"no reports; see {res['log']}"
    return out


@mcp.tool()
def use_take(name: str, take: int) -> list:
    """Switch a multi-take result to another take (re-runs post-processing and rewrites the Unity asset)."""
    out_dir = OUTPUT / name
    meta = json.loads((out_dir / "meta.json").read_text())
    if "takes" not in meta:
        raise ValueError("this motion has a single take")
    tk = next((t for t in meta["takes"] if t["take"] == take), None)
    if tk is None:
        raise ValueError(f"take must be one of {[t['take'] for t in meta['takes']]}")
    segs = [Segment(s["prompt"], s["frames"]) for s in meta["segments"]]
    d = Path(tk["dir"])
    root, rot = motion.load(d)
    pos = motion.fk(root, rot)
    prompt_text = " | ".join(s.prompt for s in segs)
    best = {"take": take, "seed": tk["seed"], "dir": d, "info": meta["generation"],
            "checks": motion.checks(pos, prompt_text), "metrics": {}, "score": tk["score"]}
    opts = meta["options"]
    new = _assemble(out_dir, name, segs, prompt_text, best, [best, best], seed=tk["seed"], steps=meta["steps"],
                    cfg=meta["text_cfg"], transition_frames=meta["transition_frames"], clean=opts["clean"],
                    loop=opts["loop"], in_place=opts["in_place"], root_path=opts["root_path"],
                    unity_check="background", start_pose=opts.get("start_pose", "free"),
                    end_pose=opts.get("end_pose", "free"), continue_from=opts.get("continue_from"),
                    speed=opts.get("speed", 1.0))
    new["takes"], new["chosen_take"] = meta["takes"], take
    if "prompts_as_given" in meta:
        new["prompts_as_given"] = meta["prompts_as_given"]
    (out_dir / "meta.json").write_text(json.dumps(new, indent=2))
    return [json.dumps(new, indent=2), Image(path=str(out_dir / "preview.png"))]


@mcp.tool()
def validate_in_unity(names: list[str] | None = None, self_test: bool = False) -> str:
    """Re-run headless Unity validation for generated motions (default: the 5 newest).
    self_test=true also runs negative controls (deliberately broken conversions must fail)."""
    metas = sorted(OUTPUT.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if names:
        metas = [OUTPUT / n / "meta.json" for n in names]
    files = []
    for m in metas[: (len(metas) if names else 5)]:
        f = json.loads(m.read_text())["files"]
        files.append(Path(f.get("unity_asset") or f["kimodo"]))
    return json.dumps(_unity_summary(unity_validate.validate(files, self_test=self_test)), indent=2)


@mcp.tool()
def list_motions(limit: int = 20) -> str:
    """List previously generated motions (newest first) with prompts and durations."""
    rows = []
    for meta in sorted(OUTPUT.glob("*/meta.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        m = json.loads(meta.read_text())
        rows.append({"name": m["name"], "prompts": [s["prompt"] for s in m["segments"]],
                     "duration_s": m["stats"]["duration_s"], "seed": m["seed"]})
    return json.dumps(rows, indent=2)


@mcp.tool()
def get_motion_preview(name: str) -> list:
    """Return the stored metadata (including background Unity validation and export results) and preview image."""
    d = OUTPUT / name
    if not (d / "meta.json").exists():
        raise ValueError(f"unknown motion {name!r}; call list_motions")
    return [(d / "meta.json").read_text(), Image(path=str(d / "preview.png"))]


_prewarm_state: dict = {"state": "off"}


def _warm(w) -> dict:
    try:
        return w.warm()
    except RuntimeError as e:
        if "unknown op" not in str(e):
            raise
        # an older motiond without the warm op: an uncached tiny generation loads the models just the same
        from motiond import RemoteWorker
        RemoteWorker(cache=False).generate([Segment("a person stands still", 30)], ROOT / ".cache" / "warm",
                                           steps=1, seed=0)
        return {"warmed": True}


def _prewarm() -> None:
    """Load the engine in the background as soon as the server starts (models come off an HDD in 40 s - 2 min), so
    it is usually ready by Claude's first generate_motion call. Uses its own daemon connection, so nothing waits on
    it except a generation that would have had to load the models anyway. PROMPTIMATE_PREWARM=0 turns it off."""
    _prewarm_state.update(state="running", started_at=time.time())
    try:
        if os.environ.get("MOTIOND", "1") == "0":
            res = worker.warm()
        else:
            from motiond import RemoteWorker
            res = _warm(RemoteWorker())
        _prewarm_state.update(state="done", **res, finished_at=time.time())
    except Exception as e:  # never take the server down; the first real call will load (and report) instead
        _prewarm_state.update(state="failed", error=f"{type(e).__name__}: {e}")
        print(f"prewarm failed: {type(e).__name__}: {e}", file=sys.stderr)


@mcp.tool()
def worker_status(warm_up: bool = False) -> str:
    """Show whether the GPU worker is loaded. The server already starts loading it in the background at startup;
    warm_up=true waits until it's loaded (about 1 min cold)."""
    if warm_up and not worker.alive():
        _warm(worker)
    st = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in _prewarm_state.items()
          if k not in ("started_at", "finished_at")}
    if "started_at" in _prewarm_state:
        st["elapsed_s"] = round(_prewarm_state.get("finished_at", time.time()) - _prewarm_state["started_at"], 1)
    return json.dumps({"loaded": worker.alive(), "text_quant": worker.text_quant, "engine": str(worker.engine_dir),
                       "uptime_s": round(time.time() - worker.started_at, 1) if worker.alive() else None,
                       "prewarm": st})


if __name__ == "__main__":
    if os.environ.get("PROMPTIMATE_PREWARM", "1") != "0":
        threading.Thread(target=_prewarm, daemon=True, name="prewarm").start()
    try:
        mcp.run()
    finally:
        worker.stop()
