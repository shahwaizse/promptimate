"""Promptimate for Roblox story shorts ("In This Town" style): MCP tools that turn a compact per-character shot list
into connected, staged performances inside the open Roblox Studio place, and record them as vertical video.

    roblox_install   put PromptimatePlayer + ShortDirector + autoplay scripts into the place (also done by perform)
    roblox_perform   beats per character -> continue_from chain (root paths from targets in place coordinates, seats,
                     end facing) -> clips pushed straight into Studio -> staging checks -> short summary + plan image
    roblox_record    camera cues -> camera checks + shot sheet, then a stitched 9:16 frame-by-frame render (MP4)

No clip data ever goes back to the client: the tool talks to Studio itself (roblox_studio.py, through Studio's own
MCP server) and returns a few hundred tokens. Registered in server.py with register(mcp, server_module).

Units: Studio studs and world axes. Clips are scaled per character by its measured standing hips height
(PromptimatePlayer), so metres = studs / (stand / 0.95).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
import threading
import time
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

import constraints as C
import motion
import roblox
from roblox_studio import chunk_module, long_str, studio

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "roblox" / "package"
STATE = ROOT / ".cache" / "roblox_perform"
SOMA_HIP = roblox.SOMA_HIP_HEIGHT
CLIPS_PATH = 'game:GetService("ReplicatedStorage").Promptimate.Clips'
FACE_FRAMES = 8          # end facing: heading pinned on the last frames
FACE_TOL = 30.0          # deg
PATH_TOL = 0.5           # m, end of a `to` path
MAX_ATTEMPTS = 3
REPAIR_ROUNDS = int(os.environ.get("PROMPTIMATE_REPAIR_ROUNDS", "2"))   # perform: regenerate beats that clip
SELF_BAD = 0.35        # fraction of a forearm/hand hidden inside its own body that reads as clipping
PAIR_BAD = 0.3         # studs: two characters' parts overlapping this deep
R15_SEAT_LIFT = 0.12     # m
SRV = None               # server module (generate_motion, worker, ...), set by register()
_GEN_LOCK = threading.Lock()
_TLS = threading.local()


class _TLWorker:
    """The server's generation worker, with a per-thread override (a heading constraint for one beat). Beats of
    different characters generate concurrently, so the old swap of the global worker under a lock is gone."""

    def __init__(self, real):
        self.real = real

    def __getattr__(self, k):
        o = getattr(_TLS, "override", None)
        return getattr(o if o is not None else self.real, k)


def _tls_install():
    """Install the thread-aware worker once; return the real one underneath."""
    w = SRV.worker
    if not isinstance(w, _TLWorker):
        w = SRV.worker = _TLWorker(w)
    return w.real

DIRS = {"+x": (1.0, 0.0), "-x": (-1.0, 0.0), "+z": (0.0, 1.0), "-z": (0.0, -1.0)}
_STILL = re.compile(r"\b(stands?|standing|still|idles?|idling|waits?|waiting|cross(es)? their arms|arms crossed|talks?|"
                    r"talking|gestures?|looks around|shifts their weight|taps|claps?|waves?|points?|nods?|shrugs?|"
                    r"thinks?|breathes?|hides|hiding|crouch(es|ing)?|kneels?|kneeling|ducks?|cowers?|lies|lying)\b", re.I)
_LOCO = re.compile(r"\b(walks?|walking|jogs?|jogging|runs?|running|steps?|moves?|crawls?|skips?|sprints?|marches?|"
                   r"strolls?|hurries|forward|backward|sideways|approach\w*|goes|comes)\b", re.I)


# =============================================================================================== tool input models
class Beat(BaseModel):
    prompt: str | list[str] = Field(description="What the body does: 'a person ...', present tense, body parts and "
                                                "manner, no story/objects. A list = segments played in order")
    seconds: float | list[float] = Field(3.0, description="Duration (s); a list matches a prompt list (0.5-10 each)")
    at: float | None = Field(None, description="Story time (s) the beat starts. Default: right after the previous beat "
                                               "(gaps are filled with idling)")
    to: str | list[float] | None = Field(None, description="Where the character ends up: [x, z] studs, or the name of a "
                                                           "part/model/character, optionally with a side ('Crates:+X'). "
                                                           "Stops short of objects and people")
    via: list[list[float]] | None = Field(None, description="[x, z] waypoints (studs) on the way to `to`")
    arrive: float | None = Field(None, description="Seconds into the beat when `to` is reached (default: where the "
                                                   "walking/running part of the prompt ends)")
    face: str | list[float] | None = Field(None, description="Facing at the end: a character/object name, an [x, z] "
                                                             "point or '+X' '-X' '+Z' '-Z'")
    sit: str | float | None = Field(None, description="Sit on this object (its top is the seat) or at this seat height "
                                                      "in studs, seated from sit_from to the end. Repeat it on the next "
                                                      "beats to stay seated; drop it to stand up")
    sit_from: float | None = Field(None, description="Seconds into the beat when seated (default ~1.5 s in)")
    peek: str | None = Field(None, description="'left' or 'right': lean/step out sideways from cover, look, and back")


class Actor(BaseModel):
    name: str = Field(description="Character Model name in the place (any R15 rig with a Humanoid)")
    start: list[float] | None = Field(None, description="[x, z] studs where the first beat starts (default: where the "
                                                        "rig stands / its previous start)")
    facing: str | list[float] | None = Field(None, description="Facing at the start: name, [x, z] or '+X'.. (default: "
                                                               "the rig's facing)")
    beats: list[Beat]
    append: bool = Field(False, description="Continue this character's existing chain instead of replacing it")


# ================================================================================================= small helpers
def wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


def basis(yaw: float):
    f = np.array([-math.sin(yaw), -math.cos(yaw)])     # Roblox look vector (x, z) of CFrame.Angles(0, yaw, 0)
    left = np.array([f[1], -f[0]])
    return f, left


def yaw_of(d) -> float:
    return math.atan2(-float(d[0]), -float(d[1]))


def to_local(p, yaw, spm, w) -> tuple[float, float]:
    """World point (studs) -> clip frame (metres; x = the character's left, z = forward) for a clip placed at p, yaw."""
    f, left = basis(yaw)
    v = np.asarray(w, float) - np.asarray(p, float)
    return float(v @ left) / spm, float(v @ f) / spm


def to_gen(pt, g) -> tuple[float, float]:
    """Final-clip frame -> generation frame (continue_from clips are generated in the frame of the lead-in)."""
    x, z = pt
    xp, zp, hp = g
    return xp + math.cos(hp) * x + math.sin(hp) * z, zp - math.sin(hp) * x + math.cos(hp) * z


def place_next(root, rot, p, yaw, spm):
    f, left = basis(yaw)
    d = root[-1] - root[0]
    h = C.frame_placement(root, rot, len(root) - 1)[2]
    return np.asarray(p, float) + (left * d[0] + f * d[2]) * spm, wrap(yaw + h)


def world_hips(root, p, yaw, spm):
    f, left = basis(yaw)
    d = root - root[:1]
    return np.asarray(p, float)[None] + (np.outer(d[:, 0], left) + np.outer(d[:, 2], f)) * spm


def _short(text: str, n: int = 28) -> str:
    t = re.sub(r"^a person\s+", "", text.strip(), flags=re.I)
    return t if len(t) <= n else t[:n - 1] + "…"


def _segments(b: Beat) -> list[tuple[str, float]]:
    ps = b.prompt if isinstance(b.prompt, list) else [b.prompt]
    ss = b.seconds if isinstance(b.seconds, list) else ([b.seconds] if len(ps) == 1 else [b.seconds / len(ps)] * len(ps))
    if len(ss) != len(ps):
        raise ValueError(f"beat '{ps[0][:40]}': {len(ps)} prompts but {len(ss)} durations")
    out = []
    for p, s in zip(ps, ss):
        s = float(s)
        while s > 10.0:              # the engine's per-segment limit: split long continuous activity
            out.append((p, 8.0))
            s -= 8.0
        out.append((p, max(0.5, s)))
    return out


def _load_cons(path, frames: int) -> C.Constraints:
    raw = Path(path).read_bytes()
    n, d = struct.unpack("<ii", raw[:8])
    c = C.Constraints(n)
    a = np.frombuffer(raw[8:], dtype="<f4")
    c.observed[:] = a[:n * d].reshape(n, d)
    c.mask[:] = a[n * d:2 * n * d].reshape(n, d)
    return c


class _HeadingProxy:
    """Wraps the generation worker: adds a heading constraint (constraints.heading) on the last frames of every
    engine pass of one generate_motion call (end facing control)."""

    def __init__(self, real, heading: float, frames: int = FACE_FRAMES):
        self.real, self.heading, self.k = real, heading, frames

    def generate(self, segments, out_dir, *a, constraints=None, **kw):
        n = sum(s.frames for s in segments)
        cons = _load_cons(constraints, n) if constraints else C.Constraints(n)
        for t in range(max(0, n - self.k), n):
            cons.heading(t, self.heading)
        path = cons.save(Path(out_dir) / ("constraints_face2.bin" if constraints and "pass2" in str(constraints)
                                          else "constraints_face.bin"))
        return self.real.generate(segments, out_dir, *a, constraints=path, **kw)

    def __getattr__(self, k):
        return getattr(self.real, k)


def _gen_frame(prev: str | None) -> tuple[float, float, float]:
    """Placement of the final clip's frame 0 inside the generation frame of a continue_from clip."""
    if not prev:
        return 0.0, 0.0, 0.0
    feat = SRV._continue_context(prev, SRV.CONTINUE_OVERLAP)
    last = feat[-1]
    return float(last[0]), float(last[2]), math.atan2(float(last[4]), float(last[3]))


# ================================================================================================ Studio: package
def _pkg_sources() -> dict[str, str]:
    return {"PromptimatePlayer": (ROOT / "roblox" / "PromptimatePlayer.lua").read_text(encoding="utf-8"),
            "ShortDirector": (PKG / "ShortDirector.lua").read_text(encoding="utf-8"),
            "Faces": (PKG / "Faces.lua").read_text(encoding="utf-8")}


def _pkg_version() -> str:
    h = hashlib.sha1()
    for k, v in sorted(_pkg_sources().items()):
        h.update(k.encode() + v.encode())
    for f in ("PromptimateAutoplay.client.lua", "PromptimateAutoplay.server.lua"):
        h.update((PKG / f).read_bytes())
    return h.hexdigest()[:10]


def install(force: bool = False) -> dict:
    st = studio()
    ver = _pkg_version()
    if not force:
        cur = st.luau('local f = game:GetService("ReplicatedStorage"):FindFirstChild("Promptimate")\n'
                      'return f and tostring(f:GetAttribute("PackageVersion")) or "none"')
        if cur == ver:
            return {"installed": ver, "changed": False}
    calls = st.upload(_pkg_sources())
    client = (PKG / "PromptimateAutoplay.client.lua").read_text(encoding="utf-8")
    server = (PKG / "PromptimateAutoplay.server.lua").read_text(encoding="utf-8")
    st.luau(f'''
local RS = game:GetService("ReplicatedStorage")
local f = RS.Promptimate
local clips = f:FindFirstChild("Clips") or Instance.new("Folder"); clips.Name = "Clips"; clips.Parent = f
if not f:FindFirstChild("Performance") then
  local m = Instance.new("ModuleScript"); m.Name = "Performance"
  m.Source = 'return [[{{"version":1,"actors":{{}}}}]]'; m.Parent = f
end
if f:GetAttribute("Autoplay") == nil then f:SetAttribute("Autoplay", true) end
if f:GetAttribute("StartDelay") == nil then f:SetAttribute("StartDelay", 1) end
local sps = game:GetService("StarterPlayer"):FindFirstChildOfClass("StarterPlayerScripts")
local ls = sps:FindFirstChild("PromptimateAutoplay") or Instance.new("LocalScript")
ls.Name = "PromptimateAutoplay"; ls.Source = {long_str(client)}; ls.Parent = sps
local ss = game:GetService("ServerScriptService"):FindFirstChild("PromptimateAutoplay") or Instance.new("Script")
ss.Name = "PromptimateAutoplay"; ss.Source = {long_str(server)}; ss.Parent = game:GetService("ServerScriptService")
f:SetAttribute("PackageVersion", {json.dumps(ver)})
return "ok"''')
    return {"installed": ver, "changed": True, "calls": calls + 2}


# ================================================================================================== Studio: scene
SCENE_LUAU = r'''
local HttpService = game:GetService("HttpService")
local RS = game:GetService("ReplicatedStorage")
local actorNames = HttpService:JSONDecode(__ACTORS__)
local targetNames = HttpService:JSONDecode(__TARGETS__)
local root = RS:FindFirstChild("Promptimate")
local Player = require(root.PromptimatePlayer:Clone())
local out = { actors = {}, targets = {}, parts = {}, humanoids = {} }
local hums, rigs = {}, {}
for _, d in workspace:GetDescendants() do
  if d:IsA("Humanoid") and d.Parent:IsA("Model") and not hums[d.Parent.Name] then
    hums[d.Parent.Name] = d.Parent; table.insert(rigs, d.Parent)
  end
end
for n in hums do table.insert(out.humanoids, n) end
local rp = RaycastParams.new(); rp.FilterType = Enum.RaycastFilterType.Exclude; rp.FilterDescendantsInstances = rigs
local function ground(x, y, z)
  local h = workspace:Raycast(Vector3.new(x, y + 0.6, z), Vector3.new(0, -80, 0), rp)
  return h and h.Position.Y or nil
end
for _, n in actorNames do
  local rig = hums[n]
  if not rig then out.actors[n] = { error = "not found" } else
    local path, i = {}, rig
    while i and i ~= game do table.insert(path, 1, i.Name); i = i.Parent end
    local hrp = rig:FindFirstChild("HumanoidRootPart"); local hum = rig:FindFirstChildOfClass("Humanoid")
    local ok, stand = pcall(Player.measure, rig)
    local floor = hrp.Position.Y - hum.HipHeight - hrp.Size.Y / 2
    if hum.RigType == Enum.HumanoidRigType.R6 and rig:FindFirstChild("Left Leg") then
      floor = hrp.Position.Y - hrp.Size.Y / 2 - rig["Left Leg"].Size.Y   -- R6 HipHeight is 0: legs hang below the root
    end
    local width = 0
    for _, pn in { "UpperTorso", "LeftUpperArm", "RightUpperArm", "Torso", "Left Arm", "Right Arm" } do
      local part = rig:FindFirstChild(pn); if part then width += part.Size.X end
    end
    out.actors[n] = { path = path, stand = ok and stand or nil, width = width, x = hrp.Position.X, z = hrp.Position.Z,
      lookX = hrp.CFrame.LookVector.X, lookZ = hrp.CFrame.LookVector.Z, floor = floor,
      -- the surface from above the head: a rig left sunk or lifted by an earlier performance must not shift the floor
      ground = ground(hrp.Position.X, math.max(floor, hrp.Position.Y + 3), hrp.Position.Z) or floor, r15 = hum.RigType == Enum.HumanoidRigType.R15,
      err = (not ok) and tostring(stand) or nil }
  end
end
local function boxOf(d)
  if d:IsA("Model") then return d:GetBoundingBox() end
  return d.CFrame, d.Size
end
local function yawOf(cf) return math.atan2(-cf.LookVector.X, -cf.LookVector.Z) end
local function entry(list)
  if #list == 1 then
    local cf, s = boxOf(list[1])
    return { cf.X, cf.Y, cf.Z, s.X, s.Y, s.Z, yawOf(cf) }
  end
  local lo, hi = Vector3.new(math.huge, math.huge, math.huge), Vector3.new(-math.huge, -math.huge, -math.huge)
  for _, d in list do
    local cf, s = boxOf(d)
    for _, sx in { -1, 1 } do for _, sy in { -1, 1 } do for _, sz in { -1, 1 } do
      local p = cf * Vector3.new(sx * s.X / 2, sy * s.Y / 2, sz * s.Z / 2)
      lo = Vector3.new(math.min(lo.X, p.X), math.min(lo.Y, p.Y), math.min(lo.Z, p.Z))
      hi = Vector3.new(math.max(hi.X, p.X), math.max(hi.Y, p.Y), math.max(hi.Z, p.Z))
    end end end
  end
  local c, s = (lo + hi) / 2, hi - lo
  return { c.X, c.Y, c.Z, s.X, s.Y, s.Z, 0 }
end
local function seatOf(list)
  -- a Seat, or a visible part named Seat*; else the highest low surface of the object (slats of a bench, a ledge)
  local parts = {}
  for _, d in list do
    if d:IsA("BasePart") then table.insert(parts, d) end
    for _, x in d:GetDescendants() do if x:IsA("BasePart") then table.insert(parts, x) end end
  end
  local function entryOf(x) local cf, s = x.CFrame, x.Size
    return { cf.X, cf.Y + s.Y / 2, cf.Z, s.X, s.Z, yawOf(cf), x:IsA("Seat"), x.Name } end
  for _, x in parts do
    if x:IsA("Seat") or (string.sub(string.lower(x.Name), 1, 4) == "seat" and x.Transparency < 0.95) then return entryOf(x) end
  end
  local lo, hi = math.huge, -math.huge
  for _, x in parts do
    if x.Transparency < 0.95 then
      lo = math.min(lo, x.Position.Y - x.Size.Y / 2); hi = math.max(hi, x.Position.Y + x.Size.Y / 2)
    end
  end
  local best = -math.huge
  for _, x in parts do
    local top = x.Position.Y + x.Size.Y / 2
    if x.Transparency < 0.95 and top <= lo + 0.65 * (hi - lo) + 1e-3 and x.Size.X * x.Size.Z >= 0.3 then best = math.max(best, top) end
  end
  if best == -math.huge then return nil end
  local mn, mx = Vector3.new(math.huge, 0, math.huge), Vector3.new(-math.huge, 0, -math.huge)
  local yaw = 0
  for _, x in parts do
    local top = x.Position.Y + x.Size.Y / 2
    if x.Transparency < 0.95 and top >= best - 0.15 and top <= best + 1e-3 and x.Size.X * x.Size.Z >= 0.3 then
      local cf, s = x.CFrame, x.Size
      yaw = yawOf(cf)
      for _, sx in { -1, 1 } do for _, sz in { -1, 1 } do
        local p = cf * Vector3.new(sx * s.X / 2, 0, sz * s.Z / 2)
        mn = Vector3.new(math.min(mn.X, p.X), 0, math.min(mn.Z, p.Z)); mx = Vector3.new(math.max(mx.X, p.X), 0, math.max(mx.Z, p.Z))
      end end
    end
  end
  -- footprint in the seat's own frame (yaw of the last surface part) for oriented benches
  local c = (mn + mx) / 2
  local ca, sa = math.cos(yaw), math.sin(yaw)
  local ex, ez = 0, 0
  for _, x in parts do
    local top = x.Position.Y + x.Size.Y / 2
    if x.Transparency < 0.95 and top >= best - 0.15 and top <= best + 1e-3 and x.Size.X * x.Size.Z >= 0.3 then
      local cf, s = x.CFrame, x.Size
      for _, sx in { -1, 1 } do for _, sz in { -1, 1 } do
        local p = cf * Vector3.new(sx * s.X / 2, 0, sz * s.Z / 2) - c
        ex = math.max(ex, math.abs(p.X * ca - p.Z * sa)); ez = math.max(ez, math.abs(p.X * sa + p.Z * ca))
      end end
    end
  end
  -- backrest: visible parts rising above the seat surface, whose centre is off to one side of the seat
  local bsum, bn = Vector3.zero, 0
  for _, x in parts do
    if x.Transparency < 0.95 and x.Position.Y > best + 0.3 and x.Position.Y - x.Size.Y / 2 < best + 2.5 then
      bsum += Vector3.new(x.Position.X - c.X, 0, x.Position.Z - c.Z); bn += 1
    end
  end
  local back = bn > 0 and (bsum / bn) or Vector3.zero
  return { c.X, best, c.Z, 2 * ex, 2 * ez, yaw, false, "surface", back.X, back.Z }
end
local all = workspace:GetDescendants()
for _, name in targetNames do
  local ln = string.lower(name)
  local stem = (#ln > 3 and string.sub(ln, -1) == "s") and string.sub(ln, 1, -2) or ln
  local exact, pref = {}, {}
  for _, d in all do
    if d:IsA("BasePart") or d:IsA("Model") then
      local n = string.lower(d.Name)
      if n == ln then table.insert(exact, d)
      elseif string.sub(n, 1, #stem) == stem then table.insert(pref, d) end
    end
  end
  local list = #exact > 0 and { exact[1] } or pref
  -- drop matches nested inside other matches
  local keep = {}
  for _, d in list do
    local nested = false
    for _, e in list do if e ~= d and d:IsDescendantOf(e) then nested = true end end
    if not nested and not d:IsDescendantOf(root or RS) then table.insert(keep, d) end
  end
  if #keep > 0 then
    local isHum = #keep == 1 and keep[1]:IsA("Model") and keep[1]:FindFirstChildOfClass("Humanoid") ~= nil
    out.targets[name] = { box = entry(keep), seat = seatOf(keep), n = #keep, humanoid = isHum,
      names = (function() local t = {} for i, d in keep do if i <= 12 then table.insert(t, d.Name) end end return t end)() }
  end
end
-- only parts near the performing characters (sourced sets are big: the whole world overflows the tool output)
local centres = {}
for _, n in actorNames do
  local rig = hums[n]
  local hrp = rig and rig:FindFirstChild("HumanoidRootPart")
  if hrp then table.insert(centres, hrp.Position) end
end
local function near(p)
  if #centres == 0 then return true end
  for _, c in centres do if math.abs(p.X - c.X) < 45 and math.abs(p.Z - c.Z) < 45 then return true end end
  return false
end
for _, d in all do
  if d:IsA("BasePart") and d.Transparency < 0.95 and not d:IsA("Terrain") and d.Size.Y >= 0.3 and d.Size.X * d.Size.Z < 2500
     and near(d.Position) then
    local inRig = false
    local m = d:FindFirstAncestorOfClass("Model")
    if m and m:FindFirstChildOfClass("Humanoid") then inRig = true end
    if not inRig and #out.parts < 4000 then
      table.insert(out.parts, { math.floor(d.Position.X * 10) / 10, math.floor(d.Position.Z * 10) / 10,
        math.floor(d.Size.X * 10) / 10, math.floor(d.Size.Z * 10) / 10, math.floor(yawOf(d.CFrame) * 100) / 100,
        math.floor((d.Position.Y + d.Size.Y / 2) * 10) / 10 })
    end
  end
end
local perf = root:FindFirstChild("Performance")
out.perf = perf and require(perf:Clone()) or nil
return HttpService:JSONEncode(out)
'''


class Scene:
    """What roblox_perform knows about the place: characters (measured), named targets and part footprints."""

    def __init__(self, actor_names: list[str], target_names: list[str]):
        code = (SCENE_LUAU.replace("__ACTORS__", long_str(json.dumps(actor_names)))
                .replace("__TARGETS__", long_str(json.dumps(sorted(set(target_names))))))
        if WORLD is not None:
            d = WORLD.scene(actor_names, sorted(set(target_names)), {"version": 1, "actors": {}})   # a clean cue sheet, as the producer resets Studio's
        else:
            d = studio().luau_json(code)
        self.actors = d["actors"]
        self.targets = d.get("targets") or {}
        self.parts = d.get("parts") or []
        self.humanoids = d.get("humanoids") or []
        self.perf = json.loads(d["perf"]) if d.get("perf") else {"version": 1, "actors": {}}
        self.perf.setdefault("actors", {})


STANDFREE_LUAU = r"""
local HttpService = game:GetService("HttpService")
local q = HttpService:JSONDecode(__Q__)
local rigs = {}
for _, d in workspace:GetDescendants() do
  if d:IsA("Humanoid") and d.Parent:IsA("Model") then table.insert(rigs, d.Parent) end
end
local op = OverlapParams.new(); op.FilterType = Enum.RaycastFilterType.Exclude; op.FilterDescendantsInstances = rigs
local out = {}
for _, p in q.pts do
  local floor = q.floor
  local cf = CFrame.new(p[1], floor + 0.35 + q.h / 2, p[2])
  local free = true
  for _, part in workspace:GetPartBoundsInBox(cf, Vector3.new(q.r * 2, q.h, q.r * 2), op) do
    if part.CanCollide and part.Transparency < 0.95 and not part:IsA("Terrain") and part.Position.Y + part.Size.Y / 2 > floor + 0.35 then
      free = false; break
    end
  end
  table.insert(out, free)
end
return HttpService:JSONEncode(out)
"""


# staging backend: None = Studio; the headless pipeline plugs in roblox/headless/stage.Staging (our own geometry)
WORLD = None


def _stand_free(pts, floor, radius: float, spm: float) -> list[bool]:
    """Whether a character standing at each ground point (x, z) is clear of scenery (Studio overlap query)."""
    if floor is None:
        return [True] * len(pts)
    q = {"pts": [[float(p[0]), float(p[1])] for p in pts], "floor": float(floor), "r": float(radius),
         "h": float(1.7 * spm)}
    try:
        if WORLD is not None:
            return list(WORLD.stand_free(q))
        return list(studio().luau_json(STANDFREE_LUAU.replace("__Q__", long_str(json.dumps(q)))))
    except Exception:
        return [True] * len(pts)


def _target_names(actors: list[Actor]) -> list[str]:
    out = []
    for a in actors:
        if isinstance(a.facing, str) and a.facing.lower() not in DIRS:
            out.append(a.facing)
        for b in a.beats:
            for v in (b.to, b.face, b.sit):
                if isinstance(v, str) and v.lower() not in DIRS:
                    out.append(v.split(":")[0])
    return out


# ================================================================================================= planning
class Planner:
    """Resolves names/sides/points to world positions (studs) and keeps a rough position timeline per character
    (for targets like 'to: Officer' or 'face: Timmy' before that character is generated)."""

    def __init__(self, scene: Scene, actors: list[Actor]):
        self.scene = scene
        self.anchors: dict[str, list[tuple[float, np.ndarray]]] = {}
        self.tracks: dict[str, list] = {}      # exact hips tracks [[t, x, z], ...] once generated
        for name, a in scene.perf["actors"].items():
            if a.get("track"):
                self.tracks[name] = a["track"]
        self.actor_names = {a.name for a in actors}
        self.width = {n: a.get("width") for n, a in scene.actors.items() if a.get("width")}

    def char_pos(self, name: str, t: float) -> np.ndarray | None:
        tr = self.tracks.get(name)
        if tr:
            ts = [r[0] for r in tr]
            return np.array([np.interp(t, ts, [r[1] for r in tr]), np.interp(t, ts, [r[2] for r in tr])])
        an = self.anchors.get(name)
        if an:
            ts = [a for a, _ in an]
            return np.array([np.interp(t, ts, [p[0] for _, p in an]), np.interp(t, ts, [p[1] for _, p in an])])
        a = self.scene.actors.get(name)
        if a and "x" in a:
            return np.array([a["x"], a["z"]])
        tg = self.scene.targets.get(name)
        if tg and tg.get("humanoid"):
            return np.array([tg["box"][0], tg["box"][2]])
        return None

    def is_char(self, name: str) -> bool:
        return (name in self.actor_names or name in self.tracks or name in self.scene.actors
                or bool(self.scene.targets.get(name, {}).get("humanoid")))

    def point(self, name: str, t: float) -> np.ndarray:
        """Centre of a named character (at story time t) or object."""
        if self.is_char(name):
            p = self.char_pos(name, t)
            if p is not None:
                return p
        tg = self.scene.targets.get(name)
        if not tg:
            raise ValueError(f"'{name}' not found in the place (characters: {', '.join(self.scene.humanoids[:12])})")
        return np.array([tg["box"][0], tg["box"][2]])

    def extent(self, name: str, d) -> float:
        """Half extent of a named object's footprint along ground direction d."""
        b = self.scene.targets[name]["box"]
        yaw = b[6]
        ax = np.array([math.cos(yaw), -math.sin(yaw)])      # part's local +X on the ground
        az = np.array([math.sin(yaw), math.cos(yaw)])       # local +Z
        d = np.asarray(d, float)
        return 0.5 * (abs(d @ ax) * b[3] + abs(d @ az) * b[5])

    def spot(self, target, frm: np.ndarray, t: float, spm: float) -> np.ndarray:
        """Where a character standing at `frm` should end up for `to: target` (stops short of objects/people)."""
        if isinstance(target, (list, tuple)):
            return np.array(target[:2], float)
        name, _, side = target.partition(":")
        margin = 0.55 * spm
        if self.is_char(name):
            c = self.point(name, t)
            d = frm - c
            if side:
                d = np.array(DIRS[side.lower()])
            n = np.linalg.norm(d)
            d = d / n if n > 1e-6 else np.array([1.0, 0.0])
            # ~1.1 m: talking distance; on the approach side if that spot is clear of scenery, else the nearest
            # clear spot around the character (benches, crates, posts): standing inside one reads as clipping
            cands = []
            for ang in (0, 25, -25, 50, -50, 75, -75, 100, -100, 130, -130, 160, -160, 180):
                a = math.radians(ang)
                dd = np.array([d[0] * math.cos(a) - d[1] * math.sin(a), d[0] * math.sin(a) + d[1] * math.cos(a)])
                for r in (1.1, 1.35):
                    cands.append(c + dd * r * spm)
            free = _stand_free(cands, self.ground, 0.42 * spm, spm)
            for pt, ok in zip(cands, free):
                if ok:
                    return pt
            return cands[0]
        c = self.point(name, t)
        tg = self.scene.targets.get(name) or {}
        if not side and tg.get("seat"):
            # walking up to something to sit on: stand in front of the seat, at the nearest point along it
            st = self.seat(name, frm, spm, [])
            return st["point"] + st["front"] * 0.6 * spm
        if side:
            d = np.array(DIRS[side.lower()])
        else:
            d = frm - c
            n = np.linalg.norm(d)
            d = d / n if n > 1e-6 else np.array([1.0, 0.0])
        return c + d * (self.extent(name, d) + margin)

    def direction(self, face, at: np.ndarray, t: float) -> np.ndarray:
        if isinstance(face, (list, tuple)):
            v = np.array(face[:2], float) - at
        elif face.lower() in DIRS:
            v = np.array(DIRS[face.lower()])
        else:
            v = self.point(face.split(":")[0], t) - at
        n = np.linalg.norm(v)
        return v / n if n > 1e-6 else np.array([0.0, -1.0])

    def seat(self, sit, near: np.ndarray, spm: float, occupied: list, width: float | None = None) -> dict:
        """Seat for `sit`: {'top': y studs, 'point': hips xz, 'front': facing dir, 'name'}. Picks the free spot on the
        seat nearest to the character, keeping ~0.6 m from anyone else seated there."""
        if isinstance(sit, (int, float)):
            return {"top": None, "height_studs": float(sit), "point": near, "front": None, "name": None}
        tg = self.scene.targets.get(sit)
        if not tg:
            raise ValueError(f"seat '{sit}' not found in the place")
        s = tg.get("seat")
        back = None
        if s:
            cx, top, cz, sx, sz, yaw, is_seat, pname = s[:8]
            if len(s) >= 10:
                back = np.array([s[8], s[9]], float)
        else:
            b = tg["box"]
            cx, top, cz, sx, sz, yaw, is_seat, pname = b[0], b[1] + b[4] / 2, b[2], b[3], b[5], b[6], False, sit
        ax = np.array([math.cos(yaw), -math.sin(yaw)])
        az = np.array([math.sin(yaw), math.cos(yaw)])
        long_ax, half = (ax, sx / 2) if sx >= sz else (az, sz / 2)
        short_ax = az if sx >= sz else ax
        pname = sit                              # occupancy and collision-ignore key: the object's name
        c = np.array([cx, cz])
        if is_seat:
            front = -az                          # a Seat faces its LookVector (-Z local)
        elif back is not None and abs(back @ short_ax) > 0.15:
            front = -short_ax if back @ short_ax > 0 else short_ax     # away from the backrest
        else:
            front = short_ax if (near - c) @ short_ax >= 0 else -short_ax   # backless: face the approach side
        w_self = width or 1.65 * spm            # blocky R15 bodies: torso + arms ~ 1.65 m-equivalents wide
        lim = max(0.0, half - 0.4 * w_self)     # keep the body on the seat (arms may overhang the end a little)
        u_pref = float(np.clip((near - c) @ long_ax, -lim, lim))

        def clash(u):
            return sum(max(0.0, 0.5 * (w_self + (o.get("w") or w_self)) + 0.2 - abs(o["u"] - u))
                       for o in occupied if o["name"] == pname)

        # the free spot on the seat nearest to where the character comes from (never past its ends)
        grid = np.linspace(-lim, lim, max(2, int(2 * lim / 0.05) + 1))
        u = float(min(grid, key=lambda v: (round(clash(v), 3), abs(v - u_pref))))
        crowded = clash(u) > 0.05
        point = c + long_ax * u + front * 0.1 * spm      # a little forward: leaning back meets the backrest
        return {"top": top, "point": point, "front": front, "name": pname, "u": u, "w": w_self,
                "crowded": crowded, "half": half, "long": long_ax, "center": c}


# ================================================================================================= generation
def _evaluate(root, rot, spec) -> tuple[float, list[str], dict]:
    """Score one generated clip against the beat spec (clip frame): end facing, path end, seat."""
    issues, info, score = [], {}, 0.0
    if spec.get("face_rel") is not None:
        h = C.frame_placement(root, rot, len(root) - 1)[2]
        err = abs(math.degrees(wrap(h - spec["face_rel"])))
        info["face_err"] = round(err, 1)
        score += err / FACE_TOL
        if err > FACE_TOL:
            issues.append(f"end facing {err:.0f} deg off")
    if spec.get("end_local") is not None:
        e = float(np.hypot(root[-1, 0] - root[0, 0] - spec["end_local"][0], root[-1, 2] - root[0, 2] - spec["end_local"][1]))
        info["end_err_m"] = round(e, 2)
        score += e / PATH_TOL
        if e > PATH_TOL:
            issues.append(f"ends {e:.1f} m from its mark")
    land = spec.get("lands")
    if land:
        pos = motion.fk(root[-12:], rot[-12:])
        hips_y = float(pos[:, 0, 1].mean())
        spine = pos[:, 4] - pos[:, 0]
        tilt = float(np.degrees(np.arccos(np.clip(spine[:, 1] / np.linalg.norm(spine, axis=1), -1, 1))).mean())
        left = pos[:, 22] - pos[:, 26]
        fwd = np.cross(left, spine)
        face_up = float((fwd[:, 1] / (np.linalg.norm(fwd, axis=1) + 1e-9)).mean())
        info["fall_end"] = {"hips_m": round(hips_y, 2), "tilt": round(tilt), "face_up": round(face_up, 2)}
        if land == "back" and not (tilt > 55 and face_up > 0.4 and hips_y < 0.35):
            issues.append("fall doesn't end lying on the back")
            score += 3
        elif land == "ground" and hips_y > 0.4:
            issues.append("fall doesn't reach the ground")
            score += 3
    # getting up: the beat must end standing (a failed get-up leaves every later beat of the chain on the floor)
    words_all = " ".join(p for p, _ in spec.get("segments") or []).lower()
    if re.search(r"gets? up|stands? up|rises|getting up|standing up", words_all) and not spec.get("seat_local"):
        end_hips = float(root[-8:, 1].mean())
        info["end_hips_m"] = round(end_hips, 2)
        if end_hips < 0.7:
            issues.append(f"doesn't get up (hips {end_hips:.2f} m at the end)")
            score += 6
    # upright: a beat that asks for nothing low (fall, lie, crawl, kneel, bend, sit, ...) shouldn't tip the body
    # over (a "jump with joy" that reads as a faint)
    words = " ".join(p for p, _ in spec.get("segments") or []).lower()
    if words and not land and not spec.get("seat_local") and not re.search(
            r"fall|lie|lies|lying|crawl|kneel|bend|bow|sit|squat|crouch|ground|floor|sleep|dive|roll|trip|stumbl|faint|"
            r"collapse|cartwheel|flip|push-?up|lean|duck|dodge|pick|tie|zombie|drunk", words):
        pos = motion.fk(root, rot)
        spine = pos[:, 4] - pos[:, 0]
        tilt = np.degrees(np.arccos(np.clip(spine[:, 1] / (np.linalg.norm(spine, axis=1) + 1e-9), -1, 1)))
        over = tilt > 35
        run_len, best = 0, 0
        for o in over:
            run_len = run_len + 1 if o else 0
            best = max(best, run_len)
        info["max_tilt"] = round(float(tilt.max()))
        if best > 0.3 * motion.FPS:
            issues.append(f"body tips over {float(tilt.max()):.0f} deg (not asked for)")
            score += 3
    st = spec.get("seat_local")
    if st:
        a = max(0, round(st["t"][0] * motion.FPS) + 6)
        b = min(len(root) - 1, round(st["t"][1] * motion.FPS) - 3)
        if b > a:
            want = st["height"] + C.SEAT_HIPS_OFFSET
            herr = float(np.abs(root[a:b + 1, 1] - want).max())
            xz = float(np.hypot(root[a:b + 1, 0] - root[0, 0] - st["x"], root[a:b + 1, 2] - root[0, 2] - st["z"]).max())
            info["seat_err_cm"] = [round(herr * 100, 1), round(xz * 100, 1)]
            score += herr / 0.06 + xz / 0.15
            if herr > 0.08 or xz > 0.18:
                issues.append(f"seat off by {herr * 100:.0f} cm height / {xz * 100:.0f} cm")
    return score, issues, info


def _smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def _warp(name: str, spec: dict) -> float:
    """Land the seat / the mark exactly. The engine follows the root constraints, but post-processing removes the
    foot sliding it used to get there and gives back up to ~0.5 m of travel (measured on get-up -> walk -> sit). The
    remaining offset is blended into the root over the approach (from the departure to the arrival, smoothstep)
    and held afterwards; the player's foot locking absorbs it in the steps. Idempotent; returns the offset in cm."""
    d = SRV.OUTPUT / name
    root, rot = motion.load(d)
    F = len(root)
    path = spec.get("path_local") or []
    dep = max((t for t, x, z in path if abs(x) < 1e-3 and abs(z) < 1e-3), default=0.0)
    st = spec.get("seat_local")
    if st and st["t"][0] > 0.3:
        a = min(F - 1, round(st["t"][0] * motion.FPS))
        b = min(F - 1, round(st["t"][1] * motion.FPS))
        cur = root[a:b + 1][:, [0, 2]].mean(0) - root[0, [0, 2]]
        off = np.array([st["x"], st["z"]]) - cur
        f0, f1 = round(dep * motion.FPS), a
    elif spec.get("end_local") is not None and not spec.get("in_place") and path:
        tgt = np.array(spec["end_local"])
        arr = min((t for t, x, z in path if abs(x - tgt[0]) < 1e-3 and abs(z - tgt[1]) < 1e-3), default=path[-1][0])
        off = tgt - (root[-1, [0, 2]] - root[0, [0, 2]])
        f0, f1 = round(dep * motion.FPS), min(F - 1, round(arr * motion.FPS))
    else:
        return 0.0
    n = float(np.linalg.norm(off))
    if n < 0.05 or n > 1.5 or f1 <= f0 + 5:
        return 0.0
    w = _smooth((np.arange(F) - f0) / max(1, f1 - f0))
    root = root.copy()
    root[:, 0] += w * off[0]
    root[:, 2] += w * off[1]
    import postprocess
    postprocess.save(d, root, rot)
    return round(n * 100, 1)


def _qmul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Quaternion product a*b, xyzw, broadcast over leading axes."""
    ax, ay, az, aw = np.moveaxis(a, -1, 0)
    bx, by, bz, bw = np.moveaxis(b, -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], -1)


def _yawed(root: np.ndarray, rot: np.ndarray, yaw: np.ndarray):
    """The clip turned about +Y by yaw[f] (radians) per frame, around its first frame's hips."""
    q = np.zeros((len(yaw), 4), np.float32)
    q[:, 1], q[:, 3] = np.sin(yaw / 2), np.cos(yaw / 2)
    rot = rot.copy()
    rot[:, 0] = _qmul(q, rot[:, 0])
    root = root.copy()
    c, s_ = np.cos(yaw), np.sin(yaw)
    dx, dz = root[:, 0] - root[0, 0], root[:, 2] - root[0, 2]
    root[:, 0] = root[0, 0] + c * dx + s_ * dz
    root[:, 2] = root[0, 2] - s_ * dx + c * dz
    return root, rot


def _turn(name: str, spec: dict) -> float:
    """End facing for in-place beats (talking to someone, reacting): the engine's heading constraint often leaves
    the character facing well away from who they talk to. The missing turn is blended into the root over the beat
    (smoothstep), so the character turns toward them in place. Idempotent; returns the turn in degrees."""
    if spec.get("face_rel") is None or spec.get("seat_local") or spec.get("path_local"):
        return 0.0
    d = SRV.OUTPUT / name
    root, rot = motion.load(d)
    F = len(root)
    if F < 12:
        return 0.0
    err = wrap(spec["face_rel"] - C.frame_placement(root, rot, F - 1)[2])
    if abs(math.degrees(err)) < 12:
        return 0.0
    err = float(np.clip(err, -math.radians(160), math.radians(160)))
    w = _smooth(np.arange(F) / max(1, int(F * 0.7)))      # turned by 70% of the beat, then held
    best = None
    for sgn in (1.0, -1.0):          # pick the direction that lands the facing (heading convention vs +Y yaw)
        r2, q2 = _yawed(root, rot, (sgn * err * w).astype(np.float32))
        e2 = abs(wrap(spec["face_rel"] - C.frame_placement(r2, q2, F - 1)[2]))
        if best is None or e2 < best[0]:
            best = (e2, r2, q2)
    if best[0] >= abs(err) - math.radians(5):
        return 0.0
    import postprocess
    postprocess.save(d, best[1], best[2])
    return round(math.degrees(abs(err)), 1)


def _cache_key(actor: str, spec: dict, prev: str | None) -> str:
    s = json.dumps({"a": actor, "spec": {k: v for k, v in spec.items() if k != "label"}, "prev": prev,
                    "v": 3}, sort_keys=True, default=lambda o: np.asarray(o).round(4).tolist())
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def _beat_cache() -> dict:
    p = STATE / "beats.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_beat_cache(c: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "beats.json").write_text(json.dumps(c, indent=0))


def _log_nan(actor, idx, spec, kw, err) -> None:
    try:
        with open(STATE / "nan_requests.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "actor": actor, "beat": idx, "err": str(err)[:200],
                                "spec": {k: v for k, v in spec.items() if k != "label"}, "kw": list(kw)},
                               default=lambda o: np.asarray(o).round(4).tolist()) + chr(10))
    except Exception:
        pass


def _generate(actor: str, idx: int, spec: dict, prev: str | None) -> tuple[str, dict]:
    """generate_motion for one beat (with end facing via the heading constraint), retried with new seeds until the
    facing / mark / seat checks pass. Returns (motion name, info)."""
    g = _gen_frame(prev)
    kw = {}
    if spec.get("path_local"):
        kw["root_path"] = [SRV.Waypoint(t=t, x=round(gx, 4), z=round(gz, 4))
                           for t, x, z in spec["path_local"] for gx, gz in [to_gen((x, z), g)]]
    st = spec.get("seat_local")
    if st:
        sx, sz = to_gen((st["x"], st["z"]), g)
        kw["seat"] = SRV.Seat(t=st["t"], height=round(st["height"], 3), x=round(sx, 4), z=round(sz, 4),
                              heading_deg=None if st.get("heading") is None else
                              round(math.degrees(wrap(st["heading"] + g[2])), 2), furniture=st.get("furniture"))
    if prev:
        kw["continue_from"] = prev
    if spec.get("in_place"):
        kw["in_place"] = True
    segs = [SRV.MotionSegment(prompt=p, seconds=s) for p, s in spec["segments"]]
    best = None
    n_att = int(os.environ.get("PROMPTIMATE_RBX_ATTEMPTS", MAX_ATTEMPTS))
    if re.search(r"gets? up|stands? up|rises", " ".join(p for p, _ in spec["segments"]).lower()):
        n_att = max(n_att, 4)          # a failed get-up ruins the rest of the chain: worth more seeds
    for attempt in range(n_att):
        if True:
            real = _tls_install()
            if spec.get("face_rel") is not None:
                _TLS.override = _HeadingProxy(real, wrap(spec["face_rel"] + g[2]))
            try:
                for tries in range(4):   # the shared GPU daemon may restart (other jobs, memory pressure): retry
                    try:
                        res = SRV.generate_motion(segs, name=f"rbx_{actor}_{idx:02d}",
                                                  takes=int(os.environ.get("PROMPTIMATE_RBX_TAKES", "2")),
                                                  seed=(attempt + spec.get("retry", 0) * MAX_ATTEMPTS) * 101,
                                                  unity_check="off", **kw)
                        break
                    except (ConnectionError, OSError) as e:
                        if tries == 3:
                            raise RuntimeError(f"motion engine unavailable: {e}") from e
                        time.sleep(10 * (tries + 1))
                    except RuntimeError as e:
                        # a degenerate request (a non-finite constraint, e.g. a target that wasn't placed yet when
                        # characters generate in parallel) fails in the engine: drop the extra constraints and try
                        # again rather than losing the whole episode
                        if "non-finite" not in str(e) or tries == 3:
                            raise
                        _log_nan(actor, idx, spec, kw, e)
                        _TLS.override = None
                        kw = {k: v for k, v in kw.items() if k in ("continue_from", "in_place")}
            finally:
                _TLS.override = None
        meta = json.loads(res[0])
        root, rot = motion.load(Path(meta["files"]["raw_dir"]))
        score, issues, info = _evaluate(root, rot, spec)
        chk = meta.get("checks", {})
        info.update(attempts=attempt + 1, checks_ok=chk.get("passed"))
        if chk.get("passed") is False:   # the engine's own checks (pops, floating, sliding...) failed: never accept
            failed = [str(x) for x in chk.get("failures") or []]
            issues.append("automatic checks failed" + (f" ({'; '.join(failed[:2])})" if failed else ""))
            score += 2
        if best is None or score < best[0]:
            best = (score, meta["name"], issues, info)
        if not issues:
            break
    _, name, issues, info = best
    info["issues"] = issues
    return name, info


def _expand(actor: Actor) -> list[dict]:
    """Beats with absolute story times; gaps filled with idle beats (seated if the character is seated)."""
    out, t, seated = [], None, None
    for b in actor.beats:
        segs = _segments(b)
        dur = sum(s for _, s in segs)
        start = b.at if b.at is not None else (t if t is not None else 0.0)
        if t is not None and start > t + 0.25:
            gap = start - t
            prompt = "a person sits still and breathes calmly" if seated else "a person stands still and breathes"
            fill = Beat(prompt=prompt, seconds=gap, sit=seated)
            out.append({"beat": fill, "segments": _segments(fill), "start": t, "dur": gap, "filler": True})
        elif t is not None and start < t - 0.05:
            start = t                                    # overlapping beats: play after the previous one
        out.append({"beat": b, "segments": segs, "start": start, "dur": dur, "filler": False})
        t = start + dur
        seated = b.sit
    for e, nxt in zip(out, out[1:] + [None]):
        # the next beat starts standing still (no travel words): this beat must come to rest, or the next clip
        # inherits its momentum (measured: a crouch after a run slid 4 m)
        e["next_still"] = nxt is None or not _LOCO.search(nxt["segments"][0][0])
    return out


def _spec(e: dict, p, yaw, spm, seated, plan: Planner, actor: str, occupied: list) -> tuple[dict, dict]:
    """Beat -> generation spec in the clip frame (+ world info for checks). seated: the seat the character is on at
    the start of this beat (or None)."""
    b: Beat = e["beat"]
    dur, t0 = e["dur"], e["start"]
    segs = e["segments"]
    spec = {"segments": [(p_, round(s, 3)) for p_, s in segs]}
    world = {"t0": t0, "t1": t0 + dur, "label": _short(segs[0][0]), "face": b.face}
    p = np.asarray(p, float)
    # --- seat
    seat = None
    if b.sit is not None:
        if seated and seated["key"] == (b.sit if isinstance(b.sit, str) else f"h{b.sit}"):
            seat = dict(seated)
            span = [0.0, dur]
        else:
            near = plan.spot(b.to, p, t0 + dur, spm) if b.to is not None else p
            seat = plan.seat(b.sit, near, spm, occupied, plan.width.get(actor))
            seat["key"] = b.sit if isinstance(b.sit, str) else f"h{b.sit}"
            if b.to is not None and isinstance(b.to, list):
                seat["point"] = np.array(b.to[:2], float)
            sf = b.sit_from if b.sit_from is not None else min(max(1.4, 0.5 * dur), max(0.6, dur - 0.4))
            span = [round(sf, 3), dur]
        if seat.get("top") is not None:
            seat["height_m"] = (seat["top"] - plan.ground) / spm
        else:
            seat["height_m"] = seat["height_studs"] / spm
        face_dir = plan.direction(b.face, seat["point"], t0 + dur) if b.face is not None else seat.get("front")
        if face_dir is None:
            face_dir = basis(yaw)[0]
        seat["face"] = np.asarray(face_dir, float)
        lx, lz = to_local(p, yaw, spm, seat["point"])
        # R15 thigh boxes hang lower under the pelvis than SOMA's skin: generate for a slightly higher seat
        # (measured: pelvis/thigh undersides 0.12-0.17 m into the slats without it)
        spec["seat_local"] = {"t": span, "height": float(np.clip(seat["height_m"] + R15_SEAT_LIFT, 0.2, 1.0)),
                              "x": lx, "z": lz,
                              "heading": wrap(yaw_of(seat["face"]) - yaw), "furniture": "bench"}
        world["seat"] = {"name": seat.get("name"), "top": seat.get("top"), "span": [t0 + span[0], t0 + dur],
                         "point": seat["point"].tolist()}
        if seat.get("crowded"):
            world.setdefault("notes", []).append(f"{seat.get('name')} is too short for everyone on it")
        if seat.get("long") is not None:
            world["seat"]["axis"] = [*np.asarray(seat["center"]).tolist(), *np.asarray(seat["long"]).tolist(),
                                     float(seat["half"])]
        occupied.append({"name": seat.get("name"), "u": seat.get("u", 0.0), "t": [t0 + span[0], t0 + dur],
                         "w": seat.get("w")})
        spec["face_rel"] = spec["seat_local"]["heading"]
        end = seat["point"]
        # approach the seat if it is more than ~0.5 m away
        if span[0] > 0 and np.linalg.norm(end - p) > 0.5 * spm:
            stand_at = end + seat["face"] * 0.42 * spm
            arrive = max(0.4, span[0] - 0.7)
            path = [(0.0, 0.0, 0.0)]
            dep = 0.0
            if len(segs) > 1 and not _LOCO.search(segs[0][0]) and segs[0][1] - 0.2 < arrive - 0.5:
                dep = segs[0][1] - 0.2
                path.append((round(dep, 3), 0.0, 0.0))      # e.g. gets up first, then walks
            pts = [stand_at]
            if b.via:                         # the creator's route to the seat
                pts = [np.array(v[:2], float) for v in b.via] + [stand_at]
            elif seat.get("long") is not None and (p - seat["center"]) @ seat["front"] < 0.3 * spm:
                # coming from behind the seat: round its nearer end to the front instead of through the backrest
                corners = [seat["center"] + seat["long"] * sd * (seat["half"] + 0.6 * spm) + seat["front"] * 0.5 * spm
                           for sd in (-1.0, 1.0)]
                corner = min(corners, key=lambda q: np.linalg.norm(q - p) + np.linalg.norm(stand_at - q))
                pts = [corner, stand_at]
            legs = [float(np.linalg.norm(b_ - a_)) for a_, b_ in zip([p] + pts, pts)]
            acc = 0.0
            for q, L in zip(pts, legs):
                acc += L
                path.append((round(dep + (arrive - dep) * acc / max(sum(legs), 1e-6), 3), *to_local(p, yaw, spm, q)))
            spec["path_local"] = path
    elif seated:
        # standing up from the seat: hold the seated pose for the first few frames
        spec["seat_local"] = {"t": [0.0, 0.3], "height": float(np.clip(seated["height_m"] + R15_SEAT_LIFT, 0.2, 1.0)), "x": 0.0, "z": 0.0,
                              "heading": 0.0, "furniture": "bench"}
        world["stands_up"] = True
    # --- path
    end = p
    if b.sit is None and (b.to is not None or b.via):
        frm = np.array(b.via[-1][:2], float) if b.via else p      # approach direction: from the last waypoint
        target = plan.spot(b.to, frm, t0 + dur, spm) if b.to is not None else np.array(b.via[-1], float)
        dep, arr = 0.0, dur
        if len(segs) > 1:
            if not _LOCO.search(segs[0][0]):
                dep = max(0.0, segs[0][1] - 0.2)
            if not _LOCO.search(segs[-1][0]):
                arr = dur - segs[-1][1] + min(0.5, segs[-1][1] / 2)
        if arr > dur - 0.5 and (re.search(r"\b(stops?|then stands|halts?)\b", segs[-1][0], re.I) or e.get("next_still")):
            arr = max(dep + 0.5, dur - max(0.5, 0.2 * segs[-1][1]))     # come to rest before the beat ends
        if b.arrive is not None:
            arr = float(np.clip(b.arrive, 0.3, dur))
        pts = [p] + [np.array(v[:2], float) for v in (b.via or [])] + [target]
        lens = [float(np.linalg.norm(b_ - a_)) for a_, b_ in zip(pts, pts[1:])]
        tot = sum(lens) or 1.0
        path, acc = [(0.0, 0.0, 0.0)], 0.0
        if dep > 0:
            path.append((round(dep, 3), 0.0, 0.0))
        for q, L in zip(pts[1:], lens):
            acc += L
            path.append((round(dep + (arr - dep) * acc / tot, 3), *to_local(p, yaw, spm, q)))
        if arr < dur - 0.05:
            path.append((round(dur, 3), *to_local(p, yaw, spm, target)))
        spec["path_local"] = path
        spec["end_local"] = to_local(p, yaw, spm, target)
        end = target
        world["to"] = target.tolist()
    # --- peek: out sideways from cover and back (hips path), relative to the facing at the start
    if b.peek and b.peek.lower() in ("left", "right") and "path_local" not in spec:
        # measured over 4 seeds from a crouch (demo/roblox_short/hard_beats.py): the hips path does the work and
        # the lean wording fights it; 'steps ... leans out ... steps back' + 0.6 m: head 0.66 m out, past a cover
        # edge 4/4 (1.1 s visible), back in cover 3/4 (demo wording, no path: 0.29 m, 1/4, 0/4)
        side = b.peek.lower()
        s = 0.6 if side == "left" else -0.6
        if not re.search(r"\bsteps?\b", segs[-1][0], re.I):
            crouch = "crouches, " if re.search(r"\bcrouch", segs[-1][0], re.I) else ""
            spec["segments"][-1] = (f"a person {crouch}steps to the {side} and leans out to look, then steps back",
                                    spec["segments"][-1][1])
            world["prompt_adjusted"] = spec["segments"][-1][0]
        spec["path_local"] = [(0.0, 0.0, 0.0), (round(0.25 * dur, 3), 0.0, 0.0), (round(0.45 * dur, 3), s, 0.05),
                              (round(0.72 * dur, 3), s, 0.05), (round(0.92 * dur, 3), 0.0, 0.0), (round(dur, 3), 0.0, 0.0)]
        world["peek"] = b.peek.lower()
    # --- stationary beats (idling, talking, arms crossed...): no travel. Long standing clips otherwise drift
    # metres over 10-20 s (measured: 12 studs backward through a shop door over 34 s of idling).
    if ("path_local" not in spec and "seat_local" not in spec and b.to is None
            and all(_STILL.search(p_) and not _LOCO.search(p_) for p_, _ in segs)):
        spec["in_place"] = True
        spec["end_local"] = (0.0, 0.0)
    # --- falls: check that the clip actually lands (readable fall), retry otherwise
    last = segs[-1][0]
    if re.search(r"\bfall(s|ing)?\b|\bcollapses?\b|\btrips?\b", last, re.I):
        if re.search(r"\b(on|onto) (their|his|her) back\b|\bflat\b|\blies\b|\blying\b", last, re.I):
            spec["lands"] = "back"
        elif re.search(r"\b(ground|floor|down)\b", last, re.I):
            spec["lands"] = "ground"
    # --- end facing
    if b.face is not None and spec.get("face_rel") is None:
        d = plan.direction(b.face, end, t0 + dur)
        spec["face_rel"] = wrap(yaw_of(d) - yaw)
    return spec, {"world": world, "seat": seat}


def perform(actors: list[Actor], check: bool = True, preview: bool = True) -> list:
    t_all = time.time()
    st = studio() if WORLD is None else None
    calls0 = st.calls if st else 0
    inst = install() if WORLD is None else {"offline": True}
    scene = Scene([a.name for a in actors], _target_names(actors))
    plan = Planner(scene, actors)
    errors = [f"{a.name}: character not found (characters in the place: {', '.join(scene.humanoids[:15])})"
              for a in actors if "error" in scene.actors.get(a.name, {"error": 1})]
    if errors:
        return [json.dumps({"ok": False, "errors": errors})]
    cache = _beat_cache()
    # ---- start placements and rough position timelines (for character targets)
    starts = {}
    for a in actors:
        m = scene.actors[a.name]
        if m.get("stand") is None:
            return [json.dumps({"ok": False, "errors": [f"{a.name}: can't measure the rig ({m.get('err')}); "
                                                        "PromptimatePlayer needs an R15 character"]})]
        spm = m["stand"] / SOMA_HIP
        old = scene.perf["actors"].get(a.name)
        if a.append and old and old.get("clips"):
            last = old["clips"][-1]
            p, yaw = np.array(old["end"][:2]), old["end"][2]
        else:
            if a.start is not None:
                p = np.array(a.start[:2], float)
            elif old and old.get("clips"):
                c0 = old["clips"][0]
                p = np.array([c0["x"], c0["z"]])
            else:
                p = np.array([m["x"], m["z"]])
            if a.facing is not None:
                yaw = yaw_of(plan.direction(a.facing, p, 0.0))
            elif old and old.get("clips"):
                yaw = old["clips"][0]["yaw"]
            else:
                yaw = yaw_of((m["lookX"], m["lookZ"]))
        starts[a.name] = (p, yaw, spm)
    # floor height under each start point (cast from just above the rig's floor, so benches aren't taken for it)
    gs = (WORLD.ground if WORLD is not None else lambda q: studio().luau_json(GROUND_LUAU.replace("__PTS__", long_str(json.dumps(q)))))((
        [[float(starts[a.name][0][0]), float(max(scene.actors[a.name]["floor"], scene.actors[a.name]["ground"])), float(starts[a.name][0][1])] for a in actors]))
    for a, g in zip(actors, gs):
        scene.actors[a.name]["ground"] = float(g)
    plan.ground = None
    for _ in range(2):    # anchors: where each character is at its beats' ends (two passes for mutual targets)
        for a in actors:
            p, yaw, spm = starts[a.name]
            t = 0.0
            an = [(0.0, p)]
            for e in _expand(a):
                b = e["beat"]
                tend = e["start"] + e["dur"]
                if b.to is not None:
                    try:
                        p = plan.spot(b.to, np.array(b.via[-1][:2], float) if b.via else p, tend, spm)
                    except (ValueError, KeyError):
                        pass
                an.append((tend, p))
            plan.anchors[a.name] = an
    # ---- generate each character's chain
    def gen_all(retry: dict) -> dict:
        results = {}
        plan_lock = threading.Lock()   # the planner's shared state and the beat cache file; generation runs outside it

        def one(a):
            p, yaw, spm = starts[a.name]
            m = scene.actors[a.name]
            old = scene.perf["actors"].get(a.name) if a.append else None
            prev = old["clips"][-1]["src"] if old and old.get("clips") else None
            clips = list(old["clips"]) if old else []
            seated = None
            occupied = []
            in_call = {x.name for x in actors}
            for other, oa in scene.perf["actors"].items():
                if other not in in_call:          # characters re-performed in this call get new seats below
                    occupied += oa.get("seats", [])
            for r in results.values():
                occupied += r["seats"]
            seats_used, beat_info = [], []
            for i, e in enumerate(_expand(a)):
                with plan_lock:
                    plan.ground = m["ground"]
                    spec, extra = _spec(e, p, yaw, spm, seated, plan, a.name, occupied)
                if retry.get((a.name, i)):
                    spec["retry"] = retry[(a.name, i)]
                key = _cache_key(a.name, spec, prev)
                hit = cache.get(key)
                if hit and (SRV.OUTPUT / hit["name"] / "root_positions.f32").exists():
                    # re-judge cached clips with the current checks: one that fails a critical one (never got up,
                    # tips over) is regenerated instead of reused
                    r_, q_ = motion.load(SRV.OUTPUT / hit["name"])
                    _, iss_now, _ = _evaluate(r_, q_, spec)
                    if any(x.startswith(("doesn't get up", "body tips over")) for x in iss_now) and not hit.get("rejudged"):
                        hit = None
                if hit and (SRV.OUTPUT / hit["name"] / "root_positions.f32").exists():
                    name, info = hit["name"], dict(hit["info"], cached=True)
                else:
                    name, info = _generate(a.name, len(clips) + 1, spec, prev)
                    cache[key] = {"name": name, "info": info, "rejudged": True}
                    with plan_lock:
                        _save_beat_cache(cache)
                warped = _warp(name, spec)
                turned = _turn(name, spec)
                if turned:
                    info = dict(info, turned_deg=turned)
                    warped = warped or 0.01
                if warped:
                    info = dict(info, warped_cm=warped)
                    r_, q_ = motion.load(SRV.OUTPUT / name)
                    _, iss, inf2 = _evaluate(r_, q_, spec)
                    info.update({k: v for k, v in inf2.items()}, issues=iss)
                    cache[key] = {"name": name, "info": info}
                    with plan_lock:
                        _save_beat_cache(cache)
                raw = SRV.OUTPUT / name
                root, rot = motion.load(raw)
                dur = (len(root) - 1) / motion.FPS
                mod = f"{a.name}_{len(clips) + 1:02d}_{hashlib.sha1((name + roblox.EXPORT_VERSION).encode()).hexdigest()[:6]}"
                clip = {"m": mod, "src": name, "s": round(e["start"], 4), "d": round(dur, 4), "x": round(float(p[0]), 4),
                        "z": round(float(p[1]), 4), "yaw": round(float(yaw), 5), "label": extra["world"]["label"]}
                if seated is not None:
                    clip["seated_start"] = True
                hips = world_hips(root, p, yaw, spm)
                clip["_hips"] = hips
                clips.append(clip)
                w = extra["world"]
                w.update(info=info, filler=e["filler"], clip=mod, src=name)
                if extra["seat"] is not None:
                    seats_used.append({"name": extra["seat"].get("name"), "u": extra["seat"].get("u", 0.0),
                                       "t": w["seat"]["span"], "top": extra["seat"].get("top"), "w": extra["seat"].get("w")})
                beat_info.append(w)
                prev = name
                p, yaw = place_next(root, rot, p, yaw, spm)
                seated = extra["seat"] if e["beat"].sit is not None else None
            track = []
            for c in clips:
                hips = c.pop("_hips", None)
                if hips is None:
                    continue
                n = len(hips)
                for f in range(0, n, 8):
                    track.append([round(c["s"] + f / motion.FPS, 3), round(float(hips[f, 0]), 3), round(float(hips[f, 1]), 3)])
                track.append([round(c["s"] + (n - 1) / motion.FPS, 3), round(float(hips[-1, 0]), 3), round(float(hips[-1, 1]), 3)])
            plan.tracks[a.name] = track
            return a.name, {"clips": clips, "beats": beat_info, "spm": spm, "end": [float(p[0]), float(p[1]), float(yaw)],
                            "seats": seats_used, "path": scene.actors[a.name]["path"], "track": track,
                            "ground": m["ground"]}

        # characters' chains are independent: generate them side by side (motiond runs several engines)
        n = max(1, min(len(actors), int(os.environ.get("MOTIOND_ENGINES", "3"))))
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(n) as ex:
            for name, r in ex.map(one, actors):
                results[name] = r
        return results

    # ---- push, check, repair: beats that clip (hands deep in the body, two bodies overlapping, the body passing
    # through scenery) or fail the engine's own checks are regenerated with new seeds (later beats of that character
    # follow, since they continue from it); the round with the fewest problems is kept.
    retry: dict = {}
    best = None
    rounds = []
    for rnd in range(REPAIR_ROUNDS + 1 if check else 1):
        results = gen_all(retry)
        push_calls = _push(scene, results)
        warnings, bad = [], {}
        if check:
            for name, r in results.items():
                warnings += _stage_checks(name, r, plan)
            body_w, body_bad = _body_checks(results)
            warnings += body_w
            for k, v in body_bad.items():
                # self-clipping on blocky R15 bodies comes from the rig's proportions, not the take: new seeds don't
                # fix it, so it is reported but doesn't trigger regeneration
                v = [x for x in v if x != "self"]
                if v:
                    bad.setdefault(k, []).extend(v)
            for name, r in results.items():
                for i, b in enumerate(r["beats"]):
                    for kind, t0, t1, _txt in r.get("flags", []):
                        if b["t0"] - 0.05 <= (t0 + t1) / 2 <= b["t1"] + 0.05:
                            bad.setdefault((name, i), []).append(kind)
                    if b["info"].get("checks_ok") is False:
                        bad.setdefault((name, i), []).append("checks")
        warnings += [f"{n} beat {i + 1} '{b['label']}': {iss}" for n, r in results.items()
                     for i, b in enumerate(r["beats"]) for iss in b["info"].get("issues", [])
                     if not any(iss.split()[0] in w and n in w and f"beat {i + 1}" in w for w in warnings)]
        n_bad = len(bad)
        rounds.append({"round": rnd, "bad_beats": n_bad, "kinds": sorted({k for v in bad.values() for k in v})})
        if best is None or n_bad < best[0]:
            best = (n_bad, results, warnings, push_calls, dict(retry))
        if n_bad == 0 or rnd == REPAIR_ROUNDS:
            break
        for k in bad:
            retry[k] = retry.get(k, 0) + 1
    n_bad, results, warnings, push_calls, used = best
    if used != retry or rounds[-1]["bad_beats"] != n_bad:   # an earlier round was better: put it back
        results = gen_all(used)
        push_calls += _push(scene, results)
    warnings = list(dict.fromkeys(warnings))
    _save_state(results)
    out = {"ok": True, "actors": {}}
    for name, r in results.items():
        f, _ = basis(r["end"][2])
        out["actors"][name] = {
            "clips": [[c["m"], c["s"], c["d"]] for c in r["clips"]],
            "ends_at": [round(r["end"][0], 1), round(r["end"][1], 1)],
            "ends_facing": _dir_name(f)}
    gen_s = [b["info"] for r in results.values() for b in r["beats"]]
    out["generated"] = sum(1 for g in gen_s if not g.get("cached"))
    out["reused"] = sum(1 for g in gen_s if g.get("cached"))
    if warnings:
        out["warnings"] = warnings[:14] + ([f"+{len(warnings) - 14} more"] if len(warnings) > 14 else [])
    out["studio"] = (f"clips in ReplicatedStorage.Promptimate.Clips; press Play to watch (autoplay) or "
                     f"roblox_record to film")
    if len(rounds) > 1:
        out["repair"] = rounds
    out["seconds"] = round(time.time() - t_all, 1)
    log = {"studio_calls": (st.calls - calls0) if st else 0, "push_calls": push_calls, "install": inst}
    (STATE / "last_perform.json").write_text(json.dumps({"out": out, "log": log, "beats": {
        n: r["beats"] for n, r in results.items()}}, indent=1, default=lambda o: np.asarray(o).tolist()))
    res = [json.dumps(out, separators=(",", ":"), ensure_ascii=False)]
    if preview:
        img = _plan_image(scene, results, warnings, plan.tracks)
        if img:
            from mcp.server.fastmcp import Image
            res.append(Image(path=str(img)))
    return res


def _dir_name(f) -> str:
    ang = math.degrees(math.atan2(f[1], f[0]))
    names = {0: "+X", 90: "+Z", 180: "-X", -180: "-X", -90: "-Z"}
    k = min(names, key=lambda a: abs(wrap(math.radians(ang - a))))
    off = math.degrees(wrap(math.radians(ang - k)))
    return names[k] if abs(off) < 12 else f"{names[k]}{off:+.0f}°"


# ================================================================================================= push to Studio
GROUND_LUAU = r'''
local HttpService = game:GetService("HttpService")
local pts = HttpService:JSONDecode(__PTS__)
local rigs = {}
for _, d in workspace:GetDescendants() do if d:IsA("Humanoid") then table.insert(rigs, d.Parent) end end
local rp = RaycastParams.new(); rp.FilterType = Enum.RaycastFilterType.Exclude; rp.FilterDescendantsInstances = rigs
local out = {}
for i, p in pts do
  local h = workspace:Raycast(Vector3.new(p[1], p[2] + 0.6, p[3]), Vector3.new(0, -60, 0), rp)
  out[i] = h and h.Position.Y or p[2]
end
return HttpService:JSONEncode(out)
'''


def _push_offline(scene: Scene, results: dict) -> int:
    """_push without Studio: clip heights from our own geometry, clip files exported locally, the cue sheet handed
    to the staging backend (its probes and body checks pose from it)."""
    for r in results.values():
        refs = [c for c in r["clips"] if "y" not in c]
        if refs:
            ys = WORLD.ground([[c["x"], r["ground"], c["z"]] for c in refs])
            raw = {id(c): float(y) for c, y in zip(refs, ys)}
            prev_y = r["ground"]
            for k, c in enumerate(r["clips"]):
                if id(c) not in raw:
                    prev_y = c["y"]
                    continue
                y = raw[id(c)]
                if k > 0 and (c.get("seated_start") or abs(y - prev_y) > 0.6):
                    y = prev_y
                c["y"] = round(y, 4)
                prev_y = c["y"]
    out_dir = STATE / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in results.values():
        for c in r["clips"]:
            f = out_dir / f"{c['m']}.json"
            if not f.exists():
                roblox.export(SRV.OUTPUT / c["src"], f, c["m"])
    perf = scene.perf
    perf["version"] = 1
    for name, r in results.items():
        perf["actors"][name] = {"path": r["path"], "spm": round(r["spm"], 4),
                                "clips": [{k: v for k, v in c.items() if k in ("m", "src", "s", "d", "x", "y", "z", "yaw", "label", "seated_start")}
                                          for c in r["clips"]],
                                "end": [round(v, 4) for v in r["end"]], "track": r["track"], "seats": r["seats"]}
    WORLD.perf_actors = {n: {"clips": a["clips"]} for n, a in perf["actors"].items() if n in WORLD.cast}
    return 0


def _push(scene: Scene, results: dict) -> int:
    if WORLD is not None:
        return _push_offline(scene, results)
    st = studio()
    calls = 0
    # ground height under every clip origin
    # (first clip: the ground under the start; later clips: the ground just below the previous clip's floor, so a
    # bench under a seated character isn't taken for the floor; a clip that starts seated keeps the floor)
    pts, refs = [], []
    for r in results.values():
        for c in r["clips"]:
            if "y" not in c:
                pts.append([c["x"], r["ground"], c["z"]])
                refs.append(c)
    if pts:
        ys = st.luau_json(GROUND_LUAU.replace("__PTS__", long_str(json.dumps(pts))))
        calls += 1
        raw = {id(c): float(y) for c, y in zip(refs, ys)}
        for r in results.values():
            prev_y = r["ground"]
            for k, c in enumerate(r["clips"]):
                if "y" in c and id(c) not in raw:
                    prev_y = c["y"]
                    continue
                y = raw[id(c)]
                if k > 0 and (c.get("seated_start") or abs(y - prev_y) > 0.6):
                    y = prev_y
                c["y"] = round(y, 4)
                prev_y = c["y"]
    # clip modules (only those not already in the place)
    have = set(json.loads(st.luau(
        'local f = game:GetService("ReplicatedStorage").Promptimate:FindFirstChild("Clips")\nlocal t = {}\n'
        'if f then for _, m in f:GetChildren() do table.insert(t, m.Name) end end\n'
        'return game:GetService("HttpService"):JSONEncode(t)')))
    calls += 1
    mods = {}
    out_dir = STATE / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    for r in results.values():
        for c in r["clips"]:
            if c["m"] in have:
                continue
            path = roblox.export(SRV.OUTPUT / c["src"], out_dir / f"{c['m']}.json", c["m"])
            mods.update(chunk_module(c["m"], path.read_text(), CLIPS_PATH))
    if mods:
        calls += st.upload(mods, folder="Clips")
    # cue sheet
    perf = scene.perf
    perf["version"] = 1
    for name, r in results.items():
        perf["actors"][name] = {"path": r["path"], "spm": round(r["spm"], 4),
                                "clips": [{k: v for k, v in c.items() if k in ("m", "src", "s", "d", "x", "y", "z", "yaw", "label", "seated_start")}
                                          for c in r["clips"]],
                                "end": [round(v, 4) for v in r["end"]], "track": r["track"], "seats": r["seats"]}
    used = {c["m"] for a in perf["actors"].values() for c in a["clips"]}
    st.luau(f'''
local HttpService = game:GetService("HttpService")
local f = game:GetService("ReplicatedStorage").Promptimate
local m = f:FindFirstChild("Performance") or Instance.new("ModuleScript")
m.Name = "Performance"; m.Source = "return " .. {json.dumps(long_str(json.dumps(perf, separators=(",", ":"))))}; m.Parent = f
local used = {{}}
for _, n in HttpService:JSONDecode({long_str(json.dumps(sorted(used)))}) do used[n] = true end
local removed = 0
for _, c in f.Clips:GetChildren() do
  local base = string.gsub(c.Name, "__%d+$", "")
  if not used[base] then c:Destroy(); removed += 1 end
end
local D = require(f.ShortDirector:Clone())
_G.PromptimateDirector = D
D.load(); D.seek(0)
return removed''')
    calls += 1
    return calls


# ================================================================================================= staging checks
def _runs(flags: list[bool], times: list[float], min_len: float) -> list[tuple[float, float]]:
    out, s = [], None
    for f, t in zip(flags + [False], times + [times[-1] if times else 0]):
        if f and s is None:
            s = t
        elif not f and s is not None:
            if t - s >= min_len - 1e-6:
                out.append((s, t))
            s = None
    return out


def _stage_checks(name: str, r: dict, plan: Planner) -> list[str]:
    """In-place checks of one character's performance on its real rig, everyone else posed at the same time."""
    beats = r["beats"]
    t0, t1 = r["clips"][0]["s"], r["clips"][-1]["s"] + r["clips"][-1]["d"]
    times = [round(t, 3) for t in np.arange(t0, t1, 0.25)]
    ends = [round(b["t1"] - 0.04, 3) for b in beats]
    times = sorted(set(times + ends))
    seats = {s["name"]: s["top"] for s in r["seats"] if s.get("name") and s.get("top") is not None}
    data = []
    for i in range(0, len(times), 120):     # batches: Studio truncates tool output at 100k characters
        if WORLD is not None:
            data += WORLD.probe(name, times[i:i + 120], {"seats": seats})
            continue
        data += studio().luau_json(
            "local D = _G.PromptimateDirector or require(game:GetService('ReplicatedStorage').Promptimate.ShortDirector:Clone())\n"
            f"return D.probe({json.dumps(name)}, {{{','.join(map(str, times[i:i + 120]))}}}, "
            f"game:GetService('HttpService'):JSONDecode({long_str(json.dumps({'seats': seats}))}))")
    spm = r["spm"]
    by_t = {round(d["t"], 3): d for d in data}
    warn = []

    def seated_at(t):
        return any(s["t"][0] - 0.3 <= t <= s["t"][1] + 0.3 for s in r["seats"])

    ts = [d["t"] for d in data]
    # floating (whole body above the ground) / sinking into the ground
    gap = [d["low"] - d["gF"] for d in data]
    fl = _runs([g > 0.35 * spm / 2.14 + 0.2 and not seated_at(d["t"]) for g, d in zip(gap, data)], ts, 0.5)
    arms = {"LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm", "RightLowerArm", "RightHand", "Left Arm", "Right Arm"}
    # lying / crawling: the R15 arm boxes' corners dip into the floor by design; not something a beat edit fixes
    sk = _runs([g < -0.35 and not (d["lowPart"] in arms and d["hips"][1] - d["gF"] < 0.6 * spm)
                for g, d in zip(gap, data)], ts, 0.25)
    for a, b in fl[:2]:
        g = max(gg for gg, d in zip(gap, data) if a <= d["t"] <= b)
        warn.append(f"{name} floats {g:.1f} studs above the ground at {a:.1f}-{b:.1f}s")
    for a, b in sk[:2]:
        g = min(gg for gg, d in zip(gap, data) if a <= d["t"] <= b)
        part = min((d for d in data if a <= d["t"] <= b), key=lambda d: d["low"] - d["gF"])["lowPart"]
        warn.append(f"{name}'s {part} sinks {-g:.1f} studs into the ground at {a:.1f}-{b:.1f}s")
    # ground height under the feet differs from the clip's floor (steps, curbs, slopes)
    # collisions with props/scenery
    hits: dict[str, list[float]] = {}
    for d in data:
        for h in d["hits"]:
            hits.setdefault(h, []).append(d["t"])
    shown = 0
    for h, tl in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        runs = _runs([any(abs(t - x) < 1e-6 for x in tl) for t in ts], ts, 0.25)
        for a, b in runs:
            r.setdefault("flags", []).append(("scenery", a, b, h))
        if runs and shown < 3:
            shown += 1
            warn.append(f"{name}'s body passes through {h} at " + ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in runs[:3]))
    # seats: thighs resting on the seat top
    for s in r["seats"]:
        if s.get("top") is None:
            continue
        vals = [by_t[t]["thigh"] - s["top"] for t in times if s["t"][0] + 0.3 <= t <= s["t"][1] - 0.1 and t in by_t]
        if vals:
            m = float(np.median(vals))
            if m > 0.35:
                warn.append(f"{name} hovers {m:.1f} studs above {s['name']} ({s['t'][0]:.1f}-{s['t'][1]:.1f}s)")
            elif m < -0.4:
                warn.append(f"{name} sinks {-m:.1f} studs into {s['name']} ({s['t'][0]:.1f}-{s['t'][1]:.1f}s)")
    # sitting over the seat, not beside it or past its end
    for b in beats:
        ax = (b.get("seat") or {}).get("axis")
        if not ax:
            continue
        cx, cz, lx, lz, half = ax
        a0, a1 = b["seat"]["span"]
        offs = [abs((by_t[t]["hips"][0] - cx) * lx + (by_t[t]["hips"][2] - cz) * lz) - half
                for t in times if a0 + 0.3 <= t <= a1 - 0.1 and t in by_t]
        if offs and max(offs) > 0.1:
            warn.append(f"{name} sits {max(offs):.1f} studs past the end of {b['seat']['name']} ({a0:.1f}-{a1:.1f}s)")
    for b in beats:
        for n in b.get("notes", []):
            warn.append(f"{name}: {n}")
    # end facing, measured on the rig
    for i, b in enumerate(beats):
        if b.get("face") is None:
            continue
        d = by_t.get(round(b["t1"] - 0.04, 3))
        if not d:
            continue
        at = np.array([d["hips"][0], d["hips"][2]])
        want = plan.direction(b["face"], at, b["t1"])
        look = np.array(d["look"], float)
        look /= np.linalg.norm(look) + 1e-9
        err = math.degrees(math.acos(float(np.clip(look @ want, -1, 1))))
        b["face_err_rig"] = round(err, 1)
        if err > FACE_TOL + 5:
            tgt = b["face"] if isinstance(b["face"], str) else str(b["face"])
            warn.append(f"{name} beat {i + 1} '{b['label']}' ends facing {err:.0f} deg away from {tgt}")
    # standing inside another character
    for other, tr in plan.tracks.items():
        if other == name or not tr:
            continue
        ot = [x[0] for x in tr]
        close = []
        for d in data:
            if not (ot[0] <= d["t"] <= ot[-1]):
                continue
            ox, oz = np.interp(d["t"], ot, [x[1] for x in tr]), np.interp(d["t"], ot, [x[2] for x in tr])
            close.append(math.hypot(d["hips"][0] - ox, d["hips"][2] - oz) < 0.38 * spm)
        rr = _runs(close, [d["t"] for d in data if ot[0] <= d["t"] <= ot[-1]], 0.25)
        if rr:
            warn.append(f"{name} and {other} overlap at {rr[0][0]:.1f}-{rr[0][1]:.1f}s")
    return warn


def _body_checks(results: dict) -> tuple[list[str], dict]:
    """Clipping between body parts, on the real rigs in Studio (PromptimatePlayer's arm push-out applied): a forearm
    or hand deep in its own torso/head/thighs, and two characters' parts overlapping. Returns (warnings,
    {(actor, beat index): [kinds]})."""
    t1 = max(c["s"] + c["d"] for r in results.values() for c in r["clips"])
    times = [round(t, 2) for t in np.arange(0, t1, 0.2)]
    data = []
    for i in range(0, len(times), 40):      # batches: Studio truncates tool output at 100k characters
        if WORLD is not None:
            data += WORLD.bodycheck(times[i:i + 40])
            continue
        data += studio().luau_json(
            "local D = _G.PromptimateDirector or require(game:GetService('ReplicatedStorage').Promptimate.ShortDirector:Clone())\n"
            "_G.PromptimateDirector = D; D.options = nil" + ("; D.load()" if i == 0 else "") + "\n"
            f"return D.bodycheck({{{','.join(map(str, times[i:i + 40]))}}})", timeout=900)
    ts = [d["t"] for d in data]
    warn, bad = [], {}

    def beat_at(name, t):
        for i, b in enumerate(results[name]["beats"]):
            if b["t0"] - 1e-6 <= t <= b["t1"] + 1e-6:
                return i
        return None

    for name, r in results.items():
        v = [(d["self"] or {}).get(name, 0.0) if isinstance(d["self"], dict) else 0.0 for d in data]
        for i, b in enumerate(r["beats"]):
            sel = [x for t, x in zip(ts, v) if b["t0"] <= t <= b["t1"]]
            if sel and sum(x > SELF_BAD for x in sel) / len(sel) > 0.15:
                bad.setdefault((name, i), []).append("self")
                warn.append(f"{name} beat {i + 1} '{b['label']}': hands sink into the body "
                            f"({sum(x > SELF_BAD for x in sel) / len(sel) * 100:.0f}% of the beat, up to "
                            f"{max(sel) * 100:.0f}% of a forearm hidden)")
    pairs = sorted({k for d in data if isinstance(d["pair"], dict) for k in d["pair"]})
    for pk in pairs:
        v = [(d["pair"].get(pk, 0.0) if isinstance(d["pair"], dict) else 0.0) for d in data]
        for a, b in _runs([x > PAIR_BAD for x in v], ts, 0.2):
            na, nb = pk.split("|")
            for n in (na, nb):
                if n in results:
                    i = beat_at(n, (a + b) / 2)
                    if i is not None:
                        bad.setdefault((n, i), []).append("pair")
            warn.append(f"{na} and {nb}: bodies overlap at {a:.1f}-{b:.1f}s (up to "
                        f"{max(x for t, x in zip(ts, v) if a <= t <= b):.1f} studs)")
    for name, r in results.items():     # limbs inside walls/counters/props
        hit = [(d["t"], (d.get("prop") or {}).get(name)) if isinstance(d.get("prop"), dict) else (d["t"], None) for d in data]
        for a, b in _runs([w is not None for _t, w in hit], ts, 0.3):
            what = next(w for t, w in hit if a <= t <= b and w)
            i = beat_at(name, (a + b) / 2)
            if i is not None:
                bad.setdefault((name, i), []).append("prop")
            warn.append(f"{name} passes through {what} at {a:.1f}-{b:.1f}s")
    return warn, bad


def _save_state(results: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    p = STATE / "state.json"
    s = json.loads(p.read_text()) if p.exists() else {"actors": {}}
    for name, r in results.items():
        s["actors"][name] = {"clips": r["clips"], "spm": r["spm"], "track": r["track"], "end": r["end"]}
    p.write_text(json.dumps(s, indent=0))


def load_state() -> dict:
    p = STATE / "state.json"
    return json.loads(p.read_text()) if p.exists() else {"actors": {}}


# ================================================================================================= preview image
COLORS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2"]


def _plan_image(scene: Scene, results: dict, warnings: list[str], others: dict | None = None) -> Path | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon
    except Exception:
        return None
    pts = np.concatenate([np.array([[x[1], x[2]] for x in r["track"]]) for r in results.values() if r["track"]])
    lo, hi = pts.min(0) - 8, pts.max(0) + 8
    span = max(hi - lo)
    c = (lo + hi) / 2
    lo, hi = c - span / 2, c + span / 2
    fig = plt.figure(figsize=(9.6, 4.8), dpi=80)
    ax = fig.add_axes([0.04, 0.06, 0.46, 0.9])
    for cx, cz, sx, sz, yaw, top in scene.parts:
        if not (lo[0] - 10 < cx < hi[0] + 10 and lo[1] - 10 < cz < hi[1] + 10):
            continue
        ca, sa = math.cos(yaw), math.sin(yaw)
        corners = [(cx + ca * u * sx / 2 + sa * v * sz / 2, cz - sa * u * sx / 2 + ca * v * sz / 2)
                   for u, v in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        shade = 0.55 + 0.4 * (1 - min(1.0, max(0.0, top) / 12))
        ax.add_patch(Polygon(corners, closed=True, fc=(shade, shade, shade), ec="none", alpha=0.7, zorder=1))
    for name, tr in (others or {}).items():      # everyone else's blocking, faint, for context
        if name in results or not tr:
            continue
        a = np.array([[x[1], x[2]] for x in tr])
        if not ((a >= lo - 10) & (a <= hi + 10)).all(axis=1).any():
            continue
        ax.plot(a[:, 0], a[:, 1], ":", color="#888888", lw=1.2, zorder=2)
        ax.text(a[-1, 0], a[-1, 1], name, fontsize=6, color="#666666", zorder=2)
    for k, (name, r) in enumerate(results.items()):
        col = COLORS[k % len(COLORS)]
        tr = np.array([[x[1], x[2]] for x in r["track"]])
        ax.plot(tr[:, 0], tr[:, 1], "-", color=col, lw=2, zorder=3, label=name)
        ax.plot(*tr[0], "o", color=col, ms=6, zorder=4)
        ts = [x[0] for x in r["track"]]
        for i, b in enumerate(r["beats"]):
            if b.get("filler"):
                continue
            x = np.interp(b["t1"], ts, tr[:, 0])
            z = np.interp(b["t1"], ts, tr[:, 1])
            ax.text(x, z, str(i + 1), fontsize=7, color="white", ha="center", va="center", zorder=6,
                    bbox=dict(boxstyle="circle,pad=0.15", fc=col, ec="none"))
        f, _ = basis(r["end"][2])
        ax.arrow(r["end"][0], r["end"][1], f[0] * 2.5, f[1] * 2.5, color=col, width=0.25, zorder=5)
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(hi[1], lo[1])            # +Z down, like Studio's top view with the camera facing -Z
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ax.set_title("plan (studs, top view; numbers = beat ends, arrow = end facing)", fontsize=8)
    ax.legend(fontsize=7, loc="upper right")
    # timeline
    tx = fig.add_axes([0.55, 0.06, 0.43, 0.9])
    names = list(results)
    tmax = max(r["clips"][-1]["s"] + r["clips"][-1]["d"] for r in results.values())
    for k, name in enumerate(names):
        r = results[name]
        col = COLORS[k % len(COLORS)]
        for i, b in enumerate(r["beats"]):
            y = len(names) - 1 - k
            tx.barh(y, b["t1"] - b["t0"], left=b["t0"], color=col if not b.get("filler") else "#cccccc",
                    alpha=0.85 if not b["info"].get("issues") else 0.45, edgecolor="white", height=0.7)
            if b["t1"] - b["t0"] > 1.2:
                tx.text(b["t0"] + 0.1, y + 0.05, f"{i + 1} {b['label'][:int((b['t1'] - b['t0']) * 2.6)]}", fontsize=6,
                        va="center", color="white" if not b.get("filler") else "#444")
    tx.set_yticks(range(len(names)))
    tx.set_yticklabels(list(reversed(names)), fontsize=8)
    tx.set_xlim(0, tmax)
    tx.tick_params(labelsize=7)
    tx.set_title(f"timeline (s) — {len(warnings)} staging warning(s)", fontsize=8)
    out = STATE / "perform_plan.png"
    STATE.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
    return out


# ================================================================================================= registration
PERFORM_DOC = """Animate characters in the open Roblox Studio place from a shot list: one call per character (or
several characters at once). Each beat is generated with Promptimate (local text-to-motion) as one connected chain
(each clip starts in the previous clip's last pose), with movement, seats and end facing resolved in the place's own
coordinates, then pushed straight into Studio (ReplicatedStorage.Promptimate) with a director that plays it.
Use it for every character performance and any action beyond plain walking/idling.

Beats: prompt = what the body does ('a person runs forward, then stops'; 'a person sits and holds a phone to their
right ear with their right hand'), one or two actions per segment, 2-3 s for a single action (wave, jump, fall),
longer for continuous activity; a list of prompts/seconds = segments within the beat. at = story time (default:
after the previous beat; gaps become idling). to = where it ends up ([x, z] studs, 'Bench', 'Officer', 'Crates:+X';
stops short of objects/people); via = waypoints; face = facing at the end (name, point or '+X'/'-Z'); sit = object
name or seat height (studs), seated from sit_from to the end, repeat on following beats to stay seated, drop to
stand up (two characters on one bench get separate spots automatically); peek = 'left'|'right' lean/step out from
cover. Known limits: ~3 m/s top speed, no fingers/props, fine manner (shiver, foot taps) is weak.

Returns only a short summary (clip names, start/duration, end positions, staging warnings: wrong end facing,
floating/sinking, passing through props, hovering over a seat, characters overlapping) and a plan image. Fix
warnings by editing the beat (to/face/sit/at or the prompt) and calling again: unchanged beats are reused, so only
the edited beat and the ones after it are regenerated. Re-calling with a character replaces its chain (append=true
continues it). Then press Play (the director autoplays) or call roblox_record."""


def register(mcp, server_module):
    global SRV
    SRV = server_module
    import anyio

    @mcp.tool(description=PERFORM_DOC)
    async def roblox_perform(actors: list[Actor], check: bool = True, preview: bool = True) -> list:
        return await anyio.to_thread.run_sync(lambda: perform(actors, check, preview))

    @mcp.tool()
    async def roblox_install(force: bool = False) -> str:
        """Install (or update) the Promptimate package in the open Roblox Studio place: PromptimatePlayer and
        ShortDirector in ReplicatedStorage.Promptimate, plus PromptimateAutoplay scripts so pressing Play performs
        every character's chain (Play mode on the client, Run mode on the server). roblox_perform does this
        automatically; call it to repair or to reinstall after an update."""
        return json.dumps(await anyio.to_thread.run_sync(lambda: install(force)))

    import roblox_record
    roblox_record.register(mcp, server_module)
