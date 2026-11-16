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
	D.cache = {}
	local perf = HttpService:JSONDecode(fresh(folder().Performance))
	D.perf = perf
	D.actors = {}
	for name, a in perf.actors do
		local rig = resolve(a.path)
		if rig then
			D.prepare(rig)
			D.actors[name] = { rig = rig, clips = a.clips }
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
	p = Player.new(a.rig, data, { origin = CFrame.new(c.x, c.y, c.z) * CFrame.Angles(0, c.yaw, 0) })
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
	return p, c
end

function D.seek(t: number)
	if not D.actors then D.load() end
	for name in D.actors do
		D.poseActor(name, t)
	end
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
		for _, pn in BODY do
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
		local foot = math.min(boxLowest(tg.LeftFoot, a.rig.LeftFoot.Size), boxLowest(tg.RightFoot, a.rig.RightFoot.Size))
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
		local thigh = math.min(boxLowest(tg.LowerTorso, a.rig.LowerTorso.Size),
			hipEnd(tg.LeftUpperLeg, a.rig.LeftUpperLeg.Size), hipEnd(tg.RightUpperLeg, a.rig.RightUpperLeg.Size))
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
	local res = {}
	for _, c in cams do
		local pos = Vector3.new(c.pos[1], c.pos[2], c.pos[3])
		local near = {}
		local op = OverlapParams.new()
		for _, q in workspace:GetPartBoundsInRadius(pos, c.r or 0.6, op) do
			if visible(q) then
				-- precise: the camera point inside the part's box (or near its surface)
				local lp = q.CFrame:PointToObjectSpace(pos)
				local s = q.Size / 2 + Vector3.new(1, 1, 1) * (c.r or 0.6)
				if math.abs(lp.X) <= s.X and math.abs(lp.Y) <= s.Y and math.abs(lp.Z) <= s.Z then
					near[ownerName(q)] = true
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
				rp.FilterDescendantsInstances = { a.rig }
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
				for k in blocked do table.insert(others, k) end
				subs[sname] = { blocked = nb, by = others, head = { tg.Head.Position.X, tg.Head.Position.Y, tg.Head.Position.Z },
					hips = { tg.LowerTorso.Position.X, tg.LowerTorso.Position.Y, tg.LowerTorso.Position.Z },
					foot = { tg.LeftFoot.Position.X, math.min(tg.LeftFoot.Position.Y, tg.RightFoot.Position.Y), tg.LeftFoot.Position.Z } }
			end
		end
		table.insert(res, { near = nl, subjects = subs })
	end
	return HttpService:JSONEncode(res)
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
