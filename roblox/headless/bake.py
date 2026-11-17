"""Texture baking: Studio won't hand over the pixels of assets the user doesn't own (EditableImage: "no permission"),
but it will display them. Each texture is shown full-frame in a CoreGui overlay over black, then over white, and
screen-grabbed; the two grabs give colour and alpha. Cached by asset id in <cache>/tex/<id>.png, so every texture is
baked once, ever.

    bake(["rbxassetid://123", ...]) -> {asset: png path}
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageGrab

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "mcp_server"))
sys.path.insert(0, str(HERE.parents[1] / "roblox" / "short"))
from pipeline import CACHE  # noqa: E402

TEX = CACHE / "tex"
CLOTHING = (585, 559)       # classic shirt/pants template size

SHOW = r'''
local CG = game:GetService("CoreGui")
local g = CG:FindFirstChild("PromptimateBake") or Instance.new("ScreenGui")
g.Name = "PromptimateBake"; g.IgnoreGuiInset = true; g.DisplayOrder = 1e6
local bg = g:FindFirstChild("bg") or Instance.new("Frame")
bg.Name = "bg"; bg.BorderSizePixel = 0; bg.Size = UDim2.fromScale(1, 1); bg.Parent = g
local im = bg:FindFirstChild("im") or Instance.new("ImageLabel")
im.Name = "im"; im.BackgroundTransparency = 1; im.BorderSizePixel = 0; im.ScaleType = Enum.ScaleType.Stretch
im.Size = UDim2.fromOffset(__S__, __S__); im.Position = UDim2.fromOffset(0, 0); im.Parent = bg
g.Parent = CG
im.Image = "__ID__"
bg.BackgroundColor3 = Color3.new(__C__, __C__, __C__)
if __PRE__ then game:GetService("ContentProvider"):PreloadAsync({ im }) end
local RS = game:GetService("RunService")
for _ = 1, 3 do RS.RenderStepped:Wait() end
return im.IsLoaded and 1 or 0'''
HIDE = 'local g = game:GetService("CoreGui"):FindFirstChild("PromptimateBake"); if g then g:Destroy() end; return 1'


def _name(asset: str) -> str:
    m = re.search(r"(\d{4,})", asset)
    return m.group(1) if m else re.sub(r"[^A-Za-z0-9]", "_", asset)[-60:]


def path_for(asset: str) -> Path:
    return TEX / f"{_name(asset)}.png"


def bake(assets, clothing=()) -> dict:
    """Bake every asset not yet cached; returns {asset: path} for the ones that loaded."""
    import fastgrab as FG
    import roblox_record as RR
    from roblox_studio import studio
    TEX.mkdir(parents=True, exist_ok=True)
    out = {}
    todo = []
    for a in dict.fromkeys(a for a in assets if a):
        p = path_for(a)
        if p.exists():
            out[a] = p
        else:
            todo.append(a)
    if not todo:
        return out
    st = studio()
    vp = RR._viewport()
    FG.pin_studio(True)
    rect = FG.calibrate(st, vp)
    vr = FG._u.GetSystemMetrics(76) + FG._u.GetSystemMetrics(78)
    side = min(rect[3] - rect[1], vr - rect[0]) - 4        # a square that is fully on screen
    box = (rect[0], rect[1], rect[0] + side, rect[1] + side)
    t = time.time()
    for a in todo:
        shots = []
        loaded = True
        for c, pre in ((0, "true"), (1, "false")):
            ok = st.luau(SHOW.replace("__S__", str(side)).replace("__ID__", a).replace("__C__", str(c)).replace("__PRE__", pre))
            loaded &= str(ok).strip() == "1"
            time.sleep(0.03)
            shots.append(np.asarray(ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")).astype("f4"))
        if not loaded:
            continue
        blk, wht = shots
        alpha = np.clip(1 - (wht - blk).mean(2, keepdims=True) / 255, 0, 1)
        rgb = np.where(alpha > 0.02, blk / np.maximum(alpha, 1e-3), 0)
        img = np.concatenate([np.clip(rgb, 0, 255), alpha * 255], 2).astype("uint8")
        im = Image.fromarray(img, "RGBA")
        if a in clothing:
            im = im.resize(CLOTHING, Image.LANCZOS)
        im.save(path_for(a))
        out[a] = path_for(a)
    st.luau(HIDE)
    print(f"baked {len(todo)} textures in {time.time() - t:.1f}s ({len(out)} available)", flush=True)
    return out


FACE_SHOW = r'''
local F = require(game:GetService("ReplicatedStorage").Promptimate.Faces:Clone())
local CG = game:GetService("CoreGui")
local g = CG:FindFirstChild("PromptimateBake") or Instance.new("ScreenGui")
g.Name = "PromptimateBake"; g.IgnoreGuiInset = true; g.DisplayOrder = 1e6; g.Parent = CG
for _, c in g:GetChildren() do c:Destroy() end
local bg = Instance.new("Frame"); bg.BorderSizePixel = 0; bg.Size = UDim2.fromOffset(__S__, __S__)
bg.BackgroundColor3 = Color3.new(__C__, __C__, __C__); bg.Parent = g
local m = Instance.new("Model"); m.Name = "__FaceBake"
local h = Instance.new("Part"); h.Name = "Head"; h.Size = Vector3.new(1, 1, 1); h.Anchored = true; h.Parent = m
local sm = Instance.new("SpecialMesh"); sm.MeshType = Enum.MeshType.Head; sm.Scale = Vector3.new(1.25, 1.25, 1.25); sm.Parent = h
m.Parent = workspace
F.set(m, "__E__")
local root = h.PromptimateFace:FindFirstChildOfClass("Frame")
root.Parent = bg
m:Destroy()
local RS = game:GetService("RunService")
for _ = 1, 3 do RS.RenderStepped:Wait() end
return 1'''


def bake_faces(names) -> dict:
    """One RGBA image per expression (the head's front plate, 0.92 of the head mesh)."""
    import fastgrab as FG
    import roblox_record as RR
    from roblox_studio import studio
    TEX.mkdir(parents=True, exist_ok=True)
    out, todo = {}, []
    for n in names:
        p = TEX / f"face_{n}.png"
        (out.__setitem__(n, p) if p.exists() else todo.append(n))
    if not todo:
        return out
    st = studio()
    vp = RR._viewport()
    FG.pin_studio(True)
    rect = FG.calibrate(st, vp)
    vr = FG._u.GetSystemMetrics(76) + FG._u.GetSystemMetrics(78)
    side = min(rect[3] - rect[1], vr - rect[0]) - 4
    box = (rect[0], rect[1], rect[0] + side, rect[1] + side)
    for n in todo:
        shots = []
        for c in (0, 1):
            st.luau(FACE_SHOW.replace("__S__", str(side)).replace("__C__", str(c)).replace("__E__", n))
            time.sleep(0.03)
            shots.append(np.asarray(ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")).astype("f4"))
        blk, wht = shots
        alpha = np.clip(1 - (wht - blk).mean(2, keepdims=True) / 255, 0, 1)
        rgb = np.where(alpha > 0.02, blk / np.maximum(alpha, 1e-3), 0)
        Image.fromarray(np.concatenate([np.clip(rgb, 0, 255), alpha * 255], 2).astype("uint8"), "RGBA") \
            .resize((512, 512), Image.LANCZOS).save(TEX / f"face_{n}.png")
        out[n] = TEX / f"face_{n}.png"
    st.luau(HIDE)
    return out
