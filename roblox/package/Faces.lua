--!strict
-- Faces: expressive classic-style 2D faces drawn on a head with a SurfaceGui (no uploaded decals), switchable per
-- beat. Expressions: neutral, happy, grin, sad, crying, shocked, scared, angry, smug, tired, wink, sleeping, love.
--   local Faces = require(path.Faces); Faces.set(character, "shocked")
local Faces = {}

local INK = Color3.fromRGB(20, 20, 20)
local WHITE = Color3.fromRGB(255, 255, 255)

local function frame(parent: Instance, name: string, pos: UDim2, size: UDim2, color: Color3, round: number?, rot: number?)
	local f = Instance.new("Frame")
	f.Name = name
	f.AnchorPoint = Vector2.new(0.5, 0.5)
	f.Position = pos
	f.Size = size
	f.BackgroundColor3 = color
	f.BorderSizePixel = 0
	f.Rotation = rot or 0
	if round then
		local c = Instance.new("UICorner")
		c.CornerRadius = UDim.new(round, 0)
		c.Parent = f
	end
	f.Parent = parent
	return f
end

-- a mouth curve made of short rotated bars along a parabola: bend > 0 smiles, < 0 frowns
local function curve(parent: Instance, cx: number, cy: number, w: number, bend: number, thick: number)
	local n = 14
	for i = 0, n - 1 do
		local u0, u1 = i / n - 0.5, (i + 1) / n - 0.5
		local x0, x1 = cx + u0 * w, cx + u1 * w
		local y0, y1 = cy + bend * (1 - (2 * u0) ^ 2), cy + bend * (1 - (2 * u1) ^ 2)
		local len = math.sqrt((x1 - x0) ^ 2 + (y1 - y0) ^ 2)
		local ang = math.deg(math.atan2(y1 - y0, x1 - x0))
		frame(parent, "m" .. i, UDim2.fromScale((x0 + x1) / 2, (y0 + y1) / 2), UDim2.fromScale(len * 1.4, thick), INK, 0.5, ang)
	end
end

local function eye(parent: Instance, x: number, kind: string)
	local y = 0.36
	if kind == "closed" then
		curve(parent, x, y + 0.02, 0.13, -0.025, 0.035)
	elseif kind == "happy" then
		curve(parent, x, y + 0.02, 0.13, 0.04, 0.035)
	elseif kind == "wide" then
		frame(parent, "eyeW", UDim2.fromScale(x, y), UDim2.fromScale(0.15, 0.17), WHITE, 0.5)
		frame(parent, "eyeP", UDim2.fromScale(x, y), UDim2.fromScale(0.06, 0.07), INK, 0.5)
	elseif kind == "half" then
		frame(parent, "eye", UDim2.fromScale(x, y + 0.015), UDim2.fromScale(0.07, 0.05), INK, 0.4)
		frame(parent, "lid", UDim2.fromScale(x, y - 0.01), UDim2.fromScale(0.12, 0.025), INK, 0.5)
	elseif kind == "heart" then
		frame(parent, "h1", UDim2.fromScale(x - 0.022, y), UDim2.fromScale(0.06, 0.06), Color3.fromRGB(220, 40, 60), 0.5)
		frame(parent, "h2", UDim2.fromScale(x + 0.022, y), UDim2.fromScale(0.06, 0.06), Color3.fromRGB(220, 40, 60), 0.5)
		frame(parent, "h3", UDim2.fromScale(x, y + 0.03), UDim2.fromScale(0.055, 0.055), Color3.fromRGB(220, 40, 60), 0.1, 45)
	else
		frame(parent, "eye", UDim2.fromScale(x, y), UDim2.fromScale(0.065, 0.11), INK, 0.5)
		frame(parent, "glint", UDim2.fromScale(x + 0.012, y - 0.025), UDim2.fromScale(0.02, 0.03), WHITE, 0.5)
	end
end

local function brow(parent: Instance, x: number, side: number, tilt: number, lift: number)
	-- tilt > 0: inner end down (angry); < 0: inner end up (sad/worried)
	frame(parent, "brow", UDim2.fromScale(x, 0.22 - lift), UDim2.fromScale(0.14, 0.03), INK, 0.5, tilt * side)
end

local SPEC = {
	neutral = { eyes = "dot", brow = { 0, 0 }, mouth = { 0.005, 0.2 } },
	happy = { eyes = "dot", brow = { 0, 0.01 }, mouth = { 0.06, 0.3 } },
	grin = { eyes = "happy", brow = { 0, 0.02 }, mouth = "grin" },
	sad = { eyes = "dot", brow = { -18, 0.01 }, mouth = { -0.045, 0.22 } },
	crying = { eyes = "closed", brow = { -20, 0.01 }, mouth = "wail", tears = true },
	shocked = { eyes = "wide", brow = { 0, 0.05 }, mouth = "o" },
	scared = { eyes = "wide", brow = { -16, 0.04 }, mouth = { -0.03, 0.26 }, sweat = true },
	angry = { eyes = "dot", brow = { 22, -0.01 }, mouth = { -0.04, 0.2 } },
	smug = { eyes = "half", brow = { 8, 0.0 }, mouth = "smirk" },
	tired = { eyes = "half", brow = { -6, -0.01 }, mouth = { -0.015, 0.16 }, sweat = true },
	wink = { eyes = "wink", brow = { 0, 0.01 }, mouth = { 0.06, 0.28 } },
	sleeping = { eyes = "closed", brow = { 0, 0 }, mouth = { 0.0, 0.08 } },
	love = { eyes = "heart", brow = { -6, 0.02 }, mouth = { 0.06, 0.28 }, blush = true },
}
Faces.names = {}
for k in SPEC do
	table.insert(Faces.names, k)
end

function Faces.set(character: Model, expression: string)
	local head = character:FindFirstChild("Head") :: BasePart?
	if not head then
		return
	end
	if character:GetAttribute("PromptimateFace") == expression and head:FindFirstChild("PromptimateFace") then
		return
	end
	for _, d in head:GetChildren() do
		if d:IsA("Decal") then
			d.Transparency = 1
		end
	end
	if head:IsA("MeshPart") and head.TextureID ~= "" then
		head.TextureID = ""      -- newer heads paint the default face into the head's texture
	end
	local old = head:FindFirstChild("PromptimateFace")
	if old then
		old:Destroy()
	end
	-- draw on a thin invisible plate at the visible head's front surface: a classic R6 head is a 2x1x1 box holding a
	-- scaled round mesh, so the box's own front face is the wrong size and sits inside the visible head
	local plate = head:FindFirstChild("PromptimateFacePlate") :: BasePart?
	if not plate then
		local mesh = head:FindFirstChildOfClass("SpecialMesh")
		local w, h, d
		if mesh then
			local sc = mesh.Scale
			w, h, d = 1.0 * sc.X, 1.0 * sc.Y, 1.0 * sc.Z     -- the classic head mesh is about a 1-stud cube before scaling
		else
			w, h, d = head.Size.X, head.Size.Y, head.Size.Z
		end
		plate = Instance.new("Part")
		plate.Name = "PromptimateFacePlate"
		plate.Size = Vector3.new(w * 0.92, h * 0.92, 0.05)
		plate.Transparency = 1
		plate.CanCollide, plate.CanQuery, plate.CanTouch, plate.Massless = false, false, false, true
		plate.CastShadow = false
		plate.CFrame = head.CFrame * CFrame.new(0, 0, -d / 2 + 0.005)
		local wc = Instance.new("WeldConstraint")
		wc.Part0, wc.Part1 = head, plate
		wc.Parent = plate
		plate.Parent = head
	end
	local s = SPEC[expression] or SPEC.neutral
	local gui = Instance.new("SurfaceGui")
	gui.Name = "PromptimateFace"
	gui.Face = Enum.NormalId.Front
	gui.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	gui.PixelsPerStud = 200
	gui.LightInfluence = 1
	gui.ZOffset = 1
	gui.Adornee = plate
	local root = Instance.new("Frame")
	root.Size = UDim2.fromScale(1, 1)
	root.BackgroundTransparency = 1
	root.Parent = gui
	local L, R = 0.36, 0.64
	if s.eyes == "wink" then
		eye(root, L, "dot")
		eye(root, R, "happy")
	else
		eye(root, L, s.eyes)
		eye(root, R, s.eyes)
	end
	brow(root, L, 1, s.brow[1], s.brow[2])
	brow(root, R, -1, s.brow[1], s.brow[2])
	local m = s.mouth
	if m == "o" then
		frame(root, "mouthO", UDim2.fromScale(0.5, 0.6), UDim2.fromScale(0.12, 0.15), INK, 0.5)
	elseif m == "wail" then
		frame(root, "mouthW", UDim2.fromScale(0.5, 0.61), UDim2.fromScale(0.2, 0.12), INK, 0.45)
		frame(root, "tongue", UDim2.fromScale(0.5, 0.645), UDim2.fromScale(0.1, 0.04), Color3.fromRGB(200, 70, 80), 0.5)
	elseif m == "grin" then
		frame(root, "grin", UDim2.fromScale(0.5, 0.6), UDim2.fromScale(0.34, 0.13), INK, 0.45)
		frame(root, "teeth", UDim2.fromScale(0.5, 0.565), UDim2.fromScale(0.28, 0.04), WHITE, 0.3)
	elseif m == "smirk" then
		curve(root, 0.56, 0.6, 0.22, 0.035, 0.035)
	else
		curve(root, 0.5, 0.6, (m :: { number })[2], (m :: { number })[1], 0.035)
	end
	if s.tears then
		for _, x in { L, R } do
			frame(root, "tear", UDim2.fromScale(x, 0.5), UDim2.fromScale(0.05, 0.2), Color3.fromRGB(90, 170, 255), 0.5)
		end
	end
	if s.sweat then
		frame(root, "sweat", UDim2.fromScale(0.84, 0.24), UDim2.fromScale(0.06, 0.1), Color3.fromRGB(120, 190, 255), 0.5)
	end
	if s.blush then
		for _, x in { 0.24, 0.76 } do
			local b = frame(root, "blush", UDim2.fromScale(x, 0.5), UDim2.fromScale(0.12, 0.06), Color3.fromRGB(255, 120, 140), 0.5)
			b.BackgroundTransparency = 0.35
		end
	end
	gui.Parent = head
	character:SetAttribute("PromptimateFace", expression)
end

return Faces
