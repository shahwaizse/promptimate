--!nocheck
-- ShortDirector (Promptimate package): plays the performances that the `roblox_perform` MCP tool pushed into this
-- place. Lives in ReplicatedStorage.Promptimate next to PromptimatePlayer; clips are in Promptimate.Clips and the cue
-- sheet is the Promptimate.Performance module (JSON: every character's continue_from chain with start times and
-- world origins).
--
--   local D = require(game.ReplicatedStorage.Promptimate.ShortDirector)
--   D.play()          -- realtime playback of every character from story time 0 (Play mode / screen recording)
--   D.play(12.5)      -- from 12.5 s;  local h = D.play(); h:Stop();  h.Ended:Wait()
--   D.seek(t)         -- pose every character at story time t and hold (frame-by-frame recording, scrubbing)
--   D.length()        -- story length in seconds
--
-- PromptimateAutoplay (installed by roblox_install / roblox_perform) calls D.autoplay() when the game starts: in
-- Play mode on the client (what a screen recording sees), in Run mode on the server. Set the Performance's
-- `autoplay` attribute (Promptimate folder attribute "Autoplay" = false) to switch it off.

local RS = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local HttpService = game:GetService("HttpService")

local D = {}
D.cache = {}          -- clip players: actor .. "|" .. module .. "|" .. origin
D.actors = nil
D.perf = nil

local BODY = { "Head", "UpperTorso", "LowerTorso", "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm",
	"RightLowerArm", "RightHand", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperLeg", "RightLowerLeg",
	"RightFoot" }
D.BODY = BODY
local BODY6 = { "Head", "Torso", "Left Arm", "Right Arm", "Left Leg", "Right Leg" }
local function bodyOf(rig: Model)
	return rig:FindFirstChild("UpperTorso") and BODY or BODY6
end
D.bodyOf = bodyOf

local function folder()
	return RS:WaitForChild("Promptimate")
end

local function fresh(module: ModuleScript)
	-- require a fresh copy: Studio caches require() per instance, and tools re-upload sources in place
	local ok, res = pcall(function()
		return require(module:Clone())
	end)
	if ok then
		return res
	end
	return require(module)
end

local function resolve(path)
	local inst = game
	for _, name in path do
		inst = inst and inst:FindFirstChild(name)
	end
	return inst
end
D.resolve = resolve

function D.prepare(rig: Model)
	for _, s in rig:GetDescendants() do
		if (s:IsA("LocalScript") or s:IsA("Script")) and s.Name == "Animate" then
			s.Enabled = false
		end
	end
	local hum = rig:FindFirstChildOfClass("Humanoid")
	if hum then
		local animator = hum:FindFirstChildOfClass("Animator")
		if animator then
			for _, tr in animator:GetPlayingAnimationTracks() do
				tr:Stop(0)
			end
		end
		hum.AutoRotate = false
	end
	local hrp = rig:FindFirstChild("HumanoidRootPart")
	if hrp then
		hrp.Anchored = true
	end
end

function D.Player()
	if not D._player then
		D._player = fresh(folder().PromptimatePlayer)
	end
	return D._player
end

-- (Re)read the cue sheet. Called automatically by seek/play; call again after roblox_perform pushed new clips.
function D.load()
	D._player = nil
	D._faces = nil
	D.cache = {}
	local old = workspace:FindFirstChild("PromptimateFX")
	if old then old:Destroy() end
	D._fx = {}
	local perf = HttpService:JSONDecode(fresh(folder().Performance))
	D.perf = perf
	D.actors = {}
	for name, a in perf.actors do
		local rig = resolve(a.path)
		if rig then
			D.prepare(rig)
			D.actors[name] = { rig = rig, clips = a.clips, faces = a.faces }
		else
			warn("ShortDirector: character not found: " .. table.concat(a.path, "."))
		end
	end
	return D.actors
end

function D.length(): number
	if not D.actors then D.load() end
	local e = 0
	for _, a in D.actors do
		local c = a.clips[#a.clips]
		if c then e = math.max(e, c.s + c.d) end
	end
	return e
end

local function clipPlayer(name, a, c)
	local key = name .. "|" .. c.m .. string.format("|%.3f,%.3f,%.3f,%.4f", c.x, c.y, c.z, c.yaw)
	local p = D.cache[key]
	if p then return p end
	local Player = D.Player()
	local data = Player.decode(fresh(folder().Clips[c.m]))
	p = Player.new(a.rig, data, { origin = CFrame.new(c.x, c.y, c.z) * CFrame.Angles(0, c.yaw, 0),
		selfCollide = (D.options and D.options.selfCollide == true) or false })
	D.cache[key] = p
	return p
end

-- Active clip and local time of an actor at story time t (holds the first frame before its first cue and the last
-- frame after its chain ends).
local function active(a, t)
	local k = 1
	for i, c in a.clips do
		if c.s <= t + 1e-6 then k = i end
	end
	local c = a.clips[k]
	return c, math.clamp(t - c.s, 0, c.d)
end

function D.poseActor(name: string, t: number)
	local a = D.actors[name]
	if not a or #a.clips == 0 then return nil end
	local c, lt = active(a, t)
	local p = clipPlayer(name, a, c)
	p:Seek(lt)
	a._player = p
	return p, c
end

-- Expression cues: perf.actors[name].faces = {{t, "happy"}, ...} (Faces.lua); the latest cue at or before t holds
local function faceAt(a, t)
	local cur
	for _, c in a.faces or {} do
		if c[1] <= t + 1e-6 then cur = c[2] end
	end
	return cur
end

-- Prop cues: perf.props = {{path = {"Sets","Bakery","Chair"}, show = {{t0, t1}, ...}, attach = {actor, hand, offset =
-- {x, y, z, rx, ry, rz}}}}: visible only inside its spans (moved far below otherwise), and carried in a hand if attached
local HIDE = Vector3.new(0, -2000, 0)
local function poseProps(t: number)
	-- several cues may name the same object (on the desk, then in Timmy's hand, then in Preston's): per object, the
	-- cue whose span contains t wins; an object with spans and none active is hidden; one without spans stays home
	local byInst = {}
	for _, p in (D.perf and D.perf.props) or {} do
		if p._inst == nil then
			p._inst = resolve(p.path) or false
		end
		local inst = p._inst
		if inst then
			local e = byInst[inst]
			if not e then
				e = { active = nil, spans = false }
				byInst[inst] = e
				if D._propHome == nil then D._propHome = {} end
				if D._propHome[inst] == nil then
					-- the home pose survives director reloads (a prop may be hidden or carried when a new one starts)
					local h = inst:GetAttribute("PromptimateHome")
					if typeof(h) ~= "CFrame" then
						h = inst:GetPivot()
						inst:SetAttribute("PromptimateHome", h)
					end
					D._propHome[inst] = h
				end
			end
			if p.show then
				e.spans = true
				for _, sp in p.show do
					if not e.active and t >= sp[1] - 1e-6 and t <= sp[2] + 1e-6 then e.active = p end
				end
			elseif not e.active then
				e.always = p
			end
		end
	end
	for inst, e in byInst do
		local p = e.active or e.always
		local home = D._propHome[inst]
		if not p then
			inst:PivotTo(home + HIDE)
		elseif p.attach and D.actors[p.attach.actor] then
			local a = D.actors[p.attach.actor]
			local hn = (p.attach.hand or "Right") .. "Hand"
			local pl = a._player
			local cf = pl and pl.targets and pl.targets[hn] or (a.rig:FindFirstChild(hn) and a.rig[hn].CFrame)
			if cf then
				local o = p.attach.offset or { 0, -0.6, 0, 0, 0, 0 }
				inst:PivotTo(cf * CFrame.new(o[1], o[2], o[3]) * CFrame.Angles(math.rad(o[4]), math.rad(o[5]), math.rad(o[6])))
			end
		else
			inst:PivotTo(home)
		end
	end
end

-- Effects over a character's head (perf.fx = {{actor, kind, show = {{t0, t1}, ...}}}): the visible consequence
-- of a story's rule. kinds: rain / snow (a cloud that follows the head), sparkle, confetti, hearts.
local FX = {
	rain = { cloud = Color3.fromRGB(95, 100, 110), color = Color3.fromRGB(40, 90, 210), rate = 160, speed = 14,
		life = 0.5, size = 0.28, dir = Enum.NormalId.Bottom },
	snow = { cloud = Color3.fromRGB(215, 220, 230), color = Color3.fromRGB(255, 255, 255), rate = 45, speed = 3,
		life = 1.4, size = 0.22, dir = Enum.NormalId.Bottom },
	sparkle = { color = Color3.fromRGB(255, 220, 90), rate = 25, speed = 1.5, life = 0.9, size = 0.35, dir = Enum.NormalId.Top },
	confetti = { color = nil, rate = 70, speed = 7, life = 1.2, size = 0.25, dir = Enum.NormalId.Top },
	hearts = { color = Color3.fromRGB(255, 90, 130), rate = 10, speed = 2, life = 1.2, size = 0.45, dir = Enum.NormalId.Top },
}
local function fxFolder()
	local f = workspace:FindFirstChild("PromptimateFX")
	if not f then f = Instance.new("Folder"); f.Name = "PromptimateFX"; f.Parent = workspace end
	return f
end
local function buildLabel()
	local m = Instance.new("Model"); m.Name = "FX_label"
	local src = Instance.new("Part"); src.Name = "Source"; src.Anchored = true; src.CanCollide = false
	src.CanQuery = false; src.Transparency = 1; src.Size = Vector3.new(0.2, 0.2, 0.2); src.Parent = m
	-- the recorder rolls the camera 90 degrees (portrait frames from a landscape viewport) and billboards roll with
	-- it: the label is drawn turned back by -90 degrees so it reads upright in the video
	local g = Instance.new("BillboardGui"); g.Name = "Label"; g.Size = UDim2.fromScale(1.3, 5); g.LightInfluence = 0
	g.Adornee = src; g.Parent = src
	local t = Instance.new("TextLabel"); t.Name = "Text"; t.BackgroundTransparency = 1
	t.AnchorPoint = Vector2.new(0.5, 0.5); t.Position = UDim2.fromScale(0.5, 0.5)
	t.Size = UDim2.fromScale(5 / 1.3, 1.3 / 5); t.Rotation = -90
	t.Font = Enum.Font.FredokaOne; t.TextScaled = true; t.TextColor3 = Color3.fromRGB(255, 214, 40)
	t.TextStrokeTransparency = 0; t.TextStrokeColor3 = Color3.fromRGB(40, 25, 0); t.Parent = g
	m.Parent = fxFolder()
	return m
end
local function buildFx(kind: string)
	if kind == "label" then return buildLabel() end
	local spec = FX[kind] or FX.sparkle
	local m = Instance.new("Model"); m.Name = "FX_" .. kind
	local src = Instance.new("Part"); src.Name = "Source"; src.Anchored = true; src.CanCollide = false
	src.CanQuery = false; src.Transparency = 1; src.Size = Vector3.new(3, 0.2, 3); src.Parent = m
	if spec.cloud then
		for i, o in { Vector3.new(-0.9, 0, 0), Vector3.new(0.8, 0.1, 0.2), Vector3.new(0, 0.45, -0.1), Vector3.new(0.1, 0.1, 0.7) } do
			local b = Instance.new("Part"); b.Name = "Puff" .. i; b.Shape = Enum.PartType.Ball; b.Anchored = true
			b.CanCollide = false; b.CanQuery = false; b.Material = Enum.Material.SmoothPlastic; b.Color = spec.cloud
			b.Size = Vector3.new(1.7, 1.7, 1.7); b:SetAttribute("Offset", o); b.Parent = m
		end
	end
	if kind == "rain" or kind == "snow" then
		-- falling drops as parts placed from story time (a particle sprite is a star and stretches with the rolled
		-- recording camera; these read as rain/snow and play the same live and frame by frame)
		for i = 1, (kind == "rain") and 22 or 18 do
			local d = Instance.new("Part"); d.Name = "Drop" .. i; d.Anchored = true; d.CanCollide = false; d.CanQuery = false
			d.Material = Enum.Material.SmoothPlastic; d.Color = spec.color; d.CastShadow = false
			if kind == "rain" then d.Size = Vector3.new(0.07, 0.55, 0.07); d.Transparency = 0.15
			else d.Shape = Enum.PartType.Ball; d.Size = Vector3.new(0.22, 0.22, 0.22) end
			d:SetAttribute("Seed", i)
			d.Parent = m
		end
		m.Parent = fxFolder()
		return m
	end
	local e = Instance.new("ParticleEmitter")
	e.Rate = spec.rate; e.Speed = NumberRange.new(spec.speed); e.Lifetime = NumberRange.new(spec.life)
	e.Size = NumberSequence.new(spec.size); e.EmissionDirection = spec.dir; e.SpreadAngle = Vector2.new(8, 8)
	e.LightEmission = (kind == "rain") and 0 or 1; e.Enabled = false
	pcall(function() e.Brightness = (kind == "sparkle" or kind == "hearts") and 4 or 1.5 end)   -- over the bloom threshold: glints glow
	if kind == "sparkle" then e.Texture = "rbxasset://textures/particles/sparkles_main.dds"; e.Rotation = NumberRange.new(0, 360) end
	if spec.color then
		e.Color = ColorSequence.new(spec.color)
	else
		e.Color = ColorSequence.new({ ColorSequenceKeypoint.new(0, Color3.fromRGB(255, 80, 80)),
			ColorSequenceKeypoint.new(0.5, Color3.fromRGB(80, 200, 255)), ColorSequenceKeypoint.new(1, Color3.fromRGB(255, 230, 60)) })
	end
	-- (no Squash: particle stretch follows the rolled recording camera)
	e.Parent = src
	m.Parent = fxFolder()
	return m
end
local function poseFx(t: number)
	local list = D.perf and D.perf.fx
	if not list then return end
	D._fx = D._fx or {}
	for i, f in list do
		local on, text = false, f.text
		for _, sp in f.show or {} do
			if t >= sp[1] and t <= sp[2] then on = true; text = sp[3] or f.text end
		end
		local a = D.actors[f.actor]
		local m = D._fx[i]
		if not m or not m.Parent then m = buildFx(f.kind); D._fx[i] = m end
		local head = a and a._player and a._player.targets and a._player.targets.Head
		if f.kind == "label" then
			local g = m.Source:FindFirstChild("Label")
			if on and head then
				m.Source.CFrame = CFrame.new(head.Position + Vector3.new(0, 2.3, 0))   -- above hat/hair: off the top of close-ups (reviewers: labels sat on faces)
				g.Enabled = true
				g.Text.Text = tostring(text or "")
			else
				g.Enabled = false
			end
			continue
		end
		local e = m.Source:FindFirstChildOfClass("ParticleEmitter")
		local cloudy = f.kind == "rain" or f.kind == "snow"
		if on and head then
			local top = head.Position + Vector3.new(0, cloudy and 3.0 or 0.6, 0)
			m.Source.CFrame = CFrame.new(top)
			local fall = (f.kind == "rain") and 9 or 1.6       -- studs per second
			local span = 2.6                                   -- from the cloud down past the head
			for _, b in m:GetChildren() do
				if b.Name:sub(1, 4) == "Puff" then
					b.Transparency = 0; b.CFrame = CFrame.new(top + b:GetAttribute("Offset"))
				elseif b.Name:sub(1, 4) == "Drop" then
					local k = b:GetAttribute("Seed")
					local ox, oz = math.sin(k * 12.9898) * 1.1, math.cos(k * 78.233) * 1.1
					local ph = ((t * fall / span) + (k * 0.6180339) % 1) % 1
					local wob = (f.kind == "snow") and math.sin(t * 2 + k) * 0.25 or 0
					b.Transparency = (f.kind == "rain") and 0.15 or 0
					b.CFrame = CFrame.new(top + Vector3.new(ox + wob, -0.6 - ph * span, oz))
				end
			end
			if e then e.Enabled = true end
		else
			if e then e.Enabled = false end
			for _, b in m:GetChildren() do
				if b.Name:sub(1, 4) == "Puff" or b.Name:sub(1, 4) == "Drop" then b.Transparency = 1 end
			end
		end
	end
end

D.poseFx = poseFx

function D.seek(t: number)
	if not D.actors then D.load() end
	for name, a in D.actors do
		D.poseActor(name, t)
		local f = faceAt(a, t)
		if f then
			if not D._faces then D._faces = fresh(folder().Faces) end
			D._faces.set(a.rig, f)
		end
	end
	poseProps(t)
	poseFx(t)
end

function D.play(t0: number?)
	if not D.actors then D.load() end
	local handle = { Ended = Instance.new("BindableEvent"), playing = true }
	local start = os.clock() - (t0 or 0)
	local finish = D.length()
	local event = RunService:IsClient() and RunService.PreRender or RunService.PreSimulation
	handle.conn = event:Connect(function()
		local t = os.clock() - start
		D.seek(math.min(t, finish))
		if t >= finish then
			handle.conn:Disconnect()
			handle.playing = false
			handle.Ended:Fire()
		end
	end)
	function handle:Stop()
		if self.conn then self.conn:Disconnect() end
		self.playing = false
	end
	return handle
end

function D.autoplay()
	local f = folder()
	if f:GetAttribute("Autoplay") == false then return end
	if not f:FindFirstChild("Performance") then return end
	D.load()
	D.seek(0)
	task.wait(f:GetAttribute("StartDelay") or 1)
	return D.play(0)
end

-- ------------------------------------------------------------------------------------------- measuring / checks
local function castExclude()
	local list = {}
	if not D.actors then return list end
	for _, a in D.actors do table.insert(list, a.rig) end
	return list
end

local function boxLowest(cf: CFrame, size: Vector3): number
	local s = size / 2
	local best = math.huge
	for _, sx in { -1, 1 } do for _, sy in { -1, 1 } do for _, sz in { -1, 1 } do
		best = math.min(best, (cf * Vector3.new(sx * s.X, sy * s.Y, sz * s.Z)).Y)
	end end end
	return best
end

-- Oriented boxes overlap test (separating axis theorem, 15 axes)
local function obbOverlap(ca: CFrame, sa: Vector3, cb: CFrame, sb: Vector3): boolean
	local A = { ca.XVector, ca.YVector, ca.ZVector }
	local B = { cb.XVector, cb.YVector, cb.ZVector }
	local ha, hb = sa / 2, sb / 2
	local ea, eb = { ha.X, ha.Y, ha.Z }, { hb.X, hb.Y, hb.Z }
	local d = cb.Position - ca.Position
	local axes = {}
	for i = 1, 3 do table.insert(axes, A[i]); table.insert(axes, B[i]) end
	for i = 1, 3 do for j = 1, 3 do
		local c = A[i]:Cross(B[j])
		if c.Magnitude > 1e-6 then table.insert(axes, c.Unit) end
	end end
	local depth = math.huge
	for _, ax in axes do
		local ra = ea[1] * math.abs(A[1]:Dot(ax)) + ea[2] * math.abs(A[2]:Dot(ax)) + ea[3] * math.abs(A[3]:Dot(ax))
		local rb = eb[1] * math.abs(B[1]:Dot(ax)) + eb[2] * math.abs(B[2]:Dot(ax)) + eb[3] * math.abs(B[3]:Dot(ax))
		local o = ra + rb - math.abs(d:Dot(ax))
		if o < 0 then return false, 0 end
		depth = math.min(depth, o)
	end
	return true, depth   -- penetration depth: smallest overlap along the separating axes
end
D.obbOverlap = obbOverlap
local MIN_DEPTH = 0.15   -- studs: touching/leaning (a backrest, a wall) isn't passing through

local function visible(p: BasePart): boolean
	return p.Transparency < 0.95 and not p:IsA("Terrain")
end

-- Set walls the camera may cut away (a film set's wild wall): thin, large, vertical parts of workspace.Sets.
-- Framing ignores them; at render time the ones between the camera and its aim point are hidden for that frame.
local cullCache = nil
local function cullables()
	if cullCache then return cullCache end
	cullCache = {}
	for _, rn in { "Sets", "Town" } do
		local root = workspace:FindFirstChild(rn)
		for _, p in root and root:GetDescendants() or {} do
			if p:IsA("BasePart") and p.Transparency < 0.95 then
				local sz = p.Size
				local axes = { { sz.X, p.CFrame.RightVector }, { sz.Y, p.CFrame.UpVector }, { sz.Z, p.CFrame.LookVector } }
				table.sort(axes, function(a, b) return a[1] < b[1] end)
				-- wall-sized only (furniture panels like a throne's back must still block the camera)
				if rn == "Sets" and axes[1][1] <= 1.2 and axes[2][1] >= 8 and math.abs(axes[1][2].Y) < 0.5 then
					table.insert(cullCache, p)
				elseif axes[2][1] <= 0.9 and axes[3][1] >= 5 and math.abs(axes[3][2].Y) > 0.9 then
					table.insert(cullCache, p)      -- lamp posts, sign poles: a crew would move them out of the shot
				end
			end
		end
	end
	return cullCache
end
D.cullables = cullables
local cullSet = nil
local function isCull(p: Instance): boolean
	if not cullSet then
		cullSet = {}
		for _, q in cullables() do cullSet[q] = true end
	end
	return cullSet[p] == true
end

local cutHidden = {}
-- Hide the cullable walls between the camera and its aim point (and any the camera sits in); restore the rest.
function D.cutaway(pos: Vector3, look: Vector3)
	local dof = game:GetService("Lighting"):FindFirstChild("PromptimateDOF")
	if dof then   -- focus on the aim point (the subject); the background softens like a real lens
		local d = (look - pos).Magnitude
		dof.FocusDistance = d
		dof.InFocusRadius = math.max(4, d * 0.35)
	end
	local want = {}
	local list = cullables()
	if #list > 0 then
		local rp = RaycastParams.new()
		rp.FilterType = Enum.RaycastFilterType.Include
		rp.FilterDescendantsInstances = list
		for _, off in { Vector3.zero, Vector3.new(0, 1.2, 0), Vector3.new(0, -1.2, 0) } do
			local from, to = pos, look + off
			for _ = 1, 4 do
				local hit = workspace:Raycast(from, to - from, rp)
				if not hit then break end
				want[hit.Instance] = true
				from = hit.Position + (to - from).Unit * 0.05
			end
		end
		for _, q in list do   -- the camera inside a wall
			local lp = q.CFrame:PointToObjectSpace(pos)
			local h = q.Size / 2 + Vector3.new(0.3, 0.3, 0.3)
			if math.abs(lp.X) <= h.X and math.abs(lp.Y) <= h.Y and math.abs(lp.Z) <= h.Z then want[q] = true end
		end
	end
	for q, t in cutHidden do
		if not want[q] then q.Transparency = t; cutHidden[q] = nil end
	end
	for q in want do
		if cutHidden[q] == nil then cutHidden[q] = q.Transparency; q.Transparency = 1 end
	end
end
function D.cutawayClear()
	for q, t in cutHidden do q.Transparency = t end
	cutHidden = {}
end

local function ownerName(p: Instance): string
	local m = p:FindFirstAncestorOfClass("Model")
	if m and m ~= workspace then
		return m.Name .. "." .. p.Name      -- "Officer.Head", "Bench2.Back"
	end
	return p.Name
end

-- Rest measurements of a character (studs): standing hips height above the feet, current floor point and facing,
-- ground height under it.
function D.measure(rig: Model)
	local Player = D.Player()
	local stand, rootToHips = Player.measure(rig)
	local hrp = rig:FindFirstChild("HumanoidRootPart")
	local hum = rig:FindFirstChildOfClass("Humanoid")
	local pos, look = hrp.Position, hrp.CFrame.LookVector
	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { rig }
	local hit = workspace:Raycast(pos + Vector3.new(0, 2, 0), Vector3.new(0, -60, 0), params)
	local floorY = pos.Y - hum.HipHeight - hrp.Size.Y / 2
	return { stand = stand, rootToHips = rootToHips, x = pos.X, z = pos.Z, floor = floorY,
		ground = hit and hit.Position.Y or floorY, lookX = look.X, lookZ = look.Z, r15 = hum.RigType == Enum.HumanoidRigType.R15 }
end

-- Staging probe of one actor at story times `times` (everyone else posed at the same time):
-- per sample {t, hips{x,y,z}, look{x,z}, low (lowest body point), lowPart, foot (lowest foot bottom), gF (ground
-- under the feet), gH (ground under the hips), hits {names of scene parts the body overlaps}, thigh (lowest point of
-- hips+thighs, for seats)}. opts.ignore: names of parts not counted as collisions (the seat being sat on).
function D.probe(name: string, times, opts)
	if not D.actors then D.load() end
	opts = opts or {}
	local ignore = {}
	for _, n in opts.ignore or {} do ignore[n] = true end
	-- seats in use: their sitting surface and anything below it (legs) are not collisions; a backrest still is
	local seatTops = opts.seats or {}
	local function seatPart(q: BasePart): boolean
		for sname, top in seatTops do
			local m = workspace:FindFirstChild(sname, true)
			if m and (q == m or q:IsDescendantOf(m)) and q.Position.Y + q.Size.Y / 2 <= top + 0.2 then
				return true
			end
		end
		return false
	end
	local a = D.actors[name]
	local exclude = castExclude()
	local rp = RaycastParams.new()
	rp.FilterType = Enum.RaycastFilterType.Exclude
	rp.FilterDescendantsInstances = exclude
	local op = OverlapParams.new()
	op.FilterType = Enum.RaycastFilterType.Exclude
	op.FilterDescendantsInstances = exclude
	local out = {}
	for _, t in times do
		D.seek(t)
		local p = D.poseActor(name, t)
		local tg = p.targets
		local low, lowPart = math.huge, ""
		local hits = {}
		local floorY
		do
			local hp = tg.LowerTorso.Position
			local h0 = workspace:Raycast(Vector3.new(hp.X, math.min(tg.LeftFoot.Position.Y, tg.RightFoot.Position.Y) + 0.5, hp.Z),
				Vector3.new(0, -60, 0), rp)
			floorY = h0 and h0.Position.Y or -1e3
		end
		local function isFloor(q: BasePart): boolean
			-- the ground the character is on: flat parts whose top is at floor level (sidewalk, road, joints, grass)
			local top = q.Position.Y + q.Size.Y / 2
			return top <= floorY + 0.25 and q.Size.Y < 4
		end
		for _, pn in bodyOf(a.rig) do
			local part = a.rig:FindFirstChild(pn)
			local cf = tg[pn]
			if part and cf then
				local y = boxLowest(cf, part.Size)
				if y < low then low, lowPart = y, pn end
				do   -- feet too: floor parts are skipped by isFloor
					local core = part.Size * 0.8
					for _, q in workspace:GetPartBoundsInBox(cf, core, op) do
						if visible(q) and q.CanCollide and not ignore[q.Name] and not ignore[q.Parent.Name] and not isFloor(q) and not seatPart(q)
							and q:IsA("Part") and q.Shape == Enum.PartType.Block and select(2, obbOverlap(cf, core, q.CFrame, q.Size)) > MIN_DEPTH then
							hits[ownerName(q)] = true
						elseif visible(q) and q.CanCollide and not ignore[q.Name] and not ignore[q.Parent.Name] and not isFloor(q) and not seatPart(q)
							and not (q:IsA("Part") and q.Shape == Enum.PartType.Block) then
							hits[ownerName(q)] = true
						end
					end
				end
			end
		end
		local foot
		if a.rig:FindFirstChild("LeftFoot") then
			foot = math.min(boxLowest(tg.LeftFoot, a.rig.LeftFoot.Size), boxLowest(tg.RightFoot, a.rig.RightFoot.Size))
		else   -- R6: one-piece legs
			foot = math.min(boxLowest(tg["Left Leg"], a.rig["Left Leg"].Size), boxLowest(tg["Right Leg"], a.rig["Right Leg"].Size))
		end
		local function ground(pos)
			-- from just above the body point: a bench or table the character is next to/under isn't the floor;
			-- the seat in use (opts.ignore) is passed through
			local from = pos + Vector3.new(0, 0.5, 0)
			for _ = 1, 4 do
				local h = workspace:Raycast(from, Vector3.new(0, -60, 0), rp)
				if not h then return -1e3, "" end
				if not (ignore[h.Instance.Name] or (h.Instance.Parent and ignore[h.Instance.Parent.Name]) or seatPart(h.Instance)) then
					return h.Position.Y, h.Instance.Name
				end
				from = h.Position - Vector3.new(0, 0.05, 0)
			end
			return -1e3, ""
		end
		local lf, rf = tg.LeftFoot.Position, tg.RightFoot.Position
		local gl = ground(lf)
		local gr = ground(rf)
		local hips = tg.LowerTorso.Position
		local gH, gName = ground(Vector3.new(hips.X, math.min(lf.Y, rf.Y), hips.Z))
		-- what rests on a seat: the pelvis box and the hip ends of the thighs (the knee ends may dip past the edge)
		local function hipEnd(cf, size)
			local s = size / 2
			local best = math.huge
			for _, sx in { -1, 1 } do for _, sz in { -1, 1 } do
				best = math.min(best, (cf * Vector3.new(sx * s.X, s.Y * 0.4, sz * s.Z)).Y)
			end end
			return best
		end
		local thigh
		if a.rig:FindFirstChild("LeftUpperLeg") then
			thigh = math.min(boxLowest(tg.LowerTorso, a.rig.LowerTorso.Size),
				hipEnd(tg.LeftUpperLeg, a.rig.LeftUpperLeg.Size), hipEnd(tg.RightUpperLeg, a.rig.RightUpperLeg.Size))
		else   -- R6: the torso bottom and the top ends of the one-piece legs
			local tor = a.rig:FindFirstChild("Torso")
			thigh = math.min(boxLowest(tg.Torso, tor.Size), hipEnd(tg["Left Leg"], a.rig["Left Leg"].Size),
				hipEnd(tg["Right Leg"], a.rig["Right Leg"].Size))
		end
		local look = tg.HumanoidRootPart.LookVector
		local hl = {}
		for k in hits do table.insert(hl, k) end
		table.insert(out, { t = t, hips = { hips.X, hips.Y, hips.Z }, look = { look.X, look.Z }, low = low, lowPart = lowPart,
			foot = foot, gF = math.max(gl, gr), gH = gH, gName = gName, hits = hl, thigh = thigh })
	end
	return HttpService:JSONEncode(out)
end

-- Camera checks at story time t for cameras {pos={x,y,z}, look={x,y,z}, subjects={names}, r}: what the camera is
-- inside of (or within r studs of), and for each subject whether its head / torso are blocked from the camera,
-- plus the subject's head, hips and feet positions (for framing checks in Python).
function D.camcheck(t: number, cams)
	if not D.actors then D.load() end
	D.seek(t)
	task.wait()   -- joint (Motor6D) poses reach the parts only on the next frame; rays must see this pose, not the last
	local res = {}
	for _, c in cams do
		local pos = Vector3.new(c.pos[1], c.pos[2], c.pos[3])
		local near = {}
		local op = OverlapParams.new()
		for _, q in workspace:GetPartBoundsInRadius(pos, c.r or 0.6, op) do
			if visible(q) and not isCull(q) then
				-- precise: the camera point inside the part's box (or near its surface)
				local lp = q.CFrame:PointToObjectSpace(pos)
				local s = q.Size / 2 + Vector3.new(1, 1, 1) * (c.r or 0.6)
				if math.abs(lp.X) <= s.X and math.abs(lp.Y) <= s.Y and math.abs(lp.Z) <= s.Z then
					near[ownerName(q)] = true
				end
			end
		end
		-- too close to any character (a head, a hat, an arm right at the lens fills the frame)
		for _, q in workspace:GetPartBoundsInRadius(pos, 1.2, op) do
			if visible(q) then
				local m = q:FindFirstAncestorOfClass("Model")
				while m and not m:FindFirstChildOfClass("Humanoid") do m = m.Parent and m.Parent:FindFirstAncestorOfClass("Model") end
				if m then
					local lp = q.CFrame:PointToObjectSpace(pos)
					local s2 = q.Size / 2 + Vector3.new(1, 1, 1) * 1.0
					if math.abs(lp.X) <= s2.X and math.abs(lp.Y) <= s2.Y and math.abs(lp.Z) <= s2.Z then
						near[m.Name .. ".closeup"] = true
					end
				end
			end
		end
		local nl = {}
		for k in near do table.insert(nl, k) end
		local subs = {}
		for _, sname in c.subjects or {} do
			local a = D.actors[sname]
			if a then
				local p = D.poseActor(sname, t)
				local tg = p.targets
				local others = {}
				local rp = RaycastParams.new()
				rp.FilterType = Enum.RaycastFilterType.Exclude
				local ex = { a.rig }
				for _, q in cullables() do table.insert(ex, q) end   -- cut-away walls don't block
				rp.FilterDescendantsInstances = ex
				local blocked = {}
				local nb = 0
				for _, pn in { "Head", "UpperTorso", "LowerTorso" } do
					local target = tg[pn].Position
					local hit = workspace:Raycast(pos, target - pos, rp)
					if hit and visible(hit.Instance) then
						nb += 1
						blocked[ownerName(hit.Instance)] = true
					end
				end
				-- and back from the head: a camera inside a mesh (throne back, wall) is invisible to rays that start
				-- inside it, but a ray from the subject hits the mesh's outside
				local back = workspace:Raycast(tg.Head.Position, pos - tg.Head.Position, rp)
				if back and visible(back.Instance) then
					nb += 2
					blocked[ownerName(back.Instance)] = true
				end
				for k in blocked do table.insert(others, k) end
				-- face: is the camera in front of the head (1 = straight on, <0 = behind), and is the face hidden
				-- by the subject's own arms/props (the rays above ignore the subject's own body)
				local hc = tg.Head
				-- the face plate's normal toward the camera (a head looking down needs a lower camera)
				local toCam = pos - hc.Position
				local face = toCam.Magnitude > 1e-3 and hc.LookVector:Dot(toCam.Unit) or 0
				local rp2 = RaycastParams.new()
				rp2.FilterType = Enum.RaycastFilterType.Exclude
				local skip = { a.rig:FindFirstChild("Head") }
				for _, acc in a.rig:GetChildren() do
					if acc:IsA("Accessory") then table.insert(skip, acc) end
				end
				for _, q in cullables() do table.insert(skip, q) end
				rp2.FilterDescendantsInstances = skip
				-- share of a 3x3 grid on the face (front of the head) hidden by anything but the head itself
				local hn, hb = 0, 0
				for iy = -1, 1 do
					for ix = -1, 1 do
						local fp = hc.Position + hc.LookVector * 0.6 + hc.RightVector * (ix * 0.4) + hc.UpVector * (iy * 0.35)
						local hit = workspace:Raycast(pos, fp - pos, rp2)
						hn += 1
						if hit and visible(hit.Instance) then hb += 1 end
					end
				end
				local selfhit = hb / hn
				subs[sname] = { blocked = nb, by = others, face = face, selfhit = selfhit, head = { tg.Head.Position.X, tg.Head.Position.Y, tg.Head.Position.Z },
					hips = { tg.LowerTorso.Position.X, tg.LowerTorso.Position.Y, tg.LowerTorso.Position.Z },
					foot = { tg.LeftFoot.Position.X, math.min(tg.LeftFoot.Position.Y, tg.RightFoot.Position.Y), tg.LeftFoot.Position.Z } }
				if c.lean then   -- framing search: scores only (Studio truncates tool output at 100k characters)
					subs[sname] = { blocked = nb, face = math.floor(face * 100) / 100, selfhit = math.floor(selfhit * 100) / 100 }
				end
			end
		end
		-- foreground: share of a 6x9 ray grid over the 9:16 frame that hits anything (an arm, a counter) in the
		-- near half of the way to the aim point, i.e. something big filling the frame in front of the subject
		local fg = 0
		if c.look then
			local look = Vector3.new(c.look[1], c.look[2], c.look[3])
			local cf = CFrame.lookAt(pos, look)
			local dist = (look - pos).Magnitude
			local th = math.tan(math.rad(c.fov or 40) / 2)
			local rp3 = RaycastParams.new()
			rp3.FilterType = Enum.RaycastFilterType.Exclude
			rp3.FilterDescendantsInstances = cullables()
			local n, hits = 0, 0
			for iy = 0, 8 do
				for ix = 0, 5 do
					local u = ((ix + 0.5) / 6 * 2 - 1) * th * 9 / 16
					local v = ((iy + 0.5) / 9 * 2 - 1) * th
					local dir = cf:VectorToWorldSpace(Vector3.new(u, v, -1).Unit) * dist * 0.55
					local hit = workspace:Raycast(pos, dir, rp3)
					n += 1
					if hit and visible(hit.Instance) then hits += 1 end
				end
			end
			fg = hits / n
		end
		table.insert(res, { near = nl, subjects = subs, fg = fg })
	end
	return HttpService:JSONEncode(res)
end

-- Body clipping at story times: per sample, each actor's deepest limb-into-own-body overlap (forearms/hands into
-- torso, head, thighs) and the deepest overlap between two characters' parts, in studs. Returns
-- {t, self={name=depth}, selfWhere={name=side}, pair={"a|b"=depth}} per time.
function D.bodycheck(times)
	if not D.actors then D.load() end
	local Player = D.Player()
	local names = {}
	for n in D.actors do table.insert(names, n) end
	table.sort(names)
	local out = {}
	for _, t in times do
		local poses = {}
		local selfd, selfw = {}, {}
		for _, n in names do
			local p = D.poseActor(n, t)
			if p then
				poses[n] = p.targets
				local d, w = p:SelfClip()
				selfd[n], selfw[n] = d, w
			end
		end
		local pair = {}
		for i = 1, #names do for j = i + 1, #names do
			local A, B = poses[names[i]], poses[names[j]]
			if A and B and (A.LowerTorso.Position - B.LowerTorso.Position).Magnitude < 12 then
				local ra, rb = D.actors[names[i]].rig, D.actors[names[j]].rig
				local best = 0
				for _, pa in bodyOf(ra) do for _, pb in bodyOf(rb) do
					local qa, qb = ra:FindFirstChild(pa), rb:FindFirstChild(pb)
					if qa and qb and A[pa] and B[pb] then
						local d = Player.obbDepth(A[pa], qa.Size, B[pb], qb.Size)
						if d > best then best = d end
					end
				end end
				pair[names[i] .. "|" .. names[j]] = best
			end
		end end
		-- limbs inside set pieces/props (walls, counters, benches, sourced models): spatial query with each limb's
		-- posed box shrunk to its core, ignoring floors (parts whose top is under the feet) and seats being sat on
		local prop = {}
		local setsF = workspace:FindFirstChild("Sets")
		if setsF then
			local qp = OverlapParams.new(); qp.FilterType = Enum.RaycastFilterType.Include
			qp.FilterDescendantsInstances = { setsF, workspace:FindFirstChild("Town") }
			for _, n in names do
				local P = poses[n]
				if P then
					local rig = D.actors[n].rig
					local foot = math.huge
					for _, pn in bodyOf(rig) do
						local q = rig:FindFirstChild(pn)
						if q and P[pn] then foot = math.min(foot, P[pn].Position.Y - q.Size.Y / 2) end
					end
					local hits, what = 0, nil
					for _, pn in bodyOf(rig) do
						local q = rig:FindFirstChild(pn)
						if q and P[pn] then
							for _, h in workspace:GetPartBoundsInBox(P[pn], q.Size * 0.6, qp) do
								local top = h.Position.Y + h.Size.Y / 2
								if h.Transparency < 0.9 and h.CanQuery and top > foot + 0.45 and h.Size.Magnitude > 0.6 then
									hits += 1; what = what or (h.Parent.Name .. "." .. h.Name .. "<" .. pn)
								end
							end
						end
					end
					if hits > 0 then prop[n] = what end
				end
			end
		end
		table.insert(out, { t = t, self = selfd, selfWhere = selfw, pair = pair, prop = prop })
	end
	return HttpService:JSONEncode(out)
end

-- Hips position of every actor at story time t (camera tracking): "name=x,y,z;..."
function D.hips(t: number)
	if not D.actors then D.load() end
	local out = {}
	for name in D.actors do
		local p = D.poseActor(name, t)
		if p then
			local h = p.targets.LowerTorso.Position
			out[name] = { h.X, h.Y, h.Z }
		end
	end
	return HttpService:JSONEncode(out)
end

return D
