"""Where is the VRAM cliff? Times a 5 s clip at batch 2 (plain) vs batch 3 (constrained) and a 10 s clip, for a given
engine env (e.g. --env KIMODO_TEXT_BACKEND=cpu). Uses a direct worker so env changes take effect."""
import argparse, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
from kimodo_worker import KimodoWorker, Segment
import constraints as C
sys.path.insert(0, str(ROOT / "bench"))
from placement_test import gpu_mem

ap = argparse.ArgumentParser(); ap.add_argument("--env", action="append", default=[]); a = ap.parse_args()
env = dict(kv.split("=", 1) for kv in a.env)
w = KimodoWorker(engine_dir=ROOT / "third_party/kimodo.cpp/build/promptimate", extra_env=env)
out = Path("D:/tmp/cliff")
P = "a person walks forward and waves with their right hand"
t = time.time(); w.generate([Segment(P, 30)], out / "w", steps=1, seed=0); cold = time.time() - t
t = time.time(); w.generate([Segment("a person jumps up and down", 30)], out / "w2", steps=1, seed=0); enc = time.time() - t
c = C.Constraints(150).root_xz(0, 0.0, 0.0).save(out / "c.bin")
res = {"env": env, "cold_s": round(cold, 1), "new_prompt_1step_s": round(enc, 2),
       "b2_150f": w.generate([Segment(P, 150)], out / "a", steps=30, seed=0)["seconds"],
       "b3_150f": w.generate([Segment(P, 150)], out / "b", steps=30, seed=0, constraints=c)["seconds"],
       "b2_300f": w.generate([Segment(P, 300)], out / "c", steps=30, seed=0)["seconds"],
       "mem": gpu_mem(w.proc.pid)}
w.stop(); print(json.dumps(res))
