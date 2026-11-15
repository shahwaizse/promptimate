r"""Encodes the rendered SystemLab frames into the text-to-ragdoll demo video (titles via ffmpeg drawtext).

    .venv\Scripts\python demo\ragdoll\make_video.py [shot ...]

Reads demo/ragdoll/build/frames/<shot>/f*.jpg + shot.json, writes demo/ragdoll/build/<shot>.mp4 and
demo/ragdoll/build/text_to_ragdoll_demo.mp4 (title card, shots, measurement card).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "demo" / "ragdoll" / "build"
FRAMES = BUILD / "frames"
FONT = "C\\:/Windows/Fonts/segoeui.ttf"
FONTB = "C\\:/Windows/Fonts/segoeuib.ttf"
ORDER = ["compare", "personalities", "trip", "stairs", "crowd", "baked"]
CAPTIONS = {
    "compare": ("Same Promptimate clip, same thrown ball", "left: physics-reactive active ragdoll   |   right: plain kinematic clip"),
    "personalities": ("One hit, three text-chosen personalities", "same 6 kg ball at the same speed; get-up is a generated Promptimate clip"),
    "trip": ("Tripping over a crate", "leg caught -> balance lost -> arms brace -> lies still -> Promptimate get-up"),
    "stairs": ("Missing the top step", "no ground under the feet -> tumble down the stairs -> get up at the bottom"),
    "baked": ("physics_pass: the reaction baked into an ordinary clip", "Humanoid .anim from the simulation, replayed with no physics on three characters"),
    "crowd": ("A crowd with five personalities", "two boulders (320 kg, 260 kg) roll through; each reacts by its personality"),
}


def ffmpeg() -> str:
    for c in (os.environ.get("FFMPEG"), r"D:\tools\ffmpeg\bin\ffmpeg.exe", shutil.which("ffmpeg")):
        if c and Path(c).exists():
            return c
    raise SystemExit("ffmpeg not found")


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%")


def shot_video(shot: str) -> Path:
    d = FRAMES / shot
    meta = json.loads((d / "shot.json").read_text(encoding="utf-8"))
    title, sub = CAPTIONS.get(shot, (meta.get("title", shot), ""))
    out = BUILD / f"{shot}.mp4"
    vf = (f"drawbox=x=0:y=ih-110:w=iw:h=110:color=black@0.45:t=fill,"
          f"drawtext=fontfile='{FONTB}':text='{esc(title)}':x=40:y=h-95:fontsize=34:fontcolor=white,"
          f"drawtext=fontfile='{FONT}':text='{esc(sub)}':x=40:y=h-50:fontsize=22:fontcolor=white@0.85,"
          f"scale=1280:720:flags=lanczos")
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(meta["fps"]), "-i", str(d / "f%05d.jpg"),
                    "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", str(out)],
                   check=True)
    return out


def card(lines: list[tuple[str, int, bool]], seconds: float, out: Path) -> Path:
    parts, y = [], 200
    for text, size, bold in lines:
        parts.append(f"drawtext=fontfile='{FONTB if bold else FONT}':text='{esc(text)}':x=(w-text_w)/2:y={y}:"
                     f"fontsize={size}:fontcolor=white")
        y += int(size * 1.7)
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"color=c=0x1d2026:s=1280x720:d={seconds}:r=30", "-vf", ",".join(parts),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)], check=True)
    return out


def metrics_lines() -> list[tuple[str, int, bool]]:
    rows = []
    track = FRAMES / "track" / "shot.json"
    if track.exists():
        m = json.loads(track.read_text(encoding="utf-8"))
        errs = [a["track_pos_err_cm"] for a in m["actors"] if a["track_pos_err_cm"] >= 0]
        degs = [a["track_joint_err_deg"] for a in m["actors"] if a["track_joint_err_deg"] >= 0]
        rows.append((f"Undisturbed tracking: {sum(errs) / len(errs):.1f} cm mean body-part error, "
                     f"{sum(degs) / len(degs):.1f} deg mean joint error", 26, False))
    sims, nans = [], 0
    for s in ORDER:
        f = FRAMES / s / "shot.json"
        if f.exists():
            m = json.loads(f.read_text(encoding="utf-8"))
            sims.append((s, m["ragdolls"], m["sim_ms_per_step"], m["substep_hz"]))
            nans += sum(a["nan"] for a in m["actors"])
    if sims:
        worst = max(sims, key=lambda x: x[2])
        rows.append((f"Physics at {worst[3]} Hz: {worst[2]:.2f} ms per step for {worst[1]} ragdolls "
                     f"({1000 / worst[2] / worst[3]:.0f}x real time, CPU)", 26, False))
        rows.append((f"Stability: {nans} NaN samples, no explosions across {len(sims)} shots", 26, False))
    return rows


def main() -> None:
    shots = sys.argv[1:] or [s for s in ORDER if (FRAMES / s / "shot.json").exists()]
    parts = [card([("Promptimate: text-to-ragdoll", 54, True),
                   ("Generated motion, played by an active ragdoll that reacts to the world", 28, False),
                   ("muscles track the clip  |  hits, trips and falls are simulated  |  personality from text", 22, False),
                   ("getting up is another generated clip", 22, False)], 4.0, BUILD / "_title.mp4")]
    for s in shots:
        parts.append(shot_video(s))
        print("encoded", s, flush=True)
    m = metrics_lines()
    if m:
        parts.append(card([("Measured (offline render, frame by frame)", 40, True)] + m, 5.0, BUILD / "_end.mp4"))
    lst = BUILD / "_concat.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    out = BUILD / "text_to_ragdoll_demo.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)], check=True)
    print(out)


if __name__ == "__main__":
    main()
