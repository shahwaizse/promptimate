"""Batch-generate the demo clip library through the MCP server's own code path, into DemoStudio/Assets/Clips/<key>.kimodo."""
import json, os, shutil, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
os.environ["UNITY_PROJECT"] = str(ROOT / "demo" / "_drop")          # server writes .kimodo here first
(ROOT / "demo" / "_drop" / "Assets").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "mcp_server"))
import server  # noqa: E402
CLIPS = ROOT / "unity" / "DemoStudio" / "Assets" / "Clips"
CLIPS.mkdir(parents=True, exist_ok=True)
spec = json.loads((ROOT / "demo" / "clips.json").read_text())
only = set(sys.argv[1:])
summary = {}
for key, s in spec.items():
    if only and key not in only: continue
    if (CLIPS / f"{key}.kimodo").exists() and not only: print("skip", key); continue
    t = time.time()
    segs = [server.MotionSegment(prompt=p, seconds=sec) for p, sec in s["seg"]]
    out = server.generate_motion(segs, name=key, seed=s["seed"], steps=30, unity_check=False)
    meta = json.loads(out[0])
    shutil.copyfile(meta["files"]["unity_asset"], CLIPS / f"{key}.kimodo")
    summary[key] = {"checks": meta["checks"]["passed"], "fails": meta["checks"]["failures"], "preview": meta["files"]["preview"]}
    print(f"{key}: {time.time()-t:.0f}s checks={meta['checks']['passed']} {meta['checks']['failures']}", flush=True)
server.worker.stop()
(ROOT / "demo" / "clips_summary.json").write_text(json.dumps(summary, indent=2))
