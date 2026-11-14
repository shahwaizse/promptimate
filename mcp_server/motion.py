"""Load kimodo.cpp raw output (SOMA 30-joint), forward kinematics, preview rendering and export."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent / "vendor"  # Apache-2.0 exporters vendored from kimodo.cpp
FPS = 30.0

# SOMA compact 30-joint control skeleton, copied from kimodo.cpp scripts/export_glb.py (Apache-2.0).
NAMES = [
    "Hips", "Spine1", "Spine2", "Chest", "Neck1", "Neck2", "Head", "Jaw",
    "LeftEye", "RightEye", "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
    "LeftHandThumbEnd", "LeftHandMiddleEnd", "RightShoulder", "RightArm", "RightForeArm",
    "RightHand", "RightHandThumbEnd", "RightHandMiddleEnd", "LeftLeg", "LeftShin", "LeftFoot",
    "LeftToeBase", "RightLeg", "RightShin", "RightFoot", "RightToeBase",
]
PARENTS = [-1, 0, 1, 2, 3, 4, 5, 6, 6, 6, 3, 10, 11, 12, 13, 13, 3, 16, 17, 18, 19, 19, 0, 22, 23, 24, 0, 26, 27, 28]
OFFSETS = np.array([
    [0.0, 0.988, 0.0], [-0.00013727, 0.0500376256, -0.00053726669], [-1.86574103e-09, 0.0712530139, -0.000298248546],
    [-5.75188398e-09, 0.0755006305, -0.00815970992], [-0.00181676517, 0.263112953, -0.00553348292],
    [-2.85102231e-08, 0.0770939664, 0.0230258546], [-4.5975437e-08, 0.0612891595, 0.0195370861],
    [2.63687901e-05, 0.0047559225, 0.0309494062], [0.0320638079, 0.0538020513, 0.0758688308],
    [-0.0322244017, 0.05361869, 0.0755823359], [0.0162165175, 0.232371641, 0.0511341324],
    [0.149198457, 2.19397873e-08, -0.0550232576], [0.287393078, 2.50268389e-09, -2.58787737e-05],
    [0.270939812, -7.06625108e-09, 2.60897248e-05], [0.122686267, -0.0322017573, 0.0483306876],
    [0.190119595, -0.00312878387, -0.000339570373], [-0.0138011824, 0.231803086, 0.0521415786],
    [-0.150371962, 1.17387901e-07, -0.0554560437], [-0.287366393, 1.87628082e-08, -2.59709359e-05],
    [-0.271336198, -1.16767401e-09, 2.61269368e-05], [-0.122642483, -0.0321145448, 0.0480403904],
    [-0.190005945, -0.00306615542, -0.0003157343], [0.10043214, -0.0843452671, 0.0259565473],
    [-1e-08, -0.432217537, -0.00802912805], [1e-08, -0.421550959, -0.0348152298],
    [0.0, -0.0505947206, 0.132315294], [-0.10047278, -0.0829525995, 0.0262031695],
    [1e-08, -0.433622059, -0.00805555828], [2e-08, -0.421173943, -0.0347839785],
    [-3.42907669e-09, -0.0507960932, 0.132841956],
], dtype=np.float32)
J = len(NAMES)


def load(motion_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Returns root positions (F,3) and local rotations xyzw (F,J,4)."""
    root = np.fromfile(motion_dir / "root_positions.f32", dtype="<f4").reshape(-1, 3)
    rot = np.fromfile(motion_dir / "local_rotations_xyzw.f32", dtype="<f4").reshape(root.shape[0], J, 4)
    return root, rot


def quat_to_mat(q: np.ndarray) -> np.ndarray:
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    m = np.empty(q.shape[:-1] + (3, 3), dtype=np.float32)
    m[..., 0, 0] = 1 - 2 * (y * y + z * z); m[..., 0, 1] = 2 * (x * y - z * w); m[..., 0, 2] = 2 * (x * z + y * w)
    m[..., 1, 0] = 2 * (x * y + z * w); m[..., 1, 1] = 1 - 2 * (x * x + z * z); m[..., 1, 2] = 2 * (y * z - x * w)
    m[..., 2, 0] = 2 * (x * z - y * w); m[..., 2, 1] = 2 * (y * z + x * w); m[..., 2, 2] = 1 - 2 * (x * x + y * y)
    return m


def fk(root: np.ndarray, rot: np.ndarray) -> np.ndarray:
    """Global joint positions (F,J,3), Y-up, metres."""
    local = quat_to_mat(rot)
    F = root.shape[0]
    g_rot = np.empty((F, J, 3, 3), dtype=np.float32)
    pos = np.empty((F, J, 3), dtype=np.float32)
    for j, p in enumerate(PARENTS):
        if p < 0:
            g_rot[:, j] = local[:, j]
            pos[:, j] = root
        else:
            g_rot[:, j] = g_rot[:, p] @ local[:, j]
            pos[:, j] = pos[:, p] + np.einsum("fab,b->fa", g_rot[:, p], OFFSETS[j])
    return pos


def stats(pos: np.ndarray) -> dict:
    """Cheap sanity metrics so an agent can spot broken output without looking."""
    feet = pos[:, [24, 25, 28, 29], 1]
    root_xz = pos[:, 0, [0, 2]]
    travel = float(np.linalg.norm(root_xz[-1] - root_xz[0]))
    path = float(np.linalg.norm(np.diff(root_xz, axis=0), axis=1).sum())
    return {
        "frames": int(pos.shape[0]),
        "duration_s": round(pos.shape[0] / FPS, 2),
        "root_displacement_m": round(travel, 2),
        "root_path_length_m": round(path, 2),
        "min_foot_height_m": round(float(feet.min()), 3),
        "max_hips_height_m": round(float(pos[:, 0, 1].max()), 3),
        "min_hips_height_m": round(float(pos[:, 0, 1].min()), 3),
        "start_xz": [round(float(v), 2) for v in root_xz[0]],
        "end_xz": [round(float(v), 2) for v in root_xz[-1]],
    }


def render_preview(pos: np.ndarray, out_png: Path, title: str = "", n: int = 8) -> Path:
    """Contact sheet: n stick-figure frames (3/4 view) plus a top-down root trajectory."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    F = pos.shape[0]
    idx = np.linspace(0, F - 1, n).round().astype(int)
    a = np.radians(35)  # oblique camera: u = x cos a + z sin a, v = y
    fig, axes = plt.subplots(1, n + 1, figsize=(2.0 * (n + 1), 3.4), dpi=90)
    for k, f in enumerate(idx):
        ax = axes[k]
        p = pos[f] - np.array([pos[f, 0, 0], 0, pos[f, 0, 2]])  # centre on hips (xz)
        u = p[:, 0] * np.cos(a) + p[:, 2] * np.sin(a)
        v = p[:, 1]
        for j, par in enumerate(PARENTS):
            if par < 0:
                continue
            c = "tab:blue" if "Left" in NAMES[j] else ("tab:red" if "Right" in NAMES[j] else "k")
            ax.plot([u[par], u[j]], [v[par], v[j]], color=c, lw=2)
        ax.axhline(0, color="0.7", lw=1)
        ax.set_xlim(-0.9, 0.9); ax.set_ylim(-0.05, 2.0); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(f"t={f / FPS:.1f}s", fontsize=8)
    ax = axes[-1]
    ax.plot(pos[:, 0, 0], pos[:, 0, 2], "k-", lw=1)
    ax.plot(pos[0, 0, 0], pos[0, 0, 2], "go", ms=5)
    ax.plot(pos[-1, 0, 0], pos[-1, 0, 2], "rs", ms=5)
    ax.set_aspect("equal", adjustable="datalim"); ax.set_title("root path (x,z)\ngreen=start", fontsize=8)
    ax.tick_params(labelsize=6)
    fig.suptitle(title[:140], fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)
    return out_png


def export(motion_dir: Path) -> dict:
    """Write animation.glb (skinned bone-mesh glTF) and animation.bvh (cm) with the upstream scripts."""
    out = {}
    for script, name, extra in (("export_glb.py", "animation.glb", []), ("export_bvh.py", "animation.bvh", [])):
        target = motion_dir / name
        r = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), "--motion-dir", str(motion_dir),
                            "--output", str(target), *extra], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=120)
        out[name] = str(target) if r.returncode == 0 else f"failed: {r.stderr.strip()[-300:]}"
    return out


def write_skeleton_json(motion_dir: Path) -> Path:
    p = motion_dir / "skeleton.json"
    p.write_text(json.dumps({"names": NAMES, "parents": PARENTS, "offsets": OFFSETS.tolist(), "fps": FPS,
                             "up": "Y", "units": "m", "rotation_layout": "local xyzw per joint"}))
    return p


def write_kimodo_file(motion_dir: Path, target: Path, prompt: str) -> Path:
    """Single-file interchange for the Unity ScriptedImporter (extension .kimodo, JSON).
    Coordinates are Kimodo's (right-handed, Y-up, metres, character faces +Z); the importer converts."""
    root, rot = load(motion_dir)
    data = {
        "version": 1, "fps": FPS, "prompt": prompt, "frames": int(root.shape[0]), "joints": J,
        "names": NAMES, "parents": PARENTS,
        "offsets": [round(float(v), 7) for v in OFFSETS.reshape(-1)],
        "root": [round(float(v), 6) for v in root.reshape(-1)],
        "rot": [round(float(v), 6) for v in rot.reshape(-1)],
        # Independent ground truth for the Unity validator: global joint positions from our own FK (Kimodo space).
        "refPos": [round(float(v), 5) for v in fk(root, rot).reshape(-1)],
    }
    local = motion_dir / target.name
    local.write_text(json.dumps(data, separators=(",", ":")))
    if target != local:  # copy whole file in one go so Unity never sees a half-written asset
        import shutil
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, target)
    return target


def checks(pos: np.ndarray, prompt: str) -> dict:
    """Semantic sanity checks in Kimodo space (right-handed, Y-up). Mirrors the Unity validator's invariants."""
    up = np.array([0.0, 1.0, 0.0])
    left = pos[:, 22] - pos[:, 26]                     # LeftLeg - RightLeg
    left[:, 1] = 0
    fwd = np.cross(left, up)                          # right-handed: left x up = forward
    fwd /= np.linalg.norm(fwd, axis=1, keepdims=True) + 1e-9
    toes = []
    for foot, toe in ((24, 25), (28, 29)):
        v = pos[:, toe] - pos[:, foot]; v[:, 1] = 0
        toes.append((np.linalg.norm(v, axis=1) > 0.03, np.einsum("fi,fi->f", v, fwd) > 0))
    measurable = toes[0][0] & toes[1][0]
    toes_ok = (toes[0][1] & toes[1][1])[measurable].mean() if measurable.any() else 1.0
    lowest = pos[:, [24, 25, 28, 29], 1].min(axis=1)
    travel = pos[-1, 0] - pos[0, 0]; travel[1] = 0
    dist = float(np.linalg.norm(travel))
    def ang(a, b):
        return float(np.degrees(np.arccos(np.clip(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9), -1, 1))))
    out = {
        "initial_facing_deg_from_+Z": round(ang(fwd[0], np.array([0, 0, 1.0])), 1),
        "facing_vs_travel_deg": round(ang(fwd.mean(axis=0), travel), 1) if dist > 0.5 else None,
        "toes_forward_ratio": round(float(toes_ok), 2),
        "grounded_ratio": round(float((lowest < 0.10).mean()), 2),
        "min_foot_height_m": round(float(lowest.min()), 3),
    }
    fails = []
    if out["initial_facing_deg_from_+Z"] > 45: fails.append("does not start facing +Z")
    if out["facing_vs_travel_deg"] and out["facing_vs_travel_deg"] > 120 and "backward" not in prompt.lower():
        fails.append("moves opposite to facing")
    if out["toes_forward_ratio"] < 0.6: fails.append("feet point backwards")
    if out["grounded_ratio"] < 0.3: fails.append("feet rarely near ground")
    if out["min_foot_height_m"] < -0.08: fails.append("feet below ground")
    out["passed"] = not fails
    out["failures"] = fails
    return out
