r"""Before/after still comparison: the earlier URP shorts (low-poly CC0 cast) next to frames of "Your Move".

    .venv\Scripts\python.exe demo\fidelity\compare.py --run final

Writes build/compare_before_after.png and build/stills/ (full-resolution stills from the final frames).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
FF = r"D:\tools\ffmpeg\bin\ffmpeg.exe"
FONT = r"C:\Windows\Fonts\segoeui.ttf"
OLD = [ROOT / "demo/shorts_template/build/last_bus/last_bus.mp4", ROOT / "demo/shorts_template/build/wrong_turn/wrong_turn.mp4"]


def grab(mp4: Path, t: float, out: Path) -> Path:
    subprocess.run([FF, "-v", "error", "-y", "-ss", str(t), "-i", str(mp4), "-frames:v", "1", str(out)], check=True)
    return out


def frame_at(run: Path, film: dict, t: float) -> Path:
    for s in film["shots"]:
        if s["t0"] <= t < s["t1"]:
            f = run / s["id"] / f"f{int(round((t - s['t0']) * film['fps'])):04d}.png"
            if f.exists():
                return f
    raise FileNotFoundError(t)


def fit(im: Image.Image, w: int, h: int) -> Image.Image:
    im = im.copy()
    im.thumbnail((w, h), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), (12, 12, 12))
    canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return canvas


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="final")
    ap.add_argument("--times", default="2.5,13.6,22.8,27.9,31.5,7.0")
    a = ap.parse_args()
    run = BUILD / a.run
    film = json.loads((run / "film.json").read_text())
    stills = BUILD / "stills"
    stills.mkdir(exist_ok=True)
    news = []
    for i, t in enumerate(float(x) for x in a.times.split(",")):
        src = frame_at(run, film, t)
        dst = stills / f"your_move_{i + 1:02d}_{t:05.2f}s.png"
        shutil.copyfile(src, dst)
        news.append(dst)
    tmp = BUILD / "before"
    tmp.mkdir(exist_ok=True)
    olds = [grab(OLD[0], 14, tmp / "last_bus_14.png"), grab(OLD[0], 22, tmp / "last_bus_22.png"),
            grab(OLD[1], 6, tmp / "wrong_turn_6.png")]

    W, H, pad, head = 2400, 1000, 24, 70
    out = Image.new("RGB", (W, H), (8, 8, 8))
    d = ImageDraw.Draw(out)
    f1 = ImageFont.truetype(FONT, 34)
    f2 = ImageFont.truetype(FONT, 22)
    ph = H - head - 50                      # portrait frame height (left)
    pw = int(ph * 9 / 16)
    leftw = 2 * pw + pad
    d.text((pad, 16), "Before: URP shorts, low-poly CC0 cast", font=f1, fill=(200, 200, 200))
    for k, p in enumerate(olds[:2]):
        out.paste(fit(Image.open(p).convert("RGB"), pw, ph), (pad + k * (pw + pad), head))
    x0 = 2 * pad + leftw
    d.text((x0, 16), "After: HDRP path tracer, Rocketbox humans, Poly Haven set", font=f1, fill=(236, 222, 196))
    rw = (W - x0 - 2 * pad) // 2
    rh = int(rw / 2.353)
    for k, p in enumerate(news):
        out.paste(fit(Image.open(p).convert("RGB"), rw, rh), (x0 + (k % 2) * (rw + pad), head + (k // 2) * (rh + pad)))
    d.text((pad, H - 34), "Same motion pipeline (Promptimate / Kimodo clips, continue_from chains, seats); only the render route differs.",
           font=f2, fill=(150, 150, 150))
    out.save(BUILD / "compare_before_after.png")
    print("wrote", BUILD / "compare_before_after.png", "and", len(news), "stills in", stills)


if __name__ == "__main__":
    main()
