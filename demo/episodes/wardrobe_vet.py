"""Try every wardrobe combo on a classic R6 body (shirt + pants + hair + extras) and render a labelled lineup so fits
can be judged by eye. usage: wardrobe_vet.py wardrobe.json out_prefix [armWidth]"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server")); sys.path.insert(0, str(ROOT / "roblox" / "short"))
from PIL import Image, ImageDraw  # noqa: E402

import roblox_record as RR  # noqa: E402
import roblox_tools as RT  # noqa: E402
import fastgrab as FG  # noqa: E402
from roblox_studio import studio  # noqa: E402

W = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["wardrobe"]
prefix = sys.argv[2]
arm = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
combos = []
for arch, lst in W.items():
    for c in lst:
        hats = [str(e["id"]) for e in c.get("extra_slots", []) if e.get("slot") == "HatAccessory"]
        faces = [str(e["id"]) for e in c.get("extra_slots", []) if e.get("slot") == "FaceAccessory"]
        combos.append({"label": f"{arch}/{c.get('variant', '')}", "Shirt": c["shirt"], "Pants": c["pants"],
                       "hair": str(c["hair"][0]) if c.get("hair") else "", "hats": ",".join(hats), "faces": ",".join(faces)})
st = studio(); RT.install(); RR._ensure_running(); vp = RR._viewport()
BUILD = r'''
local Players = game:GetService("Players")
local F = require(game:GetService("ReplicatedStorage").Promptimate.Faces:Clone())
local f = workspace:FindFirstChild("WardVet") or Instance.new("Folder"); f.Name = "WardVet"; f.Parent = workspace
for _, c in f:GetChildren() do c:Destroy() end
local p = Instance.new("Part"); p.Anchored = true; p.Size = Vector3.new(120, 1, 40); p.CFrame = CFrame.new(1100, -0.5, 500)
p.Material = Enum.Material.WoodPlanks; p.Color = Color3.fromRGB(170, 120, 80); p.Parent = f
local w = Instance.new("Part"); w.Anchored = true; w.Size = Vector3.new(120, 30, 1); w.CFrame = CFrame.new(1100, 15, 490)
w.Material = Enum.Material.Plaster; w.Color = Color3.fromRGB(225, 215, 200); w.Parent = f
local C = game:GetService("HttpService"):JSONDecode([==[__C__]==])
local out = {}
for i, c in C do
  local ok, err = pcall(function()
    local d = Instance.new("HumanoidDescription"); local sk = Color3.fromRGB(255, 204, 153)
    d.HeadColor, d.LeftArmColor, d.RightArmColor, d.TorsoColor, d.LeftLegColor, d.RightLegColor = sk, sk, sk, sk, sk, sk
    d.Shirt = c.Shirt; d.Pants = c.Pants; d.HairAccessory = c.hair; d.HatAccessory = c.hats; d.FaceAccessory = c.faces
    local m = Players:CreateHumanoidModelFromDescription(d, Enum.HumanoidRigType.R6)
    m.Name = "W" .. i; m.Parent = f; m.HumanoidRootPart.Anchored = true
    m.Humanoid.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
    m:PivotTo(CFrame.new(1050 + (i - 1) * 6, 3, 500) * CFrame.Angles(0, math.pi, 0))
    local ll = m["Left Leg"]; m:PivotTo(m:GetPivot() + Vector3.new(0, -(ll.Position.Y - ll.Size.Y / 2), 0))
    for _, x in m.Head:GetChildren() do if x:IsA("Decal") then x:Destroy() end end
    pcall(function() F.set(m, "happy") end)
    local tor = m.Torso
    for _, side in { "Left", "Right" } do
      local a, j = m[side .. " Arm"], tor[side .. " Shoulder"]
      local wv = __ARM__
      if wv < 1 then a.Size = Vector3.new(wv, 2, wv); local p1 = j.C1.Position; j.C1 = CFrame.new(p1.X * wv, p1.Y, p1.Z * wv) * j.C1.Rotation end
    end
  end)
  out[i] = ok and "ok" or tostring(err)
end
return game:GetService("HttpService"):JSONEncode(out)'''
tiles = []
for b0 in range(0, len(combos), 12):
    batch = combos[b0:b0 + 12]
    r = st.luau_json(BUILD.replace("__C__", json.dumps(batch)).replace("__ARM__", str(arm)), timeout=600)
    st.luau("task.wait(2) return 1")
    FG.pin_studio(True); rect = FG.calibrate(st, vp)
    for i, c in enumerate(batch):
        x = 1050 + i * 6
        im = FG.portrait(st, rect, vp, [x + 2.2, 3.6, 509], [x, 2.9, 500], 36).resize((216, 384))
        dr = ImageDraw.Draw(im)
        dr.rectangle((0, 0, 216, 14), fill=(0, 0, 0)); dr.text((3, 1), c["label"][:34], fill=(255, 255, 0))
        if r.get(str(i + 1), r[i] if isinstance(r, list) else "ok") != "ok":
            dr.text((3, 20), "ERR", fill=(255, 0, 0))
        tiles.append(im)
cols = 10
sheet = Image.new("RGB", (216 * cols, 384 * math.ceil(len(tiles) / cols)))
for i, t in enumerate(tiles):
    sheet.paste(t, (216 * (i % cols), 384 * (i // cols)))
sheet.save(prefix + ".jpg"); print(prefix + ".jpg", len(tiles))
st.luau('local f = workspace:FindFirstChild("WardVet"); if f then f:Destroy() end return 1')
