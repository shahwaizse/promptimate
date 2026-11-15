"""Motion constraints for the Promptimate-patched kimodo.cpp engine (inpainting through the model's observed-feature mask).

Kimodo was trained with constraint conditioning: a raw motion-feature tensor plus a per-feature mask. The patched
engine accepts them as a binary file (``constraints=PATH`` in the V2 request) laid out as
    int32 frames, int32 dim, float32 observed[frames*dim], float32 mask[frames*dim]
in raw (unnormalised) Kimodo feature space over the global output timeline. Feature layout for SOMA-30 (D = 9 + 12J):
    [0:5]          global root x, hips y, root z, cos(heading), sin(heading)
    [5:5+3J]       joint positions, x/z relative to the root, y absolute
    [5+3J:5+9J]    global joint rotations as 6D (first two matrix columns)
    [5+9J:9+12J]   joint velocities and 4 foot contacts (never constrained here)
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

import motion

J = motion.J
D = 9 + 12 * J
POS0 = 5
ROT0 = 5 + 3 * J
RIGHT_HIP, LEFT_HIP = 26, 22
END_EFFECTORS = (24, 28, 13, 19)  # left foot, right foot, left hand, right hand


def heading_angle(pos: np.ndarray) -> np.ndarray:
    """Kimodo heading convention (radians) from global joint positions (..., J, 3). 0 = facing +Z."""
    d = pos[..., RIGHT_HIP, :] - pos[..., LEFT_HIP, :]
    return np.arctan2(d[..., 2], -d[..., 0])


def global_rotations(rot: np.ndarray) -> np.ndarray:
    local = motion.quat_to_mat(rot)
    g = np.empty_like(local)
    for j, p in enumerate(motion.PARENTS):
        g[:, j] = local[:, j] if p < 0 else g[:, p] @ local[:, j]
    return g


def features(root: np.ndarray, rot: np.ndarray) -> np.ndarray:
    """Raw constraint features (F, D) for a decoded motion. The smoothed global root is approximated by the hips."""
    pos = motion.fk(root, rot)
    g = global_rotations(rot)
    F = root.shape[0]
    f = np.zeros((F, D), dtype=np.float32)
    h = heading_angle(pos)
    f[:, 0], f[:, 1], f[:, 2], f[:, 3], f[:, 4] = root[:, 0], root[:, 1], root[:, 2], np.cos(h), np.sin(h)
    rel = pos.copy()
    rel[..., 0] -= root[:, None, 0]
    rel[..., 2] -= root[:, None, 2]
    f[:, POS0:ROT0] = rel.reshape(F, -1)
    six = np.concatenate([g[..., :, 0], g[..., :, 1]], axis=-1)  # (F, J, 6): col0 then col1
    f[:, ROT0:ROT0 + 6 * J] = six.reshape(F, -1)
    return f


class Constraints:
    """Builder over a fixed output timeline of `frames` frames (30 fps)."""

    def __init__(self, frames: int):
        self.frames = int(frames)
        self.observed = np.zeros((self.frames, D), dtype=np.float32)
        self.mask = np.zeros((self.frames, D), dtype=np.float32)

    def _frame(self, t: int) -> int:
        t = int(t)
        if t < 0:
            t += self.frames
        if not 0 <= t < self.frames:
            raise ValueError(f"constraint frame {t} outside 0..{self.frames - 1}")
        return t

    def root_xz(self, t: int, x: float, z: float) -> "Constraints":
        t = self._frame(t)
        self.observed[t, 0], self.observed[t, 2] = x, z
        self.mask[t, [0, 2]] = 1.0
        return self

    def heading(self, t: int, radians: float) -> "Constraints":
        t = self._frame(t)
        self.observed[t, 3], self.observed[t, 4] = np.cos(radians), np.sin(radians)
        self.mask[t, [3, 4]] = 1.0
        return self

    def root_path(self, waypoints: list[tuple[float, float, float]], dense: bool = True) -> "Constraints":
        """waypoints: (seconds, x, z) in metres. dense=True linearly interpolates a constraint on every frame
        between consecutive waypoints (a path), else only the waypoint frames are pinned."""
        pts = sorted((self._frame(round(s * motion.FPS)) if s * motion.FPS < self.frames else self.frames - 1, x, z)
                     for s, x, z in waypoints)
        if not dense or len(pts) == 1:
            for t, x, z in pts:
                self.root_xz(t, x, z)
            return self
        for (t0, x0, z0), (t1, x1, z1) in zip(pts, pts[1:]):
            for t in range(t0, t1 + 1):
                a = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                self.root_xz(t, x0 + a * (x1 - x0), z0 + a * (z1 - z0))
        return self

    def hold_still(self, t0: int, t1: int, x: float, z: float) -> "Constraints":
        """Root stays at (x, z) for frames t0..t1 inclusive (the 'actually stops' fix)."""
        for t in range(self._frame(t0), self._frame(t1) + 1):
            self.root_xz(t, x, z)
        return self

    def pose(self, t: int, feat_row: np.ndarray, root_xz: bool = True) -> "Constraints":
        """Full-body keyframe from a feature row (see `features`), masked like kimodo's sequence transitions:
        root, all joint positions and end-effector rotations. root_xz=False leaves horizontal placement free."""
        t = self._frame(t)
        self.observed[t, :ROT0] = feat_row[:ROT0]
        self.mask[t, :ROT0] = 1.0
        if not root_xz:
            self.mask[t, [0, 2]] = 0.0
        for j in END_EFFECTORS:
            sl = slice(ROT0 + 6 * j, ROT0 + 6 * j + 6)
            self.observed[t, sl] = feat_row[sl]
            self.mask[t, sl] = 1.0
        return self

    def copy(self) -> "Constraints":
        c = Constraints(self.frames)
        c.observed[:], c.mask[:] = self.observed, self.mask
        return c

    @property
    def empty(self) -> bool:
        return not self.mask.any()

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(struct.pack("<ii", self.frames, D))
            fh.write(self.observed.astype("<f4").tobytes())
            fh.write(self.mask.astype("<f4").tobytes())
        return path


# ------------------------------------------------------------------------------------------- canonical poses / chaining
# A "pose" here is one frame: (root (3,), rot (J, 4)) in Kimodo space (hips position, local xyzw rotations with
# joint 0 = global hips rotation). Clips are generated in a canonical frame (start at the origin facing +Z); the
# helpers below move frames and clips between that frame and world placements.
FIXTURES = Path(__file__).resolve().parent / "fixtures"
POSE_WINDOW = 4      # frames held exactly at a pinned start/end pose (zero velocity there -> clean Animator blends)
SNAP_BLEND = 10      # frames over which post-processing eases back onto the exact pinned pose


def _yaw_q(a: float) -> np.ndarray:
    return np.array([0.0, np.sin(a / 2), 0.0, np.cos(a / 2)])


def _qmul(a, b):
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], axis=-1)


def transform(root: np.ndarray, rot: np.ndarray, x: float, z: float, yaw: float) -> tuple[np.ndarray, np.ndarray]:
    """Rigidly move a clip/frame: rotate by `yaw` (radians, Kimodo heading convention) about the origin's vertical
    axis, then translate by (x, z). Works on (F,3)/(F,J,4) or (3,)/(J,4)."""
    root = np.asarray(root, np.float64)
    rot = np.asarray(rot, np.float64)
    c, s = np.cos(yaw), np.sin(yaw)
    r = root.copy()
    r[..., 0] = c * root[..., 0] + s * root[..., 2] + x
    r[..., 2] = -s * root[..., 0] + c * root[..., 2] + z
    q = rot.copy()
    q[..., 0, :] = _qmul(np.broadcast_to(_yaw_q(yaw), rot[..., 0, :].shape), rot[..., 0, :])
    return r.astype(np.float32), q.astype(np.float32)


def rebase(root, rot, x: float, z: float, heading: float):
    """Inverse of transform: the placement (x, z, heading) becomes the origin facing +Z."""
    r = np.asarray(root, np.float64).copy()
    r[..., 0] -= x
    r[..., 2] -= z
    return transform(r, rot, 0.0, 0.0, -heading)


def frame_placement(root: np.ndarray, rot: np.ndarray, f: int) -> tuple[float, float, float]:
    """(hips x, hips z, Kimodo heading) of frame f."""
    p = motion.fk(root[f:f + 1], rot[f:f + 1])[0]
    return float(root[f, 0]), float(root[f, 2]), float(heading_angle(p))


FEET = (24, 25, 28, 29)  # ankles and toes


def fit_placement(root: np.ndarray, rot: np.ndarray, f: int, pose: tuple[np.ndarray, np.ndarray],
                  search_deg: float = 15.0) -> tuple[float, float, float]:
    """Placement (x, z, heading) of a canonical pose that puts its feet where frame f's feet are (least squares on
    ankles and toes, ground plane). Snapping to that placement moves the planted feet as little as possible."""
    pf = motion.fk(root[f:f + 1], rot[f:f + 1])[0][list(FEET)][:, [0, 2]].astype(np.float64)
    pr, pq = np.asarray(pose[0], np.float32)[None], np.asarray(pose[1], np.float32)[None]
    cf = motion.fk(pr, pq)[0][list(FEET)][:, [0, 2]].astype(np.float64)
    h0 = frame_placement(root, rot, f)[2]
    best = None
    for h in h0 + np.radians(np.arange(-search_deg, search_deg + 1e-9, 0.25)):
        c, s = np.cos(h), np.sin(h)
        rx, rz = c * cf[:, 0] + s * cf[:, 1], -s * cf[:, 0] + c * cf[:, 1]
        t = pf.mean(axis=0) - np.array([rx.mean(), rz.mean()])
        err = float(((rx + t[0] - pf[:, 0]) ** 2 + (rz + t[1] - pf[:, 1]) ** 2).sum())
        if best is None or err < best[0]:
            best = (err, float(t[0]), float(t[1]), float(h))
    return best[1], best[2], best[3]


def load_pose(name: str) -> tuple[np.ndarray, np.ndarray]:
    """Canonical fixture pose (origin, facing +Z), e.g. "idle" -> fixtures/idle_pose.json."""
    d = json.loads((FIXTURES / f"{name}_pose.json").read_text())
    return np.array(d["root"], np.float32), np.array(d["rot"], np.float32)


def pose_features(root: np.ndarray, rot: np.ndarray) -> np.ndarray:
    """Feature row (D,) of a single pose."""
    return features(np.asarray(root, np.float32)[None], np.asarray(rot, np.float32)[None])[0]


def pose_distance(a: tuple[np.ndarray, np.ndarray], b: tuple[np.ndarray, np.ndarray]) -> dict:
    """How far apart two poses are as the body looks (both re-based to the origin facing +Z, so a rigid move of the
    whole character doesn't count): mean / max joint position distance (cm), hips height difference (cm), max joint
    rotation difference (deg), and the heading difference (deg) before re-basing."""
    out = {}
    placed = []
    for r, q in (a, b):
        r = np.asarray(r, np.float32)[None]
        q = np.asarray(q, np.float32)[None]
        x, z, h = frame_placement(r, q, 0)
        placed.append((rebase(r, q, x, z, h), h))
    (ra, qa), ha = placed[0]
    (rb, qb), hb = placed[1]
    pa, pb = motion.fk(ra, qa)[0], motion.fk(rb, qb)[0]
    dj = np.linalg.norm(pa - pb, axis=-1)
    dq = np.abs(np.sum(qa[0] * qb[0], axis=-1))
    out["joint_mean_cm"] = round(float(dj.mean() * 100), 2)
    out["joint_max_cm"] = round(float(dj.max() * 100), 2)
    out["hips_height_cm"] = round(float(abs(ra[0, 1] - rb[0, 1]) * 100), 2)
    out["rot_max_deg"] = round(float(np.degrees(2 * np.arccos(np.clip(dq, 0, 1))).max()), 2)
    out["heading_deg"] = round(float(np.degrees((ha - hb + np.pi) % (2 * np.pi) - np.pi)), 2)
    return out


def snap_pose(root: np.ndarray, rot: np.ndarray, target: tuple[np.ndarray, np.ndarray], at: str,
              hold: int = POSE_WINDOW, blend: int | None = None, xz: bool = False) -> tuple[np.ndarray, np.ndarray, dict]:
    """Make the first (at="start") or last (at="end") `hold` frames exactly `target` (a placed pose: hips position
    and local rotations) and fade the correction out over the `blend` frames next to them. The correction is an
    offset (per-joint rotation delta and hips shift, scaled down smoothly), so the clip keeps its own velocities
    there instead of being dragged towards a frozen pose. Used after post-processing so foot locking, grounding or
    smoothing can't leave the pinned frames off-pose. xz=False keeps the clip's own horizontal hips position (only
    height and rotations snap). Returns (root, rot, info)."""
    from postprocess import qinv, qmul, qnorm, qpow
    root = np.asarray(root, np.float64).copy()
    rot = qnorm(np.asarray(rot, np.float64).copy())
    F = len(root)
    hold = max(1, min(hold, F))
    blend = SNAP_BLEND if blend is None else blend
    blend = max(0, min(blend, F - hold))
    ramp = 0.5 + 0.5 * np.cos(np.pi * (np.arange(1, blend + 1) / (blend + 1)))  # 1..0 smooth, excludes ends
    if at == "start":
        held, ref, ease = np.arange(hold), 0, np.arange(hold, hold + blend)
        edge = hold - 1
    else:
        held, ref, ease = np.arange(F - hold, F), F - 1, np.arange(F - hold - 1, F - hold - blend - 1, -1)
        edge = F - hold
    tr, tq = np.asarray(target[0], np.float64), np.asarray(target[1], np.float64)
    before = pose_distance((root[ref], rot[ref]), (tr, tq))
    axes = [0, 1, 2] if xz else [1]
    dq = qmul(tq, qinv(rot[edge]))                     # (J, 4) local delta at the hold's inner edge
    dq = np.where(dq[..., 3:4] < 0, -dq, dq)
    dr = tr - root[edge]
    if len(ease):
        rot[ease] = qnorm(qmul(qpow(np.broadcast_to(dq, rot[ease].shape), ramp[:, None]), rot[ease]))
        for a in axes:
            root[ease, a] += ramp * dr[a]
    tqh = np.where(np.sum(tq * rot[held], axis=-1, keepdims=True) < 0, -tq, tq)  # keep quaternion hemispheres
    rot[held] = tqh
    for a in axes:
        root[held, a] = tr[a]
    info = {"before": before, "after": pose_distance((root[ref], rot[ref]), (tr, tq)),
            "frames": int(len(held) + len(ease))}
    return root.astype(np.float32), rot.astype(np.float32), info
