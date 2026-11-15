"""Inspection renders for the render kit: the cast line-up, every prop in a hand, every furniture type with a seated
character. Used while tuning the catalogues in mcp_server/shots.py (prop grip offsets, model orientation, seat
heights); also a quick visual regression check after touching Props.cs / Seating.cs.

    .venv\\Scripts\\python.exe demo\\shorts_template\\inspect_assets.py [cast|props|furniture|all] [--quality draft]

Output: contact sheets + MP4s under .cache/shots/renders/inspect_* (paths printed), validation printed per shot.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server"))
import shots  # noqa: E402


def lineup(names, spacing=0.9, z=0.0):
    n = len(names)
    return [{"id": f"c{i}", "cast": c, "at": [round((i - (n - 1) / 2) * spacing, 3), z], "yaw": 180} for i, c in enumerate(names)]


def cast_shot(quality):
    names = list(shots.CAST_EXTRA)
    return {"name": "inspect_cast", "aspect": "16:9", "stage": "studio", "lighting": "studio", "quality": quality,
            "seconds": 1.0, "actors": lineup(names, 0.85),
            "camera": {"preset": "explicit", "pos": [0, 1.3, -9.5], "look_at": [0, 0.9, 0], "fov": 34}}


def props_shot(quality, names=None, motion=None, cast="man", tag=""):
    names = names or list(shots.PROPS)
    actors = []
    for i, pr in enumerate(names):
        a = {"id": f"p{i}", "cast": cast, "at": [round((i - (len(names) - 1) / 2) * 0.8, 3), 0], "yaw": 180,
             "props": [{"prop": pr, "hand": "right"}]}
        if motion:
            a["motion"] = motion
        actors.append(a)
    return {"name": "inspect_props" + tag + ("_m" if motion else ""), "aspect": "16:9", "stage": "studio", "lighting": "studio",
            "quality": quality, "seconds": 1.0 if not motion else None, "actors": actors,
            "camera": {"preset": "explicit", "pos": [0, 1.2, -4.6], "look_at": [0, 1.0, 0], "fov": 42}}


def furniture_shot(quality, seat_motion=None):
    types = [t for t in shots.FURNITURE if t != "street_lamp"]
    furn = [{"id": t, "type": t, "at": [round((i - (len(types) - 1) / 2) * 1.6, 3), 1.5], "yaw": 180} for i, t in enumerate(types)]
    actors = [{"id": "probe", "cast": "woman_casual", "at": [0, -1.6], "yaw": 180}]
    if seat_motion:
        actors[0]["motion"] = seat_motion
    return {"name": "inspect_furniture", "aspect": "16:9", "stage": "studio", "lighting": "studio", "quality": quality,
            "seconds": None if seat_motion else 1.0, "furniture": furn, "actors": actors,
            "camera": {"preset": "explicit", "pos": [0, 2.2, -8.5], "look_at": [0, 0.6, 0.8], "fov": 42}}


def run(spec):
    r = shots.render(spec)
    v = r["validation"]
    print(f"{spec['name']}: {r['seconds_total']}s cached={r['cached']} passed={v['passed']}")
    for k in ("failures", "warnings"):
        for m in v[k]:
            print(f"   {k[:-1]}: {m}")
    for k in ("props", "seats"):
        for kk, vv in (v.get(k) or {}).items():
            print(f"   {k} {kk}: {json.dumps(vv)}")
    if r.get("furniture"):
        print("   furniture:", json.dumps(r["furniture"]))
    print("   sheet:", r["contact_sheet"])
    return r


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="?", default="all")
    ap.add_argument("--quality", default="draft")
    ap.add_argument("--motion", default=None, help="motion for the props / furniture probes")
    a = ap.parse_args()
    if a.what in ("cast", "all"):
        run(cast_shot(a.quality))
    if a.what in ("props", "all"):
        names = list(shots.PROPS)
        for k in range(0, len(names), 6):
            run(props_shot(a.quality, names[k:k + 6], motion=a.motion if a.what == "props" else None, tag=str(k // 6)))
    if a.what in ("furniture", "all"):
        run(furniture_shot(a.quality, a.motion if a.what == "furniture" else None))
