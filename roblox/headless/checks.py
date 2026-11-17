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


class Checks:
    def __init__(self, scene_dir: Path, names: list[str], frames_npz: Path, fps: float):
        scene_dir = Path(scene_dir)
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
        vps = []
        for j, (pos, look, fov) in enumerate(cams):
            pos, look = np.asarray(pos, float), np.asarray(look, float)
            x, y = (j % COLS) * W, (j // COLS) * H
            self.ctx.viewport = (x, y, W, H)
            vp = RD.perspective(min(fov * WIDEN, 150), W / H, 0.05, 400) @ RD.look_at(pos, look)
            vps.append(vp)
            self.prog["vp"].write(vp.astype("f4").T.tobytes())
            self.prog["cam"].value = tuple(pos)
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
        idv = ids[:, :, 0].astype(int) + 256 * ids[:, :, 1].astype(int)
        dep = np.where(ids[:, :, 3] > 0, dep, np.inf)
        out_i = np.zeros((n, H, W), int)
        out_d = np.zeros((n, H, W), np.float32)
        for j in range(n):
            x, y = (j % COLS) * W, (j // COLS) * H
            out_i[j], out_d[j] = idv[y:y + H, x:x + W], dep[y:y + H, x:x + W]
        return out_i, out_d, vps

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
            for n, pos in enumerate(P):
                cand = np.nonzero(np.sum((self._box_c - pos) ** 2, 1) < (self._box_rad + r + 0.5) ** 2)[0]
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
    def camcheck(self, times, cams):
        runs = []
        for t in times:
            ids, dep, vps = self._render(t, [(c["pos"], c["look"], c.get("fov", 40)) for c in cams])
            nears = self.near_batch([c["pos"] for c in cams], cams[0].get("r", 0.6) if cams else 0.6, t)
            res = []
            for j, c in enumerate(cams):
                pos = np.asarray(c["pos"], float)
                subs = {}
                for s in c.get("subjects") or []:
                    if s not in self.names:
                        continue
                    ai = self.names.index(s)
                    own = {100 + 2 * ai, 101 + 2 * ai}
                    hp, hr = self.part_world(self.actor_index(s, "Head"), t)
                    tp, tr = self.part_world(self.actor_index(s, "Torso"), t)
                    nb = 0
                    for p in (hp, tp + tr @ np.array([0, 0.5, 0]), tp + tr @ np.array([0, -0.8, 0])):
                        nb += self._hit(ids[j], dep[j], vps[j], pos, p, own)
                    to = pos - hp
                    face = float((hr @ np.array([0, 0, -1.0])) @ (to / max(np.linalg.norm(to), 1e-6)))
                    hb = 0
                    for iy in (-1, 0, 1):
                        for ix in (-1, 0, 1):
                            fp = hp + hr @ np.array([ix * 0.4, iy * 0.35, -0.6])
                            hb += self._hit(ids[j], dep[j], vps[j], pos, fp, {101 + 2 * ai})
                    subs[s] = {"blocked": int(nb), "face": round(face, 2), "selfhit": round(hb / 9, 2)}
                fg = 0.0
                if c.get("look") is not None:
                    look = np.asarray(c["look"], float)
                    dist = float(np.linalg.norm(look - pos))
                    # the shot's own frame inside the widened render: its central 1/WIDEN-ish window, a 6x9 grid
                    th, thw = math.tan(math.radians(c.get("fov", 40)) / 2), math.tan(math.radians(min(c.get("fov", 40) * WIDEN, 150)) / 2)
                    k_ = th / thw
                    hits, n_ = 0, 0
                    for iy in range(9):
                        for ix in range(6):
                            u = ((ix + 0.5) / 6 * 2 - 1) * k_
                            v = ((iy + 0.5) / 9 * 2 - 1) * k_
                            x = int(min(W - 1, (u * 0.5 + 0.5) * W))
                            y = int(min(H - 1, (v * 0.5 + 0.5) * H))
                            n_ += 1
                            hits += bool(dep[j][y, x] < dist * 0.55)
                    fg = hits / n_
                res.append({"near": nears[j], "subjects": subs, "fg": round(fg, 3)})
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
                opn.append(clear)
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
