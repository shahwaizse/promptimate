"""Fast frame grabs for roblox_record: pose + aim Studio's own camera in one Luau call, wait for the render, then grab
the 3D viewport straight off the screen (~30 ms) instead of an MCP screen_capture round trip (~730 ms).
Requires the Studio window visible (not minimized or covered) while recording."""
from __future__ import annotations

import ctypes
import ctypes.wintypes as W
import time

import numpy as np
from PIL import Image, ImageGrab

_u = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    _u.SetProcessDPIAware()


def studio_window():
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)
    def cb(h, _l):
        n = ctypes.create_unicode_buffer(512)
        _u.GetWindowTextW(h, n, 512)
        if n.value.endswith("Roblox Studio") and _u.IsWindowVisible(h) and not _u.IsIconic(h):
            r = W.RECT()
            _u.GetWindowRect(h, ctypes.byref(r))
            found.append((h, (r.left, r.top, r.right, r.bottom)))
        return True

    _u.EnumWindows(cb, 0)
    return found[0] if found else None


CALIB = r'''
local f = workspace:FindFirstChild("__PromptimateCalib") or Instance.new("Part")
f.Name = "__PromptimateCalib"; f.Anchored = true; f.CanCollide = false; f.Size = Vector3.new(400, 400, 1)
f.Color = Color3.fromRGB(255, 0, 255); f.Material = Enum.Material.Neon; f.CastShadow = false
local cam = workspace.CurrentCamera
cam.CameraType = Enum.CameraType.Scriptable
cam.CFrame = CFrame.lookAt(Vector3.new(0, 900, 0), Vector3.new(0, 900, -10))
f.CFrame = CFrame.new(0, 900, -6)
f.Parent = workspace
game:GetService("RunService").RenderStepped:Wait(); game:GetService("RunService").RenderStepped:Wait()
return 1'''


def calibrate(st, vp: tuple[int, int]) -> tuple[int, int, int, int]:
    """Screen rectangle of Studio's 3D viewport: show a full-screen magenta wall and find it on screen."""
    w = studio_window()
    if not w:
        raise RuntimeError("Roblox Studio window not found (minimized?)")
    st.luau(CALIB)
    time.sleep(0.25)
    l, t, r, b = w[1]
    img = np.asarray(ImageGrab.grab(bbox=(max(l, 0), max(t, 0), r, b), all_screens=True).convert("RGB")).astype(int)
    st.luau('local f = workspace:FindFirstChild("__PromptimateCalib"); if f then f:Destroy() end; return 1')
    m = (img[:, :, 0] > 200) & (img[:, :, 1] < 80) & (img[:, :, 2] > 200)
    ys, xs = np.nonzero(m)
    if len(xs) < 1000:
        raise RuntimeError("viewport not visible on screen: bring the Studio window to the front")
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    rect = (max(l, 0) + x0, max(t, 0) + y0, max(l, 0) + x1, max(t, 0) + y1)
    if abs((x1 - x0) - vp[0]) > 6 or abs((y1 - y0) - vp[1]) > 6:
        raise RuntimeError(f"viewport on screen {x1 - x0}x{y1 - y0} != Studio viewport {vp}: is it covered?")
    return rect


def grab(rect) -> Image.Image:
    return ImageGrab.grab(bbox=rect, all_screens=True).convert("RGB")


AIM = '''local cam = workspace.CurrentCamera
cam.CameraType = Enum.CameraType.Scriptable
cam.FieldOfView = {fov:.5f}
cam.CFrame = CFrame.lookAt(Vector3.new({p[0]:.4f}, {p[1]:.4f}, {p[2]:.4f}), Vector3.new({l[0]:.4f}, {l[1]:.4f}, {l[2]:.4f}))
{seek}local RS = game:GetService("RunService"); RS.RenderStepped:Wait(); RS.RenderStepped:Wait(); RS.RenderStepped:Wait()
return 1'''


def shoot(st, rect, pos, look, fov, seek_t: float | None = None) -> Image.Image:
    seek = f"_G.PromptimateDirector.seek({seek_t:.4f})\n" if seek_t is not None else ""
    st.luau(AIM.format(fov=fov, p=pos, l=look, seek=seek))
    return grab(rect)


# ------------------------------------------------------------------ one-shot portrait frames: a 90-degree rolled camera
# turns the landscape viewport into a portrait frame; the central crop also drops Studio's View Selector widget
# (top-right corner). Output = crop rotated upright and resized (about 1.5x for 1080x1920 on a 1452x793 viewport).
MARGIN = 0.077          # fraction of the viewport width cropped from each end (clears the View Selector)


def portrait_geometry(vp, out=(1080, 1920)):
    Wv, Hv = vp
    half_long = Wv / 2 * (1 - 2 * MARGIN)            # viewport x half-extent used for the output's vertical
    half_short = half_long * out[0] / out[1]          # viewport y half-extent for the output's horizontal
    if half_short > Hv / 2:
        half_short = Hv / 2
        half_long = half_short * out[1] / out[0]
    crop = (round(Wv / 2 - half_long), round(Hv / 2 - half_short), round(Wv / 2 + half_long), round(Hv / 2 + half_short))
    return crop, half_long


def roblox_fov(fov_out_deg: float, vp, out=(1080, 1920)) -> float:
    """Roblox FieldOfView (vertical, over the viewport height) for the rolled camera, so the crop spans fov_out
    vertically in the output."""
    import math
    crop, half_long = portrait_geometry(vp, out)
    fv = half_long / math.tan(math.radians(fov_out_deg) / 2)   # viewport focal length in px
    return math.degrees(2 * math.atan((vp[1] / 2) / fv))


ROLL = '''local cam = workspace.CurrentCamera
cam.CameraType = Enum.CameraType.Scriptable
cam.FieldOfView = {fov:.5f}
local p, l = Vector3.new({p[0]:.4f}, {p[1]:.4f}, {p[2]:.4f}), Vector3.new({l[0]:.4f}, {l[1]:.4f}, {l[2]:.4f})
local f = (l - p).Unit
local right = f:Cross(Vector3.yAxis)
if right.Magnitude < 1e-3 then right = Vector3.xAxis end
cam.CFrame = CFrame.lookAt(p, l, right.Unit)   -- rolled 90 degrees: the scene's up runs along the viewport's width
{seek}local RS = game:GetService("RunService"); RS.RenderStepped:Wait(); RS.RenderStepped:Wait()
return 1'''


def portrait_raw(st, rect, vp, pos, look, fov_out, seek_t=None, out=(1080, 1920)) -> Image.Image:
    """Pose + aim + grab only (the capture loop); finish() turns it into the output frame (in a worker)."""
    seek = f"_G.PromptimateDirector.seek({seek_t:.4f})\n" if seek_t is not None else ""
    st.luau(ROLL.format(fov=roblox_fov(fov_out, vp, out), p=pos, l=look, seek=seek))
    return ImageGrab.grab(bbox=rect, all_screens=True)


def finish(raw: Image.Image, vp, out=(1080, 1920)) -> Image.Image:
    crop, _ = portrait_geometry(vp, out)
    return raw.convert("RGB").crop(crop).transpose(Image.Transpose.ROTATE_270).resize(out, Image.Resampling.LANCZOS)


def portrait(st, rect, vp, pos, look, fov_out, seek_t=None, out=(1080, 1920)) -> Image.Image:
    return finish(portrait_raw(st, rect, vp, pos, look, fov_out, seek_t, out), vp, out)


HIDE_NAMES = '''for _, h in workspace:GetDescendants() do
  if h:IsA("Humanoid") then
    if h:GetAttribute("PromptimateNameDist") == nil then h:SetAttribute("PromptimateNameDist", h.DisplayDistanceType.Name) end
    h.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
  end
end
return 1'''
RESTORE_NAMES = '''for _, h in workspace:GetDescendants() do
  if h:IsA("Humanoid") and h:GetAttribute("PromptimateNameDist") then
    h.DisplayDistanceType = Enum.HumanoidDisplayDistanceType[h:GetAttribute("PromptimateNameDist")]
    h:SetAttribute("PromptimateNameDist", nil)
  end
end
return 1'''
