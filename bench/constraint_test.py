"""Check that engine constraints steer the motion: hold-still, root path, loop (end pose = start pose).
Writes bench/results/constraint_test.json and renders comparison GIFs if mcp_server/render.py exists."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
import constraints as C  # noqa: E402
import motion  # noqa: E402
from kimodo_worker import KimodoWorker, Segment  # noqa: E402

OUT = ROOT / "bench" / "results" / "constraints"
ENGINE = ROOT / "third_party" / "kimodo.cpp" / "build" / "promptimate"


def root_speed_tail(pos, frames):
    xz = pos[-frames:, 0, [0, 2]]
    return float(np.linalg.norm(np.diff(xz, axis=0), axis=1).sum() / (frames / motion.FPS))


def main() -> None:
    w = KimodoWorker(engine_dir=ENGINE)
    res = {}
    seeds = [0, 1, 2]
    # 1. walks then stops: constrain stop (hold still for last 2 s at wherever the root is at 3 s in a free take)
    prompt = "a person walks forward then stops and stands still"
    F = 150
    for seed in seeds:
        free = OUT / f"stop_free_s{seed}"
        w.generate([Segment(prompt, F)], free, steps=30, seed=seed)
        pf = motion.fk(*motion.load(free))
        x, z = pf[90, 0, 0], pf[90, 0, 2]
        c = C.Constraints(F).hold_still(90, F - 1, float(x), float(z))
        cdir = OUT / f"stop_con_s{seed}"
        w.generate([Segment(prompt, F)], cdir, steps=30, seed=seed, constraints=c.save(cdir / "c.bin"))
        pc = motion.fk(*motion.load(cdir))
        res[f"stop_s{seed}"] = {"free_tail_speed_mps": round(root_speed_tail(pf, 60), 3),
                                "constrained_tail_speed_mps": round(root_speed_tail(pc, 60), 3),
                                "constrained_end_err_m": round(float(np.hypot(pc[-1, 0, 0] - x, pc[-1, 0, 2] - z)), 3)}
    # 2. root path: walk an L (forward 2 m then right... in Kimodo +X is the character's left)
    prompt = "a person walks forward and turns"
    c = C.Constraints(F).root_path([(0, 0, 0), (2.5, 0, 2.0), (5.0, -2.0, 2.0)])
    for seed in seeds[:2]:
        d = OUT / f"path_s{seed}"
        w.generate([Segment(prompt, F)], d, steps=30, seed=seed, constraints=c.save(d / "c.bin"))
        p = motion.fk(*motion.load(d))
        tgt = c.observed[:, [0, 2]]
        err = np.linalg.norm(p[:, 0, [0, 2]] - tgt, axis=1)
        res[f"path_s{seed}"] = {"mean_err_m": round(float(err.mean()), 3), "max_err_m": round(float(err.max()), 3)}
    # 3. loop: pass 1 free, pass 2 pins first and last frame to pass-1 frame 0 pose (last frame shifted by travel)
    prompt = "a person walks forward"
    F = 60
    for seed in seeds[:2]:
        a = OUT / f"loop_free_s{seed}"
        w.generate([Segment(prompt, F)], a, steps=30, seed=seed)
        ra, qa = motion.load(a)
        feat = C.features(ra, qa)
        travel = ra[-1] - ra[0]
        end = feat[0].copy()
        end[0] += travel[0]; end[2] += travel[2]
        c = C.Constraints(F).pose(0, feat[0]).pose(F - 1, end)
        b = OUT / f"loop_con_s{seed}"
        w.generate([Segment(prompt, F)], b, steps=30, seed=seed, constraints=c.save(b / "c.bin"))

        def seam(r, q):
            p = motion.fk(r, q)
            p = p - p[:, :1] * np.array([1, 0, 1])  # hips-relative xz
            return float(np.abs(p[-1] - p[0]).max())
        res[f"loop_s{seed}"] = {"free_seam_m": round(seam(ra, qa), 3), "constrained_seam_m": round(seam(*motion.load(b)), 3)}
    w.stop()
    (ROOT / "bench" / "results" / "constraint_test.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
