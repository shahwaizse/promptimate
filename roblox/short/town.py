"""Build the 'In This Town' set in the open Studio place (Edit datamodel) from story.py's layout: sidewalk, road,
shopfronts with signs, the bench, NO SITTING signs, the crate stack, lamps, trees, lighting. Plain anchored parts only
(no free models, so no foreign scripts). Re-running replaces workspace.Town.

    .venv\\Scripts\\python.exe roblox\\short\\town.py [--seat-top 1.05] [--shot]   # --shot saves an overview capture
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "roblox" / "tools"))
import story as S  # noqa: E402
from studio_mcp import StudioSession  # noqa: E402

LIB = r'''
local town = workspace:FindFirstChild("Town")
local function P(parent, props)
  local cls = props.Class or "Part"
  local p = Instance.new(cls)
  p.Anchored = true
  p.TopSurface = Enum.SurfaceType.Smooth; p.BottomSurface = Enum.SurfaceType.Smooth
  for k, v in props do if k ~= "Class" and k ~= "Parent" then p[k] = v end end
  p.Parent = parent
  return p
end
local function box(parent, name, cx, cy, cz, sx, sy, sz, color, mat, extra)
  local p = P(parent, { Name = name, Size = Vector3.new(sx, sy, sz), CFrame = CFrame.new(cx, cy, cz),
    Color = color, Material = mat or Enum.Material.SmoothPlastic })
  if extra then for k, v in extra do p[k] = v end end
  return p
end
local function label(part, face, text, color, bg, font, scale)
  local g = Instance.new("SurfaceGui"); g.Face = face; g.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
  g.PixelsPerStud = 40; g.LightInfluence = 0.6; g.Parent = part
  local t = Instance.new("TextLabel"); t.Size = UDim2.fromScale(1, 1); t.BackgroundTransparency = bg and 0 or 1
  if bg then t.BackgroundColor3 = bg end
  t.Text = text; t.TextColor3 = color; t.TextScaled = true; t.Font = font or Enum.Font.FredokaOne; t.Parent = g
  local c = Instance.new("UITextSizeConstraint"); c.MaxTextSize = 400; c.Parent = t
  local pad = Instance.new("UIPadding"); pad.PaddingLeft = UDim.new(0.06, 0); pad.PaddingRight = UDim.new(0.06, 0)
  pad.PaddingTop = UDim.new(scale or 0.08, 0); pad.PaddingBottom = UDim.new(scale or 0.08, 0); pad.Parent = t
  return t
end
local C3 = Color3.fromRGB
'''

GROUND = r'''
local old = workspace:FindFirstChild("Town"); if old then old:Destroy() end
local bp = workspace:FindFirstChild("Baseplate"); if bp then bp.Parent = game:GetService("ServerStorage") end
for _, n in {"PromptimateProbe", "H2H_Promptimate", "H2H_Roblox", "RobloxGenRig"} do local o = workspace:FindFirstChild(n); if o then o:Destroy() end end
town = Instance.new("Folder"); town.Name = "Town"
local g = Instance.new("Folder"); g.Name = "Ground"; g.Parent = town
box(g, "Grass", 0, -1.2, 0, 600, 1, 600, C3(92, 148, 70), Enum.Material.Grass)
box(g, "Sidewalk", 0, -0.5, 5, 160, 1, 18, C3(196, 192, 184), Enum.Material.Concrete)
for i = -16, 16 do box(g, "Joint", i * 5, 0.005, 5, 0.12, 0.01, 18, C3(165, 160, 152), Enum.Material.SmoothPlastic) end
box(g, "Curb", 0, -0.35, 14.2, 160, 0.9, 0.6, C3(160, 158, 152), Enum.Material.Concrete)
box(g, "Road", 0, -0.6, 27, 160, 0.5, 25.4, C3(54, 56, 60), Enum.Material.Asphalt)
for i = -15, 15 do box(g, "Dash", i * 6, -0.34, 27, 3, 0.02, 0.35, C3(240, 200, 60)) end
box(g, "FarSidewalk", 0, -0.5, 42.5, 160, 1, 6, C3(196, 192, 184), Enum.Material.Concrete)
town.Parent = workspace
return "ground"
'''

BUILDINGS = r'''
local b = Instance.new("Folder"); b.Name = "Buildings"
local shops = SHOPS
for i, s in shops do
  local x0, x1, h, col, name, sign, signcol = s[1], s[2], s[3], C3(s[4], s[5], s[6]), s[7], C3(s[8], s[9], s[10]), C3(s[11], s[12], s[13])
  local cx, w = (x0 + x1) / 2, x1 - x0
  local m = Instance.new("Model"); m.Name = name; m.Parent = b
  box(m, "Body", cx, h / 2, -4 - 10, w, h, 20, col, Enum.Material.Brick)
  box(m, "Trim", cx, h + 0.4, -4 - 9.6, w + 0.6, 0.8, 20.8, col:Lerp(C3(255, 255, 255), 0.35), Enum.Material.SmoothPlastic)
  box(m, "Base", cx, 0.6, -3.85, w, 1.2, 0.3, col:Lerp(C3(0, 0, 0), 0.35), Enum.Material.Concrete)
  -- sign board over the door
  local board = box(m, "Sign", cx, 9.2, -3.7, math.min(w - 2, 12), 2.4, 0.5, sign, Enum.Material.SmoothPlastic)
  label(board, Enum.NormalId.Back, name, signcol, nil, Enum.Font.FredokaOne, 0.1)
  -- door + windows (front face at z = -4, facing +Z)
  local dx = s[14] or cx
  box(m, "Door", dx, 3.2, -3.9, 3.2, 6.4, 0.3, C3(90, 60, 40), Enum.Material.Wood)
  box(m, "DoorGlass", dx, 4.3, -3.75, 2.2, 2.6, 0.1, C3(170, 210, 230), Enum.Material.Glass, { Transparency = 0.25 })
  for _, side in { -1, 1 } do
    local wx = dx + side * (w / 4 + 1)
    if wx - 2.5 > x0 + 0.5 and wx + 2.5 < x1 - 0.5 then
      box(m, "Window", wx, 3.8, -3.85, 5, 4, 0.2, C3(150, 200, 225), Enum.Material.Glass, { Transparency = 0.15 })
      box(m, "Sill", wx, 1.7, -3.6, 5.6, 0.3, 0.7, C3(240, 240, 235))
    end
  end
  for k = 0, math.floor((w - 4) / 6) do
    local wx = x0 + 3 + k * 6 + ((w - 4) % 6) / 2
    if wx + 1.5 < x1 then box(m, "UpWindow", wx, h - 3.6, -3.88, 2.6, 3.2, 0.2, C3(150, 200, 225), Enum.Material.Glass, { Transparency = 0.15 }) end
  end
  -- striped awning
  for k = 0, 5 do
    local ax = dx - 4.5 + k * 1.8 + 0.9
    box(m, "Awning", ax, 7.3, -2.6, 1.8, 0.2, 2.8, (k % 2 == 0) and signcol or C3(250, 250, 250), Enum.Material.SmoothPlastic,
      { CFrame = CFrame.new(ax, 7.3, -2.6) * CFrame.Angles(math.rad(-18), 0, 0) })
  end
  if i % 4 == 0 then task.wait() end
end
b.Parent = town
return "buildings " .. #shops
'''

PROPS = r'''
local f = Instance.new("Folder"); f.Name = "Props"
-- NO SITTING signs: pole + red board (front faces +Z)
local function nosit(x, z, h, rotY, parent, wall)
  local base = CFrame.new(x, 0, z) * CFrame.Angles(0, rotY or 0, 0)
  if not wall then
    local pole = box(parent, "SignPole", 0, 0, 0, 0.3, h, 0.3, C3(120, 120, 125), Enum.Material.Metal)
    pole.CFrame = base * CFrame.new(0, h / 2, 0)
  end
  local board = box(parent, "NoSitting", 0, 0, 0, 3.4, 3.4, 0.25, C3(210, 30, 35), Enum.Material.SmoothPlastic)
  board.CFrame = base * CFrame.new(0, h + 1.2, 0.15)
  label(board, Enum.NormalId.Back, "NO\nSITTING", C3(255, 255, 255), nil, Enum.Font.FredokaOne, 0.14)
  local small = box(parent, "SignSmall", 0, 0, 0, 3.4, 0.8, 0.22, C3(250, 250, 250), Enum.Material.SmoothPlastic)
  small.CFrame = base * CFrame.new(0, h - 0.95, 0.15)
  label(small, Enum.NormalId.Back, "BY ORDER OF THE SIT POLICE", C3(200, 20, 30), nil, Enum.Font.GothamBlack, 0.12)
end
nosit(SIGN_X, SIGN_Z, 3.4, 0, f)
nosit(20.6, -3.75, 3.4, 0, f, true)
-- crates
local cx, cz = CRATE_X, CRATE_Z
local wood = C3(160, 112, 62)
local function crate(name, cf, s)
  local c = box(f, name, 0, 0, 0, s.X, s.Y, s.Z, wood, Enum.Material.WoodPlanks); c.CFrame = cf
  for _, e in { Vector3.new(0, s.Y / 2 - 0.15, 0), Vector3.new(0, -s.Y / 2 + 0.15, 0) } do
    local band = box(f, name .. "Band", 0, 0, 0, s.X + 0.06, 0.3, s.Z + 0.06, wood:Lerp(C3(0, 0, 0), 0.35), Enum.Material.Wood)
    band.CFrame = cf * CFrame.new(e)
  end
end
crate("CrateA", CFrame.new(cx, 1.6, cz), Vector3.new(4, 3.2, 4))
crate("CrateB", CFrame.new(cx + 0.1, 4.75, cz - 0.1) * CFrame.Angles(0, math.rad(12), 0), Vector3.new(3.6, 3.1, 3.6))
crate("CrateC", CFrame.new(cx - 0.2, 1.3, cz + 3.1) * CFrame.Angles(0, math.rad(-8), 0), Vector3.new(2.6, 2.6, 2.6))
crate("CrateD", CFrame.new(cx - 0.3, 1.2, cz - 3.0) * CFrame.Angles(0, math.rad(6), 0), Vector3.new(2.4, 2.4, 2.4))
-- lamps along the curb
for i = -6, 6 do
  local x = i * 16 + 4
  box(f, "LampPole", x, 5, 12.8, 0.35, 10, 0.35, C3(45, 48, 55), Enum.Material.Metal)
  box(f, "LampArm", x, 9.9, 12.0, 0.25, 0.25, 1.8, C3(45, 48, 55), Enum.Material.Metal)
  box(f, "LampHead", x, 9.7, 11.2, 0.9, 0.35, 0.9, C3(255, 240, 200), Enum.Material.Neon)
end
-- trees across the road and in planters
local function tree(x, z, s)
  box(f, "Trunk", x, 2.5 * s, z, 0.9 * s, 5 * s, 0.9 * s, C3(105, 72, 45), Enum.Material.Wood)
  local l = P(f, { Class = "Part", Name = "Leaves", Shape = Enum.PartType.Ball, Size = Vector3.new(6, 6, 6) * s,
    CFrame = CFrame.new(x, 6.2 * s, z), Color = C3(70 + (x % 3) * 8, 140, 62), Material = Enum.Material.Grass })
  P(f, { Class = "Part", Name = "Leaves2", Shape = Enum.PartType.Ball, Size = Vector3.new(4.4, 4.4, 4.4) * s,
    CFrame = CFrame.new(x + 1.2 * s, 7.6 * s, z - 0.8 * s), Color = C3(84, 156, 70), Material = Enum.Material.Grass })
end
for i = -6, 6 do tree(i * 12 + 3, 49 + (i % 2) * 3, 1.1 + (i % 3) * 0.12) end
tree(-44, 11.0, 0.8); tree(36, 11.0, 0.8)
box(f, "PlanterA", -44, 0.5, 11.0, 2.6, 1, 2.6, C3(150, 150, 150), Enum.Material.Concrete)
box(f, "PlanterB", 36, 0.5, 11.0, 2.6, 1, 2.6, C3(150, 150, 150), Enum.Material.Concrete)
-- flower boxes in front of Mrs. Lee's shop
for _, x in { 2.2, 11.8 } do
  box(f, "FlowerBox", x, 0.6, -3.0, 3.2, 1.2, 1.4, C3(120, 80, 50), Enum.Material.Wood)
  for k = 0, 4 do
    P(f, { Class = "Part", Name = "Flower", Shape = Enum.PartType.Ball, Size = Vector3.new(0.8, 0.8, 0.8),
      CFrame = CFrame.new(x - 1.2 + k * 0.6, 1.45, -3.0 + ((k % 2) - 0.5) * 0.5),
      Color = ({ C3(240, 80, 120), C3(250, 200, 60), C3(230, 100, 200) })[k % 3 + 1], Material = Enum.Material.SmoothPlastic })
  end
end
box(f, "TrashCan", -8.2, 1.4, 1.0, 1.6, 2.8, 1.6, C3(60, 110, 70), Enum.Material.Metal)
box(f, "Hydrant", 31.0, 1.0, 12.0, 0.9, 2.0, 0.9, C3(210, 40, 40), Enum.Material.Metal)
f.Parent = town
return "props"
'''

BENCH = r'''
local old = town:FindFirstChild("Bench"); if old then old:Destroy() end
local m = Instance.new("Model"); m.Name = "Bench"
local cx, cz, L, top = BX, BZ, BL, SEAT_TOP
local wood, metal = Color3.fromRGB(150, 95, 55), Color3.fromRGB(40, 42, 48)
for k = 0, 2 do
  box(m, "Slat", cx, top - 0.12, cz - 0.6 + k * 0.45, L, 0.24, 0.4, wood, Enum.Material.WoodPlanks)
end
for k = 0, 1 do
  local back = box(m, "Back", 0, 0, 0, L, 0.5, 0.18, wood, Enum.Material.WoodPlanks)
  back.CFrame = CFrame.new(cx, top + 0.9 + k * 0.7, cz - 1.05) * CFrame.Angles(math.rad(-12), 0, 0)
end
local seat = box(m, "Seat", cx, top - 0.35, cz, L, 0.2, 1.8, wood, Enum.Material.WoodPlanks, { Transparency = 1, CanCollide = false })
for _, sx in { -1, 1 } do
  box(m, "Leg", cx + sx * (L / 2 - 0.5), (top - 0.24) / 2, cz - 0.3, 0.25, top - 0.24, 1.1, metal, Enum.Material.Metal)
  local arm = box(m, "BackLeg", 0, 0, 0, 0.25, 1.9, 0.25, metal, Enum.Material.Metal)
  arm.CFrame = CFrame.new(cx + sx * (L / 2 - 0.5), top + 0.8, cz - 1.0) * CFrame.Angles(math.rad(-12), 0, 0)
end
m.Parent = town
return "bench top=" .. top
'''

LIGHT = r'''
-- "cinematic" look (look-dev A/B vs the old flat preset): max render quality, full environment specular (the plastic
-- sheen the reference shorts have), crisp sun shadows, bloom, a warm grade and a depth of field that
-- D.cutaway() refocuses on the camera's aim point every frame. 2026-11-17 critic: ours read darker and hazier than the
-- references (bright, saturated, crisp): exposure up, haze off, more saturation, a lighter background blur.
-- User: the glare on floors and teeth was unbearable -> specular 0.2, weak high-threshold bloom, no sun glare.
pcall(function() settings().Rendering.EditQualityLevel = Enum.QualityLevel.Level21 end)
pcall(function() settings().Rendering.MeshPartDetailLevel = Enum.MeshPartDetailLevel.Level04 end)
local L = game:GetService("Lighting")
L.ClockTime = 16.2; L.GeographicLatitude = 35; L.Brightness = 2.6; L.ExposureCompensation = 0.1
L.Ambient = Color3.fromRGB(140, 134, 142); L.OutdoorAmbient = Color3.fromRGB(120, 120, 135)
L.EnvironmentDiffuseScale = 1; L.EnvironmentSpecularScale = 0.2; L.GlobalShadows = true; L.ShadowSoftness = 0.12
for _, o in L:GetChildren() do
  if o:IsA("Atmosphere") or o:IsA("PostEffect") then o:Destroy() end
end
local a = Instance.new("Atmosphere"); a.Name = "PromptimateAtmos"; a.Density = 0.15; a.Offset = 0.1; a.Haze = 0.0; a.Glare = 0
a.Color = Color3.fromRGB(205, 220, 240); a.Decay = Color3.fromRGB(150, 135, 120); a.Parent = L
local cc = Instance.new("ColorCorrectionEffect"); cc.Name = "PromptimateCC"; cc.Saturation = 0.32; cc.Contrast = 0.12
cc.Brightness = 0.02; cc.TintColor = Color3.fromRGB(255, 255, 255); cc.Parent = L
local bl = Instance.new("BloomEffect"); bl.Name = "PromptimateBloom"; bl.Intensity = 0.25; bl.Size = 24; bl.Threshold = 1.6; bl.Parent = L
local sr = Instance.new("SunRaysEffect"); sr.Name = "PromptimateRays"; sr.Intensity = 0.04; sr.Spread = 0.6; sr.Parent = L
local dof = Instance.new("DepthOfFieldEffect"); dof.Name = "PromptimateDOF"; dof.FarIntensity = 0.12; dof.NearIntensity = 0
dof.FocusDistance = 10; dof.InFocusRadius = 6; dof.Parent = L
return "lighting"
'''

SHOPS = [  # x0, x1, height, body rgb, name, sign rgb, sign-text rgb, door x
    (-70, -40, 18, (176, 120, 96), "HARDWARE", (40, 60, 90), (255, 230, 120), None),
    (-40, -18, 16, (214, 170, 120), "BAKERY", (120, 70, 40), (255, 236, 200), None),
    (-18, -2, 20, (120, 150, 190), "BOOKS", (35, 45, 80), (255, 255, 255), None),
    (-2, 17, 15, (245, 222, 230), "FLOWERS", (220, 90, 140), (255, 255, 255), 7.0),
    (17, 39, 18, (230, 190, 90), "TOYS", (200, 50, 50), (255, 255, 255), 33.0),
    (39, 70, 16, (150, 175, 140), "CAFE", (60, 90, 60), (255, 240, 210), None),
]


def shops_lua() -> str:
    rows = []
    for x0, x1, h, col, name, sign, txt, door in SHOPS:
        rows.append("{" + ",".join(map(str, [x0, x1, h, *col])) + f',"{name}",' + ",".join(map(str, [*sign, *txt]))
                    + (f",{door}" if door is not None else "") + "}")
    return "{" + ",".join(rows) + "}"


def bench_code(seat_top: float) -> str:
    (bx, bz), bl = S.BENCH["center"], S.BENCH["length"]
    return (LIB + "town = workspace.Town\n" + BENCH).replace("BX", str(bx)).replace("BZ", str(bz)) \
        .replace("BL", str(bl)).replace("SEAT_TOP", f"{seat_top:.3f}")


async def build(seat_top: float, shot: bool, lighting_only: bool = False):
    async with StudioSession() as s:
        await asyncio.sleep(3)
        steps = [LIB + GROUND, LIB + "town = workspace.Town\n" + BUILDINGS.replace("SHOPS", shops_lua()),
                 LIB + "town = workspace.Town\n" + PROPS.replace("SIGN_X", str(S.SIGN_BENCH[0])).replace("SIGN_Z", str(S.SIGN_BENCH[1]))
                 .replace("CRATE_X", str(S.CRATES[0])).replace("CRATE_Z", str(S.CRATES[1])),
                 bench_code(seat_top), LIGHT]
        for code in (steps if not lighting_only else steps[-1:]):
            r = await s.luau(code)
            print(r["content"][0][:300] if r["content"] else r, flush=True)
            if r["isError"]:
                raise SystemExit(1)
        if shot:
            out = ROOT / ".cache" / "roblox_short"
            out.mkdir(parents=True, exist_ok=True)
            for i, (cam, look) in enumerate([((0, 30, 60), (5, 0, 0)), ((-2, 13, 30), (-4, 2, 2)), ((24, 5, 14), (12, 2, 4))]):
                c = await s.call("screen_capture", {"capture_id": f"town{i}", "camera_position": list(cam), "look_at_position": list(look)})
                for x in c["content"]:
                    if isinstance(x, dict) and x.get("data"):
                        (out / f"town{i}.png").write_bytes(base64.b64decode(x["data"]))
            print("saved overview captures", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seat-top", type=float, default=1.05)
    ap.add_argument("--shot", action="store_true")
    ap.add_argument("--bench-only", action="store_true")
    ap.add_argument("--lighting-only", action="store_true")
    a = ap.parse_args()
    if a.bench_only:
        async def _b():
            async with StudioSession() as s:
                print((await s.luau(bench_code(a.seat_top)))["content"])
        asyncio.run(_b())
    else:
        asyncio.run(build(a.seat_top, a.shot, a.lighting_only))
