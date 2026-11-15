"""Build a judge manifest (prompt, preview sheet, takes sheet, key metrics) for a server_eval run, so a Claude judge
can score prompt adherence and naturalness from the images.

Usage: .venv\\Scripts\\python bench\\judge_packets.py RUN_NAME   ->  bench/results/judge_<RUN_NAME>.json
The rubric lives in RUBRIC below; judges write bench/results/judged_<RUN_NAME>.json with one entry per clip.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "bench" / "results"

RUBRIC = """Score each clip from its preview sheet (front + side stick figures over time, top-down hips path with facing
arrows, hand/hip/head height timeline with foot-contact bars) and, if present, the takes sheet.
For each clip return:
  adherence 1-5: does the motion do what the prompt says (action, body part/side, direction, manner, order of
                 segments)? 5 = clearly and fully, 3 = partly / generic, 1 = wrong action.
  naturalness 1-5: does it look like plausible human motion (balance, timing, no pops, no sliding/floating,
                   no limbs through the body)? 5 = mocap-like.
  issues: short concrete list of what is wrong (e.g. "never leaves the ground", "waves with left hand",
          "keeps walking during the stop", "arm passes through torso").
  cause: for each issue, "model" if it is plausibly beyond what a text-to-motion model of this kind produces from
         this prompt (e.g. object interaction it cannot see), "pipeline" if our processing likely caused it
         (foot locking, loop/stop constraints, seams between segments, grounding), "prompt" if a rewording or a
         targeted constraint would likely fix it, or "unclear".
Be strict and specific; do not reward a clip for being smooth if it ignores the prompt."""


def main() -> None:
    run = sys.argv[1]
    data = json.loads((RESULTS / f"server_{run}.json").read_text())
    suite = json.loads((ROOT / "bench" / "prompts.json").read_text())["prompts"]
    prompts = {p["id"]: p for p in suite}
    items = []
    for r in data["rows"]:
        d = Path(r["dir"])
        m = r["metrics"]
        items.append({
            "id": r["id"], "seed": r["seed"],
            "prompt": " | ".join(f"{s['prompt']} ({s['seconds']} s)" for s in prompts[r["id"]]["segments"]),
            "preview": str(d / "preview.png"),
            "takes": str(d / "takes.png") if (d / "takes.png").exists() else None,
            "auto_checks": {k: m.get(k) for k in ("expectation_score", "skate_speed_cms", "pop_frames",
                                                  "root_travel_m", "heading_change_deg", "hips_min_m", "hips_end_m")},
            "failed_expectations": {k: v for k, v in m.items() if k.startswith("exp_") and v < 0.999},
        })
    out = RESULTS / f"judge_{run}.json"
    out.write_text(json.dumps({"rubric": RUBRIC, "items": items}, indent=2))
    print(out, len(items), "clips")


if __name__ == "__main__":
    main()
