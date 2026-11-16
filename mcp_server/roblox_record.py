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
import os
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
    model_config = {"populate_by_name": True}
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
    subject: str | None = Field(None, description="Frame this character, from where it actually is: the camera is "
                                                  "placed relative to its pose at the shot's start (no pos/look needed)")
    shot: str = Field("medium", description="With subject: close (face) | medium (waist up) | full (whole body) | "
                                            "wide (with surroundings) | low (low angle, looking up)")
    angle: float = Field(25.0, description="With subject: degrees around it, 0 = straight in front of its face, "
                                           "+ = toward its left, 180 = from behind")
    with_: str | None = Field(None, alias="with", description="With subject: a second character for a two-shot")
    cover: bool = Field(True, description="With subject: a long shot (> ~2.4 s) is cut into ~1.5 s coverage shots "
                                          "(close / medium / other angle; two-shots alternate with singles)")
    push: float = Field(0.08, description="Slow push-in over the shot: field of view narrows by this fraction by its "
                                          "end (0 = locked-off shot)")


# ------------------------------------------------------------------------------------------- subject framing
SHOTS = {  # distance (in head heights above the floor ~ character height), camera height and aim (0 = hips, 1 = head), fov
    "close": (1.5, 1.0, 0.97, 34), "medium": (2.0, 0.92, 0.82, 38), "full": (2.8, 0.8, 0.5, 44),
    "wide": (4.0, 1.2, 0.4, 50), "low": (1.4, -0.1, 0.85, 42),
}
WIDER = {"close": "medium", "medium": "full", "low": "medium"}
POSE_LUAU = r'''
local D = _G.PromptimateDirector
local out = {}
for _, q in game:GetService("HttpService"):JSONDecode(__Q__) do
  D.seek(q[2])
  local a = D.actors[q[1]]
  local tg = a and a._player and a._player.targets
  if tg then
    -- facing = where the face points (flattened), the body's facing when the head looks straight up/down
    local h, hp = tg.Head.Position, tg.LowerTorso.Position
    local l = tg.Head.LookVector * Vector3.new(1, 0, 1)
    if l.Magnitude < 0.3 then l = tg.HumanoidRootPart.LookVector end
    local foot = math.min(tg.LeftFoot.Position.Y, tg.RightFoot.Position.Y) - 0.4
    table.insert(out, { h.X, h.Y, h.Z, hp.X, hp.Y, hp.Z, l.X, l.Z, foot })
  else
    table.insert(out, false)
  end
end
return game:GetService("HttpService"):JSONEncode(out)'''


def _cam_for(pose, other, shot: str, angle: float, lift: float = 0.0):
    hx, hy, hz, px, py, pz, lx, lz, foot = pose
    k_dist, k_h, k_aim, fov = SHOTS.get(shot, SHOTS["medium"])
    tall = max(hy - foot, 2.0)
    ln = math.hypot(lx, lz) or 1.0
    lx, lz = lx / ln, lz / ln
    if other:
        ox, oz = (hx + other[0]) / 2, (hz + other[2]) / 2
        sep = math.hypot(other[0] - hx, other[2] - hz)
        ax, az = (other[2] - hz) / (sep or 1), -(other[0] - hx) / (sep or 1)   # perpendicular to the pair
        if ax * lx + az * lz < 0:
            ax, az = -ax, -az                                                    # on the side the subject faces
        a = math.radians(angle)
        dx, dz = ax * math.cos(a) - az * math.sin(a), ax * math.sin(a) + az * math.cos(a)
        dist = max(k_dist * tall, sep * 1.5)
        aim_y = foot + tall * k_aim
        return [ox + dx * dist, foot + tall * (k_h + lift), oz + dz * dist], [ox, aim_y, oz], fov + 6
    a = math.radians(angle)
    # rotate the facing direction toward the subject's left (+angle): left of facing (lx, lz) is (lz, -lx) in Roblox
    dx, dz = lx * math.cos(a) + lz * math.sin(a), lz * math.cos(a) - lx * math.sin(a)
    ax, ay, az = px + (hx - px) * 0.3, foot + tall * k_aim, pz + (hz - pz) * 0.3
    if shot == "close":
        ax, az = hx, hz
    dist = k_dist * tall
    return [ax + dx * dist, foot + tall * (k_h + lift), az + dz * dist], [ax, ay, az], fov


TIGHTER = {"wide": "full", "full": "medium", "medium": "close", "close": "medium", "low": "close"}


def cover(cues, t_end: float, target: float | None = None):
    """Viral story shorts cut every ~1.4 s. A long subject shot becomes a sequence of coverage shots of the same
    character(s): the written shot, a tighter one from another side, the written shot from a third angle, ...; a
    two-shot alternates with singles of each character. Shots of signs/sets (pos/look) and tracked shots are kept."""
    target = target or float(os.environ.get("PROMPTIMATE_RBX_SHOT_S", "1.6"))
    out = []
    cues = sorted(cues, key=lambda c: c.start)
    for i, c in enumerate(cues):
        end = cues[i + 1].start if i + 1 < len(cues) else t_end
        dur = end - c.start
        if not (c.subject and c.cover and not c.pos and not c.track) or dur < target * 1.5:
            out.append(c)
            continue
        n = max(2, round(dur / target))
        step = dur / n
        starts = [c.start + j * step for j in range(n)]
        # cut on the narration's sentence starts when there are some inside the shot (viewers expect a new
        # picture with each new line); even splits otherwise
        marks = [m for m in (cover.cut_times or []) if c.start + 0.9 <= m <= end - 0.9]
        if marks:
            picked = [c.start]
            for m in marks:
                if m - picked[-1] >= 1.1 and end - m >= 0.9:
                    picked.append(m)
            # a long gap between sentence starts still gets an even split inside it
            full = []
            for k2, a0 in enumerate(picked):
                a1 = picked[k2 + 1] if k2 + 1 < len(picked) else end
                m2 = max(1, round((a1 - a0) / (target * 1.25)))
                full += [a0 + (a1 - a0) * q / m2 for q in range(m2)]
            starts = full
            n = len(starts)
        for j in range(n):
            u = {"start": round(starts[j], 3), "cover": False}
            if j > 0:
                if c.with_:      # two-shot -> single of subject -> two-shot -> single of the other -> ...
                    m = j % 4
                    if m == 1:
                        u.update(with_=None, shot="close" if c.shot != "wide" else "medium", angle=c.angle + 20)
                    elif m == 3:
                        u.update(subject=c.with_, with_=None, shot="close" if c.shot != "wide" else "medium", angle=-20)
                    else:
                        u.update(angle=c.angle - 15)
                else:
                    m = j % 3
                    if m == 1:
                        u.update(shot=TIGHTER.get(c.shot, c.shot), angle=c.angle - 30)
                    elif m == 2:
                        u.update(angle=c.angle + 35)
                if c.name:
                    u["name"] = f"{c.name} /{j + 1}"
            out.append(c.model_copy(update=u))
    return out


cover.cut_times = None


def frame_subjects(cues, t_end: float):
    """Cues with a subject get pos/look from the subject's real pose at the shot start (+0.4 s); when the camera would
    sit inside something or the subject is blocked, nearby angles are tried and the clearest one is used."""
    todo = [(i, c) for i, c in enumerate(cues) if c.subject and not c.pos and not c.track]
    if not todo:
        return cues
    q = []
    for i, c in todo:
        b = cues[i + 1].start if i + 1 < len(cues) else t_end
        t = (c.start + b) / 2
        q.append([c.subject, t])
        if c.with_:
            q.append([c.with_, t])
    poses = studio().luau_json(POSE_LUAU.replace("__Q__", long_str(json.dumps(q))))
    frame_subjects.alts = {}
    k = 0
    out = list(cues)
    for i, c in todo:
        pose = poses[k]
        k += 1
        other = None
        if c.with_:
            other = poses[k]
            k += 1
        if not pose:
            continue
        # nearby angles first; higher cameras (over a counter/throne arm) and far angles as fallbacks
        # one size wider as a fallback (hands at the face fill a close-up of a blocky R6 character)
        sizes = [c.shot] + ([WIDER[c.shot]] if c.shot in WIDER else [])
        cands = [(c.angle + d, lift, sz) for sz in sizes for lift in (0.0, 0.45, -0.3)
                 for d in (0, 25, -25, 50, -50, 80, -80, 115, -115, 150, -150, 180)]
        cams = []
        for ang, lift, sz in cands:
            pos, look, fov = _cam_for(pose, other, sz, ang, lift)
            cams.append({"pos": pos, "look": look, "fov": fov, "subjects": [c.subject] + ([c.with_] if c.with_ else []),
                         "r": 0.6, "lean": True})
        b = cues[i + 1].start if i + 1 < len(cues) else t_end
        times = sorted({round(min(c.start + 0.4, (c.start + b) / 2), 2), round((c.start + b) / 2, 2),
                        round(max(b - 0.4, (c.start + b) / 2), 2)})
        runs = studio().luau_json(
            "local H = game:GetService('HttpService'); local D = _G.PromptimateDirector\n"
            f"local cams = H:JSONDecode({long_str(json.dumps(cams))}); local out = {{}}\n"
            f"for _, t in {{{','.join(f'{t:.3f}' for t in times)}}} do table.insert(out, H:JSONDecode(D.camcheck(t, cams))) end\n"
            "return H:JSONEncode(out)")
        res = runs[len(runs) // 2]
        best, best_score = 0, 1e9
        ranked = []
        for j in range(len(cams)):
            score = 0.0
            for run in runs:     # the shot is judged over its length, not one instant (arms move)
                r = run[j]
                near = list(r.get("near") or [])      # inside anything, the subject's own hat included
                subs = r.get("subjects") if isinstance(r.get("subjects"), dict) else {}
                blocked = sum(v.get("blocked", 0) for v in subs.values())
                score += (len(near) * 10 + blocked * 3 + r.get("fg", 0) * 25) / len(runs)
                for v in subs.values():
                    f = v.get("face", 1.0)
                    score += (8 if f < 0 else 4 if f < 0.35 else 1.5 if f < 0.6 else 0) / len(runs)
                    score += float(v.get("selfhit") or 0) * 10 / len(runs)                # face covered (arms, props)
            pos = cams[j]["pos"]
            look = cams[j]["look"]
            horiz = math.hypot(pos[0] - look[0], pos[2] - look[2]) or 1e-3
            pitch = math.degrees(math.atan2(pos[1] - look[1], horiz))
            score += 4 if pitch > 40 else 1.5 if pitch > 28 else 0              # looking down on hats
            ang, lift, sz = cands[j]
            score += abs(ang - c.angle) / 25 * 0.5 + abs(lift) * 3 + (2.5 if sz != c.shot else 0)
            ranked.append((score, j))
            if score < best_score:
                best, best_score = j, score
        ranked.sort()
        frame_subjects.alts[i] = [_cam_for(pose, other, cands[j][2], cands[j][0], cands[j][1]) for _, j in ranked[1:8]]
        if os.environ.get("PROMPTIMATE_FRAME_DEBUG"):
            r = res[best]
            print(f"frame {c.name or c.start}: angle {cands[best]} score {best_score:.1f} fg {r.get('fg', 0):.2f} "
                  + " ".join(f"{k}:face {v.get('face', 0):.2f} cover {float(v.get('selfhit') or 0):.2f}"
                             for k, v in (r.get('subjects') or {}).items()), file=sys.stderr)
        pos, look, fov = _cam_for(pose, other, cands[best][2], cands[best][0], cands[best][1])
        out[i] = c.model_copy(update={"pos": [round(v, 3) for v in pos], "look": [round(v, 3) for v in look], "fov": fov,
                                      "subjects": c.subjects if c.subjects is not None else [c.subject]})
    return out


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
    fov = c.fov
    if c.push and not c.track:
        end = cues[k + 1].start if k + 1 < len(cues) else c.start + 4.0
        u = min(max((t - c.start) / max(end - c.start, 0.5), 0.0), 1.0)
        fov = c.fov * (1 - c.push * (u * u * (3 - 2 * u)))     # eased
    return k, c, pos, look, fov


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


def _blank(im) -> float:
    """Share of the frame taken by its single most common colour (coarse): ~1 for a camera inside a hat, a throne
    or a body (one flat colour fills the frame), ~0.2-0.4 for a readable shot."""
    a = np.asarray(im.convert("RGB").resize((72, 128)), dtype=np.int32) // 43
    keys = a[:, :, 0] * 36 + a[:, :, 1] * 6 + a[:, :, 2]
    return float(np.bincount(keys.ravel()).max() / keys.size)


BLANK_MAX = 0.5


def image_qa(cues, perf, size, t_end):
    """Look at each subject shot's actual picture (mid-shot frame): when one flat colour fills most of it (camera inside
    a prop, a hat, a body), the next-best framing candidates are tried until one is readable."""
    alts = getattr(frame_subjects, "alts", {})
    fast = _fast_setup(size)
    if not fast or not alts:
        return cues, []
    FG = fast["FG"]
    vp = _viewport()
    FG.pin_studio(True)
    rect = FG.calibrate(studio(), vp)
    studio().luau(FG.HIDE_NAMES)
    out, notes = list(cues), []

    def badness(c, pos, look, fov, t):
        """0 = readable; adds the flat-colour share, +1 when the subject's head is outside the frame, +1 when its head
        and body are both hidden behind something."""
        im = FG.portrait(studio(), rect, vp, list(pos), list(look), fov, seek_t=t, out=(270, 480))
        bl = _blank(im)
        sc = max(0.0, bl - BLANK_MAX) * 4 + (bl > BLANK_MAX)
        r = studio().luau_json(f"return _G.PromptimateDirector.camcheck({t:.3f}, game:GetService('HttpService'):JSONDecode("
                               f"{long_str(json.dumps([{'pos': list(map(float, pos)), 'look': list(map(float, look)), 'fov': fov, 'subjects': [c.subject], 'r': 0.6}]))}))")[0]
        v = (r.get("subjects") or {}).get(c.subject)
        if v:
            u, w, z = _project(np.asarray(pos, float), np.asarray(look, float), fov, size, v["head"])
            if z <= 0 or not (0.03 < u < 0.97 and 0.03 < w < 0.92):
                sc += 1
            if v.get("blocked", 0) >= 2:
                sc += 1
        return sc, bl
    for i, cand in alts.items():
        c = out[i]
        b = out[i + 1].start if i + 1 < len(out) else t_end
        t = (c.start + b) / 2
        _k, _c, pos, look, fov = camera(out, perf, t)
        sc, bl = badness(c, pos, look, fov, t)
        if sc <= 0:
            continue
        best = (sc, None)
        for pos2, look2, fov2 in cand[:5]:
            sc2, _ = badness(c, pos2, look2, fov2, t)
            if sc2 < best[0]:
                best = (sc2, (pos2, look2, fov2))
            if sc2 <= 0:
                break
        if best[1]:
            pos2, look2, fov2 = best[1]
            out[i] = c.model_copy(update={"pos": [round(v, 3) for v in pos2], "look": [round(v, 3) for v in look2],
                                          "fov": fov2})
        notes.append(f"{c.name or c.start}: bad {sc:.2f} (flat {bl:.2f}) -> {best[0]:.2f}")
    studio().luau(FG.RESTORE_NAMES)
    return out, notes


def shot_sheet(cues, perf, size, t_end, out: Path) -> Path:
    from PIL import Image, ImageDraw
    vp = _viewport()
    state = {}
    thumbs = []
    fast = _fast_setup(size)
    if fast:
        try:
            _ensure_running()
            fast["FG"].pin_studio(True)
            fast["rect"] = fast["FG"].calibrate(studio(), vp)
            studio().luau(fast["FG"].HIDE_NAMES)
        except Exception:
            fast = None
    for k, c in enumerate(cues):
        b = cues[k + 1].start if k + 1 < len(cues) else t_end
        t = (c.start + b) / 2
        if fast:
            _k, _c, pos, look, fov = camera(cues, perf, t)
            im = fast["FG"].portrait(studio(), fast["rect"], vp, list(pos), list(look), fov, seek_t=t,
                                     out=tuple(size)).resize((135, 240))
        else:
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
    if fast:
        studio().luau(fast["FG"].RESTORE_NAMES)
    sheet.save(out)
    return out


# ---------------------------------------------------------------------------------------------------- rendering
def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or r"D:\tools\ffmpeg\bin\ffmpeg.exe"


_VENC = None


def _venc() -> list[str]:
    """H.264 encoder args: the GPU's hardware encoder when ffmpeg has it (AMD AMF ~6x faster than x264 veryfast on
    1080x1920), else libx264."""
    global _VENC
    if _VENC is None:
        _VENC = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "veryfast"]
        if os.environ.get("PROMPTIMATE_VENC", "auto") != "x264":
            try:
                r = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                                    "color=c=gray:s=256x256:d=0.2", "-c:v", "h264_amf", "-f", "null", "-"],
                                   capture_output=True, timeout=30)
                if r.returncode == 0:
                    _VENC = ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "18", "-qp_p", "20",
                             "-pix_fmt", "yuv420p"]
            except Exception:
                pass
    return list(_VENC)


def _heavy(who: str):
    """Machine-wide lock for heavy jobs (scripts/heavy_lock.py) when this checkout has it: long frame-by-frame
    renders and ffmpeg encodes take turns with other heavy work on the machine."""
    import contextlib
    if os.environ.get("PROMPTIMATE_HEAVY_HELD"):     # the calling process already holds it (episode producer)
        return contextlib.nullcontext()
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


def _fast_setup(size):
    """Screen-grab recording (one rolled-camera shot per frame, ~0.27 s) when Studio's window is on screen;
    PROMPTIMATE_RBX_CAPTURE=mcp forces the MCP screen_capture path (3 stitched captures per frame, ~2.3 s)."""
    import os
    if os.environ.get("PROMPTIMATE_RBX_CAPTURE", "screen") == "mcp" or sys.platform != "win32":
        return None
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "roblox" / "short"))
        import fastgrab as FG
        if not FG.studio_window():
            return None
        return {"FG": FG}
    except Exception:
        return None


def _render_job_locked(job: dict, cues, perf, size, fps, t0, t1, draft):
    try:
        out_dir = Path(job["frames_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        # frames on disk are reused to resume an interrupted render, but only for the same performance, package,
        # cameras and size: re-recording after a new roblox_perform must not reuse stale frames
        import hashlib
        import roblox_tools as RT
        fast = _fast_setup(size)
        job["mode"] = "screen" if fast else "mcp"
        sig = hashlib.sha1(json.dumps({"mode": job["mode"], 
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
        if fast:
            try:
                fast["FG"].pin_studio(True)
                fast["rect"] = fast["FG"].calibrate(studio(), vp)
                studio().luau(fast["FG"].HIDE_NAMES)
            except Exception as e:     # window covered / minimized: fall back to MCP captures
                job["mode"] = "mcp"
                job["fast_error"] = str(e)[:200]
                fast = None
        pool = ThreadPoolExecutor(4)
        pending = []
        n0, n1 = int(round(t0 * fps)), int(math.floor(t1 * fps - 1e-6))
        job["total"] = n1 - n0 + 1
        t_start = time.time()
        # screen mode on a fresh render: frames stream straight into the encoder while they're captured (the MP4
        # is ready seconds after the last frame); PNGs are still written so an interrupted render can resume
        enc = None
        mp4 = Path(job["mp4"])
        if fast and not any(out_dir.glob("f*.png")):
            cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
                   "-framerate", str(fps), "-i", "-"]
            if job.get("audio"):
                cmd += ["-i", job["audio"], "-shortest", "-c:a", "aac", "-b:a", "192k"]
            cmd += [*_venc(), str(mp4)]
            enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        order = []
        if fast and os.environ.get("PROMPTIMATE_RBX_REALTIME", "1") != "0":
            # live pass first: Studio plays the performance, every frame it shows is captured; the loop below then
            # only fills the frames it skipped
            missing = [i for i in range(n0, n1 + 1) if not (out_dir / f"f{i - n0:05d}.png").exists()]
            if len(missing) > fps * 3:
                try:
                    import realtime as RTL
                    from PIL import Image as _Im
                    FG = fast["FG"]
                    cams = {}
                    for i in missing:
                        _k, _c, pos, look, fov = camera(cues, perf, i / fps)
                        cams[i] = [*map(float, pos), *map(float, look), FG.roblox_fov(fov, vp, tuple(size))]
                    job["state"] = "rendering (live pass)"
                    live_pending = []

                    def on_frame(k, img):
                        def w(k=k, img=img):
                            FG.finish(_Im.fromarray(img[:, :, 2::-1]), vp, tuple(size)).save(
                                out_dir / f"f{k - n0:05d}.png", compress_level=1)
                        live_pending.append(pool.submit(w))
                        job["done"] = len(live_pending)
                    lo, hi = min(missing), max(missing)
                    got = RTL.record(studio(), fast["rect"], cams, lo, hi, fps, on_frame,
                                     speed=float(os.environ.get("PROMPTIMATE_RBX_RT_SPEED", "0.6")),
                                     log=lambda m: job.__setitem__("live", m))
                    for f in live_pending:
                        f.result()
                    job["live_frames"] = len(got)
                    job["state"] = "rendering (filling skipped frames)"
                except Exception as e:
                    job["live_error"] = f"{type(e).__name__}: {e}"[:300]
            if any(out_dir.glob("f*.png")) and enc:
                enc.stdin.close(); enc.wait(); enc = None       # frames on disk now: encode from PNGs at the end
        for i in range(n0, n1 + 1):
            if job.get("cancel"):
                job["state"] = "cancelled"
                return
            path = out_dir / f"f{i - n0:05d}.png"
            if not path.exists():
                if fast:
                    if i % 24 == 0 and not fast["FG"].viewport_clear(fast["rect"]):
                        fast["FG"].pin_studio(True)        # something covered Studio: bring it back up, re-measure
                        fast["rect"] = fast["FG"].calibrate(studio(), vp)
                        if not fast["FG"].viewport_clear(fast["rect"]):
                            raise RuntimeError("Studio's viewport is covered by another window; uncover it and record again")
                    t = i / fps
                    _k, _c, pos, look, fov = camera(cues, perf, t)
                    raw = fast["FG"].portrait_raw(studio(), fast["rect"], vp, list(pos), list(look), fov, seek_t=t,
                                                  out=tuple(size))

                    def work(raw=raw, p=path):
                        im = fast["FG"].finish(raw, vp, tuple(size))
                        im.save(p, compress_level=1)
                        return im.tobytes()
                    fut = pool.submit(work)
                    pending.append(fut)
                    if enc:
                        order.append(fut)
                        while len(order) > 6:          # feed the encoder in frame order, a few frames behind
                            enc.stdin.write(order.pop(0).result())
                else:
                    imgs, rows = frame(cues, perf, i / fps, size, vp, draft, f"r{job['id']}_{i}", state)
                    pending.append(pool.submit(lambda im=imgs, rw=rows, p=path: stitch.blend(im, rw, size).save(p)))
            job["done"] = i - n0 + 1
            el = time.time() - t_start
            job["eta_s"] = round(el / job["done"] * (job["total"] - job["done"]))
        if enc:
            for fut in order:
                enc.stdin.write(fut.result())
        for p in pending:
            p.result()
        if fast:
            studio().luau(fast["FG"].RESTORE_NAMES)
        if enc:
            enc.stdin.close()
            if enc.wait() != 0:
                raise RuntimeError("ffmpeg (streamed encode) failed")
        else:
            cmd = [_ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(out_dir / "f%05d.png")]
            if job.get("audio"):
                cmd += ["-i", job["audio"], "-shortest", "-c:a", "aac", "-b:a", "192k"]
            cmd += [*_venc(), str(mp4)]
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
        return [json.dumps({k: j.get(k) for k in ("state", "done", "total", "eta_s", "error", "live", "live_frames", "live_error") if j.get(k) is not None})]
    if not shots:
        raise ValueError("give at least one camera cue")
    shots = sorted(shots, key=lambda c: c.start)
    perf = Perf()
    if not perf.actors:
        raise ValueError("no performance yet: call roblox_perform first")
    t_end = end if end is not None else perf.end()
    _ensure_running()
    if os.environ.get("PROMPTIMATE_RBX_COVER", "1") != "0":
        shots = cover(shots, t_end)
    shots = frame_subjects(shots, t_end)
    qa_notes = []
    if os.environ.get("PROMPTIMATE_RBX_IMAGE_QA", "1") != "0":
        try:
            shots, qa_notes = image_qa(shots, perf, size, t_end)
        except Exception as e:
            qa_notes = [f"image QA skipped: {e}"[:200]]
    warns, _ = check_cameras(shots, perf, size, t_end)
    out = {"shots": len(shots), "seconds": round(t_end - start, 2)}
    if qa_notes:
        out["image_qa"] = qa_notes[:20]
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
        per = 0.3 if _fast_setup(size) else (0.9 if quality == "draft" else 2.2)
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
