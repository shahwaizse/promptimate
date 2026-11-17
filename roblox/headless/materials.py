"""Our own material textures, generated (no Studio, no downloads): one tileable 512x512 RGB detail map per Roblox
material, centred on 1.0 so the renderer multiplies it over the part's colour. A map covers TILE studs.

    python roblox/headless/materials.py      # writes <cache>/mat/<Material>.png and a preview sheet"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import meshcache as MC  # noqa: E402

OUT = MC.OUT.parent / "mat"
N = 512
TILE = {"Brick": 8.0, "WoodPlanks": 8.0, "Cobblestone": 8.0, "DiamondPlate": 4.0, "Fabric": 2.0}   # studs per map
DEFAULT_TILE = 8.0
rng = np.random.default_rng(7)


def noise(scale: int, octaves: int = 4, n: int = N) -> np.ndarray:
    """Tileable value noise in [0, 1]: random grids, bicubic-upsampled with wrap-around, summed over octaves."""
    out = np.zeros((n, n))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        g = max(2, scale * 2 ** o)
        r = rng.random((g, g))
        big = np.tile(r, (3, 3))
        im = Image.fromarray((big * 255).astype("uint8")).resize((n * 3, n * 3), Image.BICUBIC)
        out += amp * (np.asarray(im, float)[n:2 * n, n:2 * n] / 255)
        tot += amp
        amp *= 0.5
    return out / tot


def _norm(a: np.ndarray, contrast: float) -> np.ndarray:
    a = (a - a.mean()) / (a.std() + 1e-6)
    return 1.0 + a * contrast


def bricks(rows=8, cols=4, mortar=0.06):
    y, x = np.mgrid[0:N, 0:N] / N
    r = np.floor(y * rows)
    xs = x * cols + (r % 2) * 0.5
    fx, fy = xs % 1, (y * rows) % 1
    is_mortar = (fx < mortar) | (fy < mortar * 2)
    brick_id = (np.floor(xs) + r * 31) % 97
    tone = 0.9 + 0.2 * ((brick_id * 0.6180339) % 1)
    m = np.where(is_mortar, 1.55, tone * _norm(noise(16, 3), 0.05))
    return m


def planks(rows=6, seam=0.025):
    y, x = np.mgrid[0:N, 0:N] / N
    r = np.floor(y * rows)
    fy = (y * rows) % 1
    shift = ((r * 0.37) % 1)
    fx = (x + shift) % 1
    grain = noise(4, 3)[:, :] * 0.6 + np.sin((y * rows * 40 + noise(8, 2) * 6) * np.pi) * 0.12
    tone = 0.92 + 0.16 * ((r * 0.618) % 1)
    m = tone * _norm(grain, 0.06)
    m = np.where((fy < seam) | (fx < seam * 0.6), 0.62, m)
    return m


def wood():
    y, x = np.mgrid[0:N, 0:N] / N
    return _norm(np.sin((y * 30 + noise(6, 3) * 5) * np.pi) * 0.5 + noise(32, 2) * 0.5, 0.07)


def cobble(cells=40):
    pts = rng.random((cells, 2))
    y, x = np.mgrid[0:N, 0:N] / N
    d1 = np.full((N, N), 9.0); d2 = np.full((N, N), 9.0); idx = np.zeros((N, N), int)
    for i, (px, py) in enumerate(pts):
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                d = np.hypot(x - px - ox, y - py - oy)
                closer = d < d1
                d2 = np.where(closer, d1, np.minimum(d2, d))
                idx = np.where(closer, i, idx)
                d1 = np.where(closer, d, d1)
    edge = np.clip((d2 - d1) * 25, 0, 1)
    tone = 0.85 + 0.3 * ((idx * 0.618) % 1)
    return (0.55 + 0.45 * edge) * tone


def diamond():
    y, x = np.mgrid[0:N, 0:N] / N * 8
    u, v = (x + y) % 1, (x - y) % 1
    bump = ((np.abs(u - 0.5) < 0.12) & (np.abs(v - 0.5) < 0.35)).astype(float)
    return 1.0 + bump * 0.18 - 0.05


def fabric():
    y, x = np.mgrid[0:N, 0:N] / N * 64
    w = (np.sin(x * np.pi) * np.sin(y * np.pi))
    return _norm(w + noise(32, 2) * 0.5, 0.06)


def marble():
    y, x = np.mgrid[0:N, 0:N] / N
    v = np.abs(np.sin((x * 3 + y * 2 + noise(3, 5) * 4) * np.pi))
    return 1.04 - (1 - v) ** 8 * 0.35


def brushed():
    n = noise(64, 2)
    s = np.asarray(Image.fromarray((n * 255).astype("uint8")).resize((N, 8)).resize((N, N)), float) / 255
    return _norm(s, 0.04)


MATERIALS = {
    "Brick": lambda: bricks(), "WoodPlanks": lambda: planks(), "Wood": lambda: wood(),
    "Concrete": lambda: _norm(noise(24, 4), 0.06), "Sand": lambda: _norm(noise(96, 2), 0.07),
    "Pebble": lambda: cobble(160) * _norm(noise(64, 2), 0.04), "Cobblestone": lambda: cobble(48),
    "Grass": lambda: _norm(noise(128, 2) * 0.6 + noise(16, 3) * 0.4, 0.12),
    "Slate": lambda: _norm(noise(8, 5), 0.09), "Granite": lambda: _norm(noise(128, 3), 0.1),
    "Marble": lambda: marble(), "Fabric": lambda: fabric(), "Metal": lambda: brushed(),
    "DiamondPlate": lambda: diamond(), "Asphalt": lambda: _norm(noise(128, 3), 0.08),
    "Ice": lambda: _norm(noise(6, 4), 0.04), "Foil": lambda: _norm(noise(40, 3), 0.1),
}


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, f in MATERIALS.items():
        a = np.clip(f(), 0.3, 1.7)
        img = (a / 2 * 255).clip(0, 255).astype("uint8")      # stored at half scale: 128 = x1.0
        Image.fromarray(np.dstack([img] * 3)).save(OUT / f"{name}.png")
        out[name] = OUT / f"{name}.png"
    return out


if __name__ == "__main__":
    r = build()
    tiles = [Image.open(p).resize((160, 160)) for p in r.values()]
    sheet = Image.new("RGB", (160 * 9, 160 * 2), (0, 0, 0))
    for i, t in enumerate(tiles):
        sheet.paste(Image.fromarray((np.asarray(t, float) * 2 * np.array([0.75, 0.55, 0.4])).clip(0, 255).astype("uint8")),
                    ((i % 9) * 160, (i // 9) * 160))
    sheet.save(MC.OUT.parent / "materials_preview.jpg")
    print(len(r), "materials ->", OUT)
