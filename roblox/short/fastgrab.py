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


def studio_window(include_minimized: bool = False):
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, W.HWND, W.LPARAM)
    def cb(h, _l):
        n = ctypes.create_unicode_buffer(512)
        _u.GetWindowTextW(h, n, 512)
        if n.value.endswith("Roblox Studio") and _u.IsWindowVisible(h) and (include_minimized or not _u.IsIconic(h)):
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
    # the window may run past the right edge of the last monitor (its side panels pushed off-screen to give the
    # viewport the whole visible width): extend the rect by the hidden part; only the central crop is ever grabbed
    vr = _u.GetSystemMetrics(76) + _u.GetSystemMetrics(78)
    if rect[2] >= vr - 1 and vp[0] - (x1 - x0) > 6:
        x1 = x0 + vp[0]
        rect = (rect[0], rect[1], rect[0] + vp[0], rect[3])
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
-- Studio's edit camera drops the roll once a command returns (seen after a Studio restart): a frame hook keeps
-- re-applying this camera for a moment, until the screen grab that follows has happened
_G.PromptimateHold = {{ cf = cam.CFrame, untilT = os.clock() + 1.5 }}
if not _G.PromptimateHoldConn then
  _G.PromptimateHoldConn = game:GetService("RunService").RenderStepped:Connect(function()
    local h = _G.PromptimateHold
    if h and os.clock() < h.untilT then workspace.CurrentCamera.CFrame = h.cf end
  end)
end
{seek}local D = _G.PromptimateDirector
if D and D.cutaway then D.cutaway(p, l) end
local RS = game:GetService("RunService"); RS.RenderStepped:Wait(); RS.RenderStepped:Wait()
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
RESTORE_NAMES = '''local D = _G.PromptimateDirector
if D and D.cutawayClear then D.cutawayClear() end
for _, h in workspace:GetDescendants() do
  if h:IsA("Humanoid") and h:GetAttribute("PromptimateNameDist") then
    h.DisplayDistanceType = Enum.HumanoidDisplayDistanceType[h:GetAttribute("PromptimateNameDist")]
    h:SetAttribute("PromptimateNameDist", nil)
  end
end
return 1'''


def layout_studio(hwnd) -> None:
    """Recording layout on the right-most monitor: the window is taller than the screen (title bar and status bar
    off-screen) and runs past its right edge (side panels off-screen), so the 3D viewport gets ~1716x805 px - the
    rolled portrait crop is 805 px wide (vs ~680 with the default window). PROMPTIMATE_STUDIO_LAYOUT=0 leaves it."""
    import os
    if os.environ.get("PROMPTIMATE_STUDIO_LAYOUT", "1") == "0":
        return
    right = _u.GetSystemMetrics(76) + _u.GetSystemMetrics(78)
    r = W.RECT(); _u.GetWindowRect(hwnd, ctypes.byref(r))
    want = (right - 1920, -160, right + 280, 1130)
    if (r.left, r.top, r.right, r.bottom) != want:
        _u.SetWindowPos(hwnd, 0, want[0], want[1], want[2] - want[0], want[3] - want[1], 0x0010 | 0x0004)
        time.sleep(1.5)


def pin_studio(on: bool = True) -> bool:
    """Raise Studio's window above the others on its monitor (without taking keyboard focus) so nothing covers the
    viewport while recording. Returns whether the window was found."""
    w = studio_window(include_minimized=True)
    if not w:
        return False
    if on:
        if _u.IsIconic(w[0]):
            _u.ShowWindow(w[0], 4)      # SW_SHOWNOACTIVATE: un-minimize to its previous size, focus stays put
            time.sleep(0.8)
        _u.ShowWindow(w[0], 8)          # SW_SHOWNA: to the front in its current (maximized) state, focus stays put
        time.sleep(0.3)
        layout_studio(w[0])
        wake_studio(w[0])
    return True


def wake_studio(hwnd=None) -> None:
    """Studio renders at 15 fps while it isn't the active app and 60 fps (vsync) when it is. Telling its windows
    they're active (WM_ACTIVATEAPP / WM_NCACTIVATE / WM_ACTIVATE, sent, not a real focus change) lifts the throttle
    without taking the keyboard from the user: 4x faster live capture, shot checks and frame grabs."""
    if hwnd is None:
        w = studio_window(include_minimized=True)
        if not w:
            return
        hwnd = w[0]
    hs = [hwnd]
    cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(lambda h, _l: hs.append(h) or True)
    _u.EnumChildWindows(hwnd, cb, 0)
    for h in hs:
        _u.SendMessageW(h, 0x1C, 1, 0)      # WM_ACTIVATEAPP(TRUE)
        _u.SendMessageW(h, 0x86, 1, 0)      # WM_NCACTIVATE(TRUE)
        _u.SendMessageW(h, 0x06, 1, 0)      # WM_ACTIVATE(WA_ACTIVE)


def viewport_clear(rect) -> bool:
    """Is Studio the window under the viewport's centre and corners?"""
    w = studio_window()
    if not w:
        return False
    l, t, r, b = rect
    vr = _u.GetSystemMetrics(76) + _u.GetSystemMetrics(78)
    r = min(r, vr - 1)          # (a viewport running off the right edge: check the visible part)
    for x, y in (((l + r) // 2, (t + b) // 2), (l + 8, t + 8), (r - 8, t + 8), (l + 8, b - 8), (r - 8, b - 8)):
        h = _u.WindowFromPoint(W.POINT(int(x), int(y)))
        if _u.GetAncestor(h, 2) != w[0]:
            return False
    return True


def minimize_studio() -> bool:
    """Minimize Studio (it stops rendering): while motion is generated, a rendering Studio competes for the GPU
    (measured: ~35 s per motion with heavy sets on screen vs 4-6 s minimized)."""
    w = studio_window()
    if not w:
        return False
    _u.ShowWindow(w[0], 7)              # SW_SHOWMINNOACTIVE
    return True
