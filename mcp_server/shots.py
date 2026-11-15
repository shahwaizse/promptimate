"""Shot rendering for Promptimate: Promptimate clips on characters, staged and filmed in Unity (URP), as MP4.

Used by the `render_shot` / `stage_actors` MCP tools and directly from Python:

    import shots
    res = shots.render({"actors": [{"id": "A", "cast": "businessman", "motion": "wave_20261115_120000"}],
                        "camera": "medium", "stage": "street", "lighting": "golden_hour", "aspect": "9:16"})
    res["mp4"], res["contact_sheet"], res["validation"]

World frame for shots: metres, Unity axes. +Z points away from the audience (the default camera side is -Z), +X is
screen-right for that audience, yaw is degrees clockwise seen from above (0 faces +Z, 180 faces the audience).

The Unity side (unity/DemoStudio, Assets/Editor/ShotStudio) builds the stage, samples the clips, computes camera
presets from the actual poses, renders, and reports where every character landed in the frame. One batchmode editor
stays warm between shots (ShotServer); renders are cached by the content of everything they depend on.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
STUDIO = Path(os.environ.get("PROMPTIMATE_RENDER_PROJECT", ROOT / "unity" / "DemoStudio"))
CACHE = ROOT / ".cache" / "shots"
QUEUE = CACHE / "queue"
GENERATED = STUDIO / "Assets" / "Promptimate" / "Generated"
VERSION = 8  # bump when the Unity renderer or resolution changes in a way that should invalidate cached renders

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
STAGES = ["street", "interior", "park", "studio", "void"]
LIGHTING = ["day", "golden_hour", "night_street", "interior_warm", "studio"]
WEATHER = ["", "rain", "fog", "rain_fog"]
CAMERAS = ["wide", "medium", "close_up", "over_shoulder", "follow", "push_in", "orbit", "low_angle", "top_down",
           "two_shot", "explicit"]

# Starter cast: CC0 characters fetched by unity/DemoStudio/fetch_render_assets.py (see render_assets.json).
# build > 1 widens the body (x/z scale) for heavier builds; height normalises the standing height.
_Q = "Assets/ThirdParty/Quaternius/"
_K = "Assets/ThirdParty/Kenney/AnimatedCharacters1/"
_P = "Assets/ThirdParty/Props/"
CAST = {
    "businessman": {"model": _Q + "BusinessMan.glb", "height": 1.82, "look": "man, dark suit and tie", "license": "CC0 (Quaternius)"},
    "adventurer": {"model": _Q + "Adventurer.glb", "height": 1.78, "look": "man, green explorer jacket, backpack", "license": "CC0 (Quaternius)"},
    "punk": {"model": _Q + "Punk.glb", "height": 1.70, "look": "woman, red leather jacket", "license": "CC0 (Quaternius)"},
    "beach": {"model": _Q + "Beach.glb", "height": 1.68, "look": "woman, summer top and shorts", "license": "CC0 (Quaternius)"},
    "farmer": {"model": _Q + "Farmer.glb", "height": 1.80, "look": "man, overalls and straw hat", "license": "CC0 (Quaternius)"},
    "kenney_skater_f": {"model": _K + "Model/characterMedium.fbx", "skin": _K + "Skins/skaterFemaleA.png", "height": 1.65,
                        "look": "stylised blocky woman, skater", "license": "CC0 (Kenney)"},
    "kenney_skater_m": {"model": _K + "Model/characterMedium.fbx", "skin": _K + "Skins/skaterMaleA.png", "height": 1.72,
                        "look": "stylised blocky man, skater", "license": "CC0 (Kenney)"},
    "kenney_criminal": {"model": _K + "Model/characterMedium.fbx", "skin": _K + "Skins/criminalMaleA.png", "height": 1.75,
                        "look": "stylised blocky man, striped shirt", "license": "CC0 (Kenney)"},
    "kenney_cyborg": {"model": _K + "Model/characterMedium.fbx", "skin": _K + "Skins/cyborgFemaleA.png", "height": 1.7,
                      "look": "stylised blocky woman, cyborg", "license": "CC0 (Kenney)"},
}
# Extended cast (all CC0 Quaternius via Poly Pizza). Filled in by CAST_EXTRA below so the starter entries above stay
# byte-identical for existing renders.
_K2 = "Assets/ThirdParty/Kenney/AnimatedCharacters2/Skins/"
_K3 = "Assets/ThirdParty/Kenney/AnimatedCharacters3/Skins/"
CAST_EXTRA: dict = {
    "woman_casual": {"model": _Q + "WomanCasual.glb", "height": 1.66, "look": "young woman, dark hair, mint t-shirt, dark shorts", "license": "CC0 (Quaternius)"},
    "woman_tank_top": {"model": _Q + "WomanTankTop.glb", "height": 1.69, "look": "young woman, long hair, light blue tank top, sporty", "license": "CC0 (Quaternius)"},
    "man_suit": {"model": _Q + "ManSuit.glb", "height": 1.79, "build": 1.08, "look": "older man, grey hair, black suit", "license": "CC0 (Quaternius)"},
    "man": {"model": _Q + "Man.glb", "height": 1.80, "look": "young man, short hair, light blue t-shirt, shorts", "license": "CC0 (Quaternius)"},
    "woman_dress": {"model": _Q + "WomanDress.glb", "height": 1.65, "look": "blonde woman, red dress", "license": "CC0 (Quaternius)"},
    "blonde_woman": {"model": _Q + "AnimatedWomanA.glb", "height": 1.67, "look": "blonde woman, white top, orange trousers", "license": "CC0 (Quaternius)"},
    "redhead_woman": {"model": _Q + "AnimatedWomanB.glb", "height": 1.63, "look": "red-haired woman, green dress", "license": "CC0 (Quaternius)"},
    "hooded_adventurer": {"model": _Q + "HoodedAdventurer.glb", "height": 1.72, "look": "woman, brown leather adventurer outfit, white hair", "license": "CC0 (Quaternius)"},
    "kid_boy": {"model": _K + "Model/characterMedium.fbx", "skin": _K3 + "humanMaleA.png", "height": 1.25,
                "look": "stylised blocky kid (boy), ~8 years", "license": "CC0 (Kenney)"},
    "kid_girl": {"model": _K + "Model/characterMedium.fbx", "skin": _K3 + "humanFemaleA.png", "height": 1.2,
                 "look": "stylised blocky kid (girl), ~8 years", "license": "CC0 (Kenney)"},
    "kenney_survivor_f": {"model": _K + "Model/characterMedium.fbx", "skin": _K2 + "survivorFemaleA.png", "height": 1.68,
                          "look": "stylised blocky woman, survivor jacket", "license": "CC0 (Kenney)"},
    "kenney_survivor_m": {"model": _K + "Model/characterMedium.fbx", "skin": _K2 + "survivorMaleB.png", "height": 1.8, "build": 1.12,
                          "look": "stylised blocky heavy-set man, survivor jacket", "license": "CC0 (Kenney)"},
}

# Props held in a hand (Props.cs). size = longest side in metres for a 1.75 m character; grip_at = where the hand is
# along the prop's main axis (0 bottom .. 1 top) after model_rot turns the model's main axis to +Y and its front to
# +Z. grip: power (handle across the fist) | cup (upright, tilts at the mouth) | flat (against the palm) | hang (bag) |
# cane | pinch. Models named
# "procedural:*" are built in code (no download).
PROPS: dict = {
    "phone": {"model": _P + "Smartphone.glb", "grip": "flat", "size": 0.15, "grip_at": 0.35, "fingers": "hold_flat", "light": "screen",
              "model_rot": [-90, 0, 180],  # file: lies flat, screen +Y, long side +Z -> screen +Z (out of the palm), long side +Y
              "license": "CC0 (smallbigsquare, Poly Pizza)"},
    "cup": {"model": _P + "Cup.glb", "grip": "cup", "size": 0.10, "grip_at": 0.5, "fingers": "grip", "license": "CC0 (Kenney)"},
    "coffee": {"model": _P + "Frappe.glb", "grip": "cup", "size": 0.16, "grip_at": 0.45, "fingers": "grip", "license": "CC0 (Kenney)"},
    "bag": {"model": _P + "BagQ.glb", "grip": "hang", "size": 0.38, "grip_at": 1.0, "fingers": "grip", "license": "CC0 (Quaternius)"},
    "briefcase": {"model": _P + "Suitcase.glb", "grip": "hang", "size": 0.45, "grip_at": 1.0, "fingers": "grip",
                  "license": "CC0 (smallbigsquare, Poly Pizza)"},
    "sword": {"model": _P + "SwordA.glb", "grip": "power", "size": 0.95, "grip_at": 0.08, "fingers": "grip", "rot": [0, 0, 0], "license": "CC0 (Quaternius)"},
    "book": {"model": _P + "BookA.glb", "grip": "flat", "size": 0.24, "grip_at": 0.5, "fingers": "hold_flat", "model_rot": [0, 90, 0], "license": "CC0 (Quaternius)"},
    "flashlight": {"model": "procedural:flashlight", "grip": "power", "size": 0.2, "grip_at": 0.35, "fingers": "grip",
                   "light": "torch", "license": "procedural (Promptimate)"},
    "umbrella": {"model": "procedural:umbrella", "grip": "power", "size": 1.04, "grip_at": 0.05, "fingers": "grip",
                 "license": "procedural (Promptimate)"},
    "stick": {"model": "procedural:cane", "grip": "cane", "size": 0.92, "grip_at": 0.93, "fingers": "grip",
              "license": "procedural (Promptimate)"},
    "baton": {"model": _P + "Baton.glb", "grip": "power", "size": 0.5, "grip_at": 0.2, "fingers": "grip", "model_rot": [-90, 0, 0],
              "license": "CC0 (CreativeTrio, Poly Pizza)"},
}

# Furniture placed by render_shot (Stages.Furniture). seat: the hips sit `seat_back` m behind the measured seat centre.
_F = "Assets/ThirdParty/Kenney/Furniture/"
_R = "Assets/ThirdParty/Kenney/CityRoads/"
FURNITURE: dict = {
    "bench": {"model": _F + "bench.fbx", "kit": "Furniture", "front_yaw": 180, "seat_height": 0.45, "seat_back": 0.04},
    "bench_cushion": {"model": _F + "benchCushion.fbx", "kit": "Furniture", "front_yaw": 180, "seat_height": 0.45, "seat_back": 0.04},
    "chair": {"model": _F + "chair.fbx", "kit": "Furniture", "front_yaw": 180, "seat_height": 0.46, "seat_back": 0.05},
    "chair_cushion": {"model": _F + "chairCushion.fbx", "kit": "Furniture", "front_yaw": 180, "seat_height": 0.46, "seat_back": 0.05},
    "sofa": {"model": _F + "loungeSofa.fbx", "kit": "Furniture", "front_yaw": 180, "seat_height": 0.42, "seat_back": 0.08},
    "sofa_long": {"model": _F + "loungeSofaLong.fbx", "kit": "Furniture", "front_yaw": 180, "seat_height": 0.42, "seat_back": 0.08},
    "lounge_chair": {"model": _F + "loungeChair.fbx", "kit": "Furniture", "front_yaw": 180, "seat_height": 0.42, "seat_back": 0.08},
    "stool": {"model": _F + "stoolBar.fbx", "kit": "Furniture", "seat_height": 0.72, "seat_back": 0.0},
    "ledge": {"model": "box", "size": [1.8, 0.42, 0.45], "color": [0.42, 0.41, 0.4], "seat_height": 0.0, "seat_back": 0.02},
    "crate": {"model": "box", "size": [0.55, 0.45, 0.55], "color": [0.45, 0.33, 0.2], "seat_height": 0.0, "seat_back": 0.0},
    "street_lamp": {"model": _R + "light-curved.fbx", "kit": "CityRoads", "lamp": [0.0, 5.6, 1.0], "anchor": "pivot"},
}

def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)  # never stdout: it carries the MCP stdio protocol


_lock = threading.Lock()   # one render at a time per process (the Unity server is single-threaded anyway)
_server_proc: subprocess.Popen | None = None


# ---------------------------------------------------------------------------------------------------------------------
# Tools on disk

def _ffmpeg() -> str:
    for c in (os.environ.get("FFMPEG"), r"D:\tools\ffmpeg\bin\ffmpeg.exe", shutil.which("ffmpeg")):
        if c and Path(c).exists():
            return str(c)
    raise RuntimeError("ffmpeg not found: set FFMPEG to ffmpeg.exe")


def _ffprobe() -> str | None:
    f = Path(_ffmpeg())
    p = f.with_name("ffprobe.exe" if f.suffix == ".exe" else "ffprobe")
    return str(p) if p.exists() else shutil.which("ffprobe")


def unity_exe() -> str:
    """The editor for the render project: SHOT_UNITY_EXE, else the version in ProjectVersion.txt, else any Unity 6."""
    env = os.environ.get("SHOT_UNITY_EXE")
    if env:
        return env
    want = None
    pv = STUDIO / "ProjectSettings" / "ProjectVersion.txt"
    if pv.exists():
        for line in pv.read_text().splitlines():
            if line.startswith("m_EditorVersion:"):
                want = line.split(":", 1)[1].strip()
    roots = [Path(r"D:\Unity\Editors"), Path(r"C:\Program Files\Unity\Hub\Editor"), Path(r"D:\Program Files\Unity\Hub\Editor")]
    found = []
    for r in roots:
        if r.is_dir():
            for d in sorted(r.iterdir()):
                exe = d / "Editor" / "Unity.exe"
                if exe.exists():
                    found.append((d.name, exe))
    for name, exe in found:
        if want and name == want:
            return str(exe)
    six = [e for n, e in found if n.startswith("6000.0")] or [e for n, e in found if n.startswith("6000")]
    if six:
        return str(six[0])
    raise RuntimeError("no Unity 6 editor found; set SHOT_UNITY_EXE")


def assets_ready() -> list[str]:
    """Missing starter asset packs (empty when everything is downloaded)."""
    sys.path.insert(0, str(STUDIO))
    try:
        import fetch_render_assets
        return fetch_render_assets.missing()
    finally:
        sys.path.remove(str(STUDIO))


def ensure_assets(log=_log) -> None:
    miss = assets_ready()
    if miss:
        log(f"downloading starter cast and stages ({len(miss)} packs, CC0)...")
        sys.path.insert(0, str(STUDIO))
        try:
            import fetch_render_assets
            fetch_render_assets.fetch(only=set(miss), log=log)
        finally:
            sys.path.remove(str(STUDIO))


def list_cast() -> dict:
    out = {k: {"look": v["look"], "height_m": v["height"], "license": v["license"]} for k, v in _all_cast().items()}
    mix = STUDIO / "Assets" / "Characters" / "Mixamo"
    if mix.is_dir():  # local-only test characters; never redistributed
        for f in sorted(mix.glob("*.fbx")):
            out["mixamo:" + f.stem] = {"look": "local Mixamo character (testing only, not redistributable)",
                                       "height_m": 1.75, "license": "Mixamo (local only)"}
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Motions: Promptimate results -> clip segments placed in the world

def _motion_meta(name: str) -> dict:
    p = OUTPUT / name / "meta.json"
    if not p.exists():
        raise ValueError(f"unknown motion {name!r} (no {p}); generate it with generate_motion or call list_motions")
    return json.loads(p.read_text())


def _kimodo_source(name: str) -> Path:
    d = OUTPUT / name
    for c in [d / f"{name}.kimodo", *d.glob("*.kimodo")]:
        if c.exists():
            return c
    meta = _motion_meta(name)
    f = meta.get("files", {})
    for k in ("kimodo", "unity_asset"):
        if f.get(k) and Path(f[k]).exists():
            return Path(f[k])
    raise ValueError(f"motion {name!r} has no .kimodo file")


def _stage_clip(src: Path, name: str) -> str:
    """Copies a .kimodo into the render project (imported as a Humanoid clip by com.promptimate.unity)."""
    GENERATED.mkdir(parents=True, exist_ok=True)
    dst = GENERATED / f"{name}.kimodo"
    if not dst.exists() or dst.stat().st_size != src.stat().st_size or dst.stat().st_mtime < src.stat().st_mtime:
        tmp = dst.with_suffix(".tmp")
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    return f"Assets/Promptimate/Generated/{name}.kimodo"


def _end_placement(name: str) -> tuple[float, float, float]:
    """Where a clip ends, in its own space: (hips x, hips z, heading deg), Kimodo convention."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import constraints as C
    import motion as M
    root, rot = M.load(OUTPUT / name)
    x, z, h = C.frame_placement(root, rot, len(root) - 1)
    return x, z, math.degrees(h)


def _duration(name: str) -> float:
    m = _motion_meta(name)
    st = m.get("stats", {})
    if st.get("duration_s"):
        return float(st["duration_s"])
    return sum(s["frames"] for s in m["segments"]) / 30.0


def idle_clip() -> str:
    """A 2 s clip of Promptimate's shared idle standing pose (the start_pose/end_pose='idle' pose), for actors who
    only stand there."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import constraints as C
    import motion as M
    import numpy as np
    import postprocess
    d = CACHE / "poses" / "idle_pose"
    target = d / "idle_pose.kimodo"
    if not target.exists():
        root, rot = C.load_pose("idle")
        n = 60
        postprocess.save(d, np.repeat(np.asarray(root, np.float32).reshape(1, 3), n, 0),
                         np.repeat(np.asarray(rot, np.float32)[None], n, 0))
        M.write_kimodo_file(d, target, "a person stands still (idle pose)", {"loop": True, "inPlace": True})
    return _stage_clip(target, "idle_pose")


def _rot(yaw_deg: float, x: float, z: float) -> tuple[float, float]:
    a = math.radians(yaw_deg)  # Unity: Quaternion.Euler(0, yaw, 0) * (x, 0, z)
    return math.cos(a) * x + math.sin(a) * z, -math.sin(a) * x + math.cos(a) * z


def resolve_segments(motions: list[str], pos: tuple[float, float], yaw: float, start: float = 0.0,
                     loop_last: bool = False, clips: list | None = None) -> tuple[list[dict], float]:
    """Unity clip segments for motions played back to back, and the time the last one ends. Each clip is placed where
    the previous one ended (what continue_from's meta 'chain' records), so walk -> stop -> wave plays as one
    continuous performance. start > 0 holds the first frame until then; start < 0 skips into the first clip."""
    segs = []
    px, pz, pyaw = pos[0], pos[1], yaw
    T = start
    for k, name in enumerate(motions):
        if k > 0:
            ex, ez, eh = _end_placement(motions[k - 1])
            ux, uz = _rot(pyaw, -ex, ez)       # Kimodo (x = character's left) -> Unity (x right)
            px, pz, pyaw = px + ux, pz + uz, pyaw - eh
        dur = _duration(name)
        if clips is not None:  # where each clip sits on the shot clock and in the world (props / seats use it)
            clips.append({"name": name, "t0": T, "dur": dur, "pos": (px, pz), "yaw": pyaw})
        base = {"clip": _stage_clip(_kimodo_source(name), name), "speed": 1, "loop": False,
                "pos": [round(px, 4), 0, round(pz, 4)], "yaw": round(pyaw, 3)}
        last = k == len(motions) - 1
        if T + dur > 0 or last:
            if k == 0 and T > 0:
                segs.append(dict(base, start=0.0, clipStart=0.0, speed=0))   # hold the first frame
            segs.append(dict(base, start=round(max(T, 0.0), 4), clipStart=round(max(0.0, -T), 4),
                             loop=bool(loop_last and last)))
        T += dur
    return segs, T


# ---------------------------------------------------------------------------------------------------------------------
# Staging

def _vec(a) -> tuple[float, float]:
    if isinstance(a, dict):
        return float(a.get("x", 0)), float(a.get("z", 0))
    return float(a[0]), float(a[-1] if len(a) == 2 else a[2])


def _yaw_to(src: tuple[float, float], dst: tuple[float, float]) -> float:
    return math.degrees(math.atan2(dst[0] - src[0], dst[1] - src[1]))


def stage(actors: list[dict]) -> dict[str, dict]:
    """World placement for each actor from simple relations. Each actor may have:
      at: [x, z]                                  explicit position (metres)
      yaw: deg                                    explicit facing (0 = +Z, away from the audience; 180 = toward it)
      near: "A", distance: 1.5, side: front|behind|left|right   relative to A (A's own front/left/...)
      face: "B" | "audience" | "away" | "left" | "right"  turn to face an actor or a direction
      enter_from: left|right|back|front, distance: 4  start off to that side of where they end up ('to'/'at'),
                                                      walking in; returns the root_path for generate_motion
    Returns {id: {"pos": [x, z], "yaw": deg, "root_path"?: [...], "notes": [...]}}."""
    out: dict[str, dict] = {}
    pending = list(actors)
    for _ in range(len(actors) + 2):
        rest = []
        for a in pending:
            aid = a.get("id") or f"actor{len(out)}"
            ref = a.get("near")
            if ref and ref not in out:
                rest.append(a)
                continue
            notes = []
            yaw = float(a.get("yaw", 180.0))
            if "at" in a:
                pos = _vec(a["at"])
            elif ref:
                r = out[ref]
                d = float(a.get("distance", 1.5))
                side = a.get("side", "front")
                lx, lz = {"front": (0, d), "behind": (0, -d), "left": (-d, 0), "right": (d, 0)}[side]
                ox, oz = _rot(r["yaw"], lx, lz)
                pos = (r["pos"][0] + ox, r["pos"][1] + oz)
                notes.append(f"{d} m {side} of {ref}")
            else:
                pos = (0.0, 0.0)
            face = a.get("face")
            if face:
                if face in out:
                    yaw = _yaw_to(pos, tuple(out[face]["pos"]))
                elif face in ("audience", "camera"):
                    yaw = 180.0
                elif face == "away":
                    yaw = 0.0
                elif face == "left":
                    yaw = -90.0
                elif face == "right":
                    yaw = 90.0
                else:
                    later = next((b for b in actors if b.get("id") == face), None)
                    if later is not None and "at" in later:
                        yaw = _yaw_to(pos, _vec(later["at"]))
            entry = {"pos": [round(pos[0], 3), round(pos[1], 3)], "yaw": round(yaw, 2), "notes": notes}
            if a.get("enter_from"):
                entry.update(_entry_path(pos, yaw, a["enter_from"], float(a.get("enter_distance", a.get("distance_in", 4.0))),
                                         float(a.get("walk_seconds", 0) or 0), float(a.get("total_seconds", 0) or 0)))
            out[aid] = entry
        pending = rest
        if not pending:
            break
    if pending:
        raise ValueError("couldn't resolve 'near' references: " + ", ".join(a.get("id", "?") for a in pending))
    # Second pass: 'face' toward actors resolved later.
    for a in actors:
        f = a.get("face")
        if f and f in out and a.get("id") in out and a.get("yaw") is None:
            me = out[a["id"]]
            if not me.get("root_path"):  # a walk-in keeps facing its walk direction at the start
                me["yaw"] = round(_yaw_to(tuple(me["pos"]), tuple(out[f]["pos"])), 2)
    return out


def _entry_path(end: tuple[float, float], end_yaw: float, side: str, dist: float, walk_s: float, total_s: float) -> dict:
    """An entrance: start `dist` metres off to `side` (audience view: left = -X), walk to `end`. Returns the world start
    placement and the root_path (in the clip's own frame, Promptimate convention) to pass to generate_motion."""
    dx, dz = {"left": (-1, 0), "right": (1, 0), "back": (0, 1), "front": (0, -1)}[side]
    start = (end[0] + dx * dist, end[1] + dz * dist)
    yaw = _yaw_to(start, end)  # start facing the walk direction
    walk_s = walk_s or max(1.5, dist / 1.25)  # comfortable walking speed ~1.25 m/s
    total_s = max(total_s, walk_s + 1.0)
    # The clip starts at its origin facing +Z (its own frame); in that frame the end point is straight ahead.
    path = [{"t": 0.0, "x": 0.0, "z": 0.0}, {"t": round(walk_s, 2), "x": 0.0, "z": round(dist, 3)},
            {"t": round(total_s, 2), "x": 0.0, "z": round(dist, 3)}]
    return {"pos": [round(start[0], 3), round(start[1], 3)], "yaw": round(yaw, 2), "end_pos": [round(end[0], 3), round(end[1], 3)],
            "end_yaw_wanted": round(end_yaw, 2), "root_path": path,
            "generate_hint": {"segments": [{"prompt": "a person walks forward", "seconds": round(walk_s, 2)},
                                           {"prompt": "a person stops and stands still", "seconds": round(total_s - walk_s, 2)}],
                              "root_path": path},
            "notes": [f"enters from the {side}: {dist} m walk in {walk_s:.1f} s, then holds"]}


def world_to_clip(point, clip_pos, clip_yaw: float) -> tuple[float, float]:
    """A world point [x, z] in a clip's own frame (generate_motion's root_path / seat convention: +Z = where the clip
    starts facing, +X = the character's left), for a clip that starts at clip_pos facing clip_yaw (Unity degrees)."""
    x, z = _vec(point)
    ux, uz = _rot(-clip_yaw, x - clip_pos[0], z - clip_pos[1])
    return round(-ux, 4), round(uz, 4)


def chain_end(motions: list[str], pos, yaw: float) -> tuple[tuple[float, float], float]:
    """World placement ((x, z), yaw) where a continue_from chain placed at pos/yaw ends: where the next clip starts."""
    clips: list[dict] = []
    resolve_segments(list(motions), _vec(pos), float(yaw), 0.0, clips=clips)
    c = clips[-1]
    ex, ez, eh = _end_placement(c["name"])
    ux, uz = _rot(c["yaw"], -ex, ez)
    return (c["pos"][0] + ux, c["pos"][1] + uz), c["yaw"] - eh


def seat_option(hips_world, face_yaw: float, clip_pos, clip_yaw: float, t: list[float], height: float = 0.45,
                furniture: str = "bench") -> dict:
    """generate_motion `seat` for a clip starting at clip_pos/clip_yaw (world) that should sit with its hips at
    hips_world facing face_yaw (world, Unity degrees) during t = [start, end] (clip seconds)."""
    x, z = world_to_clip(hips_world, clip_pos, clip_yaw)
    return {"t": list(t), "height": height, "x": x, "z": z, "heading_deg": round(-((face_yaw - clip_yaw + 180) % 360 - 180), 2),
            "furniture": furniture}


def seat_hips(furniture: dict, offset_x: float = 0.0) -> tuple[float, float]:
    """Where the hips go on a furniture entry {type, at, yaw} (yaw = the way a seated person faces), offset_x metres
    along the seat to the sitter's right (two people on one bench: -0.38 and +0.38)."""
    cat = FURNITURE.get(furniture.get("type", "bench"), {})
    cx, cz = _vec(furniture["at"])
    a = math.radians(float(furniture.get("yaw", 0.0)))
    fw, right = (math.sin(a), math.cos(a)), (math.cos(a), -math.sin(a))
    back = cat.get("seat_back", 0.05)
    return round(cx - fw[0] * back + right[0] * offset_x, 4), round(cz - fw[1] * back + right[1] * offset_x, 4)


def path_to_root_path(world_points: list, start_yaw: float, seconds: list[float] | None = None, speed: float = 1.25) -> list[dict]:
    """World waypoints [[x, z], ...] (first = where the clip starts) -> generate_motion root_path in the clip's own
    frame (origin, facing +Z = start_yaw in the world; Promptimate +X = the character's left)."""
    pts = [_vec(p) for p in world_points]
    x0, z0 = pts[0]
    out, t = [], 0.0
    for i, (x, z) in enumerate(pts):
        if i:
            t = seconds[i] if seconds else t + math.dist(pts[i - 1], pts[i]) / speed
        ux, uz = _rot(-start_yaw, x - x0, z - z0)   # world -> clip-local (Unity axes)
        out.append({"t": round(t, 2), "x": round(-ux, 3), "z": round(uz, 3)})  # Unity x right -> Promptimate x left
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Spec resolution

def load_cast_file(cast_file) -> dict:
    """A cast file keeps the same characters across episodes: {"roles": {"maya": {"cast": "woman_casual", "height":
    1.66, "build": 1.0, "props": ["phone"], "look": "..."}}}. `cast` is a catalogue name (or `model` a path); props are
    what the character always carries (merged with inferred / per-shot props). Path, dict or None."""
    if not cast_file:
        return {}
    if isinstance(cast_file, dict):
        d = cast_file
    else:
        f = Path(cast_file)
        if not f.is_absolute():
            f = ROOT / f
        d = json.loads(f.read_text(encoding="utf-8"))
    return d.get("roles", d)


def _all_cast() -> dict:
    return {**CAST, **CAST_EXTRA}


def _cast_entry(a: dict, roles: dict | None = None) -> dict:
    c = a.get("cast")
    role = (roles or {}).get(c) if c else None
    if role:  # a cast-file role: its own settings, actor keys still override
        a = {**{k: v for k, v in role.items() if k not in ("props", "look")}, **{k: v for k, v in a.items() if k != "cast"},
             "cast": role.get("cast")}
        c = a.get("cast")
    if a.get("model"):
        e = {"model": a["model"], "skin": a.get("skin"), "height": float(a.get("height", 1.75))}
    else:
        if not c:
            c = "businessman"
        if c.startswith("mixamo:"):
            e = {"model": f"Assets/Characters/Mixamo/{c.split(':', 1)[1]}.fbx", "height": float(a.get("height", 1.75))}
        else:
            cat = _all_cast()
            if c not in cat:
                raise ValueError(f"unknown cast {c!r}; one of {', '.join(list_cast())} (or give model: 'Assets/....fbx|.glb', "
                                 f"or a role from cast_file)")
            e = dict(cat[c])
            if a.get("height"):
                e["height"] = float(a["height"])
    if a.get("build"):
        e["build"] = float(a["build"])
    e["role_props"] = list(role.get("props") or []) if role else []
    # Stylised hand meshes are much bigger than human hands (the finger bones aren't): props scale with them.
    e.setdefault("prop_scale", 1.35 if ("/Quaternius/" in e["model"] or "/Kenney/" in e["model"]) else 1.0)
    if a.get("prop_scale"):
        e["prop_scale"] = float(a["prop_scale"])
    return e


# --- props ----------------------------------------------------------------------------------------------------------

PROP_WORDS = [  # (prop, regex on a lower-case clause); the first prop that matches a clause wins
    ("phone", r"\b(phone|smartphone|cell ?phone|mobile|texts?|texting|calls? (someone|somebody)|on a call)\b"),
    ("coffee", r"\b(coffee|takeaway|to-go cup)\b"),
    ("cup", r"\b(cup|mug|tea|drinks?|drinking|sips?|sipping)\b"),
    ("umbrella", r"\bumbrella\b"),
    ("flashlight", r"\b(flashlight|flash light|torch)\b"),
    ("sword", r"\b(sword|blade|katana|sabre|saber)\b"),
    ("book", r"\b(book|reads?|reading|novel)\b"),
    ("briefcase", r"\b(briefcase|suitcase)\b"),
    ("bag", r"\b(bag|handbag|purse|shopping bag)\b"),
    ("stick", r"\b(cane|walking stick|stick|staff)\b"),
]


def infer_props(clips: list[dict], merge_gap: float = 1.5) -> list[dict]:
    """Props implied by the motion prompts ("a person holds a phone to their ear" -> phone, right hand) over the shot
    time of the segments that mention them; the hand comes from the text (hands.py's side words), default right.
    Spans of the same prop closer than merge_gap seconds are joined, so a prop doesn't blink between clips."""
    import re
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hands
    found = []
    for c in clips:
        try:
            meta = _motion_meta(c["name"])
        except ValueError:
            continue
        given = meta.get("prompts_as_given") or [sg["prompt"] for sg in meta["segments"]]
        total = sum(sg["frames"] for sg in meta["segments"]) or 1
        scale = c["dur"] * 30.0 / total
        off = 0
        for sg, text in zip(meta["segments"], given):
            low = (text or sg["prompt"]).lower()
            for name, rx in PROP_WORDS:
                m = re.search(rx, low)
                if m:
                    side = hands._side_near(low, m.start()) or "right"
                    if side == "both":
                        side = "right"
                    found.append({"prop": name, "hand": side, "t": [round(c["t0"] + off * scale / 30.0, 3),
                                                                     round(c["t0"] + (off + sg["frames"]) * scale / 30.0, 3)],
                                  "why": f"'{m.group(0)}' in {c['name']}"})
                    break
            off += sg["frames"]
    out: list[dict] = []
    for f in sorted(found, key=lambda f: (f["prop"], f["hand"], f["t"][0])):
        prev = out[-1] if out else None
        if prev and prev["prop"] == f["prop"] and prev["hand"] == f["hand"] and f["t"][0] - prev["t"][1] <= merge_gap:
            prev["t"][1] = max(prev["t"][1], f["t"][1])
        else:
            out.append(dict(f))
    return out


def _prop_entry(p, actor_start: float, scale: float = 1.0) -> dict:
    if isinstance(p, str):
        p = {"prop": p}
    name = p.get("prop") or p.get("type") or p.get("id")
    if p.get("model"):
        cat = {"model": p["model"], "grip": "power", "size": 0.3, "grip_at": 0.5}
    elif name in PROPS:
        cat = PROPS[name]
    else:
        raise ValueError(f"unknown prop {name!r}; one of {', '.join(PROPS)} (or give model: 'Assets/....glb')")
    if p.get("t") is not None:
        t0, t1 = float(p["t"][0]), float(p["t"][1])
    elif p.get("chain_t") is not None:
        t0, t1 = float(p["chain_t"][0]) + actor_start, float(p["chain_t"][1]) + actor_start
    else:
        t0, t1 = -1e6, 1e6
    hand = (p.get("hand") or cat.get("hand") or "right").lower()
    if hand not in ("left", "right"):
        raise ValueError(f"prop hand must be left or right, got {hand!r}")
    out = {"id": p.get("id") or name, "model": cat["model"], "hand": hand, "start": round(t0, 3), "end": round(t1, 3),
           "grip": p.get("grip", cat.get("grip", "power")), "size": float(p.get("size", cat.get("size", 0.3) * scale)),
           "gripAt": float(p.get("grip_at", cat.get("grip_at", 0.5))),
           "modelRot": [float(v) for v in p.get("model_rot", cat.get("model_rot", [0, 0, 0]))],
           "offset": [float(v) for v in p.get("offset", cat.get("offset", [0, 0, 0]))],
           "rot": [float(v) for v in p.get("rot", cat.get("rot", [0, 0, 0]))],
           "fingers": p.get("fingers", cat.get("fingers", "grip")), "light": p.get("light", cat.get("light", "")) or ""}
    if p.get("tint") or cat.get("tint"):
        out["tint"] = [float(v) for v in (p.get("tint") or cat.get("tint"))]
    return out


# --- furniture and seats --------------------------------------------------------------------------------------------

def _furniture_entry(f: dict, i: int) -> dict:
    typ = f.get("type") or f.get("furniture") or "bench"
    if typ not in FURNITURE and not f.get("model"):
        raise ValueError(f"unknown furniture type {typ!r}; one of {', '.join(FURNITURE)} (or give model: 'Assets/....fbx')")
    cat = FURNITURE.get(typ, {})
    x, z = _vec(f.get("at", [0, 0]))
    out = {"id": f.get("id") or f"{typ}{i}", "model": f.get("model") or cat["model"], "kit": f.get("kit", cat.get("kit", "")),
           "scale": float(f.get("scale", cat.get("scale", 1.0))), "pos": [round(x, 4), 0.0, round(z, 4)],
           "yaw": float(f.get("yaw", 0.0)) + float(cat.get("front_yaw", 0.0)), "seatHeight": float(f.get("seat_height", cat.get("seat_height", 0.0)) or 0.0),
           "anchor": f.get("anchor", cat.get("anchor", "center")), "stretch": float(f.get("stretch", 1.0))}
    for k in ("size", "color", "lamp"):
        v = f.get(k, cat.get(k))
        if v is not None:
            out[k] = [float(u) for u in v]
    out["_type"] = typ
    out["_front_yaw"] = float(f.get("yaw", 0.0))  # the way a seated person faces
    return out


def _seat_from_clip(c: dict) -> dict | None:
    """A clip generated with generate_motion's `seat` option: where (world) and when (shot time) it sits, from the
    clip's actual hips over the seated span, plus the facing there."""
    try:
        meta = _motion_meta(c["name"])
    except ValueError:
        return None
    seat = (meta.get("options") or {}).get("seat")
    if not seat:
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import constraints as Cn
    import motion as M
    root, rot = M.load(OUTPUT / c["name"])
    a = max(0, min(len(root) - 1, round(seat["t"][0] * 30)))
    b = max(a, min(len(root) - 1, round(seat["t"][1] * 30)))
    mid = (a + b) // 2
    hx, hz, h = Cn.frame_placement(root, rot, mid)
    hx, hz = float(root[a:b + 1, 0].mean()), float(root[a:b + 1, 2].mean())
    ux, uz = _rot(c["yaw"], -hx, hz)
    wyaw = c["yaw"] - math.degrees(h)
    return {"t": [round(c["t0"] + seat["t"][0], 3), round(c["t0"] + seat["t"][1], 3)],
            "hips": (c["pos"][0] + ux, c["pos"][1] + uz), "yaw": wyaw, "height": float(seat.get("height", 0.45)),
            "type": seat.get("furniture") or "bench", "clip": c["name"]}


def _place_seats(actor_id: str, auto: list[dict], furniture: list[dict]) -> list[dict]:
    """Seat spans for an actor: each auto seat sits on explicit furniture within 0.6 m of where it belongs, or on
    furniture already added for another seat (shared bench), else new furniture of the seat's type is added there."""
    out = []
    for s in auto:
        fw = (math.sin(math.radians(s["yaw"])), math.cos(math.radians(s["yaw"])))
        back = FURNITURE.get(s["type"], {}).get("seat_back", 0.05)
        cx, cz = s["hips"][0] + fw[0] * back, s["hips"][1] + fw[1] * back
        best = None
        for f in furniture:
            d = math.dist((cx, cz), (f["pos"][0], f["pos"][2]))
            limit = 0.6 if not f.get("_auto") else 1.2
            same = not f.get("_auto") or (f["_type"] == s["type"] and abs((f["_front_yaw"] - s["yaw"] + 180) % 360 - 180) < 35)
            if d < limit and same and (best is None or d < best[0]):
                best = (d, f)
        if best is None:
            f = _furniture_entry({"type": s["type"], "at": [cx, cz], "yaw": s["yaw"], "seat_height": s["height"],
                                  "id": f"seat_{actor_id}_{len(furniture)}"}, len(furniture))
            f["_auto"] = True
            furniture.append(f)
        else:
            f = best[1]
        out.append({"furniture": f["id"], "start": s["t"][0], "end": s["t"][1], "_clip": s["clip"]})
    return out


def resolve(spec: dict) -> dict:
    """User-level shot spec -> the ShotSpec JSON the Unity renderer reads."""
    aspect = spec.get("aspect", "9:16")
    if aspect not in ASPECTS:
        raise ValueError(f"aspect must be one of {list(ASPECTS)}")
    w, h = ASPECTS[aspect]
    res = spec.get("resolution")
    if res:
        if isinstance(res, str) and res.endswith("p"):
            short = int(res[:-1])
            scale = short / min(w, h)
            w, h = int(round(w * scale / 2) * 2), int(round(h * scale / 2) * 2)
        elif isinstance(res, (list, tuple)):
            w, h = int(res[0]), int(res[1])
    fps = int(spec.get("fps", 30))
    if not 12 <= fps <= 60:
        raise ValueError("fps must be 12-60")
    stage_name = spec.get("stage", "street")
    if stage_name not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}")
    light = spec.get("lighting", "day")
    light = dict(light) if isinstance(light, dict) else {"preset": light}
    if spec.get("weather"):
        light.setdefault("weather", spec["weather"])
    if light.get("preset", "day") not in LIGHTING:
        raise ValueError(f"lighting must be one of {LIGHTING}")
    if (light.get("weather") or "") not in WEATHER:
        raise ValueError(f"weather must be one of {WEATHER}")
    actors_in = spec.get("actors") or []
    if not actors_in:
        raise ValueError("need at least one actor")
    roles = load_cast_file(spec.get("cast_file"))
    for i, a in enumerate(actors_in):
        a.setdefault("id", "ABCDEFGH"[i] if i < 8 else f"actor{i}")
    placed = stage(actors_in)
    furniture = [_furniture_entry(f, i) for i, f in enumerate(spec.get("furniture") or [])]
    actors, longest = [], 0.0
    for a in actors_in:
        ce = _cast_entry(a, roles)
        p = placed[a["id"]]
        motions = a.get("motion") or a.get("motions") or []
        if isinstance(motions, str):
            motions = [motions]
        pos2, yaw = tuple(p["pos"]), float(p["yaw"])
        clips: list[dict] = []
        a_start = float(a.get("start", a.get("time_offset", 0.0)))
        if motions:
            unity_segs, end = resolve_segments(motions, pos2, yaw, a_start, loop_last=bool(a.get("loop", False)), clips=clips)
            longest = max(longest, end)
        else:
            unity_segs = [{"clip": idle_clip(), "start": 0.0, "clipStart": 0.0, "speed": 1, "loop": True,
                           "pos": [pos2[0], 0, pos2[1]], "yaw": yaw}]
        # Props: explicit list (+ "auto" inside it), the role's own props, else inferred from the prompts.
        given = a.get("props")
        plist = list(given) if isinstance(given, list) else ([] if given is None else [given])
        auto = given is None or given == "auto" or "auto" in plist
        plist = [q for q in plist if q != "auto"]
        inferred = infer_props(clips) if auto else []
        names_given = {(q if isinstance(q, str) else (q.get("prop") or q.get("id"))) for q in plist}
        plist += [r for r in ce["role_props"] if (r if isinstance(r, str) else r.get("prop")) not in names_given]
        props = [_prop_entry(q, a_start, ce["prop_scale"]) for q in plist]
        taken = {(q["id"], q["hand"]) for q in props}
        busy_hands = {q["hand"] for q in props if q["start"] < -1e5}
        for q in inferred:
            if (q["prop"], q["hand"]) in taken or q["hand"] in busy_hands:
                continue
            e = _prop_entry({"prop": q["prop"], "hand": q["hand"], "t": q["t"]}, a_start, ce["prop_scale"])
            e["_why"] = q["why"]
            props.append(e)
        # Seats: explicit `sit` entries plus clips generated with the seat option.
        seats = []
        for st in a.get("sit") or []:
            t0, t1 = st["t"] if st.get("t") is not None else [st["chain_t"][0] + a_start, st["chain_t"][1] + a_start]
            seats.append({"furniture": st["on"], "start": float(t0), "end": float(t1)})
        if a.get("auto_seat", True):
            auto_seats = [x for x in (_seat_from_clip(c) for c in clips) if x]
            seats += _place_seats(a["id"], auto_seats, furniture)
        actor = {"id": a["id"], "model": ce["model"], "skin": ce.get("skin") or "", "height": ce["height"],
                 "pos": [pos2[0], 0, pos2[1]], "yaw": yaw, "segs": unity_segs,
                 "footIK": bool(a.get("foot_ik", True)), "grounding": bool(a.get("grounding", True)),
                 "_motions": motions}
        if ce.get("build"):
            actor["build"] = ce["build"]
        if clips and a.get("metric_travel", True):  # root motion in metres whatever the character's size
            best = max(clips, key=lambda c: math.hypot(*_end_placement(c["name"])[:2]))
            dist = math.hypot(*_end_placement(best["name"])[:2])
            idx = next((i for i, sg in enumerate(unity_segs) if Path(sg["clip"]).stem == best["name"] and sg.get("speed", 1) != 0), None)
            if idx is not None and dist >= 0.3:
                actor["travelCal"] = [idx, round(dist, 4)]
        if props:
            actor["props"] = props
        if seats:
            actor["seats"] = [{k: v for k, v in st.items() if not k.startswith("_")} for st in seats]
        actors.append(actor)
    ids = {f["id"] for f in furniture}
    for a in actors:
        for st in a.get("seats", []):
            if st["furniture"] not in ids:
                raise ValueError(f"actor {a['id']} sits on unknown furniture {st['furniture']!r}; furniture ids: {sorted(ids)}")
    seconds = float(spec.get("seconds") or min(max(longest, 2.0), 12.0))
    if not 0.5 <= seconds <= 30:
        raise ValueError("seconds must be 0.5-30")
    for a in actors:  # seated spans: join back-to-back clips on the same seat, drop spans outside this shot
        merged = []
        for st in sorted(a.get("seats", []), key=lambda q: q["start"]):
            if merged and merged[-1]["furniture"] == st["furniture"] and st["start"] - merged[-1]["end"] < 0.25:
                merged[-1]["end"] = max(merged[-1]["end"], st["end"])
            else:
                merged.append(dict(st))
        merged = [st for st in merged if st["end"] > 0.05 and st["start"] < seconds - 0.05]
        if merged:
            a["seats"] = merged
        else:
            a.pop("seats", None)
    cam = spec.get("camera", "medium")
    cam = cam if isinstance(cam, dict) else {"preset": cam}
    if cam.get("preset", "medium") not in CAMERAS:
        raise ValueError(f"camera preset must be one of {CAMERAS}")
    cam_out = {"preset": cam.get("preset", "medium"), "subject": cam.get("subject") or actors[0]["id"],
               "target": cam.get("target") or "", "side": cam.get("side", "auto"),
               "fov": float(cam.get("fov", 0)), "distance": float(cam.get("distance", 1.0)),
               "height": float(cam.get("height", -1)), "yawOffset": float(cam.get("yaw_offset", 0)),
               "amount": float(cam.get("amount", 1.0)), "orbitDeg": float(cam.get("orbit_deg", 0)),
               "follow": cam.get("follow", ""), "handheld": float(cam.get("handheld", 0))}
    for k in ("pos", "look_at", "end_pos", "end_look_at"):
        if cam.get(k) is not None:
            cam_out[{"look_at": "lookAt", "end_pos": "endPos", "end_look_at": "endLookAt"}.get(k, k)] = [float(v) for v in cam[k]]
    quality = spec.get("quality", "final")
    lighting = {"preset": light.get("preset", "day"), "exposure": float(light.get("exposure", 0))}
    if light.get("key_yaw") is not None:
        lighting["keyYaw"] = float(light["key_yaw"])
    if light.get("weather"):
        lighting["weather"] = light["weather"]
        lighting["weatherAmount"] = float(light.get("weather_amount", 1.0))
    if light.get("rim") is not None:
        lighting["rim"] = float(light["rim"])
    out = {"id": spec.get("name") or "shot", "width": w, "height": h, "fps": fps, "seconds": round(seconds, 3),
           "supersample": {"draft": 1.0, "final": 1.5, "high": 2.0}.get(quality, 1.5),
           "stage": stage_name, "seed": int(spec.get("seed", 0)), "lighting": lighting,
           "actors": actors, "camera": cam_out, "reportEvery": 3, "format": "jpg" if quality == "draft" else "png",
           "_aspect": aspect, "_quality": quality}
    if furniture:
        out["furniture"] = [{k: v for k, v in f.items() if not k.startswith("_")} for f in furniture]
        out["_furniture_auto"] = [f["id"] for f in furniture if f.get("_auto")]
    if spec.get("practicals"):
        out["practicals"] = [_practical(q) for q in spec["practicals"]]
    return out


def _practical(q: dict) -> dict:
    o = {"pos": [float(v) for v in q["pos"]], "intensity": float(q.get("intensity", 6)), "range": float(q.get("range", 8)),
         "type": q.get("type", "point"), "angle": float(q.get("angle", 100)), "glow": bool(q.get("glow", True)),
         "shadows": bool(q.get("shadows", False))}
    if q.get("color"):
        o["color"] = [float(v) for v in q["color"]]
    if q.get("dir"):
        o["dir"] = [float(v) for v in q["dir"]]
    return o


# ---------------------------------------------------------------------------------------------------------------------
# Warm Unity server

def _heartbeat() -> dict | None:
    hb = QUEUE / "heartbeat.json"
    try:
        d = json.loads(hb.read_text())
    except Exception:
        return None
    if time.time() - hb.stat().st_mtime > 8 or d.get("state") == "stopped":
        return None
    return d


def server_status() -> dict:
    hb = _heartbeat()
    return {"running": hb is not None, **(hb or {}), "queue": str(QUEUE), "project": str(STUDIO)}


def ensure_server(timeout: float = 420, log=_log) -> dict:
    """Starts the batchmode render server if it isn't running (first start imports assets: a few minutes once)."""
    global _server_proc
    hb = _heartbeat()
    if hb:
        return hb
    QUEUE.mkdir(parents=True, exist_ok=True)
    for f in ("heartbeat.json", "stop.flag"):
        (QUEUE / f).unlink(missing_ok=True)
    env = os.environ.copy()
    tmp = env.get("TEMP") or str(ROOT / ".cache" / "tmp")
    if Path(r"D:\tmp").is_dir():
        tmp = r"D:\tmp"
    env["TEMP"] = env["TMP"] = tmp
    log_file = ROOT / "logs" / "shot_server.log"
    log_file.parent.mkdir(exist_ok=True)
    idle = os.environ.get("SHOT_SERVER_IDLE_S", "900")
    cmd = [unity_exe(), "-batchmode", "-projectPath", str(STUDIO), "-executeMethod", "ShotStudio.ShotServer.Run",
           "-queue", str(QUEUE), "-idle", idle, "-logFile", str(log_file)]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    _server_proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    env=env, creationflags=flags)
    log(f"starting Unity render server (pid {_server_proc.pid}); log: {log_file}")
    t0 = time.time()
    while time.time() - t0 < timeout:
        hb = _heartbeat()
        if hb:
            return hb
        if _server_proc.poll() is not None:
            text = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else ""
            errs = [l for l in text.splitlines() if "error CS" in l or "SHOT_ERROR" in l or "another Unity instance" in l
                    or "It looks like another" in l][:10]
            raise RuntimeError(f"Unity render server exited ({_server_proc.returncode}); is DemoStudio open in the editor? "
                               f"see {log_file}\n" + "\n".join(errs))
        time.sleep(0.5)
    raise RuntimeError(f"Unity render server didn't start in {timeout:.0f} s; see {log_file}")


def stop_server() -> None:
    QUEUE.mkdir(parents=True, exist_ok=True)
    (QUEUE / "stop.flag").write_text("stop")


def _submit(job: dict, timeout: float, log=_log) -> None:
    ensure_server(log=log)
    jid = job["id"]
    tmp = QUEUE / f"{jid}.tmp"
    tmp.write_text(json.dumps(job))
    done = QUEUE / f"{jid}.done.json"
    done.unlink(missing_ok=True)
    os.replace(tmp, QUEUE / f"{jid}.job.json")
    _wait(jid, timeout)


def _wait(jid: str, timeout: float) -> None:
    """Waits for a queued job's done file; raises on failure, a dead server or the timeout."""
    done = QUEUE / f"{jid}.done.json"
    t0 = time.time()
    while time.time() - t0 < timeout:
        if done.exists():
            try:
                res = json.loads(done.read_text())
            except json.JSONDecodeError:
                time.sleep(0.2)
                continue
            done.unlink(missing_ok=True)
            if not res.get("ok"):
                raise RuntimeError("render failed: " + res.get("error", "?")[:2000])
            return
        if _heartbeat() is None and not (QUEUE / f"{jid}.job.json").exists() and not (QUEUE / f"{jid}.running").exists():
            raise RuntimeError("Unity render server died while rendering; see logs/shot_server.log")
        time.sleep(0.25)
    raise RuntimeError(f"render timed out after {timeout:.0f} s")


# ---------------------------------------------------------------------------------------------------------------------
# Render, encode, preview, validate

def _key(job: dict) -> str:
    h = hashlib.sha1()
    h.update(json.dumps({k: v for k, v in job.items() if k not in ("outDir", "id")}, sort_keys=True).encode())
    h.update(str(VERSION).encode())
    deps = set()
    for a in job["actors"]:
        deps.add(STUDIO / a["model"])
        for s in a["segs"]:
            deps.add(STUDIO / s["clip"])
        for pr in a.get("props", []):
            if not pr["model"].startswith("procedural:"):
                deps.add(STUDIO / pr["model"])
    for f in job.get("furniture", []):
        if f["model"] != "box":
            deps.add(STUDIO / f["model"])
    for p in sorted(deps, key=str):
        try:
            st = p.stat()
            h.update(f"{p.name}:{st.st_size}:{int(st.st_mtime)}".encode())
        except FileNotFoundError:
            h.update(f"{p}:missing".encode())
    # renderer source: a change to the Unity scripts invalidates renders
    for f in sorted((STUDIO / "Assets" / "Editor" / "ShotStudio").glob("*.cs")):
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _prepare(spec: dict, force: bool, log=_log) -> dict:
    """Resolves a shot and its cache slot. Returns {"result": ...} for a cache hit, else the context to render it."""
    t0 = time.time()
    ensure_assets(log=log)
    job = resolve(json.loads(json.dumps(spec)))
    meta_actors = [{"id": a["id"], "motions": a.pop("_motions")} for a in job["actors"]]
    aspect, quality = job.pop("_aspect"), job.pop("_quality")
    auto_furniture = job.pop("_furniture_auto", [])
    inferred = [{"actor": a["id"], "prop": q["id"], "hand": q["hand"], "t": [q["start"], q["end"]], "why": q.pop("_why")}
                for a in job["actors"] for q in a.get("props", []) if "_why" in q]
    key = _key(job)
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (spec.get("name") or "shot"))[:40]
    out = CACHE / "renders" / f"{name}_{key}"
    mp4 = out / f"{name}.mp4"
    result_file = out / "result.json"
    if not force and result_file.exists() and mp4.exists():
        res = json.loads(result_file.read_text())
        res["cached"] = True
        try:  # validation is cheap and may have changed since the render: re-check from the stored report
            res["validation"] = validate(mp4, json.loads((out / "report.json").read_text()), job)
        except Exception:
            pass
        res["seconds_total"] = round(time.time() - t0, 2)
        return {"result": res}
    frames = out / "frames"
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    frames.mkdir(parents=True)
    job["id"] = f"{name}_{key}"
    job["outDir"] = str(frames).replace("\\", "/")
    (out / "shot.json").write_text(json.dumps(job, indent=1))
    return {"job": job, "out": out, "mp4": mp4, "frames": frames, "result_file": result_file, "aspect": aspect,
            "quality": quality, "meta_actors": meta_actors, "auto_furniture": auto_furniture, "inferred": inferred, "t0": t0,
            "n_frames": max(1, round(job["seconds"] * job["fps"]))}


def _finalize(c: dict, t_render: float, keep_frames: bool = False) -> dict:
    """Encode, contact sheet, validation and the cached result for a rendered shot."""
    job, out, mp4, frames, aspect, quality = c["job"], c["out"], c["mp4"], c["frames"], c["aspect"], c["quality"]
    report = json.loads((frames / "report.json").read_text())
    ext = "jpg" if job["format"] == "jpg" else "png"
    t2 = time.time()
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(job["fps"]), "-i", str(frames / f"f%05d.{ext}"),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "17" if quality != "draft" else "21", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(mp4)], check=True)
    t_encode = time.time() - t2
    sheet = contact_sheet(frames, report, out / "contact.png", ext, aspect)
    shutil.copyfile(frames / "report.json", out / "report.json")
    if not keep_frames:
        keep = {f"f{int(f['f']):05d}.{ext}" for f in _pick(report, 4)}
        for f in frames.glob(f"f*.{ext}"):
            if f.name not in keep:
                f.unlink()
    val = validate(mp4, report, job)
    res = {"mp4": str(mp4), "contact_sheet": str(sheet), "report": str(out / "report.json"), "shot_json": str(out / "shot.json"),
           "validation": val, "cached": False, "width": job["width"], "height": job["height"], "fps": job["fps"],
           "seconds": job["seconds"], "frames": c["n_frames"], "aspect": aspect, "quality": quality,
           "stage": job["stage"], "lighting": job["lighting"]["preset"], "camera": job["camera"]["preset"],
           "actors": [{"id": a["id"], "model": a["model"], "pos": a["pos"], "yaw": a["yaw"],
                       "segments": [{"clip": Path(s["clip"]).stem, "start": s["start"], "pos": s["pos"], "yaw": s["yaw"]} for s in a["segs"]],
                       "motions": m["motions"]} for a, m in zip(job["actors"], c["meta_actors"])],
           "timing_s": {"unity": round(t_render, 2), "encode": round(t_encode, 2), "unity_breakdown": report.get("timing")}}
    if c["inferred"]:
        res["props_inferred"] = c["inferred"]
    if job.get("furniture"):
        res["furniture"] = report.get("furniture", [])
        res["furniture_auto"] = c["auto_furniture"]
    res["seconds_total"] = round(time.time() - c["t0"], 2)
    c["result_file"].write_text(json.dumps(res, indent=1))
    return res


def render(spec: dict, *, force: bool = False, keep_frames: bool = False, log=_log) -> dict:
    """Render one shot. Returns {"mp4", "contact_sheet", "report", "validation", "cached", "seconds", ...}."""
    c = _prepare(spec, force, log)
    if "result" in c:
        return c["result"]
    with _lock:
        t1 = time.time()
        _submit(c["job"], timeout=240 + c["n_frames"] * 3.0, log=log)
        t_render = time.time() - t1
    return _finalize(c, t_render, keep_frames)


def render_many(specs: list[dict], *, force: bool = False, keep_frames: bool = False, workers: int = 4, log=_log) -> list[dict]:
    """Render a whole shot list. All uncached shots are queued on the warm Unity server at once (no round trip
    between shots), and each finished shot is encoded, contact-sheeted and validated on a thread pool while Unity
    renders the next one. Results come back in the order of `specs`; a failed shot returns {"error": ...}."""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    ctx = []
    for sp in specs:
        try:
            ctx.append(_prepare(sp, force, log))
        except Exception as e:  # a bad spec must not sink the others
            ctx.append({"result": {"error": f"{type(e).__name__}: {e}", "name": sp.get("name")}})
    todo = [c for c in ctx if "job" in c]
    results: dict[int, object] = {}
    with _lock, ThreadPoolExecutor(max(1, workers)) as pool:
        if todo:
            ensure_server(log=log)
        for c in todo:  # enqueue everything; the server takes jobs oldest first
            jid = c["job"]["id"]
            (QUEUE / f"{jid}.done.json").unlink(missing_ok=True)
            tmp = QUEUE / f"{jid}.tmp"
            tmp.write_text(json.dumps(c["job"]))
            os.replace(tmp, QUEUE / f"{jid}.job.json")
            time.sleep(0.02)  # distinct creation times keep the order
        prev = time.time()
        for c in todo:
            try:
                _wait(c["job"]["id"], timeout=240 + c["n_frames"] * 3.0)
                t_render = time.time() - prev
                prev = time.time()
                results[id(c)] = pool.submit(_finalize, c, t_render, keep_frames)
            except Exception as e:
                prev = time.time()
                results[id(c)] = {"error": f"{type(e).__name__}: {e}", "name": c["job"]["id"]}
        out = []
        for c in ctx:
            if "result" in c:
                out.append(c["result"])
                continue
            r = results[id(c)]
            try:
                out.append(r.result() if hasattr(r, "result") else r)
            except Exception as e:
                out.append({"error": f"{type(e).__name__}: {e}", "name": c["job"]["id"]})
    log(f"render_many: {len(specs)} shots ({len(todo)} rendered) in {time.time() - t0:.1f}s")
    return out


def _pick(report: dict, n: int) -> list[dict]:
    fr = report["frames"]
    if len(fr) <= n:
        return fr
    idx = [round(i * (len(fr) - 1) / (n - 1)) for i in range(n)]
    idx[0] = min(1, len(fr) - 1) if len(fr) > 2 else 0   # skip the very first frame (cut point)
    return [fr[i] for i in idx]


def contact_sheet(frames: Path, report: dict, out: Path, ext: str, aspect: str, n: int = 4) -> Path:
    """4 frames side by side with each character's projected box, frame time, and (9:16) the caption / platform-UI
    zone, so framing can be judged at a glance."""
    from PIL import Image, ImageDraw
    picks = _pick(report, n)
    ims = [Image.open(frames / f"f{int(p['f']):05d}.{ext}").convert("RGB") for p in picks]
    W, H = ims[0].size
    th = 640
    tw = round(W * th / H)
    sheet = Image.new("RGB", (tw * len(ims) + 8 * (len(ims) - 1), th + 26), (18, 18, 22))
    colors = [(255, 210, 60), (90, 200, 255), (255, 110, 160), (140, 255, 140), (200, 160, 255)]
    for i, (im, p) in enumerate(zip(ims, picks)):
        t = im.resize((tw, th), Image.LANCZOS)
        d = ImageDraw.Draw(t)
        if aspect == "9:16":
            y = round(th * (1330 / 1920))
            d.line([(0, y), (tw, y)], fill=(255, 80, 80), width=1)
            yt = round(th * (168 / 1920))
            d.line([(0, yt), (tw, yt)], fill=(255, 80, 80), width=1)
        for j, a in enumerate(p["actors"]):
            x0, y0, x1, y1 = a["bbox"]
            c = colors[j % len(colors)]
            x0, x1 = max(-0.02, min(1.02, x0)), max(-0.02, min(1.02, x1))
            y0, y1 = max(-0.02, min(1.02, y0)), max(-0.02, min(1.02, y1))
            if x1 <= x0 or y1 <= y0:
                continue
            d.rectangle([x0 * tw, (1 - y1) * th, x1 * tw, (1 - y0) * th], outline=c, width=2)
            d.text((max(2, x0 * tw + 3), max(2, (1 - y1) * th + 2)), a["id"], fill=c)
        sheet.paste(t, (i * (tw + 8), 0))
        ImageDraw.Draw(sheet).text((i * (tw + 8) + 4, th + 6), f"t={p['t']:.2f}s", fill=(220, 220, 220))
    sheet.save(out)
    return out


def probe(mp4: Path) -> dict:
    fp = _ffprobe()
    if not fp:
        return {}
    r = subprocess.run([fp, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                        "stream=width,height,nb_read_frames,avg_frame_rate:format=duration", "-of", "json", str(mp4)],
                       capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        s = d["streams"][0]
        num, den = s["avg_frame_rate"].split("/")
        return {"width": int(s["width"]), "height": int(s["height"]), "frames": int(s.get("nb_read_frames", 0)),
                "fps": round(int(num) / max(1, int(den)), 3), "duration_s": round(float(d["format"]["duration"]), 3)}
    except Exception:
        return {}


def validate(mp4: Path, report: dict, job: dict) -> dict:
    """Automatic checks: the file exists with the right resolution and length; every character is in frame (projected
    mesh vertices inside the image), not hidden behind the set, and on the ground (lowest mesh point near the floor);
    chained clips join without a jump."""
    fails, warns = [], []
    p = probe(mp4)
    want_frames = max(1, round(job["seconds"] * job["fps"]))
    if not mp4.exists() or mp4.stat().st_size < 10_000:
        fails.append("mp4 missing or empty")
    if p:
        if (p["width"], p["height"]) != (job["width"], job["height"]):
            fails.append(f"resolution {p['width']}x{p['height']} != {job['width']}x{job['height']}")
        if abs(p["frames"] - want_frames) > 1:
            fails.append(f"{p['frames']} frames, expected {want_frames}")
    per = {}
    cam = job["camera"]
    preset, subj, targ = cam["preset"], cam.get("subject"), cam.get("target")
    ids = [a["id"] for a in job["actors"]]
    if preset in ("wide", "top_down", "explicit"):
        required = set(ids)
    elif preset == "orbit":
        required = {subj, targ} - {None, ""} or {ids[0]}
    elif preset == "two_shot":
        required = {subj, targ or next((i for i in ids if i != subj), subj)}
    elif preset == "over_shoulder":
        required = {targ or next((i for i in ids if i != subj), subj)}  # the subject is the foreground shoulder
    else:
        required = {subj or ids[0]}
    for a in job["actors"]:
        samples = [x for f in report["frames"] for x in f["actors"] if x["id"] == a["id"]]
        if not samples:
            fails.append(f"{a['id']}: no report samples")
            continue
        inside = [s["inFrame"] for s in samples]
        visible = [s["visible"] for s in samples]
        miny = sorted(s["minY"] for s in samples)
        med = miny[len(miny) // 2]
        heights = [s["bbox"][3] - s["bbox"][1] for s in samples]
        st = {"in_frame_min": round(min(inside), 3), "in_frame_mean": round(sum(inside) / len(inside), 3),
              "visible_mean": round(sum(visible) / len(visible), 3), "ground_median_m": round(med, 3),
              "ground_min_m": round(miny[0], 3), "screen_height_mean": round(sum(heights) / len(heights), 3)}
        st["required_in_frame"] = a["id"] in required
        per[a["id"]] = st
        if a["id"] not in required:
            if med > 0.06 and st["in_frame_mean"] > 0.3:
                fails.append(f"{a['id']}: floating, lowest point {med * 100:.0f} cm above the floor (median)")
            continue
        head_in = [s.get("headIn", 1) for s in samples]
        st["head_in_frame"] = round(sum(head_in) / len(head_in), 3)
        if preset in ("medium", "close_up", "over_shoulder", "push_in"):
            # closer framings crop the body on purpose: the face must stay in frame
            if st["head_in_frame"] < 0.95:
                fails.append(f"{a['id']}: head out of frame in {1 - st['head_in_frame']:.0%} of samples")
            if st["in_frame_mean"] < 0.25:
                fails.append(f"{a['id']}: barely in frame ({st['in_frame_mean']:.0%} of the body)")
        elif st["in_frame_mean"] < 0.85:
            fails.append(f"{a['id']}: only {st['in_frame_mean']:.0%} of the body in frame on average")
        elif st["in_frame_min"] < 0.6:
            warns.append(f"{a['id']}: partly out of frame at times (min {st['in_frame_min']:.0%})")
        if st["visible_mean"] < 0.6 and preset != "over_shoulder":  # OTS frames the target past a shoulder on purpose
            warns.append(f"{a['id']}: often hidden behind the set or another character ({st['visible_mean']:.0%} visible)")
        if med > 0.06:
            fails.append(f"{a['id']}: floating, lowest point {med * 100:.0f} cm above the floor (median)")
        if miny[0] < -0.06:
            warns.append(f"{a['id']}: sinks {-miny[0] * 100:.0f} cm into the floor at times")
        if st["screen_height_mean"] < 0.08:
            warns.append(f"{a['id']}: tiny in frame ({st['screen_height_mean']:.0%} of the frame height)")
    props_v, seats_v = {}, {}
    for ra in report.get("actors", []):
        if ra.get("maxHipStepM", 0) > 0.3:
            fails.append(f"{ra['id']}: hips jump {ra['maxHipStepM']:.2f} m between frames (clip join or placement)")
        # Props: follow the hand (pivot fixed in the hand's frame) and stay out of the holder's head and body.
        for pr in ra.get("props", []):
            key = f"{ra['id']}.{pr['id']}"
            props_v[key] = pr
            if not pr.get("samples"):
                continue
            if pr["handDriftCm"] > 1.0:
                fails.append(f"{key}: doesn't follow the hand (drifts {pr['handDriftCm']:.1f} cm in the hand's frame)")
            # body = capsules (head, torso, thighs), good to ~2-3 cm on stylised rigs: > 8 cm is a real pass-through
            if pr["maxPenetrationCm"] > 8 and pr["overThreeCmShare"] > 0.1:
                fails.append(f"{key}: passes {pr['maxPenetrationCm']:.0f} cm into the {pr['worstPart']} "
                             f"({pr['overThreeCmShare']:.0%} of samples over 3 cm)")
            if pr.get("maxPushCm", 0) > 5:
                warns.append(f"{key}: held up to {pr['maxPushCm']:.0f} cm away from the hand to keep it out of the body")
            if pr["maxPenetrationCm"] > 8 and pr["overThreeCmShare"] > 0.1:
                pass
            elif pr["maxPenetrationCm"] > 3:
                warns.append(f"{key}: touches the {pr['worstPart']} (up to {pr['maxPenetrationCm']:.1f} cm in, "
                             f"{pr['overThreeCmShare']:.0%} of samples over 3 cm)")
        # Seats: the body rests on the seat (after the render-time contact fix), over the seat, feet planted.
        for si, st in enumerate(ra.get("seats", [])):
            key = f"{ra['id']}@{st['furniture']}" + (f"#{si + 1}" if len(ra.get("seats", [])) > 1 else "")
            seats_v[key] = st
            if not st.get("samples"):
                warns.append(f"{key}: seated span not in this shot")
                continue
            if abs(st["gapAfterMedianCm"]) > 3:
                fails.append(f"{key}: seat contact off by {st['gapAfterMedianCm']:.1f} cm (median) after correction")
            if st["hipsToSeatXZMedianCm"] > 22:  # seat-centre depth itself is only known to ~8 cm (backrests, cushions)
                fails.append(f"{key}: hips {st['hipsToSeatXZMedianCm']:.0f} cm from the seat centre (median)")
            elif st["hipsToSeatXZMedianCm"] > 15:
                warns.append(f"{key}: hips {st['hipsToSeatXZMedianCm']:.0f} cm from the seat centre (median)")
            if st["gapBeforeMaxAbsCm"] > 15:
                warns.append(f"{key}: motion sat {st['gapBeforeMaxAbsCm']:.0f} cm off the seat at worst (render corrects up to 15 cm)")
            if max(st["leftFootDriftCm"], st["rightFootDriftCm"]) > 6:
                warns.append(f"{key}: feet move up to {max(st['leftFootDriftCm'], st['rightFootDriftCm']):.0f} cm while seated")
    out = {"passed": not fails, "failures": fails, "warnings": warns, "video": p, "actors": per}
    if props_v:
        out["props"] = props_v
    if seats_v:
        out["seats"] = seats_v
    return out


# ---------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Render a shot spec JSON (see docs/render-shot.md)")
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--stop-server", action="store_true")
    ap.add_argument("--fetch-assets", action="store_true")
    a = ap.parse_args()
    if a.fetch_assets:
        ensure_assets()
    if a.stop_server:
        stop_server()
    if a.spec:
        print(json.dumps(render(json.loads(Path(a.spec).read_text()), force=a.force), indent=1))
