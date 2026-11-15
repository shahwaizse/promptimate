"""Generates the motions for the example short "Wrong Turn" through Promptimate's own MCP tool function
(server.generate_motion; GPU access goes through the shared motiond daemon automatically).

    .venv\\Scripts\\python.exe demo\\shorts_template\\story\\gen_motions.py

Writes story/motions.json mapping role -> generated motion name. Staging comes from shots.stage(), so the root paths
match where render_shot puts the characters.
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
STAGING = json.loads((HERE / "staging.json").read_text())


def gen(role, segments, **kw):
    t0 = time.time()
    res = server.generate_motion([server.MotionSegment(**s) for s in segments], name=role, unity_check="off", **kw)
    meta = json.loads(res[0])
    print(f"{role}: {meta['name']} ({time.time() - t0:.0f}s) checks={meta['checks'].get('passed')} "
          f"hints={meta.get('hints')}", flush=True)
    return meta["name"]


def main():
    placed = shots.stage(STAGING["actors"])
    leo, ava = placed["leo"], placed["ava"]
    names = json.loads(OUT.read_text()) if OUT.exists() else {}

    def once(role, fn):
        if role not in names:
            names[role] = fn()
            OUT.write_text(json.dumps(names, indent=2))
        return names[role]

    # Leo walks in from the left, stops and looks around (root path from the staging helper).
    once("leo_enter", lambda: gen("leo_enter", [
        {"prompt": "a person walks forward", "seconds": 3.2},
        {"prompt": "a person stops and looks around to the left and right", "seconds": 3.0}],
        root_path=[server.Waypoint(**w) for w in leo["root_path"][:2]] +
                  [server.Waypoint(t=6.2, x=leo["root_path"][-1]["x"], z=leo["root_path"][-1]["z"])], takes=2))
    once("leo_confused", lambda: gen("leo_confused", [
        {"prompt": "a person scratches their head with their right hand", "seconds": 3.0}],
        continue_from=names["leo_enter"]))
    once("leo_listen", lambda: gen("leo_listen", [
        {"prompt": "a person stands still and nods their head", "seconds": 3.5}],
        continue_from=names["leo_confused"]))
    once("leo_thanks", lambda: gen("leo_thanks", [
        {"prompt": "a person waves with their right hand", "seconds": 2.5}],
        continue_from=names["leo_listen"]))
    once("leo_runs", lambda: gen("leo_runs", [
        {"prompt": "a person turns around and jogs forward", "seconds": 3.5}],
        continue_from=names["leo_thanks"]))
    # Ava walks in from the right and stops facing Leo.
    once("ava_enter", lambda: gen("ava_enter", [
        {"prompt": "a person walks forward", "seconds": 3.0},
        {"prompt": "a person stops and stands still", "seconds": 1.5}],
        root_path=[server.Waypoint(**w) for w in ava["root_path"][:2]] +
                  [server.Waypoint(t=4.5, x=ava["root_path"][-1]["x"], z=ava["root_path"][-1]["z"])], takes=2))
    once("ava_points", lambda: gen("ava_points", [
        {"prompt": "a person points forward with their right hand", "seconds": 3.0}],
        continue_from=names["ava_enter"]))
    once("ava_shrug", lambda: gen("ava_shrug", [
        {"prompt": "a person shrugs their shoulders", "seconds": 2.5},
        {"prompt": "a person stands still with their hands on their hips", "seconds": 2.5}],
        continue_from=names["ava_points"]))
    print(json.dumps(names, indent=2))


if __name__ == "__main__":
    main()
