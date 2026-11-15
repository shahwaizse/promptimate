"""Prints demo/retarget_report_<variant>.json as a table (optionally vs another report)."""
import json, sys
rows = json.load(open(sys.argv[1]))["rows"]
print(f"{'character':14} {'clip':12} IK  skate(p95) src | float(p95) pen | handT handH | knee elbow | pops")
for r in rows:
    print(f"{r['character'][:14]:14} {r['clip'][:12]:12} {'on ' if r['footIK'] else 'off'} "
          f"{r['skateCms']:5.1f}({r['skateP95Cms']:5.1f}) {r['srcSkateCms']:4.1f} | {r['floatCm']:5.1f}({r['floatP95Cm']:5.1f}) {r['penCm']:4.1f} | "
          f"{r['handTorsoCm']:4.1f} {r['handHeadCm']:4.1f} | {r['kneeHyperDeg']:4.1f} {r['elbowHyperDeg']:4.1f} | {r['pops']}")
