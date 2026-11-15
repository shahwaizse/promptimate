"""Can the auto-stop 'locate' pass (only used to find where the character stops) run at fewer steps?
Compares hold quality when pass 1 runs at 30 vs N steps (pass 2 always at 30). Uses the shared daemon."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
import constraints as C  # noqa: E402
import metrics  # noqa: E402
import motion  # noqa: E402
from kimodo_worker import Segment  # noqa: E402
from motiond import RemoteWorker  # noqa: E402

sys.path.insert(0, str(ROOT / "mcp_server"))
import server  # noqa: E402  (only for _auto_holds)

CASES = {
    "walk_stop": ([("a person walks forward then stops and stands still", 150)], None,
                  {"ends_stationary": True}),
    "seq_walk_stop_wave": ([("a person walks forward", 90), ("a person stops and stands still", 75),
                            ("a person waves with their right hand", 90)], None, None),
}
OUT = Path("D:/tmp/locate")


def run(w, segs, seed, locate_steps):
    holds = server._auto_holds(segs)
    frames = sum(s.frames for s in segs)
    t0 = time.time()
    d1 = OUT / f"p1_{locate_steps}_{seed}_{len(segs)}"
    w.generate(segs, d1, steps=locate_steps, seed=seed)
    r0, _ = motion.load(d1)
    c = C.Constraints(frames)
    for h0, h1 in holds:
        c.hold_still(h0, h1, float(r0[h0, 0]), float(r0[h0, 2]))
    d2 = OUT / f"p2_{locate_steps}_{seed}_{len(segs)}"
    w.generate(segs, d2, steps=30, seed=seed, constraints=c.save(d2 / "c.bin"))
    dt = time.time() - t0
    root, rot = motion.load(d2)
    m = metrics.compute(root, rot, segment_frames=[s.frames for s in segs])
    return dt, m


def main() -> None:
    w = RemoteWorker(cache=False)
    res = {}
    for name, (segs, _, _) in CASES.items():
        segs = [Segment(p, f) for p, f in segs]
        for steps in (30, 10, 6):
            rows = [run(w, segs, seed, steps) for seed in (0, 1, 2)]
            res[f"{name}@{steps}"] = {
                "seconds": round(float(np.mean([r[0] for r in rows])), 2),
                "end_speed": round(float(np.mean([r[1]["root_end_speed_ms"] for r in rows])), 3),
                "travel": round(float(np.mean([r[1]["root_travel_m"] for r in rows])), 2),
                "jerk_mean": round(float(np.mean([r[1]["jerk_mean"] for r in rows])), 1),
                "pops": round(float(np.mean([r[1]["pop_frames"] for r in rows])), 2)}
            print(f"{name}@{steps}", json.dumps(res[f"{name}@{steps}"]), flush=True)


if __name__ == "__main__":
    main()
