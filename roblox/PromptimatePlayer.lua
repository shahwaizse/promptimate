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
	rot: { { number } }, root: { { number } },
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

function Player.decode(json: string): Clip
	return HttpService:JSONDecode(json) :: Clip
end

local function rotationOnly(cf: CFrame): CFrame
	return cf - cf.Position
end

-- Standing hips height in studs: LowerTorso centre above the bottom of the feet, measured on the rest rig.
local function standHeight(character: Model): number
	local lt = character:FindFirstChild("LowerTorso") :: BasePart
	local lowest = math.huge
	for _, n in { "LeftFoot", "RightFoot" } do
		local f = character:FindFirstChild(n) :: BasePart?
		if f then
			lowest = math.min(lowest, f.Position.Y - f.Size.Y / 2)
		end
	end
	return lt.Position.Y - lowest
end

function Player.new(character: Model, clip: Clip, opts: { origin: CFrame?, speed: number? }?)
	local self = setmetatable({}, Player)
	self.character = character
	self.clip = clip
	self.speed = (opts and opts.speed) or 1
	self.humanoid = character:FindFirstChildOfClass("Humanoid")
	self.rootPart = character:FindFirstChild("HumanoidRootPart") :: BasePart
	assert(self.humanoid and self.rootPart, "PromptimatePlayer needs an R15 character with a Humanoid")
	assert(self.humanoid.RigType == Enum.HumanoidRigType.R15, "PromptimatePlayer needs an R15 rig")
	self.scale = standHeight(character)
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
	-- vertical offset between the HumanoidRootPart centre and the LowerTorso centre on the rest rig
	self.rootToHips = self.parts.LowerTorso.Position.Y - self.rootPart.Position.Y
	self.time = 0
	self.playing = false
	self.Ended = Instance.new("BindableEvent")
	return self
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

function Player:_apply(t: number)
	local world, hipsWorld = self:_sample(t)
	-- HumanoidRootPart: on the ground under the hips, yawed like the pelvis (so follow cameras keep working)
	local look = (world.LowerTorso * Vector3.new(0, 0, -1)) * Vector3.new(1, 0, 1)
	if look.Magnitude < 1e-3 then
		look = self.origin.LookVector
	end
	local rootPos = Vector3.new(hipsWorld.X, hipsWorld.Y - self.rootToHips, hipsWorld.Z)
	local rootPos0 = self.origin.Position + Vector3.new(0, self.scale - self.rootToHips, 0)
	local rootCF = CFrame.lookAt(Vector3.new(rootPos.X, rootPos0.Y, rootPos.Z), Vector3.new(rootPos.X, rootPos0.Y, rootPos.Z) + look.Unit)
	self.rootPart.CFrame = rootCF
	-- Root motor carries the full hips placement relative to the HumanoidRootPart
	local targets: { [string]: CFrame } = { HumanoidRootPart = rootCF }
	targets.LowerTorso = CFrame.new(hipsWorld.Position) * world.LowerTorso
	for _, name in ORDER do
		local joint = self.motors[name] :: any
		local c0, c1 = jointC0(joint), jointC1(joint)
		local parentCF = targets[MOTORS[name].parent]
		if name == "LowerTorso" then
			joint.Transform = (parentCF * c0):Inverse() * targets.LowerTorso * c1
		else
			-- rotation-only transform: joint positions come from the rig
			local rot = rotationOnly(parentCF * c0):Inverse() * world[name] * rotationOnly(c1)
			joint.Transform = rot
			targets[name] = parentCF * c0 * rot * c1:Inverse()
		end
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
