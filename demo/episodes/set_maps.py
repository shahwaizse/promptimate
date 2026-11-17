"""Blocking maps for the sourced sets: per set a top-down height map (raycast every 0.5 stud: open floor where a
character can stand, furniture, walls) with world-coordinate ticks, next to two 3/4 renders. Writers use it to put
characters (CAST "at") and cameras where there is open floor.
usage: set_maps.py outdir [SetName ...]"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server")); sys.path.insert(0, str(ROOT / "roblox" / "short"))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import roblox_record as RR  # noqa: E402
import fastgrab as FG  # noqa: E402
from roblox_studio import studio  # noqa: E402

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
st = studio(); RR._ensure_running(); vp = RR._viewport()
names = sys.argv[2:] or json.loads(st.luau(
    'local t = {} for _, m in workspace.Sets:GetChildren() do if m:IsA("Model") then local _, s = m:GetBoundingBox() '
    'if s.X > 12 and s.Z > 12 then table.insert(t, m.Name) end end end return game:GetService("HttpService"):JSONEncode(t)'))
SCAN = r'''
local m = workspace.Sets:FindFirstChild("__N__")
local cf, s = m:GetBoundingBox()
local rp = RaycastParams.new(); rp.FilterType = Enum.RaycastFilterType.Include; rp.FilterDescendantsInstances = { m, workspace:FindFirstChild("Town") }
local x0, z0, step = cf.X - s.X / 2, cf.Z - s.Z / 2, math.max(0.5, math.max(s.X, s.Z) / 110)
local nx, nz = math.floor(s.X / step), math.floor(s.Z / step)
local top = cf.Y + s.Y / 2 + 1
local floorY = {}
local rows = {}
-- the floor: lowest broad surface under the roof (a ray from just under the ceiling: rays from above hit roofs)
for j = 0, nz - 1 do
  local row = {}
  for i = 0, nx - 1 do
    local x, z = x0 + (i + 0.5) * step, z0 + (j + 0.5) * step
    local hits, from, ys = 0, Vector3.new(x, top, z), {}
    for k = 1, 6 do
      local h = workspace:Raycast(from, Vector3.new(0, -(from.Y - (cf.Y - s.Y / 2) + 2), 0), rp)
      if not h then break end
      table.insert(ys, math.floor(h.Position.Y * 10 + 0.5) / 10)
      from = h.Position - Vector3.new(0, 0.05, 0)
    end
    -- compact: lowest hit, and the gap up to the next surface above it (99 = open sky)
    local lo = ys[#ys]
    local gap = 99
    if lo then for q = 1, #ys - 1 do if ys[q] > lo + 0.2 then gap = math.min(gap, ys[q] - lo) end end end
    row[i + 1] = lo and string.format("%.1f:%.1f", lo, gap) or "-"
  end
  rows[j + 1] = table.concat(row, " ")
end
return game:GetService("HttpService"):JSONEncode({ x0 = x0, z0 = z0, step = step, nx = nx, nz = nz, rows = rows,
  centre = { cf.X, cf.Y, cf.Z }, size = { s.X, s.Y, s.Z } })'''
index = {}
for n in names:
    d = json.loads(st.luau(SCAN.replace("__N__", n), timeout=600))
    nx, nz, step = d["nx"], d["nz"], d["step"]
    # floor height = the most common lowest hit; per cell: standable if lowest hit within 0.3 of floor and the next
    # hit above it (furniture/ceiling) is > 5.5 studs higher (or none)
    d["rows"] = [[None if c == "-" else tuple(map(float, c.split(":"))) for c in r.split(" ")] for r in d["rows"]]
    lows = [c[0] for r in d["rows"] for c in r if c]
    floor = float(np.median(lows)) if lows else 0.0
    img = np.zeros((nz, nx, 3), np.uint8)
    for j, r in enumerate(d["rows"]):
        for i, c in enumerate(r):
            if not c:
                img[j, i] = (30, 30, 30); continue
            lo, gap = c
            clear = gap > 5.5
            if abs(lo - floor) < 0.35 and clear:
                img[j, i] = (90, 200, 110)                     # open floor
            elif abs(lo - floor) < 0.35:
                img[j, i] = (230, 200, 80)                     # floor under something low (table, bed, bench)
            else:
                img[j, i] = (200, 80, 80) if lo - floor > 2.5 else (220, 150, 100)
    scale = max(1, int(700 / max(nx, nz)))
    im = Image.fromarray(img).resize((nx * scale, nz * scale), Image.NEAREST)
    dr = ImageDraw.Draw(im)
    for v in range(int(math.ceil(d["x0"] / 5) * 5), int(d["x0"] + nx * step), 5):
        px = int((v - d["x0"]) / step * scale); dr.line([(px, 0), (px, 6)], fill=(255, 255, 255)); dr.text((px + 1, 8), str(v), fill=(255, 255, 255))
    for v in range(int(math.ceil(d["z0"] / 5) * 5), int(d["z0"] + nz * step), 5):
        py = int((v - d["z0"]) / step * scale); dr.line([(0, py), (6, py)], fill=(255, 255, 255)); dr.text((8, py - 5), str(v), fill=(255, 255, 255))
    dr.text((4, im.height - 14), f"{n}: x right, z down. green=open floor (y={floor:.1f}) yellow=under furniture red=tall", fill=(255, 255, 255))
    # two 3/4 renders from opposite corners, inside-looking (camera at standing eye height near the walls)
    cx, cy, cz = d["centre"]; sx, sy, sz = d["size"]
    FG.pin_studio(True); rect = FG.calibrate(st, vp)
    views = []
    for ang in (35, 215):
        a = math.radians(ang)
        r = 0.42 * math.hypot(sx, sz)
        cam = [cx + r * math.sin(a), floor + min(8, sy * 0.6), cz + r * math.cos(a)]
        views.append(FG.portrait(st, rect, vp, cam, [cx, floor + 2.5, cz], 60).resize((360, 640)))
    sheet = Image.new("RGB", (im.width + 720, max(im.height, 640)), (20, 20, 20))
    sheet.paste(im, (0, 0)); sheet.paste(views[0], (im.width, 0)); sheet.paste(views[1], (im.width + 360, 0))
    sheet.save(out / f"{n}.jpg")
    index[n] = {"floor_y": floor, "centre": d["centre"], "size": d["size"], "map": str(out / f"{n}.jpg")}
    print(n, json.dumps(index[n]), flush=True)
(out / "index.json").write_text(json.dumps(index, indent=1))
