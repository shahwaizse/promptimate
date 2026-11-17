"""The asset library the Studio-free pipeline renders from, exported from Studio once (cloud machines ship the files):

    props.json   every prop model in ServerStorage.PromptimateProps: parts relative to the model pivot
    looks.json   every character look: R6 body colours, clothing templates, accessories with their offset from the
                 body part they're welded to

    python roblox/headless/library.py props        # the prop library
    python roblox/headless/library.py looks        # the looks of the rigs currently in workspace (cast them first)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export as X  # noqa: E402
import studio_io as S  # noqa: E402
from pipeline import CACHE  # noqa: E402

LIB = CACHE / "lib"

PROPS = X.PART_LUAU + r'''
local lib = game:GetService("ServerStorage"):FindFirstChild("PromptimateProps")
local out = {}
for _, m in (lib and lib:GetChildren() or {}) do
  if m:IsA("Model") then
    local pv = m:GetPivot()
    local _, size = m:GetBoundingBox()
    local parts = {}
    for _, p in m:GetDescendants() do
      if p:IsA("BasePart") and p.Transparency < 0.98 then
        local ok, r = pcall(info, p)
        if ok then
          local x, y, z, a, b, c, d, e, f, g, h, i = pv:ToObjectSpace(p.CFrame):GetComponents()
          r.cf = { x, y, z, a, b, c, d, e, f, g, h, i }; r.name = p.Name
          table.insert(parts, r)
        end
      end
    end
    out[m.Name] = { size = { size.X, size.Y, size.Z }, parts = parts }
  end
end
_G.PromptimateSend("props", game:GetService("HttpService"):JSONEncode(out))
'''

LOOKS = X.PART_LUAU + r'''
local BODY = { Torso = true, Head = true, ["Left Arm"] = true, ["Right Arm"] = true, ["Left Leg"] = true, ["Right Leg"] = true }
local out = {}
for _, rig in workspace:GetDescendants() do
  if rig:IsA("Model") and rig:FindFirstChildOfClass("Humanoid") and rig:FindFirstChild("Torso") then
    local look = rig:GetAttribute("PromptimateLook") or rig.Name
    local shirt, pants, tee = rig:FindFirstChildOfClass("Shirt"), rig:FindFirstChildOfClass("Pants"), rig:FindFirstChildOfClass("ShirtGraphic")
    local body, acc = {}, {}
    for n in BODY do
      local p = rig:FindFirstChild(n)
      if p then local ok, r = pcall(info, p); if ok then r.name = n; body[n] = r end end
    end
    for _, p in rig:GetDescendants() do
      if p:IsA("BasePart") and not BODY[p.Name] and p.Name ~= "HumanoidRootPart" and p.Transparency < 0.98 then
        -- the body part it hangs on: the other side of its weld
        local host
        for _, w in p:GetDescendants() do
          if (w:IsA("Weld") or w:IsA("WeldConstraint") or w:IsA("Motor6D")) then
            local o = (w.Part0 == p) and w.Part1 or w.Part0
            if o and BODY[o.Name] then host = o end
          end
        end
        host = host or rig:FindFirstChild("Head")
        local ok, r = pcall(info, p)
        if ok then
          local x, y, z, a, b, c, d, e, f, g, h, i = host.CFrame:ToObjectSpace(p.CFrame):GetComponents()
          r.rel = { x, y, z, a, b, c, d, e, f, g, h, i }; r.host = host.Name; r.name = p.Name
          table.insert(acc, r)
        end
      end
    end
    out[look] = { actor = rig.Name, shirt = shirt and shirt.ShirtTemplate or "", pants = pants and pants.PantsTemplate or "",
      tee = tee and tee.Graphic or "", body = body, acc = acc, arms = rig:GetAttribute("PromptimateArms") or 1 }
  end
end
_G.PromptimateSend("looks", game:GetService("HttpService"):JSONEncode(out))
'''


def export_props() -> dict:
    LIB.mkdir(parents=True, exist_ok=True)
    d = json.loads(S.luau_send(PROPS, "props"))
    (LIB / "props.json").write_text(json.dumps(d))
    return d


def export_looks(merge: bool = True) -> dict:
    LIB.mkdir(parents=True, exist_ok=True)
    d = json.loads(S.luau_send(LOOKS, "looks"))
    p = LIB / "looks.json"
    if merge and p.exists():
        old = json.loads(p.read_text())
        old.update(d)
        d = old
    p.write_text(json.dumps(d))
    return d


def props() -> dict:
    return json.loads((LIB / "props.json").read_text())


def looks() -> dict:
    return json.loads((LIB / "looks.json").read_text())


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "props"
    r = export_props() if what == "props" else export_looks()
    print(what, len(r), sorted(r)[:12])
