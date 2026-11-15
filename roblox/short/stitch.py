"""Vertical 9:16 frames from Roblox Studio's landscape viewport.

Studio's `screen_capture` renders the edit viewport (here 1452x793) and resets camera roll, and Windows caps the
window height near the screen height, so a native portrait viewport is impossible. Instead each output frame is
stitched from N captures taken from the SAME camera position, pitched up/down about the camera's right axis (pure
rotation, no parallax). For pure rotation the mapping between images is an exact homography H = K_row R K_out^-1, so
rows warp onto the virtual 9:16 camera with no seams beyond resampling; overlaps are feather-blended.
At density 1 the virtual camera has the same pixels per radian as the captures (no upscaling).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image


def _basis(pos, look):
    f = np.asarray(look, float) - np.asarray(pos, float)
    f /= np.linalg.norm(f)
    up = np.array([0.0, 1.0, 0.0])
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return r, u, f


def plan(pos, look, fov_out_deg, out=(1080, 1920), vp=(1452, 793), density=1.0, overlap=0.18):
    """Rows to capture: [{'look': world point, 'fov': vertical fov deg, 'H': 3x3 output->row pixel}]"""
    Wo, Ho = out
    Wv, Hv = vp
    fo = (Ho / 2) / math.tan(math.radians(fov_out_deg) / 2)
    fr = fo * density
    fov_r = 2 * math.atan((Hv / 2) / fr)
    half_o = math.radians(fov_out_deg) / 2
    n = max(1, math.ceil((2 * half_o) / (fov_r * (1 - overlap)) - 1e-9))
    if n == 1:
        deltas = [0.0]
    else:
        span = half_o - fov_r / 2 * (1 - overlap / 2)
        deltas = list(np.linspace(span, -span, n))      # top row first (look up)
    r, u, f = _basis(pos, look)
    K_inv = np.array([[1 / fo, 0, -(Wo / 2) / fo], [0, -1 / fo, (Ho / 2) / fo], [0, 0, 1]])
    Mo = np.stack([r, u, f], axis=1)
    rows = []
    for d in deltas:
        fi = f * math.cos(d) + u * math.sin(d)
        ui = np.cross(r, fi)
        Mi_T = np.stack([r, ui, fi], axis=0)
        Kr = np.array([[fr, 0, Wv / 2], [0, -fr, Hv / 2], [0, 0, 1]])
        H = Kr @ Mi_T @ Mo @ K_inv
        rows.append({"look": (np.asarray(pos, float) + fi * 20).tolist(), "fov": math.degrees(fov_r), "H": H, "pitch": d})
    return rows


def blend(images: list[Image.Image], rows, out=(1080, 1920), feather=40) -> Image.Image:
    Wo, Ho = out
    if len(rows) == 1 and images[0].size == out:
        return images[0].convert("RGB")
    ys, xs = np.mgrid[0:Ho, 0:Wo].astype(np.float64)
    acc = np.zeros((Ho, Wo, 3))
    wsum = np.zeros((Ho, Wo))
    for img, row in zip(images, rows):
        H = row["H"] / row["H"][2, 2]
        warped = img.convert("RGB").transform(out, Image.PERSPECTIVE, tuple(H.flatten()[:8]), Image.BICUBIC)
        Wv, Hv = img.size
        den = H[2, 0] * (xs + 0.5) + H[2, 1] * (ys + 0.5) + 1
        uu = (H[0, 0] * (xs + 0.5) + H[0, 1] * (ys + 0.5) + H[0, 2]) / den
        vv = (H[1, 0] * (xs + 0.5) + H[1, 1] * (ys + 0.5) + H[1, 2]) / den
        w = np.clip(np.minimum(vv, Hv - vv) / feather, 0, 1) * np.clip(np.minimum(uu, Wv - uu) / 4, 0, 1) * (den > 0)
        if len(rows) == 1:
            w = np.ones_like(w)
        acc += np.asarray(warped, np.float64) * w[..., None]
        wsum += w
    res = acc / np.maximum(wsum, 1e-6)[..., None]
    return Image.fromarray(np.clip(res, 0, 255).astype(np.uint8))
