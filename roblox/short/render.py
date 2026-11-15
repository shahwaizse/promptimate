"""Deterministic frame-by-frame render of one version of the short in Roblox Studio (through Studio's MCP server).

    .venv\\Scripts\\python.exe roblox\\short\\render.py A|B|C [--start s] [--end s] [--every n] [--draft] [--force]

Per frame: Python computes every character's pose instructions (perf.py) -> ShortDirector.apply in Studio (Run mode,
so AnimationConstraint joints solve) -> camera from the shot list -> 3 pitched screen_captures -> stitched to 1080x1920
(stitch.py). Frames go to .cache/roblox_short/frames/<V>/f00000.png (resumable: existing frames are skipped), then
ffmpeg makes .cache/roblox_short/<V>_full.mp4. --draft = one capture per frame, center crop upscaled (quick looks).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "roblox" / "tools"))
sys.path.insert(0, str(ROOT / "mcp_server"))
os.environ.setdefault("UNITY_PROJECT", str(ROOT / ".cache" / "no_unity_project"))
import perf  # noqa: E402
import stitch  # noqa: E402
import story as S  # noqa: E402
from studio_mcp import StudioSession  # noqa: E402
from validate_in_studio import _long  # noqa: E402

CACHE = ROOT / ".cache" / "roblox_short"
FFMPEG = r"D:\tools\ffmpeg\bin\ffmpeg.exe"


def cast_json() -> str:
    return json.dumps({w: {"height": c["height"], "width": c["width"], "colors": c["colors"],
                                         "hat": c.get("hat")} for w, c in S.CAST.items()})


async def upload(s, version: str):
    """PromptimatePlayer + ShortDirector (+ B's clips) into ReplicatedStorage.Promptimate; director kept in _G."""
    import roblox
    mods = {"PromptimatePlayer": (ROOT / "roblox" / "PromptimatePlayer.lua").read_text(encoding="utf-8"),
            "ShortDirector": (HERE / "ShortDirector.lua").read_text(encoding="utf-8")}
    if version == "B":
        chains = json.loads(Path(os.environ.get("RS_CHAINS", CACHE / "b_chains.json")).read_text())["chars"]
        for clips in chains.values():
            for c in clips:
                name = "rs_" + c["key"]
                mods[name] = roblox.export_luau(Path(c["raw_dir"]), ROOT / "roblox" / "out" / f"{name}.lua", name).read_text(encoding="utf-8")
    # ModuleScript.Source is capped at 200,000 characters: long clips go into chunk modules joined by the main one
    for name in [n for n, s in mods.items() if n.startswith("rs_") and len(s) > 190_000]:
        body = json.dumps(json.loads((ROOT / "roblox" / "out" / f"{name}.json").read_text()), separators=(",", ":"))
        parts = [body[i:i + 150_000] for i in range(0, len(body), 150_000)]
        for k, part in enumerate(parts):
            mods[f"{name}__{k + 1}"] = f"return {_long(part)}\n"
        mods[name] = ("local F = game:GetService('ReplicatedStorage').Promptimate\nreturn "
                      + " .. ".join(f"require(F[{json.dumps(f'{name}__{k + 1}')}])" for k in range(len(parts))) + "\n")
    for name, src in mods.items():
        code = ('local RS = game:GetService("ReplicatedStorage")\n'
                'local folder = RS:FindFirstChild("Promptimate") or Instance.new("Folder")\n'
                'folder.Name = "Promptimate"; folder.Parent = RS\n'
                f'local m = folder:FindFirstChild({json.dumps(name)}) or Instance.new("ModuleScript")\n'
                f'm.Name = {json.dumps(name)}; m.Source = {_long(src)}; m.Parent = folder\nreturn #m.Source')
        r = await s.luau(code)
        if r["isError"]:
            raise RuntimeError(f"upload {name}: {r}")


async def setup(s, version: str) -> dict:
    await upload(s, version)
    code = ('local RS = game:GetService("RunService"); if not RS:IsRunning() then RS:Run() end\n'
            'local D = require(game:GetService("ReplicatedStorage").Promptimate.ShortDirector:Clone())\n'
            '_G.ShortDirector = D\n'
            f'return D.setup({_long(cast_json())})')
    r = await s.luau(code)
    if r["isError"]:
        raise RuntimeError(r)
    return json.loads(r["content"][0])


async def apply(s, inst: dict) -> str:
    r = await s.luau(f"return _G.ShortDirector.apply({_long(json.dumps(inst, separators=(',', ':')))})")
    if r["isError"]:
        raise RuntimeError(r["content"])
    return r["content"][0]


def camera(chars, t):
    sid, a, b, cam, _ = S.shot_at(t)
    if "track" in cam:
        pts = [perf.frame({cam["track"]: chars[cam["track"]]}, min(max(t + d, a), b))[1][cam["track"]]
               for d in np.linspace(-0.35, 0.35, 7)]
        h = np.mean(pts, axis=0)
        pos = h + np.array(cam["offset"])
        look = h + np.array(cam["aim"])
    else:
        pos, look = np.array(cam["pos"], float), np.array(cam["look"], float)
    return sid, pos, look, cam["fov"]


async def capture(s, cid, pos, look) -> Image.Image:
    for attempt in range(3):
        c = await s.call("screen_capture", {"capture_id": cid, "camera_position": [float(v) for v in pos],
                                            "look_at_position": [float(v) for v in look]})
        for x in c["content"]:
            if isinstance(x, dict) and x.get("data"):
                return Image.open(io.BytesIO(base64.b64decode(x["data"]))).convert("RGB")
        await asyncio.sleep(1)
    raise RuntimeError(f"screen_capture failed: {c}")


async def render(version: str, t_start: float, t_end: float, every: int, draft: bool, force: bool, tag: str = ""):
    out_dir = CACHE / "frames" / (version + tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = {"version": version, "frames": 0, "skipped": 0, "t_setup": 0, "t_apply": 0, "t_capture": 0}
    pool = ThreadPoolExecutor(2)
    pending = []
    t_all = time.time()
    async with StudioSession() as s:
        await asyncio.sleep(3)
        t0 = time.time()
        setup_info = await setup(s, version)
        stats["t_setup"] = round(time.time() - t0, 1)
        stats["setup"] = setup_info
        chars = perf.build(version, setup_info)
        vp = json.loads((await s.luau("local v = workspace.CurrentCamera.ViewportSize; return string.format('[%d,%d]', v.X, v.Y)"))["content"][0])
        stats["viewport"] = vp
        cur_fov = None
        n0, n1 = int(round(t_start * S.FPS)), int(math.floor(t_end * S.FPS - 1e-6))
        for i in range(n0, n1 + 1, every):
            path = out_dir / f"f{i:05d}.png"
            if path.exists() and not force:
                stats["skipped"] += 1
                continue
            t = i / S.FPS
            inst, hips = perf.frame(chars, t)
            ta = time.time()
            await apply(s, inst)
            stats["t_apply"] += time.time() - ta
            sid, pos, look, fov = camera(chars, t)
            rows = stitch.plan(pos, look, fov, S.SIZE, tuple(vp), density=(vp[1] / S.SIZE[1]) if draft else 1.0)
            imgs = []
            tc = time.time()
            for k, row in enumerate(rows):
                if cur_fov is None or abs(row["fov"] - cur_fov) > 1e-3:
                    await s.luau(f"workspace.CurrentCamera.FieldOfView = {row['fov']:.5f}; return 1")
                    cur_fov = row["fov"]
                imgs.append(await capture(s, f"{version}_{i}_{k}", pos, row["look"]))
            stats["t_capture"] += time.time() - tc
            pending.append(pool.submit(lambda im=imgs, rw=rows, p=path: stitch.blend(im, rw, S.SIZE).save(p)))
            stats["frames"] += 1
            if stats["frames"] % 24 == 0:
                el = time.time() - t_all
                print(f"{version} frame {i} t={t:.2f} {sid} rows={len(rows)} {el / stats['frames']:.2f}s/frame", flush=True)
        for p in pending:
            p.result()
    stats["wall_s"] = round(time.time() - t_all, 1)
    stats["t_apply"] = round(stats["t_apply"], 1)
    stats["t_capture"] = round(stats["t_capture"], 1)
    log = CACHE / f"render_{version}{tag}.json"
    hist = json.loads(log.read_text()) if log.exists() else []
    hist.append(stats)
    log.write_text(json.dumps(hist, indent=1))
    print(json.dumps(stats), flush=True)
    return out_dir


def encode(version: str, tag: str = ""):
    d = CACHE / "frames" / (version + tag)
    out = CACHE / f"{version}{tag}_full.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-framerate", str(S.FPS), "-i", str(d / "f%05d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium", str(out)], check=True)
    print("encoded", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("version", choices=["A", "B", "C"])
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=S.END)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--encode", action="store_true")
    a = ap.parse_args()
    tag = a.tag or ("_draft" if a.draft else "")
    asyncio.run(render(a.version, a.start, a.end, a.every, a.draft, a.force, tag))
    if a.encode:
        encode(a.version, tag)
