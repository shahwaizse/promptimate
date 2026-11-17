"""Pre-generate the motion library: every in-place action of demo/episodes/story.py ACTIONS, exactly as roblox_perform
requests it (library mode: from and back to the shared idle, snapped length, attempt seeds), so a fresh episode's
in-place beats are generation-cache hits.

    .venv\\Scripts\\python scripts\\build_motion_library.py [--attempts 2]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "mcp_server"), str(ROOT / "demo" / "episodes")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=2, help="seeds per action (perform tries attempt 0, then 1, ...)")
    a = ap.parse_args()
    os.environ.setdefault("PROMPTIMATE_RBX_TAKES", "1")
    os.environ.setdefault("PROMPTIMATE_SKIP_PREVIEW", "1")
    import server as SRV
    import roblox_tools as RT
    import story_compile as story
    jobs = [(p, s, att) for k, (p, s) in story.ACTIONS.items() if k not in story.MOVES for att in range(a.attempts)]
    SRV.worker.prefetch([p for p, _s, _a in jobs])
    t0 = time.time()

    def one(j):
        prompt, secs, att = j
        t = time.time()
        segs = [SRV.MotionSegment(prompt=prompt, seconds=max(1.0, round(secs * 2) / 2))]
        SRV.generate_motion(segs, name=f"lib_{abs(hash(prompt)) % 10**6}_{att}",
                            takes=int(os.environ["PROMPTIMATE_RBX_TAKES"]), seed=att * 101, unity_check="off",
                            start_pose="idle", end_pose="idle",
                            **({"in_place": True} if RT._STILL.search(prompt) and not RT._LOCO.search(prompt) else {}))
        return time.time() - t
    with ThreadPoolExecutor(int(os.environ.get("MOTIOND_ENGINES", "2"))) as ex:
        ts = list(ex.map(one, jobs))
    print(f"library: {len(jobs)} clips in {time.time() - t0:.1f}s ({sum(t < 0.5 for t in ts)} were already cached)")


if __name__ == "__main__":
    main()
