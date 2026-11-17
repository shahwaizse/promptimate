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
            ids, dep = ids[0], dep[0]
            ys, xs = _window(fov, CK.W, CK.H, CK.WIDEN)
            idw, dw = ids[ys, xs], dep[ys, xs]
            subs = [s for s in ((c.subjects if c.subjects else None) or ([c.subject] if c.subject else [])) if s in names]
            if c.prop:
                tgt = idw == 2
                lim = EMPTY_PROP
            elif subs:
                ids_s = [100 + 2 * names.index(s) + k for s in subs for k in (0, 1)]
                tgt = np.isin(idw, ids_s)
                lim = EMPTY
            else:
                tgt = (idw >= 100) & (idw < 200)
                lim = EMPTY
            cover = float(tgt.mean())
            if tgt.any():
                dt = float(np.median(dw[tgt]))
                front = float(((dw < dt * 0.8) & ~tgt & np.isfinite(dw)).mean())
            else:
                dt, front = None, 0.0
            lens = float(((dw < LENS) & ~tgt).mean())
            if lens > LENS_SHARE:
                front = max(front, BLOCKED + lens)
            samples += 1
            why = "empty" if cover < lim else "blocked" if front > BLOCKED else None
            if why:
                bad.append({"t": round(t, 2), "shot": c.name or f"{c.start:.1f}", "why": why, "cover": round(cover, 3),
                            "front": round(front, 2), "kind": "prop" if c.prop else "subject" if subs else "wide"})
                worst = why
        per_shot.append((i, worst))
    return {"bad_share": round(len(bad) / max(samples, 1), 3), "samples": samples,
            "empty": sum(b["why"] == "empty" for b in bad), "blocked": sum(b["why"] == "blocked" for b in bad),
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
    for i, c in enumerate(out):
        key = c.name or f"{c.start:.1f}"
        if nbad.get(key, 0) < 2:
            continue
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
        subj = next((n for n in near if n in ck.names and visible(n)), None)
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
