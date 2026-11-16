r"""Builds and renders "Your Move" in unity/FidelityStudio (HDRP path tracer).

    .venv\Scripts\python.exe demo\fidelity\make_film.py --mode raster --step 6 --res 960x540     # fast blocking preview
    .venv\Scripts\python.exe demo\fidelity\make_film.py --mode pt --spp 16 --res 960x540 --stills 3,10,20,28
    .venv\Scripts\python.exe demo\fidelity\make_film.py --mode pt --spp 96                        # final 1080p frames
    .venv\Scripts\python.exe demo\fidelity\make_film.py --layout                                  # set check renders

Reads motions.json (gen_motions.py) and layout.json, resolves every actor's continue_from chain into Unity clip
segments on one story clock (mcp_server/shots.py helpers), writes the FilmSpec and runs Unity under the machine-wide
heavy lock. Frames land in demo/fidelity/build/<run>/<shot>/fNNNN.png.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "unity" / "FidelityStudio"
os.environ.setdefault("PROMPTIMATE_RENDER_PROJECT", str(PROJECT))
sys.path.insert(0, str(ROOT / "mcp_server"))
sys.path.insert(0, str(ROOT / "scripts"))
import shots  # noqa: E402
from heavy_lock import heavy  # noqa: E402

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
LAYOUT = json.loads((HERE / "layout.json").read_text())
UNITY = Path(os.environ.get("FID_UNITY", r"D:\Unity\Editors\6000.0.34f1\Editor\Unity.exe"))

D_START = 7.5  # story time the daughter starts walking in the hallway

FATHER = ["f_window", "f_turn", "f_gesture", "f_sit", "f_sit_wait", "f_move", "f_sit_end"]
DAUGHTER = ["d_enter", "d_setdown", "d_wait", "d_walk", "d_sit", "d_sit_look", "d_sit_end"]


def actor(aid: str, model: str, height: float, roles: list[str], names: dict, start_xz, yaw: float, t0: float,
          chair: str, blink: int) -> tuple[dict, list[dict]]:
    motions = [names[r] for r in roles if r in names]
    clips: list[dict] = []
    segs, end = shots.resolve_segments(motions, tuple(start_xz), yaw, t0, clips=clips)
    a = {"id": aid, "model": model, "height": height, "pos": [start_xz[0], 0, start_xz[1]], "yaw": yaw, "segs": segs,
         "footIK": True, "grounding": True, "blinkSeed": blink, "seats": [], "props": []}
    best = max(clips, key=lambda c: math.hypot(*shots._end_placement(c["name"])[:2]))
    dist = math.hypot(*shots._end_placement(best["name"])[:2])
    idx = next((i for i, sg in enumerate(segs) if Path(sg["clip"]).stem == best["name"] and sg.get("speed", 1) != 0), None)
    if idx is not None and dist >= 0.3:
        a["travelCal"] = [idx, round(dist, 4)]
    spans = [s for s in (shots._seat_from_clip(c) for c in clips) if s]
    merged: list[list[float]] = []
    for s in sorted(spans, key=lambda q: q["t"][0]):
        if merged and s["t"][0] - merged[-1][1] < 0.25:
            merged[-1][1] = max(merged[-1][1], s["t"][1])
        else:
            merged.append(list(s["t"]))
    a["seats"] = [{"furniture": chair, "start": round(x, 3), "end": round(y, 3), "blend": 0.4, "maxCorrection": 0.12} for x, y in merged]
    return a, clips


def clip_t0(clips: list[dict], role_name: str) -> float:
    return next(c["t0"] for c in clips if c["name"] == role_name)


def K(t, pos, look, focal=35, focus=0.0, aperture=2.8, roll=0.0):
    return {"t": t, "pos": list(pos), "look": list(look), "focal": focal, "focus": focus, "aperture": aperture, "roll": roll}


def shot_list(ev: dict) -> list[dict]:
    """The cut. Times are story seconds; keys are relative to the shot start. Faces are static, so the staging keeps
    them backlit, in profile, small in frame or turned away."""
    T = ev
    s = []
    s.append({"id": "s01_room", "t0": 0.0, "t1": 5.0, "ev": 8.95, "handheld": 0.15, "keys": [
        K(0, (2.55, 1.22, -2.35), (-0.45, 1.15, 2.25), 24, 0, 5.6),
        K(5.0, (2.05, 1.30, -1.55), (-0.55, 1.2, 2.3), 26, 0, 5.6)]})
    s.append({"id": "s02_father", "t0": 5.0, "t1": T["d_door"] + 0.2, "ev": 9.25, "handheld": 0.25, "keys": [
        K(0, (-0.05, 1.58, 1.82), (-1.1, 1.58, 2.42), 50, 0, 2.0),
        K(4.0, (-0.22, 1.60, 1.95), (-1.1, 1.58, 2.42), 52, 0, 2.0)]})
    s.append({"id": "s03_door", "t0": T["d_door"] + 0.2, "t1": T["f_turn"] + 0.1, "ev": 8.65, "handheld": 0.3, "keys": [
        K(0, (-0.55, 1.52, 2.05), (-1.45, 1.35, -2.6), 40, 5.0, 2.8),
        K(T["f_turn"] + 0.1 - T["d_door"] - 0.2, (-0.5, 1.52, 2.0), (-1.3, 1.3, -0.9), 40, 2.85, 2.8)]})
    s.append({"id": "s04_turn", "t0": T["f_turn"] + 0.1, "t1": T["d_set"] + 1.0, "ev": 9.05, "handheld": 0.3, "keys": [
        K(0, (-1.55, 1.52, 0.1), (-1.05, 1.5, 2.3), 55, 0, 2.0),
        K(2.0, (-1.5, 1.52, 0.2), (-1.05, 1.52, 2.3), 55, 0, 2.0)]})
    s.append({"id": "s05_case", "t0": T["d_set"] + 1.0, "t1": T["d_set"] + 2.75, "ev": 8.55, "handheld": 0.25, "keys": [
        K(0, (0.05, 0.32, -0.5), (-1.0, 0.24, -0.8), 26, 0, 2.4),
        K(1.75, (0.0, 0.33, -0.52), (-1.0, 0.26, -0.8), 26, 0, 2.4)]})
    s.append({"id": "s06_invite", "t0": T["d_set"] + 2.75, "t1": T["d_walk"] + 0.3, "ev": 8.95, "handheld": 0.3, "keys": [
        K(0, (-2.25, 1.6, -2.3), (-0.95, 1.42, 2.3), 40, 0, 2.8),
        K(4.3, (-2.18, 1.6, -2.15), (-0.9, 1.42, 2.3), 40, 0, 2.8)]})
    s.append({"id": "s07_sit", "t0": T["d_walk"] + 0.3, "t1": T["d_seated"] + 0.1, "ev": 8.85, "handheld": 0.15, "keys": [
        K(0, (2.0, 1.35, -1.9), (-0.5, 1.05, 0.9), 24, 0, 4.0),
        K(T["d_seated"] - T["d_walk"] - 0.2, (1.85, 1.3, -1.7), (0.5, 0.95, 1.7), 24, 0, 4.0)]})
    s.append({"id": "s08_board", "t0": T["d_seated"] + 0.1, "t1": T["f_reach"] + 0.85, "ev": 9.15, "handheld": 0.2, "keys": [
        K(0, (0.45, 1.02, -0.1), (0.45, 0.98, 1.75), 32, 0, 2.8),
        K(4.0, (0.45, 1.02, 0.25), (0.45, 0.98, 1.75), 32, 0, 2.8)]})
    s.append({"id": "s09_move", "t0": T["f_reach"] + 0.85, "t1": T["f_reach"] + 3.4, "ev": 9.25, "handheld": 0.2, "keys": [
        K(0, (0.5, 0.95, 1.22), (0.39, 0.80, 1.77), 65, 0, 2.4),
        K(2.55, (0.47, 0.94, 1.27), (0.39, 0.80, 1.77), 65, 0, 2.4)]})
    s.append({"id": "s10_end", "t0": T["f_reach"] + 3.4, "t1": T["f_reach"] + 8.4, "ev": 9.05, "handheld": 0.1, "keys": [
        K(0, (0.45, 1.25, -0.5), (0.45, 1.05, 2.0), 30, 0, 4.0),
        K(4.7, (0.45, 1.45, -2.0), (0.45, 1.1, 2.1), 30, 0, 4.0)]})
    for x in s:
        x["t0"], x["t1"] = round(x["t0"], 3), round(x["t1"], 3)
    return s


def build_spec(args) -> dict:
    names = json.loads((HERE / "motions.json").read_text())
    L = LAYOUT
    if not all(r in names for r in FATHER + DAUGHTER):
        if not args.layout:
            raise SystemExit("motions.json is incomplete; run gen_motions.py first (or use --layout)")
        ev = {"d_door": 8.7, "f_turn": 11.5, "d_set": 12.1, "f_gesture": 16.3, "d_walk": 18.9, "d_seated": 24.9, "f_reach": 26.4}
        spec = {"outDir": str(BUILD / args.run), "width": args.w, "height": args.h, "fps": 24, "mode": args.mode, "spp": args.spp,
                "denoise": "none", "sunElev": 16, "sunAzim": 22, "sunLux": 38000, "sunKelvin": 3500, "sunAngle": 0.8,
                "hdri": "ehingen_hillside_nosun_2k.hdr", "skyLux": 8000, "skyRot": args.sky_rot, "fogMfp": args.fog,
                "dust": args.dust, "actors": [], "shots": shot_list(ev), "layoutCheck": True, "format": "png"}
        (BUILD / args.run).mkdir(parents=True, exist_ok=True)
        (BUILD / args.run / "events.json").write_text(json.dumps(ev, indent=2))
        return spec
    fa, fclips = actor("father", "Male_Adult_03", 1.80, FATHER, names, L["father_start"], L["father_yaw"], 0.0, "chair_a", 3)
    da, dclips = actor("daughter", "Female_Adult_09", 1.68, DAUGHTER, names, L["daughter_start"], L["daughter_yaw"], D_START, "chair_b", 11)
    ev = {
        "d_door": D_START + 1.2,
        "f_turn": clip_t0(fclips, names["f_turn"]),
        "d_set": clip_t0(dclips, names["d_setdown"]),
        "f_gesture": clip_t0(fclips, names["f_gesture"]),
        "d_walk": clip_t0(dclips, names["d_walk"]),
        "d_seated": clip_t0(dclips, names["d_sit"]) + 2.4,
        "f_reach": clip_t0(fclips, names["f_move"]),
    }
    da["props"] = [{"model": "vintage_suitcase", "part": args.case_part, "hand": "right", "release": round(ev["d_set"] + 1.35, 3),
                    "size": 0.62, "rot": [0, 90, 0], "carryUntil": round(ev["d_set"] + 0.35, 3), "carryBlend": 0.6}]
    fa["reaches"] = [{"piece": "piece_pawn_white_04", "hand": "right", "grab": round(ev["f_reach"] + 1.05, 3),
                      "place": round(ev["f_reach"] + 1.75, 3), "blend": 0.55, "move": [0, 0, 0.116]}]
    spec = {
        "outDir": str(BUILD / args.run), "width": args.w, "height": args.h, "fps": 24, "mode": args.mode, "spp": args.spp,
        "shutter": 0.5, "denoise": "oidn" if args.mode == "pt" and not args.no_denoise else "none", "maxDepth": 6,
        "sunElev": 16, "sunAzim": 22, "sunLux": 38000, "sunKelvin": 3500, "sunAngle": 0.8,
        "hdri": "ehingen_hillside_nosun_2k.hdr", "skyLux": 8000, "skyRot": args.sky_rot,
        "fogMfp": args.fog, "dust": args.dust,
        "actors": [fa, da], "shots": shot_list(ev), "only": args.only, "frameStep": args.step,
        "frames": [float(x) for x in args.stills.split(",")] if args.stills else None, "stillsCam": "",
        "layoutCheck": args.layout, "format": "png",
    }
    if spec["frames"] is None:
        spec.pop("frames")
    (BUILD / args.run).mkdir(parents=True, exist_ok=True)
    (BUILD / args.run / "events.json").write_text(json.dumps(ev, indent=2))
    return spec


def run_unity(spec_file: Path, log: Path, who: str, extra: list[str] | None = None, chunk: int = 0,
              max_crashes: int = 10) -> int:
    """Runs the render. With chunk > 0 Unity renders at most `chunk` new frames per launch and is relaunched with
    -resume (frames already on disk are skipped) until the film is done: GPU shared memory grows every frame in
    this HDRP/driver combination and the device hangs after ~80 frames otherwise. A crash also just relaunches.
    The heavy lock is held across all launches (one heavy job at a time)."""
    crashes, k = 0, 0
    with heavy(who):
        while True:
            lg = log if k == 0 else log.with_name(log.stem + f"_part{k}.log")
            cmd = [str(UNITY), "-batchmode", "-force-d3d12", "-projectPath", str(PROJECT), "-executeMethod",
                   "Fidelity.Film.Run", "-spec", str(spec_file), "-logFile", str(lg), "-report", f"report_{k:02d}.json"] + (extra or [])
            if k > 0 and "-resume" not in cmd:
                cmd += ["-resume", "1"]
            if chunk > 0:
                cmd += ["-maxFrames", str(chunk)]
            t0 = time.time()
            code = subprocess.call(cmd)
            text = lg.read_text(encoding="utf-8", errors="ignore") if lg.exists() else ""
            frames = text.count("FID_FRAME")
            print(f"launch {k}: exit={code} in {time.time() - t0:.0f}s", flush=True)
            k += 1
            if "FID_DONE" in text or "FID_LAYOUT done" in text:
                return 0
            if "error CS" in text or "FID_ERROR" in text:
                print("render failed (script error), not retrying", flush=True)
                return code or 1
            if "FID_CHUNK" in text:
                continue
            crashes += 1
            print(f"render did not finish (crash / device removed?) - relaunching with -resume ({crashes}/{max_crashes})", flush=True)
            if crashes >= max_crashes:
                return code or 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="raster")
    ap.add_argument("--spp", type=int, default=64)
    ap.add_argument("--res", default="1920x1080")
    ap.add_argument("--only", default="")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--stills", default="")
    ap.add_argument("--layout", action="store_true")
    ap.add_argument("--run", default="")
    ap.add_argument("--fog", type=float, default=0.0)
    ap.add_argument("--sky-rot", type=float, default=0.0)
    ap.add_argument("--case-part", default="suitcase_01")
    ap.add_argument("--dust", action="store_true")
    ap.add_argument("--no-denoise", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--chunk", type=int, default=55)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    args.w, args.h = (int(v) for v in args.res.split("x"))
    args.run = args.run or (f"{args.mode}_{args.spp if args.mode == 'pt' else 'r'}_{args.h}p" + ("_layout" if args.layout else "") + ("_stills" if args.stills else ""))
    spec = build_spec(args)
    f = BUILD / args.run / "film.json"
    f.write_text(json.dumps(spec, indent=1))
    print("spec", f, "shots", [(s["id"], s["t0"], s["t1"]) for s in spec["shots"]])
    if args.dry:
        return 0
    log = ROOT / "logs" / "fid" / f"film_{args.run}.log"
    if args.resume and log.exists():
        log = log.with_name(log.stem + f"_{int(time.time())}.log")
    code = run_unity(f, log, f"fidelity: {args.run}", ["-resume", "1"] if args.resume else None,
                     chunk=args.chunk if not (args.stills or args.layout) else 0)
    os.system(f'findstr /C:"FID_" /C:"error CS" "{log}"')
    return code


if __name__ == "__main__":
    sys.exit(main())
