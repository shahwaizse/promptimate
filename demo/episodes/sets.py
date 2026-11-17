"""Episode sets from free Creator Store models: insert by asset id (Studio MCP insert_asset), strip scripts and sounds,
anchor, and move into its own lot (workspace.Sets.<name>) so sets don't overlap the town or each other.

    .venv\\Scripts\\python.exe demo\\episodes\\sets.py insert <name> <assetId> <x> <z> [yaw]
    .venv\\Scripts\\python.exe demo\\episodes\\sets.py info <name>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server"))

PLACE = r'''
local HttpService = game:GetService("HttpService")
local a = HttpService:JSONDecode(__ARGS__)
local sets = workspace:FindFirstChild("Sets") or Instance.new("Folder"); sets.Name = "Sets"; sets.Parent = workspace
-- the asset insert_asset just dropped in (newest top-level model that isn't one of ours)
-- everything insert_asset dropped at the top level becomes one set model
local m = Instance.new("Model"); m.Name = a.name
local found = 0
for _, n in a.inserted do
  local c = workspace:FindFirstChild(n)
  if c then c.Parent = m; found += 1 end
end
if found == 0 then return HttpService:JSONEncode({ error = "inserted model not found" }) end
m.Parent = workspace
local old = sets:FindFirstChild(a.name); if old then old:Destroy() end
local removed = 0
for _, d in m:GetDescendants() do
  if d:IsA("BaseScript") or d:IsA("ModuleScript") or d:IsA("Sound") or d:IsA("ProximityPrompt") or d:IsA("ClickDetector") then
    d:Destroy(); removed += 1
  elseif d:IsA("BasePart") then d.Anchored = true end
end
local model = m
model.Parent = sets
local cf, size = model:GetBoundingBox()
local base = Vector3.new(cf.X, cf.Y - size.Y / 2, cf.Z)
model:PivotTo(CFrame.new(a.x, 0.1 + (cf.Y - size.Y / 2 - base.Y), a.z) * CFrame.Angles(0, math.rad(a.yaw or 0), 0) * (cf - cf.Position):Inverse() * (model:GetPivot() - model:GetPivot().Position))
-- drop so the lowest point sits on the ground (y = 0.1)
local cf2, size2 = model:GetBoundingBox()
model:PivotTo(model:GetPivot() + Vector3.new(a.x - cf2.X, 0.1 - (cf2.Y - size2.Y / 2), a.z - cf2.Z))
cf2, size2 = model:GetBoundingBox()
return HttpService:JSONEncode({ name = a.name, centre = { cf2.X, cf2.Y, cf2.Z }, size = { size2.X, size2.Y, size2.Z }, removed = removed })'''


def insert(name: str, asset_id: str, x: float, z: float, yaw: float = 0) -> dict:
    from roblox_studio import studio
    st = studio()
    before = set(json.loads(st.luau('local t = {} for _, c in workspace:GetChildren() do table.insert(t, c.Name) end '
                                    'return game:GetService("HttpService"):JSONEncode(t)')))
    r = st.call("insert_asset", {"assetId": str(asset_id), "assetType": "Model", "assetName": name})
    if r.get("isError"):
        return {"error": str(r)[:400]}
    after = json.loads(st.luau('local t = {} for _, c in workspace:GetChildren() do table.insert(t, c.Name) end '
                               'return game:GetService("HttpService"):JSONEncode(t)'))
    new = [n for n in after if n not in before] or [after[-1]]
    args = {"inserted": new, "name": name, "x": x, "z": z, "yaw": yaw}
    return st.luau_json(PLACE.replace("__ARGS__", json.dumps(json.dumps(args))))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "insert":
        print(insert(sys.argv[2], sys.argv[3], float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6]) if len(sys.argv) > 6 else 0))


# ------------------------------------------------------------------ props: a library of sourced models, placed per episode
# Library: ServerStorage.PromptimateProps.<key> (scripts/sounds stripped, anchored, pivot at the bottom centre, scaled
# to a real-world height in studs). Episodes list PLACE = [{"prop": key, "at": [x, z], "y": floor (optional, else
# raycast), "yaw": deg, "height": studs (optional), "name": unique name}] and produce.py puts clones under
# workspace.Sets.EpisodeProps (rebuilt every cast step), so PROPS cues can show/hide/attach them by path.
LIB = r'''
local HttpService = game:GetService("HttpService")
local a = HttpService:JSONDecode(__ARGS__)
local SS = game:GetService("ServerStorage")
local lib = SS:FindFirstChild("PromptimateProps") or Instance.new("Folder"); lib.Name = "PromptimateProps"; lib.Parent = SS
local m = Instance.new("Model"); m.Name = a.key
local found = 0
for _, n in a.inserted do
  local c = workspace:FindFirstChild(n)
  if c then c.Parent = m; found += 1 end
end
if found == 0 then return HttpService:JSONEncode({ error = "inserted model not found" }) end
local removed, parts = 0, 0
for _, d in m:GetDescendants() do
  if d:IsA("LuaSourceContainer") or d:IsA("Sound") or d:IsA("ProximityPrompt") or d:IsA("ClickDetector")
     or d:IsA("Humanoid") and not a.keepHumanoid then
    d:Destroy(); removed += 1
  elseif d:IsA("BasePart") then d.Anchored = true; d.CanCollide = false; parts += 1 end
end
if a.rot then   -- some uploads lie on their side: stand them up before measuring
  local c0 = m:GetBoundingBox()
  m:PivotTo(CFrame.new(c0.Position) * CFrame.Angles(math.rad(a.rot[1]), math.rad(a.rot[2]), math.rad(a.rot[3])) * (CFrame.new(c0.Position):Inverse() * m:GetPivot()))
end
local cf, size = m:GetBoundingBox()
if a.height and size.Y > 0 then m:ScaleTo(m:GetScale() * a.height / size.Y); cf, size = m:GetBoundingBox() end
m.WorldPivot = CFrame.new(cf.X, cf.Y - size.Y / 2, cf.Z) * (cf - cf.Position)
m:PivotTo(CFrame.new(0, -1000, 0))
m:SetAttribute("AssetId", a.id); m:SetAttribute("Size", size)
local old = lib:FindFirstChild(a.key); if old then old:Destroy() end
m.Parent = lib
return HttpService:JSONEncode({ key = a.key, size = { size.X, size.Y, size.Z }, parts = parts, removed = removed })'''

PLACE_PROPS = r'''
local HttpService = game:GetService("HttpService")
local L = HttpService:JSONDecode(__ARGS__)
local lib = game:GetService("ServerStorage"):FindFirstChild("PromptimateProps")
local sets = workspace:FindFirstChild("Sets") or Instance.new("Folder"); sets.Name = "Sets"; sets.Parent = workspace
local f = sets:FindFirstChild("EpisodeProps"); if f then f:Destroy() end
f = Instance.new("Folder"); f.Name = "EpisodeProps"; f.Parent = sets
local rp = RaycastParams.new(); rp.FilterType = Enum.RaycastFilterType.Exclude
local ex = { f }
for _, d in workspace:GetDescendants() do if d:IsA("Humanoid") then table.insert(ex, d.Parent) end end
rp.FilterDescendantsInstances = ex
local out, missing = {}, {}
for i, p in L do
  local src = lib and lib:FindFirstChild(p.prop)
  if not src then table.insert(missing, p.prop) else
    local m = src:Clone(); m.Name = p.name or (p.prop .. i)
    if p.height then local _, s = m:GetBoundingBox(); if s.Y > 0 then m:ScaleTo(m:GetScale() * p.height / s.Y) end end
    local y = p.y
    if y == nil then
      local hit = workspace:Raycast(Vector3.new(p.at[1], 60, p.at[2]), Vector3.new(0, -200, 0), rp)
      y = hit and hit.Position.Y or 0
    end
    m:PivotTo(CFrame.new(p.at[1], y, p.at[2]) * CFrame.Angles(math.rad(p.tilt or 0), math.rad(p.yaw or 0), 0))
    m.Parent = f
    m:SetAttribute("PromptimateHome", nil)
    -- sign/board text: the story's words (p.text), never the asset's placeholder ("your text here")
    for _, d in m:GetDescendants() do
      if d:IsA("TextLabel") or d:IsA("TextBox") or d:IsA("TextButton") then
        if p.text then d.Text = p.text; d.TextScaled = true
        elseif string.find(string.lower(d.Text), "text") then d.Text = "" end
      end
    end
    table.insert(out, m.Name)
  end
end
return HttpService:JSONEncode({ placed = out, missing = missing })'''


def _inserted(st, asset_id: str, name: str) -> list[str]:
    names = ('local t = {} for _, c in workspace:GetChildren() do table.insert(t, c.Name) end '
             'return game:GetService("HttpService"):JSONEncode(t)')
    before = set(json.loads(st.luau(names)))
    r = st.call("insert_asset", {"assetId": str(asset_id), "assetType": "Model", "assetName": name})
    if r.get("isError"):
        raise RuntimeError(str(r)[:400])
    after = json.loads(st.luau(names))
    return [n for n in after if n not in before] or [after[-1]]


def prop(key: str, asset_id: str, height: float | None = None, keep_humanoid: bool = False, rot=None) -> dict:
    """Insert a Creator Store model into the prop library (replacing an older entry with the same key)."""
    from roblox_studio import studio
    st = studio()
    args = {"inserted": _inserted(st, asset_id, key), "key": key, "id": str(asset_id), "height": height,
            "keepHumanoid": keep_humanoid, "rot": rot}
    return st.luau_json(LIB.replace("__ARGS__", json.dumps(json.dumps(args))))


def place(items: list[dict]) -> dict:
    from roblox_studio import studio
    return studio().luau_json(PLACE_PROPS.replace("__ARGS__", json.dumps(json.dumps(items))))


def library() -> dict:
    from roblox_studio import studio
    return studio().luau_json(r'''local lib = game:GetService("ServerStorage"):FindFirstChild("PromptimateProps")
local o = {} if lib then for _, m in lib:GetChildren() do local s = m:GetAttribute("Size")
o[m.Name] = { id = m:GetAttribute("AssetId"), size = s and { s.X, s.Y, s.Z } } end end
return game:GetService("HttpService"):JSONEncode(o)''')


if __name__ == "__main__" and sys.argv[1] == "prop":
    print(prop(sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else None))
elif __name__ == "__main__" and sys.argv[1] == "library":
    print(json.dumps(library(), indent=1))


BUILT = {"mirror": r'''
local SS = game:GetService("ServerStorage")
local lib = SS:FindFirstChild("PromptimateProps") or Instance.new("Folder"); lib.Name = "PromptimateProps"; lib.Parent = SS
local old = lib:FindFirstChild("mirror"); if old then old:Destroy() end
local m = Instance.new("Model"); m.Name = "mirror"
local function part(name, size, cf, mat, col, refl)
  local p = Instance.new("Part"); p.Name = name; p.Anchored = true; p.CanCollide = false; p.Size = size; p.CFrame = cf
  p.Material = mat; p.Color = col; p.Reflectance = refl or 0; p.Parent = m; return p
end
local wood = Color3.fromRGB(120, 72, 40)
part("Frame", Vector3.new(3.4, 6.6, 0.3), CFrame.new(0, 3.9, 0), Enum.Material.Wood, wood)
part("Glass", Vector3.new(2.9, 6.1, 0.05), CFrame.new(0, 3.9, -0.17), Enum.Material.Glass, Color3.fromRGB(200, 225, 240), 0.55)
part("Top", Vector3.new(3.8, 0.4, 0.45), CFrame.new(0, 7.3, 0), Enum.Material.Wood, wood)
part("FootL", Vector3.new(0.35, 0.6, 2.2), CFrame.new(-1.4, 0.3, 0), Enum.Material.Wood, wood)
part("FootR", Vector3.new(0.35, 0.6, 2.2), CFrame.new(1.4, 0.3, 0), Enum.Material.Wood, wood)
m.WorldPivot = CFrame.new(0, 0, 0)
local _, size = m:GetBoundingBox(); m:SetAttribute("Size", size); m:SetAttribute("AssetId", "built")
m:PivotTo(CFrame.new(0, -1000, 0)); m.Parent = lib
return "mirror"'''}


def build(key: str) -> str:
    from roblox_studio import studio
    return studio().luau(BUILT[key])
