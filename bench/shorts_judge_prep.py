"""Blind judging kit for story shorts: shuffled labels, 1-fps frame sheets, cut lists and whisper transcripts.

    python bench/shorts_judge_prep.py OUT_DIR SEED name=path.mp4 [name=path.mp4 ...]
        -> OUT_DIR/judge/X<n>_sheet_NN.jpg, X<n>_cuts.txt, X<n>_transcript.txt, OUT_DIR/key.json, OUT_DIR/judge_prompt.md
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_server"))
import local_config as LC  # noqa: E402  (also loads local.env: npm_config_cache etc.)
FF = LC.ffmpeg()
PROMPT = r"""You are judging {n} vertical "In this town..." story shorts (narrated Roblox-style animated stories for kids and
teens on TikTok / YouTube Shorts / Reels). Labels X1..X{n} are blind.

For each video in {judge} you have:
- X?_sheet_NN.jpg: one frame per second, 6 across x 4 down per sheet (24 s per sheet), in order.
- X?_cuts.txt: duration and detected camera cut times.
- X?_transcript.txt: the narration (automatic transcript, may contain small errors).
You cannot hear the audio: judge the script from the transcript, do not judge voice/music/sound.

Look at every sheet and read every transcript. Then score each video 1-10 on:
hook (first 3 s), story (premise, escalation, twist, payoff), acting (do characters physically act out what the
narration says, readable poses and faces), camera (shot choice, framing, cutting rhythm, nothing blocking the subject),
visual polish (sets, characters, captions, on-screen text), and overall (would a viewer watch to the end and share it).

Write your result to {out}\verdict_{{N}}.json as:
{{"scores": {{"X1": {{"hook":..,"story":..,"acting":..,"camera":..,"polish":..,"overall":..,"best":"...","worst":"..."}}, ...}},
 "ranking": ["X?", ...best first], "notes": "what separates the top videos from the bottom ones, concretely"}}
Be specific and harsh; do not give everyone similar scores. Reply with just "done".
"""


def main():
    out, seed = Path(sys.argv[1]), int(sys.argv[2])
    vids = dict(a.split("=", 1) for a in sys.argv[3:])
    (out / "judge").mkdir(parents=True, exist_ok=True)
    (out / "tx").mkdir(exist_ok=True)
    names = list(vids)
    random.Random(seed).shuffle(names)
    key = {f"X{i + 1}": n for i, n in enumerate(names)}
    (out / "key.json").write_text(json.dumps(key, indent=1))
    J = out / "judge"
    env = dict(os.environ, PATH=str(Path(FF).parent) + os.pathsep + os.environ.get("PATH", ""))
    for lab, n in key.items():
        src = vids[n]
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", src, "-vf", "fps=1,scale=240:426,tile=6x4", str(J / f"{lab}_sheet_%02d.jpg")], check=True)
        r = subprocess.run([FF, "-i", src, "-vf", "select='gt(scene,0.3)',showinfo", "-f", "null", "-"], capture_output=True, text=True)
        cuts = [round(float(m), 1) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
        dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        (J / f"{lab}_cuts.txt").write_text(f"duration {dur:.1f}s, {len(cuts)} cuts at: " + " ".join(map(str, cuts)))
        wav = out / "tx" / f"{lab}.wav"
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
        subprocess.run(["npx.cmd", "--yes", "hyperframes", "transcribe", str(wav), "-d", str(out / "tx" / lab), "--engine",
                        "whisper", "--json"], capture_output=True, env=env, timeout=900)
        try:
            d = json.loads((out / "tx" / lab / "transcript.json").read_text())
            w = d if isinstance(d, list) else d.get("words", d.get("segments", []))
            txt = " ".join((x.get("text") or x.get("word") or "").strip() for x in w)
        except Exception as e:
            txt = f"(no transcript: {e})"
        (J / f"{lab}_transcript.txt").write_text(txt, encoding="utf-8")
    (out / "judge_prompt.md").write_text(PROMPT.format(n=len(key), judge=str(J), out=str(out)), encoding="utf-8")
    print(json.dumps({"videos": len(key), "out": str(out)}))


if __name__ == "__main__":
    main()
