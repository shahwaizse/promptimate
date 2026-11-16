"""Batch narration with tiny-voca: one model load for every line of an episode (the CLI reloads per line, ~4 s each).
Runs inside the tiny-voca venv:  <venv>\\Scripts\\python tv_batch.py <checkpoint> <jobs.json>
jobs.json = [{"text": ..., "voice": "M2", "speed": 1.6, "out": "...wav"}, ...]"""
import json
import os
import sys
from pathlib import Path

from tiny_voca.infer import FRONTEND_VARIABLE, limit_peak, load_model, match_frontend, speak_text


def main():
    ckpt, jobs = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    import soundfile as sf
    if FRONTEND_VARIABLE not in os.environ:
        match_frontend(ckpt)
    model = load_model(ckpt, "cpu")
    for j in jobs:
        raw, _ = speak_text(model, j["text"], j["voice"], j["speed"], 0.0, pitch_range=1.0, peak=None)
        wave = limit_peak(raw)
        out = Path(j["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out, wave.numpy(), model.config.sample_rate, subtype="FLOAT")
        print("ok", out.name, flush=True)


if __name__ == "__main__":
    main()
