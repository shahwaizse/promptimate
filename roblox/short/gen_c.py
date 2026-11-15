"""Version C (Roblox Prompt-to-Animation): generate the non-stock beats with Studio's MCP `generate_animation`.

    .venv\\Scripts\\python.exe roblox\\short\\gen_c.py [--only key,key]

Hard cap: 12 generations per run of this project (each one publishes an animation asset to the logged-in Roblox
account; that's how the tool works). Writes .cache/roblox_short/c_gens.json with latency, asset id and the
KeyframeSequence (renamed to C_<key> in ServerStorage.RBX_ASSISTANT_ANIMGEN so similar prompts can't collide).
Prompts follow Roblox's own guide (who moves and how they feel, 'then' for sequences, body not objects, 'in place').
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "roblox" / "tools"))
sys.path.insert(0, str(HERE))
import story as S  # noqa: E402
from studio_mcp import StudioSession  # noqa: E402

OUT = ROOT / ".cache" / "roblox_short" / "c_gens.json"
CAP = 12

PLAN = [  # key, rig, prompt, seconds
    ("t_sit", "GenKid", "A tired kid sits down on a bench, then leans back and relaxes", 3.0),
    ("t_phone", "GenKid", "A kid sitting on a bench holds a phone to their right ear, then looks shocked", 3.5),
    # first try (1.0 s, "jumps up from sitting on a bench to standing") failed server-side: "Malformed Output"
    ("t_up", "GenKid", "A panicked kid quickly stands up from sitting on a bench", 2.0),
    # first try (7.7 s, four steps) failed server-side: "Malformed Output"
    ("t_hide", "GenKid", "A scared kid crouches down to hide, then leans to the left to peek out, then hides again", 6.0),
    ("t_fall", "GenKid", "A kid gets startled, jumps backward and falls down onto the ground", 2.5),
    ("t_ground", "GenKid", "A kid sits on the ground leaning back on their hands and looks up nervously", 7.1),
    ("o_look", "GenAdult", "A police officer stands in place and looks around to the left and to the right, searching", 3.0),
    ("o_talk", "GenAdult", "A police officer stands in place and talks, gesturing with both hands", 3.5),
    ("o_sit", "GenAdult", "A tired police officer sits down on the ground", 3.6),
]

RIGS = r'''
local Players = game:GetService("Players")
local out = {}
for name, spec in { GenKid = {0.85, 0.9, 200}, GenAdult = {1.0, 1.0, 210} } do
  local r = workspace:FindFirstChild(name)
  if not r then
    local d = Instance.new("HumanoidDescription"); d.HeightScale = spec[1]; d.WidthScale = spec[2]; d.DepthScale = spec[2]
    r = Players:CreateHumanoidModelFromDescription(d, Enum.HumanoidRigType.R15)
    r.Name = name; r.Parent = workspace
    r:PivotTo(CFrame.new(spec[3], r.Humanoid.HipHeight + r.HumanoidRootPart.Size.Y / 2, -200))
    r.HumanoidRootPart.Anchored = true
  end
  table.insert(out, r:GetFullName())
end
return table.concat(out, " ")
'''

RENAME = r'''
local f = game:GetService("ServerStorage"):FindFirstChild("RBX_ASSISTANT_ANIMGEN")
local k = f and f:FindFirstChild(__SRC__)
if not k then return "missing" end
local old = f:FindFirstChild(__DST__); if old and old ~= k then old:Destroy() end
k.Name = __DST__
local n = 0; local last = 0
for _, kf in k:GetChildren() do if kf:IsA("Keyframe") then n += 1; last = math.max(last, kf.Time) end end
return string.format("%d keyframes, %.2f s", n, last)
'''


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    res = json.loads(OUT.read_text()) if OUT.exists() else {}
    used = sum(v.get("attempts", 1) for v in res.values())
    async with StudioSession() as s:
        await asyncio.sleep(3)
        print((await s.luau(RIGS))["content"], flush=True)
        for key, rig, prompt, secs in PLAN:
            if (only and key not in only) or (key in res and res[key].get("clip") and key not in only):
                continue
            if used >= CAP:
                print(f"cap of {CAP} generations reached; skipping {key}", flush=True)
                break
            used += 1
            t0 = time.time()
            g = await s.call("generate_animation", {"textPrompt": prompt, "duration": secs, "instance_path": f"Workspace.{rig}"})
            lat = round(time.time() - t0, 1)
            entry = {"prompt": prompt, "seconds": secs, "rig": rig, "latency_s": lat,
                     "attempts": res.get(key, {}).get("attempts", 0) + 1}
            try:
                info = json.loads(g["content"][0]) if not g["isError"] else {"error": g["content"]}
            except Exception:
                info = {"raw": g["content"]}
            if "clipPath" in info:
                src = info["clipPath"].split(".")[-1]
                r = await s.luau(RENAME.replace("__SRC__", json.dumps(src)).replace("__DST__", json.dumps("C_" + key)))
                entry.update({"clip": "C_" + key, "asset": info.get("publishedAssetId"), "source_name": src,
                              "kfs": r["content"][0] if r["content"] else None})
            else:
                entry["error"] = info
            res[key] = entry
            OUT.write_text(json.dumps(res, indent=1))
            print(f"{key}: {lat}s {entry.get('kfs') or entry.get('error')}", flush=True)
            await asyncio.sleep(2)
    print(f"generations used: {used}/{CAP}")


if __name__ == "__main__":
    asyncio.run(main())
