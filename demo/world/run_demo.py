"""Text-to-world demo: four very different rooms from one-line descriptions, the detective office relit three ways
from text, and (with --shot) a Promptimate character acting in the office.

    .venv\\Scripts\\python demo\\world\\run_demo.py [--only office,living,...] [--no-relight] [--shot MOTION]

One WorldLab Unity session (under scripts/heavy_lock.py) renders everything, then Unity is closed.
Expanded specs are written to demo/world/specs/ (what Claude would write); renders to demo/world/build/.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server"))
import world  # noqa: E402

ROOMS = {
    "office": "a cramped 1970s detective office at night, rain on the window, a desk lamp, cigarette smoke, venetian blinds",
    "living": "a cozy Scandinavian living room on a winter morning, snow outside, a fireplace and candles",
    "subway": "an abandoned subway platform at night",
    "workshop": "a dusty abandoned workshop at golden hour, light pouring through the high window",
}
RELIGHT = {"day": {"time": "afternoon", "weather": "clear", "mood": "noir", "practicals": {"all": False}},
           "night": {"time": "night", "weather": "rain", "mood": "noir"},
           "storm": {"time": "evening", "weather": "storm", "mood": "tense"}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--no-relight", action="store_true")
    ap.add_argument("--shot", default="", help="motion name (generate_motion result) to stage in the office")
    a = ap.parse_args()
    only = {x for x in a.only.split(",") if x}
    specs = ROOT / "demo" / "world" / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    summary = {}
    t0 = time.time()
    with world.session("world: demo renders"):
        for key, text in ROOMS.items():
            if only and key not in only:
                continue
            spec = world.expand(text, seed=1)
            spec["name"] = key
            (specs / f"{key}.json").write_text(json.dumps(spec, indent=1))
            res = world.build_world(spec)
            summary[key] = {k: res.get(k) for k in ("world_id", "stills", "mp4", "sheet", "validation", "timing_s", "solve_s", "unplaced", "notes", "seconds_total")}
            summary[key]["lighting"] = {k: res["lighting"][k] for k in ("time", "weather", "mood", "ev100", "white_balance_k", "meter_lux", "hdri")}
            print(key, res["world_id"], "ok" if res["validation"]["ok"] else res["validation"]["issues"], f"{res['seconds_total']}s", flush=True)
            if key == "office" and not a.no_relight:
                for lk, lt in RELIGHT.items():
                    r2 = world.light_world(res["world_id"], lt, name=f"office_{lk}")
                    summary[f"office_{lk}"] = {k: r2.get(k) for k in ("world_id", "stills", "mp4", "sheet", "validation", "timing_s")}
                    summary[f"office_{lk}"]["lighting"] = {k: r2["lighting"][k] for k in ("time", "weather", "mood", "ev100", "white_balance_k", "meter_lux", "hdri")}
                    print(f"office_{lk}", r2["world_id"], "ok" if r2["validation"]["ok"] else r2["validation"]["issues"], flush=True)
        if a.shot and "office" in summary:
            # A Promptimate character in the generated office: walks in through the door, sits at the desk, picks up the phone.
            wid = summary["office"]["world_id"]
            info = world.describe(wid)
            door = next(o for o in info["openings"] if o["type"] == "door")
            shot = {"name": "office_walk_sit_phone", "aspect": "16:9", "seconds": 10.1, "quality": "final",
                    "actors": [{"id": "det", "cast": "man_suit", "motion": a.shot, "at": [door["inside"][0] - 0.04, door["inside"][1] - 0.36], "yaw": 0,
                                "sit": [{"on": "desk_chair", "t": [5.6, 10.1]}], "auto_seat": False}],
                    "camera": {"preset": "explicit", "pos": [-1.45, 1.6, -1.15], "look_at": [0.45, 0.95, 0.35], "end_pos": [-1.2, 1.5, -0.8], "end_look_at": [0.1, 1.0, 0.9], "fov": 50}}
            r = world.render_world_shot(wid, shot)
            summary["office_shot"] = r
            print("shot", r["mp4"], r["validation"].get("ok"), flush=True)
    summary["seconds_total"] = round(time.time() - t0, 1)
    out = world.BUILD / "demo_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=1))
    print("summary:", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
