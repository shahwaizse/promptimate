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
