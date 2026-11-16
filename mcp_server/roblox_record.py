"""roblox_record: film the performance in the open Roblox Studio place as a vertical (9:16) video, frame by frame.

Per frame: ShortDirector.seek(t) poses every character deterministically -> camera from the cue list -> pitched
`screen_capture`s stitched into the 9:16 frame (roblox/short/stitch.py: Studio's viewport is landscape and capture
resets camera roll, so a tall frame is assembled from exact rotation homographies). Before rendering, camera checks
run at the start/middle/end of every shot (camera inside or clipping a prop/body, subjects hidden or out of frame)
and a sheet with one draft frame per shot is returned, so the agent sees the framing before the long render.

Realtime fallback: press Play in Studio (PromptimateAutoplay runs the director) and screen-record the window (OBS,
Win+Alt+R). For vertical, the Ovra-style trick of rolling the camera 90 degrees and rotating the recording works.
"""
from __future__ import annotations

import base64
import io
import json
import math
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

import motion
from roblox_studio import long_str, studio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "roblox" / "short"))
import stitch  # noqa: E402

STATE = ROOT / ".cache" / "roblox_perform"
SRV = None
JOBS: dict[str, dict] = {}


class CameraCue(BaseModel):
    start: float = Field(description="Story time (s) this shot starts; it lasts until the next cue's start")
    pos: list[float] | None = Field(None, description="Camera position [x, y, z] studs (static shot)")
    look: list[float] | None = Field(None, description="Point the camera looks at [x, y, z]")
    track: str | None = Field(None, description="Follow this character: camera = its hips + offset, aimed at hips + aim")
    offset: list[float] | None = Field(None, description="track: camera offset from the hips [dx, dy, dz] studs")
    aim: list[float] | None = Field(None, description="track: look-at offset from the hips (default [0, 1, 0])")
    fov: float = Field(50.0, description="Vertical field of view of the 9:16 frame (deg)")
    subjects: list[str] | None = Field(None, description="Characters that must be visible (default: the tracked one, "
                                                         "else everyone in frame). [] = no visibility checks")
    name: str | None = Field(None, description="Label used in warnings")


# ------------------------------------------------------------------------------------------- performance (Python)
class Perf:
    """Hips positions of every character over story time, from the clips roblox_perform generated."""

    def __init__(self):
        p = STATE / "state.json"
        st = json.loads(p.read_text()) if p.exists() else {"actors": {}}
        self.actors = {}
        import roblox_tools as RT
        for name, a in st["actors"].items():
            segs = []
            for c in a["clips"]:
                root, _ = motion.load(SRV.OUTPUT / c["src"])
                hips = RT.world_hips(root, (c["x"], c["z"]), c["yaw"], a["spm"])
                y = c.get("y", 0.0) + root[:, 1] * a["spm"]
                segs.append((c["s"], np.column_stack([hips[:, 0], y, hips[:, 1]])))
            self.actors[name] = segs

    def hips(self, name: str, t: float) -> np.ndarray | None:
        segs = self.actors.get(name)
        if not segs:
            return None
        k = 0
        for i, (s, _) in enumerate(segs):
            if s <= t + 1e-6:
                k = i
        s, h = segs[k]
        f = min(max((t - s) * motion.FPS, 0), len(h) - 1)
        i0 = int(f)
        i1 = min(i0 + 1, len(h) - 1)
        a = f - i0
        return h[i0] * (1 - a) + h[i1] * a

    def end(self) -> float:
        return max((segs[-1][0] + (len(segs[-1][1]) - 1) / motion.FPS for segs in self.actors.values()), default=0.0)


def _cue_at(cues: list[CameraCue], t: float) -> tuple[int, CameraCue]:
    k = 0
    for i, c in enumerate(cues):
        if c.start <= t + 1e-6:
            k = i
    return k, cues[k]


def camera(cues, perf: Perf, t: float):
    k, c = _cue_at(cues, t)
    if c.track:
        hs = [perf.hips(c.track, t + d) for d in np.linspace(-0.35, 0.35, 7)]
        hs = [h for h in hs if h is not None]
        if not hs:
            raise ValueError(f"camera tracks '{c.track}', which has no performance")
        h = np.mean(hs, axis=0)
        pos = h + np.array(c.offset or [0, 2, 10], float)
        look = h + np.array(c.aim or [0, 1, 0], float)
    else:
        if c.pos is None or c.look is None:
            raise ValueError(f"shot {k + 1}: give pos and look, or track")
        pos, look = np.array(c.pos, float), np.array(c.look, float)
    return k, c, pos, look, c.fov


def _project(pos, look, fov, size, p) -> tuple[float, float, float]:
    """World point -> (u, v) in [0,1] of the 9:16 frame and depth."""
    r, u, f = stitch._basis(pos, look)
    v = np.asarray(p, float) - pos
    z = v @ f
    if z <= 1e-3:
        return -1.0, -1.0, z
    th = math.tan(math.radians(fov) / 2)
    aspect = size[0] / size[1]
    x = (v @ r) / (z * th * aspect)
    y = (v @ u) / (z * th)
    return 0.5 + x / 2, 0.5 - y / 2, z


# ------------------------------------------------------------------------------------------------ checks + sheet
CAM_LUAU = r'''
local HttpService = game:GetService("HttpService")
local D = _G.PromptimateDirector or require(game:GetService("ReplicatedStorage").Promptimate.ShortDirector:Clone())
_G.PromptimateDirector = D
local jobs = HttpService:JSONDecode(__JOBS__)
local out = {}
for i, j in jobs do out[i] = HttpService:JSONDecode(D.camcheck(j.t, j.cams)) end
return HttpService:JSONEncode(out)
'''


def check_cameras(cues: list[CameraCue], perf: Perf, size, t_end: float) -> tuple[list[str], list[dict]]:
    names = list(perf.actors)
    jobs, meta = [], []
    for k, c in enumerate(cues):
        a = c.start
        b = cues[k + 1].start if k + 1 < len(cues) else t_end
        for t in sorted({round(a + 0.05, 3), round((a + b) / 2, 3), round(max(a, b - 0.08), 3)}):
            _, _, pos, look, fov = camera(cues, perf, t)
            if c.subjects is not None:
                subs = list(c.subjects)
            elif c.track:
                subs = [c.track]
            else:
                subs = []
                for n in names:
                    h = perf.hips(n, t)
                    if h is None:
                        continue
                    u, v, z = _project(pos, look, fov, size, h)
                    if 0.05 < u < 0.95 and 0.05 < v < 0.95 and 0 < z < 60:
                        subs.append(n)
            jobs.append({"t": t, "cams": [{"pos": pos.tolist(), "look": look.tolist(), "subjects": subs, "r": 0.5}]})
            meta.append({"shot": k, "t": t, "pos": pos, "look": look, "fov": fov, "auto": c.subjects is None and not c.track})
    res = []
    for i in range(0, len(jobs), 12):
        res += studio().luau_json(CAM_LUAU.replace("__JOBS__", long_str(json.dumps(jobs[i:i + 12]))))
    warns, seen = [], set()
    for m, r in zip(meta, res):
        r = r[0]
        c = cues[m["shot"]]
        label = c.name or f"shot {m['shot'] + 1}"
        for n in r.get("near", []):
            key = (m["shot"], "near", n)
            if key not in seen:
                seen.add(key)
                warns.append(f"{label} @{m['t']:.1f}s: camera is inside/clipping {n}")
        for n, s in (r.get("subjects") or {}).items():
            if s["blocked"] >= 2:
                key = (m["shot"], "hid", n)
                if key not in seen:
                    seen.add(key)
                    warns.append(f"{label} @{m['t']:.1f}s: {n} hidden behind {', '.join(s['by'][:2])}")
            uh, vh, zh = _project(m["pos"], m["look"], m["fov"], size, s["head"])
            uf, vf, zf = _project(m["pos"], m["look"], m["fov"], size, s["foot"])
            out_h = not (0 <= uh <= 1 and 0 <= vh <= 1)
            out_f = not (0 <= uf <= 1 and 0 <= vf <= 1)
            if (out_h and out_f) and not m["auto"]:
                key = (m["shot"], "out", n)
                if key not in seen:
                    seen.add(key)
                    warns.append(f"{label} @{m['t']:.1f}s: {n} is out of frame")
            elif out_h and not m["auto"] and vh < 0:
                key = (m["shot"], "head", n)
                if key not in seen:
                    seen.add(key)
                    warns.append(f"{label} @{m['t']:.1f}s: {n}'s head is cut off at the top")
    return warns, meta


def _capture(cid, pos, look) -> "Image":
    from PIL import Image
    st = studio()
    last = None
    for _ in range(3):
        c = st.call("screen_capture", {"capture_id": cid, "camera_position": [float(v) for v in pos],
                                       "look_at_position": [float(v) for v in look]})
        last = c
        for x in c["content"]:
            if isinstance(x, dict) and x.get("data"):
                return Image.open(io.BytesIO(base64.b64decode(x["data"]))).convert("RGB")
        time.sleep(1)
    raise RuntimeError(f"screen_capture failed: {str(last)[:300]}")


def _viewport() -> tuple[int, int]:
    return tuple(json.loads(studio().luau(
        "local v = workspace.CurrentCamera.ViewportSize; return string.format('[%d,%d]', v.X, v.Y)")))


def _ensure_running():
    studio().luau('local RS = game:GetService("RunService"); if not RS:IsRunning() then RS:Run() end; '
                  'local D = require(game:GetService("ReplicatedStorage").Promptimate.ShortDirector:Clone()); '
                  '_G.PromptimateDirector = D; D.load(); return 1')


def frame(cues, perf, t, size, vp, draft, cid, state):
    st = studio()
    st.luau(f"_G.PromptimateDirector.seek({t:.4f}); task.wait(); task.wait(); return 1")
    k, c, pos, look, fov = camera(cues, perf, t)
    rows = stitch.plan(pos, look, fov, size, vp, density=(vp[1] / size[1]) if draft else 1.0)
    imgs = []
    for i, row in enumerate(rows):
        if state.get("fov") is None or abs(row["fov"] - state["fov"]) > 1e-3:
            st.luau(f"workspace.CurrentCamera.FieldOfView = {row['fov']:.5f}; return 1")
            state["fov"] = row["fov"]
        imgs.append(_capture(f"{cid}_{i}", pos, row["look"]))
    return imgs, rows


def shot_sheet(cues, perf, size, t_end, out: Path) -> Path:
    from PIL import Image, ImageDraw
    vp = _viewport()
    state = {}
    thumbs = []
    for k, c in enumerate(cues):
        b = cues[k + 1].start if k + 1 < len(cues) else t_end
        t = (c.start + b) / 2
        imgs, rows = frame(cues, perf, t, size, vp, True, f"sheet_{k}_{uuid.uuid4().hex[:6]}", state)
        im = stitch.blend(imgs, rows, size).resize((135, 240))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, 135, 14], fill=(0, 0, 0))
        d.text((3, 1), f"{k + 1} {c.name or ''} {t:.1f}s"[:24], fill=(255, 255, 255))
        thumbs.append(im)
    cols = min(8, len(thumbs))
    rows_n = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * 135, rows_n * 240), (20, 20, 20))
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % cols) * 135, (i // cols) * 240))
    sheet.save(out)
    return out


# ---------------------------------------------------------------------------------------------------- rendering
def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or r"D:\tools\ffmpeg\bin\ffmpeg.exe"


def _heavy(who: str):
    """Machine-wide lock for heavy jobs (scripts/heavy_lock.py) when this checkout has it: long frame-by-frame
    renders and ffmpeg encodes take turns with other heavy work on the machine."""
    import contextlib
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from heavy_lock import heavy
        return heavy(who)
    except Exception:
        return contextlib.nullcontext()


def _render_job(job: dict, cues, perf, size, fps, t0, t1, draft):
    job["state"] = "waiting for the machine's heavy-job lock"
    with _heavy(f"roblox: record {Path(job['mp4']).name}"):
        job["state"] = "rendering"
        _render_job_locked(job, cues, perf, size, fps, t0, t1, draft)


def _render_job_locked(job: dict, cues, perf, size, fps, t0, t1, draft):
    try:
        out_dir = Path(job["frames_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        # frames on disk are reused to resume an interrupted render, but only for the same performance, package,
        # cameras and size: re-recording after a new roblox_perform must not reuse stale frames
        import hashlib
        import roblox_tools as RT
        sig = hashlib.sha1(json.dumps({
            "state": (STATE / "state.json").read_text() if (STATE / "state.json").exists() else "",
            "pkg": RT._pkg_version(), "cues": [c.model_dump() if hasattr(c, "model_dump") else c for c in cues],
            "size": list(size), "fps": fps, "t": [t0, t1], "draft": draft}, sort_keys=True, default=str).encode()).hexdigest()
        sig_file = out_dir / "signature.txt"
        if not sig_file.exists() or sig_file.read_text().strip() != sig:
            for f in out_dir.glob("f*.png"):
                f.unlink()
            sig_file.write_text(sig)
        _ensure_running()
        vp = _viewport()
        state = {}
        pool = ThreadPoolExecutor(2)
        pending = []
        n0, n1 = int(round(t0 * fps)), int(math.floor(t1 * fps - 1e-6))
        job["total"] = n1 - n0 + 1
        t_start = time.time()
        for i in range(n0, n1 + 1):
            if job.get("cancel"):
                job["state"] = "cancelled"
                return
            path = out_dir / f"f{i - n0:05d}.png"
            if not path.exists():
                imgs, rows = frame(cues, perf, i / fps, size, vp, draft, f"r{job['id']}_{i}", state)
                pending.append(pool.submit(lambda im=imgs, rw=rows, p=path: stitch.blend(im, rw, size).save(p)))
            job["done"] = i - n0 + 1
            el = time.time() - t_start
            job["eta_s"] = round(el / job["done"] * (job["total"] - job["done"]))
        for p in pending:
            p.result()
        mp4 = Path(job["mp4"])
        cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(out_dir / "f%05d.png")]
        if job.get("audio"):
            cmd += ["-i", job["audio"], "-shortest", "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-preset", "medium", str(mp4)]
        subprocess.run(cmd, check=True)
        # 4-frame contact sheet
        from PIL import Image
        files = sorted(out_dir.glob("f*.png"))
        picks = [files[int(k * (len(files) - 1) / 3)] for k in range(4)] if files else []
        sheet = Image.new("RGB", (4 * 180, 320))
        for k, f in enumerate(picks):
            sheet.paste(Image.open(f).resize((180, 320)), (k * 180, 0))
        sheet.save(job["sheet"])
        job["state"] = "done"
        job["render_s"] = round(time.time() - t_start, 1)
    except Exception as e:  # report through the job status
        job["state"] = "failed"
        job["error"] = f"{type(e).__name__}: {e}"[:500]


def record(shots: list[CameraCue], start: float = 0.0, end: float | None = None, fps: int = 24,
           size: tuple[int, int] = (1080, 1920), quality: str = "final", name: str = "short",
           check_only: bool = False, sheet: bool = True, audio: str | None = None, job: str | None = None) -> list:
    from mcp.server.fastmcp import Image
    if job:
        j = JOBS.get(job)
        if not j:
            return [json.dumps({"error": f"unknown job {job}"})]
        if j["state"] == "done":
            return [json.dumps({"state": "done", "mp4": j["mp4"], "frames": j["frames_dir"], "render_s": j["render_s"]}),
                    Image(path=j["sheet"])]
        return [json.dumps({k: j.get(k) for k in ("state", "done", "total", "eta_s", "error") if j.get(k) is not None})]
    if not shots:
        raise ValueError("give at least one camera cue")
    shots = sorted(shots, key=lambda c: c.start)
    perf = Perf()
    if not perf.actors:
        raise ValueError("no performance yet: call roblox_perform first")
    t_end = end if end is not None else perf.end()
    _ensure_running()
    warns, _ = check_cameras(shots, perf, size, t_end)
    out = {"shots": len(shots), "seconds": round(t_end - start, 2)}
    if warns:
        out["camera_warnings"] = warns[:16] + ([f"+{len(warns) - 16} more"] if len(warns) > 16 else [])
    res = []
    rec = STATE / "record" / name
    rec.mkdir(parents=True, exist_ok=True)
    if sheet:
        res_sheet = shot_sheet(shots, perf, size, t_end, rec / "shots.png")
    if not check_only:
        jid = uuid.uuid4().hex[:8]
        j = {"id": jid, "state": "rendering", "done": 0, "total": 0,
             "frames_dir": str(rec / f"frames_{quality}"), "mp4": str(rec / f"{name}_{quality}.mp4"),
             "sheet": str(rec / "contact.png"), "audio": audio}
        JOBS[jid] = j
        threading.Thread(target=_render_job, args=(j, shots, perf, size, fps, start, t_end, quality == "draft"),
                         daemon=True).start()
        per = 0.9 if quality == "draft" else 2.2
        out.update(job=jid, frames=int((t_end - start) * fps),
                   eta_min=round((t_end - start) * fps * per / 60, 1),
                   status=f"rendering in the background; call roblox_record(job='{jid}') for progress / the MP4")
    res.insert(0, json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    if sheet:
        res.append(Image(path=str(res_sheet)))
    return res


RECORD_DOC = """Film the performance in the open Roblox Studio place as a vertical 9:16 video (frame-by-frame, so it
is smooth and deterministic no matter how slow Studio is). shots = camera cues in story time: static {start, pos,
look, fov} or tracking {start, track: 'Timmy', offset: [dx,dy,dz], aim: [dx,dy,dz], fov}; subjects = who must be
visible. First runs camera checks at every shot (camera inside or clipping a prop or a body, subjects hidden behind
something, out of frame / head cut off) and returns them with a sheet of one draft frame per shot: fix the cues and
call again with check_only=true until clean. Without check_only it then renders in the background (about 2 s per
frame for quality 'final', 1 s for 'draft'); call roblox_record(job=...) for progress and, when done, the MP4 path
and a contact sheet. audio = optional path to a narration/music track muxed into the MP4.
Realtime fallback: press Play (the director autoplays every character) and screen-record the Studio window."""


def register(mcp, server_module):
    global SRV
    SRV = server_module
    import anyio

    @mcp.tool(description=RECORD_DOC)
    async def roblox_record(shots: list[CameraCue] | None = None, start: float = 0.0, end: float | None = None,
                            fps: int = 24, quality: str = "final", name: str = "short", check_only: bool = False,
                            sheet: bool = True, audio: str | None = None, job: str | None = None) -> list:
        return await anyio.to_thread.run_sync(
            lambda: record(shots or [], start, end, fps, (1080, 1920), quality, name, check_only, sheet, audio, job))
