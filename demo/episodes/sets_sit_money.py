"""Sets for 'In this world, sitting down costs money': bakery interior, Timmy's room, Preston's chair market in front
of the mansion, and the paid bench sign in town. Built from parts + a few free Creator Store models."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "mcp_server"))
sys.path.insert(0, str(HERE))
import sets as SETS  # noqa: E402
from roblox_studio import studio  # noqa: E402

LIB = r'''
local sets = workspace:FindFirstChild("Sets") or Instance.new("Folder"); sets.Name = "Sets"; sets.Parent = workspace
local function folder(name)
  local f = sets:FindFirstChild(name); if f then f:Destroy() end
  f = Instance.new("Model"); f.Name = name; f.Parent = sets; return f
end
local function part(parent, name, size, cf, color, mat, extra)
  local p = Instance.new("Part"); p.Name = name; p.Anchored = true; p.Size = size; p.CFrame = cf
  p.Color = color; p.Material = mat or Enum.Material.SmoothPlastic; p.TopSurface = Enum.SurfaceType.Smooth
  p.BottomSurface = Enum.SurfaceType.Smooth
  if extra then for k, v in extra do p[k] = v end end
  p.Parent = parent; return p
end
local function sign(parent, name, size, cf, bg, text, fg, font)
  local p = part(parent, name, size, cf, bg)
  local g = Instance.new("SurfaceGui"); g.Face = Enum.NormalId.Front; g.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
  g.PixelsPerStud = 60; g.Parent = p
  local t = Instance.new("TextLabel"); t.Size = UDim2.fromScale(1, 1); t.BackgroundTransparency = 1; t.Text = text
  t.TextScaled = true; t.Font = font or Enum.Font.FredokaOne; t.TextColor3 = fg or Color3.new(1, 1, 1); t.Parent = g
  local pad = Instance.new("UIPadding"); pad.PaddingLeft = UDim.new(0.06, 0); pad.PaddingRight = UDim.new(0.06, 0)
  pad.PaddingTop = UDim.new(0.08, 0); pad.PaddingBottom = UDim.new(0.08, 0); pad.Parent = t
  return p
end
local function light(parent, pos, color, range, bright)
  local a = part(parent, "Lamp", Vector3.new(1.2, 0.4, 1.2), CFrame.new(pos), Color3.fromRGB(255, 240, 200), Enum.Material.Neon)
  local l = Instance.new("PointLight"); l.Color = color or Color3.fromRGB(255, 214, 160); l.Range = range or 22
  l.Brightness = bright or 1.6; l.Shadows = true; l.Parent = a; return a
end
local function move(model, cf) model:PivotTo(cf) end
local WOOD, PLANK = Color3.fromRGB(150, 103, 62), Color3.fromRGB(196, 150, 104)
'''

BAKERY = LIB + r'''
-- bakery interior: an open-front stage (camera side is +Z). Floor centre (350, 0).
local f = folder("BakeryShop")
local X, Z = 350, 0
part(f, "Floor", Vector3.new(34, 1, 26), CFrame.new(X, -0.4, Z), PLANK, Enum.Material.WoodPlanks)
part(f, "BackWall", Vector3.new(34, 16, 1), CFrame.new(X, 7.6, Z - 13), Color3.fromRGB(246, 220, 190), Enum.Material.SmoothPlastic)
part(f, "WallStripe", Vector3.new(34, 3, 1.1), CFrame.new(X, 1.6, Z - 13), Color3.fromRGB(170, 85, 60), Enum.Material.Brick)
part(f, "LeftWall", Vector3.new(1, 16, 26), CFrame.new(X - 17, 7.6, Z), Color3.fromRGB(246, 220, 190))
part(f, "RightWall", Vector3.new(1, 16, 26), CFrame.new(X + 17, 7.6, Z), Color3.fromRGB(246, 220, 190))
part(f, "Ceiling", Vector3.new(34, 1, 26), CFrame.new(X, 15.6, Z), Color3.fromRGB(255, 245, 230))
sign(f, "Sign", Vector3.new(14, 3.2, 0.4), CFrame.new(X, 11.5, Z - 12.4) * CFrame.Angles(0, math.pi, 0), Color3.fromRGB(170, 85, 60), "BAKERY", Color3.fromRGB(255, 240, 210))
-- shelves of bread on the back wall
for i = 0, 2 do
  part(f, "Shelf" .. i, Vector3.new(26, 0.4, 2), CFrame.new(X, 4 + i * 2.4, Z - 12), WOOD, Enum.Material.Wood)
  for k = 0, 9 do
    part(f, "Bread", Vector3.new(1.6, 0.9, 1.1), CFrame.new(X - 11.5 + k * 2.55, 4.65 + i * 2.4, Z - 12) * CFrame.Angles(0, math.rad(k * 17 % 30), 0),
      Color3.fromRGB(205, 140, 70), Enum.Material.SmoothPlastic, { Shape = Enum.PartType.Block })
  end
end
-- the counter (mom stands behind it, z ~ -7)
part(f, "Counter", Vector3.new(22, 3.4, 2.6), CFrame.new(X, 1.6, Z - 3.6), WOOD, Enum.Material.Wood)
part(f, "CounterTop", Vector3.new(22.6, 0.3, 3.0), CFrame.new(X, 3.45, Z - 3.6), Color3.fromRGB(235, 230, 225), Enum.Material.Marble)
part(f, "Glass", Vector3.new(10, 2.6, 0.2), CFrame.new(X - 5, 2.0, Z - 2.25), Color3.fromRGB(200, 230, 255), Enum.Material.Glass, { Transparency = 0.6 })
for k = 0, 5 do
  part(f, "Donut", Vector3.new(1.0, 0.4, 1.0), CFrame.new(X - 9 + k * 1.6, 2.0, Z - 3.3), Color3.fromRGB(240, 130, 170), Enum.Material.SmoothPlastic, { Shape = Enum.PartType.Cylinder })
end
light(f, Vector3.new(X - 8, 14.8, Z - 2), nil, 26, 1.8)
light(f, Vector3.new(X + 8, 14.8, Z - 2), nil, 26, 1.8)
light(f, Vector3.new(X, 14.8, Z + 6), nil, 26, 1.2)
return "ok"'''

ROOM = LIB + r'''
-- Timmy's small room (open front +Z), floor centre (450, 0)
local f = folder("TimmyRoom")
local X, Z = 450, 0
part(f, "Floor", Vector3.new(24, 1, 20), CFrame.new(X, -0.4, Z), Color3.fromRGB(120, 90, 70), Enum.Material.WoodPlanks)
part(f, "BackWall", Vector3.new(24, 14, 1), CFrame.new(X, 6.6, Z - 10), Color3.fromRGB(120, 160, 200))
part(f, "LeftWall", Vector3.new(1, 14, 20), CFrame.new(X - 12, 6.6, Z), Color3.fromRGB(110, 150, 190))
part(f, "RightWall", Vector3.new(1, 14, 20), CFrame.new(X + 12, 6.6, Z), Color3.fromRGB(110, 150, 190))
part(f, "Ceiling", Vector3.new(24, 1, 20), CFrame.new(X, 13.6, Z), Color3.fromRGB(230, 230, 235))
-- window with night sky
part(f, "Window", Vector3.new(6, 5, 0.3), CFrame.new(X + 5, 8, Z - 9.4), Color3.fromRGB(30, 40, 80), Enum.Material.Neon)
part(f, "WinFrameH", Vector3.new(6.4, 0.3, 0.5), CFrame.new(X + 5, 8, Z - 9.3), Color3.fromRGB(240, 240, 240))
part(f, "WinFrameV", Vector3.new(0.3, 5.4, 0.5), CFrame.new(X + 5, 8, Z - 9.3), Color3.fromRGB(240, 240, 240))
sign(f, "Poster", Vector3.new(3.4, 4.4, 0.2), CFrame.new(X - 5, 8.4, Z - 9.4) * CFrame.Angles(0, math.pi, 0), Color3.fromRGB(255, 220, 80), "SAVE FOR MOM'S CHAIR", Color3.fromRGB(120, 40, 20))
-- bed (left) and desk (right)
part(f, "BedFrame", Vector3.new(5, 1.4, 9), CFrame.new(X - 8.5, 0.7, Z - 4.5), WOOD, Enum.Material.Wood)
part(f, "Mattress", Vector3.new(4.6, 0.8, 8.6), CFrame.new(X - 8.5, 1.8, Z - 4.5), Color3.fromRGB(230, 230, 240), Enum.Material.Fabric)
part(f, "Blanket", Vector3.new(4.8, 0.3, 5.6), CFrame.new(X - 8.5, 2.3, Z - 3), Color3.fromRGB(200, 60, 60), Enum.Material.Fabric)
part(f, "Pillow", Vector3.new(3.4, 0.7, 1.8), CFrame.new(X - 8.5, 2.5, Z - 8), Color3.fromRGB(250, 250, 250), Enum.Material.Fabric)
part(f, "DeskTop", Vector3.new(6, 0.4, 3), CFrame.new(X + 6, 3.2, Z - 7.4), WOOD, Enum.Material.Wood)
for _, dx in { -2.7, 2.7 } do part(f, "DeskLeg", Vector3.new(0.4, 3, 2.6), CFrame.new(X + 6 + dx, 1.5, Z - 7.4), WOOD, Enum.Material.Wood) end
light(f, Vector3.new(X, 12.8, Z), Color3.fromRGB(255, 200, 140), 22, 1.3)
return "ok"'''

MARKET = LIB + r'''
-- Preston's chair market on the lawn in front of the mansion (mansion front faces -Z); stage centre (600, -128)
local f = folder("ChairMarket")
local X, Z = 600, -128
part(f, "Carpet", Vector3.new(10, 0.2, 26), CFrame.new(X, 0.15, Z), Color3.fromRGB(170, 20, 30), Enum.Material.Fabric)
part(f, "Stage", Vector3.new(26, 1.2, 10), CFrame.new(X, 0.6, Z + 8), Color3.fromRGB(240, 235, 220), Enum.Material.Marble)
sign(f, "Sign", Vector3.new(18, 4, 0.5), CFrame.new(X, 10, Z + 13), Color3.fromRGB(239, 184, 56), "PRESTON'S CHAIRS", Color3.fromRGB(80, 40, 0))
for _, dx in { -9, 9 } do part(f, "SignPost", Vector3.new(0.6, 10, 0.6), CFrame.new(X + dx, 5, Z + 13), Color3.fromRGB(200, 160, 60), Enum.Material.Metal) end
sign(f, "Price", Vector3.new(5, 2.2, 0.3), CFrame.new(X + 9, 3.4, Z + 2), Color3.fromRGB(255, 255, 255), "CHAIR: $10,000", Color3.fromRGB(200, 20, 20))
local throne = workspace.Sets:FindFirstChild("Throne")
if throne then throne.Parent = f; throne:PivotTo(CFrame.new(X, 1.2 + 4.5, Z + 9) * CFrame.Angles(0, math.pi, 0)) end
return "ok"'''

STREET = LIB + r'''
-- the paid bench in town: a coin meter and a price sign at Bench (-0.5, 1.3)
local f = folder("PaidBench")
part(f, "MeterPole", Vector3.new(0.4, 3.6, 0.4), CFrame.new(3.6, 1.9, 1.6), Color3.fromRGB(60, 60, 70), Enum.Material.Metal)
part(f, "Meter", Vector3.new(1.2, 1.6, 0.9), CFrame.new(3.6, 4.2, 1.6), Color3.fromRGB(200, 200, 210), Enum.Material.Metal)
part(f, "MeterGlass", Vector3.new(0.9, 0.6, 0.1), CFrame.new(3.6, 4.5, 2.07), Color3.fromRGB(255, 80, 60), Enum.Material.Neon)
sign(f, "PriceSign", Vector3.new(4.6, 2.2, 0.2), CFrame.new(-0.5, 5.6, 0.2) * CFrame.Angles(0, math.pi, 0), Color3.fromRGB(255, 220, 60), "SITTING: $5 / MINUTE", Color3.fromRGB(30, 30, 30))
for _, dx in { -2.6, 1.6 } do part(f, "SignPost", Vector3.new(0.25, 5, 0.25), CFrame.new(-0.5 + dx, 2.6, 0.2), Color3.fromRGB(60, 60, 70), Enum.Material.Metal) end
return "ok"'''


def build():
    st = studio()
    st.luau('for _, n in {"Bakery", "Bakery2", "Bakery3"} do local b = workspace.Sets:FindFirstChild(n); if b then b:Destroy() end end; '
            'local p = workspace:FindFirstChild("probe"); if p then p:Destroy() end; return 1')
    for name, code in (("bakery", BAKERY), ("room", ROOM), ("market", MARKET), ("street", STREET)):
        print(name, st.luau(code))
    # free models: chairs for sale + mom's chair, the money jar, a cash register
    print(SETS.insert("MomChair", "5158346011", 356, -8.5, 180))
    print(SETS.insert("Jar", "3051664260", 456, -7.4))
    print(SETS.insert("Register", "8509844849", 345, -3.6, 180))
    for i, dx in enumerate((-7, -3.5, 3.5, 7)):
        print(SETS.insert(f"SaleChair{i}", "5158346011", 600 + dx, -128 + 4, 180))
    print(SETS.insert("CarryChair", "5158346011", 620, -110, 0))
    # lift the jar onto the desk and the register onto the counter
    print(st.luau(r'''
local s = workspace.Sets
local function onTop(m, y) local cf, sz = m:GetBoundingBox(); m:PivotTo(m:GetPivot() + Vector3.new(0, y - (cf.Y - sz.Y / 2), 0)) end
onTop(s.Jar, 3.4); onTop(s.Register, 3.6)
return "ok"'''))


if __name__ == "__main__":
    build()
