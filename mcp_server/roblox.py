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
from pathlib import Path

import numpy as np

import motion

# Kimodo space: Y up, right-handed, faces +Z, +X = character's left.
# Roblox space: Y up, right-handed, characters face -Z (LookVector), +X = character's right.
# A 180 degree turn about Y maps one onto the other.
K2R = np.diag([-1.0, 1.0, -1.0])
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
    }
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
