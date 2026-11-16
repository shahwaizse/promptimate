"""Motions for the Fidelity piece "Your Move" through Promptimate's own MCP tool function (server.generate_motion;
GPU access goes through the shared motiond daemon automatically).

    .venv\\Scripts\\python.exe demo\\fidelity\\gen_motions.py [--redo role1,role2]

Story: late afternoon in an old living room. A father stands at the window. His daughter comes in with a suitcase,
sets it down. He turns, gestures to the chess table by the window, and they sit down across the board from each other.

Blocking (world metres, Unity axes: +X right, +Z toward the window wall at z = 2.8, yaw = Unity degrees):
  father  starts at the window W facing it; turns to the door, gestures to the table, sits on chair A (faces +X)
  daughter enters through the door in the south wall (x = -1.45), stops, puts the suitcase down on her right,
           walks to chair B (faces -X) across the board and sits.
Writes motions.json (role -> motion name); reruns only generate what's missing (or --redo).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("PROMPTIMATE_RENDER_PROJECT", str(ROOT / "unity" / "FidelityStudio"))
sys.path.insert(0, str(ROOT / "mcp_server"))
import server  # noqa: E402
import shots  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "motions.json"
LAYOUT = json.loads((HERE / "layout.json").read_text())
SEAT_H = LAYOUT["seat_height"]


def P(k):
    return tuple(LAYOUT[k])


def gen(role, segments, **kw):
    t0 = time.time()
    if "seat" in kw and isinstance(kw["seat"], dict):
        kw["seat"] = server.Seat(**kw["seat"])
    if "root_path" in kw:
        kw["root_path"] = [server.Waypoint(**w) for w in kw["root_path"]]
    res = server.generate_motion([server.MotionSegment(**s) for s in segments], name="fid_" + role, unity_check="off", **kw)
    meta = json.loads(res[0])
    print(f"{role}: {meta['name']} ({time.time() - t0:.0f}s) checks={meta['checks'].get('passed')} "
          f"seat={meta.get('seat_check')} hints={meta.get('hints')}", flush=True)
    return meta["name"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redo", default="")
    a = ap.parse_args()
    names = json.loads(OUT.read_text()) if OUT.exists() else {}
    for r in filter(None, a.redo.split(",")):
        names.pop(r, None)

    def once(role, fn):
        if role not in names:
            names[role] = fn()
            OUT.write_text(json.dumps(names, indent=2))
        return names[role]

    def end_of(roles, start, yaw):
        return shots.chain_end([names[r] for r in roles], start, yaw)

    def seated(role, prev, prompt, secs, takes=2):
        return once(role, lambda: gen(role, [{"prompt": prompt, "seconds": secs}], continue_from=names[prev], takes=takes,
                                      seat={"t": [0.0, secs], "height": SEAT_H, "x": 0.0, "z": 0.0, "heading_deg": 0.0,
                                            "furniture": "chair"}))

    # --- Father: at the window, turns to the door, gestures to the table, sits on chair A.
    W, WY = P("father_start"), LAYOUT["father_yaw"]
    once("f_window", lambda: gen("f_window", [
        {"prompt": "a person stands still with their hands clasped behind their back, looking forward", "seconds": 6.0},
        {"prompt": "a person stands with their hands behind their back and slowly lowers their head", "seconds": 5.5}],
        in_place=True, takes=2))
    once("f_turn", lambda: gen("f_turn", [
        {"prompt": "a person slowly turns around to their right", "seconds": 2.6},
        {"prompt": "a person stands still and looks forward", "seconds": 2.2}],
        continue_from=names["f_window"], takes=3))
    once("f_gesture", lambda: gen("f_gesture", [
        {"prompt": "a person gestures to the left with their left hand, inviting someone to sit", "seconds": 2.6}],
        continue_from=names["f_turn"], takes=3))
    pos, yaw = end_of(["f_window", "f_turn", "f_gesture"], W, WY)
    A = P("chair_a_hips")
    once("f_sit", lambda: gen("f_sit", [
        {"prompt": "a person takes a step to the left and sits down slowly", "seconds": 2.8},
        {"prompt": "a person sits still", "seconds": 1.2}],
        continue_from=names["f_gesture"], takes=3,
        seat=shots.seat_option(A, LAYOUT["chair_a_yaw"], pos, yaw, [2.5, 4.0], SEAT_H, furniture="chair")))
    seated("f_sit_wait", "f_sit", "a person sits still and looks forward", 3.5)
    seated("f_move", "f_sit_wait", "a person sits and slowly reaches forward with their right hand, then pulls it back", 3.6, takes=3)
    seated("f_sit_end", "f_move", "a person sits still and looks forward", 3.0)

    # --- Daughter: walks in with a suitcase, sets it down, walks to chair B and sits.
    D0, DY = P("daughter_start"), LAYOUT["daughter_yaw"]
    stop = P("daughter_stop")
    walk = 3.4
    once("d_enter", lambda: gen("d_enter", [
        {"prompt": "a person walks forward slowly with their right arm hanging straight down at their side, carrying something heavy", "seconds": walk},
        {"prompt": "a person stops and stands still with their arms down at their sides", "seconds": 1.2}],
        root_path=shots.path_to_root_path([D0, P("daughter_mid"), stop, stop], DY, seconds=[0, walk * 0.8, walk, walk + 1.2]),
        takes=3))
    once("d_setdown", lambda: gen("d_setdown", [
        {"prompt": "a person bends down and puts a bag down on the floor with their right hand, then stands up", "seconds": 2.8}],
        continue_from=names["d_enter"], takes=3))
    once("d_wait", lambda: gen("d_wait", [
        {"prompt": "a person stands still and looks forward", "seconds": 4.0}],
        continue_from=names["d_setdown"], takes=2))
    pos, yaw = end_of(["d_enter", "d_setdown", "d_wait"], D0, DY)
    pts = [pos] + [tuple(p) for p in LAYOUT["daughter_path"]]
    once("d_walk", lambda: gen("d_walk", [
        {"prompt": "a person walks forward", "seconds": 2.9},
        {"prompt": "a person stops and stands still", "seconds": 0.7}],
        continue_from=names["d_wait"], takes=2,
        root_path=shots.path_to_root_path(pts + [pts[-1]], yaw, seconds=[0, 0.81, 2.26, 2.9, 3.6])))
    pos, yaw = end_of(["d_enter", "d_setdown", "d_wait", "d_walk"], D0, DY)
    B = P("chair_b_hips")
    once("d_sit", lambda: gen("d_sit", [
        {"prompt": "a person turns around and sits down", "seconds": 2.6},
        {"prompt": "a person sits still", "seconds": 1.2}],
        continue_from=names["d_walk"], takes=3,
        seat=shots.seat_option(B, LAYOUT["chair_b_yaw"], pos, yaw, [2.3, 3.8], SEAT_H, furniture="chair")))
    seated("d_sit_look", "d_sit", "a person sits still and looks down at the table", 4.0)
    seated("d_sit_end", "d_sit_look", "a person sits and slowly raises their head", 4.0)
    print(json.dumps(names, indent=2))


if __name__ == "__main__":
    main()
