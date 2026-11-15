"""End-to-end example short "Wrong Turn": render the shot list with shots.render (render_shot), voice the narration
with local Kokoro TTS (`npx hyperframes tts`), assemble with the shorts template and render the vertical MP4.

    .venv\\Scripts\\python.exe demo\\shorts_template\\story\\gen_motions.py   # once: generates the motions
    .venv\\Scripts\\python.exe demo\\shorts_template\\story\\make_short.py [--quality final|draft]

Story clock: both performances run on one timeline (Leo's chain starts at T=0, Ava's at T=5). Every shot films a
window of that timeline, so cuts between angles stay continuous; each actor's `start` is (chain start - shot start).
Output: demo/shorts_template/build/wrong_turn/wrong_turn.mp4 (+ the HyperFrames project next to it).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent
ROOT = TEMPLATE.parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
sys.path.insert(0, str(TEMPLATE))
import build_short  # noqa: E402
import shots  # noqa: E402

M = json.loads((HERE / "motions.json").read_text())
STAGING = {a["id"]: a for a in json.loads((HERE / "staging.json").read_text())["actors"]}
LEO = [M[k] for k in ("leo_enter", "leo_confused", "leo_listen", "leo_thanks", "leo_runs")]
AVA = [M[k] for k in ("ava_enter", "ava_points", "ava_shrug")]
CHAIN_START = {"leo": 0.0, "ava": 5.0}
OUT = TEMPLATE / "build" / "wrong_turn_src"

# (id, story time in, duration, camera, actors in shot)
SHOTS = [
    ("s1", 0.0, 3.0, {"preset": "wide", "subject": "leo"}, ["leo"]),
    ("s2", 3.0, 2.4, {"preset": "follow", "subject": "leo", "side": "right"}, ["leo"]),
    ("s3", 6.3, 1.9, {"preset": "close_up", "subject": "leo"}, ["leo"]),
    ("s4", 6.2, 2.4, {"preset": "follow", "subject": "ava"}, ["leo", "ava"]),
    ("s5", 9.6, 2.8, {"preset": "over_shoulder", "subject": "leo", "target": "ava"}, ["leo", "ava"]),
    ("s6", 12.5, 2.7, {"preset": "two_shot", "subject": "leo", "target": "ava"}, ["leo", "ava"]),
    ("s7", 15.2, 3.0, {"preset": "follow", "subject": "leo", "distance": 1.2, "amount": 0.45}, ["leo", "ava"]),
    ("s8", 15.4, 2.5, {"preset": "low_angle", "subject": "ava"}, ["ava"]),
]
# Narration: (desired start in the edit, voice, text). Placed one after another without overlaps.
VO = [
    (0.2, "am_michael", "Leo had been walking for an hour."),
    (3.05, "am_michael", "The map said left. His gut said... also left."),
    (6.0, "am_michael", "Then a stranger stopped."),
    (7.9, "af_nova", "The station? It's back that way."),
    (10.6, "am_michael", "Of course it was."),
    (13.1, "am_michael", "He thanked her, and ran."),
    (16.1, "am_michael", "Some people never ask for directions."),
]


def actor(aid, shot_t0):
    st = STAGING[aid]
    placed = shots.stage(list(STAGING.values()))[aid]
    return {"id": aid, "cast": st["cast"], "at": placed["pos"], "yaw": placed["yaw"],
            "motion": LEO if aid == "leo" else AVA, "start": round(CHAIN_START[aid] - shot_t0, 3)}


def tts(text, voice, out: Path):
    if out.exists():
        return out
    env = os.environ.copy()
    env.setdefault("npm_config_cache", r"D:\npm-cache")
    venv_py = ROOT / ".cache" / "tts-venv" / "Scripts" / "python.exe"  # kokoro-onnx + soundfile, kept out of .venv
    if venv_py.exists():
        env.setdefault("HYPERFRAMES_PYTHON", str(venv_py))
    r = subprocess.run(["npx.cmd" if os.name == "nt" else "npx", "--yes", build_short.HF, "tts", text, "--voice", voice,
                        "--output", str(out)], capture_output=True, text=True, env=env, cwd=str(out.parent))
    if r.returncode or not out.exists():
        raise SystemExit(f"tts failed: {r.stdout[-800:]} {r.stderr[-800:]}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quality", default="final")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "vo").mkdir(exist_ok=True)
    report = {"shots": [], "renders_s": {}}
    shot_entries = []
    t_all = time.time()
    for sid, t0, dur, cam, who in SHOTS:
        spec = {"name": f"wrong_turn_{sid}", "aspect": "9:16", "stage": "street", "lighting": "golden_hour",
                "key_yaw": -60, "quality": a.quality, "seconds": dur, "camera": cam,
                "actors": [actor(x, t0) for x in who]}
        t = time.time()
        r = shots.render(spec)
        report["renders_s"][sid] = {"total": round(time.time() - t, 1), "cached": r["cached"], "unity": r["timing_s"]["unity"]}
        v = r["validation"]
        print(f"{sid} {cam['preset']:<13} {time.time() - t:5.1f}s cached={r['cached']} passed={v['passed']} "
              f"fail={v['failures']} warn={v['warnings']}", flush=True)
        report["shots"].append({"id": sid, "camera": cam, "story_t": t0, "seconds": dur, "mp4": r["mp4"],
                                "contact_sheet": r["contact_sheet"], "validation": v})
        shot_entries.append({"id": sid, "video": r["mp4"], "duration": dur, **({"punch": 1.05} if cam["preset"] in ("close_up",) else {})})
    # Voiceover, laid out without overlaps.
    vo, t_free = [], 0.0
    for k, (want, voice, text) in enumerate(VO):
        wav = tts(text, voice, OUT / "vo" / f"vo{k + 1}.wav")
        a0, a1 = build_short.speech_span(wav)
        start = max(want - a0, t_free)
        vo.append({"id": f"vo{k + 1}", "audio": str(wav), "start": round(start, 3), "text": text})
        t_free = start + a1 + 0.12
    short = {"name": "wrong_turn", "size": [1080, 1920], "fps": 30, "title": "He was SO sure.",
             "shots": shot_entries, "voiceover": vo, "music": {"src": None, "volume": 0.25}, "sfx_on_cuts": True,
             "end_card": {"text": "Animated with Promptimate", "duration": 2.4}}
    spec_path = OUT / "short.json"
    spec_path.write_text(json.dumps(short, indent=1))
    proj = build_short.build(spec_path, TEMPLATE / "build" / "wrong_turn")
    report["vo_end_s"] = round(t_free, 2)
    report["shots_total_s"] = round(sum(s["duration"] for s in shot_entries), 2)
    if not a.no_render:
        c = build_short.npx(["check", "--json"], proj)
        (proj / "check.json").write_text(c.stdout, encoding="utf-8")
        try:
            ck = json.loads(c.stdout)
            print("check ok:", ck.get("ok"), [f.get("code") for k in ("lint", "layout", "audio", "craft") for f in (ck.get(k) or {}).get("findings", [])])
        except Exception:
            print("check output not JSON")
        t = time.time()
        final = proj / "wrong_turn.mp4"
        r = build_short.npx(["render", "--output", str(final)], proj)
        (proj / "render.log").write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
        report["hyperframes_render_s"] = round(time.time() - t, 1)
        p = shots.probe(final)
        want = report["shots_total_s"] + 2.4
        report["final"] = {"mp4": str(final), **p,
                           "ok": bool(p) and (p["width"], p["height"]) == (1080, 1920) and abs(p["duration_s"] - want) < 0.25}
        print("final:", report["final"])
    report["total_s"] = round(time.time() - t_all, 1)
    (TEMPLATE / "build" / "wrong_turn_report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
