r"""Generates the Promptimate clips the text-to-ragdoll demo plays, through the shared motiond worker.

    .venv\Scripts\python demo\ragdoll\gen_clips.py [names...]

Each clip lands as <key>.kimodo in unity/SystemLab/Assets/Promptimate/Generated/ (stable names, so the Unity side can
load them by key) and the preview sheet is copied to demo/ragdoll/build/previews/ for review.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "unity" / "SystemLab"
os.environ.setdefault("TEMP", r"D:\tmp")
os.environ.setdefault("TMP", r"D:\tmp")
os.environ["UNITY_PROJECT"] = str(LAB)
os.environ.setdefault("PROMPTIMATE_PREWARM", "0")
sys.path.insert(0, str(ROOT / "mcp_server"))

# key -> generate_motion arguments. Personality shows up twice: in the clip the text asks for (how the body moves)
# and in the physics parameters (how it reacts), see personality.py.
CLIPS: dict[str, dict] = {
    "walk": dict(segments=[{"prompt": "a person walks forward", "seconds": 9}]),
    "walk_old": dict(segments=[{"prompt": "an old person walks forward slowly, hunched over", "seconds": 9}]),
    "walk_drunk": dict(segments=[{"prompt": "a drunk person walks forward, swaying from side to side", "seconds": 9}]),
    "idle": dict(segments=[{"prompt": "a person stands still and looks around", "seconds": 9}]),
    "stance_fighter": dict(segments=[{"prompt": "a person stands in a boxing stance with their guard up, bouncing lightly", "seconds": 9}]),
    "getup_back": dict(segments=[{"prompt": "a person lies on their back on the ground, then gets up and stands", "seconds": 6}], takes=2),
    "getup_front": dict(segments=[{"prompt": "a person lies face down on the ground, then pushes up with their arms and stands up", "seconds": 6}], takes=2),
    "stand_idle": dict(segments=[{"prompt": "a person stands still", "seconds": 6}]),
}


def gen(key: str) -> dict:
    import server  # noqa: E402  (env must be set first)
    spec = CLIPS[key]
    segs = [server.MotionSegment(**s) for s in spec["segments"]]
    kw = {k: v for k, v in spec.items() if k != "segments"}
    kw.setdefault("takes", int(os.environ.get("RAGDOLL_TAKES", "1")))
    res = server.generate_motion(segs, name=key, unity_check="off", **kw)
    gen_dir = LAB / "Assets" / "Promptimate" / "Generated"
    # the newest <key>_<timestamp>.kimodo the server just dropped; renamed to a stable <key>.kimodo for Unity
    found = sorted(gen_dir.glob(f"{key}_2*.kimodo"), key=lambda p: p.stat().st_mtime)
    src = found[-1] if found else Path("")
    raw = server.OUTPUT / src.stem if found else None
    files = {"raw_dir": str(raw) if raw else None, "preview": str(raw / "preview.png") if raw else None}
    info = {"checks": "see " + files["preview"] if raw else "no clip found"}
    if src.is_file():
        dst = gen_dir / f"{key}.kimodo"
        if dst.exists():
            dst.unlink()
        src.rename(dst)
        meta = src.with_suffix(".kimodo.meta")
        if meta.exists():
            meta.unlink()
    prev = ROOT / "demo" / "ragdoll" / "build" / "previews"
    prev.mkdir(parents=True, exist_ok=True)
    if files.get("preview") and Path(files["preview"]).exists():
        shutil.copy(files["preview"], prev / f"{key}.png")
    for c in res:
        if getattr(c, "type", "") == "image" and getattr(c, "data", None):
            (prev / f"{key}_sheet.png").write_bytes(base64.b64decode(c.data))
            break
    print(key, "->", files.get("raw_dir"), "| checks:", json.dumps(info.get("checks", ""))[:300], flush=True)
    return info


if __name__ == "__main__":
    keys = sys.argv[1:] or list(CLIPS)
    for k in keys:
        gen(k)
