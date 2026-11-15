"""Generate the 3 driver test motions via the Promptimate server API."""
import os, sys, json
os.environ["UNITY_PROJECT"] = r"D:\tmp\mdriver_unity"
os.environ.setdefault("TEMP", r"D:\tmp"); os.environ.setdefault("TMP", r"D:\tmp")
sys.path.insert(0, r"D:\unity-text-to-anim\mcp_server")
import server
S = server.MotionSegment
tests = {
  "a_walk_wave": [S(prompt="a person walks forward and stops", seconds=3.5), S(prompt="a person waves with their right hand", seconds=3.0)],
  "b_sit_head": [S(prompt="a person sits down on the floor", seconds=3.5), S(prompt="a person sits on the floor and puts their head in their hands", seconds=3.5)],
  "c_punch": [S(prompt="a person punches forward with their right hand", seconds=2.0), S(prompt="a person punches forward with their right hand again", seconds=2.5)],
}
out = {}
for name, segs in tests.items():
    r = server.generate_motion(segs, unity_check="off")
    out[name] = r if isinstance(r, (dict, str)) else str(r)
    print(name, json.dumps(r, default=str)[:1500], flush=True)
json.dump(out, open(r"D:\unity-text-to-anim\.cache\kling_test\gen_results.json", "w"), default=str, indent=1)
