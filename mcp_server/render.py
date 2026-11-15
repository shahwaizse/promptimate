"""Visuals for humans and for an AI judge: animated stick-figure GIFs (side-by-side comparisons) and a dense
judge contact sheet (front + side rows, top-down path with heading, height/contact timeline).

Input everywhere is global joint positions pos (F,30,3) in Kimodo space (Y-up, metres), e.g. motion.fk(root, rot).
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

import motion
import postprocess

NAMES, PARENTS = motion.NAMES, motion.PARENTS
FPS = motion.FPS

_LEFT = (37, 99, 235)
_RIGHT = (220, 38, 38)
_MID = (30, 30, 30)
_CONTACT = (22, 163, 74)
_GRID = (205, 205, 205)


def _bone_color(j):
    return _LEFT if "Left" in NAMES[j] else (_RIGHT if "Right" in NAMES[j] else _MID)


class _Camera:
    """Orthographic camera at yaw `a` (0 = in front of a +Z-facing character) and pitch `e` (looking down)."""

    def __init__(self, yaw_deg=35.0, pitch_deg=18.0):
        a, e = np.radians(yaw_deg), np.radians(pitch_deg)
        self.right = np.array([np.cos(a), 0.0, -np.sin(a)])
        fh = -np.array([np.sin(a), 0.0, np.cos(a)])           # horizontal direction camera -> target
        self.up = np.array([0.0, np.cos(e), 0.0]) + np.sin(e) * fh
        self.view = np.cos(e) * fh - np.array([0.0, np.sin(e), 0.0])

    def project(self, d):
        return d @ self.right, d @ self.up, d @ self.view


def _follow(pos, fps, tau=0.35):
    """Camera target: hips xz, critically smoothed so the camera lags gently instead of shaking."""
    c = pos[:, 0].astype(np.float64).copy()
    c[:, 1] = 0.0
    a = 1.0 - np.exp(-1.0 / (tau * fps))
    out = c.copy()
    for f in range(1, len(c)):
        out[f] = out[f - 1] + a * (c[f] - out[f - 1])
    return out


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_panel(img, box, pos, f, contacts, center, cam, scale, title, trail_s=1.5, fps=FPS):
    from PIL import ImageDraw
    x0, y0, w, h = box
    dr = ImageDraw.Draw(img)
    ox, oy = x0 + w / 2, y0 + h * 0.80

    def to_px(p):
        u, v, _ = cam.project(np.asarray(p, np.float64) - center)
        return ox + u * scale, oy - v * scale

    # ground grid (0.5 m), clipped to a disc around the camera target
    g = 0.5
    cx, cz = np.floor(center[0] / g) * g, np.floor(center[2] / g) * g
    R = 2.5
    for k in np.arange(-R, R + 1e-6, g):
        for a_, b_ in ((np.array([cx + k, 0, cz - R]), np.array([cx + k, 0, cz + R])),
                       (np.array([cx - R, 0, cz + k]), np.array([cx + R, 0, cz + k]))):
            dr.line([to_px(a_), to_px(b_)], fill=_GRID, width=1)
    # footprints: past contact positions (fading) -> skating shows up as smears
    t0 = max(0, f - int(trail_s * fps))
    for key, j in (("left_heel", 24), ("left_toe", 25), ("right_heel", 28), ("right_toe", 29)):
        m = contacts[key]
        for k in range(t0, f + 1):
            if m[k]:
                fade = (k - t0 + 1) / (f - t0 + 1)
                col = tuple(int(255 - (255 - c) * (0.25 + 0.5 * fade)) for c in _CONTACT)
                px, py = to_px([pos[k, j, 0], 0.0, pos[k, j, 2]])
                rr = 3.5 if key.endswith("toe") else 2.5
                dr.ellipse([px - rr, py - rr * 0.6, px + rr, py + rr * 0.6], fill=col)
    # shadow under hips
    sx, sy = to_px([pos[f, 0, 0], 0.0, pos[f, 0, 2]])
    dr.ellipse([sx - 0.18 * scale, sy - 0.05 * scale, sx + 0.18 * scale, sy + 0.05 * scale], fill=(225, 225, 225))
    # bones, far-to-near
    p = pos[f]
    depth = [cam.project(p[j] - center)[2] for j in range(len(NAMES))]
    order = sorted([j for j in range(len(NAMES)) if PARENTS[j] >= 0], key=lambda j: -depth[j])
    for j in order:
        if j in (7, 8, 9):  # jaw/eyes clutter the head
            continue
        dr.line([to_px(p[PARENTS[j]]), to_px(p[j])], fill=_bone_color(j), width=max(2, int(scale / 55)))
    hx, hy = to_px(p[6])
    r = 0.09 * scale
    dr.ellipse([hx - r, hy - r * 1.1, hx + r, hy + r * 0.9], outline=_MID, width=2)
    # contact markers on the feet
    for key, j in (("left_heel", 24), ("left_toe", 25), ("right_heel", 28), ("right_toe", 29)):
        if contacts[key][f]:
            px, py = to_px(p[j])
            dr.ellipse([px - 4, py - 4, px + 4, py + 4], fill=_CONTACT)
    font = _font(14)
    if title:
        dr.text((x0 + 8, y0 + 6), title[:48], fill=(20, 20, 20), font=font)
    dr.text((x0 + 8, y0 + h - 20), f"t={f / fps:4.1f}s", fill=(90, 90, 90), font=font)


def render_gif(pos_or_list, out_path, titles=None, fps=15, src_fps=FPS, panel=(360, 420), yaw_deg=35.0,
               max_seconds=None):
    """Animated stick figure(s), ground grid, gently following 3/4 camera, foot contacts in green (current contact
    dots + fading footprints so skating shows as smears). A list of pos arrays renders side by side (before/after).
    Writes a GIF (palette-quantised, small); if out_path ends in .mp4 and imageio-ffmpeg is installed, an MP4."""
    from PIL import Image
    poss = pos_or_list if isinstance(pos_or_list, (list, tuple)) else [pos_or_list]
    poss = [np.asarray(p, np.float64) for p in poss]
    titles = list(titles or [""] * len(poss))
    F = max(len(p) for p in poss)
    if max_seconds:
        F = min(F, int(max_seconds * src_fps))
    frames_idx = np.arange(0, F, src_fps / fps).round().astype(int)
    frames_idx = frames_idx[frames_idx < F]
    cam = _Camera(yaw_deg)
    pw, ph = panel
    scale = ph / 2.6
    contacts = [postprocess.detect_contacts(p, src_fps) for p in poss]
    centers = [_follow(p, src_fps) for p in poss]
    imgs = []
    for f in frames_idx:
        img = Image.new("RGB", (pw * len(poss), ph), (255, 255, 255))
        for k, p in enumerate(poss):
            ff = min(f, len(p) - 1)
            _draw_panel(img, (k * pw, 0, pw, ph), p, ff, contacts[k], centers[k][ff], cam, scale, titles[k],
                        fps=src_fps)
            if k:
                from PIL import ImageDraw
                ImageDraw.Draw(img).line([(k * pw, 0), (k * pw, ph)], fill=(180, 180, 180), width=1)
        imgs.append(img)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".mp4":
        import imageio.v2 as imageio  # optional dependency (imageio + imageio-ffmpeg)
        with imageio.get_writer(out_path, fps=fps, codec="libx264", quality=7) as wr:
            for im in imgs:
                wr.append_data(np.asarray(im))
        return out_path
    pal = imgs[len(imgs) // 2].quantize(colors=48, method=Image.Quantize.MEDIANCUT)
    q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in imgs]
    q[0].save(out_path, save_all=True, append_images=q[1:], duration=int(round(1000 / fps)), loop=0,
              optimize=True, disposal=1)
    return out_path


# ----------------------------------------------------------------------------------------------- judge sheet
def _heading_smooth(pos):
    left = pos[:, 22] - pos[:, 26]
    fwd = np.stack([-left[:, 2], np.zeros(len(pos)), left[:, 0]], 1)  # left x up (right-handed) = forward
    fwd = postprocess._filter(fwd, 3.0)
    return np.arctan2(fwd[:, 0], fwd[:, 2])


def _stick(ax, p, cam, contacts_f, ground=True):
    c = p[0].copy()
    c[1] = 0.0
    uv = np.array([cam.project(q - c)[:2] for q in p])
    if ground:
        ax.plot([-0.9, 0.9], [0.0, 0.0], color="0.75", lw=1)
    for j, par in enumerate(PARENTS):
        if par < 0 or j in (7, 8, 9):
            continue
        col = np.array(_bone_color(j)) / 255
        ax.plot([uv[par, 0], uv[j, 0]], [uv[par, 1], uv[j, 1]], color=col, lw=2, solid_capstyle="round")
    ax.add_patch(__import__("matplotlib").patches.Circle(uv[6], 0.085, fill=False, color="0.15", lw=1.5))
    for j, on in contacts_f.items():
        if on:
            ax.plot(uv[j, 0], uv[j, 1], "o", color=np.array(_CONTACT) / 255, ms=5)


def render_judge_sheet(pos, out_png, title="", n=8, fps=FPS):
    """Contact sheet for an AI judge (~1600 px wide): n frames from the front and from the side (camera relative
    to the body's facing at that frame), a top-down root path with heading arrows and time ticks, and a timeline
    of hand / hip heights with foot-contact bars."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    pos = np.asarray(pos, np.float64)
    F = len(pos)
    idx = np.linspace(0, F - 1, n).round().astype(int)
    contacts = postprocess.detect_contacts(pos, fps)
    psi = _heading_smooth(pos)
    fig = plt.figure(figsize=(16, 8.4), dpi=100)
    gs = GridSpec(3, n, figure=fig, height_ratios=[1.0, 1.0, 1.05], hspace=0.22, wspace=0.05)
    cj = {24: "left_heel", 25: "left_toe", 28: "right_heel", 29: "right_toe"}
    lo_y, hi_y = -0.05, max(2.0, float(pos[:, :, 1].max()) + 0.1)
    for row, (label, yaw_off) in enumerate((("front", 0.0), ("side (from character's left)", 90.0))):
        for k, f in enumerate(idx):
            ax = fig.add_subplot(gs[row, k])
            cam = _Camera(yaw_deg=np.degrees(psi[f]) + yaw_off, pitch_deg=0.0)
            _stick(ax, pos[f], cam, {j: contacts[name][f] for j, name in cj.items()})
            ax.set_xlim(-0.95, 0.95)
            ax.set_ylim(lo_y, hi_y)
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            for s in ax.spines.values():
                s.set_color("0.85")
            if row == 0:
                ax.set_title(f"t={f / fps:.2f}s  (#{f})", fontsize=10)
            if k == 0:
                ax.set_ylabel(label, fontsize=10)
    # top-down path
    ax = fig.add_subplot(gs[2, :3])
    x, z = pos[:, 0, 0], pos[:, 0, 2]
    for key, j, col in (("left_toe", 25, _LEFT), ("right_toe", 29, _RIGHT)):
        m = contacts[key]
        ax.scatter(pos[m, j, 0], pos[m, j, 2], s=4, color=np.array(col) / 255, alpha=0.35, lw=0)
    ax.plot(x, z, color="0.2", lw=1.3)
    step = max(1, int(round(0.5 * fps)))
    span = max(np.ptp(x), np.ptp(z), 0.5)
    L = 0.08 * span
    for f in range(0, F, step):
        ax.annotate("", xy=(x[f] + L * np.sin(psi[f]), z[f] + L * np.cos(psi[f])), xytext=(x[f], z[f]),
                    arrowprops=dict(arrowstyle="->", color="tab:orange", lw=1.2))
    for f in range(0, F, int(fps)):
        ax.plot(x[f], z[f], "k.", ms=4)
        ax.annotate(f"{f / fps:.0f}s", (x[f], z[f]), textcoords="offset points", xytext=(4, 3), fontsize=7)
    ax.plot(x[0], z[0], "o", color="tab:green", ms=7, label="start")
    ax.plot(x[-1], z[-1], "s", color="tab:red", ms=7, label="end")
    pad = 0.1 * span + 0.2
    ax.set_xlim(x.min() - pad, x.max() + pad)
    ax.set_ylim(z.min() - pad, z.max() + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("x (m)  [+x = character's initial left]", fontsize=8)
    ax.set_ylabel("z (m)  [+z = initial facing]", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=7, loc="lower right")
    ax.set_title("top-down hips path, arrows = facing every 0.5 s, dots = toe contacts", fontsize=9)
    # timeline
    ax = fig.add_subplot(gs[2, 3:])
    t = np.arange(F) / fps
    ax.plot(t, pos[:, 13, 1], color=np.array(_LEFT) / 255, lw=1.4, label="left hand")
    ax.plot(t, pos[:, 19, 1], color=np.array(_RIGHT) / 255, lw=1.4, label="right hand")
    ax.plot(t, pos[:, 0, 1], color="0.2", lw=1.4, label="hips")
    ax.plot(t, pos[:, 6, 1], color="0.55", lw=1.0, ls="--", label="head")
    for k, (key, col) in enumerate((("left_heel", _LEFT), ("left_toe", _LEFT), ("right_heel", _RIGHT),
                                    ("right_toe", _RIGHT))):
        for s, e in postprocess.spans(contacts[key]):
            ax.broken_barh([(s / fps, (e - s) / fps)], (-0.32 + 0.07 * k, 0.05), color=np.array(col) / 255,
                           alpha=0.45 if "heel" in key else 0.85)
    ax.text(0.005 * t[-1], -0.03, "foot contacts: L heel, L toe, R heel, R toe (bottom to top)", fontsize=7,
            va="bottom", ha="left", color="0.3")
    for f in idx:
        ax.axvline(f / fps, color="0.85", lw=0.8, zorder=0)
    ax.axhline(0, color="0.7", lw=0.8)
    ax.set_xlim(0, t[-1] if F > 1 else 1)
    ax.set_ylim(-0.35, max(2.1, float(pos[:, [6, 13, 19], 1].max()) + 0.1))
    ax.set_xlabel("time (s)", fontsize=8)
    ax.set_ylabel("height (m)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=7, ncol=4, loc="upper right")
    ax.set_title("heights over time (grey lines = sampled frames)", fontsize=9)
    st = motion.stats(pos.astype(np.float32))
    fig.suptitle(f"{title[:150]}\n{st['duration_s']} s, travel {st['root_displacement_m']} m, hips "
                 f"{st['min_hips_height_m']}-{st['max_hips_height_m']} m  |  blue = left, red = right, "
                 f"green dots = foot contact", fontsize=11)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    return out_png


def render_takes_sheet(pos_list, out_png, titles, n=8, panel=(150, 200)):
    """One row per take: n stick frames (3/4 view following the character, foot contacts in green), drawn with PIL
    (~0.1 s per take instead of ~0.6 s with matplotlib) so a judge can compare variations at a glance."""
    from PIL import Image as PILImage, ImageDraw

    pw, ph = panel
    label_h = 22
    sheet = PILImage.new("RGB", (pw * n, (ph + label_h) * len(pos_list)), "white")
    dr = ImageDraw.Draw(sheet)
    cam = _Camera()
    for row, (pos, title) in enumerate(zip(pos_list, titles)):
        pos = np.asarray(pos, np.float64)
        contacts = postprocess.detect_contacts(pos, FPS)
        center = _follow(pos, FPS)
        y = row * (ph + label_h)
        dr.text((6, y + 4), str(title)[:140], fill=(20, 20, 20), font=_font(13))
        for k, f in enumerate(np.linspace(0, len(pos) - 1, n).round().astype(int)):
            tile = PILImage.new("RGB", (pw, ph), "white")
            _draw_panel(tile, (0, 0, pw, ph), pos, f, contacts, center[f], cam, ph / 2.3, "", trail_s=0.0)
            sheet.paste(tile, (k * pw, y + label_h))
        dr.line([(0, y + ph + label_h - 1), (pw * n, y + ph + label_h - 1)], fill=(200, 200, 200))
    sheet.save(out_png)
    return Path(out_png)
