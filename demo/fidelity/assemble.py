r"""Cuts the rendered shots of "Your Move" into the final film: letterboxed 2.39:1 in a 1920x1080 frame, a light
film grain, title and end cards, and a sound mix (CC0 music and effects from audio_assets.json, timed to the story
events the motions produced).

    .venv\Scripts\python.exe demo\fidelity\assemble.py --run pt_96_816p [--out your_move.mp4]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
FF = r"D:\tools\ffmpeg\bin\ffmpeg.exe"
W, H, FPS = 1920, 1080, 24
TITLE_S, END_S = 3.5, 4.0
FONT_TITLE = r"C:\Windows\Fonts\georgia.ttf"
FONT_SMALL = r"C:\Windows\Fonts\segoeuil.ttf"


def sh(cmd: list[str]) -> None:
    print(" ".join(cmd[:6]), "...", flush=True)
    subprocess.run(cmd, check=True)


def tracked(draw: ImageDraw.ImageDraw, text: str, font, y: int, track: float, fill) -> None:
    widths = [draw.textlength(c, font=font) for c in text]
    total = sum(widths) + track * (len(text) - 1)
    x = (W - total) / 2
    for c, w in zip(text, widths):
        draw.text((x, y), c, font=font, fill=fill)
        x += w + track


def card(path: Path, lines: list[tuple[str, str, int, float, tuple, int]]) -> None:
    im = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(im)
    for text, font, size, track, fill, y in lines:
        tracked(d, text, ImageFont.truetype(font, size), y, track, fill)
    im.save(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--grain", type=float, default=5)
    a = ap.parse_args()
    run = BUILD / a.run
    film = json.loads((run / "film.json").read_text())
    ev = json.loads((run / "events.json").read_text())
    shots = [s for s in film["shots"] if (run / s["id"]).exists()]
    tmp = run / "_cut"
    tmp.mkdir(exist_ok=True)

    # 1. Each shot -> letterboxed, graded clip. Short cross-dissolves only on the first and last shots (fades).
    clips = []
    for i, s in enumerate(shots):
        out = tmp / f"{i:02d}_{s['id']}.mp4"
        fw, fh = film["width"], film["height"]
        scale = W / fw
        vh = int(round(fh * scale / 2) * 2)
        vf = [f"scale={W}:{vh}:flags=lanczos", f"pad={W}:{H}:0:{(H - vh) // 2}:black"]
        if a.grain > 0:
            vf.insert(1, f"noise=c0s={a.grain}:c0f=t+u")
        dur = round((s["t1"] - s["t0"]), 3)
        if i == 0:
            vf.append("fade=t=in:st=0:d=1.2")
        if i == len(shots) - 1:
            vf.append(f"fade=t=out:st={max(0, dur - 1.6):.2f}:d=1.6")
        sh([FF, "-v", "error", "-y", "-framerate", str(FPS), "-i", str(run / s["id"] / "f%04d.png"), "-vf", ",".join(vf),
            "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", str(out)])
        clips.append(out)

    # 2. Title (over black, after the last shot) and end card.
    card(tmp / "title.png", [("YOUR MOVE", FONT_TITLE, 84, 26, (236, 226, 208), 470)])
    card(tmp / "end.png", [
        ("Every motion in this film was generated from a text prompt,", FONT_SMALL, 38, 1, (210, 204, 194), 420),
        ("on one consumer GPU, and rendered in Unity.", FONT_SMALL, 38, 1, (210, 204, 194), 474),
        ("PROMPTIMATE", FONT_TITLE, 56, 18, (236, 226, 208), 580)])
    for name, d in (("title", TITLE_S), ("end", END_S)):
        sh([FF, "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-t", str(d), "-i", str(tmp / f"{name}.png"),
            "-vf", f"fade=t=in:st=0:d=0.8,fade=t=out:st={d - 0.8}:d=0.8", "-c:v", "libx264", "-preset", "slow", "-crf", "14",
            "-pix_fmt", "yuv420p", str(tmp / f"{name}.mp4")])
    clips += [tmp / "title.mp4", tmp / "end.mp4"]
    (tmp / "list.txt").write_text("".join(f"file '{c.as_posix()}'\n" for c in clips))
    picture = tmp / "picture.mp4"
    sh([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"), "-c", "copy", str(picture)])

    # 3. Sound. Story time maps 1:1 onto film time (the cut starts at story t = 0 and has no gaps).
    t_story_end = shots[-1]["t1"]
    total = t_story_end - shots[0]["t0"] + TITLE_S + END_S
    au = BUILD / "audio"
    t0 = shots[0]["t0"]
    events = [  # (file, film time, gain dB, trim start, trim duration, fade)
        ("roomtone.mp3", 0.0, -16, 2.0, total, 1.5),
        ("birds.mp3", 0.0, -13, 20.0, t_story_end - t0, 2.0),
        ("clock.mp3", 0.0, 5, 1.0, t_story_end - t0, 1.0),
        ("gymnopedie.mp3", 0.6, -9, 0.0, total - 0.6, 2.5),
        ("steps.mp3", ev["d_door"] - 1.0 - t0, -7, 1.0, 4.4, 0.4),
        ("suitcase.mp3", ev["d_set"] + 1.25 - t0, -3, 0.0, 2.0, 0.05),
        ("steps.mp3", ev["d_walk"] - t0, -8, 6.0, 3.3, 0.4),
        ("steps.mp3", ev["f_gesture"] + 2.7 - t0, -11, 12.0, 1.8, 0.3),
        ("chess.mp3", ev["f_reach"] + 1.72 - t0, -9, 0.0, 0.6, 0.02),
    ]
    inputs, filters = [], []
    for k, (f, at, gain, ss, dur, fade) in enumerate(events):
        inputs += ["-ss", f"{ss:.2f}", "-t", f"{dur:.2f}", "-i", str(au / f)]
        filters.append(f"[{k + 1}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={gain}dB,"
                       f"afade=t=in:d={fade},afade=t=out:st={max(0, dur - fade * 2):.2f}:d={fade * 2:.2f},"
                       f"adelay={int(at * 1000)}|{int(at * 1000)}[a{k}]")
    mix = "".join(f"[a{k}]" for k in range(len(events)))
    filters.append(f"{mix}amix=inputs={len(events)}:normalize=0,afade=t=out:st={total - 2.5:.2f}:d=2.5,"
                   f"loudnorm=I=-18:TP=-1.5:LRA=11[aout]")
    out = BUILD / (a.out or f"your_move.mp4")
    sh([FF, "-v", "error", "-y", "-i", str(picture)] + inputs + ["-filter_complex", ";".join(filters), "-map", "0:v",
        "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(out)])
    print("wrote", out, f"{total:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
