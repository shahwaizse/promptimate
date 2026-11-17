"""Our own character kit: no catalog clothing, hair or accessories (IP-clean for a commercial service).

- Clothing: shirt / pants templates drawn on the classic 585x559 layout (the R6 boxes map it exactly as Roblox
  does): solids, plaid, stripes, hoodies, suits with tie and lapels, dresses, uniforms, overalls, robes.
- Hair, hats, glasses, crowns: blocky low-poly meshes built from boxes and spheres, colours baked per vertex.
- Looks: keyed like the existing cast looks (c_timmy, c_preston, ...), so every episode works unchanged.

    python roblox/headless/own_assets.py      # writes <cache>/own/{tex,looks.json} and meshes into the mesh cache
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import meshcache as MC  # noqa: E402

OWN = MC.OUT.parent / "own"
TEXO = OWN / "tex"
W_, H_ = 585, 559

# template rects (x, y, w, h)
TORSO = {"F": (231, 74, 128, 128), "B": (427, 74, 128, 128), "R": (165, 74, 64, 128), "L": (361, 74, 64, 128),
         "U": (231, 8, 128, 64), "D": (231, 204, 128, 64)}
RLIMB = {"F": (217, 355, 64, 128), "B": (85, 355, 64, 128), "R": (151, 355, 64, 128), "L": (19, 355, 64, 128),
         "U": (217, 289, 64, 64), "D": (217, 485, 64, 64)}
LLIMB = {"F": (308, 355, 64, 128), "B": (440, 355, 64, 128), "R": (506, 355, 64, 128), "L": (374, 355, 64, 128),
         "U": (308, 289, 64, 64), "D": (308, 485, 64, 64)}
SIDES = ("F", "B", "R", "L")


def rgb(c):
    return tuple(int(v) for v in c)


def shade(c, k):
    return tuple(int(max(0, min(255, v * k))) for v in c)


# --------------------------------------------------------------------------------------------- patterns
def pattern(kind: str, size, base, accent, seed: int = 0) -> Image.Image:
    w, h = size
    im = Image.new("RGBA", (w, h), rgb(base) + (255,))
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(seed)
    if kind == "plaid":
        for x in range(0, w, 16):
            d.rectangle((x, 0, x + 5, h), fill=rgb(accent) + (150,))
            d.line((x + 10, 0, x + 10, h), fill=(255, 255, 255, 90), width=1)
        for y in range(0, h, 16):
            d.rectangle((0, y, w, y + 5), fill=rgb(accent) + (150,))
            d.line((0, y + 10, w, y + 10), fill=(255, 255, 255, 90), width=1)
    elif kind == "stripes":
        for y in range(0, h, 14):
            d.rectangle((0, y, w, y + 6), fill=rgb(accent) + (255,))
    elif kind == "polka":
        for y in range(4, h, 18):
            for x in range(4 + (y // 18 % 2) * 9, w, 18):
                d.ellipse((x, y, x + 7, y + 7), fill=rgb(accent) + (255,))
    elif kind == "floral":
        for _ in range(int(w * h / 260)):
            x, y = rng.integers(0, w), rng.integers(0, h)
            for a in range(5):
                ox, oy = 3 * math.cos(a * 1.256), 3 * math.sin(a * 1.256)
                d.ellipse((x + ox - 2, y + oy - 2, x + ox + 2, y + oy + 2), fill=rgb(accent) + (255,))
            d.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(250, 220, 90, 255))
    elif kind == "denim":
        a = np.asarray(im).astype(float)
        n = rng.normal(0, 9, (h, w, 1))
        a[:, :, :3] = np.clip(a[:, :, :3] + n, 0, 255)
        im = Image.fromarray(a.astype("uint8"), "RGBA")
        d = ImageDraw.Draw(im)
        for x in range(0, w, 5):
            d.line((x, 0, x + h // 3, h), fill=(255, 255, 255, 18))
    return im


def paste_rects(im: Image.Image, rects, tile: Image.Image | None = None, color=None, frac=(0.0, 1.0)):
    """Fill template rects (optionally only a vertical fraction of each side face) with a pattern tile or colour."""
    for k, (x, y, w, h) in rects.items():
        y0, y1 = (y, y + h)
        if k in SIDES and frac != (0.0, 1.0):
            y0, y1 = int(y + h * frac[0]), int(y + h * frac[1])
        elif k in ("U", "D") and frac != (0.0, 1.0) and ((k == "U" and frac[0] > 0) or (k == "D" and frac[1] < 1)):
            continue
        if tile is not None:
            im.paste(tile.crop((x, y0, x + w, y1)), (x, y0), tile.crop((x, y0, x + w, y1)))
        else:
            ImageDraw.Draw(im).rectangle((x, y0, x + w - 1, y1 - 1), fill=rgb(color) + (255,))


def shirt(spec: dict, seed: int) -> Image.Image:
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    kind = spec.get("kind", "tee")
    base, acc = spec.get("color", (60, 120, 200)), spec.get("accent", (30, 40, 70))
    tile = pattern(spec.get("pattern", "solid"), (W_, H_), base, acc, seed)
    sleeve = spec.get("sleeve", "long")
    torso = {k: v for k, v in TORSO.items()}
    paste_rects(im, torso, tile)
    arm_frac = {"long": (0.0, 1.0), "short": (0.0, 0.42), "none": (0.0, 0.0)}[sleeve]
    if arm_frac[1] > 0:
        paste_rects(im, RLIMB, tile, frac=arm_frac)
        paste_rects(im, LLIMB, tile, frac=arm_frac)
    d = ImageDraw.Draw(im)
    fx, fy, fw, fh = TORSO["F"]
    if spec.get("under"):            # an open shirt / jacket over a T-shirt: a strip down the front
        u = spec["under"]
        d.rectangle((fx + fw * 0.34, fy, fx + fw * 0.66, fy + fh), fill=rgb(u) + (255,))
    if kind == "suit":
        d.polygon([(fx + fw * 0.34, fy), (fx + fw * 0.66, fy), (fx + fw * 0.5, fy + fh * 0.55)], fill=(245, 245, 245, 255))
        tie = spec.get("tie", (170, 30, 40))
        d.polygon([(fx + fw * 0.47, fy + 6), (fx + fw * 0.53, fy + 6), (fx + fw * 0.56, fy + fh * 0.5),
                   (fx + fw * 0.5, fy + fh * 0.58), (fx + fw * 0.44, fy + fh * 0.5)], fill=rgb(tie) + (255,))
        for side in (-1, 1):       # lapels
            x0 = fx + fw * (0.5 + side * 0.16)
            d.line((x0, fy, fx + fw * (0.5 + side * 0.03), fy + fh * 0.56), fill=rgb(shade(base, 0.7)) + (255,), width=3)
        for k in range(3):
            d.ellipse((fx + fw * 0.5 - 3, fy + fh * (0.62 + k * 0.12) - 3, fx + fw * 0.5 + 3, fy + fh * (0.62 + k * 0.12) + 3),
                      fill=rgb(shade(base, 0.6)) + (255,))
    elif kind == "hoodie":
        d.rounded_rectangle((fx + fw * 0.22, fy + fh * 0.62, fx + fw * 0.78, fy + fh * 0.9), 6,
                            fill=rgb(shade(base, 0.85)) + (255,))
        for side in (-1, 1):
            d.line((fx + fw * (0.5 + side * 0.08), fy, fx + fw * (0.5 + side * 0.08), fy + fh * 0.32), fill=(240, 240, 240, 255), width=2)
    elif kind == "uniform":
        d.rectangle((fx, fy + fh * 0.78, fx + fw, fy + fh * 0.86), fill=(30, 30, 30, 255))
        d.polygon([(fx + fw * 0.68, fy + fh * 0.2), (fx + fw * 0.82, fy + fh * 0.2), (fx + fw * 0.75, fy + fh * 0.36)], fill=(230, 190, 60, 255))
        for k in range(4):
            d.ellipse((fx + fw * 0.5 - 2, fy + fh * (0.15 + k * 0.17), fx + fw * 0.5 + 2, fy + fh * (0.15 + k * 0.17) + 4), fill=(230, 190, 60, 255))
    elif kind == "vest":
        hv = spec.get("accent", (255, 140, 0))
        for k in ("F", "B"):
            x, y, w, h = TORSO[k]
            d.rectangle((x, y, x + w, y + h), fill=rgb(hv) + (255,))
            d.rectangle((x, y + h * 0.55, x + w, y + h * 0.63), fill=(230, 230, 230, 255))
    elif kind == "robe":
        d.rectangle((fx + fw * 0.44, fy, fx + fw * 0.56, fy + fh), fill=(245, 240, 230, 255))
        for k in range(10):
            d.ellipse((fx + fw * 0.44 + (k % 2) * 6, fy + k * 13, fx + fw * 0.44 + (k % 2) * 6 + 4, fy + k * 13 + 4), fill=(30, 30, 30, 255))
    elif kind == "chef":
        for k in range(2):
            for j in range(3):
                d.ellipse((fx + fw * (0.35 + k * 0.3) - 3, fy + fh * (0.25 + j * 0.2) - 3,
                           fx + fw * (0.35 + k * 0.3) + 3, fy + fh * (0.25 + j * 0.2) + 3), fill=(40, 40, 40, 255))
    elif kind == "cardigan":
        d.rectangle((fx + fw * 0.4, fy, fx + fw * 0.6, fy + fh), fill=rgb(spec.get("under", (240, 235, 220))) + (255,))
        for k in range(5):
            d.ellipse((fx + fw * 0.4 - 2, fy + 14 + k * 22, fx + fw * 0.4 + 3, fy + 19 + k * 22), fill=(80, 60, 40, 255))
    if spec.get("collar"):
        d.polygon([(fx + fw * 0.36, fy), (fx + fw * 0.5, fy + 16), (fx + fw * 0.64, fy)], fill=rgb(spec["collar"]) + (255,))
    if spec.get("logo"):            # a big simple chest graphic: star / heart / number
        cx, cy = fx + fw * 0.5, fy + fh * 0.4
        lc = rgb(spec.get("logo_color", (255, 255, 255))) + (255,)
        if spec["logo"] == "heart":
            d.ellipse((cx - 16, cy - 12, cx, cy + 4), fill=lc); d.ellipse((cx, cy - 12, cx + 16, cy + 4), fill=lc)
            d.polygon([(cx - 16, cy - 2), (cx + 16, cy - 2), (cx, cy + 18)], fill=lc)
        elif spec["logo"] == "star":
            pts = [(cx + 18 * math.sin(a * math.pi / 5) * (1 if a % 2 == 0 else 0.45),
                    cy - 18 * math.cos(a * math.pi / 5) * (1 if a % 2 == 0 else 0.45)) for a in range(10)]
            d.polygon(pts, fill=lc)
        else:
            d.text((cx - 14, cy - 20), str(spec["logo"]), fill=lc, font_size=40)
    return im


def pants(spec: dict, seed: int) -> Image.Image:
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    base, acc = spec.get("color", (40, 60, 120)), spec.get("accent", (20, 30, 60))
    kind = spec.get("kind", "trousers")
    tile = pattern(spec.get("pattern", "denim" if kind == "jeans" else "solid"), (W_, H_), base, acc, seed)
    leg_frac = {"shorts": (0.0, 0.45), "skirt": (0.0, 0.5)}.get(kind, (0.0, 1.0))
    paste_rects(im, RLIMB, tile, frac=leg_frac)
    paste_rects(im, LLIMB, tile, frac=leg_frac)
    # the torso's lower band (belt line) and, for dresses/overalls, more of the torso
    d = ImageDraw.Draw(im)
    torso_frac = {"overalls": 0.35, "dress": 0.0}.get(kind, 0.82)
    for k in SIDES:
        x, y, w, h = TORSO[k]
        y0 = int(y + h * torso_frac)
        im.paste(tile.crop((x, y0, x + w, y + h)), (x, y0), tile.crop((x, y0, x + w, y + h)))
        if kind not in ("dress", "skirt"):
            d.rectangle((x, y + h * 0.84, x + w, y + h * 0.9), fill=rgb(spec.get("belt", (40, 30, 25))) + (255,))
    paste_rects(im, {"D": TORSO["D"]}, tile)
    if kind == "overalls":
        fx, fy, fw, fh = TORSO["F"]
        for side in (-1, 1):
            d.rectangle((fx + fw * (0.5 + side * 0.3) - 5, fy, fx + fw * (0.5 + side * 0.3) + 5, fy + fh * 0.4), fill=rgb(base) + (255,))
    for limb in (RLIMB, LLIMB):     # shoes
        for k in SIDES:
            x, y, w, h = limb[k]
            d.rectangle((x, y + h * 0.88, x + w, y + h), fill=rgb(spec.get("shoes", (30, 30, 30))) + (255,))
        x, y, w, h = limb["D"]
        d.rectangle((x, y, x + w, y + h), fill=rgb(spec.get("shoes", (30, 30, 30))) + (255,))
    return im


# ---------------------------------------------------------------------------------------- blocky meshes
def _box_tris(c, s, R=None):
    import hlrender as RD
    P, N, _ = RD._box()
    R = np.eye(3) if R is None else R
    return (P * np.asarray(s, float)) @ R.T + np.asarray(c, float), N @ R.T


def _ball_tris(c, s):
    import hlrender as RD
    P, N, _ = RD._sphere(14, 10)
    return P * np.asarray(s, float) + np.asarray(c, float), N


def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


# head-local coordinates (head part centre = origin, +Y up, the face looks down -Z); the visible R6 head is a rounded
# cylinder about 1.15 wide, 1.1 tall
HAIR = {
    "short": [("box", (0, 0.5, 0.05), (1.26, 0.28, 1.26)), ("box", (0, 0.2, 0.56), (1.24, 0.7, 0.2)),
              ("box", (0.6, 0.25, 0.05), (0.12, 0.55, 1.1)), ("box", (-0.6, 0.25, 0.05), (0.12, 0.55, 1.1)),
              ("box", (0, 0.45, -0.55), (1.15, 0.2, 0.2))],
    "bangs": [("box", (0, 0.5, 0.05), (1.26, 0.3, 1.26)), ("box", (0, 0.15, 0.56), (1.24, 0.8, 0.22)),
              ("box", (0.6, 0.15, 0.05), (0.13, 0.75, 1.12)), ("box", (-0.6, 0.15, 0.05), (0.13, 0.75, 1.12)),
              ("box", (-0.18, 0.34, -0.58), (0.85, 0.36, 0.16)), ("box", (0.42, 0.38, -0.58), (0.36, 0.28, 0.16))],
    "long": [("box", (0, 0.5, 0.05), (1.28, 0.3, 1.28)), ("box", (0, -0.25, 0.58), (1.26, 1.55, 0.24)),
             ("box", (0.62, -0.15, 0.1), (0.14, 1.35, 1.0)), ("box", (-0.62, -0.15, 0.1), (0.14, 1.35, 1.0)),
             ("box", (0, 0.42, -0.57), (1.15, 0.22, 0.16))],
    "ponytail": [("box", (0, 0.5, 0.05), (1.26, 0.28, 1.26)), ("box", (0, 0.2, 0.56), (1.24, 0.7, 0.2)),
                 ("box", (0.6, 0.25, 0.05), (0.12, 0.55, 1.1)), ("box", (-0.6, 0.25, 0.05), (0.12, 0.55, 1.1)),
                 ("box", (0, -0.15, 0.82), (0.32, 0.95, 0.32)), ("box", (0, 0.45, -0.55), (1.15, 0.2, 0.2))],
    "pigtails": [("box", (0, 0.5, 0.05), (1.26, 0.28, 1.26)), ("box", (0, 0.2, 0.56), (1.24, 0.7, 0.2)),
                 ("box", (0.78, 0.15, 0.2), (0.36, 0.6, 0.36)), ("box", (-0.78, 0.15, 0.2), (0.36, 0.6, 0.36)),
                 ("box", (0, 0.42, -0.57), (1.15, 0.22, 0.16))],
    "bun": [("box", (0, 0.5, 0.05), (1.26, 0.26, 1.26)), ("box", (0, 0.2, 0.56), (1.24, 0.7, 0.2)),
            ("box", (0.6, 0.25, 0.05), (0.12, 0.55, 1.1)), ("box", (-0.6, 0.25, 0.05), (0.12, 0.55, 1.1)),
            ("ball", (0, 0.82, 0.25), (0.6, 0.5, 0.6))],
    "spiky": [("box", (0, 0.48, 0.05), (1.24, 0.24, 1.24)), ("box", (0, 0.2, 0.56), (1.22, 0.65, 0.2))]
             + [("spike", (x, 0.7, z), (0.3, 0.42, 0.3)) for x in (-0.38, 0, 0.38) for z in (-0.35, 0.05, 0.42)],
    "afro": [("ball", (0, 0.38, 0.08), (1.75, 1.45, 1.7))],
    "buzz": [("box", (0, 0.52, 0.05), (1.2, 0.12, 1.2)), ("box", (0, 0.3, 0.56), (1.18, 0.4, 0.12))],
    "bald": [],
}
HATS = {
    "beanie": [("box", (0, 0.6, 0.03), (1.34, 0.5, 1.34), "main"), ("box", (0, 0.36, 0.03), (1.4, 0.18, 1.4), "dark"),
               ("box", (0, 0.92, 0.03), (0.9, 0.2, 0.9), "main")],
    "cap": [("box", (0, 0.62, 0.05), (1.3, 0.36, 1.3), "main"), ("box", (0, 0.46, -0.8), (0.95, 0.06, 0.5), "dark")],
    "tophat": [("box", (0, 0.48, 0), (1.6, 0.06, 1.6), "main"), ("box", (0, 0.98, 0), (1.05, 1.0, 1.05), "main"),
               ("box", (0, 0.6, 0), (1.07, 0.14, 1.07), "dark")],
    "police": [("box", (0, 0.62, 0.02), (1.32, 0.36, 1.32), "main"), ("box", (0, 0.5, -0.72), (0.9, 0.06, 0.42), "dark"),
               ("box", (0, 0.66, -0.67), (0.22, 0.2, 0.04), "gold")],
    "hardhat": [("ball", (0, 0.62, 0), (1.4, 0.75, 1.4), "main"), ("box", (0, 0.42, -0.62), (1.1, 0.06, 0.3), "main")],
    "chef": [("box", (0, 0.66, 0), (1.25, 0.3, 1.25), "main"), ("ball", (0, 1.15, 0), (1.35, 0.85, 1.35), "main")],
    "crown": [("box", (0, 0.66, 0), (1.25, 0.24, 1.25), "gold")]
             + [("spike", (0.5 * math.sin(a), 0.92, 0.5 * math.cos(a)), (0.22, 0.32, 0.22), "gold") for a in np.linspace(0, 2 * math.pi, 9)[:-1]],
    "bow": [("box", (-0.24, 0.62, 0.3), (0.34, 0.26, 0.12), "main"), ("box", (0.24, 0.62, 0.3), (0.34, 0.26, 0.12), "main"),
            ("box", (0, 0.62, 0.3), (0.14, 0.16, 0.14), "dark")],
}
def _rims():
    """Glasses as thin frames: four bars per lens, a bridge and two arms (clear lenses, unlike sunglasses)."""
    out, t, z = [], 0.045, -0.62
    for cx in (-0.23, 0.23):
        w, h, cy = 0.34, 0.26, 0.12
        out += [("box", (cx, cy + h / 2, z), (w, t, t)), ("box", (cx, cy - h / 2, z), (w, t, t)),
                ("box", (cx - w / 2, cy, z), (t, h, t)), ("box", (cx + w / 2, cy, z), (t, h, t))]
    out += [("box", (0, 0.2, z), (0.12, t, t)), ("box", (-0.6, 0.2, -0.35), (t, t, 0.55)), ("box", (0.6, 0.2, -0.35), (t, t, 0.55))]
    return out


GLASSES = _rims()
MUSTACHE = [("box", (0, -0.1, -0.62), (0.5, 0.12, 0.06))]
BEARD = [("box", (0, -0.25, -0.5), (1.05, 0.5, 0.25)), ("box", (0.55, -0.05, -0.1), (0.12, 0.7, 0.8)),
         ("box", (-0.55, -0.05, -0.1), (0.12, 0.7, 0.8))]


def _flat_normals(p):
    t = p.reshape(-1, 3, 3)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    return np.repeat(n, 3, axis=0)


def piece_tris(shape, c, s, opt=None):
    """One primitive piece -> (positions, normals). Shapes: box, ball, spike (box tapered to its top), cyl / cylx /
    cylz (a cylinder along Y / X / Z), wedge (Roblox wedge: the slope falls from +Z top to -Z bottom).
    opt: {"R": 3x3 rotation applied after scaling, "taper": top scale for box / cyl (cones, frustums), "seg": sides}."""
    import hlrender as RD
    opt = opt or {}
    s = np.asarray(s, float)
    taper = opt.get("taper")
    if shape == "box":
        p, n = _box_tris((0, 0, 0), s)
    elif shape == "ball":
        P_, N_, _ = RD._sphere(opt.get("seg", 14), max(6, opt.get("seg", 14) * 5 // 7))
        p, n = P_ * s, N_ / np.maximum(s, 1e-6)
        n = n / np.linalg.norm(n, axis=1, keepdims=True)
    elif shape == "spike":
        p, n = _box_tris((0, 0, 0), s)
        taper = 0.25 if taper is None else taper
    elif shape in ("cyl", "cylx", "cylz"):
        P_, N_, _ = RD._cylinder(opt.get("seg", 20), axis=1 if shape == "cyl" else 0)
        P_, N_ = P_.astype(float), N_.astype(float)
        if shape == "cylz":
            P_, N_ = P_[:, [2, 1, 0]], N_[:, [2, 1, 0]]
        p, n = P_ * s, N_
    elif shape == "wedge":
        P_, N_, _ = RD._wedge()
        p = P_.astype(float) * s
        n = _flat_normals(p)
    else:
        raise ValueError(shape)
    if taper is not None and taper != 1:
        ax = {"cylx": 0, "cylz": 2}.get(shape, 1)
        t = p[:, ax] / max(s[ax], 1e-9) + 0.5           # 0 at the bottom, 1 at the top
        k = 1 - t * (1 - taper)
        for j in range(3):
            if j != ax:
                p[:, j] *= k
        n = _flat_normals(p) if shape in ("box", "spike") else n
        if shape in ("cyl", "cylx", "cylz"):          # tilt the side normals by the cone slope
            rr = s[[j for j in range(3) if j != ax]].mean() / 2
            slope = rr * (1 - taper) / max(s[ax], 1e-9)
            side = np.abs(n[:, ax]) < 0.5
            n = n.copy()
            n[side, ax] = slope
            n /= np.linalg.norm(n, axis=1, keepdims=True)
    R = opt.get("R")
    if R is not None:
        R = np.asarray(R, float)
        p, n = p @ R.T, n @ R.T
    return p + np.asarray(c, float), n


def build_mesh(key: str, pieces, colors: dict) -> dict:
    """Pieces [(shape, centre, size[, colour key or rgb[, opt]])] -> a cached mesh (vertex colours baked); returns its
    info. See piece_tris for the shapes and options."""
    P, N, C = [], [], []
    for pc in pieces:
        shape, c, s = pc[:3]
        ck = pc[3] if len(pc) > 3 else "main"
        col = tuple(ck) if isinstance(ck, (tuple, list)) else colors.get(ck, colors.get("main", (200, 200, 200)))
        p, n = piece_tris(shape, c, s, pc[4] if len(pc) > 4 else None)
        P.append(p); N.append(n)
        C.append(np.tile(np.array(list(col)[:3] + [255], np.uint8), (len(p), 1)))
    P, N, C = np.concatenate(P), np.concatenate(N), np.concatenate(C)
    lo, hi = P.min(0), P.max(0)
    faces = np.arange(len(P), dtype=np.uint32).reshape(-1, 3)
    np.savez(MC.OUT / f"{key}.npz", pos=P.astype("f4"), nrm=N.astype("f4"), uv=np.zeros((len(P), 2), "f4"), faces=faces,
             lo=lo, hi=hi, rgba=C)
    return {"key": key, "centre": ((lo + hi) / 2).tolist(), "size": (hi - lo).tolist()}


# -------------------------------------------------------------------------------------------------- looks
SKIN = {"light": (255, 214, 170), "fair": (245, 200, 160), "tan": (214, 160, 110), "brown": (160, 110, 72),
        "dark": (110, 74, 48)}
HAIRC = {"brown": (92, 58, 34), "black": (28, 24, 26), "blonde": (226, 186, 100), "red": (176, 76, 40),
         "white": (232, 232, 236), "grey": (160, 160, 166), "pink": (240, 130, 180)}

LOOKS = {
    "c_timmy": dict(skin="fair", hair=("bangs", "brown"), hat=("beanie", (210, 40, 40)),
                    shirt=dict(kind="tee", pattern="plaid", color=(40, 70, 200), accent=(20, 20, 40), under=(60, 190, 230), sleeve="short"),
                    pants=dict(kind="jeans", color=(40, 60, 110))),
    "timmy": dict(skin="fair", hair=("bangs", "brown"), hat=("beanie", (210, 40, 40)),
                  shirt=dict(kind="tee", color=(60, 160, 230), sleeve="short"), pants=dict(kind="jeans", color=(40, 60, 110))),
    "c_preston": dict(skin="light", hair=("short", "black"), extras=["mustache_white"],
                      shirt=dict(kind="suit", color=(225, 180, 40), tie=(200, 150, 20)), pants=dict(color=(220, 175, 40), belt=(150, 110, 20))),
    "c_kid": dict(skin="brown", hair=("short", "black"), shirt=dict(kind="tee", color=(40, 150, 70), sleeve="short", logo=8),
                  pants=dict(kind="jeans", color=(50, 70, 130))),
    "c_man": dict(skin="tan", hair=("short", "brown"), shirt=dict(kind="tee", pattern="plaid", color=(90, 110, 60), accent=(40, 50, 30), under=(240, 240, 240)),
                  pants=dict(kind="jeans", color=(50, 60, 90))),
    "c_lady": dict(skin="light", hair=("long", "brown"), extras=["glasses"], shirt=dict(kind="cardigan", color=(150, 150, 165), under=(250, 250, 250)),
                   pants=dict(color=(40, 40, 50))),
    "c_mom": dict(skin="fair", hair=("ponytail", "blonde"), shirt=dict(kind="tee", color=(240, 120, 150), sleeve="short"),
                  pants=dict(kind="jeans", color=(60, 80, 140))),
    "officer": dict(skin="brown", hair=("buzz", "black"), hat=("police", (28, 42, 92)),
                    shirt=dict(kind="uniform", color=(28, 42, 92)), pants=dict(color=(20, 24, 40))),
    "c_police": dict(skin="tan", hair=("buzz", "black"), hat=("police", (28, 42, 92)),
                     shirt=dict(kind="uniform", color=(28, 42, 92)), pants=dict(color=(20, 24, 40))),
    "c_butler": dict(skin="light", hair=("short", "grey"), shirt=dict(kind="suit", color=(25, 25, 30), tie=(25, 25, 30)),
                     pants=dict(color=(25, 25, 30))),
    "lee": dict(skin="tan", hair=("spiky", "black"), shirt=dict(kind="hoodie", color=(200, 70, 60)), pants=dict(color=(50, 50, 55))),
    "c_grandpa": dict(skin="fair", hair=("buzz", "white"), extras=["glasses", "mustache_white"],
                      shirt=dict(kind="cardigan", color=(140, 110, 80), under=(230, 225, 210)), pants=dict(color=(90, 80, 70))),
    "c_girl": dict(skin="tan", hair=("pigtails", "black"), hat=("bow", (240, 90, 150)),
                   shirt=dict(kind="tee", color=(250, 210, 230), sleeve="short", logo="heart", logo_color=(240, 90, 150)),
                   pants=dict(kind="skirt", color=(240, 120, 170))),
    "yellow": dict(skin="light", hair=("short", "brown"), shirt=dict(color=(230, 190, 40)), pants=dict(color=(50, 70, 140))),
    "red": dict(skin="light", hair=("short", "black"), shirt=dict(color=(190, 40, 40)), pants=dict(color=(40, 40, 60))),
    "green": dict(skin="brown", hair=("short", "black"), shirt=dict(color=(40, 150, 80)), pants=dict(color=(60, 50, 40))),
    "mannequin": dict(skin=(235, 235, 235), hair=("bald", "white"), shirt=dict(color=(235, 235, 235)), pants=dict(color=(235, 235, 235))),
    "mannequin2": dict(skin=(210, 200, 190), hair=("bald", "white"), shirt=dict(color=(210, 200, 190)), pants=dict(color=(210, 200, 190))),
    "c_worker": dict(skin="tan", hair=("short", "brown"), hat=("hardhat", (250, 200, 30)),
                     shirt=dict(kind="vest", color=(90, 110, 150), accent=(255, 140, 0)), pants=dict(kind="jeans", color=(50, 60, 90))),
    "c_king": dict(skin="fair", hair=("short", "red"), hat=("crown", (240, 200, 60)), extras=["beard_red"],
                   shirt=dict(kind="robe", color=(150, 30, 50)), pants=dict(color=(110, 20, 40))),
    "c_chef": dict(skin="light", hair=("short", "black"), hat=("chef", (250, 250, 250)), shirt=dict(kind="chef", color=(250, 250, 250)),
                   pants=dict(color=(40, 40, 45))),
    "wendy": dict(skin="fair", hair=("pigtails", "red"), shirt=dict(kind="tee", color=(80, 140, 220), pattern="polka", accent=(255, 255, 255)),
                  pants=dict(kind="skirt", color=(40, 60, 130))),
    "tedd": dict(skin="brown", hair=("afro", "black"), shirt=dict(kind="tee", pattern="stripes", color=(250, 250, 250), accent=(40, 120, 200)),
                 pants=dict(kind="shorts", color=(150, 120, 80))),
    "marilyn": dict(skin="light", hair=("long", "blonde"), shirt=dict(kind="tee", color=(240, 240, 240), sleeve="none"),
                    pants=dict(kind="dress", color=(220, 50, 70))),
    "c_teacher": dict(skin="tan", hair=("bun", "brown"), extras=["glasses"], shirt=dict(kind="cardigan", color=(90, 130, 110), under=(245, 240, 230)),
                      pants=dict(kind="skirt", color=(60, 60, 70))),
    "c_nerd": dict(skin="fair", hair=("short", "blonde"), extras=["glasses"],
                   shirt=dict(kind="tee", pattern="stripes", color=(240, 240, 200), accent=(80, 120, 60), collar=(250, 250, 250)),
                   pants=dict(color=(140, 110, 70))),
    "c_grandma": dict(skin="fair", hair=("bun", "white"), extras=["glasses"],
                      shirt=dict(kind="tee", pattern="floral", color=(80, 70, 120), accent=(230, 110, 130)),
                      pants=dict(kind="dress", color=(80, 70, 120), pattern="floral", accent=(230, 110, 130))),
    "c_businessman": dict(skin="light", hair=("short", "brown"), shirt=dict(kind="suit", color=(90, 95, 105), tie=(40, 80, 160)),
                          pants=dict(color=(85, 90, 100))),
}


def _resolve(name: str) -> dict:
    """A look by name; names with no hand-made entry get a deterministic outfit from the name."""
    if name in LOOKS:
        return LOOKS[name]
    h = int(hashlib.sha1(name.encode()).hexdigest(), 16)
    skins, hairs, hairc = list(SKIN), ["short", "bangs", "long", "ponytail", "spiky", "bun", "buzz"], list(HAIRC)
    pal = [(200, 60, 60), (60, 130, 210), (60, 170, 90), (240, 190, 60), (150, 80, 180), (240, 130, 60), (90, 90, 100)]
    return dict(skin=skins[h % len(skins)], hair=(hairs[(h >> 4) % len(hairs)], hairc[(h >> 8) % len(hairc)]),
                shirt=dict(kind=["tee", "hoodie", "tee"][(h >> 12) % 3], pattern=["solid", "stripes", "plaid"][(h >> 14) % 3],
                           color=pal[(h >> 16) % len(pal)], accent=pal[(h >> 20) % len(pal)], sleeve=["short", "long"][(h >> 24) % 2]),
                pants=dict(kind=["jeans", "trousers", "shorts"][(h >> 26) % 3], color=pal[(h >> 28) % len(pal)]))


HEAD_SPEC = {"kind": "box", "size": [2, 1, 1], "mesh": {"special": {"type": "Head", "scale": [1.25, 1.25, 1.25],
                                                                     "offset": [0, 0, 0], "id": "", "tex": ""}}}


def make_look(name: str) -> dict:
    spec = _resolve(name)
    seed = int(hashlib.sha1(name.encode()).hexdigest()[:8], 16)
    skin = spec["skin"] if isinstance(spec["skin"], tuple) else SKIN[spec["skin"]]
    TEXO.mkdir(parents=True, exist_ok=True)
    sh_p, pa_p = TEXO / f"{name}_shirt.png", TEXO / f"{name}_pants.png"
    shirt(spec["shirt"], seed).save(sh_p)
    pants(spec["pants"], seed + 1).save(pa_p)
    col = [v / 255 for v in skin]
    body = {}
    for bp, size in (("Torso", [2, 2, 1]), ("Head", [2, 1, 1]), ("Left Arm", [1, 2, 1]), ("Right Arm", [1, 2, 1]),
                     ("Left Leg", [1, 2, 1]), ("Right Leg", [1, 2, 1])):
        d = dict(HEAD_SPEC) if bp == "Head" else {"kind": "box", "size": size}
        d.update(name=bp, color=col, mat="SmoothPlastic", tr=0.0, cf=None)
        body[bp] = d
    acc = []

    def add(key, pieces, colors):
        info = build_mesh(key, pieces, colors)
        acc.append({"kind": "mesh", "name": key, "color": [1, 1, 1], "mat": "SmoothPlastic", "tr": 0.0, "host": "Head",
                    "size": info["size"], "mesh": {"key": key, "vcol": True},
                    "rel": [*info["centre"], 1, 0, 0, 0, 1, 0, 0, 0, 1]})

    style, hc = spec["hair"]
    hcol = HAIRC[hc] if isinstance(hc, str) else hc
    if HAIR.get(style):
        add(f"own_hair_{style}_{hc}", HAIR[style], {"main": hcol})
    if spec.get("hat"):
        hs, hcolr = spec["hat"]
        add(f"own_hat_{hs}_{'_'.join(map(str, hcolr))}", HATS[hs],
            {"main": hcolr, "dark": shade(hcolr, 0.7), "gold": (240, 200, 60)})
    for ex in spec.get("extras", []):
        if ex == "glasses":
            add("own_glasses", GLASSES, {"main": (20, 20, 24)})
        elif ex.startswith("mustache"):
            c = HAIRC.get(ex.split("_")[1], (30, 30, 30))
            add(f"own_mustache_{ex.split('_')[1]}", MUSTACHE, {"main": c})
        elif ex.startswith("beard"):
            c = HAIRC.get(ex.split("_")[1], (30, 30, 30))
            add(f"own_beard_{ex.split('_')[1]}", BEARD, {"main": c})
    return {"actor": name, "shirt": "file:" + str(sh_p), "pants": "file:" + str(pa_p), "tee": "", "body": body,
            "acc": acc, "arms": 0.85, "own": True}   # critic: held half-raised arms read stiff; act with the arms


def build(names=None) -> dict:
    import cast as CAST     # the look names every episode casts
    names = sorted(set(names or []) | set(LOOKS) | set(getattr(CAST, "LOOKS", {})))
    looks = {n: make_look(n) for n in names}
    OWN.mkdir(parents=True, exist_ok=True)
    (OWN / "looks.json").write_text(json.dumps(looks))
    # meshes go into the cache index so the renderer finds them
    idx_p = MC.OUT / "index.json"
    idx = json.loads(idx_p.read_text())
    for p in MC.OUT.glob("own_*.npz"):
        z = np.load(p)
        idx[p.stem] = {"size": (z["hi"] - z["lo"]).tolist(), "centre": ((z["hi"] + z["lo"]) / 2).tolist(),
                       "verts": int(len(z["pos"])), "tris": int(len(z["faces"])), "own": True}
    idx_p.write_text(json.dumps(idx))
    return looks


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "demo" / "episodes"))
    r = build()
    print(len(r), "looks ->", OWN)
