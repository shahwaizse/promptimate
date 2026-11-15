"""Validate a Promptimate clip on a real R15 avatar inside Roblox Studio (through Studio's MCP server).

Uploads roblox/PromptimatePlayer.lua and the clip into ReplicatedStorage, spawns (or reuses) an R15 avatar, poses it
at sampled frames with PromptimatePlayer:Seek, reads back the joints' world positions from Roblox, and compares limb
directions, left/right and facing with the source motion (Python FK).

Usage: .venv\\Scripts\\python roblox\\tools\\validate_in_studio.py <motion_dir> [<motion_dir> ...]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import motion  # noqa: E402
import roblox  # noqa: E402
from studio_mcp import StudioSession  # noqa: E402

# R15 joint -> (part that holds the rig attachment, attachment name); SOMA joint index for comparison
JOINTS = {
    "LeftShoulder": ("LeftUpperArm", "LeftShoulderRigAttachment", 11), "LeftElbow": ("LeftLowerArm", "LeftElbowRigAttachment", 12),
    "LeftWrist": ("LeftHand", "LeftWristRigAttachment", 13), "RightShoulder": ("RightUpperArm", "RightShoulderRigAttachment", 17),
    "RightElbow": ("RightLowerArm", "RightElbowRigAttachment", 18), "RightWrist": ("RightHand", "RightWristRigAttachment", 19),
    "LeftHip": ("LeftUpperLeg", "LeftHipRigAttachment", 22), "LeftKnee": ("LeftLowerLeg", "LeftKneeRigAttachment", 23),
    "LeftAnkle": ("LeftFoot", "LeftAnkleRigAttachment", 24), "RightHip": ("RightUpperLeg", "RightHipRigAttachment", 26),
    "RightKnee": ("RightLowerLeg", "RightKneeRigAttachment", 27), "RightAnkle": ("RightFoot", "RightAnkleRigAttachment", 28),
}
BONES = [("LeftShoulder", "LeftElbow"), ("LeftElbow", "LeftWrist"), ("RightShoulder", "RightElbow"),
         ("RightElbow", "RightWrist"), ("LeftHip", "LeftKnee"), ("LeftKnee", "LeftAnkle"), ("RightHip", "RightKnee"),
         ("RightKnee", "RightAnkle")]


def _long(s: str) -> str:
    eq = "=" * 3
    while f"]{eq}]" in s:
        eq += "="
    return f"[{eq}[{s}]{eq}]"


def upload_code(player_src: str, clips: dict[str, str]) -> str:
    lines = ['local RS = game:GetService("ReplicatedStorage")',
             'local folder = RS:FindFirstChild("Promptimate") or Instance.new("Folder")',
             'folder.Name = "Promptimate"; folder.Parent = RS',
             'local function put(name, src) local m = folder:FindFirstChild(name) or Instance.new("ModuleScript");'
             ' m.Name = name; m.Source = src; m.Parent = folder end',
             f'put("PromptimatePlayer", {_long(player_src)})']
    for name, src in clips.items():
        lines.append(f'put({json.dumps(name)}, {_long(src)})')
    lines.append('return "uploaded " .. #folder:GetChildren()')
    return "\n".join(lines)


POSE_CODE = r'''
local RS = game:GetService("ReplicatedStorage")
local folder = RS.Promptimate
local Player = require(folder.PromptimatePlayer:Clone())   -- clone: fresh module after re-uploads
local rig = workspace:FindFirstChild("PromptimateProbe")
if not rig then
  rig = game:GetService("Players"):CreateHumanoidModelFromDescription(Instance.new("HumanoidDescription"), Enum.HumanoidRigType.R15)
  rig.Name = "PromptimateProbe"; rig.Parent = workspace; rig:PivotTo(CFrame.new(0, 5, 0))
end
local clip = Player.decode(require(folder[CLIPNAME]:Clone()))
local track = Player.new(rig, clip, { origin = CFrame.new(0, 0, 0) })
local joints = JOINTS
local out = { frames = {}, applied = nil }
local before = rig.LeftLowerArm.Position
for _, f in FRAMES do
  local targets = track:SampleTargets(f / clip.fps)
  task.wait(); task.wait()   -- let the engine solve the joints before reading part positions
  local row = {}
  for jname, spec in joints do
    local part = rig[spec[1]]
    local att = part:FindFirstChild(spec[2])
    -- position from the target CFrames (what the player asks for)
    local cf = targets[spec[1]] * att.CFrame
    row[jname] = { cf.X, cf.Y, cf.Z, att.WorldPosition.X, att.WorldPosition.Y, att.WorldPosition.Z }
  end
  local lt = targets.LowerTorso
  row.__facing = { lt.LookVector.X, lt.LookVector.Y, lt.LookVector.Z }
  table.insert(out.frames, row)
end
out.applied = (rig.LeftLowerArm.Position - before).Magnitude
return game:GetService("HttpService"):JSONEncode(out)
'''


async def validate(dirs: list[Path]) -> list[dict]:
    player_src = (ROOT / "roblox" / "PromptimatePlayer.lua").read_text(encoding="utf-8")
    clips = {}
    for d in dirs:
        out = roblox.export_luau(d, ROOT / "roblox" / "out" / f"{d.name}.lua", d.name)
        clips[d.name] = out.read_text(encoding="utf-8")
    results = []
    async with StudioSession() as s:
        r = await s.luau(upload_code(player_src, clips))
        if r["isError"]:
            raise RuntimeError(r)
        for d in dirs:
            root, rot = motion.load(d)
            F = len(root)
            frames = list(range(0, F, max(1, F // 20)))
            code = (POSE_CODE.replace("CLIPNAME", json.dumps(d.name))
                    .replace("FRAMES", "{" + ",".join(map(str, frames)) + "}")
                    .replace("JOINTS", "{" + ",".join(f'{k}={{"{v[0]}","{v[1]}"}}' for k, v in JOINTS.items()) + "}"))
            r = await s.luau(code)
            if r["isError"]:
                raise RuntimeError(r)
            data = json.loads(r["content"][0])
            soma = motion.fk(root, rot).astype(np.float64) @ roblox.K2R
            errs, engine_errs, lr_ok, face = [], [], [], []
            for fi, f in enumerate(frames):
                row = data["frames"][fi]
                tgt = {k: np.array(v[:3]) for k, v in row.items() if not k.startswith("__")}
                eng = {k: np.array(v[3:]) for k, v in row.items() if not k.startswith("__")}
                for a, b in BONES:
                    d_s = soma[f, JOINTS[b][2]] - soma[f, JOINTS[a][2]]
                    for store, P in ((errs, tgt), (engine_errs, eng)):
                        d_r = P[b] - P[a]
                        c = np.dot(d_s, d_r) / (np.linalg.norm(d_s) * np.linalg.norm(d_r) + 1e-9)
                        store.append(np.degrees(np.arccos(np.clip(c, -1, 1))))
                lr_ok.append(np.dot(soma[f, 11] - soma[f, 17], tgt["LeftShoulder"] - tgt["RightShoulder"]) > 0)
                left = soma[f, 22] - soma[f, 26]
                fwd = np.cross(left, [0, 1.0, 0]); fwd[1] = 0
                lv = np.array(row["__facing"]); lv[1] = 0
                face.append(np.degrees(np.arccos(np.clip(np.dot(fwd, lv) / (np.linalg.norm(fwd) * np.linalg.norm(lv) + 1e-9), -1, 1))))
            res = {"clip": d.name, "frames_checked": len(frames),
                   "limb_dir_err_max_deg": round(float(np.max(errs)), 2),
                   "engine_applied_limb_err_max_deg": round(float(np.max(engine_errs)), 2),
                   "engine_moved_parts_m": round(float(data["applied"]), 3),
                   "left_right_ok": float(np.mean(lr_ok)), "facing_err_p95_deg": round(float(np.percentile(face, 95)), 1)}
            print(json.dumps(res), flush=True)
            results.append(res)
    return results


if __name__ == "__main__":
    asyncio.run(validate([Path(a) for a in sys.argv[1:]]))
