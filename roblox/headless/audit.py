"""Camera audit of a planned episode: what each final shot actually shows, measured on the GPU id/depth render of the
real camera (checks.py), sampled three times per shot.

    rep = audit(shots, perf, t_end, checks)  ->  {"bad_share": 0..1, "samples": n, "bad": [{t, shot, why, ...}], ...}

Per sample, inside the shot's own frame (the checks render a wider view):
  target   = the shot's subjects (or any character for a wide with none), or props for an insert
  cover    = share of the frame the target covers
  front    = share of the frame covered by something nearer than the target that isn't the target
  empty    = cover below EMPTY (an empty floor, a wall, the sky); blocked = front above BLOCKED
"""
from __future__ import annotations

import math
import os

import numpy as np

EMPTY = 0.02
EMPTY_PROP = 0.012
BLOCKED = 0.22
LENS = 2.5            # studs: anything this close to the lens is a foreground blob
LENS_SHARE = 0.10


def _window(fov, W, H, widen):
    th, thw = math.tan(math.radians(fov) / 2), math.tan(math.radians(min(fov * widen, 150)) / 2)
    k = th / thw
    x0, x1 = int(W * (1 - k) / 2), int(math.ceil(W * (1 + k) / 2))
    y0, y1 = int(H * (1 - k) / 2), int(math.ceil(H * (1 + k) / 2))
    return slice(max(0, y0), min(H, y1)), slice(max(0, x0), min(W, x1))


def _vp_of(pos, look, fov, CK):
    return CK._view_proj([(pos, look, fov)])[0]


def judge(ck, ids, dep, pos, look, fov, subs, prop, t):
    """One rendered sample -> (why or None, cover, front)."""
    import checks as CK
    names = ck.names
    ys, xs = _window(fov, CK.W, CK.H, CK.WIDEN)
    idw, dw = ids[ys, xs], dep[ys, xs]
    if prop:
        tgt, lim = idw == 2, EMPTY_PROP
    elif subs:
        tgt, lim = np.isin(idw, [100 + 2 * names.index(s_) + k for s_ in subs for k in (0, 1)]), EMPTY
    else:
        tgt, lim = (idw >= 100) & (idw < 200), EMPTY
    cover = float(tgt.mean())
    front = 0.0
    if tgt.any():
        dt = float(np.median(dw[tgt]))
        front = float(((dw < dt * 0.8) & ~tgt & np.isfinite(dw)).mean())
    lens = float(((dw < LENS) & ~tgt).mean())
    if lens > LENS_SHARE:
        front = max(front, BLOCKED + lens)
    why = "empty" if cover < lim else "blocked" if front > BLOCKED else None
    if not why and tgt.any():
        # something in front of the subject inside its own box (a lamp post across a face)
        rr, cc = np.nonzero(tgt)
        box = (slice(rr.min(), rr.max() + 1), slice(cc.min(), cc.max() + 1))
        tb, db = tgt[box], dw[box]
        dt_ = float(np.median(dw[tgt]))
        occ = float(((db < dt_ - 0.6) & ~tb & np.isfinite(db)).mean())
        if occ > 0.15:
            why = "occluded"
    if not why and not prop:
        others = (idw >= 100) & (idw < 200) & ~tgt         # other people filling the frame (a giant's legs)
        if float(others.mean()) > 0.35:
            why = "crowded"
    if not why and subs and not prop:
        # every subject's face shows (a partner's body hiding the main subject's head passed as "target coverage")
        for s_ in subs[:2]:
            if float((idw == 101 + 2 * names.index(s_)).mean()) < 0.004:
                why = "faceless"
                break
    for s_i, s_ in enumerate(subs[:2] if (not why and subs and not prop) else []):
        hi = ck.actor_index(s_, "Head")
        if hi is not None and s_i > 0:      # the partner of a two-shot: its head inside the frame too
            hp2, _hr2 = ck.part_world(hi, t)
            q2 = _vp_of(pos, look, fov, CK) @ np.array([*hp2, 1.0])
            if q2[3] > 1e-6:
                u2, v2 = q2[0] / q2[3], q2[1] / q2[3]
                k2 = math.tan(math.radians(fov) / 2) / math.tan(math.radians(min(fov * CK.WIDEN, 150)) / 2)
                if abs(u2) > k2 * 0.9 or v2 > k2 * 0.85:
                    why = "headless"
    if not why and subs and not prop:
        hi = ck.actor_index(subs[0], "Head")
        if hi is not None:
            hp, hr = ck.part_world(hi, t)
            q = _vp_of(pos, look, fov, CK) @ np.array([*hp, 1.0])
            if q[3] > 1e-6:
                u, v = q[0] / q[3], q[1] / q[3]
                k_ = math.tan(math.radians(fov) / 2) / math.tan(math.radians(min(fov * CK.WIDEN, 150)) / 2)
                if abs(u) > k_ * 0.85 or v > k_ * 0.82 or v < -k_ * 0.5:
                    why = "headless"
            to = np.asarray(pos, float) - hp
            face = float((hr @ np.array([0, 0, -1.0])) @ (to / max(np.linalg.norm(to), 1e-6)))
            if not why and face < -0.2:
                why = "back"
    return why, cover, front


def composition(ck, ids, pos, look, fov, subject):
    """Lower is better: a chest filling the frame, a head too low / too high, a subject that's a speck."""
    import checks as CK
    if subject not in ck.names:
        return 0.0
    ai = ck.names.index(subject)
    ys, xs = _window(fov, CK.W, CK.H, CK.WIDEN)
    idw = ids[ys, xs]
    body, head = float((idw == 100 + 2 * ai).mean()), float((idw == 101 + 2 * ai).mean())
    cost = max(0.0, body - 0.38) * 12              # judges: "the same striped torso filling the frame"
    cost += max(0.0, 0.03 - (body + head)) * 40     # a speck
    rows = np.nonzero((idw == 101 + 2 * ai).any(1))[0]
    if len(rows):                                   # head centre, 0 = bottom of frame, 1 = top (GL rows grow upward)
        hv = float(rows.mean()) / max(idw.shape[0] - 1, 1)
        cost += max(0.0, 0.55 - hv) * 6 + max(0.0, hv - 0.78) * 14     # judges: "heads cropped at the top edge"
    return cost


def search(shots, i, perf, t_end, ck, design=False, fix=None, avoid=None):
    """Every framing of shot i's subject (12 angles x 3 sizes x 2 heights), each judged at three instants in one batched
    render per instant: the best (fewest bad samples, then nearest the asked angle/size) or None."""
    import roblox_record as RR
    c = shots[i]
    if not c.subject or c.subject not in ck.names:
        return None
    b = shots[i + 1].start if i + 1 < len(shots) else t_end
    tm = (c.start + b) / 2
    q = [[c.subject, tm]] + ([[c.with_, tm]] if c.with_ and c.with_ in ck.names else [])
    poses = ck.poses(q)
    if not poses or not poses[0]:
        return None
    other = poses[1] if len(poses) > 1 else None
    sizes = [c.shot] + [s_ for s_ in ("medium", "full", "close") if s_ != c.shot]
    if not c.cover and c.with_:          # a size-difference two-shot: both whole bodies, never a close-up
        sizes = [c.shot] + [s_ for s_ in ("full", "wide") if s_ != c.shot]
    lifts = (0.0, 0.5)
    if fix == "wider":
        sizes = ["full", "wide"] if c.shot in ("close", "medium") else ["wide", "full"]
    elif fix == "closer":
        sizes = ["close", "medium"] if c.shot not in ("close",) else ["close"]
    elif fix == "higher":
        lifts = (0.6, 1.1)
    # the front arc only (the reference grammar: frontal; behind a stage line is the crowd and the set's walls)
    arc = (0, 20, -20, 40, -40, 60, -60) if os.environ.get("PROMPTIMATE_FRONT_ARC", "1") != "0" else tuple(range(0, 360, 30))
    cands = [(sz, ang, lift) for sz in sizes for lift in lifts for ang in arc]
    cams = [RR._cam_for(poses[0], other, sz, c.angle + ang, lift) for sz, ang, lift in cands]
    if avoid is not None and avoid[0] is not None and avoid[1] is not None:
        # a reviewer rejected this view: nothing within 35 degrees of it
        ad = np.asarray(avoid[0], float) - np.asarray(avoid[1], float)
        keep = []
        for j, (p_, l_, fv) in enumerate(cams):
            d_ = np.asarray(p_, float) - np.asarray(l_, float)
            cosang = float(ad[[0, 2]] @ d_[[0, 2]] / (np.linalg.norm(ad[[0, 2]]) * np.linalg.norm(d_[[0, 2]]) + 1e-9))
            if cosang < 0.82:
                keep.append(j)
        if keep:
            cams = [cams[j] for j in keep]
            cands = [cands[j] for j in keep]
    subs = [c.subject] + ([c.with_] if other else [])
    bad = np.zeros(len(cams))
    for f in (0.2, 0.5, 0.8):
        t = c.start + (b - c.start) * f
        u = min(max((t - c.start) / max(b - c.start, 0.5), 0.0), 1.0)
        shrink = 1 - (c.push or 0) * (u * u * (3 - 2 * u))          # RR.camera's eased push-in
        cams_t = [(p_, l_, fv * shrink) for p_, l_, fv in cams]
        ids, dep, _vp = ck._render(t, cams_t)
        for j, (p_, l_, fv) in enumerate(cams_t):
            why, _cv, _fr = judge(ck, ids[j], dep[j], p_, l_, fv, subs, None, t)
            bad[j] += why is not None
    comp = np.zeros(len(cams))
    if design:
        t = c.start + (b - c.start) * 0.5
        ids, dep, _vp = ck._render(t, cams)
        for j, (p_, l_, fv) in enumerate(cams):
            comp[j] = composition(ck, ids[j], p_, l_, fv, c.subject)
        # no jump cut: the previous shot of the same subject from (nearly) the same direction
        prev = next((shots[k] for k in range(i - 1, -1, -1) if shots[k].subject), None)
        if prev is not None and prev.subject == c.subject and prev.pos is not None and prev.look is not None:
            pd = np.asarray(prev.pos, float) - np.asarray(prev.look, float)
            for j, (p_, l_, fv) in enumerate(cams):
                d_ = np.asarray(p_, float) - np.asarray(l_, float)
                cosang = float(pd[[0, 2]] @ d_[[0, 2]] / (np.linalg.norm(pd[[0, 2]]) * np.linalg.norm(d_[[0, 2]]) + 1e-9))
                if cosang > 0.94 and abs(fv - (prev.fov or fv)) < 6:
                    comp[j] += 2.0
    cost = [bad[j] * 10 + comp[j] + min(abs(cands[j][1]) % 360, 360 - abs(cands[j][1]) % 360) / 60 + sizes.index(cands[j][0]) * 0.8
            + cands[j][2] * 2 for j in range(len(cams))]
    j = int(np.argmin(cost))
    return (cams[j], int(bad[j]), cands[j])


def audit(shots, perf, t_end: float, ck) -> dict:
    import checks as CK
    import roblox_record as RR
    names = ck.names
    samples, bad = 0, []
    per_shot = []
    for i, c in enumerate(shots):
        b = shots[i + 1].start if i + 1 < len(shots) else t_end
        if b - c.start < 0.2:
            continue
        worst = None
        for f in (0.2, 0.5, 0.8):
            t = c.start + (b - c.start) * f
            _k, _c, pos, look, fov = RR.camera(shots, perf, t)
            ids, dep, _vp = ck._render(t, [(pos, look, fov)])
            subs = [s_ for s_ in ([c.subject] if c.subject else []) + ([c.with_] if c.with_ else []) if s_ in names]
            if not subs and c.subjects:
                subs = [s_ for s_ in c.subjects if s_ in names]
            why, cover, front = judge(ck, ids[0], dep[0], pos, look, fov, subs, c.prop, t)
            samples += 1
            if why:
                bad.append({"t": round(t, 2), "shot": c.name or f"{c.start:.1f}", "why": why, "cover": round(cover, 3),
                            "front": round(front, 2), "kind": "prop" if c.prop else "subject" if subs else "wide"})
                worst = why
        per_shot.append((i, worst))
    return {"bad_share": round(len(bad) / max(samples, 1), 3), "samples": samples,
            "empty": sum(b["why"] == "empty" for b in bad), "blocked": sum(b["why"] == "blocked" for b in bad),
            "headless": sum(b["why"] == "headless" for b in bad), "back": sum(b["why"] == "back" for b in bad),
            "occluded": sum(b["why"] == "occluded" for b in bad), "crowded": sum(b["why"] == "crowded" for b in bad),
            "faceless": sum(b["why"] == "faceless" for b in bad),
            "by_kind": {k: sum(b["kind"] == k for b in bad) for k in ("prop", "subject", "wide")},
            "bad": bad, "per_shot": per_shot}


def _score(shots, i, perf, t_end, ck, cam=None):
    """Bad samples (0-3) of shot i, optionally with a replacement (pos, look, fov)."""
    import roblox_record as RR
    c = shots[i]
    if cam is not None:
        c = c.model_copy(update={"pos": [float(v) for v in cam[0]], "look": [float(v) for v in cam[1]], "fov": float(cam[2])})
        shots = shots[:i] + [c] + shots[i + 1:]
    r = audit(shots[i:i + 2] if i + 1 < len(shots) else [c], perf, shots[i + 1].start if i + 1 < len(shots) else t_end, ck)
    return len(r["bad"])


def repair(shots, perf, t_end: float, ck, log=print):
    """Shots the audit flags (2+ of 3 samples bad) get fixed: a subject shot takes the best of the planner's
    alternative framings; an empty prop insert or an empty wide becomes a framed shot of the nearest subject."""
    import roblox_record as RR
    rep = audit(shots, perf, t_end, ck)
    nbad = {}
    for b in rep["bad"]:
        nbad[b["shot"]] = nbad.get(b["shot"], 0) + 1
    alts = getattr(RR.frame_subjects, "alts", {})
    out, notes, convert = list(shots), [], []
    design = os.environ.get("PROMPTIMATE_DOP", "1") != "0"
    for i, c in enumerate(out):
        key = c.name or f"{c.start:.1f}"
        if design and c.subject and not c.prop and nbad.get(key, 0) < 2:
            r_ = search(out, i, perf, t_end, ck, design=True)
            if r_ is not None and r_[1] <= nbad.get(key, 0):
                (p_, l_, f_), nb_, cand_ = r_
                out[i] = c.model_copy(update={"pos": [round(float(v), 3) for v in p_], "look": [round(float(v), 3) for v in l_],
                                              "fov": float(f_)})
            continue
        if nbad.get(key, 0) < 2:
            continue
        if c.subject and not c.prop:
            r_ = search(out, i, perf, t_end, ck, design=design)
            if r_ is not None and r_[1] < nbad[key]:
                (p_, l_, f_), nb_, cand_ = r_
                out[i] = c.model_copy(update={"pos": [round(float(v), 3) for v in p_], "look": [round(float(v), 3) for v in l_],
                                              "fov": float(f_)})
                notes.append(f"{key}: {nbad[key]} bad -> {nb_} (search {cand_})")
                if nb_ == 0:
                    continue
                c = out[i]
                nbad[key] = nb_
        if c.subject and not c.prop and i in alts:
            best = (nbad[key], None)
            for cam in alts[i][:6]:
                s = _score(out, i, perf, t_end, ck, cam)
                if s < best[0]:
                    best = (s, cam)
                if s == 0:
                    break
            if best[1] is not None:
                p_, l_, f_ = best[1]
                out[i] = c.model_copy(update={"pos": [round(float(v), 3) for v in p_], "look": [round(float(v), 3) for v in l_],
                                              "fov": float(f_)})
                notes.append(f"{key}: {nbad[key]} bad -> {best[0]} (alternative framing)")
                continue
        # a prop insert / wide showing nothing: frame the nearest subject shot's subject instead
        b_ = out[i + 1].start if i + 1 < len(out) else t_end
        tm = (c.start + b_) / 2

        def visible(n):
            hi = ck.actor_index(n, "Head")
            return hi is not None and ck.pose[ck._frame(tm), hi, 1] > -500
        near = [out[j].subject for j in list(range(i - 1, -1, -1)) + list(range(i + 1, len(out))) if out[j].subject]
        # a subject shot whose every framing failed: someone else (the same person is blocked from everywhere)
        subj = next((n for n in near if n in ck.names and visible(n) and n != c.subject), None) or             next((n for n in near if n in ck.names and visible(n)), None)
        if subj is None:          # whoever is visible closest to where the shot was looking
            _k, _c, pos0, look0, _f = RR.camera(out, perf, tm)
            vis = [n for n in ck.names if visible(n) and n not in ck.alias]
            if vis:
                subj = min(vis, key=lambda n: float(np.sum((ck.part_world(ck.actor_index(n, "Head"), tm)[0] - np.asarray(look0)) ** 2)))
        if subj and (c.prop or not c.subject or nbad[key] >= 3):
            out[i] = c.model_copy(update={"prop": None, "pos": None, "look": None, "subject": subj, "with_": None,
                                          "shot": "medium", "angle": 15.0, "subjects": [subj]})
            convert.append(i)
            notes.append(f"{key}: {nbad[key]} bad -> medium shot of {subj}")
    if convert:
        out = RR.frame_subjects(out, t_end)
    after = audit(out, perf, t_end, ck)
    log(f"camera audit: {rep['bad_share']:.1%} bad -> {after['bad_share']:.1%} after repair ({len(notes)} shots changed)")
    return out, notes, rep, after
