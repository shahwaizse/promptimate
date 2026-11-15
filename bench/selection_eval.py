"""Offline: compare take pickers (physics-only v1 vs selection.py) on stored takes of server_eval runs, scored with the
benchmark's hand-written expectations, plus the takes judges named as correct. Usage: selection_eval.py RUN [RUN ...]"""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server")); sys.path.insert(0, str(ROOT / "bench"))
import metrics, motion, selection
from take_selection_eval import phys
# (id, seed) -> takes a judge called correct (from judged_r2_part*.json notes)
JUDGE_OK = {("punch", 0): {"take1"}, ("sword_swing", 0): {"take1"}, ("phone_call", 0): {"take0", "take2"},
            ("crouch", 0): {"take0", "take1"}, ("seq_sit_stand", 0): {"take2"}, ("dance", 0): {"take0"}}
suite = {p["id"]: p for p in json.loads((ROOT / "bench" / "prompts.json").read_text())["prompts"]}
old, new, best, judge_old, judge_new = [], [], [], [], []
for run in sys.argv[1:]:
    for r in json.loads((ROOT / "bench" / "results" / f"server_{run}.json").read_text())["rows"]:
        p = suite[r["id"]]; segs = [(s["prompt"], round(s["seconds"] * motion.FPS)) for s in p["segments"]]
        frames = [f for _, f in segs]; text = " | ".join(s for s, _ in segs)
        dirs = sorted(t for t in Path(r["dir"]).glob("take*") if t.is_dir())
        if len(dirs) < 2: continue
        takes = []
        for t in dirs:
            pos = motion.fk(*motion.load(t)); chk = motion.checks(pos, text)
            bench = metrics.compute(pos=pos, expect=p.get("expect"), segment_expect=p.get("segment_expect"), segment_frames=frames).get("expectation_score", 1.0)
            takes.append({"name": t.name, "pos": pos, "checks": chk, "bench": bench, "phys": phys(metrics.compute(pos=pos), chk)})
        selection.score_takes(takes, segs, text)
        a = min(takes, key=lambda x: x["phys"]); b = min(takes, key=lambda x: x["score"])
        old.append(a["bench"]); new.append(b["bench"]); best.append(max(t["bench"] for t in takes))
        k = (r["id"], r["seed"])
        if k in JUDGE_OK:
            judge_old.append(a["name"] in JUDGE_OK[k]); judge_new.append(b["name"] in JUDGE_OK[k])
            print(f"  judge case {k}: v1 picks {a['name']}, new picks {b['name']} {b['score_parts']} (correct: {sorted(JUDGE_OK[k])})")
print(f"clips {len(old)}  v1 pick {np.mean(old):.4f}  new pick {np.mean(new):.4f}  best possible {np.mean(best):.4f}")
print(f"judge-named correct takes: v1 {sum(judge_old)}/{len(judge_old)}  new {sum(judge_new)}/{len(judge_new)}")
