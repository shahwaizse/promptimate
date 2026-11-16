"""Real-time recording for roblox_record: Studio plays the performance live (story time snapped to output frame times,
cameras precomputed per frame) while DXGI desktop duplication grabs the viewport at ~4 ms per grab. Every rendered
frame carries its frame index as a binary code drawn in the strip of the viewport that the portrait crop throws away,
so each grab is matched to its exact output frame; frames Studio skipped are filled by the frame-by-frame path.
An 80 s video records in ~1.5 min instead of ~7.5.

Requires Windows, Studio's window on screen (not covered), and the `dxcam` package."""
from __future__ import annotations

import json
import time

import numpy as np

BITS = 13                  # frame index up to 8191 (5.7 min at 24 fps)
SQ = 14                    # marker square size (viewport px)
X0, Y0, STEP = 6, 30, 20   # marker column in the viewport's left strip (cropped away by fastgrab.MARGIN)

SETUP = r'''
local CG = game:GetService("CoreGui")
local g = CG:FindFirstChild("PromptimateRT") or Instance.new("ScreenGui")
g.Name = "PromptimateRT"; g.IgnoreGuiInset = true; g.DisplayOrder = 1e6; g.ResetOnSpawn = false
for _, c in g:GetChildren() do c:Destroy() end
for i = 0, __N__ + 1 do
  local f = Instance.new("Frame")
  f.Name = "b" .. i; f.BorderSizePixel = 0; f.Size = UDim2.fromOffset(__SQ__, __SQ__)
  f.Position = UDim2.fromOffset(__X0__, __Y0__ + i * __STEP__)
  f.BackgroundColor3 = (i == __N__) and Color3.new(1, 1, 1) or Color3.new(0, 0, 0)   -- b<N> white, b<N+1> black: references
  f.Parent = g
end
g.Parent = CG
_G.PromptimateRTCams = {}
return 1'''

UPLOAD = r'''
local t = _G.PromptimateRTCams
for i, c in game:GetService("HttpService"):JSONDecode(__J__) do t[__K0__ + i - 1] = c end
return #t'''

PLAY = r'''
local RS = game:GetService("RunService")
local D = _G.PromptimateDirector
local g = game:GetService("CoreGui").PromptimateRT
local cams = _G.PromptimateRTCams
local cam = workspace.CurrentCamera
cam.CameraType = Enum.CameraType.Scriptable
local n0, n1, fps, speed = __N0__, __N1__, __FPS__, __SPEED__
local bits = {}
for i = 0, __N__ - 1 do bits[i] = g["b" .. i] end
_G.PromptimateRTState = "warmup"
task.spawn(function()
  -- warm-up: pose the first frame and hold it a moment so the capture side is ready
  D.seek(n0 / fps)
  for _ = 1, 20 do RS.RenderStepped:Wait() end
  local T0 = os.clock()
  _G.PromptimateRTState = "playing"
  local last = -1
  while true do
    local k = n0 + math.floor((os.clock() - T0) * fps * speed)
    if k > n1 then break end
    if k ~= last then
      last = k
      D.seek(k / fps)
      local c = cams[k]
      if c then
        local p, l = Vector3.new(c[1], c[2], c[3]), Vector3.new(c[4], c[5], c[6])
        local f = (l - p).Unit
        local right = f:Cross(Vector3.yAxis)
        if right.Magnitude < 1e-3 then right = Vector3.xAxis end
        cam.FieldOfView = c[7]
        cam.CFrame = CFrame.lookAt(p, l, right.Unit)
        if D.cutaway then D.cutaway(p, l) end
      end
      for i = 0, __N__ - 1 do
        bits[i].BackgroundColor3 = (bit32.extract(k, i) == 1) and Color3.new(1, 1, 1) or Color3.new(0, 0, 0)
      end
    end
    RS.RenderStepped:Wait()
  end
  if D.cutawayClear then D.cutawayClear() end
  _G.PromptimateRTState = "done"
end)
return 1'''

CLEANUP = r'''
local g = game:GetService("CoreGui"):FindFirstChild("PromptimateRT"); if g then g:Destroy() end
_G.PromptimateRTCams = nil
return 1'''


def _sub(s: str, **kw) -> str:
    for k, v in kw.items():
        s = s.replace(f"__{k}__", str(v))
    return s


def _monitor_of(rect):
    """(output index, left, top) of the monitor holding the viewport rect, in dxcam's output order."""
    import ctypes
    import ctypes.wintypes as W
    mons = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, W.HMONITOR, W.HDC, ctypes.POINTER(W.RECT), W.LPARAM)
    def cb(_h, _dc, r, _l):
        mons.append((r.contents.left, r.contents.top, r.contents.right, r.contents.bottom))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(0, 0, cb, 0)
    # dxcam lists the primary output first; EnumDisplayMonitors usually does too. Match by containment.
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    hit = next(((l, t, r, b) for l, t, r, b in mons if l <= cx < r and t <= cy < b), None)
    if not hit:
        raise RuntimeError("viewport is not on any monitor")
    l, t, r, b = hit
    # dxcam numbers outputs its own way: match primary-ness (the primary monitor sits at 0,0) and resolution
    import re as _re
    import dxcam
    outs = [(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) == "True") for m in
            _re.finditer(r"Output\[(\d+)\]: Res:\((\d+), (\d+)\).*?Primary:(\w+)", dxcam.output_info())]
    primary = (l, t) == (0, 0)
    cand = [o for o in outs if o[3] == primary and (o[1], o[2]) == (r - l, b - t)] or [o for o in outs if o[3] == primary]
    if not cand:
        raise RuntimeError(f"no DXGI output matches the monitor {hit}")
    return cand[0][0], l, t, (r - l, b - t)


def _decode(img: np.ndarray) -> int | None:
    """Frame index from the marker column of a BGRA viewport grab; None if the marker isn't readable."""
    def lum(i):
        y = Y0 + i * STEP + SQ // 2
        x = X0 + SQ // 2
        p = img[y - 2:y + 3, x - 2:x + 3, :3].astype(int)
        return p.mean()
    white, black = lum(BITS), lum(BITS + 1)
    if white - black < 120:
        return None
    mid = (white + black) / 2
    k = 0
    for i in range(BITS):
        v = lum(i)
        if abs(v - mid) < (white - black) * 0.25:
            return None            # caught mid-update
        if v > mid:
            k |= 1 << i
    return k


def record(st, rect, cams: dict[int, list[float]], n0: int, n1: int, fps: int, on_frame, speed: float = 1.0,
           log=print) -> set[int]:
    """Play frames n0..n1 live; on_frame(k, BGRA viewport image) is called once per captured frame (hand it to a
    worker: the capture loop must keep up). Returns the set of frame indices captured. cams[k] =
    [px,py,pz,lx,ly,lz,roblox_fov]."""
    import dxcam
    idx, ml, mt, _ = _monitor_of(rect)
    region = (rect[0] - ml, rect[1] - mt, rect[2] - ml, rect[3] - mt)
    st.luau(_sub(SETUP, N=BITS, SQ=SQ, X0=X0, Y0=Y0, STEP=STEP))
    ks = list(range(n0, n1 + 1))
    for i in range(0, len(ks), 250):
        chunk = [[round(v, 4) for v in cams[k]] for k in ks[i:i + 250]]
        st.luau(_sub(UPLOAD, J="[==[" + json.dumps(chunk, separators=(",", ":")) + "]==]", K0=ks[i]))
    cam = dxcam.create(output_idx=idx, output_color="BGRA")
    got: set[int] = set()
    bad = 0
    try:
        st.luau(_sub(PLAY, N=BITS, N0=n0, N1=n1, FPS=fps, SPEED=speed))
        t_end = time.perf_counter() + (n1 - n0 + 1) / fps / speed + 15
        last_seen = time.perf_counter()
        while time.perf_counter() < t_end:
            img = cam.grab(region=region)
            if img is None:
                if time.perf_counter() - last_seen > 3 and n1 in got:
                    break
                time.sleep(0.001)
                continue
            last_seen = time.perf_counter()
            k = _decode(img)
            if k is None:
                bad += 1
                continue
            if n0 <= k <= n1 and k not in got:
                got.add(k)
                on_frame(k, img.copy())
            if k >= n1:
                break
    finally:
        try:
            cam.release()
        except Exception:
            pass
        del cam
        st.luau(CLEANUP)
    log(f"realtime: {len(got)}/{n1 - n0 + 1} frames captured live, {bad} unreadable grabs")
    return got
