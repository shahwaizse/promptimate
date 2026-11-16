-- The creator's own steps (what the Ovra-style prompt already does through Studio's MCP, identical with or without
-- Promptimate): a cast of R15 rigs from HumanoidDescriptions, and the set dressing this story needs (a normal-height
-- bench in place of the demo's low one, a second bench by the crates with its own NO SITTING sign).
local Players = game:GetService("Players")
local SS = game:GetService("ServerStorage")
for _, n in { "ShortCast", "GenKid", "GenAdult" } do
  local o = workspace:FindFirstChild(n); if o then o.Parent = SS end
end
local old = workspace:FindFirstChild("Cast"); if old then old:Destroy() end
local cast = Instance.new("Folder"); cast.Name = "Cast"; cast.Parent = workspace

local function weld(part, to, cf)
  part.Anchored = false; part.CanCollide = false; part.Massless = true; part.CanQuery = false; part.CanTouch = false
  part.CFrame = to.CFrame * cf
  local w = Instance.new("WeldConstraint"); w.Part0 = to; w.Part1 = part; w.Parent = part
  part.Parent = to.Parent
end
local function rig(name, h, w, head, torso, legs, x, z, yaw, hat)
  local d = Instance.new("HumanoidDescription")
  d.HeightScale = h; d.WidthScale = w; d.DepthScale = w
  d.HeadColor = head; d.LeftArmColor = head; d.RightArmColor = head; d.TorsoColor = torso
  d.LeftLegColor = legs; d.RightLegColor = legs
  local m = Players:CreateHumanoidModelFromDescription(d, Enum.HumanoidRigType.R15)
  m.Name = name
  local hum = m:FindFirstChildOfClass("Humanoid")
  hum.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
  m.HumanoidRootPart.Anchored = true
  m:PivotTo(CFrame.new(x, hum.HipHeight + m.HumanoidRootPart.Size.Y / 2, z) * CFrame.Angles(0, yaw, 0))
  m.Parent = cast
  local hy = m.Head.Size.Y / 2
  if hat == "police" then
    local cap = Instance.new("Part"); cap.Name = "Cap"; cap.Size = Vector3.new(1.35, 0.42, 1.35)
    cap.Color = Color3.fromRGB(25, 35, 70); weld(cap, m.Head, CFrame.new(0, hy + 0.12, 0))
    local brim = Instance.new("Part"); brim.Name = "Brim"; brim.Size = Vector3.new(1.1, 0.08, 0.55)
    brim.Color = Color3.fromRGB(15, 15, 18); weld(brim, m.Head, CFrame.new(0, hy - 0.05, -0.75) * CFrame.Angles(math.rad(-10), 0, 0))
    local badge = Instance.new("Part"); badge.Name = "Badge"; badge.Size = Vector3.new(0.35, 0.4, 0.06)
    badge.Color = Color3.fromRGB(240, 200, 60); badge.Material = Enum.Material.Metal
    weld(badge, m.UpperTorso, CFrame.new(-0.45, 0.35, -m.UpperTorso.Size.Z / 2 - 0.02))
  elseif hat == "bun" then
    local hair = Instance.new("Part"); hair.Name = "Hair"; hair.Size = Vector3.new(1.25, 0.5, 1.25)
    hair.Color = Color3.fromRGB(170, 170, 175); weld(hair, m.Head, CFrame.new(0, hy - 0.05, 0.08))
    local bun = Instance.new("Part"); bun.Shape = Enum.PartType.Ball; bun.Name = "Bun"; bun.Size = Vector3.new(0.7, 0.7, 0.7)
    bun.Color = Color3.fromRGB(170, 170, 175); weld(bun, m.Head, CFrame.new(0, hy + 0.25, 0.35))
  end
  return m
end
local C3 = Color3.fromRGB
-- facing: yaw = atan2(-dx, -dz) for direction (dx, dz)
rig("Timmy", 0.85, 0.9, C3(245, 205, 48), C3(13, 105, 172), C3(40, 127, 71), -13, 2.4, math.atan2(-1, 0))
rig("Officer", 1.0, 1.0, C3(204, 142, 105), C3(33, 50, 92), C3(27, 36, 64), -24, 7.5, math.atan2(-1, 0), "police")
rig("MrsLee", 1.0, 1.0, C3(234, 184, 146), C3(218, 112, 162), C3(98, 71, 140), 7, -2.6, math.atan2(0, -1), "bun")

-- benches (seat top 1.0 stud above the sidewalk, back on the -Z side for Bench, facing +Z)
local function bench(name, cx, cz, len, parent)
  local m = Instance.new("Model"); m.Name = name
  local wood, metal = C3(150, 98, 58), C3(45, 45, 50)
  local function P(n, pos, size, col)
    local p = Instance.new("Part"); p.Name = n; p.Anchored = true; p.Size = size; p.Position = pos; p.Color = col
    p.Material = Enum.Material.WoodPlanks; p.TopSurface = Enum.SurfaceType.Smooth; p.BottomSurface = Enum.SurfaceType.Smooth
    p.Parent = m; return p
  end
  for i, dz in { -0.45, 0, 0.45 } do P("Slat", Vector3.new(cx, 0.88, cz + dz), Vector3.new(len, 0.24, 0.4), wood) end
  P("Back", Vector3.new(cx, 1.75, cz - 0.85), Vector3.new(len, 0.5, 0.18), wood)
  P("Back", Vector3.new(cx, 2.4, cz - 0.85), Vector3.new(len, 0.5, 0.18), wood)
  for _, dx in { -len / 2 + 0.4, len / 2 - 0.4 } do
    local l = P("Leg", Vector3.new(cx + dx, 0.38, cz), Vector3.new(0.25, 0.76, 1.1), metal); l.Material = Enum.Material.Metal
    local b = P("BackLeg", Vector3.new(cx + dx, 1.4, cz - 0.82), Vector3.new(0.25, 2.8, 0.25), metal); b.Material = Enum.Material.Metal
  end
  m.Parent = parent
  return m
end
local props = workspace.Town.Props
local oldBench = workspace.Town:FindFirstChild("Bench"); if oldBench then oldBench.Name = "BenchDemo"; oldBench.Parent = SS end
for _, n in { "Bench", "Bench2", "Sign2" } do local o = workspace.Town:FindFirstChild(n); if o then o:Destroy() end end
bench("Bench", -0.46, 1.45, 6, workspace.Town)
bench("Bench2", 21.0, 10.0, 8, workspace.Town)   -- moved off the lamp post at (20, 12.8); 8 long: "too short for everyone on it"
-- a second NO SITTING sign beside Bench2 (moved out to x=27.6: its board hung over the bench end)
local sign = Instance.new("Model"); sign.Name = "Sign2"; sign.Parent = workspace.Town
local pole = Instance.new("Part"); pole.Anchored = true; pole.Name = "SignPole"; pole.Size = Vector3.new(0.3, 5, 0.3)
pole.Position = Vector3.new(27.6, 2.5, 9.4); pole.Color = C3(60, 60, 64); pole.Parent = sign
local board = Instance.new("Part"); board.Anchored = true; board.Name = "NoSitting2"; board.Size = Vector3.new(3, 3, 0.25)
board.Position = Vector3.new(27.6, 5.6, 9.4); board.Color = C3(250, 250, 250); board.Parent = sign
local g = Instance.new("SurfaceGui"); g.Face = Enum.NormalId.Back; g.Parent = board
local t = Instance.new("TextLabel"); t.Size = UDim2.fromScale(1, 1); t.BackgroundColor3 = C3(200, 30, 30)
t.Text = "NO SITTING"; t.TextColor3 = C3(255, 255, 255); t.TextScaled = true; t.Font = Enum.Font.FredokaOne; t.Parent = g
return "cast + set ok"
