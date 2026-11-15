"""Side-by-side evaluation of a driver (mannequin) video vs the AI motion-transfer output.

  python compare.py TEST_DIR [--a driver.mp4 --b kling.mp4]
Writes TEST_DIR/sheet.png (rows = time samples every 0.5 s, columns = driver | output) and TEST_DIR/side_by_side.gif
(both clips time-aligned from t=0, scaled to the same height). Also prints the two durations and fps.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

FF = r"D:\Tools\ffmpeg\bin\ffmpeg.exe"
FP = r"D:\Tools\ffmpeg\bin\ffprobe.exe"


def probe(p: Path) -> dict:
    out = subprocess.run([FP, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_frames:format=duration", "-of", "json", str(p)],
                         capture_output=True, text=True).stdout
    j = json.loads(out); s = j["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return {"w": s["width"], "h": s["height"], "fps": round(int(n) / int(d), 2), "duration": float(j["format"]["duration"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("test_dir"); ap.add_argument("--a", default="driver.mp4"); ap.add_argument("--b", default="kling.mp4")
    ap.add_argument("--step", type=float, default=0.5); ap.add_argument("--h", type=int, default=320)
    a = ap.parse_args()
    d = Path(a.test_dir); A, B = d / a.a, d / a.b
    pa, pb = probe(A), probe(B)
    print("driver", pa); print("output", pb)
    dur = min(pa["duration"], pb["duration"])
    n = int(dur / a.step)
    H = a.h
    # contact sheet: each clip sampled at the same timestamps, labelled, hstacked per timestamp, tiled
    fa = f"[0]fps=1/{a.step},scale=-2:{H},drawtext=text='driver %{{pts\\:hms}}':x=6:y=6:fontsize=16:fontcolor=black:box=1:boxcolor=white@0.7[a]"
    fb = f"[1]fps=1/{a.step},scale=-2:{H},drawtext=text='output':x=6:y=6:fontsize=16:fontcolor=black:box=1:boxcolor=white@0.7[b]"
    cols = 4
    rows = (n + cols - 1) // cols
    subprocess.run([FF, "-loglevel", "error", "-y", "-i", str(A), "-i", str(B), "-filter_complex",
                    f"{fa};{fb};[a][b]hstack=inputs=2,pad=iw+8:ih+8:4:4:color=white,tile={cols}x{rows}",
                    "-frames:v", "1", "-t", str(dur), str(d / "sheet.png")], check=True)
    # GIF: side by side, 12 fps, 360 px tall, palette for quality
    gh = 360
    flt = (f"[0]scale=-2:{gh},fps=12[a];[1]scale=-2:{gh},fps=12[b];[a][b]hstack=inputs=2,split[x][y];"
           f"[x]palettegen=max_colors=128[p];[y][p]paletteuse=dither=bayer:bayer_scale=4")
    subprocess.run([FF, "-loglevel", "error", "-y", "-t", str(dur), "-i", str(A), "-t", str(dur), "-i", str(B),
                    "-filter_complex", flt, str(d / "side_by_side.gif")], check=True)
    (d / "compare.json").write_text(json.dumps({"driver": pa, "output": pb}, indent=1))
    print("wrote", d / "sheet.png", d / "side_by_side.gif")


if __name__ == "__main__":
    main()
