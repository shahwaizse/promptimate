"""Which wording does the model follow best? For a failing action, generate several phrasings (3 seeds each, single
take, no post-processing) and score them with that action's expectations. Uses the shared daemon (cached).

Usage: .venv\\Scripts\\python bench\\prompt_variants.py [--only sprint,punch]
Writes bench/results/prompt_variants.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
import metrics  # noqa: E402
import motion  # noqa: E402
from kimodo_worker import Segment  # noqa: E402
from motiond import RemoteWorker  # noqa: E402

VARIANTS = {
    "sprint": ({"mean_speed_min": 4.0, "airborne_frames_min": 6}, 4, [
        "a person sprints forward", "a person runs forward very fast", "a person sprints forward at full speed",
        "a person runs as fast as they can", "a person dashes forward"]),
    "run": ({"mean_speed_min": 3.0, "airborne_frames_min": 6}, 5, [
        "a person runs forward fast", "a person runs forward", "a person is running forward quickly",
        "a person runs forward with long strides", "a person jogs forward quickly"]),
    "punch": ({"right_arm_extended_frac": 0.05, "travel_max": 1.0}, 3, [
        "a person throws a punch with their right fist", "a person punches forward with their right hand",
        "a person punches straight ahead with their right arm", "a person throws a right jab",
        "a person boxes and throws a punch with their right arm"]),
    "phone_call": ({"hand_near_head_frac": 0.4, "travel_max": 1.0}, 5, [
        "a person holds a phone to their ear and talks", "a person talks on the phone",
        "a person holds their right hand to their ear as if on a phone call",
        "a person answers a phone call and holds it to their right ear", "a person makes a phone call"]),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--seeds", default="0,1,2")
    args = ap.parse_args()
    w = RemoteWorker()
    seeds = [int(s) for s in args.seeds.split(",")]
    out = {}
    for action, (expect, secs, prompts) in VARIANTS.items():
        if args.only and action not in args.only.split(","):
            continue
        out[action] = {}
        for prompt in prompts:
            scores, extra = [], []
            for seed in seeds:
                d = ROOT / "bench" / "results" / "variants" / action / f"{abs(hash(prompt)) % 10**8}_s{seed}"
                w.generate([Segment(prompt, int(secs * motion.FPS))], d, steps=30, seed=seed)
                m = metrics.compute(*motion.load(d), expect=expect)
                scores.append(m["expectation_score"])
                extra.append({k: m.get(k) for k in ("root_mean_speed_ms", "airborne_frames", "root_travel_m")})
            out[action][prompt] = {"mean": round(float(np.mean(scores)), 3), "scores": scores,
                                   "speed": round(float(np.mean([e["root_mean_speed_ms"] for e in extra])), 2),
                                   "airborne": round(float(np.mean([e["airborne_frames"] for e in extra])), 1)}
            print(f"{action:10} {out[action][prompt]['mean']:.3f}  speed={out[action][prompt]['speed']:5}  "
                  f"air={out[action][prompt]['airborne']:5}  {prompt}", flush=True)
    (ROOT / "bench" / "results" / "prompt_variants.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
