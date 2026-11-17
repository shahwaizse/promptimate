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
FEELINGS = ["neutral", "happy", "grin", "sad", "crying", "shocked", "scared", "angry", "smug", "tired", "wink", "love"]
FX_KINDS = ["sparkle", "rain", "confetti", "hearts"]
MUSIC_MOODS = ["whimsical", "happy", "funny", "dance", "mysterious", "piano", "creepy"]
WORDS_PER_S = 2.55          # tv_M2 at 1.0x, measured on compliment_coins (for spreading cuts and fitting actions)
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


def _free_spot(x: float, z: float, floor: float, others, r: float = 1.3, apart: float = 3.5):
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
            yaw = s["yaw"]
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

    lines, cams, faces, place, props, fxs, sfx, titles = [], [], {}, [], [], [], [], []
    shown = {}     # prop name -> start ref of its open interval
    first_line = {}
    prev_set, k_cam = None, 0
    line_ids = []
    for sc in spec.SCENES:
        st = sc["set"]
        m = maps[st]
        spots = {s["name"]: s for s in m["spots"]}
        fy = m.get("floor_y", 0.0)
        here = {ch: copy(ch, st) for ch in sc.get("place", {})}
        for n in here.values():
            first_line.setdefault(n, sc["lines"][0]["id"])
        for p in sc.get("props", []):
            if p["prop"] not in props_ok:
                warn.append(f"prop {p['prop']!r} unknown, skipped")
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
            if p.get("small"):
                e["height"] = 0.35
            elif p.get("height"):
                e["height"] = p["height"]
            place.append(e)
            props.append({"name": p["name"], "show": [], **({"attach": {"actor": here[p["hold"]], "hand": "Right",
                                                                          "offset": HAND}} if p.get("hold") in here else {})})
        for ln in sc["lines"]:
            lid = ln["id"]
            line_ids.append(lid)
            dur = _est(ln["say"], ln.get("gap", 0.0))
            lines.append({"id": lid, "text": ln["say"], **({"gap": ln["gap"]} if ln.get("gap") else {})})
            # cameras: an establishing wide shot on a set change, then the line's cuts spread over its length
            cuts = ln.get("cam") or [next(iter(ln.get("do", {})), next(iter(here)))]
            cuts = cuts if isinstance(cuts, list) else [cuts]
            t0 = 0.0
            if st != prev_set:
                ps = [pos[a] for a in here.values()]
                cx, cz = sum(p[0] for p in ps) / len(ps), sum(p[1] for p in ps) / len(ps)
                sx, sz = m.get("camera_side", [-1, 0])
                cams.append({"name": f"{st.lower()} wide", "start": f"@{lid}", "pos": [round(cx + sx * 15, 1), fy + 8,
                             round(cz + sz * 15, 1)], "look": [round(cx, 1), fy + 3, round(cz, 1)], "fov": 55, "subjects": []})
                t0 = min(1.6, dur * 0.4)
                prev_set = st
            step = (dur - t0) / len(cuts)
            for j, c in enumerate(cuts):
                at = f"@{lid}" if t0 + j * step < 0.05 else f"@{lid}+{t0 + j * step:.1f}"
                who = c.split("+")
                if who[0] in {p["name"] for p in props}:
                    cams.append({"name": f"{lid} {c}", "start": at, "prop": who[0], "shot": "close", "angle": 0})
                    continue
                if who[0] not in here:
                    warn.append(f"{lid}: camera subject {c!r} not in {st}")
                    continue
                k_cam += 1
                cue = {"name": f"{lid} {c}", "start": at, "subject": here[who[0]]}
                if len(who) > 1 and who[1] in here:
                    cue.update({"with": here[who[1]], "shot": "full" if k_cam % 2 else "medium", "angle": 0})
                else:
                    cue.update({"shot": ["close", "medium", "close"][k_cam % 3], "angle": [0, 20, -15, 10][k_cam % 4]})
                cams.append(cue)
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
                            b["face"] = here[tgt]
                            tx, tz = pos[here[tgt]]
                            px, pz = pos[a]
                            d = math.hypot(tx - px, tz - pz) or 1.0
                            pos[a] = (tx - (tx - px) / d * 2.5, tz - (tz - pz) / d * 2.5)
                        elif tgt in spots:
                            s = spots[tgt]
                            b["to"] = [s["x"], s["z"]]
                            fx, fz = _yaw_dir(s["yaw"])
                            b["face"] = [round(s["x"] + fx * 5, 2), round(s["z"] + fz * 5, 2)]
                            pos[a] = (s["x"], s["z"])
                        else:
                            warn.append(f"{lid}: {ch} {tok}: no target, walking in place")
                            b["prompt"] = "a person stands and talks, gesturing with both hands"
                    if op == "@":
                        b["face"] = here.get(arg, arg if arg in ("+X", "-X", "+Z", "-Z") else None)
                        if arg == "camera":
                            sx, sz = m.get("camera_side", [-1, 0])
                            b["face"] = ("+X" if sx > 0.5 else "-X" if sx < -0.5 else "+Z" if sz > 0 else "-Z")
                        if b["face"] is None:
                            del b["face"]
                    actors[a]["beats"].append(b)
                    used += secs
                    first = False
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
                    for p in props:
                        if p["name"] == n:
                            p["show"].append([shown.pop(n), f"@{lid}"])
    for n, act in actors.items():
        if not act["beats"]:       # placed but never acting: stands there through its scene
            act["beats"].append({"at": f"@{first_line[n]}", "prompt": ACTIONS["happy"][0], "seconds": ACTIONS["happy"][1]})
    end = f"@{line_ids[-1]}.end+2.0"
    for n, t in shown.items():
        for p in props:
            if p["name"] == n:
                p["show"].append([t, end])
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
           f"PLACE = {place!r}", f"CAMERAS = {cams!r}", f"FACES = {faces!r}", f"PROPS = {props_out!r}", f"FX = {fxs!r}",
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
