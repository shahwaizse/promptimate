"""Example short #2, "Last Bus": a rainy night, a bench for two, a phone and a coffee. Renders the shot list with
shots.render_many (render_shot's engine: props in hand, sitting on furniture, night lighting with rain), voices the
narration with local Kokoro TTS (`npx hyperframes tts`), assembles with the shorts template and renders the MP4.

    .venv\\Scripts\\python.exe demo\\shorts_template\\last_bus\\gen_motions.py   # once: the motions
    .venv\\Scripts\\python.exe demo\\shorts_template\\last_bus\\make_short.py [--quality final|draft] [--sequential]

One story clock for everyone (Nora's chain starts at T=0, Walt's at 12, Jun crosses at 0.8 and again at 12.4); each
shot films a window of it. Characters come from the shared cast file (casts/town.json), so Walt always has his coffee.
Output: demo/shorts_template/build/last_bus/last_bus.mp4 and build/last_bus_report.json (timings, validation).
"""
import argparse
import hashlib
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
sys.path.insert(0, str(HERE))
import build_short  # noqa: E402
import gen_motions as G  # noqa: E402
import shots  # noqa: E402

M = json.loads((HERE / "motions.json").read_text())
CAST_FILE = "demo/shorts_template/casts/town.json"
NORA = [M[k] for k in ("nora_enter", "nora_sit", "nora_phone", "nora_call", "nora_listen", "nora_laugh", "nora_rest")]
WALT = [M[k] for k in ("walt_enter", "walt_sit", "walt_talk", "walt_drink", "walt_raise")]
CHAIN = {"nora": 0.0, "walt": 12.0, "jun": 0.8, "jun2": 12.4}
OUT = TEMPLATE / "build" / "last_bus_src"
LIGHT = {"preset": "night_street", "weather": "rain", "key_yaw": -35, "rim": 1.1, "exposure": 0.25}
PRACTICALS = [  # a warm shop window and a cool sign across the plaza, just outside the frame edges
    {"pos": [-3.2, 2.4, 4.6], "color": [1.0, 0.55, 0.3], "intensity": 5, "range": 7},
    {"pos": [3.6, 3.0, 5.2], "color": [0.35, 0.6, 1.0], "intensity": 6, "range": 8},
]


def _clock(names):
    """Story time at which each clip of a chain starts."""
    t, out = 0.0, []
    for n in names:
        out.append(t)
        t += shots._duration(n)
    return out


NORA_T = _clock(NORA)
# The seated 'looks at the phone' take holds it in the LEFT hand (forearm across the chest, palm up) and the call in
# the right: one phone, handed over between the clips, put away while she listens.
PHONE_LEFT = [NORA_T[2] - 0.2, NORA_T[3] + 0.2]
PHONE_RIGHT = [NORA_T[3] + 0.2, NORA_T[4] + 3.2]

# (id, story time in, duration, camera, actors in shot)
SHOTS = [
    ("s1", 0.0, 3.8, {"preset": "follow", "subject": "nora", "distance": 1.6}, ["nora", "jun"]),
    ("s2", 4.4, 3.2, {"preset": "medium", "subject": "nora", "distance": 1.25}, ["nora"]),
    ("s3", 8.2, 3.2, {"preset": "close_up", "subject": "nora", "height": 1.7, "distance": 1.1}, ["nora"]),
    ("s4", 14.2, 2.6, {"preset": "wide", "subject": "walt", "distance": 0.75}, ["nora", "walt"]),
    ("s5", 16.8, 3.4, {"preset": "two_shot", "subject": "nora", "target": "walt"}, ["nora", "walt"]),
    ("s6", 20.9, 2.7, {"preset": "close_up", "subject": "walt"}, ["walt", "nora"]),
    ("s7", 21.0, 3.0, {"preset": "close_up", "subject": "nora", "distance": 1.15}, ["nora", "walt"]),
    ("s8", 25.0, 3.0, {"preset": "close_up", "subject": "walt", "distance": 1.15}, ["walt", "nora"]),
    ("s9", 28.6, 3.4, {"preset": "two_shot", "subject": "nora", "target": "walt", "distance": 1.15}, ["nora", "walt"]),
]
# Narration: (desired start in the edit, voice, text), timed to the cuts (shots start at 0, 3.8, 7.0, 10.2, 12.8,
# 16.2, 18.9, 21.9, 24.9 s). Laid out one after another without overlaps; everything ends before the end card.
VO = [
    (0.2, "am_michael", "Eleven fifty-two. The last bus was due at eleven forty."),
    (4.0, "am_michael", "Nora checked the app. Again."),
    (7.3, "af_nova", "Mom? I missed it. No, I'm fine."),
    (10.4, "am_michael", "Then Walt sat down."),
    (13.2, "bm_george", "Fridays. It's always late."),
    (16.4, "bm_george", "Twenty years on this bench."),
    (19.2, "af_nova", "Twenty years?"),
    (22.1, "bm_george", "Best coffee in town is the wait."),
    (25.0, "am_michael", "It came at midnight. Neither of them minded."),
]


def actor(aid, shot_t0):
    if aid == "nora":
        return {"id": "nora", "cast": "nora", "at": list(G.NORA_START), "yaw": G.NORA_YAW, "motion": NORA,
                "start": round(CHAIN["nora"] - shot_t0, 3), "props": [{"prop": "phone", "id": "phone_l", "hand": "left", "chain_t": PHONE_LEFT},
                          {"prop": "phone", "id": "phone_r", "hand": "right", "chain_t": PHONE_RIGHT}]}
    if aid == "walt":
        return {"id": "walt", "cast": "walt", "at": list(G.WALT_START), "yaw": G.WALT_YAW, "motion": WALT,
                "start": round(CHAIN["walt"] - shot_t0, 3)}
    k = aid  # jun / jun2: the passer-by with an umbrella, behind the bench
    return {"id": "jun", "cast": "jun", "at": list(G.JUN_START), "yaw": G.JUN_YAW, "motion": [M["jun_cross"]],
            "start": round(CHAIN[k] - shot_t0, 3), "props": [{"prop": "umbrella", "hand": "right"}]}


def spec_for(sid, t0, dur, cam, who, quality):
    return {"name": f"last_bus_{sid}", "aspect": "9:16", "stage": "street", "lighting": LIGHT, "quality": quality,
            "seconds": dur, "camera": cam, "cast_file": CAST_FILE, "furniture": [G.BENCH, G.LAMP],
            "practicals": PRACTICALS, "actors": [actor(x, t0) for x in who]}


def tts(text, voice, out: Path):
    if out.exists():
        return out
    env = os.environ.copy()
    env.setdefault("npm_config_cache", r"D:\npm-cache")
    venv_py = ROOT / ".cache" / "tts-venv" / "Scripts" / "python.exe"
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
    ap.add_argument("--sequential", action="store_true", help="render shot by shot (for timing comparisons)")
    ap.add_argument("--force", action="store_true", help="re-render shots even if cached")
    ap.add_argument("--only", default="", help="comma-separated shot ids (iterate on a few shots)")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "vo").mkdir(exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    plan = [s for s in SHOTS if not only or s[0] in only]
    specs = [spec_for(*s, a.quality) for s in plan]
    report = {"shots": [], "renders_s": {}, "mode": "sequential" if a.sequential else "render_many"}
    t_all = time.time()
    t = time.time()
    results = [shots.render(sp, force=a.force) for sp in specs] if a.sequential else shots.render_many(specs, force=a.force)
    report["shots_render_s"] = round(time.time() - t, 1)
    shot_entries = []
    for (sid, t0, dur, cam, who), r in zip(plan, results):
        if "error" in r:
            print(sid, "ERROR", r["error"][:600])
            report["shots"].append({"id": sid, "error": r["error"]})
            continue
        v = r["validation"]
        report["renders_s"][sid] = {"cached": r["cached"], "unity": r["timing_s"]["unity"], "encode": r["timing_s"]["encode"]}
        print(f"{sid} {cam['preset']:<13} cached={r['cached']} passed={v['passed']} fail={v['failures']} warn={v['warnings']}",
              flush=True)
        report["shots"].append({"id": sid, "camera": cam, "story_t": t0, "seconds": dur, "mp4": r["mp4"],
                                "contact_sheet": r["contact_sheet"], "validation": v, "furniture": r.get("furniture")})
        shot_entries.append({"id": sid, "video": r["mp4"], "duration": dur,
                             **({"punch": 1.04} if cam["preset"] == "close_up" else {})})
    if only or len(shot_entries) < len(SHOTS):
        (TEMPLATE / "build" / "last_bus_report.json").write_text(json.dumps(report, indent=1))
        return
    vo, t_free = [], 0.0
    for k, (want, voice, text) in enumerate(VO):
        wav = tts(text, voice, OUT / "vo" / f"vo{k + 1}_{hashlib.sha1((voice + text).encode()).hexdigest()[:8]}.wav")
        a0, a1 = build_short.speech_span(wav)
        start = max(want - a0, t_free)
        vo.append({"id": f"vo{k + 1}", "audio": str(wav), "start": round(start, 3), "text": text})
        t_free = start + a1 + 0.12
    short = {"name": "last_bus", "size": [1080, 1920], "fps": 30, "title": "Missed the last bus.",
             "shots": shot_entries, "voiceover": vo, "music": {"src": None, "volume": 0.25}, "sfx_on_cuts": True,
             "end_card": {"text": "Animated with Promptimate", "duration": 2.4}}
    spec_path = OUT / "short.json"
    spec_path.write_text(json.dumps(short, indent=1))
    proj = build_short.build(spec_path, TEMPLATE / "build" / "last_bus")
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
        final = proj / "last_bus.mp4"
        r = build_short.npx(["render", "--output", str(final)], proj)
        (proj / "render.log").write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
        report["hyperframes_render_s"] = round(time.time() - t, 1)
        p = shots.probe(final)
        want = report["shots_total_s"] + 2.4
        report["final"] = {"mp4": str(final), **p,
                           "ok": bool(p) and (p["width"], p["height"]) == (1080, 1920) and abs(p["duration_s"] - want) < 0.25}
        print("final:", report["final"])
    report["total_s"] = round(time.time() - t_all, 1)
    (TEMPLATE / "build" / "last_bus_report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
