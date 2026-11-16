"""Produce several episodes back to back, each followed by a QA contact sheet (one frame every 1.2 s), so the machine
never idles while drafts are reviewed.
    .venv\\Scripts\\python demo\\episodes\\queue.py thousand_words hug_swap [--suffix _v1] [--from perform]
Writes build/<episode>/<episode><suffix>.mp4 and build/<episode>/qa<suffix>.jpg; a summary line per episode goes to
build/queue.log."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="+")
    ap.add_argument("--suffix", default="")
    ap.add_argument("--from", dest="start", default="cast")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT / "mcp_server"))
    import roblox_record as RR
    ff = RR._ffmpeg()
    qlog = HERE / "build" / "queue.log"
    for ep in a.episodes:
        t = time.time()
        log = HERE / "build" / ep / f"produce{a.suffix}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "w", encoding="utf-8") as fh:
            r = subprocess.run([str(PY), "-u", str(HERE / "produce.py"), ep, "--from", a.start, "--suffix", a.suffix],
                               stdout=fh, stderr=subprocess.STDOUT, cwd=str(ROOT))
        mp4 = HERE / "build" / ep / f"{ep}{a.suffix}.mp4"
        line = f"{time.strftime('%H:%M:%S')} {ep}: exit {r.returncode} in {time.time() - t:.0f}s"
        if r.returncode == 0 and mp4.exists():
            qa = HERE / "build" / ep / f"qa{a.suffix}.jpg"
            subprocess.run([ff, "-loglevel", "error", "-y", "-i", str(mp4), "-vf", "fps=1/1.2,scale=180:320,tile=10x7",
                            "-frames:v", "1", str(qa)])
            line += f" -> {mp4} (qa {qa})"
        with open(qlog, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        print(line, flush=True)


if __name__ == "__main__":
    main()
