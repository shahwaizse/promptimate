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
VERSION = 7  # bump when the Unity renderer or resolution changes in a way that should invalidate cached renders

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
STAGES = ["street", "interior", "park", "studio", "void"]
LIGHTING = ["day", "golden_hour", "night_street", "interior_warm", "studio"]
CAMERAS = ["wide", "medium", "close_up", "over_shoulder", "follow", "push_in", "orbit", "low_angle", "top_down",
           "two_shot", "explicit"]

# Starter cast: CC0 characters fetched by unity/DemoStudio/fetch_render_assets.py (see render_assets.json).
_Q = "Assets/ThirdParty/Quaternius/"
_K = "Assets/ThirdParty/Kenney/AnimatedCharacters1/"
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
    out = {k: {"look": v["look"], "height_m": v["height"], "license": v["license"]} for k, v in CAST.items()}
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
                     loop_last: bool = False) -> tuple[list[dict], float]:
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

def _cast_entry(a: dict) -> dict:
    c = a.get("cast")
    if a.get("model"):
        return {"model": a["model"], "skin": a.get("skin"), "height": float(a.get("height", 1.75))}
    if not c:
        c = "businessman"
    if c.startswith("mixamo:"):
        return {"model": f"Assets/Characters/Mixamo/{c.split(':', 1)[1]}.fbx", "height": float(a.get("height", 1.75))}
    if c not in CAST:
        raise ValueError(f"unknown cast {c!r}; one of {', '.join(list_cast())} (or give model: 'Assets/....fbx|.glb')")
    e = dict(CAST[c])
    if a.get("height"):
        e["height"] = float(a["height"])
    return e


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
    light = light if isinstance(light, dict) else {"preset": light}
    if light.get("preset", "day") not in LIGHTING:
        raise ValueError(f"lighting must be one of {LIGHTING}")
    actors_in = spec.get("actors") or []
    if not actors_in:
        raise ValueError("need at least one actor")
    for i, a in enumerate(actors_in):
        a.setdefault("id", "ABCDEFGH"[i] if i < 8 else f"actor{i}")
    placed = stage(actors_in)
    actors, longest = [], 0.0
    for a in actors_in:
        ce = _cast_entry(a)
        p = placed[a["id"]]
        motions = a.get("motion") or a.get("motions") or []
        if isinstance(motions, str):
            motions = [motions]
        pos2, yaw = tuple(p["pos"]), float(p["yaw"])
        if motions:
            unity_segs, end = resolve_segments(motions, pos2, yaw, float(a.get("start", a.get("time_offset", 0.0))),
                                               loop_last=bool(a.get("loop", False)))
            longest = max(longest, end)
        else:
            unity_segs = [{"clip": idle_clip(), "start": 0.0, "clipStart": 0.0, "speed": 1, "loop": True,
                           "pos": [pos2[0], 0, pos2[1]], "yaw": yaw}]
        actors.append({"id": a["id"], "model": ce["model"], "skin": ce.get("skin") or "", "height": ce["height"],
                       "pos": [pos2[0], 0, pos2[1]], "yaw": yaw, "segs": unity_segs,
                       "footIK": bool(a.get("foot_ik", True)), "grounding": bool(a.get("grounding", True)),
                       "_motions": motions})
    seconds = float(spec.get("seconds") or min(max(longest, 2.0), 12.0))
    if not 0.5 <= seconds <= 30:
        raise ValueError("seconds must be 0.5-30")
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
    return {"id": spec.get("name") or "shot", "width": w, "height": h, "fps": fps, "seconds": round(seconds, 3),
            "supersample": {"draft": 1.0, "final": 1.5, "high": 2.0}.get(quality, 1.5),
            "stage": stage_name, "seed": int(spec.get("seed", 0)), "lighting": lighting,
            "actors": actors, "camera": cam_out, "reportEvery": 3, "format": "jpg" if quality == "draft" else "png",
            "_aspect": aspect, "_quality": quality}


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


def render(spec: dict, *, force: bool = False, keep_frames: bool = False, log=_log) -> dict:
    """Render one shot. Returns {"mp4", "contact_sheet", "report", "validation", "cached", "seconds", ...}."""
    t0 = time.time()
    ensure_assets(log=log)
    job = resolve(json.loads(json.dumps(spec)))
    meta_actors = [{"id": a["id"], "motions": a.pop("_motions")} for a in job["actors"]]
    aspect, quality = job.pop("_aspect"), job.pop("_quality")
    key = _key(job)
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (spec.get("name") or "shot"))[:40]
    out = CACHE / "renders" / f"{name}_{key}"
    mp4 = out / f"{name}.mp4"
    result_file = out / "result.json"
    if not force and result_file.exists() and mp4.exists():
        res = json.loads(result_file.read_text())
        res["cached"] = True
        res["seconds_total"] = round(time.time() - t0, 2)
        return res
    frames = out / "frames"
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    frames.mkdir(parents=True)
    job["id"] = f"{name}_{key}"
    job["outDir"] = str(frames).replace("\\", "/")
    (out / "shot.json").write_text(json.dumps(job, indent=1))
    n_frames = max(1, round(job["seconds"] * job["fps"]))
    with _lock:
        t1 = time.time()
        _submit(job, timeout=240 + n_frames * 3.0, log=log)
        t_render = time.time() - t1
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
           "seconds": job["seconds"], "frames": n_frames, "aspect": aspect, "quality": quality,
           "stage": job["stage"], "lighting": job["lighting"]["preset"], "camera": job["camera"]["preset"],
           "actors": [{"id": a["id"], "model": a["model"], "pos": a["pos"], "yaw": a["yaw"],
                       "segments": [{"clip": Path(s["clip"]).stem, "start": s["start"], "pos": s["pos"], "yaw": s["yaw"]} for s in a["segs"]],
                       "motions": m["motions"]} for a, m in zip(job["actors"], meta_actors)],
           "timing_s": {"unity": round(t_render, 2), "encode": round(t_encode, 2), "unity_breakdown": report.get("timing")}}
    res["seconds_total"] = round(time.time() - t0, 2)
    result_file.write_text(json.dumps(res, indent=1))
    return res


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
    for ra in report.get("actors", []):
        if ra.get("maxHipStepM", 0) > 0.3:
            fails.append(f"{ra['id']}: hips jump {ra['maxHipStepM']:.2f} m between frames (clip join or placement)")
    return {"passed": not fails, "failures": fails, "warnings": warns, "video": p, "actors": per}


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
