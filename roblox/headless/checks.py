"""Studio-free shot-planning checks (the roblox_record.BACKEND interface): what ShortDirector.camcheck & co. answered
with Studio raycasts, answered here with tiny GPU renders of our own geometry (object id + depth per pixel) and poses
from the Python director.

    import roblox_record as RR; RR.BACKEND = Checks(scene_dir, ep, perf_actors)

Ray semantics map onto the id/depth buffer: "is something between the camera and this point" = "is the first
surface at that pixel nearer than the point and not the point's own object"."""
from __future__ import annotations

import json
import math
from pathlib import Path

import moderngl
import numpy as np

import hlrender as RD
import pose as PO

W, H = 72, 128               # per-candidate buffer (9:16)
COLS = 8                     # candidates per atlas row
WIDEN = 1.6                  # render a wider fov than the shot so off-frame targets can still be tested

VS = """#version 330
in vec3 in_pos; in float in_id;
uniform mat4 vp;
flat out int v_id; out float v_d;
uniform vec3 cam;
void main(){ gl_Position = vp * vec4(in_pos, 1.0); v_id = int(in_id); v_d = distance(in_pos, cam); }"""
FS = """#version 330
flat in int v_id; in float v_d;
layout(location=0) out vec4 o_id; layout(location=1) out float o_d;
void main(){ o_id = vec4(float(v_id & 255) / 255.0, float((v_id >> 8) & 255) / 255.0, 0, 1); o_d = v_d; }"""

ID_WORLD = 1
BIN = 16                     # studs per geometry bin
REACH = range(-2, 3)         # bins drawn around the camera (+-40 studs)


def _view_proj(cams) -> np.ndarray:
    """RD.perspective(min(fov * WIDEN, 150), W / H, 0.05, 400) @ RD.look_at(pos, look) for every camera at once."""
    n = len(cams)
    E = np.array([c[0] for c in cams], "f8").reshape(n, 3)
    T = np.array([c[1] for c in cams], "f8").reshape(n, 3)
    fov = np.array([min(float(c[2]) * WIDEN, 150) for c in cams], "f8")
    f = T - E
    f /= np.linalg.norm(f, axis=1, keepdims=True)
    s = np.cross(f, np.array([0.0, 1.0, 0.0]))
    sn = np.linalg.norm(s, axis=1)
    s[sn < 1e-6] = [1.0, 0.0, 0.0]
    s /= np.linalg.norm(s, axis=1, keepdims=True)
    u = np.cross(s, f)
    V = np.zeros((n, 4, 4))
    V[:, 0, :3], V[:, 1, :3], V[:, 2, :3] = s, u, -f
    V[:, :3, 3] = -np.einsum("nij,nj->ni", V[:, :3, :3], E)
    V[:, 3, 3] = 1.0
    near, far = 0.05, 400.0
    F = 1 / np.tan(np.radians(fov) / 2)
    Pm = np.zeros((n, 4, 4))
    Pm[:, 0, 0], Pm[:, 1, 1] = F / (W / H), F
    Pm[:, 2, 2], Pm[:, 2, 3] = (far + near) / (near - far), 2 * far * near / (near - far)
    Pm[:, 3, 2] = -1.0
    return Pm @ V


class Checks:
    def __init__(self, scene_dir: Path, names: list[str], frames_npz: Path, fps: float):
        scene_dir = Path(scene_dir)
        self._scene_dir, self._frames = scene_dir, Path(frames_npz)
        self.R = RD.Renderer(scene_dir, w=64, h=64)       # reuses its scene loading (meshes, matrices, walls)
        self.ctx = self.R.ctx
        ctx = self.ctx
        self.prog = ctx.program(vertex_shader=VS, fragment_shader=FS)
        self.names = names
        fr = np.load(frames_npz)
        self.pose, self.fps = fr["pose"], float(fps)
        dyn = json.loads((scene_dir / "dynamic.json").read_text())
        self.dyn = dyn
        # static world triangles (walls the camera may see through are left out, as Studio's cutaway did)
        tris, self.static_boxes = [], []
        for g in self.R.static_groups:
            key = g["k"][0]
            if g["k"][4]:            # transparent / decals: don't block
                continue
            vbo, n, centre, msize = self.R.sc._mesh(key)
            P = np.frombuffer(vbo.read(), "f4").reshape(-1, 12)[:, :3].astype("f8")
            keep = ~g["wall"]
            for m in g["mats"][keep]:
                tris.append(P @ m[:, :3].T + m[:, 3])
            for m, pos in zip(g["mats"][keep], g["pos"][keep]):
                self.static_boxes.append(m)
        T = np.concatenate(tris).astype("f4") if tris else np.zeros((0, 3), "f4")
        self.static_tri = T
        cen = T.reshape(-1, 3, 3).mean(1)
        # 16-stud bins on x/z: only geometry near the camera can block it, so only that is drawn per check
        self.bins = {}
        key = np.floor(cen[:, [0, 2]] / BIN).astype(int)
        order = np.lexsort((key[:, 1], key[:, 0]))
        tri3 = T.reshape(-1, 9)[order]
        keys = key[order]
        cuts = np.nonzero(np.any(np.diff(keys, axis=0) != 0, axis=1))[0] + 1
        for a, b in zip(np.r_[0, cuts], np.r_[cuts, len(keys)]):
            k = tuple(keys[a])
            data = np.hstack([tri3[a:b].reshape(-1, 3), np.full(((b - a) * 3, 1), ID_WORLD, "f4")]).astype("f4")
            self.bins[k] = ctx.buffer(data.tobytes())
        self.static_boxes = np.array(self.static_boxes) if self.static_boxes else np.zeros((0, 3, 4))
        self.box_inv = np.linalg.inv(self.static_boxes[:, :, :3]) if len(self.static_boxes) else None
        # dynamic: per part its mesh triangles (object space) and an id: 100 + 2*actor (+1 head and accessories),
        # props 2
        self.part_tris, self.part_id = [], []
        actor_of = {}
        for n, a in dyn["actors"].items():
            for i in range(a["first"] - 1, a["last"]):
                actor_of[i] = n
        self.actor_parts = {n: [] for n in dyn["actors"]}
        for i, p in enumerate(dyn["parts"]):
            specs = [s for s, pi in zip(self.R.sc.dyn, self.R.sc.dyn_part) if pi == i and s["mode"] != 3]
            n = actor_of.get(i)
            pid = 2 if n is None else 100 + 2 * names.index(n) + (0 if p["name"] in PO.SIZES and p["name"] != "Head" else 1)
            for s in specs:
                vbo, cnt, centre, msize = self.R.sc._mesh(s["key"])
                P = np.frombuffer(vbo.read(), "f4").reshape(-1, 12)[:, :3].astype("f8")
                sc_ = s["scale"] * np.ones(3) if s["native"] else s["scale"] / msize
                self.part_tris.append((i, (P - centre) * sc_))
                self.part_id.append(pid)
            if n is not None:
                self.actor_parts[n].append(i)
        self.fbo = None
        self.dyn_cache = {}
        self.bin_vao = {}
        self.dyn_vao = {}
        self._pw = {}

    # ------------------------------------------------------------------------------------------------ poses
    def _frame(self, t):
        return int(min(max(round(t * self.fps), 0), len(self.pose) - 1))

    def part_world(self, i, t):
        k = (self._frame(t), i)
        c = self._pw.get(k)
        if c is None:
            p = self.pose[k[0], i]
            c = self._pw[k] = (p[:3].astype("f8"), PO.q2m(p[3:].astype("f8")))
            if len(self._pw) > 20000:
                self._pw.clear()
        return c

    def actor_index(self, name, part):
        a = self.dyn["actors"][name]
        for i in range(a["first"] - 1, a["last"]):
            if self.dyn["parts"][i]["name"] == part:
                return i
        return None

    def poses(self, q):
        out = []
        for name, t in q:
            if name not in self.dyn["actors"]:
                out.append(False)
                continue
            hp, hr = self.part_world(self.actor_index(name, "Head"), t)
            tp, tr = self.part_world(self.actor_index(name, "Torso"), t)
            lt = tp + tr @ np.array([0, -1 + 0.2, 0])
            look = hr @ np.array([0, 0, -1.0])
            l = np.array([look[0], 0, look[2]])
            if np.linalg.norm(l) < 0.3:
                l = tr @ np.array([0, 0, -1.0])
                l = np.array([l[0], 0, l[2]])
            feet = []
            for leg in ("Left Leg", "Right Leg"):
                lp, lr = self.part_world(self.actor_index(name, leg), t)
                feet.append((lp + lr @ np.array([0, -1 + 0.2, 0]))[1])
            out.append([*hp, *lt, l[0], l[2], min(feet) - 0.4])
        return out

    # ----------------------------------------------------------------------------------------- id/depth render
    def _dyn_buffer(self, t):
        k = self._frame(t)
        if k in self.dyn_cache:
            return self.dyn_cache[k]
        arrs = []
        for (i, P), pid in zip(self.part_tris, self.part_id):
            pos = self.pose[k, i]
            if pos[1] < -500:
                continue
            R = PO.q2m(pos[3:].astype("f8"))
            arrs.append(np.hstack([P @ R.T + pos[:3], np.full((len(P), 1), pid)]))
        data = np.concatenate(arrs).astype("f4") if arrs else np.zeros((3, 4), "f4")
        if len(self.dyn_cache) > 8:
            self.dyn_cache.pop(next(iter(self.dyn_cache))).release()
        self.dyn_cache[k] = self.ctx.buffer(data.tobytes())
        return self.dyn_cache[k]

    def _render(self, t, cams):
        """cams: [(pos, look, fov)] -> (ids (n,H,W) int, depth (n,H,W), vps)"""
        n = len(cams)
        rows = math.ceil(n / COLS)
        size = (COLS * W, rows * H)
        if self.fbo is None or self.fbo.size != size:
            self.fbo = self.ctx.framebuffer([self.ctx.renderbuffer(size, 4), self.ctx.renderbuffer(size, 1, dtype="f4")],
                                            self.ctx.depth_renderbuffer(size))
        self.fbo.use()
        self.fbo.clear(0, 0, 0, 0, depth=1.0)
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.disable(moderngl.CULL_FACE)
        dyn = self._dyn_buffer(t)
        vao_d = self.dyn_vao.get(id(dyn))
        if vao_d is None:
            vao_d = self.dyn_vao[id(dyn)] = self.ctx.vertex_array(self.prog, [(dyn, "3f 1f", "in_pos", "in_id")])
        vps = _view_proj(cams)
        u_vp, u_cam = self.prog["vp"], self.prog["cam"]
        for j, (pos, look, fov) in enumerate(cams):
            pos = np.asarray(pos, float)
            x, y = (j % COLS) * W, (j // COLS) * H
            self.ctx.viewport = (x, y, W, H)
            vp = vps[j]
            u_vp.write(vp.astype("f4").T.tobytes())
            u_cam.value = tuple(pos)
            bx, bz = int(math.floor(pos[0] / BIN)), int(math.floor(pos[2] / BIN))
            for dx in REACH:
                for dz in REACH:
                    v = self.bin_vao.get((bx + dx, bz + dz))
                    if v is None and (bx + dx, bz + dz) in self.bins:
                        v = self.bin_vao[(bx + dx, bz + dz)] = self.ctx.vertex_array(
                            self.prog, [(self.bins[(bx + dx, bz + dz)], "3f 1f", "in_pos", "in_id")])
                    if v is not None:
                        v.render()
            vao_d.render()
        ids = np.frombuffer(self.fbo.read(attachment=0, components=4), np.uint8).reshape(size[1], size[0], 4)
        dep = np.frombuffer(self.fbo.read(attachment=1, components=1, dtype="f4"), np.float32).reshape(size[1], size[0])
        idv = ids[:, :, 0].astype(np.int32) + 256 * ids[:, :, 1].astype(np.int32)
        dep = np.where(ids[:, :, 3] > 0, dep, np.float32(np.inf))
        out_i = idv.reshape(rows, H, COLS, W).transpose(0, 2, 1, 3).reshape(rows * COLS, H, W)[:n]
        out_d = dep.reshape(rows, H, COLS, W).transpose(0, 2, 1, 3).reshape(rows * COLS, H, W)[:n]
        return out_i, out_d, list(vps)

    @staticmethod
    def _px(vp, p):
        c = vp @ np.array([*p, 1.0])
        if c[3] <= 1e-6:
            return None
        u, v = c[0] / c[3], c[1] / c[3]
        if abs(u) > 1 or abs(v) > 1:
            return None
        return int(min(W - 1, (u * 0.5 + 0.5) * W)), int(min(H - 1, (v * 0.5 + 0.5) * H))

    def _hit(self, ids, dep, vp, cam, p, own: set) -> bool:
        """Is something other than `own` between the camera and point p?"""
        px = self._px(vp, p)
        if px is None:
            return False
        x, y = px
        i, d = ids[y, x], dep[y, x]
        dist = float(np.linalg.norm(np.asarray(p) - cam))
        return bool(np.isfinite(d) and d < dist - 0.25 and i not in own and i != 0)

    def _near(self, pos, r, t):
        return self.near_batch(np.asarray(pos, float)[None], r, t)[0]

    def near_batch(self, P, r, t):
        """Per camera position: the static parts it sits in (box + r; cut-away walls excluded) and the characters it
        is within 1 stud of."""
        P = np.asarray(P, float)
        out = [[] for _ in range(len(P))]
        if self.box_inv is not None:
            if not hasattr(self, "_box_c"):
                self._box_c = self.static_boxes[:, :, 3]
                self._box_rad = 0.5 * np.linalg.norm(self.static_boxes[:, :, :3], axis=(1, 2))
                self._box_sc = np.linalg.norm(self.static_boxes[:, :, :3], axis=1)
            if not hasattr(self, "_box_tree"):
                # small boxes through a KD-tree, the few big ones (floors, walls) brute force
                from scipy.spatial import cKDTree
                big = self._box_rad > 6.0
                self._box_big = np.nonzero(big)[0]
                self._box_small = np.nonzero(~big)[0]
                self._box_tree = cKDTree(self._box_c[self._box_small])
                self._box_rmax = float(self._box_rad[self._box_small].max()) if len(self._box_small) else 0.0
            thr = (self._box_rad + r + 0.5) ** 2
            smalls = self._box_tree.query_ball_point(P, self._box_rmax + r + 0.5 + 1e-3)
            for n, near_c in enumerate(smalls):
                pos = P[n]
                near_c = np.sort(np.concatenate([self._box_big, self._box_small[np.asarray(near_c, int)]]))
                cand = near_c[np.sum((self._box_c[near_c] - pos) ** 2, 1) < thr[near_c]]
                if len(cand):
                    loc = np.einsum("nij,nj->ni", self.box_inv[cand], pos[None, :] - self._box_c[cand])
                    inside = np.all(np.abs(loc) <= 0.5 + r / np.maximum(self._box_sc[cand], 1e-3), axis=1)
                    if inside.any():
                        out[n].append(f"world{int(cand[np.argmax(inside)])}")
        k = self._frame(t)
        A = self._actor_boxes(k)
        if A is not None:
            pos_k, rot_k, half_k, owner_k = A
            loc = np.einsum("kji,nkj->nki", rot_k, P[:, None, :] - pos_k[None])    # R^T (p - c)
            hit = np.all(np.abs(loc) <= half_k[None], axis=2)                       # (n, k)
            for n in np.nonzero(hit.any(1))[0]:
                out[n].append(owner_k[int(np.argmax(hit[n]))] + ".closeup")
        return out

    def _actor_boxes(self, k):
        if getattr(self, "_ab_k", None) == k:
            return self._ab
        idx = [i for n in self.names for i in self.actor_parts.get(n, []) if self.pose[k, i, 1] > -500]
        if not idx:
            self._ab_k, self._ab = k, None
            return None
        p = self.pose[k, idx]
        owner = {i: n for n in self.names for i in self.actor_parts.get(n, [])}
        rot = np.array([PO.q2m(q.astype("f8")) for q in p[:, 3:]])
        half = np.array([np.asarray(self.dyn["parts"][i]["size"], float) / 2 + 1.0 for i in idx])
        self._ab_k, self._ab = k, (p[:, :3].astype("f8"), rot, half, [owner[i] for i in idx])
        return self._ab

    # ------------------------------------------------------------------------------------------- the checks
    def _hits(self, ids, dep, vp, cam, P, own: set) -> np.ndarray:
        """_hit for many points at once: P (n, 3) -> bool (n,)."""
        P = np.asarray(P, float)
        c = np.hstack([P, np.ones((len(P), 1))]) @ vp.T
        w = c[:, 3]
        ok = w > 1e-6
        u = np.where(ok, c[:, 0] / np.where(ok, w, 1), 9)
        v = np.where(ok, c[:, 1] / np.where(ok, w, 1), 9)
        ok &= (np.abs(u) <= 1) & (np.abs(v) <= 1)
        x = np.minimum(W - 1, ((u * 0.5 + 0.5) * W).astype(int).clip(0, W - 1))
        y = np.minimum(H - 1, ((v * 0.5 + 0.5) * H).astype(int).clip(0, H - 1))
        i, d = ids[y, x], dep[y, x]
        dist = np.linalg.norm(P - cam, axis=1)
        own_m = np.isin(i, list(own)) if own else np.zeros(len(P), bool)
        return ok & np.isfinite(d) & (d < dist - 0.25) & ~own_m & (i != 0)

    _GRID = {}

    @classmethod
    def _grid(cls, fov):
        """The 6x9 sample grid of a shot's own frame inside the widened render (pixel x, y)."""
        k = round(float(fov), 3)
        g = cls._GRID.get(k)
        if g is None:
            th, thw = math.tan(math.radians(fov) / 2), math.tan(math.radians(min(fov * WIDEN, 150)) / 2)
            k_ = th / thw
            iy, ix = np.meshgrid(np.arange(9), np.arange(6), indexing="ij")
            u = ((ix + 0.5) / 6 * 2 - 1) * k_
            v = ((iy + 0.5) / 9 * 2 - 1) * k_
            g = cls._GRID[k] = (np.minimum(W - 1, ((u * 0.5 + 0.5) * W).astype(int)).ravel(),
                                np.minimum(H - 1, ((v * 0.5 + 0.5) * H).astype(int)).ravel())
        return g

    def camcheck(self, times, cams):
        """Per time and camera: static parts it sits in, per subject (blocked body points, facing, head self-hit) and
        the foreground fraction. Vectorised over every camera x subject (the planner sends ~100 candidates)."""
        runs = []
        HEAD_PTS = np.array([[ix * 0.4, iy * 0.35, -0.6] for iy in (-1, 0, 1) for ix in (-1, 0, 1)])
        n = len(cams)
        if not n:
            return [[] for _ in times]
        P = np.array([c["pos"] for c in cams], float)
        pairs = [(j, s, self.names.index(s)) for j, c in enumerate(cams) for s in (c.get("subjects") or []) if s in self.names]
        gx = np.zeros((n, 54), int)
        gy = np.zeros((n, 54), int)
        has_look = np.zeros(n, bool)
        dist_l = np.zeros(n)
        subj_m = np.zeros((n, len(self.names) + 1), bool)
        for j, c in enumerate(cams):
            gx[j], gy[j] = self._grid(c.get("fov", 40))
            if c.get("look") is not None:
                has_look[j] = True
                dist_l[j] = float(np.linalg.norm(np.asarray(c["look"], float) - P[j]))
            for s_ in c.get("subjects") or []:
                if s_ in self.names:
                    subj_m[j, self.names.index(s_)] = True
        jj = np.arange(n)[:, None]
        for t in times:
            ids, dep, vps = self._render(t, [(c["pos"], c["look"], c.get("fov", 40)) for c in cams])
            VP = np.array(vps)
            nears = self.near_batch(P, cams[0].get("r", 0.6), t)
            subs = [dict() for _ in range(n)]
            if pairs:
                geo = {}
                for _j, s, _ai in pairs:
                    if s not in geo:
                        hp, hr = self.part_world(self.actor_index(s, "Head"), t)
                        tp, tr = self.part_world(self.actor_index(s, "Torso"), t)
                        geo[s] = (hp, hr, np.vstack([[hp, tp + tr @ np.array([0, 0.5, 0]), tp + tr @ np.array([0, -0.8, 0])],
                                                     hp + HEAD_PTS @ hr.T]))
                J = np.array([j for j, _s, _a in pairs])
                AI = np.array([a for _j, _s, a in pairs])
                Q = np.array([geo[s][2] for _j, s, _a in pairs])                        # (m, 12, 3)
                c4 = np.einsum("mij,mpj->mpi", VP[J], np.concatenate([Q, np.ones(Q.shape[:2] + (1,))], 2))
                w = c4[..., 3]
                ok = w > 1e-6
                ws = np.where(ok, w, 1.0)
                u, v = np.where(ok, c4[..., 0] / ws, 9), np.where(ok, c4[..., 1] / ws, 9)
                ok &= (np.abs(u) <= 1) & (np.abs(v) <= 1)
                x = ((u * 0.5 + 0.5) * W).astype(int).clip(0, W - 1)
                y = ((v * 0.5 + 0.5) * H).astype(int).clip(0, H - 1)
                i_ = ids[J[:, None], y, x]
                d_ = dep[J[:, None], y, x]
                dist = np.linalg.norm(Q - P[J][:, None, :], axis=2)
                base = ok & np.isfinite(d_) & (d_ < dist - 0.25) & (i_ != 0)
                own_h = (i_ == (101 + 2 * AI)[:, None])
                own_b = own_h | (i_ == (100 + 2 * AI)[:, None])
                nb = (base[:, :3] & ~own_b[:, :3]).sum(1)
                hb = (base[:, 3:] & ~own_h[:, 3:]).sum(1)
                for k, (j, s, _a) in enumerate(pairs):
                    hp, hr, _q = geo[s]
                    to = P[j] - hp
                    face = float((hr @ np.array([0, 0, -1.0])) @ (to / max(np.linalg.norm(to), 1e-6)))
                    subs[j][s] = {"blocked": int(nb[k]), "face": round(face, 2), "selfhit": round(int(hb[k]) / 9, 2)}
            d_ = dep[jj, gy, gx]
            i_ = ids[jj, gy, gx]
            hits = np.sum(d_ < dist_l[:, None] * 0.55, 1)
            body_i = np.clip((i_ - 100) // 2, 0, len(self.names))
            isb = (i_ >= 100) & (i_ < 200) & ~subj_m[jj, body_i] & (d_ < dist_l[:, None] * 0.9)
            body = isb.sum(1)
            res = []
            for j in range(n):
                fg = 0.0
                if has_look[j]:
                    # foreground: a wall right in front of the lens, or a body that isn't one of this shot's subjects
                    # (the critic's "an arm fills the frame"); a hug partner is fine, a body wall isn't
                    fg = max(hits[j] / 54, min(1.0, 1.6 * max(0.0, body[j] / 54 - 0.15)))
                res.append({"near": nears[j], "subjects": subs[j], "fg": round(float(fg), 3)})
            runs.append(res)
        return runs

    def prop_boxes(self, q):
        out = []
        for name, t, fill in q:
            idx = [i for i, p in enumerate(self.dyn["parts"]) if p.get("owner") == "prop:" + name]
            if not idx:
                out.append(False)
                continue
            k = self._frame(t)
            pts = []
            R0 = None
            for i in idx:
                p = self.pose[k, i]
                if p[1] < -500:            # hidden now: its home (the director parks it 2000 studs down)
                    p = p.copy()
                    p[1] += 2000
                R = PO.q2m(p[3:].astype("f8"))
                R0 = R if R0 is None else R0
                h = np.asarray(self.dyn["parts"][i]["size"], float) / 2
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        for sz in (-1, 1):
                            pts.append(p[:3] + R @ (h * np.array([sx, sy, sz])))
            pts = np.array(pts)
            lo, hi = pts.min(0), pts.max(0)
            cen, size = (lo + hi) / 2, hi - lo
            lv = R0 @ np.array([0, 0, -1.0])
            fov = math.radians(40)
            sz = max(size[1], 0.6 * max(size[0], size[2]), 0.5)
            dist = max(1.6, sz / fill / (2 * math.tan(fov / 2)))
            cams = []
            for kk in range(12):
                a = math.radians(kk * 30)
                d = np.array([lv[0] * math.cos(a) + lv[2] * math.sin(a), 0, lv[2] * math.cos(a) - lv[0] * math.sin(a)])
                cams.append((cen + d * dist + np.array([0, max(0.18 * dist, size[1] * 0.3), 0]), cen, 40.0))
            ids, dep, vps = self._render(t, cams)
            opn = []
            for kk, (cp, _, _) in enumerate(cams):
                clear = 0
                for off in (np.zeros(3), np.array([0, size[1] * 0.4, 0]), np.array([0, -size[1] * 0.25, 0])):
                    clear += not self._hit(ids[kk], dep[kk], vps[kk], cp, cen + off, {2})
                if self._near(cp, 0.4, t):
                    clear = 0
                # an insert of a held prop must not be a frame full of the holder's arm and torso
                win = ids[kk][H // 2 - H // 4:H // 2 + H // 4, W // 2 - W // 4:W // 2 + W // 4]
                body = float(np.mean((win >= 100) & (win < 200)))
                clear -= 2 if body > 0.6 else 1 if body > 0.35 else 0
                opn.append(max(clear, 0))
            out.append([*cen, *size, lv[0], lv[2], opn])
        return out

    def explicit(self, q):
        out = []
        for t, px, py, pz, lx, ly, lz, fov in q:
            pos, look = np.array([px, py, pz], float), np.array([lx, ly, lz], float)

            def facing(p):
                f = (look - p) / np.linalg.norm(look - p)
                s_, w_ = 0.0, 0.0
                for n in self.names:
                    hp, hr = self.part_world(self.actor_index(n, "Head"), t)
                    to = hp - p
                    d = np.linalg.norm(to)
                    if d < 45 and (to / d) @ f > math.cos(math.radians(fov * 0.45)):
                        w = 1 / max(d, 3) ** 2
                        s_ += w * float((hr @ np.array([0, 0, -1.0])) @ (-to / d))
                        w_ += w
                return (s_ / w_ if w_ else None), (1 if w_ else 0)

            base, n0 = facing(pos)
            best = False
            if base is not None and base < 0.25:
                off = pos - look
                cand = []
                for deg in (180, 150, -150, 120, -120, 90, -90):
                    p = look + PO.yaw_mat(math.radians(deg)) @ off
                    cand.append((deg, p))
                ids, dep, vps = self._render(t, [(p, look, fov) for _, p in cand])
                bestv = base + 0.3
                for j, (deg, p) in enumerate(cand):
                    v, m = facing(p)
                    blocked = self._hit(ids[j], dep[j], vps[j], p, look + (p - look) * 0.1, set(range(100, 200)))
                    if v is not None and m >= n0 and v > bestv and not blocked and not self._near(p, 0.5, t):
                        bestv, best = v, [*p, deg, v]
            out.append(best)
        return out

    # ------------------------------------------------------------------------------------- image QA support
    def portrait(self, pos, look, fov, t):
        """The shot's actual picture at 270x480 (our renderer, this instant's poses and faces)."""
        from PIL import Image
        if not hasattr(self, "_qa"):
            self._qa = RD.Renderer(self._scene_dir, w=270, h=480)
            self._qa_order = self.dyn.get("order", [])
            self._qa_faces = np.load(self._frames)["face"]
        k = self._frame(t)
        img = self._qa.frame(np.asarray(pos, float), np.asarray(look, float), float(fov),
                             RD.dyn_draws(self._qa, self.pose[k], self._qa_faces[k], self._qa_order))
        return Image.frombytes("RGB", (270, 480), img).transpose(Image.FLIP_TOP_BOTTOM)

    def camcheck_full(self, t, cam):
        """One camera's check with the subject's head / hips / feet (image QA frames the head)."""
        r = self.camcheck([t], [cam])[0][0]
        for s, v in r["subjects"].items():
            hp, _ = self.part_world(self.actor_index(s, "Head"), t)
            tp, tr = self.part_world(self.actor_index(s, "Torso"), t)
            v.update(head=list(map(float, hp)), hips=list(map(float, tp + tr @ np.array([0, -0.8, 0]))))
        return r

    def hips(self, t):
        out = {}
        for n in self.names:
            tp, tr = self.part_world(self.actor_index(n, "Torso"), t)
            out[n] = list(map(float, tp + tr @ np.array([0, -0.8, 0])))
        return out
