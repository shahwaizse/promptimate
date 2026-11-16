"""Measure two characters sitting side by side on one bench (the short's ending), on the real rigs in Studio:
hips distance, body parts of one rig intersecting the other's (oriented boxes), and each one's seat contact
(pelvis/thigh underside vs the seat top).

    .venv\\Scripts\\python.exe demo\\roblox_short\\two_sitters.py [t=35.8] [A=Timmy] [B=Officer] [seat=Bench2]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server"))
from roblox_studio import studio  # noqa: E402

CODE = r'''
local HttpService = game:GetService("HttpService")
local D = require(game:GetService("ReplicatedStorage").Promptimate.ShortDirector:Clone())
D.load(); D.seek(__T__)
local A, B = "__A__", "__B__"
local pa, pb = D.poseActor(A, __T__), D.poseActor(B, __T__)
local ta, tb = pa.targets, pb.targets
local ra, rb = D.actors[A].rig, D.actors[B].rig
local overlaps, pairs = {}, 0
for _, na in D.BODY do for _, nb in D.BODY do
  pairs += 1
  if D.obbOverlap(ta[na], ra[na].Size * 0.9, tb[nb], rb[nb].Size * 0.9) then table.insert(overlaps, na .. "/" .. nb) end
end end
local seat = workspace:FindFirstChild("__SEAT__", true)
local top = -math.huge
for _, p in seat:GetDescendants() do if p:IsA("BasePart") and p.Name == "Slat" then top = math.max(top, p.Position.Y + p.Size.Y / 2) end end
local function under(t, r)
  local best = math.huge
  for _, n in { "LowerTorso", "LeftUpperLeg", "RightUpperLeg" } do
    local cf, s = t[n], r[n].Size / 2
    for _, sx in { -1, 1 } do for _, sz in { -1, 1 } do
      local y = (cf * Vector3.new(sx * s.X, (n == "LowerTorso") and -s.Y or s.Y * 0.4, sz * s.Z)).Y
      best = math.min(best, y)
    end end
  end
  return best
end
local ha, hb = ta.LowerTorso.Position, tb.LowerTorso.Position
return HttpService:JSONEncode({ hips_distance = (Vector3.new(ha.X, 0, ha.Z) - Vector3.new(hb.X, 0, hb.Z)).Magnitude,
  shoulder_width_A = ra.UpperTorso.Size.X, shoulder_width_B = rb.UpperTorso.Size.X,
  overlapping_part_pairs = overlaps, pairs = pairs, seat_top = top,
  contact_A = under(ta, ra) - top, contact_B = under(tb, rb) - top,
  hips_A = { ha.X, ha.Y, ha.Z }, hips_B = { hb.X, hb.Y, hb.Z } })
'''


def main():
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    t, A, B, seat = float(args.get("t", 35.8)), args.get("A", "Timmy"), args.get("B", "Officer"), args.get("seat", "Bench2")
    res = studio().luau_json(CODE.replace("__T__", f"{t:.3f}").replace("__A__", A).replace("__B__", B)
                             .replace("__SEAT__", seat))
    out = ROOT / ".cache" / "roblox_short" / "v2" / "two_sitters.json"
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
