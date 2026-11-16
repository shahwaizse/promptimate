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
