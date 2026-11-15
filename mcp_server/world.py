"""Text-to-world for Promptimate: a place described in words -> a lit, furnished Unity room that Promptimate
characters can act in.

    import world
    spec = world.expand("a cramped 1970s detective office at night, rain on the window, a desk lamp, cigarette smoke")
    res = world.build_world(spec)                    # -> {"world_id", "stills": [...png], "mp4", "validation", ...}
    res2 = world.light_world(res["world_id"], "storm")   # same room, relit from text
    shot = world.render_world_shot(res["world_id"], {...render_shot-style spec...})

Pipeline
  1. Spec (JSON; Claude writes it, or `expand()` turns a one-liner into one): room size/style/era, materials,
     windows/doors, furniture with relations ("desk near the north wall, the chair at it, a lamp on it"), clutter
     density, lighting (time of day, weather, mood, practicals), effects, camera hints.
  2. Asset choice from a tagged CC0 library (unity/WorldLab/world_assets.json: Poly Haven scans, ambientCG
     materials, Kenney/Quaternius), scored by category + style/era tags, laid out with the real mesh sizes Unity
     measured (`measure()`).
  3. Layout solver: greedy over candidate positions generated from each relation, hard constraints (inside the
     floor, no overlaps, door swing and circulation kept free, tall pieces not in front of windows, wall items
     clear of openings) and soft scores (relation error, spacing); a walkway check (grid BFS from the door to the
     room centre and every seat/desk access point) repairs choices that would wall something off. Then surface,
     floor and wall clutter, rugs, ceiling fixtures.
  4. Lighting from text, physically based: time of day -> sun elevation and illuminance (lux), weather -> sky
     illuminance and HDRI choice, practicals in lumens and Kelvin (a 60 W bulb is 800 lm at 2700 K), a light meter
     at the focus point picks the exposure (EV100), every light is converted to Unity intensity relative to that
     exposure, colours are white-balanced (von Kries) to a camera white chosen by the mood. Indirect light comes
     from a split-flux estimate (window and lamp flux x mean albedo / room surface), plus a bounce light where the
     sun lands.
  5. Unity (unity/WorldLab, URP) builds and renders stills + a camera move; its report (real bounds of everything,
     drop hits, camera checks) is validated here together with image exposure statistics.
"""
from __future__ import annotations

import colorsys
import contextlib
import copy
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = Path(os.environ.get("PROMPTIMATE_WORLD_PROJECT", ROOT / "unity" / "WorldLab"))
MANIFEST = LAB / "world_assets.json"
CACHE = ROOT / ".cache" / "world"
QUEUE = CACHE / "queue"
WORLDS = CACHE / "worlds"
SIZES = CACHE / "asset_sizes.json"
BUILD = Path(os.environ.get("PROMPTIMATE_WORLD_BUILD", ROOT / "demo" / "world" / "build"))
GENERATED = LAB / "Assets" / "Promptimate" / "Generated"
VERSION = 1

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)  # stdout carries MCP stdio when imported by the server


# =====================================================================================================================
# Asset library

class Library:
    def __init__(self):
        self.man = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.models = {m["id"]: m for m in self.man["models"]}
        self.materials = {m["id"]: m for m in self.man["materials"]}
        self.hdris = {m["id"]: m for m in self.man["hdris"]}
        self.measured = json.loads(SIZES.read_text()) if SIZES.exists() else {}

    # --- paths -------------------------------------------------------------------------------------------------
    def model_path(self, m: dict) -> str:
        if m["src"] == "polyhaven":
            return f"Assets/WorldAssets/Models/{m['ref']}/{m['ref']}.gltf"
        if m["src"] == "kenney":
            return f"Assets/ThirdParty/Kenney/Furniture/{m['ref']}.fbx"
        if m["src"] == "quaternius":
            return f"Assets/ThirdParty/{m['ref']}"
        return ""

    def mat_paths(self, mid: str) -> dict:
        m = self.materials[mid]
        d = f"Assets/WorldAssets/Materials/{m['ref']}/{m['ref']}"
        out = {"id": mid, "albedo": d + "_diff.jpg", "normal": d + "_nor_gl.jpg", "rough": d + "_rough.jpg",
               "tile": float(m.get("tile", 2)), "smooth": float(m.get("smooth", 0.3))}
        if not (LAB / out["normal"]).exists():
            out["normal"] = ""
        return out

    def hdri_path(self, hid: str) -> str:
        return f"Assets/WorldAssets/HDRI/{self.hdris[hid]['ref']}.hdr"

    # --- sizes -------------------------------------------------------------------------------------------------
    def size(self, aid: str) -> tuple[float, float, float]:
        """(width x, height y, depth z) at yaw 0, from Unity's measurement when available."""
        ms = self.measured.get("models", {}).get(aid)
        if ms and ms.get("ok"):
            return tuple(float(v) for v in ms["size"])
        m = self.models[aid]
        s = [float(v) * float(m.get("scale", 1)) for v in m["size"]]
        return tuple(s)

    def front(self, m: dict) -> float:
        if "front" in m:
            return float(m["front"])
        return {"kenney": 180.0}.get(m["src"], 0.0)

    # --- choice ------------------------------------------------------------------------------------------------
    def pick_model(self, cat: str, tags: list[str], rng: random.Random, exclude: set | None = None,
                   prefer: str | None = None) -> dict | None:
        if prefer and prefer in self.models:
            return self.models[prefer]
        cands = [m for m in self.man["models"] if m["cat"] == cat]
        if not cands:
            cands = [m for m in self.man["models"] if cat in m["cat"] or m["cat"] in cat]
        if not cands:
            return None
        ok = [m for m in cands if not exclude or m["id"] not in exclude] or cands
        scored = []
        for m in ok:
            mt = set(m.get("tags", []))
            s = sum(2.0 if t in mt else 0 for t in tags) + (0.5 if "any" in mt else 0)
            s -= 1.5 if m["src"] == "kenney" else 0  # low-poly kit only as a fallback next to scanned assets
            if m["src"] == "kenney" and "lowpoly" in tags:
                s += 3
            s += rng.random() * 0.8
            scored.append((s, m))
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    def pick_material(self, use: str, tags: list[str], rng: random.Random, prefer: str | None = None) -> str:
        if prefer and prefer in self.materials:
            return prefer
        cands = [m for m in self.man["materials"] if use in m["use"]]
        scored = sorted(((sum(2 for t in tags if t in m["tags"]) + (0.5 if "any" in m["tags"] else 0) + rng.random() * 0.6, m["id"])
                         for m in cands), reverse=True)
        return scored[0][1]

    def pick_hdri(self, tags: list[str], rng: random.Random, prefer: str | None = None) -> str:
        if prefer and prefer in self.hdris:
            return prefer
        scored = sorted(((sum(2 for t in tags if t in h["tags"]) + rng.random() * 0.5, h["id"]) for h in self.man["hdris"]), reverse=True)
        return scored[0][1]


_LIB: Library | None = None


def lib(reload: bool = False) -> Library:
    global _LIB
    if _LIB is None or reload:
        _LIB = Library()
    return _LIB


# Rough mean albedo of library materials (for the indirect-light estimate).
ALBEDO = {"dark_paneled_wood": 0.14, "dark_wooden_planks": 0.15, "wood_floor_worn": 0.3, "old_wood_floor": 0.25,
          "herringbone_parquet": 0.35, "laminate_floor": 0.45, "wood_floor_light": 0.45, "dirty_carpet": 0.25,
          "interior_tiles": 0.5, "worn_tile_floor": 0.4, "concrete_floor_worn": 0.35, "terrazzo": 0.5,
          "beige_wall": 0.6, "painted_plaster": 0.7, "white_plaster": 0.8, "worn_plaster": 0.55, "peeling_paint": 0.5,
          "decrepit_wallpaper": 0.4, "wallpaper_a": 0.45, "wallpaper_b": 0.4, "brick_wall": 0.3, "painted_brick": 0.75,
          "wooden_panels": 0.4, "subway_tiles": 0.75, "square_tiled_wall": 0.65, "tiles_green": 0.4, "concrete_wall": 0.4,
          "ceiling_plaster": 0.8}

# Seating, access and clearance per category (metres).
CLEAR_FRONT = {"desk": 0.8, "sofa": 0.5, "armchair": 0.35, "bookshelf": 0.55, "shelving": 0.55, "cabinet": 0.6,
               "sideboard": 0.45, "bed": 0.5, "fireplace": 0.7, "table": 0.0, "chair": 0.2, "bench": 0.45, "tv": 0.0,
               "coat_rack": 0.0, "utility": 0.5, "clock_floor": 0.3}
SEATS = {"chair", "armchair", "sofa", "stool", "bench", "ottoman"}
SURFACES = {"desk", "table", "coffee_table", "side_table", "sideboard", "bookshelf", "fireplace"}


# =====================================================================================================================
# Colour and light physics

def kelvin_rgb_linear(k: float) -> tuple[float, float, float]:
    """Black-body colour (Tanner Helland's fit, sRGB) converted to linear RGB."""
    t = max(1000.0, min(40000.0, k)) / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
        b = 255.0
    c = [max(0.0, min(255.0, v)) / 255.0 for v in (r, g, b)]
    return tuple(_srgb_to_lin(v) for v in c)


def _srgb_to_lin(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin_to_srgb(c: float) -> float:
    c = max(0.0, c)
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def _lum(rgb) -> float:
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def balanced(k: float, wb: float) -> tuple[list[float], float]:
    """Light colour of a k-Kelvin source seen by a camera white-balanced to wb Kelvin (von Kries on RGB).
    Returns (sRGB colour with max channel 1, luminance factor to fold into the intensity)."""
    s, w = kelvin_rgb_linear(k), kelvin_rgb_linear(wb)
    lin = [s[i] / max(1e-4, w[i]) for i in range(3)]
    lum = _lum(lin)
    lin = [v / lum for v in lin]           # unit luminance
    mx = max(lin)
    return [round(_lin_to_srgb(v / mx), 4) for v in lin], 1.0 / mx


def lin_color(rgb_lin, scale: float = 1.0) -> list[float]:
    return [round(_lin_to_srgb(v * scale), 4) for v in rgb_lin]


# Sun elevation (deg) and illuminances (lux) by time of day; sky = diffuse horizontal, sun = direct normal.
TIMES = {
    "dawn": {"elev": 2, "sky": 400, "sun": 900, "k_sun": 2600, "k_sky": 9000},
    "sunrise": {"elev": 6, "sky": 1500, "sun": 8000, "k_sun": 2900, "k_sky": 8000},
    "morning": {"elev": 18, "sky": 9000, "sun": 45000, "k_sun": 4300, "k_sky": 7500},
    "noon": {"elev": 58, "sky": 18000, "sun": 100000, "k_sun": 5600, "k_sky": 7000},
    "afternoon": {"elev": 32, "sky": 14000, "sun": 75000, "k_sun": 5000, "k_sky": 7000},
    "golden_hour": {"elev": 7, "sky": 2500, "sun": 14000, "k_sun": 3000, "k_sky": 8000},
    "dusk": {"elev": -3, "sky": 120, "sun": 0, "k_sun": 2500, "k_sky": 11000},
    "evening": {"elev": -8, "sky": 15, "sun": 0, "k_sun": 2500, "k_sky": 12000},
    "night": {"elev": -30, "sky": 0.3, "sun": 0, "k_sun": 4100, "k_sky": 9000},
}
WEATHER = {  # multipliers on sky/sun, plus cloud colour shift
    "clear": {"sky": 1.0, "sun": 1.0},
    "partly_cloudy": {"sky": 1.2, "sun": 0.7},
    "overcast": {"sky": 0.9, "sun": 0.0, "k_sky": 6500},
    "rain": {"sky": 0.45, "sun": 0.0, "k_sky": 7200},
    "storm": {"sky": 0.2, "sun": 0.0, "k_sky": 8000},
    "snow": {"sky": 1.3, "sun": 0.3, "k_sky": 7000},
    "fog": {"sky": 0.6, "sun": 0.05, "k_sky": 7000},
}
MOODS = {  # EV bias, white-balance shift (K), contrast, saturation, bloom, vignette, grain, shadow/highlight tints
    "neutral": {"ev": 0.0, "wb": 300, "contrast": 8, "sat": 0, "bloom": 0.35, "vig": 0.22, "grain": 0.1},
    "noir": {"ev": -0.3, "wb": 1500, "contrast": 22, "sat": -18, "bloom": 0.8, "vig": 0.42, "grain": 0.16,
             "shadows": [0.86, 0.95, 1.05, -0.05], "highlights": [1.06, 0.98, 0.88, 0]},
    "cozy": {"ev": 0.0, "wb": 1100, "contrast": 10, "sat": 8, "bloom": 0.6, "vig": 0.28, "grain": 0.12,
             "highlights": [1.04, 1.0, 0.94, 0]},
    "cheerful": {"ev": -0.3, "wb": 400, "contrast": 8, "sat": 10, "bloom": 0.35, "vig": 0.15, "grain": 0.06},
    "eerie": {"ev": 0.6, "wb": -500, "contrast": 18, "sat": -30, "bloom": 0.5, "vig": 0.45, "grain": 0.25,
              "shadows": [0.88, 1.0, 1.0, -0.08]},
    "gloomy": {"ev": 0.4, "wb": -400, "contrast": 12, "sat": -22, "bloom": 0.35, "vig": 0.35, "grain": 0.18},
    "clinical": {"ev": -0.2, "wb": -200, "contrast": 6, "sat": -10, "bloom": 0.2, "vig": 0.12, "grain": 0.05},
    "romantic": {"ev": 0.1, "wb": 1300, "contrast": 9, "sat": 6, "bloom": 0.9, "vig": 0.3, "grain": 0.1},
    "tense": {"ev": -0.2, "wb": 0, "contrast": 20, "sat": -12, "bloom": 0.4, "vig": 0.4, "grain": 0.22},
}

# Practical light sources: lumens and colour temperature (typical real values).
SOURCES = {"candle": (12, 1850), "oil_lamp": (60, 1900), "incandescent_40w": (450, 2700), "incandescent_60w": (800, 2700),
           "incandescent_100w": (1600, 2800), "halogen": (700, 3000), "fluorescent": (2600, 4300), "led_warm": (800, 2700),
           "led_cool": (900, 5000), "sodium": (12000, 2000), "crt": (60, 8000), "neon_red": (300, 1700), "fire": (250, 1900)}


# =====================================================================================================================
# Geometry

def _fwd(yaw: float) -> tuple[float, float]:
    r = math.radians(yaw)
    return math.sin(r), math.cos(r)


def _right(yaw: float) -> tuple[float, float]:
    r = math.radians(yaw)
    return math.cos(r), -math.sin(r)


def _yaw_of(dx: float, dz: float) -> float:
    return math.degrees(math.atan2(dx, dz)) % 360


def rect(x, z, w, d, yaw):
    """Corners of a w (local x) by d (local z) rectangle centred at (x, z), rotated by Unity yaw."""
    fx, fz = _fwd(yaw)
    rx, rz = _right(yaw)
    hw, hd = w / 2, d / 2
    return [(x + rx * sx * hw + fx * sz * hd, z + rz * sx * hw + fz * sz * hd) for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def overlap(a, b, margin: float = 0.0) -> bool:
    """Separating-axis test for two convex quads (lists of 4 (x, z)); margin > 0 demands that much gap."""
    for poly in (a, b):
        for i in range(4):
            x1, z1 = poly[i]
            x2, z2 = poly[(i + 1) % 4]
            nx, nz = z2 - z1, x1 - x2
            ln = math.hypot(nx, nz) or 1
            nx, nz = nx / ln, nz / ln
            pa = [px * nx + pz * nz for px, pz in a]
            pb = [px * nx + pz * nz for px, pz in b]
            if max(pa) + margin <= min(pb) or max(pb) + margin <= min(pa):
                return False
    return True


def _point_in_quad(p, q) -> bool:
    sign = None
    for i in range(4):
        x1, z1 = q[i]
        x2, z2 = q[(i + 1) % 4]
        c = (x2 - x1) * (p[1] - z1) - (z2 - z1) * (p[0] - x1)
        if abs(c) < 1e-9:
            continue
        s = c > 0
        if sign is None:
            sign = s
        elif s != sign:
            return False
    return True


# =====================================================================================================================
# Spec expansion (stand-in for Claude writing the spec)

def _has(text: str, *words) -> bool:
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


def expand(text: str, seed: int = 0) -> dict:
    """One-line description -> world spec. Claude normally writes the spec itself; this keyword expander makes the
    pipeline usable from a single sentence and documents what a good spec looks like."""
    t = text.lower()
    style, era = [], []
    for w in ["scandinavian", "noir", "industrial", "victorian", "gothic", "modern", "minimal", "rustic", "midcentury",
              "cozy", "abandoned", "retro", "elegant", "brutalist", "farmhouse"]:
        if _has(t, w):
            style.append(w)
    m = re.search(r"\b(1[89]\d0)s\b", t)
    if m:
        era.append(m.group(1) + "s")
    time_of_day = "afternoon"
    for k, words in {"night": ["night", "midnight", "late"], "morning": ["morning"], "dawn": ["dawn"], "sunrise": ["sunrise"],
                     "golden_hour": ["golden hour", "sunset"], "dusk": ["dusk", "twilight"], "evening": ["evening"],
                     "noon": ["noon", "midday"], "afternoon": ["afternoon"]}.items():
        if any(w in t for w in words):
            time_of_day = k
            break
    weather = "clear"
    for k, words in {"storm": ["storm", "thunder", "lightning"], "rain": ["rain", "rainy", "drizzle"], "snow": ["snow", "winter"],
                     "fog": ["fog", "foggy", "mist"], "overcast": ["overcast", "grey day", "gray day", "cloudy"]}.items():
        if any(w in t for w in words):
            weather = k
            break
    mood = "neutral"
    for k, words in {"noir": ["noir", "detective"], "cozy": ["cozy", "cosy", "hygge", "warm"], "eerie": ["abandoned", "eerie", "creepy", "haunted"],
                     "gloomy": ["gloomy", "bleak"], "cheerful": ["cheerful", "bright", "sunny"], "romantic": ["romantic", "candlelit"],
                     "clinical": ["clinical", "sterile"]}.items():
        if any(w in t for w in words):
            mood = k
            break
    size = "medium"
    if _has(t, "cramped", "tiny", "small", "narrow"):
        size = "small"
    elif _has(t, "large", "huge", "spacious", "vast", "grand"):
        size = "large"
    rng = random.Random(seed)

    if _has(t, "subway", "metro", "platform", "station", "underground"):
        spec = _tpl_platform(size)
        style += ["subway", "station", "public"] + (["abandoned"] if "abandoned" not in style and _has(t, "abandoned", "derelict", "disused") else [])
        if mood == "neutral":
            mood = "eerie" if "abandoned" in style else "clinical"
    elif _has(t, "office", "detective", "study", "bureau"):
        spec = _tpl_office(size, t)
        style += ["office"] + (["noir", "1970s", "vintage"] if _has(t, "detective", "noir") else [])
    elif _has(t, "living room", "lounge", "sitting room", "apartment", "flat"):
        spec = _tpl_living(size, t)
        style += ["cozy"] if "cozy" not in style and mood == "cozy" else []
    elif _has(t, "bedroom", "motel", "hotel room"):
        spec = _tpl_bedroom(size, t)
    elif _has(t, "cafe", "café", "diner", "coffee shop", "kitchen"):
        spec = _tpl_cafe(size, t)
    else:
        spec = _tpl_workshop(size, t)
    spec["description"] = text
    spec["style"] = list(dict.fromkeys(style + era + spec.get("style", [])))
    light = spec.setdefault("lighting", {})
    light.setdefault("time", time_of_day)
    light.setdefault("weather", weather)
    light.setdefault("mood", mood)
    fx = spec.setdefault("effects", [])
    if _has(t, "smoke", "smoky", "cigarette", "cigar"):
        if not any(i.get("cat") == "ashtray" for i in spec["items"]):
            host = next((i["id"] for i in spec["items"] if i.get("cat") in ("desk", "table", "coffee_table")), None)
            if host:
                spec["items"].append({"id": "ashtray", "cat": "ashtray", "on": host, "side": "right"})
        fx.append({"type": "smoke", "source": "ashtray"})
        light["haze"] = max(light.get("haze", 0), 0.5)
    if weather in ("rain", "storm") and spec.get("openings"):
        for o in spec["openings"]:
            if o["type"] == "window":
                o["rainy"] = True
    if _has(t, "desk lamp", "lamp") and not any(i.get("cat") == "lamp_desk" for i in spec["items"]):
        host = next((i["id"] for i in spec["items"] if i.get("cat") in ("desk", "table", "side_table")), None)
        if host:
            spec["items"].append({"id": "desk_lamp", "cat": "lamp_desk", "on": host, "side": "left", "light": {"on": True}})
    if _has(t, "fireplace", "stove", "fire"):
        if not any(i.get("cat") == "fireplace" for i in spec["items"]):
            spec["items"].append({"id": "fireplace", "cat": "fireplace", "against": "any", "light": {"on": True}})
    if _has(t, "candle", "candles", "candlelit"):
        host = next((i["id"] for i in spec["items"] if i.get("cat") in ("coffee_table", "table", "side_table", "sideboard")), None)
        if host:
            spec["items"].append({"id": "candles", "cat": "candle", "on": host, "count": 3, "light": {"on": True}})
    if _has(t, "blinds", "venetian"):
        for o in spec.get("openings", []):
            if o["type"] == "window":
                o["blinds"] = True
    spec["seed"] = seed
    spec.setdefault("name", re.sub(r"[^a-z0-9]+", "_", " ".join(t.split()[:5])).strip("_")[:40] or "world")
    return spec


def _room_size(size: str, base: tuple[float, float], h: float = 2.8) -> dict:
    k = {"small": 0.86, "medium": 1.0, "large": 1.35}[size]
    return {"size": [round(base[0] * k, 2), round(base[1] * k, 2)], "height": h}


def _tpl_office(size: str, t: str) -> dict:
    noir = _has(t, "detective", "noir", "1970s", "70s")
    return {
        "room": {**_room_size(size, (5.2, 4.4), 2.9), "floor": {"tags": ["noir", "1970s", "vintage"]} if noir else {"tags": ["office"]},
                 "walls": {"tags": ["noir", "1970s", "vintage"]} if noir else {"tags": ["office"]}},
        "openings": [{"type": "window", "wall": "north", "at": 0.5, "width": 1.5, "height": 1.5, "sill": 0.85, "blinds": noir},
                     {"type": "door", "wall": "south", "at": 0.2, "width": 0.92, "height": 2.1, "open": 0}],
        "items": [
            {"id": "desk", "cat": "desk", "against": "north", "user_faces": "room", "at": 0.5},
            {"id": "desk_chair", "cat": "chair", "at_desk": "desk", "prefer": "armchair_victorian" if noir else None},
            {"id": "visitor_chair", "cat": "chair", "in_front_of": "desk", "facing": "desk", "count": 2, "gap": 0.55},
            {"id": "desk_lamp", "cat": "lamp_desk", "on": "desk", "side": "left", "light": {"on": True}},
            {"id": "phone", "cat": "phone", "on": "desk", "side": "right"},
            {"id": "cabinet", "cat": "cabinet", "against": "west", "at": 0.7},
            {"id": "bookshelf", "cat": "bookshelf", "against": "east", "at": 0.35},
            {"id": "coat_rack", "cat": "coat_rack", "corner": "sw"},
            {"id": "fan", "cat": "ceiling_fan", "ceiling": True, "above": "desk"} if noir else {"id": "ceiling_light", "cat": "lamp_ceiling", "ceiling": True},
            {"id": "frame", "cat": "frame", "on_wall": "west", "above": "cabinet"},
            {"id": "clock", "cat": "clock", "on_wall": "east", "height": 2.1},
            {"id": "plant", "cat": "plant", "corner": "se"},
        ],
        "clutter": 0.7,
        "lighting": {"window_light": "street" if noir else "sky"},
        "camera": {"focus": "desk", "move": "push_in"},
    }


def _tpl_living(size: str, t: str) -> dict:
    scandi = _has(t, "scandinavian", "nordic", "hygge")
    tags = ["scandinavian", "cozy", "light"] if scandi else ["cozy", "modern"]
    return {
        "room": {**_room_size(size, (6.4, 5.2), 2.7), "floor": {"tags": tags}, "walls": {"tags": tags}, "ceiling": "white_plaster"},
        "openings": [{"type": "window", "wall": "north", "at": 0.33, "width": 1.6, "height": 1.7, "sill": 0.55, "curtains": True},
                     {"type": "window", "wall": "north", "at": 0.75, "width": 1.6, "height": 1.7, "sill": 0.55, "curtains": True},
                     {"type": "door", "wall": "east", "at": 0.82, "width": 0.9, "height": 2.05}],
        "items": [
            {"id": "sofa", "cat": "sofa", "against": "south", "at": 0.45, "prefer": "sofa_large" if scandi else None},
            {"id": "coffee_table", "cat": "coffee_table", "in_front_of": "sofa", "gap": 0.45},
            {"id": "armchair", "cat": "armchair", "beside": "coffee_table", "side": "right", "facing": "coffee_table", "prefer": "lounge_chair_midcentury" if scandi else None},
            {"id": "rug", "cat": "rug", "under": ["sofa", "coffee_table", "armchair"], "mat": {"tags": tags + ["rug"]}},
            {"id": "fireplace", "cat": "fireplace", "against": "west", "at": 0.5, "light": {"on": True}} if scandi else {"id": "sideboard", "cat": "sideboard", "against": "west"},
            {"id": "side_table", "cat": "side_table", "beside": "sofa", "side": "left"},
            {"id": "floor_lamp", "cat": "lamp_floor", "beside": "sofa", "side": "right", "light": {"on": True}},
            {"id": "shelves", "cat": "bookshelf", "against": "east", "at": 0.35},
            {"id": "pillows", "cat": "pillows", "on": "sofa"},
            {"id": "pendant", "cat": "lamp_ceiling", "ceiling": True, "above": "coffee_table", "light": {"on": False}},
            {"id": "plant", "cat": "plant", "corner": "ne"},
            {"id": "plant2", "cat": "plant", "corner": "sw"},
            {"id": "frames", "cat": "frame", "on_wall": "south", "above": "sofa", "count": 2},
            {"id": "candles", "cat": "candle", "on": "coffee_table", "count": 2, "light": {"on": True}},
            {"id": "basket", "cat": "basket", "beside": "fireplace" if scandi else "sideboard", "side": "left"},
        ],
        "clutter": 0.55,
        "camera": {"focus": "coffee_table", "move": "dolly"},
        "lighting": {},
    }


def _tpl_platform(size: str) -> dict:
    L = {"small": 18, "medium": 24, "large": 32}[size]
    return {
        "room": {"size": [L, 9.0], "height": 4.2, "floor": "terrazzo", "walls": "subway_tiles", "ceiling": "concrete_wall",
                 "trench": {"wall": "north", "width": 3.4, "depth": 1.25}, "columns": {"count": max(3, L // 6), "offset": 2.2},
                 "edge_strip": True},
        "openings": [{"type": "arch", "wall": "south", "at": 0.25, "width": 2.6, "height": 2.7},
                     {"type": "arch", "wall": "south", "at": 0.75, "width": 2.6, "height": 2.7}],
        "items": [
            {"id": "bench", "cat": "bench", "against": "south", "at": 0.5, "prefer": "bench_painted"},
            {"id": "bench2", "cat": "bench", "against": "south", "at": 0.08, "prefer": "bench_painted"},
            {"id": "bench3", "cat": "bench", "against": "south", "at": 0.92, "prefer": "bench_painted"},
            {"id": "payphone", "cat": "payphone", "on_wall": "south", "at": 0.38},
            {"id": "camera1", "cat": "camera", "on_wall": "south", "at": 0.62},
            {"id": "utility", "cat": "utility", "against": "west", "at": 0.25},
            {"id": "clock", "cat": "clock", "on_wall": "south", "at": 0.5, "height": 3.0},
            {"id": "sign_station", "cat": "sign", "proc": "sign", "on_wall": "north", "at": 0.5, "height": 2.4, "size": [3.2, 0.7, 0.08], "color": [0.9, 0.9, 0.85], "emissive": 0.9},
            {"id": "sign_a", "cat": "sign", "proc": "sign", "on_wall": "north", "at": 0.15, "height": 2.4, "size": [2.0, 0.6, 0.08], "color": [0.85, 0.82, 0.75], "emissive": 0.7},
            {"id": "sign_b", "cat": "sign", "proc": "sign", "on_wall": "north", "at": 0.85, "height": 2.4, "size": [2.0, 0.6, 0.08], "color": [0.85, 0.82, 0.75], "emissive": 0.7},
            {"id": "wet_sign", "cat": "sign", "prefer": "wet_floor_sign", "near": "bench", "dist": 3.0},
            {"id": "trash", "cat": "trash", "corner": "sw"},
            {"id": "trash2", "cat": "trash", "against": "south", "at": 0.66},
            {"id": "lights", "cat": "lamp_ceiling", "prefer": "fluorescent_panel", "grid": [6, 2], "light": {"on": True}},
        ],
        "clutter": 0.4,
        "camera": {"focus": "bench", "move": "dolly", "establish": "along"},
        "lighting": {"time": "night", "window_light": "none"},
    }


def _tpl_bedroom(size: str, t: str) -> dict:
    return {
        "room": {**_room_size(size, (4.6, 4.0), 2.7), "floor": {"tags": ["vintage"]}, "walls": {"tags": ["vintage", "cozy"]}},
        "openings": [{"type": "window", "wall": "east", "at": 0.5, "width": 1.3, "height": 1.4, "sill": 0.9, "curtains": True},
                     {"type": "door", "wall": "south", "at": 0.15, "width": 0.9, "height": 2.05}],
        "items": [
            {"id": "bed", "cat": "bed", "against": "north", "at": 0.5},
            {"id": "nightstand", "cat": "side_table", "beside": "bed", "side": "left"},
            {"id": "lamp", "cat": "lamp_desk", "on": "nightstand", "light": {"on": True}},
            {"id": "dresser", "cat": "sideboard", "against": "west"},
            {"id": "chair", "cat": "armchair", "corner": "se"},
            {"id": "frame", "cat": "frame", "on_wall": "north", "above": "bed"},
        ],
        "clutter": 0.5, "camera": {"focus": "bed", "move": "dolly"}, "lighting": {},
    }


def _tpl_cafe(size: str, t: str) -> dict:
    return {
        "room": {**_room_size(size, (7.0, 5.5), 3.0), "floor": {"tags": ["cafe", "kitchen"]}, "walls": {"tags": ["cafe", "industrial"]}},
        "openings": [{"type": "window", "wall": "north", "at": 0.3, "width": 2.2, "height": 1.8, "sill": 0.6},
                     {"type": "window", "wall": "north", "at": 0.72, "width": 2.2, "height": 1.8, "sill": 0.6},
                     {"type": "door", "wall": "east", "at": 0.5, "width": 1.0, "height": 2.2}],
        "items": [
            {"id": "table1", "cat": "table", "prefer": "table_round_small", "at_frac": [0.3, 0.6]},
            {"id": "table2", "cat": "table", "prefer": "table_round_small", "at_frac": [0.68, 0.6]},
            {"id": "table3", "cat": "table", "prefer": "table_kitchen", "at_frac": [0.45, 0.25]},
            {"id": "chairs1", "cat": "chair", "around": "table1", "count": 2},
            {"id": "chairs2", "cat": "chair", "around": "table2", "count": 2},
            {"id": "chairs3", "cat": "chair", "around": "table3", "count": 2},
            {"id": "counter", "cat": "sideboard", "against": "west"},
            {"id": "lights", "cat": "lamp_ceiling", "prefer": "ceiling_lamp_industrial", "grid": [3, 2], "light": {"on": True}},
            {"id": "board", "cat": "sign", "prefer": "standing_chalkboard", "corner": "se"},
        ],
        "clutter": 0.6, "camera": {"focus": "table1", "move": "dolly"}, "lighting": {},
    }


def _tpl_workshop(size: str, t: str) -> dict:
    return {
        "room": {**_room_size(size, (6.0, 5.0), 3.2), "floor": "concrete_floor_worn", "walls": {"tags": ["industrial", "abandoned"]}},
        "openings": [{"type": "window", "wall": "north", "at": 0.5, "width": 2.0, "height": 1.2, "sill": 1.4},
                     {"type": "door", "wall": "south", "at": 0.2, "width": 1.0, "height": 2.2}],
        "items": [
            {"id": "bench", "cat": "desk", "prefer": "desk_wooden", "against": "north", "user_faces": "wall"},
            {"id": "stool", "cat": "stool", "at_desk": "bench"},
            {"id": "lamp", "cat": "lamp_desk", "on": "bench", "light": {"on": True}},
            {"id": "shelves", "cat": "shelving", "against": "east", "count": 2},
            {"id": "rack", "cat": "shelving", "against": "west"},
            {"id": "barrels", "cat": "barrel", "corner": "sw", "count": 2},
            {"id": "light", "cat": "lamp_ceiling", "prefer": "ceiling_lamp_industrial", "ceiling": True, "light": {"on": True}},
        ],
        "clutter": 0.7, "camera": {"focus": "bench", "move": "dolly"}, "lighting": {},
    }


# =====================================================================================================================
# Layout solver

class Room:
    def __init__(self, W: float, D: float, H: float):
        self.W, self.D, self.H = W, D, H
        self.walls = {
            "north": {"a": (-W / 2, D / 2), "t": (1, 0), "n": (0, -1), "L": W},
            "east": {"a": (W / 2, D / 2), "t": (0, -1), "n": (-1, 0), "L": D},
            "south": {"a": (W / 2, -D / 2), "t": (-1, 0), "n": (0, 1), "L": W},
            "west": {"a": (-W / 2, -D / 2), "t": (0, 1), "n": (1, 0), "L": D},
        }
        self.floor = (-W / 2, -D / 2, W / 2, D / 2)   # walkable rect (trench removes a strip)
        self.openings: list[dict] = []

    def wall_point(self, wall: str, u: float, inset: float = 0.0) -> tuple[float, float]:
        w = self.walls[wall]
        return (w["a"][0] + w["t"][0] * u + w["n"][0] * inset, w["a"][1] + w["t"][1] * u + w["n"][1] * inset)

    def wall_yaw(self, wall: str) -> float:
        n = self.walls[wall]["n"]
        return _yaw_of(n[0], n[1])

    def nearest_wall(self, x: float, z: float) -> str:
        d = {"north": self.D / 2 - z, "south": z + self.D / 2, "east": self.W / 2 - x, "west": x + self.W / 2}
        return min(d, key=d.get)

    def inside(self, poly, margin: float = 0.0) -> bool:
        x0, z0, x1, z1 = self.floor
        return all(x0 + margin - 1e-6 <= x <= x1 - margin + 1e-6 and z0 + margin - 1e-6 <= z <= z1 - margin + 1e-6 for x, z in poly)


class Solver:
    """Greedy placement with candidates per relation, hard constraints, soft scores and a walkway repair."""

    def __init__(self, room: Room, L: Library, tags: list[str], rng: random.Random, log=_log):
        self.room, self.L, self.tags, self.rng, self.log = room, L, tags, rng, log
        self.placed: dict[str, dict] = {}
        self.order: list[str] = []
        self.unplaced: list[dict] = []
        self.wall_used: list[dict] = []   # wall items: {"wall", "u0", "u1", "y0", "y1"}
        self.blocked_zones: list[list] = []  # door swings
        self.notes: list[str] = []
        for o in room.openings:
            if o["type"] in ("door", "arch"):
                w = room.walls[o["wall"]]
                cx, cz = room.wall_point(o["wall"], o["u"], 0.55)
                self.blocked_zones.append(rect(cx, cz, o["width"] + 0.3, 1.1, room.wall_yaw(o["wall"])))

    # --- helpers ----------------------------------------------------------------------------------------------
    def footprint(self, it: dict, x=None, z=None, yaw=None, pad: float = 0.0):
        return rect(it["x"] if x is None else x, it["z"] if z is None else z, it["w"] + pad, it["d"] + pad, it["yaw"] if yaw is None else yaw)

    def clear_zone(self, it: dict):
        c = it.get("clear", 0)
        if c <= 0:
            return None
        fx, fz = _fwd(it["yaw"] + (180 if it.get("cat") == "desk" and it.get("user_faces") == "room" else 0))
        # desks whose user faces the room keep the clearance on the user's (back) side as well as for the chair
        cx, cz = it["x"] + fx * (it["d"] / 2 + c / 2), it["z"] + fz * (it["d"] / 2 + c / 2)
        return rect(cx, cz, it["w"], c, it["yaw"])

    def related(self, a: dict, b: dict) -> bool:
        return a.get("rel_to") == b["id"] or b.get("rel_to") == a["id"] or (a.get("rel_to") and a.get("rel_to") == b.get("rel_to"))

    def collides(self, it: dict, x: float, z: float, yaw: float) -> str | None:
        poly = self.footprint(it, x, z, yaw)
        if not self.room.inside(poly, 0.01):
            return "outside"
        for zn in self.blocked_zones:
            if overlap(poly, zn):
                return "door"
        for o in self.room.openings:  # tall pieces don't stand in front of windows
            if o["type"] == "window" and it["h"] > o["sill"] - 0.05 and it["place"] == "floor" and it["cat"] not in SEATS and it["cat"] not in ("desk", "table", "plant", "lamp_floor"):
                wx, wz = self.room.wall_point(o["wall"], o["u"], 0.35)
                win = rect(wx, wz, o["width"] + 0.1, 0.7, self.room.wall_yaw(o["wall"]))
                if overlap(poly, win):
                    return "window"
        for other in self.placed.values():
            if other["place"] != "floor" or other.get("flat"):
                continue
            if overlap(poly, self.footprint(other), 0.02):
                if it.get("rel", {}).get("at_desk") == other["id"] or it.get("rel", {}).get("around") == other["id"]:
                    continue  # chairs tuck under their desk / table (knee space)
                return "overlap:" + other["id"]
            cz_ = self.clear_zone(other)
            if cz_ and not self.related(it, other) and overlap(poly, cz_):
                return "clearance:" + other["id"]
        mine = self.clear_zone({**it, "x": x, "z": z, "yaw": yaw})
        if mine:
            for other in self.placed.values():
                if other["place"] == "floor" and not other.get("flat") and not self.related(it, other) and overlap(mine, self.footprint(other)):
                    return "my_clearance:" + other["id"]
        return None

    # --- walkway (grid BFS) ------------------------------------------------------------------------------------
    def walkway_ok(self, extra: dict | None = None, radius: float = 0.2, cell: float = 0.1) -> tuple[bool, list[str]]:
        x0, z0, x1, z1 = self.room.floor
        nx, nz = int((x1 - x0) / cell), int((z1 - z0) / cell)
        items = [p for p in self.placed.values() if p["place"] == "floor" and not p.get("flat")]
        if extra:
            items.append(extra)
        polys = [self.footprint(p, pad=2 * radius) for p in items]
        boxes = [(min(q[0] for q in pl), max(q[0] for q in pl), min(q[1] for q in pl), max(q[1] for q in pl)) for pl in polys]

        def free(i, j):
            px, pz = x0 + (i + 0.5) * cell, z0 + (j + 0.5) * cell
            if px < x0 + radius or px > x1 - radius or pz < z0 + radius or pz > z1 - radius:
                return False
            for pl, (a, b, c, d) in zip(polys, boxes):
                if a <= px <= b and c <= pz <= d and _point_in_quad((px, pz), pl):
                    return False
            return True

        def cell_of(p):
            return int((p[0] - x0) / cell), int((p[1] - z0) / cell)

        doors = [o for o in self.room.openings if o["type"] in ("door", "arch")]
        if not doors:
            return True, []
        start = cell_of(self.room.wall_point(doors[0]["wall"], doors[0]["u"], 0.45))
        grid = {}

        def ok(c):
            if c not in grid:
                grid[c] = 0 <= c[0] < nx and 0 <= c[1] < nz and free(*c)
            return grid[c]

        # targets: room centre region and access points
        targets = {"centre": cell_of(((x0 + x1) / 2, (z0 + z1) / 2))}
        for p in items:
            acc = p.get("access")
            if acc:
                targets[p["id"]] = cell_of(acc)
        seen = {start}
        dq = deque([start])
        if not ok(start):
            return False, ["door"]
        while dq:
            c = dq.popleft()
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + d[0], c[1] + d[1])
                if n not in seen and ok(n):
                    seen.add(n)
                    dq.append(n)
        missing = []
        for name, tc in targets.items():
            near = any((tc[0] + di, tc[1] + dj) in seen for di in range(-4, 5) for dj in range(-4, 5))
            if not near:
                missing.append(name)
        return not missing, missing

    # --- candidate generation -----------------------------------------------------------------------------------
    def candidates(self, it: dict) -> list[tuple[float, float, float, float, str | None]]:
        """(x, z, yaw, relation_error, wall) candidates for a floor item from its relations."""
        R, out = self.room, []
        rel = it["rel"]
        step = 0.1
        if "at" in rel and isinstance(rel["at"], (list, tuple)):
            out.append((float(rel["at"][0]), float(rel["at"][1]), float(rel.get("yaw", it.get("yaw_hint", 0))), 0.0, None))
        if "at_frac" in rel:
            fx, fz = rel["at_frac"]
            x0, z0, x1, z1 = R.floor
            bx, bz = x0 + (x1 - x0) * fx, z0 + (z1 - z0) * fz
            for dx in (0, -0.2, 0.2, -0.4, 0.4):
                for dz in (0, -0.2, 0.2):
                    out.append((bx + dx, bz + dz, float(rel.get("yaw", 0)), math.hypot(dx, dz), None))
        walls = None
        if rel.get("against"):
            walls = list(R.walls) if rel["against"] in ("any", True) else [rel["against"]]
        if rel.get("under_window"):
            walls = [o["wall"] for o in R.openings if o["type"] == "window"]
        if walls:
            gap = float(rel.get("gap", 0.02))
            if it["cat"] == "desk" and rel.get("user_faces") == "room":
                gap = max(gap, 0.95)
            for wname in walls:
                w = R.walls[wname]
                yaw = R.wall_yaw(wname)
                if it["cat"] == "desk" and rel.get("user_faces") == "room":
                    yaw = (yaw + 180) % 360     # model front (knee side) toward the wall: user sits between desk and wall
                depth = it["d"]
                want_u = rel.get("at")
                want_u = float(want_u) * w["L"] if isinstance(want_u, (int, float)) else None
                if rel.get("under_window"):
                    ws = [o for o in R.openings if o["type"] == "window" and o["wall"] == wname]
                    want_u = ws[0]["u"] if ws else want_u
                u = it["w"] / 2 + 0.05
                while u <= w["L"] - it["w"] / 2 - 0.05 + 1e-6:
                    x, z = R.wall_point(wname, u, depth / 2 + gap)
                    err = abs(u - want_u) if want_u is not None else 0.15 * abs(u - w["L"] / 2) / w["L"]
                    out.append((x, z, yaw, err, wname))
                    u += step
        if rel.get("corner"):
            c = rel["corner"]
            ns = "north" if "n" in c else "south"
            ew = "east" if "e" in c else "west"
            sx = 1 if ew == "east" else -1
            sz = 1 if ns == "north" else -1
            for wname, yaw in ((ns, R.wall_yaw(ns)), (ew, R.wall_yaw(ew))):
                w_, d_ = (it["w"], it["d"])
                if wname in ("east", "west"):
                    x = sx * (R.W / 2 - d_ / 2 - 0.04)
                    z = sz * (R.D / 2 - w_ / 2 - 0.06)
                else:
                    x = sx * (R.W / 2 - w_ / 2 - 0.06)
                    z = sz * (R.D / 2 - d_ / 2 - 0.04)
                for k in range(14):
                    sh = k * 0.12
                    if wname in ("east", "west"):
                        out.append((x, z - sz * sh, yaw, sh, wname))
                    else:
                        out.append((x - sx * sh, z, yaw, sh, wname))
        parent = self.placed.get(rel.get("at_desk") or rel.get("in_front_of") or rel.get("beside") or rel.get("near")
                                 or rel.get("behind") or rel.get("around") or rel.get("opposite") or "")
        if rel.get("at_desk") and parent:
            # the knee side of the desk is its model front
            fx, fz = _fwd(parent["yaw"])
            dist = parent["d"] / 2 + it["d"] / 2 - 0.12
            for k, sh in enumerate((0, -0.15, 0.15, -0.3, 0.3)):
                rx, rz = _right(parent["yaw"])
                out.append((parent["x"] + fx * dist + rx * sh, parent["z"] + fz * dist + rz * sh, (parent["yaw"] + 180) % 360, abs(sh), None))
        if rel.get("in_front_of") and parent:
            yaw_p = parent["yaw"]
            if parent["cat"] in ("desk", "table"):
                yaw_p = (yaw_p + 180) % 360  # visitor side of a desk
            fx, fz = _fwd(yaw_p)
            rx, rz = _right(yaw_p)
            gap = float(rel.get("gap", 0.45))
            dist = parent["d"] / 2 + gap + it["d"] / 2
            n = it.get("count_total", 1)
            idx = it.get("count_index", 0)
            spread = (idx - (n - 1) / 2) * (it["w"] + 0.35) if n > 1 else 0
            for dd in (0, 0.15, -0.1, 0.3):
                for ds in (0, 0.15, -0.15, 0.3, -0.3):
                    x = parent["x"] + fx * (dist + dd) + rx * (spread + ds)
                    z = parent["z"] + fz * (dist + dd) + rz * (spread + ds)
                    yaw = (yaw_p + 180) % 360 if rel.get("facing") == rel.get("in_front_of") else parent["yaw"]
                    if n > 1 and rel.get("facing"):
                        yaw = (_yaw_of(parent["x"] - x, parent["z"] - z) + 180 * 0) % 360
                    out.append((x, z, yaw, abs(dd) + abs(ds), None))
        if rel.get("beside") and parent:
            rx, rz = _right(parent["yaw"])
            fx, fz = _fwd(parent["yaw"])
            sides = {"left": [-1, 1], "right": [1, -1]}.get(rel.get("side"), [1, -1])
            for s in sides:
                dist = parent["w"] / 2 + it["w"] / 2 + float(rel.get("gap", 0.12))
                for dd in (0, 0.1, 0.25, 0.45):
                    for back in (0.0, -0.2, 0.2, 0.45):
                        x = parent["x"] + rx * s * (dist + dd) + fx * (back + (it["d"] - parent["d"]) / 2 * -1 * (1 if parent.get("wall") else 0))
                        z = parent["z"] + rz * s * (dist + dd) + fz * (back + (it["d"] - parent["d"]) / 2 * -1 * (1 if parent.get("wall") else 0))
                        yaw = parent["yaw"]
                        out.append((x, z, yaw, dd + abs(back) * 0.6 + (0 if s == sides[0] else 0.3), None))
        if rel.get("around") and parent:
            n = it.get("count_total", 1)
            idx = it.get("count_index", 0)
            for k in range(12):
                ang = (idx / max(1, n)) * 360 + k * 30 * (1 if k % 2 else -1) * (k // 2) / 6
                fx, fz = _fwd(ang)
                dist = max(parent["w"], parent["d"]) / 2 + it["d"] / 2 + 0.02
                x, z = parent["x"] + fx * dist, parent["z"] + fz * dist
                out.append((x, z, (ang + 180) % 360, abs(k) * 0.1, None))
        if rel.get("near") and parent:
            dist = float(rel.get("dist", 1.0))
            for k in range(24):
                ang = k * 15
                fx, fz = _fwd(ang)
                out.append((parent["x"] + fx * dist, parent["z"] + fz * dist, self.rng.choice([0, 90, 180, 270]) + self.rng.uniform(-20, 20), 0.0, None))
        if rel.get("opposite") and parent and parent.get("wall"):
            opp = {"north": "south", "south": "north", "east": "west", "west": "east"}[parent["wall"]]
            w = R.walls[opp]
            # u on the opposite wall closest to the parent
            for k in range(-6, 7):
                px, pz = parent["x"], parent["z"]
                u = (px - w["a"][0]) * w["t"][0] + (pz - w["a"][1]) * w["t"][1] + k * 0.1
                if it["w"] / 2 < u < w["L"] - it["w"] / 2:
                    x, z = R.wall_point(opp, u, it["d"] / 2 + 0.02)
                    out.append((x, z, R.wall_yaw(opp), abs(k) * 0.1, opp))
        if rel.get("center"):
            for dx in (0, -0.3, 0.3):
                for dz in (0, -0.3, 0.3):
                    out.append((dx, dz, float(rel.get("yaw", 0)), math.hypot(dx, dz), None))
        if not out:  # anywhere on the floor, preferring walls for big pieces
            x0, z0, x1, z1 = R.floor
            for _ in range(160):
                x, z = self.rng.uniform(x0 + 0.3, x1 - 0.3), self.rng.uniform(z0 + 0.3, z1 - 0.3)
                wname = R.nearest_wall(x, z)
                yaw = R.wall_yaw(wname) if it["h"] > 0.9 else self.rng.uniform(0, 360)
                out.append((x, z, yaw, 0.5 + self.rng.random() * 0.2, None))
        # facing override
        face = rel.get("facing")
        if face and not rel.get("in_front_of"):
            tgt = self._facing_target(face)
            if tgt:
                out = [(x, z, _yaw_of(tgt[0] - x, tgt[1] - z), e, w) for x, z, _, e, w in out]
        return out

    def _facing_target(self, face):
        if isinstance(face, (list, tuple)):
            return float(face[0]), float(face[1])
        if face in self.placed:
            return self.placed[face]["x"], self.placed[face]["z"]
        if face == "center":
            return 0.0, 0.0
        for o in self.room.openings:
            if o["type"] == face or (face == "door" and o["type"] in ("door", "arch")):
                return self.room.wall_point(o["wall"], o["u"])
        return None

    # --- main ---------------------------------------------------------------------------------------------------
    def place_floor(self, it: dict) -> bool:
        cands = self.candidates(it)
        scored = []
        for x, z, yaw, err, wname in cands:
            why = self.collides(it, x, z, yaw)
            if why:
                continue
            # spacing: prefer not hugging other furniture unless related
            s = -err * 2
            for other in self.placed.values():
                if other["place"] == "floor" and not self.related(it, other):
                    d = math.hypot(other["x"] - x, other["z"] - z)
                    s -= max(0, 1.2 - d) * 0.3
            s += self.rng.random() * 0.05
            scored.append((s, x, z, yaw, wname))
        scored.sort(key=lambda c: -c[0])
        for s, x, z, yaw, wname in scored[:25]:
            cand = {**it, "x": x, "z": z, "yaw": yaw, "wall": wname}
            cand["access"] = self._access(cand)
            if it.get("flat") or it["h"] < 0.15:
                ok = True
            else:
                ok, missing = self.walkway_ok(cand)
            if ok:
                self.commit(cand)
                return True
        if scored:
            s, x, z, yaw, wname = scored[0]
            cand = {**it, "x": x, "z": z, "yaw": yaw, "wall": wname}
            cand["access"] = self._access(cand)
            self.commit(cand)
            self.notes.append(f"{it['id']}: placed without a clear walkway")
            return True
        reasons = {}
        for x, z, yaw, err, wname in cands[:400]:
            r = (self.collides(it, x, z, yaw) or "ok").split(":")[0]
            reasons[r] = reasons.get(r, 0) + 1
        self.unplaced.append({"id": it["id"], "cat": it["cat"], "why": reasons})
        return False

    def _access(self, it: dict):
        if it["cat"] not in CLEAR_FRONT and it["cat"] not in SEATS:
            return None
        rel = it.get("rel", {})
        if rel.get("at_desk") or rel.get("around"):
            return None  # reached through its desk/table
        yaw = it["yaw"]
        fx, fz = _fwd(yaw)
        if it["cat"] == "desk" and rel.get("user_faces") == "room":
            # walk round the end of the desk to the chair behind it
            rx, rz = _right(yaw)
            best = None
            for s_ in (1, -1):
                p = (it["x"] + rx * s_ * (it["w"] / 2 + 0.35) + fx * 0.3, it["z"] + rz * s_ * (it["w"] / 2 + 0.35) + fz * 0.3)
                if self.room.inside([p], 0.2) and best is None:
                    best = p
            return best
        d = it["d"] / 2 + 0.45
        return (it["x"] + fx * d, it["z"] + fz * d)

    def commit(self, it: dict):
        self.placed[it["id"]] = it
        self.order.append(it["id"])

    def place_surface(self, it: dict, parent_id: str) -> bool:
        p = self.placed.get(parent_id)
        if not p:
            self.unplaced.append({"id": it["id"], "why": {"no_parent": parent_id}})
            return False
        top = p.get("top") or p["h"]
        # usable top rect in the parent frame (shrink a little), user-relative sides for desks
        uw, ud = p["w"] - 0.08, p["d"] - 0.08
        user_yaw = (p["yaw"] + 180) % 360 if p["cat"] == "desk" else p["yaw"]
        rx, rz = _right(user_yaw)
        fx, fz = _fwd(user_yaw)
        side = it["rel"].get("side", "")
        siblings = [q for q in self.placed.values() if q.get("parent") == parent_id]
        best = None
        for k in range(80):
            if side == "left":
                sx = self.rng.uniform(-uw / 2 + it["w"] / 2, -uw * 0.1)
            elif side == "right":
                sx = self.rng.uniform(uw * 0.1, uw / 2 - it["w"] / 2)
            elif side == "center":
                sx = self.rng.uniform(-uw * 0.15, uw * 0.15)
            else:
                sx = self.rng.uniform(-uw / 2 + it["w"] / 2, uw / 2 - it["w"] / 2) if uw > it["w"] else 0
            # the far half of the desk (away from the user) for lamps/phones, near half for papers
            far = it["cat"] in ("lamp_desk", "phone", "books", "radio", "tv", "plant_small", "photo", "clock_small", "vase", "candle")
            lo, hi = (-ud / 2 + it["d"] / 2, ud / 2 - it["d"] / 2)
            if hi < lo:
                lo = hi = 0
            sz = self.rng.uniform(lo, hi)
            if far and p["cat"] in ("desk",):
                sz = self.rng.uniform(max(lo, 0), hi) if hi > 0 else 0
            x = p["x"] + rx * sx + fx * sz
            z = p["z"] + rz * sx + fz * sz
            yaw = (user_yaw + 180 + self.rng.uniform(-25, 25)) % 360 if it["cat"] in ("phone", "lamp_desk", "photo", "radio", "tv", "clock_small") else self.rng.uniform(0, 360) if it["cat"] in ("ashtray", "candle", "vase", "bowl", "plant_small") else (user_yaw + self.rng.uniform(-15, 15)) % 360
            poly = rect(x, z, it["w"], it["d"], yaw)
            if not all(_point_in_quad(q, rect(p["x"], p["z"], p["w"] - 0.02, p["d"] - 0.02, p["yaw"])) for q in poly):
                continue
            if any(overlap(poly, rect(s["x"], s["z"], s["w"], s["d"], s["yaw"]), 0.015) for s in siblings):
                continue
            best = (x, z, yaw)
            break
        if not best:
            if not it.get("_turned") and abs(it["w"] - it["d"]) > 0.1:
                return self.place_surface({**it, "w": it["d"], "d": it["w"], "_turned": True, "front": (it.get("front", 0) + 90) % 360}, parent_id)
            self.unplaced.append({"id": it["id"], "cat": it["cat"], "why": {"surface_full": parent_id}})
            return False
        x, z, yaw = best
        self.commit({**it, "x": x, "z": z, "yaw": yaw, "y": top, "parent": parent_id})
        return True

    def place_wall(self, it: dict) -> bool:
        R, rel = self.room, it["rel"]
        walls = [rel["on_wall"]] if rel.get("on_wall") not in (None, "any") else list(R.walls)
        above = self.placed.get(rel.get("above") or "")
        if above and above.get("wall"):
            walls = [above["wall"]]
        best = None
        for wname in walls:
            w = R.walls[wname]
            for k in range(int(w["L"] / 0.1)):
                u = it["w"] / 2 + 0.1 + k * 0.1
                if u > w["L"] - it["w"] / 2 - 0.1:
                    break
                y = float(rel.get("height", it.get("mount") or 1.55))
                err = 0.0
                if above:
                    au = (above["x"] - w["a"][0]) * w["t"][0] + (above["z"] - w["a"][1]) * w["t"][1]
                    n = it.get("count_total", 1)
                    idx = it.get("count_index", 0)
                    au += (idx - (n - 1) / 2) * (it["w"] + 0.25)
                    err = abs(u - au)
                    y = max(y, above["h"] + 0.35 + it["h"] / 2) if "height" not in rel else y
                elif isinstance(rel.get("at"), (int, float)):
                    err = abs(u - rel["at"] * w["L"])
                else:
                    err = abs(u - w["L"] / 2) * 0.2 + self.rng.random() * 0.4
                y0, y1 = y - it["h"] / 2, y + it["h"] / 2
                if y1 > R.H - 0.05 or y0 < 0.05:
                    continue
                if any(o["wall"] == wname and abs(u - o["u"]) < (o["width"] + it["w"]) / 2 + 0.08 and y1 > o.get("sill", 0) - 0.05 and y0 < o.get("sill", 0) + o["height"] + 0.1
                       for o in R.openings):
                    continue
                if any(q["wall"] == wname and q["u1"] + 0.08 > u - it["w"] / 2 and q["u0"] - 0.08 < u + it["w"] / 2 and q["y1"] + 0.05 > y0 and q["y0"] - 0.05 < y1 for q in self.wall_used):
                    continue
                # tall furniture against this wall at that spot hides the wall behind it
                px, pz = R.wall_point(wname, u, 0.1)
                hidden = False
                for o in self.placed.values():
                    if o["place"] == "floor" and o.get("wall") == wname and o["h"] > y0 - 0.05:
                        ou = (o["x"] - w["a"][0]) * w["t"][0] + (o["z"] - w["a"][1]) * w["t"][1]
                        if abs(ou - u) < (o["w"] + it["w"]) / 2 + 0.05:
                            hidden = True
                            break
                if hidden:
                    continue
                if best is None or err < best[0]:
                    best = (err, wname, u, y)
        if not best:
            if rel.get("above") or rel.get("on_wall") not in (None, "any"):
                # fall back: anywhere on that wall, then any wall
                r2 = {k: v for k, v in rel.items() if k != "above"}
                if rel.get("above"):
                    return self.place_wall({**it, "rel": r2})
                return self.place_wall({**it, "rel": {**r2, "on_wall": "any"}})
            self.unplaced.append({"id": it["id"], "cat": it["cat"], "why": {"no_wall_space": walls}})
            return False
        err, wname, u, y = best
        w = R.walls[wname]
        x, z = R.wall_point(wname, u, it["d"] / 2)
        wd = 0.0  # inner wall surface: n . p = -half extent
        n = w["n"]
        wall_d = -(R.D / 2 if wname in ("north", "south") else R.W / 2)
        self.wall_used.append({"wall": wname, "u0": u - it["w"] / 2, "u1": u + it["w"] / 2, "y0": y - it["h"] / 2, "y1": y + it["h"] / 2})
        self.commit({**it, "x": x, "z": z, "y": y, "yaw": R.wall_yaw(wname), "wall": wname, "wallN": list(n), "wallD": wall_d})
        return True

    def place_ceiling(self, it: dict, x: float | None = None, z: float | None = None) -> bool:
        rel = it["rel"]
        above = self.placed.get(rel.get("above") or "")
        if x is None:
            x, z = (above["x"], above["z"]) if above else (0.0, 0.0)
        for q in self.placed.values():
            if q["place"] == "ceiling" and math.hypot(q["x"] - x, q["z"] - z) < (q["w"] + it["w"]) / 2:
                x += (q["w"] + it["w"]) / 2 + 0.2
        hang = it["h"]
        self.commit({**it, "x": x, "z": z, "y": self.room.H - hang, "yaw": rel.get("yaw", 0)})
        return True


# =====================================================================================================================
# Resolve: spec -> WorldJob

def _mat_choice(L: Library, v, use: str, tags: list[str], rng) -> str:
    if isinstance(v, str):
        return L.pick_material(use, tags, rng, prefer=v)
    if isinstance(v, dict):
        return L.pick_material(use, list(v.get("tags", [])) + tags, rng, prefer=v.get("id"))
    return L.pick_material(use, tags, rng)


def resolve(spec: dict, log=_log) -> dict:
    """World spec -> the resolved world (Unity WorldJob + metadata for validation and shots)."""
    t0 = time.time()
    L = lib()
    seed = int(spec.get("seed", 0))
    rng = random.Random(seed * 7919 + 13)
    tags = list(spec.get("style", []))
    r = spec.get("room", {})
    W, D = (float(v) for v in r.get("size", [5, 4]))
    H = float(r.get("height", 2.8))
    room = Room(W, D, H)
    features, walls_extra = [], {}
    # trench (subway platform): the walkable floor stops at the platform edge
    tr = r.get("trench")
    if tr:
        tw, td = float(tr.get("width", 3.4)), float(tr.get("depth", 1.25))
        if tr.get("wall", "north") == "north":
            edge = D / 2 - tw
            room.floor = (-W / 2, -D / 2, W / 2, edge)
            features += [
                {"type": "trench", "pos": [0, -td - 0.1, D / 2 - tw / 2], "size": [W, 0.2, tw], "mat": "concrete_floor_worn"},
                {"type": "box", "pos": [0, -td / 2, edge + 0.12], "size": [W, td, 0.24], "mat": "concrete_wall"},
            ]
            for zr in (edge + 1.0, edge + 2.4):
                features.append({"type": "rail", "pos": [0, -td + 0.08, zr], "size": [W, 0.15, 0.08], "color": [0.32, 0.3, 0.28]})
            for k in range(int(W / 0.65)):
                features.append({"type": "box", "pos": [-W / 2 + 0.3 + k * 0.65, -td + 0.0, edge + 1.7], "size": [0.24, 0.12, 2.3], "color": [0.22, 0.19, 0.16]})
            if r.get("edge_strip", True):
                features.append({"type": "strip", "pos": [0, 0.004, edge - 0.25], "size": [W, 0.008, 0.4], "color": [0.85, 0.7, 0.12]})
            walls_extra = {"north": {"baseY": -td}, "east": {"baseY": -td, "tunnel": (tw, td)}, "west": {"baseY": -td, "tunnel": (tw, td)}}
    cols = r.get("columns")
    col_positions = []
    if cols:
        n = int(cols.get("count", 4))
        z = room.floor[3] - float(cols.get("offset", 2.0))
        for k in range(n):
            x = -W / 2 + (k + 0.5) * W / n
            col_positions.append((x, z))
            features.append({"type": "column", "pos": [x, H / 2, z], "size": [0.55, H, 0.55], "mat": "subway_tiles" if "subway" in tags else (r.get("walls") if isinstance(r.get("walls"), str) else "")})

    floor_mat = _mat_choice(L, r.get("floor"), "floor", tags, rng)
    wall_mat = _mat_choice(L, r.get("walls"), "wall", tags, rng)
    ceil_mat = _mat_choice(L, r.get("ceiling", "ceiling_plaster"), "ceiling", tags, rng)
    used_mats = {floor_mat, wall_mat, ceil_mat}

    # openings
    for o in spec.get("openings", []):
        w = room.walls[o["wall"]]
        u = o.get("u")
        if u is None:
            at = o.get("at", 0.5)
            u = (0.5 if at == "center" else float(at)) * w["L"]
        width = float(o.get("width", 1.2 if o["type"] == "window" else 0.9))
        u = min(max(u, width / 2 + 0.15), w["L"] - width / 2 - 0.15)
        oo = {**o, "u": u, "width": width, "height": float(o.get("height", 1.4 if o["type"] == "window" else 2.05)),
              "sill": float(o.get("sill", 0.9)) if o["type"] == "window" else 0.0}
        room.openings.append(oo)
    for wname, ex in walls_extra.items():
        if ex.get("tunnel"):
            tw, td = ex["tunnel"]
            w = room.walls[wname]
            u = tw / 2 if wname == "east" else w["L"] - tw / 2
            room.openings.append({"type": "tunnel", "wall": wname, "u": u, "width": tw - 0.1, "height": td + 3.0, "sill": -td})

    solver = Solver(room, L, tags, rng, log)
    for (x, z) in col_positions:
        solver.commit({"id": f"column_{len(solver.placed)}", "cat": "column", "place": "floor", "x": x, "z": z, "yaw": 0,
                       "w": 0.55, "d": 0.55, "h": H, "rel": {}, "structural": True})

    # expand counts and pick assets
    items_in = []
    for it in spec.get("items", []):
        if not it:
            continue
        n = int(it.get("count", 1))
        for k in range(n):
            q = copy.deepcopy(it)
            if n > 1:
                q["id"] = f"{it['id']}_{k + 1}"
                q["count_index"], q["count_total"] = k, n
                q["group"] = it["id"]
            items_in.append(q)
    used_assets: set = set()

    def make(it: dict) -> dict | None:
        cat = it.get("cat", "box")
        if it.get("proc") or cat == "rug":
            proc = it.get("proc", "rug")
            size = it.get("size") or [2.0, 0.012, 1.4]
            return {"id": it["id"], "cat": cat, "asset": proc, "src": "procedural", "proc": proc, "w": float(size[0]), "h": float(size[1]),
                    "d": float(size[2]), "place": "wall" if it.get("on_wall") else ("surface" if it.get("on") else "floor"), "rel": it,
                    "size": [float(v) for v in size], "color": it.get("color"), "emissive": float(it.get("emissive", 0)), "flat": cat == "rug"}
        m = L.pick_model(cat, tags, rng, exclude=used_assets if it.get("vary", True) else None, prefer=it.get("prefer") or it.get("asset"))
        if not m:
            solver.unplaced.append({"id": it["id"], "cat": cat, "why": {"no_asset": cat}})
            return None
        if m["cat"] not in ("chair", "lamp_ceiling", "frame", "candle", "trash", "bench") and not it.get("group"):
            used_assets.add(m["id"])
        w_, h_, d_ = L.size(m["id"])
        place = m["place"]
        if it.get("on"):
            place = "seat" if m["place"] == "seat" else "surface"
        if it.get("on_wall") or (m["place"] == "wall" and not it.get("against")):
            place = "wall"
        if it.get("ceiling") or it.get("grid") or m["place"] == "ceiling":
            place = "ceiling"
        if place == "seat":
            place = "surface"
        if m["place"] == "seat" and not it.get("on"):
            return None
        procx = {"proc": m["ref"], "size": [float(v) for v in m["size"]], "color": m.get("color")} if m["src"] == "procedural" else {}
        return {**procx, "id": it["id"], "cat": m["cat"], "asset": m["id"], "src": m["src"], "path": L.model_path(m), "front": L.front(m),
                "w": w_, "h": h_, "d": d_, "place": place, "rel": it, "top": m.get("top"), "seat": m.get("seat"), "light": m.get("light"),
                "light_spec": it.get("light"), "mount": m.get("mount"), "clear": CLEAR_FRONT.get(m["cat"], 0.0),
                "count_index": it.get("count_index", 0), "count_total": it.get("count_total", 1), "rel_to": it.get("at_desk") or it.get("in_front_of") or it.get("around") or it.get("on"),
                "lie": bool(m.get("lie")), "scale": float(m.get("scale", 1))}

    resolved = [x for x in (make(it) for it in items_in) if x]
    # order: floor items with no floor parent first (big first), then dependents, rugs, wall, surface, ceiling
    def dep(it):
        rel = it["rel"]
        return rel.get("at_desk") or rel.get("in_front_of") or rel.get("beside") or rel.get("around") or rel.get("near") or rel.get("opposite")
    floor_items = [i for i in resolved if i["place"] == "floor" and i["cat"] != "rug"]
    floor_items.sort(key=lambda i: (1 if dep(i) else 0, -(i["w"] * i["d"])))
    # dependents in order of their parents
    ordered, pending = [], list(floor_items)
    for _ in range(4):
        for i in list(pending):
            d = dep(i)
            if not d or d in {o["id"] for o in ordered} or d not in {q["id"] for q in floor_items}:
                ordered.append(i)
                pending.remove(i)
    ordered += pending
    for it in ordered:
        if solver.place_floor(it) or it["src"] == "procedural":
            continue
        # repair: try smaller alternatives of the same category (an over-sized desk in a cramped room)
        alts = sorted((m for m in L.man["models"] if m["cat"] == it["cat"] and m["id"] != it["asset"]), key=lambda m: L.size(m["id"])[0] * L.size(m["id"])[2])
        for m in alts[:4]:
            w_, h_, d_ = L.size(m["id"])
            if w_ * d_ >= it["w"] * it["d"]:
                continue
            solver.unplaced.pop()
            alt = {**it, "asset": m["id"], "src": m["src"], "path": L.model_path(m), "front": L.front(m), "w": w_, "h": h_, "d": d_,
                   "top": m.get("top"), "seat": m.get("seat"), "light": m.get("light"), "scale": float(m.get("scale", 1))}
            if solver.place_floor(alt):
                solver.notes.append(f"{it['id']}: swapped {it['asset']} for the smaller {m['id']} to fit")
                break
    for it in [i for i in resolved if i["cat"] == "rug"]:
        under = [solver.placed[u] for u in it["rel"].get("under", []) if u in solver.placed]
        if under:
            xs = [q[0] for u in under for q in rect(u["x"], u["z"], u["w"], u["d"], u["yaw"])]
            zs = [q[1] for u in under for q in rect(u["x"], u["z"], u["w"], u["d"], u["yaw"])]
            cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
            rw, rd = min(max(xs) - min(xs) + 0.3, W - 0.6), min(max(zs) - min(zs) + 0.3, D - 0.6)
            fx0, fz0, fx1, fz1 = room.floor
            cx = min(max(cx, fx0 + rw / 2 + 0.25), fx1 - rw / 2 - 0.25)
            cz = min(max(cz, fz0 + rd / 2 + 0.25), fz1 - rd / 2 - 0.25)
        else:
            cx, cz, rw, rd = 0.0, 0.0, min(2.4, W * 0.45), min(1.7, D * 0.4)
        rug_mat = _mat_choice(L, it["rel"].get("mat"), "rug", tags, rng)
        used_mats.add(rug_mat)
        solver.commit({**it, "x": cx, "z": cz, "yaw": 0, "w": rw, "d": rd, "h": 0.012, "size": [rw, 0.012, rd], "mat": rug_mat, "flat": True})
    for it in [i for i in resolved if i["place"] == "wall"]:
        solver.place_wall(it)
    for it in [i for i in resolved if i["place"] == "surface"]:
        solver.place_surface(it, it["rel"]["on"])
    for it in [i for i in resolved if i["place"] == "ceiling"]:
        grid = it["rel"].get("grid")
        if grid:
            nx, nz = grid
            x0, z0, x1, z1 = room.floor
            for a in range(nx):
                for b in range(nz):
                    q = {**it, "id": f"{it['id']}_{a}_{b}"}
                    solver.place_ceiling(q, x0 + (a + 0.5) * (x1 - x0) / nx, z0 + (b + 0.5) * (z1 - z0) / nz)
        else:
            solver.place_ceiling(it)

    # clutter
    density = float(spec.get("clutter", 0.5))
    _clutter(solver, L, tags, rng, density)
    # lighting + effects + cameras
    lighting = light_plan(spec, solver, room, L, rng, tags, (floor_mat, wall_mat, ceil_mat))
    effects = _effects(spec, solver, room, lighting, rng)
    cams = cameras(spec, solver, room)

    # materials list
    used_mats |= {q["mat"] for q in solver.placed.values() if q.get("mat")}
    for o in room.openings:
        if o.get("curtains"):
            o["curtainMat"] = o.get("curtainMat") or L.pick_material("curtain", tags, rng)
            used_mats.add(o["curtainMat"])
    job = {
        "kind": "world", "id": spec.get("name", "world"), "seed": seed, "width": int(spec.get("width", 1920)), "height": int(spec.get("height", 1080)),
        "supersample": float(spec.get("supersample", 1.5)),
        "room": {"w": W, "d": D, "h": H, "floorMat": floor_mat, "ceilingMat": ceil_mat, "floorRect": list(room.floor),
                 "trimColor": r.get("trim", [0.88, 0.86, 0.82] if "noir" not in tags else [0.25, 0.18, 0.12]), "ceiling": True, "features": features},
        "walls": [],
        "materials": [L.mat_paths(m) for m in sorted(used_mats) if m in L.materials],
        "items": [],
        **lighting["job"],
        "effects": effects,
        "stills": cams["stills"], "move": cams["move"],
    }
    for name, w in room.walls.items():
        a = w["a"]
        b = (a[0] + w["t"][0] * w["L"], a[1] + w["t"][1] * w["L"])
        ops = []
        for o in room.openings:
            if o["wall"] != name:
                continue
            ops.append({"type": o["type"], "u": o["u"], "width": o["width"], "height": o["height"], "sill": o["sill"],
                        "glass": o.get("glass", True), "blinds": bool(o.get("blinds")), "blindsTilt": float(o.get("blinds_tilt", 35)),
                        "curtains": bool(o.get("curtains")), "curtainMat": o.get("curtainMat", ""), "rainy": bool(o.get("rainy")),
                        "doorOpen": float(o.get("open", 0)), "frameColor": o.get("frame_color", [0.85, 0.83, 0.78] if "noir" not in tags else [0.3, 0.22, 0.15])})
        ex = walls_extra.get(name, {})
        job["walls"].append({"name": "Wall_" + name, "a": list(a), "b": list(b), "n": list(w["n"]), "mat": r.get("wall_mats", {}).get(name, wall_mat),
                             "height": H, "baseY": ex.get("baseY", 0.0), "openings": ops, "baseboard": "subway" not in tags,
                             **({"tint": r["wall_tint"]} if r.get("wall_tint") else {})})
    for iid in solver.order:
        p = solver.placed[iid]
        if p.get("structural"):
            continue
        anchor = {"floor": "floor", "wall": "wall", "surface": "surface", "ceiling": "ceiling"}[p["place"]]
        if p["place"] == "floor" and p.get("wall") and p["h"] > 0.3:
            anchor = "wall"  # pushed flush against its wall using the real mesh bounds
        e = {"id": iid, "asset": p["asset"], "path": p.get("path", ""), "src": p["src"], "proc": p.get("proc", ""),
             "pos": [round(p["x"], 4), round(p.get("y", 0.0) if p["place"] != "floor" else 0.0, 4), round(p["z"], 4)],
             "yaw": round(p["yaw"], 2), "front": p.get("front", 0.0), "scale": p.get("scale", 1.0), "anchor": anchor,
             "on": p.get("parent", ""), "lie": p.get("lie", False)}
        if anchor == "wall":
            w = room.walls[p["wall"]]
            e["wallN"] = list(w["n"])
            e["wallD"] = -(room.D / 2 if p["wall"] in ("north", "south") else room.W / 2) + (0.0 if p["place"] == "wall" else (p["rel"].get("gap", 0.02) if not (p["cat"] == "desk" and p["rel"].get("user_faces") == "room") else 0.95))
            e["mountY"] = round(p["y"], 3) if p["place"] == "wall" else -1
            if p["cat"] == "desk" and p["rel"].get("user_faces") == "room":
                e["anchor"] = "floor"  # desk stands free with the chair space behind it
        if p["src"] == "quaternius":
            e["fitHeight"] = p["h"]
        if p.get("proc"):
            e["size"] = p["size"]
            if p.get("mat"):
                e["mat"] = p["mat"]
            if p.get("color"):
                e["color"] = p["color"]
            e["emissive"] = p.get("emissive", 0)
            e["shadows"] = p["cat"] != "rug"
        job["items"].append(e)
    meta = {"spec": spec, "tags": tags, "placed": {k: _slim(v) for k, v in solver.placed.items()}, "unplaced": solver.unplaced,
            "notes": solver.notes, "openings": room.openings, "floor": room.floor, "lighting": lighting["meta"],
            "focus": cams["focus"], "solve_s": round(time.time() - t0, 3)}
    walk_ok, missing = solver.walkway_ok()
    meta["walkway"] = {"ok": walk_ok, "unreachable": missing}
    return {"job": job, "meta": meta}


def _slim(p: dict) -> dict:
    keep = ("id", "cat", "asset", "place", "x", "y", "z", "yaw", "w", "h", "d", "wall", "parent", "top", "seat", "access", "path", "front", "src")
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items() if k in keep}


def _clutter(S: Solver, L: Library, tags: list[str], rng: random.Random, density: float) -> None:
    """Surface clutter on desks/tables/sideboards, floor clutter in free corners, wall decor on free wall spans."""
    if density <= 0:
        return
    surf_pool = [m for m in L.man["models"] if m["place"] == "surface" and m["cat"] not in ("lamp_desk", "tv", "phone")]
    floor_pool = [m for m in L.man["models"] if m["place"] == "floor" and m["cat"] in ("plant", "basket", "box", "crate", "trash", "vase", "barrel")]
    wall_pool = [m for m in L.man["models"] if m["place"] == "wall" and m["cat"] in ("frame", "mirror", "clock")]

    def score(m):
        mt = set(m.get("tags", []))
        return sum(2 for t in tags if t in mt) + (0.5 if "any" in mt else 0) + rng.random() - (2 if m["src"] == "kenney" else 0)

    k = 0
    present = {p.get("asset") for p in S.placed.values()} | {p.get("cat") for p in S.placed.values() if p.get("cat") in ("ashtray", "phone", "lamp_desk", "tv", "clock_small")}
    for pid, p in list(S.placed.items()):
        if p.get("cat") not in SURFACES or p["place"] != "floor" or (p.get("top") or p["h"]) > 1.3 or p["cat"] == "bookshelf":
            continue
        area = p["w"] * p["d"]
        n = int(round(density * min(6, area * (5 if p["cat"] == "desk" else 3))))
        pool = sorted(surf_pool, key=score, reverse=True)[:12]
        rng.shuffle(pool)
        for m in [m for m in pool if m["id"] not in present and m["cat"] not in present][:n]:
            if m["cat"] in ("paper",) and p["cat"] not in ("desk", "table"):
                continue
            present.add(m["id"])
            w_, h_, d_ = L.size(m["id"])
            if h_ > 0.6 or w_ > p["w"] * 0.6:
                continue
            it = {"id": f"clutter_{k}", "cat": m["cat"], "asset": m["id"], "src": m["src"], "path": L.model_path(m), "front": L.front(m),
                  **({"proc": m["ref"], "size": [float(v) for v in m["size"]]} if m["src"] == "procedural" else {}),
                  "w": w_, "h": h_, "d": d_, "place": "surface", "rel": {"on": pid}, "lie": bool(m.get("lie")), "scale": float(m.get("scale", 1))}
            if S.place_surface(it, pid):
                k += 1
            else:
                S.unplaced.pop()  # clutter that doesn't fit is simply skipped
    # floor clutter: a few items along walls in free spots
    nf = int(round(density * (S.room.floor[2] - S.room.floor[0]) * (S.room.floor[3] - S.room.floor[1]) / 9))
    pool = sorted(floor_pool, key=score, reverse=True)[:6]
    for i in range(nf):
        if not pool:
            break
        m = pool[i % len(pool)]
        w_, h_, d_ = L.size(m["id"])
        it = {"id": f"floorclutter_{i}", "cat": m["cat"], "asset": m["id"], "src": m["src"], "path": L.model_path(m), "front": L.front(m),
              "w": w_, "h": h_, "d": d_, "place": "floor", "rel": {"against": "any"}, "clear": 0, "scale": float(m.get("scale", 1))}
        if not S.place_floor(it):
            S.unplaced.pop()
    # wall decor
    total_wall = sum(w["L"] for w in S.room.walls.values())
    nw = int(round(density * total_wall / 6))
    pool = sorted(wall_pool, key=score, reverse=True)[:6]
    have = sum(1 for p in S.placed.values() if p["place"] == "wall")
    for i in range(max(0, nw - have)):
        if not pool:
            break
        m = pool[i % len(pool)]
        w_, h_, d_ = L.size(m["id"])
        it = {"id": f"walldecor_{i}", "cat": m["cat"], "asset": m["id"], "src": m["src"], "path": L.model_path(m), "front": L.front(m),
              "w": w_, "h": h_, "d": d_, "place": "wall", "rel": {"on_wall": "any", "height": 1.55 + rng.uniform(-0.1, 0.15)}, "scale": 1.0,
              **({"proc": m["ref"], "size": [float(v) for v in m["size"]], "color": m.get("color")} if m["src"] == "procedural" else {})}
        if not S.place_wall(it):
            S.unplaced.pop()


# =====================================================================================================================
# Lighting from text

def _time_key(v) -> str:
    if isinstance(v, (int, float)):
        h = float(v)
        return ("night" if h < 5 or h >= 21 else "dawn" if h < 6 else "sunrise" if h < 7 else "morning" if h < 11 else
                "noon" if h < 14 else "afternoon" if h < 17.5 else "golden_hour" if h < 19 else "dusk" if h < 20 else "evening")
    v = str(v or "afternoon").lower().replace(" ", "_")
    return v if v in TIMES else {"day": "afternoon", "midnight": "night", "sunset": "golden_hour", "twilight": "dusk"}.get(v, "afternoon")


def light_plan(spec: dict, S: Solver, room: Room, L: Library, rng: random.Random, tags: list[str], mats: tuple = ()) -> dict:
    ls = spec.get("lighting", {}) or {}
    tk = _time_key(ls.get("time", "afternoon"))
    wk = str(ls.get("weather", "clear")).lower()
    wk = wk if wk in WEATHER else "clear"
    mood_k = str(ls.get("mood", "neutral")).lower()
    mood = MOODS.get(mood_k, MOODS["neutral"])
    T, Wt = TIMES[tk], WEATHER[wk]
    sky_lux = T["sky"] * Wt["sky"]
    sun_lux = T["sun"] * Wt["sun"] if T["elev"] > 0 else 0.0
    k_sky = Wt.get("k_sky", T["k_sky"]) if T["elev"] > -5 else T["k_sky"]
    windows = [o for o in room.openings if o["type"] == "window"]
    win_area = sum(o["width"] * o["height"] for o in windows)
    surf_area = 2 * room.W * room.D + 2 * (room.W + room.D) * room.H
    # mean surface albedo, area-weighted: floor, walls, ceiling
    fl, wl, cl = (list(mats) + ["", "", ""])[:3]
    a_floor, a_wall = room.W * room.D, 2 * (room.W + room.D) * room.H
    albedo = (ALBEDO.get(fl, 0.4) * a_floor + ALBEDO.get(wl, 0.5) * a_wall + ALBEDO.get(cl, 0.75) * a_floor) / (2 * a_floor + a_wall)
    rho = max(0.15, min(0.75, albedo))
    focus = cameras_focus(spec, S, room)
    fx, fy, fz = focus

    lights, meta_l = [], []
    practical_flux, practical_k = 0.0, []
    # --- practicals from items with built-in lights -----------------------------------------------------------
    defaults_on = tk in ("night", "evening", "dusk") or wk in ("storm", "rain") or mood_k in ("noir", "cozy", "romantic")
    overrides = ls.get("practicals", {}) or {}
    decay = "abandoned" in tags or mood_k == "eerie"
    for iid, p in S.placed.items():
        lt = p.get("light")
        if not lt:
            continue
        if decay and p.get("cat") == "lamp_ceiling" and rng.random() < 0.3:
            continue  # dead tube
        st = p.get("light_spec") or {}
        on = overrides.get(iid, {}).get("on", st.get("on", defaults_on if lt.get("when", "on") != "lit" else defaults_on))
        if overrides.get("all") is not None:
            on = overrides["all"]
        if not on:
            continue
        lm = float(overrides.get(iid, {}).get("lumens", st.get("lumens", lt["lumens"])))
        kk = float(overrides.get(iid, {}).get("kelvin", st.get("kelvin", lt["kelvin"])))
        practical_flux += lm
        practical_k.append((lm, kk))
        lights.append({"id": "prac_" + iid, "attach": iid, "type": lt.get("type", "point"), "pos": lt.get("offset", [0, 0.5, 0]),
                       "dir": lt.get("dir", [0, -1, 0]), "lm": lm, "k": kk, "range": float(lt.get("range", 6)), "angle": float(lt.get("angle", 100)),
                       "flicker": float(lt.get("flicker", 0)) or (0.6 if decay and p.get("cat") == "lamp_ceiling" and rng.random() < 0.25 else 0.0),
                       "glow": "flame" if lt.get("flame") else lt.get("glow", "bulb" if p.get("asset") in ("bare_bulb", "oil_lamp", "lantern") else "none"), "role": "practical",
                       "world": _attach_world(p, lt.get("offset", [0, 0.5, 0]))})
    # explicit extra practicals
    for q in ls.get("extra", []):
        lm, kk = SOURCES.get(q.get("source", "incandescent_60w"), (800, 2700))
        lm, kk = float(q.get("lumens", lm)), float(q.get("kelvin", kk))
        practical_flux += lm
        practical_k.append((lm, kk))
        lights.append({"id": q.get("id", f"extra{len(lights)}"), "type": q.get("type", "point"), "pos": q["pos"], "dir": q.get("dir", [0, -1, 0]),
                       "lm": lm, "k": kk, "range": float(q.get("range", 7)), "angle": float(q.get("angle", 100)), "flicker": float(q.get("flicker", 0)),
                       "glow": q.get("glow", "bulb"), "role": "practical", "world": tuple(q["pos"])})

    # --- daylight / window light ----------------------------------------------------------------------------
    sun = None
    win_light = ls.get("window_light", "auto")
    main_win = max(windows, key=lambda o: o["width"] * o["height"]) if windows else None
    if main_win and sun_lux > 0 and win_light not in ("none",):
        n = room.walls[main_win["wall"]]["n"]
        az = math.radians(float(ls.get("sun_azimuth_offset", rng.uniform(-35, 35))))
        el = math.radians(T["elev"])
        dxz = (n[0] * math.cos(az) - n[1] * math.sin(az), n[0] * math.sin(az) + n[1] * math.cos(az))
        sdir = [dxz[0] * math.cos(el), -math.sin(el), dxz[1] * math.cos(el)]
        sun = {"id": "sun", "type": "directional", "dir": sdir, "lux": sun_lux, "k": T["k_sun"], "role": "sun", "shadows": True}
    # light entering through windows (sky) and its indirect contribution
    sky_vert = sky_lux * 0.5
    flux_sky = sky_vert * win_area * 0.8
    flux_sun = 0.0
    if sun and main_win:
        n = room.walls[main_win["wall"]]["n"]
        cosi = max(0.0, sun["dir"][0] * n[0] + sun["dir"][2] * n[1])
        flux_sun = sun_lux * main_win["width"] * main_win["height"] * cosi * 0.8
    E_ind_day = (flux_sky + flux_sun) * rho / (surf_area * (1 - rho))
    E_ind_prac = practical_flux * rho / (surf_area * (1 - rho))
    # window light at night: street lamp outside (sodium), city glow, moon
    street = None
    if main_win and T["elev"] <= 0 and win_light in ("auto", "street", "streetlight"):
        n = room.walls[main_win["wall"]]["n"]
        wx, wz = room.wall_point(main_win["wall"], main_win["u"])
        side = rng.choice([-1, 1])
        t_ = room.walls[main_win["wall"]]["t"]
        sx, sz = wx - n[0] * 3.5 + t_[0] * side * 1.6, wz - n[1] * 3.5 + t_[1] * side * 1.6
        sy = main_win["sill"] + main_win["height"] + 1.6
        target = (wx + n[0] * 2.2, 0.6, wz + n[1] * 2.2)
        d = [target[0] - sx, target[1] - sy, target[2] - sz]
        street = {"id": "street", "type": "spot", "pos": [sx, sy, sz], "dir": d, "E_window": 22.0 if "noir" in tags or mood_k == "noir" else 9.0,
                  "k": 2000 if ls.get("street_kelvin") is None else float(ls["street_kelvin"]), "angle": 55, "range": 14, "shadows": True, "role": "street"}
    moon = None
    if main_win and T["elev"] <= 0 and win_light in ("auto", "moon", "street", "streetlight"):
        n = room.walls[main_win["wall"]]["n"]
        moon = {"id": "moon", "type": "directional", "dir": [n[0] * 0.75, -0.55, n[1] * 0.75], "lux": 0.35 if wk == "clear" else 0.12, "k": 4100, "role": "moon", "shadows": street is None}

    # --- exposure from a light meter at the focus point -----------------------------------------------------
    E_meter = E_ind_day + E_ind_prac
    E_direct_prac = 0.0
    for l in lights:
        px, py, pz = l["world"]
        d2 = max(0.15, (px - fx) ** 2 + (py - fy) ** 2 + (pz - fz) ** 2)
        cd = _candela(l)
        E_direct_prac += cd / d2
    E_daylight_direct = sky_lux * min(0.06, win_area / max(1.0, room.W * room.D) * 0.25)
    E_meter += E_direct_prac * 0.6 + E_daylight_direct
    if street:
        E_meter += street["E_window"] * 0.15
    E_meter = max(E_meter, 0.05)
    ev = math.log2(E_meter / 2.5) + mood["ev"] - float(ls.get("exposure", 0))  # + mood ev = darker; + exposure = brighter
    k_exp = 1.0 / (2.5 * 2 ** ev)

    # white balance: dominant source temperature + mood shift
    # camera white: log-mean colour temperature weighted by how much each source lights the focus point
    E_prac_tot = E_direct_prac * 0.6 + E_ind_prac
    E_day_tot = E_ind_day + E_daylight_direct
    srcs = []
    if practical_k and E_prac_tot > 0:
        pk = math.exp(sum(w * math.log(k) for w, k in practical_k) / sum(w for w, _ in practical_k))
        srcs.append((E_prac_tot, pk))
    if E_day_tot > 0.01:
        srcs.append((E_day_tot, k_sky if not sun else 0.5 * (k_sky + T["k_sun"])))
    key_k = math.exp(sum(w * math.log(k) for w, k in srcs) / sum(w for w, _ in srcs)) if srcs else 6500
    lo = 3600 if E_day_tot > 0.3 * max(1e-6, E_prac_tot) else 2600
    wb = float(ls.get("white_balance", max(lo, min(9000, key_k + mood["wb"]))))

    out_lights = []
    for l in lights:
        col, f = balanced(l["k"], wb)
        cd = _candela(l)
        out_lights.append({"id": l["id"], "type": l["type"], "pos": l["pos"], "dir": l["dir"], "color": col, "intensity": round(cd * k_exp * f, 5),
                           "range": l["range"], "angle": l.get("angle", 100), "inner": l.get("angle", 100) * 0.55, "shadows": False,
                           "flicker": l.get("flicker", 0), "glow": l.get("glow", "bulb"), "glowSize": 0.035 if l.get("glow") == "flame" else 0.06,
                           "glowIntensity": 3.0, "attach": l.get("attach", ""), "role": l["role"]})
    # shadows on the strongest practicals (URP shadowed additional lights are limited)
    for ol in sorted(out_lights, key=lambda o: -o["intensity"])[:3]:
        ol["shadows"] = True
    if sun:
        col, f = balanced(sun["k"], wb)
        out_lights.append({"id": "sun", "type": "directional", "pos": [0, 5, 0], "dir": sun["dir"], "color": col, "intensity": round(sun["lux"] * k_exp * f, 5),
                           "shadows": True, "role": "sun"})
        # bounce: where the sun patch lands, a warm-tinted soft light toward the ceiling
        if main_win:
            wx, wz = room.wall_point(main_win["wall"], main_win["u"])
            cy = main_win["sill"] + main_win["height"] / 2
            dx, dy, dz = sun["dir"]
            tt = cy / max(0.05, -dy)
            px, pz = wx + dx * tt, wz + dz * tt
            x0, z0, x1, z1 = room.floor
            px, pz = min(max(px, x0 + 0.2), x1 - 0.2), min(max(pz, z0 + 0.2), z1 - 0.2)
            patch_flux = flux_sun * rho
            col_b, fb = balanced(sun["k"] * 0.85, wb)
            out_lights.append({"id": "bounce", "type": "point", "pos": [px, 0.5, pz], "dir": [0, 1, 0], "color": col_b,
                               "intensity": round(patch_flux / (4 * math.pi) * k_exp * fb * 0.7, 5), "range": max(room.W, room.D) * 0.9, "shadows": False, "role": "bounce"})
    if street:
        col, f = balanced(street["k"], wb)
        dist = math.dist(street["pos"], (room.wall_point(main_win["wall"], main_win["u"])[0], main_win["sill"] + main_win["height"] / 2, room.wall_point(main_win["wall"], main_win["u"])[1]))
        cd = street["E_window"] * dist ** 2
        out_lights.append({"id": "street", "type": "spot", "pos": street["pos"], "dir": street["dir"], "color": col, "intensity": round(cd * k_exp * f, 5),
                           "range": street["range"], "angle": street["angle"], "inner": street["angle"] * 0.6, "shadows": True, "role": "street"})
    if moon:
        col, f = balanced(moon["k"], wb)
        out_lights.append({"id": "moon", "type": "directional", "pos": [0, 5, 0], "dir": moon["dir"], "color": col, "intensity": round(moon["lux"] * k_exp * f * 4, 5),
                           "shadows": moon["shadows"], "role": "moon"})
    # lightning
    lightning = None
    if wk == "storm":
        n = room.walls[main_win["wall"]]["n"] if main_win else (0, -1)
        col, f = balanced(9000, wb)
        lightning = {"dir": [n[0] * 0.6, -0.45, n[1] * 0.6], "color": col, "peak": round(4000 * k_exp * f, 4)}

    # ambient (indirect) colour: day part sky-coloured, practical part lamp-coloured
    sky_lin = [v for v in kelvin_rgb_linear(k_sky)]
    w_lin = kelvin_rgb_linear(wb)
    def adapt(rgb):
        a = [rgb[i] / w_lin[i] for i in range(3)]
        lm = _lum(a)
        return [v / lm for v in a]
    amb = [0.0, 0.0, 0.0]
    if E_ind_day > 0:
        a = adapt(sky_lin)
        amb = [amb[i] + a[i] * E_ind_day for i in range(3)]
    if E_ind_prac > 0 and practical_k:
        pk = math.exp(sum(w * math.log(k) for w, k in practical_k) / sum(w for w, _ in practical_k))
        a = adapt(kelvin_rgb_linear(pk))
        amb = [amb[i] + a[i] * E_ind_prac for i in range(3)]
    night_floor = 0.004 / k_exp if T["elev"] <= 0 else 0.0  # a hint of city glow so blacks aren't dead
    if night_floor:
        a = adapt(kelvin_rgb_linear(9000))
        amb = [amb[i] + a[i] * night_floor for i in range(3)]
    amb_lin = [v * k_exp for v in amb]
    amb_gain = 0.55 * float(ls.get("ambient", 1.0))
    sky_c = lin_color(amb_lin, 1.1 * amb_gain)
    eq_c = lin_color(amb_lin, 0.9 * amb_gain)
    gr_c = lin_color(amb_lin, 0.55 * amb_gain)

    # HDRI (view out of the window + reflections): chosen by time/weather/environment tags
    env_tags = [tk if tk != "afternoon" else "day", wk] + (["night"] if T["elev"] <= 0 else ["day"] if T["elev"] > 12 else []) + (["snow", "winter"] if wk == "snow" or "winter" in tags else []) + (["urban"] if "urban" not in tags else [])
    if tk in ("golden_hour",):
        env_tags += ["sunset", "golden"]
    if tk in ("dawn", "sunrise", "morning") and wk == "snow":
        env_tags += ["morning", "sunrise"]
    hid = L.pick_hdri(env_tags + list(ls.get("hdri_tags", [])), rng, prefer=ls.get("hdri"))
    hm = L.measured.get("hdri", {}).get(L.hdri_path(hid), {})
    hmean = hm.get("horizon") or hm.get("mean") or 1.0
    view_lum = (sky_lux / math.pi if T["elev"] > -5 else max(0.02, L.hdris[hid].get("lux", 2)) / math.pi) * k_exp
    hdri_exposure = max(0.002, min(60.0, view_lum / hmean * float(ls.get("window_brightness", 1.0))))
    if not windows:
        hdri_exposure = 0.0

    haze = float(ls.get("haze", 0.0))
    fog_density = 0.012 * haze if haze > 0 else 0.0
    fog_col = lin_color([v * 0.6 for v in amb_lin], 1.0)
    post = {"exposure": 0.0, "contrast": mood["contrast"], "saturation": mood["sat"], "temperature": 0, "tint": 0,
            "bloom": mood["bloom"] + (0.25 if T["elev"] <= 0 else 0), "bloomThreshold": 0.95, "vignette": mood["vig"], "grain": mood["grain"],
            "shadowsTint": mood.get("shadows", [1, 1, 1, 0]), "highlightsTint": mood.get("highlights", [1, 1, 1, 0]), "dof": float(ls.get("dof", 0.0))}
    job = {"lights": out_lights,
           "env": {"hdri": L.hdri_path(hid) if windows else "", "hdriExposure": round(hdri_exposure, 5), "hdriRotation": float(ls.get("hdri_rotation", rng.uniform(0, 360))),
                   "skyColor": [0.01, 0.01, 0.015], "ambientSky": sky_c, "ambientEquator": eq_c, "ambientGround": gr_c,
                   "reflection": 0.35 if T["elev"] <= 0 else 0.6, "fogDensity": round(fog_density, 4), "fogColor": fog_col},
           "post": post}
    meta = {"time": tk, "weather": wk, "mood": mood_k, "ev100": round(ev, 2), "white_balance_k": round(wb), "meter_lux": round(E_meter, 2),
            "sky_lux": round(sky_lux, 2), "sun_lux": round(sun_lux, 1), "practical_lumens": round(practical_flux), "indirect_lux_day": round(E_ind_day, 2),
            "indirect_lux_practicals": round(E_ind_prac, 2), "hdri": hid, "hdri_mean": hmean, "focus": [round(v, 3) for v in focus], "rho": rho,
            "lightning": lightning, "lights": [{"id": l["id"], "role": l["role"], "intensity": l["intensity"]} for l in out_lights]}
    return {"job": job, "meta": meta}


def _candela(l: dict) -> float:
    lm = l["lm"]
    if l["type"] == "spot":
        half = math.radians(l.get("angle", 100) / 2)
        return lm * 0.85 / (2 * math.pi * (1 - math.cos(half)))
    return lm / (4 * math.pi)


def _attach_world(p: dict, off) -> tuple[float, float, float]:
    rx, rz = _right(p["yaw"])
    fx, fz = _fwd(p["yaw"])
    by = p.get("y", 0.0) if p["place"] in ("surface",) else (p.get("y", 0.0) if p["place"] == "ceiling" else 0.0)
    return (p["x"] + rx * off[0] + fx * off[2], by + off[1], p["z"] + rz * off[0] + fz * off[2])


def _effects(spec: dict, S: Solver, room: Room, lighting: dict, rng) -> list[dict]:
    out = []
    ls = spec.get("lighting", {}) or {}
    lm = lighting["meta"]
    for e in spec.get("effects", []):
        e = {"type": e} if isinstance(e, str) else dict(e)
        typ = e["type"]
        if typ == "smoke":
            src = e.get("source", "ashtray")
            p = S.placed.get(src)
            if p:
                out.append({"type": "smoke", "target": src, "pos": [0.04, 0.02, 0], "color": [0.75, 0.75, 0.78], "amount": float(e.get("amount", 1.0))})
        elif typ == "steam":
            src = e.get("source")
            if src in S.placed:
                out.append({"type": "steam", "target": src, "pos": [0, 0.02, 0], "color": [0.9, 0.9, 0.9], "amount": 1.0})
    windows = [o for o in room.openings if o["type"] == "window"]
    for o in windows:
        w = room.walls[o["wall"]]
        wx, wz = room.wall_point(o["wall"], o["u"])
        n = w["n"]
        cy = o["sill"] + o["height"] / 2
        if lm["weather"] in ("rain", "storm"):
            out.append({"type": "rain_outside", "pos": [wx - n[0] * 2.2, cy - 2.5, wz - n[1] * 2.2], "size": [abs(w["t"][0]) * 6 + abs(n[0]) * 3, 5, abs(w["t"][1]) * 6 + abs(n[1]) * 3],
                        "dir": [-n[0] * 0.8, 0, -n[1] * 0.8], "color": [0.75, 0.8, 0.9], "amount": 1.4 if lm["weather"] == "storm" else 1.0})
        if lm["weather"] == "snow":
            out.append({"type": "snow_outside", "pos": [wx - n[0] * 2.5, cy - 2.5, wz - n[1] * 2.5], "size": [abs(w["t"][0]) * 7 + abs(n[0]) * 4, 5, abs(w["t"][1]) * 7 + abs(n[1]) * 4],
                        "dir": [0.2, 0, 0.1], "color": [1, 1, 1], "amount": 1.0})
    # shafts and dust where sun or street light pours through a window (haze makes them visible)
    haze = float(ls.get("haze", 0.25 if lm["sun_lux"] > 0 else 0.0))
    main = max(windows, key=lambda o: o["width"] * o["height"]) if windows else None
    lights = {l["id"]: l for l in lighting["job"]["lights"]}
    beam = lights.get("sun") or lights.get("street")
    if main and beam and haze > 0:
        w = room.walls[main["wall"]]
        wx, wz = room.wall_point(main["wall"], main["u"])
        cy = main["sill"] + main["height"] / 2
        d = beam["dir"]
        dn = math.sqrt(sum(v * v for v in d)) or 1
        d = [v / dn for v in d]
        col = beam["color"]
        out.append({"type": "shaft", "pos": [wx, cy, wz], "size": [main["width"] * 0.9, main["height"] * 0.9, 0], "dir": d, "axis": [w["t"][0], 0, w["t"][1]],
                    "color": col, "amount": haze * (1.6 if beam["id"] == "sun" else 1.0)})
        out.append({"type": "dust", "pos": [wx + d[0] * 1.3, cy + d[1] * 1.3, wz + d[2] * 1.3], "size": [1.6, 1.4, 1.6], "color": col, "amount": haze})
    if lm.get("lightning"):
        L_ = lm["lightning"]
        times = sorted(round(rng.uniform(0.6, 5.5), 2) for _ in range(2))
        out.append({"type": "lightning", "dir": L_["dir"], "color": L_["color"], "amount": L_["peak"], "times": times})
    return out


# =====================================================================================================================
# Cameras

def cameras_focus(spec: dict, S: Solver, room: Room) -> tuple[float, float, float]:
    f = (spec.get("camera") or {}).get("focus")
    p = S.placed.get(f) if f else None
    if not p:
        floor = [q for q in S.placed.values() if q["place"] == "floor" and not q.get("structural") and not q.get("flat")]
        p = max(floor, key=lambda q: q["w"] * q["d"]) if floor else None
    if not p:
        return (0.0, 1.0, 0.0)
    return (p["x"], min(1.1, (p.get("top") or p["h"]) + 0.1), p["z"])


def _cam_ok(S: Solver, x: float, z: float, y: float) -> bool:
    x0, z0, x1, z1 = S.room.floor
    if not (x0 + 0.2 < x < x1 - 0.2 and z0 + 0.2 < z < z1 - 0.2):
        return False
    for p in S.placed.values():
        if p["place"] == "floor" and not p.get("flat") and p["h"] > y - 0.4:
            if _point_in_quad((x, z), rect(p["x"], p["z"], p["w"] + 0.7, p["d"] + 0.7, p["yaw"])):
                return False
    return True


def cameras(spec: dict, S: Solver, room: Room) -> dict:
    cs = spec.get("camera") or {}
    fx, fy, fz = cameras_focus(spec, S, room)
    x0, z0, x1, z1 = room.floor
    eye = float(cs.get("height", 1.55))
    # establishing: from the far side of the room, in the corner region facing the focus
    best = None
    for k in range(80):
        a = k / 80 * 2 * math.pi
        for r_ in (0.95, 0.85, 0.7):
            cx = (x0 + x1) / 2 + math.cos(a) * (x1 - x0) / 2 * r_
            cz = (z0 + z1) / 2 + math.sin(a) * (z1 - z0) / 2 * r_
            cx = min(max(cx, x0 + 0.35), x1 - 0.35)
            cz = min(max(cz, z0 + 0.35), z1 - 0.35)
            if not _cam_ok(S, cx, cz, eye):
                continue
            d = math.hypot(cx - fx, cz - fz)
            blocked = _blocked(S, (cx, cz), (fx, fz), eye)
            score = d - (3 if blocked else 0)
            if cs.get("establish") == "along":   # long rooms: look down the length
                score += abs(cx - fx) * 0.8
            if best is None or score > best[0]:
                best = (score, cx, cz)
    if best is None:
        best = (0, (x0 + x1) / 2, z0 + 0.4)
    _, cx, cz = best
    fov_w = float(cs.get("fov", 52))
    stills = [{"name": "wide", "pos": [cx, eye, cz], "look": [fx, fy * 0.85, fz], "fov": fov_w, "t": 1.0}]
    # detail: close on the focus, from the camera side
    dx, dz = cx - fx, cz - fz
    dn = math.hypot(dx, dz) or 1
    dpos = [fx + dx / dn * 1.25, fy + 0.5, fz + dz / dn * 1.25]
    stills.append({"name": "detail", "pos": dpos, "look": [fx, fy - 0.05, fz], "fov": 40, "t": 2.0})
    # reverse: from beside the focus back toward the room / door
    rpos = None
    for ang in (60, -60, 90, -90, 120, -120):
        r = math.radians(ang)
        ux, uz = -dx / dn, -dz / dn
        vx, vz = ux * math.cos(r) - uz * math.sin(r), ux * math.sin(r) + uz * math.cos(r)
        px, pz = fx - vx * 1.4, fz - vz * 1.4
        px = min(max(px, x0 + 0.35), x1 - 0.35)
        pz = min(max(pz, z0 + 0.35), z1 - 0.35)
        if _cam_ok(S, px, pz, 1.45):
            rpos = [px, 1.45, pz]
            break
    if rpos:
        stills.append({"name": "reverse", "pos": rpos, "look": [cx, 1.2, cz], "fov": 55, "t": 3.0})
    # move
    mv = cs.get("move", "dolly")
    if mv == "push_in":
        p1 = [cx + (fx - cx) * 0.38, eye - 0.1, cz + (fz - cz) * 0.38]
        move = {"name": "move", "pos0": [cx, eye, cz], "look0": [fx, fy * 0.85, fz], "pos1": p1, "look1": [fx, fy * 0.9, fz], "fov0": fov_w, "fov1": fov_w - 8}
    else:
        side = (-dz / dn, dx / dn)
        s = min(1.0, max(0.4, min(x1 - x0, z1 - z0) * 0.18))
        while s > 0.1:
            p0 = [cx - side[0] * s, eye, cz - side[1] * s]
            p1 = [cx + side[0] * s, eye, cz + side[1] * s]
            for p in (p0, p1):
                p[0] = min(max(p[0], x0 + 0.3), x1 - 0.3)
                p[2] = min(max(p[2], z0 + 0.3), z1 - 0.3)
            if _cam_ok(S, p0[0], p0[2], eye) and _cam_ok(S, p1[0], p1[2], eye):
                break
            s *= 0.7
        move = {"name": "move", "pos0": p0, "look0": [fx - side[0] * 0.3, fy * 0.85, fz - side[1] * 0.3], "pos1": p1, "look1": [fx + side[0] * 0.3, fy * 0.85, fz + side[1] * 0.3], "fov0": fov_w, "fov1": fov_w}
    move["seconds"] = float(cs.get("seconds", 6))
    move["fps"] = int(cs.get("fps", 30))
    for c in stills + [move]:
        for k in ("pos", "look", "pos0", "look0", "pos1", "look1"):
            if k in c:
                c[k] = [round(v, 4) for v in c[k]]
    return {"stills": stills, "move": move, "focus": [fx, fy, fz]}


def _blocked(S: Solver, a, b, eye: float) -> bool:
    for p in S.placed.values():
        if p["place"] != "floor" or p.get("flat") or p["h"] < eye - 0.2:
            continue
        q = rect(p["x"], p["z"], p["w"], p["d"], p["yaw"])
        # segment vs quad: sample points
        for k in range(1, 20):
            t = k / 20
            if _point_in_quad((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), q):
                return True
    return False


# =====================================================================================================================
# Unity server (WorldLab), heavy lock

_lock = threading.Lock()
_proc: subprocess.Popen | None = None


def unity_exe() -> str:
    env = os.environ.get("WORLD_UNITY_EXE") or os.environ.get("SHOT_UNITY_EXE")
    if env:
        return env
    pv = (LAB / "ProjectSettings" / "ProjectVersion.txt").read_text().splitlines()
    want = next(l.split(":", 1)[1].strip() for l in pv if l.startswith("m_EditorVersion:"))
    for r in (Path(r"D:\Unity\Editors"), Path(r"C:\Program Files\Unity\Hub\Editor")):
        exe = r / want / "Editor" / "Unity.exe"
        if exe.exists():
            return str(exe)
    raise RuntimeError(f"Unity {want} not found; set WORLD_UNITY_EXE")


def _heartbeat() -> dict | None:
    hb = QUEUE / "heartbeat.json"
    try:
        d = json.loads(hb.read_text())
    except Exception:
        return None
    if time.time() - hb.stat().st_mtime > 8 or d.get("state") == "stopped":
        return None
    return d


def ensure_server(timeout: float = 1800, log=_log) -> dict:
    global _proc
    hb = _heartbeat()
    if hb:
        return hb
    QUEUE.mkdir(parents=True, exist_ok=True)
    for f in ("heartbeat.json", "stop.flag"):
        (QUEUE / f).unlink(missing_ok=True)
    env = os.environ.copy()
    env["TEMP"] = env["TMP"] = r"D:\tmp" if Path(r"D:\tmp").is_dir() else env.get("TEMP", "")
    logf = ROOT / "logs" / "world_server.log"
    logf.parent.mkdir(exist_ok=True)
    cmd = [unity_exe(), "-batchmode", "-projectPath", str(LAB), "-executeMethod", "WorldLab.WorldServer.Run", "-queue", str(QUEUE),
           "-idle", os.environ.get("WORLD_SERVER_IDLE_S", "600"), "-logFile", str(logf)]
    _proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log(f"starting WorldLab Unity server (pid {_proc.pid}); log {logf}")
    t0 = time.time()
    while time.time() - t0 < timeout:
        hb = _heartbeat()
        if hb:
            return hb
        if _proc.poll() is not None:
            txt = logf.read_text(encoding="utf-8", errors="replace") if logf.exists() else ""
            errs = [l for l in txt.splitlines() if "error CS" in l or "WORLD_ERROR" in l or "another Unity" in l][:10]
            raise RuntimeError(f"WorldLab server exited ({_proc.returncode}); see {logf}\n" + "\n".join(errs))
        time.sleep(0.5)
    raise RuntimeError("WorldLab server didn't start")


def stop_server(wait: float = 60) -> None:
    QUEUE.mkdir(parents=True, exist_ok=True)
    (QUEUE / "stop.flag").write_text("stop")
    t0 = time.time()
    while time.time() - t0 < wait:
        if _heartbeat() is None and (_proc is None or _proc.poll() is not None):
            return
        time.sleep(0.5)


@contextlib.contextmanager
def session(who: str = "world: render"):
    """Holds the machine-wide heavy lock while a WorldLab editor runs, and closes Unity afterwards."""
    from heavy_lock import heavy
    with heavy(who):
        try:
            ensure_server()
            yield
        finally:
            stop_server()


def _submit(job: dict, jid: str, timeout: float, log=_log) -> None:
    ensure_server(log=log)
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
                raise RuntimeError("WorldLab job failed: " + res.get("error", "?")[:3000])
            return
        if _heartbeat() is None and not (QUEUE / f"{jid}.job.json").exists() and not (QUEUE / f"{jid}.running").exists():
            raise RuntimeError("WorldLab server died; see logs/world_server.log")
        time.sleep(0.25)
    raise RuntimeError(f"WorldLab job timed out after {timeout:.0f}s")


def _need_session():
    """A session context unless a server is already up (then the caller manages it)."""
    return contextlib.nullcontext() if _heartbeat() else session()


# =====================================================================================================================
# Measure

def measure(lineup: bool = True, log=_log) -> dict:
    """Unity measures every library model (real size after its scale rule) and every HDRI's mean radiance."""
    L = lib()
    items = []
    for m in L.man["models"]:
        if m["src"] == "procedural":
            continue
        e = {"id": m["id"], "asset": m["id"], "path": L.model_path(m), "src": m["src"], "front": L.front(m), "scale": float(m.get("scale", 1)), "yaw": 0}
        if m["src"] == "quaternius":
            e["fitHeight"] = m["size"][1]
        items.append(e)
    out = CACHE / "measure"
    job = {"kind": "measure", "id": "measure", "outDir": str(out).replace("\\", "/"), "items": items, "lineup": lineup,
           "hdris": [L.hdri_path(h) for h in L.hdris]}
    with _need_session():
        _submit(job, "measure_" + str(int(time.time())), timeout=1800, log=log)
    sizes = json.loads((out / "sizes.json").read_text())
    hd = json.loads((out / "hdri.json").read_text()) if (out / "hdri.json").exists() else {}
    data = {"models": sizes, "hdri": hd, "measured_at": time.strftime("%Y-%m-%d %H:%M")}
    SIZES.parent.mkdir(parents=True, exist_ok=True)
    SIZES.write_text(json.dumps(data, indent=1))
    lib(reload=True)
    return data


# =====================================================================================================================
# Build / light / render

def _world_id(job: dict) -> str:
    h = hashlib.sha1(json.dumps(job, sort_keys=True).encode()).hexdigest()[:10]
    return f"{job['id']}_{h}"


def build_world(spec, *, name: str | None = None, render: bool = True, move: bool = True, log=_log) -> dict:
    """Spec (dict) or a one-line description (str) -> resolved world, rendered stills + camera move, validation."""
    if isinstance(spec, str):
        spec = expand(spec)
    spec = copy.deepcopy(spec)
    if name:
        spec["name"] = name
    t0 = time.time()
    res = resolve(spec, log=log)
    job, meta = res["job"], res["meta"]
    if not move:
        job["move"] = {"seconds": 0}
    wid = _world_id(job)
    WORLDS.mkdir(parents=True, exist_ok=True)
    (WORLDS / f"{wid}.json").write_text(json.dumps(res, indent=1))
    out = {"world_id": wid, "world_json": str(WORLDS / f"{wid}.json"), "solve_s": meta["solve_s"], "lighting": meta["lighting"],
           "unplaced": meta["unplaced"], "notes": meta["notes"], "walkway": meta["walkway"]}
    if render:
        out.update(render_world(wid, log=log))
    out["seconds_total"] = round(time.time() - t0, 2)
    return out


def load(world_id: str) -> dict:
    return json.loads((WORLDS / f"{world_id}.json").read_text())


def light_world(world_id: str, lighting, *, name: str | None = None, render: bool = True, log=_log) -> dict:
    """Same room and layout, new light. `lighting` is a dict ({time, weather, mood, ...}) or text ("storm at night")."""
    w = load(world_id)
    spec = copy.deepcopy(w["meta"]["spec"])
    if isinstance(lighting, str):
        e = expand(lighting + " " + spec.get("description", ""))["lighting"]
        txt = lighting.lower()
        new = {"time": e["time"] if any(k in txt for k in ("night", "morning", "dawn", "dusk", "noon", "day", "afternoon", "evening", "sunset", "golden")) else spec.get("lighting", {}).get("time"),
               "weather": e["weather"] if any(k in txt for k in ("storm", "rain", "snow", "fog", "overcast", "sunny", "clear", "thunder")) else "clear",
               "mood": e["mood"] if e["mood"] != "neutral" else spec.get("lighting", {}).get("mood", "neutral")}
        if "sunny" in txt or "clear" in txt or ("day" in txt and new["weather"] == "clear"):
            new["weather"] = "clear"
        lighting = {**spec.get("lighting", {}), **{k: v for k, v in new.items() if v}}
    spec["lighting"] = {**spec.get("lighting", {}), **lighting}
    wk = spec["lighting"].get("weather", "clear")
    for o in spec.get("openings", []):
        if o["type"] == "window":
            o["rainy"] = wk in ("rain", "storm")
    spec["name"] = name or (spec.get("name", "world") + "_" + "_".join(str(spec["lighting"].get(k, "")) for k in ("time", "weather")))
    # keep the solved layout: re-resolve with the same seed (deterministic), then reuse the placed items
    res = resolve(spec, log=log)
    old_items = {i["id"]: i for i in w["job"]["items"]}
    if set(old_items) == {i["id"] for i in res["job"]["items"]}:
        res["job"]["items"] = list(old_items.values())
    wid = _world_id(res["job"])
    (WORLDS / f"{wid}.json").write_text(json.dumps(res, indent=1))
    out = {"world_id": wid, "relit_from": world_id, "lighting": res["meta"]["lighting"]}
    if render:
        out.update(render_world(wid, log=log))
    return out


def render_world(world_id: str, *, log=_log) -> dict:
    w = load(world_id)
    job = copy.deepcopy(w["job"])
    out = BUILD / world_id
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    job["outDir"] = str(out).replace("\\", "/")
    t1 = time.time()
    with _need_session():
        _submit(job, world_id, timeout=1800, log=log)
    t_unity = time.time() - t1
    report = json.loads((out / "report.json").read_text())
    res = {"build_dir": str(out), "stills": [str(out / f"{s['name']}.png") for s in job["stills"]], "report": str(out / "report.json"),
           "timing_s": {"unity": round(t_unity, 2), "unity_breakdown": report.get("timing")}}
    if report.get("frames"):
        mp4 = out / f"{world_id}.mp4"
        t2 = time.time()
        subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(report.get("fps", 30)), "-i", str(out / "f%05d.jpg"),
                        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
        res["mp4"] = str(mp4)
        res["timing_s"]["encode"] = round(time.time() - t2, 2)
        frames = sorted(out.glob("f*.jpg"))
        keep = {frames[0], frames[len(frames) // 2], frames[-1]} if frames else set()
        for f in frames:
            if f not in keep:
                f.unlink()
    res["validation"] = validate(w, report, out)
    res["sheet"] = str(_sheet(out, res["stills"], world_id))
    (out / "result.json").write_text(json.dumps(res, indent=1))
    return res


def _ffmpeg() -> str:
    for c in (os.environ.get("FFMPEG"), r"D:\tools\ffmpeg\bin\ffmpeg.exe", shutil.which("ffmpeg")):
        if c and Path(c).exists():
            return str(c)
    raise RuntimeError("ffmpeg not found (set FFMPEG)")


def _sheet(out: Path, stills: list[str], title: str) -> Path:
    try:
        from PIL import Image
    except ImportError:
        return Path(stills[0]) if stills else out
    ims = [Image.open(s).convert("RGB") for s in stills if Path(s).exists()]
    if not ims:
        return out
    w = 640
    ims = [im.resize((w, int(im.height * w / im.width))) for im in ims]
    sheet = Image.new("RGB", (w * len(ims), ims[0].height), (10, 10, 12))
    for i, im in enumerate(ims):
        sheet.paste(im, (i * w, 0))
    p = out / "sheet.jpg"
    sheet.save(p, quality=88)
    return p


# =====================================================================================================================
# Validation

def validate(world: dict, report: dict, out: Path) -> dict:
    """Checks on what actually rendered: overlaps of real mesh bounds, things floating or sunk, surface drops that
    missed, items outside the room, cameras inside furniture, walkway, image exposure (no black/blown frames)."""
    meta, job = world["meta"], world["job"]
    items = {i["id"]: i for i in report.get("items", []) if "min" in i}
    placed = meta["placed"]
    issues, warnings = [], []
    # failed spawns
    for i in report.get("items", []):
        if i.get("status", "ok") not in ("ok",):
            (issues if i["status"].startswith("error") else warnings).append(f"{i['id']}: {i['status']}")
    room = report.get("room", {})
    rmin, rmax = room.get("min", [-99, -99, -99]), room.get("max", [99, 99, 99])
    floor_ids = [k for k, v in items.items() if placed.get(k, {}).get("place") == "floor" and not placed.get(k, {}).get("cat") == "rug"]
    # floor items: footprint overlap of real bounds (AABB, shrunk 3 cm: bounds of rotated meshes are generous)
    def aabb(i, shrink=0.03):
        return (i["min"][0] + shrink, i["min"][2] + shrink, i["max"][0] - shrink, i["max"][2] - shrink)
    pairs = []
    for a_i in range(len(floor_ids)):
        for b_i in range(a_i + 1, len(floor_ids)):
            A, B = items[floor_ids[a_i]], items[floor_ids[b_i]]
            a, b = aabb(A), aabb(B)
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oz = min(a[3], b[3]) - max(a[1], b[1])
            if ox > 0.04 and oz > 0.04:
                pa, pb = placed[floor_ids[a_i]], placed[floor_ids[b_i]]
                related = pa.get("cat") in SEATS and pb.get("cat") in ("desk", "table", "coffee_table") or pb.get("cat") in SEATS and pa.get("cat") in ("desk", "table", "coffee_table")
                (warnings if related else issues).append(f"overlap {floor_ids[a_i]} x {floor_ids[b_i]} ({ox:.2f} x {oz:.2f} m)")
                pairs.append((floor_ids[a_i], floor_ids[b_i]))
    for k, i in items.items():
        p = placed.get(k, {})
        if i["min"][0] < rmin[0] - 0.05 or i["max"][0] > rmax[0] + 0.05 or i["min"][2] < rmin[2] - 0.05 or i["max"][2] > rmax[2] + 0.05:
            issues.append(f"{k} pokes out of the room")
        if p.get("place") == "floor" and abs(i["min"][1]) > 0.03 and p.get("cat") != "rug":
            issues.append(f"{k} not on the floor (min y {i['min'][1]:.2f})")
        if i["max"][1] > rmax[1] + 0.02:
            issues.append(f"{k} goes through the ceiling")
        if p.get("place") == "surface" and i.get("dropY") is None:
            issues.append(f"{k}: surface drop missed its parent")
    # cameras
    for c in report.get("cameras", []):
        if not c.get("insideRoom"):
            warnings.append(f"camera {c['name']} outside the room (cutaway)")
        if c.get("insideItem"):
            issues.append(f"camera {c['name']} inside {c['insideItem']}")
    if not meta["walkway"]["ok"]:
        warnings.append(f"walkway: unreachable {meta['walkway']['unreachable']}")
    if meta["unplaced"]:
        warnings.append(f"unplaced: {[u['id'] for u in meta['unplaced']]}")
    # image statistics
    img = {}
    try:
        from PIL import Image
        import numpy as np
        for s in job["stills"]:
            p = out / f"{s['name']}.png"
            if not p.exists():
                issues.append(f"missing still {s['name']}")
                continue
            a = np.asarray(Image.open(p).convert("L"), dtype=np.float32) / 255.0
            st = {"mean": round(float(a.mean()), 3), "p05": round(float(np.percentile(a, 5)), 3), "p95": round(float(np.percentile(a, 95)), 3),
                  "clipped": round(float((a > 0.985).mean()), 4), "black": round(float((a < 0.02).mean()), 4)}
            img[s["name"]] = st
            if st["mean"] < 0.06:
                issues.append(f"still {s['name']} too dark (mean {st['mean']})")
            elif st["mean"] < 0.1:
                warnings.append(f"still {s['name']} dark (mean {st['mean']})")
            if st["clipped"] > 0.12:
                warnings.append(f"still {s['name']} has {st['clipped'] * 100:.0f}% blown highlights")
            if st["mean"] > 0.75:
                issues.append(f"still {s['name']} washed out (mean {st['mean']})")
    except ImportError:
        warnings.append("PIL/numpy missing: no image checks")
    return {"ok": not issues, "issues": issues, "warnings": warnings, "image": img, "items_rendered": len(items),
            "items_planned": len(job["items"])}


# =====================================================================================================================
# Characters in the world (render_shot composition)

def describe(world_id: str) -> dict:
    """What a director needs to stage actors: room bounds, door, walkway, and every placed item with its position,
    facing and (for seats) the hips target for generate_motion's `seat` option and render_shot's furniture."""
    w = load(world_id)
    meta = w["meta"]
    out = {"world_id": world_id, "room": {"w": w["job"]["room"]["w"], "d": w["job"]["room"]["d"], "h": w["job"]["room"]["h"], "floor": meta["floor"]},
           "openings": [{k: o[k] for k in ("type", "wall", "u", "width", "height") if k in o} | {"center": None} for o in meta["openings"]], "items": []}
    room = Room(w["job"]["room"]["w"], w["job"]["room"]["d"], w["job"]["room"]["h"])
    for o, oo in zip(meta["openings"], out["openings"]):
        oo["center"] = [round(v, 3) for v in room.wall_point(o["wall"], o["u"])]
        oo["inside"] = [round(v, 3) for v in room.wall_point(o["wall"], o["u"], 0.6)]
    for k, p in meta["placed"].items():
        if p.get("cat") == "column":
            continue
        e = {"id": k, "cat": p.get("cat"), "asset": p.get("asset"), "pos": [p.get("x"), p.get("z")], "yaw": p.get("yaw"), "size": [p.get("w"), p.get("h"), p.get("d")]}
        if p.get("cat") in SEATS and p.get("seat"):
            st = seat_target(world_id, k, w)
            e["seat"] = {"hips": st["hips"], "face_yaw": st["face_yaw"], "height": st["height"]}
        out["items"].append(e)
    return out


def seat_target(world_id: str, item_id: str, w: dict | None = None) -> dict:
    """Where a character sits on a placed seat: hips position (x, z), the yaw they face, the seat height, and a
    render_shot furniture entry that puts that very model there (the world drops its own copy for the shot)."""
    w = w or load(world_id)
    p = w["meta"]["placed"][item_id]
    m = lib().models[p["asset"]]
    fx, fz = _fwd(p["yaw"])
    back = 0.06
    hips = [round(p["x"] - fx * back, 3), round(p["z"] - fz * back, 3)]
    furniture = {"id": item_id, "type": "chair", "model": p["path"], "kit": "", "at": [p["x"], p["z"]], "yaw": (p["yaw"] + p.get("front", 0)) % 360,
                 "seat_height": float(m.get("seat", 0.45))}
    return {"hips": hips, "face_yaw": round(p["yaw"] % 360, 2), "height": float(m.get("seat", 0.45)), "furniture": furniture}


def render_world_shot(world_id: str, shot: dict, *, force: bool = False, log=_log) -> dict:
    """render_shot in a generated world: `shot` is a render_shot spec (actors, camera, seconds, aspect...) without a
    stage/lighting (the world provides both). `sit: [{"on": <world item id>, "t": [t0, t1]}]` on an actor seats it on a
    world chair: that chair becomes shot furniture (measured seat) and leaves the world copy for this shot."""
    import shots
    w = load(world_id)
    shot = copy.deepcopy(shot)
    seat_ids = {st["on"] for a in shot.get("actors", []) for st in (a.get("sit") or [])}
    furn = list(shot.get("furniture") or [])
    for sid in seat_ids:
        if sid in w["meta"]["placed"]:
            f = seat_target(world_id, sid, w)["furniture"]
            furn.append({"id": sid, "model": f["model"], "kit": "", "at": f["at"], "yaw": f["yaw"], "seat_height": f["seat_height"], "type": "chair"})
    if furn:
        shot["furniture"] = furn
    shot.pop("open_doors", None)
    shot.pop("door_angle", None)
    shot["stage"] = "studio"
    shot.setdefault("lighting", "studio")
    # resolve with shots' logic, staging clips into WorldLab instead of DemoStudio
    with shots._lock:
        saved = (shots.STUDIO, shots.GENERATED)
        shots.STUDIO, shots.GENERATED = LAB, GENERATED
        try:
            job = shots.resolve(json.loads(json.dumps(shot)))
        finally:
            shots.STUDIO, shots.GENERATED = saved
    meta_actors = [{"id": a["id"], "motions": a.pop("_motions")} for a in job["actors"]]
    job.pop("_aspect", None)
    job.pop("_quality", None)
    job.pop("_furniture_auto", None)
    for a in job["actors"]:
        for q in a.get("props", []):
            q.pop("_why", None)
    # the world variant for this shot: drop the seats that became shot furniture
    wj = copy.deepcopy(w["job"])
    wj["items"] = [i for i in wj["items"] if i["id"] not in seat_ids]
    wj["stills"], wj["move"] = [], {"seconds": 0}
    if shot.get("open_doors", True):  # actors walk in: doors stand open
        for wall in wj["walls"]:
            for o in wall["openings"]:
                if o["type"] == "door":
                    o["doorOpen"] = float(shot.get("door_angle", 95))
    name = re.sub(r"[^A-Za-z0-9_-]", "_", shot.get("name") or "shot")[:40]
    key = hashlib.sha1((json.dumps(job, sort_keys=True) + json.dumps(wj, sort_keys=True)).encode()).hexdigest()[:10]
    out = BUILD / f"{world_id}__{name}_{key}"
    mp4 = out / f"{name}.mp4"
    if mp4.exists() and not force:
        return json.loads((out / "result.json").read_text())
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    frames = out / "frames"
    frames.mkdir(parents=True)
    wpath = out / "world.json"
    wpath.write_text(json.dumps(wj))
    job["stage"] = "world:" + str(wpath).replace("\\", "/")
    job["id"] = f"{name}_{key}"
    job["outDir"] = str(frames).replace("\\", "/")
    (out / "shot.json").write_text(json.dumps(job, indent=1))
    t1 = time.time()
    with _need_session():
        _submit(job, job["id"], timeout=600 + job["seconds"] * job["fps"] * 4, log=log)
    t_unity = time.time() - t1
    report = json.loads((frames / "report.json").read_text())
    ext = "jpg" if job["format"] == "jpg" else "png"
    subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(job["fps"]), "-i", str(frames / f"f%05d.{ext}"),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)], check=True)
    aspect = next((k for k, v in shots.ASPECTS.items() if v == (job["width"], job["height"])), "16:9")
    sheet = shots.contact_sheet(frames, report, out / "contact.png", ext, aspect)
    val = shots.validate(mp4, report, job)
    shutil.copyfile(frames / "report.json", out / "report.json")
    keep = {f"f{int(f['f']):05d}.{ext}" for f in shots._pick(report, 4)}
    for f in frames.glob(f"f*.{ext}"):
        if f.name not in keep:
            f.unlink()
    res = {"mp4": str(mp4), "contact_sheet": str(sheet), "validation": val, "world_id": world_id, "seconds": job["seconds"],
           "actors": meta_actors, "furniture": report.get("furniture"), "timing_s": {"unity": round(t_unity, 2), "unity_breakdown": report.get("timing")}}
    (out / "result.json").write_text(json.dumps(res, indent=1))
    return res
