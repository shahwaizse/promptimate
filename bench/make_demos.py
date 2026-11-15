"""Generate the new-capability demo clips (loop, in-place, root path) through the server code path.
Writes bench/results/demos/demos.json with output dirs."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("UNITY_PROJECT", str(ROOT / ".cache" / "no_unity_project"))
sys.path.insert(0, str(ROOT / "mcp_server"))
import server  # noqa: E402

S, W = server.MotionSegment, server.Waypoint
DEMOS = {
    "loop_walk": dict(segments=[S(prompt="a person walks forward", seconds=2.0)], loop=True),
    "loop_jog": dict(segments=[S(prompt="a person jogs forward", seconds=1.5)], loop=True),
    "inplace_jog_loop": dict(segments=[S(prompt="a person jogs forward", seconds=1.5)], loop=True, in_place=True),
    "path_square": dict(segments=[S(prompt="a person walks", seconds=8.0)],
                        root_path=[W(t=0, x=0, z=0), W(t=2, x=0, z=2.5), W(t=4, x=-2.5, z=2.5),
                                   W(t=6, x=-2.5, z=0), W(t=8, x=0, z=0)]),
    "path_walk_stop": dict(segments=[S(prompt="a person walks forward and stops", seconds=5.0)],
                           root_path=[W(t=0, x=0, z=0), W(t=3, x=0, z=3), W(t=5, x=0, z=3)]),
}


def main() -> None:
    out = {}
    for name, kw in DEMOS.items():
        meta = json.loads(server.generate_motion(name=f"demo_{name}", unity_check="off", **kw)[0])
        out[name] = {"dir": meta["files"]["raw_dir"], "kimodo": meta["files"].get("kimodo"),
                     "postprocess": meta.get("postprocess"), "generation": meta["generation"],
                     "checks": meta["checks"]["passed"]}
        print(name, meta["generation"].get("total_gen_seconds"), meta["checks"]["passed"], flush=True)
    d = ROOT / "bench" / "results" / "demos"
    d.mkdir(parents=True, exist_ok=True)
    (d / "demos.json").write_text(json.dumps(out, indent=2))
    server.worker.stop()


if __name__ == "__main__":
    main()
