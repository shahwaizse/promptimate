-- PromptimateAutoplay (Script in ServerScriptService, installed by roblox_install / roblox_perform).
-- Anchors the performing characters on the server. In Run mode (no players) it also performs the chains here;
-- in Play mode the LocalScript of the same name performs them on the client.
local Players = game:GetService("Players")
local RS = game:GetService("ReplicatedStorage")
local D = require(RS:WaitForChild("Promptimate"):WaitForChild("ShortDirector"))
D.load()
D.seek(0)
task.wait(1.5)
if #Players:GetPlayers() == 0 then
	D.autoplay()
end
