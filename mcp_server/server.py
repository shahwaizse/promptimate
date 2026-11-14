"""Promptimate MCP server (id: kimodo-motion): local text-to-motion with kimodo.cpp (Vulkan) for a Claude client.

Run:  .venv\\Scripts\\python.exe mcp_server\\server.py
Claude acts as the director (it plans segments); Kimodo generates the motion.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP, Image  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import motion  # noqa: E402
import unity_validate  # noqa: E402
from kimodo_worker import KimodoWorker, Segment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
mcp = FastMCP("kimodo-motion", instructions=(
    "Local text-to-motion (NVIDIA Kimodo SOMA via kimodo.cpp on the user's GPU). "
    "Write prompts the way motion-capture captions are written: one person, plain physical description, "
    "present tense, e.g. 'a person walks forward and waves with their right hand'. "
    "Each segment is 2-10 s; chain segments for longer action, transitions are blended. "
    "Always look at the returned preview image and stats to judge the result and regenerate with a "
    "different seed or reworded prompt if it is wrong. Every result carries automatic checks: 'checks' (fast, "
    "Python) and 'unity_validation' (headless Unity bake + replay on two humanoids). If either reports failures, "
    "say so and regenerate rather than handing the clip over. Generation takes roughly 0.6 s per diffusion step "
    "on this GPU (default 30 steps), plus ~1-2 min model load on the first call."
))
worker = KimodoWorker()
# Unity project that receives .kimodo files (imported as Humanoid clips by com.promptimate.unity).
UNITY_PROJECT = Path(os.environ.get("UNITY_PROJECT", ROOT / "unity" / "PromptimateSandbox"))


class MotionSegment(BaseModel):
    prompt: str = Field(description="Motion description, e.g. 'a person jogs forward then stops'")
    seconds: float = Field(default=5.0, ge=0.5, le=10.0, description="Segment duration in seconds (30 fps)")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "motion"


@mcp.tool()
def generate_motion(segments: list[MotionSegment], name: str | None = None, seed: int = 0,
                    steps: int = 30, transition_frames: int = 5, unity_check: bool = True) -> list:
    """Generate a humanoid motion clip from one or more text segments (played in order, blended).

    Returns stats, output file paths (GLB, BVH, raw .f32 + skeleton.json, and a .kimodo file dropped into the
    Unity project, which imports as a Humanoid AnimationClip) and a preview contact sheet image.
    steps: diffusion steps (10-100; more = slower, usually smoother). seed: change it to get a different take.
    unity_check: also bake + verify the clip in headless Unity (~10 s): checks facing, left/right, feet, and
    retargeting onto a second differently-proportioned humanoid. "checks" holds the fast Python-side results.
    """
    if not segments:
        raise ValueError("need at least one segment")
    steps = max(1, min(int(steps), 200))
    segs = [Segment(s.prompt.strip(), max(2, min(300, round(s.seconds * motion.FPS)))) for s in segments]
    if len(segs) > 1 and any(s.frames <= transition_frames for s in segs[1:]):
        raise ValueError("every segment after the first must be longer than transition_frames")
    name = _slug(name or segs[0].prompt) + time.strftime("_%Y%m%d_%H%M%S")
    out_dir = OUTPUT / name
    info = worker.generate(segs, out_dir, steps=steps, seed=seed, transition=transition_frames)
    root, rot = motion.load(out_dir)
    pos = motion.fk(root, rot)
    st = motion.stats(pos)
    png = motion.render_preview(pos, out_dir / "preview.png", " | ".join(s.prompt for s in segs))
    files = motion.export(out_dir)
    motion.write_skeleton_json(out_dir)
    prompt_text = " | ".join(s.prompt for s in segs)
    if (UNITY_PROJECT / "Assets").is_dir():
        files["unity_asset"] = str(motion.write_kimodo_file(
            out_dir, UNITY_PROJECT / "Assets" / "Promptimate" / "Generated" / f"{name}.kimodo", prompt_text))
    else:
        files["kimodo"] = str(motion.write_kimodo_file(out_dir, out_dir / f"{name}.kimodo", prompt_text))
    chk = motion.checks(pos, prompt_text)
    unity = None
    if unity_check:
        try:
            unity = _unity_summary(unity_validate.validate([Path(files.get("unity_asset") or files["kimodo"])]))
        except Exception as e:  # validation problems must not lose the generated motion
            unity = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    meta = {"name": name, "segments": [s.__dict__ for s in segs], "seed": seed, "steps": steps,
            "transition_frames": transition_frames, "generation": info, "stats": st, "checks": chk,
            "unity_validation": unity,
            "files": {**files, "raw_dir": str(out_dir), "preview": str(png)}}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return [json.dumps(meta, indent=2), Image(path=str(png))]


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
    """Return the stored metadata and preview image of a generated motion."""
    d = OUTPUT / name
    if not (d / "meta.json").exists():
        raise ValueError(f"unknown motion {name!r}; call list_motions")
    return [(d / "meta.json").read_text(), Image(path=str(d / "preview.png"))]


@mcp.tool()
def worker_status(warm_up: bool = False) -> str:
    """Show whether the GPU worker is loaded. warm_up=true loads the models now (takes 1-2 min cold)."""
    if warm_up and not worker.alive():
        worker.generate([Segment("a person stands still", 30)], OUTPUT / "_warmup", steps=1, seed=0)
    return json.dumps({"loaded": worker.alive(), "text_quant": worker.text_quant,
                       "uptime_s": round(time.time() - worker.started_at, 1) if worker.alive() else None})


if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        worker.stop()
