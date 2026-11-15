"""A/B the stock and Promptimate-patched kimodo.cpp engines: per-clip latency and output equivalence.

Usage: .venv\\Scripts\\python bench\\engine_ab.py [--steps 30] [--reps 3]
Writes bench/results/engine_ab.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
import motion  # noqa: E402
from kimodo_worker import KimodoWorker, Segment  # noqa: E402

ENGINES = {
    "stock": ROOT / "third_party" / "kimodo.cpp" / "build" / "release",
    "patched": ROOT / "third_party" / "kimodo.cpp" / "build" / "promptimate",
}
PROMPTS = [
    [Segment("a person walks forward and waves with their right hand", 150)],
    [Segment("a person jumps up and down", 120)],
    [Segment("a person walks forward", 90), Segment("a person stops and looks around", 90)],
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--reps", type=int, default=2)
    args = ap.parse_args()
    out = ROOT / "bench" / "results" / "engine_ab"
    res: dict = {"steps": args.steps, "engines": {}}
    for name, d in ENGINES.items():
        w = KimodoWorker(engine_dir=d)
        t0 = time.time()
        w.generate([Segment("a person stands still", 30)], out / name / "_warm", steps=1, seed=0)
        cold = time.time() - t0
        times = []
        for rep in range(args.reps):
            for i, segs in enumerate(PROMPTS):
                info = w.generate(segs, out / name / f"p{i}", steps=args.steps, seed=rep)
                times.append({"prompt": i, "frames": sum(s.frames for s in segs), "seconds": info["seconds"]})
        w.stop()
        res["engines"][name] = {"cold_s": round(cold, 1), "runs": times,
                                "mean_s": round(float(np.mean([t["seconds"] for t in times])), 2)}
        print(name, res["engines"][name]["mean_s"], flush=True)
    # equivalence (last rep's seed for each prompt)
    diffs = []
    for i in range(len(PROMPTS)):
        a = motion.load(out / "stock" / f"p{i}")
        b = motion.load(out / "patched" / f"p{i}")
        pa, pb = motion.fk(*a), motion.fk(*b)
        diffs.append(round(float(np.abs(pa - pb).max()), 6))
    res["max_joint_pos_diff_m"] = diffs
    res["speedup"] = round(res["engines"]["stock"]["mean_s"] / res["engines"]["patched"]["mean_s"], 3)
    (ROOT / "bench" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "bench" / "results" / "engine_ab.json").write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items() if k != "engines"}, indent=2))


if __name__ == "__main__":
    main()
