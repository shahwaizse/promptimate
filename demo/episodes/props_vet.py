"""Contact sheet of the prop library: each prop next to a classic character for scale, 3/4 view, in the look-dev
light. usage: props_vet.py out.jpg [key ...]"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server")); sys.path.insert(0, str(ROOT / "roblox" / "short"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageDraw  # noqa: E402

import roblox_record as RR  # noqa: E402
import fastgrab as FG  # noqa: E402
import sets as SETS  # noqa: E402
from roblox_studio import studio  # noqa: E402

st = studio(); RR._ensure_running(); vp = RR._viewport()
lib = SETS.library()
keys = sys.argv[2:] or sorted(lib)
SETUP = r'''
local f = workspace:FindFirstChild("PropVet") or Instance.new("Folder"); f.Name = "PropVet"; f.Parent = workspace
for _, c in f:GetChildren() do c:Destroy() end
local p = Instance.new("Part"); p.Anchored = true; p.Size = Vector3.new(80, 1, 80); p.CFrame = CFrame.new(1100, -0.5, 300)
p.Material = Enum.Material.WoodPlanks; p.Color = Color3.fromRGB(170, 120, 80); p.Parent = f
local w = Instance.new("Part"); w.Anchored = true; w.Size = Vector3.new(80, 30, 1); w.CFrame = CFrame.new(1100, 15, 280)
w.Material = Enum.Material.Plaster; w.Color = Color3.fromRGB(225, 215, 200); w.Parent = f
local d = Instance.new("HumanoidDescription"); local sk = Color3.fromRGB(255, 204, 153)
d.HeadColor, d.LeftArmColor, d.RightArmColor = sk, sk, sk; d.TorsoColor = Color3.fromRGB(13, 105, 172)
d.LeftLegColor = Color3.fromRGB(40, 127, 71); d.RightLegColor = d.LeftLegColor
local m = game:GetService("Players"):CreateHumanoidModelFromDescription(d, Enum.HumanoidRigType.R6)
m.Name = "Scale"; m.Parent = f; m.HumanoidRootPart.Anchored = true
m:PivotTo(CFrame.new(1097, 3, 300) * CFrame.Angles(0, math.pi, 0))
local ll = m["Left Leg"]; m:PivotTo(m:GetPivot() + Vector3.new(0, -(ll.Position.Y - ll.Size.Y / 2), 0))
return 1'''
SHOW = r'''
local f = workspace.PropVet
local old = f:FindFirstChild("Item"); if old then old:Destroy() end
local m = game:GetService("ServerStorage").PromptimateProps:FindFirstChild("__K__"):Clone()
m.Name = "Item"; m:PivotTo(CFrame.new(1101.5, 0, 300)); m.Parent = f
local cf, s = m:GetBoundingBox()
return game:GetService("HttpService"):JSONEncode({ s.X, s.Y, s.Z, cf.X, cf.Y, cf.Z })'''
st.luau(SETUP)
st.luau("task.wait(1.5) return 1")
FG.pin_studio(True); rect = FG.calibrate(st, vp)
tiles = []
for k in keys:
    sx, sy, sz, cx, cy, cz = json.loads(st.luau(SHOW.replace("__K__", k)))
    span = max(sy, 5.4, max(sx, sz) * 0.7) + 1.0
    d = span * 1.55
    a = math.radians(30)
    look = [1099.5, max(cy, 2.7) * 0.9, 300]
    cam = [look[0] + d * math.sin(a), look[1] + span * 0.25, 300 + d * math.cos(a)]
    st.luau("task.wait(0.5) return 1")
    im = FG.portrait(st, rect, vp, cam, look, 40).resize((270, 480))
    dr = ImageDraw.Draw(im)
    dr.rectangle((0, 0, 270, 16), fill=(0, 0, 0)); dr.text((4, 2), f"{k} {sx:.1f}x{sy:.1f}x{sz:.1f}", fill=(255, 255, 0))
    tiles.append(im)
cols = 8
sheet = Image.new("RGB", (270 * cols, 480 * math.ceil(len(tiles) / cols)))
for i, t in enumerate(tiles):
    sheet.paste(t, (270 * (i % cols), 480 * (i // cols)))
sheet.save(sys.argv[1]); print(sys.argv[1])
st.luau('local f = workspace:FindFirstChild("PropVet"); if f then f:Destroy() end return 1')
