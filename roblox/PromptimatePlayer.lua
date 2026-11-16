--!strict
-- PromptimatePlayer: plays a Promptimate R15 clip (exported by mcp_server/roblox.py) on any R15 character.
--
-- Usage (LocalScript, so the result is what the Studio recording sees):
--   local Player = require(path.to.PromptimatePlayer)
--   local clip = Player.decode(require(path.to.MyClipModule))   -- a ModuleScript that returns the JSON string
--   local track = Player.new(character, clip, { origin = CFrame.new(0, 0, 0) })   -- origin: floor point + facing
--   track:Play()            -- or track:Play(startTime); track.Ended:Wait(); track:Stop()
--
-- How it works: each frame stores every R15 part's world rotation (relative to the clip start) and the hips
-- position in units of standing hip height. Joint Transforms are computed from the rig's own joint offsets, so
-- blocky, Rthro and custom R15 avatars all play the same data. Works with classic Motor6D rigs and with the newer
-- AnimationConstraint rigs (joint offsets = Attachment0/Attachment1 CFrames). The HumanoidRootPart follows the hips on the ground
-- (so follow cameras work); the character is put in Physics state with an anchored root while playing.

local RunService = game:GetService("RunService")
local HttpService = game:GetService("HttpService")

export type Clip = {
	name: string, fps: number, frames: number, loop: boolean, parts: { string },
	rot: { { number } }, root: { { number } }, contacts: { number }?,
	hands: { { number } }?, handBoxes: { string }?,
}

local MOTORS: { [string]: { parent: string, motor: string } } = {
	LowerTorso = { parent = "HumanoidRootPart", motor = "Root" },
	UpperTorso = { parent = "LowerTorso", motor = "Waist" },
	Head = { parent = "UpperTorso", motor = "Neck" },
	LeftUpperArm = { parent = "UpperTorso", motor = "LeftShoulder" },
	LeftLowerArm = { parent = "LeftUpperArm", motor = "LeftElbow" },
	LeftHand = { parent = "LeftLowerArm", motor = "LeftWrist" },
	RightUpperArm = { parent = "UpperTorso", motor = "RightShoulder" },
	RightLowerArm = { parent = "RightUpperArm", motor = "RightElbow" },
	RightHand = { parent = "RightLowerArm", motor = "RightWrist" },
	LeftUpperLeg = { parent = "LowerTorso", motor = "LeftHip" },
	LeftLowerLeg = { parent = "LeftUpperLeg", motor = "LeftKnee" },
	LeftFoot = { parent = "LeftLowerLeg", motor = "LeftAnkle" },
	RightUpperLeg = { parent = "LowerTorso", motor = "RightHip" },
	RightLowerLeg = { parent = "RightUpperLeg", motor = "RightKnee" },
	RightFoot = { parent = "RightLowerLeg", motor = "RightAnkle" },
}
-- parents before children
local ORDER = { "LowerTorso", "UpperTorso", "Head", "LeftUpperArm", "LeftLowerArm", "LeftHand", "RightUpperArm",
	"RightLowerArm", "RightHand", "LeftUpperLeg", "LeftLowerLeg", "LeftFoot", "RightUpperLeg", "RightLowerLeg",
	"RightFoot" }

-- Limb parts whose bone (joint attachment -> next joint attachment) the clip data aims "down" (-Y) in the rest
-- pose. Real rigs differ (e.g. the default R15 upper arm's bone leans ~33 degrees outward), so the player measures
-- each rig's rest bone and corrects for it.
local LIMB_BONES: { [string]: { string } } = {
	LeftUpperArm = { "LeftShoulderRigAttachment", "LeftElbowRigAttachment" },
	LeftLowerArm = { "LeftElbowRigAttachment", "LeftWristRigAttachment" },
	LeftHand = { "LeftWristRigAttachment", "LeftGripAttachment" },
	RightUpperArm = { "RightShoulderRigAttachment", "RightElbowRigAttachment" },
	RightLowerArm = { "RightElbowRigAttachment", "RightWristRigAttachment" },
	RightHand = { "RightWristRigAttachment", "RightGripAttachment" },
	LeftUpperLeg = { "LeftHipRigAttachment", "LeftKneeRigAttachment" },
	LeftLowerLeg = { "LeftKneeRigAttachment", "LeftAnkleRigAttachment" },
	RightUpperLeg = { "RightHipRigAttachment", "RightKneeRigAttachment" },
	RightLowerLeg = { "RightKneeRigAttachment", "RightAnkleRigAttachment" },
}

-- Separating-axis test of two oriented boxes. Returns the penetration depth (smallest overlap over the 15 axes; 0 when
-- apart) and that axis, pointing from box b towards box a.
local function obbDepth(ca: CFrame, sa: Vector3, cb: CFrame, sb: Vector3): (number, Vector3)
	local A = { ca.XVector, ca.YVector, ca.ZVector }
	local B = { cb.XVector, cb.YVector, cb.ZVector }
	local ea, eb = { sa.X / 2, sa.Y / 2, sa.Z / 2 }, { sb.X / 2, sb.Y / 2, sb.Z / 2 }
	local d = ca.Position - cb.Position
	local best, bestAx = math.huge, Vector3.yAxis
	local function test(ax: Vector3): boolean
		local ra = ea[1] * math.abs(A[1]:Dot(ax)) + ea[2] * math.abs(A[2]:Dot(ax)) + ea[3] * math.abs(A[3]:Dot(ax))
		local rb = eb[1] * math.abs(B[1]:Dot(ax)) + eb[2] * math.abs(B[2]:Dot(ax)) + eb[3] * math.abs(B[3]:Dot(ax))
		local s = d:Dot(ax)
		local o = ra + rb - math.abs(s)
		if o <= 0 then
			return false
		end
		if o < best then
			best, bestAx = o, (s >= 0 and ax or -ax)
		end
		return true
	end
	for i = 1, 3 do
		if not test(A[i]) or not test(B[i]) then
			return 0, Vector3.yAxis
		end
	end
	for i = 1, 3 do
		for j = 1, 3 do
			local c = A[i]:Cross(B[j])
			if c.Magnitude > 1e-6 and not test(c.Unit) then
				return 0, Vector3.yAxis
			end
		end
	end
	return best, bestAx
end

-- Self-clipping: R15 limbs and torsos are much thicker than the source body, so a hand that rests near the body in
-- the source (hands in the lap, arms crossed, phone at the ear) sinks into the blocky torso, head or thighs on the
-- rig. Each arm is swung rigidly about its shoulder just far enough to clear them; the swing is solved per frame,
-- then widened and smoothed over time so it eases in before contact and out after (no pops).
local ARM_PARTS = {
	Left = { "LeftUpperArm", "LeftLowerArm", "LeftHand" },
	Right = { "RightUpperArm", "RightLowerArm", "RightHand" },
}
local ARM_LIMBS = {
	Left = { "LeftLowerArm", "LeftHand" },
	Right = { "RightLowerArm", "RightHand" },
}
local BODY_OBSTACLES = { "UpperTorso", "LowerTorso", "Head", "LeftUpperLeg", "RightUpperLeg" }
local SELF_TOL = 0.2        -- fraction of a forearm/hand allowed inside the body (resting on it reads as normal)
local SELF_MAX, SELF_STEPS = math.rad(20), 10
local SELF_OPEN = { 0, math.rad(12), math.rad(25) }   -- elbow opening tried when a swing alone doesn't clear
local SELF_WIDEN, SELF_BLUR = 5, 4   -- frames

-- Shortest-arc rotation taking unit vector u onto unit vector v
local function arc(u: Vector3, v: Vector3): CFrame
	local c = math.clamp(u:Dot(v), -1, 1)
	local axis = u:Cross(v)
	if axis.Magnitude < 1e-6 then
		return c > 0 and CFrame.identity or CFrame.fromAxisAngle(Vector3.new(0, 0, 1), math.pi)
	end
	return CFrame.fromAxisAngle(axis.Unit, math.acos(c))
end

local Player = {}
Player.__index = Player
Player.obbDepth = obbDepth

function Player.decode(json: string): Clip
	return HttpService:JSONDecode(json) :: Clip
end

local function rotationOnly(cf: CFrame): CFrame
	return cf - cf.Position
end

-- Joint offsets: Part1.CFrame = Part0.CFrame * C0 * Transform * C1:Inverse() for both joint types
local function jointC0(j: Instance): CFrame
	if j:IsA("Motor6D") then
		return (j :: Motor6D).C0
	end
	return ((j :: AnimationConstraint).Attachment0 :: Attachment).CFrame
end
local function jointC1(j: Instance): CFrame
	if j:IsA("Motor6D") then
		return (j :: Motor6D).C1
	end
	return ((j :: AnimationConstraint).Attachment1 :: Attachment).CFrame
end

-- Rest-pose geometry from the joint offsets alone (all Transforms identity), so it doesn't depend on the pose the
-- rig is in right now (a clip created while the rig is still seated from the previous clip must get the same
-- scale). Returns (standing hips height: LowerTorso centre above the bottom of the feet, LowerTorso centre above the
-- HumanoidRootPart centre), in studs. Falls back to the current pose if a joint is missing.
local function restHeights(character: Model): (number, number)
	local rest: { [string]: CFrame } = { HumanoidRootPart = CFrame.identity }
	for _, name in ORDER do
		local part = character:FindFirstChild(name)
		local joint = part and part:FindFirstChild(MOTORS[name].motor)
		local parentCF = rest[MOTORS[name].parent]
		if not (joint and parentCF and (joint:IsA("Motor6D") or joint:IsA("AnimationConstraint"))) then
			local lt = character:FindFirstChild("LowerTorso") :: BasePart
			local root = character:FindFirstChild("HumanoidRootPart") :: BasePart
			local lowest = math.huge
			for _, n in { "LeftFoot", "RightFoot" } do
				local f = character:FindFirstChild(n) :: BasePart?
				if f then
					lowest = math.min(lowest, f.Position.Y - f.Size.Y / 2)
				end
			end
			return lt.Position.Y - lowest, lt.Position.Y - root.Position.Y
		end
		rest[name] = parentCF * jointC0(joint) * jointC1(joint):Inverse()
	end
	local lowest = math.huge
	for _, n in { "LeftFoot", "RightFoot" } do
		local f = character:FindFirstChild(n) :: BasePart
		lowest = math.min(lowest, rest[n].Y - f.Size.Y / 2)
	end
	return rest.LowerTorso.Y - lowest, rest.LowerTorso.Y
end

-- Rest measurements of an R15 character in studs: (standing hips height = LowerTorso centre above the bottom of the
-- feet, LowerTorso centre above the HumanoidRootPart centre). Clips scale by the first value (0.95 m of the source).
function Player.measure(character: Model): (number, number)
	return restHeights(character)
end

function Player.new(character: Model, clip: Clip, opts: { origin: CFrame?, speed: number?, groundClamp: boolean?, selfCollide: boolean? }?)
	local self = setmetatable({}, Player)
	self.character = character
	self.clip = clip
	self.speed = (opts and opts.speed) or 1
	-- lift low poses so no body part goes under the clip's floor (opts.groundClamp = false turns it off)
	self.groundClamp = not (opts and opts.groundClamp == false)
	-- Experimental, off by default (blind judging 2026-11-16 preferred plain playback on blocky R15: placement moved
	-- meaningful hand spots, e.g. a phone hand from the ear to the chest): opts.selfCollide = true swings arms out of
	-- the torso/head/thighs and places hands near the body by their spot on it.
	self.selfCollide = (opts and opts.selfCollide == true) or false
	self.humanoid = character:FindFirstChildOfClass("Humanoid")
	self.rootPart = character:FindFirstChild("HumanoidRootPart") :: BasePart
	assert(self.humanoid and self.rootPart, "PromptimatePlayer needs an R15 character with a Humanoid")
	assert(self.humanoid.RigType == Enum.HumanoidRigType.R15, "PromptimatePlayer needs an R15 rig")
	self.scale, self.rootToHips = restHeights(character)
	local here = self.rootPart.CFrame
	-- default origin: where the character stands now, facing its current look direction
	self.origin = (opts and opts.origin) or CFrame.lookAt(
		Vector3.new(here.Position.X, here.Position.Y - self.humanoid.HipHeight - self.rootPart.Size.Y / 2, here.Position.Z),
		Vector3.new(here.Position.X + here.LookVector.X, here.Position.Y - self.humanoid.HipHeight - self.rootPart.Size.Y / 2,
			here.Position.Z + here.LookVector.Z))
	self.motors = {}
	self.parts = {}
	for _, name in ORDER do
		local part = character:FindFirstChild(name) :: BasePart
		assert(part, "missing R15 part " .. name)
		local joint = part:FindFirstChild(MOTORS[name].motor)
		assert(joint and (joint:IsA("Motor6D") or joint:IsA("AnimationConstraint")),
			"missing joint " .. MOTORS[name].motor .. " (Motor6D or AnimationConstraint) in " .. name)
		self.motors[name] = joint
		self.parts[name] = part
	end
	-- per-limb rest correction: the clip aims each limb's rest bone along -Y; this rig's bone is `b`
	self.restFix = {}
	for name, atts in LIMB_BONES do
		local part = self.parts[name]
		local a0, a1 = part:FindFirstChild(atts[1]), part:FindFirstChild(atts[2])
		if a0 and a1 and a0:IsA("Attachment") and a1:IsA("Attachment") then
			local b = (a1.Position - a0.Position)
			if b.Magnitude > 1e-4 then
				self.restFix[name] = arc(b.Unit, Vector3.new(0, -1, 0))   -- maps the rig's rest bone onto -Y
			end
		end
	end
	-- part index in the clip's rot rows
	self.index = {}
	for i, name in clip.parts do
		self.index[name] = (i - 1) * 4
	end
	self.time = 0
	self.playing = false
	self.Ended = Instance.new("BindableEvent")
	self:_precomputeLocks()
	-- hands near the body: placed on the rig's body (clips exported with hand spots); older clips: arm push-out
	self.handPlace = self.selfCollide and clip.hands ~= nil
	if self.selfCollide then
		self:_precomputeArms()   -- what's left after hand placement: swing / open the arm clear
	end
	return self
end

local function quat(row: { number }, o: number): CFrame
	return CFrame.new(0, 0, 0, row[o + 1], row[o + 2], row[o + 3], row[o + 4])
end

-- Pose at time t (seconds): returns world CFrames for every part (rotation + LowerTorso position)
function Player:_sample(t: number)
	local clip = self.clip
	local f = t * clip.fps
	local n = clip.frames
	if clip.loop then
		f = f % (n - 1)
	else
		f = math.clamp(f, 0, n - 1)
	end
	local i0 = math.floor(f)
	local i1 = math.min(i0 + 1, n - 1)
	local a = f - i0
	local r0, r1 = clip.rot[i0 + 1], clip.rot[i1 + 1]
	local p0, p1 = clip.root[i0 + 1], clip.root[i1 + 1]
	local hips = Vector3.new(p0[1] + (p1[1] - p0[1]) * a, p0[2] + (p1[2] - p0[2]) * a, p0[3] + (p1[3] - p0[3]) * a)
	local world = {}
	local originRot = rotationOnly(self.origin)
	for _, name in ORDER do
		local o = self.index[name]
		local w = originRot * quat(r0, o):Lerp(quat(r1, o), a)
		local fix = self.restFix[name]
		world[name] = fix and w * fix or w
	end
	return world, self.origin * CFrame.new(hips * self.scale)
end

-- Root CFrame and every part's target CFrame for given world rotations (pure math, no instance writes)
function Player:_chain(world, hipsWorld: CFrame)
	-- HumanoidRootPart: on the ground under the hips, yawed like the pelvis (so follow cameras keep working)
	local look = (world.LowerTorso * Vector3.new(0, 0, -1)) * Vector3.new(1, 0, 1)
	if look.Magnitude < 1e-3 then
		look = self.origin.LookVector
	end
	local rootPos0 = self.origin.Position + Vector3.new(0, self.scale - self.rootToHips, 0)
	local p = Vector3.new(hipsWorld.X, rootPos0.Y, hipsWorld.Z)
	local rootCF = CFrame.lookAt(p, p + look.Unit)
	local targets: { [string]: CFrame } = { HumanoidRootPart = rootCF }
	targets.LowerTorso = CFrame.new(hipsWorld.Position) * world.LowerTorso
	local transforms = {}
	for _, name in ORDER do
		local joint = self.motors[name] :: any
		local c0, c1 = jointC0(joint), jointC1(joint)
		local parentCF = targets[MOTORS[name].parent]
		if name == "LowerTorso" then
			transforms[name] = (parentCF * c0):Inverse() * targets.LowerTorso * c1
		else
			-- rotation-only transform: joint positions come from the rig
			local rot = rotationOnly(parentCF * c0):Inverse() * world[name] * rotationOnly(c1)
			transforms[name] = rot
			targets[name] = parentCF * c0 * rot * c1:Inverse()
		end
	end
	return rootCF, targets, transforms
end

local LEGS = {
	{ upper = "LeftUpperLeg", lower = "LeftLowerLeg", hip = "LeftHipRigAttachment", knee = "LeftKneeRigAttachment",
		ankle = "LeftAnkleRigAttachment", bit = 1 },
	{ upper = "RightUpperLeg", lower = "RightLowerLeg", hip = "RightHipRigAttachment", knee = "RightKneeRigAttachment",
		ankle = "RightAnkleRigAttachment", bit = 2 },
}

-- Ankle world position of a leg from chain targets
function Player:_ankle(targets, leg): Vector3
	return (targets[leg.lower] * (self.parts[leg.lower]:FindFirstChild(leg.ankle) :: Attachment).CFrame).Position
end

-- Foot locking on this rig: planted spans (clip.contacts) pin the ankle where it touched down. R15 proportions
-- differ from the source skeleton, so without this, feet that were pinned in the source drift on the avatar.
function Player:_precomputeLocks()
	local clip = self.clip
	if not clip.contacts then
		return
	end
	local n = clip.frames
	local ankles = {}
	for f = 0, n - 1 do
		local world, hips = self:_sample(f / clip.fps)
		local _, targets = self:_chain(world, hips)
		ankles[f] = { self:_ankle(targets, LEGS[1]), self:_ankle(targets, LEGS[2]) }
	end
	self.locks = {}
	local BLEND = 4
	for li, leg in LEGS do
		local planted = {}
		for f = 0, n - 1 do
			planted[f] = bit32.band(clip.contacts[f + 1] or 0, leg.bit) ~= 0
		end
		local target, weight = {}, {}
		local f = 0
		while f < n do
			if planted[f] then
				local s = f
				while f < n and planted[f] do
					f += 1
				end
				local e = f - 1
				local pin = ankles[s][li]
				for g = math.max(0, s - BLEND), math.min(n - 1, e + BLEND) do
					local w = 1
					if g < s then
						w = 1 - (s - g) / (BLEND + 1)
					elseif g > e then
						w = 1 - (g - e) / (BLEND + 1)
					end
					w = w * w * (3 - 2 * w)   -- smoothstep
					if not weight[g] or w > weight[g] then
						weight[g], target[g] = w, pin
					end
				end
			else
				f += 1
			end
		end
		self.locks[li] = { target = target, weight = weight }
	end
end

-- Deepest overlap of one arm's forearm/hand with the body (torso, head, thighs) for chain targets.
-- Returns depth, push direction (body -> arm) and the point to push.
function Player:_armDepth(targets, side: string): (number, Vector3, Vector3)
	local best, dir, at = 0, Vector3.zero, Vector3.zero
	for _, ln in ARM_LIMBS[side] do
		local lp = self.parts[ln] :: BasePart
		for _, on in BODY_OBSTACLES do
			local op = self.parts[on] :: BasePart
			local d, ax = obbDepth(targets[ln], lp.Size, targets[on], op.Size)
			if d > best then
				best, dir, at = d, ax, targets[ln].Position
			end
		end
	end
	return best, dir, at
end

local openElbow

-- Rotate an arm rigidly about the shoulder (world rotations of all three parts)
local function swingArm(world, side: string, r: CFrame)
	for _, pn in ARM_PARTS[side] do
		world[pn] = r * world[pn]
	end
end

-- Open (straighten) an elbow by `ang` radians: rotate the forearm and hand about the elbow hinge
openElbow = function(self, world, targets, side: string, ang: number)
	local up, lo = self.parts[side .. "UpperArm"], self.parts[side .. "LowerArm"]
	local sa = up:FindFirstChild(side .. "ShoulderRigAttachment") :: Attachment?
	local ea = lo:FindFirstChild(side .. "ElbowRigAttachment") :: Attachment?
	local wa = lo:FindFirstChild(side .. "WristRigAttachment") :: Attachment?
	if not (sa and ea and wa) then
		return
	end
	local S = (targets[side .. "UpperArm"] * sa.CFrame).Position
	local E = (targets[side .. "LowerArm"] * ea.CFrame).Position
	local W = (targets[side .. "LowerArm"] * wa.CFrame).Position
	local n = (E - S):Cross(W - E)
	if n.Magnitude < 1e-4 then
		return
	end
	local r = CFrame.fromAxisAngle(n.Unit, -ang)
	world[side .. "LowerArm"] = r * world[side .. "LowerArm"]
	world[side .. "Hand"] = r * world[side .. "Hand"]
end

function Player:_shoulder(targets, side: string): Vector3
	local up = self.parts[side .. "UpperArm"]
	local att = up:FindFirstChild(side .. "ShoulderRigAttachment") :: Attachment?
	return att and (targets[side .. "UpperArm"] * att.CFrame).Position or targets[side .. "UpperArm"].Position
end

-- Per frame: the smallest rigid swing of each arm that clears the body, as a rotation vector in UpperTorso space;
-- then widened (max over +-SELF_WIDEN frames) and blurred (+-SELF_BLUR) so it eases in and out.
function Player:_precomputeArms()
	local clip = self.clip
	local n = clip.frames
	local raw = { Left = {}, Right = {} }
	local openAng = { Left = {}, Right = {} }
	local any = false
	for f = 0, n - 1 do
		local world, hips = self:_sample(f / clip.fps)
		local _, targets = self:_chain(world, hips)
		if self.handPlace and self:_placeHands(world, targets, f) then
			_, targets = self:_chain(world, hips)
		end
		local torsoRot = rotationOnly(targets.UpperTorso)
		for _, side in { "Left", "Right" } do
			local d0 = self:_hidden(targets, side)
			local rv = Vector3.zero
			openAng[side][f] = 0
			if d0 > SELF_TOL then
				local _, dir, at = self:_armDepth(targets, side)
				-- candidate swing axes: along the overlap's push direction, sideways (out from the body) and forward
				local S = self:_shoulder(targets, side)
				local cands = {}
				local ax = (at - S):Cross(dir)
				if ax.Magnitude > 1e-4 then table.insert(cands, ax.Unit) end
				local fwdAx, sideAx = torsoRot.LookVector, torsoRot.RightVector
				table.insert(cands, fwdAx); table.insert(cands, -fwdAx)
				table.insert(cands, sideAx); table.insert(cands, -sideAx)
				-- smallest change that clears; otherwise the least overlap (change as a tie-break), capped. A tightly
				-- bent elbow (phone at the ear, crossed arms) can't clear by swinging alone: also try opening it.
				local bestScore, bestRv, bestOpen = d0 - SELF_TOL, Vector3.zero, 0
				local cleared = false
				for _, open in SELF_OPEN do
					local base = world
					if open > 0 then
						base = table.clone(world)
						openElbow(self, base, targets, side, open)
						local _, tb = self:_chain(base, hips)
						local db = self:_hidden(tb, side)
						local sb = math.max(db - SELF_TOL, 0) + open * 0.4
						if db <= SELF_TOL then
							if sb < bestScore then bestScore, bestRv, bestOpen = sb, Vector3.zero, open end
							cleared = true
						elseif sb < bestScore then
							bestScore, bestRv, bestOpen = sb, Vector3.zero, open
						end
					end
					for _, axis in cands do
						local prevD = math.huge
						for k = 1, SELF_STEPS do
							local ang = SELF_MAX * k / SELF_STEPS
							local w2 = table.clone(base)
							swingArm(w2, side, CFrame.fromAxisAngle(axis, ang))
							local _, t2 = self:_chain(w2, hips)
							local d = self:_hidden(t2, side)
							local score = math.max(d - SELF_TOL, 0) + ang * 0.4 + open * 0.4
							if score >= bestScore and d > SELF_TOL and k > 3 and d > prevD then break end
							if score < bestScore then bestScore, bestRv, bestOpen = score, axis * ang, open end
							if d <= SELF_TOL then cleared = true; break end
							prevD = d
						end
					end
					if cleared then break end   -- don't open the elbow when a swing alone clears
				end
				rv = torsoRot:VectorToObjectSpace(bestRv)
				openAng[side][f] = bestOpen
				any = any or rv.Magnitude > 0 or bestOpen > 0
			end
			raw[side][f] = rv
		end
	end
	if not any then
		self.armFix = nil
		return
	end
	self.armFix = {}
	for _, side in { "Left", "Right" } do
		local wide = {}
		for f = 0, n - 1 do
			local m = raw[side][f]
			for g = math.max(0, f - SELF_WIDEN), math.min(n - 1, f + SELF_WIDEN) do
				if raw[side][g].Magnitude > m.Magnitude then m = raw[side][g] end
			end
			wide[f] = m
		end
		local out = {}
		for f = 0, n - 1 do
			local s, c = Vector3.zero, 0
			for g = math.max(0, f - SELF_BLUR), math.min(n - 1, f + SELF_BLUR) do
				s += wide[g]
				c += 1
			end
			out[f] = s / c
		end
		self.armFix[side] = out
		local ow, oo = {}, {}
		for f = 0, n - 1 do
			local m = 0
			for g = math.max(0, f - SELF_WIDEN), math.min(n - 1, f + SELF_WIDEN) do m = math.max(m, openAng[side][g]) end
			ow[f] = m
		end
		for f = 0, n - 1 do
			local s, c = 0, 0
			for g = math.max(0, f - SELF_BLUR), math.min(n - 1, f + SELF_BLUR) do s += ow[g]; c += 1 end
			oo[f] = s / c
		end
		self.elbowFix = self.elbowFix or {}
		self.elbowFix[side] = oo
	end
end

-- Apply the precomputed arm swings at time t to the world rotations
function Player:_applyArms(world, t: number, hips: CFrame)
	if not self.armFix then
		return
	end
	local f = math.clamp(t * self.clip.fps, 0, self.clip.frames - 1)
	if self.clip.loop then
		f = (t * self.clip.fps) % (self.clip.frames - 1)
	end
	local i0 = math.floor(f)
	local i1 = math.min(i0 + 1, self.clip.frames - 1)
	local a = f - i0
	local torsoRot = world.UpperTorso
	if self.elbowFix then
		local targets
		for side, fix in self.elbowFix do
			local o = fix[i0] + (fix[i1] - fix[i0]) * a
			if o > 1e-4 then
				if not targets then
					local _, tg = self:_chain(world, hips)
					targets = tg
				end
				openElbow(self, world, targets, side, o)
			end
		end
	end
	for side, fix in self.armFix do
		local rv = fix[i0]:Lerp(fix[i1], a)
		local ang = rv.Magnitude
		if ang > 1e-4 then
			swingArm(world, side, CFrame.fromAxisAngle(torsoRot:VectorToWorldSpace(rv / ang), ang))
		end
	end
end

-- Deepest limb-into-own-body overlap at the current pose (studs), for automated checks
-- How much of a forearm or hand is hidden inside the body (torso, head, thighs) at the current pose: the fraction
-- of a 5x5x5 grid of points in the limb's box that fall inside a body part's box. That is what reads as clipping;
-- a limb resting flush on the body, or touching it at an angle, hides little.
local GRID = { -0.8, -0.4, 0, 0.4, 0.8 }
function Player:_hidden(tg, side: string): (number, string)
	local best, where = 0, ""
	do
		for _, ln in ARM_LIMBS[side] do
			local cf, h = tg[ln], (self.parts[ln] :: BasePart).Size / 2
			local inside, total = 0, 0
			for _, x in GRID do for _, y in GRID do for _, z in GRID do
				local p = cf * Vector3.new(x * h.X, y * h.Y, z * h.Z)
				total += 1
				for _, on in BODY_OBSTACLES do
					local l = tg[on]:PointToObjectSpace(p)
					local s = (self.parts[on] :: BasePart).Size / 2
					if math.abs(l.X) < s.X and math.abs(l.Y) < s.Y and math.abs(l.Z) < s.Z then
						inside += 1
						break
					end
				end
			end end end
			local frac = inside / total
			if frac > best then best, where = frac, ln end
		end
	end
	return best, where
end

function Player:SelfClip(): (number, string)
	if not self.targets then
		return 0, ""
	end
	local a, wa = self:_hidden(self.targets, "Left")
	local b, wb = self:_hidden(self.targets, "Right")
	if a >= b then return a, wa end
	return b, wb
end

-- Hands near the body (clip.hands, from mcp_server/roblox.py): put the rig's wrist at the same spot on the same body
-- part as in the source, at the source clearance plus this rig's forearm thickness, with two-bone arm IK.
local HAND_STRIDE = 18
function Player:_wristGoal(targets, f: number, side: string): (Vector3?, number)
	local h = self.clip.hands
	if not h then
		return nil, 0
	end
	local row = h[f + 1]
	local o = (side == "Left" and 0 or HAND_STRIDE) + 1
	local near = row[o]
	if near <= 1e-3 then
		return nil, 0
	end
	local lower = self.parts[side .. "LowerArm"] :: BasePart
	local rR = math.min(lower.Size.X, lower.Size.Z) / 2
	local function spot(k: number): Vector3
		local part = self.clip.handBoxes[row[k] + 1]
		local cf, size = targets[part], (self.parts[part] :: BasePart).Size / 2
		local q = Vector3.new(row[k + 1] * size.X, row[k + 2] * size.Y, row[k + 3] * size.Z)
		local n = Vector3.new(row[k + 4], row[k + 5], row[k + 6])
		return cf * (q + n * (row[k + 7] * self.scale + rR)), cf:VectorToWorldSpace(n)
	end
	local g, out = spot(o + 1)
	local b = row[o + 17]
	if b > 1e-3 then
		local g2, out2 = spot(o + 9)
		g = g:Lerp(g2, b)
		out = (out:Lerp(out2, b)).Magnitude > 1e-3 and out:Lerp(out2, b).Unit or out
	end
	-- the rig's parts overlap where the source body has room (a blocky pelvis over the lap): push the goal out of
	-- every body part, inflated by the forearm thickness
	for _ = 1, 3 do
		local moved = false
		for _, on in BODY_OBSTACLES do
			local cf, s = targets[on], (self.parts[on] :: BasePart).Size / 2 + Vector3.new(rR, rR, rR)
			local l = cf:PointToObjectSpace(g)
			local px, py, pz = s.X - math.abs(l.X), s.Y - math.abs(l.Y), s.Z - math.abs(l.Z)
			if px > 0 and py > 0 and pz > 0 then
				-- leave along the way the hand faces off the body in the source (a lap hand goes forward onto
				-- the thighs, not up into the chest); the nearest face only if that way is blocked
				local d = cf:VectorToObjectSpace(out)
				local tx = math.abs(d.X) > 1e-4 and ((d.X > 0 and s.X or -s.X) - l.X) / d.X or math.huge
				local ty = math.abs(d.Y) > 1e-4 and ((d.Y > 0 and s.Y or -s.Y) - l.Y) / d.Y or math.huge
				local tz = math.abs(d.Z) > 1e-4 and ((d.Z > 0 and s.Z or -s.Z) - l.Z) / d.Z or math.huge
				local tExit = math.min(tx, ty, tz)
				if tExit < 2.5 then
					l = l + d * (tExit + 1e-3)
				elseif px <= py and px <= pz then
					l = Vector3.new(l.X >= 0 and s.X or -s.X, l.Y, l.Z)
				elseif py <= pz then
					l = Vector3.new(l.X, l.Y >= 0 and s.Y or -s.Y, l.Z)
				else
					l = Vector3.new(l.X, l.Y, l.Z >= 0 and s.Z or -s.Z)
				end
				g = cf * l
				moved = true
			end
		end
		if not moved then
			break
		end
	end
	return g, near
end

-- Hand placement for frame f (world rotations updated); true if anything moved
function Player:_placeHands(world, targets, f: number): boolean
	local changed = false
	for _, side in { "Left", "Right" } do
		local g, near = self:_wristGoal(targets, f, side)
		if g then
			self:_armIK(world, targets, side, self:_wrist(targets, side):Lerp(g, near))
			changed = true
		end
	end
	return changed
end

function Player:_wrist(targets, side: string): Vector3
	local lo = self.parts[side .. "LowerArm"]
	local wa = lo:FindFirstChild(side .. "WristRigAttachment") :: Attachment?
	return wa and (targets[side .. "LowerArm"] * wa.CFrame).Position or targets[side .. "Hand"].Position
end

-- Two-bone IK on one arm: upper and lower arm turn so the wrist reaches `goal` (elbow stays in its plane); the hand
-- keeps its world rotation
function Player:_armIK(world, targets, side: string, goal: Vector3)
	local up, lo = self.parts[side .. "UpperArm"], self.parts[side .. "LowerArm"]
	local sa = up:FindFirstChild(side .. "ShoulderRigAttachment") :: Attachment?
	local ea = up:FindFirstChild(side .. "ElbowRigAttachment") :: Attachment?
	if not (sa and ea) then
		return
	end
	local S = (targets[side .. "UpperArm"] * sa.CFrame).Position
	local E = (targets[side .. "UpperArm"] * ea.CFrame).Position
	local W = self:_wrist(targets, side)
	local L1, L2 = (E - S).Magnitude, (W - E).Magnitude
	local toGoal = goal - S
	if toGoal.Magnitude < 1e-4 then
		return
	end
	local d = math.clamp(toGoal.Magnitude, math.abs(L1 - L2) + 1e-3, L1 + L2 - 1e-3)
	local dir = toGoal.Unit
	local pole = (E - S) - dir * (E - S):Dot(dir)
	if pole.Magnitude < 1e-4 then
		pole = -(world.UpperTorso * Vector3.new(0, 1, 0)) - dir * (-(world.UpperTorso * Vector3.new(0, 1, 0))):Dot(dir)
		if pole.Magnitude < 1e-4 then
			return
		end
	end
	pole = pole.Unit
	local a = (L1 * L1 + d * d - L2 * L2) / (2 * d)
	local hgt = math.sqrt(math.max(L1 * L1 - a * a, 0))
	local E2 = S + dir * a + pole * hgt
	local W2 = S + dir * d
	world[side .. "UpperArm"] = arc((E - S).Unit, (E2 - S).Unit) * world[side .. "UpperArm"]
	world[side .. "LowerArm"] = arc((W - E).Unit, (W2 - E2).Unit) * world[side .. "LowerArm"]
end

-- Two-bone IK on one leg: rotate the upper and lower leg so the ankle reaches `goal` (knee stays in its plane)
function Player:_legIK(world, targets, leg, goal: Vector3)
	local up, lo = self.parts[leg.upper], self.parts[leg.lower]
	local H = (targets[leg.upper] * (up:FindFirstChild(leg.hip) :: Attachment).CFrame).Position
	local K = (targets[leg.upper] * (up:FindFirstChild(leg.knee) :: Attachment).CFrame).Position
	local A = self:_ankle(targets, leg)
	local L1, L2 = (K - H).Magnitude, (A - K).Magnitude
	local toGoal = goal - H
	local d = math.clamp(toGoal.Magnitude, math.abs(L1 - L2) + 1e-3, L1 + L2 - 1e-3)
	local dir = toGoal.Unit
	local pole = (K - H) - dir * (K - H):Dot(dir)
	if pole.Magnitude < 1e-4 then
		pole = (world.LowerTorso * Vector3.new(0, 0, -1)) - dir * (world.LowerTorso * Vector3.new(0, 0, -1)):Dot(dir)
	end
	pole = pole.Unit
	local a = (L1 * L1 + d * d - L2 * L2) / (2 * d)
	local h = math.sqrt(math.max(L1 * L1 - a * a, 0))
	local K2 = H + dir * a + pole * h
	local A2 = H + dir * d
	world[leg.upper] = arc((K - H).Unit, (K2 - H).Unit) * world[leg.upper]
	world[leg.lower] = arc((A - K).Unit, (A2 - K2).Unit) * world[leg.lower]
end

function Player:_apply(t: number)
	local world, hipsWorld = self:_sample(t)
	local rootCF, targets, transforms = self:_chain(world, hipsWorld)
	if self.locks then
		local f = math.clamp(math.floor(t * self.clip.fps + 0.5), 0, self.clip.frames - 1)
		local changed = false
		for li, leg in LEGS do
			local lk = self.locks[li]
			local w = lk.weight[f]
			if w and w > 0 then
				local A = self:_ankle(targets, leg)
				self:_legIK(world, targets, leg, A:Lerp(lk.target[f], w))
				changed = true
			end
		end
		if changed then
			rootCF, targets, transforms = self:_chain(world, hipsWorld)
		end
	end
	if self.handPlace then
		local f = math.clamp(math.floor(t * self.clip.fps + 0.5), 0, self.clip.frames - 1)
		if self:_placeHands(world, targets, f) then
			rootCF, targets, transforms = self:_chain(world, hipsWorld)
		end
	end
	if self.armFix then
		self:_applyArms(world, t, hipsWorld)
		rootCF, targets, transforms = self:_chain(world, hipsWorld)
	end
	if self.groundClamp then
		-- Lying, sitting on the ground, crawling, falls: rig parts are thicker than the source body, so a pose that
		-- rests on the floor in the source dips the arms, shins or torso under it on the rig. Lift the pose by the
		-- deepest dip of the body (zero for standing poses, which foot locking handles; continuous, so no pops).
		-- The head is left out: rig heads are far bigger than the source's, and lifting the whole body to clear a
		-- head tipped back onto the floor makes a lying character hover; the head is tilted up off the floor instead.
		local floorY = self.origin.Position.Y
		local function lowest(tg, name): number
			-- MeshPart bodies (Rthro, classic Man/Woman...): Size is a loose box around a rounded mesh: test a core
			local part = self.parts[name] :: BasePart
			local k = part:IsA("MeshPart") and (name == "Head" and 0.75 or 0.85) or 1
			local cf, h = tg[name], part.Size / 2 * k
			local lo = math.huge
			for _, sx in { -1, 1 } do
				for _, sy in { -1, 1 } do
					for _, sz in { -1, 1 } do
						lo = math.min(lo, (cf * Vector3.new(sx * h.X, sy * h.Y, sz * h.Z)).Y)
					end
				end
			end
			return lo
		end
		-- the body rests on its torso and legs; arms and head that dip under the floor are lifted on their own
		local low = math.huge
		for _, name in { "LowerTorso", "UpperTorso", "LeftUpperLeg", "RightUpperLeg", "LeftLowerLeg", "RightLowerLeg" } do
			low = math.min(low, lowest(targets, name))
		end
		if low < floorY then
			hipsWorld = hipsWorld + Vector3.new(0, floorY - low, 0)
			rootCF, targets, transforms = self:_chain(world, hipsWorld)
		end
		for _, side in { "Left", "Right" } do
			local function armLow(tg)
				return math.min(lowest(tg, side .. "UpperArm"), lowest(tg, side .. "LowerArm"), lowest(tg, side .. "Hand"))
			end
			if armLow(targets) < floorY - 0.02 then
				-- swing the arm about the shoulder (the smallest angle, any direction) until it rests on the floor
				local saved = { world[side .. "UpperArm"], world[side .. "LowerArm"], world[side .. "Hand"] }
				local tr = world.UpperTorso
				local best, bestAng = nil, math.huge
				for _, axis in { tr.LookVector, -tr.LookVector, tr.RightVector, -tr.RightVector } do
					for k2 = 1, 12 do
						local ang = math.rad(5 * k2)
						if ang >= bestAng then
							break
						end
						local r = CFrame.fromAxisAngle(axis, ang)
						world[side .. "UpperArm"], world[side .. "LowerArm"], world[side .. "Hand"] =
							r * saved[1], r * saved[2], r * saved[3]
						local _, tg2 = self:_chain(world, hipsWorld)
						if armLow(tg2) >= floorY - 0.02 then
							best, bestAng = { world[side .. "UpperArm"], world[side .. "LowerArm"], world[side .. "Hand"] }, ang
							break
						end
					end
				end
				local use = best or saved
				world[side .. "UpperArm"], world[side .. "LowerArm"], world[side .. "Hand"] = use[1], use[2], use[3]
				rootCF, targets, transforms = self:_chain(world, hipsWorld)
			end
		end
		if lowest(targets, "Head") < floorY - 0.02 then
			-- tilt the head about the neck (forward/back, then sideways) by the smallest angle that clears
			local base = world.Head
			local best, bestAng = nil, math.huge
			for _, axis in { base.RightVector, -base.RightVector, base.LookVector, -base.LookVector } do
				for k2 = 1, 12 do
					local ang = math.rad(5 * k2)
					if ang >= bestAng then
						break
					end
					world.Head = CFrame.fromAxisAngle(axis, ang) * base
					local _, tg2 = self:_chain(world, hipsWorld)
					if lowest(tg2, "Head") >= floorY - 0.02 then
						best, bestAng = world.Head, ang
						break
					end
				end
			end
			world.Head = best or base
			if not best then   -- can't clear by tilting: lift by what's left
				local _, tg3 = self:_chain(world, hipsWorld)
				hipsWorld = hipsWorld + Vector3.new(0, math.max(0, floorY - lowest(tg3, "Head")), 0)
			end
			rootCF, targets, transforms = self:_chain(world, hipsWorld)
		end
	end
	self.rootPart.CFrame = rootCF
	for _, name in ORDER do
		(self.motors[name] :: any).Transform = transforms[name]
	end
	self.targets = targets
end

function Player:Play(startTime: number?)
	self.time = startTime or 0
	self.playing = true
	-- stop the default Animate script / tracks and keep physics out of the way while we drive the rig
	local animate = self.character:FindFirstChild("Animate")
	if animate and animate:IsA("LocalScript") then
		animate.Enabled = false
	end
	local animator = self.humanoid:FindFirstChildOfClass("Animator")
	if animator then
		for _, tr in animator:GetPlayingAnimationTracks() do
			tr:Stop(0)
		end
	end
	self.rootPart.Anchored = true
	self.humanoid:ChangeState(Enum.HumanoidStateType.Physics)
	local event = RunService:IsClient() and RunService.PreRender or RunService.PreSimulation
	self.conn = event:Connect(function(dt)
		if not self.playing then
			return
		end
		self.time += dt * self.speed
		self:_apply(self.time)
		if not self.clip.loop and self.time * self.clip.fps >= self.clip.frames - 1 then
			self.playing = false
			self.Ended:Fire()
		end
	end)
	self:_apply(self.time)
end

-- Jump to a time and hold the pose (scrubbing / stills)
function Player:Seek(t: number)
	self.time = t
	self:_apply(t)
end

function Player:Stop()
	self.playing = false
	if self.conn then
		self.conn:Disconnect()
		self.conn = nil
	end
end

-- Target CFrames of every R15 part at time t (what the joints are set to produce), for automated checks
function Player:SampleTargets(t: number): { [string]: CFrame }
	self:_apply(t)
	return self.targets
end

return Player
