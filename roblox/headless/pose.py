"""Studio-free posing: a numpy port of ShortDirector.poseActor + PromptimatePlayer's R6 retarget.

    P = Poser(perf_actors)            # {name: {"clips": [{m, s, d, x, y, z, yaw}, ...], "arms": 0.55}}
    parts = P.pose(name, t)           # {"Torso": (pos(3), rot(3x3)), "Head": ..., "Left Arm": ...}

Classic R6 rig: Torso 2x2x1, Head 2x1x1 (round mesh), arms and legs 1x2x1, standard Motor6D offsets."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CLIPS = ROOT / ".cache" / "roblox_perform" / "clips"

SIZES = {"Torso": (2, 2, 1), "Head": (2, 1, 1), "Left Arm": (1, 2, 1), "Right Arm": (1, 2, 1), "Left Leg": (1, 2, 1),
         "Right Leg": (1, 2, 1)}
# Motor6D joint positions: on the torso (C0) and on the limb (C1), studs
JOINT = {"Head": ((0, 1, 0), (0, -0.5, 0)), "Right Arm": ((1, 0.5, 0), (-0.5, 0.5, 0)),
         "Left Arm": ((-1, 0.5, 0), (0.5, 0.5, 0)), "Right Leg": ((1, -1, 0), (0.5, 1, 0)),
         "Left Leg": ((-1, -1, 0), (-0.5, 1, 0))}
R6LIMBS = {"Left Arm": ("LeftUpperArm", "LeftLowerArm"), "Right Arm": ("RightUpperArm", "RightLowerArm"),
           "Left Leg": ("LeftUpperLeg", "LeftLowerLeg"), "Right Leg": ("RightUpperLeg", "RightLowerLeg")}
LEG = 2.0           # R6.measure: hips = leg length above the feet
HALF_TORSO = 1.0


# ------------------------------------------------------------------------------------------- rotation helpers
def q2m(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def m2q(m):
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1) * 2
        return np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, s / 4])
    i = int(np.argmax(np.diag(m)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(1 + m[i, i] - m[j, j] - m[k, k]) * 2
    q = np.zeros(4)
    q[i] = s / 4
    q[j] = (m[j, i] + m[i, j]) / s
    q[k] = (m[k, i] + m[i, k]) / s
    q[3] = (m[k, j] - m[j, k]) / s
    return q


def slerp(q0, q1, a):
    d = float(np.dot(q0, q1))
    if d < 0:
        q1, d = -q1, -d
    if d > 0.9995:
        q = q0 + (q1 - q0) * a
        return q / np.linalg.norm(q)
    th = math.acos(min(d, 1.0))
    s = math.sin(th)
    return (math.sin((1 - a) * th) * q0 + math.sin(a * th) * q1) / s


def mlerp(m0, m1, a):
    return q2m(slerp(m2q(m0), m2q(m1), a))


def axis_angle(axis, ang):
    axis = np.asarray(axis, float)
    n = np.linalg.norm(axis)
    if n < 1e-9:
        return np.eye(3)
    x, y, z = axis / n
    c, s = math.cos(ang), math.sin(ang)
    C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def to_axis_angle(m):
    q = m2q(m)
    if q[3] < 0:
        q = -q
    ang = 2 * math.acos(min(1.0, q[3]))
    s = math.sqrt(max(1e-12, 1 - q[3] * q[3]))
    return q[:3] / s, ang


def arc(u, v):
    c = float(np.clip(np.dot(u, v), -1, 1))
    ax = np.cross(u, v)
    if np.linalg.norm(ax) < 1e-6:
        return np.eye(3) if c > 0 else axis_angle((0, 0, 1), math.pi)
    return axis_angle(ax, math.acos(c))


def yaw_mat(yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


# ------------------------------------------------------------------------------------------------- clips
@lru_cache(maxsize=4096)
def clip(name: str) -> dict:
    d = json.loads((CLIPS / f"{name}.json").read_text())
    if isinstance(d, str):
        d = json.loads(d)
    d["_rot"] = np.asarray(d["rot"], float)
    d["_root"] = np.asarray(d["root"], float)
    d["_index"] = {n: i * 4 for i, n in enumerate(d["parts"])}
    return d


class Poser:
    def __init__(self, actors: dict):
        self.actors = actors

    def active(self, a, t):
        k = 0
        for i, c in enumerate(a["clips"]):
            if c["s"] <= t + 1e-6:
                k = i
        c = a["clips"][k]
        return c, min(max(t - c["s"], 0.0), c["d"])

    def pose(self, name: str, t: float) -> dict:
        a = self.actors[name]
        if not a.get("clips"):
            return {}
        c, lt = self.active(a, t)
        return pose_r6(clip(c["m"]), lt, (c["x"], c.get("y", 0.0), c["z"]), c["yaw"], a.get("arms", 1.0))


def pose_r6(cl: dict, t: float, origin_pos, origin_yaw: float, arms: float = 1.0) -> dict:
    n = cl["frames"]
    f = t * cl["fps"]
    f = (f % (n - 1)) if cl.get("loop") else min(max(f, 0), n - 1)
    i0 = int(math.floor(f))
    i1 = min(i0 + 1, n - 1)
    a = f - i0
    r0, r1 = cl["_rot"][i0], cl["_rot"][i1]
    hips = cl["_root"][i0] + (cl["_root"][i1] - cl["_root"][i0]) * a
    O = yaw_mat(origin_yaw)
    src = {}
    for nm, o in cl["_index"].items():
        src[nm] = O @ q2m(slerp(r0[o:o + 4], r1[o:o + 4], a))
    world = {"Torso": mlerp(src["LowerTorso"], src["UpperTorso"], 0.6)}
    # the head relative to the torso, damped and capped (a big block head copying a human neck reads as broken)
    ax, ang = to_axis_angle(world["Torso"].T @ src["Head"])
    world["Head"] = world["Torso"] @ axis_angle(ax, min(ang * 0.75, math.radians(30))) if ang > 1e-4 else world["Torso"]
    down = np.array([0, -1, 0.0])
    for nm, (u, l) in R6LIMBS.items():
        up, lo = src[u], src[l]
        d1, d2 = up @ down, lo @ down
        d = d1 + d2
        d = d / np.linalg.norm(d) if np.linalg.norm(d) > 1e-3 else d1
        w = arc(d1, d) @ up
        if arms < 1 and "Arm" in nm:
            side = -1 if nm == "Left Arm" else 1
            rest = world["Torso"] @ axis_angle((0, 0, 1), side * math.radians(4))
            w = mlerp(rest, w, arms)
        world[nm] = w
    hip_world = np.asarray(origin_pos, float) + O @ (hips * LEG)

    def chain(hw):
        torso_p = hw + world["Torso"] @ np.array([0, HALF_TORSO, 0])
        out = {"Torso": (torso_p, world["Torso"])}
        for nm, (c0, c1) in JOINT.items():
            jp = torso_p + world["Torso"] @ np.asarray(c0, float)
            out[nm] = (jp - world[nm] @ np.asarray(c1, float), world[nm])
        return out

    parts = chain(hip_world)
    floor = float(origin_pos[1])
    low = math.inf
    for nm, (p, R) in parts.items():
        h = np.asarray(SIZES[nm], float) / 2
        low = min(low, p[1] - np.abs(R[1]) @ h)
    if low < floor - 0.02:
        parts = chain(hip_world + np.array([0, floor - low, 0]))
    return parts


# ------------------------------------------------------------------------- vectorised (all frames of a clip at once)
def qmul(a, b):
    ax, ay, az, aw = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bx, by, bz, bw = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], -1)


def qconj(q):
    return q * np.array([-1, -1, -1, 1.0])


def qrot(q, v):
    """Rotate vectors v (..., 3) by quaternions q (..., 4)."""
    u, w = q[..., :3], q[..., 3:4]
    t = 2 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def qslerp(q0, q1, a):
    a = np.asarray(a, float)[..., None] if np.ndim(a) else np.full(q0.shape[:-1] + (1,), float(a))
    d = np.sum(q0 * q1, -1, keepdims=True)
    q1 = np.where(d < 0, -q1, q1)
    d = np.abs(d)
    th = np.arccos(np.clip(d, -1, 1))
    s = np.sin(th)
    near = d > 0.9995
    w0 = np.where(near, 1 - a, np.sin((1 - a) * th) / np.where(near, 1, s))
    w1 = np.where(near, a, np.sin(a * th) / np.where(near, 1, s))
    q = w0 * q0 + w1 * q1
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def qaxis(axis, ang):
    axis = np.asarray(axis, float)
    n = np.linalg.norm(axis, axis=-1, keepdims=True)
    axis = axis / np.maximum(n, 1e-12)
    h = np.asarray(ang)[..., None] / 2
    return np.concatenate([axis * np.sin(h), np.cos(h)], -1)


def qarc(u, v):
    """Shortest-arc rotation u -> v (unit vectors), batched."""
    c = np.clip(np.sum(u * v, -1), -1, 1)
    ax = np.cross(u, v)
    n = np.linalg.norm(ax, axis=-1)
    q = qaxis(np.where(n[..., None] < 1e-6, np.array([0, 0, 1.0]), ax), np.arccos(c))
    q = np.where((n < 1e-6)[..., None], np.where((c > 0)[..., None], np.array([0, 0, 0, 1.0]), np.array([0, 0, 1.0, 0])), q)
    return q


def qyaw(yaw):
    return np.array([0, math.sin(yaw / 2), 0, math.cos(yaw / 2)])


def pose_r6_vec(cl: dict, ts: np.ndarray, origin_pos, origin_yaw: float, arms: float = 1.0) -> dict:
    """pose_r6 for many local times at once: {part: (pos (n,3), quat xyzw (n,4))}."""
    n = cl["frames"]
    f = ts * cl["fps"]
    f = np.mod(f, n - 1) if cl.get("loop") else np.clip(f, 0, n - 1)
    i0 = np.floor(f).astype(int)
    i1 = np.minimum(i0 + 1, n - 1)
    a = f - i0
    R0, R1 = cl["_rot"][i0], cl["_rot"][i1]
    hips = cl["_root"][i0] + (cl["_root"][i1] - cl["_root"][i0]) * a[:, None]
    qo = np.broadcast_to(qyaw(origin_yaw), (len(ts), 4))
    src = {nm: qmul(qo, qslerp(R0[:, o:o + 4], R1[:, o:o + 4], a)) for nm, o in cl["_index"].items()}
    W = {"Torso": qslerp(src["LowerTorso"], src["UpperTorso"], 0.6)}
    rel = qmul(qconj(W["Torso"]), src["Head"])
    rel = np.where(rel[:, 3:4] < 0, -rel, rel)
    ang = 2 * np.arccos(np.clip(rel[:, 3], -1, 1))
    axis = rel[:, :3] / np.maximum(np.sqrt(np.maximum(1 - rel[:, 3] ** 2, 0)), 1e-9)[:, None]
    head_rel = qaxis(axis, np.minimum(ang * 0.75, math.radians(30)))
    head_rel = np.where((ang > 1e-4)[:, None], head_rel, np.array([0, 0, 0, 1.0]))
    W["Head"] = qmul(W["Torso"], head_rel)
    down = np.array([0, -1, 0.0])
    for nm, (u, l) in R6LIMBS.items():
        up, lo = src[u], src[l]
        d1, d2 = qrot(up, down), qrot(lo, down)
        d = d1 + d2
        dn = np.linalg.norm(d, axis=-1, keepdims=True)
        d = np.where(dn > 1e-3, d / np.maximum(dn, 1e-9), d1)
        w = qmul(qarc(d1, d), up)
        if arms < 1 and "Arm" in nm:
            side = -1 if nm == "Left Arm" else 1
            rest = qmul(W["Torso"], qaxis(np.array([0, 0, 1.0]), side * math.radians(4)))
            w = qslerp(rest, w, arms)
        W[nm] = w
    hip_world = np.asarray(origin_pos, float) + qrot(qo, hips * LEG)

    def chain(hw):
        tp = hw + qrot(W["Torso"], np.array([0, HALF_TORSO, 0.0]))
        out = {"Torso": (tp, W["Torso"])}
        for nm, (c0, c1) in JOINT.items():
            jp = tp + qrot(W["Torso"], np.asarray(c0, float))
            out[nm] = (jp - qrot(W[nm], np.asarray(c1, float)), W[nm])
        return out

    parts = chain(hip_world)
    floor = float(origin_pos[1])
    low = np.full(len(ts), np.inf)
    for nm, (p, q) in parts.items():
        h = np.asarray(SIZES[nm], float) / 2
        # lowest corner: |R[1,:]| . h, row 1 of the rotation matrix from the quaternion
        x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
        r1 = np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1)
        low = np.minimum(low, p[:, 1] - np.abs(r1) @ h)
    lift = np.where(low < floor - 0.02, floor - low, 0.0)
    if np.any(lift > 0):
        parts = chain(hip_world + lift[:, None] * np.array([0, 1.0, 0]))
    return parts


def hold_time(lt, d: float, hold: float):
    """A short clip covering a longer hold: played forth and back an odd number of times, re-timed slightly, so the
    hold starts on the clip's first frame and ends on its last (the neighbouring clips join without a pop)."""
    n = max(1, int(round(hold / d)))
    if n % 2 == 0:
        n += 1 if hold / d >= n else -1
    n = max(1, n)
    u = np.asarray(lt, float) * (n * d / hold)
    k = np.floor(u / d)
    r = u - k * d
    return np.where(k % 2 == 0, r, d - r).clip(0, d) if np.ndim(u) else (r if int(k) % 2 == 0 else d - r)


def pose_actor_frames(actor: dict, times: np.ndarray) -> dict:
    """All frames of one actor: {part: (pos (n,3), quat (n,4))}, clips switched as the director does."""
    clips = actor["clips"]
    starts = np.array([c["s"] for c in clips])
    k = np.clip(np.searchsorted(starts, times + 1e-6, side="right") - 1, 0, len(clips) - 1)
    out = {nm: (np.zeros((len(times), 3)), np.zeros((len(times), 4))) for nm in SIZES}
    for ci in np.unique(k):
        m = k == ci
        c = clips[ci]
        lt = np.clip(times[m] - c["s"], 0, c["d"])
        if c.get("hold") and c["hold"] > c["d"] + 0.05:
            lt = hold_time(np.clip(times[m] - c["s"], 0, c["hold"]), c["d"], c["hold"])
        r = pose_r6_vec(clip(c["m"]), lt, (c["x"], c.get("y", 0.0), c["z"]), c["yaw"], actor.get("arms", 1.0))
        for nm, (p, q) in r.items():
            out[nm][0][m] = p
            out[nm][1][m] = q
    return out
