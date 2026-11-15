-- ShortDirector: deterministic per-frame posing for the 'In This Town' comparison short.
-- Python computes every frame's instructions (roblox/short/perf.py); this module only applies them:
--   D.setup(castJSON)            -> builds the characters (R15, scaled, coloured, props), returns stand heights
--   D.apply(frameJSON)           -> poses every character for one frame
-- Frame instruction per character:
--   { cf = {x,y,z,yaw,pitch?, px?,py?,pz?},            -- HumanoidRootPart (anim modes); optional pitch about a pivot
--     tracks = { {key, time, weight, loop}, ... },      -- AnimationTracks (stock ids "rbxassetid://..." or "kfs:Name")
--     pm = {clip, t, x, z, yaw},                        -- Promptimate clip (PromptimatePlayer:Seek), origin on the floor
--     phone = true|false }
local RS = game:GetService("ReplicatedStorage")
local Players = game:GetService("Players")
local HttpService = game:GetService("HttpService")
local KSP = game:GetService("KeyframeSequenceProvider")

local D = {}
D.chars = {}

local function weld(part, to, cf)
	part.Anchored = false; part.CanCollide = false; part.Massless = true; part.CanQuery = false; part.CanTouch = false
	part.CFrame = to.CFrame * cf
	local w = Instance.new("WeldConstraint"); w.Part0 = to; w.Part1 = part; w.Parent = part
	part.Parent = to.Parent
end

local function hat(rig, kind)
	local head = rig.Head
	local hy = head.Size.Y / 2
	if kind == "police" then
		local cap = Instance.new("Part"); cap.Name = "Cap"; cap.Size = Vector3.new(1.35, 0.42, 1.35)
		cap.Color = Color3.fromRGB(25, 35, 70); cap.Material = Enum.Material.Fabric
		weld(cap, head, CFrame.new(0, hy + 0.12, 0))
		local brim = Instance.new("Part"); brim.Name = "Brim"; brim.Size = Vector3.new(1.1, 0.08, 0.55)
		brim.Color = Color3.fromRGB(15, 15, 18)
		weld(brim, head, CFrame.new(0, hy - 0.05, -0.75) * CFrame.Angles(math.rad(-10), 0, 0))
		local badge = Instance.new("Part"); badge.Name = "Badge"; badge.Size = Vector3.new(0.3, 0.3, 0.05)
		badge.Color = Color3.fromRGB(240, 200, 60); badge.Material = Enum.Material.Metal
		weld(badge, head, CFrame.new(0, hy + 0.15, -0.69))
		local star = Instance.new("Part"); star.Name = "ChestBadge"; star.Size = Vector3.new(0.35, 0.4, 0.06)
		star.Color = Color3.fromRGB(240, 200, 60); star.Material = Enum.Material.Metal
		weld(star, rig.UpperTorso, CFrame.new(-0.45, 0.35, -rig.UpperTorso.Size.Z / 2 - 0.02))
	elseif kind == "bun" then
		local hair = Instance.new("Part"); hair.Name = "Hair"; hair.Size = Vector3.new(1.25, 0.5, 1.25)
		hair.Color = Color3.fromRGB(170, 170, 175); hair.Material = Enum.Material.Fabric
		weld(hair, head, CFrame.new(0, hy - 0.05, 0.08))
		local bun = Instance.new("Part"); bun.Shape = Enum.PartType.Ball; bun.Name = "Bun"; bun.Size = Vector3.new(0.7, 0.7, 0.7)
		bun.Color = Color3.fromRGB(170, 170, 175); bun.Material = Enum.Material.Fabric
		weld(bun, head, CFrame.new(0, hy + 0.25, 0.35))
	end
end

function D.setup(castJSON: string)
	local cast = HttpService:JSONDecode(castJSON)
	local folder = workspace:FindFirstChild("ShortCast")
	if folder then folder:Destroy() end
	folder = Instance.new("Folder"); folder.Name = "ShortCast"; folder.Parent = workspace
	D.chars = {}
	local Player = require(RS.Promptimate.PromptimatePlayer:Clone())
	D.Player = Player
	local out = {}
	for name, c in cast do
		local d = Instance.new("HumanoidDescription")
		d.HeightScale = c.height; d.WidthScale = c.width; d.DepthScale = c.width
		local col = c.colors
		d.HeadColor = Color3.fromRGB(table.unpack(col.Head))
		d.LeftArmColor = Color3.fromRGB(table.unpack(col.Arms)); d.RightArmColor = d.LeftArmColor
		d.TorsoColor = Color3.fromRGB(table.unpack(col.Torso))
		d.LeftLegColor = Color3.fromRGB(table.unpack(col.Legs)); d.RightLegColor = d.LeftLegColor
		local rig = Players:CreateHumanoidModelFromDescription(d, Enum.HumanoidRigType.R15)
		rig.Name = name
		for _, s in rig:GetChildren() do if s:IsA("LuaSourceContainer") then s:Destroy() end end
		local hum = rig:FindFirstChildOfClass("Humanoid")
		hum.DisplayDistanceType = Enum.HumanoidDisplayDistanceType.None
		rig.HumanoidRootPart.Anchored = true
		rig:PivotTo(CFrame.new(0, hum.HipHeight + rig.HumanoidRootPart.Size.Y / 2, -200))
		rig.Parent = folder
		if c.hat then hat(rig, c.hat) end
		local phone = Instance.new("Part"); phone.Name = "Phone"; phone.Size = Vector3.new(0.22, 0.6, 0.08)
		phone.Color = Color3.fromRGB(20, 20, 24); phone.Material = Enum.Material.SmoothPlastic
		weld(phone, rig.RightHand, CFrame.new(0, -0.35, -0.12) * CFrame.Angles(0, 0, 0))
		phone.Transparency = 1
		local lowest = math.min(rig.LeftFoot.Position.Y - rig.LeftFoot.Size.Y / 2, rig.RightFoot.Position.Y - rig.RightFoot.Size.Y / 2)
		local animator = hum:FindFirstChildOfClass("Animator") or Instance.new("Animator", hum)
		D.chars[name] = { rig = rig, hum = hum, animator = animator, tracks = {}, clips = {}, phone = phone,
			hrpY = rig.HumanoidRootPart.Position.Y - lowest }
		out[name] = { stand = rig.LowerTorso.Position.Y - lowest, hrpY = rig.HumanoidRootPart.Position.Y - lowest,
			hipHeight = hum.HipHeight }
	end
	return HttpService:JSONEncode(out)
end

local function track(ch, key: string)
	local tr = ch.tracks[key]
	if tr then return tr end
	local anim = Instance.new("Animation")
	if string.sub(key, 1, 4) == "kfs:" then
		local kfs = game:GetService("ServerStorage").RBX_ASSISTANT_ANIMGEN[string.sub(key, 5)]
		anim.AnimationId = KSP:RegisterKeyframeSequence(kfs)
	else
		anim.AnimationId = key
	end
	tr = ch.animator:LoadAnimation(anim)
	tr.Priority = Enum.AnimationPriority.Action
	tr.Looped = false
	tr:Play(0, 0.0001, 0)
	tr:AdjustSpeed(0)
	local t0 = os.clock()
	while tr.Length == 0 and os.clock() - t0 < 5 do task.wait() end
	ch.tracks[key] = tr
	return tr
end

function D.lengths(name: string, keysJSON: string)
	local ch = D.chars[name]
	local out = {}
	for _, k in HttpService:JSONDecode(keysJSON) do out[k] = track(ch, k).Length end
	return HttpService:JSONEncode(out)
end

local function clip(ch, name: string, x, z, yaw)
	local key = name .. string.format("@%.3f,%.3f,%.4f", x, z, yaw)
	local p = ch.clips[key]
	if p then return p end
	local data = D.Player.decode(require(RS.Promptimate[name]:Clone()))
	p = D.Player.new(ch.rig, data, { origin = CFrame.new(x, 0, z) * CFrame.Angles(0, yaw, 0) })
	ch.clips[key] = p
	return p
end

function D.apply(frameJSON: string)
	local frame = HttpService:JSONDecode(frameJSON)
	for name, f in frame do
		local ch = D.chars[name]
		local used = {}
		if f.pm then
			for _, tr in ch.tracks do tr:AdjustWeight(0.0001, 0) end
			local p = clip(ch, f.pm[1], f.pm[3], f.pm[4], f.pm[5])
			p:Seek(f.pm[2])
		else
			-- clear any Promptimate joint transforms left from B-mode posing
			if f.tracks then
				for _, t in f.tracks do
					local tr = track(ch, t[1])
					local len = tr.Length > 0 and tr.Length or 1
					local tp = t[4] and (t[2] % len) or math.clamp(t[2], 0, len - 1e-3)
					tr.TimePosition = tp
					tr:AdjustWeight(math.max(t[3], 0.0001), 0)
					used[t[1]] = true
				end
			end
			for k, tr in ch.tracks do if not used[k] then tr:AdjustWeight(0.0001, 0) end end
			local c = f.cf
			local cf = CFrame.new(c[1], c[2], c[3]) * CFrame.Angles(0, c[4], 0)
			if c[5] and c[5] ~= 0 then
				-- tip over about a ground pivot (feet), in the character's own frame: pitch backward
				local pivot = CFrame.new(c[1], 0, c[3]) * CFrame.Angles(0, c[4], 0)
				cf = pivot * CFrame.Angles(c[5], 0, 0) * pivot:Inverse() * cf
			end
			ch.rig.HumanoidRootPart.CFrame = cf
		end
		ch.phone.Transparency = f.phone and 0 or 1
	end
	task.wait(); task.wait()
	local out = {}
	for name, ch in D.chars do
		local p = ch.rig.LowerTorso.Position
		table.insert(out, string.format("%s=%.2f,%.2f,%.2f", name, p.X, p.Y, p.Z))
	end
	return table.concat(out, ";")
end

-- Lowest points for calibration: min bottom Y of the given parts (e.g. thighs on a seat, or the whole body)
function D.lowest(name: string, partsJSON: string)
	local ch = D.chars[name]
	local best, which = math.huge, ""
	for _, pn in HttpService:JSONDecode(partsJSON) do
		local part = ch.rig[pn]
		local cf, s = part.CFrame, part.Size / 2
		for _, sx in { -1, 1 } do for _, sy in { -1, 1 } do for _, sz in { -1, 1 } do
			local y = (cf * Vector3.new(sx * s.X, sy * s.Y, sz * s.Z)).Y
			if y < best then best, which = y, pn end
		end end end
	end
	local lt = ch.rig.LowerTorso.Position
	return string.format("%.4f,%s,%.3f,%.3f,%.3f", best, which, lt.X, lt.Y, lt.Z)
end

return D
