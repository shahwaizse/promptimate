"""Procedural face decals for the headless renderer.

Draws the 13 expression textures `hlrender.tex()` loads (face_<name>.png) with PIL,
so a fresh clone can render without the Studio screen-grabs made by bake.py.
Geometry was measured from those grabs: 512x512 RGBA, transparent background,
features centred on x=256 (the renderer maps the whole canvas onto the head's front
face, so positions and sizes are kept the same). Everything is drawn at 4x and
box-downsampled for smooth edges.

    python roblox/headless/own_faces.py [OUT_DIR] [--force]
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp_server"))
import local_config as LC  # noqa: E402

SIZE = 512
SS = 4  # supersampling factor

BLACK = (20, 20, 20, 255)
WHITE = (255, 255, 255, 255)
TEAR = (90, 170, 255, 255)
SWEAT = (120, 190, 255, 255)
HEART = (220, 40, 60, 255)
CHEEK = (255, 119, 139, 165)
TONGUE = (200, 70, 80, 255)

FACES = ("angry", "crying", "grin", "happy", "love", "neutral", "sad", "scared",
         "shocked", "sleeping", "smug", "tired", "wink")

# Canvas coordinates are continuous (pixel i spans [i, i+1]); features mirror about x=256.
EYE_X = 184.0          # left eye / brow centre; right one is at 512 - EYE_X
BROW_HALF = 28.0       # half length of a brow between its round-cap centres
BROW_W = 15.5
MOUTH_W = 17.0
LID_W = 18.0


def mx(x: float) -> float:
    return SIZE - x


class Canvas:
    def __init__(self):
        self.img = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    # --- primitives (canvas units) -------------------------------------------------
    def rrect(self, x0, y0, x1, y1, r, fill):
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        self.d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1], radius=r * SS, fill=fill)

    def pill(self, cx, cy, w, h, fill):
        self.rrect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, min(w, h) / 2, fill)

    def ellipse(self, cx, cy, w, h, fill):
        self.d.ellipse([(cx - w / 2) * SS, (cy - h / 2) * SS, (cx + w / 2) * SS - 1, (cy + h / 2) * SS - 1], fill=fill)

    def polygon(self, pts, fill):
        self.d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill)

    def stroke(self, pts, w, fill=BLACK):
        """Round-capped, round-jointed thick polyline (stamped discs, 1 px apart at 4x)."""
        r = w * SS / 2
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) * SS))
            for i in range(n + 1):
                t = i / n
                x, y = (x0 + (x1 - x0) * t) * SS, (y0 + (y1 - y0) * t) * SS
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def curve(self, p0, mid, p2, w, fill=BLACK):
        """Quadratic Bezier from p0 to p2 passing through `mid` at t=0.5."""
        c = (2 * mid[0] - (p0[0] + p2[0]) / 2, 2 * mid[1] - (p0[1] + p2[1]) / 2)
        pts = []
        for i in range(41):
            t = i / 40
            a, b, e = (1 - t) ** 2, 2 * t * (1 - t), t * t
            pts.append((a * p0[0] + b * c[0] + e * p2[0], a * p0[1] + b * c[1] + e * p2[1]))
        self.stroke(pts, w, fill)

    def layer(self, fn):
        """Draw a translucent feature on its own layer so its alpha is kept, then composite."""
        sub = Canvas()
        fn(sub)
        self.img.alpha_composite(sub.img)

    def result(self) -> Image.Image:
        return self.img.resize((SIZE, SIZE), Image.BOX)

    # --- features ------------------------------------------------------------------
    def brows(self, cy, tilt=0.0, w=BROW_W):
        """tilt in degrees: positive = inner ends lower (angry), negative = inner ends raised (sad)."""
        a = math.radians(tilt)
        dx, dy = BROW_HALF * math.cos(a), BROW_HALF * math.sin(a)
        self.stroke([(EYE_X - dx, cy - dy), (EYE_X + dx, cy + dy)], w)
        self.stroke([(mx(EYE_X - dx), cy - dy), (mx(EYE_X + dx), cy + dy)], w)

    def pill_eye(self, cx):
        self.pill(cx, 184.0, 34, 56, BLACK)
        hx = cx + 6.5 if cx < SIZE / 2 else cx + 6.0
        self.pill(hx, 171.5, 9, 15, WHITE)

    def pill_eyes(self):
        self.pill_eye(EYE_X)
        self.pill_eye(mx(EYE_X))

    def big_eyes(self):
        for cx in (EYE_X, mx(EYE_X)):
            self.rrect(cx - 38, 141, cx + 38, 228, 32, WHITE)
            self.ellipse(cx, 184.5, 30, 35, BLACK)

    def closed_eye_up(self, cx):    # "^" lid: crying, sleeping
        self.curve((cx - 29, 191.5), (cx, 182.0), (cx + 29, 191.5), LID_W)

    def closed_eye_down(self, cx):  # "U" lid: grin, wink
        self.curve((cx - 30, 199.5), (cx, 214.5), (cx + 30, 199.5), LID_W)

    def lidded_eyes(self):          # half-closed: smug, tired
        for cx in (EYE_X, mx(EYE_X)):
            self.rrect(cx - 18, 179, cx + 18, 205, 9, BLACK)
            self.pill(cx, 179.0, 62, 12, BLACK)

    def heart(self, cx):
        r = 13.5
        self.ellipse(cx - 13, 183.5, 2 * r, 2 * r, HEART)
        self.ellipse(cx + 13, 183.5, 2 * r, 2 * r, HEART)
        self.polygon([(cx - 13, 175), (cx + 13, 175), (cx + 22, 196), (cx - 22, 196)], HEART)
        self.polygon([(cx - 22.5, 196), (cx + 22.5, 196), (cx, 218.5)], HEART)  # 45-degree point

    def smile(self, x0, x1, y_end=310.5, y_mid=337.5):
        self.curve((x0, y_end), ((x0 + x1) / 2, y_mid), (x1, y_end), MOUTH_W)

    def frown(self, x0, x1, y_end, y_mid, w=MOUTH_W):
        self.curve((x0, y_end), ((x0 + x1) / 2, y_mid), (x1, y_end), w)

    def sweat(self):
        self.pill(430.5, 122.5, 31, 51, SWEAT)


# --- the 13 expressions ---------------------------------------------------------------

def f_neutral(c):
    c.brows(112.5)
    c.pill_eyes()
    c.frown(211.5, 300.5, 307.5, 310.0)


def f_happy(c):
    c.brows(107.5)
    c.pill_eyes()
    c.smile(183.5, 328.5)


def f_grin(c):
    c.brows(102.5)
    c.closed_eye_down(EYE_X)
    c.closed_eye_down(mx(EYE_X))
    c.rrect(169, 274, 343, 341, 30, BLACK)
    c.rrect(184, 280, 328, 300, 4, WHITE)


def f_wink(c):
    c.brows(107.5)
    c.pill_eye(EYE_X)
    c.closed_eye_down(mx(EYE_X))
    c.smile(188.5, 323.5)


def f_love(c):
    c.brows(102.5, tilt=-6)
    c.heart(EYE_X)
    c.heart(mx(EYE_X))
    c.layer(lambda s: (s.pill(122.5, 256.0, 61, 30, CHEEK), s.pill(mx(122.5), 256.0, 61, 30, CHEEK)))
    c.smile(188.5, 323.5)


def f_sad(c):
    c.brows(107.5, tilt=-18)
    c.pill_eyes()
    c.frown(204.5, 307.5, 304.0, 283.5)


def f_angry(c):
    c.brows(118.0, tilt=22)
    c.pill_eyes()
    c.frown(209.5, 302.5, 304.0, 286.5)


def f_crying(c):
    c.brows(107.5, tilt=-20)
    c.closed_eye_up(EYE_X)
    c.closed_eye_up(mx(EYE_X))
    c.pill(184.0, 256.0, 26, 102, TEAR)
    c.pill(mx(184.0), 256.0, 26, 102, TEAR)
    c.rrect(205, 282, 307, 343, 25, BLACK)
    c.pill(256.0, 330.0, 52, 20, TONGUE)


def f_scared(c):
    c.brows(92.5, tilt=-16)
    c.big_eyes()
    c.frown(194.0, 318.0, 305.0, 291.5, w=16.5)
    c.sweat()


def f_shocked(c):
    c.brows(87.0, w=16.0)
    c.big_eyes()
    c.pill(256.0, 307.5, 62, 77, BLACK)


def f_sleeping(c):
    c.brows(112.5)
    c.closed_eye_up(EYE_X)
    c.closed_eye_up(mx(EYE_X))
    c.rrect(235, 299, 277, 316, 2, BLACK)


def f_smug(c):
    c.brows(112.5, tilt=8)
    c.lidded_eyes()
    c.curve((236.0, 312.0), (288.0, 325.0), (338.5, 309.5), MOUTH_W)


def f_tired(c):
    c.brows(117.5, tilt=-6)
    c.lidded_eyes()
    c.frown(220.5, 291.5, 306.0, 299.5)
    c.sweat()


DRAW = {name: globals()[f"f_{name}"] for name in FACES}


def render(name: str) -> Image.Image:
    c = Canvas()
    DRAW[name](c)
    return c.result()


def build(out_dir: Path | None = None, force: bool = False) -> list[Path]:
    """Write face_<name>.png for every expression; existing files are kept unless force."""
    out_dir = Path(out_dir) if out_dir else Path(LC.HEADLESS_CACHE) / "tex"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for name in FACES:
        p = out_dir / f"face_{name}.png"
        if force or not p.exists():
            render(name).save(p)
        out.append(p)
    return out


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    paths = build(Path(args[0]) if args else None, force="--force" in sys.argv[1:])
    print(f"{len(paths)} face textures in {paths[0].parent}")
    sys.stdout.flush()
    os._exit(0)
