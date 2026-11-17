"""Average the blind verdicts of a judging round: python bench/shorts_judge_tally.py OUT_DIR"""
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
key = json.loads((out / "key.json").read_text())
V = [json.loads(p.read_text()) for p in sorted(out.glob("verdict_*.json"))]
cats = ["hook", "story", "acting", "camera", "polish", "overall"]
rows = []
for x, name in key.items():
    have = [v for v in V if x in v["scores"]]
    avg = {c: sum(float(v["scores"][x][c]) for v in have) / max(len(have), 1) for c in cats}
    rows.append((avg["overall"], name, avg, [v["ranking"].index(x) + 1 for v in have if x in v["ranking"]]))
print(f"{len(V)} judges")
for o, name, avg, ranks in sorted(rows, reverse=True):
    print(f"{name:26s} " + " ".join(f"{c[:5]} {avg[c]:.1f}" for c in cats) + f"  ranks {ranks}")
if "--notes" in sys.argv:
    for x, name in key.items():
        if name.startswith("OURS"):
            print(name, "| worst:", " / ".join(v["scores"][x]["worst"][:200] for v in V if x in v["scores"]))
