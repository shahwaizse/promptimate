"""Studio-free director: everything that moves, per frame, from the episode + performance + asset library.
Writes the same files export.export_dynamic() pulls out of Studio (dynamic.json, frames.npz), so the renderer can't
tell the difference.

    build(ep, perf_actors, out_dir, fps, t_end)

perf_actors: {name: {"clips": [...]}} (roblox_perform's state.json). ep: a paced episode module (CAST, PLACE, FACES,
PROPS with times resolved to seconds)."""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import numpy as np

import export as X
import library as L
import pose as PO

HIDE_Y = -2000.0


def _cf(c):
    return np.asarray(c[:3], float), np.asarray(c[3:12], float).reshape(3, 3)


def _q(R):
    return PO.m2q(R)


def euler_xy(tilt_deg, yaw_deg):
    """CFrame.Angles(rx, ry, 0) = Rx @ Ry (Roblox applies Z, then Y, then X: R = Rx Ry Rz)."""
    rx, ry = math.radians(tilt_deg), math.radians(yaw_deg)
    Rx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    return Rx @ PO.yaw_mat(ry)


def angles(rx, ry, rz):
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = PO.yaw_mat(b)
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


def ground_y(static_parts, x, z, top=60.0):
    """Highest upward-facing surface under (x, z) below `top`: boxes only (good enough for prop placement)."""
    best = 0.0
    for p in static_parts:
        if p["kind"] not in ("box",) or p.get("tr", 0) > 0.9:
            continue
        pos, R = _cf(p["cf"])
        h = np.asarray(p["size"]) / 2
        loc = R.T @ (np.array([x, pos[1], z]) - pos)
        if abs(loc[0]) <= h[0] and abs(loc[2]) <= h[2]:
            y = pos[1] + np.abs(R[1]) @ h
            if best < y < top:
                best = y
    return best


def build(ep, perf_actors: dict, out: Path, fps: int, t_end: float, static: dict | None = None) -> dict:
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    looks, props_lib = L.looks(), L.props()
    own = L.LIB.parent / "own" / "looks.json"
    if os.environ.get("PROMPTIMATE_OWN_ASSETS", "1") != "0" and own.exists():
        looks = dict(looks, **json.loads(own.read_text()))       # our own characters win over catalog ones
    cast = {c["name"]: c for c in getattr(ep, "CAST", [])}
    names = sorted(n for n in cast if n in perf_actors)
    parts = []          # exported part dicts (renderer specs)
    actors = {}
    # ---- characters: 6 R6 body parts + accessories (offset from their host body part)
    acc_rel = []        # per part: (actor, host body part, rel pos, rel rot) or None
    for n in names:
        want = cast[n]["look"]
        lk = looks.get(want) or next((v for k, v in looks.items() if k.split("#")[0] == want), None)
        if lk is None:
            raise KeyError(f"look '{cast[n]['look']}' of {n} is not in the library (library.py looks)")
        first = len(parts) + 1
        for bp in ("Torso", "Head", "Left Arm", "Right Arm", "Left Leg", "Right Leg"):
            d = dict(lk["body"][bp])
            d["name"], d["owner"] = bp, n
            parts.append(d)
            acc_rel.append((n, bp, None, None))
        for a in lk["acc"]:
            d = dict(a)
            d["owner"] = n
            parts.append(d)
            acc_rel.append((n, a["host"], np.asarray(a["rel"][:3]), np.asarray(a["rel"][3:12]).reshape(3, 3)))
        actors[n] = {"shirt": lk["shirt"], "pants": lk["pants"], "tee": lk["tee"], "first": first, "last": len(parts),
                     "arms": lk.get("arms", 0.55)}
    # ---- episode props: library models placed at their home pivots (scaled to the asked height)
    prop_parts = {}     # prop name -> [(part index, rel pos, rel rot)]
    home = {}
    for i, it in enumerate(getattr(ep, "PLACE", [])):
        lib = props_lib.get(it["prop"])
        if lib is None:
            raise KeyError(f"prop '{it['prop']}' is not in the library")
        nm = it.get("name") or f"{it['prop']}{i + 1}"
        s = (it["height"] / lib["size"][1]) if it.get("height") and lib["size"][1] > 0 else 1.0
        y = it.get("y")
        if y is None:
            y = ground_y((static or {}).get("parts", []), it["at"][0], it["at"][1])
        home[nm] = (np.array([it["at"][0], y, it["at"][1]], float), euler_xy(it.get("tilt", 0), it.get("yaw", 0)))
        prop_parts[nm] = []
        for p in lib["parts"]:
            d = dict(p)
            d["size"] = [v * s for v in p["size"]]
            if (d.get("mesh") or {}).get("special"):
                sp = dict(d["mesh"]["special"])
                sp["scale"] = [v * s for v in sp["scale"]]
                d["mesh"] = dict(d["mesh"], special=sp)
            d["owner"] = "prop:" + nm
            if it.get("text"):
                pass
            prop_parts[nm].append((len(parts), np.asarray(p["cf"][:3]) * s, np.asarray(p["cf"][3:12]).reshape(3, 3)))
            parts.append(d)
            acc_rel.append(None)
    # ---- prop cues: spans and hand attachment, per object
    cues = {}
    for c in getattr(ep, "PROPS", []):
        path = c["path"]
        if len(path) >= 4 and path[1] == "Sets" and path[2] == "EpisodeProps":
            cues.setdefault(path[3], []).append(c)
    hidden_static = [".".join(c["path"]) for c in getattr(ep, "PROPS", [])
                     if not (len(c["path"]) >= 4 and c["path"][2] == "EpisodeProps") and c.get("show") == []]
    faces = {n: sorted((float(t), e) for t, e in getattr(ep, "FACES", {}).get(n, [])) for n in names}
    fidx = {f: i + 1 for i, f in enumerate(X.FACES)}
    # ---- all frames at once
    nf = int(t_end * fps) + 1
    times = np.arange(nf) / fps
    body = {n: PO.pose_actor_frames({"clips": perf_actors[n]["clips"], "arms": actors[n]["arms"]}, times) for n in names}
    pose = np.zeros((nf, len(parts), 7), np.float32)
    fbytes = np.zeros((nf, len(names)), np.uint8)
    for ai, n in enumerate(names):
        cur = np.full(nf, fidx["neutral"], np.uint8)
        for ft, e in faces[n]:
            cur[times >= ft - 1e-6] = fidx.get(e, 1)
        fbytes[:, ai] = cur
    for i, rel in enumerate(acc_rel):
        if rel is None:
            continue
        n, host, rp, rr = rel
        hp, hq = body[n][host]
        if rp is None:
            pose[:, i, :3], pose[:, i, 3:] = hp, hq
        else:
            pose[:, i, :3] = hp + PO.qrot(hq, rp)
            pose[:, i, 3:] = PO.qmul(hq, PO.m2q(rr))
    for nm, plist in prop_parts.items():
        hp, hr = home[nm]
        hq = PO.m2q(hr)
        pv = np.repeat(hp[None], nf, 0)
        pq = np.repeat(hq[None], nf, 0)
        cs = cues.get(nm, [])
        spans = any(c.get("show") is not None for c in cs)
        state = np.full(nf, -1 if spans else -2)       # -1 hidden, -2 home, >= 0 the cue index in force
        for ci in range(len(cs) - 1, -1, -1):           # the first matching cue wins: assign in reverse
            c = cs[ci]
            if c.get("show") is None:
                state[state == -2] = ci
                continue
            for sp in c["show"]:
                state[(times >= float(sp[0]) - 1e-6) & (times <= float(sp[1]) + 1e-6)] = ci
        pv[state == -1] += np.array([0, HIDE_Y, 0])
        for ci, c in enumerate(cs):
            at = c.get("attach")
            m = state == ci
            if not (at and at["actor"] in body and m.any()):
                continue
            ap, aq = body[at["actor"]][(at.get("hand") or "Right") + " Arm"]
            hand = ap[m] + PO.qrot(aq[m], np.array([0, -1 + 0.25, 0.0]))
            o = at.get("offset") or [0, -0.6, 0, 0, 0, 0]
            pv[m] = hand + PO.qrot(aq[m], np.asarray(o[:3], float))
            pq[m] = PO.qmul(aq[m], PO.m2q(angles(*o[3:6])))
        for i, rp, rr in plist:
            pose[:, i, :3] = pv + PO.qrot(pq, rp)
            pose[:, i, 3:] = PO.qmul(pq, PO.m2q(rr))
    (out / "dynamic.json").write_text(json.dumps({"parts": parts, "actors": actors, "order": names}))
    np.savez(out / "frames.npz", pose=pose, face=fbytes, fps=fps, t0=0.0)
    return {"parts": len(parts), "frames": nf, "seconds": round(time.time() - t0, 1), "hidden_static": hidden_static}


def props_at_home(ep, static: dict | None = None) -> list[dict]:
    """The episode's props (PLACE) as world-space parts at their home pivots: staging sees them like set pieces."""
    lib = L.props()
    out = []
    for i, it in enumerate(getattr(ep, "PLACE", [])):
        m = lib.get(it["prop"])
        if m is None:
            continue
        nm = it.get("name") or f"{it['prop']}{i + 1}"
        s = (it["height"] / m["size"][1]) if it.get("height") and m["size"][1] > 0 else 1.0
        y = it.get("y")
        if y is None:
            y = ground_y((static or {}).get("parts", []), it["at"][0], it["at"][1])
        hp, hr = np.array([it["at"][0], y, it["at"][1]], float), euler_xy(it.get("tilt", 0), it.get("yaw", 0))
        for p in m["parts"]:
            d = dict(p)
            d["size"] = [v * s for v in p["size"]]
            rp, rr = np.asarray(p["cf"][:3]) * s, np.asarray(p["cf"][3:12]).reshape(3, 3)
            wp, wr = hp + hr @ rp, hr @ rr
            d["cf"] = [*wp, *wr.ravel()]
            d["path"] = f"Workspace.Sets.EpisodeProps.{nm}.{p['name']}"
            out.append(d)
    return out
