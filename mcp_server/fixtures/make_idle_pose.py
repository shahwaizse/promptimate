r"""Rebuild idle_pose.json: the canonical neutral standing pose used by generate_motion(start_pose/end_pose="idle").

Source is real model output, not a hand-made pose: "a person stands still" (4 s, seeds 0-5, 30 steps, text_cfg 2)
through the shared daemon, cleaned like any clip (feet on the floor). From the middle 60 % of each clip we take the
frame with the least joint motion, score it for symmetry (feet and hands balanced about the body midline, equal hand
heights) and a hip-width stance, keep the best, and re-base it to the origin facing +Z (Kimodo heading 0, hips x/z = 0).

Run: .venv\Scripts\python mcp_server\fixtures\make_idle_pose.py   (cached in .cache/gen after the first run)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import constraints as C  # noqa: E402
import motion  # noqa: E402
import postprocess  # noqa: E402
from kimodo_worker import Segment  # noqa: E402
from motiond import RemoteWorker  # noqa: E402

PROMPT, SECONDS, SEEDS, STEPS = "a person stands still", 4.0, (0, 1, 2, 3, 4, 5), 30


def main() -> None:
    w = RemoteWorker()
    best = None
    for seed in SEEDS:
        d = motion.ROOT / "output" / "_fixture_idle" / f"s{seed}"
        w.generate([Segment(PROMPT, int(SECONDS * motion.FPS))], d, steps=STEPS, seed=seed)
        root, rot = motion.load(d)
        root, rot, _ = postprocess.clean(root, rot, contacts=postprocess.load_contacts(d))
        pos = motion.fk(root, rot)
        F = len(pos)
        speed = np.linalg.norm(np.diff(pos, axis=0), axis=-1).mean(axis=1) * motion.FPS  # mean joint speed m/s
        for f in range(int(0.2 * F), int(0.8 * F)):
            r1, q1 = C.rebase(root[f:f + 1], rot[f:f + 1], float(root[f, 0]), float(root[f, 2]),
                              float(C.heading_angle(pos[f])))
            p = motion.fk(r1, q1)[0]
            asym = (abs(p[24, 0] + p[28, 0]) + abs(p[13, 0] + p[19, 0]) + abs(p[13, 1] - p[19, 1])
                    + abs(p[24, 2] - p[28, 2]))
            stance = abs(abs(p[24, 0] - p[28, 0]) - 0.30)  # ankles ~30 cm apart (hip width), not a wide stance
            score = speed[f - 1:f + 1].mean() + 2.0 * asym + stance
            if best is None or score < best[0]:
                best = (score, seed, f, r1[0], q1[0], float(speed[f - 1:f + 1].mean()), float(asym))
    score, seed, f, r, q, sp, asym = best
    out = {"source": {"prompt": PROMPT, "seconds": SECONDS, "seed": seed, "steps": STEPS, "frame": f,
                      "joint_speed_ms": round(sp, 4), "asymmetry_m": round(asym, 4)},
           "note": "hips position (x/z = 0) and local joint rotations (xyzw, joint 0 = global hips) of one frame, "
                   "Kimodo space, facing +Z, feet on the floor",
           "root": [round(float(v), 6) for v in r], "rot": [[round(float(v), 6) for v in j] for j in q]}
    (HERE / "idle_pose.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["source"]))


if __name__ == "__main__":
    main()
