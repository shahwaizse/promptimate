"""Headless renderer for exported Roblox scenes (export.py): moderngl (OpenGL 3.3, no window; EGL on Linux) drawing
straight into ffmpeg. Every frame is rendered, nothing is skipped, and it runs faster than real time.

Look: bright, evenly lit, colourful (no vignette, grain or glare): sun with a soft shadow map that follows the
camera, sky/ground ambient, a little specular. Parts are instanced per (mesh, texture). Meshes come from Studio's
local asset cache (meshcache.py), textures from bake.py (shown in Studio once, screen-grabbed, cached by id).
Classic clothing maps the 585x559 shirt/pants template onto the R6 boxes; faces are projected onto the head front."""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import moderngl
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import meshcache as MC  # noqa: E402

MESHES = MC.OUT
TEXDIR = MC.OUT.parent / "tex"
MATDIR = MC.OUT.parent / "mat"
# the look: sun colour/strength, sky and ground ambient (hemispheric), exposure. LIGHT_OVERRIDE is for A/B tests
# 2026-11-17 critic: our sets read flat and evenly lit next to the references (raking sun, real shade): a stronger,
# warmer sun and less fill, kept mild enough that a face in shade still reads
LIGHT = {"sun": (1.6, 1.5, 1.32), "sky": (0.32, 0.36, 0.45), "ground": (0.19, 0.17, 0.16), "exp": 1.0}
LIGHT_OVERRIDE = None
MAT_NAMES = {p.stem for p in MATDIR.glob("*.png")} if MATDIR.exists() else set()
MAT_TILE = {"Brick": 8.0, "WoodPlanks": 8.0, "Cobblestone": 8.0, "DiamondPlate": 4.0, "Fabric": 2.0, "Grass": 6.0}
R6_PARTS = {"Torso": "r6:torso", "Right Arm": "r6:rlimb", "Right Leg": "r6:rlimb", "Left Arm": "r6:llimb",
            "Left Leg": "r6:llimb"}
# classic clothing template rects (x, y, w, h) on 585x559 per box face, in _box() face order (+X -X +Y -Y +Z -Z)
TEMPLATE = {
    "r6:torso": [(165, 74, 64, 128), (361, 74, 64, 128), (231, 8, 128, 64), (231, 204, 128, 64), (427, 74, 128, 128),
                 (231, 74, 128, 128)],
    "r6:rlimb": [(151, 355, 64, 128), (19, 355, 64, 128), (217, 289, 64, 64), (217, 485, 64, 64), (85, 355, 64, 128),
                 (217, 355, 64, 128)],
    "r6:llimb": [(506, 355, 64, 128), (374, 355, 64, 128), (308, 289, 64, 64), (308, 485, 64, 64), (440, 355, 64, 128),
                 (308, 355, 64, 128)],
}


# --------------------------------------------------------------------------------------------- primitive meshes
# box faces: (normal, u axis = viewer's right, v axis = up) seen from outside; texture v grows downward
BOX_FACES = [((1, 0, 0), (0, 0, -1), (0, 1, 0)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)), ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
             ((0, -1, 0), (-1, 0, 0), (0, 0, -1)), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (-1, 0, 0), (0, 1, 0))]


def _box(rects=None):
    P, N, U = [], [], []
    for fi, (n, u, v) in enumerate(BOX_FACES):
        n, u, v = map(np.array, (n, u, v))
        c = n * 0.5
        quad = [c - u * .5 - v * .5, c + u * .5 - v * .5, c + u * .5 + v * .5, c - u * .5 + v * .5]
        uvs = [(0, 1), (1, 1), (1, 0), (0, 0)]
        if rects:
            x, y, w, h = rects[fi]
            uvs = [((x + a * w) / 585, (y + b * h) / 559) for a, b in uvs]
        for i in (0, 1, 2, 0, 2, 3):
            P.append(quad[i]); N.append(n); U.append(uvs[i])
    return np.array(P, "f4"), np.array(N, "f4"), np.array(U, "f4")


def _quad():
    """A decal: unit square in the XY plane facing -Z (texture up = +Y, right = -X as seen from the front)."""
    P = np.array([[.5, -.5, 0], [-.5, -.5, 0], [-.5, .5, 0], [.5, -.5, 0], [-.5, .5, 0], [.5, .5, 0]], "f4")
    U = np.array([[0, 1], [1, 1], [1, 0], [0, 1], [1, 0], [0, 0]], "f4")
    return P, np.tile(np.array([0, 0, -1], "f4"), (6, 1)), U


def _sphere(seg=24, rings=16):
    P, N = [], []
    for i in range(rings):
        for j in range(seg):
            def pt(a, b):
                th, ph = math.pi * a / rings, 2 * math.pi * b / seg
                return np.array([math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)])
            q = [pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j + 1)]
            for k in (0, 1, 2, 0, 2, 3):
                P.append(q[k] * 0.5); N.append(q[k])
    P = np.array(P, "f4")
    return P, np.array(N, "f4"), np.zeros((len(P), 2), "f4")


def _cylinder(seg=28, axis=0, round_=0.0):
    """Roblox cylinders run along the part's X axis; axis=1 runs along Y (the classic head, with rounded rims)."""
    P, N = [], []
    rings = [(-.5, 0.5, 0.0), (.5, 0.5, 0.0)]
    if round_:
        k = 6
        rings = []
        for i in range(k + 1):         # bottom rim -> top rim, quarter circles of radius round_
            a = -math.pi / 2 + math.pi / 2 * i / k
            rings.append((-.5 + round_ + round_ * math.sin(a), .5 - round_ + round_ * math.cos(a), math.sin(a)))
        for i in range(k + 1):
            a = math.pi / 2 * i / k
            rings.append((.5 - round_ + round_ * math.sin(a), .5 - round_ + round_ * math.cos(a), math.sin(a)))
    for j in range(seg):
        a0, a1 = 2 * math.pi * j / seg, 2 * math.pi * (j + 1) / seg
        for (x0, r0, s0), (x1, r1, s1) in zip(rings, rings[1:]):
            q = [(x0, r0 * math.cos(a0), r0 * math.sin(a0)), (x1, r1 * math.cos(a0), r1 * math.sin(a0)),
                 (x1, r1 * math.cos(a1), r1 * math.sin(a1)), (x0, r0 * math.cos(a1), r0 * math.sin(a1))]
            c0, c1 = math.sqrt(max(0, 1 - s0 * s0)), math.sqrt(max(0, 1 - s1 * s1))
            ns = [(s0, c0 * math.cos(a0), c0 * math.sin(a0)), (s1, c1 * math.cos(a0), c1 * math.sin(a0)),
                  (s1, c1 * math.cos(a1), c1 * math.sin(a1)), (s0, c0 * math.cos(a1), c0 * math.sin(a1))]
            for k2 in (0, 1, 2, 0, 2, 3):
                P.append(q[k2]); N.append(ns[k2])
        for x, sgn, r in ((rings[-1][0], 1, rings[-1][1]), (rings[0][0], -1, rings[0][1])):
            c0, s0, c1, s1 = r * math.cos(a0), r * math.sin(a0), r * math.cos(a1), r * math.sin(a1)
            tri = [(x, 0, 0), (x, c0, s0), (x, c1, s1)] if sgn > 0 else [(x, 0, 0), (x, c1, s1), (x, c0, s0)]
            for v in tri:
                P.append(v); N.append((sgn, 0, 0))
    P, N = np.array(P, "f4"), np.array(N, "f4")
    if axis == 1:
        P, N = P[:, [1, 0, 2]], N[:, [1, 0, 2]]
    return P, N, np.zeros((len(P), 2), "f4")


def _wedge():
    v = np.array([[-.5, -.5, -.5], [.5, -.5, -.5], [.5, -.5, .5], [-.5, -.5, .5], [-.5, .5, .5], [.5, .5, .5]], "f4")
    tris = [(0, 2, 1), (0, 3, 2), (3, 4, 5), (3, 5, 2), (0, 1, 5), (0, 5, 4), (0, 4, 3), (1, 2, 5)]
    P = v[np.array(tris).ravel()]
    tri = P.reshape(-1, 3, 3)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    return P, np.repeat(n, 3, axis=0).astype("f4"), np.zeros((len(P), 2), "f4")


def _head():
    P, N, U = _cylinder(32, axis=1, round_=0.18)
    return P * np.array([1.0, 0.95, 1.0], "f4"), N, U


PRIMS = {"box": _box, "ball": _sphere, "cyl": _cylinder, "wedge": _wedge, "cwedge": _wedge, "head": _head,
         "quad": _quad, **{k: (lambda r=r: _box(r)) for k, r in TEMPLATE.items()}}

# --------------------------------------------------------------------------------------------------- shaders
VS = """#version 330
in vec3 in_pos; in vec3 in_nrm; in vec2 in_uv; in vec4 in_vcol;
in vec4 i_m0; in vec4 i_m1; in vec4 i_m2; in vec4 i_col; in vec4 i_uvp;
uniform mat4 vp; uniform mat4 light_vp; uniform float use_vcol;
out vec3 v_nrm; out vec4 v_col; out vec4 v_lpos; out vec3 v_wpos; out vec2 v_uv; out vec3 v_opos;
void main(){
  mat4 m = transpose(mat4(i_m0, i_m1, i_m2, vec4(0,0,0,1)));
  vec4 w = m * vec4(in_pos, 1.0);
  v_wpos = w.xyz;
  v_opos = in_pos;
  v_nrm = normalize(transpose(inverse(mat3(m))) * in_nrm);
  v_col = mix(i_col, vec4(in_vcol.rgb, i_col.a), use_vcol);
  v_uv = in_uv * i_uvp.xy;
  v_lpos = light_vp * w;
  gl_Position = vp * w;
}"""
FS = """#version 330
in vec3 v_nrm; in vec4 v_col; in vec4 v_lpos; in vec3 v_wpos; in vec2 v_uv; in vec3 v_opos;
uniform sampler2DShadow shadow; uniform sampler2D tex; uniform int mode; uniform sampler2D mat; uniform float mat_on; uniform float mat_tile;
uniform vec3 sun; uniform vec3 sun_col; uniform vec3 sky; uniform vec3 ground; uniform vec3 cam; uniform float exposure;
out vec4 f;
void main(){
  vec4 base = v_col;
  if (mode == 1) {                      // texture over the part colour (MeshPart/FileMesh textures, clothing)
    vec4 t = texture(tex, v_uv);
    base.rgb = mix(base.rgb, t.rgb, t.a);
  } else if (mode == 2) {               // the face drawing on the head's front
    vec2 uv = vec2(0.5 - v_opos.x / 0.92, 0.5 - v_opos.y / 0.92);
    if (v_opos.z < 0.0 && uv.x > 0.0 && uv.x < 1.0 && uv.y > 0.0 && uv.y < 1.0) {
      vec4 t = texture(tex, uv);
      base.rgb = mix(base.rgb, t.rgb, t.a);
    }
  } else if (mode == 3) {               // decal: texture tinted by its colour, its own alpha
    vec4 t = texture(tex, v_uv);
    base = vec4(t.rgb * v_col.rgb, t.a * v_col.a);
    if (base.a < 0.01) discard;
  }
  base.rgb = pow(max(base.rgb, 0.0), vec3(2.2));      // colours and textures are sRGB: light in linear space
  vec3 n = normalize(v_nrm);
  if (!gl_FrontFacing) n = -n;
  if (mat_on > 0.5 && mode != 3) {      // our procedural material, triplanar in world studs
    vec3 w = pow(abs(n), vec3(4.0)); w /= (w.x + w.y + w.z);
    vec3 q = v_wpos / mat_tile;
    vec3 dm = texture(mat, q.zy).rgb * w.x + texture(mat, q.xz).rgb * w.y + texture(mat, q.xy).rgb * w.z;
    base.rgb *= dm * 2.0;
  }
  vec3 p = v_lpos.xyz / v_lpos.w * 0.5 + 0.5;
  float sh = 0.0;
  vec2 ts = 1.0 / vec2(textureSize(shadow, 0));
  for (int x = -1; x <= 1; x++) for (int y = -1; y <= 1; y++)
    sh += texture(shadow, vec3(p.xy + vec2(x, y) * ts * 1.5, p.z - 0.0015));
  sh /= 9.0;
  if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) sh = 1.0;
  float d = max(dot(n, sun), 0.0);
  vec3 amb = mix(ground, sky, n.y * 0.5 + 0.5);
  vec3 v = normalize(cam - v_wpos);
  float spec = pow(max(dot(reflect(-sun, n), v), 0.0), 24.0) * 0.05;
  vec3 c = base.rgb * (amb + sun_col * d * sh) + spec * sh;
  c *= exposure;
  c = c / (1.0 + c * 0.05);
  float lum = dot(c, vec3(0.299, 0.587, 0.114));
  c = max(mix(vec3(lum), c, 1.18), 0.0);           // a little extra colour
  f = vec4(pow(c, vec3(1.0 / 2.2)), base.a);
}"""
SVS = """#version 330
in vec3 in_pos; in vec4 i_m0; in vec4 i_m1; in vec4 i_m2;
uniform mat4 light_vp;
void main(){ mat4 m = transpose(mat4(i_m0, i_m1, i_m2, vec4(0,0,0,1))); gl_Position = light_vp * m * vec4(in_pos, 1.0); }"""
SFS = """#version 330
void main(){}"""
SKY_VS = """#version 330
in vec2 p; out vec2 uv; void main(){ uv = p; gl_Position = vec4(p, 0.9999, 1.0); }"""
SKY_FS = """#version 330
in vec2 uv; uniform vec3 top; uniform vec3 horizon; out vec4 f;
void main(){ float t = clamp(uv.y * 0.5 + 0.5, 0.0, 1.0); f = vec4(mix(horizon, top, pow(t, 0.8)), 1.0); }"""


# ---------------------------------------------------------------------------------------------------- maths
def look_at(eye, target, up=(0, 1, 0)):
    eye, target, up = map(lambda a: np.asarray(a, "f8"), (eye, target, up))
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    if np.linalg.norm(s) < 1e-6:
        s = np.array([1.0, 0, 0])
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def perspective(fovy_deg, aspect, near=0.1, far=1200.0):
    f = 1 / math.tan(math.radians(fovy_deg) / 2)
    m = np.zeros((4, 4))
    m[0, 0], m[1, 1] = f / aspect, f
    m[2, 2], m[2, 3] = (far + near) / (near - far), 2 * far * near / (near - far)
    m[3, 2] = -1
    return m


def ortho(l, r, b, t, n, f):
    m = np.eye(4)
    m[0, 0], m[1, 1], m[2, 2] = 2 / (r - l), 2 / (t - b), -2 / (f - n)
    m[0, 3], m[1, 3], m[2, 3] = -(r + l) / (r - l), -(t + b) / (t - b), -(f + n) / (f - n)
    return m


def quat_mat(q):
    x, y, z, w = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    return np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
                     2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
                     2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], 1).reshape(-1, 3, 3)


def _asset(s: str | None) -> str | None:
    if not s:
        return None
    if s.startswith("file:"):           # our own generated textures (own_assets.py)
        return s[5:] if Path(s[5:]).exists() else None
    m = re.search(r"(\d{4,})", s)
    if not m:
        return None
    p = TEXDIR / f"{m.group(1)}.png"
    return str(p) if p.exists() else None


# ----------------------------------------------------------------------------------------------- the scene
class Scene:
    def __init__(self, ctx, static: dict, dyn: dict | None, index: dict):
        self.ctx = ctx
        self.index = index
        self.meshes = {}
        self.missing = 0
        self.light = static.get("light", {})
        self.static = [s for p in static["parts"] for s in self._specs(p)]
        self.dyn = []
        self.dyn_part = []          # dynamic spec -> index of its part in the pose array
        self.dyn_actor = []         # actor name or None (head specs pick the actor's face per frame)
        actor_of = {}
        for name, a in (dyn or {}).get("actors", {}).items():
            for i in range(a["first"] - 1, a["last"]):
                actor_of[i] = name
        self.skins = self._skins(dyn) if dyn else {}
        for i, p in enumerate((dyn or {}).get("parts", [])):
            for s in self._specs(p, actor=actor_of.get(i)):
                self.dyn.append(s)
                self.dyn_part.append(i)
                self.dyn_actor.append(actor_of.get(i))

    def _skins(self, dyn) -> dict:
        """Per actor and body part: body colour + pants + shirt composited on the clothing template."""
        out = {}
        cols = {}
        for i, p in enumerate(dyn["parts"]):
            cols.setdefault(p.get("owner"), {})[p["name"]] = p["color"]
        for name, a in dyn["actors"].items():
            shirt, pants = _asset(a.get("shirt")), _asset(a.get("pants"))
            if not shirt and not pants:
                continue
            S = Image.open(shirt).convert("RGBA").resize((585, 559)) if shirt else None
            Pn = Image.open(pants).convert("RGBA").resize((585, 559)) if pants else None
            for part in R6_PARTS:
                c = cols.get(name, {}).get(part)
                if c is None:
                    continue
                im = Image.new("RGBA", (585, 559), tuple(int(v * 255) for v in c) + (255,))
                layers = [Pn, S] if part == "Torso" else ([S] if "Arm" in part else [Pn])
                for L in layers:
                    if L is not None:
                        im.alpha_composite(L)
                key = f"skin:{name}:{part}"
                out[(name, part)] = key
                self._tex_images[key] = im
        return out

    _tex_images: dict = {}

    def _mesh(self, key):
        if key in self.meshes:
            return self.meshes[key]
        if key in PRIMS:
            P, N, U = PRIMS[key]()
            V = np.ones((len(P), 4), "f4")
            centre, size = np.zeros(3), np.ones(3)
        else:
            z = np.load(MESHES / f"{key}.npz")
            idx = z["faces"].ravel()
            P, N, U = z["pos"][idx], z["nrm"][idx], z["uv"][idx]
            V = (z["rgba"][idx].astype("f4") / 255) if "rgba" in z.files else np.ones((len(P), 4), "f4")
            lo, hi = z["lo"], z["hi"]
            centre, size = (lo + hi) / 2, np.maximum(hi - lo, 1e-4)
        data = np.hstack([P, N, U, V]).astype("f4")
        self.meshes[key] = (self.ctx.buffer(data.tobytes()), len(P), centre, size)
        return self.meshes[key]

    def _specs(self, p, actor=None):
        """Draw specs for one exported part: the part itself, plus one quad per decal."""
        kind = p["kind"]
        size = np.array(p["size"], "f8")
        mesh = p.get("mesh") or {}
        key, scale, vcol, tex, mode = kind, size, 0.0, None, 0
        native = False          # FileMesh: rendered at mesh size x Scale, not at the part's size
        sp = mesh.get("special")
        if mesh.get("key"):             # our own meshes (own_assets.py): referenced directly, colours baked per vertex
            key, vcol = mesh["key"], 1.0 if mesh.get("vcol") else 0.0
        elif actor and p["name"] in R6_PARTS and (actor, p["name"]) in self.skins:
            key, tex, mode = R6_PARTS[p["name"]], self.skins[(actor, p["name"])], 1
        elif sp and sp["type"] == "Head":
            key, scale = "head", np.array(sp["scale"]) * 0.96
            if actor:
                mode = 2
        elif sp and sp["type"] == "Sphere":
            key = "ball"
        elif sp and sp["type"] == "Cylinder":
            key = "cyl"
        elif sp and sp["type"] == "FileMesh":
            sc = np.maximum(np.abs(np.array(sp["scale"])), 1e-3)
            hits = MC.match(sp["meshSize"], self.index) if sp.get("meshSize") else MC.match(size / sc, self.index, tol=0.06)
            if hits:
                key, scale, native = hits[0], sc, True
                tex = _asset(sp.get("tex"))
                mode = 1 if tex else 0
            else:
                self.missing += 1
                key = "box"
        elif kind in ("mesh", "union") and mesh.get("size"):
            hits = MC.match(mesh["size"], self.index)
            if hits:
                key = hits[0]
                vcol = 1.0 if kind == "union" and not mesh.get("partColor", True) else 0.0
                if kind == "mesh":
                    tex = _asset(mesh.get("tex"))
                    mode = 1 if tex else 0
            else:
                self.missing += 1
                key = "box"
        elif kind in ("mesh", "union"):
            self.missing += 1
            key = "box"
        col = list(p["color"]) + [1.0 - float(p.get("tr", 0))]
        if p.get("mat") == "Neon":
            col = [min(1, c * 1.6) for c in col[:3]] + [col[3]]
        if p.get("mat") == "Glass":
            col[3] = min(col[3], 0.35)
        cf = p.get("cf")
        if key == "box" and kind in ("mesh", "union", "box") and (sp or {}).get("type") == "FileMesh" and actor is not None:
            return []           # an accessory we have no mesh for: nothing beats a grey box on a head
        matname = p.get("mat") if p.get("mat") in MAT_NAMES and mode in (0, 1) and not tex else None
        out = [{"key": key, "scale": scale, "native": native, "col": col, "vcol": vcol, "tex": tex, "mode": mode, "mat": matname,
                "uvp": (1.0, 1.0), "cf": cf, "pos": np.array(cf[:3]) if cf else None, "local": None,
                "wall": self._wall(p), "cast": p.get("cast", True) is not False}]
        for dc in p.get("decals") or []:
            t = _asset(dc.get("tex"))
            if not t:
                continue
            fi = ["Right", "Left", "Top", "Bottom", "Back", "Front"].index(dc["face"]) if dc["face"] in \
                ("Right", "Left", "Top", "Bottom", "Back", "Front") else 5
            n, u, v = (np.array(a, "f8") for a in BOX_FACES[fi])
            # local frame of the decal quad: its -Z is the face normal (quad faces -Z), X = -u, Y = v
            R = np.stack([-u, v, -n], 1)
            w_, h_ = abs(u @ size), abs(v @ size)
            off = n * (abs(n @ size) / 2 + 0.01)
            uvp = (1.0, 1.0)
            if dc.get("tile"):
                uvp = (w_ / max(dc["tile"][0], 1e-3), h_ / max(dc["tile"][1], 1e-3))
            out.append({"key": "quad", "scale": np.array([w_, h_, 1.0]), "native": False,
                        "col": list(dc.get("color", (1, 1, 1))) + [1.0 - float(dc.get("tr", 0))], "vcol": 0.0,
                        "tex": t, "mode": 3, "mat": None, "uvp": uvp, "cf": cf, "pos": np.array(cf[:3]) if cf else None,
                        "local": (R, off), "wall": False})
        return out

    @staticmethod
    def _wall(p) -> bool:
        """Parts the camera may see through (Studio's cutaway rule): wall-sized slabs standing upright, and poles."""
        if p.get("wall") is not None:   # an explicit flag (own_sets.py: window strips, door headers, ceilings)
            return bool(p["wall"])
        if not p.get("cf"):
            return False
        sz = np.array(p["size"])
        rot = np.array(p["cf"][3:12]).reshape(3, 3)
        order = np.argsort(sz)
        thin, mid = sz[order[0]], sz[order[1]]
        if thin <= 1.2 and mid >= 8 and abs(rot[1, order[0]]) < 0.5:
            return True
        return sz[order[1]] <= 0.9 and sz[order[2]] >= 5 and abs(rot[1, order[2]]) > 0.9

    def model(self, spec, pos, rot):
        """3x4 world matrix for a spec at pos/rot (3x3)."""
        _vbo, _n, centre, msize = self._mesh(spec["key"])
        if spec["local"] is not None:
            R, off = spec["local"]
            pos, rot = pos + rot @ off, rot @ R
        s = spec["scale"] if spec["native"] else spec["scale"] / msize
        if spec["native"]:
            s = spec["scale"] * np.ones(3)
        m = np.zeros((3, 4))
        m[:, :3] = rot * s[None, :]
        m[:, 3] = pos - rot @ (centre * s)
        return m


class Renderer:
    def __init__(self, scene_dir: Path, w=1080, h=1920, hide_paths=None):
        self.ctx = moderngl.create_standalone_context()
        ctx = self.ctx
        self.w, self.h = w, h
        index = json.loads((MESHES / "index.json").read_text())
        static = json.loads((scene_dir / "static.json").read_text())
        hp = Path(scene_dir) / "hide.json"
        hide_paths = hide_paths if hide_paths is not None else (json.loads(hp.read_text()) if hp.exists() else [])
        if hide_paths:      # set pieces this episode hides (benches, signs): out of the static world for good
            pre = tuple(hide_paths)
            static = dict(static, parts=[p for p in static["parts"]
                                          if not any(p.get("path", "") == h or p.get("path", "").startswith(h + ".") for h in pre)])
        dyn_p = scene_dir / "dynamic.json"
        dyn = json.loads(dyn_p.read_text()) if dyn_p.exists() else None
        Scene._tex_images = {}
        self.sc = Scene(ctx, static, dyn, index)
        self.textures = {}
        self.prog = ctx.program(vertex_shader=VS, fragment_shader=FS)
        self.sprog = ctx.program(vertex_shader=SVS, fragment_shader=SFS)
        self.sky = ctx.program(vertex_shader=SKY_VS, fragment_shader=SKY_FS)
        self.sky_vao = ctx.vertex_array(self.sky, [(ctx.buffer(np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], "f4").tobytes()), "2f", "p")])
        self.color = ctx.renderbuffer((w, h), 4, samples=4)
        self.depth = ctx.depth_renderbuffer((w, h), samples=4)
        self.fbo = ctx.framebuffer([self.color], self.depth)
        self.out = ctx.framebuffer([ctx.renderbuffer((w, h), 4)])
        self.shadow_tex = ctx.depth_texture((4096, 4096))
        self.shadow_tex.compare_func = "<="
        self.shadow_tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.shadow_fbo = ctx.framebuffer(depth_attachment=self.shadow_tex)
        self.white = ctx.texture((1, 1), 4, b"\xff\xff\xff\xff")
        self.faces = {}
        # static instances grouped by (mesh, texture, mode, vcol, transparent)
        groups = {}
        S = self.sc
        for sp in S.static:
            c = sp["cf"]
            m = S.model(sp, np.array(c[:3]), np.array(c[3:12]).reshape(3, 3))
            k = (sp["key"], sp["tex"], sp["mode"], sp["vcol"], sp["col"][3] < 0.999 or sp["mode"] == 3, sp["mat"])
            groups.setdefault((k, sp.get("cast", True)), []).append(
                (np.hstack([m.ravel(), sp["col"], sp["uvp"], (0, 0)]), sp["pos"], sp["wall"], m))
        self.static_groups = []
        for (k, cast), items in groups.items():
            M = np.array([a for a, _, _, _ in items], "f4")
            self.static_groups.append({"k": k, "cast": cast, "inst": M, "pos": np.array([p for _, p, _, _ in items]),
                                       "wall": np.array([w_ for _, _, w_, _ in items]),
                                       "mats": np.array([m for _, _, _, m in items]),
                                       "buf": ctx.buffer(reserve=max(16, M.nbytes)), "n": 0, "mask": None})
        # dynamic: per-spec part index, grouped once by key (heads re-grouped per face each frame)
        self.dyn_idx = np.array(S.dyn_part, int)
        self.dyn_buf = {}
        self.vaos = {}

    # textures ---------------------------------------------------------------------------------------------
    def tex(self, key):
        if key is None:
            return self.white
        t = self.textures.get(key)
        if t is None:
            if key.startswith("skin:"):
                im = Scene._tex_images[key]
            elif key.startswith("face:"):
                im = Image.open(TEXDIR / f"face_{key[5:]}.png").convert("RGBA")
            else:
                im = Image.open(key).convert("RGBA")
            t = self.ctx.texture(im.size, 4, im.tobytes())
            t.build_mipmaps()
            t.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
            t.repeat_x = t.repeat_y = True
            t.anisotropy = 8.0
            self.textures[key] = t
        return t

    def mat(self, name):
        k = "mat:" + name
        t = self.textures.get(k)
        if t is None:
            im = Image.open(MATDIR / f"{name}.png").convert("RGB")
            t = self.ctx.texture(im.size, 3, im.tobytes())
            t.build_mipmaps()
            t.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
            t.anisotropy = 8.0
            self.textures[k] = t
        return t

    def _vao(self, prog, key, ibuf):
        k = (id(prog), key, id(ibuf))
        if k not in self.vaos:
            vbo, n, _, _ = self.sc._mesh(key)
            if prog is self.prog:
                self.vaos[k] = self.ctx.vertex_array(prog, [(vbo, "3f 3f 2f 4f", "in_pos", "in_nrm", "in_uv", "in_vcol"),
                                                          (ibuf, "4f 4f 4f 4f 4f/i", "i_m0", "i_m1", "i_m2", "i_col", "i_uvp")])
            else:
                self.vaos[k] = self.ctx.vertex_array(prog, [(vbo, "3f 36x", "in_pos"),
                                                          (ibuf, "4f 4f 4f 32x/i", "i_m0", "i_m1", "i_m2")])
        return self.vaos[k]

    @staticmethod
    def _cut(mats, cam, look):
        """Which wall instances block the camera -> aim segment (plus two offsets): ray vs oriented box."""
        if len(mats) == 0:
            return np.zeros(0, bool)
        hit = np.zeros(len(mats), bool)
        A = mats[:, :, :3]                       # rot * scale (unit box)
        T = mats[:, :, 3]
        Ainv = np.linalg.inv(A)
        for off in (0.0, 1.2, -1.2):
            a = cam
            b = look + np.array([0, off, 0])
            pa = np.einsum("nij,nj->ni", Ainv, a[None, :] - T)
            pb = np.einsum("nij,nj->ni", Ainv, b[None, :] - T)
            d = pb - pa
            with np.errstate(divide="ignore", invalid="ignore"):
                t1 = (-0.5 - pa) / d
                t2 = (0.5 - pa) / d
            tmin = np.nanmax(np.where(np.isfinite(t1), np.minimum(t1, t2), -np.inf), 1)
            tmax = np.nanmin(np.where(np.isfinite(t1), np.maximum(t1, t2), np.inf), 1)
            inside = np.all(np.abs(pa) <= 0.5 + 0.05, 1)
            hit |= ((tmin <= tmax) & (tmax >= 0) & (tmin <= 1)) | inside
        return hit

    def frame(self, cam_pos, look, fov, dyn_draws=(), radius=160.0):
        ctx = self.ctx
        cam_pos, look = np.asarray(cam_pos, "f8"), np.asarray(look, "f8")
        draws = []
        nocast = set()          # draws that cast no shadow (parts with "cast": false)
        for g in self.static_groups:
            mask = np.einsum("ij,ij->i", g["pos"] - cam_pos, g["pos"] - cam_pos) < radius * radius
            wm = mask & g["wall"]
            if wm.any():
                cut = np.zeros(len(mask), bool)
                cut[wm] = self._cut(g["mats"][wm], cam_pos, look)
                mask &= ~cut
            if g["mask"] is None or not np.array_equal(mask, g["mask"]):
                sel = g["inst"][mask]
                g["n"] = len(sel)
                if len(sel):
                    g["buf"].write(sel.tobytes())
                g["mask"] = mask
            if g["n"]:
                draws.append((g["k"], g["buf"], g["n"]))
                if not g["cast"]:
                    nocast.add(len(draws) - 1)
        for k, M in dyn_draws:
            b = self.dyn_buf.get(k)
            if b is None or b.size < M.nbytes:
                b = self.dyn_buf[k] = ctx.buffer(reserve=max(M.nbytes, 2048))
            b.write(M.tobytes())
            draws.append((k, b, len(M)))
        L = self.sc.light
        sun = np.array(L.get("sun", (0.4, 0.8, 0.3)), "f8")
        sun /= np.linalg.norm(sun)
        lv = look_at(look + sun * 150, look, (0, 0, 1) if abs(sun[1]) > 0.99 else (0, 1, 0))
        light_vp = (ortho(-45, 45, -45, 45, 1, 400) @ lv).astype("f4")
        self.shadow_fbo.use()
        self.shadow_fbo.clear(depth=1.0)
        ctx.enable(moderngl.DEPTH_TEST)
        ctx.disable(moderngl.CULL_FACE)
        self.sprog["light_vp"].write(light_vp.T.tobytes())
        for di, (k, b, n) in enumerate(draws):
            if not k[4] and di not in nocast:
                self._vao(self.sprog, k[0], b).render(instances=n)
        self.fbo.use()
        ctx.viewport = (0, 0, self.w, self.h)
        self.fbo.clear(0.6, 0.78, 0.95, 1.0)
        ctx.disable(moderngl.DEPTH_TEST)
        self.sky["top"].value = (0.36, 0.62, 0.95)
        self.sky["horizon"].value = (0.80, 0.90, 0.99)
        self.sky_vao.render()
        ctx.enable(moderngl.DEPTH_TEST)
        vp = (perspective(fov, self.w / self.h) @ look_at(cam_pos, look)).astype("f4")
        P = self.prog
        P["vp"].write(vp.T.tobytes())
        P["light_vp"].write(light_vp.T.tobytes())
        P["sun"].value = tuple(sun)
        lo = LIGHT_OVERRIDE or LIGHT
        P["sun_col"].value = tuple(lo["sun"])
        P["sky"].value = tuple(lo["sky"])
        P["ground"].value = tuple(lo["ground"])
        P["cam"].value = tuple(cam_pos)
        P["exposure"].value = float((LIGHT_OVERRIDE or LIGHT).get("exp", 1.0))
        self.shadow_tex.use(0)
        P["shadow"].value = 0
        P["tex"].value = 1
        P["mat"].value = 2
        for transp in (False, True):
            if transp:
                ctx.enable(moderngl.BLEND)
                ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
                ctx.depth_mask = False
            for k, b, n in draws:
                if k[4] != transp:
                    continue
                key, tex, mode, vcol, _, matname = k
                P["use_vcol"].value = vcol
                P["mode"].value = mode
                self.tex(tex).use(1)
                if matname:
                    self.mat(matname).use(2)
                    P["mat_tile"].value = MAT_TILE.get(matname, 8.0)
                P["mat_on"].value = 1.0 if matname else 0.0
                if mode == 3:
                    ctx.polygon_offset = -1, -1
                self._vao(P, key, b).render(instances=n)
                ctx.polygon_offset = 0, 0
        ctx.depth_mask = True
        ctx.disable(moderngl.BLEND)
        ctx.copy_framebuffer(self.out, self.fbo)
        return self.out.read(components=3)


def dyn_draws(R: Renderer, pose: np.ndarray, faces_row=None, actor_order=(), hidden_y: float = -500):
    """Instance data for the moving parts at one frame: pose (n,7) position + quaternion per exported part."""
    S = R.sc
    rots = quat_mat(pose[:, 3:7].astype("f8"))
    face_of = {}
    if faces_row is not None:
        import export as X
        for a, f in zip(actor_order, faces_row):
            face_of[a] = X.FACES[int(f) - 1] if 0 < int(f) <= len(X.FACES) else "neutral"
    groups = {}
    for sp, pi, actor in zip(S.dyn, R.dyn_idx, S.dyn_actor):
        p = pose[pi]
        if p[1] < hidden_y:
            continue
        m = S.model(sp, p[:3].astype("f8"), rots[pi])
        tex, mode = sp["tex"], sp["mode"]
        if mode == 2:
            tex = f"face:{face_of.get(actor, 'neutral')}"
        k = (sp["key"], tex, mode, sp["vcol"], sp["col"][3] < 0.999 or mode == 3, sp["mat"])
        groups.setdefault(k, []).append(np.hstack([m.ravel(), sp["col"], sp["uvp"], (0, 0)]))
    return [(k, np.array(v, "f4")) for k, v in groups.items()]


def render_video(scene_dir: Path, cams: np.ndarray, out_mp4: Path, fps: int = 30, ffmpeg_args=None,
                 vf: str | None = None, extra_inputs=(), start: int = 0) -> dict:
    """cams: (F, 7) camera position, look-at, vertical fov per output frame; poses from scene_dir/frames.npz."""
    t = time.time()
    R = Renderer(scene_dir)
    fr = np.load(scene_dir / "frames.npz")
    poses, faces = fr["pose"], fr["face"]
    order = json.loads((scene_dir / "dynamic.json").read_text()).get("order", [])
    t_load = time.time() - t
    ff = r"D:\tools\ffmpeg\bin\ffmpeg.exe"
    filt = "vflip" + ("," + vf if vf else "")
    cmd = [ff, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{R.w}x{R.h}", "-framerate",
           str(fps), "-i", "-", *extra_inputs, "-vf", filt,
           *(ffmpeg_args or ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22",
                             "-pix_fmt", "yuv420p"]), str(out_mp4)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t1 = time.time()
    for i in range(len(cams)):
        k = min(start + i, len(poses) - 1)
        img = R.frame(cams[i, :3], cams[i, 3:6], cams[i, 6], dyn_draws(R, poses[k], faces[k], order))
        enc.stdin.write(img)
    enc.stdin.close()
    enc.wait()
    return {"frames": len(cams), "load_s": round(t_load, 1), "render_s": round(time.time() - t1, 1),
            "fps": round(len(cams) / (time.time() - t1), 1), "missing_meshes": R.sc.missing}


FF = "D:/tools/ffmpeg/bin/ffmpeg.exe"


def _ass_vf(ass: str | None, fonts: str | None, t0: float) -> str | None:
    """Captions burned in this chunk's frames: shift the timestamps to story time for the subtitle filter."""
    if not ass:
        return None
    esc = lambda p: str(p).replace(chr(92), "/").replace(":", chr(92) + ":")
    f = f"ass='{esc(ass)}'" + (f":fontsdir='{esc(fonts)}'" if fonts else "")
    return f"setpts=PTS+{t0:.6f}/TB,{f},setpts=PTS-STARTPTS"


def render_parallel(scene_dir: Path, cams: np.ndarray, out_mp4: Path, fps: int = 30, workers: int = 3,
                    ass: str | None = None, fonts: str | None = None, wav: str | None = None) -> dict:
    """The timeline cut into `workers` slices rendered by separate processes (one GL context each; the GPU has room),
    captions burned in per slice, slices joined without re-encoding, audio muxed: the finished episode."""
    t = time.time()
    scene_dir = Path(scene_dir)
    np.save(scene_dir / "cams_r.npy", cams)
    n = len(cams)
    bounds = [round(n * i / workers) for i in range(workers + 1)]
    procs, chunks = [], []
    for i in range(workers):
        a, b = bounds[i], bounds[i + 1]
        ch = scene_dir / f"chunk{i}.mp4"
        chunks.append(ch)
        cmd = [sys.executable, __file__, "--chunk", str(scene_dir), str(a), str(b), str(ch), str(fps)]
        if ass:
            cmd += ["--ass", str(ass), "--fonts", str(fonts or "")]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT))
    logs = []
    for p in procs:
        out, _ = p.communicate()
        logs.append(out.decode(errors="ignore")[-400:])
        if p.returncode != 0:
            raise RuntimeError("render worker failed: " + logs[-1])
    t_render = time.time() - t
    lst = scene_dir / "chunks.txt"
    lst.write_text("".join("file '" + c.as_posix() + "'" + chr(10) for c in chunks))
    cmd = [FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst)]
    if wav:
        cmd += ["-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", str(out_mp4)]
    subprocess.run(cmd, check=True)
    for c in chunks:
        c.unlink(missing_ok=True)
    return {"frames": n, "workers": workers, "render_s": round(t_render, 1), "total_s": round(time.time() - t, 1),
            "fps": round(n / t_render, 1), "worker_logs": [l.strip().splitlines()[-1] if l.strip() else "" for l in logs]}


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--chunk":
    d, a, b, outp, fps = Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), Path(sys.argv[5]), int(sys.argv[6])
    ass = sys.argv[sys.argv.index("--ass") + 1] if "--ass" in sys.argv else None
    fonts = sys.argv[sys.argv.index("--fonts") + 1] if "--fonts" in sys.argv else None
    cams = np.load(d / "cams_r.npy")[a:b]
    print(render_video(d, cams, outp, fps, vf=_ass_vf(ass, fonts, a / fps), start=a))
