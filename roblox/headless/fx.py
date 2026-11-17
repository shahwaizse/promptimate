"""Visual effects for the Studio-free director, built from ordinary posed parts (so the renderer and the camera checks
need nothing new): particle bursts (sparkle, hearts, confetti, rain cloud, poof, dizzy stars, zzz, anger, sweat)
and text signs (a board with a real-font texture).

    parts, P, Q, S = particles(kind, anchor, t0, t1, times, seed)
        anchor: (nf, 3) world point per frame (a head, a prop, a fixed spot)
        -> parts: exported part dicts; P (nf, n, 3) positions, Q (nf, n, 4) quaternions (w last: x y z w as
           pose.py), S (nf, n) uniform scale; hidden frames have P[..., 1] += HIDE_Y.
    sign_png(text, path, style) -> path of the rendered texture
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

import pose as PO

HIDE_Y = -2000.0
FONTS = Path(__file__).resolve().parents[2] / "demo" / "episodes" / "build" / "_media" / "fonts"
TEX_OUT = Path(r"D:\tmp\headless\own\tex\signs")


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]


GOLD, WHITE, PINK, RED, GREY, GREY_L, BLUE, YEL = (_rgb(c) for c in (
    "ffd84a", "ffffff", "ff7eb6", "ff3b4f", "9aa0aa", "dfe3e8", "5aa8ff", "ffe14d"))
CONFETTI = [_rgb(c) for c in ("ff4d6d", "ffd23f", "3bceac", "4d96ff", "b15cff", "ff8c42")]


def _q_axis(axis, ang):
    axis = np.asarray(axis, float)
    axis = axis / np.linalg.norm(axis)
    s = np.sin(ang / 2)[..., None]
    return np.concatenate([axis * s, np.cos(ang / 2)[..., None]], -1)


# a shape = sub-parts (kind, local offset, size, local rotation about Z in degrees, material)
SHAPES = {
    "star": [("box", (0, 0, 0), (0.16, 1.0, 0.16), 0, "Neon"), ("box", (0, 0, 0), (1.0, 0.16, 0.16), 0, "Neon"),
             ("box", (0, 0, 0), (0.42, 0.42, 0.18), 45, "Neon")],
    "heart": [("ball", (-0.2, 0.1, 0), (0.52, 0.52, 0.3), 0, "SmoothPlastic"),
              ("ball", (0.2, 0.1, 0), (0.52, 0.52, 0.3), 0, "SmoothPlastic"),
              ("box", (0, -0.12, 0), (0.55, 0.55, 0.3), 45, "SmoothPlastic")],
    "chip": [("box", (0, 0, 0), (0.34, 0.04, 0.2), 0, "SmoothPlastic")],
    "streak": [("box", (0, 0, 0), (0.05, 0.55, 0.05), 0, "Glass")],
    "puff": [("ball", (0, 0, 0), (1.0, 0.9, 1.0), 0, "SmoothPlastic")],
    "cloud": [("ball", (0, 0, 0), (1.6, 0.8, 1.2), 0, "SmoothPlastic"), ("ball", (0.8, -0.1, 0.1), (1.1, 0.65, 0.9), 0, "SmoothPlastic"),
              ("ball", (-0.8, -0.1, -0.1), (1.1, 0.6, 0.9), 0, "SmoothPlastic")],
    "z": [("box", (0, 0.3, 0), (0.6, 0.12, 0.1), 0, "Neon"), ("box", (0, -0.3, 0), (0.6, 0.12, 0.1), 0, "Neon"),
          ("box", (0, 0, 0), (0.12, 0.78, 0.1), -50, "Neon")],
    "vein": [("box", (0, 0.18, 0), (0.12, 0.42, 0.1), 0, "Neon"), ("box", (0, -0.18, 0), (0.12, 0.42, 0.1), 0, "Neon"),
             ("box", (0.18, 0, 0), (0.42, 0.12, 0.1), 0, "Neon"), ("box", (-0.18, 0, 0), (0.42, 0.12, 0.1), 0, "Neon")],
    "drop": [("ball", (0, 0, 0), (0.3, 0.42, 0.3), 0, "Glass")],
}


def _shape_parts(shape, color):
    out = []
    for kind, off, size, rz, mat in SHAPES[shape]:
        d = {"kind": "box", "name": f"fx_{shape}", "size": list(size), "color": list(color), "mat": mat,
             "tr": 0.25 if mat == "Glass" else 0.0, "cf": None, "fx": True, "cast": False}
        if kind == "ball":
            d["kind"] = "part"
            d["mesh"] = {"special": {"type": "Sphere", "scale": [1, 1, 1]}}
        out.append((d, np.asarray(off, float), PO.m2q(np.array([[math.cos(math.radians(rz)), -math.sin(math.radians(rz)), 0],
                                                                 [math.sin(math.radians(rz)), math.cos(math.radians(rz)), 0],
                                                                 [0, 0, 1]]))))
    return out


def _expand(shape, colors, C, Qc, Sc):
    """Particles (centres C (nf, k, 3), rotations Qc (nf, k, 4), scales Sc (nf, k)) -> parts and per-part arrays."""
    nf, k = Sc.shape
    parts, P, Q, S = [], [], [], []
    for j in range(k):
        for d, off, q in _shape_parts(shape, colors[j % len(colors)]):
            parts.append(dict(d))
            P.append(C[:, j] + PO.qrot(Qc[:, j], off[None] * Sc[:, j, None]))
            Q.append(PO.qmul(Qc[:, j], np.repeat(q[None], nf, 0)))
            S.append(Sc[:, j])
    return parts, np.stack(P, 1), np.stack(Q, 1), np.stack(S, 1)


def _face_cam(nf, k, yaw=None):
    """Rotations that spin each particle about Y (shapes are flat in XY: they read from most angles while turning)."""
    yaw = np.zeros((nf, k)) if yaw is None else yaw
    return _q_axis((0, 1, 0), yaw)


def particles(kind: str, anchor: np.ndarray, t0: float, t1: float, times: np.ndarray, seed: int = 0):
    nf = len(times)
    rng = np.random.default_rng(seed)
    A = np.asarray(anchor, float)
    if A.ndim == 1:
        A = np.repeat(A[None], nf, 0)
    live = (times >= t0) & (times <= t1)
    tt = np.clip(times - t0, 0, None)
    if kind == "sparkle":
        k = 10
        ph, rad, h = rng.uniform(0, 1, k), rng.uniform(1.2, 2.0, k), rng.uniform(-0.6, 1.4, k)
        ang = 2 * np.pi * (ph[None] + tt[:, None] * 0.12)
        C = A[:, None] + np.stack([np.cos(ang) * rad, np.repeat(h[None], nf, 0), np.sin(ang) * rad], -1)
        S = 0.42 * np.clip(np.sin(2 * np.pi * (tt[:, None] * rng.uniform(0.9, 1.6, k)[None] + ph[None])), 0, None) ** 1.5
        shape, cols, Qc = "star", [GOLD, WHITE, GOLD], _face_cam(nf, k, tt[:, None] * 2.0 + ph[None] * 6)
    elif kind == "hearts":
        k = 6
        ph, rx, rz = rng.uniform(0, 1, k), rng.uniform(-0.9, 0.9, k), rng.uniform(-0.6, 0.6, k)
        u = (tt[:, None] / 1.8 + ph[None]) % 1.0
        C = A[:, None] + np.stack([np.repeat(rx[None], nf, 0) + 0.2 * np.sin(6 * u), 0.6 + 2.2 * u, np.repeat(rz[None], nf, 0)], -1)
        S = 0.75 * np.sin(np.pi * u)
        shape, cols, Qc = "heart", [PINK, RED], _face_cam(nf, k, 0.6 * np.sin(2 * np.pi * u))
    elif kind == "confetti":
        k = 40
        period = 2.6
        u = tt[:, None] % period
        v0 = np.stack([rng.uniform(-4, 4, k), rng.uniform(3, 7, k), rng.uniform(-4, 4, k)], -1)
        C = A[:, None] + np.array([0, 1.5, 0]) + v0[None] * u[..., None] * np.exp(-0.9 * u[..., None]) + \
            np.array([0, -1.0, 0]) * (u[..., None] ** 2) * 2.2
        S = np.where(u < period - 0.15, 1.0, 0.0) * np.ones((nf, k))
        spin = rng.uniform(4, 10, k)
        Qc = PO.qmul(_q_axis((1, 0, 0), u * spin[None]), _q_axis((0, 0, 1), u * spin[None] * 0.7))
        shape, cols = "chip", CONFETTI
    elif kind == "rain":
        k = 16
        ph, rx, rz = rng.uniform(0, 1, k), rng.uniform(-1.1, 1.1, k), rng.uniform(-0.7, 0.7, k)
        u = (tt[:, None] / 0.55 + ph[None]) % 1.0
        C = A[:, None] + np.stack([np.repeat(rx[None], nf, 0), 2.2 - 3.6 * u, np.repeat(rz[None], nf, 0)], -1)
        S = np.ones((nf, k))
        Qc = _face_cam(nf, k)
        shape, cols = "streak", [BLUE]
        p2, q2, s2 = _cloud(A + np.array([0, 2.6, 0]), nf, tt)
        parts, P, Q, SS = _expand(shape, cols, C, Qc, S)
        parts2, P2, Q2, S2 = _expand("cloud", [GREY], p2, q2, s2)
        parts, P, Q, SS = parts + parts2, np.concatenate([P, P2], 1), np.concatenate([Q, Q2], 1), np.concatenate([SS, S2], 1)
        return _finish(parts, P, Q, SS, live)
    elif kind == "poof":
        k = 14
        dirs = rng.normal(size=(k, 3))
        dirs[:, 1] = np.abs(dirs[:, 1]) * 0.6
        dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
        u = np.clip(tt[:, None] / 0.9, 0, 1)
        r = 0.4 + 2.4 * (1 - (1 - u) ** 2)
        C = A[:, None] + np.array([0, 0.3, 0]) + dirs[None] * r[..., None] + np.array([0, 0.8, 0]) * u[..., None]
        S = (0.8 + 1.0 * u) * np.clip((1 - u) / 0.45, 0, 1) * rng.uniform(0.8, 1.3, k)[None]
        shape, cols, Qc = "puff", [WHITE, GREY_L], _face_cam(nf, k)
        live = live & (tt < 0.9)
    elif kind == "dizzy":
        k = 5
        ang = 2 * np.pi * (np.arange(k)[None] / k + tt[:, None] * 0.7)
        C = A[:, None] + np.stack([np.cos(ang) * 0.95, 0.95 + 0.1 * np.sin(3 * ang), np.sin(ang) * 0.95], -1)
        S = 0.4 * np.ones((nf, k))
        shape, cols, Qc = "star", [YEL], _face_cam(nf, k, ang * 2)
    elif kind == "zzz":
        k = 3
        u = (tt[:, None] / 2.4 + np.arange(k)[None] / k) % 1.0
        C = A[:, None] + np.stack([0.6 + 0.9 * u, 0.7 + 1.8 * u, 0.2 * np.sin(5 * u)], -1)
        S = (0.5 + 0.6 * u) * np.sin(np.pi * u) ** 0.5
        shape, cols, Qc = "z", [WHITE, _rgb("bcd7ff")], _face_cam(nf, k)
    elif kind == "anger":
        k = 2
        u = (tt[:, None] / 0.7) % 1.0
        C = A[:, None] + np.array([[0.55, 0.75, -0.2], [-0.5, 0.95, -0.25]])[None]
        S = 0.55 + 0.25 * np.sin(2 * np.pi * u)
        shape, cols, Qc = "vein", [RED], _face_cam(nf, k)
    elif kind == "sweat":
        k = 3
        ph = np.arange(k) / k
        u = (tt[:, None] / 1.1 + ph[None]) % 1.0
        C = A[:, None] + np.stack([0.75 + 0.1 * np.arange(k)[None] * np.ones((nf, 1)), 0.6 - 1.0 * u, -0.2 * np.ones((nf, k))], -1)
        S = 0.8 * np.sin(np.pi * u) ** 0.4
        shape, cols, Qc = "drop", [_rgb("9fd8ff")], _face_cam(nf, k)
    else:
        raise KeyError(f"unknown fx kind {kind!r}")
    parts, P, Q, SS = _expand(shape, cols, C, Qc, S)
    return _finish(parts, P, Q, SS, live)


def _cloud(A, nf, tt):
    C = A[:, None] + np.array([0, 0.05, 0]) * np.sin(tt * 2)[:, None, None]
    return C, _face_cam(nf, 1), np.ones((nf, 1))


def _finish(parts, P, Q, S, live):
    P = P.copy()
    off = (~live)[:, None] | (S <= 1e-3)
    P[..., 1] += np.where(off, HIDE_Y, 0.0)
    S = np.where(off, 1.0, S)
    return parts, P, Q, S


KINDS = ("sparkle", "hearts", "confetti", "rain", "poof", "dizzy", "zzz", "anger", "sweat")


# ------------------------------------------------------------------------------------------------- signs
STYLES = {   # board colour, text colour, border colour
    "wood": ("#c98b4f", "#fff6e0", "#7a4e2e"), "red": ("#e04848", "#ffffff", "#a83030"), "blue": ("#2f6fd6", "#ffffff", "#1d4a99"),
    "green": ("#2f9e55", "#ffffff", "#1f6e3a"), "black": ("#24262b", "#ffe14d", "#55585f"), "white": ("#f7f7f2", "#e04848", "#c8ccd2"),
    "gold": ("#f0c43c", "#5a3a10", "#b8862a"),
}


def sign_png(text: str, style: str = "wood", w: int = 1024, h: int = 512) -> str:
    """A sign face: the text (upper case, wrapped to fit) on a coloured board with a border. Cached by content."""
    import hashlib
    from PIL import Image, ImageDraw, ImageFont
    TEX_OUT.mkdir(parents=True, exist_ok=True)
    bg, fg, bd = STYLES.get(style, STYLES["wood"])
    key = hashlib.sha1(f"{text}|{style}|{w}x{h}".encode()).hexdigest()[:12]
    out = TEX_OUT / f"sign_{key}.png"
    if out.exists():
        return str(out)
    im = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(im)
    b = int(h * 0.06)
    d.rectangle([0, 0, w - 1, h - 1], outline=bd, width=b)
    words = text.upper().split()
    font_p = FONTS / "Montserrat-Black.ttf"
    for size in range(int(h * 0.42), 20, -4):
        f = ImageFont.truetype(str(font_p), size)
        lines, cur = [], ""
        for wd in words:
            t = (cur + " " + wd).strip()
            if d.textlength(t, font=f) <= w - 4 * b:
                cur = t
            else:
                if cur:
                    lines.append(cur)
                cur = wd
        lines.append(cur)
        lh = size * 1.08
        if len(lines) * lh <= h - 4 * b and all(d.textlength(l_, font=f) <= w - 4 * b for l_ in lines):
            break
    y = (h - len(lines) * lh) / 2
    for l_ in lines:
        d.text(((w - d.textlength(l_, font=f)) / 2, y), l_, font=f, fill=fg)
        y += lh
    im.save(out)
    return str(out)


def sign_parts(text: str, style: str = "wood", width: float = 4.0, stand: bool = True) -> tuple[list[dict], float]:
    """A sign as exported parts in its own frame (pivot at the floor, facing -Z): the board (texture on its front, -Z)
    and two posts when standing. Returns (parts, height)."""
    tex = sign_png(text, style)
    bh = width / 2
    y0 = 2.6 if stand else 0.0
    bg = _rgb(STYLES.get(style, STYLES["wood"])[0])
    board = {"kind": "box", "name": "sign_board", "size": [width, bh, 0.2], "color": bg, "mat": "SmoothPlastic", "tr": 0.0,
             "cf": [0, y0 + bh / 2, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1],
             "decals": [{"face": "Front", "tex": "file:" + tex, "offset": 0.12}, {"face": "Back", "tex": "file:" + tex, "offset": 0.12}]}
    parts = [board]
    if stand:
        for sx in (-1, 1):
            parts.append({"kind": "box", "name": "sign_post", "size": [0.25, y0 + 0.2, 0.25], "color": _rgb("7a4e2e"),
                          "mat": "Wood", "tr": 0.0, "cf": [sx * width * 0.35, (y0 + 0.2) / 2, 0.15, 1, 0, 0, 0, 1, 0, 0, 0, 1]})
    return parts, y0 + bh
