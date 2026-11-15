"""Render a Promptimate motion folder as a clean gray mannequin MP4 (driver video for AI motion transfer).

Pure numpy software renderer (no Unity): the body is a union of swept spheres along the 30-joint SOMA skeleton,
z-buffered and Lambert shaded, with a fixed perspective camera framed so the whole clip stays in shot.

usage: python render_mannequin.py MOTION_DIR OUT.mp4 [--w 720 --h 1280 --yaw 15 --fill 0.80]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mcp_server"))
import motion as M  # noqa: E402

FFMPEG = r"D:\Tools\ffmpeg\bin\ffmpeg.exe"
N = {n: i for i, n in enumerate(M.NAMES)}

# (joint a, joint b, radius a, radius b) in metres
BONES = [
    ("Hips", "Spine1", .115, .115), ("Spine1", "Spine2", .115, .12), ("Spine2", "Chest", .12, .13),
    ("Chest", "Neck1", .125, .07), ("Neck1", "Neck2", .05, .048), ("Neck2", "Head", .048, .05),
    ("Chest", "LeftShoulder", .09, .065), ("LeftShoulder", "LeftArm", .065, .058),
    ("Chest", "RightShoulder", .09, .065), ("RightShoulder", "RightArm", .065, .058),
    ("LeftArm", "LeftForeArm", .052, .042), ("LeftForeArm", "LeftHand", .042, .032),
    ("RightArm", "RightForeArm", .052, .042), ("RightForeArm", "RightHand", .042, .032),
    ("LeftHand", "LeftHandMiddleEnd", .034, .022), ("LeftHand", "LeftHandThumbEnd", .018, .013),
    ("RightHand", "RightHandMiddleEnd", .034, .022), ("RightHand", "RightHandThumbEnd", .018, .013),
    ("Hips", "LeftLeg", .11, .085), ("Hips", "RightLeg", .11, .085),
    ("LeftLeg", "LeftShin", .08, .055), ("LeftShin", "LeftFoot", .055, .04),
    ("RightLeg", "RightShin", .08, .055), ("RightShin", "RightFoot", .055, .04),
    ("LeftFoot", "LeftToeBase", .045, .035), ("RightFoot", "RightToeBase", .045, .035),
]


GRAY = np.array([0.58, 0.59, 0.61])
DRESS = {"shirt": np.array([0.20, 0.36, 0.62]), "pants": np.array([0.22, 0.22, 0.25]), "shoes": np.array([0.85, 0.85, 0.85]),
         "skin": np.array([0.85, 0.66, 0.52]), "hair": np.array([0.18, 0.12, 0.08]), "eyes": np.array([0.05, 0.05, 0.05])}


def part(a: str, b: str) -> str:
    if "Hand" in b and "Fore" not in a or "Hand" in a:
        return "skin"
    if b in ("Neck2", "Head"):
        return "skin"
    if "Toe" in b:
        return "shoes"
    if "Leg" in b or "Shin" in b or "Foot" in b:
        return "pants"
    if a == "Hips" and b == "Spine1":
        return "pants"
    return "shirt"


STYLE = "gray"


def col(name):
    return GRAY if STYLE == "gray" else DRESS[name]


def spheres(p: np.ndarray):
    """Per-frame sphere centres (S,3), radii (S,) and colours (S,3) for joint positions p (J,3)."""
    cs, rs, ks = [], [], []
    for a, b, ra, rb in BONES:
        pa, pb = p[N[a]], p[N[b]]
        n = max(2, int(np.linalg.norm(pb - pa) / (min(ra, rb) * 0.12)) + 1)
        t = np.linspace(0, 1, n)[:, None]
        cs.append(pa + (pb - pa) * t); rs.append(ra + (rb - ra) * t[:, 0]); ks.append(np.repeat(col(part(a, b))[None], n, 0))
    # head: sphere centred between Head joint and eyes, plus a small nose so front/back is readable
    eyes = (p[N["LeftEye"]] + p[N["RightEye"]]) / 2
    head_c = p[N["Head"]] * 0.45 + eyes * 0.55 + np.array([0, 0.015, 0])
    fwd = eyes - p[N["Head"]]; fwd[1] = 0; fwd /= np.linalg.norm(fwd) + 1e-6
    def add(c, r, k):
        cs.append(np.asarray(c)[None]); rs.append(np.array([r])); ks.append(col(k)[None])
    add(head_c, 0.105, "skin")
    add(head_c + np.array([0, -0.06, 0]) + fwd * 0.03, 0.075, "skin")  # jaw/chin
    add(head_c + fwd * 0.10 + np.array([0, -0.01, 0]), 0.022, "skin")  # nose
    if STYLE != "gray":
        side = np.cross([0, 1, 0], fwd); side /= np.linalg.norm(side) + 1e-6
        add(head_c - fwd * 0.012 + np.array([0, 0.018, 0]), 0.104, "hair")  # hair cap: back and top of the head
        add(head_c - fwd * 0.03 + np.array([0, -0.02, 0]), 0.100, "hair")
        for sgn in (-1, 1):
            add(head_c + fwd * 0.088 + side * 0.038 * sgn + np.array([0, 0.02, 0]), 0.016, "eyes")
    return np.concatenate(cs), np.concatenate(rs), np.concatenate(ks)


class Camera:
    def __init__(self, pos_all: np.ndarray, w: int, h: int, yaw_deg: float, fill: float, fov_deg: float = 35.0):
        lo = pos_all.reshape(-1, 3).min(0) - 0.15
        hi = pos_all.reshape(-1, 3).max(0) + 0.15
        lo[1] = 0.0
        target = (lo + hi) / 2
        target[1] = max(target[1], 0.85)
        yaw = np.radians(yaw_deg)
        back = np.array([np.sin(yaw), 0.0, np.cos(yaw)])  # character faces +Z; camera in front
        self.w, self.h = w, h
        self.f = (h / 2) / np.tan(np.radians(fov_deg) / 2)
        corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        for dist in np.arange(2.0, 30.0, 0.05):
            self._set(target + back * dist + np.array([0, 0.25, 0]), target)
            uv, _ = self.project(corners)
            mx, my = w * (1 - fill) / 2, h * (1 - fill) / 2
            if (uv[:, 0] > mx).all() and (uv[:, 0] < w - mx).all() and (uv[:, 1] > my).all() and (uv[:, 1] < h - my).all():
                break

    def _set(self, eye, target):
        fwd = target - eye; fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0, 1, 0]); right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        self.eye, self.R = eye, np.stack([right, up, fwd])  # world -> cam (x right, y up, z forward)

    def to_cam(self, x):
        return (x - self.eye) @ self.R.T

    def project(self, x):
        c = self.to_cam(x)
        u = self.w / 2 + self.f * c[..., 0] / c[..., 2]
        v = self.h / 2 - self.f * c[..., 1] / c[..., 2]
        return np.stack([u, v], -1), c[..., 2]


def background(cam: Camera, w: int, h: int) -> np.ndarray:
    """Seamless studio backdrop: light floor plane fading into a light wall."""
    v, u = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.stack([(u - w / 2) / cam.f, -(v - h / 2) / cam.f, np.ones_like(u)], -1) @ cam.R  # cam -> world dirs
    t = -cam.eye[1] / np.minimum(d[..., 1], -1e-4)
    dist = np.where(d[..., 1] < -1e-4, t * np.linalg.norm(d, axis=-1), 1e9)
    floor_mix = np.clip(1 - (dist - 2) / 14, 0, 1)
    wall = np.array([0.86, 0.86, 0.85]); floor = np.array([0.80, 0.80, 0.79])
    img = wall * (1 - floor_mix[..., None]) + floor * floor_mix[..., None]
    return img.astype(np.float32)


def render_frame(p: np.ndarray, cam: Camera, bg: np.ndarray, ss: int = 2) -> np.ndarray:
    W, H = cam.w * ss, cam.h * ss
    c, r, k = spheres(p)
    uv, z = cam.project(c)
    uv *= ss
    R = cam.f * ss * r / z
    zbuf = np.full((H, W), np.inf, np.float32)
    nbuf = np.zeros((H, W, 3), np.float32)
    kbuf = np.zeros((H, W, 3), np.float32)
    for (cu, cv), zz, rr, RR, kk in zip(uv, z, r, R, k):
        x0, x1 = int(max(cu - RR, 0)), int(min(cu + RR + 1, W))
        y0, y1 = int(max(cv - RR, 0)), int(min(cv + RR + 1, H))
        if x0 >= x1 or y0 >= y1:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1]
        dx, dy = (xx - cu) / RR, (yy - cv) / RR
        d2 = dx * dx + dy * dy
        m = d2 < 1
        nz = np.sqrt(np.clip(1 - d2, 0, 1))
        depth = zz - rr * nz
        sub = zbuf[y0:y1, x0:x1]
        win = m & (depth < sub)
        sub[win] = depth[win]
        nb = nbuf[y0:y1, x0:x1]
        nb[win] = np.stack([dx, -dy, -nz], -1)[win]
        kbuf[y0:y1, x0:x1][win] = kk
    mask = np.isfinite(zbuf)
    # shading in camera space: key light upper-left-front, fill from right, rim from behind
    key = np.array([-0.45, 0.65, -0.6]); key /= np.linalg.norm(key)
    fill = np.array([0.6, 0.2, -0.5]); fill /= np.linalg.norm(fill)
    lam = np.clip(nbuf @ key, 0, 1) * 0.62 + np.clip(nbuf @ fill, 0, 1) * 0.22 + 0.26
    rim = np.clip(1 + nbuf[..., 2], 0, 1) ** 3 * 0.12
    body = np.clip(kbuf * (lam + rim)[..., None], 0, 1)
    # soft contact shadow: project sphere centres near the floor, splat dark blobs, blur
    img = np.array(Image.fromarray((bg * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)).astype(np.float32) / 255
    sh = Image.new("L", (W, H), 0)
    from PIL import ImageDraw
    dr = ImageDraw.Draw(sh)
    for cc, rr in zip(c, r):
        hgt = cc[1]
        if hgt > 0.6:
            continue
        g = cc.copy(); g[1] = 0
        guv, gzz = cam.project(g[None])
        gu, gv, gz = float(guv[0, 0]) * ss, float(guv[0, 1]) * ss, float(gzz[0])
        rad = float(cam.f * ss * (rr * 1.3 + 0.03) / gz)
        a = int(90 * (1 - hgt / 0.6))
        dr.ellipse([gu - rad, gv - rad * 0.35, gu + rad, gv + rad * 0.35], fill=a)
    sh = np.array(sh.filter(ImageFilter.GaussianBlur(6 * ss))).astype(np.float32) / 255
    img = img * (1 - 0.45 * sh[..., None])
    img[mask] = body[mask]
    out = Image.fromarray((img * 255).astype(np.uint8)).resize((cam.w, cam.h), Image.LANCZOS)
    return np.array(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("motion_dir"); ap.add_argument("out")
    ap.add_argument("--w", type=int, default=720); ap.add_argument("--h", type=int, default=1280)
    ap.add_argument("--yaw", type=float, default=15.0); ap.add_argument("--fill", type=float, default=0.80)
    ap.add_argument("--follow", action="store_true", help="translation-only follow camera")
    ap.add_argument("--style", default="gray", choices=["gray", "dressed"])
    ap.add_argument("--hold", type=float, default=0.0, help="seconds to hold the last pose")
    a = ap.parse_args()
    global STYLE
    STYLE = a.style
    root, rot = M.load(Path(a.motion_dir))
    pos = M.fk(root, rot)
    if a.hold > 0:
        pos = np.concatenate([pos, np.repeat(pos[-1:], int(a.hold * M.FPS), 0)])
    cam = Camera(pos, a.w, a.h, a.yaw, a.fill)
    bg = background(cam, a.w, a.h)
    follow = None
    if a.follow:
        # translation-only follow camera: smoothed hips ground track, fixed distance framing a 2.1 m tall body
        tr = pos[:, 0, :].copy(); tr[:, 1] = 0
        sig = M.FPS * 0.6; k = np.arange(-int(3 * sig), int(3 * sig) + 1); k = np.exp(-0.5 * (k / sig) ** 2); k /= k.sum()
        padded = np.concatenate([np.repeat(tr[:1], len(k) // 2, 0), tr, np.repeat(tr[-1:], len(k) // 2, 0)])
        tr = np.stack([np.convolve(padded[:, d], k, mode="valid") for d in range(3)], -1)
        yaw = np.radians(a.yaw); back = np.array([np.sin(yaw), 0.0, np.cos(yaw)])
        dist = (2.15 / 2) / np.tan(np.radians(35.0) / 2) / a.fill
        follow = (tr, back, dist)
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{a.w}x{a.h}", "-r", str(int(M.FPS)), "-i", "-", "-c:v", "libx264",
                             "-pix_fmt", "yuv420p", "-crf", "16", "-movflags", "+faststart", str(out)],
                            stdin=subprocess.PIPE)
    gt = []
    for i, p in enumerate(pos):
        if follow is not None:
            tr, back, dist = follow
            tgt = tr[i] + np.array([0, 1.0, 0])
            cam._set(tgt + back * dist + np.array([0, 0.15, 0]), tgt)
            if i % 3 == 0:
                bg = background(cam, a.w, a.h)
        frame = render_frame(p, cam, bg)
        uv, _ = cam.project(p)
        gt.append(uv.round(1).tolist())
        proc.stdin.write(frame.tobytes())
        if i == 0:
            Image.fromarray(frame).save(out.with_suffix(".first.png"))
    proc.stdin.close(); proc.wait()
    import json
    out.with_suffix(".joints2d.json").write_text(json.dumps({"names": M.NAMES, "w": a.w, "h": a.h, "uv": gt}))
    print(out, pos.shape[0], "frames")


if __name__ == "__main__":
    main()
