"""Physical clean-up of generated Kimodo SOMA motion: foot contacts, foot locking (two-bone IK),
grounding, optional rotation-safe smoothing, in-place and seamless-loop conversion.

Everything works on the raw representation that every exporter consumes:
    root (F,3)    hips world position, Y-up, metres
    rot  (F,30,4) LOCAL joint rotations, xyzw (joint 0 = Hips global rotation)
Bone lengths are fixed by motion.OFFSETS, so only rotations (and, where intended, the root) change.

Ground convention: Kimodo's training data stands with the ankle joint at ~6.8 cm and the toe-base joint at
~1.8 cm (median over the idle clips). The rest pose in OFFSETS puts the toe 5.06 cm below the ankle, the same
flat-foot drop seen in the data, so the floor sits 1.8 cm below the toe joint (the sole of the SOMA mesh).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

import motion

FPS = motion.FPS
PARENTS = motion.PARENTS
OFF = motion.OFFSETS.astype(np.float64)
J = motion.J

LEGS = {"left": (22, 23, 24, 25), "right": (26, 27, 28, 29)}  # thigh(hip), shin(knee), foot(ankle), toe
TOE_FLOOR = 0.018                                      # toe-base joint height when the foot is flat on the floor
ANKLE_FLOOR = TOE_FLOOR - float(OFF[25, 1])            # = 0.0686: rest-pose ankle->toe drop added on top
FLOOR = {"heel": ANKLE_FLOOR, "toe": TOE_FLOOR}

# contact detection (height above that joint's floor height, 3D speed) with hysteresis
ENTER_H, EXIT_H = 0.015, 0.030       # m
ENTER_V, EXIT_V = 0.30, 0.60         # m/s
MIN_CONTACT = 3                      # frames
BLEND = 5                            # frames of ease-in/out around each locked span


# ----------------------------------------------------------------------------------------------- quaternions
def qnorm(q):
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def qmul(a, b):
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz], axis=-1)


def qinv(q):
    return q * np.array([-1.0, -1.0, -1.0, 1.0])


def qrot(q, v):
    u = q[..., :3]
    w = q[..., 3:4]
    t = 2.0 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def qaxis_angle(axis, angle):
    axis = axis / (np.linalg.norm(axis, axis=-1, keepdims=True) + 1e-12)
    h = 0.5 * np.asarray(angle)[..., None]
    return np.concatenate([axis * np.sin(h), np.cos(h)], axis=-1)


def qlog(q):
    """Rotation vector (axis * angle) of unit quaternions."""
    q = np.where(q[..., 3:4] < 0, -q, q)
    s = np.linalg.norm(q[..., :3], axis=-1, keepdims=True)
    ang = 2.0 * np.arctan2(s, q[..., 3:4])
    return q[..., :3] * np.where(s > 1e-9, ang / np.maximum(s, 1e-12), 2.0)


def qexp(v):
    ang = np.linalg.norm(v, axis=-1, keepdims=True)
    axis = v / np.maximum(ang, 1e-12)
    return np.concatenate([axis * np.sin(ang / 2), np.cos(ang / 2)], axis=-1)


def qpow(q, t):
    """Scale a rotation by factor t (slerp from identity)."""
    return qexp(qlog(q) * np.asarray(t)[..., None])


def qangle(a, b):
    d = np.abs(np.sum(a * b, axis=-1))
    return 2.0 * np.arccos(np.clip(d, 0.0, 1.0))


def hemisphere(q):
    """Make a quaternion track continuous over time (axis 0) so filtering/averaging is valid."""
    q = q.copy()
    for f in range(1, q.shape[0]):
        flip = np.sum(q[f] * q[f - 1], axis=-1) < 0
        q[f][flip] *= -1
    return q


def yaw_quat(psi):
    return qaxis_angle(np.broadcast_to([0.0, 1.0, 0.0], np.shape(psi) + (3,)), psi)


def heading(q_hips):
    """Yaw (radians, about +Y, 0 = facing +Z) of the hips' forward (+Z) axis."""
    f = qrot(q_hips, np.array([0.0, 0.0, 1.0]))
    return np.arctan2(f[..., 0], f[..., 2])


# ----------------------------------------------------------------------------------------------- kinematics
def fk_full(root, rot):
    """Float64 FK: global rotations (F,J,4) and positions (F,J,3)."""
    rot = np.asarray(rot, np.float64)
    F = rot.shape[0]
    G = np.empty((F, J, 4))
    P = np.empty((F, J, 3))
    for j, p in enumerate(PARENTS):
        if p < 0:
            G[:, j] = rot[:, j]
            P[:, j] = root
        else:
            G[:, j] = qmul(G[:, p], rot[:, j])
            P[:, j] = P[:, p] + qrot(G[:, p], OFF[j])
    return G, P


def fk(root, rot):
    return fk_full(root, rot)[1]


def soft_reach(a, c, t, lmax, margin=0.004):
    """Soft IK: extending the leg beyond its original length approaches (lmax - margin) asymptotically instead of
    snapping straight, which avoids knee pops at the straight-leg singularity. Shortening is untouched."""
    v = t - a
    d = np.linalg.norm(v, axis=-1)
    d0 = np.linalg.norm(c - a, axis=-1)
    cap = lmax - margin
    room = np.maximum(cap - d0, 1e-6)
    ext = np.maximum(d - d0, 0.0)
    soft = np.where(d0 >= cap, np.minimum(d, d0), d0 + room * (1.0 - np.exp(-ext / room)))
    nd = np.where(d > d0, soft, d)
    return a + v * (nd / np.maximum(d, 1e-9))[..., None]


def two_bone_ik(a, b, c, t, Ga, Gb, hinge_fallback):
    """Daniel Holden's analytic two-bone IK. a,b,c = hip, knee, ankle positions; t = ankle target;
    Ga, Gb = global rotations of the thigh and shin joints. Returns new (Ga, Gb). The knee stays in its current
    bend plane (pole = current knee), with a hinge-axis fallback so near-straight legs stay stable."""
    lab = np.linalg.norm(b - a, axis=-1)
    lcb = np.linalg.norm(b - c, axis=-1)
    lat = np.clip(np.linalg.norm(t - a, axis=-1), np.abs(lab - lcb) + 1e-4, lab + lcb - 1e-4)

    def nz(v):
        return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-12)

    def ang(u, v):
        return np.arccos(np.clip(np.sum(nz(u) * nz(v), axis=-1), -1.0, 1.0))

    ac_ab_0 = ang(c - a, b - a)
    ba_bc_0 = ang(a - b, c - b)
    ac_at_0 = ang(c - a, t - a)
    ac_ab_1 = np.arccos(np.clip((lcb ** 2 - lab ** 2 - lat ** 2) / (-2 * lab * lat), -1, 1))
    ba_bc_1 = np.arccos(np.clip((lat ** 2 - lab ** 2 - lcb ** 2) / (-2 * lab * lcb), -1, 1))
    cr = np.cross(c - a, b - a)
    axis0 = nz(cr + hinge_fallback * 0.02)
    axis1 = np.cross(c - a, t - a)
    small = np.linalg.norm(axis1, axis=-1, keepdims=True) < 1e-9
    axis1 = np.where(small, axis0, axis1)
    r0 = qaxis_angle(axis0, ac_ab_1 - ac_ab_0)
    r1 = qaxis_angle(axis0, ba_bc_1 - ba_bc_0)
    r2 = qaxis_angle(axis1, np.where(small[..., 0], 0.0, ac_at_0))
    Ga2 = qmul(r2, qmul(r0, Ga))
    Gb2 = qmul(r2, qmul(r0, qmul(r1, Gb)))
    return qnorm(Ga2), qnorm(Gb2)


# ----------------------------------------------------------------------------------------------- contacts
def _speed(p, fps):
    v = np.gradient(p, axis=0) * fps
    s = np.linalg.norm(v, axis=-1)
    if len(s) >= 3:  # 3-tap average against single-frame noise
        s = np.convolve(np.pad(s, 1, mode="edge"), np.ones(3) / 3, mode="valid")
    return s


def _hysteresis(h, s):
    out = np.zeros(len(h), bool)
    on = False
    for f in range(len(h)):
        if on:
            on = not (h[f] > EXIT_H or s[f] > EXIT_V)
        else:
            on = h[f] < ENTER_H and s[f] < ENTER_V
        out[f] = on
    return out


def spans(mask):
    """[(start, end_exclusive), ...] of True runs."""
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def _clean_mask(m, min_len=MIN_CONTACT, gap=2):
    m = m.copy()
    for s, e in spans(~m):  # fill tiny gaps inside a contact
        if s > 0 and e < len(m) and e - s <= gap:
            m[s:e] = True
    for s, e in spans(m):
        if e - s < min_len:
            m[s:e] = False
    return m


def detect_contacts(pos, fps=FPS):
    """Per foot and joint ('left_heel', 'left_toe', ...) boolean contact masks (F,)."""
    out = {}
    for side, (_, _, ank, toe) in LEGS.items():
        for part, j in (("heel", ank), ("toe", toe)):
            h = pos[:, j, 1] - FLOOR[part]
            out[f"{side}_{part}"] = _clean_mask(_hysteresis(h, _speed(pos[:, j], fps)))
    return out


CONTACT_KEYS = ("left_heel", "left_toe", "right_heel", "right_toe")  # = column order of foot_contacts.f32
MODEL_MAX_H = 0.05   # m above the joint's floor height: model contacts higher than this are vetoed in "fuse"
SEATED_HIPS_M = 0.6  # hips below this = seated or kneeling (model contacts unreliable there)
MODEL_MAX_V = 1.0    # m/s: model contacts on a fast-moving joint are vetoed in "fuse"


def load_contacts(motion_dir):
    """The engine's predicted foot contacts (F,4) float32 from foot_contacts.f32, or None for older clips.
    Columns (verified against foot heights/velocities and heel-before-toe lift-off timing): left heel (LeftFoot),
    left toe (LeftToeBase), right heel, right toe. Values are ~binary probabilities."""
    f = Path(motion_dir) / "foot_contacts.f32"
    if not f.exists():
        return None
    c = np.fromfile(f, dtype="<f4")
    root_n = (Path(motion_dir) / "root_positions.f32").stat().st_size // 12
    return c.reshape(root_n, -1) if root_n and c.size == root_n * 4 else None


def contacts_from_model(model, pos=None, fps=FPS, mode="fuse", threshold=0.5):
    """Boolean contact masks from the model's predicted contacts.
    mode="model": threshold only (+ min length / gap fill).
    mode="fuse":  model timing, vetoed where the joint is clearly airborne or moving fast (needs pos).
    mode="union": heuristic contacts OR the "fuse" contacts (needs pos); the recommended default."""
    model = np.asarray(model, np.float64)
    out = {}
    for k, key in enumerate(CONTACT_KEYS):
        m = model[:, k] > threshold
        if mode == "fuse" and pos is not None:
            side, part = key.split("_")
            j = LEGS[side][2] if part == "heel" else LEGS[side][3]
            h = pos[:, j, 1] - FLOOR[part]
            m &= (h < MODEL_MAX_H) & (_speed(pos[:, j], fps) < MODEL_MAX_V)
            # Seated / kneeling (hips low): the model marks feet planted while the body shifts on the seat, and
            # pinning them makes skating worse; leave those frames to the heuristic.
            m &= pos[:, 0, 1] > SEATED_HIPS_M
        out[key] = _clean_mask(m)
    if mode == "union" and pos is not None:  # heuristic OR physically-plausible model contacts
        heur = detect_contacts(pos, fps)
        fused = contacts_from_model(model, pos, fps, mode="fuse", threshold=threshold)
        out = {k: _clean_mask(heur[k] | fused[k]) for k in CONTACT_KEYS}
    return out


def _ramp(mask, blend=BLEND):
    """Lock weight: 1 inside contact spans, smoothstep ease over `blend` frames on each side."""
    F = len(mask)
    w = mask.astype(np.float64)
    if blend <= 0:
        return w
    for s, e in spans(mask):
        for k in range(1, blend + 1):
            x = 1.0 - k / (blend + 1)
            x = x * x * (3 - 2 * x)
            if s - k >= 0:
                w[s - k] = max(w[s - k], x)
            if e - 1 + k < F:
                w[e - 1 + k] = max(w[e - 1 + k], x)
    return w


def _ground_offset(pos, contacts):
    vals = []
    for side, (_, _, ank, toe) in LEGS.items():
        for part, j in (("heel", ank), ("toe", toe)):
            m = contacts[f"{side}_{part}"]
            vals.append(pos[m, j, 1] - FLOOR[part])
    v = np.concatenate(vals) if vals else np.zeros(0)
    return float(np.median(v)) if len(v) >= 5 else 0.0


# ----------------------------------------------------------------------------------------------- metrics
def metrics(root, rot, fps=FPS, contacts=None):
    """skate_cms: mean horizontal speed of heel/toe joints during their contact frames (cm/s); pivot_skate_cms:
    per planted foot the slower of its planted points (a foot pivoting on its toe is not skating); penetration: mean / max depth
    of heel/toe joints below their floor height (cm); jerk: mean |d3 pos/dt3| over all joints (m/s^3)."""
    pos = fk(root, rot)
    if contacts is None:
        contacts = detect_contacts(pos, fps)
    # slide per frame pair, counted only when the joint is in contact on both frames
    def slide(j):
        return np.linalg.norm(np.diff(pos[:, j, [0, 2]], axis=0), axis=-1) * fps
    sk, n, piv, npiv = 0.0, 0, 0.0, 0
    for side, (_, _, ank, toe) in LEGS.items():
        hm, tm = contacts[f"{side}_heel"], contacts[f"{side}_toe"]
        h2, t2 = hm[1:] & hm[:-1], tm[1:] & tm[:-1]
        vh, vt = slide(ank), slide(toe)
        sk += vh[h2].sum() + vt[t2].sum()
        n += int(h2.sum() + t2.sum())
        v = np.where(h2 & t2, np.minimum(vh, vt), np.where(t2, vt, vh))
        m = h2 | t2
        piv += v[m].sum()
        npiv += int(m.sum())
    depth = np.concatenate([np.maximum(0, FLOOR["heel"] - pos[:, [24, 28], 1]).ravel(),
                            np.maximum(0, FLOOR["toe"] - pos[:, [25, 29], 1]).ravel()])
    jerk = np.linalg.norm(np.diff(pos, n=3, axis=0), axis=-1) * fps ** 3 if len(pos) > 3 else np.zeros(1)
    return {"skate_cms": round(100 * sk / max(n, 1), 2), "contact_frames": n,
            "pivot_skate_cms": round(100 * piv / max(npiv, 1), 2),
            "penetration_mean_cm": round(100 * float(depth.mean()), 3),
            "penetration_max_cm": round(100 * float(depth.max()), 2),
            "jerk": round(float(jerk.mean()), 2)}


# ----------------------------------------------------------------------------------------------- smoothing
def _gauss(sigma):
    r = max(1, int(round(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    return k / k.sum(), r


def _filter(x, sigma, odd=False):
    """Gaussian filter along axis 0; x (F,...). Edge padding by repetition, or by point reflection (odd=True),
    which keeps linear trends unbiased at the clip ends."""
    k, r = _gauss(sigma)
    r = min(r, len(x) - 1)
    k = k[len(k) // 2 - r: len(k) // 2 + r + 1]
    k = k / k.sum()
    if odd and r > 0:
        xp = np.concatenate([2 * x[:1] - x[r:0:-1], x, 2 * x[-1:] - x[-2:-r - 2:-1]], 0)
    else:
        xp = np.concatenate([np.repeat(x[:1], r, 0), x, np.repeat(x[-1:], r, 0)], 0)
    out = np.zeros_like(x)
    for i, kv in enumerate(k):
        out += kv * xp[i:i + len(x)]
    return out


def smooth_motion(root, rot, sigma=1.2, max_corr_deg=3.0, max_corr_m=0.01, segment_boundaries=None, seam_sigma=2.5,
           seam_radius=6):
    """Jitter filter. Rotations are filtered as continuous-hemisphere quaternions then renormalised, and every
    per-frame correction is clamped (max_corr_deg / max_corr_m) so large, sharp intended motions survive while
    small high-frequency noise is removed. Around segment boundaries a wider window softens the seam."""
    F = rot.shape[0]
    q = hemisphere(np.asarray(rot, np.float64))
    sig = np.full(F, float(sigma))
    if segment_boundaries:
        for b in segment_boundaries:
            lo, hi = max(0, b - seam_radius), min(F, b + seam_radius + 1)
            sig[lo:hi] = np.maximum(sig[lo:hi], seam_sigma)
    out_q, out_r = q.copy(), np.asarray(root, np.float64).copy()
    base = sigma if sigma > 0 else 1.2
    for s in sorted(set(np.round(sig, 3))):
        if s <= 0:
            continue
        sel = np.isclose(sig, s)
        fq = qnorm(_filter(q, s))
        fr = _filter(np.asarray(root, np.float64), s)
        lim = max_corr_deg * max(1.0, s / base)
        d = qmul(fq, qinv(q))                      # correction, clamped in angle
        ang = qangle(fq, q)
        scale = np.minimum(1.0, np.radians(lim) / np.maximum(ang, 1e-9))
        out_q[sel] = qmul(qpow(d, scale), q)[sel]
        dr = fr - root
        limr = max_corr_m * max(1.0, s / base)
        n = np.linalg.norm(dr, axis=-1, keepdims=True)
        out_r[sel] = (root + dr * np.minimum(1.0, limr / np.maximum(n, 1e-9)))[sel]
    return out_r, qnorm(out_q)


# ----------------------------------------------------------------------------------------------- clean
def clean(root, rot, fps=FPS, *, foot_lock=True, ground=True, smooth=False, segment_boundaries=None,
          contacts=None, contact_mode="union"):
    """Make generated motion physically clean. Returns (root, rot, info).

    ground:    shift the root vertically so contact feet stand on the floor (one global offset), and lift any
               heel/toe that still dips below the floor with leg IK (never by raising the root -> no floating).
    foot_lock: pin each heel/toe contact span to a fixed world point, solved with two-bone leg IK on the thigh and
               shin local rotations and a foot-joint correction so the toe stays planted; eased in/out.
    smooth:    light rotation-safe jitter filter (off by default); segment_boundaries soften multi-prompt seams.
    contacts:  optional (F,4) model-predicted foot contacts (foot_contacts.f32, see load_contacts). Used according
               to contact_mode: "union" (default: heuristic OR model, model vetoed where the joint is airborne or
               fast), "fuse" (model timing with that veto), "model" (threshold only) or "heuristic" (ignore them).
               Measured on the engine A/B clips, "union" gives the lowest residual skate: the model ends contacts
               2-3 frames before heel-lift/toe-off while the foot is still planted, but occasionally catches a
               short contact the heuristic misses. Without them the height+velocity heuristic is used.
    """
    root0 = np.asarray(root, np.float64)
    rot0 = qnorm(np.asarray(rot, np.float64))
    root1 = root0.copy()
    rot1 = rot0.copy()
    info: dict = {"fps": fps, "frames": int(root0.shape[0])}

    if smooth or segment_boundaries:
        root1, rot1 = smooth_motion(root1, rot1, sigma=1.2 if smooth else 0.0, segment_boundaries=segment_boundaries)
        info["smoothed"] = bool(smooth)
        info["segment_boundaries"] = list(segment_boundaries or [])

    # untouched joints/frames are returned bit-exact (input float32), only solved ones are rewritten
    out_rot = rot1.astype(np.float32) if (smooth or segment_boundaries) else np.array(rot, np.float32, copy=True)
    G, P = fk_full(root1, rot1)
    # pass 1: rough offset from the clip itself (lowest slow frames), then detect contacts relative to the floor
    shift = 0.0
    if ground:
        rough = _rough_floor(P, fps)
        Pr = P - np.array([0, rough, 0])
        shift = rough + _ground_offset(Pr, detect_contacts(Pr, fps))
        if abs(shift) < 0.002:
            shift = 0.0
        root1[:, 1] -= shift
        P[..., 1] -= shift
    info["ground_offset_m"] = round(-shift, 4)
    heur = detect_contacts(P, fps)
    if contacts is not None and contact_mode != "heuristic":
        model = np.asarray(contacts)
        if model.shape != (P.shape[0], 4):
            raise ValueError(f"contacts must be (frames, 4), got {model.shape}")
        contacts = contacts_from_model(model, P, fps, mode=contact_mode)
        info["contact_source"] = f"model:{contact_mode}"
        info["contact_agreement_vs_heuristic"] = round(float(np.mean([(contacts[k] == heur[k]).mean()
                                                                      for k in CONTACT_KEYS])), 3)
    else:
        contacts = heur
        info["contact_source"] = "heuristic"
    info["contacts"] = {k: [[int(s), int(e)] for s, e in spans(m)] for k, m in contacts.items()}
    info["contact_frames"] = {k: int(m.sum()) for k, m in contacts.items()}
    info["before"] = metrics(root0 - np.array([0, shift, 0]), rot0, fps, contacts)

    ik_frames = {}
    max_err = 0.0
    for side, (hip, knee, ank, toe) in LEGS.items():
        orig_ank = P[:, ank].copy()
        orig_toe = P[:, toe].copy()
        Gf = G[:, ank].copy()
        toe_off_w = qrot(Gf, OFF[toe])                     # ankle -> toe in world, original foot orientation
        target = orig_ank.copy()
        Gf_des = Gf.copy()
        if foot_lock:
            heel_m, toe_m = contacts[f"{side}_heel"], contacts[f"{side}_toe"]
            wh, wt = _ramp(heel_m), _ramp(toe_m)
            heel_lock = _locks(orig_ank, heel_m, wh, fps, FLOOR["heel"])
            toe_lock = _locks(orig_toe, toe_m, wt, fps, FLOOR["toe"])
            # while the toe is planted the foot pivots about it: hold the foot's yaw at the span's value (kills
            # rotational skating) and derive the ankle from the toe lock, so heel-lift rotates about the ball
            psi_f = np.unwrap(np.arctan2(toe_off_w[:, 0], toe_off_w[:, 2]))
            Gf_des = qmul(yaw_quat(wt * _yaw_locks(psi_f, toe_m, fps, _speed(orig_toe, fps))), Gf)
            A_t = toe_lock - qrot(Gf_des, OFF[toe])
            # heel-strike (heel down, toe not yet): heel lock has priority; once the toe is down it takes over,
            # with a short smooth hand-over instead of a jump between the two anchors
            sel = toe_m.astype(np.float64)
            sel = np.convolve(np.pad(sel, 2, mode="edge"), [0.1, 0.2, 0.4, 0.2, 0.1], mode="valid")
            wt_eff = np.where(heel_m | toe_m, np.minimum(sel, wt), wt)
            target = (orig_ank + wt_eff[:, None] * (A_t - orig_ank)
                      + ((1 - wt_eff) * wh)[:, None] * (heel_lock - orig_ank))
        if ground:  # penetration: lift ankle so heel and toe are on/above the floor
            toe_now = target + qrot(Gf_des, OFF[toe])
            lift = np.maximum(0.0, FLOOR["toe"] - toe_now[:, 1])
            target[:, 1] += lift
            target[:, 1] = np.maximum(target[:, 1], FLOOR["heel"])
        moved = (np.linalg.norm(target - orig_ank, axis=-1) > 1e-5) | (qangle(Gf_des, Gf) > 1e-5)
        idx = np.where(moved)[0]
        ik_frames[side] = int(len(idx))
        if len(idx) == 0:
            continue
        a, b, c = P[idx, hip], P[idx, knee], P[idx, ank]
        hinge = qrot(G[idx, hip], np.array([-1.0, 0.0, 0.0]))
        tgt = soft_reach(a, c, target[idx], float(np.linalg.norm(OFF[knee]) + np.linalg.norm(OFF[ank])))
        Ga, Gb = two_bone_ik(a, b, c, tgt, G[idx, hip], G[idx, knee], hinge)
        Gpar = G[idx, PARENTS[hip]]
        rot1[idx, hip] = qmul(qinv(Gpar), Ga)
        rot1[idx, knee] = qmul(qinv(Ga), Gb)
        rot1[idx, ank] = qmul(qinv(Gb), Gf_des[idx])
        new = qnorm(rot1[idx, hip:toe + 1])
        # keep each quaternion in the same hemisphere as the input so keyframe interpolation stays short-path
        new = np.where(np.sum(new * rot0[idx, hip:toe + 1], axis=-1, keepdims=True) < 0, -new, new)
        rot1[idx, hip:toe + 1] = new
        out_rot[idx, hip:toe + 1] = new
        # reachability check
        new_ank = a + qrot(Ga, OFF[knee]) + qrot(Gb, OFF[ank])
        max_err = max(max_err, float(np.linalg.norm(new_ank - target[idx], axis=-1).max()))
    info["ik_frames"] = ik_frames
    info["ik_unreached_max_cm"] = round(100 * max_err, 2)
    info["after"] = metrics(root1, rot1, fps, contacts)
    info["skate_cms"] = [info["before"]["skate_cms"], info["after"]["skate_cms"]]
    return root1.astype(np.float32), out_rot, info


def _rough_floor(P, fps):
    """Clip-relative floor estimate before contacts are known: 10th percentile of slow-frame sole heights."""
    sole = np.minimum(P[:, [25, 29], 1] - FLOOR["toe"], P[:, [24, 28], 1] - FLOOR["heel"])
    sp = np.stack([_speed(P[:, j], fps) for j in (25, 29)], 1)
    vals = sole[sp < ENTER_V]
    if len(vals) < 5:
        vals = sole.ravel()
    return float(np.percentile(vals, 10))


def _span_edges(sp_list, k, F):
    s, e = sp_list[k]
    prev_e = sp_list[k - 1][1] if k > 0 else -10 ** 9
    next_s = sp_list[k + 1][0] if k + 1 < len(sp_list) else 10 ** 9
    return max(0, s - BLEND, (prev_e + s + 1) // 2), min(F, e + BLEND, (e + next_s + 1) // 2)


def _yaw_locks(psi, mask, fps, sp):
    """Per-frame yaw correction (rad) holding the foot heading at its speed-weighted span mean; ease regions carry
    the edge correction (the caller's weight ramp fades it)."""
    corr = np.zeros(len(psi))
    sp_list = spans(mask)
    for k, (s, e) in enumerate(sp_list):
        wt = 1.0 / (sp[s:e] + 0.05)
        target = float((psi[s:e] * wt).sum() / wt.sum())
        corr[s:e] = target - psi[s:e]
        lo, hi = _span_edges(sp_list, k, len(psi))
        corr[lo:s] = corr[s]
        corr[e:hi] = corr[e - 1]
    return corr


def _locks(p, mask, w, fps, floor):
    """Per-frame lock position for one joint: inside (and around) each span a fixed xz point (speed-weighted
    mean, slowest frames dominate); y follows the original but never below the floor."""
    lock = p.copy()
    lock[:, 1] = np.maximum(p[:, 1], floor)
    sp = _speed(p, fps)
    F = len(p)
    sp_list = spans(mask)
    for k, (s, e) in enumerate(sp_list):
        wt = 1.0 / (sp[s:e] + 0.05)
        xz = (p[s:e][:, [0, 2]] * wt[:, None]).sum(0) / wt.sum()
        # ease region: up to `blend` frames, never past the midpoint of the gap to a neighbouring span
        lo, hi = _span_edges(sp_list, k, F)
        lock[s:e, 0] = xz[0]
        lock[s:e, 2] = xz[1]
        # ease regions carry the (constant) offset of the span edge, so the caller's weight ramp decays a fixed
        # correction instead of chasing a point the swinging foot is rapidly leaving
        lock[lo:s] = p[lo:s] + (lock[s] - p[s])
        lock[e:hi] = p[e:hi] + (lock[e - 1] - p[e - 1])
    return lock


# ----------------------------------------------------------------------------------------------- in place / loop
def make_in_place(root, rot, fps=FPS, keep_sway=True):
    """Remove horizontal root travel; keep height, body rotation and (by default) the natural side-to-side and
    fore-aft sway (only the slow travel component, a ~1 s Gaussian trend, is removed). Feet will slide backwards
    like on a treadmill: do not foot-lock an in-place clip."""
    root = np.asarray(root, np.float64).copy()
    xz = root[:, [0, 2]]
    if keep_sway and len(root) > 10:
        trend = _filter(xz, sigma=max(2.0, 0.5 * fps), odd=True)
        new = xz - trend  # sway around the origin
    else:
        new = np.zeros_like(xz)
    root[:, 0], root[:, 2] = new[:, 0], new[:, 1]
    return root.astype(np.float32), np.asarray(rot, np.float32).copy()


def _loop_features(root, rot):
    """Heading-invariant pose features: hips-relative joint positions in the hips' yaw frame + root height."""
    G, P = fk_full(root, rot)
    psi = heading(G[:, 0])
    inv = yaw_quat(-psi)
    rel = P - P[:, :1] * np.array([1, 0, 1])
    rel = qrot(inv[:, None], rel)
    return rel, psi


def seam_error(root, rot):
    """Seam jump of a looping clip: hips-relative, heading-aligned joint displacement between the last and first
    frame (cm), and as a ratio of the median per-frame displacement inside the clip (1.0 = invisible)."""
    rel, _ = _loop_features(root, rot)
    step = np.linalg.norm(np.diff(rel, axis=0), axis=-1).mean(1)
    seam = float(np.linalg.norm(rel[0] - rel[-1], axis=-1).mean())
    vel_in = np.diff(rel, axis=0)
    acc_seam = float(np.linalg.norm((rel[0] - rel[-1]) - vel_in[-1], axis=-1).mean())
    acc_typ = float(np.median(np.linalg.norm(np.diff(vel_in, axis=0), axis=-1).mean(1)))
    return {"seam_cm": round(100 * seam, 2), "seam_ratio": round(seam / max(np.median(step), 1e-6), 2),
            "seam_accel_ratio": round(acc_seam / max(acc_typ, 1e-6), 2)}


def find_loop_window(root, rot, fps=FPS, min_seconds=1.0, max_seconds=None, vel_weight=0.5, skip_seconds=0.3):
    """Best (start, end) with frame `end` ~ frame `start` (pose + velocity, heading-invariant); the loop is
    frames start..end-1. Longer windows win ties."""
    rel, _ = _loop_features(root, rot)
    F = len(rel)
    vel = np.gradient(rel, axis=0) * fps / 10.0
    feat = np.concatenate([rel.reshape(F, -1), vel_weight * vel.reshape(F, -1),
                           np.asarray(root)[:, 1:2] * 3.0], 1)
    d = ((feat[:, None, :] - feat[None, :, :]) ** 2).sum(-1)
    lo = int(round(min_seconds * fps))
    hi = int(round(max_seconds * fps)) if max_seconds else F
    skip = min(int(round(skip_seconds * fps)), max(0, F - lo - 2) // 2)
    best, bi, bj = np.inf, 0, F - 1
    for i in range(skip, F - lo):
        for j in range(i + lo, min(F - skip, i + hi + 1) if F - skip > i + lo else F):
            c = d[i, j] * (1.0 + 0.35 * (1.0 - (j - i) / F))
            if c < best:
                best, bi, bj = c, i, j
    return bi, bj, float(best)


def _seam_offsets(dp, dv, L, N):
    """Per-frame additive offsets (L, ...) for a loop seam: the end side ramps to +dp/2 with slope +dv/2 at the
    virtual frame L, the start side starts at -dp/2 with slope -dv/2, both easing to zero over N frames with zero
    slope (cubic Hermite). Afterwards x[L-1] -> x[0] continues with matching value and velocity."""
    dp, dv = np.asarray(dp, np.float64), np.asarray(dv, np.float64)
    t = np.arange(L, dtype=np.float64)
    se = np.clip((t - (L - N)) / N, 0, 1)
    ss = np.clip((N - t) / N, 0, 1)
    h = lambda x: x * x * (3 - 2 * x)  # noqa: E731
    g = lambda x: x ** 3 - x ** 2      # noqa: E731
    sh = (L,) + (1,) * dp.ndim
    return (0.5 * dp * (h(se) - h(ss)).reshape(sh) + 0.5 * dv * N * (g(se) + g(ss)).reshape(sh))


def make_loop(root, rot, fps=FPS, *, window=None, blend_frames=None, straighten=True, min_seconds=1.0,
              foot_lock=True, stationary_speed=0.15, contacts=None, contact_mode="union"):
    """Turn a cyclic motion into a seamless loop. Picks the best window (pose + velocity similarity), crops it
    and distributes the seam difference over both ends (half each, smooth-eased): local rotations, hips yaw-free
    rotation, root height and heading-local root velocity are cross-faded so last -> first is continuous.
    Travelling cycles keep their mean velocity; with straighten=True the net turn over the loop is removed so the
    loop walks in a straight line when repeated with root motion; cycles slower than stationary_speed (m/s) are
    treated as in-place (zero net drift per repeat). foot_lock re-solves foot contacts loop-aware (clean_loop).
    Returns (root, rot, info); info["loop_offset_xz_m"] is the root-motion step from one repeat to the next."""
    root = np.asarray(root, np.float64)
    rot = hemisphere(qnorm(np.asarray(rot, np.float64)))
    if window is None:
        i, j, cost = find_loop_window(root, rot, fps, min_seconds=min_seconds)
    else:
        (i, j), cost = window, None
    L = j - i
    raw_r, raw_q = root[i:j].copy(), rot[i:j].copy()
    info = {"window": [int(i), int(j)], "frames": int(L), "seconds": round(L / fps, 2),
            "match_cost": None if cost is None else round(cost, 4),
            "seam_before": seam_error(raw_r.astype(np.float32), raw_q.astype(np.float32))}
    N = int(blend_frames or max(3, min(int(0.4 * fps), L // 3)))

    # hips: split into heading yaw and yaw-free remainder
    psi_all = np.unwrap(heading(rot[i:j + 1, 0]))
    hrel = qmul(yaw_quat(-psi_all), rot[i:j + 1, 0])
    loc = rot[i:j + 1].copy()
    loc[:, 0] = hrel
    loc = hemisphere(loc)
    # seam offsets (cubic Hermite, split half/half between both ends) matching pose AND velocity at last -> first
    def rv(a, b):  # rotation vector of a * b^-1
        return qlog(qmul(a, qinv(b)))
    dp = rv(loc[0], loc[L])
    dv = rv(loc[1], loc[0]) - rv(loc[L], loc[L - 1])
    o = _seam_offsets(dp, dv, L, N)
    new_loc = qmul(qexp(o), loc[:L])

    # heading: remove net turn (straight loop) or keep it
    psi = psi_all[:L + 1].copy()
    if straighten:
        psi = psi - (psi[L] - psi[0]) * np.arange(L + 1) / L
    new_psi = psi[:L]
    new_rot = new_loc.copy()
    new_rot[:, 0] = qmul(yaw_quat(new_psi), new_loc[:, 0])

    # root: height cross-fade + heading-local horizontal velocity cross-fade, re-integrated
    y = root[i:j + 1, 1]
    new_y = y[:L] + _seam_offsets(y[0] - y[L], (y[1] - y[0]) - (y[L] - y[L - 1]), L, N)
    xz = root[i:j + 1][:, [0, 2]]
    vel = np.diff(xz, axis=0)                                       # L steps (frame k -> k+1)
    c, s = np.cos(-psi_all[:L]), np.sin(-psi_all[:L])
    lv = np.stack([c * vel[:, 0] + s * vel[:, 1], -s * vel[:, 0] + c * vel[:, 1]], 1)  # rotate into heading frame
    # velocity seam: step L-1 (into virtual frame L) should continue into step 0
    nxt = np.diff(root[j:j + 2][:, [0, 2]], axis=0)
    if len(nxt):
        cc, ss = np.cos(-psi_all[L]), np.sin(-psi_all[L])
        lv_next = np.array([cc * nxt[0, 0] + ss * nxt[0, 1], -ss * nxt[0, 0] + cc * nxt[0, 1]])
    else:
        lv_next = lv[-1]
    lv = lv + _seam_offsets(lv[0] - lv_next, (lv[1] - lv[0]) - (lv_next - lv[L - 1]), L, N)
    c2, s2 = np.cos(new_psi), np.sin(new_psi)
    wv = np.stack([c2 * lv[:, 0] + s2 * lv[:, 1], -s2 * lv[:, 0] + c2 * lv[:, 1]], 1)
    stationary = bool(np.linalg.norm(wv.sum(0)) * fps / L < stationary_speed)
    if stationary:  # (near) in-place cycle: remove the residual drift so repeats stay put and feet stay planted
        wv = wv - wv.mean(0)
    new_xz = np.concatenate([xz[:1], xz[:1] + np.cumsum(wv[:-1], axis=0)], 0)
    new_root = np.stack([new_xz[:, 0], new_y, new_xz[:, 1]], 1)
    new_rot = qnorm(new_rot)
    loop_step = wv[-1]  # displacement from last frame to the next loop's first frame
    info["loop_offset_xz_m"] = [round(float(v), 3) for v in (new_xz[-1] + loop_step - new_xz[0])]
    info["mean_speed_ms"] = round(float(np.linalg.norm(new_xz[-1] + loop_step - new_xz[0]) * fps / L), 3)
    info["blend_frames"] = N
    info["stationary"] = stationary
    if foot_lock:
        kw = {}
        if contacts is not None:
            kw = {"contacts": np.asarray(contacts)[i:j], "contact_mode": contact_mode}
        new_root, new_rot, ci = clean_loop(new_root, new_rot, fps, loop_offset=new_xz[-1] + loop_step - new_xz[0],
                                           loop_yaw=float(psi[L] - psi[0]), **kw)
        info["foot_lock"] = {k: ci[k] for k in ("before", "after", "ground_offset_m")}
    info["seam_after"] = seam_error(np.asarray(new_root, np.float32), np.asarray(new_rot, np.float32))
    info["seam_before"] = {k: float(v) for k, v in info["seam_before"].items()}
    info["seam_after"] = {k: float(v) for k, v in info["seam_after"].items()}
    return np.asarray(new_root, np.float32), np.asarray(new_rot, np.float32), info


def _tile(root, rot, offset_xz, yaw, copies=3):
    """Repeat a loop `copies` times, each copy moved by the loop's root offset and yaw (root motion)."""
    root = np.asarray(root, np.float64)
    rot = np.asarray(rot, np.float64)
    rs, qs = [], []
    R_acc = np.array([0.0, 0.0, 0.0, 1.0])
    t_acc = np.zeros(3)
    step_q = yaw_quat(np.float64(yaw))
    o = np.array([offset_xz[0], 0.0, offset_xz[1]])
    p0 = root[0] * np.array([1, 0, 1])
    for _ in range(copies):
        r = qrot(R_acc, root - p0) + p0 + t_acc
        r[:, 1] = root[:, 1]
        q = rot.copy()
        q[:, 0] = qmul(np.broadcast_to(R_acc, q[:, 0].shape), q[:, 0])
        rs.append(r)
        qs.append(q)
        t_acc = t_acc + qrot(R_acc, o)
        R_acc = qmul(step_q, R_acc)
    return np.concatenate(rs), np.concatenate(qs)


def clean_loop(root, rot, fps=FPS, *, loop_offset=(0.0, 0.0), loop_yaw=0.0, **kw):
    """clean() for a looping clip: contacts that cross the seam are handled by cleaning three tiled copies and
    keeping the middle one, so the result still loops seamlessly."""
    L = len(root)
    tr, tq = _tile(root, rot, loop_offset, loop_yaw)
    if kw.get("contacts") is not None and len(kw["contacts"]) == L:
        kw["contacts"] = np.tile(np.asarray(kw["contacts"]), (3, 1))
    cr, cq, info = clean(tr, tq, fps, **kw)
    p0 = np.asarray(root, np.float64)[0] * np.array([1, 0, 1])
    # undo the middle copy's placement
    mid_r = np.asarray(cr[L:2 * L], np.float64)
    mid_q = np.asarray(cq[L:2 * L], np.float64)
    off = np.array([loop_offset[0], 0.0, loop_offset[1]])
    inv = yaw_quat(np.float64(-loop_yaw))
    y = mid_r[:, 1].copy()
    mid_r = qrot(inv, mid_r - p0 - off) + p0
    mid_r[:, 1] = y
    mid_q[:, 0] = qmul(np.broadcast_to(inv, mid_q[:, 0].shape), mid_q[:, 0])
    info["before"] = metrics(root, rot, fps)
    info["after"] = metrics(mid_r, mid_q, fps)
    return mid_r.astype(np.float32), qnorm(mid_q).astype(np.float32), info


# ----------------------------------------------------------------------------------------------- io
def save(motion_dir, root, rot):
    """Write root_positions.f32 and local_rotations_xyzw.f32 (little-endian float32, kimodo layout)."""
    d = Path(motion_dir)
    d.mkdir(parents=True, exist_ok=True)
    root = np.ascontiguousarray(root, dtype="<f4").reshape(-1, 3)
    rot = np.ascontiguousarray(rot, dtype="<f4").reshape(root.shape[0], J, 4)
    root.tofile(d / "root_positions.f32")
    rot.tofile(d / "local_rotations_xyzw.f32")
    return d


def retime(root, rot, factor, fps=FPS):
    """Play the motion `factor` times faster (factor > 1: shorter clip, faster motion; < 1: slower). Root positions
    are resampled linearly, rotations with per-joint slerp, so the result keeps fps and skeleton. Used for speeds the
    model doesn't reach on its own (it tops out around 3 m/s, so a sprint is a 1.3x retimed run)."""
    root = np.asarray(root, np.float64)
    rot = hemisphere(qnorm(np.asarray(rot, np.float64)))
    F = len(root)
    n = max(2, int(round((F - 1) / float(factor))) + 1)
    t = np.linspace(0.0, F - 1, n)
    i0 = np.clip(np.floor(t).astype(int), 0, F - 2)
    a = (t - i0)[:, None]
    new_root = root[i0] * (1 - a) + root[i0 + 1] * a
    q0, q1 = rot[i0], rot[i0 + 1]
    rel = qmul(qinv(q0), q1)                       # q0^-1 q1, then q0 * rel^a
    new_rot = qmul(q0, qpow(rel, a))  # a: (n,1) broadcasts over joints
    return new_root.astype(np.float32), qnorm(new_rot).astype(np.float32)
