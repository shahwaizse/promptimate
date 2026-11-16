"""Measure the hard beats from the Roblox short (peek out from cover, falls that land readably) for the old demo
wording vs the new options, over several seeds, with motion metrics in the clip frame.

    .venv\\Scripts\\python.exe demo\\roblox_short\\hard_beats.py peek|fall|all

peek: from a crouched hide clip, continue_from into each variant; head lateral offset toward the peek side (m), time
      the head spends beyond a cover edge 0.30 m to the side, return to cover at the end, head height while peeking.
fall: from the same crouch; at the end: hips height, torso tilt from vertical, facing up (on the back) vs sitting;
      time the hips reach the ground; 'readable' = down by 2.0 s, lying (tilt > 55 deg) and still down at the end.
Results: .cache/roblox_short/v2/hard_beats.json
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server"))
os.environ.setdefault("UNITY_PROJECT", str(ROOT / ".cache" / "no_unity_project"))
import motion  # noqa: E402
import server  # noqa: E402
import roblox_tools as RT  # noqa: E402

RT.SRV = server
OUT = ROOT / ".cache" / "roblox_short" / "v2" / "hard_beats.json"
SEEDS = [0, 101, 202, 303]
HEAD, NECK, HIPS, LHIP, RHIP = 6, 4, 0, 22, 26


def gen(prompt, seconds, seed, prev=None, path=None, name="hb"):
    kw = {}
    if prev:
        kw["continue_from"] = prev
    if path:
        g = RT._gen_frame(prev)
        kw["root_path"] = [server.Waypoint(t=t, x=gx, z=gz) for t, x, z in path for gx, gz in [RT.to_gen((x, z), g)]]
    segs = [server.MotionSegment(prompt=p, seconds=s) for p, s in (prompt if isinstance(prompt, list) else [(prompt, seconds)])]
    meta = json.loads(server.generate_motion(segs, name=name, seed=seed, unity_check="off", **kw)[0])
    return meta["name"]


def peek_path(d, side, amount=0.42):
    s = amount if side == "left" else -amount
    return [(0.0, 0.0, 0.0), (0.25 * d, 0.0, 0.0), (0.45 * d, s, 0.05), (0.72 * d, s, 0.05), (0.92 * d, 0.0, 0.0), (d, 0.0, 0.0)]


def peek_metrics(name, side, t0=0.0, t1=None):
    root, rot = motion.load(ROOT / "output" / name)
    pos = motion.fk(root, rot)
    a = int(t0 * motion.FPS)
    b = len(pos) if t1 is None else int(t1 * motion.FPS)
    p = pos[a:b]
    sgn = 1.0 if side == "left" else -1.0
    lat = (p[:, HEAD, 0] - p[0, HEAD, 0]) * sgn          # + = toward the peek side (clip frame: +x = left)
    return {"head_out_max_m": round(float(lat.max()), 3),
            "beyond_edge_s": round(float((lat > 0.30).sum()) / motion.FPS, 2),
            "back_in_cover": bool(abs(lat[-1]) < 0.12),
            "head_height_m": round(float(np.median(p[:, HEAD, 1])), 2)}


def fall_metrics(name):
    root, rot = motion.load(ROOT / "output" / name)
    pos = motion.fk(root, rot)
    hips = pos[:, HIPS, 1]
    down = np.where(hips < 0.30)[0]
    end = pos[-12:]
    spine = end[:, NECK] - end[:, HIPS]
    tilt = float(np.degrees(np.arccos(np.clip(spine[:, 1] / np.linalg.norm(spine, axis=1), -1, 1))).mean())
    left = end[:, LHIP] - end[:, RHIP]
    fwd = np.cross(left, spine)               # body forward (right-handed: left x up)
    fwd /= np.linalg.norm(fwd, axis=1, keepdims=True)
    face_up = float(fwd[:, 1].mean())
    t_down = round(float(down[0]) / motion.FPS, 2) if len(down) else None
    stays = bool((hips[-15:] < 0.35).all())
    lying = tilt > 55
    return {"t_down_s": t_down, "end_hips_m": round(float(end[:, HIPS, 1].mean()), 2), "end_tilt_deg": round(tilt, 0),
            "face_up": round(face_up, 2), "on_back": bool(lying and face_up > 0.5),
            "pose": "lying on back" if lying and face_up > 0.5 else "lying" if lying else "sitting" if hips[-1] < 0.35 else "up",
            "readable": bool(t_down is not None and t_down <= 2.0 and lying and stays)}


def main(which):
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    base = gen("a person crouches down low and hides", 2.2, 0, name="hb_crouch")
    if which in ("peek", "all"):
        variants = {
            "demo wording (no path)": ("a person leans to the left and peeks out", "left", False),
            "new wording (no path)": ("a person crouches and leans to the right to peek out", "right", False),
            "new wording + peek path": ("a person crouches and leans to the right to peek out", "right", True),
            "step-out wording + peek path": ("a person crouches, steps to the right and leans out to look, then steps back",
                                             "right", True),
        }
        out = {}
        for label, (prompt, side, use_path) in variants.items():
            rows = []
            for seed in SEEDS:
                n = gen(prompt, 2.5, seed, prev=base, path=peek_path(2.5, side) if use_path else None, name="hb_peek")
                rows.append(peek_metrics(n, side))
            out[label] = {"runs": rows, "mean_head_out_m": round(float(np.mean([r["head_out_max_m"] for r in rows])), 3),
                          "mean_beyond_edge_s": round(float(np.mean([r["beyond_edge_s"] for r in rows])), 2),
                          "peeks_past_edge": f"{sum(r['beyond_edge_s'] >= 0.4 for r in rows)}/{len(rows)}",
                          "back_in_cover": f"{sum(r['back_in_cover'] for r in rows)}/{len(rows)}"}
            print(label, json.dumps({k: v for k, v in out[label].items() if k != "runs"}), flush=True)
        # the demo's actual peek segments (t_hide: peek 1.7-3.7 s, again 5.2-7.7 s)
        demo = sorted((ROOT / "output").glob("rs_t_hide_*"))[-1].name
        out["demo clip (as rendered)"] = {"runs": [peek_metrics(demo, "left", 1.7, 3.7), peek_metrics(demo, "left", 5.2, 7.7)]}
        res["peek"] = out
    if which == "peek2":   # follow-up: is it the wording or the path, and does a bigger offset help?
        step = "a person crouches, steps to the right and leans out to look, then steps back"
        out = {}
        for label, (amount, use_path) in {"step-out wording (no path)": (0, False),
                                          "step-out wording + 0.6 m path": (0.6, True)}.items():
            rows = []
            for seed in SEEDS:
                n = gen(step, 2.5, seed, prev=base, path=peek_path(2.5, "right", amount) if use_path else None,
                        name="hb_peek")
                rows.append(peek_metrics(n, "right"))
            out[label] = {"runs": rows, "mean_head_out_m": round(float(np.mean([r["head_out_max_m"] for r in rows])), 3),
                          "mean_beyond_edge_s": round(float(np.mean([r["beyond_edge_s"] for r in rows])), 2),
                          "peeks_past_edge": f"{sum(r['beyond_edge_s'] >= 0.4 for r in rows)}/{len(rows)}",
                          "back_in_cover": f"{sum(r['back_in_cover'] for r in rows)}/{len(rows)}"}
            print(label, json.dumps({k: v for k, v in out[label].items() if k != "runs"}), flush=True)
        res.setdefault("peek", {}).update(out)
    if which in ("fall", "all"):
        variants = {
            "demo wording": "a person gets startled, jumps backward and falls down onto the ground",
            "falls backward onto their back": "a person gets startled and falls backward onto their back",
            "lands flat on their back": "a person falls backward and lands flat on their back",
        }
        out = {}
        for label, prompt in variants.items():
            rows = [fall_metrics(gen(prompt, 2.5, seed, prev=base, name="hb_fall")) for seed in SEEDS]
            out[label] = {"runs": rows, "readable": f"{sum(r['readable'] for r in rows)}/{len(rows)}",
                          "on_back": f"{sum(r['on_back'] for r in rows)}/{len(rows)}",
                          "poses": [r["pose"] for r in rows]}
            print(label, json.dumps({k: v for k, v in out[label].items() if k != "runs"}), flush=True)
        demo = sorted((ROOT / "output").glob("rs_t_fall_*"))[-1].name
        out["demo clip (as rendered)"] = {"runs": [fall_metrics(demo)]}
        res["fall"] = out
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=1))



if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
