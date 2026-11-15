"""Motion quality metrics for Promptimate (pure numpy). The benchmark scoreboard in bench/ is built on this.

Input: root (F,3) and local rotations rot (F,30,4 xyzw) as produced by kimodo.cpp, or FK positions (F,30,3).
Kimodo space: Y-up, metres, right-handed, character starts facing +Z, 30 fps, floor at y = 0.

`compute(root, rot, boundaries=..., expect=..., segment_expect=...)` returns a flat dict of floats:
  physical quality   skate_*, penetration_*, float_*, airborne_*
  smoothness         jerk_*, max_joint_speed_ms, max_joint_acc_ms2, pop_frames
  seams              seam_* (only when segment boundaries are given)
  root behaviour     root_*, heading_*
  prompt adherence   exp_<check> (soft score 0..1 per check), expectation_score (mean), expectation_pass_rate
Lower is better for skate/penetration/float/jerk/pop/seam metrics; higher is better for expectation_*.
"""
from __future__ import annotations

import numpy as np

try:
    from . import motion  # type: ignore
except ImportError:  # imported as a top-level module with mcp_server/ on sys.path
    import motion  # type: ignore

FPS = motion.FPS
HIPS, HEAD, CHEST = 0, 6, 3
L_SHOULDER, R_SHOULDER = 11, 17          # LeftArm / RightArm = the actual shoulder (glenohumeral) joints
L_HAND, R_HAND = 13, 19
L_FOOT, L_TOE, R_FOOT, R_TOE = 24, 25, 28, 29
L_HIP, R_HIP = 22, 26
FOOT_JOINTS = [L_FOOT, L_TOE, R_FOOT, R_TOE]

# Rest heights above the floor of the contact joints (ankle ~5 cm, toe ~0 cm) and contact thresholds.
CONTACT_HEIGHT = {L_FOOT: 0.10, R_FOOT: 0.10, L_TOE: 0.05, R_TOE: 0.05}
CONTACT_MAX_SPEED = 1.0      # m/s (3D); HumanML3D-style: a contact joint must be both low and slow
SKATE_SPEED = 0.15           # m/s horizontal: a contact frame faster than this counts as skating
FLOAT_CLEARANCE = 0.08       # m: lowest foot point above this = no foot on the ground
FLOAT_MIN_RUN_S = 0.7        # no-contact runs longer than a jump flight are "floating"
STAND_HIPS = 0.95            # m: hips height of a standing SOMA character (rest pose 0.988)
POP_ACC = 120.0              # m/s^2 per-joint acceleration that counts as a pop/glitch frame
END_FRACTION = 0.2           # last 20 % of a clip/segment for "ends stationary"


def _r(x: float, nd: int = 4) -> float:
    return float(round(float(x), nd))


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous True runs as (start, end_exclusive)."""
    m = np.concatenate([[False], mask.astype(bool), [False]])
    d = np.diff(m.astype(np.int8))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def facing(pos: np.ndarray, smooth: int = 9) -> np.ndarray:
    """Horizontal facing unit vectors (F,3) from the hip line (left x up = forward)."""
    left = pos[:, L_HIP] - pos[:, R_HIP]
    left[:, 1] = 0
    fwd = np.cross(left, np.array([0.0, 1.0, 0.0]))
    if smooth > 1 and len(fwd) > smooth:
        k = np.ones(smooth) / smooth
        fwd = np.stack([np.convolve(np.pad(fwd[:, i], smooth // 2, mode="edge"), k, "valid") for i in range(3)], 1)
    return fwd / (np.linalg.norm(fwd, axis=1, keepdims=True) + 1e-9)


def yaw_deg(fwd: np.ndarray) -> np.ndarray:
    """Unwrapped yaw in degrees, 0 = +Z, positive = counter-clockwise seen from above (towards +X)."""
    return np.degrees(np.unwrap(np.arctan2(fwd[:, 0], fwd[:, 2])))


# ----------------------------------------------------------------------------------------------- physical


def foot_metrics(pos: np.ndarray) -> dict:
    vel = np.diff(pos[:, FOOT_JOINTS], axis=0) * FPS              # (F-1,4,3)
    h = 0.5 * (pos[1:, FOOT_JOINTS, 1] + pos[:-1, FOOT_JOINTS, 1])  # height at mid-frame
    speed3 = np.linalg.norm(vel, axis=2)
    hspeed = np.linalg.norm(vel[..., [0, 2]], axis=2)
    thr = np.array([CONTACT_HEIGHT[j] for j in FOOT_JOINTS])
    contact = (h < thr) & (speed3 < CONTACT_MAX_SPEED)
    out = {}
    if contact.any():
        hs = hspeed[contact]
        out["skate_speed_cms"] = _r(100 * hs.mean(), 2)
        out["skate_p95_cms"] = _r(100 * np.percentile(hs, 95), 2)
        out["skate_ratio"] = _r((hs > SKATE_SPEED).mean())
        # Distance slid while in contact, per second of clip (cm/s); comparable across clips of any length.
        out["skate_dist_cm_per_s"] = _r(100 * (hs / FPS).sum() / (len(pos) / FPS) / 2, 2)  # per foot pair
    else:
        out.update(skate_speed_cms=0.0, skate_p95_cms=0.0, skate_ratio=0.0, skate_dist_cm_per_s=0.0)
    out["contact_ratio"] = _r(contact.any(axis=1).mean())

    lowest = np.minimum(pos[:, [L_FOOT, R_FOOT], 1] - 0.05, pos[:, [L_TOE, R_TOE], 1]).min(axis=1)  # (F,)
    depth = np.clip(-lowest, 0, None)   # sole (ankle - 5 cm) or toe below the floor
    out["penetration_max_cm"] = _r(100 * depth.max(), 2)
    out["penetration_mean_cm"] = _r(100 * depth.mean(), 3)
    out["penetration_ratio"] = _r((depth > 0.01).mean())
    out["min_foot_height_cm"] = _r(100 * lowest.min(), 2)

    off = lowest > FLOAT_CLEARANCE
    runs = _runs(off)
    long_runs = [(a, b) for a, b in runs if (b - a) / FPS > FLOAT_MIN_RUN_S]
    out["airborne_frames"] = int(off.sum())
    out["airborne_max_run_s"] = _r(max([(b - a) for a, b in runs], default=0) / FPS, 3)
    out["float_ratio"] = _r(sum(b - a for a, b in long_runs) / len(pos))
    # Hovering: whole body shifted up (lowest foot point clearly above floor on average while "standing").
    out["mean_lowest_foot_cm"] = _r(100 * lowest.mean(), 2)
    return out


def smoothness_metrics(pos: np.ndarray) -> dict:
    out = {}
    if len(pos) < 5:
        return out
    v = np.diff(pos, axis=0) * FPS
    a = np.diff(v, axis=0) * FPS
    j = np.diff(a, axis=0) * FPS
    sp = np.linalg.norm(v, axis=2)
    am = np.linalg.norm(a, axis=2)
    jm = np.linalg.norm(j, axis=2)
    out["jerk_mean"] = _r(jm.mean(), 1)
    out["jerk_p95"] = _r(np.percentile(jm, 95), 1)
    out["jerk_max"] = _r(jm.max(), 1)
    out["max_joint_speed_ms"] = _r(sp.max(), 3)
    out["max_joint_acc_ms2"] = _r(am.max(), 1)
    out["pop_frames"] = int((am.max(axis=1) > POP_ACC).sum())
    # Frame-to-frame speed jump relative to the local motion level (catches single-frame pops on slow clips).
    dsp = np.abs(np.diff(sp, axis=0))
    out["max_speed_jump_ms"] = _r(dsp.max(), 3)
    return out


def seam_metrics(pos: np.ndarray, boundaries: list[int], window: int = 4) -> dict:
    """Jerk/velocity discontinuity around segment boundaries vs. the rest of the clip."""
    bs = [int(b) for b in boundaries if 3 < b < len(pos) - 3]
    if not bs or len(pos) < 12:
        return {}
    v = np.diff(pos, axis=0) * FPS
    a = np.diff(v, axis=0) * FPS
    j = np.diff(a, axis=0) * FPS
    jf = np.linalg.norm(j, axis=2).mean(axis=1)           # mean joint jerk per frame (len F-3); index i ~ frame i+1.5
    af = np.linalg.norm(a, axis=2).max(axis=1)            # worst joint acceleration per frame (len F-2)
    base_j = np.median(jf) + 1e-6
    base_a = np.median(af) + 1e-6
    ratios_j, ratios_a, vjumps = [], [], []
    near = np.zeros(len(jf), bool)
    for b in bs:
        lo, hi = max(0, b - window - 2), min(len(jf), b + window)
        near[lo:hi] = True
        ratios_j.append(jf[lo:hi].max() / base_j)
        ratios_a.append(af[max(0, b - window - 1):min(len(af), b + window)].max() / base_a)
        # velocity change across the seam: mean joint velocity just before vs just after
        pre = v[max(0, b - 3):b].mean(axis=0)
        post = v[b:min(len(v), b + 3)].mean(axis=0)
        vjumps.append(np.linalg.norm(post - pre, axis=1).max())
    away = jf[~near]
    return {
        "seam_jerk_ratio": _r(max(ratios_j), 3),           # peak jerk near seam / median jerk of clip
        "seam_acc_ratio": _r(max(ratios_a), 3),
        "seam_vel_jump_ms": _r(max(vjumps), 3),
        "seam_jerk_vs_p95": _r(max(jf[max(0, b - window - 2):b + window].max() for b in bs)
                               / (np.percentile(away, 95) + 1e-6) if len(away) else 0.0, 3),
    }


# ------------------------------------------------------------------------------------------------- root


def root_metrics(pos: np.ndarray, end_fraction: float = END_FRACTION) -> dict:
    xz = pos[:, HIPS, [0, 2]]
    F = len(pos)
    disp = xz[-1] - xz[0]
    step = np.linalg.norm(np.diff(xz, axis=0), axis=1)
    dur = max(F - 1, 1) / FPS
    fwd = facing(pos)
    f0 = fwd[: min(10, F)].mean(0)[[0, 2]]
    f0 /= np.linalg.norm(f0) + 1e-9
    side = np.array([f0[1], -f0[0]])     # right-hand side of initial facing in (x,z)
    yaw = yaw_deg(fwd)
    w = max(3, min(15, F // 6))
    n_end = max(3, int(round(F * end_fraction)))
    hips_y = pos[:, HIPS, 1]
    return {
        "root_travel_m": _r(np.linalg.norm(disp), 3),
        "root_path_m": _r(step.sum(), 3),
        "root_forward_m": _r(disp @ f0, 3),         # along initial facing (negative = backward)
        "root_lateral_m": _r(disp @ side, 3),
        "root_mean_speed_ms": _r(step.sum() / dur, 3),
        "root_end_speed_ms": _r(step[-(n_end - 1):].mean() * FPS if F > 3 else 0.0, 3),
        "root_start_speed_ms": _r(step[: n_end - 1].mean() * FPS if F > 3 else 0.0, 3),
        "heading_change_deg": _r(yaw[-w:].mean() - yaw[:w].mean(), 1),
        "heading_change_abs_deg": _r(abs(yaw[-w:].mean() - yaw[:w].mean()), 1),
        "heading_abs_total_deg": _r(np.abs(np.diff(yaw)).sum(), 1),
        "initial_facing_deg": _r(abs(np.degrees(np.arctan2(f0[0], f0[1]))), 1),
        "hips_min_m": _r(hips_y.min(), 3),
        "hips_max_m": _r(hips_y.max(), 3),
        "hips_end_m": _r(hips_y[-n_end:].mean(), 3),
    }


# ------------------------------------------------------------------------------------------ expectations

def _ge(actual: float, target: float, scale: float | None = None) -> float:
    """Soft score for actual >= target: 1 when met, linear down to 0 at target - scale."""
    scale = scale if scale else max(abs(target), 1e-6)
    return float(np.clip(1 - (target - actual) / scale, 0, 1))


def _le(actual: float, target: float, scale: float | None = None) -> float:
    scale = scale if scale else max(abs(target), 1e-6)
    return float(np.clip(1 - (actual - target) / scale, 0, 1))


def _count_events(mask: np.ndarray, min_gap: int = 4) -> int:
    runs = _runs(mask)
    n, last = 0, -10 ** 9
    for a, b in runs:
        if a - last >= min_gap:
            n += 1
        last = b
    return n


def expectation_checks(pos: np.ndarray, expect: dict, prefix: str = "") -> dict[str, float]:
    """Soft 0..1 scores for machine-checkable prompt expectations. Unknown keys raise (typos in prompts.json)."""
    out: dict[str, float] = {}
    if not expect:
        return out
    rm = root_metrics(pos)
    fwd = facing(pos)
    F = len(pos)
    hips_y = pos[:, HIPS, 1]
    lowest = np.minimum(pos[:, [L_FOOT, R_FOOT], 1] - 0.05, pos[:, [L_TOE, R_TOE], 1]).min(axis=1)
    sh_y = {"right": pos[:, R_SHOULDER, 1], "left": pos[:, L_SHOULDER, 1]}
    hand = {"right": pos[:, R_HAND], "left": pos[:, L_HAND]}
    shoulder = {"right": pos[:, R_SHOULDER], "left": pos[:, L_SHOULDER]}

    def frac_hand_up(side: str) -> float:
        if side == "any":
            return float(((hand["right"][:, 1] > sh_y["right"]) | (hand["left"][:, 1] > sh_y["left"])).mean())
        if side == "both":
            return float(((hand["right"][:, 1] > sh_y["right"]) & (hand["left"][:, 1] > sh_y["left"])).mean())
        return float((hand[side][:, 1] > sh_y[side]).mean())

    def arm_extended(side: str) -> np.ndarray:
        """Pointing / reaching: hand >= 0.30 m in front of its shoulder (along facing), not hanging down."""
        rel = hand[side] - shoulder[side]
        return (np.einsum("fi,fi->f", rel, fwd) > 0.30) & (rel[:, 1] > -0.30)

    def hand_forward(side: str) -> np.ndarray:
        rel = hand[side] - pos[:, CHEST]
        return np.einsum("fi,fi->f", rel, fwd)          # metres in front of the chest

    for key, val in expect.items():
        k = prefix + key
        if key == "travel_min":
            out[k] = _ge(rm["root_travel_m"], val)
        elif key == "travel_max":
            out[k] = _le(rm["root_travel_m"], val, max(val, 0.5))
        elif key == "forward_min":
            out[k] = _ge(rm["root_forward_m"], val)
        elif key == "backward_min":
            out[k] = _ge(-rm["root_forward_m"], val)
        elif key == "mean_speed_min":
            out[k] = _ge(rm["root_mean_speed_ms"], val)
        elif key == "mean_speed_max":
            out[k] = _le(rm["root_mean_speed_ms"], val, max(val, 0.3))
        elif key == "ends_stationary":   # val = max mean root speed (m/s) over the last 20 %
            out[k] = _le(rm["root_end_speed_ms"], val, max(val, 0.3))
        elif key == "turn_min_deg":
            out[k] = _ge(abs(rm["heading_change_deg"]), val)
        elif key == "turn_max_deg":
            out[k] = _le(abs(rm["heading_change_deg"]), val, max(val, 30))
        elif key in ("right_hand_up_frac", "left_hand_up_frac", "any_hand_up_frac", "both_hands_up_frac"):
            out[k] = _ge(frac_hand_up(key.split("_")[0]), val)
        elif key in ("right_arm_extended_frac", "left_arm_extended_frac", "any_arm_extended_frac"):
            side = key.split("_")[0]
            m = (arm_extended("right") | arm_extended("left")) if side == "any" else arm_extended(side)
            out[k] = _ge(float(m.mean()), val)
        elif key == "arms_forward_frac":   # both hands >= 0.3 m in front of the chest (zombie, reaching)
            m = (hand_forward("right") > 0.3) & (hand_forward("left") > 0.3)
            out[k] = _ge(float(m.mean()), val)
        elif key == "hands_up_max_frac":   # hands should mostly stay down (e.g. plain walking)
            out[k] = _le(frac_hand_up("any"), val, 0.3)
        elif key == "clap_count_min":       # hands come together (< 12 cm) at least N separate times
            d = np.linalg.norm(hand["right"] - hand["left"], axis=1)
            out[k] = _ge(_count_events(d < 0.12), val)
        elif key == "hips_drop_min":        # hips go at least X m below standing height at some point
            out[k] = _ge(STAND_HIPS - hips_y.min(), val)
        elif key == "hips_end_max":         # hips height over the last 20 % (sit/crouch and stay)
            out[k] = _le(rm["hips_end_m"], val, 0.3)
        elif key == "hips_end_min":         # hips back up at the end (stands up again)
            out[k] = _ge(rm["hips_end_m"], val, 0.4)
        elif key == "hips_low_frac":        # val = [height, frac]
            h, fr = val
            out[k] = _ge(float((hips_y < h).mean()), fr)
        elif key == "hips_rise_min":        # hips rise X m above their median height (jump)
            out[k] = _ge(hips_y.max() - np.median(hips_y), val)
        elif key == "airborne_frames_min":
            out[k] = _ge(float((lowest > FLOAT_CLEARANCE).sum()), val)
        elif key == "foot_raise_min":       # a foot (ankle) goes at least X m above the floor (kick)
            out[k] = _ge(float(pos[:, [L_FOOT, R_FOOT], 1].max()), val)
        elif key == "head_low_max":         # mean head height at most X (slumped / sad posture)
            out[k] = _le(float(pos[:, HEAD, 1].mean()), val, 0.15)
        elif key == "stays_upright":        # head stays above X m the whole time (no accidental fall)
            out[k] = _ge(float(pos[:, HEAD, 1].min()), val, 0.4)
        else:
            raise KeyError(f"unknown expectation '{key}'")
    return out


# ---------------------------------------------------------------------------------------------- top level


def compute(root: np.ndarray | None = None, rot: np.ndarray | None = None, *, pos: np.ndarray | None = None,
            boundaries: list[int] | None = None, expect: dict | None = None,
            segment_expect: list[dict | None] | None = None, segment_frames: list[int] | None = None) -> dict:
    """All metrics as a flat dict. Give root+rot (preferred) or FK positions `pos`.

    boundaries: frame indices where segments meet (multi-segment clips); derived from segment_frames if omitted.
    expect: whole-clip expectations; segment_expect[i]: expectations evaluated on segment i only
    (needs segment_frames).
    """
    if pos is None:
        pos = motion.fk(root, rot)
    pos = pos.astype(np.float64)
    out: dict = {"frames": int(len(pos)), "duration_s": _r(len(pos) / FPS, 2)}
    out.update(foot_metrics(pos))
    out.update(smoothness_metrics(pos))
    out.update(root_metrics(pos))
    if boundaries is None and segment_frames and len(segment_frames) > 1:
        boundaries = list(np.cumsum(segment_frames)[:-1])
    if boundaries:
        out.update(seam_metrics(pos, boundaries))
    scores: dict[str, float] = {}
    scores.update(expectation_checks(pos, expect or {}))
    if segment_expect and segment_frames:
        starts = np.concatenate([[0], np.cumsum(segment_frames)]).astype(int)
        for i, e in enumerate(segment_expect):
            if e:
                seg = pos[starts[i]:starts[i + 1]]
                scores.update(expectation_checks(seg, e, prefix=f"seg{i}_"))
    for k, v in scores.items():
        out["exp_" + k] = _r(v, 3)
    if scores:
        vals = np.array(list(scores.values()))
        out["expectation_score"] = _r(vals.mean(), 4)
        out["expectation_pass_rate"] = _r((vals >= 0.999).mean(), 4)
    return out


# Direction of "better" for summaries / compare (+1 higher is better, -1 lower is better, 0 informational).
DIRECTION = {
    "skate_speed_cms": -1, "skate_p95_cms": -1, "skate_ratio": -1, "skate_dist_cm_per_s": -1,
    "penetration_max_cm": -1, "penetration_mean_cm": -1, "penetration_ratio": -1, "float_ratio": -1,
    "jerk_mean": -1, "jerk_p95": -1, "jerk_max": -1, "max_joint_acc_ms2": -1, "pop_frames": -1,
    "max_speed_jump_ms": -1, "seam_jerk_ratio": -1, "seam_acc_ratio": -1, "seam_vel_jump_ms": -1,
    "seam_jerk_vs_p95": -1, "expectation_score": 1, "expectation_pass_rate": 1,
    "gen_seconds": -1, "wall_seconds": -1, "gen_seconds_per_clip_second": -1,
}
