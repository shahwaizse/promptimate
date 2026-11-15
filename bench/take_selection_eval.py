"""Offline: does intent-aware take selection pick better takes than the physics-only score? Re-ranks the 3 stored
takes of each clip in server_eval runs and scores the pick with the benchmark's hand-written expectations.

Usage: .venv\\Scripts\\python bench\\take_selection_eval.py RUN [RUN ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
import intent  # noqa: E402
import metrics  # noqa: E402
import motion  # noqa: E402

PHYS_W = {"pop_frames": 2.0, "skate_speed_cms": 0.15, "float_ratio": 5.0, "jerk_p95": 0.004, "penetration_max_cm": 0.5}


def phys(m: dict, chk: dict) -> float:
    return 10.0 * len(chk["failures"]) + sum(w * m.get(k, 0) for k, w in PHYS_W.items())


def intent_penalty(pos, segs) -> float:
    e, se = intent.expectations([(p, f / motion.FPS) for p, f in segs])
    frames = [f for _, f in segs]
    m = metrics.compute(pos=pos, expect=e, segment_expect=se or None, segment_frames=frames)
    vals = [v for k, v in m.items() if k.startswith("exp_")]
    return 12.0 * float(np.sum(1.0 - np.array(vals))) if vals else 0.0


def main() -> None:
    suite = {p["id"]: p for p in json.loads((ROOT / "bench" / "prompts.json").read_text())["prompts"]}
    old_scores, new_scores, oracle, changed = [], [], [], []
    for run in sys.argv[1:]:
        for r in json.loads((ROOT / "bench" / "results" / f"server_{run}.json").read_text())["rows"]:
            p = suite[r["id"]]
            segs = [(s["prompt"], round(s["seconds"] * motion.FPS)) for s in p["segments"]]
            frames = [f for _, f in segs]
            takes = sorted(t for t in Path(r["dir"]).glob("take*") if t.is_dir())
            if len(takes) < 2:
                continue
            rows = []
            for t in takes:
                pos = motion.fk(*motion.load(t))
                chk = motion.checks(pos, " | ".join(s for s, _ in segs))
                m = metrics.compute(pos=pos)
                bench = metrics.compute(pos=pos, expect=p.get("expect"), segment_expect=p.get("segment_expect"),
                                        segment_frames=frames).get("expectation_score", 1.0)
                rows.append((phys(m, chk), phys(m, chk) + intent_penalty(pos, segs), bench, t.name))
            a, b = min(rows, key=lambda x: x[0]), min(rows, key=lambda x: x[1])
            old_scores.append(a[2]); new_scores.append(b[2]); oracle.append(max(x[2] for x in rows))
            if a[3] != b[3]:
                changed.append((r["id"], r["seed"], a[3], round(a[2], 2), b[3], round(b[2], 2)))
    print(f"clips {len(old_scores)}  physics-only pick {np.mean(old_scores):.4f}  intent-aware pick "
          f"{np.mean(new_scores):.4f}  best possible {np.mean(oracle):.4f}")
    for c in changed:
        print("  changed:", c)


if __name__ == "__main__":
    main()
