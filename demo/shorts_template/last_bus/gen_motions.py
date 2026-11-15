"""Motions for the example short "Last Bus" through Promptimate's own MCP tool function (server.generate_motion; GPU
access goes through the shared motiond daemon automatically).

    .venv\\Scripts\\python.exe demo\\shorts_template\\last_bus\\gen_motions.py

Blocking (world metres, shots.py convention: +Z away from the audience): a bench for two at BENCH facing the
audience, Nora walks in from the left and sits on its left half (her right), Walt walks in from the right and sits on
the right half, Jun crosses behind with an umbrella. Sitting uses generate_motion's `seat` option, computed with
shots.seat_option from where each clip actually starts (shots.chain_end), so the hips land on the bench render_shot
places. Writes motions.json (role -> motion name); reruns only generate what's missing.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "mcp_server"))
import server  # noqa: E402
import shots  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "motions.json"
BENCH = {"id": "bench", "type": "bench", "at": [0.0, 1.0], "yaw": 180, "stretch": 1.7, "seat_height": 0.45}
LAMP = {"id": "lamp", "type": "street_lamp", "at": [1.55, 1.45], "yaw": -90}
SEAT_H = 0.45
NORA_SEAT = shots.seat_hips(BENCH, +0.38)   # her right = screen-left
WALT_SEAT = shots.seat_hips(BENCH, -0.38)
WALK_Z = 0.62                               # walk line in front of the bench
NORA_START, NORA_YAW = (-4.2, WALK_Z), 90.0
WALT_START, WALT_YAW = (4.4, WALK_Z), -90.0
JUN_START, JUN_YAW = (-4.5, 4.2), 90.0


def gen(role, segments, **kw):
    t0 = time.time()
    if "seat" in kw and isinstance(kw["seat"], dict):
        kw["seat"] = server.Seat(**kw["seat"])
    if "root_path" in kw:
        kw["root_path"] = [server.Waypoint(**w) for w in kw["root_path"]]
    res = server.generate_motion([server.MotionSegment(**s) for s in segments], name=role, unity_check="off", **kw)
    meta = json.loads(res[0])
    print(f"{role}: {meta['name']} ({time.time() - t0:.0f}s) checks={meta['checks'].get('passed')} "
          f"seat={meta.get('seat_check')} hints={meta.get('hints')}", flush=True)
    return meta["name"]


def main():
    names = json.loads(OUT.read_text()) if OUT.exists() else {}

    def once(role, fn):
        if role not in names:
            names[role] = fn()
            OUT.write_text(json.dumps(names, indent=2))
        return names[role]

    def seated(role, prev, prompt, secs, takes=1):
        # Already seated: the clip starts on the bench (continue_from re-bases it to the origin) and stays there.
        return once(role, lambda: gen(role, [{"prompt": prompt, "seconds": secs}], continue_from=names[prev], takes=takes,
                                      seat={"t": [0.0, secs], "height": SEAT_H, "x": 0.0, "z": 0.0, "heading_deg": 0.0,
                                            "furniture": "bench"}))

    # --- Nora: walks in from the left, turns to the audience and sits, phone, call, listens, laughs.
    nora_end = (NORA_SEAT[0], WALK_Z)
    walk = round(abs(nora_end[0] - NORA_START[0]) / 1.25, 2)
    once("nora_enter", lambda: gen("nora_enter", [
        {"prompt": "a person walks forward with their head down", "seconds": walk},
        {"prompt": "a person stops and stands still", "seconds": 1.0}],
        root_path=shots.path_to_root_path([NORA_START, nora_end, nora_end], NORA_YAW, seconds=[0, walk, walk + 1.0]),
        takes=2))
    pos, yaw = shots.chain_end([names["nora_enter"]], NORA_START, NORA_YAW)
    once("nora_sit", lambda: gen("nora_sit", [
        {"prompt": "a person turns right and sits down", "seconds": 2.4},
        {"prompt": "a person sits still", "seconds": 1.4}],
        continue_from=names["nora_enter"], takes=2,
        seat=shots.seat_option(NORA_SEAT, 180.0, pos, yaw, [2.1, 3.8], SEAT_H)))
    seated("nora_phone", "nora_sit", "a person sits and looks down at a phone in their right hand", 4.0, takes=2)
    seated("nora_call", "nora_phone", "a person sits and holds a phone to their ear with their right hand", 4.0, takes=2)
    seated("nora_listen", "nora_call", "a person sits and turns their head to the left", 4.0)
    seated("nora_laugh", "nora_listen", "a person sits and laughs", 4.0, takes=2)
    seated("nora_rest", "nora_laugh", "a person sits still and looks forward", 4.0)

    # --- Walt: walks in from the right with his coffee, turns to the audience and sits, talks, drinks, raises it.
    walt_end = (WALT_SEAT[0], WALK_Z)
    walk = round(abs(walt_end[0] - WALT_START[0]) / 1.05, 2)  # slower, older
    once("walt_enter", lambda: gen("walt_enter", [
        {"prompt": "a person walks forward slowly holding a cup in their right hand", "seconds": walk},
        {"prompt": "a person stops and stands still", "seconds": 1.0}],
        root_path=shots.path_to_root_path([WALT_START, walt_end, walt_end], WALT_YAW, seconds=[0, walk, walk + 1.0]),
        takes=2))
    pos, yaw = shots.chain_end([names["walt_enter"]], WALT_START, WALT_YAW)
    once("walt_sit", lambda: gen("walt_sit", [
        {"prompt": "a person turns left and sits down slowly", "seconds": 2.6},
        {"prompt": "a person sits still", "seconds": 1.4}],
        continue_from=names["walt_enter"], takes=2,
        seat=shots.seat_option(WALT_SEAT, 180.0, pos, yaw, [2.3, 4.0], SEAT_H)))
    seated("walt_talk", "walt_sit", "a person sits and talks, gesturing with their left hand", 4.0, takes=2)
    seated("walt_drink", "walt_talk", "a person sits and drinks from a cup with their right hand", 3.5, takes=2)
    seated("walt_raise", "walt_drink", "a person sits and raises their right hand in a toast", 3.5, takes=2)

    # --- Jun: crosses behind the bench with an umbrella.
    once("jun_cross", lambda: gen("jun_cross", [
        {"prompt": "a person walks forward holding an umbrella above their head with their right hand", "seconds": 7.0}],
        root_path=[{"t": 0, "x": 0, "z": 0}, {"t": 7.0, "x": 0, "z": 9.0}], takes=2))
    print(json.dumps(names, indent=2))


if __name__ == "__main__":
    main()
