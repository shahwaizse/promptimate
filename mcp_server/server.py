"""Promptimate MCP server (id: kimodo-motion): local text-to-motion with kimodo.cpp (Vulkan) for a Claude client.

Run:  .venv\\Scripts\\python.exe mcp_server\\server.py
Claude acts as the director (it plans segments); Kimodo generates the motion.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
from mcp.server.fastmcp import FastMCP, Image  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import constraints as C  # noqa: E402
import metrics  # noqa: E402
import motion  # noqa: E402
import postprocess  # noqa: E402
import render  # noqa: E402
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
    "Speed on an 8 GB RX 6600 XT: ~8 s for a 5 s clip at 30 steps once warm, plus ~1 min model load on the first call."
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


def _finish(out_dir: Path, name: str, prompt_text: str, root, rot, *, loop: bool, in_place: bool) -> dict:
    """Write final raw files + .kimodo for the chosen take; returns file paths."""
    postprocess.save(out_dir, root, rot)
    motion.write_skeleton_json(out_dir)
    extra = {"loop": loop, "inPlace": in_place}
    if (UNITY_PROJECT / "Assets").is_dir():
        target = UNITY_PROJECT / "Assets" / "Promptimate" / "Generated" / f"{name}.kimodo"
        files = {"unity_asset": str(motion.write_kimodo_file(out_dir, target, prompt_text, extra))}
    else:
        files = {"kimodo": str(motion.write_kimodo_file(out_dir, out_dir / f"{name}.kimodo", prompt_text, extra))}
    files.update({"glb": str(out_dir / "animation.glb"), "bvh": str(out_dir / "animation.bvh"),
                  "raw_dir": str(out_dir), "preview": str(out_dir / "preview.png")})
    return files


@mcp.tool()
def generate_motion(segments: list[MotionSegment], name: str | None = None, seed: int = 0,
                    steps: int = DEFAULT_STEPS, transition_frames: int = 5, text_cfg: float | None = None,
                    takes: int = DEFAULT_TAKES, clean: bool = True, loop: bool = False, in_place: bool = False,
                    root_path: list[Waypoint] | None = None, auto_stop: bool = True,
                    unity_check: str = "background") -> list:
    """Generate a humanoid motion clip from one or more text segments (played in order, blended).

    Returns stats, automatic checks, output paths (.kimodo dropped into the Unity project, imported as a Humanoid
    AnimationClip; GLB/BVH written in the background) and a preview image.
    steps: diffusion steps (10-100). seed: change it for a different take. text_cfg: how strongly to follow the
    text (default ~2; higher = more literal but can get stiff). takes: generate N variations (seeds seed..seed+N-1)
    and keep the cleanest. clean: lock feet to the ground and remove floor penetration. loop: seamless cycle.
    in_place: remove horizontal travel. root_path: waypoints pinning the hips' ground position over time.
    auto_stop: when a segment says the character stops / stands still / stays in place, actually hold the hips
    there (a second constrained pass; the model alone often keeps drifting).
    unity_check: "background" (default; result lands in meta.json, see get_motion_preview), "sync" or "off".
    """
    if not segments:
        raise ValueError("need at least one segment")
    steps = max(1, min(int(steps), 200))
    takes = max(1, min(int(takes), 6))
    segs = [Segment(s.prompt.strip(), max(2, min(300, round(s.seconds * motion.FPS)))) for s in segments]
    if len(segs) > 1 and any(s.frames <= transition_frames for s in segs[1:]):
        raise ValueError("every segment after the first must be longer than transition_frames")
    frames = sum(s.frames for s in segs)
    name = _slug(name or segs[0].prompt) + time.strftime("_%Y%m%d_%H%M%S")
    out_dir = OUTPUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_text = " | ".join(s.prompt for s in segs)
    cfg = DEFAULT_TEXT_CFG if text_cfg is None else float(text_cfg)
    cons = None
    if root_path:
        cons = C.Constraints(frames).root_path([(w.t, w.x, w.z) for w in root_path])
    boundaries = list(np.cumsum([s.frames for s in segs])[:-1]) if len(segs) > 1 else None

    holds = _auto_holds(segs) if auto_stop and not root_path and not in_place else []

    t0 = time.time()
    results = []
    for k in range(takes):
        d = out_dir / f"take{k}"
        cfile = cons.save(d / "constraints.bin") if cons is not None else None
        info = worker.generate(segs, d, steps=steps, seed=seed + k, transition=transition_frames,
                               text_cfg=cfg, constraints=cfile)
        if loop or holds:
            # pass 2, same seed: hold the hips still where the text says the character stops (at the spot the
            # free pass reached), and/or pin the last frame to the first frame's pose (offset by the travel).
            r0, q0 = motion.load(d)
            c2 = cons.copy() if cons is not None else C.Constraints(frames)
            for h0, h1 in holds:
                c2.hold_still(h0, h1, float(r0[h0, 0]), float(r0[h0, 2]))
            if loop:
                feat = C.features(r0, q0)
                end = feat[0].copy()
                end[[0, 2]] += (r0[-1] - r0[0])[[0, 2]]
                c2.pose(0, feat[0]).pose(frames - 1, end)
            info2 = worker.generate(segs, d, steps=steps, seed=seed + k, transition=transition_frames,
                                    text_cfg=cfg, constraints=c2.save(d / "constraints_pass2.bin"))
            info["seconds"] = round(info["seconds"] + info2["seconds"], 2)
            info["passes"] = 2
            if holds:
                info["auto_holds_s"] = [[round(a / motion.FPS, 2), round(b / motion.FPS, 2)] for a, b in holds]
        root, rot = motion.load(d)
        pos = motion.fk(root, rot)
        chk = motion.checks(pos, prompt_text)
        m = metrics.compute(pos=pos, boundaries=boundaries)
        results.append({"take": k, "seed": seed + k, "dir": d, "info": info, "checks": chk, "metrics": m,
                        "score": round(_score(m, chk), 3)})
    best = min(results, key=lambda r: r["score"])
    gen_seconds = round(time.time() - t0, 2)

    meta = _assemble(out_dir, name, segs, prompt_text, best, results, seed=seed, steps=steps, cfg=cfg,
                     transition_frames=transition_frames, clean=clean, loop=loop, in_place=in_place,
                     root_path=[w.model_dump() for w in root_path] if root_path else None, unity_check=unity_check)
    meta["generation"]["total_gen_seconds"] = gen_seconds
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
              transition_frames, clean, loop, in_place, root_path, unity_check) -> dict:
    """Post-process the chosen take, write all outputs, start background export/validation, return meta."""
    d = best["dir"]
    root, rot = motion.load(d)
    contacts = postprocess.load_contacts(d)
    pp = {}
    if loop:
        root, rot, li = postprocess.make_loop(root, rot, window=(0, len(root) - 1) if len(root) > 2 else None,
                                              foot_lock=clean, contacts=contacts)
        pp["loop"] = {k: li[k] for k in ("frames", "seconds", "seam_before", "seam_after", "loop_offset_xz_m")
                      if k in li}
    elif clean:
        root, rot, ci = postprocess.clean(root, rot, contacts=contacts,
                                          segment_boundaries=list(np.cumsum([s.frames for s in segs])[:-1]))
        pp["clean"] = {k: ci[k] for k in ("ground_offset_m", "before", "after") if k in ci}
    if in_place:
        root, rot = postprocess.make_in_place(root, rot)[:2]
    files = _finish(out_dir, name, prompt_text, root, rot, loop=loop, in_place=in_place)
    pos = motion.fk(root, rot)
    render.render_judge_sheet(pos, out_dir / "preview.png", prompt_text)
    st = motion.stats(pos)
    chk = motion.checks(pos, prompt_text, in_place=in_place)
    final_metrics = {k: v for k, v in metrics.compute(pos=pos).items()
                     if k in ("skate_speed_cms", "penetration_max_cm", "float_ratio", "jerk_p95", "pop_frames",
                              "root_end_speed_ms", "root_travel_m", "heading_change_deg")}
    meta = {"name": name, "segments": [s.__dict__ for s in segs], "seed": best["seed"], "steps": steps,
            "text_cfg": cfg, "transition_frames": transition_frames, "options": {
                "clean": clean, "loop": loop, "in_place": in_place, "root_path": root_path},
            "generation": best["info"], "stats": st, "checks": chk, "metrics": final_metrics, "postprocess": pp,
            "files": files}
    if len(results) > 1:
        meta["takes"] = [{"take": r["take"], "seed": r["seed"], "score": r["score"],
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
                    unity_check="background")
    new["takes"], new["chosen_take"] = meta["takes"], take
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


@mcp.tool()
def worker_status(warm_up: bool = False) -> str:
    """Show whether the GPU worker is loaded. warm_up=true loads the models now (takes ~1 min cold)."""
    if warm_up and not worker.alive():
        shutil.rmtree(OUTPUT / "_warmup", ignore_errors=True)
        worker.generate([Segment("a person stands still", 30)], OUTPUT / "_warmup", steps=1, seed=0)
    return json.dumps({"loaded": worker.alive(), "text_quant": worker.text_quant, "engine": str(worker.engine_dir),
                       "uptime_s": round(time.time() - worker.started_at, 1) if worker.alive() else None})


if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        worker.stop()
