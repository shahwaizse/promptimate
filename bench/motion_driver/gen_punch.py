import os, sys, json
os.environ["UNITY_PROJECT"] = r"D:\tmp\mdriver_unity"
sys.path.insert(0, r"D:\unity-text-to-anim\mcp_server")
import server
S = server.MotionSegment
r = server.generate_motion([S(prompt="a person stands in a fighting stance", seconds=1.0),
                            S(prompt="a person punches forward with their right fist", seconds=2.0),
                            S(prompt="a person punches forward with their right fist again", seconds=2.0)],
                           takes=4, seed=10, start_pose="idle", unity_check="off")
s = r[0]; j = json.loads(s); print(j["files"]["preview"], j["chosen_take"], [ (t["seed"], t["score"], t["why"]) for t in j["takes"]])
