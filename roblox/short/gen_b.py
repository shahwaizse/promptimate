"""Version B (Promptimate): generate every character's performance as one continue_from chain per character, with
root_path blocking converted from the town layout (story.py) into each clip's own space.

    .venv\\Scripts\\python.exe roblox\\short\\gen_b.py [--redo key,key]

Writes .cache/roblox_short/b_chains.json: per character, clips with story start time, duration and world origin
(floor x/z under the first frame's hips + Roblox yaw), plus a continuity check at every join (world joint distance
between the last frame of a clip and the first of the next, through the same placement the Roblox player uses).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
sys.path.insert(0, str(HERE))
os.environ.setdefault("UNITY_PROJECT", str(ROOT / ".cache" / "no_unity_project"))
os.environ.setdefault("TEMP", r"D:\tmp")
os.environ.setdefault("TMP", r"D:\tmp")
import constraints as C  # noqa: E402
import motion  # noqa: E402
import story as S  # noqa: E402

OUT = ROOT / ".cache" / "roblox_short"
CHAINS = OUT / "b_chains.json"

W = S.PATHS
SEAT_M = 0.42          # kid bench seat top (m); x 2.14 studs/m = 0.9 studs
SEAT_XZ = (0.0, 1.3)   # seated hips (studs, world)
# per character: (key, story start, [(prompt, seconds)], world waypoints [(story t, (x, z))] or None, kwargs, want_end_dir)
PLAN = {
    "timmy": [
        ("t_walk", 0.0, [("a person walks forward slowly and tiredly with their head down", 4.0)],
         W["timmy_walk"], {"takes": 3}, None),
        ("t_sit", 4.0, [("a person turns to the right and sits down", 2.0), ("a person sits and leans back, relaxing", 1.0)],
         None, {"seat_world": {"t": [1.6, 3.0], "height": SEAT_M, "at": SEAT_XZ, "face": S.PZ}}, S.PZ),
        ("t_phone", 7.0, [("a person sits and holds a phone to their right ear with their right hand", 3.5)], None,
         {"seat_world": {"t": [0.0, 3.5], "height": SEAT_M, "at": SEAT_XZ, "face": S.PZ}}, None),
        ("t_run", 10.5, [("a person stands up quickly and turns to the left", 1.0),
                         ("a person runs forward, then stops and turns around", 3.8)],
         [(10.5, SEAT_XZ)] + W["timmy_run"] + [(15.3, S.TIMMY_HIDE)],
         {"seat_world": {"t": [0.0, 0.3], "height": SEAT_M, "at": SEAT_XZ, "face": S.PZ}}, S.NX),
        ("t_hide", 15.3, [("a person crouches down low and hides", 1.7), ("a person leans to the left and peeks out", 2.0),
                          ("a person ducks back down", 1.5), ("a person slowly leans to the left and peeks out again", 2.5)],
         None, {}, None),
        ("t_fall", 23.0, [("a person gets startled, jumps backward and falls down onto the ground", 2.5)], None, {}, None),
        ("t_ground", 25.5, [("a person sits on the ground leaning back on their hands and looks up", 7.1)], None, {}, None),
    ],
    "officer": [
        ("o_walk", 7.5, [("a person walks forward confidently", 4.8), ("a person stops and stands still", 1.2)],
         [(7.5, W["officer_walk"][0][1]), (12.8, W["officer_walk"][1][1]), (13.5, W["officer_walk"][1][1])], {"takes": 3}, None),
        ("o_look", 13.5, [("a person looks around to the left and to the right, searching", 3.0),
                          ("a person turns to the left and looks", 2.0)], None, {}, None),
        ("o_walk2", 18.5, [("a person walks forward quickly", 3.6), ("a person stops and turns to the left", 0.9)],
         W["officer_walk2"] + [(23.0, S.OFFICER_SCARE)], {}, S.NZ),
        # o_walk2 ended turned ~180 deg (facing -X, Timmy is at -Z): turn right into the scare (fix-up regeneration)
        ("o_boo", 23.0, [("a person turns to the right and leans forward, raising both arms to scare someone", 1.2),
                         ("a person stands with their hands on their hips", 1.3)], None, {}, S.NZ),
        ("o_talk", 25.5, [("a person talks and gestures with both hands", 3.5)], None, {}, None),
        ("o_sit", 29.0, [("a person sits down on the ground", 3.6)], None, {}, None),
    ],
    "lee": [
        ("l_idle", 0.0, [("a person stands still and shifts their weight", 8.25),
                         ("a person stands still and looks around", 8.25)], None, {"in_place": True}, None),
        ("l_point", 16.5, [("a person points to the left with their left arm", 2.5)], None, {}, None),
        ("l_arms", 19.0, [("a person crosses their arms", 3.6), ("a person stands with their arms crossed and taps their foot", 10.0)],
         None, {}, None),
    ],
}


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def basis(yaw: float):
    f = np.array([-math.sin(yaw), -math.cos(yaw)])          # Roblox look vector (x, z)
    left = np.array([f[1], -f[0]])                           # -(f x up)
    return f, left


def to_local(p, yaw, spm, t0, pts):
    f, left = basis(yaw)
    out = []
    for t, (x, z) in pts:
        w = np.array([x, z]) - p
        out.append({"t": round(t - t0, 3), "x": round(float(w @ left) / spm, 4), "z": round(float(w @ f) / spm, 4)})
    return out


def world_joints(root, rot, frame, p, yaw, spm):
    """World (studs) joint positions of one frame, placed like PromptimatePlayer (frame-0 hips = origin)."""
    pos = motion.fk(root[frame:frame + 1], rot[frame:frame + 1])[0].astype(np.float64)
    f, left = basis(yaw)
    rel = pos - np.array([root[0, 0], 0, root[0, 2]])
    xz = p + np.outer(rel[:, 0], left) * spm + np.outer(rel[:, 2], f) * spm
    return np.stack([xz[:, 0], rel[:, 1] * spm, xz[:, 1]], axis=1)


def place_next(root, rot, p, yaw, spm):
    f, left = basis(yaw)
    d = root[-1] - root[0]
    h = C.frame_placement(root, rot, len(root) - 1)[2]
    return p + (left * d[0] + f * d[2]) * spm, yaw + h


def end_dir(root, rot, yaw):
    h = C.frame_placement(root, rot, len(root) - 1)[2]
    f, _ = basis(yaw + h)
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redo", default="", help="comma-separated clip keys to regenerate (and everything after them)")
    ap.add_argument("--only", default="", help="comma-separated characters")
    ap.add_argument("--chains", default="", help="output json (default .cache/roblox_short/b_chains.json)")
    a = ap.parse_args()
    global CHAINS
    if a.chains:
        CHAINS = Path(a.chains)
    import server
    OUT.mkdir(parents=True, exist_ok=True)
    prev = json.loads(CHAINS.read_text()) if CHAINS.exists() else {}
    redo = set(filter(None, a.redo.split(",")))
    result = {"chars": {}, "timing": prev.get("timing", {})}
    t_all = time.time()
    for who, clips in PLAN.items():
        if a.only and who not in a.only.split(","):
            continue
        spm = S.SPM[who]
        (p0, d0) = S.START[who]
        p, yaw = np.array(p0, float), S.yaw_of(d0)
        old = {c["key"]: c for c in prev.get("chars", {}).get(who, [])}
        out, prev_name, dirty = [], None, False
        for key, t0, segs, pts, kw, want in clips:
            dirty = dirty or key in redo or key not in old
            if not dirty:
                c = old[key]
            else:
                c, best = None, None
                for attempt in range(3):
                    args = dict(kw)
                    sw = args.pop("seat_world", None)
                    if sw:
                        loc = to_local(p, yaw, spm, 0.0, [(0.0, sw["at"])])[0]
                        args["seat"] = server.Seat(t=sw["t"], height=sw["height"], x=loc["x"], z=loc["z"],
                                                   heading_deg=round(math.degrees(wrap(S.yaw_of(sw["face"]) - yaw)), 2),
                                                   furniture="bench")
                    if pts:
                        args["root_path"] = [server.Waypoint(**w) for w in to_local(p, yaw, spm, t0, pts)]
                    if prev_name:
                        args["continue_from"] = prev_name
                    tt = time.time()
                    meta = json.loads(server.generate_motion([server.MotionSegment(prompt=pr, seconds=s) for pr, s in segs],
                                                             name=f"rs_{key}", seed=attempt * 7, unity_check="off", **args)[0])
                    gen_s = round(time.time() - tt, 1)
                    root, rot = motion.load(Path(meta["files"]["raw_dir"]))
                    ok, ang = True, 0.0
                    if want is not None:
                        fe = end_dir(root, rot, yaw)
                        ang = math.degrees(math.acos(max(-1, min(1, float(fe @ np.array(want, float))))))
                        ok = ang < 50
                        print(f"  {key} attempt {attempt}: end facing off by {ang:.0f} deg", flush=True)
                    c = {"seat_check": meta.get("seat_check"), "key": key, "name": meta["name"], "raw_dir": meta["files"]["raw_dir"], "gen_s": gen_s,
                         "checks": meta["checks"].get("passed"), "hints": meta.get("hints"), "attempts": attempt + 1,
                         "end_facing_err_deg": round(ang, 1)}
                    if best is None or ang < best["end_facing_err_deg"]:
                        best = c
                    if ok:
                        break
                c = dict(best, attempts=attempt + 1)
                print(f"{who}/{key}: {c['name']} ({c['gen_s']}s, checks={c['checks']}) hints={c['hints']}", flush=True)
            root, rot = motion.load(Path(c["raw_dir"]))
            c.update({"start": t0, "dur": round((len(root) - 1) / motion.FPS, 4), "frames": len(root),
                      "origin": {"x": round(float(p[0]), 4), "z": round(float(p[1]), 4), "yaw": round(float(yaw), 5)},
                      "hips0_canonical": [round(float(root[0, 0]), 3), round(float(root[0, 2]), 3)]})
            # continuity with the previous clip
            if out:
                pr, pq = motion.load(Path(out[-1]["raw_dir"]))
                o = out[-1]["origin"]
                a_ = world_joints(pr, pq, len(pr) - 1, np.array([o["x"], o["z"]]), o["yaw"], spm)
                b_ = world_joints(root, rot, 0, p, yaw, spm)
                c["join_err_studs"] = round(float(np.linalg.norm(a_ - b_, axis=1).max()), 3)
            out.append(c)
            prev_name = c["name"]
            p, yaw = place_next(root, rot, p, yaw, spm)
        result["chars"][who] = out
        CHAINS.write_text(json.dumps(result, indent=1))
    result["timing"]["gen_b_wall_s_last_run"] = round(time.time() - t_all, 1)
    CHAINS.write_text(json.dumps(result, indent=1))
    for who, cl in result["chars"].items():
        for c in cl:
            print(f"{who:8s} {c['key']:9s} start={c['start']:5.1f} dur={c['dur']:5.2f} join_err={c.get('join_err_studs', '-')}"
                  f" origin=({c['origin']['x']:.1f},{c['origin']['z']:.1f}) yaw={math.degrees(c['origin']['yaw']):.0f}")
    server.worker.stop()


if __name__ == "__main__":
    main()
