"""Quick sweep of engine/ggml env switches on the slow shapes (batch 3 @150 frames, batch 2 @300 frames), 10 steps.
Prints one line per config as it finishes (watch the log)."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
from kimodo_worker import KimodoWorker, Segment
import constraints as C
BASE = {"KIMODO_TEXT_BACKEND": "cpu", "KIMODO_PROFILE": "0"}
CONFIGS = [{}, {"KIMODO_MOTION_PACKED_ATTENTION": "0"}, {"KIMODO_MOTION_GRAPH_CACHE": "0"},
           {"GGML_VK_DISABLE_FUSION": "1"}, {"GGML_VK_DISABLE_GRAPH_OPTIMIZE": "1"}, {"KIMODO_MOTION_LAYER_CHUNK": "16"},
           {"KIMODO_MOTION_LAYER_CHUNK": "2"}, {"GGML_VK_DISABLE_ASYNC": "1"}, {"GGML_VK_SERIALIZE_SUBMISSIONS": "1"}]
out = Path("D:/tmp/sweep")
P = "a person walks forward"
for extra in CONFIGS:
    env = {**BASE, **extra}
    w = KimodoWorker(engine_dir=ROOT / "third_party/kimodo.cpp/build/promptimate", extra_env=env)
    w.generate([Segment(P, 30)], out / "w", steps=1, seed=0)
    c = C.Constraints(150).root_xz(0, 0., 0.).save(out / "c.bin")
    r = {"env": extra,
         "b2_150": w.generate([Segment(P, 150)], out / "a", steps=10, seed=0)["seconds"],
         "b3_150": w.generate([Segment(P, 150)], out / "b", steps=10, seed=0, constraints=c)["seconds"],
         "b2_300": w.generate([Segment(P, 300)], out / "c", steps=10, seed=0)["seconds"]}
    w.stop()
    print(json.dumps(r), flush=True)
