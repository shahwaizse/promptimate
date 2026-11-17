"""Studio -> headless scene: one static dump of the world (parts, meshes, unions, decals) plus a per-frame dump of
everything that moves (character parts, accessories, episode props), as position + quaternion float32.

    scene = export_static(out)          # once per place edit (sets are reused across episodes)
    dyn = export_dynamic(out, fps, t0, t1)   # per episode, after roblox_perform: ~2 ms of posing per frame

Studio only poses; it renders nothing, so this runs at Luau speed, not at Studio's frame rate."""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio_io as S  # noqa: E402

# per part: kind, size, cframe (pos + 3x3), colour, material, transparency, reflectance, mesh info, decals
PART_LUAU = r'''
local SHAPE = { [Enum.PartType.Block] = "box", [Enum.PartType.Ball] = "ball", [Enum.PartType.Cylinder] = "cyl",
  [Enum.PartType.Wedge] = "wedge", [Enum.PartType.CornerWedge] = "cwedge" }
local function face(e) return e.Name end
local function info(p)
  local kind, mesh = "box", nil
  if p:IsA("MeshPart") then kind = "mesh"; mesh = { size = { p.MeshSize.X, p.MeshSize.Y, p.MeshSize.Z }, id = p.MeshId, tex = p.TextureID }
  elseif p:IsA("UnionOperation") then
    kind = "union"
    local ok, ms = pcall(function() return p.MeshSize end)
    mesh = { size = ok and { ms.X, ms.Y, ms.Z } or nil, partColor = p.UsePartColor }
  elseif p:IsA("WedgePart") then kind = "wedge"
  elseif p:IsA("CornerWedgePart") then kind = "cwedge"
  elseif p:IsA("TrussPart") then kind = "box"
  elseif p:IsA("Part") then kind = SHAPE[p.Shape] or "box" end
  local sm = p:FindFirstChildOfClass("SpecialMesh")
  if sm then
    mesh = mesh or {}
    mesh.special = { type = sm.MeshType.Name, scale = { sm.Scale.X, sm.Scale.Y, sm.Scale.Z },
      offset = { sm.Offset.X, sm.Offset.Y, sm.Offset.Z }, id = sm.MeshId, tex = sm.TextureId }
    -- a FileMesh's real dimensions (the part's size says nothing): a MeshPart built from the id reports them
    if sm.MeshType == Enum.MeshType.FileMesh and sm.MeshId ~= "" then
      _G.PromptimateMeshSize = _G.PromptimateMeshSize or {}
      local ms = _G.PromptimateMeshSize[sm.MeshId]
      if ms == nil then
        local ok, mp = pcall(function() return game:GetService("AssetService"):CreateMeshPartAsync(Content.fromUri(sm.MeshId)) end)
        ms = ok and { mp.MeshSize.X, mp.MeshSize.Y, mp.MeshSize.Z } or false
        _G.PromptimateMeshSize[sm.MeshId] = ms
      end
      mesh.special.meshSize = ms or nil
    end
  end
  local decals = {}
  for _, d in p:GetChildren() do
    if d:IsA("Decal") then
      table.insert(decals, { face = face(d.Face), tex = d.Texture, color = { d.Color3.R, d.Color3.G, d.Color3.B },
        tr = d.Transparency, tile = d:IsA("Texture") and { d.StudsPerTileU, d.StudsPerTileV } or nil })
    end
  end
  local c = p.CFrame
  local x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 = c:GetComponents()
  return { kind = kind, size = { p.Size.X, p.Size.Y, p.Size.Z },
    cf = { x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 },
    color = { p.Color.R, p.Color.G, p.Color.B }, mat = p.Material.Name, tr = p.Transparency, refl = p.Reflectance,
    shadow = p.CastShadow, cc = p.CanCollide, cq = p.CanQuery, block = p:IsA("Part") and p.Shape == Enum.PartType.Block,
    mesh = mesh, decals = (#decals > 0) and decals or nil }
end
'''

STATIC = PART_LUAU + r'''
local skip = {}
for _, d in workspace:GetDescendants() do
  if d:IsA("Humanoid") then skip[d.Parent] = true end
end
local ep = workspace:FindFirstChild("Sets") and workspace.Sets:FindFirstChild("EpisodeProps")
local out = {}
local function walk(inst)
  for _, c in inst:GetChildren() do
    if skip[c] or c == ep or c:IsA("Camera") or c:IsA("Terrain") then continue end
    if c:IsA("BasePart") and c.Transparency < 0.98 then
      local ok, r = pcall(info, c)
      if ok then r.name = c.Name; r.path = c:GetFullName(); table.insert(out, r) end
    end
    walk(c)
  end
end
walk(workspace)
local L = game:GetService("Lighting")
local sun = L:GetSunDirection()
local light = { sun = { sun.X, sun.Y, sun.Z }, ambient = { L.Ambient.R, L.Ambient.G, L.Ambient.B },
  outdoor = { L.OutdoorAmbient.R, L.OutdoorAmbient.G, L.OutdoorAmbient.B }, brightness = L.Brightness,
  exposure = L.ExposureCompensation }
_G.PromptimateSend("static", game:GetService("HttpService"):JSONEncode({ parts = out, light = light }))
'''

# the moving set: every part of every actor rig (accessories included) and every episode prop; clothing per actor
DYN_LIST = PART_LUAU + r'''
local D = _G.PromptimateDirector
local list, actors = {}, {}
_G.PromptimateDyn = {}
local function add(p, owner)
  local ok, r = pcall(info, p)
  if ok then r.name = p.Name; r.owner = owner; table.insert(list, r); table.insert(_G.PromptimateDyn, p) end
end
local names = {}
for name, a in D.actors do table.insert(names, name) end
table.sort(names)
for _, name in names do
  local rig = D.actors[name].rig
  local shirt, pants = rig:FindFirstChildOfClass("Shirt"), rig:FindFirstChildOfClass("Pants")
  local tee = rig:FindFirstChildOfClass("ShirtGraphic")
  actors[name] = { shirt = shirt and shirt.ShirtTemplate or "", pants = pants and pants.PantsTemplate or "",
    tee = tee and tee.Graphic or "", first = #list + 1 }
  for _, p in rig:GetDescendants() do
    if p:IsA("BasePart") and p.Name ~= "HumanoidRootPart" and p.Transparency < 0.98 then add(p, name) end
  end
  actors[name].last = #list
end
local ep = workspace:FindFirstChild("Sets") and workspace.Sets:FindFirstChild("EpisodeProps")
if ep then
  for _, p in ep:GetDescendants() do
    if p:IsA("BasePart") and p.Transparency < 0.98 then add(p, "prop:" .. (p:FindFirstAncestorOfClass("Model") or p).Name) end
  end
end
_G.PromptimateDynNames = names
_G.PromptimateSend("dynlist", game:GetService("HttpService"):JSONEncode({ parts = list, actors = actors, order = names }))
'''

# per frame: 7 float32 per moving part (position, quaternion x y z w) and one byte per actor (face expression)
DYN_FRAMES = r'''
local D = _G.PromptimateDirector
local E = game:GetService("EncodingService")
local parts, names = _G.PromptimateDyn, _G.PromptimateDynNames
local k0, k1, fps = __K0__, __K1__, __FPS__
local FACES = __FACES__
local fidx = {}
for i, f in FACES do fidx[f] = i end
local n = #parts
local per = n * 28 + #names
local CH = math.max(1, math.floor(700000 / per))      -- frames per POST (<1 MB base64)
local k = k0
while k <= k1 do
  local m = math.min(CH, k1 - k + 1)
  local b = buffer.create(m * per)
  local o = 0
  for j = 0, m - 1 do
    D.seek((k + j) / fps)
    for i = 1, n do
      local c = parts[i].CFrame
      local p = c.Position
      local ax, ang = c:ToAxisAngle()
      local s = math.sin(ang / 2)
      buffer.writef32(b, o, p.X); buffer.writef32(b, o + 4, p.Y); buffer.writef32(b, o + 8, p.Z)
      buffer.writef32(b, o + 12, ax.X * s); buffer.writef32(b, o + 16, ax.Y * s); buffer.writef32(b, o + 20, ax.Z * s)
      buffer.writef32(b, o + 24, math.cos(ang / 2))
      o += 28
    end
    for _, name in names do
      buffer.writeu8(b, o, fidx[D.actors[name].rig:GetAttribute("PromptimateFace") or "neutral"] or 0); o += 1
    end
  end
  _G.PromptimateSend("f" .. k, buffer.tostring(E:Base64Encode(b)))
  k += m
end
return CH
'''

FACES = ["neutral", "happy", "grin", "sad", "crying", "shocked", "scared", "angry", "smug", "tired", "wink",
         "sleeping", "love"]


def export_static(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    t = time.time()
    body = S.luau_send(STATIC, "static")
    (out / "static.json").write_bytes(body)
    d = json.loads(body)
    print(f"static: {len(d['parts'])} parts in {time.time() - t:.1f}s", flush=True)
    return d


def export_dynamic(out: Path, fps: int, t0: float, t1: float, step: int = 1) -> dict:
    """Pose every moving part at frames k0..k1 (every `step`-th frame; the renderer interpolates the rest)."""
    out.mkdir(parents=True, exist_ok=True)
    t = time.time()
    s = S.sink()
    lst = json.loads(S.luau_send(DYN_LIST, "dynlist"))
    (out / "dynamic.json").write_text(json.dumps(lst))
    n, na = len(lst["parts"]), len(lst["order"])
    k0, k1 = int(round(t0 * fps)), int(t1 * fps)
    fps_eff = fps / step
    code = (S.SEND + DYN_FRAMES.replace("__K0__", str(int(round(t0 * fps_eff)))).replace("__K1__", str(int(t1 * fps_eff)))
            .replace("__FPS__", repr(fps_eff)).replace("__FACES__", "{" + ",".join(f'"{f}"' for f in FACES) + "}"))
    from roblox_studio import studio
    ch = int(studio().luau(code, timeout=1800))
    ks = list(range(int(round(t0 * fps_eff)), int(t1 * fps_eff) + 1, ch))
    per = n * 28 + na
    poses, faces = [], []
    for k in ks:
        raw = base64.b64decode(s.take(f"f{k}"))
        m = len(raw) // per
        a = np.frombuffer(raw, np.uint8).reshape(m, per)
        poses.append(a[:, :n * 28].copy().view(np.float32).reshape(m, n, 7))
        faces.append(a[:, n * 28:].copy())
    P = np.concatenate(poses)
    F = np.concatenate(faces)
    np.savez(out / "frames.npz", pose=P, face=F, fps=fps_eff, t0=t0)
    print(f"dynamic: {n} parts x {len(P)} frames ({fps_eff:g} fps) in {time.time() - t:.1f}s", flush=True)
    return {"parts": n, "frames": len(P), "seconds": time.time() - t}


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:\tmp\headless\scene")
    export_static(out)
