"""Batch narration with tiny-voca: one model load for every line of an episode (the CLI reloads per line, ~4 s each).
Runs inside the tiny-voca venv:  <venv>\\Scripts\\python tv_batch.py <checkpoint> <jobs.json>
jobs.json = [{"text": ..., "voice": "M2", "speed": 1.2, "out": "...wav", "pitch_range"?: 1.45, "gap"?: 0.05,
              "max_pause"?: 0.12}, ...]
With "gap", every sentence is synthesised on its own, trimmed of the model's edge silence (~0.22 s before each
sentence) and joined with `gap` seconds (x1.5 after ! or ?): narration paced like the reference shorts."""
import json
import os
import sys
from pathlib import Path

import torch
from tiny_voca.infer import FRONTEND_VARIABLE, finished, limit_peak, load_model, match_frontend, sentences, speak_text


def trim(wave, sr, pre=0.03, post=0.06, floor_db=45.0):
    """wave without leading/trailing silence (frames more than floor_db under the loudest), short fades."""
    hop = int(sr * 0.01)
    n = len(wave) // hop
    if n < 3:
        return wave
    e = wave[:n * hop].reshape(n, hop).pow(2).mean(1).add(1e-12).log10().mul(10)
    act = torch.nonzero(e > e.max() - floor_db).flatten()
    if not len(act):
        return wave
    a = max(0, int(act[0]) * hop - int(pre * sr))
    b = min(len(wave), (int(act[-1]) + 1) * hop + int(post * sr))
    w = wave[a:b].clone()
    f = min(int(0.005 * sr), len(w) // 2)
    if f:
        ramp = torch.linspace(0, 1, f)
        w[:f] *= ramp
        w[-f:] *= ramp.flip(0)
    return w


def cap_pauses(wave, sr, max_pause, floor_db=40.0):
    """Internal silences (commas, the model's hesitations) longer than max_pause cut down to max_pause, the way an
    editor tightens a voice-over; the references have ~5 pauses >= 0.1 s per minute, tiny-voca ~30."""
    hop = int(sr * 0.01)
    n = len(wave) // hop
    if n < 3:
        return wave
    e = wave[:n * hop].reshape(n, hop).pow(2).mean(1).add(1e-12).log10().mul(10)
    quiet = (e < e.max() - floor_db).tolist()
    keep, k, f = [], 0, int(0.005 * sr)
    i = 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if i > 0 and j < n and (j - i) * hop > max_pause * sr:      # an internal run, too long
                a = i * hop + int(max_pause * sr / 2)
                b = j * hop - int(max_pause * sr / 2)
                seg = wave[k:a].clone()
                if f and len(seg) > f:
                    seg[-f:] *= torch.linspace(1, 0, f)
                keep.append(seg)
                k = b
            i = j
        else:
            i += 1
    tail = wave[k:].clone()
    if keep and f and len(tail) > f:
        tail[:f] *= torch.linspace(0, 1, f)
    keep.append(tail)
    return torch.cat(keep)


def main():
    ckpt, jobs = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    import soundfile as sf
    if FRONTEND_VARIABLE not in os.environ:
        match_frontend(ckpt)
    model = load_model(ckpt, "cpu")
    sr = model.config.sample_rate
    for j in jobs:
        pr = float(j.get("pitch_range", 1.0))
        if j.get("gap") is None:
            raw, _ = speak_text(model, j["text"], j["voice"], j["speed"], 0.0, pitch_range=pr, peak=None)
        else:
            parts = []
            sents = sentences(finished(j["text"]))
            for k, s in enumerate(sents):
                w, _ = speak_text(model, s, j["voice"], j["speed"], 0.0, seed=k, pitch_range=pr, peak=None)
                w = trim(w, sr)
                if j.get("max_pause"):
                    w = cap_pauses(w, sr, float(j["max_pause"]))
                parts.append(w)
                if k < len(sents) - 1:
                    g = float(j["gap"]) * (1.5 if s.rstrip().rstrip("\"')").endswith(("!", "?")) else 1.0)
                    parts.append(torch.zeros(int(g * sr)))
            raw = torch.cat(parts)
        wave = limit_peak(raw)
        out = Path(j["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(out, wave.numpy(), sr, subtype="FLOAT")
        print("ok", out.name, flush=True)


if __name__ == "__main__":
    main()
