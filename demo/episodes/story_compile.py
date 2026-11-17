"""Compact story spec -> full episode module (eps/<slug>.py), deterministically.

A writer only fills in the story: cast looks, which own set each scene plays in, where people stand (the set's named
spots), the narration lines and, per line, what each character does from a fixed ACTIONS vocabulary. Everything else
(coordinates, facing, beats, cameras, faces, props, labels, FX, SFX, titles) is derived here. Fixed vocabulary + fixed
durations = every in-place beat is a motion-library clip that the generation cache already holds.

    python demo/episodes/story_compile.py demo/episodes/stories/<slug>.py   # writes demo/episodes/eps/<slug>.py

Spec (a Python file defining these names):
    TITLE = "In This Town, ..."
    MUSIC = "whimsical"                      # one of MUSIC_MOODS
    KEYWORDS = ["coin", ...]                 # caption words that pop in yellow
    CAST = {"Rosa": "c_grandma", ...}        # character -> look (LOOKS)
    SCENES = [{"set": "Bakery",              # one of the own sets (maps in D:\\tmp\\headless\\own\\sets\\maps)
               "place": {"Rosa": "behind_case", "Gus": "door"},   # spot name, or "spot:dx,dz" offset in studs
               "props": [{"name": "Coins", "prop": "coin_pile", "at": "case_front", "small": True},
                         {"name": "Bread", "prop": "bread", "hold": "Gus"}],
               "lines": [{"id": "rule", "say": "In this town, ...",
                          "do": {"Rosa": "happy clap@Gus joy", "Gus": "walk>Rosa talk thumbs"},
                          "cam": ["Rosa", "Gus+Rosa", "Coins"],       # cuts spread over the line
                          "feel": {"Rosa": "grin"}, "label": "+1 COIN", "fx": {"Rosa": "sparkle"},
                          "sfx": "coin drop", "show": ["Coins"], "hide": [], "title": "COMPLIMENTS"}]}]
    action syntax: "<action>" | "<action>@<who or +X/-X/+Z/-Z or camera>" (face at the end) |
                   "<walk action>><who or spot>" (go there)
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OWN = Path(r"D:\tmp\headless\own")
MAPS = OWN / "sets" / "maps"

# action -> (prompt, seconds). Prompts are shared across episodes: the motion library is keyed on (prompt, seconds).
ACTIONS = {
    # standing / reacting
    "happy": ("a person stands and smiles happily", 2.5),
    "sad": ("a person stands alone with their head down, sad", 3.0),
    "stare": ("a person stares in surprise", 2.5),
    "talk": ("a person stands and talks, gesturing with both hands", 2.5),
    "shrug": ("a person shrugs", 2.0),
    "wave": ("a person waves with their right hand", 2.0),
    "nod": ("a person nods slowly", 2.0),
    "shake": ("a person shakes their head slowly, disappointed", 2.5),
    "no": ("a person shakes their head quickly", 1.5),
    "point": ("a person points forward sternly", 2.0),
    "point_smile": ("a person points forward with their right hand and smiles", 2.0),
    "laugh_at": ("a person points forward and laughs", 2.5),
    "stomp": ("a person stomps their foot down hard", 2.0),
    "bow": ("a person bows deeply", 2.0),
    "cry": ("a person covers their face with both hands and cries", 2.5),
    "look_self": ("a person looks down at their own body in shock", 2.0),
    "reach": ("a person reaches forward slowly with their right hand", 2.5),
    "hug": ("a person steps forward and hugs someone tightly", 2.5),
    "pocket": ("a person reaches into their pocket and pulls something out", 2.0),
    "flex": ("a person flexes both arms proudly", 1.5),
    "clap": ("a person claps their hands excitedly", 2.0),
    "thumbs": ("a person gives a thumbs up with their right hand", 2.0),
    "spread": ("a person spreads both arms wide proudly", 2.0),
    "hips": ("a person stands with their hands on their hips, unimpressed", 3.0),
    "frustrated": ("a person throws both arms up in frustration", 2.0),
    "spin": ("a person turns around in a full circle, showing off", 2.5),
    "look_back": ("a person looks back over their right shoulder", 2.0),
    "shake_it": ("a person holds something upside down with both hands and shakes it", 2.5),
    "hand_out": ("a person holds out their right hand, palm up, with their head down", 3.5),
    "hope": ("a person clasps their hands together in front of their chest", 2.5),
    "look_hand": ("a person looks down at their right hand", 2.0),
    "heart": ("a person puts their right hand on their chest and smiles", 3.0),
    "belly": ("a person rubs their belly happily", 2.0),
    "snub": ("a person turns away and crosses their arms", 2.5),
    "joy": ("a person jumps up and down with joy, arms in the air", 2.5),
    "scared": ("a person steps back in fear with their hands up", 2.0),
    "think": ("a person scratches their head, thinking", 2.5),
    "facepalm": ("a person slaps their forehead with their right hand", 2.0),
    "dance": ("a person dances happily, bouncing to the music", 3.0),
    "cheer": ("a person pumps their fist in the air and cheers", 2.0),
    "angry": ("a person clenches their fists and shakes them angrily", 2.0),
    "yawn": ("a person stretches their arms up and yawns", 2.5),
    "salute": ("a person salutes with their right hand", 2.0),
    "phone": ("a person holds a phone up to their ear and talks", 3.0),
    "write": ("a person writes on a notepad held in their left hand", 2.5),
    "eat": ("a person eats, bringing their right hand to their mouth", 2.5),
    "gasp": ("a person gasps and covers their mouth with both hands", 2.0),
    "beg": ("a person kneels down and begs with their hands together", 3.0),
    "faint": ("a person faints and falls backward onto the ground", 3.0),
    "give": ("a person holds out something in both hands, offering it", 2.0),
    "count": ("a person counts on their fingers", 2.5),
    "whisper": ("a person leans forward and whispers, a hand beside their mouth", 2.0),
    "cross_arms": ("a person stands with their arms crossed", 3.0),
    # going somewhere (need ">target")
    "walk": ("a person walks forward casually", 2.5),
    "walk_sad": ("a person walks forward slowly with their head down", 2.5),
    "walk_happy": ("a person walks forward happily, swinging their arms", 2.5),
    "march": ("a person marches forward confidently, swinging their arms", 3.0),
    "run": ("a person runs forward", 2.0),
    "sneak": ("a person sneaks forward on tiptoes", 3.0),
}
MOVES = {"walk", "walk_sad", "walk_happy", "march", "run", "sneak"}
REACT = {"happy": "clap", "grin": "laugh_at", "love": "heart", "sad": "sad", "crying": "cry", "shocked": "gasp",
         "scared": "scared", "angry": "angry", "smug": "cross_arms", "tired": "yawn", "wink": "thumbs", "neutral": "nod"}
FEELINGS = ["neutral", "happy", "grin", "sad", "crying", "shocked", "scared", "angry", "smug", "tired", "wink", "love"]
FX_KINDS = ["sparkle", "rain", "confetti", "hearts", "dizzy", "zzz", "anger", "sweat", "poof"]
SIGN_STYLES = ["wood", "red", "blue", "green", "black", "white", "gold"]
MUSIC_MOODS = ["whimsical", "happy", "funny", "dance", "mysterious", "piano", "creepy"]
WORDS_PER_S = 3.4           # tv_M2 at 1.2x with trimmed sentence gaps (audio hill-climb, 2026-11-18)
HAND = [0, -0.6, -0.3, 0, 0, 0]
SPREAD = 12.0             # studs: people placed further than this from a scene's first person are moved beside them


def sfx_names() -> list[str]:
    m = HERE / "build" / "_media"
    return sorted(p.stem[len("sound_effect_"):-2].replace("_", " ") for p in m.glob("sound_effect_*_0.json"))


def looks() -> list[str]:
    return sorted(json.loads((OWN / "looks.json").read_text()))


def set_maps() -> dict:
    return {p.stem: json.loads(p.read_text()) for p in sorted(MAPS.glob("*.json"))}


def catalog() -> str:
    """Everything a writer may use, as compact text (for the writer prompt)."""
    out = ["ACTIONS (key: what the body does, seconds):"]
    out += [f"  {k}{' (needs >target)' if k in MOVES else ''}: {p[len('a person '):]} ({s:g}s)" for k, (p, s) in ACTIONS.items()]
    out.append("FEELINGS (face): " + ", ".join(FEELINGS))
    out.append("FX: " + ", ".join(FX_KINDS) + "   (labels: short ALL-CAPS text over the shot)")
    out.append("SIGN STYLES: " + ", ".join(SIGN_STYLES))
    out.append("SFX: " + ", ".join(sfx_names()))
    out.append("MUSIC: " + ", ".join(MUSIC_MOODS))
    out.append("LOOKS: " + ", ".join(looks()))
    props = json.loads((OWN / "props.json").read_text())
    out.append("PROPS: " + ", ".join(sorted(props)))
    out.append("SETS (spot names; sit spots are not usable yet):")
    for name, m in set_maps().items():
        sp = ", ".join(f"{s['name']}" + (f" ({s['note']})" if s.get("note") else "") for s in m["spots"] if s["kind"] == "stand")
        out.append(f"  {name}: {sp}")
    return "\n".join(out)


# ------------------------------------------------------------------------------------------------ compiler
def _yaw_dir(yaw: float) -> tuple[float, float]:
    r = math.radians(yaw)       # 0 faces -Z, 90 faces -X, 180 faces +Z
    return (-math.sin(r), -math.cos(r))


_WORLD = None


def _free_spot(x: float, z: float, floor: float, others, r: float = 2.2, apart: float = 3.5):
    """The nearest standing place to (x, z), checked against the set geometry (stage.World: furniture, fountains,
    benches) and at least `apart` studs from people already placed. Spiral search out to 10 studs."""
    global _WORLD
    if _WORLD is None:
        sys.path.insert(0, str(HERE.parents[1] / "roblox" / "headless"))
        import stage
        _WORLD = stage.World(json.loads((OWN / "scene_static.json").read_text()), [])
    cands = [(x, z)]
    for rad in (1.0, 2.0, 3.0, 4.0, 5.5, 7.0, 8.5, 10.0):
        n = int(6 * rad)
        cands += [(x + rad * math.cos(2 * math.pi * k / n), z + rad * math.sin(2 * math.pi * k / n)) for k in range(n)]
    ok_apart = [all(math.hypot(cx - ox, cz - oz) >= apart for ox, oz in others) for cx, cz in cands]
    pre = [c for c, ok in zip(cands, ok_apart) if ok]
    free = _WORLD.stand_free({"pts": pre, "floor": floor, "r": r, "h": 4.6})
    for c, f in zip(pre, free):
        if f:
            return round(c[0], 2), round(c[1], 2)
    return x, z


def _free_spot_ok(x, z, floor, r=1.6):
    _free_spot(x, z, floor, [], r=r)      # loads the world
    return bool(_WORLD.stand_free({"pts": [(x, z)], "floor": floor, "r": r, "h": 4.6})[0])


def _est(text: str, gap: float = 0.0) -> float:
    return len(text.split()) / WORDS_PER_S + gap


def _clean_names(spec) -> None:
    """One-word character names everywhere ("Mama Dot" -> "MamaDot"), also inside action strings and cuts."""
    ren = {n: re.sub(r"\W", "", n) for n in spec.CAST}
    ren = {a: b for a, b in ren.items() if a != b}
    if not ren:
        return
    order = sorted(ren, key=len, reverse=True)

    def txt(v):
        for a in order:
            v = v.replace(a, ren[a])
        return v

    def keys(d):
        return {ren.get(k, k): v for k, v in d.items()}
    spec.CAST = keys(spec.CAST)
    for sc in spec.SCENES:
        sc["place"] = keys(sc.get("place", {}))
        for p in sc.get("props", []):
            for k in ("hold", "at"):
                if isinstance(p.get(k), str):
                    p[k] = ren.get(p[k], p[k])
        for ln in sc["lines"]:
            ln["do"] = {ren.get(k, k): txt(v) for k, v in ln.get("do", {}).items()}
            for k in ("feel", "fx"):
                if isinstance(ln.get(k), dict):
                    ln[k] = keys(ln[k])
            c = ln.get("cam")
            if c:
                ln["cam"] = [txt(x) for x in c] if isinstance(c, list) else txt(c)


def compile_story(spec, slug: str) -> str:
    _clean_names(spec)
    maps = set_maps()
    lks = set(looks())
    sfx_ok = set(sfx_names())
    props_ok = set(json.loads((OWN / "props.json").read_text()))
    warn = []
    sets_of = {}
    for sc in spec.SCENES:
        for ch in sc.get("place", {}):
            sets_of.setdefault(ch, [])
            if sc["set"] not in sets_of[ch]:
                sets_of[ch].append(sc["set"])

    def copy(ch, st):
        return ch if len(sets_of.get(ch, [st])) <= 1 else f"{ch}{st[:3]}"

    cast, actors, pos, facing = [], {}, {}, {}
    for sc in spec.SCENES:
        m = maps[sc["set"]]
        spots = {s["name"]: s for s in m["spots"]}
        here0 = [copy(c, sc["set"]) for c in sc.get("place", {})]
        anchor = next((pos[n] for n in here0 if n in pos), None)
        k_side = 0
        for ch, where in sc.get("place", {}).items():
            n = copy(ch, sc["set"])
            if n in actors:
                continue
            nm, _, off = where.partition(":")
            s = spots.get(nm)
            if s is None:
                warn.append(f"{ch}: no spot {nm!r} in {sc['set']}; using {m['spots'][0]['name']}")
                s = m["spots"][0]
            dx, dz = (float(v) for v in off.split(",")) if off else (0.0, 0.0)
            x, z = round(s["x"] + dx, 2), round(s["z"] + dz, 2)
            sx_, sz_ = m.get("camera_side", [-1, 0])
            yaw = round(math.degrees(math.atan2(-sx_, -sz_)), 1)
            if anchor is None:
                anchor = (x, z)
            elif math.hypot(x - anchor[0], z - anchor[1]) > SPREAD:
                # too far from the scene's first person (spots can be 40+ studs apart): stand beside them as the
                # camera sees it, facing them
                sx, sz = m.get("camera_side", [-1, 0])
                k_side += 1
                side = (1 if k_side % 2 else -1) * 5.0 * ((k_side + 1) // 2)
                x, z = round(anchor[0] - sz * side + sx * 1.5, 2), round(anchor[1] + sx * side + sz * 1.5, 2)
                fx, fz = anchor[0] - x, anchor[1] - z
                yaw = round(math.degrees(math.atan2(-fx, -fz)), 1)
                warn.append(f"{ch}: {where} is far from the others in {sc['set']}; placed beside them")
            others = [pos[o] for o in pos if o in [copy(c2, sc["set"]) for c2 in sc.get("place", {})]]
            fx_, fz_ = _free_spot(x, z, m.get("floor_y", 0.0), others)
            if (fx_, fz_) != (x, z):
                warn.append(f"{ch}: {where} is blocked or crowded in {sc['set']}; moved {math.hypot(fx_ - x, fz_ - z):.1f} studs")
                x, z = fx_, fz_
            look = spec.CAST.get(ch, "c_man")
            if look not in lks:
                warn.append(f"{ch}: unknown look {look!r}")
                look = "c_man"
            cast.append({"name": n, "look": look, "at": [x, z], "yaw": yaw})
            fx, fz = _yaw_dir(yaw)
            actors[n] = {"name": n, "start": [x, z], "facing": [round(x + fx * 5, 2), round(z + fz * 5, 2)], "beats": []}
            pos[n], facing[n] = (x, z), (fx, fz)

    # ---- stage lines (the reference shorts' blocking): a scene's cast stands on one line across the open middle of
    # the set, facing the camera side, 4.5 studs apart, in the left-to-right order of the spots the writer chose. Frontal
    # shots then have a clear view of everyone (no walls, poles or backs between the camera and a face).
    if os.environ.get("PROMPTIMATE_STAGE", "line") == "line":
        restaged = set()
        for sc in spec.SCENES:
            m = maps[sc["set"]]
            sx_, sz_ = m.get("camera_side", [-1, 0])
            names_ = [copy(ch, sc["set"]) for ch in sc.get("place", {})]
            new_ = [n for n in names_ if n in pos and n not in restaged]
            if not new_:
                continue
            bx, bz = m["bounds"]["x"], m["bounds"]["z"]
            # the line's centre: the open floor between the set's middle and its camera side
            cx0, cz0 = (bx[0] + bx[1]) / 2, (bz[0] + bz[1]) / 2
            half = abs(sx_) * (bx[1] - bx[0]) / 2 + abs(sz_) * (bz[1] - bz[0]) / 2
            cx0, cz0 = cx0 + sx_ * min(4.0, half * 0.25), cz0 + sz_ * min(4.0, half * 0.25)
            px_, pz_ = -sz_, sx_                      # along the line (the camera's left-right)
            order = sorted(new_, key=lambda n: (pos[n][0] - cx0) * px_ + (pos[n][1] - cz0) * pz_)
            k_ = len(order)
            fy = m.get("floor_y", 0.0)
            placed_ = [pos[n] for n in names_ if n in restaged]
            yaw_ = round(math.degrees(math.atan2(-sx_, -sz_)), 1)
            for j, n in enumerate(order):
                off = (j - (k_ - 1) / 2) * 4.5
                x_, z_ = cx0 + px_ * off, cz0 + pz_ * off
                x_, z_ = _free_spot(x_, z_, fy, placed_, r=1.6, apart=3.8)
                pos[n] = (x_, z_)
                facing[n] = _yaw_dir(yaw_)
                placed_.append((x_, z_))
                restaged.add(n)
                for c in cast:
                    if c["name"] == n:
                        c["at"], c["yaw"] = [x_, z_], yaw_
                fx_, fz_ = _yaw_dir(yaw_)
                actors[n]["start"] = [x_, z_]
                actors[n]["facing"] = [round(x_ + fx_ * 5, 2), round(z_ + fz_ * 5, 2)]

    # ---- extras: each scene gets a crowd behind and around the cast, facing the action (library actions only)
    import random as _rnd
    rng = _rnd.Random(len(spec.TITLE))
    used_looks = {c["look"] for c in cast}
    spare = [l_ for l_ in sorted(lks) if l_ not in used_looks and not l_.startswith("mannequin")]
    extra_moves = ["happy", "clap", "talk", "nod", "cross_arms", "cheer", "point_smile", "laugh_at", "shrug", "wave"]
    n_extra = 0
    for sc in spec.SCENES:
        want = int(sc.get("extras", 8))
        if want <= 0 or not spare:
            continue
        m = maps[sc["set"]]
        sx_, sz_ = m.get("camera_side", [-1, 0])
        mains = [pos[copy(ch, sc["set"])] for ch in sc.get("place", {}) if copy(ch, sc["set"]) in pos]
        if not mains:
            continue
        cx_ = sum(q[0] for q in mains) / len(mains)
        cz_ = sum(q[1] for q in mains) / len(mains)
        taken = list(mains)
        for k in range(want * 3):
            if sum(1 for a_ in actors if a_.startswith(f"x{sc['set'][:3]}")) >= want:
                break
            back = rng.uniform(4.0, 13.0)
            side = rng.uniform(-11.0, 11.0)
            x0, z0 = cx_ - sx_ * back + (-sz_) * side, cz_ - sz_ * back + sx_ * side
            fx_, fz_ = _free_spot(x0, z0, m.get("floor_y", 0.0), taken, r=1.6, apart=3.0)
            if (fx_, fz_) == (x0, z0) and not _free_spot_ok(x0, z0, m.get("floor_y", 0.0)):
                continue
            n_extra += 1
            nm = f"x{sc['set'][:3]}{n_extra}"
            look = spare[(n_extra * 7) % len(spare)]
            # face the cast centre, cheated toward the camera
            dx_, dz_ = cx_ - fx_, cz_ - fz_
            dn_ = math.hypot(dx_, dz_) or 1.0
            gx_, gz_ = 0.6 * dx_ / dn_ + sx_, 0.6 * dz_ / dn_ + sz_
            yaw_ = round(math.degrees(math.atan2(-gx_, -gz_)), 1)
            cast.append({"name": nm, "look": look, "at": [fx_, fz_], "yaw": yaw_})
            first = sc["lines"][0]["id"]
            mv = extra_moves[n_extra % len(extra_moves)]
            beats = [{"at": f"@{first}+{rng.uniform(0.2, 2.5):.1f}", "prompt": ACTIONS[mv][0], "seconds": ACTIONS[mv][1]}]
            mv2 = extra_moves[(n_extra * 3) % len(extra_moves)]
            beats.append({"prompt": ACTIONS[mv2][0], "seconds": ACTIONS[mv2][1]})
            actors[nm] = {"name": nm, "start": [fx_, fz_], "facing": [round(fx_ + gx_ * 5, 2), round(fz_ + gz_ * 5, 2)],
                          "beats": beats}
            pos[nm], facing[nm] = (fx_, fz_), _yaw_dir(yaw_)
            taken.append((fx_, fz_))
    lines, cams, faces, place, props, fxs, sfx, titles = [], [], {}, [], [], [], [], []
    shown = {}     # prop name -> start ref of its open interval
    events = []
    cur_look = {c["name"]: c["look"] for c in cast}
    cur_scale = {}
    char_state = {}       # character -> {"scale", "look"} carried into its copies in later scenes
    started = set()
    introduced = set()
    last_feel = {}
    first_line = {}
    prev_set, k_cam = None, 0
    line_ids = []
    for sc in spec.SCENES:
        st = sc["set"]
        m = maps[st]
        spots = {s["name"]: s for s in m["spots"]}
        fy = m.get("floor_y", 0.0)
        here = {ch: copy(ch, st) for ch in sc.get("place", {})}
        csx, csz = m.get("camera_side", [-1, 0])

        def cheat(a_, b_, csx=csx, csz=csz):
            """Face a partner the film way: halfway between them and the camera side, so the face stays open to the
            camera (judges: backs of heads, both figures seen from behind)."""
            (ax, az), (bx, bz) = pos[a_], pos[b_]
            dx, dz = bx - ax, bz - az
            dn = math.hypot(dx, dz) or 1.0
            fx, fz = 0.45 * dx / dn + csx, 0.45 * dz / dn + csz
            fn = math.hypot(fx, fz) or 1.0
            return [round(ax + fx / fn * 5, 2), round(az + fz / fn * 5, 2)]
        for n in here.values():
            first_line.setdefault(n, sc["lines"][0]["id"])
        for p in sc.get("props", []):
            if any(q["name"] == p["name"] for q in props):
                continue          # the same prop declared again when a set is revisited: it's already there
            if p.get("sign"):
                p = dict(p, prop="sign")
            elif p.get("prop") not in props_ok:
                warn.append(f"prop {p.get('prop')!r} unknown, skipped")
                continue
            if p.get("hold") in here:
                a = here[p["hold"]]
                (x, z), (fx, fz) = pos[a], facing[a]
                at = [round(x - fx * 1.4, 2), round(z - fz * 1.4, 2)]
            elif p.get("at") in here:
                a = here[p["at"]]
                (x, z), (fx, fz) = pos[a], facing[a]
                at = [round(x + fx * 1.6 + fz * 1.2, 2), round(z + fz * 1.6 - fx * 1.2, 2)]
            else:
                nm, _, off = str(p.get("at", "")).partition(":")
                s = spots.get(nm, m["spots"][0])
                dx, dz = (float(v) for v in off.split(",")) if off else (0.0, 0.0)
                at = [round(s["x"] + dx, 2), round(s["z"] + dz, 2)]
            e = {"prop": p["prop"], "at": at, "y": fy, "yaw": p.get("yaw", 0), "name": p["name"]}
            if p["prop"] == "sign":
                sx, sz = m.get("camera_side", [-1, 0])
                e.update(text=str(p["sign"]), style=p.get("style", "wood") if p.get("style") in SIGN_STYLES else "wood",
                         width=float(p.get("width", 4.0)), stand=not p.get("hold"),
                         yaw=p.get("yaw", round(math.degrees(math.atan2(-sx, -sz)), 1)))
                if p.get("hold"):
                    e["width"] = float(p.get("width", 1.6))
            if p.get("small"):
                e["height"] = 0.35
            elif p.get("height"):
                e["height"] = p["height"]
            place.append(e)
            props.append({"name": p["name"], "show": [], **({"attach": {"actor": here[p["hold"]], "hand": "Right",
                                                                          "offset": HAND}} if p.get("hold") in here else {})})
        for ch_, a_ in here.items():
            if a_ in started:
                continue
            started.add(a_)
            stt = char_state.get(ch_, {})
            first_id = sc["lines"][0]["id"]
            if abs(stt.get("scale", 1.0) - 1) > 1e-3:
                events.append({"kind": "scale", "actor": a_, "at": f"@{first_id}-0.3", "to": stt["scale"], "over": 0.05})
                cur_scale[a_] = stt["scale"]
            if stt.get("look") and stt["look"] != cur_look.get(a_):
                events.append({"kind": "look", "actor": a_, "at": f"@{first_id}-0.3", "look": stt["look"]})
                cur_look[a_] = stt["look"]
        for ln in sc["lines"]:
            lid = ln["id"]
            line_ids.append(lid)
            dur = _est(ln["say"], ln.get("gap", 0.0))
            lines.append({"id": lid, "text": ln["say"], **({"gap": ln["gap"]} if ln.get("gap") else {})})
            # cameras: an establishing wide shot on a set change, then the line's cuts spread over its length
            cuts = ln.get("cam") or [next(iter(ln.get("do", {})), next(iter(here)))]
            cuts = list(cuts) if isinstance(cuts, list) else [cuts]
            # the person the line names is on screen when it starts (judges: "keep the same character on screen while
            # the narration names them")
            named = [ch for ch in here if re.search(r"" + re.escape(ch) + r"", ln["say"], re.I)]
            if named and not any(c_.split("+")[0] in named or (len(c_.split("+")) > 1 and c_.split("+")[1] in named)
                                 for c_ in cuts[:1]):
                cuts = [named[0]] + cuts[:2]
            t0 = 0.0
            if st != prev_set:
                # a wide of the person the line is about, placed and checked by the shot planner (fixed establishing
                # positions landed inside walls and behind trees)
                who0 = next((c.split("+")[0] for c in cuts if c.split("+")[0] in here), next(iter(ln.get("do", {})), next(iter(here))))
                if who0 in here:
                    others = [here[o] for o in here if o != who0][:1]
                    cams.append({"name": f"{st.lower()} wide", "start": f"@{lid}", "subject": here[who0], "shot": "wide",
                                 "angle": 0, **({"with": others[0]} if others else {})})
                    t0 = min(1.6, dur * 0.4)
                prev_set = st
            step = (dur - t0) / len(cuts)
            # size changes this line (who -> (offset, new scale)): their cuts become full shots next to a normal-size
            # person, or the shrink / growth can't be seen (a single framed to fit is always "full size")
            sz_ch = {}
            for w_, what_ in (ln.get("change") or {}).items():
                m_ = re.match(r"^\s*(grow|shrink|normal)\s*([\d.]*)\s*(?:@\s*([\d.]+))?", str(what_))
                if m_ and w_ in here:
                    v_ = 1.0 if m_.group(1) == "normal" else float(m_.group(2) or (1.7 if m_.group(1) == "grow" else 0.55))
                    sz_ch[w_] = (float(m_.group(3) or min(0.8, dur * 0.3)), v_)
            for j, c in enumerate(cuts):
                t_cut = t0 + j * step
                at = f"@{lid}" if t_cut < 0.05 else f"@{lid}+{t_cut:.1f}"
                who = c.split("+")
                if who[0] in {p["name"] for p in props}:
                    appears = {k for k, v in (ln.get("change") or {}).items() if str(v).strip().startswith("appear")}
                    if who[0] in appears and who[0] not in shown:
                        # it pops in during this line: the insert starts with the pop, not before it
                        m_ap = re.search(r"@\s*([\d.]+)", str((ln.get("change") or {})[who[0]]))
                        off_ap = float(m_ap.group(1)) if m_ap else min(0.8, dur * 0.3)
                        if t_cut < off_ap - 0.3:
                            at = f"@{lid}+{max(0.0, off_ap - 0.3):.1f}"
                    if who[0] in shown or who[0] in ln.get("show", []) or who[0] in appears:
                        is_sign = any(e_["name"] == who[0] and e_["prop"] == "sign" for e_ in place)
                        cams.append({"name": f"{lid} {c}", "start": at, "prop": who[0], "shot": "medium" if is_sign else "close", "angle": 0})
                        continue
                    warn.append(f"{lid}: cut to {who[0]} before it is shown; framing a person instead")
                    who = [next(iter(ln.get("do", {})), next(iter(here)))]
                if who[0] not in here:
                    warn.append(f"{lid}: camera subject {c!r} not in {st}")
                    continue
                k_cam += 1
                cue = {"name": f"{lid} {c}", "start": at, "subject": here[who[0]]}
                a0 = here[who[0]]
                s_now = cur_scale.get(a0, 1.0)
                if who[0] in sz_ch and (t_cut + step > sz_ch[who[0]][0]):
                    s_now = sz_ch[who[0]][1] if t_cut >= sz_ch[who[0]][0] else max(s_now, sz_ch[who[0]][1], key=lambda v: abs(v - 1))
                changing = who[0] in sz_ch and t_cut <= sz_ch[who[0]][0] < t_cut + step
                if abs(s_now - 1) > 0.12 or changing:
                    mates = [o for o in here if o != who[0] and abs(cur_scale.get(here[o], 1.0) - 1) < 0.12]
                    mate = who[1] if len(who) > 1 and who[1] in here else (mates[0] if mates else None)
                    cue.update({"shot": "full" if s_now < 1 else "wide", "angle": [0, 20, -20][k_cam % 3], "cover": False})
                    if mate:
                        cue["with"] = here[mate]
                elif len(who) > 1 and who[1] in here:
                    cue.update({"with": here[who[1]], "shot": "full" if k_cam % 2 else "medium", "angle": 0})
                else:
                    # whole bodies read (acting, sizes); a close-up only for a big feeling
                    big = (ln.get("feel") or {}).get(who[0]) in ("shocked", "crying", "scared", "love", "angry")
                    # head-and-shoulders or whole body (a blocky "medium" is a torso filling the frame)
                    cue.update({"shot": "close" if big else ["full", "close", "full"][k_cam % 3],
                                "angle": [0, 20, -15, 10][k_cam % 4]})
                cams.append(cue)
            for ch in ln.get("do", {}):
                if ch in here and ch not in introduced:
                    introduced.add(ch)
                    events.append({"kind": "tag", "actor": here[ch], "text": ch, "at": f"@{lid}+0.2", "until": f"@{lid}+2.8"})
            acted = {}
            # actions, chained from the line's start; drop what can't fit before the line is over
            for ch, acts in ln.get("do", {}).items():
                if ch not in here:
                    warn.append(f"{lid}: {ch} is not in {st}")
                    continue
                a = here[ch]
                used = 0.0
                first = True
                for tok in acts.split():
                    mm = re.match(r"^([a-z_]+)(?:([>@])(.+))?$", tok)
                    if not mm or mm.group(1) not in ACTIONS:
                        warn.append(f"{lid}: unknown action {tok!r}")
                        continue
                    key, op, arg = mm.groups()
                    prompt, secs = ACTIONS[key]
                    if used and used + secs > dur + 1.0:
                        warn.append(f"{lid}: {ch} {tok} dropped (line too short)")
                        break
                    b = {"prompt": prompt, "seconds": secs}
                    if first:
                        b["at"] = f"@{lid}"
                    if key in MOVES:
                        tgt = arg if op == ">" else None
                        if tgt in here:
                            b["to"] = here[tgt]
                            b["face"] = cheat(a, here[tgt])
                            tx, tz = pos[here[tgt]]
                            px, pz = pos[a]
                            d = math.hypot(tx - px, tz - pz) or 1.0
                            pos[a] = (tx - (tx - px) / d * 2.5, tz - (tz - pz) / d * 2.5)
                        elif tgt and any(e_["name"] == tgt for e_ in place):
                            e_ = next(e_ for e_ in place if e_["name"] == tgt)      # walk up to a prop
                            px, pz = pos[a]
                            gx_, gz_ = e_["at"]
                            d_ = math.hypot(gx_ - px, gz_ - pz) or 1.0
                            gx_, gz_ = round(gx_ - (gx_ - px) / d_ * 2.2, 2), round(gz_ - (gz_ - pz) / d_ * 2.2, 2)
                            b["to"] = [gx_, gz_]
                            b["face"] = list(e_["at"])
                            pos[a] = (gx_, gz_)
                        elif tgt and tgt.partition(":")[0] in spots:
                            nm_, _, off_ = tgt.partition(":")
                            s = spots[nm_]
                            try:
                                dx_, dz_ = (float(v) for v in off_.split(",")) if off_ else (0.0, 0.0)
                            except ValueError:
                                dx_, dz_ = 0.0, 0.0
                            gx_, gz_ = round(s["x"] + dx_, 2), round(s["z"] + dz_, 2)
                            b["to"] = [gx_, gz_]
                            fx, fz = _yaw_dir(s["yaw"])
                            b["face"] = [round(gx_ + fx * 5, 2), round(gz_ + fz * 5, 2)]
                            pos[a] = (gx_, gz_)
                        else:
                            warn.append(f"{lid}: {ch} {tok}: no target, walking in place")
                            b["prompt"] = "a person stands and talks, gesturing with both hands"
                    if op == "@":
                        b["face"] = cheat(a, here[arg]) if arg in here else (arg if arg in ("+X", "-X", "+Z", "-Z") else None)
                        if arg == "camera":
                            sx, sz = m.get("camera_side", [-1, 0])
                            b["face"] = ("+X" if sx > 0.5 else "-X" if sx < -0.5 else "+Z" if sz > 0 else "-Z")
                        if b["face"] is None:
                            del b["face"]
                    actors[a]["beats"].append(b)
                    used += secs
                    first = False
                acted[ch] = used
            # nobody just stands there: everyone in the scene fills the rest of the line with a reaction that matches
            # their feeling (judges: "characters stand and talk instead of acting out the beat")
            for ch, a in here.items():
                feel_ = (ln.get("feel") or {}).get(ch) or last_feel.get(a, "neutral")
                last_feel[a] = feel_
                used = acted.get(ch, 0.0)
                left = dur - used
                if left < 1.9:
                    continue
                key = REACT.get(feel_, "nod")
                if ch == next(iter(ln.get("do", {})), None) and key in ("nod", "cross_arms"):
                    key = "talk"
                prompt, secs = ACTIONS[key]
                bt = {"prompt": prompt, "seconds": secs}
                if not used:
                    bt["at"] = f"@{lid}+0.3"
                actors[a]["beats"].append(bt)
                if left - secs >= 2.2:
                    key2 = "nod" if key != "nod" else "shrug"
                    actors[a]["beats"].append({"prompt": ACTIONS[key2][0], "seconds": ACTIONS[key2][1]})
            for n in ln.get("show", []):          # shown at the line's start (before this line's changes act on it)
                shown.setdefault(n, f"@{lid}")
            for who, what in (ln.get("change") or {}).items():
                mm = re.match(r"^\s*(grow|shrink|normal|look|swap|vanish|appear|poof)\s*([^@]*?)\s*(?:@\s*([\d.]+))?\s*$", str(what))
                if not mm:
                    warn.append(f"{lid}: change {who}: {what!r} not understood")
                    continue
                verb, arg, off = mm.group(1), mm.group(2).strip(), float(mm.group(3) or min(0.8, dur * 0.3))
                at = f"@{lid}+{off:.1f}"
                prop_names = {q["name"] for q in props}
                if who in prop_names:
                    # the camera is on the object when it goes / comes (judges: "a poof over Bruno's chest, not the
                    # cake disappearing")
                    cams.append({"name": f"{lid} {who} {verb}", "start": f"@{lid}+{max(0.0, off - 0.5):.1f}",
                                 "prop": who, "shot": "medium", "angle": 0})
                    if j_next := next((t_ for t_ in (t0 + k_ * step for k_ in range(len(cuts))) if t_ > off + 1.1), None):
                        pass
                    cams.append({"name": f"{lid} after {who}", "start": f"@{lid}+{off + 1.3:.1f}",
                                 "subject": here[next(iter(ln.get("do", {})), next(iter(here)))], "shot": "medium", "angle": 15})
                    if verb == "appear":
                        shown.setdefault(who, at)
                    elif verb == "vanish" and who in shown:
                        t_show = shown.pop(who)
                        next(q for q in props if q["name"] == who)["show"].append([t_show, at])
                    events.append({"kind": "poof", "prop": who, "at": at})
                    continue
                if who not in here:
                    warn.append(f"{lid}: change {who}: not in {st}")
                    continue
                a = here[who]
                if verb in ("grow", "shrink", "normal"):
                    to = 1.0 if verb == "normal" else float(arg or (1.7 if verb == "grow" else 0.55))
                    if verb == "shrink":       # judges: "Max at -7 inches looks normal-sized": every change reads
                        to = min(to, max(0.5, cur_scale.get(here[who], 1.0) * 0.75)) if who in here else min(to, 0.7)
                    elif verb == "grow":
                        to = max(to, min(1.7, cur_scale.get(here[who], 1.0) * 1.35)) if who in here else max(to, 1.4)
                    events.append({"kind": "scale", "actor": a, "at": at, "to": max(0.35, min(1.7, to)), "over": 0.7})
                    cur_scale[a] = max(0.35, min(1.7, to))
                    char_state.setdefault(who, {})["scale"] = cur_scale[a]
                elif verb == "look":
                    if arg in lks:
                        events.append({"kind": "look", "actor": a, "at": at, "look": arg, "poof": True})
                        events.append({"kind": "tag", "actor": a, "text": who, "at": at, "until": f"@{lid}+{off + 3.2:.1f}"})
                        cur_look[a] = arg
                        char_state.setdefault(who, {})["look"] = arg
                    else:
                        warn.append(f"{lid}: change {who}: unknown look {arg!r}")
                elif verb == "swap":
                    b = here.get(arg)
                    if b:
                        la, lb = cur_look[a], cur_look[b]
                        events.append({"kind": "look", "actor": a, "at": at, "look": lb, "poof": True})
                        events.append({"kind": "look", "actor": b, "at": at, "look": la, "poof": True})
                        events.append({"kind": "tag", "actor": a, "text": who, "at": at, "until": f"@{lid}+{off + 3.2:.1f}"})
                        events.append({"kind": "tag", "actor": b, "text": arg, "at": at, "until": f"@{lid}+{off + 3.2:.1f}"})
                        cur_look[a], cur_look[b] = lb, la
                        char_state.setdefault(who, {})["look"] = lb
                        char_state.setdefault(arg, {})["look"] = la
                    else:
                        warn.append(f"{lid}: swap {who} with {arg!r}: not in {st}")
                elif verb in ("vanish", "appear", "poof"):
                    events.append({"kind": verb, "actor": a, "at": at, "poof": True})
                if verb in ("look", "swap", "vanish", "appear"):    # the change on screen, whole body
                    cams.append({"name": f"{lid} {who} {verb}", "start": f"@{lid}+{max(0.0, off - 0.5):.1f}", "subject": a,
                                 "shot": "full", "angle": 0, "cover": False})
            for ch, f in ln.get("feel", {}).items():
                if ch in here and f in FEELINGS:
                    faces.setdefault(here[ch], []).append((f"@{lid}", f))
            if ln.get("label"):
                who = here.get(next(iter(ln.get("do", {})), ""), next(iter(here.values())))
                # a title owns the top of the frame for its first 1.8 s: the label waits for it
                t_lab = "+2.2" if ln.get("title") else "+0.4"
                fxs.append({"actor": who, "kind": "label", "show": [[f"@{lid}{t_lab}", f"@{lid}.end+0.3", ln["label"]]]})
            for ch, kind in (ln.get("fx") or {}).items():
                if ch in here and kind in FX_KINDS:
                    fxs.append({"actor": here[ch], "kind": kind, "show": [[f"@{lid}+0.3", f"@{lid}.end+0.4"]]})
            for s in ([ln["sfx"]] if isinstance(ln.get("sfx"), str) else ln.get("sfx") or []):
                if s in sfx_ok:
                    sfx.append((f"@{lid}+0.4", s, 0.5))
                else:
                    warn.append(f"{lid}: sfx {s!r} not in the library, skipped")
            if ln.get("title"):
                titles.append((f"@{lid}+0.4", f"@{lid}+2.0" if ln.get("label") else f"@{lid}.end+0.3", ln["title"]))
            for n in ln.get("show", []):
                shown.setdefault(n, f"@{lid}")
            for n in ln.get("hide", []):
                if n in shown:
                    t_show = shown.pop(n)
                    for p in props:
                        if p["name"] == n:
                            p["show"].append([t_show, f"@{lid}"])
                            break
    for n, act in actors.items():
        if not act["beats"]:       # placed but never acting: stands there through its scene
            act["beats"].append({"at": f"@{first_line[n]}", "prompt": ACTIONS["happy"][0], "seconds": ACTIONS["happy"][1]})
    # ambient motes in every scene (anchored on its first character)
    for sc in spec.SCENES:
        who_ = next((copy(ch, sc["set"]) for ch in sc.get("place", {})), None)
        if who_:
            fxs.append({"actor": who_, "kind": "motes", "show": [[f"@{sc['lines'][0]['id']}", f"@{sc['lines'][-1]['id']}.end+0.5"]]})
    end = f"@{line_ids[-1]}.end+2.0"
    for n, t in shown.items():
        for p in props:
            if p["name"] == n:
                p["show"].append([t, end])
                break
    for n in actors:
        faces.setdefault(n, [])
        if not faces[n] or faces[n][0][0] != 0:
            faces[n].insert(0, (0, "neutral" if not faces[n] else faces[n][0][1]))
    music = spec.MUSIC if getattr(spec, "MUSIC", "") in MUSIC_MOODS else "whimsical"

    def EPp(n):
        return ["Workspace", "Sets", "EpisodeProps", n]
    props_out = [{"path": EPp(p["name"]), "show": p["show"], **({"attach": p["attach"]} if "attach" in p else {})}
                 for p in props if p["show"]]
    src = [f'"""{spec.TITLE} (compiled from stories/{slug}.py by story_compile.py; edit the story, not this file)"""',
           f"TITLE = {spec.TITLE!r}", 'STATIC = "own"', 'VOICE, SPEED = "tv_M2", 1.0',
           'CAPTIONS = {"size": 120, "highlight": False, "max_words": 2}',
           f"KEYWORDS = {list(getattr(spec, 'KEYWORDS', []))!r}",
           f"CAST = {cast!r}", f"ACTORS = {list(actors.values())!r}", f"LINES = {lines!r}", f"TITLES = {titles!r}",
           f"PLACE = {place!r}", f"CAMERAS = {cams!r}", f"FACES = {faces!r}", f"PROPS = {props_out!r}", f"FX = {fxs!r}", f"EVENTS = {events!r}",
           f'MUSIC = {{"query": {music!r}, "pick": 0, "from": 0, "gain": 0.45}}', f"SFX = {sfx!r}"]
    for w in warn:
        print("story:", w)
    return "\n".join(src) + "\n"


def load(path: Path):
    s = importlib.util.spec_from_file_location("story_" + path.stem, path)
    mod = importlib.util.module_from_spec(s)
    s.loader.exec_module(mod)
    return mod


def main():
    if sys.argv[1:] == ["--catalog"]:
        print(catalog())
        return
    p = Path(sys.argv[1])
    out = HERE / "eps" / f"{p.stem}.py"
    out.write_text(compile_story(load(p), p.stem), encoding="utf-8")
    print(f"story: wrote {out}")


if __name__ == "__main__":
    main()
