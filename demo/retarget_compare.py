"""Summarises demo/retarget_report_<variant>.json files side by side (worst / mean over characters per clip and Foot IK).
Usage: .venv/Scripts/python demo/retarget_compare.py baseline solefix grounding"""
import json, sys
from collections import defaultdict
vs = sys.argv[1:]
data = {v: json.load(open(f"demo/retarget_report_{v}.json"))["rows"] for v in vs}
metrics = [("skateCms", "skate cm/s (mean)"), ("floatCm", "sole height while planted cm (mean)"),
           ("penCm", "deepest below floor cm (max)"), ("kneeHyperDeg", "knee hyperext deg (max)"), ("pops", "pops (sum)")]
for key, label in metrics:
    print(f"\n== {label}: per clip, Foot IK off | on; each cell = mean over characters [worst]")
    print(f"{'clip':13}" + "".join(f"{v:>34}" for v in vs))
    clips = sorted({r["clip"] for r in data[vs[0]]})
    for c in clips:
        line = f"{c:13}"
        for v in vs:
            cell = []
            for ik in (False, True):
                xs = [r[key] for r in data[v] if r["clip"] == c and r["footIK"] == ik]
                worst = max(xs, key=abs) if xs else 0
                cell.append(f"{sum(xs)/len(xs):5.1f}[{worst:5.1f}]" if xs else "  -  ")
            line += f"{' | '.join(cell):>34}"
        print(line)
    if key == "skateCms":
        print(f"{'(source)':13}" + "".join(f"{'':>34}" for v in vs[:0]) + "  " +
              "  ".join(f"{c}={next(r['srcSkateCms'] for r in data[vs[0]] if r['clip']==c):.1f}" for c in clips))
