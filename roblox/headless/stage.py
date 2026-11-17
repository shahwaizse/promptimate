"""Studio-free staging for roblox_perform: the place's geometry from the static export (plus the episode's props at
home) answering what perform asked Studio: the scene snapshot, ground heights, free standing spots, staging probes and
body checks (roblox_tools.WORLD interface).

Vertical rays (all of perform's ground queries) run on an XZ grid of triangles; part overlaps are oriented-box tests
(Studio's GetPartBoundsInBox + obbOverlap)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import hlrender as RD
import meshcache as MC
import pose as PO

CELL = 2.0
MIN_DEPTH = 0.15
BODY6 = ("Head", "Torso", "Left Arm", "Right Arm", "Left Leg", "Right Leg")


def _owner(path: str, name: str) -> tuple[str, str]:
    seg = (path or "").split(".")
    parent = seg[-2] if len(seg) >= 2 else ""
    return parent, f"{parent}.{name}" if parent else name


class World:
    def __init__(self, static: dict, props: list[dict] | None = None, index: dict | None = None):
        """static: export.export_static() dump; props: extra parts (episode props at home) in the same format."""
        index = index or json.loads((MC.OUT / "index.json").read_text())
        self.parts = [p for p in static["parts"] + (props or []) if p.get("cf")]
        n = len(self.parts)
        self.c = np.array([p["cf"][:3] for p in self.parts], float)
        self.R = np.array([np.array(p["cf"][3:12]).reshape(3, 3) for p in self.parts], float)
        self.h = np.array([p["size"] for p in self.parts], float) / 2
        self.top = self.c[:, 1] + np.einsum("nj,nj->n", np.abs(self.R[:, 1, :]), self.h)
        self.tr = np.array([p.get("tr", 0) for p in self.parts], float)
        self.cc = np.array([p.get("cc", True) for p in self.parts], bool)
        self.cq = np.array([p.get("cq", True) for p in self.parts], bool)
        self.block = np.array([p.get("block", p["kind"] == "box" and not (p.get("mesh") or {}).get("special"))
                               for p in self.parts], bool)
        self.name = [p["name"] for p in self.parts]
        self.path = [p.get("path", p["name"]) for p in self.parts]
        po = [_owner(p.get("path", ""), p["name"]) for p in self.parts]
        self.parent = [a for a, _ in po]
        self.owner = [b for _, b in po]
        self.rad = np.linalg.norm(self.h, axis=1)
        # spatial hash of part centres (overlap candidates)
        self.grid8 = {}
        for i, (x, z) in enumerate(np.floor(self.c[:, [0, 2]] / 8).astype(int)):
            self.grid8.setdefault((x, z), []).append(i)
        self.big = np.nonzero(self.rad > 12)[0]          # big parts: checked everywhere
        # triangles for vertical rays (each with its part index)
        sc = RD.Scene.__new__(RD.Scene)
        sc.ctx, sc.index, sc.meshes, sc.missing, sc.skins = None, index, {}, 0, {}
        mesh_cache = {}
        tris, tid = [], []
        for i, p in enumerate(self.parts):
            if self.tr[i] >= 0.95:
                continue
            spec = RD.Scene._specs(sc, p)[0] if True else None
            key = spec["key"]
            if key not in mesh_cache:
                if key in RD.PRIMS:
                    P_, _, _ = RD.PRIMS[key]()
                    mesh_cache[key] = (P_.astype(float), np.zeros(3), np.ones(3))
                else:
                    z = np.load(MC.OUT / f"{key}.npz")
                    mesh_cache[key] = (z["pos"][z["faces"].ravel()].astype(float), (z["lo"] + z["hi"]) / 2,
                                       np.maximum(z["hi"] - z["lo"], 1e-4))
            P_, centre, msize = mesh_cache[key]
            s = spec["scale"] * np.ones(3) if spec["native"] else spec["scale"] / msize
            W = (P_ - centre) * s @ self.R[i].T + self.c[i]
            tris.append(W.reshape(-1, 3, 3))
            tid.append(np.full(len(W) // 3, i))
        self.T = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
        self.tid = np.concatenate(tid) if tid else np.zeros(0, int)
        lo = np.floor(self.T[:, :, [0, 2]].min(1) / CELL).astype(int)
        hi = np.floor(self.T[:, :, [0, 2]].max(1) / CELL).astype(int)
        span = (hi - lo + 1)
        self.tgrid = {}
        for k in np.nonzero(span.prod(1) <= 4)[0]:          # small triangles: their few cells
            for x in range(lo[k, 0], hi[k, 0] + 1):
                for z in range(lo[k, 1], hi[k, 1] + 1):
                    self.tgrid.setdefault((x, z), []).append(k)
        self.big_tris = np.nonzero(span.prod(1) > 4)[0]      # large ones (floors, ramps): tested on every query
        self._bt_lo, self._bt_hi = self.T[self.big_tris][:, :, [0, 2]].min(1), self.T[self.big_tris][:, :, [0, 2]].max(1)
        self.tgrid = {k: np.array(v) for k, v in self.tgrid.items()}

    # ------------------------------------------------------------------------------------------- vertical rays
    def _down(self, x, y, z, length=60.0, skip=None):
        """Highest surface at (x, z) at or below y (and above y - length): (y, part index) or (None, None).
        skip(i) -> True to look through a part."""
        cand = self.tgrid.get((int(math.floor(x / CELL)), int(math.floor(z / CELL))))
        m = (self._bt_lo[:, 0] <= x) & (self._bt_hi[:, 0] >= x) & (self._bt_lo[:, 1] <= z) & (self._bt_hi[:, 1] >= z)
        ids = self.big_tris[m]
        if cand is not None:
            ids = np.concatenate([cand, ids])
        if len(ids) == 0:
            return None, None
        T = self.T[ids]
        a, b, c = T[:, 0], T[:, 1], T[:, 2]
        v0, v1 = b[:, [0, 2]] - a[:, [0, 2]], c[:, [0, 2]] - a[:, [0, 2]]
        v2 = np.array([x, z]) - a[:, [0, 2]]
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        ok = np.abs(den) > 1e-12
        den = np.where(ok, den, 1)
        u = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
        v = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
        inside = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
        yy = a[:, 1] + u * (b[:, 1] - a[:, 1]) + v * (c[:, 1] - a[:, 1])
        sel = inside & (yy <= y + 1e-4) & (yy >= y - length)
        if not sel.any():
            return None, None
        order = np.argsort(-yy[sel])
        hits_y, hits_p = yy[sel][order], self.tid[ids[sel]][order]
        for yv, pi in zip(hits_y, hits_p):
            if skip is None or not skip(int(pi)):
                return float(yv), int(pi)
        return None, None

    def ground_pts(self, pts):
        """GROUND_LUAU: ray down from p + 0.6 for 60 studs (characters aren't in this world)."""
        out = []
        for x, y, z in pts:
            g, _ = self._down(x, y + 0.6, z, 60)
            out.append(g if g is not None else y)
        return out

    # ---------------------------------------------------------------------------------------------- overlaps
    def _near_parts(self, centre, radius):
        if not hasattr(self, "_kd"):
            from scipy.spatial import cKDTree
            small = np.nonzero(self.rad <= 12)[0]
            self._kd, self._kd_ids = cKDTree(self.c[small]), small
        ids = self._kd_ids[self._kd.query_ball_point(centre, radius + 12)]
        ids = np.concatenate([ids, self.big]) if len(self.big) else ids
        d = np.linalg.norm(self.c[ids] - centre, axis=1)
        return ids[d <= self.rad[ids] + radius]

    def obb_depth(self, ca, Ra, ha, ids):
        """Penetration depth (0 = apart) of box (ca, Ra, ha) with parts ids, 15-axis SAT, vectorised."""
        if len(ids) == 0:
            return np.zeros(0)
        Rb, hb, cb = self.R[ids], self.h[ids], self.c[ids]
        A = Ra.T                                   # rows: box a axes
        d = cb - ca
        depth = np.full(len(ids), np.inf)
        axes = [np.broadcast_to(A[i], (len(ids), 3)) for i in range(3)] + [Rb[:, :, i] for i in range(3)]
        for i in range(3):
            for j in range(3):
                cr = np.cross(A[i][None, :], Rb[:, :, j])
                n = np.linalg.norm(cr, axis=1, keepdims=True)
                axes.append(np.where(n > 1e-6, cr / np.maximum(n, 1e-9), 0))
        for ax in axes:
            ra = np.abs(ax @ A.T) @ ha
            rb = np.einsum("nk,nk->n", np.abs(np.einsum("nj,njk->nk", ax, Rb)), hb)
            o = ra + rb - np.abs(np.einsum("nj,nj->n", d, ax))
            valid = np.linalg.norm(ax, axis=1) > 1e-6
            depth = np.where(valid, np.minimum(depth, o), depth)
        return np.maximum(depth, 0)

    def overlaps(self, C, Rs, Hs):
        """Many query boxes at once: (query index, part index, depth) for every overlapping pair (depth > 0)."""
        if not hasattr(self, "_kd"):
            self._near_parts(np.zeros(3), 1.0)
        C = np.asarray(C, float)
        lists = self._kd.query_ball_point(C, np.linalg.norm(Hs, axis=1) + 12)
        qi, pi = [], []
        for k, l in enumerate(lists):
            if l:
                qi.append(np.full(len(l), k)); pi.append(self._kd_ids[l])
            if len(self.big):
                qi.append(np.full(len(self.big), k)); pi.append(self.big)
        if not qi:
            return np.zeros(0, int), np.zeros(0, int), np.zeros(0)
        qi, pi = np.concatenate(qi), np.concatenate(pi)
        keep = np.linalg.norm(self.c[pi] - C[qi], axis=1) <= self.rad[pi] + np.linalg.norm(Hs[qi], axis=1)
        qi, pi = qi[keep], pi[keep]
        dep = np.zeros(len(qi))
        for a0 in range(0, len(qi), 100000):
            sl = slice(a0, a0 + 100000)
            dep[sl] = _sat(C[qi[sl]], Rs[qi[sl]], Hs[qi[sl]], self.c[pi[sl]], self.R[pi[sl]], self.h[pi[sl]])
        m = dep > 0
        return qi[m], pi[m], dep[m]

    def stand_free(self, q):
        out = []
        for x, z in q["pts"]:
            floor = q["floor"]
            c = np.array([x, floor + 0.35 + q["h"] / 2, z])
            ids = self._near_parts(c, max(q["r"], q["h"] / 2) * 1.8)
            ids = ids[(self.tr[ids] < 0.95) & self.cc[ids] & (self.top[ids] > floor + 0.35)]
            dep = self.obb_depth(c, np.eye(3), np.array([q["r"], q["h"] / 2, q["r"]]), ids)
            out.append(not bool(np.any(dep > 0)))
        return out


# ------------------------------------------------------------------------------------- perform's backend
class Staging:
    """roblox_tools.WORLD: everything perform asked Studio, for one episode."""

    def __init__(self, world: World, cast: list[dict], looks_arms: dict | None = None):
        self.w = world
        self.cast = {c["name"]: c for c in cast}
        self.arms = looks_arms or {}
        self.perf_actors = {}          # set by push(): name -> {"clips": [...]}

    def _floor_at(self, x, z):
        g, _ = self.w._down(x, 6.0, z, 30.0)
        return g if g is not None else 0.1

    def scene(self, actor_names, target_names, perf):
        out = {"actors": {}, "targets": {}, "parts": [], "humanoids": sorted(self.cast)}
        for n in actor_names:
            c = self.cast.get(n)
            if not c:
                out["actors"][n] = {"error": "not found"}
                continue
            x, z = float(c["at"][0]), float(c["at"][1])
            floor = self._floor_at(x, z)
            yaw = math.radians(c.get("yaw", 0))
            g, _ = self.w._down(x, floor + 3 + 3, z, 80)
            out["actors"][n] = {"path": ["Workspace", "Cast", n], "stand": 2.0, "width": 4.0, "x": x, "z": z,
                                "lookX": -math.sin(yaw), "lookZ": -math.cos(yaw), "floor": floor,
                                "ground": g if g is not None else floor, "r15": False}
        for t in target_names:
            idx = [i for i, p in enumerate(self.w.path) if p.split(".")[-1] == t or ("." + t + ".") in ("." + p + ".")]
            if not idx:
                continue
            exact = [i for i in idx if self.w.name[i] == t]
            if len(exact) == 1 and len(idx) == 1:
                i = exact[0]
                L = self.w.R[i][:, 2]
                out["targets"][t] = [*self.w.c[i], *(self.w.h[i] * 2), math.atan2(L[0], L[2])]
            else:
                pts = []
                for i in idx:
                    for sx in (-1, 1):
                        for sy in (-1, 1):
                            for sz in (-1, 1):
                                pts.append(self.w.c[i] + self.w.R[i] @ (self.w.h[i] * np.array([sx, sy, sz])))
                pts = np.array(pts)
                lo, hi = pts.min(0), pts.max(0)
                out["targets"][t] = [*((lo + hi) / 2), *(hi - lo), 0.0]
        centres = np.array([[float(self.cast[n]["at"][0]), float(self.cast[n]["at"][1])] for n in actor_names if n in self.cast])
        W = self.w
        for i in range(len(W.parts)):
            if W.tr[i] >= 0.95 or W.h[i, 1] * 2 < 0.3 or (W.h[i, 0] * 2) * (W.h[i, 2] * 2) >= 2500:
                continue
            if len(centres) and not np.any((np.abs(centres[:, 0] - W.c[i, 0]) < 45) & (np.abs(centres[:, 1] - W.c[i, 2]) < 45)):
                continue
            L = W.R[i][:, 2]
            out["parts"].append([round(W.c[i, 0], 1), round(W.c[i, 2], 1), round(W.h[i, 0] * 2, 1), round(W.h[i, 2] * 2, 1),
                                 round(math.atan2(-(-L[0]), -(-L[2])), 2), round(W.c[i, 1] + W.h[i, 1], 1)])
            if len(out["parts"]) >= 4000:
                break
        out["perf"] = json.dumps(perf) if perf else None
        return out

    def ground(self, pts):
        return self.w.ground_pts(pts)

    def stand_free(self, q):
        return self.w.stand_free(q)

    # -------------------------------------------------------------------------------------------- poses
    def _batch(self, name, times):
        """Vectorised poses of one actor at many times: list of {part: (pos, R)} (R6 aliases included)."""
        a = self.perf_actors[name]
        V = PO.pose_actor_frames({"clips": a["clips"], "arms": self.arms.get(name, 0.55)}, np.asarray(times, float))
        mats = {pn: (V[pn][0], quat_mats(V[pn][1])) for pn in V}
        out = []
        for k in range(len(times)):
            tg = {pn: (mats[pn][0][k], mats[pn][1][k]) for pn in mats}
            tp, tr = tg["Torso"]
            tg["LowerTorso"] = (tp + tr @ np.array([0, -0.8, 0]), tr)
            for leg, foot in (("Left Leg", "LeftFoot"), ("Right Leg", "RightFoot")):
                lp, lr = tg[leg]
                tg[foot] = (lp + lr @ np.array([0, -0.8, 0]), lr)
            out.append(tg)
        return out

    def _targets(self, name, t):
        a = self.perf_actors[name]
        parts = PO.Poser({name: {"clips": a["clips"], "arms": self.arms.get(name, 0.55)}}).pose(name, t)
        tp, tr = parts["Torso"]
        tg = {k: v for k, v in parts.items()}
        tg["LowerTorso"] = (tp + tr @ np.array([0, -0.8, 0]), tr)
        for leg, foot in (("Left Leg", "LeftFoot"), ("Right Leg", "RightFoot")):
            lp, lr = parts[leg]
            tg[foot] = (lp + lr @ np.array([0, -0.8, 0]), lr)
        return tg

    @staticmethod
    def _lowest(p, R, size):
        return float(p[1] - np.abs(R[1]) @ (np.asarray(size, float) / 2))

    def probe(self, name, times, opts):
        W = self.w
        ignore = set(opts.get("ignore") or [])
        seats = opts.get("seats") or {}

        def seat_part(i):
            for sname, top in seats.items():
                if top is not None and (W.name[i] == sname or ("." + sname + ".") in ("." + W.path[i] + ".")) and W.top[i] <= top + 0.2:
                    return True
            return False

        def ignored(i):
            return W.name[i] in ignore or W.parent[i] in ignore

        out = []
        for t, tg in zip(times, self._batch(name, times)):
            hips = tg["LowerTorso"][0]
            lf, rf = tg["LeftFoot"][0], tg["RightFoot"][0]
            f0, _ = W._down(hips[0], min(lf[1], rf[1]) + 0.5, hips[2], 60)
            floorY = f0 if f0 is not None else -1e3
            low, low_part, hits = math.inf, "", set()
            for pn in BODY6:
                p, R = tg[pn]
                size = np.asarray(PO.SIZES[pn], float)
                y = self._lowest(p, R, size)
                if y < low:
                    low, low_part = y, pn
                core = size * 0.8
                ids = W._near_parts(p, np.linalg.norm(core) / 2)
                if len(ids) == 0:
                    continue
                ok = (W.tr[ids] < 0.95) & W.cc[ids] & ~((W.top[ids] <= floorY + 0.25) & (W.h[ids, 1] * 2 < 4))
                ids = ids[ok]
                ids = np.array([i for i in ids if not ignored(i) and not seat_part(i)], int)
                if len(ids) == 0:
                    continue
                dep = W.obb_depth(p, R, core / 2, ids)
                for i, d in zip(ids, dep):
                    if (W.block[i] and d > MIN_DEPTH) or (not W.block[i] and d > 0):
                        hits.add(W.owner[i])
            foot = min(self._lowest(*tg["Left Leg"], PO.SIZES["Left Leg"]), self._lowest(*tg["Right Leg"], PO.SIZES["Right Leg"]))

            def ground(pos):
                g, pi = W._down(pos[0], pos[1] + 0.5, pos[2], 60, skip=lambda i: ignored(i) or seat_part(i))
                return (g, W.name[pi]) if g is not None else (-1e3, "")

            gl, gr = ground(lf)[0], ground(rf)[0]
            gH, gName = ground(np.array([hips[0], min(lf[1], rf[1]), hips[2]]))

            def hip_end(p, R, size):
                s = np.asarray(size, float) / 2
                return min(float((p + R @ np.array([sx * s[0], s[1] * 0.4, sz * s[2]]))[1]) for sx in (-1, 1) for sz in (-1, 1))

            thigh = min(self._lowest(*tg["Torso"], PO.SIZES["Torso"]), hip_end(*tg["Left Leg"], PO.SIZES["Left Leg"]),
                        hip_end(*tg["Right Leg"], PO.SIZES["Right Leg"]))
            lk = tg["Torso"][1] @ np.array([0, 0, -1.0])
            lk = np.array([lk[0], lk[2]]) / max(np.hypot(lk[0], lk[2]), 1e-6)
            out.append({"t": t, "hips": list(map(float, hips)), "look": list(map(float, lk)), "low": low, "lowPart": low_part,
                        "foot": foot, "gF": max(gl, gr), "gH": gH, "gName": gName, "hits": sorted(hits), "thigh": thigh})
        return out

    def bodycheck(self, times):
        W = self.w
        names = sorted(self.perf_actors)
        out = []
        allp = {n: self._batch(n, times) for n in names}
        # limbs inside set pieces: every (time, actor, limb) core box in one batched overlap query
        Q, meta = [], []
        for k in range(len(times)):
            for n in names:
                tg = allp[n][k]
                foot = min(float(tg[pn][0][1] - PO.SIZES[pn][1] / 2) for pn in BODY6)
                for pn in BODY6:
                    Q.append((tg[pn][0], tg[pn][1], np.asarray(PO.SIZES[pn], float) * 0.3))
                    meta.append((k, n, pn, foot))
        props_at = [dict() for _ in times]
        if Q:
            qi, pi, _ = W.overlaps(np.array([q[0] for q in Q]), np.array([q[1] for q in Q]), np.array([q[2] for q in Q]))
            for a_, b_ in zip(qi, pi):
                k, n, pn, foot = meta[a_]
                if W.tr[b_] < 0.9 and W.cq[b_] and W.top[b_] > foot + 0.45 and np.linalg.norm(W.h[b_] * 2) > 0.6 and n not in props_at[k]:
                    props_at[k][n] = f"{W.parent[b_]}.{W.name[b_]}<{pn}"
        # body-vs-body: per actor pair, every time they're within 12 studs, all 36 part pairs in one SAT call
        nt = len(times)
        C = {n: np.array([[allp[n][k][pn][0] for pn in BODY6] for k in range(nt)]) for n in names}      # (T,6,3)
        Rm = {n: np.array([[allp[n][k][pn][1] for pn in BODY6] for k in range(nt)]) for n in names}     # (T,6,3,3)
        LT = {n: np.array([allp[n][k]["LowerTorso"][0] for k in range(nt)]) for n in names}
        pairs_at = [dict() for _ in range(nt)]
        ii, jj = np.meshgrid(np.arange(6), np.arange(6), indexing="ij")
        ii, jj = ii.ravel(), jj.ravel()
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a_, b_ = names[i], names[j]
                ks = np.nonzero(np.linalg.norm(LT[a_] - LT[b_], axis=1) < 12)[0]
                if len(ks) == 0:
                    continue
                K = np.repeat(ks, 36)
                I, J = np.tile(ii, len(ks)), np.tile(jj, len(ks))
                dep = _sat(C[a_][K, I], Rm[a_][K, I], _HALF[I], C[b_][K, J], Rm[b_][K, J], _HALF[J]).reshape(len(ks), 36).max(1)
                for k, d in zip(ks, dep):
                    pairs_at[k][f"{a_}|{b_}"] = float(d)
        for k, t in enumerate(times):
            pair = pairs_at[k]
            prop = props_at[k]
            out.append({"t": t, "self": {n: 0 for n in names}, "selfWhere": {n: "" for n in names}, "pair": pair, "prop": prop})
        return out


def _obb_pair(a, sa, b, sb):
    (ca, Ra), (cb, Rb) = a, b
    ha, hb = np.asarray(sa, float) / 2, np.asarray(sb, float) / 2
    d = cb - ca
    best = math.inf
    axes = [Ra[:, i] for i in range(3)] + [Rb[:, i] for i in range(3)]
    for i in range(3):
        for j in range(3):
            c = np.cross(Ra[:, i], Rb[:, j])
            n = np.linalg.norm(c)
            if n > 1e-6:
                axes.append(c / n)
    for ax in axes:
        ra = ha @ np.abs(Ra.T @ ax)
        rb = hb @ np.abs(Rb.T @ ax)
        o = ra + rb - abs(d @ ax)
        if o <= 0:
            return 0.0
        best = min(best, o)
    return best


def quat_mats(q):
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
                     2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
                     2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], 1).reshape(-1, 3, 3)


_HALF = np.array([np.asarray(PO.SIZES[p], float) / 2 for p in BODY6])


def _pair_depth(A, B):
    """Deepest overlap between any body part of A and any of B (36 box pairs, vectorised SAT)."""
    ca = np.array([A[p][0] for p in BODY6]); Ra = np.array([A[p][1] for p in BODY6])
    cb = np.array([B[p][0] for p in BODY6]); Rb = np.array([B[p][1] for p in BODY6])
    i, j = np.meshgrid(np.arange(6), np.arange(6), indexing="ij")
    i, j = i.ravel(), j.ravel()
    RA, RB, ha, hb, d = Ra[i], Rb[j], _HALF[i], _HALF[j], cb[j] - ca[i]
    axes = [RA[:, :, k] for k in range(3)] + [RB[:, :, k] for k in range(3)]
    for k in range(3):
        for l in range(3):
            c = np.cross(RA[:, :, k], RB[:, :, l])
            n = np.linalg.norm(c, axis=1, keepdims=True)
            axes.append(np.where(n > 1e-6, c / np.maximum(n, 1e-9), 0))
    depth = np.full(36, np.inf)
    for ax in axes:
        ra = np.einsum("nk,nk->n", np.abs(np.einsum("nj,njk->nk", ax, RA)), ha)
        rb = np.einsum("nk,nk->n", np.abs(np.einsum("nj,njk->nk", ax, RB)), hb)
        o = ra + rb - np.abs(np.einsum("nj,nj->n", d, ax))
        valid = np.linalg.norm(ax, axis=1) > 1e-6
        depth = np.where(valid, np.minimum(depth, o), depth)
    return float(max(0.0, depth.max())) if np.all(np.isfinite(depth)) else 0.0


def _sat(ca, Ra, ha, cb, Rb, hb):
    """Penetration depth of box pairs (n,...) by the 15-axis separating-axis test, vectorised (0 when apart)."""
    d = cb - ca
    axes = [Ra[:, :, k] for k in range(3)] + [Rb[:, :, k] for k in range(3)]
    for k in range(3):
        for l in range(3):
            c = np.cross(Ra[:, :, k], Rb[:, :, l])
            nrm = np.linalg.norm(c, axis=1, keepdims=True)
            axes.append(np.where(nrm > 1e-6, c / np.maximum(nrm, 1e-9), 0))
    depth = np.full(len(ca), np.inf)
    for ax in axes:
        ra = np.einsum("nk,nk->n", np.abs(np.einsum("nj,njk->nk", ax, Ra)), ha)
        rb = np.einsum("nk,nk->n", np.abs(np.einsum("nj,njk->nk", ax, Rb)), hb)
        o = ra + rb - np.abs(np.einsum("nj,nj->n", d, ax))
        valid = np.linalg.norm(ax, axis=1) > 1e-6
        depth = np.where(valid, np.minimum(depth, o), depth)
    return np.maximum(depth, 0)
