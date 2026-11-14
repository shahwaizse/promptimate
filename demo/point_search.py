"""Find a take that actually POINTS. Generates prompt x seed variants and scores each with a geometric test:
an arm counts as pointing when it is nearly straight, the hand is in front of the body and at about shoulder height."""
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
import motion  # noqa: E402
from kimodo_worker import KimodoWorker, Segment  # noqa: E402

PROMPTS = [
    "a person points forward with their right arm fully extended and shouts",
    "a person points at something in the distance with an outstretched right arm",
    "a person stands and points straight ahead with their right arm, then points again",
    "a person shouts and points forward with a straight arm, waving the other arm",
]
SEEDS = [1, 2, 3]
SECONDS = 6
OUT = ROOT / "output" / "point_search"

# SOMA indices: (shoulder, elbow, hand) for right and left arms
ARMS = {"right": (17, 18, 19), "left": (11, 12, 13)}


def point_score(pos: np.ndarray) -> dict:
    up = np.array([0.0, 1.0, 0.0])
    left = pos[:, 22] - pos[:, 26]; left[:, 1] = 0
    fwd = np.cross(left, up); fwd /= np.linalg.norm(fwd, axis=1, keepdims=True) + 1e-9
    best = {}
    for side, (s, e, h) in ARMS.items():
        upper = np.linalg.norm(pos[:, e] - pos[:, s], axis=1); lower = np.linalg.norm(pos[:, h] - pos[:, e], axis=1)
        reach = np.linalg.norm(pos[:, h] - pos[:, s], axis=1) / (upper + lower)          # 1 = perfectly straight
        v = pos[:, h] - pos[:, s]
        forward = np.einsum("fi,fi->f", v, fwd)                                           # metres in front of shoulder
        height = pos[:, h, 1] - pos[:, s, 1]                                             # hand relative to shoulder
        ok = (reach > 0.88) & (forward > 0.35) & (np.abs(height) < 0.20)
        best[side] = {"frac": float(ok.mean()), "max_forward": float(forward.max()), "max_reach": float(reach.max())}
    side = max(best, key=lambda k: best[k]["frac"])
    return {"side": side, **best[side]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    w = KimodoWorker()
    rows = []
    try:
        for pi, prompt in enumerate(PROMPTS):
            for seed in SEEDS:
                d = OUT / f"p{pi}_s{seed}"
                w.generate([Segment(prompt, SECONDS * 30)], d, steps=30, seed=seed)
                root, rot = motion.load(d)
                pos = motion.fk(root, rot)
                sc = point_score(pos)
                motion.render_preview(pos, d / "preview.png", f"{prompt} (seed {seed})")
                rows.append({"dir": str(d), "prompt": prompt, "seed": seed, **sc})
                print(f"p{pi} s{seed}: pointing {sc['frac']*100:.0f}% of frames ({sc['side']}), forward {sc['max_forward']:.2f} m, reach {sc['max_reach']:.2f}", flush=True)
    finally:
        w.stop()
    rows.sort(key=lambda r: -r["frac"])
    (OUT / "ranking.json").write_text(json.dumps(rows, indent=2))
    # also score the ORIGINAL (broken) clip for reference
    orig = sorted((ROOT / "output").glob("point_shout_2026*"))[-1]
    r0, q0 = motion.load(orig)
    print("original point_shout:", point_score(motion.fk(r0, q0)))


if __name__ == "__main__":
    main()
