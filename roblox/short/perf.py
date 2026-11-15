"""Per-version performances for the comparison short, evaluated per frame in Python and applied by ShortDirector.lua.

A (stock): what agent-made 'In This Town' shorts use today. Stock R15 animations only (idle, walk, run, jump, fall,
  sit, wave, point, cheer) played through the Animator, characters moved MoveTo-style in straight lines at Roblox's
  natural speeds (walk 8 studs/s, run 16, scaled by height) and turned like Humanoid.AutoRotate. Walk/run
  playback follows the default Animate script (walk/run blend and timewarp from speed). Creator tricks an agent
  would plausibly script are included: a Seat for sitting (stock sit pose, snaps in), turning the body to "look
  around", sliding sideways to "peek", tipping the character over for a fall, wave/point for "talking".
B (Promptimate): every beat generated (gen_b.py), one continue_from chain per character, played with
  PromptimatePlayer:Seek.
C (Roblox Prompt-to-Animation): A, with the non-stock beats replaced by generate_animation clips (gen_c.py), played
  as KeyframeSequences on the same rigs. Seat/ground height offsets per clip are calibrated (what a creator would
  tweak by hand); root motion inside the clips is left as generated.
"""
from __future__ import annotations

import json
import os
import math
from pathlib import Path

import numpy as np

import story as S

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache" / "roblox_short"

ID = {k: f"rbxassetid://{v}" for k, v in {
    "idle": 507766388, "walk": 507777826, "run": 507767714, "wave": 507770239, "point": 507770453,
    "cheer": 507770677, "laugh": 507770818, "sit": 2506281703, "fall": 507767968, "jump": 507765000}.items()}
LOOPED = {"idle", "walk", "run", "wave", "point", "laugh", "sit", "fall"}
HS = {w: c["height"] for w, c in S.CAST.items()}
FADE = 0.2


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def lerp_yaw(a, b, w):
    return a + wrap(b - a) * w


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------------------------------------ anim timelines
class Seg:
    """One stretch of a character's anim-mode timeline.
    tracks: [(key, speed, loop, offset)] or "loco" (Animate-script walk/run/idle from the path speed)."""

    def __init__(self, t0, t1, tracks, at=None, path=None, face=None, yoff=0.0, pitch=None, phone=False, side=None,
                 fade=FADE, yaws=None):
        self.t0, self.t1, self.tracks, self.at, self.path = t0, t1, tracks, at, path
        self.face, self.yoff, self.pitch, self.phone, self.side, self.fade, self.yaws = face, yoff, pitch, phone, side, fade, yaws

    def pos(self, t):
        if self.path:
            pts = self.path
            if t <= pts[0][0]:
                return np.array(pts[0][1], float), None
            for (ta, a), (tb, b) in zip(pts, pts[1:]):
                if t <= tb:
                    w = (t - ta) / max(tb - ta, 1e-6)
                    a, b = np.array(a, float), np.array(b, float)
                    return a + (b - a) * w, (b - a) / max(tb - ta, 1e-6)
            return np.array(pts[-1][1], float), None
        return np.array(self.at, float), None


def loco_tracks(v, hs, t_in):
    """Default R15 Animate script: walk/run weights and timewarp from the speed (studs/s)."""
    if v < 0.75 * hs:
        return [(ID["idle"], t_in, 1.0, True)]
    rs = v / (16.0 * hs)
    if rs <= 0.5:
        return [(ID["walk"], t_in * rs / 0.5, 1.0, True)]
    if rs < 1.0:
        f = (rs - 0.5) / 0.5
        return [(ID["walk"], t_in, 1 - f, True), (ID["run"], t_in, f, True)]
    return [(ID["run"], t_in * rs, 1.0, True)]


class AnimChar:
    def __init__(self, who, segs, hrp_y):
        self.who, self.segs, self.hrp_y = who, sorted(segs, key=lambda s: s.t0), hrp_y
        self._yaw_cache = {}

    def _seg(self, t):
        i = 0
        for k, s in enumerate(self.segs):
            if s.t0 <= t:
                i = k
        return i

    def _tracks(self, s, t):
        dt = t - s.t0
        if s.tracks == "loco":
            p, v = s.pos(t)
            return loco_tracks(float(np.linalg.norm(v)) if v is not None else 0.0, HS[self.who], dt)
        return [(key, dt * sp + off, 1.0, loop) for key, sp, loop, off in s.tracks]

    def _yaw_target(self, s, t):
        if s.yaws:                           # scripted body turns: [(t, yaw)] piecewise (smoothstep between keys)
            ks = s.yaws
            if t <= ks[0][0]:
                return ks[0][1]
            for (ta, a), (tb, b) in zip(ks, ks[1:]):
                if t <= tb:
                    return lerp_yaw(a, b, smooth((t - ta) / max(tb - ta, 1e-6)))
            return ks[-1][1]
        if s.face is not None:
            return s.face
        _, v = s.pos(t)
        if v is not None and np.linalg.norm(v) > 1e-3:
            return S.yaw_of(v / np.linalg.norm(v))
        return None

    def yaw(self, t):
        """AutoRotate-like: turn toward the target heading at ~10 rad/s (deterministic, integrated from t=0)."""
        step = 1.0 / 120
        key = round(t / step)
        if key in self._yaw_cache:
            return self._yaw_cache[key]
        k0 = max([k for k in self._yaw_cache if k <= key], default=None)
        if k0 is None:
            s = self.segs[0]
            y = self._yaw_target(s, s.t0)
            y = y if y is not None else 0.0
            k0 = round(s.t0 / step) if s.t0 > 0 else 0
            self._yaw_cache[k0] = y
            if key <= k0:
                return y
        y = self._yaw_cache[k0]
        for k in range(k0 + 1, key + 1):
            tt = k * step
            s = self.segs[self._seg(tt)]
            tgt = self._yaw_target(s, tt)
            if tgt is not None:
                d = wrap(tgt - y)
                y += max(-10 * step, min(10 * step, d)) if not s.yaws else d
            self._yaw_cache[k] = y
        return y

    def frame(self, t):
        i = self._seg(t)
        s = self.segs[i]
        p, _ = s.pos(t)
        if s.side is not None:           # sideways slide (peek trick): [(t, offset studs toward the character's left)]
            off = np.interp(t, [a for a, _ in s.side], [b for _, b in s.side])
            yw = self.yaw(t)
            f = np.array([-math.sin(yw), -math.cos(yw)])
            p = p + np.array([f[1], -f[0]]) * off
        w = smooth((t - s.t0) / s.fade) if (s.fade > 0 and i > 0) else 1.0
        tracks = [(k, tm, wt * w, lp) for k, tm, wt, lp in self._tracks(s, t)]
        yoff = s.yoff(t) if callable(s.yoff) else s.yoff
        if i > 0 and w < 1:
            ps = self.segs[i - 1]
            tracks += [(k, tm, wt * (1 - w), lp) for k, tm, wt, lp in self._tracks(ps, t)]
            pyo = ps.yoff(t) if callable(ps.yoff) else ps.yoff
            if abs(pyo - yoff) > 0.3 and s.tracks != "loco":   # seats snap in; small offsets blend
                pass
            else:
                yoff = pyo + (yoff - pyo) * w
        merged = {}
        for k, tm, wt, lp in tracks:
            if k in merged:
                merged[k] = (k, merged[k][1] if merged[k][2] >= wt else tm, merged[k][2] + wt, lp)
            else:
                merged[k] = (k, tm, wt, lp)
        pitch = 0.0
        if s.pitch:
            ta, tb, ang = s.pitch
            pitch = ang * smooth((t - ta) / max(tb - ta, 1e-6)) ** 1.6
        yw = self.yaw(t)
        y = self.hrp_y + yoff
        return ({"cf": [round(float(p[0]), 4), round(y, 4), round(float(p[1]), 4), round(yw, 5), round(pitch, 4)],
                 "tracks": [[k, round(tm, 4), round(wt, 4), lp] for k, tm, wt, lp in merged.values()],
                 "phone": s.phone},
                np.array([p[0], y + 0.9, p[1]]))


# ------------------------------------------------------------------------------------------------ A and C builders
def _dist(path):
    return sum(float(np.linalg.norm(np.subtract(b, a))) for (_, a), (_, b) in zip(path, path[1:]))


def move(t_end_or_start, pts, speed, align="end"):
    """Straight-line MoveTo path through points at constant speed; align='end' arrives at t, 'start' leaves at t."""
    pts = [np.array(p, float) for p in pts]
    total = sum(float(np.linalg.norm(b - a)) for a, b in zip(pts, pts[1:]))
    dur = total / speed
    t0 = t_end_or_start - dur if align == "end" else t_end_or_start
    out, t, prev = [(t0, tuple(pts[0]))], t0, pts[0]
    for p in pts[1:]:
        t += float(np.linalg.norm(p - prev)) / speed
        out.append((t, tuple(p)))
        prev = p
    return out


def stock_timeline(who, cal, gens=None):
    """A when gens is None; C when gens maps beat keys to generated KeyframeSequence names."""
    G = gens or {}
    hs = HS[who]
    walk_v, run_v = 8.0 * hs, 16.0 * hs
    T = S.T
    PZ, NX, PX, NZ = (S.yaw_of(S.PZ), S.yaw_of(S.NX), S.yaw_of(S.PX), S.yaw_of(S.NZ))
    idle = [(ID["idle"], 1, True, 0)]
    seat = tuple(cal["seat"]) if "seat" in cal else (S.BENCH["center"][0], S.BENCH["center"][1] + 0.4)
    segs = []

    def kfs(key):
        return [("kfs:" + G[key], 1, False, 0)]

    if who == "timmy":
        wpath = move(T["timmy_walk"][1], [p for _, p in S.PATHS["timmy_walk"]], walk_v)
        segs += [Seg(0, wpath[0][0], idle, at=wpath[0][1], face=PX),
                 Seg(wpath[0][0], T["timmy_walk"][1], "loco", path=wpath)]
        stand = S.PATHS["timmy_walk"][-1][1]
        if "t_sit" in G:   # C: turn to the bench and play the generated sit
            segs.append(Seg(4.0, 7.0, kfs("t_sit"), at=(stand[0], stand[1] + cal.get("c_sit_dz", 0.0)), face=PZ,
                            yoff=cal.get("c_sit_y", 0.0)))
            segs.append(Seg(7.0, 10.5, kfs("t_phone"), at=(stand[0], stand[1] + cal.get("c_phone_dz", 0.0)), face=PZ,
                            yoff=cal.get("c_phone_y", 0.0), phone=True))
            segs.append(Seg(10.5, 12.5, kfs("t_up"), at=(stand[0], stand[1] + cal.get("c_up_dz", 0.0)), face=PZ,
                            yoff=cal.get("c_up_y", 0.0)))   # Roblox needed 2 s for the stand-up (1 s failed)
        else:              # A: Seat -> stock sit pose (snaps into the seat), jump out
            segs.append(Seg(4.0, 4.25, idle, at=stand, face=PZ))
            segs.append(Seg(4.25, 10.5, [(ID["sit"], 1, True, 0)], at=seat, face=PZ, yoff=cal["a_sit_y"], fade=0.1))
            segs.append(Seg(7.0, 10.5, [(ID["sit"], 1, True, 0)], at=seat, face=PZ, yoff=cal["a_sit_y"], fade=0, phone=True))
            hop = lambda t: cal["a_sit_y"] * (1 - smooth((t - 10.5) / 0.55)) + 2.2 * math.sin(math.pi * min(1, max(0, (t - 10.5) / 0.55)))  # noqa: E731
            segs.append(Seg(10.5, 11.05, [(ID["jump"], 1, False, 0)], path=[(10.5, seat), (11.05, stand)], face=PZ, yoff=hop, fade=0.1))
            segs.append(Seg(11.05, 11.5, idle, at=stand, face=PZ))
        run_t = 12.5 if "t_up" in G else 11.5
        rpath = move(run_t, [p for _, p in S.PATHS["timmy_run"]], run_v, align="start")
        segs.append(Seg(run_t, rpath[-1][0], "loco", path=rpath))
        hide = S.TIMMY_HIDE
        if "t_hide" in G:
            segs.append(Seg(rpath[-1][0], 15.3, idle, at=hide, face=NX))
            segs.append(Seg(15.3, 23.0, kfs("t_hide"), at=hide, face=NX, yoff=cal.get("c_hide_y", 0.0)))
            segs.append(Seg(23.0, 25.5, kfs("t_fall"), at=hide, face=NX, yoff=cal.get("c_fall_y", 0.0)))
            segs.append(Seg(25.5, S.END + 1, kfs("t_ground"), at=hide, face=NX, yoff=cal.get("c_ground_y", 0.0)))
        else:
            # hide: stand behind the crates; peek = slide toward the left (street side) and back, twice
            side = [(15.3, 0), (16.6, 0), (17.1, 1.6), (18.4, 1.6), (18.9, 0), (19.8, 0), (20.4, 1.8), (23.0, 1.8)]
            segs.append(Seg(rpath[-1][0], 23.0, idle, at=hide, face=NX, side=side))
            segs.append(Seg(23.0, 23.6, [(ID["jump"], 1, False, 0)], at=hide, face=NX,
                            yoff=lambda t: 1.6 * math.sin(math.pi * min(1, max(0, (t - 23.0) / 0.6))), side=[(23.0, 1.8)], fade=0.08))
            segs.append(Seg(23.6, S.END + 1, [(ID["fall"], 1, True, 0)], at=hide, face=NX, pitch=(23.6, 24.1, math.radians(84)),
                            side=[(23.6, 1.8)], fade=0.1))
    elif who == "officer":
        wpath = move(T["officer_walk"][1], [p for _, p in S.PATHS["officer_walk"]], walk_v)
        segs += [Seg(0, wpath[0][0], idle, at=wpath[0][1], face=PX), Seg(wpath[0][0], 13.5, "loco", path=wpath)]
        stop = S.PATHS["officer_walk"][-1][1]
        if "o_look" in G:
            segs.append(Seg(13.5, 16.5, kfs("o_look"), at=stop, face=PX))
        else:
            segs.append(Seg(13.5, 16.5, idle, at=stop, yaws=[(13.5, PX), (14.2, PX + 0.8), (15.0, PX + 0.8), (15.8, PX - 0.8), (16.5, PX - 0.6)]))
        segs.append(Seg(16.5, 18.5, idle, at=stop, yaws=[(16.5, PX - 0.6), (17.0, NZ + 0.2), (18.5, NZ + 0.2)]))
        w2 = move(T["officer_walk2"][1] - 0.4, [p for _, p in S.PATHS["officer_walk2"]], walk_v)
        segs.append(Seg(18.5, w2[0][0], idle, at=stop, face=NZ + 0.2))
        segs.append(Seg(w2[0][0], w2[-1][0], "loco", path=w2))
        scare = S.OFFICER_SCARE
        face_t = S.yaw_of(tuple(np.subtract(S.TIMMY_HIDE, scare) / np.linalg.norm(np.subtract(S.TIMMY_HIDE, scare))))
        segs.append(Seg(w2[-1][0], 23.0, idle, at=scare, face=face_t))
        segs.append(Seg(23.0, 24.4, [(ID["cheer"], 1.3, False, 0)], at=scare, face=face_t, fade=0.1))
        segs.append(Seg(24.4, 25.5, idle, at=scare, face=face_t))
        if "o_talk" in G:
            segs.append(Seg(25.5, 29.0, kfs("o_talk"), at=scare, face=face_t))
            segs.append(Seg(29.0, S.END + 1, kfs("o_sit"), at=scare, face=face_t, yoff=cal.get("c_osit_y", 0.0)))
        else:
            segs.append(Seg(25.5, 27.25, [(ID["point"], 1, True, 0)], at=scare, face=face_t))
            segs.append(Seg(27.25, 29.0, [(ID["wave"], 1, True, 0)], at=scare, face=face_t))
            segs.append(Seg(29.0, 29.25, idle, at=scare, face=face_t))
            segs.append(Seg(29.25, S.END + 1, [(ID["sit"], 1, True, 0)], at=scare, face=face_t, yoff=cal["a_gsit_y"], fade=0.1))
    elif who == "lee":
        door = S.LEE_DOOR
        to_crates = S.yaw_of(tuple(np.subtract(S.CRATES, door) / np.linalg.norm(np.subtract(S.CRATES, door))))
        segs.append(Seg(0, 16.5, idle, at=door, face=PZ))
        segs.append(Seg(16.5, 19.0, [(ID["point"], 1, True, 0)], at=door, face=to_crates, fade=0.1))
        segs.append(Seg(19.0, S.END + 1, idle, at=door, face=PZ))
    return segs


# ------------------------------------------------------------------------------------------------ B (Promptimate)
class PMChar:
    def __init__(self, who, clips, stand):
        self.who, self.clips, self.stand = who, clips, stand
        for c in clips:
            d = json.loads((ROOT / "roblox" / "out" / f"{c['module']}.json").read_text())
            c["_root"] = np.array(d["root"], float)
            c["_fps"] = d["fps"]

    def frame(self, t):
        k = 0
        for i, c in enumerate(self.clips):
            if c["start"] <= t:
                k = i
        c = self.clips[k]
        lt = min(max(t - c["start"], 0.0), c["dur"])
        f = lt * c["_fps"]
        i0 = int(math.floor(f))
        i1 = min(i0 + 1, len(c["_root"]) - 1)
        a = f - i0
        r = c["_root"][i0] * (1 - a) + c["_root"][i1] * a
        o = c["origin"]
        yw = o["yaw"]
        # Roblox local (x right, -z forward) rotated by yaw about Y
        lx, ly, lz = r * self.stand
        wx = o["x"] + math.cos(yw) * lx + math.sin(yw) * lz
        wz = o["z"] - math.sin(yw) * lx + math.cos(yw) * lz
        phone = c["key"] == "t_phone"
        return ({"pm": [c["module"], round(lt, 4), o["x"], o["z"], o["yaw"]], "phone": phone}, np.array([wx, ly, wz]))


# ------------------------------------------------------------------------------------------------ assembly
def build(version: str, setup: dict):
    """version 'A' | 'B' | 'C' -> {who: char}; setup = ShortDirector.setup() result (stand, hrpY per character)."""
    cal = json.loads((CACHE / "calibration.json").read_text()) if (CACHE / "calibration.json").exists() else {}
    chars = {}
    if version == "B":
        chains = json.loads(Path(os.environ.get("RS_CHAINS", CACHE / "b_chains.json")).read_text())["chars"]
        for who, clips in chains.items():
            for c in clips:
                c["module"] = "rs_" + c["key"]
            chars[who] = PMChar(who, clips, setup[who]["stand"])
        return chars
    gens = None
    if version == "C":
        g = json.loads((CACHE / "c_gens.json").read_text())
        gens = {k: v["clip"] for k, v in g.items() if v.get("clip")}
    for who in S.CAST:
        chars[who] = AnimChar(who, stock_timeline(who, cal.get(version, {}), gens), setup[who]["hrpY"])
    return chars


def frame(chars, t):
    inst, hips = {}, {}
    for who, ch in chars.items():
        inst[who], hips[who] = ch.frame(t)
    return inst, hips
