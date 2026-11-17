"""Our own props and sets (IP-clean, no Creator Store models, no internet textures): every prop and set piece is built
from boxes, spheres, cylinders and wedges with vertex colours (own_assets.build_mesh) plus our procedural materials.
Style: bright, colourful, clean, blocky-but-polished.

    python roblox/headless/own_sets.py            # props + sets + blocking maps + preview sheets
    python roblox/headless/own_sets.py --no-render

Writes, under <cache>/own (cache = PROMPTIMATE_HEADLESS_CACHE, default D:\\tmp\\headless):
    props.json              {key: {size, parts}} like lib/props.json: parts relative to the pivot (bottom centre),
                            the front faces -Z
    sets/<Set>.json         {"parts": [...], "light": {...}, "floor_y", "bounds", "spots"}: world coordinates, one
                            self-contained lot per set at x = 6000, 6200, ... (z = 0)
    scene_static.json       every set combined, in the static.json format
    sets/maps/<Set>.png     writer-facing top-down blocking map (green open floor, yellow under low furniture, red tall
                            obstacles; ticks every 5 studs); sets/maps/<Set>.json: floor height + named spots
    sets_preview.jpg, props_preview.jpg   render checks

Conventions: studs; yaw in degrees as PLACE / CAST use it (0 = the front faces -Z, 90 = faces -X, 180 = faces +Z).
Interiors are closed boxes (four walls + ceiling) whose walls, ceilings and everything mounted on them carry
"wall": true and a "cutgroup": the renderer drops a whole wall (with its windows, frames, pictures, baseboards) when it
stands between the camera and its target, as Studio's cutaway did. Walls and ceilings cast no shadow ("cast": false),
so rooms stay sunlit and bright. The ceiling is a mesh part (not a box), so director.ground_y never puts props on it.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import meshcache as MC  # noqa: E402
import own_assets as OA  # noqa: E402

OWN = MC.OUT.parent / "own"
SETS_DIR = OWN / "sets"
MAPS_DIR = SETS_DIR / "maps"
PREVIEW_DIR = OWN / "preview"
STATIC_SRC = MC.OUT.parent / "scene" / "static.json"
DEFAULT_LIGHT = {"sun": [-0.8731, 0.4449, 0.1994], "ambient": [0.549, 0.525, 0.557], "outdoor": [0.47, 0.47, 0.53],
                 "brightness": 2.6, "exposure": 0.1}
I3 = [1, 0, 0, 0, 1, 0, 0, 0, 1]
LOT_ROT = 90.0          # every lot is turned so its back wall faces the sun (see Lot)


# ------------------------------------------------------------------------------------------------- colours
def hx(s: str):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


WOOD, WOOD_D, WOOD_L, WOOD_R = hx("b97a48"), hx("7a4e2e"), hx("dcb07a"), hx("a0522d")
WHITE, CREAM, OFFW = hx("f6f6f2"), hx("faecce"), hx("e8e4dc")
RED, RED_D, PINK, PINK_L = hx("e04848"), hx("a83030"), hx("f58cb4"), hx("fbc4d8")
BLUE, BLUE_D, BLUE_L, SKY = hx("3c82dc"), hx("28508c"), hx("8cc0f0"), hx("a8d8fa")
TEAL, MINT, GREEN, GREEN_D, LIME = hx("3cbeb4"), hx("aee6d2"), hx("50b45a"), hx("2f7a3c"), hx("a0d250")
YEL, GOLD, GOLD_D, ORANGE = hx("fad23c"), hx("f0c43c"), hx("c8962a"), hx("f5963c")
PURPLE, LILAC = hx("965ac8"), hx("c8b4f0")
GREY, GREY_D, GREY_L, DARK, BLACK = hx("969ba5"), hx("5a5f69"), hx("c8ccd2"), hx("34363c"), hx("1e1e22")
METAL, GLASS_C, TERRA, BROWN = hx("b9bec6"), hx("aadcff"), hx("d26e46"), hx("6e4628")
BOOK_COLS = [RED, BLUE, GREEN, YEL, PURPLE, ORANGE, TEAL, PINK, hx("2a6e9e"), hx("8e3a3a"), CREAM]


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def lit(c, k):
    return tuple(int(max(0, min(255, v * k))) for v in c)


# ------------------------------------------------------------------------------------------------- maths
def Rx(d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def Ry(d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def Rz(d):
    a = math.radians(d); c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


# ---------------------------------------------------------------------------------- pieces (bottom-based)
def _o(o):
    return o or None


def bx(x, y0, z, w, h, d, c, **o):
    """A box whose bottom is at y0."""
    return ("box", (x, y0 + h / 2, z), (w, h, d), c, _o(o))


def bc(x, y, z, w, h, d, c, **o):
    """A box by its centre."""
    return ("box", (x, y, z), (w, h, d), c, _o(o))


def cy(x, y0, z, dia, h, c, d=None, **o):
    """An upright cylinder (bottom at y0); taper= scales its top (cones, flares)."""
    return ("cyl", (x, y0 + h / 2, z), (dia, h, d or dia), c, _o(o))


def cx(x, y, z, length, dia, c, **o):
    """A cylinder along X, by its centre."""
    return ("cylx", (x, y, z), (length, dia, dia), c, _o(o))


def cz(x, y, z, length, dia, c, **o):
    """A cylinder along Z (a disc facing -Z), by its centre."""
    return ("cylz", (x, y, z), (dia, dia, length), c, _o(o))


def bl(x, y, z, w, h, d, c, **o):
    """A ball / ellipsoid by its centre."""
    return ("ball", (x, y, z), (w, h, d), c, _o(o))


def wg(x, y0, z, w, h, d, c, **o):
    """A wedge (bottom at y0): high edge at +Z, the slope faces -Z (rotate with R= for other directions)."""
    return ("wedge", (x, y0 + h / 2, z), (w, h, d), c, _o(o))


def sp(x, y0, z, w, h, d, c, **o):
    return ("spike", (x, y0 + h / 2, z), (w, h, d), c, _o(o))


def rod(p0, p1, t, c, shape="box"):
    """A bar from p0 to p1 (thickness t): a box (or cylinder) whose Y axis runs along the bar."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    d = p1 - p0
    L = float(np.linalg.norm(d))
    y = d / L
    ref = np.array([1.0, 0, 0]) if abs(y[0]) < 0.9 else np.array([0, 0, 1.0])
    x = np.cross(y, ref); x /= np.linalg.norm(x)
    z = np.cross(x, y)
    R = np.stack([x, y, z], 1)
    kind = "cyl" if shape == "cyl" else "box"
    return (kind, tuple((p0 + p1) / 2), (t, L, t), c, {"R": R})


def G(mat, pieces, tr=0.0):
    """One mesh part of a prop: pieces sharing a material (and transparency)."""
    return {"mat": mat, "tr": tr, "pieces": [p for p in pieces if p is not None]}


# ------------------------------------------------------------------------------------------- pixel text
FONT = {  # 3x5 glyphs, rows top -> bottom
    "A": ["010", "101", "111", "101", "101"], "B": ["110", "101", "110", "101", "110"], "C": ["011", "100", "100", "100", "011"],
    "D": ["110", "101", "101", "101", "110"], "E": ["111", "100", "110", "100", "111"], "F": ["111", "100", "110", "100", "100"],
    "G": ["011", "100", "101", "101", "011"], "H": ["101", "101", "111", "101", "101"], "I": ["111", "010", "010", "010", "111"],
    "K": ["101", "101", "110", "101", "101"], "L": ["100", "100", "100", "100", "111"], "M": ["10001", "11011", "10101", "10001", "10001"],
    "N": ["1001", "1101", "1011", "1001", "1001"], "O": ["010", "101", "101", "101", "010"], "P": ["110", "101", "110", "100", "100"],
    "R": ["110", "101", "110", "101", "101"], "S": ["011", "100", "010", "001", "110"], "T": ["111", "010", "010", "010", "010"],
    "U": ["101", "101", "101", "101", "111"], "V": ["101", "101", "101", "101", "010"], "W": ["10001", "10001", "10101", "11011", "10001"],
    "Y": ["101", "101", "010", "010", "010"], "Z": ["111", "001", "010", "100", "111"], "&": ["010", "101", "010", "101", "011"],
    "$": ["011", "110", "010", "011", "110"], " ": ["000", "000", "000", "000", "000"], "1": ["010", "110", "010", "010", "111"],
    "2": ["110", "001", "010", "100", "111"], "0": ["111", "101", "101", "101", "111"], "!": ["010", "010", "010", "000", "010"],
}


def text_pieces(text, x0, y0, z, px, c, depth=0.12):
    """Pixel letters in the XY plane facing -Z, centred on x0, bottom at y0 (px = pixel size)."""
    glyphs = [FONT.get(ch, FONT[" "]) for ch in text.upper()]
    w = sum(len(g[0]) + 1 for g in glyphs) * px - px
    out, col0 = [], 0
    for g in glyphs:
        for r, row in enumerate(g):
            for k, bit in enumerate(row):
                if bit == "1":
                    # seen from -Z the viewer's right is -X: letters run toward -X
                    x = x0 + w / 2 - (col0 + k) * px - px / 2
                    out.append(bx(x, y0 + (4 - r) * px, z, px * 1.02, px * 1.02, depth, c))
        col0 += len(g[0]) + 1
    return out


# ================================================================================================ PROPS
PROPS: dict = {}


def prop(key):
    def deco(fn):
        PROPS[key] = fn
        return fn
    return deco


@prop("cake")
def _cake():
    p = [cy(0, 0, 0, 1.7, 0.06, WHITE, seg=24), cy(0, 0.06, 0, 1.3, 0.42, PINK, seg=24),
         cy(0, 0.4, 0, 1.36, 0.1, WHITE, seg=24), cy(0, 0.5, 0, 0.9, 0.3, PINK_L, seg=24), cy(0, 0.78, 0, 0.94, 0.07, WHITE, seg=24)]
    for a in range(8):
        t = a * math.pi / 4
        p.append(bl(0.6 * math.cos(t), 0.47, 0.6 * math.sin(t), 0.16, 0.14, 0.16, WHITE))
        p.append(bl(0.36 * math.cos(t + 0.4), 0.88, 0.36 * math.sin(t + 0.4), 0.13, 0.13, 0.13, RED))
    for i, col in enumerate((BLUE, YEL, GREEN)):
        x = (i - 1) * 0.2
        p += [cy(x, 0.85, 0.02, 0.05, 0.22, col), bl(x, 1.12, 0.02, 0.07, 0.1, 0.07, ORANGE)]
    return [G("SmoothPlastic", p)]


@prop("coffee_cup")
def _coffee_cup():
    return [G("SmoothPlastic", [cy(0, 0, 0, 0.8, 0.05, WHITE, seg=20), cy(0, 0.05, 0, 0.44, 0.44, RED, taper=1.18, seg=20),
                               cy(0, 0.47, 0, 0.47, 0.03, BROWN, seg=20), bx(0.33, 0.14, 0, 0.08, 0.26, 0.08, RED),
                               bx(0.27, 0.36, 0, 0.16, 0.07, 0.08, RED), bx(0.27, 0.13, 0, 0.16, 0.07, 0.08, RED)])]


@prop("gift_box")
def _gift_box():
    return [G("SmoothPlastic", [bx(0, 0, 0, 1.2, 0.95, 1.2, RED), bx(0, 0.92, 0, 1.32, 0.26, 1.32, lit(RED, 1.1)),
                               bx(0, 0, 0, 0.22, 1.2, 1.34, YEL), bx(0, 0, 0, 1.34, 1.2, 0.22, YEL),
                               bl(-0.24, 1.32, 0, 0.46, 0.26, 0.28, YEL, R=Rz(-20)), bl(0.24, 1.32, 0, 0.46, 0.26, 0.28, YEL, R=Rz(20)),
                               bl(0, 1.27, 0, 0.18, 0.16, 0.2, GOLD)])]


@prop("crown")
def _crown():
    p = [cy(0, 0, 0, 1.1, 0.42, GOLD, seg=16), cy(0, 0.05, 0, 1.0, 0.5, RED_D, seg=16)]
    for k in range(8):
        a = k * math.pi / 4
        x, z = 0.5 * math.sin(a), -0.5 * math.cos(a)
        p += [sp(x, 0.4, z, 0.24, 0.38, 0.24, GOLD, R=Ry(-math.degrees(a))), bl(x, 0.82, z, 0.11, 0.11, 0.11, GOLD)]
        p.append(bl(0.56 * math.sin(a + 0.39), 0.2, -0.56 * math.cos(a + 0.39), 0.14, 0.14, 0.08, [RED, BLUE, GREEN, BLUE][k % 4],
                    R=Ry(-math.degrees(a + 0.39))))
    return [G("SmoothPlastic", p)]


@prop("phone")
def _phone():
    return [G("SmoothPlastic", [bx(0, 0, 0, 0.29, 0.55, 0.05, BLACK), bx(0, 0.035, -0.027, 0.25, 0.48, 0.006, hx("4aa0f0")),
                               bx(0, 0.43, -0.031, 0.21, 0.04, 0.004, WHITE), bx(-0.06, 0.1, -0.031, 0.05, 0.05, 0.004, YEL),
                               bx(0.02, 0.1, -0.031, 0.05, 0.05, 0.004, GREEN), bx(0.09, 0.1, -0.031, 0.05, 0.05, 0.004, PINK),
                               bx(0.08, 0.46, 0.027, 0.07, 0.07, 0.006, GREY_D)])]


@prop("laptop")
def _laptop():
    hinge = np.array([0, 0.07, 0.48])
    R = Rx(-14)          # the lid leans back (its top toward +Z)
    lid_c = hinge + R @ np.array([0, 0.44, 0.03])
    scr_c = hinge + R @ np.array([0, 0.46, -0.005])
    logo_c = hinge + R @ np.array([0, 0.48, 0.06])
    return [G("SmoothPlastic", [bx(0, 0, 0, 1.4, 0.07, 1.0, METAL), bx(0, 0.07, -0.05, 1.22, 0.008, 0.5, DARK),
                               bx(0, 0.07, -0.38, 0.45, 0.006, 0.2, GREY_L),
                               ("box", tuple(lid_c), (1.4, 0.88, 0.05), METAL, {"R": R}),
                               ("box", tuple(scr_c), (1.28, 0.76, 0.01), hx("3c78c8"), {"R": R}),
                               ("box", tuple(logo_c), (0.16, 0.16, 0.01), WHITE, {"R": R})])]


@prop("books")
def _books():
    p, y = [], 0.0
    spec = [(1.5, 0.24, 1.05, RED, 4), (1.4, 0.2, 1.0, BLUE, -6), (1.45, 0.22, 0.95, GREEN, 3), (1.3, 0.18, 0.9, YEL, -3),
            (1.2, 0.16, 0.85, PURPLE, 8)]
    for w, h, d, c, rot in spec:
        R = Ry(rot)
        p.append(("box", (0, y + h / 2, 0), (w, h, d), c, {"R": R}))
        p.append(("box", tuple(R @ np.array([0.05, 0, -0.03]) + [0, y + h / 2, 0]), (w - 0.05, h - 0.06, d - 0.03), CREAM, {"R": R}))
        y += h
    return [G("SmoothPlastic", p)]


@prop("piggy_bank")
def _piggy():
    return [G("SmoothPlastic", [bl(0, 0.68, 0.02, 1.05, 0.92, 1.3, PINK), cz(0, 0.66, -0.66, 0.2, 0.4, lit(PINK, 0.88)),
                               bx(-0.07, 0.62, -0.77, 0.06, 0.1, 0.02, RED_D), bx(0.07, 0.62, -0.77, 0.06, 0.1, 0.02, RED_D),
                               bl(-0.22, 0.88, -0.5, 0.1, 0.12, 0.08, BLACK), bl(0.22, 0.88, -0.5, 0.1, 0.12, 0.08, BLACK),
                               sp(-0.27, 1.02, -0.25, 0.22, 0.24, 0.12, lit(PINK, 0.88)), sp(0.27, 1.02, -0.25, 0.22, 0.24, 0.12, lit(PINK, 0.88)),
                               cy(-0.27, 0, -0.33, 0.24, 0.35, lit(PINK, 0.9)), cy(0.27, 0, -0.33, 0.24, 0.35, lit(PINK, 0.9)),
                               cy(-0.27, 0, 0.38, 0.24, 0.35, lit(PINK, 0.9)), cy(0.27, 0, 0.38, 0.24, 0.35, lit(PINK, 0.9)),
                               bl(0, 0.78, 0.68, 0.12, 0.12, 0.12, lit(PINK, 0.9)), bx(0, 1.1, 0.05, 0.36, 0.04, 0.08, DARK)])]


@prop("coin_pile")
def _coin_pile():
    p = [bl(0, 0.22, 0, 1.7, 0.44, 1.5, GOLD_D, seg=16)]
    rng = np.random.default_rng(3)
    for x, z, n in ((-0.4, -0.2, 9), (0.35, -0.25, 7), (0.05, 0.3, 11), (-0.55, 0.35, 5), (0.6, 0.3, 4)):
        for i in range(n):
            p.append(cy(x + rng.normal(0, 0.015), 0.2 + i * 0.075, z + rng.normal(0, 0.015), 0.5, 0.07,
                        GOLD if i % 2 == 0 else lit(GOLD, 0.9), seg=16))
    for a in range(10):
        t = a * 0.63
        p.append(cy(0.72 * math.cos(t), 0.04, 0.65 * math.sin(t), 0.45, 0.06, GOLD, seg=14, R=Rx(rng.uniform(-20, 20))))
    return [G("SmoothPlastic", p)]


@prop("cash_stack")
def _cash_stack():
    p = []
    for layer in range(3):
        for i, (x, z) in enumerate(((-0.33, -0.3), (0.33, -0.3), (-0.33, 0.3), (0.33, 0.3))):
            if layer == 2 and i > 1:
                continue
            y = layer * 0.19
            rot = (layer * 7 + i * 5) % 13 - 6
            R = Ry(rot)
            p.append(("box", (x, y + 0.09, z), (0.62, 0.18, 0.55), hx("78be6e"), {"R": R}))
            p.append(("box", (x, y + 0.09, z), (0.16, 0.185, 0.56), hx("f0f5dc"), {"R": R}))
    return [G("SmoothPlastic", p)]


@prop("gold_bars")
def _gold_bars():
    p = []
    for layer, n in enumerate((3, 2, 1)):
        for i in range(n):
            x = (i - (n - 1) / 2) * 0.62
            for z in ((-0.3, 0.3) if layer < 2 else (0,)):
                p.append(("box", (x, layer * 0.34 + 0.17, z), (0.58, 0.34, 0.55), GOLD if (i + layer) % 2 else lit(GOLD, 1.06),
                          {"taper": 0.78}))
    return [G("SmoothPlastic", p)]


@prop("trophy")
def _trophy():
    return [G("SmoothPlastic", [bx(0, 0, 0, 0.95, 0.28, 0.95, WOOD_D), bx(0, 0.28, 0, 0.72, 0.2, 0.72, BLACK),
                               bx(0, 0.06, -0.48, 0.5, 0.16, 0.02, GOLD), cy(0, 0.48, 0, 0.2, 0.32, GOLD),
                               bl(0, 0.82, 0, 0.34, 0.16, 0.34, GOLD), bl(0, 0.96, 0, 0.62, 0.36, 0.62, GOLD),
                               cy(0, 0.96, 0, 0.62, 0.58, GOLD, taper=1.3), cy(0, 1.5, 0, 0.84, 0.08, lit(GOLD, 1.08)),
                               bx(-0.52, 1.0, 0, 0.1, 0.42, 0.1, GOLD), bx(0.52, 1.0, 0, 0.1, 0.42, 0.1, GOLD),
                               bx(-0.45, 1.38, 0, 0.22, 0.09, 0.1, GOLD), bx(0.45, 1.38, 0, 0.22, 0.09, 0.1, GOLD),
                               bx(-0.45, 0.96, 0, 0.2, 0.09, 0.1, GOLD), bx(0.45, 0.96, 0, 0.2, 0.09, 0.1, GOLD),
                               sp(0, 1.12, -0.33, 0.22, 0.22, 0.04, WHITE, taper=0.1)])]


@prop("photo_frame")
def _photo_frame():
    return [G("SmoothPlastic", [bx(0, 0, 0, 1.0, 1.2, 0.1, GOLD_D), bx(0, 0.55, -0.055, 0.78, 0.53, 0.02, SKY),
                               bx(0, 0.12, -0.055, 0.78, 0.45, 0.02, LIME), sp(-0.12, 0.5, -0.07, 0.4, 0.35, 0.01, GREEN_D, taper=0.05),
                               bl(0.22, 0.85, -0.07, 0.14, 0.14, 0.02, YEL), bx(0, 0, 0.25, 0.1, 0.95, 0.07, GOLD_D, R=Rx(-25))])]


@prop("cash_register")
def _cash_register():
    return [G("SmoothPlastic", [bx(0, 0, 0, 1.6, 0.34, 1.4, DARK), bx(0, 0.06, -0.71, 1.4, 0.22, 0.03, GREY_D),
                               bx(0, 0.34, 0.12, 1.6, 0.36, 1.16, TEAL), wg(0, 0.34, -0.42, 1.5, 0.36, 0.56, lit(TEAL, 0.9)),
                               *[bx(-0.45 + 0.3 * (i % 4), 0.5 + 0.06 * (i // 4), -0.52 + 0.14 * (i // 4), 0.2, 0.05, 0.1,
                                    [WHITE, WHITE, WHITE, RED, WHITE, WHITE, WHITE, GREEN][i]) for i in range(8)],
                               bx(0.2, 0.7, 0.45, 0.14, 0.3, 0.14, GREY_D), bx(0.2, 0.98, 0.45, 0.9, 0.32, 0.12, GREY_D),
                               bx(0.2, 1.01, 0.38, 0.78, 0.24, 0.02, hx("78f0b4")), cy(-0.5, 0.7, 0.4, 0.3, 0.28, WHITE, d=0.4)])]


@prop("backpack")
def _backpack():
    c = hx("e65a3c")
    return [G("Fabric", [bx(0, 0, 0, 1.3, 1.5, 0.8, c), ("cylx", (0, 1.5, 0), (1.3, 0.6, 0.8), c, None),
                        bx(0, 0.15, -0.46, 1.0, 0.75, 0.2, lit(c, 0.85)), bx(0, 0.82, -0.57, 0.9, 0.05, 0.04, YEL),
                        bx(-0.36, 0.25, 0.44, 0.18, 1.3, 0.1, DARK), bx(0.36, 0.25, 0.44, 0.18, 1.3, 0.1, DARK),
                        bx(0, 1.75, 0.1, 0.4, 0.08, 0.12, DARK), bx(-0.68, 0.3, 0, 0.12, 0.6, 0.5, lit(c, 0.85)),
                        bx(0.68, 0.3, 0, 0.12, 0.6, 0.5, lit(c, 0.85))])]


@prop("pizza")
def _pizza():
    p = [cy(0, 0, 0, 2.7, 0.1, WOOD_L, seg=28), cy(0, 0.1, 0, 2.3, 0.16, hx("e6aa5a"), seg=28),
         cy(0, 0.16, 0, 2.05, 0.12, RED, seg=28), cy(0, 0.2, 0, 1.95, 0.1, hx("ffd75a"), seg=28)]
    for k, (r, a) in enumerate(((0.0, 0), (0.6, 0.3), (0.6, 1.6), (0.6, 2.9), (0.6, 4.2), (0.62, 5.4), (0.32, 2.2), (0.32, 4.9))):
        p.append(cy(r * math.cos(a), 0.29, r * math.sin(a), 0.36, 0.05, hx("b4322d"), seg=16))
    for a in (0.9, 2.5, 3.7, 5.0):
        p.append(bx(0.85 * math.cos(a), 0.3, 0.85 * math.sin(a), 0.16, 0.03, 0.1, GREEN_D, R=Ry(math.degrees(a))))
    return [G("SmoothPlastic", p)]


@prop("newspaper")
def _newspaper():
    p = [bx(0, 0, 0, 1.6, 0.08, 1.1, hx("ebe8de")), bx(0, 0.08, -0.36, 1.35, 0.01, 0.2, DARK),
         bx(0.35, 0.08, 0.05, 0.6, 0.01, 0.45, GREY)]
    for i in range(6):
        p.append(bx(-0.35, 0.08, -0.12 + i * 0.09, 0.6, 0.006, 0.04, GREY_D))
    for i in range(3):
        p.append(bx(0.35, 0.08, 0.36 + i * 0.07, 0.6, 0.006, 0.035, GREY_D))
    return [G("SmoothPlastic", p)]


@prop("umbrella")
def _umbrella():
    return [G("SmoothPlastic", [cy(0, 2.05, 0, 3.5, 0.18, WHITE, seg=8), cy(0, 2.2, 0, 3.4, 0.75, RED, seg=8, taper=0.1),
                               bl(0, 3.0, 0, 0.14, 0.2, 0.14, WHITE), cy(0, 0.25, 0, 0.1, 2.8, GREY_D),
                               bx(0.12, 0, 0, 0.34, 0.1, 0.1, BLACK), bx(0.27, 0, 0, 0.1, 0.32, 0.1, BLACK)])]


@prop("clock")
def _clock():
    p = [cz(0, 1.0, 0, 0.3, 2.0, RED, seg=28), cz(0, 1.0, -0.12, 0.1, 1.72, WHITE, seg=28)]
    for k in range(12):
        a = k * math.pi / 6
        big = k % 3 == 0
        p.append(bc(0.7 * math.sin(a), 1.0 + 0.7 * math.cos(a), -0.18, 0.08 if big else 0.05, 0.2 if big else 0.1, 0.03, DARK,
                    R=Rz(-math.degrees(a))))
    p += [bc(0.17, 1.17, -0.2, 0.08, 0.5, 0.03, BLACK, R=Rz(-45)), bc(0, 1.3, -0.22, 0.05, 0.62, 0.03, BLACK),
          cz(0, 1.0, -0.23, 0.05, 0.12, RED)]
    return [G("SmoothPlastic", p)]


@prop("sign_board")
def _sign_board():
    return [G("Wood", [bx(-2.0, 0, 0.05, 0.32, 5.9, 0.32, WOOD_D), bx(2.0, 0, 0.05, 0.32, 5.9, 0.32, WOOD_D),
                       bx(0, 5.9, 0.05, 4.6, 0.15, 0.45, WOOD_D)]),
            G("SmoothPlastic", [bx(0, 3.2, -0.15, 4.4, 2.6, 0.2, RED), bx(0, 3.4, -0.26, 4.0, 2.2, 0.04, CREAM),
                                bx(0, 4.85, -0.29, 3.2, 0.36, 0.02, BLUE), bx(0, 4.25, -0.29, 3.4, 0.16, 0.02, GREY_D),
                                bx(0, 3.95, -0.29, 2.8, 0.16, 0.02, GREY_D), bx(0, 3.65, -0.29, 3.2, 0.16, 0.02, GREY_D)])]


@prop("tv")
def _tv():
    return [G("Wood", [bx(0, 0.25, 0, 6.6, 1.55, 1.8, WOOD), bx(-3.0, 0, -0.6, 0.3, 0.25, 0.3, WOOD_D), bx(3.0, 0, -0.6, 0.3, 0.25, 0.3, WOOD_D),
                       bx(-3.0, 0, 0.6, 0.3, 0.25, 0.3, WOOD_D), bx(3.0, 0, 0.6, 0.3, 0.25, 0.3, WOOD_D)]),
            G("SmoothPlastic", [bx(-1.65, 0.45, -0.91, 3.0, 1.15, 0.04, WOOD_L), bx(1.65, 0.45, -0.91, 3.0, 1.15, 0.04, WOOD_L),
                                bx(-0.4, 1.0, -0.95, 0.5, 0.08, 0.05, GOLD_D), bx(0.4, 1.0, -0.95, 0.5, 0.08, 0.05, GOLD_D),
                                bx(0, 1.8, 0.2, 1.6, 0.08, 0.8, BLACK), bx(0, 1.88, 0.28, 0.3, 0.45, 0.2, BLACK),
                                bx(0, 2.15, 0.15, 5.5, 2.85, 0.22, BLACK), bx(0, 2.27, 0.03, 5.25, 2.6, 0.02, hx("1e3a6e")),
                                bc(-1.3, 3.9, 0.015, 0.25, 2.2, 0.01, hx("3c5a96"), R=Rz(-35)),
                                bc(-0.8, 3.9, 0.015, 0.12, 2.2, 0.01, hx("3c5a96"), R=Rz(-35))])]


def _sofa_like(width, col, legs=WOOD_D, pillows=(YEL, PINK)):
    n = max(1, round(width / 2.4))
    inner = width - 1.4
    cw = inner / n
    p = [bx(0, 0.45, 0, width, 1.0, 3.1, col), bx(0, 1.45, 1.15, width - 0.6, 1.75, 0.75, col)]
    for i in range(n):
        x = -inner / 2 + cw * (i + 0.5)
        p += [bx(x, 1.45, -0.28, cw - 0.06, 0.5, 2.4, lit(col, 1.1)), bx(x, 1.95, 0.68, cw - 0.08, 1.25, 0.45, lit(col, 1.08))]
    for s in (-1, 1):
        p += [bx(s * (width / 2 - 0.35), 0.45, 0, 0.7, 1.65, 3.1, lit(col, 0.95)), bx(s * (width / 2 - 0.35), 2.1, 0, 0.74, 0.15, 3.14, lit(col, 1.05))]
    if width > 4:
        p += [bc(-(inner / 2 - 0.55), 2.45, 0.35, 0.9, 0.85, 0.3, pillows[0], R=Rz(12) @ Rx(-12)),
              bc(inner / 2 - 0.55, 2.45, 0.35, 0.9, 0.85, 0.3, pillows[1], R=Rz(-12) @ Rx(-12))]
    lg = [cy(s * (width / 2 - 0.3), 0, t * 1.25, 0.3, 0.45, legs) for s in (-1, 1) for t in (-1, 1)]
    return [G("Fabric", p), G("Wood", lg)]


@prop("sofa")
def _sofa():
    return _sofa_like(7.2, hx("3ca0be"))


@prop("armchair")
def _armchair():
    return _sofa_like(3.4, hx("f0a03c"))


@prop("bed")
def _bed():
    return [G("Wood", [bx(0, 0.35, 0, 4.7, 0.75, 7.6, WOOD), bx(0, 0, 3.7, 4.9, 3.0, 0.3, WOOD), bx(0, 0, -3.75, 4.9, 1.6, 0.25, WOOD),
                       bx(0, 2.6, 3.7, 5.0, 0.25, 0.4, WOOD_D), bx(0, 1.35, -3.75, 5.0, 0.25, 0.35, WOOD_D),
                       *[bx(s * 2.2, 0, t * 3.5, 0.4, 0.4, 0.4, WOOD_D) for s in (-1, 1) for t in (-1, 1)]]),
            G("Fabric", [bx(0, 1.1, 0.05, 4.4, 0.65, 7.2, WHITE), bx(0, 1.15, -0.95, 4.56, 0.72, 5.3, hx("5a8ce6")),
                         bx(0, 1.16, 1.75, 4.56, 0.74, 0.55, WHITE), bx(0, 1.18, -0.95, 4.6, 0.12, 5.32, hx("f0d250")),
                         bx(-1.05, 1.72, 2.85, 1.85, 0.5, 1.05, WHITE), bx(1.05, 1.72, 2.85, 1.85, 0.5, 1.05, WHITE)])]


@prop("dining_table")
def _dining_table():
    return [G("Wood", [bx(0, 2.7, 0, 6.2, 0.3, 3.6, WOOD), bx(0, 2.4, 0, 5.7, 0.3, 3.1, WOOD_D),
                       *[bx(s * 2.65, 0, t * 1.35, 0.38, 2.45, 0.38, WOOD_D) for s in (-1, 1) for t in (-1, 1)]]),
            G("Fabric", [bx(0, 3.0, 0, 1.6, 0.02, 3.62, hx("e65a5a"))])]


@prop("chair")
def _chair():
    return [G("Wood", [*[bx(s * 0.72, 0, t * 0.72, 0.24, 1.5, 0.24, WOOD_D) for s in (-1, 1) for t in (-1, 1)],
                       bx(0, 1.5, 0, 1.75, 0.22, 1.75, WOOD), bx(-0.72, 1.72, 0.74, 0.24, 2.0, 0.24, WOOD_D),
                       bx(0.72, 1.72, 0.74, 0.24, 2.0, 0.24, WOOD_D), bx(0, 3.35, 0.74, 1.8, 0.32, 0.28, WOOD),
                       bx(-0.3, 2.0, 0.74, 0.18, 1.35, 0.14, WOOD), bx(0.3, 2.0, 0.74, 0.18, 1.35, 0.14, WOOD)]),
            G("Fabric", [bx(0, 1.72, -0.05, 1.5, 0.16, 1.5, RED)])]


@prop("office_chair")
def _office_chair():
    p = []
    for k in range(5):
        a = k * 72
        R = Ry(a)
        p.append(("box", tuple(R @ np.array([0, 0.28, -0.55])), (0.18, 0.12, 1.1), GREY_D, {"R": R}))
        p.append(("ball", tuple(R @ np.array([0, 0.12, -1.05])), (0.22, 0.22, 0.22), BLACK, None))
    p += [cy(0, 0.25, 0, 0.4, 0.25, GREY_D), cy(0, 0.45, 0, 0.22, 1.05, METAL), bx(0, 1.45, 0, 1.2, 0.12, 1.2, GREY_D),
          bx(-1.0, 1.65, 0.2, 0.12, 0.55, 0.12, GREY_D), bx(1.0, 1.65, 0.2, 0.12, 0.55, 0.12, GREY_D),
          bx(-1.0, 2.15, -0.05, 0.22, 0.1, 1.2, BLACK), bx(1.0, 2.15, -0.05, 0.22, 0.1, 1.2, BLACK),
          bx(0, 1.6, 0.95, 0.3, 0.8, 0.12, GREY_D)]
    return [G("SmoothPlastic", p),
            G("Fabric", [bx(0, 1.55, -0.05, 2.0, 0.45, 2.0, hx("2d4b8c")), bc(0, 3.2, 1.0, 1.9, 2.0, 0.38, hx("2d4b8c"), R=Rx(-8))])]


@prop("park_bench")
def _park_bench():
    m = hx("2d503c")
    return [G("Metal", [bx(s * 2.6, 0, 0, 0.22, 1.35, 1.8, m) for s in (-1, 1)]
            + [bx(s * 2.6, 1.85, -0.15, 0.22, 0.14, 1.5, m) for s in (-1, 1)]
            + [bx(s * 2.6, 1.35, 0.82, 0.22, 1.65, 0.2, m) for s in (-1, 1)]
            + [bx(s * 2.6, 1.35, -0.75, 0.2, 0.5, 0.2, m) for s in (-1, 1)]),
            G("Wood", [bx(0, 1.35, z, 6.2, 0.14, 0.5, hx("d2823c")) for z in (-0.6, 0, 0.6)]
            + [bc(0, y, 0.9, 6.2, 0.42, 0.14, hx("d2823c"), R=Rx(-10)) for y in (2.05, 2.65)])]


@prop("school_desk")
def _school_desk():
    """A combo desk: desktop at -Z, the attached seat at +Z (the student faces -Z)."""
    return [G("Metal", [bx(s * 1.3, 0, -0.5, 0.14, 2.45, 0.14, GREY) for s in (-1, 1)]
            + [bx(s * 1.3, 0, 0.0, 0.14, 0.1, 3.2, GREY) for s in (-1, 1)]
            + [bx(s * 0.9, 0, 1.0, 0.12, 1.5, 0.12, GREY) for s in (-1, 1)]
            + [bx(s * 0.9, 1.6, 1.62, 0.1, 1.6, 0.1, GREY) for s in (-1, 1)]
            + [bx(0, 1.5, 0.3, 0.1, 0.1, 1.5, GREY), bx(0, 1.9, -0.5, 2.6, 0.45, 1.6, GREY_D)]),
            G("Wood", [bx(0, 2.4, -0.55, 3.0, 0.18, 2.0, WOOD_L), bx(0, 1.5, 1.05, 2.0, 0.16, 1.6, WOOD_L),
                       bc(0, 2.6, 1.68, 2.0, 0.9, 0.12, WOOD_L, R=Rx(-6)),
                       bx(0.9, 2.58, -1.2, 0.8, 0.04, 0.12, hx("c8a064"))]),
            G("SmoothPlastic", [bx(-0.7, 2.58, -0.4, 0.9, 0.05, 1.2, BLUE), cy(0.8, 2.58, -0.95, 0.05, 0.7, YEL, R=Rz(80))])]


@prop("desk")
def _desk():
    """An office desk: the sitter is at +Z facing -Z; the -Z side has a modesty panel."""
    return [G("Wood", [bx(0, 2.4, 0, 5.6, 0.22, 2.7, WOOD_L), bx(0, 0.4, -1.15, 5.2, 2.0, 0.12, lit(WOOD_L, 0.9))]),
            G("SmoothPlastic", [bx(-1.9, 0, 0, 1.6, 2.4, 2.5, OFFW), bx(2.55, 0, 0, 0.22, 2.4, 2.5, OFFW),
                                *[bx(-1.9, 0.2 + i * 0.75, 1.26, 1.4, 0.6, 0.04, WHITE) for i in range(3)],
                                *[bx(-1.9, 0.62 + i * 0.75, 1.3, 0.5, 0.08, 0.06, METAL) for i in range(3)]])]


@prop("computer")
def _computer():
    """A desktop monitor + keyboard (screen faces -Z)."""
    return [G("SmoothPlastic", [bx(0, 0, 0.25, 0.9, 0.06, 0.6, DARK), bx(0, 0.06, 0.35, 0.2, 0.8, 0.12, DARK),
                                bx(0, 0.55, 0.25, 2.3, 1.45, 0.14, BLACK), bx(0, 0.62, 0.175, 2.15, 1.3, 0.01, hx("3c8cdc")),
                                bx(-0.5, 1.1, 0.168, 0.8, 0.12, 0.01, WHITE), bx(0.4, 0.75, 0.168, 1.0, 0.5, 0.01, hx("78c8f0")),
                                bx(0, 0, -0.65, 1.8, 0.06, 0.55, GREY_L), bx(1.35, 0, -0.65, 0.25, 0.08, 0.38, GREY_L)])]


@prop("chalkboard")
def _chalkboard():
    p = [bx(0, 1.55, 0, 7.0, 3.7, 0.2, hx("2d5a46"))]
    p += [bx(-2.3 + 0.0, 4.2, -0.11, 2.2, 0.12, 0.02, WHITE), bx(-2.0, 3.8, -0.11, 2.8, 0.1, 0.02, WHITE),
          bx(-2.2, 3.45, -0.11, 2.4, 0.1, 0.02, WHITE), bx(1.8, 3.3, -0.11, 0.1, 1.4, 0.02, YEL),
          bx(1.8, 3.95, -0.11, 1.4, 0.1, 0.02, YEL), bx(-1.0, 2.5, -0.11, 3.6, 0.1, 0.02, PINK_L),
          bx(1.8, 2.4, -0.11, 1.2, 0.1, 0.02, WHITE)]
    return [G("SmoothPlastic", p),
            G("Wood", [bx(0, 5.2, 0, 7.4, 0.3, 0.35, WOOD), bx(0, 1.25, 0, 7.4, 0.3, 0.35, WOOD), bx(-3.6, 1.25, 0, 0.3, 4.25, 0.35, WOOD),
                       bx(3.6, 1.25, 0, 0.3, 4.25, 0.35, WOOD), bx(0, 1.42, -0.3, 7.0, 0.1, 0.4, WOOD),
                       bx(-3.4, 0, 0, 0.3, 1.25, 0.3, WOOD_D), bx(3.4, 0, 0, 0.3, 1.25, 0.3, WOOD_D),
                       bx(-3.4, 0, 0, 0.42, 0.15, 1.8, WOOD_D), bx(3.4, 0, 0, 0.42, 0.15, 1.8, WOOD_D)]),
            G("SmoothPlastic", [bx(1.0, 1.52, -0.35, 0.5, 0.08, 0.12, WHITE), bx(1.7, 1.52, -0.32, 0.6, 0.18, 0.22, hx("c8b48c"))])]


@prop("lockers")
def _lockers():
    cols = [hx("3c78d2"), hx("e05050"), hx("3c78d2"), hx("e8b438")]
    p = [bx(0, 0, 0, 6.2, 6.5, 1.7, GREY_L), bx(0, 0, -0.84, 6.2, 0.35, 0.04, DARK)]
    for i in range(4):
        x = -2.3 + i * 1.535
        c = cols[i]
        p += [bx(x, 0.45, -0.87, 1.4, 5.85, 0.06, c), bx(x + 0.5, 2.8, -0.92, 0.1, 0.55, 0.06, METAL)]
        p += [bx(x, 5.4 - k * 0.2, -0.905, 0.9, 0.08, 0.02, lit(c, 0.7)) for k in range(4)]
        p.append(bx(x, 4.3, -0.905, 0.45, 0.25, 0.02, WHITE))
    return [G("Metal", p)]


@prop("fridge")
def _fridge():
    body = hx("aee6dc")
    return [G("SmoothPlastic", [bx(0, 0.15, 0, 3.0, 6.35, 2.6, body), bx(0, 0, 0.05, 2.8, 0.2, 2.4, DARK),
                                bx(0, 4.45, -1.31, 2.95, 0.1, 0.04, lit(body, 0.7)),
                                bx(1.15, 4.75, -1.4, 0.15, 1.2, 0.15, METAL), bx(1.15, 2.2, -1.4, 0.15, 1.9, 0.15, METAL),
                                bx(-0.6, 3.4, -1.32, 0.5, 0.6, 0.02, YEL, R=Rz(6)), bx(0.2, 3.0, -1.32, 0.5, 0.4, 0.02, PINK, R=Rz(-4)),
                                bc(-0.3, 5.6, -1.33, 0.2, 0.2, 0.05, RED), bc(0.3, 5.3, -1.33, 0.2, 0.2, 0.05, BLUE),
                                bx(-0.5, 1.6, -1.32, 0.6, 0.8, 0.02, WHITE), bx(-0.5, 1.75, -1.335, 0.4, 0.06, 0.01, BLUE),
                                bx(-0.5, 1.95, -1.335, 0.4, 0.06, 0.01, BLUE)])]


@prop("kitchen_counter")
def _kitchen_counter():
    cab = hx("82b4dc")
    p = [bx(0, 0.3, 0.05, 8.0, 2.6, 2.4, cab), bx(0, 0, 0.15, 7.8, 0.3, 2.2, DARK)]
    for i in range(4):
        x = -3.0 + i * 2.0
        p += [bx(x, 0.45, -1.16, 1.85, 1.7, 0.04, lit(cab, 1.08)), bx(x, 2.3, -1.16, 1.85, 0.45, 0.04, lit(cab, 1.08)),
              bx(x + 0.65, 1.6, -1.2, 0.08, 0.5, 0.06, METAL), bx(x, 2.48, -1.2, 0.5, 0.08, 0.06, METAL)]
    return [G("SmoothPlastic", p),
            G("Marble", [bx(0, 2.9, 0, 8.2, 0.3, 2.6, hx("f0f0ee"))]),
            G("Metal", [bx(1.8, 3.2, 0.05, 2.2, 0.02, 1.5, GREY), bx(1.8, 3.19, 0.05, 2.0, 0.03, 1.3, GREY_D)])]


@prop("faucet")
def _faucet():
    return [G("Metal", [cy(0, 0, 0, 0.3, 0.12, METAL), cy(0, 0.1, 0, 0.14, 0.9, METAL), bx(0, 0.88, -0.25, 0.14, 0.14, 0.6, METAL),
                        bx(0, 0.72, -0.5, 0.12, 0.2, 0.12, METAL), bx(-0.3, 0, 0, 0.12, 0.25, 0.12, METAL),
                        bx(0.3, 0, 0, 0.12, 0.25, 0.12, METAL)])]


@prop("stove")
def _stove():
    return [G("SmoothPlastic", [bx(0, 0, 0, 3.0, 3.0, 2.4, WHITE), bx(0, 3.0, 0, 3.0, 0.15, 2.4, BLACK),
                                *[cy(x, 3.15, z, 0.9, 0.06, GREY_D, seg=16) for x in (-0.7, 0.7) for z in (-0.5, 0.45)],
                                *[cy(x, 3.15, z, 0.5, 0.08, DARK, seg=16) for x in (-0.7, 0.7) for z in (-0.5, 0.45)],
                                bx(0, 3.0, 1.05, 3.0, 0.9, 0.3, WHITE), *[cz(x, 3.5, 0.88, 0.1, 0.22, BLACK) for x in (-0.9, -0.3, 0.3, 0.9)],
                                bx(0, 0.6, -1.22, 2.3, 1.5, 0.05, DARK), bx(0, 0.8, -1.25, 1.7, 1.0, 0.02, hx("5a3c28")),
                                bx(0, 2.3, -1.3, 2.2, 0.12, 0.12, METAL), bx(0, 2.6, -1.22, 2.8, 0.3, 0.04, GREY_L)])]


@prop("door")
def _door():
    door = hx("d2643c")
    p = [bx(0, 0, 0, 4.0, 7.0, 0.3, door)]
    for s in (-1, 1):
        for y0 in (0.6, 3.9):
            p += [bx(-0.95, y0, s * 0.16, 1.45, 2.6, 0.04, lit(door, 0.9)), bx(0.95, y0, s * 0.16, 1.45, 2.6, 0.04, lit(door, 0.9))]
        p.append(bl(1.55, 3.3, s * 0.25, 0.22, 0.22, 0.2, GOLD))
    return [G("SmoothPlastic", p),
            G("Wood", [bx(-2.2, 0, 0, 0.4, 7.4, 0.9, WHITE), bx(2.2, 0, 0, 0.4, 7.4, 0.9, WHITE), bx(0, 7.0, 0, 4.8, 0.4, 0.9, WHITE)])]


@prop("mailbox")
def _mailbox():
    b = hx("3c6ed2")
    return [G("Wood", [bx(0, 0, 0, 0.36, 3.1, 0.36, WOOD_D), bx(0, 0, 0, 0.8, 0.15, 0.8, WOOD_D)]),
            G("SmoothPlastic", [bx(0, 3.05, 0, 1.0, 0.55, 1.8, b), cz(0, 3.6, 0, 1.8, 1.0, b, seg=20),
                                bx(0, 3.05, -0.91, 0.9, 0.95, 0.04, lit(b, 0.9)), bx(0, 3.4, -0.95, 0.3, 0.08, 0.06, WHITE),
                                bx(0.56, 3.35, 0.4, 0.07, 0.75, 0.12, RED), bx(0.56, 3.95, 0.5, 0.07, 0.28, 0.4, RED)])]


@prop("streetlight")
def _streetlight():
    pole = hx("2d3a4a")
    return [G("Metal", [cy(0, 0, 0, 1.2, 0.5, pole, seg=12), cy(0, 0.5, 0, 0.8, 0.5, pole, seg=12),
                        cy(0, 1.0, 0, 0.42, 11.2, pole, seg=12), bx(0, 12.1, 0, 1.3, 0.2, 1.3, pole),
                        bx(0, 13.3, 0, 1.5, 0.15, 1.5, pole), sp(0, 13.45, 0, 1.4, 0.55, 1.4, pole, taper=0.2),
                        bl(0, 14.1, 0, 0.25, 0.25, 0.25, pole),
                        *[bx(sx * 0.55, 12.3, sz * 0.55, 0.12, 1.0, 0.12, pole) for sx in (-1, 1) for sz in (-1, 1)]]),
            G("SmoothPlastic", [bx(0, 12.3, 0, 1.0, 1.0, 1.0, hx("fff5c8"))])]


@prop("tree")
def _tree():
    return [G("Wood", [cy(0, 0, 0, 1.5, 7.5, hx("8c5a32"), seg=8), cy(0, 0, 0, 2.1, 0.6, hx("7a4e2a"), seg=8),
                       rod((0, 5.5, 0), (1.8, 8.0, 0.4), 0.6, hx("8c5a32"))]),
            G("Grass", [bl(0, 10.4, 0, 8.6, 7.0, 8.4, hx("50b45a"), seg=10), bl(-2.9, 8.8, 1.0, 5.2, 4.4, 5.0, hx("46a050"), seg=10),
                        bl(2.8, 9.2, -1.2, 5.0, 4.8, 5.0, hx("5abe5a"), seg=10), bl(0.4, 13.3, 0.3, 5.6, 4.6, 5.4, hx("64c85f"), seg=10),
                        bl(0.5, 9.0, 3.0, 4.4, 4.0, 4.0, hx("4aa852"), seg=10), bl(-0.8, 9.4, -3.0, 4.4, 4.0, 4.2, hx("5ab95a"), seg=10)])]


@prop("bush")
def _bush():
    return [G("Grass", [bl(0, 1.25, 0, 3.4, 2.5, 3.0, hx("4fae55"), seg=10), bl(-1.3, 0.95, 0.3, 2.1, 1.9, 2.1, hx("5abe5a"), seg=10),
                        bl(1.35, 1.0, -0.2, 2.3, 2.0, 2.2, hx("46a050"), seg=10)]),
            G("SmoothPlastic", [bl(x, y, z, 0.3, 0.3, 0.3, c) for x, y, z, c in
                                ((-0.8, 2.0, -0.9, PINK), (0.5, 2.3, -0.7, YEL), (1.5, 1.6, -0.9, PINK), (-1.8, 1.4, -0.4, WHITE),
                                 (0.0, 1.7, -1.4, WHITE))])]


@prop("car")
def _car():
    body = hx("e64646")
    p = [bx(0, 0.7, 0, 4.5, 1.9, 9.0, body), bx(0, 2.6, 0.9, 4.0, 0.08, 4.4, body)]
    p += [bx(0, 4.55, 0.85, 3.5, 0.32, 3.7, body)]
    for s in (-1, 1):
        p += [bx(s * 1.6, 2.6, 0.85 + t * 1.85, 0.2, 2.0, 0.2, body) for t in (-1, 0, 1)]
        p += [bx(s * 2.26, 1.55, 0, 0.04, 0.32, 8.6, WHITE), bx(s * 1.45, 1.75, -4.52, 0.9, 0.5, 0.06, hx("fff5c8")),
              bx(s * 1.5, 1.75, 4.52, 0.8, 0.4, 0.06, hx("ff3c3c")), bx(s * 2.3, 2.5, -0.6, 0.35, 0.2, 0.25, body)]
    p += [bx(0, 0.5, -4.6, 4.6, 0.55, 0.3, GREY_D), bx(0, 0.5, 4.6, 4.6, 0.55, 0.3, GREY_D), bx(0, 1.2, -4.53, 2.0, 0.5, 0.05, DARK),
          bx(0, 0.95, 4.76, 1.3, 0.45, 0.03, WHITE)]
    wheels = []
    for s in (-1, 1):
        for t in (-2.9, 2.9):
            wheels += [cx(s * 2.0, 1.0, t, 0.8, 2.0, BLACK, seg=16), cx(s * 2.05, 1.0, t, 0.82, 1.0, GREY_L, seg=12)]
    return [G("SmoothPlastic", p + wheels),
            G("Glass", [("box", (0, 3.6, 0.85), (3.9, 1.95, 4.3), hx("8cc8f0"), {"taper": 0.85})], tr=0.35)]


@prop("bicycle")
def _bicycle():
    fr = hx("28b4aa")
    rear, front, crank = (0, 1.2, 1.75), (0, 1.2, -1.75), (0, 1.05, 0.15)
    seat, head = (0, 2.55, 0.65), (0, 2.65, -1.3)
    p = [cx(0, 1.2, z, 0.16, 2.4, BLACK, seg=24) for z in (1.75, -1.75)]
    p += [cx(0, 1.2, z, 0.18, 1.9, GREY_L, seg=20) for z in (1.75, -1.75)]
    p += [cx(0, 1.2, z, 0.3, 0.3, DARK, seg=10) for z in (1.75, -1.75)]
    p += [rod(rear, seat, 0.14, fr), rod(seat, head, 0.16, fr), rod(crank, head, 0.18, fr), rod(crank, seat, 0.16, fr),
          rod(rear, crank, 0.12, fr), rod(head, front, 0.14, fr), rod(seat, (0, 2.85, 0.75), 0.1, GREY),
          rod(head, (0, 3.2, -1.4), 0.12, GREY), bx(0, 2.85, 0.65, 0.42, 0.16, 0.8, BLACK),
          bx(0, 3.15, -1.4, 1.7, 0.1, 0.1, GREY), bx(-0.85, 3.12, -1.4, 0.18, 0.16, 0.16, BLACK), bx(0.85, 3.12, -1.4, 0.18, 0.16, 0.16, BLACK),
          cx(0, 1.05, 0.15, 0.3, 0.5, GREY_D), bx(-0.3, 0.75, 0.15, 0.4, 0.08, 0.2, BLACK), bx(0.3, 1.25, 0.15, 0.4, 0.08, 0.2, BLACK),
          bx(0, 2.3, -1.85, 0.5, 0.25, 0.4, hx("f0d23c"))]
    return [G("SmoothPlastic", p)]


@prop("throne")
def _throne():
    v = hx("b4283c")
    return [G("SmoothPlastic", [bx(0, 0, 0, 4.8, 0.5, 4.2, GOLD_D), bx(-1.95, 0.5, 1.25, 0.45, 5.6, 0.75, GOLD), bx(1.95, 0.5, 1.25, 0.45, 5.6, 0.75, GOLD),
                                bx(0, 5.6, 1.25, 4.4, 0.55, 0.75, GOLD), sp(0, 6.15, 1.25, 1.3, 0.8, 0.6, GOLD, taper=0.3),
                                bl(-1.95, 6.3, 1.25, 0.55, 0.55, 0.55, GOLD), bl(1.95, 6.3, 1.25, 0.55, 0.55, 0.55, GOLD),
                                bl(0, 6.15, 0.88, 0.36, 0.36, 0.12, hx("3c64e6")), bl(-0.9, 5.88, 0.87, 0.24, 0.24, 0.1, GREEN),
                                bl(0.9, 5.88, 0.87, 0.24, 0.24, 0.1, GREEN),
                                bx(-1.95, 1.4, -0.2, 0.55, 1.15, 2.6, GOLD), bx(1.95, 1.4, -0.2, 0.55, 1.15, 2.6, GOLD),
                                bx(-1.95, 2.55, -0.25, 0.7, 0.2, 2.8, GOLD_D), bx(1.95, 2.55, -0.25, 0.7, 0.2, 2.8, GOLD_D),
                                bx(0, 0.5, -0.1, 3.5, 1.2, 3.0, GOLD_D)]),
            G("Fabric", [bx(0, 1.7, 0.0, 3.5, 0.45, 2.8, v), bx(0, 2.1, 1.12, 3.5, 3.5, 0.5, v), bx(0, 2.2, 0.88, 2.6, 2.9, 0.1, lit(v, 1.15))])]


@prop("polaroid_camera")
def _polaroid():
    return [G("SmoothPlastic", [bx(0, 0, 0, 1.1, 0.7, 0.8, CREAM), bx(0, 0, 0.1, 1.12, 0.12, 0.62, DARK),
                                cz(0, 0.36, -0.45, 0.14, 0.46, BLACK, seg=20), cz(0, 0.36, -0.52, 0.04, 0.3, hx("466e96"), seg=20),
                                *[bx(-0.35 + i * 0.05, 0.12, -0.41, 0.05, 0.46, 0.02, c) for i, c in enumerate((RED, ORANGE, YEL, GREEN, BLUE))],
                                bx(0.3, 0.52, -0.41, 0.3, 0.12, 0.02, WHITE), bx(0.3, 0.7, 0.1, 0.25, 0.12, 0.25, DARK),
                                bx(0, 0.02, -0.41, 0.8, 0.05, 0.02, DARK)])]


@prop("coffee_table")
def _coffee_table():
    return [G("Wood", [bx(0, 1.15, 0, 4.4, 0.25, 2.5, WOOD), bx(0, 0.35, 0, 3.9, 0.12, 2.0, WOOD_L),
                       *[bx(s * 1.95, 0, t * 1.0, 0.3, 1.15, 0.3, WOOD_D) for s in (-1, 1) for t in (-1, 1)]])]


@prop("bookshelf")
def _bookshelf():
    rng = np.random.default_rng(11)
    p = [bx(-2.2, 0, 0, 0.3, 7.2, 1.45, WOOD), bx(2.2, 0, 0, 0.3, 7.2, 1.45, WOOD), bx(0, 6.95, 0, 4.7, 0.3, 1.5, WOOD),
         bx(0, 0, 0.62, 4.1, 7.0, 0.15, WOOD_D)]
    shelves = (0.0, 1.75, 3.45, 5.15)
    for y in shelves:
        p.append(bx(0, y, 0, 4.1, 0.22, 1.4, WOOD))
    books = []
    for si, y in enumerate(shelves):
        x = -1.95
        while x < 1.8:
            w = rng.uniform(0.22, 0.42)
            h = rng.uniform(1.0, 1.45)
            if rng.random() < 0.1 and x < 1.2:
                x += 0.5
                continue
            col = BOOK_COLS[rng.integers(len(BOOK_COLS))]
            tilt = 8 if rng.random() < 0.08 else 0
            books.append(("box", (x + w / 2, y + 0.22 + h / 2, -0.05), (w, h, 1.05), col, {"R": Rz(tilt)} if tilt else None))
            books.append(bx(x + w / 2, y + 0.22 + h * 0.7, -0.585, w * 0.6, 0.08, 0.01, GOLD))
            x += w + 0.02
    return [G("Wood", p), G("SmoothPlastic", books)]


@prop("lamp")
def _lamp():
    return [G("Metal", [cy(0, 0, 0, 1.2, 0.15, DARK, seg=16), cy(0, 0.15, 0, 0.16, 4.1, GOLD_D, seg=10)]),
            G("Fabric", [cy(0, 3.9, 0, 1.75, 1.45, hx("fae6be"), taper=0.62, seg=16)])]


@prop("table_lamp")
def _table_lamp():
    return [G("SmoothPlastic", [cy(0, 0, 0, 0.65, 0.12, GOLD_D, seg=14), bl(0, 0.5, 0, 0.6, 0.75, 0.6, TEAL), cy(0, 0.8, 0, 0.08, 0.4, GOLD_D)]),
            G("Fabric", [cy(0, 1.1, 0, 1.0, 0.75, hx("fae6be"), taper=0.65, seg=14)])]


@prop("plant")
def _plant():
    leaves = [bl(0, 2.1, 0, 1.7, 1.6, 1.7, hx("4fb455"), seg=10), bl(-0.6, 1.7, 0.3, 1.1, 1.0, 1.1, hx("5ac05a"), seg=10),
              bl(0.6, 1.8, -0.3, 1.1, 1.1, 1.1, hx("46a050"), seg=10)]
    for k in range(6):
        a = k * 60
        R = Ry(a) @ Rx(-28)
        leaves.append(("box", tuple(Ry(a) @ np.array([0, 2.5, -0.5])), (0.4, 1.4, 0.08), hx("5ac864"), {"R": R, "taper": 0.3}))
    return [G("SmoothPlastic", [cy(0, 0, 0, 1.15, 1.0, TERRA, taper=1.2, seg=16), cy(0, 0.9, 0, 1.5, 0.22, lit(TERRA, 1.1), seg=16),
                                cy(0, 1.0, 0, 1.25, 0.14, BROWN, seg=16)]), G("Grass", leaves)]


@prop("rug")
def _rug():
    return [G("Fabric", [bx(0, 0, 0, 8.0, 0.05, 5.6, hx("d25a50")), bx(0, 0.05, 0, 7.2, 0.012, 4.8, CREAM),
                         bx(0, 0.06, 0, 6.6, 0.012, 4.2, hx("e6aa5a")), bx(0, 0.072, 0, 2.2, 0.012, 2.2, hx("d25a50"), R=Ry(45)),
                         bx(0, 0.07, 0, 5.8, 0.012, 0.2, CREAM), bx(0, 0.07, 0, 0.2, 0.012, 3.4, CREAM)])]


@prop("ceiling_light")
def _ceiling_light():
    """A pendant: hangs 2.4 below the ceiling (place its bottom at ceiling - height)."""
    return [G("SmoothPlastic", [cy(0, 1.6, 0, 0.6, 0.15, WHITE), cy(0, 1.0, 0, 0.06, 1.75, DARK), cy(0, 0.05, 0, 1.6, 0.95, WHITE, taper=0.25, seg=18),
                                cy(0, 0.0, 0, 1.1, 0.06, hx("fff5d2"), seg=18)])]


@prop("flush_light")
def _flush_light():
    return [G("SmoothPlastic", [cy(0, 0.15, 0, 2.4, 0.15, WHITE, seg=20), cy(0, 0, 0, 2.0, 0.2, hx("fffae6"), seg=20, taper=1.1)])]


@prop("nightstand")
def _nightstand():
    return [G("Wood", [bx(0, 0, 0, 1.8, 2.0, 1.6, WOOD_L), bx(0, 1.05, -0.81, 1.55, 0.75, 0.04, lit(WOOD_L, 1.08)),
                       bx(0, 0.2, -0.81, 1.55, 0.75, 0.04, lit(WOOD_L, 1.08)), bx(0, 1.38, -0.86, 0.4, 0.08, 0.06, GOLD_D),
                       bx(0, 0.53, -0.86, 0.4, 0.08, 0.06, GOLD_D)])]


@prop("wardrobe")
def _wardrobe():
    c = hx("e8d2b4")
    return [G("Wood", [bx(0, 0.3, 0, 4.4, 7.4, 2.2, c), bx(0, 0, 0, 4.2, 0.3, 2.0, WOOD_D), bx(0, 7.7, 0, 4.6, 0.3, 2.4, lit(c, 0.95)),
                       bx(-1.08, 0.5, -1.11, 2.05, 7.0, 0.04, lit(c, 1.05)), bx(1.08, 0.5, -1.11, 2.05, 7.0, 0.04, lit(c, 1.05)),
                       bx(-0.2, 3.6, -1.17, 0.1, 0.8, 0.1, GOLD_D), bx(0.2, 3.6, -1.17, 0.1, 0.8, 0.1, GOLD_D)])]


@prop("toy_box")
def _toy_box():
    return [G("SmoothPlastic", [bx(0, 0, 0, 3.0, 1.6, 1.8, hx("f0b43c")), bx(0, 1.6, 0, 3.1, 0.2, 1.9, RED),
                                bx(0, 0.5, -0.91, 1.0, 0.6, 0.02, BLUE), bl(0.6, 2.2, 0.1, 0.8, 0.8, 0.8, hx("3cb4e6")),
                                bx(-0.6, 1.8, 0, 0.6, 0.6, 0.6, GREEN, R=Ry(20))])]


@prop("beanbag")
def _beanbag():
    return [G("Fabric", [bl(0, 0.9, 0, 2.8, 1.8, 2.8, PURPLE, seg=16), bl(0, 1.6, 0.6, 2.2, 1.4, 1.2, lit(PURPLE, 1.08), seg=14)])]


@prop("poster")
def _poster():
    """Wall art (faces -Z, 0.06 deep)."""
    return [G("SmoothPlastic", [bx(0, 0, 0, 2.6, 3.4, 0.06, WHITE), bx(0, 0.2, -0.035, 2.3, 3.0, 0.01, hx("3c3c8c")),
                                bl(0.4, 2.4, -0.045, 0.7, 0.7, 0.01, YEL), sp(-0.3, 0.4, -0.045, 1.6, 1.4, 0.01, hx("e65a8c"), taper=0.05),
                                sp(0.6, 0.4, -0.05, 1.2, 1.0, 0.01, hx("b45aa0"), taper=0.05)])]


@prop("painting")
def _painting():
    return [G("SmoothPlastic", [bx(0, 0, 0, 4.0, 2.8, 0.15, GOLD_D), bx(0, 0.2, -0.08, 3.6, 2.4, 0.02, hx("96d2f0")),
                                bx(0, 0.2, -0.09, 3.6, 0.9, 0.02, hx("64b45a")), sp(-0.8, 1.1, -0.1, 1.8, 1.1, 0.01, hx("5a78a0"), taper=0.05),
                                sp(0.6, 1.1, -0.1, 1.4, 0.8, 0.01, hx("7896b4"), taper=0.05), cz(1.2, 2.1, -0.095, 0.01, 0.45, WHITE)])]


@prop("curtains")
def _curtains():
    """A curtain pair for a 6-wide window (rod at the top)."""
    c = hx("e66e78")
    p = [cx(0, 5.0, 0, 8.4, 0.15, GOLD_D)]
    for s in (-1, 1):
        for k in range(4):
            p.append(bx(s * (3.6 - k * 0.32), 0, 0.05 * (k % 2), 0.34, 4.9, 0.18, lit(c, 1.0 - 0.06 * (k % 2))))
    return [G("Fabric", p)]


@prop("upper_cabinet")
def _upper_cabinet():
    cab = hx("82b4dc")
    p = [bx(0, 0, 0, 8.0, 2.6, 1.4, cab)]
    for i in range(4):
        x = -3.0 + i * 2.0
        p += [bx(x, 0.12, -0.71, 1.85, 2.35, 0.04, lit(cab, 1.08)), bx(x + 0.65, 0.3, -0.75, 0.08, 0.45, 0.06, METAL)]
    return [G("SmoothPlastic", p)]


@prop("microwave")
def _microwave():
    return [G("SmoothPlastic", [bx(0, 0, 0, 1.9, 1.1, 1.3, WHITE), bx(-0.25, 0.12, -0.66, 1.2, 0.85, 0.02, DARK),
                                bx(0.62, 0.12, -0.66, 0.45, 0.85, 0.02, GREY_L), bx(0.62, 0.8, -0.68, 0.3, 0.12, 0.01, hx("50e68c"))])]


@prop("toaster")
def _toaster():
    return [G("SmoothPlastic", [bx(0, 0, 0, 1.0, 0.7, 0.6, RED), bx(-0.2, 0.7, 0, 0.15, 0.02, 0.45, DARK), bx(0.2, 0.7, 0, 0.15, 0.02, 0.45, DARK),
                                bx(0, 0.68, 0, 0.12, 0.2, 0.4, hx("d2a064")), bx(0.52, 0.4, 0, 0.06, 0.1, 0.12, BLACK)])]


@prop("fruit_bowl")
def _fruit_bowl():
    return [G("SmoothPlastic", [cy(0, 0, 0, 1.3, 0.4, WHITE, taper=1.35, seg=16), bl(-0.2, 0.45, 0, 0.4, 0.4, 0.4, RED),
                                bl(0.22, 0.45, 0.1, 0.4, 0.4, 0.4, ORANGE), bl(0, 0.5, -0.25, 0.38, 0.38, 0.38, LIME),
                                bc(0.1, 0.62, 0.25, 0.7, 0.2, 0.2, YEL, R=Rz(20))])]


@prop("bread")
def _bread():
    return [G("SmoothPlastic", [bl(0, 0.35, 0, 1.4, 0.7, 0.8, hx("d2964a")), *[bc(x, 0.66, 0, 0.08, 0.04, 0.5, hx("aa6e32"), R=Ry(30))
                                                                         for x in (-0.35, 0, 0.35)]])]


@prop("cupcake")
def _cupcake():
    return [G("SmoothPlastic", [cy(0, 0, 0, 0.5, 0.35, hx("5ab4e6"), taper=1.25, seg=14), bl(0, 0.42, 0, 0.65, 0.4, 0.65, PINK_L),
                                bl(0, 0.62, 0, 0.36, 0.3, 0.36, PINK_L), bl(0, 0.82, 0, 0.12, 0.12, 0.12, RED)])]


@prop("display_case")
def _display_case():
    """Bakery / cafe pastry case: wooden base, glass box with a shelf of treats."""
    base = hx("f5e1c3")
    treats = []
    for i in range(5):
        x = -2.3 + i * 1.15
        treats += [cy(x, 2.75, -0.2, 0.75, 0.35, [PINK, hx("8c5a3c"), YEL, PINK_L, hx("c8783c")][i], seg=14),
                   bl(x, 3.18, -0.2, 0.18, 0.18, 0.18, RED)]
        treats += [bl(x, 3.95, 0.15, 0.7, 0.36, 0.45, hx("d2964a")), cy(x, 3.6, 0.15, 0.9, 0.04, WHITE, seg=12)]
    return [G("Wood", [bx(0, 0, 0, 6.2, 2.6, 2.5, base), bx(0, 2.6, 0, 6.2, 0.15, 2.5, WOOD), bx(0, 0, -0.9, 6.0, 0.3, 0.04, WOOD_D),
                       bx(0, 3.6, 0, 6.0, 0.06, 2.3, WHITE), bx(0, 5.0, 0, 6.2, 0.1, 2.5, WOOD),
                       *[bx(sx * 3.05, 2.75, sz * 1.2, 0.1, 2.3, 0.1, WOOD) for sx in (-1, 1) for sz in (-1, 1)]]),
            G("SmoothPlastic", treats + [bx(0, 0.6, -1.26, 4.6, 0.5, 0.02, PINK)]),
            G("Glass", [bx(0, 2.75, 0, 6.0, 2.25, 2.3, hx("c8f0ff"))], tr=0.6)]


@prop("shop_counter")
def _shop_counter():
    c = hx("dc5a46")
    return [G("Wood", [bx(0, 0, 0.1, 7.0, 3.0, 2.2, c), *[bx(-2.6 + i * 1.73, 0.4, -1.01, 1.4, 2.2, 0.04, lit(c, 1.12)) for i in range(4)],
                       bx(0, 0, -0.92, 7.0, 0.3, 0.04, DARK)]),
            G("Marble", [bx(0, 3.0, 0, 7.4, 0.28, 2.6, hx("f2f0ec"))])]


@prop("espresso_machine")
def _espresso():
    return [G("Metal", [bx(0, 0, 0, 2.2, 1.6, 1.4, METAL), bx(0, 1.6, 0, 2.3, 0.15, 1.5, GREY_D),
                        bx(-0.5, 0.75, -0.75, 0.3, 0.2, 0.4, BLACK), bx(0.5, 0.75, -0.75, 0.3, 0.2, 0.4, BLACK),
                        bx(0, 0, -0.85, 2.0, 0.08, 0.5, GREY_D)]),
            G("SmoothPlastic", [bx(0, 1.0, -0.71, 1.8, 0.4, 0.02, RED), cy(-0.5, 0.08, -0.8, 0.3, 0.32, WHITE), cy(0.5, 0.08, -0.8, 0.3, 0.32, WHITE),
                                *[cy(x, 1.75, 0.1, 0.35, 0.3, WHITE) for x in (-0.6, 0, 0.6)]])]


@prop("menu_board")
def _menu_board():
    p = [bx(0, 0, 0, 7.0, 3.6, 0.15, hx("2d2d32"))]
    p += text_pieces("MENU", 0, 2.75, -0.1, 0.13, YEL, 0.04)
    for col, x in ((PINK_L, 1.8), (hx("8cdcf0"), -1.8)):
        for i in range(4):
            p += [bx(x, 0.4 + i * 0.55, -0.09, 2.2, 0.14, 0.02, WHITE), bx(x - 1.35, 0.38 + i * 0.55, -0.09, 0.3, 0.18, 0.02, col)]
    return [G("Wood", [bx(0, -0.15, 0, 7.3, 3.9, 0.12, WOOD_D)]), G("SmoothPlastic", p)]


@prop("bistro_table")
def _bistro_table():
    return [G("Metal", [cy(0, 0, 0, 1.4, 0.1, DARK, seg=16), cy(0, 0.1, 0, 0.18, 2.6, DARK, seg=10)]),
            G("Marble", [cy(0, 2.7, 0, 2.8, 0.18, WHITE, seg=24)])]


@prop("cafe_chair")
def _cafe_chair():
    c = hx("3cb4aa")
    return [G("Metal", [*[bx(s * 0.6, 0, t * 0.6, 0.12, 1.55, 0.12, DARK) for s in (-1, 1) for t in (-1, 1)],
                        bx(-0.6, 1.55, 0.62, 0.12, 1.6, 0.12, DARK), bx(0.6, 1.55, 0.62, 0.12, 1.6, 0.12, DARK),
                        bx(0, 2.85, 0.62, 1.32, 0.35, 0.1, c), bx(0, 2.2, 0.62, 1.32, 0.12, 0.1, c)]),
            G("SmoothPlastic", [bx(0, 1.55, 0, 1.4, 0.16, 1.4, c)])]


@prop("bar_stool")
def _bar_stool():
    return [G("Metal", [cy(0, 0, 0, 1.2, 0.08, DARK), cy(0, 0.08, 0, 0.18, 2.8, METAL), cy(0, 1.2, 0, 0.9, 0.06, METAL)]),
            G("Fabric", [cy(0, 2.85, 0, 1.4, 0.35, RED, seg=18)])]


@prop("judge_bench")
def _judge_bench():
    """A raised judge's bench: platform (top 1.5) with a tall panelled front desk at -Z; the judge stands/sits at +Z."""
    wd = hx("8c5532")
    base = [bx(0, 0, 0.5, 13.0, 1.5, 7.0, lit(wd, 0.9))] + [bx(s_ * 7.0, 0, 1.5, 1.0, 0.5, 2.0, lit(wd, 0.8)) for s_ in (-1, 1)]
    p = [bx(0, 1.5, -2.25, 13.0, 4.2, 1.2, wd), bx(0, 5.7, -2.1, 13.6, 0.35, 1.8, lit(wd, 1.15)),
         bx(0, 0, -3.3, 14.0, 0.5, 0.9, lit(wd, 0.8))]
    for i in range(6):
        x = -5.4 + i * 2.16
        if abs(x) < 1.5:
            continue
        p.append(bx(x, 2.1, -2.87, 1.7, 3.0, 0.06, lit(wd, 1.12)))
    return [G("Wood", base), G("Wood", p),
            G("SmoothPlastic", [cz(0, 3.6, -2.92, 0.12, 2.6, GOLD, seg=28), cz(0, 3.6, -2.99, 0.04, 2.1, hx("1e3c78"), seg=28),
                                sp(0, 3.0, -3.02, 1.0, 1.2, 0.03, GOLD, taper=0.05), bx(0, 6.05, -1.6, 0.4, 0.15, 1.0, BROWN),
                                cy(0.3, 6.05, -1.9, 0.4, 0.18, BROWN)])]


@prop("pew")
def _pew():
    wd = hx("a0643c")
    return [G("Wood", [bx(0, 1.35, 0, 10.0, 0.25, 1.7, wd), bc(0, 2.6, 0.82, 10.0, 2.2, 0.22, wd, R=Rx(-6)),
                       bx(-4.9, 0, 0.1, 0.3, 3.6, 2.0, lit(wd, 0.85)), bx(4.9, 0, 0.1, 0.3, 3.6, 2.0, lit(wd, 0.85)),
                       bx(0, 0.3, 0.0, 9.5, 1.05, 0.15, lit(wd, 0.85)), bx(0, 3.6, 0.9, 10.2, 0.2, 0.4, lit(wd, 0.9))])]


@prop("witness_stand")
def _witness_stand():
    wd = hx("8c5532")
    return [G("Wood", [bx(0, 0, 0, 4.2, 1.0, 4.2, lit(wd, 0.9))]),
            G("Wood", [bx(0, 1.0, -1.95, 4.2, 3.0, 0.3, wd), bx(0, 4.0, -1.95, 4.5, 0.25, 0.6, lit(wd, 1.15))]),
            G("Wood", [bx(-1.95, 1.0, 0, 0.3, 3.0, 4.2, wd), bx(-1.95, 4.0, 0, 0.6, 0.25, 4.4, lit(wd, 1.15))]),
            G("Wood", [bx(1.95, 1.0, -0.6, 0.3, 3.0, 3.0, wd)]),
            G("Metal", [cy(1.2, 4.25, -1.95, 0.2, 0.2, BLACK), rod((1.2, 4.4, -1.95), (1.0, 5.1, -1.6), 0.08, BLACK), bl(1.0, 5.15, -1.55, 0.25, 0.3, 0.25, DARK)])]


@prop("railing")
def _railing():
    """The bar (low wooden rail) 12 wide, with balusters."""
    wd = hx("8c5532")
    p = [bx(0, 3.0, 0, 12.0, 0.3, 0.5, wd), bx(0, 0, 0, 12.0, 0.3, 0.5, wd)]
    p += [bx(-5.8 + i * 0.6, 0.3, 0, 0.18, 2.7, 0.18, lit(wd, 1.15)) for i in range(20)]
    p += [bx(s * 6.0, 0, 0, 0.5, 3.6, 0.6, wd) for s in (-1, 1)]
    return [G("Wood", p)]


@prop("flag")
def _flag():
    return [G("Metal", [cy(0, 0, 0, 1.0, 0.3, GOLD_D), cy(0, 0.3, 0, 0.16, 8.2, GOLD), bl(0, 8.6, 0, 0.4, 0.4, 0.4, GOLD)]),
            G("Fabric", [bx(0.95, 5.0, 0, 1.8, 3.2, 0.06, BLUE), bx(0.95, 6.1, -0.035, 1.8, 0.6, 0.01, WHITE),
                         bx(0.95, 5.1, -0.035, 1.8, 0.6, 0.01, RED), bl(0.95, 7.3, -0.04, 0.5, 0.5, 0.01, YEL)])]


@prop("vault_door")
def _vault_door():
    """A big round vault door for a back wall (faces -Z, 1 stud deep)."""
    p = [cz(0, 4.5, 0, 0.6, 9.0, GREY, seg=32), cz(0, 4.5, -0.35, 0.5, 7.6, METAL, seg=32), cz(0, 4.5, -0.62, 0.3, 1.4, GOLD_D, seg=20)]
    for k in range(3):
        p.append(bc(0, 4.5, -0.75, 4.0, 0.3, 0.2, GOLD, R=Rz(k * 60)))
    for k in range(12):
        a = k * math.pi / 6
        p.append(cz(3.3 * math.sin(a), 4.5 + 3.3 * math.cos(a), -0.62, 0.15, 0.35, GREY_D, seg=10))
    p += [bx(4.2, 3.2, -0.5, 0.5, 2.6, 0.6, GREY_D), bx(0, 0, 0.0, 9.0, 0.3, 1.0, GREY_D)]
    return [G("Metal", p)]


@prop("teller_window")
def _teller_window():
    """A bank teller counter, 7 wide: marble top at 3.6 and a glass screen with a speaking slot."""
    return [G("Wood", [bx(0, 0, 0, 7.0, 3.4, 2.0, hx("5a3c2a")), *[bx(-2.4 + i * 2.4, 0.4, -1.01, 2.0, 2.6, 0.04, hx("6e4a32")) for i in range(3)]]),
            G("Marble", [bx(0, 3.4, 0, 7.4, 0.25, 2.4, hx("f0ece6"))]),
            G("SmoothPlastic", [bx(s * 3.55, 3.65, 0.4, 0.15, 4.0, 0.15, GOLD) for s in (-1, 1)] + [bx(0, 7.6, 0.4, 7.25, 0.18, 0.18, GOLD),
                                                                                                   bx(0, 4.55, 0.4, 7.1, 0.1, 0.12, GOLD)]),
            G("Glass", [bx(0, 4.65, 0.4, 7.0, 2.9, 0.06, hx("c8f0ff"))], tr=0.65)]


@prop("rope_post")
def _rope_post():
    return [G("Metal", [cy(0, 0, 0, 0.9, 0.15, GOLD_D, seg=14), cy(0, 0.15, 0, 0.18, 2.9, GOLD, seg=10), bl(0, 3.1, 0, 0.36, 0.36, 0.36, GOLD)])]


@prop("water_cooler")
def _water_cooler():
    return [G("SmoothPlastic", [bx(0, 0, 0, 1.4, 3.2, 1.4, WHITE), bx(0, 2.0, -0.71, 0.9, 0.5, 0.04, GREY_L),
                                bx(-0.2, 2.2, -0.75, 0.12, 0.15, 0.1, BLUE), bx(0.2, 2.2, -0.75, 0.12, 0.15, 0.1, RED)]),
            G("Glass", [cy(0, 3.2, 0, 1.1, 1.6, hx("78c8ff"), seg=16), cy(0, 4.8, 0, 0.5, 0.25, hx("78c8ff"))], tr=0.35)]


@prop("filing_cabinet")
def _filing_cabinet():
    return [G("Metal", [bx(0, 0, 0, 1.6, 4.4, 2.2, GREY_L), *[bx(0, 0.2 + i * 1.05, -1.11, 1.45, 0.95, 0.04, lit(GREY_L, 1.06)) for i in range(4)],
                        *[bx(0, 0.75 + i * 1.05, -1.16, 0.5, 0.1, 0.08, GREY_D) for i in range(4)]])]


@prop("whiteboard")
def _whiteboard():
    p = [bx(0, 0, 0, 6.0, 3.4, 0.12, METAL), bx(0, 0.15, -0.065, 5.7, 3.1, 0.02, WHITE)]
    p += [bx(-1.2, 2.3, -0.08, 2.6, 0.1, 0.01, BLUE), bx(-1.0, 1.9, -0.08, 3.0, 0.1, 0.01, GREY_D), bx(-1.3, 1.5, -0.08, 2.4, 0.1, 0.01, GREY_D)]
    for i, h in enumerate((0.6, 1.1, 0.8, 1.6)):     # a bar chart going up
        p.append(bx(1.2 + i * 0.4, 0.6, -0.08, 0.3, h, 0.01, [RED, YEL, GREEN, BLUE][i]))
    p += [bx(0, -0.05, -0.15, 5.0, 0.1, 0.3, METAL)]
    return [G("SmoothPlastic", p)]


@prop("printer")
def _printer():
    return [G("SmoothPlastic", [bx(0, 0, 0, 2.2, 2.4, 1.8, GREY_D), bx(0, 2.4, 0, 2.2, 0.9, 1.8, WHITE), bx(0, 2.9, -0.5, 1.6, 0.06, 0.6, WHITE),
                                bx(0.6, 3.0, 0.4, 0.6, 0.3, 0.4, GREY_D), bx(0.6, 3.1, 0.18, 0.4, 0.15, 0.02, hx("78f0b4"))])]


@prop("cubicle_wall")
def _cubicle_wall():
    """A low office partition, 8 wide x 4.6 tall."""
    return [G("Fabric", [bx(0, 0.1, 0, 7.8, 4.3, 0.3, hx("8ca0be"))]), G("Metal", [bx(0, 4.4, 0, 8.0, 0.2, 0.4, GREY_L), bx(-3.95, 0, 0, 0.15, 4.4, 0.4, GREY_L),
                                                                                    bx(3.95, 0, 0, 0.15, 4.4, 0.4, GREY_L)])]


@prop("bulletin_board")
def _bulletin_board():
    p = [bx(0, 0, 0, 5.0, 3.2, 0.1, hx("c8965a"))]
    rng = np.random.default_rng(5)
    for i in range(7):
        x, y = -1.8 + (i % 4) * 1.2 + rng.uniform(-0.1, 0.1), 0.4 + (i // 4) * 1.4 + rng.uniform(-0.1, 0.1)
        p += [bx(x, y, -0.06, 0.9, 1.1, 0.01, [WHITE, YEL, PINK_L, SKY, MINT, WHITE, LILAC][i], R=Rz(rng.uniform(-8, 8))),
              bl(x, y + 1.0, -0.08, 0.12, 0.12, 0.04, RED)]
    return [G("Wood", [bx(0, -0.15, 0.02, 5.3, 3.5, 0.1, WOOD_D)]), G("SmoothPlastic", p)]


@prop("globe")
def _globe():
    return [G("SmoothPlastic", [cy(0, 0, 0, 0.6, 0.1, WOOD_D), cy(0, 0.1, 0, 0.08, 0.3, GOLD_D), bl(0, 0.75, 0, 0.8, 0.8, 0.8, hx("3c8cdc"), seg=16),
                                bl(0.15, 0.85, -0.25, 0.4, 0.35, 0.35, GREEN, seg=10), bl(-0.25, 0.6, -0.2, 0.3, 0.3, 0.35, GREEN, seg=10)])]


@prop("apple")
def _apple():
    return [G("SmoothPlastic", [bl(0, 0.2, 0, 0.42, 0.4, 0.42, RED), bx(0, 0.38, 0, 0.04, 0.12, 0.04, BROWN), bc(0.07, 0.45, 0, 0.12, 0.04, 0.08, GREEN)])]


@prop("cubby_shelf")
def _cubby_shelf():
    p = [bx(0, 0, 0, 6.0, 3.0, 1.4, WOOD_L)]
    cols = [RED, BLUE, YEL, GREEN, ORANGE, PURPLE, TEAL, PINK]
    for i in range(8):
        x, y = -2.25 + (i % 4) * 1.5, 0.25 + (i // 4) * 1.35
        p += [bx(x, y, -0.6, 1.3, 1.15, 0.2, lit(WOOD_L, 0.7)), bx(x, y + 0.05, -0.65, 1.1, 0.85, 0.9, cols[i])]
    return [G("Wood", p)]


@prop("trash_can")
def _trash_can():
    return [G("Metal", [cy(0, 0, 0, 1.6, 2.8, hx("2d6e50"), seg=14), cy(0, 2.8, 0, 1.75, 0.25, hx("235a41"), seg=14),
                        *[bx(0.8 * math.sin(a), 0.3, 0.8 * math.cos(a), 0.12, 2.3, 0.12, hx("235a41"), R=Ry(math.degrees(a)))
                          for a in np.linspace(0, 2 * math.pi, 9)[:-1]]])]


@prop("hydrant")
def _hydrant():
    return [G("SmoothPlastic", [cy(0, 0, 0, 1.1, 0.25, RED_D, seg=12), cy(0, 0.25, 0, 0.8, 1.8, RED, seg=12), cy(0, 2.05, 0, 0.95, 0.2, RED_D, seg=12),
                                bl(0, 2.3, 0, 0.75, 0.55, 0.75, RED, seg=12), cx(0, 1.4, 0, 1.35, 0.4, RED_D, seg=10),
                                cz(0, 1.3, -0.45, 0.4, 0.5, RED_D, seg=10), bx(0, 2.6, 0, 0.2, 0.2, 0.2, GOLD_D)])]


@prop("planter")
def _planter():
    return [G("Concrete", [bx(0, 0, 0, 4.0, 1.4, 4.0, hx("c8c4be"))]), G("Grass", [bx(0, 1.4, 0, 3.6, 0.1, 3.6, hx("5aa046"))]),
            G("SmoothPlastic", [bl(x, 1.7, z, 0.5, 0.5, 0.5, c) for x, z, c in ((-1, -1, PINK), (1, -1, YEL), (-1, 1, WHITE), (1, 1, PINK),
                                                                               (0, -1.2, RED), (-1.2, 0, YEL), (1.2, 0, RED))])]


@prop("fence")
def _fence():
    """A white picket fence section, 8 wide."""
    p = [bx(0, 0.9, 0.12, 8.0, 0.25, 0.12, WHITE), bx(0, 2.3, 0.12, 8.0, 0.25, 0.12, WHITE)]
    for i in range(12):
        x = -3.67 + i * 0.667
        p.append(bx(x, 0, 0, 0.42, 2.9, 0.12, WHITE))
        p.append(sp(x, 2.9, 0, 0.42, 0.35, 0.12, WHITE, taper=0.1))
    return [G("SmoothPlastic", p)]


@prop("hedge")
def _hedge():
    return [G("Grass", [bx(0, 0, 0, 8.0, 3.0, 2.2, hx("46a050")), bl(-2.5, 3.0, 0, 3.0, 0.8, 2.2, hx("4fae55")), bl(1.5, 3.0, 0, 4.0, 0.9, 2.2, hx("4fae55"))])]


@prop("flower_bed")
def _flower_bed():
    rng = np.random.default_rng(9)
    p = []
    for i in range(30):
        x, z = rng.uniform(-2.6, 2.6), rng.uniform(-1.1, 1.1)
        h = rng.uniform(0.5, 0.9)
        p += [bx(x, 0.4, z, 0.08, h, 0.08, GREEN_D), bl(x, 0.4 + h, z, 0.36, 0.3, 0.36, [RED, YEL, PINK, PURPLE, WHITE, ORANGE][i % 6])]
    return [G("Wood", [bx(0, 0, 0, 6.2, 0.5, 2.8, WOOD)]), G("Grass", [bx(0, 0.5, 0, 5.8, 0.05, 2.4, BROWN)]), G("SmoothPlastic", p)]


@prop("fountain")
def _fountain():
    stone = hx("dcd7cd")
    return [G("Concrete", [cy(0, 0, 0, 14.0, 1.6, stone, seg=24), cy(0, 1.6, 0, 14.4, 0.3, lit(stone, 1.05), seg=24),
                           cy(0, 0, 0, 2.0, 4.6, stone, seg=12), cy(0, 4.4, 0, 3.0, 0.5, stone, seg=16, taper=2.0),
                           cy(0, 4.9, 0, 6.0, 0.4, lit(stone, 1.05), seg=20), cy(0, 5.3, 0, 0.9, 1.8, stone, seg=10),
                           cy(0, 7.1, 0, 2.2, 0.35, lit(stone, 1.05), seg=14, taper=1.3)]),
            G("Glass", [cy(0, 0.2, 0, 13.2, 1.15, hx("64bef0"), seg=24), cy(0, 5.2, 0, 5.4, 0.15, hx("64bef0"), seg=20),
                        cy(0, 7.4, 0, 0.5, 1.4, hx("aadcff"), seg=10), bl(0, 8.8, 0, 1.2, 0.9, 1.2, hx("aadcff"), seg=12)], tr=0.35)]


@prop("picnic_table")
def _picnic_table():
    wd = hx("c8823c")
    return [G("Wood", [bx(0, 2.6, 0, 6.5, 0.25, 3.0, wd), *[bx(0, 1.4, s * 2.3, 6.5, 0.22, 1.1, wd) for s in (-1, 1)],
                       *[rod((x, 0, -2.4), (x, 2.6, 0.6), 0.3, lit(wd, 0.85)) for x in (-2.6, 2.6)],
                       *[rod((x, 0, 2.4), (x, 2.6, -0.6), 0.3, lit(wd, 0.85)) for x in (-2.6, 2.6)],
                       *[bx(x, 1.2, 0, 0.25, 0.2, 5.8, lit(wd, 0.85)) for x in (-2.6, 2.6)]])]


@prop("slide")
def _slide():
    return [G("Metal", [*[bx(sx * 1.2, 0, sz * 1.2 + 2.0, 0.3, 6.6, 0.3, BLUE) for sx in (-1, 1) for sz in (-1, 1)],
                        bx(0, 5.0, 2.0, 2.7, 0.3, 2.7, BLUE), *[bx(0, 0.9 + i * 1.0, 3.25, 2.1, 0.15, 0.15, YEL) for i in range(5)],
                        bx(-1.25, 5.3, 2.0, 0.15, 1.2, 2.6, RED), bx(1.25, 5.3, 2.0, 0.15, 1.2, 2.6, RED)]),
            G("SmoothPlastic", [bc(0, 2.8, -1.6, 2.2, 0.25, 6.4, ORANGE, R=Rx(-48)), bc(-1.1, 3.1, -1.6, 0.2, 0.6, 6.4, lit(ORANGE, 0.9), R=Rx(-48)),
                                bc(1.1, 3.1, -1.6, 0.2, 0.6, 6.4, lit(ORANGE, 0.9), R=Rx(-48)), bx(0, 0, -4.4, 2.2, 0.3, 1.6, ORANGE)])]


@prop("swing_set")
def _swing_set():
    p = [rod((-4.5, 0, -1.6), (-4.5, 7.5, 0), 0.35, RED), rod((-4.5, 0, 1.6), (-4.5, 7.5, 0), 0.35, RED),
         rod((4.5, 0, -1.6), (4.5, 7.5, 0), 0.35, RED), rod((4.5, 0, 1.6), (4.5, 7.5, 0), 0.35, RED), cx(0, 7.5, 0, 9.4, 0.35, YEL)]
    for x, c in ((-2.0, BLUE), (2.0, GREEN)):
        p += [bx(x - 0.7, 1.6, 0, 0.06, 5.9, 0.06, GREY_D), bx(x + 0.7, 1.6, 0, 0.06, 5.9, 0.06, GREY_D), bx(x, 1.45, 0, 1.7, 0.18, 0.8, c)]
    return [G("Metal", p)]


@prop("bus_stop")
def _bus_stop():
    return [G("Metal", [bx(s * 3.6, 0, 1.2, 0.25, 7.5, 0.25, GREY_D) for s in (-1, 1)] + [bx(0, 7.5, 0.4, 8.0, 0.3, 2.6, BLUE),
                                                                                        bx(0, 1.4, 1.1, 6.0, 0.2, 0.9, GREY_D)]),
            G("Glass", [bx(0, 0.4, 1.3, 7.0, 6.9, 0.08, hx("c8f0ff"))], tr=0.6),
            G("SmoothPlastic", [bx(4.4, 0, -0.5, 0.2, 7.8, 0.2, GREY_D), cz(4.4, 7.3, -0.5, 0.1, 1.4, YEL), bx(3.1, 4.0, 1.21, 0.9, 2.0, 0.05, PINK_L)])]


@prop("awning")
def _awning():
    """A striped shop awning, 12 wide, sloping down toward -Z (mount its back at a façade)."""
    p = []
    n = 12
    for i in range(n):
        x = -6 + (i + 0.5)
        c = RED if i % 2 == 0 else WHITE
        p.append(("wedge", (x, 0.75, 0), (1.0, 1.5, 3.0), c, None))
        p.append(bx(x, -0.4, -1.5, 1.0, 0.45, 0.08, c))
    return [G("Fabric", p)]


@prop("house")
def _house():
    """A small backdrop house (front with a door and windows at -Z), 14 wide x 10 deep, gable roof."""
    wall = hx("f5dcb4")
    roof = hx("c84b3c")
    p = [bx(0, 0, 0, 14.0, 9.0, 10.0, wall), bx(0, 0, 0, 14.2, 0.8, 10.2, lit(wall, 0.8))]
    p += [wg(0, 9.0, -2.6, 15.0, 4.0, 5.4, roof), wg(0, 9.0, 2.6, 15.0, 4.0, 5.4, roof, R=Ry(180))]
    p += [bx(0, 9.0, 0, 13.0, 3.9, 0.4, wall)]
    p += [bx(0, 0, -5.05, 3.2, 5.6, 0.15, hx("5a8cc8")), bx(0, 5.6, -5.05, 3.8, 0.4, 0.2, WHITE), bl(1.0, 2.8, -5.15, 0.25, 0.25, 0.15, GOLD)]
    for x in (-4.5, 4.5):
        p += [bx(x, 3.0, -5.05, 3.0, 2.8, 0.12, WHITE), bx(x, 3.2, -5.1, 2.5, 2.4, 0.08, hx("8cc8f0")), bx(x, 2.8, -5.2, 3.4, 0.25, 0.4, WHITE),
              bx(x - 1.8, 3.0, -5.08, 0.5, 2.8, 0.1, hx("5a8cc8")), bx(x + 1.8, 3.0, -5.08, 0.5, 2.8, 0.1, hx("5a8cc8"))]
    p += [bx(4.0, 10.5, 1.5, 1.4, 3.5, 1.4, hx("8c4636"))]
    return [G("SmoothPlastic", p)]


@prop("ceiling_fan")
def _ceiling_fan():
    p = [cy(0, 1.4, 0, 0.5, 0.2, WHITE), cy(0, 0.6, 0, 0.12, 0.85, WHITE), cy(0, 0.2, 0, 0.9, 0.45, WHITE, seg=14), cy(0, 0, 0, 0.6, 0.2, hx("fff5d2"))]
    for k in range(4):
        R = Ry(k * 90 + 20)
        p.append(("box", tuple(R @ np.array([0, 0.45, -1.8])), (0.75, 0.06, 2.8), WOOD, {"R": R}))
    return [G("SmoothPlastic", p)]


# ---------------------------------------------------------------------------------------------- building
def _bbox(groups):
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for g in groups:
        for pc in g["pieces"]:
            p, _ = OA.piece_tris(*pc[:3], pc[4] if len(pc) > 4 else None)
            lo, hi = np.minimum(lo, p.min(0)), np.maximum(hi, p.max(0))
    return lo, hi


def build_prop(key: str) -> dict:
    """A prop -> {size, parts}: one vertex-coloured mesh part per material group, pivot at the bottom centre."""
    groups = PROPS[key]()
    lo, hi = _bbox(groups)
    shift = -np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
    parts = []
    for gi, g in enumerate(groups):
        mk = f"own_prop_{key}_{gi}"
        pieces = [(pc[0], tuple(np.asarray(pc[1], float) + shift), pc[2], pc[3], pc[4] if len(pc) > 4 else None) for pc in g["pieces"]]
        info = OA.build_mesh(mk, pieces, {"main": (200, 200, 200)})
        mat = g["mat"]
        parts.append({"kind": "mesh", "name": f"{key}_{gi}", "size": info["size"], "cf": [*info["centre"], *I3],
                      "color": [1, 1, 1], "mat": mat, "tr": g["tr"], "mesh": {"key": mk, "vcol": True},
                      "shadow": True, "block": True, "cc": g["tr"] < 0.5 or mat != "Glass", "cq": True, "refl": 0})
    return {"size": (hi - lo).tolist(), "parts": parts, "own": True}


def build_unit_meshes():
    """Untextured unit primitives as mesh keys (parts colour them): the ceiling slab (a mesh so ground_y skips it)."""
    OA.build_mesh("own_unitbox", [("box", (0, 0, 0), (1, 1, 1), (255, 255, 255))], {"main": (255, 255, 255)})
    # the ceiling slab: every normal points up, so its underside is lit like the floor instead of sitting in the
    # ground ambient (a dark grey band over every interior shot)
    OA.build_mesh("own_ceiling", [("box", (0, 0, 0), (1, 1, 1), (255, 255, 255))], {"main": (255, 255, 255)})
    f = MC.OUT / "own_ceiling.npz"
    z = dict(np.load(f))
    z["nrm"] = np.tile(np.array([0, 1, 0], "f4"), (len(z["nrm"]), 1))
    np.savez(f, **z)


def register_meshes():
    idx_p = MC.OUT / "index.json"
    idx = json.loads(idx_p.read_text()) if idx_p.exists() else {}
    for p in MC.OUT.glob("own_*.npz"):
        z = np.load(p)
        idx[p.stem] = {"size": (z["hi"] - z["lo"]).tolist(), "centre": ((z["hi"] + z["lo"]) / 2).tolist(),
                       "verts": int(len(z["pos"])), "tris": int(len(z["faces"])), "own": True}
    idx_p.write_text(json.dumps(idx))


# ================================================================================================= SETS
class Lot:
    """One set: world-space parts, named spots, the floor height and the camera views it is previewed from."""

    def __init__(self, name: str, x0: float, floor_y: float = 0.0, interior: bool = True, rot: float = LOT_ROT):
        """Lots are authored in a local frame (back wall at +Z, cameras from -Z) and turned by `rot` degrees about
        their origin when finished (finish()): the sun comes from -X, so rot = 90 puts the back wall and the faces of
        characters looking at the camera in the sun."""
        self.name, self.x0, self.floor_y, self.interior, self.rot = name, x0, floor_y, interior, rot
        self.parts: list[dict] = []
        self.spots: list[dict] = []
        self.views: list[dict] = []
        self.bounds = None              # (xmin, xmax, zmin, zmax) world: the map extent
        self.n = 0

    # parts ----------------------------------------------------------------------------------------------
    def box(self, name, c, size, color, mat="SmoothPlastic", tr=0.0, R=None, kind="box", **extra):
        """A part by world centre (x is relative to the lot origin x0)."""
        R = np.eye(3) if R is None else np.asarray(R, float)
        col = [v / 255 for v in color] if max(color) > 1 else list(color)
        d = {"kind": kind, "name": name, "size": [float(v) for v in size], "cf": [c[0] + self.x0, c[1], c[2], *R.ravel().tolist()],
             "color": col, "mat": mat, "tr": tr, "shadow": True, "block": True, "cc": True, "cq": True, "refl": 0,
             "path": f"Workspace.OwnSets.{self.name}.{extra.pop('group', 'Set')}.{name}"}
        if kind == "cyl":       # Roblox cylinders run along X: stand them up
            pass
        d.update(extra)
        self.parts.append(d)
        return d

    def slab(self, name, x0, x1, z0, z1, y_top, thick, color, mat="SmoothPlastic", **extra):
        return self.box(name, ((x0 + x1) / 2, y_top - thick / 2, (z0 + z1) / 2), (x1 - x0, thick, z1 - z0), color, mat, **extra)

    def place(self, key, x, z, yaw=0.0, y=None, s=1.0, name=None, **extra):
        """A prop from the library at (x, z) (x relative to x0), its pivot on the floor unless y is given."""
        lib = PROP_LIB[key]
        self.n += 1
        nm = name or f"{key}{self.n}"
        y = self.floor_y if y is None else y
        R = Ry(yaw)
        base = np.array([x + self.x0, y, z])
        out = []
        for p in lib["parts"]:
            d = json.loads(json.dumps(p))
            rp = np.asarray(p["cf"][:3]) * s
            rr = np.asarray(p["cf"][3:12]).reshape(3, 3)
            d["size"] = [v * s for v in p["size"]]
            d["cf"] = [*(base + R @ rp).tolist(), *(R @ rr).ravel().tolist()]
            d["path"] = f"Workspace.OwnSets.{self.name}.{nm}.{p['name']}"
            d["prop"] = key
            d.update(extra)
            self.parts.append(d)
            out.append(d)
        return out

    def spot(self, name, x, z, yaw=0.0, kind="stand", y=None, note=""):
        a = math.radians(yaw)
        self.spots.append({"name": name, "x": round(x + self.x0, 2), "z": round(z, 2), "y": round(self.floor_y if y is None else y, 2),
                           "yaw": yaw, "facing": [round(-math.sin(a), 3), round(-math.cos(a), 3)], "kind": kind, "note": note})

    def view(self, label, cam, look, fov=60):
        self.views.append({"label": label, "cam": [cam[0] + self.x0, cam[1], cam[2]], "look": [look[0] + self.x0, look[1], look[2]], "fov": fov})

    def finish(self):
        """Turn the lot about its origin by self.rot (parts, spots, views, bounds) -> world coordinates."""
        if not self.rot:
            return self
        Rw = Ry(self.rot)
        o = np.array([self.x0, 0.0, 0.0])
        for p in self.parts:
            c = np.asarray(p["cf"][:3], float)
            R = np.asarray(p["cf"][3:12], float).reshape(3, 3)
            p["cf"] = [*(o + Rw @ (c - o)).tolist(), *(Rw @ R).ravel().tolist()]
        for sp_ in self.spots:
            q = o + Rw @ (np.array([sp_["x"], 0, sp_["z"]]) - o)
            sp_["x"], sp_["z"] = round(float(q[0]), 2), round(float(q[2]), 2)
            sp_["yaw"] = (sp_["yaw"] + self.rot + 180) % 360 - 180
            a = math.radians(sp_["yaw"])
            sp_["facing"] = [round(-math.sin(a), 3), round(-math.cos(a), 3)]
        for v in self.views:
            for k in ("cam", "look"):
                v[k] = (o + Rw @ (np.array(v[k]) - o)).tolist()
        if self.bounds:
            x0, x1, z0, z1 = self.bounds
            C = np.array([[x, 0, z] for x in (x0, x1) for z in (z0, z1)])
            W = (C - o) @ Rw.T + o
            self.bounds = (W[:, 0].min(), W[:, 0].max(), W[:, 2].min(), W[:, 2].max())
        f = Rw @ np.array([0, 0, -1.0])
        self.front_dir = [round(float(f[0]), 3), round(float(f[2]), 3)]
        return self

    # rooms ------------------------------------------------------------------------------------------------
    def wall(self, name, axis, fixed, a, b, H, thick, color, mat="SmoothPlastic", openings=(), inner=1, y0=0.0,
             wainscot=None, base_col=WHITE, trim=True, frame_col=WHITE):
        """An axis-aligned wall: axis 'x' runs along X at z = fixed; 'z' runs along Z at x = fixed (local coords).
        openings: [(u_centre, width, bottom, height, kind)] with kind 'window' | 'door' | 'arch' | 'gap'.
        inner = +1 / -1: the room side is at fixed + inner (axis 'x': +z / -z; axis 'z': +x / -x)."""
        cg = f"{self.name}.{name}"
        common = dict(wall=True, cutgroup=cg, cast=False, group=name, role="wall")
        ops = sorted(openings, key=lambda o: o[0])

        def piece(nm, u0, u1, v0, v1, col=color, m=mat, depth=thick, off=0.0, tr=0.0, role="wall"):
            if u1 - u0 < 1e-3 or v1 - v0 < 1e-3:
                return
            uc, vc = (u0 + u1) / 2, (v0 + v1) / 2
            f = fixed + inner * off
            if axis == "x":
                c, size = (uc, vc, f), (u1 - u0, v1 - v0, depth)
            else:
                c, size = (f, vc, uc), (depth, v1 - v0, u1 - u0)
            kw = dict(common, role=role)
            self.box(f"{name}_{nm}", c, size, col, m, tr=tr, **kw)

        u = a
        for i, (uc, w, ob, oh, kind) in enumerate(ops):
            u0, u1 = uc - w / 2, uc + w / 2
            piece(f"seg{i}", u, u0, y0, y0 + H)
            if ob > 0:
                piece(f"below{i}", u0, u1, y0, y0 + ob)
            piece(f"above{i}", u0, u1, y0 + ob + oh, y0 + H)
            u = u1
            if kind == "window":
                fc, ft, fd = frame_col, 0.35, thick + 0.3
                piece(f"wf{i}a", u0, u1, y0 + ob, y0 + ob + ft, fc, "SmoothPlastic", fd)
                piece(f"wf{i}b", u0, u1, y0 + ob + oh - ft, y0 + ob + oh, fc, "SmoothPlastic", fd)
                piece(f"wf{i}c", u0, u0 + ft, y0 + ob, y0 + ob + oh, fc, "SmoothPlastic", fd)
                piece(f"wf{i}d", u1 - ft, u1, y0 + ob, y0 + ob + oh, fc, "SmoothPlastic", fd)
                piece(f"wm{i}v", uc - 0.1, uc + 0.1, y0 + ob, y0 + ob + oh, fc, "SmoothPlastic", 0.25)
                piece(f"wm{i}h", u0, u1, y0 + ob + oh * 0.62 - 0.1, y0 + ob + oh * 0.62 + 0.1, fc, "SmoothPlastic", 0.25)
                piece(f"glass{i}", u0 + ft, u1 - ft, y0 + ob + ft, y0 + ob + oh - ft, GLASS_C, "Glass", 0.1, tr=0.5, role="glass")
                piece(f"sill{i}", u0 - 0.3, u1 + 0.3, y0 + ob - 0.25, y0 + ob, fc, "SmoothPlastic", 0.7, off=0.35 + thick / 2 - 0.35)
            elif kind == "arch":
                fc = frame_col
                piece(f"af{i}a", u0 - 0.35, u0, y0, y0 + ob + oh + 0.35, fc, "SmoothPlastic", thick + 0.3)
                piece(f"af{i}b", u1, u1 + 0.35, y0, y0 + ob + oh + 0.35, fc, "SmoothPlastic", thick + 0.3)
                piece(f"af{i}c", u0 - 0.35, u1 + 0.35, y0 + ob + oh, y0 + ob + oh + 0.35, fc, "SmoothPlastic", thick + 0.3)
        piece("seg_end", u, b, y0, y0 + H)
        # trims on the room side: baseboard, crown moulding, wainscot with a chair rail
        doors = [(uc - w / 2 - 0.4, uc + w / 2 + 0.4) for uc, w, ob, oh, kind in ops if kind in ("door", "arch", "gap") and ob <= 0.01]

        def runs(lo_, hi_):
            out, cur = [], lo_
            for d0, d1 in sorted(doors):
                if d1 <= cur or d0 >= hi_:
                    continue
                if d0 > cur:
                    out.append((cur, d0))
                cur = max(cur, d1)
            if cur < hi_:
                out.append((cur, hi_))
            return out

        off = thick / 2 + 0.08
        for j, (r0, r1) in enumerate(runs(a + thick, b - thick) if trim else []):
            if wainscot:
                wc, wh = wainscot
                piece(f"wain{j}", r0, r1, y0, y0 + wh, wc, "SmoothPlastic", 0.12, off=off - 0.02, role="trim")
                piece(f"rail{j}", r0, r1, y0 + wh - 0.1, y0 + wh + 0.25, base_col, "SmoothPlastic", 0.3, off=off + 0.04, role="trim")
            piece(f"base{j}", r0, r1, y0, y0 + 0.7, base_col, "SmoothPlastic", 0.3, off=off + 0.06, role="trim")
        if trim:
            piece("crown", a + thick, b - thick, y0 + H - 0.45, y0 + H, base_col, "SmoothPlastic", 0.3, off=off + 0.06, role="trim")
        return cg

    def room(self, W, D, H=14.0, wall_col=CREAM, wall_mat="SmoothPlastic", floor_col=WOOD_L, floor_mat="WoodPlanks", thick=0.8,
             back=(), left=(), right=(), front=(), wainscot=None, ceiling_col=hx("f2efe8"), base_col=WHITE, frame_col=WHITE, floor_parts=True,
             walls=None):
        """A closed room centred on the lot origin: interior x in [-W/2, W/2], z in [-D/2, D/2], floor top at floor_y.
        back = +Z wall (faces the default camera), front = -Z wall (cut away when the camera is outside it),
        left = -X wall, right = +X wall. walls: per-wall colours {'back': (col, mat), ...}."""
        fy = self.floor_y
        self.W, self.D, self.H = W, D, H
        t = thick
        walls = walls or {}
        if floor_parts:
            self.slab("floor", -W / 2 - t, W / 2 + t, -D / 2 - t, D / 2 + t, fy, 1.0, floor_col, floor_mat, role="floor", group="Room")
        spec = {"back": ("x", D / 2 + t / 2, -W / 2 - t, W / 2 + t, back, -1),
                "front": ("x", -D / 2 - t / 2, -W / 2 - t, W / 2 + t, front, 1),
                "left": ("z", -W / 2 - t / 2, -D / 2, D / 2, left, 1),
                "right": ("z", W / 2 + t / 2, -D / 2, D / 2, right, -1)}
        for nm, (axis, fixed, a, b, ops, inner) in spec.items():
            col, mat = walls.get(nm, (wall_col, wall_mat))
            self.wall(nm, axis, fixed, a, b, H, t, col, mat, ops, inner, fy, wainscot=wainscot, base_col=base_col, frame_col=frame_col,
                      trim=True)
        # the ceiling: a mesh slab (director.ground_y never lands props on it), cut away when the camera is above it
        self.box("ceiling", (0, fy + H + 0.25, 0), (W + 2 * t, 0.5, D + 2 * t), ceiling_col, "SmoothPlastic", kind="mesh",
                 mesh={"key": "own_ceiling"}, wall=True, cutgroup=f"{self.name}.ceiling", cast=False, group="Room", role="ceiling")
        self.bounds = (self.x0 - W / 2 - 3, self.x0 + W / 2 + 3, -D / 2 - 3, D / 2 + 3)

    def on_wall(self, key, which, u, y, s=1.0, out=0.0, **extra):
        """A prop mounted on the inner face of a room wall (u = position along the wall), cut away with that wall."""
        W, D, t = self.W, self.D, 0.8
        depth = PROP_LIB[key]["size"][2] * s
        d = 0.02 + depth / 2 + out
        if which == "back":
            x, z, yaw = u, D / 2 - d, 0
        elif which == "front":
            x, z, yaw = u, -D / 2 + d, 180
        elif which == "left":
            x, z, yaw = -W / 2 + d, u, 90
        else:
            x, z, yaw = W / 2 - d, u, -90
        return self.place(key, x, z, yaw, y=self.floor_y + y, s=s, wall=True, cutgroup=f"{self.name}.{which}", cast=False, **extra)

    def ceiling_light(self, x, z, key="ceiling_light"):
        h = PROP_LIB[key]["size"][1]
        return self.place(key, x, z, 0, y=self.floor_y + self.H - h, wall=True, cutgroup=f"{self.name}.ceiling", cast=False)

    def surround(self, W, D, seed=0, ground=GREEN):
        """Outside an interior lot: lawn, a path, trees, a fence and houses behind (seen through the windows)."""
        fy = self.floor_y
        self.slab("lawn", -60, 60, -60, 60, fy - 0.15, 1.0, hx("64b45a"), "Grass", role="ground", group="Outside")
        self.slab("sidewalk", -W / 2 - 1, W / 2 + 1, -D / 2 - 9, -D / 2 - 1, fy - 0.05, 0.6, hx("d2d0cc"), "Concrete", role="ground", group="Outside")
        rng = np.random.default_rng(seed)
        for i, x in enumerate(np.linspace(-W / 2 - 4, W / 2 + 4, 5)):
            self.place("tree", x + rng.uniform(-2, 2), D / 2 + 12 + rng.uniform(-2, 3), rng.uniform(0, 360), y=fy - 0.15, s=rng.uniform(0.85, 1.1))
        for side in (-1, 1):
            for z in np.linspace(-D / 2 + 2, D / 2 - 2, 3):
                self.place("tree", side * (W / 2 + 11 + rng.uniform(0, 4)), z + rng.uniform(-2, 2), rng.uniform(0, 360), y=fy - 0.15,
                           s=rng.uniform(0.8, 1.05))
            self.place("bush", side * (W / 2 + 4), D / 2 - 4, 0, y=fy - 0.15)
            self.place("bush", side * (W / 2 + 4), -D / 2 + 3, 0, y=fy - 0.15)
        for x in np.arange(-W / 2 - 4, W / 2 + 5, 8):
            self.place("fence", x, D / 2 + 6, 0, y=fy - 0.15)
        for i, x in enumerate((-W / 2 - 6, W / 2 + 6)):
            self.place("house", x, D / 2 + 30, 180, y=fy - 0.15)
        self.place("house", 0, D / 2 + 36, 180, y=fy - 0.15, s=1.2)
        for side in (-1, 1):
            self.place("house", side * (W / 2 + 26), 0, side * 90, y=fy - 0.15)


# ------------------------------------------------------------------------------------------------ the lots
LOT_X = {"LivingRoom": 6000, "Kitchen": 6200, "Bedroom": 6400, "Classroom": 6600, "Cafe": 6800, "Courtroom": 7000,
         "Street": 7200, "Park": 7400, "Bakery": 7600, "Office": 7800, "Bank": 8000}


def interior_views(L: Lot, eye_look_z=None, eye_x=None, eye_look_x=None):
    W, D, H = L.W, L.D, L.H
    ex = W * 0.12 if eye_x is None else eye_x
    L.view("eye", (ex, 5.2, -D / 2 + 2.0), (ex - W * 0.16 if eye_look_x is None else eye_look_x, 4.0, D / 2 - 6 if eye_look_z is None else eye_look_z), 62)
    L.view("wide", (-W * 0.16, 10.0, -D / 2 - 9.0), (0, 3.2, 2.0), 74)


def set_living_room():
    L = Lot("LivingRoom", LOT_X["LivingRoom"])
    W, D = 34, 28
    L.room(W, D, wall_col=hx("fae6c8"), floor_col=hx("c88c5a"), wainscot=(hx("8cbedc"), 4.2),
           back=[(-8, 6, 4.0, 6.5, "window"), (8, 6, 4.0, 6.5, "window")], right=[(6, 4.6, 0, 7.4, "door")],
           left=[(0, 7, 4.0, 6.5, "window")])
    L.place("door", W / 2 + 0.4, 6, 90, wall=True, cutgroup="LivingRoom.right", cast=False)
    L.place("rug", 0, 1.5, 0)
    L.place("sofa", 0, D / 2 - 3.0, 0)
    L.place("coffee_table", 0, 2.0, 0)
    L.place("books", -0.8, 2.0, 15, y=1.4, s=0.7)
    L.place("coffee_cup", 1.1, 1.6, 0, y=1.4)
    L.place("armchair", -9.5, 3.0, 65)
    L.place("armchair", 9.0, 1.0, -70)
    L.place("tv", 0, -D / 2 + 1.4, 180)
    L.place("plant", -6.5, -D / 2 + 1.6, 0)
    L.place("plant", 6.0, -D / 2 + 1.6, 0)
    L.place("bookshelf", -W / 2 + 1.0, -6.0, 90)
    L.place("lamp", -W / 2 + 1.6, 7.5, 0)
    L.place("lamp", 5.0, D / 2 - 1.8, 0)
    L.place("plant", W / 2 - 1.6, D / 2 - 1.6, 0)
    L.place("nightstand", -5.2, D / 2 - 1.3, 0)
    L.place("table_lamp", -5.2, D / 2 - 1.3, 0, y=2.0)
    L.place("photo_frame", -4.7, D / 2 - 1.0, 10, y=2.0, s=0.8)
    L.place("beanbag", 11.5, -6.5, 30)
    L.place("toy_box", W / 2 - 2.0, -D / 2 + 1.5, 180)
    L.on_wall("painting", "back", 0, 9.5, s=1.1)
    L.on_wall("clock", "left", 6.0, 10.5, s=0.9)
    L.on_wall("photo_frame", "left", -3.5, 9.0, s=1.3)
    L.on_wall("curtains", "back", -8, 3.6)
    L.on_wall("curtains", "back", 8, 3.6)
    L.ceiling_light(0, 1.0, "ceiling_fan")
    L.ceiling_light(-9, 8)
    L.ceiling_light(9, 8)
    L.surround(W, D, 1)
    L.spot("sofa_seat_left", -2.2, D / 2 - 3.4, 0, "sit", y=1.95)
    L.spot("sofa_seat_right", 2.2, D / 2 - 3.4, 0, "sit", y=1.95)
    L.spot("sofa_front", 0, 6.5, 0, note="standing between the sofa and the coffee table")
    L.spot("tv_front", 0, -7.5, 180, note="facing the TV")
    L.spot("armchair_left", -9.5, 3.0, 65, "sit", y=1.95)
    L.spot("armchair_right", 9.0, 1.0, -70, "sit", y=1.95)
    L.spot("door", W / 2 - 3, 6, 90, note="just inside the front door")
    L.spot("bookshelf", -W / 2 + 4.5, -6, -90)
    L.spot("centre", 4, -3, 0)
    L.spot("window", 8, D / 2 - 3.5, 180, note="looking out of the right back window (sofa is to its left)")
    interior_views(L)
    return L


def set_kitchen():
    L = Lot("Kitchen", LOT_X["Kitchen"])
    W, D = 32, 26
    L.room(W, D, wall_col=hx("fff5dc"), floor_col=hx("e6e1d7"), floor_mat="Marble",
           back=[(0, 7, 5.2, 5.5, "window")], left=[(-2, 4.6, 0, 7.4, "door")], right=[(4, 6, 4.0, 6.5, "window")])
    L.place("door", -W / 2 - 0.4, -2, 90, wall=True, cutgroup="Kitchen.left", cast=False)
    # checker tiles on the floor
    for i in range(int(W / 4)):
        for j in range(int(D / 4)):
            if (i + j) % 2 == 0:
                L.box(f"tile{i}_{j}", (-W / 2 + 2 + i * 4, 0.01, -D / 2 + 2 + j * 4), (4, 0.02, 4), hx("6eaadc"), "SmoothPlastic", role="floor",
                      group="Floor", block=False)
    # back counter run: counter | stove | counter | fridge
    zb = D / 2 - 1.35
    L.place("kitchen_counter", -0.5, zb, 0)
    L.place("faucet", 1.3, zb + 0.6, 0, y=3.2)
    L.place("stove", -6.0, zb, 0)
    L.place("kitchen_counter", -11.6, zb, 0, s=0.8)
    L.place("fridge", 6.0, zb - 0.1, 0)
    L.place("kitchen_counter", 11.5, zb, 0, s=0.8)
    L.place("microwave", 11.5, zb, 0, y=3.2 * 0.8 + 0.02)
    L.place("toaster", -1.9, zb + 0.2, 0, y=3.2)
    L.place("coffee_cup", -3.2, zb, 0, y=3.2)
    L.place("fruit_bowl", -12.0, zb, 0, y=2.56)
    L.on_wall("upper_cabinet", "back", -10.5, 7.0, s=0.8)
    L.on_wall("upper_cabinet", "back", 12.0, 7.0, s=0.65)
    L.on_wall("clock", "back", -5.5, 9.0, s=0.75)
    # backsplash tiles
    L.box("backsplash", (-3.5, 4.4, D / 2 - 0.05), (16, 2.4, 0.12), hx("aadcf0"), "SmoothPlastic", wall=True, cutgroup="Kitchen.back",
          cast=False, role="trim", group="back")
    # island with stools
    L.place("kitchen_counter", 0, 2.5, 180, s=0.85)
    for x in (-2.4, 0, 2.4):
        L.place("bar_stool", x, -0.4, 0, s=0.85)
    L.place("cake", -1.5, 2.5, 0, y=3.2 * 0.85)
    L.place("pizza", 1.8, 2.5, 0, y=3.2 * 0.85, s=0.6)
    # dining corner
    L.place("dining_table", -8.5, -5.5, 90)
    for z, yaw in ((-8.4, 0), (-2.6, 180)):
        L.place("chair", -8.5, z, yaw)
    for x, yaw in ((-10.4, -90), (-6.6, 90)):
        for z in (-6.9, -4.1):
            L.place("chair", x, z, yaw)
    L.place("fruit_bowl", -8.5, -5.5, 0, y=3.0)
    L.place("plant", W / 2 - 1.8, -D / 2 + 1.8, 0)
    L.place("plant", -W / 2 + 1.8, -D / 2 + 1.8, 0)
    L.place("trash_can", W / 2 - 1.4, D / 2 - 6, 0, s=0.6)
    L.ceiling_light(0, 2.5)
    L.ceiling_light(-8.5, -5.5)
    L.ceiling_light(8, -4, "flush_light")
    L.surround(W, D, 2)
    L.spot("counter_front", -0.5, D / 2 - 4.2, 0, note="at the sink, facing the back counter (yaw 180 to face the room)")
    L.spot("stove_front", -6.0, D / 2 - 4.2, 180)
    L.spot("fridge_front", 6.0, D / 2 - 4.6, 180)
    L.spot("island_stool_mid", 0, -0.4, 180, "sit", y=2.75)
    L.spot("island_front", 4.8, 1.0, 90)
    L.spot("table_head", -8.5, -8.4, 180, "sit", y=1.72)
    L.spot("table_side", -10.4, -4.1, -90, "sit", y=1.72)
    L.spot("door", -W / 2 + 3, -2, -90, note="just inside the side door")
    L.spot("centre", 5, -6, 0)
    interior_views(L)
    return L


def set_bedroom():
    L = Lot("Bedroom", LOT_X["Bedroom"])
    W, D = 30, 26
    L.room(W, D, wall_col=hx("c8dcf5"), floor_col=hx("d2a06e"), back=[(9, 6, 4.0, 6.5, "window")],
           right=[(-5, 4.6, 0, 7.4, "door")], left=[(2, 6, 4.0, 6.5, "window")], wainscot=(WHITE, 3.5))
    L.place("door", W / 2 + 0.4, -5, 90, wall=True, cutgroup="Bedroom.right", cast=False)
    L.place("rug", -1.5, 3.0, 90, s=0.85)
    L.place("bed", -3.0, D / 2 - 4.2, 180)
    L.place("nightstand", -7.0, D / 2 - 1.2, 0)
    L.place("nightstand", 1.0, D / 2 - 1.2, 0)
    L.place("table_lamp", -7.0, D / 2 - 1.2, 0, y=2.0)
    L.place("table_lamp", 1.0, D / 2 - 1.2, 0, y=2.0)
    L.place("phone", 1.4, D / 2 - 1.5, 160, y=2.0)
    L.place("wardrobe", W / 2 - 1.3, 6.0, -90)
    L.place("desk", -W / 2 + 3.4, -5.5, -90)
    L.place("laptop", -W / 2 + 3.0, -5.5, -90, y=2.62)
    L.place("office_chair", -W / 2 + 5.6, -5.5, -90)
    L.place("books", -W / 2 + 2.6, -7.5, 80, y=2.62, s=0.6)
    L.place("bookshelf", -W / 2 + 1.0, 4.5, 90, s=0.9)
    L.place("toy_box", 6.0, -D / 2 + 1.4, 180)
    L.place("beanbag", 9.5, -7.0, -40)
    L.place("plant", W / 2 - 1.6, -D / 2 + 1.6, 0)
    L.place("backpack", 4.0, D / 2 - 1.0, 20)
    L.place("lamp", 7.0, D / 2 - 1.6, 0)
    L.on_wall("poster", "back", -3.0, 7.5)
    L.on_wall("poster", "left", -6, 7.0, s=0.9)
    L.on_wall("curtains", "back", 9, 3.6)
    L.ceiling_light(-2, 1, "flush_light")
    L.surround(W, D, 3)
    L.spot("bed_side", 1.5, D / 2 - 6.0, -90, note="standing at the bed's right side, facing it")
    L.spot("bed_sit", -0.6, D / 2 - 6.5, -90, "sit", y=1.75, note="sitting on the bed's edge facing +X")
    L.spot("bed_lie", -3.0, D / 2 - 5.0, 180, "lie", y=1.8)
    L.spot("desk_chair", -W / 2 + 5.6, -5.5, -90, "sit", y=2.0)
    L.spot("wardrobe_front", W / 2 - 4.2, 6.0, -90)
    L.spot("door", W / 2 - 3, -5, 90)
    L.spot("window", 9, D / 2 - 3.5, 180)
    L.spot("centre", 3, -2, 0)
    interior_views(L)
    return L


def set_classroom():
    L = Lot("Classroom", LOT_X["Classroom"])
    W, D = 38, 34
    L.room(W, D, wall_col=hx("f5f0c8"), floor_col=hx("dcc8a0"), floor_mat="WoodPlanks", wainscot=(hx("78b48c"), 3.8),
           left=[(-8, 7, 4.0, 7.0, "window"), (2, 7, 4.0, 7.0, "window"), (11, 7, 4.0, 7.0, "window")],
           right=[(-11, 4.6, 0, 7.4, "door")])
    L.place("door", W / 2 + 0.4, -11, 90, wall=True, cutgroup="Classroom.right", cast=False)
    L.place("chalkboard", 0, D / 2 - 0.5, 0, y=1.0)
    L.on_wall("clock", "back", 11, 9.0, s=0.8)
    L.on_wall("bulletin_board", "back", -11.5, 5.0)
    # alphabet strip above the board
    for i in range(14):
        L.box(f"abc{i}", (-9.1 + i * 1.4, 11.6, D / 2 - 0.1), (1.2, 1.2, 0.08), BOOK_COLS[i % len(BOOK_COLS)], wall=True,
              cutgroup="Classroom.back", cast=False, role="trim", group="back")
    L.place("desk", -6.0, D / 2 - 6.5, 180, s=0.9)
    L.place("office_chair", -6.0, D / 2 - 3.6, 180, s=0.9)
    L.place("globe", -7.4, D / 2 - 6.5, 0, y=2.62 * 0.9)
    L.place("apple", -4.8, D / 2 - 6.9, 0, y=2.62 * 0.9)
    L.place("books", -5.6, D / 2 - 6.2, 30, y=2.62 * 0.9, s=0.6)
    # student desks: 3 rows x 4 columns facing the board (+Z)
    for r, z in enumerate((2.5, -3.5, -9.5)):
        for c, x in enumerate((-10.5, -3.5, 3.5, 10.5)):
            L.place("school_desk", x, z, 180)
    L.place("lockers", W / 2 - 1.0, 6.0, -90)
    L.place("lockers", -0.0 + 6, -D / 2 + 1.0, 180)
    L.place("cubby_shelf", -12, -D / 2 + 0.9, 180)
    L.place("bookshelf", W / 2 - 1.0, -4.0, -90, s=0.9)
    L.place("plant", -W / 2 + 1.6, D / 2 - 1.6, 0)
    L.place("plant", W / 2 - 1.6, D / 2 - 1.6, 0)
    L.place("trash_can", W / 2 - 1.5, -14.5, 0, s=0.55)
    L.place("backpack", -12.0, -5.2, 160, s=0.8)
    L.place("backpack", 5.2, 1.0, -30, s=0.8)
    for x in (-9, 9):
        for z in (-8, 6):
            L.ceiling_light(x, z, "flush_light")
    L.surround(W, D, 4)
    L.spot("board_front", 2.5, D / 2 - 3.0, 180, note="teacher at the board, facing the class")
    L.spot("teacher_desk", -6.0, D / 2 - 3.6, 180, "sit", y=1.8)
    for r, z in enumerate((2.5, -3.5, -9.5)):
        for c, x in enumerate((-10.5, -3.5, 3.5, 10.5)):
            L.spot(f"desk_r{r + 1}c{c + 1}", x, z - 1.05, 180, "sit", y=1.65, note="student seat facing the board")
    L.spot("aisle_front", 0, 6.5, 180)
    L.spot("aisle_back", 0, -13.0, 180)
    L.spot("lockers", W / 2 - 4.0, 6.0, -90)
    L.spot("door", W / 2 - 3, -11, 90)
    interior_views(L, eye_look_z=D / 2 - 4, eye_x=0.4)
    return L


def set_cafe():
    L = Lot("Cafe", LOT_X["Cafe"])
    W, D = 34, 28
    L.room(W, D, wall_col=hx("f0dcc3"), floor_col=hx("8c5a3c"), floor_mat="WoodPlanks", wainscot=(hx("3c8c78"), 4.0),
           left=[(-5, 7, 3.5, 7.0, "window"), (5, 7, 3.5, 7.0, "window")], right=[(-7, 4.6, 0, 7.4, "door")])
    L.place("door", W / 2 + 0.4, -7, 90, wall=True, cutgroup="Cafe.right", cast=False)
    # back: counter with machines, pastry case, menu boards
    L.place("shop_counter", -2.5, D / 2 - 6.0, 180)
    L.place("display_case", 7.2, D / 2 - 6.0, 0, s=0.8)
    L.place("espresso_machine", -4.0, D / 2 - 6.0, 180, y=3.28)
    L.place("cash_register", 0.0, D / 2 - 6.2, 180, y=3.28)
    L.place("cupcake", -1.6, D / 2 - 6.6, 0, y=3.28)
    L.place("coffee_cup", 1.4, D / 2 - 6.6, 0, y=3.28)
    L.place("kitchen_counter", -6.0, D / 2 - 1.3, 0)
    L.place("coffee_cup", -8.5, D / 2 - 1.3, 0, y=3.2)
    L.on_wall("menu_board", "back", -6.0, 7.0)
    L.on_wall("menu_board", "back", 3.0, 7.0, s=0.75)
    # tables
    for x, z in ((-11, -1), (-4, -2), (3, -1), (-11, -9), (-4, -9.5), (3, -9)):
        L.place("bistro_table", x, z, 0, s=0.9)
        L.place("cafe_chair", x - 2.2, z, -90)
        L.place("cafe_chair", x + 2.2, z, 90)
        L.place("coffee_cup", x + 0.4, z - 0.3, 0, y=2.88 * 0.9)
    L.place("cupcake", -4.4, -2.0, 0, y=2.88 * 0.9)
    L.place("newspaper", 2.6, -1.0, 20, y=2.88 * 0.9)
    # window bench seating on the left
    L.box("bench_seat", (-W / 2 + 1.4, 1.0, 0), (2.4, 2.0, 18), hx("a0643c"), "Wood", group="Bench")
    L.box("bench_cushion", (-W / 2 + 1.4, 2.15, 0), (2.2, 0.3, 17.6), hx("dc5a46"), "Fabric", group="Bench")
    L.place("plant", W / 2 - 1.8, -D / 2 + 1.8, 0)
    L.place("plant", 11.5, 3.0, 0)
    for x in (-9, -2, 5):
        L.ceiling_light(x, -5)
    L.ceiling_light(-2.5, D / 2 - 6.0)
    L.ceiling_light(7, D / 2 - 6.0)
    L.surround(W, D, 5)
    L.spot("counter_front", -2.5, D / 2 - 9.6, 0, note="customer at the counter facing the barista")
    L.spot("counter_back", -2.5, D / 2 - 3.6, 180, note="barista behind the counter")
    L.spot("register", 0.0, D / 2 - 9.6, 0)
    L.spot("pastry_case", 7.2, D / 2 - 9.4, 0)
    L.spot("table1_left", -13.2, -1, 90, "sit", y=1.71)
    L.spot("table1_right", -8.8, -1, -90, "sit", y=1.71)
    L.spot("table3_left", 0.8, -1, 90, "sit", y=1.71)
    L.spot("window_bench", -W / 2 + 1.6, -6, -90, "sit", y=2.3)
    L.spot("door", W / 2 - 3, -7, 90)
    L.spot("centre", 8, -5, 0)
    interior_views(L, eye_x=9.0)
    return L


def set_courtroom():
    L = Lot("Courtroom", LOT_X["Courtroom"])
    W, D, H = 42, 46, 18
    L.room(W, D, H, wall_col=hx("f0e6d2"), floor_col=hx("e6dcc8"), floor_mat="Marble", wainscot=(hx("8c5532"), 5.0),
           left=[(-12, 6, 4.5, 11.0, "window"), (0, 6, 4.5, 11.0, "window"), (12, 6, 4.5, 11.0, "window")],
           right=[(-12, 6, 4.5, 11.0, "window"), (0, 6, 4.5, 11.0, "window"), (12, 6, 4.5, 11.0, "window")],
           front=[(0, 5.0, 0, 8.0, "door")], base_col=hx("6e4228"), frame_col=hx("f5f0e6"))
    L.place("door", 0, -D / 2 - 0.4, 0, s=1.1, wall=True, cutgroup="Courtroom.front", cast=False)
    # carpet aisle
    L.box("aisle", (0, 0.02, -8), (5, 0.04, 26), hx("b4323c"), "Fabric", role="floor", group="Floor", block=False)
    # the bench, the throne behind it on the platform
    zb = D / 2 - 7.5
    L.place("judge_bench", 0, zb, 0)
    L.place("throne", 0, zb + 2.2, 0, y=1.5, s=0.85)
    L.place("flag", -9.0, D / 2 - 2.0, 0)
    L.place("flag", 9.0, D / 2 - 2.0, 0)
    L.on_wall("clock", "back", -13.0, 11, s=1.0)
    # a big seal on the back wall
    for i, (dia, c) in enumerate(((7.0, GOLD), (5.6, hx("1e3c78")))):
        L.box(f"seal{i}", (0, 12.5, D / 2 - 0.1 - i * 0.12), (0.2, dia, dia), c, "SmoothPlastic", kind="cyl", R=Ry(90), wall=True,
              cutgroup="Courtroom.back", cast=False, role="trim", group="back")
    L.box("seal_star", (0, 12.5, D / 2 - 0.4), (2.4, 2.4, 0.1), GOLD, R=Rz(45), wall=True, cutgroup="Courtroom.back", cast=False,
          role="trim", group="back")
    # tall columns on the back wall
    for x in (-15, 15):
        L.box(f"col{x}", (x, H / 2, D / 2 - 0.9), (H, 1.6, 1.6), hx("f5f0e6"), "Marble", kind="cyl", R=Rz(90), wall=True,
              cutgroup="Courtroom.back", cast=False, role="trim", group="back")
    L.place("witness_stand", -10.0, zb - 1.0, 30)
    L.place("desk", 10.0, zb - 1.5, 0, s=0.8)          # the clerk
    L.place("office_chair", 10.0, zb + 1.0, 0, s=0.85)
    # counsel tables facing the bench
    for x in (-7.5, 7.5):
        L.place("desk", x, 3.5, 180)
        L.place("office_chair", x - 1.2, 0.9, 180, s=0.9)
        L.place("office_chair", x + 1.4, 0.9, 180, s=0.9)
    L.place("books", -7.0, 3.2, 10, y=2.62, s=0.7)
    L.place("newspaper", 8.0, 3.4, -10, y=2.62)
    # the bar with a gate gap at the aisle
    L.place("railing", -9.0, -2.0, 0, s=1.0)
    L.place("railing", 9.0, -2.0, 0, s=1.0)
    # the gallery
    for z in (-6.5, -11.0, -15.5):
        L.place("pew", -9.0, z, 0)
        L.place("pew", 9.0, z, 0)
    for x, z in ((-W / 2 + 1.6, -D / 2 + 1.6), (W / 2 - 1.6, -D / 2 + 1.6)):
        L.place("plant", x, z, 0)
    for x in (-10, 10):
        for z in (-12, 4, 14):
            L.ceiling_light(x, z)
    L.surround(W, D, 6)
    L.spot("judge_bench", 0, zb + 2.0, 180, "sit", y=1.5 + 1.95 * 0.85, note="the judge on the throne behind the bench")
    L.spot("judge_standing", 4.6, zb + 0.9, 180, y=1.5, note="standing at the bench on the platform")
    L.spot("witness_stand", -10.0, zb - 1.0, 210, y=1.0, note="inside the witness box")
    L.spot("defense_table", -8.7, 0.9, 0, "sit", y=1.9, note="sitting at the left counsel table, facing the bench")
    L.spot("prosecution_table", 8.9, 0.9, 0, "sit", y=1.9)
    L.spot("podium_front", 0, 1.5, 0, note="addressing the bench in the aisle")
    L.spot("aisle", 0, -9.0, 0)
    L.spot("gallery_left", -9.0, -7.0, 0, "sit", y=1.6)
    L.spot("gallery_right", 9.0, -11.5, 0, "sit", y=1.6)
    L.spot("door", 0, -D / 2 + 3, 0)
    L.view("eye", (3.5, 5.4, -5.0), (-1.0, 6.0, D / 2 - 6), 62)
    L.view("wide", (-8.0, 12.0, -D / 2 - 9), (0, 4.0, 2.0), 74)
    return L


def facade(L: Lot, x, z, w, h, col, mat="Brick", sign=None, sign_col=RED, awning=True, shop=True, yaw=0, depth=12.0, door_col=None,
           floors=2, win_col=hx("8cc8f0"), trim=WHITE, letter_col=WHITE):
    """A street building whose front (shop window, door, awning, sign, upper windows) faces -Z (yaw 180: faces +Z).
    x, z: the front's centre at ground level (local coords)."""
    R = Ry(yaw)
    nm = f"bld{len(L.parts)}"

    def put(name, c, size, colr, m="SmoothPlastic", **kw):
        wc = np.array([x, 0, z]) + R @ np.asarray(c, float)
        return L.box(f"{nm}_{name}", tuple(wc), size, colr, m, R=R, group=nm, role="building", **kw)

    put("body", (0, h / 2, depth / 2), (w, h, depth), col, mat)
    put("parapet", (0, h + 0.4, 0.4), (w + 0.4, 0.8, 1.0), trim)
    put("cornice", (0, h - 0.6, -0.15), (w + 0.2, 0.5, 0.5), trim)
    if shop:
        put("base", (0, 0.4, -0.1), (w, 0.8, 0.3), lit(col, 0.7))
        sw = w - 6.5
        put("shopwin_frame", (-1.6, 3.7, -0.1), (sw + 0.6, 5.0, 0.3), trim)
        put("shopwin", (-1.6, 3.7, -0.22), (sw, 4.4, 0.1), win_col)
        for k in range(1, 3):
            put(f"mull{k}", (-1.6 - sw / 2 + k * sw / 3, 3.7, -0.3), (0.2, 4.4, 0.1), trim)
        put("door_frame", (w / 2 - 2.6, 3.7, -0.1), (3.4, 7.4, 0.3), trim)
        put("door", (w / 2 - 2.6, 3.5, -0.22), (2.8, 7.0, 0.1), door_col or lit(sign_col, 0.85))
        put("door_glass", (w / 2 - 2.6, 4.6, -0.3), (1.8, 3.0, 0.06), win_col)
        put("knob", (w / 2 - 3.6, 3.4, -0.36), (0.25, 0.25, 0.15), GOLD)
        if awning:
            for i in range(int(w // 1.5)):
                cc = sign_col if i % 2 == 0 else WHITE
                xx = -w / 2 + 0.75 + i * 1.5
                put(f"awn{i}", (xx, 8.3, -1.4), (1.5, 1.4, 2.8), cc, "Fabric", kind="wedge")
                put(f"awnf{i}", (xx, 7.4, -2.8), (1.5, 0.45, 0.1), cc, "Fabric")
        if sign:
            put("signboard", (0, 10.0, -0.25), (min(w - 2, len(sign) * 1.6 + 2), 2.2, 0.3), sign_col)
            px = 0.32
            for k, pc in enumerate(text_pieces(sign, 0, 9.2, -0.45, px, letter_col, 0.12)):
                _, c, s, colr, _o2 = pc
                put(f"ltr{k}", c, s, colr)
    fl0 = 11.0 if shop else 1.0
    nwin = max(1, int(w // 5))
    for f in range(floors if not shop else floors - 1):
        yb = fl0 + f * 6.0
        if yb + 4.5 > h:
            break
        for i in range(nwin):
            xx = -w / 2 + (i + 0.5) * w / nwin
            put(f"w{f}_{i}f", (xx, yb + 2.0, -0.08), (2.8, 3.6, 0.2), trim)
            put(f"w{f}_{i}g", (xx, yb + 2.0, -0.18), (2.3, 3.1, 0.06), win_col)
            put(f"w{f}_{i}s", (xx, yb + 0.15, -0.3), (3.2, 0.3, 0.6), trim)
            put(f"w{f}_{i}m", (xx, yb + 2.0, -0.23), (0.15, 3.1, 0.05), trim)


def set_street():
    L = Lot("Street", LOT_X["Street"], floor_y=0.4, interior=False)
    fy = 0.4
    # road along X at z in [-9, 9]; sidewalks (top 0.4) z in [9, 19] and [-19, -9]
    L.slab("ground", -80, 80, -80, 80, -0.05, 1.0, hx("5aaa50"), "Grass", role="ground", group="Ground")
    L.slab("road", -80, 80, -9, 9, 0.0, 0.6, hx("50525a"), "Asphalt", role="floor", group="Road")
    for s in (-1, 1):
        z0, z1 = (9, 20) if s > 0 else (-20, -9)
        L.slab(f"sidewalk{s}", -80, 80, z0, z1, fy, 0.9, hx("d2d0cc"), "Concrete", role="floor", group="Sidewalk")
        L.slab(f"curb{s}", -80, 80, s * 9.2 - 0.2, s * 9.2 + 0.2, fy + 0.02, 0.9, hx("e6e4e0"), "Concrete", role="floor", group="Sidewalk")
    for i in range(16):
        L.box(f"lane{i}", (-75 + i * 10, 0.01, 0), (5, 0.03, 0.35), YEL, role="floor", group="Road", block=False)
    for i in range(8):
        L.box(f"zebra{i}", (22 + (i - 3.5) * 0, 0.015, -7.5 + i * 2.1), (6, 0.03, 1.1), WHITE, role="floor", group="Road", block=False,
              R=np.eye(3))
    # shopfronts on the +Z side (fronts at z = 20, facing -Z)
    shops = [(-56, 18, 16, hx("f0b48c"), "Brick", "PIZZA", hx("e04848")), (-37, 18, 14, hx("8cc8e6"), "Concrete", "TOYS", hx("3c82dc")),
             (-18, 18, 18, hx("f5d26e"), "Brick", "CAFE", hx("3c9c78")), (2, 20, 15, hx("e68ca0"), "Brick", "BAKERY", hx("d2508c")),
             (22, 18, 20, hx("c8b4e6"), "Concrete", "BOOKS", hx("965ac8")), (41, 18, 16, hx("a0dca0"), "Brick", "SHOP", hx("2f8a4c")),
             (60, 18, 14, hx("f0c8a0"), "Brick", "BANK", hx("28508c"))]
    for x, w, h, col, mat, sign, sc in shops:
        facade(L, x, 20.0, w, h, col, mat, sign=sign, sign_col=sc, floors=3, letter_col=WHITE if sign != "TOYS" else YEL)
    # across the road: apartments and a corner shop (fronts at z = -20 facing +Z)
    across = [(-55, 20, 24, hx("dc8c6e"), "Brick", None), (-33, 22, 18, hx("f0e6c8"), "Concrete", "MARKET"), (-11, 20, 26, hx("8cb4dc"), "Brick", None),
              (11, 22, 20, hx("e6c88c"), "Brick", "SALON"), (33, 20, 24, hx("b4dcc8"), "Concrete", None), (55, 22, 18, hx("f0a0a0"), "Brick", "GAMES")]
    for x, w, h, col, mat, sign in across:
        facade(L, x, -20.0, w, h, col, mat, sign=sign, sign_col=[hx("e05050"), hx("3c82dc"), hx("e6a028")][int(abs(x)) % 3], yaw=180,
               shop=sign is not None, floors=4)
    # the street's ends: buildings across the road so the frame never runs out of town
    for s in (-1, 1):
        facade(L, s * 72, 0, 44, 26, hx("d2beaa"), "Brick", yaw=90 * s, shop=False, floors=4, depth=10)
    # street furniture
    for i, x in enumerate(np.arange(-66, 70, 16)):
        L.place("streetlight", x, 10.6, 0, y=fy)
        L.place("streetlight", x + 8, -10.6, 180, y=fy)
    for x in (-46, -28, 12, 32, 51):
        L.place("planter", x, 12.4, 0, y=fy, s=0.6)
        L.place("tree", x, 12.4, x * 7, y=fy + 1.4 * 0.6, s=0.55)
    for x in (-60, -24, 6, 44):
        L.place("tree", x, -13.0, x * 3, y=fy, s=0.7)
    L.place("park_bench", -9, 12.4, 180, y=fy)
    L.place("park_bench", 30, -12.5, 0, y=fy)
    L.place("mailbox", 12.0, 10.8, 180, y=fy)
    L.place("hydrant", -30.0, 10.4, 0, y=fy)
    L.place("trash_can", -3.0, 11.0, 0, y=fy, s=0.7)
    L.place("trash_can", 40.0, -11.0, 0, y=fy, s=0.7)
    L.place("bus_stop", -40, -14.0, 180, y=fy)
    L.place("sign_board", 52.0, 11.5, 0, y=fy, s=0.7)
    L.place("bicycle", 28.0, 11.0, 90, y=fy)
    L.place("car", -14.0, 4.5, 90)
    L.place("car", 38.0, -4.5, -90)
    L.bounds = (L.x0 - 70, L.x0 + 70, -28, 28)
    L.spot("crosswalk_near", 19.5, -10.2, 180, y=fy, note="at the crosswalk on the south sidewalk, facing the road")
    L.spot("crosswalk_far", 22, 10, 0, y=fy)
    L.spot("cafe_door", -18 + 18 / 2 - 2.6, 17.5, 180, y=fy, note="outside the CAFE door")
    L.spot("bakery_window", 2 - 1.6, 17.0, 180, y=fy, note="looking into the BAKERY window")
    L.spot("bank_door", 60 + 14 / 2 - 2.6, 17.5, 180, y=fy)
    L.spot("bench", -9, 12.4 - 0.2, 180, "sit", y=fy + 1.5)
    L.spot("bus_stop", -37, -11.2, 180, y=fy, note="waiting at the bus stop, facing the road")
    L.spot("sidewalk_north", -2, 14.5, 90, y=fy, note="walking lane along the shops (yaw 90 walks toward -X)")
    L.spot("sidewalk_south", 0, -15, -90, y=fy)
    L.spot("road_centre", 6, 0, 0, y=0.0)
    L.view("eye", (12.0, 5.6, -14.5), (2.0, 5.5, 16.0), 62)
    L.view("wide", (-24.0, 15.0, -6.0), (4.0, 4.0, 16.0), 70)
    return L


def set_park():
    L = Lot("Park", LOT_X["Park"], interior=False)
    L.slab("lawn", -72, 72, -72, 72, 0.0, 1.0, hx("64b45a"), "Grass", role="floor", group="Ground")
    # paths: a cross and a ring plaza around the fountain
    L.slab("path_x", -60, 60, -3, 3, 0.06, 0.2, hx("dcc8a0"), "Cobblestone", role="floor", group="Paths")
    L.slab("path_z", -3, 3, -60, 60, 0.06, 0.2, hx("dcc8a0"), "Cobblestone", role="floor", group="Paths")
    L.box("plaza", (0, -0.04, 0), (0.2, 26, 26), hx("e6d7b4"), "Cobblestone", kind="cyl", R=Rz(90), role="floor", group="Paths")
    L.floor_y = 0.06
    L.place("fountain", 0, 0, 0, y=0.06)
    # benches around the plaza facing the fountain
    for a in (45, 135, 225, 315):
        r = 11.5
        x, z = r * math.sin(math.radians(a)), r * math.cos(math.radians(a))
        L.place("park_bench", x, z, a, y=0.06)
    for x in (-22, 22):
        L.place("park_bench", x, 5.0, 180, y=0.06)
        L.place("streetlight", x + 4, 4.0, 0, y=0.06, s=0.85)
        L.place("streetlight", x - 4, -4.0, 0, y=0.06, s=0.85)
    rng = np.random.default_rng(7)
    for x, z in ((-20, 18), (-34, 14), (-14, 32), (-40, 36), (20, 22), (34, 15), (16, 38), (44, 34), (-26, -22), (-38, -14), (-16, -38),
                 (24, -18), (38, -30), (14, -36), (-48, -2), (50, -6), (-8, 48), (8, -50), (-52, 22), (52, 48)):
        L.place("tree", x, z, rng.uniform(0, 360), s=rng.uniform(0.8, 1.15))
    for x, z in ((-12, 14), (12, 14), (-12, -14), (12, -14), (-30, 30), (30, -10), (-6, 30), (6, -30)):
        L.place("bush", x, z, rng.uniform(0, 360))
    for x, z, yaw in ((-14, 7, 0), (14, -7, 0), (-9, -18, 90), (9, 18, 90)):
        L.place("flower_bed", x, z, yaw)
    # playground
    L.box("sandpit", (30, 0.04, 30), (24, 0.12, 18), hx("f0dca0"), "Sand", role="floor", group="Playground")
    L.place("slide", 24, 31, 90)
    L.place("swing_set", 36, 30, 0)
    L.place("picnic_table", -30, -32, 15)
    L.place("picnic_table", -40, -24, -10)
    L.place("trash_can", -6, 6, 0, s=0.6)
    L.place("trash_can", 6, -6, 0, s=0.6)
    L.place("sign_board", 4.5, -45, 180, s=0.7)
    # the perimeter: hedge ring and town buildings beyond
    for x in np.arange(-60, 61, 8):
        for z in (-62, 62):
            if abs(x) > 5:
                L.place("hedge", x, z, 0)
    for z in np.arange(-60, 61, 8):
        for x in (-62, 62):
            if abs(z) > 5:
                L.place("hedge", x, z, 90)
    cols = [hx("dc8c6e"), hx("f0e6c8"), hx("8cb4dc"), hx("e6c88c"), hx("b4dcc8"), hx("f0a0a0"), hx("c8b4e6")]
    for i, x in enumerate(np.arange(-56, 57, 16)):
        facade(L, x, 70, 15, 18 + (i % 3) * 5, cols[i % len(cols)], "Brick", shop=False, floors=4)
        facade(L, x, -70, 15, 20 + (i % 2) * 6, cols[(i + 3) % len(cols)], "Brick", shop=False, floors=4, yaw=180)
    for i, z in enumerate(np.arange(-56, 57, 16)):
        facade(L, 70, z, 15, 18 + (i % 3) * 4, cols[(i + 1) % len(cols)], "Brick", shop=False, floors=4, yaw=90)
        facade(L, -70, z, 15, 20 + (i % 2) * 5, cols[(i + 5) % len(cols)], "Brick", shop=False, floors=4, yaw=-90)
    L.bounds = (L.x0 - 64, L.x0 + 64, -64, 64)
    L.spot("fountain_south", 0, -9.0, 0, note="at the fountain's south rim, facing it")
    L.spot("fountain_east", 9.0, 0, 90)
    L.spot("bench_ne", 8.1, 8.1, 45, "sit", y=1.5, note="on the NE bench facing the fountain")
    L.spot("bench_sw", -8.1, -8.1, 225, "sit", y=1.5)
    L.spot("path_south", 0, -30, 180, note="on the south path walking north (yaw 180 faces +Z)")
    L.spot("path_west", -30, 0, -90)
    L.spot("playground", 30, 24, 0)
    L.spot("swings", 34, 30.0, 0, "sit", y=1.6)
    L.spot("picnic", -30, -29.6, 195, "sit", y=1.62)
    L.spot("lawn_open", -20, 30, 0)
    L.view("eye", (-6.0, 5.2, -24.0), (2.0, 4.5, 4.0), 62)
    L.view("wide", (-30.0, 22.0, -46.0), (2.0, 2.0, 6.0), 66)
    return L


def set_bakery():
    L = Lot("Bakery", LOT_X["Bakery"])
    W, D = 32, 26
    L.room(W, D, wall_col=hx("fadce6"), floor_col=hx("f0e6d2"), floor_mat="Marble", wainscot=(hx("f5f0e6"), 4.0),
           left=[(-3, 8, 3.0, 7.0, "window")], right=[(-6, 4.6, 0, 7.4, "door")], base_col=hx("d2508c"), frame_col=WHITE)
    L.place("door", W / 2 + 0.4, -6, 90, wall=True, cutgroup="Bakery.right", cast=False)
    for i in range(int(W / 4)):
        for j in range(int(D / 4)):
            if (i + j) % 2 == 0:
                L.box(f"tile{i}_{j}", (-W / 2 + 2 + i * 4, 0.01, -D / 2 + 2 + j * 4), (4, 0.02, 4), hx("f5a0be"), role="floor", group="Floor",
                      block=False)
    zc = D / 2 - 7.0
    L.place("display_case", -6.0, zc, 0)
    L.place("display_case", 1.0, zc, 0)
    L.place("shop_counter", 8.8, zc, 180, s=0.75)
    L.place("cash_register", 8.8, zc, 180, y=3.28 * 0.75)
    L.place("cake", 10.8, zc - 0.2, 0, y=3.28 * 0.75)
    L.place("cupcake", 6.8, zc - 0.4, 0, y=3.28 * 0.75)
    # the back: bread shelves, oven, work table
    for x in (-10, -3):
        L.place("bookshelf", x, D / 2 - 1.0, 0, s=0.85, name=f"breadshelf{x}")
    rng = np.random.default_rng(12)
    for x0 in (-10, -3):
        for sy in (1.75, 3.45, 5.15):
            for k in range(4):
                L.place("bread", x0 - 1.4 + k * 0.95, D / 2 - 1.2, rng.uniform(-15, 15), y=sy * 0.85 + 0.2, s=0.6)
    L.place("stove", 4.5, D / 2 - 1.4, 0, s=1.2)
    L.place("kitchen_counter", 11.5, D / 2 - 1.4, 0, s=0.7)
    L.place("bread", 10.5, D / 2 - 1.3, 10, y=3.2 * 0.7)
    L.place("cake", 12.5, D / 2 - 1.3, 0, y=3.2 * 0.7)
    L.on_wall("menu_board", "back", 8.0, 8.0, s=0.8)
    # the shop sign in pixel letters
    for k, pc in enumerate(text_pieces("BAKERY", 0, 0, 0, 0.45, hx("d2508c"), 0.12)):
        _, c, s, col, _o = pc
        L.box(f"sign{k}", (c[0] - 3.5, c[1] + 10.3, D / 2 - 0.12), s, col, wall=True, cutgroup="Bakery.back", cast=False, role="trim",
              group="back")
    # customer side: small tables, a cake stand, plants
    for x, z in ((-9.0, -6.5), (-1.5, -8.0)):
        L.place("bistro_table", x, z, 0, s=0.85)
        L.place("cafe_chair", x - 2.1, z, -90)
        L.place("cafe_chair", x + 2.1, z, 90)
        L.place("cupcake", x, z, 0, y=2.88 * 0.85)
    L.place("dining_table", 7.0, -6.5, 0, s=0.7)
    L.place("cake", 6.0, -6.5, 0, y=3.0 * 0.7, s=1.4)
    L.place("gift_box", 8.6, -6.3, 20, y=3.0 * 0.7)
    L.place("plant", -W / 2 + 1.8, -D / 2 + 1.8, 0)
    L.place("plant", W / 2 - 1.8, D / 2 - 6.5, 0)
    for x in (-6, 1, 8.8):
        L.ceiling_light(x, zc)
    L.ceiling_light(-4, -7, "flush_light")
    L.surround(W, D, 8)
    L.spot("case_front", -2.5, zc - 3.3, 0, note="customer at the pastry cases")
    L.spot("behind_case", -2.5, zc + 2.6, 180, note="baker behind the cases")
    L.spot("register_front", 8.8, zc - 3.4, 0)
    L.spot("register_back", 8.8, zc + 2.2, 180)
    L.spot("oven", 4.5, D / 2 - 4.2, 0)
    L.spot("cake_table", 7.0, -9.0, 0)
    L.spot("table_seat", -11.1, -6.5, 90, "sit", y=1.71 * 1.0)
    L.spot("door", W / 2 - 3, -6, 90)
    interior_views(L)
    return L


def set_office():
    L = Lot("Office", LOT_X["Office"])
    W, D = 40, 32
    L.room(W, D, wall_col=hx("e6ebf0"), floor_col=hx("6e7d91"), floor_mat="Fabric",
           back=[(-13, 7, 3.5, 8.0, "window"), (-4, 7, 3.5, 8.0, "window"), (5, 7, 3.5, 8.0, "window"), (14, 7, 3.5, 8.0, "window")],
           left=[(-6, 4.6, 0, 7.4, "door")], base_col=GREY_D, frame_col=GREY_L)
    L.place("door", -W / 2 - 0.4, -6, 90, wall=True, cutgroup="Office.left", cast=False)
    # the boss's desk at the back centre, facing the room
    L.place("desk", 0, D / 2 - 5.5, 0)
    L.place("office_chair", 0, D / 2 - 3.2, 0)
    L.place("computer", -0.8, D / 2 - 5.2, 180, y=2.62, s=0.8)
    L.place("trophy", 2.0, D / 2 - 5.5, 0, y=2.62, s=0.7)
    L.place("phone", 1.2, D / 2 - 6.2, 0, y=2.62)
    L.place("plant", -4.5, D / 2 - 1.8, 0)
    L.place("plant", 4.5, D / 2 - 1.8, 0)
    L.on_wall("painting", "back", 0.5, 10.5, s=0.9)
    # cubicles: two rows of desks with partitions
    for r, z in enumerate((-1.0, -9.5)):
        for c, x in enumerate((-14.0, -5.5, 5.5, 14.0)):
            L.place("cubicle_wall", x, z - 1.9, 0, s=1.0)
            L.place("desk", x, z, 180, s=0.85)
            L.place("computer", x + 0.5, z - 0.2, 0, y=2.62 * 0.85, s=0.75)
            L.place("office_chair", x + 0.3, z + 2.3, 180, s=0.9)
            L.place("coffee_cup", x - 1.6, z - 0.4, 0, y=2.62 * 0.85)
    for x in (-9.75, 9.75):
        L.place("cubicle_wall", x, -5.2, 90, s=0.55)
    L.place("water_cooler", W / 2 - 1.6, 9.0, -90)
    L.place("filing_cabinet", W / 2 - 1.4, 4.5, -90)
    L.place("filing_cabinet", W / 2 - 1.4, 2.6, -90)
    L.place("printer", W / 2 - 1.6, -2.5, -90)
    L.on_wall("whiteboard", "right", 12.5, 4.0)
    L.on_wall("clock", "left", 6.0, 10.0, s=0.8)
    L.place("plant", W / 2 - 1.8, -D / 2 + 1.8, 0)
    L.place("plant", -W / 2 + 1.8, D / 2 - 1.8, 0)
    L.place("sofa", -W / 2 + 2.0, 6.5, 90, s=0.85)
    L.place("coffee_table", -W / 2 + 6.0, 6.5, 90, s=0.7)
    for x in (-12, 0, 12):
        for z in (-8, 4):
            L.ceiling_light(x, z, "flush_light")
    L.surround(W, D, 9)
    L.spot("boss_chair", 0, D / 2 - 3.2, 0, "sit", y=2.0, note="the boss behind the big desk, facing the room")
    L.spot("boss_desk_front", 0, D / 2 - 9.0, 180, note="standing in front of the boss's desk")
    for r, z in enumerate((-1.0, -9.5)):
        for c, x in enumerate((-14.0, -5.5, 5.5, 14.0)):
            L.spot(f"cubicle_r{r + 1}c{c + 1}", x + 0.3, z + 2.3, 180, "sit", y=1.8)
    L.spot("water_cooler", W / 2 - 4.5, 9.0, -90)
    L.spot("whiteboard", W / 2 - 4.0, 12.5, -90)
    L.spot("lounge_sofa", -W / 2 + 2.4, 6.5, -90, "sit", y=1.66)
    L.spot("door", -W / 2 + 3, -6, -90)
    L.spot("aisle", 0, 3.8, 0)
    interior_views(L, eye_x=0.0, eye_look_x=0.0)
    return L


def set_bank():
    L = Lot("Bank", LOT_X["Bank"])
    W, D, H = 40, 34, 16
    L.room(W, D, H, wall_col=hx("f5f0e1"), floor_col=hx("f0ebe1"), floor_mat="Marble", wainscot=(hx("5a3c2a"), 4.5),
           left=[(-6, 6, 4.0, 9.0, "window"), (6, 6, 4.0, 9.0, "window")], right=[(-3, 5.0, 0, 8.0, "door")],
           base_col=hx("3c2a1e"), frame_col=hx("f5f0e6"))
    L.place("door", W / 2 + 0.4, -3, 90, s=1.1, wall=True, cutgroup="Bank.right", cast=False)
    for i in range(int(W / 5)):
        for j in range(int(D / 5)):
            if (i + j) % 2 == 0:
                L.box(f"tile{i}_{j}", (-W / 2 + 2.5 + i * 5, 0.01, -D / 2 + 2.5 + j * 5), (5, 0.02, 5), hx("c8b496"), "Marble", role="floor",
                      group="Floor", block=False)
    L.place("vault_door", 9.0, D / 2 - 0.8, 0)
    zt = D / 2 - 9.0
    for x in (-11, -3.6, 3.8):
        L.place("teller_window", x, zt, 180)
    L.place("cash_stack", -11.5, zt - 0.4, 15, y=3.65)
    L.place("coin_pile", -3.0, zt - 0.4, 0, y=3.65, s=0.6)
    L.place("piggy_bank", 3.0, zt - 0.4, 200, y=3.65, s=0.8)
    # behind the counter: a cart of gold, filing cabinets
    L.place("dining_table", 13.5, zt + 3.0, 0, s=0.7)
    L.place("gold_bars", 13.5, zt + 3.0, 0, y=3.0 * 0.7)
    L.place("filing_cabinet", -16.5, D / 2 - 1.4, 0)
    L.place("filing_cabinet", -14.6, D / 2 - 1.4, 0)
    L.place("desk", -6.5, D / 2 - 3.0, 0, s=0.85)
    L.place("computer", -6.5, D / 2 - 3.4, 180, y=2.62 * 0.85, s=0.7)
    # the queue: rope posts with velvet ropes
    posts = [(-14, -2.0), (-8, -2.0), (-2, -2.0), (4, -2.0), (-14, -6.0), (-8, -6.0), (-2, -6.0), (4, -6.0)]
    for x, z in posts:
        L.place("rope_post", x, z, 0)
    for z in (-2.0, -6.0):
        for a, b in ((-14, -8), (-8, -2), (-2, 4)):
            if z == -6.0 and a == -2:
                continue
            L.box(f"rope{a}_{z}", ((a + b) / 2, 2.5, z), (b - a - 0.4, 0.22, 0.22), hx("b4283c"), "Fabric", kind="cyl", group="Queue",
                  block=False)
    # columns
    for x in (-17, 17):
        for z in (-10, 4):
            L.box(f"column{x}_{z}", (x, H / 2, z), (H, 2.0, 2.0), hx("f5f0e6"), "Marble", kind="cyl", R=Rz(90), group="Columns")
            L.box(f"colbase{x}_{z}", (x, 0.4, z), (2.8, 0.8, 2.8), hx("e6e0d2"), "Marble", group="Columns")
            L.box(f"colcap{x}_{z}", (x, H - 0.5, z), (2.8, 1.0, 2.8), hx("e6e0d2"), "Marble", group="Columns")
    # waiting area
    for z in (-10.0, -13.0):
        L.place("pew", 8.5, z, 0, s=0.6)
    L.place("plant", W / 2 - 1.8, -D / 2 + 1.8, 0)
    L.place("plant", -W / 2 + 1.8, -D / 2 + 1.8, 0)
    L.place("plant", 1.0, D / 2 - 1.8, 0)
    for k, pc in enumerate(text_pieces("BANK", 0, 0, 0, 0.55, GOLD, 0.15)):
        _, c, s, col, _o = pc
        L.box(f"sign{k}", (c[0] - 5.5, c[1] + 11.0, D / 2 - 0.15), s, col, wall=True, cutgroup="Bank.back", cast=False, role="trim",
              group="back")
    L.on_wall("clock", "back", 1.5, 11.5, s=0.9)
    for x in (-10, 0, 10):
        for z in (-8, 6):
            L.ceiling_light(x, z)
    L.surround(W, D, 10)
    L.spot("teller1_front", -11, zt - 2.9, 0, note="customer at teller window 1")
    L.spot("teller1_back", -11, zt + 2.5, 180, note="teller behind window 1")
    L.spot("teller2_front", -3.6, zt - 2.9, 0)
    L.spot("teller3_front", 3.8, zt - 2.9, 0)
    L.spot("vault", 9.0, D / 2 - 4.0, 0, note="facing the vault door")
    L.spot("queue_start", -16.5, -4.0, -90, note="the head of the rope queue")
    L.spot("queue_mid", -5, -4.0, 90)
    L.spot("waiting_bench", 8.5, -10.3, 0, "sit", y=1.0)
    L.spot("door", W / 2 - 3, -3, 90)
    L.spot("lobby", 0, -11, 0)
    interior_views(L, eye_x=11.0)
    return L


SET_BUILDERS = {"LivingRoom": set_living_room, "Kitchen": set_kitchen, "Bedroom": set_bedroom, "Classroom": set_classroom, "Cafe": set_cafe,
                "Courtroom": set_courtroom, "Street": set_street, "Park": set_park, "Bakery": set_bakery, "Office": set_office, "Bank": set_bank}
PROP_LIB: dict = {}


# ================================================================================================== maps
def _part_footprint(p):
    c = np.array(p["cf"][:3]); R = np.array(p["cf"][3:12]).reshape(3, 3); h = np.array(p["size"]) / 2
    if p["kind"] == "mesh" and (p.get("mesh") or {}).get("key", "").startswith("own_prop_"):
        pass
    corners = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]) * h
    W = corners @ R.T + c
    return W, W[:, 1].min(), W[:, 1].max()


def _mesh_tris_world(p, cache):
    key = p["mesh"]["key"]
    if key not in cache:
        z = np.load(MC.OUT / f"{key}.npz")
        P = z["pos"][z["faces"].ravel()].astype(float)
        cache[key] = (P, (z["lo"] + z["hi"]) / 2, np.maximum(z["hi"] - z["lo"], 1e-4))
    P, centre, msize = cache[key]
    s = np.array(p["size"]) / msize
    R = np.array(p["cf"][3:12]).reshape(3, 3)
    return ((P - centre) * s) @ R.T + np.array(p["cf"][:3])


def blocking_map(L: Lot, res=None):
    """Top-down rasters: floor height, obstacle height above the floor -> PNG + json (spots)."""
    from PIL import Image, ImageDraw, ImageFont
    x0, x1, z0, z1 = L.bounds
    cell = res or (0.25 if (x1 - x0) < 60 else 0.5)
    nx, nz = int(math.ceil((x1 - x0) / cell)), int(math.ceil((z1 - z0) / cell))
    xs = x0 + (np.arange(nx) + 0.5) * cell
    zs = z0 + (np.arange(nz) + 0.5) * cell
    GX, GZ = np.meshgrid(xs, zs)            # [iz, ix]
    floor = np.full(GX.shape, -np.inf)
    obst = np.full(GX.shape, -np.inf)       # highest obstacle top (world y) with its bottom low enough to block
    cache = {}

    def raster(polys, value, target):
        """Fill the XZ polygons into target (max with value), PIL scanline fill on the polygons' bbox."""
        allp = np.concatenate(polys)
        pmin, pmax = allp.min(0), allp.max(0)
        i0, i1 = max(0, int((pmin[0] - x0) / cell) - 1), min(nx, int((pmax[0] - x0) / cell) + 2)
        j0, j1 = max(0, int((pmin[1] - z0) / cell) - 1), min(nz, int((pmax[1] - z0) / cell) + 2)
        if i0 >= i1 or j0 >= j1:
            return
        mask = Image.new("L", (i1 - i0, j1 - j0), 0)
        dr = ImageDraw.Draw(mask)
        for poly in polys:
            dr.polygon([((x - x0) / cell - i0, (z - z0) / cell - j0) for x, z in poly], fill=1)
        m = np.asarray(mask, bool)
        sub = target[j0:j1, i0:i1]
        sub[m] = np.maximum(sub[m], value)

    def hull(P2):
        from scipy.spatial import ConvexHull
        try:
            return P2[ConvexHull(P2).vertices]
        except Exception:
            return None

    cap = L.floor_y + 6.0
    for p in L.parts:
        if p.get("role") == "ceiling" or (p.get("tr", 0) >= 0.95):
            continue
        Wc, ylo, yhi = _part_footprint(p)
        if p.get("role") in ("floor", "ground"):
            hp = hull(Wc[:, [0, 2]])
            if hp is not None:
                raster([hp], yhi, floor)
            continue
        if ylo > cap:                       # overhead (lights, awnings, signs, upper windows): no obstacle
            continue
        if p["kind"] == "mesh" and (p.get("mesh") or {}).get("key", "").startswith("own_prop_"):
            T = _mesh_tris_world(p, cache).reshape(-1, 3, 3)
            T = T[T[:, :, 1].min(1) < cap]
            if len(T):
                raster(list(T[:, :, [0, 2]]), min(T[:, :, 1].max(), cap), obst)
        else:
            hp = hull(Wc[:, [0, 2]])
            if hp is not None:
                raster([hp], min(yhi, cap), obst)
    ground = np.where(np.isfinite(floor), floor, np.nan)
    rel = obst - np.nan_to_num(ground, nan=L.floor_y)
    cls = np.zeros(GX.shape, np.uint8)       # 0 none (no floor), 1 open, 2 low, 3 tall
    has_floor = np.isfinite(floor)
    cls[has_floor] = 1
    cls[has_floor & (rel > 0.3)] = 2
    cls[(rel > 3.8)] = 3
    cls[has_floor & (rel > 0.3) & (rel <= 3.8)] = 2
    # image: true top view (+X right, +Z down), the camera-side (-Z) at the top
    px = max(4, int(round(1100 / max(x1 - x0, z1 - z0))))
    img_w, img_h = int((x1 - x0) * px), int((z1 - z0) * px)
    pal = np.array([[235, 235, 235], [120, 200, 120], [245, 215, 90], [220, 80, 75]], np.uint8)
    rgb = pal[cls]                            # [iz, ix]
    im = Image.fromarray(rgb, "RGB").resize((img_w, img_h), Image.NEAREST)
    margin = 60
    canvas = Image.new("RGB", (img_w + 2 * margin + 260, img_h + 2 * margin), (255, 255, 255))
    canvas.paste(im, (margin, margin))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 13)
        bfont = ImageFont.truetype("arialbd.ttf", 16)
    except Exception:
        font = bfont = ImageFont.load_default()
    X = lambda x: margin + (x - x0) * px
    Z = lambda z: margin + (z - z0) * px
    for v in np.arange(math.ceil(x0 / 5) * 5, x1 + 1e-6, 5):
        major = int(round(v)) % 10 == 0
        d.line([(X(v), margin), (X(v), margin + img_h)], fill=(150, 150, 150) if major else (200, 200, 200), width=1)
        d.line([(X(v), margin - 6), (X(v), margin)], fill=(0, 0, 0), width=1)
        if major or px >= 20:
            d.text((X(v) - 14, margin - 22), f"{v:.0f}", fill=(0, 0, 0), font=font)
    for v in np.arange(math.ceil(z0 / 5) * 5, z1 + 1e-6, 5):
        major = int(round(v)) % 10 == 0
        d.line([(margin, Z(v)), (margin + img_w, Z(v))], fill=(150, 150, 150) if major else (200, 200, 200), width=1)
        d.line([(margin - 6, Z(v)), (margin, Z(v))], fill=(0, 0, 0), width=1)
        if major or px >= 20:
            d.text((margin - 44, Z(v) - 7), f"{v:.0f}", fill=(0, 0, 0), font=font)
    fd = getattr(L, "front_dir", [0, -1])
    side = {(-1, 0): "-X (left edge)", (1, 0): "+X (right edge)", (0, -1): "-Z (top edge)", (0, 1): "+Z (bottom edge)"}.get(
        (int(round(fd[0])), int(round(fd[1]))), str(fd))
    d.text((margin, 6), f"{L.name}  (top view: +X right, +Z down; floor y = {L.floor_y:g}; camera / open side: {side})",
           fill=(0, 0, 0), font=bfont)
    for s in L.spots:
        sx, sz = X(s["x"]), Z(s["z"])
        r = 6
        col = {"stand": (20, 90, 200), "sit": (150, 40, 170), "lie": (150, 40, 170)}.get(s["kind"], (20, 90, 200))
        d.ellipse([sx - r, sz - r, sx + r, sz + r], fill=col, outline=(255, 255, 255))
        fx, fz = s["facing"]
        d.line([(sx, sz), (sx + fx * 18, sz + fz * 18)], fill=col, width=3)
        d.text((sx + 8, sz - 6), s["name"], fill=(0, 0, 0), font=font, stroke_width=2, stroke_fill=(255, 255, 255))
    lx = margin + img_w + 20
    for i, (c, t) in enumerate(((pal[1], "open floor (stand/walk)"), (pal[2], "low furniture (< 3.8)"), (pal[3], "tall obstacle / wall"),
                                (pal[0], "no floor / outside"))):
        d.rectangle([lx, margin + i * 26, lx + 18, margin + i * 26 + 18], fill=tuple(int(v) for v in c), outline=(0, 0, 0))
        d.text((lx + 26, margin + i * 26 + 2), t, fill=(0, 0, 0), font=font)
    d.ellipse([lx, margin + 120, lx + 12, margin + 132], fill=(20, 90, 200)); d.text((lx + 20, margin + 118), "stand spot (line = facing)", fill=(0, 0, 0), font=font)
    d.ellipse([lx, margin + 144, lx + 12, margin + 156], fill=(150, 40, 170)); d.text((lx + 20, margin + 142), "sit / lie spot", fill=(0, 0, 0), font=font)
    d.text((lx, margin + 176), "ticks: 5 studs (world coords)", fill=(0, 0, 0), font=font)
    d.text((lx, margin + 196), "yaw 0 faces -Z, 90 faces -X", fill=(0, 0, 0), font=font)
    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    canvas.save(MAPS_DIR / f"{L.name}.png")
    info = {"set": L.name, "floor_y": L.floor_y, "lot_x": L.x0, "bounds": {"x": [x0, x1], "z": [z0, z1]},
            "yaw_convention": "degrees; 0 = facing -Z, 90 = facing -X, 180 = facing +Z (as PLACE / CAST)",
            "interior": L.interior, "camera_side": getattr(L, "front_dir", None),
            "note": "camera_side = the direction from the room centre toward its front (cut-away) wall / main camera side", "room": {"W": getattr(L, "W", None), "D": getattr(L, "D", None), "H": getattr(L, "H", None)},
            "spots": L.spots}
    (MAPS_DIR / f"{L.name}.json").write_text(json.dumps(info, indent=1))
    return cls, (x0, z0, cell)


def check_spots(L: Lot):
    """Floors under every spot (stage.World ground rays) and standing room for stand spots."""
    import stage as ST
    W = ST.World({"parts": L.parts})
    out = []
    for s in L.spots:
        g, _ = W._down(s["x"], (s["y"] if s["kind"] == "stand" else L.floor_y) + 0.6, s["z"], 20)
        free = W.stand_free({"pts": [(s["x"], s["z"])], "floor": g if g is not None else L.floor_y, "r": 0.9, "h": 4.8})[0] \
            if s["kind"] == "stand" else None
        out.append({"spot": s["name"], "ground": None if g is None else round(g, 2), "free": free})
    return out


# ================================================================================================ render
def render_views(sets: list[Lot], light, w=540, h=960):
    import hlrender as RD
    from PIL import Image
    tiles = []
    for L in sets:
        d = PREVIEW_DIR / L.name
        d.mkdir(parents=True, exist_ok=True)
        (d / "static.json").write_text(json.dumps({"parts": L.parts, "light": light}))
        (d / "dynamic.json").write_text(json.dumps({"parts": [], "actors": {}, "order": []}))
        R = RD.Renderer(d, w=w, h=h)
        for v in L.views:
            img = R.frame(np.array(v["cam"]), np.array(v["look"]), v["fov"])
            im = Image.frombytes("RGB", (w, h), img).transpose(Image.FLIP_TOP_BOTTOM)
            im.save(PREVIEW_DIR / f"{L.name}_{v['label']}.png")
            tiles.append((f"{L.name} / {v['label']}", im))
        if R.sc.missing:
            print("  missing meshes:", L.name, R.sc.missing)
        R.ctx.release()
    return tiles


def contact_sheet(tiles, out, cols, scale=0.5, label_h=26):
    from PIL import Image, ImageDraw, ImageFont
    tw, th = int(tiles[0][1].width * scale), int(tiles[0][1].height * scale)
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + label_h)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arialbd.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    for i, (lab, im) in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (c * tw, r * (th + label_h) + label_h))
        d.text((c * tw + 6, r * (th + label_h) + 5), lab, fill=(0, 0, 0), font=font)
    sheet.save(out, quality=90)
    return out


def render_props(light, keys, tile=320):
    """Every prop on its own pedestal next to a 2 x 5 x 1 stud scale block, one framed render each."""
    import hlrender as RD
    from PIL import Image
    xb = 12000
    parts = [{"kind": "box", "name": "floor", "size": [4000, 1, 60], "cf": [xb + 1900, -0.5, 0, *I3], "color": [0.86, 0.88, 0.9],
              "mat": "Concrete", "tr": 0}]
    L = Lot("Props", xb, interior=False)
    slots = {}
    x = 0.0
    for k in keys:
        sz = PROP_LIB[k]["size"]
        x += max(sz[0], 2.0) / 2 + 1.0
        L.place(k, x, 0, 0)
        L.box(f"scale_{k}", (x - sz[0] / 2 - 1.8, 2.5, 0), (2, 5, 1), hx("ff8c28"), group="Scale")
        slots[k] = (x, sz)
        L.box(f"floor_{k}", (x - 1.4, -0.5, 0), (max(sz[0], 2.0) + 12.0, 1.0, max(sz[2], 2.0) + 16.0), hx("dcdfe4"), "Concrete", group="Floor")
        x += max(sz[0], 2.0) / 2 + 6.0 + max(sz[0], sz[1]) * 0.6
    parts += L.parts
    d = PREVIEW_DIR / "_props"
    d.mkdir(parents=True, exist_ok=True)
    (d / "static.json").write_text(json.dumps({"parts": parts, "light": light}))
    (d / "dynamic.json").write_text(json.dumps({"parts": [], "actors": {}, "order": []}))
    R = RD.Renderer(d, w=tile, h=tile)
    tiles = []
    for k in keys:
        px, sz = slots[k]
        cxw = xb + ((px - sz[0] / 2 - 2.8) + (px + sz[0] / 2)) / 2
        ext = max(sz[0] + 3.0, sz[1], 5.0, sz[2])
        dist = ext * 1.25 + 2.5
        look = np.array([cxw, max(sz[1], 5.0) * 0.45, 0])
        cam = look + np.array([dist * 0.42, dist * 0.32, -dist])
        img = R.frame(cam, look, 45, radius=60)
        tiles.append((k, Image.frombytes("RGB", (tile, tile), img).transpose(Image.FLIP_TOP_BOTTOM)))
    R.ctx.release()
    return tiles


# ================================================================================================== main
def build_all(render=True, only=None):
    t0 = time.time()
    OWN.mkdir(parents=True, exist_ok=True)
    SETS_DIR.mkdir(parents=True, exist_ok=True)
    build_unit_meshes()
    PROP_LIB.clear()
    for k in PROPS:
        PROP_LIB[k] = build_prop(k)
    (OWN / "props.json").write_text(json.dumps(PROP_LIB))
    print(f"{len(PROP_LIB)} props ({time.time() - t0:.1f}s)")
    light = json.loads(STATIC_SRC.read_text())["light"] if STATIC_SRC.exists() else DEFAULT_LIGHT
    sets = []
    for name, fn in SET_BUILDERS.items():
        if only and name not in only:
            continue
        L = fn().finish()
        sets.append(L)
        (SETS_DIR / f"{name}.json").write_text(json.dumps({"parts": L.parts, "light": light, "floor_y": L.floor_y, "lot_x": L.x0,
                                                           "bounds": L.bounds, "spots": L.spots, "views": L.views}))
        blocking_map(L)
        bad = [c for c in check_spots(L) if c["ground"] is None or (c["free"] is False)]
        print(f"  {name}: {len(L.parts)} parts, {len(L.spots)} spots" + (f"  CHECK {bad}" if bad else ""))
    register_meshes()
    if not only:
        allp = [p for L in sets for p in L.parts]
        (OWN / "scene_static.json").write_text(json.dumps({"parts": allp, "light": light}))
        print(f"scene_static.json: {len(allp)} parts")
    if render:
        tiles = render_views(sets, light)
        contact_sheet(tiles, OWN / ("sets_preview.jpg" if not only else "sets_preview_partial.jpg"), cols=min(len(tiles), 8))
        if not only:
            pt = render_props(light, sorted(PROP_LIB))
            contact_sheet(pt, OWN / "props_preview.jpg", cols=10, scale=1.0, label_h=22)
    print(f"done in {time.time() - t0:.1f}s")
    return sets


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--only", nargs="*", help="build / preview only these sets")
    a = ap.parse_args()
    build_all(render=not a.no_render, only=a.only)
