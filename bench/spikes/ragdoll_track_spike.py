r"""Spike for docs/text-to-system.md: can a Promptimate clip drive an active ragdoll on this machine's CPU?

Builds a MuJoCo humanoid straight from the SOMA 30-joint skeleton (mcp_server/motion.py), tracks the clip with
per-joint PD torques plus a capped "balance assist" wrench on the pelvis, shoves the chest, and reports tracking
error, recovery and speed for a few reaction personalities. CPU only; needs `pip install mujoco numpy`.

    D:\tmp\t2s-venv\Scripts\python bench\spikes\ragdoll_track_spike.py output\walk_20261116_015815\take0
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import mujoco
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp_server"))
import motion as M  # noqa: E402

SIM = [0, 1, 2, 3, 4, 5, 6, 10, 11, 12, 13, 16, 17, 18, 19, 22, 23, 24, 25, 26, 27, 28, 29]
RADIUS = {0: .085, 1: .095, 2: .1, 3: .1, 4: .045, 5: .045, 10: .04, 11: .045, 12: .038, 13: .03,
          16: .04, 17: .045, 18: .038, 19: .03, 22: .07, 23: .05, 26: .07, 27: .05}
KP = {1: 500, 2: 500, 3: 500, 4: 60, 5: 60, 6: 40, 10: 150, 11: 120, 12: 80, 13: 15, 16: 150, 17: 120, 18: 80,
      19: 15, 22: 500, 23: 400, 24: 150, 25: 20, 26: 500, 27: 400, 28: 150, 29: 20}
DT = 0.002

# Reaction "personalities": what the text would choose. assist = fraction of the balance wrench kept while stunned,
# gain = fraction of joint stiffness kept while stunned, stun = seconds before both ramp back (None = never).
PERSONALITIES = {
    "stoic": dict(assist=1.0, gain=1.0, stun=0.0),
    "stagger": dict(assist=0.15, gain=0.45, stun=0.7),
    "knockout": dict(assist=0.0, gain=0.04, stun=None),
}


def build_xml(floor_y: float) -> str:
    kids = {j: [c for c in range(M.J) if M.PARENTS[c] == j] for j in range(M.J)}

    def body(j: int) -> str:
        o = M.OFFSETS[j] if j else np.zeros(3)
        s = f'<body name="{M.NAMES[j]}" pos="{o[0]:.5f} {o[1]:.5f} {o[2]:.5f}">'
        if j == 0:
            s += '<freejoint name="root"/>'
        else:
            kd = KP[j] / 10
            s += f'<joint name="j{j}" type="ball" damping="{kd}" armature="0.02"/>'
        name = M.NAMES[j]
        if name.endswith("Foot"):
            s += '<geom type="box" pos="0 -0.035 0.06" size="0.045 0.03 0.1"/>'
        elif name.endswith("ToeBase"):
            s += '<geom type="box" pos="0 0 0.035" size="0.045 0.015 0.04"/>'
        elif name == "Head":
            s += '<geom type="sphere" pos="0 0.08 0.02" size="0.1"/>'
        else:
            for c in kids[j]:
                if M.NAMES[c] in ("LeftHandThumbEnd", "RightHandThumbEnd"):
                    continue
                e = M.OFFSETS[c]
                s += f'<geom type="capsule" fromto="0 0 0 {e[0]:.5f} {e[1]:.5f} {e[2]:.5f}" size="{RADIUS.get(j, .04)}"/>'
        for c in kids[j]:
            if c in SIM:
                s += body(c)
        return s + "</body>"

    return f"""<mujoco>
    <option timestep="{DT}" gravity="0 -9.81 0" integrator="implicitfast"/>
  <default><geom contype="1" conaffinity="0" friction="1.0 0.02 0.001" density="1000"/></default>
  <worldbody>
    <geom name="floor" type="plane" pos="0 {floor_y:.4f} 0" quat="0.70710678 -0.70710678 0 0" size="20 20 0.1"
          contype="0" conaffinity="1"/>
    {body(0)}
  </worldbody>
</mujoco>"""


def wxyz(q: np.ndarray) -> np.ndarray:
    return np.concatenate([q[..., 3:], q[..., :3]], -1).astype(np.float64)


def nlerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    b = np.where((a * b).sum(-1, keepdims=True) < 0, -b, b)
    q = a * (1 - t) + b * t
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def sub_quat(qa: np.ndarray, qb: np.ndarray) -> np.ndarray:
    out = np.zeros(3)
    mujoco.mju_subQuat(out, qa, qb)
    return out


def run(clip: Path, personality: str | None, *, push_n=450.0, push_t=1.5, push_dur=0.2, assist_f=1500.0,
        assist_t=600.0, root_kp=20000.0, trace: list | None = None) -> dict:
    root, rot = M.load(clip)
    ref_pos = M.fk(root, rot)
    q_ref, F = wxyz(rot), root.shape[0]
    floor_y = float(np.percentile(ref_pos[:, [25, 29], 1].min(1), 5)) - 0.016
    model = mujoco.MjModel.from_xml_string(build_xml(floor_y))
    mujoco.mj_setTotalmass(model, 70.0)
    data = mujoco.MjData(model)
    bid = {j: model.body(M.NAMES[j]).id for j in SIM}
    qadr = {j: model.joint(f"j{j}").qposadr[0] for j in SIM[1:]}
    dadr = {j: model.joint(f"j{j}").dofadr[0] for j in SIM[1:]}

    data.qpos[:3], data.qpos[3:7] = root[0], q_ref[0, 0]
    for j in SIM[1:]:
        data.qpos[qadr[j]:qadr[j] + 4] = q_ref[0, j]
    data.qvel[:3] = (root[1] - root[0]) * M.FPS
    mujoco.mj_forward(model, data)

    p = PERSONALITIES.get(personality or "stoic")
    steps, per_frame = int((F - 1) / M.FPS / DT), []
    R = np.zeros(9)
    max_tau = 0.0
    t0 = time.perf_counter()
    for i in range(steps):
        t = i * DT
        f = min(t * M.FPS, F - 1.001)
        k, a = int(f), f - int(f)
        since = t - push_t
        stunned = personality is not None and since >= 0
        if stunned and p["stun"] is not None:  # ramp back to full over 0.5 s after the stun
            w = np.clip((since - p["stun"]) / 0.5, 0, 1)
        else:
            w = 0.0 if stunned else 1.0
        gain = p["gain"] + (1 - p["gain"]) * w if stunned else 1.0
        assist = p["assist"] + (1 - p["assist"]) * w if stunned else 1.0

        qt, qn = nlerp(q_ref[k], q_ref[k + 1], a), q_ref[k + 1]
        data.qfrc_applied[:] = 0
        for j in SIM[1:]:
            cur = data.qpos[qadr[j]:qadr[j] + 4]
            w_ref = sub_quat(qn[j], q_ref[k, j]) * M.FPS
            tau = gain * KP[j] * sub_quat(qt[j], cur) + gain * KP[j] / 10 * w_ref
            lim = KP[j] * 0.6
            tau = np.clip(tau, -lim, lim)
            max_tau = max(max_tau, float(np.abs(tau).max()))
            data.qfrc_applied[dadr[j]:dadr[j] + 3] = tau

        # Balance assist: capped PD wrench on the pelvis towards the reference root (the "hand of god").
        data.xfrc_applied[:] = 0
        p_ref = root[k] * (1 - a) + root[k + 1] * a
        v_ref = (root[k + 1] - root[k]) * M.FPS
        fo = root_kp * (p_ref - data.qpos[:3]) + root_kp / 10 * (v_ref - data.qvel[:3])
        mujoco.mju_quat2Mat(R, data.qpos[3:7])
        Rm = R.reshape(3, 3)
        to = Rm @ (root_kp * 0.15 * sub_quat(qt[0], data.qpos[3:7]) - root_kp * 0.015 * data.qvel[3:6])
        fn, tn = np.linalg.norm(fo), np.linalg.norm(to)
        data.xfrc_applied[bid[0], :3] = fo * min(1, assist * assist_f / (fn + 1e-9))
        data.xfrc_applied[bid[0], 3:] = to * min(1, assist * assist_t / (tn + 1e-9))
        if personality is not None and 0 <= since < push_dur:
            data.xfrc_applied[bid[3], :3] = [push_n, 0, 0]  # sideways shove on the chest

        mujoco.mj_step(model, data)
        if not np.isfinite(data.qpos).all():
            return {"personality": personality, "error": f"diverged at {t:.2f}s"}
        if (i + 1) % int(1 / M.FPS / DT + 0.5) == 0:
            kk = min(int(round((t + DT) * M.FPS)), F - 1)
            sim = np.array([data.xpos[bid[j]] for j in SIM])
            per_frame.append((t + DT, float(np.linalg.norm(sim - ref_pos[kk, SIM], axis=1).mean()),
                              float(data.qpos[1] - floor_y), float(np.linalg.norm(sim[0] - ref_pos[kk, 0]))))
            if trace is not None:
                trace.append((sim.copy(), ref_pos[kk, SIM].copy()))
    wall = time.perf_counter() - t0

    arr = np.array(per_frame)
    after = arr[arr[:, 0] >= push_t]
    out = {
        "personality": personality or "no push",
        "seconds": round(steps * DT, 2),
        "realtime_factor": round(steps * DT / wall, 1),
        "mean_joint_err_cm_before_push": round(float(arr[arr[:, 0] < push_t, 1].mean()) * 100, 1),
        "peak_root_dev_cm_after_push": round(float(after[:, 3].max()) * 100, 1),
        "final_joint_err_cm": round(float(arr[-10:, 1].mean()) * 100, 1),
        "min_hip_height_m": round(float(after[:, 2].min()), 2),
        "final_hip_height_m": round(float(arr[-1, 2]), 2),
        "max_joint_torque_nm": round(max_tau),
    }
    rec = after[(after[:, 0] > push_t + push_dur) & (after[:, 3] < 0.05)]
    out["recovered_within_5cm_after_s"] = round(float(rec[0, 0] - push_t), 2) if len(rec) else None
    return out


def strip(trace: list, path: Path, every: int = 9) -> None:
    """Front-view stick figures: reference in grey, simulated in colour."""
    from PIL import Image, ImageDraw
    frames = trace[::every][:14]
    W, H, s = 150, 300, 150
    im = Image.new("RGB", (W * len(frames), H), "white")
    d = ImageDraw.Draw(im)
    idx = {j: n for n, j in enumerate(SIM)}
    x0 = trace[0][1][0, 0]
    for n, (sim, ref) in enumerate(frames):
        for pts, col in ((ref, (190, 190, 190)), (sim, (200, 60, 40))):
            for j in SIM[1:]:
                a, b = pts[idx[M.PARENTS[j]]], pts[idx[j]]
                d.line([(n * W + W / 2 + (a[0] - x0) * s * .5, H - 20 - a[1] * s),
                        (n * W + W / 2 + (b[0] - x0) * s * .5, H - 20 - b[1] * s)], fill=col, width=3)
    im.save(path)


if __name__ == "__main__":
    clip = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    results = []
    for name in (None, "stoic", "stagger", "knockout"):
        tr: list = []
        results.append(run(clip, name, trace=tr))
        if out_dir and name:
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                strip(tr[40:], out_dir / f"ragdoll_{name}.png")
            except ImportError:
                pass
    results.append({**run(clip, None, assist_f=0.0, assist_t=0.0), "personality": "no push, NO balance assist"})
    print(json.dumps(results, indent=1))
