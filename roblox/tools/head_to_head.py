"""Head-to-head on identical R15 avatars in Roblox Studio: Roblox's own Prompt-to-Animation (Studio MCP
`generate_animation`) vs Promptimate (default pipeline, retargeted with mcp_server/roblox.py).

For each benchmark prompt: generate with both, play both on side-by-side R15 rigs (Run mode), read every frame's joint
positions back from Roblox, convert to metres in Kimodo space and score with mcp_server/metrics.py (the same
expectations as bench/prompts.json), time both, and save side-by-side screen captures.

Note: each Roblox generation publishes an animation asset to the logged-in account (that's how the tool works).

Usage: .venv\\Scripts\\python roblox\\tools\\head_to_head.py [--prompts id1,id2] [--reuse]
Writes .cache/roblox_h2h/results.json and per-prompt captures.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("UNITY_PROJECT", str(ROOT / ".cache" / "no_unity_project"))
import metrics  # noqa: E402
import motion  # noqa: E402
import roblox  # noqa: E402
from studio_mcp import StudioSession  # noqa: E402
from validate_in_studio import upload_code  # noqa: E402

OUT = ROOT / ".cache" / "roblox_h2h"
DEFAULT = ["wave", "jump", "sit_floor", "punch", "death_fall", "sneak", "phone_call", "strafe_left"]

# R15 sample points -> SOMA joint indices (see motion.NAMES); "part:attachment" or "part:@center" / "part:@toe"
POINTS = {
    0: "LowerTorso:RootRigAttachment", 1: "UpperTorso:WaistRigAttachment", 2: "UpperTorso:WaistRigAttachment",
    3: "UpperTorso:@center", 4: "Head:NeckRigAttachment", 5: "Head:NeckRigAttachment", 6: "Head:@center",
    7: "Head:@center", 8: "Head:@center", 9: "Head:@center",
    10: "UpperTorso:LeftShoulderRigAttachment", 11: "LeftUpperArm:LeftShoulderRigAttachment",
    12: "LeftLowerArm:LeftElbowRigAttachment", 13: "LeftHand:LeftWristRigAttachment", 14: "LeftHand:LeftGripAttachment",
    15: "LeftHand:LeftGripAttachment", 16: "UpperTorso:RightShoulderRigAttachment",
    17: "RightUpperArm:RightShoulderRigAttachment", 18: "RightLowerArm:RightElbowRigAttachment",
    19: "RightHand:RightWristRigAttachment", 20: "RightHand:RightGripAttachment", 21: "RightHand:RightGripAttachment",
    22: "LeftUpperLeg:LeftHipRigAttachment", 23: "LeftLowerLeg:LeftKneeRigAttachment", 24: "LeftFoot:@center",
    25: "LeftFoot:@toe", 26: "RightUpperLeg:RightHipRigAttachment", 27: "RightLowerLeg:RightKneeRigAttachment",
    28: "RightFoot:@center", 29: "RightFoot:@toe",
}

SETUP = r'''
local Players = game:GetService("Players")
local function rig(name, x)
  local r = workspace:FindFirstChild(name)
  if r then r:Destroy() end
  r = Players:CreateHumanoidModelFromDescription(Instance.new("HumanoidDescription"), Enum.HumanoidRigType.R15)
  r.Name = name; r.Parent = workspace
  local hum = r:FindFirstChildOfClass("Humanoid")
  r:PivotTo(CFrame.new(x, hum.HipHeight + r.HumanoidRootPart.Size.Y / 2, 0))
  r.HumanoidRootPart.Anchored = true
  return r:GetFullName()
end
for _, n in {"PromptimateProbe", "RobloxGenRig"} do local o = workspace:FindFirstChild(n); if o then o:Destroy() end end
local RS = game:GetService("RunService")
if not RS:IsRunning() then RS:Run() end
local out = rig("H2H_Promptimate", -4) .. " " .. rig("H2H_Roblox", 4)
-- colour code: blue = Promptimate (left), orange = Roblox (right)
for name, col in { H2H_Promptimate = Color3.fromRGB(70, 130, 220), H2H_Roblox = Color3.fromRGB(235, 140, 50) } do
  for _, p in workspace[name]:GetDescendants() do
    if p:IsA("BasePart") and p.Name ~= "HumanoidRootPart" then p.Color = col end
  end
  local bc = workspace[name]:FindFirstChildOfClass("BodyColors")
  if bc then bc:Destroy() end
end
return out
'''

SAMPLE = r'''
local HttpService = game:GetService("HttpService")
local POINTS = __POINTS__   -- array of unique "part:what" specs
local MODE, NAME, FRAMES, FPS = __MODE__, __NAME__, __FRAMES__, 30
local rig = workspace[MODE == "promptimate" and "H2H_Promptimate" or "H2H_Roblox"]
local function read()
  local row = {}
  for _, spec in POINTS do
    local partName, what = string.match(spec, "^(.-):(.+)$")
    local part = rig[partName]
    local p
    if what == "@center" then p = part.Position
    elseif what == "@toe" then p = (part.CFrame * CFrame.new(0, -part.Size.Y / 2, -part.Size.Z / 2)).Position
    else p = part:FindFirstChild(what).WorldPosition end
    table.insert(row, string.format("%.2f,%.2f,%.2f", p.X, p.Y, p.Z))
  end
  return table.concat(row, ",")
end
local lowest = math.min(rig.LeftFoot.Position.Y - rig.LeftFoot.Size.Y / 2, rig.RightFoot.Position.Y - rig.RightFoot.Size.Y / 2)
local stand = rig.LowerTorso.Position.Y - lowest
local frames = {}
if MODE == "promptimate" then
  local folder = game:GetService("ReplicatedStorage").Promptimate
  local Player = require(folder.PromptimatePlayer:Clone())
  local clip = Player.decode(require(folder[NAME]:Clone()))
  local track = Player.new(rig, clip, { origin = CFrame.new(rig.HumanoidRootPart.Position.X, 0, 0) })
  for f = 0, FRAMES - 1 do track:Seek(f / FPS); task.wait(); table.insert(frames, read()) end
  track:Stop()
else
  local kfs = game:GetService("ServerStorage").RBX_ASSISTANT_ANIMGEN[NAME]
  local id = game:GetService("KeyframeSequenceProvider"):RegisterKeyframeSequence(kfs)
  local anim = Instance.new("Animation"); anim.AnimationId = id
  local animator = rig.Humanoid:FindFirstChildOfClass("Animator") or Instance.new("Animator", rig.Humanoid)
  for _, t in animator:GetPlayingAnimationTracks() do t:Stop(0) end
  local tr = animator:LoadAnimation(anim)
  tr.Looped = false; tr:Play(0); tr:AdjustSpeed(0)
  local len = tr.Length > 0 and tr.Length or (FRAMES / FPS)
  for f = 0, FRAMES - 1 do tr.TimePosition = math.min(f / FPS, len - 1e-3); task.wait(); task.wait(); table.insert(frames, read()) end
  tr:Stop(0)
end
return string.format("%.4f", stand) .. "|" .. table.concat(frames, ";")
'''

POSE_BOTH = r'''
local MODE_T = __T__
local folder = game:GetService("ReplicatedStorage").Promptimate
local Player = require(folder.PromptimatePlayer:Clone())
local a = workspace.H2H_Promptimate
local clip = Player.decode(require(folder[__PNAME__]:Clone()))
local track = Player.new(a, clip, { origin = CFrame.new(a.HumanoidRootPart.Position.X, 0, 0) })
track:Seek(MODE_T)
local b = workspace.H2H_Roblox
local kfs = game:GetService("ServerStorage").RBX_ASSISTANT_ANIMGEN[__RNAME__]
local id = game:GetService("KeyframeSequenceProvider"):RegisterKeyframeSequence(kfs)
local anim = Instance.new("Animation"); anim.AnimationId = id
local animator = b.Humanoid:FindFirstChildOfClass("Animator") or Instance.new("Animator", b.Humanoid)
for _, t in animator:GetPlayingAnimationTracks() do t:Stop(0) end
local tr = animator:LoadAnimation(anim); tr.Looped = false; tr:Play(0); tr:AdjustSpeed(0)
tr.TimePosition = math.min(MODE_T, math.max(tr.Length - 1e-3, 0))
task.wait(); task.wait()
local mid = (a.LowerTorso.Position + b.LowerTorso.Position) / 2
return string.format("%.3f,%.3f,%.3f", mid.X, mid.Y, mid.Z)
'''


UNIQUE = sorted(set(POINTS.values()))


def to_soma_positions(text: str) -> np.ndarray:
    """Roblox joint samples (studs) -> (F,30,3) metres in Kimodo space, start x/z at 0, floor (y=0) at 0."""
    stand, body = text.split("|", 1)
    s = 0.95 / float(stand)
    rows = [np.array(list(map(float, fr.split(",")))).reshape(-1, 3) for fr in body.split(";")]
    uniq = np.stack(rows)                                   # (F, U, 3)
    pos = np.stack([uniq[:, UNIQUE.index(POINTS[i])] for i in range(30)], axis=1)
    pos = pos @ roblox.K2R          # Roblox -> Kimodo axes (same 180 deg turn)
    pos *= s
    pos[..., [0, 2]] -= pos[:1, :1, [0, 2]]
    return pos


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", default=",".join(DEFAULT))
    ap.add_argument("--reuse", action="store_true", help="reuse generations from a previous run")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    suite = {p["id"]: p for p in json.loads((ROOT / "bench" / "prompts.json").read_text())["prompts"]}
    prev = json.loads((OUT / "results.json").read_text()) if args.reuse and (OUT / "results.json").exists() else {}
    import server  # Promptimate pipeline (motiond)
    results = {}
    async with StudioSession() as s:
        await asyncio.sleep(3)
        print((await s.luau(SETUP))["content"], flush=True)
        for pid in args.prompts.split(","):
            p = suite[pid]
            prompt = " then ".join(seg["prompt"] for seg in p["segments"]) if len(p["segments"]) > 1 else p["segments"][0]["prompt"]
            secs = sum(seg["seconds"] for seg in p["segments"])
            F = int(round(secs * 30))
            r = prev.get(pid, {})
            # --- Promptimate
            if "pm_dir" not in r:
                t0 = time.time()
                meta = json.loads(server.generate_motion([server.MotionSegment(prompt=seg["prompt"], seconds=seg["seconds"])
                                                          for seg in p["segments"]], name=f"h2h_{pid}", unity_check="off")[0])
                r["pm_seconds"] = round(time.time() - t0, 1)
                r["pm_dir"] = meta["files"]["raw_dir"]
            clip_name = f"h2h_{pid}"
            src = roblox.export_luau(Path(r["pm_dir"]), OUT / f"{clip_name}.lua", clip_name).read_text(encoding="utf-8")
            player_src = (ROOT / "roblox" / "PromptimatePlayer.lua").read_text(encoding="utf-8")
            await s.luau(upload_code(player_src, {clip_name: src}))
            # --- Roblox
            if "rb_clip" not in r:
                t0 = time.time()
                g = await s.call("generate_animation", {"textPrompt": prompt, "duration": secs,
                                                        "instance_path": "Workspace.H2H_Roblox"})
                r["rb_seconds"] = round(time.time() - t0, 1)
                info = json.loads(g["content"][0]) if not g["isError"] else {"error": g["content"]}
                if "clipPath" not in info:
                    print(pid, "roblox generation failed:", info, flush=True)
                    results[pid] = r
                    continue
                r["rb_clip"] = info["clipPath"].split(".")[-1]
                r["rb_asset"] = info.get("publishedAssetId")
            # --- sample both from the engine
            scores = {}
            for mode, name in (("promptimate", clip_name), ("roblox", r["rb_clip"])):
                code = (SAMPLE.replace("__POINTS__", "{" + ",".join(f'"{v}"' for v in UNIQUE) + "}")
                        .replace("__MODE__", json.dumps(mode)).replace("__NAME__", json.dumps(name))
                        .replace("__FRAMES__", str(F)))
                res = await s.luau(code)
                if res["isError"]:
                    print(pid, mode, "sampling failed:", res["content"], flush=True)
                    continue
                pos = to_soma_positions(res["content"][0])
                m = metrics.compute(pos=pos, expect=p.get("expect"), segment_expect=p.get("segment_expect"),
                                    segment_frames=[round(seg["seconds"] * 30) for seg in p["segments"]])
                scores[mode] = {k: m.get(k) for k in ("expectation_score", "skate_speed_cms", "penetration_max_cm",
                                                      "float_ratio", "jerk_mean", "pop_frames", "root_travel_m",
                                                      "heading_change_deg", "hips_min_m", "hips_end_m")}
                scores[mode]["failed_expectations"] = {k: v for k, v in m.items() if k.startswith("exp_") and v < 0.999}
            r["scores"] = scores
            # --- side-by-side captures at 4 times
            caps = []
            for i, frac in enumerate((0.15, 0.4, 0.65, 0.9)):
                t = frac * secs
                mid = (await s.luau(POSE_BOTH.replace("__T__", f"{t:.3f}").replace("__PNAME__", json.dumps(clip_name))
                                    .replace("__RNAME__", json.dumps(r["rb_clip"]))))["content"][0]
                x, y, z = map(float, mid.split(","))
                cap = await s.call("screen_capture", {"capture_id": f"h2h_{pid}_{i}",
                                                      "camera_position": [x, y + 3, z - 16], "look_at_position": [x, y, z]})
                for c in cap["content"]:
                    if isinstance(c, dict) and c.get("data"):
                        path = OUT / f"{pid}_{i}.png"
                        path.write_bytes(base64.b64decode(c["data"]))
                        caps.append(str(path))
            r["captures"] = caps
            results[pid] = r
            print(pid, json.dumps({k: r.get(k) for k in ("pm_seconds", "rb_seconds")}),
                  json.dumps({m: {k: v for k, v in sc.items() if k in ("expectation_score", "skate_speed_cms", "root_travel_m")}
                              for m, sc in scores.items()}), flush=True)
            (OUT / "results.json").write_text(json.dumps({**prev, **results}, indent=1))
    server.worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
