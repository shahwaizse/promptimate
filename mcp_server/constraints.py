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
# Hips joint height above the seat surface when seated upright (SOMA skeleton; measured as the median gap between the
# hips joint and the mesh's seat contact over the render cast, see demo/shorts_template/README.md).
SEAT_HIPS_OFFSET = 0.17  # SOMA's pelvis root is ~8.5 cm above the hip joints, which sit ~8.5 cm above the seat
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
        pts = sorted((self._frame(min(round(s * motion.FPS), self.frames - 1)), x, z) for s, x, z in waypoints)
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

    def hips_height(self, t: int, y: float) -> "Constraints":
        """Hips joint height (feature 1, metres above the floor) at frame t."""
        t = self._frame(t)
        self.observed[t, 1] = y
        self.mask[t, 1] = 1.0
        return self

    def seat(self, t0: int, t1: int, height: float, x: float | None = None, z: float | None = None,
             heading: float | None = None, legs: str = "full", ease: int = 24, ease_out: bool = True) -> "Constraints":
        """Seated on a seat whose top is `height` m above the floor for frames t0..t1 inclusive. The model ignores a
        lone hips-height mask (it was trained on root, end-effector and full-body masks), so this pins a seated
        lower body like an end-effector constraint: hips (height + SEAT_HIPS_OFFSET), legs and feet from
        seated_pose(), plus the ground position (x, z) and the facing (heading, radians, default the clip's initial
        facing). The upper body stays free. legs: "full" (hips, thighs, knees, feet) | "feet" (hips and feet only)."""
        h = 0.0 if heading is None else float(heading)
        row = seated_pose_features(height, h, 0.0 if x is None else x, 0.0 if z is None else z)
        joints = [0, 24, 25, 28, 29] if legs == "feet" else [0, 22, 23, 24, 25, 26, 27, 28, 29]
        if row is None:  # seat too high for the feet to reach the floor: hips and thighs only
            row = seated_pose_features(height, h, 0.0 if x is None else x, 0.0 if z is None else z, feet=False)
            joints = [0, 22, 23, 26, 27]
        cols = [1, 3, 4] + [POS0 + 3 * j + k for j in joints for k in range(3)]
        cols += [ROT0 + 6 * j + k for j in (24, 28) if j in joints for k in range(6)]
        body = list(cols)
        if x is not None and z is not None:
            cols += [0, 2]
        t0, t1 = self._frame(t0), self._frame(t1)
        for t in range(t0, t1 + 1):
            self.observed[t, cols] = row[cols]
            self.mask[t, cols] = 1.0
        # Eased transitions from standing into the seat (and back out when the clip goes on): without them the model
        # drops to the floor first and is then pulled up onto the seat. Root-relative body only, so the approach
        # path stays free.
        if ease > 0:
            stand = load_pose("idle")
            seated = seated_pose(height, feet=row is not None and legs != "hips")
            if seated is None:
                seated = seated_pose(height, feet=False)
            for k in range(1, ease + 1):
                w = 0.5 - 0.5 * np.cos(np.pi * k / (ease + 1))           # 0..1 towards seated
                r, q = blend_pose(stand, seated, w)
                r, q = transform(r, q, 0.0, 0.0, h)
                frow = pose_features(r, q)
                for t in (t0 - (ease + 1 - k),) + ((t1 + (ease + 1 - k),) if ease_out else ()):
                    if 0 <= t < self.frames and (t < t0 or t > t1) and not self.mask[t, 1]:
                        self.observed[t, body] = frow[body]
                        self.mask[t, body] = 1.0
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


def _rx(a: float) -> np.ndarray:
    return np.array([np.sin(a / 2), 0.0, 0.0, np.cos(a / 2)])


def seated_pose(height: float, feet: bool = True) -> tuple[np.ndarray, np.ndarray] | None:
    """Canonical seated pose (origin, facing +Z) on a seat `height` m high: the idle pose with the hips at
    height + SEAT_HIPS_OFFSET, each thigh pitched forward so the shin hangs vertically and the ankle lands at its idle
    height above the floor (feet flat, where they were in global orientation). None when the seat is too high (or low)
    for the feet to reach the floor that way; feet=False then gives thighs horizontal-ish and the feet free."""
    from postprocess import qinv, qmul, qnorm
    root, rot = load_pose("idle")
    root = np.asarray(root, np.float64).copy()
    rot = np.asarray(rot, np.float64).copy()
    p0 = motion.fk(root[None].astype(np.float32), rot[None].astype(np.float32))[0]
    root[1] = float(height) + SEAT_HIPS_OFFSET

    def glob(q):
        g = [None] * J
        for j, par in enumerate(motion.PARENTS):
            g[j] = q[j] if par < 0 else qmul(g[par], q[j])
        return g

    for hip, knee, ankle in ((22, 23, 24), (26, 27, 28)):
        g0 = glob(rot)
        ankle_y0 = float(p0[ankle, 1])

        def place(a):
            q = rot.copy()
            gt = qmul(_rx(-a), g0[hip])                      # thigh pitched forward by a (about the global X axis)
            q[hip] = qnorm(qmul(qinv(g0[motion.PARENTS[hip]]), gt))
            q[knee] = qnorm(qmul(qinv(gt), g0[knee]))       # shin keeps its idle (vertical) global orientation
            return q

        def ankle_y(a):
            q = place(a)
            return float(motion.fk(root[None].astype(np.float32), q[None].astype(np.float32))[0][ankle, 1])

        lo, hi = np.radians(20), np.radians(120)
        if not feet:
            rot = place(np.radians(80))
            continue
        if not (ankle_y(lo) <= ankle_y0 + 1e-4 <= ankle_y(hi) + 2e-4):  # the ankle rises as the thigh pitches up
            return None
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (lo, mid) if ankle_y(mid) > ankle_y0 else (mid, hi)
        rot = place(0.5 * (lo + hi))
    return root.astype(np.float32), rot.astype(np.float32)


def blend_pose(a: tuple[np.ndarray, np.ndarray], b: tuple[np.ndarray, np.ndarray], w: float):
    """Per-joint slerp of local rotations and lerp of the hips position between two canonical poses."""
    ra, qa = np.asarray(a[0], np.float64), np.asarray(a[1], np.float64)
    rb, qb = np.asarray(b[0], np.float64), np.asarray(b[1], np.float64)
    qb = np.where(np.sum(qa * qb, axis=-1, keepdims=True) < 0, -qb, qb)
    d = np.clip(np.sum(qa * qb, axis=-1, keepdims=True), -1, 1)
    th = np.arccos(d)
    sn = np.sin(th)
    small = sn < 1e-5
    wa = np.where(small, 1 - w, np.sin((1 - w) * th) / np.where(small, 1, sn))
    wb = np.where(small, w, np.sin(w * th) / np.where(small, 1, sn))
    q = wa * qa + wb * qb
    q /= np.linalg.norm(q, axis=-1, keepdims=True)
    return (ra + w * (rb - ra)).astype(np.float32), q.astype(np.float32)


def seated_pose_features(height: float, heading: float, x: float, z: float, feet: bool = True) -> np.ndarray | None:
    """Feature row of seated_pose turned to `heading` (radians) with the hips at (x, z)."""
    p = seated_pose(height, feet)
    if p is None:
        return None
    r, q = transform(p[0], p[1], 0.0, 0.0, heading)
    r = np.asarray(r, np.float32).copy()
    r[0], r[2] = x, z
    return pose_features(r, q)


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
