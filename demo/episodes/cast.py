"""Episode casting in the open Roblox Studio place: every character an episode needs is built from a free-to-use
Roblox catalog body (HumanoidDescription; nothing is bought or published), named, placed and coloured. Characters
of other episodes are parked in ServerStorage.PromptimateCastPool so they don't wander into shot."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server"))

# look -> bundle id + optional colours (rgb). Smooth bodies only (blocky R15 swallows hands; see memory).
LOOKS = {
    "timmy": {"bundle": 573, "skin": [232, 190, 160]},          # Oliver: leather jacket
    "officer": {"bundle": 504, "skin": [150, 105, 80], "paint": {"torso": [28, 42, 92], "arms": [28, 42, 92], "legs": [20, 24, 40],
                                          "feet": [15, 15, 15]}, "badge": True},
    "lee": {"bundle": 337, "skin": [245, 205, 175]},            # City Life Woman
    "tedd": {"bundle": 341},                                    # Squad Ghouls: Drop Dead Tedd
    "randel": {"bundle": 342}, "wendy": {"bundle": 365}, "marilyn": {"bundle": 366}, "zoe": {"bundle": 367},
    "paladin": {"bundle": 338}, "junkbot": {"bundle": 589},
    # plain base bodies, painted: townsfolk, or mannequins (white, no hair)
    "mannequin": {"bundle": 985, "hair": False, "skin": [236, 232, 226], "paint": {"all": [236, 232, 226]}},
    "mannequin2": {"bundle": 980, "hair": False, "skin": [236, 232, 226], "paint": {"all": [236, 232, 226]}},
    "red": {"skin": [232, 190, 160], "bundle": 985, "paint": {"torso": [190, 40, 40], "arms": [232, 190, 160], "legs": [40, 40, 60],
                                     "head": [232, 190, 160]}},
    "green": {"skin": [140, 100, 70], "bundle": 980, "paint": {"torso": [40, 150, 80], "arms": [140, 100, 70], "legs": [60, 50, 40],
                                       "head": [140, 100, 70]}},
    "yellow": {"skin": [250, 215, 185], "bundle": 985, "paint": {"torso": [230, 190, 40], "arms": [250, 215, 185], "legs": [50, 70, 140],
                                        "head": [250, 215, 185]}},
}

# classic blocky looks (the "In this town" trend's look): body colours + free Roblox hair/hats
SKIN = [255, 204, 153]
LOOKS.update({
    "c_timmy": {"classic": {"skin": SKIN, "shirt": [13, 105, 172], "legs": [40, 127, 71]}, "hairIds": [1772336109]},
    "c_mom": {"classic": {"skin": [234, 184, 146], "shirt": [255, 255, 255], "legs": [196, 40, 28]}, "hairIds": [137714508]},
    "c_preston": {"classic": {"skin": SKIN, "shirt": [239, 184, 56], "legs": [239, 184, 56]}, "hairIds": [1029597]},
    "c_kid": {"classic": {"skin": [124, 92, 70], "shirt": [255, 89, 89], "legs": [27, 42, 53]}, "hairIds": [6467488863]},
    "c_lady": {"classic": {"skin": SKIN, "shirt": [107, 50, 124], "legs": [99, 95, 98]}, "hairIds": [236398736]},
    "c_man": {"classic": {"skin": [204, 142, 105], "shirt": [75, 151, 75], "legs": [99, 95, 98]}, "hairIds": [265133385]},
    "c_worker": {"classic": {"skin": SKIN, "shirt": [218, 133, 65], "legs": [27, 42, 53]}, "hairIds": [915184016]},
    "c_butler": {"classic": {"skin": [204, 142, 105], "shirt": [27, 27, 32], "legs": [27, 27, 32]}, "hairIds": [915184016]},
    "c_girl": {"classic": {"skin": [234, 184, 146], "shirt": [255, 150, 200], "legs": [13, 105, 172]}, "hairIds": [236398736]},
    "c_grandpa": {"classic": {"skin": SKIN, "shirt": [120, 90, 60], "legs": [60, 60, 70]}, "hairIds": [265133385]},
})

ENSURE = r'''
local Players = game:GetService("Players"); local AssetService = game:GetService("AssetService")
local MS = game:GetService("MarketplaceService"); local SS = game:GetService("ServerStorage")
local HttpService = game:GetService("HttpService")
local spec = HttpService:JSONDecode(__SPEC__)
local pool = SS:FindFirstChild("PromptimateCastPool") or Instance.new("Folder"); pool.Name = "PromptimateCastPool"; pool.Parent = SS
local castF = workspace:FindFirstChild("Cast") or Instance.new("Folder"); castF.Name = "Cast"; castF.Parent = workspace
local want = {}
for _, c in spec do want[c.name] = c end
-- park characters that aren't in this episode (the town's original trio included)
for _, d in workspace:GetDescendants() do
  if d:IsA("Model") and d:FindFirstChildOfClass("Humanoid") and not d:IsDescendantOf(workspace:FindFirstChild("PromptimateAvatarTest") or pool)
     and not d:IsDescendantOf(workspace:FindFirstChild("PromptimateCastTest") or pool) and not want[d.Name] then
    d.Parent = pool
  end
end
local function paint(m, p)
  local groups = { torso = { "UpperTorso", "LowerTorso" }, arms = { "LeftUpperArm", "RightUpperArm", "LeftLowerArm", "RightLowerArm", "LeftHand", "RightHand" },
    legs = { "LeftUpperLeg", "RightUpperLeg", "LeftLowerLeg", "RightLowerLeg" }, feet = { "LeftFoot", "RightFoot" }, head = { "Head" } }
  for g, rgb in p do
    local names = {}
    if g == "all" then for _, l in groups do for _, n in l do table.insert(names, n) end end else names = groups[g] or {} end
    for _, n in names do
      local part = m:FindFirstChild(n)
      if part then
        if part:IsA("MeshPart") then part.TextureID = "" end
        for _, sa in part:GetChildren() do if sa:IsA("SurfaceAppearance") then sa:Destroy() end end
        part.Color = Color3.fromRGB(rgb[1], rgb[2], rgb[3])
      end
    end
  end
  local bc = m:FindFirstChildOfClass("BodyColors"); if bc then bc:Destroy() end
end
local cacheDesc = {}
local function build(c)
  local desc = Instance.new("HumanoidDescription")
  local hair = {}
  local items = {}
  if c.bundle then items = AssetService:GetBundleDetailsAsync(c.bundle).Items end
  for _, it in items do
    if it.Type == "Asset" then
      local okI, info = pcall(MS.GetProductInfo, MS, it.Id, Enum.InfoType.Asset)
      local t = okI and info.AssetTypeId or 0
      if t == 17 or t == 79 then desc.Head = it.Id elseif t == 27 then desc.Torso = it.Id
      elseif t == 28 then desc.RightArm = it.Id elseif t == 29 then desc.LeftArm = it.Id
      elseif t == 30 then desc.LeftLeg = it.Id elseif t == 31 then desc.RightLeg = it.Id
      elseif t == 11 then desc.Shirt = it.Id elseif t == 12 then desc.Pants = it.Id
      elseif t == 41 and c.hair ~= false then table.insert(hair, tostring(it.Id))
      elseif t == 8 and c.hair ~= false then desc.HatAccessory = tostring(it.Id)
      elseif t == 42 then desc.FaceAccessory = tostring(it.Id) end
    end
  end
  for _, h in c.hairIds or {} do table.insert(hair, tostring(h)) end
  desc.HairAccessory = table.concat(hair, ",")
  if c.hatIds then desc.HatAccessory = table.concat(c.hatIds, ",") end
  if c.classic then   -- classic blocky body: colours on the description (head/arms skin, shirt, trousers)
    local function col(v) return Color3.fromRGB(v[1], v[2], v[3]) end
    local sk = col(c.classic.skin)
    desc.HeadColor, desc.LeftArmColor, desc.RightArmColor = sk, col(c.classic.arms or c.classic.skin), col(c.classic.arms or c.classic.skin)
    desc.TorsoColor = col(c.classic.shirt)
    desc.LeftLegColor, desc.RightLegColor = col(c.classic.legs), col(c.classic.legs)
  end
  if c.skin then   -- body colour shows through the skin areas of textured bodies (faces, hands, necks)
    local col = Color3.fromRGB(c.skin[1], c.skin[2], c.skin[3])
    desc.HeadColor, desc.TorsoColor, desc.LeftArmColor, desc.RightArmColor, desc.LeftLegColor, desc.RightLegColor = col, col, col, col, col, col
  end
  local m = Players:CreateHumanoidModelFromDescription(desc, c.rig == "R6" and Enum.HumanoidRigType.R6 or Enum.HumanoidRigType.R15)
  if c.paint then paint(m, c.paint) end
  if c.badge then
    local b = Instance.new("Part"); b.Name = "Badge"; b.Size = Vector3.new(0.18, 0.22, 0.05); b.Color = Color3.fromRGB(230, 190, 60)
    b.Material = Enum.Material.Metal; b.CanCollide = false; b.Massless = true
    b.CFrame = m.UpperTorso.CFrame * CFrame.new(-0.3, 0.25, -m.UpperTorso.Size.Z / 2 - 0.01)
    local w = Instance.new("WeldConstraint"); w.Part0 = m.UpperTorso; w.Part1 = b; w.Parent = b; b.Parent = m
  end
  for _, s in m:GetDescendants() do if s:IsA("Script") or s:IsA("LocalScript") then s:Destroy() end end
  m:SetAttribute("PromptimateLook", c.lookKey)
  m:SetAttribute("PromptimateArms", c.arms or 0.55)   -- story acting: faces carry it, arms stay out of the face
  return m
end
local out = {}
for _, c in spec do
  local ok, err = pcall(function()
    local m
    for _, d in workspace:GetDescendants() do if d:IsA("Model") and d.Name == c.name and d:FindFirstChildOfClass("Humanoid") then m = d break end end
    if not m then local p = pool:FindFirstChild(c.name); if p and p:GetAttribute("PromptimateLook") == c.lookKey then m = p end end
    if m and m:GetAttribute("PromptimateLook") ~= c.lookKey then m:Destroy(); m = nil end
    if not m then m = build(c); m.Name = c.name end
    m.Parent = castF
    local hrp = m.HumanoidRootPart; hrp.Anchored = true
    -- stand on whatever is there (sidewalk, floor, stage): ray down from above, ignoring characters
    local rp = RaycastParams.new(); rp.FilterType = Enum.RaycastFilterType.Exclude
    rp.FilterDescendantsInstances = { castF, pool }
    local floor = 0.1
    local hit = workspace:Raycast(Vector3.new(c.x, 6, c.z), Vector3.new(0, -30, 0), rp)   -- below awnings and ceilings
    if hit then floor = hit.Position.Y end
    local legs = m.Humanoid.HipHeight
    if m.Humanoid.RigType == Enum.HumanoidRigType.R6 and m:FindFirstChild("Left Leg") then legs = m["Left Leg"].Size.Y end
    local y = floor + legs + hrp.Size.Y / 2
    m:PivotTo(CFrame.new(c.x, y, c.z) * CFrame.Angles(0, math.rad(c.yaw or 0), 0))
    m.Humanoid.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
    out[c.name] = "ok"
  end)
  if not ok then out[c.name] = tostring(err) end
end
return HttpService:JSONEncode(out)'''


def ensure(cast: list[dict]) -> dict:
    """cast: [{name, look, at: [x, z], yaw}] -> builds/places everyone; parks every other character."""
    from roblox_studio import studio
    spec = []
    for c in cast:
        lk = dict(LOOKS[c["look"]])
        spec.append({"name": c["name"], "lookKey": c["look"] + "#" + __import__("hashlib").sha1(json.dumps(lk, sort_keys=True).encode()).hexdigest()[:6], "bundle": lk.get("bundle"), "paint": lk.get("paint"),
                     "badge": lk.get("badge", False), "hair": lk.get("hair", True), "skin": lk.get("skin"),
                     "classic": lk.get("classic"), "hairIds": lk.get("hairIds"), "hatIds": lk.get("hatIds"),
                     "rig": "R6",   # R15 retired: too blocky for story videos (user call, 2026-11-16)
                     "x": c["at"][0], "z": c["at"][1], "yaw": c.get("yaw", 0)})
    return studio().luau_json(ENSURE.replace("__SPEC__", json.dumps(json.dumps(spec))), timeout=900)
