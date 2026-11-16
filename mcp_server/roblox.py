"""Roblox bridge: retarget a Promptimate (SOMA 30-joint) motion onto the Roblox R15 rig.

Export format (JSON, compact): per frame and per R15 part, the part's WORLD rotation (quaternion x, y, z, w) in
Roblox space relative to the clip's start (character facing -Z, Y up, right-handed), plus the root (LowerTorso)
position in units of standing hip height, so any avatar size works. The Luau player
(`roblox/PromptimatePlayer.lua`) turns those into Motor6D.Transform values using the rig's own C0/C1, so custom R15
avatars (Rthro, blocky, user bundles) play the same data.

Retarget method: bone-direction matching, independent of rest poses (SOMA's rest is a T-pose, R15's has the arms
down). For each R15 part, R_part maps the part's rest primary axis (e.g. "down" for an upper arm) onto the SOMA bone
direction at that frame and its rest secondary axis ("forward") onto the SOMA joint's forward axis, orthonormalised.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

import motion

# Kimodo space: Y up, right-handed, faces +Z, +X = character's left.
# Roblox space: Y up, right-handed, characters face -Z (LookVector), +X = character's right.
# A 180 degree turn about Y maps one onto the other.
K2R = np.diag([-1.0, 1.0, -1.0])
EXPORT_VERSION = "2"   # bump when the clip data changes (Studio re-uploads clip modules)
SOMA_HIP_HEIGHT = 0.95   # m, hips height of the standing SOMA rest pose (motion.OFFSETS[0, 1] ~ 0.988, ~0.95 walking)

UP, DOWN, FWD = np.array([0.0, 1.0, 0.0]), np.array([0.0, -1.0, 0.0]), np.array([0.0, 0.0, 1.0])

# R15 part -> (primary: ("bone", from_joint, to_joint) | ("axis", joint, rest_axis_in_joint_frame),
#              rest primary axis of the R15 part, secondary joint whose forward axis gives the twist,
#              rest secondary axis of the R15 part). Kimodo-space vectors; joints are SOMA indices (motion.NAMES).
PARTS = {
    "LowerTorso":    (("axis", 0, UP), UP, 0, FWD),
    "UpperTorso":    (("axis", 3, UP), UP, 3, FWD),
    "Head":          (("axis", 6, UP), UP, 6, FWD),
    "LeftUpperArm":  (("bone", 11, 12), DOWN, 11, FWD),
    "LeftLowerArm":  (("bone", 12, 13), DOWN, 12, FWD),
    "LeftHand":      (("bone", 13, 15), DOWN, 13, FWD),
    "RightUpperArm": (("bone", 17, 18), DOWN, 17, FWD),
    "RightLowerArm": (("bone", 18, 19), DOWN, 18, FWD),
    "RightHand":     (("bone", 19, 21), DOWN, 19, FWD),
    "LeftUpperLeg":  (("bone", 22, 23), DOWN, 22, FWD),
    "LeftLowerLeg":  (("bone", 23, 24), DOWN, 23, FWD),
    "LeftFoot":      (("axis", 24, UP), UP, 24, FWD),
    "RightUpperLeg": (("bone", 26, 27), DOWN, 26, FWD),
    "RightLowerLeg": (("bone", 27, 28), DOWN, 27, FWD),
    "RightFoot":     (("axis", 28, UP), UP, 28, FWD),
}
ORDER = list(PARTS)
# Motor6D hierarchy of the standard R15 rig: part -> (parent part, motor name)
MOTORS = {
    "LowerTorso": ("HumanoidRootPart", "Root"), "UpperTorso": ("LowerTorso", "Waist"), "Head": ("UpperTorso", "Neck"),
    "LeftUpperArm": ("UpperTorso", "LeftShoulder"), "LeftLowerArm": ("LeftUpperArm", "LeftElbow"),
    "LeftHand": ("LeftLowerArm", "LeftWrist"), "RightUpperArm": ("UpperTorso", "RightShoulder"),
    "RightLowerArm": ("RightUpperArm", "RightElbow"), "RightHand": ("RightLowerArm", "RightWrist"),
    "LeftUpperLeg": ("LowerTorso", "LeftHip"), "LeftLowerLeg": ("LeftUpperLeg", "LeftKnee"),
    "LeftFoot": ("LeftLowerLeg", "LeftAnkle"), "RightUpperLeg": ("LowerTorso", "RightHip"),
    "RightLowerLeg": ("RightUpperLeg", "RightKnee"), "RightFoot": ("RightLowerLeg", "RightAnkle"),
}


def _global_rotations(rot: np.ndarray) -> np.ndarray:
    local = motion.quat_to_mat(rot).astype(np.float64)
    g = np.empty_like(local)
    for j, p in enumerate(motion.PARENTS):
        g[:, j] = local[:, j] if p < 0 else g[:, p] @ local[:, j]
    return g


def _frame(primary: np.ndarray, secondary: np.ndarray) -> np.ndarray:
    """Orthonormal basis (columns: primary, secondary-perp, primary x secondary) for (F,3) inputs -> (F,3,3)."""
    a = primary / np.linalg.norm(primary, axis=-1, keepdims=True)
    s = secondary - np.sum(secondary * a, axis=-1, keepdims=True) * a
    s /= np.linalg.norm(s, axis=-1, keepdims=True) + 1e-12
    return np.stack([a, s, np.cross(a, s)], axis=-1)


def _mat_to_quat(m: np.ndarray) -> np.ndarray:
    """(F,3,3) -> (F,4) xyzw, sign-continuous over time."""
    F = m.shape[0]
    q = np.empty((F, 4))
    tr = m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2]
    for i in range(F):
        r = m[i]
        if tr[i] > 0:
            s = 2.0 * np.sqrt(tr[i] + 1.0)
            q[i] = [(r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, 0.25 * s]
        elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
            s = 2.0 * np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2])
            q[i] = [0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s, (r[2, 1] - r[1, 2]) / s]
        elif r[1, 1] > r[2, 2]:
            s = 2.0 * np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2])
            q[i] = [(r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s, (r[0, 2] - r[2, 0]) / s]
        else:
            s = 2.0 * np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1])
            q[i] = [(r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s, (r[1, 0] - r[0, 1]) / s]
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    for i in range(1, F):
        if np.dot(q[i], q[i - 1]) < 0:
            q[i] = -q[i]
    return q


def retarget(root: np.ndarray, rot: np.ndarray) -> dict:
    """SOMA motion -> {"rot": {part: (F,3,3) Roblox-space world rotation}, "root": (F,3) in hip heights}."""
    pos = motion.fk(root, rot).astype(np.float64)
    g = _global_rotations(rot)
    out = {}
    for part, (prim, rest_prim, sec_joint, rest_sec) in PARTS.items():
        if prim[0] == "bone":
            d = pos[:, prim[2]] - pos[:, prim[1]]
        else:
            d = g[:, prim[1]] @ prim[2]
        s = g[:, sec_joint] @ FWD
        target = _frame(d, s)                                     # Kimodo space
        rest = _frame(rest_prim[None], rest_sec[None])[0]         # R15 rest, Kimodo space
        r_k = target @ rest.T                                     # R_part (Kimodo space)
        out[part] = K2R @ r_k @ K2R                               # same rotation expressed in Roblox space
    lt = (pos[:, 0] - pos[:1, 0] * np.array([1, 0, 1])) @ K2R     # hips; x/z relative to the start, y absolute
    return {"rot": out, "root": lt / SOMA_HIP_HEIGHT}


# Hands near the body are placed by WHERE they are on the body, not by copying arm angles: R15 torsos, heads and
# thighs are far thicker than the source body, so copied angles put a hand resting in the lap, at the ear or on the
# chest inside the blocky part. Each wrist is described relative to the source body's boxes (same part frames as the
# R15 parts the retarget drives): the closest point on the box surface (normalised to the box's half-size) and the
# wrist's clearance above it. The player puts the rig's wrist at the same spot on the rig's part, at the same
# clearance plus the rig's forearm thickness, with arm IK.
# part -> (SOMA joint the box hangs off (None: thigh bone), centre offset and half-size in the part's rest frame
# (Kimodo axes: x left, y up, z forward), metres)
BODY_BOXES = {
    "UpperTorso": (3, (0.0, 0.13, -0.01), (0.165, 0.16, 0.11)),
    "LowerTorso": (0, (0.0, 0.04, 0.0), (0.16, 0.09, 0.11)),
    "Head": (6, (0.0, 0.06, 0.02), (0.085, 0.115, 0.10)),
    "LeftUpperLeg": (None, (22, 23), (0.075, None, 0.075)),
    "RightUpperLeg": (None, (26, 27), (0.075, None, 0.075)),
}
BOX_ORDER = list(BODY_BOXES)
WRISTS = {"Left": 13, "Right": 19}
WRIST_R = 0.035          # m, source forearm half-thickness at the wrist
NEAR_IN, NEAR_OUT = 0.06, 0.22   # m clearance: full surface placement below NEAR_IN, none above NEAR_OUT


def _hand_spots(root: np.ndarray, rot: np.ndarray, rt: dict) -> list[list[float]]:
    """Per frame: for each wrist (Left, Right) [near weight, box1 index, q1(3), n1(3), e1, box2 index, q2(3), n2(3),
    e2, blend toward box2], with q = closest surface point / half-size, n = outward unit direction (part-local,
    Roblox axes), e = clearance beyond the source forearm radius in hip heights."""
    pos = motion.fk(root, rot).astype(np.float64)
    F = len(root)
    boxes = {}
    for part, (joint, off, half) in BODY_BOXES.items():
        R = K2R @ rt["rot"][part] @ K2R                  # part rotation, Kimodo space (rest frame -> world)
        if joint is None:
            a, b = off
            c = (pos[:, a] + pos[:, b]) / 2
            ln = np.linalg.norm(pos[:, b] - pos[:, a], axis=1)
            h = np.stack([np.full(F, half[0]), ln / 2, np.full(F, half[2])], 1)
        else:
            c = pos[:, joint] + np.einsum("fij,j->fi", R, np.array(off))
            h = np.tile(np.array(half), (F, 1))
        boxes[part] = (R, c, h)
    out = []
    for f in range(F):
        row = []
        for side in ("Left", "Right"):
            w = pos[f, WRISTS[side]]
            cand = []
            for bi, part in enumerate(BOX_ORDER):
                R, c, h = boxes[part]
                l = R[f].T @ (w - c[f])                    # box-local, Kimodo axes
                q = np.clip(l, -h[f], h[f])
                o = l - q
                d = float(np.linalg.norm(o))
                if d < 1e-6:                               # inside the source box: onto the nearest face
                    k = int(np.argmin(h[f] - np.abs(l)))
                    n = np.zeros(3); n[k] = 1.0 if l[k] >= 0 else -1.0
                    q = l.copy(); q[k] = h[f][k] * n[k]
                    d = -float(h[f][k] - abs(l[k]))
                else:
                    n = o / d
                cand.append((d, bi, (K2R @ (q / h[f])).tolist(), (K2R @ n).tolist(),
                             max(d - WRIST_R, 0.0) / SOMA_HIP_HEIGHT))
            cand.sort(key=lambda x: x[0])
            (d1, i1, q1, n1, e1), (d2, i2, q2, n2, e2) = cand[0], cand[1]
            near = float(np.clip((NEAR_OUT - d1) / (NEAR_OUT - NEAR_IN), 0, 1))
            near = near * near * (3 - 2 * near)
            blend = float(np.clip(0.5 - (d2 - d1) / 0.08, 0, 0.5))   # two boxes about as close: share
            row += [round(near, 3), i1, *[round(v, 3) for v in q1], *[round(v, 3) for v in n1], round(e1, 4),
                    i2, *[round(v, 3) for v in q2], *[round(v, 3) for v in n2], round(e2, 4), round(blend, 3)]
        out.append(row)
    return out


def _contacts(root: np.ndarray, rot: np.ndarray) -> list[int]:
    import postprocess
    c = postprocess.detect_contacts(motion.fk(root, rot).astype(np.float64))
    left = c["left_heel"] | c["left_toe"]
    right = c["right_heel"] | c["right_toe"]
    return [int(l) | (int(r) << 1) for l, r in zip(left, right)]


def export(motion_dir: Path, out_path: Path, name: str = "", loop: bool = False) -> Path:
    """Write the Roblox clip JSON for a Promptimate motion folder (raw f32 files)."""
    root, rot = motion.load(Path(motion_dir))
    rt = retarget(root, rot)
    q = {p: np.round(_mat_to_quat(rt["rot"][p]), 4) for p in ORDER}
    F = len(root)
    data = {
        "format": "promptimate-r15", "version": 1, "name": name or Path(motion_dir).name, "fps": motion.FPS,
        "frames": F, "loop": loop, "parts": ORDER,
        # rot[f] = [x,y,z,w for each part in `parts` order]; root[f] = [x,y,z] in hip heights (y = hips height)
        "rot": [[float(v) for p in ORDER for v in q[p][f]] for f in range(F)],
        "root": [[round(float(v), 4) for v in rt["root"][f]] for f in range(F)],
        # foot contacts per frame: bit 1 = left planted, bit 2 = right planted (the player pins planted feet
        # with leg IK on the R15 rig, since its proportions would otherwise bring foot sliding back)
        "contacts": _contacts(root, rot),
    }
    if os.environ.get("PROMPTIMATE_RBX_HANDS") == "1":
        # experimental (PromptimatePlayer selfCollide): hands near the body, placed by their spot on it
        data["handBoxes"] = BOX_ORDER
        data["hands"] = _hand_spots(root, rot, rt)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, separators=(",", ":")))
    return out_path


# ------------------------------------------------------------------------------------------------ validation

# Approximate standard R15 (blocky) joint offsets in studs, Roblox space, rest pose (arms down): child joint
# position relative to the parent's joint. Only used offline to check the retarget (directions, handedness).
R15_OFFSETS = {
    "LowerTorso": (0, 0, 0), "UpperTorso": (0, 0.2, 0), "Head": (0, 1.6, 0),
    "LeftUpperArm": (-1.25, 1.35, 0), "LeftLowerArm": (0, -1.0, 0), "LeftHand": (0, -0.9, 0),
    "RightUpperArm": (1.25, 1.35, 0), "RightLowerArm": (0, -1.0, 0), "RightHand": (0, -0.9, 0),
    "LeftUpperLeg": (-0.5, -0.2, 0), "LeftLowerLeg": (0, -1.2, 0), "LeftFoot": (0, -1.25, 0),
    "RightUpperLeg": (0.5, -0.2, 0), "RightLowerLeg": (0, -1.2, 0), "RightFoot": (0, -1.25, 0),
}
CHILD = {"LeftUpperArm": "LeftLowerArm", "LeftLowerArm": "LeftHand", "RightUpperArm": "RightLowerArm",
         "RightLowerArm": "RightHand", "LeftUpperLeg": "LeftLowerLeg", "LeftLowerLeg": "LeftFoot",
         "RightUpperLeg": "RightLowerLeg", "RightLowerLeg": "RightFoot"}
SOMA_BONE = {"LeftUpperArm": (11, 12), "LeftLowerArm": (12, 13), "RightUpperArm": (17, 18), "RightLowerArm": (18, 19),
             "LeftUpperLeg": (22, 23), "LeftLowerLeg": (23, 24), "RightUpperLeg": (26, 27), "RightLowerLeg": (27, 28)}


def r15_fk(rt: dict) -> dict:
    """Joint positions of the R15 rig (studs, Roblox space) driven by retargeted world rotations."""
    F = next(iter(rt["rot"].values())).shape[0]
    pos = {"LowerTorso": np.zeros((F, 3))}
    for part, (parent, _) in MOTORS.items():
        if part == "LowerTorso":
            continue
        pos[part] = pos[parent] + rt["rot"][parent] @ np.array(R15_OFFSETS[part], float)
    return pos


def validate(root: np.ndarray, rot: np.ndarray) -> dict:
    """Checks: limb directions match SOMA (deg), left/right not swapped, facing preserved."""
    rt = retarget(root, rot)
    soma = motion.fk(root, rot).astype(np.float64) @ K2R
    rp = r15_fk(rt)
    errs = {}
    for part, (a, b) in SOMA_BONE.items():
        d_s = soma[:, b] - soma[:, a]
        d_r = rp[CHILD[part]] - rp[part]
        cos = np.sum(d_s * d_r, axis=1) / (np.linalg.norm(d_s, axis=1) * np.linalg.norm(d_r, axis=1))
        errs[part] = float(np.degrees(np.arccos(np.clip(cos, -1, 1))).max())
    # handedness: R15 left shoulder must be on the side SOMA's left shoulder is
    lr_soma = soma[:, 11] - soma[:, 17]
    lr_r15 = rp["LeftUpperArm"] - rp["RightUpperArm"]
    hand_ok = float((np.sum(lr_soma * lr_r15, axis=1) > 0).mean())
    # facing: torso forward (-Z rotated) vs SOMA facing (left x up)
    fwd_r15 = rt["rot"]["LowerTorso"] @ np.array([0, 0, -1.0])
    left = soma[:, 22] - soma[:, 26]
    fwd_soma = np.cross(left, np.array([0, 1.0, 0]))   # right-handed: left x up = forward
    fwd_soma[:, 1] = 0
    cosf = np.sum(fwd_r15 * fwd_soma, axis=1) / (np.linalg.norm(fwd_r15, axis=1) * np.linalg.norm(fwd_soma, axis=1) + 1e-9)
    return {"limb_dir_err_max_deg": round(max(errs.values()), 3), "per_limb_deg": {k: round(v, 3) for k, v in errs.items()},
            "handedness_ok_ratio": round(hand_ok, 3), "facing_err_max_deg": round(float(np.degrees(np.arccos(np.clip(cosf, -1, 1))).max()), 2)}


if __name__ == "__main__":
    import sys
    d = Path(sys.argv[1])
    print(json.dumps(validate(*motion.load(d)), indent=2))
    if len(sys.argv) > 2:
        print(export(d, Path(sys.argv[2])))


def export_luau(motion_dir: Path, out_path: Path, name: str = "", loop: bool = False) -> Path:
    """Same data as export(), wrapped as a Luau ModuleScript source that returns the JSON string (drop it into
    ReplicatedStorage and `PromptimatePlayer.decode(require(module))`)."""
    tmp = export(motion_dir, Path(out_path).with_suffix(".json"), name, loop)
    body = tmp.read_text()
    eq = "=" * 4
    while f"]{eq}]" in body:
        eq += "="
    src = (f"-- Promptimate R15 clip '{name or Path(motion_dir).name}' (generated; play with PromptimatePlayer)\n"
           f"return [{eq}[{body}]{eq}]\n")
    out_path = Path(out_path)
    out_path.write_text(src, encoding="utf-8")
    return out_path
