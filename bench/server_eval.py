"""End-to-end evaluation through the MCP server code path (server.generate_motion), scored with the benchmark's
expectations. Compares server options, e.g. auto_stop on/off, takes=1 vs 3, clean on/off.

Usage: .venv\\Scripts\\python bench\\server_eval.py --name autostop --prompts walk_stop,seq_walk_stop_wave \\
         --seeds 0,1,2 --opt auto_stop=true --opt takes=1
Writes bench/results/server_<name>.json (per-clip metrics + summary).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("UNITY_PROJECT", str(ROOT / ".cache" / "no_unity_project"))  # don't touch the sandbox
sys.path.insert(0, str(ROOT / "mcp_server"))
import metrics  # noqa: E402
import motion  # noqa: E402
import server  # noqa: E402


def parse_opt(kv: str):
    k, v = kv.split("=", 1)
    if v.lower() in ("true", "false"):
        return k, v.lower() == "true"
    try:
        return k, int(v)
    except ValueError:
        try:
            return k, float(v)
        except ValueError:
            return k, v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--tier", default=None, choices=["smoke", "smoke2", "standard", "full"])
    ap.add_argument("--prompts", default=None)
    ap.add_argument("--seeds", default=None)
    ap.add_argument("--opt", action="append", default=[])
    ap.add_argument("--rescore", action="store_true",
                    help="no generation: recompute metrics for the clips of an existing run --name (after metric changes)")
    args = ap.parse_args()
    if args.rescore:
        return rescore(args.name)
    suite = json.loads((ROOT / "bench" / "prompts.json").read_text())
    suite = suite["prompts"] if isinstance(suite, dict) else suite
    sys.path.insert(0, str(ROOT / "bench"))
    import tiers
    keep, seeds = tiers.resolve(args.tier or ("full" if not (args.prompts or args.seeds) else None),
                                args.prompts, args.seeds)
    if keep:
        suite = [p for p in suite if p["id"] in keep]
    opts = dict(parse_opt(o) for o in args.opt)
    opts.setdefault("unity_check", "off")
    rows = []
    for p in suite:
        for seed in seeds:
            segs = [server.MotionSegment(prompt=s["prompt"], seconds=s["seconds"]) for s in p["segments"]]
            t0 = time.time()
            out = server.generate_motion(segs, name=f"eval_{args.name}_{p['id']}", seed=seed * 10, **opts)
            wall = time.time() - t0
            meta = json.loads(out[0])
            d = Path(meta["files"]["raw_dir"])
            root, rot = motion.load(d)
            seg_frames = [s["frames"] for s in meta["segments"]]
            m = metrics.compute(root, rot, expect=p.get("expect"),
                                segment_expect=p.get("segment_expect"),
                                segment_frames=seg_frames)
            rows.append({"id": p["id"], "seed": seed, "wall_s": round(wall, 2), "dir": str(d),
                         "auto_holds_s": meta["generation"].get("auto_holds_s"), "metrics": m})
            print(f"{p['id']:22} s{seed} wall={wall:5.1f}s exp={m.get('expectation_score')} "
                  f"skate={m['skate_speed_cms']} end_speed={m['root_end_speed_ms']}", flush=True)
    write(args.name, opts, rows)
    server.worker.stop()


def rescore(name: str) -> None:
    path = ROOT / "bench" / "results" / f"server_{name}.json"
    res = json.loads(path.read_text())
    suite = {p["id"]: p for p in json.loads((ROOT / "bench" / "prompts.json").read_text())["prompts"]}
    for r in res["rows"]:
        p, d = suite[r["id"]], Path(r["dir"])
        root, rot = motion.load(d)
        frames = [round(s["seconds"] * motion.FPS) for s in p["segments"]]
        r["metrics"] = metrics.compute(root, rot, expect=p.get("expect"), segment_expect=p.get("segment_expect"),
                                       segment_frames=frames)
    write(name, res["opts"], res["rows"])


def write(name: str, opts: dict, rows: list) -> None:
    keys = ["expectation_score", "expectation_pass_rate", "skate_speed_cms", "jerk_mean", "pop_frames",
            "root_end_speed_ms"]
    summary = {k: round(float(np.mean([r["metrics"].get(k, np.nan) for r in rows])), 4) for k in keys}
    summary["wall_s_mean"] = round(float(np.mean([r["wall_s"] for r in rows])), 2)
    by_prompt = {pid: round(float(np.mean([r["metrics"].get("expectation_score", np.nan)
                                           for r in rows if r["id"] == pid])), 3)
                 for pid in dict.fromkeys(r["id"] for r in rows)}
    res = {"name": name, "opts": opts, "summary": summary, "by_prompt": by_prompt, "rows": rows}
    (ROOT / "bench" / "results" / f"server_{name}.json").write_text(json.dumps(res, indent=2))
    print(json.dumps({"summary": summary, "by_prompt": by_prompt}, indent=2))


if __name__ == "__main__":
    main()
